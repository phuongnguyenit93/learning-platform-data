# Cấu hình --add-opens cho deep reflection đúng module và package

## 1. Khi nào cần --add-opens?

Java module system kiểm soát package nào một module cho module khác truy cập. Với code thông thường, một package cần được export để module khác truy cập các kiểu public. Với deep reflection, chẳng hạn đọc hoặc thay đổi private field bằng Reflection API, package cần được mở (open) cho module thực hiện thao tác đó.

Khi thư viện cần deep reflection vào một package chưa được mở, ứng dụng có thể gặp `InaccessibleObjectException`. Tùy chọn JVM `--add-opens` cho phép mở một package cụ thể của module nguồn tới một hoặc nhiều module đích trong lúc chạy.

`--add-opens` hữu ích khi:

- Một framework hoặc thư viện cần đọc private field để ánh xạ object.
- Một thư viện serialization cần deep reflection vào package của ứng dụng.
- Một dependency cũ cần truy cập package của JDK mà chưa có bản nâng cấp tương thích.
- Ứng dụng đã xác định rõ package và module caller cần được cấp quyền tạm thời.

`--add-opens` thay đổi ranh giới truy cập của một tiến trình JVM. Nó không sửa thư viện và không biến package nội bộ thành API ổn định. Ưu tiên nâng cấp hoặc thay dependency để loại bỏ nhu cầu truy cập sâu khi có thể.

Mục tiêu bài học:

- Đọc đúng cấu trúc của tùy chọn `--add-opens`.
- Xác định module nguồn, package cần mở và module caller.
- Cấu hình cho named module và code chạy trên classpath.
- Phân biệt `--add-opens` với `opens` trong `module-info.java` và `--add-exports`.
- Đặt tùy chọn ở đúng lệnh khởi chạy JVM.
- Giới hạn phạm vi mở package và xác minh cấu hình đã có hiệu lực.

## 2. Cú pháp của --add-opens

Cú pháp tổng quát:

~~~text
--add-opens source-module/package=target-module(,target-module)*
~~~

Ý nghĩa từng thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `source-module` | Module sở hữu package cần mở. |
| `package` | Tên package cần mở, viết bằng dấu chấm. |
| `target-module` | Module cần được phép deep reflection vào package đó. |
| `ALL-UNNAMED` | Tất cả unnamed modules, thường là code được nạp từ classpath. |

Ví dụ:

~~~bash
java --add-opens java.base/java.lang=com.example.mapper -jar app.jar
~~~

Đọc từ trái sang phải:

- `java.base` là module chứa package nguồn.
- `java.lang` là package cần mở.
- `com.example.mapper` là named module được cấp quyền.
- JVM đang chạy ứng dụng với cấu hình mở package đó cho module đích.

Cấu trúc này có hướng rõ ràng: module nguồn/package ở bên trái dấu `=`, module nhận quyền ở bên phải. Không đảo vị trí hai module.

Một tùy chọn có thể mở cùng package cho nhiều target module bằng cách liệt kê tên module, phân cách bằng dấu phẩy. Chỉ liệt kê các caller thực sự cần quyền.

## 3. Xác định đúng module nguồn và package

Không nên đoán module chỉ từ tên class. Hãy đọc exception message và xác định module chứa class/package bị truy cập.

Ví dụ lỗi:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private final byte[] java.lang.String.value accessible:
module java.base does not "opens java.lang"
to unnamed module @4a54c0de
~~~

Từ message này:

- Module nguồn là `java.base`.
- Package nguồn là `java.lang`.
- Caller thuộc `unnamed module`.
- Vì vậy, nếu cần mở tạm thời cho code trên classpath, target có thể là `ALL-UNNAMED`.

Lệnh tương ứng:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Đây chỉ là ví dụ minh họa cách đọc message và cú pháp. Mở `java.lang` cho mọi unnamed module là quyền rộng; không dùng lệnh này như cấu hình mặc định cho mọi ứng dụng. Trước hết hãy kiểm tra thư viện nào đang truy cập package và liệu có bản nâng cấp loại bỏ nhu cầu đó hay không.

Có thể xem module có trong runtime:

~~~bash
java --list-modules
~~~

Xem các package/module được cung cấp bởi một module:

~~~bash
java --describe-module java.base
~~~

Nếu module đến từ một JAR, có thể kiểm tra descriptor:

~~~bash
jar --describe-module --file path/to/library.jar
~~~

Tên module trong lệnh `--add-opens` phải là tên module thực tế, không nhất thiết là tên file JAR hoặc tên package.

## 4. Xác định đúng module caller

Module đích là module chứa code thực hiện deep reflection, không phải module chứa class bị truy cập.

Caller có thể thuộc hai dạng:

- **Named module:** module có tên được khai báo trong `module-info.java` hoặc được xác định khi đóng gói module.
- **Unnamed module:** code chạy trên classpath, không thuộc named module cụ thể.

Trong exception message, caller trên classpath thường xuất hiện như:

~~~text
to unnamed module @4a54c0de
~~~

Khi cấu hình JVM, dùng `ALL-UNNAMED`:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

`ALL-UNNAMED` áp dụng cho tất cả unnamed modules trong JVM. Nếu nhiều thư viện chạy trên classpath, tất cả đều thuộc phạm vi nhận quyền đối với package đã mở. Vì thế, nếu có thể, hãy đưa dependency cần thiết vào named module hoặc dùng một kiến trúc không cần mở package rộng như vậy.

Nếu message nêu caller là `com.example.mapper`, dùng đúng tên đó:

~~~bash
java --add-opens com.example.model/com.example.model.api=com.example.mapper ...
~~~

Không dùng tên package `com.example.mapper` thay cho module name trừ khi hai tên đó tình cờ giống nhau và module descriptor thực sự xác nhận tên module.

## 5. Ví dụ mở package của một named module

Giả sử ứng dụng có hai module:

- `com.example.model` chứa class `Account`.
- `com.example.mapper` dùng reflection để đọc private field của `Account`.

Module model export package để module mapper có thể biên dịch và sử dụng kiểu public:

~~~java
// module com.example.model
module com.example.model {
    exports com.example.model.api;
}
~~~

Class `Account`:

~~~java
package com.example.model.api;

public class Account {
    private final String token;

    public Account(String token) {
        this.token = token;
    }
}
~~~

Module mapper:

~~~java
// module com.example.mapper
module com.example.mapper {
    requires com.example.model;
}
~~~

Code mapper dùng reflection:

~~~java
package com.example.mapper;

import com.example.model.api.Account;
import java.lang.reflect.Field;

public class AccountInspector {
    public static String readToken(Account account)
            throws ReflectiveOperationException {
        Field field = Account.class.getDeclaredField("token");

        if (!field.trySetAccessible()) {
            throw new IllegalStateException(
                "The model package is not open to this module"
            );
        }

        return (String) field.get(account);
    }
}
~~~

Package `com.example.model.api` đã được export, nên mapper truy cập được class public `Account`. Nhưng `exports` không cấp quyền deep reflection vào private field `token`. Khi chạy, có thể mở package cho đúng module mapper:

~~~bash
java --add-opens com.example.model/com.example.model.api=com.example.mapper --module-path mods --module com.example.mapper/com.example.mapper.Main
~~~

Trong ví dụ:

- `com.example.model` là module nguồn.
- `com.example.model.api` là package cần mở.
- `com.example.mapper` là module caller.
- `--module-path mods` chỉ vị trí các module.
- `--module com.example.mapper/com.example.mapper.Main` chọn module và main class.

Nếu không có `--add-opens` hoặc một chỉ thị `opens` phù hợp, `trySetAccessible()` có thể trả về `false`; nếu dùng `setAccessible(true)`, thao tác có thể ném `InaccessibleObjectException`.

Ví dụ này minh họa cơ chế module trên package của ứng dụng. Với thư viện thực tế, hãy chỉ mở package có trong exception message và chỉ cho module caller thực sự cần quyền.

## 6. Cấu hình cho thư viện chạy trên classpath

Nếu thư viện được nạp từ classpath, caller thường thuộc unnamed module. Ví dụ message:

~~~text
module java.base does not "opens java.lang" to unnamed module
~~~

Cấu hình launcher:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar:lib/*" com.example.Main
~~~

Trên Windows, classpath separator là dấu chấm phẩy:

~~~powershell
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar;lib/*" com.example.Main
~~~

Với lệnh `-jar`, đặt tùy chọn JVM trước `-jar`:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Không đặt tùy chọn JVM sau tên class hoặc sau `-jar` rồi mong launcher hiểu đó là option của JVM. Phần sau tên main class hoặc JAR được chuyển thành tham số ứng dụng.

Lưu ý rằng `ALL-UNNAMED` mở package cho tất cả code trong unnamed modules của tiến trình. Nếu chỉ một dependency cần reflection, quyền này có phạm vi rộng hơn module đích cụ thể. Hãy cân nhắc cập nhật dependency hoặc chuyển nó sang named module nếu phù hợp với kiến trúc ứng dụng.

## 7. --add-opens khác opens trong module-info.java như thế nào?

Nếu bạn sở hữu module nguồn và biết package nào cần mở, có thể khai báo quyền mở ngay trong `module-info.java`.

Mở package cho một named module cụ thể:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.api to com.example.mapper;
}
~~~

Đây là qualified open: package chỉ được mở cho module `com.example.mapper`.

Có thể mở package không giới hạn target bằng:

~~~java
module com.example.model {
    opens com.example.model.api;
}
~~~

Hoặc khai báo toàn bộ module là open module:

~~~java
open module com.example.model {
    // Các requires nếu cần.
}
~~~

Hai cách sau rộng hơn qualified open vì cho phép deep reflection vào nhiều caller hơn. Chỉ dùng khi thiết kế module thực sự yêu cầu.

So sánh:

| Cách cấu hình | Nơi khai báo | Phạm vi |
| --- | --- | --- |
| `--add-opens source/package=target` | Lệnh khởi chạy JVM | Mở package cụ thể trong tiến trình đang chạy. |
| `opens package to target;` | `module-info.java` của module nguồn | Mở package cho module được chỉ định theo descriptor. |
| `opens package;` | `module-info.java` | Mở package cho mọi module. |
| `open module name { ... }` | `module-info.java` | Mở mọi package của module cho deep reflection. |

Nếu sở hữu module và muốn quyền mở là một phần hợp đồng module, qualified `opens` thường thể hiện ý định rõ ràng. Nếu cần cấu hình tạm thời cho một dependency hoặc module JDK mà không thể sửa descriptor, `--add-opens` là lựa chọn runtime.

Không thể sửa `module-info.java` của module `java.base` trong JDK đã cài để thêm một directive `opens` tùy ý; khi cần kiểm tra tương thích tạm thời, launcher option là cơ chế thích hợp hơn.

## 8. Phân biệt --add-opens với --add-exports

Hai tùy chọn giải quyết hai loại quyền truy cập khác nhau:

| Tùy chọn | Cho phép | Không cho phép |
| --- | --- | --- |
| `--add-opens` | Deep reflection vào các thành viên package, gồm private members theo quy tắc reflection. | Không thay thế export để code biên dịch/truy cập trực tiếp kiểu public trong package. |
| `--add-exports` | Truy cập thông thường đến các kiểu public trong package được export. | Không cấp quyền deep reflection vào private members. |

Ví dụ:

~~~bash
# Cho phép deep reflection:
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar

# Cho phép truy cập kiểu public trong package chưa export:
java --add-exports java.base/sun.security.x509=ALL-UNNAMED -jar app.jar
~~~

Nếu exception ghi `does not "opens package"`, điều tra `--add-opens`.

Nếu lỗi ghi `does not export package`, đó là dấu hiệu của quyền export và cần xem xét `--add-exports` hoặc API công khai thay thế.

Không thêm cả hai tùy chọn theo thói quen. Xác định đúng thao tác bị chặn rồi cấp đúng loại quyền.

## 9. --add-opens là tùy chọn runtime

`--add-opens` điều chỉnh quyền truy cập trong JVM đang chạy. Nó không làm cho một package trở thành exported package khi biên dịch source code.

Nếu code cần tham chiếu trực tiếp một kiểu public từ package không export, cần giải quyết bằng API/module configuration phù hợp cho compile-time, chẳng hạn `--add-exports` khi trường hợp sử dụng được chấp nhận.

Với reflection, việc kiểm tra thường diễn ra ở runtime khi framework gọi `trySetAccessible()` hoặc `setAccessible(true)`. Do đó, tùy chọn phải được truyền đến đúng JVM thực sự chạy ứng dụng hoặc test.

Một số nơi cần kiểm tra:

- Lệnh `java` trong script khởi động.
- JVM options của service manager.
- Cấu hình runtime của container.
- JVM forked bởi Maven Surefire hoặc Gradle Test.
- Cấu hình IDE nếu lỗi chỉ xảy ra khi chạy từ IDE.

Đặt option ở JVM build không đảm bảo nó xuất hiện ở JVM test fork hoặc JVM production. Xác minh command line của đúng tiến trình.

## 10. Cấu hình trong Maven và Gradle test

Nếu lỗi chỉ xuất hiện khi chạy test, cần đặt option vào JVM thực thi test.

Với Maven Surefire, có thể thêm vào `argLine`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--add-opens java.base/java.lang=ALL-UNNAMED</argLine>
    </configuration>
</plugin>
~~~

Nếu dự án đã dùng `argLine` cho JaCoCo hoặc agent khác, cần kết hợp các option hiện có thay vì ghi đè chúng.

Với Gradle:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        "--add-opens",
        "java.base/java.lang=ALL-UNNAMED"
    )
}
~~~

Đây là ví dụ cấu hình cho test JVM. Với ứng dụng production, cấu hình phải nằm ở launcher hoặc service runtime thực sự khởi chạy ứng dụng.

Không thêm tùy chọn toàn cục vào mọi test hoặc mọi service nếu chỉ một thư viện cụ thể cần quyền. Ghi lại dependency, package và lý do mở để có thể gỡ bỏ khi nâng cấp.

## 11. Chọn phạm vi mở nhỏ nhất

`--add-opens` cấp quyền theo package, không theo từng class hoặc từng field. Vì vậy, package được mở sẽ cho target module thực hiện deep reflection đối với các lớp trong package theo quy tắc module.

Thứ tự lựa chọn nên là:

1. Một source module cụ thể.
2. Một package cụ thể trong module đó.
3. Một target named module cụ thể.
4. Chỉ dùng `ALL-UNNAMED` khi caller thực sự chạy trên classpath và không thể xác định một named module phù hợp.
5. Không mở toàn bộ module nếu chỉ một package cần reflection.

Ví dụ hẹp:

~~~bash
java --add-opens com.example.model/com.example.model.api=com.example.mapper ...
~~~

Ví dụ rộng hơn:

~~~bash
java --add-opens com.example.model/com.example.model.api=ALL-UNNAMED ...
~~~

Lệnh thứ hai cho tất cả unnamed modules quyền deep reflection vào package đó. Không dùng nó nếu caller là named module và tên module có thể xác định.

Mở package không xác thực danh tính nghiệp vụ của caller và không thay thế authorization ở tầng ứng dụng. Đây là thay đổi quyền truy cập trong JVM, cần được quản lý như một phần cấu hình bảo mật.

## 12. Không dùng --illegal-access thay cho --add-opens

Các hướng dẫn cũ có thể đề nghị:

~~~bash
java --illegal-access=permit -jar app.jar
~~~

Đây là cơ chế chuyển tiếp trong các phiên bản Java trước khi strong encapsulation trở thành mặc định. Java 16 đã bật strong encapsulation mặc định cho phần lớn JDK internals. Từ Java 17, theo JEP 403, `--illegal-access` không còn mở lại các package nội bộ; option này không phải cách sửa lỗi cho JDK hiện đại.

Khi cần một ngoại lệ tạm thời, hãy dùng `--add-opens` cho đúng module/package/caller và ghi nhận lý do. Sau đó nâng cấp hoặc thay dependency để có thể bỏ option.

Không thêm `--add-opens` hàng loạt để che tất cả lỗi reflection. Mỗi package mở thêm đều làm rộng bề mặt truy cập trong tiến trình.

## 13. Quy trình xác định và xác minh option

Khi gặp `InaccessibleObjectException`, làm theo quy trình:

1. Lấy đầy đủ exception message và stack trace.
2. Đọc module nguồn và package trong phần `does not "opens ..."`.
3. Xác định caller module sau từ `to ...`.
4. Tìm frame của framework hoặc thư viện thực hiện reflection.
5. Xác định artifact/version và kiểm tra bản nâng cấp.
6. Nếu vẫn cần mở package, viết option theo dạng `source-module/package=target-module`.
7. Đặt option vào đúng JVM chạy ứng dụng hoặc test.
8. Khởi động lại tiến trình; thay đổi command line không áp dụng hồi tố cho JVM đã chạy.
9. Chạy lại đúng luồng gây lỗi.
10. Kiểm tra log và xác nhận lỗi đã biến mất.
11. Ghi lại option cùng dependency và điều kiện gỡ bỏ.
12. Khi dependency đã được sửa, xóa option và chạy lại test để bảo đảm không còn phụ thuộc.

Có thể xác minh option launcher nhận được bằng cách chạy lại command line đầy đủ trong môi trường tương ứng. Với hệ thống production, kiểm tra cấu hình thực tế của process/container thay vì chỉ kiểm tra file cấu hình nguồn.

## 14. Lỗi thường gặp và cách khắc phục

1. **Đảo module nguồn và module đích:** module sở hữu package phải đứng trước dấu `/`; caller module đứng sau dấu `=`.
2. **Dùng dấu slash sai chỗ:** cú pháp là `source-module/package=target-module`; tên package viết bằng dấu chấm.
3. **Dùng tên package thay cho module name:** xác định module name từ exception hoặc module descriptor.
4. **Dùng `ALL-UNNAMED` cho named module:** target phải là tên module caller nếu caller là named module.
5. **Dùng `--add-exports` cho private reflection:** deep reflection cần `--add-opens`.
6. **Dùng `--add-opens` để sửa compile-time access:** option này áp dụng cho runtime; xem xét export/API phù hợp cho compile-time.
7. **Đặt option sau tên main class hoặc sau `-jar`:** launcher coi phần đó là tham số ứng dụng; đặt JVM option trước điểm chọn main/JAR/module.
8. **Chỉ cấu hình ở build JVM:** test fork hoặc production JVM có thể không nhận option; cấu hình đúng process.
9. **Mở `ALL-UNNAMED` không cần thiết:** quyền được cấp cho mọi unnamed module; ưu tiên target named module cụ thể.
10. **Mở toàn bộ module:** chỉ mở package cần thiết; tránh `open module` nếu không có yêu cầu rõ ràng.
11. **Dựa vào `--illegal-access`:** option cũ không còn mở lại package từ Java 17; dùng API công khai hoặc cấu hình hẹp khi chuyển tiếp.
12. **Không gỡ option sau khi nâng cấp thư viện:** giữ lại cấu hình không còn cần thiết làm tăng quyền truy cập không cần thiết.

## 15. Bài tập thực hành

1. Cho message `module java.base does not "opens java.lang" to unnamed module`; viết option `--add-opens` tương ứng.
2. Cho caller module là `com.example.mapper`, source module là `com.example.model`, package là `com.example.model.api`; viết option đúng.
3. Phân tích từng phần trong cú pháp `--add-opens source-module/package=target-module`.
4. Giải thích vì sao `ALL-UNNAMED` có phạm vi rộng hơn một named module.
5. Viết `module-info.java` dùng qualified `opens package to target;` và so sánh với option runtime.
6. Phân biệt `--add-opens` với `--add-exports` qua hai exception message.
7. Đặt option vào Maven Surefire và Gradle Test JVM.
8. Tìm option thực tế trong command line của một JVM chạy ứng dụng.
9. Thử `trySetAccessible()` trước và sau khi mở package trong một ví dụ module nhỏ.
10. Đề xuất kế hoạch nâng cấp dependency để gỡ bỏ một option `--add-opens` đang dùng.
11. Giải thích vì sao không nên mở toàn bộ package cho `ALL-UNNAMED`.
12. Kiểm tra vì sao `--illegal-access=permit` không phải giải pháp trên Java 17 trở đi.

## Ghi nhớ

`--add-opens` có cú pháp `source-module/package=target-module` và được truyền cho JVM lúc chạy. Module nguồn là nơi chứa package cần mở; target là module thực hiện deep reflection. Nếu caller thuộc classpath, target thường là `ALL-UNNAMED`; nếu caller là named module, dùng đúng module name. `--add-opens` cho phép deep reflection, trong khi `--add-exports` cho phép truy cập thông thường tới kiểu public; hai tùy chọn không thay thế nhau. Nếu sở hữu module nguồn, có thể dùng qualified `opens package to target;` trong `module-info.java`. Chỉ mở package và caller cần thiết, đặt option vào đúng JVM process và xem đây là giải pháp chuyển tiếp khi dependency chưa thể nâng cấp. Trên Java hiện đại, ưu tiên API công khai và thư viện tương thích thay vì dựa vào truy cập JDK internal.

**Tài liệu tham khảo chính thức:**

- [JEP 261 – Module System](https://openjdk.org/jeps/261)
- [JEP 396 – Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396)
- [JEP 403 – Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [Java Launcher – java command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/java.html)
- [Java Language Specification – Module declarations](https://docs.oracle.com/javase/specs/jls/se16/html/jls-7.html#jls-7.7)
- [Java API – AccessibleObject](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java API – InaccessibleObjectException](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html)
