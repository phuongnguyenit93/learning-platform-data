# Ngăn lớp và tài nguyên dùng các thứ tự ưu tiên khác nhau

Trong Java, một **class loader tùy chỉnh** có thể chọn **lớp (`.class`) từ một nguồn**, nhưng lại trả **tài nguyên (`.properties`, `.xml`, `META-INF/services/...`, template...) từ nguồn khác** nếu chính sách `loadClass` và chính sách `getResource`/`getResources` không thống nhất.

Ví dụ điển hình: ứng dụng dùng **child-first cho `demo.Feature`** để chạy phiên bản plugin, nhưng vẫn giữ `ClassLoader.getResource` mặc định **parent-first**. Kết quả có thể là:

```text
demo.Feature             -> plugin/child (version B)
demo/config.properties   -> application/parent (version A)
```

Code của phiên bản B đọc cấu hình A, dù hai mục tưởng chừng được đóng chung trong plugin. Đây là một loại lỗi **khác nguồn lớp–tài nguyên (class/resource provenance mismatch)**: khó phát hiện vì cả việc nạp lớp và đọc file đều có thể thành công, nhưng chương trình chạy sai logic.

**Mục tiêu của bài:** Thiết kế và kiểm thử một chính sách ưu tiên nhất quán giữa việc nạp lớp, tra một tài nguyên và tra **tất cả** tài nguyên; đồng thời hiểu khi nào cố ý dùng chung tài nguyên của parent thay vì áp dụng child-first cho mọi thứ.

## 1. Lớp và tài nguyên dùng các API khác nhau

Class loader có nhiều đường tìm kiếm độc lập:

| Thao tác | API điển hình | Tên đầu vào | Kết quả |
|---|---|---|---|
| Nạp lớp | `loadClass("demo.Feature")` | **Binary name** với dấu `.` | `Class<?>` |
| Tìm nơi định nghĩa bytecode | `findClass("demo.Feature")` | Binary name | `Class<?>` do loader riêng cung cấp nếu có |
| Tìm một tài nguyên | `getResource("demo/config.properties")` | **Resource name** với dấu `/` | `URL` hoặc `null` |
| Tìm tất cả tài nguyên cùng tên | `getResources("META-INF/services/spi.Plugin")` | Resource name | `Enumeration<URL>` |
| Đọc nội dung | `getResourceAsStream(name)` | Resource name | `InputStream` hoặc `null` |

Tên lớp `demo.Feature` và resource path `demo/Feature.class` **không phải cùng loại đầu vào**. Không truyền `demo/Feature.class` vào `loadClass` và không truyền `demo.Feature` vào `getResource` để kỳ vọng cùng ý nghĩa.

Các phương thức mở rộng thường gặp:

- `loadClass(String, boolean)`: điều phối class loading, cache, delegation và resolve.
- `findClass(String)`: tìm/định nghĩa lớp từ nguồn của loader.
- `getResource(String)`: cung cấp **một** URL tài nguyên.
- `getResources(String)`: cung cấp **các** URL tài nguyên, với thứ tự có thể quan trọng.
- `findResource(String)` và `findResources(String)`: tìm tài nguyên ở phần nguồn riêng của loader.
- `getResourceAsStream(String)`: đọc tài nguyên qua stream; trên `ClassLoader`, implementation mặc định dựa trên đường tìm resource.

**Vấn đề:** Override `loadClass` không tự động thay đổi thứ tự của `getResource` và `getResources`. Override `findClass` cũng không tự tạo quy tắc tìm tài nguyên.

## 2. Chính sách mặc định: parent-first cho cả lớp và tài nguyên

Với triển khai chuẩn của `ClassLoader`, cách hiểu khái quát là:

```text
loadClass("demo.Feature")
    1. findLoadedClass
    2. parent.loadClass hoặc bootstrap
    3. findClass của loader hiện tại khi parent không nạp được

getResource("demo/config.properties")
    1. parent.getResource hoặc bootstrap resource lookup
    2. findResource của loader hiện tại nếu parent không có

getResources("demo/config.properties")
    1. tài nguyên của parent/bootstrap
    2. tài nguyên của loader hiện tại (findResources)
```

Điểm quan trọng: **`getResource` chỉ chọn một URL**, còn **`getResources` trả nhiều URL**. Với loader mặc định, parent được ưu tiên trong cả hai, nhưng API danh sách còn có thể chứa hai bản cùng tên từ các nguồn khác nhau.

Ví dụ parent và child đều cung cấp `demo/config.properties`:

```text
parent/classes/demo/config.properties  -> mode=parent
child/classes/demo/config.properties   -> mode=child

getResource(name)        -> URL của parent
getResources(name)       -> [URL parent, URL child]
```

Đây là thứ tự thông thường khi cả hai nằm trong phạm vi lookup của các loader theo cấu hình trên. Không suy ra rằng **mọi custom loader** hoặc **mọi runtime module/JAR** buộc giữ đúng thứ tự này: implementation và các hạn chế module/resource có thể thay đổi tập kết quả thực tế.

### Vì sao xung đột xuất hiện khi chọn child-first?

Một plugin loader có thể override `loadClass` theo chủ đích:

```text
loadClass("demo.Feature")
    1. child.findClass
    2. parent.loadClass nếu child không có
```

Nhưng nếu không override phương thức resource:

```text
getResource("demo/config.properties")
    1. parent.getResource
    2. child.findResource
```

Khi parent/child cùng có cả class và resource, class sẽ đến từ **child**, resource lại đến từ **parent**. Việc khai báo một chính sách class child-first **không bảo đảm** toàn bộ resources đi kèm cũng child-first.

## 3. Mô hình nguồn gốc phải xét theo namespace và loại tài nguyên

Một chính sách hợp lý thường tách ba phạm vi:

| Phạm vi | Lớp nên lấy từ | Tài nguyên nên lấy từ | Vì sao? |
|---|---|---|---|
| **Lớp nền tảng/JDK** | Bootstrap/platform/parent | Các resource nền tảng theo API thích hợp | Giữ type identity và runtime rules |
| **Shared contracts** như `spi.Plugin` | Parent/shared loader | Shared schemas/config mặc định theo thiết kế chung | Host và plugin phải dùng một runtime interface |
| **Private implementation** như `plugins.alpha.*` | Plugin/child (khi có yêu cầu isolation) | Resource được đóng gói với phiên bản plugin trước, nếu đó là contract | Tránh implementation phiên bản B đọc tài nguyên phiên bản A |

Không phải **tất cả** tài nguyên nằm cùng package đều cần child-first. Ví dụ một cấu hình tổ chức cấp application có thể được thiết kế **chủ ý lấy từ parent** để nhiều plugin cùng dùng. Mục tiêu là **quy tắc được thiết kế rõ và kiểm thử được**, không phải “mọi lookup bắt buộc cùng thứ tự toàn cục”.

Tương tự, `META-INF/services/...` thường là **danh sách đóng góp từ nhiều JAR**, không phải tài nguyên đơn nên chọn duy nhất một bản. Khi xử lý loại này, cần xem `getResources` và contract của `ServiceLoader` thay vì chỉ đổi `getResource`.

## 4. Ví dụ Java 17+ chứng minh lỗi và cách chỉnh chính sách

Ta xây hai bản `demo.Feature` **cùng binary name nhưng nội dung khác nhau**, và hai tệp `demo/label.txt`. App loader thấy bản parent; loader con có directory riêng của child.

Sau đó so sánh hai loader:

- **`ChildFirstClassOnly`**: child-first đúng lớp `demo.Feature` nhưng giữ resource lookup parent-first.
- **`CoherentLoader`**: giữ cùng class policy, đồng thời ưu tiên child cho đúng `demo/label.txt` ở cả `getResource` lẫn `getResources`.

Cấu trúc:

```text
resource-order-demo/
├── src-parent/demo/Feature.java
├── src-child/demo/Feature.java
├── src-app/app/OrderDemo.java
└── out/
    ├── parent/demo/label.txt
    ├── child/demo/label.txt
    └── app/
```

### 4.1. Bản class ở parent

Tệp **`src-parent/demo/Feature.java`**:

```java
package demo;

public final class Feature {
    public static String origin() {
        return "parent-class";
    }
}
```

### 4.2. Bản class ở child

Tệp **`src-child/demo/Feature.java`**:

```java
package demo;

public final class Feature {
    public static String origin() {
        return "child-class";
    }
}
```

Hai class có cùng binary name nhưng **sẽ được định nghĩa bởi loaders khác nhau**, nên là **hai runtime classes khác nhau**. Demo không cố ép hai lớp đó về cùng kiểu; nó dùng reflection để gọi method public trả `String` (kiểu nền tảng chung).

### 4.3. Ứng dụng kiểm tra class và resource

Tệp **`src-app/app/OrderDemo.java`**:

```java
package app;

import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class OrderDemo {
    private static final String CLASS_NAME = "demo.Feature";
    private static final String RESOURCE_NAME = "demo/label.txt";

    static class ChildFirstClassOnly extends URLClassLoader {
        ChildFirstClassOnly(URL[] urls, ClassLoader parent) {
            super(urls, Objects.requireNonNull(parent));
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!CLASS_NAME.equals(name)) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    try {
                        result = findClass(name);
                    } catch (ClassNotFoundException missing) {
                        result = super.loadClass(name, false);
                    }
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }
    }

    static final class CoherentLoader extends ChildFirstClassOnly {
        CoherentLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        @Override
        public URL getResource(String name) {
            if (RESOURCE_NAME.equals(name)) {
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
            if (!RESOURCE_NAME.equals(name)) {
                return super.getResources(name);
            }

            Map<String, URL> ordered = new LinkedHashMap<>();
            Enumeration<URL> own = findResources(name);
            while (own.hasMoreElements()) {
                URL next = own.nextElement();
                ordered.putIfAbsent(next.toExternalForm(), next);
            }

            Enumeration<URL> parent = getParent().getResources(name);
            while (parent.hasMoreElements()) {
                URL next = parent.nextElement();
                ordered.putIfAbsent(next.toExternalForm(), next);
            }
            return Collections.enumeration(ordered.values());
        }
    }

    static String classValue(ClassLoader loader) throws Exception {
        Class<?> type = Class.forName(CLASS_NAME, true, loader);
        return (String) type.getMethod("origin").invoke(null);
    }

    static String resourceValue(URL url) throws IOException {
        try (InputStream stream = url.openStream()) {
            return new String(stream.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        URL childRoot = Path.of(args[0]).toUri().toURL();
        ClassLoader app = OrderDemo.class.getClassLoader();

        try (var naive = new ChildFirstClassOnly(
                    new URL[]{childRoot}, app);
             var aligned = new CoherentLoader(
                    new URL[]{childRoot}, app)) {

            System.out.println("Naive class: " + classValue(naive));
            System.out.println("Naive resource: "
                    + resourceValue(
                            naive.getResource(RESOURCE_NAME)));

            System.out.println("Aligned class: " + classValue(aligned));
            System.out.println("Aligned resource: "
                    + resourceValue(
                            aligned.getResource(RESOURCE_NAME)));

            List<String> items = new ArrayList<>();
            Enumeration<URL> urls =
                    aligned.getResources(RESOURCE_NAME);
            while (urls.hasMoreElements()) {
                items.add(resourceValue(urls.nextElement()));
            }
            System.out.println("Aligned all resources: "
                    + String.join(",", items));
        }
    }
}
```

Đây là chương trình hoàn chỉnh trong Java 17+. Một số chi tiết:

- `URLClassLoader` đã có `findClass`, `findResource`, `findResources` cho URL directories/JARs. Ta chỉ thay thứ tự chọn có chủ đích, không tự viết parser bytecode.
- `ChildFirstClassOnly` child-first **chỉ cho `demo.Feature`**, còn các class khác (đặc biệt Java/JDK classes) giữ parent-first.
- `getClassLoadingLock` và `findLoadedClass` bảo đảm yêu cầu đồng thời/repeat lookup không vô tình tạo class trùng trong một loader.
- `CoherentLoader.getResource` ưu tiên `findResource` của child cho `demo/label.txt` rồi mới fallback.
- `CoherentLoader.getResources` trả URL child trước, URL parent sau, có **khử trùng lặp theo chuỗi `toExternalForm()`** trong phạm vi demo. Đây không phải khẳng định mọi URL biểu diễn cùng một tài nguyên vật lý đều được chuẩn hóa/canonicalize như nhau.
- `Objects.requireNonNull(parent)` khiến `getParent()` luôn khác `null` trong demo. Loader tổng quát cần cân nhắc cả trường hợp bootstrap parent và Java platform resource lookup.
- Khi code gọi `Class.forName(CLASS_NAME, true, loader)`, loader được **truyền tường minh**; vì thế ta kiểm soát việc tìm đúng lớp từ namespace muốn thử.

### 4.4. Biên dịch và chạy

Bash (Linux/macOS/Git Bash), từ thư mục `resource-order-demo`:

```bash
mkdir -p out/parent/demo out/child/demo out/app

printf 'parent-resource\n' > out/parent/demo/label.txt
printf 'child-resource\n' > out/child/demo/label.txt

javac --release 17 -d out/parent src-parent/demo/Feature.java
javac --release 17 -d out/child src-child/demo/Feature.java
javac --release 17 -d out/app src-app/app/OrderDemo.java

java -cp "out/app:out/parent" app.OrderDemo out/child
```

Trên Windows PowerShell, tạo thư mục và resource như sau:

```powershell
New-Item -ItemType Directory -Force -Path out/parent/demo, out/child/demo, out/app | Out-Null
[System.IO.File]::WriteAllText("out/parent/demo/label.txt", "parent-resource" + [Environment]::NewLine)
[System.IO.File]::WriteAllText("out/child/demo/label.txt", "child-resource" + [Environment]::NewLine)
javac --release 17 -d out/parent src-parent/demo/Feature.java
javac --release 17 -d out/child src-child/demo/Feature.java
javac --release 17 -d out/app src-app/app/OrderDemo.java
java -cp "out/app;out/parent" app.OrderDemo out/child
```

Chú ý: Linux/macOS dùng dấu `:` phân cách các phần tử `java -cp`; Windows dùng `;`. Đây là quy tắc command-line classpath, không thay đổi tên resource `demo/label.txt`.

**Đầu ra đã kiểm tra** bằng `javac --release 17` và chạy trên JDK 21:

```text
Naive class: child-class
Naive resource: parent-resource
Aligned class: child-class
Aligned resource: child-resource
Aligned all resources: child-resource,parent-resource
```

### 4.5. Diễn giải kết quả

**Trước khi sửa resource policy:**

```text
ChildFirstClassOnly
  loadClass("demo.Feature")           -> child  -> "child-class"
  getResource("demo/label.txt")       -> parent -> "parent-resource"
```

Code đang chạy class phiên bản child nhưng đọc resource phiên bản parent. Nếu thay `label.txt` bằng template/schema/database mapping của hai phiên bản thư viện, mismatch có thể làm chương trình xử lý sai mà không ném exception.

**Sau khi đồng bộ chính sách:**

```text
CoherentLoader
  loadClass("demo.Feature")           -> child  -> "child-class"
  getResource("demo/label.txt")       -> child  -> "child-resource"
  getResources("demo/label.txt")      -> [child, parent]
```

Đối với tài nguyên được đánh dấu **private/versioned của plugin**, child-first là chính sách mong muốn. Với tài nguyên **shared/global** khác, loader này vẫn dùng chính sách parent-first mặc định.

**Giới hạn thử nghiệm:** Demo minh họa hai directories và một class/một resource để nhìn rõ vấn đề. Hệ thống production cần quy tắc cho **toàn namespace**, dependencies, `META-INF/services`, package/module constraints, URL/JAR provider và vòng đời loader; không nên sao chép điều kiện so sánh đúng một tên vào một hệ thống lớn.

## 5. Tại sao sửa getResource vẫn chưa đủ?

Có ít nhất ba đường đọc phổ biến:

```java
URL one = loader.getResource("demo/label.txt");

Enumeration<URL> all =
        loader.getResources("demo/label.txt");

try (InputStream stream =
        loader.getResourceAsStream("demo/label.txt")) {
    // Đọc byte nếu stream khác null.
}
```

Đây là đoạn mã minh họa đặt trong method với biến `loader` đã khai báo và có xử lý ngoại lệ khi cần.

Nếu bạn chỉ override `getResource` mà không override `getResources`:

- Đọc đơn lẻ có thể thấy child trước.
- API quét tất cả URL vẫn có thể liệt kê **parent trước**.
- Một framework dùng `getResources` có thể chọn cấu hình A thay vì B, tạo kết quả khác với code trực tiếp gọi `getResource`.

Ngược lại, nếu chỉ override `getResources` mà bỏ `getResource`, việc đọc file đơn lẻ có thể vẫn parent-first. Đừng cho rằng một phương thức mặc định luôn được implement bằng phương thức kia.

`getResourceAsStream` trên `ClassLoader` thường mở stream qua `getResource` của loader tương ứng; nếu dùng custom subclass override `getResourceAsStream` thì phải bảo đảm quy tắc mới không đi lệch chính sách đã chọn.

Cần xác minh **API thực tế** framework gọi. Một framework có thể dùng `Class.getResource`, `ClassLoader.getResource`, `Thread.currentThread().getContextClassLoader().getResources` hoặc một custom resource resolver với ordering riêng.

## 6. Cẩn thận: Class.getResource khác ClassLoader.getResource

Hai lệnh sau thường cùng chỉ một resource nhưng diễn giải tên khác:

```java
URL fromClass = demo.Feature.class.getResource("label.txt");

URL fromLoader = demo.Feature.class.getClassLoader()
        .getResource("demo/label.txt");
```

- `Class.getResource("label.txt")` dùng tên tương đối với **package của class**: `demo/label.txt`.
- `Class.getResource("/demo/label.txt")` dùng tên từ gốc namespace (dấu `/` đầu được bỏ khi tra).
- `ClassLoader.getResource("demo/label.txt")` yêu cầu tên resource với `/` phân tách package, **không có dấu `/` đầu**.

Nếu caller `demo.Feature` được định nghĩa ở plugin loader thì `Feature.class.getClassLoader()` trả defining loader đó. Vì thế một resource lookup dựa trên **đúng class liên quan** thường tốt hơn việc tùy tiện dùng `ClassLoader.getSystemResource`.

Tuy nhiên, với **named modules**, resource encapsulation còn tác động đến việc resource có được tìm thấy hay không. Một số resource trong package của module không được lộ ra qua `ClassLoader.getResource` nếu package không mở theo quy tắc API. `Class.getResource` và `Module.getResourceAsStream` cũng có hợp đồng cụ thể. Không kết luận rằng một `null` luôn do **thứ tự ưu tiên**; có thể là vấn đề module access.

### Class resource cũng cần được xét

Một mismatch sâu hơn xuất hiện khi `loadClass("demo.Feature")` định nghĩa class từ child, nhưng `getResource("demo/Feature.class")` trả **bytecode của parent**. Nếu tool inspection, scanner hoặc bytecode transformer dùng resource lookup để lấy class file rồi giả định bytes thuộc runtime class đã load, nó sẽ có thể phân tích nhầm phiên bản.

Không nên coi `getResource("...class")` là bằng chứng tuyệt đối về nguồn bytecode đã dùng: custom loader có thể giải mã, sinh hoặc biến đổi bytes trước `defineClass`; resource URL có thể không phản ánh những bước này. Nếu yêu cầu đồng bộ chặt, thiết kế một **provenance API** riêng và giữ manifest/hash/metadata của bytes mà loader thực sự định nghĩa.

## 7. Không đổi thứ tự của mọi resource một cách mù quáng

Có hai loại tài nguyên cần xử lý khác nhau:

### 7.1. Resource **exclusive** hoặc versioned

Ví dụ:

```text
plugins/acme/schema.json
plugins/acme/templates/view.html
plugins/acme/config/default.properties
```

Nếu những file này gắn trực tiếp với implementation của plugin đang child-first, ưu tiên **child** trước parent có thể phù hợp. Khi resource không có ở child, có thể fallback parent nếu contract cho phép; nếu fallback bị coi là nguy hiểm, **fail fast** để tránh vô tình dùng schema phiên bản khác.

Đây là quyết định chính sách:

| Tài nguyên thiếu ở child | Hành vi có thể chọn | Khi phù hợp |
|---|---|---|
| Có default shared hợp lệ | Fallback parent | Compatibility/default settings đã được thiết kế |
| Bắt buộc đồng phiên bản | Không fallback, báo lỗi | Schema, migration scripts hoặc template bắt buộc khớp implementation |
| Có nhiều lớp override | Dùng ordered overlay | Hệ thống cấu hình có precedence rõ ràng |
| Có nhiều contributors | Trả `getResources` đầy đủ | SPI, plugin registry, extension descriptors |

Đừng dựa vào “tìm thấy cái đầu tiên” nếu contract thực sự đòi **trộn nhiều nguồn**.

### 7.2. Resource **aggregation/multi-source**

Ví dụ:

```text
META-INF/services/com.example.spi.Plugin
META-INF/spring.factories                 (một số hệ sinh thái/phiên bản)
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Các file này thường mô tả đóng góp từ **nhiều JAR**. Nếu đổi `getResources` thành chỉ trả **một** resource child, framework có thể mất toàn bộ provider hoặc cấu hình parent.

Đối với metadata aggregation, chính sách hợp lý có thể là:

1. Tìm tất cả resources từ các nguồn được cho phép.
2. Quy định thứ tự nếu framework có contract liên quan.
3. Bảo đảm không làm mất entry hợp lệ.
4. Chỉ khử trùng lặp khi biết định nghĩa trùng lặp của API/frame­work; **URL trùng** không phải lúc nào cũng tương đương **nội dung/provider trùng**.
5. Kiểm thử startup, discovery, cache và reloading với nhiều JAR.

**Đặc biệt với ServiceLoader:** `ServiceLoader.load(service)` theo Java SE 17 dùng TCCL để khám phá providers; `ServiceLoader.load(service, loader)` dùng loader tường minh. Trong chế độ classpath, provider configuration nằm dưới `META-INF/services/<binary-name-of-service>`. Hành vi sai của `getResources` có thể khiến ServiceLoader bỏ sót descriptors hoặc chọn provider không mong muốn. Service type và provider class phải tương thích trong **cùng runtime type namespace**.

## 8. Parent-first cho shared API, child-first cho private implementation

Với plugin:

```text
ApplicationClassLoader
    ├── shared.api.Plugin
    └── shared.api.Message
           ^
           | parent delegation
           |
PluginClassLoader
    ├── plugins.acme.AcmePlugin
    ├── plugins.acme.schema.json
    └── META-INF/services/shared.api.Plugin
```

Một thiết kế điển hình:

- **`shared.api.*`**: luôn ưu tiên parent để app và plugin dùng cùng `Class<?>` của contract.
- **`plugins.acme.*`**: có thể ưu tiên child cho implementation nếu thật sự cần isolation.
- **`plugins/acme/...` resources**: nếu versioned cùng implementation, ưu tiên nguồn plugin hoặc đọc qua class liên quan.
- **`META-INF/services/...`**: có thể phải tổng hợp nhiều descriptors từ parent và child, không đơn giản lấy resource đầu.
- **JDK/platform classes**: không tự định nghĩa lại để tránh phá type identity và các quy tắc bảo vệ của JVM.

Nếu plugin tự định nghĩa lại `shared.api.Plugin` bằng child-first, code ở app không nhất thiết cast được plugin object về interface cùng tên. Khi đó lỗi không còn chỉ là resource mismatch mà là **class identity mismatch**.

### Một bản đồ chính sách nên được viết rõ

Thay vì những câu chung chung “child-first cho tất cả”, có thể xây một ma trận:

| Nhóm | Class lookup | Single resource lookup | Multiple resource lookup |
|---|---|---|---|
| `java.*`, runtime/platform | Parent/bootstrap | Theo platform/module APIs | Theo platform/module APIs |
| `shared.api.*` | Parent-first | Shared resources theo parent | Theo contract shared |
| `plugins.alpha.*` | Child-first (nếu cần) | Child-first với resources tương ứng | Child-first rồi parent, hoặc chỉ child |
| `META-INF/services/*` | Không có class cùng tên | Không phải cơ chế discovery đầy đủ | Tổng hợp entries phù hợp |
| `app/config/global.properties` | Không áp dụng | Parent-first, hoặc nguồn config tường minh | Theo contract application |

Bảng chỉ là **thiết kế mẫu**, không phải các quy tắc JVM tự áp dụng. Những namespace khác cần được phân loại dựa trên nhiệm vụ thực tế.

## 9. Cấu trúc custom loader production an toàn hơn

Có thể tập trung chính sách vào một bộ phân loại theo name (minh họa bằng giả mã):

```text
classPolicy(binaryName):
    if JDK hoặc shared contract:
        return PARENT_FIRST
    if plugin-private package:
        return CHILD_FIRST
    return PARENT_FIRST

resourcePolicy(resourceName):
    if plugin-private resource:
        return CHILD_FIRST
    if service/provider descriptor:
        return AGGREGATE
    return PARENT_FIRST
```

Sau đó ba đường nạp **đều** hỏi bộ phân loại:

```text
loadClass(name):
    quyết định classPolicy(name)
    kiểm tra findLoadedClass, khóa theo name, parent/child
    resolve khi cần

getResource(name):
    quyết định resourcePolicy(name)
    trả URL đầu phù hợp chính sách hoặc null

getResources(name):
    quyết định resourcePolicy(name)
    hợp nhất enumeration phù hợp contract
```

Dù có bộ phân loại chung, **không được ép mọi resource name thành một binary class name**. Class và resource có quy tắc đặt tên khác nhau; một namespace class có thể đi kèm nhiều loại tài nguyên không tương ứng trực tiếp 1:1.

Các điểm phải kiểm tra khi tự cài đặt:

1. `loadClass` vẫn kiểm tra `findLoadedClass` và dùng `getClassLoadingLock(name)` để tránh race/duplicate definitions.
2. Không bắt hoặc nuốt `VerifyError`, `LinkageError`, `ClassFormatError` hay `SecurityException` như thể là `ClassNotFoundException` để lặng lẽ fallback sang bản khác.
3. `getResources` tuân thủ `IOException` và hợp đồng enumeration; không tạo ra danh sách bị cắt nếu thư viện cần toàn bộ descriptors.
4. Giữ thứ tự có tính quyết định trong điều kiện input ổn định, và ghi rõ khi thứ tự bị chi phối bởi classpath order, module/provider semantics hoặc plugin priority.
5. Đóng streams, JAR handles và resource-specific file systems đúng vòng đời.
6. Không cho path/resource names không tin cậy dùng `../` hoặc URL ngoài phạm vi cho phép để thoát nguồn resource của plugin.
7. Không biến class loader thành security sandbox cho plugin không tin cậy: JVM class loading và OS isolation là các vấn đề khác nhau.
8. Thiết kế un/reload mà không giữ references vô hạn qua caches, thread context loader hoặc provider instances.

## 10. TCCL có thể làm đổi nguồn resource ở call site

Một chương trình có thể dùng:

```java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

URL url = tccl == null
        ? null
        : tccl.getResource("plugins/acme/config.properties");
```

Đây là đoạn minh họa trong method có import `java.net.URL`; nếu TCCL là child thì resource lookup có thể theo policy của child. Nhưng:

```java
URL url = SomeLibrary.class.getClassLoader()
        .getResource("plugins/acme/config.properties");
```

dùng **defining loader của `SomeLibrary`**, có thể là parent và có policy khác. Cùng resource name không bảo đảm cùng kết quả nếu lookup bắt đầu từ **hai loaders khác nhau**.

Khi tạm đổi TCCL, luôn khôi phục:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi framework/SPI có contract sử dụng TCCL.
} finally {
    thread.setContextClassLoader(previous);
}
```

Đây là snippet minh họa với `pluginLoader` có sẵn. Trong thread pools, không khôi phục TCCL có thể khiến request sau đọc resource/plugin provider của request trước; đồng thời TCCL giữ một strong reference tới loader cũ khiến plugin khó được unload.

**Quan trọng:** `Class.forName(String)` **không tự dùng TCCL**; overload một tham số dùng defining loader của calling class. Đừng sửa vấn đề resource bằng cách thay TCCL rồi cho rằng tất cả class lookups tự động chuyển sang child loader.

## 11. Manifest Class-Path, URLClassLoader và JAR resources

Nếu child có URL tới `plugin.jar`, `URLClassLoader` có thể tìm `.class` và resources trong JAR đó. Manifest `Class-Path` của JAR có thể mở rộng các URL phụ thuộc theo quy tắc của JAR specification; điều này làm tập nguồn được tìm thấy rộng hơn nhưng **không tự thay chính sách parent/child** bạn cài đặt.

Ví dụ:

```text
app.jar                       (parent)
  demo/Feature.class
  demo/label.txt

plugin.jar                    (child URLClassLoader)
  demo/Feature.class
  demo/label.txt
```

Nếu class policy child-first mà resource policy parent-first, vẫn gặp mismatch như demo dù nguồn là JAR thay vì directory.

Tài nguyên JAR thường có URL dạng:

```text
jar:file:/opt/plugins/plugin.jar!/demo/label.txt
```

URL này chỉ **entry trong archive**, không phải một `java.io.File` độc lập. Dùng `URL.openStream()`/`getResourceAsStream` để đọc thay vì `new File(url.toURI())`. Tránh parse bằng `substring` quanh `!/` nếu loader/framework có thể trả nested JAR URLs hoặc protocol đặc biệt.

**Classpath order không phải cùng khái niệm với loader delegation order.** Một URLClassLoader có thể có nhiều JAR theo thứ tự URLs, nhưng trước khi kiểm tra những URLs đó, `getResource` mặc định vẫn có thể nhờ parent tìm trước. Điều chỉnh thứ tự của `URL[]` ở child chưa đủ để child thắng resource parent khi parent có cùng tên.

## 12. Module system và những giới hạn của đồng bộ thứ tự

Trên Java 9+, **JPMS named modules** có module readability, exports/opens và chính sách resource encapsulation. Vì vậy:

- Một class có thể tồn tại trong module nhưng không thể được dùng ở nơi gọi do module/access rules.
- `ClassLoader.getResource` có thể không lộ non-`.class` resources thuộc package trong named module khi package chưa được `opens` theo quy tắc API.
- `Class.getResource`, `Module.getResourceAsStream` và `ClassLoader.getResource` có khác biệt hợp đồng; một URL `null` không đủ để kết luận chỉ do priority.
- Service discovery của named modules có thể dựa vào `provides ... with ...` và module layers, không nhất thiết vào `META-INF/services`.
- Custom loader không tự giải quyết module readability/exports/opens nếu code đã vi phạm các ràng buộc đó.

Khi hệ thống dùng JPMS, hãy quyết định liệu lớp và resource nên được truy cập **theo module ownership** thay vì giả định một parent/child URL search chain đơn giản. Với code gắn chặt với một module, `Module.getResourceAsStream` có thể là lựa chọn phù hợp hơn nếu access contract cho phép.

## 13. Kiểm thử để phát hiện mismatch trước production

### Kiểm thử phải kiểm tra **cả giá trị và nguồn**

Chỉ kiểm tra:

```java
assertNotNull(loader.getResource("demo/label.txt"));
```

là chưa đủ. Parent có thể trả một resource trùng tên, khiến test pass trong khi dùng sai phiên bản.

Hãy kiểm tra:

- `loadedClass.getClassLoader()` là defining loader mong đợi hay không.
- Bytecode/class behavior thuộc đúng phiên bản (ví dụ method trả `child-class`).
- URL resource đến từ archive/directory/module dự kiến.
- **Nội dung** resource có version/marker đồng bộ với implementation.
- `getResource` chọn đúng một nguồn; `getResources` có thứ tự và tập URL đúng theo contract.
- Caller dùng `Class.getResource`, loader tường minh hay TCCL thực tế.
- Trường hợp không có child resource có được fallback parent hay phải fail fast.
- Khi có hai JAR trùng tên resource hoặc provider descriptor, có bao nhiêu bản được xử lý?

**Lưu ý:** Việc suy ra class origin từ `getResource("...class")` chỉ là heuristic. Trong custom loader có transformation hoặc bytecode từ bộ nhớ, nguồn `.class` mà `getResource` trả có thể không phải bytes đã `defineClass`. Nếu cần bằng chứng mạnh, lưu provenance/hash tại thời điểm định nghĩa class.

### Ma trận test hữu ích

| Class từ parent? | Class từ child? | Resource parent? | Resource child? | Kỳ vọng |
|---|---|---|---|---|
| Có | Có | Có | Có | Child-class + child-resource với policy child-first private |
| Có | Không | Có | Không | Fallback parent nếu được phép |
| Không | Có | Không | Có | Child cung cấp cả hai |
| Có | Có | Có | Không | Fail-fast hoặc fallback theo contract, không im lặng |
| Có | Có | Không | Có | Child resource; class theo policy định sẵn |
| Nhiều provider JAR | Nhiều provider classes | Nhiều descriptors | Nhiều descriptors | `getResources`/SPI không bỏ sót contributions hợp lệ |

Đừng chỉ test trường hợp child và parent không trùng tên — khi đó hai chính sách khác nhau có thể trông giống nhau. **Phải tạo một fixture cố ý trùng binary name và resource name** như demo ở phần 4.

## 14. Dấu hiệu trong ứng dụng thực tế

### A. Class của plugin B nhưng cấu hình phiên bản A

Triệu chứng: tính năng plugin mới đã được nạp nhưng ứng dụng dùng một schema cũ, một enum mapping cũ hoặc template lỗi thời.

Kiểm tra: `Class.getClassLoader`, nơi class được định nghĩa, `getResource` URL, nội dung resource và thứ tự `getResources`. Nếu dùng child-first class mà parent-first resource, sửa chính sách hoặc dùng API đọc resource gắn với class tương ứng.

### B. SPI provider không được phát hiện dù class tồn tại

Triệu chứng: `Class.forName("plugins.X", false, pluginLoader)` hoạt động, nhưng `ServiceLoader.load(Service.class, pluginLoader)` không tìm được provider.

Kiểm tra: tệp `META-INF/services/<service-binary-name>` có được đóng gói, `getResources` có trả đủ descriptors, provider type có dùng **đúng shared service interface**, và module/TCCL context có phù hợp không.

### C. Framework lấy cấu hình khác với chương trình tự đọc

Triệu chứng: `loader.getResource(name)` trả child URL, nhưng framework vẫn đọc parent resource.

Kiểm tra: framework có dùng `getResources` không? Có dùng system loader, TCCL, `Class.getResource` hay module resource API khác không? Có cache resource list hoặc config tại lần khởi động trước không?

### D. “Chạy IDE đúng, đóng JAR sai”

IDE có thể đưa thư mục resources và classes vào classpath theo một thứ tự khác với executable JAR/container. Khi JAR deployment thêm parent libraries hoặc plugin loader, tên tài nguyên trùng có thể bắt đầu gây shadowing.

Kiểm tra build output/JAR entries bằng `jar --list --file ...` và đối chiếu loader/url thực tế khi chạy, không chỉ dựa trên source directory.

### E. Hot reload vẫn dùng resource cũ

Nếu loader thế hệ mới tải class B nhưng một singleton ở parent đã cache URL/resource A, đổi loader không tự vô hiệu hóa cache đó. Cần thiết kế cache key/lifecycle theo plugin generation hoặc loại bỏ cache cũ.

## 15. Các lỗi thiết kế cần tránh

1. **Override `loadClass` child-first cho mọi lớp** mà không giữ shared APIs ở parent: dẫn tới trùng class identity và `ClassCastException`.
2. **Override chỉ `getResource`**, quên `getResources`: framework aggregation vẫn dùng thứ tự cũ.
3. **Override `getResources` chỉ trả một URL đầu tiên**, làm mất service descriptors và plugin contributions.
4. **Đồng bộ bằng cách đổi tất cả resources sang child-first** bất chấp config shared/global hoặc module rules.
5. **Dùng `getResource("...class")` làm bằng chứng tuyệt đối về bytes đã load** dù code dùng transformations/custom sources.
6. **Bắt và che `LinkageError`, `VerifyError` như thể chỉ là tài nguyên không thấy**; cần phân biệt lỗi class loading và mismatch resource.
7. **Nhầm resource name với class name**; `getResource("a.B")` và `loadClass("a/B.class")` không phải hai cách gọi tương đương.
8. **Đọc JAR resource bằng `new File(url.toURI())`**; URL `jar:` không phải filesystem file.
9. **Quên kiểm tra `null`/`IOException`**, dựa vào giả định mọi resource hiện diện.
10. **Quên reset TCCL hoặc giải phóng URLClassLoader/caches** sau plugin lifecycle.
11. **Không kiểm thử trường hợp parent và child cùng có tên**, nên bỏ sót mismatch cho đến deployment thực.
12. **Giả định thay classpath order đủ sửa policy**, khi bản thân parent delegation đã quyết định ưu tiên trước classpath URLs của child.

## 16. Câu hỏi tự kiểm tra

**1. Child override `loadClass` thành child-first. `getResource` có tự child-first không?** Không. `getResource` là đường lookup khác và mặc định của `ClassLoader` thường ưu tiên parent.

**2. Vì sao class child và resource parent có thể cùng được tìm thấy mà ứng dụng vẫn sai?** Hai phiên bản không nhất quán; class B có thể đọc schema/config/template của A.

**3. Tại sao không chỉ sửa `getResource`?** Vì một số framework/API dùng `getResources` để lấy nhiều resources. Không chỉnh phương thức đó thì thứ tự/tập kết quả có thể vẫn khác.

**4. Trong ví dụ, vì sao `CoherentLoader.getResources` trả child rồi parent?** Resource `demo/label.txt` được phân loại private/versioned theo chính sách demo; child được ưu tiên nhưng ta vẫn cho phép liệt kê bản parent.

**5. Có nên trả child-only cho mọi `META-INF/services/*`?** Không. SPI thường cần phát hiện providers từ nhiều nguồn; phải giữ đúng aggregation contract.

**6. Nếu plugin dùng interface cùng tên nhưng do loader khác định nghĩa, thứ tự resource đúng đã đủ chưa?** Chưa. Shared interface cần cùng runtime identity; class identity phụ thuộc defining loader.

**7. `Class.getResource("label.txt")` và `ClassLoader.getResource("label.txt")` có nhất thiết tìm cùng entry không?** Không. API `Class` giải quyết tên tương đối với package; `ClassLoader` dùng resource name từ gốc loader namespace.

**8. Nếu resource lookup trả `null` trong named module, có chắc priority sai không?** Không. Module encapsulation/opens cũng có thể ngăn resource hiển thị.

**9. Đổi TCCL có tự làm `Class.forName(String)` dùng loader mới không?** Không. `Class.forName(String)` dùng defining loader của caller; chỉ những API có chủ đích đọc TCCL mới bị ảnh hưởng.

**10. Kiểm thử nào bắt lỗi nhanh nhất?** Tạo parent và child có **trùng class name lẫn resource name** nhưng giá trị khác, rồi assert class behavior, resource content và thứ tự `getResources`.

## 17. Tài liệu chuẩn

- Java SE 17 API, `ClassLoader`: `loadClass`, `getResource`, `getResources`, `findResource`, `findResources` và resource-stream methods: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `URLClassLoader`: class/resource lookup từ URLs và `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 API, `Class.getResource` và `Class.getClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 API, `ServiceLoader`: provider discovery từ resource descriptors/modules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- JVMS §5.3, *Creation of Classes and Interfaces*, về defining/initiating loaders và runtime class identity: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3

**Ghi nhớ:** Một plugin có thể chạy **class từ child** mà lại đọc **resource từ parent** nếu chỉ thay `loadClass`. Muốn tránh lệch phiên bản, hãy xây **ma trận chính sách theo namespace và loại tài nguyên**, đồng bộ `getResource` với `getResources` khi cần, bảo vệ shared API, và kiểm thử bằng các lớp/tài nguyên trùng tên ở hai nguồn. Với service descriptors hay tài nguyên tổng hợp, “nhất quán” thường có nghĩa **tổng hợp đúng** chứ không phải luôn chỉ lấy child.
