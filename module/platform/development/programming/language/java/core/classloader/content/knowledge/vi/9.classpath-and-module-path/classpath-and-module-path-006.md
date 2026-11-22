# JAR, manifest Main-Class và Class-Path trong cơ chế tìm lớp Java

Một tệp **JAR (Java ARchive)** đóng gói các tệp `.class`, tài nguyên và metadata vào một archive dạng ZIP. Với một **executable JAR** thông thường, JVM launcher sử dụng tệp `META-INF/MANIFEST.MF` trong JAR để xác định **lớp khởi động** qua thuộc tính `Main-Class`. Thuộc tính `Class-Path` trong cùng manifest có thể chỉ ra **những JAR/thư mục phụ thuộc** để class loader mở rộng đường tìm kiếm.

Ví dụ:

```text
app/
├── app.jar
└── lib/
    ├── helper.jar
    └── parser.jar
```

Manifest bên trong `app.jar`:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/helper.jar lib/parser.jar

```

Sau khi đóng gói đúng, lệnh `java -jar app.jar` tìm `demo.Main`, gọi `public static void main(String[] args)`, và có thể tìm lớp phụ thuộc trong `lib/helper.jar`, `lib/parser.jar`. Các mục `Class-Path` được hiểu **tương đối với vị trí của JAR chứa manifest**, không đơn thuần tương đối với working directory của terminal.

Đây là ba thành phần riêng biệt:

- **JAR**: lưu bytecode và tài nguyên theo tên entry như `demo/Main.class`.
- **`Main-Class`**: chỉ định lớp có điểm vào của ứng dụng được `java -jar` sử dụng.
- **`Class-Path`**: bổ sung các đường dẫn tìm class/resource khi loader xử lý JAR chứa manifest.

## 1. JAR chứa những gì?

JAR thường được tạo bằng công cụ `jar` của JDK. Nó là một ZIP archive với quy ước metadata dành cho Java.

Ví dụ cấu trúc bên trong:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
├── demo/
│   ├── Main.class
│   └── Config.class
└── application.properties
```

Tệp `demo/Main.class` là **JAR entry** tương ứng với binary name `demo.Main`. Tài nguyên `application.properties` nằm tại gốc JAR có thể được tìm bằng các API resource khi JAR nằm trong phạm vi lookup phù hợp.

Không được dùng `Main-Class: demo/Main.class` hoặc `Main-Class: demo.Main.class`. `Main-Class` nhận **tên lớp**, ví dụ `demo.Main`, chứ không nhận đường dẫn tài nguyên `.class`.

Đối với classloader, đường đi có thể hiểu là:

```text
java -jar app.jar
        |
        v
Đọc META-INF/MANIFEST.MF
        |
        +--> Main-Class: demo.Main
        |          |
        |          v
        |     tìm demo/Main.class trong app.jar
        |
        +--> Class-Path: lib/helper.jar
                   |
                   v
              thêm nguồn tìm lớp/tài nguyên
                   |
                   v
            gọi demo.Main.main(String[])
```

Đây là mô hình giúp học. Trên Java 9+, runtime có thêm module, bootstrap/platform loaders và các chi tiết JVM/JDK; sơ đồ không có nghĩa toàn bộ lớp nền tảng chỉ được tìm trong các JAR bên ngoài.

## 2. Manifest là gì?

Manifest tiêu chuẩn nằm đúng đường dẫn **`META-INF/MANIFEST.MF`** trong JAR. Nó là một tệp văn bản có cú pháp riêng, gồm **main section** và tùy chọn các section cho từng entry.

Một manifest tối thiểu dùng cho `java -jar`:

```text
Manifest-Version: 1.0
Main-Class: demo.Main

```

- `Manifest-Version` chỉ phiên bản định dạng manifest; nên đặt ở đầu tệp.
- `Main-Class` là tên nhị phân của lớp khởi chạy, **không kèm `.class`**. Class phải nằm trong phạm vi tìm thấy và có điểm vào `main` hợp lệ.
- Dòng trống sau các thuộc tính dùng để kết thúc **main section**. Khi tự tạo manifest, bảo đảm có ký tự xuống dòng kết thúc dòng cuối; dùng công cụ `jar` để hợp nhất và chuẩn hóa manifest nếu có thể.

Ví dụ có thêm dependency:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/helper.jar lib/parser.jar

```

Tên thuộc tính manifest có cú pháp `Name: value`, **có dấu hai chấm và khoảng trắng phân cách**. Tên thuộc tính không phân biệt chữ hoa/chữ thường theo specification, nhưng nên viết theo dạng chuẩn `Main-Class` và `Class-Path` để dễ đọc.

Đối với manifest dài, giới hạn một dòng vật lý là **72 byte khi mã hóa UTF-8**, không phải 72 ký tự. Nội dung dài phải được **gập dòng** và dòng tiếp theo bắt đầu bằng một dấu cách; dấu cách đó là ký hiệu nối dòng, không phải ký tự tùy ý thêm vào đường dẫn. Hãy để `jar` hoặc công cụ manifest chuẩn xử lý việc gập dòng. Không tự chèn newline giữa một đường dẫn rồi kỳ vọng JVM ghép lại theo ý người viết.

**Phân biệt quan trọng:** metadata trong manifest không đồng nghĩa loader tự chạy toàn bộ class. `Main-Class` chọn điểm vào cho launcher; những class khác thường chỉ được tải khi chương trình/JVM thực sự cần chúng.

## 3. Main-Class: xác định entry point

Với source Java:

```java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JAR");
    }
}
```

Sau khi biên dịch, class file phải có entry:

```text
demo/Main.class
```

Nếu `Main-Class: demo.Main`, launcher có thể tìm main class và gọi phương thức:

```java
public static void main(String[] args)
```

Đối với Java 17 trong bài, đây là chữ ký entry point cần dùng. `main` phải `public`, `static`, trả `void` và nhận mảng `String[]`. Một constructor của `Main` không bắt buộc được gọi.

Hai lệnh có semantics khác nhau:

```bash
java -cp out demo.Main
java -jar app.jar
```

- Với `-cp`/`--class-path`, người chạy **ghi rõ main class trên dòng lệnh** và xác định classpath.
- Với `-jar`, launcher **lấy main class từ manifest của JAR**; tên JAR là đối số cho launcher.
- Các tham số **sau** tên JAR là tham số chương trình truyền vào `main(String[] args)`.

Ví dụ:

```bash
java -jar app.jar input.txt --verbose
```

Trong `main`, `args[0]` là `input.txt`, `args[1]` là `--verbose`. Không được hiểu các từ phía sau tên JAR là tùy chọn `-cp` của JVM.

### Khi thiếu Main-Class

Một thư viện `utils.jar` vẫn hoàn toàn hữu dụng dù không có `Main-Class`: ứng dụng khác có thể đưa nó vào classpath để sử dụng lớp bên trong.

Nhưng nếu chạy `java -jar utils.jar` mà manifest không khai báo entry point, launcher có thể báo:

```text
no main manifest attribute, in utils.jar
```

Đó là lỗi **đóng gói/khởi chạy**, không chứng minh JAR bị hỏng hoặc mọi lớp trong nó không nạp được.

## 4. Class-Path trong manifest được hiểu như thế nào?

Theo *JAR File Specification*, giá trị `Class-Path` là danh sách **URL tương đối** đến JAR hoặc thư mục phụ thuộc, cách nhau bằng một hay nhiều khoảng trắng.

Ví dụ:

```text
Class-Path: lib/helper.jar lib/parser.jar config/
```

Trong bản phân phối:

```text
dist/
├── app.jar
├── config/
│   └── config.properties
└── lib/
    ├── helper.jar
    └── parser.jar
```

Các mục tương ứng với vị trí JAR chứa manifest:

| Manifest entry | Nguồn tìm tương ứng khi JAR ở `dist/app.jar` |
|---|---|
| `lib/helper.jar` | `dist/lib/helper.jar` |
| `lib/parser.jar` | `dist/lib/parser.jar` |
| `config/` | `dist/config/`, một thư mục tài nguyên/class |

Các đường dẫn này **không phụ thuộc vào nơi bạn đứng khi gõ `java -jar`**. Nếu chạy `java -jar /opt/app/dist/app.jar` trong thư mục làm việc `/tmp`, `lib/helper.jar` vẫn được hiểu dựa trên `/opt/app/dist/app.jar`.

Một số quy tắc quan trọng của specification:

1. `Class-Path` khai báo ở **main section** và chỉ nên có **một header** `Class-Path` trong một manifest; nhiều entry liệt kê trên cùng thuộc tính.
2. Mỗi entry là một **relative URL** hợp lệ, có thể là JAR hoặc thư mục. Dấu `/` là dấu phân tách theo URL, không thay bằng `\` của Windows.
3. Entry **kết thúc bằng `/`** được hiểu như thư mục; entry không kết thúc bằng `/` được giả định là JAR.
4. Entry được resolve so với URL của **context JAR**, tức JAR chứa manifest đang được xử lý.
5. URL không hợp lệ, không tìm thấy hoặc trùng lặp có thể bị bỏ qua trong quá trình xây đường tìm kiếm. Vì thế path viết sai có thể dẫn tới lỗi chỉ lúc một class thực sự được sử dụng.
6. Quy tắc URL an toàn ưu tiên dependency nằm dưới thư mục chứa context JAR. Một số ngoại lệ tương thích áp dụng khi JAR được nạp từ file system (bao gồm trường hợp liên quan `../` và `file:`), nhưng không nên phụ thuộc vào chúng nếu muốn gói triển khai đơn giản và dễ di chuyển.

**Không đặt ký tự wildcard** `lib/*` trong manifest với kỳ vọng nó giống wildcard của tùy chọn `java -cp`. Manifest `Class-Path` dùng danh sách URL, **không có cơ chế wildcard expansion giống command-line classpath**. Hãy liệt kê `lib/a.jar lib/b.jar` cụ thể hoặc dùng công cụ đóng gói/deployment khác.

Đường dẫn chứa dấu cách phải được thể hiện bằng URL hợp lệ (ví dụ percent encoding khi phù hợp), không chỉ đặt trong dấu nháy theo cú pháp shell. Cách bền vững hơn là đặt tên file/thư mục phụ thuộc không có khoảng trắng và đóng gói theo cấu trúc cố định.

## 5. Thực hành Java 17+: tạo executable JAR có dependency riêng

Bài tập sau cho thấy rõ `Main-Class` chọn entry point và `Class-Path` mở rộng search path đến một thư viện nằm **ngoài** JAR chính.

Tạo cấu trúc nguồn:

```text
jar-demo/
├── src/
│   ├── demo/
│   │   └── Main.java
│   └── util/
│       └── Message.java
└── app.mf
```

### 5.1. Viết class phụ thuộc

Tệp **`src/util/Message.java`**:

```java
package util;

public final class Message {
    private Message() {
    }

    public static String text() {
        return "Dependency OK";
    }
}
```

### 5.2. Viết main class

Tệp **`src/demo/Main.java`**:

```java
package demo;

import util.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Main class: " + Main.class.getName());
        System.out.println(Message.text());
        System.out.println("Main resource visible: "
                + (Main.class.getClassLoader()
                        .getResource("demo/Main.class") != null));
    }
}
```

Ở đây `demo.Main` có tham chiếu đến `util.Message`. Khi chạy ứng dụng, class loader cần tìm `util/Message.class`. Ta sẽ đưa class đó vào `helper.jar` thay vì nhúng vào `app.jar`.

### 5.3. Tạo manifest

Tệp **`app.mf`**:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/helper.jar

```

Giữ newline sau dòng cuối và dòng trống kết thúc phần main khi tự soạn nội dung. Khi tạo archive, công cụ `jar` sẽ xử lý định dạng manifest.

### 5.4. Biên dịch và đóng gói

Trên **Bash** (Linux/macOS/Git Bash), từ thư mục `jar-demo`:

```bash
mkdir -p classes/helper classes/app dist/lib

javac --release 17 -d classes/helper src/util/Message.java
jar --create --file dist/lib/helper.jar -C classes/helper .

javac --release 17 -cp dist/lib/helper.jar -d classes/app src/demo/Main.java
jar --create --file dist/app.jar --manifest app.mf -C classes/app .

java -jar dist/app.jar
```

Trên **Windows PowerShell**, thay bước tạo thư mục đầu tiên bằng:

```powershell
New-Item -ItemType Directory -Force -Path classes/helper, classes/app, dist/lib | Out-Null
```

Các lệnh `javac`, `jar`, `java` sau đó có cùng cú pháp như trên (miễn JDK đã nằm trên `PATH`).

Đầu ra trên JDK 17+ với ví dụ này:

```text
Main class: demo.Main
Dependency OK
Main resource visible: true
```

Ý nghĩa các lệnh:

- `javac --release 17` biên dịch tương thích API/class-file target Java 17.
- `-d classes/helper` và `-d classes/app` đặt file class đúng cây package tương ứng.
- `jar --create --file dist/lib/helper.jar -C classes/helper .` đóng gói thư viện chứa `util/Message.class`.
- `javac -cp dist/lib/helper.jar ...` giúp **compiler** tìm `util.Message` khi biên dịch `Main`.
- `jar --create --file dist/app.jar --manifest app.mf ...` đóng gói ứng dụng và đưa các thuộc tính manifest vào archive.
- `java -jar dist/app.jar` dùng manifest của `app.jar`, rồi tìm dependency qua `Class-Path: lib/helper.jar`.

**Quan trọng:** `-cp` trong lệnh `javac` là **compile-time classpath**, không tự trở thành runtime classpath. Ở ví dụ này, chương trình runtime tìm dependency được là do **manifest `Class-Path`**, không phải vì compiler trước đó có tham số `-cp`.

Cấu trúc đầu ra:

```text
dist/
├── app.jar
└── lib/
    └── helper.jar
```

Nếu sao chép cả thư mục `dist` sang một máy khác có JRE/JDK phù hợp, quan hệ đường dẫn `lib/helper.jar` vẫn giữ nguyên. Nếu chỉ chép `app.jar` nhưng quên `lib/helper.jar`, đến lúc code dùng `util.Message`, runtime không thể tìm định nghĩa lớp cần thiết.

### 5.5. Kiểm tra nội dung JAR

Dùng công cụ có sẵn của JDK:

```bash
jar --list --file dist/app.jar
jar --list --file dist/lib/helper.jar
```

Các entry quan trọng cần thấy:

```text
# Trong app.jar
META-INF/
META-INF/MANIFEST.MF
demo/Main.class

# Trong helper.jar
META-INF/
META-INF/MANIFEST.MF
util/Message.class
```

Trên `jar --list` thực tế còn có thể có entry/thứ tự khác; khối trên **chỉ liệt kê các entry cần xác minh**, không phải stdout cố định toàn bộ lệnh. Điều cần kiểm tra là tên entry tương ứng chính xác với package/binary name.

Để kiểm tra nội dung manifest bằng công cụ ZIP/JAR viewer, mở `META-INF/MANIFEST.MF` bên trong `app.jar`. Khi dùng công cụ `jar --extract`, hãy giải nén vào **thư mục làm việc riêng** để không trộn file metadata vào source hiện tại.

## 6. Điều gì xảy ra nếu bỏ Class-Path?

Giữ `app.jar` và `helper.jar` như bài tập nhưng tạo manifest chỉ có:

```text
Manifest-Version: 1.0
Main-Class: demo.Main

```

Chạy `java -jar dist/app.jar` ở chế độ classpath thông thường sẽ không còn đường dẫn manifest đến `lib/helper.jar`. Khi code bắt đầu dùng `util.Message`, bạn có thể thấy lỗi dạng:

```text
java.lang.NoClassDefFoundError: util/Message
Caused by: java.lang.ClassNotFoundException: util.Message
```

Đây là **mẫu phần đầu exception/cause**, còn stack trace thực tế phụ thuộc nơi class được sử dụng và runtime. Nó cho biết JVM không giải quyết được class phụ thuộc lúc chạy. `Main-Class` vẫn có thể đúng.

Hãy phân biệt:

| Quan sát | Vấn đề thường gặp |
|---|---|
| `no main manifest attribute` | Thiếu/sai `Main-Class` trong executable JAR |
| `Could not find or load main class ...` | Main class không có ở vị trí đúng, tên sai, hoặc lỗi liên quan khi nạp main class |
| `ClassNotFoundException` | API loader được gọi tường minh không tìm được class theo đường tìm kiếm |
| `NoClassDefFoundError: util/Message` | JVM cần class dependency nhưng không có định nghĩa phù hợp lúc sử dụng |
| `UnsupportedClassVersionError` | Class file biên dịch cho Java mới hơn runtime đang chạy |
| `NoSuchMethodError` | Dependency tìm được nhưng phiên bản binary không còn method được code tham chiếu |
| `SecurityException` về sealing/signature | Ràng buộc package hoặc JAR signing không thỏa mãn |

**Không suy diễn rằng mọi `NoClassDefFoundError` đều do thiếu dependency JAR.** Lớp đã thất bại trong static initialization cũng có thể dẫn đến `NoClassDefFoundError` trong những lần sử dụng sau. Phải đọc thông điệp và cause.

## 7. Vì sao java -jar không dùng -cp theo cách thường gặp?

Đây là một trong những điểm quan trọng nhất về **đường dẫn tìm kiếm**.

Theo tài liệu lệnh `java` của JDK 17, khi chạy chế độ **`-jar`**, JAR được chỉ định là nguồn chính của user classes; **các thiết lập classpath khác bị bỏ qua** đối với chế độ khởi chạy này. Nguồn phụ thuộc bổ sung có thể đến từ **manifest `Class-Path`** và các cơ chế JVM/module phù hợp.

Ví dụ muốn thêm `other.jar` bằng cách viết:

```bash
java -cp other.jar -jar dist/app.jar
```

thì **không thể dựa vào `-cp other.jar`** để mở rộng đường tìm class của chế độ `-jar`. Cách chuẩn của bài tập là ghi `Class-Path: lib/helper.jar` trong manifest hoặc chọn một kiểu khởi chạy khác.

Khi muốn tự điều khiển classpath và main class, bỏ `-jar` và ghi rõ tên lớp:

```bash
# Linux/macOS
java -cp "dist/app.jar:dist/lib/helper.jar" demo.Main
```

```powershell
# Windows PowerShell
java -cp "dist/app.jar;dist/lib/helper.jar" demo.Main
```

**Lưu ý dấu phân cách:** Windows dùng `;`, Linux/macOS dùng `:` cho các phần tử classpath của lệnh `java -cp`. Đây là khác biệt của **command-line classpath**, không thay đổi quy tắc dùng dấu `/` bên trong thuộc tính manifest `Class-Path`.

Với cách chạy `-cp`, tên `demo.Main` trên command line chọn entry point. `Main-Class` trong manifest của `app.jar` không còn là nơi quyết định entry point cho lệnh đó. Tuy nhiên, nếu JAR chứa manifest `Class-Path` và loader đang sử dụng có hỗ trợ manifest class-path, các dependency trong manifest vẫn có thể được xử lý theo cơ chế đó; không nên hiểu chế độ `-cp` là “tắt mọi metadata của JAR”.

## 8. Class-Path và class loader có tương tác ra sao?

Các entry `Class-Path` ảnh hưởng đến **nguồn mà application class loader có thể tìm kiếm** trong mô hình classpath/JAR thông thường. Nó không thay thế quy tắc **parent delegation**:

```text
Application loader cần demo.Main
        |
        +--> parent/bootstrap/platform trước (nếu phù hợp)
        |
        +--> app.jar
        |
        +--> lib/helper.jar (theo manifest Class-Path)
```

Khi code gọi:

```java
Class<?> type = Class.forName("util.Message");
```

lệnh đó dùng defining loader của **calling class** theo hợp đồng overload một tham số. Nếu `demo.Main` được application loader định nghĩa trong mô hình ví dụ, loader đó có thể tìm `util.Message` qua entry `lib/helper.jar`. Nhưng việc manifest có đường dẫn đến JAR **không tự động nạp tất cả lớp** ngay khi JVM bắt đầu.

Ba khái niệm cần tách:

- **Class path:** nguồn JAR/thư mục để tìm class/resource.
- **Class loader:** đối tượng/cơ chế thực hiện lookup, delegation và định nghĩa lớp.
- **Runtime class identity:** `(binary name, defining class loader)`. Hai loader khác nhau có thể định nghĩa hai class cùng tên nhưng không cùng runtime type.

Đây là lý do đặt hai bản `shared.api.Service` trong các JAR của loader khác nhau có thể gây lỗi ép kiểu, dù mỗi JAR đều khai báo `Class-Path` hợp lệ. Manifest `Class-Path` xác định đường tìm kiếm; nó **không hòa nhất namespace của hai defining loaders**.

## 9. Những tình huống dễ nhầm

### 9.1. Đường dẫn tương đối tính theo JAR, không theo terminal

Giả sử:

```text
/opt/demo/app.jar
/opt/demo/lib/helper.jar
```

Chạy:

```bash
cd /tmp
java -jar /opt/demo/app.jar
```

Khi manifest có `Class-Path: lib/helper.jar`, dependency vẫn được tìm tương đối với `/opt/demo/app.jar`. Nếu di chuyển riêng `app.jar` sang `/tmp/app.jar` nhưng không mang theo `lib`, quan hệ đường dẫn không còn đúng.

### 9.2. Wildcard không giống trong manifest

Dòng:

```text
Class-Path: lib/*
```

không tương đương với tùy chọn `java -cp "lib/*"`. Khi dùng manifest, hãy liệt kê từng entry URL cần thiết, ví dụ `lib/a.jar lib/b.jar`. Với CLI, wildcard classpath có quy tắc mở rộng JAR riêng của launcher.

### 9.3. Tên JAR đúng nhưng package entry sai

Giả sử code yêu cầu `org.example.Tool` nhưng archive chỉ chứa `Tool.class` tại gốc. Đây không phải tên entry tương ứng; classloader kỳ vọng đường resource dạng `org/example/Tool.class` trong JAR thông thường. Cần biên dịch và đóng gói từ **gốc của cây package**, ví dụ `jar -C classes .`, thay vì đóng gói nhầm thư mục `classes` như một entry bên trong.

### 9.4. Quên dependency lúc chạy

Lệnh `javac -cp lib/helper.jar` chỉ giúp **biên dịch**. Nếu JAR ứng dụng không chứa dependency đó, không có manifest `Class-Path` hợp lệ và launcher không được cấu hình classpath phù hợp, runtime có thể ném lỗi khi class `util.Message` được giải quyết.

### 9.5. Main-Class ghi đường dẫn thay vì binary name

Sai:

```text
Main-Class: demo/Main.class
```

Đúng:

```text
Main-Class: demo.Main
```

Cũng không nên dùng tên canonical `Outer.Inner` khi entry point là nested class có binary name `Outer$Inner`; với lớp lồng nhau, manifest cần binary name mà launcher có thể giải quyết. Thực tế nên dùng top-level main class cho ứng dụng để đơn giản.

### 9.6. JAR chứa nhiều main classes

Một archive có thể chứa `demo.Main`, `demo.AdminMain` và `demo.BatchMain`, nhưng manifest `Main-Class` chọn **một** entry point mặc định cho `java -jar`. Khi muốn khởi chạy một entry point khác, có thể dùng `java -cp app.jar demo.BatchMain` (kèm dependencies phù hợp) hoặc tạo executable JAR/launcher riêng.

### 9.7. Xung đột dependency và thứ tự tìm kiếm

Nếu nhiều JAR chứa class cùng binary name, class loader thường chọn theo chính sách tìm kiếm của nó (classpath ordering, parent delegation, module mapping, custom loader). Đừng trông chờ `Class-Path` giải quyết version conflict. Nó chỉ mô tả URL thư viện phụ thuộc; bản class thực sự được dùng phải kiểm tra theo loader/classpath hiện hành.

### 9.8. Executable JAR khác fat JAR/nested JAR

Executable JAR chuẩn trong bài chứa trực tiếp `demo/Main.class`; dependency đặt bên ngoài dưới `lib/helper.jar` và được tham chiếu bởi manifest.

Một **fat/uber JAR** có thể gộp nội dung nhiều thư viện vào một JAR phẳng. Một **Spring Boot executable JAR** phổ biến lại bố trí classes và nested JAR ở cấu trúc như `BOOT-INF/classes` và `BOOT-INF/lib`, sử dụng launcher/classloader chuyên dụng. Đừng cho rằng JVM launcher mặc định sẽ tự quét mọi nested JAR bên trong một JAR ZIP thông thường.

`Main-Class` của dạng đóng gói framework có thể là **launcher** của framework, còn entry point nghiệp vụ được mô tả bằng metadata riêng. Những thuộc tính đó là cơ chế của công cụ đóng gói, không phải quy tắc chung của mọi JAR Java.

### 9.9. Manifest và JPMS

Trong ứng dụng **module path** dùng named modules, cơ chế module resolution, module descriptor `module-info.class` và quy tắc module access khác với classpath truyền thống. `Main-Class` của executable JAR và `Class-Path` trong manifest không thể thay thế `requires`, `exports` hay `opens` của JPMS. Nếu chạy module bằng `java --module-path ... -m module[/mainclass]`, phải phân tích startup và module-path theo hợp đồng chế độ đó.

## 10. Tạo JAR với jar --main-class thay vì file manifest thủ công

Trong trường hợp không cần thuộc tính `Class-Path` hoặc metadata đặc biệt, công cụ `jar` hỗ trợ ghi main class ngay khi đóng gói:

```bash
jar --create --file app.jar --main-class demo.Main -C classes/app .
```

Nó tạo manifest phù hợp để launcher biết entry point. Tuy nhiên, nếu ứng dụng cần `Class-Path: lib/helper.jar` như bài thực hành, phải **đảm bảo thuộc tính này có mặt** (ví dụ cung cấp `--manifest app.mf`).

Một số tùy chọn viết tắt truyền thống của `jar`:

```bash
jar cfm dist/app.jar app.mf -C classes/app .
```

Lệnh trên tương đương về mục đích với `jar --create --file dist/app.jar --manifest app.mf -C classes/app .` trong bài; các ký tự `c`, `f`, `m` lần lượt đại diện cho create, file và manifest. Với người mới học, cú pháp dài làm vai trò từng tham số rõ hơn.

**Đừng khai báo trùng thuộc tính `Main-Class` trong nhiều nguồn manifest** rồi mặc định rằng mọi công cụ đều merge theo thứ tự bạn muốn. Chọn một cơ chế cấu hình đóng gói rõ ràng và kiểm tra manifest cuối cùng.

## 11. Kiểm tra nhanh và xử lý lỗi triển khai

Khi `java -jar dist/app.jar` thất bại, có thể làm theo chuỗi sau:

1. **Xác định JAR nào đang chạy.** Đường dẫn file và working directory có đúng không? Lệnh có dùng `-jar` không?
2. **Kiểm tra `META-INF/MANIFEST.MF`.** `Main-Class` có chính xác binary name? `Class-Path` có các entry cần thiết?
3. **Kiểm tra entry class trong JAR.** `jar --list --file dist/app.jar` có `demo/Main.class` ở đúng gốc package?
4. **Kiểm tra dependency files.** `dist/lib/helper.jar` có tồn tại? `jar --list --file dist/lib/helper.jar` có `util/Message.class`?
5. **Kiểm tra cách resolve đường dẫn.** `Class-Path: lib/helper.jar` gắn với vị trí `app.jar`, không phải bất kỳ thư mục bạn `cd` tới.
6. **Đừng cố “sửa” `-jar` bằng `-cp`.** Nếu muốn lựa chọn classpath tường minh, chạy dạng `java -cp ... demo.Main`.
7. **Đọc throwable/cause thực sự.** Thiếu class, class version sai và mismatch binary có thể có giải pháp khác nhau.
8. **Kiểm tra classloader/module khi có framework hoặc plugin.** Có thể cùng binary name nhưng lớp đang được nạp bởi loader không mong muốn.

Để quan sát nơi code đang được nạp, trong một phương thức có thể dùng:

```java
System.out.println(Main.class.getClassLoader());
System.out.println(Main.class.getProtectionDomain()
        .getCodeSource().getLocation());
```

Đây là **đoạn minh họa** với `Main` tồn tại và điều kiện code source phù hợp, không phải chương trình độc lập. `getCodeSource()` hoặc thông tin nguồn có thể vắng trong một số môi trường, nên production code cần kiểm tra `null`. Kết quả loader/URL phụ thuộc runtime và không có stdout cố định.

## 12. Câu hỏi tự kiểm tra

**1. JAR có bắt buộc chứa `Main-Class` không?** Không. JAR thư viện thường không có entry point. `Main-Class` quan trọng khi muốn khởi chạy JAR bằng `java -jar`.

**2. `Main-Class` chứa `demo/Main.class` hay `demo.Main`?** Chứa binary name `demo.Main`, không thêm hậu tố `.class`.

**3. `Class-Path: lib/x.jar` được giải quyết so với thư mục nào?** So với URL/vị trí của JAR chứa manifest, tức **context JAR**.

**4. `Class-Path` cho phép `lib/*` giống `java -cp "lib/*"` không?** Không; manifest dùng các relative URL entries, không dùng wildcard classpath kiểu CLI.

**5. `javac -cp helper.jar` có tự làm `java -jar app.jar` tìm helper.jar không?** Không. Compile-time và runtime lookup là hai cấu hình khác nhau.

**6. Nếu `java -jar` báo `no main manifest attribute` thì có nghĩa bytecode trong JAR không dùng được?** Không. Có thể đó chỉ là library JAR hoặc bước đóng gói thiếu entry point.

**7. Vì sao chạy `java -jar app.jar` trên một working directory khác vẫn tìm được `lib/helper.jar`?** Vì manifest relative URL dựa trên context JAR, không dựa trên current working directory.

**8. `Class-Path` có đảm bảo class được nạp bởi đúng loader không?** Không. Classpath cung cấp nguồn tìm kiếm; định nghĩa/ủy quyền do class loader và môi trường runtime quyết định.

**9. Một JAR thông thường có tự hiểu thư viện được nhúng dưới `lib/x.jar` bên trong chính ZIP không?** Không. Cần đóng gói class phẳng, external dependency qua manifest, hoặc launcher/classloader chuyên dụng nếu dùng nested JAR.

**10. Dùng `java -cp ... demo.Main` có đọc `Main-Class` để chọn main không?** Không. Entry point được xác định bởi tên `demo.Main` trên command line.

## 13. Tài liệu chuẩn

- *JAR File Specification*, phần **JAR Manifest**, **Main Attributes**, **Class-Path Attribute** và quy tắc resolve URL (Java 17): https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- Java SE 17, *The java Command*: các chế độ `-jar`, `-cp`/`--class-path` và entry point: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17, *The jar Command*: các tùy chọn `--create`, `--file`, `--manifest`, `--main-class`, `--list`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Java SE 17 API, `java.lang.ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html

**Ghi nhớ:** `Main-Class` giải thích **chạy từ đâu**, còn `Class-Path` chỉ **tìm các class/resource phụ thuộc ở đâu** trong mô hình classpath. Với `java -jar`, hãy đóng gói đúng entry `demo/Main.class`, khai báo `Main-Class: demo.Main`, liệt kê dependency bằng các URL tương đối như `lib/helper.jar` và phân phối đầy đủ cấu trúc thư mục bên cạnh JAR chính.
