# Phân biệt tài nguyên không tồn tại và tài nguyên bị giới hạn truy cập trong Java

Khi đọc file cấu hình, template, ảnh hoặc metadata nằm trong một mô-đun Java, lời gọi như `Class.getResource(...)` hoặc `Module.getResourceAsStream(...)` có thể trả về `null`. Kết quả này **không luôn có nghĩa là file không tồn tại**. Trong named module, resource có thể đang nằm trong một package bị đóng đối với mô-đun gọi.

Cần phân biệt hai tình huống:

- **Không tìm thấy (not found):** tên resource sai, file không được đóng gói, sai đường dẫn hoặc resource không nằm trong module/class loader đang tra cứu.
- **Bị giới hạn bởi encapsulation:** resource có trong named module, nhưng package chứa nó không được mở cho mô-đun gọi theo quy tắc JPMS.

Các API tra cứu thông thường thường dùng cùng giá trị `null` cho cả hai trường hợp. Muốn chẩn đoán chính xác, cần kiểm tra cách tạo tên resource, trạng thái `opens` của package và nội dung thật của module artifact.

## 1. Resource được đặt tên và tìm kiếm như thế nào?

Resource là dữ liệu đi kèm chương trình, ví dụ:

- `application.properties`, `messages.properties`.
- File JSON, XML hoặc YAML.
- Template HTML, ảnh, font và các file dữ liệu tĩnh.
- File metadata được đóng gói trong JAR hoặc thư mục mô-đun.

Resource không nhất thiết là class Java. Nó được định vị bằng tên dạng đường dẫn, dùng dấu gạch chéo xuôi `/` làm dấu phân cách.

Ví dụ cấu trúc một mô-đun:

```text
com.acme.assets/
├── module-info.class
└── com/acme/assets/
    ├── api/AssetAnchor.class
    ├── internal/InternalMarker.class
    └── publicdata/PublicMarker.class
```

Resource được đặt cạnh các class trong package tương ứng:

```text
com/acme/assets/internal/secret.txt
com/acme/assets/publicdata/banner.txt
```

Tên resource là đường dẫn bên trong module/JAR, không phải đường dẫn tuyệt đối trên ổ đĩa. Không dùng dấu `\\` của Windows trong tên resource.

## 2. Phân biệt các API tra cứu resource

Các API có quy tắc đặt tên và encapsulation khác nhau. Cần chọn đúng API theo vị trí của resource.

### `Class.getResource` và `Class.getResourceAsStream`

Hai phương thức này tìm resource gắn với class:

```java
URL url = AssetAnchor.class.getResource(
    "/com/acme/assets/publicdata/banner.txt"
);

InputStream input = AssetAnchor.class.getResourceAsStream(
    "/com/acme/assets/publicdata/banner.txt"
);
```

Quy tắc tên:

- Tên bắt đầu bằng `/` là đường dẫn tuyệt đối tính từ gốc resource.
- Tên không bắt đầu bằng `/` là đường dẫn tương đối với package của class.

Ví dụ, nếu class nằm trong package `com.acme.assets.api`:

```java
AssetAnchor.class.getResource("help.txt");
```

sẽ tìm `com/acme/assets/api/help.txt`.

Trong named module, resource không phải file `.class` nằm trong package của mô-đun chỉ được tìm thấy khi package đó mở cho mô-đun của code đang gọi phương thức. Nếu package không mở cho caller, phương thức trả về `null`, kể cả khi file có thật trong JAR hoặc thư mục mô-đun.

`getResource` trả về `URL`; `getResourceAsStream` trả về `InputStream`. Cả hai đều có thể trả về `null` khi không tìm thấy hoặc caller không được phép nhìn thấy resource.

### `Module.getResourceAsStream`

Phương thức này tìm resource trực tiếp trong một mô-đun cụ thể:

```java
Module assets = AssetAnchor.class.getModule();

try (InputStream input =
        assets.getResourceAsStream(
            "com/acme/assets/publicdata/banner.txt")) {
    if (input == null) {
        System.out.println("Resource unavailable");
    } else {
        System.out.println(
            new String(input.readAllBytes(), StandardCharsets.UTF_8)
        );
    }
}
```

Tên resource được tính từ gốc mô-đun. Một dấu `/` ở đầu tên được bỏ qua, nhưng thông thường nên truyền tên không có dấu đó.

Nếu resource thuộc một package trong named module, package phải mở cho module của caller. Nếu không, phương thức trả về `null`. Nếu resource không thuộc package nào của module, quy tắc encapsulation package này không áp dụng. Ví dụ `META-INF/MANIFEST.MF` không bị encapsulate như một package Java.

Phương thức có thể ném `IOException` nếu xảy ra lỗi I/O. Giá trị `null` vẫn có thể biểu thị resource không có hoặc package không mở cho caller.

### `ClassLoader.getResource` và `ClassLoader.getResourceAsStream`

Các phương thức này tìm resource qua class loader:

```java
ClassLoader loader = AssetAnchor.class.getClassLoader();

URL url = loader.getResource(
    "com/acme/assets/publicdata/banner.txt"
);
```

Khác với `Class.getResource`, tên truyền cho `ClassLoader` không có dấu `/` ở đầu.

Trong named module, đối với resource không phải `.class` nằm trong package của module, `ClassLoader.getResource` chỉ tìm thấy resource khi package được mở **không điều kiện**. Qualified open như:

```java
opens com.acme.assets.publicdata to com.acme.consumer;
```

có thể cho phép `Class.getResource` hoặc `Module.getResourceAsStream` từ `com.acme.consumer` đọc resource, nhưng chưa đủ cho `ClassLoader.getResource`. ClassLoader không dùng module của caller để xét qualified open; nó yêu cầu package open cho mọi mô-đun.

Có ngoại lệ đối với resource tên kết thúc bằng `.class`: các class resource không chịu cùng giới hạn encapsulation như resource dữ liệu thông thường. Resource ngoài package, ví dụ ở gốc module hoặc trong `META-INF`, cũng không bị áp dụng quy tắc mở package theo cách trên.

### Bảng so sánh nhanh

| API | Dạng tên | Điều kiện mở package trong named module | Kết quả không tìm thấy/không truy cập được |
|---|---|---|---|
| `Class.getResource` | `/` đầu tên là tuyệt đối; không có là tương đối với package class | Mở cho module của caller | `null` |
| `Class.getResourceAsStream` | Giống `Class.getResource` | Mở cho module của caller | `null` |
| `Module.getResourceAsStream` | Tính từ gốc module; có thể bỏ dấu `/` đầu | Mở cho module của caller nếu resource thuộc package | `null` |
| `ClassLoader.getResource` | Đường dẫn từ gốc, không có `/` đầu | Package phải open không điều kiện | `null` |
| `ClassLoader.getResourceAsStream` | Đường dẫn từ gốc, không có `/` đầu | Package phải open không điều kiện | `null` |

## 3. Vì sao `null` chưa đủ để kết luận resource bị thiếu?

Giả sử ứng dụng gọi:

```java
InputStream input = assets.getResourceAsStream(
    "com/acme/assets/internal/secret.txt"
);
```

Nếu `input == null`, có ít nhất hai khả năng:

1. `secret.txt` không được đóng gói hoặc tên resource không đúng.
2. File có trong mô-đun, nhưng package `com.acme.assets.internal` không mở cho module của caller.

Vì API dùng cùng kết quả `null`, chỉ kiểm tra biến trả về không thể phân biệt hai trường hợp.

Có thể kiểm tra quyền mở package:

```java
Module caller = Main.class.getModule();
Module assets = AssetAnchor.class.getModule();

boolean openToCaller = assets.isOpen(
    "com.acme.assets.internal",
    caller
);
```

Nếu `openToCaller` là `false`, resource thuộc package đó có thể bị giới hạn bởi encapsulation. Tuy nhiên, điều này **chưa chứng minh resource tồn tại**. Package có thể đóng và file cũng có thể bị thiếu cùng lúc.

Nếu `openToCaller` là `true` mà lookup vẫn trả `null`, hãy kiểm tra tên resource, vị trí đóng gói, module/class loader thực tế và lỗi tạo URL.

## 4. `opens` khác `exports` khi đọc resource

Trong JPMS:

- `exports` công khai các kiểu public trong package để mã ở mô-đun khác sử dụng khi biên dịch và chạy.
- `opens` cho phép deep reflection và cho phép các API tra cứu resource theo quy tắc module resource nhìn thấy package từ caller tương ứng.

Ví dụ:

```java
module com.acme.assets {
    exports com.acme.assets.api;
    opens com.acme.assets.publicdata to com.acme.consumer;
}
```

Ở đây:

- Consumer có thể import kiểu public trong `com.acme.assets.api`.
- Consumer được phép tra cứu resource trong `com.acme.assets.publicdata` bằng các API caller-sensitive như `Class.getResource` và `Module.getResourceAsStream`.
- Package `com.acme.assets.internal` không được mở, nên resource dữ liệu trong package đó bị giới hạn đối với consumer.

Chỉ export package không thay thế cho open package khi cần đọc resource không phải class trong named module.

Nếu cần đọc resource từ một framework hoặc module cụ thể, chỉ mở package cần thiết và giới hạn bằng qualified open:

```java
opens com.acme.assets.templates to com.acme.template.engine;
```

Không mở toàn bộ mô-đun chỉ để giải quyết một resource riêng lẻ.

## 5. Ví dụ chạy được: resource có thật nhưng bị đóng và resource thật sự bị thiếu

Ví dụ gồm hai named modules:

- `com.acme.assets`: chứa resource và quyết định package nào được mở.
- `com.acme.consumer`: đọc resource và kiểm tra trạng thái truy cập.

Cấu trúc mã nguồn:

```text
src/
├── com.acme.assets/
│   ├── module-info.java
│   └── com/acme/assets/
│       ├── api/AssetAnchor.java
│       ├── internal/InternalMarker.java
│       ├── internal/secret.txt
│       ├── publicdata/PublicMarker.java
│       └── publicdata/banner.txt
└── com.acme.consumer/
    ├── module-info.java
    └── com/acme/consumer/Main.java
```

**Module descriptor của mô-đun chứa resource — `src/com.acme.assets/module-info.java`:**

```java
module com.acme.assets {
    exports com.acme.assets.api;
    opens com.acme.assets.publicdata to com.acme.consumer;
}
```

Package `com.acme.assets.internal` không được mở. Package `com.acme.assets.publicdata` được mở có giới hạn cho consumer.

**Class làm điểm tham chiếu tới module — `AssetAnchor.java`:**

```java
package com.acme.assets.api;

public final class AssetAnchor {
}
```

**Class trong package nội bộ — `InternalMarker.java`:**

```java
package com.acme.assets.internal;

public final class InternalMarker {
}
```

**Class trong package được mở — `PublicMarker.java`:**

```java
package com.acme.assets.publicdata;

public final class PublicMarker {
}
```

Tạo hai file resource với nội dung:

`src/com.acme.assets/com/acme/assets/internal/secret.txt`:

```text
SECRET-RESOURCE
```

`src/com.acme.assets/com/acme/assets/publicdata/banner.txt`:

```text
PUBLIC-RESOURCE
```

**Module descriptor của consumer — `src/com.acme.consumer/module-info.java`:**

```java
module com.acme.consumer {
    requires com.acme.assets;
}
```

**Chương trình kiểm tra — `src/com.acme.consumer/com/acme/consumer/Main.java`:**

```java
package com.acme.consumer;

import com.acme.assets.api.AssetAnchor;
import java.io.InputStream;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReader;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

public final class Main {
    private static String read(InputStream input) throws Exception {
        if (input == null) {
            return "null";
        }

        try (input) {
            return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
            );
        }
    }

    public static void main(String[] args) throws Exception {
        Module caller = Main.class.getModule();
        Module assets = AssetAnchor.class.getModule();

        String internal =
            "com/acme/assets/internal/secret.txt";
        String publicData =
            "com/acme/assets/publicdata/banner.txt";
        String missing =
            "com/acme/assets/internal/missing.txt";

        System.out.println("consumer reads assets: "
            + caller.canRead(assets));
        System.out.println("internal open to consumer: "
            + assets.isOpen("com.acme.assets.internal", caller));
        System.out.println("publicdata open to consumer: "
            + assets.isOpen("com.acme.assets.publicdata", caller));

        System.out.println("Class.getResource internal: "
            + (AssetAnchor.class.getResource("/" + internal) != null));
        System.out.println("Class.getResource public: "
            + (AssetAnchor.class.getResource("/" + publicData) != null));
        System.out.println("Class.getResource missing: "
            + (AssetAnchor.class.getResource("/" + missing) != null));

        System.out.println("Module.getResourceAsStream internal: "
            + read(assets.getResourceAsStream(internal)));
        System.out.println("Module.getResourceAsStream public: "
            + read(assets.getResourceAsStream(publicData)));
        System.out.println("Module.getResourceAsStream missing: "
            + read(assets.getResourceAsStream(missing)));

        ClassLoader loader = AssetAnchor.class.getClassLoader();
        System.out.println("ClassLoader.getResource internal: "
            + (loader.getResource(internal) != null));
        System.out.println("ClassLoader.getResource public qualified-open: "
            + (loader.getResource(publicData) != null));

        try (ModuleReader reader = ModuleFinder
                .of(Path.of(args[0]))
                .find("com.acme.assets")
                .orElseThrow()
                .open()) {

            System.out.println("ModuleReader.find internal: "
                + reader.find(internal).isPresent());
            System.out.println("ModuleReader.find missing: "
                + reader.find(missing).isPresent());
            System.out.println("ModuleReader.read internal: "
                + read(reader.open(internal).orElse(null)));
        }
    }
}
```

Biên dịch từ thư mục gốc chứa `src/`:

**PowerShell:**

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --module-source-path src -d out -m com.acme.assets,com.acme.consumer
New-Item -ItemType Directory -Force out/com.acme.assets/com/acme/assets/internal, out/com.acme.assets/com/acme/assets/publicdata | Out-Null
Copy-Item src/com.acme.assets/com/acme/assets/internal/secret.txt out/com.acme.assets/com/acme/assets/internal/
Copy-Item src/com.acme.assets/com/acme/assets/publicdata/banner.txt out/com.acme.assets/com/acme/assets/publicdata/
```

**Bash:**

```bash
mkdir -p out
javac --module-source-path src -d out -m com.acme.assets,com.acme.consumer
mkdir -p out/com.acme.assets/com/acme/assets/internal
mkdir -p out/com.acme.assets/com/acme/assets/publicdata
cp src/com.acme.assets/com/acme/assets/internal/secret.txt out/com.acme.assets/com/acme/assets/internal/
cp src/com.acme.assets/com/acme/assets/publicdata/banner.txt out/com.acme.assets/com/acme/assets/publicdata/
```

`javac` biên dịch file Java nhưng không tự sao chép các file resource tùy ý trong source tree. Vì vậy cần đưa `.txt` vào đúng package path của exploded module sau khi biên dịch.

Chạy ứng dụng:

```bash
java --module-path out -m com.acme.consumer/com.acme.consumer.Main out
```

Kết quả trên OpenJDK 24:

```text
consumer reads assets: true
internal open to consumer: false
publicdata open to consumer: true
Class.getResource internal: false
Class.getResource public: true
Class.getResource missing: false
Module.getResourceAsStream internal: null
Module.getResourceAsStream public: PUBLIC-RESOURCE
Module.getResourceAsStream missing: null
ClassLoader.getResource internal: false
ClassLoader.getResource public qualified-open: false
ModuleReader.find internal: true
ModuleReader.find missing: false
ModuleReader.read internal: SECRET-RESOURCE
```

Cách đọc kết quả:

- `secret.txt` có thật nhưng package `internal` không mở cho consumer. Các API caller-sensitive trả `null`.
- `banner.txt` có thật và package `publicdata` mở qualified cho consumer. `Class.getResource` và `Module.getResourceAsStream` đọc được.
- `missing.txt` không tồn tại nên lookup cũng trả `null`.
- `ClassLoader.getResource` không tìm thấy cả hai resource trong package vì package `publicdata` chỉ được mở qualified, không mở không điều kiện.
- `ModuleReader.find` tìm thấy `secret.txt` và không tìm thấy `missing.txt`. Điều này phân biệt được file có thật nhưng bị giới hạn với file không có trong module artifact.

## 6. Dùng `ModuleReader` để xác minh resource có trong module artifact

`ModuleReader` thuộc API `java.lang.module` từ Java 9. Nó đọc nội dung của một module reference, thường được lấy qua `ModuleFinder`.

**Tìm module trên module path:**

```java
ModuleReference reference = ModuleFinder
    .of(Path.of("out"))
    .find("com.acme.assets")
    .orElseThrow();
```

**Kiểm tra resource có tồn tại:**

```java
try (ModuleReader reader = reference.open()) {
    boolean exists = reader
        .find("com/acme/assets/internal/secret.txt")
        .isPresent();

    System.out.println(exists);
}
```

`find(name)` trả về `Optional<URI>`:

- `Optional` có giá trị: module reader định vị được resource.
- `Optional.empty()`: resource không được tìm thấy trong module reference đó.
- `IOException`: xảy ra lỗi I/O hoặc reader đã đóng.

Để mở nội dung:

```java
try (ModuleReader reader = reference.open()) {
    try (InputStream input = reader
            .open("com/acme/assets/internal/secret.txt")
            .orElseThrow()) {
        System.out.println(
            new String(input.readAllBytes(), StandardCharsets.UTF_8)
        );
    }
}
```

Trong ví dụ, `ModuleReader` tìm và đọc được `secret.txt` dù package không mở cho consumer. Đây là API đọc nội dung của module artifact, hữu ích cho công cụ đóng gói, kiểm tra và chẩn đoán. Nó không thay đổi `opens` và không làm resource tự động nhìn thấy qua `Class.getResource` hoặc `ClassLoader.getResource`.

`ModuleReader.list()` cũng có thể liệt kê tên resource trong module:

```java
try (ModuleReader reader = reference.open()) {
    reader.list()
        .filter(name -> name.endsWith(".txt"))
        .forEach(System.out::println);
}
```

Nếu module được nạp từ runtime image, custom module layer hoặc nguồn không phải thư mục/JAR thông thường, cách lấy `ModuleReference` có thể khác. `ModuleFinder.of(path)` trong ví dụ phù hợp với module path chứa exploded module hoặc modular JAR.

## 7. Quy trình chẩn đoán khi lookup trả về `null`

Khi resource lookup thất bại, kiểm tra theo thứ tự:

1. **Xác nhận tên resource.** Kiểm tra chữ hoa/thường, phần mở rộng, dấu `/` đầu tên và đường dẫn tương đối/tuyệt đối của API đang dùng.
2. **Xác nhận module hoặc class loader.** Lấy module từ class thực tế bằng `SomeClass.class.getModule()`; không giả định resource nằm trong class loader hệ thống.
3. **Xác nhận resource đã được đóng gói.** Với exploded module, kiểm tra file nằm dưới đúng thư mục package trong output. Với modular JAR, kiểm tra nội dung JAR.
4. **Xác định package chứa resource.** Lấy phần trước dấu `/` cuối cùng và đổi `/` thành dấu chấm. Ví dụ `com/acme/assets/internal/secret.txt` thuộc package `com.acme.assets.internal`.
5. **Kiểm tra open đối với đúng caller.** Dùng `targetModule.isOpen(packageName, callerModule)`. Với `ClassLoader.getResource`, kiểm tra package có open không điều kiện bằng `targetModule.isOpen(packageName)`.
6. **Nếu vẫn chưa rõ, dùng `ModuleReader`.** Nếu reader tìm thấy resource nhưng API lookup trả `null`, resource có trong artifact và vấn đề nằm ở quy tắc truy cập hoặc cách tra cứu. Nếu reader không tìm thấy, kiểm tra lại việc đóng gói và tên file.

Lưu ý: bước kiểm tra `isOpen` chỉ cho biết quyền mở package. Nó không xác nhận file tồn tại. Cần đối chiếu với nội dung module artifact để kết luận chính xác.

## 8. Các trường hợp đặc biệt và lỗi phổ biến

**Nhầm dấu `/` giữa các API**

`Class.getResource` dùng dấu `/` đầu tên để chỉ đường dẫn tuyệt đối. `ClassLoader.getResource` và `ModuleReader.find` nhận tên từ gốc, thường không có dấu `/` đầu. Sai quy tắc có thể khiến resource không được tìm thấy.

**Dùng `exports` để mở resource**

Export package không đủ cho resource dữ liệu trong named module. Dùng `opens` cho package và module cần truy cập.

**Dùng qualified open với ClassLoader**

Qualified open phục vụ caller-sensitive lookup như `Class.getResource` và `Module.getResourceAsStream`. `ClassLoader.getResource` cần package open không điều kiện đối với resource không phải `.class`.

**Resource nằm ngoài package**

Resource ở gốc module hoặc trong `META-INF` không thuộc package Java theo quy tắc encapsulation package. Không nên suy ra mọi resource đều cần `opens`.

**Nhầm `canRead` với quyền đọc resource**

`caller.canRead(target)` chỉ kiểm tra quan hệ readability. Nó không xác nhận package chứa resource đã mở cho caller. Một consumer có thể đọc module nhưng vẫn không đọc được resource trong package đóng.

**Resource trong classpath và resource trong named module**

Khi chạy trên classpath, code thuộc unnamed module và quy tắc encapsulation của named module không áp dụng theo cách tương tự. Khi chuyển ứng dụng sang module path, cùng một lời gọi resource có thể bắt đầu trả về `null` nếu package chưa được mở. Hãy kiểm tra module descriptor khi đóng gói lại thư viện thành named module.

**Class resource và resource dữ liệu**

Resource kết thúc bằng `.class` có ngoại lệ trong quy tắc encapsulation của class loader. Không lấy kết quả truy cập file class để suy ra rằng file `.properties` cùng package cũng có thể truy cập.

**Không đóng stream hoặc reader**

Đóng `InputStream` sau khi đọc. Đóng `ModuleReader` bằng try-with-resources; các thao tác tiếp theo trên reader đã đóng sẽ thất bại bằng `IOException`.

## 9. Checklist khi triển khai và chẩn đoán

1. Dùng đúng API theo nguồn resource: `Class`, `Module`, `ClassLoader` hoặc `ModuleReader`.
2. Dùng tên resource dạng `/`-separated path và đúng quy tắc dấu `/` đầu.
3. Xác nhận resource được sao chép vào exploded module hoặc đóng gói trong modular JAR.
4. Kiểm tra package chứa resource có phải package của named module hay không.
5. Với `Class.getResource` và `Module.getResourceAsStream`, kiểm tra package mở cho module caller.
6. Với `ClassLoader.getResource`, kiểm tra package mở không điều kiện; qualified open chưa đủ.
7. Không xem `null` là bằng chứng duy nhất cho resource không tồn tại.
8. Dùng `ModuleReader.find/open` khi cần xác minh nội dung module artifact độc lập với quyền truy cập thông thường.
9. Đóng stream và reader đúng cách, đồng thời xử lý `IOException`.

Khi phân biệt resource bị thiếu với resource bị giới hạn truy cập, hãy kiểm tra cả **nội dung artifact** lẫn **quyền mở package**. Kết quả `null` chỉ nói rằng API lookup hiện tại không cung cấp được resource; nó chưa cho biết nguyên nhân.