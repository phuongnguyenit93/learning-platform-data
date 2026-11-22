# Nạp tài nguyên từ module bằng Class, ClassLoader và Module trong Java

Khi học **classloader** ở Java 9+ (bao gồm Java 17), không thể luôn áp dụng tư duy “tài nguyên ở trong JAR/classpath thì bất kỳ class loader nào tìm thấy cũng đọc được”. Với **Java Platform Module System (JPMS)**, resource có thể thuộc một **named module**, và việc tìm/đọc resource chịu các quy tắc **module encapsulation**.

Ba API dễ bị nhầm:

- `SomeClass.class.getResource(...)` và `SomeClass.class.getResourceAsStream(...)`: tìm resource **gắn với một Class**, hiểu tên tương đối theo package và, khi class thuộc named module, tìm trong **chính module đó**.
- `someClassLoader.getResource(...)`, `getResources(...)` và `getResourceAsStream(...)`: tìm resource qua **class loader**, với quy tắc delegation và ràng buộc nghiêm ngặt khi resource nằm trong package của **named module**.
- `someModule.getResourceAsStream(...)`: tìm resource **được sở hữu bởi một Module cụ thể**, đồng thời kiểm tra package có mở cho **module của caller** hay không.

**Điểm trọng tâm:** Một resource tồn tại trong module và có thể đọc bằng `Class.getResourceAsStream` hoặc `Module.getResourceAsStream` từ code **bên trong module**, nhưng vẫn có thể trả **`null`** khi code gọi `ClassLoader.getResourceAsStream` — ngay cả khi đó là cùng defining class loader. `exports` package chứa public types **không tương đương `opens` để cho phép truy cập non-`.class` resources**.

## 1. Ôn lại: resource, classpath và module

Resource là dữ liệu được ứng dụng đóng gói cạnh code: `.properties`, `.json`, `.xml`, ảnh, template, schema, `META-INF/services` hoặc thậm chí file `.class`.

Ví dụ một ứng dụng chạy trên classpath:

```text
out/
└── demo/
    ├── Main.class
    └── config.properties
```

Các đoạn mã:

```java
URL a = Main.class.getResource("config.properties");
URL b = Main.class.getClassLoader()
        .getResource("demo/config.properties");
```

có thể trả về cùng resource nếu resource nằm đúng đường tìm kiếm. Nhưng hai API dùng **cách diễn giải tên khác nhau**; và nếu `Main` nằm trong **named module** thì `Class` có thể định vị resource trong module bằng cơ chế khác với lookup classloader công khai.

### Module trong runtime là gì?

`java.lang.Module` biểu diễn một module runtime, named hoặc unnamed. Lấy qua:

```java
Module m = Main.class.getModule();
System.out.println(m.getName());
System.out.println(m.isNamed());
```

Đây là snippet minh họa, cần lớp `Main` trong phạm vi code. Class trên classpath thường thuộc **unnamed module** của defining loader. Class trong module path có `module-info.class` được resolved vào **named module**, ví dụ `com.acme.core`.

**Named module không phải class loader.** Một class loader có thể định nghĩa classes của nhiều named modules; chỉ biết defining loader không đủ để chọn module sở hữu một resource. Đây là một lý do `Module.getResourceAsStream` và `Class.getResource...` tồn tại.

## 2. So sánh chính xác ba nhóm API

| API | Đầu vào | Phạm vi tìm kiếm | Kết quả |
|---|---|---|---|
| `SomeClass.class.getResource("a.txt")` | Tên tương đối package | Resource gắn với `SomeClass`; trong named module tìm thuộc module của class | `URL` hoặc `null` |
| `SomeClass.class.getResource("/pkg/a.txt")` | Tên tuyệt đối từ root | Tương tự, nhưng bỏ `/` đầu trước lookup | `URL` hoặc `null` |
| `SomeClass.class.getResourceAsStream(...)` | Quy tắc tên như `Class.getResource` | Như trên, trả stream đọc bytes | `InputStream` hoặc `null` |
| `loader.getResource("pkg/a.txt")` | Tên resource từ root, **không có `/` đầu** | Parent/loader resource lookup; named modules bị encapsulation | `URL` hoặc `null` |
| `loader.getResources("pkg/a.txt")` | Tên resource từ root | Có thể tìm **nhiều** resources từ loader hierarchy/modules theo contract | `Enumeration<URL>` |
| `loader.getResourceAsStream("pkg/a.txt")` | Tên resource từ root | Luồng đọc qua loader lookup | `InputStream` hoặc `null` |
| `module.getResourceAsStream("pkg/a.txt")` | Tên resource từ root (có thể có `/` đầu) | **Đúng một Module**; áp dụng kiểm tra open theo caller module | `InputStream` hoặc `null` |

Cần tránh hai suy luận sai:

1. `Class.getResourceAsStream` **không chỉ đơn giản** luôn lấy `clazz.getClassLoader().getResourceAsStream` trong Java 17. Với class thuộc named module, JavaDoc mô tả nó sử dụng **module-aware lookup** và kiểm tra khả năng truy cập theo **module của caller**.
2. `ClassLoader.getResource` **không tự bỏ qua JPMS** chỉ vì bạn có đối tượng loader. Với non-`.class` resource nằm trong package của named module, API ClassLoader yêu cầu package đó được **mở vô điều kiện (opened unconditionally)**. Tính chất này áp dụng cả khi code gọi cùng module; ClassLoader API không cấp quyền dựa trên caller module giống hai API còn lại.

Dòng giải thích trong dấu ngoặc góc ở trên là diễn giải, không phải cú pháp Java.

## 3. Quy tắc tên resource: Class so với ClassLoader/Module

Giả sử module chứa:

```text
demo/assets/internal/
    Inside.class
    secret.txt
```

Với class `demo.assets.internal.Inside`:

```java
Inside.class.getResource("secret.txt");
Inside.class.getResource("/demo/assets/internal/secret.txt");
Inside.class.getResourceAsStream("secret.txt");
```

Đều nhắm tới `demo/assets/internal/secret.txt` theo quy tắc tên.

- Đối với **`Class.getResource`** và `Class.getResourceAsStream`: tên bắt đầu bằng `/` được hiểu từ root; tên không có `/` đầu được đặt tương đối với package của class.
- Đối với **`ClassLoader.getResource`**: truyền `"demo/assets/internal/secret.txt"`, **không** có `/` đầu; tên ở dạng path với dấu `/`.
- Đối với **`Module.getResourceAsStream`**: thường truyền tên từ root như `"demo/assets/internal/secret.txt"`; API chấp nhận dấu `/` đầu và sẽ bỏ nó trước lookup.

Ví dụ:

```java
String name = "demo/assets/internal/secret.txt";
ClassLoader cl = Inside.class.getClassLoader();
Module mod = Inside.class.getModule();

InputStream a = Inside.class.getResourceAsStream("secret.txt");
InputStream b = cl.getResourceAsStream(name);
InputStream c = mod.getResourceAsStream(name);
```

Đây là **đoạn minh họa bên trong method**, cần import `java.io.InputStream`, class `Inside` và xử lý `IOException` cho lời gọi trên `Module`. **Không suy ra `a`, `b`, `c` bằng nhau**: nếu resource nằm trong package encapsulated của named module, `a` và `c` có thể đọc được từ code trong module còn `b` là `null`.

**Không dùng `ClassLoader.loadClass("demo/assets/internal/Inside.class")`.** `loadClass` nhận **binary class name** với dấu chấm `demo.assets.internal.Inside`, không phải resource path.

## 4. JPMS encapsulation áp dụng cho tài nguyên thế nào?

Với resource nằm trong **named module**, Java SE 17 `Module.getResourceAsStream` mô tả:

1. Nếu tên resource kết thúc bằng **`.class`**, resource đó **không bị encapsulate bởi quy tắc này**.
2. JVM/API suy ra package name từ phần path trước dấu `/` cuối, đổi các `/` thành dấu `.`.
3. Nếu package name ấy **thực sự là một package trong module**, non-`.class` resource chỉ được đọc từ một module caller khác nếu package được **mở (`opens`)** cho module caller đó.
4. Nếu path không tương ứng package thực tế của module, resource **không bị encapsulated theo quy tắc package**. Ví dụ `META-INF/MANIFEST.MF` không thuộc một Java package hợp lệ.
5. Resource không có, không thể truy cập hoặc bị từ chối có thể dẫn tới `null`. Với API `Module.getResourceAsStream`, lỗi I/O có thể ném `IOException`.

### Exports không phải opens

`module-info.java`:

```java
module demo.assets {
    exports demo.assets.api;
}
```

cho phép module khác **sử dụng public types** trong package `demo.assets.api` theo JPMS access rules. Nó **không** đồng nghĩa package `demo.assets.internal` được mở để các module khác đọc `secret.txt`.

Các cách khai báo:

```java
// Ví dụ từng kiểu declaration, không ghép tất cả để áp dụng cùng lúc:
exports demo.assets.api;
opens demo.assets.internal;
opens demo.assets.internal to demo.consumer;
```

Đây là **những dòng minh họa thuộc module declaration**, không phải Java code đứng độc lập.

- `exports pkg;`: công bố public API types theo quy tắc module access; **không đủ** để non-`.class` resource được ClassLoader tìm thấy.
- `opens pkg;`: mở package **vô điều kiện** cho mọi module; ClassLoader có thể tìm non-`.class` resources trong package này nếu các điều kiện lookup khác thỏa.
- `opens pkg to some.module;`: **qualified opens**, mở cho một tập module được nêu; `Module.getResourceAsStream` và `Class.getResourceAsStream` từ caller module được mở có thể thành công, nhưng **ClassLoader lookup vẫn yêu cầu unconditional opens**.
- `open module demo.assets { ... }`: khai báo open module với các packages của nó được mở vô điều kiện; tác động rộng hơn và không nên dùng chỉ để xử lý một file config.
- `--add-opens module/package=target` khi khởi chạy: có thể bổ sung qualified opens có kiểm soát; **không biến qualified opens thành unconditional opens**.

**Quy tắc quan trọng nhất:** Với `ClassLoader.getResource`/`getResources`/`getResourceAsStream`, ngoại lệ dành cho resource kết thúc bằng `.class`; các non-`.class` resources trong package của named module phải thuộc package **opened unconditionally**, ngay cả khi mã gọi `ClassLoader` nằm trong chính module đó. Đây là chi tiết dễ bị bỏ qua khi di chuyển project từ classpath sang module path.

## 5. Ví dụ Java 17+ chạy được: cùng module, ba API, ba kết quả khác nhau

Bài thử có hai phía:

- **Named module `demo.assets`** sở hữu một resource riêng `demo/assets/internal/secret.txt` trong package **không exports và không opens**.
- **Ứng dụng classpath/unnamed module** gọi API công khai `demo.assets.api.Api` và thử đọc resource của module từ bên ngoài.

Một file metadata ở `META-INF/demo.info` được đặt **ngoài package** để đối chiếu: nó không bị encapsulate vì tên `META-INF` không phải package Java.

### 5.1. Cấu trúc tệp

```text
module-resource-demo/
├── src/
│   └── demo.assets/
│       ├── module-info.java
│       └── demo/
│           └── assets/
│               ├── api/
│               │   └── Api.java
│               └── internal/
│                   └── Inside.java
├── resources/
│   └── demo.assets/
│       ├── demo/
│       │   └── assets/
│       │       └── internal/
│       │           └── secret.txt
│       └── META-INF/
│           └── demo.info
└── src-app/
    └── DemoMain.java
```

### 5.2. Module descriptor

Tệp **`src/demo.assets/module-info.java`**:

```java
module demo.assets {
    exports demo.assets.api;
}
```

Chỉ export API package để caller ngoài module có thể gọi `Api.check()`. Package `demo.assets.internal` là package nội bộ, không có `exports` hay `opens`.

### 5.3. API công khai của module

Tệp **`src/demo.assets/demo/assets/api/Api.java`**:

```java
package demo.assets.api;

import demo.assets.internal.Inside;

public final class Api {
    public static void check() throws Exception {
        Inside.check();
    }
}
```

`Api` được export qua `module-info.java`. Dù package `demo.assets.internal` không export ra ngoài, **code bên trong cùng module** như `Api` có thể tham chiếu `Inside` vì chúng cùng module và `Inside` được khai báo public.

### 5.4. Code đọc tài nguyên bên trong module

Tệp **`src/demo.assets/demo/assets/internal/Inside.java`**:

```java
package demo.assets.internal;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Inside {
    private static final String NAME =
            "demo/assets/internal/secret.txt";

    private static String value(InputStream in) throws Exception {
        if (in == null) {
            return "(null)";
        }
        try (in) {
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void check() throws Exception {
        Module m = Inside.class.getModule();

        System.out.println("inside Class: "
                + value(Inside.class.getResourceAsStream("secret.txt")));

        System.out.println("inside ClassLoader: "
                + value(Inside.class.getClassLoader()
                        .getResourceAsStream(NAME)));

        System.out.println("inside Module: "
                + value(m.getResourceAsStream(NAME)));

        System.out.println("module named: " + m.isNamed());
    }
}
```

Trong cùng module:

- `Inside.class.getResourceAsStream("secret.txt")` biết class thuộc module nào và có **module-aware access** cho package của chính module.
- `Inside.class.getClassLoader().getResourceAsStream(NAME)` dùng rule của **ClassLoader**, nên resource non-`.class` trong internal package chưa mở vô điều kiện **không được trả về**.
- `m.getResourceAsStream(NAME)` gọi từ code `Inside` thuộc **cùng module**, nên được truy cập nội dung nếu resource tồn tại.

### 5.5. Code bên ngoài module

Tệp **`src-app/DemoMain.java`**:

```java
import demo.assets.api.Api;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class DemoMain {
    private static String value(InputStream in) throws Exception {
        if (in == null) {
            return "(null)";
        }
        try (in) {
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        Api.check();

        Module module = Api.class.getModule();
        String name = "demo/assets/internal/secret.txt";

        System.out.println("outside Module: "
                + value(module.getResourceAsStream(name)));

        System.out.println("outside ClassLoader: "
                + value(Api.class.getClassLoader()
                        .getResourceAsStream(name)));

        System.out.println("outside Class URL: "
                + (Api.class.getResource("/" + name) != null));

        System.out.println("class file visible: "
                + (Api.class.getClassLoader().getResource(
                        "demo/assets/internal/Inside.class") != null));

        System.out.println("outside root META-INF: "
                + value(module.getResourceAsStream(
                        "META-INF/demo.info")));
    }
}
```

`DemoMain` chạy trong **unnamed module**, khác module `demo.assets`. Nó có thể tham chiếu `Api` (exported), nhưng **không tự có quyền đọc private resource thuộc package `demo.assets.internal`**.

### 5.6. Tạo hai tài nguyên

Tệp **`resources/demo.assets/demo/assets/internal/secret.txt`**:

```text
hidden-in-module
```

Tệp **`resources/demo.assets/META-INF/demo.info`**:

```text
public-metadata
```

### 5.7. Biên dịch và chạy trên Bash

Từ thư mục gốc `module-resource-demo` (Linux/macOS/Git Bash), dùng JDK 17+:

```bash
mkdir -p mods/demo.assets/demo/assets/internal
mkdir -p mods/demo.assets/META-INF out/app

javac --release 17 -d mods/demo.assets \
  src/demo.assets/module-info.java \
  src/demo.assets/demo/assets/api/Api.java \
  src/demo.assets/demo/assets/internal/Inside.java

cp resources/demo.assets/demo/assets/internal/secret.txt \
   mods/demo.assets/demo/assets/internal/secret.txt
cp resources/demo.assets/META-INF/demo.info \
   mods/demo.assets/META-INF/demo.info

javac --release 17 --module-path mods \
  --add-modules demo.assets \
  -d out/app src-app/DemoMain.java

java --module-path mods --add-modules demo.assets \
  -cp out/app DemoMain
```

`--module-path mods` cho runtime/compiler tìm named module `demo.assets`. `--add-modules demo.assets` buộc module này được resolved khi dùng main class từ classpath/unnamed module. Không dùng lệnh chỉ có `java -cp out/app ...` để mong JVM tự tìm module từ `mods`.

### 5.8. Tương đương cơ bản trên Windows PowerShell

Thay phần tạo thư mục và sao chép tài nguyên bằng:

```powershell
New-Item -ItemType Directory -Force -Path mods/demo.assets/demo/assets/internal, mods/demo.assets/META-INF, out/app | Out-Null

javac --release 17 -d mods/demo.assets src/demo.assets/module-info.java src/demo.assets/demo/assets/api/Api.java src/demo.assets/demo/assets/internal/Inside.java

Copy-Item -LiteralPath resources/demo.assets/demo/assets/internal/secret.txt -Destination mods/demo.assets/demo/assets/internal/secret.txt
Copy-Item -LiteralPath resources/demo.assets/META-INF/demo.info -Destination mods/demo.assets/META-INF/demo.info

javac --release 17 --module-path mods --add-modules demo.assets -d out/app src-app/DemoMain.java

java --module-path mods --add-modules demo.assets -cp out/app DemoMain
```

### 5.9. Đầu ra chính xác

Ví dụ đã được **biên dịch với `javac --release 17` và chạy trên OpenJDK 21**, dùng đúng cấu trúc module ở trên:

```text
inside Class: hidden-in-module
inside ClassLoader: (null)
inside Module: hidden-in-module
module named: true
outside Module: (null)
outside ClassLoader: (null)
outside Class URL: false
class file visible: true
outside root META-INF: public-metadata
```

**Giải thích kết quả:**

1. `inside Class`: code trong package nội bộ của module gọi `Class.getResourceAsStream`, nên được xem là caller từ **chính module**.
2. `inside ClassLoader`: không có unconditional `opens demo.assets.internal;`, vì vậy resource non-`.class` không hiện ra qua `ClassLoader`.
3. `inside Module`: caller cùng module được phép đọc resource của module đó.
4. `outside Module`: caller nằm ở unnamed module; package `demo.assets.internal` chưa mở cho caller, nên trả `null`.
5. `outside ClassLoader`: quy tắc ClassLoader yêu cầu unconditional opens; không thỏa nên trả `null`.
6. `outside Class URL`: `Api.class.getResource("/.../secret.txt")` từ unnamed caller cũng bị quy tắc module encapsulation; không tạo URL.
7. `class file visible`: `Inside.class` kết thúc bằng `.class` nên **ngoại lệ resource `.class`** áp dụng; class-loader lookup vẫn có thể thấy URL class-file trong bài thử này.
8. `outside root META-INF`: resource trong `META-INF` không nằm trong Java package của module, do đó được phép tìm theo quy tắc module resource, và in đúng nội dung.

**Không kết luận rằng mọi class file hoặc mọi root resource trong mọi runtime đều phải có URL.** Quy tắc encapsulation không cấm chúng theo cách non-`.class` package resources bị cấm, nhưng thực tế còn phụ thuộc resource có tồn tại, loader có tạo URL được và môi trường runtime.

## 6. Thử nghiệm qualified opens: mở cho caller chưa đủ với ClassLoader

Giữ nguyên toàn bộ project đã biên dịch. Chạy lại với:

```bash
java --module-path mods --add-modules demo.assets \
  --add-opens demo.assets/demo.assets.internal=ALL-UNNAMED \
  -cp out/app DemoMain
```

Trên PowerShell, có thể dùng một dòng:

```powershell
java --module-path mods --add-modules demo.assets --add-opens demo.assets/demo.assets.internal=ALL-UNNAMED -cp out/app DemoMain
```

`ALL-UNNAMED` ở launcher nêu mục tiêu là các unnamed modules, bao gồm module chứa `DemoMain` trong ví dụ. Đây là **qualified opens**, không phải mở package vô điều kiện.

Đầu ra lần hai (đã kiểm thử):

```text
inside Class: hidden-in-module
inside ClassLoader: (null)
inside Module: hidden-in-module
module named: true
outside Module: hidden-in-module
outside ClassLoader: (null)
outside Class URL: true
class file visible: true
outside root META-INF: public-metadata
```

So sánh:

| Lookup | Trước qualified opens | Sau qualified opens |
|---|---|---|
| `Inside.class.getResourceAsStream` gọi trong module | Được | Được |
| `Inside.class.getClassLoader().getResourceAsStream` | `null` | Vẫn `null` |
| `Module.getResourceAsStream` gọi từ unnamed module | `null` | Được |
| `Class.getResource` gọi từ unnamed module | `null` | Được |
| `ClassLoader.getResourceAsStream` gọi từ unnamed module | `null` | Vẫn `null` |

Đây là bằng chứng thực hành cho **sự khác nhau về granularity của access control**:

- `Class`/`Module` kiểm tra khả năng package mở cho **caller module**.
- `ClassLoader` đối với non-`.class` resources trong named-module packages chỉ trả resource nếu package **opened unconditionally**.

Nếu sửa `module-info.java` thành:

```java
module demo.assets {
    exports demo.assets.api;
    opens demo.assets.internal;
}
```

rồi biên dịch lại module, package nội bộ sẽ mở vô điều kiện theo module declaration. Khi các điều kiện tìm resource còn lại thỏa, ClassLoader có thể thấy `secret.txt`. Đây là **phương án thiết kế khác**, không phải điều chỉnh miễn phí: nó mở package rộng hơn nhiều, nên cần cân nhắc encapsulation.

**Lưu ý bảo mật:** Không thêm `opens` hoặc `--add-opens` bừa bãi chỉ để một đoạn code đọc config. Nếu resource có tính nội bộ, tốt hơn thường là API đọc resource **bên trong module** và chỉ xuất dữ liệu đã xử lý.

## 7. Đọc tài nguyên đúng lớp đúng module

Khi code và resource thuộc cùng named module, một cách phổ biến là để class bên trong module sở hữu việc đọc:

```java
package demo.assets.internal;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ConfigReader {
    public static String load() throws IOException {
        try (InputStream in =
                ConfigReader.class.getResourceAsStream("secret.txt")) {
            if (in == null) {
                throw new IOException("Missing secret.txt");
            }
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
```

Đây là **class utility có thể biên dịch**, nhưng không chứa `main` và phải được xây dựng với resource `secret.txt` thực sự cùng package. Khi code `ConfigReader.load()` chạy trong module sở hữu package, `Class.getResourceAsStream` dùng ngữ cảnh caller phù hợp để đọc resource nội bộ mà không cần mở package cho mọi module.

Ở module-level, có thể dùng:

```java
Module owner = ConfigReader.class.getModule();
try (InputStream in = owner.getResourceAsStream(
        "demo/assets/internal/secret.txt")) {
    if (in == null) {
        throw new IOException("Resource missing/inaccessible");
    }
    // Xử lý stream ở đây.
}
```

Đây là snippet minh họa bên trong method có imports `InputStream` và `IOException`; điều kiện access vẫn được kiểm tra theo **module của caller thực sự**. Nếu bê chính đoạn code này ra một module khác thì resource nội bộ có thể thành `null`.

**Cần nhớ:** Cách đọc bằng `Class` không cấp quyền truy cập vĩnh viễn cho mọi caller. Nó có thể thành công khi lời gọi nằm trong module A, nhưng một caller module B gọi `AClass.class.getResource(...)` có thể bị từ chối khi A không mở package cho B.

## 8. Khi nào chọn Class, ClassLoader hay Module?

### Chọn Class khi tài nguyên “đi kèm class” và thuộc module của class

Ví dụ: schema riêng, template nội bộ, default config, migration text chỉ ứng dụng/module sở hữu biết cách diễn giải.

```java
try (InputStream in =
        MyComponent.class.getResourceAsStream("default.yaml")) {
    // ...
}
```

Đây là snippet minh họa không độc lập. Lợi ích: tên tương đối đơn giản, gắn với class/module, tránh nhầm loader context. Nên đặt code đọc tài nguyên trong module sở hữu tài nguyên nếu nó được encapsulate.

### Chọn Module khi đã biết module đích và cần lookup theo module name/identity

Ví dụ framework giữ đối tượng `Module` sau khi tạo `ModuleLayer`:

```java
Module pluginModule = layer.findModule("demo.assets")
        .orElseThrow();

try (InputStream in =
        pluginModule.getResourceAsStream(
                "demo/assets/internal/secret.txt")) {
    // ...
}
```

Đây là đoạn minh họa cần biến `layer` kiểu `ModuleLayer` có giá trị. **Đã có reference tới `Module` không tự cấp quyền đọc private resources**: caller vẫn phải được package mở thích hợp hoặc tài nguyên không bị encapsulate.

### Chọn ClassLoader khi tìm resource trong loader namespace hoặc cần tổng hợp nhiều nguồn

Ví dụ:

```java
ClassLoader loader = Thread.currentThread()
        .getContextClassLoader();
if (loader != null) {
    URL url = loader.getResource(
            "META-INF/services/demo.spi.Provider");
}
```

Đây là snippet minh họa, không tự bảo đảm provider tồn tại. Resource `META-INF/services/...` thường nằm ngoài Java package thông thường; APIs như `ServiceLoader` có discovery rules riêng trong named modules qua `provides ... with ...`, không chỉ đọc descriptor từ classpath.

ClassLoader phù hợp để tra resources từ classpath/unnamed modules, loader plugin hoặc aggregation do framework quản lý — nhưng **không nên dùng để “đột nhập” private named-module packages**.

## 9. “Resource có tồn tại nhưng null” — chẩn đoán có hệ thống

Khi `getResource` hoặc `getResourceAsStream` trả `null`, kiểm tra theo thứ tự:

1. **Đúng tên chưa?** `Class.getResource("file.txt")` là tương đối package; `ClassLoader.getResource("pkg/file.txt")` dùng path từ root không có `/` đầu; `Module.getResourceAsStream` dùng root path (và có thể bỏ `/` đầu).
2. **Resource có nằm trong output?** Source project có file không đồng nghĩa compiler/build tool đã copy nó vào `mods` hoặc JAR.
3. **Class nằm trong module nào?** `clazz.getModule().getName()`, `isNamed()`; classpath/unnamed và module path/named dùng quy tắc khác nhau.
4. **Đang gọi API nào?** `Class`, `ClassLoader` và `Module` có access rules riêng.
5. **Caller thuộc module nào?** `Module.getResourceAsStream` và `Class.getResourceAsStream` dùng khả năng mở package cho caller; cùng module khác bên ngoài.
6. **Resource path thuộc package nào?** Với `demo/assets/internal/secret.txt`, suy ra `demo.assets.internal`; kiểm tra package có thực sự thuộc module không.
7. **`exports` hay `opens`?** `exports` public API không đủ. `opens ... to ...` có thể đủ cho caller cụ thể nhưng không đủ cho `ClassLoader.getResource`.
8. **Có phải `.class` resource không?** Ngoại lệ `.class` của rules cần được xét, nhưng còn phụ thuộc resource availability.
9. **Class loader phù hợp chưa?** Parent delegation, TCCL và custom child loaders có thể thay đổi nguồn/tập resources.
10. **Có IOException hoặc URL không tạo được không?** `null` cũng có thể đến từ cơ chế loader/resource provider; đừng khẳng định nguyên nhân duy nhất luôn là encapsulation.
11. **Có phải module chưa resolved không?** Module path có chứa module nhưng runtime chưa resolve module nếu không được root/add-module phù hợp.
12. **Đã thử từ chính module chưa?** Nếu code của module đọc được còn app bên ngoài không, hãy xem module access chứ đừng tự sao chép resource sang classpath rồi che nguyên nhân.

Một đoạn diagnostic trong code đã có đối tượng `Class<?> type`:

```java
Module owner = type.getModule();
System.out.println("type=" + type.getName());
System.out.println("module=" + owner.getName());
System.out.println("named=" + owner.isNamed());
System.out.println("loader=" + type.getClassLoader());
System.out.println("opens to caller="
        + owner.isOpen(type.getPackageName(),
                Diagnostic.class.getModule()));
```

Đây là **snippet minh họa**, cần class `Diagnostic` và biến `type` có sẵn. Giá trị `isOpen(..., callerModule)` là một chỉ báo về package access, không thay cho việc xác minh tên resource có thật hay quy tắc `ClassLoader` về unconditional opens.

## 10. Resource đóng gói trong JAR/module image không nhất thiết là File

`Class.getResource` có thể trả URL như:

```text
file:/opt/app/classes/demo/assets/config.txt
jar:file:/opt/app/lib/demo.jar!/demo/assets/config.txt
jrt:/java.base/java/lang/String.class
```

`file:` thường tương ứng resource trên filesystem. `jar:` biểu diễn entry trong JAR; `jrt:` biểu diễn resource trong JDK runtime image.

**Không viết**:

```java
File f = new File(type.getResource("config.txt").toURI());
```

như giải pháp cho mọi resource. `File(URI)` đòi URI kiểu `file:` phù hợp. Với `jar:`/`jrt:`, việc chuyển trực tiếp không tương đương một local filesystem file và có thể ném exception.

Khi mục tiêu **đọc bytes**, ưu tiên:

```java
try (InputStream in =
        type.getResourceAsStream("config.txt")) {
    if (in == null) {
        throw new IllegalStateException(
                "Resource absent or inaccessible");
    }
    byte[] bytes = in.readAllBytes();
}
```

Đây là snippet trong method có xử lý `IOException`. Với resource lớn, dùng streaming/buffer và giới hạn bộ nhớ thay vì đọc toàn bộ.

**Quan trọng:** Stream giúp code độc lập nơi lưu **sau khi được phép tìm tài nguyên**; dùng stream **không vượt qua module encapsulation**.

## 11. Unnamed module và classpath khác named module thế nào?

Đặt classes/resource trên classpath thường có:

```text
java -cp out/app demo.Main
```

Classes trên classpath thuộc **unnamed module** của loader tương ứng. Những quy tắc đặc biệt về encapsulated **named-module packages** không được áp dụng y hệt với resource chỉ sống trong unnamed module/classpath thông thường.

Nhưng khi chuyển cùng project sang:

```text
java --module-path mods -m demo.assets/demo.assets.api.Main
```

và khai báo `module-info.java`, package resource có thể bị encapsulate theo JPMS. Vì thế test “IDE/classpath chạy được” **không đủ** để chứng minh module-path deployment đúng.

**Cách chuyển đổi an toàn:**

- Giữ assets nội bộ do code cùng module đọc bằng `Class.getResourceAsStream` hoặc `Module.getResourceAsStream`.
- Nếu code module B cần đọc resource A, hãy thiết kế **public data API** ở module A trước khi mở package.
- Nếu bắt buộc external module lookup, dùng `opens pkg to consumer.module` ở phạm vi tối thiểu phù hợp.
- Chỉ dùng unconditional `opens pkg;` nếu chính sách cho phép resource công khai hơn và đã xem xét reflection exposure.
- Không ngẫu nhiên thêm toàn bộ tài nguyên vào JAR/classpath khác để “né” encapsulation, vì điều đó tạo duplicate sources và coupling triển khai.

## 12. ModuleLayer và resource lookup khi plugin có nhiều layer

Với các framework phát triển module layers riêng, **module identity và loader mapping** là những chiều khác nhau:

```text
Boot layer
   ├── java.base
   └── ...
Plugin layer
   ├── plugin.a
   └── plugin.b
        |
        └── có thể gắn với loader riêng hoặc loader dùng chung
```

Nếu framework có đối tượng `ModuleLayer` và tên module:

```java
Module module = pluginLayer.findModule("plugin.a")
        .orElseThrow();
InputStream in = module.getResourceAsStream(
        "plugin/a/config/defaults.json");
```

Đây là snippet minh họa: `pluginLayer` được tạo ở nơi khác; vẫn cần xử lý `IOException`/`null` và đóng stream. API `Module` giúp chọn đúng module **ngay cả khi nhiều module chia sẻ class loader**.

`ClassLoader.getResources` khi nhiều modules cùng loader cung cấp tên giống nhau có thể có **thứ tự không được đặc tả**; không nên thiết kế plugin config “lấy resource đầu tiên” rồi mặc định đó là version/tenant đúng. Hãy dùng explicit module lookup hoặc policy nguồn rõ ràng.

### TCCL không tự mở package

`Thread.currentThread().setContextClassLoader(pluginLoader)` ảnh hưởng các API chủ động đọc TCCL (ví dụ một số service discovery), nhưng **không làm package của named module tự được `opens`**. Ngay cả khi TCCL trỏ đúng loader, `ClassLoader.getResource` vẫn bị quy tắc unconditional opens đối với non-`.class` resources của named module.

## 13. META-INF/services, module services và file resources

`META-INF/services/<service-binary-name>` là kiểu resource dùng cho **classpath-based service provider declarations**, nhưng named modules có thể đăng ký services bằng `module-info.java`:

```java
module plugin.provider {
    requires plugin.api;
    provides plugin.api.Service
        with plugin.impl.ServiceImpl;
}
```

Đây là module declaration minh họa cần module `plugin.api` và implementation hợp lệ. `ServiceLoader` hiểu **provider declarations trong named modules**, không cần bạn phải tự đọc từng `META-INF/services` trong mọi trường hợp.

Điều quan trọng:

- `ServiceLoader.load(Service.class)` dùng **thread context class loader** theo Java SE 17 API (đồng thời có module-specific discovery rules).
- `ServiceLoader.load(layer, Service.class)` dùng **module layer** được chỉ định.
- `ClassLoader.getResource("META-INF/services/...")` chỉ là một kiểu truy cập resource; **không thay thế** toàn bộ contract của `ServiceLoader`.
- Với custom loaders, `getResources` phải hỗ trợ đúng aggregation để không vô tình bỏ sót provider-configuration files từ nhiều JARs.
- Qualified `opens` cho module consumer không phải cơ chế “xuất” mọi config của module qua ClassLoader.

## 14. Lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| Gọi `ClassLoader.getResource("/p/config.txt")` | Loader API dùng tên từ root **không có `/` đầu** | `getResource("p/config.txt")` |
| Giả định `Class.getResource("config.txt")` luôn tìm root | Tên không có `/` đầu **tương đối package** | Dùng `"/p/config.txt"` nếu muốn root |
| Có `exports p;` nên ClassLoader tìm được `p/config.txt` | Export public types, không phải unconditional open | Dùng `Class`/`Module` nội bộ hoặc `opens` có chủ đích |
| Qualified `opens p to x;` rồi mong ClassLoader thấy | ClassLoader đòi **unconditional opens** cho non-`.class` resource | Dùng module-aware API của caller được mở |
| Đặt TCCL là plugin loader rồi coi như JPMS open tự thay đổi | TCCL và module encapsulation là hai cơ chế khác nhau | Chọn API/module policy đúng |
| Resource trả `null` nên kết luận file không đóng gói | Có thể không mở package, sai module, sai name hoặc module chưa resolved | Kiểm tra cả resource existence và access |
| Cắt chuỗi URL `jar:...!/path` để tạo `File` | JAR entry không phải local file độc lập | Đọc stream, hoặc dùng ZIP FS khi thực sự cần |
| Dùng `ClassLoader.getResources` rồi phụ thuộc thứ tự modules | Thứ tự giữa resources từ nhiều modules cùng loader có thể không được đặc tả | Chọn module đích tường minh |
| Tự đọc `META-INF/services` và cho rằng tương đương ServiceLoader | ServiceLoader còn hiểu named module providers | Dùng API `ServiceLoader` |
| Mở tất cả packages vô điều kiện để “chạy được” | Mở rộng exposure, ảnh hưởng reflection/resource access | Chỉ mở package/caller cần thiết hoặc cung cấp API |
| Quên đóng `InputStream` | Leak handles và memory/resource pressure | Dùng `try-with-resources` |
| Thử mỗi classpath mà không thử module path | Named module resources có encapsulation khác | Test cả layout triển khai thực tế |

## 15. Checklist triển khai ứng dụng có module

1. Xác định **tài nguyên thuộc module nào**, file có được copy vào module output/JAR không.
2. Chọn `Class`/`Module` nếu asset gắn với module; chỉ dùng loader namespace khi yêu cầu phù hợp.
3. Xác định **caller module** thực hiện lookup, tránh suy đoán từ ClassLoader.
4. Đối chiếu package path của resource với `Module.getPackages()` khi cần chẩn đoán.
5. Nếu resource là non-`.class` trong một package thực của named module, kiểm tra **opens**:
   - code cùng module: module-aware lookup có thể đọc;
   - caller module khác: cần opens cho caller;
   - ClassLoader lookup: cần unconditional opens.
6. Xử lý `null` là thiếu hoặc không truy cập được, không dereference ngay.
7. Xử lý `IOException` và dùng stream với tài nguyên JAR/JRT.
8. Không tự thay classpath/module path/loader giữa các phần ứng dụng nếu thiếu kiểm thử.
9. Khi có nhiều modules/layers, ưu tiên định danh module tường minh thay vì dựa vào thứ tự `getResources`.
10. Xác minh trên Java runtime/module-path thực tế, không chỉ IDE.
11. Không thêm `opens` rộng hơn mức cần thiết và nhớ xem xét exposure của reflective access.
12. Giữ resource schema và version tương thích với code trong module sở hữu nó.

## 16. Câu hỏi tự kiểm tra

**1. `Class.getResource("a.txt")` với class thuộc `demo.internal` tìm ở đâu?** Tên tương đối với package: `demo/internal/a.txt`.

**2. `ClassLoader.getResource("demo/internal/a.txt")` có cần dấu `/` đầu không?** Không. Đây là tên từ root namespace của loader.

**3. Với named module không mở package `demo.internal`, code bên trong chính module có đọc `a.txt` bằng `Module.getResourceAsStream` không?** Có thể đọc nếu resource tồn tại và các điều kiện lookup thỏa; caller là chính module nên đáp ứng access rule.

**4. Code bên trong module gọi `ClassLoader.getResourceAsStream` có tự được quyền đọc cùng resource không?** Không. ClassLoader API vẫn yêu cầu package mở **vô điều kiện** nếu đó là non-`.class` resource nằm trong package của named module.

**5. `exports demo.internal;` có tương đương `opens demo.internal;` không?** Không. `exports` cho public API access; `opens` điều khiển reflective access và package-resource access theo các quy tắc thích hợp.

**6. `--add-opens demo.assets/demo.assets.internal=ALL-UNNAMED` có khiến ClassLoader.getResource đọc được không?** Không chỉ nhờ qualified opens này. Nó cho unnamed caller đọc qua module-aware APIs; ClassLoader vẫn đòi unconditional opens.

**7. Resource `demo/internal/Inside.class` có chịu cùng giới hạn như `demo/internal/secret.txt` không?** Không. Resource name kết thúc `.class` là một ngoại lệ của resource encapsulation rule; lookup vẫn có thể không tìm thấy vì các nguyên nhân khác.

**8. Resource `META-INF/demo.info` có cần mở package `META-INF` không?** Không theo rule package encapsulation, vì `META-INF` không phải tên Java package hợp lệ.

**9. Module và ClassLoader có phải một đối tượng không?** Không. Module biểu diễn namespace và metadata trong JPMS; loader định nghĩa classes và có thể gắn với nhiều modules.

**10. Nếu `Module.getResourceAsStream` trả `null` từ module khác, hướng sửa tốt nhất có luôn là unconditional `opens` không?** Không. Ưu tiên API public đọc resource trong module, hoặc qualified opens trong phạm vi cần thiết nếu thực sự yêu cầu truy cập trực tiếp.

## 17. Tài liệu chuẩn

- **Java SE 17 API — `Class`**, `getResource(String)` và `getResourceAsStream(String)`, cách xử lý name và named-module lookup: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 API — `ClassLoader`**, `getResource`, `getResources`, `getResourceAsStream`, `findResource(moduleName,name)`, unconditional opens: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 API — `Module`**, `getResourceAsStream(String)`, nguồn module, caller module và rules mở package: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- **Java SE 17 — `java` command**, `--module-path`, `--add-modules`, `--add-opens`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **JLS `7.7 — Module Declarations**, `exports`, `opens` và `open module`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7
- **Java SE 17 API — `ModuleLayer`**, tìm module trong layer: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html

**Ghi nhớ:** **`Class` và `Module` biết resource thuộc module nào và xét quyền mở package theo caller; `ClassLoader` tra trong loader namespace và đòi package của named module mở vô điều kiện cho non-`.class` resources.** Nếu resource nội bộ, đọc bên trong module và cung cấp API dữ liệu ra ngoài; đừng mở mọi package chỉ để chạy được một resource lookup.
