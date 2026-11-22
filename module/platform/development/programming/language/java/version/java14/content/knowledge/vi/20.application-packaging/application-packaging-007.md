# Phân biệt đóng gói ứng dụng với việc biên dịch mã Java thành mã máy

## Mục tiêu bài học

Khi triển khai Java, các cụm từ **“đóng gói thành EXE”**, **“build JAR”**, **“compile Java”** và **“tạo native executable”** rất dễ bị dùng lẫn. Chúng mô tả **những thao tác khác nhau** trong chu trình phát triển và phân phối phần mềm. Đặc biệt, `jpackage` có thể tạo ứng dụng có trình khởi chạy `.exe` trên Windows, nhưng điều đó **không có nghĩa mã Java của ứng dụng đã được biên dịch trước thành mã máy của CPU**.

Sau bài này, bạn có thể:

1. Phân biệt **biên dịch Java source sang bytecode**, **đóng gói lớp/thư viện thành JAR**, **tạo application image/bộ cài bằng `jpackage`**, và **biên dịch ahead-of-time (AOT) thành native executable**.
2. Giải thích vai trò của `javac`, `jar`, `java`, JVM/JIT, `jlink`, `jpackage` và GraalVM `native-image` mà không nhầm tên công cụ với kết quả đầu ra.
3. Biết vì sao có launcher nền tảng riêng và Java runtime đi kèm **không biến bytecode ứng dụng thành mã máy sẵn có trong một file độc lập**.
4. Xây dựng một ví dụ Java 17+ bằng `javac` và `jar`, chạy bằng `java -jar`, rồi tạo application image với `jpackage` để kiểm chứng.
5. Biết trường hợp nào nên chọn phân phối JAR, bộ ứng dụng đóng gói runtime, installer hệ điều hành hoặc native-image AOT.
6. Nhận diện các giới hạn về hệ điều hành, module, phụ thuộc, bảo mật, khả năng tương thích và hiệu năng khi đóng gói.

**Phạm vi hiện hành:** `jpackage` là công cụ chuẩn của JDK, ổn định từ **Java 16** và tiếp tục được duy trì trong các JDK hiện đại. Các bước ví dụ dùng **JDK 17 trở lên**; không sử dụng `jpackage` ở trạng thái incubator, lệnh preview hoặc cơ chế Java đã lỗi thời. Khái niệm GraalVM Native Image được trình bày theo tài liệu hiện hành và chỉ là **lựa chọn bổ sung**, không được giả định có sẵn trong mọi JDK.

## 1. Bốn thao tác rất khác nhau

| Hoạt động | Công cụ thường dùng | Đầu vào | Đầu ra chính | Đã chuyển code Java thành mã máy trước khi chạy? |
| --- | --- | --- | --- | --- |
| Biên dịch nguồn Java | `javac` | Tệp `.java` | Bytecode trong `.class` | **Chưa**; `.class` là bytecode cho JVM |
| Gom lớp và tài nguyên | `jar`, Maven/Gradle | `.class`, resource, thư viện | File `.jar` | **Chưa**; JAR là định dạng lưu trữ, không phải mã máy ứng dụng |
| Đóng gói để phân phối | `jpackage` | JAR/module và runtime image | Application image, launcher, installer theo OS | **Không** biên dịch ứng dụng thành native machine code; có native launcher và runtime |
| Biên dịch AOT sang native | GraalVM `native-image` | Bytecode, metadata, thư viện | Native executable cho OS/CPU đích | **Có**, phần code cần thiết được biên dịch thành executable trước khi chạy |

Đây là sự khác biệt quan trọng nhất:

- **`javac`** là compiler Java thông thường. Nó tạo bytecode `.class`, có thể chạy trên JVM tương thích với target bytecode.
- **`jar`** chỉ tổ chức nhiều file vào một archive (về định dạng dựa trên ZIP) cùng manifest/metadata. Việc cho JAR một `Main-Class` khiến `java -jar` biết điểm vào, **không đổi bản chất bytecode**.
- **`jpackage`** tạo **bộ phân phối ứng dụng**: launcher hợp với OS, các file ứng dụng, một runtime Java được tạo/cung cấp và tài nguyên liên quan. Có file native launcher nhưng lớp Java trong ứng dụng vẫn chạy trên JVM đi kèm.
- **`native-image`** của GraalVM là công cụ **biên dịch AOT**; nó phân tích bytecode và tạo binary chạy trực tiếp theo môi trường OS/CPU mục tiêu, sử dụng các thành phần runtime đã đưa vào binary, **không cần khởi động một JVM Java thông thường ở máy đích**. Nó có các giới hạn và yêu cầu cấu hình riêng, đặc biệt với reflection, dynamic proxies, JNI và resource.

Dùng đúng danh từ giúp nhóm phát triển tránh cam kết sai cho người dùng cuối, ví dụ “ứng dụng này hoàn toàn không cần JVM” khi thực tế chỉ là bộ cài đã **đóng kèm JVM**.

## 2. Luồng xử lý từ .java đến người dùng cuối

```text
                Mã nguồn HelloApp.java
                        |
                        v
                javac --release 17
                        |
                        v
                  HelloApp.class
                 (Java bytecode)
                        |
            +-----------+------------------+
            |                              |
            v                              v
        java -cp ...                  jar --create ...
       (JVM chạy bytecode)                 |
                                           v
                                      hello-app.jar
                                           |
                           +---------------+-------------------+
                           |                                   |
                           v                                   v
                       java -jar                           jpackage
                           |                                   |
                           v                                   v
                JVM nạp và chạy bytecode              app image / installer
                (có interpreter/JIT)                  + launcher hệ điều hành
                           |                          + JAR chứa bytecode
                           |                          + runtime Java đi kèm
                           v                                   |
                  mã máy ở runtime                             v
                                                    chạy launcher -> JVM kèm theo
                                                         nạp bytecode/JIT

               NHÁNH RIÊNG: hello-app.jar
                           |
                           v
                   GraalVM native-image
                   (phân tích và AOT compile)
                           |
                           v
                   Native executable
                   cho OS/CPU đích
```

`jpackage` và `native-image` đều có thể mang lại một file người dùng nhấp để mở, nhưng **cơ chế thực thi** khác nhau. Chỉ nhìn phần mở rộng `.exe`, icon hay tên tệp không đủ để xác định ứng dụng đã được AOT compile.

### Bytecode và machine code khác nhau thế nào?

Bytecode là lệnh trung gian của nền tảng Java, ví dụ có các thao tác tương tự `getstatic`, `invokestatic` hoặc `invokevirtual`. Những lệnh này **không phải** instruction set của x86-64 hay ARM64. JVM là thành phần nạp, kiểm tra và thực thi bytecode; JVM có thể giải thích lệnh và/hoặc dùng JIT để tạo machine code trong lúc chương trình chạy.

Machine code là các lệnh dành cho **kiến trúc CPU thực**, được hệ điều hành/processor nạp và chạy. Native executable được tạo trước cho một target nhất định thường không có tính di động cùng cách với Java bytecode.

### JIT cũng biên dịch thành mã máy — nhưng ở thời điểm khác

**Just-in-time compilation (JIT)** có thể dịch những phần bytecode phù hợp thành mã máy **trong quá trình chương trình thực thi**. Mục đích là tối ưu hiệu năng dựa trên thông tin runtime; quá trình này không đồng nghĩa `javac` đã xuất một `.exe` chứa mã máy của toàn bộ ứng dụng.

Nếu chương trình được phát hành bằng `jpackage`, JVM đóng kèm vẫn có thể dùng JIT như khi chạy `java -jar`. Vì vậy phân biệt đúng là:

- **JIT:** quá trình dịch/tối ưu tại runtime bên trong JVM.
- **AOT Native Image:** tạo binary đã biên dịch trước thời điểm người dùng chạy.
- **`jpackage`:** chuẩn bị artifact phân phối; không phải trình AOT compiler cho code Java.

## 3. Đóng gói bằng jpackage thực sự tạo ra cái gì?

`jpackage` là công cụ JDK dùng để tạo **self-contained Java application**. Với một ứng dụng JAR, image thường có:

- **Ứng dụng:** tệp `.jar`, các JAR phụ thuộc và tài nguyên khác được đưa vào input directory.
- **Launcher:** chương trình khởi chạy phù hợp với nền tảng, ví dụ `HelloBytecode.exe` trên Windows hoặc file executable trong `bin/` trên Linux.
- **Runtime:** bản Java runtime image được tạo/cung cấp để chạy ứng dụng mà không yêu cầu người dùng cài **Java runtime riêng ở hệ thống**.
- **Cấu hình:** thông tin app, main class/JAR, JVM options hoặc arguments; có thể bổ sung icon, shortcuts và installer metadata.

`jpackage` có thể tự dùng **`jlink`** tạo runtime khi bạn không cung cấp `--runtime-image`. `jlink` liên kết các module của **Java runtime** để tạo runtime image, **không** phải công cụ biên dịch lớp Java của ứng dụng thành mã máy.

Một application image có thể trông như:

```text
Linux (mô tả khái quát):
HelloBytecode/
  bin/HelloBytecode
  lib/
    app/hello-app.jar
    runtime/...

Windows (mô tả khái quát):
HelloBytecode/
  HelloBytecode.exe
  app/hello-app.jar
  runtime/...

macOS (mô tả khái quát):
HelloBytecode.app/
  Contents/MacOS/HelloBytecode
  Contents/app/hello-app.jar
  Contents/runtime/...
```

Các thư mục và tên file nội bộ có thể khác theo JDK, cách cấu hình và hệ điều hành; không dựa vào layout nội bộ này như một API ổn định. Điểm bất biến về ý tưởng là **một native launcher có thể khởi động ứng dụng Java chạy trên runtime đã đóng gói**.

**Quan trọng:** Có một file launcher native ở kết quả `jpackage` **không chứng minh mã ứng dụng trong JAR đã biến thành machine code**. Một file cài đặt `.msi`/`.exe` hoặc `.dmg` là **native package/installer theo OS**, không tự đồng nghĩa ứng dụng là *native-image AOT*.

## 4. Ví dụ Java 17+ hoàn chỉnh: từ source đến bytecode

Giả sử bạn tạo thư mục dự án với cấu trúc:

```text
packaging-demo/
  src/
    lesson/
      packaging/
        HelloApp.java
  classes/      (tạo trong bước biên dịch)
  input/        (chứa JAR để jpackage đọc)
  dist/         (chứa app image)
```

Tạo file **`src/lesson/packaging/HelloApp.java`**:

```java
package lesson.packaging;

public final class HelloApp {
    private HelloApp() {
    }

    private static int total(int a, int b) {
        return Math.addExact(a, b);
    }

    public static void main(String[] args) {
        System.out.println("message=Hello from Java");
        System.out.println("sum=" + total(7, 5));
    }
}
```

Chương trình sử dụng các API Java chuẩn trong module `java.base`. Nó không phụ thuộc GUI, network, thời gian, môi trường hoặc số ngẫu nhiên, nên stdout được kỳ vọng ổn định ở cả những cách chạy hợp lệ sau đây.

### Bước A — Chuẩn bị các thư mục

Trong terminal tại `packaging-demo/`:

```bash
# Linux hoặc macOS:
mkdir -p classes input dist
```

Với **Windows PowerShell** có thể dùng:

```powershell
New-Item -ItemType Directory -Force -Path classes,input,dist | Out-Null
```

Hãy tạo file nguồn đúng đường dẫn ở trên (bằng IDE hoặc editor) trước khi biên dịch; các lệnh ví dụ không tự sinh nội dung file `HelloApp.java`.

### Bước B — javac: biên dịch thành bytecode

```bash
javac --release 17 -encoding UTF-8 -d classes src/lesson/packaging/HelloApp.java
```

`--release 17` yêu cầu compiler tạo bytecode/API tương thích Java 17. `-d classes` chỉ định thư mục đích, còn package `lesson.packaging` quyết định đường dẫn của class. Sau khi chạy thành công, có:

```text
classes/
  lesson/
    packaging/
      HelloApp.class
```

Đây là tệp **Java bytecode**, **không** phải executable native `HelloApp.exe`. Để chứng minh bằng công cụ JDK:

```bash
javap -c -classpath classes lesson.packaging.HelloApp
```

`javap -c` hiển thị các **bytecode instructions** từ class file. Đầu ra cụ thể là disassembly, không phải một bộ mã máy của CPU. Bạn có thể kiểm tra target class version bằng `javap -verbose` nếu cần.

Chạy class trực tiếp bằng JVM:

```bash
java -cp classes lesson.packaging.HelloApp
```

**Stdout mong đợi chính xác:**

```text
message=Hello from Java
sum=12
```

Ở bước này, **chưa có JAR, chưa có installer và chưa có native-image AOT**. JVM đang nạp class bytecode rồi thực thi.

## 5. Bước tiếp theo: jar gom bytecode nhưng không đổi định dạng lệnh

Tạo JAR có `Main-Class` trong manifest:

```bash
jar --create --file input/hello-app.jar --main-class lesson.packaging.HelloApp -C classes .
```

Giải thích:

- `--create`: tạo một archive JAR mới.
- `--file input/hello-app.jar`: chỉ định file đầu ra.
- `--main-class lesson.packaging.HelloApp`: đưa điểm vào ứng dụng vào manifest, để `java -jar` biết chạy class nào.
- `-C classes .`: chuyển vào thư mục `classes` khi đóng gói, đảm bảo đường dẫn `lesson/packaging/HelloApp.class` nằm đúng bên trong archive.

Kiểm tra các mục trong JAR:

```bash
jar --list --file input/hello-app.jar
```

Bạn sẽ thấy file `.class` và manifest trong archive (thứ tự hiển thị có thể khác); **không** thấy mã máy của ứng dụng chỉ vì đóng JAR.

Chạy:

```bash
java -jar input/hello-app.jar
```

**Stdout mong đợi y hệt khi chạy class:**

```text
message=Hello from Java
sum=12
```

Lệnh `java -jar` yêu cầu một Java runtime tương thích có mặt ở môi trường đang chạy. Một JAR ứng dụng đơn giản không tự chứa runtime Java, trừ khi bạn sử dụng một quy trình phân phối khác.

**JAR không phải “exe Java” theo nghĩa native:** nó là archive. `Main-Class` giúp launcher Java chọn chương trình khởi đầu, nhưng mã nguồn không được chuyển thành CPU instructions khi `jar` chạy.

## 6. jpackage: tạo application image có launcher và runtime đi kèm

Sau khi có `input/hello-app.jar`, dùng **một** trong hai cách sau tùy hệ điều hành. Các lệnh không nên chạy đè trên cùng thư mục output từ lần trước nếu chưa chủ động tạo đích mới.

### Trên Linux hoặc macOS

```bash
jpackage --type app-image --name HelloBytecode --input input --main-jar hello-app.jar --dest dist
```

### Trên Windows, khi muốn xem output trong console

```powershell
jpackage --type app-image --name HelloBytecode --input input --main-jar hello-app.jar --dest dist --win-console
```

`--win-console` chỉ dành cho Windows và phù hợp với bài demo console. Không truyền tùy chọn đó trên Linux/macOS. Với chương trình GUI, cách tổ chức launcher/console sẽ khác.

**Giải thích các tùy chọn:**

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--type app-image` | Tạo thư mục/bundle ứng dụng có thể chạy, **chưa phải installer OS** |
| `--name HelloBytecode` | Tên ứng dụng/launcher trong kết quả |
| `--input input` | Thư mục chứa file ứng dụng cần mang vào image |
| `--main-jar hello-app.jar` | Tên file JAR trong `--input`, có manifest `Main-Class` |
| `--dest dist` | Vị trí ghi application image |
| `--win-console` | Trên Windows: tạo launcher hỗ trợ tương tác console |

Do `hello-app.jar` có `Main-Class`, không cần thêm `--main-class` ở đây. Nếu JAR không có main class trong manifest, bạn có thể thêm `--main-class lesson.packaging.HelloApp` để chỉ rõ.

Nếu không cung cấp `--runtime-image`, `jpackage` thường dùng `jlink` để tạo Java runtime image cần thiết theo cấu hình JDK và loại ứng dụng. Với ứng dụng **non-modular JAR**, tập module runtime được chọn theo quy tắc của phiên bản JDK dùng đóng gói; không suy rằng runtime được tự động rút gọn thành duy nhất `java.base` trong mọi bản JDK.

### Chạy application image

Trên Linux, đường dẫn launcher thường là:

```bash
./dist/HelloBytecode/bin/HelloBytecode
```

Trên macOS:

```bash
./dist/HelloBytecode.app/Contents/MacOS/HelloBytecode
```

Trên Windows PowerShell:

```powershell
& ".\dist\HelloBytecode\HelloBytecode.exe"
```

**Stdout mong đợi khi launcher được chạy trong console phù hợp:**

```text
message=Hello from Java
sum=12
```

Đường dẫn launcher cụ thể cần xác nhận trên image do hệ điều hành/JDK thực tế tạo ra. Trong bản dùng Windows, `--win-console` giúp quan sát stdout trong console. Với desktop bundle khởi động bằng thao tác nhấp chuột, có thể không có cửa sổ console để nhìn thấy output dù chương trình vẫn chạy.

### Điều gì đã thay đổi sau jpackage?

Đã thay đổi **cách phân phối**: người dùng nhận được launcher, JAR và runtime đi kèm. Máy đích thường **không cần cài một JDK hoặc JRE riêng** để chạy ứng dụng từ image này.

**Không** thay đổi bản chất code Java của `HelloApp`: file `.class` vẫn tồn tại trong JAR, và runtime Java đóng kèm vẫn thực thi bytecode. Việc có một launcher `.exe` trên Windows **không** chứng minh body của method `total(...)` đã được đóng thành native machine instructions bên trong `HelloBytecode.exe`.

### Lưu ý khi thư viện phụ thuộc nhiều

Nếu chương trình phụ thuộc JAR khác, cần đưa những dependency/resource cần thiết vào `--input` và bảo đảm cấu hình class path/module path đúng. `jpackage` **không tự suy ra và tải dependency từ Maven Central**, cũng không tự sửa lỗi class loading chỉ vì tạo launcher thành công.

Kiểm thử phải dùng chính image trên một máy/VM có cấu hình OS đích. Với ứng dụng desktop hay module phức tạp, hãy xem thêm native libraries, permissions, services, font, locale, certificate store và drivers.

## 7. Đóng gói thành installer là một bước khác

`--type app-image` tạo **application image**: một cấu trúc có thể chạy/di chuyển được theo điều kiện của OS. Nếu muốn một **bộ cài tương thích hệ điều hành**, `jpackage` còn hỗ trợ:

| Hệ điều hành dùng để build | Định dạng installer thường dùng |
| --- | --- |
| Windows | `--type exe`, `--type msi` |
| macOS | `--type dmg`, `--type pkg` |
| Linux | `--type deb`, `--type rpm` |

Ví dụ chạy **trên chính OS tương ứng**:

```bash
# Windows:
jpackage --type msi --name HelloBytecode --input input --main-jar hello-app.jar --dest dist

# macOS:
jpackage --type dmg --name HelloBytecode --input input --main-jar hello-app.jar --dest dist

# Linux Debian/Ubuntu, nếu có công cụ đóng gói cần thiết:
jpackage --type deb --name HelloBytecode --input input --main-jar hello-app.jar --dest dist
```

Các dòng trên là **lựa chọn minh họa cho từng nền tảng**, không chạy tuần tự tất cả trên một máy. Định dạng yêu cầu bộ công cụ bổ trợ khác nhau theo OS/JDK (ví dụ WiX trên Windows hoặc các công cụ build package trên Linux). Xem `jpackage --help` trên môi trường thực để kiểm tra tùy chọn và prerequisites.

**Không có hỗ trợ đóng gói cross-platform trực tiếp**: bạn phải build gói tương thích trên hệ điều hành đích. Tạo Windows MSI trên Linux bằng đúng `jpackage` không phải một tính năng chuẩn được công cụ hứa hẹn.

Installer có thể cài shortcut, tích hợp menu, cung cấp thông tin app, hoặc thực hiện các bước cài đặt/hủy cài đặt của OS. Đây là **tính năng phân phối**, không phải một phép chuyển Java bytecode sang native machine code.

## 8. jlink tạo runtime — không biên dịch ứng dụng thành mã máy

Một nhầm lẫn khác: vì `jpackage` gọi `jlink`, có người nghĩ `jlink` là compiler AOT. Điều đó không chính xác.

`jlink` tạo **custom Java runtime image** bằng cách ghép các module đã chọn cùng các thành phần Java runtime cần thiết. Một ứng dụng đơn giản chỉ dùng `java.base` có thể dùng:

```bash
jlink --add-modules java.base --output custom-runtime
```

Sau đó dùng runtime này cho `jpackage` nếu phù hợp:

```bash
jpackage --type app-image --name HelloBytecode --input input --main-jar hello-app.jar --runtime-image custom-runtime --dest dist
```

**Không chạy câu lệnh `jpackage` thứ hai này vào cùng thư mục `dist/HelloBytecode` đã có từ mục 6** nếu chưa chọn đích riêng hoặc dọn có chủ đích. Hãy dùng một thư mục output khác khi muốn so sánh hai biến thể.

Cần nhớ:

- `--runtime-image` yêu cầu runtime image **phù hợp OS/CPU đích**.
- Các module được thêm phải bao phủ nhu cầu thực của ứng dụng, thư viện phụ thuộc và service providers. Với ứng dụng lớn, phân tích module bằng `jdeps` và test đầy đủ trên chính image.
- `jlink` không chuyển `lesson.packaging.HelloApp` thành machine code trước khi chạy; class vẫn nằm trong JAR.
- Cách `jpackage` tự tạo runtime và cơ chế service bindings có thể thay đổi theo phiên bản JDK. Ví dụ, từ JDK 25, runtime image tự tạo bởi `jpackage` không tự ràng buộc toàn bộ service providers như trước; các ứng dụng dùng `ServiceLoader` nên kiểm tra rõ module/provider và cấu hình `--jlink-options --bind-services` khi cần. Đây là lưu ý hiện hành, **không** phải yêu cầu bắt buộc cho ví dụ `HelloApp` chỉ dùng `java.base`.

`jdeps --print-module-deps input/hello-app.jar` có thể dùng để kiểm tra module dependency tĩnh. Tuy nhiên, với reflection, service loading hoặc optional features, phân tích tĩnh **chưa chắc nhận diện hết** nhu cầu runtime. Kiểm thử ứng dụng đã đóng gói vẫn rất quan trọng.

## 9. Biên dịch native AOT là một con đường khác: GraalVM Native Image

Nếu yêu cầu thực tế là **mã Java được biên dịch trước thành một native executable**, công cụ phù hợp có thể là **GraalVM Native Image**, không phải `jpackage`.

Với một GraalVM có công cụ `native-image` và native toolchain đầy đủ, bạn có thể thử từ JAR có `Main-Class` đã tạo:

```bash
native-image -jar input/hello-app.jar hello-native
```

Đây là **bước tùy chọn**, **không** có sẵn chỉ vì JDK 17 chuẩn được cài. Cú pháp và các prerequisites cần kiểm tra theo bản GraalVM mà bạn dùng. Sau khi build thành công, thường có `hello-native` trên Linux/macOS hoặc `hello-native.exe` trên Windows.

Khi chạy executable được tạo từ ví dụ đơn giản, **stdout nghiệp vụ mong đợi vẫn là**:

```text
message=Hello from Java
sum=12
```

Nhưng bên dưới, executable đã được Native Image **phân tích và biên dịch AOT** từ bytecode cùng các lớp/runtime cần thiết cho target. Nó không chạy bằng cách nạp JAR vào một JVM HotSpot đi kèm như bundle `jpackage`. Binary vẫn có thể phụ thuộc hệ điều hành và các thư viện native của môi trường, vì thế “native” **không tự có nghĩa hoàn toàn static hoặc chạy trên mọi OS**.

### Đừng xem AOT là lựa chọn luôn tốt hơn

GraalVM Native Image có thể giúp giảm thời gian khởi động hoặc bộ nhớ trong nhiều kịch bản, nhưng kết quả phụ thuộc ứng dụng và cấu hình. Quá trình build có thể tốn thời gian và RAM hơn; một số khả năng động của Java như reflection, dynamic class loading, proxy, resource access, JNI và khởi tạo tĩnh cần metadata hoặc cấu hình riêng.

Ngược lại, ứng dụng chạy trên JVM có JIT có thể tối ưu tốt cho workload dài hạn. **Không suy ra một lựa chọn luôn nhanh hơn** chỉ vì nó chứa hay không chứa một file `.exe`; nên benchmark cold start, throughput, peak memory và latency dưới workload thực.

### Bảng tổng hợp

| Đặc điểm | JAR chạy bằng JVM | Image/installer từ `jpackage` | Executable từ Native Image |
| --- | --- | --- | --- |
| Code ứng dụng chính | Bytecode `.class` | Bytecode trong JAR/module | Machine code được AOT compile |
| Cơ chế chạy | JVM có sẵn | Runtime Java/JVM đi kèm | Native binary với runtime components của Native Image |
| Cần cài Java riêng trên máy đích? | Thông thường **có** runtime phù hợp | **Không**, runtime được đóng kèm | **Không** cần JVM Java riêng, nhưng có thể cần thư viện OS |
| Có launcher theo OS? | Không bắt buộc | **Có** | Executable native chính là điểm chạy |
| Có thể tạo installer OS? | Cần công cụ khác hoặc quy trình bổ sung | **Có**, là mục đích của `jpackage` | Có thể đóng installer riêng; Native Image chủ yếu tạo binary |
| Portability của artifact | Bytecode tương đối độc lập OS nếu dependencies không native | Image/installer đặc thù OS/kiến trúc | Binary đặc thù OS/kiến trúc |
| Biên dịch app thành mã máy tại build? | **Không** | **Không** | **Có** |
| Có thể dùng JIT trong runtime JVM? | **Có** | **Có** | Không chạy theo mô hình HotSpot/JIT thông thường |

“Có runtime đi kèm” khác với “không cần runtime”. Image từ `jpackage` vẫn chạy **một Java runtime**, chỉ là runtime đã được phân phối cùng sản phẩm. Native Image cũng mang theo thành phần hỗ trợ thực thi riêng, nên tránh phát biểu quá đà rằng nó “không có runtime nào”.

## 10. Những kiểm chứng nên làm thay vì nhìn phần mở rộng file

### Kiểm tra JAR vẫn chứa class bytecode

```bash
jar --list --file input/hello-app.jar
javap -c -classpath input/hello-app.jar lesson.packaging.HelloApp
```

Kết quả `javap` sẽ cho thấy JVM bytecode instructions. `jpackage` không sửa `.class` thành máy mã CPU trong JAR. Bạn có thể xem payload app trong image phù hợp để xác minh JAR vẫn hiện diện; đường dẫn cụ thể là chi tiết bố cục của phiên bản công cụ.

### Kiểm tra image chứa runtime

Mở thư mục image và tìm vùng chứa runtime Java; các layout điển hình ở mục 3 minh họa ý tưởng. Hãy thử chạy image **trên máy thử không cài Java riêng** nhưng cùng OS/architecture phù hợp: launcher vẫn có thể chạy nhờ runtime đi kèm (nếu các dependencies hệ điều hành khác đầy đủ).

### Kiểm tra Native Image thực sự là native binary

Dùng lệnh `native-image` để tạo binary rồi thử chạy **mà không gọi `java -jar` hay JVM launcher**. Trên Linux có thể dùng công cụ phân tích file native (`file`, `ldd` nếu phù hợp); trên Windows có thể xem PE metadata; trên macOS có thể kiểm tra định dạng Mach-O. Đây là bước điều tra artifact, không phải lý do bỏ kiểm thử nghiệp vụ.

### Kiểm tra hiệu năng bằng số liệu

Đo startup time, RSS/peak memory, warmup, throughput, kích thước bản phân phối và build time. So sánh cùng workload và target OS/CPU. **Đừng kết luận “EXE thì nhanh hơn JAR”** khi hai tệp có thể đều khởi động cùng JVM, hoặc khi kết quả đo chủ yếu phản ánh disk cache và antivirus.

## 11. Những lỗi thiết kế và kỳ vọng phổ biến

**1. “`jpackage` dịch Java sang mã máy.”** Không đúng. `jpackage` chuẩn bị launcher, runtime và ứng dụng để phân phối; `javac` đã tạo bytecode trước đó. Có native launcher không đồng nghĩa phần code nghiệp vụ đã AOT compile.

**2. “`jar` tạo chương trình chạy độc lập mà không cần Java.”** Không đúng. Manifest `Main-Class` chỉ định điểm vào cho `java -jar`; JVM vẫn cần ở máy chạy, trừ khi đóng runtime cùng ứng dụng bằng cách khác.

**3. “`javac` luôn biên dịch thành instruction của x86/ARM.”** Không đúng. `javac` thường tạo Java class bytecode. JIT có thể tạo machine code sau khi JVM bắt đầu chạy.

**4. “Không phải cài JRE nghĩa là chương trình không dùng JVM.”** Không đúng. App image từ `jpackage` có thể chứa Java runtime/JVM riêng, nên người dùng không phải tự cài.

**5. “File `.exe` nào cũng là native-compiled Java.”** Không đúng. Installer, launcher và binary AOT có thể cùng mang phần mở rộng `.exe` nhưng chức năng khác nhau.

**6. “Có thể build gói installer cho mọi OS trên một máy bằng `jpackage`.”** Không đúng theo cách công cụ chính thức hỗ trợ: build các format của mỗi nền tảng trên chính nền tảng đó, với toolchain tương ứng.

**7. “`jlink` tạo mã máy cho ứng dụng.”** Không đúng. `jlink` tạo custom Java runtime từ module; nó không chuyển toàn bộ logic của JAR thành native executable.

**8. “Đóng gói giúp che giấu bytecode và tài sản trí tuệ hoàn toàn.”** Không đúng. Bytecode trong JAR vẫn có thể được giải nén và phân tích bằng công cụ JDK hoặc decompiler. Signing, obfuscation, kiểm soát quyền và threat model là những chủ đề riêng.

**9. “Chỉ cần một JAR là đủ mọi dependency.”** Không đúng. Phải đóng đúng JAR phụ thuộc, native libraries, resources và cấu hình cần thiết. Một bản dựng thành công không chứng minh ứng dụng có đủ mọi tài nguyên runtime.

**10. “Native Image luôn chạy nhanh hơn JVM.”** Không đúng như một định luật. Nó có ưu thế trong một số chỉ tiêu, còn JVM/JIT có thể thuận lợi ở workload khác; kiểm chứng bằng benchmark thực tế.

**11. “Installer được sinh ra là đã được ký số.”** Không đúng. Việc tạo installer không tự đảm bảo code signing, notarization, chính sách cập nhật, chứng nhận phát hành hoặc nguồn tải đáng tin. Cần một quy trình phát hành có kiểm soát.

**12. “App image thay đổi được trên mọi OS chỉ bằng rename launcher.”** Không đúng. Runtime, native launcher, thư viện và installer gắn với OS/architecture. `HelloBytecode.exe` trên Windows không biến thành binary Linux khi đổi tên file.

## 12. Khi nào chọn phương án nào?

### Phát hành JAR

Chọn khi máy chủ hoặc môi trường đích **đã có Java runtime do tổ chức quản lý**, ứng dụng được triển khai qua container/orchestrator, hoặc pipeline đã có tooling quản lý JVM. Đây là lựa chọn phổ biến cho backend; Java bytecode không bị khóa vào một installer desktop riêng.

### Phát hành app image/installer với jpackage

Chọn khi cần **người dùng desktop cài và khởi chạy thuận tiện** mà không tự quản lý Java runtime: icon, shortcut, installer OS và runtime đi kèm. Người dùng có thể thấy ứng dụng như một app thông thường nhưng ứng dụng vẫn chạy trên Java runtime đã đóng gói.

### Dùng GraalVM Native Image

Cân nhắc khi có yêu cầu cụ thể về **cold start**, footprint, triển khai native binary hoặc môi trường runtime. Đầu tư kiểm tra tương thích reflection/resources/native libraries và đo hiệu năng thực. Không chọn chỉ vì muốn có `.exe`, bởi `jpackage` đã giải quyết bài toán tạo launcher/installer mà không cần AOT.

### Dùng jlink

Dùng khi cần tự tạo một **Java runtime image gọn theo module**, có thể đóng chung với ứng dụng. Nó bổ sung cho `jpackage`; không phải đối thủ thay thế native-image AOT.

## 13. Bài thực hành có tiêu chí QA

### Bài 1 — Ba cách chạy cùng bytecode

Từ `HelloApp.java`, thực hiện `javac`, tạo JAR có manifest, chạy bằng `java -cp` và `java -jar`. So sánh hai stdout; chúng phải cùng là:

```text
message=Hello from Java
sum=12
```

Giải thích vì sao cả hai cách chạy đều sử dụng JVM dù command-line khác nhau.

### Bài 2 — Tạo application image

Dùng `jpackage --type app-image` tương ứng OS. Kiểm tra image có launcher, payload app và runtime; chạy launcher trên máy tương thích. Giải thích vì sao xuất hiện một file `.exe` hoặc executable launcher **không chứng minh toàn bộ ứng dụng đã AOT compile**.

### Bài 3 — Nhận diện JAR chứa bytecode

Dùng `jar --list` và `javap -c` trên JAR nguồn. Liệt kê ít nhất ba loại bytecode instruction hoặc thành phần JVM class bạn tìm thấy. Đặt câu hỏi: “Có lệnh nào từ `jar` hoặc `jpackage` đã dịch `HelloApp.total(...)` thành x86/ARM machine code chưa?”

### Bài 4 — Native Image là lựa chọn độc lập

Nếu có GraalVM Native Image, thử `native-image -jar input/hello-app.jar hello-native`. Ghi lại OS/architecture mục tiêu và các điều kiện build. So sánh artifact và runtime với app image từ `jpackage`. Nếu công cụ không được cài, chỉ cần mô tả đúng pipeline; không đánh dấu “đã build binary” giả.

### Bài 5 — Installer hệ điều hành

Trên OS phù hợp và với các prerequisites đã cài, tạo một gói installer (`msi`, `dmg`, `deb` hoặc `rpm`). Phân biệt launcher, app image và installer. Kiểm tra quy trình cài/gỡ ứng dụng, shortcut và quyền thay vì chỉ kiểm tra một file xuất hiện.

### Bài 6 — Đọc hiểu một phát biểu sai

Đánh giá phát biểu: “Đã dùng `jpackage` xuất Windows EXE, vì vậy mã Java đã thành mã máy và ứng dụng không còn JVM.” Phân tích thành **hai khẳng định độc lập**: (a) việc có launcher EXE, (b) cơ chế thực thi bytecode và runtime. Đưa ra giải thích đúng, ngắn gọn.

### Bài 7 — Hệ thống thực tế

Giả sử một ứng dụng dùng `ServiceLoader`, JDBC driver và resource files. Lập checklist dependency khi đóng gói; kiểm tra runtime image/modules, service bindings, class path và resource loading. Giải thích vì sao việc tạo installer thành công không bảo đảm mọi nhánh chức năng chạy đúng.

**Tiêu chí hoàn thành:** Người học phải chỉ ra được **đầu vào, đầu ra, thời điểm biên dịch và cơ chế chạy** của từng công cụ, tự chạy được Java class/JAR/app image và không đồng nhất “đóng gói theo OS” với “biên dịch AOT thành mã máy”.

## 14. Tài liệu đối chiếu chính thức và hiện hành

- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): biên dịch Java source thành class bytecode, tùy chọn `--release` và `-d`.
- [Oracle Java SE 17 — jar](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): tạo archive, manifest và main class.
- [Oracle Java SE 17 — jpackage](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): `--type app-image`, `--input`, `--main-jar`, `--runtime-image`, định dạng installer.
- [Oracle Java SE 26 — Packaging Overview](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html): cấu trúc application image, yêu cầu runtime, giới hạn build theo OS và cách tự tạo runtime với jlink.
- [Oracle Java SE 17 — jlink](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): tạo custom runtime image từ modules.
- [Oracle Java SE 17 — java](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): chạy class, JAR và module bằng Java launcher.
- [Oracle JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): JAR là archive và manifest `Main-Class`.
- [GraalVM Native Image — Reference Manual](https://www.graalvm.org/latest/reference-manual/native-image/): AOT từ bytecode thành native binary, runtime components và yêu cầu reachability metadata.

**Ghi nhớ:** **`javac` tạo bytecode; `jar` lưu bytecode; `jpackage` phân phối ứng dụng cùng launcher và Java runtime; `native-image` mới là một công cụ AOT tạo native executable từ bytecode.** Một ứng dụng có thể có icon, installer và file `.exe` mà **mã Java vẫn chạy trên JVM đóng kèm**. Hãy phân biệt *đóng gói* với *biên dịch thành mã máy* bằng cách kiểm tra artifact và cơ chế chạy, không dựa vào phần mở rộng file.