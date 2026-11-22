# Giới hạn định nghĩa lớp trong package java.* — Java ClassLoader

Java cho phép ứng dụng tự viết `ClassLoader` để tải bytecode từ JAR, thư mục, bộ nhớ hoặc nguồn tùy biến. Nhưng quyền **định nghĩa lớp mới** không phải là quyền vô hạn: một custom/application class loader thông thường **không được định nghĩa class có binary name bắt đầu bằng `java.`**. Nếu gọi `ClassLoader.defineClass(...)` với tên như `java.demo.Reserved`, JVM/JDK áp dụng giới hạn đặc biệt và ném **`SecurityException`**.

Quy tắc trong **Java SE 17 API, `ClassLoader#defineClass`** được phát biểu chính xác hơn: tên bắt đầu bằng `java.` chỉ có thể được định nghĩa bởi **platform class loader hoặc các loader tổ tiên của nó**. Đây **không phải** quyền mà bất kỳ subclass `ClassLoader` nào cũng được cấp chỉ vì nó ủy quyền cho platform loader.

Bài học tập trung vào sự khác nhau giữa **load/ủy quyền một lớp nền tảng đã tồn tại** và **tự định nghĩa lớp mới trong namespace `java.*`**, vì sao JVM bảo vệ namespace đó, cách nhận diện lỗi, các giới hạn liên quan và thiết kế package/class loader an toàn.

## 1. Hai hành động dễ bị nhầm: loadClass và defineClass

Giả sử một custom loader:

```java
ClassLoader child = new ClassLoader(
        ClassLoader.getSystemClassLoader()) {
};
Class<?> stringType = child.loadClass("java.lang.String");
```

Điều này **hợp lệ**. Child yêu cầu `java.lang.String`, mặc định ủy quyền lên parent rồi tới các loader nền tảng phù hợp. Nó nhận lại đối tượng `Class<?>` tương ứng với lớp `String` vốn đã được runtime định nghĩa, **không tự tạo một bản `java.lang.String` thứ hai**.

Ngược lại, code trong subclass:

```java
return defineClass("java.demo.Reserved", bytes, 0, bytes.length);
```

đang yêu cầu **chính subclass đó định nghĩa class** thuộc namespace `java.`. Trên application/custom loader bình thường, yêu cầu bị từ chối bằng `SecurityException` cho dù bytes là class file hợp lệ.

| Hành động | Ý nghĩa | Kết quả thường gặp với class JDK |
|---|---|---|
| `child.loadClass("java.lang.String")` | Yêu cầu tìm class, có thể ủy quyền parent | Thành công, trả lại class nền tảng |
| `Class.forName("java.lang.String")` | Tra class theo defining loader của caller và yêu cầu initialization | Thành công trong runtime phù hợp |
| `String.class` | Class literal tham chiếu class đã được JVM biết đến | Hợp lệ |
| `child.defineClass("java.demo.Reserved", bytes, ...)` trong subclass | Child **tự định nghĩa** class trong namespace `java.` | `SecurityException` |
| `child.getResource("java/lang/String.class")` | Tra resource/class bytes, không phải định nghĩa runtime class | Có thể trả URL nếu resource được cung cấp/quy tắc module cho phép |

**Nguyên tắc:** `loadClass` có thể trả class do **loader khác** định nghĩa. Chỉ việc gọi `loadClass` trên child không chứng minh child là *defining loader*. Quan sát bằng `clazz.getClassLoader()` và hiểu cơ chế parent delegation.

## 2. Quy tắc bảo vệ chính xác của defineClass

Các overload thường gặp:

```java
protected final Class<?> defineClass(
        String name, byte[] b, int off, int len);

protected final Class<?> defineClass(
        String name, byte[] b, int off, int len,
        java.security.ProtectionDomain domain);
```

Đây là **chữ ký API minh họa**, không phải một chương trình riêng. Khi custom loader dùng `defineClass` để định nghĩa class thường, Java SE 17 đặt các điều kiện:

1. `name` là **binary name** dự kiến, ví dụ `com.example.Widget`; không phải `com/example/Widget.class`.
2. Bytes phải có định dạng class file hợp lệ, offset/length trong giới hạn.
3. Khi `name` không `null`, tên khai báo trong bytecode phải khớp tên được truyền, nếu không có thể phát sinh `NoClassDefFoundError`.
4. Package có thể chịu quy tắc nhất quán **chứng chỉ người ký (signer certificates)** giữa những classes được cùng loader định nghĩa.
5. **Đặc biệt với `java.`:** một loader **không phải platform loader hoặc tổ tiên của nó** không được định nghĩa class mang tên bắt đầu bằng `java.`; có thể nhận `SecurityException`.

Quy tắc này được công bố trực tiếp trong JavaDoc, **không chỉ là một quy ước ngầm “đừng dùng tên đó”**.

### Quy tắc kiểm tra phần đầu tên

Dạng cấm là tên bắt đầu bằng **`java.`** có dấu chấm ngay sau `java`:

```text
java.lang.String         -> namespace được bảo vệ
java.util.List           -> namespace được bảo vệ
java.demo.Reserved       -> namespace được bảo vệ

com.example.MyClass      -> không rơi vào quy tắc java.*
org.acme.plugin.Tool     -> không rơi vào quy tắc java.*
myjava.demo.Widget       -> không rơi vào quy tắc java.*
javax.example.Widget     -> không tự động bị quy tắc java.* này chi phối
jdk.example.Widget       -> không tự động bị quy tắc java.* này chi phối
```

Những dòng `javax.*` hoặc `jdk.*` cuối **không phải khuyến nghị đặt tên ứng dụng ở đó**. Các package/JDK modules khác vẫn có thể được bảo vệ bởi **các cơ chế riêng** (module/package conflicts, accessibility, class identity, vendor policies). Với ứng dụng mới, nên chọn package thuộc miền/tổ chức của mình, như `com.acme.project`.

**Đừng đánh đồng** giới hạn `java.*` với việc Java cấm mọi class có tiền tố chữ `java` trong bất kỳ ngữ cảnh nào; vấn đề là namespace được quy định và cách runtime định nghĩa class.

## 3. Vì sao Java cần hạn chế namespace java.*?

Một mục tiêu quan trọng là bảo vệ **tính toàn vẹn của các kiểu/API nền tảng** mà toàn bộ Java runtime dựa vào.

Ví dụ, nếu một plugin có thể bí mật định nghĩa `java.lang.String` riêng dưới cùng tên:

- `Object`, `String`, `Class`, `Throwable` hoặc các API tiêu chuẩn có thể bị hiểu sai namespace và tính tương thích kiểu.
- Code có thể nhầm một lớp giả mạo với một lớp nền tảng chỉ vì chúng có **cùng binary name**.
- Các giả định nội bộ của bytecode, linking, serialization, reflection hoặc framework có thể trở nên không đáng tin.
- Hệ thống/plugin có nguy cơ đánh lừa code khác bằng tên namespace vốn mang ý nghĩa platform.

Java dùng nhiều biện pháp đồng thời: namespace restriction tại `defineClass`, cơ chế loader hierarchy, type identity, verifier, linking constraints, module ownership/access và các kiểm tra khác. **Giới hạn `java.*` là một biện pháp riêng** — không phải mô tả đầy đủ mô hình bảo mật của JVM.

### Cùng tên không đồng nghĩa cùng runtime type

Đối với class thông thường:

```text
Runtime class identity =
    (binary name, defining class loader)
```

Nếu hai loaders khác nhau cùng định nghĩa `com.acme.User`, chúng tạo hai runtime classes khác nhau dù source/bytecode giống nhau. Với `java.lang.String`, việc cho phép ứng dụng tự định nghĩa thêm bản trùng tên có thể tạo nguy cơ đặc biệt nghiêm trọng. Bởi vậy JDK quy định phạm vi loader rất hẹp đối với tên bắt đầu `java.`.

**Phân biệt:** Parent-first delegation giúp child **dùng chung các class nền tảng**; giới hạn `defineClass` ngăn child tùy ý tạo **class mới mạo danh namespace nền tảng**. Hai cơ chế bổ sung cho nhau nhưng **không giống nhau**.

## 4. Java 17+ demo: class thường định nghĩa được; java.* bị từ chối

Demo dưới đây biên dịch ra **hai class files hợp lệ**:

- `sample.Allowed`: class tên thông thường để custom loader định nghĩa thành công.
- `java.demo.Reserved`: một class test **nằm trong namespace bị bảo vệ**, chỉ nhằm chứng minh custom loader không được định nghĩa nó. **Không triển khai code ứng dụng thực tế trong package này.**

Chương trình chính tải bytes từ disk, tự gọi `defineClass` cho hai tên khác nhau, đồng thời đối chiếu `loadClass("java.lang.String")`.

Cấu trúc:

```text
guard-demo/
├── src/
│   ├── sample/
│   │   └── Allowed.java
│   ├── java/
│   │   └── demo/
│   │       └── Reserved.java
│   └── GuardDemo.java
└── out/
```

### 4.1. Class bình thường

Tệp **`src/sample/Allowed.java`**:

```java
package sample;

public final class Allowed {
    public static String value() {
        return "allowed";
    }
}
```

### 4.2. Class thử nghiệm mang tên java.*

Tệp **`src/java/demo/Reserved.java`**:

```java
package java.demo;

public final class Reserved {
    public static String value() {
        return "reserved";
    }
}
```

Tệp này phục vụ **bài thử biên dịch bytecode**; không được dùng làm thư viện chạy thực tế. Trên một số cấu hình compiler/modules, khai báo những package trùng với các JDK modules có thể bị chặn ngay khi biên dịch. Trong bài này `java.demo` là tên thử nghiệm không thuộc module nền tảng chuẩn, và lệnh bên dưới đã được kiểm tra với `javac --release 17` trên JDK 21.

### 4.3. Loader chính và kiểm tra exception

Tệp **`src/GuardDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;

public final class GuardDemo {
    static final class ByteLoader extends ClassLoader {
        ByteLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        ByteLoader loader = new ByteLoader(
                GuardDemo.class.getClassLoader());

        byte[] allowed = Files.readAllBytes(
                Path.of(args[0], "sample", "Allowed.class"));

        Class<?> ordinary =
                loader.define("sample.Allowed", allowed);

        System.out.println("Normal definition: "
                + ordinary.getName());
        System.out.println("Custom defining loader: "
                + (ordinary.getClassLoader() == loader));

        Class<?> core = loader.loadClass("java.lang.String");
        System.out.println("Delegated String: "
                + (core == String.class));
        System.out.println("String bootstrap: "
                + (core.getClassLoader() == null));

        byte[] reserved = Files.readAllBytes(
                Path.of(args[0], "java", "demo", "Reserved.class"));

        try {
            loader.define("java.demo.Reserved", reserved);
            System.out.println("Unexpected reserved definition");
        } catch (SecurityException expected) {
            System.out.println(
                    "Reserved definition: SecurityException");
        }
    }
}
```

`ByteLoader` subclass `ClassLoader` chỉ để có quyền gọi phương thức protected `defineClass`. Method `define` có quyền truy cập package-private và được `GuardDemo` gọi từ cùng top-level/nest context; chúng cùng file nguồn, nên ví dụ hợp lệ.

### 4.4. Chạy trên Java 17+

Từ thư mục `guard-demo`, dùng JDK 17+:

```bash
mkdir -p out

javac --release 17 -d out \
  src/sample/Allowed.java \
  src/java/demo/Reserved.java \
  src/GuardDemo.java

java -cp out GuardDemo out
```

Trong **PowerShell**, tạo thư mục `out` và dùng các lệnh một dòng:

```powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac --release 17 -d out src/sample/Allowed.java src/java/demo/Reserved.java src/GuardDemo.java
java -cp out GuardDemo out
```

**Đầu ra đã kiểm thử bằng OpenJDK 21 với mục tiêu `--release 17`:**

```text
Normal definition: sample.Allowed
Custom defining loader: true
Delegated String: true
String bootstrap: true
Reserved definition: SecurityException
```

### 4.5. Giải thích chính xác kết quả

1. **Normal definition:** `ByteLoader#define("sample.Allowed", bytes)` được phép vì tên thuộc namespace của ứng dụng, class file hợp lệ và cùng loader chưa định nghĩa tên đó.
2. **Custom defining loader:** `ordinary.getClassLoader() == loader` là `true`. Đây là bằng chứng class `sample.Allowed` được loader tự định nghĩa, không chỉ khởi phát việc nạp rồi ủy quyền.
3. **Delegated String:** `loader.loadClass("java.lang.String")` kế thừa phương thức mặc định với parent delegation. Loader tìm `String` ở đường parent/bootstrap thay vì gọi `defineClass` để tạo bản riêng.
4. **String bootstrap:** trong JDK tiêu chuẩn, defining loader của `java.lang.String` là bootstrap; API `getClassLoader()` trả `null` cho trường hợp này.
5. **Reserved definition:** bytes của `java.demo.Reserved` đã tồn tại và tên truyền vào **khớp binary name** trong class file, nhưng loader ứng dụng tùy chỉnh vẫn bị chặn bởi quy tắc `java.*`; `defineClass` ném `SecurityException`.

Tất cả dòng stdout cố định ở trên phù hợp với môi trường JDK chuẩn nêu trong bài thử. Những runtime Java không chuẩn hoặc custom VM có thể có cơ chế triển khai riêng; khi viết code production, vẫn dựa trên hợp đồng Java SE thay vì so sánh nguyên văn thông điệp exception.

**Không dùng lệnh `java -cp out java.demo.Reserved` để “chạy” class bị bảo vệ**: ngoài vấn đề launcher/class loading, class test cũng **không có `main`**. Mục tiêu duy nhất là minh họa `defineClass` trên custom loader.

## 5. Không phải compile thành công là class có thể chạy

Đây là khác biệt thường gây nhầm:

```text
.java source
    |
    v
javac --release 17
    |
    +--> tạo .class có binary name java.demo.Reserved
    |
    v
runtime loader của ứng dụng
    |
    +--> defineClass("java.demo.Reserved", bytes, ...)
                |
                v
         SecurityException
```

`javac` là bước **biên dịch source thành class file**, còn `defineClass` là bước runtime **định nghĩa class trong một loader**. Compiler có thể nhận một source hợp lệ về mặt cú pháp/tên class, nhưng JVM/JDK vẫn áp dụng runtime restrictions độc lập. Những package đang thuộc một named module cũng có thể bị compiler/module tools ngăn từ trước; không nên suy diễn rằng **mọi** `package java.*` đều compile được trên mọi cấu hình.

### Vì sao cứ chuyển class file vào JAR khác không đủ?

Đưa `java/demo/Reserved.class` vào một JAR được thêm trên classpath **không cấp thêm quyền defining loader**:

```text
app.jar / plugin.jar
    └── java/demo/Reserved.class

Application/Custom ClassLoader
    └── attempt define java.demo.Reserved
            └── SecurityException
```

Resource có thể tồn tại trong JAR, nhưng khả năng tìm thấy bytes và quyền định nghĩa runtime class là hai điều kiện khác nhau.

## 6. Phân biệt loader được phép và loader của ứng dụng

Java SE 17 JavaDoc mô tả: nếu binary name bắt đầu `java.`, định nghĩa class chỉ được thực hiện bởi **platform class loader hoặc các loader tổ tiên của nó**.

Trong cấu trúc JDK 17 thường gặp:

```text
Application/System loader
       |
       v parent
Platform loader
       |
       v parent
Bootstrap loader (getClassLoader() thường là null)
```

- **Bootstrap loader** xử lý nhiều class thiết yếu như `java.lang.String`, `java.lang.Object`.
- **Platform loader** phụ trách tập class/module nền tảng được JDK bố trí cho loader này.
- **Application loader** nạp code ứng dụng trong classpath/module configuration thông thường.

Nói **“chỉ bootstrap mới có quyền với toàn bộ `java.*`”** là **không chính xác** theo phát biểu JavaDoc Java 17, vì còn có **platform loader hoặc ancestors** trong quy tắc cho phép. Nhưng điều đó **không cho phép một ứng dụng tự tạo subclass có parent là platform loader rồi được hưởng quyền định nghĩa `java.*`**. Loader vừa tạo là **child**, không phải platform loader hay một ancestor của nó.

Một class được **định nghĩa bởi platform loader** không đồng nghĩa ứng dụng có quyền gọi `protected defineClass` trên đối tượng platform loader. Quyền truy cập protected, module/package access, và cơ chế runtime đều vẫn áp dụng.

### Calling loader khác defining loader

Giả sử:

```java
ClassLoader app = ClassLoader.getSystemClassLoader();
Class<?> stringType = app.loadClass("java.lang.String");
```

Đây là snippet hoàn chỉnh về cú pháp trong một phương thức. `app` bắt đầu yêu cầu class, nhưng `stringType.getClassLoader()` trên JDK tiêu chuẩn trả `null` (bootstrap). Danh tính runtime class gắn với loader đã **định nghĩa**, không phải biến `app`.

Đừng kết luận `String` đã được ứng dụng định nghĩa vì lệnh `app.loadClass` trả thành công.

## 7. Giới hạn java.* không phải toàn bộ bảo vệ package

Ngoài kiểm tra tên `java.`, việc định nghĩa class chịu nhiều ràng buộc khác:

| Cơ chế | Nó bảo vệ điều gì? | Lỗi/biểu hiện có thể gặp |
|---|---|---|
| **Reserved `java.*` namespace** | Loader ngoài platform/ancestors không tự định nghĩa class `java.*` | `SecurityException` |
| **Class binary name match** | Tên truyền vào `defineClass` phù hợp với bytes | `NoClassDefFoundError` |
| **Class-file validation** | Dữ liệu đúng định dạng class file và version | `ClassFormatError`, `UnsupportedClassVersionError` |
| **Bytecode verification** | Quy tắc stack, types, control flow, v.v. | `VerifyError` |
| **Package signer consistency** | Các class trong cùng package của loader có tập chứng chỉ ký phù hợp | `SecurityException` |
| **Runtime package identity** | Quyền package-private dựa trên package name **và defining loader** | Có thể `IllegalAccessError` |
| **Loading constraints** | Nhất quán type identity ở những chữ ký/quan hệ liên loader | `LinkageError` |
| **JPMS module rules** | Module membership, readability, exports/opens | Lỗi access/linking hoặc lỗi build/module resolution |
| **Package sealing khi loader/JAR áp dụng** | Tính nhất quán nguồn code đối với sealed package | Lỗi sealing riêng theo loader/tool |

Không nên phân loại mọi exception `SecurityException` thành “đụng `java.*`”. Ví dụ mismatch signer certificates có thể dùng **cùng exception class** nhưng root cause khác.

Cũng không nên coi `ClassNotFoundException` đồng nghĩa `SecurityException`: thứ nhất nói về **không tìm được** định nghĩa qua đường lookup, thứ hai trong bài liên quan **không được phép tự định nghĩa** class trong namespace dành riêng.

## 8. Vì sao definePackage không giúp thay đổi giới hạn?

`ClassLoader#definePackage` quản lý **metadata package** của loader, như specification title, implementation version, vendor, sealing URL và các thuộc tính liên quan.

Ví dụ abstract:

```java
definePackage(
        "com.acme.plugin",
        "Plugin API", "1.0", "Acme",
        "Plugin Runtime", "1.0", "Acme",
        null);
```

Đây là đoạn minh họa bên trong subclass `ClassLoader`, không phải một chương trình độc lập.

**Định nghĩa metadata package** là hoạt động khác với **định nghĩa runtime class**. Không thể cho rằng gọi `definePackage("java.demo", ...)` sẽ cấp cho custom loader quyền gọi `defineClass("java.demo.Reserved", ...)`. `ClassLoader#defineClass` vẫn phải thực hiện các kiểm tra namespace của nó.

Package Java cũng không phải một “folder toàn cục”. Trong JVM, **runtime package** của class thường xác định bởi:

```text
(package name, defining class loader)
```

Hai class cùng `package com.acme;` nhưng được các loader khác nhau định nghĩa không tự động dùng chung quyền package-private. Đây là một lý do bổ sung để tránh tùy tiện đóng gói lại core/sharing classes ở nhiều loader.

## 9. Named modules, JDK runtime image và package java.*

Từ Java 9, JDK dùng **Java Platform Module System (JPMS)**, với những module như `java.base`, `java.logging`, `java.sql`. Một số API có package `java.*` được bố trí ở các module và loader nền tảng khác nhau theo cấu hình runtime.

Điểm cần phân biệt:

- **`package java.*`**: tên namespace ở mức Java binary name.
- **`module java.base`**: một named module trong hệ thống module của Java.
- **`java.*` class-definition restriction**: kiểm tra của `defineClass` theo loader được phép.
- **Module accessibility**: lớp/module có được đọc/truy cập hay không qua `requires`, `exports`, `opens` và các quy tắc khác.
- **Runtime image resource `jrt:`**: cách JDK hiện đại cung cấp một số tài nguyên module, không phải `File` thông thường.

Các cơ chế này có liên quan nhưng **không thay thế cho nhau**. Ví dụ dùng một lựa chọn launcher để mở package cho reflection (khi hợp lệ) không có nghĩa ứng dụng tự dưng được quyền **định nghĩa class mới trong `java.*` bằng loader riêng**.

Nếu cần mở rộng chức năng Java, chọn package ứng dụng riêng và API/plugin extension points được tài liệu hóa. Nếu cần điều chỉnh hành vi JDK trong thử nghiệm được kiểm soát, đó là một chủ đề chuyên biệt về tools/modules/instrumentation với giới hạn riêng; **không nên lấy việc định nghĩa thêm class trong `java.*` bằng application loader làm giải pháp**.

### Không đồng nhất tên java.*, javax.*, jdk.*

Một số APIs tiêu chuẩn có package `javax.*`, một số JDK implementation APIs dùng `jdk.*` hoặc `sun.*`. Quy tắc `defineClass` dành riêng cho tên bắt đầu **`java.`** được mô tả rõ ràng; không được tự mở rộng cùng chính sách cụ thể ấy sang mọi package khác chỉ dựa trên tiền tố.

Tuy nhiên, **không nên đặt mã ứng dụng mới dưới `javax.*`, `jdk.*`, `sun.*`** để “tránh rule java.*”: các namespace đó có thể do nền tảng/framework sở hữu, bị ràng buộc bởi modules, tránh được một kiểm tra cũng không tạo ra contract tương thích hay ổn định.

## 10. Parent delegation và bảo vệ các lớp lõi

`ClassLoader.loadClass` mặc định hoạt động theo nguyên tắc parent-first:

```text
ChildLoader.loadClass("java.lang.String")
    |
    +-- kiểm tra class đã được loader ghi nhận
    |
    +-- hỏi parent loader
          |
          +-- tiếp tục lên platform/bootstrap
          |
          +-- String đã tồn tại trong runtime
    |
    +-- trả Class<?> của String từ runtime
```

Đối với lớp JDK, đây là **mục tiêu**: tất cả modules, application components và plugins dùng chung những runtime types nền tảng mà chúng cần giao tiếp.

Một loader **child-first** được viết cho plugin có thể cố ý ưu tiên tự nạp `com.acme.private.*`, nhưng nên **giữ parent-first** cho các runtime/platform types và shared API.

Ví dụ chính sách khái quát:

```text
java.*                         -> parent/platform only
javax.* / jdk.* / sun.*        -> theo contract/runtime/module phù hợp
shared.api.*                   -> parent first
plugins.acme.internal.*        -> child first nếu thật sự cần isolation
other names                    -> parent first mặc định
```

Đây là **chính sách kiến trúc minh họa**, không phải đoạn code hoàn chỉnh hay bảng quy định tất cả packages. Đối với Java 17+, không nên tự định nghĩa `java.*` từ child ngay cả khi policy child-first; tốt hơn phân vùng trách nhiệm rõ ngay từ thiết kế.

## 11. Điều gì xảy ra khi cố phá quy tắc bằng custom loader?

Một loader có thể override `loadClass` hoặc `findClass` và đọc bytes từ bất kỳ nguồn nào. Tuy nhiên, cuối cùng nếu muốn biến bytes thành runtime class thông thường, nó vẫn phải dùng một cơ chế **định nghĩa class** chịu quy tắc JVM/JDK, trong đó có namespace restriction.

Ví dụ giả mã:

```text
findClass("java.demo.Reserved"):
    bytes = read("java/demo/Reserved.class")
    return defineClass("java.demo.Reserved", bytes, 0, bytes.length)

Kết quả với ordinary application-defined loader:
    SecurityException
```

Không nên bắt `SecurityException` rồi giả vờ rằng đó chỉ là “class không có trong file”. Xử lý và log nguyên nhân thật sự. Nếu một loader đặc biệt cần fallback parent, fallback chỉ đúng khi parent thực sự cung cấp **class tiêu chuẩn đã biết** — không phải tìm một bản `java.*` tùy biến để thay thế.

Các đường vòng thiếu kiểm soát còn có thể tạo hệ thống khó kiểm tra, không tương thích giữa JDK releases hoặc vi phạm những giả định an toàn của platform. Thiết kế vững chắc là **đổi tên package của class ứng dụng** và dùng API Java chuẩn, thay vì cố làm cho loader ứng dụng sở hữu namespace nền tảng.

### Vì sao exception không phụ thuộc SecurityManager?

Tên `SecurityException` có thể khiến người học nghĩ lỗi chỉ xảy ra khi `SecurityManager` được bật. Trong trường hợp `ClassLoader#defineClass`, **quy tắc package `java.*` được áp dụng trực tiếp** bởi API/implementation. Không cần một SecurityManager do ứng dụng cài riêng mới có exception này.

Đây là phân biệt quan trọng trên Java hiện đại, khi mô hình SecurityManager truyền thống đã bị giới hạn/deprecated và không nên xem là công cụ bảo vệ plugin thông thường.

## 12. Lỗi phổ biến và cách chẩn đoán

### 12.1. “Prohibited package name: java.demo”

Một exception có thể có thông báo tương tự:

```text
java.lang.SecurityException: Prohibited package name: java.demo
```

Đây là **mẫu thông điệp thường gặp**, không phải contract để parse chuỗi; nội dung có thể khác theo JDK. Kiểm tra:

1. `name` truyền vào `defineClass` là gì?
2. Có bắt đầu bằng `java.` không?
3. Loader thực sự gọi `defineClass` là loader nào?
4. Bạn đang **tự định nghĩa class** hay chỉ gọi `loadClass` để dùng class nền tảng?
5. Class file có bị đưa nhầm vào package `java.*` do code generator, bytecode rewriting hoặc cấu hình shading/relocation không?

**Cách sửa:** dùng package thuộc ứng dụng, chẳng hạn `com.example.plugin`. Không dùng loader tùy biến để định nghĩa class với namespace dành riêng.

### 12.2. “Class file có sẵn nhưng vẫn không load được”

Tồn tại `java/demo/Reserved.class` trên classpath/JAR không có nghĩa application loader được định nghĩa nó. Tìm resource bằng `getResource` và định nghĩa class bằng `defineClass` là hai hoạt động khác nhau.

Nếu class nằm trong một named module của JDK hoặc runtime image, hãy sử dụng module/public API phù hợp thay vì sao chép file rồi định nghĩa lại từ application loader.

### 12.3. “Mình override loadClass rồi, sao vẫn bị chặn?”

Bởi `loadClass` là chiến lược **tìm và lựa chọn**, còn `defineClass` có **ràng buộc namespace**. Thay thứ tự parent/child không tạo thêm quyền định nghĩa những tên bị hạn chế.

Nếu chỉ muốn dùng `java.lang.String`, hãy ủy quyền parent. Nếu muốn triển khai logic ứng dụng tùy biến, đặt class ở package riêng.

### 12.4. “SecurityException” nhưng không có tên java.*

Một nguyên nhân khác của `defineClass` có thể là signer certificate set trong một package không nhất quán, hoặc chính sách khác của môi trường. Kiểm tra toàn bộ stack trace và nguyên nhân; không đổi package tùy tiện khi nguyên nhân thật là ký số hoặc sealing.

### 12.5. “java.lang.String cannot be cast to java.lang.String”

Thông điệp cùng tên/cast sai (thường với các class ứng dụng, không phải String chuẩn) có thể do **hai defining loaders** tạo hai runtime types khác nhau. Nhưng trường hợp namespace `java.*` được bảo vệ thường chặn kiểu giả mạo trước khi tạo class, nên cần phân biệt lỗi class identity của thư viện với lỗi cấm package `java.*`.

### 12.6. Có được dùng tên javafoo.* không?

Riêng phép kiểm tra `name.startsWith("java.")` sẽ không coi `javafoo.*` là `java.*`. Tuy nhiên, việc đặt tên package kiểu dễ gây nhầm với JDK không tốt cho maintainability. Package ứng dụng nên dùng tên miền đảo ngược, ví dụ `org.example.learning`.

## 13. So sánh với các ràng buộc bảo vệ khác

| Trường hợp | Vấn đề chính | Điều chỉnh phù hợp |
|---|---|---|
| Plugin định nghĩa `java.demo.Plugin` qua custom loader | Reserved namespace `java.*` | Đổi thành `com.acme.plugin.Plugin` |
| Hai plugin tự định nghĩa hai bản `shared.api.Plugin` | Runtime type identity khác nhau | Đặt shared API ở parent và delegate |
| Plugin dùng `package demo;` nhưng không truy cập được package-private method ở app | Runtime package gồm package name + defining loader | Dùng API public/chia sẻ đúng loader |
| Class hợp lệ nhưng bytes khác tên `defineClass(name, ...)` | Binary name mismatch | Sửa name/source bytes đồng nhất |
| Class file từ JDK mới hơn runtime | Version mismatch | Dùng JDK phù hợp hoặc `javac --release` |
| Provider class không thấy do loader/plugin classpath | Lookup/source configuration | Chọn loader/classpath/module layer đúng |
| Module không `exports`/`opens` package cần dùng | JPMS access rule | Thiết kế module descriptors và access hợp lệ |
| Khởi tạo static class ném lỗi | Initialization failure | Sửa nguyên nhân initializer, không chỉ đổi loader |

Lưu ý: **chuyển package để thoát giới hạn `java.*` chỉ giải quyết vấn đề đặt tên bị cấm**, không sửa các lỗi kiểu, dependency, module hoặc bytecode khác nếu chúng cùng tồn tại.

## 14. Quy tắc thiết kế thư viện và plugin tránh xung đột namespace

1. **Dùng namespace bạn sở hữu:** `com.yourcompany.project` hoặc `org.yourteam.module`.
2. **Không tạo class ứng dụng trong `java.*`**, kể cả class thử nghiệm được code generator sinh ra hoặc source chuyển đổi.
3. **Dùng public JDK APIs** để tương tác với nền tảng; tránh bắt chước class tiêu chuẩn bằng tên nhị phân trùng.
4. **Giữ parent delegation** với platform types và shared contracts nếu không có lý do kiến trúc được kiểm tra nghiêm túc.
5. **Override `findClass` trước**, chỉ override `loadClass` khi cần namespace isolation đặc biệt và hiểu đầy đủ locking/linking.
6. **Đưa shared API vào loader chung**, để host/plugin giao tiếp qua một runtime interface.
7. **Không nhầm compile-time với runtime:** JVM loader có thể áp dụng kiểm tra mà `javac` không gặp ở một cấu hình source cụ thể.
8. **Kiểm tra generated/relocated bytecode names** trong build output/JAR; không chỉ nhìn tên source.
9. **Không coi ClassLoader là sandbox:** mã không đáng tin nên được cô lập bằng những cơ chế bảo mật phù hợp hơn ở hệ điều hành/process/container.
10. **Kiểm thử trên JDK thực tế** mà sản phẩm dùng, kể cả Java version, module path, custom loaders và các bytecode generators.

### Khi xây loader riêng, nên lưu những log gì?

Đối với các lỗi dạng này, log nên có:

```text
requested binary name
loader implementation/class
defining/parent loader identity
bytecode source (JAR/URI/provider)
root exception class and cause
JDK version and module context (nếu liên quan)
```

Tránh log toàn bộ bytecode hoặc đường dẫn có dữ liệu nhạy cảm. Thông báo `SecurityException` và tên package thường đủ để chỉ ra lỗi `java.*`, nhưng vẫn cần trace khi có nhiều loader.

## 15. Câu hỏi tự kiểm tra

**1. `child.loadClass("java.lang.String")` có bị cấm như `child.defineClass("java.lang.String", ...)` không?** Không. `loadClass` mặc định ủy quyền parent và có thể nhận class có sẵn; `defineClass` đòi tự tạo runtime class.

**2. `java.demo.Reserved` không nằm trong JDK tiêu chuẩn thì application loader có thể định nghĩa không?** Không theo quy tắc `defineClass`: tên bắt đầu bằng `java.` là yếu tố giới hạn, không chỉ việc tên đã được JDK dùng hay chưa.

**3. Java SE 17 JavaDoc nói “chỉ bootstrap loader” đúng không?** Không hoàn toàn. Nó nêu **platform class loader hoặc các ancestors**. Application/custom child loader không được hưởng quyền đó.

**4. Đổi parent của custom loader thành platform loader có khiến child được phép `defineClass("java.demo.Reserved", ...)` không?** Không. Child không phải platform loader hoặc ancestor của nó.

**5. Compile class source trong `java.demo` thành công có đảm bảo chạy được từ classpath không?** Không. Biên dịch và runtime definition là hai bước với kiểm tra khác nhau.

**6. `getResource("java/demo/Reserved.class")` thấy bytecode có nghĩa là loader được định nghĩa class không?** Không. URL/resource lookup không cấp quyền định nghĩa runtime class.

**7. Vì sao `SecurityException` chưa chắc liên quan `java.*`?** `defineClass` còn có kiểm tra signer certificates cùng package và môi trường có thể có quy tắc khác.

**8. `definePackage("java.demo", ...)` có cấp quyền để `defineClass` tên `java.demo.Reserved` không?** Không. Package metadata và class definition restriction là hai vấn đề độc lập.

**9. Có nên đổi `java.demo.Widget` thành `javax.demo.Widget` để né `java.*` không?** Không nên. Hãy đặt code trong namespace riêng, vì các package platform khác cũng có ownership và constraints.

**10. Nếu muốn nạp plugin implementation từ bytes, giải pháp cơ bản là gì?** Đặt class ở package của ứng dụng, giữ shared API ở parent, custom loader override `findClass` và dùng `defineClass` đúng binary name/valid bytes, đồng thời tuân thủ module/package constraints.

## 16. Nguồn tham khảo chính thức

- **Java SE 17 API — `ClassLoader`**, đặc biệt `defineClass(String, byte[], int, int)` và overload nhận `ProtectionDomain` (định nghĩa `java.*` và `SecurityException`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 API — `Class#getClassLoader`** (defining loader và bootstrap `null`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **JVMS §5.3 — Creation of Classes and Interfaces** (class identity: binary name + defining loader): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS §5.4 — Linking, Verification and Access Control** (các kiểm tra runtime bổ sung): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- **JLS §7 — Packages and Modules** (khái niệm Java packages và JPMS): https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html

**Ghi nhớ:** **Ứng dụng được dùng các lớp `java.*` bằng cách để loader phù hợp của nền tảng cung cấp chúng, nhưng custom/application loader không được tự định nghĩa lớp `java.*`.** Hãy phân biệt `loadClass` với `defineClass`, dùng package sở hữu bởi ứng dụng và thiết kế parent delegation/shared API rõ ràng thay vì cố tự tạo bản sao của lớp/namespaces nền tảng.
