# CDS, AppCDS và giới hạn theo ClassLoader hoặc cấu hình chạy

> **Java Core → ClassLoader → Hiệu năng.** Class Data Sharing (**CDS**) và Application Class Data Sharing (**AppCDS**) là kỹ thuật của HotSpot/OpenJDK nhằm lưu các dạng biểu diễn lớp đã xử lý vào **archive**, để lần khởi động JVM sau có thể nạp chúng nhanh hơn và chia sẻ một phần bộ nhớ metadata giữa các JVM tương thích. Điểm quan trọng trong hệ plugin là: **CDS không đồng nghĩa chỉ bootstrap loader được lợi**, nhưng khả năng archive và tái sử dụng lớp do custom loader nạp còn phụ thuộc **JDK, đường đi nạp class, archive, classpath/module path, JAR và tùy chọn khởi chạy**. Không có cam kết tất cả class của mọi loader đều được archive. Ví dụ Java 17+ ở phần thực hành tạo AppCDS động và kiểm tra bằng JVM logs, kể cả class từ một `URLClassLoader` riêng.

## 1. CDS giải quyết chi phí nào?

Khi khởi động một ứng dụng Java, JVM cần làm nhiều việc:

1. Tìm class theo loader/delegation.
2. Đọc tệp `.class` từ runtime image, directory, JAR hoặc nguồn khác.
3. Phân tích class-file format, kiểm tra cấu trúc và thực hiện những giai đoạn linking/verification theo thời điểm JVM yêu cầu.
4. Tạo và quản lý metadata của lớp.
5. Chạy initialization khi Java semantics yêu cầu, tạo instances và phục vụ logic ứng dụng.

CDS đưa một số kết quả chuẩn bị về class metadata vào archive có thể được JVM **memory-map** trong các lần khởi động sau. Mục tiêu là giảm chi phí đọc/phân tích/thiết lập metadata và có cơ hội chia sẻ các trang dữ liệu phù hợp giữa nhiều JVM processes.

```text
Không dùng application CDS:
   JVM start -> tìm JAR/class -> parse class bytes -> metadata -> run

Dùng AppCDS hợp lệ:
   Trial/training run -> tạo archive *.jsa
   JVM start tiếp theo -> map compatible archive
                        -> dùng archived representation khi eligible
                        -> fallback load bình thường với lớp khác
                        -> run
```

CDS có thể cải thiện **startup time**, và có thể giảm **footprint tổng** khi nhiều JVM cùng dùng các trang archive chia sẻ. Đây **không** phải cách thay thế heap của mọi process, không cache sẵn mọi Java object, không bảo đảm throughput của business logic hoặc peak heap giảm một lượng cụ thể. Chi phí tạo archive và lợi ích phụ thuộc workload, filesystem, OS page cache, JVM build và tập lớp được nạp.

### “Shared class data” không làm mất type identity

Một class runtime vẫn được định danh theo JVM bởi **(binary name, defining loader)**. CDS không cho phép hai custom loaders độc lập trở thành cùng một defining loader, cũng không làm hai `Class<?>` vốn không cùng loader trở thành một object vì chúng từng xuất hiện trong cùng `.jsa`. JVM quản lý các lớp và kiểm tra điều kiện load/archive theo semantics tương thích với Java.

Vì vậy:

- AppCDS là **tối ưu nạp lớp**, không phải mechanism thay đổi thứ tự parent delegation.
- Không thay thế dependency isolation/namespace separation trong hệ plugin.
- Không là cơ chế bảo mật/sandbox cho bytecode không đáng tin.
- Không biến class đã load từ plugin-v1 thành plugin-v2 chỉ vì thay JAR trong lúc JVM còn chạy.

## 2. Phân biệt CDS, AppCDS, archive mặc định và dynamic archive

| Thuật ngữ | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| **CDS** | Class Data Sharing của JVM, ban đầu phục vụ các lớp runtime nền tảng. | Nhiều JDK phân phối sẵn **default CDS archive**. |
| **AppCDS** | Mở rộng tập lớp eligible để chứa lớp ứng dụng và thư viện. | Có thể tăng lợi ích startup ngoài các core classes. |
| **Default/base archive** | Archive từ JDK distribution hoặc được tạo phù hợp, thường `classes.jsa`. | Thường được JVM dùng mặc định khi có thể. |
| **Static/custom archive** | Archive được build bằng classlist và `-Xshare:dump` hoặc công cụ phù hợp. | Nhiều bước, hợp với pipeline build/train có kiểm soát. |
| **Dynamic/top archive** | Archive bổ sung được tạo trong một trial run, ví dụ `-XX:ArchiveClassesAtExit=app.jsa`. | Có thể nằm **trên** default/base archive, dễ thực hành AppCDS. |
| **AOT cache mới hơn** | Cơ chế tiến hóa từ CDS, mở rộng cache tới class loading/linking và nhiều tối ưu. | JDK 24+ có JEP 483; **không đánh đồng** lệnh AOT với lệnh CDS cổ điển. |

Theo Oracle Java SE 25 java launcher docs, JVM có thể dùng **một base archive và một dynamic archive**. Trong file log, dynamic archive thường được gọi là **top** archive. Nếu chỉ truyền tên `app.jsa` của dynamic archive, header archive chứa liên hệ tới base archive thích hợp; JVM có thể tìm default base.

### CDS mặc định

Trong nhiều bản phân phối OpenJDK/Oracle JDK hiện đại, CDS mặc định đã được bật nếu có archive hợp lệ. Một vị trí thường gặp:

```text
JAVA_HOME/lib/server/classes.jsa      (Linux/macOS, tùy distribution)
JAVA_HOME/bin/server/classes.jsa      (Windows, tùy distribution)
```

Đây là **đường dẫn minh họa**, phải kiểm tra JDK bạn thật sự chạy. Từ JDK 12, Oracle JDK thường phân phối sẵn default archive. Không nên luôn giả định một build JDK tùy chỉnh có default archive hoặc một đường dẫn cố định.

`java -Xshare:auto`: sử dụng CDS khi có thể; đây là hành vi mặc định trong nhiều cấu hình.

`java -Xshare:off`: tắt CDS để thử nghiệm đối chứng.

`java -Xshare:on`: yêu cầu CDS; **nếu không thể dùng archive có thể khiến JVM báo lỗi và thoát**. Theo Oracle launcher, đây là chế độ chẩn đoán, **không phải tùy chọn nên ép trong production**.

`-Xshare` thuộc HotSpot/OpenJDK; các JVM khác có thể có tên option, scope và hỗ trợ khác.

## 3. Vì sao AppCDS không “cache mọi class”?

Tập lớp có thể dùng archive thường là **những lớp được quan sát và đủ điều kiện** trong quá trình tạo archive, với các ràng buộc format/loader/configuration.

Ví dụ:

```text
Ứng dụng có 20.000 class files trong dependencies
Training run chỉ dùng 1.800 classes
Archive có thể chứa subset của 1.800 classes (eligible)
Khởi động production:
   - các lớp khớp và eligible có thể lấy từ archive
   - các lớp khác nạp bình thường
```

Các con số ở đây là **giả định minh họa**, không phải cam kết tỉ lệ coverage. Điều thực sự xảy ra phải được xem qua class-load/ CDS logs.

Một class có thể không được archive hoặc không tái sử dụng khi:

- Trial run chưa kích hoạt code path chứa class đó.
- Class được định nghĩa bằng một custom loader/bytecode transformation không đáp ứng điều kiện của implementation.
- Classpath/JAR/module options thay đổi khiến JVM không tin dùng archive cũ.
- JVM khác phiên bản/build/kiến trúc hoặc archive header không tương thích.
- Loader ở lần chạy tiếp theo dùng nguồn/identity/delegation không phù hợp archived metadata.
- JVM không map được archive và fallback theo chính sách `-Xshare`.
- Một số loại class được tạo động/hidden class hoặc mảng có quy tắc hỗ trợ riêng, tùy release.

**Đừng kết luận rằng mọi lớp được in ra bởi `-XX:DumpLoadedClassList` sẽ chắc chắn được phục hồi từ archive.** Danh sách loaded classes, tập eligible classes và tập classes thực sự **được dùng từ archive** là ba nhóm khác nhau.

## 4. Giới hạn theo ClassLoader: hiểu đúng nhất trong hệ plugin

Phân biệt ba trường hợp:

### A. Bootstrap, platform và application class loaders

Các lớp Java runtime/core thường có nhiều cơ hội sử dụng default CDS archive. Với AppCDS, classes từ system/application loader và platform loader cũng có thể eligible. Đây là đường đi phổ biến của ứng dụng được đóng gói từ JARs.

Nhưng ngay cả với application loader, không nên tuyên bố **mọi class** đều được archive. Nếu class chưa xuất hiện trong trial run hoặc môi trường mismatch, nó vẫn có thể load theo đường bình thường.

### B. Custom URLClassLoader

Một kết luận **sai** là “CDS hoàn toàn không hỗ trợ user-defined class loaders”. Tài liệu Oracle CDS trên Java 24 mô tả AppCDS có thể phục vụ **custom class loaders**. Dynamic archive từ JDK 13 cải thiện hỗ trợ cho use case này.

Một ứng dụng có thể:

```java
URL jar = Path.of("plugin.jar").toUri().toURL();
try (URLClassLoader pluginLoader = new URLClassLoader(
        new URL[]{jar}, ClassLoader.getPlatformClassLoader())) {
    Class<?> plugin = Class.forName(
            "plugin.Greeter", true, pluginLoader);
}
```

Snippet cần `import java.net.URL; import java.net.URLClassLoader; import java.nio.file.Path;` và là phần code trong method. Nó tạo plugin loader riêng. Nếu code path và archive đáp ứng điều kiện, một class do loader ấy định nghĩa **có thể** được lưu/tái sử dụng từ AppCDS.

**Đã kiểm chứng trên OpenJDK 24:** dynamic archive của ví dụ phần 8 chứa lớp `plugin.Greeter`, và `-Xlog:class+load=info` ở lần chạy sau báo:

```text
plugin.Greeter source: shared objects file (top)
```

Dòng được rút gọn bỏ timestamp/decorations, còn chuỗi source là kết quả quan sát thực. Đồng thời chương trình trả `c.getClassLoader() == pluginLoader` là `true`. Archive reuse **không làm mất defining loader**.

### C. Custom loader tải bytes không chuẩn hoặc định nghĩa class động

Một loader có thể đọc bytes từ database/network, tạo bytecode qua ASM, instrument từng class hoặc override `loadClass` để đổi delegation. Với trường hợp này:

- `CodeSource` tùy chỉnh **không phải bảo đảm** class được CDS hỗ trợ.
- Việc cùng binary name ở hai lần chạy chưa đủ để đảm bảo archive class match.
- Có thể cần cơ chế ghi nhận/định danh class và hỗ trợ archive dành riêng cho implementation/JDK release.
- Nếu bytes sinh phụ thuộc thời điểm/random/env, archive reuse có thể không khả thi.
- Nếu phần class chưa archived, JVM thường load theo đường chuẩn; đừng tuyên bố tối ưu bị “hỏng” toàn bộ chỉ vì một class fallback.

**Quy tắc thực hành:** hỏi bằng log **“class X, do loader Y, ở run này đã được lấy từ shared objects file chưa?”**. Không suy đoán theo tên `URLClassLoader` hoặc `SecureClassLoader`.

## 5. Static archive so với dynamic archive: nên dùng khi nào?

### Static dump dựa trên class list

Quy trình Oracle Java launcher điển hình:

```bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist \
     -cp app.jar demo.CdsDemo
java -Xshare:dump -XX:SharedArchiveFile=app-static.jsa \
     -XX:SharedClassListFile=app.classlist -cp app.jar
java -XX:SharedArchiveFile=app-static.jsa \
     -cp app.jar demo.CdsDemo
```

Đây là **mẫu giải thích flags**, cần ứng dụng/args/dependencies đúng thực tế. Bài tập chính phần 8 chọn **dynamic** để tránh phụ thuộc nội dung classlist và trình tự static dump. Với static CDS, Oracle Java 25 docs yêu cầu đường `-cp` chứa JARs thích hợp khi ghi classlist và tạo archive; các restrictions theo release phải được kiểm tra.

### Dynamic AppCDS

Phương án ít bước hơn:

```bash
java -XX:ArchiveClassesAtExit=app.jsa \
     -cp app.jar demo.CdsDemo
java -XX:SharedArchiveFile=app.jsa \
     -cp app.jar demo.CdsDemo
```

Tại lần chạy thứ nhất, JVM có thể ghi top archive vào `app.jsa` khi quá trình kết thúc bình thường. Tại lần chạy thứ hai, JVM map archive nếu tương thích. Nó không bảo đảm mọi class load trong trial run đều sẽ archive thành công hoặc mọi lần chạy đều có cache hit.

**Chi phí:** trial/dump run có thêm xử lý khi shutdown, tạo tệp archive và tiêu thụ I/O/disk. Theo Oracle, archived form đôi khi **lớn hơn nhiều** so với bytes trong JAR. Không tạo archive mỗi lần khởi động production như thể đây là bước miễn phí.

### Có thể tạo archive từ JVM đang chạy?

Một số JDK hỗ trợ `jcmd <pid> VM.cds static_dump ...` / `dynamic_dump ...`. Dynamic dump bằng `jcmd` có thể cần JVM được khởi động với `-XX:+RecordDynamicDumpInfo`. Cú pháp/capabilities phụ thuộc release; đọc `java`/`jcmd` docs của đúng JDK.

**Không** đọc `jcmd` command minh họa như công thức có thể gọi từ mọi JDK vendor/process; công cụ có thể yêu cầu attach permission, JVM flags và điều kiện run nhất định.

## 6. Giới hạn do classpath, module path và layout JAR

Trong Oracle `java` launcher CDS/AppCDS docs, các restrictions quan trọng gồm:

1. **Đường classpath/module path:** việc tạo/reuse archives cho app classes thường yêu cầu nguồn JAR phù hợp. Non-empty class directories hoặc exploded modules có thể không được hỗ trợ cho archive creation/reuse của cấu hình nhất định. Tránh dùng `-cp out/classes` của IDE để kết luận coverage production tương đương JAR.
2. **Classpath order:** với static/dynamic archive, đường classpath lúc dùng archive phải thỏa điều kiện tương thích với lúc tạo, thường là **bằng hoặc mở rộng từ một prefix** theo quy tắc được tài liệu từng JDK mô tả. Thay đổi thứ tự JAR có thể khiến classpath check thất bại.
3. **Jar contents:** khi JAR được sửa sau archive generation, JVM có thể từ chối archive hoặc bỏ các phần không còn compatible. Đừng reuse archive vô điều kiện sau deploy plugin-v2.
4. **Module path:** chỉ một số layout/module paths được hỗ trợ; exploded modules, patched modules, upgrade module path và các flags nhất định có thể tắt CDS hoặc archived module graph optimization tùy JDK.
5. **JDK build:** archive gắn với runtime build/architecture/format. Nó **không phải JAR portable** có thể tạo trên JDK A rồi áp dụng cho mọi JDK B.
6. **Platform/JVM options:** module resolution options, heap/object layout và các flags ảnh hưởng archive có thể thay khả năng tái sử dụng.
7. **Current working directory/relative paths:** nếu archive/classpath URLs được tạo dựa trên relative paths, thay working directory giữa trial run và production có thể làm không khớp. Ưu tiên đường dẫn/cấu hình triển khai ổn định.

Một nguyên nhân thường gặp: developer tạo `app.jsa` bằng một JDK 24 build local, sau đó đặt trên Linux container JDK 21. Không nên kỳ vọng sử dụng được: **tạo archive với đúng JDK distribution/build/architecture của môi trường đích**, hoặc để pipeline production tạo archive.

**Nhấn mạnh:** các restrictions có khác biệt giữa JDK 17, 21, 24, 25 và 26; dùng docs phù hợp phiên bản. Đừng biến một điều kiện của static dump thành khẳng định “không có class nào từ directory được JVM sử dụng default CDS”, vì default archive vẫn có thể nạp core classes dù app classes không eligible.

## 7. Module options và archive: vì sao thay flags có thể mất lợi ích?

Với modular applications, không chỉ `-cp` mà `--module-path` và các options như `--module`, `--add-modules`, `--enable-native-access` có thể ảnh hưởng việc khớp archive. Oracle Java 25 docs yêu cầu một số tùy chọn module liên quan có giá trị đồng nhất giữa lúc tạo và lúc dùng archive để tối ưu đầy đủ.

Ví dụ:

```bash
java --module-path libs -m m.app/com.example.Main \
     -XX:ArchiveClassesAtExit=module-app.jsa

java --module-path libs -m m.app/com.example.Main \
     -XX:SharedArchiveFile=module-app.jsa
```

Đây là **mẫu cấu hình**, chưa phải chương trình chạy vì phải có modular artifacts thật. Nếu trial run dùng `--add-modules m.analytics` mà production dùng `--add-modules m.reporting`, JVM có thể **không dùng archived full module graph** hoặc bỏ tối ưu tùy class/linking data.

Một số flags như `--upgrade-module-path`, `--patch-module`, `--limit-modules` có thể vô hiệu hóa CDS theo Oracle docs. Không tự giả định một cấu hình build-time chạy với `--patch-module` của test cũng cho archive reuse trong production.

### Custom ModuleLayer

Class loaders được tạo bởi `ModuleLayer.defineModulesWithOneLoader`/`defineModulesWithManyLoaders` có module configurations và mapping riêng. AppCDS có thể tối ưu một số classes tùy cách JVM ghi nhận chúng, nhưng **không hứa toàn bộ class trong mọi layer đều được archive**.

Hỏi:

- Module `X` đã được resolved trong training run chưa?
- Class `Y` có được load qua đúng loader/module path lúc tạo archive không?
- Lúc chạy production, configuration/loader identity/URLs có còn match?
- Class đang xuất hiện trong `-Xlog:class+load` từ shared archive hay từ file/module image?

Không nên sử dụng `--add-reads`/`--add-exports`/`--add-opens` như cách “bật AppCDS”; chúng điều chỉnh JPMS access graph, không phải lệnh tạo archive.

## 8. Thực hành đầy đủ Java 17+: app.jar + plugin.jar + URLClassLoader

Thí nghiệm này tạo một ứng dụng `demo.CdsDemo` trong `app.jar` và một plugin `plugin.Greeter` trong `plugin.jar`. `CdsDemo` dùng `URLClassLoader` với parent là platform loader để định nghĩa class plugin. Khi dùng `-XX:ArchiveClassesAtExit` và sau đó `-XX:SharedArchiveFile`, ta quan sát **JVM logs** để xác định class có từ archived data hay không.

### Cấu trúc thư mục

```text
src/
  demo/CdsDemo.java
  plugin/Greeter.java
classes/
  app/            (javac tạo)
  plugin/         (javac tạo)
app.jar           (jar tạo)
plugin.jar        (jar tạo)
app.jsa           (lần chạy dump tạo)
```

**File `src/demo/CdsDemo.java`:**

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class CdsDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("main class: "
                + CdsDemo.class.getName());
        System.out.println("main system loader: "
                + (CdsDemo.class.getClassLoader()
                    == ClassLoader.getSystemClassLoader()));

        URL pluginUrl = Path.of("plugin.jar")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{pluginUrl},
                ClassLoader.getPlatformClassLoader())) {

            Class<?> c = Class.forName(
                    "plugin.Greeter", true, loader);

            System.out.println("plugin defining loader: "
                    + (c.getClassLoader() == loader));
            System.out.println("plugin message: "
                    + c.getMethod("greet").invoke(null));
        }
    }
}
```

**File `src/plugin/Greeter.java`:**

```java
package plugin;

public class Greeter {
    public static String greet() {
        return "hello-appcds";
    }
}
```

### Biên dịch bằng JDK 17+ và đóng JAR

Đứng trong thư mục gốc chứa `src`:

```bash
javac --release 17 -d classes/app src/demo/CdsDemo.java
javac --release 17 -d classes/plugin src/plugin/Greeter.java
jar --create --file app.jar -C classes/app .
jar --create --file plugin.jar -C classes/plugin .
```

Lưu ý `plugin.jar` **không được thêm vào application classpath**: chỉ `-cp app.jar` ở các bước sau. Plugin được tìm qua `URLClassLoader` riêng, giúp kiểm tra đúng trường hợp custom defining loader.

### Chạy baseline

```bash
java -cp app.jar demo.CdsDemo
```

**Stdout chính xác trên OpenJDK 24.0.2 (cùng một JVM build đã dùng ở các lần sau):**

```text
main class: demo.CdsDemo
main system loader: true
plugin defining loader: true
plugin message: hello-appcds
```

### Tạo dynamic AppCDS archive

```bash
java -XX:ArchiveClassesAtExit=app.jsa \
     -cp app.jar demo.CdsDemo
```

Lệnh dùng xuống dòng kiểu Bash; PowerShell chạy trên **một dòng**:

```powershell
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar demo.CdsDemo
```

Sau run, file `app.jsa` xuất hiện khi JVM hỗ trợ/đủ điều kiện và archive creation thành công. **Thí nghiệm trên OpenJDK 24.0.2 đã tạo `app.jsa` thành công**, chương trình vẫn in bốn dòng như baseline.

### Dùng archive và xem CDS logs

```bash
java -Xlog:cds=info -XX:SharedArchiveFile=app.jsa \
     -cp app.jar demo.CdsDemo
```

Trên bản chạy kiểm thử, log gồm các tín hiệu:

```text
[info][cds] Opened archive ...classes.jsa.
[info][cds] Opened archive app.jsa.
```

Đây là **trích đoạn rút gọn bỏ timestamp/đường dẫn cụ thể**, không phải toàn bộ stdout/stderr cố định. Archive base và top được mở; chương trình vẫn trả bốn dòng giống baseline.

### Chứng minh lớp đã được dùng từ archive

```bash
java -Xlog:class+load=info \
     -XX:SharedArchiveFile=app.jsa \
     -cp app.jar demo.CdsDemo
```

Trong test OpenJDK 24, hai log entries rút gọn thành:

```text
demo.CdsDemo source: shared objects file (top)
plugin.Greeter source: shared objects file (top)
```

**Đây mới là bằng chứng class-level cụ thể**, thay vì chỉ thấy file `app.jsa` tồn tại. Đặc biệt, `plugin.Greeter` là lớp do **custom `URLClassLoader`** định nghĩa (theo stdout).

### Đối chứng tắt CDS

```bash
java -Xshare:off -Xlog:class+load=info \
     -cp app.jar demo.CdsDemo
```

Với cùng artifact trong thử nghiệm, class-load logs đã chuyển về nguồn JAR:

```text
demo.CdsDemo source: file:/.../app.jar
plugin.Greeter source: file:/.../plugin.jar
```

Các đường dẫn là **trích đoạn đã lược phần absolute path**; không coi hai dòng này là stdout đầy đủ. Cả hai lượt chạy đều in kết quả chức năng giống nhau: chương trình đúng cả khi có archive lẫn khi không.

### Giải thích kỹ thuật

1. `app.jar` chứa main class và đi qua **system loader**.
2. `plugin.jar` chỉ nằm trong `URLClassLoader` mà chương trình tạo, không thuộc `-cp`.
3. Trong trial run, class plugin được load nên có cơ hội được JVM ghi nhận để archive.
4. Lần chạy tiếp theo cùng JDK/JAR/configuration, các classes eligible có thể được tìm trong top archive; test cho thấy cả `demo.CdsDemo` và `plugin.Greeter` được báo `shared objects file (top)`.
5. `plugin defining loader: true` vẫn đúng: CDS không biến plugin class thành system-loader class.
6. `-Xshare:off` là đối chứng xác nhận Java vẫn hoạt động khi archive không tham gia, còn JVM đọc class từ JAR bytes.

**Kết quả có tính môi trường:** JDK 24.0.2 được kiểm thử. Với JDK khác, custom loader khác hoặc archive mismatch, `plugin.Greeter` có thể fallback hoặc không eligible. Hãy kiểm tra log của **chính JVM và bản triển khai của bạn**, không sao chép log trong bài làm giả định.

## 9. Đọc class-load logs và CDS diagnostics đúng cách

Các lựa chọn thường gặp trên HotSpot:

```text
-Xlog:cds=info
-Xlog:class+load=info
-Xlog:class+load=debug
-Xshare:off
-Xshare:auto
-Xshare:on
```

Ý nghĩa:

- `-Xlog:cds=info`: có mở archive nào, mapping/configuration và các vấn đề cơ bản không?
- `-Xlog:class+load=info`: class **cụ thể** được báo source như `shared objects file`, `shared objects file (top)`, `file:/...jar` hoặc nguồn runtime image.
- `-Xlog:class+load=debug`: thêm thông tin có thể hỗ trợ chẩn đoán, nhưng log dài và version-specific.
- `-Xshare:off`: phép đối chứng tắt CDS.
- `-Xshare:on`: hữu ích để bắt mismatch trong test vì có thể fail startup, **tránh ép production**.

**Không coi `source: shared objects file` của `java.lang.String` là bằng chứng AppCDS cho plugin thành công.** Nó có thể chỉ là **default base archive**; bạn cần tìm chính tên plugin class và nhìn `(top)`/source phù hợp.

Một bộ lọc thực tế:

```bash
java -Xlog:class+load=info -XX:SharedArchiveFile=app.jsa \
     -cp app.jar demo.CdsDemo 2>&1 |
     grep -E 'demo.CdsDemo|plugin.Greeter'
```

Lệnh `grep` là cú pháp Bash/Linux/macOS; trên PowerShell có thể thay bằng `Select-String 'demo.CdsDemo|plugin.Greeter'`. Vì `-Xlog` in rất nhiều classes, lọc giúp xác định đúng loại loader và source. Khi dùng command trên production, logging có thể ảnh hưởng hiệu năng/I/O và tiết lộ đường dẫn triển khai.

### Những điều KHÔNG được suy ra từ logs

- Một class load từ archive không chứng minh **toàn bộ application** nhanh hơn trên production.
- Log `shared objects file` không cho biết mức savings bytes/RSS cho từng class chính xác.
- Có `app.jsa` không chứng minh toàn bộ classes đều load từ top archive.
- Nhiều classes không archived không tự chứng minh CDS tổng thể vô dụng; default JDK classes vẫn có thể hưởng lợi.
- `CodeSource.location` phản ánh provenance metadata của loader, còn class-load log phản ánh JVM source ở lượt load, và archive-use là một lớp thông tin khác. Cần đọc chung thay vì trộn hai khái niệm.

## 10. Lỗi cấu hình thường gặp với plugin framework

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `app.jsa` có nhưng plugin class vẫn `source: file:/...plugin.jar` | Plugin class chưa archived, loader không eligible, config không khớp, archive chưa được chọn. | Quan sát training path, class-loader behavior, logs lúc dump/use. |
| `app.jsa` không được tạo | Trial run không thoát đúng, sai archive path/quyền ghi, không có compatible base, JDK flags xung đột. | Xem stderr/exit code, kiểm tra base archive và quyền. |
| Chạy JDK mới sau cập nhật JDK thì archive không dùng | JDK build/format mismatch. | Tạo lại archive bằng đúng JDK runtime mới. |
| Cập nhật plugin.jar nhưng vẫn dùng archive cũ | Artifact/path/checksum không còn khớp; JVM có thể từ chối/bỏ archived entries. | Đánh version archive cùng image/artifacts; regenerate archive. |
| IDE `-cp out/classes` thử thành công app nhưng AppCDS ít hiệu quả | Directory layout không giống production JAR/config và có restrictions với archived app classes. | Train từ packaged artifacts giống production. |
| `-Xshare:on` làm service không start | CDS archive không dùng được, và chế độ `on` bắt buộc. | Không dùng `on` trong prod; kiểm tra mismatch, dùng `auto`. |
| Static classlist nhiều nhưng archive không chứa class custom loader | Eligibility/loader/classlist constraints khác nhau. | Thử dynamic archive, kiểm tra logs; đừng đảm bảo mọi loader được support. |
| Parent-first load plugin API từ host thay vì plugin JAR | Loader khác với dự tính; archive không phải nguyên nhân trực tiếp. | Kiểm tra defining loader và delegation. |
| Tắt CDS nhưng startup vẫn chậm | Bottleneck do I/O, DI container, reflection, network, DB, JIT warmup hoặc app init. | Profile startup, tách parse/link và application init. |
| Nhiều archive files chiếm dung lượng | AppCDS tạo bản lưu metadata, có thể lớn hơn class bytes. | Chọn tập class có giá trị, dọn archives theo version. |
| Dùng `--patch-module` khi dump archive | Một số JVM/module options vô hiệu hóa CDS. | Đọc restrictions đúng JDK, bỏ flags không phù hợp trong pipeline. |

Một custom `ClassLoader` **không nên override delegation/defineClass chỉ để ép được archived classes**; làm vậy có thể phá class identity, package sealing, xác thực nguồn hoặc logic plugin. Trước hết kiểm thử CDS của JVM hiện hữu, rồi tối ưu với cơ chế được JDK/framework hỗ trợ.

## 11. Đo hiệu quả CDS/AppCDS có ý nghĩa

Muốn biết AppCDS có đáng đưa vào vận hành, hãy đo ba cấu hình bằng **cùng artifacts và JDK build**:

A. **Không dùng CDS:** `-Xshare:off`.

B. **CDS mặc định:** không truyền `-XX:SharedArchiveFile`, để JVM dùng default base archive nếu có.

C. **AppCDS:** `-XX:SharedArchiveFile=app.jsa` với archive được tạo từ trial run phù hợp.

Mục tiêu đo:

| Chỉ số | Vì sao quan trọng | Cách đo gợi ý |
| --- | --- | --- |
| Startup latency (p50/p95) | AppCDS thường cải thiện phần cold start. | Timestamp ready-to-serve, nhiều lần chạy độc lập. |
| Time-to-first-request | Gần nhu cầu người dùng hơn tổng main duration. | Kích hoạt health/readiness endpoint và đo end-to-end. |
| RSS/PSS của nhiều JVM processes | Xem lợi ích shared pages trong cùng máy. | OS memory tools; tránh chỉ cộng heap sizes. |
| Heap/metaspace memory | Phân tích áp lực bộ nhớ khác nhau. | JFR/jcmd/metrics, hiểu CDS metadata được mmap ngoài heap. |
| Archive size | Chi phí disk và deploy/cache management. | Kích thước `.jsa` và artifact images. |
| Number of actual archived class loads | Đánh giá coverage thay vì đoán. | `-Xlog:class+load=info` đã lọc tên. |

**Không công bố số % cải thiện không đo được.** Một app chủ yếu đợi network/database có thể thấy lợi ích nhỏ dù hàng trăm core classes được share. Một CLI tool khởi động thường xuyên có thể thấy lợi ích đáng kể.

### Quy trình benchmark đơn giản

1. Dùng cùng host, JDK build, JVM flags quan trọng, artifacts và môi trường.
2. Tách chi phí **archive generation** khỏi lần khởi động đo production.
3. Chạy đủ số lần (ví dụ vài chục lần) cho A/B/C; đảo thứ tự để giảm thiên lệch page cache/thermal effects.
4. Nếu cần cold-cache behavior, mô tả chính xác trạng thái OS page cache, không gọi mọi lượt sau run đầu tiên là “cold”.
5. Không bật `-Xlog:class+load` trong đo latency chuẩn nếu logger gây I/O/overhead; dùng logs trong vòng kiểm tra archive coverage riêng.
6. Báo số mẫu, JDK version, archive/JAR hashes, median/p95 và sai số/độ phân tán.
7. Đo nhiều JVM processes song song nếu mục tiêu là footprint chia sẻ; một JVM duy nhất không phản ánh đầy đủ saving cross-process.

Ví dụ lệnh chạy từng cấu hình (đo bằng công cụ ngoài như `time`, `Measure-Command` hoặc hệ telemetry):

```bash
java -Xshare:off -cp app.jar demo.CdsDemo
java -cp app.jar demo.CdsDemo
java -XX:SharedArchiveFile=app.jsa -cp app.jar demo.CdsDemo
```

Các lệnh này **không tự tính benchmark thống kê**. Phần 8 chỉ kiểm chứng chức năng và archive source, không đo tốc độ.

## 12. AppCDS trong plugin hot reload: archive và lifecycle

Trong hệ plugin có thể reload:

```text
Host process
   |
   +-- PluginLoader v1 -> plugin.jar v1
   |        (được dùng trong AppCDS trial run)
   |
   +-- PluginLoader v2 -> plugin.jar v2
            (artifact/bytes khác; không thể giả định dùng archive v1)
```

CDS cache **không** bảo đảm plugin v2 tương thích archived representation của v1. Khi đổi version, hãy xem archive là **artifact cùng vòng đời deploy/JDK image** chứ không phải database vĩnh viễn có thể dùng cho mọi plugin revision.

Cũng cần phân biệt:

- **Đóng loader**: `URLClassLoader.close()` giải phóng file/JAR handles của loader theo API; không ép ngay class unloading.
- **Đỡ load work nhờ archive**: một phần class metadata có thể phục hồi nhanh ở JVM startup hoặc class loading, nhưng class vẫn tuân thủ defining-loader identity.
- **Hot reload trong cùng process**: có thể dùng loader generation mới; archive reuse cho một generation không có nghĩa runtime thay class objects thế hệ cũ.
- **GC/unloading**: phụ thuộc reachability của loader, threads, TCCL, ThreadLocal, host static caches; AppCDS không sửa leaks lifecycle.
- **Security**: archive không sandbox plugin; bytecode không đáng tin vẫn cần boundary phù hợp.

Một hướng vận hành tốt: pin phiên bản JDK/JAR/plugin set, tạo archive như một phần **deployment image có version**, kiểm tra logs khi khởi động, tạo archive lại khi build/JAR thay đổi, và có fallback không CDS nếu môi trường không phù hợp.

## 13. CDS so với JDK 24+ AOT cache: không đánh đồng

Từ **JDK 24**, JEP 483 giới thiệu *Ahead-of-Time Class Loading & Linking*: một bước tiến so với CDS truyền thống, cho phép cache cả những trạng thái nạp/link classes được xây trong training run cho các lần JVM startup kế tiếp. JDK 25 tiếp tục bổ sung cải tiến tạo và khai thác AOT cache (JEP 514, 515).

**Khác biệt về học tập:**

| CDS/AppCDS truyền thống | AOT cache hiện đại |
| --- | --- |
| Tập trung lưu archived class data/metadata để load nhanh hơn. | Có thể lưu thêm class loading/linking state và các tối ưu mở rộng. |
| Thường dùng `.jsa` với `-XX:ArchiveClassesAtExit`, `-XX:SharedArchiveFile`. | Dùng quy trình/flags `-XX:AOT...`, khác theo JDK release. |
| Nền tảng lâu đời và tương thích nhiều JDK 17+. | JDK 24+ và cú pháp tiếp tục phát triển; không copy lệnh JDK 25 vào JDK 17. |
| Không biến loader identity thành một namespace chung. | Cũng phải bảo toàn class/module semantics. |

Đừng nhầm “JDK 24+ khuyến nghị AOT cache cho startup” với “CDS ngừng hoạt động”. Kết quả thực nghiệm của phần 8 trên OpenJDK 24 cho thấy **dynamic CDS vẫn chạy được**. Khi chọn giải pháp production, xem tài liệu JDK và framework thực tế, so sánh profiling và chi phí vận hành.

Nguồn: [JEP 483](https://openjdk.org/jeps/483), [Oracle Java SE 25 java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html) và [JEP 514](https://openjdk.org/jeps/514).

## 14. Những nhầm lẫn cần tránh

1. **“CDS chỉ giúp bootstrap classes.”** Không đúng tổng quát. AppCDS có thể hỗ trợ application/platform/custom-loader classes, tùy eligibility; test phần 8 xác nhận custom URLClassLoader trên JDK 24.
2. **“Có JAR trên classpath là được archive.”** Không. Class cần được load trong trial run và đáp ứng điều kiện archive.
3. **“AppCDS làm class của loader A và loader B thành cùng Class object.”** Không. Defining loader vẫn là thành phần class identity.
4. **“`getURLs()` chứng minh class được dùng từ archive.”** Không. Nó cho cấu hình search URL; muốn biết archive source phải xem JVM load logs.
5. **“File app.jsa tồn tại nghĩa AppCDS đang hoạt động.”** Không. Có thể mismatch và fallback; kiểm tra `-Xlog:cds` + `-Xlog:class+load`.
6. **“Dùng archive từ JDK build khác vẫn được.”** Không nên giả định; archive gắn với JVM distribution/build/architecture, không portable như JAR.
7. **“Archive từ app v1 phải giúp plugin v2.”** Không chắc; thay JAR/bytes/classpath có thể vô hiệu archived class reuse.
8. **“`-Xshare:on` là best practice production.”** Không; Oracle mô tả là testing option có thể abort startup nếu archive unusable.
9. **“Archive có hàng nghìn classes nghĩa startup chắc nhanh hơn một tỉ lệ cố định.”** Không; phải benchmark workload thực.
10. **“CDS chia sẻ toàn bộ Java heap của nhiều processes.”** Không; JVM processes vẫn có heaps/states riêng, chỉ một phần archived memory metadata có thể chia sẻ.
11. **“Không có class plugin nào archived nên nên bỏ mọi class loader abstraction.”** Không; plugin loaders giải quyết correctness/lifecycle, còn CDS là tối ưu tùy khả năng.
12. **“Dùng `-Xshare:off` sẽ khiến app sai logic.”** Một app không nên phụ thuộc CDS để có logic đúng; nếu khác hành vi, đó là dấu hiệu cần điều tra compatibility/bug.

## 15. Câu hỏi ôn tập

1. **CDS cải thiện chủ yếu phần nào?** Startup/class-loading metadata và memory footprint giữa một số JVMs; không phải mọi runtime CPU operations.
2. **AppCDS thêm gì vào CDS?** Cơ hội archive app/library classes ngoài core runtime classes.
3. **Default base archive khác top/dynamic archive thế nào?** Base thường đi cùng JDK; top chứa lớp bổ sung được ghi sau training run.
4. **Custom `URLClassLoader` có thể dùng archived class không?** Có trong điều kiện phù hợp, phụ thuộc JDK/eligibility; ví dụ OpenJDK 24 đã kiểm chứng.
5. **Một class có `source: shared objects file (top)` nghĩa gì?** JVM báo class được dùng từ top/dynamic shared archive trong lần load.
6. **`CodeSource.location == file:/...plugin.jar` có chứng minh CDS hit?** Không. Nó là metadata nguồn artifact, không phải class-load archive source.
7. **Tại sao training run cần đi qua nhiều chức năng?** Chỉ class được load/eligible trong trial run mới có cơ hội được archive.
8. **JAR thay sau tạo archive thì sao?** Tính tương thích archive có thể mất; nên regenerate cùng artifacts và JDK.
9. **`-Xshare:on` khác `-Xshare:auto`?** `on` yêu cầu sử dụng archive và có thể khiến startup lỗi, `auto` dùng khi có thể.
10. **Tại sao `-Xshare:off` hữu ích?** Làm đối chứng tắt CDS để quan sát class-file loads và đo chênh lệch.
11. **Vì sao không ép non-empty directory trong classpath vào pipeline dump?** Restrictions của CDS/AppCDS theo JVM release/layout; dùng JARs khớp production và xác minh doc.
12. **CDS có chữa leak TCCL/ThreadLocal giữ custom loader không?** Không; đó là bài toán lifecycle/reference.
13. **Nếu `String` được nạp từ `shared objects file` có chứng minh app plugin archived không?** Không; đó có thể là default base archive.
14. **Khi nào nên cân nhắc AOT cache mới hơn?** Trên JDK 24+ khi framework/JVM hỗ trợ và đo cho thấy có lợi; không trộn tùy chọn các phiên bản.

## 16. Tài liệu chính thức

- [Oracle Java SE 25 — java command: Application Class Data Sharing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xshare`, `-XX:ArchiveClassesAtExit`, `-XX:SharedArchiveFile`, static/dynamic archives, classpath/module restrictions và AOT.
- [Oracle Java SE 24 — Class Data Sharing](https://docs.oracle.com/en/java/javase/24/vm/class-data-sharing.html): CDS/AppCDS, default archives, mục tiêu startup/footprint, class loaders.
- [Oracle Java SE 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): lựa chọn cho Java 17 baseline.
- [dev.java — CDS and AppCDS in HotSpot](https://dev.java/learn/jvm/cps-appcds/): cách tạo static/dynamic archives và giới hạn thực hành.
- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): lịch sử AppCDS.
- [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): dynamic archive và custom loader support.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): AOT cache JDK 24.
- [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): cải tiến quy trình tạo AOT cache JDK 25.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): runtime class identity, defining loader và delegation.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): URL/JAR lookup, `getURLs()` và close behavior.
