# Kiểm thử rằng module không lộ API ngoài ý muốn

Trong Java Platform Module System (JPMS), **strong encapsulation** không chỉ là việc chia mã nguồn thành các module có tên. Một thiết kế module tốt phải quy định rõ package nào là API công khai, package nào dành riêng cho implementation và framework nào (nếu có) được phép sử dụng deep reflection. Kiểm thử những ranh giới này giúp tránh tình trạng một thay đổi ở **module-info.java**, một bản đóng gói JAR hoặc một tùy chọn khởi chạy vô tình làm lộ những class vốn phải được giữ kín.

Mục tiêu của bài này là xây dựng các phép kiểm thử có thể chạy lại để trả lời ba câu hỏi:

1. **Compile-time:** Một module độc lập có thể import và sử dụng API công khai, nhưng bị từ chối khi import package nội bộ không?
2. **Runtime reflection:** Code ở module khác có bị chặn khi cố truy cập sâu vào field, method hoặc constructor private của module đích không?
3. **Module contract:** Descriptor và cấu hình khởi động có đúng danh sách **exports**, **opens** và ngoại lệ truy cập đã được phê duyệt không?

Chỉ nhìn cấu trúc thư mục hoặc đặt tên package là **internal** chưa đủ. Ranh giới truy cập thực tế được quyết định bởi descriptor, module graph, Java access rules và các quyền runtime có thể được bổ sung.

## 1. Lộ API ngoài ý muốn nghĩa là gì?

Một named module có thể chứa nhiều package, nhưng không phải package nào cũng cần trở thành API cho module khác. Ví dụ:

~~~text
com.acme.order
├── com.acme.order.api
├── com.acme.order.internal
├── com.acme.order.persistence
└── com.acme.order.spi
~~~

Giả sử hợp đồng thiết kế quy định:

- **com.acme.order.api**: API public cho ứng dụng tiêu thụ.
- **com.acme.order.internal**: chi tiết triển khai, không được export hoặc open.
- **com.acme.order.persistence**: entity nội bộ, chỉ được open cho một ORM cụ thể khi thật sự cần reflection.
- **com.acme.order.spi**: hợp đồng mở rộng, có thể export có giới hạn nếu chỉ một module plugin được phép dùng.

Những thay đổi có thể gây lộ API:

~~~java
module com.acme.order {
    exports com.acme.order.api;
    exports com.acme.order.internal; // Lộ package implementation
}
~~~

Hoặc:

~~~java
open module com.acme.order {
    exports com.acme.order.api;
}
~~~

Trong ví dụ thứ hai, toàn bộ package của module được mở cho deep reflection ở runtime; đây là quyền rộng hơn nhiều so với việc chỉ export API công khai.

Một modular JAR vô tình bị đóng gói thành **automatic module** cũng có thể mất ranh giới dự kiến. Automatic module có các quy tắc tương thích rộng, export và open tất cả package của nó. Vì vậy, kiểm thử không chỉ đọc tên package: cần kiểm tra loại module và các quyền thực tế.

## 2. Hiểu chính xác requires, exports và opens

Ba nhóm quy tắc cần phân biệt:

| Cơ chế | Điều gì được cho phép? | Có thể kiểm thử bằng |
|---|---|---|
| **requires** và module readability | Module caller đọc được module đích. | Module graph và **Module.canRead(...)**. |
| **exports** | Module khác truy cập các public type/member trong package theo quy tắc Java. | Compile-time consumer test và **ModuleDescriptor.exports()**. |
| **opens** | Module khác thực hiện deep reflection vào package tại runtime. | **trySetAccessible()**, **Module.isOpen(...)**, **ModuleDescriptor.opens()**. |

Ví dụ một descriptor có ranh giới chặt:

~~~java
module com.acme.order {
    exports com.acme.order.api;
}
~~~

Module khác khai báo:

~~~java
module com.acme.client {
    requires com.acme.order;
}
~~~

Khi đó client có thể dùng public API trong **com.acme.order.api**. Tuy nhiên, client không thể import kiểu public từ **com.acme.order.internal** vì package này không được export.

Việc một class được khai báo **public** không tự động làm nó trở thành API của toàn hệ thống. Public chỉ giải quyết một phần quy tắc Java; JPMS còn kiểm tra ranh giới module.

Ngược lại, nếu module có:

~~~java
module com.acme.order {
    exports com.acme.order.api;
    opens com.acme.order.persistence to com.acme.orm;
}
~~~

Package **persistence** vẫn không được export cho việc import trực tiếp từ mã nguồn, nhưng module **com.acme.orm** có thể thực hiện deep reflection theo quyền được cấp. Đó có thể là ngoại lệ được thiết kế có chủ đích, không phải lộ API ngoài ý muốn.

## 3. Xây dựng module mẫu để kiểm thử encapsulation

Ví dụ sau dùng một module nghiệp vụ và một module kiểm thử độc lập. Điểm quan trọng là kiểm thử phải chạy **bên ngoài module được kiểm tra**.

Cấu trúc thư mục:

~~~text
src/
  com.acme.order/
    module-info.java
    com/acme/order/api/OrderApi.java
    com/acme/order/internal/OrderState.java
tests/
  com.acme.contract.test/
    module-info.java
    com/acme/contract/test/EncapsulationTest.java
negative-src/
  com.acme.contract.negative/
    module-info.java
    com/acme/contract/negative/IllegalImport.java
~~~

Descriptor module nghiệp vụ:

~~~java
// src/com.acme.order/module-info.java
module com.acme.order {
    exports com.acme.order.api;
}
~~~

Class implementation:

~~~java
// src/com.acme.order/com/acme/order/internal/OrderState.java
package com.acme.order.internal;

public final class OrderState {
    private final String secret;

    public OrderState(String secret) {
        this.secret = secret;
    }
}
~~~

Class API:

~~~java
// src/com.acme.order/com/acme/order/api/OrderApi.java
package com.acme.order.api;

import com.acme.order.internal.OrderState;

public final class OrderApi {
    private OrderApi() {
    }

    public static Object sampleState() {
        return new OrderState("INTERNAL-ONLY");
    }
}
~~~

Việc **OrderApi** tạo và sử dụng **OrderState** là hợp lệ: cả hai package thuộc cùng module. Phương thức **sampleState()** cố ý trả về **Object** để module kiểm thử có một instance thật mà không cần import kiểu nội bộ.

Trong thiết kế ứng dụng thực tế, API nên trả về một kiểu hợp đồng ổn định thay vì Object. Ở đây Object chỉ phục vụ việc minh họa giới hạn reflection khi chưa export package implementation.

## 4. Kiểm thử thành công với API được phép công bố

Module kiểm thử bên ngoài:

~~~java
// tests/com.acme.contract.test/module-info.java
module com.acme.contract.test {
    requires com.acme.order;
}
~~~

Một kiểm thử đơn giản:

~~~java
package com.acme.contract.test;

import com.acme.order.api.OrderApi;

public final class EncapsulationTest {
    public static void main(String[] args) throws Exception {
        Object state = OrderApi.sampleState();

        if (state == null) {
            throw new AssertionError("Public API không hoạt động");
        }

        System.out.println("Public API accessible");
    }
}
~~~

Biên dịch module nghiệp vụ:

~~~bash
javac -d mods --module-source-path src -m com.acme.order
~~~

Biên dịch module kiểm thử:

~~~bash
javac -d testmods \
      --module-path mods \
      --module-source-path tests \
      -m com.acme.contract.test
~~~

Chạy trên Linux/macOS:

~~~bash
java --module-path "mods:testmods" \
     -m com.acme.contract.test/com.acme.contract.test.EncapsulationTest
~~~

Trên Windows, module path nhiều thư mục dùng dấu chấm phẩy:

~~~powershell
java --module-path "mods;testmods" -m com.acme.contract.test/com.acme.contract.test.EncapsulationTest
~~~

Đây là **positive test**: API được chủ ý export phải biên dịch và chạy thành công từ một module bên ngoài. Một hệ thống chỉ chạy negative tests mà không có positive test sẽ khó phân biệt encapsulation đúng với cấu hình làm hỏng toàn bộ API.

## 5. Negative compile test: package internal không được import

Kiểm thử mạnh nhất cho quyền truy cập mã nguồn là thực sự dùng **javac** để biên dịch một module tiêu thụ cố import package nội bộ.

Descriptor của module kiểm thử âm tính:

~~~java
// negative-src/com.acme.contract.negative/module-info.java
module com.acme.contract.negative {
    requires com.acme.order;
}
~~~

Class cố dùng implementation:

~~~java
// negative-src/com.acme.contract.negative/com/acme/contract/negative/IllegalImport.java
package com.acme.contract.negative;

import com.acme.order.internal.OrderState;

public final class IllegalImport {
    OrderState state = new OrderState("should-not-compile");
}
~~~

Biên dịch riêng fixture này:

~~~bash
javac -d negative-out \
      --module-path mods \
      --module-source-path negative-src \
      -m com.acme.contract.negative
~~~

Khi module **com.acme.order** chỉ export package **api**, trình biên dịch dự kiến từ chối import **com.acme.order.internal**. Thông báo thường chứa ý rằng package không visible hoặc không được export cho module caller.

Đây là **expected compilation failure**, không phải lỗi bài học. Trong CI, hãy kiểm tra cả hai điều kiện:

1. **javac** thoát với mã khác 0.
2. Diagnostic đúng bản chất **package internal không được export**; không phải lỗi cú pháp, thiếu JDK, thiếu module path hay source file không tồn tại.

Một kiểm thử âm tính không nên được đánh dấu thành công chỉ vì bất kỳ lỗi biên dịch nào xuất hiện. Nếu fixture hỏng cú pháp, phép thử không còn chứng minh được encapsulation của module.

Ví dụ Bash:

~~~bash
if javac -d negative-out --module-path mods \
         --module-source-path negative-src \
         -m com.acme.contract.negative; then
    echo "FAIL: package internal đã trở nên có thể import"
    exit 1
else
    echo "Expected: javac từ chối package internal"
fi
~~~

Trong pipeline thực tế, nên bắt stderr và xác nhận diagnostic phù hợp trước khi chấp nhận negative test.

## 6. Negative runtime test: không mở private field cho caller

Lệnh **javac** kiểm tra khả năng import API, nhưng không đủ để chứng minh module không cho phép deep reflection. Cần một test runtime đặt ở module khác.

Bổ sung vào test class:

~~~java
package com.acme.contract.test;

import com.acme.order.api.OrderApi;
import java.lang.reflect.Field;

public final class EncapsulationTest {
    public static void main(String[] args) throws Exception {
        Object state = OrderApi.sampleState();

        Class<?> internalClass = state.getClass();
        Module owner = internalClass.getModule();
        Module caller = EncapsulationTest.class.getModule();
        String pkg = internalClass.getPackageName();

        if (owner.isExported(pkg, caller)) {
            throw new AssertionError("Internal package đã được export");
        }

        if (owner.isOpen(pkg, caller)) {
            throw new AssertionError("Internal package đã được opens");
        }

        Field secret = internalClass.getDeclaredField("secret");

        if (secret.trySetAccessible()) {
            throw new AssertionError(
                "Caller đã có thể deep-reflect vào field private"
            );
        }

        System.out.println("Encapsulation preserved");
    }
}
~~~

Test này kiểm tra ba lớp tín hiệu:

- **isExported(pkg, caller)**: package có được truy cập như một API runtime cho caller không.
- **isOpen(pkg, caller)**: package có đang mở cho caller thực hiện deep reflection không.
- **trySetAccessible()**: caller có thực sự suppress access checks cho private field được không.

Việc lấy được **Class<?>** hoặc **Field** không đồng nghĩa với quyền truy cập giá trị. Mục tiêu của negative runtime test là xác minh thao tác vượt ranh giới **không được phép**.

**Lưu ý:** Một test đặt bên trong **com.acme.order** sẽ cho kết quả khác, vì code cùng module có quyền truy cập nội bộ rộng hơn code thuộc module ngoài. Hãy bảo đảm test được biên dịch và chạy dưới named module **com.acme.contract.test**.

## 7. Kiểm tra descriptor bằng allowlist

Compile tests kiểm tra một số trường hợp cụ thể. Để tránh bỏ sót các package vô tình được export hoặc open, có thể kiểm tra trực tiếp **ModuleDescriptor** của artifact.

Ví dụ dùng **ModuleFinder**:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;

public final class DescriptorContractTest {
    public static void main(String[] args) {
        ModuleDescriptor d = ModuleFinder
            .of(Path.of("mods"))
            .find("com.acme.order")
            .orElseThrow()
            .descriptor();

        if (d.isAutomatic() || d.isOpen()) {
            throw new AssertionError(
                "Module phải là explicit module không open"
            );
        }

        Set<String> expectedExports = Set.of("com.acme.order.api");

        Set<String> actualExports = d.exports().stream()
            .filter(e -> !e.isQualified())
            .map(ModuleDescriptor.Exports::source)
            .collect(Collectors.toSet());

        if (!expectedExports.equals(actualExports)) {
            throw new AssertionError(
                "Exports không khớp hợp đồng: " + actualExports
            );
        }

        if (d.exports().stream().anyMatch(
                ModuleDescriptor.Exports::isQualified)) {
            throw new AssertionError(
                "Có qualified exports chưa được phê duyệt"
            );
        }

        if (!d.opens().isEmpty()) {
            throw new AssertionError(
                "Module đang mở package cho reflection"
            );
        }

        System.out.println("Module descriptor contract passed");
    }
}
~~~

Đây là ví dụ với chính sách **chỉ một package được export và không package nào được open**. Với module có qualified exports/opens hợp lệ, thay các kiểm tra cấm tuyệt đối bằng allowlist về tên package và danh sách module đích.

Vì **ModuleDescriptor** bất biến và phản ánh metadata của module, việc đọc nó không đòi hỏi nạp các class nghiệp vụ. Có thể kiểm tra trực tiếp JAR sau khi build, thay vì chỉ kiểm tra source descriptor.

### Tại sao phải kiểm tra cả automatic và open module?

Nếu thư viện được đóng gói sai và mất **module-info.class**, JAR đặt trên module path có thể trở thành automatic module. Một automatic module có ngữ nghĩa export/open rộng, ngay cả khi tập directive được tổng hợp khác với các exports bạn viết trong source.

Tương tự, **open module** mở mọi package ở runtime. Bởi vậy, chỉ xem số dòng **opens** không luôn đủ; cần kiểm tra cả **isOpen()** và **isAutomatic()**.

## 8. Qualified exports và qualified opens cần được kiểm thử riêng

Đôi khi hệ thống cần cho một module cụ thể truy cập package không dành cho công chúng:

~~~java
module com.acme.order {
    exports com.acme.order.api;
    exports com.acme.order.spi to com.acme.plugin.host;
    opens com.acme.order.persistence to com.acme.orm;
}
~~~

Trong trường hợp này:

- **api** được export cho mọi module đọc module order.
- **spi** chỉ được export cho **com.acme.plugin.host**.
- **persistence** chỉ được open cho **com.acme.orm**.

Test descriptor cần so sánh cả package và target:

~~~java
for (ModuleDescriptor.Exports e : d.exports()) {
    System.out.println(
        e.source() + " -> " + e.targets()
    );
}

for (ModuleDescriptor.Opens o : d.opens()) {
    System.out.println(
        o.source() + " -> " + o.targets()
    );
}
~~~

Với directive không qualified, tập **targets()** rỗng; với directive qualified, tập này chứa tên module đích. Cần phân biệt hai trường hợp bằng **isQualified()**, không suy luận rằng tập rỗng là “không có quyền”.

Một chính sách kiểm thử hữu ích là khai báo rõ danh sách:

~~~text
unqualified exports:
  com.acme.order.api

qualified exports:
  com.acme.order.spi -> com.acme.plugin.host

qualified opens:
  com.acme.order.persistence -> com.acme.orm

other exports/opens:
  forbidden
~~~

Sau đó so sánh descriptor thực tế với hợp đồng này. Nhờ vậy, một thay đổi vô tình từ qualified export thành unqualified export sẽ bị phát hiện, dù tên package vẫn giữ nguyên.

## 9. Kiểm thử runtime trong đúng module caller

Các quyền xuất khẩu hoặc mở package có thể phụ thuộc caller. Một test chỉ gọi:

~~~java
targetModule.isOpen("com.acme.order.persistence")
~~~

không thể hiện đầy đủ cùng ngữ nghĩa với việc kiểm tra package được mở cho một module cụ thể:

~~~java
targetModule.isOpen(
    "com.acme.order.persistence",
    ormModule
)
~~~

Tương tự, với qualified exports:

~~~java
targetModule.isExported(
    "com.acme.order.spi",
    pluginModule
)
~~~

Hãy tạo test module tương ứng với từng đối tượng tiêu thụ quan trọng: ứng dụng thông thường, plugin được phép, framework ORM được phép và một module không được phép.

Một phép thử cho **com.acme.orm** chứng minh ORM có quyền cần thiết, nhưng chưa chứng minh **com.acme.untrusted** bị chặn. Đối với package nhạy cảm, cần cả positive và negative tests tương ứng với policy.

Một chi tiết nữa: các phép kiểm tra runtime có thể phản ánh những thay đổi về access sau khi khởi chạy, trong khi **ModuleDescriptor** phản ánh metadata gốc. Vì vậy, kiểm tra descriptor và kiểm tra hành vi runtime cần bổ sung cho nhau, không phải thay thế nhau.

## 10. Tránh để tùy chọn JVM che giấu kết quả test

Các tùy chọn sau có thể làm thay đổi ranh giới module lúc chạy:

~~~text
--add-exports source.module/package=target.module
--add-opens source.module/package=target.module
--add-reads source.module=target.module
~~~

Ví dụ:

~~~bash
java --add-opens com.acme.order/com.acme.order.internal=ALL-UNNAMED \
     -p "mods:testmods" \
     -m com.acme.contract.test/com.acme.contract.test.EncapsulationTest
~~~

Lệnh trên mở package cho unnamed modules, không nhất thiết mở cho module test có tên. Nếu mục tiêu là kiểm tra ranh giới giữa các named modules, cần kiểm tra chính xác target của từng flag.

Một cấu hình như sau sẽ trực tiếp làm phép thử reflection âm tính thất bại:

~~~bash
java --add-opens com.acme.order/com.acme.order.internal=com.acme.contract.test \
     -p "mods:testmods" \
     -m com.acme.contract.test/com.acme.contract.test.EncapsulationTest
~~~

Vì flag đã cấp quyền cho module test, **trySetAccessible()** có thể thành công. Đây không phải lỗi ngẫu nhiên của JVM mà là kết quả đúng theo cấu hình được yêu cầu.

Khi chạy contract tests:

1. Dùng lệnh Java rõ ràng, có thể tái hiện.
2. Kiểm tra **VM options** do IDE, Maven, Gradle hoặc CI truyền vào.
3. Tránh những flag mở rộng quyền nếu không nằm trong hợp đồng kiểm thử.
4. Kiểm tra các cấu hình **--patch-module** hoặc module-related options khác có thể thay đổi cách test được chạy.
5. Ghi nhận JDK version và loại module (named/unnamed/automatic) để giải thích kết quả.

Đặc biệt, nhiều framework test sử dụng reflection. Nếu test runner đã cấp **--add-opens** cho module đang được test, một negative reflection test có thể không còn phản ánh cấu hình production mà bạn muốn bảo vệ. Có thể chạy một JVM test độc lập với module test riêng để có bằng chứng chính xác hơn.

## 11. Không nhầm encapsulation với việc không thể khám phá metadata

Ngay cả khi package không export, một số API reflection vẫn có thể trả về tên class hoặc metadata của thành viên. Ví dụ:

~~~java
Class<?> type = state.getClass();

System.out.println(type.getName());
System.out.println(type.getDeclaredFields().length);
~~~

Việc nhìn thấy tên kiểu hoặc biết class có field chưa chứng minh caller có thể đọc, ghi hoặc gọi các thành viên đó. Ngăn chặn thao tác truy cập là khác với che giấu hoàn toàn mọi dấu vết metadata.

Một test sai hướng thường chỉ kiểm tra rằng:

~~~java
state.getClass().getDeclaredFields().length == 0
~~~

rồi suy luận “module được encapsulate”. Suy luận này không đúng; **getDeclaredFields()** có thể khám phá khai báo mà không cấp quyền truy cập sâu.

Thay vào đó, hãy kiểm tra:

- Có thể compile import nội bộ hay không?
- Package có được export/open cho caller không?
- Có thể **trySetAccessible()** hoặc **setAccessible(true)** để thực hiện deep reflection không?
- Có thể gọi public API đã phê duyệt không?

Các kết quả này gắn trực tiếp với hợp đồng JPMS cần bảo vệ.

## 12. Service provider không cần export implementation package

JPMS hỗ trợ service binding:

~~~java
module com.acme.order {
    exports com.acme.order.api;

    provides com.acme.order.api.OrderPlugin
        with com.acme.order.internal.DefaultOrderPlugin;
}
~~~

Trong trường hợp này, package **internal** có thể vẫn không được export hoặc open. **ServiceLoader** được phép tìm provider theo khai báo **provides ... with ...**, nhưng điều đó không đồng nghĩa mọi module được import hoặc deep-reflect vào implementation.

Đừng coi việc ServiceLoader phát hiện được provider là bằng chứng package implementation bị lộ API. Hợp đồng service được công bố qua kiểu service và module descriptor, còn implementation cụ thể có thể được giữ kín.

Ngược lại, nếu consumer dùng trực tiếp provider class thay vì service interface, bạn có thể đã vô tình tạo dependency vào implementation. Contract tests nên ưu tiên dùng service type công khai và kiểm tra package triển khai vẫn không được export.

## 13. Phân tích JAR cuối cùng, không chỉ module-info.java trong source

Trong pipeline build, artifact cuối có thể khác những gì developer nhìn thấy trong source tree. Một plugin đóng gói, build profile hoặc bước shading có thể làm mất descriptor hoặc thay đổi cấu trúc JAR.

Sau khi tạo JAR:

~~~bash
jar --create \
    --file dist/com.acme.order.jar \
    -C mods/com.acme.order .
~~~

Kiểm tra descriptor thực tế:

~~~bash
jar --describe-module \
    --file dist/com.acme.order.jar
~~~

Kiểm tra nội dung archive:

~~~bash
jar --list --file dist/com.acme.order.jar
~~~

Cần xác nhận:

- **module-info.class** có mặt trong modular JAR dự kiến.
- Tên module chính xác và ổn định.
- Không xuất hiện exports hoặc opens vượt ngoài allowlist.
- Các package implementation không trở thành exported package chỉ vì thay đổi artifact.
- JAR không vô tình chuyển thành automatic module.

Có thể dùng **jdeps** để tìm dependency tĩnh của JAR:

~~~bash
jdeps --summary dist/com.acme.order.jar
~~~

Tuy nhiên, **jdeps** không thay thế kiểm tra descriptor và negative tests. Một dependency tĩnh hợp lệ không chứng minh package được bảo vệ đúng; ngược lại, Java reflection có thể tạo quan hệ runtime mà phân tích tĩnh không thấy đầy đủ.

## 14. API public không phải lúc nào cũng là API ổn định

JPMS bảo vệ boundary ở cấp package. Một package đã được export có thể chứa nhiều public type, nhưng không phải public type nào cũng nên trở thành hợp đồng dùng lâu dài.

Ví dụ package:

~~~text
com.acme.order.api
  OrderService.java
  OrderRequest.java
  ExperimentalOrderDebug.java
~~~

Nếu **com.acme.order.api** được export, public type **ExperimentalOrderDebug** cũng có thể được module khác truy cập. JPMS không có directive export riêng từng class.

Do đó, nếu có public implementation không nên trở thành API:

- Chuyển class sang package không được export nếu hợp lý.
- Giảm access modifier khi thiết kế cho phép.
- Tách API ổn định khỏi package triển khai hoặc package thử nghiệm.
- Sử dụng công cụ kiểm tra API surface để phát hiện thay đổi public type/method trong các package được export.

Các bài kiểm thử JPMS giúp đảm bảo package boundary, còn kiểm thử compatibility của public API có thể cần thêm công cụ phân tích chữ ký public. Không nên coi “chỉ export đúng một package” là đủ để mọi class trong package đó đều được thiết kế chuẩn.

## 15. Đưa kiểm thử ranh giới module vào CI

Một pipeline có thể gồm các bước:

~~~text
1. Compile module nguồn
2. Package modular JAR
3. Kiểm tra ModuleDescriptor của JAR cuối
4. Compile positive consumer test: phải thành công
5. Compile negative consumer test: phải thất bại đúng lý do
6. Chạy negative reflection test: phải bị chặn
7. Chạy positive service/framework test nếu có qualified opens
8. Lưu lại log và kết quả cùng JDK version
~~~

Kết quả kỳ vọng:

| Kiểm thử | Kết quả đúng |
|---|---|
| Import public API được export | Biên dịch thành công. |
| Import package internal không export | Biên dịch thất bại vì module không export package. |
| Deep reflection từ module không được phép | **trySetAccessible()** trả false hoặc **setAccessible(true)** bị chặn. |
| Deep reflection từ framework được phép | Có thể hoạt động nếu policy cho phép và caller đúng module. |
| Descriptor exports/opens allowlist | Khớp chính xác. |
| Artifact cuối không phải open/automatic module | Điều kiện được xác nhận. |
| Chạy không có VM flags ngoài hợp đồng | Không cấp thêm quyền ngoài dự kiến. |

Nếu một trong các kiểm thử âm tính bắt đầu thành công sau khi nâng cấp dependency hoặc sửa descriptor, đó là tín hiệu cần xem lại: package nội bộ có thể vừa được export/open ngoài ý muốn.

Nếu kiểm thử dương tính thất bại, hợp đồng API có thể đã bị thu hẹp quá mức. Cả hai hướng đều quan trọng cho một module encapsulation contract ổn định.

## 16. Các lỗi kiểm thử thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Negative compile test thất bại vì không tìm thấy module | Module path của fixture sai. | Sửa đường dẫn trước khi kết luận encapsulation đạt. |
| Reflection negative test thành công bất ngờ | Test chạy trong cùng module, package bị opens, hoặc có --add-opens. | Tách test thành named module riêng, kiểm tra descriptor và VM options. |
| Test descriptor cho phép automatic module | Chỉ đếm exports/opens mà không xét loại module. | Kiểm tra **isAutomatic()** và **isOpen()**. |
| Test chỉ xem tên package, không xem target | Qualified exports/opens bị hiểu thành public. | So sánh cả **isQualified()** và **targets()**. |
| Test chạy trên classpath thay vì module path | Mất nhiều ranh giới named module dự kiến. | Chạy fixture như named module. |
| Package internal chứa public type trong package đã export | Mọi public type của package có thể truy cập. | Di chuyển implementation sang package không export. |
| Các VM options khác nhau giữa CI và production | Test cho kết quả không đại diện. | Đồng bộ cấu hình, tách test không có flags ngoại lệ. |
| Positive API test không tồn tại | Có thể đóng kín cả API hợp lệ mà không phát hiện. | Thêm positive consumer test. |

## 17. Checklist bảo vệ encapsulation

- Module được đóng gói thành **explicit named module**.
- Module không bị chuyển thành **automatic module** hoặc **open module** ngoài dự kiến.
- Chỉ các API package đã phê duyệt được unqualified export.
- Qualified exports/opens chỉ cấp cho module đích hợp lệ.
- Internal/implementation packages không bị export hay open ngoài ý muốn.
- Test consumer thuộc một named module khác, không nằm trong module nguồn.
- Positive compile test dùng được API hợp lệ.
- Negative compile test bị từ chối vì đúng quy tắc export.
- Negative runtime test xác nhận không được deep reflection từ caller ngoài allowlist.
- Descriptor trong JAR cuối khớp policy; không chỉ kiểm tra source.
- Các VM options như **--add-exports**, **--add-opens** được quản lý và không làm vô hiệu kiểm thử.
- CI chạy lại các contract tests sau khi đổi descriptor, JDK hoặc cấu hình build.

**Kiểm thử một module không lộ API ngoài ý muốn là kiểm thử một hợp đồng truy cập**, không phải chỉ kiểm tra tên package hay số lượng class public. Hãy kết hợp ba lớp bằng chứng: **negative compile tests**, **runtime reflection tests** và **ModuleDescriptor allowlist** trên artifact đã đóng gói. Cách làm này phát hiện cả trường hợp API công khai bị mở rộng vô tình lẫn trường hợp framework hoặc JVM options nới quyền reflection vượt thiết kế.