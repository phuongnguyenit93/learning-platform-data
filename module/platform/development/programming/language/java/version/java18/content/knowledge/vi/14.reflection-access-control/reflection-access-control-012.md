# Phân biệt --add-exports với --add-opens khi chẩn đoán lỗi truy cập

> **Chương:** Quyền reflection — **mô-đun:** `JAVA_VERSION_JAVA18`. Bài học phân tích hợp đồng truy cập của Java Platform Module System (JPMS), nhất là khi sử dụng `Class`, `Method`, `Field`, `Constructor`, `AccessibleObject` và `MethodHandles`. Hai tùy chọn `--add-exports` và `--add-opens` vẫn hữu ích để chẩn đoán lỗi trên JDK hiện đại, nhưng chúng mở **hai mức quyền khác nhau**. Ưu tiên sửa thiết kế module hoặc nâng cấp thư viện hơn là giữ các tùy chọn mở quyền quá rộng trong production.

Một lỗi `IllegalAccessException` khi gọi phương thức công khai của lớp nằm trong package không được export **không giống** lỗi `InaccessibleObjectException` khi cố dùng `setAccessible(true)` trên field private. Trường hợp thứ nhất thường liên quan quyền truy cập **public API** qua ranh giới module; trường hợp thứ hai liên quan **deep reflection** — thao tác cố tình bỏ qua các kiểm tra quyền truy cập theo ngôn ngữ Java.

Hai tùy chọn chẩn đoán tương ứng:

- `--add-exports source.module/package=target.module`: bổ sung quyền *export package*, để code ở module đích truy cập các kiểu `public` và thành viên `public` được phép của chúng, khi các điều kiện truy cập khác thỏa mãn.
- `--add-opens source.module/package=target.module`: mở package cho module đích thực hiện **deep reflection tại runtime**, bao gồm khả năng gọi `trySetAccessible()` hoặc `setAccessible(true)` để truy cập thành viên không công khai.

Không có tùy chọn nào biến `private` thành `public` trong source Java, tự thêm dependency `requires` cho mọi tình huống hoặc sửa lỗi signature/method không tồn tại. Cần chẩn đoán đúng ranh giới trước khi thêm flag.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt ba khái niệm **module readability**, **exports** và **opens** trong JPMS.
2. Chọn `--add-exports` cho trường hợp cần truy cập **public API** trong package chưa export, nhất là khi biên dịch hoặc liên kết mã.
3. Chọn `--add-opens` khi một framework cần **deep reflection** vào field/method/constructor không công khai ở runtime.
4. Giải thích sự khác nhau giữa `IllegalAccessException`, `InaccessibleObjectException`, lỗi biên dịch và `IllegalAccessError`.
5. Dùng `AccessibleObject.trySetAccessible()`, `canAccess()`, `Module.isExported()` và `Module.isOpen()` để thu thập bằng chứng.
6. Chạy ví dụ có **hai named modules** để quan sát kết quả trước và sau từng flag.
7. Đề xuất cách sửa bền vững trong `module-info.java` thay vì duy trì flags mở quyền vô hạn.

## 2. Ba ranh giới phải tách biệt

JPMS bổ sung các ranh giới module ngoài `public`, `protected`, package-private và `private` của Java. Để dùng một type trong package của module khác, cần xem ba điều kiện riêng biệt.

| Ranh giới | Ví dụ | Tác dụng |
|---|---|---|
| **Readability** | `requires demo.vault;` | Module caller đọc được module chứa API |
| **Exports** | `exports vault.api;` | Cho code ở module khác sử dụng các type `public` trong package và các thành viên công khai tương ứng |
| **Opens** | `opens vault.internal to demo.client;` | Cho module cụ thể thực hiện reflective access sâu vào package tại runtime |

Một module có thể **được đọc** nhưng package của nó vẫn không được export. Một lớp có thể được tìm thấy theo tên bằng `Class.forName(...)` nhưng Java vẫn từ chối gọi constructor hoặc đọc field của lớp đó. Khả năng **tìm metadata** không đồng nghĩa có quyền **sử dụng member**.

### 2.1. `exports` không đồng nghĩa `opens`

Trong `module-info.java`:

```java
module demo.vault {
    exports vault.api;
    opens vault.model to demo.client;
}
```

- `vault.api` được export: caller có quyền truy cập bình thường tới `public` API khi module readability phù hợp. Export **không** tự cấp quyền đọc field private bằng reflection.
- `vault.model` được mở riêng cho `demo.client`: tại runtime, code trong module đó có thể thực hiện deep reflection nếu gọi API bật access phù hợp. Việc mở package **không** cấp quyền import những lớp trong package đó vào source của một module khác tại compile time.

Có thể dùng cú pháp có danh sách module đích, ví dụ `exports vault.api to demo.client, demo.tool;` hoặc `opens vault.model to demo.client, demo.tool;`. Trong dự án thật, ưu tiên target nhỏ nhất có thể.

### 2.2. `opens` không tự gọi `setAccessible`

Khi package đã mở, field private **vẫn là private**. Code reflection thường vẫn phải yêu cầu bỏ kiểm tra quyền với `trySetAccessible()` hoặc `setAccessible(true)` trước khi `Field.get`, `Field.set` hay `Method.invoke` trên private member. `--add-opens` cho phép yêu cầu đó thành công, chứ không tự biến private member thành public.

### 2.3. Open package cũng có ý nghĩa runtime với public types

Tại runtime, package đã mở cho một module được xem như export cho module đó trong một số kiểm tra quyền truy cập. Vì thế `Module.isExported(pkg, callerModule)` có thể trả `true` khi package được mở bằng `--add-opens`. Nhưng **compile time** vẫn phân biệt rõ `exports` và `opens`: mở package không cho phép source Java import tùy ý các lớp của package đó.

## 3. Bảng so sánh hai launcher options

| Tiêu chí | `--add-exports` | `--add-opens` |
|---|---|---|
| Mục tiêu chính | Mở thêm **public API surface** của một package | Cho phép **deep reflection tại runtime** |
| Với type `public` và thành viên `public` | Có, nếu quyền ngôn ngữ/module phù hợp | Có thể cho phép reflective access tại runtime |
| Với field `private` của lớp ở module khác | Không đủ | Có thể dùng `trySetAccessible`/`setAccessible` để truy cập |
| Có tác dụng khi `javac` biên dịch code import API? | **Có**, qua `javac --add-exports` khi được hỗ trợ | **Không**, không cung cấp quyền import ở compile time |
| Tùy chọn cho `java` launcher? | Có | Có |
| Phạm vi áp dụng | Package của source module tới target module | Package của source module tới target module |
| Dạng cho thư viện chạy trên classpath | `=ALL-UNNAMED` | `=ALL-UNNAMED` |
| Rủi ro | Phụ thuộc vào public API không công bố | Lộ toàn bộ chi tiết không công khai cho target, dễ phá vỡ invariants |
| Hướng thay thế lâu dài | Export đúng API hoặc dùng API công khai khác | `opens ... to ...` có giới hạn, SPI/DTO/accessor, cập nhật framework |

Dạng cú pháp chuẩn:

```text
java --add-exports source.module/package.name=target.module ...
java --add-opens   source.module/package.name=target.module ...
```

Cú pháp `--add-exports=source.module/package.name=target.module` và `--add-opens=source.module/package.name=target.module` cũng được hỗ trợ bởi launcher hiện đại.

## 4. Đọc thông báo lỗi trước khi quyết định flag

Lỗi có thể xuất hiện ở các giai đoạn khác nhau.

| Triệu chứng | Bước thường xảy ra | Chẩn đoán |
|---|---|---|
| Compiler báo package thuộc module X nhưng không được export | `javac` với import/static type reference | Cần một public API được export; `--add-exports` ở compile time có thể hỗ trợ chẩn đoán |
| `IllegalAccessError` với code đã biên dịch | Linkage/truy cập bytecode ở runtime | Public API không được export phù hợp hoặc có khác biệt giữa cấu hình compile và runtime |
| `IllegalAccessException` từ `Constructor.newInstance`/`Method.invoke` | Java reflection thông thường | Member/package không cho phép truy cập theo access rules; kiểm tra exports, type visibility, instance/static |
| `InaccessibleObjectException` từ `setAccessible(true)` | Cố bật deep reflection | Package không mở cho caller module hoặc trường hợp không thể suppress access |
| `trySetAccessible() == false` | Thử bật deep reflection | Yêu cầu mở quyền không được chấp thuận, cần xem `opens` và caller module |
| `NoSuchMethodException`, `NoSuchFieldException` | Tra cứu member | Không phải lỗi module access đơn thuần; kiểm tra tên/signature, overload, kế thừa |
| `ClassNotFoundException` | Tải class | Kiểm tra classpath/module path, class loader và module resolution trước khi thêm flags |
| `InvocationTargetException` với cause là lỗi nghiệp vụ | Method đích đã bắt đầu chạy và ném lỗi | Đọc `getCause()`; không tự suy ra cần `--add-opens` |
| `ExceptionInInitializerError` | Khởi tạo class thất bại | Kiểm tra static initializer; access flag không nhất thiết là nguyên nhân |

`Class.getDeclaredMethod(...)` hoặc `getDeclaredField(...)` có thể tìm metadata của private member mà **không** có nghĩa caller đã được phép invoke/get. Lỗi thường xuất hiện khi thực sự gọi `Method.invoke`, `Field.get` hoặc cố `setAccessible(true)`.

### 4.1. Tránh chọn flag chỉ từ chữ “access”

Lỗi `IllegalAccessException` trong reflection chưa chắc do thiếu `--add-exports`. Ví dụ bạn tìm thấy một `private` member nhưng chưa bật khả năng suppress checks; export package vẫn không cấp phép gọi nó từ module khác. Ngược lại, gọi một `public` method của lớp `public` trong package không export có thể thất bại dù không đụng private data.

Nên xác định member `public` hay non-public, class declaring có `public` không, package ở module nào, module caller là named hay unnamed, và quá trình lỗi xảy ra lúc compile, lookup, access suppression hay invocation.

## 5. Thí nghiệm có hai named modules

Thí nghiệm sau chỉ sử dụng các module do người học tạo. Không sử dụng `jdk.internal.*`, `sun.*` hoặc kỹ thuật sửa field private của JDK. Nhờ vậy, bạn có thể so sánh hai flags mà không phụ thuộc API nội bộ dễ thay đổi.

**Mục tiêu:** module `demo.vault` chứa lớp `public` trong package **không export**; module `demo.client` thực hiện reflection vào constructor công khai, method công khai và một field private.

### 5.1. Cấu trúc thư mục

```text
reflection-access-lab/
  src/
    demo.vault/
      module-info.java
      vault/
        internal/
          SecretBox.java
    demo.client/
      module-info.java
      client/
        Main.java
  out/
```

Tất cả file Java ở đây là nội dung minh họa để người học tạo trong một thư mục lab riêng, không phải các file mà worker cần sinh trong module tài liệu.

### 5.2. Module chứa dữ liệu: `demo.vault`

File `src/demo.vault/module-info.java`:

```java
module demo.vault {
    // Không exports và không opens vault.internal.
}
```

File `src/demo.vault/vault/internal/SecretBox.java`:

```java
package vault.internal;

public class SecretBox {
    private final String secret = "private-token";

    public SecretBox() {}

    public String publicSummary() {
        return "public-summary";
    }

    private String privateSummary() {
        return "secret=" + secret;
    }
}
```

Lớp `SecretBox` và `publicSummary()` đều là `public`, nhưng package `vault.internal` **không được export**. Đó là ranh giới JPMS. Field `secret` và method `privateSummary()` là thành viên không công khai — ranh giới của deep reflection.

### 5.3. Module client: `demo.client`

File `src/demo.client/module-info.java`:

```java
module demo.client {
    requires demo.vault;
}
```

`requires demo.vault` giúp `demo.client` đọc module nguồn và buộc module đó được resolve khi chạy. Nhưng `requires` **không** tự mở package `vault.internal`.

File `src/demo.client/client/Main.java`:

```java
package client;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.InaccessibleObjectException;

public class Main {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("vault.internal.SecretBox");
        Module source = type.getModule();
        Module caller = Main.class.getModule();
        String pkg = type.getPackageName();

        System.out.println("Source module = " + source.getName());
        System.out.println("Caller module = " + caller.getName());
        System.out.println("Exported to caller = " +
                source.isExported(pkg, caller));
        System.out.println("Open to caller = " +
                source.isOpen(pkg, caller));

        Constructor<?> constructor = type.getConstructor();
        Object instance = null;

        try {
            instance = constructor.newInstance();
            System.out.println("Public constructor: SUCCESS");
        } catch (ReflectiveOperationException e) {
            System.out.println("Public constructor: " +
                    e.getClass().getSimpleName());
        }

        if (instance != null) {
            Method publicMethod = type.getMethod("publicSummary");
            System.out.println("Public method: " +
                    publicMethod.invoke(instance));
        }

        Field privateField = type.getDeclaredField("secret");
        boolean deepAccess = privateField.trySetAccessible();
        System.out.println("Private field trySetAccessible = " +
                deepAccess);

        if (deepAccess && instance != null) {
            System.out.println("Private field value = " +
                    privateField.get(instance));
        } else if (!deepAccess) {
            try {
                privateField.setAccessible(true);
            } catch (InaccessibleObjectException e) {
                System.out.println("setAccessible failure = " +
                        e.getClass().getSimpleName());
            }
        }

        Method privateMethod =
                type.getDeclaredMethod("privateSummary");
        boolean privateMethodEnabled =
                privateMethod.trySetAccessible();

        System.out.println("Private method trySetAccessible = " +
                privateMethodEnabled);

        if (privateMethodEnabled && instance != null) {
            System.out.println("Private method result = " +
                    privateMethod.invoke(instance));
        }
    }
}
```

Chương trình **không import** lớp `vault.internal.SecretBox` vào source của client; nó dùng tên class dạng string để kiểm tra quyền runtime. Mục 7 sẽ minh họa trường hợp import trực tiếp tại compile time.

### 5.4. Biên dịch hai module

Từ thư mục `reflection-access-lab`:

```text
javac --module-source-path src -d out -m demo.vault,demo.client
```

Lệnh này không cần `--add-exports`, vì client chỉ dùng `Class.forName` và Reflection API công khai; không có tham chiếu source-level tới `SecretBox`.

### 5.5. Trường hợp A: không có flags

```text
java --module-path out -m demo.client/client.Main
```

Kết quả tiêu biểu:

```text
Source module = demo.vault
Caller module = demo.client
Exported to caller = false
Open to caller = false
Public constructor: IllegalAccessException
Private field trySetAccessible = false
setAccessible failure = InaccessibleObjectException
Private method trySetAccessible = false
```

JVM có thể tải `Class<?>` và lấy `getDeclaredField`, nhưng không cho caller tạo instance bằng constructor công khai trong package không export. Field private cũng không thể bật accessible vì package chưa mở.

### 5.6. Trường hợp B: chỉ `--add-exports`

```text
java --module-path out --add-exports demo.vault/vault.internal=demo.client -m demo.client/client.Main
```

Kết quả tiêu biểu:

```text
Source module = demo.vault
Caller module = demo.client
Exported to caller = true
Open to caller = false
Public constructor: SUCCESS
Public method: public-summary
Private field trySetAccessible = false
setAccessible failure = InaccessibleObjectException
Private method trySetAccessible = false
```

`--add-exports` bổ sung quyền sử dụng `public` API của package, nhưng **không mở private field/method**. Đây là phép thử chứng minh exports và opens khác nhau.

### 5.7. Trường hợp C: chỉ `--add-opens`

```text
java --module-path out --add-opens demo.vault/vault.internal=demo.client -m demo.client/client.Main
```

Kết quả tiêu biểu:

```text
Source module = demo.vault
Caller module = demo.client
Exported to caller = true
Open to caller = true
Public constructor: SUCCESS
Public method: public-summary
Private field trySetAccessible = true
Private field value = private-token
Private method trySetAccessible = true
Private method result = secret=private-token
```

Ở runtime, package mở cho target được xem như export cho target đó; vì vậy `isExported(pkg, caller)` cũng có thể trả `true`. Điểm khác biệt quyết định là `isOpen(pkg, caller)` và `trySetAccessible()`: deep reflection thành công chỉ trong trường hợp package được mở cho module caller.

### 5.8. Ma trận kết quả và kết luận

| Chạy JVM | Public constructor/method | Private field/method qua `trySetAccessible` |
|---|---|---|
| Không flag | Bị từ chối vì package không export | Bị từ chối vì package không open |
| Chỉ `--add-exports` | Được phép | Vẫn bị từ chối |
| Chỉ `--add-opens` | Có thể truy cập tại runtime | Được phép sau khi bật accessible |
| Cả hai | Được phép | Được phép; thường không cần cả hai nếu chỉ dùng reflection runtime |

Các ví dụ trên giả định chương trình chạy đúng hai named modules và không có module directive khác. Java access checks có những điều kiện khác về declaring type, static/instance, subclass, qualified export và context của caller; không dùng bảng này thay cho kiểm chứng đúng mã thực tế.

## 6. `trySetAccessible`, `setAccessible` và `canAccess`

Ba API liên quan nhau nhưng không tương đương:

| API | Trả về/hành vi | Dùng khi nào |
|---|---|---|
| `trySetAccessible()` | `true` nếu bật access thành công, `false` nếu không thể suppress access | Muốn xử lý thiếu quyền có kiểm soát |
| `setAccessible(true)` | Bật access hoặc ném `InaccessibleObjectException` nếu không thể | Khi lỗi phải được báo rõ cho caller |
| `canAccess(receiver)` | Kiểm tra caller hiện có truy cập member được hay không, không thay đổi quyền | Chẩn đoán trước khi thao tác; truyền receiver hợp lệ |

Ví dụ kiểm tra một field instance:

```java
Field field = type.getDeclaredField("secret");

// canAccess(instance) yêu cầu instance đúng kiểu declaring class.
System.out.println("Before = " + field.canAccess(instance));

if (field.trySetAccessible()) {
    System.out.println("After = " + field.canAccess(instance));
    Object value = field.get(instance);
} else {
    System.out.println("Package chưa được mở cho module caller");
}
```

Với `static` member hoặc constructor, tham số của `canAccess` phải là `null`. Với instance field/method, tham số phải là receiver đúng kiểu; gọi `canAccess` với receiver `null` hoặc sai kiểu có thể ném `IllegalArgumentException`. Trong mẫu trên, chỉ dùng `canAccess(instance)` sau khi đã tạo được instance.

**Không dùng** `isAccessible()` để suy luận caller có thể truy cập member hay không: tên API này dễ gây hiểu nhầm, vì nó chỉ phản ánh việc có bật suppress access checks; API đó đã deprecated. Dùng `canAccess` hoặc `trySetAccessible`.

## 7. `--add-exports` ở compile time khác runtime

Thí nghiệm ở mục 5 không import type của package nội bộ. Nếu client muốn dùng class đó trực tiếp từ Java source, compiler cần thấy package được export.

### 7.1. Ví dụ truy cập API công khai theo kiểu tĩnh

Thêm file `src/demo.client/client/DirectClient.java` vào thư mục lab minh họa:

```java
package client;

import vault.internal.SecretBox;

public final class DirectClient {
    public static void main(String[] args) {
        SecretBox box = new SecretBox();
        System.out.println(box.publicSummary());
    }
}
```

Biên dịch lại module mà **không** có flag có thể báo package `vault.internal` thuộc `demo.vault` nhưng chưa được export tới `demo.client`.

Nếu cần kiểm tra khả năng phụ thuộc vào public API chưa export, có thể tạm thêm `--add-exports` cho `javac`:

```text
javac --module-source-path src -d out --add-exports demo.vault/vault.internal=demo.client -m demo.vault,demo.client
```

Và tại runtime:

```text
java --module-path out --add-exports demo.vault/vault.internal=demo.client -m demo.client/client.DirectClient
```

Compiler và runtime có **cấu hình tách biệt**. Một flag chỉ cấp cho `javac` không tự động xuất hiện trong lệnh `java`, image container, IDE run configuration hay service manager.

### 7.2. `--add-opens` không thay compiler export

`--add-opens` là điều khiển runtime. Nó **không** tạo quyền import package của module khác khi biên dịch. Nếu code đã được biên dịch hợp lệ bằng cơ chế khác, package mở có thể cho phép truy cập runtime; nhưng thêm `--add-opens` vào lệnh `javac` không phải cách giải quyết lỗi import của Java source.

Lưu ý thêm: với `javac --release`, việc mở rộng các package được export bởi standard/JDK modules cho một release được chỉ định có giới hạn riêng. Không coi `--add-exports` là cách bỏ qua mọi quy tắc compiler hoặc thay thế dependency chính thức.

### 7.3. Vì sao production không nên dựa vào public package nội bộ

Một package chưa được export có thể bị thay đổi giữa các bản phát hành mà không duy trì contract cho bên ngoài. Dùng `--add-exports` để ép truy cập có thể làm code chạy hôm nay nhưng gãy ở phiên bản tiếp theo. Với package nội bộ của JDK, rủi ro tương thích càng lớn.

Ưu tiên:

1. Tìm API công khai và ổn định tương đương.
2. Cập nhật library/framework để dùng API còn được hỗ trợ.
3. Chỉnh module nguồn để export package API hợp lý nếu bạn quản lý module đó.
4. Chỉ dùng `--add-exports` có mục tiêu hẹp cho chẩn đoán, white-box test hoặc lộ trình chuyển đổi có thời hạn.

## 8. Named modules và `ALL-UNNAMED`

Target module trong flag phải khớp với module chứa code cần truy cập.

### 8.1. Caller là named module

Nếu code reflection nằm trong `demo.client`:

```text
--add-opens demo.vault/vault.internal=demo.client
```

Nếu code dùng public API từ `demo.client`:

```text
--add-exports demo.vault/vault.internal=demo.client
```

Với nhiều named modules cần quyền riêng, giá trị target có thể là danh sách phân tách bằng dấu phẩy:

```text
--add-opens demo.vault/vault.internal=demo.client,demo.tool
```

Hãy cấp quyền cho module thực sự thực hiện reflection. Khi một framework gọi `Field.setAccessible`, module của **framework** có thể là caller được kiểm tra, không phải module chứa `main` của ứng dụng.

### 8.2. Caller ở classpath: unnamed module

Nếu thư viện reflection chạy trên classpath, code thường nằm trong **unnamed module**. Dạng target đặc biệt `ALL-UNNAMED` cho phép tất cả unnamed modules truy cập:

```text
--add-opens demo.vault/vault.internal=ALL-UNNAMED
--add-exports demo.vault/vault.internal=ALL-UNNAMED
```

Không ghi `=ALL-UNNAMED` khi caller là named module, vì quyền đó nhắm tới unnamed modules. Ngược lại, cấp quyền cho một named module cụ thể không tự cấp quyền cho mọi classpath library.

### 8.3. Dùng dấu phẩy giữa nhiều target, không dùng wildcard package

Một flag mở **một package** trong **một source module** tới danh sách target modules. Không dùng cú pháp giả định như `java.base/*` để mở toàn bộ package của module. Khi cần nhiều package, dùng các flag riêng biệt; tốt nhất chỉ mở các package thật sự được yêu cầu bởi chương trình.

## 9. Giải pháp bền vững trong `module-info.java`

Nếu bạn quản lý module nguồn, thay đổi declaration có thể rõ ràng và ổn định hơn flags khởi chạy.

### 9.1. Export API công khai có chủ đích

```java
module demo.vault {
    exports vault.api;
}
```

Code client sử dụng type `public` của `vault.api` bình thường. Không cần deep reflection để đọc private state. Nếu package thực sự chỉ là implementation detail, đừng export nó; hãy xây dựng một façade hoặc SPI công khai phù hợp.

### 9.2. Mở package riêng cho framework cần reflection

```java
module demo.vault {
    exports vault.api;
    opens vault.model to demo.client;
}
```

`opens ... to ...` là **qualified opens**. Nó có ý nghĩa runtime cho reflection nhưng không cung cấp compile-time access như `exports`. Với DI, ORM hoặc serializer, target nên là tên module thực sự chứa code reflection của framework, không phải tên package và không nhất thiết là module ứng dụng.

### 9.3. `open module` là phạm vi rất rộng

```java
open module demo.vault {
    exports vault.api;
}
```

`open module` mở mọi package của module cho reflection ở runtime. Đây là một quyết định thiết kế lớn, không nên dùng chỉ để vượt qua một lỗi của một private field. Thông thường, qualified `opens` có phạm vi nhỏ hơn và dễ kiểm toán hơn.

### 9.4. Không mở package nếu không cần

Trước khi sửa `module-info.java` hoặc thêm flag:

- Có thể dùng constructor/factory public hợp lệ không?
- Framework có hỗ trợ Java records, property accessor hoặc binding qua method công khai không?
- Có API/SPI chính thức thay thế truy cập private field không?
- Có thể nâng cấp dependency đang cần reflection sâu không?
- Có thể chuyển dữ liệu qua DTO/immutable value object thay vì reflection vào implementation class không?

Một bản sửa kiến trúc loại bỏ nhu cầu deep reflection thường bền vững hơn việc mở quyền trong mọi môi trường.

## 10. Kết nối với `MethodHandles.privateLookupIn`

Trên JDK hiện đại, một số framework sử dụng `MethodHandles.Lookup` và `MethodHandles.privateLookupIn(...)` thay vì chỉ gọi `Field.setAccessible(true)`.

`privateLookupIn` có hợp đồng kiểm soát quyền riêng: muốn có private lookup vào class ở module khác, package của class đó phải được **opened** phù hợp cho module của caller (cùng với các điều kiện khác của `Lookup` và readability). Chỉ dùng `--add-exports` không đủ để tự động mở private lookup.

Ví dụ có thể thấy:

```java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup lookup = MethodHandles.privateLookupIn(
        secretClass, MethodHandles.lookup());
```

Nếu access thất bại, có thể nhận `IllegalAccessException` theo hợp đồng `MethodHandles` thay vì `InaccessibleObjectException` của `setAccessible(true)`. Vì thế, hãy đọc đúng **API nào gây lỗi**; không đồng nhất mọi “lỗi reflection” thành cùng exception class.

Đừng dùng `MethodHandles` để cố bypass module boundary. API này cũng thực thi quyền theo lookup context và module openness.

## 11. Chẩn đoán quyền truy cập bằng dữ liệu runtime

Một utility chẩn đoán có thể ghi module nguồn, module caller và trạng thái export/open thay vì đoán từ stack trace.

```java
import java.lang.reflect.Field;

public final class AccessDiagnostics {
    public static void printFor(Class<?> targetClass) {
        Module source = targetClass.getModule();
        Module caller = AccessDiagnostics.class.getModule();
        String packageName = targetClass.getPackageName();

        System.out.println("source module: " + source.getName());
        System.out.println("caller module: " + caller.getName());
        System.out.println("package: " + packageName);
        System.out.println("exported to caller: " +
                source.isExported(packageName, caller));
        System.out.println("open to caller: " +
                source.isOpen(packageName, caller));

        for (Field field : targetClass.getDeclaredFields()) {
            System.out.println("field=" + field.getName()
                    + ", type=" + field.getType().getTypeName());
        }
    }
}
```

Không dùng output `Module.isExported` và `isOpen` làm bằng chứng rằng có thể đọc được mọi field: điều kiện visibility của declaring class/member, caller identity và việc có bật suppress access vẫn quan trọng.

Khi `AccessDiagnostics` nằm trong module khác với caller thực sự, phép kiểm tra sẽ phản ánh **module của utility**, không nhất thiết module của framework đang thực hiện reflection. Trong chẩn đoán nâng cao, hãy gọi kiểm tra từ chính module chứa reflection code hoặc chuyển module caller thực tế vào utility.

### 11.1. Ghi nhận đầy đủ môi trường

Một bản ghi lỗi truy cập hữu ích nên có:

```text
timestamp:
java.vendor:
java.runtime.version:
java.home:
source_module:
source_package:
caller_module:
target_member:
target_modifier:
operation: lookup / invoke / get / setAccessible / privateLookupIn
exported_to_caller:
open_to_caller:
effective_jvm_flags:
exception_type:
cause:
```

Không log giá trị field private, mật khẩu, token hoặc dữ liệu nhạy cảm chỉ để chẩn đoán JPMS. Khi cần dùng flag tạm thời, ghi rõ ai chấp thuận, package nào được mở, target module nào nhận quyền và khi nào cần loại bỏ flag.

## 12. Các nhầm lẫn cần tránh

| Nhầm lẫn | Điều chỉnh đúng |
|---|---|
| “Class là public nên module nào cũng gọi được” | Còn phải xét package có được export/open phù hợp không |
| “`requires` là đủ để truy cập mọi package của module khác” | `requires` là readability, không thay `exports`/`opens` |
| “`--add-exports` cho phép đọc private field” | Export chủ yếu cấp quyền public API; deep reflection cần mở package |
| “`--add-opens` làm private thành public” | Chỉ cho phép suppress access check khi reflection API thực hiện yêu cầu |
| “Thêm `--add-opens` vào `javac` để sửa lỗi import” | `opens` không cấp compile-time public access |
| “`Class.forName` thành công thì `newInstance` sẽ thành công” | Load metadata không đồng nghĩa có quyền invoke |
| “`getDeclaredField` thành công thì `Field.get` chắc chắn thành công” | Access check còn diễn ra khi đọc hoặc bật accessible |
| “`ALL-UNNAMED` có nghĩa tất cả named modules” | Nó chỉ nhắm unnamed modules trên classpath |
| “Mọi `IllegalAccessException` đều cần `--add-opens`” | Cần phân biệt public access, private member, module/package và API gây lỗi |
| “`trySetAccessible() == false` là lỗi không thể xử lý” | Có thể chuyển sang public accessor/SPI hoặc cấu hình mở đúng package |
| “Mở toàn bộ `java.base` sẽ an toàn cho production” | Mở quá rộng làm suy yếu encapsulation và tăng rủi ro bảo trì |

### 12.1. Không dựa vào cờ legacy

Trên các JDK hiện đại, không dựa vào `--illegal-access=permit`, `warn` hoặc `debug` để mở lại hàng loạt package nội bộ như một số hướng dẫn từ thời chuyển tiếp JDK 9–16. Tùy chọn đó đã trở nên lỗi thời từ JDK 17; khi cần chẩn đoán, dùng đúng hướng dẫn `--add-exports`/`--add-opens` có phạm vi hẹp hoặc sửa nguồn.

Đối với API nội bộ của JDK, ưu tiên cập nhật framework và thay bằng public API. Ngay cả khi `--add-exports` tạm cho phép truy cập một package nội bộ, nó không biến package đó thành API được cam kết ổn định.

## 13. Quy trình lựa chọn `--add-exports` hay `--add-opens`

Khi nhận stack trace ở production hoặc CI:

1. **Xác định giai đoạn:** lỗi xảy ra khi `javac`, class loading, linking, `Method.invoke`, `Field.get`, `setAccessible` hay `privateLookupIn`?
2. **Xác định member:** type và member là `public` hay private/package-private/protected? Package thuộc module nào?
3. **Xác định caller:** module thực hiện access là named hay unnamed? Framework hay app thực sự gọi reflection?
4. **Kiểm tra module:** đọc `module-info.java`, `requires`, `exports`, `opens`; dùng `Module.isExported`/`isOpen` tại runtime khi cần.
5. **Chọn phương án nhỏ nhất:** với public API, xem `exports`; với deep reflection, xem `opens`. Không mở package nếu sửa code/API được.
6. **Chỉ dùng flag tạm thời khi cần:** `--add-exports` ở `javac`/`java` phù hợp nhu cầu; `--add-opens` ở runtime cho reflective access; target module phải đúng.
7. **Thử lại trong môi trường chính xác:** IDE, Gradle/Maven launcher, test runner, service manager và container có thể khác nhau về module path và JVM args.
8. **Đánh giá an toàn:** hạn chế package và module đích; xác định rủi ro khi lộ private internals.
9. **Loại bỏ workaround:** cập nhật module descriptor/framework hoặc public API để hạn chế phụ thuộc vào flags không cần thiết.

## 14. Bài tập tự kiểm tra

1. `requires demo.vault` có tự cho phép truy cập `vault.internal.SecretBox` không? Vì sao?
2. Khi gọi public constructor trong package chưa export, vì sao `Class.forName` có thể thành công nhưng `Constructor.newInstance` thất bại?
3. Nếu `--add-exports` giúp gọi public method nhưng `privateField.trySetAccessible()` vẫn trả `false`, thiếu quyền gì?
4. `--add-opens` có cho phép source Java import trực tiếp class thuộc package chưa export tại compile time không?
5. Vì sao `Module.isExported(pkg, target)` có thể trả `true` khi package được mở tại runtime?
6. `trySetAccessible` khác `setAccessible(true)` như thế nào khi không thể mở quyền?
7. Với classpath library, khi nào dùng `ALL-UNNAMED` và khi nào không nên dùng?
8. Vì sao `InaccessibleObjectException` và `IllegalAccessException` cần được chẩn đoán tại đúng thao tác gây lỗi?
9. Khi framework dùng `MethodHandles.privateLookupIn`, chỉ thêm `--add-exports` có đủ không?
10. Nếu bạn quản lý module nguồn, giải pháp nào nên ưu tiên thay vì thêm flags cho mọi môi trường?
11. Vì sao `--illegal-access` trong hướng dẫn từ các JDK cũ không còn là lựa chọn thích hợp?
12. Cần ghi những dữ liệu nào để tái lập lỗi quyền reflection mà không làm lộ giá trị private field?

**Tiêu chí hoàn thành:** Bạn có thể nhìn lỗi truy cập để xác định đang thiếu export hay open, phân biệt tác dụng compile time với runtime, áp dụng đúng target module trong launcher và chuyển sang thiết kế module có quyền tối thiểu khi có thể.

## 15. Tài liệu chuẩn

- [JLS, Chương 7 — Packages and Modules, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html): ngữ nghĩa `exports`, `opens` và `open module` ở compile time/runtime.
- [AccessibleObject — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `setAccessible`, `trySetAccessible`, `canAccess` và điều kiện module openness.
- [Module — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html): `isExported`, `isOpen` và cách diễn giải opened package tại runtime.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): tham số launcher `--add-exports` và `--add-opens`.
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `--add-exports` ở compile time và hạn chế khi dùng `--release`.
- [Migrating from JDK 8 to Later JDK Releases — Java SE 26](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): strong encapsulation và cách dùng hai flags khi chuyển đổi.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): chính sách encapsulation JDK internals, tránh workaround từ `--illegal-access`.
- [MethodHandles — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): quyền cho `privateLookupIn` theo module boundary.

