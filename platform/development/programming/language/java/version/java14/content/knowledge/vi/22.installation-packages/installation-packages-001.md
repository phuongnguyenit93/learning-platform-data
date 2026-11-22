# Chọn định dạng gói cài đặt jpackage được hỗ trợ trên hệ điều hành đích

## 1. Vấn đề cần giải quyết

Khi phát hành ứng dụng Java cho người dùng cuối, một file `.jar` có thể chưa đủ: người dùng muốn cài phần mềm theo quy trình quen thuộc của hệ điều hành. Công cụ **`jpackage`** trong JDK tạo gói phân phối chứa ứng dụng Java, launcher native và Java runtime cần thiết.

Tùy chọn quyết định **định dạng đầu ra** là:

~~~text
jpackage --type <package-type> [các tùy chọn ứng dụng]
~~~

Không phải giá trị `--type` nào cũng được hỗ trợ trên mọi máy. Ví dụ: `--type msi` là **Windows Installer package**, `--type deb` là **Debian package**, `--type dmg` là **macOS disk image**. Việc chỉ đổi tham số `--type` **không thể** dùng Windows để build trực tiếp native package dành cho macOS hoặc Linux.

**Quy tắc chọn đúng:**

1. Xác định **hệ điều hành và cơ chế cài đặt trên máy đích**.
2. Chọn **format phù hợp với hệ điều hành đó**.
3. Build bằng `jpackage` **trên hệ điều hành tương ứng**.
4. Kiểm tra có **công cụ đóng gói native** cần thiết.
5. Thử **cài đặt, chạy, nâng cấp, gỡ cài** bằng artifact thật trên môi trường đích.

**Phiên bản Java hiện đại:** `jpackage` được đưa vào JDK 14/15 dưới dạng incubating, rồi trở thành công cụ chính thức từ **JDK 16** (JEP 392). Nội dung bài dựa trên option và hành vi vẫn được duy trì trong tài liệu Oracle JDK 17/25/26. Ví dụ Java dùng `--release 17` và không yêu cầu API preview hoặc module incubator cũ.

## 2. Bảng định dạng được hỗ trợ theo hệ điều hành

| Hệ điều hành đích | Giá trị `--type` cho **native package** | Artifact tạo ra | Hệ thống cài đặt/tiêu thụ |
| --- | --- | --- | --- |
| **Windows** | `exe` | `.exe` installer | Trình cài đặt native Windows |
| **Windows** | `msi` | `.msi` | Windows Installer; phù hợp nhiều quy trình quản lý phần mềm |
| **macOS** | `dmg` | `.dmg` | Disk image, thường chứa `.app` để người dùng kéo/copy |
| **macOS** | `pkg` | `.pkg` | Installer package của macOS |
| **Linux** | `deb` | `.deb` | Hệ sinh thái Debian/Ubuntu và các máy hỗ trợ gói DEB |
| **Linux** | `rpm` | `.rpm` | Các hệ sinh thái RPM như Fedora/RHEL/openSUSE |
| **Windows, macOS, Linux** | `app-image` | Thư mục/bundle ứng dụng | **Không phải native installer**; chạy launcher trực tiếp |

**Chú ý phân biệt:** `--type app-image` là giá trị `jpackage` hỗ trợ để tạo **application image có launcher, ứng dụng và runtime**, nhưng **không phải gói cài đặt native**. Nó hữu ích để QA và làm bước trung gian trước khi tạo installer.

### Windows: `exe` hay `msi`?

- Chọn **`exe`** nếu sản phẩm muốn bộ cài dạng chương trình executable, phù hợp workflow người dùng tải rồi chạy installer.
- Chọn **`msi`** nếu cần gói theo Windows Installer, chẳng hạn quy trình triển khai và quản trị ứng dụng dựa trên MSI.
- Cả hai là **đầu ra Windows**, khác với file `.exe` là **launcher** nằm trong thư mục app image.
- Để tạo hai định dạng cho cùng ứng dụng, phải chạy `jpackage` **hai lần**, một lần cho mỗi giá trị `--type`.
- Đừng suy ra MSI tự giải quyết toàn bộ bài toán auto-update, kiểm soát nâng cấp hoặc ký số. Các yêu cầu đó vẫn cần cấu hình, kiểm tra và quy trình phát hành riêng.

### macOS: `dmg` hay `pkg`?

- **`dmg`** phù hợp kiểu phân phối mở disk image rồi copy ứng dụng `.app` tới nơi người dùng muốn. Nó **không nhất thiết** có trình hướng dẫn cài đặt kiểu PKG.
- **`pkg`** là định dạng installation package của macOS, thích hợp khi cần workflow cài đặt theo cơ chế package.
- Đừng nhầm `HelloApp.app` là bản thân một `.pkg`. `.app` là **application bundle**, có thể nằm trong một `.dmg` hoặc được cài bởi `.pkg`.
- Với bản phát hành macOS, kiểm tra yêu cầu về **code signing** và **notarization** theo chính sách phân phối của ứng dụng. Việc chọn `dmg` hoặc `pkg` không tự động chứng minh artifact đã được ký hoặc notarize đúng.

### Linux: `deb` hay `rpm`?

- **`deb`** dành cho máy và kênh phân phối hỗ trợ DEB (Debian/Ubuntu và các hệ thống tương thích).
- **`rpm`** dành cho máy và kênh phân phối hỗ trợ RPM (Fedora/RHEL/openSUSE và các hệ thống tương thích).
- Chọn theo **hệ thống quản lý package trên máy nhận**. Từ “Linux” một mình chưa đủ để biết người dùng sẽ dùng DEB hay RPM.
- Không phải cứ dùng hệ điều hành Linux là tự động có cả mọi toolchain; muốn build mỗi loại cần công cụ bổ sung thích hợp trên máy build.
- Việc một file DEB/RPM được tạo không bảo đảm nó tương thích mọi bản phân phối hoặc mọi phiên bản Linux; vẫn cần thử cài đặt và runtime dependencies.

## 3. Kiểm tra `--type` được hỗ trợ trên máy build

`jpackage` có lệnh tự mô tả:

~~~text
jpackage --help
~~~

Phần trợ giúp nêu **các giá trị `--type` hợp lệ cho môi trường đang chạy công cụ**, cùng những tùy chọn dành riêng cho nền tảng đó. Đây là cách nhanh nhất để xác nhận máy build hiện tại, thay vì sao chép một danh sách toàn cầu và đoán.

Trong một lần kiểm thử thực tế trên **Windows với `jpackage 24.0.2`**, phần loại gói của `jpackage --help` hiển thị:

~~~text
Valid values are: {"app-image", "exe", "msi"}
~~~

Lệnh **`jpackage --type deb`** trên Windows đã bị từ chối với thông báo:

~~~text
Error: Invalid or unsupported type: [deb]
~~~

Hai kết quả trên chỉ xác nhận hành vi **trên Windows JDK 24 trong lần chạy thử**, không phải một bản in giống hệt cho Linux hoặc macOS. Trên hệ điều hành khác, danh sách local `--type` tương ứng với nền tảng đó.

Đọc `jpackage --help` giúp kiểm tra **hỗ trợ format ở cấp công cụ**, nhưng **chưa chứng minh toàn bộ prerequisites đã sẵn sàng**. Ví dụ trên Windows, trợ giúp có thể liệt kê `msi`, trong khi lệnh build thật vẫn thất bại nếu máy thiếu **WiX Toolset** thích hợp.

### Bốn điều kiện độc lập phải đúng

| Điều kiện | Câu hỏi kiểm tra |
| --- | --- |
| **Đúng OS** | Máy build là Windows, macOS hay Linux phù hợp với installer? |
| **Đúng package type** | `jpackage --help` trên máy đó có `exe/msi/dmg/pkg/deb/rpm` mong muốn? |
| **Đủ toolchain** | WiX, công cụ Debian/RPM, hoặc công cụ macOS cần thiết đã có đúng phiên bản? |
| **Đúng ứng dụng** | Có JAR/module, main class, dependencies, Java runtime/modules tương thích và metadata không? |

Nếu một trong bốn điều kiện sai, đừng coi việc format xuất hiện trong tài liệu Java toàn cầu là bằng chứng lệnh build chắc chắn thành công.

## 4. Định dạng mặc định không nhất thiết là định dạng muốn phát hành

Nếu **không truyền** `--type`, `jpackage` tạo package có **format mặc định phụ thuộc nền tảng** theo tài liệu Oracle:

| Nền tảng máy build | Mặc định `jpackage` khi không có `--type` |
| --- | --- |
| Windows | `exe` |
| macOS | `dmg` |
| Debian-based Linux | `deb` |
| Các Linux còn lại theo quy tắc mặc định được tài liệu Oracle mô tả | `rpm` |

Ví dụ trên Windows:

~~~powershell
jpackage --name ExampleApp --input .\input --main-jar ExampleApp.jar
~~~

Nếu thiếu các option khác không bắt buộc và môi trường đủ toolchain, `jpackage` sẽ mặc định tạo **EXE installer**, **không** tạo `app-image` và cũng không tự chọn MSI. Trên macOS, mặc định có thể là DMG; trên Debian là DEB.

**Thực hành cho CI/CD:** luôn ghi rõ `--type`, ví dụ `--type msi` hoặc `--type deb`. Như vậy quy trình không vô tình đổi định dạng khi chuyển sang một runner khác. Đồng thời ghi rõ `--name`, `--app-version` và `--dest` để artifact dễ nhận diện, phân loại và triển khai.

Không nên dùng lựa chọn mặc định như một hình thức “tự phát hiện” cơ chế quản lý package của tất cả người dùng; hệ thống build thường chỉ biết môi trường **của chính nó**, trong khi người dùng có thể ở nhiều distro hoặc công ty dùng chính sách triển khai riêng.

## 5. Java 17: ví dụ xác định format hợp lệ theo OS đích

Để thấy rõ ranh giới hỗ trợ, ta có thể viết một chương trình nhỏ **chỉ tư vấn và kiểm tra định dạng**. Nó **không chạy `jpackage`** và **không thay thế kiểm tra toolchain**, nhưng minh họa cách từ chối lựa chọn sai ngay từ cấu hình.

Tạo file **`PackageFormatChooserDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;

public class PackageFormatChooserDemo {
    static List<String> supported(String target) {
        return switch (target.toLowerCase(Locale.ROOT)) {
            case "windows" -> List.of("exe", "msi");
            case "macos" -> List.of("dmg", "pkg");
            case "linux" -> List.of("deb", "rpm");
            default -> throw new IllegalArgumentException("Unknown platform");
        };
    }

    static String select(String target, String requestedType) {
        if (!supported(target).contains(requestedType)) {
            throw new IllegalArgumentException(
                    "Unsupported installer type for " + target);
        }
        return requestedType;
    }

    public static void main(String[] args) {
        System.out.println("windows=" + String.join(",", supported("windows")));
        System.out.println("macos=" + String.join(",", supported("macos")));
        System.out.println("linux=" + String.join(",", supported("linux")));
        System.out.println("windowsSelected=" + select("windows", "msi"));
        System.out.println("linuxSelected=" + select("linux", "deb"));

        boolean rejected = false;
        try {
            select("windows", "deb");
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("windowsDebRejected=" + rejected);
        System.out.println("appImageIsNotInstaller=true");
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 PackageFormatChooserDemo.java
java PackageFormatChooserDemo
~~~

**Stdout đã được kiểm thử:**

~~~text
windows=exe,msi
macos=dmg,pkg
linux=deb,rpm
windowsSelected=msi
linuxSelected=deb
windowsDebRejected=true
appImageIsNotInstaller=true
~~~

Giải thích:

- `supported("windows")` trả đúng hai định dạng installer native dành cho Windows là `exe` và `msi`.
- `supported("macos")` và `supported("linux")` liệt kê các loại package được tài liệu Java hỗ trợ trên hai nền tảng đó.
- `select("windows", "deb")` bị từ chối **trước khi chạy công cụ**, tránh yêu cầu bất khả thi trên runner Windows.
- Dòng `appImageIsNotInstaller=true` là **thông điệp giải thích cố định** do chương trình ví dụ in ra, không phải một biến được `jpackage` kiểm tra.
- Hàm `select` nhận **OS đích do caller đã xác định**, không tự nhận biết distro hay xác minh quyền cài đặt. Nó cũng so khớp tên type chính xác; có thể thêm khâu chuẩn hóa input nếu ứng dụng cần nhận chuỗi tùy ý.
- Trên Linux, việc nhận `deb` hoặc `rpm` trong danh sách **chưa có nghĩa cả hai đã sẵn toolchain** hay sẽ cài được trên distro nhận. Đây chỉ là vòng chọn format **ở cấp platform**.

Trong pipeline thực tế, hãy kết hợp mapping này với việc chạy `jpackage --help`, kiểm tra toolchain và cài thử package được tạo.

## 6. Ví dụ thực hành trên Windows: build app image để kiểm tra trước khi chọn installer

Khi chuẩn bị tạo MSI hoặc EXE, trước tiên nên bảo đảm ứng dụng đóng gói **chạy thật**. Dưới đây là ví dụ file Java dùng Java 17, build JAR rồi tạo app image trên Windows. Nó chứng minh launcher/runtime hoạt động trước bước đóng gói installer.

Tạo file **`FormatSelectionApp.java`**:

~~~java
public class FormatSelectionApp {
    public static void main(String[] args) {
        System.out.println("Launcher works on Windows");
        System.out.println("argumentCount=" + args.length);
    }
}
~~~

Mở **PowerShell trên Windows** có `javac`, `jar` và `jpackage` trong `PATH`; chạy tại thư mục chứa file nguồn:

~~~powershell
New-Item -ItemType Directory -Force -Path classes, input, out
javac --release 17 -encoding UTF-8 -d classes .\FormatSelectionApp.java
jar --create --file .\input\FormatSelectionApp.jar --main-class FormatSelectionApp -C classes .
jpackage --type app-image --name FormatSelectionApp --input .\input --main-jar FormatSelectionApp.jar --dest .\out --win-console
.\out\FormatSelectionApp\FormatSelectionApp.exe one two
~~~

**Stdout của launcher thực tế:**

~~~text
Launcher works on Windows
argumentCount=2
~~~

Trên máy kiểm thử Windows JDK 24, bước kiểm tra đã xác nhận:

~~~text
appImageDirectory=True
launcherExists=True
runtimeExists=True
Launcher works on Windows
argumentCount=2
~~~

Điểm quan trọng: câu lệnh `jpackage --type app-image` đã tạo **thư mục `out\FormatSelectionApp`**, trong đó có launcher `.exe` và runtime. **Đây chưa phải bộ cài EXE/MSI**. Sau khi image chạy ổn, mới quyết định định dạng native installer phù hợp với người dùng Windows.

`--win-console` là tùy chọn **Windows-only**, giúp ví dụ dòng lệnh in stdout ra console khi chạy launcher. Không copy option này sang lệnh Linux/macOS.

**Phạm vi kiểm chứng:** phần tạo và chạy **app image** đã thực thi thành công. Môi trường thử chưa có công cụ WiX trong `PATH`; vì vậy các lệnh tạo MSI/EXE installer ở phần tiếp theo là **hướng dẫn cú pháp theo tài liệu**, không phải kết quả đã tạo file MSI/EXE thực tế.

## 7. Các lệnh jpackage cho từng hệ điều hành

Giả sử ứng dụng đã được biên dịch thành file `FormatSelectionApp.jar`, nằm trong thư mục `input` và có `Main-Class` đúng trong manifest. Chọn **một dòng** dành cho format muốn tạo.

### Windows: EXE hoặc MSI

~~~powershell
# Chạy trên Windows với WiX tương thích.
jpackage --type exe --name FormatSelectionApp --app-version 1.0 --input .\input --main-jar FormatSelectionApp.jar --dest .\installers --win-console

jpackage --type msi --name FormatSelectionApp --app-version 1.0 --input .\input --main-jar FormatSelectionApp.jar --dest .\installers --win-menu --win-shortcut
~~~

Hai lệnh trên là **ví dụ tài liệu, chưa được chạy thử tạo installer**. Mục tiêu là **cùng một ứng dụng** nhưng hai format đầu ra Windows khác nhau. Có thể chạy cả hai nếu sản phẩm cần hai kênh phân phối, nhưng không phải một lệnh tạo đồng thời EXE và MSI.

`--win-menu` và `--win-shortcut` là option dành cho tích hợp menu/shortcut trên Windows khi tạo installer. `--win-console` có ích cho ví dụ console app; với GUI app thật, thường cân nhắc bỏ nó.

### Debian/Ubuntu: DEB

~~~bash
# Chạy trên Linux phù hợp, có toolchain DEB.
jpackage --type deb --name FormatSelectionApp --app-version 1.0 --input input --main-jar FormatSelectionApp.jar --dest installers
~~~

Cần hệ thống build Linux và các công cụ Debian packaging phù hợp. Oracle hướng dẫn `fakeroot` là một prerequisite trên Ubuntu. Đầu ra mong muốn là package `.deb` để cài bằng package manager tương thích.

### RPM-based Linux: RPM

~~~bash
# Chạy trên Linux phù hợp, có toolchain RPM.
jpackage --type rpm --name FormatSelectionApp --app-version 1.0 --input input --main-jar FormatSelectionApp.jar --dest installers
~~~

Theo tài liệu Oracle, môi trường Red Hat Linux cần `rpm-build`. Đầu ra mong muốn là package `.rpm`, nhưng vẫn phải kiểm tra các dependency và chính sách distro cụ thể trước khi phát hành.

### macOS: DMG hoặc PKG

~~~bash
# Chạy trên macOS; chọn một kiểu phân phối.
jpackage --type dmg --name FormatSelectionApp --app-version 1.0 --input input --main-jar FormatSelectionApp.jar --dest installers

jpackage --type pkg --name FormatSelectionApp --app-version 1.0 --input input --main-jar FormatSelectionApp.jar --dest installers
~~~

Các lệnh Linux/macOS **không được thực thi trên máy thử Windows**; chúng là cú pháp tham khảo phù hợp với tài liệu Oracle. Với macOS, Xcode command-line tools cần thiết trong một số thao tác ký gói (`--mac-sign`) và tùy chỉnh icon DMG. Việc thêm `--type dmg/pkg` không tự động ký hoặc notarize.

**Không chạy đồng thời hai lệnh vào cùng thư mục output nếu dễ gây nhầm artifact.** Với CI, nên có thư mục đích riêng theo OS/format/version, ví dụ `artifacts/windows-msi` và `artifacts/windows-exe`. Tên thư mục này là quy ước triển khai do dự án đặt, không phải yêu cầu bắt buộc của `jpackage`.

## 8. Prerequisites: supported type chưa đồng nghĩa build thành công

Tài liệu Oracle JDK 26 quy định **build native package trên target platform**, cần JDK, ứng dụng và software hỗ trợ đóng gói.

| OS/format | Yêu cầu cần kiểm tra |
| --- | --- |
| Windows `exe` / `msi` | **WiX Toolset** tương thích bản JDK; Oracle mô tả yêu cầu WiX 3.0 trở lên, nhưng phải xem hỗ trợ chính xác của JDK đang chạy |
| Linux `deb` | Công cụ Debian packaging; ví dụ Oracle nêu `fakeroot` cho Ubuntu |
| Linux `rpm` | Công cụ RPM packaging; ví dụ Oracle nêu `rpm-build` trên Red Hat |
| macOS `dmg` / `pkg` | Công cụ do macOS cung cấp; với yêu cầu ký hoặc tùy biến icon có thể cần Xcode command-line tools |

**Phân biệt ba loại lỗi:**

1. **Unsupported type:** chẳng hạn `--type deb` trên Windows → `jpackage` báo không hỗ trợ (đã kiểm chứng).
2. **Supported type nhưng thiếu toolchain:** chẳng hạn `--type msi` trên Windows nhưng không có WiX phù hợp → không tạo được MSI; đây không tự động là lỗi Java source.
3. **Toolchain đủ nhưng ứng dụng đóng gói sai:** thiếu JAR, sai `--main-jar`, thiếu main class, Java modules/native dependencies hoặc option sai → lỗi ở input/cấu hình đóng gói.

Đừng giải quyết lỗi thứ nhất chỉ bằng cách cài thêm toolchain của hệ điều hành khác. Ví dụ cài `dpkg` trên Windows không có nghĩa `jpackage` chính thức hỗ trợ cross-build native Linux DEB trên Windows.

### Cách kiểm tra thực hành

Trước build, nên chạy trên **mỗi runner**:

~~~text
java -version
javac -version
jpackage --version
jpackage --help
~~~

Trên Linux, kiểm tra thêm công cụ phù hợp với package manager (ví dụ `fakeroot`, `rpmbuild`) theo pipeline. Trên Windows, kiểm tra WiX đã được cài đúng và công cụ có thể được `jpackage` tìm thấy. Trên macOS, kiểm tra công cụ ký/notarization khi quy trình phát hành yêu cầu.

**Lưu ý:** một vài lệnh kiểm tra chỉ cho biết công cụ tồn tại trong `PATH`. Để chắc chắn, phải chạy build thật và cài thử artifact: các yêu cầu version, quyền, dependency hoặc môi trường có thể khác nhau.

## 9. Nếu cần phát hành cho nhiều OS, thiết kế build matrix

Thực hành thường gặp trong CI:

| Job/runner | Loại artifact | Ý nghĩa |
| --- | --- | --- |
| Windows runner | `--type exe` | Bộ cài EXE |
| Windows runner | `--type msi` | Gói Windows Installer |
| macOS runner | `--type dmg` | Mac disk image |
| macOS runner | `--type pkg` | Mac installer package |
| Linux runner phù hợp DEB | `--type deb` | Gói Debian |
| Linux runner phù hợp RPM | `--type rpm` | Gói RPM |

Có thể chia source/JAR và test logic Java dùng chung. Tuy vậy mỗi job cần **tạo runtime và launcher phù hợp với OS/architecture**, rồi mới sinh package native.

Ví dụ kế hoạch pipeline (mang tính cấu trúc, không phải file CI cấu hình cụ thể):

~~~text
Build & test application
  ├─ Windows: prepare JDK + WiX
  │    ├─ jpackage --type exe
  │    └─ jpackage --type msi
  ├─ macOS: prepare JDK + native packaging tools
  │    ├─ jpackage --type dmg
  │    └─ jpackage --type pkg
  └─ Linux: prepare JDK + distro packaging tools
       ├─ jpackage --type deb
       └─ jpackage --type rpm
            ↓
     OS-specific install/launch QA
            ↓
     Approved release artifacts
~~~

Đừng đặt kỳ vọng một Windows job tạo xong toàn bộ sáu định dạng chỉ vì `jpackage` liệt kê toàn cầu các loại `--type` có thể dùng. Nếu dự án hỗ trợ **nhiều kiến trúc CPU**, cần xác định runner/runtime phù hợp từng kiến trúc thay vì coi tên format là đủ.

**Khi nào không cần mọi format?** Nếu đối tượng người dùng chỉ là Windows doanh nghiệp yêu cầu MSI, không cần tạo `dmg` hoặc `rpm`. Nếu phân phối một tiện ích Linux chỉ cho Debian-based systems, có thể chỉ cần DEB. Format nên xuất phát từ **phạm vi nền tảng thực sự được sản phẩm hỗ trợ**, không phải checklist buộc tạo tất cả gói.

## 10. App image là lựa chọn hỗ trợ QA, không thay native installer

Tạo app image là một cách kiểm thử trước khi tiêu tốn thời gian tạo installer:

~~~bash
jpackage --type app-image --name ExampleApp --input input --main-jar ExampleApp.jar --dest image-output
~~~

Với Windows, output là thư mục chứa launcher `ExampleApp.exe` và runtime; với macOS là `.app` bundle; với Linux là cây thư mục ứng dụng có launcher. Có thể chạy launcher để kiểm tra classpath, Java modules, resources, JVM options và dependencies.

Từ image đã thử, có thể dùng workflow hai giai đoạn:

~~~text
Application JAR/module
         |
         v
jpackage --type app-image
         |
         v
Kiểm tra launcher và runtime
         |
         v
jpackage --type <installer type> --app-image <đường dẫn image>
         |
         v
Native installable package
~~~

Cần dùng `--app-image` theo đúng cú pháp cho platform; không kết hợp `--app-image` và `--runtime-image` trong cùng lệnh tạo installer từ image. Muốn đổi runtime, hãy chọn runtime lúc tạo image trước đó. **App image tự nó không có trạng thái installed/uninstalled giống native installer.**

**Không đồng nhất với native compilation:** launcher native không có nghĩa class Java đã được biên dịch hoàn toàn thành machine code không dùng JVM. `jpackage` đóng gói Java runtime trong image và installer; công cụ như GraalVM Native Image là chủ đề khác.

## 11. Kiểm tra artifact sau build: từ “đúng đuôi” đến “cài và chạy được”

**Đúng phần mở rộng chưa đủ để kết luận hợp lệ.** Một pipeline phát hành cần kiểm tra:

### Cấp artifact

- Loại file được sinh đúng với `--type` và OS/format đích.
- Có metadata tên ứng dụng, version, vendor, description nếu quy trình cần.
- Đúng kiến trúc hệ điều hành/CPU, ứng dụng và Java runtime được đóng gói tương thích.
- Chữ ký của installer/app bundle và nguồn tải phù hợp với chính sách phát hành; checksum chỉ có ích nếu được phân phối từ nguồn đáng tin.
- Artifact được lưu/tên hóa theo platform/format/version để tránh nhầm một file EXE launcher với EXE installer.

### Cấp cài đặt

- Có thể **cài** trên máy sạch không có JDK phát triển riêng.
- Shortcut/menu/file association được tạo đúng **nếu có cấu hình**.
- Ứng dụng chạy bằng launcher sau khi cài, dùng đúng JVM options và có đủ Java modules.
- Thư mục cài và quyền đọc/ghi hợp lệ cho người dùng mục tiêu.
- Có thể **gỡ cài**, và giữ/xóa dữ liệu người dùng đúng quy định.
- Có thể **nâng cấp** từ một phiên bản trước; không chỉ thử cài mới.

### Cấp chức năng

- Kết nối mạng/cơ sở dữ liệu, file IO, locale, timezone, fonts, TLS và native libraries hoạt động trên OS đích.
- Ứng dụng không vô tình phụ thuộc `JAVA_HOME` hoặc JDK của máy build.
- Cơ chế log và xử lý lỗi hoạt động trong môi trường cài đặt thực.
- Khi thay phiên bản Java runtime đóng gói, kiểm thử lại modules hoặc service providers có liên quan.

Đối với JDK 25 trở đi, tài liệu Oracle ghi nhận runtime do `jpackage` tự sinh không còn tự động bao gồm **service bindings** như các phiên bản trước; ứng dụng dựa vào ServiceLoader có thể cần cấu hình `--jlink-options --bind-services` theo tài liệu và kiểm thử lại. Đây là một ví dụ cho thấy **đúng installer type vẫn chưa bảo đảm runtime đủ các khả năng của ứng dụng**.

## 12. Những lỗi phổ biến và cách sửa

**Lỗi 1 — Chọn `--type deb` trên Windows.**  
Không hỗ trợ. Hãy chạy build DEB trên Linux với công cụ phù hợp.

**Lỗi 2 — Chọn `--type dmg` trên Linux.**  
Không hỗ trợ. Hãy dùng macOS runner để tạo DMG.

**Lỗi 3 — Cho rằng bất kỳ Linux nào cũng nên dùng DEB.**  
Sai. Chọn DEB hoặc RPM theo distro/cơ chế package manager được người dùng hỗ trợ.

**Lỗi 4 — Không truyền `--type` trong CI.**  
Có thể nhận format mặc định khác khi đổi runner. Hãy chỉ định tường minh `--type exe/msi/deb/rpm/dmg/pkg`.

**Lỗi 5 — Nhầm `--type app-image` với gói cài đặt.**  
App image là launcher/app/runtime có thể chạy, không phải bộ cài native. Cần bước tạo package khác nếu người dùng muốn cài theo OS.

**Lỗi 6 — Nhầm hai file `.exe` trên Windows.**  
EXE launcher nằm trong image và EXE installer do `--type exe` tạo là hai sản phẩm khác nhau.

**Lỗi 7 — Thấy `msi` trong `--help` nên nghĩ không cần WiX.**  
Sai. `--help` xác nhận loại gói được phép trên OS, chưa xác nhận prerequisite của toolchain.

**Lỗi 8 — Nghĩ mỗi lần chạy `jpackage` có thể xuất cả MSI và EXE.**  
Muốn nhiều format phải chạy **một lần cho mỗi type**.

**Lỗi 9 — Tạo package xong nhưng không cài thử.**  
File tồn tại chưa chứng minh quy trình install/uninstall/upgrade thành công.

**Lỗi 10 — Cho rằng macOS DMG và PKG có cùng cách cài.**  
Sai. DMG là disk image phân phối, còn PKG là gói cài đặt theo macOS installer.

**Lỗi 11 — Tưởng `--release 17` quyết định Java runtime được bundling.**  
Sai. `javac --release 17` kiểm soát mức bytecode/API lúc biên dịch; runtime dùng khi `jpackage` tạo image phụ thuộc JDK đóng gói hoặc `--runtime-image`.

**Lỗi 12 — Tưởng native package tự ký số và tự cập nhật.**  
Không. Ký số, notarization, auto-update, chính sách upgrade và CI release là những phần phải thiết kế riêng.

**Lỗi 13 — Tưởng có JAR chạy được là đủ.**  
Cần kiểm tra launcher, native libraries, modules, quyền và hành vi sau khi cài trên máy đích.

**Lỗi 14 — Tưởng có thể “giả làm” macOS bằng tham số target.**  
Không có option `--target-os macos` giúp tạo native Mac installer từ Windows theo quy trình jpackage hỗ trợ.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Chạy `jpackage --type msi` trên Linux có được không?  
**Đáp án:** Không theo hỗ trợ chính thức. MSI là định dạng Windows, cần Windows runner.

**Câu 2.** Ubuntu và Fedora thường dùng cùng một định dạng package `jpackage` không?  
**Đáp án:** Thường không. Debian/Ubuntu dùng DEB, Fedora/RPM-based dùng RPM.

**Câu 3.** Trên Windows, `jpackage --help` chỉ có `app-image, exe, msi`. Điều này chứng minh WiX đã cài chưa?  
**Đáp án:** Chưa. Danh sách cho biết format phù hợp với OS; vẫn cần công cụ tạo installer.

**Câu 4.** Nếu bỏ `--type` trên macOS, định dạng native mặc định là gì theo Oracle?  
**Đáp án:** `dmg`. Trong CI nên ghi `--type dmg` rõ ràng.

**Câu 5.** Muốn tạo cả MSI và EXE cho cùng một ứng dụng Windows, cần mấy lần gọi `jpackage`?  
**Đáp án:** Ít nhất **hai lần**, mỗi lần một giá trị `--type`.

**Câu 6.** `--type app-image` tạo native installer không?  
**Đáp án:** Không. Nó tạo image có launcher, ứng dụng và runtime để chạy trực tiếp.

**Câu 7.** Có thể dùng app image Windows cho installer macOS không?  
**Đáp án:** Không. Image chứa launcher và runtime theo Windows, không thể chuyển thành bản Mac chỉ bằng đổi type.

**Câu 8.** Vì sao một `.dmg` được tạo thành công chưa đủ khẳng định release macOS sẵn sàng?  
**Đáp án:** Vẫn cần test mở/copy/launch, quyền, compatibility và signing/notarization nếu áp dụng.

**Câu 9.** `jpackage --type deb` trả lỗi unsupported trên Windows thì cần sửa nội dung JAR không?  
**Đáp án:** Không nhất thiết. Phải chuyển build sang Linux phù hợp; lỗi thuộc hỗ trợ OS/format, không chứng minh JAR sai.

**Câu 10.** Runtime có Java đi kèm rồi có thể bỏ kiểm tra ServiceLoader/modules không?  
**Đáp án:** Không. Runtime image cần đầy đủ module và service bindings cho chức năng thật; quy tắc `jlink/jpackage` có thể thay đổi giữa các bản JDK.

## Tài liệu chính thức

- **Oracle JDK 26 – Packaging Overview**: bảng OS và native formats (Windows `exe/msi`; macOS `dmg/pkg`; Linux `deb/rpm`), yêu cầu build trên target platform, toolchain bổ sung: https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html
- **Oracle JDK 25 – Basic Packaging**: defaults theo nền tảng (Windows `exe`, macOS `dmg`, Debian `deb`, các Linux còn lại `rpm`), `--name`, `--app-version` và `--dest`: https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html
- **Oracle JDK 26 – jpackage Command**: cách dùng `--type`, `--input`, `--main-jar`, `--module` và các option platform: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html
- **Oracle JDK 25 – Packaging Overview**: Java runtime, prerequisites và thay đổi service bindings của `jpackage` từ JDK 25: https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html
- **Oracle JDK 17 – jpackage Command**: cú pháp đã ổn định cho Java 17+: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html
- **OpenJDK JEP 392 – Packaging Tool**: `jpackage` chính thức từ JDK 16, không còn quy trình incubating cũ: https://openjdk.org/jeps/392