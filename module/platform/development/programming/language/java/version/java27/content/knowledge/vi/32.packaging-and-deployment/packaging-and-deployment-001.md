# Tạo runtime image theo module bằng jlink

> **Phạm vi:** Java 27 — chương **Đóng gói và triển khai**. Bài học hướng dẫn dùng `jlink` để liên kết các **named modules** và những phụ thuộc cần thiết thành một **custom Java runtime image** có thể chạy ứng dụng bằng JVM đi kèm. Nội dung phân biệt runtime image với JAR, JDK, `jpackage` và native executable; có ví dụ thực hành từ source đến image, chẩn đoán module thiếu, service providers, thư viện chưa modular hóa, kích thước, tính tương thích nền tảng và bảo trì bảo mật. Chỉ dùng những tùy chọn còn được hỗ trợ trong Java 27; các flag cũ đã deprecated không được đưa làm lựa chọn mặc định.

## 1. jlink giải quyết vấn đề gì?

Khi triển khai một ứng dụng Java, thông thường cần cả **mã ứng dụng** lẫn **Java runtime** có đủ những module/JVM components ứng dụng sử dụng. Việc sao chép cả JDK phát triển lên môi trường chạy có thể mang theo nhiều công cụ và module không phục vụ ứng dụng.

`jlink` là công cụ của JDK để **liên kết một tập module và các dependency bắc cầu thành runtime image tùy biến**:

~~~text
        JDK 27 (system modules)
                  │
       ┌──────────┴──────────┐
       │                     │
  Module ứng dụng       Module thư viện
  com.example.app       com.example.greetings
       │                     ▲
       └─────────requires────┘
                  │
                  ▼
        jlink --add-modules
                  │
                  ▼
       Custom runtime image
       ├── bin/java
       ├── bin/hello (launcher tùy chọn)
       ├── lib/modules
       ├── conf/
       └── các thành phần runtime cần thiết
                  │
                  ▼
          Chạy bằng JVM đi kèm
       Không cần cài JDK riêng trên máy đích
       (nhưng vẫn cần OS/native dependencies)
~~~

Nếu chỉ `jlink` từ một số **JDK modules** thì image chứa JVM runtime tương ứng. Nếu root module là **explicit application module** và nó được link vào image, class/resources của ứng dụng cũng nằm trong image. Hai chiến lược này khác nhau và không nên đánh đồng.

### 1.1. Ưu điểm thực tế

- Chỉ mang theo **các named modules được resolve**, không phải mọi module của một full JDK.
- Có thể tạo launcher để chạy app, giúp phân phối cùng **JVM/runtime đã chọn**.
- Giảm bề mặt triển khai không cần thiết khi loại bỏ các modules/tools thừa.
- Kiểm soát phiên bản runtime gắn với artifact, có lợi cho kiểm thử và triển khai lặp lại.
- Kết hợp với `jpackage` hoặc container packaging trong pipeline phát hành.
- Có thể bỏ headers/manpages, strip debug data hoặc nén resources theo tùy chọn được hỗ trợ để tối ưu kích thước.

**Giảm kích thước không được bảo đảm theo một tỷ lệ cố định**: số module, native dependencies, cấu hình nén, dịch vụ và chức năng ứng dụng quyết định image thực tế.

### 1.2. Những gì jlink không làm

| Công việc | jlink có thực hiện không? |
| --- | --- |
| Chọn, resolve và liên kết named modules đã có | **Có** |
| Sinh custom JVM runtime image | **Có** |
| Tự biên dịch mã nguồn `.java` | **Không**; dùng `javac`/build tool |
| Tải JAR dependencies từ Maven Central | **Không**; build tool chuẩn bị artifacts |
| Biến bytecode thành native executable kiểu AOT compiler riêng | **Không** |
| Tự tạo bộ cài `.msi`/`.pkg`/`.deb` | **Không**; xem `jpackage` |
| Tự đóng gói mọi JAR không modular vào image | **Không** |
| Tự phát hiện mọi class chỉ được gọi qua reflection | **Không** |
| Tự cập nhật image khi JDK có bản vá bảo mật | **Không** |
| Biến image Windows thành image Linux tương thích | **Không** |

`jlink` đã là công cụ chính thức từ JPMS, tiếp tục được hỗ trợ trong Java 27. Nó là giải pháp **custom runtime**, không phải một hướng dẫn sử dụng JRE độc lập kiểu phát hành Java cũ.

## 2. Điều kiện tiên quyết: named modules và module graph

Một explicit Java module được khai báo bằng `module-info.java`:

~~~java
module com.example.greetings {
    exports com.example.greetings;
}
~~~

Một module dùng thư viện đó:

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

Trong JPMS:

- `requires` khai báo dependency tới **tên module**, không phải Maven `artifactId` hay tên JAR.
- `exports` cho phép các named modules khác đọc được **public/protected API** ở package đã xuất.
- `opens` phục vụ deep reflection tại runtime trong phạm vi đã khai.
- Mỗi named module (trừ `java.base`) có dependency ngầm đến `java.base`.
- `requires transitive` có thể làm khả năng đọc dependency lan đến modules tiêu thụ API; không tự export mọi package.
- `requires static` biểu diễn dependency bắt buộc lúc compile nhưng có thể vắng mặt ở runtime; cần xem kỹ code thực sự gọi dependency hay không.
- `uses` và `provides ... with` phục vụ service loading — có thể ảnh hưởng tập modules cần link.

**Cần phân biệt ba tập:**

1. **Observable modules:** những module finder có thể tìm trong JDK/module path.
2. **Root modules:** tên được chọn bởi `--add-modules` và các tùy chọn liên quan.
3. **Resolved modules:** tập closure phụ thuộc mà jlink thực sự đưa vào image theo quy tắc JPMS, cùng những provider bổ sung nếu yêu cầu service binding.

Ví dụ `com.example.app` được chọn làm root và có `requires com.example.greetings;`; `jlink` sẽ resolve `com.example.greetings` và `java.base` cần thiết. **Một JAR có mặt trên module path nhưng không nằm trong resolved graph không tự được đưa vào image.**

### 2.1. Module path có thể gồm gì?

Theo tài liệu Java SE 27, `jlink --module-path` quan sát:

- Các **modular JAR** có descriptor `module-info.class`.
- Các **exploded module directories** (thư mục output có `module-info.class`).
- Các **JMOD files**, thường chứa system modules và có thể chứa native libraries/config đặc thù.

Trên một JDK đầy đủ có thư mục `jmods/`, `jlink` có thể tìm system modules từ đó. Với image/JDK đặc biệt hỗ trợ linking from runtime image (JEP 493), nguồn system modules có thể khác — phần 11 sẽ giải thích cách kiểm tra.

**Không** hiểu module path là một thư mục nguồn `src/` chưa biên dịch. `jlink` là công cụ **link**, không phải compiler.

### 2.2. Không phải bất kỳ JAR trên module path đều link được

Một JAR **không có `module-info.class`** có thể hoạt động như **automatic module** trong ứng dụng chạy bằng `java -p`, nhưng `jlink` hiện không link trực tiếp automatic modules vào image. Cần explicit module descriptor hoặc phương án phân phối khác.

Ví dụ tình huống lỗi:

~~~text
Error: automatic module cannot be used with jlink: <module-name>
~~~

Các cách xử lý hợp lệ và giới hạn khi dùng thư viện chưa modular hóa được trình bày ở phần 16.

## 3. Runtime image khác JAR, JMOD và JDK ở đâu?

| Khái niệm | Chứa gì? | Dùng để làm gì? |
| --- | --- | --- |
| Class file `.class` | Bytecode và class metadata | Đơn vị JVM load/link |
| **Modular JAR** | Class/resources và `module-info.class` | Phân phối module, compile/run và làm đầu vào jlink |
| **JMOD** | Module content, có thể gồm native/config files | Đầu vào link/module packaging; **không** chạy trực tiếp bằng `java -jar` |
| **Full JDK** | JVM, system modules, developer tools như `javac`, `jlink` | Phát triển, biên dịch, chẩn đoán, tạo image |
| **Custom runtime image** | JVM và modules đã link, configurations/native libs phù hợp | Chạy ứng dụng trên nền tảng đích |
| **Application image / installer** | Runtime, launcher, payload/resources và metadata cài đặt | Phân phối cho người dùng; thường dùng `jpackage` |

Khi `jlink` tạo output, thư mục có thể trông như:

~~~text
dist/hello-runtime/
├── bin/
│   ├── java                   # java.exe trên Windows
│   └── hello                  # hello.exe trên Windows, khi --launcher
├── conf/
├── legal/
├── lib/
│   ├── modules                # runtime module image data
│   └── các thư viện runtime khác tùy OS/JDK
└── release                    # thông tin runtime image
~~~

**Cấu trúc cụ thể phụ thuộc JDK distribution và hệ điều hành**. Đừng viết script production dựa vào một danh sách file tuyệt đối cố định trừ những phần đã được runtime/tooling xác nhận.

- Image **có JVM riêng**; dùng `dist/hello-runtime/bin/java` thay vì `java` ngoài PATH.
- Nó thường **không chứa `javac`, `jar` hay `jlink`** nếu bạn không link các developer tools/modules tương ứng.
- `lib/modules` là định dạng runtime image nội bộ, **không** tương đương việc giữ nguyên các JAR trong `lib/`.
- App code chỉ có sẵn bên trong image nếu đã được link như named module, hoặc bạn phân phối **payload app/JAR riêng**.

## 4. Ví dụ tự chứa: ứng dụng gồm hai module

Ví dụ sau dùng **hai explicit named modules**, không cần dependencies ngoài JDK. Đây là **bố cục thực hành để người học tự tạo**, không phải lệnh ghi thêm file vào module bài học hiện tại.

### 4.1. Bố cục thư mục

~~~text
jlink-demo/
├── src/
│   ├── com.example.greetings/
│   │   ├── module-info.java
│   │   └── com/example/greetings/Greeter.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
├── mods/                # compile output (tạo khi thực hành)
├── lib/                 # modular JAR output (tùy chọn)
└── dist/                # runtime images (tạo khi thực hành)
~~~

Hai tên module là `com.example.greetings` và `com.example.app`, mỗi module có package/class tương ứng.

### 4.2. Module thư viện

File `src/com.example.greetings/module-info.java`:

~~~java
module com.example.greetings {
    exports com.example.greetings;
}
~~~

File `src/com.example.greetings/com/example/greetings/Greeter.java`:

~~~java
package com.example.greetings;

import java.util.Objects;

public final class Greeter {
    private Greeter() {}

    public static String greet(String name) {
        return "Xin chào, " + Objects.requireNonNull(name, "name");
    }
}
~~~

### 4.3. Module ứng dụng

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.greetings;
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.greetings.Greeter;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        String name = args.length == 0 ? "Java 27" : args[0];
        System.out.println(Greeter.greet(name));
    }
}
~~~

**Những gì example chứng minh:**

- App không nằm trên classpath; nó có `module-info.java`.
- Thư viện export public API package.
- App khai báo `requires` tới thư viện.
- Điểm vào là `com.example.app/com.example.app.Main` (module name `/` main class FQN).
- Không có API preview hoặc thao tác I/O ngoài console, nên ví dụ tập trung vào module resolution và link.

## 5. Biên dịch và chạy từ exploded modules

Thực hiện tại thư mục `jlink-demo/`. Trước tiên xác nhận JDK:

~~~bash
java -version
javac -version
jlink --version
~~~

Ba công cụ nên thuộc bộ JDK 27 mà bạn chọn. Nếu `java -version` chỉ đúng JDK 27 nhưng `jlink` lại thuộc JDK khác, bạn có thể link ra image khác mong đợi.

### 5.1. Chuẩn bị output directories

Linux/macOS (Bash):

~~~bash
mkdir -p mods lib dist
~~~

Windows (PowerShell):

~~~powershell
New-Item -ItemType Directory -Force -Path mods,lib,dist | Out-Null
~~~

Trong ví dụ, các path là tương đối so với `jlink-demo/`, không phải những đường dẫn cố định của máy người học.

### 5.2. Biên dịch cả hai module

~~~bash
javac --module-source-path src -d mods --module com.example.greetings,com.example.app
~~~

`--module-source-path src` cho compiler biết layout source theo module; `--module` chọn những module cần compile. Compiler đọc `requires com.example.greetings;` nên compile và resolve hai module theo quan hệ đã khai.

Output mong đợi:

~~~text
mods/
├── com.example.greetings/
│   ├── module-info.class
│   └── com/example/greetings/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Nếu sử dụng Gradle/Maven ở dự án thật, chúng có thể biên dịch các modules trong các output paths khác. Điều cốt lõi là module artifacts được chuẩn bị đúng, không phải output bắt buộc luôn có tên `mods`.

### 5.3. Chạy trước khi jlink

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Xin chào, Java 27
~~~

Truyền tham số:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main "Linh"
~~~

Kết quả:

~~~text
Xin chào, Linh
~~~

**Nên kiểm thử trước khi link**: nếu app chưa chạy với `java --module-path`, việc chuyển sang `jlink` không tự sửa lỗi `module-info`, thiếu JAR hay sai main class.

### 5.4. Kiểm tra descriptor và dependency

~~~bash
java --module-path mods --describe-module com.example.app
java --module-path mods --describe-module com.example.greetings
jdeps --module-path mods --check com.example.app
~~~

- `java --describe-module` xem descriptor và các `requires`/`exports` liên quan.
- `jdeps --check` phân tích module dependencies và graph; không thay thế kiểm thử runtime của các dependency dùng qua reflection/service loading.

## 6. Dùng jlink tạo runtime image

Từ root của ví dụ (sau khi compile thành công):

~~~bash
jlink --module-path mods --add-modules com.example.app --launcher hello=com.example.app/com.example.app.Main --output dist/hello-runtime --strip-debug --no-header-files --no-man-pages --compress=zip-6
~~~

Đây là lệnh **chủ đạo**:

| Thành phần | Ý nghĩa |
| --- | --- |
| `jlink` | Dùng linker của JDK đang chọn |
| `--module-path mods` | Chỉ nơi có hai compiled application modules |
| `--add-modules com.example.app` | Chọn ứng dụng làm **root module**; dependencies được resolve |
| `--launcher hello=com.example.app/com.example.app.Main` | Sinh launcher `hello` trỏ tới module/main class |
| `--output dist/hello-runtime` | Đặt thư mục runtime image cần tạo |
| `--strip-debug` | Bỏ debug information khỏi output image |
| `--no-header-files` | Bỏ developer header files |
| `--no-man-pages` | Bỏ man pages |
| `--compress=zip-6` | Nén resources theo cú pháp Java 27 hiện hành |

**Lưu ý về system modules:** với bản JDK 27 chuẩn có `jmods/`, `jlink` có thể tự thêm nguồn system modules khi `java.base` chưa được giải từ module path được truyền (theo manpage). Nếu JDK vendor đã xây dựng để link từ runtime image theo JEP 493, cách lấy system modules có thể khác. Hãy dùng `jlink --help` và JDK distribution docs để biết khả năng thực tế.

**Lưu ý về output:** `--output` tạo một image mới. Nếu `dist/hello-runtime` đã tồn tại từ lần build trước, jlink có thể báo lỗi. Trong pipeline, dùng output directory mới cho từng build hoặc chủ động dọn đúng thư mục artifact do pipeline sở hữu; **không** xóa bừa các thư mục không thuộc build.

### 6.1. Cơ chế liên kết của lệnh trên

~~~text
Root: com.example.app
  ├── requires com.example.greetings
  │     └── implicitly requires java.base
  └── implicitly requires java.base
               │
               ▼
Resolved set (mẫu tối giản):
  com.example.app
  com.example.greetings
  java.base
               │
               ▼
jlink tạo image chứa code của cả app, thư viện và JVM
~~~

Danh sách trên đúng theo **ví dụ có descriptor tối giản**. Trong ứng dụng thực, providers, JDK modules cho networking/SQL/management và library dependencies có thể mở rộng graph. `--add-modules` nhận tên module, **không** nhận class FQN hoặc file JAR.

### 6.2. Nếu muốn khai rõ nguồn JMOD trên host JDK

Ở JDK có thư mục `jmods/`, có thể chỉ định cả module artifacts và system modules:

Linux/macOS:

~~~bash
jlink --module-path "mods:$JAVA_HOME/jmods" --add-modules com.example.app --output dist/explicit-runtime
~~~

Windows PowerShell:

~~~powershell
jlink --module-path "mods;$env:JAVA_HOME\jmods" --add-modules com.example.app --output dist/explicit-runtime
~~~

Ví dụ này **chỉ dành cho JDK có `jmods`**. Không coi sự tồn tại của `jmods` là bắt buộc với mọi bản JDK 27 vì JEP 493 cho phép cách liên kết không dựa trên JMODs khi vendor bật tính năng.

Ký tự phân tách module-path entries là `;` trên Windows và `:` trên Linux/macOS; không nhầm với dấu `/` bên trong module/main class.

## 7. Chạy và xác minh image đã tạo

Bên trong image, dùng đúng `bin/java` đã được link.

Linux/macOS:

~~~bash
./dist/hello-runtime/bin/java --version
./dist/hello-runtime/bin/java --list-modules
./dist/hello-runtime/bin/java --module com.example.app/com.example.app.Main
./dist/hello-runtime/bin/hello "Mai"
~~~

Windows PowerShell:

~~~powershell
.\dist\hello-runtime\bin\java.exe --version
.\dist\hello-runtime\bin\java.exe --list-modules
.\dist\hello-runtime\bin\java.exe --module com.example.app/com.example.app.Main
.\dist\hello-runtime\bin\hello.exe "Mai"
~~~

Kết quả từ launcher cuối:

~~~text
Xin chào, Mai
~~~

**Đừng kiểm thử nhầm bằng `java` trong PATH**. Kiểm tra `./dist/hello-runtime/bin/java` (hoặc `java.exe`) để xác nhận image chứa runtime và các modules cần thiết.

### 7.1. Xem đúng module graph trong image

~~~bash
./dist/hello-runtime/bin/java --list-modules
./dist/hello-runtime/bin/java --describe-module com.example.app
./dist/hello-runtime/bin/java --show-module-resolution --module com.example.app/com.example.app.Main
~~~

Đây là cú pháp cho Linux/macOS; Windows chỉ cần thay đường dẫn executable như trên. Module graph mà launcher thể hiện có thể bao gồm các system modules bổ sung nếu image được xây với services hoặc các root modules khác.

### 7.2. Không cần một JDK khác khi chạy image

Sau khi toàn bộ thư mục image được phân phối **đúng nền tảng**, launcher `bin/java` bên trong có JVM và module runtime để chạy. Máy đích không cần tự cài một full JDK riêng.

Nhưng image **không phải chương trình độc lập khỏi hệ điều hành**: nó vẫn phụ thuộc binary architecture, system libraries, quyền thực thi, filesystem layout và các nguồn dữ liệu ngoài như database, native drivers hoặc certificate stores.

### 7.3. Đừng chỉ sao chép bin/java

Chạy `bin/java` thường cần `lib/modules`, native libraries, cấu hình bảo mật và các tệp liên quan trong image. Việc copy **duy nhất binary java** ra thư mục khác có thể tạo lỗi ngay khi khởi động. Phân phối **toàn bộ runtime image** theo cấu trúc của nó, không cắt tùy tiện các file không hiểu mục đích.

## 8. Link modular JAR thay vì exploded modules

Ở dự án thật, build tool thường tạo **modular JARs**. Có thể đóng gói hai compiled modules từ ví dụ thành JARs:

~~~bash
jar --create --file lib/com.example.greetings.jar -C mods/com.example.greetings .
jar --create --file lib/com.example.app.jar -C mods/com.example.app .
~~~

Mỗi JAR cần chứa `module-info.class` ở gốc archive. Kiểm tra:

~~~bash
jar --describe-module --file lib/com.example.greetings.jar
jar --describe-module --file lib/com.example.app.jar
jar --list --file lib/com.example.app.jar
~~~

Chạy trực tiếp từ module path trước khi link:

~~~bash
java --module-path lib --module com.example.app/com.example.app.Main
~~~

Tạo image mới từ JAR artifacts:

~~~bash
jlink --module-path lib --add-modules com.example.app --launcher hello=com.example.app/com.example.app.Main --output dist/hello-jar-runtime --compress=zip-6
~~~

Sau khi link:

~~~bash
./dist/hello-jar-runtime/bin/java --module com.example.app/com.example.app.Main
~~~

Lệnh chạy cuối là dành cho Linux/macOS; trên Windows dùng `.\dist\hello-jar-runtime\bin\java.exe`. **Không** cần cung cấp `--module-path lib` khi app module đã được liên kết bên trong image, trừ khi thiết kế có phụ thuộc modules bên ngoài hình ảnh.

### 8.1. Tên module khác tên JAR

Ví dụ file `my-greetings-2.0.jar` có thể chứa explicit module `com.example.greetings`. `jlink --add-modules` phải dùng **tên module**, không dùng tên file hoặc package tự suy đoán.

Với modular JAR:

~~~bash
jar --describe-module --file lib/com.example.greetings.jar
~~~

Hãy đọc tên module từ descriptor. Tự đoán từ `artifactId` của Maven hoặc filename của Gradle có thể sai.

### 8.2. JMOD có cần thiết cho thư viện ứng dụng?

Thông thường **không**. Tài liệu `jmod` của Java SE 27 khuyến nghị đa số thư viện vẫn đóng gói dưới dạng **modular JAR** để phát hành lên repository hoặc dùng qua module path.

`JMOD` thích hợp hơn cho những module cần kèm native libs, configuration files hoặc hỗ trợ liên kết runtime theo cách đặc biệt. JMOD **không phải executable JAR**; không dùng `java -jar foo.jmod` để chạy chương trình.

### 8.3. Maven và Gradle có thể chuẩn bị đầu vào

Quy trình khái niệm:

~~~text
mvn package / ./gradlew jar
             │
             ▼
    Modular JAR artifacts
             │
             ▼
   jlink --module-path <artifact-directory>
         --add-modules <app-module>
             │
             ▼
       Runtime image
             │
             ▼
    Smoke test bằng image/bin/java
~~~

Các đường dẫn thực tế có thể là `target/*.jar` hoặc `build/libs/*.jar`; nhiều project còn có dependency artifacts trong một thư mục staging riêng. Không giả định `--module-path build/libs` đủ nếu third-party module JARs nằm ở repository cache và chưa được copy tới staging. Build pipeline cần **chuẩn bị một module path đầy đủ, ổn định** trước khi link.

## 9. Phân tích dependency graph bằng jdeps

`jdeps` là công cụ đi kèm JDK để phân tích class/module dependencies ở mức bytecode. Nó hữu ích trước khi link image, đặc biệt khi dự án có nhiều thư viện.

### 9.1. Với explicit module

~~~bash
jdeps --module-path mods --check com.example.app
jdeps --module-path mods --module com.example.app --list-deps
~~~

Lệnh `--check` cho biết descriptor, graph liên quan và có thể chỉ ra các vấn đề ở dependency graph. Tùy cấu trúc app, `--list-deps` liệt kê module/package dependencies quan sát được trong bytecode.

Có thể yêu cầu danh sách module dạng dấu phẩy phù hợp làm đầu vào `jlink`:

~~~bash
jdeps --module-path mods --print-module-deps --module com.example.app
~~~

**Quan trọng:** output chính xác phải được kiểm tra trên JDK và artifact thật; `jdeps` không phải một command tự động tạo ra runtime image, và `--print-module-deps` không thể suy ra mọi class chỉ được load động.

### 9.2. Với JAR không modular

Nếu `app.jar` là classpath JAR và phụ thuộc các JAR trong `lib/`:

~~~bash
jdeps --multi-release 27 --class-path "lib/*" --print-module-deps app.jar
~~~

Cách dùng `--multi-release 27` hữu ích khi các artifacts là multi-release JARs. `jdeps` phân tích những class references có thể thấy và hỗ trợ liệt kê các **JDK modules** cần thiết ở mức bytecode.

Không vội dùng `--ignore-missing-deps` chỉ để nhận output đẹp: nếu thiếu class/JAR khi phân tích, phải xác minh dependency set trước, vì bỏ qua dependency có thể tạo runtime image thiếu thành phần cần thiết.

### 9.3. Vì sao output jdeps có thể chưa đủ?

Một số dependency không xuất hiện dưới dạng class reference tĩnh trong bytecode của app:

- `Class.forName("...")` với class name lấy từ config/string.
- `ServiceLoader` chọn provider modules lúc chạy.
- JDBC driver được nạp qua service discovery.
- Provider liên quan cryptography, charset, locale, security.
- Plugin/JNI/FFM library hoặc thư viện được load tùy môi trường.
- Reflection dùng bởi framework (ORM, JSON, DI, logging).
- Multi-release JARs có đường code thay đổi theo JDK release.
- Native dependencies cần shared libraries/certificates/config bên ngoài.

**Công thức đúng:** `jdeps` để lấy **bản đồ tĩnh khởi đầu** + kiểm tra `module-info.java`/`uses`/`provides` + integration tests trên **image thực**. Không nhầm `jdeps --print-module-deps` với một danh sách runtime hoàn hảo cho mọi workload.

## 10. ServiceLoader và service provider modules

JPMS có cơ chế dịch vụ:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
~~~

Module cung cấp implementation:

~~~java
module com.example.provider {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.provider.VietnameseGreetingService;
}
~~~

Module `com.example.spi` chứa interface `GreetingService` và export package API; `com.example.provider` chứa class thực hiện interface. Các tên trên chỉ là **ví dụ về descriptor**; để chạy thật, cần tạo/compile đầy đủ module API, provider và app.

### 10.1. Vì sao provider dễ bị thiếu?

App có thể khai `uses` rồi gọi:

~~~java
var loader = java.util.ServiceLoader.load(
        com.example.spi.GreetingService.class);
~~~

Một provider JAR nằm trên module path **không có nghĩa** nó sẽ tự được link vào image nếu không nằm trong resolved graph. Nếu thiếu provider, việc duyệt `ServiceLoader` có thể không tìm được implementation dù code compile thành công.

Hai cách phù hợp:

1. **Bổ sung provider module vào root modules** khi biết chính xác cần provider nào.
2. **Dùng `--bind-services`** khi muốn linker resolve/bind providers quan sát được theo các service declarations.

Ví dụ với provider cụ thể:

~~~bash
jlink --module-path lib --add-modules com.example.app,com.example.provider --output dist/with-provider
~~~

Hoặc chọn service binding theo graph:

~~~bash
jlink --module-path lib --add-modules com.example.app --bind-services --output dist/with-services
~~~

### 10.2. Không bật bind-services theo phản xạ

`--bind-services` có thể kéo vào **nhiều provider modules và phụ thuộc bắc cầu**, kể cả các modules của JDK không liên quan trực tiếp tới tính năng bạn định dùng. Điều này có thể làm image tăng kích thước đáng kể và làm thay đổi tập dịch vụ khả dụng.

Trước khi quyết định:

~~~bash
jlink --suggest-providers java.security.Provider
~~~

Lệnh giúp liệt kê những provider modules phù hợp với service được hỏi trong phạm vi module path quan sát được. Tùy nhu cầu, **chọn explicit provider modules** có thể tốt hơn việc link mọi providers.

### 10.3. JDBC driver là một ví dụ thực tế

App sử dụng `java.sql` thường còn cần một JDBC driver cụ thể. `requires java.sql;` **không** tự đưa driver JDBC bên thứ ba vào image.

Với driver là **explicit named module** và có service provider declaration phù hợp, có thể link provider module rõ ràng. Nhưng nhiều driver JAR không có explicit descriptor và chỉ hoạt động như automatic module; loại này không thể được đưa trực tiếp vào image bằng `jlink`.

Lúc đó cần:

- Chọn một distribution JDBC driver có explicit module descriptor phù hợp, **hoặc**
- Dùng custom JDK runtime image và phân phối JDBC/app JARs riêng ở classpath/module path theo một mô hình đã kiểm thử.

Một image chỉ có `java.sql` nhưng thiếu driver không thể thực hiện truy cập database chỉ bằng phép màu của linker.

## 11. Java 27: JMODs và khả năng link từ runtime image (JEP 493)

Đây là thay đổi quan trọng so với cách học `jlink` chỉ dựa trên những bản JDK cũ.

### 11.1. Truyền thống: jlink dùng JMODs của full JDK

Một full JDK thường có:

~~~text
jdk-27/
├── bin/
│   ├── java
│   ├── javac
│   └── jlink
├── jmods/
│   ├── java.base.jmod
│   ├── java.logging.jmod
│   ├── java.sql.jmod
│   └── ...
└── lib/
~~~

`jlink` dùng JMODs và user modules để tạo image mới. Điều này giải thích vì sao chạy `jlink` từ một runtime image rất nhỏ **không mặc nhiên** có đủ thông tin để tạo image thứ hai.

### 11.2. JEP 493: không bắt buộc JMODs ở mọi JDK vendor build

[JEP 493 — Linking Run-Time Images without JMODs](https://openjdk.org/jeps/493), được đưa vào JDK 24, cho phép bản JDK được **xây dựng với tính năng thích hợp** liên kết runtime image mà không cần giữ bộ JMOD files của JDK.

Điểm chính:

- Đây là **khả năng được bật tại lúc xây dựng JDK distribution**, không phải một flag người dùng cứ thêm vào lệnh `jlink` là mọi bản JDK tự có.
- Không phải mọi JDK vendor/build đều bật sẵn; những gì hiện hữu phụ thuộc distribution.
- Cách linker đọc dữ liệu của system modules có thể khác so với bản JDK có `jmods/`.
- Khi sử dụng khả năng link từ runtime image, có thể có **giới hạn bổ sung** với một số modules hoặc việc tạo chuỗi image nhiều tầng. Cần đọc tài liệu của distribution và kiểm tra ngay trên tool thực.

### 11.3. Kiểm tra capabilities của jlink thực tế

~~~bash
jlink --help
~~~

Đối với những build có hỗ trợ, cuối output có thể xuất hiện:

~~~text
Capabilities:
    Linking from run-time image enabled
~~~

Hoặc:

~~~text
Capabilities:
    Linking from run-time image disabled
~~~

Từ `--help`, bạn biết khả năng của **đúng jlink executable**. **Không kết luận** mọi JDK 27 đều có JMODs, hoặc mọi JDK 27 đều link từ runtime image, khi chưa kiểm tra vendor build cụ thể.

### 11.4. Hướng dẫn thực hành an toàn

- Nếu có `$JAVA_HOME/jmods`, dùng quy trình module path thông thường.
- Nếu không có, kiểm tra linker capabilities và hướng dẫn của vendor trước khi chạy.
- Nếu JDK không có JMODs **và** linker không hỗ trợ runtime-image linking, cần dùng một JDK distribution phù hợp hơn làm **build/link environment**.
- Chỉ ghi “linkable from runtime image” trong tài liệu triển khai nếu CI đã xác minh với **đúng distribution**.
- Tránh hard-code quy trình copy JMODs từ một JDK có vendor/update khác để trộn vào module graph; có thể gây lỗi tính tương thích của native/runtime components.

## 12. Các tùy chọn jlink còn áp dụng trong Java 27

| Tùy chọn | Ý nghĩa | Cần thận trọng |
| --- | --- | --- |
| `--module-path` / `-p` | Nguồn named modules/JMODs | Đủ app modules và system modules |
| `--add-modules` | Các root modules được link | Chỉ đặt module names thực sự cần |
| `--output` | Output runtime image directory | Không overwrite image cũ |
| `--launcher` | Sinh launcher cho module/main class | Đúng module/class FQN |
| `--bind-services` | Resolve/bind provider modules | Có thể tăng image đáng kể |
| `--suggest-providers` | Gợi ý provider modules cho service | Dùng để kiểm tra trước khi bind |
| `--compress=zip-N` | Nén resources mức 0–9 | Size vs startup/decompression CPU |
| `--strip-debug` | Bỏ debug information | Có thể giảm khả năng chẩn đoán |
| `--no-header-files` | Bỏ header files | Không dùng image đó như developer SDK |
| `--no-man-pages` | Bỏ man pages | Ảnh hưởng khả năng tra cứu offline |
| `--include-locales` | Chọn locale data với `jdk.localedata` | Phải giữ đúng BCP 47 tags |
| `--generate-cds-archive` | Sinh archive CDS nếu image hỗ trợ | Tùy JDK/plugin, đo startup và size |
| `--limit-modules` | Giới hạn tập observable modules | Có thể làm module/service không resolve |
| `--save-opts` | Ghi options vào file | Không chèn secret vào options file |
| `--list-plugins` | Xem các plugins được tool hỗ trợ | Không giả định plugin của bản khác còn tồn tại |
| `--ignore-signing-information` | Cho phép link trong một số trường hợp signed modular JAR | **Loại bỏ signature-related data**; không dùng tùy tiện |

Để xem những plugin options **thực tế có**:

~~~bash
jlink --list-plugins
jlink --help
~~~

### 12.1. Nén: dùng cú pháp zip-N hiện hành

Ở Java 27, dạng được tài liệu hỗ trợ là:

~~~bash
--compress=zip-0
--compress=zip-6
--compress=zip-9
~~~

- `zip-0`: không nén.
- `zip-6`: mức nén mặc định được tài liệu công bố.
- `zip-9`: nén mạnh hơn, có thể tốn CPU và không chắc giảm tổng size đáng kể cho mọi workload.

**Không dùng `--compress=2` làm gợi ý mới**: cách khai báo bằng số `0/1/2` đã được **deprecated, dự kiến loại bỏ** trong release tương lai. Đây là một khác biệt cần lưu ý khi đọc các tutorial `jlink` viết cho các JDK cũ.

### 12.2. Bỏ header và manpage không phải dọn sạch không giới hạn

Một lệnh giảm size vừa phải:

~~~bash
jlink --module-path mods --add-modules com.example.app --output dist/slim-runtime --strip-debug --no-header-files --no-man-pages --compress=zip-6
~~~

Không tự xóa thêm ngẫu nhiên những thư mục như `lib/`, `conf/security/`, `legal/`, `release` sau khi linker chạy. Các tệp còn lại có thể cần cho JVM startup, TLS/crypto, timezones, native libraries, licensing hoặc vận hành.

### 12.3. Tùy chọn include-locales

Ví dụ một ứng dụng cần dữ liệu bản địa hóa cho tiếng Việt và tiếng Anh:

~~~bash
jlink --module-path mods --add-modules com.example.app,jdk.localedata --include-locales=vi,en --output dist/localized-runtime
~~~

Các tag trong `--include-locales` là **BCP 47 language tags**. Plugin `include-locales` yêu cầu module `jdk.localedata`. Một số locale data vẫn nằm trong `java.base`; với ứng dụng cần đầy đủ localization, hãy **kiểm tra output thực** thay vì suy từ danh sách language tags.

Nếu chương trình dùng `DateTimeFormatter`, `NumberFormat` hoặc `ResourceBundle` cho nhiều thị trường, hãy chạy integration tests với các `Locale` cụ thể ngay trên image. Đừng giả định dữ liệu resource bundles tùy chỉnh được linker tự thay đổi cho bạn.

### 12.4. JFR/CDS và công cụ giám sát

Một runtime image có thể thiếu những công cụ/module hữu ích cho production diagnostics nếu bạn không thêm chúng. Ví dụ:

- `jdk.jfr` hỗ trợ Java Flight Recorder, khi runtime/JDK distribution triển khai phù hợp.
- `jdk.management` hoặc một số JDK modules khác có thể cần cho cơ chế quan sát cụ thể.
- `jcmd` là công cụ command-line của JDK; **không mặc định** có sẵn bên trong minimal image.
- `--generate-cds-archive` có thể hỗ trợ startup khi image và VM hỗ trợ; cần đo thực tế sau khi bật, không dựa vào kích thước file đơn lẻ.

Nếu chạy ứng dụng trong production, xác định **kịch bản quan sát và xử lý sự cố** trước khi loại bỏ các module/chẩn đoán cần thiết. Minimal image tốt là image **đủ chức năng và đủ khả năng vận hành**, không phải chỉ có kích thước nhỏ nhất.

## 13. Các module dễ bị thiếu trong ứng dụng thực

| Nhu cầu ứng dụng | Module/provider cần xem xét | Ghi chú |
| --- | --- | --- |
| HTTP networking | `java.net.http` nếu dùng JDK HttpClient | `java.base` vẫn chứa socket APIs cơ bản |
| JDBC API | `java.sql` | **Không** tự mang driver của vendor |
| JNDI | `java.naming` | Còn tùy provider/config |
| XML parsing | `java.xml` | XML APIs trong module này |
| Logging chuẩn JDK | `java.logging` | Framework logging ngoài JDK cần JAR riêng |
| Management/JMX | `java.management` | Kiểm tra monitoring integration |
| Locale dữ liệu mở rộng | `jdk.localedata` | Dùng với `--include-locales` khi cần |
| Charset mở rộng | `jdk.charsets` | Charset trong `java.base` vẫn còn; cần test charset đặc biệt |
| Crypto/TLS providers | Provider modules phù hợp, ví dụ `jdk.crypto.ec` | Phụ thuộc thuật toán/protocol/security provider |
| JFR | `jdk.jfr` | Kiểm tra nhu cầu profiling/recording |
| Java desktop APIs | `java.desktop` | UI, font/image-related APIs khi cần |

**Không thêm tất cả các modules theo bảng một cách máy móc**. Bảng chỉ là điểm kiểm tra, không phải một cấu hình chung dành cho mọi service. Các module bạn thêm phải phục vụ code hoặc providers thực sự được dùng.

### 13.1. Runtime configuration và resources

Một custom image có thể cần:

- Certificate truststore và các trust anchors phù hợp với môi trường.
- Timezone information và locale data.
- Security providers cho TLS, key/certificate algorithms.
- Native libraries cần cho database drivers, crypto, media hoặc JNI.
- `ServiceLoader` providers, resource bundles, file config, templates, static assets.
- JVM flags, resource limits, logging/tracing setup.
- External connections và secrets từ runtime environment.

**jlink không tự khám phá file cấu hình ứng dụng đang nằm ngoài modular artifacts**. Nếu app đọc `./config/application.yml` hoặc `/var/secrets/token` tại runtime, pipeline phải phân phối/cấp những dữ liệu đó theo một cơ chế **ngoài image** rõ ràng, hoặc đóng resource vào module/JAR khi thích hợp và an toàn.

### 13.2. TLS/crypto là một ví dụ dễ sai

Một image có thể chạy `System.out.println(...)` thành công nhưng lỗi khi kết nối HTTPS vì provider/algorithm/truststore/config không phù hợp với môi trường.

Khi app có HTTPS/TLS, hãy:

1. Xác định đúng JDK security providers và keystore/truststore setup.
2. Bảo đảm image có module/provider cần thiết.
3. Kiểm thử hostname verification, certificate chain và cipher suites theo endpoint mục tiêu.
4. Không tắt TLS certificate validation để “sửa” image thiếu provider.
5. Không nhúng private keys hoặc production secrets vào runtime image.

## 14. Đo kích thước và performance đúng cách

Tối ưu jlink cần phép đo. Không kết luận “image 30 MB chắc chắn nhanh hơn image 70 MB” chỉ từ dung lượng.

### 14.1. So sánh có kiểm soát

Tạo hai images từ cùng source/JDK:

~~~bash
jlink --module-path mods --add-modules com.example.app --output dist/base-runtime
jlink --module-path mods --add-modules com.example.app --output dist/compressed-runtime --strip-debug --no-man-pages --no-header-files --compress=zip-9
~~~

So sánh kích thước trên Linux/macOS:

~~~bash
du -sh dist/base-runtime dist/compressed-runtime
~~~

Trên Windows PowerShell:

~~~powershell
Get-ChildItem -Recurse -File dist/base-runtime |
    Measure-Object -Property Length -Sum

Get-ChildItem -Recurse -File dist/compressed-runtime |
    Measure-Object -Property Length -Sum
~~~

**Không có kết quả size cố định được bảo đảm.** JDK vendor, OS, architecture, included modules, plugins, compression và developer tools quyết định footprint.

### 14.2. Đo nhiều chỉ số

| Chỉ số | Tại sao cần |
| --- | --- |
| Size của thư mục runtime | Chi phí đĩa/artifact |
| Size bản ZIP/TAR/image layer | Chi phí truyền/caching |
| Startup latency | Quan trọng cho CLI/serverless/short-lived jobs |
| Warm throughput và p95/p99 latency | Xác định performance dưới workload thật |
| Peak RSS / process memory | JVM + native memory + heap |
| CPU load khi khởi động | Tác động decompression/JIT initialization |
| GC allocation/pauses | Không suy đoán từ module count |
| Time to first successful request | Bao gồm runtime + app startup + dependencies |

Khi kiểm chứng, dùng cùng JVM flags, cùng workload, warmup và số lần chạy. Không lấy một lần `time bin/java -version` làm bằng chứng cho startup của một server phức tạp.

### 14.3. Bớt module không đồng nghĩa bớt heap cần thiết

`--add-modules` quyết định modules có trong image, không tự biến `-Xmx4g` thành heap 128 MB hoặc làm objects biến mất. Heap/native memory và throughput vẫn phụ thuộc workload, object graph, JVM flags và GC.

Một image nhỏ có thể giúp packaging/cold-start phần nào nhưng cũng có thể đòi CPU giải nén nhiều hơn. **Benchmark quyết định**, không có một flag phù hợp cho mọi dịch vụ.

## 15. Runtime image mang tính nền tảng: OS, kiến trúc và phân phối

`jlink` tạo native runtime components phù hợp **nền tảng JDK đầu vào**: OS, CPU architecture và thư viện hệ thống liên quan. Khác với JAR bytecode có tính portable cao, một image Windows x64 không thể chỉ copy sang Linux ARM64 rồi mong chạy được.

### 15.1. Chiến lược build

- Tạo image trên cùng OS/architecture/ABI phù hợp với môi trường đích, hoặc dùng bộ công cụ cross-platform được hỗ trợ và đã kiểm chứng.
- Kiểm tra dependency tới C runtime/glibc, OS native libs và các provider phụ thuộc nền tảng.
- Với Linux containers, build/runtime base images nên có **ABI và native runtime compatibility** phù hợp.
- Với macOS/Windows, cần xét quyền thực thi, signing/notarization hoặc native redistributables theo nền tảng.
- Không phân phối một image duy nhất cho mọi OS nếu không có giải pháp multi-platform cụ thể.
- Giữ provenance của JDK distribution (vendor/version/build/architecture) trong release metadata.

### 15.2. Phân phối image như một artifact

Trên Linux/macOS, ví dụ tạo archive sau khi xây image:

~~~bash
tar -C dist -czf hello-runtime-linux-archive.tar.gz hello-runtime
~~~

Đây là ví dụ với image đã link **cho một nền tảng tương thích**; tên `linux` phải phản ánh OS đích thật chứ không phải tự động được tar biến đổi.

Ở máy đích tương thích, giải nén cả thư mục và chạy launcher:

~~~bash
tar -xzf hello-runtime-linux-archive.tar.gz
./hello-runtime/bin/hello
~~~

Khi phân phối TAR/ZIP/container layers, phải bảo toàn **permission bits, symlinks, directory hierarchy và native libraries**. Không chỉ chép mỗi file executable trong `bin/`.

### 15.3. jlink so với jpackage và container

| Công cụ/phương án | Sản phẩm |
| --- | --- |
| `jlink` | Tùy biến Java runtime image từ module graph |
| `jpackage` | Application image/native installer; có thể dùng jlink nội bộ hoặc một runtime image đã tạo |
| Container image | Package filesystem, OS user/config, app/runtime và metadata triển khai |
| Native-image/AOT compiler bên ngoài JDK | Native executable theo mô hình công cụ riêng, không tương đương jlink |

Với ứng dụng desktop dùng `jpackage`, có thể tạo runtime image riêng bằng `jlink` rồi truyền vào:

~~~bash
jpackage --type app-image --name HelloApp --module-path lib --module com.example.app/com.example.app.Main --runtime-image dist/hello-jar-runtime --dest dist/packages
~~~

**Lệnh trên là một ví dụ cách phối hợp**, yêu cầu các input module artifacts và runtime image thật sự tồn tại, JDK có `jpackage` và quyền phù hợp theo OS. `jpackage` có quy tắc riêng về layout/launcher/resource path, nên cần chạy thử bộ cài/app image kết quả thay vì tự suy từ lệnh `jlink`.

Trong container, vẫn phải chọn base OS runtime tương thích native libs và sử dụng một non-root user khi thích hợp. `jlink` không thay thế các chính sách container security, resource limits và graceful shutdown.

## 16. Ứng dụng không modular và automatic modules: lựa chọn thực tế

Không phải thư viện Java hiện đại nào cũng có explicit descriptor. Một JAR được đặt trên `--module-path` có thể là **automatic module**; nó giúp chạy theo cơ chế JPMS nhưng **không đủ để jlink liên kết module đó**.

Ví dụ lỗi:

~~~text
Error: automatic module cannot be used with jlink: commons.math3
~~~

Đây là ví dụ về loại lỗi, không phải khẳng định dự án đang dùng artifact đó. Hãy kiểm tra từng JAR thật:

~~~bash
jar --describe-module --file lib/some-library.jar
~~~

### 16.1. Ba phương án phù hợp

**Phương án A — Dùng phiên bản thư viện có explicit descriptor.**

Nếu vendor đã cung cấp modular JAR phù hợp, ưu tiên nâng cấp/đổi sang bản đã được kiểm chứng có `module-info.class`. Kiểm tra dependencies transitives và public API trước khi cập nhật. Một module descriptor không bảo đảm thư viện không có lỗi, nhưng giúp linker xác định graph tường minh.

**Phương án B — Modular hóa thư viện thuộc quyền sở hữu.**

Nếu bạn sở hữu source, có thể tạo `module-info.java`, định nghĩa `requires`/`exports`/`opens`/`uses`/`provides`, biên dịch thành explicit modular JAR rồi link. `jdeps --generate-module-info` có thể gợi ý descriptor để **review**, nhưng không tự hiểu hết reflection, service providers, native requirements và API semantics.

Không sửa một JAR third-party có chữ ký để thêm descriptor rồi tuyên bố signature/binary compatibility vẫn hợp lệ. Thực hiện việc modular hóa theo license và phát hành version artifact mới có kiểm thử nếu được phép.

**Phương án C — Tạo runtime image chỉ gồm JDK modules, app/JARs ở ngoài.**

Đây là giải pháp được hỗ trợ khi cần dùng JARs còn chạy trên classpath. Ví dụ:

~~~bash
jdeps --multi-release 27 --class-path "lib/*" --print-module-deps app.jar
~~~

Đầu ra là điểm bắt đầu xác định JDK modules được tham chiếu tĩnh. Giả sử đã xác minh ứng dụng cần `java.base`, `java.sql` và `java.naming`:

~~~bash
jlink --add-modules java.base,java.sql,java.naming --output dist/jdk-only-runtime --compress=zip-6
~~~

Chạy với app/JARs **phân phối bên ngoài image**:

Linux/macOS:

~~~bash
./dist/jdk-only-runtime/bin/java --class-path "app.jar:lib/*" com.example.app.Main
~~~

Windows PowerShell:

~~~powershell
.\dist\jdk-only-runtime\bin\java.exe --class-path "app.jar;lib/*" com.example.app.Main
~~~

Ở đây `com.example.app.Main` là **tên class minh họa của một app không modular**, không phải module name. Các lệnh chỉ chạy khi `app.jar`, toàn bộ runtime JARs và entrypoint có thật. Phải phân phối **cả image lẫn JARs**, kiểm tra classpath và native resources.

### 16.2. Image chứa app module khác runtime chỉ chứa JDK modules

| Câu hỏi | App được link trong image | Chỉ link JDK runtime + external JARs |
| --- | --- | --- |
| App có explicit module descriptor? | Bắt buộc cho app module được jlink link | Không bắt buộc nếu chạy trên classpath |
| Application code nằm trong `lib/modules`? | Có nếu app module đã link | Không; app được phân phối riêng |
| Chạy app | `image/bin/java -m module/class` hoặc `--launcher` | `image/bin/java -cp ... MainClass` |
| Third-party automatic JAR có thể link trực tiếp? | Không | Có thể được phân phối riêng như classpath JAR |
| Cần quản lý dependencies khi deploy? | Modules đã link; external files vẫn cần nếu app dùng | Cả JARs, version, resources ngoài runtime |
| Dễ cập nhật app mà không tạo lại image? | Thường phải relink khi cập nhật module trong image | Có thể cập nhật app JAR, nhưng vẫn phải kiểm tra tương thích |
| Ai bảo trì bản vá JDK? | Chủ sở hữu image | Chủ sở hữu image |

**Không gọi phương án C là “ứng dụng đã được jlink thành module image”**; nó là **custom JDK runtime** được dùng để chạy một ứng dụng JAR bên ngoài.

### 16.3. Nếu app dùng cả named modules ngoài image

Có thể xây một runtime chỉ có JDK modules, rồi cung cấp application modular JARs trên `--module-path` lúc chạy. Cách này hợp lệ nếu graph/runtime image có đủ system modules và các thư viện được phân phối đúng. Nhưng khi app có external automatic modules, jlink vẫn **không thể link chúng vào image** — phải để chúng ngoài và xác minh được giải pháp chạy hợp lệ.

Đừng tùy tiện trộn classpath và module path nếu dependency không thể resolve. Với explicit named app module, `requires` tới một unnamed module thông thường **không hợp lệ**; migration JPMS cần xét toàn bộ graph.

## 17. Tích hợp jlink trong quy trình Maven, Gradle và CI

Một pipeline đáng tin cậy nên tách các bước:

~~~text
Checkout source
      │
      ▼
Chọn đúng JDK 27 (vendor + build + OS/arch)
      │
      ▼
Maven/Gradle:
  compile → unit tests → package modular JARs
      │
      ▼
Chuẩn bị module-path đủ artifacts/dependencies
      │
      ▼
jdeps / module graph checks (khi cần)
      │
      ▼
jlink vào thư mục image sạch
      │
      ▼
Smoke test bằng image/bin/java, bin/launcher
      │
      ▼
Integration tests: I/O, services, crypto, locale, DB...
      │
      ▼
Ký số / checksum / SBOM / archive hoặc container
      │
      ▼
Publish artifact được phê duyệt, triển khai theo platform
~~~

### 17.1. Maven: không nhầm phase package với jlink

`mvn package` thông thường tạo JAR/WAR; **không tự động** tạo custom runtime image nếu chưa có plugin/build integration thực hiện `jlink`.

Ví dụ thứ tự tác vụ theo ý tưởng:

~~~bash
mvn verify
# Sau khi có modular JARs, chuẩn bị module-path vào thư mục staging.
jlink --module-path staging/modules --add-modules com.example.app --launcher hello=com.example.app/com.example.app.Main --output dist/hello-runtime
~~~

`staging/modules` là **đường dẫn minh họa** phải được pipeline chuẩn bị với modular JARs đầy đủ. Không giả định `target/` có sẵn tất cả dependencies hoặc toàn bộ JARs đã modular hóa.

Một Maven plugin có thể hỗ trợ `jlink` theo lifecycle, nhưng version, goal names và plugin capabilities phụ thuộc plugin được chọn. Kiểm tra tài liệu plugin hiện hành; không chép cấu hình plugin cũ thiếu kiểm thử với Java 27.

### 17.2. Gradle: task graph cần ràng buộc inputs/outputs

Tương tự, `./gradlew build` tạo/kiểm tra artifacts theo tasks được cấu hình, **không tự tạo jlink image** nếu build chưa có task/plugin thực hiện việc đó.

Một thiết kế Gradle task/link integration cần:

- Phụ thuộc vào tasks tạo modular JAR artifacts.
- Resolve runtime modules vào tập input có thể tái hiện.
- Chỉ rõ JDK toolchain/linker phù hợp.
- Khai báo output directory và đảm bảo tác vụ không lén chỉnh output của tasks khác.
- Có một smoke-test task thật sự khởi động **launcher trong runtime image**.
- Không chạy `jlink` ngay trong configuration phase chỉ vì một build script được đánh giá.
- Kiểm tra khả năng caching/incremental thực tế; custom task có side effects cần task inputs/outputs rõ.

Nếu dùng một plugin có sẵn, phải xác minh nó hỗ trợ Java 27, cách đặt tên modules, service binding và JDK distribution định dùng. Không chỉ dựa vào việc task Gradle chạy thành công một lần trên máy phát triển.

### 17.3. Ví dụ script từng bước có thể tái hiện

Với các file nguồn từ phần 4 đã được tạo và đang dùng Linux/macOS:

~~~bash
mkdir -p mods dist
javac --module-source-path src -d mods --module com.example.greetings,com.example.app
java --module-path mods --module com.example.app/com.example.app.Main
jdeps --module-path mods --check com.example.app
jlink --module-path mods --add-modules com.example.app --launcher hello=com.example.app/com.example.app.Main --output dist/hello-runtime --compress=zip-6
./dist/hello-runtime/bin/java --list-modules
./dist/hello-runtime/bin/hello "CI"
~~~

Kết quả dòng cuối:

~~~text
Xin chào, CI
~~~

**Điều kiện:** `dist/hello-runtime` phải chưa tồn tại, và JDK/build environment hỗ trợ linking. Trong CI, sử dụng staging/output riêng cho mỗi run để không cần xóa tùy tiện artifact của lần build khác.

Tương đương trên Windows thay executable của image bằng `.\dist\hello-runtime\bin\hello.exe`; các lệnh JDK `javac`/`jdeps`/`jlink` vẫn dùng cùng các tham số về module.

### 17.4. Tách publish khỏi build/test

Link xong **không tự publish** image lên registry/repository hay triển khai nó. CI nên:

1. Sinh artifact có định danh version/build rõ.
2. Chạy smoke và integration tests trên artifact đó.
3. Tính checksum, tạo metadata/SBOM và ký theo chính sách.
4. Cất artifact đã kiểm thử vào repository có kiểm soát.
5. Chỉ publish/deploy qua stage có quyền phù hợp.

Đừng rebuild lại bằng một JDK khác ở stage deploy rồi giả định image mới giống image đã test.

## 18. Bảo trì và an ninh custom runtime images

**Đây là trách nhiệm bắt buộc khi dùng jlink:** chủ sở hữu phải **tự cập nhật runtime image**. Việc JDK trên máy build hoặc máy chạy đã cập nhật **không tự động thay các runtime binaries đã link nằm trong image cũ**.

### 18.1. Khi có bản vá JDK

Quy trình đúng:

1. Chọn **JDK 27 build đã vá** từ nguồn đáng tin, hoặc release đích mới theo chính sách vòng đời hỗ trợ của tổ chức.
2. Cập nhật build provenance và toolchain version.
3. Build lại modular artifacts nếu thay đổi compiler/toolchain đòi hỏi.
4. Chạy `jlink` lại từ JDK đã vá để tạo **image mới**.
5. Kiểm thử hành vi, security providers, locale/timezone, native libraries và startup.
6. Phát hành artifact/image mới và triển khai có kiểm soát.
7. Xác minh `image/bin/java --version` ở chính artifact production.

**Không** sửa thủ công `lib/modules` hoặc chép vài file `.dll`/`.so` từ một JDK update khác rồi xem đó là vá runtime. Các thành phần native/modules có thể phụ thuộc lẫn nhau.

### 18.2. Minimal image không đồng nghĩa image bảo mật

Một image chỉ chứa một số module vẫn có thể:

- Bao gồm thư viện có CVE nếu JDK version chưa được vá.
- Dùng TLS truststore/certificates sai hoặc thiếu.
- Bị cấu hình chạy quyền root quá rộng.
- Chứa secret được đóng gói nhầm.
- Dùng third-party native library/JAR có lỗ hổng.
- Không có khả năng logging/monitoring cần thiết để phát hiện sự cố.

**Giảm attack surface bằng cách loại modules không cần** là một lợi ích, nhưng vẫn phải thực hiện dependency scanning, container hardening, secret management và patch management.

### 18.3. Chữ ký và thông tin license

`--ignore-signing-information` có thể làm linker bỏ những signature-related entries của signed modular JARs. Đây không phải một flag “giúp build nhanh” vô hại. Nếu gặp lỗi về signed JAR:

- Xác minh JAR thật, nguồn phát hành và chữ ký.
- Đối chiếu chính sách xử lý signed artifacts khi liên kết.
- Không bật flag này trong CI production nếu chưa được nhóm security/legal phê duyệt.
- Lưu license notices và attribution khi phân phối runtime/JARs theo yêu cầu của distribution.

Các tệp trong `legal/` có thể phục vụ điều kiện giấy phép. Không xóa riêng thư mục pháp lý chỉ để giảm một vài KB.

### 18.4. Chính sách artifact có thể tái hiện

Lưu trong release metadata:

- JDK vendor, `java.version`, `java.runtime.version` và build.
- OS, architecture, native runtime requirements.
- Maven/Gradle toolchain và plugin versions.
- Module graph / `--add-modules` / `--bind-services` / compression flags.
- Versions, checksums và provenance của modular JARs.
- Binary checksum của image archive/container artifact.
- Kết quả smoke/integration tests và security scan.

Cố định toàn bộ đầu vào giúp tạo lại image khi có sự cố. **Không giả định** việc hai lệnh `jlink` cùng text luôn tạo byte-for-byte identical archives giữa các JDK vendors/OSes.

## 19. Chẩn đoán lỗi jlink phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `Module ... not found` | Sai tên module; thiếu user JAR hoặc system module | `jar --describe-module`, `--module-path`, `jlink --help` |
| `automatic module cannot be used with jlink` | JAR không có explicit descriptor | Dùng modular JAR thật hoặc runtime-only image |
| `java.base` không được tìm thấy | JDK thiếu JMODs và không hỗ trợ linking-from-runtime, hoặc path sai | `jlink --help` capabilities; đúng JDK |
| `Error: directory ... already exists` | Output directory đã tồn tại | Dùng output mới/clean staging có kiểm soát |
| Split package / reads conflict | Hai modules sở hữu/export cùng package xung đột | Đọc descriptor, loại JAR trùng, sửa module graph |
| Image chạy `java --version` được nhưng app không chạy | Chưa link app module, main class sai hoặc thiếu dependency | `image/bin/java --list-modules`, launcher, `-m` |
| `NoClassDefFoundError` sau khi link | Dependency động/JAR ngoài image bị thiếu | JFR/stack, `jdeps` và runtime classpath |
| `ServiceConfigurationError` | Thiếu provider, sai descriptor hoặc provider không khởi tạo được | `uses`/`provides`, `--bind-services`, `--suggest-providers` |
| JDBC báo không có driver | `java.sql` đã có nhưng driver provider/JAR chưa có | Driver module name, classpath/service discovery |
| HTTPS/TLS lỗi trên image | Crypto provider, truststore hoặc native/security config thiếu | Security modules, trust anchors, endpoint test |
| Locale/charset sai | Đã cắt module/data cần thiết | `jdk.localedata`/`jdk.charsets`, integration tests |
| `UnsatisfiedLinkError` | Native library sai OS/arch hoặc không được đóng gói | Runtime architecture, system libs và JNI paths |
| Image chạy trên máy build nhưng không chạy trên target | OS/CPU/ABI khác hoặc thiếu shared libs | Build platform matrix, `file`/`ldd` theo nền tảng |
| `jpackage` fail sau jlink | Runtime image không phù hợp packaging/launcher | `jpackage --verbose`, image layout, tool versions |
| Image quá lớn | `--bind-services`/`ALL-MODULE-PATH` hoặc nhiều providers | `--list-modules`, so sánh graphs, chọn roots |
| Không thể dùng `jcmd` trong container | Minimal image không bao gồm diagnostic tool | Dùng JDK tool ngoài image hoặc cấu hình quan sát phù hợp |
| Build lại image mới vẫn có CVE | CI dùng JDK base cũ hoặc dependency chưa vá | `image/bin/java --version`, provenance, security scan |

### 19.1. Đầu tiên kiểm tra đúng công cụ

~~~bash
java -version
jlink --version
jlink --help
jlink --list-plugins
~~~

Nếu JDK trong `PATH` không khớp JDK được toolchain/CI chọn, hãy chỉ rõ đường dẫn đến `bin/jlink` của JDK phù hợp. Không giả định `JAVA_HOME` và `PATH` luôn đồng nhất.

### 19.2. Kiểm tra input trước khi link

~~~bash
java --module-path lib --list-modules
jar --describe-module --file lib/com.example.app.jar
jdeps --module-path lib --check com.example.app
~~~

`java --list-modules` hiển thị các modules observable trong configuration được chỉ định, **không có nghĩa tất cả sẽ được link**. `jdeps` giúp kiểm tra phụ thuộc tĩnh nhưng không khám phá được mọi service/provider qua config.

### 19.3. Kiểm tra image sau khi link

Linux/macOS:

~~~bash
./dist/hello-runtime/bin/java --version
./dist/hello-runtime/bin/java --list-modules
./dist/hello-runtime/bin/java --module com.example.app/com.example.app.Main
~~~

Windows PowerShell:

~~~powershell
.\dist\hello-runtime\bin\java.exe --version
.\dist\hello-runtime\bin\java.exe --list-modules
.\dist\hello-runtime\bin\java.exe -m com.example.app/com.example.app.Main
~~~

Nếu lệnh thứ ba chạy được nhưng `bin/hello` không chạy, kiểm tra `--launcher` mapping và native executable permissions. Nếu cả hai đều lỗi, kiểm tra main class/module descriptor và thông báo exception.

### 19.4. Không “sửa” module thiếu bằng ALL-MODULE-PATH vô điều kiện

`--add-modules ALL-MODULE-PATH` có thể đưa vào quá nhiều modules quan sát được, làm image lớn và gây xung đột. Nó là tùy chọn có ý nghĩa trong một số tác vụ kỹ thuật, nhưng **không phải cách sửa mặc định** cho một dependency sai tên hoặc provider thiếu.

Cách sửa tốt hơn là:

1. Xác định module thực sự thiếu.
2. Tìm vì sao dependency đó không được resolve.
3. Khai `requires`/`uses`/`provides` đúng nếu sở hữu code.
4. Bổ sung provider root chính xác hoặc service binding khi có lý do.
5. Chạy lại jlink và integration tests.

## 20. Kịch bản kiểm thử runtime image theo chức năng

Một image được tạo thành công chưa chắc chạy được ứng dụng production. Cần một tập test có kiểm chứng các module/resources quan trọng.

### 20.1. Tầng kiểm tra cơ bản

- `image/bin/java --version` báo runtime đúng version và vendor mong đợi.
- `image/bin/java --list-modules` chứa root module và các dependencies cần thiết.
- Launcher sinh từ `--launcher` mở được app với input mẫu và trả exit code mong muốn.
- Thư mục app image có toàn bộ tệp cần thiết; không phụ thuộc ngầm vào full JDK trên PATH.
- Trên máy target tương thích, thử chạy khi **không có JDK khác** được cấu hình trong PATH.

### 20.2. Tầng chức năng ứng dụng

- HTTP client/server kết nối được theo security/TLS policy.
- JDBC driver được phát hiện và kết nối được tới database test.
- JSON/DI/ORM/reflection vẫn truy cập được các modules/packages đã export/open phù hợp.
- `ServiceLoader` tìm được providers cần thiết.
- Locale, charset, timezone và resource bundles trả kết quả mong đợi.
- Native/JNI dependencies được load đúng.
- Config files, templates và application resources có mặt đúng path.
- Logging/tracing/metrics/profiling hoạt động theo yêu cầu vận hành.
- Graceful shutdown và signal handling không khác kỳ vọng khi chạy qua launcher.

### 20.3. Tầng deployment và bảo trì

- Artifact chạy đúng OS/arch/ABI.
- Cài đặt quyền thực thi và sở hữu file phù hợp, không chạy thừa quyền.
- Không có secret trong image, JAR hoặc command-line arguments được log.
- Scan dependencies/JDK modules với cơ sở dữ liệu CVE cập nhật.
- Có đường tái tạo image từ JDK đã vá và module artifacts đã pin version.
- Có hướng dẫn rollback/roll-forward giữa các image versions.
- Đã lưu checksums, SBOM/provenance và license notices.
- Performance test xác nhận size/startup/throughput không giảm ngoài ngân sách cho phép.

## 21. Checklist thực hành jlink trên Java 27

- [ ] Xác định rõ mục tiêu: **link ứng dụng vào image** hay chỉ tạo **JDK runtime image cho JARs bên ngoài**.
- [ ] Dùng đúng JDK 27 build/toolchain, xác minh `java` và `jlink` cùng nguồn phù hợp.
- [ ] Kiểm tra JDK có `jmods` hoặc có `Linking from run-time image enabled` theo JEP 493.
- [ ] Có explicit module descriptor hợp lệ cho các application/library modules cần link.
- [ ] Không nhầm automatic module với explicit module mà jlink có thể link.
- [ ] `--module-path` bao gồm toàn bộ input modules cần thiết.
- [ ] `--add-modules` dùng **module names**, không dùng JAR filenames/class names.
- [ ] Từng module có `requires`/`exports`/`opens` đúng theo API contract.
- [ ] Đã kiểm tra module graph bằng `jdeps` và chạy app trên module path trước khi link.
- [ ] Xem xét service loading: `uses`/`provides`, providers explicit hoặc `--bind-services` có kiểm soát.
- [ ] Kiểm tra provider modules: JDBC, crypto, charset, locale, logging và những dịch vụ thật sự sử dụng.
- [ ] Dùng cú pháp nén hiện hành `--compress=zip-0` tới `zip-9`; không đưa `--compress=2` vào cấu hình mới.
- [ ] Không cắt bỏ thủ công `lib/`, `conf/security/` hoặc legal notices chỉ để giảm size.
- [ ] Image được tạo vào output directory mới, tách biệt giữa các build jobs.
- [ ] Có thể chạy `image/bin/java --list-modules` và entrypoint **từ chính image**.
- [ ] Đã test trên đúng OS/architecture/runtime dependencies của máy đích.
- [ ] Phân phối **toàn bộ thư mục image**, bảo toàn permissions/symlinks.
- [ ] Nếu dùng `jpackage`, đã xác minh application image/installer thực sự cài và chạy được.
- [ ] Đã xác nhận config, certificates, secrets và external resources được cung cấp đúng cách.
- [ ] Đã thử startup, chức năng, GC/memory/performance và diagnostics cần thiết.
- [ ] Có CI để build lại image khi JDK có bản vá, không dựa vào việc cập nhật JDK ngoài image.
- [ ] Có metadata về JDK vendor/build, module graph, input artifacts, checksum và provenance.
- [ ] Không dùng `--ignore-signing-information` hoặc `ALL-MODULE-PATH` vô điều kiện để che lỗi.
- [ ] Nếu image nhỏ hơn, đã đo startup/throughput và xác nhận các chức năng vẫn nguyên vẹn.

## 22. Nguồn tài liệu chính thức và tham khảo

- [Java SE 27 — The jlink Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jlink.html) — syntax, module path, root modules, launchers, compression, plugins, service binding và runtime images.
- [Java SE 27 — The jdeps Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html) — phân tích module graph, `--check` và `--print-module-deps`.
- [Java SE 27 — The jmod Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jmod.html) — JMOD files, native/config resources và phân biệt JMOD với runtime JAR.
- [Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — `--module-path`, `--module`, `--list-modules` và `--describe-module`.
- [Java SE 27 — The javac Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — `--module-source-path` và compile modular Java sources.
- [Java SE 27 — The jar Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html) — tạo và kiểm tra modular JARs.
- [Java SE 27 — The jpackage Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jpackage.html) — tạo application images/native installers và sử dụng `--runtime-image`.
- [Java SE 27 — java.lang.module](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/module/package-summary.html) — JPMS resolution và configuration model.
- [Java SE 27 — java.util.ServiceLoader](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ServiceLoader.html) — cơ chế tìm/khởi tạo service providers.
- [JEP 282 — jlink: The Java Linker](https://openjdk.org/jeps/282) — thiết kế công cụ Java linker.
- [JEP 261 — Module System](https://openjdk.org/jeps/261) — ngữ nghĩa Java Platform Module System.
- [JEP 493 — Linking Run-Time Images without JMODs](https://openjdk.org/jeps/493) — JDK vendor build capability, không cần JMODs khi được bật.

**Kết luận:** `jlink` trong Java 27 biến một **tập named modules và dependency graph hợp lệ** thành một **custom runtime image** chứa JVM và đúng những module được chọn. Quy trình an toàn là **biên dịch thành modular artifacts → xác minh module graph → link bằng `jlink` → chạy/kiểm thử bằng JVM trong image → đóng gói theo nền tảng → phát hành và bảo trì bản vá**. Đừng nhầm image với native executable, đừng giả định automatic JARs hay dynamic service providers luôn được link, và không dùng flag nén/quan niệm JMOD lỗi thời khi JDK distribution đã hỗ trợ cách mới.
