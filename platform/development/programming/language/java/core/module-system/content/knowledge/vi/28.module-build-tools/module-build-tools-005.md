# Test module path và test module descriptor

## 1. Kiểm thử trong Java Platform Module System

Trong ứng dụng Java truyền thống, các class production và class test thường được ghép vào cùng một classpath. Test framework tìm test class, tải class và gọi method mà không cần biết module descriptor.

Với **Java Platform Module System (JPMS)**, khi mã production trở thành named module, ranh giới truy cập được quyết định bởi:

- Tên module và những dependency **requires**.
- Quan hệ module **readability**.
- Package nào được **exports** để module khác truy cập public API.
- Package nào được **opens** để framework dùng deep reflection.
- Class loader và module layer nơi class được định nghĩa.

Do đó, chạy test không còn chỉ là đưa các file JAR vào một danh sách đường dẫn. Cần xác định **test module path**, cách tổ chức test code và liệu test có descriptor **module-info.java** riêng hay được ghép vào module production bằng **--patch-module**.

Có hai mô hình quan trọng:

1. **Test như một named module độc lập**: có descriptor riêng, chỉ truy cập API mà module production export, phù hợp kiểm thử public contract và integration.
2. **Test được patch vào production module**: không có named test module riêng tại thời điểm chạy; test code được xem là một phần của module production, phù hợp kiểm thử package-private code hoặc những trường hợp cần test nằm cùng package với implementation.

Hai mô hình giải quyết nhu cầu khác nhau. Không nên sử dụng tùy chọn mở toàn bộ package nội bộ nếu một test chỉ cần public API.

## 2. Module path khác classpath như thế nào?

**Classpath** chứa class/JAR được nạp vào unnamed module của class loader tương ứng. Code trong unnamed module thường không có file module-info.java.

**Module path** chứa các named module có thể được phân giải. Một entry có thể là modular JAR, exploded module hoặc JAR được xem là automatic module tùy nội dung artifact.

Ví dụ:

~~~bash
java --class-path "build/classes:lib/*" com.acme.app.Main
~~~

và:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

không có cùng quy tắc truy cập. Với named module, việc một class nằm trong JAR có mặt trên module path **không đảm bảo** consumer được phép import nó. Consumer còn cần đọc module chứa class và package phải được export phù hợp.

Trong kiểm thử, một bộ test có thể có dependency riêng với production, ví dụ assertion library hoặc test engine. Đặt mọi dependency test lên classpath rồi kỳ vọng chúng tự nhìn thấy mọi package của named module thường dẫn tới lỗi readability, encapsulation hoặc reflection.

## 3. Test module path là gì?

**Test module path** là tập named module được cung cấp cho compiler hoặc runtime khi biên dịch/chạy test. Đây không phải một tùy chọn Java có tên --test-module-path; thực tế vẫn sử dụng **--module-path** (hoặc **-p**) với các đường dẫn chứa module cần thiết cho bài test.

Thông thường cần các nhóm artifact sau:

- **Production modules**: module ứng dụng và các module thư viện cần test.
- **Test modules**: nếu test được biên dịch thành named module riêng.
- **Test framework modules**: JUnit hoặc runner module nếu bài test sử dụng framework.
- **Dependency modules**: các module mà production và test cần ở compile-time/runtime.

Có thể có hai thư mục output:

~~~text
project/
├── src/          # production module sources
├── test-src/     # test module sources
├── mods/         # production exploded modules
└── test-mods/    # test exploded modules
~~~

Ví dụ lệnh chạy module test độc lập:

~~~bash
java --module-path mods:test-mods \
     --module com.acme.math.tests/com.acme.math.tests.TestMain
~~~

Trên Linux/macOS, nhiều entry trong path được phân cách bằng dấu hai chấm. Trên Windows, dùng dấu chấm phẩy và đặt chuỗi đường dẫn trong dấu nháy khi cần:

~~~powershell
java --module-path "mods;test-mods" --module com.acme.math.tests/com.acme.math.tests.TestMain
~~~

Khi build bằng Maven hoặc Gradle, plugin test có thể tạo module path và các tùy chọn launcher thay cho bạn. Tuy nhiên, cần hiểu module path thực tế nếu muốn chẩn đoán lỗi test.

## 4. Ví dụ production module làm đối tượng kiểm thử

Tạo project có một module com.acme.math:

~~~text
src/
└── com.acme.math/
    ├── module-info.java
    └── com/
        └── acme/
            └── math/
                ├── api/
                │   └── Calculator.java
                └── internal/
                    └── Accumulator.java
~~~

Module descriptor:

~~~java
module com.acme.math {
    exports com.acme.math.api;
}
~~~

Class công khai:

~~~java
package com.acme.math.api;

public final class Calculator {
    private Calculator() {
    }

    public static int sum(int left, int right) {
        return left + right;
    }
}
~~~

Class nội bộ:

~~~java
package com.acme.math.internal;

final class Accumulator {
    private int total;

    void add(int value) {
        total += value;
    }

    int value() {
        return total;
    }
}
~~~

Module chỉ export com.acme.math.api. Package com.acme.math.internal không được export; class Accumulator còn là package-private.

Biên dịch module production:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.math
~~~

Output:

~~~text
mods/
└── com.acme.math/
    ├── module-info.class
    └── com/acme/math/
        ├── api/Calculator.class
        └── internal/Accumulator.class
~~~

Đây là exploded named module có thể sử dụng trực tiếp trong test module path.

## 5. Mô hình A: một test module có descriptor riêng

Nếu muốn kiểm thử **public API** giống như consumer thực sự, đặt test code vào một named module độc lập.

Source tree:

~~~text
test-src/
└── com.acme.math.tests/
    ├── module-info.java
    └── com/
        └── acme/
            └── math/
                └── tests/
                    └── TestMain.java
~~~

Descriptor của test module:

~~~java
module com.acme.math.tests {
    requires com.acme.math;
}
~~~

Class test không dùng framework ngoài:

~~~java
package com.acme.math.tests;

import com.acme.math.api.Calculator;

public class TestMain {
    public static void main(String[] args) {
        assertEquals(5, Calculator.sum(2, 3));
        assertEquals(0, Calculator.sum(-2, 2));
        System.out.println("All tests passed");
    }

    private static void assertEquals(int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "Expected " + expected + ", got " + actual
            );
        }
    }
}
~~~

Test module chỉ import Calculator từ package đã export của production module. Đây là kiểm thử quan trọng của API contract: test không được phép phụ thuộc vào implementation package mà người dùng thư viện cũng không được thấy.

## 6. Biên dịch test module độc lập

Sau khi biên dịch production vào mods, biên dịch test:

~~~bash
javac --module-source-path test-src \
      --module-path mods \
      -d test-mods \
      -m com.acme.math.tests
~~~

Giải thích:

- --module-source-path test-src: nơi chứa source của test module, bao gồm module-info.java.
- --module-path mods: nơi javac tìm production named module.
- -d test-mods: nơi tạo output của test module.
- -m com.acme.math.tests: tên module test được biên dịch.

Output:

~~~text
test-mods/
└── com.acme.math.tests/
    ├── module-info.class
    └── com/acme/math/tests/TestMain.class
~~~

Chạy:

~~~bash
java --module-path mods:test-mods \
     -m com.acme.math.tests/com.acme.math.tests.TestMain
~~~

Kết quả mong đợi:

~~~text
All tests passed
~~~

Trong cách làm này, test module không hề bị ghép vào production module. Hai module có tên riêng, descriptor riêng, ranh giới API riêng.

## 7. Test module không thể bỏ qua exports

Giả sử trong test module độc lập, ta viết:

~~~java
package com.acme.math.tests;

import com.acme.math.internal.Accumulator;
~~~

Code này không hợp lệ trong ví dụ hiện tại vì:

1. com.acme.math.internal không được export từ com.acme.math.
2. Accumulator là class package-private nên không thể truy cập từ một package khác ngay cả khi package đã được export.

Thêm requires com.acme.math vào module descriptor của test chỉ tạo quan hệ đọc; nó không buộc module production công khai các package nội bộ.

Tùy mục đích, có thể:

- Chỉ kiểm thử public behavior qua Calculator, giữ nguyên encapsulation.
- Đưa test vào cùng module/package bằng --patch-module khi thật sự cần kiểm thử logic package-private.
- Refactor phần logic cần kiểm thử thành một API có ranh giới rõ ràng nếu nhiều consumer hợp lệ cần sử dụng.

Không nên export tất cả package internal chỉ vì test module độc lập không biên dịch được.

## 8. Mô hình B: patch test code vào production module

Trong nhiều bộ unit test, class test cần cùng package với class production để truy cập các thành viên package-private.

Tùy chọn **--patch-module** cho phép bổ sung class test vào module production có sẵn ở compile-time và runtime. Đây là cách thường gặp khi test framework cần giữ bố cục package giống source production.

Ví dụ source test:

~~~text
patch-src/
└── com/
    └── acme/
        └── math/
            └── internal/
                └── AccumulatorTest.java
~~~

Test class:

~~~java
package com.acme.math.internal;

public class AccumulatorTest {
    public static void main(String[] args) {
        Accumulator acc = new Accumulator();
        acc.add(4);
        acc.add(6);

        if (acc.value() != 10) {
            throw new AssertionError(
                    "Expected 10, got " + acc.value()
            );
        }
        System.out.println("Internal test passed");
    }
}
~~~

AccumulatorTest ở cùng package com.acme.math.internal với Accumulator. Khi được patch thành một phần của module com.acme.math, test có thể truy cập type và member package-private theo các quy tắc truy cập Java.

## 9. Biên dịch và chạy test bằng --patch-module

Biên dịch test source trong ngữ cảnh module production:

~~~bash
javac --module-path mods \
      --patch-module com.acme.math=patch-src \
      -d patch-classes \
      patch-src/com/acme/math/internal/AccumulatorTest.java
~~~

Giải thích:

- --module-path mods: module com.acme.math đã biên dịch.
- --patch-module com.acme.math=patch-src: test source được xử lý như phần bổ sung của module com.acme.math.
- -d patch-classes: xuất test bytecode sang thư mục riêng, không đè sản phẩm production.

Chạy test đã biên dịch:

~~~bash
java --module-path mods \
     --patch-module com.acme.math=patch-classes \
     -m com.acme.math/com.acme.math.internal.AccumulatorTest
~~~

Kết quả:

~~~text
Internal test passed
~~~

Ở runtime, class test thuộc module com.acme.math, cùng package với class production. Không cần export com.acme.math.internal cho module test độc lập vì trong mô hình này **không tồn tại module test riêng** chứa AccumulatorTest.

Khi chạy mà quên --patch-module, JVM chỉ nhìn thấy nội dung module gốc và có thể không tìm được main class của test. Biên dịch patch không tự thay đổi artifact production.

## 10. So sánh test module descriptor và patch module

| Tiêu chí | Test named module riêng | Test được patch vào production |
|---|---|---|
| Module của test | Có tên và module-info.java riêng | Dùng chính tên module production |
| Quan hệ với production | Khai báo requires | Test được xem là code trong production module |
| Truy cập public API exported | Có, nếu module đọc được dependency | Có |
| Truy cập package-private cùng package | Không, nếu ở module khác | Có thể, khi test nằm cùng package của module được patch |
| Tính sát thực với external consumer | Cao | Thấp hơn vì test có quyền nội bộ |
| Tình huống phù hợp | API test, integration test, boundary test | Unit test logic nội bộ, fixture |
| Cấu hình chính | --module-path, module-info.java | --patch-module, thường kèm module path |
| Tách artifact test khỏi production | Có | Có thể giữ test bytecode trong output riêng |

Hai chiến lược có thể cùng tồn tại: kiểm thử contract bằng test named module độc lập, kiểm thử internal helper bằng patched test. Chọn công cụ theo nhu cầu encapsulation chứ không tạo thêm quyền truy cập chỉ để tiện viết test.

## 11. Descriptor của test khi dùng JUnit

Một framework kiểm thử như JUnit 5 cung cấp API để đánh dấu test method và một platform/engine để tìm, thực thi chúng. Trong named test module, descriptor cần khai báo dependency đối với những module mà test code thực sự import.

Ví dụ minh họa một test module dùng JUnit Jupiter API:

~~~java
module com.acme.math.tests {
    requires com.acme.math;
    requires org.junit.jupiter.api;
}
~~~

Test code:

~~~java
package com.acme.math.tests;

import com.acme.math.api.Calculator;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void sumsNumbers() {
        assertEquals(5, Calculator.sum(2, 3));
    }
}
~~~

Đây là **ví dụ descriptor ở mức ý tưởng**. Lệnh chạy cụ thể tùy phiên bản JUnit, runner, build tool và việc các JAR JUnit được đặt trên module path hay classpath. Test engine và launcher còn có dependency riêng; chỉ thêm requires org.junit.jupiter.api không có nghĩa mọi runner sẽ tự tìm và chạy test.

Vì nhiều runner dùng reflection để khám phá hoặc gọi test method, có thể cần **opens package test** cho module runner tương ứng:

~~~java
module com.acme.math.tests {
    requires com.acme.math;
    requires org.junit.jupiter.api;

    opens com.acme.math.tests to org.junit.platform.commons;
}
~~~

Danh sách module cần opens phụ thuộc runner thực tế và cách test framework triển khai. Không tự động mở toàn bộ module nếu chỉ một package test cần reflective access.

## 12. Test framework và --add-reads

Khi test được patch vào production module, test code có thể tham chiếu API JUnit hoặc framework khác mà production module **không** khai báo requires. Điều này tạo bài toán module readability.

Ví dụ module production:

~~~java
module com.acme.math {
    exports com.acme.math.api;
}
~~~

Nếu class test được patch vào com.acme.math và dùng org.junit.jupiter.api.Test, module com.acme.math có thể cần một quan hệ đọc bổ sung tới module chứa JUnit API khi compile hoặc chạy test.

Có thể sử dụng tùy chọn thử nghiệm:

~~~text
--add-reads com.acme.math=org.junit.jupiter.api
~~~

hoặc điều chỉnh cách bố trí test module/framework theo cơ chế hỗ trợ của build tool. Nếu JUnit API được đặt trên classpath, module đích của --add-reads có thể là ALL-UNNAMED trong tình huống phù hợp.

Tuy nhiên, --add-reads không tự đưa JUnit vào module graph. Với named module chưa được phân giải, có thể cần --add-modules hoặc thêm root module phù hợp. Cần xem cấu hình runner thực tế để biết đã tạo những module nào.

Những flag kiểu này thuộc cấu hình test. Không nên thêm requires tới thư viện kiểm thử vào module-info.java **production** nếu thư viện test không phải dependency thực sự của phần mềm phát hành.

## 13. Test framework và --add-opens

JUnit, mock framework, dependency injection container hoặc serializer có thể cần deep reflection vào class nội bộ.

Với named module, việc package được exports **không đồng nghĩa** private member tự động mở cho reflection. Khi framework cần quyền mở, thường dùng:

~~~text
--add-opens module.name/package.name=target.module
~~~

Ví dụ:

~~~bash
java --module-path mods:test-mods:lib-mods \
     --add-opens com.acme.math/com.acme.math.internal=org.junit.platform.commons \
     -m com.acme.math.tests/com.acme.math.tests.TestMain
~~~

Ví dụ này minh họa cú pháp. Cần thay target module theo module thực sự thực hiện reflective access; không phải mọi test runner đều cần mở com.acme.math.internal.

Phân biệt rõ:

- **exports**: cho phép truy cập Java thông thường vào public type/member của package.
- **opens**: cho phép deep reflection theo quy tắc JPMS.
- **--add-exports**: bổ sung export tạm thời tại compile-time hoặc runtime.
- **--add-opens**: bổ sung quyền mở package tại runtime.
- **--patch-module**: bổ sung class/resource vào module đã có.

Nếu lỗi đến từ import một type không export, opens không giải quyết được vấn đề biên dịch. Nếu lỗi đến từ reflection vào private member, exports không tự giải quyết được.

## 14. Test module path trong Maven hoặc Gradle

Các build tool thường quản lý dependency test ở scope riêng. Với JPMS, cần để ý một số điểm:

1. Production source có module-info.java hay không.
2. Test source có module-info.java riêng hay được build tool patch vào module production.
3. Test dependency đang nằm trên module path, classpath hay tổ hợp được hỗ trợ.
4. Test runner dùng module layer/class loader nào để khám phá test.
5. Những tùy chọn --patch-module, --add-reads, --add-exports, --add-opens có được sinh tự động hay phải cấu hình thủ công.
6. Runtime JDK của test có tương thích với bytecode, test engine và các named module hay không.

Ví dụ, trong Maven các plugin compiler và test runner có các tùy chọn liên quan đến module path. Trong Gradle, Java plugin và test task cũng có cơ chế cấu hình module inference/test runtime. Hành vi chi tiết phụ thuộc version của build tool/plugin và project layout.

Một lỗi dễ gặp là compile test với một bộ tùy chọn module, nhưng test runner dùng bộ tùy chọn khác. Hãy quan sát lệnh Java thực tế của test task khi cần chẩn đoán thay vì chỉ dựa trên cấu hình dependency được khai báo trong build file.

## 15. Kiểm tra module descriptor của test

Với test module riêng, có thể kiểm tra module-info.class:

~~~bash
javap -p -v test-mods/com.acme.math.tests/module-info.class
~~~

Đối với modular JAR, dùng:

~~~bash
jar --describe-module --file dist/com.acme.math.tests.jar
~~~

Lưu ý: test module không bắt buộc phải được đóng gói thành JAR. Exploded module dưới test-mods/com.acme.math.tests là đủ để chạy.

Khi test module có requires production, descriptor phải phản ánh đúng tên module. Đừng sử dụng tên artifact Maven/JAR thay cho JPMS module name nếu hai tên khác nhau.

Nếu dùng patch strategy, không cần tạo module-info.java thứ hai chỉ để patch vào module production. Việc cố cung cấp descriptor khác tên hoặc descriptor trùng gốc có thể gây xung đột không cần thiết. Hãy dùng descriptor của production và các tùy chọn test thích hợp.

## 16. Quan sát module resolution khi chạy test

Có thể bật thông tin phân giải module:

~~~bash
java --show-module-resolution \
     --module-path mods:test-mods \
     -m com.acme.math.tests/com.acme.math.tests.TestMain
~~~

Thông tin này giúp xác định module roots, dependency modules và các quan hệ được phân giải. Nó đặc biệt hữu ích khi test module không tìm thấy production module hoặc test framework module.

Để xem một số vấn đề cấu hình module path, có thể dùng:

~~~bash
java --validate-modules --module-path mods:test-mods
~~~

Tùy chọn --validate-modules thực hiện kiểm tra module path theo khả năng của launcher. Đây không phải lệnh thay thế việc chạy test; nó hỗ trợ phát hiện một số lỗi cấu hình trước khi thực thi.

Trong trường hợp cần xác nhận class được nạp từ đâu, có thể bật class loading logging:

~~~bash
java -Xlog:class+load=info \
     --module-path mods:test-mods \
     -m com.acme.math.tests/com.acme.math.tests.TestMain
~~~

Việc xem nguồn class giúp phân biệt test code đang được nạp từ test module độc lập, từ patch output hay từ một JAR nằm ngoài dự kiến.

## 17. Các lỗi thường gặp với test module descriptor

### Module not found

Thông báo ví dụ:

~~~text
module not found: com.acme.math
~~~

Test module khai báo requires com.acme.math nhưng javac hoặc java không nhìn thấy artifact đó.

Cách xử lý: biên dịch production trước, đưa mods hoặc modular JAR đúng vào --module-path, kiểm tra tên module và cấu trúc output. Không nhầm root thư mục mods với thư mục con mods/com.acme.math khi chọn kiểu module path phù hợp.

### Package is not visible

Test module import package internal chưa export. Cần kiểm thử qua public API, hoặc dùng patch strategy nếu bài test thật sự cần package-private code.

### InaccessibleObjectException

Test framework dùng deep reflection vào package chưa được open. Xem lỗi để xác định module thực hiện reflection, rồi cân nhắc opens trong descriptor test hoặc --add-opens tạm thời ở runtime.

### Test class không được tìm thấy

Có thể test class ở output directory nhưng runner lại tìm sai module layer, class loader, package hoặc module path. Kiểm tra lệnh của test runner và nguồn class thực tế.

### Split package giữa production và test named module

Nếu test module độc lập đặt class vào cùng package com.acme.math.internal với production, hai named module cùng có một package. Điều này có thể gây lỗi split package khi graph/layer có liên quan.

Với test named module, nên dùng package test riêng. Nếu cần test cùng package production, hãy dùng --patch-module để test code thuộc cùng named module thay vì tạo một named test module thứ hai chia package đó.

### Duplicate module name

Module path có nhiều JAR/exploded module có cùng tên JPMS. Cần loại bỏ bản trùng hoặc điều chỉnh dependency trước khi chạy test; đổi tên file JAR không giải quyết tên module trong descriptor.

### NoClassDefFoundError hoặc ServiceConfigurationError

Test dependency có thể thiếu ở runtime, service provider chưa được đưa vào layer, hoặc test engine không phân giải được module cần thiết. Kiểm tra module path runtime và các uses/provides khi dùng ServiceLoader.

## 18. Đừng mở rộng API production chỉ để chạy test

Một số hướng xử lý có vẻ nhanh nhưng làm yếu encapsulation:

- Export toàn bộ package internal để test import được.
- Mở toàn bộ module bằng open module mà không có nhu cầu runtime thật.
- Đưa test framework vào requires của module production.
- Ghép tất cả test JAR vào module path mà không kiểm soát named/automatic module.
- Chuyển source test vào production source để compiler không báo lỗi.

Những cách này làm thay đổi hợp đồng hoặc cấu trúc runtime của phần mềm phát hành chỉ vì nhu cầu của test.

Nguyên tắc phù hợp hơn:

- Kiểm thử hành vi public bằng named test module độc lập.
- Kiểm thử các chi tiết package-private bằng patch strategy khi cần.
- Giới hạn opens hoặc --add-opens đến đúng package và đúng module đích.
- Giữ test dependency trong cấu hình test, không phát hành như runtime dependency của production khi không cần.
- Không thay đổi module-info.java production chỉ để che lỗi build/test nếu có cách cấu hình test riêng.

Việc rạch ròi như vậy giúp sản phẩm giữ encapsulation mạnh, trong khi test vẫn có thể truy cập những phần cần thiết với phạm vi đã kiểm soát.

## 19. Quy trình thực hành một dự án modular

Khi thiết lập test module path từ đầu, có thể làm theo quy trình:

1. **Xác định tên module production** và những package được exports/opens trong module-info.java.
2. **Biên dịch production** bằng javac --module-source-path và -m, kiểm tra module-info.class.
3. **Chọn chiến lược test**: named test module độc lập để test API, hay --patch-module để test nội bộ.
4. **Nếu chọn named test module**, tạo module-info.java của test với requires production và các framework module cần dùng.
5. **Biên dịch test** với --module-source-path test-src, --module-path mods và -d test-mods.
6. **Nếu chọn patch test**, biên dịch với --patch-module production.module=patch-src và đặt output ở thư mục riêng.
7. **Chạy test** bằng java -p và -m hoặc test runner, đảm bảo module path runtime chứa đủ dependency.
8. **Chỉ thêm quyền phù hợp khi cần**: --add-reads cho readability, --add-exports cho public access, --add-opens cho deep reflection.
9. **Quan sát lỗi resolution/class loading** nếu test không được khám phá hoặc không chạy.
10. **Giữ artifact production sạch**: không ghi test class vào output hoặc modular JAR phát hành.

Khi dùng framework lớn, build tool là lựa chọn thuận tiện để quản lý các bước này. Tuy vậy, hiểu cú pháp javac/java ở mức module giúp xác định chính xác lỗi phát sinh tại compilation, resolution, class loading hay test discovery.

## 20. Ghi nhớ

- **Test module path** là module path dùng để biên dịch/chạy test; Java không có tùy chọn chuẩn tên --test-module-path.
- **Test module descriptor** là module-info.java của named test module khi test được tổ chức thành module độc lập.
- Named test module cần requires module production và những module framework mà mã test import.
- Named test module chịu cùng quy tắc readability, exports và opens như các module khác.
- **--patch-module** cho phép đặt test class vào production module để truy cập package-private code ở cùng package.
- Test module độc lập không nên đặt class vào package đã thuộc production module để tránh split package.
- **--add-reads** và **--add-opens** giải quyết những vấn đề khác nhau; không dùng một tùy chọn để thay thế tùy chọn kia.
- Test framework dùng reflection có thể cần mở package test hoặc package production một cách có giới hạn.
- Compile-time module path và runtime module path cần nhất quán, nhưng chúng phục vụ các giai đoạn khác nhau.
- Xem --show-module-resolution, module-info.class và lệnh test runner khi chẩn đoán.
- Đừng thay đổi exports/opens của production một cách rộng rãi chỉ để test chạy.

**Kết luận:** Với JPMS, cấu hình test cần tôn trọng module graph và encapsulation. Hãy dùng named test module cùng descriptor riêng khi muốn kiểm thử như một consumer bên ngoài; dùng --patch-module khi cần kiểm thử nội bộ trong cùng module. Hai cách tiếp cận này giúp kiểm thử có phạm vi rõ ràng mà không phải hy sinh ranh giới thiết kế của module production.