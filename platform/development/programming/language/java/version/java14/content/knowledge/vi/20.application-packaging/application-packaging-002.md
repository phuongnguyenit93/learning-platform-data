# Từ công cụ ươm tạo Java 14 tới `jpackage` chính thức từ Java 16

## 1. Khái niệm và kết luận cần nhớ

`jpackage` là công cụ của **JDK** để đóng gói một ứng dụng Java thành **application image** (thư mục ứng dụng tự chứa launcher và Java runtime) hoặc **gói cài đặt gốc của hệ điều hành**. Mục tiêu là phân phối một ứng dụng Java mà người dùng cuối thường **không cần tự cài đặt JDK/JRE riêng**.

Lịch sử của công cụ có ý nghĩa khi đọc hướng dẫn cũ:

| Phiên bản | Trạng thái của `jpackage` | Điều cần biết ngày nay |
| --- | --- | --- |
| Java 14 — JEP 343 | **Incubating tool** | Bước giới thiệu và thử nghiệm; không dùng tên module ươm tạo trong hướng dẫn Java hiện đại |
| Java 15 | Tiếp tục incubating để nhận phản hồi | Đây vẫn là giai đoạn chuyển tiếp, không phải giao diện công cụ cuối cùng |
| **Java 16 — JEP 392** | **Được đưa thành tính năng chính thức, production-ready** | Mốc để sử dụng công cụ như một phần JDK ổn định |
| Java 17, 21 và JDK mới | `jpackage` tiếp tục được hỗ trợ, tài liệu hóa | Dùng cú pháp và lựa chọn của **JDK đang triển khai**, kiểm tra trên OS đích |

Trong JDK 14/15, module cung cấp công cụ có tên `jdk.incubator.jpackage`. Khi chính thức ở JDK 16, tên chuyển sang **`jdk.jpackage`**. **Tên lệnh `jpackage` không đổi.** Việc chuyển trạng thái không làm Java tự sinh installer từ mã `.java`; bạn vẫn cần **build ứng dụng trước**.

**Special Note về kiến thức hiện hành:** Bài này chỉ dùng Java 14/15 để giải thích **mốc lịch sử**, không yêu cầu bật module incubator, không dùng cờ thử nghiệm cũ và không đề xuất chạy quy trình đóng gói bằng JDK 14. Mọi bước thực hành dùng **JDK 17+** và API/công cụ chính thức.

## 2. Hai loại kết quả: application image và native installer

`jpackage` có thể tạo **hai loại sản phẩm**, phù hợp với những tình huống khác nhau.

### 2.1. Application image: để chạy thử và phân phối theo thư mục

```text
[Ứng dụng JAR hoặc module] + [Java runtime image]
                 |
              jpackage
                 |
          application image
        [launcher + app + runtime]
```

Với `--type app-image`, công cụ tạo một thư mục/bundle ứng dụng có launcher riêng và Java runtime phù hợp. Đây **không phải một installer có giao diện cài đặt**; thường bạn có thể chạy launcher trực tiếp trong thư mục đầu ra.

Ví dụ:

```bash
jpackage --type app-image --name PackDemo --input input --main-jar packaging-demo.jar --main-class PackagingDemo --dest dist
```

Trong đó `input` là thư mục chứa JAR **đã build**, và `packaging-demo.jar` phải nằm trong thư mục ấy.

Đây là **dạng lệnh đa nền tảng**. Nếu ứng dụng là chương trình dòng lệnh và đang build trên Windows, nên thêm `--win-console` để launcher có console:

```powershell
jpackage --type app-image --name PackDemo --input input --main-jar packaging-demo.jar --main-class PackagingDemo --dest dist --win-console
```

`--win-console` **chỉ dành cho Windows**; không đưa tùy chọn này vào lệnh chạy trên Linux hoặc macOS.

### 2.2. Native installer: gói cài đặt theo hệ điều hành

`jpackage` cũng tạo được gói cài đặt theo OS, chẳng hạn:

| Hệ điều hành nơi build | `--type` installer thường dùng | Đầu ra |
| --- | --- | --- |
| Windows | `exe` hoặc `msi` | Bộ cài đặt Windows |
| Linux | `deb` hoặc `rpm` | Gói theo hệ thống quản lý package tương ứng |
| macOS | `pkg` hoặc `dmg` | Gói cài đặt/phân phối macOS |

**Không có cross-platform packaging:** Theo tài liệu Oracle, gói cho một nền tảng phải được **tạo trên chính nền tảng đó**. Không thể mặc nhiên tạo bộ cài Windows trên Linux bằng `--type exe`. Để phát hành ba nền tảng, thường dùng **ba môi trường build tương ứng**, ví dụ CI runners cho Windows/Linux/macOS.

Đừng nhầm `app-image` với native installer. Tạo application image trước giúp kiểm tra launcher và Java runtime độc lập, sau đó mới xây installer nếu cần. Installer có thể đòi hỏi **công cụ native bổ sung**, quyền ký ứng dụng và cấu hình hệ điều hành tùy phiên bản JDK.

## 3. Điều gì ổn định từ Java 16 và điều gì vẫn phụ thuộc môi trường?

Những ý tưởng còn đúng trong Java 17+:

1. **Đầu vào là ứng dụng đã build**: JAR hoặc module, kèm file tài nguyên/phụ thuộc cần thiết.
2. **Launcher riêng**: người dùng có thể chạy ứng dụng qua một executable hoặc app bundle do `jpackage` tạo.
3. **Java runtime được đóng kèm**: nếu không truyền `--runtime-image`, `jpackage` thường dùng `jlink` để tạo runtime image thích hợp.
4. **Đóng gói native theo OS**: `exe`/`msi`, `deb`/`rpm`, `pkg`/`dmg` là các lựa chọn hiện hành, nhưng không thay thế quy trình build trên OS đích.
5. **Metadata và tùy biến**: tên ứng dụng, phiên bản, vendor, icon, JVM options, launcher phụ, file associations và chính sách cài đặt tùy theo nhu cầu.

Những điều **không** nên coi là bất biến tuyệt đối: cấu trúc thư mục của application image trên mọi OS, phiên bản công cụ native cần để tạo installer, quy trình ký/notarization, cách hiển thị shortcut, và bộ module runtime mà một ứng dụng classpath cần. Vì vậy, luôn đọc `jpackage --help` và tài liệu của **JDK đang dùng**.

### Không nhầm tên module công cụ với module của ứng dụng

Từ Java 16, module **`jdk.jpackage`** là một phần triển khai công cụ đóng gói. Nhưng bạn **không cần thêm**:

```java
// KHÔNG phải yêu cầu của ứng dụng chỉ để được đóng gói:
requires jdk.jpackage;
```

Đoạn trên chỉ minh họa **hiểu nhầm cần tránh**. Ứng dụng chỉ cần khai báo các module **thực sự dùng khi chạy**, ví dụ `requires java.sql;` nếu cần JDBC. `jpackage` là công cụ **trong quá trình build/distribution**, không phải dependency runtime mà mọi ứng dụng Java phải yêu cầu.

Tương tự, **đừng viết `requires jdk.incubator.jpackage;`** trong một dự án Java hiện đại: đó là tên **lịch sử** của giai đoạn ươm tạo, không phải cách dùng chính thức từ Java 16.

## 4. Workflow đóng gói hiện đại

Một quy trình triển khai dễ kiểm soát:

1. **Build và kiểm thử ứng dụng** với JDK target, tạo JAR hoặc modular artifacts.
2. **Chạy thử bằng `java`** để biết chương trình hoạt động trước khi đóng gói.
3. **Gọi `jpackage --type app-image`** để tạo launcher và runtime image.
4. **Chạy launcher đã tạo**; kiểm tra tham số, tài nguyên, quyền file và hành vi trên hệ điều hành thực.
5. Nếu cần installer, **tạo gói native trên chính OS mục tiêu**, kiểm tra cài đặt, khởi chạy và gỡ cài đặt.
6. **Ký và phân phối** ứng dụng theo yêu cầu nền tảng; quản lý phiên bản, cập nhật, lỗ hổng runtime và giấy phép/phụ thuộc.

Trong pipeline này, `jpackage` **không thay thế `javac`, hệ thống build (Maven/Gradle) hay kiểm thử**. Nó nhận các file đầu ra của quá trình build.

## 5. Chương trình Java 17+ hoàn chỉnh: đóng gói ứng dụng JAR

Đây là ví dụ **không sử dụng JPMS module của ứng dụng**, thích hợp để bắt đầu vì chỉ cần một JAR có lớp `main`.

### 5.1. Tạo mã nguồn

Tạo tệp `src/PackagingDemo.java`:

```java
public class PackagingDemo {
    public static void main(String[] args) {
        System.out.println("app=PackDemo");
        System.out.println("args=" + args.length);
    }
}
```

Mã chạy được với Java 17+ và không cần thư viện ngoài JDK.

Cấu trúc ban đầu:

```text
project/
└── src/
    └── PackagingDemo.java
```

### 5.2. Biên dịch, đóng JAR, chạy thử

Tại thư mục `project`, tạo các thư mục `classes`, `input` và `dist`. Trên Linux/macOS:

```bash
mkdir -p classes input dist
```

Trên Windows PowerShell, có thể dùng:

```powershell
New-Item -ItemType Directory -Force classes,input,dist
```

Sau đó chạy các lệnh JDK sau (dấu `/` trong đường dẫn được Java/JDK trên các hệ điều hành hỗ trợ):

```bash
javac --release 17 -d classes src/PackagingDemo.java
jar --create --file input/packaging-demo.jar -C classes .
java -cp input/packaging-demo.jar PackagingDemo
```

Đầu ra của bước chạy thử JAR:

```text
app=PackDemo
args=0
```

Giải thích:

- `javac --release 17` đặt mức API và mã bytecode Java 17, giúp phát hiện việc dùng API không tương thích với phiên bản target.
- `-d classes` là thư mục đầu ra của class file.
- `jar --create --file ... -C classes .` đóng toàn bộ nội dung `classes` vào JAR.
- `java -cp ... PackagingDemo` chạy trực tiếp bằng **classpath**, không cần khai báo `Main-Class` trong manifest vì lệnh chỉ rõ lớp `PackagingDemo`.
- Đối với `jpackage` ở bước sau, ta cũng truyền `--main-class PackagingDemo` tường minh.

### 5.3. Tạo application image

Chạy lệnh **nền tảng chung**:

```bash
jpackage --type app-image --name PackDemo --input input --main-jar packaging-demo.jar --main-class PackagingDemo --dest dist
```

Nếu build trên **Windows cho ứng dụng console**, dùng biến thể sau để nhìn được stdout:

```powershell
jpackage --type app-image --name PackDemo --input input --main-jar packaging-demo.jar --main-class PackagingDemo --dest dist --win-console
```

Giải thích các tham số quan trọng:

| Tham số | Ý nghĩa |
| --- | --- |
| `--type app-image` | Tạo application image **không** tạo installer |
| `--name PackDemo` | Đặt tên ứng dụng và launcher |
| `--input input` | Thư mục chứa JAR và các file ứng dụng cần đưa vào image |
| `--main-jar packaging-demo.jar` | JAR chính, tính theo **đường dẫn tương đối so với `--input`** |
| `--main-class PackagingDemo` | Lớp chứa `public static void main(String[] args)` |
| `--dest dist` | Thư mục chứa sản phẩm đóng gói |
| `--win-console` | Windows: tạo launcher có cửa sổ console cho ứng dụng CLI |

**Đặc biệt:** `--main-jar` là **tên JAR nằm bên trong `input`**, không phải `input/packaging-demo.jar` khi đã chỉ định `--input input`. Viết cả tiền tố `input/` vào `--main-jar` có thể khiến công cụ tìm sai file.

### 5.4. Chạy launcher đã đóng gói

Trên Windows PowerShell:

```powershell
.\dist\PackDemo\PackDemo.exe
```

Trên Linux, vị trí launcher của application image thường có dạng:

```bash
./dist/PackDemo/bin/PackDemo
```

Trên macOS, đường dẫn app bundle có thể có dạng:

```bash
./dist/PackDemo.app/Contents/MacOS/PackDemo
```

Các vị trí là **hình thức đầu ra theo nền tảng**, có thể khác nếu tùy biến công cụ hoặc thay đổi layout. Khi không chắc, hãy xem nội dung thư mục `dist` sau khi đóng gói.

Với JFR hỗ trợ? **Không liên quan**: ví dụ này chỉ dùng `java.base`, không cần module JFR hoặc dịch vụ JFR. Mục tiêu là chứng minh `jpackage` hoạt động với ứng dụng Java cơ bản.

**Đầu ra khi chạy launcher console thành công:**

```text
app=PackDemo
args=0
```

**Kiểm chứng thực tế:** Ví dụ đã được biên dịch với `javac --release 17`, tạo JAR, chạy JAR, sau đó `jpackage --type app-image` trên Windows (với `--win-console`), và chạy executable trong `dist/PackDemo`. Cả lần chạy JAR lẫn launcher đều in đúng hai dòng trên. Đối với Linux/macOS, cần kiểm thử bằng môi trường build cùng OS tương ứng.

### 5.5. Có cần `Main-Class` trong manifest không?

Không nhất thiết khi dùng `--main-class` tường minh. Nếu JAR đã có `Main-Class` trong manifest, `jpackage` có thể dựa vào đó khi không chỉ rõ `--main-class`; nhưng để tài liệu và pipeline dễ tái lập, việc truyền `--main-class` một cách rõ ràng là hợp lý.

Nếu ứng dụng có nhiều dependency JAR, hãy **đưa đủ dependency runtime** vào `--input` hoặc dùng cách phân phối module/phụ thuộc phù hợp, kiểm tra classpath và launcher sau khi package. Một JAR chỉ có mã của ứng dụng nhưng thiếu thư viện cần thiết sẽ không tự chạy được chỉ vì đã được đóng cùng runtime.

## 6. Ứng dụng có JPMS: `--module` thay cho `--main-jar`

`jpackage` cũng hỗ trợ **ứng dụng mô-đun** được khai báo bằng `module-info.java`. Khác với app JAR theo classpath, entry point ở đây dùng:

```text
--module module.name/package.Main
```

### 6.1. Cấu trúc dự án

```text
src/
└── com.example.pkgdemo/
    ├── module-info.java
    └── com/
        └── example/
            └── pkgdemo/
                └── Main.java
```

Tệp `src/com.example.pkgdemo/module-info.java`:

```java
module com.example.pkgdemo {
}
```

Tệp `src/com.example.pkgdemo/com/example/pkgdemo/Main.java`:

```java
package com.example.pkgdemo;

public class Main {
    public static void main(String[] args) {
        System.out.println("modular=true");
    }
}
```

Đây là ứng dụng độc lập, chỉ yêu cầu `java.base` ngầm định. **Không yêu cầu `jdk.jpackage` trong `module-info.java`.**

### 6.2. Build và chạy theo module path

```bash
javac --release 17 -d mods --module-source-path src -m com.example.pkgdemo
java --module-path mods --module com.example.pkgdemo/com.example.pkgdemo.Main
```

Đầu ra:

```text
modular=true
```

### 6.3. Đóng gói ứng dụng mô-đun

```bash
jpackage --type app-image --name ModPackDemo --module-path mods --module com.example.pkgdemo/com.example.pkgdemo.Main --dest dist
```

Trên Windows, để nhìn thấy đầu ra của ví dụ console:

```powershell
jpackage --type app-image --name ModPackDemo --module-path mods --module com.example.pkgdemo/com.example.pkgdemo.Main --dest dist --win-console
```

Launcher Windows tạo ra có đường dẫn điển hình `dist/ModPackDemo/ModPackDemo.exe`. Khi chạy, nó in:

```text
modular=true
```

Mã JPMS và lệnh `jpackage` theo `--module` trên đây cũng đã được **biên dịch, đóng thành application image và chạy launcher thực tế trên Windows** với đầu ra `modular=true`.

**Không dùng đồng thời `--module` và `--main-jar`**: Oracle quy định đây là hai cách chỉ định đầu vào chính, **loại trừ nhau**. Chọn:

- **Ứng dụng classpath/JAR:** `--input`, `--main-jar` và `--main-class` khi cần.
- **Ứng dụng JPMS:** `--module-path`, `--module module/main-class`.

Nếu một dự án là ứng dụng classpath với nhiều thư viện không mô-đun, đừng chuyển sang JPMS chỉ để dùng `jpackage`; công cụ vẫn hỗ trợ đóng gói classpath apps.

## 7. Java runtime kèm theo: vai trò của `jlink`

Một phần giá trị của `jpackage` là tạo **bản Java runtime phục vụ ứng dụng**, giúp người dùng cuối không phải tự cài Java rồi cấu hình `JAVA_HOME`.

Với nhiều ứng dụng, khi không cung cấp runtime image, `jpackage` dùng `jlink` để tạo runtime dựa trên các module cần thiết. Sự khác nhau quan trọng:

- Với **ứng dụng JPMS**, công cụ có thể dựa vào main module và đồ thị phụ thuộc `requires` để tính tập module runtime.
- Với **ứng dụng classpath**, tập module mặc định có thể rộng hơn vì không có module descriptor để suy ra chính xác toàn bộ phụ thuộc.
- Nếu ứng dụng nạp lớp bằng reflection, `ServiceLoader`, plugin hoặc dynamic code, một số dependency có thể không hiện rõ qua phân tích tĩnh. Hãy **kiểm thử packaged launcher thực tế**.
- `--add-modules`, `--module-path` và `--jlink-options` có thể tinh chỉnh runtime image, nhưng đừng bỏ module chỉ để giảm dung lượng khi chưa kiểm tra chức năng.

Có thể dùng runtime image tự chuẩn bị:

```bash
jpackage --type app-image --name PackDemo --input input --main-jar packaging-demo.jar --main-class PackagingDemo --runtime-image custom-runtime --dest dist
```

Đây là **lệnh minh họa**, giả định `custom-runtime` đã được tạo hợp lệ bằng `jlink` hoặc một quy trình tương đương và chứa các module/tài nguyên ứng dụng cần. Khi có `--runtime-image`, `jpackage` dùng runtime bạn cung cấp thay vì tự tạo bằng `jlink` cho lần đóng gói đó.

**Không nhầm application image với toàn bộ JDK.** Runtime trong gói thường là bản rút gọn phục vụ **chạy ứng dụng**, không phải bộ công cụ phát triển với `javac`, `jpackage` và mọi lệnh JDK.

## 8. Tạo installer native: khi nào và như thế nào?

Sau khi đã thử `app-image` thành công, có thể tạo installer trên **OS tương ứng**. Ví dụ minh họa:

Windows (cần công cụ native đáp ứng yêu cầu của phiên bản JDK):

```powershell
jpackage --type exe --name PackDemo --input input --main-jar packaging-demo.jar --main-class PackagingDemo --dest installers --win-console
```

Linux Debian-based (chạy trên Linux hỗ trợ gói `deb`):

```bash
jpackage --type deb --name PackDemo --input input --main-jar packaging-demo.jar --main-class PackagingDemo --dest installers
```

macOS (chạy trên macOS):

```bash
jpackage --type dmg --name PackDemo --input input --main-jar packaging-demo.jar --main-class PackagingDemo --dest installers
```

**Đây là những lệnh minh họa theo nền tảng**, không phải ba lệnh được kiểm thử trong một máy. Cài thêm tool đóng gói native nếu JDK yêu cầu: công cụ tạo installer Windows, công cụ package trên Linux hoặc công cụ ký/gói trên macOS có thể khác nhau theo phiên bản JDK và OS. Đừng ghi cố định một phiên bản WiX hay Xcode cho tất cả JDK hiện tại; đối chiếu tài liệu đúng phiên bản build.

Một cách khác là tạo installer **từ application image đã xây và kiểm thử**:

```bash
jpackage --type exe --name PackDemo --app-image dist/PackDemo --dest installers
```

Lệnh cuối **chỉ mang tính minh họa cho Windows**. `--app-image` trỏ tới image đã có. Với macOS/Linux, dùng kiểu installer và đường dẫn image tương ứng.

### Tên, phiên bản và metadata khi phân phối

Các tùy chọn hiện hành thường có ích:

| Tùy chọn | Mục đích |
| --- | --- |
| `--name` | Tên ứng dụng |
| `--app-version` | Phiên bản phân phối của ứng dụng |
| `--vendor` | Tên nhà phát hành |
| `--description` | Mô tả |
| `--icon` | Icon theo định dạng phù hợp OS |
| `--arguments` | Tham số mặc định cho chương trình |
| `--java-options` | Tùy chọn JVM khi chạy |
| `--license-file` | Tệp giấy phép đi kèm installer |
| `--install-dir` | Vị trí cài đặt theo nền tảng |
| `--add-launcher` | Launcher phụ theo cấu hình |
| `--file-associations` | Liên kết với phần mở rộng tệp |
| `--resource-dir` | Tùy biến tài nguyên gói theo mẫu platform-specific |

Đối với `--app-version`, các nền tảng có quy tắc định dạng và sắp xếp phiên bản riêng; hãy dùng **phiên bản được chấp nhận trên OS đích** và kiểm tra quá trình nâng cấp từ phiên bản cũ.

Để phân phối ra công chúng, cần cân nhắc **ký mã (code signing), notarization, quyền cài đặt, bảo vệ file cấu hình và quy trình update**. `jpackage` không tự mang lại hệ thống cập nhật ứng dụng tự động, không bảo đảm gói sẽ được các bộ lọc bảo mật của OS tin cậy nếu chưa ký.

## 9. Lỗi thường gặp khi chuyển từ hướng dẫn Java 14 sang hiện tại

| Lỗi / hiểu nhầm | Vì sao sai? | Cách làm hiện hành |
| --- | --- | --- |
| Vẫn ghi `jdk.incubator.jpackage` như dependency hoặc bước build mới | Tên giai đoạn ươm tạo Java 14/15 | Dùng `jpackage` của **JDK 16+**, kiểm tra tài liệu của JDK hiện tại |
| Nghĩ công cụ vẫn “experimental” ở Java 17+ | JEP 392 đã chuẩn hóa từ Java 16 | Coi đây là công cụ JDK chính thức, song vẫn kiểm thử từng bản JDK |
| Nghĩ phải thêm `requires jdk.jpackage;` vào `module-info.java` | Công cụ build không phải dependency nghiệp vụ runtime | Khai báo chỉ những module ứng dụng cần khi chạy |
| Gọi `jpackage` trực tiếp trên file `.java` | Công cụ đóng gói artifact đã biên dịch | `javac`/build trước, rồi `jpackage` |
| Viết `--main-jar input/app.jar` đồng thời `--input input` | `--main-jar` thường tương đối với thư mục input | Dùng `--main-jar app.jar` |
| Dùng đồng thời `--main-jar` và `--module` | Hai đường dẫn xác định main entry loại trừ nhau | Chọn classpath hoặc JPMS |
| Dùng `--win-console` trên Linux/macOS | Đây là cờ chỉ có trên Windows | Bỏ cờ trên OS khác |
| Tạo `--type exe` trên Linux và mong có installer Windows | `jpackage` không hỗ trợ cross-platform packaging | Build trên OS đích |
| Nghĩ `--type app-image` sinh installer cài đặt | App image là thư mục/bundle tự chứa | Dùng `exe`, `deb`, `pkg`... khi cần installer |
| Thiếu dependency JAR hoặc resource trong `--input` | Launcher có thể chạy nhưng lỗi `ClassNotFoundException`/tệp thiếu | Đóng đủ tài nguyên và kiểm tra launcher |
| Runtime image thiếu module JVM cần dùng | Ứng dụng lỗi khi chạy dù JAR chạy tốt bằng JDK đầy đủ | Kiểm tra `jlink`, `--add-modules`, `ServiceLoader`, reflection |
| Gói chương trình console Windows nhưng không thấy stdout | Launcher GUI mặc định có thể không hiện console | Dùng `--win-console` khi cần CLI/console |
| Chỉ kiểm tra tạo installer thành công | Chưa chứng minh app khởi động hoặc có quyền hoạt động | Chạy thử `app-image` và quy trình cài/gỡ/nâng cấp |
| Cho rằng đóng kèm runtime không cần cập nhật nữa | Runtime trong gói cũng có thể có lỗ hổng | Rebuild và phân phối bản mới khi JDK được vá |

## 10. Bài tập có đáp án

**Câu 1.** `jpackage` bắt đầu là công cụ incubating ở Java nào và chính thức từ Java nào?  
**Đáp án:** Incubating từ **Java 14** (JEP 343), tiếp tục trong 15; chính thức/production-ready từ **Java 16** (JEP 392).

**Câu 2.** Tên module `jpackage` đã thay đổi như thế nào?  
**Đáp án:** Từ `jdk.incubator.jpackage` trong giai đoạn incubator sang `jdk.jpackage` ở Java 16. Tên lệnh CLI vẫn là `jpackage`.

**Câu 3.** Cần viết `requires jdk.jpackage;` trong mọi ứng dụng modular trước khi đóng gói không?  
**Đáp án:** Không. `jpackage` là công cụ build; `module-info.java` mô tả dependency runtime thật của ứng dụng.

**Câu 4.** `--type app-image` có giống `--type exe` không?  
**Đáp án:** Không. `app-image` tạo thư mục/bundle tự chứa; `exe` tạo installer Windows theo yêu cầu OS và các tool native cần thiết.

**Câu 5.** Dùng `jpackage` trên Linux để tạo file `msi` Windows được không?  
**Đáp án:** Không, `jpackage` không hỗ trợ tạo gói xuyên hệ điều hành. Dùng môi trường build Windows.

**Câu 6.** Nếu `--input input`, JAR nằm ở `input/packaging-demo.jar`, tham số `--main-jar` nên ghi gì?  
**Đáp án:** `--main-jar packaging-demo.jar`, tương đối với thư mục `input`.

**Câu 7.** Với ứng dụng JPMS, dùng bộ tham số nào để chỉ định main class?  
**Đáp án:** `--module-path mods --module com.example.pkgdemo/com.example.pkgdemo.Main`, không kết hợp `--main-jar`.

**Câu 8.** Nếu không chỉ định `--runtime-image`, `jpackage` xử lý Java runtime thế nào?  
**Đáp án:** Công cụ thường gọi `jlink` để tạo runtime image từ các module được chọn/giải quyết, sau đó đóng kèm ứng dụng.

**Câu 9.** Tại sao nên chạy thử app image trước khi tạo installer?  
**Đáp án:** Vì có thể phát hiện sớm lỗi launcher, thiếu class/module, cấu hình JVM, quyền file và tài nguyên không được đóng gói.

**Câu 10.** Đóng gói kèm runtime có nghĩa là không cần quan tâm bản vá bảo mật Java nữa?  
**Đáp án:** Không. Runtime đóng kèm vẫn cần được cập nhật; ứng dụng phải được rebuild/repackage khi cần bản vá.

## 11. Ghi nhớ và nguồn tài liệu chính thức

**Kết luận:** Từ một công cụ **ươm tạo trong Java 14**, `jpackage` đã trở thành **công cụ JDK chính thức từ Java 16**. Khi thực hành ngày nay, hãy tập trung vào workflow đã ổn định: **build JAR/module → `jpackage --type app-image` → kiểm thử launcher → đóng native installer trên OS đích nếu cần**.

- Không dùng tên module ươm tạo cũ cho dự án mới.
- Không nhầm công cụ `jpackage` với module nghiệp vụ của ứng dụng.
- Phân biệt `app-image` với installer và giới hạn cross-platform.
- Giữ runtime, thư viện và tài nguyên cập nhật; kiểm chứng package thực tế trên từng OS.

Nguồn chính thức:

- [OpenJDK JEP 343 — Packaging Tool (Incubator)](https://openjdk.org/jeps/343): lịch sử công cụ ươm tạo được giới thiệu trong JDK 14.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): đưa công cụ thành tính năng production-ready trong JDK 16.
- [Oracle JDK 16 Release Notes](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html): xác nhận từ incubator Java 14/15 sang công cụ chính thức và thay tên module.
- [Oracle Java SE 21 — The `jpackage` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html): các cờ `--type`, `--input`, `--main-jar`, `--module`, `--runtime-image`, `--app-image` và tùy chọn OS.
- [Oracle Java SE 21 — Packaging Overview](https://docs.oracle.com/en/java/javase/21/jpackage/packaging-overview.html): xây app image, tạo installer và Java runtime đi kèm.
