# Thứ tự ủy quyền tài nguyên phải nhất quán với chính sách nạp lớp

Khi viết `ClassLoader` tùy biến, ta thường quan tâm đến `loadClass()`: ưu tiên hỏi **parent** trước (*parent-first*) hay tự tìm lớp trong nguồn của **child** trước (*child-first*)? Tuy nhiên, một ứng dụng Java còn tải các **resource** như `.properties`, template, schema, cấu hình logging, metadata `META-INF/services/...` hoặc tệp dữ liệu đóng gói cùng thư viện. Các resource được tìm bằng `getResource()`, `getResources()` và `getResourceAsStream()`.

**Quy tắc thiết kế cốt lõi:** Nếu một plugin/class được định nghĩa từ nguồn child thì các resource **gắn với triển khai đó** thường cũng phải được chọn từ child; nếu class dùng chung do parent định nghĩa thì metadata/resource tương ứng cần có chính sách rõ ràng từ parent. Khi đổi `loadClass()` sang child-first nhưng để `getResource()` và `getResources()` giữ parent-first mặc định, ta có thể nhận **code của child nhưng config/metadata của parent**, tạo hành vi rất khó phát hiện.

Lưu ý chính xác: Java **không bắt buộc mọi resource phải luôn theo một thứ tự duy nhất với mọi lớp**. Một số cấu hình cần parent-first có chủ ý, một số resource cần tổng hợp từ nhiều nơi. Điều cần bảo đảm là **chính sách tra cứu nhất quán với phạm vi sở hữu resource và hợp đồng nạp lớp**, đặc biệt với những resource gắn chặt với một class/provider.

## 1. Hai đường tìm kiếm phải hiểu riêng

| Hoạt động | API thường gặp | Mục tiêu |
| --- | --- | --- |
| Nạp định nghĩa lớp | `ClassLoader.loadClass(String)`, `Class.forName(..., loader)` | Nhận `Class<?>` có defining loader phù hợp. |
| Tìm một resource | `ClassLoader.getResource(String)` | Trả về **URL đầu tiên** phù hợp hoặc `null`. |
| Mở stream tài nguyên | `ClassLoader.getResourceAsStream(String)` | Thường dựa trên resource đã chọn từ `getResource`, trả `InputStream` hoặc `null`. |
| Tìm nhiều resource cùng tên | `ClassLoader.getResources(String)` | Trả một `Enumeration<URL>` của các bản tìm được theo chính sách loader. |
| Tìm resource liên quan tới lớp | `SomeClass.class.getResource(...)` | Áp dụng quy tắc tên tương đối/tuyệt đối theo package, rồi tìm trong ngữ cảnh của lớp/module. |

Trong `java.lang.ClassLoader` mặc định, đường nạp lớp thông thường tuân theo **parent delegation**: kiểm tra đã nạp, nhờ parent trước, sau đó mới tự tìm qua `findClass()`. Với resource, cách triển khai `getResource()` mặc định cũng thử parent trước rồi mới gọi `findResource()`; `getResources()` mặc định liệt kê kết quả từ parent trước rồi tới `findResources()`.

Nhưng đây là **hai cơ chế riêng**. Nếu chỉ ghi đè `loadClass` mà không xét API resource, class có thể theo child-first trong khi resource vẫn parent-first. Tương tự, nếu chỉ ghi đè `getResource` nhưng quên `getResources`, việc tìm một resource và nhiều resource có thể khác chính sách.

### Sơ đồ vấn đề

~~~text
               Cùng tên: plugin/Engine.class
                         plugin/config.properties

                       Parent      Child
                         │           │
          class?          │           └──── CHỌN Engine của Child
                         │
          resource?       └──────────────── CHỌN config của Parent

             Engine Child + config Parent
                 → sai schema, sai feature flag,
                   hành vi khó tái hiện
~~~

Đây là một tình huống thường gặp khi cùng tên resource tồn tại ở nhiều JAR/thư mục. Nếu parent không có resource trùng thì vấn đề có thể bị che giấu trong giai đoạn phát triển; sau khi nâng cấp host hoặc plugin, resource mới xuất hiện ở parent và bắt đầu chiếm ưu tiên bất ngờ.

## 2. Parent-first và child-first: nhất quán nghĩa là gì?

**Parent-first** ưu tiên lớp và resource do parent cung cấp:

~~~text
loadClass("demo.Marker")         → Parent thử trước → Parent.Marker
getResource("demo/id.properties")→ Parent thử trước → Parent resource
getResources(...)                → Parent entries trước, child entries sau
~~~

Ưu điểm là chia sẻ API và tài nguyên chung, tránh plugin tự thay thế những class do host sở hữu. Nếu resource thực sự thuộc về phiên bản plugin child, parent-first không phải lúc nào cũng là lựa chọn mong muốn.

**Child-first** chỉ định child ưu tiên các class và resource **trong phạm vi cô lập đã chọn**:

~~~text
loadClass("plugin.impl.Engine")     → Child thử trước → Child.Engine
getResource("plugin/engine.yml")   → Child thử trước → Child resource
getResources("plugin/engine.yml")  → Child entries trước, parent entries sau
~~~

Lưu ý: có thể và thường **nên** giữ parent-first với `java.*` và package API hợp đồng chung, chỉ child-first với implementation riêng. Tránh child-first toàn bộ không có ranh giới rõ ràng, vì dễ tạo duplicate interface/class, `ClassCastException` hoặc rắc rối linking.

**Một-resource** và **nhiều-resource** có yêu cầu riêng:

- `getResource(name)` chọn **một** vị trí; thay thứ tự có thể đổi kết quả ngay.
- `getResources(name)` có thể tìm **nhiều** bản. Thứ tự enumeration có thể ảnh hưởng việc merge cấu hình hoặc khám phá provider. Không nên tùy tiện đảo/xóa kết quả nếu framework dựa trên ngữ nghĩa hợp nhất.
- `getResourceAsStream(name)` thường ủy quyền đến `getResource` của chính loader; nếu custom loader đổi cách tìm URL thì đường stream cần được xem xét nhất quán.
- `findResource` và `findResources` được thiết kế để tìm **resource cục bộ** của loader; việc ủy quyền parent thuộc lớp phương thức `get...`.

**Bất biến nên kiểm tra cho các resource gắn chặt với class:** Sau khi biết class `C` thực sự do loader nào định nghĩa, resource đóng gói cùng `C` phải được lấy theo contract của thành phần đó, tránh vô tình dùng một bản của thành phần khác.

## 3. Ví dụ Java 17 chạy độc lập: nhìn thấy hai chính sách

Chương trình sau tự tạo hai thư mục tạm `parent` và `child`. Cả hai có cùng tên class `demo.Marker` và resource `demo/id.properties`, nhưng nội dung khác nhau. Nó dùng `JavaCompiler` của JDK để biên dịch hai bản class tại thời điểm chạy, rồi quan sát class và resource do từng loader chọn.

**Tệp duy nhất: `ResourceDelegationDemo.java`**

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
import java.io.InputStream;
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.Properties;

public class ResourceDelegationDemo {
    private static final String CLASS_NAME = "demo.Marker";
    private static final String RESOURCE = "demo/id.properties";

    static class ChildFirstLoader extends URLClassLoader {
        ChildFirstLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);

                if (type == null) {
                    if (CLASS_NAME.equals(name)) {
                        try {
                            type = findClass(name);
                        } catch (ClassNotFoundException notLocal) {
                            type = super.loadClass(name, false);
                        }
                    } else {
                        type = super.loadClass(name, false);
                    }
                }

                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }

        @Override
        public URL getResource(String name) {
            if (RESOURCE.equals(name)) {
                URL local = findResource(name);
                if (local != null) {
                    return local;
                }
            }
            return super.getResource(name);
        }

        @Override
        public Enumeration<URL> getResources(String name)
                throws IOException {
            if (!RESOURCE.equals(name)) {
                return super.getResources(name);
            }

            List<URL> result = Collections.list(findResources(name));
            result.addAll(Collections.list(
                    getParent().getResources(name)));
            return Collections.enumeration(result);
        }
    }

    private static void buildVersion(Path directory, String owner)
            throws IOException {
        Path source = directory.resolve("src/demo/Marker.java");
        Path resource = directory.resolve(RESOURCE);

        Files.createDirectories(source.getParent());
        Files.createDirectories(resource.getParent());
        Files.writeString(source,
                "package demo; public class Marker { " +
                "public static String owner() { return \"" +
                owner + "\"; } }");
        Files.writeString(resource, "owner=" + owner + "\n");

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK, not a JRE");
        }

        int exit = compiler.run(
                null, null, null,
                "-d", directory.toString(), source.toString());

        if (exit != 0) {
            throw new IllegalStateException("Compilation failed: " + exit);
        }
    }

    private static String readOwner(URL url) throws IOException {
        if (url == null) {
            return "(missing)";
        }

        Properties props = new Properties();
        try (InputStream input = url.openStream()) {
            props.load(input);
        }
        return props.getProperty("owner");
    }

    private static void inspect(String label, ClassLoader loader)
            throws Exception {
        Class<?> type = loader.loadClass(CLASS_NAME);
        String classOwner =
                (String) type.getMethod("owner").invoke(null);

        String firstResource =
                readOwner(loader.getResource(RESOURCE));

        Enumeration<URL> found = loader.getResources(RESOURCE);
        List<String> resourceOrder = new ArrayList<>();

        while (found.hasMoreElements()) {
            resourceOrder.add(readOwner(found.nextElement()));
        }

        System.out.println(label + " class: " + classOwner);
        System.out.println(label + " resource: " + firstResource);
        System.out.println(label + " resources: " +
                String.join(" -> ", resourceOrder));
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("resource-order-");
        Path parentDir = Files.createDirectories(root.resolve("parent"));
        Path childDir = Files.createDirectories(root.resolve("child"));

        buildVersion(parentDir, "PARENT");
        buildVersion(childDir, "CHILD");

        try (URLClassLoader parent = new URLClassLoader(
                    new URL[] { parentDir.toUri().toURL() }, null);
             URLClassLoader parentFirst = new URLClassLoader(
                    new URL[] { childDir.toUri().toURL() }, parent);
             ChildFirstLoader childFirst = new ChildFirstLoader(
                    new URL[] { childDir.toUri().toURL() }, parent)) {

            inspect("Parent-first", parentFirst);
            inspect("Child-first", childFirst);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa `ResourceDelegationDemo.java`, sử dụng **JDK 17+** (cần `javac` và system compiler của module `jdk.compiler`):

~~~bash
javac --release 17 ResourceDelegationDemo.java
java ResourceDelegationDemo
~~~

**Stdout dự kiến với JDK 17+ tiêu chuẩn và các URL thư mục do chương trình tạo:**

~~~text
Parent-first class: PARENT
Parent-first resource: PARENT
Parent-first resources: PARENT -> CHILD
Child-first class: CHILD
Child-first resource: CHILD
Child-first resources: CHILD -> PARENT
~~~

Giải thích:

1. `buildVersion` sinh hai `demo.Marker` (mỗi bản trả tên chủ sở hữu khác nhau) và hai resource trùng tên `demo/id.properties`.
2. `parent` có URL trỏ đến bản PARENT; cả `parentFirst` và `childFirst` trỏ bản CHILD nhưng dùng cùng parent.
3. `parentFirst` là `URLClassLoader` mặc định, nên `loadClass` cùng `getResource` ủy quyền parent trước; kết quả đều là PARENT.
4. `ChildFirstLoader.loadClass` tự gọi `findClass` trước **chỉ cho `demo.Marker`**, sau đó mới fallback sang parent. Với những lớp khác (đặc biệt JDK classes), nó giữ hành vi chuẩn.
5. `ChildFirstLoader.getResource` ưu tiên `findResource` của child cho đúng tên resource liên quan `demo.Marker`, sau đó fallback về parent.
6. `ChildFirstLoader.getResources` trả danh sách child trước rồi đến parent **cho resource đã chọn**; các resource khác sử dụng triển khai chuẩn. Vì vậy kết quả enumeration theo hai chính sách đổi thứ tự.
7. `getClassLoadingLock(name)` và `findLoadedClass(name)` tránh tự định nghĩa trùng và giúp giữ đồng bộ hành vi nạp lớp; `resolveClass` chỉ gọi khi yêu cầu resolve.

**Phạm vi của mã:** Đây là demo lớp/resource trên **classpath dạng thư mục** với một tên class cụ thể. Loader thực tế cần kiểm soát package, bảo vệ API chung, thứ tự resource trùng, lỗi I/O và quan hệ module rõ hơn. `getResources` ở ví dụ cố ý không loại duplicate URL; khi ứng dụng muốn merge/provider discovery cần xét việc lọc trùng và giữ thứ tự theo hợp đồng.

### Nếu chỉ ghi đè loadClass() thì sao?

Nếu `ChildFirstLoader` chỉ có override `loadClass`, còn giữ nguyên `getResource` và `getResources` của `ClassLoader`/`URLClassLoader`, ta có thể quan sát:

~~~text
Child-first class: CHILD
Child-first resource: PARENT
Child-first resources: PARENT -> CHILD
~~~

Đây là **kết quả phân tích cho biến thể** bỏ hai override resource, không phải output của chương trình hoàn chỉnh đang cung cấp. Nó minh họa chính xác nguyên nhân cần đồng bộ chính sách khi class và resource có liên quan.

## 4. Phân biệt Class.getResource và ClassLoader.getResource

Hai API dùng **quy tắc tên resource khác nhau**, dễ dẫn đến chẩn đoán nhầm thứ tự loader:

| Gọi API | Cách hiểu đường dẫn |
| --- | --- |
| `loader.getResource("config/app.properties")` | Tên resource tính từ **root**, không bắt đầu bằng dấu `/`. |
| `SomeClass.class.getResource("config/app.properties")` | Tên tương đối tính từ **package của SomeClass**. |
| `SomeClass.class.getResource("/config/app.properties")` | Tên tuyệt đối tính từ **root** (bỏ dấu `/` đầu trước khi lookup). |

Ví dụ khi `demo.Marker` tìm `demo/id.properties`:

~~~java
// Fragment minh họa với Class<?> markerType đã có.
markerType.getResource("id.properties");
markerType.getResource("/demo/id.properties");
markerType.getClassLoader().getResource("demo/id.properties");
~~~

Ba lời gọi đều có thể nói tới resource tương ứng với package `demo`, **nhưng đường tìm và ngữ nghĩa module của Class.getResource có thể khác**. Đoạn code là fragment, không nằm trong ví dụ hoàn chỉnh phần trước.

Đừng thêm dấu `/` đầu tên cho `ClassLoader.getResource` rồi quy kết việc trả `null` là do parent/child; vấn đề có thể chỉ là **tên resource sai quy ước**.

**Với named modules (Java 9+)**, tra cứu non-`.class` resource còn chịu ảnh hưởng module encapsulation/`opens`; thứ tự loader không phải yếu tố duy nhất. Với `Class.getResource`, module định nghĩa class có thể quyết định cách và phạm vi truy cập resource. Ví dụ Java 17 ở phần 3 dùng URL classpath/unnamed module để làm rõ delegation độc lập với JPMS.

## 5. getResources(): thứ tự tổng hợp quan trọng như thế nào?

Nhiều framework không tìm **một** file mà duyệt **tất cả** resource cùng tên. Ví dụ:

- Metadata `META-INF/services/com.acme.api.Plugin` cho cơ chế SPI của Java.
- Nhiều tệp cấu hình cùng tên do host và plugin cung cấp.
- Resources cho discovery, routing, template registry, hoặc cấu hình thư viện.

Trong `ClassLoader` mặc định, `getResources` liệt kê parent trước rồi local của child. Nếu class được ưu tiên từ child nhưng resource SPI của parent xuất hiện trước, code có thể khám phá provider không khớp phiên bản class/API đã nạp hoặc merge config theo thứ tự bất ngờ.

**Ba chính sách khác nhau phải được xác định rõ:**

1. **First-wins**: lấy resource đầu tiên (thường qua `getResource`); child-first hay parent-first quyết định kết quả.
2. **Last-wins**: đọc mọi resource rồi ghi đè giá trị theo thứ tự; một thứ tự đảo có thể làm bản cuối chiếm ưu tiên.
3. **Merge-all**: cần toàn bộ resource, nhưng có thể cần chống duplicate hoặc xử lý xung đột tên/provider.

Không nên đánh đồng `getResources` với việc tìm một resource duy nhất. Một triển khai custom đôi khi có quyền trả các bản từ cả parent và child, nhưng phải giữ được **quy tắc thứ tự nhất quán và có tài liệu**. Với `ServiceLoader`, còn có điều kiện provider type và khả năng nạp class của provider bằng loader được chọn; đổi thứ tự resource **không đảm bảo** ServiceLoader có thể cast được provider nếu API interface đã bị các loader định nghĩa trùng.

### Ví dụ xung đột metadata

~~~text
parent:
  com/acme/api/Codec.class
  META-INF/services/com.acme.api.Codec  → com.acme.api.DefaultCodec

child:
  com/acme/plugin/FastCodec.class
  META-INF/services/com.acme.api.Codec  → com.acme.plugin.FastCodec
~~~

Trong thiết kế hợp lệ, **interface Codec được chia sẻ** từ parent; class FastCodec do plugin loader định nghĩa nhưng implements đúng interface ấy. Resource SPI có thể được tổng hợp qua `getResources` để cả hai provider có thể được tìm. Không nên định nghĩa lại `Codec` trong child và mong việc đảo thứ tự `getResources` sửa được `ClassCastException`.

## 6. Khi nào nên ưu tiên child resource và khi nào giữ parent resource?

Không nên áp đặt child-first cho mọi thứ. Một chính sách thực tế thường có ranh giới:

| Nhóm class/resource | Quy tắc gợi ý | Vì sao |
| --- | --- | --- |
| Java platform và API host chia sẻ | Parent-first | Duy trì type identity/API contract và hành vi nền tảng. |
| Implementation riêng của plugin | Child-first nếu cần isolation | Cho phép plugin dùng phiên bản triển khai riêng. |
| Resource đi kèm implementation plugin | Child-first tương ứng | Tránh plugin đọc config/schema/template của host. |
| Resource cấu hình host được chủ động override bởi plugin | Thỏa thuận rõ first-wins hay merge | Có thể cần parent-first, child-first hoặc merge theo mục tiêu nghiệp vụ. |
| `META-INF/services/...` | Thường duyệt nhiều resource | Giữ provider discovery đầy đủ và bảo đảm API chung. |

Chính sách có thể triển khai theo **namespace/package/resource prefix** hoặc theo mapping rõ ràng giữa plugin và resource. Điều quan trọng là xác định **ai sở hữu** từng đường dẫn và **điều gì xảy ra nếu hai bên cùng tên**.

Với loader child-first được viết tùy biến, những phương thức thường cần xem xét như một bộ liên quan:

~~~text
loadClass / findClass
getResource / findResource
getResources / findResources
getResourceAsStream
~~~

`getResourceAsStream` trong triển khai chuẩn dựa trên `getResource`; thông thường không cần override riêng nếu hành vi mở stream theo URL đã đáp ứng. Tuy nhiên nếu custom loader lưu resource trong bộ nhớ, filesystem phi chuẩn hay xử lý stream đặc biệt, cần kiểm tra đường stream cũng theo cùng chính sách.

## 7. Lỗi phổ biến khi triển khai

### 7.1. Chỉ đổi loadClass, quên getResource

**Triệu chứng:** `MyPlugin.class.getClassLoader()` là child nhưng `loader.getResource("plugin/config.yml")` trả URL trong JAR parent. Plugin có thể đọc cấu hình sai phiên bản.

**Khắc phục:** Thống nhất chính sách cho resource gắn với implementation. In URL được chọn và class defining loader khi debug.

### 7.2. getResource child-first nhưng getResources parent-first

**Triệu chứng:** Đọc một file thấy bản child, còn framework dùng enumeration lại nạp provider/config parent trước.

**Khắc phục:** Đặt test cho cả `getResource` và thứ tự `getResources` của tên resource quan trọng. Với resource cần merge, kiểm tra danh sách đầy đủ, không chỉ phần tử đầu.

### 7.3. Ghi đè loadClass mà phá parent delegation

**Triệu chứng:** `ClassCastException` với hai bản cùng tên API, `LinkageError` hoặc lớp JDK bị chặn tìm.

**Khắc phục:** Giữ parent-first cho API/JDK, chỉ child-first các package implementation có kiểm soát; sử dụng `findLoadedClass`, `getClassLoadingLock` và `resolveClass` đúng hợp đồng.

### 7.4. Nghĩ URL trả về là file trên đĩa

Resource có thể có scheme `jar:`, `jrt:` hoặc URL từ loader đặc thù. Không nên ép `Paths.get(url.toURI())` cho mọi URL. Thường nên dùng `url.openStream()` hoặc `getResourceAsStream` khi chỉ cần đọc bytes. Với URL `jar:`, đường đến một entry trong JAR không phải file riêng ở filesystem mặc định.

### 7.5. Nhầm tên tương đối/tuyệt đối

`ClassLoader.getResource("demo/id.properties")` và `Marker.class.getResource("id.properties")` có thể cùng tên resource logic, nhưng `ClassLoader.getResource("/demo/id.properties")` là sai quy tắc thông thường. Luôn xác nhận đường dẫn trong JAR bằng công cụ phù hợp.

### 7.6. Module access ảnh hưởng resource lookup

Với named module, resource đóng trong package không mở có thể không được trả về qua API từ bên ngoài, ngay cả khi class loader thích hợp nhìn thấy module đó. Đừng giải quyết mọi `null` bằng việc đảo thứ tự parent/child; xem module ownership và `opens`/encapsulation khi cần.

### 7.7. Thay đổi global TCCL không quản lý vòng đời

`Thread.currentThread().getContextClassLoader()` được nhiều framework dùng để chọn loader cho resource/provider. Đổi TCCL mà không khôi phục trong `finally` có thể gây kết quả khác nhau theo thread và giữ plugin loader cũ sau redeploy. Dùng TCCL có chủ đích và quản lý vòng đời.

## 8. Quy trình điều tra khi class đúng nhưng resource sai

1. **Xác định class đích** và in `Class.getClassLoader()` để biết defining loader thực sự. Không giả định loader gọi `loadClass` đã tự định nghĩa class.
2. **Xác định tên resource chính xác**: đường dẫn tuyệt đối hay tương đối, có package prefix, có dấu `/` đầu không.
3. **In URL đầu tiên** từ `loader.getResource(name)` và duyệt **mọi URL theo thứ tự** từ `loader.getResources(name)`.
4. **So sánh nơi class được định nghĩa** với nơi resource được chọn: child class đi kèm parent config là dấu hiệu đáng nghi.
5. **Kiểm tra tài nguyên được dùng qua đường nào**: `SomeClass.getResource`, `ClassLoader.getResource`, `ServiceLoader` hoặc TCCL có thể khác.
6. **Kiểm tra chính sách parent-first/child-first** của tên class và tên resource, cùng fallback khi child không có.
7. **Kiểm tra module/resource encapsulation** nếu là named module.
8. **Khóa hành vi mong muốn bằng kiểm thử nhỏ** với hai bản class/resource trùng tên, xác nhận cả `getResource` và `getResources` như chương trình Java 17 phía trên.

Một đoạn chẩn đoán ngắn (fragment, giả sử có `type` và `resourceName`):

~~~java
ClassLoader loader = type.getClassLoader();
System.out.println("Defining loader: " + loader);

URL first = loader.getResource(resourceName);
System.out.println("First resource: " + first);

Enumeration<URL> all = loader.getResources(resourceName);
while (all.hasMoreElements()) {
    System.out.println("Candidate: " + all.nextElement());
}
~~~

Fragment trên cần import `java.net.URL`, `java.util.Enumeration`, xử lý `IOException`, và giả định `loader` không null. Khi `type` do bootstrap loader định nghĩa (`getClassLoader() == null`), cần dùng API tra cứu resource phù hợp thay vì gọi method trên null.

## 9. Tự kiểm tra

**Câu 1.** Một custom loader nạp `plugin.Engine` bằng child-first nhưng giữ `getResource` mặc định. Parent và child cùng có `plugin/settings.properties`. Resource nào thường được chọn?

**Đáp án:** Parent-first resource lookup thường chọn **bản parent**; kết quả có thể không khớp implementation `Engine` từ child.

**Câu 2.** Vì sao override `getResource` chưa đủ nếu framework dùng `getResources`?

**Đáp án:** `getResources` có quy tắc liệt kê riêng. Framework có thể thấy bản parent trước dù `getResource` đang ưu tiên child.

**Câu 3.** Có nên child-first mọi `java.*` và interface API host để đồng bộ với plugin không?

**Đáp án:** Không. Giữ parent-first cho platform và API chung giúp tránh hai định nghĩa kiểu khác nhau. Chỉ áp dụng child-first có phạm vi cho implementation/resource thuộc plugin.

**Câu 4.** Tên nào phù hợp với `ClassLoader.getResource` nếu tệp nằm ở `demo/id.properties`?

**Đáp án:** `"demo/id.properties"`, không có dấu `/` đầu.

**Câu 5.** Với `META-INF/services`, liệu chỉ đảo `getResources` sang child-first là đủ sửa mọi lỗi `ServiceLoader`?

**Đáp án:** Không. Cần bảo đảm các provider được tìm thấy **triển khai đúng cùng interface API** do loader mà consumer kỳ vọng định nghĩa; còn phải xét module/discovery và khả năng nạp provider.

## Ghi nhớ

**Class loading và resource lookup là hai đường tra cứu khác nhau nhưng có liên hệ về ngữ nghĩa.** Với parent-first, mặc định class/resource thường ưu tiên parent; với child-first có chọn lọc, resource gắn với implementation cần được điều phối đồng bộ qua `getResource`, `getResources` và đường stream liên quan. Xác định rõ **class nào thuộc parent hay child**, **resource nào thuộc thành phần đó** và **thứ tự first-wins/merge-all** để tránh kết hợp code từ một phiên bản với cấu hình/metadata từ phiên bản khác.

**Tài liệu chuẩn:**

- Java SE 17 API, `ClassLoader`, các phương thức `loadClass`, `getResource`, `getResources`, `findResource`, `findResources`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 API, `Class.getResource`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 API, `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
