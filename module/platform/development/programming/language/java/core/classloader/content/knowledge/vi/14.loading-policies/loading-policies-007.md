# Rủi ro nạp trùng API, annotation hoặc kiểu exception trong ClassLoader Java

## 1. Khái niệm cốt lõi: tên giống nhau chưa đủ để thành cùng kiểu

Trong JVM, danh tính runtime của một class/interface thông thường dựa trên **cặp (binary name, defining class loader)**. Vì vậy nếu hai loader thực sự tự định nghĩa lớp cùng tên `shared.Api` từ cùng bytecode, JVM vẫn có thể coi chúng là **hai kiểu khác nhau**.

~~~text
HostLoader    defines shared.Api -> Class A
PluginLoader  defines shared.Api -> Class B

A.getName().equals(B.getName()) = true
A == B                          = false
~~~

Rủi ro này xuất hiện khi host và plugin đóng gói bản sao của cùng API JAR, hoặc container sử dụng class loader cô lập với chính sách child-first quá rộng. Ba nhóm dễ bị ảnh hưởng nhất:

- **Interface/API:** Plugin tuy khai báo `implements shared.Api` nhưng thực hiện với bản API của loader plugin, không phải bản host dùng. Cast hoặc `isAssignableFrom` có thể thất bại.
- **Annotation:** Class được gắn annotation `shared.Marker` của plugin nhưng host kiểm tra bằng `Marker.class` của host. Phép `isAnnotationPresent` có thể trả false dù tên annotation giống nhau.
- **Exception:** Plugin ném `shared.Problem` thuộc namespace của plugin; `catch (shared.Problem e)` của host dùng một runtime Class khác nên không bắt trúng kiểu ấy.

Các hệ quả khác bao gồm `ClassCastException`, `ServiceConfigurationError` (provider không phải subtype), `LinkageError` vì loading constraints, static state bị nhân đôi, lỗi callback/DTO, và metadata framework không được nhận dạng.

**Không kết luận hai kiểu khác nhau chỉ vì có hai đối tượng ClassLoader.** Nếu cả hai loader ủy quyền tìm `shared.Api` cho cùng parent và parent định nghĩa nó, chúng có thể nhận về **chính cùng một Class runtime**. Điều cần xem là **defining loader** của Class kết quả.

## 2. API/interface bị nhân đôi gây lỗi như thế nào?

Host có một interface:

~~~java
package shared;

public interface Api {
    String message();
}
~~~

Plugin:

~~~java
package plugin;

import shared.Api;

public final class PluginImpl implements Api {
    @Override
    public String message() {
        return "hello";
    }
}
~~~

Đây là hai đoạn minh họa; bài thực hành ở phần sau cung cấp toàn bộ file Java.

Hai mô hình:

~~~text
ĐÚNG: chia sẻ API
HostLoader -- defines shared.Api
      ^
      | delegation shared.*
PluginLoader -- defines plugin.PluginImpl
      implements shared.Api (của parent)

SAI: nạp trùng API
HostLoader -- defines shared.Api [H]
PluginLoader -- defines shared.Api [P]
PluginLoader -- defines plugin.PluginImpl
      implements shared.Api [P] != [H]
~~~

Trong mô hình sai, một object được tạo từ `plugin.PluginImpl` không nhất thiết cast được sang `shared.Api` mà host đã resolve. `Api.class.getName().equals(pluginApi.getName())` vẫn true, nhưng `Api.class == pluginApi` false.

Một thông báo dạng “`shared.Api cannot be cast to shared.Api`” không phải mâu thuẫn; nó đang nói tới hai kiểu cùng binary name do hai defining loader khác nhau định nghĩa.

## 3. Annotation bị nhân đôi khiến reflection hoặc framework bỏ sót

Annotation cũng là một kiểu Java runtime. Ví dụ:

~~~java
package shared;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface Marker {}
~~~

Nếu plugin gắn `@Marker` nhưng chính annotation Class ấy do plugin loader định nghĩa, host gọi:

~~~java
boolean found = pluginType.isAnnotationPresent(Marker.class);
~~~

với `Marker.class` từ host sẽ không tự động match bản Marker của plugin. `found` có thể là false ngay cả khi `pluginType.getDeclaredAnnotations()` cho thấy annotation có tên `shared.Marker`.

Cần phân biệt **ba lỗi khác nhau**:

1. Không khai báo `RetentionPolicy.RUNTIME`: annotation có thể không hiện trong Java runtime reflection.
2. Annotation runtime có tồn tại, nhưng **Class identity không trùng**: host dùng Class của loader khác.
3. Framework scan nhầm scope, module package chưa `opens` khi cần deep reflection, hoặc đang scan proxy khác class thực tế.

Lỗi annotation có thể làm host bỏ qua controller/route, validator, transaction marker, dependency injection component hoặc authorization metadata. Với annotation mang ý nghĩa chính sách, hậu quả không chỉ là một phép kiểm tra trả false.

**Chính sách đúng:** những annotation mà host/framework cần đọc từ plugin phải được định nghĩa trong **shared contract loader**. Đừng chữa lỗi bằng cách so chuỗi tên annotation rồi chấp nhận mọi type cùng tên.

## 4. Exception bị nhân đôi khiến catch không trúng

Nếu host và plugin đều định nghĩa `shared.Problem extends Exception` dưới hai loader khác nhau, chúng vẫn là hai exception types độc lập. Một typed handler như:

~~~java
try {
    pluginCall();
} catch (Problem e) {
    handle(e);
}
~~~

là **đoạn minh họa** có biến, phương thức và kiểu `Problem` được khai báo thích hợp. Nó dựa trên type compatibility runtime, không dựa vào `getClass().getName()`. Object do `PluginProblem` tạo có thể thoát khỏi `catch (HostProblem)` dù tên nhị phân giống nhau.

Khi host gọi plugin qua reflection, cần nhớ Java reflection **bọc exception do method ném**:

~~~java
try {
    method.invoke(null);
} catch (java.lang.reflect.InvocationTargetException wrapper) {
    Throwable cause = wrapper.getCause();
    // Xem defining loader và Class của cause thay vì wrapper.
}
~~~

Đây là **mã minh họa**, không phải chương trình có main. `wrapper` là `InvocationTargetException`, còn `cause` có thể là bản `shared.Problem` do plugin loader định nghĩa.

Giải pháp: cho exception types trong hợp đồng host-plugin nằm ở shared parent loader; hoặc dùng adapter để chuyển exception riêng của plugin thành **shared exception type** hay error DTO trước khi trả qua boundary. Không bắt mọi `Throwable` rồi xóa toàn bộ root cause.

## 5. Quy tắc định danh kiểu và những API kiểm tra hữu ích

| Kiểm tra | Trả lời câu hỏi |
| --- | --- |
| `a.getName().equals(b.getName())` | Binary names giống nhau không? |
| `a == b` với `Class<?>` | Có là cùng runtime Class không? |
| `a.getClassLoader()` | Defining loader của a là ai? |
| `a.isAssignableFrom(b)` | Đối tượng kiểu b có thể gán cho a theo quy tắc kiểu không? |
| `a.isInstance(object)` | Object có tương thích với a không? |
| `annotation.annotationType()` | Annotation instance thuộc đúng runtime annotation Class nào? |
| `cause instanceof HostProblem` | Exception thực sự tương thích với kiểu host không? |
| `clazz.getModule()` | Runtime module của class (Java 9+) là gì? |

Đừng chỉ so `toString()` của Class hoặc loader, vì các chuỗi mô tả không phải cơ chế kiểm tra type identity chuẩn. Khi in loader của class lõi như `java.lang.String`, `getClassLoader()` có thể là `null`, đại diện bootstrap loader.

## 6. Vì sao duplicate contract lọt qua loader policy?
Với `shared.Api`, `shared.Marker` và `shared.Problem`, cùng một lỗi thiết kế là để child định nghĩa lại **contract của host**. Parent-first chỉ giúp khi parent thực sự có các class ấy; child-first có chọn lọc phải loại trừ contract package.

| Nhóm | Kiểm tra bắt buộc |
| --- | --- |
| Service/API | `HostApi.class.isAssignableFrom(pluginImpl)` |
| Annotation host đọc | `impl.isAnnotationPresent(HostMarker.class)` và retention `RUNTIME` |
| Exception host bắt | Class của nguyên nhân gốc có assignable vào `HostProblem.class` |
| Implementation/private dependency | Nguồn class và defining loader đúng plugin mong đợi |

Các phép kiểm tra trên trả lời **những câu hỏi khác nhau**; không thể chỉ kiểm tra `getName()` một lần rồi coi toàn bộ contract đã đúng. Bài thực hành tiếp theo cố ý nạp trùng cả ba loại để quan sát từng lỗi.

## 7. Thí nghiệm Java 17+: nạp trùng rồi sửa cùng một plugin

Ví dụ sau cố tình compile `shared.*` vào **cả host-classes và plugin-classes**. Host sẽ chạy hai cấu hình:

- `isolated`: child-first cho `plugin.*` và `shared.*`, làm trùng interface, annotation, exception.
- `shared`: child-first chỉ cho `plugin.*`; còn `shared.*` ủy quyền parent, làm contract thống nhất.

### 7.1. Cấu trúc file

~~~text
duplicate-types-demo/
├── src-shared/
│   └── shared/
│       ├── Api.java
│       ├── Marker.java
│       └── Problem.java
├── src-plugin/
│   └── plugin/
│       └── PluginImpl.java
└── src-host/
    └── HostMain.java
~~~

### 7.2. src-shared/shared/Api.java

~~~java
package shared;

public interface Api {
    String message();
}
~~~

### 7.3. src-shared/shared/Marker.java

~~~java
package shared;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Marker {
}
~~~

`@Retention(RUNTIME)` đảm bảo annotation có thể được reflection quan sát. `@Target(TYPE)` ghi rõ nó được dùng cho class/interface declarations.

### 7.4. src-shared/shared/Problem.java

~~~java
package shared;

public class Problem extends Exception {
    public Problem(String message) {
        super(message);
    }
}
~~~

### 7.5. src-plugin/plugin/PluginImpl.java

~~~java
package plugin;

import shared.Api;
import shared.Marker;
import shared.Problem;

@Marker
public final class PluginImpl implements Api {
    @Override
    public String message() {
        return "hello";
    }

    public static void fail() throws Problem {
        throw new Problem("plugin problem");
    }
}
~~~

Plugin implementation implement API, có annotation runtime và method ném checked exception.

### 7.6. src-host/HostMain.java

~~~java
import java.io.IOException;
import java.lang.annotation.Annotation;
import java.lang.reflect.InvocationTargetException;
import java.nio.file.Files;
import java.nio.file.Path;

import shared.Api;
import shared.Marker;
import shared.Problem;

public class HostMain {
    static final class PluginLoader extends ClassLoader {
        private final Path root;
        private final boolean duplicateShared;

        PluginLoader(Path root, boolean duplicateShared) {
            super(HostMain.class.getClassLoader());
            this.root = root;
            this.duplicateShared = duplicateShared;
        }

        private boolean local(String name) {
            return name.startsWith("plugin.")
                    || (duplicateShared && name.startsWith("shared."));
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!local(name)) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    result = findClass(name);
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = root.resolve(
                    name.replace('.', '/') + ".class");
            try {
                byte[] bytes = Files.readAllBytes(file);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    static void demonstrate(String label, Path root,
                            boolean duplicateShared) throws Exception {
        PluginLoader loader = new PluginLoader(root, duplicateShared);
        Class<?> impl = loader.loadClass("plugin.PluginImpl");
        Object object = impl.getConstructor().newInstance();

        Class<?> pluginApi = loader.loadClass("shared.Api");
        Class<?> pluginMarkerType = loader.loadClass("shared.Marker");
        Class<?> pluginProblem = loader.loadClass("shared.Problem");
        Class<? extends Annotation> pluginMarker =
                pluginMarkerType.asSubclass(Annotation.class);

        System.out.println(label + " API name equal: "
                + Api.class.getName().equals(pluginApi.getName()));
        System.out.println(label + " API same Class: "
                + (Api.class == pluginApi));
        System.out.println(label + " host Api instance: "
                + (object instanceof Api));
        System.out.println(label + " host Marker present: "
                + impl.isAnnotationPresent(Marker.class));
        System.out.println(label + " plugin Marker present: "
                + impl.isAnnotationPresent(pluginMarker));

        try {
            impl.getMethod("fail").invoke(null);
        } catch (InvocationTargetException wrapper) {
            Throwable cause = wrapper.getCause();
            System.out.println(label + " exception same name: "
                    + cause.getClass().getName()
                           .equals(Problem.class.getName()));
            System.out.println(label + " exception same Class: "
                    + (cause.getClass() == Problem.class));
            System.out.println(label + " exception is host Problem: "
                    + (cause instanceof Problem));
            System.out.println(label + " exception is plugin Problem: "
                    + pluginProblem.isInstance(cause));
        }

        try {
            Api api = (Api) object;
            System.out.println(label + " message: " + api.message());
        } catch (ClassCastException wrongApi) {
            System.out.println(label + " cast: ClassCastException");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: HostMain <plugin-classes-directory>");
        }
        Path root = Path.of(args[0]);
        demonstrate("isolated", root, true);
        demonstrate("shared", root, false);
    }
}
~~~

Vì `HostMain` không import hay tham chiếu trực tiếp `plugin.PluginImpl` khi compile, loader parent không tự được cung cấp plugin implementation nếu classpath chỉ chứa `host-classes`.

`PluginLoader` cho tên `plugin.*` đi local-first trong cả hai trường hợp; với `duplicateShared=true` mới cho `shared.*` đi local-first. Những tên khác (như `java.lang.String`) vẫn đi qua parent. Trong loader, `getClassLoadingLock` và `findLoadedClass` ngăn định nghĩa trùng tên khi có nhiều lời gọi.

**Giới hạn của demo:** `findClass` đọc classfile từ thư mục đã chuẩn bị sẵn mà không kiểm tra symlink, file size, allowlist hay thư mục tin cậy. Chỉ dùng nó để quan sát type identity trong môi trường học tập, **không dùng nguyên trạng làm plugin loader cho code không tin cậy**.

### 7.7. Biên dịch và chạy

Tại thư mục `duplicate-types-demo`, dùng JDK 17+:

~~~bash
javac --release 17 -d host-classes src-shared/shared/Api.java src-shared/shared/Marker.java src-shared/shared/Problem.java src-host/HostMain.java
javac --release 17 -d plugin-classes src-shared/shared/Api.java src-shared/shared/Marker.java src-shared/shared/Problem.java src-plugin/plugin/PluginImpl.java
java -cp host-classes HostMain plugin-classes
~~~

**Stdout dự kiến** khi chạy đúng file và lệnh:

~~~text
isolated API name equal: true
isolated API same Class: false
isolated host Api instance: false
isolated host Marker present: false
isolated plugin Marker present: true
isolated exception same name: true
isolated exception same Class: false
isolated exception is host Problem: false
isolated exception is plugin Problem: true
isolated cast: ClassCastException
shared API name equal: true
shared API same Class: true
shared host Api instance: true
shared host Marker present: true
shared plugin Marker present: true
shared exception same name: true
shared exception same Class: true
shared exception is host Problem: true
shared exception is plugin Problem: true
shared message: hello
~~~

### 7.8. Vì sao chỉ đổi policy đã sửa được?

Trong cấu hình `isolated`, loader plugin tự define `Api`, `Marker` và `Problem`. Tên và bytes có thể giống host nhưng Class runtime khác. Plugin thực thi theo các phiên bản của nó; host cast và annotation lookup dùng phiên bản host, nên thất bại.

Trong cấu hình `shared`, package `shared.*` được ủy quyền cho loader host. Plugin implementation được định nghĩa riêng, nhưng các shared contract types trong bytecode được resolve tới Class của parent. Do đó cast sang host `Api` được; host đọc annotation `Marker` được; và exception `Problem` là đúng runtime type host chờ đợi.

Reflection ở ví dụ này không bỏ qua type identity. Nó chỉ cho phép host quan sát Class/annotation/exception của plugin khi chưa thể cast object sang interface host.

## 8. Exception matching và reflection wrappers

Một điều dễ bị che khuất: method plugin ném `Problem`, nhưng `Method.invoke` ném ra `InvocationTargetException` cho caller. Vì vậy muốn biết **kiểu exception thật** cần lấy `getCause()`.

Nếu host code trong đường gọi trực tiếp có typed catch `catch (Problem e)`, JVM sẽ kiểm tra kiểu tương thích với **host Problem** đã liên kết. Một object của **plugin Problem** khác defining loader không tự trở thành host Problem chỉ vì có cùng tên.

Trong kiến trúc plugin, nên phân loại rõ:

- **Contract exception:** một phần API chung và được parent loader định nghĩa.
- **Plugin-private exception:** chỉ tồn tại trong plugin và nên được adapter chuyển sang contract exception hoặc error DTO.
- **Framework wrapper:** `InvocationTargetException`, `ExecutionException`, `CompletionException` v.v.; cần unwrap theo hợp đồng API tương ứng.
- **VM/linkage errors:** không tự động chuyển tất cả thành `ClassNotFoundException` hay domain error, vì làm mất root cause.

Trong log, in cả `exception.getClass()` và `exception.getClass().getClassLoader()` để phân biệt hai exception cùng tên.

## 9. Annotation scanning và ServiceLoader bị ảnh hưởng

Các framework (DI, web routing, ORM, validation, AOP, testing) có thể tìm annotation bằng `getAnnotation`, `getAnnotationsByType` hoặc `isAnnotationPresent`. Nếu annotation type nhân đôi, host scanner có thể không nhận dạng marker, dù plugin metadata có annotation cùng tên.

Đừng chẩn đoán nhầm thành “quên `@Retention(RUNTIME)`” mà không in `annotation.annotationType()` và defining loader.

`ServiceLoader` hoạt động trên **đúng service type Class**. Provider implement bản interface từ plugin loader có thể không là subtype của service interface host sử dụng, dẫn đến `ServiceConfigurationError`, ví dụ provider không phải subtype. Thay đổi Thread Context ClassLoader có thể ảnh hưởng nơi tìm provider, **không tự hợp nhất hai runtime types** đã được định nghĩa.

Cách sửa là để provider và consumer cùng tham chiếu một **shared service API Class**; khi dùng named modules, kiểm tra thêm `uses`, `provides...with` và khả năng đọc module.

## 10. Loading constraints và lỗi không chỉ xảy ra lúc cast

JVM áp đặt **loading constraints** nhằm đảm bảo những reference types được sử dụng qua method descriptors, inheritance và những điểm liên kết khác có ngữ nghĩa kiểu nhất quán.

Hai Class cùng tên do hai loader định nghĩa **có thể** cùng tồn tại độc lập. Nhưng nếu JVM cần cùng một kiểu `shared.Dto` trong một quan hệ override/interface hoặc descriptor giao tiếp mà hai loader lại resolve thành Class khác nhau, một **`LinkageError` vì loader constraint violation** có thể xuất hiện ở giai đoạn liên kết/resolve, trước khi ứng dụng tới phép cast.

Phân biệt:

| Lỗi | Dấu hiệu |
| --- | --- |
| `ClassCastException` | Object không tương thích với Class của phép cast |
| `LinkageError` / loading constraint | JVM không thể bảo đảm tính nhất quán kiểu khi liên kết những class liên quan |
| `ServiceConfigurationError` | Provider không tương thích hoặc cấu hình service sai |
| `InvocationTargetException` | Reflection wrapper của exception do method ném |
| `NoSuchMethodError` / `NoSuchFieldError` | Symbol/version mismatch, không nhất thiết chỉ do loader duplication |
| `ClassNotFoundException` | Loader không tìm thấy class theo tên trong phạm vi tìm kiếm |

Không nói “nhân đôi API thì luôn có LinkageError”, cũng không nói “mọi vấn đề chỉ là ClassCastException”: loại lỗi phụ thuộc cách những class được sử dụng.

## 11. Phân biệt API contract và dependency private

Tập **shared contract** thường gồm:

- Service interfaces, abstract base types và những superinterfaces chung.
- Parameter/return types xuất hiện ở method signatures, DTO/record/enum dùng xuyên ranh giới.
- Checked/unchecked exception types mà host xử lý theo Class.
- Annotation types mà host cần scan.
- Listener/callback types và service provider contracts.

Plugin có thể có private implementation classes và những thư viện phiên bản riêng **không lộ ra ở boundary**. Nếu một thư viện private xuất hiện trong public API, ranh giới không còn tách biệt sạch; cần xây adapter hoặc chuẩn hóa contract.

Ví dụ nếu plugin dùng phiên bản JSON library khác host, nên chuyển qua DTO chung hoặc chuỗi/byte với schema rõ, thay vì trả một object parser implementation từ plugin rồi cast sang implementation phiên bản host.

## 12. Đóng gói và build configuration

Nguyên nhân duplication thường nằm ở artifact hơn là chính Java source:

- Plugin fat JAR/uber JAR có bản copy `shared/Api.class` và child-first loader định nghĩa bản ấy.
- Container cung cấp API sẵn nhưng plugin vẫn đóng kèm bản API.
- Maven/Gradle dependency scopes khiến API được ship hai lần khi deployment.
- Shading/relocation thay package names của một dependency được host dự kiến chia sẻ.
- App server isolation, test class loader hoặc hot reload tạo loader mới với bản contract riêng.

Trong các hệ thống host cung cấp contract JAR ở runtime, plugin thường compile against API nhưng không tự đóng gói bản duplicate; Maven `provided` hoặc Gradle `compileOnly` **có thể** phù hợp tùy môi trường build/deploy. Phải kiểm tra artifact và class loader runtime thực tế.

Có thể kiểm tra entries:

~~~bash
jar --list --file plugin.jar
~~~

Khi `plugin.jar` tồn tại, tìm `shared/Api.class`, `shared/Marker.class`, `shared/Problem.class`. **Có file trùng chưa chứng minh Class bị define trùng**, vì parent-first có thể vẫn dùng bản của parent. Muốn kết luận, so `Class<?>` và defining loader runtime.

## 13. Debug có hệ thống

Một helper đơn giản:

~~~java
static void describe(Class<?> type) {
    System.out.println(type.getName());
    System.out.println(type.getClassLoader());
    System.out.println(type.getModule());
}
~~~

Đây là mã minh họa đặt trong class bất kỳ, không phải file chạy độc lập.

Quy trình khi thấy “X cannot be cast to X”, annotation biến mất hoặc exception handler không chạy:

1. Lấy **hai Class cụ thể** đang đối chiếu, ví dụ `Api.class` của host và `pluginLoader.loadClass("shared.Api")`.
2. In tên, defining loader, module; so `Class<?>` bằng `==`.
3. Kiểm tra parent chain và chính sách parent-first/child-first theo **từng package**.
4. Kiểm tra các artifact có bản sao `shared.*` và deployment runtime có đúng loại loader không.
5. Với annotation, xác nhận `RetentionPolicy.RUNTIME`, kiểm tra `annotation.annotationType()` và loader.
6. Với exception, unwrap wrapper, in `cause.getClass()` và loader, so `instanceof HostProblem`.
7. Với ServiceLoader, kiểm tra Class của service, Class provider và `isAssignableFrom`.
8. Với LinkageError, kiểm tra method descriptors, những kiểu chung trong signatures, versions và loader constraints.
9. Chuyển shared contract sang common parent, giữ plugin-private implementation ở child, rồi chạy lại test.
10. Test trong đúng môi trường container/plugin/module layer; IDE chạy thành công chưa chứng minh packaged artifact đã đúng.

Có thể bật class loading logs trong OpenJDK/HotSpot:

~~~bash
java -Xlog:class+load=info -cp host-classes HostMain plugin-classes
~~~

Log chi tiết thay đổi theo JDK và môi trường, vì vậy không có transcript cố định. Kết hợp log với `getClassLoader()`, không suy toàn bộ identity chỉ từ JAR path.

## 14. Những sai lầm cần tránh

| Sai lầm | Cách hiểu/sửa |
| --- | --- |
| “Cùng tên đầy đủ là cùng Class” | Runtime identity có defining loader |
| “Hai loader khác nhau chắc chắn nạp trùng” | Delegation có thể trả cùng Class parent |
| “Bytecode giống thì cast được” | Bytes giống không xóa namespace loader |
| “Annotation tên đúng thì reflection nhận được” | Phải cùng annotation Class, retention phù hợp |
| “catch cùng tên sẽ bắt mọi exception cùng tên” | Typed catch so tương thích runtime Class |
| “Bật child-first cho mọi package để isolate” | Chỉ cô lập plugin implementation/private dependencies |
| “TCCL mới sửa mọi duplication” | TCCL thay lookup context, không hợp nhất Class |
| “ServiceLoader không phải subtype chỉ do provider sai” | Có thể do service interface copy ở child |
| “LinkageError xuất hiện ở mọi duplicate” | Chỉ xuất hiện khi constraints/linkage cụ thể bị vi phạm |
| “Reflection bỏ qua type safety” | Reflection vẫn có kiểm tra receiver/argument/type; exception được bọc |
| “Chuyển JAR sang module path là tự sửa” | JPMS có quy tắc riêng, class identity vẫn quan trọng |
| “Cứ gộp mọi dependency vào parent” | Chỉ contract cần shared; private libs cần chính sách rõ |

## 15. Bộ test khuyến nghị cho plugin boundary

1. `hostApiClass.isAssignableFrom(pluginImplClass)` đúng khi plugin khai báo implement API chung.
2. Annotation `shared.Marker` có thể được host tìm bằng `isAnnotationPresent`.
3. Plugin ném shared exception thì handler/type check của host nhận đúng Class.
4. ServiceLoader provider là subtype của service interface host cung cấp.
5. Method parameters/return DTO classes ở boundary do common loader định nghĩa.
6. Plugin A và Plugin B có thể giữ dependency private khác versions mà không làm trùng API.
7. API/annotation/exception classes không bị copy định nghĩa qua child-first.
8. Hot reload tạo implementation Class mới nhưng shared API Class vẫn ổn định.
9. Test các trường hợp thiếu dependency và loader constraints, không chỉ tìm được class.
10. Kiểm tra JAR/WAR đóng gói thật và loader policy của application server.
11. Khi dùng annotations với named modules, kiểm tra exports/opens theo API scanner.
12. Đảm bảo logs khi lỗi có binary name **và** defining loader, tránh chẩn đoán sai.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Hai interface cùng `getName()` nhưng khác defining loader có tương đương không?  
Không. JVM có thể coi đó là hai runtime types độc lập.

**Câu 2.** Hai plugin loader cùng delegate `shared.Api` về parent thì sao?  
Chúng có thể dùng cùng `Class<?>` do parent định nghĩa, không nhân đôi API.

**Câu 3.** Vì sao host `(Api) plugin` lỗi dù plugin code có `implements Api`?  
Vì `Api` trong plugin có thể là bản do loader khác define.

**Câu 4.** Annotation host không thấy có thể do những nguyên nhân nào?  
Retention không phải RUNTIME, annotation Class từ loader khác, sai class được scan hoặc module access.

**Câu 5.** Object `Problem` của plugin cùng tên có tự bị `catch(Problem)` của host bắt không?  
Không nếu hai Class runtime khác và không có quan hệ gán tương thích phù hợp.

**Câu 6.** Khi Method.invoke ném exception của plugin, tìm exception gốc ở đâu?  
Trong `InvocationTargetException.getCause()`.

**Câu 7.** ServiceLoader báo provider not a subtype thường nên kiểm tra gì trước?  
Provider có implement đúng service `Class<S>` của host không, cùng defining loader hay không.

**Câu 8.** Có nên để shared annotations và exceptions local-first với plugin implementation không?  
Không nếu host cần nhận diện chúng bằng typed contract; delegate các types này về shared parent.

**Câu 9.** Lỗi loader constraint violation có luôn xuất hiện ngay khi loader định nghĩa hai class cùng tên không?  
Không; phụ thuộc quan hệ liên kết cụ thể giữa những classes liên quan.

**Câu 10.** Module path có làm hai Class từ hai defining loader khác nhau thành một kiểu không?  
Không. Module configuration không xóa class identity.

## 17. Tài liệu tham chiếu

- JVM Specification Java 17 `5.3, runtime class identity và defining loader: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JVM Specification Java 17 `5.3.4, Loading Constraints: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4
- Java SE 17, ClassLoader API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17, Class API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17, Annotation API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html
- Java SE 17, ServiceLoader API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17, InvocationTargetException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html
- JLS Java 17 `12.2, Loading of Classes and Interfaces: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
