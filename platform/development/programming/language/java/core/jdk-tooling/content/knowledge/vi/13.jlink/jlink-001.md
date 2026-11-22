# Lệnh jlink

`jlink` là công cụ trong JDK dùng để **liên kết các Java module và tạo custom runtime image**. Runtime image chứa JVM cùng tập module cần thiết để chạy một ứng dụng. Nhờ đó, ứng dụng có thể được phân phối cùng một runtime nhỏ hơn JDK đầy đủ, với các thành phần được chọn theo dependency của ứng dụng.

Cú pháp tổng quát:

```text
jlink --module-path <module-path>
      --add-modules <module>[,<module>...]
      --output <directory>
      [other-options]
```

Ba phần quan trọng nhất:

- `--module-path`: nơi tìm các module đầu vào.
- `--add-modules`: các module gốc cần đưa vào runtime image.
- `--output`: thư mục nhận runtime image được tạo.

`jlink` làm việc với Java module có thể liên kết, chẳng hạn module trong JMOD, modular JAR hoặc exploded module. Nó không đóng gói một ứng dụng classpath bất kỳ thành runtime image chỉ bằng cách truyền tên một tệp JAR thông thường.

## 1. Runtime image là gì?

Một JDK cài trên máy thường chứa nhiều công cụ phát triển như `javac`, `javadoc`, `jdb`, `jar`, `jlink` và các module phục vụ build. Ứng dụng khi triển khai có thể chỉ cần JVM và một phần module Java SE.

`jlink` đọc đồ thị phụ thuộc module và tạo image gồm các thành phần cần thiết. Ví dụ cấu trúc một image:

```text
app-image/
├── bin/
│   ├── java
│   └── app
├── conf/
├── include/
├── legal/
├── lib/
│   └── modules
└── release
```

Các thư mục và tệp thực tế phụ thuộc hệ điều hành, JDK và các module được link. Nếu có khai báo launcher bằng `--launcher`, image sẽ có thêm command launcher trong thư mục `bin`.

Runtime image thường nhỏ hơn JDK đầy đủ vì không chứa toàn bộ công cụ phát triển và module không được yêu cầu. Nó vẫn chứa runtime cần để chạy ứng dụng; đây không phải một tệp executable native duy nhất.

## 2. Cơ chế module resolution khi link

`jlink` không đơn giản sao chép mọi JAR có trong thư mục. Nó phân giải module graph dựa trên các khai báo module và các tùy chọn đầu vào.

Quy trình khái quát:

1. Đọc module path và tìm các module có thể quan sát.
2. Xác định root modules được chọn bằng `--add-modules`.
3. Phân giải các quan hệ `requires` và dependency bắc cầu.
4. Xác định các service provider nếu bật service binding.
5. Kiểm tra các module đã phân giải có thể liên kết hay không.
6. Ghi runtime image và áp dụng các plugin được chọn.

Ví dụ module descriptor:

```java
module com.example.app {
    requires java.logging;
}
```

Nếu chọn `com.example.app`, module `java.logging` cũng được đưa vào vì là dependency bắt buộc. Các module cần thiết khác được phân giải theo quan hệ phụ thuộc của chúng.

Các dependency được nạp bằng reflection, tên lớp cấu hình trong tệp hoặc cơ chế plugin có thể không được thể hiện đầy đủ trong `requires`. Khi ứng dụng dùng những module đó, hãy bổ sung root module thích hợp bằng `--add-modules` và kiểm thử image thực tế.

## 3. Chuẩn bị một ứng dụng modular

Ví dụ tạo ứng dụng module tên `com.example.app`:

```text
project/
└── src/
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
```

Nội dung `module-info.java`:

```java
module com.example.app {
}
```

Nội dung `Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from custom runtime");
    }
}
```

Biên dịch module vào thư mục `mods`:

```sh
mkdir -p mods/com.example.app
javac -d mods/com.example.app \
  src/com.example.app/module-info.java \
  src/com.example.app/com/example/app/Main.java
```

Sau khi biên dịch:

```text
mods/
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
```

Thư mục `mods/com.example.app` là exploded module: một module đã được phân giải thành cấu trúc thư mục thay vì đóng gói trong JAR/JMOD.

Kiểm tra module descriptor:

```sh
jar --describe-module --file mods/com.example.app
```

Với exploded module, có thể dùng công cụ thích hợp để kiểm tra descriptor hoặc chạy `jlink` trực tiếp trên module path. Tên module phải khớp với khai báo trong `module-info.java`.

## 4. Tạo runtime image cơ bản

Giả sử biến môi trường `JAVA_HOME` trỏ đến JDK đang dùng. Thư mục `$JAVA_HOME/jmods` chứa các JMOD của JDK đó; thư mục `mods` chứa exploded module vừa biên dịch.

Trên Linux/macOS:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output app-image
```

Trên Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME/jmods;mods" --add-modules com.example.app --output app-image
```

Ký tự phân tách module path khác nhau theo hệ điều hành:

| Hệ điều hành | Ký tự phân tách |
|---|---|
| Windows | Dấu chấm phẩy `;` |
| Linux/macOS | Dấu hai chấm `:` |

Thư mục output phải chưa tồn tại hoặc đang rỗng. Nếu `app-image` đã có nội dung, hãy chọn một đường dẫn mới hoặc dọn đúng thư mục build trước khi chạy lại.

Sau khi tạo thành công, image chứa các module runtime cần thiết. Chạy chương trình bằng Java trong image:

```sh
./app-image/bin/java -m com.example.app/com.example.app.Main
```

Kết quả:

```text
Hello from custom runtime
```

Trên Windows, chạy:

```powershell
.\app-image\bin\java.exe -m com.example.app/com.example.app.Main
```

Image này có thể chạy ứng dụng mà không cần dùng lệnh `java` của JDK cài trên máy, miễn là image được tạo đúng nền tảng và dependency cần thiết đã được đưa vào.

## 5. Tạo launcher riêng bằng --launcher

Nếu muốn người dùng chạy ứng dụng bằng một command ngắn, có thể tạo launcher bằng `--launcher`:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --launcher app=com.example.app/com.example.app.Main \
  --output app-image
```

Cú pháp:

```text
--launcher <command>=<module>[/<main-class>]
```

- `command`: tên launcher được tạo trong thư mục `bin`.
- `module`: tên module có điểm vào.
- `main-class`: tên lớp đầy đủ chứa `public static void main(String[] args)`.

Nếu module đã khai báo main class trong module descriptor bằng chỉ thị `main-class`, có thể bỏ phần `/<main-class>` theo cú pháp được hỗ trợ.

Sau khi tạo image, chạy launcher:

```sh
./app-image/bin/app
```

Kết quả:

```text
Hello from custom runtime
```

Launcher là command khởi chạy Java module bằng runtime đi kèm image. Nó khác native command do ứng dụng tự cung cấp và đóng gói trong JMOD bằng `jmod --cmds`.

## 6. Các tùy chọn jlink quan trọng

| Tùy chọn | Công dụng |
|---|---|
| `--module-path` | Khai báo nơi tìm module đầu vào |
| `--add-modules` | Chọn root module cần link; nhận danh sách phân tách bằng dấu phẩy |
| `--bind-services` | Tìm và liên kết service provider cùng các dependency của chúng |
| `--limit-modules` | Giới hạn tập module có thể quan sát trong quá trình resolution |
| `--output` | Chọn thư mục runtime image đầu ra |
| `--launcher` | Tạo command launcher cho module/main class |
| `--compress=0` | Không nén resource |
| `--compress=1` | Chia sẻ chuỗi hằng số trong resource |
| `--compress=2` | Nén resource bằng ZIP |
| `--strip-debug` | Loại thông tin debug khỏi các module được link |
| `--no-header-files` | Không đưa header file native vào image |
| `--no-man-pages` | Không đưa man page vào image |
| `--strip-native-commands` | Loại native command khỏi image |
| `--include-locales` | Giới hạn dữ liệu locale được đưa vào image |
| `--save-opts` | Lưu các tùy chọn link để có thể dùng lại |

Danh sách tùy chọn và plugin có thể thay đổi theo phiên bản JDK. Xem trợ giúp của công cụ đang sử dụng:

```sh
jlink --help
jlink --list-plugins
```

Không nên bật mọi plugin chỉ để giảm kích thước. Hãy xác định yêu cầu của ứng dụng, áp dụng từng tùy chọn rồi kiểm thử runtime image.

## 7. Chọn module gốc với --add-modules

`--add-modules` xác định module gốc cần đưa vào image. Ví dụ:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,java.sql \
  --output app-image
```

Lệnh trên chọn cả `com.example.app` và `java.sql` làm root module. Các module bắt buộc được tham chiếu qua `requires` sẽ được phân giải thêm.

Có thể dùng:

```text
--add-modules ALL-MODULE-PATH
```

để thêm tất cả module quan sát được trên module path. Cách này tiện cho thử nghiệm nhưng có thể tạo image lớn hơn đáng kể và làm mất lợi ích của việc chọn module tối thiểu.

Nếu ứng dụng tải module theo tên lúc chạy hoặc sử dụng framework plugin, hãy xác định module cần thiết và thêm tường minh. Chỉ thêm module có căn cứ từ cấu hình ứng dụng và kiểm thử.

## 8. Service binding với --bind-services

Java ServiceLoader cho phép module sử dụng một service interface và tìm implementation được cung cấp bởi module khác.

Ví dụ module sử dụng service:

```java
module com.example.app {
    uses com.example.spi.ReportService;
}
```

Module cung cấp implementation:

```java
module com.example.report.csv {
    requires com.example.app;
    provides com.example.spi.ReportService
        with com.example.report.csv.CsvReportService;
}
```

Khi tạo runtime image, `--bind-services` yêu cầu linker tìm các provider của service được các module đã chọn sử dụng, rồi liên kết provider cùng dependency cần thiết.

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --bind-services \
  --output app-image
```

Service binding có thể làm image chứa thêm module provider. Điều này cần thiết nếu ứng dụng dựa vào ServiceLoader để tìm implementation, nhưng không nên bật một cách máy móc nếu không cần service provider.

## 9. Giảm kích thước runtime image

Có thể kết hợp các plugin để giảm dung lượng:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --compress=2 \
  --output app-image
```

Các tùy chọn trên:

- `--strip-debug`: loại thông tin debug khỏi module được link.
- `--no-header-files`: loại native header file không cần cho runtime thông thường.
- `--no-man-pages`: loại trang hướng dẫn.
- `--compress=2`: nén resource bằng ZIP.

Nén có thể giảm kích thước image nhưng có thể ảnh hưởng thời gian đọc tài nguyên khi chạy. Hãy đo kích thước và hiệu năng trên ứng dụng thực tế.

Không loại native command nếu ứng dụng hoặc quy trình triển khai cần chúng. Tương tự, đừng loại debug metadata nếu cần phân tích lỗi production hoặc dùng công cụ phụ thuộc thông tin đó.

## 10. Giới hạn dữ liệu locale

JDK có module `jdk.localedata` chứa dữ liệu locale bổ sung. Nếu image cần hỗ trợ một tập locale cụ thể, có thể chọn bằng plugin `--include-locales`.

Ví dụ:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,jdk.localedata \
  --include-locales=en,vi \
  --output app-image
```

Trong ví dụ, module `jdk.localedata` được thêm rõ ràng và dữ liệu locale được giới hạn cho tiếng Anh và tiếng Việt. Danh sách locale cần khớp với yêu cầu sản phẩm và các locale tag mà JDK hỗ trợ.

Nếu ứng dụng dùng định dạng ngày, số, tiền tệ hoặc collation theo locale khác, hãy kiểm thử trực tiếp trên image. Thiếu locale data có thể làm hành vi hiển thị hoặc xử lý văn bản khác với JDK đầy đủ.

## 11. Giới hạn module universe với --limit-modules

`--limit-modules` giới hạn tập module mà linker có thể quan sát khi giải quyết module graph.

Ví dụ:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --limit-modules java.base,java.logging,com.example.app \
  --output app-image
```

Tùy chọn này có thể giúp kiểm soát phạm vi module và tránh vô tình quan sát module ngoài dự kiến. Tuy nhiên, nếu một module bắt buộc hoặc service provider không nằm trong tập cho phép, quá trình link sẽ thất bại hoặc image thiếu chức năng.

Chỉ dùng `--limit-modules` sau khi hiểu dependency graph. Để chẩn đoán, có thể xem module descriptor bằng:

```sh
jar --describe-module --file path/to/library.jar
jmod describe path/to/module.jmod
```

## 12. Module path và định dạng module đầu vào

Module path có thể chứa:

- JMOD file, thường được cung cấp trong thư mục `jmods` của JDK.
- Modular JAR có `module-info.class`.
- Exploded module, là thư mục chứa module descriptor và các class file.

JAR chỉ có manifest hoặc chỉ chứa class file theo classpath truyền thống không tự động trở thành module tường minh phù hợp để link. Automatic module cũng không phải đầu vào thay thế cho một module tường minh trong quy trình jlink thông thường.

Có thể xem tên module của một JAR:

```sh
jar --describe-module --file library.jar
```

Có thể xem mô tả JMOD:

```sh
jmod describe library.jmod
```

Các module đầu vào phải có dependency được phân giải đầy đủ. Nếu một module yêu cầu module khác mà module đó không có trên module path, `jlink` sẽ báo lỗi resolution.

Nên dùng JMOD của cùng JDK mà bạn đang dùng để link. Trộn các JMOD từ nhiều phiên bản JDK có thể gây lỗi do khác biệt phiên bản module, class file hoặc cấu trúc nội bộ.

## 13. Kiểm tra runtime image sau khi tạo

Sau khi `jlink` chạy thành công, kiểm tra image bằng chính executable trong image.

Liệt kê các module:

```sh
./app-image/bin/java --list-modules
```

Kiểm tra phiên bản runtime:

```sh
./app-image/bin/java -version
```

Chạy module:

```sh
./app-image/bin/java -m com.example.app/com.example.app.Main
```

Chạy launcher nếu đã cấu hình:

```sh
./app-image/bin/app
```

Trên Windows, các executable tương ứng nằm trong `app-image\bin`, ví dụ `java.exe` và launcher có phần mở rộng phù hợp.

Kiểm tra tệp `release` ở thư mục gốc image để xem thông tin phiên bản và module. Kiểm tra trực tiếp thư mục `bin` nếu cần xác nhận command native hoặc launcher cụ thể.

Một image tạo thành công vẫn cần kiểm thử chức năng. Hãy chạy test tích hợp, kiểm tra file cấu hình, locale, TLS/security provider, logging, native library và các đường dẫn tài nguyên mà ứng dụng cần.

## 14. Tính tương thích nền tảng

Runtime image được tạo cho hệ điều hành và kiến trúc của môi trường JDK/linker tương ứng. `jlink` không phải công cụ cross-compiler cho phép tạo image Windows trên Linux chỉ bằng cách đổi một tham số.

Các thành phần native trong image, chẳng hạn JVM library và native command, phụ thuộc định dạng binary và ABI của nền tảng. Vì vậy:

- Tạo image Windows bằng JDK/toolchain phù hợp trên Windows.
- Tạo image Linux bằng JDK/toolchain phù hợp trên Linux.
- Tạo image macOS bằng JDK/toolchain phù hợp trên macOS.
- Kiểm thử image trên kiến trúc CPU mục tiêu.
- Kiểm tra các native library phụ thuộc vào hệ điều hành.

Nếu sản phẩm hỗ trợ nhiều nền tảng, hãy tạo và kiểm thử một image riêng cho từng nền tảng/kiến trúc. Không phát hành cùng một runtime image cho tất cả hệ điều hành.

## 15. jlink và các công cụ JDK liên quan

| Công cụ | Vai trò |
|---|---|
| `javac` | Biên dịch mã nguồn Java thành class file |
| `jar` | Tạo và thao tác với JAR; mô tả module của modular JAR |
| `jmod` | Tạo, liệt kê, mô tả và giải nén JMOD |
| `jdeps` | Phân tích dependency của class/JAR/module |
| `jlink` | Liên kết module và tạo custom runtime image |
| `java` | Chạy ứng dụng bằng JVM |
| `jimage` | Kiểm tra hoặc thao tác với định dạng JDK runtime image |

Một quy trình thường gặp:

```text
.java source
    |
    v
javac
    |
    v
Exploded module / modular JAR
    |
    v
jmod (nếu cần đóng gói module thành JMOD)
    |
    v
jlink
    |
    v
Custom runtime image
    |
    v
java hoặc launcher trong image
```

Không phải dự án nào cũng cần tạo JMOD trung gian. Nếu module đã ở dạng exploded module hoặc modular JAR, có thể đưa trực tiếp lên module path của `jlink`.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Error: Module ... not found` | Module không nằm trên module path hoặc tên module sai | Kiểm tra `--module-path`, tên trong module descriptor và đường dẫn JMOD/JAR |
| `Module ... not found, required by ...` | Thiếu dependency bắt buộc | Bổ sung module vào module path và kiểm tra khai báo `requires` |
| `automatic module ... cannot be used with jlink` | Đầu vào là automatic module thay vì module tường minh phù hợp | Dùng modular JAR/JMOD có descriptor hoặc chuyển dependency sang module hóa rõ ràng |
| `directory exists and is not empty` | Thư mục output đã tồn tại và có nội dung | Chọn thư mục output mới hoặc dọn đúng thư mục build rồi chạy lại |
| Image tạo được nhưng ứng dụng lỗi `ClassNotFoundException` | Thiếu module được tải động hoặc dependency không được khai báo | Bổ sung module cần thiết bằng `--add-modules` và kiểm thử lại |
| ServiceLoader không tìm thấy provider | Provider module không được link hoặc thiếu service binding | Kiểm tra `uses`/`provides`, module path và cân nhắc `--bind-services` |
| Image thiếu locale | Thiếu `jdk.localedata` hoặc locale không được include | Thêm module và cấu hình `--include-locales` |
| Runtime image không chạy trên hệ điều hành khác | Image chứa native binary cho nền tảng build | Tạo image riêng bằng JDK phù hợp với target |
| Image quá lớn | Chọn quá nhiều module hoặc chưa dùng plugin phù hợp | Xem module graph, chọn root module tối thiểu và đo tác động plugin |
| Launcher không xuất hiện | Cú pháp `--launcher` sai hoặc module/main class không hợp lệ | Kiểm tra tên module, tên lớp và danh sách file trong `bin` |
| Runtime thiếu command native | Command không có trong module hoặc đã bị strip | Kiểm tra JMOD `bin/`, cấu hình `--cmds` và plugin `--strip-native-commands` |
| Ứng dụng chạy bằng JDK đầy đủ nhưng lỗi trong image | Image thiếu resource, provider, locale, module hoặc native dependency | Kiểm thử trên image, bổ sung đúng thành phần và link lại |

Khi gặp lỗi, trước tiên kiểm tra module path và module descriptor, sau đó kiểm tra root module và dependency. Nếu link thành công nhưng ứng dụng lỗi khi chạy, hãy kiểm tra những thành phần được nạp động, service provider, resource và native library.

## 17. Checklist tạo custom runtime image

- [ ] Ứng dụng đã được tổ chức thành module có descriptor phù hợp.
- [ ] Module path chứa các module ứng dụng và JDK cần thiết.
- [ ] Đã chọn root module bằng `--add-modules`.
- [ ] Dependency bắt buộc và module được tải động đã được tính đến.
- [ ] Service provider đã được xử lý nếu ứng dụng dùng ServiceLoader.
- [ ] Output directory chưa tồn tại hoặc đang rỗng.
- [ ] Launcher được khai báo nếu muốn command khởi chạy riêng.
- [ ] Plugin nén/strip/locale phù hợp với yêu cầu sản phẩm.
- [ ] Image được tạo cho đúng hệ điều hành và kiến trúc.
- [ ] Đã chạy `java --list-modules` từ image để xác nhận module.
- [ ] Đã chạy ứng dụng bằng runtime image, không chỉ bằng JDK phát triển.
- [ ] Đã kiểm thử dependency, resource, locale, TLS và native library trên môi trường đích.

## 18. Tài liệu tham khảo

- Oracle JDK Tool Reference — The `jlink` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html
- Oracle JDK Tool Reference — The `jmod` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jmod.html
- Java Platform Module System — Java Language and JVM specifications: https://docs.oracle.com/javase/specs/

`jlink` biến tập module đã được phân giải thành một runtime image có thể phân phối cùng ứng dụng. Khi chọn đúng root modules, dependency, launcher và plugin, bạn có thể tạo runtime gọn hơn, dễ kiểm thử và phù hợp với nền tảng triển khai.