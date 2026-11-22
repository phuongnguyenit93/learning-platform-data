# Add-reads hoặc add-opens cho test có kiểm soát

Khi kiểm thử ứng dụng dùng Java Platform Module System (JPMS), bộ test có thể cần truy cập nhiều thứ hơn mã production: framework phải khám phá phương thức kiểm thử bằng reflection, test cần đọc API của thư viện test hoặc một phép thử nội bộ cần chạm đến các lớp không export. JPMS sẽ không tự nới lỏng module graph chỉ vì mã chạy trong thư mục test.

Hai tùy chọn thường gặp là **--add-reads** và **--add-opens**. Chúng giải quyết hai vấn đề khác nhau:

- **--add-reads** bổ sung quan hệ readability: một named module được phép đọc một module đích, kể cả unnamed module khi dùng ALL-UNNAMED.
- **--add-opens** mở một package của module nguồn cho deep reflection từ module đích khi chạy.

Mục tiêu khi kiểm thử không phải phá encapsulation của toàn ứng dụng. Hãy dùng các quyền bổ sung chỉ khi test thực sự cần, thu hẹp theo module và package, chỉ áp dụng cho tác vụ test và không chuyển chúng vào cấu hình production.

## 1. Vì sao test JPMS có nhu cầu truy cập đặc biệt?

Một ứng dụng modular có thể được triển khai bằng descriptor:

~~~java
module com.example.billing {
    exports com.example.billing.api;
}
~~~

Ở production, consumer chỉ nên dùng package api. Nhưng khi chạy test có thể xuất hiện ba nhu cầu riêng:

1. Test black-box sử dụng API công khai của com.example.billing từ một module test khác.
2. Test white-box được biên dịch vào module đang kiểm thử để kiểm tra hành vi nội bộ.
3. Test runner hoặc framework phản chiếu vào class/method/field của module được kiểm thử.

Nếu test là một named module độc lập và chỉ gọi API đã export, thường không cần thêm --add-reads hoặc --add-opens: chỉ cần khai báo requires và sử dụng public API như bình thường.

Nếu test được patch vào module production hoặc framework cần reflection sâu, việc nới lỏng quyền có mục tiêu đôi khi là cần thiết.

## 2. Hiểu requires, exports, opens và readability

Mỗi quyền phục vụ một mục tiêu:

| Cơ chế | Ý nghĩa |
| --- | --- |
| requires m | Khai báo dependency tĩnh, làm cho module hiện tại đọc m. |
| exports p | Cho phép truy cập kiểu public trong package p theo quy tắc JPMS. |
| opens p | Cho phép deep reflection vào package p tại runtime. |
| --add-reads a=b | Bổ sung quan hệ a đọc b trong cấu hình công cụ hoặc runtime. |
| --add-exports a/p=b | Bổ sung export package p của a cho b. |
| --add-opens a/p=b | Mở package p của a cho deep reflection từ b tại runtime. |

Không thể dùng một tùy chọn để thay thế tất cả:

- Có readability chưa chắc truy cập được kiểu public trong package không export.
- Package được export chưa chắc cho phép truy cập private field bằng reflection.
- Package được open không tự bổ sung quan hệ readability hoặc biến package thành public API để import khi biên dịch.
- --add-reads không mở package để framework gọi setAccessible(true).

Một lỗi khác nhau cần một cơ chế xử lý khác nhau.

## 3. Cú pháp --add-reads

Cú pháp tổng quát:

~~~text
--add-reads SOURCE_MODULE=TARGET_MODULE
~~~

Có thể chỉ định nhiều module đích bằng danh sách ngăn cách bằng dấu phẩy, tùy công cụ hỗ trợ. Quan hệ có hướng: SOURCE_MODULE được phép đọc TARGET_MODULE.

Ví dụ:

~~~bash
java --module-path mods \
    --add-reads com.example.billing=com.example.testing.tools \
    -m com.example.billing/com.example.billing.Main
~~~

Trong ví dụ, com.example.billing được bổ sung quan hệ đọc com.example.testing.tools. Điều đó **không** có nghĩa com.example.testing.tools đọc com.example.billing; muốn chiều ngược lại phải có quan hệ readability riêng.

Quan hệ đọc cho phép tham chiếu giữa các module theo quy tắc JPMS, nhưng package của target vẫn phải export thích hợp để mã nguồn khác truy cập kiểu public.

## 4. ALL-UNNAMED dùng khi dependency nằm trên classpath

Một JAR nằm trên classpath thuộc unnamed module của class loader tương ứng. Nó không có module name để ghi trong requires của named module.

Khi các test class được patch vào một named module nhưng cần dùng thư viện test trên classpath, có thể bổ sung quan hệ:

~~~bash
--add-reads com.example.billing=ALL-UNNAMED
~~~

Ý nghĩa: module com.example.billing có thể đọc unnamed modules trong cấu hình hiện hành. Đây là tình huống thường gặp khi JUnit hoặc thư viện mocking được cung cấp qua test classpath thay vì module path.

Tùy chọn này không thay đổi vị trí của thư viện và không biến JAR trên classpath thành một named module. Nếu named test module cần một thư viện đã có module name trên module path, ưu tiên requires trong descriptor test khi có thể.

ALL-UNNAMED có phạm vi rộng hơn một named module cụ thể. Vì thế chỉ đặt nó ở tác vụ test thực sự cần đọc thư viện classpath.

## 5. Cú pháp --add-opens

Cú pháp tổng quát:

~~~text
--add-opens SOURCE_MODULE/PACKAGE=TARGET_MODULE
~~~

Ví dụ framework test được đóng gói thành named module com.example.test.engine và cần reflection sâu vào package com.example.billing.internal:

~~~bash
java --module-path mods \
    --add-opens com.example.billing/com.example.billing.internal=com.example.test.engine \
    -m com.example.test.launcher/com.example.test.launcher.Main
~~~

Tên module trong lệnh trên là ví dụ minh họa; phải thay bằng module name thực tế của test engine, launcher và module ứng dụng.

Tùy chọn --add-opens làm package có thể được deep reflection từ module đích tại runtime. Nó không cấp quyền mở mọi package khác của module nguồn.

Nếu test engine nằm trên classpath, thay module đích bằng ALL-UNNAMED:

~~~bash
--add-opens com.example.billing/com.example.billing.internal=ALL-UNNAMED
~~~

Chỉ mở đúng package mà test runner thực sự cần. Không nên mở cả java.base hoặc hàng chục package nội bộ của ứng dụng khi chưa có lỗi và lý do cụ thể.

## 6. Vì sao JUnit hoặc framework test cần opens?

Framework test thường khám phá phương thức mang annotation và gọi chúng bằng reflection. Một phương thức test có thể package-private hoặc có constructor không public; việc gọi từ một module khác chịu quy tắc truy cập của JPMS.

Ví dụ:

~~~java
package com.example.billing.test;

import org.junit.jupiter.api.Test;

class InvoiceCalculatorTest {
    @Test
    void addsTax() {
        // Assertions của test.
    }
}
~~~

Nếu class test được patch vào named module com.example.billing, module chứa framework có thể cần quyền reflection vào package com.example.billing.test để tạo instance và gọi method.

Khi test engine là named module, nên mở package cho đúng module cần reflective access. Khi framework trên classpath, có thể dùng ALL-UNNAMED. Tên module cần mở cho phụ thuộc vào phiên bản, cách đóng gói và launcher đang chạy; hãy lấy từ lỗi thực tế hoặc tài liệu của test framework, không đoán từ tên JAR.

Không phải mọi test đều cần opens. Ví dụ một test chỉ gọi method public được export có thể chạy mà không yêu cầu deep reflection vào private member, tùy cách test runner hoạt động.

## 7. Test black-box với module riêng

Cách kiểm thử tốt cho hợp đồng công khai là đặt test trong một named module riêng:

~~~text
src/
├── com.example.billing/
│   ├── module-info.java
│   └── com/example/billing/api/InvoiceService.java
└── com.example.billing.tests/
    ├── module-info.java
    └── com/example/billing/tests/ApiContractTest.java
~~~

Module production:

~~~java
module com.example.billing {
    exports com.example.billing.api;
}
~~~

Module test:

~~~java
module com.example.billing.tests {
    requires com.example.billing;
}
~~~

Test có thể sử dụng những kiểu public thuộc package api. Module test không tự đọc được package internal vì module production không export package đó.

Ưu điểm là test phản ánh đúng khả năng dùng thư viện từ một consumer bên ngoài. Nếu API cần một package hoặc type không được export, lỗi biên dịch sẽ giúp phát hiện hợp đồng chưa nhất quán.

Với loại test này, đừng thêm --add-exports hoặc --add-opens chỉ để làm test pass. Nếu test không dùng được API công khai, hãy xem lại thiết kế API hoặc cách test được tổ chức.

## 8. Test white-box với --patch-module

Một số test cần nằm trong cùng module với code production để kiểm tra package-private class hoặc hành vi nội bộ. JPMS hỗ trợ --patch-module để thêm class/resources vào một named module trong lúc biên dịch hoặc chạy.

Ví dụ:

~~~text
src/main/java/com/example/billing/internal/TaxTable.java
src/test/java/com/example/billing/internal/TaxTableTest.java
~~~

Khi test được patch vào com.example.billing, về mặt module system, các test class đó thuộc module com.example.billing chứ không hình thành một module test độc lập.

Cấu hình biên dịch minh họa:

~~~bash
javac --module-path mods \
    --patch-module com.example.billing=src/test/java \
    --add-reads com.example.billing=ALL-UNNAMED \
    --class-path libs/test-api.jar \
    -d out/test \
    src/test/java/com/example/billing/internal/TaxTableTest.java
~~~

Ở đây:

- --patch-module chỉ ra nguồn test được biên dịch như phần bổ sung của module com.example.billing.
- --add-reads bổ sung quan hệ đọc tới thư viện test ở classpath.
- --class-path cung cấp thư viện test cho compiler.
- out/test chứa class test sau khi biên dịch.

Ví dụ cần các artifact thực tế đã được biên dịch vào mods và các thư viện tương ứng trong libs. Cách biên dịch được điều chỉnh theo cấu trúc và plugin build của dự án.

--patch-module **không phải** là một cách mở package cho framework bên ngoài. Test runner vẫn có thể cần --add-opens khi gọi test method bằng reflection.

## 9. Test runtime có thể cần cả ba cấu hình

Với test white-box được patch vào module production và framework chạy trên classpath, quá trình test có thể cần:

~~~text
--patch-module com.example.billing=out/test
--add-reads com.example.billing=ALL-UNNAMED
--add-opens com.example.billing/com.example.billing.internal=ALL-UNNAMED
~~~

Ý nghĩa khác nhau:

- patch-module đưa class test đã biên dịch vào named module đích.
- add-reads cho test trong module đích đọc thư viện test thuộc unnamed module.
- add-opens cho phép runner trên classpath reflection vào package test hoặc implementation cần thiết.

Nếu test class nằm ở package com.example.billing.tests thay vì internal, hãy mở package thực sự chứa test class cho framework. Không nhất thiết phải mở internal chỉ vì đó là package bị test kiểm tra bằng gọi method package-private.

Những tùy chọn này chỉ nên tồn tại trong tiến trình test. Khi chạy ứng dụng production, không patch class test vào module và không truyền các quyền mở rộng nếu production không cần.

## 10. Ví dụ tối giản: tái hiện nhu cầu --add-opens

Giả sử có một named module com.example.counter:

~~~java
module com.example.counter {
    exports com.example.counter.api;
}
~~~

Một class trong package không export:

~~~java
package com.example.counter.internal;

public final class CounterState {
    private int count = 7;

    private CounterState() {
    }
}
~~~

Một chương trình ReflectionProbe trên classpath muốn tạo instance và đọc private field:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
                Class.forName("com.example.counter.internal.CounterState");

        Constructor<?> constructor = type.getDeclaredConstructor();
        constructor.setAccessible(true);
        Object target = constructor.newInstance();

        Field field = type.getDeclaredField("count");
        field.setAccessible(true);

        System.out.println(field.getInt(target));
    }
}
~~~

Giả sử modular JAR hoặc output của com.example.counter nằm trong mods và ReflectionProbe đã biên dịch nằm trong out/probe. Khi chạy:

~~~bash
java --module-path mods \
    --add-modules com.example.counter \
    -cp out/probe \
    ReflectionProbe
~~~

Lời gọi setAccessible(true) có thể ném InaccessibleObjectException vì package internal chưa open cho unnamed module.

Nếu đây là phép test có kiểm soát, có thể chạy:

~~~bash
java --module-path mods \
    --add-modules com.example.counter \
    --add-opens com.example.counter/com.example.counter.internal=ALL-UNNAMED \
    -cp out/probe \
    ReflectionProbe
~~~

Lúc này package internal được mở cho deep reflection từ chương trình trên classpath. Đây là quyền runtime có phạm vi rõ ràng, không phải thay đổi vĩnh viễn đối với module-info.java.

Trong hệ thống thực, hãy cân nhắc liệu kiểm tra bằng public API có đủ hay không trước khi phụ thuộc vào private field.

## 11. --add-reads không sửa được InaccessibleObjectException

Giả sử module com.example.counter đã readable đối với module test, nhưng test cố gọi:

~~~java
field.setAccessible(true);
~~~

trên field private của package không open.

Thêm:

~~~text
--add-reads com.example.tests=com.example.counter
~~~

chỉ bổ sung quan hệ readability từ tests tới counter. Nó không cấp quyền truy cập field private bằng reflection.

Khi lỗi nêu rõ package không opens cho module caller, cần xem xét opens hoặc --add-opens theo hướng phù hợp. Nếu test không thực sự cần private member, cách tốt hơn là chuyển sang public API.

Ngược lại, --add-opens không giúp compiler import một kiểu public trong package không được export theo quy tắc truy cập thông thường. Khi cần compile-time API access, xem xét exports/--add-exports và readability.

## 12. Cần --add-exports lúc nào?

Bài học tập trung vào --add-reads và --add-opens, nhưng đôi khi lỗi test là package không visible, không phải deep reflection.

Ví dụ test muốn import một public implementation class trong package không export:

~~~java
import com.example.billing.internal.BillingCalculator;
~~~

Nếu test là named module khác, compiler có thể báo package không được export. Việc thêm --add-opens ở runtime không giải quyết lỗi biên dịch đó.

Khi thực sự có nhu cầu tương thích, công cụ có thể dùng:

~~~text
--add-exports com.example.billing/com.example.billing.internal=com.example.billing.tests
~~~

cho đúng module đích ở compile-time và runtime khi cần. Tuy nhiên, nếu loại test đó có thể được viết bằng public API, không nên tạo phụ thuộc vào class internal chỉ vì dễ viết test hơn.

Nếu bạn quản lý code production, thường nên chuyển logic cần kiểm thử thành hợp đồng có chủ đích hoặc dùng test patched trong cùng module thay vì mở rộng API toàn cục.

## 13. Cấu hình Gradle chỉ cho test

Trong Gradle, nên đưa các tùy chọn JVM vào task Test, không đưa vào cấu hình chạy production.

Ví dụ với Groovy DSL:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-reads',
        'com.example.billing=ALL-UNNAMED',
        '--add-opens',
        'com.example.billing/com.example.billing.internal=ALL-UNNAMED'
    )
}
~~~

Đoạn này minh họa vị trí cấu hình. Nó chỉ phù hợp nếu test chạy với module com.example.billing đã được resolve và framework thực sự cần cả hai quyền.

Nếu Gradle hoặc test plugin đã cấu hình module path, patch-module hoặc các quyền tương đương, tránh lặp lại hoặc xung đột. Tùy chọn compiler cho task JavaCompile và tùy chọn JVM của task Test là hai phạm vi khác nhau.

Khi biên dịch test class được patch vào named module, có thể cần cấu hình thêm compiler arguments hoặc module path. Không nên nghĩ rằng jvmArgs ở Test task tự thay đổi cách javac đã biên dịch test.

Nếu chỉ một task integrationTest cần reflection, hãy cấu hình đúng task đó thay vì tasks.withType(Test) cho mọi test.

## 14. Cấu hình Maven cho test runtime

Với Maven Surefire Plugin, các cờ JVM chạy test thường được cấu hình qua argLine, trong trường hợp plugin fork JVM và sử dụng chế độ chạy phù hợp.

Ví dụ minh họa:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>
            --add-reads com.example.billing=ALL-UNNAMED
            --add-opens com.example.billing/com.example.billing.internal=ALL-UNNAMED
        </argLine>
    </configuration>
</plugin>
~~~

Trong cấu hình thực tế, cần giữ lại các JVM arguments khác mà dự án đang dùng, chẳng hạn tham số của coverage agent. Cách cấu hình test module path và patch-module phụ thuộc plugin, phiên bản Java và cấu trúc dự án.

Đối với integration test, Maven Failsafe Plugin có thể được cấu hình riêng để giữ đúng phạm vi kiểm thử cần quyền nới lỏng.

Không chép các tham số test này sang cấu hình java -jar, image container production hoặc script chạy dịch vụ. Mục đích của test-only flags là cho phép kiểm thử khi có lý do xác định, không thay đổi chính sách đóng gói của chương trình sản xuất.

## 15. Khi nào chọn descriptor thay vì flag?

Có hai hướng cấp quyền:

1. **Khai báo quyền trong module-info.java:** phù hợp với hành vi được thiết kế lâu dài, ví dụ một framework production cần deep reflection vào package model.
2. **Bổ sung flag ở test runtime/compiler:** phù hợp với tình huống chỉ test cần quyền, không nên trở thành hợp đồng production.

Ví dụ production cần ORM:

~~~java
module com.example.billing {
    exports com.example.billing.api;
    opens com.example.billing.entity to com.example.persistence;
}
~~~

Đây là một phần thiết kế runtime của ứng dụng, không phải quyền tạm thời của test.

Ngược lại, nếu chỉ bộ test muốn đọc trạng thái private, nên cân nhắc cấu hình test-only:

~~~text
--add-opens com.example.billing/com.example.billing.internal=com.example.tests
~~~

Tên com.example.tests phải là module name thực tế khi test chạy như named module. Nếu framework reflection là một module khác với module chứa test class, đích opens phải là module thực sự thực hiện reflection.

Tránh chỉnh module-info.java production để mở package cho framework test chỉ được dùng trong quá trình build, trừ khi hệ thống có lý do kiến trúc rõ ràng.

## 16. Cách xác định module thực sự thực hiện reflection

Thông báo lỗi thường cho biết module nguồn và module đích:

~~~text
module com.example.billing does not "opens
com.example.billing.internal" to module com.example.test.engine
~~~

Điều đó nghĩa là:

- Package thuộc module com.example.billing.
- Package bị từ chối là com.example.billing.internal.
- Module thực hiện reflection là com.example.test.engine.

Biện pháp test-only tương ứng có thể là:

~~~text
--add-opens com.example.billing/com.example.billing.internal=com.example.test.engine
~~~

Không nên tự động thay đích bằng module của test class nếu stacktrace cho biết framework engine thuộc một module khác.

Nếu thông báo nói "to unnamed module", caller nằm trong unnamed module ở thời điểm lỗi. Khi đó có thể dùng ALL-UNNAMED cho test runtime, nhưng vẫn cần xác minh artifact trên classpath và phạm vi cần mở.

Để xác nhận module name của JAR:

~~~bash
jar --describe-module --file path/to/test-engine.jar
~~~

Cách này hữu ích với automatic modules, nơi tên được suy ra từ manifest hoặc tên file JAR.

## 17. Khi bị "module not found" hoặc "unknown module"

Nếu --add-reads hoặc --add-opens tham chiếu tới module không tồn tại hoặc chưa được resolve, launcher/compiler có thể cảnh báo hoặc báo lỗi tùy tình huống.

Nguyên nhân thường gặp:

- Sai module name của framework hoặc ứng dụng.
- Dependency chưa được đưa vào module path.
- Module nằm trên module path nhưng chưa được resolve vào configuration.
- Cấu hình test dùng classpath nhưng flag lại trỏ tới tên của một module giả định.
- Lệnh build dùng JDK hoặc cấu hình khác với lệnh chạy thủ công.

Đầu tiên hãy xác minh module name thực tế:

~~~bash
jar --describe-module --file libs/framework.jar
~~~

Sau đó xem module resolution ở runtime:

~~~bash
java --show-module-resolution \
    --module-path mods \
    -m com.example.app/com.example.app.Main
~~~

Đặt thêm --add-modules khi có lý do cần đưa một module root vào graph. Đừng dùng --add-reads như cách thay thế việc tìm hoặc resolve một module bị thiếu.

## 18. Một bảng phân biệt lỗi thường gặp

| Triệu chứng | Cơ chế có thể liên quan | Hướng xử lý |
| --- | --- | --- |
| package ... is not visible | Thiếu export hoặc readability | Kiểm tra requires, module path, exports và --add-exports. |
| module ... does not read ... | Thiếu readability | Kiểm tra requires hoặc --add-reads theo đúng chiều. |
| InaccessibleObjectException | Deep reflection vào package chưa open | Kiểm tra opens hoặc --add-opens cho đúng caller. |
| IllegalAccessException khi gọi method | Không đủ quyền reflection/Java visibility | Kiểm tra caller, member, exports/opens và cách gọi. |
| ClassNotFoundException | Không tìm được class | Kiểm tra classpath/module path và class loader. |
| NoClassDefFoundError | Dependency hoặc class cần thiết không được tải | Kiểm tra runtime dependencies và nguyên nhân gốc. |
| Test chạy ở IDE nhưng CLI lỗi | IDE và CLI truyền module flags khác nhau | So sánh compiler args, JVM args và cấu hình module path. |
| Test chỉ pass khi mở toàn bộ package | Test phụ thuộc mạnh vào implementation | Cân nhắc chuyển sang public API hoặc tập trung white-box test trong đúng module. |

Các lỗi này không nên được sửa bằng cách thêm mọi flag cùng lúc. Chọn quyền tối thiểu dựa trên thông báo lỗi và nhu cầu kiểm thử.

## 19. Quan sát trạng thái module mà không mở quyền

Nếu cần xác minh readability và opens trong một chương trình, có thể dùng Module API:

~~~java
Module owner = com.example.billing.api.Invoice.class.getModule();
Module caller = TestDiagnostics.class.getModule();

System.out.println("Caller reads owner: " + caller.canRead(owner));

System.out.println("API exported to caller: " +
        owner.isExported("com.example.billing.api", caller));

System.out.println("Internal open to caller: " +
        owner.isOpen("com.example.billing.internal", caller));
~~~

Các API này cho biết trạng thái quan hệ giữa hai module tại runtime mà không yêu cầu setAccessible(true). Khi phân tích framework, caller phải là module đang thực sự gọi reflection; kết quả kiểm tra với TestDiagnostics.class.getModule() không nhất thiết giống kết quả của một framework trong module khác.

Để kiểm tra quyền mở cho test engine, lấy chính Module của engine nếu có thể, hoặc dựa vào thông báo exception và module graph.

## 20. Giữ quyền test ở phạm vi nhỏ nhất

Một chiến lược kiểm soát nên xác định rõ:

- **Module nguồn:** module đang sở hữu package cần truy cập.
- **Package:** package chứa class hoặc method đang bị từ chối.
- **Module đích:** framework/test runner thực sự cần quyền.
- **Giai đoạn:** chỉ compile test, chạy unit test hay integration test.
- **Lý do:** thiếu readability, cần reflection sâu hay cần type public ở package không export.
- **Điểm gỡ bỏ:** khi nâng cấp framework, refactor test hoặc chuyển sang API public.

Ví dụ bảng ghi chú cấu hình:

| Quyền | Giai đoạn | Lý do |
| --- | --- | --- |
| --add-reads com.example.billing=ALL-UNNAMED | Biên dịch test patched và test runtime khi cần | Test class thuộc named module phải tham chiếu thư viện test trên classpath. |
| --add-opens com.example.billing/com.example.billing.tests=ALL-UNNAMED | Test runtime | Test engine trên classpath cần gọi test method bằng reflection. |
| --add-opens com.example.billing/com.example.billing.internal=com.example.test.engine | Test runtime đặc thù | Engine named module cần kiểm tra private member trong phép thử white-box. |

Đừng thêm những dòng này nếu dự án không có nhu cầu tương ứng. Bảng chỉ minh họa cách ghi lại quyết định; tên module và package phải lấy từ dự án thật.

## 21. Hướng loại bỏ flag tạm thời

Một test-only flag có thể trở thành gánh nặng nếu không được quản lý. Để loại bỏ:

1. Liệt kê các flag JPMS đang được cấu hình riêng cho test.
2. Nhóm theo module nguồn, package và module đích.
3. Xác định test nào thực sự cần từng quyền.
4. Với test black-box, chuyển kiểm tra sang API public thay vì private field.
5. Với white-box, xem xét patch-module hoặc tách API nội bộ có chủ đích khi hợp lý.
6. Nâng cấp framework nếu bản mới hỗ trợ JPMS tốt hơn.
7. Bỏ từng flag sau khi loại bỏ nhu cầu thực tế.
8. Chạy lại unit test, integration test và lệnh chạy production để xác nhận không có phụ thuộc ngầm.

Không cần đưa flag kiểm thử vào production chỉ để thống nhất các môi trường. Hai môi trường có vai trò khác nhau và nên có mức quyền tối thiểu phù hợp.

## 22. Tự kiểm tra

**Tình huống 1:** Test class được patch vào com.example.billing và import một thư viện test trên classpath. Khi compiler báo module không đọc unnamed module, nên xem xét gì?

Trả lời: --add-reads com.example.billing=ALL-UNNAMED ở giai đoạn biên dịch test, cùng classpath chứa thư viện. Nếu runtime cũng cần liên kết tới thư viện đó, phải cấu hình quan hệ đọc phù hợp tại runtime.

**Tình huống 2:** Framework test trên classpath không gọi được method package-private trong module com.example.billing. Thông báo nêu package com.example.billing.tests không open. Flag nào có thể liên quan?

Trả lời: --add-opens com.example.billing/com.example.billing.tests=ALL-UNNAMED ở runtime, với điều kiện framework thực sự cần deep reflection vào package test này.

**Tình huống 3:** Thêm --add-reads có làm setAccessible(true) thành công với private field của module khác không?

Trả lời: không. --add-reads chỉ bổ sung readability. Deep reflection thường cần package được open đúng đích.

**Tình huống 4:** Vì sao một test độc lập chỉ dùng API public được export thường không cần --add-opens?

Trả lời: test có thể dùng requires và các quy tắc truy cập Java thông thường; không cần vượt qua kiểm tra private member.

**Tình huống 5:** Test engine là named module, nhưng dự án dùng ALL-UNNAMED theo thói quen. Có gì cần kiểm tra?

Trả lời: xác minh module thực sự thực hiện reflection. Nếu là named module, nên chỉ định module name đó thay cho ALL-UNNAMED khi có thể.

**Tình huống 6:** Có nên thêm add-opens của test vào lệnh chạy production?

Trả lời: thông thường không. Chỉ cấp quyền nới lỏng trong tác vụ test cần nó, ghi rõ nguyên nhân và bỏ flag khi không còn nhu cầu.

**Tình huống 7:** Compiler báo public class trong package internal không visible. Nên dùng --add-opens để sửa?

Trả lời: không. Đây có thể là vấn đề exports/readability ở compile-time. Nên xem test có thể dùng API public hay cần tổ chức lại thành white-box test; chỉ dùng --add-exports có mục tiêu nếu thực sự cần.
