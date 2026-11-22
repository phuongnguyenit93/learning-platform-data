# Mục tiêu phân phối ứng dụng Java kèm runtime cần thiết

## 1. Tại sao phải đóng gói cả runtime?

Khi phát triển ứng dụng Java, lệnh quen thuộc có thể là:

~~~bash
java -jar my-app.jar
~~~

Nhưng lệnh đó **phụ thuộc máy người dùng đã cài Java** hoặc có một runtime tương thích. Máy đích còn phải có đúng phiên bản, đúng kiến trúc, thư viện hệ thống và cấu hình môi trường. Đối với ứng dụng desktop hoặc công cụ cài đặt cho người dùng cuối, yêu cầu tự cài và cấu hình Java trước thường làm tăng chi phí hỗ trợ.

Mục tiêu của **phân phối ứng dụng kèm runtime cần thiết** là tạo một bản phát hành mà trong đó **ứng dụng và Java runtime đủ để chạy ứng dụng** được đóng gói chung. Người dùng mở **launcher** hoặc cài một **native installer** như ứng dụng thông thường; họ không phải tự cấu hình `JAVA_HOME`, `PATH` hoặc cài JDK/JRE riêng để chạy đúng bản đó.

Ví dụ mô hình:

~~~text
Máy lập trình / CI                                  Máy người dùng
-----------------                                 -------------------
Mã nguồn Java                                      Bản phân phối ứng dụng
     |                                                   |
javac, jar / build tool                                  |
     |                                                   v
Ứng dụng JAR hoặc module                   +---------------------------+
     |                                     | Launcher theo nền tảng    |
     +--> Phân tích modules bằng jdeps      | App JAR / resources       |
     |                                     | Runtime Java được kèm    |
     +--> jlink: tạo runtime image -------->| Native libraries cần thiết|
     |                                     +---------------------------+
     +--> jpackage: tạo app image                       |
                / installer                             v
                                                   Chạy ứng dụng
                                              không cần Java hệ thống
~~~

**Trọng tâm:** “Kèm runtime” không có nghĩa đóng gói toàn bộ JDK phát triển. Một bản phân phối tốt thường chứa **runtime image** gồm các module Java cần thiết, launchers và các file ứng dụng; không nhất thiết chứa `javac`, mã nguồn JDK, Javadoc hay công cụ phát triển.

### Tình trạng tính năng hiện hành

- `jlink` dùng để tạo **custom runtime image** từ các module của JDK (cùng những module tương thích).
- `jpackage` tạo **application image** hoặc **installer** có chứa launcher, ứng dụng và runtime.
- `jpackage` từng được giới thiệu ở Java 14 dưới dạng incubating tool (JEP 343), và trở thành **công cụ chính thức từ Java 16** (JEP 392). Bản chính thức dùng module `jdk.jpackage`, không phải module incubating lịch sử.
- Các cách làm trong bài hoạt động với **JDK 17+** trên các nền tảng được hỗ trợ, không sử dụng cú pháp incubating đã lỗi thời.

## 2. Các mục tiêu phân phối phải được đáp ứng cùng lúc

Không chỉ hỏi “có chạy trên máy tôi không”, hãy xác định **hợp đồng của bản phát hành**:

| Mục tiêu | Ý nghĩa thực tế | Cách xác nhận |
| --- | --- | --- |
| **Không cần cài Java riêng** | Launcher chạy bằng runtime trong bản phân phối | Kiểm thử trên máy sạch không có Java hệ thống |
| **Kiểm soát phiên bản runtime** | Ứng dụng chạy với bản JDK/JRE tương ứng đã đóng gói | Kiểm tra runtime version và danh sách modules trong image |
| **Đủ phụ thuộc** | Có JDK modules, JAR, resource và native libraries cần dùng | Chạy toàn bộ luồng nghiệp vụ, không chỉ màn hình khởi động |
| **Phù hợp hệ điều hành / CPU** | Image và launcher đúng Windows, macOS hoặc Linux cùng kiến trúc | Build và test trên nền tảng đích |
| **Dễ cài và mở ứng dụng** | Có launcher/icon/installer nếu cần | Kiểm thử thao tác mở, cài, gỡ |
| **Có thể cập nhật bảo mật** | Có quy trình rebuild khi JDK hoặc thư viện có bản vá | Quản lý phiên bản, SBOM và vòng đời bản phát hành |
| **Có thể chẩn đoán lỗi** | Biết app/runtime version và ghi log theo quy định | Smoke test + kiểm tra log/exception khi chạy |
| **Không phình vô ích** | Bớt module và file không cần, không gây thiếu chức năng | So dung lượng với kiểm thử tích hợp thực tế |

**Cân bằng quan trọng:** Runtime ít module hơn có thể giảm kích thước và bề mặt tấn công, nhưng **thiếu một module sử dụng động** thì chương trình có thể chạy qua smoke test rồi thất bại ở một tính năng ít dùng. Đừng đánh đổi tính đúng đắn lấy vài megabyte mà chưa kiểm thử đầy đủ.

## 3. Phân biệt bốn sản phẩm dễ nhầm

### 3.1. JAR chỉ chứa ứng dụng

~~~text
my-app.jar
~~~

JAR chứa bytecode, resource và metadata theo cách đóng gói. Một executable JAR có `Main-Class` trong manifest và có thể chạy qua `java -jar`, nhưng **không tự chứa Java runtime**.

Nếu chương trình phụ thuộc thư viện bên thứ ba, cách tạo JAR còn ảnh hưởng khả năng nạp dependency: có thể dùng classpath gồm nhiều JAR, fat/uber JAR do build tool tạo, hoặc cơ chế launcher hỗ trợ. Đừng nghĩ mọi `jar --create` đều tự thu thập dependency.

### 3.2. Runtime image do `jlink` tạo

~~~text
custom-runtime/
  bin/
  conf/
  legal/
  lib/
  release
  ...
~~~

Đây là **Java runtime** đã được link từ một tập module. Nó có thể chạy các lớp/JAR nếu đủ module, nhưng **chưa tự là bản phân phối ứng dụng có native launcher riêng**. Thư mục thực tế có thể khác theo JDK và nền tảng.

### 3.3. Application image do `jpackage` tạo

~~~text
PackagedHello/
  PackagedHello.exe           (ví dụ trên Windows)
  app/
    packaged-hello.jar
    ...
  runtime/
    lib/
      modules
    ...
~~~

Đây là **sơ đồ dạng thư mục mang tính minh họa** của application image Windows. `jpackage` cung cấp launcher và sắp xếp ứng dụng, runtime cùng một đơn vị phân phối. Tên thư mục và các file chi tiết có thể thay đổi theo JDK/nền tảng; không viết automation dựa vào mọi đường dẫn nội bộ mà chưa kiểm tra image cụ thể.

**App image** có thể được kiểm thử trực tiếp. Đối với người dùng cuối, có thể phân phối theo chính sách phù hợp hoặc dùng nó làm đầu vào tạo installer.

### 3.4. Installer theo nền tảng

Installer sử dụng hình thức quen thuộc của hệ điều hành, ví dụ:
- Windows: `exe` hoặc `msi`.
- macOS: `pkg` hoặc `dmg`.
- Linux: `deb` hoặc `rpm`.

Installer thường có chức năng cài đặt, cấu hình shortcut và gỡ cài đặt tùy định dạng, tùy chọn và công cụ hỗ trợ. **Installer không phải một “runtime Java duy nhất chạy mọi nơi”**: mỗi nền tảng cần tạo đúng định dạng và runtime thích hợp.

### Bảng tóm tắt

| Sản phẩm | Có app code? | Có Java runtime? | Dành cho người dùng cuối? |
| --- | --- | --- | --- |
| JAR thông thường | Có | **Không** | Có thể, nhưng người dùng cần Java phù hợp |
| `jlink` runtime image | Không nhất thiết | **Có** | Là một thành phần, chưa đủ nếu chưa có app |
| `jpackage --type app-image` | Có | **Có** | Có thể chạy từ image trên đúng nền tảng |
| `jpackage` native installer | Có | **Có** (theo cấu hình thường dùng) | Có: cài đặt ứng dụng theo cách của OS |

## 4. `jpackage` tự tạo runtime hay dùng runtime do bạn cung cấp?

`jpackage` nhận **JAR hoặc module của ứng dụng** và tạo application image. Bạn có hai lựa chọn chính:

### Cách A — Để `jpackage` tạo runtime tự động

~~~bash
jpackage --type app-image --name DemoApp --input input --main-jar demo.jar --main-class Main --dest release
~~~

Đây là **lệnh mẫu**: yêu cầu đã có `input/demo.jar`, lớp `Main` và thư mục output phù hợp. Nếu **không có `--runtime-image`**, `jpackage` dùng cơ chế link runtime bằng `jlink`. Với ứng dụng non-modular chạy qua classpath, tập module mặc định có thể **rộng hơn** nhu cầu thực tế. Nếu muốn thêm module hay điều chỉnh link, dùng `--add-modules`, `--module-path` hoặc `--jlink-options` khi thích hợp.

**Ưu điểm:** ít bước, dễ có bản chạy đầu tiên.

**Hạn chế:** runtime tự động không nhất thiết nhỏ nhất hoặc chứa tất cả thành phần động của ứng dụng; vẫn cần kiểm thử.

### Cách B — Tạo runtime riêng bằng `jlink`, rồi truyền qua `--runtime-image`

~~~bash
jlink --add-modules java.base,java.logging --output custom-runtime
jpackage --type app-image --name DemoApp --input input --main-jar demo.jar --main-class Main --runtime-image custom-runtime --dest release
~~~

Đây là **lệnh mẫu** khi biết ứng dụng chỉ cần những module trên và `input/demo.jar` có sẵn. `jlink` tạo một runtime có tập module chủ động chọn; `jpackage` **đưa runtime đó vào image ứng dụng**.

**Ưu điểm:** kiểm soát danh sách module, chính sách runtime và kích thước.

**Hạn chế:** bạn chịu trách nhiệm bảo đảm đủ module, service providers, thư viện native và compatibility.

**Không nhầm:** `--runtime-image` là **đường dẫn tới một runtime image đã tạo**, không phải đường dẫn thẳng tới JDK installation bất kỳ hoặc một file `.jar`. Với runtime tạo từ `jlink`, dùng thư mục **output** của `jlink`.

## 5. Xác định “runtime cần thiết” bằng `jdeps` và hiểu giới hạn

`jdeps` là công cụ phân tích phụ thuộc trong bytecode. Nó có thể giúp tìm **JDK modules được tham chiếu trực tiếp** từ ứng dụng/JAR.

Ví dụ ứng dụng sử dụng `java.util.logging.Logger` sẽ có dependency tới module `java.logging`. Với một JAR đơn giản, lệnh:

~~~bash
jdeps --print-module-deps input/packaged-hello.jar
~~~

trả về trong ví dụ đã kiểm chứng:

~~~text
java.base,java.logging
~~~

Nhờ đó có thể tạo runtime bằng:

~~~bash
jlink --add-modules java.base,java.logging --strip-debug --no-man-pages --no-header-files --output runtime
~~~

Các tùy chọn:
- `--add-modules`: tập module gốc cần đưa vào image; `jlink` còn giải quyết module dependencies bắt buộc.
- `--strip-debug`: giảm thông tin debug trong image theo khả năng công cụ.
- `--no-man-pages`: bỏ man pages.
- `--no-header-files`: bỏ các header files dành cho phát triển.
- `--output runtime`: đường dẫn thư mục runtime image mới (không nên là thư mục đã chứa dữ liệu tùy ý).

### 5.1. `jdeps` không thấy hết mọi đường sử dụng động

Phân tích tĩnh **có giới hạn** nếu ứng dụng sử dụng:
- Reflection như `Class.forName("...")` với tên kiểu tạo lúc runtime.
- `ServiceLoader` hoặc cơ chế plugin tìm implementation dựa trên service provider.
- JNI/native code, thư viện ngoài JVM và một số phương thức nạp module động.
- Framework tạo proxy hoặc load class theo cấu hình, manifest hay tên chuỗi.
- Tính năng phụ thuộc charset, security provider, locale hoặc database driver ít được gọi.

Do đó `jdeps` cung cấp **gợi ý bắt đầu**, không phải bằng chứng runtime đã đầy đủ. Với service providers trong module layer, cân nhắc `jlink --bind-services` khi phù hợp, và thêm các module phụ thuộc cần thiết. Chỉ chọn những provider thật sự có ý nghĩa với sản phẩm để không kéo quá nhiều module.

### 5.2. Phân biệt JDK modules và thư viện bên thứ ba

`java.base` hay `java.logging` là module nền tảng Java. Nhưng một JAR ứng dụng có thể còn phụ thuộc `jackson`, JDBC driver, logging backend hoặc các thư viện riêng.

`jlink` **không tự đóng tất cả JAR bên thứ ba vào application payload**. Khi dùng `jpackage --input input` cho ứng dụng non-modular, phải đưa đúng các JAR/resources cần chạy vào `input` và bảo đảm cơ chế classpath/manifest/launcher phù hợp.

Nếu ứng dụng được cấu hình là **modular**, tập module và cách phân phối khác; xem mục 10. Với modular JAR đặt trên module path, các phụ thuộc module phải được phân giải nhất quán.

## 6. Chương trình Java chạy được: tạo ứng dụng để đóng gói

Ta dùng một chương trình nhỏ có dependency thật tới `java.logging` để `jdeps` thấy hai module `java.base` và `java.logging`.

Lưu nội dung sau vào tệp **`PackagedHello.java`**:

~~~java
import java.util.logging.Logger;

public class PackagedHello {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(PackagedHello.class.getName());
        System.out.println("App started");
        System.out.println("Logger: " + logger.getName());
        System.out.println("Arguments: " + String.join(",", args));
    }
}
~~~

Mã này dùng API chính thức từ nhiều phiên bản Java và chạy được với **Java 17+**. Nó **không** in version của runtime để stdout bài học luôn như nhau trên các JDK tương thích.

### 6.1. Biên dịch và tạo JAR

Chạy các lệnh trong **PowerShell trên Windows**, từ thư mục chứa `PackagedHello.java`, với JDK 17+ đã cài trên **máy build**:

~~~powershell
New-Item -ItemType Directory -Force -Path classes,input,release | Out-Null

javac -encoding UTF-8 --release 17 -d classes PackagedHello.java

jar --create --file input/packaged-hello.jar --main-class PackagedHello -C classes .

java -jar input/packaged-hello.jar course
~~~

**Stdout của lần chạy thử đã kiểm chứng:**

~~~text
App started
Logger: PackagedHello
Arguments: course
~~~

`jar --create` với `--main-class PackagedHello` ghi Main-Class vào manifest để JAR có thể chạy qua `java -jar`. Tùy chọn `-C classes .` đưa các file đã biên dịch vào JAR. Với ứng dụng lớn, dùng build tool như Maven/Gradle để dựng artifact và quản lý dependencies thay vì sao chép thủ công.

### 6.2. Kiểm tra dependency Java modules

~~~powershell
jdeps --print-module-deps input/packaged-hello.jar
~~~

**Output đã kiểm chứng:**

~~~text
java.base,java.logging
~~~

`java.base` cung cấp core API, `java.logging` cung cấp `Logger`. Không tự rút kết luận rằng mọi ứng dụng khác cũng chỉ cần hai module này. Đầu ra của `jdeps` phải được xác nhận bằng build thực tế và bài kiểm thử chức năng.

### 6.3. Tạo runtime rút gọn

~~~powershell
jlink --add-modules java.base,java.logging --strip-debug --no-man-pages --no-header-files --output runtime
~~~

Sau lệnh này, thư mục `runtime` chứa một Java runtime image. Một phép kiểm tra đơn giản trên Windows:

~~~powershell
Test-Path .\runtime\lib\modules
.\runtime\bin\java.exe --list-modules
~~~

Trong lần chạy thực tế trên môi trường kiểm chứng, lệnh `--list-modules` có `java.base@24.0.2` và `java.logging@24.0.2`, vì **JDK đang sử dụng để tạo image là JDK 24**. Nếu build bằng JDK 17 hay 21 thì **version trong runtime tương ứng sẽ khác**. Hai module được chọn bằng `--add-modules`, không phải hai artifact riêng của ứng dụng.

**Điểm quan trọng:** `javac --release 17` chỉ đặt mức tương thích **ngôn ngữ/API và bytecode Java 17** cho chương trình. Nó **không hạ phiên bản các module trong runtime** mà `jlink`/`jpackage` tạo ra từ JDK đang dùng. Muốn phân phối runtime của một phiên bản JDK cụ thể, hãy dùng toolchain và module tương ứng của bản JDK đó.

### 6.4. Tạo application image với runtime vừa xây

~~~powershell
jpackage --type app-image --name PackagedHello --input input --main-jar packaged-hello.jar --main-class PackagedHello --runtime-image runtime --win-console --dest release
~~~

Giải thích từng phần:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--type app-image` | Tạo **application image** để kiểm thử, chưa tạo installer |
| `--name PackagedHello` | Tên ứng dụng và launcher |
| `--input input` | Thư mục chứa JAR và resource cần đưa vào app |
| `--main-jar packaged-hello.jar` | JAR chính, là đường dẫn tương đối **bên trong `input`** |
| `--main-class PackagedHello` | Lớp chứa `public static void main(String[] args)` |
| `--runtime-image runtime` | Runtime tạo bởi `jlink` ở bước trước |
| `--win-console` | Tạo launcher dạng console trên **Windows** để nhìn stdout |
| `--dest release` | Thư mục đầu ra; dưới đó sẽ có application image |

`--win-console` là tùy chọn **dành cho Windows**, không mang sang macOS/Linux. Đối với ứng dụng GUI, không nhất thiết bật console; với ví dụ CLI cần nhìn stdout, bật nó giúp kiểm thử.

**Không dùng đồng thời `--module` và `--main-jar`**: một tùy chọn mô tả **modular main application**, tùy chọn kia mô tả **non-modular main JAR**.

### 6.5. Chạy launcher đã đóng gói

~~~powershell
.\release\PackagedHello\PackagedHello.exe course

Test-Path .\release\PackagedHello\runtime\lib\modules
~~~

**Stdout launcher đã kiểm chứng:**

~~~text
App started
Logger: PackagedHello
Arguments: course
~~~

**Kết quả `Test-Path` trong lần chạy thử:**

~~~text
True
~~~

Điều đó kiểm chứng:
1. Launcher `PackagedHello.exe` được tạo.
2. Ứng dụng chạy từ **application image** thay vì gọi `java -jar` trực tiếp.
3. Image có thư mục **runtime đi kèm**, chứa `lib/modules` của Java runtime image.

Trong môi trường kiểm chứng, launcher hoạt động sau khi `jpackage` tạo image với `--runtime-image`; runtime dùng là bản được link từ JDK đang chạy công cụ.

**Phân biệt kiểm tra cục bộ và kiểm tra triển khai:** Máy build có JDK sẵn. Một bản phát hành thật cần được kiểm tra thêm **trên máy Windows tương thích không cài Java riêng**, để xác nhận mọi đường dẫn/launcher hoạt động độc lập với Java trong hệ thống.

### 6.6. Kết quả kiểm chứng trong môi trường thực hành

Quy trình đầy đủ đã được chạy, không chỉ suy đoán từ tài liệu:

| Bước | Kết quả |
| --- | --- |
| `javac -encoding UTF-8 --release 17` | Thành công |
| `jar --create --main-class` | Thành công |
| `java -jar ... course` | In đúng 3 dòng |
| `jdeps --print-module-deps` | `java.base,java.logging` |
| `jlink --add-modules java.base,java.logging` | Runtime image được tạo |
| `jpackage --type app-image --runtime-image` | Application image Windows được tạo |
| `PackagedHello.exe course` | In đúng 3 dòng như bản chạy trực tiếp |
| `runtime/lib/modules` trong application image | Có thật |

Lưu ý rằng lần chạy được thực hiện trên **JDK 24 (toolchain) nhưng biên dịch bytecode với `--release 17`**. Đây là một điểm cần nói rõ khi đánh giá tái lập: **runtime kèm theo là runtime JDK của toolchain link**, không phải “Java 17” chỉ vì flag `--release 17`.

## 7. Nếu bỏ `--runtime-image` thì sao?

Bạn có thể chọn để `jpackage` tự tạo Java runtime:

~~~powershell
jpackage --type app-image --name PackagedHelloAuto --input input --main-jar packaged-hello.jar --main-class PackagedHello --win-console --dest release
~~~

Lệnh trên là biến thể cùng cấu trúc chương trình: `jpackage` tạo runtime bằng `jlink` khi không có `--runtime-image`. Đây thường là cách tốt để tạo **bản chạy đầu tiên** trước khi tối ưu hóa module.

Một thử nghiệm riêng trên máy build đã xác nhận rằng khi bỏ `--runtime-image`, `jpackage` vẫn tạo app image có launcher và `runtime/lib/modules` và launcher khởi động được.

**So sánh hai chiến lược:**

| Tiêu chí | Runtime tự động | Runtime tùy chỉnh `jlink` |
| --- | --- | --- |
| Số bước | Ít | Nhiều hơn |
| Kiểm soát module | Theo mặc định/tùy chọn `jpackage` | Chọn rõ qua `jlink --add-modules` |
| Dung lượng | Có thể lớn hơn | Có thể nhỏ hơn nếu chỉ có modules cần thiết |
| Rủi ro thiếu module khi dùng động | Vẫn có, cần test | Cần kiểm tra kỹ hơn vì có thể rút gọn mạnh |
| Dễ lặp lại build | Phải cố định JDK và options | Phải cố định JDK, module list và options |
| Khả năng kiểm thử | Cần test end-to-end | Cần test end-to-end |

**Không có quy tắc “tự động luôn lớn gấp N lần tùy chỉnh”**. Dung lượng phụ thuộc phiên bản JDK, các module, service providers, native libraries và tùy chọn build. Thực tế thử nghiệm trên máy local có khác biệt kích thước rõ rệt giữa hai cách, nhưng không nên lấy số megabyte của một máy làm tiêu chuẩn cho mọi ứng dụng.

## 8. Application image không đồng nghĩa một tệp nhị phân duy nhất

Đôi khi người dùng nghe “self-contained” và hiểu “chỉ cần gửi một file `.exe` là đủ”. Điều đó **không đúng** cho application image thông thường.

Trong Windows app image, `PackagedHello.exe` là **launcher**, cần các file ở thư mục `app` và `runtime` đi kèm. Nếu chỉ chép riêng `.exe` sang thư mục khác hoặc xóa `runtime`, có thể làm ứng dụng không chạy.

### Khi phân phối app image dạng thư mục

- Giữ nguyên cây thư mục do `jpackage` tạo.
- Nén/phân phối cả thư mục nếu chính sách phát hành cho phép.
- Giải nén và kiểm tra launcher từ vị trí cuối.
- Đảm bảo quyền truy cập file, quyền thực thi và các file đi kèm không bị giải nén sai.
- Không tự suy đoán cấu trúc file chi tiết là API ổn định giữa các phiên bản.

### Khi cần trải nghiệm cài đặt thông thường

Tạo native installer theo nền tảng, có thể từ ứng dụng đã build hoặc từ một app image đã kiểm thử. Ví dụ hướng lệnh (phụ thuộc nền tảng, chưa phải ví dụ đã chạy):

~~~powershell
# Windows, khi có các công cụ tạo installer phù hợp:
jpackage --type exe --name PackagedHello --input input --main-jar packaged-hello.jar --main-class PackagedHello --runtime-image runtime --win-console --dest release
~~~

**Điều kiện:** Đóng gói `exe`/`msi` trên Windows có thể yêu cầu các công cụ hệ thống bổ sung (ví dụ WiX phiên bản tương thích với JDK), còn macOS và Linux có các yêu cầu riêng về ký mã hoặc đóng gói. Chạy `jpackage --help` và xem hướng dẫn **đúng phiên bản JDK hiện đang dùng** trước khi áp dụng. Không hứa rằng một máy chỉ có JDK là luôn tạo được mọi installer.

## 9. Build cho đúng OS và kiến trúc

`jpackage` tạo ứng dụng và installer **phụ thuộc nền tảng**, không phải công cụ cross-compiler tự động. App image được tạo trên Windows không trở thành ứng dụng macOS/Linux khi sao chép sang hệ khác.

| Nền tảng build | Launcher / app image điển hình | Installer có thể tạo |
| --- | --- | --- |
| Windows | Launcher `.exe` cùng app/runtime directories | `exe`, `msi` |
| macOS | `.app` bundle với launcher, app và runtime | `dmg`, `pkg` |
| Linux | Launcher và thư mục chứa app/runtime | `deb`, `rpm` tùy distro và tooling |

**Quan trọng:** Phải kiểm soát cả **CPU architecture** như x64/arm64, không chỉ tên OS. Nếu ứng dụng dùng JNI hoặc native libraries, những file đó phải tương thích OS/architecture đích.

### 9.1. Cách tổ chức pipeline phát hành

Một pipeline tương đối an toàn:

~~~text
Commit / release tag
    |
    +-- Build & test Java code
    |
    +-- Matrix:
          Windows x64   -> jpackage app-image -> smoke test -> installer -> sign -> publish
          macOS arm64   -> jpackage app-image -> smoke test -> installer -> sign/notarize -> publish
          Linux x64     -> jpackage app-image -> smoke test -> deb/rpm -> publish
    |
    +-- Security scan, manifest/SBOM, checksums, release notes
    |
    +-- Chạy kiểm thử trên môi trường không có JDK/JRE hệ thống
~~~

Đây là **sơ đồ gợi ý quy trình**, không phải lệnh chạy trực tiếp. Build trên runners/machines tương ứng từng OS và kiến trúc. Bước ký mã, notarization, bản quyền và phân phối phụ thuộc kênh phát hành.

### 9.2. “Không cần Java hệ thống” không có nghĩa không cần OS dependencies

Ứng dụng vẫn có thể phụ thuộc:
- Thư viện hệ điều hành cho đồ họa, âm thanh, TLS hoặc các chức năng native.
- Native DLL/`.so`/`.dylib` do ứng dụng hoặc bên thứ ba cung cấp.
- Truy cập file/configuration, chứng chỉ hoặc proxy của máy đích.
- Kiến trúc CPU, phiên bản OS, quyền người dùng và giới hạn bảo mật.
- Tài nguyên như font, codec, thư viện GUI hoặc driver đặc thù.

Runtime kèm theo giải quyết **phụ thuộc Java runtime**, không tự đảm bảo ứng dụng chạy trên **mọi bản hệ điều hành**.

## 10. Non-modular JAR và modular application

### 10.1. Non-modular: `--main-jar`

Nếu ứng dụng chạy qua classpath/JAR thông thường, dùng:

~~~bash
jpackage --type app-image --name DemoApp --input input --main-jar demo.jar --main-class com.example.Main --dest release
~~~

`--main-jar` lấy JAR từ thư mục `--input`. Khi app có nhiều JAR, resource và config đi kèm, phải đặt đúng các file cần được phân phối vào input. Không quên file database driver hoặc dependency chỉ xuất hiện trên các đường chạy ít dùng.

### 10.2. Modular: `--module`

Nếu ứng dụng có `module-info.java` và đóng gói theo Java Platform Module System (JPMS), có thể dùng:

~~~bash
jpackage --type app-image --name DemoApp --module-path mods --module com.example.app/com.example.app.Main --dest release
~~~

Đây là **lệnh khuôn mẫu**, cần một modular application thật có tên module, main class và module path tương ứng. `jpackage` có thể đưa main module và transitive module dependencies vào runtime. Khi cần module JDK hoặc provider bổ sung, chỉ định `--add-modules`, `--module-path` và `--jlink-options` thích hợp.

**Không trộn tùy tiện:** `--main-jar` và `--module` mô tả hai cách chọn main application **loại trừ nhau**.

### 10.3. Cân nhắc việc chuyển sang module chỉ để đóng gói

Không nhất thiết phải chuyển toàn bộ ứng dụng legacy/classpath sang JPMS để tạo application image. `jpackage` hỗ trợ **cả non-modular và modular**. Lựa chọn module nên dựa trên kiến trúc, khả năng module hóa các dependency, nhu cầu strong encapsulation và khả năng bảo trì, không phải chỉ để cho phép người dùng không cài Java.

## 11. Tính tương thích của phiên bản: bốn câu hỏi khác nhau

Một phiên bản phân phối có nhiều “version”:

1. **Source/bytecode target:** `javac --release 17` tạo lớp và API được biên dịch theo mục tiêu Java 17.
2. **JDK chạy công cụ:** JDK mà bạn dùng để gọi `jlink` và `jpackage`, ví dụ 17, 21 hoặc một bản được hỗ trợ khác.
3. **Runtime thực sự được kèm:** Runtime modules/đường dẫn được build hoặc cung cấp qua `--runtime-image`.
4. **Version ứng dụng:** `--app-version` hoặc version ghi trong manifest/release metadata.

Ví dụ: Có thể biên dịch source bằng JDK 24 với `--release 17`, rồi chạy `jlink` cùng JDK 24. Bản app image vẫn kèm **runtime Java 24**, không phải Java 17. Nếu người dùng đặt kỳ vọng phiên bản runtime là một bản LTS cụ thể, build pipeline phải **cố định toolchain** và kiểm tra kết quả.

### 11.1. Vì sao không nên ghép ngẫu nhiên runtime từ JDK khác?

`jlink` làm việc với modules và runtime files thuộc một hệ JDK. Các module `jmods` và native libraries phải tương thích, đồng bộ phiên bản/kiến trúc. Đừng ghép thủ công module JDK 17 với native runtime khác để tạo một cấu hình không được hỗ trợ.

Để kiểm soát runtime an toàn, dùng một JDK đã xác minh và xây image trong pipeline reproducible; khi cần một JDK build khác với target runtime, hãy hiểu rõ những giới hạn tương thích của từng công cụ và kiểm thử trên sản phẩm cuối cùng.

### 11.2. Bản phân phối không tự được cập nhật khi Java hệ thống nâng cấp

Một lợi ích của runtime kèm theo là độc lập với Java hệ thống. Mặt trái: **cập nhật JDK/JRE hệ thống không có nghĩa runtime đang nằm bên trong ứng dụng tự được vá**. Chủ ứng dụng phải:

- Theo dõi các bản vá bảo mật của dòng JDK đang dùng.
- Build lại app image/installer với runtime đã cập nhật.
- Phát hành bản mới qua cơ chế update của ứng dụng.
- Kiểm thử hồi quy trên OS mục tiêu sau khi thay đổi runtime.

Đây là trách nhiệm vận hành quan trọng của việc phân phối “self-contained”.

## 12. Những thành phần cần kiểm tra trước khi phát hành

### 12.1. Java modules

Chạy `jdeps`, dùng `jlink` hoặc để `jpackage` tự link, rồi xác minh bằng `--list-modules` và test tính năng.

### 12.2. Java libraries

Xác nhận tất cả JAR/runtime resources được đóng gói. Nếu dùng Maven/Gradle, kiểm tra `runtimeClasspath` hoặc cấu hình tương đương, không chỉ `compileClasspath`.

### 12.3. Service providers và reflection

Kiểm thử:
- JDBC driver được nạp qua `DriverManager`.
- `ServiceLoader`, provider cho logging/crypto/locale khi có.
- Tên class từ config hoặc reflection.
- Serialization, dependency injection và framework proxy.

Các cơ chế này có thể không được phản ánh đầy đủ chỉ bởi `jdeps` tĩnh; cân nhắc `--bind-services` hoặc module additions theo bằng chứng thực tế.

### 12.4. Native libraries và đường dẫn

Kiểm tra cách nạp DLL/`.so`/`.dylib`, quyền thực thi và nơi ghi cấu hình/log. **Đừng mặc định thư mục cài đặt luôn ghi được**; nhiều OS quản lý thư mục ứng dụng theo chính sách quyền nghiêm ngặt. Dữ liệu người dùng nên lưu vào vị trí dữ liệu ứng dụng phù hợp với OS, không sửa trực tiếp file bên trong runtime image.

### 12.5. Vận hành và phân phối

- Bản quyền và license của Java runtime + các thư viện kèm theo.
- Chữ ký mã và cơ chế chứng thực installer tùy OS.
- SBOM và checksums để kiểm chứng artifact.
- Metadata gồm app version, vendor, description.
- Kịch bản cài đặt, mở, cập nhật, gỡ cài đặt.
- Kiểm tra bảo vệ dữ liệu và không đóng gói secret/API key trong JAR hoặc image.

## 13. Khi nào nên dùng cách nào?

| Tình huống | Lựa chọn khởi đầu phù hợp |
| --- | --- |
| App desktop cho người dùng không có Java | `jpackage --type app-image`, sau đó tạo native installer nếu cần |
| CLI tool dùng nội bộ trên Windows | App image có `--win-console` để nhìn stdout/stderr |
| App chỉ cần vài JDK modules, dung lượng quan trọng | `jdeps` + `jlink` + `jpackage --runtime-image` |
| App non-modular có nhiều dependency | Chuẩn hóa JAR/input; để `jpackage` tạo runtime trước, rồi tối ưu khi có test |
| App JPMS/module rõ ràng | `jpackage --module-path --module` |
| Nhiều OS/CPU | Matrix build/test tương ứng; không tái sử dụng nguyên image của OS khác |
| Chỉ triển khai backend trong container | Có thể dùng container image với runtime phù hợp hoặc cơ chế runtime khác; `jpackage` không phải bắt buộc |
| Chỉ giao thư viện cho một ứng dụng Java khác | Thông thường phát hành JAR/library; không cần runtime riêng cho từng library |

**Lưu ý:** Một backend Java chạy trong container hoặc một ứng dụng web phục vụ qua trình duyệt có thể có mô hình phân phối hoàn toàn khác app desktop. “Kèm runtime” vẫn có ý nghĩa trong container image, nhưng không nhất thiết phải tạo native launcher/installer bằng `jpackage` cho mọi trường hợp.

## 14. Lỗi phổ biến và cách khắc phục

### Lỗi A — Phát hành mỗi JAR và nói người dùng không cần Java

~~~text
my-app.jar
~~~

Đây chỉ là một JAR. Nếu người dùng chạy bằng `java -jar`, họ vẫn cần một Java runtime thích hợp ở máy đích.

**Sửa:** phân phối app image hoặc installer kèm runtime, hoặc có quy trình cài Java rõ ràng nếu sản phẩm không yêu cầu self-contained.

### Lỗi B — Chỉ gửi file launcher `.exe`

Launcher có thể phụ thuộc các thư mục `app` và `runtime` cùng image. Chép riêng `.exe` thường làm ứng dụng hỏng.

**Sửa:** giữ nguyên toàn bộ cấu trúc application image hoặc phát hành installer được tạo chính thức.

### Lỗi C — Tin `--release 17` làm runtime đi kèm thành Java 17

`--release` điều khiển **target compilation**, không làm thay đổi bản JDK mà `jlink` sử dụng.

**Sửa:** cố định toolchain/runtime mong muốn và xác nhận `runtime/bin/java --list-modules` hoặc metadata runtime.

### Lỗi D — Chỉ lấy output của `jdeps` làm toàn bộ runtime

Runtime có thể thiếu service provider, module được nạp động hoặc chức năng ít dùng.

**Sửa:** kiểm thử tích hợp; thêm module/provider cần thiết vào image theo bằng chứng. Đừng thu nhỏ runtime cho đến khi hiểu đúng tác động.

### Lỗi E — Quên dependency JAR và resources

`jlink` xử lý module runtime, không tự đưa mọi dependency ứng dụng vào package.

**Sửa:** chuẩn bị `--input` đầy đủ, kiểm tra classpath/manifest hoặc đường đóng gói JPMS, kiểm thử packaging artifact thay vì chỉ chạy trong IDE.

### Lỗi F — Dùng image build Windows để phát hành macOS

`jpackage` không tự tạo đa nền tảng từ một bản build.

**Sửa:** build bằng runners đúng OS và CPU architecture đích.

### Lỗi G — Tạo installer nhưng chưa thử app image

Nếu launcher hoặc runtime image sai, installer cũng có thể cài một ứng dụng không khởi động được.

**Sửa:** dùng `--type app-image` làm bước kiểm thử trước, chạy launcher từ thư mục output và chạy automated smoke tests.

### Lỗi H — Không có công cụ tạo native installer

Trên Windows, tùy JDK và định dạng, `jpackage` có thể cần WiX tương thích. macOS/Linux có công cụ, chứng chỉ hoặc môi trường build riêng.

**Sửa:** kiểm tra `jpackage --help` và điều kiện của hệ điều hành / JDK cụ thể. Không đánh đồng việc app image build được với mọi installer build được.

### Lỗi I — Tin self-contained có nghĩa chạy trên mọi OS

App image chứa native launcher và các file native/JVM theo OS/CPU.

**Sửa:** khai báo rõ ma trận hỗ trợ, build và test theo môi trường đích; kiểm tra những native dependencies khác Java.

### Lỗi J — Bỏ quên cập nhật runtime

Java hệ thống được vá nhưng app image vẫn chứa bản cũ.

**Sửa:** đưa runtime vào kế hoạch bản vá bảo mật, rebuild và phát hành lại theo quy trình versioned releases.

### Lỗi K — Tối ưu bằng cách xóa tùy tiện file trong runtime

File runtime có những thành phần cần thiết để nạp module hoặc chạy native code.

**Sửa:** dùng các tùy chọn hỗ trợ chính thức của `jlink` và `jpackage`; đừng xóa thủ công file không hiểu ý nghĩa.

## 15. Bài tập tự kiểm tra

### Bài 1 — Xác định sản phẩm

Bạn có tệp `report.jar` và câu lệnh `java -jar report.jar`. Người dùng cần có Java không?

**Đáp án:** Có, theo mô hình này máy chạy phải có một Java runtime phù hợp. JAR tự nó **không kèm runtime**.

### Bài 2 — Chọn cách tạo app image nhanh nhất

Ứng dụng non-modular có `input/demo.jar` và `com.example.Main`. Hãy tạo app image không chỉ định runtime tùy chỉnh.

**Đáp án khuôn mẫu:**

~~~bash
jpackage --type app-image --name Demo --input input --main-jar demo.jar --main-class com.example.Main --dest release
~~~

`jpackage` sẽ tạo runtime cho image từ JDK công cụ theo các tùy chọn hiện hành. Lệnh này là ví dụ **mẫu**, cần JAR và class đúng thực tế.

### Bài 3 — Tối ưu module

`jdeps --print-module-deps input/packaged-hello.jar` trả `java.base,java.logging`. Lệnh `jlink` nào phù hợp cho ví dụ đã kiểm chứng?

**Đáp án:**

~~~bash
jlink --add-modules java.base,java.logging --output runtime
~~~

Có thể thêm `--strip-debug --no-man-pages --no-header-files` để giảm dữ liệu phụ khi tạo runtime. Vẫn phải kiểm thử đầy đủ, nhất là khi chương trình dùng reflection/providers.

### Bài 4 — So sánh hai version

Ứng dụng được biên dịch bằng `javac --release 17` nhưng image được tạo bằng `jlink` của JDK 24. Runtime trong image là Java 17 hay 24?

**Đáp án:** Runtime image được link từ các **module JDK 24** nên là runtime **24**, trong khi bytecode của ứng dụng được biên dịch nhắm **Java 17**. Một chương trình biên dịch nhắm Java 17 có thể chạy trên runtime Java 24 nếu tương thích, nhưng flag `--release` không quyết định version runtime.

### Bài 5 — Vì sao app image lớn hơn JAR?

Một JAR vài KB tạo thành app image hàng chục MB. Có phải `jpackage` đã tạo lỗi?

**Đáp án:** Không nhất thiết. App image chứa **Java runtime modules, native launcher và các file hỗ trợ**, không chỉ bytecode ứng dụng. Dung lượng phụ thuộc module/OS/JDK và có thể đáng kể ngay với app đơn giản. Muốn giảm, xác định module cần thiết và dùng `jlink` nhưng không bỏ qua chức năng.

### Bài 6 — Test trên máy sạch

Bản phát hành Windows chạy được trên máy developer có Java sẵn. Điều đó đủ để tuyên bố “người dùng không cần Java” chưa?

**Đáp án:** **Chưa**. Cần kiểm tra trên máy thử nghiệm tương thích không có Java hệ thống, giữ nguyên app image đầy đủ, xem runtime được kèm và thử luồng nghiệp vụ chính. Developer machine có thể vô tình che giấu dependency thiếu.

### Bài 7 — ServiceLoader và runtime thiếu provider

Sau khi link runtime tối giản, app mở màn hình đầu nhưng một tính năng dùng `ServiceLoader` thất bại. Vì sao?

**Đáp án:** Phân tích `jdeps` tĩnh có thể không cho thấy provider được chọn động. Kiểm tra service/provider, bổ sung module hoặc dùng `--bind-services` nếu phù hợp, rồi kiểm thử lại packaged app.

### Bài 8 — App-image và installer

Bạn vừa tạo `release/PackagedHello` chứa launcher và runtime. Có thể xem đó là một `.msi` đã sẵn sàng để cài trên Windows không?

**Đáp án:** Không. Đó là **application image**. Muốn installer `msi` hoặc `exe` cần chạy `jpackage` với loại package thích hợp, đáp ứng yêu cầu công cụ tạo installer của hệ thống và kiểm thử cài/gỡ.

## 16. Checklist phát hành ứng dụng kèm runtime

- [ ] Định nghĩa rõ **OS, CPU architecture, version tối thiểu** được hỗ trợ.
- [ ] Xác nhận artifact ứng dụng (JAR/modules/resources/dependencies) đầy đủ.
- [ ] Cố định toolchain JDK, build options và runtime version theo chính sách.
- [ ] Phân tích JDK modules bằng `jdeps` và kiểm tra dependency động.
- [ ] Chọn `jpackage` runtime tự động hoặc `jlink` tùy chỉnh có kiểm chứng.
- [ ] Tạo app image trước, chạy launcher trực tiếp với đối số thực tế.
- [ ] Xác nhận image có **runtime bên trong**, không chỉ một file launcher.
- [ ] Kiểm thử trên máy sạch **không cài Java hệ thống**.
- [ ] Kiểm thử dependency ít dùng, service provider, native libraries và đường dẫn dữ liệu.
- [ ] Đánh giá size, startup, resource usage và overhead của runtime được kèm.
- [ ] Tạo installer, ký mã và kiểm thử cài/gỡ khi kênh phân phối yêu cầu.
- [ ] Ghi version, checksums, SBOM và release notes để truy vết.
- [ ] Có quy trình cập nhật **JDK runtime đóng gói** khi xuất hiện bản vá bảo mật.
- [ ] Không nhúng secret vào JAR hoặc các file cấu hình không được bảo vệ.

## 17. Kết luận

**Mục tiêu của đóng gói ứng dụng Java kèm runtime là đơn giản hóa việc chạy và triển khai ứng dụng cho người dùng cuối**, đồng thời kiểm soát các phụ thuộc Java cần thiết. Muốn đạt mục tiêu đó:

1. **JAR** chứa mã ứng dụng nhưng thường chưa có runtime.
2. **`jlink`** tạo một Java runtime image theo các module được chọn.
3. **`jpackage`** kết hợp ứng dụng, launcher và runtime thành **app image** hoặc **native installer**.
4. Có thể **để `jpackage` link runtime tự động** hoặc **truyền runtime do `jlink` tạo** bằng `--runtime-image`.
5. **`jdeps` là khởi điểm để tìm modules**, không thay thế kiểm thử với dynamic loading, providers và native dependencies.
6. Một bản phân phối **không cần Java hệ thống** vẫn phải phù hợp **OS/CPU, quyền, native libraries và bản vá bảo mật**.
7. Cần kiểm tra **chính sản phẩm cuối** trên máy sạch; app chỉ chạy được trong IDE chưa chứng minh bản phát hành đã đầy đủ.

**Nguồn chính thức và hiện hành:**
- [Oracle JDK 21 — `jpackage` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html): các loại package, `--runtime-image`, `--main-jar`, `--module` và tùy chọn link.
- [Oracle JDK 21 — Packaging Overview](https://docs.oracle.com/en/java/javase/21/jpackage/packaging-overview.html): application image, runtime đi kèm và phụ thuộc theo OS.
- [Oracle JDK 21 — Java Runtime Modifications](https://docs.oracle.com/en/java/javase/21/jpackage/java-runtime-modifications.html): tạo và sử dụng runtime tùy chỉnh.
- [Oracle JDK 21 — `jlink` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html): tạo custom runtime image.
- [Oracle JDK 21 — `jdeps` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): kiểm tra module dependencies.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): `jpackage` trở thành công cụ chính thức từ Java 16.
- [OpenJDK JEP 282 — jlink](https://openjdk.org/jeps/282): linker cho Java runtime image.
