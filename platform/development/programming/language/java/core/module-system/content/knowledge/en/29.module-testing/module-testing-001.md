# Test code trong named test module

Khi kiểm thử một ứng dụng Java dùng JPMS, test code không nhất thiết phải chạy trên classpath hoặc được ghép trực tiếp vào module sản phẩm. Ta có thể tạo một **named test module** riêng, có tên và **module-info.java** của chính nó. Module kiểm thử khai báo **requires** tới module cần kiểm thử, đồng thời chỉ truy cập những package được module sản phẩm export. Nhờ vậy, test chạy dưới các quy tắc readability và strong encapsulation gần với ứng dụng modular thực tế hơn.

Cách tổ chức này phù hợp khi muốn kiểm tra API công khai, kiểm tra integration giữa nhiều module hoặc kiểm chứng rằng thư viện thực sự sử dụng được từ một consumer named module độc lập. Nó khác với kỹ thuật **--patch-module**, vốn đưa test classes vào module cần kiểm thử để có thể kiểm tra implementation nội bộ trong một số tình huống.

Bài này trình bày named test module, cách biên dịch/chạy bằng JDK, cách dùng JUnit Platform, những giới hạn khi truy cập package nội bộ và cách lựa chọn chiến lược test theo mục đích.

## 1. Named test module là gì?

Một named test module là một module có tên tường minh, được tạo riêng cho mã kiểm thử. Nó thường có một file **module-info.java** cùng tập class test, nhưng không được đóng gói thành một phần của artifact sản phẩm phát hành cho người dùng cuối.

Ví dụ module sản phẩm:

~~~java
module com.acme.calculator {
    exports com.acme.calculator.api;
}
~~~

Module kiểm thử riêng:

~~~java
module com.acme.calculator.tests {
    requires com.acme.calculator;
}
~~~

Tên **com.acme.calculator.tests** là tên của test module; nó khác với **com.acme.calculator**. Directive **requires** cho phép test module đọc module sản phẩm. Vì module sản phẩm chỉ export package **com.acme.calculator.api**, test module có thể sử dụng API trong package đó nhưng không thể import trực tiếp các class thuộc package không export.

Đây là khác biệt quan trọng so với việc chạy test đơn thuần trên classpath: code test hoạt động như một consumer modular thực sự, phải tuân thủ module graph và module boundary.

Lợi ích chính:

- Phát hiện dependency thiếu trong module descriptor của consumer.
- Kiểm tra package public API được export đúng.
- Kiểm tra hành vi của module khi code gọi đến từ module khác.
- Tách test framework/dependency khỏi module sản phẩm.
- Có thể xây dựng các bộ integration test dưới dạng những named module độc lập.
- Tránh vô tình dựa vào package-private members hoặc implementation package không export.

Tuy nhiên, named test module không tự thay thế unit test nội bộ, không bảo đảm test framework đã được resolve và không giúp truy cập package-private của module khác.

## 2. Hai chiến lược kiểm thử modular thường gặp

Trước khi viết test, cần chọn ranh giới mà bài test muốn kiểm tra.

| Chiến lược | Module identity của test | Điểm mạnh | Giới hạn |
|---|---|---|---|
| **Named test module riêng** | Module khác module sản phẩm | Kiểm tra API, readability, exports và integration như consumer thật | Không truy cập package không export hoặc package-private chỉ nhờ requires |
| **Patch test classes vào module sản phẩm** | Test classes được coi thuộc module sản phẩm tại runtime | Hữu ích khi cần kiểm tra implementation, package-private hoặc test gần cấu trúc production | Không còn là một consumer module độc lập; cần cấu hình --patch-module và framework access chính xác |
| **Test trên classpath** | Unnamed module của class loader | Đơn giản cho code legacy và một số test runner | Có thể không kiểm tra đầy đủ module boundary của named consumer |
| **Custom ModuleLayer cho test** | Một hay nhiều named module trong layer riêng | Kiểm tra plugin, provider, multi-layer behavior | Phức tạp hơn về module finder, loader và service identity |

Không phải dự án nào cũng cần mọi chiến lược. Với một thư viện công bố API cho nhiều module khác, named test module riêng rất hữu ích. Với logic package-private mà dự án quyết định kiểm thử trực tiếp, patch-module có thể phù hợp hơn, nhưng nên đánh giá xem test qua public API có đủ hay không trước.

## 3. Cấu trúc source cho production và test module

Một ví dụ tối giản dùng hai source roots: **src** dành cho module sản phẩm và **tests** dành cho module test.

~~~text
project/
├── src/
│   └── com.acme.calculator/
│       ├── module-info.java
│       └── com/acme/calculator/api/
│           └── Calculator.java
├── tests/
│   └── com.acme.calculator.tests/
│       ├── module-info.java
│       └── com/acme/calculator/tests/
│           └── CalculatorTestMain.java
├── mods/
└── test-mods/
~~~

Mỗi thư mục module gốc có descriptor riêng. Package của test đặt là **com.acme.calculator.tests**, không đặt chung tên package implementation của module sản phẩm.

Việc dùng hai source roots giúp tách dependency:

- Production module không cần phụ thuộc JUnit hay test helper.
- Test module có thể phụ thuộc production module và các test libraries.
- Artifact production chỉ lấy output từ **mods/com.acme.calculator**.
- Artifact test và test runner dùng output từ **test-mods/com.acme.calculator.tests**.
- Có thể kiểm tra module API bằng cách thực sự chạy test từ một named module khác.

Dù module name thường có suffix **.tests**, tên cụ thể là lựa chọn của dự án; nó cần hợp lệ và không trùng tên module được dùng trong cùng configuration.

## 4. Ví dụ production module hoàn chỉnh

Descriptor sản phẩm:

~~~java
// src/com.acme.calculator/module-info.java
module com.acme.calculator {
    exports com.acme.calculator.api;
}
~~~

Class API:

~~~java
// src/com.acme.calculator/com/acme/calculator/api/Calculator.java
package com.acme.calculator.api;

public final class Calculator {
    public int add(int left, int right) {
        return Math.addExact(left, right);
    }

    public int subtract(int left, int right) {
        return Math.subtractExact(left, right);
    }
}
~~~

Ở ví dụ này, **Calculator** là một kiểu public thuộc package được export. Test module khác có thể import class và gọi các phương thức public sau khi khai báo **requires com.acme.calculator**.

Giả sử module sản phẩm còn một package **com.acme.calculator.internal** để chứa thuật toán triển khai; package đó không được export và không phải một phần của hợp đồng API. Test consumer độc lập nên kiểm tra kết quả mà public API cung cấp thay vì import class implementation nội bộ.

Việc dùng **Math.addExact** giúp ví dụ có một hành vi lỗi rõ ràng để test: khi phép cộng vượt miền int, method ném **ArithmeticException**. Một public API tốt cần định nghĩa cả hành vi bình thường lẫn điều kiện lỗi mà consumer có thể quan sát.

## 5. Viết named test module không cần framework

Để thấy rõ cơ chế JPMS trước khi thêm JUnit, tạo một test module có main method dùng assertions thủ công.

Descriptor của test module:

~~~java
// tests/com.acme.calculator.tests/module-info.java
module com.acme.calculator.tests {
    requires com.acme.calculator;
}
~~~

Class test:

~~~java
// tests/com.acme.calculator.tests/com/acme/calculator/tests/CalculatorTestMain.java
package com.acme.calculator.tests;

import com.acme.calculator.api.Calculator;

public final class CalculatorTestMain {
    public static void main(String[] args) {
        Calculator calculator = new Calculator();

        if (calculator.add(2, 3) != 5) {
            throw new AssertionError("2 + 3 should equal 5");
        }

        if (calculator.subtract(8, 3) != 5) {
            throw new AssertionError("8 - 3 should equal 5");
        }

        boolean overflowDetected = false;
        try {
            calculator.add(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException expected) {
            overflowDetected = true;
        }

        if (!overflowDetected) {
            throw new AssertionError("Overflow should throw");
        }

        System.out.println("All modular tests passed");
    }
}
~~~

Nếu test thất bại, **AssertionError** làm tiến trình báo lỗi. Ví dụ này không dùng Java keyword **assert**, vì **assert** có thể bị vô hiệu hóa nếu runtime không bật **-ea**. Trong bài kiểm thử thực tế, một test framework thường quản lý assertion, test discovery và reporting thay cho code thủ công.

Điều quan trọng là test class được định nghĩa trong named module **com.acme.calculator.tests** và truy cập production API qua **requires** cộng **exports**.

## 6. Biên dịch và chạy test module bằng javac/java

Giả sử đang đứng ở root thư mục dự án với cấu trúc của ví dụ trên, biên dịch production module trước:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.calculator
~~~

Sau đó biên dịch test module. Test cần tìm production module đã được biên dịch trên module path:

~~~bash
javac --module-path mods \
      --module-source-path tests \
      -d test-mods \
      -m com.acme.calculator.tests
~~~

Với layout này, output sau biên dịch có dạng:

~~~text
mods/
└── com.acme.calculator/
    ├── module-info.class
    └── com/acme/calculator/api/Calculator.class

test-mods/
└── com.acme.calculator.tests/
    ├── module-info.class
    └── com/acme/calculator/tests/CalculatorTestMain.class
~~~

Chạy test như một chương trình modular:

~~~bash
java --module-path "mods:test-mods" \
     -m com.acme.calculator.tests/com.acme.calculator.tests.CalculatorTestMain
~~~

Trên Linux/macOS, module path phân cách bằng dấu hai chấm như ví dụ. Trên Windows, dùng dấu chấm phẩy: **"mods;test-mods"**. Các dòng lệnh này dùng Java 9+ và giả định đường dẫn source/output trùng cấu trúc minh họa.

Khi chạy, launcher phải resolve **com.acme.calculator.tests** làm root. Directive **requires com.acme.calculator** đưa production module vào graph. Nếu thiếu module sản phẩm trong module path, runtime có thể báo **FindException**; đó là bằng chứng test đang chịu sự kiểm soát dependency của JPMS.

## 7. Vì sao test module không thể tự ý dùng package nội bộ?

Giả sử production module có class:

~~~java
package com.acme.calculator.internal;

public final class CalculationEngine {
    public int compute(int x, int y) {
        return x + y;
    }
}
~~~

Class là **public**, nhưng package **com.acme.calculator.internal** không được export trong descriptor:

~~~java
module com.acme.calculator {
    exports com.acme.calculator.api;
}
~~~

Nếu test module import class nội bộ:

~~~java
import com.acme.calculator.internal.CalculationEngine;
~~~

compiler sẽ từ chối truy cập package chưa export, dù test module đã có **requires com.acme.calculator**.

Hai directive có vai trò khác nhau:

- **requires** tạo quan hệ readability tới module.
- **exports** công bố package để module khác truy cập kiểu public của package đó.

Không nên thêm **exports com.acme.calculator.internal;** chỉ để giúp test biên dịch, bởi điều đó biến implementation package thành API công khai cho mọi module đọc module sản phẩm.

Nếu test thật sự cần truy cập một public class nội bộ, có thể cân nhắc **qualified exports** dành cho test module trong một cấu hình module có kiểm soát, hoặc tạm dùng **--add-exports** khi biên dịch/chạy. Tuy nhiên, cả hai phương án đều tạo sự phụ thuộc của test vào implementation. Nếu cần kiểm tra package-private, qualified exports không đủ vì access modifier vẫn có hiệu lực.

## 8. Khi nào dùng --patch-module thay vì named test module riêng?

Nếu mục tiêu test là kiểm tra class, method hoặc constructor **package-private** của production module, test module riêng không có quyền truy cập chỉ nhờ requires. Một cách kiểm thử truyền thống của Java modular là **patch test classes vào production module**.

Ví dụ ý tưởng:

~~~bash
java --module-path mods \
     --patch-module com.acme.calculator=build/patch-tests \
     -m com.acme.calculator/com.acme.calculator.tests.InternalTestRunner
~~~

Ví dụ trên chỉ minh họa cú pháp. Test runner muốn chạy thành công còn phải được biên dịch với đúng cấu hình patch, nằm trong output được patch và có dependencies phù hợp. Không thể chỉ chuyển một module test đã biên dịch hoàn chỉnh vào **--patch-module** rồi giả định descriptor của nó sẽ được sử dụng như một module mới.

Khi patch:

- Test classes được coi là một phần của module được patch.
- Test cùng package có thể truy cập thành viên package-private theo quy tắc Java tương ứng.
- Test không còn mô phỏng consumer named module độc lập.
- Module descriptor của production vẫn là descriptor điều khiển ranh giới module.
- Test framework có thể cần thêm readability và opens tại runtime.

Do đó, **named test module riêng** và **patch-module** phục vụ mục tiêu khác nhau. Nên ưu tiên test public API bằng consumer module riêng, còn patch test chỉ dùng khi có lý do kiểm tra implementation.

## 9. Kết hợp JUnit Jupiter với named test module

Trong dự án thực tế, JUnit 5/JUnit Jupiter thường được dùng để tổ chức test. Khi chạy dưới JPMS, cần phân biệt **module test**, **module của JUnit API**, **module dùng để discovery/execute tests** và **module thực hiện reflection**.

Ví dụ descriptor của test module khi dùng JUnit Jupiter:

~~~java
module com.acme.calculator.tests {
    requires com.acme.calculator;
    requires org.junit.jupiter.api;

    opens com.acme.calculator.tests to org.junit.platform.commons;
}
~~~

Giải thích:

- **requires com.acme.calculator** cho phép test truy cập public API của production module.
- **requires org.junit.jupiter.api** cho phép compiler nhận diện annotation **@Test** và các assertion của JUnit Jupiter API.
- **opens com.acme.calculator.tests to org.junit.platform.commons** cho phép thành phần reflection tương ứng của JUnit Platform truy cập test classes/methods khi cần.

Tên module JUnit và chi tiết reflection có thể phụ thuộc vào artifact/phiên bản JUnit thực tế được dùng; cần kiểm tra bằng **jar --describe-module** trên các JAR đã resolve. Với một số runner hoặc extension, có thể cần mở package cho module thực hiện reflection tương ứng. Không mở toàn bộ production module chỉ vì test framework cần truy cập test methods.

Test class:

~~~java
package com.acme.calculator.tests;

import com.acme.calculator.api.Calculator;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {
    private final Calculator calculator = new Calculator();

    @Test
    void addsTwoNumbers() {
        assertEquals(5, calculator.add(2, 3));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(
            ArithmeticException.class,
            () -> calculator.add(Integer.MAX_VALUE, 1)
        );
    }
}
~~~

Trong JUnit Jupiter, test class và test method có thể không public. Nhưng ở named module, việc test runner dùng reflection vào test package phải đáp ứng **opens** thích hợp. Annotation **@Test** có thể biên dịch thành công trong khi test discovery/execution thất bại do package chưa mở.

JUnit Platform cần một test engine thích hợp (ví dụ Jupiter engine), launcher hoặc runner tích hợp build tool. Chỉ thêm JUnit API vào module path chưa đủ để tự động chạy test; test engine và runtime configuration phải hoạt động đúng.

## 10. Vì sao test discovery có thể thất bại dù javac thành công?

Biên dịch và chạy test là hai giai đoạn khác nhau.

Khi biên dịch, named test module cần:

- Tìm module sản phẩm trong module path.
- Tìm module cung cấp JUnit annotations/assertions.
- Có **requires** đúng module name.
- Chỉ import kiểu được export cho test module.

Khi JUnit Platform chạy, cần thêm:

- Test module đã được resolve trong layer thích hợp.
- Test engine phù hợp được phát hiện và có mặt ở runtime.
- Test package được mở cho module reflection cần thiết.
- Test class/method được test framework khám phá đúng.
- Những module hỗ trợ extension/provider có mặt trong runtime configuration.

Ví dụ một lỗi **InaccessibleObjectException** thường liên quan **opens** chứ không phải thiếu **requires**. Một lỗi **FindException** cho module sản phẩm thường liên quan module path hoặc module name. Trường hợp JUnit không tìm thấy test có thể do test module chưa được resolve, selector sai, engine thiếu hoặc cấu hình test runner không nhìn thấy module đó.

Không sửa mọi lỗi test discovery bằng **--add-opens ALL-UNNAMED**. Hãy xác định test runner/framework chạy trong named module nào và package nào thực sự phải được mở.

## 11. Cấu hình Maven/Gradle cần lưu ý

Build tool có thể biên dịch production source và test source theo các chiến lược khác nhau. Chỉ bật một test plugin hoặc thêm file **module-info.java** trong thư mục test chưa chứng minh test đang chạy như named test module độc lập.

### Maven

Với Maven, **maven-surefire-plugin** và **maven-failsafe-plugin** cung cấp cơ chế chạy test. Một số cấu hình có thể đưa tests lên module path hoặc patch tests vào module sản phẩm tùy phiên bản plugin và dự án.

Ví dụ phần cấu hình cho test runner dùng module path:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <useModulePath>true</useModulePath>
  </configuration>
</plugin>
~~~

Ví dụ chỉ minh họa tùy chọn; dự án cần cố định phiên bản plugin theo chính sách và kiểm tra output thực tế. **useModulePath=true** không tự bảo đảm test code là một named test module riêng; cần xác nhận test descriptor, compile output và cách Surefire chạy tests trong cấu hình cụ thể.

### Gradle

Với Gradle, task **Test** có thể dùng JUnit Platform:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Một cấu hình khác có thể cho Gradle suy luận module path khi có descriptor:

~~~groovy
java {
    modularity.inferModulePath = true
}
~~~

Tuy nhiên, các đoạn này chưa đủ để định nghĩa một named test module riêng nếu sourceSet và đường dẫn module output chưa được tổ chức tương ứng. Cần xác định plugin, source roots, module-info.java của test và JVM arguments do task thực sự tạo ra.

Trong cả Maven và Gradle, hãy ghi nhận:

1. Test sources được biên dịch thành named module riêng hay được patch vào production module?
2. Test runtime có chứa đầy đủ JUnit API, engine và launcher không?
3. Runner có chọn đúng test module và test classes không?
4. Package test có được mở cho framework reflection không?
5. Script CI có dùng cùng cấu hình như máy phát triển không?

Không suy luận kết quả từ mỗi tên task **test**. Dùng log build và thông tin module/class loader ở runtime để xác nhận cách test thực sự chạy.

## 12. Test module có nên export package test?

Thông thường, một named test module **không cần exports** package chứa test classes. Test runner không nên phải import test implementation như một API Java thông thường; nó có thể cần reflection, khi đó **opens** có giới hạn là hướng cấu hình phù hợp.

Ví dụ descriptor tối giản:

~~~java
module com.acme.calculator.tests {
    requires com.acme.calculator;
    requires org.junit.jupiter.api;
    opens com.acme.calculator.tests to org.junit.platform.commons;
}
~~~

Ở đây, package **com.acme.calculator.tests** không được export như API public. **opens** chỉ cho phép deep reflection tại runtime từ module đã chỉ định.

Nếu một module test utility khác cần dùng helper class public, có thể tách helper đó thành một **test fixtures module** riêng với exports rõ ràng thay vì export toàn bộ test package. Điều này giúp giữ contract kiểm thử dùng chung ổn định và tránh phụ thuộc vòng giữa các test modules.

Trong nhiều hệ thống, test code chỉ cần chạy, không cần module khác import các test classes của nó. Vì vậy, hãy bắt đầu với exports rỗng và bổ sung quyền khi thật sự có consumer hợp lệ.

## 13. Test fixtures và dependency dùng chung

Khi nhiều named test modules cùng cần fake data, builders hoặc mock implementations, nên cân nhắc tạo một module hỗ trợ kiểm thử riêng, ví dụ:

~~~java
module com.acme.test.fixtures {
    requires com.acme.calculator;
    exports com.acme.test.fixtures.api;
}
~~~

Module test có thể đọc fixtures:

~~~java
module com.acme.calculator.tests {
    requires com.acme.calculator;
    requires com.acme.test.fixtures;
}
~~~

Nguyên tắc tổ chức:

- Test fixtures là dependency phục vụ test, không phải dependency runtime của sản phẩm.
- Chỉ export helper API mà nhiều test modules thực sự cần.
- Không đưa thư viện mock/test framework vào production module nếu không có yêu cầu nghiệp vụ.
- Nếu test fixtures cần đọc một module API, ghi **requires** rõ ràng.
- Tránh dùng helper có thể sửa trạng thái global theo cách làm test phụ thuộc thứ tự chạy.
- Đảm bảo fixtures không đóng gói lại một bản sao service API, gây khác class identity khi test nhiều layer.

Một named test module có thể cần nhiều dependency hơn production module, nhưng module graph của test nên vẫn dễ đọc và có phạm vi rõ ràng.

## 14. Kiểm thử service provider bằng named test module

Một trường hợp ứng dụng JPMS thường gặp là dùng **ServiceLoader**. Named test module có thể kiểm tra rằng service provider module thực sự được resolve và tìm thấy theo service contract.

Giả sử API module chứa interface:

~~~java
module com.acme.codec.spi {
    exports com.acme.codec.spi;
}
~~~

Provider module:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.spi;

    provides com.acme.codec.spi.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

Test module:

~~~java
module com.acme.codec.tests {
    requires com.acme.codec.spi;
    uses com.acme.codec.spi.Codec;
}
~~~

Test code:

~~~java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

boolean found = loader.stream().findAny().isPresent();
if (!found) {
    throw new AssertionError("No codec provider found");
}
~~~

Cần bảo đảm provider module đã được resolve vào layer phù hợp. Một provider JAR chỉ nằm trên module path chưa chắc được đưa vào resolved graph. Trong test launcher, có thể dùng **--add-modules com.acme.codec.json** để bổ sung provider làm root hoặc dùng cơ chế service binding phù hợp.

Với custom ModuleLayer, có thể dùng **ServiceLoader.load(layer, Codec.class)** để tìm provider trong layer được chọn. Test module cần chia sẻ cùng service API identity với provider; không đóng gói nhiều bản sao của API vào các plugin layers.

Bộ test này giúp kiểm tra cấu hình module thật chứ không chỉ gọi trực tiếp constructor của một implementation class.

## 15. Kiểm thử exports và encapsulation

Named test module đặc biệt hữu ích để xác nhận module boundary đúng như thiết kế.

### Test dương tính

Viết một test module consumer import kiểu public từ package đã export:

~~~java
import com.acme.calculator.api.Calculator;
~~~

Nếu test compile và chạy thành công, điều này xác nhận ít nhất đường truy cập được sử dụng phù hợp với module descriptor và runtime graph.

### Test âm tính

Thử biên dịch một nguồn riêng cố import kiểu từ package không export:

~~~java
import com.acme.calculator.internal.CalculationEngine;
~~~

Compiler nên từ chối truy cập khi không có qualified export hoặc escape hatch. Test âm tính kiểu này thường phải được tổ chức thành một bước kiểm thử compilation có kiểm soát và kỳ vọng thất bại, không đưa trực tiếp vào source set test thông thường vì nó sẽ làm cả build fail.

Cần phân biệt:

- Test kiểm tra **exports**: import và truy cập kiểu public giữa các named modules.
- Test kiểm tra **opens**: framework reflection từ module phù hợp.
- Test kiểm tra **readability**: cần **requires** để đọc module dependency.
- Test kiểm tra **package-private**: chỉ code cùng package và cùng điều kiện module/class loader thích hợp mới có thể truy cập.

Các test này có thể đi cùng nhau nhưng không nên gộp mọi lỗi thành “module không chạy được”.

## 16. Kiểm thử reflection từ framework

Với framework ORM hoặc JSON serialization, có thể có tình huống test chỉ pass khi module sản phẩm mở package model cho framework.

Ví dụ descriptor sản phẩm:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    opens com.acme.customer.model to com.acme.json;
}
~~~

Named test module consumer có thể gọi public API và kiểm chứng framework xử lý model như mong đợi. Tuy nhiên, module **com.acme.json** mới là module cần deep reflection; không nhất thiết phải mở package model cho test module chỉ vì test gọi chức năng.

Nếu một test thử dùng reflection trực tiếp từ **com.acme.customer.tests**, quyền mở package cần được xem xét riêng cho module test, và điều đó có thể khác với cấu hình production. Tránh kết luận rằng production đã hỗ trợ framework chỉ vì test runner dùng **--add-opens ...=ALL-UNNAMED** và test pass.

Khi lỗi reflection xảy ra:

1. Đọc exception để xác định source module/package và target module.
2. Kiểm tra module sở hữu package có **opens** phù hợp không.
3. Kiểm tra framework/test runner có module name gì.
4. Chỉ dùng **--add-opens** như escape hatch có phạm vi rõ khi không sửa descriptor được.
5. Chạy lại test dưới cấu hình module dự kiến dùng tại production.

Named test module giúp lộ những khác biệt giữa quyền được khai báo và quyền đang được cấp bởi VM options.

## 17. Tránh split package giữa production và test module

Một lỗi hay gặp khi tổ chức source là để test class cùng package với class production rồi đưa chúng thành **hai named modules khác nhau**.

Ví dụ:

~~~text
production module:
  com.acme.calculator.internal.Engine

test module:
  com.acme.calculator.internal.EngineTest
~~~

Cả hai module chứa package **com.acme.calculator.internal**. Đây là **split package**, có thể gây xung đột khi resolve hoặc định nghĩa layer, tùy exports/readability và cách class loader ánh xạ module.

Không nên giữ cấu trúc đó rồi chỉ đổi class loader theo kiểu trial-and-error. Có hai lựa chọn rõ ràng:

- Với **named test module riêng**, đặt test classes trong package riêng như **com.acme.calculator.tests** và chỉ kiểm tra API mà module cho phép.
- Với **test cần cùng package** để truy cập package-private, dùng chiến lược patch tests vào module sản phẩm trong một test build tách biệt, thay vì định nghĩa một named test module thứ hai cùng package.

Dù có thể dùng nhiều loader trong một số cấu hình, đó không phải lý do thiết kế split package làm mặc định. Package ownership rõ ràng giúp test module dễ build, dễ debug và ít phụ thuộc vào chi tiết launcher.

## 18. Kiểm tra runtime module identity trong test

Khi nghi ngờ test chạy trên classpath thay vì module path, hãy kiểm tra bằng **Class.getModule()**:

~~~java
Module testModule = CalculatorTestMain.class.getModule();
Module productionModule = Calculator.class.getModule();

System.out.println("Test named: " + testModule.isNamed());
System.out.println("Test module: " + testModule.getName());
System.out.println("Production module: " + productionModule.getName());
System.out.println("Same module: " + (testModule == productionModule));
~~~

Trong ví dụ test module riêng, kỳ vọng:

~~~text
Test named: true
Test module: com.acme.calculator.tests
Production module: com.acme.calculator
Same module: false
~~~

Nếu testModule.isNamed() trả về false, test class đang ở unnamed module trong runtime context được quan sát. Nếu hai module object bằng nhau, có thể test class đã được patch vào production module hoặc được định nghĩa theo cấu hình khác với mong đợi.

Để điều tra sâu hơn, in:

~~~java
System.out.println(testModule.getLayer());
System.out.println(testModule.getClassLoader());
System.out.println(productionModule.getLayer());
System.out.println(productionModule.getClassLoader());
~~~

Module name là thông tin cần thiết, nhưng class loader và layer cũng quan trọng trong kiến trúc có nhiều layers. Không kết luận rằng hai class thuộc cùng runtime module chỉ vì chúng có prefix package giống nhau.

## 19. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| **Module com.acme.calculator not found** | Test module path thiếu production module | Xác nhận output/module path khi biên dịch và chạy |
| Compiler báo package không visible | Production package chưa export cho test module | Kiểm tra descriptor; test qua public API hoặc cân nhắc qualified export có kiểm soát |
| Test import package-private thất bại | Test ở module khác và không có quyền ở cấp Java | Đổi sang test public API hoặc tổ chức patch-module |
| JUnit phát hiện 0 tests | Runner không scan test module, engine thiếu hoặc selector sai | Kiểm tra JUnit Platform runtime, module roots và test discovery |
| **InaccessibleObjectException** khi chạy JUnit | Test package hoặc production package chưa mở cho module reflection tương ứng | Kiểm tra opens đúng module thực hiện reflection |
| Named test module bị coi là unnamed | Test classes được đưa lên classpath | Kiểm tra cách build tool đặt output lên module path |
| **ResolutionException** do package conflict | Split package hoặc exports conflict trong graph | Tách test package hoặc điều chỉnh cấu trúc module |
| ServiceLoader không thấy provider | Provider module chưa được resolve hoặc uses/provides sai | Kiểm tra descriptor, layer và service binding |
| Test pass trong IDE nhưng fail trên CI | IDE và CI dùng khác module path, VM options hoặc engine | So sánh Java command và runtime image thực tế |
| Test code xuất hiện trong release JAR | Build artifact lẫn test output vào production | Tách output và kiểm tra nội dung JAR phát hành |

Các lỗi này có thể xảy ra ở những giai đoạn khác nhau: javac compile, module resolution khi startup, layer definition, test discovery hoặc runtime invocation. Đọc chính xác loại exception và module/package được nêu trước khi chọn hướng sửa.

## 20. Quy trình triển khai trong dự án

Một lộ trình thực tế cho dự án đang chuyển sang JPMS:

1. **Xác định mục tiêu test:** public API, integration, module boundary hay implementation internals.
2. **Tạo module sản phẩm có descriptor rõ ràng:** công bố package API bằng exports.
3. **Tạo source root test riêng:** đặt module-info.java với module name có hậu tố tests.
4. **Khai báo test dependency:** requires production module và những test API module cần thiết.
5. **Biên dịch theo thứ tự:** production output trước, test module với production trên module path sau.
6. **Chọn runner:** một main test runner đơn giản hoặc JUnit Platform engine/launcher.
7. **Mở test package nếu cần:** qualified opens dành cho reflection do framework thực hiện.
8. **Chạy như named module:** xác nhận Class.getModule().isNamed() và module name thực tế.
9. **Kiểm thử module boundary:** import các exported API và tổ chức negative compile tests nếu cần.
10. **Tách integration tests:** có thể tạo module riêng cho test end-to-end, service hoặc plugin layers.
11. **Kiểm soát artifact:** không đưa test module/classes/framework dependencies vào production JAR trừ trường hợp có chủ đích rõ.
12. **Đồng bộ CI:** thực hiện cùng JDK/module-path/VM options trên máy phát triển và pipeline.
13. **Ghi nhận trường hợp patch-module:** giải thích vì sao test cần truy cập nội bộ và điều kiện loại bỏ cấu hình này.

Nếu dự án chưa tổ chức build cho named test module riêng, nên bắt đầu bằng ví dụ không dùng framework ở phần 4–6. Khi module name, requires và runtime path đã hoạt động, mới tích hợp JUnit để tách lỗi JPMS với lỗi discovery/reflection của framework.

## 21. Bài tập thực hành

1. Tạo **com.acme.calculator** với một package API export và một package internal không export.
2. Tạo **com.acme.calculator.tests** có **requires com.acme.calculator**.
3. Viết một **CalculatorTestMain** kiểm tra kết quả và lỗi overflow bằng AssertionError.
4. Biên dịch production module rồi test module bằng **--module-source-path** và **--module-path**.
5. Chạy test module bằng **java -m**, xác nhận main method thực thi và exit status đúng.
6. Xóa production module khỏi module path lúc chạy, quan sát thông báo thiếu module.
7. Thử import public class từ package không export và quan sát lỗi compiler.
8. Thử đặt test class vào cùng package internal của production trong named module riêng, điều tra split-package issue.
9. Chuyển test sang JUnit Jupiter, khai báo **requires org.junit.jupiter.api** và opens test package cho framework phù hợp.
10. Kiểm tra test engine/launcher có resolve đúng module test không, và test discovery tìm được các method.
11. Tạo test module khác chỉ kiểm tra public API để so sánh với patch-module test.
12. Thêm một provider module và viết integration test dùng ServiceLoader, xác nhận provider đã được resolve.
13. In Module object, name, layer và loader của test và production class.
14. Kiểm tra production JAR không chứa test classes hoặc dependency JUnit.
15. Chạy test trong CI với đúng launcher flags và JDK mục tiêu.

## 22. Những điều cần ghi nhớ

- **Named test module** là module có descriptor và tên riêng, thường khai báo **requires** tới production module.
- Nó kiểm tra production API dưới module boundary tương tự consumer modular thật.
- **requires** không cho phép truy cập package chưa export; package-private vẫn chịu access rules của Java.
- **--patch-module** phục vụ test code cần được xem là một phần của production module; khác với test module riêng.
- Test package nên tách namespace với package của production để tránh split package.
- JUnit Jupiter test module có thể cần **requires org.junit.jupiter.api** và qualified **opens** cho module reflection của JUnit Platform.
- Test engine/launcher phải có mặt và được cấu hình; chỉ biên dịch test annotations chưa đủ để chạy tests.
- Build tool có thể chạy test trên classpath, module path hoặc patch-module; cần xác minh runtime thực tế.
- Service integration tests cần đúng provider resolution và cùng service API identity.
- Module API nên được kiểm tra qua exported packages trước; test internal implementation chỉ khi có lý do rõ.
- Production artifacts không nên chứa test classes hoặc test framework dependencies.
- Khi debug, phân biệt lỗi compiler, module resolution, layer instantiation, reflection và test discovery.

**Named test module giúp test trở thành một consumer JPMS thực sự.** Dùng nó khi muốn xác nhận module descriptor và API boundary hoạt động đúng với ứng dụng bên ngoài; phối hợp với patch-module một cách có chủ đích khi cần kiểm thử implementation nội bộ.