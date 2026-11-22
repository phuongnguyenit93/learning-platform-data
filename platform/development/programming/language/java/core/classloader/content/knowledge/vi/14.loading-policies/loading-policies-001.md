# So sánh parent-first và child-first trong Java ClassLoader

**Parent-first** và **child-first** là hai **chính sách ưu tiên tìm lớp** khi một class loader cần xử lý tên class chưa được nạp. Chúng quyết định **hỏi parent trước hay thử nguồn class của chính loader trước**, từ đó ảnh hưởng tới phiên bản thư viện được sử dụng, runtime type identity, khả năng tích hợp plugin và cách xử lý xung đột dependency.

Trong Java, `ClassLoader.loadClass` mặc định triển khai **parent-first delegation**. **Child-first** là chiến lược tùy biến, thường gặp trong hệ plugin, application server hoặc môi trường cô lập phiên bản thư viện. Nó **không phải một cờ có sẵn** trong constructor `URLClassLoader`. Muốn dùng child-first cần một loader triển khai chính sách riêng, đồng thời phải giữ những ngoại lệ cần thiết cho các lớp nền tảng và API dùng chung.

Bài học thuộc nhóm **Chính sách nạp** của **Java core – classloader**. Nội dung tập trung vào thứ tự lookup, ví dụ Java 17+ có thể chạy, ảnh hưởng tới **defining loader**, SPI/DTO dùng chung, resources, các lỗi thường gặp và cách chọn chính sách có căn cứ.

## 1. “First” là ưu tiên lookup, không phải thứ tự kế thừa Java

Giả sử host và plugin cùng có một class tên `lib.Version`:

```text
HOST / parent loader                 PLUGIN / child loader
lib.Version  ->  "host"              lib.Version  ->  "plugin"
                  ▲                                  │
                  └──── parent của plugin loader ────┘
```

Khi code yêu cầu `pluginLoader.loadClass("lib.Version")`:

- **Parent-first:** thử parent trước. Nếu parent tìm được `lib.Version`, child trả đúng class đó; bản plugin có thể **không bao giờ được định nghĩa**.
- **Child-first:** thử nguồn local của plugin trước. Nếu child tự tìm/định nghĩa được `lib.Version`, bản plugin được chọn; nếu không có local class, tùy chính sách mới fallback sang parent.

Đây là **hai chính sách lựa chọn lớp**. Chúng **không** thay đổi:

- Java superclass của `PluginLoader` (từ khóa `extends`);
- parent object trả về bởi `pluginLoader.getParent()`;
- những class đã được định nghĩa trước đó;
- classpath dùng lúc **biên dịch**;
- ngữ nghĩa tạo object hay gọi constructor của class đã nạp.

**Điểm cốt lõi:** cùng một binary name có thể dẫn tới **hai runtime types khác nhau** nếu hai class loaders riêng biệt tự định nghĩa nó. JVM định danh kiểu bởi **(binary name, defining loader)**, không chỉ bằng chuỗi tên class.

## 2. Luồng mặc định: parent-first

Java 17 `ClassLoader.loadClass(String, boolean)` có thuật toán khái niệm:

```text
loadClass(name)
      │
      ▼
findLoadedClass(name)
      ├── đã nạp → trả Class<?> được ghi nhận
      │
      └── chưa
            │
            ▼
      hỏi parent.loadClass(name)
            │
            ├── thành công → trả class do parent/ancestor tìm được
            │
            └── ClassNotFoundException
                       │
                       ▼
                 findClass(name)
                       │
                       ├── thành công → class do child định nghĩa
                       └── thất bại → ClassNotFoundException
```

Ba điều cần nhớ:

1. **Kiểm tra đã nạp trước:** JVM không tạo thêm một định nghĩa class khác cùng binary name trong cùng defining loader chỉ vì `loadClass` được gọi lại.
2. **Parent có cơ hội trước:** nếu `parent.loadClass` thành công, child không cần dùng `findClass` cho tên ấy.
3. **Child là phương án sau:** chỉ khi parent không tìm thấy theo logic mặc định, child mới thử nguồn class của mình.

`ClassLoader.loadClass(String)` thông thường gọi overload có `resolve=false` và không tự yêu cầu static initialization. Loading, linking, initialization là các khái niệm khác với chính sách ưu tiên parent/child.

Lưu ý sơ đồ thể hiện **hợp đồng `ClassLoader` mặc định**. Built-in loaders trong JDK 9+ có logic module-aware, custom loaders có thể override `loadClass`. Không mô tả sơ đồ tuyến tính này như quy tắc tuyệt đối của mọi loader hiện đại.

## 3. Luồng child-first: ưu tiên nguồn riêng, nhưng phải có giới hạn

Một loader child-first phổ biến triển khai ý tưởng:

```text
loadClass(name)
      │
      ▼
findLoadedClass(name)
      ├── đã có → trả Class<?>
      └── chưa
           │
           ▼
     Đây có phải lớp nền tảng / API bắt buộc chia sẻ?
           ├── có → dùng parent-first cho namespace bảo vệ
           │
           └── không
                │
                ▼
          thử child.findClass(name)
                ├── tìm thấy → trả class child định nghĩa
                └── ClassNotFoundException
                          │
                          ▼
                    thử parent.loadClass(name)
```

**Quan trọng:** chỉ riêng ý tưởng “child trước” chưa đủ để có implementation đúng. Một custom loader thực tế còn phải:

- Dùng `findLoadedClass` để tránh định nghĩa trùng class.
- Đồng bộ lookup đúng cách, ví dụ `synchronized (getClassLoadingLock(name))`.
- Không nuốt mọi `LinkageError` hoặc `SecurityException` để fallback tùy tiện.
- Giữ một **shared API namespace** luôn resolve về đúng runtime type của host.
- Không cố tự định nghĩa những lớp thuộc namespace bảo vệ như `java.*`.
- Cân nhắc `registerAsParallelCapable()` nếu định triển khai concurrent loading phức tạp; không mặc nhiên loader nào cũng parallel-capable.
- Duy trì tính nhất quán của package sealing, module access và resource/service discovery.

**Không phải mọi package nên child-first.** Hệ plugin thông thường cần **parent-first cho contract**, **child-first có chọn lọc cho thư viện private**.

## 4. Bảng so sánh quyết định

| Tiêu chí | Parent-first | Child-first |
| --- | --- | --- |
| Nguồn được thử đầu tiên | Parent/ancestor | Nguồn riêng của child (trừ namespace bảo vệ) |
| Triển khai trong `ClassLoader` mặc định | Có | Không, thường cần override |
| Với class trùng tên ở host và plugin | Bản host thường thắng | Bản plugin có thể thắng |
| Chia sẻ host-defined SPI/DTO | Thuận tiện nếu API ở parent | Phải bảo vệ API package qua delegation |
| Cô lập phiên bản dependency private | Khó nếu parent đã có bản cùng tên | Thuận lợi hơn khi child chứa bản phù hợp |
| Nguy cơ | Host library shadow plugin library; version skew | Tạo bản sao API gây `ClassCastException`, `LinkageError` |
| JDK classes | Thường ủy quyền từ child qua parent | Vẫn cần bảo đảm lớp nền tảng có đường nạp hợp lệ |
| Sự phức tạp | Thấp hơn, hợp đồng quen thuộc | Cao hơn: đồng bộ, fallback, constraints, module/resource |
| Có thay parent object? | Không bắt buộc | Không bắt buộc |
| Có bảo đảm sandbox an toàn? | Không | Không |

Không có lựa chọn “tốt nhất tuyệt đối”. **Parent-first** phù hợp nếu hệ thống có dependency graph thống nhất và muốn dùng chung nhiều API; **child-first chọn lọc** hữu ích nếu các plugin phải dùng những versions thư viện khác nhau nhưng vẫn cần một contract chung.

## 5. Chuẩn bị thực hành A — cùng tên class ở host và plugin

Thực hành này dùng `URLClassLoader` để tạo **parent-first loader** và một **child-first loader tùy biến**. Chúng cùng nhìn **một thư mục plugin**, nhưng khác thứ tự ưu tiên.

Cây thư mục:

```text
policy-lab/
├── src/
│   ├── hostlib/
│   │   └── lib/Version.java
│   ├── pluginlib/
│   │   └── lib/Version.java
│   └── app/
│       └── demo/PolicyDemo.java
├── hostlib-out/      (sinh bởi javac)
├── pluginlib-out/    (sinh bởi javac)
└── app-out/          (sinh bởi javac)
```

**`src/hostlib/lib/Version.java`:**

```java
package lib;

public final class Version {
    public static String origin() {
        return "host";
    }
}
```

**`src/pluginlib/lib/Version.java`:**

```java
package lib;

public final class Version {
    public static String origin() {
        return "plugin";
    }
}
```

Hai source file khai báo **cùng binary name `lib.Version`**, nhưng tạo ra **hai thư mục binary khác nhau**. Không compile cả hai cùng một output folder; mục đích là quan sát việc **chọn class runtime** chứ không phải khai báo hai lớp trùng trong một Java package của cùng build.

### Child-first implementation có kiểm soát

Tệp **`src/app/demo/PolicyDemo.java`**:

```java
package demo;

import lib.Version;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PolicyDemo {
    static final class ChildFirstLoader extends URLClassLoader {
        ChildFirstLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);

                if (found == null) {
                    if (name.startsWith("java.")) {
                        // Namespace nền tảng: để parent/ancestor xử lý.
                        found = super.loadClass(name, false);
                    } else {
                        try {
                            // Ưu tiên URL của chính child.
                            found = findClass(name);
                        } catch (ClassNotFoundException notLocal) {
                            // Chỉ fallback khi thực sự không có local class.
                            found = super.loadClass(name, false);
                        }
                    }
                }

                if (resolve) {
                    resolveClass(found);
                }
                return found;
            }
        }
    }

    private static String origin(ClassLoader loader) throws Exception {
        Class<?> type = loader.loadClass("lib.Version");
        return (String) type.getMethod("origin").invoke(null);
    }

    public static void main(String[] args) throws Exception {
        URL pluginClasses = Path.of("pluginlib-out")
                .toAbsolutePath().toUri().toURL();
        URL[] urls = { pluginClasses };
        ClassLoader host = PolicyDemo.class.getClassLoader();

        System.out.println("host=" + Version.origin());

        try (URLClassLoader parentFirst =
                     new URLClassLoader(urls, host);
             ChildFirstLoader childFirst =
                     new ChildFirstLoader(urls, host)) {

            System.out.println("parent-first=" + origin(parentFirst));
            System.out.println("child-first=" + origin(childFirst));

            Class<?> fromParent = parentFirst.loadClass("lib.Version");
            Class<?> fromChild = childFirst.loadClass("lib.Version");

            System.out.println("parent shares host=" +
                    (fromParent == Version.class));
            System.out.println("child differs from host=" +
                    (fromChild != Version.class));
            System.out.println("child defined locally=" +
                    (fromChild.getClassLoader() == childFirst));
        }
    }
}
```

**Biên dịch** trong `policy-lab` bằng JDK 17+:

```sh
javac --release 17 -d hostlib-out src/hostlib/lib/Version.java
javac --release 17 -d pluginlib-out src/pluginlib/lib/Version.java
javac --release 17 -cp hostlib-out -d app-out src/app/demo/PolicyDemo.java
```

Chạy **Windows PowerShell/CMD**, classpath phân tách bằng dấu `;`:

```powershell
java -cp "app-out;hostlib-out" demo.PolicyDemo
```

Chạy **Linux/macOS**, phân tách bằng dấu `:`:

```sh
java -cp "app-out:hostlib-out" demo.PolicyDemo
```

**Stdout của lệnh `java` với layout này:**

```text
host=host
parent-first=host
child-first=plugin
parent shares host=true
child differs from host=true
child defined locally=true
```

### Giải thích từng dòng

- **`host=host`:** `demo.PolicyDemo` sử dụng `lib.Version` từ `hostlib-out` trong application classpath.
- **`parent-first=host`:** `URLClassLoader` mặc định hỏi host loader trước. Vì parent đã có `lib.Version`, nó trả bản `host` và không tìm bản plugin.
- **`child-first=plugin`:** subclass `ChildFirstLoader` thử `findClass("lib.Version")` trước. Nó đọc `pluginlib-out/lib/Version.class` và tự định nghĩa runtime type riêng.
- **`parent shares host=true`:** cùng `Class<?>` với `Version.class` của host; vì vậy hai lời gọi dùng chung class identity.
- **`child differs from host=true`:** tên `lib.Version` giống, nhưng defining loaders khác nhau.
- **`child defined locally=true`:** `getClassLoader()` của `Class<?>` trả đúng `childFirst`, minh họa kết quả lookup là bản local.

**Giới hạn ví dụ:** đây là một loader đơn giản để giải thích chính sách. Nó dùng parent fallback cho `java.*`, chưa xây dựng đầy đủ package/module policy cho framework production, cũng chưa xử lý mọi loại tài nguyên hoặc phiên bản plugin. Không copy nguyên xi làm class loader cho mã bên thứ ba không tin cậy.

## 6. Vì sao ví dụ A không cần đổi parent?

Trong ví dụ, **cả parent-first và child-first đều có cùng parent object**:

```java
ClassLoader host = PolicyDemo.class.getClassLoader();
URLClassLoader parentFirst = new URLClassLoader(urls, host);
ChildFirstLoader childFirst = new ChildFirstLoader(urls, host);
```

Đây là **snippet minh họa lại** có thể nằm trong method nếu các biến và imports có sẵn; khi dùng thực tế, phải đóng hai loaders đúng lúc.

Sự khác nhau ở `loadClass`:

- Với parent-first, kế hoạch mặc định là hỏi `host.loadClass`, rồi mới gọi `findClass` của child.
- Với child-first, `findClass` của child được gọi sớm cho những tên không thuộc namespace bảo vệ. Chỉ khi không tìm được local class mới hỏi parent.

**Parent là quan hệ giữa loader objects**, không phải cú pháp `extends`. Dùng cùng object parent **không khiến hai policies cho cùng kết quả**, vì mỗi loader có thể chọn thứ tự gọi parent khác nhau.

Ngược lại, chỉ đổi parent trong constructor `URLClassLoader` thông thường cũng có thể thay đổi class được tìm, nhưng **không có nghĩa đã triển khai child-first**. Hãy phân biệt **chọn nguồn có thể thấy** với **thứ tự ưu tiên giữa các nguồn đó**.

## 7. Cùng tên không phải cùng kiểu: runtime identity và casting

Một type trong JVM được xác định bằng cặp:

```text
(binary name, defining loader)
```

Trong ví dụ A:

```text
"lib.Version" + host loader       → host Class
"lib.Version" + childFirst loader → plugin Class
```

Do đó:

```java
fromParent.getName().equals(fromChild.getName()); // true
fromParent == fromChild;                          // false
```

Đây là snippet minh họa khi hai biến đã được khai báo từ ví dụ A. Nếu `lib.Version` là class nghiệp vụ dùng để truyền object giữa host và plugin, bản child-first **có thể không cast được** sang bản host, dù method signatures nhìn giống nhau.

Nếu chỉ dùng internal library `lib.Version` để tính toán và trả `String`, hai definitions riêng có thể không gây vấn đề. Nhưng nếu bản library này lộ ra trong public API (parameter/return type/exception/annotation), vấn đề identity trở thành lỗi boundary.

**Không dùng tên class làm tiêu chuẩn tương đương runtime.** Muốn kiểm tra một plugin implements đúng interface của host, dùng `HostApi.class.isAssignableFrom(pluginClass)` và so sánh `Class<?>` từ hai bên khi cần.

## 8. Ranh giới thiết kế: API phải chia sẻ, dependency private có thể cô lập

Giả sử host có interface:

```java
package api;

public interface Greeter {
    String greet(String name);
}
```

Nếu plugin implements **đúng runtime `api.Greeter`** của host, host có thể cast instance sang `Greeter`. Nếu child-first loader **tự định nghĩa một bản sao `api.Greeter`**, kết quả có thể là:

```text
HostLoader defines api.Greeter    → interface A
PluginLoader defines api.Greeter  → interface B

PluginImpl implements B
Host cần interface A

A.getName() == B.getName()       → cùng binary name
A == B                           → false
A.isAssignableFrom(PluginImpl)   → false
```

Mã source interface **giống từng ký tự** cũng không gộp hai types thành một. Đây là lý do **child-first thuần túy** thường không phù hợp cho toàn bộ package.

Mô hình thực tế hay dùng là **delegation chọn lọc**:

| Namespace | Chính sách đáng cân nhắc | Lý do |
| --- | --- | --- |
| `java.*` và các platform APIs phù hợp | Parent/platform delegation | Không cố tự định nghĩa lớp nền tảng |
| `api.*` (host SPI/DTO/callback) | Parent-first bắt buộc cho API chung | Bảo vệ type identity giữa host và plugin |
| `impl.*` | Child-first | Plugin implementation có thể nằm trong JAR riêng |
| `vendor.*` private | Child-first nếu host cũng có phiên bản khác | Cho phép plugin tự quản dependency version |
| Unknown name | Fallback theo chính sách đã định | Cần không nuốt lỗi liên kết và không tạo vòng lặp |

Namespace `api.*` là **tên ví dụ**, không phải package chuẩn của JDK. Trong production, hãy liệt kê chính xác các contract packages và types lộ qua method descriptors, không chỉ dựa vào một prefix đơn giản nếu API phân bố nhiều package.

## 9. Thực hành B — child-first có ngoại lệ để chia sẻ API của host

Ví dụ sau cố ý đóng gói **hai bản bytes của cùng `api.Greeter`** ở hai nguồn: `api-out` của host và `plugin-out` của plugin. Điều này giúp thấy vì sao phải có quy tắc **parent-first riêng cho `api.*`**, dù implementation dùng child-first.

Cây tệp:

```text
shared-api-lab/
└── src/
    ├── api/api/Greeter.java
    ├── plugin/impl/PluginGreeter.java
    └── host/demo/SelectiveDemo.java
```

**`src/api/api/Greeter.java`:**

```java
package api;

public interface Greeter {
    String greet(String name);
}
```

**`src/plugin/impl/PluginGreeter.java`:**

```java
package impl;

import api.Greeter;

public final class PluginGreeter implements Greeter {
    public PluginGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

**`src/host/demo/SelectiveDemo.java`:**

```java
package demo;

import api.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class SelectiveDemo {
    static final class SelectiveLoader extends URLClassLoader {
        private final boolean protectSharedApi;

        SelectiveLoader(URL[] urls, ClassLoader parent,
                        boolean protectSharedApi) {
            super(urls, parent);
            this.protectSharedApi = protectSharedApi;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> clazz = findLoadedClass(name);

                if (clazz == null) {
                    boolean delegate = name.startsWith("java.")
                            || (protectSharedApi && name.startsWith("api."));

                    if (delegate) {
                        clazz = super.loadClass(name, false);
                    } else {
                        try {
                            clazz = findClass(name);
                        } catch (ClassNotFoundException missingLocal) {
                            clazz = super.loadClass(name, false);
                        }
                    }
                }

                if (resolve) {
                    resolveClass(clazz);
                }
                return clazz;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        URL pluginUrl = Path.of("plugin-out")
                .toAbsolutePath().toUri().toURL();
        URL[] urls = { pluginUrl };
        ClassLoader sharedParent = Greeter.class.getClassLoader();

        try (SelectiveLoader protectedLoader =
                    new SelectiveLoader(urls, sharedParent, true);
             SelectiveLoader naiveLoader =
                    new SelectiveLoader(urls, sharedParent, false)) {

            Class<?> good =
                    protectedLoader.loadClass("impl.PluginGreeter");
            Class<?> goodApi = good.getInterfaces()[0];

            System.out.println("protected API shared=" +
                    (goodApi == Greeter.class));
            System.out.println("protected implementation local=" +
                    (good.getClassLoader() == protectedLoader));
            System.out.println("protected assignable=" +
                    Greeter.class.isAssignableFrom(good));

            Greeter service = (Greeter)
                    good.getDeclaredConstructor().newInstance();
            System.out.println("protected result=" +
                    service.greet("Java"));

            Class<?> bad = naiveLoader.loadClass("impl.PluginGreeter");
            Class<?> badApi = bad.getInterfaces()[0];

            System.out.println("naive same name=" +
                    badApi.getName().equals(Greeter.class.getName()));
            System.out.println("naive same Class=" +
                    (badApi == Greeter.class));
            System.out.println("naive assignable=" +
                    Greeter.class.isAssignableFrom(bad));
        }
    }
}
```

**Biên dịch** từ thư mục `shared-api-lab`:

```sh
javac --release 17 -d api-out src/api/api/Greeter.java
javac --release 17 -cp api-out -d plugin-out src/plugin/impl/PluginGreeter.java
javac --release 17 -d plugin-out src/api/api/Greeter.java
javac --release 17 -cp api-out -d host-out src/host/demo/SelectiveDemo.java
```

Lệnh thứ ba cố ý sao chép **binary API** vào output của plugin bằng cách compile cùng file source sang `plugin-out`. Trong môi trường production, **không nên đóng gói shared API duplicate** nếu tránh được; thao tác này chỉ nhằm mô phỏng lỗi một cách có kiểm soát.

Chạy **Windows**:

```powershell
java -cp "host-out;api-out" demo.SelectiveDemo
```

Chạy **Linux/macOS**:

```sh
java -cp "host-out:api-out" demo.SelectiveDemo
```

**Stdout của lệnh `java`:**

```text
protected API shared=true
protected implementation local=true
protected assignable=true
protected result=Hello, Java
naive same name=true
naive same Class=false
naive assignable=false
```

### Lý giải đường đi của hai loaders

**Loader có bảo vệ API:**

1. `impl.PluginGreeter` không thuộc namespace bảo vệ; child ưu tiên `findClass` và tự define implementation.
2. Khi JVM cần `api.Greeter` cho mệnh đề `implements`, `SelectiveLoader` phát hiện prefix `api.` và gọi `super.loadClass` theo parent-first.
3. Host parent nhìn thấy `api.Greeter` từ `api-out`, nên trả **đúng runtime interface** của host, dù trong `plugin-out` có bản sao.
4. `Greeter.class.isAssignableFrom(good)` đúng; ép kiểu và gọi method thành công.

**Loader ngây thơ không bảo vệ API:**

1. Cả `impl.PluginGreeter` và `api.Greeter` được child tìm trong `plugin-out`.
2. `api.Greeter` của child có cùng binary name với bản host nhưng **khác defining loader**.
3. Plugin class implements **bản interface child**, không phải interface host.
4. `Greeter.class.isAssignableFrom(bad)` trả `false`. Nếu thực hiện cast `(Greeter) bad.getDeclaredConstructor().newInstance()`, chương trình có thể ném `ClassCastException`.

**Hạn chế thiết kế trong bài:** kiểm tra prefix `api.` chỉ là bài tập. Một hệ thống sản xuất phải xác định **chính xác** những packages cần chia sẻ và loader nào sở hữu chúng, xét additional platform namespaces, JPMS, package sealing, class-loading concurrency và resource lookup. Việc gọi `super.loadClass` cho `api.*` sẽ vẫn fallback về local nếu parent **không có API**; do đó điều kiện tiên quyết là **shared parent thực sự định nghĩa/nhìn thấy đúng contract**.

## 10. Vì sao `java.*` cần ngoại lệ đặc biệt?

Java runtime có những namespace và module thuộc nền tảng mà custom loader không được tùy tiện tự định nghĩa. Trong loader child-first:

```java
if (name.startsWith("java.")) {
    return super.loadClass(name, false);
}
```

Đây là **snippet minh họa logic**, không phải override hoàn chỉnh (nó chưa có đồng bộ, loaded-cache hay resolve handling). Nó thể hiện ý định không tự tìm local `java.*` trước.

Lưu ý:

- Kiểm tra `java.` **không thay thế** mọi quy tắc module/JDK. Các platform APIs có thể nằm trong namespaces khác; implementation production nên có **policy đầy đủ** và hiểu JPMS.
- `ClassLoader.defineClass` có những kiểm tra riêng cấm định nghĩa tên class bắt đầu bằng `java.` trong loader ứng dụng thông thường.
- Chọn parent là `ClassLoader.getPlatformClassLoader()` có thể giúp child nhìn thấy toàn bộ **platform classes**, trong khi parent `null` chỉ dựa vào bootstrap mechanism, không bảo đảm mọi Java SE/JDK class đều ở bootstrap trên Java 9+.
- Không nhầm câu “tránh define `java.*`” với câu “mọi `java.*` do platform loader trực tiếp define”: nhiều class cốt lõi do bootstrap define, platform vẫn nhìn thấy qua delegation.

Một child-first loader an toàn về **đúng đắn của nạp lớp** vẫn **không** biến plugin code thành sandbox bảo mật. Class loader giải quyết namespace/visibility; code không tin cậy cần boundary bảo mật độc lập.

## 11. Vì sao không được bắt mọi lỗi để fallback parent?

Một mẫu sai:

```java
try {
    return findClass(name);
} catch (Throwable ignored) {
    return getParent().loadClass(name);
}
```

Đây là **mẫu sai**, không có đủ context để chạy độc lập. `Throwable` bao gồm nhiều lỗi không có nghĩa là “không tìm thấy class ở child”:

- `LinkageError` có thể biểu thị bytecode/API không tương thích, vi phạm loader constraint hoặc lỗi định nghĩa class.
- `ExceptionInInitializerError`/`NoClassDefFoundError` có thể cho thấy initialization trước đó hỏng hoặc dependency thiếu.
- `SecurityException` có thể phản ánh vi phạm quy tắc namespace/permissions.
- `OutOfMemoryError` không phải một tín hiệu lookup để âm thầm chuyển nguồn.
- `ClassFormatError` và `UnsupportedClassVersionError` cho thấy class bytes không phù hợp, không nên bị che bằng một bản class ngẫu nhiên của parent.

Fallback trong ví dụ chỉ diễn ra khi `findClass` ném **`ClassNotFoundException`**. Đây là tín hiệu “local không có định nghĩa class với tên này” trong API loader; khi đó thử parent là logic hợp lý. Mọi lỗi khác cần xử lý theo contract, log có ngữ cảnh và **không tráo sang version khác mà không được phép**.

Thậm chí `ClassNotFoundException` có thể phát sinh do custom loader logic nội bộ; hệ thống production cần phân biệt missing local class, missing dependency, access/JPMS failure và các nguyên nhân khác khi debug.

## 12. Đồng bộ, `findLoadedClass` và quy tắc chỉ define một lần

Khi nhiều threads cùng yêu cầu class `lib.Version`, một custom child-first loader không được để cả hai tự `defineClass` cùng binary name trong một loader instance. JVM có thể báo `LinkageError: attempted duplicate class definition` hoặc các lỗi liên quan.

Phần quan trọng của override ở hai ví dụ:

```java
synchronized (getClassLoadingLock(name)) {
    Class<?> existing = findLoadedClass(name);
    if (existing != null) {
        return existing;
    }

    // Thử local hoặc parent theo policy.
}
```

Đây là **snippet minh họa**, chưa có logic tìm/lưu kết quả đầy đủ. Điểm chính:

- `getClassLoadingLock(name)` cung cấp lock mà `ClassLoader` dùng cho yêu cầu nạp tên class. Với loader không được đăng ký parallel-capable, lock có thể là chính loader object; parallel-capable loaders có thể có lock theo class name.
- `findLoadedClass(name)` tra cứu class đã được ghi nhận do loader đó khởi xướng nạp. Nó không chỉ cho biết class tự child define; lớp từ parent cũng có thể được ghi nhận là đã load qua loader.
- Phải kiểm tra loaded class **trước** mỗi đường định nghĩa local.
- `resolveClass(clazz)` chỉ thực hiện khi `resolve` được yêu cầu, sau khi chọn được `Class<?>` thích hợp.
- Không dùng khóa toàn cục tùy tiện nếu cần performance, nhưng cũng không bỏ đồng bộ chỉ vì test đơn luồng chạy đúng.

### Parallel-capable loader

`ClassLoader.registerAsParallelCapable()` là API `protected static`. Khi tạo subclass có nhu cầu concurrency và muốn dùng locks theo từng binary name, cần đăng ký đúng thời điểm trong static initializer của subclass, hiểu quy tắc về superclass và registration. Không tự động thêm nó vào mọi snippet vì sẽ làm ví dụ so sánh chính sách khó đọc.

Một override sai trong loader phức tạp còn có nguy cơ **deadlock** nếu loaders có quan hệ delegation vòng tròn hoặc đồng bộ không nhất quán. Parent chain của `ClassLoader` chuẩn tránh một số dạng vòng lặp nhờ cách khởi tạo, nhưng custom graph/delegation ngoài parent có thể tạo thêm phụ thuộc giữa loaders. Thiết kế production phải kiểm tra concurrency và cycle detection.

## 13. Method linking và binary compatibility sau khi chọn class

Lookup ưu tiên chỉ quyết định **runtime class nào được dùng**. Sau đó JVM còn phải liên kết những method/field references trong bytecode:

```text
Plugin compile-time:
    lib.Parser.parse(String):Result  (v2)

Runtime parent-first:
    lib.Parser v1 chỉ có parse(byte[]):Result

Kết quả:
    runtime class được tìm nhưng method descriptor không tồn tại
    → có thể ném NoSuchMethodError tại điểm sử dụng
```

Vấn đề này không nhất thiết xuất hiện ngay khi `pluginLoader.loadClass("impl.Plugin")` trả về `Class<?>`; JVM có thể trì hoãn resolution đến lúc instruction cần method. Vì vậy việc “đã load thành công” **không bảo đảm** phiên bản dependency tương thích.

Các lỗi thường gặp:

| Lỗi | Điều có thể đã xảy ra |
| --- | --- |
| `ClassNotFoundException` | Loader được hỏi không tìm được class theo tên |
| `NoClassDefFoundError` | Dependency không được định nghĩa/sử dụng khi JVM cần hoặc class đã từng initialization lỗi |
| `NoSuchMethodError` | Runtime method reference không có method khớp descriptor |
| `NoSuchFieldError` | Runtime field reference không có field khớp name/descriptor |
| `IncompatibleClassChangeError` | Chênh lệch class/interface, static/instance hoặc hợp đồng liên kết khác |
| `IllegalAccessError` | Runtime access/module constraints không cho phép liên kết |
| `ClassCastException` | Runtime type không assignable với type host mong muốn |
| `LinkageError` loading constraint | Hai loader definitions không đáp ứng những ràng buộc type safety |
| `ExceptionInInitializerError` | Static initializer thất bại, không chỉ đơn thuần là chọn loader sai |

Để sửa, cần tìm **defining loader và artifact của đúng class runtime**, so bytecode descriptor và dependency graph. Không đổi child-first để che mọi `LinkageError` nếu chưa hiểu nguyên nhân.

## 14. Resources có nhất thiết child-first cùng class không?

**Không.** Một custom loader chỉ override `loadClass` để child-first vẫn có thể **giữ `getResource`/`getResources` parent-first mặc định**.

Ví dụ:

```text
Host classpath:
    config/theme.txt = host-theme

Plugin URL:
    config/theme.txt = plugin-theme
```

Dù `ChildFirstLoader` của ví dụ A định nghĩa `lib.Version` từ child URL, `child.getResource("config/theme.txt")` có thể trả **bản host** do resource lookup hỏi parent trước. Nếu plugin cần tài nguyên riêng, điều này phải được thiết kế/kiểm tra.

Các API:

- `ClassLoader.getResource(name)`: URL tài nguyên được tìm theo policy của loader.
- `ClassLoader.getResourceAsStream(name)`: InputStream hoặc `null` nếu không tìm thấy/mở không được; caller phải kiểm tra và đóng.
- `ClassLoader.getResources(name)`: Enumeration các URL có thể thấy, phù hợp điều tra resource trùng tên.
- `URLClassLoader.findResource(name)`: tìm trong các URL riêng của child, **không phải thay đổi class loading policy**.
- `getURLs()`: URL roots riêng của URLClassLoader, **không** bao gồm URL của parent.

Với hệ plugin cần isolation mạnh, phải xác định chính sách **class**, **resource** và **ServiceLoader discovery** riêng. Không suy từ “child-first classes” sang “child-first resources”.

## 15. Tự kiểm tra ưu tiên resource khi class dùng child-first
Trước khi đổi resource policy, dùng chính loader của thực hành A và đặt `config/theme.txt` ở cả host và plugin. Cho hai tệp nội dung khác nhau, rồi kiểm tra ba thao tác:

```java
String path = "config/theme.txt";
System.out.println(childFirst.getResource(path));  // parent-first mặc định
System.out.println(childFirst.findResource(path)); // chỉ nguồn URL của child
var urls = childFirst.getResources(path);
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());       // thứ tự tất cả URL
}
```

Đoạn mã nằm trong phạm vi `try` đã khai báo `ChildFirstLoader childFirst`; cần xử lý `IOException` từ `getResources`. Các API trên trả URL hoặc enumeration, **không** trả nội dung trực tiếp. Hãy đọc từng URL để xác nhận thứ tự nguồn và lưu ý `ClassLoader.getResource` mặc định vẫn có thể chọn tài nguyên parent dù `loadClass` đã ưu tiên child. Nếu resource là schema/config bắt buộc khớp với implementation, hãy ghi rõ quy tắc override hoặc fail-fast. Với `META-INF/services`, cần xét đủ mọi descriptor thay vì chỉ URL đầu tiên.

## 16. Child-first trong mô hình plugin: thiết kế boundary rõ ràng

Hệ plugin thường có ba nhóm:

```text
                        SHARED HOST API
                         api.Plugin
                         api.Request
                         api.Response
                              ▲
                     parent-first cho api.*
                              │
                 ┌────────────┴────────────┐
                 │                         │
             PLUGIN A                   PLUGIN B
             impl.a.*                   impl.b.*
             vendor.json v1             vendor.json v2
                 │                         │
              child-first              child-first
              private libs              private libs
```

Đây là một **mô hình khái niệm**, không tự tạo module/loader graph khi chưa triển khai. Các contract classes cần dùng chung identity; private dependencies có thể khác version.

### Phân biệt shared types và private types

Ví dụ API:

```java
package api;

public interface Processor {
    Result process(Request input) throws PluginException;
}
```

Đây là **khai báo minh họa**, cần thêm `Request`, `Result` và `PluginException` để compile. Tất cả các kiểu xuất hiện ở boundary có thể cần cùng runtime identity:

- `api.Processor` là SPI để host cast plugin implementation.
- `api.Request` và `api.Result` xuất hiện trong JVM method descriptor.
- `api.PluginException` có thể được host catch theo runtime type.
- Callback interface, enum, annotation và những type lồng bên trong payload cũng có thể rò ra biên giới.
- Một `vendor.JsonNode` xuất hiện ở public method signature có thể khiến thư viện tưởng như private trở thành **shared contract dependency**.

Nếu plugin định nghĩa bản sao `api.Request`, reflective lookup như `getMethod("process", HostRequest.class)` có thể không tìm đúng method, hoặc JVM có thể báo loading-constraint errors tùy ngữ cảnh.

**Nguyên tắc thiết kế:** parent-first cho những package/types phải chia sẻ; child-first cho những code/dependencies có thể độc lập, với sự kiểm soát chính sách fallback và module access.

## 17. JPMS và Java 9+: module readability không bằng loader priority

Trong Java Platform Module System (JPMS), một named module có:

- **module resolution**: module nào được chọn vào layer;
- **readability** qua `requires` và các quy tắc module;
- **exports/opens**: package nào accessible hoặc mở cho reflection;
- **defining loader**: loader nào định nghĩa class;
- **delegation policy**: thứ tự loader tìm class.

Năm trục này **không phải một thứ**. Một module `app.module` đọc `api.module` không có nghĩa application loader phải là child của API loader, hoặc chọn child-first cho một package sẽ tự bỏ qua được `exports`.

`URLClassLoader` thường nạp JAR theo **classpath-style** từ các URL. Đưa một modular JAR vào URL array **không tự tạo `ModuleLayer` mới** với `requires`/`exports` hợp lệ. Muốn module isolation, phải thiết kế layer và loaders phù hợp, không chỉ đổi `loadClass`.

Trên Java 9+, các built-in loaders (bootstrap/platform/application) có cơ chế module-aware, nên quan hệ thực tế giữa loader và module có thể phức tạp hơn một parent chain. Những ví dụ ở trên chạy trên **unnamed application classpath** để kiểm soát chính sách dễ quan sát.

## 18. Khi nào chọn policy nào?

**Chọn parent-first mặc định nếu:**

- Plugin là extension đáng tin trong một ứng dụng có dependency versions đã được đồng bộ;
- mọi plugin dùng chung host SDK/SPI/DTO và ít cần library versions riêng;
- mục tiêu là dễ bảo trì, giảm nhầm lẫn type identity và tránh tự override `loadClass`;
- runtime không đòi isolation theo package.

**Cân nhắc child-first có ngoại lệ nếu:**

- Nhiều plugin phải dùng **những versions khác nhau** của cùng thư viện;
- host có library trùng binary names, parent-first sẽ chọn sai phiên bản mà plugin đã compile against;
- shared API đã được thiết kế và nạp bởi một loader chung;
- hệ thống sẵn sàng kiểm thử đồng bộ, package sealing, JPMS và resource loading theo loader graph thực tế.

**Không chọn child-first nếu mục tiêu duy nhất là “an toàn hơn”.** Class loader policy không thay thế sandbox; plugin code không tin cậy có thể thực hiện các hành động mà process có quyền. Hãy sử dụng ranh giới tiến trình/container và các kiểm soát quyền truy cập riêng khi threat model đòi hỏi.

### Quy trình ra quyết định

1. Xác định **shared API type identity** mà host và plugin phải cùng dùng.
2. Tập hợp **dependency collisions**: tên class nào tồn tại ở parent và child, version nào đang được compile against?
3. Kiểm tra parent-first có thực sự gây lỗi version hay không bằng ví dụ nhỏ và binary signatures.
4. Nếu cần child-first, viết policy **theo package**, không đổi toàn bộ tên class vô điều kiện.
5. Định nghĩa chính sách resource lookup và service discovery tương ứng.
6. Thử plugin bằng **runtime loader graph thật**, không chỉ compile cả host/plugin chung một classpath.
7. Kiểm tra unloading/lifecycle khi thay plugin, không tái sử dụng loaded class như thể nó sẽ relink với JAR mới.

## 19. Công cụ chẩn đoán trong Java 17+

### Xác định defining loader

```java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("defined by=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
}
```

Đây là một **method minh họa**, đặt trong class và gọi với type cần kiểm tra. `getModule().getName()` trả `null` khi class ở unnamed module — đó là tình huống bình thường.

Với class loaders có thể lấy được:

```java
System.out.println(pluginLoader.getParent());
System.out.println(java.util.Arrays.toString(pluginLoader.getURLs()));
```

Snippets cần `pluginLoader` kiểu `URLClassLoader`. Nhớ rằng `getURLs()` chỉ cho biết **URLs riêng của child**, không phải effective set sau delegation.

### Đọc bytecode và descriptor

Với ví dụ A:

```sh
javap -classpath hostlib-out -s lib.Version
javap -classpath pluginlib-out -s lib.Version
javap -classpath app-out -c -v demo.PolicyDemo
```

Những lệnh này đọc class files tĩnh. `javap` có thể xác nhận method descriptors mà compiler sinh, nhưng **không chứng minh runtime chọn parent hay child**. Cần kết hợp với `Class.getClassLoader()` hoặc source logging.

### Class-load log

Trên HotSpot:

```sh
java -Xlog:class+load=info -cp "app-out:hostlib-out" demo.PolicyDemo
```

Lệnh dùng classpath separator **Linux/macOS**; Windows thay `:` bằng `;`. Unified Logging có nhiều dòng, thứ tự và vị trí phụ thuộc JVM/build, nên không có stdout chính xác cố định. Tìm các sự kiện `lib.Version` và nguồn class files, sau đó đối chiếu với thông tin defining loader trong chương trình.

## 20. Checklist debug lỗi thực tế

| Triệu chứng | Câu hỏi cần hỏi | Hướng xử lý |
| --- | --- | --- |
| Plugin thấy library phiên bản cũ | Parent có class cùng binary name không? | Kiểm tra parent-first, chọn dependency strategy rõ |
| `ClassCastException` với class cùng tên | Host/plugin có hai `Class<?>` từ hai defining loaders? | Bảo vệ shared API, inspect loaders |
| `NoSuchMethodError` | Caller compile với descriptor nào, runtime class có method ấy? | So bytecode/JAR versions, policy ưu tiên |
| `NoClassDefFoundError` | Dependency nằm ở URL nào hoặc class initializer lỗi? | Đọc cause và runtime lookup graph |
| `IllegalAccessError` | Package/module/caller có quyền access không? | Kiểm tra JPMS exports, visibility |
| `LinkageError` loader constraint violation | Types trong public signatures có bị định nghĩa kép? | Hợp nhất contract identity |
| `ClassNotFoundException` | Local và parent đều không tìm được? | Kiểm tra URL root, JAR entries, parent |
| `ServiceConfigurationError` | Service interface/provider có cùng identity, discovery loader đúng? | TCCL, ServiceLoader, shared SPI |
| Resource configuration sai | `getResource` vẫn parent-first? | Debug `getResources`/`findResource` |
| Trường hợp chỉ lỗi khi nhiều threads | `loadClass` override có bảo vệ `findLoadedClass` và lock? | Test concurrency, locks, parallel capability |

**Đừng nuốt `Throwable` và fallback.** Lỗi liên kết, bảo mật hoặc VM không phải là một lựa chọn class source bình thường. Giữ stacktrace và root cause khi debug.

## 21. Vòng đời loaders và thay version

`URLClassLoader` triển khai `Closeable`. Nếu code sở hữu loader, có thể:

```java
try (URLClassLoader plugin = new URLClassLoader(urls, parent)) {
    Class<?> implementation =
            plugin.loadClass("impl.PluginGreeter");
}
```

Đây là **snippet**, cần biến `urls`, `parent` và import `URLClassLoader`. Khi kết thúc, `close()` đóng những JAR/file handles mà loader quản lý. Nhưng:

- `close()` **không lập tức unload** mọi class/object plugin;
- object/Class/Method/ThreadLocal/threads hoặc TCCL còn được tham chiếu có thể giữ loader sống;
- class đã được định nghĩa không tự đổi bytecode khi một JAR trên đĩa bị thay;
- sau close, code có thể cố lazy-load dependency/resource và thất bại;
- một phiên bản plugin mới thường cần **loader instance mới**, ngắt callbacks/threads và giải phóng references cũ;
- shared API vẫn cần giữ runtime identity ổn định trong vòng đời plugin versions.

Child-first không tự giải quyết hot reload; nó chỉ là một thành phần của kiến trúc nạp lớp.

## 22. Những ngộ nhận cần tránh

- **“Java mặc định child-first.”** Không. `ClassLoader.loadClass` chuẩn ưu tiên parent.
- **“Đặt URL plugin trước URL host trong một child là đã override parent-first.”** Không: parent vẫn được hỏi trước local URLs.
- **“Chỉ cần chọn parent platform là thành child-first.”** Không: đó là thay **tập nhìn thấy qua parent**, không đổi thứ tự lookup.
- **“Child-first luôn tốt hơn vì plugin dùng thư viện mới.”** Không: có thể tự định nghĩa bản sao shared APIs.
- **“Tên interface giống nhau thì cast được.”** Không: JVM type identity còn có defining loader.
- **“Override `loadClass` chỉ cần gọi `findClass` trước.”** Chưa đủ: cần loaded-cache, synchronization, fallback, module/API constraints.
- **“Bắt mọi `Throwable` rồi thử parent là an toàn.”** Sai: như vậy che lỗi JVM/linkage/permission.
- **“Child-first có nghĩa resources cũng child-first.”** Không: `getResource` có policy riêng.
- **“Plugin có duplicate API trong JAR nên JVM tự chọn đúng một bản.”** Không: phụ thuộc delegation và defining loader.
- **“Parent-first sao chép mọi parent JAR vào child.”** Không: chỉ là runtime lookup/delegation.
- **“Hai URLClassLoader cùng class Java là cùng class namespace.”** Không: **hai instances** có thể tự định nghĩa runtime classes khác nhau.
- **“Chạy được trong IDE có nghĩa plugin JAR chắc chắn chạy trong loader runtime.”** Không: IDE/test classpath có thể che lỗi boundary.
- **“Parent-first/child-first là lựa chọn bảo mật đủ cho plugin không tin cậy.”** Không.
- **“Đóng URLClassLoader thì mọi classes unload tức thì.”** Không; còn phụ thuộc GC và references.

## 23. Câu hỏi tự kiểm tra

**1. Parent-first hỏi ai trước?** Sau kiểm tra loaded class, loader hỏi parent; chỉ khi parent không tìm được mới thử `findClass` của child.

**2. Child-first có sẵn trong constructor `URLClassLoader` không?** Không. `URLClassLoader` mặc định dùng `loadClass` parent-first; child-first phải được triển khai có chủ đích.

**3. Cùng binary name ở parent và child, parent-first thường dùng bản nào?** Bản parent nếu parent tìm được trước.

**4. Cùng tình huống, child-first có thể dùng bản nào?** Bản child nếu local lookup thành công và namespace không được bảo vệ.

**5. Hai definitions cùng tên có là cùng Java type runtime không?** Không nếu defining loaders khác nhau.

**6. Vì sao nên parent-first cho API của host?** Để host và plugin dùng cùng runtime interface/DTO/callback identities, tránh cast/linkage lỗi.

**7. Vì sao `findLoadedClass` quan trọng?** Tránh duplicate definitions và đảm bảo loaded classes được sử dụng nhất quán.

**8. Vì sao chỉ fallback khi `ClassNotFoundException`?** Vì các errors khác có thể phản ánh bytecode không hợp lệ, thiếu quyền hoặc lỗi linking, không phải “không có local class”.

**9. Nếu chỉ override `loadClass`, `getResource` có tự child-first không?** Không. Resource lookup cần policy riêng nếu muốn đổi.

**10. `URLClassLoader.getURLs()` có bao gồm URLs của parent không?** Không; chỉ các URL riêng của loader ấy.

**11. Tại sao `NoSuchMethodError` có thể xuất hiện dù class đã load thành công?** Method resolution trong bytecode đòi exact descriptor, nhưng runtime version được chọn không có method ấy.

**12. Parent-first có thể là lựa chọn hợp lý khi plugin cần các SDK/DTO chung?** Có, đặc biệt khi tất cả plugins dùng một binary API có version quản lý thống nhất.

**13. Child-first có phải luôn chọn riêng mọi Java SE class không?** Không; những nền tảng/namespace bảo vệ cần delegation theo quy tắc runtime.

**14. Chọn strategy dựa trên tiêu chí gì?** Những types **phải chung identity**, những dependencies **phải có version riêng**, module/resource policy và chi phí vận hành.

## 24. Nguồn chuẩn

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): thuật toán `loadClass`, `findLoadedClass`, `findClass`, `getClassLoadingLock`, parallel capability.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): constructor, URLs, lookup và lifecycle.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): defining loader và `isAssignableFrom` khi kiểm tra API identity.
- [JVMS Java SE 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): runtime class identity, loading, linking và loading constraints.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery và tác động của loader/context.

**Tóm tắt cần nhớ:** **Parent-first** ưu tiên reuse class từ parent, tốt cho shared APIs và cấu trúc runtime đơn giản, nhưng có thể khiến dependency host shadow bản plugin. **Child-first** ưu tiên định nghĩa từ child, hữu ích khi plugin cần dependency versions riêng, nhưng phải **cố ý parent-first cho các shared boundary types**, đồng bộ đúng, xử lý lỗi chính xác và kiểm tra resource/JPMS. Câu hỏi không phải “chính sách nào tốt hơn?” mà là **“class nào phải chung runtime identity, và class nào phải được phép tách riêng?”**
