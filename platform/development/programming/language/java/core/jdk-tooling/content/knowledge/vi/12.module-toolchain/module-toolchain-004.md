# Directive opens trong Java Module System

Trong Java Platform Module System (JPMS), từ Java 9, module có thể giới hạn package nào được module khác sử dụng. Directive **`opens`** trong `module-info.java` cho phép một package được mở để các module khác thực hiện reflection, bao gồm cả *deep reflection* vào thành viên không public như field hoặc method private.

`opens` thường cần thiết cho framework hoặc thư viện dùng reflection để ánh xạ object, đọc annotation, tạo proxy hoặc truy cập field private. Nó kiểm soát quyền truy cập phản chiếu ở cấp module; nó không biến thành viên private thành public và không cấp quyền truy cập trực tiếp trong mã nguồn.

## 1. Vì sao JPMS cần opens?

Trước Java 9, ứng dụng thường chạy trên classpath và nhiều thư viện có thể dùng reflection để truy cập sâu vào lớp của thư viện khác. JPMS bổ sung ranh giới module nhằm đóng gói và kiểm soát việc truy cập package.

Khi một module không mở package, module khác có thể vẫn nhìn thấy và sử dụng các kiểu public được export, nhưng không nhất thiết được phép bỏ qua kiểm tra truy cập để đọc hoặc sửa thành viên private bằng reflection.

Ví dụ, một framework có thể cần:

- Đọc field private để ánh xạ dữ liệu từ database vào object.
- Gọi constructor hoặc method không public để tạo object.
- Kiểm tra annotation và metadata trên thành viên nội bộ.
- Tạo proxy hoặc thực hiện dependency injection bằng reflection.

Directive `opens` cho phép chủ sở hữu module quyết định package nào có thể được truy cập sâu bằng reflection và module nào được phép làm việc đó.

## 2. Phân biệt exports và opens

Hai directive đều nhắc đến package, nhưng có mục đích khác nhau.

| Tiêu chí | `exports` | `opens` |
| --- | --- | --- |
| Mục đích | Công khai API của package cho module khác | Cho phép reflection truy cập sâu vào package |
| Truy cập mã nguồn thông thường | Cho phép module đọc package và dùng các kiểu public phù hợp | Không cấp quyền truy cập compile-time |
| Reflection vào public API | Có thể dùng theo quy tắc truy cập thông thường | Không bắt buộc nếu chỉ truy cập public API đã export |
| Reflection vào private member | Không tự cho phép deep reflection | Cho phép module được mở package truy cập sâu |
| Thời điểm áp dụng | Compile time và runtime | Runtime |
| Có thể giới hạn module nhận quyền | Có, bằng qualified exports | Có, bằng qualified opens |

Ví dụ:

```java
module com.example.model {
    exports com.example.model;
    opens com.example.model to com.example.reflector;
}
```

- `exports com.example.model;` cho phép module khác sử dụng API public trong package `com.example.model`.
- `opens com.example.model to com.example.reflector;` cho phép module `com.example.reflector` thực hiện deep reflection vào package đó, bao gồm thành viên private.

Một package có thể được export, được open, cả hai hoặc không có directive nào, tùy thiết kế module.

**Điểm cần nhớ:** `opens` không thay thế `exports`. Nếu mã nguồn module khác cần import và gọi một lớp public trong package, package đó vẫn cần được export hoặc được truy cập theo một cơ chế module phù hợp.

## 3. Cú pháp của opens directive

Có hai dạng cơ bản.

### Mở package cho mọi module

```java
opens com.example.model;
```

Đây là *unqualified opens*. Package được mở để tất cả module khác có thể thực hiện deep reflection vào package.

Dạng này thuận tiện khi một package cần được nhiều framework hoặc module khác nhau truy cập bằng reflection, nhưng phạm vi quyền rộng hơn.

### Chỉ mở package cho module được chỉ định

```java
opens com.example.model to com.example.reflector;
```

Đây là *qualified opens*. Chỉ module có tên `com.example.reflector` được cấp quyền deep reflection vào package `com.example.model`.

Có thể chỉ định nhiều module nhận quyền:

```java
opens com.example.model to
    com.example.reflector,
    com.example.persistence;
```

Nên ưu tiên qualified opens khi biết rõ module nào cần reflection. Cách này giới hạn bề mặt truy cập và làm rõ quan hệ giữa các module.

## 4. Mở toàn bộ module bằng open module

Ngoài việc mở từng package, module descriptor có thể khai báo:

```java
open module com.example.model {
    exports com.example.model;
}
```

Một *open module* mở tất cả package của module cho deep reflection từ các module khác ở runtime.

Cần lưu ý:

- `open module` áp dụng cho mọi package trong module.
- Có thể khai báo các directive như `requires` và `exports` bên trong open module.
- Không khai báo thêm directive `opens` riêng trong một open module.
- Open module không đồng nghĩa với việc export mọi package để mã nguồn khác import các kiểu public.

Chỉ nên dùng `open module` khi thực sự cần mở rộng toàn bộ module cho reflection. Nếu chỉ một vài package cần được framework truy cập, mở từng package thường có phạm vi rõ ràng hơn.

## 5. Ví dụ hoàn chỉnh: reflection vào private field giữa hai module

Ví dụ sau tạo hai module Java 17:

- `com.example.model`: cung cấp lớp `Secret` với field private.
- `com.example.reflector`: sử dụng reflection để đọc field private của `Secret`.

Cấu trúc dự án:

```text
project/
  src/
    com.example.model/
      module-info.java
      com/example/model/Secret.java
    com.example.reflector/
      module-info.java
      com/example/reflector/Main.java
```

### Bước 1: Khai báo module chứa lớp dữ liệu

Tệp **`src/com.example.model/module-info.java`**:

```java
module com.example.model {
    exports com.example.model;
    opens com.example.model to com.example.reflector;
}
```

Package được export để module reflector có thể import lớp public. Package cũng được mở riêng cho module reflector để reflection có thể truy cập field private.

### Bước 2: Tạo lớp có private field

Tệp **`src/com.example.model/com/example/model/Secret.java`**:

```java
package com.example.model;

public final class Secret {
    private final String token = "module-secret";

    public Secret() {
    }
}
```

Field `token` vẫn là private và final. Directive `opens` chỉ cho phép module được chỉ định thực hiện deep reflection vào package chứa lớp này.

### Bước 3: Khai báo module sử dụng reflection

Tệp **`src/com.example.reflector/module-info.java`**:

```java
module com.example.reflector {
    requires com.example.model;
}
```

Directive `requires` tạo quan hệ phụ thuộc compile-time giữa module reflector và module model. Vì package `com.example.model` đã được export, mã nguồn reflector có thể import lớp `Secret`.

### Bước 4: Viết chương trình reflection

Tệp **`src/com.example.reflector/com/example/reflector/Main.java`**:

```java
package com.example.reflector;

import com.example.model.Secret;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        Secret secret = new Secret();

        Field tokenField = Secret.class.getDeclaredField("token");
        tokenField.setAccessible(true);

        System.out.println("private token=" + tokenField.get(secret));
    }
}
```

Giải thích:

1. Tạo một đối tượng `Secret`.
2. `getDeclaredField("token")` lấy metadata của field được khai báo trực tiếp trong lớp, kể cả field private.
3. `setAccessible(true)` yêu cầu reflection bỏ qua kiểm tra truy cập Java thông thường cho thao tác phản chiếu này.
4. `field.get(secret)` đọc giá trị field từ đối tượng.

### Bước 5: Biên dịch hai module

Chạy từ thư mục gốc `project`:

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force mods | Out-Null
javac -d mods --module-source-path src -m com.example.model,com.example.reflector
```

**macOS/Linux:**

```bash
mkdir -p mods
javac -d mods --module-source-path src -m com.example.model,com.example.reflector
```

Sau khi biên dịch, cấu trúc đầu ra:

```text
mods/
  com.example.model/
    module-info.class
    com/example/model/Secret.class
  com.example.reflector/
    module-info.class
    com/example/reflector/Main.class
```

### Bước 6: Chạy module reflector

Chạy:

```bash
java --module-path mods -m com.example.reflector/com.example.reflector.Main
```

Kết quả:

```text
private token=module-secret
```

Kết quả thành công vì package `com.example.model` được mở cho module `com.example.reflector`. Mã nguồn vẫn giữ field `token` là private; chỉ thao tác reflection được cấp quyền truy cập sâu.

## 6. Điều gì xảy ra nếu không có opens?

Nếu module model chỉ khai báo:

```java
module com.example.model {
    exports com.example.model;
}
```

Mã nguồn reflector vẫn có thể biên dịch vì package được export và lớp `Secret` là public. Tuy nhiên, khi chạy, lệnh:

```java
tokenField.setAccessible(true);
```

không thể bỏ qua kiểm tra truy cập vì package không được mở cho module reflector.

Trên Java 17, thao tác này thường ném `java.lang.reflect.InaccessibleObjectException`. Thông báo cụ thể phụ thuộc tên module và package, nhưng nguyên nhân là module nguồn chưa mở package cho module gọi reflection.

Có thể dùng `trySetAccessible()` để kiểm tra trước:

```java
if (tokenField.trySetAccessible()) {
    System.out.println(tokenField.get(secret));
} else {
    System.out.println("Deep reflection is not allowed");
}
```

- Trả về `true`: quyền truy cập sâu đã được bật cho đối tượng phản chiếu.
- Trả về `false`: không thể bật quyền truy cập sâu theo cấu hình hiện tại.
- Nếu dùng `setAccessible(true)` và module không mở package, Java có thể ném `InaccessibleObjectException`.

`trySetAccessible()` và `setAccessible(true)` không sửa module descriptor hoặc access modifier. Chúng chỉ yêu cầu quyền phản chiếu cho đối tượng `Field`, `Method` hoặc `Constructor` tương ứng.

## 7. Dùng --add-opens khi chạy ứng dụng

Nếu không thể sửa `module-info.java` của module nguồn, Java launcher cung cấp tùy chọn runtime `--add-opens`.

Cú pháp:

```text
--add-opens source.module/package=target.module
```

Trong đó:

- `source.module`: module chứa package cần mở.
- `package`: package cần cho phép deep reflection.
- `target.module`: module được cấp quyền truy cập.

Với ví dụ trên, nếu `com.example.model` không khai báo directive `opens`, có thể chạy:

```bash
java --module-path mods --add-opens com.example.model/com.example.model=com.example.reflector -m com.example.reflector/com.example.reflector.Main
```

Kết quả:

```text
private token=module-secret
```

Tùy chọn `--add-opens` bổ sung quyền mở package tại runtime cho lần khởi chạy đó. Nó hữu ích khi tích hợp thư viện cũ hoặc framework chưa có cấu hình module phù hợp.

### Mở package cho code trên classpath

Code chạy trên classpath thuộc unnamed module. Có thể mở package cho các module không tên bằng:

```bash
java --module-path mods --add-opens com.example.model/com.example.model=ALL-UNNAMED -cp app.jar app.LegacyMain
```

`ALL-UNNAMED` đại diện cho các unnamed module. Tùy chọn này chỉ nên dùng khi ứng dụng thực sự chạy code cần reflection trên classpath.

Không nên mở toàn bộ package của nhiều module cho `ALL-UNNAMED` nếu chỉ một framework hoặc thư viện cụ thể cần quyền đó. Hãy giới hạn module nguồn, package và đối tượng nhận quyền.

## 8. Phân biệt opens trong module-info và --add-opens

| Tiêu chí | Directive `opens` | Tùy chọn `--add-opens` |
| --- | --- | --- |
| Khai báo ở đâu | `module-info.java` | Dòng lệnh Java launcher |
| Thời điểm | Là một phần của module descriptor, áp dụng khi module được nạp | Runtime của lần khởi chạy |
| Phạm vi | Một package, có thể qualified hoặc unqualified | Một package của module nguồn cho module đích |
| Mục đích | Thiết kế quyền reflection như một phần của module | Bổ sung quyền mở khi chạy mà không sửa module descriptor |
| Phù hợp | Module chủ động hỗ trợ framework/reflection | Tích hợp legacy hoặc xử lý cấu hình triển khai |

Ưu tiên khai báo `opens` trong module descriptor khi quyền reflection là một phần có chủ đích trong thiết kế module. Dùng `--add-opens` khi cần cấu hình runtime, ví dụ để chạy thư viện cũ hoặc kiểm thử một ứng dụng chưa thể thay đổi module descriptor.

## 9. opens không thay đổi access modifier

Giả sử lớp có:

```java
private String token;
```

Ngay cả khi package đã được mở, field vẫn có access flag private trong class file. Directive `opens` không thay đổi:

- Từ khóa `private`, `protected` hoặc `public` trong mã nguồn.
- Access flags trong class file.
- Khả năng gọi trực tiếp private method từ mã nguồn của module khác.
- Quan hệ kế thừa hoặc visibility của lớp.

Mã nguồn module khác vẫn không thể viết:

```java
secret.token = "changed"; // Không hợp lệ: token là private
```

Muốn thao tác với thành viên private, mã phải dùng reflection và module phải mở package cho module gọi. Reflection vẫn chịu những giới hạn của Java, ví dụ các ràng buộc đặc biệt đối với final field và các đối tượng không cho phép sửa đổi.

## 10. opens không đồng nghĩa với requires hoặc exports

Một module descriptor có thể chứa nhiều directive khác nhau:

```java
module com.example.application {
    requires com.example.model;
}
```

- `requires` khai báo module phụ thuộc để module hiện tại đọc module đó.
- `exports` công khai package để module khác dùng API public.
- `opens` cho phép module khác deep reflection vào package.

Các directive không thay thế nhau. Ví dụ, module reflector cần `requires com.example.model` để biên dịch khi import lớp `Secret`; module model cần `exports com.example.model` để công khai lớp đó; và cần `opens` nếu reflector phải truy cập private field bằng reflection.

## 11. Chọn qualified opens hay unqualified opens?

Nên chọn phạm vi nhỏ nhất đáp ứng yêu cầu.

**Dùng qualified opens khi:**

- Chỉ một framework hoặc module cụ thể cần reflection.
- Muốn thể hiện rõ module nào được truy cập sâu.
- Muốn giảm phạm vi package bị mở.

Ví dụ:

```java
opens com.example.persistence.model to
    org.example.orm,
    com.example.json;
```

**Dùng unqualified opens khi:**

- Package cần hỗ trợ nhiều module không thể liệt kê trước.
- Thiết kế thư viện chủ động cho phép mọi module thực hiện reflection vào package.
- Phạm vi mở rộng đã được đánh giá và chấp nhận.

Ví dụ:

```java
opens com.example.dto;
```

**Dùng open module khi:**

- Gần như mọi package trong module đều cần được truy cập sâu bằng reflection.
- Module được thiết kế như một vùng dữ liệu cho framework.
- Việc mở toàn bộ package là có chủ đích và đã được đánh giá.

Tránh dùng open module chỉ để xử lý một lỗi reflection đơn lẻ. Mở đúng package thường dễ bảo trì và kiểm soát hơn.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `InaccessibleObjectException` | Package chưa mở cho module gọi reflection | Thêm qualified `opens` hoặc cấu hình `--add-opens` |
| `trySetAccessible()` trả về `false` | Module nguồn không mở package cho module đích | Kiểm tra tên module và package trong directive |
| Không import được lớp public dù có opens | `opens` không cấp quyền truy cập compile-time | Thêm `exports` nếu cần dùng API public |
| Đã thêm opens nhưng vẫn lỗi | Mở nhầm package hoặc nhầm target module | Kiểm tra package khai báo và tên module thực tế |
| Lỗi chỉ xuất hiện khi chạy bằng IDE | IDE dùng cấu hình launcher/module path khác | Thêm VM option vào cấu hình chạy của IDE |
| Framework cũ lỗi trên Java 17 | Framework dùng deep reflection vào package không được mở | Nâng framework hoặc mở đúng package cho module cần thiết |
| Mở package cho unnamed module nhưng vẫn lỗi | Ứng dụng chạy trên named module hoặc target chưa đúng | Dùng tên module đích hoặc `ALL-UNNAMED` theo cách ứng dụng được khởi chạy |

Khi chẩn đoán, hãy đọc đầy đủ thông báo lỗi. Thông báo thường cho biết module nguồn, package đang bị đóng và module đích cần được cấp quyền.

## 13. Thực hành tốt về bảo mật và bảo trì

- Chỉ mở package thật sự cần thiết cho reflection.
- Ưu tiên qualified opens để giới hạn module nhận quyền.
- Giữ API public riêng biệt với package nội bộ cần deep reflection.
- Không mở toàn bộ module chỉ để giải quyết một lỗi ở một package.
- Hạn chế dùng `--add-opens` toàn cục hoặc mở nhiều package cho `ALL-UNNAMED`.
- Khi có thể, nâng framework để hỗ trợ JPMS thay vì duy trì nhiều cờ runtime.
- Kiểm tra module path và tên module thực tế trong môi trường production.
- Không coi `opens` là cơ chế bảo vệ bí mật. Mọi code được cấp quyền reflection vẫn có thể đọc dữ liệu nội bộ trong phạm vi package đã mở.
- Khi thay đổi module descriptor, chạy lại kiểm thử tích hợp để phát hiện framework hoặc thư viện phụ thuộc reflection.

## 14. Ghi nhớ

- `opens` là directive JPMS cho phép deep reflection vào một package.
- `opens package;` mở package cho mọi module.
- `opens package to module.name;` chỉ mở package cho module được chỉ định.
- `open module` mở tất cả package cho reflection ở runtime.
- `exports` cho phép truy cập API public thông thường; `opens` cho phép reflection sâu.
- `--add-opens source.module/package=target.module` bổ sung quyền mở package khi chạy.
- `ALL-UNNAMED` đại diện cho code chạy trên classpath.
- `opens` không đổi access modifier và không cấp quyền gọi private member trực tiếp từ mã nguồn.

Khi hiểu rõ `opens`, bạn có thể thiết kế module tương thích với framework dùng reflection, xử lý lỗi `InaccessibleObjectException` và vẫn giới hạn quyền truy cập nội bộ ở phạm vi cần thiết.
