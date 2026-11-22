# Khả năng truy cập tài nguyên thuộc module đích (JPMS và nest trong Java 15+)

## Mục tiêu

Trong một ứng dụng Java dùng **Java Platform Module System (JPMS)**, nhìn thấy lớp công khai thuộc một module khác **không có nghĩa** bạn cũng đọc được mọi tệp cấu hình, template hay tài nguyên nằm trong module đó. Quyền truy cập **class/member**, quan hệ **nestmate** và quyền tìm **resource** là những cơ chế liên quan nhưng không đồng nhất.

Bài này giúp bạn:

1. Phân biệt module *gọi* (caller) với **module đích** (target) và hiểu cách Java xác định quyền đọc tài nguyên.
2. Sử dụng đúng `Module.getResourceAsStream`, `Class.getResourceAsStream` và `ClassLoader.getResourceAsStream` trong ứng dụng modular.
3. Phân biệt `requires`, `exports`, `opens ... to ...` và `opens` không giới hạn; biết vì sao `exports` **không đủ** để truy cập resource đã được đóng gói.
4. Hiểu mối quan hệ với **nestmate** và `MethodHandles.Lookup`: quyền đọc private member không phải giấy phép truy cập mọi tài nguyên của module khác.
5. Thực hành một dự án có hai **named module** chạy được với **JDK 17+**, có các ví dụ tài nguyên được mở, không được mở và được đọc từ bên trong chính module đích.

**Phạm vi hiện hành:** JPMS được đưa vào Java 9, nest-based access control có từ Java 11, và các API hidden class liên quan đến `Lookup` có từ Java 15. Những cơ chế và API công khai dùng trong bài vẫn áp dụng trên các JDK hiện đại; không dùng Security Manager hoặc kỹ thuật legacy làm giải pháp.

## 1. “Tài nguyên thuộc module đích” là gì?

Tài nguyên (*resource*) thường là một tệp dữ liệu được đóng gói cùng một module, ví dụ:

```text
m.target
├── module-info.java
└── p
    ├── target
    │   ├── Target.java
    │   └── message.txt
    └── secret
        ├── Marker.java
        └── private.txt
```

Trong hình trên:

- `p.target.Target` là một **class**; nó có thể được xuất (*export*) để module khác tham chiếu trong Java code.
- `p/target/message.txt` là **resource** nằm trong package `p.target`.
- `p/secret/private.txt` là resource ở package `p.secret`, có thể được giữ kín với module bên ngoài.
- `module-info.java` khai báo quan hệ module và quyền truy cập ở cấp package.

**Bài học quan trọng:** việc code ở module `m.client` biên dịch được câu lệnh `import p.target.Target;` không tự chứng minh `m.client` được đọc `p/target/message.txt` hay `p/secret/private.txt`.

Trong JPMS, trước hết phải phân biệt:

- **Module readability:** `requires m.target;` trong `m.client` cho phép module đọc dependency cần thiết.
- **Package export:** `exports p.target;` cho phép các kiểu public trong package đó được module khác truy cập theo quy tắc Java.
- **Package open:** `opens p.target to m.client;` mở package cho module cụ thể, được dùng cho deep reflection và **kiểm tra quyền truy cập resource không phải `.class`**.
- **Nestmate:** quan hệ giữa các class cùng nest, phục vụ quyền truy cập private member. Nó không mở mọi package hay resource của module cho code gọi từ module khác.

## 2. Quy tắc đóng gói tài nguyên ở named module

Theo hợp đồng `Module.getResourceAsStream(String name)`, resource trong một **named module** có thể bị JPMS đóng gói (*encapsulated*). Với đường dẫn chuẩn cách bằng dấu `/`:

1. Nếu tên resource **kết thúc bằng `.class`**, trường hợp đặc biệt đó **không bị đóng gói theo quy tắc resource này**.
2. Nếu resource thuộc **một package thực sự có trong module**, đối với tài nguyên thông thường như `.txt`, `.json` hay `.properties`, module gọi phải được module đích **mở package đó** (có thể mở có điều kiện tới module gọi).
3. Nếu resource **không nằm trong một package có trong module**, quy tắc đóng gói package này không ngăn việc tìm resource. Dĩ nhiên resource vẫn phải thật sự tồn tại và được module loader tìm thấy.

Vì thế `Module.getResourceAsStream("p/target/message.txt")` có thể trả một `InputStream` cho module `m.client` khi `m.target` khai báo:

```java
opens p.target to m.client;
```

Nếu chỉ có:

```java
exports p.target;
```

thì module client đọc được **public class** nhưng chưa chắc đọc được **resource** nằm trong package đó.

Lưu ý: việc `getResourceAsStream` trả `null` **không chỉ có một nguyên nhân**. Nó có thể là file không được đóng gói, sai đường dẫn, module không được resolve, package chưa mở đúng phía hoặc class loader không tìm được resource. Phải xác định nguyên nhân qua cấu trúc build và các quyền module, không suy luận chỉ từ `null`.

### Bảng quyền truy cập thông dụng

| Khai báo trong `m.target/module-info.java` | Code `m.client` dùng public class `p.target`? | `m.client` tìm tài nguyên `p/target/message.txt` bằng `Module.getResourceAsStream`? |
| --- | --- | --- |
| `exports p.target;` | Có, nếu module client đọc `m.target` | **Không chỉ nhờ exports** |
| `exports p.target; opens p.target to m.client;` | Có | Có thể, nếu resource tồn tại |
| `exports p.target; opens p.target;` | Có | Có thể, package được mở không giới hạn |
| `opens p.target to m.client;` nhưng không `exports` | Không bảo đảm import public class từ module khác | Resource có thể truy cập qua `Module` nếu đã có cách hợp lệ lấy đối tượng Module |
| `open module m.target { ... }` | Phụ thuộc `exports` cho compile-time access | Các package của module được mở không giới hạn; **quyền mở quá rộng** nếu chỉ cần một file |

Không nên mở toàn bộ module chỉ để giải quyết một resource cụ thể. Nếu muốn cung cấp vài dữ liệu có kiểm soát, thường tốt hơn là thiết kế **API public ở module đích** trả về chính dữ liệu được phép dùng.

## 3. Ba API dễ nhầm: Module, Class và ClassLoader

### 3.1. `Module.getResourceAsStream`: biết rõ module đích

```java
Module target = Target.class.getModule();

try (InputStream in =
        target.getResourceAsStream("p/target/message.txt")) {
    if (in == null) {
        throw new IllegalStateException("Resource not visible");
    }
    // Xử lý nội dung, ví dụ: in.readAllBytes()
}
```

Tên đường dẫn dùng `/` phân cách từ gốc module. Dấu `/` đầu tên được `Module.getResourceAsStream` bỏ trước khi tìm. API này xem xét **module của code gọi phương thức**, không phải cứ cầm đối tượng `Module` là bỏ qua mọi quy tắc đóng gói. Nó khai báo `throws IOException`; cần quản lý stream bằng *try-with-resources*.

Ưu điểm: nêu rõ module đích, tránh đoán class loader nào chịu trách nhiệm cho resource. Hạn chế: không thể vượt quyền mở package nếu caller là module khác.

### 3.2. `Class.getResourceAsStream`: đường dẫn tương đối hoặc tuyệt đối

```java
InputStream a = Target.class.getResourceAsStream("message.txt");
InputStream b = Target.class.getResourceAsStream("/p/target/message.txt");
```

Với `Target` nằm trong package `p.target`:

- `"message.txt"` được diễn giải tương đối thành `p/target/message.txt`.
- `"/p/target/message.txt"` bắt đầu từ gốc module hoặc classpath.

Nếu `Target.class` thuộc named module, `Class.getResourceAsStream` vẫn tuân thủ **quy tắc encapsulation của tài nguyên**. Không thể dùng dấu `/` hoặc đổi cách viết đường dẫn để vượt qua `opens`.

Ở cả hai lệnh trên, phải đóng `InputStream` sau khi dùng. Đoạn minh họa có biến `Target` và `InputStream` đã import, không phải chương trình độc lập.

### 3.3. `ClassLoader.getResourceAsStream`: điều kiện còn chặt hơn

```java
InputStream in = Target.class.getClassLoader()
        .getResourceAsStream("p/target/message.txt");
```

Đối với một resource **không phải `.class` nằm trong package của named module**, lookup kiểu `ClassLoader.getResourceAsStream` chỉ tìm thấy khi package được **mở vô điều kiện** (*opened unconditionally*).

Ví dụ, khai báo:

```java
opens p.target to m.client;
```

là **qualified opens**. Nó có thể cho phép `m.client` đọc bằng `Module.getResourceAsStream` và `Class.getResourceAsStream`, **nhưng chưa đủ để ClassLoader trả resource đó**.

Đây là khác biệt dễ gây lỗi khi di chuyển một ứng dụng từ classpath sang module path. Kết quả của cách lookup theo `ClassLoader` còn có thể phụ thuộc cách class loader được triển khai, sự tồn tại của resource, và nhiều module dùng chung class loader. Vì vậy khi đã biết module đích, hãy ưu tiên API module-aware hoặc một API công khai do module đích cung cấp.

## 4. Ví dụ hoàn chỉnh: m.target và m.client

Dự án sau minh họa cùng lúc:

- `m.client` đọc được public class `Target` nhờ `exports` và `requires`.
- `m.client` đọc được `message.txt` qua `Module` và `Class` vì package `p.target` được **mở có điều kiện** tới `m.client`.
- `m.client` **không** đọc được `private.txt` trong package `p.secret` vì package không mở tới client.
- Code chạy **bên trong `m.target`** vẫn đọc được resource của chính module đó.
- `ClassLoader.getResourceAsStream` không tìm được `message.txt` khi package chỉ được mở có điều kiện.
- Tệp `Marker.class` là ngoại lệ `.class` của quy tắc resource encapsulation.
- Một class lồng bên trong `Target` truy cập private field như nestmate, nhưng điều đó **không mở `p.secret` cho m.client**.
- `privateLookupIn` từ module client có thể lấy private access do package được mở, nhưng lookup trả về **không giữ quyền MODULE** khi chuyển qua biên module.

### 4.1. Cấu trúc thư mục

Tạo các tệp theo cấu trúc sau:

```text
src/
├── m.target/
│   ├── module-info.java
│   └── p/
│       ├── target/
│       │   ├── Target.java
│       │   └── message.txt
│       └── secret/
│           ├── Marker.java
│           └── private.txt
└── m.client/
    ├── module-info.java
    └── q/
        └── client/
            └── Client.java
```

**File 1 — `src/m.target/module-info.java`:**

```java
// File: src/m.target/module-info.java
module m.target {
    exports p.target;
    opens p.target to m.client;
}
```

**File 2 — `src/m.target/p/target/Target.java`:**

```java
// File: src/m.target/p/target/Target.java
package p.target;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Target {
    private static final String SECRET = "NEST_OK";

    private static final class NestMember {
        private static String readSecret() {
            return SECRET;
        }
    }

    public static boolean nestAccess() {
        return Target.class.isNestmateOf(NestMember.class)
                && NestMember.readSecret().equals(SECRET);
    }

    public static String readClosedResource() throws IOException {
        try (InputStream in = Target.class.getModule()
                .getResourceAsStream("p/secret/private.txt")) {
            return in == null ? "<missing>"
                    : new String(in.readAllBytes(), StandardCharsets.UTF_8)
                            .strip();
        }
    }
}
```

**File 3 — `src/m.target/p/secret/Marker.java`:**

```java
// File: src/m.target/p/secret/Marker.java
package p.secret;

public final class Marker { }
```

`Marker` dùng để bảo đảm `p.secret` thật sự là một **package của module đích**. Nếu resource nằm ở đường dẫn không thuộc package nào của module, quy tắc encapsulation có thể khác và ví dụ về resource đóng kín sẽ không còn đúng.

**File 4 — `src/m.client/module-info.java`:**

```java
// File: src/m.client/module-info.java
module m.client {
    requires m.target;
}
```

**File 5 — `src/m.client/q/client/Client.java`:**

```java
// File: src/m.client/q/client/Client.java
package q.client;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.nio.charset.StandardCharsets;
import p.target.Target;

public final class Client {
    private static String read(InputStream in) throws IOException {
        if (in == null) {
            return "<missing>";
        }
        try (in) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8)
                    .strip();
        }
    }

    public static void main(String[] args) throws Exception {
        Module target = Target.class.getModule();
        Module client = Client.class.getModule();

        System.out.println("canRead=" + client.canRead(target));
        System.out.println("exported=" + target.isExported("p.target", client));
        System.out.println("qualifiedOpen=" + target.isOpen("p.target", client));
        System.out.println("unconditionalOpen=" + target.isOpen("p.target"));
        System.out.println("secretOpen=" + target.isOpen("p.secret", client));

        System.out.println("moduleOpenResource="
                + read(target.getResourceAsStream("p/target/message.txt"))
                        .equals("SHARED"));
        System.out.println("classRelative="
                + read(Target.class.getResourceAsStream("message.txt"))
                        .equals("SHARED"));
        System.out.println("classAbsolute="
                + read(Target.class.getResourceAsStream("/p/target/message.txt"))
                        .equals("SHARED"));
        System.out.println("clientClosedResource="
                + (target.getResourceAsStream("p/secret/private.txt") == null));
        System.out.println("targetOwnResource="
                + Target.readClosedResource().equals("PRIVATE"));

        System.out.println("loaderQualifiedUnavailable="
                + (Target.class.getClassLoader()
                        .getResourceAsStream("p/target/message.txt") == null));

        try (InputStream classFile =
                target.getResourceAsStream("p/secret/Marker.class")) {
            System.out.println("classNotEncapsulated=" + (classFile != null));
        }

        System.out.println("nestPrivateAccess=" + Target.nestAccess());
        MethodHandles.Lookup borrowed = MethodHandles.privateLookupIn(
                Target.class, MethodHandles.lookup());
        System.out.println("borrowedModuleMode="
                + ((borrowed.lookupModes() & MethodHandles.Lookup.MODULE) != 0));
    }
}
```

**File 6 — `src/m.target/p/target/message.txt`:** nội dung văn bản:

```text
SHARED
```

**File 7 — `src/m.target/p/secret/private.txt`:** nội dung:

```text
PRIVATE
```

Code dùng `String.strip()` khi đọc tài nguyên để cả tệp có/không có newline cuối vẫn cho cùng kết quả kiểm thử. Trong hệ thống thực tế cần giữ chính xác khoảng trắng của resource, **đừng strip vô điều kiện**; dùng `readAllBytes()` hoặc giải mã và giữ nguyên dữ liệu theo hợp đồng.

### 4.2. Biên dịch và chạy trên Linux/macOS (Bash)

Từ thư mục chứa `src`, dùng **JDK 17+**:

```bash
javac --release 17 -encoding UTF-8 --module-source-path src \
  -d out --module m.target,m.client

mkdir -p out/m.target/p/target out/m.target/p/secret
cp src/m.target/p/target/message.txt out/m.target/p/target/message.txt
cp src/m.target/p/secret/private.txt out/m.target/p/secret/private.txt

java --module-path out --module m.client/q.client.Client
```

### 4.3. Biên dịch và chạy trên Windows PowerShell

```powershell
javac --release 17 -encoding UTF-8 --module-source-path src -d out --module m.target,m.client

New-Item -ItemType Directory -Force -Path out/m.target/p/target, out/m.target/p/secret | Out-Null
Copy-Item src/m.target/p/target/message.txt out/m.target/p/target/message.txt
Copy-Item src/m.target/p/secret/private.txt out/m.target/p/secret/private.txt

java --module-path out --module m.client/q.client.Client
```

**Quan trọng:** `javac` biên dịch tệp `.java`, **không tự copy** resource `.txt` vào `out`. Hai lệnh `cp`/`Copy-Item` rất quan trọng. Trong Maven/Gradle, hãy cấu hình build để đóng gói resource vào **đúng vị trí tương ứng** trong modular JAR/output.

### 4.4. Stdout mong đợi (xác minh bằng JDK 17-compatible code)

```text
canRead=true
exported=true
qualifiedOpen=true
unconditionalOpen=false
secretOpen=false
moduleOpenResource=true
classRelative=true
classAbsolute=true
clientClosedResource=true
targetOwnResource=true
loaderQualifiedUnavailable=true
classNotEncapsulated=true
nestPrivateAccess=true
borrowedModuleMode=false
```

**Giải thích những dòng quan trọng:**

- `canRead=true` và `exported=true` xác nhận client có module dependency và quyền tham chiếu public API.
- `qualifiedOpen=true` đi cùng `unconditionalOpen=false` cho thấy package được mở **chỉ cho m.client**, không mở rộng cho mọi module.
- `moduleOpenResource=true`, `classRelative=true`, `classAbsolute=true` là ba cách truy cập thành công từ client tới file `message.txt`.
- `clientClosedResource=true` nghĩa là lời gọi từ client tới resource `p.secret` trả về `null`, **không phải** đọc được private file.
- `targetOwnResource=true` chứng minh code đang chạy trong chính `m.target` có thể đọc resource thuộc package đóng của module mình. Đây không phải là cơ chế client vượt quyền: client chỉ gọi **phương thức public** mà target chủ động cung cấp.
- `loaderQualifiedUnavailable=true` xác nhận qualified opens chưa đủ để `ClassLoader.getResourceAsStream` thấy resource thường.
- `classNotEncapsulated=true` minh họa ngoại lệ `.class` trong quy tắc tìm resource. Không hiểu điều này là được phép bỏ qua mọi quy tắc bảo mật hay reflection.
- `nestPrivateAccess=true` là quyền truy cập private field giữa các nestmate **trong m.target**; không tạo thêm quyền cho client.
- `borrowedModuleMode=false` cho thấy `Lookup` lấy qua `privateLookupIn` từ module khác không giữ cờ `MODULE`, dù điều kiện `opens` cho phép lấy private lookup.

## 5. Vì sao nestmate không tự mở tài nguyên của module đích?

Quan hệ **nest** do JVM dùng để kiểm tra quyền truy cập private member giữa các class cùng nest host. Nó không phải danh sách module được phép đọc resource.

Trong ví dụ, `Target.NestMember` truy cập private field `SECRET` của `Target` được, nhưng điều đó không làm `p.secret` mở cho `m.client`. Muốn module khác đọc một resource bị đóng gói, bạn vẫn phải thiết kế một trong các cơ chế rõ ràng sau:

1. Khai báo `opens p.secret to m.client;` nếu thực sự muốn module client trực tiếp truy cập resource trong package đó và chấp nhận hệ quả mở package cho deep reflection.
2. Cung cấp **public API có kiểm soát** bên trong module đích, ví dụ `Target.readClosedResource()`, chỉ trả dữ liệu mà ứng dụng chủ động cho phép.
3. Đưa resource cần chia sẻ tới một thiết kế đóng gói phù hợp với chính sách API thay vì mở cả package kín chỉ để đọc một file.

Hệ thống có thể có hidden class từ `MethodHandles.Lookup.defineHiddenClass(..., NESTMATE)` trong Java 15+. Hidden class này có quan hệ nestmate thích hợp và thuộc runtime package/module của lookup class. Điều đó **không cho phép một Lookup tùy ý của m.client tự trở thành thành viên module m.target**. Việc định nghĩa hidden class đòi hỏi quyền lookup phù hợp; `NESTMATE` điều khiển quan hệ nest, không xóa kiểm tra quyền module hay resource.

### 5.1. `privateLookupIn` và giới hạn khi đi qua module

`MethodHandles.privateLookupIn(Target.class, MethodHandles.lookup())` cần module client đọc module target **và** package target mở cho client, ngoài các điều kiện lookup access. Với `opens p.target to m.client;`, mã kiểm thử phía trên lấy được private lookup.

Tuy nhiên, khi caller/target thuộc **hai module khác nhau**, lookup trả về **không có `MODULE` mode**. Vì vậy không thể suy ra từ đó rằng nó là *full-privilege lookup* đủ cho `defineHiddenClass` bên trong module đích. Cũng đừng dùng quyền `privateLookupIn` để kết luận resource của mọi package ở module đích đã được mở.

Quyền truy cập private member, khả năng định nghĩa class runtime và khả năng đọc tệp resource là các hợp đồng API khác nhau. Cần kiểm tra **đúng phương thức được gọi và module của code đang gọi**.

## 6. Hướng thiết kế an toàn cho ứng dụng thực tế

### 6.1. Ưu tiên API do module đích cung cấp khi không muốn mở package

Nếu module đích cần cho client đọc một template cụ thể nhưng không muốn mở package, có thể chủ động cung cấp phương thức public:

```java
// Mã minh họa bên trong một class public thuộc module đích:
public static String readTemplate() throws java.io.IOException {
    try (var in = Target.class.getResourceAsStream("message.txt")) {
        if (in == null) {
            throw new java.io.FileNotFoundException("message.txt");
        }
        return new String(in.readAllBytes(),
                java.nio.charset.StandardCharsets.UTF_8);
    }
}
```

Phương thức nằm trong **module đích** nên có thể tìm resource của chính nó theo quy tắc module. Client chỉ gọi API đã export. Bạn có thể chủ động kiểm soát loại dữ liệu xuất, caching, xử lý lỗi, phân quyền ứng dụng và không vô tình mở package cho deep reflection. Đây là định hướng phù hợp khi package chứa thêm các cấu hình không nên tiết lộ.

### 6.2. Dữ liệu mật không nên được bảo vệ chỉ bằng resource encapsulation

JPMS là cơ chế module encapsulation và kiểm soát truy cập ở mức API/runtime; nó **không phải kho giữ bí mật**. Tệp được đóng gói trong JAR có thể bị đọc bằng công cụ quản lý tệp hoặc giải nén nếu người dùng có file. Không đóng gói mật khẩu, khóa riêng hay thông tin bí mật trong resource với kỳ vọng `opens` sẽ bảo vệ chúng tuyệt đối.

### 6.3. Không dùng `--add-opens` như thiết kế mặc định

Khi debugging hoặc tích hợp thư viện đặc biệt, Java có thể được chạy với tùy chọn kiểu:

```bash
java --add-opens m.target/p.target=m.client \
  --module-path out --module m.client/q.client.Client
```

Đây là cách điều chỉnh quyền mở package cho tiến trình đang chạy, **không phải thay thế tốt cho hợp đồng module rõ ràng**. Với resource thông thường, việc mở có điều kiện cho `m.client` cũng không có nghĩa `ClassLoader.getResourceAsStream` sẽ tìm thấy file khi package không được mở **vô điều kiện**.

Với ứng dụng production, ưu tiên module descriptor, API rõ ràng và bài kiểm thử phù hợp. Tránh mở package quá rộng chỉ để “làm cho resource được tìm thấy”.

## 7. Cách chẩn đoán khi getResourceAsStream trả null

Đừng coi `null` là lỗi quyền truy cập duy nhất. Hãy kiểm tra theo thứ tự:

1. **Tên resource:** `Module.getResourceAsStream` dùng đường dẫn tương đối từ gốc module, phân cách bằng `/`. `Class.getResourceAsStream` thêm package nếu không có `/` ở đầu.
2. **Tài nguyên có nằm trong output không?** Kiểm tra quá trình copy resource từ `src` vào `out/m.target/...` hoặc đóng gói vào JAR.
3. **Đang đọc từ đúng module đích không?** Với code modular, `Target.class.getModule()` đáng tin hơn việc đoán module qua class loader hay tên file.
4. **Resource nằm trong package thật sự của module không?** Một đường dẫn trông giống tên package nhưng package không tồn tại có thể có quy tắc encapsulation khác.
5. **Package có mở cho module gọi không?** Kiểm tra `target.isOpen("p.target", client)`; `isExported` không thay được `isOpen`.
6. **Đang dùng API nào?** Với `ClassLoader.getResourceAsStream`, qualified opens vẫn không đủ cho resource thường trong package named module.
7. **Dữ liệu dạng `.class` hay resource thông thường?** Có ngoại lệ `.class` ở lớp tìm resource nhưng không nên suy rộng thành quyền phản chiếu.
8. **Có thêm lỗi đọc I/O không?** Nếu stream đã được mở, hãy dùng `try-with-resources` và xử lý `IOException`; đừng nuốt lỗi rồi báo sai rằng resource không tồn tại.

### Bảng lỗi phổ biến

| Lỗi | Lý do | Cách sửa |
| --- | --- | --- |
| `import Target` chạy được, nhưng `message.txt` không thấy | `exports` không tự mở package cho resource | Cân nhắc `opens ... to ...` hoặc API đọc resource từ trong target |
| `target.isExported(...) == true` nhưng stream vẫn null | Hai loại quyền khác nhau | Kiểm tra `isOpen(package, callerModule)` |
| `Module.getResourceAsStream` đọc được nhưng `ClassLoader.getResourceAsStream` không | Package chỉ mở có điều kiện | Dùng API module-aware, không ép mở vô điều kiện khi không cần |
| Resource nằm trong `src` nhưng không có khi chạy | Trình biên dịch không copy `.txt` | Cấu hình copy resource vào build output/JAR |
| `Target.class.getResourceAsStream("p/target/message.txt")` trả null | Class API diễn giải đây là đường dẫn tương đối, thêm package lần nữa | Dùng `"message.txt"` hoặc `"/p/target/message.txt"` |
| Tưởng thành viên cùng nest đồng nghĩa có quyền đọc mọi resource | Nest chỉ điều khiển private member access | Dùng đúng kiểm tra opens/API của module |
| Dùng `privateLookupIn` để tự định nghĩa hidden class ở module khác | Lookup liên module mất `MODULE` mode | Định nghĩa class trong ngữ cảnh lookup có đủ quyền |
| Mở cả module chỉ để đọc một file | Quyền mở rộng hơn mức cần thiết | Đề xuất public resource API hoặc mở package có điều kiện |
| Di chuyển sang module path thì resource lookup đổi hành vi | Named module áp dụng encapsulation khác classpath | Kiểm thử trong cấu hình module path thật |

## 8. Bài tập tự kiểm tra

**Bài 1.** Module `m.target` khai báo `exports p.target;`; module `m.client` khai báo `requires m.target;`. Có chắc `Module.getResourceAsStream("p/target/config.json")` từ client trả stream không?

**Đáp án:** Không. Nếu `p.target` là package của module đích, một resource `.json` ở đó cần package mở cho caller; `exports` không tự đủ. Ngoài ra file phải tồn tại trong build output.

**Bài 2.** Package được khai báo `opens p.target to m.client;`. Vì sao `ClassLoader.getResourceAsStream("p/target/config.json")` vẫn có thể không tìm thấy?

**Đáp án:** Với resource thông thường nằm trong package named module, phương thức `ClassLoader` yêu cầu package **opened unconditionally**; qualified opens chỉ mở cho module được chỉ định.

**Bài 3.** Tại sao code gọi `Target.readClosedResource()` từ client vẫn nhận dữ liệu, dù `p.secret` không mở cho client?

**Đáp án:** Lệnh đọc resource thật sự chạy **bên trong m.target**, nơi target có thể đọc dữ liệu của chính mình; client chỉ gọi public method được phép. Đây là quyết định API của module đích, không phải client vượt encapsulation.

**Bài 4.** `Target.NestMember` truy cập private field `SECRET` được. Điều đó có cho client đọc `p/secret/private.txt` không?

**Đáp án:** Không. Nestmate access liên quan tới private member của class cùng nest, không thay thế quy tắc resource encapsulation của JPMS.

**Bài 5.** Một resource mang tên `p/secret/Marker.class` trong named module có chịu cùng quy tắc encapsulation như `p/secret/private.txt` không?

**Đáp án:** Không theo quy tắc `Module.getResourceAsStream`: tên kết thúc bằng `.class` là trường hợp ngoại lệ không bị encapsulated tại bước tìm resource; điều này không đồng nghĩa code có quyền gọi hoặc phản chiếu tùy ý lên class ấy.

## Ghi nhớ

Khả năng truy cập tài nguyên thuộc **module đích** không chỉ dựa vào `requires` hay `exports`. Với resource thường ở một package thật sự của named module, **module đích cần mở package cho module gọi**, trừ khi code đọc thực sự chạy trong module đích hoặc áp dụng ngoại lệ resource theo đặc tả. `Module.getResourceAsStream` và `Class.getResourceAsStream` có thể tôn trọng *qualified opens*, trong khi `ClassLoader.getResourceAsStream` cần *unconditional opens* đối với resource thường trong package. Quan hệ nestmate và quyền `Lookup` điều khiển truy cập thành viên/class runtime, **không tự vượt qua** quyền truy cập tài nguyên của JPMS.

### Tài liệu chính thức còn áp dụng

- [Java SE 17 — Module: getResourceAsStream, isOpen, isExported](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [Java SE 17 — Class: getResourceAsStream, getModule, isNestmateOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — ClassLoader: getResourceAsStream và quy tắc opened unconditionally](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — MethodHandles, privateLookupIn và lookup modes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java Language Specification — Module Declarations, §7.7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
- [JEP 371 — Hidden Classes (Java 15)](https://openjdk.org/jeps/371)
