# Metadata tên, phiên bản, nhà cung cấp và biểu tượng của app image

## 1. Tại sao app image cần metadata?

Khi đóng gói ứng dụng Java bằng **`jpackage`**, ứng dụng có thể được phân phối dưới dạng **application image**: một thư mục/bundle có launcher riêng, JAR/module của ứng dụng và Java runtime cần thiết. Một app image có thể chạy tốt nhưng vẫn khó nhận diện nếu tên, phiên bản, nhà phát hành hoặc icon chưa được thiết lập.

Các tùy chọn hiện hành chính:

| Tùy chọn `jpackage` | Metadata | Ví dụ |
| --- | --- | --- |
| `--name` | Tên ứng dụng và thường là tên launcher/bundle | `--name LessonDesk` |
| `--app-version` | Phiên bản của ứng dụng hoặc gói | `--app-version 2.4.1` |
| `--vendor` | Tên tổ chức/người phát hành | `--vendor "Example Learning"` |
| `--icon` | Đường dẫn biểu tượng hợp lệ theo hệ điều hành | `--icon assets/lesson.ico` |
| `--description` | Mô tả ngắn, hữu ích khi xem thông tin ứng dụng | `--description "JPackage metadata sample"` |

Ví dụ Windows (lệnh đầy đủ sẽ được giải thích ở phần 5):

```powershell
jpackage --type app-image --name LessonDesk --app-version 2.4.1 --vendor "Example Learning" --description "JPackage metadata sample" --icon assets\lesson.ico --input input --main-jar app-demo.jar --main-class AppMetadataDemo --dest dist --win-console
```

**Ngữ cảnh Java 14:** `jpackage` xuất hiện dưới dạng công cụ ươm tạo ở Java 14 (JEP 343), tiếp tục incubating trong Java 15, và trở thành công cụ **chính thức từ Java 16** (JEP 392). Bài này chỉ dùng **`jpackage` chính thức trong JDK 17+**, phù hợp với các JDK hiện đại. Không bật module incubator `jdk.incubator.jpackage`, không tái sử dụng cú pháp thử nghiệm đã lỗi thời.

`--type app-image` tạo **application image**, không phải installer native. Nếu cần bộ cài Windows `.msi`/`.exe`, Linux `.deb`/`.rpm` hoặc macOS `.pkg`/`.dmg`, cần quy trình `jpackage` khác trên đúng OS đó.

## 2. Tên ứng dụng: `--name`

`--name` đặt tên ứng dụng đóng gói; nếu không chỉ định, `jpackage` sẽ suy tên từ **main JAR hoặc main module**, điều này có thể không phải tên thương mại mong muốn.

Giả sử:
- Main class là `AppMetadataDemo`.
- Tệp JAR là `app-demo.jar`.
- Tên sản phẩm người dùng nhìn thấy là `LessonDesk`.

Ba tên này **không cần giống nhau**. Với `--name LessonDesk`, app image Windows có thể trông như:

```text
dist/
└── LessonDesk/
    ├── LessonDesk.exe
    ├── app/
    └── runtime/
```

Trên Linux, launcher thường nằm trong `dist/LessonDesk/bin/LessonDesk`; trên macOS, bundle thường có tên `LessonDesk.app`. **Cấu trúc thực tế tùy JDK và OS**; chỉ dựa trên launcher/bundle hiện được tạo ra chứ không xem các file nội bộ của `jpackage` là API ổn định.

Nên:
- Chọn tên nhận diện đủ ổn định qua các bản phát hành.
- Tránh ký tự gây lỗi trong tên file/đường dẫn của OS đích.
- Xác minh launcher và thư mục bundle mang tên mong muốn.
- Với bản cài đặt/updater, kiểm tra tên package và identifier theo quy định riêng của nền tảng.

Tên ứng dụng **không phải** tên `package` Java, tên `module` JPMS, tên `Main-Class` của JAR hay thông tin nhà phát hành.

## 3. Phiên bản: `--app-version`

Tham số `--app-version 2.4.1` đặt phiên bản của **ứng dụng/gói phân phối**. Theo hướng dẫn hiện hành của Oracle, nếu không khai báo thì ứng dụng mặc định mang phiên bản **`1.0`**.

Phiên bản ứng dụng cần tách khỏi:
- Phiên bản Java runtime được đóng kèm (ví dụ Java 17 hoặc 21).
- Mức mã Java do `javac --release` chọn.
- Giá trị `Implementation-Version` trong `MANIFEST.MF` của JAR.
- Các hằng số phiên bản do chính ứng dụng khai báo.

Ví dụ có thể **biên dịch Java 17**, dùng `jpackage` của một JDK mới, tạo app image với **`--app-version 2.4.1`**. Điều đó không biến Java runtime thành phiên bản 2.4.1.

### Chú ý định dạng phiên bản và cập nhật

Phiên bản `2.4.1` là ví dụ gồm các thành phần số thông dụng, đã được thử nghiệm trên Windows. Tuy nhiên, **installer native trên từng OS** có thể có quy định riêng đối với định dạng, so sánh và nâng cấp phiên bản. Không nên mặc định rằng mọi chuỗi SemVer có hậu tố như `2.4.1-beta+5` đều được backend Windows Installer, Debian/RPM và macOS xử lý giống nhau.

Trong quy trình phát hành:
1. Chọn version nhất quán giữa artifact, ghi chú phát hành và metadata package.
2. Kiểm tra phiên bản được công cụ đóng gói và OS đích chấp nhận.
3. Kiểm thử đường đi **cài đặt mới → nâng cấp → gỡ cài đặt** khi tạo native installer.
4. Khi sửa lỗi bảo mật hoặc cập nhật runtime kèm theo, phát hành bản mới thay vì lặng lẽ thay nội dung gói cũ mà không quản lý version.

Nếu ứng dụng cần trang “About” hiển thị version, nên tạo cấu hình ứng dụng từ **cùng một nguồn build**; `--app-version` không tự sinh biến Java để ứng dụng đọc trong `main`.

## 4. Nhà cung cấp: `--vendor`

`--vendor "Example Learning"` đặt tên tổ chức/người cung cấp ứng dụng trong metadata đóng gói. Tài liệu Oracle không quy định một tên vendor mặc định để ứng dụng có thể dựa vào.

Tên có khoảng trắng cần đặt trong dấu nháy kép để shell hiểu là **một đối số**:

```powershell
--vendor "Example Learning"
```

Đây là **một đoạn đối số CLI minh họa**, chưa phải lệnh chạy độc lập. Trên Bash cũng nên quote những chuỗi có khoảng trắng.

Tên vendor có thể hiển thị dưới dạng tên công ty/nhà phát hành trên các nền tảng hỗ trợ, song cách hiển thị tùy loại gói. Nó **không tương đương chữ ký số**: bất kỳ ai có thể điền một chuỗi vendor vào metadata. Khi phát hành công khai, vẫn cần xem xét chứng chỉ ký code, bảo vệ artifact và quy trình phân phối.

Đừng nhầm:
- `--vendor`: nhãn metadata.
- `--copyright`: tuyên bố bản quyền (tùy chọn khác).
- `--description`: mô tả ứng dụng.
- Code signing/notarization: quy trình bảo mật **riêng**.

## 5. Biểu tượng: `--icon` và định dạng theo OS

`--icon` nhận **đường dẫn file icon** của gói/launcher. Đường dẫn có thể tuyệt đối hoặc tương đối với **working directory hiện tại** khi chạy `jpackage`; không mặc nhiên tính từ `--input`.

| Nền tảng | Tệp icon nên chuẩn bị | Ví dụ |
| --- | --- | --- |
| Windows | `.ico` hợp lệ | `assets/lesson.ico` |
| Linux | `.png` hợp lệ | `assets/lesson.png` |
| macOS | `.icns` hợp lệ | `assets/lesson.icns` |

**Không đổi tên `.png` thành `.ico` rồi coi đó là định dạng đúng**. Tệp phải được tạo bằng công cụ xuất định dạng tương ứng, có kích thước và độ phân giải phù hợp để hiển thị rõ ở các tỷ lệ UI.

Có thể quản lý source thiết kế chung và xuất các biến thể:

```text
assets/
├── lesson.ico
├── lesson.png
└── lesson.icns
```

Nếu **không dùng `--icon`**, `jpackage` áp dụng icon mặc định. Điều này đủ để thử nghiệm nhưng không thích hợp với sản phẩm cần nhận diện thương hiệu.

### Icon của launcher không tự đổi icon trong UI Java

`--icon` cấu hình **app image/launcher và gói**. Trong ứng dụng Swing hoặc JavaFX, biểu tượng cửa sổ `JFrame`/`Stage` có thể cần được thiết lập bằng API giao diện. Icon của file association cũng là một chủ đề cấu hình khác.

Nếu có **nhiều launcher**, `--add-launcher` có thể dùng properties riêng, trong đó có trường `icon`. Không nên kỳ vọng tất cả launcher dùng icon riêng nếu chỉ truyền một `--icon` chung.

### Phân biệt `--icon` với `--resource-dir`

`--icon` là cách đơn giản, chính thức để đặt **icon chính**. `--resource-dir` dành cho các tài nguyên/template đóng gói có quy tắc đặt tên riêng theo OS, bao gồm `<launcher-name>.ico` ở Windows, `<launcher-name>.png` trên Linux, `<launcher-name>.icns` ở macOS.

Chỉ muốn thay icon? **Dùng `--icon` trước**. Khi cần tùy biến sâu các tài nguyên của native installer hoặc launcher phụ, đọc quy tắc `--resource-dir` cho JDK/OS cụ thể. Giá trị do tùy chọn dòng lệnh chỉ định thường ưu tiên hơn tài nguyên thay thế khi cả hai cùng áp dụng.

## 6. Ví dụ Java 17+ đầy đủ: tạo app image với metadata

Phần này đã được kiểm chứng thực tế trên **Windows với JDK hỗ trợ Java 17**: tạo JAR, tạo file `.ico` demo, chạy `jpackage --type app-image` và kiểm tra metadata launcher.

### 6.1. Tạo chương trình

Tạo file **`src/AppMetadataDemo.java`**:

```java
public class AppMetadataDemo {
    public static void main(String[] args) {
        System.out.println("AppMetadataDemo=ready");
        System.out.println("arguments=" + args.length);
    }
}
```

Đây là **chương trình Java hoàn chỉnh**, không cần thư viện ngoài JDK.

### 6.2. Chuẩn bị thư mục và icon demo (Windows PowerShell)

Tại thư mục dự án, mở Windows PowerShell 5.1:

```powershell
New-Item -ItemType Directory -Force src,classes,input,assets,dist | Out-Null

Add-Type -AssemblyName System.Drawing

$iconFile = [System.IO.File]::Create(
    (Join-Path (Get-Location) "assets\lesson.ico")
)
try {
    [System.Drawing.SystemIcons]::Application.Save($iconFile)
}
finally {
    $iconFile.Dispose()
}
```

Mã PowerShell này sinh tệp ICO **minh họa** từ icon hệ thống qua `System.Drawing`. Nó phù hợp để học cú pháp đóng gói trên Windows nhưng **không phải icon sản phẩm để phát hành**, và không được dùng để tạo icon Linux/macOS. Khi phát hành thật, dùng tệp brand icon được thiết kế và xuất đúng định dạng.

Cấu trúc ban đầu:

```text
project/
├── src/AppMetadataDemo.java
├── assets/lesson.ico
├── classes/
├── input/
└── dist/
```

### 6.3. Biên dịch, tạo JAR và chạy thử

```powershell
javac --release 17 -d classes src\AppMetadataDemo.java
jar --create --file input\app-demo.jar -C classes .
java -cp input\app-demo.jar AppMetadataDemo
```

Đầu ra của lệnh `java`:

```text
AppMetadataDemo=ready
arguments=0
```

`javac --release 17` đảm bảo biên dịch theo mức API/ngôn ngữ Java 17. `jar` đóng class đã biên dịch vào `input/app-demo.jar`. Lệnh `java -cp` xác nhận JAR chạy bình thường trước khi tạo app image.

### 6.4. Chạy `jpackage` với đủ bốn metadata

```powershell
jpackage --type app-image --name LessonDesk --app-version 2.4.1 --vendor "Example Learning" --description "JPackage metadata sample" --icon assets\lesson.ico --input input --main-jar app-demo.jar --main-class AppMetadataDemo --dest dist --win-console
```

Đây là lệnh **một dòng**, tránh khác biệt ký tự nối dòng giữa Bash và PowerShell.

| Phần lệnh | Ý nghĩa |
| --- | --- |
| `--type app-image` | Tạo application image, không tạo installer |
| `--name LessonDesk` | Tên sản phẩm và launcher |
| `--app-version 2.4.1` | Phiên bản ứng dụng |
| `--vendor "Example Learning"` | Nhà phát hành |
| `--description ...` | Mô tả ngắn |
| `--icon assets\lesson.ico` | Icon Windows, tương đối với working directory |
| `--input input` | Thư mục chứa JAR đầu vào |
| `--main-jar app-demo.jar` | Tên JAR **tương đối với `--input`** |
| `--main-class AppMetadataDemo` | Lớp chứa `main` |
| `--dest dist` | Thư mục tạo sản phẩm |
| `--win-console` | Tạo console launcher cho ví dụ dòng lệnh **chỉ trên Windows** |

**Đừng nhầm đường dẫn:** với `--input input`, ghi `--main-jar app-demo.jar`, không ghi `--main-jar input\app-demo.jar`. Ngược lại, `--icon assets\lesson.ico` được xác định so với thư mục hiện tại, **không** so với `input`.

Sau khi thành công, launcher Windows nằm ở:

```text
dist/LessonDesk/LessonDesk.exe
```

Một bản Java runtime được đóng trong app image. Người dùng cuối chạy launcher đó, không cần tự chỉ định `java -cp`.

### 6.5. Chạy launcher đã đóng gói

```powershell
.\dist\LessonDesk\LessonDesk.exe
```

**Stdout đã được kiểm chứng:**

```text
AppMetadataDemo=ready
arguments=0
```

Kết quả giống khi chạy JAR trực tiếp, chứng tỏ launcher tìm được ứng dụng Java và chuyển điều khiển tới `main`.

### 6.6. Kiểm tra metadata của Windows executable

```powershell
$info = (Get-Item .\dist\LessonDesk\LessonDesk.exe).VersionInfo

"ProductName=$($info.ProductName)"
"ProductVersion=$($info.ProductVersion)"
"CompanyName=$($info.CompanyName)"
"FileVersion=$($info.FileVersion)"
"Description=$($info.FileDescription)"
```

**Kết quả thực nghiệm trên Windows:**

```text
ProductName=LessonDesk
ProductVersion=2.4.1
CompanyName=Example Learning
FileVersion=2.4.1
Description=JPackage metadata sample
```

Vì vậy trong kiểm thử này, `--name`, `--app-version`, `--vendor` và `--description` đã được phản ánh vào metadata của launcher Windows. `--icon` cũng được công cụ chấp nhận khi tạo app image với tệp ICO hợp lệ. Để đánh giá **hình hiển thị icon**, cần quan sát launcher trong Explorer/taskbar/shortcut trên Windows thực tế; thông tin `VersionInfo` không phải cách kiểm tra pixel của icon.

Các kết quả trên được kiểm chứng với **`javac --release 17`**, `jar`, `jpackage` và chạy launcher. Không coi chi tiết `VersionInfo` của Windows là API chung của macOS/Linux.

## 7. Dùng metadata trên Linux và macOS

Khi đã có `input/app-demo.jar`, hãy chuẩn bị icon đúng hệ điều hành và chạy lệnh tương ứng trên chính OS đích.

Linux (đã chuẩn bị `assets/lesson.png`):

```bash
jpackage --type app-image \
  --name LessonDesk \
  --app-version 2.4.1 \
  --vendor "Example Learning" \
  --description "JPackage metadata sample" \
  --icon assets/lesson.png \
  --input input \
  --main-jar app-demo.jar \
  --main-class AppMetadataDemo \
  --dest dist
```

Launcher Linux thường có đường dẫn:

```bash
./dist/LessonDesk/bin/LessonDesk
```

macOS (đã chuẩn bị `assets/lesson.icns`):

```bash
jpackage --type app-image \
  --name LessonDesk \
  --app-version 2.4.1 \
  --vendor "Example Learning" \
  --description "JPackage metadata sample" \
  --icon assets/lesson.icns \
  --input input \
  --main-jar app-demo.jar \
  --main-class AppMetadataDemo \
  --dest dist
```

Ví dụ đường dẫn executable của app bundle:

```bash
./dist/LessonDesk.app/Contents/MacOS/LessonDesk
```

**Hai biến thể Linux/macOS là ví dụ theo tài liệu Oracle, chưa được chạy trong lần kiểm chứng Windows.** Tùy bản JDK và OS, cách hiển thị icon/metadata và chi tiết cấu trúc bundle có thể khác, cần tự kiểm tra trên môi trường phát hành thực.

Đặc biệt, `--win-console` là cờ **riêng Windows** và không được thêm vào lệnh trên Linux/macOS.

## 8. App image metadata, manifest JAR và ký số là ba việc khác nhau

| Loại dữ liệu | Ví dụ | Tác dụng |
| --- | --- | --- |
| Metadata app image | `--name`, `--app-version`, `--vendor`, `--icon` | Nhận diện launcher/bundle và gói phân phối |
| JAR manifest | `Main-Class`, `Implementation-Version` khi build quy định | Thông tin và cấu hình riêng của JAR |
| Metadata runtime | `java.version`, tập module trong runtime image | Nền tảng Java chạy ứng dụng |
| Chứng thực/phân phối | Code signing, notarization, installer signing | Xác minh nguồn gốc và tính toàn vẹn theo hệ điều hành |

`--app-version` **không tự tạo** `Implementation-Version` trong JAR. `--vendor` **không ký số**. `--icon` **không tự đổi icon của mọi cửa sổ JavaFX/Swing**. `--name` **không đổi tên lớp Java `AppMetadataDemo`**.

Nếu ứng dụng có giao diện “About” cần hiển thị đúng phiên bản phát hành, hãy thiết kế **nguồn version trong build chung** để vừa tạo thông tin cho app vừa cấp `--app-version`, thay vì đoán lại từ `java.version`.

## 9. Thực hành QA khi phân phối

**Đối với app image:**

1. **Tên:** thư mục, launcher, hiển thị sản phẩm đúng `--name`?
2. **Version:** `--app-version` đúng release? Windows có thể kiểm tra `.VersionInfo`.
3. **Vendor:** tên chính xác và được quote khi có khoảng trắng?
4. **Icon:** file tồn tại, đúng định dạng, hiển thị sắc nét và không lẫn icon mặc định?
5. **Đầu vào:** JAR/module cùng dependency đã nằm trong `--input` hoặc module path?
6. **Runtime:** launcher chạy mà không cần JDK của máy build?
7. **Bảo mật:** artifact có được quản lý, có quy trình ký phù hợp trước khi phát hành công khai?

**Đối với installer native (nếu tạo sau):** kiểm tra tên package, quy tắc version riêng, installer vendor metadata, icon/shortcut, quyền ghi, nâng cấp và gỡ cài đặt. `jpackage` **không hỗ trợ cross-platform packaging**: cần build trên OS mục tiêu.

**Lưu ý icon cache trên Windows:** Explorer đôi khi hiển thị icon cũ sau khi thay tài nguyên. Nên kiểm tra sản phẩm trong thư mục/tên build mới và làm mới hiển thị phù hợp trước khi kết luận icon đóng gói bị lỗi.

**Khi có nhiều launcher:** cân nhắc `--add-launcher` cùng file properties riêng (có thể chỉ định `icon` cho launcher phụ) thay vì giả định một icon chính sẽ thay được tất cả icon.

## 10. Lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Không đặt `--name` | Tên suy từ JAR/module không đúng sản phẩm | Đặt tên sản phẩm tường minh |
| Dùng `--app-version` làm runtime version | Hiểu nhầm JDK và app release | Phân biệt `java.version` và app version |
| Đặt version tùy ý chứa hậu tố trên mọi OS | Backend native có thể từ chối | Kiểm thử format/version trên OS target |
| Viết `--vendor Example Learning` không quote | Shell tách đối số | Dùng `--vendor "Example Learning"` |
| Tưởng vendor metadata là chữ ký số | Không xác thực được người phát hành | Dùng cơ chế ký/phân phối thật |
| Dùng ICO Windows trên Linux/macOS | Icon sai định dạng nền tảng | Xuất PNG/ICNS đúng OS |
| Đổi tên PNG thành ICO | Icon vẫn không hợp lệ | Chuyển đổi định dạng thực sự |
| Giả định `--icon` lấy từ `--input` | Không tìm đúng file icon | Dùng path từ working directory |
| Thêm `--win-console` vào lệnh Linux | Sai tùy chọn nền tảng | Chỉ dùng cờ đó trên Windows |
| Dùng `--main-jar input/app-demo.jar` cùng `--input input` | Đường dẫn JAR chính có thể sai | `--main-jar app-demo.jar` |
| Chỉ kiểm tra output `jpackage` mà không chạy launcher | Chưa phát hiện lỗi startup/module/resource | Chạy app image thực tế |
| Hiểu `app-image` là installer native | Không có quy trình cài/gỡ tương ứng | Tạo installer riêng nếu cần |
| Tưởng `--icon` tự đổi JavaFX/Swing stage icon | Icon UI không theo ý muốn | Thiết lập qua API framework |
| Build bằng JDK mới rồi quên cập nhật runtime trong bundle | Bản ứng dụng vẫn chứa runtime cũ nếu không rebuild | Repackage và phân phối bản cập nhật |

## 11. Bài tập có đáp án

**Câu 1.** Bốn tùy chọn quan trọng nhất của chủ đề là gì?  
**Đáp án:** `--name`, `--app-version`, `--vendor` và `--icon`.

**Câu 2.** Nếu không đặt `--app-version`, mặc định theo Oracle là gì?  
**Đáp án:** `1.0`. Với bản phát hành thật nên đặt version rõ ràng.

**Câu 3.** `--app-version 2.4.1` có khiến `java.version` là `2.4.1` không?  
**Đáp án:** Không. Đó là hai tầng phiên bản khác nhau.

**Câu 4.** Windows dùng file icon định dạng nào? Linux, macOS dùng gì?  
**Đáp án:** Windows `.ico`, Linux `.png`, macOS `.icns`.

**Câu 5.** `--icon assets/lesson.ico` được tính đường dẫn từ đâu?  
**Đáp án:** Từ current working directory của shell (nếu là đường dẫn tương đối), không tự từ `--input`.

**Câu 6.** Nếu `--input input` và JAR nằm ở `input/app-demo.jar` thì `--main-jar` cần ghi gì?  
**Đáp án:** `app-demo.jar`.

**Câu 7.** Có thể dùng `--vendor` thay cho code signing không?  
**Đáp án:** Không; vendor chỉ là chuỗi thông tin, không xác thực tác giả.

**Câu 8.** Cách kiểm tra version/vendor của launcher Windows trong demo là gì?  
**Đáp án:** Dùng `(Get-Item .\dist\LessonDesk\LessonDesk.exe).VersionInfo` và xem `ProductVersion`, `CompanyName`, v.v.

**Câu 9.** `--type app-image` tạo installer `msi` đúng không?  
**Đáp án:** Không; nó tạo application image. Tạo installer cần `--type` thích hợp và môi trường native tương ứng.

## 12. Tổng kết và tài liệu tham khảo chính thức

**Tư duy đúng:** metadata cho **sản phẩm được đóng gói**, không phải các trường bắt buộc trong lớp Java. Khi phát hành, xác định một **tên sản phẩm**, một **version có thể nâng cấp**, một **vendor đúng**, một **icon phù hợp từng OS**; truyền rõ vào `jpackage`, build app image và chạy launcher thật trước khi đưa tới người dùng.

`jpackage` chính thức từ Java 16, vẫn được hỗ trợ trong Java 17+; không dùng hướng dẫn incubator Java 14 cho dự án mới.

Nguồn chính thức:

- [Oracle Java SE 25 — Basic Packaging](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html): ý nghĩa và mặc định của tên, version, vendor, icon.
- [Oracle Java SE 25 — The jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): tham số hiện hành `--name`, `--app-version`, `--vendor`, `--icon`.
- [Oracle Java SE 21 — Override jpackage Resources](https://docs.oracle.com/en/java/javase/21/jpackage/override-jpackage-resources.html): tài nguyên icon theo OS và `--resource-dir`.
- [Oracle Java SE 21 — Packaging Overview](https://docs.oracle.com/en/java/javase/21/jpackage/packaging-overview.html): `app-image` và giới hạn nền tảng.
- [Oracle JDK 16 Release Notes](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html): quá trình chuẩn hóa `jpackage` từ Java 14 tới Java 16.
