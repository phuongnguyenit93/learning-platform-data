# Đầu vào ứng dụng mô-đun và ứng dụng theo class path khi đóng gói bằng jpackage

## Mục tiêu

`jpackage` là công cụ của JDK dùng để tạo **application image** hoặc gói cài đặt ứng dụng Java cho hệ điều hành đích. Để đóng gói thành công, trước hết phải biết ứng dụng khởi chạy theo **class path** hay theo **Java Platform Module System (JPMS)**. Hai kiểu đều có thể sử dụng tệp `.jar`, nhưng **cách chỉ định đầu vào, entry point và phụ thuộc không giống nhau**.

Sau bài này, bạn có thể:

- Nhận diện class-path application không có `module-info.class` và explicit named module có `module-info.class`.
- Sử dụng đúng `--input`, `--main-jar`, `--main-class` cho ứng dụng non-modular; `--module-path` và `--module` cho ứng dụng modular.
- Chuẩn bị JAR hoặc module từ mã Java trước khi đóng gói; chạy thử bằng `java -jar` hoặc `java --module`.
- Hiểu vì sao `--main-jar` và `--module` **không thể cùng được chỉ định** làm entry point; khi nào `--module-path` vẫn có tác dụng với ứng dụng class path.
- Phân biệt thư mục nguồn `--input`, thư mục kết quả `--dest` và runtime Java do `jlink` tạo.
- Kiểm tra sự có mặt và khả năng tải các thư viện phụ thuộc, resources, module providers, JNI.
- Tạo và chạy được hai ví dụ application image trên Java hiện đại.

**Phiên bản:** `jpackage` được thử nghiệm ở Java 14 (JEP 343) và trở thành công cụ chính thức, production-ready từ **Java 16** (JEP 392). Nội dung dùng **cú pháp hiện hành của Java 17+**, không dùng module incubator cũ hay `--enable-preview`. Ví dụ đã được biên dịch với `javac --release 17`, đóng gói và chạy launcher bằng `jpackage` của JDK 24 trên Windows. Tài liệu lựa chọn option cũng đã đối chiếu Oracle JDK 25.

## 1. Đầu vào jpackage thực sự là gì?

`jpackage` thường **không nhận một tệp `.java` rồi tự xây toàn bộ project**. Trước khi đóng gói, bạn đã biên dịch code bằng `javac` hoặc build tool (Maven/Gradle), tạo JAR, modular JAR hoặc cây modules đã biên dịch.

~~~text
Mã nguồn Java
   |
   v
javac / Maven / Gradle
   |
   +-- executable classpath JAR
   |       |
   |       v
   |  --input <directory> --main-jar <jar>
   |       |
   |       v
   |    jpackage
   |
   +-- explicit named module
           |
           v
      --module-path <modules> --module <name[/Main]>
           |
           v
         jpackage
              |
              v
    Application image (launcher + Java runtime + app)
              |
              v
      Native installer (nếu cần)
~~~

Dùng `--type app-image` trước tiên rất hữu ích vì bạn có thể **mở launcher vừa tạo và kiểm thử** mà không cần cài native installer. Các gói như `exe`/`msi` (Windows), `dmg`/`pkg` (macOS), `deb`/`rpm` (Linux) phụ thuộc hệ điều hành. **jpackage không cross-build native installer cho một hệ điều hành khác**: phải build và kiểm thử trên nền tảng phù hợp.

## 2. Phân biệt class path và module path

### 2.1. Class-path application (non-modular)

Một JAR ứng dụng không có `module-info.class` thường được chạy qua `java -jar app.jar` hoặc `java -cp ... pkg.Main`. Những class này tham gia **unnamed module** khi được tải từ class path. Cách đóng gói cơ bản:

~~~bash
jpackage --type app-image \
  --name ClassicHello \
  --input input/classic \
  --main-jar classic.jar \
  --dest images
~~~

Giải thích:

- `--input input/classic` chỉ **thư mục chứa payload** ứng dụng cần đóng gói.
- `--main-jar classic.jar` chỉ JAR chính, được xác định **tương đối với thư mục `--input`**.
- `--main-class pkg.Main` chỉ cần khi entry point không thể lấy từ `Main-Class` trong manifest của JAR; cũng có thể khai báo tường minh khi muốn.
- `--dest images` là nơi **đặt kết quả**, không phải nơi lấy JAR đầu vào.
- `--name ClassicHello` là tên ứng dụng/launcher, không phải tên Java module.

Nếu JAR nằm ở `input/classic/lib/classic.jar`, giá trị đúng là `--main-jar lib/classic.jar`. Không đưa một đường dẫn ngoài `--input` làm main JAR rồi kỳ vọng công cụ tự copy JAR đó vào image.

### 2.2. Modular application (explicit named module)

Ứng dụng mô-đun thực sự có file `module-info.java` được biên dịch thành `module-info.class`. Module có **tên riêng** và có thể khai báo phụ thuộc bằng `requires`, phân quyền truy cập bằng `exports/opens`.

~~~bash
jpackage --type app-image \
  --name ModuleHello \
  --module-path mods \
  --module demo.mod/demo.mod.Main \
  --dest images
~~~

- `--module-path mods` chỉ nơi chứa các **named modules** (ví dụ modular JARs).
- `--module demo.mod/demo.mod.Main` xác định **main module** `demo.mod` và **main class** `demo.mod.Main`.
- Nếu main module đã chứa metadata khai báo main class, có thể dùng `--module demo.mod`.
- Không khai báo `--main-jar` cho cùng entry point; ứng dụng đang dùng **module launcher**.

**Mấu chốt:** JAR không tự trở thành explicit module chỉ vì đặt vào `mods` hoặc đặt trên module path. Cần kiểm tra descriptor thật sự, đặc biệt khi thư viện là automatic module.

### 2.3. Bảng so sánh

| Nội dung | Ứng dụng class path | Ứng dụng modular |
|---|---|---|
| Entry point | Main JAR | Main named module |
| Tùy chọn quyết định kiểu khởi chạy | `--main-jar` | `--module` |
| Đầu vào chính | `--input` | `--module-path` |
| Main class | Manifest `Main-Class` hoặc `--main-class` | `--module name/class` hoặc main class trong module metadata |
| Kiểm tra trước khi đóng gói | `java -jar app.jar` | `java --module-path mods --module name/class` |
| Descriptor module | Không bắt buộc | Có `module-info.class` cho explicit module |
| Dependencies | Class path và các JAR cần thiết | `requires`, module graph và named modules |
| Kết quả cuối | App image/native installer | App image/native installer |

**Không đánh giá class path là lỗi thời.** `jpackage` hiện vẫn hỗ trợ chính thức cả hai chế độ. Bạn nên chọn dựa trên cấu trúc ứng dụng và thư viện đang sử dụng.

## 3. Quy tắc lựa chọn option

| Option | Ý nghĩa | Cảnh báo |
|---|---|---|
| `--input` / `-i` | Thư mục các tệp ứng dụng được copy vào image | Mọi file trong thư mục đầu vào được đóng gói; loại bớt file bí mật/không cần |
| `--main-jar` | JAR chứa main class của ứng dụng non-modular | Đường dẫn tương đối so với `--input` |
| `--main-class` | Tên class khởi chạy | Với `jpackage`, chỉ dùng khi có `--main-jar` |
| `--module-path` / `-p` | Đường dẫn tìm các modules cho resolution/linking | Có thể gồm các thư mục hoặc modular JARs; dấu ngăn cách đường dẫn tùy OS |
| `--module` / `-m` | Main module, kèm main class tùy chọn sau dấu `/` | Không dùng đồng thời `--main-jar` |
| `--name` | Tên app/launcher | Không phải module name |
| `--type app-image` | Tạo app image trước khi tạo installer | Dễ test launcher và runtime |
| `--dest` | Thư mục kết quả | Khác `--input` |
| `--add-modules` | Bổ sung module cho runtime do jlink tạo | Chỉ thêm khi có yêu cầu thực |
| `--runtime-image` | Dùng runtime image được tạo từ trước | Bạn phải bảo đảm nó đủ module, đúng OS/CPU |
| `--java-options` | Truyền options cho JVM khi launcher chạy | Khác `--arguments` của app |
| `--arguments` | Đối số mặc định cho `main(String[] args)` | Có thể được thay bằng đối số người dùng |
| `--verbose` | Hiển thị log đóng gói chi tiết | Hữu ích cho chẩn đoán lỗi |

**Hai quy tắc thường bị nhầm:**

1. **`--module` và `--main-jar` loại trừ nhau.** Không thể dùng cả hai trong cùng lệnh để chọn hai ứng dụng chính.
2. **`--module-path` không chỉ có ý nghĩa khi dùng `--module`.** Một ứng dụng có `--main-jar` vẫn có thể chỉ định module path để hỗ trợ việc `jlink` tạo runtime; điều đó **không biến ứng dụng thành modular launcher**.

Tương tự, `--input` là nơi lấy payload; dùng `--input` không đồng nghĩa khai báo một module. Với modular launcher, tên module chính vẫn do `--module` quyết định.

## 4. Thực hành A: tạo JAR class path và đóng gói

### Bước A1. Viết mã nguồn

Tệp **`src-classic/demo/classic/Main.java`**:

~~~java
package demo.classic;

public final class Main {
    public static void main(String[] args) {
        System.out.println("launch=classpath");
        System.out.println("message=hello from JAR");
    }
}
~~~

Đây là chương trình độc lập tối giản. **Không có `module-info.java`**.

### Bước A2. Biên dịch và tạo executable JAR

Các lệnh sau sử dụng cú pháp terminal **Bash** trên Linux/macOS. Trên Windows, tạo thư mục bằng PowerShell rồi dùng lệnh `javac`/`jar` tương ứng; dấu `\` ở cuối dòng trong Bash không được dùng làm line continuation của PowerShell.

~~~bash
mkdir -p build/classic-classes input/classic images

javac --release 17 -encoding UTF-8 \
  -d build/classic-classes \
  src-classic/demo/classic/Main.java

jar --create \
  --file input/classic/classic.jar \
  --main-class demo.classic.Main \
  -C build/classic-classes .
~~~

Tùy chọn `--main-class` ở **lệnh `jar`** ghi `Main-Class` vào manifest. Nó không phải một lệnh khởi chạy ứng dụng. Hãy thử JAR:

~~~bash
java -jar input/classic/classic.jar
~~~

Output:

~~~text
launch=classpath
message=hello from JAR
~~~

### Bước A3. Đóng gói app image

~~~bash
jpackage --type app-image \
  --name ClassicHello \
  --input input/classic \
  --main-jar classic.jar \
  --dest images
~~~

Vì JAR có `Main-Class` trong manifest, không cần `--main-class` ở `jpackage`. Nếu JAR không có thông tin đó, khai báo tường minh:

~~~bash
jpackage --type app-image \
  --name ClassicHello \
  --input input/classic \
  --main-jar classic.jar \
  --main-class demo.classic.Main \
  --dest another-output
~~~

Hai lệnh trên là **hai phương án thay thế**, không chạy đè vào cùng output. Nếu đã có app image cùng tên trong `--dest`, công cụ có thể từ chối vì đích đã tồn tại.

**Kiểm tra launcher đã đóng gói** theo nền tảng:

~~~text
Windows: images\ClassicHello\ClassicHello.exe
Linux:   images/ClassicHello/bin/ClassicHello
macOS:   images/ClassicHello.app/Contents/MacOS/ClassicHello
~~~

Ứng dụng console trên Windows cần thêm `--win-console` vào lệnh `jpackage` để xem stdout tương tác qua console. `--win-console` **chỉ dành cho Windows**; không dùng tùy chọn này trên Linux/macOS.

**Thử nghiệm thực tế:** Sau khi dùng `--win-console` trên Windows, launcher từ image in đúng hai dòng `launch=classpath` và `message=hello from JAR` như bản `java -jar` trước đóng gói.

## 5. Thực hành B: tạo explicit module và đóng gói

### Bước B1. Chuẩn bị hai tệp

Cây mã nguồn:

~~~text
src-mod/
    module-info.java
    demo/
        mod/
            Main.java
~~~

Tệp **`src-mod/module-info.java`**:

~~~java
module demo.mod {
}
~~~

Tệp **`src-mod/demo/mod/Main.java`**:

~~~java
package demo.mod;

public final class Main {
    public static void main(String[] args) {
        System.out.println("launch=module");
        System.out.println("message=hello from module");
    }
}
~~~

`demo.mod` là tên **named module**. Không cần viết `requires java.base;` vì mọi module đều đọc `java.base` ngầm định. Ví dụ không có public API cần export, vì vậy module descriptor rỗng là hợp lệ.

### Bước B2. Biên dịch và tạo modular JAR

~~~bash
mkdir -p build/mod-classes mods images

javac --release 17 -encoding UTF-8 \
  -d build/mod-classes \
  src-mod/module-info.java \
  src-mod/demo/mod/Main.java

jar --create \
  --file mods/demo.mod.jar \
  --main-class demo.mod.Main \
  -C build/mod-classes .
~~~

JAR đã tạo chứa **`module-info.class`** và metadata main class. Kiểm tra bằng:

~~~bash
jar --describe-module --file mods/demo.mod.jar
jar --list --file mods/demo.mod.jar
~~~

`jar --describe-module` hiển thị thông tin module, còn `jar --list` cho biết các class có trong tệp. Một JAR có thể chỉ là **automatic module** dù công cụ hiển thị tên module; vì vậy phải xem có **descriptor thật sự** hay không.

Thử chạy từ module path:

~~~bash
java --module-path mods \
  --module demo.mod/demo.mod.Main
~~~

Output:

~~~text
launch=module
message=hello from module
~~~

### Bước B3. Đóng gói app image cho module

~~~bash
jpackage --type app-image \
  --name ModuleHello \
  --module-path mods \
  --module demo.mod/demo.mod.Main \
  --dest images
~~~

Nếu modular JAR đã ghi main class, có thể dùng `--module demo.mod`; tuy nhiên cú pháp `module/mainClass` tường minh thường rõ ràng hơn khi học hoặc debug.

Không truyền `--main-jar` hoặc `--main-class` riêng cho chế độ modular. Nếu muốn thay main class, cung cấp nó sau dấu `/` trong `--module`.

**Thử nghiệm thực tế:** Trên Windows, sau khi tạo image với `--win-console`, launcher `ModuleHello.exe` in đúng hai dòng `launch=module` và `message=hello from module`.

## 6. Phụ thuộc ứng dụng và mô-đun: cần đưa đủ dữ liệu vào image

### 6.1. Ứng dụng class path có nhiều JARs

Ví dụ một ứng dụng phụ thuộc `helper.jar`:

~~~text
input/classic/
    classic.jar
    lib/
        helper.jar
~~~

`jpackage --input input/classic` sẽ **copy nội dung thư mục input** vào app image. Tuy nhiên, **việc một JAR xuất hiện trong image chưa chứng minh JVM launcher tải được nó**. Bạn vẫn phải đảm bảo classpath, manifest `Class-Path`, cấu hình launcher hoặc build layout thực tế giúp code tìm được `helper.jar`.

Với fat/uber JAR hoặc Spring Boot-style JAR có nested JARs và custom loader, đừng suy đoán `jpackage` hiểu mọi cấu trúc đó như executable JAR phẳng. Cần kiểm tra điểm vào của JAR, launcher configuration và test **launcher sau đóng gói**.

### 6.2. Ứng dụng modular có nhiều named modules

Ví dụ:

~~~text
mods/
    demo.mod.jar
    demo.core.jar
    vendor.api.jar
~~~

Trong `module-info.java`, một module có thể ghi `requires demo.core;`. `jpackage` cùng `jlink` phải **resolve đủ module graph** từ các module paths được cung cấp. Nếu thiếu một dependency, có thể gặp `Module ... not found`, duplicate modules, split packages hoặc các lỗi liên quan tới `exports`/`opens`.

**Automatic module không giống explicit module.** Một JAR thông thường đặt trên module path có thể được suy ra thành automatic module, nhưng `jlink` **không link automatic modules như explicit named modules**. Khi gặp lỗi này, hãy cân nhắc modularize dependency, thay dependency hoặc lựa chọn classpath deployment thích hợp, thay vì chỉ đổi tên thư mục.

### 6.3. Runtime image do jpackage tạo

Nếu không truyền `--runtime-image`, `jpackage` dùng **`jlink`** để tạo runtime Java đính kèm:

- Với **modular app**, main module và các module dependencies được liên kết theo module graph.
- Với **non-modular app**, công cụ chọn tập JDK modules mặc định phù hợp với class-path launcher theo quy tắc của JDK.
- Khi ứng dụng tải động modules, class bằng reflection, service providers hoặc JNI, tập runtime tự suy ra có thể **chưa đủ**; cân nhắc `--add-modules`/`--jlink-options` và kiểm thử khởi chạy thật.

Ví dụ bổ sung module:

~~~bash
jpackage --type app-image \
  --name ClassicHello \
  --input input/classic \
  --main-jar classic.jar \
  --add-modules java.logging \
  --dest with-logging
~~~

Đây là **minh họa**, không phải yêu cầu cho Hello World. Chỉ bổ sung `java.logging` nếu ứng dụng thật cần module đó.

Một cấu hình khác có thể dùng runtime tự tạo:

~~~bash
jpackage --type app-image \
  --name ModuleHello \
  --module-path mods \
  --module demo.mod/demo.mod.Main \
  --runtime-image path/to/runtime-image \
  --dest custom-runtime-image
~~~

`path/to/runtime-image` là đường dẫn minh họa tới **Java runtime image đã được chuẩn bị đúng bằng jlink**, không phải bất kỳ thư mục nào có tệp `java.exe`. Khi cung cấp runtime sẵn, người đóng gói chịu trách nhiệm về danh sách module, native libraries, kiến trúc và OS của nó.

**Lưu ý phiên bản còn áp dụng:** Từ **JDK 25**, `jpackage` **không tự thêm service bindings** khi tạo runtime theo mặc định như trước đó. Nếu ứng dụng dựa vào providers qua module services, phải kiểm tra image và cân nhắc `--jlink-options --bind-services` theo hướng dẫn Oracle. Khi tự chỉ định `--jlink-options`, hãy đối chiếu các tùy chọn mặc định khác của `jpackage`; thay đổi này có thể ảnh hưởng dependency closure khi nâng JDK.

## 7. Những điều không nên nhầm

| Nhầm lẫn | Vì sao không đúng | Cách làm đúng |
|---|---|---|
| Có đuôi `.jar` thì luôn là module | Classpath và modular đều dùng JAR | Kiểm tra `module-info.class` và cách launch |
| Chỉ chuyển JAR sang thư mục `mods` là thành explicit module | Descriptor có thể không tồn tại | Modularize source và biên dịch `module-info.java` |
| `--input` là nơi xuất gói | `--input` chỉ thư mục payload | Dùng `--dest` để chọn output |
| `--main-jar` nhận đường dẫn tùy ý ngoài input | JAR chính phải được chỉ theo vị trí tương đối trong input | Sắp xếp thư mục và cung cấp tên/path đúng |
| Dùng đồng thời `--module` và `--main-jar` | Hai entry point loại trừ nhau | Chọn một chế độ |
| Dùng `--main-class` cho module mà không có main JAR | `jpackage` giới hạn option này cho `--main-jar` | Dùng `--module module/class` |
| Có `--module-path` nghĩa là launcher chắc chắn modular | Module path có thể phục vụ runtime linking cho non-modular app | Xem `--main-jar` hay `--module` |
| `--input` copy JAR phụ thì JVM chắc chắn load được | Payload copy và classpath resolution là hai việc khác | Kiểm tra classpath và chạy launcher đóng gói |
| JAR tự động có tên module thì jlink chắc chắn xử lý | Automatic module không tương đương explicit module | Kiểm tra descriptor/module graph |
| Build thành công nghĩa là ứng dụng chạy được | Có thể lỗi runtime modules, JNI, service/resource | Khởi chạy app image thật |
| Có thể tạo installer Windows trên Linux | Native packages là platform-specific | Build trên OS đích |
| `--win-console` dùng được trên mọi OS | Option chỉ có trên Windows | Chỉ thêm trên Windows |
| Mọi bản JDK có cùng tập runtime modules | Defaults và service binding có thể thay đổi | Đối chiếu docs theo JDK và test package |
| Một file trông giống resource ứng dụng đều an toàn để copy | Input có thể chứa secrets hoặc file tạm | Chỉ đưa artifact thực sự cần phân phối |

## 8. Quy trình kiểm tra và gỡ lỗi

### Trước khi đóng gói

1. Chạy `java -version`, `javac -version`, `jpackage --version` để nắm toolchain.
2. Xác định app đang launch qua **`java -jar` hay `java --module`**.
3. Với class path, kiểm tra **`--input` chứa JAR chính** và manifest `Main-Class` hoặc `--main-class`.
4. Với modular app, kiểm tra **`module-info.class`**, module name, `--module-path` và quan hệ `requires`.
5. Kiểm tra dependency JARs, native libraries, resource files và cấu hình cần thiết.

### Khi đóng gói

1. Chọn đúng một trong **`--main-jar`** và **`--module`**.
2. Dùng `--type app-image` trước để dễ chẩn đoán.
3. Chọn `--dest` riêng; không đưa artifact tạm hoặc mật khẩu vào `--input`.
4. Nếu có lỗi, thêm `--verbose`, đọc đúng thông báo về main class, JAR, module, runtime hoặc công cụ OS.
5. Không trộn ví dụ dùng Bash `\` để nối dòng với PowerShell; trên Windows dùng dòng lệnh đơn hoặc backtick PowerShell.

### Sau khi đóng gói

1. Mở launcher thực tế từ image, không chỉ chạy lại JAR trong thư mục build.
2. Kiểm tra mọi chức năng cần thư viện bên ngoài, resources, JNI và module service providers.
3. Test trên OS/architecture sẽ phân phối; native installer có thể cần thêm công cụ hệ thống và signing.
4. So sánh kết quả trước và sau đóng gói. Nếu chỉ main class chạy mà chức năng khác lỗi, kiểm tra dependency closure.
5. Đưa một bước launch packaged image vào CI cho từng hệ điều hành được hỗ trợ nếu dự án có yêu cầu phát hành thường xuyên.

**Ví dụ lỗi và hướng xử lý:**

- **Main JAR not found:** xem tệp nằm ở đâu bên trong `--input` và sửa `--main-jar` thành đường dẫn tương đối đúng.
- **Main class not found:** xem manifest/JAR contents, kiểm tra tên package và lệnh chạy bằng `java -jar`.
- **Module not found / resolution failure:** kiểm tra module path, tên module/descriptor và `requires`; thử `java --module-path ... --module ...` trước.
- **NoClassDefFoundError khi chạy launcher:** JAR thư viện có thể chưa được đưa vào classpath/package đúng cách.
- **Thiếu module/provider sau nâng JDK:** kiểm tra `--add-modules`, `--jlink-options` và thay đổi service bindings của bản JDK.
- **Không thấy stdout trên Windows:** với ứng dụng console, xây launcher bằng `--win-console`.

## 9. Tự luyện tập

**Câu 1.** `app.jar` không có `module-info.class`, manifest có `Main-Class: com.example.Main`. Nên chọn cặp option chính nào?

**Đáp án:** `--input <directory> --main-jar app.jar`. Không bắt buộc thêm `--main-class` nếu manifest đúng.

**Câu 2.** Một modular JAR `org.demo.app.jar` chứa descriptor module `org.demo.app` và main class `org.demo.Main`. Chọn đầu vào nào?

**Đáp án:** `--module-path <directory-containing-jar> --module org.demo.app/org.demo.Main`.

**Câu 3.** Tại sao `--input jars --main-jar ../outside.jar` không phải cách khai báo nên dùng?

**Đáp án:** Main JAR phải nằm trong payload đầu vào và được tham chiếu tương đối so với `--input`. Hãy đặt JAR trong thư mục đầu vào rồi ghi đúng path bên trong.

**Câu 4.** Một lệnh chứa cả `--main-jar app.jar` và `--module org.demo.app`, có hợp lệ không?

**Đáp án:** Không. Chúng là hai entry point loại trừ nhau; chọn class path hoặc modular launcher.

**Câu 5.** Chỉ có `Automatic-Module-Name` trong manifest đã đủ để `jlink` coi JAR là explicit named module?

**Đáp án:** Không. Automatic module không có descriptor thật sự và không tương đương explicit module dùng cho module linking.

**Câu 6.** Vì sao vẫn cần chạy packaged launcher sau khi `jpackage` trả thành công?

**Đáp án:** Vì artifact có thể được tạo nhưng không load được dependency, resource hoặc runtime module. Thành công của lệnh tạo image không thay cho kiểm thử ứng dụng đã đóng gói.

**Câu 7.** Một chương trình non-modular dùng reflection để tải provider. Sau khi nâng toolchain lên JDK 25, provider không thấy trong runtime. Nên kiểm tra gì?

**Đáp án:** Kiểm tra module/provider có trong image không, tập modules được jlink tạo, và thay đổi `jpackage` service bindings; cân nhắc thêm modules hoặc `--bind-services` khi cần theo hướng dẫn JDK tương ứng.

## Tài liệu chính thức

- [Oracle Java 25 — Packaging Tool: Basic Packaging](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html): quy trình cơ bản cho class path và modular application.
- [Oracle Java 25 — jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): options, ràng buộc và cú pháp.
- [Oracle Java 25 — Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): application image, runtime `jlink`, phụ thuộc, platform và service bindings.
- [Oracle Java 17 — jpackage Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): cú pháp trong JDK 17.
- [Oracle Java 25 — java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `java -jar`, `java --module`, class path và module path.
- [Oracle Java 25 — jar Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html): tạo JAR, `--main-class`, `--describe-module`.
- [Oracle Java 25 — jlink Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jlink.html): tạo runtime image.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): mốc tính năng chính thức Java 16.
- [Oracle Java 16 Release Notes](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html): phân biệt mốc incubator Java 14 với production-ready Java 16.
- [OpenJDK JEP 261 — Module System](https://openjdk.org/jeps/261): nền tảng module path và Java modules.

**Ghi nhớ:** Đầu tiên hãy xác định **entry point**: class path dùng **`--input` + `--main-jar`**, còn explicit named module dùng **`--module-path` + `--module`**. Không dùng cả `--module` và `--main-jar`. Sau khi chuẩn bị đúng đầu vào, luôn biên dịch, chạy trực tiếp, tạo `--type app-image` và **chạy launcher từ image** để kiểm tra đầy đủ tính tương thích.