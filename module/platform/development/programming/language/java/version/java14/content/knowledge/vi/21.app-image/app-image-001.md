# Tạo ảnh ứng dụng bằng `jpackage --type app-image` (Java 16+)

> Mục tiêu: biết cách **build và kiểm thử một application image** chứa ứng dụng Java, launcher gốc hệ điều hành và Java runtime đi kèm; phân biệt image với JAR, runtime image của `jlink` và native installer; nắm các tham số `--type app-image`, `--input`, `--main-jar`, `--name`, `--dest` cùng những lỗi thường gặp. `jpackage` là công cụ chính thức từ **JDK 16**, vẫn được hỗ trợ trong các JDK hiện hành. Ví dụ thực hành dùng **JDK 17+**; không dùng cách gọi module ươm tạo hay flag preview của JDK 14/15.

## 1. App image của `jpackage` là gì?

`jpackage` là công cụ đóng gói ứng dụng Java thành định dạng quen thuộc với hệ điều hành đích. Với tùy chọn:

```bash
jpackage --type app-image [các tham số khác]
```

`jpackage` tạo một **thư mục/bundle application image**. Thông thường nó bao gồm: **launcher native** để khởi chạy ứng dụng, các JAR/module và tài nguyên của ứng dụng, cùng **Java runtime** được tạo bằng `jlink` hoặc được cung cấp sẵn. Người dùng chạy launcher thay vì phải thiết lập thủ công `java -cp`.

Cụm từ "image" ở đây **không phải ảnh đồ họa** PNG/JPEG, và cũng không phải một binary đã biên dịch AOT từ toàn bộ mã Java. Bytecode ứng dụng vẫn chạy trên JVM đi kèm, khác với công cụ GraalVM Native Image.

### Phân biệt bốn kết quả đóng gói

| Kết quả | Cách tạo thường gặp | Đặc điểm |
|---|---|---|
| **JAR** | `jar`, Maven, Gradle | Chứa Java classes/resources; thường cần runtime Java để chạy |
| **Runtime image** | `jlink` | Chứa tập module/runtime Java được chọn, **chưa phải bundle ứng dụng đầy đủ** |
| **Application image** | `jpackage --type app-image` | Thư mục chứa ứng dụng, launcher OS và runtime |
| **Native installer** | `jpackage --type exe/msi/pkg/dmg/deb/rpm` | Gói cài đặt theo hệ điều hành, có thể hỗ trợ shortcut, menu, uninstall |

**Quan trọng:** Windows app image có một file launcher `AppName.exe` bên trong, nhưng file ấy **không phải installer**. `--type app-image` không tạo tệp cài đặt `.msi`/`.dmg`/`.deb`. Việc đặt cùng một đuôi `.exe` cho launcher và Windows installer dễ gây nhầm lẫn; cần nhìn vào **kiểu package đã yêu cầu** và cấu trúc đầu ra.

App image thích hợp để kiểm tra launcher, runtime, dependencies và tài nguyên **trước khi** tạo installer, hoặc phân phối cả thư mục được nén nếu kênh phát hành chấp nhận kiểu này.

## 2. Điều kiện để chạy `jpackage` hiện hành

1. Dùng JDK có `javac`, `jar`, `jlink` và `jpackage`, ưu tiên JDK 17+ hoặc JDK mới đang được hỗ trợ.
2. Ứng dụng phải được **biên dịch và đóng gói thành JAR/module trước**, cùng tất cả file tài nguyên, native libraries và JAR phụ thuộc nếu có.
3. Tạo image **trên hệ điều hành mà image dự kiến chạy**: Windows cho image Windows, macOS cho app bundle macOS, Linux cho image Linux. `jpackage` không cung cấp khả năng cross-build một native image cho OS khác chỉ bằng đổi tên file.
4. Xác định CPU architecture, quyền thực thi, OS libraries và phụ thuộc native cần có trên máy đích. Runtime Java đi kèm **không** thay thế toàn bộ hệ điều hành.
5. Thư mục đầu vào và đầu ra phải được tách riêng, có quyền đọc/ghi phù hợp; không đưa build cache, thông tin nhạy cảm hoặc file thử nghiệm dư vào image.
6. Không dùng module cũ `jdk.incubator.jpackage`: công cụ đã được nâng từ incubating (JDK 14–15) thành công cụ **production-ready từ JDK 16**.

Xác nhận công cụ:

```bash
java -version
javac -version
jar --version
jpackage --version
jpackage --help
```

Nếu terminal báo `jpackage` không tồn tại, hãy kiểm tra `PATH` và `JAVA_HOME`. Một runtime rút gọn do `jlink` tạo ra không nhất thiết chứa công cụ build này. Nếu dùng nhiều bản JDK, nên bảo đảm các lệnh đến từ bản JDK dự kiến.

## 3. Các tham số cấu hình app image

| Tùy chọn | Vai trò | Ghi chú |
|---|---|---|
| `--type app-image` hoặc `-t app-image` | Chỉ tạo app image | Không bỏ qua rồi để `jpackage` chọn package type mặc định theo OS |
| `--name DemoImage226` | Tên ứng dụng và launcher | Ảnh hưởng tên bundle/thư mục kết quả |
| `--input input` | **Thư mục đầu vào** | Mọi file trong thư mục này đều có thể được đưa vào payload |
| `--main-jar HelloApp.jar` | JAR chính của ứng dụng non-modular | Đường dẫn tính **tương đối với `--input`** |
| `--main-class HelloApp` | Class chứa `public static void main(String[])` | Có thể được suy ra từ JAR manifest nếu hợp lệ; khai báo rõ giúp dễ đọc |
| `--dest dist` | Thư mục **cha** để xuất kết quả | Ví dụ kết quả là `dist/DemoImage226/` |
| `--app-version 1.0.0` | Version ứng dụng trong metadata | Không ảnh hưởng version Java runtime |
| `--java-options "-Ddemo.mode=PACKAGED"` | Cờ truyền cho JVM khi chạy launcher | Đây là **system property**, không phải `args[]` |
| `--arguments "Mai"` | Đối số `main(String[])` mặc định | Sử dụng khi không có đối số ứng dụng do người chạy launcher truyền vào |
| `--icon path` | Icon cho ứng dụng | Định dạng theo OS, ví dụ `.ico` Windows, `.icns` macOS, `.png` Linux |
| `--win-console` | Dùng console cho launcher **Windows** | Hữu ích khi thử `System.out.println`; không áp dụng trên Linux/macOS |
| `--runtime-image runtimeDir` | Đóng gói runtime đã tạo sẵn | Phải chứa đúng module ứng dụng sử dụng |
| `--module-path mods --module module/main` | Đầu vào ứng dụng modular | Không dùng đồng thời `--module` và `--main-jar` |
| `--verbose` | In thông tin chi tiết quá trình build | Dùng khi cần debug packaging |
 
### `--input` khác `--dest`

`--input` là nơi bạn đặt **file sẽ mang vào image**; `--dest` là nơi `jpackage` **xuất** image. Nếu `--input` là `input/` chứa `HelloApp.jar`, thì `--main-jar` là `HelloApp.jar` chứ không nhất thiết là đường dẫn tuyệt đối của tệp. Đặt `--dest` khác `--input` để không vô tình đưa một image cũ vào image mới.

Việc `jpackage` tạo xong thư mục **không tự chứng minh** mọi dependency của app đủ hoặc launcher đã hoạt động; cần chạy thử sản phẩm cuối.

## 4. Ví dụ đầy đủ: một Java class thành Windows app image

Ví dụ này dùng **Windows PowerShell** vì dễ xác minh sự khác biệt giữa JAR và launcher native. Lệnh ví dụ đã được biên dịch, đóng gói, chạy thật trên **OpenJDK 24 Windows**.

### 4.1. Tạo source Java

Tạo tệp **`src/HelloApp.java`** (không có khai báo package):

```java
public final class HelloApp {
    public static void main(String[] args) {
        System.out.println("Hello from app-image");
        System.out.println("mode=" +
            System.getProperty("demo.mode", "missing"));
        System.out.println("firstArg=" +
            (args.length == 0 ? "<none>" : args[0]));
    }
}
```

Lớp `HelloApp` in ba dòng để kiểm tra chương trình, giá trị `-Ddemo.mode` và đối số đầu tiên. Đầu ra của nó xác định, không phụ thuộc JDK patch version, dữ liệu hệ thống hoặc network.

### 4.2. Build JAR và app image bằng PowerShell

Chạy đoạn sau trong **thư mục dự án mới/sạch**. Ký tự nháy ngược ở cuối dòng lệnh là **line continuation của PowerShell**, **không** dùng nguyên xi trên Bash/Linux/macOS.

```powershell
# Trong Windows PowerShell ở thư mục dự án sạch.
New-Item -ItemType Directory -Force -Path src,classes,input,dist |
    Out-Null

# Tệp src\HelloApp.java chứa lớp HelloApp ở trên.
javac -encoding UTF-8 -d classes src\HelloApp.java
jar --create --file input\HelloApp.jar --main-class HelloApp `
    -C classes .

# Chạy thử trước khi đóng gói:
java -jar input\HelloApp.jar

# Tạo app image, KHÔNG tạo bộ cài:
jpackage --type app-image `
    --name DemoImage226 `
    --input input `
    --main-jar HelloApp.jar `
    --main-class HelloApp `
    --dest dist `
    --app-version 1.0.0 `
    --java-options "-Ddemo.mode=PACKAGED" `
    --arguments "Mai" `
    --win-console

# Chạy launcher trong image:
& .\dist\DemoImage226\DemoImage226.exe
```

Lệnh `javac` biên dịch Java code thành `HelloApp.class` trong `classes`. Lệnh `jar --create ... --main-class HelloApp` xây dựng JAR có main class, đọc class từ `classes`. `java -jar` kiểm chứng artifact **trước** đóng gói.

Khi dùng `jpackage`, `--type app-image` chọn đầu ra thư mục, `--name` đặt tên image/launcher, `--input` chứa `HelloApp.jar`, `--dest` chỉ định thư mục cha `dist`. Tùy chọn `--win-console` làm launcher Windows hiển thị stdout, còn `--java-options` và `--arguments` cấu hình lúc **chạy launcher**, không sửa bytecode gốc.

### 4.3. Stdout đã xác minh

Chạy JAR gốc bằng `java -jar input\HelloApp.jar`:

```text
Hello from app-image
mode=missing
firstArg=<none>
```

Chạy launcher đã tạo bằng `& .\dist\DemoImage226\DemoImage226.exe`:

```text
Hello from app-image
mode=PACKAGED
firstArg=Mai
```

**Vì sao khác nhau?** Lệnh `java -jar` trực tiếp không nhận `-Ddemo.mode=PACKAGED` hoặc đối số `Mai`, nên in `missing` và `<none>`. Trái lại, launcher trong image được cấu hình hai giá trị này. Dù vậy cả hai vẫn chạy **cùng bytecode Java**.

Chúng tôi cũng đã kiểm tra trên máy thử: sau `jpackage`, thư mục image tồn tại, `DemoImage226.exe` tồn tại, `app/HelloApp.jar` tồn tại và thư mục `runtime/` tồn tại. Launcher chạy thành công với đúng stdout ở trên.

## 5. Nội dung và cấu trúc thư mục app image

Sau khi chạy lệnh ví dụ trên **Windows**, kết quả điển hình:

```text
dist/
  DemoImage226/
    DemoImage226.exe        <-- launcher native (không phải installer)
    app/
      HelloApp.jar          <-- JAR ứng dụng
      DemoImage226.cfg      <-- metadata launcher
    runtime/
      ...                   <-- Java runtime
```

Các file phụ và đường dẫn chi tiết có thể thay đổi theo JDK/OS; không dựa vào vị trí của từng file nội bộ như một API ổn định. Tuy vậy cần xác nhận đủ **launcher + payload + runtime**.

Để kiểm tra trên Windows PowerShell:

```powershell
Test-Path .\dist\DemoImage226\DemoImage226.exe
Test-Path .\dist\DemoImage226\app\HelloApp.jar
Test-Path .\dist\DemoImage226\runtime
& .\dist\DemoImage226\DemoImage226.exe
```

Ba kết quả `Test-Path` sẽ là `True` trong ví dụ đã thử. Đầu ra launcher phải khớp với chương trình đã thiết kế. Không chỉ kiểm tra sự tồn tại của JAR: một app có thể thiếu file cấu hình, thiếu module Java runtime hoặc phụ thuộc native dù đóng gói báo thành công.

### Kết quả trên các hệ điều hành khác

- **Linux:** thường có launcher ở `bin/`, ứng dụng dưới `lib/app/`, runtime ở `lib/runtime/`; launcher không có hậu tố `.exe`.
- **macOS:** là một bundle `DemoImage226.app` với nội dung trong `Contents/` như `Contents/MacOS/`, `Contents/app/`, `Contents/runtime/`.
- **Windows:** là thư mục `DemoImage226/` có `DemoImage226.exe`, `app/` và `runtime/`.

Các sơ đồ này là **bố cục phổ biến được tài liệu Oracle minh họa**, không buộc mọi phiên bản JDK phải có chính xác từng file con giống nhau. Không di chuyển **một mình** file launcher sang máy khác: phải phân phối **toàn bộ image**, giữ các thư mục tương đối và thử trên OS/CPU phù hợp.

### Vì sao runtime được kèm theo?

Khi không truyền `--runtime-image`, `jpackage` tạo runtime bằng `jlink`. Đối với ứng dụng Java non-modular, runtime có thể gồm nhiều module JDK hơn những gì ứng dụng thực sự cần. Vì vậy image có thể có kích thước đáng kể. Đo kích thước thực tế và cân nhắc tối ưu module nếu có mục tiêu phân phối cụ thể; đừng mặc định image nhỏ hay lớn chỉ dựa vào tên tùy chọn.

## 6. Biến thể: non-modular, modular và runtime tùy chỉnh

### 6.1. Classpath/non-modular JAR

```bash
jpackage --type app-image --name SampleApp \
  --input input --main-jar SampleApp.jar \
  --main-class com.example.Main --dest dist
```

Đây là **snippet lệnh Bash minh họa**, giả sử `SampleApp.jar` nằm trong thư mục `input` và có class `com.example.Main`. Các JAR phụ thuộc, resources hoặc native libraries cần được đưa vào staging theo yêu cầu của ứng dụng; `jpackage` không tự tìm và tải Maven dependency trên mạng.

### 6.2. Java module với `module-info.java`

```bash
jpackage --type app-image \
  --name ModularApp \
  --module-path mods \
  --module com.example.app/com.example.app.Main \
  --dest dist
```

Giả sử `mods` chứa module `com.example.app` đã build. `--module` chỉ định tên module và main class (nếu cần). Không kết hợp `--module` với `--main-jar` vì đó là hai cách chọn ứng dụng chính khác nhau.

Mẫu lệnh này **không được thử** trong chương trình `HelloApp` (vì `HelloApp` cố tình non-modular); nó minh họa cú pháp được `jpackage` hỗ trợ theo tài liệu.

### 6.3. Runtime dùng `jlink`

Có thể xây runtime riêng để giảm kích thước hoặc kiểm soát module:

```bash
jlink --add-modules java.base,java.logging \
  --output my-runtime \
  --strip-debug --no-header-files --no-man-pages

jpackage --type app-image --name SampleApp \
  --input input --main-jar SampleApp.jar \
  --main-class com.example.Main \
  --runtime-image my-runtime --dest dist
```

**Đây là mẫu minh họa, không phải lệnh đảm bảo runtime `java.base,java.logging` đủ cho mọi app**. Nếu app dùng Swing/JavaFX/JDBC/JFR, DNS providers, `ServiceLoader` hoặc thư viện native, cần bổ sung module phù hợp. Dùng `jdeps` và test trên máy sạch để xác nhận. Từ JDK 25, Oracle thay đổi cách service binding mặc định của runtime do `jpackage` tạo; nếu app phụ thuộc `ServiceLoader` có thể cần cấu hình `--jlink-options --bind-services` và kiểm tra provider thực tế.

**Phân biệt `--runtime-image` và `--app-image`:** tùy chọn thứ nhất nhận một **Java runtime image** để đưa vào app image khi tạo. Tùy chọn thứ hai nhận một **application image đã tạo** để thực hiện bước đóng gói khác (ví dụ installer). Khi chuyển image có sẵn thành installer, `--runtime-image` và `--app-image` là các tùy chọn loại trừ nhau — hãy lựa chọn runtime ở bước tạo app image ban đầu.

## 7. Khi nào cần native installer thay vì app image?

Một app image có thể được chạy trực tiếp từ thư mục nếu OS và quyền cho phép, nhưng **không tự thực hiện quy trình cài đặt hệ điều hành** như đăng ký vị trí cài đặt, tạo entry uninstall, tạo shortcut hoặc tích hợp chính sách phân phối.

Sau khi QA app image Windows, có thể chuyển thành installer (ví dụ MSI) bằng một bước **riêng**:

```powershell
# Minh họa, KHÔNG phải bước của bài demo đã chạy.
jpackage --type msi `
    --name DemoImage226 `
    --app-image dist\DemoImage226 `
    --dest installers
```

Phương thức này có thể cần toolchain native installer, chẳng hạn phiên bản WiX phù hợp với JDK trên Windows. Chỉ chạy nếu có nhu cầu tạo bộ cài và đủ công cụ. **Không** nói rằng `--type app-image` tự sinh ra MSI.

Đối với Linux/macOS, native installer tương ứng có các định dạng `deb/rpm`, `pkg/dmg` và yêu cầu toolchain riêng. Đầu ra luôn nên build/test trên OS đích; không cross-build image macOS từ Windows bằng một lá cờ đơn giản.

### Vòng đời phát hành

1. Build/test ứng dụng và tạo JAR/module.
2. `jpackage --type app-image` tạo image ứng dụng.
3. Chạy **launcher của image**, kiểm tra cấu hình, module, native libs và resources.
4. Khi cần, dùng chính image đã QA để build native installer, rồi kiểm tra cả cài đặt/gỡ cài đặt.
5. Với phân phối ngoài tổ chức, cân nhắc ký mã, notarization trên macOS, cập nhật runtime để nhận bản vá và kiểm soát license của các thành phần đi kèm.

Đừng bỏ bước kiểm tra app image vì installer đã build được: packaging thành công không đồng nghĩa mọi luồng nghiệp vụ trong ứng dụng thành công.

## 8. Các lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân hay gặp | Hướng xử lý |
|---|---|---|
| `jpackage: command not found` | Terminal không dùng JDK có `jpackage` | Xác nhận JDK/PATH và `jpackage --version` |
| Không tìm thấy `--main-jar` | Sai đường dẫn tương đối với `--input` | Đảm bảo `input/HelloApp.jar` có thật trước khi build |
| Launcher không tìm thấy main class | Sai `--main-class` hoặc JAR manifest | Kiểm tra tên package/class và chạy thử `java -jar` |
| Build được image nhưng chạy thiếu class | Thiếu JAR phụ thuộc hoặc resource trong `--input` | Đưa dependencies đúng staging và smoke test |
| Đầu ra là một folder, không phải `.msi` | Đã yêu cầu `--type app-image` | Dùng lệnh installer tách biệt nếu cần |
| Chỉ chép file `.exe` sang máy khác rồi lỗi | Launcher cần `app/` và `runtime/` bên cạnh | Chép **toàn bộ app image**, không cắt riêng launcher |
| Windows launcher không hiển thị stdout | Không bật chế độ console | Dùng `--win-console` cho ứng dụng CLI Windows |
| `--arguments` bị nhầm với JVM options | Argument cho `main` khác `-D...` cho JVM | Dùng `--arguments` và `--java-options` đúng mục đích |
| Gõ `--main-jar` cùng `--module` | Hai cơ chế đầu vào khác nhau | Chọn non-modular **hoặc** modular |
| `--runtime-image` gây lỗi lúc chạy | Runtime thiếu Java modules/service providers | Phân tích `jdeps`, thêm modules, kiểm tra launcher |
| Image quá lớn | Runtime nhiều module hoặc đóng gói file không cần | Thu gọn staging, cân nhắc `jlink` tùy chỉnh |
| Build trên Windows rồi mong chạy macOS | Launcher/runtime đặc thù OS | Build lại bằng máy/CI của OS đích |
| Đường dẫn có dấu cách bị tách thành nhiều args | Shell parsing/quoting sai | Quote `--input`, `--dest`, `--icon` và paths |
| Image target đã tồn tại | Thư mục output không sạch hoặc không đủ quyền | Sử dụng output mới/sạch, không ghi đè dữ liệu ngoài ý muốn |
| Dùng `--app-image` và `--runtime-image` cùng bước installer | Tùy chọn loại trừ nhau | Chỉ định runtime khi tạo image lần đầu |
| Cho rằng app image là native AOT binary | `jpackage` đóng gói JVM và JAR/module | Phân biệt với công cụ AOT/native compile khác |

**Lưu ý về bảo mật:** không đưa `.env`, secrets, private keys, credentials, dữ liệu khách hàng hoặc file build nội bộ vào `--input`. `jpackage` sao chép dữ liệu đầu vào vào bundle; người nhận image có thể đọc nhiều file bên trong. Tương tự, giá trị trong `--java-options` và `--arguments` không phải cơ chế bí mật để giữ token vì launcher/config có thể được kiểm tra.

## 9. Checklist QA trước khi giao app image

1. **Sử dụng công cụ chính thức:** `jpackage` thuộc JDK 16+; build bằng JDK 17+ phù hợp, không dùng `jdk.incubator.jpackage`.
2. **Chạy artifact nguồn:** JAR/module chạy đúng trước khi đưa vào `jpackage`.
3. **Chọn `--type app-image` rõ ràng:** không bỏ qua để tool tạo native installer mặc định.
4. **Kiểm tra staging:** đúng `--input` và `--main-jar`, đầy đủ dependencies/resources, không có file nhạy cảm.
5. **Dùng `--name` và `--dest` rõ ràng:** input và output tách nhau.
6. **Chọn entrypoint đúng:** `--main-class` cho JAR hoặc `--module` cho modular app.
7. **Xác minh launcher:** đúng nền tảng, đúng quyền thực thi, đúng JVM options/application arguments.
8. **Xác minh payload:** JAR/modules, tài nguyên, native libraries và runtime hiện diện đúng.
9. **Thực sự chạy thử image:** không chỉ kiểm tra việc thư mục được tạo.
10. **Kiểm tra runtime module closure:** `jdeps`/`jlink` nếu có runtime tùy chỉnh; test use cases dựa trên provider nếu có.
11. **Kiểm tra cross-platform:** mỗi OS/CPU cần build phù hợp; không phân phối image Windows cho Linux/macOS.
12. **Xác nhận quy trình phân phối:** app image có đủ, hay cần bộ cài native ở bước sau?
13. **Bảo vệ nguồn phát hành:** license, ký mã, công cụ antivirus/notarization và cập nhật bản vá Java runtime khi release mới.
14. **Kiểm thử trên máy người dùng tương đương:** đặc biệt là file paths, quyền ghi và native dependencies.

## Tài liệu chính thức

- Oracle Java SE 25, `The jpackage Command` — cú pháp `--type app-image` và các options: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html
- Oracle Java SE 25, `Packaging Overview` — Java runtime đi kèm và bố cục image Windows/Linux/macOS: https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html
- Oracle Java SE 25, `Image and Runtime Modifications` — tạo image rồi dùng `--app-image` để tạo installer: https://docs.oracle.com/en/java/javase/25/jpackage/image-and-runtime-modifications.html
- OpenJDK JEP 392, `Packaging Tool` — công cụ `jpackage` chính thức từ Java 16: https://openjdk.org/jeps/392
- Oracle Java SE 17, `The jpackage Command` — phiên bản API/cú pháp JDK LTS: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html
