# Icon package với công cụ jpackage

## 1. Icon package là gì?

Trong quy trình đóng gói ứng dụng Java, icon package là biểu tượng nhận diện được gắn vào application image, launcher và gói cài đặt do `jpackage` tạo ra. Icon giúp người dùng nhận biết ứng dụng trong File Explorer, Finder, menu ứng dụng, desktop shortcut hoặc danh sách ứng dụng đã cài.

`jpackage` là công cụ đóng gói ứng dụng đi kèm JDK. Công cụ có thể tạo application image chứa launcher và runtime cần thiết, hoặc tạo installer theo định dạng của hệ điều hành. Tùy chọn chính để chỉ định biểu tượng là `--icon`:

~~~bash
jpackage --type app-image --name IconDemo --icon path/to/icon-file
~~~

Đường dẫn icon có thể là đường dẫn tuyệt đối hoặc tương đối với thư mục làm việc hiện tại của tiến trình chạy `jpackage`. Khi đường dẫn có dấu cách, đặt toàn bộ đường dẫn trong dấu nháy.

Cần phân biệt ba loại biểu tượng:

- **Application/package icon:** biểu tượng ứng dụng được cấu hình khi đóng gói bằng `--icon`.
- **Icon của từng launcher:** mỗi launcher bổ sung có thể có icon riêng qua cấu hình `--add-launcher`.
- **Icon trong cửa sổ ứng dụng:** do mã giao diện Java đặt lúc runtime, ví dụ JavaFX `Stage`. Tùy chọn `--icon` không tự thay thế icon trong cửa sổ do ứng dụng tạo ra.

## 2. Định dạng icon theo hệ điều hành

`jpackage` cần tệp icon đúng định dạng của hệ điều hành đích. Không đổi phần mở rộng của một ảnh PNG thành ICO hoặc ICNS; nội dung tệp phải thực sự đúng định dạng.

| Hệ điều hành | Định dạng icon | Ghi chú |
|---|---|---|
| Windows | `.ico` | Dùng cho launcher và package. Nên tạo ICO có nhiều kích thước để Windows chọn phiên bản phù hợp. |
| macOS | `.icns` | Dùng cho icon của application bundle và launcher trên macOS. |
| Linux | `.png` | Icon được dùng trong tích hợp desktop; tệp desktop có thể tham chiếu tới icon. |

Trên Linux, icon thường được tham chiếu bởi tệp `.desktop` thay vì nhúng vào launcher native như trên Windows. Vì vậy, khi kiểm tra, hãy xem cả application image, desktop entry và đường dẫn icon.

Các định dạng này áp dụng cho cả icon chính và icon riêng của launcher bổ sung. Tệp dùng cho file association cũng phải có định dạng phù hợp với hệ điều hành.

## 3. Chuẩn bị artwork trước khi đóng gói

Nên chuẩn bị một bản thiết kế nguồn có thể xuất ra từng định dạng nền tảng. Một icon tốt cần rõ khi hiển thị ở kích thước nhỏ, có độ tương phản đủ và không phụ thuộc vào chi tiết quá mảnh.

Khuyến nghị:

- Thiết kế bố cục vuông, đặt hình chính ở vùng an toàn để tránh bị cắt khi hệ điều hành áp dụng mask hoặc hiệu ứng hiển thị.
- Dùng nền trong suốt nếu artwork cần hòa vào desktop hoặc dock.
- Tạo ICO nhiều kích thước, chẳng hạn 16, 32, 48, 64, 128 và 256 pixel, để Windows có lựa chọn phù hợp.
- Với ICNS, cung cấp các representation cần thiết cho màn hình macOS có mật độ điểm ảnh khác nhau.
- Với PNG trên Linux, xuất bản có độ phân giải cao, thường 256 hoặc 512 pixel, để desktop environment có thể thu nhỏ.
- Kiểm tra icon trên nền sáng và tối, trong taskbar/dock và ở kích thước nhỏ.
- Giữ các file icon trong thư mục assets có tên rõ theo nền tảng.

Ví dụ cấu trúc:

~~~text
project/
├── src/
│   └── com/example/IconDemo.java
├── assets/
│   ├── windows/
│   │   └── icon-demo.ico
│   ├── macos/
│   │   └── icon-demo.icns
│   └── linux/
│       └── icon-demo.png
├── classes/
├── input/
└── dist/
~~~

Có thể dùng cùng một artwork gốc cho mọi nền tảng, nhưng phải xuất riêng thành ICO, ICNS và PNG. Không nên chỉ đổi đuôi tệp.

## 4. Chuẩn bị một ứng dụng Java mẫu

Tạo tệp `src/com/example/IconDemo.java`:

~~~java
package com.example;

public class IconDemo {
    public static void main(String[] args) {
        System.out.println("Icon package ready");
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
mkdir -p classes input dist
javac --release 17 -d classes src/com/example/IconDemo.java
~~~

Đóng gói class thành JAR:

~~~bash
jar --create --file input/icon-demo.jar --main-class com.example.IconDemo -C classes .
~~~

Thư mục `input` chứa JAR chính của ứng dụng. `jpackage` sẽ dùng `--input` để lấy các file cần đóng gói; `--main-jar` chỉ ra JAR chính và `--main-class` chỉ ra lớp có phương thức `main`.

Kiểm tra JAR trước khi package:

~~~bash
jar --list --file input/icon-demo.jar
~~~

Trong output cần có entry:

~~~text
META-INF/MANIFEST.MF
com/example/IconDemo.class
~~~

## 5. Gắn icon chính bằng `--icon`

### Windows

Dùng tệp ICO:

~~~powershell
jpackage --type app-image --input input --name IconDemo --main-jar icon-demo.jar --main-class com.example.IconDemo --icon assets/windows/icon-demo.ico --win-console --dest dist --verbose
~~~

Sau khi tạo application image, launcher nằm trong thư mục output:

~~~powershell
.\dist\IconDemo\IconDemo.exe
~~~

Stdout:

~~~text
Icon package ready
~~~

`--win-console` tạo launcher console cho ứng dụng cần tương tác terminal hoặc ghi stdout/stderr. Với ứng dụng desktop không cần console, có thể bỏ tùy chọn này.

### macOS

Dùng tệp ICNS:

~~~bash
jpackage --type app-image --input input --name IconDemo --main-jar icon-demo.jar --main-class com.example.IconDemo --icon assets/macos/icon-demo.icns --dest dist --verbose
~~~

Application image trên macOS thường là bundle `IconDemo.app`. Kiểm tra icon của bundle trong Finder hoặc Dock sau khi tạo.

### Linux

Dùng tệp PNG:

~~~bash
jpackage --type app-image --input input --name IconDemo --main-jar icon-demo.jar --main-class com.example.IconDemo --icon assets/linux/icon-demo.png --dest dist --verbose
~~~

Application image Linux chứa launcher và tài nguyên desktop. Khi kiểm tra icon, xác nhận đường dẫn PNG mà desktop entry sử dụng tồn tại trong application image hoặc vị trí cài đặt tương ứng.

Các lệnh trên được chạy trên từng hệ điều hành đích. `jpackage` không hỗ trợ tạo native package cho hệ điều hành khác từ một host bất kỳ.

## 6. Đóng gói ứng dụng modular

Với ứng dụng JPMS, có thể chỉ định module path và module chính. `--module` thay cho cặp `--main-jar`/`--main-class`.

Ví dụ:

~~~bash
jpackage --type app-image --name ModularIconDemo --module-path mods --module com.example.app/com.example.app.Main --icon assets/linux/modular-icon.png --dest dist
~~~

Thay đường dẫn icon bằng ICO trên Windows hoặc ICNS trên macOS khi build trên các hệ điều hành đó.

Không truyền đồng thời `--module` và `--main-jar`. Hãy chọn đúng chế độ theo cách ứng dụng được biên dịch và đóng gói.

## 7. Icon riêng cho launcher bổ sung

Một ứng dụng có thể cung cấp nhiều launcher với tham số hoặc mục đích khác nhau. Tùy chọn `--add-launcher` nhận tên launcher và một tệp properties. Trong properties, khóa `icon` chỉ định icon riêng cho launcher đó.

Ví dụ tệp `admin-launcher.properties` trên Windows:

~~~properties
icon=C:/project/assets/windows/admin.ico
arguments=--mode=admin
~~~

Tạo application image có launcher chính và launcher bổ sung:

~~~powershell
jpackage --type app-image --input input --name IconDemo --main-jar icon-demo.jar --main-class com.example.IconDemo --icon assets/windows/icon-demo.ico --add-launcher Admin=admin-launcher.properties --win-console --dest dist --verbose
~~~

Kết quả có launcher chính `IconDemo.exe` và launcher bổ sung `Admin.exe`. Launcher bổ sung dùng icon được khai báo trong `admin-launcher.properties`.

Với macOS, giá trị `icon` trỏ tới tệp `.icns`; với Linux, trỏ tới `.png`. Nếu không chỉ định icon riêng cho launcher bổ sung, launcher có thể dùng icon mặc định của nền tảng.

Có thể dùng cùng một launcher properties để thiết lập thêm `main-class`, `main-jar` hoặc `module`, `description`, `arguments`, `java-options` và các tùy chọn launcher được hỗ trợ.

## 8. Icon cho file association

Icon của ứng dụng và icon của loại tệp được ứng dụng mở là hai mục cấu hình riêng. Nếu muốn hệ điều hành hiển thị biểu tượng riêng cho file extension mà ứng dụng đăng ký xử lý, dùng `--file-associations` với một tệp properties.

Ví dụ `demo-association.properties`:

~~~properties
extension=demo
mime-type=application/x-demo
description=Demo document
icon=assets/windows/demo-file.ico
~~~

Đường dẫn icon file association phải nằm trong thư mục input của ứng dụng khi package. Ví dụ có thể đặt file như sau:

~~~text
input/
├── icon-demo.jar
└── assets/
    └── windows/
        └── demo-file.ico
~~~

Sau đó tạo installer:

~~~powershell
jpackage --type exe --input input --name IconDemo --main-jar icon-demo.jar --main-class com.example.IconDemo --icon assets/windows/icon-demo.ico --file-associations demo-association.properties --dest dist
~~~

Trong file association properties, các khóa thường dùng là:

- `extension`: phần mở rộng của tệp, ví dụ `demo`.
- `mime-type`: MIME type, ví dụ `application/x-demo`.
- `description`: mô tả ngắn loại tệp.
- `icon`: biểu tượng dành cho tệp thuộc association đó.

Mỗi association có thể dùng một tệp properties riêng và truyền bằng một lần `--file-associations`. Nếu không khai báo icon riêng, hệ điều hành có thể dùng icon mặc định của ứng dụng. Định dạng icon phải phù hợp nền tảng: ICO, ICNS hoặc PNG.

## 9. Tùy chỉnh icon qua `--resource-dir`

`--resource-dir` cho phép thay thế tài nguyên mặc định và template mà `jpackage` dùng khi tạo application image hoặc installer. Với icon launcher, tên file trong resource directory phụ thuộc hệ điều hành và tên launcher.

Ví dụ:

| Hệ điều hành | Tệp icon trong resource directory |
|---|---|
| Windows | `IconDemo.ico` |
| macOS | `IconDemo.icns` |
| Linux | `IconDemo.png` |

Tên tệp phải khớp tên application hoặc launcher tương ứng. Với launcher bổ sung tên `Admin`, có thể cung cấp `Admin.ico`, `Admin.icns` hoặc `Admin.png` tùy nền tảng.

Ví dụ:

~~~text
resource-dir/
├── IconDemo.ico
├── Admin.ico
└── IconDemo.properties
~~~

Gọi `jpackage`:

~~~powershell
jpackage --type app-image --input input --name IconDemo --main-jar icon-demo.jar --main-class com.example.IconDemo --resource-dir resource-dir --dest dist --verbose
~~~

Nếu đã có tùy chọn dòng lệnh phù hợp như `--icon`, nên ưu tiên dùng tùy chọn đó. `--resource-dir` hữu ích khi cần thay template hoặc tài nguyên khác mà dòng lệnh không cung cấp tùy chọn riêng. Dùng `--verbose` để xem `jpackage` đã chọn tài nguyên nào.

## 10. Application image và installer

Icon được xử lý trong quá trình tạo application image. Có thể bắt đầu bằng `--type app-image` để kiểm tra launcher, runtime và icon trước khi tạo installer.

Các định dạng package phổ biến theo nền tảng:

| Nền tảng | Application image | Installer |
|---|---|---|
| Windows | `app-image` | `exe`, `msi` |
| macOS | `app-image` | `pkg`, `dmg` |
| Linux | `app-image` | `deb`, `rpm` |

Các loại package được hỗ trợ tùy hệ điều hành và bản JDK. Build installer trên hệ điều hành đích; `jpackage` không cross-package giữa Windows, macOS và Linux.

Quy trình nên thực hiện:

1. Biên dịch ứng dụng và chuẩn bị input directory.
2. Chọn icon đúng định dạng nền tảng.
3. Tạo application image với `--type app-image` và `--icon`.
4. Mở/chạy launcher và kiểm tra icon trong môi trường desktop.
5. Tạo installer bằng định dạng phù hợp với nền tảng.
6. Cài thử installer trên máy sạch hoặc máy ảo để kiểm tra shortcut, menu, file association và icon sau cài đặt.

Nếu cần tạo installer từ một application image đã có, dùng `--app-image` theo chế độ package của `jpackage`. Khi cần thay icon launcher, hãy tạo lại application image với tài nguyên icon mong muốn rồi package image đó.

## 11. Icon của cửa sổ JavaFX và Swing

`jpackage --icon` thiết lập icon ở cấp package/launcher. Nó không tự đặt icon trong mọi cửa sổ do mã ứng dụng tạo ra.

Với JavaFX, đặt icon cho `Stage` trong phương thức `start`:

~~~java
@Override
public void start(Stage stage) {
    Image icon = new Image(
            getClass().getResourceAsStream("/icons/app.png"));
    stage.getIcons().add(icon);

    stage.setTitle("Icon Demo");
    stage.show();
}
~~~

Tệp `app.png` phải được đóng gói trong classpath hoặc module resources. Nếu cần nhiều kích thước, có thể thêm nhiều `Image` vào danh sách `stage.getIcons()` để JavaFX chọn kích thước phù hợp.

Với Swing, đặt icon cho `JFrame` bằng `setIconImage`:

~~~java
Image icon = Toolkit.getDefaultToolkit().getImage(
        getClass().getResource("/icons/app.png"));
frame.setIconImage(icon);
~~~

Vì vậy, ứng dụng desktop có thể cần hai bước: đặt icon launcher/package bằng `jpackage` và đặt icon cửa sổ trong mã UI.

## 12. Kiểm tra icon sau khi package

Dùng `--verbose` khi chạy `jpackage`. Log có thể hiển thị tài nguyên icon tùy chỉnh đã được nạp, ví dụ:

~~~text
Using custom package resource [icon] (loaded from file .../icon-demo.ico).
Succeeded in building Windows Application Image package
~~~

Thông báo cụ thể có thể khác giữa phiên bản JDK và hệ điều hành. Sau khi package:

- Kiểm tra file icon có tồn tại và đúng định dạng trước khi gọi `jpackage`.
- Kiểm tra log verbose để xác nhận đường dẫn icon đã được sử dụng.
- Kiểm tra launcher native hoặc application bundle được tạo ra.
- Chạy launcher để xác nhận ứng dụng hoạt động sau khi package.
- Kiểm tra desktop shortcut, Start Menu, Dock hoặc menu ứng dụng sau khi cài đặt.
- Với file association, cài ứng dụng và mở thử một tệp có extension đã đăng ký.
- Với Linux, kiểm tra desktop entry và icon path mà entry tham chiếu.
- Với macOS, kiểm tra icon của application bundle trong Finder/Dock.
- Với Windows, kiểm tra icon của file launcher và shortcut.

Một smoke test đơn giản trên Windows:

~~~powershell
.\dist\IconDemo\IconDemo.exe
~~~

Stdout khi launcher được tạo với `--win-console`:

~~~text
Icon package ready
~~~

Có thể kiểm tra thêm icon của launcher trong File Explorer hoặc Properties. Một số desktop environment lưu cache icon; sau khi thay icon, hãy kiểm tra application image mới hoặc làm mới cache theo quy trình của hệ điều hành.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Launcher vẫn dùng icon mặc định | Đường dẫn sai, icon sai định dạng hoặc file không được đọc. | Kiểm tra đường dẫn từ current working directory, định dạng và log `--verbose`. |
| Đổi đuôi PNG thành ICO nhưng package lỗi | Phần mở rộng thay đổi nhưng nội dung file vẫn là PNG. | Xuất hoặc chuyển đổi thành ICO thực sự bằng công cụ tạo icon. |
| Windows hiển thị icon mờ hoặc thiếu kích thước | ICO chỉ chứa một kích thước nhỏ hoặc artwork không tối ưu. | Tạo ICO có nhiều kích thước và kiểm tra alpha channel. |
| macOS không hiển thị icon mong muốn | Tệp không phải ICNS hợp lệ hoặc bundle chưa được build lại. | Tạo ICNS đúng định dạng, build lại application image và kiểm tra bundle. |
| Linux shortcut không hiển thị icon | PNG không nằm ở đường dẫn được desktop entry tham chiếu hoặc tên resource sai. | Kiểm tra resource directory, desktop entry và icon path. |
| Launcher bổ sung dùng icon mặc định | Chưa khai báo khóa `icon` trong properties của `--add-launcher` hoặc tên resource không khớp. | Đặt icon riêng trong launcher properties hoặc cung cấp resource đúng tên launcher. |
| File mở rộng vẫn dùng icon cũ | File association chưa khai báo icon hoặc installer chưa đăng ký association mới. | Kiểm tra `--file-associations`, đặt icon trong input directory và cài lại package để thử. |
| Icon launcher đúng nhưng icon cửa sổ sai | Chỉ cấu hình icon package, chưa cấu hình icon trong JavaFX/Swing. | Đặt icon bằng `Stage.getIcons()` hoặc `JFrame.setIconImage()`. |
| Build từ application image vẫn giữ icon cũ | Application image đầu vào đã chứa launcher với icon cũ. | Tạo lại application image với icon mới rồi đóng gói installer từ image mới. |
| Package tạo được trên một OS nhưng không tạo được cho OS khác | `jpackage` không hỗ trợ cross-platform native packaging. | Chạy build trên runner/agent của từng hệ điều hành đích. |

## 14. Checklist trước khi phát hành

- Đã xác định hệ điều hành đích và định dạng icon tương ứng.
- Icon là tệp hợp lệ, không chỉ đổi phần mở rộng.
- Artwork rõ ở kích thước nhỏ, có vùng an toàn và transparency phù hợp.
- Đã chuẩn bị ICO, ICNS hoặc PNG theo nền tảng.
- Đường dẫn truyền cho `--icon` tồn tại và được tính từ thư mục làm việc đúng.
- Application image đã được tạo và kiểm tra bằng `--type app-image`.
- Log `--verbose` xác nhận tài nguyên icon được nạp.
- Launcher chính và từng launcher bổ sung dùng đúng icon.
- File association có icon riêng nếu sản phẩm cần đăng ký loại tệp.
- Icon cửa sổ JavaFX/Swing được đặt trong mã UI nếu cần.
- Installer được tạo trên hệ điều hành đích và đã cài thử.
- Shortcut, menu, Dock, desktop entry và file association hiển thị đúng icon.
- Artifact cuối cùng được build lại sau khi thay đổi icon.

## 15. Tài liệu tham khảo

- [The jpackage Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html)
- [Support Application Requirements — JDK 24](https://docs.oracle.com/en/java/javase/24/jpackage/support-application-features.html)
- [Packaging Tool User's Guide — JDK 24](https://docs.oracle.com/en/java/javase/24/jpackage/packaging-tool-user-guide.pdf)

`--icon` là cách trực tiếp để gắn biểu tượng cho application package và launcher do `jpackage` tạo ra. Hãy chuẩn bị đúng định dạng cho hệ điều hành đích, kiểm tra bằng application image trước, cấu hình icon riêng cho launcher hoặc file association khi cần, rồi xác nhận icon trên chính installer và môi trường desktop sẽ phát hành.
