# Reflection test khi package đóng trong Java Module System

Khi áp dụng Java Platform Module System (JPMS), một package có thể chứa class public nhưng vẫn **không được export** cho module khác. Ngay cả khi package được export, các field hoặc constructor private trong package ấy cũng không tự động được mở cho deep reflection. Vì vậy, một bộ kiểm thử reflection cần xác nhận cả hai phía: **quyền truy cập nào phải bị từ chối** và **quyền nào được mở có chủ đích để framework hoặc module được phép hoạt động**.

Đây là một dạng kiểm thử quan trọng khi chuyển ứng dụng từ classpath sang module path. Test trước đây chạy qua unnamed module hoặc được ghép vào module đang kiểm tra có thể truy cập khác với một consumer thực sự chạy trong named module độc lập. Nếu test chỉ kiểm tra luồng thành công, hoặc test runner tự truyền --add-opens để tránh lỗi, cấu hình bị mở quá rộng có thể tồn tại mà không được phát hiện.

Bài học này hướng dẫn thiết kế test cho package đóng, phân biệt exports với opens, dùng Java reflection API, thiết lập hai module độc lập để kiểm tra biên giới và xử lý các cờ test runner có thể làm sai lệch kết quả.

## 1. Ba lớp quyền truy cập cần phân biệt

Trong JPMS, có ít nhất ba câu hỏi độc lập:

1. **Module có đọc module kia không?** Quan hệ này thường được tạo bởi requires trong module-info.java.
2. **Package có được export tới consumer không?** Chỉ khi có exports phù hợp, mã Java thông thường từ consumer mới có thể truy cập kiểu public trong package đó.
3. **Package có được open cho caller reflection không?** Khi cần truy cập sâu vào private member bằng reflection, package phải được mở cho module của caller theo quy tắc JPMS.

Ví dụ:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Package com.example.domain.api là API public. Package com.example.domain.model, nếu tồn tại, không được export hoặc open bởi descriptor trên.

Điều đó có các hệ quả:

- Một module khác có thể nhìn thấy tên class qua một số API reflection nhưng không có nghĩa nó được gọi constructor, method hoặc truy cập field của class đó.
- Việc Class.getDeclaredField hay Class.getDeclaredMethod trả về metadata không đồng nghĩa có quyền bỏ qua access checks.
- Một package được exports không có nghĩa private field trong package được mở cho deep reflection.
- Ngay cả khi package được opens, việc mã nguồn consumer import class từ package đó vẫn cần exports thích hợp.

Bài kiểm thử cần phân tách những hành vi này thay vì gộp vào một câu khẳng định "reflection hoạt động".

## 2. Mục tiêu của reflection test

Một bộ test có ý nghĩa nên bảo vệ các hợp đồng sau:

| Tình huống | Kỳ vọng |
| --- | --- |
| Consumer đọc được module nhưng package không export | Truy cập Java thông thường bị chặn |
| Consumer tìm được metadata của private field trong package đóng | Không được tự bỏ qua access checks |
| Caller khác module gọi trySetAccessible trên private field | Trả về false nếu package chưa mở cho caller |
| Caller khác module gọi setAccessible(true) khi không đủ quyền | Ném InaccessibleObjectException |
| Package được opens ... to cho đúng consumer | Consumer đó có thể thực hiện deep reflection phù hợp |
| Consumer khác không nằm trong qualified opens | Vẫn bị từ chối deep reflection |
| Package chỉ có exports | Public API truy cập được nhưng private member không mặc nhiên mở |
| Test chỉ chạy trong module sở hữu package | Không dùng kết quả đó để khẳng định module bên ngoài bị chặn |

Test chính xác phải chạy dưới điều kiện module graph, module descriptor và JVM arguments gần với cấu hình thực tế.

## 3. Fixture: một module domain và một module kiểm thử bên ngoài

Để tái hiện ranh giới JPMS, tạo hai named modules thực sự:

~~~text
reflection-demo/
└── src/
    ├── com.example.domain/
    │   ├── module-info.java
    │   └── com/example/domain/model/Customer.java
    └── com.example.probe/
        ├── module-info.java
        └── com/example/probe/ReflectionProbe.java
~~~

Module domain:

~~~java
// src/com.example.domain/module-info.java
module com.example.domain {
}
~~~

Class model:

~~~java
// src/com.example.domain/com/example/domain/model/Customer.java
package com.example.domain.model;

public final class Customer {
    private final String secret = "internal-only";

    public Customer() {
    }

    public String publicName() {
        return "customer";
    }
}
~~~

Module probe:

~~~java
// src/com.example.probe/module-info.java
module com.example.probe {
    requires com.example.domain;
}
~~~

Với descriptor trên, module probe **đọc được** domain nhưng package com.example.domain.model vẫn **đóng** đối với probe: nó chưa được export và chưa được open.

Đây là fixture chủ động để kiểm tra từ chối quyền. Không dùng tên package mặc định và không đặt class probe trong chính module domain vì mục tiêu là kiểm tra một caller khác module.

## 4. Negative test với trySetAccessible

Tạo class kiểm thử chạy từ module probe:

~~~java
package com.example.probe;

import java.lang.reflect.Field;

public final class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        Field secret = type.getDeclaredField("secret");

        boolean accessible = secret.trySetAccessible();

        if (accessible) {
            throw new AssertionError(
                "Closed package unexpectedly allowed deep reflection"
            );
        }

        System.out.println("PASS: deep reflection denied");
    }
}
~~~

Điểm quan trọng:

- Class.forName tìm class theo binary name; tên class được viết dưới dạng string để tránh phải import package không export.
- getDeclaredField lấy metadata field có tên secret.
- trySetAccessible cố bỏ qua Java language access checks bằng quyền reflection hiện có.
- Khi probe là một named module khác và package domain.model chưa open cho probe, trySetAccessible trả về false.
- Nếu trả về true, test thất bại và cần tìm nguyên nhân package đã bị mở bởi descriptor, JVM arguments hoặc một điều chỉnh runtime khác.

Bài test này không cần khởi tạo Customer và không đọc giá trị field. Vì vậy nó cô lập đúng kiểm tra quyền reflection, không phụ thuộc constructor hoặc dữ liệu nghiệp vụ.

Biên dịch hai module:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.example.domain,com.example.probe
~~~

Chạy trên module path:

~~~bash
java --module-path mods \
     -m com.example.probe/com.example.probe.ReflectionProbe
~~~

Khi chưa có quyền open nào được bổ sung, kỳ vọng:

~~~text
PASS: deep reflection denied
~~~

Đây là negative test: thành công nghĩa là quyền không được cấp, chứ không phải framework đã đọc được field.

## 5. Negative test với setAccessible(true)

Nếu muốn kiểm tra rõ loại exception, thay lời gọi trySetAccessible bằng:

~~~java
package com.example.probe;

import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public final class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        Field secret = type.getDeclaredField("secret");

        try {
            secret.setAccessible(true);
            throw new AssertionError(
                "Expected JPMS to reject private-field access"
            );
        } catch (InaccessibleObjectException expected) {
            System.out.println("PASS: inaccessible package rejected");
        }
    }
}
~~~

**setAccessible(true)** yêu cầu nâng quyền reflection, còn **trySetAccessible()** cung cấp kết quả boolean khi không được cấp quyền.

Không nên bắt mọi RuntimeException hoặc Exception rồi cho test pass, bởi như vậy có thể che các lỗi khác như class không tìm thấy, field bị đổi tên hoặc code test sai.

Một bộ test tốt phải tách bước tìm class/field khỏi bước yêu cầu quyền để khi thất bại có thể biết chính xác vấn đề ở tên class, bytecode, module graph hay encapsulation.

## 6. Tại sao Class.forName có thể tìm class dù package đóng?

JPMS phân biệt **khả năng tìm và nạp class** với **quyền truy cập vào kiểu và member**. Trong nhiều cấu hình modular, Class.forName có thể nạp class theo tên dù package chứa class chưa được exports hoặc opens cho caller. Thao tác này tự nó không tạo quyền gọi private member.

Vì vậy, chuỗi thao tác sau không mâu thuẫn:

~~~text
Class.forName("...Customer")          -> có thể thành công
getDeclaredField("secret")           -> có thể thành công
trySetAccessible()                   -> false
setAccessible(true)                  -> InaccessibleObjectException
~~~

Một lỗi phổ biến là nhìn thấy Class<?> được trả về rồi kết luận package đã bị mở. Kết luận đúng chỉ có thể rút ra khi kiểm tra quyền truy cập theo API mà ứng dụng thực sự dùng.

Tính khả dụng của class vẫn phụ thuộc module đã được phân giải, class loader nhìn thấy bytecode và tên class chính xác. Nếu Class.forName thất bại vì ClassNotFoundException, hãy sửa vấn đề loading/resolution trước, không đánh dấu negative reflection test là pass.

## 7. Positive test bằng qualified opens

Sau khi đã xác nhận package đóng từ bên ngoài, thử mở có giới hạn cho đúng module probe.

Sửa descriptor của domain:

~~~java
module com.example.domain {
    opens com.example.domain.model
        to com.example.probe;
}
~~~

Rebuild hai module rồi chạy lại class ReflectionProbe dùng trySetAccessible. Với cấu hình này, việc nâng quyền reflection của module probe đối với package model được cho phép và **trySetAccessible()** có thể trả về true.

Một positive test rõ ràng:

~~~java
package com.example.probe;

import java.lang.reflect.Field;

public final class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        Field field = type.getDeclaredField("secret");

        if (!field.trySetAccessible()) {
            throw new AssertionError(
                "Qualified opens did not permit reflection"
            );
        }

        System.out.println("PASS: qualified opens allows probe");
    }
}
~~~

Khi dùng ví dụ này, hãy thay test negative trước đó hoặc chạy hai biến thể với descriptor tương ứng. Không thể yêu cầu cả "được phép" và "không được phép" cho cùng một caller, cùng package, cùng cấu hình module tại cùng thời điểm.

Qualified opens không export package. Nếu cố import com.example.domain.model.Customer trong source của module probe, javac vẫn có thể báo package không visible vì thiếu exports.

## 8. Kiểm tra consumer thứ hai vẫn bị chặn

Để xác nhận **qualified** opens thực sự giới hạn quyền, tạo một module khác:

~~~text
src/
└── com.example.otherprobe/
    ├── module-info.java
    └── com/example/otherprobe/OtherProbe.java
~~~

Descriptor:

~~~java
module com.example.otherprobe {
    requires com.example.domain;
}
~~~

Dùng cùng ý tưởng kiểm tra:

~~~java
package com.example.otherprobe;

import java.lang.reflect.Field;

public final class OtherProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        Field field = type.getDeclaredField("secret");

        if (field.trySetAccessible()) {
            throw new AssertionError(
                "Other module gained reflection access unexpectedly"
            );
        }

        System.out.println("PASS: other consumer remains blocked");
    }
}
~~~

Khi descriptor domain chỉ ghi **opens com.example.domain.model to com.example.probe**, module otherprobe không có quyền deep reflection đối với package đó.

Biên dịch cả ba module:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.example.domain,com.example.probe,com.example.otherprobe
~~~

Chạy từng module probe độc lập:

~~~bash
java --module-path mods \
     -m com.example.probe/com.example.probe.ReflectionProbe
~~~

~~~bash
java --module-path mods \
     -m com.example.otherprobe/com.example.otherprobe.OtherProbe
~~~

Kết quả mong đợi khi qualified opens đúng là probe được phép, còn otherprobe bị từ chối. Đây là cách thử cả positive và negative case cho cùng chính sách.

## 9. Kiểm tra exports không thay thế opens

Một package có thể được export nhưng vẫn không được mở cho private reflection:

~~~java
module com.example.domain {
    exports com.example.domain.model;
}
~~~

Module probe khai báo requires như trước. Bây giờ code Java trong probe có thể import các public type của package:

~~~java
import com.example.domain.model.Customer;
~~~

Nhưng đối với private field secret, thao tác:

~~~java
Field field = Customer.class.getDeclaredField("secret");
boolean allowed = field.trySetAccessible();
~~~

vẫn bị chặn nếu package chưa được mở cho probe.

Cần phân biệt hai kiểm tra:

| Kiểm tra | Với exports nhưng không opens |
| --- | --- |
| Import Customer là public class | Được phép nếu probe đọc domain |
| Gọi public constructor phù hợp | Có thể được phép theo Java access rules |
| Gọi publicName() là public method | Có thể được phép theo Java access rules |
| Bỏ qua private access cho field secret | Không được phép từ probe |

Điều này cho thấy test chỉ kiểm tra public API không đủ để bảo đảm framework serialization có thể đọc private state.

Ngược lại, khi package chỉ có opens, reflection sâu có thể được phép nhưng source Java của consumer vẫn không thể truy cập package như một API export.

## 10. Kiểm tra MethodHandles.privateLookupIn

Một số framework dùng **MethodHandles** thay vì java.lang.reflect.Field. JPMS vẫn kiểm soát quyền truy cập private qua module openness.

Ví dụ:

~~~java
package com.example.probe;

import java.lang.invoke.MethodHandles;

public final class LookupProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        try {
            MethodHandles.privateLookupIn(
                type,
                MethodHandles.lookup()
            );

            throw new AssertionError(
                "Expected privateLookupIn to be rejected"
            );
        } catch (IllegalAccessException expected) {
            System.out.println("PASS: privateLookupIn denied");
        }
    }
}
~~~

Khi package domain.model đóng với module probe, **privateLookupIn** không thể cấp lookup quyền private. Khi mở package cho probe và caller có quyền lookup phù hợp, thao tác có thể thành công.

Cần lưu ý MethodHandles có các điều kiện riêng về lookup modes, module readability và loại lookup được dùng. Do đó, khi gặp IllegalAccessException, hãy kiểm tra cả package opens và lookup object thực tế; không mặc định mọi lỗi MethodHandles đều do thiếu opens.

Nếu framework production sử dụng MethodHandles, nên có ít nhất một integration test qua chính framework đó, không chỉ test Field.setAccessible.

## 11. Module API giúp giải thích kết quả test

Trong code test, có thể kiểm tra module của class:

~~~java
Class<?> type =
    Class.forName("com.example.domain.model.Customer");

Module domain = type.getModule();
Module caller = ReflectionProbe.class.getModule();

System.out.println("Domain: " + domain.getName());
System.out.println("Caller: " + caller.getName());
System.out.println("Readable: " + caller.canRead(domain));
System.out.println(
    "Exported: " +
    domain.isExported("com.example.domain.model", caller)
);
System.out.println(
    "Opened: " +
    domain.isOpen("com.example.domain.model", caller)
);
~~~

Khi package không export/open, domain.isExported và domain.isOpen cho module probe thường trả về false. Sau khi thêm qualified opens, isOpen trở thành true cho module probe nhưng vẫn false cho otherprobe.

Những API này giúp chẩn đoán **quyền runtime hiện tại**. Chúng không nói quyền được tạo từ module-info.java hay từ một cờ launcher. Nếu --add-opens còn được truyền ngoài ý muốn, isOpen có thể trả về true dù descriptor chưa ghi opens.

Để xác nhận chính sách mà artifact dự định cung cấp, đối chiếu Module API với descriptor được đóng gói và JVM arguments của test.

## 12. JVM arguments có thể làm negative test sai

Một test định chứng minh package đóng sẽ mất giá trị nếu launcher đã thêm quyền:

~~~bash
java --add-opens \
  com.example.domain/com.example.domain.model=com.example.probe \
  --module-path mods \
  -m com.example.probe/com.example.probe.ReflectionProbe
~~~

Cờ trên mở package cho probe ở runtime. Negative test dùng trySetAccessible sẽ trả về true và fail theo đúng logic của nó.

Tình huống nguy hiểm là test được viết lỏng lẻo, chỉ kiểm tra "không có exception khi khởi chạy" và vì vậy không phát hiện quyền đã bị mở ngoài dự kiến.

Cần kiểm kê các nơi có thể truyền cờ:

- IDE Run/Debug configuration.
- Maven Surefire, Failsafe và cấu hình argLine.
- Gradle Test, JavaExec hoặc applicationDefaultJvmArgs.
- JDK_JAVA_OPTIONS, JAVA_TOOL_OPTIONS.
- CI scripts, container entrypoint hoặc launch scripts.
- Agent và launcher wrapper có thể thêm tùy chọn module.

Một test xác minh encapsulation nên có một chế độ chạy **không có cờ --add-opens/--add-exports liên quan** để kiểm tra ranh giới mặc định.

## 13. Nguy cơ khi test được patch vào module đang kiểm tra

Một số build tool chạy test modular bằng cách dùng **--patch-module** để đưa test class vào module chính.

Ví dụ khái quát:

~~~bash
--patch-module com.example.domain=target/test-classes
~~~

Khi test class được định nghĩa là một phần của chính module domain, nó không còn là một consumer khác module đối với domain. Module có quyền truy cập nội bộ của chính nó, do đó test có thể truy cập những thành phần mà một library bên ngoài sẽ bị chặn.

Điều này phù hợp với unit test kiểm tra implementation nội bộ, nhưng **không thích hợp làm bằng chứng duy nhất** rằng encapsulation đã chặn consumer bên ngoài.

Để test chính sách module boundary:

1. Dùng một named module kiểm thử riêng.
2. Cho module kiểm thử requires module production nếu cần đọc nó.
3. Không patch test class vào module domain trong bài kiểm tra ranh giới.
4. Khởi chạy test bằng module path theo cấu hình xác định.
5. Kiểm tra module thực tế của test class bằng getModule().getName().

Ví dụ kiểm tra:

~~~java
System.out.println(ReflectionProbe.class.getModule().getName());
~~~

Kết quả phải là **com.example.probe** trong fixture ở trên. Nếu in **com.example.domain**, bạn đang chạy test trong module sở hữu package, không phải consumer bên ngoài.

## 14. Tích hợp với JUnit và Maven

Một dự án thực tế thường dùng JUnit 5 và Maven. Có thể tổ chức một module test integration riêng, nhưng cần kiểm tra cách Maven Surefire hoặc Failsafe đặt test classes lên module path, dùng --patch-module hay truyền thêm --add-opens.

Mục tiêu cấu hình:

- Module chứa domain được build như modular JAR đúng descriptor.
- Integration test được chạy trong một module khác domain nếu muốn kiểm tra boundary.
- Test runtime không tự mở package đang được xác minh trong negative case.
- JUnit engine và test launcher có quyền truy cập cần thiết để chạy test, nhưng quyền đó không nên vô tình mở domain.model tới test module.
- Các assertion kiểm tra rõ false/true hoặc đúng exception, thay vì chỉ kiểm tra tiến trình không crash.

Một mẫu JUnit test đơn giản trong module consumer:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Field;
import org.junit.jupiter.api.Test;

final class DomainReflectionTest {
    @Test
    void privateFieldIsNotOpenToConsumer() throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        Field field = type.getDeclaredField("secret");

        assertFalse(field.trySetAccessible());
    }
}
~~~

Đây là ví dụ về assertion. Để chạy như module test thực sự, descriptor của test module phải khai báo dependency tới module domain và các module JUnit tương ứng với version đang dùng; Maven/Gradle phải cấu hình module path và test launcher thích hợp.

Không nên mặc định tên module của mọi JUnit artifact là giống nhau trên mọi phiên bản. Kiểm tra tên thực tế bằng **jar --describe-module** hoặc tài liệu tương ứng của toolchain.

Nếu Surefire tự thêm --add-opens để chạy test, cần phân biệt quyền mà JUnit engine cần với quyền mà bài test đang xác minh. Có thể dùng một Java main probe nhỏ như các ví dụ đầu bài để tách kiểm tra encapsulation khỏi sự phức tạp của test runner.

## 15. Tích hợp với Gradle

Trong Gradle, cách đưa test lên module path tùy cấu hình source set, modularity inference và plugin đang dùng.

Ví dụ có thể có JVM args trên Test task:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-opens',
        'com.example.domain/com.example.domain.model=ALL-UNNAMED'
    )
}
~~~

Cấu hình này có thể cần cho một số framework test cũ, nhưng nó cũng làm thay đổi quyền mà test quan sát được. Với bài test xác minh package đóng, cần tách cấu hình kiểm tra boundary khỏi các test vốn phải mở package để hoạt động.

Có thể tạo một task JavaExec chạy module probe bằng lệnh **java --module-path ... -m ...**, hoặc một integration-test task riêng không truyền cờ mở package được kiểm tra.

Điều quan trọng không phải tên task mà là **module identity thực tế của caller** và **các JVM arguments cuối cùng**. Hãy in caller.getModule().getName() khi điều tra.

## 16. Phân biệt InaccessibleObjectException và IllegalAccessException

Các API phản ánh loại lỗi khác nhau:

| Thao tác | Kết quả khi bị chặn |
| --- | --- |
| Field.trySetAccessible() | Thường trả về false |
| Field.setAccessible(true) | InaccessibleObjectException khi không thể bật accessible flag vì JPMS |
| Field.get(instance) khi không có quyền | IllegalAccessException |
| Constructor.newInstance(...) khi không có quyền | IllegalAccessException hoặc lỗi truy cập liên quan |
| MethodHandles.privateLookupIn(...) | IllegalAccessException nếu điều kiện lookup/module access không đáp ứng |

Không nên dùng một catch(Exception) rộng để cho tất cả test đi qua. Nếu code bị ClassNotFoundException, NoSuchFieldException hoặc lỗi khởi tạo bất ngờ, đó không phải bằng chứng encapsulation đang hoạt động chính xác.

Khi test cần chứng minh một đường truy cập bị từ chối, nên assert chính xác exception hoặc giá trị trả về của thao tác mà production thực sự sử dụng.

## 17. Kiểm thử reflection có kiểm soát thay vì mở toàn bộ module

Nếu framework chỉ cần truy cập một package model, cấu hình nên giới hạn package và consumer:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.model
        to com.example.json;
}
~~~

Tránh ngay lập tức thay bằng:

~~~java
open module com.example.domain {
    exports com.example.domain.api;
}
~~~

**open module** mở mọi package của module cho deep reflection. Điều đó có thể làm hỏng các negative test bảo vệ package khác và làm suy yếu ranh giới mà ứng dụng muốn duy trì.

Bộ kiểm thử phù hợp có thể có hai module consumer:

- Module **com.example.json** được phép reflection vào domain.model.
- Module **com.example.otherprobe** không được phép reflection vào domain.model.

Với các package nội bộ khác của domain, cả hai consumer vẫn phải bị chặn nếu descriptor không chủ động mở.

Test dương và âm cùng tồn tại là cách xác nhận đúng phạm vi qualified opens, thay vì chỉ xác nhận framework có thể hoạt động.

## 18. Reflection test với library trên classpath

Một legacy library nằm trên classpath thuộc unnamed module của class loader tương ứng. Nếu muốn framework trên classpath deep reflection vào package của named module, cách mở quyền tạm có thể là:

~~~bash
--add-opens com.example.domain/com.example.domain.model=ALL-UNNAMED
~~~

Giá trị ALL-UNNAMED không phải tên module có thể viết trong qualified opens của module-info.java. Nó là đích đặc biệt của tùy chọn dòng lệnh, đại diện cho các unnamed modules.

Vì vậy, khi đánh giá migration:

- Test với framework trên classpath phải phản ánh quyền dành cho unnamed module.
- Test với framework đã được chuyển thành named module phải phản ánh quyền dành cho tên module cụ thể đó.
- Nếu chuyển framework lên module path làm thay đổi tên hoặc module identity, cần cập nhật các qualified opens và test tương ứng.
- Không suy luận từ test classpath rằng cùng một đường reflection sẽ hoạt động trong named-module runtime.

Nếu library cũ chưa hỗ trợ JPMS và cần cờ tương thích, hãy ghi lại cờ cùng module nguồn, package, consumer và điều kiện loại bỏ. Đừng dùng test đã bật ALL-UNNAMED làm bằng chứng package đóng chặt.

## 19. Công cụ quan sát và chẩn đoán

Có thể xem descriptor của modular JAR:

~~~bash
jar --describe-module --file mods/com.example.domain.jar
~~~

Nếu test dùng exploded modules, hãy kiểm tra module-info.class tồn tại trong output của module:

~~~text
mods/com.example.domain/module-info.class
mods/com.example.probe/module-info.class
~~~

Có thể quan sát quá trình phân giải:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.example.probe/com.example.probe.ReflectionProbe
~~~

Khi nghi ngờ class nạp sai JAR hoặc sai loader:

~~~bash
java -Xlog:class+load=info \
     --module-path mods \
     -m com.example.probe/com.example.probe.ReflectionProbe
~~~

Trong test, in module identity:

~~~java
Module testModule =
    ReflectionProbe.class.getModule();

Module domainModule =
    Class.forName(
        "com.example.domain.model.Customer"
    ).getModule();

System.out.println("Test module: " + testModule.getName());
System.out.println("Domain module: " + domainModule.getName());
System.out.println(
    "Domain opened to test: " +
    domainModule.isOpen(
        "com.example.domain.model",
        testModule
    )
);
~~~

Nếu test thất bại, hãy xác định module name, source artifact, JVM arguments, descriptor và API reflection đã được gọi. Đó là các bằng chứng tối thiểu để tách lỗi permission khỏi lỗi class loading.

## 20. Những sai lầm thường gặp

**Dùng test trong cùng module để chứng minh package đóng.** Code cùng module được phép truy cập nội bộ của module mình; phải dùng caller ở một named module khác.

**Chỉ dùng Class.forName và kết luận package open.** Tìm được Class không chứng minh deep reflection được cấp quyền.

**Nhầm exports với opens.** Export public API không cho phép đọc private field; open phục vụ reflection nhưng không thay thế exports cho source import thông thường.

**Catch mọi exception và cho test pass.** Lỗi classpath, field name hoặc test setup có thể bị che.

**Giữ --add-opens trong test runtime.** Negative test sẽ chạy với chính quyền mà nó được thiết kế để bác bỏ.

**Patch test vào module production.** Caller module thay đổi; quyền kiểm thử không phản ánh consumer thực tế.

**Kiểm thử một module duy nhất sau qualified opens.** Chưa chứng minh các module khác vẫn bị chặn.

**Giữ bản JAR cũ khi sửa descriptor.** Source module-info.java đã thay đổi nhưng runtime vẫn sử dụng module-info.class cũ.

**Chỉ chạy IDE classpath test.** Kết quả có thể khác khi production dùng named modules và module path.

**Xem opens như sandbox bảo mật.** JPMS mạnh về encapsulation và ranh giới API, nhưng không phải cơ chế cô lập mã không tin cậy thành sandbox an toàn.

## 21. Quy trình kiểm thử đề xuất

1. Tạo fixture domain module với package chứa private field.
2. Tạo probe module riêng có requires tới domain.
3. Kiểm tra probe thực sự chạy dưới đúng tên module bằng Class.getModule().
4. Khi package đóng, xác nhận trySetAccessible false và setAccessible(true) bị từ chối.
5. Khi chỉ exports, kiểm tra public API hợp lệ nhưng private reflection vẫn bị chặn.
6. Khi qualified opens tới probe, xác nhận positive reflection pass.
7. Tạo otherprobe và xác nhận qualified opens không cấp quyền cho module không được liệt kê.
8. Nếu production dùng MethodHandles, kiểm tra privateLookupIn tương ứng.
9. Nếu production dùng framework serialization/injection, chạy integration test kích hoạt thật đường reflection đó.
10. Xem lại JVM args và test runner để chắc chắn không vô tình mở package trong negative case.
11. Kiểm tra module-info.class của artifact và dùng --show-module-resolution khi cần.
12. Chạy test với JDK và module path phù hợp môi trường triển khai.

**Reflection test khi package đóng** không chỉ kiểm tra một lời gọi setAccessible có ném exception hay không. Nó xác minh chính sách module: consumer nào được phép dùng public API, consumer nào có thể deep reflection và consumer nào phải bị chặn. Một test fixture gồm các named modules độc lập, negative/positive assertions rõ ràng và launcher không có ngoại lệ ngầm là nền tảng đáng tin cậy để bảo vệ encapsulation khi ứng dụng Java được modular hóa.