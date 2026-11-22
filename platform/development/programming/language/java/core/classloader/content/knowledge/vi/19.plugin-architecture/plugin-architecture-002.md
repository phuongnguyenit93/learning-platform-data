# Chọn ClassLoader cho API chung và phụ thuộc riêng trong kiến trúc plugin Java

Một hệ thống plugin muốn đạt hai mục tiêu có vẻ mâu thuẫn: **host và plugin cần hiểu cùng một hợp đồng giao tiếp**, nhưng **mỗi plugin có thể cần thư viện triển khai riêng, thậm chí khác phiên bản với host hoặc plugin khác**. Nếu đưa tất cả class vào một application classpath, version conflict có thể xảy ra. Nếu tạo một child-first loader cho mọi thứ, host và plugin có thể không còn sử dụng cùng runtime interface để giao tiếp.

Giải pháp kiến trúc thông dụng là phân chia **ownership theo loại class**:

- **Shared API** — interface SPI, DTO, exception, callback và các hợp đồng thật sự qua biên giới host/plugin: do **loader cha chung** định nghĩa; các plugin delegate khi cần class API.
- **Plugin implementation** — class thực thi nghiệp vụ chỉ plugin sử dụng: do **plugin loader riêng** định nghĩa.
- **Private dependencies** — thư viện mà một plugin sở hữu và muốn cô lập phiên bản: thường do **plugin loader** định nghĩa với chính sách tìm kiếm có chọn lọc; không vô tình dùng bản cùng tên của parent.
- **JDK/platform classes** — tiếp tục ủy quyền theo cơ chế phù hợp, không tự “nạp lại” `java.*`.

**Nguyên tắc ghi nhớ:** *Chia sẻ hợp đồng; cô lập chi tiết triển khai.* Lựa chọn loader đúng phải dựa trên **class identity**, **hợp đồng nhị phân**, **version thực được nạp**, **resource visibility**, **vòng đời plugin** và **nhu cầu tương tác**, không chỉ dựa vào sơ đồ cây các loader.

## 1. Vì sao kiến trúc plugin cần nhiều loader?

Trong Java, runtime identity của một class/interface là **cặp (binary name, defining class loader)**:

~~~text
Runtime type = (binary name, defining loader)

(api.Greeting, AppLoader)        -> shared interface
(api.Greeting, PluginLoaderA)    -> interface KHÁC nếu child tự define
(plugin.impl.Greeter, LoaderA)   -> implementation A
(plugin.impl.Greeter, LoaderB)   -> implementation B khác
~~~

Hai file `api/Greeting.class` giống từng byte, nhưng được hai defining loaders khác nhau định nghĩa thì vẫn là **hai runtime types khác nhau**. Điều này ảnh hưởng trực tiếp tới `instanceof`, cast, method signatures, reflection và khả năng truyền object giữa host/plugin.

### Sơ đồ khuyến nghị

~~~text
                   Bootstrap / Platform
                           |
                   Application loader
                  /        |          \
       api.Greeting  api.PluginContext  shared DTO
                           |
                  +--------+--------+
                  |                 |
            Plugin loader A   Plugin loader B
                  |                 |
       plugin.impl.Greeter   plugin.impl.Greeter
       deps.private.Json v1 deps.private.Json v2
       resources A          resources B
                  |                 |
                  +--------+--------+
                           |
                 host giao tiếp qua
                  cùng api.Greeting
~~~

Ở đây, hai plugin có thể tự định nghĩa class implementation với **cùng tên nhị phân**, miễn host không cố coi chúng là một runtime implementation type. Cả hai object đều có thể được ép về **cùng interface `api.Greeting`** do parent định nghĩa.

### Defining loader khác initiating loader

~~~java
Class<?> apiType = pluginLoader.loadClass("api.Greeting");
ClassLoader defining = apiType.getClassLoader();
~~~

Đây là mảnh minh họa với biến `pluginLoader` đã có. Nếu plugin loader ủy quyền cho parent, `defining` là **parent**, không phải `pluginLoader`. Loader nhận lời gọi `loadClass` không nhất thiết là loader định nghĩa class.

Khi debug, hỏi:

~~~java
System.out.println(apiType == api.Greeting.class);
System.out.println(apiType.getClassLoader()
        == api.Greeting.class.getClassLoader());
~~~

Hai giá trị cùng là `true` trong cấu hình API chung đúng. Nhưng kiểm tra riêng `getName()` **không đủ**, vì hai `Class<?>` khác loader vẫn có thể cùng tên.

## 2. Phân loại class trước khi chọn parent hoặc child

| Nhóm class | Ví dụ | Nơi thường nên định nghĩa | Lý do |
|---|---|---|---|
| API interface qua boundary | `api.Greeting`, `spi.PaymentProvider` | Parent chung | Giữ một runtime type để cast và invoke |
| Shared DTO, callback, exception | `api.Request`, `api.PluginException` | Parent chung | Method signature qua boundary cần cùng identity |
| Java/platform | `java.lang.String`, `java.sql.*` | Bootstrap/platform/parent phù hợp | Không định nghĩa lại Java platform types |
| Implementation của plugin | `plugin.impl.Greeter` | Plugin loader | Tách vòng đời và version |
| Private implementation dependency | `deps.format.Formatter` | Plugin loader nếu cần version riêng | Tránh host version che plugin version |
| Shared dependency được dùng trong API | `api.json.JsonNode` nếu type xuất hiện trong method public | Parent hoặc contract thống nhất | Tránh hai bản không tương thích trong signature |
| Logging/service facade chung | API của logging/metrics hoặc SPI | Thường parent | Tránh split API, tạo policy rõ cho adapter |
| Resources private | `plugin/config.txt`, template | Nguồn riêng plugin, lookup có chủ đích | Cấu hình không bị resource từ parent che khuất |

**Không quyết định chỉ theo tên JAR.** Một thư viện có thể gồm phần API thực sự chia sẻ và phần implementation riêng. Nếu các lớp của một package cần package-private access lẫn nhau, hãy cân nhắc giữ chúng trong **cùng defining loader**, vì JVM xác định runtime package từ **package name + defining loader**.

### Câu hỏi trước khi “để dependency ở child”

1. Type của thư viện đó có xuất hiện trong public method/field của SPI không?
2. Host có ép kiểu, reflection, deserialize hoặc gọi callback với object thuộc thư viện ấy không?
3. Nó có dựa vào `ServiceLoader`, `Class.forName` hoặc thread context class loader không?
4. Nó dùng native libraries, static singletons, global registries, thread pools hoặc log manager không?
5. Có hai version cùng tồn tại và thực sự cần cả hai không?
6. Library có dùng package-private/nestmate giữa các class mà bạn dự định chia loader không?
7. Nếu plugin redeploy, reference nào có thể giữ loader cũ sống?
8. Có cơ chế mô-đun JPMS hoặc framework launcher riêng không?

Nếu type phải đi qua boundary, thường phải đưa type đó vào một **shared contract** hoặc thay bằng định dạng trung lập (ví dụ message/schema) thay vì cho mỗi bên định nghĩa một bản riêng.

## 3. Parent-first: mặc định an toàn cho API chung nhưng có thể chọn sai dependency

`ClassLoader.loadClass(String, boolean)` mặc định thực hiện:

~~~text
Child.loadClass(name)
  -> findLoadedClass(name)
  -> parent.loadClass(name)  [nếu parent tìm được, dùng class parent]
  -> child.findClass(name)   [nếu parent không tìm được]
  -> resolve nếu được yêu cầu
~~~

Ưu điểm của **parent-first**:

- Giữ host/plugin dùng chung API, DTO và những lớp ở parent.
- Không vô tình định nghĩa lại `java.*` và shared API ở mỗi child.
- Dễ khớp với cách làm việc của `URLClassLoader` mặc định.
- Giảm số bản trùng class metadata và đơn giản hóa nhiều đường dependency.

Nhưng có một rủi ro:

~~~text
Host classpath:
  deps.format.Formatter v1
Plugin JAR:
  deps.format.Formatter v2
PluginLoader: parent-first
~~~

Nếu parent nhìn thấy `deps.format.Formatter` v1, plugin loader trả **v1** khi được yêu cầu nạp class cùng tên, dù JAR của plugin chứa **v2**.

Nếu plugin compile dựa vào method chỉ v2 mới có, JVM có thể báo `NoSuchMethodError` hoặc lỗi linkage khác ở runtime. “Class tìm được” không chứng minh **binary compatibility**. Vì vậy parent-first là lựa chọn tốt cho **API dùng chung**, nhưng không mặc nhiên tốt cho mọi **private dependency**.

## 4. Child-first có chọn lọc: chỉ áp dụng cho implementation/private dependency

Khi plugin cần phiên bản riêng của một thư viện cùng binary name, ta có thể thay chính sách tìm class **cho một tập namespace giới hạn**:

~~~text
Tên lớp                        Chính sách
------------------------------------------------
java.*                         mặc định / delegation
api.*                          parent-first
shared.contract.*              parent-first
plugin.impl.*                  child-first (nếu có nhu cầu)
deps.format.*                  child-first
mọi tên còn lại                parent-first
~~~

Cách triển khai **không** nên đơn giản là “mọi tên child-first”:

- Nếu `api.Greeting` nằm trong plugin JAR và child tự định nghĩa nó, host không thể cast provider về `api.Greeting` của host.
- Nếu plugin dùng các API framework phải chia sẻ, tải bản khác có thể phá method signatures, service registries hoặc phản xạ.
- JVM đặt ràng buộc đối với package `java.*`; custom loader không được tự định nghĩa core Java classes.
- Một thư viện private có thể gọi interface của host; khi đó phần API của thư viện phải được chia sẻ đúng ranh giới.

**Mục tiêu không phải “child-first nhiều nhất”, mà là “child-first đúng nơi cần đổi version”.**

### Tránh phân chia các class phụ thuộc package-private

Giả sử hai class `p.Accessor` và `p.Secret` dùng các thành viên package-private. Nếu chúng được định nghĩa bởi hai loaders khác nhau dù source có cùng `package p;`, chúng thuộc **hai runtime packages khác nhau**. Một lời gọi bytecode có thể phát sinh `IllegalAccessError`.

Vì vậy chính sách namespace nên được thiết kế theo **cụm package/nhóm thư viện nhất quán**, không theo vài class đơn lẻ bị tách ngẫu nhiên qua loaders.

## 5. Ví dụ Java 17+ đầy đủ: parent-first dùng v1, private dependency dùng v2

Thí nghiệm sau cho thấy:

- Host có `api.Greeting` và `deps.format.Formatter` phiên bản **v1** trên application classpath.
- Plugin chứa `plugin.impl.PluginGreeting` và một bản `deps.format.Formatter` phiên bản **v2** trong JAR riêng.
- Loader mặc định **parent-first** khiến plugin chạy với dependency **host-v1**.
- Loader **child-first chỉ cho `deps.format.*`** cho phép plugin dùng **plugin-v2**.
- Cả hai provider đều **cast thành công về một `api.Greeting` duy nhất** vì shared API được parent định nghĩa.
- Hai plugin loaders riêng biệt cho ra hai bản runtime class implementation/dependency khác nhau.
- Resource cùng tên có thể vẫn được lấy từ parent do resource lookup độc lập với policy tải class.

Không sử dụng Maven, Gradle hay thư viện bên ngoài. Mã biên dịch và chạy được trên **JDK 17+**.

### 5.1. Cấu trúc project

~~~text
project/
  src/
    api/api/Greeting.java
    v1/deps/format/Formatter.java
    v2/deps/format/Formatter.java
    plugin/plugin/impl/PluginGreeting.java
    host/LoaderBoundaryDemo.java
  out/
    api/
    lib-v1/
    lib-v2/
    plugin/
    host/
  dist/
    private-plugin.jar
~~~

Các thư mục `out` và `dist` được tạo trong bước build.

### 5.2. API chung: `src/api/api/Greeting.java`

~~~java
package api;

public interface Greeting {
    String message();
}
~~~

Đây là contract mà host biết từ lúc biên dịch. **Không copy `api/Greeting.class` vào JAR private plugin.** Plugin compile dựa vào bản API ở `out/api`, còn runtime plugin loader ủy quyền tìm `api.Greeting` về parent.

### 5.3. Formatter phiên bản host: `src/v1/deps/format/Formatter.java`

~~~java
package deps.format;

public final class Formatter {
    private Formatter() {
    }

    public static String identity() {
        return "host-v1";
    }
}
~~~

### 5.4. Formatter phiên bản riêng plugin: `src/v2/deps/format/Formatter.java`

~~~java
package deps.format;

public final class Formatter {
    private Formatter() {
    }

    public static String identity() {
        return "plugin-v2";
    }
}
~~~

Hai nguồn có cùng binary name `deps.format.Formatter` nhưng kết quả khác. Đây là một ví dụ tối giản cho **version conflict**, không phải lời khuyên đặt hai thư viện cùng tên trên một classpath.

### 5.5. Implementation: `src/plugin/plugin/impl/PluginGreeting.java`

~~~java
package plugin.impl;

import api.Greeting;
import deps.format.Formatter;

public final class PluginGreeting implements Greeting {
    public PluginGreeting() {
    }

    @Override
    public String message() {
        return Formatter.identity();
    }
}
~~~

File này sẽ được compile với Formatter **v2**, nhưng khi chạy với parent-first nó vẫn có thể nhận Formatter **v1**. Trong ví dụ hai version có cùng method signature nên chạy được với hai kết quả khác nhau. Nếu version thực tế không giữ binary compatibility, bạn có thể thấy lỗi linkage thay vì chỉ kết quả khác.

### 5.6. Host và custom loader: `src/host/LoaderBoundaryDemo.java`

~~~java
import api.Greeting;
import deps.format.Formatter;

import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public final class LoaderBoundaryDemo {

    static final class PolicyLoader extends URLClassLoader {
        private final boolean isolatePrivateDeps;

        PolicyLoader(String name, URL[] sources, ClassLoader parent,
                     boolean isolatePrivateDeps) {
            super(name, sources, parent);
            this.isolatePrivateDeps = isolatePrivateDeps;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {

            // Shared API, Java classes và mọi namespace khác:
            // dùng parent-first mặc định.
            if (!isolatePrivateDeps || !name.startsWith("deps.format.")) {
                return super.loadClass(name, resolve);
            }

            // Chỉ namespace private dependency được child-first.
            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);

                if (found == null) {
                    try {
                        found = findClass(name);
                    } catch (ClassNotFoundException absentInPlugin) {
                        found = super.loadClass(name, false);
                    }
                }

                if (resolve) {
                    resolveClass(found);
                }
                return found;
            }
        }
    }

    private static Greeting instantiate(PolicyLoader loader)
            throws Exception {
        Class<?> type = loader.loadClass(
                "plugin.impl.PluginGreeting");

        return (Greeting) type.getConstructor().newInstance();
    }

    private static String text(URL url) throws Exception {
        if (url == null) {
            return "missing";
        }
        try (InputStream in = url.openStream()) {
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LoaderBoundaryDemo <plugin-jar>");
        }

        URL jar = Path.of(args[0]).toAbsolutePath()
                .toUri().toURL();
        URL[] sources = {jar};
        ClassLoader parent =
                LoaderBoundaryDemo.class.getClassLoader();

        try (PolicyLoader parentFirst =
                    new PolicyLoader("parent-first", sources,
                            parent, false);
             PolicyLoader privateFirst =
                    new PolicyLoader("private-first", sources,
                            parent, true);
             PolicyLoader otherPrivate =
                    new PolicyLoader("private-2", sources,
                            parent, true)) {

            Greeting normal = instantiate(parentFirst);
            Greeting isolated = instantiate(privateFirst);

            Class<?> apiFromPlugin = privateFirst.loadClass(
                    "api.Greeting");
            Class<?> ownLib = privateFirst.loadClass(
                    "deps.format.Formatter");
            Class<?> parentLib = parentFirst.loadClass(
                    "deps.format.Formatter");

            System.out.println("host library: "
                    + Formatter.identity());
            System.out.println("parent-first plugin: "
                    + normal.message());
            System.out.println("private-first plugin: "
                    + isolated.message());

            System.out.println("same shared API: "
                    + (apiFromPlugin == Greeting.class));
            System.out.println("plugin cast works: "
                    + (isolated instanceof Greeting));
            System.out.println("parent-first library from parent: "
                    + (parentLib.getClassLoader() == parent));
            System.out.println("private library from child: "
                    + (ownLib.getClassLoader() == privateFirst));

            Class<?> otherLib = otherPrivate.loadClass(
                    "deps.format.Formatter");
            System.out.println("private library types equal: "
                    + (ownLib == otherLib));

            Class<?> otherImplementation = otherPrivate.loadClass(
                    "plugin.impl.PluginGreeting");
            System.out.println("implementation types equal: "
                    + (isolated.getClass() == otherImplementation));

            String resourceName = "plugin/config.txt";
            System.out.println("resource via loader: "
                    + text(privateFirst.getResource(resourceName)));
            System.out.println("resource from child URL: "
                    + text(privateFirst.findResource(resourceName)));
        }
    }
}
~~~

**Giải thích kỹ thuật:**

1. `PolicyLoader` kế thừa `URLClassLoader`. Loader này có danh sách URL chứa plugin JAR và parent là application loader.
2. Mặc định toàn bộ class names vẫn theo `super.loadClass`. Chỉ class bắt đầu bằng `deps.format.` được ưu tiên `findClass` của child.
3. Bên trong nhánh child-first, `getClassLoadingLock(name)` cùng `findLoadedClass(name)` giúp tránh tự định nghĩa lại cùng class name trong một loader. `resolveClass` xử lý khi `resolve=true`.
4. `api.Greeting` không thuộc nhánh child-first nên được parent định nghĩa và chia sẻ. Hai object plugin khác implementation loader vẫn tương thích API chung.
5. `plugin.impl.PluginGreeting` không nằm trong application classpath của host; cả parent-first lẫn private-first loaders tự định nghĩa bản plugin riêng.
6. `deps.format.Formatter` có ở host và plugin. Loader mặc định trả class của parent; private-first loader định nghĩa class từ plugin JAR.
7. `getResource` mặc định tiếp tục dùng resource delegation của ClassLoader. **Đổi `loadClass` không tự đổi `getResource`**.
8. `findResource` chỉ tra cứu các URL riêng của URLClassLoader; dùng để minh họa nơi chứa resource, không phải khuyến khích truy cập resource bằng API protected của mọi loader.

### 5.7. Lệnh biên dịch và đóng gói

Các lệnh sau dùng **Bash/Linux/macOS**, chạy từ thư mục `project`:

~~~bash
mkdir -p out/api out/lib-v1 out/lib-v2 out/plugin out/host dist
mkdir -p out/lib-v1/plugin out/plugin/plugin

javac -d out/api src/api/api/Greeting.java
javac -d out/lib-v1 src/v1/deps/format/Formatter.java
javac -d out/lib-v2 src/v2/deps/format/Formatter.java

javac -cp "out/api:out/lib-v2" -d out/plugin \
    src/plugin/plugin/impl/PluginGreeting.java

javac -cp "out/api:out/lib-v1" -d out/host \
    src/host/LoaderBoundaryDemo.java

printf 'host-resource\n' > out/lib-v1/plugin/config.txt
printf 'plugin-resource\n' > out/plugin/plugin/config.txt

jar --create --file dist/private-plugin.jar \
    -C out/plugin . -C out/lib-v2 .

java -cp "out/api:out/host:out/lib-v1" \
    LoaderBoundaryDemo dist/private-plugin.jar
~~~

Lưu ý:

- `out/api` là **API dùng chung**, xuất hiện trên classpath host.
- `out/lib-v1` là dependency host, vì thế application loader thấy Formatter v1 và resource `plugin/config.txt` của host.
- `out/lib-v2` là dependency riêng của plugin, chỉ dùng lúc biên dịch plugin và khi đóng gói vào `private-plugin.jar`; **không** đưa nó vào application classpath của lệnh chạy.
- `out/plugin` cũng **không** nằm trong application classpath. Plugin implementation chỉ đến từ URLClassLoader.
- JAR private chứa class implementation, thư viện v2 và resource plugin, nhưng **không chứa `api/Greeting.class`**.
- `javac -cp ...` là **compile-time classpath**. Nó không quyết định policy runtime của custom loader.

Sau khi build, các entry quan trọng bên trong `dist/private-plugin.jar` là:

~~~text
plugin/impl/PluginGreeting.class
deps/format/Formatter.class
plugin/config.txt
~~~

Có thể kiểm tra bằng:

~~~bash
jar --list --file dist/private-plugin.jar
~~~

Nếu `api/Greeting.class` xuất hiện trong plugin JAR do cách đóng gói nhầm, dù parent-first thường vẫn ưu tiên bản parent, việc **trùng API bytecode** là dấu hiệu cần sửa packaging để không tạo điều kiện cho một policy khác tự định nghĩa lại shared API.

### 5.8. Stdout và giải thích

**Stdout dự kiến trên Java 17+ khi các file đúng như trên:**

~~~text
host library: host-v1
parent-first plugin: host-v1
private-first plugin: plugin-v2
same shared API: true
plugin cast works: true
parent-first library from parent: true
private library from child: true
private library types equal: false
implementation types equal: false
resource via loader: host-resource
resource from child URL: plugin-resource
~~~

Đọc theo từng nhóm:

- `host library: host-v1`: app loader nạp `deps.format.Formatter` từ host output v1.
- `parent-first plugin: host-v1`: plugin class được loader riêng định nghĩa, nhưng tham chiếu `Formatter` được parent trả về v1.
- `private-first plugin: plugin-v2`: nhánh child-first cho `deps.format.*` buộc private dependency đến từ plugin JAR.
- `same shared API: true`: plugin loader cũng nhìn thấy đúng `api.Greeting.class` mà host sử dụng.
- `plugin cast works: true`: object plugin được tạo từ class riêng nhưng implements shared API do parent định nghĩa, nên host cast thành công.
- `parent-first library from parent: true` và `private library from child: true` minh chứng không nên dựa vào tên class để đoán defining loader.
- `private library types equal: false`: hai child loaders riêng định nghĩa hai runtime `deps.format.Formatter` dù đọc cùng plugin JAR.
- `implementation types equal: false`: class implementation từ hai plugin loader cũng khác identity.
- `resource via loader: host-resource`: `ClassLoader.getResource` mặc định hỏi parent trước, host đã có resource cùng tên.
- `resource from child URL: plugin-resource`: `URLClassLoader.findResource` tìm resource chỉ ở nguồn child.

**Điểm rất quan trọng:** class policy child-first có chọn lọc **không làm resource policy child-first tương ứng**. Nếu plugin gọi nhầm `getResource("plugin/config.txt")` và parent có một bản trùng, cấu hình của host có thể che cấu hình của plugin dù class `Formatter` đã được cô lập v2.

### 5.9. Windows PowerShell

Trên Windows, thay cách tạo thư mục/file bằng `New-Item` và `Set-Content`; lệnh `javac`, `jar` và `java` vẫn dùng tương tự. Dấu phân cách `-cp` là **`;`**, ví dụ:

~~~powershell
java -cp "out/api;out/host;out/lib-v1" LoaderBoundaryDemo dist/private-plugin.jar
~~~

Nếu dùng PowerShell để tạo resource, lưu UTF-8 đúng dữ liệu, không thêm ký tự không mong muốn; trong ví dụ, `String.strip()` bỏ ký tự xuống dòng của resource khi in.

## 6. Hợp đồng nhị phân và dependency leak qua public API

Chọn loader cho dependency không chỉ là lựa chọn nơi lưu JAR. Ví dụ interface:

~~~java
package api;

public interface ReportPlugin {
    deps.format.Document create();
}
~~~

Đây là **mảnh minh họa**; cần type `deps.format.Document` thực sự có thể nạp từ API/module tương ứng.

Ở đây `deps.format.Document` xuất hiện trong **public method signature**. Nếu mỗi plugin tự định nghĩa type `Document` khác nhau, host nhận các runtime types khác identity và có thể không gọi/cast/link đúng contract.

**Hướng thiết kế tốt hơn:**

~~~java
package api;

public interface ReportPlugin {
    api.DocumentDto create();
}
~~~

Trong mô hình này, `api.DocumentDto` được loader chung định nghĩa. Plugin có thể chuyển đổi từ object `deps.format.Document` private sang DTO chung trước khi trả về.

Khi plugin cần dùng một dependency type làm contract công khai, **dependency không còn thật sự private**. Bạn cần một trong những phương án:

1. Nâng dependency API type thành **shared dependency** được parent định nghĩa, thống nhất version/ABI.
2. Tạo **anti-corruption layer/adapter** chuyển dữ liệu từ private type sang DTO thuộc shared API.
3. Dùng dữ liệu trao đổi độc lập class identity (schema/message, JSON, protobuf phù hợp) nếu cần biên giới linh hoạt hoặc ngoài tiến trình.
4. Version contract một cách rõ ràng khi có thay đổi không tương thích.

Không nên đưa cả dependency v1 và v2 vào parent rồi hy vọng JVM chọn bản theo caller. Với một binary name và một defining loader, JVM không thể đồng thời định nghĩa hai version cùng tên trong chính loader đó.

## 7. Shading, relocation và trường hợp không cần custom loader

Không phải version conflict nào cũng buộc viết một `ClassLoader` child-first. Một lựa chọn là **shading/relocation**: build tool đổi binary package name của dependency private, ví dụ:

~~~text
deps.format.Formatter
        |
        v
pluginA.shadow.deps.format.Formatter
~~~

Khi đổi tên binary class thực sự và sửa bytecode/resource metadata tương ứng, parent-first có thể hoạt động mà không gặp xung đột tên class cũ. Nhưng việc relocation cần kiểm tra:

- Reflection bằng tên class dạng String.
- `META-INF/services` descriptors và provider names.
- Resources tham chiếu bằng đường dẫn package.
- Serialization metadata hoặc hardcoded names.
- Native libraries, JNI, service registries hay config resource mà library phụ thuộc.
- License/packaging và việc tích hợp với framework sử dụng package names cụ thể.

**Relocation không chỉ là đổi tên file JAR.** Nếu library dùng reflection/service metadata nhiều, relocation có thể phát sinh lỗi khác. Hãy cân nhắc giữa đơn giản hóa runtime loader và chi phí build/compatibility khi thực sự cần multi-version.

## 8. ServiceLoader, SPI và TCCL ở plugin boundary

`ServiceLoader` tiêu thụ **service type chung** từ parent và provider ở plugin loader. Với classpath SPI, plugin cần `META-INF/services/api.PluginService` chứa đúng binary provider name; host nên dùng overload tường minh `ServiceLoader.load(api.PluginService.class, pluginLoader)` khi đã biết plugin owner. Overload một tham số sử dụng TCCL của thread, vì vậy framework chạy trên worker khác có thể không tìm provider của plugin. Nếu phải đổi TCCL, lưu context của chính worker và restore trong `finally`. JPMS named modules dùng `uses`/`provides` và có thể dùng `ServiceLoader.load(layer, Service.class)`; đừng gộp cơ chế đó với loader URL classpath.

## 9. Chính sách resource không tự theo chính sách class

Resource lookup và class lookup là hai đường khác nhau:

| API | Cách tìm thường gặp |
|---|---|
| `loader.loadClass("deps.format.Formatter")` | Theo policy override của loader; có thể child-first |
| `loader.getResource("plugin/config.txt")` | Mặc định parent-first |
| `loader.getResources("plugin/config.txt")` | Có thể nhận nhiều URLs từ parent và child |
| `URLClassLoader.findResource("plugin/config.txt")` | Chỉ tìm nguồn URL riêng của loader |
| `SomeClass.class.getResource("config.txt")` | Tên tương đối với package của class |
| `Class.getResource("/plugin/config.txt")` | Tên tuyệt đối từ gốc, nhưng vẫn theo quy tắc module/loader liên quan |

Nếu parent và child đều chứa `plugin/config.txt`, resource từ parent có thể được chọn dù class logic đang dùng dependency từ child. Vì vậy:

- Đặt config private dưới namespace riêng, tránh path collisions.
- Truyền resource URL/stream tường minh nếu cần đúng nguồn.
- Với URLClassLoader, có thể dùng `findResource` khi thật sự muốn tìm trong child URLs và loader chưa bị đóng.
- Khi override resource lookup, cần cân nhắc đồng bộ `getResource` **và `getResources`**, không tạo hai hành vi mâu thuẫn.
- Với named modules JPMS, resource trong package của named module còn chịu quy tắc `opens`; API `Class`/`Module`/`ClassLoader` có điều kiện truy cập khác nhau.

**Không dùng** việc thử `getResource` thành công để kết luận class cùng tên cũng được cùng loader định nghĩa.

## 10. Binary compatibility và lỗi version thực tế

Có những tình huống quan trọng:

### 10.1. Parent-first chọn một version cũ

Plugin biên dịch dựa vào:

~~~java
Formatter.formatAdvanced(value);
~~~

nhưng parent chỉ có Formatter bản cũ không chứa method với descriptor phù hợp. Class loading có thể thành công, nhưng khi JVM resolve method lúc thực thi, `NoSuchMethodError` có thể xuất hiện.

**Cách điều tra:** kiểm tra `Formatter.class.getClassLoader()` của class thực tế, `CodeSource` nếu có, tên JAR/path, và method signatures của version dùng khi compile.

### 10.2. Child-first tải cả shared API

Plugin object implement interface có **cùng tên** với host nhưng defining loader khác. `ClassCastException` hoặc `ServiceConfigurationError` có thể xảy ra. Không sửa bằng một cast “mạnh hơn”; cần sửa **loader ownership**.

### 10.3. Package-private xuyên loader

Hai class cùng source package nhưng defining loaders khác nhau thuộc runtime packages khác. JVM có thể từ chối truy cập package-private bằng `IllegalAccessError`. Không giải quyết bằng `--add-opens` một cách mù quáng: module openness và runtime package identity là hai vấn đề khác nhau.

### 10.4. Host/plugin có hai phiên bản cùng một native library

Một số native libraries có hạn chế riêng về việc nạp native code từ nhiều class loaders trong cùng JVM. Classloader separation không tự tạo **hai native linker/process namespaces độc lập**. Nếu plugin dependency phụ thuộc JNI hoặc global native state, xem kỹ lifecycle và hỗ trợ của thư viện; có thể cần cách ly bằng process.

### 10.5. Duplicate classes trong cùng một plugin JAR

Nếu một plugin JAR đã gộp/shade sai và chứa nhiều bản cùng binary name, thứ tự entry/search có thể làm class được chọn không như dự định. Trước khi thay policy, kiểm tra artifact bằng `jar --list --file ...` và dependency tree/build pipeline.

## 11. Phân biệt “private” về version với “private” về bảo mật

Trong bài này, `private` chỉ có nghĩa **dependency không được chia sẻ phiên bản/namespace với host**. ClassLoader không tạo security sandbox: plugin cùng process vẫn có thể gọi các JDK API và tác động tới file, mạng, bộ nhớ trong quyền của process. Plugin không tin cậy cần OS/process/container isolation và boundary IPC phù hợp.

## 12. Vòng đời: có thể unload plugin đến đâu?

Mỗi plugin generation phải giữ loader mở khi còn cần lazy-load class/resource. Khi dừng, host chặn công việc mới, drain tasks, unregister callbacks, đóng resource, restore TCCL và cuối cùng close `URLClassLoader`. Class unloading phụ thuộc GC/reachability; `close()` không buộc dỡ class ngay. Thử riêng parent/shared libraries có static caches có thể giữ plugin objects sống.

## 13. Chẩn đoán: class nào do loader nào định nghĩa?

### Dùng `Class.getClassLoader()`

~~~java
Class<?> type = object.getClass(); // object khác null
ClassLoader defining = type.getClassLoader();

System.out.println("type=" + type.getName());
System.out.println("loader=" + defining);
System.out.println("module=" + type.getModule());
~~~

Đây là mảnh minh họa, không phải chương trình đầy đủ. Với core Java classes, `getClassLoader()` có thể trả `null` để biểu diễn bootstrap.

### Dùng CodeSource nếu khả dụng

~~~java
Class<?> type = object.getClass();
var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();

System.out.println(source == null
        ? "CodeSource unavailable"
        : source.getLocation());
~~~

Không phải mọi runtime class đều có CodeSource hữu ích; nó có thể `null`. Không dựa vào string representation của loader hoặc `identityHashCode` làm ID tuyệt đối; chúng không thay thế so object identity `==`.

### Những thông tin nên log

| Thông tin | Vì sao |
|---|---|
| Binary name | Tìm đúng class gây lỗi |
| Defining loader object/type | Phân biệt API parent, dependency child |
| Loader logical name/generation | Liên hệ plugin đang hoạt động |
| Parent chain | Hiểu delegation |
| CodeSource URL/JAR hash | Xác định bytecode thật |
| Policy branch theo package | Biết parent-first hay child-first đã áp dụng |
| Thread context loader | Điều tra ServiceLoader và frameworks |
| Resource URL | Điều tra file config bị parent che |
| Java module/layer | Điều tra JPMS readability/exports/opens |
| Full exception chain | Phân biệt load/link/initialize/cast/runtime |

Không log credentials hoặc toàn bộ content tài nguyên nhạy cảm chỉ để quan sát.

### Lệnh theo dõi JVM

Trên HotSpot/JDK 17+:

~~~bash
java -Xlog:class+load=info \
    -cp "out/api:out/host:out/lib-v1" \
    LoaderBoundaryDemo dist/private-plugin.jar
~~~

Đây là lệnh chẩn đoán, output phụ thuộc JDK và nhiều hơn stdout chuẩn của demo. Không lấy class-loading log làm thứ tự class loading chính thức cho mọi JVM implementation.

## 14. Thiết kế plugin theo nhu cầu: ba phương án

| Phương án | Khi phù hợp | Đánh đổi |
|---|---|---|
| **Một loader chung, parent-first** | Tất cả plugin dùng dependency compatible, ít nhu cầu version song song | Đơn giản nhưng version conflict giữa plugins |
| **Một loader cho mỗi plugin, selective child-first** | Mỗi plugin cần dependency riêng, API chung ổn định | Tăng số loaders/metaspace, cần policy/resource/lifecycle |
| **Tách process** | Plugin không tin cậy hoặc có native/global state xung đột | Cách ly mạnh hơn, nhưng cần IPC/serialization/operational tooling |

Có thêm lựa chọn **shading/relocation** nếu runtime child-first gây quá nhiều phức tạp; việc chọn phương án phải dựa trên dependency graph thật, method signatures và mô hình deployment.

**Không nhất thiết mỗi plugin phải có loader riêng.** Nếu plugins đáng tin, dùng chung API và dependencies tương thích, parent-first đơn giản có thể là lựa chọn tốt hơn. Ngược lại, “mỗi plugin một loader” chỉ đáng giá khi lợi ích version isolation và lifecycle lớn hơn overhead.

## 15. Checklist thiết kế trước khi phát hành

- [ ] Xác định tập shared API interfaces/DTOs/exceptions/callbacks.
- [ ] Các shared types được định nghĩa bởi **một parent loader** mà host và plugin dùng chung.
- [ ] Plugin JAR không vô tình gói bản sao API chung, hoặc tối thiểu policy chắc chắn không định nghĩa lại API ấy.
- [ ] Implementation plugin do child plugin loader định nghĩa.
- [ ] Private dependency chỉ được child-first ở namespace có chủ đích.
- [ ] Tất cả class trong cùng package dùng package-private đã được giữ đúng defining loader.
- [ ] Các method signatures qua boundary không rò rỉ private dependency types.
- [ ] Parent và plugin version được kiểm tra binary compatibility.
- [ ] Resource lookup được kiểm tra riêng với class lookup.
- [ ] SPI/ServiceLoader, TCCL và provider descriptors được cấu hình đúng.
- [ ] Có policy fail-fast nếu thiếu dependency hoặc bản thư viện không tương thích.
- [ ] Có kế hoạch stop/drain/close/unload cho mỗi plugin generation.
- [ ] Có log defining loader, CodeSource, resource URL và lỗi gốc.
- [ ] Có test ít nhất hai plugin có cùng binary implementation name nhưng khác defining loader.
- [ ] Có test duplicate resource name và parent-first/child-first lựa chọn đúng dữ liệu.
- [ ] Có test missing methods, class not found, duplicate shared API, class cast, hot reload.
- [ ] Nếu dùng JPMS, module layer/readability/exports/opens được đánh giá độc lập.

## 16. Các sai lầm thường gặp

**“Cứ đưa mọi thư viện vào parent để chia sẻ.”** Không đúng nếu các plugin cần nhiều phiên bản không tương thích cùng binary name.

**“Cứ child-first mọi thứ để cô lập.”** Không đúng nếu làm đôi shared API và khiến host không cast được implementation.

**“Cùng file `api/Greeting.class` là cùng interface.”** Không: JVM xét **defining loader**, không chỉ nội dung bytecode.

**“Loader được gọi `loadClass` chắc chắn là loader định nghĩa class.”** Không: parent delegation có thể trả parent type.

**“Chỉ cần plugin interface nằm ở parent, mọi thư viện implementation đều cô lập.”** Không: phải xét class loading policy thực tế và các dependency transitive.

**“Child-first cho class đồng nghĩa child-first cho resource.”** Không: resource delegation là đường riêng.

**“Dùng `Thread.currentThread().setContextClassLoader` một lần là xong.”** Không: phải restore khi request kết thúc, nhất là thread pools.

**“`URLClassLoader.close()` thay bytecode cũ thành mới.”** Không: class definitions đã có không bị thay bởi close; muốn thế hệ mới thường cần loader mới.

**“`--add-opens` tự giải quyết mọi ClassCastException.”** Không: module openness không làm hai runtime types khác loader trở thành một type.

**“Để framework vào plugin jar là framework sẽ dùng luôn provider/plugin class.”** Không: framework có thể dùng TCCL, ServiceLoader, system loader hoặc cache riêng.

**“Shading là đổi tên JAR.”** Không: phải thực hiện relocation class/resource names có hệ thống.

**“ClassLoader riêng là sandbox.”** Không: cần security boundary độc lập nếu không tin cậy plugin code.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Host và plugin trao đổi `api.Greeting`. Ai nên định nghĩa interface này?

**Đáp án:** Một loader cha chung mà host và plugin delegate tới, để cả hai dùng **cùng runtime interface**.

**Câu 2.** Host có `deps.format.Formatter` v1, plugin muốn v2. Parent-first sẽ trả bản nào nếu parent nhìn thấy v1?

**Đáp án:** v1. Muốn v2 riêng, cần child-first chọn lọc cho namespace phù hợp hoặc phương án như shading/relocation.

**Câu 3.** Plugin loader child-first tự định nghĩa `api.Greeting` giống bytecode của host. Host có cast được provider sang `api.Greeting` của host không?

**Đáp án:** Không được bảo đảm; đó là hai runtime interfaces khác nhau và cast có thể thất bại. Phải dùng shared API thật sự.

**Câu 4.** Cả host lẫn plugin có `plugin/config.txt`. Tại sao loader child-first cho `deps.format.*` vẫn có thể trả config host?

**Đáp án:** Vì `getResource` mặc định delegate parent trước; class loading policy override không thay resource lookup.

**Câu 5.** Vì sao không nên expose `deps.format.Document` private qua public method của SPI?

**Đáp án:** Vì host/plugin cần cùng runtime type cho signature ấy. Nếu mỗi plugin định nghĩa version riêng, boundary có thể không tương thích. Dùng DTO/API chung hoặc chuyển dữ liệu sang định dạng trung lập.

**Câu 6.** Hai plugin loaders cùng tự định nghĩa `plugin.impl.PluginGreeting` từ một JAR có tạo ra cùng runtime `Class<?>` không?

**Đáp án:** Không. Tên/bytecode giống nhau nhưng defining loaders khác nhau nên class identity khác.

**Câu 7.** `URLClassLoader.close()` có lập tức unload class của plugin không?

**Đáp án:** Không. Phải giải phóng references/lifecycle; JVM/GC quyết định class unloading.

**Câu 8.** Khi `ServiceLoader.load(SPI.class)` không tìm provider, cần kiểm tra gì?

**Đáp án:** TCCL của thread, `META-INF/services` hoặc `uses`/`provides`, visibility của loader, và việc provider implement **đúng runtime SPI type**.

## 18. Sơ đồ quyết định cuối cùng

~~~text
             Xây kiến trúc class loader cho plugin
                             |
                   Có API qua boundary?
                     /            \
                   Có              Không
                    |                 |
          đặt API tại parent    Cân nhắc đơn giản:
                    |            parent-first nếu đủ
         plugin private version riêng?
                     /          \
                   Không         Có
                     |            |
              parent-first    selective child-first
                     |        CHỈ private namespaces
                     |            |
                     +------+-----+
                            |
                 Kiểm tra type identity
                 + public method signatures
                            |
                 Kiểm tra resources/SPI/TCCL
                            |
                 Kiểm tra lifecycle/generation
                            |
                 Log defining loader/CodeSource
                            |
                   Integration + redeploy tests
~~~

**Kết luận:** Khi lựa chọn loader, hãy **đặt shared API ở nơi tất cả participants nhìn thấy đúng cùng runtime Class**, còn **private implementation/dependencies ở loader riêng nếu thật sự cần cô lập version**. Parent-first cung cấp mặc định ổn định cho contract; child-first có chọn lọc giải quyết xung đột triển khai; quan sát defining loader và source thực tế giúp chứng minh chính sách đã hoạt động đúng.

### Tài liệu chuẩn

- [Java SE 17 — ClassLoader: loadClass, getClassLoader và delegation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader: findClass, getResource, findResource, close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [JVMS 17 5.3 — Class/interface identity, defining and initiating loaders](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
- [Java SE 17 — ServiceLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java Language Specification 13 — Binary compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html)
