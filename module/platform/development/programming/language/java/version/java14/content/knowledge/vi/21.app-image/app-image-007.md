# Runtime được tạo qua jlink hoặc được cung cấp sẵn khi đóng gói app image bằng jpackage

## 1. Mục tiêu của bài học

Một ứng dụng Java thường được chạy bằng lệnh `java -cp ...` hoặc `java --module-path ... -m ...`, đòi hỏi máy đích đã cài một Java runtime tương thích. Với **`jpackage`**, ta có thể tạo một **application image (app image)** gồm cả ứng dụng, launcher dành cho hệ điều hành và **Java runtime riêng được đóng cùng ứng dụng**. Người dùng chạy launcher của ứng dụng mà không cần tự cài JDK/JRE toàn cục.

Câu hỏi quan trọng: **Java runtime nằm trong app image được lấy từ đâu?** Có hai cách chính, cùng còn được hỗ trợ trên JDK hiện hành:

1. **Để `jpackage` tạo runtime:** không truyền `--runtime-image`. Công cụ tự gọi **`jlink`** để tạo runtime image phù hợp với các module/cấu hình được chỉ định.
2. **Dùng runtime image có sẵn:** tự chạy `jlink` từ trước, hoặc nhận một **runtime image hợp lệ đã được xây dựng**, rồi truyền thư mục đó bằng `--runtime-image`. `jpackage` sao chép runtime đó vào app image, không tự thực hiện lại bước link để bổ sung các module còn thiếu.

Ví dụ rút gọn:

~~~bash
# Cách A: jpackage tự chạy jlink.
jpackage --type app-image --name MyApp \
    --input input --main-jar app.jar --main-class AppMain

# Cách B: runtime đã được tạo bằng jlink từ trước.
jlink --add-modules java.base,java.logging \
    --output custom-runtime
jpackage --type app-image --name MyApp \
    --input input --main-jar app.jar --main-class AppMain \
    --runtime-image custom-runtime
~~~

Đây là **mảnh lệnh minh họa trên shell hỗ trợ dấu `\` nối dòng**; các thư mục/JAR/class phải có thật, và câu lệnh Windows PowerShell đầy đủ nằm ở mục 6.

**Chú ý phiên bản:** `jpackage` xuất hiện ở dạng *incubating tool* trong **Java 14**, nhưng đã trở thành công cụ chính thức của JDK từ **Java 16** (JEP 392). Khi phát triển mới, sử dụng cú pháp và tài liệu hiện hành của **Java 17+**, không dùng module incubator `jdk.incubator.jpackage` hoặc quy trình thời Java 14.

## 2. Phân biệt JDK, runtime image và app image

Ba khái niệm thường bị gọi nhầm là “bộ Java”:

| Thành phần | Bản chất | Có gì? | Vai trò |
| --- | --- | --- | --- |
| **JDK dùng để build** | Bộ công cụ phát triển Java | `javac`, `jar`, `jdeps`, `jlink`, `jpackage`, các JDK modules... | Biên dịch, phân tích dependency và tạo bản phân phối |
| **Runtime image** | Một Java runtime theo tập modules đã link | `java.base` và những modules/dependencies được chọn, thư viện runtime, metadata | Chạy ứng dụng, có thể gọn hơn JDK đầy đủ |
| **Application image** | Bộ ứng dụng được đóng gói | Launcher riêng + app JAR/resources + runtime image | Bản phân phối ứng dụng chạy trực tiếp trên nền tảng đã build |

Quy trình khái quát:

~~~text
AppMain.java
     |
 javac + jar
     v
 input/app.jar
     |
     |  jpackage --type app-image
     |             |
     |       +-----+------------------------+
     |       |                              |
     |  Không --runtime-image         Có --runtime-image
     |       |                              |
     |  jpackage gọi jlink           runtime image có sẵn
     |       |                              |
     +-------+------------------------------+
             |
        Application image
        +---------------------+
        | launcher của app    |
        | app JAR/resources   |
        | Java runtime        |
        +---------------------+
~~~

**`jlink` không tự tạo launcher native của ứng dụng theo cùng cách `jpackage`.** `jlink` tạo Java runtime image dựa trên modules; `jpackage` kết hợp runtime đó với ứng dụng và launcher. Đây là hai nhiệm vụ liên quan nhưng khác nhau.

**`--type app-image` không có nghĩa là installer.** Nó tạo thư mục/bundle có thể chạy. Các dạng installer như `exe/msi` (Windows), `deb/rpm` (Linux) hoặc `dmg/pkg` (macOS) là những `--type` khác, tùy nền tảng và công cụ hệ thống bổ sung.

## 3. Cách A — Để jpackage tự tạo runtime với jlink

Khi **không có `--runtime-image`**, `jpackage` tự gọi `jlink`. Ví dụ ứng dụng **non-modular**, chạy bằng classpath:

~~~bash
jpackage --type app-image \
    --name AutoDemo \
    --input input \
    --main-jar app.jar \
    --main-class AppMain \
    --dest dist
~~~

Kết quả là một app image mang tên `AutoDemo` trong `dist`; bên trong chứa runtime được tạo tự động. Các lựa chọn:

- `--type app-image`: chỉ tạo app image, không tạo installer.
- `--name AutoDemo`: tên ứng dụng/launcher.
- `--input input`: thư mục chứa JAR và các tài nguyên cần đóng gói.
- `--main-jar app.jar`: tên JAR **tương đối so với `--input`**, không phải đường dẫn tùy ý ở mọi nơi.
- `--main-class AppMain`: main class để launcher gọi; cần khi JAR không khai báo main class trong manifest hoặc muốn chỉ định rõ.
- `--dest dist`: thư mục đích của app image.

Với non-modular app có `--main-jar`, JDK hiện đại chọn **tập JDK modules mặc định dành cho classpath/unnamed-module applications**, chứ **không chỉ riêng `java.base`**. Điều này thường làm app chạy dễ dàng nhưng runtime có thể chưa tối giản.

Với **modular app** (có `module-info.java` và được đóng thành modular JAR), `jpackage --module-path ... --module name/main-class` có thể dựa vào **main module và transitive module dependencies** để tạo runtime. Những phụ thuộc được khai báo bằng `requires` được xử lý trong đồ thị module.

### Tùy chỉnh runtime tự tạo

Các lựa chọn liên quan trực tiếp tới `jlink`:

~~~bash
jpackage --type app-image \
    --name AutoDemo \
    --input input --main-jar app.jar --main-class AppMain \
    --add-modules java.logging \
    --jlink-options "--strip-debug --no-man-pages --no-header-files" \
    --dest dist
~~~

Đây là ví dụ **có chỉ định jlink options**, không phải lệnh cần thiết để chạy ví dụ ở mục 6. Với runtime do jpackage tạo:

- `--add-modules` bổ sung root modules được chuyển cho `jlink`. Module tương ứng và dependencies phải có trong module path quan sát được.
- `--module-path` cung cấp nơi tìm ứng dụng/module bổ sung khi đóng gói modular app.
- `--jlink-options` chuyển các lựa chọn link runtime cho `jlink`.
- **Mặc định nếu không chỉ định `--jlink-options`**, jpackage dùng `--strip-native-commands --strip-debug --no-man-pages --no-header-files`. Khi **tự cung cấp `--jlink-options`**, không tự giả định tất cả lựa chọn mặc định vẫn được cộng thêm; hãy truyền đầy đủ những lựa chọn muốn giữ.

**Không đặt `--runtime-image` nếu mục tiêu là để `jpackage` tự chọn/link modules.** Tùy chọn này chuyển sang cách B.

## 4. Cách B — Tạo runtime bằng jlink trước rồi cung cấp cho jpackage

Cách này cho phép kiểm soát rõ ràng **những module nào có trong Java runtime**, cũng như các lựa chọn tối ưu.

Ví dụ ứng dụng cần `java.base` và `java.logging`:

~~~bash
jlink --add-modules java.base,java.logging \
    --output custom-runtime \
    --strip-debug \
    --no-header-files \
    --no-man-pages
~~~

`jlink` tìm các JDK modules trên module path (mặc định thường là `$JAVA_HOME/jmods` của JDK chạy công cụ), liên kết các root modules với **toàn bộ transitive dependencies** và tạo thư mục runtime `custom-runtime`.

Sau đó:

~~~bash
jpackage --type app-image \
    --name CustomDemo \
    --input input \
    --main-jar app.jar \
    --main-class AppMain \
    --runtime-image custom-runtime \
    --dest dist
~~~

**`--runtime-image` nhận một **đường dẫn thư mục Java runtime image hợp lệ**, không phải đường dẫn `java.exe`, không phải `.jar` và cũng không phải `.jfr`.** Đường dẫn có thể tuyệt đối hoặc tương đối so với thư mục hiện tại.

Khi đã chọn cách B:

1. Runtime phải được tạo trước khi gọi `jpackage`.
2. `jpackage` sao chép nội dung runtime image vào app image mới.
3. Công cụ đóng gói **không tự link thêm modules** vào runtime đã đưa qua `--runtime-image`; trách nhiệm đầy đủ dependency thuộc về người tạo runtime.
4. Hãy kiểm thử launcher trên hệ thống đích: việc có thư mục runtime hợp lệ **không** đảm bảo ứng dụng có đủ mọi module hoặc dependency động.

Lý do nên chọn cách B:

- Muốn **runtime tối giản** sau khi phân tích module dependencies và thử nghiệm.
- Muốn **reproducible build**: cố định JDK version, các module và lựa chọn `jlink`.
- Cần một **nhóm modules riêng** (chẳng hạn các modules từ thư viện tùy biến, JavaFX, locales, crypto providers).
- Muốn xây một runtime đáp ứng **chính sách nền tảng/cấu hình** riêng, rồi đóng gói cùng nhiều app.
- Có yêu cầu runtime version khác JDK được dùng để chạy `jpackage`, trong giới hạn compatibility có thể kiểm chứng.

**Dùng lại runtime** không có nghĩa người dùng cuối sử dụng **một thư mục Java duy nhất được chia sẻ**. Khi `jpackage` sao chép runtime vào từng app image, mỗi app vẫn có thể mang một **bản sao riêng**.

## 5. Bảng lựa chọn hai cách

| Tiêu chí | jpackage tự chạy jlink | Runtime có sẵn qua --runtime-image |
| --- | --- | --- |
| Công tạo runtime | jpackage thực hiện tự động | Người build tự chạy jlink hoặc cung cấp image hợp lệ |
| Dễ thiết lập | Ít bước, phù hợp khởi đầu | Nhiều bước hơn, chủ động kiểm soát |
| Chọn modules | Main module/default module set + `--add-modules` và jlink settings | Modules được chốt lúc tạo runtime trước đó |
| Tối ưu kích thước | Có thể tùy chỉnh bằng jlink options, nhưng defaults không phải lúc nào nhỏ nhất | Dễ tối ưu chính xác theo nhu cầu đã đo |
| Dùng JDK khác để tạo runtime | Phụ thuộc jpackage/JDK của build process | Có thể cung cấp runtime từ một JDK tương thích khác |
| Kiểm soát service providers | Các quy tắc jpackage/jlink của JDK hiện tại | `jlink --bind-services` hoặc modules đã xác định |
| Nguy cơ thiếu module | Có thể xảy ra, nhất là phụ thuộc động | Có thể xảy ra khi tự chọn quá ít modules |
| Phù hợp | Ứng dụng thông thường, build pipeline ngắn | Yêu cầu module chính xác, môi trường đặc thù, quản lý runtime riêng |

**Không có lựa chọn đúng trong mọi dự án.** Nếu jpackage tự tạo runtime và launcher đã chạy đầy đủ trên máy đích, không cần mặc định chuyển sang custom runtime chỉ vì có thể. Nếu phụ thuộc không được phát hiện, cần thêm các modules hoặc cung cấp runtime rõ ràng thay vì xuất bản image chưa được kiểm thử.

## 6. Ví dụ hoàn chỉnh, Java 17+ — xây hai app image và so sánh

Ví dụ sau dùng ứng dụng **non-modular** có một main class, chủ động sử dụng `java.util.logging.Logger` để chứng minh cả hai cách đều có module `java.logging`.

Tất cả thao tác xây dựng được **kiểm thử trên OpenJDK 24/Windows**. Để xem stdout khi chạy launcher Windows, ví dụ dùng tùy chọn **`--win-console`** dành riêng cho Windows.

### 6.1. File nguồn AppMain.java

Lưu nội dung sau thành **`AppMain.java`** (UTF-8):

~~~java
import java.util.logging.Logger;

public class AppMain {
    public static void main(String[] args) {
        Logger.getLogger(AppMain.class.getName()).fine("runtime OK");

        System.out.println("app-image OK");
        System.out.println(
            "java.logging present=" +
                ModuleLayer.boot()
                    .findModule("java.logging")
                    .isPresent()
        );
    }
}
~~~

Giải thích:

- `Logger` nằm trong `java.logging`.
- `ModuleLayer.boot().findModule("java.logging").isPresent()` kiểm tra module đã được resolve trong boot layer tại runtime. Không chỉ dựa vào tên thư mục hay cấu hình mong muốn.
- `fine(...)` theo cấu hình logging mặc định có thể không in ra console; hai dòng `System.out.println` là kết quả cần kiểm thử.
- Không phụ thuộc library ngoài hoặc biến môi trường ứng dụng.

### 6.2. Biên dịch và đóng JAR

Từ thư mục chứa `AppMain.java`, mở **Windows PowerShell**:

~~~powershell
mkdir input
mkdir classes
mkdir dist

javac -encoding UTF-8 -d classes AppMain.java

jar --create --file input/app.jar -C classes .
~~~

Đây là các lệnh dành cho một thư mục làm việc mới, nơi `input`, `classes` và `dist` chưa tồn tại. Nếu các thư mục đã có, chỉ cần tái sử dụng đúng đường dẫn, tránh build cũ lẫn vào thư mục mới.

Lệnh `jar --create` tạo non-modular `app.jar`, chứa `AppMain.class`. Vì JAR này không cần manifest `Main-Class`, ta truyền `--main-class AppMain` khi đóng gói.

Có thể phân tích dependency module tĩnh:

~~~powershell
jdeps --print-module-deps input/app.jar
~~~

Với ví dụ này, kết quả kỳ vọng là:

~~~text
java.base,java.logging
~~~

`jdeps` là công cụ **gợi ý dependency từ bytecode**; nó không phát hiện chắc chắn tất cả việc dùng reflection, dynamic class loading, JNI hoặc provider được nạp qua `ServiceLoader`. Không dựa hoàn toàn vào `jdeps` để quyết định image cuối cùng khi ứng dụng có những cơ chế đó.

### 6.3. Cách A: jpackage tự tạo runtime

~~~powershell
jpackage --type app-image --name AutoDemo --input input --main-jar app.jar --main-class AppMain --dest dist --win-console
~~~

Vì **không** có `--runtime-image`, công cụ sẽ dùng `jlink` theo quy tắc của jpackage. Kết quả trên Windows:

~~~text
dist/
  AutoDemo/
    AutoDemo.exe
    app/
      app.jar
      AutoDemo.cfg
    runtime/
      ...
~~~

Đây là **sơ đồ khái quát**, không phải danh sách tất cả file hoặc đường dẫn chi tiết của mọi nền tảng. Trên Windows, launcher thường nằm ở thư mục gốc của app image. Trên Linux và macOS, layout khác theo quy ước nền tảng.

Chạy trong PowerShell:

~~~powershell
.\dist\AutoDemo\AutoDemo.exe
~~~

Đầu ra:

~~~text
app-image OK
java.logging present=true
~~~

### 6.4. Cách B: jlink trước rồi đưa image cho jpackage

Tạo runtime tối thiểu cho bài mẫu:

~~~powershell
jlink --add-modules java.base,java.logging --output custom-runtime --strip-debug --no-header-files --no-man-pages
~~~

Ở đây **không** dùng `--strip-native-commands`, nên runtime tự tạo vẫn có thể chứa tiện ích `bin/java` để kiểm tra danh sách modules, khác với runtime do jpackage tự động tạo theo defaults.

Có thể kiểm tra:

~~~powershell
.\custom-runtime\bin\java.exe --list-modules
~~~

Kết quả danh sách module bao gồm `java.base` và `java.logging`, với phiên bản module tương ứng JDK đã dùng. **Không** hard-code số phiên bản module trong test, vì nó khác giữa JDK 17, 21, 24, 25, 26...

Đóng gói bằng runtime đã tạo:

~~~powershell
jpackage --type app-image --name CustomDemo --input input --main-jar app.jar --main-class AppMain --runtime-image custom-runtime --dest dist --win-console
~~~

Chạy:

~~~powershell
.\dist\CustomDemo\CustomDemo.exe
~~~

Đầu ra đã kiểm thử:

~~~text
app-image OK
java.logging present=true
~~~

**Hai app images đều chạy đúng một chương trình**, khác nhau ở nguồn runtime được dùng để đóng gói. Trong thử nghiệm trên **OpenJDK 24/Windows**, cả hai launcher đều tạo ra đúng hai dòng kết quả này.

### 6.5. Kiểm tra sự hiện diện của runtime trong app image

Không nên chỉ nhìn tên thư mục rồi kết luận đã đóng gói đúng. Trên Windows của ví dụ:

~~~powershell
Test-Path .\dist\AutoDemo\runtime\release
Test-Path .\dist\CustomDemo\runtime\release
~~~

Đầu ra thử nghiệm:

~~~text
True
True
~~~

Tệp `runtime/release` là metadata runtime của Java image, có thể có các trường như `JAVA_VERSION`, `MODULES`, `OS_NAME` và `OS_ARCH`. Trên Windows, có thể xem bằng `Get-Content .\dist\CustomDemo\runtime\release`. Đừng suy đoán **runtime/bin/java.exe** luôn có trong app image tự tạo: mặc định `--strip-native-commands` của jpackage có thể loại công cụ đó.

Quan trọng hơn cả file metadata là **chạy launcher** trên một máy/VM sạch cùng OS và kiến trúc, không có Java runtime cài toàn cục, rồi thử các luồng chức năng thực tế.

### 6.6. Chuyển ý tưởng sang Linux/macOS

Trên Linux/macOS, bỏ **`--win-console`** vì đó là tùy chọn Windows. `javac`, `jar`, `jlink`, `jpackage --type app-image` vẫn là các công cụ JDK, nhưng launcher được đặt ở đường dẫn khác:

| Nền tảng | Ví dụ launcher trong app image |
| --- | --- |
| Windows | `dist/AutoDemo/AutoDemo.exe` |
| Linux | `dist/AutoDemo/bin/AutoDemo` |
| macOS | `dist/AutoDemo.app/Contents/MacOS/AutoDemo` |

Các đường dẫn là **mẫu bố cục điển hình** cho app image trên từng hệ điều hành; kiểm tra kết quả thực tế của JDK/vendor bạn dùng. Với macOS, còn có quy tắc code signing/notarization khi phân phối ra ngoài.

**Không có cross-platform packaging bằng jpackage:** phải xây bản phân phối tương ứng trên nền tảng được hỗ trợ (Windows build cho Windows, Linux build cho Linux, macOS build cho macOS). Runtime image được cung cấp cũng phải tương thích **OS, CPU architecture và native libraries** của app image. Một runtime tạo trên Windows không thể đơn giản sao chép vào app image dành cho Linux rồi kỳ vọng chạy.

## 7. Với ứng dụng modular, jlink giải quyết dependencies như thế nào?

Ứng dụng modular có file `module-info.java` khai báo các module cần thiết. Ví dụ:

~~~java
module com.example.demo {
    requires java.logging;
}
~~~

Đây là **mảnh file module-info.java**, không phải chương trình độc lập. Giả sử ứng dụng đã được build thành modular JAR trong thư mục `mods`, với main class `com.example.demo.Main`.

Để **jpackage tự link runtime**, có thể chạy:

~~~bash
jpackage --type app-image \
    --name ModularDemo \
    --module-path mods \
    --module com.example.demo/com.example.demo.Main \
    --dest dist
~~~

Hoặc chủ động tạo runtime:

~~~bash
jlink --module-path mods \
    --add-modules com.example.demo \
    --output modular-runtime
~~~

Sau đó:

~~~bash
jpackage --type app-image \
    --name ModularDemo \
    --module-path mods \
    --module com.example.demo/com.example.demo.Main \
    --runtime-image modular-runtime \
    --dest dist
~~~

Đây là **các lệnh minh họa kiến trúc**: thư mục `mods` phải có modular JAR được tạo trước, và ứng dụng phải khai báo main class hợp lệ. Không thể dùng trực tiếp `AppMain.java` non-modular ở mục 6 để giả làm app modular mà không có module descriptor.

Một modular runtime được link từ `com.example.demo` sẽ giải quyết `requires java.logging` và dependencies bắc cầu. Tuy nhiên, **phụ thuộc động** như reflection, service providers, thư viện sử dụng class names dạng chuỗi hoặc thành phần native có thể cần modules hoặc resources bổ sung. Không coi “`jlink` chạy thành công” là bảo đảm mọi tính năng của app đều hoạt động.

## 8. Trường hợp quan trọng trên JDK hiện đại: service bindings

Một điểm **mới đáng lưu ý trong JDK 25 và tiếp tục áp dụng trên JDK 26**: **runtime do jpackage tự tạo không còn bổ sung service bindings theo mặc định**. Trước JDK 25, các runtime do jpackage tạo có thể kèm các module cung cấp dịch vụ do bước bind service. Việc thay đổi này có thể khiến tập modules của app image **khác nhau giữa các bản JDK**, ngay cả khi lệnh đóng gói tương tự.

Cơ chế **service binding** của `jlink` có thể thêm những **provider modules** cho các service được module khác sử dụng, ngoài phần `requires` tĩnh:

~~~bash
jlink --add-modules java.base,java.logging \
    --bind-services \
    --output runtime-with-services
~~~

Đây là **mảnh lệnh có chủ đích mở rộng modules**; hãy đo lại kích thước vì bind services có thể kéo thêm nhiều module cùng dependencies.

Khi để jpackage tự chạy jlink và ứng dụng cần service providers, có thể sử dụng:

~~~bash
jpackage --type app-image \
    --name ServiceDemo \
    --input input --main-jar app.jar --main-class AppMain \
    --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services" \
    --dest dist
~~~

**Vì sao phải đưa cả bốn lựa chọn strip và `--bind-services`?** Khi chỉ định `--jlink-options`, nên khai báo đầy đủ những options muốn áp dụng. Bốn tùy chọn strip ở trên là defaults thường dùng của jpackage; thêm `--bind-services` để yêu cầu liên kết provider modules.

Nếu dùng **runtime tự tạo**, hãy thêm `--bind-services` **ngay trong lệnh jlink tạo runtime**, hoặc chỉ định cụ thể những provider modules cần thiết. Khi `jpackage` nhận `--runtime-image`, đừng chờ nó chạy lại `jlink` và bù provider còn thiếu.

**Không bật `--bind-services` mù quáng cho mọi ứng dụng.** Nó có thể làm image lớn hơn; trong nhiều trường hợp, chọn module provider cần thiết bằng `--add-modules` là cách kiểm soát chính xác hơn. Hãy kiểm tra đúng chức năng sử dụng `ServiceLoader`, charset providers, crypto providers, XML, logging hoặc các thư viện liên quan, tùy ứng dụng.

## 9. Module dependencies: dùng jdeps nhưng vẫn cần test

Bước chuẩn bị hữu ích trước khi tạo custom runtime:

~~~bash
jdeps --print-module-deps input/app.jar
~~~

Với ví dụ `AppMain.java`, công cụ cho biết các module tĩnh của code:

~~~text
java.base,java.logging
~~~

Sau đó có thể tạo:

~~~bash
jlink --add-modules java.base,java.logging \
    --output custom-runtime
~~~

Nhưng `jdeps` phân tích bytecode và metadata tĩnh, nên **không đảm bảo nhìn thấy mọi dependency được nạp động**:

- `Class.forName("...")`, reflection, plugin discovery.
- `ServiceLoader` và providers được giải quyết khi chạy.
- JNI/native libraries và phụ thuộc hệ điều hành.
- JavaFX/modules ngoài JDK, runtime locales hoặc các module chỉ cần ở một nhánh nghiệp vụ ít chạy.
- Driver/database/HTTP/TLS functionality sử dụng modules/providers đặc thù.
- Resource files, config, icons, native components của thư viện.

**Cách làm đúng:** dùng `jdeps` làm điểm khởi đầu, ghi lại danh sách modules được chọn, rồi chạy test khởi động, test chức năng và test tích hợp trên **launcher đã được jpackage tạo**.

### Lỗi do thiếu module nhìn như thế nào?

Nếu custom runtime không có `java.logging` nhưng ứng dụng cố dùng `Logger`, chương trình có thể thất bại khi cần nạp lớp với lỗi liên quan `NoClassDefFoundError` hoặc `ClassNotFoundException`. Với ứng dụng modular, thiếu module bắt buộc có thể gây lỗi **module resolution**, ví dụ `FindException`.

Không nên suy ra thiếu module chỉ từ một dòng message duy nhất. Hãy kiểm tra cả runtime module list, dependency declarations, classpath/module path, stack trace và JDK version tương ứng.

### Nhận biết build bằng JDK không tương thích

Một ứng dụng được compile bằng JDK mới hơn runtime đóng gói có thể lỗi `UnsupportedClassVersionError`. Ví dụ, nếu ứng dụng cần class-file version của JDK 25 nhưng runtime là Java 17 thì launcher không thể chạy các class đó.

Muốn bảo đảm target Java 17, dùng công cụ biên dịch phù hợp, chẳng hạn:

~~~bash
javac --release 17 -d classes AppMain.java
~~~

`--release 17` là chính sách compatibility của **mã Java được biên dịch**, không có nghĩa jlink/jpackage tự lấy Java 17 runtime. Hãy **chọn runtime image đúng version** và kiểm thử thực tế.

## 10. Kiểm tra runtime và ứng dụng sau khi đóng gói

Một checklist kỹ thuật đơn giản:

| Kiểm tra | Câu hỏi cần trả lời |
| --- | --- |
| Launcher mở được | `AutoDemo.exe`/launcher Linux/macOS có chạy trên máy sạch không? |
| Java version | Runtime thực tế trong app image là bản nào, có đáp ứng class-file version và API không? |
| Modules | Có đủ root modules, transitive deps, providers cho các tính năng đang dùng không? |
| Ứng dụng/resources | File JAR, config, tài nguyên, icon và native libs có được copy theo đúng layout không? |
| Mạng/TLS/locales | Có đủ certificate store, crypto providers, charset/locales và thư viện tương thích không? |
| Dung lượng | App image tự tạo và custom khác nhau bao nhiêu? Có xóa nhầm module thiết yếu không? |
| Bảo mật/patch | Đang dùng runtime có bản vá bảo mật và nguồn JDK đáng tin chưa? |
| Vòng đời phát hành | Khi JDK có bản vá, ai rebuild và phân phối lại app image? |

### Kiểm tra release metadata

Trên Windows:

~~~powershell
Get-Content .\dist\AutoDemo\runtime\release
Get-Content .\dist\CustomDemo\runtime\release
~~~

Tệp `release` cho phép nhìn version/modules của runtime. Kiểm tra metadata **không thay thế** việc thực thi app.

### Kiểm tra module của runtime tự tạo

Nếu không loại `bin/java`:

~~~powershell
.\custom-runtime\bin\java.exe --list-modules
~~~

Với app image tự tạo theo default `--strip-native-commands`, lệnh `runtime/bin/java` có thể **không có**, nên kiểm tra `release` hoặc dùng các công cụ JDK build để phân tích nội dung image. Không coi việc `java.exe` vắng mặt là bằng chứng app image không chạy được: launcher của jpackage vẫn có thể chạy ứng dụng bằng runtime đóng gói.

### Test máy đích

Đối với production, nên thử trên một máy/VM sạch **cùng OS và kiến trúc**, với tài khoản quyền hạn thấp phù hợp, không cài JDK toàn cục và không phụ thuộc PATH của máy developer.

Test cả:

- Khởi động launcher và các tham số `--java-options` nếu có.
- Các chức năng dùng modules ngoài `java.base`, chẳng hạn logging, HTTP, XML, desktop, database hoặc security providers.
- Trường hợp lỗi và log chẩn đoán hữu ích; kiểm tra native dependencies.
- Đọc/ghi cấu hình trong đường dẫn mà người dùng có quyền, không giả định được sửa file bên trong thư mục cài ứng dụng.
- Chương trình update/uninstall nếu sau này tạo native installer.

## 11. Chọn runtime có sẵn từ máy, CI hoặc artifact đã build

Runtime được cung cấp qua `--runtime-image` **không bắt buộc** phải được tạo trong cùng một lệnh build; bạn có thể dùng một image đã lưu từ pipeline đáng tin. Nhưng tính “có sẵn” không làm nó **tự tương thích**.

Trước khi đóng gói, xác minh:

1. **Nguồn JDK/runtime:** do vendor đáng tin hoặc pipeline được kiểm soát tạo, có checksum/signature/metadata phù hợp?
2. **OS/architecture:** runtime được tạo cho Windows x64, Linux x64, macOS ARM64… tương thích với máy build và gói đích chưa?
3. **Java version:** hỗ trợ bytecode, language/API của ứng dụng chưa?
4. **Các modules bắt buộc:** đủ modules tĩnh, service providers và modules động?
5. **Native libraries và resources:** có phụ thuộc filesystem, C library hoặc native packages của OS?
6. **Bản vá bảo mật:** runtime đã được cập nhật chưa? Việc mang runtime trong app image có thể khiến bản cũ còn tồn tại ở từng máy đích.
7. **Quyền và điều kiện phân phối:** đã xem giấy phép và quy định phân phối runtime của vendor/thư viện đi kèm chưa?
8. **Build có thể tái lập:** ghi rõ JDK version, module list, jlink options và nguồn artifact để phát hành lặp lại.

**Quan trọng:** runtime image đóng gói vào app không tự nhận các bản vá của JDK cài toàn cục trên máy người dùng. Khi JDK có bản vá bảo mật, bạn thường phải **build, kiểm thử và phân phối app image mới** dùng runtime đã cập nhật.

### Có thể dùng Java runtime version khác bản jpackage đang chạy?

Tài liệu Oracle cho phép cung cấp một runtime được tạo riêng, kể cả do một JDK khác tạo, miễn là cấu hình và target phù hợp. Đây không phải “mã chạy trên mọi phiên bản Java”:

- Bytecode của app phải được runtime đó hỗ trợ.
- Java APIs/modules của ứng dụng phải có mặt trong runtime.
- Launcher/native artifacts phải tương thích nền tảng, kiến trúc và yêu cầu JDK packaging tương ứng.
- Phải test lại nếu thay đổi JDK vendor, major version hoặc tùy chọn jlink.

Không nên lấy ví dụ JDK 11/JDK 14 lịch sử làm lệnh production mặc định. Đối với code mới, chọn **JDK còn được hỗ trợ và đang nhận bản vá** theo chính sách tổ chức.

## 12. Phân biệt --runtime-image với --app-image

Hai tùy chọn tên gần giống nhưng **đầu vào khác hẳn**:

| Option | Nhận gì? | Ý định |
| --- | --- | --- |
| `--runtime-image my-runtime` | Thư mục **runtime image** tạo trước đó | Đưa runtime riêng vào app image mới |
| `--app-image existing-app` | **Application image** đã có launcher, app và runtime | Dùng app image đã tạo để đóng installer hoặc thao tác hỗ trợ |
| `--type app-image` | Chỉ định **loại đầu ra** là app image | Build thư mục/bundle ứng dụng, không phải installer |

**Không kết hợp `--runtime-image` với `--app-image`**: tài liệu jpackage xác định hai lựa chọn này mutually exclusive. Nếu cần đổi runtime của một ứng dụng, hãy dùng `--runtime-image` khi **tạo app image ở bước đầu**, không trông đợi sửa runtime bằng cách truyền cả hai options ở bước tạo installer.

Quy trình điển hình có hai giai đoạn:

~~~bash
# Giai đoạn 1: tạo app image với runtime đã chọn.
jpackage --type app-image --name MyApp \
    --input input --main-jar app.jar --main-class AppMain \
    --runtime-image custom-runtime

# Giai đoạn 2: có thể tạo installer từ app image đã sẵn sàng,
# dùng định dạng và công cụ của đúng hệ điều hành.
jpackage --name MyApp --app-image MyApp --type msi
~~~

Lệnh `--type msi` là **ví dụ chỉ dành cho Windows**, có thể cần công cụ cài đặt/phần mềm bổ sung tương ứng. Không chạy trên Linux/macOS. Đây là các **mảnh lệnh minh họa workflow**; người build phải biết đường dẫn app image thực và tùy chọn ký gói/cài đặt.

## 13. Các lỗi phổ biến và cách khắc phục

| Hiểu nhầm hoặc lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “jpackage chỉ hỗ trợ runtime tự tạo.” | Khi không truyền `--runtime-image`, jpackage tự chạy jlink | Bắt đầu từ cách A nếu không có yêu cầu riêng |
| “Luôn phải chạy jlink thủ công trước.” | Không bắt buộc | Chỉ tự build runtime nếu muốn kiểm soát module/phiên bản |
| “--runtime-image nhận đường dẫn JAR.” | Đây là đường dẫn **thư mục runtime** | Dùng output của `jlink` hoặc runtime image hợp lệ |
| “Có --runtime-image thì --add-modules tự bổ sung missing modules.” | Runtime đã link; jpackage không rebuild nó | Sửa lệnh jlink tạo runtime, rồi build app image mới |
| “App image giống installer.” | `--type app-image` chỉ tạo folder/bundle | Dùng `--type` native phù hợp nếu cần installer |
| “jlink tự đóng gói toàn bộ app.” | jlink tạo Java runtime, không thay hết công việc jpackage | Kết hợp jlink + jpackage |
| “jdeps luôn phát hiện mọi dependency.” | Reflection/ServiceLoader/JNI có thể không hiện trong phân tích tĩnh | Thêm modules phù hợp, chạy test tích hợp |
| “Chỉ cần java.base cho mọi app.” | HTTP, logging, desktop, XML, DB, crypto… có modules riêng | Kiểm tra imports, runtime features và dependencies |
| “JDK 24 và JDK 26 tự chọn cùng providers.” | Từ JDK 25 jpackage không tự bind service providers | Kiểm tra `--bind-services` hoặc provider modules cụ thể |
| “Chỉ cần thêm --jlink-options mới, các defaults cũ chắc vẫn áp dụng.” | Tự cung cấp jlink-options thay cách lựa chọn mặc định | Chỉ định đầy đủ options muốn có |
| “Runtime Windows dùng được trên Linux.” | Native runtime và launcher phụ thuộc OS/architecture | Build/test trên từng nền tảng đích |
| “Runtime cũ cũng chạy bytecode Java mới.” | Có thể gặp `UnsupportedClassVersionError` | Compile target và runtime version tương thích |
| “App image tự cập nhật Java theo JDK hệ thống.” | Nó mang runtime riêng | Cập nhật, build lại và phát hành bản mới |
| “Mọi runtime đều có runtime/bin/java.” | jpackage mặc định có thể strip native commands | Chạy launcher; xem runtime/release |
| “Dùng --app-image và --runtime-image cùng lúc để đổi Java.” | Hai tùy chọn loại trừ nhau | Chọn runtime từ lúc tạo app image |
| “Đóng gói xong là không cần test.” | Thiếu modules/deps động có thể chỉ xuất hiện khi chạy nhánh hiếm | Test trên máy sạch và workflow quan trọng |

## 14. Chiến lược kiểm thử CI/CD

Một pipeline đáng tin có thể chia:

1. **Compile:** `javac --release 17` hoặc build tool với target phù hợp, chạy unit tests.
2. **Package JAR/modular artifacts:** đầu vào sạch, có manifest/main class hoặc module descriptor đúng.
3. **Analyze:** chạy `jdeps` và kiểm tra phụ thuộc reflection/providers ngoài tĩnh.
4. **Build runtime:** chọn jpackage implicit jlink hoặc custom jlink runtime; cố định JDK vendor/version.
5. **Build app image:** `jpackage --type app-image` trước, để có thể kiểm tra launcher và nội dung.
6. **Inspect:** kiểm tra app payload, runtime/release, JDK version/modules và kích thước.
7. **Smoke tests:** chạy launcher trên runner/VM đúng OS và architecture, không dựa vào JDK cài sẵn.
8. **Integration tests:** database, TLS/HTTP, file I/O, GUI (nếu có), providers và đường dẫn động.
9. **Native installer (nếu cần):** tạo `exe/msi`, `deb/rpm` hoặc `dmg/pkg` trên nền tảng phù hợp.
10. **Security/distribution:** ký gói, kiểm tra license, checksum, provenance và cập nhật runtime khi có bản vá.

Để so sánh kích thước hai app images, dùng công cụ filesystem của môi trường build. **Không nên xem runtime nhỏ nhất là tốt nhất** nếu phải loại các modules cần cho tính năng. Thước đo thành công là **tính đúng đắn, khả năng chạy trên máy đích, bảo mật, khả năng cập nhật và kích thước phù hợp**.

### Nếu phải giảm size

Thử theo thứ tự:

- Xác nhận modules app thực sự dùng qua `jdeps` và test runtime.
- Với ứng dụng modular, khai báo `requires` rõ ràng, tránh module root quá rộng.
- Với non-modular, cân nhắc custom runtime được quản lý thay vì toàn bộ default modules, nếu test đầy đủ.
- Dùng `jlink` options như `--strip-debug`, `--no-man-pages` và `--no-header-files` theo mục đích.
- Khi dùng JDK mới, tham khảo `jlink --help` cho các tùy chọn nén **còn hỗ trợ** (ví dụ cú pháp `--compress=zip-6` trên JDK 26). Tránh sao chép các giá trị `--compress=0/1/2` cũ vốn đang bị đánh dấu deprecated trong tài liệu JDK 26.
- Đo size và chạy smoke/integration tests sau mỗi thay đổi, đặc biệt khi xử lý native libraries, resources và service providers.

## 15. Bài tập thực hành

### Bài 1 — Nhận diện lựa chọn runtime

Lệnh:

~~~bash
jpackage --type app-image --name Hello \
    --input input --main-jar hello.jar --main-class HelloMain
~~~

**Câu hỏi:** runtime đến từ đâu?

**Đáp án:** không có `--runtime-image`, nên **jpackage tự gọi jlink** với tập module và các options hiện hành.

### Bài 2 — Runtime có sẵn

Lệnh:

~~~bash
jlink --add-modules java.base,java.logging --output my-runtime
jpackage --type app-image --name Hello \
    --input input --main-jar hello.jar --main-class HelloMain \
    --runtime-image my-runtime
~~~

**Câu hỏi:** nếu app sau đó cần `java.desktop` nhưng image không có, sửa ở đâu?

**Đáp án:** sửa lệnh **jlink** để thêm `java.desktop` và dependencies, tạo lại runtime rồi **đóng gói lại app image**. Không tin jpackage sẽ tự bổ sung module vào runtime đã được cung cấp.

### Bài 3 — Theo dõi output

Chạy ví dụ `AppMain.java` ở mục 6, tạo hai app images và khởi chạy từng launcher. Giải thích vì sao chúng cùng in:

~~~text
app-image OK
java.logging present=true
~~~

**Đáp án:** cả hai runtime đều chứa module `java.logging`; cách A chọn default module set đủ để chạy app non-modular, còn cách B đã chỉ định module này trong `jlink --add-modules`.

### Bài 4 — Dependency động

Một thư viện dùng `ServiceLoader.load(MyService.class)` nhưng runtime tối giản chỉ chứa consumer module, không có provider module.

**Câu hỏi:** tại sao build pass nhưng runtime không tìm được provider?

**Đáp án:** static `requires` chưa chắc kéo đủ các providers được chọn động. Cần thêm provider module hoặc dùng service binding thích hợp, rồi test đầy đủ trên app image đã tạo.

### Bài 5 — Kiểm tra phiên bản

Ứng dụng được biên dịch bằng `--release 21` nhưng runtime có sẵn trong `--runtime-image` là Java 17.

**Đáp án:** runtime 17 không thể chạy class-file/API yêu cầu Java 21; phải dùng runtime mới đủ khả năng hoặc build ứng dụng thật sự tương thích Java 17 rồi test.

### Bài 6 — Build cho Linux từ Windows?

Một nhóm chỉ có Windows runner, tạo runtime Windows và app image Windows rồi đổi tên thư mục thành bản Linux.

**Đáp án:** không hợp lệ. `jpackage` không hỗ trợ cross-platform packaging kiểu này; cần runner và runtime phù hợp nền tảng đích.

### Bài 7 — JDK 25 trở đi

Một app dựa trên dynamic service providers chạy đúng với app image được build bằng JDK 21 nhưng thất bại với runtime do jpackage JDK 26 tự tạo.

**Gợi ý:** kiểm tra **service bindings**; từ JDK 25, jpackage không thêm chúng theo mặc định. Xác minh providers cần thiết và cân nhắc `--jlink-options --bind-services` với các lựa chọn mặc định khác, hoặc cung cấp custom runtime đã được jlink/bind đúng.

### Bài 8 — Không cần installer

Bạn muốn đóng gói app để test trên CI mà không cần cấu hình trình cài đặt native.

**Đáp án:** ưu tiên `jpackage --type app-image`; sau khi test launcher mới tạo installer nếu dự án thực sự cần cài đặt.

## 16. Checklist trước khi phát hành

1. App là **modular** hay **non-modular**? Đã chọn `--module` hoặc `--main-jar` đúng trường hợp chưa?
2. `--input` có đủ JAR/config/resources và `--main-jar` có path tương đối đúng không?
3. Muốn **jpackage tự chạy jlink** hay có **runtime image tự quản lý**?
4. Nếu tự tạo runtime, danh sách `--add-modules` đã bao phủ các tính năng và dependencies động chưa?
5. Nếu dùng `--jlink-options`, đã giữ các strip options mong muốn thay vì giả định mặc định chưa?
6. Với JDK 25+, service providers của app có cần `--bind-services` hoặc modules explicit không?
7. Runtime image đã đúng JDK version/vendor, kiến trúc, OS và mức vá bảo mật chưa?
8. Có phân biệt runtime image với app image và tránh kết hợp `--runtime-image` với `--app-image` chưa?
9. Đã chạy **launcher** trên máy sạch cùng nền tảng, thay vì chỉ chạy `java -cp` trên máy build chưa?
10. Đã kiểm tra module `java.logging`/desktop/HTTP/XML/TLS providers theo use case, không chỉ `java.base`?
11. App image có thể phân phối bằng folder/bundle hay cần installer native, ký số, notarization?
12. Đã có kế hoạch rebuild ứng dụng khi **runtime cần bản vá bảo mật** và ghi rõ provenance chưa?

## 17. Tài liệu chính thức, còn áp dụng

- [Oracle Java 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html): `--type app-image`, `--runtime-image`, `--jlink-options`, `--add-modules`, cách đóng gói modular và non-modular.
- [Oracle Java 26 — Packaging Overview](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html): nguồn runtime mặc định, tập module, sự thay đổi service bindings từ JDK 25.
- [Oracle Java 26 — Image and Runtime Modifications](https://docs.oracle.com/en/java/javase/26/jpackage/image-and-runtime-modifications.html): cung cấp custom runtime qua `--runtime-image` và phân biệt với `--app-image`.
- [Oracle Java 26 — The jlink Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html): `--add-modules`, `--module-path`, `--bind-services`, module dependencies và options nén còn hỗ trợ.
- [Oracle Java 26 — The jdeps Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html): phân tích dependency tĩnh và `--print-module-deps`.
- [Oracle JDK 16 Release Notes](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html): jpackage được chuẩn hóa từ JDK 16 sau thời kỳ incubating JDK 14–15.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): cơ sở công cụ jpackage chính thức.
- [Oracle Java 17 — jpackage Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): xác nhận cú pháp `--runtime-image` còn áp dụng trên Java 17+.
