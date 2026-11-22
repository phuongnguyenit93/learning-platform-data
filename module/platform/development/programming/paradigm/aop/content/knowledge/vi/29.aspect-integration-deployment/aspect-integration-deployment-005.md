# Triển khai dệt khi nạp trong môi trường có nhiều bộ nạp lớp

## 1. Mục tiêu và bối cảnh

Trong **Aspect-Oriented Programming (AOP)**, *weaving* (dệt) là quá trình đưa logic của aspect vào các vị trí **join point** phù hợp trong chương trình. Với **load-time weaving (LTW)**, weaver biến đổi bytecode **trong quá trình class loader nạp và định nghĩa lớp cho JVM**, thay vì bắt buộc tạo sẵn mọi lớp đã dệt lúc build.

Khi hệ thống chỉ có một class loader ứng dụng, việc thiết lập LTW có thể trông đơn giản: cung cấp aspect, cấu hình pointcut và bật weaver từ đầu. Nhưng hệ thống plugin, ứng dụng cách ly theo tenant, máy chủ có nhiều module, test sandbox, chương trình có loader tự viết hoặc nền tảng nạp mã động thường có **nhiều class loader**. Khi đó, câu hỏi thực sự là:

- Loader nào **định nghĩa** lớp đích? Loader nào chỉ **ủy quyền** yêu cầu nạp cho loader khác?
- Aspect, thư viện runtime và cấu hình weaving có **hiển thị** với loader sẽ định nghĩa lớp đích hay không?
- Agent/weaver đã hoạt động **trước thời điểm lớp đích được định nghĩa** chưa?
- Hai lớp có cùng tên nhị phân nhưng do hai loader khác nhau định nghĩa có được dệt, khởi tạo và quản lý trạng thái như hai thực thể riêng không?
- Khi triển khai hoặc gỡ plugin, những tham chiếu nào khiến loader cũ không thể được thu gom rác?

Bài dùng **AspectJ** làm ví dụ thực tế cho LTW và cú pháp pointcut; các nguyên tắc về danh tính lớp, ủy quyền class loader và thời điểm định nghĩa lớp áp dụng rộng trong Java. Các công cụ AOP khác có thể có tập join point và cách tích hợp riêng. Mục tiêu là hiểu cơ chế, triển khai có giới hạn, kiểm chứng được từng loader và chẩn đoán lỗi chính xác.

## 2. Ba kiểu weaving và giới hạn của LTW

| Kiểu | Thời điểm | Đầu vào điển hình | Tính chất |
| --- | --- | --- | --- |
| Compile-time weaving (CTW) | Khi biên dịch nguồn | Java/AspectJ source | Compiler tạo ra bytecode đã dệt. |
| Post-compile/binary weaving | Sau khi có `.class`/JAR, trước khi nạp | Bytecode có sẵn | Tạo artifact mới đã dệt. |
| Load-time weaving (LTW) | Khi một loader chuẩn bị định nghĩa class | Bytecode đi qua class loading/transformer | Biến đổi tại thời điểm nạp, phụ thuộc loader và cấu hình nhìn thấy lúc đó. |

LTW không đồng nghĩa với “đợi phương thức chạy rồi mới chèn advice”. **Khi một lớp đã được JVM định nghĩa**, chỉ bật agent hoặc thêm aspect sau đó **không tự động** dệt lại lớp ấy. Java Instrumentation có những API liên quan đến retransformation/redefinition, nhưng đó là cơ chế khác, chịu giới hạn riêng; không coi AspectJ LTW thông thường là giải pháp tự động dệt lại mọi lớp đã nạp.

Trong mô hình AspectJ, dệt tại thời điểm nạp có thể được kích hoạt bởi một class loader tích hợp khả năng weaving, hoặc bởi một Java instrumentation agent như `-javaagent:/path/to/aspectjweaver.jar`. Hai cách khởi tạo khác nhau nhưng đều phải tôn trọng quan hệ class loader và thời điểm định nghĩa lớp.

## 3. Danh tính lớp Java trong hệ thống nhiều loader

Trong JVM, danh tính runtime của một class về thực chất được xác định bởi **tên nhị phân cùng defining class loader**. Tên `com.example.Plugin` giống hệt nhau không có nghĩa là cùng `Class<?>`.

```text
Bootstrap / Platform
          │
Application loader ──────── common API + shared aspect
          │
          ├── PluginLoader-A ─── com.acme.plugin.Worker
          │
          └── PluginLoader-B ─── com.acme.plugin.Worker
```

Nếu cả hai plugin loader tự định nghĩa bytecode `com.acme.plugin.Worker`, ta có hai class runtime khác nhau:

- `workerA.getName().equals(workerB.getName())` → `true`.
- `workerA == workerB` → `false`.
- Method, static field, static initializer và class-level state của Worker thuộc từng bản định nghĩa riêng.
- Ép kiểu đối tượng Worker-A sang Worker-B có thể gây `ClassCastException` hoặc `Class<?>` mismatch dù tên lớp giống nhau.
- Mỗi loader có tập lớp/resource tìm thấy và cơ chế ủy quyền riêng; do đó cùng một tên pointcut không đảm bảo mọi loader đều được weaving giống nhau.

Cần phân biệt ba khái niệm:

**Initiating loader:** loader nhận yêu cầu nạp lớp; có thể nhờ loader cha thực hiện.

**Defining loader:** loader thực sự gọi cơ chế định nghĩa class trong JVM. Đây mới là loader quyết định danh tính class và ranh giới LTW của lớp đó.

**Thread context class loader (TCCL):** loader do thread giữ trong `Thread.currentThread().getContextClassLoader()`. Một số thư viện dùng nó để tra cứu service/resource, nhưng nó **không tự biến thành defining loader** của class, cũng không tự quyết định class nào được LTW dệt. Phải quan sát trực tiếp `SomeClass.class.getClassLoader()`.

### Ủy quyền parent-first và loader tự tùy biến

Nhiều loader Java hoạt động theo kiểu **parent-first**: hỏi parent trước, sau đó mới tìm trong nội bộ. Nếu parent đã có `com.acme.plugin.Worker`, hai child loader có thể chỉ nhận đúng class parent đã định nghĩa. Khi đó chúng **không** tạo hai bản class độc lập dù đều có cùng file `Worker.class` trong URL riêng.

Một số hệ thống plugin cố ý dùng child-first cho namespace plugin. Điều đó thay đổi nơi class được định nghĩa, khả năng nhìn thấy resource, khả năng dùng aspect và rủi ro xung đột kiểu. Không nên thay delegation strategy chỉ để “ép aspect chạy” mà chưa xét compatibility, isolation và an toàn.

## 4. Ba quy tắc cốt lõi khi LTW gặp nhiều class loader

Tài liệu AspectJ quy định rõ ba nguyên tắc:

1. **Aspect phải được khai báo cho weaver trước khi các lớp đích được nạp.** Nếu class đã được định nghĩa rồi mới thêm aspect/cấu hình, các join point trên class đó có thể bị bỏ lỡ.
2. **Weaver dùng được các aspect nhìn thấy từ loader đang dệt hoặc các loader cha của nó.** Aspect nằm riêng trong loader con A không mặc định hiển thị cho loader con B.
3. **Một class loader chỉ có thể dệt những class do chính nó định nghĩa.** Loader con không thể quay lại dệt class đã được parent hoặc loader ủy quyền khác định nghĩa.

Diễn giải bằng ví dụ:

| Class đích | Defining loader | Aspect được đặt ở | Kết luận cần kiểm tra |
| --- | --- | --- | --- |
| `PluginA.Worker` | PluginLoader-A | Application loader (parent của A) | Aspect có thể nhìn thấy từ A; A cần cấu hình/agent đúng để dệt. |
| `PluginB.Worker` | PluginLoader-B | PluginLoader-A | B không thấy aspect của A theo sibling isolation thông thường. |
| `SharedApi` | Application loader | PluginLoader-A | A không được dệt lại `SharedApi` do parent đã định nghĩa. |
| `Worker` cùng tên ở A và B | Mỗi plugin loader riêng | Shared parent | Có thể dệt hai class độc lập; phải kiểm tra cả hai. |
| `Worker` đã được định nghĩa trước khi bật LTW | Bất kỳ loader | Aspect khai báo muộn | Không tự kỳ vọng weaving hồi tố. |

“Có thể nhìn thấy” là **điều kiện cần**, chưa đủ. Còn phải có cấu hình `META-INF/aop.xml` thích hợp, class nằm trong vùng `include/exclude`, các pointcut thực sự khớp join point, aspect/runtime tương thích và agent được bật đúng thời điểm.

**Lỗi thường gặp:** đặt `aspectjweaver.jar` trên classpath ứng dụng chính, thấy agent khởi động, rồi kết luận mọi class của mọi plugin đã được dệt. Điều này không đúng nếu plugin loader không nhìn thấy aspect/cấu hình, không đi qua transformer phù hợp, class đã được nạp trước hoặc pattern loại class đích.

## 5. Kiến trúc triển khai được khuyến nghị

Một sơ đồ khả thi cho nhiều plugin có chung quy tắc tracing:

```text
JVM startup
  └── -javaagent:.../aspectjweaver.jar
        └── Application loader
              ├── aspectjweaver/runtime
              ├── demo.TraceAspect
              ├── META-INF/aop.xml
              ├── HostMain
              │
              ├── PluginLoader-A
              │     └── demo.Plugin (được A định nghĩa)
              │
              └── PluginLoader-B
                    └── demo.Plugin (được B định nghĩa)
```

Luồng triển khai:

1. Khởi chạy JVM với agent đúng phiên bản.
2. Đưa aspect dùng chung và `META-INF/aop.xml` vào vị trí có thể được các loader cần dệt nhìn thấy. Với parent-first, shared parent thường là lựa chọn dễ kiểm soát.
3. Để class plugin chỉ được định nghĩa trong plugin loader tương ứng, tránh đặt trùng bản plugin trong classpath cha.
4. Trong XML, **chỉ định rõ aspect** và thu hẹp những class cần weave bằng type pattern.
5. Tải từng plugin, ghi nhận defining loader của từng class và kiểm tra số lần advice chạy.
6. Khi unload/reload plugin, loại mọi tham chiếu lâu dài đến class/instance/loader cũ, sau đó mới đánh giá khả năng GC.

Cấu trúc không nhất thiết luôn như vậy. Có hệ thống chọn aspect **riêng cho mỗi plugin** để tránh chia sẻ state, hoặc dùng class loader có hỗ trợ weaving đặc biệt. Nhưng mỗi lựa chọn phải công khai ranh giới aspect visibility, runtime dependency, configuration discovery, class identity và lifecycle.

### Khi nên đặt aspect ở parent?

Đặt aspect ở shared parent phù hợp khi muốn cùng một chính sách chạy trên nhiều plugin và chấp nhận rằng **bản class của aspect có thể được chia sẻ**. Điều này không có nghĩa advice/state tự cô lập theo tenant. Nếu aspect singleton chứa một `static Map` theo đối tượng plugin hoặc có instance field mutable, các plugin có thể cùng tác động lên state ấy. Nếu thiết kế cần isolation, phải định nghĩa state key và lifecycle rõ ràng, hoặc bố trí aspect ở loader riêng theo yêu cầu.

### Khi nào aspect nên ở child?

Khi từng plugin có chính sách riêng hoặc mã aspect không được chia sẻ với các plugin khác. Cần đảm bảo plugin loader thấy chính aspect đó và runtime mà nó dùng; aspect của plugin A không đương nhiên khả dụng với plugin B. Nếu cùng một tên aspect được định nghĩa ở hai child loader, đó là **hai class runtime khác nhau**, mang state/lifecycle riêng.

## 6. Cấu hình `META-INF/aop.xml` và phạm vi loader

Với AspectJ LTW, các tệp `META-INF/aop.xml` **nằm trên đường tìm kiếm tài nguyên của class loader** được dùng để cấu hình weaver. Một loader có thể nhìn thấy nhiều `aop.xml`, ví dụ một file trong shared parent và một file riêng trong plugin.

Cấu hình mẫu:

```xml
<aspectj>
    <aspects>
        <aspect name="demo.TraceAspect"/>
    </aspects>
    <weaver options="-showWeaveInfo">
        <include within="demo.Plugin"/>
    </weaver>
</aspectj>
```

Giải thích:

- `<aspect name="demo.TraceAspect"/>` **khai báo aspect** cho weaver; chỉ `include` không tự “tìm” aspect chưa được khai báo.
- `<include within="demo.Plugin"/>` giới hạn class đích theo type pattern. Dùng chính xác namespace triển khai; không mở rộng thành `*..*` khi không cần.
- `options="-showWeaveInfo"` bật thông tin dệt có ích khi kiểm chứng; ở production nên cân nhắc mức log để tránh chi phí và nhiễu.
- Cấu hình được đọc theo **loader/resource visibility**; cùng một file đặt trong resource path của parent có thể được nhiều child nhìn thấy theo delegation, nhưng việc dệt từng child vẫn phải được kiểm tra riêng.

Một số chi tiết cần biết:

1. Khi có **nhiều file `aop.xml` hiển thị**, các khai báo, tùy chọn và filter có thể được kết hợp theo quy tắc của weaver. Không mặc định mỗi file là một “sandbox” độc lập.
2. Các mục `<aspects><include .../></aspects>` và `<aspects><exclude .../></aspects>` lọc **tập aspect đã khai báo**; các mục `<weaver><include .../></weaver>` và `<weaver><exclude .../></weaver>` lọc **tập type sẽ dệt**. Nhầm hai vị trí này dễ khiến aspect mất hiệu lực hoặc weave sai class.
3. Nếu không có `weaver include`, phạm vi có thể rất rộng (các type không bị loại), tăng thời gian nạp và rủi ro chạm code của thư viện.
4. Nếu môi trường expose nhiều bản khác nhau của cùng aspect hoặc nhiều file XML định nghĩa trùng một *concrete-aspect* cùng tên, có thể phát sinh lỗi/xung đột. Hãy kiểm tra resource enumeration và ownership.
5. Khi include/exclude không chọn class nào, **agent vẫn có thể báo khởi động bình thường** mà advice không xuất hiện.

Các mẫu type trong `within` là **pattern**, không phải đường dẫn filesystem hay tên module. Ví dụ `com.acme.plugin..*` đại diện các kiểu trong package và package con theo cú pháp AspectJ; không bao gồm namespace ngoài vùng đó.

## 7. Ví dụ chạy: cùng một class được hai URLClassLoader định nghĩa và dệt riêng

Ví dụ chứng minh ba việc: parent thấy aspect/cấu hình, hai child loader tự định nghĩa cùng tên binary class, và advice chạy khi hai bản class được tải dưới LTW. Đây là **chương trình đầy đủ** với JDK 17+ và AspectJ compiler/weaver tương thích; không cần máy chủ ứng dụng.

### 7.1. Cấu trúc tệp

```text
project/
├── plugin-src/
│   └── demo/
│       └── Plugin.java
└── src-host/
    ├── HostMain.java
    ├── demo/
    │   └── TraceAspect.aj
    └── META-INF/
        └── aop.xml
```

**Tệp `plugin-src/demo/Plugin.java`:**

```java
package demo;

public class Plugin {
    public void work() {
        System.out.println("[business] work");
    }
}
```

**Tệp `src-host/demo/TraceAspect.aj`:**

```java
package demo;

public aspect TraceAspect {
    before(): execution(void demo.Plugin.work()) {
        System.out.println("[advice] work");
    }
}
```

**Tệp `src-host/META-INF/aop.xml`:**

```xml
<aspectj>
    <aspects>
        <aspect name="demo.TraceAspect"/>
    </aspects>
    <weaver>
        <include within="demo.Plugin"/>
    </weaver>
</aspectj>
```

**Tệp `src-host/HostMain.java`:**

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class HostMain {
    public static void main(String[] args) throws Exception {
        URL pluginUrl = Path.of("plugin-classes").toUri().toURL();
        URL[] pluginUrls = {pluginUrl};
        ClassLoader parent = HostMain.class.getClassLoader();

        try (URLClassLoader first =
                     new URLClassLoader("plugin-A", pluginUrls, parent);
             URLClassLoader second =
                     new URLClassLoader("plugin-B", pluginUrls, parent)) {

            Class<?> a = Class.forName("demo.Plugin", true, first);
            Class<?> b = Class.forName("demo.Plugin", true, second);

            Object objA = a.getDeclaredConstructor().newInstance();
            Object objB = b.getDeclaredConstructor().newInstance();

            a.getMethod("work").invoke(objA);
            b.getMethod("work").invoke(objB);

            System.out.println("same-name=" + a.getName().equals(b.getName()));
            System.out.println("same-class=" + (a == b));
            System.out.println("loader-A-owns=" + (a.getClassLoader() == first));
            System.out.println("loader-B-owns=" + (b.getClassLoader() == second));
        }
    }
}
```

**Điểm cố ý trong mã:**

- Parent là application loader của `HostMain`, nơi lưu aspect và `aop.xml`.
- Parent **không** có `demo.Plugin` trên classpath; bản bytecode này chỉ nằm trong `plugin-classes` để mỗi child tự định nghĩa.
- Mỗi `URLClassLoader` có tên và URL giống nguồn bytecode nhưng là đối tượng loader khác nhau.
- `getClassLoader()` dùng để kiểm tra defining loader; không dùng TCCL để suy ra class identity.
- Reflection gọi đúng một lần `work()` trên mỗi bản class, đủ để đếm advice mà không cần framework.

### 7.2. Biên dịch và chạy

Giả sử biến `ASPECTJ_HOME` trỏ đến bản AspectJ tương thích với JDK 17 và lệnh `ajc` đã có trong `PATH`. Từ thư mục `project/`, ví dụ trên shell Linux/macOS:

```bash
mkdir -p host-classes/META-INF plugin-classes
javac -d plugin-classes plugin-src/demo/Plugin.java
ajc -17 \
  -classpath "plugin-classes:$ASPECTJ_HOME/lib/aspectjrt.jar" \
  -d host-classes src-host/demo/TraceAspect.aj
javac -d host-classes src-host/HostMain.java
cp src-host/META-INF/aop.xml host-classes/META-INF/aop.xml

java \
  -javaagent:"$ASPECTJ_HOME/lib/aspectjweaver.jar" \
  -cp "host-classes:$ASPECTJ_HOME/lib/aspectjweaver.jar" \
  HostMain
```

Nếu cài AspectJ theo cấu trúc khác, điều chỉnh đường dẫn JAR theo môi trường. Tệp `aspectjweaver.jar` được cung cấp cho JVM agent; compiler `ajc` cần runtime JAR trên classpath biên dịch. Trên Windows, dấu phân cách classpath là `;`; việc copy và biến môi trường cũng phải thay theo PowerShell/cmd.

**Stdout nghiệp vụ dự kiến** (khi weaving thành công và bỏ qua các diagnostic riêng nếu môi trường bật verbose):

```text
[advice] work
[business] work
[advice] work
[business] work
same-name=true
same-class=false
loader-A-owns=true
loader-B-owns=true
```

Giải thích:

- Hai dòng `[advice] work` chứng minh advice chạy trên hai lần execution do **hai class runtime độc lập**.
- `same-name=true` nhưng `same-class=false` phản ánh Java class identity.
- Hai kiểm tra `loader-...-owns=true` xác nhận mỗi child là defining loader, do đó agent có thể áp dụng weaving tại ranh giới loader tương ứng.
- Nếu bốn dòng nhận dạng cuối vẫn đúng nhưng không có dòng `[advice]`, việc định nghĩa class đã thành công mà **LTW hoặc pointcut/aspect visibility** chưa được xác minh; xem mục chẩn đoán.

**Điểm kiểm thử quan trọng:** không cho `plugin-classes` vào `-cp` của lệnh chạy `HostMain`. Nếu vô tình đặt nó vào parent classpath, parent-first delegation có thể khiến cả A và B nhận *cùng class do parent định nghĩa*; bài kiểm thử nhiều loader sẽ không còn đúng.

### 7.3. Thử nghiệm phản chứng

1. **Tắt `-javaagent`:** cả hai child vẫn định nghĩa được `demo.Plugin` và in business, nhưng advice không chạy. Đây là dấu hiệu để tách lỗi cấu hình weaving khỏi lỗi classloading.
2. **Đưa `plugin-classes` vào classpath parent:** tùy thứ tự nạp, cả hai yêu cầu có thể được parent đáp ứng; `same-class` có thể thành `true` và kiểm tra ownership thành `false`. Không còn phép thử “mỗi child định nghĩa class”.
3. **Đặt aspect chỉ bên loader A:** B không đương nhiên nhìn thấy aspect A. Cần xét lại visibility, XML và đường đóng gói; không kết luận chỉ cần thêm một file XML ở B.
4. **Nạp class trước khi cấu hình aspect:** không kỳ vọng LTW chuẩn dệt hồi tố; tạo loader mới/nạp class mới với cấu hình đúng sẽ là phép thử rõ ràng hơn.

Ví dụ này minh họa kiến trúc, không có nghĩa mọi hệ thống plugin có khả năng đặt aspect ở parent. Thực tế phải tuân theo delegation policy, module descriptors, security constraints, classloader custom implementation và thứ tự transformer.

## 8. Thiết kế classpath và đóng gói nhiều plugin

### 8.1. Tách API chung khỏi implementation

Kiến trúc thường dùng:

```text
Shared parent loader
  ├── com.acme.api.PluginApi
  ├── com.acme.aspect.AuditAspect
  └── META-INF/aop.xml
        │
        ├── plugin-A loader → com.acme.pluginA.Worker
        └── plugin-B loader → com.acme.pluginB.Worker
```

API contract nằm ở shared parent giúp `PluginApi` chỉ có một danh tính class dùng chung. Các implementation nằm ở child để hỗ trợ thay thế, nạp lại và cách ly. Aspect có thể đặt tại parent nếu cần quan sát cả hai, với include pattern như `com.acme.pluginA..*` và `com.acme.pluginB..*` hoặc một namespace chung phù hợp.

Để plugin implement interface được chia sẻ, đừng đóng gói lại bản class `PluginApi` vào child theo cách child-first tự định nghĩa bản trùng. Nếu không, cùng một interface trên source có thể trở thành hai runtime types không assign được.

### 8.2. Tránh tạo hai bản runtime AspectJ không tương thích

Khi plugin đem theo `aspectjrt.jar` hoặc `aspectjweaver.jar` riêng, các loader có thể nhìn thấy bản khác nhau của các kiểu `org.aspectj.*`. Điều này tạo rủi ro version mismatch, linkage error và việc aspect tham chiếu runtime API khác với cái host đang dùng. Hãy xác định **ai sở hữu phiên bản weaver/runtime**, lớp nào thấy thư viện đó và có cần cô lập bản runtime riêng không.

Một giải pháp “thêm mọi JAR vào mọi classpath” có thể tạm chữa `ClassNotFoundException` nhưng phá isolation. Cần quản lý dependency visibility có chủ đích, đặc biệt khi plugin thay đổi độc lập.

### 8.3. Chú ý classpath so với JPMS module path

Java 9+ có thêm Java Platform Module System (JPMS). *Class loader visibility* và *module readability/exports/opens* là các ranh giới khác nhau. Có thể loader nhìn thấy class nhưng liên kết/truy cập phản chiếu bị chặn bởi module boundary. Với named module, cần kiểm tra module graph và yêu cầu export/open cụ thể của phần mềm, không mặc định LTW luôn vượt qua module encapsulation.

Trong một môi trường dùng module layer riêng cho từng plugin, cần xác định **layer**, **class loader**, **module readability** và **thời điểm instrumentation**. Đừng coi module layer là class loader hoặc cho rằng thêm `--add-opens` tùy tiện sẽ sửa mọi lỗi weaving.

## 9. Thứ tự khởi động và vòng đời class loader

Trình tự triển khai nên được thiết kế trước:

```text
(1) JVM khởi động + đăng ký Java agent
      ↓
(2) Shared aspect/runtime/config hiển thị
      ↓
(3) Khởi tạo child loader hoặc plugin container
      ↓
(4) Child loader đọc/ủy quyền cấu hình, chuẩn bị class
      ↓
(5) Bytecode class đích qua transformer/weaver
      ↓
(6) JVM defineClass → Class<?> trở thành class đã định nghĩa
      ↓
(7) Gọi phương thức, kiểm tra advice
      ↓
(8) Đóng loader, loại tham chiếu khi unload/redeploy
```

**Trạng thái “agent đã cài” không cho biết mọi bước sau đều đã xảy ra.** Một class có thể bị nạp do static initializer, reflection, dependency injection, service discovery, bytecode inspection hoặc cache của framework trước khi plugin init hoàn tất.

Với reload plugin:

- Loader mới định nghĩa class mới, dù tên và bytecode không đổi.
- Class và instance từ loader cũ không thể tự biến thành class/instance từ loader mới.
- Aspect đặt ở parent có thể giữ các tham chiếu đến class/instance/loader cũ trong static map, listener, thread, timer hoặc executor, làm loader cũ không unload được.
- `URLClassLoader.close()` giải phóng tài nguyên mở của loader (ví dụ JAR handle), **không đảm bảo class unloading** nếu vẫn còn reachable objects/threads/references.
- Không giữ `Class<?>` hoặc `Method` của child trong cache global vô hạn; sử dụng cache có lifecycle rõ ràng, weak references đúng chỗ và teardown các callback.

Việc class được dệt không cho phép đoán mức memory leak; phải quan sát heap dump, classloader instances còn sống, ThreadLocal và reference chains.

## 10. Quan sát, logging và xác minh theo từng loader

Để không đoán mò, kết hợp chứng cứ **từ JVM** và **từ weaver**.

### 10.1. Nhận diện loader của class và tài nguyên

Java 17 có thể dùng:

```java
Class<?> type = object.getClass();
ClassLoader defining = type.getClassLoader();
System.out.println(type.getName());
System.out.println(defining);
System.out.println(type.getModule());
```

Đoạn này chỉ có thể chạy trong ngữ cảnh đã có biến `object`. Nếu `getClassLoader() == null`, class thuộc bootstrap loader; không phải lỗi tự thân. Giá trị `toString()` của loader (đôi khi kèm hash) phù hợp log chẩn đoán, không nên dùng để khẳng định danh tính duy nhất thay cho so sánh tham chiếu hoặc mapping theo lifecycle.

Khi nghi ngờ `aop.xml`, kiểm tra việc enumeration tài nguyên với loader cụ thể:

```java
import java.net.URL;
import java.util.Enumeration;

public class ResourceProbe {
    public static void report(ClassLoader loader) throws Exception {
        Enumeration<URL> urls = loader.getResources("META-INF/aop.xml");
        while (urls.hasMoreElements()) {
            System.out.println(urls.nextElement());
        }
    }
}
```

Đây là lớp utility, chưa phải chương trình độc lập có `main()`. Kết quả là các resource URL **nhìn thấy qua loader**; nó không chứng minh tất cả đều đã được weaver sử dụng theo ý muốn. Cần đối chiếu log của agent. Với loader tùy biến, thứ tự enumeration và parent delegation có thể khác nhau.

### 10.2. Bật chẩn đoán AspectJ có mục tiêu

Ví dụ cấu hình tạm thời trong `META-INF/aop.xml`:

```xml
<aspectj>
    <aspects>
        <aspect name="demo.TraceAspect"/>
    </aspects>
    <weaver options="-verbose -debug -showWeaveInfo">
        <include within="demo.Plugin"/>
    </weaver>
</aspectj>
```

Các tùy chọn phục vụ mục đích khác nhau:

- `-verbose`: thông tin cấu hình/bootstrap của weaver.
- `-debug`: thêm thông tin xử lý class, kể cả weaving/exclusion/ignore theo phiên bản.
- `-showWeaveInfo`: thông tin khi class/advice được dệt.
- JVM `-Daj.weaving.verbose=true` có thể hữu ích để đưa một số thông báo bootstrap ra sớm, trước khi phân tích cấu hình.

Lưu ý hai tầng log: **weaver reports** cho thấy class nào được transform và aspect/advice nào được đăng ký; **application events** xác nhận đúng behavior trong thực thi. Một log báo weaver initialized chưa chứng minh mọi Plugin được weave; một dòng advice chưa chứng minh cả loader A/B đã được phủ.

### 10.3. Bảng kiểm chứng khi có hai child loader

| Kiểm tra | Loader A | Loader B | Cách xác minh |
| --- | --- | --- | --- |
| Class binary name | `demo.Plugin` | `demo.Plugin` | `Class.getName()` |
| Defining loader | A | B | So tham chiếu `getClassLoader()` với loader kỳ vọng |
| Có `aop.xml` nhìn thấy | Có/không | Có/không | `getResources("META-INF/aop.xml")` |
| Aspect nhìn thấy | Có/không | Có/không | Class/resource visibility và weaver registration |
| Class match include/exclude | Có/không | Có/không | Cấu hình + diagnostics |
| Advice được weave và thực thi | Có/không | Có/không | Weave info + test chạy phương thức |
| Class bị load sớm | Có/không | Có/không | Log classloading/agent startup |
| Loader unload được sau đóng | Đo riêng | Đo riêng | Heap analysis / lifecycle test |

Đừng chỉ báo “LTW đang chạy” ở mức JVM. Trong môi trường nhiều loader, kết luận có giá trị hơn là: *aspect X, configuration Y được nhìn thấy bởi loader A/B; class Z do loader đó định nghĩa, đã dệt; advice P chạy N lần trong workload cố định*.

## 11. Ma trận lỗi thường gặp và cách gỡ

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm chứng |
| --- | --- | --- |
| Có log agent khởi động nhưng không có advice | `aop.xml` không hiển thị, aspect chưa khai báo, include không match, class đã load trước | Xác minh resource, aspect list, weave info và timing. |
| Advice chạy ở plugin A nhưng không ở B | Aspect/config nằm riêng trong A; B có class loader sibling | So loader graph, `getResources` và registered aspects ở B. |
| Hai child nhưng chỉ một bản class được thấy | Parent đã định nghĩa target do parent-first delegation | Kiểm tra `a == b` và defining loader; bỏ target khỏi parent path khi muốn child ownership. |
| `ClassNotFoundException` / `NoClassDefFoundError` | Thiếu aspect/runtime/API trong loader visibility hoặc phụ thuộc của class | Kiểm tra binary name, dependency graph, classpath và loader links. |
| `ClassCastException` giữa hai bản class cùng tên | Different defining loaders | Chia sẻ interface/API ở parent hoặc dùng boundary serialization/adaptation. |
| `LinkageError` / verifier error | Bytecode transform conflict, trùng type khác loader, runtime version mismatch | Chốt exact exception, dump class, kiểm tra version/transformer order. |
| Aspect không áp dụng cho class core | Class được định nghĩa bởi loader parent/bootstrap, hoặc bị loại bởi weaver rules | Xác định defining loader, kiểm tra supported scope/exclusions. |
| Weaving chỉ hiệu lực sau restart | Class đã được định nghĩa từ trước khi cấu hình mới có hiệu lực | Đảm bảo agent/config sớm; thử loader mới và restart có kiểm soát. |
| Redeploy plugin làm tăng heap | Static cache/aspect parent giữ class/instance/loader cũ | Heap dump, threads, listeners, ThreadLocal, teardown. |
| Chậm khởi động/plugin loading | Too-broad `include`, debug logging, transform nhiều class | Giới hạn type pattern, đo class count và thời gian load. |

### Quy trình gỡ lỗi theo thứ tự

1. **Xác định đối tượng:** ghi class binary name, class loader thực tế, module và đường JAR của class đích.
2. **Xem graph loader:** ai là parent, có child-first không, class đã được parent định nghĩa chưa?
3. **Kiểm tra tài nguyên:** `META-INF/aop.xml` nào thực sự được loader thấy; có nhiều bản trùng không?
4. **Kiểm tra aspect:** aspect class có trong loader hoặc parent, runtime API tương thích và được khai báo trong XML chưa?
5. **Kiểm tra thời điểm:** Java agent có được kích hoạt từ JVM startup, trước khi class đích được định nghĩa?
6. **Kiểm tra chọn class:** include/exclude có thực sự chứa target class, có namespace viết đúng không?
7. **Kiểm tra join point:** advice pointcut loại `execution/call` có phù hợp thân phương thức hoặc call site được dệt không?
8. **Bật weave info tạm thời:** đối chiếu từng loader/class, thay vì dựa vào stdout nghiệp vụ duy nhất.
9. **Chạy case tối giản:** một phương thức ở A, một ở B; xác định số advice mong đợi rồi so sánh.
10. **Đánh giá lifecycle:** khi plugin reload, class cũ có còn bị giữ bởi aspect/static cache/thread không?

Nếu đã có nhiều agent chuyển đổi bytecode, ghi rõ **thứ tự transformer**, phạm vi class, phiên bản và biến đổi nào được thực hiện. Bytecode từ transformer trước có thể là đầu vào cho transformer sau; thứ tự có thể quan trọng và gây ra lỗi không xuất hiện ở môi trường chỉ có một agent.

## 12. Những giới hạn kỹ thuật phải tôn trọng

### 12.1. Không phải mọi class đều có thể weave bằng một cấu hình

Theo tài liệu LTW AspectJ, một số namespace hạ tầng như `org.aspectj.*` và các class nền tảng `java.*`, `javax.*` thuộc nhóm không được expose cho LTW của chính AspectJ, bất kể include. Cũng cần phân biệt: có thể weave một **call join point** nằm trong class ứng dụng được dệt khi nó gọi API nền tảng, nhưng điều đó không đồng nghĩa bytecode của class nền tảng đã bị dệt.

### 12.2. Loader tự viết có thể có hành vi đặc biệt

Các loader custom có thể kiểm soát `findClass`, parent delegation, URL/resource visibility, package sealing, bytecode generation và cách nạp JAR. Không mặc định `URLClassLoader` trong ví dụ bao phủ mọi plugin framework. Nếu loader tạo lớp động hoặc không cung cấp resource thông thường, cần kiểm tra agent/weaver thực sự nhận bytecode nào.

### 12.3. Class initialization khác với class definition

`Class.forName(name, true, loader)` yêu cầu nạp/khởi tạo class theo ngữ nghĩa API, nhưng quan trọng hơn cho LTW là **lớp được định nghĩa lúc nào**. Class có thể được define trước khi static initializer chạy hoặc trước lần gọi phương thức đầu tiên. Do đó “chưa gọi method lần nào” không chứng minh class còn cơ hội được LTW dệt.

### 12.4. Nạp lại và dệt lại là hai vấn đề khác nhau

Class loader mới có thể định nghĩa lại class cùng tên như một **runtime identity mới**, khiến LTW có cơ hội xử lý bytecode khi nạp. Đó không phải là weave lại **Class<?> đã tồn tại**. AspectJ cũng có khái niệm reweavable bytecode trong một số pipeline; không coi đó là quyền sửa mọi class đã định nghĩa trong JVM theo thời gian thực.

### 12.5. Resource lookup và security

Tệp XML hiển thị cho một loader không có nghĩa aspect class, package access và quyền thao tác đều hợp lệ. Khi có giới hạn module/security hoặc classpath không đồng nhất, có thể xuất hiện failure khi resolve aspect hoặc verify class. Không “chữa” bằng cách đưa tất cả lớp của mọi plugin lên shared parent, vì cách đó có thể làm mất isolation của plugin.

## 13. Hiệu năng, cô lập và vận hành lâu dài

LTW ảnh hưởng không chỉ latency của advice mà cả **thời gian tải class** và tài nguyên:

- Mỗi class được dệt có chi phí phân tích/biến đổi bytecode lúc nạp; khởi động nhiều plugin có thể đẩy chi phí về giai đoạn loading.
- Weaver cần tìm/đọc cấu hình và resolve aspect cho các loader liên quan; nhiều aop.xml visible hoặc classpath rộng làm chẩn đoán phức tạp hơn.
- Include/exclude rộng có thể đưa class thư viện không cần thiết vào phạm vi xử lý; nên dùng pattern giới hạn theo package/type đã xác nhận.
- Advice chạy trên đường nóng có thể phát sinh overhead CPU, allocation và logging; vấn đề này độc lập với thời điểm weaving.
- Khi có nhiều loader định nghĩa cùng các tên class, số bản class và metadata runtime tăng; thêm cache/static reference có thể khiến loader không unload.
- Một aspect chung chứa mutable state phải đảm bảo thread safety và isolation; per-loader class identity **không tự cô lập** một aspect singleton nằm ở parent.
- Khi cần zero-downtime redeploy, chạy kiểm thử tạo/đóng loader nhiều lần và quan sát class count, live loader count, heap, threads và callbacks.

### Tiêu chí chấp nhận khi đưa vào môi trường thật

- [ ] Agent/weaver và version chạy đúng từ startup.
- [ ] Danh tính class loader cho từng module/plugin được ghi nhận.
- [ ] Aspect class/runtime/aop.xml nhìn thấy ở đúng loader scope.
- [ ] Include/exclude chỉ chọn những class mong muốn; không vô tình chạm core dependency.
- [ ] Test cho mỗi child loader chứng minh advice khớp và không khớp theo dự kiến.
- [ ] Thời điểm class definition được xác minh; không phụ thuộc cấu hình bổ sung quá muộn.
- [ ] Đã thử nested calls, exception, concurrency và classloader reload khi có liên quan.
- [ ] Metrics về startup time, class loading, heap và advice latency ở mức phù hợp.
- [ ] Lifecycle của plugin không bị aspect/global cache/thread giữ tài nguyên cũ.
- [ ] Có kế hoạch tắt/bật LTW và tái hiện vấn đề bằng cấu hình cố định để rollback.

## 14. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — class identity.** Loader A và B có cùng URL chứa `demo.Plugin.class`, nhưng parent không chứa class này. Cả hai dùng parent-first và gọi `Class.forName(..., true, loader)` riêng. Hai `Class<?>` chắc chắn là cùng đối tượng không?

**Đáp án:** không. Nếu mỗi child tự định nghĩa lớp, hai đối tượng `Class<?>` khác nhau dù cùng tên và bytecode. Phải kiểm tra defining loader thực tế.

**Bài 2 — parent class.** Plugin A muốn advice tác động lên `com.acme.SharedApi` đã được Application loader định nghĩa. Chỉ thêm `SharedApi` vào include của aop.xml nằm trong plugin A có đủ không?

**Đáp án:** không. Loader A không thể weave class mà parent đã định nghĩa. Cần thiết kế việc weave đúng loader và đúng thời điểm class được định nghĩa; không tạo bản trùng API chỉ để lách hạn chế này.

**Bài 3 — sibling visibility.** Aspect được định nghĩa chỉ trong PluginLoader-A, còn target nằm ở PluginLoader-B. Theo mô hình loader sibling độc lập, B có tự nhìn thấy aspect không?

**Đáp án:** không. B thông thường chỉ thấy class do nó định nghĩa hoặc do parent/delegate phù hợp, chứ không tự nhìn thấy sibling A. Muốn chia sẻ aspect, tổ chức classloader graph/đóng gói có chủ đích.

**Bài 4 — cấu hình thấy nhưng advice không chạy.** `getResources("META-INF/aop.xml")` trả về URL đúng, nhưng gọi `work()` không thấy advice. Hãy kể ít nhất ba nguyên nhân.

**Đáp án:** aspect chưa được khai báo/resolve; class bị exclude hoặc không match pointcut; class đã load trước khi weaving; hoặc agent không transform class được loader định nghĩa. Chứng cứ cần thêm là log weave info, class identity và thứ tự load.

**Bài 5 — reload.** Đã gọi `close()` trên URLClassLoader nhưng heap vẫn giữ nhiều class của plugin cũ. Có thể kết luận `close()` thất bại không?

**Đáp án:** không. `close()` không bắt buộc unload class ngay; phải kiểm tra các tham chiếu còn tồn tại, chẳng hạn static cache ở parent aspect, live threads, ThreadLocal, listener hoặc objects/plugin instances.

**Bài 6 — aop.xml.** Trong XML có `<weaver><include within="com.acme..*"/></weaver>` nhưng không có `<aspects><aspect name="..."/></aspects>`. Có thể coi `include` tự khám phá và kích hoạt mọi aspect trên classpath không?

**Đáp án:** không. `include` ở phần `weaver` giới hạn type để dệt; aspect cần được khai báo theo cơ chế cấu hình tương ứng.

## 15. Kết luận và tài liệu tham khảo

Triển khai LTW trong nhiều class loader không chỉ là việc thêm `-javaagent`. Kết quả phụ thuộc vào **loader thực sự định nghĩa class**, **aspect/config có hiển thị đúng ranh giới hay không**, và **weaver đã sẵn sàng trước class definition chưa**. Kết hợp ba điều kiện đó với pointcut đủ chính xác, kiểm chứng độc lập trên từng loader và quản lý lifecycle sẽ giúp triển khai AOP linh hoạt mà vẫn duy trì isolation.

Tài liệu đọc thêm:

- [AspectJ Development Guide — Load-Time Weaving](https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html): khái niệm, ba quy tắc class loader, cấu hình, agent và giới hạn LTW.
- [AspectJ — Load-Time Weaving Requirements](https://eclipse.dev/aspectj/doc/released/devguide/ltw-rules.html): aspect visibility và ranh giới class loader.
- [AspectJ — Dumping classes during LTW](https://eclipse.dev/aspectj/doc/released/pdguide/ltwdump.html): lấy bytecode trước/sau weaving để phân tích lỗi khó.
- [JDK 17 API — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation, defining loader và class-loading contract.
- [JDK 17 API — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): API loader dùng trong ví dụ và lifecycle `close()`.
