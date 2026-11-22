# ClassCastException do khác định danh loader

## 1. Vì sao một class dường như không cast được thành “chính nó”?

Khi ứng dụng Java có nhiều `ClassLoader`, đôi khi bạn gặp lỗi khó hiểu:

~~~text
java.lang.ClassCastException:
class plugin.Worker cannot be cast to class plugin.Worker
~~~

Trên JDK mới, thông điệp thường bổ sung tên **module và loader** ở mỗi phía; nội dung chính xác có thể khác giữa các môi trường nên không nên viết test dựa trên toàn bộ chuỗi exception.

Nguyên nhân: trong JVM, **tên class không phải toàn bộ danh tính của kiểu**. Với một class/interface thông thường, danh tính runtime là cặp:

~~~text
(binary name, defining class loader)
~~~

Ví dụ:

~~~text
("plugin.Worker", LoaderA) != ("plugin.Worker", LoaderB)
~~~

Ngay cả khi hai loader đọc **chính cùng một file `plugin/Worker.class` với bytecode giống nhau**, nếu cả hai thực sự định nghĩa class, JVM tạo **hai runtime class khác nhau**.

Hệ quả:

- `classA.getName().equals(classB.getName())` có thể trả `true`.
- `classA == classB` trả `false` nếu defining loaders khác nhau.
- `classA.isInstance(objectB)` trả `false` nếu objectB thuộc bản class khác không có quan hệ subtype được JVM công nhận.
- `classA.cast(objectB)` ném `ClassCastException`.
- Cùng một interface dùng trong source code cũng có thể bị **định nghĩa hai lần**, khiến implementation của plugin không thể cast sang interface ở host.

Đây là lỗi **runtime type identity**, không phải lỗi do viết sai tên package hay Java compiler không hiểu `import`.

## 2. Defining loader và initiating loader

Để debug chính xác, phải phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Binary name** | Tên nhị phân của class, ví dụ `plugin.Worker`. |
| **Defining class loader** | Loader thực sự định nghĩa class trong JVM; là thành phần của runtime identity. |
| **Initiating class loader** | Loader khởi đầu yêu cầu tải class; có thể delegate cho loader khác định nghĩa. |
| **Parent-first delegation** | Child thử hỏi parent trước, sau đó mới tìm trong nguồn riêng nếu parent không thấy. |
| **Class object** | Đối tượng `Class<?>` đại diện đúng một kiểu runtime cụ thể, không chỉ chuỗi tên. |

Ví dụ minh họa:

~~~java
Class<?> type = child.loadClass("api.Task");
ClassLoader definingLoader = type.getClassLoader();
~~~

Không được suy ra `definingLoader == child`. Với parent-first, nếu parent đã nạp `api.Task` thì `child.loadClass` trả lại **Class của parent**.

Do đó, chỉ có bản sao `api.Task.class` trong JAR plugin **chưa đủ kết luận bị xung đột**. Nếu child luôn ủy quyền parent cho interface và parent có class ấy, bản sao có thể không được sử dụng. Lỗi xuất hiện khi có **hai bản thực sự được định nghĩa bởi hai loader**.

### Hai class triển khai riêng và một API chung

~~~text
             Host / Application Loader
             ├── api.Task
             └── PluginManager
                       |
          +------------+------------+
          |                         |
       Loader A                  Loader B
       plugin.Worker             plugin.Worker
       implements api.Task       implements api.Task
       (Task từ parent)          (Task từ parent)
~~~

Hai `plugin.Worker` của A/B là hai kiểu khác nhau; nhưng **cả hai có thể được cast sang cùng interface `api.Task`** nếu dùng bản Task do parent định nghĩa. Đó là mô hình chuẩn của hệ thống plugin.

## 3. Hai tình huống ClassCastException khác nhau

### Tình huống A — cast giữa hai bản implementation trùng tên

~~~java
Class<?> fromA = loaderA.loadClass("plugin.Worker");
Class<?> fromB = loaderB.loadClass("plugin.Worker");
Object objectB = fromB.getDeclaredConstructor().newInstance();

System.out.println(fromA.getName().equals(fromB.getName())); // true
System.out.println(fromA == fromB);                          // false
System.out.println(fromA.isInstance(objectB));               // false
fromA.cast(objectB); // ClassCastException
~~~

Đây là đoạn minh họa trong context có hai loader thật sự định nghĩa riêng `plugin.Worker`, constructor truy cập được. Dùng đúng code đầy đủ ở phần 6 để tái hiện.

Ngay cả nếu plugin A và B được biên dịch từ source giống nhau, một instance Worker của B không tự trở thành instance Worker của A. Nếu host cần dùng cả hai, hãy thao tác qua **shared interface** chứ không ép từ concrete class của loader này sang concrete class của loader kia.

### Tình huống B — chính interface API cũng bị nhân đôi

~~~text
Host loader:
  api.Task            -- interface host mong đợi

Isolated plugin loader:
  api.Task            -- bản interface do plugin định nghĩa
  plugin.Worker       -- implements Task trong isolated loader
~~~

Cast kiểu:

~~~java
api.Task task = (api.Task) isolatedObject;
~~~

có thể ném `ClassCastException`, dù mã plugin có `implements api.Task`. Lý do: ký hiệu `api.Task` trong bytecode plugin được resolve thành **Task của isolated loader**, còn phép cast của host tham chiếu **Task của host loader**. Tên giống, interface runtime khác.

Đây là tình huống khó hơn vì đọc source/JAR sẽ thấy type name hoàn toàn hợp lý.

## 4. Duplicate JAR, delegation và chọn package policy

| Tình huống | Khả năng xảy ra |
| --- | --- |
| Plugin JAR có `api.Task.class`, child parent-first và parent có Task | Có thể vẫn dùng **Task của parent**; không nhất thiết lỗi cast. |
| Child-first với cả `api.*` | Child có thể define bản Task khác; nguy cơ ClassCastException. |
| Child có parent là platform/bootstrap, không thấy API host | Child tự define Task từ plugin archive; khác Task host. |
| Hai sibling loaders tự define `plugin.Worker` | Hai runtime types Worker khác nhau dù cùng bytes. |
| Host vô tình thêm plugin JAR vào application classpath | Parent có thể tải implementation sớm, đảo kết quả kỳ vọng về defining loader. |
| Plugin reload tạo loader v2 | Worker v1 và Worker v2 không cùng concrete type, kể cả binary name giống. |

Giải pháp cho SPI/API:

1. Đặt **interface/hợp đồng chung** (và các types đi qua public method signatures) trong classpath/module của host hoặc loader cha được chia sẻ.
2. Để child **parent-first với package của shared API**.
3. Chỉ dùng child-first có chọn lọc với package implementation hoặc dependency cần cách ly.
4. Không cast concrete class giữa các plugin versions/loaders.
5. Nếu cần giao tiếp giữa các lớp riêng, dùng API chung, adapter, DTO chung hoặc serialization có hợp đồng rõ ràng.

**Lưu ý:** `ClassLoader.getParent()` chỉ cho parent trực tiếp; thực tế custom loader có thể override lookup, nên không dựa vào cây loader đơn giản để đoán class identity. Hãy kiểm tra `clazz.getClassLoader()` và `clazz == otherClazz` ngay tại runtime.

## 5. Class.cast, instanceof và isAssignableFrom

Các phép này có mục tiêu liên quan nhưng khác hình thức:

| Phép kiểm tra | Dùng cho | Khi type identity không tương thích |
| --- | --- | --- |
| `TargetType.class.isInstance(object)` | Kiểm tra một object thuộc type/subtype cụ thể không | Trả `false` |
| `TargetType.class.cast(object)` | Cast động bằng đối tượng Class | Ném `ClassCastException` với non-null object không tương thích |
| `object instanceof TargetType` | Kiểm tra runtime type ở code Java | `false` |
| `TargetType.class.isAssignableFrom(otherClass)` | Kiểm tra class/interface khác có assignable tới type này không | `false` |
| `clazzA == clazzB` | Kiểm tra có đúng **cùng runtime Class object** không | `false` |
| `clazzA.getName().equals(clazzB.getName())` | So sánh chuỗi binary name | Có thể `true` dù cast thất bại |

Đừng dùng so tên class bằng chuỗi để thay thế cho `isAssignableFrom`. Với plugin API, câu hỏi thật là **implementation class có tương thích với interface Class của host không**, chứ không phải implementation và interface có tên giống nhau không.

Đối với `Class.cast(null)`, giống cast reference thông thường, `null` không gây ClassCastException; những ví dụ trong bài cố ý dùng instance thật để minh họa.

## 6. Chương trình Java 17+ độc lập: lỗi cast và shared API đúng cách

Chương trình gồm **ba file source**. Đặc biệt, ta sẽ compile `api.Task` vào **hai output folders khác nhau** để có khả năng tạo bản sao API khi loader cô lập đọc plugin root.

Cấu trúc:

~~~text
example/
├── src/
│   ├── api/Task.java
│   ├── plugin/Worker.java
│   └── host/IdentityDemo.java
└── out/
    ├── host/           (Task + IdentityDemo)
    └── plugin/         (Task + Worker)
~~~

**Chỉ `out/host` được đưa vào application classpath khi chạy.** `out/plugin` được truyền qua tham số, không đưa vào `-cp`.

### src/api/Task.java

~~~java
package api;

public interface Task {
    String run();
}
~~~

### src/plugin/Worker.java

~~~java
package plugin;

import api.Task;

public final class Worker implements Task {
    @Override
    public String run() {
        return "plugin-ok";
    }
}
~~~

### src/host/IdentityDemo.java

~~~java
import api.Task;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class IdentityDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("plugin class root");
        }

        URL root = Path.of(args[0]).toAbsolutePath()
                .normalize().toUri().toURL();
        ClassLoader host = IdentityDemo.class.getClassLoader();

        try (URLClassLoader a = new URLClassLoader(
                     new URL[]{root}, host);
             URLClassLoader b = new URLClassLoader(
                     new URL[]{root}, host);
             URLClassLoader isolated = new URLClassLoader(
                     new URL[]{root},
                     ClassLoader.getPlatformClassLoader())) {

            Class<?> classA = a.loadClass("plugin.Worker");
            Class<?> classB = b.loadClass("plugin.Worker");

            Object objectA =
                    classA.getDeclaredConstructor().newInstance();
            Object objectB =
                    classB.getDeclaredConstructor().newInstance();

            System.out.println("same binary name: "
                    + classA.getName().equals(classB.getName()));
            System.out.println("same runtime Class: "
                    + (classA == classB));
            System.out.println("defined by A/B: "
                    + (classA.getClassLoader() == a
                    && classB.getClassLoader() == b));
            System.out.println("A isInstance(B): "
                    + classA.isInstance(objectB));

            try {
                classA.cast(objectB);
                System.out.println("unexpected cast success");
            } catch (ClassCastException expected) {
                System.out.println(
                        "cross-loader cast: ClassCastException");
            }

            System.out.println("shared API A: "
                    + (a.loadClass("api.Task") == Task.class));
            System.out.println("shared API B: "
                    + (b.loadClass("api.Task") == Task.class));

            System.out.println("A via API: "
                    + ((Task) objectA).run());
            System.out.println("B via API: "
                    + ((Task) objectB).run());

            Class<?> copyApi = isolated.loadClass("api.Task");
            Object isolatedObject =
                    isolated.loadClass("plugin.Worker")
                            .getDeclaredConstructor().newInstance();

            System.out.println("isolated API same: "
                    + (copyApi == Task.class));
            System.out.println("isolated implements host API: "
                    + (isolatedObject instanceof Task));

            try {
                Task invalid = (Task) isolatedObject;
                System.out.println(
                        "unexpected API cast success: " + invalid.run());
            } catch (ClassCastException expected) {
                System.out.println(
                        "isolated API cast: ClassCastException");
            }
        }
    }
}
~~~

**Cơ chế của từng loader:**

- `a` và `b` lấy **host loader làm parent**. Với `api.Task`, cả hai delegate về host. Nhưng parent không có `plugin.Worker` nên chúng tự define Worker khác nhau.
- `isolated` dùng **platform loader làm parent**, không dùng application loader của host. Khi nó cần `api.Task`, parent không nhìn thấy Task của ứng dụng, nên isolated định nghĩa Task từ `out/plugin`.
- Ba loader đều trỏ tới cùng URL thư mục `out/plugin`; khác biệt đến từ **parent/delegation và defining loader**, không phải khác tên file.
- `try-with-resources` đóng loader sau thí nghiệm; việc đóng không hứa hẹn class đã unload ngay.

### Lệnh Linux/macOS

Đứng trong thư mục `example` có ba source files:

~~~bash
mkdir -p out/host out/plugin

javac --release 17 -d out/host \
  src/api/Task.java src/host/IdentityDemo.java

javac --release 17 -d out/plugin \
  src/api/Task.java src/plugin/Worker.java

java -cp out/host IdentityDemo out/plugin
~~~

### Lệnh Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out\host, out\plugin | Out-Null
javac --release 17 -d out\host src\api\Task.java src\host\IdentityDemo.java
javac --release 17 -d out\plugin src\api\Task.java src\plugin\Worker.java
java -cp out\host IdentityDemo out\plugin
~~~

Việc compile `Task.java` hai lần là **cố ý để tạo bản copy** cho thử nghiệm. Khi build thật, API contract nên được định nghĩa nhất quán ở parent và không được child define một bản runtime thứ hai.

### Stdout chính xác đã kiểm chứng

~~~text
same binary name: true
same runtime Class: false
defined by A/B: true
A isInstance(B): false
cross-loader cast: ClassCastException
shared API A: true
shared API B: true
A via API: plugin-ok
B via API: plugin-ok
isolated API same: false
isolated implements host API: false
isolated API cast: ClassCastException
~~~

Bài đã được biên dịch bằng `javac --release 17` và chạy trên OpenJDK 21. Đầu ra trên khớp từng dòng.

### Diễn giải kết quả

1. **same binary name: true** — A và B đều tải `plugin.Worker`.
2. **same runtime Class: false** — Worker do hai defining loaders khác nhau tạo.
3. **defined by A/B: true** — hai implementation thực sự được định nghĩa riêng.
4. **A isInstance(B): false** — B object không thuộc A concrete class.
5. **cross-loader cast: ClassCastException** — cast chéo concrete class thất bại đúng dự kiến.
6. **shared API A/B: true** — A/B đều nhận bản `api.Task` ở host do parent-first.
7. **A/B via API: plugin-ok** — host vẫn giao tiếp được với cả hai Worker qua cùng interface Task.
8. **isolated API same: false** — loader cô lập đã định nghĩa Task riêng từ plugin root.
9. **isolated implements host API: false** — một Worker implements isolated Task không phải instance của host Task.
10. **isolated API cast: ClassCastException** — phép ép sang host interface thất bại.

Đây là cách tái hiện **hai lỗi định danh riêng biệt**: cast concrete implementation A ↔ B, và cast một implementation có copy interface vào interface của host.

## 7. Cách sửa trong ứng dụng plugin thực tế

Kiến trúc nên có một **shared API package** và những implementation loaders riêng:

~~~text
Parent / Host ClassLoader
  ├── api.Task       (một runtime interface duy nhất)
  └── PluginManager
      |
      +--- Plugin Loader v1
      |       plugin.Worker
      |
      +--- Plugin Loader v2
              plugin.Worker
~~~

Host chỉ phụ thuộc API:

~~~java
Class<?> impl = pluginLoader.loadClass("plugin.Worker");
api.Task task = (api.Task) impl
        .getDeclaredConstructor().newInstance();

System.out.println(task.run());
~~~

Đây là đoạn code minh họa trong method, với `pluginLoader`, interface Task và constructor/method hợp lệ. Implementation v1 và v2 **không cần cast qua lại**.

Biện pháp thực tế:

- **Chỉ một chủ sở hữu API:** package `api.*` trong loader cha; plugin biên dịch dựa vào API ấy nhưng runtime dùng bản cha.
- **Parent-first cho API/shared types:** nếu chọn child-first để cô lập dependency plugin, loại trừ package contract khỏi chính sách child-first.
- **Không trao concrete objects qua boundary khi không cần:** dùng interface, DTO được chia sẻ, các primitive/string hoặc message/serialization.
- **Đồng nhất types trong signatures:** exceptions, return values, method parameters, DTO và parent interfaces cần có class identity thống nhất khi đi qua ranh giới.
- **Plugin isolation có kiểm thử:** xác nhận `pluginLoader.loadClass("api.Task") == api.Task.class` và `api.Task.class.isAssignableFrom(impl)`.
- **Đừng chỉ sửa dependency scope:** Maven `provided` hoặc Gradle `compileOnly` có thể giúp không đóng gói bản runtime API thứ hai, nhưng host **phải cung cấp thật API** và loader policy cần delegate chính xác.
- **JAR shading/relocation có cân nhắc:** cách ly private dependencies bằng tên package riêng có thể tránh xung đột, nhưng không relocate interface API chung nếu host cần cast qua interface đó.

Một plugin JAR có API trùng tên **không nhất thiết phải gây lỗi** khi child parent-first; mặt khác, một custom loader child-first sai có thể tạo bản sao dù build tree trông “sạch”. Phải kiểm tra bằng runtime facts.

## 8. Debug thực tế: in đúng Class và defining loader

Khi có ClassCastException, đừng chỉ in tên hai class. Hãy in đủ:

~~~java
static void inspect(Object actualObject, Class<?> expected) {
    Class<?> actual = actualObject.getClass();

    System.out.println("actual: " + actual.getName());
    System.out.println("expected: " + expected.getName());
    System.out.println("same Class: " + (actual == expected));
    System.out.println("compatible: "
            + expected.isInstance(actualObject));
    System.out.println("actual loader: " + actual.getClassLoader());
    System.out.println("expected loader: " + expected.getClassLoader());
    System.out.println("actual module: " + actual.getModule());
    System.out.println("expected module: " + expected.getModule());
}
~~~

Đây là **helper minh họa**, không phải chương trình chạy độc lập. Tên loader/identity string và module có thể thay đổi theo JVM.

**Quan trọng:** nếu `expected` là một interface thì `actual == expected` thường false dù cast **hợp lệ** (implementation khác interface). Vì vậy hãy kiểm tra `expected.isInstance(actualObject)` và **identity của interface thực sự được implementation nạp**:

~~~java
Class<?> taskSeenByPlugin =
        pluginLoader.loadClass("api.Task");

System.out.println(taskSeenByPlugin == api.Task.class);
~~~

Kết quả false là chỉ dấu mạnh về hai interface classes khác nhau. Nhưng kết quả true chỉ chứng minh **Task identity** là chung; vẫn cần kiểm tra implementation thật sự implements Task và constructor/linking không có lỗi khác.

### Kiểm tra CodeSource và modules

Khi cần xác định JAR vật lý:

~~~java
Class<?> type = actualObject.getClass();
var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();

System.out.println(source == null
        ? "(unknown source)"
        : source.getLocation());
~~~

Không bảo đảm mọi class đều có CodeSource URL hữu ích; custom loaders có thể cung cấp metadata khác hoặc null. **CodeSource chỉ giúp điều tra nguồn bytes**, còn defining loader vẫn là yếu tố cần thiết cho type identity.

`Class.getModule()` giúp phân biệt named/unnamed modules trên Java 9+, nhưng **cùng một module name không tự làm hai classes khác defining loader trở thành cùng kiểu**. Các lớp thuộc bootstrap loader có thể trả `getClassLoader() == null`; null ở đây **không** nghĩa class chưa được nạp.

### Log nạp lớp

JDK 17+ có thể dùng:

~~~bash
java -Xlog:class+load=info -cp out/host IdentityDemo out/plugin
~~~

Đây là lệnh chẩn đoán, output sẽ dài và khác nhau giữa JDKs; lọc theo `plugin.Worker` và `api.Task`. Không dùng toàn bộ log như stdout cố định của bài.

## 9. Phân biệt ClassCastException với các lỗi loader khác

| Exception/Error | Hiện tượng | Hướng điều tra |
| --- | --- | --- |
| `ClassNotFoundException` | Lookup bằng tên không tìm thấy class. | Loader đang được hỏi có source/URL/module nào? |
| `NoClassDefFoundError` | Một dependency không thể được định nghĩa khi cần, hoặc class có initialization failure trước đó. | Cause và defining loader của class chứa symbolic reference. |
| `ClassCastException` | Object không tương thích với runtime target type. | Hai class/interface có cùng defining loader identity không? |
| `LinkageError: loader constraint violation` | JVM phát hiện yêu cầu type identity không nhất quán giữa loader tại linking. | Shared method/field signature types và loading constraints. |
| `NoSuchMethodError` | Runtime method được resolve không khớp bản compile. | Version/dependency parent-vs-child. |
| `IllegalAccessError` | JVM access checks thất bại. | Module exports, package access, JVM linking. |

ClassCastException cũng có thể là một lỗi cast **thông thường không liên quan nhiều loaders**, ví dụ ép Integer thành String. Chỉ kết luận xung đột loader khi metadata của hai runtime types chứng minh điều đó.

Ngược lại, trong một số tương tác xuyên loader, JVM áp dụng **loading constraints** cho type names trong method/field signatures để bảo vệ type safety. Lỗi có thể xuất hiện dưới dạng `LinkageError` **trước khi** có phép cast cụ thể.

## 10. Reload plugin và ClassCastException sau deploy

Một quá trình hot reload thường tạo loader mới cho version khác:

~~~text
Loader L1: plugin.Worker (v1)
Loader L2: plugin.Worker (v2)
~~~

Nếu host giữ object của L1 rồi cố cast nó sang **concrete Class của L2**, lỗi hoàn toàn có thể xảy ra, dù v1 và v2 có code tương tự.

Quy trình an toàn:

1. Thiết kế host–plugin boundary bằng interface/DTO ở parent.
2. Đưa v2 vào loader mới, thử tạo instance và cast qua **shared interface**.
3. Chuyển routing của request mới sang v2 sau health check.
4. Đợi request v1 hoàn tất; dừng callbacks, tasks, threads, unregister và đóng resources v1.
5. Đóng loader v1 khi thích hợp; bỏ references cũ từ caches/registries/ThreadLocal/TCCL.
6. Không cast implementation object từ v1 thành concrete class v2.

`URLClassLoader.close()` không tự xóa class/object đã nạp. Class unloading còn phụ thuộc reachability và GC. Đừng dùng `System.gc()` hoặc restart JVM như giải pháp mặc định nếu lỗi thực tế là trộn runtime class identities; trước hết sửa ranh giới chia sẻ và lifecycle.

## 11. Thread Context ClassLoader và ServiceLoader

Thread context class loader (TCCL) là loader mà framework có thể **chủ động chọn** để tìm services/resources:

~~~java
Thread current = Thread.currentThread();
ClassLoader old = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Gọi framework/API có hợp đồng tìm service bằng TCCL.
} finally {
    current.setContextClassLoader(old);
}
~~~

Đoạn minh họa cần biến `pluginLoader` tồn tại. Một ví dụ API chủ động dùng TCCL là `ServiceLoader.load(ServiceType.class)`. Tuy nhiên TCCL **không sửa được type identity** nếu provider implements bản copy interface khác. Một plugin do TCCL tìm thấy vẫn phải tương thích với Class service ở host.

Không nhầm TCCL với defining loader: khi JVM resolve symbolic references trong bytecode, nó dựa trên defining loader của class chứa reference cùng các loading constraints; nó không tự hỏi TCCL cho mọi dependency.

Với ứng dụng JPMS, `exports` và `opens` điều khiển access/reflection qua module boundary, nhưng không hợp nhất hai Class objects do hai defining loaders khác nhau tạo. Sửa xung đột loader bằng `--add-opens` thường không đúng nguyên nhân.

## 12. Checklist chẩn đoán và ôn tập

Hướng chẩn đoán khi cast lỗi:

1. **Object nào** đang cast và **target Class** nào là đích?
2. Binary name của hai lớp là gì? Có phải chỉ giống tên không?
3. Defining loader của actual class và expected type là ai?
4. Nếu target là interface, plugin có dùng đúng **Class interface** của parent không?
5. Có duplicate API JAR trong plugin, shaded JAR hoặc child-first quá rộng không?
6. Parent loader có vô tình nạp plugin implementation trên application classpath không?
7. Sau reload, có trộn object v1 với Class v2 không?
8. Có thể thay cast concrete implementation bằng cast qua shared interface không?
9. Nếu xảy ra LinkageError/NoSuchMethodError, dependency versions hoặc loading constraints có bất nhất không?
10. Với JPMS, access failure do exports/opens có bị nhầm với ClassCastException không?
11. Cache, callback, TCCL, ThreadLocal hoặc registry nào còn giữ refs loader cũ?
12. Có test runtime class identity bằng `==`, `isInstance` và `isAssignableFrom` chưa?

### Câu hỏi tự kiểm tra

**Câu 1.** Hai loader cùng đọc bytecode Worker và trả class có tên `plugin.Worker`. Tại sao `classA == classB` false?

**Đáp:** JVM phân biệt class runtime theo **binary name và defining loader**. Cùng bytecode/tên không làm hai định nghĩa trở thành một.

**Câu 2.** Worker của Loader A và Loader B có thể cùng được ép sang `api.Task` không?

**Đáp:** Có, nếu cả hai implementation đều thực sự implements **cùng runtime interface Task** do một loader chung định nghĩa.

**Câu 3.** Plugin source có `implements api.Task`, nhưng host cast object vào Task lại lỗi. Vì sao?

**Đáp:** Plugin có thể đã dùng **Task được loader riêng định nghĩa**, khác Task của host; import/name giống nhau chưa đủ.

**Câu 4.** JAR chứa bản copy Task có chắc gây cast lỗi không?

**Đáp:** Không. Nếu parent-first delegate về Task do parent định nghĩa, copy ở child có thể không được load.

**Câu 5.** Có thể dùng `--add-opens` để hợp nhất hai classes trùng tên khác loader không?

**Đáp:** Không. Opens chỉ tác động tới access/reflection của JPMS, không đổi danh tính Class.

**Câu 6.** Cast concrete implementation giữa hai phiên plugin sau reload có phải luôn hợp lệ nếu hai phiên bản cùng source?

**Đáp:** Không. Nếu chúng do hai defining loaders khác nhau định nghĩa, concrete runtime classes khác nhau. Dùng shared API boundary thay thế.

## Tài liệu chuẩn

- [JVMS Java SE 21 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): danh tính class theo binary name và defining loader.
- [JVMS Java SE 21 §5.3.4 — Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.4): bảo vệ type safety khi nhiều loaders.
- [JLS Java SE 21 §12.2.2 — Class Loader Consistency](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2.2): consistency của class loader.
- [Java SE 21 — java.lang.Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `cast`, `isInstance`, `isAssignableFrom` và `getClassLoader`.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): delegation và defining loader.
- [Java SE 21 — ClassCastException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassCastException.html): exception cast runtime không tương thích.
