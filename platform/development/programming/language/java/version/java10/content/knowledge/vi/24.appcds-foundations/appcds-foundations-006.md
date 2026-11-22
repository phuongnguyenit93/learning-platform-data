# Phạm vi lớp và class loader theo khả năng JDK đang dùng — AppCDS (Java 10+)

## 1. Vấn đề trọng tâm

Khi ứng dụng Java khởi động, JVM phải nạp nhiều lớp: lớp lõi của Java SE, lớp ứng dụng, thư viện trong JAR, các module và đôi khi lớp plugin được định nghĩa bởi `custom ClassLoader`. **Class Data Sharing (CDS)** và **Application Class-Data Sharing (AppCDS)** cho phép chuẩn bị trước metadata của một số lớp trong **shared archive**, giúp giảm chi phí khởi động và có thể tiết kiệm bộ nhớ khi nhiều JVM cùng dùng các trang dữ liệu chia sẻ.

Nhưng một điều thường bị hiểu sai là: “Bật AppCDS thì mọi lớp, kể cả lớp tải bằng custom loader, đều được nạp từ archive”. **Không đúng.** Phạm vi được hỗ trợ phụ thuộc vào **JDK đang dùng**, phương pháp tạo archive, nguồn JAR/module, loại class loader, quan hệ class identity và các điều kiện tương thích khi chạy lại.

Tại **Java 10**, JEP 310 bổ sung AppCDS để mở rộng CDS tới các lớp ứng dụng trên class path. Các thế hệ JDK sau bổ sung module path support, dynamic archive và nhiều tối ưu mới. Vì vậy bài học này vừa giải thích nền tảng Java 10, vừa tập trung vào **những quy tắc còn áp dụng trên JDK hiện đại**, không khuyến nghị sử dụng runtime hoặc cờ cấu hình Java 10 đã lỗi thời cho ứng dụng mới.

Sau bài này, bạn có thể:

1. Phân biệt CDS mặc định với AppCDS cho lớp ứng dụng.
2. Nhận diện bootstrap, platform, system/application và custom class loader.
3. Giải thích tại sao **defining loader** là một phần danh tính của class.
4. Hiểu ranh giới archive trên class path, module path, JAR và lớp được sinh động.
5. Phân biệt static archive với dynamic archive từ JDK 13.
6. Dùng `-Xlog:class+load=info` và `-Xlog:cds=info` để kiểm tra lớp có thực sự lấy từ archive hay không.
7. Viết thí nghiệm Java 10 chạy được, tạo dynamic archive bằng JDK hỗ trợ và xác minh custom loader có thể **hit/miss khác nhau**.
8. Chọn chiến lược CDS/AppCDS hay AOT cache theo phiên bản JDK thực tế, thay vì copy lệnh cũ.

## 2. CDS, AppCDS và hiệu quả được kỳ vọng

CDS lưu một phần dữ liệu lớp ở dạng HotSpot đã tối ưu trong một **archive**. Khi JVM tương thích khởi động, archive có thể được memory-map. Thay vì phải chuẩn bị từ đầu mọi metadata lớp, JVM có thể tận dụng phần đã lưu.

AppCDS (Application Class-Data Sharing) mở rộng cơ chế này tới **các lớp của ứng dụng và thư viện**, đặc biệt từ JAR được dùng trong quá trình chạy.

**Lợi ích có thể đạt được:**

- Rút ngắn startup time với workload nạp nhiều class.
- Chia sẻ một phần metadata giữa nhiều tiến trình JVM trên cùng host.
- Giảm chi phí nạp/parse class khi môi trường phù hợp.
- Hỗ trợ container hoặc dịch vụ có yêu cầu khởi động nhanh.

**Không được suy ra:**

- Archive là nơi chứa toàn bộ heap hay các object mutable của app.
- CDS bảo đảm mọi ứng dụng sẽ nhanh hơn cùng một tỉ lệ.
- Một class trong JAR tự động được archive chỉ vì JAR nằm trên class path.
- Có thể đem archive từ một bản JDK sang bản JDK khác mà không kiểm tra.
- CDS thay thế dependency management, bytecode verification, JPMS access hoặc cập nhật bảo mật.

Từ JDK 12, default CDS archive được đóng gói trong nhiều phân phối JDK và thường có hiệu lực mặc định khi không tắt. **Default CDS archive không đồng nghĩa đã có AppCDS archive dành cho chính ứng dụng của bạn.**

## 3. Class loader trong Java 10+ và phạm vi thường gặp

Một class loader có nhiệm vụ tìm hoặc định nghĩa class. Java có các loader built-in và cho phép tạo loader tùy chỉnh.

| Loader | Vai trò thường gặp | Cách nhận diện | Liên hệ với CDS/AppCDS |
| --- | --- | --- | --- |
| **Bootstrap** | Lớp lõi JVM và một số lớp Java SE | `String.class.getClassLoader() == null` trên HotSpot | Nhiều lớp nền tảng là đối tượng tối ưu CDS cơ bản |
| **Platform** | Các module/lớp JDK do platform loader định nghĩa | `ClassLoader.getPlatformClassLoader()` | Có khả năng dùng archive với lớp đủ điều kiện |
| **System/Application** | Lớp ứng dụng thông thường từ class path/module path | `ClassLoader.getSystemClassLoader()` | Trường hợp AppCDS điển hình |
| **Custom** | Plugin, framework, class loader con, loader riêng | Instance subclass `ClassLoader` như `URLClassLoader` | Có hỗ trợ ở JDK phù hợp, **không bảo đảm mọi trường hợp** |

Lưu ý:

- Bootstrap loader được biểu diễn bằng `null` trong nhiều lời gọi `Class.getClassLoader()`; không có nghĩa lớp ấy không được loader nạp.
- Không phải toàn bộ JDK module đều thuộc platform loader. Một số class được bootstrap loader định nghĩa.
- System loader thường là application loader built-in; JVM có cơ chế cho phép cấu hình system loader khác, vì vậy không dựa vào tên class implementation cố định.
- Custom loader có thể **ủy quyền** tới parent. Một loader được yêu cầu load class không nhất thiết là loader cuối cùng **định nghĩa** class ấy.
- Không thay đổi cây class loader chỉ vì muốn ép một class “dùng CDS”; sự thay đổi loader còn ảnh hưởng visibility, class identity, dependency resolution và isolation.

### Ví dụ xác định loader

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader platform = ClassLoader.getPlatformClassLoader();

System.out.println(String.class.getClassLoader() == null);
System.out.println(system.getParent() == platform);
```

Trong môi trường built-in application loader thông thường trên HotSpot, hai biểu thức có thể trả `true`. Nếu app sử dụng system loader tùy biến, phải kiểm tra thực tế.

## 4. Defining loader, initiating loader và Thread Context ClassLoader

Có ba khái niệm khác nhau:

- **Defining loader** là loader thực sự định nghĩa `Class<?>`. Bạn thường nhận được từ `SomeType.class.getClassLoader()`.
- **Initiating loader** bắt đầu một yêu cầu nạp class; có thể dùng delegation và nhận kết quả từ loader cha.
- **Thread Context ClassLoader (TCCL)** là giá trị `Thread.currentThread().getContextClassLoader()`. Framework có thể dùng nó cho service discovery hoặc plugin lookup.

Đổi TCCL **không** làm class đã tải bị định nghĩa lại:

```java
Thread thread = Thread.currentThread();
ClassLoader oldContext = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(customLoader);
    // Thread giờ có custom context loader.
    // Defining loader của các Class<?> đã tồn tại không đổi.
} finally {
    thread.setContextClassLoader(oldContext);
}
```

Đây là đoạn minh họa cần biến `customLoader`. Đừng xem TCCL là flag bật/tắt CDS. Nếu một class được bootstrap loader hoặc application loader định nghĩa, đổi context loader không biến nó thành class của custom loader.

### Parent delegation ảnh hưởng cách đọc log

Ví dụ một custom `URLClassLoader` có parent là system loader. Khi yêu cầu load `demo.SomeClass`, parent có thể tìm thấy và định nghĩa nó trước; custom loader không phải defining loader dù bạn gọi `custom.loadClass(...)`. Vì vậy kiểm tra `clazz.getClassLoader()` quan trọng hơn việc chỉ nhìn object loader dùng để khởi đầu lời gọi.

## 5. Cùng tên class nhưng khác defining loader vẫn là class khác

Java phân biệt class không chỉ bằng **binary name** mà còn theo loader đã định nghĩa nó.

```java
// Giả định first/second là hai custom loader độc lập:
Class<?> a = Class.forName("plugin.PluginGreeting", true, first);
Class<?> b = Class.forName("plugin.PluginGreeting", true, second);

System.out.println(a.getName().equals(b.getName())); // true
System.out.println(a == b);                          // false
```

Mã cần các biến loader và plugin thật; mục 12 có bản đầy đủ.

**Vì sao quan trọng với AppCDS?**

1. Một entry archive không được làm hai class có loader khác nhau trở thành cùng một kiểu để tăng cache hit.
2. Loader constraints, tính hợp lệ của bytecode, package và module access phải được bảo toàn.
3. Nếu plugin reload bằng loader mới, class identity mới xuất hiện dù binary name không đổi.
4. Hai class cùng tên từ hai loader có thể không cast cho nhau; việc quản lý API chung giữa plugin cần thiết kế đúng.
5. Archive hit/miss phải được đánh giá theo **lần nạp cụ thể**, không chỉ theo tên class.

Khi nghe “AppCDS hỗ trợ custom loader”, nên hiểu là **có những đường nạp lớp từ custom loader được HotSpot tối ưu**, chứ không phải toàn bộ loader tùy biến đều được bảo đảm như nhau.

## 6. Phạm vi theo từng thế hệ JDK — không áp dụng nhầm lịch sử

### Java 10: JEP 310 — Application Class-Data Sharing

Java 10 mở rộng CDS với các lớp ứng dụng, nhất là lớp tải từ **application class path**. Đây là mốc giới thiệu nền tảng AppCDS. Tuy nhiên tài liệu công cụ JDK 10 tại thời điểm đó ghi rằng **application classes từ module path không được AppCDS hỗ trợ**.

Đó là **giới hạn ở JDK 10**, không phải kết luận cho JDK hiện nay.

Một số cờ bật tính năng và điều kiện thương mại trong JDK 10 là thông tin **lịch sử**, không nên copy vào cấu hình hiện đại. Trên JDK đang được hỗ trợ, phải dùng tài liệu `java` của bản đó.

### Các JDK sau: mở rộng các nguồn class

Trên JDK hiện đại, các nguồn lớp có thể được CDS/AppCDS hỗ trợ gồm:

- Lớp nền tảng và JDK runtime image.
- Ứng dụng/thư viện từ **JAR trên class path**.
- Class/module trong **modular JAR trên module path** theo các điều kiện liên quan.
- Một số class được tải bằng **custom class loader** dưới những giới hạn thích hợp.

Đây là **tập có thể đủ điều kiện**, không phải danh sách toàn bộ class chắc chắn có trong archive.

### JDK 13: Dynamic CDS Archives — JEP 350

JDK 13 bổ sung cơ chế **ghi dynamic archive khi ứng dụng kết thúc**, giảm thao tác thu thập class list thủ công:

```bash
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar demo.ScopeDemo plugin.jar
```

Ví dụ chỉ chạy khi các JAR đã được tạo và JDK có hỗ trợ tùy chọn. Lệnh này **không có trong JDK 10**.

Dynamic archive cải thiện tính tiện dụng và hỗ trợ tốt hơn với ứng dụng có custom loader, nhưng vẫn không có quy tắc “mọi lớp nạp trong trial run đều sẽ được archive”.

### JDK 24 và về sau: AOT cache

JDK 24 giới thiệu **Ahead-of-Time (AOT) Cache** qua JEP 483. Các bản JDK mới tiếp tục phát triển hình thức tối ưu trước runtime, bao gồm class loading/linking và khả năng lưu những dạng thông tin khác. Đây là hướng **rộng hơn** metadata class sharing truyền thống.

Tài liệu JDK 25 và JDK 27 vẫn mô tả CDS/AppCDS. Với hệ thống chạy JDK 24+, nên đánh giá hướng AOT cache được JDK/framework hỗ trợ, không mặc định quy trình AppCDS năm 2018 là phương án tốt nhất cho mọi trường hợp.

Không trộn lệnh tạo AOT cache và CDS truyền thống từ hai thế hệ khác nhau khi chưa hiểu tính tương thích.

## 7. Bảng phạm vi: lớp nào có cơ hội được archive?

| Lớp và nguồn nạp | Loader | Khả năng AppCDS | Điều cần kiểm tra |
| --- | --- | --- | --- |
| Lớp JDK lõi như `String` | Bootstrap | CDS base archive thường liên quan | Không xem mỗi class JDK đều trong archive |
| Một số platform module | Bootstrap/Platform | Có thể archive nếu đủ điều kiện | Module và defining loader |
| Main class trong JAR | Built-in application | Trường hợp phổ biến | Class path khớp với training run |
| Dependency từ JAR class path | Built-in application | Có thể archive tập class đã dùng | Không archive toàn bộ JAR nếu chưa tải |
| Module app trong modular JAR | Loader theo JPMS | Hỗ trợ ở JDK mới | Module path và flags nhất quán |
| Class từ thư mục `.class` đang mở | Application | Không mặc định là nguồn archiving theo công cụ CDS | Dùng JAR cho thí nghiệm |
| Plugin class trong JAR | Custom `URLClassLoader` | **Có thể**, không chắc chắn | Log theo class/loader trên JDK mục tiêu |
| Cùng FQN qua hai custom loader | Hai custom loader | Có thể hit/miss khác nhau | Class identity phải giữ nguyên |
| Lớp tạo bằng bytecode runtime | Loader/frame­work đặc thù | Không được bảo đảm hỗ trợ tổng quát | Phân tích generated/hidden/proxy classes |
| Array classes ghi như tên class trực tiếp vào static class list | Do JVM tạo | Không thể xem như ordinary class list entries | Quy tắc riêng cho array classes |

**Phân biệt nguồn và kết quả:** “Lớp được nạp từ JAR” không có nghĩa “lớp đã được archive”. “Custom loader được JDK hỗ trợ” không có nghĩa “mọi instance custom loader đều hit cùng entry archive”.

## 8. Class path, module path và JAR: điều kiện để archive được dùng lại

Trong tài liệu `java` của JDK hiện đại, các điều kiện đáng lưu ý:

- CDS archiving của class path ứng dụng gắn với **JAR**, không nên xây bài test dựa vào thư mục non-empty chứa các `.class` rời.
- Class path và module path có các hạn chế đối với **non-empty directory**.
- Module path hỗ trợ **modular JAR**, không suy rằng các exploded module đủ điều kiện như JAR.
- Class path lúc tạo archive phải phù hợp với hoặc là **tiền tố** của class path lúc sử dụng trong quy tắc được mô tả; thay đổi tùy ý thứ tự entry có thể làm archive không được dùng.
- JAR được chỉnh sửa sau thời điểm archive tạo ra có thể khiến archive không được sử dụng.
- Các tùy chọn module graph như `--module-path`, `--module`, `--add-modules` phải phù hợp giữa các lần chạy khi có yêu cầu.
- Một số tùy chọn như `--patch-module`, `--upgrade-module-path` và `--limit-modules` không tương thích với CDS theo tài liệu JDK hiện đại.

Điều này **không có nghĩa** JVM bình thường không thể chạy class từ một directory. Nó chỉ nói về **điều kiện tối ưu archive**. Ứng dụng vẫn có thể chạy đúng khi CDS bị bỏ qua; đó là một vấn đề hiệu năng, không được làm thay đổi ngữ nghĩa class loading.

### Tập lớp archive không bằng toàn bộ library

Một ứng dụng có thể mang JAR chứa hàng nghìn class nhưng chỉ tải một phần khi startup/training. Tạo archive với workload đại diện giúp tập lớp có ích hơn. Archiving thêm những class không được sử dụng cũng tiêu thụ dung lượng archive mà không chắc cải thiện kết quả.

### Build JDK cụ thể là một phần ràng buộc

Archive phụ thuộc build/runtime và cơ chế nội bộ JVM. Khi đổi JDK, cập nhật bản vá, đổi image, thay JAR hoặc config liên quan, cần kiểm tra **tạo lại archive**. Không đóng gói archive như một artifact portable hoàn toàn tách khỏi JDK.

## 9. Dynamic archive và hai tầng

Ở cơ chế CDS truyền thống hiện đại, có thể hiểu:

```text
JDK/HotSpot
  └── Base/default shared archive
        └── Top/dynamic application archive
              ├── Eligible application classes
              ├── Eligible library classes
              └── Eligible custom-loader classes (có điều kiện)
```

JVM có thể dùng static/base archive và top/dynamic archive, với tùy chọn:

```text
-XX:SharedArchiveFile=<static_archive>:<dynamic_archive>
```

**Trên Windows**, dấu phân cách giữa hai archive là **dấu chấm phẩy** (`;`), không phải dấu hai chấm. Trong những trường hợp dynamic archive đã ghi liên hệ tới base archive thích hợp, có thể chỉ cung cấp đường dẫn top archive để JVM tìm ra base.

```bash
java -XX:SharedArchiveFile=app.jsa -cp app.jar demo.ScopeDemo plugin.jar
```

**Lưu ý:** Tên “static/dynamic” nói về cách tạo archive, không phải một bảo đảm rằng archive chứa “toàn bộ class tĩnh/động”. Tùy chế độ, tập lớp và mức độ tối ưu vẫn có khác biệt.

Nếu archive không tương thích, JVM có thể fallback sang đường load bình thường trong cấu hình cho phép. Đừng dùng `-Xshare:on` trong production chỉ để “bắt buộc nhanh” vì chế độ đó có thể làm tiến trình không khởi động.

## 10. Custom loader và điều kiện archive hit

Trên JDK hiện đại, AppCDS có thể hỗ trợ một số class được tải bằng **custom class loader**. Các tài liệu Oracle và dev.java mô tả khả năng này, nhưng cần hiểu ranh giới:

- Archive không được làm thay đổi **defining loader** của class.
- Class có thể không đủ điều kiện nếu bytecode được sinh/biến đổi theo runtime.
- Trường hợp trùng binary name qua nhiều loader có thể được xử lý khác nhau, để giữ class identity.
- Class không được tải trong training run thường không thể được kỳ vọng có trong archive ứng dụng đó.
- Khác biệt về class path, plugin JAR, module graph, JVM agent hoặc VM options có thể khiến archived form không được dùng.
- Mức độ hỗ trợ custom loader có thể khác nhau giữa các bản JDK và các phương pháp tạo archive.

**Ví dụ thực nghiệm:** Với hai `URLClassLoader` độc lập cùng đọc một plugin JAR, ở một bản JDK hiện đại, log cho thấy một lần tải `plugin.PluginGreeting` từ `shared objects file (top)` và một lần tải từ chính `plugin.jar`. Điều đó hoàn toàn phù hợp với việc hai `Class<?>` có danh tính khác nhau.

Kết luận đúng là **custom loader có thể hưởng lợi, nhưng cần kiểm chứng từng tình huống**, không phải “custom loader luôn không hỗ trợ” hoặc “custom loader luôn hỗ trợ”.

## 11. Thiết kế thí nghiệm có thể chạy lại

Ta cần hai JAR:

1. `app.jar` chứa `demo.ScopeDemo`, được system/application loader nạp thông qua `-cp`.
2. `plugin.jar` chứa `plugin.PluginGreeting`. JAR plugin **không nằm trên `-cp`**; main nhận đường dẫn và tự tạo custom URLClassLoader.

Chương trình:

- Kiểm tra bootstrap loader của `String`.
- Kiểm tra class main do system loader định nghĩa.
- Tạo hai URLClassLoader có **parent là platform loader** để class plugin được định nghĩa riêng biệt.
- Tải cùng binary name ở hai loader, so sánh identity.
- Thay đổi TCCL rồi khôi phục, chứng minh defining loader không đổi.
- Chạy bình thường, tạo dynamic archive trên JDK 13+, rồi dùng log quan sát archive hit.

Đây là thí nghiệm minh họa cơ chế VM, **không phải một mẫu kiến trúc plugin bắt buộc** cho mọi ứng dụng.

## 12. Chương trình đầy đủ — mã tương thích Java 10

Tạo tệp **`src/demo/ScopeDemo.java`**:

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.nio.file.Paths;

public final class ScopeDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected one plugin JAR path");
        }
        Path pluginJar = Paths.get(args[0]).toAbsolutePath();
        ClassLoader system = ClassLoader.getSystemClassLoader();
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        System.out.println("bootstrapStringLoaderNull=" +
                (String.class.getClassLoader() == null));
        System.out.println("mainDefinedBySystem=" +
                (ScopeDemo.class.getClassLoader() == system));
        System.out.println("systemParentIsPlatform=" +
                (system.getParent() == platform));

        URL url = pluginJar.toUri().toURL();
        try (URLClassLoader first = new URLClassLoader(new URL[] { url }, platform);
             URLClassLoader second = new URLClassLoader(new URL[] { url }, platform)) {
            Class<?> a = Class.forName("plugin.PluginGreeting", true, first);
            Class<?> b = Class.forName("plugin.PluginGreeting", true, second);
            System.out.println("pluginDefinedByFirst=" +
                    (a.getClassLoader() == first));
            System.out.println("pluginDefinedBySecond=" +
                    (b.getClassLoader() == second));
            System.out.println("sameBinaryName=" + a.getName().equals(b.getName()));
            System.out.println("sameClassObject=" + (a == b));
            System.out.println("pluginGreeting=" + a.getMethod("greeting").invoke(null));

            Thread thread = Thread.currentThread();
            ClassLoader oldContext = thread.getContextClassLoader();
            try {
                thread.setContextClassLoader(first);
                System.out.println("contextUsesFirst=" +
                        (thread.getContextClassLoader() == first));
                System.out.println("mainDefiningLoaderUnchanged=" +
                        (ScopeDemo.class.getClassLoader() == system));
            } finally {
                thread.setContextClassLoader(oldContext);
            }
        }
        System.out.println("done=true");
    }
}
```

Tạo tệp **`src/plugin/PluginGreeting.java`**:

```java
package plugin;

public final class PluginGreeting {
    public static String greeting() {
        return "Hello from custom loader";
    }
}
```

Ở thư mục gốc thí nghiệm, chuẩn bị hai thư mục đầu ra `appclasses` và `pluginclasses` có quyền ghi, sau đó biên dịch/đóng gói:

```bash
javac --release 10 -d appclasses src/demo/ScopeDemo.java
javac --release 10 -d pluginclasses src/plugin/PluginGreeting.java

jar --create --file app.jar -C appclasses .
jar --create --file plugin.jar -C pluginclasses .

java -cp app.jar demo.ScopeDemo plugin.jar
```

- `javac --release 10` xác nhận **source/API target Java 10**.
- `jar --create` là cú pháp công cụ JAR được JDK hiện đại hỗ trợ.
- Runtime chạy có thể là JDK mới; `--release 10` **không biến** JVM đang chạy thành JDK 10.
- `-cp app.jar` chỉ chứa class main; plugin.jar là **tham số ứng dụng** cho custom loader.

**Stdout chạy baseline đã kiểm chứng:**

```text
bootstrapStringLoaderNull=true
mainDefinedBySystem=true
systemParentIsPlatform=true
pluginDefinedByFirst=true
pluginDefinedBySecond=true
sameBinaryName=true
sameClassObject=false
pluginGreeting=Hello from custom loader
contextUsesFirst=true
mainDefiningLoaderUnchanged=true
done=true
```

Cách đọc:

1. `String.class.getClassLoader()==null` thể hiện biểu diễn bootstrap loader trong HotSpot thí nghiệm.
2. Main class thuộc system loader trong lối chạy `-cp` thông thường.
3. Parent của system loader là platform loader ở môi trường được test.
4. Plugin class được **hai loader riêng** định nghĩa, vì plugin.jar không nằm trên class path của system.
5. Hai binary name giống nhau nhưng hai đối tượng Class khác nhau, giữ đúng semantics loader.
6. Thay TCCL chỉ đổi context của thread, không đổi defining loader của main.
7. Hai loader được đóng khi thoát `try-with-resources`.

Nếu thay custom system loader của JVM, một số giá trị loader/parent có thể khác. Đừng biến các chi tiết của bản baseline thành bất biến cho mọi JVM cấu hình tùy chỉnh.

## 13. Tạo dynamic CDS archive và đọc log trên JDK 13+

Các lệnh tiếp theo **không phải tính năng Java 10**: Dynamic CDS Archives có từ JDK 13. Chúng chạy được trên JDK hiện đại khi VM và môi trường hỗ trợ.

**Bước 1: tạo archive từ một lần chạy**

```bash
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar demo.ScopeDemo plugin.jar
```

Sau khi chương trình chạy xong, JVM có thể ghi `app.jsa` chứa những lớp đủ điều kiện được tải trong quá trình đó.

**Bước 2: chạy lại với archive và log nạp class**

```bash
java -XX:SharedArchiveFile=app.jsa -Xlog:class+load=info -cp app.jar demo.ScopeDemo plugin.jar
```

**Bước 3 (tùy chọn): đọc log cơ chế CDS**

```bash
java -XX:SharedArchiveFile=app.jsa -Xlog:cds=info -cp app.jar demo.ScopeDemo plugin.jar
```

Không cần chạy đồng thời cả hai lệnh logging trừ khi muốn. Chúng có thể in nhiều dòng debug; hãy lọc class main và plugin ở console/log file.

### Kết quả quan sát trong lần thực nghiệm

Với hai JAR và source code phía trên, lần chạy đã kiểm chứng:

- Biên dịch Java 10 thành công.
- Baseline đúng 11 dòng stdout đã nêu.
- Tạo dynamic archive thành công; file `app.jsa` tồn tại sau khi JVM kết thúc.
- Lần chạy lại log **`demo.ScopeDemo source: shared objects file (top)`**.
- Với `plugin.PluginGreeting`, log có **một lần nạp từ `shared objects file (top)`** và một lần nạp khác từ **plugin.jar**.
- Khi dump, HotSpot có thể ghi warning **`Duplicated unregistered class`** đối với tên class plugin đã được hai custom loader định nghĩa.

Ví dụ một dòng log:

```text
[class,load] demo.ScopeDemo source: shared objects file (top)
```

Đây là **bằng chứng archive hit**, không chỉ là phỏng đoán vì file `app.jsa` có tồn tại.

Điều thú vị nhất: **hai custom loader nạp cùng tên lớp nhưng có thể có kết quả archive hit/miss khác nhau**. Điều đó không phá ngữ nghĩa của Java; hai Class object vẫn khác nhau, như đã thấy `sameClassObject=false`.

**Không cố định hóa mọi warning hay đường dẫn file:** cấu trúc log, thứ tự nạp, mức hỗ trợ custom class loader và quyết định archive phụ thuộc JDK/build. Trên JDK khác, plugin có thể không vào archive hoặc được xử lý theo cách khác. Điều nên test là **semantics class loading đúng và đọc log thực tế**.

## 14. Khi nào không nên dùng cách thử này trực tiếp?

- **Đang chạy JDK 10:** `ArchiveClassesAtExit` là API launcher của JDK 13+, không phải JDK 10. Đừng ép cờ mới lên JDK cũ.
- **Plugin được load từ nguồn không phải JAR hoặc bytecode thay đổi:** có thể không archive theo cách được ví dụ.
- **JAR/Classpath đang thay đổi liên tục:** archive có thể hết tương thích nhanh.
- **Framework có launcher đặc thù/nested JAR:** phải làm theo hướng dẫn CDS/AOT riêng của framework.
- **Mục tiêu production là hot reload:** class loader identity có thể thay đổi qua mỗi lần reload.
- **Muốn giảm warmup chứ không chỉ startup:** trên JDK 24+ nên cân nhắc thêm AOT cache nếu framework/JDK hỗ trợ.

Không nên xây script triển khai chỉ dựa trên việc `java` không in exception. Hãy xác thực **lớp nào thực sự dùng archive** và đo hiệu quả.

## 15. Xác minh bằng logging: điều gì có giá trị?

| Dấu hiệu | Kết luận đáng tin |
| --- | --- |
| `app.jsa` xuất hiện | Có file archive; **chưa chứng minh lớp cụ thể được reuse** |
| `-XX:SharedArchiveFile=...` không báo lỗi | JVM chạy; có thể archive đã được dùng một phần hoặc bỏ qua theo mode |
| `source: shared objects file (top)` | Class ở lần load tương ứng có **archive hit** |
| `source: file:/.../plugin.jar` | Class ở lần load tương ứng được nạp theo nguồn JAR |
| Warning duplicate unregistered class | Có hiện tượng lớp trùng namespace/loader làm VM bỏ qua một bản khi dump |
| `-Xlog:cds=info` | Thông tin tạo/nạp archive, các điều kiện tương thích/fallback |
| `-Xshare:off` | Đối chứng tắt CDS để đo chênh lệch |
| `-Xshare:on` | Chế độ chẩn đoán fail-fast, **không khuyến nghị production** |

Tài liệu Oracle nêu `-Xshare:on` là lựa chọn kiểm thử: nếu archive không dùng được, JVM có thể kết thúc ngay. Cấu hình production thường nên cho phép app hoạt động bình thường ngay cả khi tối ưu thiếu, và đưa trạng thái này vào log/metric.

### Kiểm tra hiệu năng

Để đánh giá CDS, đừng dùng một lần đo thời gian bằng mắt. Cần:

1. Giữ nguyên JDK build, máy/CPU, JAR, classpath, module path và startup workload.
2. Chạy nhiều lần có và không có archive.
3. Đo startup latency, CPU/memory footprint và phân bố kết quả.
4. Quan sát class load source của các class quan trọng.
5. Kiểm tra tính đúng đắn sau khi bật/tắt tối ưu.

Memory-mapped archive có thể làm một số metric trên Windows trông như **tăng address-space mapping**, dù việc chia sẻ trang giữa các JVM làm giảm tổng bộ nhớ vật lý. Cần chọn metric đúng.

## 16. Các giới hạn thường gặp khi dùng custom loader

**Một — Parent delegation:** loader con có thể nhận class do loader cha định nghĩa. `custom.loadClass(name)` không chứng minh custom loader là defining loader; dùng `clazz.getClassLoader()`.

**Hai — Class identity:** hai loader định nghĩa cùng binary name tạo hai class khác nhau; archive không thể hợp nhất chúng.

**Ba — Generated bytecode:** proxy, hidden classes, bytecode instrumentation và các loader chuyên biệt có điều kiện khác so với class thường từ JAR. Không có cam kết mọi generated class được archive.

**Bốn — Hot reload:** một lớp được reload qua loader mới có class identity mới. Archive có thể không tối ưu đường load tương ứng.

**Năm — Module access:** việc có archive không cho phép vượt qua module readability, exports/opens hoặc kiểm tra bytecode.

**Sáu — Agents và bytecode transformer:** training run thiếu agent nhưng production có agent có thể tạo khác biệt, làm một số tối ưu không dùng được. Phải test cấu hình tương đồng.

**Bảy — Resource lifecycle:** nếu tự tạo URLClassLoader, đóng loader đúng thời điểm theo hợp đồng. Đóng loader không đồng nghĩa class đã unload ngay; phụ thuộc tham chiếu và GC.

**Tám — Nhiều process:** bộ nhớ metadata chia sẻ hiệu quả hơn khi nhiều JVM có thể mmap cùng archive đúng điều kiện; không suy rằng mọi process trên máy khác nhau chia sẻ chung vật lý memory pages.

## 17. AOT cache của JDK hiện đại: liên hệ nhưng không đồng nhất

JDK 24 đưa vào AOT cache, JDK 25/27 tiếp tục mở rộng và đơn giản hóa khả năng này. Mục tiêu là thực hiện thêm công việc **trước khi chạy** ứng dụng, ví dụ class loading/linking, thay vì chỉ cache dạng metadata truyền thống.

AOT cache có các điều kiện riêng về:

- JDK/distribution/build.
- Đường dẫn ứng dụng, classpath, module path.
- OS/CPU architecture.
- Training workload, nội dung dependency.
- Các tùy chọn JVM có thể không tương thích.

Không có lý do giả định một AOT cache tạo ra một lần có thể dùng vô hạn trên mọi container hoặc JDK mới. Khi framework cung cấp quy trình AOT riêng (ví dụ Spring trên JDK mới), ưu tiên tài liệu phiên bản của framework đó.

Điểm nhấn theo đề bài: **khả năng tối ưu class loading trong JDK mới còn phụ thuộc loader và cấu hình**; AOT cache không làm các quy tắc class identity trở nên không cần thiết.

## 18. Hướng dẫn triển khai theo khả năng JDK

| JDK/môi trường | Hướng thực hiện có trách nhiệm |
| --- | --- |
| Java 10 (mốc lịch sử) | Hiểu JEP 310; không triển khai runtime production mới chỉ để dùng cách bật AppCDS cũ |
| JDK 13+ có dynamic archive | Thử `ArchiveClassesAtExit` và `SharedArchiveFile` theo tài liệu version |
| JDK 24+ có AOT cache | Đánh giá AOT cache và workflow framework tương thích |
| JDK 25/27 | Đọc trực tiếp man page và tài liệu CDS/AOT của phiên bản đang cài |
| Ứng dụng classpath/JAR bình thường | Thường dễ thử AppCDS hơn loader/plugin tùy biến |
| App dùng nhiều plugin/custom loaders | Phải có test log, loader identity và fallback |
| App có instrumentation/hot reload | Đối chiếu điều kiện archive trong cấu hình thực |
| Container/image thường xuyên rebuild | Đưa quy trình tạo lại archive vào pipeline nếu có lợi |

Quy tắc: **không suy khả năng chỉ từ version string hay việc VM nhận cờ**. Cần đọc tài liệu đúng build và kiểm chứng trên runtime mục tiêu.

## 19. Sai lầm cần tránh

**1.** Nghĩ AppCDS tự archive mọi class trong JAR. Thực tế nó chỉ lưu lớp được chọn/đủ điều kiện.

**2.** Nghĩ JDK 10 và JDK 27 có cùng phạm vi module path. Tài liệu JDK 10 có hạn chế mà JDK mới đã thay đổi.

**3.** Nghĩ custom loader luôn không được AppCDS hỗ trợ. JDK hiện đại có những đường hỗ trợ có điều kiện.

**4.** Nghĩ mọi instance custom loader đều hưởng archive như nhau. Ví dụ hai URLClassLoader cho thấy có thể hit/miss khác nhau.

**5.** Nhầm binary name với toàn bộ class identity. Defining loader cũng là yếu tố quan trọng.

**6.** Nhầm TCCL với defining loader. Đổi TCCL không thay type identity.

**7.** Dùng `-XX:ArchiveClassesAtExit` trên JDK 10. Dynamic archive có từ JDK 13.

**8.** Coi file archive tồn tại là bằng chứng lớp plugin đã được lưu. Cần log class loading.

**9.** Tạo archive từ môi trường classpath/JDK khác rồi bắt production dùng. Điều kiện tương thích có thể không thỏa.

**10.** Thay JAR sau khi tạo archive nhưng giữ nguyên archive. Điều này có thể làm archive không dùng được.

**11.** Cho rằng class trong directory hay exploded module luôn tương đương class trong JAR đối với archiving. Công cụ CDS có ràng buộc riêng.

**12.** Chạy `-Xshare:on` ở production không có dự phòng. JVM có thể không khởi động khi archive không hợp lệ.

**13.** Nghĩ CDS làm thay đổi module permission/verification. Nó chỉ là tối ưu VM và phải giữ semantics.

**14.** Chỉ nhìn startup nhanh mà tuyên bố mọi plugin class đã hit. Phải xem nguồn load của từng class.

**15.** Nghĩ archive có thể chuyển giữa mọi JDK build như một JAR. Archive phụ thuộc VM/build.

**16.** Nghĩ có AOT cache thì không cần test class loader. Cơ chế AOT cũng phải giữ đúng loader identity và có điều kiện riêng.

## 20. Checklist code review/QA

- [ ] Xác định đúng JDK feature/update/build và vendor trên môi trường thật.
- [ ] Đã phân biệt CDS mặc định với AppCDS ứng dụng tự tạo.
- [ ] Không dùng cờ Java 10 đã lỗi thời cho JDK hiện đại.
- [ ] Có danh sách nguồn class: runtime image, class path JAR, modular JAR, custom loader.
- [ ] Kiểm tra defining loader của lớp, không nhầm với TCCL.
- [ ] Hai lớp cùng binary name nhưng loader khác được quản lý đúng.
- [ ] Dynamic dump chỉ dùng khi JDK hỗ trợ (JDK 13+).
- [ ] Đã kiểm tra hạn chế classpath non-empty directory và exploded module.
- [ ] JAR/module path/VM flags phù hợp giữa training, dump và run.
- [ ] Archive được tạo lại khi nâng JDK hoặc thay dependency.
- [ ] Có log `class+load`/`cds` để kiểm tra hit/miss.
- [ ] Không mặc định mọi generated class hoặc plugin class đều archived.
- [ ] Có policy khi archive không được dùng: fallback hoặc fail-fast chỉ ở test.
- [ ] Có test startup và memory footprint trên workload đại diện.
- [ ] Nếu dùng JDK 24+, đã cân nhắc AOT cache được framework hỗ trợ.
- [ ] Archive và JDK/JAR có nguồn gốc triển khai tin cậy.

## 21. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** CDS và AppCDS khác nhau ở điểm nào?

**Đáp án:** AppCDS mở rộng khả năng chia sẻ metadata từ lớp nền tảng tới các lớp ứng dụng/thư viện đủ điều kiện, trong khi CDS cơ bản chủ yếu tập trung lớp JDK.

**Câu 2.** JEP nào đưa AppCDS vào Java 10?

**Đáp án:** JEP 310.

**Câu 3.** `String.class.getClassLoader()==null` có nghĩa String không được nạp không?

**Đáp án:** Không. Null ở đây thường biểu diễn bootstrap class loader trong HotSpot.

**Câu 4.** Hai URLClassLoader độc lập định nghĩa `plugin.PluginGreeting`, có phải cùng một class runtime không?

**Đáp án:** Không. Dù binary name giống, defining loader khác nên Class object khác.

**Câu 5.** Đổi TCCL có thay defining loader của class đã có không?

**Đáp án:** Không. TCCL là context của thread, không thay class identity.

**Câu 6.** Java 10 có `ArchiveClassesAtExit` không?

**Đáp án:** Không. Dynamic CDS Archives được đưa vào ở JDK 13 (JEP 350).

**Câu 7.** AppCDS có hỗ trợ custom class loader trên JDK hiện đại không?

**Đáp án:** Có thể, dưới điều kiện JDK/VM và đường load lớp phù hợp; không đảm bảo mọi loader và mọi class đều hit.

**Câu 8.** `source: shared objects file (top)` trong log có nghĩa gì?

**Đáp án:** Lần nạp class tương ứng lấy dữ liệu từ top/dynamic archive.

**Câu 9.** Cùng tên class plugin nạp bởi hai loader có thể một lần hit, một lần miss không?

**Đáp án:** Có. Điều đó phù hợp với việc giữ namespace và class identity khác nhau.

**Câu 10.** JAR thay đổi sau khi dump archive, có nên reuse archive cũ không?

**Đáp án:** Không nên. Archive có thể không hợp lệ; cần tạo lại và kiểm thử.

**Câu 11.** Vì sao không dùng `-Xshare:on` cho mọi production deployment?

**Đáp án:** Đây là chế độ fail-fast nếu CDS archive không dùng được, có thể làm ứng dụng không khởi động.

**Câu 12.** Archive có phải artifact độc lập portable giữa mọi bản JDK không?

**Đáp án:** Không. Nó phụ thuộc runtime/build và dữ liệu ứng dụng, cấu hình.

**Câu 13.** Nếu app chạy bình thường với archive bật, có bảo đảm custom plugin đã dùng archive không?

**Đáp án:** Không. Phải đọc log nguồn nạp class hoặc thông tin archive.

**Câu 14.** JDK 24+ có gì cần cân nhắc thêm cho startup?

**Đáp án:** AOT cache, một cơ chế tối ưu rộng hơn CDS metadata truyền thống và có workflow/điều kiện riêng.

**Câu 15.** Một class từ JAR được load thành công, liệu chắc chắn nó có trong dynamic archive không?

**Đáp án:** Không. JVM chỉ lưu những lớp đủ điều kiện trong quá trình tạo archive.

**Câu 16.** Kiểm thử tốt nhất đối với AppCDS trong ứng dụng có custom loader là gì?

**Đáp án:** Kết hợp test class identity/defining loader, tạo archive với workload đại diện, chạy lại có log `class+load`, và đo startup/footprint trên JDK mục tiêu.

## 22. Tài liệu chính thức còn áp dụng

1. [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): mốc AppCDS trong Java 10.
2. [Oracle JDK 10 — java launcher, AppCDS](https://docs.oracle.com/javase/10/tools/java.htm): tham khảo **giới hạn lịch sử**, không sao chép cờ cũ.
3. [Oracle Java SE 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): kiến thức CDS/AppCDS hiện hành, built-in/custom loader, giới hạn.
4. [Oracle Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): class path/module path restrictions, static/dynamic archives, log và AOT.
5. [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): JDK 13, dynamic archiving.
6. [dev.java — CDS and AppCDS in HotSpot](https://dev.java/learn/jvm/cps-appcds/): quy trình CDS/AppCDS, hỗ trợ loader và thí dụ.
7. [Java SE 25 — ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): bootstrap/platform/system loader và delegation.
8. [Java SE 25 — URLClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): cách nạp class từ URL/JAR.
9. [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): hướng AOT cache ở JDK 24.
10. [Spring Framework — JVM AOT Cache](https://docs.spring.io/spring-framework/reference/integration/aot-cache.html): áp dụng trên framework hiện đại, cần kiểm tra version.

**Kết luận:** AppCDS mở rộng CDS tới lớp ứng dụng từ Java 10, nhưng **phạm vi class và class loader được tối ưu phụ thuộc JDK đang chạy**. Trên JDK mới, built-in và một số custom loader có thể dùng archived classes; tuy nhiên class identity, nguồn JAR, classpath/module path, version/build và cách tạo archive quyết định kết quả thực tế. Hãy **đo và đọc log**, đừng suy đoán; với JDK 24+, đánh giá thêm AOT cache nếu phù hợp.
