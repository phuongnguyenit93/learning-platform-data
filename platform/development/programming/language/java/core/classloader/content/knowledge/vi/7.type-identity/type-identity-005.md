# Runtime package được xác định bởi tên package và class loader

Trong Java, hai lớp cùng khai báo `package demo;` chưa chắc thuộc **cùng runtime package**. Theo *Java Virtual Machine Specification* (JVMS), runtime package của một class/interface được xác định bằng **tên package và defining class loader** (loader thực sự định nghĩa lớp đó). Vì vậy, nếu hai loader khác nhau định nghĩa các lớp có tên package giống hệt nhau, chúng vẫn thuộc **hai runtime packages khác nhau**.

Quy tắc này rất quan trọng với `classloader`, plugin, application server, bytecode generation và các thư viện dùng nhiều phiên bản dependency, vì nó ảnh hưởng trực tiếp đến quyền truy cập **package-private**, class identity và lỗi liên kết lúc chạy.

## 1. Phân biệt source package và runtime package

Trong mã nguồn Java, khai báo:

```java
package com.example.domain;
```

xác định package name `com.example.domain`. Khi lập trình thông thường, các tệp cùng package có thể truy cập các thành viên package-private của nhau nếu các điều kiện khác cũng phù hợp.

Nhưng JVM phải xử lý các lớp có thể được định nghĩa bởi nhiều class loaders. Do đó nó cần biết không chỉ tên package, mà còn loader đã định nghĩa lớp:

```text
Runtime package identity =
    (package name, defining class loader)
```

Ví dụ:

```text
Class A:
  binary name       = demo.One
  package name      = demo
  defining loader   = Loader-Parent

Class B:
  binary name       = demo.Two
  package name      = demo
  defining loader   = Loader-Child

Runtime package A = (demo, Loader-Parent)
Runtime package B = (demo, Loader-Child)

Kết luận: runtime package A != runtime package B
```

Tuy cả hai đều có lệnh `package demo;`, chúng **không** được JVM coi là cùng runtime package.

Ngược lại, nếu cả hai lớp được **cùng loader định nghĩa**, chúng có cùng package name và cùng runtime package, kể cả khi source file nằm ở hai thư mục dự án hoặc hai JAR khác nhau. Việc chia sẻ package trong cùng loader vẫn có thể bị ràng buộc thêm bởi quy tắc sealing, mô-đun và cấu hình môi trường; không có nghĩa được bỏ qua các quy tắc đó.

### Ba khái niệm cần tách rõ

| Khái niệm | Danh tính/cách xác định | Ví dụ |
|---|---|---|
| **Binary name** | Tên nhị phân của class/interface | `demo.One` |
| **Runtime class** | `(binary name, defining loader)` | `(demo.One, Loader-A)` |
| **Runtime package** | `(package name, defining loader)` | `(demo, Loader-A)` |

Điểm khác biệt quan trọng: hai class **khác tên** như `demo.One` và `demo.Two` có thể cùng runtime package nếu cùng defining loader; hai class **cùng tên** như `demo.One` định nghĩa ở hai loader khác nhau vừa là hai runtime classes khác nhau, vừa thuộc hai runtime packages khác nhau.

## 2. Defining loader khác initiating loader

Khi gọi:

```java
Class<?> type = childLoader.loadClass("demo.One");
```

không thể suy ra ngay rằng `childLoader` là defining loader của `type`.

Mặc định, `ClassLoader.loadClass` sử dụng **parent delegation**: nó tìm lớp đã nạp, nhờ parent tìm trước, rồi mới gọi `findClass` ở child nếu parent không nạp được. Vì thế:

```text
childLoader.loadClass("demo.One")
        |
        v
parentLoader.loadClass("demo.One")
        |
        +--> nếu parent tìm thấy:
              type.getClassLoader() == parentLoader
              child chỉ là một initiating loader có thể nhận diện type
```

Trong JVMS:

- **Defining loader** là loader được dùng để thực sự định nghĩa runtime class, ví dụ qua `defineClass`.
- **Initiating loader** là loader đã bắt đầu nạp một lớp qua cơ chế delegation hoặc được JVM ghi nhận trong quá trình tải. Một loader có thể là initiating loader của class do loader khác định nghĩa.
- Danh tính runtime class và runtime package dựa trên **defining loader**, không dựa trên đối tượng loader vừa được gọi ở một biểu thức `loadClass`.

API quan sát hữu ích:

```java
ClassLoader definingLoader = someType.getClassLoader();
String packageName = someType.getPackageName();
```

Đây là các câu lệnh minh họa khi đã có biến `someType` kiểu `Class<?>`. `getClassLoader()` có thể là `null` khi JVM biểu diễn bootstrap loader. `getPackageName()` cho **chuỗi tên package**, không trả toàn bộ danh tính runtime package.

Nếu cần so sánh hai class đã nạp:

```java
boolean sameRuntimePackage =
        first.getPackageName().equals(second.getPackageName())
        && first.getClassLoader() == second.getClassLoader();
```

Đây là cách so sánh minh họa cho **class/interface thông thường** khi `first` và `second` đều đã có giá trị. Với array classes hoặc các loại đặc biệt khác, cần xét quy tắc JVM dành riêng cho loại đó; không áp dụng máy móc mọi phép suy luận về package-private access của một class thông thường.

## 3. Vì sao runtime package ảnh hưởng đến access control?

Java có bốn mức truy cập thường học: `public`, `protected`, *package-private* (không ghi modifier) và `private`.

Một method/field **package-private** thông thường chỉ có thể được truy cập từ code trong **cùng runtime package**. Do vậy, việc **source package name giống nhau** chưa đủ.

Ví dụ mã Java hợp lệ khi biên dịch cùng package:

```java
package demo;

public class PackageApi {
    static String secret() {
        return "private-to-package";
    }
}
```

```java
package demo;

public class PackageClient {
    public static String callSecret() {
        return PackageApi.secret();
    }
}
```

Ở thời điểm biên dịch, compiler thấy hai lớp cùng package `demo` nên cho phép gọi method `secret()`. Nhưng khi chạy, nếu `PackageClient` được loader con tự định nghĩa còn `PackageApi` do loader cha định nghĩa, JVM nhìn thấy:

```text
PackageClient:
    runtime package = (demo, ChildLoader)

PackageApi:
    runtime package = (demo, ParentLoader)

PackageClient.callSecret()
        |
        | invokes PackageApi.secret()  [package-private]
        v
    IllegalAccessError
```

`IllegalAccessError` là một `LinkageError`: lỗi kiểm tra quyền truy cập ở cấp JVM, có thể chỉ xuất hiện khi symbolic method reference được giải quyết hoặc khi JVM thực hiện kiểm tra liên quan. Điều này khác với lỗi compiler `'secret() is not public'` khi code nguồn vốn nằm khác package.

### Bảng phân biệt các tình huống

| Nguồn và runtime | Cùng runtime package? | Truy cập package-private |
|---|---|---|
| Hai class `demo.A`, `demo.B` do cùng defining loader định nghĩa | Có | Có thể truy cập theo quy tắc package-private |
| Hai class `demo.A`, `demo.B` do hai defining loaders khác nhau định nghĩa | Không | Bị từ chối nếu không có cơ chế quyền truy cập khác hợp lệ |
| Hai class có package name khác nhau nhưng cùng loader | Không | Không được package-private |
| Child gọi `loadClass` nhưng parent thực sự định nghĩa cả hai class cùng package | Có | Vẫn thuộc một runtime package của parent |
| Hai class khác loader, tương tác qua member `public` của lớp `public` và quyền module hợp lệ | Không | Public API có thể truy cập, không cần cùng runtime package |

Từ **“có thể”** ở đây là có chủ ý: quyền package-private phải được kiểm tra với đúng class/member và các quy tắc truy cập liên quan; không phải mọi thành viên hay mọi module đều tự động truy cập được chỉ vì cùng tên package.

## 4. Demo Java 17+: cùng package name nhưng IllegalAccessError

Ví dụ sau **biên dịch được bằng Java 17** và cố ý tạo hai runtime packages khác nhau. Loader con chỉ nạp `demo.PackageClient` theo kiểu child-first; `demo.PackageApi` vẫn do loader cha nạp. Kết quả: lời gọi API `public` hoạt động, còn lời gọi method package-private bị JVM từ chối.

Cấu trúc mã nguồn:

```text
src/
└── demo/
    ├── PackageApi.java
    ├── PackageClient.java
    └── RuntimePackageDemo.java
```

**Tệp `src/demo/PackageApi.java`:**

```java
package demo;

public class PackageApi {
    static String secret() {
        return "private-to-package";
    }

    public static String open() {
        return "public-api";
    }
}
```

**Tệp `src/demo/PackageClient.java`:**

```java
package demo;

public class PackageClient {
    public static String callSecret() {
        return PackageApi.secret();
    }

    public static String callPublic() {
        return PackageApi.open();
    }
}
```

**Tệp `src/demo/RuntimePackageDemo.java`:**

```java
package demo;

import java.io.InputStream;
import java.lang.reflect.InvocationTargetException;

public class RuntimePackageDemo {
    static class ChildFirstClientLoader extends ClassLoader {
        ChildFirstClientLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            // Chỉ thay chiến lược tải cho đúng một class thử nghiệm.
            if (!"demo.PackageClient".equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);
                if (type == null) {
                    type = findClass(name);
                }
                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            String path = name.replace('.', '/') + ".class";

            // Lấy bytes của class thử nghiệm từ classpath cha.
            try (InputStream input =
                    getParent().getResourceAsStream(path)) {
                if (input == null) {
                    throw new ClassNotFoundException(name);
                }

                byte[] bytes = input.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (java.io.IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = RuntimePackageDemo.class.getClassLoader();
        Class<?> original = PackageClient.class;

        Class<?> child = new ChildFirstClientLoader(parent)
                .loadClass("demo.PackageClient");

        System.out.println("Same binary name: "
                + original.getName().equals(child.getName()));
        System.out.println("Same defining loader: "
                + (original.getClassLoader() == child.getClassLoader()));

        System.out.println("Parent public: "
                + PackageClient.callPublic());
        System.out.println("Child public: "
                + child.getMethod("callPublic").invoke(null));

        try {
            System.out.println(
                    child.getMethod("callSecret").invoke(null));
        } catch (InvocationTargetException ex) {
            System.out.println("Child package-private: "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa `src` bằng JDK 17+:

```bash
javac --release 17 -d out src/demo/PackageApi.java src/demo/PackageClient.java src/demo/RuntimePackageDemo.java
java -cp out demo.RuntimePackageDemo
```

Đầu ra:

```text
Same binary name: true
Same defining loader: false
Parent public: public-api
Child public: public-api
Child package-private: IllegalAccessError
```

**Tại sao như vậy?**

1. `PackageClient.class` từ application loader được tham chiếu trực tiếp trong `main`, tạo ra một runtime class do parent loader định nghĩa.
2. `ChildFirstClientLoader` cố ý chỉ tự `defineClass("demo.PackageClient", bytes)`. JVM cho phép hai runtime classes cùng binary name tồn tại vì defining loaders khác nhau.
3. Khi `PackageClient` của child gọi `PackageApi.open()`, đường tải thông thường ủy quyền cho parent và lấy `PackageApi` từ parent. Method `open()` là `public` nên lời gọi hợp lệ trong ví dụ classpath này.
4. Khi bản child gọi `PackageApi.secret()`, bytecode tham chiếu đến method không có modifier `public`, `protected` hoặc `private` — tức **package-private**. Hai class có defining loader khác nhau, nên thuộc hai runtime packages khác nhau dù cùng tên `demo`. JVM báo `IllegalAccessError`.
5. Reflection `Method.invoke` bọc throwable do method được gọi ném vào `InvocationTargetException`. Ví dụ lấy `ex.getCause()` để in đúng `IllegalAccessError` ở bên trong.

Đây là loader **dùng để thí nghiệm**, không phải cách cài đặt class loader production. Nó đọc lại bytecode từ parent resource và chủ động thay đổi chính sách cho một binary name; khi làm plugin thật cần giới hạn namespace, giải quyết dependency, package sealing, module boundaries và vòng đời loader.

**Lưu ý:** Đừng sửa `PackageApi.secret()` thành `public` khi đang thử nghiệm lần đầu, vì điều đó làm mất tình huống cần quan sát. Có thể thực hiện thay đổi này **sau** khi thấy lỗi để đối chiếu: cùng khác runtime package, nhưng public access trở nên hợp lệ.

## 5. Khác runtime package vẫn có thể giao tiếp như thế nào?

Việc khác runtime package không cấm mọi tương tác. Điều nó thay đổi ở ví dụ là **access check cho package-private member**.

Một ranh giới hợp lý giữa application và plugin thường là:

```text
Parent/App ClassLoader
    ├── shared.api.Plugin          (public interface)
    └── shared.api.Message         (public DTO/contract)
              ^
              | delegation cho các shared APIs
              |
Child/Plugin ClassLoader
    ├── plugin.impl.ExamplePlugin  (implementation riêng)
    └── plugin.libs.*              (dependency riêng nếu được cấu hình)
```

Plugin loader **ủy quyền cho parent** với `shared.api.Plugin` và `shared.api.Message`. Vì vậy application và plugin làm việc với cùng runtime types của API chung. Code triển khai riêng ở child có thể giao tiếp qua public methods của interface, và application không phải truy cập package-private internals của plugin.

Một interface chia sẻ:

```java
package shared.api;

public interface Plugin {
    String run(String input);
}
```

Đây là **đoạn nguồn API minh họa**, không chứa `main`. Khi sử dụng thật, compile API thành dependency mà parent loader có thể định nghĩa, rồi đảm bảo child ủy quyền cho parent đối với namespace API. Cần đồng thời tính đến rule truy cập module khi dùng named modules.

Nếu hai loader **cùng tự định nghĩa lại** `shared.api.Plugin`, tên giống nhau vẫn không đủ: chúng là hai runtime interface khác nhau và object plugin có thể không cast được sang interface ứng dụng mong đợi.

## 6. Các quy tắc quyền truy cập có liên quan

Runtime package là một phần của cơ chế truy cập; cần phân biệt những trường hợp sau:

### 6.1. Lớp top-level không có `public`

Ví dụ:

```java
package demo;

class Helper {
}
```

`Helper` là **package-private top-level class**. Một lớp trong runtime package khác không có quyền truy cập trực tiếp vào kiểu này chỉ vì có cùng chuỗi tên package. JVM có thể báo `IllegalAccessError` khi cố giải quyết một tham chiếu không hợp lệ.

### 6.2. Trường và phương thức package-private

Thành viên không khai báo access modifier thường có quyền **package access**. Compiler Java kiểm tra theo package trong source; JVM kiểm tra trong bối cảnh runtime types và runtime packages.

Ví dụ:

```java
package demo;

public class Holder {
    static int count = 1;
    static int readCount() {
        return count;
    }
}
```

Nếu caller do loader khác định nghĩa, cùng `package demo;` trong source không bảo đảm lời gọi `Holder.readCount()` qua runtime link sẽ được phép.

### 6.3. `protected` và `private`

- `protected` có quy tắc truy cập khi cùng runtime package **hoặc** qua quan hệ lớp con trong những điều kiện cụ thể; không được hiểu đơn giản là “mọi subclass luôn truy cập được mọi protected member bằng mọi receiver”.
- `private` phụ thuộc đến quyền sở hữu class/nestmates và cơ chế truy cập JVM; **cùng runtime package không đủ** để truy cập private member.
- `public` thường không đòi cùng runtime package, nhưng còn chịu module accessibility và các quy tắc hợp lệ khác.

Vì vậy tránh suy luận rằng biết runtime package là có thể bỏ qua những kiểm tra khác về subclass, declaring class, module hoặc bytecode instruction.

## 7. Java 9+ module system có thay đổi công thức không?

**Không thay công thức cốt lõi của runtime package trong JVMS:** package name cộng defining loader vẫn quyết định runtime package identity của class/interface thông thường. Java Platform Module System (JPMS) bổ sung **module membership** và **module readability/exports/opens** vào mô hình truy cập.

Hãy xét hai lớp cùng package name nhưng ở hai loader:

```text
Loader A defines com.acme.One
Loader B defines com.acme.Two
```

Chúng không cùng runtime package, kể cả khi các module liên quan đều `exports com.acme`. Ngược lại, hai class trong cùng runtime package không có nghĩa mọi tương tác reflective hay truy cập kiểu trong named modules luôn được phép.

Các khái niệm phân biệt:

| Khái niệm | Hỏi điều gì? |
|---|---|
| Runtime package | Class thuộc tên package nào **và do defining loader nào định nghĩa**? |
| Runtime module | Class thuộc module runtime nào (`Class.getModule()`)? |
| Module reads | Module của caller có đọc được module của type được gọi không? |
| Exports | Package có được export cho module cần truy cập public types không? |
| Opens | Có cho phép loại deep reflection phù hợp với rules hiện hành không? |

Ví dụ thử nghiệm phía trên chạy trên **classpath** nên các lớp ứng dụng nằm trong unnamed module. Đây là cách cô lập hiệu ứng runtime-package/loader để học, không có nghĩa bỏ qua JPMS khi ứng dụng dùng module path.

Với named modules, cấu hình split packages và phân công packages cho loaders còn chịu thêm ràng buộc. Đừng dùng thử nghiệm “hai loader cùng khai báo package” như lời khuyên để cố nhét nhiều module xung đột vào một class loader.

## 8. Không nhầm runtime package với Package metadata hoặc JAR layout

Có nhiều cách quan sát một tên package nhưng không cách nào một mình quyết định quyền truy cập:

- `type.getPackageName()` trả **tên package**, ví dụ `demo`. Hai runtime packages khác nhau vẫn có thể trả cùng chuỗi.
- `type.getPackage()` trả metadata kiểu `java.lang.Package` khi thích hợp, có thể chứa thông tin annotation, specification/implementation version hoặc sealing. Đối tượng `Package` không thay thế định nghĩa runtime-package identity của JVMS.
- Đường dẫn tài nguyên `demo/PackageApi.class` biểu diễn cách tổ chức file/JAR. Hai loader có thể đọc cùng entry bytecode nhưng định nghĩa **hai runtime classes**.
- `Class.getProtectionDomain()` mô tả thông tin protection domain liên quan nguồn/quyền trong runtime; nó không phải thành phần của cặp định danh runtime package.
- `type.getClassLoader()` là điểm quan sát defining loader hữu ích; khi trả `null`, Java API dùng quy ước biểu diễn bootstrap loader.

**Package sealing** là ràng buộc riêng có thể được class loader/JAR manifest áp dụng để kiểm soát nguồn định nghĩa class trong một package. Nó không làm các class khác defining loader tự động trở thành cùng runtime package. Một lỗi sealing cũng không đồng nghĩa `IllegalAccessError` do package-private.

## 9. Trường hợp thường gặp khi triển khai

### 9.1. Plugin vô tình nhúng bản sao shared API

Ứng dụng có `com.app.spi.Plugin` do app loader định nghĩa, nhưng plugin JAR cũng đóng gói class cùng tên, và child-first loader định nghĩa bản của nó. Khi code cố cast implementation sang `com.app.spi.Plugin` phía ứng dụng, có thể gặp `ClassCastException` hoặc lỗi linking do loader constraints.

**Hướng giải quyết:** đặt SPI/DTO hợp đồng chung ở loader cha, thiết lập delegation cho namespace của nó và chỉ isolate implementation hoặc dependency cần thiết.

### 9.2. Framework sinh proxy ở loader không phù hợp

Code sinh/proxy có thể cần truy cập package-private constructor, type hoặc method. Nếu proxy bị định nghĩa ở loader khác dù mang cùng package name, lời gọi có thể lỗi `IllegalAccessError`. Các framework thường cần cơ chế định nghĩa class phù hợp để giữ runtime package/nest/module access khi được phép.

**Hướng giải quyết:** xác định proxy class thực tế được định nghĩa bởi loader nào, phương thức nào bị từ chối và access requirements của thư viện. Không sửa bằng cách tự ý mở toàn bộ module hoặc đổi mọi method thành `public` nếu không phù hợp contract.

### 9.3. Thấy “same package” nhưng Java vẫn từ chối

Kiểm tra thêm defining loader, package name, module, exports/opens, class access modifiers và các symbolic references được bytecode dùng.

**Hướng giải quyết:** phân biệt lỗi xuất phát từ *runtime package mismatch*, *module access* hay *binary incompatibility*. Ba vấn đề có thể có biểu hiện liên quan nhưng cách sửa khác nhau.

### 9.4. Hot reload tạo class có cùng tên

Reload thông qua defining loader mới tạo runtime classes **mới**, dù mã nguồn/package name không đổi. Instance cũ và class mới không tự nhiên tương thích. Phần static state, package access và type casting gắn với đúng class identity.

**Hướng giải quyết:** giữ rõ vòng đời loader, tránh trộn instances từ thế hệ cũ/mới vào cùng API nội bộ; dùng shared public contracts ổn định khi giao tiếp xuyên boundary.

## 10. Cách chẩn đoán một IllegalAccessError giữa các loader

Khi log báo lỗi truy cập dù hai class source đều khai báo một package:

1. Ghi nhận **class đang cố truy cập**, class khai báo target member và tên method/field trong stack trace.
2. In `getName()`, `getPackageName()`, `getClassLoader()` của hai `Class<?>` tương ứng. Quan trọng là **defining loader**, không chỉ loader đã gọi `loadClass`.
3. Kiểm tra member có `public`, `protected`, `private` hay package-private, và target declaring class có `public` hay không.
4. Kiểm tra actual class loader policy (`loadClass` override, parent-first/child-first) và xem có duplicate API classes trong các JAR không.
5. Nếu dùng JPMS, kiểm tra module ownership, `exports`/`opens` và các quy tắc access liên quan.
6. Xác minh deployment thực tế: class version, binary name, shaded JAR, generated classes hoặc proxy bytecode. Không chỉ nhìn source hiện tại.
7. Sửa placement/delegation hoặc API boundary: dùng loader chung cho shared contracts, hoặc public API hợp lệ nếu giao tiếp xuyên runtime packages thực sự là chủ đích.

Có thể dùng đoạn hỗ trợ sau trong một chương trình đã có hai đối tượng `Class<?>`:

```java
static void inspect(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("package=" + type.getPackageName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
}
```

Đây là **method minh họa**, không phải chương trình độc lập. Chuỗi in cho loader/module phụ thuộc cấu hình môi trường; không gán cứng đầu ra. Trong tình huống có duplicate binary name, nên in cả `System.identityHashCode(type)` hoặc so sánh `Class<?>` trực tiếp nếu cần kiểm tra object identity trong phạm vi một JVM.

## 11. Kiểm tra kiến thức

**Câu 1.** Hai class đều `package demo;`, một class do loader A và một class do loader B định nghĩa. Chúng có cùng runtime package không?

**Trả lời:** Không. Runtime package identity là `(package name, defining loader)`; defining loaders khác nhau nên runtime packages khác nhau.

**Câu 2.** Child loader gọi `loadClass("demo.Api")` nhưng parent có sẵn `demo.Api`, và child kế thừa parent-first. Class này thuộc runtime package của loader nào?

**Trả lời:** Nếu parent là defining loader thực tế, runtime package dựa vào parent, dù lời gọi ban đầu đi qua child.

**Câu 3.** Compiler cho phép gọi package-private method từ một lớp cùng source package. JVM chắc chắn cho phép khi chạy không?

**Trả lời:** Không. Nếu classes được định nghĩa bởi các loaders khác nhau, JVM có thể ném `IllegalAccessError`.

**Câu 4.** Có thể dùng `type.getPackageName()` để kiểm tra hai lớp có chung runtime package không?

**Trả lời:** Không đủ. Phải xét cả defining loader; với lớp bình thường có thể đối chiếu chuỗi package cùng `getClassLoader()`.

**Câu 5.** Hai lớp có cùng binary name nhưng được định nghĩa bởi hai loaders khác nhau có là một kiểu không?

**Trả lời:** Không. Runtime class identity là `(binary name, defining loader)`. Chúng cũng có runtime packages khác nhau vì defining loaders khác nhau.

**Câu 6.** Khi muốn plugin và app dùng cùng interface, nên đặt interface ở đâu?

**Trả lời:** Trong dependency mà loader chung/parent định nghĩa được, và đảm bảo plugin loader ủy quyền namespace API đó để cả hai cùng sử dụng một runtime type.

**Câu 7.** Module `exports` một package có thể tự biến hai runtime packages khác nhau thành một runtime package không?

**Trả lời:** Không. Module rules là tầng bổ sung về khả năng truy cập; chúng không thay đổi cặp package name và defining loader.

## 12. Nguồn chuẩn

- *Java Virtual Machine Specification* `5.3`, “Creation of Classes and Interfaces”: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- *Java Virtual Machine Specification* `5.4.4`, “Access Control”: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4
- Java SE 17 API, `ClassLoader` và delegation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `Class` (`getPackageName`, `getClassLoader` và `getModule`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html

**Ghi nhớ:** Tên package trong `package ...;` là thông tin cú pháp; runtime package theo JVM còn phụ thuộc **defining class loader**. Đây là lý do hai lớp cùng package name đôi khi không truy cập được package-private members của nhau, và cũng là lý do phải bố trí class loaders cùng shared APIs đúng chỗ trong kiến trúc plugin/module.
