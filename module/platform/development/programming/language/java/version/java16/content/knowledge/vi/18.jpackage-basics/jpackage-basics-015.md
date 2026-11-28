# Đóng gói icon và tài nguyên với --icon, --resource-dir

**Module:** JAVA_VERSION_JAVA16  
**Chương:** jpackage cơ bản  
**Áp dụng:** Java 16 trở lên; jpackage tiếp tục là công cụ đóng gói ứng dụng Java trong các JDK hiện đại.

`jpackage` tạo application image hoặc gói cài đặt native cho ứng dụng Java. Ngoài JAR và runtime, một gói hoàn chỉnh thường cần icon đúng nền tảng, thông tin hiển thị và một số tài nguyên riêng cho trình cài đặt. Hai tùy chọn phục vụ hai mục đích khác nhau:

- `--icon`: chỉ định file icon cho application package.
- `--resource-dir`: chỉ định thư mục chứa các tài nguyên đóng gói tùy chỉnh để ghi đè resource mặc định của jpackage. Phạm vi sử dụng phụ thuộc JDK; trong jpackage Java 16, tùy chọn này được dùng khi tạo native application package.

Điểm cần phân biệt là tài nguyên của **bộ đóng gói** và tài nguyên mà **ứng dụng đọc khi chạy**. `--resource-dir` dành cho resource override của jpackage; ảnh, cấu hình hoặc dữ liệu mà chương trình cần đọc lúc chạy nên được đóng trong JAR hoặc đưa vào thư mục input của ứng dụng. Một số JDK mới có thêm `--app-content` để đưa nội dung bổ sung vào application payload; tùy chọn này không thuộc baseline jpackage của Java 16.

## 1. jpackage và hai loại đầu ra

`jpackage` được đưa vào JDK từ các phiên bản trước và trở thành công cụ hoàn chỉnh trong Java 16 qua JEP 392. Công cụ hỗ trợ tạo:

| Đầu ra | Mục đích |
| --- | --- |
| `app-image` | Thư mục ứng dụng có launcher và runtime cần thiết, phù hợp để kiểm tra hoặc phân phối dạng thư mục |
| `msi`, `exe` | Bộ cài native trên Windows |
| `pkg`, `dmg` | Bộ cài hoặc image phân phối trên macOS |
| `deb`, `rpm` | Gói cài native trên Linux |

Gói native thường tích hợp tốt hơn với nền tảng: launcher, biểu tượng, metadata và cơ chế cài/gỡ theo định dạng của hệ điều hành. `app-image` hữu ích để xác minh nội dung trước khi tạo installer.

`jpackage` tạo gói cho nền tảng đang chạy. Hãy build và kiểm tra từng định dạng trên hệ điều hành đích; không xem `--type` là một cơ chế cross-compile native installer giữa Windows, macOS và Linux.

## 2. Chỉ định icon bằng --icon

Tùy chọn có dạng:

```sh
jpackage --icon path/to/application-icon
```

Icon phải phù hợp với nền tảng đích. Các định dạng thường dùng:

| Nền tảng | Định dạng thường dùng | Gợi ý |
| --- | --- | --- |
| Windows | `.ico` | Nên có nhiều kích thước trong cùng file ICO để hiển thị tốt ở các vị trí khác nhau |
| macOS | `.icns` | Dùng bộ icon ICNS với các kích thước/scale cần thiết |
| Linux | `.png` | Dùng PNG có độ phân giải phù hợp; kiểm tra cách desktop environment hiển thị icon |

Đây là quy ước định dạng theo nền tảng. Hãy kiểm tra yêu cầu của đúng JDK và hệ điều hành đang đóng gói thay vì đổi đuôi file để giả lập định dạng khác.

Ví dụ trên Linux:

```sh
jpackage --type app-image \
  --name AcmeDesk \
  --input build/libs \
  --main-jar acme-desk.jar \
  --main-class com.acme.desktop.Main \
  --icon packaging/icons/acme.png \
  --dest build/image
```

Ví dụ Windows thay icon bằng file ICO:

```powershell
jpackage --type app-image --name AcmeDesk --input build/libs --main-jar acme-desk.jar --main-class com.acme.desktop.Main --icon packaging/icons/acme.ico --dest build/image
```

Ví dụ macOS dùng file ICNS:

```sh
jpackage --type app-image \
  --name AcmeDesk \
  --input build/libs \
  --main-jar acme-desk.jar \
  --main-class com.acme.desktop.Main \
  --icon packaging/icons/acme.icns \
  --dest build/image
```

Các ví dụ giả định thư mục `build/libs` chứa main JAR và dependency cần thiết. Đường dẫn icon được tính từ working directory nơi chạy lệnh. Để build lặp lại được, nên dùng đường dẫn tương đối trong repository hoặc truyền đường dẫn tuyệt đối đã được pipeline xác định.

## 3. Icon được đóng gói ở đâu và kiểm tra thế nào?

`--icon` cung cấp icon cho application package theo quy tắc của nền tảng. JDK có thể chuyển hoặc đặt tài nguyên vào cấu trúc application image/installer tương ứng. Không giả định file icon nguồn sẽ được sao chép nguyên xi vào một vị trí giống nhau trên mọi OS.

Sau khi tạo `app-image`:

1. Mở thư mục đầu ra và xác nhận launcher được tạo.
2. Chạy launcher trên đúng OS để kiểm tra icon trong ứng dụng.
3. Kiểm tra shortcut/menu entry nếu installer tạo các mục đó.
4. Tạo installer native và kiểm tra icon trong giao diện cài đặt, danh sách ứng dụng và ứng dụng đã cài.
5. Kiểm tra các kích thước hiển thị phổ biến, theme sáng/tối và high-DPI nếu ứng dụng nhắm tới desktop.

Nếu icon không hiển thị, kiểm tra định dạng thật của file, đường dẫn, nội dung file, tùy chọn build và cache icon của desktop environment. Đổi phần mở rộng từ PNG sang ICO/ICNS không chuyển đổi nội dung file.

## 4. --resource-dir dùng để làm gì?

Tùy chọn có dạng:

```sh
jpackage --resource-dir path/to/package-resources
```

Thư mục này chứa các resource override mà jpackage nhận diện khi tạo application image hoặc installer. Tùy nền tảng và loại gói, các resource có thể là template, metadata hoặc tài nguyên dành riêng cho installer/launcher. Khi có file override tương ứng, jpackage dùng file tùy chỉnh thay cho resource mặc định.

`--resource-dir` không có nghĩa là “chép mọi file trong thư mục này vào thư mục làm việc của ứng dụng để code Java đọc”. Một file bất kỳ đặt vào đây không tự động trở thành resource trên classpath hoặc dữ liệu runtime.

Phân biệt các tùy chọn:

| Nhu cầu | Cách cung cấp |
| --- | --- |
| Icon ứng dụng | `--icon` |
| Ghi đè template hoặc resource đóng gói mà jpackage hỗ trợ | `--resource-dir` |
| Đưa file/thư mục runtime vào application image trên Java 16 | Đặt trong thư mục `--input`; mọi file trong thư mục này được đóng gói |
| Đưa nội dung bổ sung vào application payload trên một số JDK mới | `--app-content`, nếu `jpackage --help` của JDK đang dùng có tùy chọn này |
| Cung cấp main JAR và dependency | `--input`, `--main-jar` hoặc cấu hình module tương ứng |
| Resource Java cần đọc bằng `getResource()` | Đóng trong JAR/module của ứng dụng |

## 5. Tổ chức resource theo nền tảng

Không nên dùng chung một resource directory cho mọi nền tảng nếu bên trong có template hoặc metadata phụ thuộc OS. Tổ chức source trong repository theo mục đích:

```text
packaging/
  icons/
    acme.png
    acme.ico
    acme.icns
  jpackage/
    linux/
      (các resource override được JDK mục tiêu hỗ trợ)
    windows/
      (các resource override được JDK mục tiêu hỗ trợ)
    macos/
      (các resource override được JDK mục tiêu hỗ trợ)
  app-content/
    (tài nguyên cần đặt cạnh application image)
```

Khi tạo native package trên Linux, truyền `packaging/jpackage/linux`; trên Windows, truyền `packaging/jpackage/windows`; trên macOS, truyền `packaging/jpackage/macos`. Mỗi thư mục chỉ nên chứa các file override mà phiên bản jpackage và loại package tương ứng hỗ trợ.

Không tự đặt tên file rồi kỳ vọng jpackage sẽ sử dụng nó. Tên và định dạng resource override phụ thuộc nền tảng, loại package và phiên bản JDK. Dùng tài liệu `jpackage` của JDK đang build và resource mặc định tương ứng làm căn cứ; chỉ sao chép vào repository những file thực sự cần tùy chỉnh.

Hướng dẫn jpackage của JDK 16 đưa ra một số ví dụ resource override:

| Nền tảng/loại gói | Ví dụ resource | Công dụng |
| --- | --- | --- |
| Linux | `<launcher-name>.png`, `<launcher-name>.desktop` | Icon launcher và desktop entry |
| Linux DEB | `control`, `preinst`, `prerm`, `postinst`, `postrm`, `copyright` | Metadata và script cài/gỡ |
| Linux RPM | `<package-name>.spec` | Hướng dẫn tạo RPM |
| macOS | `<launcher-name>.icns`, `Info.plist`, `Runtime-Info.plist` | Icon và metadata bundle |
| Windows | `<launcher-name>.ico`, `main.wxs`, `overrides.wxi` | Icon launcher và template WiX |

Đây là ví dụ theo hướng dẫn JDK 16, không phải danh sách bất biến cho mọi JDK. Hãy dùng `--verbose` để biết tên file mà phiên bản jpackage hiện tại mong đợi. Nếu một resource có tùy chọn dòng lệnh riêng như `--icon`, ưu tiên tùy chọn đó; trong phần lớn trường hợp, giá trị dòng lệnh có ưu tiên hơn file override cùng mục đích.

## 6. Ví dụ đóng gói Linux với icon và resource override

Giả sử pipeline Linux đã chuẩn bị:

- `build/libs/acme-desk.jar`: ứng dụng chính.
- `packaging/icons/acme.png`: icon Linux.
- `packaging/jpackage/linux/`: các resource override hợp lệ cho loại gói Linux đang tạo.

Tạo application image trước:

```sh
jpackage --type app-image \
  --name AcmeDesk \
  --input build/libs \
  --main-jar acme-desk.jar \
  --main-class com.acme.desktop.Main \
  --icon packaging/icons/acme.png \
  --dest build/image
```

Sau khi xác minh application image, tạo gói DEB:

```sh
jpackage --type deb \
  --name AcmeDesk \
  --input build/libs \
  --main-jar acme-desk.jar \
  --main-class com.acme.desktop.Main \
  --icon packaging/icons/acme.png \
  --resource-dir packaging/jpackage/linux \
  --dest build/packages
```

Nếu resource directory rỗng hoặc không cần override, có thể bỏ `--resource-dir`. Không cần tạo thư mục chỉ để truyền một đường dẫn không có nội dung.

## 7. Ví dụ đóng gói Windows và macOS

Windows MSI:

```powershell
jpackage --type msi --name AcmeDesk --input build/libs --main-jar acme-desk.jar --main-class com.acme.desktop.Main --icon packaging/icons/acme.ico --resource-dir packaging/jpackage/windows --win-menu --win-shortcut --dest build/packages
```

macOS DMG:

```sh
jpackage --type dmg \
  --name AcmeDesk \
  --input build/libs \
  --main-jar acme-desk.jar \
  --main-class com.acme.desktop.Main \
  --icon packaging/icons/acme.icns \
  --resource-dir packaging/jpackage/macos \
  --dest build/packages
```

Các tùy chọn `--win-menu` và `--win-shortcut` chỉ dành cho Windows. Không đưa chúng vào lệnh build macOS hoặc Linux. Tương tự, resource override của MSI không nên dùng cho DMG, DEB hoặc RPM.

Máy build cần có công cụ đóng gói native mà nền tảng yêu cầu. Kiểm tra thông báo lỗi và tài liệu của JDK nếu thiếu WiX/toolchain Windows, công cụ tạo gói Linux hoặc công cụ đóng gói/signing trên macOS.

## 8. Resource runtime nên dùng thư mục input hoặc JAR

Giả sử ứng dụng cần một thư mục `templates` khi chạy. Không đặt thư mục này trong `--resource-dir` với kỳ vọng Java tự tìm thấy nó.

Với jpackage của Java 16, đặt file runtime trong thư mục input. Mọi file trong thư mục này được đưa vào application image:

```text
build/package-input/
  acme-desk.jar
  templates/
    default.json
  config/
    defaults.properties
```

Ví dụ tạo application image:

```sh
jpackage --type app-image \
  --name AcmeDesk \
  --input build/package-input \
  --main-jar acme-desk.jar \
  --main-class com.acme.desktop.Main \
  --dest build/image
```

Hoặc đóng resource bất biến trong JAR và đọc bằng class loader:

```java
try (var input = AcmeDesk.class.getResourceAsStream("/templates/default.json")) {
    if (input == null) {
        throw new IllegalStateException("Missing default template");
    }
    // Đọc nội dung template.
}
```

Chọn cách phù hợp với vòng đời dữ liệu:

- Resource bất biến, đi cùng version ứng dụng: đóng trong JAR/module.
- File cần nằm trong application image trên Java 16: đặt trong thư mục `--input`.
- Trên JDK mới có `--app-content`, có thể dùng tùy chọn đó cho nội dung bổ sung; kiểm tra `jpackage --help` của đúng JDK trước khi dùng.
- Template phục vụ quá trình tạo installer/application image: dùng `--resource-dir` nếu đó là loại resource override được jpackage hỗ trợ.

## 9. Ghi đè resource mặc định một cách có kiểm soát

Khi tùy chỉnh resource:

1. Xác định chính xác package type và nền tảng đích.
2. Kiểm tra danh sách resource override được phiên bản JDK mục tiêu hỗ trợ.
3. Lấy bản template phù hợp làm cơ sở, giữ nguyên placeholder và cấu trúc mà jpackage cần.
4. Chỉ sửa nội dung cần thiết như metadata, template hoặc installer resource.
5. Lưu bản tùy chỉnh trong source control, không sửa trực tiếp thư mục cài JDK.
6. Tạo native package mới và kiểm tra kết quả trên môi trường đích.
7. Khi nâng JDK, so sánh lại template mặc định và xác minh resource override vẫn tương thích.

Để xem tên resource mặc định mà chính JDK đang dùng chọn:

```sh
jpackage --type deb --input build/libs --main-jar acme-desk.jar \
  --main-class com.acme.desktop.Main --name AcmeDesk \
  --verbose --temp build/jpackage-temp
```

`--temp` cần trỏ tới thư mục mới hoặc rỗng. Kết hợp `--verbose` và thư mục tạm được giữ lại để quan sát resource/template mà công cụ sử dụng. Thay `deb` bằng loại package trên nền tảng build thực tế.

Resource override gắn với chi tiết triển khai của jpackage. Một template có thể thay đổi giữa các JDK hoặc loại package; đừng coi file override nội bộ là API bất biến nếu tài liệu không cam kết điều đó.

## 10. Bảo vệ installer resource và nội dung đóng gói

Một số resource tùy chỉnh có thể tham gia quá trình cài đặt hoặc gỡ cài đặt. Ví dụ script/package metadata có thể được installer thực thi theo quyền của hệ thống. Vì vậy:

- Review mọi script và template trước khi đưa vào `--resource-dir`.
- Không tải resource override từ nguồn không tin cậy trong pipeline release.
- Không đặt password, signing key hoặc token trong resource directory.
- Không chèn dữ liệu người dùng hoặc secret vào template installer.
- Giữ thay đổi resource có thể review trong version control.
- Tạo gói từ workspace sạch hoặc build artifact đã xác định để tránh đưa file ngoài ý muốn vào package.

`--resource-dir` là đầu vào của quá trình đóng gói. Xem nó như một phần của build configuration và kiểm soát quyền ghi như source code.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Icon không xuất hiện | Sai định dạng nền tảng, đường dẫn sai hoặc file icon không hợp lệ | Kiểm tra file thật, định dạng và chạy lại trên OS đích |
| Installer dùng icon mặc định | Icon không được truyền trong lệnh tạo package hoặc resource override không đúng | Xác minh `--icon` trong đúng lệnh và loại gói |
| Resource override bị bỏ qua | Sai tên file, sai thư mục hoặc resource không được loại package/JDK hỗ trợ | Đối chiếu resource override được tài liệu hóa cho đúng JDK |
| File runtime không tìm thấy | Đặt file ứng dụng vào `--resource-dir` | Đóng file trong JAR hoặc đưa file vào thư mục `--input` trên Java 16 |
| Build trên OS này không tạo được gói OS khác | jpackage không phải công cụ cross-compile native installer | Chạy pipeline trên từng nền tảng đích |
| Gói thay đổi sau khi nâng JDK | Template/resource override phụ thuộc phiên bản jpackage | So sánh template và kiểm thử lại package trên JDK mới |

Khi chẩn đoán, lưu lại lệnh jpackage hoàn chỉnh, phiên bản JDK, OS, package type và resource directory đã dùng. Chỉ các dữ liệu này mới giúp tái hiện chính xác quá trình đóng gói.

## 12. Checklist trước khi phát hành

1. Icon có đúng định dạng thực của nền tảng đích không?
2. Đường dẫn `--icon` có tồn tại trên máy build và được đưa vào pipeline không?
3. Đã kiểm tra icon trong application image và installer thực tế chưa?
4. Resource directory có chỉ chứa các override được jpackage của JDK mục tiêu hỗ trợ không?
5. Resource override có được tách theo Linux, Windows và macOS không?
6. File runtime đã được đóng trong JAR hoặc thư mục `--input` chưa?
7. Có tránh dùng `--resource-dir` như một thư mục chứa mọi asset ứng dụng không?
8. Template và installer script đã được review và lưu version control chưa?
9. Không có secret hoặc signing key trong resource directory chứ?
10. Đã build native package trên đúng OS đích chưa?
11. Đã kiểm tra lại resource override khi nâng JDK chưa?
12. Có lưu lệnh build, JDK version và package type để tái lập release không?

**Ghi nhớ:** Dùng `--icon` để chỉ định icon của application package theo định dạng nền tảng. Dùng `--resource-dir` để cung cấp resource override mà jpackage hỗ trợ; với jpackage Java 16, tùy chọn này được dùng khi tạo native application package. Tài nguyên runtime thuộc JAR hoặc thư mục `--input`; `--app-content` chỉ dùng khi JDK mới đang chạy có hỗ trợ. Tách resource theo OS/package type, kiểm tra lại khi nâng JDK và review mọi template/script trước khi phát hành.

## Tài liệu chính thức

- [JEP 392 — Packaging Tool, delivered in Java 16](https://openjdk.org/jeps/392).
- [Java SE 16 `jpackage` Tool — tùy chọn và package types](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html).
- [Java SE 16 Packaging Tool User's Guide — Override jpackage Resources](https://docs.oracle.com/en/java/javase/16/jpackage/override-jpackage-resources.html).
- [Java SE 26 `jpackage` Tool — `--icon`, `--resource-dir`, `--app-content` và package types](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html).
- [Java SE 26 `jpackage` Tool — ví dụ và tùy chọn theo nền tảng](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html#examples).
- [Java SE 26 `java` Launcher — chạy ứng dụng và runtime image](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
