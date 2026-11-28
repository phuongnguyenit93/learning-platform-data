# Nhận diện IllegalAccessError và InaccessibleObjectException

`IllegalAccessError` và `InaccessibleObjectException` đều có thể xuất hiện khi ứng dụng cố truy cập một kiểu, thành viên hoặc trạng thái nội bộ mà module không cho phép. Tuy nhiên, hai lỗi xảy ra ở những cơ chế khác nhau: `IllegalAccessError` là lỗi liên kết khi bytecode truy cập một lớp hoặc thành viên không được phép ở runtime; `InaccessibleObjectException` là lỗi runtime reflection khi ứng dụng cố mở quyền truy cập sâu nhưng ranh giới module không cho phép.

Phân biệt đúng hai lỗi giúp tìm đúng cách sửa. Với truy cập Java thông thường, kiểm tra quan hệ đọc module và package được export. Với reflection sâu, kiểm tra package đã được open cho module gọi hay chưa. Không nên mở rộng quyền toàn JDK để che lỗi; hãy sửa module descriptor hoặc dùng tùy chọn mở quyền có phạm vi hẹp khi cần tương thích tạm thời.

Bài học thuộc chương **Đóng gói JDK** của module **JAVA_VERSION_JAVA16**. Từ Java 16, strong encapsulation được áp dụng mặc định rộng hơn; Java 17 tiếp tục củng cố việc đóng gói nội bộ JDK. Các nguyên tắc về module readability, exports, opens và chẩn đoán dưới đây vẫn áp dụng trong JDK hiện đại.

## 1. Hai lỗi này khác nhau ở đâu?

| Đặc điểm | IllegalAccessError | InaccessibleObjectException |
| --- | --- | --- |
| Loại lỗi | Linkage error, thuộc nhóm Error | Runtime exception, unchecked |
| Thời điểm thường gặp | Khi JVM liên kết hoặc thực thi bytecode có truy cập không hợp lệ | Khi reflection cố bật quyền truy cập sâu |
| Cơ chế | Truy cập lớp/thành viên bằng bytecode vượt qua giới hạn visibility hoặc module export | Gọi setAccessible(true) nhưng module không mở package cho caller |
| Ví dụ | Bytecode của module client gọi public class trong package không export từ module provider | Framework gọi Field.setAccessible(true) trên private field trong package không open |
| Hướng xử lý chính | Kiểm tra requires, exports, phiên bản binary và module graph | Kiểm tra opens, trySetAccessible và cấu hình reflection |

`IllegalAccessError` kế thừa từ `IncompatibleClassChangeError` và `LinkageError`. Nó thường xuất hiện khi bytecode được biên dịch trong một môi trường có quyền truy cập nhưng lúc chạy lại gặp module descriptor hoặc phiên bản class khác không cho phép truy cập đó.

`InaccessibleObjectException` nằm trong package `java.lang.reflect`. Nó được ném khi `AccessibleObject.setAccessible(true)` không thể bật quyền truy cập do giới hạn ngôn ngữ hoặc module. Với `trySetAccessible()`, trường hợp không thể mở quyền thường được biểu diễn bằng giá trị `false` thay vì ném exception.

## 2. Hiểu ba lớp quyền trong hệ thống module

Để truy cập một kiểu trong named module, cần phân biệt ba câu hỏi:

1. Module gọi có đọc được module đích không?
2. Package chứa kiểu có được module đích export cho module gọi không?
3. Nếu cần truy cập sâu bằng reflection, package có được open cho module gọi không?

| Cơ chế | Khai báo trong module-info.java | Tùy chọn runtime | Ý nghĩa |
| --- | --- | --- | --- |
| Readability | `requires target.module;` | `--add-reads source=target` | Module nguồn được phép đọc module đích |
| Truy cập API công khai | `exports package.name;` hoặc `exports package.name to client.module;` | `--add-exports source/package=target` | Cho phép module đích truy cập các kiểu public trong package |
| Reflection sâu | `opens package.name to client.module;` hoặc `open module` | `--add-opens source/package=target` | Cho phép reflection truy cập sâu vào thành viên của package |

Các cơ chế này không thay thế lẫn nhau. `requires` không tự export package. `exports` không đồng nghĩa package đã open để reflection sâu. `opens` không làm package trở thành API có thể import và sử dụng bình thường khi biên dịch.

## 3. Nhận diện IllegalAccessError

Ví dụ, module provider có package triển khai không export:

```java
module com.example.provider {
    // Chỉ export package API công khai.
    exports com.example.provider.api;
}
```

Module client khai báo:

```java
module com.example.client {
    requires com.example.provider;
}
```

Nếu code trong client gọi trực tiếp kiểu thuộc `com.example.provider.internal`, package đó không được export cho client. Khi biên dịch mới bằng module system, compiler thường báo package không được export. Nhưng một tình huống khác có thể xảy ra: client đã được biên dịch trước đó khi package còn được export, sau đó provider được cập nhật descriptor và bỏ export. Khi chạy với module mới, JVM có thể ném `IllegalAccessError` khi bytecode thực hiện truy cập.

Thông báo lỗi thường cho biết:

- Module nào đang thực hiện truy cập.
- Kiểu hoặc package nào bị truy cập.
- Module chứa kiểu đó.
- Package không được export cho module gọi.

Khi thấy lỗi này, đừng bắt đầu bằng cách thêm `--add-opens`. Truy cập trực tiếp từ bytecode cần quyền truy cập API thông thường; hãy kiểm tra readability và exports.

## 4. Sửa IllegalAccessError bằng module descriptor

Nếu package là API mà module provider chủ động hỗ trợ, khai báo export phù hợp:

```java
module com.example.provider {
    exports com.example.provider.api;
    exports com.example.provider.spi
        to com.example.client;
}
```

Module client vẫn cần khai báo dependency:

```java
module com.example.client {
    requires com.example.provider;
}
```

Trong ví dụ này, `com.example.provider.spi` chỉ được export tới `com.example.client`. Đây là qualified export, giới hạn API được công bố cho module cần dùng.

Nếu module provider do chính ứng dụng quản lý, sửa module descriptor là cách rõ ràng và có thể kiểm soát trong source. Không export package triển khai nội bộ chỉ để làm cho một lỗi biến mất; hãy cân nhắc chuyển kiểu cần dùng vào package API hoặc cung cấp một facade công khai.

## 5. Dùng --add-exports trong tình huống tương thích có giới hạn

Khi không thể sửa ngay module descriptor, có thể dùng `--add-exports` để cấp quyền truy cập API công khai của một package cho module đích ở runtime:

```powershell
java --add-exports com.example.provider/com.example.provider.spi=com.example.client --module-path mods --module com.example.client/com.example.client.Main
```

Cú pháp:

```text
--add-exports source.module/package.name=target.module
```

Nếu ứng dụng gọi từ classpath, caller thuộc unnamed module và có thể dùng `ALL-UNNAMED` làm target:

```powershell
java --add-exports com.example.provider/com.example.provider.spi=ALL-UNNAMED -cp "app.jar;lib/*" com.example.Main
```

`--add-exports` chỉ giải quyết quyền truy cập kiểu và thành viên public trong package được export. Nó không mở private field/method cho reflection sâu. Với module do bạn kiểm soát, ưu tiên sửa `module-info.java` để quyền truy cập được ghi nhận trong cấu trúc module.

Nếu source code cần biên dịch với package chưa export, `javac` cũng có tùy chọn `--add-exports`; khi chạy, JVM phải nhận cấu hình tương ứng để bytecode có quyền truy cập. Chỉ thêm tùy chọn ở một giai đoạn có thể khiến compile thành công nhưng runtime vẫn ném `IllegalAccessError`.

Đối với package nội bộ của JDK, việc export package không biến các lớp trong đó thành API Java SE được hỗ trợ ổn định. Không xây ứng dụng mới phụ thuộc vào `sun.*` hoặc package triển khai nội bộ chỉ vì có thể mở quyền truy cập bằng tùy chọn runtime.

## 6. Nhận diện InaccessibleObjectException

Lỗi này thường xuất hiện khi thư viện hoặc framework dùng reflection để truy cập private field, private method hoặc constructor trong một package thuộc module khác.

Ví dụ, module model export API nhưng không open package entity:

```java
module com.example.model {
    exports com.example.model;
}
```

Lớp model:

```java
package com.example.model;

public class Account {
    private String secret = "internal-value";
}
```

Module inspector đọc module model:

```java
module com.example.inspector {
    requires com.example.model;
}
```

Code reflection:

```java
package com.example.inspector;

import com.example.model.Account;
import java.lang.reflect.Field;

public class Inspector {
    public static void main(String[] args) throws Exception {
        Field secret = Account.class.getDeclaredField("secret");
        secret.setAccessible(true);

        Account account = new Account();
        System.out.println(secret.get(account));
    }
}
```

Package `com.example.model` được export nên client có thể tham chiếu public class `Account`. Nhưng package không được open, vì vậy lời gọi `setAccessible(true)` để vượt qua private access có thể ném `InaccessibleObjectException`. Export API công khai không cấp quyền reflection sâu.

## 7. Sửa InaccessibleObjectException bằng opens

Nếu module model chủ động hỗ trợ framework inspector truy cập sâu vào package, khai báo qualified open:

```java
module com.example.model {
    exports com.example.model;
    opens com.example.model to com.example.inspector;
}
```

`opens` mở package cho reflection sâu từ module đích, nhưng không biến mọi thành viên private thành API công khai để code khác gọi trực tiếp.

Nếu cần mở nhiều package cho reflection và module thực sự được thiết kế để framework introspect, có thể dùng `open module`:

```java
open module com.example.model {
}
```

Open module mở tất cả package của module cho deep reflection. Chỉ dùng khi đó là chủ đích thiết kế; qualified `opens` thường giới hạn quyền tốt hơn.

## 8. Dùng --add-opens có mục tiêu

Nếu chưa thể sửa module descriptor, có thể mở một package cho đúng module cần reflection:

```powershell
java --add-opens com.example.model/com.example.model=com.example.inspector --module-path mods --module com.example.inspector/com.example.inspector.Inspector
```

Cú pháp:

```text
--add-opens source.module/package.name=target.module
```

Với thư viện chạy trên classpath, caller thuộc unnamed module:

```powershell
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar;lib/*" com.example.Main
```

Ví dụ cuối chỉ là biện pháp tương thích có phạm vi cụ thể khi thư viện cũ cần reflection sâu vào package `java.lang`. Hãy cập nhật thư viện sang phiên bản dùng API được hỗ trợ và loại bỏ tùy chọn mở JDK package khi không còn cần.

`--add-opens` không sửa lỗi truy cập trực tiếp từ bytecode và không thay thế `--add-exports`. Chọn đúng tùy chọn dựa trên cơ chế gây lỗi.

## 9. Phân biệt với IllegalAccessException

Không nhầm `InaccessibleObjectException` với `IllegalAccessException`:

| Exception | Tình huống |
| --- | --- |
| `IllegalAccessException` | Một thao tác reflection như `Field.get()` hoặc `Method.invoke()` không có quyền truy cập cần thiết |
| `InaccessibleObjectException` | Ứng dụng cố bật quyền truy cập sâu bằng `setAccessible(true)` nhưng module boundary không cho phép |
| `IllegalAccessError` | JVM gặp truy cập không hợp lệ khi liên kết/thực thi bytecode |

Ví dụ, `trySetAccessible()` cho phép kiểm tra khả năng mở quyền mà không cần dựa vào exception:

```java
Field field = Account.class.getDeclaredField("secret");

if (field.trySetAccessible()) {
    Object value = field.get(account);
    System.out.println(value);
} else {
    System.out.println("Package is not open for deep reflection");
}
```

Nếu `trySetAccessible()` trả `false`, hãy xem đó là tín hiệu rằng code không có quyền reflection sâu. Đừng tiếp tục giả định `Field.get()` sẽ đọc được private field. Thiết kế API công khai hoặc mở package có chủ đích nếu reflection là yêu cầu hợp lệ.

## 10. Chẩn đoán module và dependency

Khi gặp lỗi truy cập, thực hiện các bước sau:

1. Đọc toàn bộ exception message và stack trace để xác định caller, target module và package.
2. Xác định ứng dụng đang chạy trên classpath hay module path.
3. Kiểm tra module descriptor của module đích.
4. Kiểm tra phiên bản JAR thực tế ở runtime có giống artifact đã compile không.
5. Phân biệt truy cập bytecode thông thường với deep reflection.
6. Chạy lại với module resolution output nếu cần xác nhận đồ thị module.

Các lệnh hữu ích:

```powershell
jar --describe-module --file lib\provider.jar
java --show-module-resolution --module-path mods --module com.example.client/com.example.client.Main
jdeps --jdk-internals app.jar
```

Ý nghĩa:

- `jar --describe-module` cho biết tên module và các directive của modular JAR.
- `java --show-module-resolution` hiển thị cách JVM giải quyết module khi khởi chạy.
- `jdeps --jdk-internals` tìm các phụ thuộc tới API nội bộ JDK trong JAR hoặc class directory.

Với dự án nhiều dependency, kiểm tra dependency tree của build tool để phát hiện nhiều phiên bản cùng artifact. Một JAR cũ có thể được nạp ở runtime dù source hiện tại đã được build với phiên bản khác.

## 11. Lộ trình xử lý lỗi theo thông báo

| Dấu hiệu | Câu hỏi đầu tiên | Hướng xử lý |
| --- | --- | --- |
| `IllegalAccessError` và thông báo package không export | Caller có đọc module đích và package đã export chưa? | Sửa `requires`/`exports` hoặc dùng qualified `--add-exports` tạm thời |
| `InaccessibleObjectException` và thông báo package không open | Thư viện nào gọi `setAccessible(true)`? | Cập nhật thư viện hoặc khai báo qualified `opens`/`--add-opens` |
| `IllegalAccessException` trong reflection | Thành viên được gọi có accessible không? | Kiểm tra API reflection và quyền truy cập đã được cấp |
| Lỗi chỉ xuất hiện ở runtime | Artifact hoặc module descriptor khi chạy có khác lúc compile không? | Kiểm tra classpath/module path và dependency thực tế |
| Lỗi phát sinh sau khi nâng JDK | Có phụ thuộc vào JDK internals hoặc deep reflection không được hỗ trợ không? | Thay bằng API chuẩn hoặc nâng cấp thư viện tương thích |

## 12. Nguyên tắc sửa lỗi bền vững

- Ưu tiên Java SE API và API công khai được module export.
- Nếu sở hữu module, khai báo `requires`, `exports` và `opens` theo nhu cầu thực.
- Chỉ mở package cần thiết và chỉ cho module cần truy cập.
- Dùng `--add-exports` cho truy cập API public; dùng `--add-opens` cho deep reflection.
- Chỉ xem tùy chọn command line là cầu nối tương thích có phạm vi, không phải thiết kế lâu dài.
- Nâng cấp framework/ORM/serializer để chúng hỗ trợ JPMS và không cần truy cập JDK internals.
- Không dựa vào package `sun.*` hoặc `com.sun.*` như API ứng dụng ổn định.
- Kiểm tra lại trên JDK mục tiêu sau khi thay module descriptor hoặc dependency.

## 13. Bài tập tự kiểm tra

Một ứng dụng có module `com.example.model` và `com.example.json`. Module model export package `com.example.model.api` nhưng không open package `com.example.model.entity`. Framework JSON có thể tạo đối tượng qua API public nhưng cần đọc private field trong entity bằng reflection.

Hãy trả lời:

1. Nếu code của module json import một public class từ package không export, lỗi truy cập bytecode nào có thể xuất hiện khi chạy binary đã compile trước đó?
2. Nếu framework gọi `Field.setAccessible(true)` trên private field của entity, lỗi nào có thể xuất hiện?
3. `exports` có đủ để framework truy cập private field không?
4. Module model nên khai báo gì nếu chỉ muốn mở entity cho module json?
5. Nếu chưa thể sửa module descriptor, tùy chọn runtime nào có phạm vi phù hợp?

**Đáp án:**

1. `IllegalAccessError`.
2. `InaccessibleObjectException`.
3. Không. `exports` cho phép truy cập API công khai; deep reflection cần package được open.
4. `opens com.example.model.entity to com.example.json;`.
5. `--add-opens com.example.model/com.example.model.entity=com.example.json`.

## Ghi nhớ

**`IllegalAccessError` thường báo bytecode đang truy cập kiểu hoặc thành viên không được phép; `InaccessibleObjectException` báo reflection không thể mở quyền truy cập sâu qua ranh giới module.** Kiểm tra riêng readability bằng `requires`, truy cập API công khai bằng `exports` và deep reflection bằng `opens`. Sửa module descriptor khi bạn sở hữu module; nếu cần tương thích tạm thời, dùng `--add-exports` hoặc `--add-opens` đúng mục đích và đúng target. Ưu tiên thay JDK internals bằng API được hỗ trợ và cập nhật thư viện tương thích với strong encapsulation.

## Tài liệu tham khảo

- [Oracle Java SE 26 — IllegalAccessError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/IllegalAccessError.html)
- [Oracle Java SE 26 — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html)
- [Oracle Java SE 26 — AccessibleObject](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Oracle Java SE 26 — The java Command: --add-exports and --add-opens](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396)
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
