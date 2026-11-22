# Giới hạn của ký tự đại diện trong đường dẫn phụ thuộc (Java classpath)

## 1. Classpath wildcard dùng để giải quyết vấn đề gì?

Khi biên dịch hoặc chạy Java theo **classpath**, chương trình thường cần nhiều thư viện đã đóng gói thành JAR. Có thể liệt kê từng thư viện:

~~~bash
java -cp 'build/classes:lib/alpha.jar:lib/beta.jar' demo.app.Main
~~~

Cách này chính xác nhưng bất tiện khi thư mục chứa nhiều JAR. Cú pháp **classpath wildcard** cho phép thay danh sách các JAR nằm ngay trong một thư mục bằng ký tự `*` ở **thành phần cuối của đường dẫn**, ví dụ:

~~~bash
java -cp 'build/classes:lib/*' demo.app.Main
~~~

Lệnh trên sử dụng classpath với hai entry logic: thư mục chứa class của ứng dụng và tập các JAR được mở rộng từ `lib/*`. Wildcard này **không phải cơ chế tìm file tùy ý**, không tự tải dependency từ Internet, không đọc metadata phiên bản Maven và không tự thu thập JAR nằm trong các thư mục con.

Bài này tập trung vào giới hạn của wildcard trong **đường dẫn phụ thuộc**, khi dùng `javac` và `java` với JDK 17+; đồng thời giải thích lúc nào cần đường dẫn tường minh hoặc công cụ build để tránh lỗi khó tái hiện.

## 2. Cú pháp được hỗ trợ: entry có basename là dấu *

Trong classpath của Java launcher, entry dạng `lib/*` biểu diễn **các tệp có đuôi `.jar` hoặc `.JAR` nằm trực tiếp trong thư mục `lib`**. Một entry chỉ chứa `*` biểu diễn các JAR ngay trong thư mục làm việc hiện tại.

Ví dụ thư mục:

~~~text
project/
├── lib/
│   ├── alpha.jar
│   ├── beta.JAR
│   ├── .hidden.jar
│   ├── old.zip
│   ├── Extra.class
│   ├── classes/
│   │   └── demo/Helper.class
│   └── nested/
│       └── gamma.jar
└── build/
    └── classes/
        └── demo/app/Main.class
~~~

Khi dùng `lib/*`, những gì xảy ra là:

| Đường dẫn | Được `lib/*` nhận? | Lý do |
| --- | --- | --- |
| `lib/alpha.jar` | Có | JAR trực tiếp trong `lib` |
| `lib/beta.JAR` | Có | Đuôi `.JAR` cũng được hỗ trợ |
| `lib/.hidden.jar` | Có | File JAR ẩn vẫn nằm trong phạm vi |
| `lib/old.zip` | Không | Wildcard chỉ chọn đuôi `.jar`/`.JAR`, dù ZIP có thể được liệt kê tường minh trong classpath |
| `lib/Extra.class` | Không | Không thu thập file `.class` rời |
| `lib/classes/demo/Helper.class` | Không | Không thêm thư mục class vào classpath |
| `lib/nested/gamma.jar` | Không | Không quét đệ quy thư mục con |
| `build/classes/demo/app/Main.class` | Không | `build/classes` là entry riêng, không nằm trong `lib/*` |

Cú pháp `lib/*.jar` **không phải mẫu classpath wildcard được Java định nghĩa**; dấu sao của tiện ích classpath là một *basename* `*` của entry, không phải một mẫu lọc đuôi do người dùng tự viết. Tương tự, `lib/**`, `lib/a*.jar` và `lib/{a,b}.jar` không phải cú pháp wildcard JAR do Java launcher cung cấp. Nếu một lệnh với các mẫu đó dường như hoạt động, có thể shell hoặc công cụ bao ngoài đã xử lý chúng **trước** khi Java nhận đối số.

**Hệ quả thực tế:** nếu ứng dụng cần class rời nằm trong `lib/classes`, hãy thêm thư mục này thành **entry riêng**; nếu cần JAR ở `lib/nested`, phải khai báo thêm `lib/nested/*` hoặc đường dẫn JAR cụ thể.

## 3. “Mở rộng wildcard” là gì và diễn ra lúc nào?

Classpath là danh sách các vị trí mà class loader/tool compiler sẽ dùng để tìm class hoặc resource phù hợp theo cơ chế classpath. Mỗi entry có thể là thư mục class, một file JAR/ZIP được hỗ trợ hoặc một entry wildcard JAR.

Với lệnh:

~~~bash
java -cp 'build/classes:lib/*' demo.app.Main
~~~

Java launcher mở rộng `lib/*` thành danh sách các JAR trực tiếp trong `lib` **trước khi vào phương thức `main`**. Diễn giải sơ đồ:

~~~text
Input classpath       build/classes : lib/*
                            |
                            v
Java launcher      liệt kê các JAR nằm ngay trong lib/
                            |
                            v
Classpath runtime  build/classes : lib/alpha.jar : lib/beta.JAR : ...
                            |
                            v
                     tải demo.app.Main
~~~

Dấu `:` trong sơ đồ là separator trên Linux/macOS. Windows dùng `;`. Khi JAR tồn tại, property `java.class.path` của JVM thường phản ánh danh sách đường dẫn đã mở rộng; **không dùng thứ tự của chuỗi đó làm hợp đồng ổn định**.

Một JAR mới đặt vào `lib` sau khi JVM đã khởi chạy **không tự động được wildcard thu thập lại**. Thao tác mở rộng diễn ra trước khi chạy ứng dụng, không phải mỗi khi class loader tìm một class. Muốn thay đổi tập thư viện của một tiến trình đã chạy phải dùng cơ chế class loading phù hợp, hoặc khởi động lại với classpath mới.

Cần phân biệt đây là tiện ích của **Java launcher/JDK tools**. Một ứng dụng tự nhúng JVM hoặc tự xây class loader không bắt buộc hỗ trợ wildcard trong chuỗi đầu vào của riêng nó.

## 4. Shell wildcard khác Java classpath wildcard

Có hai bộ xử lý hoàn toàn khác nhau cùng dùng dấu `*`:

- **Shell expansion/globbing:** trước khi chạy chương trình, shell có thể thay `lib/*` bằng nhiều tên file và thư mục.
- **Java classpath expansion:** Java launcher nhận **một classpath argument** chứa ký tự `*`, rồi mở rộng các JAR theo quy tắc riêng.

Trên Bash, hãy **quote toàn bộ classpath**:

~~~bash
# Bash/Linux/macOS: cú pháp nên dùng
javac -cp 'lib/*' -d build/classes src/demo/app/Main.java
java -cp 'build/classes:lib/*' demo.app.Main
~~~

Dùng dấu nháy đơn ở đây giúp Bash gửi nguyên chuỗi `lib/*` hoặc `build/classes:lib/*` cho Java. Nếu không quote, shell có thể mở rộng `lib/*` trước thành nhiều đối số độc lập. Khi đó `-cp` chỉ lấy một đối số làm classpath, các tên file tiếp theo có thể bị hiểu nhầm là class chính, source file hoặc một đối số sai; kết quả phụ thuộc shell và nội dung thư mục.

Trong PowerShell trên Windows, cũng nên quote:

~~~powershell
# Windows: separator giữa các classpath entries là dấu chấm phẩy.
javac -cp 'lib/*' -d build/classes src/demo/app/Main.java
java -cp 'build/classes;lib/*' demo.app.Main
~~~

Dấu `;` là ký tự cú pháp của PowerShell nếu không nằm trong chuỗi, nên quote cả biểu thức classpath. Trên Windows khi gọi trực tiếp `java.exe` và `javac.exe`, Java vẫn nhận entry `lib/*` theo quy tắc của Java launcher, dù cách shell xử lý wildcard không giống Bash.

**Ba ý nghĩa dấu sao không được lẫn:**

| Biểu thức | Ai xử lý? | Nghĩa |
| --- | --- | --- |
| `lib/*` trong đối số `-cp` đã được quote | Java launcher/tool classpath | Các JAR ngay trong `lib` |
| `src/*.java` trong lệnh shell không quote | Shell nếu nó hỗ trợ glob | Mẫu tên file nguồn cấp cho `javac` |
| `import demo.lib.*;` trong Java source | Java compiler theo quy tắc import | Import-on-demand các type thích hợp của package, không quét thư mục/JAR và không import package con |

Trong `javac`, **classpath wildcard không phải wildcard để chọn source files**. Công cụ có tùy chọn nguồn và quy tắc chọn compilation units riêng; muốn compile mọi file `.java`, dùng source set/build tool hoặc danh sách file phù hợp, không suy từ `-cp 'src/*'`.

## 5. Ví dụ Java 17+ chạy được: đóng gói JAR rồi dùng wildcard

Ví dụ sau tạo **một dependency JAR** do chính ta xây, compile ứng dụng dựa trên JAR đó và chạy với classpath wildcard. Không cần Internet hay dependency ngoài JDK.

Cấu trúc đầu vào:

~~~text
project/
├── src/
│   ├── library/demo/lib/Message.java
│   └── app/demo/app/Main.java
├── lib/            # nhận file JAR sau khi đóng gói
└── build/          # nhận .class sau khi biên dịch
~~~

### 5.1. Source thư viện: `src/library/demo/lib/Message.java`

~~~java
package demo.lib;

public final class Message {
    private Message() {}

    public static String text() {
        return "JAR_OK";
    }
}
~~~

### 5.2. Source ứng dụng: `src/app/demo/app/Main.java`

~~~java
package demo.app;

import demo.lib.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
~~~

Hai class ở hai package khác nhau. App cần thư viện tại **compile time** để resolve `demo.lib.Message`, và ở **runtime** để thực thi lời gọi `Message.text()`.

### 5.3. Chạy trên Bash/Linux/macOS/Git Bash

Từ thư mục `project/` chứa `src/`, sau khi tạo đúng hai file trên:

~~~bash
mkdir -p build/library build/app lib

# Compile thư viện từ source.
javac --release 17 -encoding UTF-8 -d build/library src/library/demo/lib/Message.java

# Đóng các class thư viện thành JAR.
jar --create --file lib/message.jar -C build/library .

# Compile app: javac sẽ mở rộng 'lib/*' thành các JAR trực tiếp trong lib/.
javac --release 17 -encoding UTF-8 -cp 'lib/*' -d build/app src/app/demo/app/Main.java

# Chạy: phải có cả app classes và dependency JAR.
java -cp 'build/app:lib/*' demo.app.Main
~~~

Stdout của lệnh `java` cuối cùng là:

~~~text
JAR_OK
~~~

Những lệnh `javac` và `jar` thành công thông thường không in dòng output nào đáng chú ý. Trong ví dụ này, file `lib/message.jar` chứa `demo/lib/Message.class`; `build/app` chứa `demo/app/Main.class`.

Có thể kiểm tra nội dung thư viện bằng:

~~~bash
jar --list --file lib/message.jar
~~~

Danh sách có thể gồm các entry metadata như `META-INF/` và `META-INF/MANIFEST.MF`, cùng `demo/lib/Message.class`. Thứ tự danh sách không phải đối tượng cần kiểm tra.

### 5.4. Chạy trên Windows/PowerShell

Các bước tạo thư mục và classpath tương ứng:

~~~powershell
New-Item -ItemType Directory -Force build/library, build/app, lib | Out-Null
javac --release 17 -encoding UTF-8 -d build/library src/library/demo/lib/Message.java
jar --create --file lib/message.jar -C build/library .
javac --release 17 -encoding UTF-8 -cp 'lib/*' -d build/app src/app/demo/app/Main.java
java -cp 'build/app;lib/*' demo.app.Main
~~~

Stdout:

~~~text
JAR_OK
~~~

Đường dẫn tới các file nguồn dùng dấu `/` như trên được công cụ Java và PowerShell chấp nhận trong ngữ cảnh thông thường; sự khác biệt cần chú ý nhất là **classpath separator**.

### 5.5. Hai lỗi có chủ đích để phân biệt classpath

**Lỗi biên dịch:** nếu chuyển `message.jar` sang nơi khác rồi chạy lệnh `javac -cp 'lib/*' ...`, compiler không thể resolve `demo.lib.Message`, vì wildcard không tìm thấy dependency. Thông báo cụ thể phụ thuộc JDK, thường thuộc nhóm `package demo.lib does not exist` hoặc `cannot find symbol`.

**Lỗi chạy:** ngay cả khi `lib/message.jar` còn tồn tại, lệnh dưới đây không có entry cho **app classes**:

~~~bash
java -cp 'lib/*' demo.app.Main
~~~

Trong ví dụ này `demo.app.Main` chỉ nằm trong `build/app`, nên Java không thể nạp main class. **Wildcard chỉ bổ sung các JAR trong `lib`, không bổ sung mọi class output của dự án.**

Nếu app có thể khởi động nhưng dùng thư viện bị thiếu lúc runtime, có thể gặp `NoClassDefFoundError`, lỗi linkage khác hoặc lỗi khi đường thực thi chạm tới mã đó; không kết luận chỉ từ việc compile thành công rằng runtime đã có đủ dependencies.

## 6. Không quét đệ quy và không thu thập class directory

Ví dụ:

~~~text
lib/
├── core.jar
├── drivers/
│   ├── jdbc-one.jar
│   └── jdbc-two.jar
└── classes/
    └── sample/Plugin.class
~~~

`lib/*` chỉ nhận `core.jar`. Muốn bổ sung hai JAR trong `drivers` và class rời trong `classes`, cần liệt kê ba entry logic:

~~~bash
# Bash/Linux/macOS:
java -cp 'build/app:lib/*:lib/drivers/*:lib/classes' demo.app.Main
~~~

Tương ứng trên Windows:

~~~powershell
java -cp 'build/app;lib/*;lib/drivers/*;lib/classes' demo.app.Main
~~~

Giải thích:

- `lib/*` → JAR ở mức trực tiếp của `lib`.
- `lib/drivers/*` → JAR ở mức trực tiếp của `lib/drivers`.
- `lib/classes` → **directory entry**, cho phép tìm `lib/classes/sample/Plugin.class` theo package tương ứng.

Không dùng `lib/**` như kỳ vọng recursive glob của Bash, Gradle hoặc công cụ tìm file; đó không phải cách mở rộng classpath wildcard trong Java. Nếu cấu trúc thư viện có hàng trăm thư mục con, nên quản lý dependency bằng cấu hình build có danh sách rõ ràng thay vì tự duy trì các wildcard rải rác.

Một file ZIP có bytecode và được công cụ Java hỗ trợ như classpath archive có thể được nêu **tường minh**, ví dụ `lib/special.zip`. Nhưng `lib/*` không thu thập nó, bởi tiêu chí wildcard là **đuôi tên file JAR**, không phải kiểm tra nội dung archive.

## 7. Thứ tự JAR không được bảo đảm: nguy cơ duplicate classes và resource

Đây là giới hạn quan trọng khi `lib/*` chứa nhiều JAR:

~~~text
lib/
├── api-v1.jar     # có demo.api.Service
├── api-v2.jar     # cũng có demo.api.Service
└── client.jar
~~~

Nếu hai JAR cung cấp cùng fully qualified class, class loader trên classpath thông thường tìm class theo thứ tự các entry. Nhưng **thứ tự liệt kê các JAR do `lib/*` mở rộng không được quy định ổn định**. Không nên dựa vào tên file theo alphabet hay thứ tự quan sát được trong một lần chạy để quyết định `api-v1.jar` hoặc `api-v2.jar` thắng.

Hậu quả có thể là:

- App chạy trên máy này nhưng gặp `NoSuchMethodError` hoặc `NoSuchFieldError` trên máy khác do phiên bản class được nạp không như kỳ vọng.
- Một resource trùng tên xuất hiện ở nhiều JAR; mã dùng `getResource`/class loader có thể chọn bản đầu tiên theo thứ tự tìm kiếm, dẫn đến khác biệt khó chẩn đoán.
- Class compile từ phiên bản API này nhưng runtime lại thấy phiên bản khác, gây lỗi linkage khi thực thi.

Giải pháp là đảm bảo **chỉ một phiên bản hợp lệ** của mỗi dependency cần thiết được chọn, và nếu cần thứ tự ưu tiên, **liệt kê JAR tường minh** trên classpath hoặc để dependency resolver của Gradle/Maven quyết định phiên bản.

Ví dụ classpath có thứ tự xác định theo ý người cấu hình (trong phạm vi những entry được liệt kê):

~~~bash
java -cp 'build/app:lib/api-v2.jar:lib/client.jar' demo.app.Main
~~~

Trong ví dụ đó, mọi class cần thiết phải thực sự có trong các JAR được liệt kê. Dù thứ tự entry tường minh giúp bạn kiểm soát tìm class, **không** nên dựa vào duplicate classes để xử lý phiên bản; hãy loại bỏ bản trùng và dùng build dependency graph rõ ràng.

Wildcard cũng bao gồm các JAR ẩn ở cấp thư mục hiện tại. Vì vậy, một file `.hidden.jar`, JAR backup hoặc bản thư viện chưa được rà soát nhưng có đuôi phù hợp trong `lib` có thể gia nhập classpath ngoài ý muốn. Nên quản lý nội dung thư mục `lib` thay vì xem đó là một “hộp thả JAR bất kỳ”.

## 8. Wildcard không giải quyết dependency transitively

Giả sử `analytics.jar` gọi API từ `json.jar`:

~~~text
lib/
├── analytics.jar
└── json.jar
~~~

`lib/*` có thể đưa **cả hai** vào classpath vì chúng cùng nằm trực tiếp trong thư mục. Nhưng không có nghĩa Java đã hiểu rằng `analytics.jar` *phụ thuộc* `json.jar`. Launcher chỉ mở rộng tên file; nó không đọc và giải Maven POM/Gradle metadata để tải JAR còn thiếu, chọn phiên bản phù hợp hay giải quyết version conflict.

Nếu `json.jar` không có trong `lib` mà nằm dưới `lib/transitive/json.jar`, wildcard của `lib` sẽ không tự đi xuống để tìm nó. Nếu dependency có native library, data file, cấu hình hay module service providers cần thiết thì chỉ thêm JAR cũng có thể chưa đủ điều kiện chạy.

Vì vậy:

- Với bài tập rất nhỏ hoặc một bộ JAR đã đóng gói sẵn, `lib/*` thuận tiện.
- Với dự án có dependency graph nhiều tầng hoặc yêu cầu tái lập, dùng Gradle/Maven để pin và resolve phụ thuộc, sau đó cung cấp classpath runtime được công cụ build tạo.
- Với sản phẩm phân phối, cân nhắc manifest classpath hợp lệ, startup script rõ ràng hoặc cách đóng gói theo tiêu chuẩn công cụ, thay vì kỳ vọng wildcard tự xử lý mọi dependency.

## 9. javac và java đều cần classpath đúng pha

`javac` cần **compile classpath** để tìm API mà Java source đang dùng. `java` cần **runtime classpath** để tải class và resources khi chương trình chạy.

Trong ví dụ mục 5:

~~~text
Compile library:
  source       src/library/demo/lib/Message.java
  output       build/library

Package library:
  input        build/library
  output       lib/message.jar

Compile app:
  source       src/app/demo/app/Main.java
  classpath    lib/*
  output       build/app

Run app:
  main         demo.app.Main
  classpath    build/app + lib/*
~~~

Thêm `-cp 'lib/*'` khi compile không khiến JAR trở thành một phần của output `build/app`. Lệnh `javac -d build/app` chỉ ghi classes do compiler tạo. Tại runtime phải bổ sung dependency JAR vào classpath, trừ khi bạn đã có cơ chế đóng gói hợp lệ khác chứa dependency.

Ngược lại, thêm `build/app` vào runtime classpath không tự đưa JAR vào; các lỗi dependency chỉ xuất hiện ở các code path có sử dụng class bị thiếu. Khi thay thư viện, hãy kiểm chứng lại cả compile và runtime, không chỉ kiểm tra launcher có tìm được main class hay không.

**Đừng nhầm `sourcepath` và `classpath`:** `javac --source-path src/main/java` hướng compiler tìm **source files**; `javac -cp 'lib/*'` hướng compiler tìm **compiled classes trong JAR**. Wildcard đặc biệt của JAR classpath không phải cú pháp tổng quát cho `--source-path`, `--module-source-path` hoặc tên package.

## 10. java -jar, JAR manifest và giới hạn của wildcard

Lệnh `java -jar app.jar` vận hành theo cơ chế **executable JAR**. Trong chế độ này, user classpath được khai báo qua `-cp` hoặc biến môi trường `CLASSPATH` không trở thành nguồn lớp tìm kiếm bổ sung như khi dùng `java -cp ... MainClass`. Cách phụ thuộc được cung cấp phụ thuộc việc đóng gói JAR và manifest.

Đoạn sau **không phải một lệnh đáng tin để bổ sung `lib/*`** cho executable JAR:

~~~bash
java -cp 'lib/*' -jar app.jar
~~~

Nếu `app.jar` cần các JAR bên ngoài, có thể dùng cơ chế manifest `Class-Path` được hỗ trợ, hoặc gọi main class qua `-cp` với đủ app JAR và dependency JAR:

~~~bash
# Chỉ là cấu trúc mẫu: app.jar phải thực sự có demo.app.Main.
java -cp 'app.jar:lib/*' demo.app.Main
~~~

Trên Windows thay `:` bằng `;`.

**Wildcard classpath không được mở rộng trong trường `Class-Path` của manifest.** Viết:

~~~text
Class-Path: lib/*
~~~

không tương đương lệnh `java -cp 'lib/*'`. Trong manifest, cần nêu những JAR đúng cú pháp tương đối, ví dụ:

~~~text
Class-Path: lib/alpha.jar lib/beta.jar
~~~

Đây là đoạn thuộc **main section** của manifest, không phải một manifest hoàn chỉnh. Đường dẫn manifest được hiểu theo vị trí JAR và quy tắc URL của JAR spec, không đơn giản luôn dựa vào thư mục làm việc của shell. Đừng tự thêm đoạn này vào manifest nếu cách phân phối JAR đã được plugin đóng gói quản lý.

Cũng không được nhầm classpath wildcard với option `-jar` của lệnh `jar`: `jar --create --file ...` là công cụ tạo archive, không phải cơ chế resolve dependency khi runtime.

## 11. Module path (JPMS) không dùng chung cú pháp wildcard của classpath

Từ Java 9, các **named modules** có thể được tìm qua `--module-path` (`-p`), trong khi mã theo classpath nằm trong **unnamed module**.

- `--class-path 'lib/*'`: cơ chế mở rộng các JAR classpath trực tiếp.
- `--module-path lib`: khai báo **thư mục chứa các module** để module system tìm và resolve theo module name (khi cấu trúc phù hợp).
- `--module-source-path`: chỉ nơi chứa source theo module layout, hoàn toàn khác việc mở rộng JAR dependency.

Không tự chuyển `--module-path lib` thành `--module-path 'lib/*'` với giả định dấu sao hoạt động như trong classpath. Module path có quy tắc thư mục module/JAR riêng và resolution theo `module-info.java`, `requires`, `exports`; cần dùng đường dẫn module hợp lệ. Một JAR có thể là automatic module khi đặt trên module path tùy nội dung và quy tắc đặt tên, nhưng không vì thế mà wildcard classpath trở thành công cụ module resolution.

Đối với plugin hoặc thư viện yêu cầu JPMS, hãy xác minh mô hình module graph và xem dependency là named/automatic/unnamed module trước khi chọn `-p` hay `-cp`.

## 12. Gradle/Maven có cách chọn dependency riêng

Trong Gradle (Groovy DSL), có thể thêm thư viện local bằng một tập file:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation fileTree(dir: 'lib', include: ['*.jar'])
}
~~~

Đoạn này nằm trong một `build.gradle` có plugin Java và là ví dụ về **file collection do Gradle chọn**. Mẫu `*.jar` ở đây là **pattern của Gradle**, không phải wildcard classpath mà Java launcher mở rộng. Điều đó giải thích vì sao `lib/*.jar` trong cấu hình Gradle có thể hợp lệ, còn `java -cp 'lib/*.jar'` không phải cú pháp wildcard JAR của Java.

Khi đã biết artifact cụ thể, khai báo module dependency theo tọa độ và phiên bản sẽ dễ quản lý hơn:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.example:artifact-name:1.2.3'
}
~~~

`org.example:artifact-name:1.2.3` chỉ là **tọa độ minh họa**, không khẳng định artifact này tồn tại hay tải được. Trong dự án thật dùng đúng tọa độ của dependency đã chọn. Gradle sẽ xây compile/runtime classpaths theo mô hình configurations và dependency resolution, không nhất thiết chuyển cấu hình đó thành một chuỗi `lib/*` ở user-facing script.

Trong Maven, dependency quản lý bằng khai báo `<dependency>` với `groupId`, `artifactId`, `version` và scope thích hợp trong `pom.xml`; không thay thế việc chọn phiên bản bằng một thư mục JAR wildcard. Nếu bắt buộc dùng local JAR, cần quản lý nguồn gốc và cách phân phối rõ ràng.

**Vấn đề của việc gom tất cả JAR:** một thư mục `lib` có thể chứa công cụ test, annotation processor, bản JAR cũ hoặc dependency chỉ dùng lúc compile. Đưa hết chúng vào runtime classpath bằng `lib/*` có thể làm phình classpath và khó nhìn ra phạm vi phụ thuộc. Build tool giúp phân biệt `implementation`, `runtimeOnly`, `testImplementation` theo lifecycle.

## 13. Diagnosing: xác minh wildcard thực sự đã được mở rộng

Có thể kiểm tra classpath runtime bằng một chương trình Java độc lập nhỏ `ShowClasspath.java`:

~~~java
public class ShowClasspath {
    public static void main(String[] args) {
        System.out.println(System.getProperty("java.class.path"));
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 ShowClasspath.java
~~~

Nếu file đang nằm ở thư mục làm việc và thư mục `lib` có một số JAR, chạy trên Unix:

~~~bash
java -cp '.:lib/*' ShowClasspath
~~~

Trên Windows:

~~~powershell
java -cp '.;lib/*' ShowClasspath
~~~

Đầu ra là chuỗi classpath mà Java runtime báo cáo; **giá trị cụ thể thay đổi** theo JAR hiện có, OS, separator và thứ tự mở rộng. Không nên cam kết một stdout cố định cho bài kiểm tra này. Khi có JAR hợp lệ, bạn thường sẽ nhìn thấy các file `lib/name.jar` được liệt kê thay cho entry wildcard.

Có thể kiểm tra JAR trực tiếp bằng `jar --list --file lib/message.jar`; kiểm tra class resolution bằng compiler/runtime error hoặc công cụ quan sát class loading phù hợp, ví dụ `java -Xlog:class+load=info` trên HotSpot JDK 17+ (sẽ tạo rất nhiều log, định dạng không ổn định). Những cách này trả lời các câu hỏi khác nhau:

1. **Classpath string có đúng entry mong muốn không?**
2. **Mỗi archive có chứa class/package mình cần không?**
3. **Runtime thật sự nạp class từ archive nào?**
4. **Có nhiều phiên bản định nghĩa cùng class không?**

Cách kiểm tra quan trọng là bắt đầu từ **output sạch**, chỉ giữ JAR mà ứng dụng cần, chạy lại lệnh `javac` và `java` có classpath tường minh. Đừng dùng việc chương trình “tình cờ chạy được” trên một máy với thư mục `lib` lâu năm làm bằng chứng dependency đã được cấu hình đúng.

## 14. Tóm tắt các giới hạn và hướng xử lý

| Mong muốn | `lib/*` có đáp ứng? | Cấu hình đúng |
| --- | --- | --- |
| Tất cả JAR ngay trong `lib` | Có | `-cp 'lib/*'` |
| Chỉ các JAR khớp `a*.jar` | Không phải wildcard classpath | Liệt kê file hoặc dùng công cụ build chọn pattern |
| Lấy JAR trong mọi thư mục con | Không | Thêm mỗi root `dir/*` hoặc dùng build tool |
| Lấy các `.class` rời trong `lib/classes` | Không | Thêm `lib/classes` như classpath entry |
| Lấy `.zip` trong thư mục qua wildcard | Không | Liệt kê `.zip` cụ thể nếu phù hợp |
| Chọn thứ tự giữa nhiều JAR trùng class | Không | Liệt kê JAR theo thứ tự và loại duplicate |
| Tự resolve/transitively download dependencies | Không | Dùng Gradle/Maven và lock/version policy phù hợp |
| Áp dụng `*` cho manifest `Class-Path` | Không | Ghi từng JAR đúng manifest syntax |
| Áp dụng cùng `*` cho module path | Không | Dùng module path hợp lệ, khai báo module graph |
| Thêm thư viện cho `java -jar` qua `-cp` | Không như lệnh `java -cp Main` | Dùng manifest, packaging hoặc gọi main bằng `-cp` |
| Tự chọn mọi file `.java` để compile | Không | Chọn source files/source set bằng `javac` hoặc build tool |

### Checklist trước khi chấp nhận một lệnh có wildcard

- **Directory:** các JAR cần thiết có nằm trực tiếp trong thư mục được chỉ định không?
- **Extension:** file có đuôi `.jar`/`.JAR` như quy tắc của Java hay là `.zip`, `.class`, thư mục con?
- **Shell:** classpath đã được quote để không bị Bash/PowerShell xử lý sai chưa?
- **Separator:** danh sách classpath dùng `:` cho Unix hoặc `;` cho Windows chưa?
- **Main classes:** output chứa main class đã được thêm ngoài wildcard chưa?
- **Compile vs runtime:** dependency có trong cả pha cần thiết hay chỉ một pha?
- **Duplicate:** thư mục có nhiều phiên bản cùng một class/resource không?
- **Packaging:** đang chạy qua `java -cp`, `java -jar` hay `--module-path`? Chúng có quy tắc khác nhau.
- **Reproducibility:** phiên bản và nội dung thư mục JAR có được kiểm soát ở CI/deployment không?

### Bài thực hành

Từ ví dụ mục 5, chạy lần lượt:

1. Giữ `message.jar` trong `lib`, biên dịch và chạy `java -cp 'build/app:lib/*' demo.app.Main`, xác nhận `JAR_OK`.
2. Chuyển `message.jar` vào `lib/nested` trên một bản sao thử nghiệm; thấy `lib/*` không còn nhận ra thư viện. Thêm `lib/nested/*` vào classpath để khắc phục.
3. Thử bỏ `build/app` khỏi runtime classpath và quan sát main class không được tìm thấy.
4. Đặt một file `.zip` hoặc `.class` vào `lib`; xác minh wildcard không đưa file đó thành một dependency JAR mới.
5. Tạo `ShowClasspath.java` ở mục 13 để quan sát đường dẫn thực sự đã mở rộng. Không so sánh chuỗi theo thứ tự JAR cố định.

**Thông điệp cốt lõi:** Java classpath wildcard là tiện ích viết tắt **danh sách JAR trực tiếp trong một thư mục**. Nó không thay thế source selection, recursive file matching, module resolution hay dependency management. Hiểu rõ ranh giới này giúp tránh lỗi thiếu class, chọn nhầm phiên bản và các build chỉ hoạt động tình cờ trên một môi trường.

## Tài liệu tham khảo

- [Oracle Java SE 17 — java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cú pháp `--class-path` và quy tắc mở rộng JAR wildcard.
- [OpenJDK — wildcard.c](https://github.com/openjdk/jdk/blob/master/src/java.base/share/native/libjli/wildcard.c): chú giải về phạm vi `*`, không recursive, không gồm `.class`/`.zip`, thứ tự JAR và giới hạn với manifest/module path.
