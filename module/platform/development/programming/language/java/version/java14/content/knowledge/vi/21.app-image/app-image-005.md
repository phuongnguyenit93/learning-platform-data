# App image: đối số ứng dụng và tùy chọn JVM cho launcher bằng jpackage (Java 16+)

## 1. Mục tiêu: cấu hình lúc khởi chạy ứng dụng đã đóng gói

Một ứng dụng Java thường khởi chạy bằng dòng lệnh:

```bash
java -Xmx128m -Ddemo.profile=packaged -jar LauncherArgsDemo.jar --mode=default limit=5
```

Dòng trên minh họa **hai nhóm tham số khác nhau**:

1. **JVM options** như `-Xmx128m` và `-Ddemo.profile=packaged` được JVM xử lý *trước khi chạy `main`*. `-Xmx128m` cấu hình giới hạn heap, còn `-D...` tạo Java system property.
2. **Application arguments** như `--mode=default` và `limit=5` được truyền cho chương trình qua `String[] args` của `public static void main(String[] args)`. JVM không tự hiểu ý nghĩa nghiệp vụ của chúng: chính ứng dụng cần parse và xử lý.

Khi đóng gói thành **application image** bằng công cụ `jpackage`, người dùng cuối có thể mở một **launcher riêng của nền tảng**, chẳng hạn `LaunchDemo.exe` trên Windows, thay vì phải tự nhập `java -jar`. Nhà phát triển cần quyết định:

- Launcher mặc định chuyển **đối số nào tới `main(String[] args)`** khi người dùng không cung cấp tham số?
- Launcher tự cấu hình **JVM options nào** (system properties, kích thước heap, các tùy chọn runtime)?
- Người dùng có thể **thay các tham số ứng dụng** trên dòng lệnh hay không?
- Nếu ứng dụng có nhiều chế độ chạy, có cần **launcher thứ hai** với cấu hình riêng không?
- Làm thế nào để **kiểm tra app-image tạo ra thực sự chứa đúng cấu hình**?

Hai tùy chọn `jpackage` trực tiếp giải quyết bài toán:

```text
--arguments     đối số mặc định cho main(String[] args)
--java-options  tùy chọn dành cho JVM của packaged launcher
```

**Đây là chủ đề của bài:** cấu hình và kiểm thử đối số ứng dụng và JVM options của launcher trong một **app image** được tạo bằng `jpackage` hiện hành.

### Phiên bản còn áp dụng

`jpackage` xuất hiện ở dạng **incubating tool trong Java 14** (JEP 343), tiếp tục incubating trong Java 15, và trở thành **production-ready từ Java 16** (JEP 392). Trong các JDK hiện đại, sử dụng công cụ **`jpackage` chính thức**, không sử dụng hướng dẫn incubator hoặc tên module `jdk.incubator.jpackage` đã lỗi thời. Bài thực hành dùng mã Java 17 và lệnh `jpackage` của JDK hiện hành.

## 2. Application image là gì, khác installer ra sao?

**App image** là một thư mục kết quả chứa:

- Launcher dành cho hệ điều hành, ví dụ `LaunchDemo.exe` trên Windows.
- Các JAR/module, resource và file cấu hình launcher của ứng dụng.
- Java runtime image cần thiết cho ứng dụng (mặc định có thể được `jpackage` tạo thông qua `jlink`), giúp người dùng không phải cài một Java runtime riêng cho mỗi app.
- Những tệp phụ trợ khác tùy hệ điều hành, JDK và cấu hình đóng gói.

Để tạo app image:

```bash
jpackage --type app-image --name LaunchDemo --input app-input --main-jar LauncherArgsDemo.jar --main-class LauncherArgsDemo --dest out
```

Đây là **lệnh minh họa sau khi đã tạo JAR và thư mục `app-input`**. Nếu không có JAR, lệnh sẽ thất bại. `--type app-image` yêu cầu tạo **thư mục application image**, **không phải file cài đặt** `.msi`, `.exe` installer, `.deb` hay `.dmg`.

**Nhiều phần mềm có “file .exe” trong app image trên Windows, nhưng đó là file launcher; không đồng nghĩa đã có installer EXE.** Để tạo installer, cần chọn package type tương ứng và có thể phải chuẩn bị công cụ cài đặt/signing của nền tảng.

`jpackage` tạo output **cho hệ điều hành đang chạy công cụ**; không có cơ chế cross-package tự động từ Windows sang macOS/Linux bằng một lệnh. Vì vậy, ví dụ đường dẫn `.exe` ở bài này dành cho Windows. Linux/macOS có bố cục, executable và quy tắc bundle khác. Những cờ như `--win-console` **chỉ dùng trên Windows**.

## 3. Hai nhóm tham số: đừng nhầm `--arguments` với `--java-options`

| Tiêu chí | `--arguments` | `--java-options` |
| --- | --- | --- |
| Đích nhận | `String[] args` trong `main` | JVM được launcher khởi tạo |
| Ví dụ | `--mode=default`, `limit=5` | `-Ddemo.profile=packaged`, `-Xmx128m` |
| Tác dụng | Chọn chế độ ứng dụng, file dữ liệu, business flag... | Cấu hình heap, system properties, module access và các option JVM |
| Khi user chạy launcher với tham số mới | **Tham số mới thay danh sách default arguments** | JVM options đã cấu hình vẫn áp dụng theo launcher |
| Có thể lặp option lúc đóng gói? | Có, `--arguments` nhiều lần | Có, `--java-options` nhiều lần |
| Được lưu ở đâu? | Phần `[ArgOptions]` của `app-name.cfg` | Phần `[JavaOptions]` của `app-name.cfg` |
| Do Java app tự parse? | Có | Không; JVM xử lý trước khi gọi `main` |

### Ví dụ đối số ứng dụng

```bash
jpackage ... --arguments "--mode=default" --arguments "limit=5"
```

Dấu ba chấm ở đây chỉ là **ký hiệu cho các option đóng gói khác**, không phải lệnh độc lập có thể chạy nguyên văn. Hai lần `--arguments` làm mặc định `main` nhận hai phần tử:

```text
args[0] = --mode=default
args[1] = limit=5
```

Khi user chạy launcher **không có tham số dòng lệnh**, hai giá trị mặc định được truyền vào `main`. Nếu user tự chạy launcher với `--mode=cli limit=9`, những tham số dòng lệnh mới **thay thế danh sách default arguments**, không tự động nối vào phía sau mặc định.

**Không mặc định các cờ kiểu `--mode=...` có ý nghĩa đặc biệt đối với `jpackage` hoặc JVM.** Đây chỉ là các chuỗi mà tác giả chương trình `main` có thể tự phân tích.

### Ví dụ JVM options

```bash
jpackage ... --java-options "-Ddemo.profile=packaged" --java-options "-Xmx128m"
```

Hai tùy chọn JVM ở trên được lưu trong launcher và sử dụng khi launcher khởi tạo Java runtime:

- `-Ddemo.profile=packaged`: truy cập trong mã bằng `System.getProperty("demo.profile")`.
- `-Xmx128m`: chọn mức tối đa heap do JVM quản lý. Đây không phải là lời hứa tiến trình chỉ dùng tối đa 128 MiB RAM tổng cộng; JVM còn dùng native memory, thread stack, code cache và các vùng khác.

**Không truyền một JVM option bằng cách gõ nó sau file executable rồi kỳ vọng có tác dụng như `java -Xmx...`.** Tham số được thêm sau packaged launcher thông thường là **application arguments**, không phải option khởi tạo JVM. Muốn một cấu hình JVM khác, chuẩn bị launcher/config khác và kiểm thử nó.

## 4. Ví dụ hoàn chỉnh: Java `main` nhìn thấy tham số gì?

Tạo tệp **`LauncherArgsDemo.java`** với chương trình độc lập:

```java
import java.lang.management.ManagementFactory;
import java.util.Arrays;

public class LauncherArgsDemo {
    public static void main(String[] args) {
        System.out.println("profile=" +
                System.getProperty("demo.profile", "unset"));

        System.out.println("args=" + Arrays.toString(args));

        System.out.println("heapOption=" +
                ManagementFactory.getRuntimeMXBean()
                        .getInputArguments().contains("-Xmx128m"));
    }
}
```

Đây là toàn bộ source có thể biên dịch bằng Java 17+. Tên lớp public và tên file đều là `LauncherArgsDemo`.

**Chương trình kiểm chứng trực tiếp ba khía cạnh:**

1. System property `demo.profile` có được launcher truyền tới JVM hay không.
2. Mảng `args` có đúng các tham số ứng dụng mặc định hoặc tham số người dùng chọn khi chạy không.
3. Danh sách JVM input arguments được `RuntimeMXBean` báo cáo có chứa chính xác `-Xmx128m` hay không.

`ManagementFactory.getRuntimeMXBean().getInputArguments()` phù hợp cho **demo/diagnostics** vì nó phản ánh tập tùy chọn JVM được biết tới qua API quản lý. Nó **không phải cách tổng quát để xác nhận mọi cài đặt JVM đã có hiệu lực trong mọi tình huống**; option có thể chịu ảnh hưởng của cách launcher/runtime áp dụng hoặc giá trị được sinh động. Trong ví dụ này, kiểm tra mục tiêu cụ thể `-Xmx128m` là đủ và đã được chạy thực tế.

### Biên dịch và tạo JAR

Các lệnh PowerShell sau chạy trong thư mục chứa `LauncherArgsDemo.java`:

```powershell
New-Item -ItemType Directory -Force -Path classes, app-input, out | Out-Null

javac --release 17 -encoding UTF-8 -d classes LauncherArgsDemo.java

jar --create --file app-input/LauncherArgsDemo.jar --main-class LauncherArgsDemo -C classes .
```

Trong đó:

- `javac --release 17` biên dịch chương trình theo Java 17, không cần preview flag.
- `-d classes` đưa file `.class` vào thư mục riêng.
- `jar --create` tạo JAR với main class được chỉ định; không cần tự viết manifest bằng tay.
- `app-input` là thư mục nguồn mà `jpackage --input` sẽ đưa nội dung vào app image.
- `out` là nơi nhận thư mục output từ `jpackage`.

**Lưu ý:** các lệnh là PowerShell Windows; nếu dùng Bash trên Linux/macOS, thay lệnh tạo thư mục bằng `mkdir -p classes app-input out` và điều chỉnh đường dẫn sau khi đóng gói theo nền tảng. `javac` và `jar` là công cụ JDK, không phải chức năng của `jpackage`.

## 5. Tạo app image với cả application arguments và JVM options

Trên **Windows PowerShell**, sau khi có `app-input/LauncherArgsDemo.jar`, dùng một lệnh duy nhất:

```powershell
jpackage --type app-image --name LaunchDemo --input app-input --main-jar LauncherArgsDemo.jar --main-class LauncherArgsDemo --dest out --arguments "--mode=default" --arguments "limit=5" --java-options "-Ddemo.profile=packaged" --java-options "-Xmx128m" --win-console
```

Lệnh là mẫu **đã kiểm thử** với `jpackage` JDK hiện đại. Các phần đáng chú ý:

- `--type app-image`: xuất application image thay vì installer.
- `--name LaunchDemo`: tên bundle và launcher chính.
- `--input app-input`: lấy các payload JAR/resources trong thư mục này.
- `--main-jar LauncherArgsDemo.jar`: JAR chính của app, tên đường dẫn được giải theo `--input`.
- `--main-class LauncherArgsDemo`: entry point Java của JAR.
- `--dest out`: đặt kết quả dưới `out`.
- Hai `--arguments`: tạo **hai** application args mặc định.
- Hai `--java-options`: chuyển hai JVM options cho launcher.
- `--win-console`: trên Windows, tạo **console launcher**, cần thiết để quan sát `System.out.println` khi chạy kiểu CLI.

**Không cần bộ cài Windows (WiX) chỉ để tạo `--type app-image`** theo nhu cầu ví dụ này. Nếu chọn `--type exe`/`msi` để tạo installer, các yêu cầu công cụ nền tảng có thể khác. Tham số `--win-console` cũng không được đem nguyên xi sang Linux/macOS.

Sau khi tạo xong, trên Windows có thể chạy:

```powershell
.\out\LaunchDemo\LaunchDemo.exe
```

**Standard output (khởi chạy không truyền đối số mới):**

```text
profile=packaged
args=[--mode=default, limit=5]
heapOption=true
```

Ý nghĩa:

- `profile=packaged` chứng minh JVM đọc được system property từ `--java-options "-Ddemo.profile=packaged"`.
- `args=[--mode=default, limit=5]` chứng minh hai `--arguments` được chuyển tới `main`.
- `heapOption=true` xác nhận JVM startup có `-Xmx128m` trong danh sách input arguments.

### Khi user truyền tham số lúc mở launcher

Tiếp tục chạy:

```powershell
.\out\LaunchDemo\LaunchDemo.exe --mode=cli limit=9
```

**Standard output:**

```text
profile=packaged
args=[--mode=cli, limit=9]
heapOption=true
```

So với lần đầu, **chỉ application args đổi**: `--mode=cli` và `limit=9` thay hoàn toàn `--mode=default` và `limit=5`. Hai JVM options còn áp dụng, vì launcher vẫn sử dụng cấu hình JVM đã đóng gói.

Cần hiểu “có thể truyền arguments lúc chạy” là **khả năng của launcher nhận các đối số dòng lệnh**, không có nghĩa ứng dụng nhất thiết hiểu một cờ mới. Nếu chương trình không parse hoặc bỏ qua tham số, chức năng tương ứng không tự xuất hiện.

## 6. Tạo launcher phụ với cấu hình khác bằng `--add-launcher`

Một app image có thể cần nhiều entry point hoặc **nhiều profile chạy cùng ứng dụng**: launcher thường dùng chế độ mặc định, launcher phụ dùng chế độ “safe” hoặc “diagnostics”.

`jpackage` hỗ trợ:

```text
--add-launcher launcher-name=properties-file
```

`properties-file` là file dạng Java properties mô tả những option bổ sung/ghi đè cho launcher phụ. Ví dụ tạo tệp **`safe-launcher.properties`** bên cạnh thư mục `app-input` và chứa đúng:

```properties
arguments=--mode=safe
java-options=-Ddemo.profile=safe
win-console=true
```

Các key trên đang được hỗ trợ trong các bản JDK hiện hành:

- `arguments`: danh sách default arguments cho launcher phụ.
- `java-options`: những JVM options dành cho launcher phụ.
- `win-console`: tùy chọn Windows để có console khi chạy.
- Một số key khác có thể là `main-jar`, `main-class`, `module`, `icon`, `description` tùy mục đích; không cần đặt chúng khi launcher phụ vẫn dùng main JAR/class của launcher chính.

Chạy lệnh tạo app image **mới** từ nguồn, lần này có thêm `--add-launcher`:

```powershell
jpackage --type app-image --name LaunchDemo --input app-input --main-jar LauncherArgsDemo.jar --main-class LauncherArgsDemo --dest out --arguments "--mode=default" --arguments "limit=5" --java-options "-Ddemo.profile=packaged" --java-options "-Xmx128m" --win-console --add-launcher "LaunchDemoSafe=safe-launcher.properties"
```

**Quan trọng:** Hai lệnh tạo image trong phần 5 và phần 6 là **hai lựa chọn thay thế**. `jpackage` sẽ không tạo đè một output `out/LaunchDemo` đã tồn tại theo ý bạn. Muốn thực hành phần 6 sau phần 5, dùng một **thư mục `--dest` mới**, hoặc chỉ chạy **lệnh phần 6 từ đầu** khi `out/LaunchDemo` chưa tồn tại. Đừng dùng `--add-launcher` như một lệnh cập nhật image đã tạo sẵn.

Ví dụ sau được kiểm thử thực tế với **app image mới**, có cả launcher chính `LaunchDemo.exe` và launcher phụ `LaunchDemoSafe.exe` trên Windows.

Chạy launcher phụ:

```powershell
.\out\LaunchDemo\LaunchDemoSafe.exe
```

**Standard output của ví dụ đã kiểm thử:**

```text
profile=safe
args=[--mode=safe]
heapOption=false
```

Điều này cho thấy:

- Launcher phụ đã dùng **application args riêng**: `--mode=safe`.
- JVM của launcher phụ đã nhận system property **`demo.profile=safe`**.
- `heapOption=false` vì trong ví dụ launcher phụ chỉ có JVM option `-Ddemo.profile=safe`: danh sách JVM options đã được **ghi đè** so với lựa chọn của launcher chính, do đó không còn `-Xmx128m`.

**Hệ quả thiết kế:** Nếu launcher phụ vẫn cần giới hạn heap của launcher chính, hãy **nêu nó rõ ràng** trong `java-options` của launcher phụ, ví dụ một dòng phù hợp chứa cả `-Ddemo.profile=safe` và `-Xmx128m`. Đừng giả định mọi cấu hình cũ sẽ được cộng dồn. Khi nhiều launcher có default JVM options riêng, **kiểm tra từng launcher** thay vì chỉ chạy launcher chính.

### Khi nào launcher phụ hữu ích?

- Khởi chạy app với những **default app args** khác nhau, ví dụ chế độ đọc dữ liệu, chạy batch, chạy giao diện.
- Khởi chạy cùng app với **system property/heap khác** dành cho môi trường đặc biệt, chẳng hạn chẩn đoán giới hạn bộ nhớ.
- Có thêm một **launcher console trên Windows** để xem stdout/log khi launcher chính là giao diện GUI.
- Nhiều main class/module trong một image, khi các cấu hình main-jar/main-class/module và runtime thực sự phù hợp.

**Không** gộp vào app-image mọi chế độ chứa bí mật rồi cho rằng những giá trị đó được che giấu. Các option mặc định có thể nằm trong file cấu hình và dễ bị kiểm tra.

## 7. Kiểm tra file cấu hình launcher trong app image

`jpackage` tạo file cấu hình theo tên launcher. Trên Windows với app image ví dụ, vị trí chính là:

```text
out/
  LaunchDemo/
    LaunchDemo.exe
    LaunchDemoSafe.exe     (nếu dùng --add-launcher)
    app/
      LaunchDemo.cfg
      LaunchDemoSafe.cfg   (nếu có launcher phụ)
      LauncherArgsDemo.jar
    runtime/
      ...
```

Đây là **sơ đồ khái quát trên Windows**, không phải giao diện thư mục được cam kết giống hệt ở Linux/macOS hoặc mọi JDK. Khi kiểm tra, dùng file thực tế trong image đã tạo.

Trong `app/LaunchDemo.cfg`, hai phần liên quan là:

```ini
[JavaOptions]
java-options=-Djpackage.app-version=1.0
java-options=-Ddemo.profile=packaged
java-options=-Xmx128m

[ArgOptions]
arguments=--mode=default
arguments=limit=5
```

Đoạn trên là **trích phần liên quan trong một kết quả đã kiểm thử**, không phải toàn bộ file config và không phải format phải giống từng dòng trong mọi JDK. `-Djpackage.app-version=1.0` là option được công cụ sinh theo cấu hình version mặc định trong lần thử này. Những giá trị do bạn chọn đáng chú ý nhất là:

- `java-options=-Ddemo.profile=packaged`.
- `java-options=-Xmx128m`.
- `arguments=--mode=default`.
- `arguments=limit=5`.

Tại sao vừa xem `cfg` vừa chạy `.exe`?

1. **Kiểm tra file `cfg`** chứng minh các tùy chọn đã được **ghi vào image**.
2. **Chạy launcher thật** chứng minh chúng được **JVM/`main` nhận ở runtime**.
3. **Chạy với app args khác** chứng minh semantics override default args.
4. **Chạy launcher phụ** chứng minh cấu hình độc lập, thay vì giả định nó kế thừa mọi JVM option.

Nếu `cfg` trông đúng nhưng chương trình hoạt động sai, hãy tiếp tục kiểm tra cách **ứng dụng parse `args`**, runtime được đóng gói, quoting, quyền đọc resource và những option JVM không hợp lệ. Không tự kết luận rằng `jpackage` đã đặt sai chỉ vì business flag không tạo hiệu ứng mong muốn.

## 8. Xử lý đối số có dấu cách và quoting

Đối số có khoảng trắng là nguồn lỗi phổ biến. Ví dụ muốn `main` nhận **một** phần tử `"customer data"` thay vì **hai** phần tử `"customer"` và `"data"`.

Theo hướng dẫn `jpackage`, khi truyền một argument chứa space qua `--arguments`, cần **hai lớp quoting**: một lớp để shell chuyển đúng giá trị cho `jpackage`, và một lớp để trình phân tích đối số mặc định của launcher hiểu toàn bộ phần có space là **một argument**.

Trong tài liệu chính thức, các dạng tổng quát như sau:

```text
--arguments "\"String 1\" \"String 2\""
--arguments "\"String 1\"" --arguments "\"String 2\""
```

Đây là các ví dụ minh họa **theo cú pháp escaping của hướng dẫn shell**, không phải hai lệnh hoàn chỉnh. Chúng nhằm chỉ ra **dấu nháy bao trong** để giữ space trong một giá trị. **PowerShell, cmd, Bash và hệ thống build Gradle/Maven có quy tắc quoting riêng.** Đừng dán các escape với giả định mọi shell xử lý chúng giống nhau.

Cách giảm lỗi:

- Nếu có thể, dùng **một đối số không chứa khoảng trắng** hoặc đổi thành key-value mà ứng dụng parse được.
- Khi bắt buộc có space, kiểm tra `Arrays.toString(args)` ở ứng dụng thực tế và assert `args.length`/giá trị.
- Với launcher phụ, có thể dùng dòng property có quoting rõ ràng, ví dụ `arguments=--file "customer data.csv"`, sau đó chạy thử `LaunchDemoSafe` để xác nhận hai phần tử.
- Chú ý đường dẫn Windows chứa dấu cách, shell quoting và escape của file properties; **mỗi tầng có quy tắc khác nhau**.
- Nếu dùng `@options-file` của `jpackage` để gom các option đóng gói, đó là **file cấu hình cho công cụ jpackage lúc build**, không phải tự động là tham số `main` khi launcher chạy.

**Đừng dùng `String.split(" ")` để giải mã lại `args`**. Java launcher đã phân tách arguments thành các phần tử `String[]`. Một đối số chứa dấu cách là **một phần tử**, không phải chuỗi cần split tiếp.

## 9. JVM options chứa giá trị và đường dẫn

### 9.1. System properties bằng `-D`

Định dạng thường gặp:

```text
-Dname=value
```

Ví dụ:

```powershell
jpackage --type app-image --name LaunchDemo --input app-input --main-jar LauncherArgsDemo.jar --dest out --java-options "-Ddemo.profile=prod"
```

Đây là **một lựa chọn lệnh khác**; không chạy trên output trùng tên đã tồn tại. Nó minh họa cách đưa property vào JVM. Mã `main` có thể đọc bằng:

```java
String profile = System.getProperty("demo.profile", "unset");
```

**Đừng đặt thông tin bí mật** như password, API key, token hoặc secret trực tiếp trong `-D...` được đóng gói: chúng có thể hiện ra trong cấu hình launcher, công cụ chẩn đoán hoặc dữ liệu hệ thống.

### 9.2. Kích thước heap

`-Xms` chọn kích thước heap ban đầu, `-Xmx` chọn giới hạn tối đa heap. Những giá trị này là **option JVM**, không phải application args:

```text
--java-options "-Xms64m"
--java-options "-Xmx128m"
```

Ví dụ dùng `-Xmx128m` chỉ để kiểm chứng. Với ứng dụng thật, tính toán heap theo bộ nhớ thiết bị, container limits và yêu cầu của công việc. Không sao chép giới hạn 128 MiB cho mọi workload.

### 9.3. Đường dẫn tới resource trong app image

`jpackage` hỗ trợ các ký hiệu mở rộng ở runtime trong `--arguments` và `--java-options`, bao gồm **`$APPDIR`, `$BINDIR` và `$ROOTDIR`**. Chúng giúp tham chiếu resource mà không hardcode vị trí cài đặt cụ thể.

Ví dụ minh họa:

```text
--java-options "-Dapp.config=$APPDIR/config/settings.properties"
```

Đây là **đoạn option**, không phải lệnh đầy đủ. File `config/settings.properties` phải thật sự được đưa vào payload image đúng vị trí mong muốn. Nếu chạy trong PowerShell, ký tự `$` cũng được shell dùng cho variable expansion, nên phải dùng quoting/escaping phù hợp để `jpackage` nhận nguyên ký hiệu cần xử lý lúc runtime.

**Không mặc định `$APPDIR` là biến môi trường thật mà user phải tự khai báo.** Nó là macro đặc biệt mà jpackage launcher hỗ trợ mở rộng. Nội dung chính xác của `$APPDIR`/`$BINDIR`/`$ROOTDIR` phụ thuộc bố cục bundle trên nền tảng tương ứng.

### 9.4. Tránh ghi đè classpath/module path sai

Với ứng dụng non-modular, `jpackage` tạo classpath mặc định gồm các JAR trong `--input`. Nếu tự chỉ định `-cp`, `-classpath` hoặc `-Djava.class.path` qua `--java-options`, có thể **ghi đè classpath tự sinh**, làm launcher không còn tìm thấy main class hoặc dependency.

Nếu bắt buộc cấu hình classpath, cần bảo đảm mọi JAR cần thiết của image vẫn nằm trong đường dẫn đã chỉ định, kiểm thử dưới launcher thật và chú ý dấu phân cách classpath của Windows khác Linux/macOS.

Với ứng dụng modular, `--module-path` và `--module` của `jpackage` là những option ở **giai đoạn đóng gói**; không nhầm chúng với một application arg tên `--module-path`. Khi cần modular app, build module đúng, cung cấp dependency và kiểm tra runtime image chứa đủ module.

## 10. Phân biệt option của công cụ đóng gói với option JVM chạy app

Không phải option nào của `jpackage` cũng được chuyển cho JVM hoặc cho `main`. Một số điều khiển quá trình **build image**, một số đi vào cấu hình **launcher**:

| Option | Giai đoạn | Vai trò |
| --- | --- | --- |
| `--type app-image` | Build | Chọn xuất app image |
| `--name` | Build | Tên ứng dụng/launcher |
| `--input` | Build | Thư mục payload |
| `--main-jar` / `--main-class` | Build + launcher metadata | Chọn entry point non-modular |
| `--module` / `--module-path` | Build + runtime/linking | Chọn entry point modular và module path |
| `--runtime-image` | Build | Dùng Java runtime image đã dựng sẵn |
| `--jlink-options` | Build | Điều khiển cách `jlink` tạo runtime |
| `--arguments` | Launcher | Default `String[] args` |
| `--java-options` | Launcher/JVM | JVM options mặc định |
| `--add-launcher` | Build | Tạo thêm launcher với config riêng |
| `--win-console` | Launcher Windows | Cho phép tương tác/quan sát console |

**Ví dụ về sự nhầm lẫn:** Muốn heap lớn hơn nhưng lại viết `--arguments "-Xmx2g"`. Khi đó `main` nhận một chuỗi `"-Xmx2g"`, **không làm JVM tăng heap**. Ngược lại, muốn application mode `--mode=batch` nhưng lại viết `--java-options "--mode=batch"`; JVM có thể coi đó là option không hợp lệ và launcher không khởi động đúng.

## 11. Phối hợp build automation và kiểm thử

Với project Maven/Gradle, có thể tự động hóa việc tạo JAR rồi chạy `jpackage` ở build pipeline. Nhưng hãy thiết kế test ở **hai cấp**:

### 11.1. Test Java entry point

Chạy JAR trực tiếp:

```powershell
java -Ddemo.profile=packaged -Xmx128m -jar app-input/LauncherArgsDemo.jar --mode=default limit=5
```

Mục đích là xác nhận code `main` xử lý `args` và `System.getProperty` đúng. Test ở cấp này **chưa xác minh launcher của jpackage**.

### 11.2. Test packaged launcher thực

Sau khi build app image, chạy executable:

```powershell
.\out\LaunchDemo\LaunchDemo.exe
.\out\LaunchDemo\LaunchDemo.exe --mode=cli limit=9
```

Kiểm tra:

1. Không truyền runtime args → `args` có giá trị mặc định đã cấu hình.
2. Truyền runtime args → chúng thay default arguments.
3. System property và JVM option vẫn có hiệu lực.
4. Nếu có launcher phụ, test từng launcher riêng.
5. Các file resource được tham chiếu bằng macro/đường dẫn thực sự tồn tại.
6. Image dùng đúng JRE/JDK runtime dự định; máy test khác không phải cài Java riêng nếu image đóng đủ runtime.

### 11.3. Test trên đúng nền tảng phát hành

- **Windows:** `--win-console` cho demo CLI, có thể cần ký gói/file theo yêu cầu phân phối. Nếu test build automation, kiểm tra executable và `app/LaunchDemo.cfg`.
- **Linux:** kiểm tra executable permissions, thư viện hệ thống và bố cục đường dẫn; không dùng `--win-console`.
- **macOS:** kiểm tra bundle, cấp quyền/việc ký và tương tác với policy hệ điều hành nếu phân phối; không giả định app image macOS giống folder Windows.

`jpackage` **không cross-compile installer/image cho nền tảng khác**: tạo trên đúng OS mục tiêu, hoặc thiết lập các runner CI phù hợp. Tính năng app-image giúp thử launcher trước khi tạo installer/phát hành.

## 12. Lỗi thường gặp

| Lỗi / hiểu nhầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt `-Xmx128m` trong `--arguments` | `main` nhận chuỗi, heap không đổi theo ý định | Dùng `--java-options` |
| Đặt `--mode=default` trong `--java-options` | JVM có thể báo option không hợp lệ | Đưa vào `--arguments` |
| Nghĩ user args được **nối thêm** vào args mặc định | Kết quả `String[] args` khác dự đoán | User args thay default args nếu được cung cấp |
| Nghĩ user gõ `-D...` sau `LaunchDemo.exe` sẽ thiết lập property | Thường chỉ đi vào `args` | Cấu hình JVM options cho launcher khi đóng gói |
| Chỉ test `java -jar` | Không xác nhận cấu hình launcher sinh ra | Chạy executable trong app image |
| Quên `--win-console` khi cần xem stdout trên Windows | Không quan sát console output như mong muốn | Dùng launcher console cho CLI |
| Tạo app image rồi nghĩ đã có installer | Nhầm thư mục image với gói cài đặt | Chọn package type và công cụ nền tảng khi cần |
| Chạy lại `jpackage` với `--dest` trùng output đã có | Công cụ không tự cập nhật image theo kỳ vọng | Dùng output mới hoặc dọn build artifacts có chủ đích |
| Tưởng launcher phụ cộng dồn mọi JVM option | Có thể bị ghi đè, như `-Xmx128m` trong ví dụ | Khai báo đủ JVM options cho launcher phụ |
| Viết app argument có space mà thiếu lớp quoting | Một argument bị tách thành nhiều phần tử | Quoting theo shell và parser launcher, test `args` |
| Dùng `$APPDIR` trong PowerShell mà không bảo vệ dấu `$` | Shell mở rộng biến trước `jpackage` | Escape/quote đúng để launcher xử lý macro ở runtime |
| Đưa secret vào `--java-options -D...` | Secret có thể lộ trong `cfg` và công cụ chẩn đoán | Cấu hình secret runtime theo cơ chế bảo mật |
| Đổi classpath qua `--java-options` mà quên JAR trong image | `ClassNotFoundException`/không chạy | Giữ đủ classpath JAR/module path |
| Dùng hướng dẫn `jdk.incubator.jpackage` của Java 14 cho JDK mới | Dựa vào interface incubator đã thay đổi | Dùng `jpackage` chính thức Java 16+ |
| Cho rằng `--release 17` quyết định phiên bản runtime được đóng gói | Nhầm version classfile với runtime image | Kiểm soát `jpackage` JDK hoặc `--runtime-image` |
| Không test trên máy/OS đích | Packaging có thể khác về đường dẫn và launcher | Dùng CI runner đúng OS và test image |

## 13. Quy trình áp dụng trong dự án

1. **Xác định loại app:** non-modular JAR hay modular app, entry point `main` và dependencies.
2. **Tạo artifact ứng dụng** chạy được bằng `java -jar` hoặc `java -m`; đảm bảo build/test của code Java đạt.
3. **Chọn ứng dụng cần đóng gói bằng jpackage** và runtime cần ship; dùng `--type app-image` để thử sớm launcher.
4. **Liệt kê mặc định cho `main`:** ví dụ mode, đường dẫn cấu hình, giới hạn bản ghi; đưa vào `--arguments`.
5. **Liệt kê tùy chọn JVM cần thiết:** heap, system property không nhạy cảm, flags được hỗ trợ; đưa vào `--java-options`.
6. **Quyết định launcher phụ:** dùng `--add-launcher` với properties riêng nếu cần entry point hoặc default JVM/args khác.
7. **Dùng một command/CI configuration tái lập được**, tránh sửa file `cfg` thủ công sau mỗi lần build mà không kiểm soát nguồn cấu hình.
8. **Chạy launcher thật** với không args và có args; kiểm tra output/behavior, không chỉ kiểm tra lệnh build trả exit code 0.
9. **Soát `app-name.cfg`** để xác nhận nhóm `[ArgOptions]` và `[JavaOptions]` có nội dung dự định.
10. **Kiểm tra security:** không embed secrets, không gắn `-D` chứa token; cân nhắc quyền truy cập resource và logging dữ liệu.
11. **Kiểm tra runtime/nền tảng:** build trên OS đích, kiểm chứng dependency và runtime image trên một máy phù hợp, tiến tới installer nếu nhu cầu phát hành yêu cầu.
12. **Lưu test hồi quy** cho các launcher chính/phụ, đảm bảo thay đổi build script không vô tình thay đổi args/JVM startup.

## 14. Câu hỏi tự kiểm tra

**1. `--arguments "--mode=default"` sẽ được Java runtime dùng như JVM flag hay thông số `main`?**

Nó là **application argument** truyền đến `main(String[] args)`, không phải JVM flag.

**2. Khi app-image đã có `--arguments "--mode=default"`, nếu user chạy `LaunchDemo.exe --mode=cli` thì `args` chứa gì?**

Thông thường chỉ `--mode=cli` được truyền. User arguments **ghi đè** toàn bộ danh sách default arguments của launcher, không tự append vào.

**3. Muốn đặt `System.getProperty("demo.profile")` thành `packaged`, dùng option nào?**

Dùng `--java-options "-Ddemo.profile=packaged"` lúc tạo launcher; system property được JVM khởi tạo trước khi chạy `main`.

**4. `-Xmx128m` có nghĩa chương trình không thể dùng quá 128 MiB RAM toàn tiến trình không?**

Không. Nó đặt **max Java heap**; total process memory còn có các phần bộ nhớ khác.

**5. Vì sao `--win-console` xuất hiện trong ví dụ nhưng không thể sao chép nguyên lệnh đó để build trên macOS?**

Vì đó là option **chỉ dành cho Windows**, và `jpackage` tạo app image **trên OS mục tiêu đang chạy**, không cross-platform.

**6. Launcher phụ có `java-options=-Ddemo.profile=safe` có luôn kế thừa `-Xmx128m` từ launcher chính không?**

Không thể mặc định như vậy. Trong demo đã kiểm thử, launcher phụ được cấu hình riêng và `heapOption=false`. Muốn giới hạn heap, khai báo rõ trong launcher phụ và chạy test.

**7. Có thể xem thông số `--arguments` và `--java-options` của image ở đâu?**

Trên Windows, tìm file `app/LaunchDemo.cfg`, lần lượt xem `[ArgOptions]` và `[JavaOptions]`. Sau đó chạy executable để kiểm tra hành vi thực tế.

**8. Thêm `--java-options "-cp ..."` có thể gây vấn đề gì?**

Nó có thể **ghi đè classpath mặc định** mà `jpackage` sinh cho non-modular app. Nếu không gồm đủ JAR cần thiết, ứng dụng có thể không tìm được class.

**9. Vì sao không nên đóng gói mật khẩu trong `-Dapp.secret=...`?**

Vì giá trị có thể hiện trong cấu hình launcher và các nguồn dữ liệu chẩn đoán/triển khai. Nên dùng secret management của môi trường vận hành.

## 15. Tài liệu chính thức, còn áp dụng hiện nay

- [Oracle Java 25 — The jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): `--type app-image`, `--arguments`, `--java-options`, `--add-launcher` và các option platform-specific.
- [Oracle Java 25 — Support Application Requirements](https://docs.oracle.com/en/java/javase/25/jpackage/support-application-features.html): cấu hình default arguments, JVM options, quoting và multiple launchers.
- [Oracle Java 25 — Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): ứng dụng image và Java runtime image.
- [Oracle Java 25 — Basic Packaging](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html): các cách đóng gói JAR/module và hành vi mặc định.
- [Oracle Java 16 — Significant Changes](https://docs.oracle.com/en/java/javase/16/migrate/significant-changes-jdk-release.html): `jpackage` chuyển từ incubating Java 14/15 thành tính năng chính thức từ Java 16 (JEP 392).
- [Java SE 25 — `java` Tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): kiến thức nền về option `-D`, `-Xmx` và cách Java launcher xử lý tùy chọn.

**Ghi nhớ:** Với app-image tạo bằng `jpackage`, **`--arguments` cấu hình tham số mặc định cho `main(String[] args)`**, còn **`--java-options` cấu hình JVM khi launcher khởi chạy**. User truyền application args mới có thể thay default arguments, nhưng không biến chúng thành JVM options. Hãy kiểm tra cả **`.cfg`** lẫn **executable thực**, đặc biệt khi có launcher phụ và quy tắc quoting hoặc platform khác nhau.
