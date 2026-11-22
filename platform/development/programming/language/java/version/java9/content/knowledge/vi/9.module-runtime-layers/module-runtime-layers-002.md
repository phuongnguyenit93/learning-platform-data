# Kiểm tra khả năng đọc và quyền truy cập package bằng `Module`

JPMS (Java Platform Module System) kiểm soát việc các mô-đun nhìn thấy và sử dụng nhau qua ba khía cạnh riêng:

- **Readability — khả năng đọc:** mô-đun hiện tại có đọc được mô-đun đích hay không. API kiểm tra là `Module.canRead(Module)`.
- **Export — công khai package:** package của mô-đun nguồn có được công khai cho mô-đun gọi hay không. API kiểm tra là `Module.isExported(String)` và `Module.isExported(String, Module)`.
- **Open — mở package cho reflection:** mô-đun nguồn có cho phép mô-đun gọi deep reflection vào package hay không. API kiểm tra là `Module.isOpen(String)` và `Module.isOpen(String, Module)`.

Ba API này trả lời những câu hỏi khác nhau. Một mô-đun có thể đọc được mô-đun khác nhưng không truy cập được package chưa export; một package có thể mở cho reflection mà không được export trong module descriptor; và các phương thức kiểm tra export/open không tự xác nhận quan hệ readability.

Các API `Module` này có từ Java 9 và phản ánh trạng thái mô-đun tại runtime. Chúng hữu ích khi viết framework, plugin loader, công cụ chẩn đoán hoặc kiểm tra quyền truy cập trước khi dùng reflection.

## 1. Lấy đối tượng `Module` cần kiểm tra

Trước khi gọi các phương thức, cần có đúng hai đối tượng `Module`: mô-đun đang gọi và mô-đun chứa package cần kiểm tra.

**Lấy module của class hiện tại:**

```java
Module caller = Main.class.getModule();
```

**Lấy module của một class đã được nạp:**

```java
Module target = SecretInfo.class.getModule();
```

Hoặc khi chỉ biết tên lớp tại runtime:

```java
Module target = Class
    .forName("com.acme.secret.api.SecretInfo")
    .getModule();
```

**Lấy module theo tên trong một layer:**

```java
Module target = ModuleLayer.boot()
    .findModule("com.acme.secret")
    .orElseThrow();
```

`ModuleLayer.boot().findModule(...)` trả về `Optional<Module>`. Mô-đun phải có mặt trong layer đang tra cứu; nếu chưa được phân giải vào boot layer, kết quả sẽ rỗng. Khi chạy ví dụ bên dưới, `com.acme.other` được thêm làm root bằng `--add-modules`.

Lưu ý hướng kiểm tra: `caller.canRead(target)` hỏi **caller có đọc target không**. Đảo hai đối tượng sẽ trả lời câu hỏi khác.

## 2. Kiểm tra readability bằng `canRead`

Cú pháp:

```java
boolean canRead = caller.canRead(target);
```

`canRead` trả về `true` nếu mô-đun gọi đọc được mô-đun đích trong đồ thị readability hiện tại.

Quan hệ đọc có thể đến từ:

- Chỉ thị `requires` trực tiếp trong `module-info.java`.
- Các quan hệ readability được truyền qua `requires transitive`.
- Quy tắc của automatic module và unnamed module.
- Các cạnh readability được thêm trong runtime bằng cơ chế như `Module.addReads` hoặc tùy chọn khởi chạy tương ứng.

Một named module luôn đọc chính nó. Unnamed module đọc tất cả mô-đun. Vì vậy, khi kiểm tra mã chạy trên classpath, `canRead` thường trả về `true` cho mọi module đích.

Ví dụ:

```java
Module caller = Main.class.getModule();
Module target = SecretInfo.class.getModule();

System.out.println(caller.canRead(target));
```

Nếu `com.acme.inspector` khai báo:

```java
module com.acme.inspector {
    requires com.acme.secret;
}
```

thì `caller.canRead(target)` trả về `true` khi `target` là module `com.acme.secret`.

Nếu một mô-đun không có quan hệ đọc với mô-đun khác, kết quả là `false`, ngay cả khi package của mô-đun nguồn được export công khai cho mọi mô-đun. `canRead` không kiểm tra package export hay open.

## 3. Kiểm tra export bằng `isExported`

Có hai overload thường dùng.

**Kiểm tra package có được export không điều kiện:**

```java
boolean exportedToEveryone =
    target.isExported("com.acme.secret.api");
```

Overload một tham số kiểm tra package có được export không điều kiện cho mọi mô-đun hay không. Một qualified export chỉ dành cho một số mô-đun sẽ không làm overload này trả về `true`.

**Kiểm tra package có được export cho một mô-đun cụ thể:**

```java
boolean exportedToCaller =
    target.isExported("com.acme.secret.spi", caller);
```

Overload hai tham số hữu ích khi module descriptor dùng qualified export:

```java
module com.acme.secret {
    exports com.acme.secret.api;
    exports com.acme.secret.spi to com.acme.inspector;
}
```

Khi đó:

- `com.acme.secret.api` được export không điều kiện.
- `com.acme.secret.spi` chỉ được export cho `com.acme.inspector`.
- Một mô-đun khác không nằm trong danh sách `to` không được nhận quyền export đó.

**Chi tiết runtime cần nhớ:** `Module.isExported(packageName, other)` kiểm tra package có được export **hoặc mở** cho mô-đun đích hay không. Tương tự, overload một tham số xem package được export hoặc mở không điều kiện. Vì vậy, nếu package chỉ được khai báo bằng `opens` cho caller, `isExported(packageName, caller)` vẫn có thể trả về `true` ở runtime.

Điều này không biến `opens` thành chỉ thị `exports` trong module descriptor và không cho phép mã nguồn import package đó khi biên dịch. Nếu cần biết module descriptor khai báo `exports` hay `opens` cụ thể, hãy kiểm tra `Module.getDescriptor().exports()` và `Module.getDescriptor().opens()` thay vì suy luận chỉ từ `isExported`.

Các phương thức `isExported` không kiểm tra mô-đun gọi có đọc mô-đun nguồn hay không. Hãy kiểm tra thêm `canRead` khi cần xác minh đầy đủ điều kiện truy cập qua named modules.

## 4. Kiểm tra open package bằng `isOpen`

`isOpen` kiểm tra quyền mở package cho deep reflection.

**Kiểm tra package có được mở không điều kiện:**

```java
boolean openToEveryone =
    target.isOpen("com.acme.secret.model");
```

**Kiểm tra package có được mở cho một mô-đun cụ thể:**

```java
boolean openToCaller =
    target.isOpen("com.acme.secret.model", caller);
```

Ví dụ module descriptor:

```java
module com.acme.secret {
    opens com.acme.secret.model to com.acme.inspector;
}
```

Chỉ thị này cho phép code thuộc `com.acme.inspector` dùng deep reflection trên các kiểu trong package `com.acme.secret.model`, chẳng hạn truy cập private field hoặc private constructor sau khi gọi `trySetAccessible()` thành công.

`isOpen` khác `isExported` ở mục đích:

- Export công khai API cho truy cập thông thường từ mô-đun khác, theo các modifier truy cập Java.
- Open cho phép deep reflection vào các kiểu trong package.
- Package được mở cho một mô-đun cụ thể cũng được xem là exported cho mô-đun đó tại runtime, nhưng không trở thành package có thể import từ mã nguồn bên ngoài.
- `isOpen` không kiểm tra mô-đun đích có đọc mô-đun nguồn hay không.

Một `open module` mở tất cả package của nó cho deep reflection ở runtime. Tuy nhiên, điều đó không tự động biến tất cả package thành API compile-time được export trong module descriptor. Unnamed module cũng có các package được xem là exported và opened ở runtime.

## 5. Ví dụ hoàn chỉnh: kiểm tra ba trạng thái giữa các mô-đun

Ví dụ có ba named modules:

- `com.acme.secret`: mô-đun chứa API, SPI và model nội bộ.
- `com.acme.inspector`: mô-đun thực hiện kiểm tra.
- `com.acme.other`: mô-đun độc lập, không đọc `com.acme.secret`.

Cấu trúc:

```text
src/
├── com.acme.secret/
│   ├── module-info.java
│   └── com/acme/secret/
│       ├── api/SecretInfo.java
│       ├── spi/InternalSpi.java
│       └── model/Account.java
├── com.acme.inspector/
│   ├── module-info.java
│   └── com/acme/inspector/Main.java
└── com.acme.other/
    ├── module-info.java
    └── com/acme/other/Other.java
```

**Module descriptor của mô-đun nguồn — `src/com.acme.secret/module-info.java`:**

```java
module com.acme.secret {
    exports com.acme.secret.api;
    exports com.acme.secret.spi to com.acme.inspector;
    opens com.acme.secret.model to com.acme.inspector;
}
```

**Package API được export không điều kiện — `SecretInfo.java`:**

```java
package com.acme.secret.api;

public final class SecretInfo {
    public static String version() {
        return "1.0";
    }
}
```

**Package SPI chỉ export cho inspector — `InternalSpi.java`:**

```java
package com.acme.secret.spi;

public interface InternalSpi {
    String execute();
}
```

**Package model được mở cho reflection — `Account.java`:**

```java
package com.acme.secret.model;

public final class Account {
    private final String id = "A-101";

    private Account() {}
}
```

**Module descriptor của mô-đun kiểm tra — `src/com.acme.inspector/module-info.java`:**

```java
module com.acme.inspector {
    requires com.acme.secret;
}
```

**Mô-đun độc lập — `src/com.acme.other/module-info.java`:**

```java
module com.acme.other {
}
```

**Chương trình kiểm tra — `src/com.acme.inspector/com/acme/inspector/Main.java`:**

```java
package com.acme.inspector;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Exception {
        Module caller = Main.class.getModule();
        Module secret = Class
            .forName("com.acme.secret.api.SecretInfo")
            .getModule();
        Module other = ModuleLayer.boot()
            .findModule("com.acme.other")
            .orElseThrow();

        System.out.println("inspector reads secret: "
            + caller.canRead(secret));
        System.out.println("inspector reads other: "
            + caller.canRead(other));
        System.out.println("other reads secret: "
            + other.canRead(secret));

        System.out.println("api exported to all: "
            + secret.isExported("com.acme.secret.api"));
        System.out.println("api exported to other: "
            + secret.isExported("com.acme.secret.api", other));
        System.out.println("spi exported to all: "
            + secret.isExported("com.acme.secret.spi"));
        System.out.println("spi exported to inspector: "
            + secret.isExported("com.acme.secret.spi", caller));
        System.out.println("spi exported to other: "
            + secret.isExported("com.acme.secret.spi", other));

        System.out.println("model open to all: "
            + secret.isOpen("com.acme.secret.model"));
        System.out.println("model open to inspector: "
            + secret.isOpen("com.acme.secret.model", caller));
        System.out.println("model open to other: "
            + secret.isOpen("com.acme.secret.model", other));
        System.out.println("api open to inspector: "
            + secret.isOpen("com.acme.secret.api", caller));
        System.out.println("model exported to inspector at runtime: "
            + secret.isExported("com.acme.secret.model", caller));
        System.out.println("model exported to all: "
            + secret.isExported("com.acme.secret.model"));

        Class<?> accountType =
            Class.forName("com.acme.secret.model.Account");
        Constructor<?> constructor =
            accountType.getDeclaredConstructor();

        if (!constructor.trySetAccessible()) {
            throw new IllegalStateException("Constructor is not open");
        }
        Object account = constructor.newInstance();

        Field id = accountType.getDeclaredField("id");
        if (!id.trySetAccessible()) {
            throw new IllegalStateException("Field is not open");
        }

        System.out.println("deep reflection: " + id.get(account));
    }
}
```

Biên dịch từ thư mục gốc dự án bằng JDK 17 trở lên:

**PowerShell:**

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --module-source-path src -d out -m com.acme.secret,com.acme.inspector,com.acme.other
```

**Bash:**

```bash
mkdir -p out
javac --module-source-path src -d out -m com.acme.secret,com.acme.inspector,com.acme.other
```

Chạy ứng dụng và thêm `com.acme.other` làm root để nó có mặt trong boot layer:

```bash
java --module-path out --add-modules com.acme.other -m com.acme.inspector/com.acme.inspector.Main
```

Kết quả:

```text
inspector reads secret: true
inspector reads other: false
other reads secret: false
api exported to all: true
api exported to other: true
spi exported to all: false
spi exported to inspector: true
spi exported to other: false
model open to all: false
model open to inspector: true
model open to other: false
api open to inspector: false
model exported to inspector at runtime: true
model exported to all: false
deep reflection: A-101
```

Cách đọc kết quả:

- Inspector đọc được secret vì descriptor có `requires com.acme.secret`.
- Inspector không đọc other và other cũng không đọc secret vì không có cạnh readability tương ứng.
- API được export không điều kiện nên `isExported(api)` và `isExported(api, other)` đều là `true`. Kết quả này không tự tạo readability cho `other`.
- SPI được qualified export nên chỉ inspector nhận được quyền export.
- Model chỉ được mở cho inspector. Do đó `isOpen(model, inspector)` là `true`, còn `isOpen(model)` và `isOpen(model, other)` là `false`.
- `isExported(model, inspector)` cũng trả về `true` ở runtime vì package được mở cho inspector. Nhưng `isExported(model)` vẫn là `false` vì package không được mở hoặc export không điều kiện.
- `trySetAccessible()` thành công cho private constructor và private field, nên chương trình đọc được giá trị `A-101`.

Ví dụ này cho thấy không thể dùng một boolean duy nhất để kết luận toàn bộ quyền truy cập. Cần kiểm tra đúng quan hệ mà thao tác sắp thực hiện yêu cầu.

## 6. Phân biệt kết quả runtime với module descriptor

Các phương thức `Module` kiểm tra trạng thái runtime. Trạng thái này có thể phản ánh:

- Các chỉ thị `requires`, `exports`, `opens` trong module descriptor.
- Quy tắc mặc định của unnamed module, automatic module hoặc open module.
- Các thay đổi động được thêm qua `Module.addReads`, `Module.addExports`, `Module.addOpens`.
- Các tùy chọn khởi chạy như `--add-reads`, `--add-exports`, `--add-opens`.

Nếu cần kiểm tra **module descriptor khai báo gì**, lấy descriptor:

```java
var descriptor = target.getDescriptor();

if (descriptor != null) {
    System.out.println(descriptor.exports());
    System.out.println(descriptor.opens());
}
```

`ModuleDescriptor.exports()` và `ModuleDescriptor.opens()` cho biết các directive trong descriptor. Chúng không phải phép kiểm tra tổng hợp trạng thái runtime sau mọi thay đổi động. Đối với unnamed module, `getDescriptor()` có thể trả về `null`.

Đặc biệt, không dùng `isExported` để suy ra rằng descriptor chắc chắn có một `exports` directive: package được mở cũng được xem là exported ở runtime theo API này.

## 7. Lỗi thường gặp và cách chẩn đoán

**Gọi `target.canRead(caller)` thay vì `caller.canRead(target)`**

Hãy xác định ai đang thực hiện thao tác và ai là mô-đun chứa package. `canRead` được gọi trên mô-đun cần có khả năng đọc.

**`canRead` là true nhưng vẫn không import được class**

Readability chỉ cho biết mô-đun có đọc mô-đun đích. Package vẫn phải được export cho caller, và class/member vẫn phải đáp ứng modifier truy cập Java.

**`isExported` trả true nhưng không tìm thấy `exports` trong descriptor**

Kiểm tra `opens`: package mở cho caller cũng được xem là exported ở runtime. Nếu cần phân biệt directive, xem `getDescriptor().exports()` và `getDescriptor().opens()`.

**`isOpen` là false dù class có public**

Public không đồng nghĩa package được mở cho deep reflection. Nếu framework cần truy cập private hoặc bỏ qua kiểm tra truy cập thông thường, package phải được mở cho mô-đun framework bằng `opens` hoặc cơ chế runtime phù hợp.

**Dùng overload một tham số cho qualified export/open**

`isExported(packageName)` và `isOpen(packageName)` hỏi quyền không điều kiện. Với directive có mệnh đề `to`, phải truyền đúng đối tượng `Module` đích vào overload hai tham số.

**Tra cứu module không có trong layer**

`ModuleLayer.findModule` chỉ tìm trong layer được gọi. Xác nhận module đã được phân giải vào layer đó; có thể cần thêm root module bằng `--add-modules` khi chạy.

**Kiểm tra nhầm package**

Tham số đầu tiên là tên package đầy đủ, ví dụ `com.acme.secret.model`, không phải tên class hay đường dẫn thư mục. Package phải thuộc module đang được kiểm tra.

## 8. Checklist khi kiểm tra quyền truy cập

1. Lấy đúng `Module` của caller và module chứa class/package đích.
2. Dùng `caller.canRead(target)` để kiểm tra readability.
3. Dùng `target.isExported(packageName, caller)` để kiểm tra quyền truy cập package ở runtime.
4. Dùng `target.isOpen(packageName, caller)` khi cần deep reflection.
5. Với qualified export/open, luôn truyền đúng module đích vào overload hai tham số.
6. Không suy ra directive `exports` chỉ từ kết quả `isExported`; package được mở cũng được xem là exported ở runtime.
7. Nếu cần biết khai báo tĩnh, kiểm tra `ModuleDescriptor`; nếu cần biết trạng thái hiện tại, kiểm tra `Module`.
8. Khi reflection thất bại, kiểm tra `isOpen` và xử lý kết quả `trySetAccessible()` trước khi truy cập member.

`canRead`, `isExported` và `isOpen` là ba phép kiểm tra bổ sung cho nhau. Dùng đúng phương thức và đúng hướng module giúp chẩn đoán chính xác lỗi readability, lỗi package access và lỗi deep reflection trong các ứng dụng Java mô-đun.
