# Ràng buộc tạo gói ứng dụng Java trên nền tảng đích bằng `jpackage`

## 1. Bài toán: cùng một mã Java, nhưng gói cài đặt không giống nhau

Một ứng dụng Java có thể có **JAR** dùng trên nhiều hệ điều hành nếu môi trường có Java tương thích và ứng dụng không phụ thuộc thành phần native riêng. Tuy nhiên, khi cần phát hành như một ứng dụng mà người dùng **cài đặt và mở bằng launcher của hệ điều hành**, tệp cài đặt, cấu trúc thư mục, runtime nhúng và công cụ đóng gói trở thành **đặc thù của nền tảng đích**.

Java cung cấp công cụ `jpackage` để tạo:

- **Application image**: một thư mục ứng dụng chứa launcher, nội dung ứng dụng và Java runtime phù hợp.
- **Native installer**: gói cài đặt theo định dạng của hệ điều hành như `.exe`, `.msi`, `.deb`, `.rpm`, `.dmg` hoặc `.pkg`.

**Nguyên tắc quan trọng nhất:** `jpackage` **không hỗ trợ tạo native package cho hệ điều hành khác từ host đang chạy**. Muốn tạo gói Windows cần chạy `jpackage` trên Windows; muốn tạo gói macOS cần chạy trên macOS; muốn tạo gói Linux cần chạy trên Linux. Có thể điều phối các job bằng CI/CD, VM hoặc runner tương ứng, nhưng **không có tùy chọn `--target-os` để biến một lần chạy trên Windows thành bộ cài macOS/Linux**.

Nguyên tắc này áp dụng **cả với application image**: một image được tạo trên Windows có launcher và runtime Windows, nên không thể coi thư mục đó là gói di động nguyên xi sang macOS hoặc Linux. **Mã nguồn/JAR có thể tái sử dụng; image và installer phải được tạo, kiểm thử theo nền tảng.**

**Phiên bản hiện hành:** `jpackage` xuất hiện từ Java 14 ở giai đoạn incubating (JEP 343), và trở thành công cụ chuẩn từ **JDK 16** (JEP 392). Với bài học Java 14, hãy sử dụng cú pháp và cách triển khai **ổn định trên JDK 17, 21 và các phiên bản hiện đại**, không dùng cách bật module incubator đã lỗi thời. Trước mỗi lần đóng gói, kiểm tra `jpackage --help` trên đúng JDK/host đang sử dụng.

## 2. Bảng nền tảng, định dạng và môi trường tạo gói

| Nền tảng nơi chạy `jpackage` | Loại gói native | Yêu cầu chính | Điều cần kiểm tra thêm |
| --- | --- | --- | --- |
| **Windows** | `exe`, `msi` | JDK có `jpackage`; bộ công cụ WiX phù hợp khi tạo installer | Phiên bản WiX được JDK hỗ trợ, quyền cài đặt, signing, kiến trúc CPU |
| **macOS** | `dmg`, `pkg` | JDK và công cụ hệ thống macOS cần thiết | Kiến trúc Apple Silicon/Intel, bundle metadata, signing, notarization và Gatekeeper khi phân phối |
| **Linux** | `deb`, `rpm` | JDK và bộ công cụ tạo package của phân phối | Debian packaging tools/`fakeroot` cho môi trường phù hợp, `rpmbuild` cho RPM, thư viện native, kiến trúc CPU |
| **Mọi hệ điều hành được hỗ trợ** | `app-image` | JDK/`jpackage` của nền tảng hiện tại | Image **vẫn phụ thuộc OS/CPU**, không phải JAR portable |

Tên định dạng `deb` hoặc `rpm` không có nghĩa mọi phân phối Linux đều cài và chạy gói đó giống nhau. Trên Linux, cần kiểm tra trình quản lý gói, glibc/các thư viện liên quan, file association, launcher, cấu trúc thư mục và các dependency thật sự.

Tương tự, **Windows `.exe` installer không phải cùng loại tệp với `.exe` launcher** bên trong một application image. Một tệp `DemoPack.exe` ở thư mục image là chương trình khởi động ứng dụng; một output `DemoPack-1.0.exe` do `jpackage --type exe` tạo là bộ cài đặt. Không nên gửi riêng launcher exe rồi nghĩ toàn bộ runtime đã đi kèm.

**Cách kiểm tra thực tế:**

```bash
java -version
javac -version
jpackage --version
jpackage --help
```

`jpackage --help` trên **Windows** hiển thị các giá trị `--type` được hỗ trợ trên host đó, điển hình `app-image`, `exe`, `msi`; nó không hiển thị `dmg` như một loại gói có thể tạo trực tiếp tại Windows. Trên macOS/Linux, danh sách loại gói và tùy chọn nền tảng khác.

Nếu máy chỉ có **JRE** hoặc không cung cấp bộ công cụ của JDK, lệnh `jpackage` có thể không sẵn có. Cần có một **JDK phát hành cùng công cụ `jpackage`**, không thể chỉ dựa vào `java -version` rồi khẳng định đóng gói được.

## 3. Phân biệt ba loại sản phẩm đầu ra

### 3.1. JAR: phần ứng dụng có thể tái sử dụng

Một tệp `.jar` chứa class và tài nguyên Java đã biên dịch. Nếu được build với `javac --release 17`, nó có thể chạy trên runtime Java tương thích với bytecode/API mục tiêu, nhưng điều đó **không tự giải quyết** các dependency native, quyền truy cập file, giao diện đồ họa hoặc các tích hợp OS.

Ví dụ:

```bash
java -jar demo.jar
```

Nếu ứng dụng có dependency bên ngoài, cần cung cấp đúng classpath/module path, hoặc tạo JAR theo chiến lược đóng gói dependency phù hợp. Có JAR là điều kiện đầu vào, không tự tạo launcher/công cụ cài đặt hệ điều hành.

### 3.2. Application image: đã có launcher và runtime theo OS

`jpackage --type app-image` tạo **thư mục** chứa launcher của nền tảng, các file ứng dụng và runtime Java cần thiết (do `jlink` tạo hoặc do bạn cung cấp).

Ví dụ cấu trúc khái quát:

```text
Windows:
DemoPack/
  DemoPack.exe
  app/
  runtime/

Linux:
DemoPack/
  bin/
  lib/

macOS:
DemoPack.app/
  Contents/
    MacOS/
    app/
    runtime/
```

Các tên thư mục/file bên trong có thể có thêm file cấu hình, thư viện và tài nguyên, tùy OS/JDK; **không chỉnh cấu trúc nội bộ dựa trên giả định cố định** nếu chưa cần. Nếu phân phối image, phải phân phối **trọn bộ nội dung**, không chỉ copy launcher.

`app-image` hữu ích để **thử trước**: tạo image, chạy launcher, xác nhận runtime và tài nguyên đã đầy đủ; sau đó mới tạo installer.

### 3.3. Native installer: phục vụ cài đặt hệ điều hành

Native installer là một đầu ra khác, ví dụ:

```bash
# Chỉ chạy trên Windows với toolchain installer phù hợp:
jpackage --type msi --name DemoPack \
  --input input --main-jar demo.jar \
  --main-class sample.Main --dest output
```

Đây là **lệnh đa dòng Bash minh họa cú pháp option**; trên PowerShell hãy đặt trên một dòng hoặc dùng cú pháp nối dòng của PowerShell. Để tạo `msi`, host phải là Windows và bộ công cụ tạo installer phù hợp phải sẵn có. Nếu chưa cài WiX, `--type app-image` có thể hoạt động trong khi `--type msi` thất bại.

Gói cài đặt cũng cần được kiểm tra hành vi **install/upgrade/uninstall**, không chỉ kiểm tra launcher chạy.

## 4. Ví dụ Java 17+ đầy đủ: tạo Windows application image

Bài kiểm thử này dùng **Windows**, vì đây là một nền tảng có thể kiểm chứng được lệnh đóng gói và launcher. Các lệnh ở mục này dành cho **PowerShell trên Windows**, nơi đã có `javac`, `jar` và `jpackage` trên `PATH`.

### 4.1. Tạo mã nguồn

Đặt tệp `src/sample/Main.java`:

```java
package sample;

public class Main {
    public static void main(String[] args) {
        System.out.println("PACKAGED_OK=" + Runtime.version().feature());
        System.out.println("ARGS=" + args.length);
    }
}
```

Mã chỉ dùng Java SE, không có dependency ngoài. `Runtime.version().feature()` hiển thị **phiên bản Java đang chạy** trong runtime được đóng gói; nó không phải phiên bản `--release` dùng khi biên dịch.

### 4.2. Biên dịch và tạo JAR

Tại thư mục dự án (có thư mục `src`), dùng PowerShell:

```powershell
New-Item -ItemType Directory -Force classes, input, output | Out-Null

javac --release 17 -encoding UTF-8 -d classes src/sample/Main.java

jar --create --file input/demo.jar --main-class sample.Main -C classes .
```

- `javac --release 17` biên dịch mã với API và bytecode tương thích Java 17.
- `jar --create` tạo `input/demo.jar` có `Main-Class` chỉ tới `sample.Main`.
- `--main-jar demo.jar` ở bước tiếp theo là **đường dẫn tương đối từ thư mục `--input input`**, không phải đường dẫn tuyệt đối ngẫu nhiên.

Trước khi làm package, có thể kiểm tra bằng:

```powershell
java -jar input/demo.jar
```

### 4.3. Tạo và chạy image

```powershell
jpackage --type app-image --name DemoPack --input input --main-jar demo.jar --main-class sample.Main --app-version 1.0 --dest output --win-console

.\output\DemoPack\DemoPack.exe
```

**Đây là lệnh đã kiểm chứng trên Windows với OpenJDK 24, mã được biên dịch bằng `--release 17`.** Đầu ra thực tế:

```text
PACKAGED_OK=24
ARGS=0
```

Giải thích:

1. `--type app-image` yêu cầu tạo **thư mục ứng dụng**, không phải bộ cài `msi` hoặc `exe`.
2. `--input input` chứa JAR và các tài nguyên đi kèm; `--main-jar` và `--main-class` xác định điểm khởi động.
3. `--name DemoPack` đặt tên ứng dụng/launcher; `--app-version 1.0` khai báo phiên bản.
4. `--dest output` chọn nơi ghi đầu ra; thư mục Windows ví dụ là `output/DemoPack/`.
5. `--win-console` là **tùy chọn chỉ dùng trên Windows** để launcher mở console cho chương trình CLI, giúp nhìn thấy `System.out.println`.
6. `PACKAGED_OK=24` phản ánh **JDK 24 dùng lúc tạo runtime image trong lần kiểm thử**, **không** có nghĩa chương trình phải chạy trên Java 24. Trên host dùng JDK 17 hoặc 21, con số dự kiến thay theo runtime được dùng để đóng gói.

Kết quả đã được xác minh bằng việc chạy **launcher trong application image**, không chỉ bằng việc `jpackage` trả mã thành công.

### 4.4. Từ image sang installer

Khi Windows image chạy ổn, có thể tạo installer trên **cùng nền tảng Windows**:

```powershell
jpackage --type msi --name DemoPack --input input --main-jar demo.jar --main-class sample.Main --app-version 1.0 --dest output --win-console
```

Lệnh này **chỉ là bước tham khảo, chưa được thực thi trong phép kiểm thử trên** vì việc tạo native installer còn phụ thuộc bộ công cụ WiX thích hợp với phiên bản `jpackage` và cấu hình máy. Không suy luận bộ cài đã được tạo thành công chỉ từ việc `app-image` hoạt động.

Các option khác như `--win-shortcut` và `--win-menu` có thể dùng theo yêu cầu phát hành. Kiểm tra `jpackage --help` trên JDK Windows đang dùng để biết chính xác option, thay vì copy nguyên các option có tiền tố `--win-` sang Linux/macOS.

## 5. Cùng một ứng dụng, tạo gói Linux và macOS như thế nào?

**Phần có thể tái sử dụng** là mã nguồn, JAR, bản release và thông tin version. **Phần cần chạy lại** là `jpackage` trên runner có OS và kiến trúc mục tiêu.

Giả sử mỗi runner đã có `input/demo.jar` (tạo từ cùng nguồn) và một JDK tương thích:

### Linux Debian/Ubuntu: DEB

```bash
jpackage --type deb \
  --name DemoPack \
  --input input \
  --main-jar demo.jar \
  --main-class sample.Main \
  --app-version 1.0 \
  --dest output
```

Cần chạy **trên Linux** với bộ công cụ tạo gói Debian cần thiết, cùng các dependency OS thực tế. Không nên dùng `--type deb` trên Windows. Để phát hành, hãy cài thử trên môi trường Debian/Ubuntu đích hoặc máy thử nghiệm tương ứng, xác nhận launcher và runtime.

### Linux phân phối RPM

```bash
jpackage --type rpm \
  --name DemoPack \
  --input input \
  --main-jar demo.jar \
  --main-class sample.Main \
  --app-version 1.0 \
  --dest output
```

Runner Linux tạo RPM thường cần `rpmbuild`/`rpm-build` và các công cụ của distribution. `rpm` và `deb` **không phải hai phần mở rộng có thể đổi tên để chuyển đổi qua lại**; chúng có metadata và hệ quản lý gói riêng.

### macOS: DMG hoặc PKG

```bash
jpackage --type dmg \
  --name DemoPack \
  --input input \
  --main-jar demo.jar \
  --main-class sample.Main \
  --app-version 1.0 \
  --dest output
```

```bash
jpackage --type pkg \
  --name DemoPack \
  --input input \
  --main-jar demo.jar \
  --main-class sample.Main \
  --app-version 1.0 \
  --dest output
```

Các lệnh này phải chạy **trên macOS**. Gói `dmg` thường chứa ứng dụng `.app` để phân phối, còn `pkg` là định dạng installer có logic cài đặt riêng. Nếu muốn phân phối cho người dùng ngoài môi trường tin cậy, kiểm tra yêu cầu **ký mã (code signing), notarization và Gatekeeper**; việc tạo thành công `dmg` hoặc `pkg` **không** tự chứng minh gói sẽ được macOS chấp nhận mà không có cảnh báo.

**Những lệnh Linux/macOS là cấu hình ví dụ dựa trên công cụ chính thức, không phải đầu ra đã thực thi trên Windows.** Với mỗi OS, cần chạy thực tế trên runner tương ứng.

## 6. Vì sao không thể dùng một host tạo mọi installer?

`jpackage` không đơn thuần “nén JAR rồi đổi tên file”. Nó còn tạo hoặc tích hợp nhiều thành phần phụ thuộc nền tảng:

- **Native launcher:** tệp thực thi Windows, macOS hoặc Linux, với quy ước khởi động khác nhau.
- **Java runtime image:** các thư viện thực thi và native modules phải phù hợp OS và **kiến trúc CPU**.
- **Metadata cài đặt:** thông tin tên, phiên bản, đường dẫn cài đặt, menu, shortcut, file association, quyền install/uninstall khác nhau.
- **Công cụ OS:** WiX, công cụ Debian/RPM, các tiện ích macOS phục vụ đóng gói và signing.
- **Mã native bổ sung:** JNI libraries, DLL/`so`/`dylib`, thư viện UI hoặc bộ giải mã có thể yêu cầu build riêng cho OS/CPU.

Ví dụ: chạy JDK Windows x64 sẽ không tự cho ra launcher macOS ARM64 hoặc runtime Linux ARM64 chỉ vì bytecode Java có thể tương thích. Cần toolchain JDK, dependencies và môi trường build dành cho đích.

**Giải pháp đúng không phải tìm tham số `--target-os`** (không có trong `jpackage` chuẩn), mà tổ chức build trên Windows/macOS/Linux tương ứng. VM, container hoặc CI runner có thể dùng **khi thực sự chạy đúng OS/toolchain**. Linux container không phải macOS, và một container không biến Windows runtime thành macOS runtime.

## 7. Ràng buộc kiến trúc CPU và phiên bản JDK

Hệ điều hành không phải yếu tố duy nhất. Cần phân biệt:

| Trục tương thích | Ví dụ | Điều phải xác nhận |
| --- | --- | --- |
| OS | Windows, macOS, Linux | Launcher/native installer tạo trên OS thích hợp |
| Kiến trúc | x86-64, ARM64 | JDK/runtime và thư viện native phù hợp kiến trúc đích |
| Phiên bản Java | 17, 21, 25... | Bytecode/API ứng dụng và runtime được đóng gói |
| Phân phối Linux | Debian/Ubuntu, RPM-based | Package manager, các thư viện hệ thống và dependency |
| Chính sách cài đặt | User/system-wide, signed/unsigned | Quyền, đường dẫn, cơ chế trust và ký gói |

Cần hiểu hai thao tác độc lập:

```bash
javac --release 17 ...
jpackage --type app-image ...
```

Lệnh `javac --release 17` đặt **mức tương thích biên dịch Java**, không đổi runtime và launcher của `jpackage` thành Java 17. Nếu chạy `jpackage` từ JDK 24, runtime được tạo thường dựa trên JDK đó; nếu muốn kiểm soát runtime, hãy dùng đúng JDK đóng gói hoặc chỉ rõ `--runtime-image` phù hợp.

### `--runtime-image` và `jlink`

Nếu không truyền `--runtime-image`, `jpackage` thường gọi `jlink` để tạo runtime. Bạn cũng có thể tạo trước runtime:

```bash
jlink --add-modules java.base,java.logging --output appRuntime
```

Rồi dùng khi đóng gói:

```bash
jpackage --type app-image --name DemoPack \
  --input input --main-jar demo.jar --main-class sample.Main \
  --runtime-image appRuntime --dest output
```

Các lệnh là **mẫu minh họa**; runtime `appRuntime` phải được tạo đúng OS/CPU và chứa **đầy đủ module mà ứng dụng thực sự dùng**, không chỉ module mẫu trong lệnh `jlink`. Với ứng dụng có JDBC, JavaFX, crypto/provider, reflection, `ServiceLoader` hoặc các thư viện khác, cần kiểm tra các module/dịch vụ tương ứng và test launcher thực sự.

Một khác biệt phiên bản cần lưu ý khi nâng cấp: trong **JDK 25 trở lên**, `jpackage` không còn tự động đưa các **service bindings** vào runtime image như một số phiên bản trước. Nếu ứng dụng dựa vào `ServiceLoader`, cần kiểm tra các provider trong image và cân nhắc tùy chọn `jlink --bind-services` qua cấu hình `--jlink-options` thích hợp. Đây là lý do không nên đổi JDK build mà bỏ qua bước smoke test.

## 8. Ràng buộc công cụ hệ điều hành trước khi tạo installer

### Windows: WiX và installer

Khi tạo `--type exe` hoặc `--type msi`, công cụ cần các thành phần build installer của Windows (thường là **WiX Toolset**, với phiên bản phù hợp JDK). Nếu thiếu hoặc không tương thích, lệnh tạo installer có thể lỗi **dù JAR chạy tốt và app-image đã được tạo thành công**.

Trước khi build nên:

- Kiểm tra `jpackage --help`, môi trường Windows và công cụ WiX tương thích theo hướng dẫn của JDK đang dùng.
- Kiểm tra metadata tên/version, hành vi cài đặt theo user/hệ thống, menu/shortcut và cơ chế update.
- Nếu cần phân phối rộng rãi, kiểm tra quy trình **ký executable/installer** và uy tín/chính sách trust trên Windows.
- Thực hiện thử nghiệm **install – launch – upgrade – uninstall**, không chỉ chạy `java -jar`.

**Không dùng thành công của `--type app-image` để kết luận WiX sẵn sàng.** App-image không nhất thiết yêu cầu toàn bộ công cụ tạo installer.

### macOS: signing và notarization

Để đóng gói trên macOS có thể cần các **Xcode command-line tools** cho một số thao tác, đặc biệt signing hoặc tùy chỉnh DMG icon. Quy trình phát hành công khai thường phải xét identity ký, entitlements, yêu cầu notarization và chính sách Gatekeeper.

`jpackage --mac-sign` là **tùy chọn dành cho macOS**, không hoạt động trên Windows/Linux. Không coi mọi gói macOS chưa ký đều không thể tạo; **khả năng tạo file** và **khả năng phân phối/cài đặt không cảnh báo** là hai yêu cầu riêng.

Khi hỗ trợ cả Intel và Apple Silicon, kiểm tra kiến trúc/khả năng tương thích của JDK và mọi thư viện native. Đừng giả định một `.app` tạo bằng runtime x64 tự trở thành ARM64 khi đổi máy chạy.

### Linux: công cụ tạo DEB/RPM và dependency

Trên môi trường thích hợp, build DEB thường cần **Debian packaging tools** (một số distro/runner cần `fakeroot`); build RPM cần **RPM build tools**. Hãy xác nhận bằng tài liệu của JDK và hệ Linux đích đang dùng, không suy diễn một dependency list cố định cho mọi distribution.

Sau khi build, kiểm tra thông tin package, dependency native và quyền cài đặt. Một DEB chạy được trên một bản Ubuntu không bảo đảm sẽ chạy trên mọi Linux, nhất là khi có thư viện đồ họa, glibc hoặc thư viện native khác.

## 9. Những tùy chọn dễ nhầm

| Tùy chọn | Dùng để làm gì? | Lưu ý |
| --- | --- | --- |
| `--type app-image` | Tạo thư mục ứng dụng chạy được trên host OS | Không phải installer |
| `--type exe/msi/deb/rpm/dmg/pkg` | Tạo installer theo OS | Chỉ định loại phù hợp host/toolchain |
| `--app-image DIR` | Dùng một **image đã tạo** làm đầu vào cho bước package/sign phù hợp | **Khác** `--type app-image` |
| `--input DIR` | Thư mục chứa JAR và file ứng dụng để copy vào image | Kiểm soát nội dung, tránh copy file thừa/secret |
| `--main-jar FILE` | JAR chính đối với ứng dụng non-modular | Tên file tương đối từ `--input` |
| `--main-class CLASS` | Main class trong JAR chính | Phải đúng package/class thực tế |
| `--module MOD/CLASS` | Điểm khởi động cho ứng dụng modular | Không trộn cùng `--main-jar` |
| `--runtime-image DIR` | Dùng runtime đã chuẩn bị trước | Phải phù hợp OS/CPU và đủ module |
| `--add-modules` | Bổ sung module cho runtime được tạo | Không bù được dependency ngoài bị thiếu |
| `--dest DIR` | Thư mục ghi đầu ra | Không đổi nền tảng đích |
| `--icon FILE` | Biểu tượng ứng dụng/gói | Định dạng và quy tắc theo OS, ví dụ ICO/ICNS/PNG |
| `--win-console` | Launcher console Windows cho CLI | Không phải tùy chọn chung trên Linux/macOS |
| `--verbose` | In thông tin chẩn đoán thêm khi đóng gói | Dùng khi package lỗi |

**Sai thường gặp:** dùng `--app-image output` khi ý định là **tạo mới** image. Khi tạo mới, dùng `--type app-image`. `--app-image` nhận **một đường dẫn tới image đã có** để làm đầu vào trong trường hợp phù hợp.

## 10. Thiết kế CI/CD cho ba hệ điều hành

Một pipeline có thể gồm phần **chung** và các job **theo OS**:

```text
              Nguồn Java + kiểm thử
                       |
             Build JAR / modules
                       |
             Lưu artifact chung
                       |
             +---------+---------+
             |         |         |
        Windows job  macOS job  Linux job
             |         |         |
           jpackage  jpackage  jpackage
             |         |         |
          exe/msi    dmg/pkg    deb/rpm
             |         |         |
         Test cài   Test app    Test cài
          đặt/gỡ     /ký số      đặt/gỡ
             +---------+---------+
                       |
                Phát hành theo OS
```

Các nguyên tắc:

1. **Tái sử dụng nguồn/JAR:** công việc biên dịch và unit test có thể dùng một artifact chung nếu dependency thuần Java.
2. **Chạy jpackage riêng:** dùng runner Windows cho Windows, macOS cho macOS, Linux cho Linux. Nếu cần cả `msi` và `exe`, thực hiện riêng bước tạo từng định dạng.
3. **Ghép đúng kiến trúc:** tạo artifact x64/ARM64 theo môi trường và dependency native tương ứng; đưa OS/architecture vào tên artifact phân phối.
4. **Cấp công cụ cho từng job:** WiX, công cụ package Linux, công cụ macOS/signing; xác định phiên bản thay vì phụ thuộc “máy build ngẫu nhiên”.
5. **Kiểm tra sản phẩm thật:** launcher từ app-image, cài đặt, chạy, gỡ, bản nâng cấp, file association/shortcut nếu dùng.
6. **Bảo mật bí mật ký gói:** certificate/private key và credential notarization chỉ có trên job được bảo vệ; không đóng chúng vào JAR, package hoặc JFR/log.
7. **Gắn thông tin phiên bản:** JDK toolchain, `jpackage` version, mã ứng dụng, phiên bản installer và kiến trúc phải có thể truy vết.

**Nếu build là trên container hoặc VM**, cần chắc chắn OS bên trong **thật sự** phù hợp với loại gói và có quyền/công cụ cần thiết. Một Linux Docker container chạy trên máy macOS vẫn là môi trường Linux khi gọi `jpackage` trong container; nó không tạo DMG macOS hợp lệ chỉ nhờ host vật lý là Mac.

## 11. Quy trình kiểm thử sau khi đóng gói

Một phép thử có ý nghĩa nên gồm **ba mức**.

### Mức 1 — Kiểm thử ứng dụng trước đóng gói

- `javac` và unit tests chạy thành công.
- JAR/module khởi động được; resource/dependency tồn tại.
- Kiểm tra phiên bản Java mục tiêu (`--release` hoặc cấu hình toolchain).

### Mức 2 — Kiểm thử application image

- `jpackage --type app-image` thành công.
- **Launcher được tạo** đúng trên host, chạy và in/hiển thị kết quả chính xác.
- App có thể đọc resource, font, locale, native library và config dự kiến.
- Không phụ thuộc nhầm vào JDK cài sẵn trên máy phát triển hoặc current working directory.
- Ứng dụng không giả định thư mục cài đặt **có thể ghi được**; dữ liệu người dùng và cache nên dùng vị trí phù hợp OS.

### Mức 3 — Kiểm thử native installer

- Tạo đúng định dạng và kiến trúc.
- Cài đặt trên máy thử **không có sẵn JDK**; ứng dụng vẫn chạy bằng runtime đi kèm.
- Kiểm tra quyền install/uninstall, đường dẫn, shortcuts, icon, file associations nếu có.
- Kiểm tra upgrade/downgrade theo chính sách version, đặc biệt Windows MSI/EXE.
- Trên macOS, kiểm tra signature/notarization/Gatekeeper theo kênh phát hành.
- Trên Linux, kiểm tra dependency và package manager của distro đích.
- Lưu artifact build, log lỗi và phiên bản công cụ để có thể tái hiện.

Không nên xem quá trình tạo installer **mã thoát 0** là hoàn thành QA. Cần cài và chạy thực sự trên máy đích hoặc môi trường kiểm thử có cấu hình tương đương.

## 12. Xử lý các lỗi phổ biến

| Hiện tượng | Nguyên nhân khả dĩ | Cách giải quyết |
| --- | --- | --- |
| `jpackage: command not found` | Máy không có JDK/tool trong PATH | Cài JDK có `jpackage`, xác minh `jpackage --version` |
| `--type dmg` không được chấp nhận trên Windows | Định dạng khác OS host | Chạy job macOS |
| `--type msi` thất bại nhưng app-image chạy | Thiếu/chưa tương thích WiX hoặc cấu hình installer | Kiểm tra toolchain, chạy `--verbose` |
| `--type deb` lỗi trên Linux | Thiếu Debian packaging tools, quyền/thư mục | Cài công cụ thích hợp, kiểm tra log |
| `--type rpm` lỗi | Thiếu `rpmbuild`/metadata hợp lệ | Cài RPM build tools và xác nhận config |
| Ứng dụng trong image không mở được | Sai main class, thiếu dependency/module/resource, JNI sai OS | Test launcher và kiểm tra log, module runtime |
| Ứng dụng chạy `java -jar` nhưng image lỗi | Runtime image được tạo khác môi trường phát triển | Rà soát `jlink`, `--add-modules`, service providers, native libs |
| macOS cảnh báo ứng dụng chưa đáng tin | Vấn đề signing/notarization hoặc chính sách Gatekeeper | Ký, kiểm tra entitlements và quy trình phân phối |
| Windows chạy launcher nhưng không thấy `println` | Console launcher không được cấu hình | Dùng `--win-console` cho ứng dụng CLI trên Windows |
| Installer chạy trên x64 nhưng không chạy trên ARM64 | Runtime/native library không đúng kiến trúc | Tạo/test gói trên runner kiến trúc phù hợp |
| Thay đuôi `.exe` sang `.dmg` | Không biến đổi nội dung hệ điều hành | Phải đóng gói lại trên OS đích |
| Ứng dụng cố ghi vào thư mục cài đặt | Thư mục cài thường hạn chế quyền ghi | Dùng user data/cache path phù hợp nền tảng |

Không nên sửa lỗi gói bằng cách bỏ qua quyền cài đặt, chạy mọi thứ dưới quyền quản trị hoặc tắt cơ chế bảo vệ OS. Cần điều tra nguyên nhân theo công cụ và môi trường đích.

## 13. Tự kiểm tra kiến thức

**Câu 1:** Có thể chạy một lần `jpackage --type msi` trên Linux để có gói Windows không?

**Đáp án:** Không. `jpackage` không hỗ trợ cross-platform package; cần chạy trên Windows và có toolchain installer phù hợp.

**Câu 2:** `javac --release 17` có bảo đảm runtime trong gói sẽ là JDK 17 không?

**Đáp án:** Không. `--release` kiểm soát mức biên dịch. Runtime do `jpackage`/`jlink` tạo theo JDK dùng khi đóng gói, trừ khi được cấu hình bằng một runtime image phù hợp.

**Câu 3:** Nếu một Windows app-image chạy thành công, có thể khẳng định `msi` đã sẵn sàng không?

**Đáp án:** Không. Native installer có thể cần WiX và metadata/quy trình build khác; phải thử tạo và cài `msi` riêng.

**Câu 4:** Vì sao chuyển một application image đã tạo trên Windows nguyên thư mục sang Linux không phải giải pháp cross-platform?

**Đáp án:** Image chứa **native launcher và runtime Windows**, không phải chỉ Java bytecode.

**Câu 5:** Ứng dụng dùng `ServiceLoader` có thể cần kiểm tra gì khi đổi JDK đóng gói?

**Đáp án:** Xác minh runtime image có module/provider cần dùng; lưu ý chính sách service binding khác giữa các JDK (đặc biệt JDK 25+), kiểm tra `--jlink-options`/`--bind-services` khi thực sự cần và smoke test launcher.

**Câu 6:** Quy trình CI cho ba OS nên chia thế nào?

**Đáp án:** Có thể build/test JAR chung, sau đó chạy **các job packaging riêng trên Windows/macOS/Linux**, mỗi job có JDK, toolchain OS, signing và phép thử cài đặt phù hợp.

**Ghi nhớ:** `jpackage` tạo launcher, runtime và gói cài đặt mang tính **nền tảng đích**, không phải một trình biên dịch installer xuyên OS. Để phát hành nhiều hệ điều hành, hãy **dùng cùng mã Java/JAR nhưng đóng gói trên từng OS/kiến trúc**, kiểm tra công cụ native, runtime image, ký gói và cài đặt thực tế. `--type app-image` giúp thử sản phẩm trước khi tạo native installer.

### Tham khảo chính thức còn áp dụng

- [JEP 392 — Packaging Tool (chuẩn từ JDK 16)](https://openjdk.org/jeps/392).
- [JDK 25 — Packaging Overview and Prerequisites](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html).
- [JDK 25 — jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html).
- [JDK 21 — jpackage Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html).
- [JDK 25 — Basic Packaging](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html).
