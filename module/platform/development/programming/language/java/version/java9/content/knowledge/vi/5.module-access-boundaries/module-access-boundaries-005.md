# Mở package có chọn lọc bằng opens ... to

Trong Java Platform Module System (JPMS), một mô-đun có thể giữ package triển khai ở trạng thái đóng đối với mã Java thông thường, đồng thời cho phép một số mô-đun được truy cập sâu bằng reflection. Chỉ thị `opens ... to` trong `module-info.java` cung cấp quyền đó theo danh sách mô-đun đích.

Cách mở có chọn lọc thường phù hợp khi một framework hoặc thư viện cần đọc/ghi field, constructor hay method không công khai trong một package cụ thể. Mô-đun sở hữu package vẫn kiểm soát được package nào được mở và mô-đun nào được nhận quyền reflection.

## 1. Vì sao JPMS có opens?

JPMS kiểm soát hai kiểu truy cập khác nhau:

- **Truy cập mã Java thông thường**: mã ở mô-đun khác import và sử dụng các kiểu, thành viên public trong package được xuất.
- **Truy cập sâu bằng reflection**: mã dùng reflection để truy cập các thành viên không public, chẳng hạn private field hoặc private constructor. Để bỏ qua kiểm tra truy cập Java thông thường, package của đối tượng phải được mở cho mô-đun gọi reflection.

Trước JPMS, nhiều framework dựa vào reflection để ánh xạ object, tạo proxy, inject dependency hoặc đọc metadata. Khi chạy trên module path, một package trong named module được đóng theo mặc định. Việc class hoặc field được khai báo public/private vẫn tuân theo quy tắc truy cập Java; JPMS bổ sung thêm ranh giới ở cấp mô-đun.

Chỉ thị `opens` cho phép chủ sở hữu mô-đun cấp quyền reflection vào một package. Nó không tự xuất package cho mã nguồn của mô-đun khác import và sử dụng trực tiếp.

## 2. Cú pháp opens ... to

Cú pháp qualified opens:

~~~java
module com.example.model {
    opens com.example.model.internal to com.example.inspector;
}
~~~

Ý nghĩa:

- `opens` là chỉ thị mở package cho truy cập sâu bằng reflection tại runtime.
- `com.example.model.internal` là package thuộc mô-đun đang khai báo.
- `to` mở quyền cho một hoặc nhiều mô-đun đích.
- `com.example.inspector` là tên JPMS module của bên được cấp quyền.

Có thể mở cho nhiều mô-đun bằng danh sách phân cách dấu phẩy:

~~~java
module com.example.model {
    opens com.example.model.internal
        to com.example.inspector, com.example.persistence;
}
~~~

Chỉ các mô-đun có tên trong danh sách mới được quyền truy cập sâu vào package này. Tên sau `to` là tên mô-đun JPMS, không phải Maven `artifactId`, tên file JAR hay tên project Gradle.

Ngoài qualified opens, module descriptor còn hỗ trợ mở package không giới hạn mô-đun đích:

~~~java
module com.example.model {
    opens com.example.model.internal;
}
~~~

Dạng này cho phép mọi mô-đun khác truy cập sâu vào package đã chỉ định. Chỉ dùng khi package thực sự cần mở rộng rãi; nếu biết rõ framework hoặc mô-đun nào cần reflection, ưu tiên `opens ... to`.

## 3. Phân biệt opens với exports

`exports` và `opens` không thay thế nhau:

| Chỉ thị | Truy cập mã Java thông thường | Reflection vào thành viên không public | Phạm vi |
|---|---|---|---|
| `exports p;` | Cho phép mô-đun khác đọc mô-đun truy cập kiểu public trong package | Không tự cấp quyền deep reflection | Tất cả mô-đun đọc mô-đun này |
| `exports p to m;` | Cho phép mô-đun `m` truy cập kiểu public trong package | Không tự cấp quyền deep reflection | Chỉ mô-đun được nêu tên |
| `opens p;` | Không làm package trở thành API import được | Có | Mọi mô-đun tại runtime |
| `opens p to m;` | Không làm package trở thành API import được | Có | Chỉ mô-đun `m` tại runtime |
| `open module x { ... }` | Không tự xuất package cho mã Java thông thường | Có | Mọi package của mô-đun được mở cho reflection |

Một module descriptor có thể vừa xuất package API, vừa mở package nội bộ cho một framework:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.inspector;
}
~~~

Trong ví dụ này:

- Client có thể import các kiểu public trong `com.example.model.api`.
- Mô-đun `com.example.inspector` có thể dùng reflection sâu vào package `com.example.model.internal`.
- Các mô-đun khác không được cấp quyền deep reflection vào package nội bộ đó.

Đừng dùng `exports` chỉ để làm cho `setAccessible(true)` hoạt động. Nếu mục tiêu là truy cập private field hoặc constructor của framework, `opens` mới là chỉ thị đúng.

## 4. Cách reflection sử dụng quyền opens

Giả sử mô-đun A sở hữu class có private field trong package `com.example.model.internal`. Mô-đun B lấy được một đối tượng thuộc class đó rồi dùng reflection.

Khi B gọi:

~~~java
Field field = object.getClass().getDeclaredField("secret");
boolean accessible = field.trySetAccessible();
~~~

JVM kiểm tra quyền truy cập sâu theo ranh giới mô-đun:

- Nếu package được mở cho mô-đun B, `trySetAccessible()` có thể bật quyền truy cập thành viên private.
- Nếu package chưa được mở cho B, `trySetAccessible()` trả về `false` khi không thể bật quyền truy cập.
- Nếu dùng `setAccessible(true)` trong trường hợp bị module system chặn, ứng dụng có thể nhận `InaccessibleObjectException`.

`trySetAccessible()` có từ Java 9 và hữu ích khi ứng dụng muốn xử lý rõ trường hợp package chưa được mở. Nó không tự cấp quyền; quyết định vẫn thuộc module descriptor hoặc cấu hình khởi chạy.

Quyền `opens` được kiểm tra theo mô-đun gọi reflection, không theo tên class hoặc tên JAR. Vì vậy, khi cấu hình framework, cần xác định tên JPMS module thực tế của framework.

## 5. Ví dụ hoàn chỉnh: chỉ mở package internal cho một mô-đun

Ví dụ gồm hai named module:

- `com.example.model` sở hữu dữ liệu và chỉ mở package `internal` cho `com.example.inspector`.
- `com.example.inspector` dùng reflection để đọc private field của đối tượng do API public trả về.

Cấu trúc source:

~~~text
src/
├── com.example.model/
│   ├── module-info.java
│   └── com/example/model/
│       ├── api/
│       │   └── PersonFactory.java
│       └── internal/
│           └── Person.java
└── com.example.inspector/
    ├── module-info.java
    └── com/example/inspector/
        └── Main.java
~~~

**Module descriptor của model `src/com.example.model/module-info.java`:**

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.inspector;
}
~~~

Mô-đun chỉ xuất package API và mở có chọn lọc package internal. Mô-đun inspector không được import trực tiếp class `Person` từ package internal.

**API công khai `PersonFactory.java`:**

~~~java
package com.example.model.api;

import com.example.model.internal.Person;

public final class PersonFactory {

    private PersonFactory() {
    }

    public static Object create() {
        return new Person("module-private-data");
    }
}
~~~

Factory trả về `Object` để client không cần phụ thuộc vào kiểu triển khai nội bộ. Trong một API thực tế, kiểu trả về có thể là interface hoặc kiểu công khai khác phù hợp với thiết kế.

**Class triển khai nội bộ `Person.java`:**

~~~java
package com.example.model.internal;

public final class Person {

    private final String secret;

    public Person(String secret) {
        this.secret = secret;
    }
}
~~~

Field `secret` là private. Mô-đun inspector không thể đọc field bằng truy cập Java thông thường.

**Module descriptor của inspector `src/com.example.inspector/module-info.java`:**

~~~java
module com.example.inspector {
    requires com.example.model;
}
~~~

Inspector khai báo `requires` vì nó sử dụng API public của model. Chỉ thị `opens` trong descriptor của model không tự tạo quan hệ phụ thuộc này.

**Mã reflection `Main.java`:**

~~~java
package com.example.inspector;

import com.example.model.api.PersonFactory;

import java.lang.reflect.Field;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Object person = PersonFactory.create();

        Field secret = person.getClass().getDeclaredField("secret");

        if (!secret.trySetAccessible()) {
            System.out.println("not-open");
            return;
        }

        System.out.println(secret.get(person));
    }
}
~~~

`getDeclaredField` tìm field được khai báo trực tiếp trên class. `trySetAccessible` yêu cầu JVM cho phép reflection sâu. Vì package `com.example.model.internal` đã mở cho `com.example.inspector`, chương trình có thể đọc giá trị private field.

Biên dịch và chạy bằng JDK 17 trở lên, từ thư mục gốc dự án:

~~~powershell
javac --module-source-path src -d out -m com.example.model,com.example.inspector
java --module-path out -m com.example.inspector/com.example.inspector.Main
~~~

Kết quả stdout:

~~~text
module-private-data
~~~

Có thể kiểm tra tác dụng của `opens` bằng cách bỏ dòng:

~~~java
opens com.example.model.internal to com.example.inspector;
~~~

và giữ nguyên phần còn lại của module descriptor. Khi biên dịch lại rồi chạy, `trySetAccessible()` không thể bật quyền truy cập và chương trình in:

~~~text
not-open
~~~

Đối chiếu hai kết quả cho thấy `exports com.example.model.api` vẫn đủ để client dùng factory, còn việc đọc private field chỉ thành công khi package internal được mở cho đúng mô-đun gọi reflection.

## 6. Khi nào nên dùng qualified opens?

Một số tình huống có thể cần mở package cho reflection:

- Framework ánh xạ object cần đọc hoặc ghi private field.
- Framework dependency injection cần truy cập constructor hoặc member không public.
- Thư viện serialization cần đọc trạng thái nội bộ của object.
- Framework tạo proxy hoặc xử lý metadata dựa trên reflection.
- Công cụ kiểm thử hoặc công cụ nội bộ cần truy cập implementation detail trong một phạm vi được kiểm soát.

Trước khi thêm `opens`, hãy xác định package nào thực sự cần reflection và mô-đun nào gọi reflection. Chỉ mở package chứa các kiểu cần xử lý. Không mở cả package API hoặc toàn mô-đun nếu nhu cầu chỉ giới hạn ở một package nội bộ.

Với framework chạy từ classpath, code của framework thường thuộc unnamed module. Module descriptor không dùng tên giả `ALL-UNNAMED` trong danh sách sau `to`; có thể cấu hình quyền mở lúc khởi chạy bằng tùy chọn `--add-opens` nếu cần hỗ trợ một ứng dụng hoặc thư viện chưa thể sửa module descriptor.

## 7. open module và opens ... to khác nhau thế nào?

Java cho phép khai báo:

~~~java
open module com.example.model {
    exports com.example.model.api;
}
~~~

`open module` mở tất cả package của mô-đun cho deep reflection từ các mô-đun khác tại runtime. Nó không có nghĩa là mọi package đều được xuất để mã Java thông thường import.

So sánh:

- `opens p to m;` chỉ mở một package cho một mô-đun đích.
- `opens p;` mở một package cho mọi mô-đun.
- `open module m { ... }` mở tất cả package cho reflection.

Một module declaration đã có từ khóa `open` không khai báo thêm các chỉ thị `opens` riêng lẻ bên trong. Khi cần kiểm soát quyền truy cập theo package, dùng module thông thường và khai báo qualified opens. Cách này giúp descriptor thể hiện rõ phạm vi quyền reflection.

## 8. Tùy chọn --add-opens khi chạy ứng dụng

Nếu không thể sửa module descriptor của thư viện hoặc mô-đun sở hữu package, launcher của Java có thể thêm quyền mở tại runtime:

~~~powershell
java --add-opens com.example.model/com.example.model.internal=com.example.inspector --module-path out -m com.example.inspector/com.example.inspector.Main
~~~

Cú pháp tổng quát:

~~~text
--add-opens source-module/package=target-module
~~~

Nếu framework nằm trên classpath, target có thể là `ALL-UNNAMED`:

~~~powershell
java --add-opens com.example.model/com.example.model.internal=ALL-UNNAMED --module-path out -m com.example.inspector/com.example.inspector.Main
~~~

`--add-opens` là cấu hình của tiến trình khởi chạy. Nó không sửa module descriptor trong JAR và không thay đổi artifact đã build. Vì vậy:

- Ưu tiên khai báo `opens ... to` trong module descriptor do dự án kiểm soát.
- Dùng `--add-opens` khi cần tích hợp một thành phần bên ngoài hoặc khi chưa thể thay đổi mô-đun sở hữu package.
- Ghi rõ module/package/target trong cấu hình triển khai để có thể kiểm tra và gỡ bỏ khi không còn cần thiết.
- Không thêm quyền mở toàn cục chỉ để che một lỗi reflection chưa xác định nguyên nhân.

## 9. Kiểm tra trạng thái mở ở runtime

API `Module` cung cấp các phương thức để kiểm tra trạng thái export/open:

~~~java
Module modelModule = person.getClass().getModule();
Module inspectorModule = Main.class.getModule();

boolean opened = modelModule.isOpen(
        "com.example.model.internal",
        inspectorModule
);

System.out.println(opened);
~~~

Với cấu hình qualified opens ở ví dụ, kết quả là:

~~~text
true
~~~

`Module.isOpen(packageName, targetModule)` kiểm tra package có mở cho mô-đun đích hay không. Có thể dùng `Module.isExported(packageName, targetModule)` để kiểm tra quyền export. Hai kiểm tra này trả lời hai câu hỏi khác nhau.

Khi cần chẩn đoán reflection, hãy kiểm tra đúng module của class đích và module của caller. Không chỉ nhìn vào tên JAR hoặc tên package vì các tên đó không xác định đầy đủ quyền truy cập JPMS.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `trySetAccessible()` trả về `false` | Package chưa mở cho mô-đun gọi reflection | Thêm qualified `opens package to target.module;` trong descriptor của mô-đun sở hữu package |
| `setAccessible(true)` ném `InaccessibleObjectException` | JVM từ chối deep reflection qua ranh giới mô-đun | Kiểm tra package và caller module; mở đúng package cho đúng target |
| Class public vẫn không import được | Package chưa được xuất bằng `exports` | Xuất package API nếu cần truy cập mã Java thông thường |
| Đã có `opens` nhưng client không biên dịch được | `opens` không cấp quyền import/compile-time access | Thêm `exports` cho API cần dùng; giữ `opens` riêng cho reflection |
| Framework vẫn bị chặn | Mở nhầm tên mô-đun đích hoặc nhầm package | Xác định module name thực tế của framework và package chứa class cần reflection |
| Dùng artifactId trong `opens ... to` | Nhầm tọa độ artifact với tên JPMS module | Dùng module name từ descriptor hoặc `jar --describe-module` |
| Mở cả mô-đun để sửa một lỗi nhỏ | Phạm vi reflection rộng hơn nhu cầu | Dùng `opens package to target.module;` cho package cần thiết |
| Có `open module` và khai báo `opens` riêng | Cú pháp module descriptor không cho kết hợp hai cách này | Chọn open module hoặc module thường với các chỉ thị opens riêng |

## 11. Checklist khi thiết kế

- Xác định chính xác package chứa class/field cần deep reflection.
- Xác định module name của framework hoặc module gọi reflection.
- Giữ package API dùng cho compile-time access trong `exports`.
- Dùng `opens package to target.module;` cho package nội bộ cần reflection có chọn lọc.
- Không nhầm tên module với artifactId, tên project hoặc tên file JAR.
- Giữ `requires` cho dependency mô-đun mà mã nguồn thực sự cần đọc; `opens` không thay thế `requires`.
- Dùng `trySetAccessible()` khi cần xử lý rõ trường hợp không được mở.
- Kiểm thử cả cấu hình đã mở và chưa mở để xác nhận quyền reflection hoạt động đúng.
- Chỉ dùng `open module` khi toàn bộ package thực sự cần mở cho reflection.
- Chỉ dùng `--add-opens` như cấu hình runtime có chủ đích khi không thể điều chỉnh descriptor của mô-đun sở hữu package.

Qualified opens là cách JPMS cấp quyền reflection theo nguyên tắc tối thiểu cần thiết. Khi module descriptor xuất package API riêng và chỉ mở package triển khai cho các framework cần thiết, mô-đun vẫn giữ được ranh giới rõ ràng trong khi hỗ trợ các thư viện dựa trên reflection.
