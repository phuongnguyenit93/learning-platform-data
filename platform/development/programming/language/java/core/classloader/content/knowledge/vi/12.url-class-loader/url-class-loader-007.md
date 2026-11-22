# URLClassLoader.close() không đồng nghĩa với gỡ bỏ lớp đã nạp

`URLClassLoader` có thể tìm và định nghĩa các lớp từ thư mục hoặc JAR theo một tập URL. Vì class loader này triển khai `Closeable`, ta có thể gọi `close()` hoặc dùng `try-with-resources`. Nhưng **đóng loader không phải lệnh “gỡ tất cả class khỏi JVM”**, không hủy các object đã tạo, không reset static field và không ép garbage collector thu hồi class metadata.

Tài liệu Java SE 17 quy định rõ: sau `URLClassLoader.close()`, loader không còn dùng được để **định nghĩa lớp mới từ nguồn URL của chính nó**, nhưng **các lớp và tài nguyên đã được nạp vẫn có thể truy cập**, và các lớp/tài nguyên do parent định nghĩa vẫn truy cập theo delegation. Mặt khác, **class unloading** là cơ chế quản lý bộ nhớ của JVM, chỉ có thể xảy ra khi defining class loader đủ điều kiện được GC thu hồi; ngay cả khi đủ điều kiện, JVM **không cam kết phải unload ngay**.

Bài thuộc chủ đề **URLClassLoader** trong Java core – classloader. Trọng tâm là phân biệt **close / ngừng nạp mới / class unloading / giải phóng toàn bộ plugin**, quan sát hành vi Java 17+ bằng ví dụ chạy được, hiểu các tham chiếu giữ class loader sống, và thiết kế vòng đời plugin tránh lỗi khóa JAR, memory leak hoặc truy cập phụ thuộc sau khi đóng.

## 1. Ba hành động thường bị đánh đồng

| Hành động | Điều gì thực sự xảy ra? | Điều gì KHÔNG được bảo đảm? |
| --- | --- | --- |
| **`URLClassLoader.close()`** | Đóng tài nguyên do URL loader mở, nhất là các file/JAR phù hợp; ngừng tìm/định nghĩa **class và resource mới từ các URL của chính loader** | Không unload class đã định nghĩa; không hủy object, thread, static state hay mọi handle do plugin tự mở |
| **Bỏ tham chiếu Java đến loader và class/plugin** | Có thể khiến loader và các lớp được nó định nghĩa trở nên đủ điều kiện cho GC | Không đảm bảo GC chạy, loader được thu hồi hay class được unload ngay |
| **Class unloading** | JVM có thể thu hồi metadata/class-related state của class khi defining loader có thể bị GC thu hồi | Không phải API Java gọi trực tiếp theo tên class; không thể yêu cầu unload tùy ý trong một loader còn sống |

**Một câu để nhớ:** `close()` là **kết thúc hoạt động tìm tài nguyên từ các URL của loader và giải phóng những handle thuộc loader**; còn **unloading** phụ thuộc trạng thái sống của toàn bộ đồ thị object/Class/ClassLoader và quyết định của JVM.

`URLClassLoader` là một `ClassLoader` cụ thể. Không phải mọi subclass của `ClassLoader` đều có phương thức `close()` hay cơ chế đóng tài nguyên giống URLClassLoader.

## 2. JavaDoc Java 17 nói chính xác gì về `close()`?

Chữ ký API:

```java
public void close() throws IOException
```

Các bảo đảm/cảnh báo quan trọng trong Java SE 17:

1. **Không còn nạp mới từ nguồn do loader định nghĩa.** Các lớp/tài nguyên mới mà loader phải tự tìm trong URL search path sẽ không được cung cấp sau close.
2. **Class/resource đã được nạp vẫn truy cập được.** Đặc biệt, `Class<?>`, method đã resolve, object đã tạo và static state không tự “biến mất” vì close.
3. **Parent delegation vẫn hoạt động.** Một class được bootstrap/platform/system parent định nghĩa không bị vô hiệu vì child URL loader đóng.
4. **Đóng file đã mở qua URL của loader.** Với các URL dạng `jar:` hoặc `file:` phù hợp, API cố gắng đóng những file/JAR mà loader đã mở trong quá trình tìm class/resource.
5. **Nếu thread khác đang nạp class đồng thời với close, kết quả của lần nạp đang diễn ra không được xác định.** Không dùng `close()` như cơ chế đồng bộ an toàn để “hủy” class loading đang chạy.
6. **Đóng lặp lại không có tác dụng bổ sung.** Gọi close trên loader đã closed không phải lỗi chỉ vì gọi lại.
7. **Có thể ném `IOException`.** Loader cố đóng những file đã mở; nếu có nhiều lỗi I/O, ngoại lệ bổ sung được đính kèm dạng suppressed exceptions. Những unchecked exceptions/errors không được cam kết bị bắt.

Từ các quy tắc trên, câu sau là **sai**:

> “Đã gọi `loader.close()` rồi, chắc chắn không còn method nào thuộc class plugin chạy được nữa.”

Đóng loader **không** chặn CPU thực thi bytecode vốn đã được nạp và đã liên kết. Nó cũng không phát một sự kiện cưỡng bức “destroy all instances”. Bên ngoài còn giữ `Class<?>` hoặc object plugin thì code cũ vẫn có thể chạy.

Cũng tránh khẳng định điều ngược lại quá mức: **mọi phương thức của class cũ đều tiếp tục chạy tốt sau close**. Một phương thức đã nạp có thể **lần đầu cần resolve/nạp thêm một class phụ thuộc** khi được gọi về sau. Nếu dependency ấy chỉ có trong URL của loader đã đóng, lời gọi có thể thất bại dù bản thân method/class ban đầu đã nạp trước close.

## 3. Ví dụ Java 17+ đã chạy kiểm chứng: class cũ vẫn sử dụng được

Ví dụ sau tự chạy bằng JDK 17+ và cố ý tách output của host khỏi output của plugin. Không thêm thư mục plugin vào classpath của host.

### 3.1 Cấu trúc

```text
url-close-demo/
├── source/
│   └── plugin/
│       ├── Hello.java
│       └── NotYet.java
├── CloseDemo.java
├── plugins/       (output .class riêng của plugin)
└── host/          (output của host)
```

Tạo các thư mục nếu chưa tồn tại. `plugins` không được đưa vào `-cp` khi chạy `CloseDemo`, vì ta muốn class của plugin chỉ có thể được tìm qua `URLClassLoader` riêng.

### 3.2 Hai class của plugin

File `source/plugin/Hello.java`:

```java
package plugin;

public class Hello {
    public String message() {
        return "still alive";
    }
}
```

File `source/plugin/NotYet.java`:

```java
package plugin;

public class NotYet {
    public static String value() {
        return "new";
    }
}
```

`Hello` sẽ được load **trước** khi đóng. `NotYet` vẫn có file `.class` tồn tại trong cùng thư mục URL, nhưng **không được yêu cầu load trước close**.

### 3.3 Host tạo rồi đóng URLClassLoader

File `CloseDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.lang.reflect.Method;

public class CloseDemo {
    public static void main(String[] args) throws Exception {
        URL[] urls = {
            Path.of("plugins").toUri().toURL()
        };

        URLClassLoader loader = new URLClassLoader(
                urls, ClassLoader.getPlatformClassLoader());

        Class<?> cls = loader.loadClass("plugin.Hello");
        Object obj = cls.getDeclaredConstructor().newInstance();
        Method message = cls.getMethod("message");

        System.out.println("before close: " + message.invoke(obj));

        loader.close();

        System.out.println("after close: " + message.invoke(obj));
        System.out.println("same cached class: "
                + (loader.loadClass("plugin.Hello") == cls));
        System.out.println("parent class: "
                + (loader.loadClass("java.lang.String") == String.class));

        try {
            loader.loadClass("plugin.NotYet");
            System.out.println("unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("new plugin class: not found");
        }
    }
}
```

Vì `CloseDemo` chỉ dùng reflection để truy cập `plugin.Hello`, nó **không cần import/biên dịch phụ thuộc trực tiếp** vào class plugin. `ClassLoader.getPlatformClassLoader()` làm parent để JDK classes vẫn có thể được delegate tới nền tảng, nhưng không cung cấp `plugin.Hello`.

### 3.4 Biên dịch và chạy

Từ thư mục `url-close-demo`, tạo output directories `plugins` và `host` rồi chạy:

```bash
javac --release 17 -d plugins source/plugin/Hello.java source/plugin/NotYet.java
javac --release 17 -d host CloseDemo.java
java -cp host CloseDemo
```

Ví dụ trên đã được kiểm chứng bằng `javac --release 17` và chạy trên JVM tương thích. Stdout:

```text
before close: still alive
after close: still alive
same cached class: true
parent class: true
new plugin class: not found
```

### 3.5 Giải thích từng dòng

- **`before close: still alive`:** `loader.loadClass("plugin.Hello")` tìm class file trong `plugins`, rồi host tạo một instance và gọi method qua reflection.
- **`after close: still alive`:** object, `Class<?>` và `Method` vẫn còn tham chiếu hợp lệ. `close()` không phá hủy chúng; method đã sẵn sàng vẫn chạy.
- **`same cached class: true`:** với cơ chế `loadClass` mặc định, class mà loader đã khởi đầu nạp có thể được tìm lại qua `findLoadedClass`, ngay cả khi URL search path đã đóng. Đừng hiểu close là xóa class cache.
- **`parent class: true`:** loader đã đóng vẫn có thể nhờ parent tìm `java.lang.String`, là class nền tảng không do plugin loader định nghĩa.
- **`new plugin class: not found`:** `plugin.NotYet.class` tồn tại trong thư mục `plugins` nhưng URL loader đã closed, không còn tìm/định nghĩa mới từ URL ấy. Vì parent cũng không có class này, ta nhận `ClassNotFoundException`.

Ví dụ cố ý gọi `loader.loadClass("plugin.Hello")` sau close để chứng minh class đã load còn truy cập được. **Không xây kiến trúc dựa trên việc tiếp tục dùng một loader đã đóng như loader bình thường**; hãy coi nó đã hết nhiệm vụ nạp mới.

### 3.6 Vì sao chưa đủ kết luận class đã bị unload?

Trong ví dụ, `loader`, `cls`, `obj` và `message` vẫn còn tham chiếu sống trong method. Đặc biệt, chính chương trình đang tiếp tục sử dụng chúng. Class `plugin.Hello` không bị unload chỉ vì close, và **không có bất kỳ kiểm tra GC nào** trong ví dụ. Nó minh họa **khả năng tiếp tục dùng class cũ**, không đo thời gian sống metadata sau khi chương trình kết thúc.

## 4. Điểm tinh tế: một class đã nạp vẫn có thể cần class chưa nạp

JVM không nhất thiết resolve tất cả symbolic references của một class cùng một lúc. Resolution có thể được thực hiện khi cần. Xét ví dụ **minh họa cơ chế**, không phải một file chạy độc lập:

```java
package plugin;

public class Entry {
    public void execute() {
        Dependency.run();
    }
}
```

Nếu `Entry` đã được load trước close nhưng `Dependency` chưa được loader tìm/resolve, lần đầu gọi `execute()` sau close có thể cần nạp `plugin.Dependency`. Lúc đó, việc loader không còn đọc được URL path có thể dẫn đến lỗi linking như `NoClassDefFoundError` hoặc `ClassNotFoundException` được báo trong ngữ cảnh cụ thể. JVM có quyền resolve sớm hơn, nên **không nên dựa vào một thời điểm duy nhất được bảo đảm cho mọi dependency**.

Vì thế hai khẳng định khác nhau:

- **Class đã nạp vẫn có thể sử dụng sau close.** Được JavaDoc bảo đảm ở mức class/resource đã có.
- **Mọi đường thực thi của mọi class đã nạp đều luôn thành công sau close.** Không được bảo đảm vì có thể còn lazy loading/resolution, resource lookup hoặc nghiệp vụ sử dụng file/JAR sau đó.

Một ví dụ thực tế: class plugin được nạp sớm nhưng chỉ đến lần xử lý request thứ 100 mới tạo thêm formatter/codec tùy chọn. Nếu URL loader bị đóng ngay sau bootstrap, chức năng tùy chọn có thể hỏng trong tương lai dù test startup không phát hiện.

## 5. Loading, initialization, close và unloading là bốn thời điểm khác nhau

Để không nhầm trong sơ đồ vòng đời, tách thành các sự kiện:

```text
Tạo URLClassLoader
       |
       v
Tìm Class<?> từ URL / parent
       |
       v
Loading + Linking (theo nhu cầu)
       |
       v
Initialization <clinit> (khi JVM có thao tác yêu cầu)
       |
       v
Object / method / static state được sử dụng
       |
       +------------> URLClassLoader.close()
       |                    |
       |                    +--> đóng handle của loader
       |                    +--> dừng tìm mới từ URL của loader
       |                    +--> KHÔNG tự unload class
       |
       v
Ngừng tác vụ, đóng tài nguyên riêng, loại bỏ các tham chiếu giữ plugin
       |
       v
Defining loader có thể không còn reachable
       |
       v
GC có thể thu hồi loader và unload các class do nó định nghĩa
       (thời điểm không được JVM cam kết)
```

**Loading** tạo/đưa class definition vào JVM. **Initialization** chạy static initializers khi JVM yêu cầu. **`close()`** đóng những nguồn/handle do loader sở hữu. **Unloading** là tối ưu quản lý bộ nhớ khi điều kiện GC phù hợp. Không có quan hệ “gọi close ⇒ ngay sau đó static field trở về `null` hoặc `0`”.

`java.lang.Class` và defining loader có quan hệ bản sắc runtime: cùng một binary name nhưng được hai loader khác nhau **tự định nghĩa** là hai kiểu riêng, với static state riêng. Vì thế khi cần reload version mới, cách thông thường là **tạo loader mới**, không mong instance `URLClassLoader` cũ “quên lớp” đã nạp.

## 6. Điều kiện class unloading trong JLS 17

Java Language Specification `12.7 nói rằng JVM **có thể** unload class/interface nếu và chỉ nếu **defining class loader của nó có thể được garbage collector thu hồi**. Các class được bootstrap loader nạp không thuộc diện unloading theo quy tắc này.

Diễn giải thực tế:

- Nếu một class do plugin loader định nghĩa vẫn có object instance sống hoặc `Class<?>` đang được giữ, metadata/class-loader graph thường chưa đủ điều kiện thu hồi.
- Nếu app/container vẫn giữ **tham chiếu mạnh tới plugin loader**, trực tiếp hoặc gián tiếp, loader không được GC thu hồi nên các class do nó định nghĩa cũng không thể unload.
- Nếu **mọi đường tham chiếu mạnh liên quan** đã được giải phóng, class và loader *có thể* đủ điều kiện, nhưng JVM không bắt buộc chạy GC hoặc unload theo yêu cầu ứng dụng.
- Việc một variable local được gán `null` không đủ để chứng minh graph không còn tham chiếu; class objects, instances, method handles, threads, stacks và native roots có thể còn giữ.
- Class do **bootstrap** định nghĩa như `java.lang.String` không được unload theo JLS 12.7, bất kể một URL loader con đã closed bao nhiêu lần.

**Đúng:** “Sau khi dừng plugin và bỏ toàn bộ strong references liên quan, JVM có thể unload class do loader plugin định nghĩa.”

**Sai:** “`loader = null; System.gc();` sẽ chắc chắn giải phóng ngay mọi class plugin.”

`System.gc()` là yêu cầu/hint tới runtime theo chính sách GC; nó không có hợp đồng bảo đảm unload class ngay hoặc trong một khoảng thời gian nhất định. Cũng không nên xây business logic dựa trên kết quả kiểm tra WeakReference thành `null` ở một mốc thời gian tùy ý.

## 7. Điều gì giữ class loader sống sau close?

Một loader có thể được giữ alive qua nhiều đường. Những nguồn giữ tham chiếu thường gặp ở ứng dụng plugin/app server:

| Nguồn giữ | Ví dụ | Cách xử lý khi dừng plugin |
| --- | --- | --- |
| **Instance plugin** | Host cache giữ `Object plugin` hoặc interface implementation | Loại bỏ khỏi registry/cache; không giữ object sống quá vòng đời |
| **`Class<?>` / reflection** | `Map<String, Class<?>>`, `Method`, `Constructor`, `MethodHandle` | Gỡ metadata/cache gắn với deployment cũ |
| **Thread context class loader** | Thread pool worker còn `setContextClassLoader(pluginLoader)` | Khôi phục TCCL cũ bằng `finally` trong task; kiểm tra worker sống lâu |
| **Thread do plugin tạo** | Thread đang chạy mã plugin và giữ runnable/task class | Yêu cầu dừng, ngắt/chờ có kiểm soát trước close; tránh thread vô hạn |
| **`ThreadLocal` / inheritable context** | Thread pool giữ value do plugin định nghĩa | Xóa đúng nơi tạo; cân nhắc scope task và thread reuse |
| **Static registry ở host** | Event listener, callback, scheduler, SPI cache | Hủy registration, `remove` listener và cache entries |
| **ServiceLoader/cache provider** | Cache host giữ provider instances/classes | Dọn cache/scope theo deployment; tạo lại context phù hợp |
| **Shutdown hooks** | Hook thread/runnable của plugin được đăng ký với runtime | Gỡ hook khi được phép và khi chưa bắt đầu shutdown |
| **JMX/MBean, logging, JDBC, driver registry** | Provider hoặc listener còn đăng ký trong subsystem sống lâu | Unregister/close theo API subsystem |
| **Native/JNI refs, task stacks** | Code vẫn chạy hoặc bridge giữ object/class | Dừng tác vụ an toàn và giải phóng các refs do native code quản lý |

Một điều dễ quên: **close và unload không giải quyết nhau theo thứ tự ngược**. Muốn dừng plugin an toàn thường phải **ngăn yêu cầu mới**, hoàn tất/hủy các công việc đang chạy, đóng tài nguyên do plugin sở hữu, **sau đó mới close loader**, rồi loại bỏ những tham chiếu cuối cùng. Nếu còn thread đang load class trong khi `close()`, JavaDoc nói kết quả load đồng thời ấy không xác định.

### Vì sao static field trong plugin cũng cần xem xét?

Static field thuộc class của plugin có thể giữ các object khác, bao gồm thread/task/registry. Nhưng chỉ riêng một vòng tham chiếu **bên trong cụm object không còn reachable** không tự ngăn garbage collector: GC thông thường có thể thu hồi các vòng không được root tham chiếu. Nguy hiểm thật sự nằm ở **đường tham chiếu từ một GC root hoặc đối tượng sống lâu bên ngoài plugin** tới object/class/loader của plugin.

Vì vậy, không kết luận “có static cache trong plugin ⇒ chắc chắn leak vĩnh viễn”. Hãy phân tích **có đường strong reference từ root tới loader hay không**.

## 8. WeakReference có chứng minh loader đã unload chưa?

Có thể dùng `WeakReference<ClassLoader>` để quan sát tương đối việc một loader còn được strong-reference giữ hay đã có cơ hội được thu hồi. Nhưng phải hiểu giới hạn:

```java
java.lang.ref.WeakReference<ClassLoader> reference =
        new java.lang.ref.WeakReference<>(loader);

// Chỉ sau khi đã dừng plugin, loại bỏ tất cả strong references
// và thoát khỏi scope còn giữ loader:
loader = null;

System.gc(); // Không bảo đảm GC chạy hoặc thu hồi loader ngay.
System.out.println(reference.get());
```

Đây là **đoạn minh họa**, không phải chương trình kiểm chứng unload độc lập. `reference.get()` có thể vẫn không null vì loader đang reachable hoặc đơn giản vì GC chưa diễn ra. Nếu `get()==null`, ta có bằng chứng weak referent loader đã bị clear; điều đó **không phải API cam kết thời điểm mọi class metadata được thu hồi**, cũng không đủ thay thế công cụ đo metaspace và class-unload logs.

Một lỗi test phổ biến là giữ `Class<?> klass` hoặc instance plugin trong biến local/static để “kiểm tra đã unload chưa”. Chính các tham chiếu đó có thể giữ class/loader sống. Test đáng tin hơn thường tạo và dùng loader trong **method scope riêng**, chỉ trả weak reference ra ngoài, đồng thời dọn hết registry/TCCL/resource theo vòng đời.

Khi điều tra thực tế, có thể quan sát:

```bash
java -Xlog:class+unload=info -cp host CloseDemo
```

Cú pháp logging trên dành cho các HotSpot JVM hỗ trợ unified logging, và output phụ thuộc sự kiện GC thực tế. **Không thấy log unload không chứng minh `close()` bị lỗi**; chương trình có thể chưa đủ điều kiện, chưa có GC/unloading, hoặc đã kết thúc quá sớm.

Có thể phối hợp `jcmd` và heap dump/classloader statistics tùy JDK/runtime để tìm **retaining paths**. Không sử dụng `-Xlog:class+load=info` như bằng chứng class đã unload: `load` và `unload` là hai loại sự kiện khác nhau.

## 9. `close()` có giải phóng khóa JAR không?

Một lý do thực tiễn để dùng `URLClassLoader.close()` là **giải phóng những JAR/file handles loader đã mở**. Trên Windows, file đang bị process giữ handle có thể khiến thay, xóa hoặc cập nhật JAR thất bại; đóng URLClassLoader theo contract là bước quan trọng khi undeploy/redeploy plugin.

Nhưng các phát biểu sau **không** tương đương:

- **Đã close URL loader:** loader cố đóng file/JAR thuộc tài nguyên mà chính nó mở theo contract.
- **Chắc chắn mọi stream, socket, DB connection và thread của plugin đều được đóng:** không. Plugin có thể tự mở chúng bên ngoài URLClassLoader.
- **Chắc chắn thao tác ghi đè/xóa JAR trên mọi OS đều thành công:** không. Handle có thể do thành phần khác giữ, hoặc chính `close()` ném `IOException`.
- **Có thể tiếp tục đọc mọi resource sau close:** không bảo đảm. Resource đã nạp/truy cập có thể còn sẵn, nhưng stream do loader theo dõi có thể bị đóng trong quá trình close; nguồn URL đã closed không còn phục vụ resource mới theo cách thường.

Nếu mã plugin gọi `URLClassLoader.getResourceAsStream()`, URL loader có thể theo dõi các stream tương ứng để đóng khi loader closed. Nếu plugin trực tiếp mở `FileInputStream`, `Socket`, `JarFile` hoặc dùng thư viện JNI, những tài nguyên đó **không tự thuộc vòng đời close của URLClassLoader**.

**Quy tắc quản lý tài nguyên:** tài nguyên nào do code nào mở thì nên được code đó **đóng theo hợp đồng riêng**, trừ khi tài liệu API nói rõ quyền sở hữu và trách nhiệm được chuyển giao.

### Xử lý `IOException` khi close

Ví dụ an toàn khi một tác vụ thực sự chỉ cần nạp/đọc class từ loader trong một phạm vi:

```java
URL[] urls = {Path.of("plugins").toUri().toURL()};

try (URLClassLoader loader = new URLClassLoader(
        urls, ClassLoader.getPlatformClassLoader())) {
    // Chỉ làm những thao tác cần class và resource từ URLs.
    Class<?> type = loader.loadClass("plugin.Hello");
    System.out.println(type.getName());
} // loader.close() được gọi; IOException có thể được truyền ra.
```

Đây là **đoạn minh họa**, cần đặt trong method có `throws Exception` hoặc xử lý các checked exceptions. `try-with-resources` cũng có thể lưu lỗi đóng tài nguyên thành suppressed exception nếu phần body đã ném lỗi khác.

Cẩn thận: dùng `try-with-resources` cho loader plugin **ngay trong factory** rồi trả về instance plugin để host dùng nhiều giờ là thiết kế rủi ro. Sau khi factory trả về, loader đã closed; object cũ có thể dùng được ở một số đường code, nhưng lazy dependency loading hoặc resource lookup về sau có thể hỏng.

## 10. Vòng đời plugin đúng: stop trước, close sau, release references cuối cùng

Một plugin host có thể dùng vòng đời khái niệm:

```text
CREATED
   |
   v
LOADING/STARTING
   |
   v
RUNNING
   |
   +-- ngừng tiếp nhận công việc mới
   |
   v
STOPPING
   |
   +-- hoàn tất/hủy task đang chạy
   +-- xóa thread context loader tạm thời
   +-- unregister listeners / scheduled tasks
   +-- plugin.stop(): đóng tài nguyên riêng
   +-- gỡ provider/cache/registry của host
   |
   v
CLOSING_LOADER
   |
   +-- URLClassLoader.close(): đóng JAR/file handles của loader
   |
   v
RELEASED
   |
   +-- bỏ strong references còn lại
   |
   v
ELIGIBLE_FOR_GC (nếu không còn đường tham chiếu mạnh)
   |
   v
MAY_UNLOAD (JVM quyết định, không có deadline)
```

Pseudocode minh họa thứ tự, **không phải class chạy độc lập**:

```java
void unloadPlugin(PluginHandle handle) throws Exception {
    handle.rejectNewRequests();
    handle.awaitOrCancelRunningTasks();

    handle.unregisterCallbacks();
    handle.stopPluginResources();

    // Không chạy task plugin mới trong lúc close.
    handle.classLoader().close();

    handle.clearStrongReferences();
}
```

`PluginHandle` trong đoạn trên là **interface/kiểu minh họa do ứng dụng tự thiết kế**, không phải Java SE API. Nội dung cho thấy ý định lifecycle: phối hợp thread, provider registry và resource ownership, chứ không có ý nghĩa `URLClassLoader.close()` tự gọi các bước đó.

**Không đóng loader khi còn thread khác đang loading.** JavaDoc 17 cảnh báo kết quả của lần load đồng thời với close là undefined. Ngừng nhận yêu cầu và đợi các thao tác loading hoàn tất trước khi đóng là yêu cầu vận hành quan trọng.

Nếu một plugin hỗ trợ chuyển trạng thái “running → stopped” nhưng còn object đã đăng ký được host gọi lại sau shutdown, cần sửa hợp đồng callback và xóa registry. Close không phải cơ chế “ngắt ngay mọi hàm do plugin định nghĩa”.

## 11. Reload plugin cần loader mới, không phải mở lại loader cũ

`close()` không làm loader quên các class đã định nghĩa, và Java SE không có API đảm bảo unload riêng một class đang được sử dụng. Thay bytecode của `plugin.jar` rồi gọi `oldLoader.loadClass(name)` có thể vẫn trả về class cũ.

Để chuyển từ v1 sang v2: ngừng request/tác vụ v1, unregister callback, đóng tài nguyên và loader v1, giải phóng tham chiếu host tới instance/`Class<?>` cũ, rồi tạo **loader mới** cho v2. Giữ API/SPI chia sẻ ở parent để host nhận diện provider v2; implementation cần được loader của từng thế hệ định nghĩa, nếu không parent-first có thể tiếp tục chọn bản cũ.

Hai thế hệ tự định nghĩa cùng binary name vẫn là hai runtime types khác nhau; đừng truyền trực tiếp implementation object cũ sang chỗ đòi class cụ thể của v2.

## 12. Các trường hợp khiến developer tưởng `close()` đã “thành công” nhưng plugin vẫn chiếm bộ nhớ

### 12.1 TCCL trong thread pool

`Thread.currentThread().setContextClassLoader(pluginLoader)` giúp những API sử dụng TCCL khám phá plugin. Nếu không khôi phục sau tác vụ, worker thread còn sống có thể giữ loader cũ **sau khi plugin đã close**:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Chạy công việc/plugin SPI discovery trong đúng context.
} finally {
    thread.setContextClassLoader(previous);
}
```

Đây là đoạn minh họa, giả định `pluginLoader` tồn tại. Với thread pool, phải quản lý TCCL ở **worker thread thực thi nhiệm vụ**, không chỉ thread submit.

### 12.2 Static registry của host

`HostEventBus.listeners` là collection sống lâu do host class ở parent loader định nghĩa. Nếu add một listener object do plugin loader định nghĩa và quên remove, host vẫn giữ listener dù plugin loader đã close.

```text
GC root → host static registry → listener instance → plugin Class → PluginLoader
```

Cách sửa: đăng ký có registration token/handle, gỡ registration trong `stop()`. Không giải quyết được bằng việc chỉ `loader.close()`.

### 12.3 Thread/Executor do plugin tạo

Nếu plugin tự tạo scheduler/thread và không shutdown, JVM có thể còn task đang chạy hoặc thread chờ nhiệm vụ, cùng stack/context giữ loader/class/plugin instance. Dừng scheduler, chờ termination và xóa task references là phần lifecycle riêng.

### 12.4 Logging/JDBC/JMX và các framework caches

Một framework được nạp ở parent có thể lưu class metadata, provider instances, callback, logger/filter, MBean hoặc driver registration do plugin cung cấp. Khi undeploy, phải gọi API cleanup phù hợp của framework. `URLClassLoader.close()` không biết những registries đó.

### 12.5 File resource ngoài quyền sở hữu loader

Plugin có thể tự gọi `new FileInputStream(...)` hoặc `new JarFile(...)`, giữ stream của bên thứ ba, memory mapped files hoặc native handles. Những resource này cần cleanup riêng. Nếu OS vẫn báo khóa JAR sau close, kiểm tra **ai thực sự đang giữ file handle** thay vì quy toàn bộ cho URLClassLoader.

## 13. Những lỗi thường gặp và cách phân biệt

| Dấu hiệu | Diễn giải có khả năng đúng | Hướng kiểm tra |
| --- | --- | --- |
| Gọi method của plugin sau close vẫn chạy | Class/method đã nạp; close không unload bytecode | Có còn instance/`Class<?>`/method references? |
| `loader.loadClass("plugin.NewType")` sau close báo `ClassNotFoundException` | Loader ngừng tìm class mới từ URL do nó phụ trách | Class có thực sự chưa nạp? Có ở parent không? |
| Method class cũ thất bại do dependency sau close | Dependency có thể chỉ được lazy-load/resolve khi method chạy | Tìm `NoClassDefFoundError`/cause, thời điểm resolve |
| JAR không thể thay trên Windows dù đã close | Handle khác vẫn giữ file hoặc close lỗi | Kiểm tra suppressed `IOException`, streams, native handles |
| Metaspace vẫn cao sau nhiều lần reload | Loader/plugin cũ vẫn reachable hoặc GC chưa unload | Heap dump, TCCL, thread, static cache/registry, unload logs |
| `System.gc()` rồi weak reference vẫn còn | Loader chưa đủ điều kiện hoặc GC chưa clear referent | Kiểm tra retaining paths, không xem GC hint là phép thử chắc chắn |
| V1 và V2 có cùng tên class nhưng không ép kiểu cho nhau | Khác defining loader nên là runtime types khác | Tách API chung ở parent, kiểm tra class identity |
| Reload nhưng vẫn nhận behavior cũ | Parent đã định nghĩa implementation hoặc cache/instance v1 còn sống | Kiểm tra `getClassLoader()`, namespace và registry |
| `IOException` khi `close()` | Có lỗi đóng file do loader mở | Xử lý/ghi log, xem suppressed exceptions |
| Thỉnh thoảng lỗi khi loader đang bị đóng | Racing giữa class load và close | Đồng bộ lifecycle, stop/await trước close |

Cần phân biệt rõ:

- `ClassNotFoundException` thường xuất hiện trong API lookup như `ClassLoader.loadClass` khi tìm class không thành công.
- `NoClassDefFoundError` có thể xuất hiện khi JVM cần class phụ thuộc ở giai đoạn linking/execution mà class ấy không sẵn có, hoặc khi initialization trước đó đã thất bại.
- `ClassCastException` giữa hai class trùng binary name thường liên quan **hai defining loaders khác nhau**, không trực tiếp do close.
- `OutOfMemoryError: Metaspace` trong ứng dụng reload nhiều lần có thể liên quan nhiều loader/class metadata không được thu hồi, nhưng cần chứng cứ retaining references và đo thực tế trước khi kết luận.

## 14. Cách quan sát chính xác hơn khi điều tra leak

Các công cụ hữu ích trên một JDK/HotSpot tương thích:

```bash
java -Xlog:class+load=info,class+unload=info -cp host CloseDemo
```

Tùy môi trường, output sẽ rất nhiều hoặc không có sự kiện unload trước khi chương trình kết thúc. `class+load` giúp quan sát class được load; `class+unload` chỉ in khi runtime thật sự unload.

Có thể dùng lệnh `jcmd` (khi công cụ có sẵn và tiến trình cho phép attach) để xem thống kê loader:

```bash
jcmd <PID> VM.classloader_stats
```

Đây là **lệnh minh họa**: thay `<PID>` bằng process ID thật, không gõ nguyên ký hiệu góc; lệnh/format có thể khác giữa các bản JDK hoặc cần quyền phù hợp. Dữ liệu hữu ích là **số loader, class count, metaspace usage** qua các lần deploy/undeploy.

Để tìm nguyên nhân giữ loader, cần **heap dump và retaining-path analysis**. Mục tiêu là tìm chuỗi tham chiếu đi từ GC root đến plugin loader hoặc class/provider objects. Lúc phân tích, tránh giữ tham chiếu thử nghiệm trong chính ứng dụng hoặc thêm static cache debug mới khiến loader bị giữ sống.

**Không dùng `Runtime.freeMemory()` như phép đo trực tiếp class unloading.** Heap objects, native JAR handles và metaspace class metadata là những loại tài nguyên khác nhau. JVM có thể giữ vùng memory đã cấp phát để tái sử dụng dù loader/class nào đó đã được thu hồi.

## 15. Ví dụ sử dụng loader trong phạm vi hẹp và dài hạn

**Tác vụ hữu hạn:** dùng `try (URLClassLoader loader = new URLClassLoader(urls, parent)) { ... }` khi toàn bộ việc tải và xử lý class/resource kết thúc trong khối; đọc và đóng stream trước khi thoát.

**Plugin dài hạn:** manager giữ cả loader và instance trong suốt quá trình sử dụng. Đóng loader trong factory trước khi trả instance có thể khiến method cũ chạy được nhưng lazy class/resource lookup về sau hỏng. Dừng plugin, chờ task hoàn thành, dọn callbacks, đóng loader rồi gỡ các strong references.

Khác biệt nằm ở **phạm vi sở hữu thực tế**, không ở cú pháp gọi `close()`.

## 16. Câu hỏi tự kiểm tra

**1.** Sau `URLClassLoader.close()`, class đã nạp có biến mất ngay khỏi JVM không?

**Đáp án:** Không. `close()` không gỡ định nghĩa class, object hoặc static state. Class unloading liên quan khả năng GC thu hồi defining loader và là quyết định của JVM.

**2.** Vì sao trong ví dụ, `message.invoke(obj)` vẫn trả `still alive` sau close?

**Đáp án:** Instance, `Class<?>` và `Method` đã được tạo/resolve trước khi loader đóng. Close không phá hủy metadata/bytecode đã nạp.

**3.** `URLClassLoader.loadClass("plugin.Hello")` sau close có thể trả cùng `Class<?>` cũ không?

**Đáp án:** Có trong cơ chế mặc định khi class đã được loader khởi đầu nạp và còn lưu trong lookup state (`findLoadedClass`). Điều này khác với việc tìm/định nghĩa một class hoàn toàn mới từ URL sau close.

**4.** Vì sao có `plugin.NotYet.class` trên đĩa mà lệnh load sau close vẫn báo không thấy?

**Đáp án:** URL loader đã đóng nên không tiếp tục dùng source URL của chính nó để định nghĩa class mới. Parent trong ví dụ cũng không cung cấp class ấy.

**5.** Tại sao không nên đóng loader rồi để plugin tiếp tục nhận request?

**Đáp án:** Các method đã nạp có thể còn hoạt động nhưng những dependency/resource cần nạp lần đầu về sau có thể không truy cập được. Đồng thời close cạnh tranh với thread đang load tạo kết quả không xác định.

**6.** `loader = null; System.gc();` có bảo đảm class đã unload không?

**Đáp án:** Không. Loader có thể còn reachable qua instance, class object, cache, thread/TCCL hoặc registry; GC/unload cũng không bị buộc chạy ngay.

**7.** Để reload JAR v2 có đúng type identity mới, thường cần làm gì?

**Đáp án:** Tạo **URLClassLoader mới** sau khi quản lý dừng/đóng loader v1. Nếu v1 và v2 thực sự do hai defining loaders khác nhau định nghĩa, cùng binary name vẫn là hai runtime types khác nhau.

**8.** Nếu dùng `try-with-resources` trong hàm tạo plugin rồi trả instance, điều gì nguy hiểm?

**Đáp án:** Loader đóng trước khi plugin kết thúc hoạt động. Code plugin có thể còn dùng được một thời gian, nhưng sẽ lỗi khi cần lazy-load các class/resource còn lại.

**9.** Sau close JAR vẫn bị khóa. Có thể kết luận JavaDoc sai không?

**Đáp án:** Không. Có thể có handle do plugin hoặc thư viện khác mở, hoặc lỗi I/O trong quá trình close. Cần điều tra file handle thực tế và exception/suppressed exceptions.

**10.** `Class<?>` của plugin bị giữ trong một static map ở host. `close()` có giúp GC unload class đó không?

**Đáp án:** Close không xóa entry map. Strong reference từ host có thể giữ `Class<?>`/defining loader sống. Phải xóa cache/registry đúng vòng đời và xác minh không còn root references.

## 17. Checklist thiết kế plugin có thể hot-reload

1. **Loader scope:** Mỗi deployment/version có loader riêng, shared API ở parent phù hợp.
2. **Load phase:** Không để lẫn classes của plugin vào application classpath khiến parent-first chọn nhầm class.
3. **Ownership:** Host/plugin xác định ai quản lý threads, scheduler, listener, driver, MBean, stream, JAR handles.
4. **Stop:** Ngừng yêu cầu mới; kết thúc các tác vụ và class loading đang hoạt động.
5. **Unregister:** Gỡ provider/listener/cache/registrations từ các object sống lâu ở host.
6. **Context:** Khôi phục TCCL, xóa `ThreadLocal` của task và kiểm tra thread pools.
7. **Close:** Gọi `URLClassLoader.close()` sau khi không còn công việc cần source URL, ghi nhận `IOException` và suppressed.
8. **Release:** Bỏ tham chiếu mạnh tới loader, instances, `Class<?>` và reflection metadata của deployment cũ.
9. **Reload:** Tạo loader mới cho artifact/version mới, kiểm tra class identity của shared API.
10. **Observe:** Theo dõi classloader stats, class unloading logs, metaspace và heap retaining paths; không dùng `System.gc()` làm tiêu chí thành công duy nhất.

## Kết luận

**`URLClassLoader.close()` ≠ unload classes ≠ shutdown plugin.** Close chủ yếu đóng những nguồn/tài nguyên do loader sở hữu và ngăn nó định nghĩa class mới từ các URL; **class đã nạp còn có thể được sử dụng**. Để JVM **có thể** unload class plugin, phải quản lý toàn bộ vòng đời plugin, bỏ các strong references giữ defining loader sống và để GC quyết định thời điểm thu hồi. Không có API Java SE nào bảo đảm “đóng loader ⇒ class biến mất ngay”.

**Tài liệu chuẩn (Java 17):**

- [`URLClassLoader` Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html) — contract của `close()`, exceptions, URLs/JAR handles, behavior đối với class đã nạp.
- [`ClassLoader` Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — `loadClass`, `findLoadedClass` và parent delegation.
- [JLS 17 `12.7 – Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7) — điều kiện để class/interface có thể được unload.
- [JVMS 17 – Loading, Linking and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) — class identity, loader và thời điểm resolution.
