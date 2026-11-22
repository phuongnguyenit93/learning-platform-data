# Nhận diện mô hình cô lập trong container và test runner

## 1. Vì sao phải nhận diện đúng kiểu cô lập?

Trong Java, **cô lập (isolation)** không chỉ có một nghĩa. Một ứng dụng server có thể chạy nhiều web applications trong cùng JVM nhưng mỗi ứng dụng dùng một ClassLoader riêng. Một test runner có thể tạo đối tượng test mới cho từng phương thức nhưng vẫn giữ **cùng class loader và các static fields**. Một build tool có thể chạy tests trong **JVM forked process**; khi ấy cả heap, static fields, loader instances và nhiều trạng thái VM đều tách khỏi process build.

Nếu không biết hệ thống đang dùng tầng cô lập nào, ta dễ kết luận sai:

- “Hai ứng dụng cùng tên class nên chắc là một kiểu.”
- “JUnit tạo test object mới nên static fields được reset.”
- “Đóng URLClassLoader nghĩa là JVM đã unload class.”
- “Chạy test song song bằng nhiều thread giống chạy bằng nhiều JVM.”
- “Container đã cô lập plugin nên các plugin không thể ảnh hưởng tới nhau.”
- “Plugin class loader có thể nhìn thấy mọi class trong host.”
- “Mọi container đều dùng parent-first giống ClassLoader mặc định.”

**Mục tiêu bài học:** phân biệt và nhận diện **cô lập theo object/test instance, thread, ClassLoader, Module/ModuleLayer, JVM process và container hệ điều hành**, với các dấu hiệu runtime cụ thể để debug ClassLoader trong **application container** và **test runner**.

Chủ đề thuộc nhóm **Kiến trúc plugin**, nên trọng tâm là **ranh giới tìm/nạp class, định danh kiểu, chia sẻ API, quản lý trạng thái và vòng đời**; không coi cô lập là một công tắc bảo mật duy nhất.

## 2. Bản đồ các tầng cô lập

| Tầng | Cách hình thành | Có thể tách | Không mặc nhiên tách |
|---|---|---|---|
| Test instance/object | Tạo instance mới của class test | Instance fields của object mới | Static fields, JVM, class loader, database |
| Thread | Chạy code trên Thread khác | Call stack, thread-local state | Heap, static fields, class definitions |
| ClassLoader | Loader khác định nghĩa cùng binary name | Runtime class identity, static fields của class riêng, class namespace | Process, heap nói chung, file/socket, APIs chia sẻ |
| JPMS Module/Layer | Module graph, `requires`/`exports`/`opens` và loader mapping | Readability/encapsulation, service discovery, phạm vi module | Process, heap, bảo mật sandbox tổng quát |
| JVM process | OS process khác chạy JVM khác | Heap/GC, static state, class loader graph, system properties, process-level caches | File system, database, network, external services |
| OS container | Namespaces, cgroups, mount/network configuration | Nhiều tài nguyên ở mức OS tùy cấu hình | External resources/volumes, kernel, endpoint dùng chung |

**Không có thứ tự “tầng cao bao hàm mọi quyền bảo mật” đơn giản:** ClassLoader tách danh tính runtime type nhưng không cấm plugin tự gọi API file/network; module đóng gói API chứ không phải sandbox; JVM process tách bộ nhớ nhưng vẫn có thể dùng chung một database. Một OS container còn phụ thuộc cấu hình mount, network, capabilities và chính sách triển khai.

Để chẩn đoán tình huống cụ thể, phải xác định **cái gì được chia sẻ**, **cái gì được tái tạo**, **khi nào được làm sạch**.

## 3. ClassLoader isolation: cùng tên không đồng nghĩa cùng runtime class

Với class bình thường, JVM phân biệt các runtime classes bằng **binary name** và **defining ClassLoader**. Vì thế:

```text
Shared Parent Loader
     ├── shared.api.PluginContract
     │
     ├── AppLoader-A
     │     └── app.impl.Worker
     │
     └── AppLoader-B
           └── app.impl.Worker
```

Hai bản `app.impl.Worker` có thể cùng binary name, cùng bytes từ cùng JAR nhưng **khác runtime class** nếu được định nghĩa bởi hai loaders độc lập. Mỗi bản có **static fields riêng** và có thể khởi tạo class riêng.

Một ví dụ về danh tính:

```java
// Trích đoạn, không phải chương trình độc lập:
Class<?> a = loaderA.loadClass("app.impl.Worker");
Class<?> b = loaderB.loadClass("app.impl.Worker");

System.out.println(a.getName().equals(b.getName())); // true
System.out.println(a == b);                          // false nếu mỗi loader tự define
```

Câu thứ hai **chỉ** cho `false` nếu mỗi loader thực sự định nghĩa bản riêng. Nếu cả hai ủy quyền cho cùng parent đã có `app.impl.Worker`, `a == b` có thể là `true`.

### Defining loader khác initiating loader

`loadClass(name)` trên loader con có thể tìm class từ parent. Khi đó:
- Loader con là bên **khởi xướng yêu cầu**.
- Defining loader của class trả về có thể là **parent**.
- `type.getClassLoader()` cho biết **defining loader**, không nhất thiết là loader ban đầu được gọi.

Để nhận diện cô lập thật, **không chỉ nhìn tên loader của biến được truyền vào `loadClass`**. Hãy xem chính đối tượng `Class<?>` được trả về và defining loader của nó.

## 4. Parent-first, child-first và nguồn class thực sự được chọn

Thuật toán mặc định của `ClassLoader.loadClass` theo hướng parent-first:

```text
loadClass(name)
    │
    ▼
findLoadedClass(name)
    │ không có
    ▼
parent.loadClass(name) / bootstrap
    │ cha không tìm thấy
    ▼
findClass(name) trên loader hiện tại
    │
    ▼
Class<?> runtime
```

Trong hệ plugin, **parent-first** rất phù hợp với những **API chung**: service interfaces, DTO và protocol types phải được host và plugin hiểu như cùng một runtime class.

Ngược lại, **child-first** có thể có ích khi mỗi plugin cần bản dependency riêng, nhưng phải có quy tắc rõ:
- Không cố override những Java platform classes.
- Không định nghĩa lại host/shared API ở child.
- Xác định package nào là private của plugin và package nào thuộc container.
- Đừng catch mọi `LinkageError` rồi âm thầm fallback sang bản class khác.
- Kiểm tra package access và type identity ở đường callback giữa plugin và host.

**Child-first không đồng nghĩa cô lập hoàn toàn:** class platform, API chung và các nguồn tài nguyên có thể vẫn dùng chung; chính sách class/resource lookup thực tế còn tùy framework.

## 5. Container web application: sơ đồ ClassLoader thường gặp

Các application servers/web containers như Tomcat dùng nhiều loaders để phân chia phần runtime container và các web applications. Mô hình khái niệm thường gặp:

```text
Bootstrap / Platform
         │
       System
         │
       Common
       /    \
   Webapp-A  Webapp-B
      │         │
  WEB-INF/  WEB-INF/
  classes   classes
  + lib     + lib
```

Ở cấu hình thông thường:
- **Common loader** cung cấp thư viện container hoặc thành phần chia sẻ.
- **Webapp-A** nhìn thấy lớp/resource riêng trong `WEB-INF/classes` và JAR ở `WEB-INF/lib`.
- **Webapp-B** có vùng triển khai riêng tương ứng.
- Mỗi webapp loader có thể định nghĩa bản riêng của cùng binary name từ JAR nằm trong webapp.
- Những API/platform classes và một số API servlet/container thường được ủy quyền cho loader phía trên.

**Ví dụ Tomcat:** tài liệu Class Loader How-To mô tả Webapp loader mặc định ưu tiên các repositories nội bộ webapp đối với nhiều application classes (**local-first**), khác với parent-first mặc định của `ClassLoader`; nhưng có ngoại lệ cho JRE base và các Jakarta EE API do container cung cấp. Có thể có cấu hình `<Loader delegate="true"/>` khiến quy tắc ưu tiên delegation thay đổi.

Điều này cho thấy **“Java ClassLoader là parent-first” không đủ để đoán hành vi mọi container**. Phải đọc chính sách của runtime cụ thể và deployment setup.

### Khi nào hai webapps chia sẻ kiểu?

Giả sử cả hai webapps dùng:
- API `jakarta.servlet.Servlet` do container cung cấp từ tầng chung.
- `com.example.JsonHelper` được đóng gói riêng trong từng `WEB-INF/lib`.

Chúng có thể dùng **cùng runtime type** `jakarta.servlet.Servlet` nhưng dùng **hai runtime types khác nhau** `com.example.JsonHelper`. Nếu `JsonHelper` chứa một static cache, mỗi webapp sẽ có cache riêng **nếu** mỗi loader thật sự tự định nghĩa class đó. Nếu class được đặt ở common loader và được dùng từ tầng đó, static cache có thể chia sẻ.

**Không đoán theo JAR name**; một JAR có mặt ở hai nơi không đủ để quyết định class nào đang được dùng. Cần kiểm tra defining loader và code source.

## 6. Shared API là “cầu nối” bắt buộc giữa các loader

Nếu plugin A triển khai `api.Service` được định nghĩa bởi loader A, còn host dùng `api.Service` được định nghĩa bởi parent, hai interfaces cùng tên **không phải cùng kiểu**. Kết quả có thể là:
- `ClassCastException` khi ép kiểu.
- `ServiceConfigurationError` khi ServiceLoader thấy provider không assignable.
- `LinkageError` hoặc `IllegalAccessError` khi cấu trúc dependency khác runtime.
- Reflection thấy tên giống nhưng `==` trên `Class<?>` trả `false`.

Thiết kế tốt:

```text
             Host / Shared API Loader
                      │
                  api.Service
                      │
           ┌──────────┴─────────┐
           │                    │
      PluginLoader-A       PluginLoader-B
       impl.ServiceA        impl.ServiceB
           │                    │
           └──── implements api.Service ────┘
```

Plugin implementations riêng, **API dùng chung**. Host nhận đối tượng qua interface chung, không ép sang implementation class của một loader khác.

## 7. Demo Java 17+: hai loader, hai static states, một shared interface

Đây là phép thử thực tế để **nhận diện cô lập theo ClassLoader**. Chương trình tạo **hai `URLClassLoader` instances** trên cùng directory chứa implementation. Chúng cùng dùng host loader làm parent, nên cùng dùng một interface `CounterService`. Nhưng chúng định nghĩa hai bản class implementation riêng với static counters khác nhau.

### 7.1. Cấu trúc thư mục

```text
loader-isolation/
├── src/
│   ├── api/CounterService.java
│   ├── plugin/CounterImpl.java
│   └── host/IsolationDemo.java
├── host-out/
└── plugin-out/
```

### 7.2. src/api/CounterService.java

```java
package example.api;

public interface CounterService {
    int next();
}
```

### 7.3. src/plugin/CounterImpl.java

```java
package example.impl;

import example.api.CounterService;

public final class CounterImpl implements CounterService {
    private static int counter = 0;

    public CounterImpl() {
    }

    @Override
    public int next() {
        return ++counter;
    }
}
```

### 7.4. src/host/IsolationDemo.java

```java
package example.host;

import example.api.CounterService;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class IsolationDemo {
    public static void main(String[] args) throws Exception {
        URL location = Path.of("plugin-out").toUri().toURL();
        ClassLoader parent = IsolationDemo.class.getClassLoader();

        try (URLClassLoader a = new URLClassLoader(
                     new URL[] {location}, parent);
             URLClassLoader b = new URLClassLoader(
                     new URL[] {location}, parent)) {

            Class<?> classA = a.loadClass("example.impl.CounterImpl");
            Class<?> classB = b.loadClass("example.impl.CounterImpl");

            CounterService a1 = (CounterService)
                    classA.getDeclaredConstructor().newInstance();
            CounterService a2 = (CounterService)
                    classA.getDeclaredConstructor().newInstance();
            CounterService b1 = (CounterService)
                    classB.getDeclaredConstructor().newInstance();

            System.out.println("A first: " + a1.next());
            System.out.println("A second: " + a2.next());
            System.out.println("B first: " + b1.next());

            System.out.println("same implementation class: "
                    + (classA == classB));
            System.out.println("both use shared API: "
                    + (a1 instanceof CounterService
                       && b1 instanceof CounterService));
            System.out.println("A defined by A: "
                    + (classA.getClassLoader() == a));
            System.out.println("B defined by B: "
                    + (classB.getClassLoader() == b));

            try {
                classA.cast(b1);
                System.out.println("unexpected cross-cast");
            } catch (ClassCastException expected) {
                System.out.println("cross-loader cast rejected");
            }
        }
    }
}
```

### 7.5. Biên dịch đúng classpath

Tạo các thư mục. Trên Bash:

```bash
mkdir -p host-out plugin-out
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force host-out,plugin-out | Out-Null
```

Biên dịch/chạy với JDK 17+:

```bash
javac --release 17 -d host-out src/api/CounterService.java src/host/IsolationDemo.java
javac --release 17 -cp host-out -d plugin-out src/plugin/CounterImpl.java
java -cp host-out example.host.IsolationDemo
```

**Tuyệt đối không thêm `plugin-out` vào host classpath khi thử ví dụ**. Nếu có, parent loader có thể định nghĩa `example.impl.CounterImpl` trước; hai URLClassLoader sẽ ủy quyền cho cùng parent và kết quả cô lập static states không còn đúng.

Cấu trúc output:

```text
host-out/
├── example/api/CounterService.class
└── example/host/IsolationDemo.class

plugin-out/
└── example/impl/CounterImpl.class
```

### 7.6. Stdout mong đợi

```text
A first: 1
A second: 2
B first: 1
same implementation class: false
both use shared API: true
A defined by A: true
B defined by B: true
cross-loader cast rejected
```

**Giải thích:**

1. `classA` và `classB` có cùng binary name `example.impl.CounterImpl`, nhưng hai defining loader instances khác nhau; do đó `classA != classB`.
2. Static field `counter` của classA được tăng từ 0 → 1 → 2; classB có **static counter riêng**, tăng từ 0 → 1.
3. Cả hai classes implements **cùng `CounterService` do parent định nghĩa**, vì host/shared API chỉ được đặt ở `host-out`. Do đó có thể cast objects của cả hai về service interface.
4. Nhưng `classA.cast(b1)` không hợp lệ: b1 là instance của classB, không phải classA. Class cast dựa trên **type identity**, không phải tên chuỗi.
5. `URLClassLoader.close()` khi rời try-with-resources đóng tài nguyên loader quản lý; nó **không chứng minh class đã unload hoặc static state bị GC ngay**.

Đây là ví dụ **một JVM, hai loaders**. Các biến hệ thống, heap, sockets và filesystem vẫn dùng chung process. Nó không cung cấp process isolation.

## 8. Test runner: cô lập test instance không phải cô lập ClassLoader

**JUnit Jupiter** mặc định tạo **một instance mới của test class cho mỗi test method** (lifecycle `PER_METHOD`). Điều này giảm nhiễm **instance fields**, nhưng không có nghĩa:
- JVM mới cho mỗi method;
- ClassLoader mới cho mỗi method;
- static fields của class test được reset;
- database/file/temp directory được reset;
- code trong background thread tự dừng.

Mẫu JUnit 5 minh họa:

```java
// Trích đoạn test class khi dự án đã có JUnit Jupiter dependency:
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class StateIsolationTest {
    private int instanceCount = 0;
    private static int sharedCount = 0;

    @Test
    void first() {
        assertEquals(1, ++instanceCount);
        ++sharedCount;
    }

    @Test
    void second() {
        assertEquals(1, ++instanceCount);
        ++sharedCount;
    }
}
```

Đây là **trích đoạn dự án JUnit**, không phải chương trình Java SE chạy độc lập; cần JUnit Jupiter dependency, engine và test runner. Hai phép assert với instance field sẽ đúng trong mặc định `PER_METHOD`. **Không dự đoán số cuối của sharedCount theo thứ tự test** nếu không đặt quy tắc execution order; giá trị static tồn tại theo runtime class, không reset chỉ vì JUnit tạo test instance mới.

Có thể dùng `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` nếu muốn một test object dùng chung; điều này càng tăng khả năng chia sẻ instance state giữa methods, nhưng **vẫn không thay đổi bản chất static hoặc JVM process isolation**.

### Static contamination qua tests

Một class:

```java
public final class GlobalState {
    public static int count = 0;
}
```

Nếu hai tests thuộc cùng defining loader trong cùng JVM, chúng có thể thấy **cùng `GlobalState.count`**. Test một tăng biến; test hai chạy sau có thể nhận giá trị khác giả định. Đó là nguyên nhân phổ biến của tests chỉ fail khi chạy cả suite, nhưng pass khi chạy riêng.

Cách sửa:
- Reset static state có kiểm soát ở `@BeforeEach`/`@AfterEach` nếu phù hợp.
- Tránh global mutable static state khi thiết kế ứng dụng.
- Dùng dependency injection/test fixtures độc lập.
- Nếu thư viện bên thứ ba không thể reset, dùng **forked JVM** hoặc lớp isolation mạnh hơn theo công cụ build.

## 9. Demo Java 17+ không cần JUnit: static state trong một process

Tạo file `ProcessStateDemo.java`:

```java
public final class ProcessStateDemo {
    private static int counter = 0;

    public static void main(String[] args) {
        System.out.println("test A: " + ++counter);
        System.out.println("test B: " + ++counter);
    }
}
```

Chạy:

```bash
javac ProcessStateDemo.java
java ProcessStateDemo
java ProcessStateDemo
```

Mỗi process in cùng hai dòng:

```text
test A: 1
test B: 2
```

Vì ta chạy `java ProcessStateDemo` **hai lần**, shell tạo **hai JVM processes**, và static state bắt đầu lại trong process thứ hai. Trong **một lần chạy**, “test A” và “test B” (đây chỉ là các nhãn in) cùng dùng class `ProcessStateDemo` nên chia sẻ counter.

Đây là phép đối chiếu **process boundary**: hai JVM khác nhau không chia sẻ cùng heap/class static fields. Dĩ nhiên, cả hai vẫn có thể thao tác cùng file hoặc database nếu code yêu cầu.

## 10. Gradle Test: forked JVM và worker reuse

Với Gradle Java/JVM testing, `Test` task thường chạy tests trong **forked JVM worker process** tách khỏi process build. Nhưng **một worker process có thể chạy nhiều test classes**, nên **forked JVM không mặc nhiên có nghĩa mỗi test class/method một JVM**.

Các cấu hình chính:

| Gradle Test property | Ý nghĩa thực tế |
|---|---|
| `maxParallelForks` | Số test JVM worker processes tối đa chạy song song cho một Test task |
| `forkEvery` | Số test classes/definitions tối đa một process xử lý trước khi được thay bằng process mới; `0` nghĩa là không áp giới hạn |
| `maxHeapSize` | Heap size của forked test JVM |
| `jvmArgs` | JVM options cho workers |
| `useJUnitPlatform()` | Chọn chạy test bằng JUnit Platform |

Ví dụ `build.gradle.kts` của dự án Gradle Kotlin DSL:

```kotlin
tasks.test {
    useJUnitPlatform()
    maxParallelForks = 2
    forkEvery = 1
    maxHeapSize = "512m"
}
```

Đây là **đoạn cấu hình Gradle**, không phải Java source tự chạy bằng `javac`. Phải có Gradle project/JUnit dependencies thích hợp.

Diễn giải:
- Cho phép tối đa hai forked test JVM workers chạy đồng thời theo giới hạn Gradle.
- `forkEvery=1` định hướng tạo process mới sau mỗi test class/definition, tăng cô lập process **giữa test classes**, nhưng tốn thời gian khởi động JVM.
- Không đồng nghĩa mỗi test **method** được cô lập bằng process khác.
- Những tests dùng chung filesystem/database/external service vẫn có thể gây nhiễm lẫn nhau, dù ở hai JVM processes.

**Cẩn trọng hiệu năng:** giá trị `forkEvery` quá nhỏ làm test suite chậm rõ rệt. Chỉ tăng process isolation khi có nhu cầu rõ ràng như library giữ static state khó reset hoặc memory/resource leaks cần hạn chế.

## 11. Maven Surefire/Failsafe: fork process và ClassLoader strategy

**Maven Surefire** có nhiều cách khởi chạy tests và dựng test classpath. Không nên coi nó luôn chỉ là một `java -cp ...` trong chính Maven JVM.

Những tùy chọn hữu ích khi debug:
- `forkCount`: cấu hình số lượng forked JVM test processes trong các phiên bản plugin hỗ trợ.
- `reuseForks`: điều khiển việc tái sử dụng forked processes giữa nhiều tests/test classes theo cấu hình.
- `useSystemClassLoader`: ảnh hưởng chiến lược sử dụng system class loader so với isolated loader trong những chế độ chạy.
- `useManifestOnlyJar`: sử dụng manifest-only JAR cho classpath dài khi phù hợp.
- `argLine`: truyền JVM arguments cho forked test process trong cấu hình thường gặp.

Trích đoạn `pom.xml`:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.5.3</version>
      <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Đây là **trích đoạn POM**, không phải `pom.xml` đầy đủ để chạy độc lập. Plugin version là ví dụ cấu hình, cần đối chiếu với phiên bản dự án thực tế.

Nếu test class được nạp bởi **isolated test ClassLoader** thay vì system class loader, có thể thấy:
- `Class.forName(name)` từ test code tìm classes khác với code chạy trong Maven/plugin realm.
- Resources/providers tìm qua TCCL thay đổi.
- Reflection hoặc `instanceof` giữa thư viện trong test và Maven plugin class realm có thể không tương thích do class identity.

**Fork process và loader isolation là hai quyết định tách biệt:** fork tạo JVM mới; bên trong process đó vẫn có class loader hierarchy và chiến lược nạp riêng. Không sửa một lỗi type identity chỉ bằng việc đoán `forkCount` sẽ giải quyết mọi thứ.

## 12. Nhận diện test chạy song song bằng thread hay process

Một số cơ chế chạy song song:
- JUnit Platform có thể thực hiện methods/classes trên nhiều worker threads trong **cùng một JVM**.
- Gradle `maxParallelForks` chạy nhiều **JVM test worker processes**.
- Build system hoặc CI có thể chạy nhiều test tasks/jobs trong nhiều processes/machines.
- Một custom runner có thể tạo class loaders độc lập trong cùng JVM để thực thi test suites.

Bảng dấu hiệu:

| Dấu hiệu quan sát | Nhiều threads, một JVM | Nhiều ClassLoaders, một JVM | Nhiều JVM processes |
|---|---|---|---|
| Process ID | Giống | Giống | Khác |
| Static state của cùng runtime class | Thường chia sẻ | Riêng nếu được định nghĩa riêng | Riêng |
| `Class<?>` của cùng binary name | Cùng nếu cùng defining loader | Có thể khác | Không so sánh object trực tiếp giữa processes |
| Heap | Chung | Chung | Tách |
| ClassLoader identity | Thường cùng | Khác | Mỗi process có graph riêng |
| ThreadLocal | Riêng theo thread | Phụ thuộc thread; không phải auto loader isolation | Không chia sẻ process |
| File/database ngoài process | Có thể chung | Có thể chung | Vẫn có thể chung |

**Một JVM process** được xác nhận qua process-level diagnostics. **Hai Java objects của loader khác nhau** chưa đủ nói chúng định nghĩa hai classes riêng, vì parent delegation có thể trả cùng class.

## 13. Runtime probes: in ra điều gì để biết đang bị cô lập ở đâu?

Khi chạy trong container/test runner, tạo helper như sau:

```java
public final class RuntimeProbe {
    private RuntimeProbe() {
    }

    public static void print(Class<?> type) {
        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("thread=" + Thread.currentThread().getName());
        System.out.println("name=" + type.getName());
        System.out.println("loader=" + type.getClassLoader());
        System.out.println("module=" + type.getModule());
        System.out.println("TCCL="
                + Thread.currentThread().getContextClassLoader());
        System.out.println("source="
                + (type.getProtectionDomain().getCodeSource() == null
                    ? "<unknown>"
                    : type.getProtectionDomain().getCodeSource().getLocation()));
    }

    public static void main(String[] args) {
        print(RuntimeProbe.class);
    }
}
```

Biên dịch/chạy:

```bash
javac RuntimeProbe.java
java RuntimeProbe
```

**Không đưa stdout cố định** cho PID, thread name, loader `toString()` hay CodeSource: chúng phụ thuộc OS, JDK, IDE, runner và đường làm việc. Khi cần so sánh dữ liệu thật, chạy probe trong **mỗi test/application/plugin boundary** và đối chiếu.

### Giải thích từng trường

- **PID:** có thuộc cùng JVM process không? Một process có thể có nhiều class loaders.
- **Thread:** các tác vụ khác thread có thể chia sẻ class/static state.
- **Class name:** chỉ định binary name; không đủ để kết luận class identity.
- **ClassLoader:** cho biết defining loader của `type`; với bootstrap thường được biểu diễn bằng `null`.
- **Module:** runtime module của class; named/unnamed/module layer liên quan access.
- **TCCL:** loader làm **ngữ cảnh khám phá** cho một số SPI/framework, không nhất thiết là defining loader của class.
- **CodeSource:** nếu có, cho biết location gắn với protection domain; có thể `null`, synthetic hoặc không có URL hữu ích. Không coi nó là bằng chứng bảo mật tuyệt đối.

Tốt hơn việc chỉ đọc `loader.toString()`: so sánh trực tiếp **reference equality** (`a.getClassLoader() == b.getClassLoader()`) trong cùng JVM và kiểm tra **`Class<?>` identity** khi có thể.

## 14. TCCL, context switching và plugin discovery

**Thread Context ClassLoader (TCCL)** là một trường trên `Thread` để framework ở loader cha có thể khám phá providers thuộc ngữ cảnh ứng dụng/plugin.

Ví dụ:

```java
// Trích đoạn:
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    ServiceLoader<MyService> services =
            ServiceLoader.load(MyService.class);
    services.findFirst().ifPresent(service -> service.start());
} finally {
    thread.setContextClassLoader(previous);
}
```

Đây là **trích đoạn**, `MyService`, `pluginLoader` và `start()` là API do ứng dụng cung cấp. `ServiceLoader.load(S.class)` dùng TCCL; **`Class.forName("p.Impl")` không tự dùng TCCL**.

### Vì sao TCCL dễ gây “rò rỉ cô lập”?

Nếu webapp/plugin A đặt TCCL của một worker thread thành `Loader-A` rồi không restore:
- Request tiếp theo thuộc B có thể tìm provider của A.
- Worker thread lâu sống có thể giữ **strong reference** tới Loader-A.
- Sau undeploy, class loader cũ có thể chưa đủ điều kiện GC/unloading.

Do đó phải dùng `try/finally` khi tự thay TCCL, và container phải quản lý thread pool/worker lifecycle đúng cách.

## 15. “Cùng package” vẫn có thể là hai runtime packages

Ở JVM, cùng tên package bằng chuỗi **không đủ** để có quyền package-private giữa hai class do loaders khác nhau định nghĩa. Hai class có thể khai báo:

```java
package example.impl;
```

nhưng một class thuộc `Loader-A`, class kia thuộc `Loader-B`. Chúng không tự trở thành cùng runtime package có quyền package-private access. Trong hệ named modules, runtime package identity còn liên quan module.

Điều này gây ra tình huống:
- Compile cùng source tree thì package-private hoạt động.
- Khi deploy vào container với class loaders tách biệt, runtime báo `IllegalAccessError` hoặc lỗi liên kết/truy cập tương ứng.
- Tên package và tên class trên stack trace vẫn giống, khiến khó tìm nguyên nhân.

**Giải pháp:** không thiết kế plugin boundary dựa trên package-private access xuyên loader; dùng public shared API hoặc đặt các class phải chung runtime package vào cùng defining loader/module theo cấu hình phù hợp.

## 16. ModuleLayer isolation khác ClassLoader isolation

JPMS (Java 9+) cung cấp:
- **Module** và `module-info.java`: `requires`, `exports`, `opens`, `uses`, `provides`.
- **ModuleLayer**: grouping của modules được resolve trong runtime configuration.
- **ClassLoader mapping**: một layer có thể dùng một hoặc nhiều loaders.

Không phải mọi module có loader riêng. Một loader có thể định nghĩa classes của nhiều modules. Và module readability/encapsulation **không phải thay cho process sandbox**.

```text
Boot layer
  ├── host.app
  └── shared.api
        │
        ▼
Child layer for plugins
  ├── plugin.one  ─┐
  └── plugin.two  ─┴─ một hoặc nhiều ClassLoaders
```

Module A có thể đọc B nhưng không được access package B chưa export. Ngược lại, có `Class<?>` của class từ một module khác cũng không tự cho phép reflection private nếu package không open.

### Dấu hiệu nhận diện

- `type.getModule().getName()`: tên module hoặc `null` nếu unnamed module.
- `type.getModule().getLayer()`: layer của named module khi có.
- `type.getClassLoader()`: defining loader.
- `callerModule.canRead(targetModule)`: readability.
- `targetModule.isExported(packageName, callerModule)` / `isOpen(...)`: quyền runtime package.

**Đừng kết luận một plugin “được sandbox” chỉ vì nó ở child layer.** Cơ chế Java module không cung cấp cách ly memory/process hay chặn tùy ý filesystem/network.

## 17. Process isolation: static state reset nhưng external state có thể còn

Một test runner chạy mỗi test class trong JVM process riêng có các lợi thế:
- ClassLoader graph bắt đầu mới; classes và static fields của process cũ không còn được chia sẻ.
- Các system properties, installed runtime hooks, cached singletons của Java process mới thường bắt đầu theo cấu hình JVM đó.
- JVM crash trong worker này thường không kéo theo heap của worker khác (dù build có thể báo lỗi).
- Có thể chọn JVM arguments khác, heap limit khác.

Nhưng:
- Hai tests vẫn có thể ghi **cùng database schema**.
- Hai processes có thể tranh **cùng TCP port**, file lock hoặc thư mục temp cố định.
- Cùng OS user/credentials có thể truy cập resources ngoài process.
- Một subprocess do test cũ tạo ra có thể còn sống nếu cleanup sai.
- Process mới tốn CPU/memory và startup latency.

Vì vậy, process isolation là **bức tường đối với Java heap và class identity của process**, không phải transaction rollback tự động cho external systems.

### OS container còn là tầng khác

Docker/Kubernetes container là cơ chế cô lập ở mức **OS/runtime deployment**, có thể bao gồm namespace/network/mount/cgroup restrictions. Một container có thể chứa một hoặc nhiều processes tùy thiết kế, nhưng thông lệ JVM service thường chạy một process chính.

Nếu hai JVM processes nằm trong cùng container, chúng vẫn là **hai processes**; nếu hai JVM chạy ở hai containers khác nhau, chúng còn có những biên OS khác. Tuy nhiên, cả hai containers vẫn có thể mount cùng volume hoặc nói chuyện với cùng database.

**Không đánh đồng** “application container” (Tomcat/servlet container) với “OS container” (Docker): từ “container” được dùng cho hai loại hệ thống rất khác nhau.

## 18. Hệ plugin: quyết định cái gì cần chia sẻ

Một plugin architecture bền vững thường chia class thành:

| Thành phần | Vị trí gợi ý | Lý do |
|---|---|---|
| Java platform API | Bootstrap/platform loaders | Cùng JVM platform type |
| Shared SPI/interface/DTO | Host/common parent loader hoặc shared module | Runtime identity ổn định ở biên |
| Plugin implementation | Plugin-specific loader/module | Cho phép phiên bản riêng |
| Third-party libraries riêng | Loader plugin khi cần isolation | Tránh version conflicts với plugin khác |
| Libraries thật sự dùng chung | Common loader có chính sách version rõ | Giảm duplication; dễ gây shared state |
| Credentials/config | Quản lý theo deployment boundary | Không coi ClassLoader là nơi cất secret |
| Lifecycle resources | Plugin owner/manager | Stop/close/unregister rõ ràng |

Không đưa mọi thứ lên parent: như vậy làm mất khả năng phiên bản riêng và có thể gây library conflicts. Cũng không đẩy mọi thứ xuống child: nếu child định nghĩa lại service interface chung, khả năng cast và discovery sẽ hỏng.

## 19. Vòng đời loader và nguy cơ rò rỉ khi redeploy

Khi webapp/plugin được redeploy, loader cũ có thể vẫn reachable qua TCCL, `ThreadLocal`, listener của servlet container, scheduled executor, service provider cache hoặc references tới `Class<?>`/implementation. Shutdown cần quiesce requests, unregister callbacks, stop workers, restore context trên đúng threads, close I/O và loader khi thích hợp, rồi bỏ strong references. Nếu loaded-class count/metaspace tăng, kiểm tra **retaining paths** bằng heap/thread diagnostics; `URLClassLoader.close()` và một lần GC không chứng minh class đã unload.

## 20. Những lỗi thường gặp theo ranh giới cô lập

| Triệu chứng | Giả thuyết có giá trị kiểm tra |
|---|---|
| Test chạy riêng pass nhưng cả suite fail | Static/shared mutable state, thứ tự tests, external resource pollution |
| Một webapp cast lỗi với class từ app khác | Cùng tên nhưng khác defining ClassLoaders |
| ServiceLoader không tìm thấy provider | TCCL/explicit loader sai, thiếu `META-INF/services` hoặc `provides` |
| ClassCastException dù tên lớp giống hệt | Defining loaders khác nhau; không so string name |
| IllegalAccessError khi tách plugin | Runtime package/loader/module access khác lúc compile |
| NoSuchMethodError khi container chứa nhiều bản lib | Parent/shared vs webapp dependency khác compile-time ABI |
| Đổi JAR rồi chạy vẫn thấy behavior cũ | Loader cũ đã định nghĩa class; chưa redeploy/restart đúng |
| Không xóa được JAR sau undeploy | Loader/JarFile/file handle khác chưa đóng |
| Redeploy nhiều lần metaspace tăng | Loader còn reachable qua thread/TCCL/cache/listeners |
| Gradle test static state tồn tại giữa classes | Nhiều test classes dùng lại một JVM worker |
| Test methods chạy song song gây race | Nhiều threads dùng chung object/static/external state |
| Tests chạy ở JVM khác vẫn tranh port | Process isolation không tách external resources |
| Reflection bị InaccessibleObjectException | JPMS package không được opens phù hợp |
| Class.forName trong host không thấy plugin | Dùng loader của caller thay vì plugin loader/TCCL |

**Đừng giải quyết mọi lỗi bằng cách đổi thành child-first.** Nếu vấn đề là external shared database, concurrency hoặc class loader leak, thay delegation không xử lý nguyên nhân.

## 21. Checklist nhận diện mô hình cô lập trong một dự án thực

Khi xem một server/test suite không rõ kiến trúc:

1. **Kiểm tra process boundary.** Các tác vụ có cùng PID không? Build tool có forked JVM workers không? Xem Gradle `forkEvery`/`maxParallelForks` hoặc Surefire `forkCount`/`reuseForks`.
2. **Kiểm tra thread boundary.** Test runner chạy parallel bằng threads hay processes? TCCL có được đặt riêng theo task không?
3. **Kiểm tra test instance lifecycle.** JUnit `PER_METHOD` hay `PER_CLASS`? Điều này chỉ quyết định test object lifecycle, không tự reset static.
4. **Kiểm tra loader graph.** In defining loader của service API, plugin implementation và dependency nghi vấn.
5. **Kiểm tra delegation order.** Parent-first hay child-first? Có whitelist cho platform/shared APIs không?
6. **Kiểm tra runtime type identity.** Trong cùng JVM, so `Class<?>` bằng `==`; tên giống không đủ.
7. **Kiểm tra JPMS graph.** Type ở module/layer nào? `requires`, `exports`, `opens` thế nào?
8. **Kiểm tra classpath/code source.** Tệp class đến từ `WEB-INF/lib`, common/lib, plugin jar hay test runtime classpath? Có shadowing không?
9. **Kiểm tra shared mutable state.** Static caches, singleton, ThreadLocal, global registries, filesystem, DB, ports.
10. **Kiểm tra lifecycle.** Sau test/undeploy, loader, threads, callbacks và resource handles có được dọn không?
11. **Tạo test nhỏ kiểm chứng giả thuyết.** Hai loaders độc lập + shared API; hai JVM processes; JUnit isolated instances; đổi mỗi một biến mỗi lần.
12. **Đọc tài liệu runner/container đúng phiên bản.** Cấu hình defaults có thể thay đổi; đừng lấy giả định từ một framework khác.

## 22. Mini decision tree: tình huống này bị cô lập đến mức nào?

```text
Có hai execution contexts X và Y
            │
            ▼
Có cùng PID?
   ├─ Không → JVM process state tách nhau
   │           └─ vẫn kiểm tra shared files/DB/network
   └─ Có
        │
        ▼
X và Y dùng cùng runtime Class<?> cho type nghi vấn?
   ├─ Có → cùng static state của type đó
   │        └─ test instances/threads vẫn có thể riêng
   └─ Không
        │
        ▼
Khác defining ClassLoaders?
   ├─ Có → class namespace/static state của type đó tách
   │        └─ shared API/resources/process vẫn có thể chung
   └─ Cần kiểm tra Module/Layer hoặc class thật đã resolve
        │
        ▼
Kiểm tra TCCL, parent delegation và code source
            │
            ▼
Nếu vướng access:
   kiểm tra module readability, exports, opens
            │
            ▼
Nếu vướng state:
   kiểm tra static, ThreadLocal, cache, external resources
```

Sơ đồ là **quy trình chẩn đoán**, không phải thuật toán Java chạy ngầm. Ví dụ trong nhiều JVM processes, không thể so sánh hai `Class<?>` objects trực tiếp vì chúng ở hai heaps khác nhau.

## 23. Câu hỏi tự kiểm tra

1. **Hai webapps Tomcat cùng JVM có thể có hai bản runtime class cùng tên không?** Có, nếu hai webapp loaders riêng định nghĩa chúng.
2. **Parent-first có luôn là thứ tự mặc định của webapp loader Tomcat không?** Không; webapp loader của Tomcat có local-first cho nhiều app classes và ngoại lệ quan trọng.
3. **JVM phân biệt hai class cùng binary name dựa trên gì?** Binary name và defining loader.
4. **Cùng loader object được gọi loadClass có bảo đảm nó là defining loader không?** Không, parent có thể định nghĩa class.
5. **Hai plugin instances có static state riêng chỉ vì là hai objects?** Không; phải xem static field thuộc runtime class nào.
6. **Hai defining loaders riêng có thể giữ hai static fields riêng của cùng tên class không?** Có.
7. **Làm thế nào host nhận plugin object từ hai loaders khác nhau?** Qua shared interface/API do loader chung định nghĩa, hoặc boundary dữ liệu thích hợp.
8. **JUnit PER_METHOD có reset static fields không?** Không.
9. **JUnit chạy tests song song bằng threads có tách JVM heap không?** Không.
10. **Gradle maxParallelForks chủ yếu điều khiển gì?** Số forked test JVM worker processes có thể chạy song song.
11. **Gradle forkEvery=1 gần với cô lập theo test method hay test class?** Test class/definition, không mặc nhiên per-method.
12. **Maven Surefire forkCount=0 đồng nghĩa gì về process?** Không tạo forked test JVM theo cấu hình đó; cần xem loader strategy của phiên bản plugin.
13. **Hai JVM riêng có chia sẻ static fields không?** Không, nhưng có thể dùng chung DB/files/ports.
14. **TCCL có phải defining loader của mọi class do thread chạy không?** Không; nó chỉ là loader ngữ cảnh cho APIs/frameworks dùng nó.
15. **Đóng URLClassLoader có bảo đảm class unload ngay không?** Không.
16. **OS container và servlet container là cùng khái niệm không?** Không.
17. **Một ModuleLayer tự tạo có phải sandbox chống file/network không?** Không.
18. **Tại sao hai class cùng tên không cast được dù cùng bytecode?** Defining loaders khác nhau làm runtime type identity khác nhau.
19. **Nếu test fail chỉ khi chạy cả suite, nên kiểm tra gì trước?** Shared static/external state, test order, runner process/thread reuse, class loader boundaries.
20. **Dữ liệu nào hỗ trợ chẩn đoán hiệu quả nhất?** PID, thread, Class object/defining loader, module/layer, TCCL, class source và runner configuration.

## 24. Tài liệu chuẩn và nguồn đọc tiếp

- [Java SE 17 — ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `findLoadedClass` và defining loaders.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): loader dùng URL, close và tài nguyên JAR.
- [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity, runtime packages và loading.
- [Java SE 17 — ModuleLayer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): module layers, module-to-loader mapping.
- [Apache Tomcat — Class Loader How-To](https://tomcat.apache.org/tomcat-11.0-doc/class-loader-howto.html): Common/Webapp class loaders, WEB-INF và delegation exceptions.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): forked JVM, `maxParallelForks`, `forkEvery` và test workers.
- [Maven Surefire — Class Loading and Forking](https://maven.apache.org/surefire/maven-surefire-plugin/examples/class-loading.html): chọn class loader strategy và fork modes.
- [JUnit 5 User Guide — Test Instance Lifecycle](https://docs.junit.org/5.12.0/user-guide/#writing-tests-test-instance-lifecycle): `PER_METHOD`/`PER_CLASS` và test object state.

**Kết luận:** Nhận diện mô hình cô lập trong container và test runner là việc xác định **ranh giới cụ thể của class definitions, static state, module access, threads, processes và external resources**. Với Java plugins, đối chiếu **defining ClassLoader** và shared API trước; với tests, phân biệt **test instance lifecycle** khỏi **forked JVM process**. Không xem bất kỳ cơ chế đơn lẻ nào là cô lập tuyệt đối hay giải pháp bảo mật thay thế.
