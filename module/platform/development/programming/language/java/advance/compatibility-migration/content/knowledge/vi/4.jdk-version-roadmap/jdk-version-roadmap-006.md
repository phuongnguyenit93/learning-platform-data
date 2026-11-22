# Nâng cấp JDK 11 lên 17: đóng gói nội bộ và công cụ đã thay đổi

Nâng cấp từ JDK 11 lên JDK 17 không chỉ là đổi phiên bản JDK trong CI hoặc thay base image của container. Từ Java 9, JDK đã chuyển sang cấu trúc module; các thành phần runtime, thư viện nền tảng và công cụ đóng gói cũng thay đổi theo từng release. Trong khoảng từ 11 đến 17, một số công cụ cũ bị loại bỏ, cơ chế truy cập nội bộ của JDK được siết chặt, và `jpackage` trở thành công cụ chuẩn để tạo bộ cài ứng dụng.

Đối với Java Compatibility Migration, cần kiểm tra đồng thời ba lớp:

1. **Cấu trúc JDK và runtime image:** script, plugin hoặc ứng dụng có đang giả định cấu trúc thư mục JDK/JRE cũ hay truy cập trực tiếp file nội bộ không?
2. **Công cụ build và đóng gói:** pipeline có dùng công cụ đã bị loại bỏ, hoặc chưa tận dụng được cách tạo runtime image và bộ cài mới không?
3. **Ứng dụng và dependency:** source, bytecode, reflection, thư viện native và cơ chế nạp class có tương thích với JDK 17 không?

JDK 11 và JDK 17 đều là các bản LTS, nhưng không nên coi nâng cấp này là một bước thay thế nhị phân. Hãy xác định chính xác những công cụ mà dự án đang gọi, artifact mà pipeline đang tạo và cấu trúc runtime mà môi trường production đang sử dụng.

## 1. Phạm vi thay đổi từ JDK 11 lên JDK 17

JDK 17 bao gồm các thay đổi tích lũy từ những release 12, 13, 14, 15, 16 và 17. Vì vậy, một ứng dụng chạy ổn trên JDK 11 vẫn có thể gặp lỗi khi chạy hoặc đóng gói trên JDK 17 dù source không thay đổi.

| Khu vực | Trạng thái ở JDK 11 | Trạng thái ở JDK 17 | Tác động cần kiểm tra |
|---|---|---|---|
| JDK module image | Đã dùng cấu trúc module từ Java 9 | Tiếp tục dùng module image | Script không được giả định có `rt.jar`, `tools.jar` hoặc thư mục JRE lồng bên trong JDK |
| Truy cập JDK internals | Strong encapsulation đã được triển khai theo từng bước; một số truy cập còn được nới lỏng | Strong encapsulation mặc định được áp dụng rộng rãi theo JEP 403 | Reflection hoặc import package nội bộ có thể thất bại |
| `jlink` | Đã có từ Java 9 | Tiếp tục được hỗ trợ | Có thể tạo runtime image tối giản; phải xác định đúng module và service provider |
| `jpackage` | Chưa phải công cụ chuẩn đi kèm JDK 11 | Công cụ chuẩn từ JDK 16, có trong JDK 17 | Có thể thay thế nhiều script tự ghép runtime và bộ cài native |
| Pack200 | Đã deprecated for removal | Công cụ và API đã bị loại bỏ từ JDK 14 | Pipeline gọi `pack200`, `unpack200` hoặc `Pack200` không còn chạy |
| Nashorn JavaScript engine | Đã deprecated for removal trong JDK 11 | Bị loại khỏi JDK từ JDK 15 | Ứng dụng không còn nhận được engine Nashorn chỉ từ JDK |
| RMI Activation | Đã deprecated for removal trong JDK 11 | Bị loại bỏ từ JDK 17 | Code dùng `java.rmi.activation` cần được thay thế hoặc thiết kế lại |
| AOT/JIT thử nghiệm | Có `jaotc` trong một số bản phân phối JDK 11 | Các công cụ/compiler thử nghiệm này bị loại khỏi JDK 17 | Pipeline tối ưu native/AOT cũ cần được đánh giá lại |

Một số thành phần đã bị loại khỏi JDK trước phiên bản 11. Ví dụ, JavaFX không còn được đóng gói trong JDK từ Java 11; Java EE/CORBA modules, Java Web Start và `appletviewer` cũng đã rời JDK trước mốc này. Nếu ứng dụng đang chuyển từ JDK 8 hoặc một JDK vendor có bộ công cụ bổ sung, cần kiểm tra riêng các thay đổi đã xảy ra trước JDK 11, tránh nhầm chúng là thay đổi mới của 11 lên 17.

## 2. Cấu trúc đóng gói JDK sau Java 9

JDK 11 đã sử dụng cấu trúc module của Java 9. Vì vậy, khi nâng từ 11 lên 17, nhóm phát triển không phải chuyển đổi lần đầu từ `rt.jar` sang module image, nhưng vẫn cần kiểm tra các script và thư viện nội bộ đang dựa vào cấu trúc đó.

### 2.1. Không còn `rt.jar` và `tools.jar`

Trong các JDK cũ, nhiều lớp nền tảng được đóng gói trong `rt.jar`, còn công cụ và API phục vụ compiler/tooling có thể nằm trong `tools.jar`. Từ Java 9, các class của JDK được tổ chức thành module trong runtime image. Các file JAR cũ không còn là cách đóng gói nền tảng.

Một số giả định cũ cần được tìm kiếm trong script, plugin và code:

```text
$JAVA_HOME/jre/lib/rt.jar
$JAVA_HOME/lib/tools.jar
$JAVA_HOME/jre/bin/java
$JAVA_HOME/jre/bin/keytool
$JAVA_HOME/jre/lib/ext
```

Không nên thay các đường dẫn này bằng một đường dẫn nội bộ khác trong JDK 17. Hãy dùng API hoặc công cụ được hỗ trợ:

- Chạy compiler bằng Java toolchain hoặc `javac` từ JDK được chọn.
- Dùng `java --list-modules` để xem các module runtime có sẵn.
- Dùng `jar`, `jmod`, `jdeps` và `jlink` cho các thao tác module/JAR tương ứng.
- Dùng `jrt:/` filesystem nếu một công cụ thực sự cần duyệt tài nguyên của module image.
- Dùng `JAVA_HOME` hoặc toolchain do build tool quản lý để định vị JDK, thay vì tự ghép đường dẫn theo cấu trúc JDK cũ.

### 2.2. Module image và `jrt:/`

Các module nền tảng được lưu trong runtime image, thường được tổ chức bên trong thư mục `lib` của JDK/JRE image. Có thể xem danh sách module bằng:

```bash
java --list-modules
```

JDK cung cấp filesystem provider `jrt:/` để truy cập nội dung module image. Ví dụ, một công cụ Java có thể duyệt filesystem này thay vì mở `rt.jar`:

```java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;

URI uri = URI.create("jrt:/");
try (FileSystem fileSystem = FileSystems.getFileSystem(uri)) {
    Path javaBase = fileSystem.getPath("/modules/java.base");
    System.out.println(javaBase);
}
```

Đây là cách truy cập có chủ đích tới module image. Phần lớn ứng dụng nghiệp vụ không cần tự duyệt JDK image; nếu một plugin hoặc công cụ phân tích đang làm việc này, cần kiểm tra khả năng tương thích của nó với JDK 17.

### 2.3. JDK image và runtime image

JDK là bộ công cụ phát triển, chứa compiler, debugger và các công cụ khác. Runtime image là môi trường cần thiết để chạy ứng dụng. Từ Java 9, có thể tạo runtime image tùy chỉnh bằng `jlink`, chỉ gồm những module cần thiết.

Điều này có ý nghĩa đối với đóng gói:

- Không giả định một thư mục JRE riêng nằm bên trong thư mục JDK.
- Không copy toàn bộ JDK vào production nếu ứng dụng chỉ cần runtime.
- Có thể tạo runtime image theo từng ứng dụng hoặc nhóm ứng dụng.
- Phải kiểm tra các module nền tảng mà ứng dụng thực sự sử dụng, kể cả module được nạp qua service provider.
- Runtime image được tạo trên một nền tảng/kiến trúc nhất định; cần tạo và kiểm tra image phù hợp với môi trường đích.

Không nên xóa hoặc thay đổi trực tiếp file trong runtime image sau khi `jlink` tạo ra. Hãy tái tạo image từ module path và tham số build có thể lặp lại.

### 2.4. Thư mục extension và endorsed standards

Các cơ chế extension/endorsed standards cũ như `lib/ext`, `java.ext.dirs` và `java.endorsed.dirs` không còn là cơ chế mở rộng JDK hiện đại. Từ Java 9, thư viện ứng dụng cần được khai báo qua classpath, module path hoặc dependency management của build tool.

Nếu script còn copy JAR vào thư mục extension của JRE hoặc truyền các system property cũ, cần thay bằng một cấu hình classpath/module path rõ ràng. Không nên khôi phục cơ chế extension bằng cách tự tạo thư mục có tên giống cấu trúc cũ.

## 3. Strong encapsulation của JDK internals

Đây là thay đổi có ảnh hưởng lớn khi chuyển sang JDK 17. Các package nội bộ như `sun.*`, `com.sun.*` hoặc package trong module JDK không được export không phải API công khai ổn định. Một số ứng dụng và thư viện cũ vẫn truy cập chúng bằng reflection hoặc import trực tiếp.

### 3.1. Quá trình siết chặt truy cập

Java 9 giới thiệu module system và cơ chế encapsulation. Trong các release đầu, một số package cũ được giữ khả năng truy cập với cảnh báo để hỗ trợ migration. JDK 16 chuyển sang strong encapsulation mặc định đối với các package nội bộ của JDK; JDK 17 tiếp tục chính sách đó theo JEP 403.

Vì vậy, tùy chọn cũ:

```bash
--illegal-access=permit
```

không còn là cách khôi phục hành vi truy cập rộng trong JDK 17. Tùy chọn `--illegal-access` không còn tác dụng mở các package như trước và có thể chỉ phát ra cảnh báo rằng tùy chọn đã bị bỏ qua.

### 3.2. Dấu hiệu lỗi thường gặp

Khi nâng JDK, có thể gặp các lỗi như:

```text
java.lang.reflect.InaccessibleObjectException
```

hoặc:

```text
java.lang.IllegalAccessError
```

Nguyên nhân thường là thư viện đang cố truy cập thành viên hoặc kiểu nằm trong package mà module sở hữu không mở/export cho module gọi.

Ví dụ, một thư viện cũ cố truy cập sâu vào trường nội bộ của một class JDK bằng `setAccessible(true)`. Trên JDK cũ, hành động này có thể đã hoạt động nhờ cơ chế nới lỏng; trên JDK 17, nó có thể ném `InaccessibleObjectException`.

### 3.3. Phân biệt `--add-exports` và `--add-opens`

Hai tùy chọn này phục vụ hai mục đích khác nhau:

| Tùy chọn | Mục đích | Trường hợp dùng |
|---|---|---|
| `--add-exports` | Cho phép module khác truy cập các kiểu public trong package chưa export | Code compile hoặc runtime cần tham chiếu kiểu public thuộc package nội bộ |
| `--add-opens` | Mở package cho deep reflection ở runtime | Framework hoặc thư viện cần phản chiếu vào field/method/constructor không public |

Ví dụ mở package `java.base/java.lang` cho code trên classpath (module không tên):

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
```

Ví dụ export một package tới một module có tên:

```bash
javac --add-exports java.base/sun.nio.ch=my.module \
  -d out src/module-info.java src/example/Main.java
```

Tên module và package trong ví dụ chỉ minh họa cú pháp. Chỉ thêm flag sau khi đã xác định chính xác thư viện nào cần truy cập và package nào đang bị đóng.

`--add-reads` có thể bổ sung quan hệ đọc giữa các module trong những tình huống module graph đặc biệt. `--patch-module` cho phép bổ sung/thay thế nội dung module trong các tình huống phát triển hoặc kiểm thử có chủ đích; đây không phải giải pháp migration thông thường để che giấu việc dùng JDK internals.

### 3.4. Cách xử lý lâu dài

Ưu tiên theo thứ tự:

1. Nâng thư viện lên phiên bản hỗ trợ JDK 17 và không còn truy cập package nội bộ.
2. Thay API nội bộ bằng API công khai được hỗ trợ, ví dụ `java.util.Base64` thay cho encoder/decoder nội bộ cũ.
3. Nếu cần, thay thư viện bằng một implementation được duy trì và có API ổn định.
4. Chỉ dùng `--add-opens` hoặc `--add-exports` như biện pháp tương thích có phạm vi hẹp, được ghi nhận và có kế hoạch loại bỏ.

Không nên mở hàng loạt package cho `ALL-UNNAMED` chỉ để ứng dụng khởi động. Cách đó mở rộng quyền truy cập reflection của tất cả code trên classpath và làm tăng chi phí nâng cấp về sau.

### 3.5. Tìm dependency tới JDK internals

Dùng `jdeps` trên JAR và classpath của ứng dụng:

```bash
jdeps --jdk-internals --recursive \
  --class-path "lib/*" app.jar
```

Kết quả chỉ ra một số tham chiếu bytecode tới API nội bộ đã biết. Cần đọc cả phần khuyến nghị thay thế của công cụ và xác định thư viện chứa tham chiếu đó.

`jdeps` không thể phát hiện đầy đủ mọi truy cập reflection được tạo từ chuỗi, class được nạp động, native code hoặc hành vi phụ thuộc cấu hình. Vì vậy cần kết hợp với tìm kiếm source, kiểm thử runtime và log trên JDK 17.

## 4. `jlink`: tạo runtime image tối giản

`jlink` đã có từ Java 9, do đó có sẵn trong JDK 11 và JDK 17. Điểm quan trọng trong migration là kiểm tra lại module graph và cách pipeline tạo runtime image, thay vì xem `jlink` như một công cụ mới chỉ xuất hiện ở JDK 17.

### 4.1. Khi nào nên dùng `jlink`?

`jlink` phù hợp khi muốn đóng gói runtime chỉ chứa module cần thiết cho ứng dụng. Lợi ích có thể gồm:

- Giảm kích thước runtime image so với việc mang toàn bộ JDK.
- Kiểm soát chính xác module nền tảng có trong môi trường chạy.
- Tạo runtime riêng cho từng ứng dụng hoặc nhóm ứng dụng.
- Giảm sự khác biệt giữa runtime kiểm thử và runtime triển khai nếu cùng một image được dùng xuyên suốt pipeline.

Đổi lại, nhóm phát triển phải duy trì module list, xác minh service provider, locale/charset, security provider và các thành phần runtime mà ứng dụng cần. Một image quá tối giản có thể làm ứng dụng thất bại khi chạy một luồng ít được kiểm thử.

### 4.2. Tìm module cần thiết bằng `jdeps`

Với một ứng dụng JAR và thư viện phụ thuộc, có thể bắt đầu bằng:

```bash
jdeps --print-module-deps \
  --ignore-missing-deps \
  --class-path "lib/*" \
  app.jar
```

`jdeps` phân tích tham chiếu tĩnh trong bytecode và in ra danh sách module nền tảng cần thiết. `--ignore-missing-deps` hữu ích khi khảo sát sơ bộ nhưng không nên biến mất khỏi quá trình điều tra lỗi: dependency không tìm thấy vẫn cần được giải thích.

Phân tích tĩnh có giới hạn. Nếu ứng dụng dùng reflection, JDBC driver, logging provider, serialization provider hoặc `ServiceLoader`, module cần thiết có thể không được suy ra đầy đủ. Có thể phải bổ sung module theo kết quả test hoặc dùng `--bind-services` để đưa các provider module được phát hiện vào runtime image.

### 4.3. Tạo runtime image

Ví dụ tạo image từ JDK module path và module của ứng dụng:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.order,java.sql,java.logging \
  --bind-services \
  --output build/order-runtime
```

Đường dẫn module path và danh sách module cần điều chỉnh theo môi trường. Trên Windows, ký tự phân tách path và cách viết biến môi trường khác với ví dụ shell POSIX.

Một runtime image có thể được kiểm tra bằng chính executable trong image:

```bash
build/order-runtime/bin/java --list-modules
build/order-runtime/bin/java -jar app.jar
```

Trong thực tế, JAR ứng dụng và dependency phải được đặt đúng vị trí hoặc được launcher cấu hình để nạp. Hãy chạy smoke test với image đã tạo, không chỉ chạy ứng dụng bằng JDK đầy đủ của máy phát triển.

### 4.4. Các lưu ý với `jlink`

- `jlink` tạo runtime image cho nền tảng mà công cụ đang chạy; không dùng một image Linux như runtime Windows.
- Module path phải cung cấp các module cần thiết. JAR trên classpath không tự động trở thành module có thể link.
- Một số thư viện dạng non-modular/automatic module có thể cần được modularize hoặc đóng gói theo cách khác trước khi đưa vào linked image.
- `--bind-services` hỗ trợ tìm service provider trong module path, nhưng không phát hiện mọi plugin được nạp bằng reflection hoặc cấu hình động.
- Cần kiểm tra các provider như JDBC driver, logging backend, crypto provider và locale data nếu ứng dụng dùng chúng.
- Runtime image không chứa compiler và toàn bộ công cụ phát triển; không dùng nó làm build JDK.
- Không nên chỉ kiểm tra kích thước image. Hãy kiểm tra startup, health check, luồng nghiệp vụ, TLS, timezone, charset và xử lý lỗi.

## 5. `jpackage`: đóng gói ứng dụng thành bộ cài native

`jpackage` được giới thiệu dưới dạng incubator ở JDK 14 và trở thành công cụ chuẩn từ JDK 16 (JEP 392). Vì vậy JDK 17 có `jpackage`, trong khi JDK 11 tiêu chuẩn không có công cụ này.

`jpackage` giúp tạo application image hoặc bộ cài theo hệ điều hành, có thể kèm runtime riêng. Nó phù hợp với ứng dụng desktop, công cụ nội bộ cài trên máy người dùng hoặc một số ứng dụng server cần phân phối như gói cài native.

### 5.1. Các kiểu đầu ra

Các loại gói tùy hệ điều hành và công cụ hỗ trợ:

| Nền tảng | Kiểu đầu ra thường dùng | Ghi chú |
|---|---|---|
| Windows | `app-image`, `exe`, `msi` | Gói native cần toolchain đóng gói Windows phù hợp |
| macOS | `app-image`, `dmg`, `pkg` | Bộ cài phải được tạo và kiểm tra trên macOS; ký/notarize theo yêu cầu phân phối |
| Linux | `app-image`, `deb`, `rpm` | Gói DEB/RPM cần công cụ đóng gói tương ứng trên môi trường build |

`app-image` là thư mục ứng dụng có launcher và runtime cần thiết; nó không phải installer native. `exe`, `msi`, `dmg`, `pkg`, `deb` hoặc `rpm` là các gói cài đặt theo hệ điều hành.

### 5.2. Đóng gói ứng dụng không modular

Ứng dụng có thể tiếp tục dùng classpath và JAR truyền thống. Ví dụ:

```bash
jpackage \
  --type app-image \
  --name OrderTool \
  --input build/libs \
  --main-jar order-tool.jar \
  --main-class com.example.order.Main \
  --dest build/packages
```

Ở đây, `--input` chỉ thư mục chứa các JAR cần đóng gói; `--main-jar` xác định JAR khởi chạy và `--main-class` xác định lớp main nếu manifest không cung cấp thông tin phù hợp. Cần đưa dependency runtime vào input theo cách mà launcher có thể nạp.

### 5.3. Đóng gói ứng dụng modular

Với ứng dụng có module descriptor và module path, có thể chỉ định module chính:

```bash
jpackage \
  --type app-image \
  --name OrderTool \
  --module-path mods \
  --module com.example.order/com.example.order.Main \
  --dest build/packages
```

Với ứng dụng cần runtime tùy chỉnh, có thể tạo runtime bằng `jlink` trước rồi truyền vào `jpackage` bằng `--runtime-image`:

```bash
jpackage \
  --type app-image \
  --name OrderTool \
  --input build/libs \
  --main-jar order-tool.jar \
  --main-class com.example.order.Main \
  --runtime-image build/order-runtime \
  --dest build/packages
```

Hai ví dụ minh họa hai kiểu đóng gói. Hãy chọn cách phù hợp với module model thực tế; không cần chuyển một ứng dụng classpath sang modular chỉ để dùng `jpackage`.

### 5.4. Công cụ native và yêu cầu build

`jpackage` tạo gói native cho nền tảng build. Các định dạng installer thường cần công cụ riêng của hệ điều hành, ví dụ toolchain tạo MSI/EXE trên Windows, công cụ đóng gói DEB/RPM trên Linux hoặc công cụ của Apple trên macOS.

Do đó:

- Tách job đóng gói theo OS/architecture nếu phải phát hành nhiều nền tảng.
- Ghi nhận phiên bản công cụ native và cấu hình signing.
- Không giả định một artifact installer có thể tạo trên mọi runner.
- Kiểm thử installer trên máy sạch hoặc VM tương ứng, không chỉ chạy thư mục build trên máy dev.
- Với macOS/Windows, xác minh signing, certificate, notarization và SmartScreen theo chính sách phân phối.
- Xem `jpackage --help` từ đúng JDK 17 vendor/build đang dùng để xác nhận option thực tế.

### 5.5. Launcher và runtime options

`jpackage` có thể cấu hình tên launcher, icon, version, shortcut, file association và các tùy chọn Java runtime. Nếu ứng dụng cần `--add-opens` hoặc system property, hãy đưa các option đó vào cấu hình launcher có kiểm soát, thay vì phụ thuộc vào câu lệnh khởi chạy thủ công của developer.

Không nhúng secret, token hoặc mật khẩu vào launcher option hay gói cài. Các cấu hình nhạy cảm cần được cung cấp qua secret store hoặc cơ chế cấu hình phù hợp ở môi trường chạy.

## 6. Các công cụ và thành phần bị loại bỏ trong giai đoạn 11–17

Một số pipeline cũ vẫn có thể gọi công cụ đã bị loại bỏ dù ứng dụng Java không trực tiếp tham chiếu API đó. Hãy kiểm kê cả shell script, Dockerfile, Gradle task, Maven plugin và quy trình release.

### 6.1. Pack200 và Unpack200

Pack200 từng được dùng để nén JAR, đặc biệt trong một số quy trình phân phối Java cũ. Công nghệ này đã deprecated for removal trong JDK 11 và bị loại bỏ từ JDK 14 theo JEP 367. JDK 17 không còn cung cấp:

- Lệnh `pack200` và `unpack200`.
- API `java.util.jar.Pack200` và các thành phần liên quan.

Nếu pipeline đang đóng gói hoặc giải nén artifact bằng Pack200, cần chuyển sang JAR/ZIP thông thường hoặc cơ chế phân phối hiện đại. Không nên đổi tên file `.pack.gz` thành `.jar`; cần cập nhật cả bước tạo, lưu trữ, tải xuống, giải nén và kiểm tra checksum.

### 6.2. Nashorn JavaScript engine

Nashorn được deprecated for removal trong JDK 11 và bị loại khỏi JDK từ JDK 15 theo JEP 372. Vì vậy, trên JDK 17, đoạn code tìm engine có thể không còn nhận được Nashorn mặc định:

```java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("nashorn");
```

Nếu ứng dụng cần JavaScript scripting, có thể chọn một engine độc lập được duy trì hoặc chuyển phần logic script sang một cơ chế khác. Việc thêm một Nashorn artifact độc lập có thể hỗ trợ một số trường hợp, nhưng cần kiểm tra phiên bản, khả năng tương thích và mức độ duy trì. Không nên giả định mọi script Nashorn cũ chạy nguyên trạng trên engine khác vì khác biệt về Java interop, API và semantics.

### 6.3. RMI Activation

RMI Activation đã deprecated for removal trong JDK 11 và bị loại khỏi JDK 17 theo JEP 407. Các API trong package `java.rmi.activation` và công cụ `rmid` không còn sẵn có như trước.

RMI core không bị loại bỏ toàn bộ. Nếu ứng dụng dùng activation system để kích hoạt remote object theo yêu cầu, cần thiết kế lại lifecycle và cơ chế khởi động service. Có thể chuyển sang service process do systemd, Windows Service, container orchestrator hoặc nền tảng vận hành quản lý, tùy kiến trúc.

### 6.4. RMI compiler `rmic`

`rmic` đã bị loại bỏ trước JDK 17, từ JDK 15. Các pipeline còn gọi `rmic` cần được thay đổi. Trước khi sửa, xác định ứng dụng đang dùng static stub generation hay dynamic stub mechanism; không phải ứng dụng RMI nào cũng cần một bước `rmic` riêng trong JDK mới.

### 6.5. AOT/JIT compiler thử nghiệm

Các công cụ thử nghiệm liên quan AOT/JIT như `jaotc` và Graal JIT compiler thử nghiệm trong JDK đã bị loại bỏ theo JEP 410 trong JDK 17. Nếu pipeline từng biên dịch ahead-of-time bằng `jaotc`, hãy xác định lý do sử dụng, benchmark và giải pháp runtime/compiler thay thế. Không coi AOT output cũ là artifact có thể dùng trực tiếp với JDK 17.

### 6.6. Công cụ JavaFX và các thành phần đã rời JDK 11

`javapackager` thuộc bộ công cụ JavaFX cũ và không còn được cung cấp cùng JDK 11. JavaFX cũng không còn được đóng gói trong JDK từ Java 11. Nếu migration thực tế bắt đầu từ JDK 8 hoặc một JDK vendor có JavaFX tích hợp, cần thay JavaFX bằng dependency riêng và xem xét `jpackage` cho bước đóng gói.

Java Web Start (`javaws`), `appletviewer` và một số công nghệ Java EE/CORBA cũng đã bị loại khỏi JDK 11 hoặc trước đó. Đây không phải thay đổi mới riêng của JDK 17, nhưng vẫn có thể xuất hiện trong script cũ, tài liệu build hoặc quy trình cài đặt được kế thừa.

### 6.7. Bảng kiểm nhanh công cụ

| Công cụ/API | Mốc thay đổi | Việc cần làm khi dùng JDK 17 |
|---|---|---|
| `jpackage` | Chuẩn hóa từ JDK 16 | Có thể dùng để tạo app image/installer; chuẩn hóa runner theo OS |
| `pack200`, `unpack200`, `Pack200` API | Loại bỏ từ JDK 14 | Thay bước nén/giải nén trong pipeline |
| Nashorn | Loại khỏi JDK từ JDK 15 | Chọn JavaScript engine độc lập hoặc thay thiết kế scripting |
| `rmic` | Loại bỏ từ JDK 15 | Xem lại quy trình sinh RMI stub |
| `jaotc` và Graal JIT thử nghiệm trong JDK | Loại bỏ theo JEP 410 trong JDK 17 | Thiết kế lại bước tối ưu/đóng gói AOT nếu còn dùng |
| RMI Activation / `rmid` | Loại bỏ từ JDK 17 | Thay cơ chế activation và quản lý lifecycle |
| `javapackager`/JavaFX trong JDK | Đã không còn trong JDK 11 | Dùng JavaFX dependency riêng và đánh giá `jpackage` |

## 7. Thay đổi trong cách tổ chức JAR, module và runtime dependency

### 7.1. Classpath và module path

Ứng dụng classpath vẫn được hỗ trợ trong JDK 17. Không bắt buộc chuyển mọi ứng dụng sang JPMS. Tuy nhiên, nếu muốn tạo runtime image tối giản bằng `jlink`, cần hiểu module graph và module path.

Classpath gom các class và resource vào một namespace không tên. Module path cung cấp các module có metadata và ranh giới truy cập rõ ràng. Một JAR không có `module-info.class` có thể được xử lý như automatic module trong một số tình huống module path, nhưng automatic module không đồng nghĩa với module có hợp đồng ổn định hoặc luôn có thể đưa trực tiếp vào linked runtime image.

Hãy quyết định rõ ứng dụng đang dùng:

- Classpath truyền thống với `-cp`/`-classpath`.
- Module path với module descriptor.
- Mô hình lai, trong đó ứng dụng modular gọi thư viện trên classpath hoặc automatic module.

Đừng đổi `-cp` thành `--module-path` một cách máy móc. Cách nạp class, tên module, access rule và service discovery có thể thay đổi.

### 7.2. JAR modular và JMOD

JAR có thể chứa `module-info.class` để khai báo tên module, dependency (`requires`), package được export (`exports`) và service (`uses`/`provides`). Có thể xem metadata module bằng:

```bash
jar --describe-module --file build/libs/order-domain.jar
```

JMOD là định dạng đóng gói module dùng trong quá trình phát triển/linking, có thể chứa native command, native library, cấu hình và resource ngoài nội dung JAR thông thường. Công cụ `jmod` hỗ trợ tạo, mô tả và liệt kê JMOD. Phần lớn ứng dụng doanh nghiệp không cần tự tạo JMOD; chỉ nên sử dụng khi có nhu cầu module image đặc thù.

### 7.3. Multi-release JAR

Một multi-release JAR có thể chứa các implementation khác nhau theo phiên bản Java trong các thư mục `META-INF/versions/<N>`. JVM chọn class phù hợp với runtime release. Khi nâng từ 11 lên 17, cần kiểm tra thư viện có nhánh implementation dành cho Java 17 hay không và artifact có được đóng gói đúng thuộc tính `Multi-Release: true` hay không.

Có thể dùng `jdeps --multi-release 17` để phân tích nhánh phù hợp với release 17 khi khảo sát dependency. Không được giả định mọi công cụ quét JAR đều chọn cùng nhánh class như JVM.

### 7.4. Tài nguyên runtime và provider

Khi tạo runtime image, đừng chỉ dựa vào danh sách module xuất hiện trong source. Kiểm tra các tài nguyên và provider được dùng ở runtime:

- JDBC driver và `java.sql`/`java.naming` khi cần.
- Logging provider và bridge.
- Security provider, keystore và truststore.
- Locale, timezone và charset data.
- XML parser, transformer và service provider.
- Native library, JNI và thư viện phụ thuộc của hệ điều hành.
- ServiceLoader provider và plugin được cấu hình ngoài source.

Một runtime image có thể khởi động thành công nhưng thất bại ở luồng hiếm khi chạy nếu thiếu provider hoặc resource. Hãy xây dựng test đại diện cho những đường đi này.

## 8. Công cụ khảo sát và kiểm tra trước khi đóng gói

JDK 17 cung cấp nhiều công cụ giúp kiểm tra dependency và API đã deprecated. Nên chạy chúng trên artifact được tạo từ baseline và trên artifact đã build bằng JDK 17.

### 8.1. `jdeps`

Một số lệnh thường dùng:

```bash
# Xem dependency module của ứng dụng
jdeps --print-module-deps --class-path "lib/*" app.jar

# Tìm tham chiếu tới JDK internal APIs
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar

# Xem dependency theo package
jdeps --summary app.jar
```

`jdeps` hỗ trợ phân tích bytecode tĩnh. Nó không phát hiện toàn bộ class được nạp bằng reflection, tên plugin trong cấu hình, native code hoặc giao tiếp giữa các dịch vụ.

### 8.2. `jdeprscan`

Dùng `jdeprscan` để khảo sát việc sử dụng API đã deprecated trong release mục tiêu:

```bash
jdeprscan --release 17 --class-path "lib/*" app.jar
```

Kết quả giúp phát hiện API cần chuyển đổi trước hoặc trong migration. Cần đọc kết quả cùng tài liệu API của JDK 17: deprecated không đồng nghĩa API đã bị xóa, và công cụ không thay thế compile/test để phát hiện mọi API không còn tồn tại.

### 8.3. `jar`, `jmod` và `java`

Các lệnh hữu ích:

```bash
jar --describe-module --file app.jar
jmod describe java.base.jmod
java --list-modules
java --version
javac --version
```

Chạy chúng từ đúng `JAVA_HOME` mà pipeline sử dụng. Nếu máy cài nhiều JDK, `java --version` trong terminal không nhất thiết phản ánh JDK mà Gradle daemon, Maven toolchain hoặc container build đang dùng.

### 8.4. Kiểm tra API nội bộ và warning

Tìm trong source và script các dấu hiệu:

```text
sun.*
com.sun.*
--illegal-access
--add-opens
--add-exports
Pack200
pack200
unpack200
nashorn
java.rmi.activation
rmic
rmid
jaotc
javapackager
rt.jar
tools.jar
lib/ext
java.ext.dirs
java.endorsed.dirs
```

Đây là từ khóa khảo sát, không phải kết luận mọi kết quả đều là lỗi. Ví dụ, một package `com.sun.*` có thể thuộc thư viện bên thứ ba chứ không phải package nội bộ của JDK. Cần xác định module sở hữu class và nguồn dependency trước khi thay đổi.

## 9. Lựa chọn chiến lược đóng gói

Không phải ứng dụng nào cũng cần cùng một kiểu package. Quyết định phụ thuộc vào cách triển khai, mức kiểm soát runtime và yêu cầu vận hành.

| Kiểu triển khai | Cách đóng gói gợi ý | Điểm cần kiểm tra |
|---|---|---|
| Ứng dụng server trong container | JAR/WAR và JDK/JRE runtime image trong container | Base image, architecture, CA certificates, timezone, native libs, JVM options |
| Ứng dụng server cần runtime tối giản | `jlink` runtime image + application artifact | Module closure, service provider, locale, security provider và smoke test |
| Desktop Java | `jpackage` app image hoặc installer | Launcher, icon, signing, native packaging tool và update strategy |
| Công cụ CLI nội bộ | JAR + runtime được quản lý tập trung hoặc `jpackage` | Cách phân phối JDK, PATH, launcher, config và logging |
| Ứng dụng modular | Module path + `jlink`, có thể kết hợp `jpackage` | `module-info`, `uses/provides`, module graph và module version |
| Ứng dụng classpath truyền thống | JAR/dependency rõ ràng, có thể dùng `jpackage` | Manifest, classpath, dependency đóng gói và runtime image |

### 9.1. Đóng gói trong container

Với server application, một mô hình thường dùng là build artifact bằng JDK 17 rồi copy artifact vào runtime image tương ứng. Có thể dùng runtime image chuẩn của vendor hoặc image do `jlink` tạo.

Ví dụ Dockerfile nhiều stage mang tính minh họa:

```dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./gradlew clean bootJar

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/app.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Tên image và tag cần được chốt theo vendor, kiến trúc và chính sách cập nhật của tổ chức. Với runtime image tối giản do `jlink` tạo, stage cuối có thể copy image đó và launcher phù hợp. Cần kiểm tra CA certificates, timezone, user permissions, native library và các công cụ chẩn đoán mà đội vận hành cần.

### 9.2. Đóng gói desktop hoặc ứng dụng cài trên máy người dùng

Với desktop application, `jpackage` có thể tạo thư mục app image hoặc installer native. Hãy kiểm thử:

- Cài đặt và gỡ cài đặt trên máy sạch.
- Shortcut, icon, file association và launcher arguments.
- Quyền ghi dữ liệu, vị trí config và log.
- Update/upgrade installer từ phiên bản trước.
- Signing và xác minh nguồn phát hành.
- Hành vi khi runtime image đi kèm được cập nhật.

Không nên coi việc lệnh `jpackage` trả exit code 0 là bằng chứng installer hoạt động đúng. Phải cài và chạy artifact thực tế trên môi trường đích.

## 10. Quy trình migration JDK 11 lên 17 cho build và packaging

### Bước 1: Đóng băng baseline JDK 11

Ghi lại:

- JDK vendor, version và architecture.
- Gradle/Maven wrapper và phiên bản plugin.
- Compile release, toolchain và runtime JDK.
- Artifact hiện tại: JAR/WAR, container image, installer hoặc runtime image.
- Danh sách script và công cụ packaging được gọi trong CI/CD.
- Các system property, JVM argument và module option đang dùng.

Lưu artifact và build log của baseline để có thể so sánh sau migration.

### Bước 2: Kiểm kê giả định về cấu trúc JDK

Tìm các đường dẫn `rt.jar`, `tools.jar`, thư mục `jre`, `lib/ext`, endorsed directory và code đọc trực tiếp nội dung JDK. Xác định phần nào là script cũ còn được thực thi và phần nào chỉ là tài liệu hoặc code không còn dùng.

Thay việc truy cập file nội bộ bằng toolchain hoặc công cụ chuẩn. Không tự tạo lại cấu trúc thư mục cũ trong JDK 17.

### Bước 3: Kiểm tra công cụ đã bị loại bỏ

Tìm lệnh `pack200`, `unpack200`, `rmic`, `rmid`, `jaotc`, `javapackager` và các API như `Pack200`, `java.rmi.activation`. Kiểm tra cả script ngoài source Java, Gradle task, Maven plugin, Dockerfile và release pipeline.

Phân loại mỗi kết quả theo trạng thái: đang được gọi, chỉ còn trong tài liệu, chỉ dùng ở môi trường cũ hoặc không còn sử dụng. Chỉ thay những đường đi còn hoạt động và xác định rõ chức năng thay thế.

### Bước 4: Phân tích dependency và JDK internals

Chạy `jdeps --jdk-internals` và `jdeprscan --release 17` trên application artifact cùng dependency. Nâng các thư viện nền tảng lên phiên bản hỗ trợ JDK 17. Đặc biệt chú ý framework, ORM, bytecode enhancer, mocking library, serialization, logging, JDBC driver và thư viện native.

Nếu có `--add-opens`/`--add-exports`, ghi rõ package, module đích, thư viện yêu cầu và lý do. Mỗi flag nên gắn với một dependency cụ thể để có thể loại bỏ khi thư viện được nâng cấp.

### Bước 5: Nâng build tool và compiler environment

Xác minh phiên bản Gradle/Maven wrapper, plugin và CI runner hỗ trợ chạy trên JDK 17. Phân biệt JDK chạy build với toolchain dùng compile. Nếu cần duy trì hỗ trợ runtime Java 11, có thể dùng JDK 17 compiler với `--release 11`/cấu hình tương đương, sau khi xác nhận build tool và plugin hỗ trợ cấu hình đó.

Nếu mục tiêu là chuyển runtime production lên Java 17, đặt compile release và runtime JDK theo chính sách mục tiêu sau khi đã đánh giá source compatibility.

### Bước 6: Biên dịch và kiểm thử trên JDK 17

Chạy clean build trên JDK 17. Phân loại lỗi thành:

- API đã bị loại bỏ hoặc không còn được JDK cung cấp.
- Truy cập JDK internals bị chặn.
- Dependency/plugin không hỗ trợ JDK 17.
- Compiler hoặc module graph thay đổi.
- Runtime behavior, serialization, TLS, locale hoặc native library thay đổi.

Sau khi build thành công, chạy unit test, integration test và kiểm thử startup trên runtime thực tế. Test phải bao gồm những luồng sử dụng reflection, scripting, RMI, provider discovery hoặc resource hiếm gặp nếu hệ thống có các cơ chế đó.

### Bước 7: Thiết kế lại packaging

Chọn một trong các hướng phù hợp:

- Giữ JAR/WAR và dùng runtime image chuẩn JDK 17 trong container/server.
- Tạo runtime image riêng bằng `jlink` nếu cần kiểm soát module và kích thước runtime.
- Dùng `jpackage` để tạo app image hoặc installer native cho ứng dụng cần phân phối trên desktop/máy người dùng.

Không cần áp dụng cả `jlink` và `jpackage` cho mọi ứng dụng. Chọn theo yêu cầu triển khai, vận hành, bảo mật và cập nhật.

### Bước 8: Kiểm thử artifact đóng gói

Kiểm tra artifact trên môi trường sạch, không dựa vào JDK hoặc thư viện có sẵn trên máy build. Với container, chạy image cuối; với installer, cài đặt và khởi chạy trên OS mục tiêu; với custom runtime, chạy test bằng `bin/java` nằm trong runtime image.

### Bước 9: Phát hành có kiểm soát và giữ khả năng rollback

Phát hành theo nhóm ứng dụng hoặc môi trường. Theo dõi startup, error rate, latency, memory, CPU, TLS/connectivity và các lỗi classloading. Nếu schema hoặc contract được thay đổi cùng lúc, cần tách rõ nguyên nhân khi rollback. Lưu lại JDK vendor/build, base image digest, dependency lock/resolution và packaging options của artifact đã phát hành.

## 11. Những lỗi thường gặp khi nâng JDK 11 lên 17

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `InaccessibleObjectException` | Deep reflection vào package JDK không mở | Nâng thư viện; thay API; dùng `--add-opens` hẹp nếu cần chuyển tiếp |
| `IllegalAccessError` | Module không export package hoặc access rule thay đổi | Kiểm tra module/package; cân nhắc `--add-exports` có phạm vi rõ |
| `ClassNotFoundException` cho Nashorn | Engine không còn trong JDK 17 | Thêm engine độc lập phù hợp hoặc thay scripting design |
| Không tìm thấy `Pack200` hoặc `pack200` | API/tool đã bị loại khỏi JDK | Thay pipeline bằng JAR/ZIP thông thường |
| Không tìm thấy `java.rmi.activation` | RMI Activation đã bị loại trong JDK 17 | Thiết kế lại activation/lifecycle |
| `rmic` không tồn tại | Công cụ đã bị loại trước JDK 17 | Xem lại nhu cầu stub generation và cơ chế RMI đang dùng |
| `jlink` báo thiếu module | Module path hoặc danh sách module không đầy đủ | Dùng `jdeps`, kiểm tra module descriptor và service provider |
| Ứng dụng chạy với JDK đầy đủ nhưng lỗi trong custom image | Runtime image thiếu module/provider/resource | Kiểm tra module closure và chạy test bằng image cuối |
| `jpackage` không tạo được installer | Thiếu native packaging tool hoặc runner sai OS | Chuẩn bị toolchain/runner đúng nền tảng; kiểm tra `jpackage --help` |
| Installer tạo được nhưng ứng dụng không chạy trên máy sạch | Runtime, file config, native library hoặc launcher sai | Cài và test trên máy sạch, xác minh mọi file được đóng gói |

## 12. Checklist hoàn tất migration packaging

Trước khi xác nhận pipeline đã sẵn sàng với JDK 17, hãy kiểm tra:

- [ ] JDK vendor, version, architecture và build toolchain đã được ghi nhận.
- [ ] Không còn script đang hoạt động phụ thuộc `rt.jar`, `tools.jar`, JRE lồng trong JDK hoặc `lib/ext`.
- [ ] Không còn bước packaging đang gọi Pack200/unpack200.
- [ ] Đã xác minh ứng dụng có dùng Nashorn, RMI Activation, `rmic` hoặc `jaotc` hay không.
- [ ] Đã rà soát truy cập JDK internals bằng `jdeps` và kiểm thử runtime.
- [ ] Các `--add-opens`/`--add-exports` còn lại có lý do, owner và kế hoạch loại bỏ.
- [ ] Build tool, plugin và dependency hỗ trợ JDK 17.
- [ ] Đã quyết định rõ classpath/module path và chiến lược runtime image.
- [ ] Nếu dùng `jlink`, module list và service provider đã được kiểm tra bằng runtime image thực tế.
- [ ] Nếu dùng `jpackage`, native toolchain, signing và OS-specific build runner đã sẵn sàng.
- [ ] Artifact cuối đã được chạy trên môi trường sạch tương ứng với production.
- [ ] CI lưu được thông tin JDK, dependency, image digest và tham số đóng gói để tái tạo artifact.
- [ ] Có phương án rollback và theo dõi sau phát hành.

## 13. Kết luận

Khi chuyển từ JDK 11 lên 17, cần rà soát cả cấu trúc module image, truy cập JDK internals, công cụ bị loại bỏ và cách tạo runtime/application package. `jlink` đã có từ Java 9 và có thể tạo runtime image tối giản; `jpackage` là bổ sung quan trọng từ JDK 16, hỗ trợ tạo app image và installer native trong JDK 17. Trong khi đó, Pack200, Nashorn, RMI Activation và một số công cụ AOT/RMI cũ đã rời JDK ở các release nằm giữa 11 và 17.

Hãy bắt đầu bằng inventory các script và artifact đang dùng, phân tích dependency bằng `jdeps`/`jdeprscan`, sửa truy cập nội bộ theo API được hỗ trợ, sau đó chọn chiến lược đóng gói phù hợp. Việc kiểm thử phải chạy trên chính runtime image, container hoặc installer cuối cùng; build thành công bằng JDK đầy đủ chưa đủ chứng minh package triển khai hoạt động đúng.
