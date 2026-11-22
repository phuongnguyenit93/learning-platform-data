# Chẩn đoán class loader bằng jcmd: VM.classloaders, VM.classloader_stats và VM.class_hierarchy

Trong một JVM chạy lâu — đặc biệt ứng dụng có plugin, application server, Spring Boot, công cụ build, hot reload hay các `URLClassLoader` tùy chỉnh — câu hỏi “vì sao class không được tìm thấy?”, “class nào do loader nào nạp?” và “vì sao metaspace tăng sau mỗi lần redeploy?” không nên trả lời bằng suy đoán về classpath.

**`jcmd`** là công cụ đi kèm JDK (đặc biệt trong HotSpot/OpenJDK) để gửi *diagnostic commands* tới **một tiến trình JVM đang chạy**. Ba lệnh liên quan class loading thường được dùng cùng nhau, nhưng cung cấp **ba góc nhìn khác nhau**:

1. **`VM.classloaders`:** in **cây quan hệ class loader (parent hierarchy)**; tùy chọn có thể liệt kê class thuộc mỗi loader.
2. **`VM.classloader_stats`:** in **thống kê theo class loader**: số class, thông tin `ClassLoaderData` và dung lượng metadata/metaspace chunks/blocks.
3. **`VM.class_hierarchy`:** in **cây kế thừa class** (superclass/subclass), có định danh `ClassLoaderData*` của loader liên quan; **không phải** cây parent của class loader.

Bài thuộc nhóm **Chẩn đoán** trong Java core – classloader. Nội dung tập trung vào cú pháp Java 17+, ví dụ chạy được để tạo class loader có tên, cách đọc output, cách phối hợp ba lệnh chẩn đoán lỗi nạp class và rò rỉ class loader, giới hạn của snapshot và lưu ý an toàn khi attach JVM production.

## 1. Bảng chọn lệnh đúng câu hỏi

| Bạn muốn biết | Lệnh phù hợp | Nhìn thấy gì? | Không kết luận được trực tiếp |
| --- | --- | --- | --- |
| JVM đang có những **loader** nào, parent là ai? | `VM.classloaders` | Bootstrap/platform/app và các custom loader trong cây | Object nào giữ loader sống, binary có tương thích không |
| Loader A đã nạp **class nào**? | `VM.classloaders show-classes=true` | Class names được hiển thị dưới loader trong cây | Class từ JAR nào trong mọi trường hợp, heap object size |
| Có bao nhiêu loader/class, metadata đang phân bổ ra sao? | `VM.classloader_stats` | `Classes`, `ChunkSz`, `BlockSz`, `CLD*` theo loader | Strong retaining path và thời điểm unload chắc chắn |
| `plugin.Child` kế thừa class nào? | `VM.class_hierarchy plugin.Child` | Superclass chain và loader-data identity | Loader parent chain |
| `plugin.Base` có các subclass đang nạp nào? | `VM.class_hierarchy -s plugin.Base` | Superclasses và subclasses của class được chỉ định | Mọi class trên classpath chưa nạp |
| Vì sao loader cũ không được GC thu hồi? | Thống kê + heap dump/retaining paths + TCCL | Dấu hiệu leak và đường giữ reference | Chỉ dùng một snapshot `jcmd` chưa đủ kết luận |
| Class nào thực sự đến từ JAR/CodeSource nào? | Class-loading log, `ProtectionDomain`/CodeSource, `javap` | Nguồn class theo loader/bytecode | Không dựa hoàn toàn vào ba lệnh thống kê trên |

**Mấu chốt:** `VM.classloaders` và `VM.class_hierarchy` có chữ “hierarchy” trong mô tả, nhưng **hierarchy của chúng là hai loại quan hệ khác nhau**.

## 2. Điều kiện để dùng được jcmd

Một phiên chạy điển hình:

```bash
jcmd -l
jcmd <PID> help
jcmd <PID> help VM.classloaders
jcmd <PID> help VM.classloader_stats
jcmd <PID> help VM.class_hierarchy
```

Trong các lệnh trên, **thay `<PID>` bằng số PID thực tế**, ví dụ `14920`; đừng gõ nguyên dấu ngoặc nhọn/góc vào PowerShell/CMD/Bash vì có thể bị shell hiểu thành redirection.

### Chọn PID và JDK phù hợp

- `jcmd -l` liệt kê những tiến trình Java mà cơ chế discovery có thể nhìn thấy; danh sách phụ thuộc quyền truy cập và namespace/container.
- Nếu bạn biết PID của service từ process manager, task manager, `ps` hoặc `ProcessHandle.current().pid()`, dùng trực tiếp `jcmd PID ...`.
- Ưu tiên `jcmd` của **cùng phiên bản/nhà cung cấp JDK** với target JVM, và môi trường hỗ trợ Attach API/diagnostic commands tương ứng.
- Tiến trình phải là JVM đang chạy, hỗ trợ attach; thường cần cùng user/đúng quyền OS. Trong Docker/Kubernetes còn phải xét PID namespace, container filesystem và security policy.
- JVM có thể khởi động với cấu hình **vô hiệu attach**, ví dụ `-XX:+DisableAttachMechanism` trên HotSpot; trong trường hợp đó `jcmd` không hoạt động theo cách thường.
- Đừng mặc định mọi JVM Java SE đều hỗ trợ chính xác ba lệnh này. Đây là **diagnostic commands của HotSpot/OpenJDK và một số runtime tương thích**; luôn hỏi target bằng `help`.

### Cú pháp chuẩn

```text
jcmd <PID> <diagnostic_command> [options] [arguments]
```

Ví dụ:

```bash
jcmd 14920 VM.classloaders
jcmd 14920 VM.classloader_stats
jcmd 14920 VM.class_hierarchy plugin.Greeter
```

`14920` chỉ là PID minh họa. Các lệnh **chỉ đọc/in thông tin** trong bài; tuy vậy diagnostic attach vẫn có chi phí JVM runtime. `VM.classloader_stats` được tài liệu đánh giá *Low impact*; hai lệnh in cây thường *Medium impact* tùy số loaders/classes. Trên JVM production lớn, tránh gọi tràn lan hoặc liệt kê mọi class không cần thiết.

## 3. Kiểm tra sự tồn tại và tùy chọn của từng lệnh

Chạy:

```bash
jcmd <PID> help VM.classloaders
```

Trên một JVM HotSpot đã thử nghiệm, help cho biết:

```text
VM.classloaders
Prints classloader hierarchy.

Options:
  show-classes : Print loaded classes. (BOOLEAN, false)
  verbose      : Print detailed information. (BOOLEAN, false)
  fold         : Show loaders of the same name and class as one.
                 (BOOLEAN, true)
```

Đoạn trên **lược bỏ phần header/impact và rút gọn mô tả**, không phải copy nguyên toàn bộ terminal output. Các tùy chọn sử dụng dạng `key` hoặc `key=value`:

```bash
jcmd <PID> VM.classloaders
jcmd <PID> VM.classloaders show-classes=true
jcmd <PID> VM.classloaders verbose=true
jcmd <PID> VM.classloaders fold=false
jcmd <PID> VM.classloaders show-classes=true fold=false
```

Đặc biệt **`fold=true` mặc định có thể gom các loader có cùng tên và cùng class** trong output. Khi điều tra **nhiều instance URLClassLoader cùng tên**, dùng `fold=false` để tránh vô tình đọc hình hiển thị gộp thành “chỉ một loader”.

Với statistics:

```bash
jcmd <PID> help VM.classloader_stats
```

Help xác nhận:

```text
VM.classloader_stats
Print statistics about all ClassLoaders.
Impact: Low
Syntax: VM.classloader_stats
```

Lệnh này **không có `show-classes` hay `fold`** trong cú pháp của bản JVM đã kiểm thử; không chuyển tùy chọn của `VM.classloaders` sang statistics.

Với class hierarchy:

```bash
jcmd <PID> help VM.class_hierarchy
```

Help chỉ ra:

```text
VM.class_hierarchy [options] [<classname>]
  -i : Include inherited interfaces (BOOLEAN, false)
  -s : Show subclasses as well as superclasses when class
       name is supplied (BOOLEAN, false)
  classname : Fully qualified class name (optional)
```

Đoạn này cũng là **tóm lược help**, giữ đúng ý nghĩa flags. Cách sử dụng:

```bash
jcmd <PID> VM.class_hierarchy
jcmd <PID> VM.class_hierarchy plugin.Greeter
jcmd <PID> VM.class_hierarchy -s plugin.Greeter
jcmd <PID> VM.class_hierarchy -i plugin.Greeter
```

Nếu không chỉ định tên class, lệnh có thể in **toàn bộ hierarchy các class đã nạp**, rất nhiều dòng. Dùng tên class khi có thể.

**Chú ý vị trí:** `-s` và `-i` là **options của `VM.class_hierarchy`**, không phải flags của executable `jcmd` đặt trước PID.

## 4. VM.classloaders — cây quan hệ loader parent

Lệnh:

```bash
jcmd <PID> VM.classloaders
```

Một JVM có custom loader do chương trình đặt tên `plugin-demo` có thể hiển thị:

```text
+-- <bootstrap>
      |
      +-- "platform", jdk.internal.loader.ClassLoaders$PlatformClassLoader
            |
            +-- "app", jdk.internal.loader.ClassLoaders$AppClassLoader
            |
            +-- "plugin-demo", java.net.URLClassLoader
```

Đây là **phần output thực nghiệm được giản lược khoảng trắng**, không hứa format giống hệt trên mọi JDK/OS.

Đọc sơ đồ:

- **Bootstrap loader** ở gốc; ở API `Class.getClassLoader()`, bootstrap có thể được thể hiện bằng `null`.
- **Platform loader** nạp các classes thuộc platform theo module/runtime configuration.
- **Application loader** thường phụ trách application classpath.
- **Plugin loader** là một instance `URLClassLoader` riêng, có thể chọn platform hoặc application loader làm parent.
- **Cây thể hiện quan hệ parent của loaders**, không phải class Java `extends` nhau. Ví dụ `URLClassLoader` *extends* `SecureClassLoader` trong hệ class inheritance, nhưng cây `VM.classloaders` không vẽ `SecureClassLoader` làm cha delegation chỉ vì quan hệ `extends`.

Trong ví dụ ở bài này, plugin loader được tạo với **parent = platform loader** nên `plugin-demo` nằm **cùng nhánh dưới platform** với app loader, **không phải con của app**. Đừng mặc định “plugin do app tạo ⇒ app là parent”. Quan hệ delegation là do **constructor/configuration** quyết định.

### Ba tùy chọn đặc biệt của VM.classloaders

**`show-classes=true`:** in class names gắn với mỗi loader. Hữu ích khi nghi `PluginLoader` nạp lại bản API được parent sở hữu, hoặc muốn xác định `plugin.Greeter` có thực sự do loader plugin define.

**`verbose=true`:** thêm chi tiết của loaders/output. Cần xem output trên JVM mục tiêu vì trường/cú pháp biểu diễn thay đổi giữa releases.

**`fold=false`:** không gom các loaders có cùng name và class. Rất quan trọng với plugin reload leak: nhiều instance URLClassLoader cùng tên có thể bị folded khi `fold=true`, khiến ảnh chụp hierarchy ít rõ ràng hơn số instances.

Ví dụ:

```bash
jcmd <PID> VM.classloaders show-classes=true fold=false
```

**Chi phí:** in toàn bộ class cho hàng nghìn loaders có thể tạo output rất lớn và mất thời gian. Trong production hãy bắt đầu bằng bản mặc định, chỉ bật `show-classes=true` khi đã có mục tiêu chẩn đoán.

### Điều VM.classloaders chưa cho biết

- Không hiển thị **GC roots/retaining paths** dẫn đến loader.
- Không chứng minh loader đã leak chỉ vì nó tồn tại trong một snapshot.
- Không nói class trên filesystem *có thể load* nhưng **chưa load**.
- Không thay `javap` để xem method/field descriptors.
- Không thay `ModuleLayer`/JPMS graph để kết luận exports/opens/readability.

## 5. VM.classloader_stats — số class và các số liệu metadata

Lệnh:

```bash
jcmd <PID> VM.classloader_stats
```

Một snapshot rút gọn từ JVM thử nghiệm:

```text
ClassLoader   Parent       CLD*         Classes ChunkSz BlockSz Type
0x...         0x...        0x...             1    5120    1336  java.net.URLClassLoader
0x...         0x...        0x...             1    6144    3440  jdk.internal.loader.ClassLoaders$AppClassLoader
0x...         0x...        0x...           899 4456448  367896  <boot class loader>
...
Total = 4                                   907 4486144  383144
```

**Đây là output đã rút gọn**, địa chỉ và số liệu chỉ mang tính ví dụ từ một JVM thử nghiệm. Không được so các số này như định mức cho mọi JVM Java 17; số classes/core modules thay đổi theo JVM/build và code đang chạy.

Các cột:

| Cột | Ý nghĩa thực dụng | Cần thận trọng |
| --- | --- | --- |
| `ClassLoader` | Địa chỉ/định danh biểu diễn loader trong VM snapshot, có thể `0x0` cho bootstrap | Không phải Java identity hash code hay PID |
| `Parent` | Thông tin parent pointer của classloader object | Giá trị dạng pointer, không là binary name của class parent |
| `CLD*` | Internal pointer tới cấu trúc **ClassLoaderData** của HotSpot | Chỉ định danh nội bộ trong runtime; không phải API Java ổn định |
| `Classes` | Số class thuộc loader/loader-data entry tương ứng trong thống kê | Không phải số object instances tạo từ class đó |
| `ChunkSz` | Tổng kích thước các metaspace chunks được cấp phát trong nhóm thống kê | Không phải heap memory, không phải “bộ nhớ sống chỉ cho class” |
| `BlockSz` | Tổng kích thước metaspace blocks được cấp phát trong các chunks | Không đồng nhất với RSS hay mức dùng Java heap |
| `Type` | Class của loader (hoặc bootstrap/hidden classes notation) | Nhiều instance có cùng `Type` nhưng tuổi đời khác |

Có thể có dòng **`+ hidden classes`** gắn vào bộ đếm của một loader/data entry. Hidden classes được JVM dùng cho một số implementation như lambda/invokedynamic; đừng mặc định chúng là “lớp bị giấu do ứng dụng độc hại” hay nhất định là leak.

### Chú ý kích thước và phép cộng

`ChunkSz` và `BlockSz` trong output HotSpot đang quan sát là các con số kích thước **theo bytes** trong bản xây dựng thử nghiệm; `jcmd` help chính thức mô tả dạng thống kê, không bắt buộc mọi JVM/phiên bản hiển thị cột giống hệt. Cần đối chiếu chú thích ngay dưới `Total` trong output bản runtime đang dùng.

Không suy ra:

- “`ChunkSz` = live Java heap của plugin.”
- “`BlockSz` = dung lượng JAR trên đĩa.”
- “`ChunkSz - BlockSz` = classloader leak chắc chắn.”
- “Một loader có 100 class nghĩa 100 object instance.”
- “Sau close loader, `Classes` của loader phải về 0.”

Một URL loader có thể được **đóng** nhưng object/class của nó vẫn được giữ mạnh bởi host, nên `VM.classloader_stats` vẫn hiển thị loader với class count và metadata.

### Khi nào statistics đặc biệt hữu ích?

- So **số instance custom loaders** và **số class mỗi loader** trước/sau nhiều lần reload plugin.
- Phát hiện xu hướng: sau mỗi redeploy có thêm một `java.net.URLClassLoader` với nhiều classes, và các loader cũ không biến mất sau GC phù hợp.
- Xác nhận bản ứng dụng vô tình tạo hàng trăm loaders gần như giống nhau.
- Ước lượng áp lực metadata theo loader (không thay `VM.metaspace`/Native Memory Tracking khi cần số liệu metaspace chi tiết).
- Correlate `CLD*` với class names từ `VM.class_hierarchy` trên cùng target JVM, cùng thời điểm tương đối.

**Một snapshot chưa đủ chứng minh leak.** JVM có thể vừa tạo loader hợp lệ, GC chưa diễn ra, hoặc container chủ ý giữ nhiều phiên bản song song. Cần so thời gian và tìm đường giữ strong reference.

## 6. VM.class_hierarchy — cây kế thừa của Java classes

Lệnh:

```bash
jcmd <PID> VM.class_hierarchy plugin.Greeter
```

Ví dụ trên target đã nạp `plugin.Greeter`:

```text
java.lang.Object/null
|--plugin.Greeter/0x0000...
```

`plugin.Greeter` là subclass của `java.lang.Object`. Phần `0x0000...` là **ClassLoaderData pointer** của defining loader, khác định danh Java object/loader name. `null` sau `java.lang.Object` ở ví dụ có nghĩa class được bootstrap loader định nghĩa.

### Đừng đọc nhầm thành cây classloader

Cây này là:

```text
java.lang.Object
   |
   +-- plugin.Greeter
```

không phải:

```text
Bootstrap loader
   |
   +-- Plugin URLClassLoader
```

Mối quan hệ **extends/implements giữa classes** và **parent delegation giữa loaders** là hoàn toàn khác nhau.

Một class `plugin.Greeter` có thể extends `plugin.Base`; hai class ấy có thể được define bởi các loader khác nhau tùy mô hình. `VM.class_hierarchy` tập trung vào class inheritance và in thêm loader-data identity để hỗ trợ phân biệt runtime definitions.

### Dùng -s và -i

```bash
jcmd <PID> VM.class_hierarchy plugin.Greeter
jcmd <PID> VM.class_hierarchy -s plugin.Greeter
jcmd <PID> VM.class_hierarchy -i plugin.Greeter
```

- Không `-s`: khi lọc theo tên class, chỉ in superclasses theo help của VM.
- Có `-s`: bổ sung các subclasses đã nạp của class được chọn.
- Có `-i`: in thêm inherited interfaces phù hợp theo implementation.
- Không truyền tên: có thể in **toàn bộ loaded class hierarchy**, rất lớn.

**Không thể dùng lệnh này để xem source code, bytecode, method implementations hoặc mọi class có trên classpath chưa được load.** Với lỗi `NoSuchMethodError`, cần `javap` để đối chiếu binary descriptors; `VM.class_hierarchy` chỉ giúp nhận diện hierarchy/loader-data liên quan.

### Khi có cùng binary name trong hai loaders

Hai loaders độc lập có thể tự define hai class đều tên `plugin.Greeter`. Với JVM, đó là **hai runtime types khác nhau** (binary name + defining loader). `VM.class_hierarchy` có thể biểu diễn chúng dưới cùng tên chữ nhưng với **loader-data identity khác nhau**; nên phối hợp `VM.classloader_stats` hoặc `VM.classloaders show-classes=true fold=false`.

Không kết luận chỉ từ tên chữ rằng đó là cùng một `Class<?>`. Cần xác định **defining loader**.

## 7. Ví dụ Java 17+: tạo URLClassLoader có tên rồi dùng cả ba lệnh

Đây là một ví dụ **đã biên dịch với `javac --release 17` và chạy** trên JVM HotSpot. Nó tạo một `URLClassLoader` có name `plugin-demo`, tự nạp class plugin và giữ chương trình sống trong một khoảng để `jcmd` attach. Bạn có thể chạy lại trên JDK 17+ có `jcmd`.

### 7.1 Cấu trúc

```text
jcmd-loader-demo/
├── src/
│   └── plugin/
│       └── Greeter.java
├── App.java
├── plugin/           (output .class của plugin)
└── host/             (output .class của host)
```

Tạo thư mục output `plugin` và `host`. **Không đưa `plugin` vào `-cp` của host**, để class plugin thật sự do URL loader riêng define.

### 7.2 Class của plugin

File `src/plugin/Greeter.java`:

```java
package plugin;

public class Greeter {
    public String say() {
        return "Hello from plugin";
    }
}
```

### 7.3 Host tạo named URLClassLoader

File `App.java`:

```java
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class App {
    public static void main(String[] args) throws Exception {
        URLClassLoader loader = new URLClassLoader(
                "plugin-demo",
                new java.net.URL[] {
                    Path.of("plugin").toUri().toURL()
                },
                ClassLoader.getPlatformClassLoader());

        Class<?> clazz = loader.loadClass("plugin.Greeter");
        Object object = clazz.getConstructor().newInstance();

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("loader=" + clazz.getClassLoader().getName());
        System.out.println("msg=" + clazz.getMethod("say").invoke(object));

        Thread.sleep(30_000);
        loader.close();
    }
}
```

Giải thích:

- Constructor `URLClassLoader(String name, URL[] urls, ClassLoader parent)` có trên Java 17 và cho phép đặt tên để dễ quan sát.
- Parent được chọn là `ClassLoader.getPlatformClassLoader()`, nên `plugin-demo` nằm dưới platform trong cây delegation; nó không phải child của app loader.
- `clazz.getClassLoader().getName()` trả `plugin-demo` để xác nhận đúng loader.
- `ProcessHandle.current().pid()` in PID thực tế của tiến trình target, tránh đoán.
- `Thread.sleep(30_000)` giữ chương trình sống khoảng **30 giây**, vừa đủ cho thao tác thủ công trong ví dụ. Đây chỉ là khoảng giữ tiến trình minh họa, không phải quy trình chẩn đoán server dài hạn.
- `loader.close()` sau sleep chỉ đóng URL loader; không ép unload classes. Class/object references vẫn còn trong method tại thời điểm chạy ví dụ.

### 7.4 Biên dịch và chạy

Tại thư mục `jcmd-loader-demo`:

```bash
javac --release 17 -d plugin src/plugin/Greeter.java
javac --release 17 -d host App.java
java -cp host App
```

Stdout đã quan sát:

```text
PID=<PID thật của tiến trình>
loader=plugin-demo
msg=Hello from plugin
```

**Không dùng nguyên `<PID thật của tiến trình>` như stdout cố định**: dòng đầu luôn là PID OS/runtime hiện tại, ví dụ trên máy thử nghiệm là một số cụ thể nhưng sẽ khác trên máy người học.

Để gọi `jcmd` khi target còn sống, **mở terminal thứ hai** trong khi terminal đầu đang sleep. Với ứng dụng chạy lâu thật, bạn không cần viết `Thread.sleep`.

### 7.5 Ba lệnh trên target

Ở terminal thứ hai:

```bash
jcmd -l
jcmd <PID> help VM.classloaders
jcmd <PID> VM.classloaders show-classes=false
jcmd <PID> VM.classloader_stats
jcmd <PID> VM.class_hierarchy -s plugin.Greeter
```

**Đã kiểm chứng trên JVM thử nghiệm:**

- `VM.classloaders` chứa `"plugin-demo", java.net.URLClassLoader` dưới platform loader.
- `VM.classloader_stats` có một dòng loader type `java.net.URLClassLoader` với ít nhất class plugin được tính, kèm `CLD*`, `ChunkSz` và `BlockSz`.
- `VM.class_hierarchy -s plugin.Greeter` in `java.lang.Object/null` và `plugin.Greeter/<loader-data-pointer>`.

Vì pointer, class count, heap/metaspace allocations và bootstrap class count đều phụ thuộc JVM, đây là **các đặc điểm được kiểm chứng**, không phải khẳng định các số cụ thể cố định trong mọi lần chạy.

### 7.6 Ba lệnh trả lời ba câu hỏi khác nhau

Cùng một plugin class:

- “`plugin-demo` có parent loader nào?” → `VM.classloaders`.
- “`plugin-demo` đã định nghĩa bao nhiêu class, metadata chunks thế nào?” → `VM.classloader_stats`.
- “`plugin.Greeter` extends class nào, và class loader data nào gắn với định nghĩa này?” → `VM.class_hierarchy`.

Nếu mới chỉ dùng một trong ba, bạn có thể đánh đồng loader **object**, loader **data**, class **hierarchy**, parent **delegation**, hoặc metaspace **allocation**.

## 8. Correlate CLD* giữa statistics và class hierarchy

Trong thử nghiệm, thống kê có dòng tương tự:

```text
... CLD*=0x0000020ffe529c10 ... Type=java.net.URLClassLoader
```

Cây class hierarchy có:

```text
|--plugin.Greeter/0x0000020ffe529c10
```

Đây là **minh họa từ một snapshot của JVM thử nghiệm**, cho thấy cả hai output cùng nhắc đến một `ClassLoaderData*`. Không copy pointer này sang tiến trình khác hoặc JVM restart: đây là địa chỉ/ID VM-internal, không phải persistent identifier.

Một cách đọc an toàn:

1. Dùng `VM.classloaders fold=false` để xác định custom loader theo tên và parent.
2. Dùng `VM.classloader_stats` để tìm những loader type liên quan và `CLD*`; lưu snapshot theo thời điểm.
3. Dùng `VM.class_hierarchy plugin.Greeter` để thấy class thực sự đã nạp và CLD pointer của nó.
4. Nếu pointer khớp trong cùng JVM, bạn có thêm dữ kiện liên hệ loader-data và class.
5. Không suy ra *CodeSource/JAR file path*, version hoặc GC retaining path chỉ từ pointer ấy.

**Một điểm tinh tế:** `ClassLoaderData` là cấu trúc nội bộ của HotSpot, không phải `java.lang.ClassLoader` hay `java.lang.Module` public API. Mối liên hệ của nó hữu ích để debug, nhưng output/địa chỉ/format có thể khác trong release khác.

## 9. Dùng thống kê jcmd để khoanh vùng loader nghi bị giữ

Với plugin reload, thu `VM.classloaders fold=false` và `VM.classloader_stats` **trước/sau mỗi thế hệ triển khai** trong cùng JVM. Dùng `fold=false` để nhìn rõ nhiều loader cùng tên/class; đọc `Classes`, `CLD*`, `ChunkSz` và `BlockSz` như các số liệu loader metadata, không phải object heap bytes.

Nếu loader cũ vẫn xuất hiện sau `close()`, có thể còn công việc hợp lệ hoặc strong references từ TCCL, task, cache, listener hay provider; JVM cũng không bắt buộc unload ngay. So xu hướng qua nhiều chu kỳ và GC thích hợp. Để tìm **ai đang giữ loader**, cần heap dump/MAT Path to GC Roots hoặc bằng chứng tương đương, không suy từ một snapshot jcmd. Bài JFR/heap dump hướng dẫn điều tra root path, phân biệt thời điểm quan sát và tính hợp lệ của lifecycle.
## 10. Vì sao close loader không làm nó biến mất khỏi thống kê?

`URLClassLoader.close()` chỉ đóng nguồn classpath/JAR handles theo hợp đồng. Nó **không**:

- Đóng mọi thread/executor do plugin tạo.
- Xóa mọi callback/provider/cache host đang giữ.
- Hủy instances hoặc xóa `Class<?>` đã nạp.
- Buộc GC thu hồi loader.
- Buộc JVM unload class metadata.

Một loader đã closed **vẫn có thể xuất hiện** trong `VM.classloaders`/`VM.classloader_stats` nếu nó còn reachable/loader data còn tồn tại. Đây không phải bằng chứng close thất bại.

Quy trình plugin stop tốt hơn:

```text
Reject new requests
       |
       v
Await/cancel in-flight plugin tasks
       |
       v
Call plugin.stop() and unregister callbacks/services
       |
       v
Restore TCCL / clear ThreadLocal / close plugin-owned resources
       |
       v
Call URLClassLoader.close()
       |
       v
Release host strong references to old instance/Class/loader
       |
       v
Loader may become eligible for GC
       |
       v
JVM may unload its classes (no guaranteed deadline)
```

**Điểm liên quan chẩn đoán:** chụp statistics ngay sau `close()` mà không kiểm tra tasks/strong references rồi kết luận “classloader leak” là một kết luận vội. Class unloading có điều kiện reachability và phụ thuộc quyết định GC.

## 11. Phân biệt loaded classes với observable classes trên đường tìm

`VM.classloaders show-classes=true` và `VM.class_hierarchy` tập trung vào **các class đã được JVM nạp**. Một JAR có hàng nghìn `.class` nhưng ứng dụng chỉ chạm tới mười class, thống kê không tự liệt kê toàn bộ mọi file class có trong JAR.

Phân biệt:

| Khái niệm | Ví dụ |
| --- | --- |
| **File có trên đĩa** | `plugin.jar!/plugin/Unused.class` tồn tại |
| **Loader có thể tìm** | `URLClassLoader` biết URL trỏ tới plugin JAR |
| **Class đã load/define** | JVM đã có runtime `Class<?>` cho `plugin.Used` |
| **Class đã initialize** | JVM đã chạy `<clinit>` theo quy tắc initialization |
| **Class đủ điều kiện unload** | Defining loader có thể được GC thu hồi |
| **Class đã unload** | JVM thực sự thực hiện unloading, có thể thấy qua logs/events |

Không dùng `VM.class_hierarchy` như một câu lệnh “liệt kê toàn bộ classes có thể load từ classpath”. Và cũng không suy rằng class vắng mặt trong snapshot nghĩa là file bị thiếu: có thể chỉ chưa được nạp.

Muốn điều tra class-path/JAR contents, phối hợp `jar --list`, classloading logs, runtime resource lookup hoặc `javap`.

## 12. Khi nào dùng -Xlog thay vì jcmd?

`jcmd` cho **snapshot lúc yêu cầu**, còn unified JVM logging có thể ghi **chuỗi sự kiện theo thời gian**. Với HotSpot:

```bash
java -Xlog:class+load=info,class+unload=info -cp host App
```

Lệnh này cho phép quan sát class load và unload events xảy ra theo thời gian nếu runtime có hỗ trợ. Lưu ý:

- `class+load`: sự kiện class được load, không phải danh sách tất cả file JAR.
- `class+unload`: sự kiện unloading; chỉ xuất hiện **khi thực sự xảy ra**.
- Không thấy log unload **không chứng minh** `URLClassLoader.close()` thất bại hoặc VM bị leak.
- Runtime có thể giữ classloader mạnh bởi callback/TCCL hoặc chưa có GC/unloading.
- Logging chi tiết có thể sinh output lớn; chọn đúng mức log và lưu file theo chính sách production.

Trong môi trường production, nên chọn hợp lý:

- `jcmd` snapshot ít lần để biết trạng thái hiện tại.
- `-Xlog:class+load/class+unload` hoặc JFR khi cần timeline.
- Heap dump/retaining path khi cần xác định leak.
- `VM.metaspace` hoặc NMT khi cần đi sâu vào native/metaspace allocations.

Các công cụ bổ trợ không làm mất vai trò của ba lệnh chính; chúng trả lời **những câu hỏi mà snapshot tree/stats không thể trả lời**.

## 13. Khi jcmd không chạy hoặc báo lỗi attach

Một vài tình huống:

| Dấu hiệu | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| `jcmd -l` không thấy tiến trình | Khác user/PID namespace/container, process không hỗ trợ discovery | Kiểm tra OS PID và chạy jcmd cùng namespace/quyền |
| `Could not attach` hoặc timeout | Attach mechanism tắt, quyền thiếu, JVM bận/không phản hồi, filesystem temp restrictions | Kiểm tra runtime flags, user, container và logs |
| `Unknown diagnostic command` | JVM/version/vendor không hỗ trợ tên command | `jcmd PID help` |
| Command chạy nhưng output quá nhiều | Chọn `show-classes=true` hoặc hierarchy không filter | Bỏ liệt kê class, lọc theo class cụ thể |
| Không thấy plugin loader | Plugin chưa load, đã GC, bị fold, hoặc parent đã define class thay | `fold=false`, chạy đúng lúc, kiểm tra code/defining loader |
| `VM.classloader_stats` có nhiều rows giống type | Nhiều **loader instances** cùng class/type | So CLD/loader IDs và lifecycle; không đếm theo type name duy nhất |
| `VM.class_hierarchy plugin.Foo` không thấy class | Class chưa load, sai binary name, target JVM khác, đã unload | Xác nhận `getName()`/loader và class-loading logs |
| Output class hierarchy có `null` | Class do bootstrap loader định nghĩa | Không hiểu `null` là class không có superclass |
| Snapshot sau deploy có `ChunkSz` tăng | Nạp thêm classes/metaspace chunks | So nhiều mốc và GC, không kết luận leak ngay |
| Loader tồn tại sau `close()` | Còn references hoặc VM chưa unload | Phân tích TCCL/cache/tasks/retaining roots |

### Lưu ý bảo mật và vận hành

`jcmd` là công cụ quản trị tương tác với tiến trình. Không cấp quyền attach cho user/automation không tin cậy. Một số diagnostic commands có khả năng làm thay đổi trạng thái VM hoặc tạo heap dump; **chỉ chạy những lệnh cần thiết và hiểu tác động**.

Với ba lệnh trong bài, dùng `help` trước rồi đọc output; không chạy “`jcmd PID` không command” hoặc script quét mọi tiến trình trong production nếu chưa được phép. Cũng không lưu log chứa thông tin classnames/plugin internals công khai.

## 14. Lỗi suy luận thường gặp

| Kết luận vội | Cách hiểu đúng |
| --- | --- |
| “`VM.class_hierarchy` là cây parent của loaders.” | Sai; đó là cây **class inheritance**. `VM.classloaders` mới là parent loader hierarchy. |
| “`VM.classloader_stats` hiển thị heap bytes của mỗi instance.” | Sai; thống kê theo loader/class metadata. |
| “`ChunkSz` cao chứng tỏ memory leak.” | Chưa đủ. Đây là allocation snapshot; cần xu hướng và retaining paths. |
| “Loader đã `close()` phải biến mất khỏi stats.” | Sai; close không ép GC/unload. |
| “Không thấy loader trong `VM.classloaders` tức không có class tương ứng.” | Có thể class do parent/bootstrap define, loader chưa tạo, bị fold hoặc đã GC. |
| “Class có trong JAR thì chắc có trong `VM.class_hierarchy`.” | Không; chỉ class đã loaded/defined mới xuất hiện. |
| “`fold=true` cho tôi số chính xác mọi loader instance.” | Có thể gộp loaders cùng tên/class; dùng `fold=false` khi đếm instances. |
| “CLD pointer là tên/id vĩnh viễn của loader.” | Không; địa chỉ VM-internal không ổn định qua JVM restart. |
| “ClassLoader name giống nhau nghĩa cùng loader.” | Không; nhiều objects có thể cùng `getName()`. |
| “`jcmd` có thể tự sửa classpath, recompile class cũ.” | Không; đây là diagnostics, không phải build/deployment repair tool. |
| “jcmd chỉ dùng được cho Java classpath, không dùng được JPMS.” | Không đúng; target JVM dùng named modules vẫn có loaders/classes để chẩn đoán. |
| “Class hierarchy và classloader hierarchy là một đồ thị.” | Sai; inheritance và delegation là hai quan hệ khác nhau. |

## 15. Câu hỏi tự kiểm tra có đáp án

**1.** Muốn xem plugin loader là child của platform hay application loader, dùng lệnh nào?

**Đáp án:** `jcmd PID VM.classloaders`; thêm `fold=false` khi cần phân biệt các instances cùng tên/type.

**2.** Muốn biết loader nào đang giữ nhiều class metadata, dùng lệnh nào?

**Đáp án:** `jcmd PID VM.classloader_stats`. Đọc `Classes`, `ChunkSz`, `BlockSz` và `Type`. Các con số không phải heap object sizes.

**3.** `VM.class_hierarchy plugin.Greeter` in `java.lang.Object` phía trên plugin class. Điều đó nói gì?

**Đáp án:** `plugin.Greeter` kế thừa `java.lang.Object` ở **class hierarchy**; không chứng minh plugin loader có parent là bootstrap loader.

**4.** `-s` trên `VM.class_hierarchy` có tác dụng gì?

**Đáp án:** Khi đã chọn classname, nó yêu cầu in thêm các **subclasses**, ngoài superclasses.

**5.** `-i` có ý nghĩa gì?

**Đáp án:** Yêu cầu hiển thị inherited interfaces theo capability của command.

**6.** Vì sao `VM.classloaders fold=false` hữu ích khi phát hiện leak?

**Đáp án:** Mặc định fold có thể gộp loaders cùng name/class trong hiển thị. Khi đếm nhiều instance loader sau redeploy, cần tách chúng.

**7.** Vì sao kết quả `VM.classloader_stats` sau close vẫn có `plugin-demo`?

**Đáp án:** Close chỉ đóng nguồn URL/JAR handles của URLClassLoader; loader/class metadata có thể còn sống qua references và VM chưa unload.

**8.** `CLD*` là gì?

**Đáp án:** Một pointer/identifier nội bộ của HotSpot `ClassLoaderData`; có thể correlate các lệnh cùng target JVM nhưng không phải public Java object ID bền vững.

**9.** Một class nằm trong plugin JAR nhưng không xuất hiện trong `VM.class_hierarchy`. Có thể là vì sao?

**Đáp án:** Class chưa được load, không phải JVM thiếu file; output command tập trung các loaded classes.

**10.** `VM.classloader_stats` tăng `Classes` qua ba lần deploy có chắc leak?

**Đáp án:** Chưa. Cần biết ứng dụng còn chạy nhiều versions hợp lệ không, GC/unload đã xảy ra chưa và có strong retaining paths nào giữ loaders cũ.

**11.** Để tìm chính xác **ai giữ old loader sống**, ba lệnh trên đủ không?

**Đáp án:** Không; cần heap dump/retaining path analysis và kiểm tra TCCL/ThreadLocal/callbacks/registries.

**12.** Khi JVM báo “unknown command”, bước đầu là gì?

**Đáp án:** `jcmd PID help` và `jcmd PID help VM.classloaders` để kiểm tra target runtime có hỗ trợ command/flags hay không.

**13.** Vì sao không so trực tiếp địa chỉ `0x...` từ hai JVM restart?

**Đáp án:** Đó là pointer/VM internal identity, không phải ID ổn định giữa tiến trình/lần khởi động.

**14.** Muốn xem class nào đến từ JAR nào, lệnh nào bổ trợ?

**Đáp án:** Class-loading logs (ví dụ `-Xlog:class+load=info`), CodeSource của `Class<?>` khi có, cùng `jar --list`/`javap`. `VM.classloader_stats` không phải file-origin resolver.

## 16. Checklist thao tác thực chiến

1. Xác nhận **JDK/HotSpot** của target và khả năng attach; dùng đúng `jcmd`.
2. Dùng `jcmd -l` hoặc lấy PID bằng công cụ OS; kiểm tra target process đúng.
3. Chạy `jcmd PID help` và `help VM.classloaders/VM.classloader_stats/VM.class_hierarchy`.
4. Chụp `VM.classloaders` để xem parent tree, không nhầm với class inheritance.
5. Bật `fold=false` nếu nghi nhiều instance loaders trùng tên/type.
6. Chỉ bật `show-classes=true` khi cần, chú ý chi phí output lớn.
7. Chụp `VM.classloader_stats` để xem `CLD*`, class counts và allocations metadata.
8. Dùng `VM.class_hierarchy ClassName` hoặc `-s`/`-i` theo câu hỏi về inheritance/interface.
9. Correlate `CLD*` giữa stats và hierarchy trong cùng process/snapshot, không lưu làm ID vĩnh viễn.
10. So snapshot **trước/sau** plugin load/reload/stop và sau GC phù hợp.
11. Không coi `URLClassLoader.close()` là lệnh class unloading.
12. Khi nghi leak, tìm root references bằng heap dump và kiểm tra TCCL, ThreadLocal, registries, active tasks.
13. Dùng class-loading/unloading logs hoặc JFR nếu cần timeline, `VM.metaspace` nếu cần phân tích memory sâu.
14. Kiểm tra CodeSource/JAR khi nghi trùng class/version thay vì suy từ tên class hoặc type của loader.
15. Giữ quyền attach, tác động runtime và dữ liệu diagnostics trong phạm vi bảo mật/vận hành được phép.

## Kết luận

**`VM.classloaders` cho biết loader nào làm parent của loader nào; `VM.classloader_stats` cho biết số class và thống kê metadata theo loader; `VM.class_hierarchy` cho biết cây kế thừa của những classes đã nạp, kèm loader-data identity.** Chúng bổ trợ nhau để chẩn đoán classloading và plugin leaks, nhưng không thay nhau và không thay được heap retaining paths.

Khi cần điều tra một JVM có nhiều plugin, hãy bắt đầu bằng **PID → `VM.classloaders fold=false` → `VM.classloader_stats` → `VM.class_hierarchy ClassName`**, sau đó dùng class-loading logs hoặc heap dump nếu câu hỏi là **class/JAR nào thực sự được nạp** hoặc **GC root nào đang giữ loader cũ**. Không kết luận “leak” chỉ từ một snapshot hay từ việc loader vẫn xuất hiện ngay sau `close()`.

**Tài liệu chính thức:**

- [Oracle Java SE 17 — `jcmd` man page](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.classloaders`, `VM.classloader_stats`, `VM.class_hierarchy`, options và impact.
- [Oracle Java SE 17 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/): quy trình dùng tools/JVM diagnostics.
- [`ClassLoader` API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, named loader.
- [`URLClassLoader` API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): constructors, `close()` và giới hạn.
- [JLS 17 `12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): khả năng GC thu hồi defining loader và class unloading.
