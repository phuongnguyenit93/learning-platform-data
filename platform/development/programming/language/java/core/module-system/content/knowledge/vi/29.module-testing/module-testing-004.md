# JUnit trên module path

Khi một ứng dụng Java sử dụng Java Platform Module System (JPMS), việc chạy unit test bằng JUnit cần quan tâm đến nhiều yếu tố hơn so với cách truyền thống trên classpath: **named module**, `requires`, `exports`, `opens`, class loader và cách JUnit Platform tìm kiếm test engine. Một bài test chạy tốt trên classpath có thể không biên dịch hoặc không được khám phá khi cùng bytecode được chuyển sang module path.

Điểm cốt lõi: **JUnit là một framework sử dụng reflection**, trong khi JPMS thiết lập ranh giới truy cập giữa các module. Để kiểm thử hiệu quả mà vẫn giữ encapsulation của mã production, cần lựa chọn rõ một trong hai chiến lược: **test nằm trong một named module độc lập** hoặc **test được patch vào module đang kiểm thử**.

Bài học này hướng dẫn cấu trúc source, các module JUnit liên quan, ví dụ test JUnit Jupiter, cấu hình Maven/Gradle, chạy JUnit Platform Console và xử lý lỗi thường gặp.

## 1. Vì sao JUnit trên module path khác classpath?

Trên classpath thông thường, test source có thể import JUnit API và một class khác mà không có module descriptor:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class BasicTest {
    @Test
    void addition() {
        assertEquals(5, 2 + 3);
    }
}
```

Các class trên classpath thuộc unnamed module tương ứng với class loader. Build tool chuẩn bị JUnit dependency, phát hiện bài test và thực thi thông qua JUnit Platform.

Với named modules, Java còn phải trả lời các câu hỏi:

1. Module chứa test có **đọc được** module `org.junit.jupiter.api` không?
2. Module chứa test có đọc được **module sản phẩm** đang được kiểm thử không?
3. Package API của sản phẩm có được `exports` cho module test không?
4. Package chứa test class/method có được `opens` cho module thực hiện reflection không?
5. JUnit Jupiter **TestEngine** đã được phân giải vào module graph chưa?
6. JUnit Platform launcher có tìm và chọn đúng test classes không?
7. Những class test nằm trong cùng package với production classes có gây split package khi đặt ở một test module khác không?

Những vấn đề này phát sinh từ module boundaries, không phải do assertion của JUnit thay đổi.

## 2. Thành phần JUnit cần phân biệt

JUnit 5 tổ chức runtime thành **JUnit Platform**, **JUnit Jupiter** và **JUnit Vintage**. Trong môi trường JPMS, các artifact tương ứng có thể được nhận diện bằng những module name khác nhau:

| Thành phần | Module name thường gặp | Vai trò |
|---|---|---|
| JUnit Jupiter API | `org.junit.jupiter.api` | `@Test`, lifecycle annotations, assertions |
| JUnit Jupiter Engine | `org.junit.jupiter.engine` | Khám phá và chạy Jupiter tests |
| JUnit Platform Commons | `org.junit.platform.commons` | Tiện ích nội bộ cho engine và reflection |
| JUnit Platform Engine | `org.junit.platform.engine` | Giao diện TestEngine và discovery |
| JUnit Platform Launcher | `org.junit.platform.launcher` | Điều phối các test engines |
| JUnit Platform Console | `org.junit.platform.console` | Chạy test qua command line |
| JUnit Vintage Engine | `org.junit.vintage.engine` | Chạy các JUnit 3/4 tests qua Platform |

Đây là ví dụ theo hệ module JUnit phổ biến; bộ JUnit thực tế phải có các artifact tương thích. Một module name cần được xác nhận từ JAR đang sử dụng:

```shell
jar --describe-module --file lib/junit-jupiter-api.jar
```

Đường dẫn file ở đây chỉ minh họa. Đối với một JAR có tên kèm phiên bản, hãy truyền đúng đường dẫn thực tế.

**Jupiter API không phải Jupiter Engine.** Code có thể biên dịch được vì API tồn tại nhưng launcher không chạy được test nếu engine chưa có hoặc chưa được phân giải. Ngược lại, có engine trong thư mục `lib` cũng không bảo đảm engine sẽ được đưa vào configuration nếu cách khởi động không làm nó trở thành root hoặc dependency/service provider được chọn.

## 3. Hai mô hình kiểm thử module

### 3.1. Test là một named module riêng

Ví dụ:

```text
com.example.math
      ↑
      │ requires
com.example.math.tests
      │
      └── requires org.junit.jupiter.api
```

Test module khai báo trực tiếp dependency tới module sản phẩm và JUnit API. Test sử dụng package API được export, giống như một ứng dụng khách bình thường.

Ưu điểm:

- Kiểm tra được hợp đồng API công khai từ góc nhìn module bên ngoài.
- Module test có descriptor riêng, dễ mô tả dependency.
- Không cần thay đổi hoặc patch nội dung module production.
- Phù hợp với API tests và nhiều integration tests.

Giới hạn:

- Không import được package nội bộ chưa export.
- Không truy cập được package-private member của module khác.
- Test package vẫn cần mở cho JUnit reflection khi cần.
- Cấu hình module path và discovery phải đầy đủ.

### 3.2. Test được patch vào module production

Với `--patch-module`, compiler và runtime coi những test classes nhất định là phần bổ sung của module sản phẩm. Điều này hữu ích nếu unit test cần truy cập package-private code trong cùng package.

Ưu điểm:

- Giữ mô hình unit test nội bộ giống cách test classpath truyền thống.
- Có thể truy cập thành viên package-private trong cùng module/package.
- Không phải export implementation package chỉ để test.

Giới hạn:

- Cần khai báo quyền đọc JUnit riêng cho bước test bằng `--add-reads`.
- Reflection có thể cần `--add-opens`.
- Cần bảo đảm test patch chỉ dùng trong cấu hình test, không bị đóng gói vào production JAR.

Hai chiến lược không loại trừ nhau: một dự án có thể patch unit tests và chạy API/integration tests bằng test module riêng.

## 4. Ví dụ module sản phẩm

Giả sử có module `com.example.math` với package API đã export:

```text
src/main/java/
├── module-info.java
└── com/example/math/api/
    └── Calculator.java
```

Descriptor:

```java
module com.example.math {
    exports com.example.math.api;
}
```

Class:

```java
package com.example.math.api;

public final class Calculator {
    public int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public int divide(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("Divisor must not be zero");
        }
        return a / b;
    }
}
```

Package API được export nên module khác có thể sử dụng public class `Calculator` nếu có readability tới `com.example.math`.

Để kiểm thử hành vi chỉ qua public contract, hãy dùng test module riêng. Nếu cần kiểm tra một class `com.example.math.internal.MathHelper` không export, hãy cân nhắc patch test vào cùng module, thay vì mở toàn bộ implementation ra bên ngoài.

## 5. Cách A: named test module độc lập

Một cấu trúc source minh họa:

```text
project/
├── src/main/java/
│   ├── module-info.java
│   └── com/example/math/api/Calculator.java
└── src/test-modules/
    └── com.example.math.tests/
        ├── module-info.java
        └── com/example/math/tests/CalculatorTest.java
```

Descriptor của test module:

```java
module com.example.math.tests {
    requires com.example.math;
    requires org.junit.jupiter.api;

    opens com.example.math.tests to org.junit.platform.commons;
}
```

Giải thích:

- `requires com.example.math` để test đọc module sản phẩm.
- `requires org.junit.jupiter.api` để dùng annotation và Assertions.
- `opens com.example.math.tests to org.junit.platform.commons` để reflection trong JUnit Platform có thể truy cập những test class/method không public theo nhu cầu.

Nếu các extensions hoặc framework khác cần reflection, có thể phải mở package cho module tương ứng. Nên xác định module thực hiện reflection từ stack trace thay vì mở toàn bộ module không cần thiết.

Test:

```java
package com.example.math.tests;

import com.example.math.api.Calculator;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {
    private final Calculator calculator = new Calculator();

    @Test
    void addReturnsSum() {
        assertEquals(9, calculator.add(4, 5));
    }

    @Test
    void divisionRejectsZero() {
        assertThrows(
            IllegalArgumentException.class,
            () -> calculator.divide(10, 0)
        );
    }
}
```

JUnit Jupiter cho phép test class và test method không public trong trường hợp thông thường. Nhưng quyền reflection xuyên ranh giới named module vẫn phải phù hợp với `opens` hoặc runtime flags.

## 6. Biên dịch module sản phẩm và test module

Một chuỗi lệnh minh họa trên Linux/macOS (điều chỉnh đường dẫn và shell trên Windows):

Biên dịch production module:

```shell
javac -d out/main     src/main/java/module-info.java     src/main/java/com/example/math/api/Calculator.java
```

Đóng gói thành modular JAR:

```shell
mkdir -p mods
jar --create --file mods/com.example.math.jar -C out/main .
```

Giả sử `lib` là thư mục chứa các JUnit JAR và các dependency tương thích. Biên dịch test module:

```shell
javac --module-path "mods:lib"     -d out/test/com.example.math.tests     src/test-modules/com.example.math.tests/module-info.java     src/test-modules/com.example.math.tests/com/example/math/tests/CalculatorTest.java
```

Sau khi biên dịch, thư mục `out/test/com.example.math.tests` là exploded named module với `module-info.class` và các test classes. Có thể dùng nó làm một phần tử của module path.

Lưu ý:

- `--module-path` khác `--class-path`. Với module path, hãy dùng thư mục chứa các modular JAR hoặc đường dẫn JAR cụ thể, không giả định cú pháp `lib/*` có ý nghĩa giống wildcard classpath.
- Trên Windows, phần tử trong danh sách path được phân cách bằng `;`, không phải `:`.
- Không đưa test module vào production image chỉ vì nó cần cho test.
- Nếu test module phụ thuộc vào module khác, chúng phải được tìm thấy trong runtime image hoặc trên module path phù hợp.

## 7. Chạy named test module với JUnit Platform Console

Một cách chạy trực tiếp bằng JUnit Platform Console (với phiên bản hỗ trợ subcommand `execute`) là:

```shell
java --module-path "mods:lib:out/test/com.example.math.tests"     --add-modules com.example.math.tests,org.junit.jupiter.engine     --module org.junit.platform.console/org.junit.platform.console.ConsoleLauncher     execute --select-module com.example.math.tests
```

Ý nghĩa:

1. `mods` chứa module sản phẩm.
2. `lib` chứa JUnit Platform, Jupiter Engine và các dependency tương thích.
3. `out/test/com.example.math.tests` là exploded test module.
4. `--add-modules` bảo đảm test module và Jupiter Engine được chọn vào graph.
5. `--module` khởi động ConsoleLauncher.
6. `--select-module` yêu cầu JUnit Platform chọn test module đích.

Cú pháp ConsoleLauncher thay đổi theo phiên bản. Kiểm tra trợ giúp của phiên bản đang cài:

```shell
java --module-path "lib"     -m org.junit.platform.console/org.junit.platform.console.ConsoleLauncher     --help
```

Với phiên bản có lệnh con `execute`, có thể xem trợ giúp của chính subcommand đó. Không áp đặt một command-line fragment cho mọi release của JUnit.

JUnit Platform tìm TestEngine thông qua service provider mechanism. Nếu Engine JAR ở một vị trí nhưng module chưa được phân giải, launcher có thể không tìm được Jupiter Engine. Vì vậy, khi chạy thủ công trên module path, kiểm tra cả tập root modules lẫn cơ chế service binding.

## 8. Cách B: test trong cùng module bằng --patch-module

Giả sử module sản phẩm còn một package implementation:

```text
src/main/java/
└── com/example/math/internal/MathHelper.java

src/test/java/
└── com/example/math/internal/MathHelperTest.java
```

Class nội bộ:

```java
package com.example.math.internal;

final class MathHelper {
    static int square(int value) {
        return value * value;
    }
}
```

Unit test cùng package:

```java
package com.example.math.internal;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MathHelperTest {
    @Test
    void computesSquare() {
        assertEquals(36, MathHelper.square(6));
    }
}
```

Nếu test được biên dịch thành một module khác, package `com.example.math.internal` không được export, và class `MathHelper` không public, nên test không thể truy cập nó trực tiếp.

Trong mô hình `--patch-module`, test class được đưa vào cùng named module `com.example.math`. Khi đó, test cùng package có thể sử dụng package-private class/method như trong một compilation unit thông thường.

## 9. Biên dịch test bằng --patch-module và --add-reads

Giả sử module sản phẩm đã được biên dịch và `mods` chứa modular JAR của nó:

```shell
javac --module-path "mods:lib"     --add-modules org.junit.jupiter.api     --patch-module com.example.math=src/test/java     --add-reads com.example.math=org.junit.jupiter.api     -d out/test-patch     src/test/java/com/example/math/internal/MathHelperTest.java
```

Các flags:

- `--patch-module`: cho compiler coi test sources là phần bổ sung của module sản phẩm.
- `--add-modules`: đảm bảo module JUnit API có thể tham gia compilation graph.
- `--add-reads`: cho `com.example.math` đọc `org.junit.jupiter.api` trong riêng cấu hình biên dịch test.
- `-d`: thư mục chứa test class file sau khi biên dịch.

Tại sao phải có `--add-reads`? Vì production module descriptor không chứa:

```java
requires org.junit.jupiter.api;
```

Và đó là điều bình thường. JUnit là dependency của test, không phải một phần contract của module production. Sửa production descriptor để thêm JUnit chỉ nhằm biên dịch test thường không phải giải pháp phù hợp.

Một số build tool tự tạo các flags tương đương khi nhận ra modular test project. Nếu tự chạy javac, phải giữ nhất quán giữa các tham số compiler và runtime.

## 10. Chạy patch tests với JUnit Platform

Ở runtime, lớp test đã biên dịch cần được patch vào module sản phẩm. Đồng thời, module sản phẩm phải đọc JUnit API và package chứa test phải cho phép reflection.

Lệnh minh họa:

```shell
java --module-path "mods:lib"     --patch-module com.example.math=out/test-patch     --add-modules com.example.math,org.junit.jupiter.api,org.junit.jupiter.engine     --add-reads com.example.math=org.junit.jupiter.api     --add-opens com.example.math/com.example.math.internal=org.junit.platform.commons     --module org.junit.platform.console/org.junit.platform.console.ConsoleLauncher     execute --select-package com.example.math.internal
```

Giải thích:

- Test class được patch vào `com.example.math`.
- `--add-reads` cấp readability test-only tới JUnit API.
- `--add-opens` mở package test cho thành phần reflection.
- `--add-modules` thêm các module test runtime cần được phân giải.
- JUnit Platform Console chọn package test cần chạy.

Với một số phiên bản ConsoleLauncher hoặc chiến lược test discovery, có thể cần cách lựa chọn test module hoặc test class khác. Tài liệu và flags thực tế phải phù hợp phiên bản JUnit đang dùng.

**Không đưa `--patch-module`, `--add-reads` và `--add-opens` test-only vào lệnh khởi động production**. Những tùy chọn này thuộc test runtime.

## 11. Khi nào cần requires, add-reads và add-modules?

Ba cơ chế này giải quyết các vấn đề khác nhau.

### requires trong module-info.java

```java
module com.example.math.tests {
    requires com.example.math;
    requires org.junit.jupiter.api;
}
```

Đây là dependency cố định của named test module riêng. Nó được compiler và resolver dùng để thiết lập readability.

### --add-reads

```text
--add-reads com.example.math=org.junit.jupiter.api
```

Bổ sung một quan hệ đọc cho một lần biên dịch/chạy mà không sửa module descriptor. Thường gặp trong test patch.

### --add-modules

```text
--add-modules org.junit.jupiter.engine
```

Bổ sung root module cần được resolution chọn. Nó không tự tạo readability tùy ý giữa mọi module và không export package.

Nếu JUnit API module đã nằm trên module path nhưng test module không đọc nó, thêm `--add-modules` chưa chắc giải quyết được lỗi import. Nếu test module có requires đúng nhưng API module không tìm thấy, cần sửa module path hoặc dependency artifact trước.

## 12. Khi nào cần opens và add-opens?

JUnit Jupiter thường chạy test thông qua reflection. Package chứa class test cần cho phép reflection phù hợp với nơi JUnit Platform thực hiện lời gọi.

Với test module riêng:

```java
module com.example.math.tests {
    requires com.example.math;
    requires org.junit.jupiter.api;
    opens com.example.math.tests to org.junit.platform.commons;
}
```

Với patch tests:

```text
--add-opens com.example.math/com.example.math.internal=org.junit.platform.commons
```

Điểm phân biệt:

- `exports`: mở quyền truy cập API Java thông thường tới public types.
- `opens`: cho phép deep reflection trong một package.
- `--add-exports`: bổ sung quyền truy cập public types cho module cụ thể.
- `--add-opens`: bổ sung quyền deep reflection trong runtime.

Một package được export không mặc nhiên cho phép JUnit truy cập private/package-private test methods bằng reflection. Ngược lại, mở package cho reflection không có nghĩa code bên ngoài có thể import mọi kiểu nội bộ như API công khai.

Nếu lỗi reflection đến từ thư viện khác — ví dụ Mockito, ORM, JSON serializer hoặc một Jupiter extension — module đích của `opens` có thể khác `org.junit.platform.commons`. Xem stack trace và tên module thực tế để chọn phạm vi chính xác.

## 13. Maven Surefire với named modules

Maven Surefire Plugin hỗ trợ chạy test trong dự án JPMS. Ví dụ POM cấu hình JUnit Jupiter ở scope test:

```xml
<dependencies>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
  </dependency>
</dependencies>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.5.2</version>
      <configuration>
        <useModulePath>true</useModulePath>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Các phiên bản trên là ví dụ có thật, không phải yêu cầu bắt buộc. Hãy chọn JUnit/JDK/Surefire tương thích với toolchain dự án và thống nhất các artifact JUnit trong cùng release train.

Chạy:

```shell
mvn test
```

Để xem chi tiết command line, classpath/module path và các flags của Surefire:

```shell
mvn -X test
```

Khi test không tìm thấy hoặc bị lỗi module access, xem các thông tin:

1. Maven có nhận `module-info.java` của production không?
2. Test classes được patch vào module production hay chạy trên classpath?
3. JUnit API và Engine có nằm ở test runtime đúng vị trí không?
4. Có `--patch-module`, `--add-reads`, `--add-opens` nào được Maven tạo không?
5. JDK version của Maven và JDK chạy test có trùng nhau không?

Không chuyển dependency JUnit sang compile scope chỉ để né lỗi. Thông thường JUnit phải là test dependency.

## 14. Gradle và useJUnitPlatform()

Với Gradle Groovy DSL, một cấu hình minh họa:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

java {
    modularity.inferModulePath = true
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các thành phần:

- `testImplementation` chứa API và dependency phục vụ biên dịch test.
- `testRuntimeOnly` bổ sung thành phần runtime được build cần.
- `modularity.inferModulePath` để Gradle suy luận module path khi nhận diện module descriptor.
- `useJUnitPlatform()` chạy test qua JUnit Platform.

Chạy:

```shell
./gradlew test
```

Trên Windows, dùng `gradlew.bat test` nếu có Gradle Wrapper.

Không phải mọi phiên bản Gradle hoặc plugin tự động cấu hình cùng một chiến lược module patch. Nếu test source set đã được tổ chức thành một named test module riêng, có thể cần cấu hình module source path, compilation task và test runtime riêng. Hãy kiểm tra lệnh thực tế do Gradle tạo khi có lỗi.

## 15. JUnit 4, Vintage và migration

Một codebase lâu năm có thể chứa:

```java
import org.junit.Test;                  // JUnit 4
```

và:

```java
import org.junit.jupiter.api.Test;      // JUnit Jupiter
```

Hai annotation thuộc hai hệ test khác nhau. JUnit Platform có thể chạy JUnit 4 tests qua **Vintage Engine** khi dependency tương ứng được cung cấp, nhưng chỉ thêm Jupiter API không biến JUnit 4 tests thành Jupiter tests.

Khi kiểm kê test trước migration, nên ghi:

- Số lượng test JUnit 4 và Jupiter.
- Có JUnit Vintage Engine hay runner tùy chỉnh nào không?
- Có extensions, rules hoặc test framework tích hợp như Spring Test không?
- Những dependency nào thuộc compile-time và runtime của test.
- Module nào cần opens cho reflection.
- Có test suite cần classpath thay vì module path trong giai đoạn chuyển tiếp không?

Lộ trình thực tế có thể giữ một nhóm legacy tests trên classpath trong khi test mới được viết theo named modules, nhưng cần cấu hình CI rõ ràng để tránh “test biến mất” khỏi test report.

## 16. Kiểm tra module name của JUnit dependencies

Không nên đoán module name chỉ từ tên file hoặc artifact Maven. Kiểm tra từng artifact bằng:

```shell
jar --describe-module --file lib/junit-jupiter-api.jar
jar --describe-module --file lib/junit-jupiter-engine.jar
```

Đường dẫn cần thay bằng filename thật. Có thể xem module mà launcher có thể quan sát:

```shell
java --module-path "mods:lib" --list-modules
```

Tuy nhiên, `--list-modules` không chứng minh tất cả module sẽ được phân giải trong lần chạy test. Để xem quá trình resolution, sử dụng:

```shell
java --show-module-resolution     --module-path "mods:lib:out/test/com.example.math.tests"     --add-modules com.example.math.tests,org.junit.jupiter.engine     -m org.junit.platform.console/org.junit.platform.console.ConsoleLauncher     execute --select-module com.example.math.tests
```

Khi engine không được khám phá, có thể kiểm tra cả service provider declarations và module resolution. Test discovery là một giai đoạn riêng sau khi launcher khởi động thành công.

## 17. Lỗi module không đọc JUnit API

Một lỗi điển hình:

```text
module com.example.math does not read org.junit.jupiter.api
```

Nguyên nhân thường là test class được patch vào module production nhưng module production không có readability tới JUnit API.

Cách xử lý:

- Xác định test thực sự đang chạy trong module nào.
- Nếu test là named module riêng, thêm `requires org.junit.jupiter.api;` vào test module descriptor.
- Nếu test được patch vào production module, dùng `--add-reads com.example.math=org.junit.jupiter.api` trong cấu hình compile test và runtime khi cần.
- Bảo đảm artifact JUnit API nằm đúng module path và được phân giải.
- Không thêm JUnit vào descriptor production nếu nó không phải dependency runtime/contract thật của sản phẩm.

Nếu compiler báo `package org.junit.jupiter.api is not visible`, kiểm tra cả module path và readability. `--add-opens` không sửa được lỗi thiếu requires.

## 18. InaccessibleObjectException khi JUnit reflection

Một lỗi runtime có thể có dạng:

```text
java.lang.reflect.InaccessibleObjectException:
module com.example.math does not "opens com.example.math.internal"
to module org.junit.platform.commons
```

Tình huống này không liên quan trực tiếp tới việc JUnit API thiếu. Test class có thể đã được tìm thấy, nhưng JUnit không thể dùng reflection để gọi test method.

Cách khắc phục:

1. Với test module riêng, `opens` test package cho module thực hiện reflection.
2. Với patch test, thêm `--add-opens` đúng module/package/target ở runtime.
3. Kiểm tra xem exception đến từ JUnit Platform, Mockito, framework DI hay một extension khác.
4. Hạn chế mở package cần thiết, tránh dùng `open module` cho toàn bộ production module chỉ vì một test.

Với test phải truy cập private field của một module JDK, cần cân nhắc thay thiết kế test để dựa vào public API. Không nên mở tràn lan các JDK internals trong pipeline mặc định.

## 19. Lỗi No tests found

Khi launcher chạy nhưng không phát hiện test, có thể thấy thông báo:

```text
No tests found
```

Nguyên nhân có thể là:

- Test class chưa được compile, hoặc được compile vào thư mục không nằm trong patch/module path.
- Test module chưa được resolution.
- Jupiter Engine không có ở runtime hoặc không được JUnit Platform phát hiện.
- Selector chỉ nhầm package/module/class.
- Test mang annotation JUnit 4 nhưng chỉ có Jupiter Engine.
- Build tool có include/exclude pattern loại test khỏi discovery.
- Test suite sử dụng launcher phiên bản không phù hợp với flags được truyền.

Các bước nên thử:

1. Kiểm tra `.class` đã được tạo.
2. Kiểm tra tên module và module path.
3. Chọn một test class cụ thể thay vì scan toàn bộ runtime.
4. Kiểm tra JUnit Engine provider.
5. Bật log của build tool/launcher để xem discovery.
6. Kiểm tra module `opens` nếu discovery thấy class nhưng không thực thi được method.

Không nên chỉ thêm mọi JAR vào classpath để “cho chạy” rồi kết luận module path đã được cấu hình đúng. Điều đó thay đổi mô hình runtime đang kiểm thử.

## 20. Split package giữa test và production

Một lỗi đặc thù của JPMS xảy ra khi test module riêng chứa cùng package với module sản phẩm:

```text
com.example.math
└── com.example.math.internal

com.example.math.tests
└── com.example.math.internal
```

Từ góc nhìn module, cùng một tên package tồn tại trong hai named modules. Tùy readability, exports và chiến lược class loader, cấu hình này có thể bị từ chối hoặc gây vấn đề.

Nếu muốn test module độc lập, nên đặt test trong package riêng như:

```text
com.example.math.tests
```

và chỉ kiểm thử API được module sản phẩm export. Nếu muốn test cùng package để truy cập package-private, dùng `--patch-module` thay vì tạo một named test module khác sở hữu package trùng.

Thay module name không giải quyết package trùng; phải thay tổ chức package hoặc cách định nghĩa module test.

## 21. Resource và test fixtures trên module path

Ngoài Java class, test có thể cần:

- JSON/YAML/XML fixtures.
- SQL seed files.
- Properties và logging configuration.
- Service provider metadata.
- Test extensions được phát hiện bằng ServiceLoader.
- Resource được nạp bằng `Class.getResourceAsStream`.
- File được tìm qua thread context class loader.

Khi dùng JPMS, resource lookup có thể chịu ảnh hưởng module encapsulation và class loader. Một resource nằm trên disk chưa có nghĩa nó nằm trong module artifact hoặc module patch được dùng lúc chạy.

Với test patch, nên đảm bảo `src/test/resources` hoặc output tài nguyên được đưa vào patch path theo cấu hình build. Với test module riêng, resource cần nằm trong test module hoặc được truy cập bằng đường dẫn/classloader phù hợp.

Khi một fixture không tìm thấy, đừng sửa `opens` ngay. Hãy kiểm tra:

1. Resource có được copy vào build output không?
2. Resource được đặt trong module nào?
3. Code dùng `Class.getResourceAsStream`, `Module.getResourceAsStream` hay class loader?
4. Đường dẫn resource tuyệt đối/tương đối có đúng không?
5. Resource có bị encapsulation hoặc quyền mở package ảnh hưởng không?

## 22. JUnit và ServiceLoader trên module path

JUnit Platform dùng cơ chế service provider để phát hiện TestEngine. Điều này gợi nhớ JPMS service binding ở ứng dụng.

Ví dụ một ứng dụng riêng dùng service:

```java
module com.example.app {
    requires com.example.codec.api;
    uses com.example.codec.api.Codec;
}
```

Provider:

```java
module com.example.codec.json {
    requires com.example.codec.api;
    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

Muốn test sử dụng provider, module provider phải thực sự có mặt trong configuration/layer phù hợp. Chỉ đặt một JAR trong thư mục module path chưa chắc khiến nó trở thành module được phân giải.

Với JUnit, cũng cần phân biệt:

- API annotation/assertion: JUnit Jupiter API.
- Engine module: cung cấp implementation của TestEngine.
- Launcher: yêu cầu tìm engine qua service mechanism.
- Module resolution: quyết định module nào thực sự được chọn.
- Test discovery: quyết định test class nào được khám phá trong runtime graph.

Một lần build thành công chỉ xác nhận compilation. Không thể suy ra JUnit Platform đã phát hiện test engine và thực thi toàn bộ test suite.

## 23. API tests và internal unit tests

Hai lớp kiểm thử thường nên có mục tiêu khác nhau:

### API/integration tests

Test chỉ import những public types trong package được export. Nó đóng vai một consumer module thật:

```java
module com.example.math.tests {
    requires com.example.math;
    requires org.junit.jupiter.api;
    opens com.example.math.tests to org.junit.platform.commons;
}
```

Kiểu test này phát hiện các vấn đề mà test trong cùng module có thể không thấy, ví dụ quên `exports` một package API hoặc module consumer thiếu `requires`.

### Implementation unit tests

Test cần kiểm tra các hành vi package-private ở cùng package. Có thể patch vào production module:

```text
--patch-module com.example.math=out/test-patch
```

Kiểu test này thuận tiện cho logic nội bộ nhưng không thay thế hoàn toàn API tests. Vì test được chạy trong cùng module, nó có thể truy cập những kiểu mà consumer module không thể truy cập.

Khi thiết kế bộ test, nên giữ cả hai góc nhìn tùy độ phức tạp của hệ thống.

## 24. Quy trình migration từ classpath tests

Một kế hoạch chuyển đổi có thể thực hiện tuần tự:

1. Kiểm kê JUnit versions, runners, engines và extensions đang dùng.
2. Xác nhận phiên bản JDK mục tiêu và module name của các JUnit artifacts.
3. Kiểm tra descriptor và những package được export của production modules.
4. Phân loại test: public API/integration hay internal/package-private unit test.
5. Tạo named test module cho các bài cần kiểm tra module boundary.
6. Dùng patch-module cho các bài cần truy cập implementation nội bộ.
7. Giữ JUnit dependency trong test scope.
8. Cấu hình readability và opens tối thiểu cần thiết.
9. Cấu hình test engine và launcher trên đúng module path.
10. Chạy một bài nhỏ, quan sát test discovery rồi mở rộng sang toàn bộ suite.
11. So sánh số lượng test được phát hiện với baseline classpath cũ.
12. Kiểm thử tương tự trên máy local, CI và môi trường release.

Trong giai đoạn chuyển tiếp, có thể một phần test vẫn cần chạy trên classpath. Điều quan trọng là làm rõ **test đang kiểm tra runtime model nào**; không đánh đồng kết quả classpath với kết quả chạy trên module path.

## 25. Bảng chẩn đoán nhanh

| Triệu chứng | Lớp nguyên nhân cần kiểm tra |
|---|---|
| `module ... does not read org.junit.jupiter.api` | Thiếu `requires` hoặc `--add-reads` |
| `package org.junit.jupiter.api is not visible` | JUnit API module path/readability |
| `module ... does not open package ...` | Thiếu `opens` hoặc `--add-opens` |
| `InaccessibleObjectException` | Reflection qua ranh giới module bị chặn |
| `Module ... not found` | Thiếu JAR, sai module name hoặc module path |
| `No tests found` | Test output, selector, runtime test module hoặc engine |
| `TestEngine not found` | Engine dependency/module resolution/service discovery |
| `package ... is not visible` | Test module không đọc hoặc package production chưa export |
| `reads package ... from both ...` | Split package hoặc hai module export cùng package |
| IDE chạy nhưng CI không chạy | Khác JDK, build tool, test runtime flags hoặc test selector |

Cách debug hiệu quả là phân loại lỗi trước: **compilation**, **module resolution**, **access/reflection** hay **test discovery**. Mỗi lớp lỗi có cách sửa khác nhau.

## 26. Checklist dự án JUnit modular

- [ ] Production `module-info.java` không chứa JUnit dependency không cần thiết.
- [ ] Test classes được xây dựng theo một chiến lược rõ ràng.
- [ ] Named test module có `requires` tới module sản phẩm và JUnit API.
- [ ] Patch tests có `--add-reads` đúng module/target.
- [ ] Package chứa test được mở đúng phạm vi cho reflection khi cần.
- [ ] JUnit Jupiter Engine và JUnit Platform Launcher phù hợp đã có ở runtime.
- [ ] Các module cần thiết đã thực sự được phân giải.
- [ ] Test module không vô tình tạo split package với production.
- [ ] Test resources được copy và tìm thấy theo cấu hình module.
- [ ] Maven Surefire hoặc Gradle `useJUnitPlatform()` được cấu hình đúng.
- [ ] Số lượng test được phát hiện đúng như dự kiến.
- [ ] CI dùng JDK, JUnit, module path và test flags tương ứng với local.
- [ ] Các flag mở rộng quyền truy cập không bị đưa vào production launcher.

## Kết luận

JUnit trên module path cần phối hợp ba cơ chế: **dependency readability**, **package access cho reflection** và **test discovery qua JUnit Platform**. Named test module riêng phù hợp để kiểm tra API công khai; test patch qua `--patch-module` phù hợp khi cần kiểm tra package-private implementation ở cùng module.

`requires` và `--add-reads` giúp module test đọc JUnit API hoặc module sản phẩm; `opens` và `--add-opens` giúp engine/framework truy cập test class bằng reflection; `--add-modules` và cấu hình launcher giúp những module runtime cần thiết được phân giải. Các tùy chọn này không thay thế nhau.

Hãy giữ JUnit trong test scope, chỉ mở đúng package cần thiết, xác minh Jupiter Engine đã được tìm thấy và kiểm thử trên đúng module path mà build/CI thực sự sử dụng. Khi chọn chiến lược test có chủ đích, ứng dụng có thể tận dụng JPMS encapsulation mà vẫn duy trì một bộ JUnit test đáng tin cậy.