# Liên kết loại tệp với ứng dụng khi tạo gói cài đặt Java bằng jpackage

## Mục tiêu bài học

Một ứng dụng desktop thường không chỉ được mở từ menu hoặc biểu tượng. Người dùng còn mong muốn **nhấp đúp vào một loại tệp** — ví dụ tài liệu có phần mở rộng `.jotdemo` — để hệ điều hành khởi động ứng dụng có khả năng đọc loại tệp đó. Cơ chế này gọi là **file association**: liên kết **loại tệp** với một **ứng dụng/launcher** ở cấp hệ điều hành.

Với Java hiện đại, công cụ `jpackage` hỗ trợ khai báo các liên kết loại tệp bằng tùy chọn **`--file-associations`** khi tạo **gói cài đặt ứng dụng**. Điều cần phân biệt:

- **Đóng gói và đăng ký:** `jpackage` có thể tạo metadata giúp bộ cài đặt đăng ký ứng dụng xử lý loại tệp.
- **Chọn ứng dụng mặc định:** việc hệ điều hành có tự dùng ứng dụng của bạn mỗi khi nhấp đúp không phải quyền quyết định tuyệt đối của `jpackage`; các ứng dụng khác và lựa chọn của người dùng vẫn có thể chi phối.
- **Xử lý nội dung:** đăng ký thành công không biến ứng dụng thành một trình đọc tệp tự động. Ứng dụng Java phải tự nhận đường dẫn và xử lý dữ liệu an toàn.

Sau bài này, bạn sẽ tạo file `.properties` mô tả loại tệp, tích hợp với `jpackage` cho Windows/macOS/Linux, xây dựng một chương trình Java 17+ nhận đường dẫn tệp, chạy test độc lập và kiểm tra hành vi thực sau khi cài đặt.

**Tính hiện hành:** `jpackage` là công cụ phát hành chính thức từ Java 16, được hỗ trợ trong Java 17 và các bản hiện đại. Hướng dẫn này dùng **JDK 17 trở lên**, không dùng những công cụ đóng gói legacy của các JDK cũ, không yêu cầu preview hay incubator.

## 1. File association là gì?

Giả sử bạn phát triển ứng dụng **JotDemo**, dùng để mở các tài liệu văn bản UTF-8 có phần mở rộng **`.jotdemo`**.

Nếu chưa có file association:

1. Người dùng tìm tệp `sample.jotdemo`.
2. Hệ điều hành có thể không biết ứng dụng nào xử lý; người dùng phải chọn `Open with` hoặc mở ứng dụng rồi chọn tệp bằng một chức năng riêng.

Nếu đã có liên kết và hệ điều hành lựa chọn JotDemo làm trình xử lý:

1. Người dùng mở `sample.jotdemo` trong trình quản lý tệp.
2. Hệ điều hành tìm ứng dụng đã đăng ký hoặc được chọn làm mặc định cho loại tệp đó.
3. Hệ điều hành khởi động **launcher của JotDemo** và cung cấp thông tin về tệp được mở theo cơ chế của nền tảng.
4. Ứng dụng Java nhận đường dẫn/tài nguyên, kiểm tra và đọc dữ liệu, rồi hiển thị nội dung.

```text
Người dùng mở sample.jotdemo
                |
                v
Hệ điều hành xác định loại tệp
  (extension / MIME / metadata)
                |
                v
Tra ứng dụng xử lý đã đăng ký
  + lựa chọn mặc định của người dùng
                |
                v
Launcher từ bộ cài JotDemo
                |
                v
main(String[] args)
  nhận đường dẫn tệp được gửi tới
                |
                v
Kiểm tra, đọc và xử lý tài liệu
```

**Lưu ý:** File association không phải là chức năng nhận diện nội dung bằng phép màu. Hệ điều hành có thể dựa vào extension, MIME hoặc metadata riêng; còn ứng dụng phải kiểm tra tệp thực sự có đúng định dạng, quyền và giới hạn tài nguyên. Đổi tên `virus.bin` thành `notes.jotdemo` không tự làm nội dung trở nên an toàn.

## 2. Bốn thành phần cần phân biệt

| Thành phần | Là gì? | Ai chịu trách nhiệm? |
| --- | --- | --- |
| **Phần mở rộng** (*extension*) | Hậu tố tên tệp, ví dụ `.jotdemo` | Người tạo định dạng và hệ điều hành |
| **MIME type** | Nhãn chỉ kiểu dữ liệu, ví dụ `application/x-jotdemo` | Đặc tả định dạng và cơ chế hệ điều hành |
| **Đăng ký association** | Metadata nói rằng ứng dụng có khả năng xử lý loại tệp | Gói cài đặt/installer và hệ điều hành |
| **Handler của ứng dụng** | Mã nhận tệp được mở và thực hiện đọc/hiển thị | Code Java do bạn viết |

Điểm quyết định: **`jpackage` chỉ giúp phần đăng ký ứng dụng ở tầng cài đặt**, không viết thay logic `main`, không biến một JAR thành trình parse tài liệu và không giành quyền thay đổi ứng dụng mặc định của người dùng trong mọi trường hợp.

Ngoài ra, một ứng dụng có thể đăng ký nhiều loại tệp, và một loại tệp có thể có nhiều ứng dụng xử lý. Khi có cạnh tranh, cơ chế chọn mặc định hoặc hộp thoại `Open with` tùy thuộc OS và thiết lập người dùng.

## 3. Tùy chọn chính: --file-associations

Cú pháp khái quát:

```bash
jpackage ... --file-associations path/to/type.properties
```

`--file-associations` nhận **đường dẫn tới một file Java Properties** chứa các cặp `key=value` để mô tả **một liên kết loại tệp**. Tài liệu `jpackage` hiện hành cho phép các khóa:

| Khóa properties | Vai trò | Ví dụ |
| --- | --- | --- |
| `extension` | Phần mở rộng tệp ứng dụng xử lý | `jotdemo` |
| `mime-type` | MIME type của tài liệu | `application/x-jotdemo` |
| `description` | Mô tả ngắn cho liên kết | `JotDemo text document` |
| `icon` | Icon cho loại tệp | `document.ico` hoặc tài nguyên tương ứng OS |

Một association phải có **ít nhất một trong hai khóa `extension` hoặc `mime-type`**. Có thể cung cấp cả hai. `description` và `icon` là tùy chọn.

**Định dạng đúng:** Ví dụ extension được viết là `extension=jotdemo` **không cần dấu chấm đầu** trong file properties. Tệp trên hệ thống thực tế là `sample.jotdemo`. Đây là cách Oracle dùng trong ví dụ chính thức (`extension=js`, `extension=groovy`).

**Icon:** Nếu khai báo `icon=...`, tài nguyên icon phải nằm trong thư mục `--input` tại thời điểm đóng gói theo hướng dẫn Oracle. Chọn định dạng icon thích hợp với nền tảng đang xây gói. Nếu chưa có icon hợp lệ, có thể **bỏ hẳn khóa này** để dùng icon mặc định, tránh gây lỗi build vì đường dẫn sai.

**Một association một file properties:** Muốn thêm loại thứ hai, tạo một file khác và truyền thêm **một lần `--file-associations`**. Đừng nhét nhiều loại tệp tùy ý vào một khóa `extension` rồi kỳ vọng nó tự hoạt động như danh sách.

## 4. Ví dụ file properties đầy đủ

Tạo cấu trúc dự án:

```text
jotdemo-project/
  src/
    lesson/
      assoc/
        JotDemo.java
  associations/
    jotdemo.properties
  classes/     (do javac tạo)
  input/       (chứa jotdemo.jar)
  dist/        (chứa gói cài đặt)
  sample.jotdemo
```

Nội dung file **`associations/jotdemo.properties`**:

```properties
extension=jotdemo
mime-type=application/x-jotdemo
description=JotDemo text document
```

Giải thích:

- `jotdemo` là phần mở rộng riêng của ví dụ; không dùng các loại phổ biến như `txt`, `pdf`, `png` để tránh vô tình tranh quyền mở tài liệu với phần mềm đã có.
- `application/x-jotdemo` là một tên MIME **dùng cho ví dụ**, không phải loại MIME đã được đăng ký chuẩn toàn cầu. Khi phát hành sản phẩm thật, chọn định danh MIME phù hợp với định dạng và chính sách đăng ký/namespace của tổ chức.
- `description` để hệ điều hành và công cụ đóng gói có thể hiển thị mô tả thân thiện.
- Không có `icon`; ứng dụng sẽ dùng tài nguyên mặc định, tránh việc cần chuẩn bị file hình riêng trên từng OS.

Bạn có thể lưu association properties **ngoài thư mục `input`**, rồi truyền **đường dẫn tương đối hoặc tuyệt đối** bằng `--file-associations`. `--input` là nơi chứa payload của ứng dụng; file properties là cấu hình cho công cụ đóng gói.

Nếu ứng dụng thật xử lý thêm `.jotnote` với MIME khác, tạo file `associations/jotnote.properties` riêng rồi thêm lần thứ hai:

```bash
--file-associations associations/jotdemo.properties --file-associations associations/jotnote.properties
```

Đoạn trên là **phần tùy chọn của lệnh `jpackage`**, không phải lệnh shell độc lập. Nội dung `jotnote.properties` phải mô tả loại tệp thứ hai bằng các khóa tương ứng, không được giả định phần này tự tạo.

## 5. Hai giai đoạn: tạo bộ ứng dụng và đăng ký với hệ điều hành

Đây là chỗ thường nhầm nhất.

### Giai đoạn A — Build artifact

Công cụ `jpackage` lấy ứng dụng Java đã biên dịch/đóng JAR, tạo Java runtime image và launcher phù hợp hệ điều hành. Bạn có thể dùng `--type app-image` để kiểm tra một bundle **chưa được cài đặt vào hệ thống**.

### Giai đoạn B — Install/register

Khi tạo **gói cài đặt** (`msi`/`exe` trên Windows, `dmg`/`pkg` trên macOS, `deb`/`rpm` trên Linux) và người dùng cài/đăng ký ứng dụng, metadata association mới có cơ hội được hệ điều hành nhận diện. Oracle xếp `--file-associations` vào nhóm **options for creating the application package**, và tài liệu nói về việc tạo association **khi ứng dụng được cài đặt**.

Vì vậy:

- **`jpackage --type app-image` chạy thành công** không đồng nghĩa `sample.jotdemo` đã tự động mở bằng JotDemo khi nhấp đúp.
- **Installer build thành công** cũng chưa chứng minh ứng dụng đã được cài hoặc đã trở thành app mặc định.
- Cần **cài gói lên hệ điều hành đích**, kiểm tra handler đã được đăng ký và thử hành động `Open with` hoặc nhấp đúp.
- Nếu OS ưu tiên ứng dụng khác, người dùng có thể cần **chọn JotDemo làm ứng dụng mặc định** cho loại tệp đó.

**Không nên tự ý ghi đè file association phổ biến** trong installer chỉ để bảo đảm chương trình được chọn mặc định. Một gói cài đặt tốt cần tôn trọng lựa chọn của người dùng và chính sách hệ điều hành.

## 6. Mã Java 17+ hoàn chỉnh: handler nhận tệp được mở

Để xác minh association, chương trình phải **thực sự nhận và đọc tệp**. Ví dụ dưới đây có hai chế độ:

- `--cli path`: chạy kiểm tra từ terminal; in kết quả ra stdout ổn định.
- `path`: đường dẫn nhận được khi người dùng mở tệp qua association; hiển thị một hộp thoại Swing để bạn dễ nhận biết ngay cả khi launcher không có console. Nếu đang chạy trong môi trường headless, chương trình in stdout thay vì mở GUI.

Ứng dụng ví dụ đọc **dòng đầu của tệp UTF-8**; chỉ cho phép extension `.jotdemo` và giới hạn kích thước tệp ở **64 KiB**. Những kiểm tra này làm rõ rằng file association không tự kiểm tra nội dung và quyền truy cập.

Tạo file **`src/lesson/assoc/JotDemo.java`**:

```java
package lesson.assoc;

import java.awt.GraphicsEnvironment;
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import javax.swing.JOptionPane;

public final class JotDemo {
    private JotDemo() {
    }

    public static void main(String[] args) throws IOException {
        boolean cli = args.length == 2
                && "--cli".equals(args[0]);

        if ((!cli && args.length != 1)
                || (cli && args.length != 2)) {
            System.err.println(
                    "Usage: JotDemo [--cli] <document.jotdemo>");
            return;
        }

        Path file = Path.of(args[cli ? 1 : 0])
                .toAbsolutePath()
                .normalize();

        String name = file.getFileName().toString();
        if (!name.toLowerCase(Locale.ROOT)
                .endsWith(".jotdemo")) {
            throw new IllegalArgumentException(
                    "Expected a .jotdemo file: " + name);
        }

        if (!Files.isRegularFile(file)) {
            throw new IllegalArgumentException(
                    "Not a regular file: " + file);
        }

        if (Files.size(file) > 64 * 1024) {
            throw new IllegalArgumentException(
                    "File exceeds 64 KiB: " + name);
        }

        String first;
        try (BufferedReader reader =
                Files.newBufferedReader(
                        file, StandardCharsets.UTF_8)) {
            first = reader.readLine();
        }

        String summary = "file=" + name
                + "\nfirst="
                + (first == null ? "<empty>" : first);

        if (cli || GraphicsEnvironment.isHeadless()) {
            System.out.println(summary);
        } else {
            JOptionPane.showMessageDialog(
                    null,
                    summary,
                    "JotDemo",
                    JOptionPane.INFORMATION_MESSAGE);
        }
    }
}
```

### Phân tích code

1. `args` chứa **các tham số được truyền tới ứng dụng**. Trong mô hình launcher file association, hệ điều hành/launcher thường cung cấp đường dẫn tệp được mở. Ví dụ chỉ hỗ trợ một đường dẫn mỗi lượt; ứng dụng thực cần thiết kế cách xử lý nhiều tệp/URI nếu nền tảng yêu cầu.
2. `--cli` là **chế độ test do chính ví dụ định nghĩa**, không phải một tham số có sẵn của `jpackage`.
3. `Path.of(...)` chuyển chuỗi argument thành Path. Dùng `toAbsolutePath().normalize()` giúp biểu diễn đường dẫn rõ ràng, **không phải** xác thực quyền hay chống mọi cách vượt đường dẫn.
4. Code kiểm tra extension và tồn tại của file. Tên file đúng **không chứng minh nội dung hợp lệ**; ứng dụng thực cần một parser và schema validation phù hợp với định dạng riêng.
5. `Files.size(file)` giúp tránh vô tình đọc file quá lớn trong demo. Đây chỉ là kiểm tra sơ bộ; trong môi trường không tin cậy, cần chống race condition và áp dụng giới hạn khi thực sự đọc.
6. `BufferedReader` đọc một dòng và đóng file bằng `try-with-resources`, không tải toàn bộ file vào RAM.
7. Chế độ CLI in hai dòng có thể kiểm tra chính xác; chế độ mở qua association hiển thị dialog vì launcher GUI thông thường không có một console nhìn thấy được.
8. `JOptionPane` thuộc module `java.desktop`. Nếu bạn tự tạo runtime tối giản bằng `jlink`, phải bảo đảm runtime image chứa những module mà ứng dụng cần. Với jpackage mặc định, hãy kiểm tra ứng dụng được đóng gói chạy thực tế thay vì tự suy đoán module nào đã được chọn.

**Lưu ý về bảo mật:** Vì file path đến từ hệ điều hành hoặc người dùng, không chạy command shell từ tên tệp, không dùng nội dung file làm mã thực thi, không ghi ra toàn bộ dữ liệu nhạy cảm khi debug. Demo này chỉ hiển thị tên tệp và dòng đầu; phần hiển thị dữ liệu thực tế cần phù hợp chính sách ứng dụng.

## 7. Biên dịch và kiểm thử ứng dụng trước khi đóng gói

Từ thư mục gốc dự án, tạo thư mục output.

**Linux/macOS:**

```bash
mkdir -p classes input associations dist
```

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force -Path classes,input,associations,dist | Out-Null
```

Lưu file Java và file `associations/jotdemo.properties` đúng như ở trên bằng editor. Sau đó biên dịch:

```bash
javac --release 17 -encoding UTF-8 -d classes src/lesson/assoc/JotDemo.java
```

Tham số `--release 17` đảm bảo mã và API được biên dịch theo mức tương thích Java 17. `-d classes` đưa `lesson/assoc/JotDemo.class` vào thư mục output theo package.

Tạo JAR có manifest `Main-Class`:

```bash
jar --create --file input/jotdemo.jar --main-class lesson.assoc.JotDemo -C classes .
```

Kiểm tra JAR:

```bash
jar --list --file input/jotdemo.jar
```

Danh sách sẽ chứa `lesson/assoc/JotDemo.class` cùng manifest và các metadata archive, thứ tự file không phải contract cố định.

### Chuẩn bị tệp ví dụ

**Linux/macOS:**

```bash
printf 'Hello from JotDemo\n' > sample.jotdemo
```

**Windows PowerShell:**

```powershell
Set-Content -Path sample.jotdemo -Value 'Hello from JotDemo' -Encoding ascii
```

`-Encoding ascii` ở đây hợp lệ vì nội dung demo chỉ chứa các ký tự ASCII, và ASCII đồng thời là tập con hợp lệ của UTF-8. Cách này tránh BOM không mong đợi trong một số phiên bản PowerShell. Với tài liệu tiếng Việt thật, hãy tạo UTF-8 không BOM theo yêu cầu định dạng thay vì ép mọi nội dung sang ASCII.

Chạy test:

```bash
java -jar input/jotdemo.jar --cli sample.jotdemo
```

**Stdout mong đợi chính xác:**

```text
file=sample.jotdemo
first=Hello from JotDemo
```

Đây là kết quả được xác định bởi nội dung `sample.jotdemo` của ví dụ, không phụ thuộc việc file association đã được cài đặt hay chưa. Nếu lệnh không cho đúng hai dòng, hãy sửa **Java app/JAR/file test** trước khi đổ lỗi cho `jpackage` hoặc hệ điều hành.

### Kiểm tra thêm các ca biên

- `java -jar input/jotdemo.jar --cli missing.jotdemo`: phải thất bại vì không phải file thực.
- `java -jar input/jotdemo.jar --cli sample.txt`: phải thất bại ở phần extension.
- Một file `.jotdemo` rỗng: chương trình in `first=<empty>`.
- Tệp `.jotdemo` lớn hơn 64 KiB: chương trình ném `IllegalArgumentException`.
- Tên file có dấu cách như `"my notes.jotdemo"`: phải truyền **một argument được quote đúng** khi chạy từ shell; file manager thường truyền đường dẫn theo cơ chế riêng của nền tảng.
- Nếu user chọn một tệp không phải UTF-8, việc đọc có thể thất bại. Ứng dụng thật cần xác định encoding và thông báo phù hợp thay vì xem mọi dữ liệu là hợp lệ.

**Đừng dùng nội dung stdout của CLI làm bằng chứng association của OS đã được đăng ký.** Nó chỉ kiểm tra handler xử lý tệp.

## 8. Tạo app-image để kiểm tra launcher — chưa phải file association đã đăng ký

Trước khi build installer, có thể tạo image để kiểm tra chương trình và các module phụ thuộc:

```bash
jpackage --type app-image --name JotDemo --input input --main-jar jotdemo.jar --dest image-out
```

Thư mục `image-out` sẽ chứa bundle phù hợp hệ điều hành, với launcher, file ứng dụng và runtime cần thiết. Dùng launcher được tạo để xác minh ứng dụng có thể chạy trên Java runtime đi kèm.

Ví dụ kiểm tra launcher trên Linux, đường dẫn thường có dạng:

```bash
./image-out/JotDemo/bin/JotDemo --cli sample.jotdemo
```

Trên macOS, launcher thường nằm bên trong `JotDemo.app/Contents/MacOS/`; trên Windows, là `JotDemo.exe` trong image. Cấu trúc có thể thay đổi theo bản JDK, nên hãy kiểm tra artifact thực thay vì hardcode đường dẫn trong hệ thống triển khai.

**Quan trọng:** Ở bước `app-image`, bạn chỉ kiểm tra rằng **launcher mở được chương trình**. Không tuyên bố double-click `sample.jotdemo` sẽ tự sử dụng JotDemo trước khi installer được cài và hệ điều hành nhận association.

Nếu image-out đã tồn tại từ lần build trước, hãy dùng một thư mục output mới hoặc xóa nội dung cũ **có chủ đích**; đừng vô tình ghi chồng artifact chưa kiểm thử.

## 9. Tạo gói cài đặt với --file-associations

Khi ứng dụng và properties đã sẵn sàng, tạo installer theo nền tảng. **Mỗi máy chỉ dùng lệnh phù hợp với hệ điều hành của nó.**

### Windows

```powershell
jpackage --type msi --name JotDemo --input input --main-jar jotdemo.jar --file-associations associations/jotdemo.properties --dest dist
```

Tùy phiên bản JDK, Windows cần **WiX Toolset** và các công cụ build installer được hỗ trợ. Có thể dùng `--type exe` thay `--type msi` nếu muốn tạo loại installer khác. `--file-associations` vẫn là **đường dẫn tới properties file**, không phải phần mở rộng hay tên class.

Không cần `--win-console` cho ví dụ mở file qua giao diện, vì app có `JOptionPane`. Nếu phát hành một công cụ dòng lệnh cần console, Windows có tùy chọn `--win-console` riêng cho launcher; lựa chọn này **không phải** điều kiện để tạo file association.

### macOS

```bash
jpackage --type dmg --name JotDemo --input input --main-jar jotdemo.jar --file-associations associations/jotdemo.properties --dest dist
```

`--type dmg` tạo gói phân phối phù hợp macOS. Người dùng vẫn phải cài/đăng ký ứng dụng theo cơ chế của hệ điều hành và có thể cần chọn JotDemo trong `Open With`. Khi phân phối rộng rãi, các yêu cầu ký ứng dụng và notarization là một bước riêng, không tự được đáp ứng chỉ nhờ `--file-associations`.

### Linux (Debian/Ubuntu)

```bash
jpackage --type deb --name JotDemo --input input --main-jar jotdemo.jar --file-associations associations/jotdemo.properties --dest dist
```

Trên một distro RPM phù hợp, có thể chọn `--type rpm` thay cho `deb`. Các trình đóng gói hệ điều hành có dependencies riêng: ví dụ Oracle hướng dẫn Debian/Ubuntu có thể cần công cụ `fakeroot`; RPM cần các công cụ build RPM.

Với Linux, association thường tham gia cơ chế MIME/desktop entry của desktop environment. **Đừng kết luận tất cả distro, desktop environment hay phiên đăng nhập đều sẽ tự đặt JotDemo làm mặc định** chỉ vì tạo và cài gói thành công.

### Phần nào thực sự xảy ra khi build?

1. `--input input` chứa payload đã được biên dịch (`jotdemo.jar`).
2. `--main-jar jotdemo.jar` chỉ định JAR ứng dụng có manifest `Main-Class`.
3. `--file-associations associations/jotdemo.properties` thêm mô tả handler cho loại tệp.
4. `--type ...` chọn định dạng bộ cài phù hợp OS.
5. `--dest dist` là nơi đặt output installer, **không phải** thư mục chứa file của người dùng được mở.

Với một file association thứ hai, thêm một option `--file-associations` khác chỉ đến **một file properties khác**, theo quy tắc Oracle. Không được dùng `--arguments sample.jotdemo` để mô phỏng file association: `--arguments` là **giá trị mặc định cho ứng dụng khi không có argument** và không đăng ký một định dạng tệp với OS.

## 10. Kiểm thử sau khi cài đặt: ba tầng QA khác nhau

Để kết luận “file association hoạt động”, cần kiểm tra theo thứ tự.

### Tầng 1 — Java handler

`java -jar input/jotdemo.jar --cli sample.jotdemo` phải trả đúng:

```text
file=sample.jotdemo
first=Hello from JotDemo
```

Nếu thất bại, hãy điều tra code xử lý đường dẫn/encoding. Đây chưa phải test installer.

### Tầng 2 — Launcher/application image

Chạy launcher từ app image cùng đối số `--cli sample.jotdemo`. Nếu không chạy, hãy kiểm tra runtime đi kèm, các module, dependencies và cấu hình main class. Một launcher hoạt động **không** chứng minh association đã được đăng ký.

### Tầng 3 — Installer và đăng ký với OS

Cài gói trên một máy hoặc VM thử nghiệm phù hợp OS, rồi thử:

1. Mở trình quản lý tệp và chọn `sample.jotdemo`.
2. Kiểm tra ứng dụng JotDemo **có xuất hiện trong danh sách `Open with`** không.
3. Chọn JotDemo làm handler (hoặc mặc định, nếu bạn muốn) khi OS cho phép.
4. Mở lại `sample.jotdemo` bằng thao tác của người dùng; ứng dụng phải hiển thị hộp thoại `JotDemo` với nội dung `file=...` và `first=...`.
5. Đổi tên hoặc tạo file có dấu cách trong đường dẫn, ví dụ `my notes.jotdemo`, và kiểm tra ứng dụng vẫn nhận **một đường dẫn đúng**.
6. Thử gỡ cài đặt; xác nhận trạng thái association/handler được hệ điều hành cập nhật phù hợp, không để lại một launcher trỏ đến nơi đã bị gỡ.

**Không dùng “đã xuất hiện icon” như bằng chứng đầy đủ.** Icon, registry/MIME metadata, lựa chọn mặc định và việc ứng dụng thực sự đọc tệp là những tầng khác nhau.

### Dấu hiệu kiểm tra theo hệ điều hành

| OS | Nơi thường kiểm tra | Lưu ý |
| --- | --- | --- |
| Windows | `Open with`, Settings → Apps → Default apps | Đăng ký handler không luôn thay đổi app mặc định đã được người dùng chọn |
| macOS | Finder → Get Info → Open with | Có thể cần chọn handler và `Change All` theo quyết định của người dùng |
| Linux | Trình quản lý tệp, MIME applications/default apps | Tùy desktop; có thể dùng `xdg-mime` để kiểm tra mapping nếu công cụ có sẵn |

Ví dụ tùy chọn trên Linux desktop có XDG utilities:

```bash
xdg-mime query filetype sample.jotdemo
xdg-mime query default application/x-jotdemo
```

Kết quả tùy hệ thống và cài đặt MIME, không có stdout cố định cho hai lệnh. `xdg-mime` không phải yêu cầu bắt buộc của Java/JDK, và kết quả `default` có thể khác giữa người dùng hoặc desktop environment.

## 11. Những tình huống xung đột association

### Một extension được nhiều ứng dụng đăng ký

Nhiều chương trình có thể xử lý cùng `.txt`, `.json`, `.csv` hoặc `.md`. Cài JotDemo không có nghĩa nó phải trở thành ứng dụng mặc định của các extension phổ biến đó. OS có thể giữ lựa chọn hiện tại, hiển thị `Open with` hoặc cho người dùng đổi mặc định.

**Khuyến nghị:** Với định dạng mới, dùng extension riêng. Với định dạng có sẵn, cung cấp khả năng mở file qua menu/`Open with` mà không ép thay đổi mặc định trái ý người dùng.

### MIME type không khớp extension

Nếu `mime-type` chỉ một định dạng nhưng `extension` lại đại diện định dạng khác, desktop có thể xử lý khác kỳ vọng. Hãy thống nhất tài liệu định dạng, metadata và nội dung thực mà chương trình hỗ trợ; kiểm tra trên OS đích.

### Ứng dụng không nhận argument

Nếu Java `main(String[] args)` bỏ qua mọi argument, OS có khởi động launcher thành công thì người dùng cũng không thấy file được mở. File association chỉ là **khai báo khả năng xử lý**, không tạo chức năng mở tài liệu tự động.

### Đường dẫn có space và ký tự Unicode

Đừng tách đường dẫn bằng `split(" ")` hay ghép thành một shell command không escape. Hệ điều hành/launcher cung cấp argument theo cơ chế của mình; app nên dùng `Path.of(args[index])` trên đúng **một argument** được nhận. Test cả tên có space và Unicode trên OS thật.

### Double-click khác chạy trong terminal

Ứng dụng Java console in ra `System.out` có thể không có cửa sổ console khi được mở bằng file manager. Do đó ví dụ có **hộp thoại Swing** ở chế độ mở file. Ứng dụng thật thường mở cửa sổ GUI, tài liệu hoặc editor thay vì chỉ ghi log ra stdout.

### Association không phải chữ ký số

Việc ứng dụng có file association không chứng minh installer đã được ký, dữ liệu đầu vào đáng tin, hoặc app có đủ quyền mở mọi file. Đó là các vấn đề độc lập.

## 12. Các lỗi thường gặp khi dùng jpackage

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Viết `--file-associations jotdemo` | Công cụ mong **đường dẫn properties file** | Dùng `associations/jotdemo.properties` |
| Viết `extension=.jotdemo` | Khác cú pháp ví dụ chính thức, có thể không được OS xử lý như dự kiến | Viết `extension=jotdemo` |
| Bỏ cả `mime-type` lẫn `extension` | Association thiếu thông tin nhận diện bắt buộc | Có ít nhất một khóa, tốt nhất rõ ràng |
| Trỏ `icon` đến file không tồn tại | Build có thể thất bại hoặc icon không đúng | Bỏ icon hoặc chuẩn bị tài nguyên đúng |
| Ghi nhiều loại vào một properties mà không xác định quy tắc | Có thể không tạo các association mong muốn | Mỗi loại một properties, lặp option |
| Chỉ dùng `--type app-image` | Chưa có bước installer đăng ký với OS | Tạo/cài gói native và test |
| Build installer rồi không cài | Chưa chứng minh registry/MIME đã cập nhật | Cài trên máy thử phù hợp |
| Mong installer luôn chiếm mặc định | OS/user policy có thể giữ app khác | Tôn trọng default, test `Open with` |
| Không xử lý `args` ở Java main | App khởi động nhưng không đọc file | Nhận đường dẫn, kiểm tra, mở tệp |
| Đọc mọi file tùy ý không kiểm tra | Có rủi ro dữ liệu lớn, encoding sai, nội dung độc hại | Validation, giới hạn size, quyền |
| Gói cho OS khác bằng cùng một jpackage invocation | Công cụ không hỗ trợ cross-platform package trực tiếp | Build trên OS đích |
| Quên `java.desktop` trong custom runtime | GUI Swing có thể không chạy | Đảm bảo runtime chứa module cần thiết |
| Cài nhiều phiên bản có cùng identifier | Có thể xung đột handler và nâng cấp | Quản lý version, ID gói và uninstall |
| Thử ngay sau khi đổi default mà không xác minh trạng thái OS | Có thể chưa áp dụng hoặc cache cần cập nhật | Kiểm tra mapping và mở lại một tệp test |

Ngoài ra, `jpackage` có thể đóng JAR và runtime thành gói, nhưng **không biên dịch thay code Java chưa được build**. Phải chạy `javac`/build tool trước để tạo JAR hợp lệ. File association cũng không cần và không hàm ý rằng ứng dụng được biên dịch AOT sang machine code.

## 13. Bảo mật, quyền riêng tư và UX

### Chỉ mở những định dạng app hiểu

Phần mở rộng và MIME không thay thế xác minh nội dung. Ví dụ đang giới hạn `.jotdemo` và 64 KiB. Ứng dụng thực nên kiểm tra magic bytes/schema khi có, encoding, quyền, symbolic links và trường hợp nội dung lỗi theo threat model phù hợp.

### Không dùng đường dẫn như lệnh shell

Nếu mở tệp thông qua `ProcessBuilder`, mọi tham số phải được đưa thành phần tử argument riêng và không đưa dữ liệu từ đường dẫn vào một chuỗi lệnh tùy ý. Trong bài, ứng dụng chỉ đọc qua `java.nio.file.Files` nên không cần shell.

### Đừng ghi đè lựa chọn mặc định

Kể cả khi installer có thể đề nghị association, việc thay đổi app mặc định ảnh hưởng quy trình người dùng. Hãy thông báo đúng loại tệp mà phần mềm xử lý và cho phép người dùng lựa chọn theo UI/OS.

### Chạy kiểm thử trên phiên bản và kiến trúc đích

Windows MSI/EXE, macOS DMG/PKG và Linux DEB/RPM có cơ chế đăng ký ứng dụng khác nhau. Chọn đúng OS/architecture, chính sách ký/notarization, dependencies và quyền cài đặt. Không suy ra file association hoạt động trên cả ba OS chỉ vì nó hoạt động trên một máy.

### Gỡ cài đặt và nâng cấp

Một ứng dụng đã gỡ có thể khiến file type association hoặc default handler cần được OS cập nhật lại. Kiểm thử cài mới, nâng cấp, gỡ cài đặt, cài song song và xung đột tên/identifier để tránh entry mồ côi hoặc launcher trỏ sai.

## 14. Bảng kiểm tra QA theo lớp

| Lớp | Kiểm tra | Kết quả hợp lệ |
| --- | --- | --- |
| Java source | `javac --release 17` | Có class file, không lỗi biên dịch |
| JAR | `java -jar ... --cli sample.jotdemo` | Đúng hai dòng stdout |
| Properties | Có `extension=jotdemo` và MIME phù hợp | File hợp lệ, được jpackage đọc |
| App image | Launcher chạy được khi có đối số | Có runtime và JAR đủ dependencies |
| Native installer | `jpackage --type ... --file-associations ...` | Build thành công đúng OS |
| OS registry/MIME/Launch Services | JotDemo xuất hiện như handler của `.jotdemo` | Handler được đăng ký, chưa chắc default |
| Người dùng mở file | Mở tệp bằng JotDemo từ file manager | Hộp thoại hiển thị đúng tên/dòng đầu |
| File path có space | `my notes.jotdemo` | Không bị cắt thành nhiều argument |
| Đường dẫn sai | Tệp không tồn tại/không phải file | Ứng dụng báo lỗi đúng |
| Dữ liệu sai | Extension không đúng, file quá lớn, encoding lỗi | Không xử lý mù quáng |
| Uninstall | Gỡ JotDemo | Trạng thái handler/default được OS cập nhật phù hợp |

Không đánh dấu **QA PASS cho association** chỉ bằng việc `jpackage` trả exit code 0. Chỉ kết luận sau khi **đã cài** và kiểm tra hành vi mở tệp trên hệ điều hành tương ứng.

## 15. Bài thực hành

### Bài A — Tạo association đầu tiên

Tạo `jotdemo.properties` với `extension`, `mime-type` và `description` như bài. Biên dịch `JotDemo.java`, tạo JAR và chạy kiểm tra CLI với file nhỏ. Giải thích vì sao CLI test thành công không đồng nghĩa association đã tồn tại.

### Bài B — Đóng gói và cài đặt

Build installer dành cho hệ điều hành bạn sử dụng. Cài gói, kiểm tra JotDemo trong `Open with` rồi thử mở `sample.jotdemo`. Ghi nhận các bước OS đã thực hiện; nếu cần chọn default, hãy làm bằng UI chính thức của OS.

### Bài C — Hai loại tệp

Tạo file properties thứ hai cho `.jotnote`, lặp `--file-associations` trong command `jpackage`. Mở cả hai loại sau khi cài đặt. Sửa Java handler để cho phép cả hai phần mở rộng **một cách có chủ đích**, thay vì chỉ đổi properties rồi nghĩ code tự hỗ trợ.

### Bài D — Kiểm tra các trường hợp khó

Thử file tên `my notes.jotdemo`, tên có Unicode, file rỗng, file không tồn tại, file lớn hơn 64 KiB và file bị sai encoding. Ghi rõ ở tầng nào phát hiện lỗi: OS association, argument truyền vào launcher hay code Java.

### Bài E — Tôn trọng app mặc định

Giả sử máy đã cài hai ứng dụng có thể mở `.jotdemo`. Xác nhận JotDemo vẫn có thể được chọn qua `Open with` ngay cả khi ứng dụng khác đang mặc định; không tự thay đổi default nếu chưa được người dùng chọn.

### Bài F — Chuẩn bị phát hành thực tế

Viết checklist cho code signing/notarization, quyền cài đặt, kiểm tra trên VM sạch, tương thích OS/CPU, nâng cấp và gỡ cài đặt. Giải thích vì sao file association **không phải một cơ chế bảo mật hay file parser**.

**Tiêu chí đạt:** Người học nêu được bốn khóa properties, tạo và dùng chính xác `--file-associations`, phân biệt build/cài đặt/ứng dụng mặc định, và chứng minh ứng dụng Java nhận, kiểm tra, xử lý được **tệp thực sự do người dùng mở** trên OS đích.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 26 — Support Application Requirements, Set File Associations](https://docs.oracle.com/en/java/javase/26/jpackage/support-application-features.html): hướng dẫn các khóa `extension`, `mime-type`, `description`, `icon`, quy tắc mỗi association một properties file.
- [Oracle Java SE 26 — jpackage command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html): vị trí tùy chọn `--file-associations` trong nhóm tạo application package, định dạng installer và giới hạn nền tảng.
- [Oracle Java SE 17 — jpackage command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): cách sử dụng API/tool trên JDK 17+.
- [Oracle Java SE 26 — Packaging Overview](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html): application image, installer, các prerequisites theo hệ điều hành.
- [Oracle Java SE 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cách truyền arguments tới Java main class và chạy JAR.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): chuẩn hóa công cụ `jpackage` từ JDK 16.

**Ghi nhớ:** **`--file-associations` mô tả khả năng mở một loại tệp để bộ cài đặt đăng ký với OS.** Nó không thay thế logic đọc file trong Java, không bảo đảm ứng dụng trở thành mặc định và không phải là cơ chế tự kích hoạt khi chỉ tạo một `app-image`. Chỉ sau khi cài đặt, chọn handler thích hợp và mở thử một file thật, bạn mới có thể xác nhận liên kết hoạt động.