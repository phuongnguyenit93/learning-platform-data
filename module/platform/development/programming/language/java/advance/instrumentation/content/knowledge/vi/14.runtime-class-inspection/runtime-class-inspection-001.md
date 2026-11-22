# getAllLoadedClasses trả ảnh chụp các lớp đã được JVM nạp

**Chủ đề:** Java Advance → instrumentation → **Khảo sát khi chạy**.

`Instrumentation.getAllLoadedClasses()` là API cho Java agent **quan sát những lớp hiện đã được JVM nạp**. Một lần gọi trả về **một mảng `Class<?>[]`**, trong đó mỗi phần tử đại diện cho một kiểu runtime đang tồn tại tại thời điểm khảo sát. Mảng này giúp trả lời “JVM đang biết những lớp nào?”, chẳng hạn khi chẩn đoán plugin, class loader, bộ nhớ metaspace hoặc chọn ứng viên cho retransformation.

Hợp đồng quan trọng: đây là **ảnh chụp danh sách**, không phải luồng sự kiện liên tục, không phải danh sách tất cả lớp có thể tìm thấy trong JAR/classpath, không phải danh sách đối tượng `new` đã tạo, cũng không có nghĩa các lớp ấy đều đã **khởi tạo** (`initialized`). API trả **`Class<?>` objects**, không trả bytes của class file.

Trong JDK 17+, Javadoc nêu rõ mảng bao gồm **classes, interfaces, hidden classes/interfaces và array classes**. Cách lấy “các lớp mà một loader có thể tìm theo tên” lại là `getInitiatedClasses(loader)`, có tiêu chí khác.

> **Môi trường ví dụ:** JDK 17 trở lên có `javac`, `jar` và `java`. Bài sử dụng Java agent khởi động qua `-javaagent` để nhận `Instrumentation`, không cần attach vào tiến trình khác, không đăng ký transformer và không tự thay bytecode.

## 1. `getAllLoadedClasses()` nằm trong API nào?

Chữ ký của `java.lang.instrument.Instrumentation`:

```java
Class[] getAllLoadedClasses();
```

Trong mã Java hiện đại, nên giữ kết quả ở biến có generic wildcard để tránh thao tác raw type:

```java
Class<?>[] snapshot = instrumentation.getAllLoadedClasses();
```

Hai dòng trên là **fragment API**, không phải chương trình độc lập: `instrumentation` cần được JVM đưa tới agent qua `premain` hoặc `agentmain`. Không thể tự tạo một `Instrumentation` hợp lệ bằng `new Instrumentation()`; đó là interface do JVM cung cấp.

Giá trị trả về:

- **Một mảng mới cho mỗi lần khảo sát** chứa những `Class` objects đang thuộc tập loaded classes mà JVM báo tại thời điểm gọi.
- **Các classes và interfaces** đã load, kể cả hidden types và array types theo Javadoc JDK 17.
- **Mảng độ dài 0** theo hợp đồng nếu không có class nào được báo (trên JVM Java thực tế đang chạy chương trình, điều này hầu như không xảy ra).
- **Không có hợp đồng về thứ tự** để ứng dụng dựa vào: không diễn giải `snapshot[0]` là “class được nạp đầu tiên”, không kỳ vọng hai lần gọi sắp xếp giống nhau.

Một phần tử `Class<?>` có thể đưa ra:

| Câu hỏi | API đọc từ `Class<?>` |
| --- | --- |
| Tên kiểu runtime | `clazz.getName()` |
| Defining class loader | `clazz.getClassLoader()`; `null` thường chỉ bootstrap |
| Module | `clazz.getModule()` |
| Có phải interface? | `clazz.isInterface()` |
| Có phải array type? | `clazz.isArray()` |
| Component type nếu là array | `clazz.getComponentType()` |
| Có phải hidden class? | `clazz.isHidden()` (JDK 15+) |
| Có phải enum/record/annotation? | `isEnum()` / `isRecord()` / `isAnnotation()` |
| Có thể dùng redefinition/retransformation? | **Không suy từ class membership**; hỏi riêng `instrumentation.isModifiableClass(clazz)` |

**Lưu ý:** `clazz.getName()` có thể giống giữa hai `Class<?>` khác nhau do hai defining loaders khác nhau; key duy nhất ở runtime là **chính object `Class<?>`/identity và loader**, không chỉ chuỗi tên.

## 2. “Đã nạp” không đồng nghĩa “đã khởi tạo”

Một class có các giai đoạn liên quan tới JVM: **loading → linking (verification/preparation/resolution) → initialization**. JVM có thể đã load một class nhưng chưa chạy khối `static` hay khởi tạo static fields theo logic ứng dụng.

Ví dụ (chỉ là fragment minh họa):

```java
Class<?> clazz = Class.forName(
        "demo.LoadedLater",
        false,
        ClassLoader.getSystemClassLoader());
```

- Tham số thứ hai `false` yêu cầu **không khởi tạo** class tại lệnh này nếu nó chưa được khởi tạo.
- Lớp vẫn có thể được **load** và xuất hiện trong `getAllLoadedClasses()`.
- Khi dùng `Class.forName(name, true, loader)`, JVM sẽ khởi tạo class nếu chưa khởi tạo.
- Không nhầm việc thấy `Class<?>` trong snapshot với việc `static { ... }` đã chạy.

Một lần scan snapshot **không phải** một cơ chế để hỏi “class này đã initialized hay chưa” theo API `Class<?>` chuẩn. Dùng một bài lab có static initializer ghi dấu sẽ làm rõ sự khác biệt.

### 2.1. Không phải lớp nào cũng load chỉ vì có file `.class`

Giả sử JAR chứa các class `A`, `B` và `C`. Nếu JVM chưa thực sự load `C`, tệp `C.class` vẫn có thể nằm trên classpath nhưng **không xuất hiện trong snapshot**. Ngược lại, class được tạo động, hidden class hoặc array type có thể có mặt mà không có một tệp `.class` độc lập tương ứng trên disk theo cách công cụ build thường lưu.

Snapshot phản ánh **runtime state**, không phải nội dung thư mục, JAR hay module path.

## 3. “Ảnh chụp” có giới hạn thời gian và phạm vi

```text
T0: JVM đã load A, B
       │
       ▼
S1 = getAllLoadedClasses()   -> chứa A, B, ... những classes khác
       │
T1: chương trình load C
       │
       ▼
S2 = getAllLoadedClasses()   -> chứa A, B, C, ... tại thời điểm mới
       │
T2: loader của D có thể bị GC/unload (nếu đủ điều kiện)
       │
       ▼
S3 = getAllLoadedClasses()   -> tập kết quả có thể tiếp tục thay đổi
```

S1 **không tự cập nhật** khi C được load. Muốn biết tình trạng mới phải gọi API lần nữa. Hai lần gọi có thể khác nhau về:

- **Số lượng classes:** agent, JIT/runtime support, reflection, serialization, frameworks và chính code khảo sát có thể kích hoạt load thêm types.
- **Membership:** có lớp mới load; một số loader/types cũ có thể unload khi không còn reachable.
- **Thứ tự:** không được dùng vị trí mảng làm identity hay timeline nạp lớp.
- **Phân bố loader/module:** ứng dụng có thể tạo hoặc tháo plugin loaders.

Không có bảo đảm rằng **hai ảnh chụp tạo thành một transaction cố định của toàn bộ ứng dụng** khi nhiều threads đang load/unload cùng lúc. Một diff là bằng chứng quan sát **tại hai thời điểm**, không thể suy ra đầy đủ thứ tự mọi sự kiện đã xảy ra ở giữa.

**Quan trọng với memory:** Nếu agent giữ `Class<?>[]` lâu trong static field/cache, các `Class<?>` references có thể giữ cho lớp/defining loader không được thu hồi như kỳ vọng. Vì vậy một “bộ khảo sát” cũng có thể **gây class-loader retention** nếu lưu toàn bộ snapshots mãi mãi. Chỉ giữ số liệu/tóm tắt phù hợp hoặc bản chụp ngắn hạn; giải phóng references sau phân tích.

## 4. Dự án Java 17+ chạy được: quan sát một lớp trước/sau lúc load

Ta sẽ xây **Java agent chỉ đọc**. Khi chạy ứng dụng, nó:

1. Chụp danh sách loaded classes trước khi ứng dụng cố ý tải `demo.LoadedLater`.
2. Gọi `Class.forName(..., false, ...)` để **load nhưng chưa initialize**.
3. Chụp lại và kiểm tra class đã xuất hiện.
4. Gọi `Class.forName(..., true, ...)` để kích hoạt static initializer.
5. Xác nhận class identity không đổi do việc initialization.

### 4.1. Cấu trúc thư mục

```text
loaded-classes-lab/
├── agent.mf
├── src/
│   └── demo/
│       ├── CensusAgent.java
│       ├── LoadedLater.java
│       ├── SnapshotMain.java
│       └── LoaderIdentityMain.java
└── plugin-src/
    └── plug/
        └── SideBySide.java
```

Khi biên dịch sẽ tạo `out/` và `plugin-out/`. Không cần thư viện bên thứ ba, không cần tạo một workspace/repository riêng cho hiểu biết của bài này: đây là mô tả các file bạn có thể tạo tại máy học tập.

### 4.2. Agent — `src/demo/CensusAgent.java`

```java
package demo;

import java.lang.instrument.Instrumentation;

public final class CensusAgent {
    private static volatile Instrumentation instrumentation;

    private CensusAgent() {}

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
    }

    public static Class<?>[] snapshot() {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException(
                    "Run with -javaagent:census-agent.jar");
        }
        return inst.getAllLoadedClasses();
    }

    public static Class<?>[] initiatedBy(ClassLoader loader) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Agent not initialized");
        }
        return inst.getInitiatedClasses(loader);
    }
}
```

`premain` chạy **trước `main` của ứng dụng** khi khởi động bằng `-javaagent`. Biến `Instrumentation` được lưu ở static `volatile` để code ứng dụng đọc sau khi JVM đã gọi `premain`. Ở bài lab tuần tự, `volatile` không thiết yếu cho kết quả in, nhưng là thói quen công bố reference đúng khi nhiều threads có thể truy cập.

Ở đây **không gọi `addTransformer`, `redefineClasses` hay `retransformClasses`**: mục tiêu chỉ là quan sát. `getAllLoadedClasses` tự nó không gắn hook vào methods và không thay định nghĩa lớp.

### 4.3. Lớp được tải muộn — `src/demo/LoadedLater.java`

```java
package demo;

public final class LoadedLater {
    static {
        System.out.println("INIT=LoadedLater");
    }

    private LoadedLater() {}

    public static String message() {
        return "ready";
    }
}
```

Dòng `INIT=LoadedLater` chỉ in khi **class initializer được thực thi**. Việc chỉ tham chiếu tên lớp bằng **chuỗi literal** `"demo.LoadedLater"` không có nghĩa JVM buộc load class đó ngay từ đầu.

### 4.4. Chương trình chính — `src/demo/SnapshotMain.java`

```java
package demo;

import java.util.Arrays;

public final class SnapshotMain {
    private SnapshotMain() {}

    private static boolean contains(
            Class<?>[] snapshot, String name, ClassLoader loader) {
        for (Class<?> type : snapshot) {
            if (type.getName().equals(name)
                    && type.getClassLoader() == loader) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        ClassLoader applicationLoader =
                SnapshotMain.class.getClassLoader();
        String className = "demo.LoadedLater";

        Class<?>[] before = CensusAgent.snapshot();
        System.out.println("BEFORE_PRESENT="
                + contains(before, className, applicationLoader));

        Class<?> loaded = Class.forName(
                className, false, applicationLoader);

        Class<?>[] afterLoad = CensusAgent.snapshot();
        System.out.println("AFTER_PRESENT="
                + contains(afterLoad, className, applicationLoader));
        System.out.println("FOUND_SAME_CLASS="
                + Arrays.asList(afterLoad).contains(loaded));

        Class<?> initialized = Class.forName(
                className, true, applicationLoader);
        System.out.println("SAME_AFTER_INIT="
                + (loaded == initialized));
    }
}
```

**Vì sao lọc cả tên lẫn loader?** Trường hợp loader A và loader B cùng định nghĩa `demo.LoadedLater`, chỉ gọi `getName().equals(...)` có thể chọn nhầm class. Trong lab này loader là application loader, nên filter theo `getClassLoader() == applicationLoader` để xác định đúng runtime class.

`Arrays.asList(afterLoad).contains(loaded)` so theo `Class.equals` (về danh tính `Class`) để chứng minh phần tử trả về chính là object `Class<?>` do `Class.forName` trả. Không dựa vào vị trí mảng.

### 4.5. Manifest agent — `agent.mf`

Tạo tệp manifest văn bản, có **newline cuối**:

```text
Manifest-Version: 1.0
Premain-Class: demo.CensusAgent
```

Vì agent chỉ chụp danh sách, **không cần** các manifest attributes `Can-Retransform-Classes` hoặc `Can-Redefine-Classes`. Những capability đó phục vụ thay bytecode, không phải điều kiện bắt buộc cho `getAllLoadedClasses()`.

### 4.6. Biên dịch và chạy

Đứng tại thư mục `loaded-classes-lab`. Trên Linux/macOS tạo thư mục output:

```bash
mkdir -p out
javac --release 17 -d out src/demo/CensusAgent.java src/demo/LoadedLater.java src/demo/SnapshotMain.java
jar --create --file census-agent.jar --manifest agent.mf -C out demo/CensusAgent.class
java -javaagent:census-agent.jar -cp out demo.SnapshotMain
```

Trên Windows PowerShell, thay lệnh tạo thư mục bằng:

```powershell
New-Item -ItemType Directory -Force out
```

Các lệnh `javac`, `jar` và `java` còn lại dùng được tương tự trên Windows. Với dự án này và **không có agent/thành phần khác chủ động nạp `demo.LoadedLater` trước `SnapshotMain`**, stdout của lệnh Java:

```text
BEFORE_PRESENT=false
AFTER_PRESENT=true
FOUND_SAME_CLASS=true
INIT=LoadedLater
SAME_AFTER_INIT=true
```

Giải thích đúng trình tự:

1. `BEFORE_PRESENT=false`: lớp cụ thể chưa được load vào application loader trong thời điểm chụp đầu tiên của lab.
2. `Class.forName(name, false, loader)` nạp lớp mà **không** chạy khối `static`; chưa có dòng `INIT=LoadedLater`.
3. `AFTER_PRESENT=true`: snapshot thứ hai đã chứa lớp.
4. `FOUND_SAME_CLASS=true`: phần tử `Class<?>` được tìm thấy có **đúng identity**.
5. `Class.forName(name, true, loader)` kích hoạt initialization, nên **`INIT=LoadedLater`** xuất hiện sau các kết quả snapshot.
6. `SAME_AFTER_INIT=true`: initialization **không tạo ra một class identity mới**.

Nếu một agent/framework khác đã load class đó từ trước, dòng `BEFORE_PRESENT` có thể là `true`. Khi đó không được coi là API sai; cần chạy trong tiến trình lab sạch, kiểm tra những hooks khác và ranh giới khảo sát. `getAllLoadedClasses` không tự phân biệt “vì lý do nào một class được nạp”.

### 4.7. Vì sao không in tổng số lớp như một giá trị cố định?

Kết quả `snapshot.length` phụ thuộc JVM vendor/version, JDK modules, agent libraries, cách chương trình được khởi động và thời điểm GC/loading. **Không tồn tại con số chuẩn “một JVM phải có 1.000 lớp”**. Ví dụ cố tình chỉ in các boolean có điều kiện rõ, không bịa số lượng loaded classes.

Nếu muốn khảo sát số lượng thật trên máy, thêm dòng vào `SnapshotMain`:

```java
// Fragment: biến before và afterLoad đã được khai báo ở trên.
System.out.println("COUNT_BEFORE=" + before.length);
System.out.println("COUNT_AFTER=" + afterLoad.length);
```

Đây là **fragment thêm vào chương trình**, nên output hai dòng số đếm **phụ thuộc runtime**. Đừng viết unit test yêu cầu một con số chính xác cho mọi JDK.

## 5. Trường hợp đặc biệt: class loader khác nhau nhưng tên lớp giống nhau

Hệ thống plugin hoặc hot-reload có thể nạp **hai class có cùng binary name** bằng hai defining class loaders khác nhau. `getAllLoadedClasses` có thể trả **cả hai `Class<?>` objects**; nếu chuyển sang một `Set<String>` theo `getName()`, bạn sẽ vô tình **gộp hai runtime types thành một**.

### 5.1. Lớp plugin — `plugin-src/plug/SideBySide.java`

```java
package plug;

public final class SideBySide {
    public String version() {
        return "one";
    }
}
```

Chúng ta sẽ dùng **cùng một tệp class file** nhưng nạp qua **hai loaders riêng**. Không cần biên dịch hai source versions khác nhau để minh họa class identity.

### 5.2. Chương trình — `src/demo/LoaderIdentityMain.java`

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Arrays;

public final class LoaderIdentityMain {
    private LoaderIdentityMain() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LoaderIdentityMain <plugin-classes-dir>");
        }

        URL[] urls = {
                Path.of(args[0]).toAbsolutePath().toUri().toURL()
        };
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader first = new URLClassLoader(urls, parent);
             URLClassLoader second = new URLClassLoader(urls, parent)) {

            Class<?> a = Class.forName("plug.SideBySide", false, first);
            Class<?> b = Class.forName("plug.SideBySide", false, second);
            Class<?>[] snapshot = CensusAgent.snapshot();

            System.out.println("SAME_NAME="
                    + a.getName().equals(b.getName()));
            System.out.println("SAME_CLASS=" + (a == b));
            System.out.println("DIFFERENT_LOADERS="
                    + (a.getClassLoader() != b.getClassLoader()));
            System.out.println("SEES_A="
                    + Arrays.asList(snapshot).contains(a));
            System.out.println("SEES_B="
                    + Arrays.asList(snapshot).contains(b));
        }
    }
}
```

**Lý do dùng platform loader làm parent:** ngăn application/system loader (đang chạy `LoaderIdentityMain` trên `out`) vô tình định nghĩa trước `plug.SideBySide` rồi ủy quyền cả hai child loaders tới cùng class. Đây là thiết kế lab, không phải khuyến nghị dùng platform parent cho mọi plugin thực tế: ứng dụng cần chia sẻ API/SPI ở loader cha và quản lý dependency visibility theo kiến trúc.

### 5.3. Chạy thí nghiệm loader identity

Sau khi đã tạo `census-agent.jar` ở phần 4:

```bash
mkdir -p plugin-out
javac --release 17 -d plugin-out plugin-src/plug/SideBySide.java
javac --release 17 -cp out -d out src/demo/LoaderIdentityMain.java
java -javaagent:census-agent.jar -cp out demo.LoaderIdentityMain plugin-out
```

Trên Windows PowerShell, có thể tạo `plugin-out` bằng `New-Item -ItemType Directory -Force plugin-out`; còn `javac` và `java` giữ nguyên.

Stdout trên JDK hỗ trợ `-javaagent`, với class plugin chỉ ở `plugin-out` và không có cơ chế nạp khác can thiệp:

```text
SAME_NAME=true
SAME_CLASS=false
DIFFERENT_LOADERS=true
SEES_A=true
SEES_B=true
```

Mặc dù `a.getName()` và `b.getName()` đều trả `plug.SideBySide`, JVM coi chúng là **hai class identities**. Snapshot chứa hai `Class<?>` references riêng. Điều này giải thích tại sao:

- Đếm `snapshot.length` khác đếm **số tên lớp duy nhất**.
- Key `String name` không đủ để gán đúng class cho một loader.
- `isModifiableClass(a)` và `isModifiableClass(b)` có thể cần hỏi **riêng**, vì là hai runtime types.
- Khi loại plugin, phải giải phóng references tới `Class<?>` và classloaders cũ nếu muốn lớp cũ đủ điều kiện unload.

Lệnh `URLClassLoader.close()` đóng tài nguyên loader phù hợp, **không tự ép JVM unload** classes đang được các references khác giữ.

## 6. `getAllLoadedClasses` khác `getInitiatedClasses(loader)` thế nào?

Hai API cùng trả `Class[]` nhưng trả lời **hai câu hỏi khác nhau**:

| API | Câu hỏi | Phạm vi và giới hạn |
| --- | --- | --- |
| `getAllLoadedClasses()` | “Toàn JVM đang có những runtime classes nào?” | Bao gồm classes, interfaces, hidden types, arrays theo Javadoc |
| `getInitiatedClasses(loader)` | “Loader này có thể tìm những class nào bằng tên theo cơ chế load/link?” | Những classes với loader đã được ghi nhận là **initiating loader**; nếu `loader == null` là bootstrap |
| `Class.getClassLoader()` | “Defining loader của **một Class<?>** là ai?” | Thuộc tính của từng class, **không** phải danh sách initiating loaders |

`getInitiatedClasses(loader)` có thể chứa classes **do parent định nghĩa** nhưng child đã **initiate** qua delegation. Không được mặc nhiên coi mỗi phần tử trả về là class có `clazz.getClassLoader() == loader`.

Javadoc JDK 17 nêu thêm: `getInitiatedClasses` **không bao gồm hidden classes/interfaces và array classes có component type là hidden class/interface**, vì chúng không thể được loader tìm theo tên theo cách thông thường. Ngược lại, `getAllLoadedClasses` **bao gồm** chúng.

### 6.1. Một fragment đọc initiated classes

```java
// Fragment: lấy từ class CensusAgent và lớp main đã biết.
ClassLoader loader = SnapshotMain.class.getClassLoader();
Class<?>[] initiated = CensusAgent.initiatedBy(loader);
System.out.println("INITIATED_COUNT=" + initiated.length);
```

**Đây là fragment**, không phải một dòng stdout cố định. Danh sách và count có thể thay đổi trong cùng JVM khi loading/linking diễn ra. Không nhầm initiating loader với defining loader trong phân tích plugins.

### 6.2. Bootstrap loader và `null`

`Class.getClassLoader() == null` thường chỉ class do **bootstrap loader** định nghĩa. `getInitiatedClasses(null)` có nghĩa hỏi classes mà bootstrap loader có thể tìm bằng tên; nó **không** nghĩa “không cần filter”, và **không** đồng nghĩa toàn bộ JVM.

Khi log, nên dùng marker rõ ràng như `<bootstrap>` cho loader `null`, vì chuỗi `null` dễ bị hiểu nhầm là thiếu dữ liệu. Đây là lựa chọn hiển thị, không phải tên thật của một Java `ClassLoader` object.

## 7. Hidden classes, array classes, interfaces và primitives

### 7.1. Hidden classes

`Class.isHidden()` giúp nhận biết lớp được định nghĩa theo cơ chế hidden class (JDK 15+). Hidden classes thường phục vụ các runtime frameworks/language mechanisms; chúng không có tên binary bình thường để `Class.forName` nạp trực tiếp. Vì vậy:

- Có thể **xuất hiện trong `getAllLoadedClasses`**.
- Không được suy tên có thể dùng nguyên văn để load lại bằng `Class.forName`.
- Không nên coi chúng như một candidate bình thường cho mọi loại redefinition/retransformation.
- Có thể tăng số lượng loaded classes dù bạn không thấy tệp `.class` tương ứng trong build output.
- Nếu log tên, cần chú ý các tên có thành phần sinh động/runtime-specific và policy bảo mật.

**Không được** giả định mọi lambda trên mọi JDK/vendor được hiện thực bằng cùng một cơ chế hidden classes. Quan sát `clazz.isHidden()` thay vì suy đoán từ pattern tên.

### 7.2. Array classes

Mảng `String[]`, `int[]` và `int[][]` đều có `Class<?>` objects. Khi xuất hiện trong snapshot, `clazz.isArray()` là `true`. `getName()` của array class có thể là descriptor-like form như `[Ljava.lang.String;` hoặc `[I` thay vì cú pháp source `java.lang.String[]`.

Với một array class, `getComponentType()` giúp đi xuống element/component type:

```java
// Fragment: arrayType là Class<?> và được kiểm tra trước.
if (arrayType.isArray()) {
    Class<?> component = arrayType.getComponentType();
    System.out.println(component.getName());
}
```

Một array class **không phải** class có methods của riêng mình để retransform tùy ý. Theo Javadoc `Instrumentation.isModifiableClass`, **array classes và primitive classes không bao giờ modifiable**. Vì vậy *“nằm trong snapshot” không dẫn tới “được phép thay bytecode”*.

### 7.3. Interfaces và primitive types

`getAllLoadedClasses` trả cả interfaces: `clazz.isInterface()` phân biệt. Với primitive types (ví dụ `int.class`, `void.class`), các `Class<?>` objects đại diện cho primitives không đồng nghĩa một Java class file đã được load/defined như reference class. Không thiết kế công cụ “scan loaded classes” dựa trên giả định primitives có class-file bodies hoặc là đối tượng có thể retransform.

Nếu muốn phân loại mọi phần tử, ưu tiên đặc điểm API `isArray()`, `isHidden()`, `isInterface()`, `isPrimitive()` thay vì so tên chuỗi như `"["` hay `"lambda"`.

## 8. Quét toàn JVM: lọc, sắp xếp và báo cáo cho an toàn

Để tạo báo cáo dễ đọc, nên snapshot một lần, lọc đúng package/module/loader, trích những trường cần thiết rồi **giải phóng mảng** sau xử lý. Một số ví dụ fragment:

```java
Class<?>[] snapshot = CensusAgent.snapshot();

long arrayCount = Arrays.stream(snapshot)
        .filter(Class::isArray)
        .count();

long hiddenCount = Arrays.stream(snapshot)
        .filter(Class::isHidden)
        .count();

long interfaceCount = Arrays.stream(snapshot)
        .filter(Class::isInterface)
        .count();
```

**Fragment:** cần `import java.util.Arrays;` và một agent `CensusAgent` hoạt động. Các count phụ thuộc từng JVM/chương trình và **có thể thay đổi theo thời điểm**; không có stdout cố định đáng tin cho ví dụ này.

### 8.1. Đừng dùng `getName()` làm khóa duy nhất

Nếu cần nhóm:

```text
Identity thực tế của class:
  Class<?> reference
  + defining ClassLoader identity
  + name/module khi hiển thị
```

Với `HashMap<Class<?>, ...>` hoặc `Set<Class<?>>`, chính `Class<?>` references giúp phân biệt hai types cùng name. Một `Map<String, Class<?>>` theo `getName()` có thể ghi đè một bản khi hai plugin loaders định nghĩa cùng binary name.

Để hiển thị ổn định, **sắp xếp bản sao danh sách đã lọc** theo tên + loader description thay vì kỳ vọng thứ tự từ `getAllLoadedClasses`. Không sửa mảng JVM bên trong; mảng trả về là một container quan sát riêng, nhưng lớp bên trong là các runtime objects. Dù sắp xếp để hiển thị, không nhầm vị trí đã sắp xếp với thứ tự class thực tế được JVM load.

### 8.2. Tiêu chí lọc thường gặp

| Tiêu chí | Ví dụ | Cảnh báo |
| --- | --- | --- |
| Package prefix | `getName().startsWith("com.example.")` | Hidden/arrays có naming khác; prefix có thể bỏ sót |
| Loader identity | `clazz.getClassLoader() == targetLoader` | Chọn defining loader, khác initiating loader |
| Named module | `clazz.getModule().getName()` | Unnamed module trả `null`; cần xử lý |
| Array/hidden | `isArray()`, `isHidden()` | Không mọi runtime type đều có file class độc lập |
| Capability | `inst.isModifiableClass(clazz)` | Có thể là false; điều kiện cần nhưng không đủ để retransform thành công |
| Annotation/reflection | `getDeclaredMethods()`, `getAnnotations()` | Có thể kích hoạt việc tải types khác; dễ tốn chi phí/vi phạm access |

Bản report nên giới hạn số dòng, có sampling/batching và không in liên tục hàng chục nghìn tên class vào stdout trong đường nóng của ứng dụng. **Tên lớp/module/loader** cũng có thể tiết lộ cấu trúc ứng dụng hoặc dependencies; bảo vệ log phù hợp.

## 9. Snapshot không phải stream load/unload events

Nếu gọi snapshots tại T1 và T2 rồi tính:

```text
added = S2 - S1
removed = S1 - S2
```

thì đây là **chênh lệch membership giữa hai lần quan sát**, không phải log sự kiện đầy đủ. Một class có thể được load rồi unload giữa hai lần và **không hề xuất hiện ở cả hai snapshots**. Khi có nhiều loader cùng tên, phép trừ phải dùng **class identity**, không chỉ name.

Đặc biệt:

- **Không suy ra load order** từ thứ tự phần tử mảng.
- **Không suy ra thời gian load** từ một `Class<?>` (không có field `loadedAt` tiêu chuẩn).
- **Không suy ra lý do class được nạp** hoặc bytecode source từ một `Class<?>` object.
- **Không khẳng định class đã initialized** vì hiện trong mảng.
- **Không khẳng định không có leak** chỉ vì class count không tăng giữa hai lần đo.
- **Không suy ra số objects** thuộc lớp từ việc lớp chỉ xuất hiện một lần trong snapshot.

Muốn ghi **events mỗi khi class được định nghĩa**, hãy dùng công cụ phù hợp như `ClassFileTransformer` ở load time, JVMTI events hoặc JFR events (tùy event và khả năng runtime), thay vì dùng `getAllLoadedClasses` như một callback. Nếu cần chụp danh sách hiện tại lúc agent được attach **sau khi chương trình đã chạy**, API đặc biệt hữu ích vì không bỏ lỡ các classes đã tồn tại trước khi agent bắt đầu quan sát.

### 9.1. Lúc nào snapshot khác ClassFileTransformer?

| Nhu cầu | Công cụ/đường đi |
| --- | --- |
| Lấy danh sách classes **hiện đang load** | `Instrumentation.getAllLoadedClasses()` |
| Xem các classes loader đã initiate | `Instrumentation.getInitiatedClasses(loader)` |
| Nhìn bytes của lớp **trong callback** khi load/redefine/retransform | `ClassFileTransformer.transform` |
| Thay bytecode method của class đã load | `retransformClasses` / `redefineClasses` nếu capability/target cho phép |
| Xem class file từ JAR hoặc thư mục trên disk | `jar`, `javap`, `Files.readAllBytes` |
| Phân tích bytecode class file theo API typed | ASM; hoặc `java.lang.classfile` trên JDK 24+ |
| Quan sát load/unload theo thời gian | Logging/events JFR/JVMTI hoặc agent callback thích hợp |

**Đừng nhầm:** `getAllLoadedClasses` **không trả bytecode** và **không tự tạo `ClassFileTransformer` callback**. Muốn “dump every loaded class file” không phải chỉ viết `Class<?>[] classes = getAllLoadedClasses()` rồi serialize `clazz`.

## 10. Kiểm tra khả năng thay đổi class sau khi lấy snapshot

Một bước hay gặp trong instrumentation là lấy các classes rồi chọn target để `retransformClasses`. Làm đúng theo trình tự:

1. Chụp `Class<?>[]`.
2. Chọn class cần phân tích theo **identity + loader + class name + policy**.
3. Gọi `isModifiableClass(type)` cho đúng class đó.
4. Kiểm tra `isRetransformClassesSupported()` và manifest agent nếu muốn retransform.
5. Đăng ký transformer với `addTransformer(transformer, true)` khi phù hợp, bảo đảm output class file hợp lệ.
6. Chỉ gọi `retransformClasses` trên những targets đúng và modifiable, có error handling/rollback hợp lý.

Một fragment:

```java
// Fragment: inst là Instrumentation đã được agent cung cấp.
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(candidate)) {
    inst.retransformClasses(candidate);
}
```

`candidate` phải là một `Class<?>` đã chọn; đoạn này cần xử lý `UnmodifiableClassException`, `UnsupportedOperationException` và các lỗi bytecode khác trong code thật. Không suy luận **mọi lớp thấy trong snapshot đều có thể retransform**. Array/primitive không modifiable; một số classes khác cũng không modifiable tùy JVM. Chỉ việc gọi `getAllLoadedClasses` không cấp capability nào.

Ở các JVM sau JDK 21, nạp agent động có các cảnh báo/chính sách theo phiên bản; thí nghiệm của bài dùng **startup `-javaagent`** nên không cần cấu hình quyền attach/self-attach.

## 11. Vấn đề hiệu năng, bộ nhớ và bảo mật

### 11.1. Chi phí tạo mảng nhiều lần

Snapshot có thể chứa **hàng chục nghìn `Class<?>` objects** trong ứng dụng lớn. Gọi API trong loop tốc độ cao gây:

- Chi phí JVM duyệt/thu thập danh sách.
- Cấp phát `Class<?>[]` và rác GC.
- Chi phí lọc/sắp xếp/log, có thể nhiều hơn việc lấy mảng.
- Những references dài hạn làm khó class unloading.
- Nguy cơ contention/safepoint/ảnh hưởng latency tùy VM, thời điểm và quy mô.

**Không** gọi `getAllLoadedClasses()` cho **mỗi request**, **mỗi method invocation**, hoặc trong `transform` callback cho mọi class. Ưu tiên trigger theo chẩn đoán, khoảng thời gian đủ thưa, rate limit, cache số liệu tổng hợp và giới hạn output.

### 11.2. Tác dụng phụ của việc inspect

Việc gọi `getAllLoadedClasses` để lấy `Class<?>[]` không có ý nghĩa “khởi tạo tất cả classes”. Nhưng nếu sau đó code tự gọi `Class.forName(name)`, `getDeclaredMethods()`, truy vấn annotations hoặc tạo instance, các thao tác ấy có thể dẫn đến loading/linking/initialization, class access checks hoặc exception riêng. **Tách bước enumerate và bước reflective deep inspection**, ghi rõ tác động.

### 11.3. Dữ liệu nhạy cảm

Tên classes và loaders có thể cho biết framework, internal package, công nghệ hoặc module triển khai. Nếu snapshot phục vụ vận hành, chỉ xuất thông tin cần thiết, kiểm soát quyền xem, rút gọn tên/loại trừ packages nhạy cảm và không ghi data từ object instances.

## 12. Phân biệt theo loader, module và runtime identity

Với cùng tên `com.acme.Plugin`, có thể có:

```text
com.acme.Plugin @ LoaderPluginA
com.acme.Plugin @ LoaderPluginB
com.acme.Plugin @ LoaderPluginC
```

Đây là **ba runtime class identities** nếu ba defining loaders thực sự định nghĩa type riêng. `Class.getModule()` giúp phân nhóm theo JPMS module; unnamed modules có thể khác nhau theo loader ngay cả khi `getName()` của module trả `null`.

Không chỉ tạo một dictionary `Map<String, Boolean> loadedByName` để xem plugin đã load: kết quả có thể báo “đã load” do loader A trong khi ứng dụng đang cần loader B. Bên cạnh tên, lưu một **loader ID riêng cho report** (theo object identity hoặc số định danh nội bộ) thay vì `loader.toString()` như khóa duy nhất lâu dài.

Nếu cần theo dõi **unloading**, đừng giữ `Class<?>` hoặc loader trong một static map mạnh vô hạn. Có thể dùng số liệu đã tách khỏi object references, weak references trong trường hợp phù hợp, hoặc công cụ chuyên biệt; vẫn cần hiểu GC không có thời điểm unload bảo đảm.

## 13. Những nhầm lẫn phổ biến

| Nhận định | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Snapshot có mọi class trong classpath” | Classpath là tập tài nguyên *có thể* load | API chỉ liệt kê classes **hiện đã load** |
| “Class đã load nghĩa là đã chạy static initializer” | Loading và initialization là các giai đoạn khác nhau | `Class.forName(name,false,loader)` có thể load mà chưa initialize |
| “Mảng trả về sẽ tự cập nhật về sau” | Mảng là kết quả của lần gọi | Gọi lại để lấy snapshot mới |
| “Thứ tự trong array là load order” | Javadoc không quy định thứ tự đó | Không suy timeline từ index |
| “Một tên class chỉ xuất hiện một lần” | Hai defining loaders có thể tạo hai runtime types cùng tên | So `Class<?>` identity và loader |
| “Nhìn thấy class thì chắc retransform được” | Nhiều classes không modifiable | Kiểm tra capability và `isModifiableClass` |
| “Lấy snapshot sẽ trả raw .class bytes” | API trả `Class[]` | Dùng callback/bytecode tooling cho bytes |
| “getInitiatedClasses loader là toàn bộ classes loader tự định nghĩa” | Initiating loader có thể là child ủy quyền parent | Phân biệt initiating và defining |
| “Hidden types không thuộc snapshot” | `getAllLoadedClasses` bao gồm hidden types trên JDK 17+ | Dùng `isHidden` để phân loại |
| “Mọi hidden class có thể load lại theo tên” | Hidden class không phải class findable by name | Không `Class.forName` như type bình thường |
| “Arrays không có Class objects” | Array types có `Class<?>` objects | `isArray` và component type |
| “Snapshot count là số object instances” | Một class có thể có 0 hay hàng triệu objects | Snapshot đo **types**, không đo instances |
| “Giữ snapshots không ảnh hưởng memory” | `Class<?>` references có thể giữ loader sống | Giải phóng snapshots, tránh strong refs dài hạn |
| “Diff hai snapshots là log đầy đủ load/unload” | Events có thể xảy ra giữa hai lần gọi | Chỉ kết luận chênh lệch membership |
| “Đếm tên unique là số runtime classes” | Gộp types cùng tên từ nhiều loaders | Đếm `Class<?>` identities |
| “Không thấy lớp nghĩa JVM chưa từng load nó” | Nó có thể đã unload trước snapshot | Snapshot chỉ mô tả **hiện tại** |
| “Gọi enumerate tự thêm transformer” | Đây là API quan sát | Không có biến đổi bytecode nếu không đăng ký/gọi API khác |

## 14. Checklist kiểm thử một bộ quét classes

- [ ] Agent `premain`/`agentmain` nhận đúng `Instrumentation`; không cố `new` interface này.
- [ ] Snapshot được chụp đúng **JVM process** và đúng thời điểm mong muốn.
- [ ] Dùng `Class<?>[]`, không coi các entries là class names hay class bytes.
- [ ] Có thể thấy interface, hidden class và array class; code phân loại đúng.
- [ ] Không giả định static initialization xảy ra khi class xuất hiện.
- [ ] Phân biệt cùng binary name nhưng khác defining loader.
- [ ] Không dựa vào thứ tự của snapshot.
- [ ] Nếu so hai snapshots, dùng identity-based set/diff và xử lý thời điểm load/unload.
- [ ] Không dùng map chỉ theo string name để đại diện một runtime class.
- [ ] Không giữ toàn bộ `Class<?>[]` dài hạn trong static caches.
- [ ] Không gọi scan với tần suất rất cao hoặc trong mọi method invocation.
- [ ] Có filter/package/module scope, giới hạn log size, kiểm soát data sensitivity.
- [ ] Với retransformation, kiểm tra capability, manifest và `isModifiableClass` tách biệt.
- [ ] Không dùng raw hash/classpath file list làm bằng chứng về loaded runtime classes.
- [ ] Kiểm tra behavior trên JVM vendor và version mục tiêu, không hardcode total class count.

## 15. Câu hỏi tự kiểm tra

1. **`getAllLoadedClasses` trả file bytes hay `Class<?>[]`?**  
   Trả `Class<?>[]`: danh sách các runtime class objects.

2. **Class nằm trong JAR nhưng chưa load có được liệt kê không?**  
   Không chỉ vì nó có trong JAR/classpath. Phải được JVM load.

3. **Vì sao snapshot chứa `demo.LoadedLater` trước khi in `INIT=LoadedLater`?**  
   `Class.forName(name,false,loader)` load class mà chưa yêu cầu initialization.

4. **Có thể dùng `snapshot[0]` để biết class đầu tiên JVM load không?**  
   Không. Thứ tự mảng không phải hợp đồng thứ tự class loading.

5. **Hai classes có cùng `getName()` nhưng khác defining loaders có phải một class không?**  
   Không. Chúng là hai runtime identities; cùng tên vẫn có thể khác `Class<?>`.

6. **`getInitiatedClasses(loader)` có thể chứa class do parent định nghĩa không?**  
   Có. “Initiating” loader có thể ủy quyền để parent định nghĩa class.

7. **Hidden class có trong `getAllLoadedClasses` nhưng không trong `getInitiatedClasses` được không?**  
   Có theo Javadoc JDK 17+, vì hidden types không tìm lại được theo tên thông thường.

8. **Mỗi snapshot có bắt buộc tăng số lượng so với lần trước?**  
   Không. JVM có thể load/unload, và quá trình quan sát không bảo đảm count chỉ tăng.

9. **`getAllLoadedClasses` có tự biến đổi class hay chạy static initializers của tất cả classes không?**  
   Không có chức năng ấy. Đây là API khảo sát, không phải transformer hay initializer.

10. **Class ở snapshot đều có thể gọi `retransformClasses` không?**  
    Không. Phải kiểm tra `isModifiableClass` và `isRetransformClassesSupported`; array/primitive classes không modifiable.

11. **Nếu giữ `Class<?>[]` trong static cache mãi, có nguy cơ gì?**  
    Strong references tới `Class`/loaders có thể giữ classes/plugin loaders sống, làm phình memory.

12. **Một lớp đã load rồi unload giữa T1/T2 nhưng vắng ở cả hai snapshots có được nhận diện không?**  
    Không bằng phép so hai snapshots; cần event stream/logging thích hợp.

13. **Tại sao `getName()` không phải khóa đủ cho plugin inventory?**  
    Nhiều defining loaders có thể định nghĩa cùng binary name; phải có loader/identity.

14. **`Class.forName("demo.LoadedLater",true,loader)` khác tham số `false` ở đâu?**  
    `true` yêu cầu initialization nếu chưa initialized; `false` không yêu cầu chạy initializer.

15. **Muốn thấy bytecode của class đã load phải làm gì?**  
    Dùng đường thu thập class-file bytes qua transformer/retransform hoặc JVMTI/diagnostic tooling phù hợp, không phải lấy `Class<?>[]` rồi cast sang bytes.

## 16. Tài liệu chính thức

- **Oracle JDK 17 — `Instrumentation.getAllLoadedClasses`, `getInitiatedClasses`, `isModifiableClass`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- **Oracle JDK 25 — `Instrumentation`** (đối chiếu API ở bản JDK mới): https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- **Oracle JDK 17 — `java.lang.instrument` package**, `premain`/`agentmain`, manifest `Premain-Class`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- **Oracle JDK 17 — `Class.forName(name, initialize, loader)`** và các phương thức kiểm tra `Class<?>`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Oracle JDK 17 — `ClassLoader`**, parent delegation và defining loader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Oracle JDK 17 — `URLClassLoader`** và `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **JVMS 17 — Chapter 5: Loading, Linking, and Initializing**, class identity và runtime packages: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html

**Kết luận:** `Instrumentation.getAllLoadedClasses()` là cách lấy **một ảnh chụp những runtime classes hiện có trong JVM**. Kết quả là `Class<?>[]` gồm cả interfaces, hidden types và arrays; nó không phải danh sách mọi class file trên disk, không tự chứng minh initialization hoặc khả năng retransform, không có thứ tự tải lớp, và không tự cập nhật. Hãy đối chiếu theo **class identity + defining loader**, chỉ lấy snapshots khi cần, và giải phóng references sau khi phân tích.
