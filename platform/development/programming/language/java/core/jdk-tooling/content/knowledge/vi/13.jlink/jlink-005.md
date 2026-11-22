# Launcher trong runtime image của jlink

**Launcher trong image** là lệnh khởi chạy ứng dụng được tạo cùng một runtime image bằng công cụ **jlink**. Launcher đã được cấu hình sẵn để dùng Java runtime nằm trong image và chạy một module cùng main class xác định. Người dùng có thể mở ứng dụng bằng một lệnh riêng như greeter thay vì phải gõ đầy đủ đường dẫn tới java và module/main class.

Tùy chọn tạo launcher là:

~~~bash
--launcher <command>=<module>/<main-class>
~~~

Ví dụ:

~~~bash
jlink \
    --module-path mods \
    --add-modules com.example.cli \
    --launcher greeter=com.example.cli/com.example.cli.Main \
    --output image
~~~

Lệnh trên tạo runtime image trong thư mục image, thêm module com.example.cli và tạo launcher có tên greeter trong thư mục bin của image. Trên Unix-like systems, có thể chạy image/bin/greeter; trên Windows, launcher thường là image\bin\greeter.bat.

Launcher dùng runtime đi kèm image. Máy đích không cần cài riêng JDK hoặc JRE tương thích, miễn là image được tạo cho hệ điều hành và kiến trúc phù hợp.

## 1. Runtime image và launcher có vai trò gì?

jlink liên kết một tập module Java cùng các dependency bắc cầu của chúng để tạo một runtime image tùy chỉnh. Image thường nhỏ hơn một JDK đầy đủ vì chỉ chứa các module và tài nguyên cần thiết cho ứng dụng.

Một runtime image có thể chứa:

- Java runtime và các module nền tảng mà ứng dụng cần.
- Các module ứng dụng đã được đưa vào image.
- Các thư viện native và tài nguyên runtime tương ứng với nền tảng.
- Thư mục bin chứa lệnh java và các lệnh khác được liên kết.
- Các launcher ứng dụng được tạo bằng tùy chọn --launcher.

Ví dụ cấu trúc khái quát:

~~~text
image/
├── bin/
│   ├── java
│   ├── keytool
│   └── greeter
├── conf/
├── legal/
├── lib/
└── release
~~~

Tên file và tập thư mục thực tế phụ thuộc JDK, hệ điều hành, module được liên kết và các tùy chọn tối ưu. Trên Windows, launcher tùy chỉnh được tạo dưới dạng batch script, thường có đuôi .bat; trên Unix-like systems, nó là shell script.

Hai cách chạy ứng dụng từ image:

~~~bash
image/bin/java \
    --module com.example.cli/com.example.cli.Main
~~~

hoặc dùng launcher đã tạo:

~~~bash
image/bin/greeter
~~~

Cả hai đều sử dụng runtime bên trong image. Launcher chỉ giúp cố định module và main class để lệnh khởi chạy ngắn gọn hơn.

## 2. Cú pháp --launcher

Cú pháp đầy đủ:

~~~bash
jlink --launcher <command>=<module>
jlink --launcher <command>=<module>/<main-class>
~~~

Các thành phần:

- **command:** tên lệnh launcher được tạo trong thư mục bin.
- **module:** tên module ứng dụng đã được liên kết vào image.
- **main-class:** tên đầy đủ của lớp có phương thức main cần chạy.

Ví dụ:

~~~bash
--launcher inventory=com.example.inventory/com.example.inventory.Main
~~~

Image sẽ có launcher tên inventory. Launcher được cấu hình để chạy main class com.example.inventory.Main trong module com.example.inventory.

### Có thể bỏ main class không?

Có thể dùng dạng:

~~~bash
--launcher inventory=com.example.inventory
~~~

Khi không chỉ định main class trong tùy chọn launcher, module phải có main class được ghi trong ModuleMainClass attribute. Attribute này thường được thiết lập khi đóng gói modular JAR bằng tùy chọn --main-class của công cụ jar.

Khi chưa chắc module đã có main class metadata, nên chỉ định đầy đủ module/main-class trong --launcher. Cách này làm rõ entry point và tránh phụ thuộc vào metadata của artifact.

### Launcher phải trỏ tới module trong image

Module được ghi trong --launcher phải nằm trong tập module mà jlink liên kết. Thông thường, module ứng dụng được đưa vào bằng --add-modules; jlink tiếp tục thêm các dependency bắc cầu cần thiết.

Không thể dùng launcher của jlink để chạy tùy ý một class chỉ nằm trên classpath hoặc một JAR chưa được đưa vào image. jlink làm việc với module graph.

## 3. Phân biệt launcher của jlink với lệnh java

Một lệnh java thông thường cần biết module và main class:

~~~bash
java --module-path mods \
    --module com.example.cli/com.example.cli.Main
~~~

Nếu ứng dụng chạy từ runtime image, có thể gọi java nằm bên trong image:

~~~bash
image/bin/java \
    --module com.example.cli/com.example.cli.Main
~~~

Tùy chọn --launcher tạo một lệnh đã cấu hình sẵn cho module và main class:

~~~bash
image/bin/greeter
~~~

Về mặt sử dụng, launcher giống một shortcut có thể thực thi. Nó không biên dịch source, không thay thế javac, không tự đóng gói dependency và không phải một installer. Việc liên kết runtime và module đã được thực hiện khi chạy jlink.

Launcher thường thực hiện các công việc sau:

1. Xác định thư mục runtime image chứa chính nó.
2. Gọi Java runtime nằm trong image.
3. Chỉ định module và main class đã cấu hình.
4. Chuyển các đối số ứng dụng cho phương thức main.

Do launcher gắn với image, có thể đổi tên thư mục image hoặc chuyển toàn bộ image sang vị trí khác trên cùng nền tảng mà không cần cài JDK riêng. Khi di chuyển, giữ nguyên cấu trúc thư mục bên trong image.

## 4. Đối số ứng dụng và tùy chọn JVM

Các đối số đặt sau launcher được chuyển cho phương thức main dưới dạng String[] args.

Ví dụ:

~~~bash
image/bin/greeter production --port 8080
~~~

Trong Java:

~~~java
public static void main(String[] args) {
    // args[0] = "production"
    // args[1] = "--port"
    // args[2] = "8080"
}
~~~

Điểm cần chú ý: các đối số sau tên launcher là đối số của ứng dụng. Chúng không tự động trở thành tùy chọn JVM như -Xmx, -D hoặc -agentlib.

Nếu cần thiết lập heap hoặc system property, có thể gọi trực tiếp Java runtime trong image:

~~~bash
image/bin/java \
    -Xms128m \
    -Xmx512m \
    -Dapp.profile=production \
    --module com.example.cli/com.example.cli.Main \
    production --port 8080
~~~

Cách này cho phép truyền tùy chọn JVM trước module và đối số ứng dụng sau main class.

Một số launcher script được jlink tạo ra sử dụng biến môi trường JLINK_VM_OPTIONS để nhận tùy chọn JVM. Vì nội dung script có thể phụ thuộc JDK và nền tảng, hãy kiểm tra script được tạo trên môi trường build trước khi dựa vào biến này trong quy trình triển khai. Cách rõ ràng nhất khi cần điều khiển JVM trực tiếp là gọi image/bin/java với các tùy chọn mong muốn.

Không nhầm tùy chọn --launcher của jlink với các tùy chọn --arguments và --java-options của jpackage. jpackage có cơ chế cấu hình đối số mặc định và JVM options cho application launcher; jlink tập trung vào việc liên kết module và tạo lệnh chạy module/main class.

## 5. Điều kiện để tạo launcher

Để tạo launcher trong image, cần chuẩn bị:

1. JDK có công cụ jlink.
2. Module ứng dụng đã được biên dịch.
3. Module descriptor hợp lệ.
4. Các dependency module cần thiết có trên module path hoặc trong JDK image.
5. Main class có entry point phù hợp.
6. Tên module và main class chính xác.
7. Thư mục output image chưa tồn tại hoặc đã được dọn theo quy trình build.

Một module descriptor đơn giản:

~~~java
module com.example.cli {
}
~~~

Main class:

~~~java
package com.example.cli;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Image launcher ready.");
    }
}
~~~

Nếu module sử dụng các module khác, khai báo dependency trong module-info.java:

~~~java
module com.example.cli {
    requires java.logging;
}
~~~

jlink sẽ đọc module graph để đưa module gốc và các dependency bắc cầu vào image.

### Dependency phải là module mà jlink có thể liên kết

Module path của jlink có thể chứa modular JAR, JMOD file hoặc exploded module directory. Một JAR chỉ nằm trên classpath không đủ để jlink liên kết nó vào runtime image.

Automatic module cũng không phải lựa chọn để đưa trực tiếp vào image bằng jlink. Với thư viện legacy, cần chuyển sang module có descriptor tường minh hoặc thiết kế lại cách đóng gói dependency trước khi tạo image.

Nếu ứng dụng vẫn cần một thư viện ngoài image, cần xử lý dependency đó bằng một cơ chế triển khai phù hợp, chẳng hạn module path/classpath bên ngoài và một wrapper launcher do dự án quản lý. Launcher mặc định của jlink được thiết kế để khởi chạy module đã liên kết trong image.

## 6. Quy trình tạo image có launcher

Quy trình tổng quát:

~~~text
module-info.java + source files
             |
             v
          javac
             |
             v
       exploded module
             |
             v
           jlink
       /     |      \
      /      |       \
runtime   module    launcher
image     graph     command
      \      |       /
       \     |      /
             v
       image/bin/app
             |
             v
       application main
~~~

Các bước:

1. Viết module descriptor và mã nguồn.
2. Biên dịch module bằng javac.
3. Kiểm tra module và dependency.
4. Chọn module gốc cho image bằng --add-modules.
5. Chỉ định module path để jlink tìm các module.
6. Tạo launcher bằng --launcher.
7. Chỉ định thư mục image bằng --output.
8. Chạy thử launcher từ image vừa tạo.
9. Kiểm tra các module và tài nguyên có trong image.
10. Đóng gói toàn bộ image để triển khai trên nền tảng tương ứng.

Không cần đóng gói một JDK đầy đủ cùng ứng dụng. Runtime image do jlink tạo đã chứa runtime cần thiết cho module graph đã liên kết.

## 7. Ví dụ thực hành hoàn chỉnh với Java 17+

Ví dụ tạo module com.example.cli và launcher tên greeter. Chương trình in một dòng cố định và hiển thị các đối số được truyền từ launcher.

Cấu trúc dự án:

~~~text
jlink-launcher-demo/
└── src/
    └── com.example.cli/
        ├── module-info.java
        └── com/
            └── example/
                └── cli/
                    └── Main.java
~~~

### Bước 1: tạo module descriptor

Tạo tệp src/com.example.cli/module-info.java:

~~~java
module com.example.cli {
}
~~~

Module không cần dependency ngoài java.base trong ví dụ này.

### Bước 2: tạo main class

Tạo tệp src/com.example.cli/com/example/cli/Main.java:

~~~java
package com.example.cli;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Image launcher ready.");

        if (args.length > 0) {
            System.out.println("args=" + String.join("|", args));
        }
    }
}
~~~

Main class có phương thức public static void main(String[] args), là entry point mà launcher sẽ gọi.

### Bước 3: biên dịch module

Từ thư mục gốc jlink-launcher-demo, tạo output directory:

~~~bash
mkdir -p mods
~~~

Biên dịch bằng Java 17:

~~~bash
javac --release 17 \
    --module-source-path src \
    -d mods \
    -m com.example.cli
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path "mods" | Out-Null
javac --release 17 --module-source-path "src" -d "mods" -m com.example.cli
~~~

Kết quả:

~~~text
mods/
└── com.example.cli/
    ├── module-info.class
    └── com/
        └── example/
            └── cli/
                └── Main.class
~~~

Đây là exploded module. Thư mục com.example.cli chứa module-info.class và các class của module.

### Bước 4: tạo runtime image và launcher trên Linux/macOS

Chạy từ thư mục gốc dự án:

~~~bash
jlink \
    --module-path "mods:$JAVA_HOME/jmods" \
    --add-modules com.example.cli \
    --launcher greeter=com.example.cli/com.example.cli.Main \
    --output image
~~~

Trong lệnh:

- **--module-path** cho jlink biết nơi tìm exploded module và JDK modules.
- **--add-modules com.example.cli** chọn module ứng dụng làm root module.
- **--launcher greeter=...** tạo lệnh greeter cho main class.
- **--output image** tạo runtime image trong thư mục image.

### Bước 5: tạo runtime image trên Windows PowerShell

Dấu phân cách các phần tử module path trên Windows là dấu chấm phẩy:

~~~powershell
jlink --module-path "mods;$env:JAVA_HOME\jmods" --add-modules com.example.cli --launcher greeter=com.example.cli/com.example.cli.Main --output image
~~~

Nếu JAVA_HOME chưa được thiết lập, có thể truyền đường dẫn tuyệt đối tới thư mục jmods của JDK đang dùng.

Không dùng dấu hai chấm làm dấu phân cách module path trên Windows; dấu phân cách phụ thuộc hệ điều hành.

### Bước 6: kiểm tra launcher và image

Sau khi jlink hoàn tất, cấu trúc có dạng:

~~~text
image/
├── bin/
│   ├── java
│   ├── keytool
│   └── greeter
├── conf/
├── legal/
├── lib/
└── release
~~~

Trên Windows, launcher tùy chỉnh thường có tên greeter.bat trong image\bin.

Có thể liệt kê module trong image:

~~~bash
image/bin/java --list-modules
~~~

Trên Windows:

~~~powershell
.\image\bin\java.exe --list-modules
~~~

Danh sách hiển thị các module đã được liên kết cùng phiên bản runtime. Tập module thực tế phụ thuộc JDK và dependency của ứng dụng.

### Bước 7: chạy launcher

Trên Linux/macOS:

~~~bash
./image/bin/greeter
~~~

Trên Windows PowerShell:

~~~powershell
.\image\bin\greeter.bat
~~~

Output:

~~~text
Image launcher ready.
~~~

Truyền đối số:

~~~bash
./image/bin/greeter production 8080
~~~

Output:

~~~text
Image launcher ready.
args=production|8080
~~~

Đây là output của ứng dụng mẫu. Không cần gọi java từ PATH; launcher sử dụng runtime nằm trong image.

### Bước 8: chạy trực tiếp bằng java trong image

Có thể bỏ qua launcher và gọi module/main class:

~~~bash
image/bin/java \
    --module com.example.cli/com.example.cli.Main \
    production 8080
~~~

Output:

~~~text
Image launcher ready.
args=production|8080
~~~

Hai cách chạy sử dụng cùng module và runtime. Lệnh java hữu ích khi cần truyền JVM options; launcher tiện lợi khi muốn cung cấp một lệnh cố định cho người dùng.

## 8. Nhiều launcher trong cùng một image

Một runtime image có thể chứa nhiều launcher cho nhiều entry point trong các module đã liên kết.

Ví dụ:

~~~bash
jlink \
    --module-path mods \
    --add-modules com.example.cli,com.example.admin \
    --launcher greeter=com.example.cli/com.example.cli.Main \
    --launcher admin=com.example.admin/com.example.admin.Main \
    --output image
~~~

Image sẽ có hai lệnh ứng dụng:

~~~text
image/
└── bin/
    ├── java
    ├── greeter
    └── admin
~~~

Trên Windows, các lệnh tương ứng được tạo dưới dạng batch launcher theo nền tảng.

Mỗi launcher gắn với một module và main class cụ thể. Tất cả launcher dùng chung runtime image, vì vậy không cần tạo hai bản runtime riêng nếu hai ứng dụng có thể dùng chung module graph.

Trước khi tạo nhiều launcher, cần bảo đảm mọi module mà các launcher tham chiếu đều được đưa vào image. Tùy chọn --add-modules có thể nhận nhiều tên module phân tách bằng dấu phẩy.

## 9. ServiceLoader và --bind-services

Nếu ứng dụng dùng ServiceLoader, module ứng dụng có thể khai báo uses và module provider khai báo provides.

Ví dụ consumer:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
~~~

Ví dụ provider:

~~~java
module com.example.provider {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.provider.DefaultGreetingService;
}
~~~

Khi tạo image, có thể thêm provider module tường minh bằng --add-modules hoặc dùng tùy chọn:

~~~bash
--bind-services
~~~

--bind-services yêu cầu jlink liên kết các module provider của service và dependency tương ứng trong quá trình service binding.

Ví dụ:

~~~bash
jlink \
    --module-path mods \
    --add-modules com.example.app \
    --bind-services \
    --launcher app=com.example.app/com.example.app.Main \
    --output image
~~~

Service provider chỉ được đưa vào image khi module resolution và service binding xác định được provider phù hợp. Nếu ứng dụng cần một provider cụ thể, có thể thêm provider module rõ ràng để build dễ dự đoán hơn.

Dùng --bind-services có thể làm image lớn hơn vì nhiều provider module được liên kết. Kiểm tra danh sách module sau khi build để xác nhận tập module thực tế.

Có thể tìm provider phù hợp cho một service bằng:

~~~bash
jlink --suggest-providers com.example.spi.GreetingService
~~~

Lệnh này gợi ý module provider trên module path cho service type được chỉ định.

## 10. Tùy chọn tối ưu runtime image

Ngoài launcher, jlink có các tùy chọn giúp điều chỉnh nội dung image:

| Tùy chọn | Tác dụng |
|---|---|
| --strip-debug | Loại bỏ thông tin debug khỏi image |
| --no-header-files | Không đưa header file vào image |
| --no-man-pages | Không đưa man page vào image |
| --bind-services | Liên kết service provider và dependency |
| --limit-modules | Giới hạn tập module có thể quan sát trong quá trình resolution |
| --save-opts | Lưu tùy chọn build vào file |
| --list-plugins | Liệt kê plugin mà jlink hỗ trợ |

Ví dụ image gọn hơn:

~~~bash
jlink \
    --module-path mods \
    --add-modules com.example.cli \
    --launcher greeter=com.example.cli/com.example.cli.Main \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --output image
~~~

Không nên bật hoặc tắt plugin chỉ để giảm kích thước mà chưa kiểm thử. Một số tài nguyên hoặc thông tin có thể cần cho việc debug, chẩn đoán, locale hoặc triển khai.

Tùy chọn compression thay đổi theo phiên bản JDK. Hãy chạy jlink --list-plugins và đọc trợ giúp của đúng JDK đang dùng trước khi đặt --compress. Không sao chép nguyên giá trị compression từ một phiên bản JDK khác mà chưa xác nhận.

## 11. jlink launcher và jpackage launcher

Hai công cụ có mục tiêu khác nhau:

| Công cụ | Kết quả chính | Launcher |
|---|---|---|
| jlink | Runtime image tùy chỉnh từ module graph | Tạo lệnh module/main bằng --launcher |
| jpackage | Application image hoặc gói cài đặt nền tảng | Tạo launcher ứng dụng có thêm cấu hình và tích hợp hệ điều hành |

jlink tập trung vào runtime image. Launcher của nó là cách chạy một module và main class đã liên kết.

jpackage đóng gói ứng dụng để phân phối. Nó có thể tạo application image, gói EXE/MSI trên Windows, DEB/RPM trên Linux hoặc PKG/DMG trên macOS tùy nền tảng. Nếu không truyền runtime image có sẵn, jpackage có thể gọi jlink để tạo runtime.

Ví dụ đóng gói ứng dụng modular bằng jpackage:

~~~bash
jpackage \
    --type app-image \
    --name Greeter \
    --module-path mlib \
    --module com.example.cli/com.example.cli.Main
~~~

jpackage có các tùy chọn riêng như --arguments, --java-options và --add-launcher để cấu hình launcher của application image. Các tùy chọn này không phải cú pháp của jlink.

Nếu chỉ cần một runtime image có lệnh khởi chạy module, jlink là đủ. Nếu cần installer, icon, shortcut, application bundle hoặc cấu hình launcher cho người dùng cuối, hãy xem xét jpackage.

## 12. Giới hạn và lưu ý khi triển khai

### Image gắn với nền tảng

Runtime image chứa thư viện native và runtime được tạo cho hệ điều hành, kiến trúc và JDK tương ứng. Không tạo image trên Linux rồi mặc định có thể chạy trực tiếp trên Windows hoặc macOS.

Build và kiểm thử image riêng cho từng nền tảng đích. Cần tính tới kiến trúc CPU, phiên bản hệ điều hành, thư viện native và yêu cầu phân phối của môi trường chạy.

### Không tự động cập nhật

Custom runtime image không có cơ chế tự cập nhật JDK như một số cài đặt Java phổ thông. Đội phát triển phải xây dựng và phân phối lại image khi cần cập nhật JDK, bản vá bảo mật hoặc dependency runtime.

Hãy xác định quy trình rebuild, kiểm thử và phát hành image cho từng nền tảng. Không xem image đã tạo một lần là runtime được bảo trì tự động.

### Không thể link JAR classpath tùy ý

jlink cần module mà nó có thể phân giải. Dependency chỉ có trên classpath hoặc automatic module không thể được xử lý như explicit named module trong runtime image.

Với thư viện cũ, kiểm tra module descriptor, Automatic-Module-Name và dependency. Có thể cần nâng cấp thư viện, tạo module descriptor phù hợp hoặc dùng một cách đóng gói khác.

### Main class không tồn tại hoặc sai tên

Nếu tên module hoặc main class trong --launcher sai, launcher sẽ không khởi chạy đúng ứng dụng. Kiểm tra module name, package, class name và file class đã được biên dịch.

### Thiếu dependency

Nếu module ứng dụng dùng một module nhưng descriptor không khai báo đúng, javac hoặc jlink có thể báo lỗi resolution. Kiểm tra requires, module path và module graph.

### Tạo lại image trong thư mục đã tồn tại

jlink yêu cầu output path phù hợp cho một image mới. Trong build pipeline, hãy quản lý bước clean output rõ ràng. Không ghi đè image đang được dùng bởi tiến trình khác.

### Launcher không nhận JVM option như mong đợi

Các đối số sau launcher được chuyển cho ứng dụng. Nếu muốn thay đổi heap, system property hoặc agent, gọi image/bin/java với JVM options hoặc dùng wrapper script được quản lý rõ ràng.

### Image không chứa công cụ debug

Image tối giản có thể không có jcmd, jfr hoặc các công cụ chẩn đoán khác nếu các module tương ứng không được liên kết. Nếu cần điều tra production, quyết định trước có cần thêm module chẩn đoán vào image hay dùng một bộ công cụ ngoài.

## 13. Kiểm tra image sau khi tạo

Sau khi jlink hoàn tất, nên kiểm tra:

1. Image directory đã được tạo và có cấu trúc hợp lệ.
2. Lệnh launcher xuất hiện trong image/bin.
3. Runtime trong image có đúng phiên bản dự kiến.
4. Danh sách module có module ứng dụng và dependency cần thiết.
5. Launcher chạy đúng main class.
6. Đối số được chuyển chính xác vào String[] args.
7. Các tài nguyên, locale và service provider cần thiết có mặt.
8. Image chạy được trên hệ điều hành và kiến trúc đích.
9. Kích thước image đáp ứng yêu cầu phân phối.
10. Quy trình cập nhật image đã được xác định.

Các lệnh kiểm tra:

~~~bash
image/bin/java --version
image/bin/java --list-modules
image/bin/java --describe-module com.example.cli
~~~

Trên Windows:

~~~powershell
.\image\bin\java.exe --version
.\image\bin\java.exe --list-modules
.\image\bin\java.exe --describe-module com.example.cli
~~~

Có thể kiểm tra image bằng cách chạy trực tiếp Java trong image, sau đó chạy launcher. Nếu hai cách cho kết quả khác nhau, kiểm tra script launcher, module/main class và các đối số truyền vào.

## 14. Quy trình build và phát hành khuyến nghị

Một quy trình dễ tái lập:

1. Build module ứng dụng bằng đúng JDK mục tiêu.
2. Chạy unit test và kiểm tra module descriptor.
3. Xác định root module và các dependency bắt buộc.
4. Kiểm tra service provider nếu ứng dụng dùng ServiceLoader.
5. Chạy jlink với module path, add-modules và launcher rõ ràng.
6. Thêm các plugin tối ưu sau khi đã xác định yêu cầu vận hành.
7. Kiểm tra danh sách module và file launcher.
8. Chạy integration test thông qua launcher.
9. Chạy test trên hệ điều hành và kiến trúc đích.
10. Đóng gói toàn bộ runtime image thành artifact phân phối.
11. Ghi nhận phiên bản JDK, module graph và tùy chọn jlink đã dùng.
12. Lập lịch rebuild và phát hành image khi JDK hoặc dependency cần cập nhật.

Đối với ứng dụng nhiều nền tảng, tạo một image cho từng nền tảng. Đối với ứng dụng có nhiều entry point, cân nhắc nhiều launcher trong cùng image nếu chúng chia sẻ module graph và runtime.

## 15. Tóm tắt các lệnh cần nhớ

~~~bash
# Compile module
javac --release 17 --module-source-path src -d mods -m com.example.cli

# Create image and launcher
jlink \
    --module-path mods \
    --add-modules com.example.cli \
    --launcher greeter=com.example.cli/com.example.cli.Main \
    --output image

# Inspect modules
image/bin/java --list-modules

# Run generated launcher
image/bin/greeter

# Run with explicit JVM options
image/bin/java -Xmx512m \
    --module com.example.cli/com.example.cli.Main
~~~

Launcher trong image là lệnh tiện dụng để chạy một module đã được liên kết cùng runtime tùy chỉnh. Khi module graph, main class, dependency và nền tảng được xác định chính xác, jlink tạo ra một image có thể triển khai mà không yêu cầu người dùng cài một JDK riêng.

## Tài liệu tham khảo

- [The jlink Command — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [The java Command — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [The jpackage Command — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Creating Runtime and Application Images with jlink — dev.java](https://dev.java/learn/jlink/)
