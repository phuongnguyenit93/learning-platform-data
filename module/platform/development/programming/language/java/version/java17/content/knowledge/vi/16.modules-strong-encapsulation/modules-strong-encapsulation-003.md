# `exports` cho API công khai và `opens` cho reflection trong Java 17

Java Platform Module System (JPMS) cho phép một ứng dụng chia thành các **module có tên**, khai báo phụ thuộc và kiểm soát package nào được module khác truy cập. Trong một module, không phải package nào cũng tự động trở thành API cho module bên ngoài.

Hai directive quan trọng trong `module-info.java` là:

- **`exports`**: công khai một package để các module khác có thể sử dụng các kiểu và thành viên được phép truy cập theo quy tắc Java.
- **`opens`**: cho phép module khác truy cập sâu vào package bằng reflection ở runtime, kể cả những thành viên không public khi quyền truy cập được bật phù hợp.

Hai directive giải quyết hai nhu cầu khác nhau. `exports` phục vụ việc sử dụng API trong mã nguồn và truy cập thông thường; `opens` phục vụ reflection sâu ở runtime, thường gặp ở framework serialization, dependency injection hoặc persistence. Một package có thể vừa được export vừa được open nếu ứng dụng thật sự cần cả hai quyền.

## 1. Vì sao module cần kiểm soát package?

Trước khi có JPMS, một ứng dụng Java thường được tổ chức theo package và JAR. Package giúp nhóm lớp theo namespace, nhưng bản thân package không tạo ra ranh giới đóng gói mạnh giữa các JAR. Các lớp public trên classpath thường có thể được code khác tham chiếu nếu JAR nằm trên classpath.

JPMS bổ sung ranh giới ở cấp module. Một module có thể:

- Khai báo tên module.
- Khai báo module phụ thuộc bằng `requires`.
- Công khai một số package bằng `exports`.
- Mở một số package cho reflection bằng `opens`.
- Khai báo service được sử dụng hoặc cung cấp bằng `uses` và `provides`.

Ví dụ một module thư viện có thể chứa:

```text
com.acme.library
├── com.acme.api
│   └── Greeter.java
└── com.acme.internal
    └── NameFormatter.java
```

Thư viện muốn người dùng gọi `Greeter`, nhưng muốn giữ `NameFormatter` là chi tiết triển khai. Module descriptor có thể export package API và không export package nội bộ:

```java
module com.acme.library {
    exports com.acme.api;
}
```

Kết quả là module khác có thể dùng các kiểu public trong `com.acme.api` nếu module đó đọc được `com.acme.library`. Package `com.acme.internal` vẫn nằm trong module và không được công khai qua ranh giới module.

**Không export package không có nghĩa lớp bên trong package phải là private.** Lớp có thể vẫn là public để các lớp khác trong cùng module sử dụng; module descriptor kiểm soát việc module bên ngoài có được truy cập package đó hay không.

## 2. `exports`: công khai package cho mã nguồn của module khác

Cú pháp cơ bản:

```java
module com.acme.library {
    exports com.acme.api;
}
```

Directive `exports` công khai package `com.acme.api` cho các module khác. Module tiêu thụ vẫn cần khai báo phụ thuộc bằng `requires`.

Ví dụ module client:

```java
module com.acme.client {
    requires com.acme.library;
}
```

Lớp client có thể import kiểu public trong package đã export:

```java
package com.acme.client;

import com.acme.api.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Lan"));
    }
}
```

Hai điều kiện cần nhớ:

1. Module client phải đọc module thư viện, thường thông qua `requires com.acme.library;`.
2. Package chứa kiểu được sử dụng phải được module thư viện export cho module client.

Nếu thiếu `requires`, module client không có quan hệ readability cần thiết. Nếu thiếu `exports`, package có thể tồn tại trong module thư viện nhưng không được client sử dụng như API thông thường.

### `exports` không bỏ qua modifier của Java

Export package không làm tất cả thành viên trở thành public. Các quy tắc truy cập của ngôn ngữ Java vẫn áp dụng:

- Kiểu top-level package-private vẫn không thể được import từ package khác.
- Thành viên `private` vẫn chỉ truy cập được trong phạm vi được Java cho phép.
- Thành viên package-private không tự trở nên public.
- Thành viên `protected` vẫn tuân theo quy tắc truy cập protected, bao gồm điều kiện kế thừa khi truy cập từ package khác.

`exports` mở package ở cấp module; nó không xóa các quy tắc truy cập của class, field, constructor hay method.

## 3. Ví dụ hoàn chỉnh: export API, giữ package nội bộ

Tạo cấu trúc source cho hai module:

```text
src/
├── com.acme.library/
│   ├── module-info.java
│   ├── com/acme/api/Greeter.java
│   └── com/acme/internal/NameFormatter.java
└── com.acme.client/
    ├── module-info.java
    └── com/acme/client/Main.java
```

### Module thư viện

Tệp `src/com.acme.library/module-info.java`:

```java
module com.acme.library {
    exports com.acme.api;
}
```

Tệp `src/com.acme.library/com/acme/api/Greeter.java`:

```java
package com.acme.api;

import com.acme.internal.NameFormatter;

public class Greeter {

    public String greet(String name) {
        return "Hello, " + NameFormatter.format(name);
    }
}
```

Tệp `src/com.acme.library/com/acme/internal/NameFormatter.java`:

```java
package com.acme.internal;

final class NameFormatter {

    private NameFormatter() {
    }

    static String format(String name) {
        if (name == null || name.isBlank()) {
            return "Guest";
        }

        return name.strip();
    }
}
```

`NameFormatter` không cần public vì chỉ `Greeter` trong cùng module sử dụng. Package `com.acme.internal` không được export, nên client không thể import lớp nội bộ này.

### Module client

Tệp `src/com.acme.client/module-info.java`:

```java
module com.acme.client {
    requires com.acme.library;
}
```

Tệp `src/com.acme.client/com/acme/client/Main.java`:

```java
package com.acme.client;

import com.acme.api.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();

        System.out.println(greeter.greet("  Lan  "));
        System.out.println(greeter.greet(" "));
    }
}
```

Biên dịch cả hai module từ thư mục gốc của dự án:

```bash
javac --module-source-path src -d out -m com.acme.library,com.acme.client
```

Chạy module client:

```bash
java --module-path out -m com.acme.client/com.acme.client.Main
```

Kết quả:

```text
Hello, Lan
Hello, Guest
```

Nếu thêm `import com.acme.internal.NameFormatter;` vào client, code sẽ không biên dịch được vì package `com.acme.internal` chưa được export. Đây chính là mục đích của đóng gói mạnh: module thư viện chỉ công khai bề mặt API đã chọn.

## 4. Qualified exports: chỉ công khai cho module được chỉ định

Không phải lúc nào thư viện cũng muốn export package cho tất cả module. Có thể dùng **qualified exports** để chỉ định module được phép truy cập:

```java
module com.acme.library {
    exports com.acme.api to com.acme.client;
}
```

Cú pháp tổng quát:

```java
exports package.name to module.one, module.two;
```

Trong ví dụ trên, package `com.acme.api` chỉ được export cho module `com.acme.client`. Module khác dù có `requires com.acme.library;` cũng không được tự động sử dụng package này như API công khai.

Qualified exports hữu ích khi:

- Một package là API nội bộ dùng chung giữa một số module trong cùng hệ thống.
- Một thư viện cung cấp package dành riêng cho module tích hợp hoặc adapter.
- Muốn thu hẹp bề mặt API công khai trong một ứng dụng modular lớn.

Đây vẫn là export cho truy cập thông thường, không phải cơ chế cấp quyền deep reflection. Nếu framework trong module được chỉ định cần truy cập private member, phải xem xét `opens` riêng.

## 5. `opens`: mở package cho reflection ở runtime

Reflection cho phép chương trình khám phá kiểu, constructor, method và field khi chạy. Ví dụ framework có thể tìm annotation, gọi constructor hoặc đọc field để ánh xạ object thành JSON.

Trong module có đóng gói mạnh, việc biết tên một lớp không đồng nghĩa với việc được quyền truy cập sâu vào mọi thành viên của lớp đó.

Directive `opens` mở package cho **deep reflection ở runtime**:

```java
module com.acme.model {
    opens com.acme.model.internal;
}
```

`opens com.acme.model.internal;` cho phép code trong các module khác thực hiện reflection sâu vào package đó, theo các quy tắc của Java Reflection API.

Có thể giới hạn quyền mở cho một module cụ thể:

```java
module com.acme.model {
    opens com.acme.model.internal to com.acme.inspector;
}
```

Đây là **qualified opens**. Chỉ module `com.acme.inspector` được cấp quyền mở package này cho reflection sâu.

### `opens` không làm package thành API nguồn

Một module khác không thể import lớp trong package chỉ vì package đó được mở:

```java
// Module com.acme.inspector:
import com.acme.model.internal.Account; // Không được phép nếu package chưa exports.
```

`opens` không thay thế `exports`. Nó cho phép truy cập thông qua reflection ở runtime, không cấp quyền sử dụng package như API Java thông thường khi biên dịch.

Đây là khác biệt quan trọng nhất:

| Directive | Mục đích | Cho phép import kiểu public trong package từ module khác? | Cho phép deep reflection vào private member? |
| --- | --- | --- | --- |
| `exports` | Truy cập API thông thường giữa module. | Có, nếu module consumer đọc module nguồn và kiểu/thành viên đáp ứng modifier Java. | Không tự cấp quyền deep reflection vào private member. |
| `opens` | Reflection sâu ở runtime. | Không. | Có, đối với module được mở và theo quy tắc reflection. |
| Cả `exports` và `opens` | Vừa công khai API vừa cho phép framework reflection sâu. | Có. | Có. |

## 6. Ví dụ reflection: đọc private field từ module khác

Giả sử module model muốn giữ package nội bộ không export, nhưng cho phép một module inspector đọc dữ liệu bằng reflection.

Cấu trúc:

```text
src/
├── com.acme.model/
│   ├── module-info.java
│   └── com/acme/model/internal/Account.java
└── com.acme.inspector/
    ├── module-info.java
    └── com/acme/inspector/Main.java
```

### Module model

Tệp `src/com.acme.model/module-info.java`:

```java
module com.acme.model {
    opens com.acme.model.internal to com.acme.inspector;
}
```

Tệp `src/com.acme.model/com/acme/model/internal/Account.java`:

```java
package com.acme.model.internal;

public class Account {

    private String token = "demo-token";

    public Account() {
    }
}
```

Package `com.acme.model.internal` không được export. Client không thể dùng `Account` như kiểu API trong mã nguồn thông thường.

### Module inspector

Tệp `src/com.acme.inspector/module-info.java`:

```java
module com.acme.inspector {
    requires com.acme.model;
}
```

Tệp `src/com.acme.inspector/com/acme/inspector/Main.java`:

```java
package com.acme.inspector;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class Main {

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> accountType = Class.forName(
                "com.acme.model.internal.Account"
        );

        Constructor<?> constructor =
                accountType.getDeclaredConstructor();

        if (!constructor.trySetAccessible()) {
            throw new IllegalStateException(
                    "Không thể truy cập constructor bằng reflection"
            );
        }

        Object account = constructor.newInstance();

        Field tokenField = accountType.getDeclaredField("token");

        if (!tokenField.trySetAccessible()) {
            throw new IllegalStateException(
                    "Package chưa được mở cho reflection"
            );
        }

        Object token = tokenField.get(account);

        System.out.println(token);
    }
}
```

Biên dịch:

```bash
javac --module-source-path src -d out -m com.acme.model,com.acme.inspector
```

Chạy:

```bash
java --module-path out -m com.acme.inspector/com.acme.inspector.Main
```

Kết quả:

```text
demo-token
```

Điểm cần chú ý:

1. Module inspector không import `Account`; nó tìm lớp bằng tên ở runtime.
2. Package `com.acme.model.internal` được mở có mục tiêu cho `com.acme.inspector`.
3. `trySetAccessible()` yêu cầu quyền truy cập reflection. Nếu quyền không được cấp, phương thức trả `false`.
4. Khi đã truy cập được constructor và field, reflection có thể tạo object và đọc private field.

Ví dụ này minh họa quyền kỹ thuật của reflection. Ứng dụng thực tế không nên mở private field tùy tiện nếu có thể dùng API public hoặc accessor được thiết kế rõ ràng.

## 7. `setAccessible`, `trySetAccessible` và lỗi đóng gói mạnh

Reflection API có các phương thức kiểm soát access check:

- `setAccessible(true)` yêu cầu bỏ qua kiểm tra truy cập Java trong phạm vi được phép.
- `trySetAccessible()` thử bật quyền truy cập và trả về `true` hoặc `false` tùy khả năng.
- `canAccess(target)` kiểm tra đối tượng hiện có quyền truy cập thành viên hay không.

Trong module không mở package cho caller, cố gắng mở private member có thể thất bại. `setAccessible(true)` có thể ném `InaccessibleObjectException`; `trySetAccessible()` trả `false` trong trường hợp không thể bật quyền.

Ví dụ:

```java
Field field = accountType.getDeclaredField("token");

boolean accessible = field.trySetAccessible();

if (!accessible) {
    System.out.println("Không được phép truy cập sâu");
}
```

Nếu package được mở cho module gọi reflection, `trySetAccessible()` có thể thành công. Nếu package chỉ được export mà không được open, truy cập thông thường vào public API có thể được phép, nhưng deep reflection vào private member vẫn bị giới hạn.

Không nên bắt `InaccessibleObjectException` rồi bỏ qua như thể thao tác đã thành công. Hãy xác định module nào cần truy cập, package nào cần mở và cấu hình descriptor đúng phạm vi.

## 8. `exports` và `opens` có thể cùng áp dụng cho một package

Một package có thể vừa là API công khai vừa cần framework truy cập sâu vào object.

Ví dụ:

```java
module com.acme.domain {
    exports com.acme.domain.api;

    opens com.acme.domain.model to com.acme.json;
}
```

Trong đó:

- `com.acme.domain.api` được export cho các module tiêu thụ API.
- `com.acme.domain.model` được mở cho module `com.acme.json` để framework JSON thực hiện reflection sâu.

Nếu cùng package cần cả hai quyền, có thể khai báo cả hai directive:

```java
module com.acme.domain {
    exports com.acme.domain.model;
    opens com.acme.domain.model to com.acme.json;
}
```

Cần cân nhắc xem package model có thực sự nên là API công khai không. Nhiều thiết kế chỉ export DTO hoặc API ổn định, rồi mở một package triển khai cụ thể cho framework.

Không cần mở toàn bộ module chỉ vì một framework cần truy cập vài package. Qualified opens giúp giảm bề mặt truy cập reflection.

## 9. `open module`: mở toàn bộ package cho reflection

Nếu module khai báo:

```java
open module com.acme.application {
    exports com.acme.application.api;
}
```

thì tất cả package trong module được mở cho deep reflection ở runtime. Tuy nhiên, điều này **không có nghĩa tất cả package đều được export cho truy cập nguồn**.

Trong một `open module`:

- Mọi package được mở cho reflection ở runtime.
- Các package vẫn cần `exports` nếu muốn module khác import và dùng API thông thường.
- Không khai báo thêm các directive `opens` riêng trong thân `open module`; module đã mở toàn bộ package.
- Có thể vẫn dùng `exports` để công khai API theo nhu cầu.

So sánh:

```java
module com.acme.application {
    opens com.acme.application.model;
}
```

Chỉ package `com.acme.application.model` được mở.

```java
open module com.acme.application {
}
```

Mọi package của module được mở cho reflection.

Vì `open module` cấp quyền rộng hơn, chỉ nên sử dụng khi thật sự cần framework hoặc cơ chế runtime truy cập sâu trên toàn module. Trong ứng dụng thông thường, mở đúng package và đúng module đích thường an toàn và dễ hiểu hơn.

## 10. Framework cần reflection: nên mở package nào?

Một số framework cần reflection để:

- Đọc field và annotation.
- Gọi constructor, kể cả constructor không public.
- Gán giá trị vào field hoặc property.
- Tạo proxy hoặc thực hiện injection.
- Ánh xạ object với bảng dữ liệu hoặc JSON.

Nếu framework nằm trong module riêng, package chứa class được xử lý có thể cần mở cho module framework đó.

Ví dụ module ứng dụng:

```java
module com.acme.app {
    requires com.acme.json;
    requires com.acme.persistence;

    exports com.acme.app.api;

    opens com.acme.app.dto to com.acme.json;
    opens com.acme.app.entity to com.acme.persistence;
}
```

Ý nghĩa:

- API được export để module khác gọi.
- DTO được mở cho module JSON.
- Entity được mở cho module persistence.
- Package nội bộ khác vẫn đóng.

Tên module thực tế phụ thuộc module descriptor của framework. Không nên đoán tên module dựa trên tên artifact Maven/Gradle; hãy kiểm tra tên module được khai báo trong JAR (ví dụ bằng `jar --describe-module`) hoặc tài liệu chính thức của framework.

Nếu framework chạy trên classpath trong unnamed module, qualified opens có thể nhắm đến `ALL-UNNAMED`. Tuy nhiên, chỉ dùng khi thật sự cần tương thích với framework không modular; với ứng dụng modular, ưu tiên mở cho named module cụ thể.

## 11. `ALL-UNNAMED` và code trên classpath

Một ứng dụng có thể kết hợp named module và thư viện chạy trên classpath. Code trên classpath thuộc **unnamed module** của class loader tương ứng.

Trong module descriptor, qualified `opens` và `exports` nhắm tới các named module. Khi cần cấp quyền tạm thời cho code trong unnamed module, có thể dùng tùy chọn dòng lệnh `--add-opens`:

```bash
java --add-opens com.acme.model/com.acme.model.internal=ALL-UNNAMED \
     --module-path out \
     -m com.acme.inspector/com.acme.inspector.Main
```

Tùy chọn này mở package `com.acme.model.internal` của module `com.acme.model` cho code thuộc unnamed module ở runtime.

Nếu muốn mở package cho một named module cụ thể bằng dòng lệnh:

```bash
java --add-opens com.acme.model/com.acme.model.internal=com.acme.inspector \
     --module-path out \
     -m com.acme.inspector/com.acme.inspector.Main
```

`--add-opens` là tùy chọn runtime. Nó không làm package trở thành API có thể import khi biên dịch.

Tương tự, `--add-exports` bổ sung quyền export cho một package tới module đích. Tùy chọn này có thể hữu ích khi tích hợp hoặc chẩn đoán ứng dụng cũ, nhưng không nên dùng để che giấu một module descriptor thiết kế thiếu rõ ràng.

## 12. Phân biệt `--add-exports` và `--add-opens`

Hai tùy chọn dòng lệnh có tên gần nhau nhưng mục đích khác nhau:

| Tùy chọn | Thời điểm | Mục đích |
| --- | --- | --- |
| `--add-exports sourceModule/package=targetModule` | Có thể dùng khi biên dịch và chạy. | Bổ sung quyền export package cho module đích, phục vụ truy cập API thông thường. |
| `--add-opens sourceModule/package=targetModule` | Runtime. | Bổ sung quyền mở package cho deep reflection. |

Ví dụ:

```bash
javac --add-exports com.acme.model/com.acme.model.api=com.acme.client ...
```

là quyền export bổ sung cho quá trình biên dịch (và khi chạy cũng cần quyền tương ứng nếu ứng dụng dựa vào export đó).

Trong khi:

```bash
java --add-opens com.acme.model/com.acme.model.internal=com.acme.inspector ...
```

là quyền mở package ở runtime để reflection sâu.

Không nhầm `--add-opens` với `--add-exports`: một package được mở cho reflection không tự động trở thành package được export cho mã nguồn.

## 13. `requires`, `exports` và `opens` là ba việc khác nhau

Một lỗi thường gặp là nghĩ rằng chỉ cần `exports` là module consumer có thể truy cập package. Thực tế, JPMS tách ba khái niệm:

- **Readability:** module consumer đọc được module cung cấp hay không, thường được khai báo bằng `requires`.
- **Export:** package có được công khai cho truy cập thông thường hay không.
- **Open:** package có được mở cho deep reflection ở runtime hay không.

Ví dụ:

```java
// Module com.acme.library
module com.acme.library {
    exports com.acme.api;
}
```

```java
// Module com.acme.client
module com.acme.client {
    requires com.acme.library;
}
```

`com.acme.client` đọc `com.acme.library` và được phép truy cập package `com.acme.api` vì package đó đã export. Nếu muốn framework trong `com.acme.json` đọc private field trong package `com.acme.model`, module thư viện cần thêm `opens` phù hợp.

Có thể ghi nhớ bằng bảng:

| Directive | Trả lời câu hỏi |
| --- | --- |
| `requires` | Module của tôi phụ thuộc/đọc module nào? |
| `exports` | Module khác được dùng package nào như API thông thường? |
| `opens` | Module nào được reflection sâu vào package nào ở runtime? |

## 14. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `package ... is not visible` | Module consumer chưa đọc module nguồn hoặc package chưa được export. | Kiểm tra `requires` và `exports`. |
| `module ... does not read ...` | Thiếu quan hệ readability. | Thêm `requires` phù hợp vào module consumer. |
| `package ... is declared in module ..., which does not export it` | Package tồn tại nhưng không export cho module đang dùng. | Export package công khai hoặc thiết kế API qua package đã export. |
| Import được class nhưng không gọi được thành viên | Modifier Java của class/member không cho phép truy cập. | Kiểm tra `public`, `protected`, package-private và `private`. `exports` không xóa các quy tắc này. |
| `trySetAccessible()` trả `false` | Package không mở cho module gọi reflection hoặc điều kiện truy cập không được đáp ứng. | Thêm `opens package to caller.module;` nếu deep reflection thực sự cần thiết. |
| `InaccessibleObjectException` | Code cố bật access sâu nhưng module không mở package. | Mở đúng package cho module đích hoặc dùng API public. |
| Framework không đọc được private field | Package chứa model/entity chưa được mở cho module framework. | Dùng qualified `opens` đúng tên module framework. |
| `opens` đã khai báo nhưng import vẫn lỗi | `opens` chỉ cấp quyền reflection runtime, không export package cho mã nguồn. | Thêm `exports` nếu cần truy cập nguồn; giữ `opens` cho reflection nếu cần. |
| Qualified opens không có tác dụng với framework trên classpath | Target thực tế là unnamed module, không phải named module đã chỉ định. | Kiểm tra cách chạy framework; cân nhắc `ALL-UNNAMED` nếu phù hợp. |
| Mở toàn module nhưng import package vẫn lỗi | `open module` mở cho reflection, không export tất cả package. | Khai báo `exports` cho package cần làm API. |

## 15. Nguyên tắc thiết kế module an toàn

Khi thiết kế module cho ứng dụng Java 17, nên xác định rõ package nào là API và package nào chỉ phục vụ triển khai.

### Chỉ export API ổn định

Chọn package có kiểu và hợp đồng mà module khác thực sự cần dùng. Tránh export toàn bộ package nội bộ chỉ để giải quyết lỗi compile. Mỗi package được export trở thành một phần của bề mặt API mà các module khác có thể phụ thuộc.

### Chỉ open cho framework cần thiết

Nếu một framework chỉ cần reflection trên entity, hãy mở package entity cho module framework tương ứng. Không mở toàn module khi chỉ một package cần truy cập.

### Ưu tiên qualified directive

Nếu biết module tiêu thụ hoặc framework cụ thể, dùng dạng qualified:

```java
module com.acme.domain {
    exports com.acme.domain.api to com.acme.application;

    opens com.acme.domain.entity to com.acme.persistence;
}
```

Điều này giúp quyền truy cập được giới hạn theo mục đích.

### Ưu tiên API công khai thay vì reflection sâu khi có thể

Nếu module khác chỉ cần đọc dữ liệu, một accessor public hoặc API chuyên biệt có thể rõ ràng và bền vững hơn mở private field. Reflection sâu phù hợp với framework hoặc công cụ cần cơ chế tổng quát, nhưng không nên trở thành cách giao tiếp mặc định giữa các module.

### Không mở private state chỉ để tiện debug

Mở package cho reflection có thể cho phép module đích đọc hoặc thay đổi trạng thái nội bộ. Chỉ cấp quyền khi có lý do rõ ràng, và xem xét dữ liệu nhạy cảm trong các entity hoặc object đó.

## 16. Quy trình chọn giữa exports và opens

Khi một module khác cần truy cập package, hãy xác định trước cách truy cập:

```text
Module khác cần dùng package?
             |
             v
     Có import class trong source?
             |
       +-----+-----+
       |           |
      Có          Không
       |           |
       v           v
    requires?   Dùng reflection?
       |           |
       v           v
    exports?    Deep reflection?
       |           |
       v       +---+---+
 API thông     |       |
 thường       Có     Không
                |       |
                v       v
              opens   Kiểm tra quyền
              package reflection thông thường
```

- Nếu module khác cần import kiểu và gọi API công khai, cần readability và `exports`.
- Nếu framework cần truy cập private field hoặc constructor bằng reflection, cần `opens` cho module framework.
- Nếu cần cả hai, khai báo cả `exports` và `opens` theo package và module đích.
- Nếu package chỉ dùng nội bộ trong cùng module, thường không cần export hoặc open.

## 17. Ghi nhớ nhanh

| Nhu cầu | Directive/cấu hình |
| --- | --- |
| Công khai package cho mọi module đọc module hiện tại | `exports com.acme.api;` |
| Chỉ export cho một vài module | `exports com.acme.api to com.acme.client;` |
| Mở package cho deep reflection từ mọi module | `opens com.acme.model;` |
| Chỉ mở cho một module reflection cụ thể | `opens com.acme.model to com.acme.inspector;` |
| Mở mọi package của module cho reflection | `open module com.acme.model { ... }` |
| Module consumer phụ thuộc module thư viện | `requires com.acme.library;` |
| Mở package ở runtime bằng command line | `--add-opens source/package=target` |
| Bổ sung export bằng command line | `--add-exports source/package=target` |
| Kiểm tra tên module trong JAR | `jar --describe-module --file library.jar` |

**Nguyên tắc cốt lõi:** `exports` công khai package để module khác dùng API thông thường; `opens` cấp quyền reflection sâu ở runtime. `requires` xác lập readability, còn modifier Java vẫn quyết định quyền truy cập từng class và member. Hãy export đúng package cần làm API, mở đúng package cho đúng framework và tránh cấp quyền rộng hơn nhu cầu thực tế.
