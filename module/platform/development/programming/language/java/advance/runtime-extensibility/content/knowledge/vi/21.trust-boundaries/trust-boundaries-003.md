# Vì sao class loader và JPMS không tạo môi trường cách ly mã độc

## 1. Kết luận và mô hình tin cậy

Trong Java, **`ClassLoader` và Java Platform Module System (JPMS) chủ yếu quản lý cách nạp, định danh, liên kết và truy cập các lớp/module**, chứ **không tự tạo một sandbox an toàn cho mã không đáng tin cậy**. Plugin chạy trong cùng tiến trình JVM với host vẫn có thể thực thi mã Java được phép ở cấp tiến trình. Nếu không có cơ chế cưỡng chế quyền độc lập, việc đưa plugin vào classloader riêng hoặc `ModuleLayer` riêng **không tự cấm** nó dùng tài nguyên hệ điều hành mà tiến trình Java được phép dùng.

Cần phân biệt rõ hai loại ranh giới:

- **Ranh giới cấu trúc:** lớp nào được loader nào định nghĩa; package nào được module export/open; module nào đọc được module khác; nhà cung cấp SPI nào được phát hiện trong layer. Đây là trọng tâm của classloader và JPMS.
- **Ranh giới tin cậy/bảo mật:** mã nào được phép đọc tệp, truy cập mạng, sử dụng thông tin nhạy cảm, chiếm CPU/RAM, tạo thread, làm ảnh hưởng trạng thái tiến trình hoặc thực hiện thao tác hệ điều hành. Việc cưỡng chế các quyền này phải được thiết kế riêng.

Một mô hình sai thường thấy:

```text
Host JVM
  +-- Loader A / ModuleLayer A --> plugin chưa tin cậy
  +-- Loader B / ModuleLayer B --> plugin khác

"Khai báo module và classloader riêng nên plugin A không
thể ảnh hưởng host/plugin B"  <-- KẾT LUẬN SAI
```

Mô hình đúng hơn:

```text
CÙNG MỘT JVM / CÙNG TIẾN TRÌNH HỆ ĐIỀU HÀNH
  |
  +-- Host classes / modules
  +-- Loader A -> plugin A
  +-- Layer B  -> plugin B
  |
  +-- Cùng Java runtime, heap và nhiều trạng thái JVM
  +-- Thường cùng danh tính/quyền OS của tiến trình
  +-- Các API Java SE khả dụng theo cấu hình runtime
  +-- Tài nguyên và giới hạn ở cấp tiến trình

Classloader / ModuleLayer = tổ chức kiểu và truy cập module;
không phải rào chắn quyền file, network, CPU hay bộ nhớ.
```

Điều này không có nghĩa classloader/JPMS “vô ích”: chúng rất quan trọng cho **tính đúng đắn, đóng gói, phát triển theo module, giảm xung đột thư viện và quản lý plugin tin cậy**. Nhưng các lợi ích đó không nên bị diễn giải thành một cam kết sandbox chống mã độc.

## 2. ClassLoader thực sự cô lập điều gì?

### 2.1. Định danh lớp và vùng nhìn thấy

JVM phân biệt một class theo **tên nhị phân và bộ nạp đã định nghĩa class**. Hai loader khác nhau có thể định nghĩa hai `com.example.Widget` riêng biệt, khiến chúng không tương thích ép kiểu dù tên giống nhau.

Một loader riêng thường cho phép:

- Nạp một bộ JAR chỉ dùng trong plugin; chọn phiên bản thư viện khác với host.
- Kiểm soát quá trình **tra cứu class/resource** và cơ chế ủy quyền cha–con.
- Đóng phạm vi class metadata và hỗ trợ vòng đời plugin; khi mọi tham chiếu thích hợp đã được giải phóng, classloader cùng các lớp có thể trở thành đối tượng được GC.
- Chỉ chia sẻ một API/SPI chung với host, thay vì để plugin lẫn lộn class implementation.

Ví dụ với `URLClassLoader`:

```java
// Đoạn minh họa; cần import java.net.* và java.nio.file.*.
URL jarUrl = Path.of("plugins", "example.jar").toUri().toURL();

try (URLClassLoader pluginLoader = new URLClassLoader(
        new URL[] {jarUrl}, Host.class.getClassLoader())) {
    Class<?> pluginClass =
            Class.forName("demo.plugin.PluginImpl", false, pluginLoader);
    System.out.println(pluginClass.getClassLoader() == pluginLoader);
}
```

Đoạn minh họa này giả định tồn tại `Host` và JAR chứa `demo.plugin.PluginImpl`; nó **không phải chương trình độc lập**. Tham số `false` của `Class.forName` yêu cầu không khởi tạo lớp ngay trong lời gọi. Việc có một `Class<?>` được nạp qua pluginLoader chỉ chứng minh ranh giới nạp/định nghĩa, **không** chứng minh quyền hệ điều hành bị hạn chế.

### 2.2. Parent-first và child-first không phải cơ chế bảo mật

Loader thường dùng **parent-first delegation**: hỏi cha trước rồi mới tìm ở đường dẫn riêng. Một số hệ plugin dùng child-first cho thư viện implementation để tách phiên bản. Cả hai là **chính sách tìm bytecode**, không phải chính sách cho phép/chặn thao tác nghiệp vụ hay I/O.

Ngay cả khi plugin không thể trực tiếp tham chiếu đến một package nội bộ của host, nó vẫn có thể sử dụng **API Java SE** mà runtime cho phép và những đối tượng host đã chia sẻ. Ví dụ, class `java.lang.System` thuộc nền tảng Java, không bị một plugin loader tự động thay bằng một bản “không có quyền” chỉ vì được nạp từ JAR riêng.

Điều quan trọng hơn: một plugin không đáng tin trong cùng JVM có thể ảnh hưởng tới trạng thái chung hoặc tài nguyên chung mà nó có thể tiếp cận. **Sự tách biệt namespace không đồng nghĩa tách biệt tiến trình hay quyền hạn.**

### 2.3. Bytecode verification không xác nhận ý định an toàn

JVM có cơ chế xác minh bytecode nhằm đảm bảo ràng buộc định dạng và tính an toàn kiểu ở mức máy ảo. Bytecode hợp lệ vẫn có thể chứa **logic không mong muốn**: chạy liên tục, sử dụng quá nhiều bộ nhớ, ghi lên dữ liệu mà tiến trình được phép ghi, phát sinh thread hoặc sử dụng những API mà host không định kiểm soát.

Vì thế, **“JAR nạp được, bytecode được verifier chấp nhận” không phải chứng chỉ đáng tin cậy**. Verifier giúp bảo vệ các bất biến của VM trong mô hình triển khai, không đánh giá tác động nghiệp vụ hoặc thay thế xác thực quyền truy cập.

## 3. JPMS bảo vệ tính đóng gói, không thay thế sandbox

JPMS cho phép mô tả quan hệ phụ thuộc và khả năng truy cập giữa các **named module**. Một `module-info.java` có thể chứa:

```java
module demo.plugin {
    requires demo.api;
    exports demo.plugin.spi;
    opens demo.plugin.model to demo.framework;
    provides demo.api.Service with demo.plugin.impl.ServiceImpl;
}
```

Đây là **tệp module descriptor minh họa**, cần những module/package/class tương ứng mới biên dịch được. Ý nghĩa các chỉ thị:

| Chỉ thị / cơ chế | Mục đích thật sự | Điều không được suy ra |
|---|---|---|
| `requires` | Module khai báo dependency và quan hệ readability | Không phải “cấp quyền được truy cập filesystem/network” |
| `exports` | Cho module khác truy cập public types trong package theo quy tắc Java | Không có nghĩa package khác không export tạo ra sandbox |
| `opens` | Cho phép deep reflection đối với package, có thể giới hạn theo module | Không phải cơ chế cấp hoặc thu hồi quyền OS |
| `uses` / `provides` | Khai báo tiêu thụ và cung cấp dịch vụ SPI | Provider không được tự kiểm chứng là đáng tin |
| `ModuleLayer` | Gom module đã resolve vào một layer có quan hệ tổ tiên | Không tạo JVM mới, process riêng hoặc heap riêng |
| `ModuleFinder` / `Configuration` | Tìm và giải quyết module cùng dependency | Không xác minh hành vi an toàn của bytecode |

**Một giới hạn mạnh vẫn có giá trị:** JPMS kiểm soát truy cập ở cấp module, bao gồm các quy tắc xuất package và khả năng mở cho reflection. Không được phủ nhận rằng `exports`, `opens` và strong encapsulation có tác dụng thực thi. Điều cần hiểu là chúng kiểm soát **mức truy cập các package/lớp qua hệ thống module**, chứ không áp một chính sách least-privilege cho toàn bộ các tác vụ mà mã plugin có thể yêu cầu JVM thực hiện.

Ví dụ, một named module có thể dùng các API công khai thuộc `java.base` (phụ thuộc mặc định của named module). Việc module không `requires demo.host` không làm mất khả năng dùng các API nền tảng được phép và không tự cấm thao tác trên tài nguyên tiến trình.

### 3.1. ModuleLayer không phải một “process container”

`ModuleLayer.boot()` là layer khởi đầu của các named modules được giải quyết khi JVM khởi động. Host có thể tạo thêm layer động để nạp plugin. Một layer có thể dùng classloader riêng, nhưng **vẫn ở trong cùng JVM**, với các thread, process permissions, tài nguyên CPU/RAM và nhiều trạng thái runtime dùng chung.

Ví dụ:

```java
ModuleLayer pluginLayer = ModuleLayer.boot()
        .defineModulesWithOneLoader(
                pluginConfig, ClassLoader.getSystemClassLoader());
```

Đây là đoạn minh họa, giả định `pluginConfig` đã được tạo bằng `Configuration.resolve` hợp lệ. `defineModulesWithOneLoader` không cấp một kernel namespace, user identity mới hoặc quota RAM riêng. Nó xác lập cách các named modules được định nghĩa vào layer bằng loader mới theo API JPMS.

### 3.2. Khả năng đọc module không đồng nhất với quyền làm việc

Đôi khi người học suy luận: “Plugin không `requires` module nội bộ của host, vậy nó không thể gây ảnh hưởng tới host.” Có hai thiếu sót:

1. Không đọc được một module nội bộ có thể giúp **hạn chế việc sử dụng trực tiếp API Java của module đó**, nhưng không áp đặt ràng buộc lên tất cả API nền tảng hoặc tài nguyên hệ điều hành.
2. Plugin có thể tương tác với host **thông qua giao diện/đối tượng được chia sẻ hợp lệ**. Nếu host vô tình trao một đối tượng có quyền quá rộng (ví dụ service thực hiện thao tác quản trị), một module descriptor có tính đóng gói tốt không tự ngăn việc lạm dụng giao diện đó.

JPMS hỗ trợ thiết kế API có phạm vi rõ. Nó **không tự đánh giá ý định và độ tin cậy của bên gọi**.

### 3.3. Named, automatic và unnamed module không là các mức sandbox

Một JAR có `module-info.class` và được resolve có thể là explicit named module. Một JAR không có descriptor nhưng được resolve trên module path có thể là automatic named module. Một JAR trên classpath thuộc unnamed module của classloader tương ứng.

Ba cách đóng gói/quản lý này có quy tắc truy cập khác nhau nhưng **không** ánh xạ thành “named module an toàn; unnamed module nguy hiểm”. Độ tin cậy là thuộc tính của **nguồn mã, quyền được cấp, review và ranh giới runtime**, không phải chỉ của hình thức package.

## 4. Những gì vẫn được chia sẻ trong cùng JVM

Kể cả khi classloader và ModuleLayer khác nhau, các thành phần vẫn sống trong **cùng tiến trình Java**. Mức chia sẻ cụ thể phụ thuộc cách tạo loader, API và thiết kế host, nhưng có các nguy cơ quan trọng:

| Tài nguyên / trạng thái | Vì sao module/loader riêng chưa đủ? |
|---|---|
| **Danh tính và quyền hệ điều hành của tiến trình** | Plugin chạy theo quyền process đã được JVM nhận; loader không tự tạo user ID riêng |
| **Heap/garbage collector** | Cùng JVM có tài nguyên nhớ chung, áp lực cấp phát ở một plugin có thể ảnh hưởng toàn process |
| **CPU, thread và scheduler** | Mã chạy trong process có thể tạo công việc chiếm tài nguyên; ModuleLayer không áp CPU quota |
| **`System.getProperties()`** và trạng thái hệ thống khác | Các API cấp JVM được dùng chung theo khả năng truy cập; loader không tạo bản sao System cho mỗi plugin |
| **`System.out`/`System.err`** | Streams và các trạng thái chung không tự tách theo layer |
| **File/network APIs** | Khả năng thực hiện bị chi phối bởi OS/quy tắc runtime thực tế, không phải `exports` của plugin |
| **Đối tượng host truyền vào SPI** | Nếu truyền reference tới service mutable/privileged, plugin dùng các phương thức được expose |
| **Đời sống của host JVM** | Một plugin lỗi nặng hoặc dùng tài nguyên quá mức có thể ảnh hưởng độ ổn định toàn ứng dụng |

Ví dụ một module có thể không được phép truy cập `com.host.internal.SecretManager` vì package không export, nhưng điều đó **không chứng minh** nó không thể gọi các API nền tảng hoặc tương tác với bất kỳ shared service hợp lệ nào. Tính đóng gói bảo vệ bề mặt API, không tự tách thực thể thực thi.

### 4.1. Không cần “bẻ khóa” JPMS để thấy giới hạn

Giới hạn bảo mật này không phụ thuộc vào hành vi vượt qua access control. Một plugin có thể dùng các API **hoàn toàn công khai và đúng quy tắc Java** nhưng vẫn tạo tác động không mong muốn. Do đó, không nên đặt mục tiêu “giấu mọi class của host khỏi plugin” rồi coi xong phần threat model.

Bài kiểm chứng an toàn ở phần 5 chỉ đọc một **system property giả lập vô hại** để chỉ ra rằng cả lớp được nạp riêng và module nằm trong layer động đều nhìn thấy **trạng thái JVM chung**. Không dùng tệp nhạy cảm, mạng hoặc thao tác gây hại.

## 5. Ví dụ Java 17+ hoàn chỉnh: hai cơ chế nạp, một trạng thái JVM

### 5.1. Mục tiêu kiểm chứng

Host đặt một giá trị cấu hình giả lập:

```text
demo.host.mode = ACTIVE
```

Sau đó host:

1. Nạp một lớp plugin từ JAR ngoài application classpath bằng `URLClassLoader` riêng.
2. Định nghĩa một named module plugin trong một `ModuleLayer` động.
3. Gọi **phương thức public** của cả hai thông qua reflection hợp lệ.
4. Quan sát cả hai đều đọc được system property đã được host đặt, dù classloader và module organization khác nhau.

Điều này minh họa **một trạng thái JVM dùng chung**. Nó **không** nhằm nói rằng mọi đối tượng riêng tư của host đều đọc được hoặc mọi quyền của host sẽ mặc nhiên được truyền qua tất cả cơ chế bảo vệ khác.

### 5.2. Cấu trúc tệp

```text
trust-boundary-demo/
├── classpath-plugin/
│   └── demo/loader/LoaderProbe.java
├── named-plugin/
│   ├── module-info.java
│   └── demo/moduleplugin/ModuleProbe.java
└── host/
    └── Host.java
```

Bản build sẽ tạo một plugin JAR ở `plugins/loader-plugin.jar`, một exploded named module trong `mods/demo.moduleplugin` và các class host ở `out/host`. Chỉ cần JDK 17+.

### 5.3. Plugin được nạp bằng URLClassLoader

**`classpath-plugin/demo/loader/LoaderProbe.java`**

```java
package demo.loader;

public final class LoaderProbe {
    private LoaderProbe() {
    }

    public static String readMode() {
        return System.getProperty("demo.host.mode");
    }
}
```

Phương thức chỉ đọc một property do host đặt, không thao tác tài nguyên bên ngoài. Không có phụ thuộc vào `Host`.

### 5.4. Plugin dạng named module

**`named-plugin/module-info.java`**

```java
module demo.moduleplugin {
    exports demo.moduleplugin;
}
```

**`named-plugin/demo/moduleplugin/ModuleProbe.java`**

```java
package demo.moduleplugin;

public final class ModuleProbe {
    private ModuleProbe() {
    }

    public static String readMode() {
        return System.getProperty("demo.host.mode");
    }
}
```

Module này chỉ cần `java.base` (được đọc ngầm) và export package chứa public API để host có thể gọi `readMode()` qua reflection đúng quy tắc module. Nó **không** yêu cầu host mở toàn bộ package hoặc dùng tùy chọn vượt qua encapsulation.

### 5.5. Host tạo classloader và ModuleLayer

**`host/Host.java`**

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Set;

public final class Host {
    public static void main(String[] args) throws Exception {
        System.setProperty("demo.host.mode", "ACTIVE");
        System.out.println("host=" + System.getProperty("demo.host.mode"));

        Path jar = Path.of("plugins", "loader-plugin.jar").toAbsolutePath();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {jar.toUri().toURL()},
                Host.class.getClassLoader())) {
            Class<?> type = Class.forName(
                    "demo.loader.LoaderProbe", true, pluginLoader);
            Object value = type.getMethod("readMode").invoke(null);

            System.out.println("loader=" + value);
            System.out.println("loader.separate="
                    + (type.getClassLoader() != Host.class.getClassLoader()));
        }

        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        Configuration config =
                ModuleLayer.boot().configuration().resolve(
                        finder, ModuleFinder.of(),
                        Set.of("demo.moduleplugin"));

        ModuleLayer layer =
                ModuleLayer.boot().defineModulesWithOneLoader(
                        config, ClassLoader.getSystemClassLoader());

        Class<?> type = Class.forName(
                "demo.moduleplugin.ModuleProbe",
                true, layer.findLoader("demo.moduleplugin"));

        Object value = type.getMethod("readMode").invoke(null);
        System.out.println("module=" + value);
        System.out.println("module.named=" + type.getModule().isNamed());
    }
}
```

**Giải thích trọng điểm:**

- `URLClassLoader` được tạo mới để thấy `loader-plugin.jar`; application classpath của host không chứa JAR đó.
- `LoaderProbe` là public class được pluginLoader định nghĩa. `loader.separate=true` thể hiện loader nạp plugin **khác** loader nạp host.
- `ModuleFinder.of(Path.of("mods"))` phát hiện exploded module `demo.moduleplugin`, rồi `Configuration.resolve` giải quyết module dựa trên boot configuration.
- `defineModulesWithOneLoader` tạo một layer mới, dùng loader được tạo cho các module của layer ấy với system loader làm parent.
- `ModuleProbe` thuộc một **named module**, xác nhận qua `getModule().isNamed()`.
- Cả hai plugin đều gọi `System.getProperty(...)` từ API Java công khai. Đọc được giá trị `ACTIVE` **không phải hành vi vượt quyền**: chỉ chứng minh lớp/module khác vẫn dùng chung trạng thái cấp JVM.
- Bài học bảo mật nằm ở việc **đã tách cách nạp và cách tổ chức module nhưng không tách trạng thái tiến trình**.

### 5.6. Biên dịch và chạy trên Windows PowerShell

Chạy các lệnh dưới đây từ thư mục `trust-boundary-demo`:

```powershell
New-Item -ItemType Directory -Force -Path out\loader,out\host,mods\demo.moduleplugin,plugins | Out-Null

javac -d out\loader classpath-plugin\demo\loader\LoaderProbe.java
jar --create --file plugins\loader-plugin.jar -C out\loader .

javac -d mods\demo.moduleplugin named-plugin\module-info.java named-plugin\demo\moduleplugin\ModuleProbe.java
javac -d out\host host\Host.java

java -cp out\host Host
```

**Stdout dự kiến với đúng cấu trúc và không có provider/trạng thái ngoài ảnh hưởng:**

```text
host=ACTIVE
loader=ACTIVE
loader.separate=true
module=ACTIVE
module.named=true
```

Không thêm plugin JAR vào `-cp`. Phần module cũng không cần xuất hiện ở boot layer vì host dùng `ModuleFinder` và tạo layer mới khi chạy. Trên macOS/Linux, dùng câu lệnh shell tạo thư mục tương đương và dấu `/` cho đường dẫn.

### 5.7. Những kết luận đúng và sai từ thí nghiệm

**Đúng:** việc đặt một class ở URLClassLoader riêng và một class ở named module thuộc ModuleLayer riêng **không tạo bản sao riêng của `java.lang.System` hay toàn bộ trạng thái JVM**.

**Sai:** “Vì đọc được property nên plugin có quyền đọc mọi object private trong host.” Quy tắc package access, module exports, reflection và capability của đối tượng vẫn có tác dụng. Thí nghiệm **không** kiểm tra khả năng truy cập mọi class, cũng không chứng minh chính sách OS hoặc các cơ chế cô lập khác không hoạt động.

**Sai:** “Chỉ cần ẩn package host là plugin không thể ảnh hưởng tài nguyên hệ thống.” Các API công khai do nền tảng cho phép và những đối tượng host chủ động cấp vẫn tạo ra bề mặt tác động cần mô hình hóa.

**Sai:** “System property chỉ hiển thị vì classloader có quan hệ cha–con.” Cả hai class dùng API nền tảng `java.base`. Đây là một ví dụ của **trạng thái dùng chung trong một JVM**; parent delegation chỉ là cơ chế tìm/định nghĩa lớp, không phân chia bộ nhớ tiến trình thành vùng bảo mật.

## 6. Khi nào classloader và JPMS thực sự hữu ích?

Không nên nhầm “không phải sandbox” với “không có giá trị”. Hệ module/plugin tin cậy vẫn được lợi từ:

- **Class identity rõ ràng:** giúp nhiều phiên bản thư viện implementation cùng tồn tại có kiểm soát.
- **API boundary:** host và plugin chỉ dùng các giao diện được thiết kế, tránh truy cập vô tình vào package implementation.
- **Module readability và strong encapsulation:** kiểm soát các truy cập ở mức Java và một số hình thức reflection theo quy tắc JPMS.
- **Dịch vụ SPI có khai báo:** `uses`/`provides` và `ServiceLoader` giúp tìm implementation mà không phải hard-code mọi lớp.
- **Tách layer:** có thể nạp những module mới mà không đưa hết chúng vào boot layer.
- **Vòng đời và bảo trì:** nếu host quản lý toàn bộ callback, thread, cache và resource đúng cách, classloader/layer cũ có thể trở nên không còn tham chiếu và được thu gom.

Các điểm trên giúp giảm **lỗi tích hợp và phụ thuộc**, nhưng chúng không đặt quota CPU, cấp danh tính OS mới hoặc áp kiểm soát đọc/ghi file/network theo plugin. Nếu bài toán có plugin chưa tin cậy, phải thêm một **ranh giới cưỡng chế bảo mật** khác.

## 7. SecurityManager có giải quyết vấn đề không?

Trong các JDK cũ, Java có `SecurityManager` và mô hình quyền dựa trên policy/protection domain. Tuy nhiên, không nên thiết kế một hệ plugin mới dựa trên kỳ vọng rằng chỉ cần bật SecurityManager là có sandbox đáng tin cậy:

- `SecurityManager` được **deprecated for removal từ Java 17** (JEP 411) và sau đó cơ chế này bị vô hiệu hóa vĩnh viễn trong JDK 24 (JEP 486).
- Classloader và JPMS **không tự động thay thế** một bộ kiểm tra quyền cho những hoạt động hệ thống.
- Thiết kế cần hoạt động với JDK hiện đại nên dùng cơ chế cách ly được hỗ trợ và cưỡng chế ở bên ngoài tiến trình plugin hoặc mô hình capability/host API phù hợp, chứ không trông chờ vào một cơ chế legacy đã bị rút bỏ.

Không dùng `System.setSecurityManager` để minh họa bảo vệ plugin mới, bởi kết quả phụ thuộc phiên bản JDK và khả năng hỗ trợ đã thay đổi. Đặc biệt, **không** xem một custom classloader là SecurityManager chỉ vì nó được lập trình để lọc một số tên class.

## 8. Nếu plugin không đáng tin: kiến trúc nào phù hợp?

### 8.1. Tách tiến trình và trao đổi qua giao thức

Với mã plugin từ nguồn không tin cậy hoặc người dùng ngoài, một cách tiếp cận thường phù hợp hơn là chạy plugin trong **tiến trình riêng**:

```text
Host process (API / credentials quan trọng)
      |
      | Giao thức có schema, validation và timeout
      | (IPC / stdin-stdout / local socket / RPC)
      v
Plugin worker process
      |
      +-- OS identity/quyền hạn riêng
      +-- Chỉ mount hoặc cấp filesystem cần thiết
      +-- Giới hạn network egress/ingress
      +-- Giới hạn CPU, RAM, số tiến trình, thời gian
      +-- Log, giám sát, quota và chính sách restart
```

Ranh giới tiến trình giúp host có cơ hội **cưỡng chế** quyền thông qua hệ điều hành hoặc container sandbox. Hiệu quả bảo vệ phụ thuộc cấu hình thực tế: chỉ tạo process mới nhưng chạy cùng quyền OS, cùng filesystem và không có quota thì mức cách ly vẫn hạn chế.

Bên host cần coi tất cả đầu vào từ worker là **không tin cậy**: parse dữ liệu theo schema, kiểm tra kích thước, xác thực danh tính/nguồn, đặt timeout, chống lặp và không đưa capability quá rộng qua giao thức. Nếu host gửi cho plugin một “lệnh quản trị tùy ý”, tách process cũng không cứu được thiết kế quyền kém.

### 8.2. Giới hạn quyền theo nguyên tắc least privilege

Những lớp kiểm soát có thể phối hợp:

| Tầng | Biện pháp | Mục đích |
|---|---|---|
| **OS/container** | User/service account riêng, ACL, filesystem permissions, read-only mount, network policy | Cưỡng chế tài nguyên plugin được phép sử dụng |
| **Tài nguyên** | CPU/memory/pid limits, timeout, giám sát/kill process vi phạm chính sách | Hạn chế ảnh hưởng tới host và plugin khác |
| **Giao tiếp** | IPC/RPC với schema, kích thước tối đa, authentication/authorization | Giới hạn công việc mà host thực hiện thay plugin |
| **API** | Capability object nhỏ, scope/tenant phù hợp, input validation | Không trao object quản trị/secret vô hạn quyền |
| **Chuỗi cung ứng** | Ký phát hành, hash, dependency scanning, allowlist nguồn tin cậy | Giảm khả năng đưa plugin lạ hoặc đã bị thay đổi vào hệ thống |
| **Vận hành** | Audit, log, giám sát, cách ly khi lỗi, rollback | Phát hiện và phục hồi sau sự cố |

**Quan trọng:** code signing hoặc kiểm tra hash giúp xác minh **nguồn gốc/tính toàn vẹn**, không tự làm mã đã ký trở nên an toàn. Quét dependency và review là lớp giảm thiểu rủi ro, không thể thay chính sách quyền ở runtime.

### 8.3. Plugin tin cậy và plugin chưa tin cậy cần hai đường khác nhau

**Plugin do cùng tổ chức xây dựng, được review và triển khai có kiểm soát:** dùng classloader/JPMS trong cùng JVM có thể phù hợp vì lợi ích hiệu năng, SPI, tái sử dụng đối tượng và giảm chi phí IPC. Tuy vậy, cần quản lý vòng đời, lỗi, giới hạn resource và theo dõi sự cố.

**Plugin từ bên thứ ba hoặc do người dùng tải lên mà không thể tin cậy:** mặc định coi là **untrusted code execution**; ưu tiên tách process và áp cấu hình OS/container nghiêm ngặt. Không nhập plugin vào JVM có quyền cao rồi dựa vào `ModuleLayer` hoặc child-first classloader để chống mã độc.

**Mã script “sandboxed” qua một Java ScriptEngine** cũng không tự an toàn chỉ vì chạy qua `javax.script`. Một số engine có tùy chọn hạn chế interop/quyền, nhưng cần đánh giá và kiểm thử trên chính engine đó; nếu yêu cầu cách ly mạnh, nên dùng biện pháp cưỡng chế ngoài JVM.

## 9. Các lỗi thiết kế thường gặp

| Ngộ nhận | Vì sao sai | Hướng thay thế |
|---|---|---|
| “Mỗi plugin một `URLClassLoader` là an toàn” | Loader tách định danh và đường nạp, không cấp quyền OS riêng | Dùng loader cho dependency isolation; process sandbox cho mã chưa tin |
| “Module không export implementation nên không thể gây hại” | Encapsulation chặn truy cập Java tới package, không chặn API công khai của runtime | Threat model theo capability và tài nguyên mà plugin có thể sử dụng |
| “`ModuleLayer` tương đương container” | Vẫn một JVM, nhiều trạng thái/tài nguyên dùng chung | Process/container được giới hạn thực sự |
| “Kiểm tra `module-info.java` chứng minh plugin đáng tin” | Descriptor mô tả module, không đánh giá mục đích mã | Xác thực nguồn, review và runtime enforcement |
| “Đã `provides` SPI thì ServiceLoader tự an toàn” | SPI chỉ tìm/tạo provider theo contract; constructor/static init có thể thực thi mã | Chỉ kích hoạt plugin từ nguồn tin cậy hoặc trong worker cô lập |
| “Bytecode verifier chặn logic có hại” | Verifier kiểm tra tính hợp lệ, không kiểm tra mục tiêu nghiệp vụ | Defense-in-depth và phân quyền |
| “Cấm reflection là đủ” | Các API hợp lệ khác vẫn có quyền nếu process có quyền; mã không cần reflection để gây ảnh hưởng | Giới hạn capability và quyền hệ điều hành |
| “`URLClassLoader.close()` sẽ dừng plugin hoàn toàn” | Thread, listener và cache có thể giữ lớp/loader cũ | Dừng callback/executor/resource rồi gỡ tham chiếu; theo dõi leak |
| “Một process riêng là tuyệt đối an toàn” | Process vẫn có quyền OS và giao thức IPC có thể cấp quyền quá rộng | Kết hợp OS identity, filesystem/network policy, quotas và host validation |

### 9.1. Tin cậy và “được phép dùng chung dữ liệu” là hai chuyện khác

Có thể host cố ý chia sẻ một object `PluginContext` chứa cấu hình để plugin sử dụng. Điều đó **không sai** nếu plugin là nguồn tin cậy và object chỉ có API cần thiết. Rủi ro xuất hiện khi host coi mọi script/JAR có cùng `PluginContext` là đáng tin, hoặc truyền nhầm đối tượng chứa nhiều quyền quản trị hơn yêu cầu.

Trong cùng tiến trình, một object reference có thể là một capability mạnh. Thiết kế SPI tốt nên định nghĩa rõ **phương thức được phép gọi, phạm vi tenant, lifecycle, giới hạn dữ liệu**, đồng thời chủ động hạn chế những object có thể lọt vào plugin.

### 9.2. Sự cố vẫn lan truyền dù plugin không “tấn công”

Ngay cả plugin thiện chí cũng có thể vô tình giữ thread chạy mãi, đăng ký callback mà quên unregister, dùng quá nhiều heap, gây deadlock hoặc làm tràn log. Classloader/ModuleLayer không tự ngăn các lỗi này ảnh hưởng host. Vì vậy, **isolation là bài toán độ tin cậy và an toàn vận hành, không chỉ vấn đề mã độc**.

## 10. Checklist khi đánh giá ranh giới plugin

1. **Nguồn plugin:** Có ai được đưa JAR/script vào hệ thống? Có xác minh danh tính, tính toàn vẹn và quy trình phê duyệt không?
2. **Mức độ tin cậy:** Plugin nội bộ đã được review hay mã bất kỳ do người dùng cung cấp?
3. **Quyền chạy:** Plugin có chạy trong cùng process và cùng OS identity với host không? Có sandbox thực tế không?
4. **API chung:** Có đưa vào plugin token, connection, object quản trị, callback hoặc service có quyền quá rộng không?
5. **Classloader topology:** API/SPI được định nghĩa và chia sẻ đúng class identity chưa? Có tránh duplicate API gây lỗi ép kiểu không?
6. **Module graph:** `requires`, `exports`, `opens`, `uses`, `provides` có được cấu hình đúng để giảm bề mặt API không?
7. **Tài nguyên:** Có giới hạn thời gian, CPU, RAM, số thread, file handle, network và queue không?
8. **Vòng đời:** Có hủy listener, timer, executor, thread-local, service registry và đóng tài nguyên khi unload không?
9. **Đầu vào/đầu ra:** IPC có schema/validation, giới hạn kích thước và timeout? Có phân quyền cho từng operation?
10. **Quan sát:** Có metrics, log, audit, cảnh báo, thu hồi quyền và cách khôi phục khi plugin lỗi không?
11. **Kiểm thử:** Có thử dependency conflicts, callback in-flight, plugin không chịu dừng, malformed input và memory pressure không?
12. **Tuyên bố bảo mật:** Tài liệu có phân biệt rõ “module encapsulation” với “sandbox quyền runtime” để tránh hiểu nhầm không?

Nếu câu trả lời chỉ là “plugin có loader riêng” hoặc “plugin là named module”, thì **chưa đủ cơ sở** để kết luận rằng mã chưa tin cậy đã được cách ly.

## 11. Câu hỏi tự kiểm tra

1. **Classloader khác nhau có tạo heap riêng không?** Không. Các lớp có identity khác nhưng vẫn trong một JVM và dùng bộ nhớ tiến trình JVM.
2. **Module không export package có chặn mọi hoạt động của mã bên trong không?** Không. Nó hạn chế quyền truy cập Java vào package theo quy tắc module, không tự giới hạn I/O hoặc CPU của mã trong module.
3. **Vì sao ví dụ ở mục 5 dùng system property?** Để chứng minh trạng thái chung bằng hành vi an toàn, không phải chỉ ra cách vượt access control.
4. **Một plugin trong ModuleLayer riêng có phải process riêng không?** Không, layer không tạo OS process.
5. **`SecurityManager` có nên là nền tảng của sandbox plugin Java hiện đại?** Không. Cơ chế legacy này đã bị loại khỏi hướng hỗ trợ của các JDK mới, không phải giải pháp thay thế process isolation.
6. **Ký JAR có ngăn mọi hành vi nguy hiểm của plugin không?** Không. Ký xác nhận nguồn/tính toàn vẹn nếu chuỗi xác minh được triển khai đúng; mã có nguồn tin cậy vẫn có thể chứa lỗi hoặc hành vi không mong muốn.
7. **Process riêng đã đủ an toàn chưa?** Chưa chắc. Phải cấu hình quyền OS, hạn chế tài nguyên và thiết kế IPC chặt chẽ.
8. **Vì sao không nên trao JDBC connection quản trị cho plugin chưa tin cậy?** Đó là một capability có quyền cao; classloader/JPMS không tự giảm quyền của object mà host đã trao.

**Bài tập:** (a) chạy chương trình mục 5 và đối chiếu cả hai plugin đọc `ACTIVE`; (b) bỏ `exports demo.moduleplugin` rồi quan sát giới hạn gọi public method từ unnamed host qua reflection; chỉ phân tích lỗi truy cập, không dùng tùy chọn bypass access control; (c) vẽ lại kiến trúc plugin của bạn theo hai phương án “cùng JVM cho plugin tin cậy” và “worker process giới hạn quyền cho plugin chưa tin cậy”, liệt kê đúng những gì được bảo vệ và chưa được bảo vệ.

## 12. Tài liệu tham khảo

- Java SE 17 — `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 — `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 — `ModuleLayer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 17 — `ModuleFinder` và `Configuration`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java Language Specification 17, Chapter 7 — Packages and Modules: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
- JEP 411 — Deprecate the Security Manager for Removal: https://openjdk.org/jeps/411
- JEP 486 — Permanently Disable the Security Manager: https://openjdk.org/jeps/486
