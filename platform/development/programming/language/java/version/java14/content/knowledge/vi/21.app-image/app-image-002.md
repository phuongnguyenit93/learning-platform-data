# Chọn input, main JAR và main class khi tạo app image bằng jpackage

## 1. Bài toán và ba tùy chọn quan trọng nhất

**Application image (app image)** là bộ thư mục/bundle ứng dụng Java có launcher native, dữ liệu ứng dụng và Java runtime phù hợp để chạy trên hệ điều hành đích. Công cụ **`jpackage`** tạo app image từ chương trình Java đã build. Với ứng dụng **non-modular chạy bằng classpath**, ba lựa chọn cốt lõi là:

- **`--input`**: thư mục chứa file ứng dụng sẽ được **đưa vào image**. Không phải đường dẫn file JAR.
- **`--main-jar`**: file JAR chính chứa mã khởi động, chỉ định bằng **đường dẫn tương đối so với thư mục `--input`**.
- **`--main-class`**: tên lớp Java đầy đủ (fully qualified class name) cần gọi khi chạy launcher. Có thể không truyền khi main JAR có thuộc tính `Main-Class` hợp lệ trong manifest.

Cùng với ba tùy chọn trên, thường dùng `--type app-image` để yêu cầu image thay vì trình cài đặt hệ điều hành, `--name` đặt tên ứng dụng và `--dest` chọn thư mục kết quả.

Ví dụ cho một ứng dụng Java console trên Windows, viết lệnh PowerShell trên **một dòng**:

~~~powershell
jpackage --type app-image --name HelloBundle --input input --main-jar hello.jar --main-class com.example.app.Main --dest output --win-console
~~~

Lệnh này **không** tự biên dịch `Main.java`, không tự tải thư viện còn thiếu và không đọc cấu hình dự án Maven/Gradle. Trước khi chạy, bạn cần build được JAR và chuẩn bị đúng thư mục `input`.

**Phiên bản hiện hành:** `jpackage` trở thành công cụ chính thức từ **JDK 16 (JEP 392)** và vẫn được duy trì trong JDK hiện đại. Bài thuộc module Java 14 nhưng chỉ dùng cách đóng gói còn áp dụng hiện nay. Ví dụ mã nguồn dùng **Java 17+**, không dựa vào preview/incubator, cờ mở khóa JFR hay hướng dẫn legacy.

## 2. Phân biệt các khái niệm dễ bị lẫn

Giả sử có dự án:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
├── classes/
│   └── com/example/app/Main.class
├── input/
│   ├── hello.jar
│   ├── helper.jar
│   └── config/
│       └── defaults.properties
└── output/
~~~

Trong trường hợp này:

1. `src/` là mã nguồn Java. `jpackage` không lấy nguồn `.java` để tự biên dịch.
2. `classes/` chứa file `.class` do `javac` tạo ra; thường chỉ là trung gian trước khi dùng `jar` đóng gói.
3. `input/` là **thư mục staging** dành riêng cho artifact phát hành. Mọi tệp nằm trong đó sẽ được đóng vào image. Đừng đặt thư mục output bên trong input.
4. `hello.jar` là **main JAR** và phải chứa `com/example/app/Main.class`. Tên truyền cho `--main-jar` sẽ là `hello.jar`.
5. `helper.jar` có thể là dependency; nó không phải main JAR chỉ vì cùng có phần mở rộng `.jar`.
6. `com.example.app.Main` là **tên lớp Java**, khác với tên file `Main.java`, tên đường dẫn `com/example/app/Main.class` và tên image `HelloBundle`.
7. `output/` là nơi nhận image đã tạo. Nó được chọn bằng `--dest`, **không phải** bằng `--input`.

### Bảng tra cứu nhanh

| Tùy chọn | Giá trị ví dụ | Công dụng |
|---|---|---|
| `--type` | `app-image` | Chọn đầu ra là application image |
| `--name` | `HelloBundle` | Đặt tên ứng dụng và launcher theo nền tảng |
| `--input` | `input` | Chỉ thư mục payload cần đóng gói |
| `--main-jar` | `hello.jar` | Chọn JAR chứa main class, đường dẫn tính từ `input` |
| `--main-class` | `com.example.app.Main` | Chọn class chạy khi mở launcher |
| `--dest` | `output` | Thư mục nhận image |
| `--win-console` | Cờ không có giá trị | Tạo launcher console trên Windows để thấy stdout/stderr |

**Quy tắc ghi nhớ:** `--input` = những tệp nào, `--main-jar` = JAR nào, `--main-class` = class nào.

## 3. Chọn thư mục --input đúng và an toàn

### 3.1. Input là thư mục, không phải file JAR

**Đúng:**

~~~powershell
jpackage --type app-image --name Demo --input .\input --main-jar app.jar --main-class com.example.Main --dest .\output --win-console
~~~

Ví dụ trên giả định có `input/app.jar` chứa `com.example.Main`. Nếu đổi thành `--input .\input\app.jar` thì giá trị truyền cho `--input` không còn là thư mục. Nếu truyền `--main-jar input/app.jar` trong khi đã dùng `--input input`, bạn có thể khiến công cụ tìm sai vị trí vì `--main-jar` phải **tương đối với input**.

### 3.2. Main JAR có thể nằm ở thư mục con

Khi cấu trúc là:

~~~text
input/
└── bin/
    └── hello.jar
~~~

có thể viết:

~~~powershell
jpackage --type app-image --name NestedDemo --input input --main-jar bin/hello.jar --main-class com.example.app.Main --dest output --win-console
~~~

Đây là lệnh **minh họa**: chỉ chạy được nếu JAR thật sự nằm ở `input/bin/hello.jar` và chứa lớp được chọn. Không tự nối thêm tiền tố `input/` vào giá trị `--main-jar`.

### 3.3. Staging folder nên có gì?

`--input` nên chứa chính xác những artifact ứng dụng cần lúc chạy:

- Main JAR hoặc executable JAR tương thích với launcher của Java.
- Những JAR runtime dependencies cần thiết, nếu chưa được đóng vào một fat JAR.
- Tài nguyên ngoài JAR mà ứng dụng đọc bằng đường dẫn file, nếu được phép phân phối.
- Những tệp phụ trợ nhỏ cần thiết cho chức năng ứng dụng.

**Không nên** đặt cả project root làm input. Nếu `--input .` và thư mục hiện tại có `.git`, secrets, tests, build cache, source code, JDK khác, output cũ hoặc file nội bộ, các tệp đó có thể bị đưa vào image, làm tăng dung lượng và gây nguy cơ lộ thông tin. Dùng thư mục staging tách riêng là cách đơn giản và dễ kiểm toán.

**Nhớ:** `jpackage` không tự chạy `mvn package`, `gradle build` và không tải Maven dependencies. Phải build xong và copy các JAR/tài nguyên cần thiết vào input trước.

### 3.4. Tài nguyên ngoài JAR và classpath

Việc `input/config/defaults.properties` được copy vào image **không đồng nghĩa** `ClassLoader.getResourceAsStream("config/defaults.properties")` tự động tìm thấy file ngoài JAR. Classloader tìm theo classpath/module path, còn file ngoài JAR cần đường dẫn file phù hợp với cấu trúc image và cách launcher xác định app directory.

Nếu tài nguyên nên được đọc bằng classloader, đóng tài nguyên đó **vào JAR/classpath**. Nếu tài nguyên cần tùy chỉnh sau phát hành, đọc bằng file API và thiết kế đường dẫn độc lập với current working directory. Cần kiểm tra thực tế vì người dùng có thể chạy launcher từ một thư mục bất kỳ.

## 4. Chọn main JAR: file khởi động chứ không phải mọi file .jar

Đối với app không dùng JPMS, `--main-jar` chọn file chứa lớp khởi động. Nếu `input/` có:

~~~text
input/
├── hello.jar
├── logging.jar
└── database-driver.jar
~~~

và class `com.example.app.Main` nằm trong `hello.jar`, lựa chọn phù hợp là:

~~~text
--input input --main-jar hello.jar
~~~

`logging.jar` và `database-driver.jar` là thư viện hỗ trợ. Không chọn một dependency làm main JAR chỉ vì file của nó đứng đầu theo bảng chữ cái.

### Main JAR không nhất thiết là JAR duy nhất

Một ứng dụng classpath có thể dùng nhiều JAR. Theo tài liệu `jpackage`, payload input chứa các JAR cần thiết và launcher non-modular được tạo với classpath tương ứng. Tuy nhiên, nếu bạn cố tình đặt `-cp`, `--classpath` hoặc `-Djava.class.path` qua `--java-options`, các thiết lập riêng có thể ghi đè classpath mặc định; phải bảo đảm mọi dependency vẫn được chỉ ra đúng.

Nếu dùng **fat/uber JAR**, các dependency có thể đã được gộp trong một file. Nhưng **JAR được framework tạo ra có thể cần bootstrap/main class riêng của framework**; không nên tự thay launcher của framework bằng class ứng dụng rồi tin các cơ chế nạp class đặc thù vẫn hoạt động.

### Kiểm tra JAR trước khi đóng image

~~~powershell
jar --list --file .\input\hello.jar
java -jar .\input\hello.jar
~~~

Lệnh `jar --list` giúp kiểm tra JAR có đúng `com/example/app/Main.class` và `META-INF/MANIFEST.MF` không. Lệnh `java -jar` chỉ chạy được khi manifest đã có `Main-Class` phù hợp và app có đủ dependency. Nếu chưa tạo manifest nhưng biết class, có thể chạy `java -cp .\input\hello.jar com.example.app.Main` với ứng dụng một JAR không có dependency ngoài.

**Nếu ứng dụng chưa khởi động được bằng Java trước khi package, jpackage không phải công cụ sửa lỗi dependency hoặc main class.**

## 5. Chọn main class và quan hệ với JAR manifest

Lớp Java ví dụ:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from packaged Java!");
        System.out.println("arguments=" + args.length);
    }
}
~~~

Tên sử dụng với `--main-class` là **`com.example.app.Main`**.

| Giá trị | Có đúng không? | Giải thích |
|---|---|---|
| `com.example.app.Main` | Đúng | Tên lớp đầy đủ theo package |
| `Main.java` | Sai | Tên file nguồn, không phải tên class |
| `com/example/app/Main.class` | Sai | Đường dẫn entry trong JAR |
| `Main` | Thường sai ở ví dụ này | Thiếu package |
| `com.example.app.main` | Sai | Java phân biệt chữ hoa và chữ thường |
| `HelloBundle` | Sai | Đây là tên image/launcher, không phải class Java |

Trong mô hình khởi động truyền thống, class có phương thức `public static void main(String[] args)`. `String... args` là cú pháp varargs tương đương về tham số JVM cho phương thức này.

### Khi nào cần --main-class tường minh?

Nếu JAR **không có thuộc tính `Main-Class` trong manifest**, hãy chỉ định `--main-class`. Nếu JAR **đã có `Main-Class` hợp lệ**, `jpackage` có thể lấy tên lớp từ manifest nên `--main-class` là tùy chọn.

Manifest ví dụ:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
~~~

Khi dùng công cụ `jar` của JDK, có thể tạo thuộc tính này bằng:

~~~powershell
jar --create --file .\input\hello.jar --main-class com.example.app.Main -C .\classes .
~~~

Lệnh `jar --main-class` ở đây **đưa tên main class vào manifest của JAR**. Đừng nhầm nó với tham số `jpackage --main-class`, tuy chúng cùng diễn đạt lựa chọn lớp khởi động.

### Hai cách đóng gói hợp lệ

**Có --main-class tường minh:**

~~~powershell
jpackage --type app-image --name HelloBundle --input input --main-jar hello.jar --main-class com.example.app.Main --dest output --win-console
~~~

**Không có --main-class vì JAR có manifest Main-Class:**

~~~powershell
jpackage --type app-image --name ManifestBundle --input input --main-jar hello.jar --dest output --win-console
~~~

Cách thứ hai đã được chạy thử thực tế: khi manifest đúng, launcher vẫn chạy chương trình. Nếu manifest sai hoặc thiếu, cách bỏ `--main-class` không phải phép đoán tự động lớp Java có phương thức `main`.

**`--name` không thay thế `--main-class`**. Tên app có thể là `HelloBundle` trong khi main JAR là `hello.jar` và class là `com.example.app.Main`.

## 6. Ví dụ Java 17+ đầy đủ: từ source tới app image

Ví dụ này sử dụng **PowerShell trên Windows** để kiểm chứng console launcher, vì `--win-console` giúp nhìn thấy stdout. Trên Linux/macOS, tham số tạo image cốt lõi giống nhau nhưng bỏ `--win-console` và chạy launcher theo layout OS.

### Bước 1. Chuẩn bị thư mục

Ở một thư mục dự án mới:

~~~powershell
New-Item -ItemType Directory -Force -Path .\src\com\example\app, .\classes, .\input, .\output | Out-Null
~~~

Không đặt `output` bên trong `input`.

### Bước 2. Tạo file Main.java

Lưu mã sau vào **`src/com/example/app/Main.java`**:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from packaged Java!");
        System.out.println("arguments=" + args.length);
    }
}
~~~

Đây là **chương trình Java hoàn chỉnh**. Nó không dùng thư viện ngoài, nên việc xác định main JAR rất rõ ràng.

### Bước 3. Biên dịch cho Java 17

~~~powershell
javac --release 17 -d .\classes .\src\com\example\app\Main.java
~~~

Với `package com.example.app;`, file được tạo ở `classes/com/example/app/Main.class`.

`--release 17` kiểm tra cú pháp và API theo target Java 17, đồng thời tạo class file thích hợp với Java 17. **Nó không ép jpackage phải đóng gói runtime Java 17** nếu công cụ `jpackage` đang chạy từ JDK phiên bản khác.

### Bước 4. Tạo JAR executable

~~~powershell
jar --create --file .\input\hello.jar --main-class com.example.app.Main -C .\classes .
~~~

Ý nghĩa các phần:

- `--create`: tạo JAR.
- `--file .\input\hello.jar`: đưa JAR vào đúng input staging.
- `--main-class com.example.app.Main`: tạo manifest `Main-Class`.
- `-C .\classes .`: đưa nội dung biên dịch vào JAR, giữ đúng đường dẫn của package.

Thử chạy trực tiếp:

~~~powershell
java -jar .\input\hello.jar
~~~

**Standard output:**

~~~text
Hello from packaged Java!
arguments=0
~~~

Nếu lệnh này thất bại, sửa vấn đề class/manifest trước khi tạo native launcher.

### Bước 5. Tạo app image với jpackage

~~~powershell
jpackage --type app-image --name HelloBundle --input .\input --main-jar hello.jar --main-class com.example.app.Main --dest .\output --win-console
~~~

`jpackage` lấy JAR từ `input`, xây launcher native và đưa một runtime image phù hợp vào application image. `--win-console` dành cho chương trình console trên Windows; không dùng trên Linux/macOS.

### Bước 6. Chạy launcher native

~~~powershell
.\output\HelloBundle\HelloBundle.exe
~~~

**Standard output từ launcher image:**

~~~text
Hello from packaged Java!
arguments=0
~~~

Quy trình `javac --release 17` → `jar --main-class` → `jpackage --type app-image` → chạy `HelloBundle.exe` đã được **biên dịch và thử thực tế thành công** trên JDK hiện đại chạy Windows. Cùng một ví dụ đã kiểm tra việc bỏ `--main-class` khi manifest có Main-Class.

### Kết cấu output trên Windows

Một layout điển hình:

~~~text
output/
└── HelloBundle/
    ├── HelloBundle.exe
    ├── app/
    │   ├── HelloBundle.cfg
    │   └── hello.jar
    └── runtime/
        └── ... file Java runtime ...
~~~

Đây là sơ đồ đại diện, không mô tả mọi file nội bộ mà công cụ có thể tạo thêm. Tên/thư mục cụ thể phụ thuộc OS và JDK/vendor. **Không copy riêng `HelloBundle.exe` mà bỏ `app` và `runtime`**: launcher cần các phần còn lại của image.

### Bước 7. Thử cơ chế manifest inference

Vì JAR đã có `Main-Class` hợp lệ, có thể tạo một image khác:

~~~powershell
jpackage --type app-image --name ManifestBundle --input .\input --main-jar hello.jar --dest .\output --win-console
.\output\ManifestBundle\ManifestBundle.exe
~~~

Hai lệnh PowerShell trên là một chuỗi thực hiện sau bước build JAR. Launcher thứ hai vẫn gọi `com.example.app.Main`. **Không cần tự sao chép manifest bằng tay nếu đã dùng `jar --main-class`**.

## 7. Tương đương trên Linux và macOS

Với Bash trên Linux, sau khi đã lưu cùng file `Main.java` như ở phần 6:

~~~bash
mkdir -p src/com/example/app classes input output
javac --release 17 -d classes src/com/example/app/Main.java
jar --create --file input/hello.jar --main-class com.example.app.Main -C classes .
jpackage --type app-image --name HelloBundle --input input --main-jar hello.jar --main-class com.example.app.Main --dest output
./output/HelloBundle/bin/HelloBundle
~~~

Lệnh minh họa **cần JDK có jpackage** và file source tồn tại. Trên Linux, launcher thường nằm ở `bin/HelloBundle` bên trong image. Trên macOS, image thường là bundle `HelloBundle.app` và launcher nằm ở `Contents/MacOS/HelloBundle`. Các yêu cầu ký ứng dụng/notarization khi phân phối macOS là vấn đề phát hành riêng.

**Không hỗ trợ đóng chéo nền tảng trực tiếp:** jpackage tạo native launcher/package theo hệ điều hành mà nó đang chạy. Muốn phát hành cho Windows, Linux và macOS, cần xây và kiểm thử artifact cho các target OS/kiến trúc tương ứng.

## 8. Khi dùng modular app: phải chuyển sang --module

Các tùy chọn `--input`/`--main-jar`/`--main-class` là con đường non-modular. Nếu ứng dụng dùng **Java Platform Module System (JPMS)** với `module-info.java` và artifact modular, nên chọn:

~~~bash
jpackage --type app-image --name ModularDemo --module-path mods --module com.example.app/com.example.app.Main --dest output
~~~

Đoạn này **minh họa** cho module `com.example.app` đã build trong `mods`.

- `--module-path` cho biết nơi có module ứng dụng và module dependencies.
- `--module com.example.app/com.example.app.Main` chỉ main module, kèm tên main class sau dấu `/`.
- `--main-jar` và `--module` là **hai cách chọn điểm vào thay thế nhau**, không cùng chỉ định cho launcher chính.
- `--main-class` của jpackage đi cùng `--main-jar`, không dùng để thay phần `/mainClass` của `--module`.

Không có lý do phải chuyển ứng dụng classpath đơn giản sang JPMS chỉ để gọi jpackage. Chọn cách phù hợp với artifact thực tế.

### So sánh ngắn

| Loại ứng dụng | Tùy chọn điểm vào | Nguồn file/module |
|---|---|---|
| Classpath, non-modular | `--main-jar app.jar` và tùy chọn `--main-class pkg.Main` | `--input input` |
| JPMS modular | `--module moduleName/pkg.Main` | `--module-path mods` |

Bảng này mô tả launcher chính. Việc tạo thêm launcher phụ qua `--add-launcher` là chủ đề cấu hình nâng cao, không làm thay đổi nguyên tắc chọn điểm vào.

## 9. App image không giống runtime image hoặc installer

| Thuật ngữ | Mục đích | Tạo bởi |
|---|---|---|
| **App image** | Bundle có launcher, payload Java và runtime phù hợp | `jpackage --type app-image` |
| **Runtime image** | Java runtime đã cấu hình module, chưa tự là app launcher hoàn chỉnh | `jlink` |
| **Native installer** | Gói cài đặt native như `exe/msi/deb/rpm/pkg/dmg` | `jpackage --type ...` theo OS |

**Đừng nhầm:**

- `--type app-image` chọn **loại output mới** cần tạo.
- `--app-image directory` nhận **application image đã tạo trước** làm input để xây installer hoặc thực hiện thao tác phù hợp trên image có sẵn.

### Runtime được tạo ra sao?

Nếu không cung cấp `--runtime-image`, `jpackage` dùng `jlink` để tạo runtime đi kèm. Người dùng cuối thường **không cần tự cài JDK riêng** để chạy image, nhưng image vẫn phải phù hợp hệ điều hành và CPU architecture. Nếu truyền một runtime tự tạo:

~~~bash
jpackage --type app-image --name HelloBundle --input input --main-jar hello.jar --main-class com.example.app.Main --runtime-image custom-runtime --dest output
~~~

thì `custom-runtime` phải đã tồn tại và có các module cần thiết. Nếu cắt bỏ nhầm module như `java.sql`, `java.desktop` hoặc thành phần mã hóa mà ứng dụng sử dụng, launcher có thể lỗi dù jpackage tạo image xong.

**Không giả định mọi JDK tạo cùng runtime module graph mặc định.** Một số hành vi liên quan service binding của jlink/jpackage thay đổi giữa các JDK release mới; hãy xác nhận bằng `jpackage --help` của JDK dùng build và chạy thử image đã đóng.

## 10. Dự án Maven/Gradle và nhiều dependency

Với dự án thực, thường không đóng gói trực tiếp `target/` hoặc `build/` toàn bộ. Một quy trình có thể là:

1. Chạy build và test bằng Maven/Gradle.
2. Tạo main JAR tương thích với launcher. Xác minh class chính, manifest và thư viện phụ thuộc.
3. Copy các artifact runtime được phép phát hành vào staging folder `input/`.
4. Chạy thử ứng dụng bằng `java -jar` hoặc `java -cp` trong môi trường có đúng dependencies.
5. Gọi `jpackage --type app-image` và chỉ rõ main JAR/main class hoặc JPMS module.
6. Chạy thử native launcher ở chính OS build, kiểm tra arguments, config, tài nguyên, file permissions.
7. Khi image đã ổn định mới cân nhắc tạo installer native và ký ứng dụng theo quy trình phát hành.

Một build có thể tạo nhiều file: `app-1.0.jar`, `app-1.0-tests.jar`, `app-1.0-sources.jar`, `app-1.0-javadoc.jar`. **Không dùng tên artifact chung để đoán main JAR**; phải chọn file chứa code khởi động thực và dependency runtime.

### Fat JAR theo framework có thể khác JAR Java thông thường

Một số framework tạo archive có Main-Class là **bootstrap loader** và metadata riêng xác định application start class. Nếu override `--main-class` sang lớp ứng dụng thông thường, có thể bỏ qua cơ chế nạp nested JAR của framework. Hãy biết kiểu artifact build ra, thử cách launcher tương thích trước, rồi chọn jpackage flags tương ứng.

### Cẩn thận với --java-options

`--java-options` dùng để truyền tham số JVM, có thể chứa `-D...`, `--add-opens` hay classpath tùy ứng dụng. Nếu bạn tự chỉ định `-cp` hoặc `-Djava.class.path`, bạn có thể **ghi đè classpath mặc định** do jpackage tạo và làm rơi thư viện cần thiết. Chỉ custom classpath khi thực sự cần và kiểm tra lại trên image.

## 11. Các lỗi thường gặp và hướng khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Báo không tìm được main JAR | `--main-jar` không tương đối đúng với `--input` | Kiểm tra đường dẫn bên trong staging folder |
| `--input` trỏ vào file `.jar` | Tham số yêu cầu thư mục | Đổi thành đường dẫn thư mục chứa JAR |
| Không có main class | Manifest thiếu `Main-Class`, cũng không truyền `--main-class` | Tạo manifest hoặc truyền tên lớp |
| `ClassNotFoundException` | Sai package/class name, class không ở main JAR hoặc classpath sai | Dùng `jar --list` và kiểm tra classpath |
| `NoClassDefFoundError` lúc chạy | Thiếu JAR runtime dependency hoặc module runtime | Thêm dependency và chạy thử launcher |
| Lỗi file cấu hình khi chạy image | Resource path dựa sai vào working directory | Thiết kế đường dẫn app directory, đưa resource đúng chỗ |
| Không thấy stdout trên Windows | Launcher không phải console | Thêm `--win-console` khi đóng gói ứng dụng dòng lệnh |
| Image quá lớn | Input chứa tệp build, source, test và cache không cần thiết | Chỉ staging tệp runtime |
| App chạy bằng `java -jar` nhưng launcher lỗi | Khác biệt trong cách launcher dựng classpath/config | Kiểm tra Main-Class, --main-class, --java-options, dependency |
| Đưa cả `--module` và `--main-jar` | Hai cách chọn điểm vào xung đột | Chọn một mô hình modular hoặc non-modular |
| Dùng `--app-image` để yêu cầu tạo image | Nhầm input image với output type | Chọn `--type app-image` |
| Chỉ copy `HelloBundle.exe` sang máy khác | Thiếu runtime và tệp payload | Phân phối nguyên image/bundle |
| Chạy image trên OS khác | Native launcher khác nền tảng | Package riêng trên target OS/architecture |
| Không có lệnh `jpackage` | PATH/JDK không phù hợp | Dùng JDK hiện đại có jpackage, kiểm tra `jpackage --version` |
| Folder có khoảng trắng gây parse lỗi | Shell không quote đường dẫn đúng | Dùng quote cho path có khoảng trắng |
| Custom runtime bị thiếu module | `jlink` loại nhầm module ứng dụng dùng | Bổ sung module và chạy test image |

### Trình tự kiểm tra khi launcher không khởi động

1. `input` là thư mục thật và không chứa file nội bộ không mong muốn?
2. `--main-jar` đang trỏ đúng file trong input?
3. Main JAR có class `com/example/app/Main.class` không?
4. Manifest có `Main-Class` hợp lệ hoặc jpackage được truyền đúng `--main-class`?
5. `java -jar` / `java -cp` chạy được trong môi trường có đầy đủ dependency?
6. `jpackage --type app-image` tạo ra đủ launcher, app payload và runtime?
7. Có custom `--java-options` vô tình ghi đè classpath không?
8. Có chạy launcher trên đúng OS và thử từ working directory khác không?
9. Lỗi chi tiết trong `jpackage --verbose` có xác nhận nguyên nhân cần sửa không?

**Không giải quyết bằng cách sửa tay ngẫu nhiên file `.cfg` trong image rồi phát hành mà không kiểm thử lại**. Ưu tiên sửa pipeline và tái tạo artifact để kết quả có thể tái lập.

## 12. Quy tắc về an toàn và phát hành

Đầu vào của jpackage có thể chứa dữ liệu mà lập trình viên không định phát hành. Vì **mọi file trong input được đóng vào image**, cần review nguồn tệp:

- Loại credential, token, file cấu hình chứa bí mật và dữ liệu cá nhân.
- Tránh gom vào source code, test fixture, build cache, thư mục version control không cần thiết.
- Xác minh quyền phân phối các dependency và Java runtime được sử dụng.
- Kiểm tra bảo mật và tính toàn vẹn của artifact phát hành theo chính sách đội ngũ.
- Không đặt output vào bên trong input để tránh vô tình đóng lại image cũ.
- Đóng gói riêng theo OS/architecture; test bằng một môi trường tương tự máy người dùng, không phụ thuộc JDK đã cài trên máy phát triển.
- Nếu cần code signing/notarization, shortcut, registry/file association hoặc installer tự động, xử lý theo cơ chế `jpackage` dành cho từng OS; app image thuần **không tự thực hiện mọi bước phân phối**.

**Lưu ý thực dụng:** image có launcher native không phải một executable Java độc lập chứa tất cả trong một file duy nhất. Phải giao đúng **toàn bộ bundle** theo cấu trúc được jpackage tạo.

## 13. Checklist trước khi giao app image

- [ ] Đã chọn đúng chế độ non-modular JAR hay modular module.
- [ ] `--input` trỏ tới **thư mục staging**.
- [ ] Không có credential, source, test/build cache không cần phát hành trong input.
- [ ] Main JAR tồn tại **tương đối với input** như `--main-jar` khai báo.
- [ ] Main JAR chứa class với tên package chính xác.
- [ ] `Main-Class` trong manifest hợp lệ hoặc đã truyền `--main-class` tường minh.
- [ ] Các JAR phụ thuộc và resource được đặt đúng cách.
- [ ] Ứng dụng đã chạy được trước khi package, với cùng runtime dependencies.
- [ ] `--type app-image` được sử dụng để thử image trước installer.
- [ ] `--dest` không nằm trong `--input`.
- [ ] Có `--win-console` khi cần console trên Windows; bỏ cờ này trên OS khác.
- [ ] Runtime image đủ module mà ứng dụng cần.
- [ ] Native launcher chạy được ngay trong image đã tạo.
- [ ] Thử từ working directory khác để phát hiện sai resource path.
- [ ] Đã chạy test trên OS/architecture cần phát hành.
- [ ] Đã bảo toàn nguyên folder/bundle khi chuyển image sang môi trường khác.

## 14. Bài tập tự kiểm tra

**Câu 1.** `input/hello.jar` chứa main class; `input/helper.jar` là thư viện. Chọn `--input` và `--main-jar` như thế nào?

**Đáp án:** `--input input --main-jar hello.jar`. `helper.jar` là dependency; nó không thay thế main JAR.

**Câu 2.** Class khai báo `package com.example.app; public class Main`. Có nên truyền `--main-class Main.java`?

**Đáp án:** Không. Tên đúng là `com.example.app.Main`, không có hậu tố `.java` hoặc `.class`.

**Câu 3.** Khi manifest có `Main-Class: com.example.app.Main`, `--main-class` có bắt buộc không?

**Đáp án:** Không. jpackage có thể lấy main class từ manifest. Tuy nhiên việc khai báo tường minh vẫn có giá trị khi muốn kiểm soát điểm khởi động và biết chắc đường dẫn class.

**Câu 4.** Vì sao `--main-jar input/hello.jar` dễ sai khi `--input input`?

**Đáp án:** Đường dẫn của main JAR đã được diễn giải từ thư mục input. Nếu file nằm ngay `input/hello.jar`, chỉ cần `--main-jar hello.jar`.

**Câu 5.** `--type app-image` và `--app-image` có giống nhau không?

**Đáp án:** Không. `--type app-image` là **loại đầu ra**, còn `--app-image` nhận **app image có sẵn** làm đầu vào cho một nhiệm vụ đóng gói khác.

**Câu 6.** Có thể đặt `--module com.example.app/...` cùng `--main-jar hello.jar` cho launcher chính không?

**Đáp án:** Không. Hai cách này chọn điểm khởi động theo hai mô hình khác nhau. Chọn `--module` cho JPMS hoặc `--main-jar` cho classpath app.

**Câu 7.** Nếu có app image Windows, chỉ copy launcher `.exe` sang Linux có chạy được không?

**Đáp án:** Không. Image có launcher và runtime phụ thuộc OS; cần package trên nền tảng đích và chuyển toàn bộ bundle.

**Câu 8.** Tại sao không nên dùng thư mục project root làm `--input`?

**Đáp án:** Mọi tệp trong đó có thể bị đóng gói, kể cả secrets, source, cache và file test. Staging directory sạch là lựa chọn an toàn hơn.

**Câu 9.** `--name HelloBundle` có khiến main class tự trở thành `HelloBundle` không?

**Đáp án:** Không. Tên launcher/image và tên lớp Java là hai khái niệm độc lập.

**Câu 10.** Vì sao image có thể chạy trên máy build nhưng lỗi trên máy thử nghiệm?

**Đáp án:** Các nguyên nhân có thể là OS/architecture khác, resource path lệch, runtime thiếu module, dependency không được đóng vào image hoặc quyền filesystem khác. Phải thử trên môi trường mục tiêu thay vì chỉ nhìn việc jpackage hoàn tất.

## 15. Tài liệu tham khảo

- [Java SE 17 — The jpackage Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): định nghĩa `--input`, `--main-jar`, `--main-class`, `--module` và tạo `app-image`.
- [Java SE 17 — Basic Packaging](https://docs.oracle.com/en/java/javase/17/jpackage/basic-packaging.html): cách chọn main class từ manifest, non-modular và modular app.
- [Java SE 25 — Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): layout image, runtime đi kèm và quan hệ giữa image/installer.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): jpackage chính thức từ JDK 16.
- [Java SE 17 — jar Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): tạo main JAR và manifest bằng `--main-class`.
- [OpenJDK — jpackage Tool Guide đang phát triển](https://github.com/openjdk/jdk/blob/master/src/jdk.jpackage/share/man/jpackage.md): danh mục tùy chọn của JDK mới; đối chiếu thêm `jpackage --help` trên đúng JDK build.

**Tóm tắt:** Với app image non-modular, chọn **`--input` = thư mục payload**, **`--main-jar` = file JAR khởi động bên trong input**, **`--main-class` = lớp Java đầy đủ cần chạy** (hoặc bỏ nếu manifest `Main-Class` đúng). Dùng **`--type app-image`** để tạo và kiểm tra native launcher trước khi tạo installer; luôn test thực tế với JAR, dependency, resource và runtime trên hệ điều hành đích.