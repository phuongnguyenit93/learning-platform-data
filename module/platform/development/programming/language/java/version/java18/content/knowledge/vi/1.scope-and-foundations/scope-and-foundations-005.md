# Xác minh java, javac, javadoc và jwebserver thuộc cùng bộ JDK bằng đường dẫn và thông tin phiên bản

> **Chương:** Phạm vi và nền tảng  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Xác định chính xác bốn công cụ đang được gọi từ terminal, đối chiếu đường dẫn cài đặt và phiên bản runtime, rồi xử lý các trường hợp PATH, JAVA_HOME, symlink, shim, IDE hoặc build tool khiến máy dùng lẫn nhiều JDK. Các lệnh minh họa áp dụng cho JDK hiện đại có hỗ trợ các công cụ Java 18 trở lên.

## 1. Vì sao phải kiểm tra cả đường dẫn lẫn phiên bản?

Một máy có thể cài đồng thời JDK 17, 21 và 25. Terminal có thể gọi `java` từ JDK 25, nhưng `javac` hoặc `javadoc` lại đến từ JDK 17 do thứ tự `PATH`. Một lệnh `jwebserver` khác có thể được gọi từ bản cài thứ ba.

Khi đó, một kết quả như:

~~~text
java 25.0.x
javac 17.0.x
javadoc 25.0.x
jwebserver 21.0.x
~~~

đã cho thấy môi trường không nhất quán. Ngay cả khi cả bốn lệnh đều báo major version 25, chỉ nhìn số phiên bản vẫn chưa đủ chứng minh chúng đến từ **cùng một bộ cài**: chúng có thể thuộc các vendor, patch build hoặc thư mục JDK khác nhau.

Đối với module Java 18, việc kiểm tra có ý nghĩa vì các phần thực hành dùng những thành phần được đưa vào JDK 18:

- **JEP 400:** hành vi default charset UTF-8 trên cấu hình mặc định.
- **JEP 408:** công cụ `jwebserver` và module `jdk.httpserver`.
- **JEP 413:** `{@snippet}` trong standard doclet của `javadoc`.
- **JEP 418:** `InetAddressResolverProvider` trong Java SE API.
- **JEP 416:** core reflection được tái triển khai bằng method handles; API `MethodHandle` vốn có từ Java 7.

Một JDK hiện đại như Java 21 LTS hoặc 25 LTS có thể thực hành các nội dung này. Cần xác minh **các công cụ cùng thuộc bộ JDK được chọn**, thay vì chỉ kiểm tra một lệnh `java -version`.

Sau bài này, người học có thể:

1. Phân biệt `JAVA_HOME` với cơ chế phân giải lệnh qua `PATH`.
2. Liệt kê mọi executable có tên `java`, `javac`, `javadoc` và `jwebserver` mà shell tìm thấy.
3. Đối chiếu đường dẫn `bin`, version, vendor và `java.home` của các công cụ.
4. Dùng đường dẫn tuyệt đối để chạy cả bốn công cụ từ một JDK đã chọn.
5. Xác định lỗi do PATH, symlink/shim, runtime image thiếu module hoặc IDE/build tool dùng JDK khác.

## 2. Bốn công cụ có vai trò và cách hiển thị phiên bản khác nhau

| Lệnh | Vai trò | Cách xem phiên bản | Dấu hiệu cần kiểm tra |
|---|---|---|---|
| `java` | Khởi chạy JVM và ứng dụng Java | `java --version` | Runtime version, vendor, build |
| `javac` | Biên dịch mã nguồn Java thành class file | `javac --version` | Compiler version |
| `javadoc` | Tạo tài liệu HTML từ source và doc comment | `javadoc --version` | Phiên bản công cụ Javadoc |
| `jwebserver` | Chạy Simple Web Server để phục vụ tệp tĩnh | `jwebserver --version` | Phiên bản công cụ Simple Web Server |

Cả bốn công cụ thường nằm trong thư mục `bin` của cùng một JDK:

~~~text
jdk-25/
├── bin/
│   ├── java[.exe]
│   ├── javac[.exe]
│   ├── javadoc[.exe]
│   └── jwebserver[.exe]
├── conf/
├── include/
├── jmods/
└── lib/
~~~

Trên Windows, tên file thực thi thường có đuôi `.exe`; trên Linux/macOS thường không có đuôi. Các thành phần khác của cấu trúc JDK có thể thay đổi theo nền tảng và nhà phân phối.

`jwebserver` thuộc module JDK `jdk.httpserver`. Vì vậy, một custom runtime image được tạo bằng `jlink` có thể không chứa module này; thiếu lệnh không nhất thiết có nghĩa bản JDK đầy đủ bị hỏng.

**Quy tắc quan trọng:** Cần kiểm tra ba loại bằng chứng:

- **Đường dẫn thực thi:** shell đã tìm thấy file nào?
- **Thông tin phiên bản/runtime:** executable đó báo version, vendor và runtime home nào?
- **Khả năng sử dụng:** công cụ và module cần thiết có thực sự hiện diện, chạy được không?

Không một loại bằng chứng riêng lẻ nào thay thế được hai loại còn lại.

## 3. Hiểu đúng `PATH` và `JAVA_HOME`

### 3.1. `PATH` quyết định lệnh trần được gọi

Khi nhập:

~~~shell
java --version
~~~

shell hoặc hệ điều hành tìm executable `java` theo cơ chế phân giải lệnh và thứ tự các thư mục trong `PATH`. Với nhiều bản JDK, thư mục xuất hiện trước thường được ưu tiên.

Ví dụ:

~~~text
PATH:
  C:\Program Files\Java\jdk-17\bin
  C:\Program Files\Eclipse Adoptium\jdk-25\bin
  C:\Windows\System32
~~~

Lệnh `java` và `javac` có thể được lấy từ JDK 17 vì thư mục đó đứng trước JDK 25.

### 3.2. `JAVA_HOME` không tự điều khiển mọi lệnh

`JAVA_HOME` là biến môi trường mà nhiều IDE, build tool và script dùng để tìm JDK. Bản thân Java launcher không có nghĩa vụ tự chuyển sang `JAVA_HOME` khi người dùng gõ `java`. Lệnh trần vẫn được phân giải qua `PATH`.

Một cấu hình có thể mâu thuẫn:

~~~text
JAVA_HOME = C:\Program Files\Eclipse Adoptium\jdk-25
PATH      = C:\Program Files\Java\jdk-17\bin;...
~~~

Khi đó:

- Script đọc `JAVA_HOME` có thể gọi JDK 25.
- Terminal gõ `java` có thể chạy JDK 17.
- IDE có thể dùng một JDK thứ ba theo Project SDK.

Vì vậy, luôn kiểm tra **cả `JAVA_HOME`, `PATH` và đường dẫn thực của từng lệnh**.

### 3.3. Symlink, shim và version manager

Một số hệ thống không trỏ trực tiếp vào JDK:

- Linux có thể dùng `/usr/bin/java` trỏ qua `/etc/alternatives/java`.
- macOS có thể dùng launcher/shim hệ thống hoặc lựa chọn JDK qua `/usr/libexec/java_home`.
- Windows có thể có Oracle Java Path shim hoặc thư mục liên kết.
- SDKMAN, jenv, asdf, mise và các công cụ quản lý phiên bản có thể thay đổi PATH theo terminal hoặc project.

Khi đường dẫn đầu tiên trông khác `JAVA_HOME/bin`, đừng kết luận ngay đó là JDK khác. Hãy xem đích symlink/shim và xác minh runtime property `java.home`. Ngược lại, cũng đừng cho rằng hai đường dẫn khác nhau chắc chắn cùng một bộ cài chỉ vì chúng in ra cùng major version.

## 4. Kiểm tra trên Windows PowerShell

### 4.1. Liệt kê mọi lệnh mà PowerShell tìm thấy

Mở PowerShell và chạy:

~~~powershell
Get-Command java, javac, javadoc, jwebserver -All |
    Select-Object Name, CommandType, Source, Path
~~~

Lệnh này liệt kê tất cả kết quả phân giải trong PowerShell, bao gồm application và những command type khác như alias hoặc function. Nếu cùng tên có nhiều application, cần xem thứ tự và đường dẫn.

Tiếp theo dùng `where.exe` để liệt kê các executable theo PATH:

~~~powershell
where.exe java
where.exe javac
where.exe javadoc
where.exe jwebserver
~~~

**Lưu ý:** Trong PowerShell, `where` thường là alias của `Where-Object`. Gọi rõ `where.exe` để dùng tiện ích Windows.

Có thể kiểm tra riêng một đường dẫn đã tìm được:

~~~powershell
Get-Item 'C:\Program Files\Eclipse Adoptium\jdk-25\bin\java.exe' |
    Format-List FullName, LinkType, Target
~~~

Nếu file là symlink hoặc reparse point, xem thêm `LinkType` và `Target` khi PowerShell cung cấp. Một shim có thể chuyển tiếp sang executable ở nơi khác; hãy đối chiếu đích cuối cùng và runtime properties.

### 4.2. Kiểm tra `JAVA_HOME` và các thư mục PATH

~~~powershell
$env:JAVA_HOME
$env:Path -split ';'
~~~

Ví dụ `JAVA_HOME` nên trỏ vào thư mục gốc JDK:

~~~text
C:\Program Files\Eclipse Adoptium\jdk-25.0.x
~~~

Không trỏ trực tiếp vào thư mục `bin` nếu công cụ đang mong đợi JDK home. Thư mục chứa lệnh là `$env:JAVA_HOME\bin`.

### 4.3. Chạy cả bốn công cụ bằng đường dẫn tuyệt đối

Đây là cách trực tiếp để bảo đảm các lệnh trong phép kiểm tra đến từ **cùng thư mục JDK đã chọn**:

~~~powershell
$jdkHome = $env:JAVA_HOME
if (-not $jdkHome) {
    throw 'JAVA_HOME chưa được thiết lập.'
}

$bin = Join-Path $jdkHome 'bin'
$tools = @(
    'java.exe',
    'javac.exe',
    'javadoc.exe',
    'jwebserver.exe'
)

foreach ($tool in $tools) {
    $path = Join-Path $bin $tool
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Không tìm thấy $path"
    }
    Get-Item -LiteralPath $path |
        Select-Object FullName, Length
}
~~~

Sau đó gọi version bằng chính các đường dẫn đó:

~~~powershell
& (Join-Path $bin 'java.exe') --version
& (Join-Path $bin 'javac.exe') --version
& (Join-Path $bin 'javadoc.exe') --version
& (Join-Path $bin 'jwebserver.exe') --version
~~~

Vì các đường dẫn đều được ghép từ cùng `$jdkHome\bin`, phép kiểm tra này không phụ thuộc thứ tự PATH. Nếu một file không tồn tại, JDK hoặc runtime image đang chọn thiếu công cụ đó.

### 4.4. So sánh lệnh mặc định với JDK đã chọn

Sau khi chạy bằng đường dẫn tuyệt đối, kiểm tra xem lệnh trần có trỏ về cùng file hay không:

~~~powershell
$names = 'java', 'javac', 'javadoc', 'jwebserver'
foreach ($name in $names) {
    $resolved = Get-Command $name -ErrorAction Stop
    $expected = Join-Path $bin ($name + '.exe')

    [pscustomobject]@{
        Tool        = $name
        CommandType = $resolved.CommandType
        Resolved    = $resolved.Path
        Expected    = $expected
        SamePath    = ($resolved.CommandType -eq 'Application' -and
                       $resolved.Path -ieq $expected)
    }
}
~~~

Nếu `SamePath` là `False`:

- Có thể PATH đang ưu tiên một JDK khác.
- Có thể PowerShell đang gọi alias/function/wrapper.
- Có thể đường dẫn được chọn chứa symlink/shim nên cần kiểm tra target trước khi so sánh chuỗi path.

Kết quả `True` cho cả bốn là dấu hiệu tốt: các lệnh mặc định trỏ đến đúng executable trong JDK đã chọn. Với môi trường dùng symlink hoặc shim, kết hợp kiểm tra `java.home` và target để tránh kết luận sai do khác cách biểu diễn đường dẫn.

## 5. Kiểm tra trên Linux và macOS

### 5.1. Xem shell phân giải lệnh ở đâu

Dùng:

~~~shell
type -a java javac javadoc jwebserver
command -v java
command -v javac
command -v javadoc
command -v jwebserver
~~~

`type -a` giúp thấy alias, function và nhiều executable cùng tên tùy shell. `command -v` trả kết quả phân giải hiện tại. Trên Bash, nếu vừa đổi PATH mà shell vẫn nhớ vị trí cũ, chạy:

~~~shell
hash -r
~~~

Trong Zsh, có thể dùng `rehash` để làm mới command hash.

Trên Linux dùng GNU coreutils, có thể xem đường dẫn sau khi giải quyết symlink:

~~~shell
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
readlink -f "$(command -v javadoc)"
readlink -f "$(command -v jwebserver)"
~~~

`readlink -f` không phải tùy chọn chuẩn có mặt trên mọi hệ điều hành; macOS mặc định không cung cấp đúng hành vi GNU này. Trên macOS, xem các JDK đã cài bằng:

~~~shell
/usr/libexec/java_home -V
~~~

Sau đó chọn một JDK cụ thể trong phiên shell:

~~~shell
export JAVA_HOME="$(/usr/libexec/java_home -v 25)"
export PATH="$JAVA_HOME/bin:$PATH"
rehash
~~~

Đối với Linux, đặt `JAVA_HOME` thành thư mục JDK do package manager hoặc nhà phân phối cung cấp. Không sao chép một đường dẫn ví dụ của máy khác vì tên thư mục phụ thuộc vendor và bản build.

### 5.2. Chạy công cụ bằng đường dẫn từ `JAVA_HOME`

~~~shell
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"

"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/javac" --version
"$JAVA_HOME/bin/javadoc" --version
"$JAVA_HOME/bin/jwebserver" --version
~~~

Nếu cả bốn lệnh thành công, bạn đã xác nhận JDK được chỉ định có đủ các executable. Đây là phép kiểm mạnh hơn gọi lệnh trần vì shell không được chọn một bản khác qua PATH.

Có thể in thư mục thực mà shell phân giải:

~~~shell
for tool in java javac javadoc jwebserver; do
    printf '%-12s %s\n' "$tool" "$(command -v "$tool")"
done
~~~

Nếu dùng Linux, so sánh kết quả `readlink -f` của bốn lệnh với `$JAVA_HOME/bin` sau khi giải quyết symlink. Nếu dùng macOS, kết hợp `type -a`, `/usr/libexec/java_home -V` và runtime properties ở phần tiếp theo.

## 6. Đối chiếu version, vendor và runtime home

### 6.1. Version của bốn công cụ

Chạy các lệnh version từ JDK đã chọn:

~~~shell
java --version
javac --version
javadoc --version
jwebserver --version
~~~

Kết quả thường có major version tương ứng, ví dụ `25` hoặc `21`. Một số công cụ in thêm build/patch, một số công cụ chỉ in version ngắn. Không nên so sánh toàn bộ chuỗi bằng mắt rồi kết luận chỉ dựa trên cách định dạng.

Đối chiếu:

- Major version phải phù hợp với JDK dự kiến.
- Patch version nên tương ứng trong cùng một bộ build.
- Vendor/build/runtime version cần nhất quán khi công cụ cung cấp thông tin đó.
- Đường dẫn executable phải thuộc cùng JDK home hoặc có target đã được xác minh.

Nếu `java` là 25 nhưng `javac` là 21 thì môi trường không đồng bộ. Nếu cả hai là 25 nhưng một lệnh đến từ Temurin và lệnh khác đến từ Oracle JDK, chúng không thuộc cùng bộ phân phối dù cùng major.

### 6.2. Xem runtime properties của `java`

Chạy:

~~~shell
java -XshowSettings:properties -version
~~~

Trong phần output, chú ý:

| Property | Ý nghĩa |
|---|---|
| `java.home` | Runtime home mà JVM thực sự đang chạy sử dụng |
| `java.vendor` | Nhà cung cấp runtime |
| `java.version` | Phiên bản Java |
| `java.runtime.version` | Phiên bản runtime đầy đủ, thường chứa patch/build |
| `os.arch` | Kiến trúc CPU mà runtime báo cáo |

`java.home` đặc biệt hữu ích khi lệnh `java` là shim hoặc symlink: nó cho biết runtime home thực tế, không chỉ chuỗi lệnh người dùng đã gõ.

Trong JDK 9 trở lên, cấu trúc runtime đã thay đổi so với mô hình JRE riêng trong các bản cũ. Khi làm việc với JDK hiện đại, hãy xem `java.home` như đường dẫn runtime image đang được sử dụng và đối chiếu nó với bộ cài JDK đã chọn; đừng giả định mọi phiên bản đều có thư mục con `jre`.

### 6.3. Xem JVM chạy bên trong `javac` và `javadoc`

Hai công cụ này hỗ trợ tùy chọn `-J` để chuyển cờ trực tiếp cho JVM chạy công cụ. Vì thế có thể kiểm tra runtime version:

~~~shell
javac -J-version
javadoc -J-version
~~~

Hoặc xem các runtime properties:

~~~shell
javac -J-XshowSettings:properties -version
javadoc -J-XshowSettings:properties --version
~~~

Các dòng `java.home`, `java.vendor` và `java.runtime.version` từ JVM chạy compiler/doclet giúp phát hiện trường hợp wrapper hoặc môi trường gọi công cụ bằng một runtime khác.

Tài liệu công cụ xác nhận `javac -J` và `javadoc -J` chuyển tùy chọn tới runtime của chính công cụ. Không nhầm kết quả này với version của thư viện mà chương trình sẽ chạy trong production.

**Riêng `jwebserver`:** tool specification công khai `--version` để in version của công cụ, nhưng không nên tự giả định nó hỗ trợ mọi tùy chọn `-J` như `javac` và `javadoc`. Cách xác minh rõ ràng là gọi executable `jwebserver` bằng đường dẫn tuyệt đối trong cùng `JAVA_HOME/bin` và kiểm tra version.

### 6.4. Ví dụ bảng kết quả đạt

| Công cụ | Đường dẫn | Version | Kết luận |
|---|---|---|---|
| `java` | `.../jdk-25/bin/java` | `25.0.x` | Đúng bộ JDK |
| `javac` | `.../jdk-25/bin/javac` | `25.0.x` | Đúng bộ JDK |
| `javadoc` | `.../jdk-25/bin/javadoc` | `25.0.x` | Đúng bộ JDK |
| `jwebserver` | `.../jdk-25/bin/jwebserver` | `25.0.x` | Đúng bộ JDK |

Bảng này chỉ minh họa. Thay đường dẫn và version bằng output thực tế trên máy. Một kết quả đạt cần **cùng JDK home/đích đã chuẩn hóa**, các version phù hợp và các công cụ thực sự chạy được.

## 7. Kiểm tra module và khả năng sử dụng Simple Web Server

`jwebserver` là công cụ thuộc module JDK `jdk.httpserver`. Sau khi kiểm tra executable, xem module bằng:

~~~shell
java --describe-module jdk.httpserver
~~~

Hoặc liệt kê module:

~~~shell
java --list-modules
~~~

Trên Windows có thể lọc kết quả:

~~~powershell
& (Join-Path $bin 'java.exe') --list-modules |
    Select-String '^jdk\.httpserver@'
~~~

Trên Linux/macOS:

~~~shell
"$JAVA_HOME/bin/java" --list-modules | grep '^jdk\.httpserver@'
~~~

Nếu module không tồn tại trong runtime đang chạy, có thể đang dùng custom runtime image được tạo với tập module tối giản. Một bản JDK đầy đủ thường cung cấp module và lệnh tương ứng, nhưng một image runtime được cắt gọn có thể không có `jwebserver`.

Khi cần xác minh thực tế, chạy server trên một thư mục thử nghiệm có nội dung không nhạy cảm:

~~~shell
jwebserver -b 127.0.0.1 -p 8000 -d public
~~~

Trong terminal khác:

~~~shell
curl -I http://127.0.0.1:8000/
~~~

Sau đó dừng bằng `Ctrl+C`. `jwebserver` phục vụ tệp tĩnh qua HTTP/1.1, hỗ trợ `GET` và `HEAD`; không phải server production và không cung cấp HTTPS/HTTP/2. Phép thử này xác minh công cụ có thể khởi động và phục vụ tài nguyên trong môi trường hiện tại.

## 8. Đảm bảo IDE, Maven/Gradle và CI cũng dùng JDK dự kiến

Ngay cả khi bốn lệnh trong terminal nhất quán, dự án vẫn có thể build bằng một JDK khác.

### 8.1. IDE có thể có Project SDK riêng

Các IDE thường có ít nhất hai lựa chọn độc lập:

- JDK chạy chính IDE.
- JDK/SDK dùng để biên dịch và chạy project.

Chọn đúng **Project SDK**, **language level** và cấu hình run/debug. Sau đó kiểm tra output của task build và chạy một class nhỏ in `java.home`, `java.vendor` và `java.runtime.version`. Không suy ra Project SDK chỉ từ terminal đang mở bên ngoài IDE.

### 8.2. Maven và Gradle có thể dùng JDK riêng

Với Maven, xem:

~~~shell
mvn -version
~~~

Output thường chỉ ra Java version và Java home mà Maven đang chạy. Đồng thời kiểm tra compiler/toolchain configuration nếu project chọn JDK khác cho compile.

Với Gradle, xem:

~~~shell
gradle --version
~~~

Hoặc dùng wrapper của dự án:

~~~shell
./gradlew --version
~~~

Trên Windows:

~~~powershell
.\gradlew.bat --version
~~~

Gradle có thể dùng JVM để chạy daemon khác với toolchain dùng biên dịch source. Hãy kiểm tra cả **Gradle runtime JVM**, **Java toolchain**, cấu hình daemon và cấu hình IDE. Không coi output một lệnh version duy nhất là bằng chứng mọi task build đều dùng cùng JDK.

### 8.3. CI phải ghi lại phiên bản và đường dẫn

Trong pipeline, thêm bước diagnostic trước khi build:

~~~shell
java --version
javac --version
javadoc --version
jwebserver --version
java -XshowSettings:properties -version
~~~

Nếu pipeline dùng container hoặc runner có nhiều JDK, log thêm `JAVA_HOME`, vị trí executable và vendor. Ghim major version theo yêu cầu dự án, nhưng cập nhật patch theo chính sách bảo mật của nhà phân phối.

**Ví dụ:** Máy cá nhân có Temurin 25, CI dùng Oracle JDK 25, production dùng Corretto 21. Đây có thể là thiết kế hợp lệ nếu dự án kiểm thử đúng ma trận runtime và API target. Nhưng không được mô tả cả ba là “cùng một bộ JDK”. Chúng là các distribution/version khác nhau.

## 9. Các tình huống lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `java --version` là 25, `javac --version` là 17 | PATH đặt JDK 17 trước JDK 25 | Kiểm tra `where.exe`/`type -a`, chỉnh PATH hoặc gọi tuyệt đối |
| Cả bốn version là 25 nhưng path ở nhiều thư mục | Nhiều bản cài/vendor cùng major | Chọn một JDK home, gọi bốn file từ cùng `bin` |
| `JAVA_HOME` là 25 nhưng lệnh trần chạy 17 | JAVA_HOME không đồng nghĩa PATH | Đưa `JAVA_HOME/bin` lên trước PATH hoặc dùng đường dẫn tuyệt đối |
| `java.home` khác đường dẫn dự kiến | Shim, symlink, wrapper hoặc runtime image khác | Xem target và runtime properties, kiểm tra command resolution |
| `jwebserver` không được nhận diện | JDK thiếu tool, PATH sai hoặc runtime image bị cắt gọn | Kiểm tra `jdk.httpserver` và executable trong JDK home |
| `javadoc`/`javac` version đúng nhưng JVM tool khác | Wrapper hoặc cờ chạy tool làm thay đổi runtime | Dùng `-J-version`, `-J-XshowSettings:properties` |
| Terminal đúng nhưng IDE build sai | Project SDK khác terminal | Chỉnh Project SDK/toolchain và kiểm tra log build |
| Terminal đúng nhưng CI khác | Runner/container dùng image hoặc PATH khác | Khai báo JDK trong pipeline, log vendor/version/home |
| Hai lệnh in cùng version nhưng vendor khác | Cùng major không đồng nghĩa cùng distribution | Đối chiếu `java.vendor` và đường dẫn cài đặt |
| Sau khi đổi PATH vẫn thấy version cũ | Shell cache command hoặc terminal cũ | Mở terminal mới; Bash `hash -r`; Zsh `rehash` |

Không dùng cách sửa lỗi bằng cách xóa ngẫu nhiên các JDK khác. Có thể nhiều dự án cần nhiều major version. Chỉ cần chọn đúng JDK cho từng project và đảm bảo các lệnh của project đó được phân giải nhất quán.

## 10. Quy trình xác minh ngắn có thể lặp lại

Khi nhận một máy mới hoặc một CI runner, làm theo thứ tự:

1. **Ghi yêu cầu:** major JDK, vendor, OS/architecture, patch policy và công cụ cần có.
2. **Kiểm tra biến môi trường:** `JAVA_HOME`, `PATH`; xác định các version manager hoặc shim đang tham gia.
3. **Liệt kê lệnh được phân giải:** Windows dùng `Get-Command -All`/`where.exe`; Linux/macOS dùng `type -a`/`command -v`.
4. **Chọn JDK home cụ thể:** xác nhận thư mục cài đặt và các executable trong `bin`.
5. **Chạy tuyệt đối:** gọi `java`, `javac`, `javadoc`, `jwebserver` từ cùng `JAVA_HOME/bin`.
6. **So sánh version:** major, patch/build và vendor khi có.
7. **Kiểm tra runtime:** `java.home` của java; `-J-version` và `-J-XshowSettings:properties` của javac/javadoc.
8. **Kiểm tra module:** `jdk.httpserver` có trong runtime và `jwebserver` chạy được.
9. **Kiểm tra môi trường project:** IDE, build tool, CI, runtime image.
10. **Lưu biên bản:** version, vendor, đường dẫn, kết quả, ngày kiểm tra và những phần chưa xác minh.

Một bộ kiểm tra đạt có thể phát biểu chính xác:

> “Trong phiên terminal này, bốn executable được gọi trực tiếp từ thư mục `bin` của cùng JDK home. Các version phù hợp; runtime home/vendor của JVM và hai tool JVM đã được đối chiếu; module `jdk.httpserver` có mặt và `jwebserver` khởi động được.”

Không nên phát biểu rộng hơn như “mọi IDE, CI và production đều dùng cùng JDK” nếu chưa kiểm tra các môi trường đó.

## 11. Bài thực hành

### Bài 1 — Phát hiện PATH không đồng bộ

Cài hoặc dùng sẵn hai JDK khác major. Đặt JDK cũ trước JDK mới trong PATH. Chạy bốn lệnh version và liệt kê đường dẫn được phân giải.

**Tiêu chí đạt:** Giải thích được vì sao cài JDK mới chưa đủ; xác định đúng executable mà shell đang gọi.

### Bài 2 — Ép bốn công cụ dùng một JDK home

Đặt `JAVA_HOME` đến JDK mục tiêu. Gọi bốn executable qua đường dẫn tuyệt đối `JAVA_HOME/bin` (hoặc `JAVA_HOME\bin` trên Windows). So sánh version và đường dẫn với lệnh trần.

**Tiêu chí đạt:** Bốn lệnh chạy từ cùng JDK home; phát hiện được lệnh trần còn trỏ sang JDK khác nếu có.

### Bài 3 — Đối chiếu runtime home của công cụ

Chạy `java -XshowSettings:properties -version`, `javac -J-XshowSettings:properties -version` và `javadoc -J-XshowSettings:properties --version`. Ghi lại `java.home`, `java.vendor` và `java.runtime.version`.

**Tiêu chí đạt:** Giải thích được `-J` truyền tùy chọn vào JVM chạy công cụ; không giả định `jwebserver` hỗ trợ `-J` nếu tool specification không công bố.

### Bài 4 — Xác minh Simple Web Server

Kiểm tra `jwebserver --version`, module `jdk.httpserver`, sau đó chạy server loopback trên thư mục thử nghiệm và gửi yêu cầu HEAD.

**Tiêu chí đạt:** Phân biệt executable tồn tại với module/runtime thực sự có thể khởi chạy; biết server chỉ dành cho thử nghiệm tệp tĩnh.

### Bài 5 — Kiểm tra môi trường build

Mở dự án trong IDE, chạy Maven hoặc Gradle wrapper, so sánh JDK của build tool với JDK terminal. Ghi lại các khác biệt có chủ ý (nếu có).

**Tiêu chí đạt:** Không đồng nhất Project SDK, Gradle/Maven runtime và Java toolchain; biết xác định nơi cần chỉnh khi build sai JDK.

## 12. Mẫu biên bản kiểm tra môi trường

Có thể lưu mẫu sau trong báo cáo của dự án:

~~~text
Ngày kiểm tra:
Hệ điều hành / kiến trúc CPU:
JDK home dự kiến:
JAVA_HOME:
PATH (các thư mục JDK liên quan):
java command path:
javac command path:
javadoc command path:
jwebserver command path:
java version / vendor / runtime version:
javac version:
javac JVM home / vendor:
javadoc version:
javadoc JVM home / vendor:
jwebserver version:
jdk.httpserver có mặt:
IDE Project SDK:
Maven/Gradle JVM:
CI JDK:
Kết quả:
Các sai khác đã biết:
~~~

Biên bản có giá trị khi chứa output thực tế và ngày kiểm tra. Nếu JDK được cập nhật patch hoặc đổi vendor, chạy lại quy trình để xác nhận PATH, runtime và công cụ không bị trộn.

## 13. Tài liệu chính thức để tra cứu

- [The Java Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): tùy chọn launcher và cách xem thông tin runtime.
- [The Javac Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--version` và `-J` để chuyển tùy chọn tới JVM chạy compiler.
- [The Javadoc Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html): `--version`, `-J` và cách kiểm tra JVM chạy Javadoc.
- [The Jwebserver Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): `--version`, các tùy chọn bind/port/directory và giới hạn server.
- [Module jdk.httpserver — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): module cung cấp `jwebserver` và Simple Web Server API.
- [Java SE & JDK 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/): tra cứu module và API của đúng JDK.
- [JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): mục tiêu và phạm vi tính năng.
- [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): tính năng snippet trong standard doclet.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset.
- [JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418): resolver SPI.
- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi triển khai core reflection.

**Kết quả cuối cùng cần có:** Xác định được bốn executable, biết chúng được lấy từ đâu, chứng minh chúng thuộc cùng JDK home bằng đường dẫn và version/runtime properties, đồng thời xác nhận module/công cụ cần thiết thực sự hoạt động. Đây là nền tảng để thực hành các thay đổi Java 18 trên một JDK hiện đại mà không bị nhầm lẫn giữa nhiều bản cài.
