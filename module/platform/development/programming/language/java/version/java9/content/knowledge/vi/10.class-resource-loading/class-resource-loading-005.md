# Truy cập tài nguyên qua `Class`, `ClassLoader` hoặc `Module`

Java cho phép đọc tài nguyên được đóng gói cùng ứng dụng hoặc thư viện mà không cần biết chúng nằm trong thư mục thường hay bên trong JAR. Ba API thường dùng là `Class`, `ClassLoader` và `Module`. Chọn API dựa trên nơi tài nguyên thuộc về và ranh giới mô-đun:

- `Class` phù hợp khi tài nguyên nằm cạnh một lớp cụ thể và cần đường dẫn tương đối với package của lớp đó.
- `ClassLoader` phù hợp khi cần tìm tài nguyên theo đường dẫn gốc, liệt kê nhiều tài nguyên cùng tên hoặc làm việc với class loader do framework cung cấp.
- `Module` phù hợp khi muốn đọc trực tiếp tài nguyên thuộc một named module và tuân thủ quy tắc đóng gói của JPMS.

Từ Java 9, tài nguyên trong named module còn chịu quy tắc `opens`. Một package được `exports` cho API công khai chưa chắc đã cho phép mô-đun khác đọc các file `.properties`, `.xml` hoặc `.txt` nằm trong package đó.

## 1. Tài nguyên Java được lưu ở đâu?

Tài nguyên là file không nhất thiết là mã nguồn Java, ví dụ:

- `application.properties`, `messages.properties`.
- JSON, XML, YAML, CSV hoặc template.
- Ảnh, font, âm thanh và dữ liệu nhúng.
- File cấu hình mặc định nằm cạnh một class.

Ở thời điểm chạy, tài nguyên thường được lấy từ classpath, module path, runtime image hoặc một nguồn do class loader tùy chỉnh cung cấp. Khi đóng gói JAR, tên entry của tài nguyên là đường dẫn tương đối bên trong archive, sử dụng dấu `/`.

Ví dụ cấu trúc:

```text
com.example.assets/
├── module-info.java
└── com/example/assets/
    ├── Asset.java
    └── settings.txt
```

Trong JAR, `settings.txt` phải nằm tại `com/example/assets/settings.txt`. `javac` biên dịch `.java` nhưng không tự sao chép file `.txt` hoặc `.properties`; build tool hoặc bước đóng gói cần đưa tài nguyên vào đúng vị trí trong output.

## 2. Đọc tài nguyên bằng `Class`

`Class` cung cấp hai phương thức:

- `getResource(String name)` trả về `URL` hoặc `null`.
- `getResourceAsStream(String name)` trả về `InputStream` hoặc `null`.

Điểm quan trọng là cách diễn giải đường dẫn:

**Tên bắt đầu bằng `/` là đường dẫn tuyệt đối từ gốc tài nguyên.** Dấu `/` đầu tiên được bỏ đi khi tìm kiếm.

```java
URL absolute = Asset.class.getResource("/com/example/assets/settings.txt");
```

**Tên không bắt đầu bằng `/` là đường dẫn tương đối với package của lớp.**

```java
URL relative = Asset.class.getResource("settings.txt");
```

Nếu `Asset` thuộc package `com.example.assets`, tên tương đối trên tìm `com/example/assets/settings.txt`.

### Khi nào dùng `Class`?

Dùng `Class` khi tài nguyên thuộc về một kiểu cụ thể và muốn tránh phụ thuộc vào vị trí gốc của classpath:

```java
try (InputStream input = Asset.class.getResourceAsStream("settings.txt")) {
    if (input == null) {
        throw new IllegalStateException("Missing settings.txt");
    }
    // Đọc nội dung input tại đây.
}
```

Cách này tiện cho thư viện vì file cấu hình có thể được đặt cạnh class sở hữu nó. Khi đổi package, đường dẫn tương đối vẫn đi theo package mới.

## 3. Đọc tài nguyên bằng `ClassLoader`

`ClassLoader` tìm tài nguyên theo tên đường dẫn từ gốc, không gắn với package của một lớp cụ thể.

```java
ClassLoader loader = Asset.class.getClassLoader();
URL url = loader.getResource("com/example/assets/settings.txt");
InputStream input = loader.getResourceAsStream("com/example/assets/settings.txt");
```

Với `ClassLoader`, không thêm dấu `/` ở đầu tên tài nguyên. `getResource("/com/example/assets/settings.txt")` thường không tìm thấy vì class loader không loại bỏ dấu `/` như `Class.getResource`.

Các phương thức chính:

| Phương thức | Kết quả |
| --- | --- |
| `getResource(name)` | `URL` đầu tiên tìm thấy hoặc `null` |
| `getResourceAsStream(name)` | `InputStream` đầu tiên tìm thấy hoặc `null` |
| `getResources(name)` | `Enumeration<URL>` chứa các kết quả tìm được |

`getResources` hữu ích khi nhiều JAR cùng cung cấp một file có cùng tên, chẳng hạn metadata hoặc file đăng ký extension. Ứng dụng cần xác định cách hợp nhất hoặc lựa chọn kết quả thay vì giả định chỉ có một file.

### Chọn class loader nào?

```java
ClassLoader definingLoader = Asset.class.getClassLoader();
ClassLoader contextLoader = Thread.currentThread().getContextClassLoader();
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
```

- Class loader của lớp phù hợp khi tài nguyên thuộc thư viện hoặc module đã nạp lớp đó.
- Thread context class loader thường được framework và ứng dụng host dùng để tìm tài nguyên do ứng dụng/plugin cung cấp.
- System class loader tìm tài nguyên theo class path/module path của ứng dụng khởi chạy.

Không phải class nào cũng có class loader khác `null`: lớp được nạp bởi bootstrap class loader, như `String`, có `getClassLoader()` trả về `null`. Nếu dùng class loader từ một lớp bất kỳ, hãy xử lý trường hợp này hoặc dùng API `Class`/`ClassLoader.getSystemResource` phù hợp.

## 4. Đọc tài nguyên trực tiếp bằng `Module`

Java 9 bổ sung `Module.getResourceAsStream(String name)`. Phương thức này đọc tài nguyên từ chính module được đại diện bởi đối tượng `Module`.

```java
Module module = Asset.class.getModule();
try (InputStream input = module.getResourceAsStream(
        "com/example/assets/settings.txt")) {
    if (input == null) {
        throw new IllegalStateException("Resource is missing or not accessible");
    }
    // Đọc nội dung input tại đây.
}
```

Tên tài nguyên là đường dẫn từ gốc module, dùng dấu `/` và không thêm dấu `/` ở đầu. Phương thức trả về `null` nếu không tìm thấy tài nguyên hoặc tài nguyên không được phép truy cập theo quy tắc đóng gói mô-đun; lỗi I/O có thể được báo bằng `IOException`.

`Module.getResourceAsStream` hữu ích khi đã có đối tượng module và muốn đọc một tài nguyên thuộc đúng module đó. Nó cũng giúp code diễn đạt rõ tài nguyên đến từ module nào thay vì phụ thuộc vào thứ tự tìm kiếm của class loader.

## 5. Quy tắc `exports` và `opens` khi dùng JPMS

Đối với tài nguyên thông thường nằm trong một package của named module, JPMS kiểm soát quyền truy cập qua trạng thái mở package:

- `exports` cho phép mô-đun khác truy cập các kiểu `public` được công bố trong package. `exports` không tự cho phép đọc tài nguyên không phải class nằm trong package đó.
- `opens` cho phép truy cập phản chiếu sâu và đọc tài nguyên trong package ở runtime.
- Qualified `opens package.name to consumer.module;` chỉ mở package cho các module được chỉ định.
- Unqualified `opens package.name;` mở package cho mọi module theo cơ chế runtime.

Ví dụ descriptor của module chứa tài nguyên:

```java
module com.example.assets {
    exports com.example.assets;
    opens com.example.assets to com.example.app;
}
```

`exports` cho phép ứng dụng import lớp `Asset`. `opens` cho phép `com.example.app` đọc tài nguyên `settings.txt` nằm trong package `com.example.assets`.

### Khác biệt quan trọng giữa ba API

Khi một package chỉ được mở có điều kiện cho `com.example.app`:

| Cách đọc từ `com.example.app` | Kết quả | Lý do |
| --- | --- | --- |
| `Asset.class.getResource("settings.txt")` | Có thể truy cập | `Class` kiểm tra quyền của module gọi; package đã mở cho app |
| `Asset.class.getModule().getResourceAsStream("com/example/assets/settings.txt")` | Có thể truy cập | `Module` kiểm tra quyền của module gọi; package đã mở cho app |
| `Asset.class.getClassLoader().getResource("com/example/assets/settings.txt")` | Không truy cập được | `ClassLoader` không có module gọi để áp dụng qualified open; tài nguyên trong named module chỉ được tìm thấy qua class loader khi package được mở không điều kiện |

Vì vậy, nếu muốn dùng `ClassLoader.getResource` để tìm tài nguyên trong package của named module, package phải được mở không điều kiện, ví dụ:

```java
module com.example.assets {
    exports com.example.assets;
    opens com.example.assets;
}
```

Nếu không mở package, các API `Class` và `Module` gọi từ module khác cũng có thể trả về `null`. Một package được export nhưng không mở vẫn bị đóng gói đối với tài nguyên thông thường. Tài nguyên class file có quy tắc ngoại lệ riêng; quy tắc ở đây tập trung vào file dữ liệu như `.txt` và `.properties`.

Không nên mở toàn bộ module hoặc nhiều package hơn nhu cầu chỉ để đọc một file. Qualified `opens` giữ phạm vi truy cập nhỏ hơn.

## 6. Ví dụ hoàn chỉnh: một resource trong named module

Ví dụ này có hai module:

- `com.example.assets` chứa lớp `Asset` và file `settings.txt`.
- `com.example.app` đọc tài nguyên qua `Class`, `ClassLoader` và `Module`.

### Cấu trúc thư mục

```text
src/
├── com.example.assets/
│   ├── module-info.java
│   └── com/example/assets/
│       ├── Asset.java
│       └── settings.txt
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

`src/com.example.assets/module-info.java`:

```java
module com.example.assets {
    exports com.example.assets;
    opens com.example.assets to com.example.app;
}
```

`src/com.example.assets/com/example/assets/Asset.java`:

```java
package com.example.assets;

public final class Asset {
    private Asset() { }
}
```

`src/com.example.assets/com/example/assets/settings.txt`:

```text
theme=dark
```

`src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.assets;
}
```

`src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.assets.Asset;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class Main {
    private static String read(InputStream input) throws Exception {
        if (input == null) {
            return "<not found or not accessible>";
        }
        try (InputStream in = input) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        String path = "com/example/assets/settings.txt";
        URL relative = Asset.class.getResource("settings.txt");
        URL absolute = Asset.class.getResource("/" + path);
        URL viaLoader = Asset.class.getClassLoader().getResource(path);

        System.out.println("relative Class URL = " + (relative != null));
        System.out.println("absolute Class URL = " + (absolute != null));
        System.out.println("ClassLoader URL = " + (viaLoader != null));
        System.out.println("Class resource = "
                + read(Asset.class.getResourceAsStream("settings.txt")));
        System.out.println("Module resource = "
                + read(Asset.class.getModule().getResourceAsStream(path)));
    }
}
```

### Biên dịch và chạy

Chạy từ thư mục gốc chứa `src/` bằng JDK 17 trở lên:

```bash
mkdir -p out
javac --module-source-path src -d out -m com.example.assets,com.example.app
cp src/com.example.assets/com/example/assets/settings.txt \
   out/com.example.assets/com/example/assets/
java --module-path out --module com.example.app/com.example.app.Main
```

`javac` tạo thư mục package và file class nhưng không sao chép `settings.txt`. Lệnh `cp` đặt resource vào đúng package path trong exploded module. Trên PowerShell, bước sao chép tương đương:

```powershell
Copy-Item src/com.example.assets/com/example/assets/settings.txt `
    out/com.example.assets/com/example/assets/
```

Kết quả:

```text
relative Class URL = true
absolute Class URL = true
ClassLoader URL = false
Class resource = theme=dark
Module resource = theme=dark
```

`Class` và `Module` đọc được vì `com.example.assets` mở package có phạm vi cho `com.example.app`. `ClassLoader` không đọc được vì package chỉ qualified-open, chưa mở không điều kiện.

### Thử thay đổi `opens`

**Trường hợp 1 — không có `opens`:** giữ `exports com.example.assets;` nhưng xóa directive `opens`. Khi đó cả hai lệnh `Asset.class.getResource(...)` và `Module.getResourceAsStream(...)` từ ứng dụng trả về `null`; class loader cũng không tìm thấy tài nguyên. `exports` không đủ để đọc file dữ liệu trong package.

**Trường hợp 2 — mở không điều kiện:** thay qualified open bằng:

```java
opens com.example.assets;
```

Khi chạy lại, cả ba cách tra cứu đều tìm thấy tài nguyên:

```text
relative Class URL = true
absolute Class URL = true
ClassLoader URL = true
Class resource = theme=dark
Module resource = theme=dark
```

Đây là khác biệt quan trọng khi thiết kế thư viện modular: nếu chỉ cần cho một module cụ thể đọc file, qualified `opens` kết hợp với `Class` hoặc `Module` thường có phạm vi quyền phù hợp hơn.

## 7. Xử lý `URL`, `InputStream` và nhiều kết quả

### Luôn đóng stream

`getResourceAsStream` trả về stream cần được đóng. Dùng try-with-resources:

```java
try (InputStream input = Main.class.getResourceAsStream("defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("defaults.properties not found");
    }
    properties.load(input);
}
```

Không giữ stream mở lâu hơn thời gian cần thiết; điều này đặc biệt quan trọng khi đọc tài nguyên từ JAR.

### Không giả định URL là file trên đĩa

URL có thể dùng giao thức `file:`, `jar:`, `jrt:` hoặc giao thức do class loader tùy chỉnh cung cấp. Không nên chuyển mọi URL thành `File` bằng cách lấy `url.getPath()` hoặc `new File(url.toURI())`.

Nếu cần đọc nội dung, dùng `url.openStream()` trong try-with-resources. Nếu cần hiển thị hoặc lưu địa chỉ, giữ nguyên URL.

### Liệt kê tất cả tài nguyên trùng tên

```java
Enumeration<URL> resources = loader.getResources("META-INF/example/extensions");
while (resources.hasMoreElements()) {
    URL resource = resources.nextElement();
    System.out.println(resource);
}
```

`getResource` chỉ trả về một kết quả; `getResources` trả về tất cả kết quả mà class loader tìm được. Khi nhiều thư viện cung cấp cùng một resource, hãy xác định quy tắc hợp nhất, thứ tự ưu tiên hoặc loại trùng phù hợp với ứng dụng.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Class.getResource("settings.txt")` trả về `null` | Tên tương đối được tìm trong package của class; file nằm ở vị trí khác | Kiểm tra package path hoặc dùng tên tuyệt đối bắt đầu bằng `/` |
| `ClassLoader.getResource("/config/app.properties")` trả về `null` | ClassLoader không loại bỏ dấu `/` đầu tên | Dùng `config/app.properties` |
| `Module.getResourceAsStream` trả về `null` | Sai đường dẫn, file chưa được đóng gói hoặc package không mở cho module gọi | Kiểm tra module descriptor và vị trí resource trong output/JAR |
| Resource hoạt động trên classpath nhưng thất bại trên module path | JPMS đang áp dụng quy tắc encapsulation | Mở đúng package bằng qualified hoặc unqualified `opens` |
| Package đã `exports` nhưng resource vẫn không đọc được | `exports` công bố API Java; nó không thay thế `opens` cho tài nguyên dữ liệu | Thêm `opens` đúng phạm vi nếu cần đọc resource từ module khác |
| Chạy từ IDE được nhưng chạy từ JAR thất bại | Build không sao chép resource vào JAR hoặc sai entry path | Kiểm tra nội dung JAR bằng `jar --list --file app.jar` |
| Đọc stream gây lỗi hoặc giữ file/JAR mở | Stream không được đóng | Dùng try-with-resources |
| Chuyển URL thành `File` thất bại | Resource nằm trong JAR hoặc nguồn không phải filesystem | Dùng `URL.openStream()` hoặc `getResourceAsStream()` |

## 9. Chọn API nào?

| Nhu cầu | API nên dùng |
| --- | --- |
| File cấu hình nằm cạnh class | `Class.getResource` hoặc `getResourceAsStream` |
| Đường dẫn tính từ gốc tài nguyên | `ClassLoader.getResource` |
| Đọc tài nguyên từ một named module cụ thể | `Module.getResourceAsStream` |
| Tìm tất cả file cùng tên do nhiều thư viện cung cấp | `ClassLoader.getResources` |
| Framework cần tìm tài nguyên do ứng dụng host cung cấp | Context class loader, theo hợp đồng của framework |

## Ghi nhớ

- `Class.getResource`: tên có `/` đầu là tuyệt đối; không có `/` đầu là tương đối với package của class.
- `ClassLoader.getResource` và `Module.getResourceAsStream`: dùng đường dẫn từ gốc, không có `/` đầu.
- `Class` và `ClassLoader` trả URL; các phương thức `getResourceAsStream` trả stream.
- `Module.getResourceAsStream` đọc resource thuộc module cụ thể và tuân theo encapsulation của JPMS.
- `exports` không đồng nghĩa `opens`; resource dữ liệu trong package của named module thường cần package mở cho module gọi.
- Qualified `opens` phù hợp khi chỉ một module cần truy cập; `ClassLoader` chỉ tìm thấy resource trong package được mở không điều kiện.
- Luôn kiểm tra `null`, đóng stream và không giả định URL tương ứng với file trên filesystem.

## Tài liệu tham khảo

- [Java SE 17 API — `Class.getResource`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String))
- [Java SE 17 API — `ClassLoader.getResource`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getResource(java.lang.String))
- [Java SE 17 API — `Module.getResourceAsStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String))
- [Java Language Specification — Module Declarations and `opens`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2)