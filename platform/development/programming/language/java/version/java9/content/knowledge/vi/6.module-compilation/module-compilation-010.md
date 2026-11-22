# Đồng bộ cấu hình biên dịch, kiểm thử và chạy

Với một ứng dụng dùng Java Platform Module System (JPMS), cấu hình biên dịch, kiểm thử và chạy cần thống nhất về **phiên bản Java mục tiêu, tên mô-đun, dependency và module path**. Nếu ba giai đoạn sử dụng các tập dependency hoặc cách phân giải mô-đun khác nhau, mã có thể biên dịch thành công nhưng test hoặc ứng dụng lại lỗi khi chạy.

Mục tiêu của việc đồng bộ là bảo đảm compiler, test runner và JVM nhìn thấy cùng một đồ thị mô-đun cần thiết. Công cụ xây dựng như Gradle hoặc Maven chịu trách nhiệm cung cấp đúng JDK, dependency và tham số cho từng giai đoạn; module descriptor vẫn là nguồn khai báo quan hệ đọc và quyền truy cập giữa các mô-đun.

## 1. Ba giai đoạn và các cấu hình phải khớp

Một quy trình modular thường gồm:

1. **Compile**: compiler đọc source code, module descriptor và các dependency cần thiết; kiểm tra package export, quan hệ `requires` và mức Java mục tiêu.
2. **Test**: test runner biên dịch/chạy test cùng các mô-đun của ứng dụng, cộng thêm dependency chỉ dành cho kiểm thử. Test có thể cần quyền reflection riêng nếu framework truy cập thành viên không public.
3. **Run**: JVM phân giải các mô-đun cần thiết trên module path, khởi chạy main class và áp dụng các quy tắc `exports`, `opens`, `uses`, `provides`.

Các thông tin nên được quản lý thống nhất:

| Thông tin | Khi compile | Khi test | Khi run |
|---|---|---|---|
| JDK/toolchain | Compiler đúng phiên bản | Test JVM tương thích | JVM tương thích với bytecode và API |
| Java release | `javac --release` | Test code dùng cùng mức API mục tiêu | Runtime phải hỗ trợ class file đã tạo |
| Module name | Đọc từ `module-info.java` | Test module tham chiếu đúng tên | Launcher chọn đúng module |
| Dependency | Có trên module path hoặc classpath phù hợp | Có thêm dependency test | Có đủ dependency runtime |
| Module path | Chứa các mô-đun cần compile | Chứa ứng dụng và test modules khi dùng named tests | Chứa toàn bộ mô-đun runtime |
| Main/test entry | Compile các module cần thiết | Test runner phát hiện và thực thi test | Chỉ định module và main class |

Một cấu hình nhất quán không có nghĩa là mọi dependency phải xuất hiện trong cả ba giai đoạn. Thư viện chỉ dùng khi test có thể chỉ nằm trong test configuration. Điều cần giữ đúng là các mô-đun ứng dụng và phiên bản Java mà ba giai đoạn cùng phụ thuộc.

## 2. Chọn JDK và mức Java mục tiêu

JDK được dùng để chạy compiler và mức Java mà artifact hướng tới là hai khái niệm liên quan nhưng khác nhau:

- **JDK/toolchain** xác định bộ công cụ thực tế dùng để biên dịch, chạy test và có thể chạy ứng dụng.
- **Release target** xác định phiên bản Java mà bytecode/API đầu ra được phép sử dụng.

Với JDK hiện đại, ưu tiên `--release` thay vì tự kết hợp `-source` và `-target`:

```powershell
javac --release 17 ...
```

`--release 17` yêu cầu compiler tạo class file và kiểm tra API theo nền tảng Java 17. Nó không tự chọn cài đặt JDK 17; compiler đang chạy vẫn đến từ JDK được chọn trong môi trường hoặc toolchain.

Nguyên tắc:

- Chọn một mức release được ứng dụng hỗ trợ và dùng nhất quán cho main source lẫn test source.
- Chọn toolchain đủ mới để hỗ trợ mức release đó.
- Chạy test bằng JVM tương thích với bytecode được tạo.
- Triển khai trên runtime có phiên bản bằng hoặc mới hơn mức Java mục tiêu.
- Không giả định JDK dùng để build cũng chính là runtime production; nếu khác nhau, phải kiểm tra tính tương thích rõ ràng.

Với dự án cần hỗ trợ nhiều môi trường, hãy quản lý mức Java trong một cấu hình chung của build tool thay vì lặp các con số khác nhau ở từng task.

## 3. Đồng bộ module path và classpath

JPMS dùng hai vùng tìm kiếm chính:

- **Module path** chứa các named module để Java phân giải theo tên mô-đun và descriptor.
- **Class path** chứa class/JAR được nạp vào unnamed module, thường dùng cho thư viện hoặc test setup chưa chạy như named module.

Khi ứng dụng có `module-info.java`, các dependency modular của ứng dụng nên được đưa lên module path. Module descriptor khai báo quan hệ cần thiết, ví dụ:

```java
module com.example.app {
    requires com.example.greeting;
}
```

Compiler cần tìm thấy `com.example.greeting` trên module path khi biên dịch. JVM cũng cần tìm thấy mô-đun đó trên module path khi chạy. Việc có một dependency trong cấu hình Gradle/Maven chỉ giúp build tool resolve artifact; nó không thay thế quan hệ `requires` trong module descriptor.

Một số lỗi đồng bộ thường gặp:

- Compile dùng module path nhưng run chỉ cung cấp classpath, khiến ứng dụng không được phân giải như named module.
- Compile tìm thấy một phiên bản dependency nhưng runtime lại dùng phiên bản khác có module name hoặc API khác.
- Một dependency có mặt lúc compile nhưng bị thiếu trong runtime configuration.
- Test runner đặt test hoặc dependency lên classpath trong khi test descriptor lại khai báo chúng như named modules.
- Một package đã `exports` cho compile-time access nhưng framework cần reflection sâu mà package chưa được `opens`.

Không cần ép mọi thư viện trong hệ thống thành named module. Điều quan trọng là hiểu thư viện nào là explicit module, automatic module hoặc thuộc unnamed module, rồi cấu hình đúng đường tìm kiếm ở từng giai đoạn.

## 4. Cấu hình bằng javac và java

Các tùy chọn dòng lệnh giúp nhìn rõ từng giai đoạn. Với cấu trúc nhiều mô-đun, `--module-source-path` cho compiler biết vị trí source root và cách tìm source của từng mô-đun.

Ví dụ source tree:

```text
src/
├── com.example.greeting/
│   ├── module-info.java
│   └── com/example/greeting/api/Greeting.java
└── com.example.app/
    ├── module-info.java
    ├── com/example/app/api/GreetingFacade.java
    └── com/example/app/Main.java

test-src/
└── com.example.tests/
    ├── module-info.java
    └── com/example/tests/GreetingTest.java
```

**Mô-đun thư viện `com.example.greeting`:**

```java
module com.example.greeting {
    exports com.example.greeting.api;
}
```

```java
package com.example.greeting.api;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello, JPMS!";
    }
}
```

**Mô-đun ứng dụng `com.example.app`:**

```java
module com.example.app {
    requires com.example.greeting;
    exports com.example.app.api;
}
```

```java
package com.example.app.api;

import com.example.greeting.api.Greeting;

public final class GreetingFacade {
    private GreetingFacade() {
    }

    public static String message() {
        return Greeting.message();
    }
}
```

Điểm khởi chạy `Main.java`:

```java
package com.example.app;

import com.example.app.api.GreetingFacade;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(GreetingFacade.message());
    }
}
```

**Mô-đun kiểm thử `com.example.tests`:**

```java
module com.example.tests {
    requires com.example.app;
}
```

Test chạy như một named module riêng và kiểm tra API công khai của ứng dụng:

```java
package com.example.tests;

import com.example.app.api.GreetingFacade;

public final class GreetingTest {
    private GreetingTest() {
    }

    public static void main(String[] args) {
        String actual = GreetingFacade.message();

        if (!"Hello, JPMS!".equals(actual)) {
            throw new AssertionError("Unexpected greeting: " + actual);
        }

        System.out.println("PASS: GreetingFacade returns " + actual);
    }
}
```

Từ thư mục gốc dự án, dùng JDK 17 trở lên để biên dịch main modules và test module:

```powershell
New-Item -ItemType Directory -Force out, test-out | Out-Null

javac --release 17 --module-source-path src -d out -m com.example.greeting,com.example.app

javac --release 17 --module-path out --module-source-path test-src -d test-out -m com.example.tests
```

Hai lệnh compile sử dụng cùng release target. Lệnh thứ hai đặt output của ứng dụng lên module path để compiler kiểm tra quan hệ `requires com.example.app` của test module.

Chạy ứng dụng:

```powershell
java --module-path out -m com.example.app/com.example.app.Main
```

Stdout:

```text
Hello, JPMS!
```

Chạy test module trên cùng module graph với ứng dụng. Trên Windows PowerShell, dấu chấm phẩy phân tách các entry của module path:

```powershell
java --module-path "out;test-out" -m com.example.tests/com.example.tests.GreetingTest
```

Stdout:

```text
PASS: GreetingFacade returns Hello, JPMS!
```

Trên Linux/macOS, dùng dấu hai chấm để phân tách module path:

```bash
java --module-path "out:test-out" -m com.example.tests/com.example.tests.GreetingTest
```

Ví dụ này dùng một test module Java nhỏ để làm rõ module graph. Trong dự án thực tế, test runner như JUnit sẽ thay phần main test đơn giản; nguyên tắc phân giải mô-đun và dependency vẫn giống nhau.

## 5. Đồng bộ khi dùng Gradle

Với Gradle Java Plugin, có thể cấu hình toolchain, release và module path trong build script:

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
    modularity.inferModulePath = true
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

application {
    mainModule = 'com.example.app'
    mainClass = 'com.example.app.Main'
}

dependencies {
    implementation project(':greeting')
    testImplementation libs.junit.jupiter
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Các điểm cần hiểu:

- `toolchain` chọn JDK cho các task Java của Gradle.
- `options.release` đồng bộ API và class file target của main/test compile tasks.
- `modularity.inferModulePath = true` cho phép Gradle nhận diện module descriptor và suy luận dependency phù hợp để dùng module path.
- `mainModule` và `mainClass` xác định entry point của ứng dụng modular.
- `implementation project(':greeting')` cung cấp artifact của project thư viện cho build graph. Module descriptor của app vẫn khai báo `requires com.example.greeting`.
- `testImplementation` giữ thư viện test trong test configuration.
- `useJUnitPlatform()` yêu cầu Gradle Test task chạy JUnit Platform; alias `libs.junit.jupiter` nên được quản lý trong version catalog hoặc dependency management chung của dự án.

Nếu dùng multi-project build, kiểm tra tên project Gradle và tên JPMS module độc lập với nhau. Ví dụ project `:greeting` có thể tạo artifact chứa module `com.example.greeting`; quan hệ `requires` phải dùng tên trong descriptor.

Gradle có thể tự suy luận module path cho các task Java khi cấu trúc mô-đun được khai báo rõ. Tuy nhiên, cách tổ chức test module, JUnit và quyền reflection còn phụ thuộc vào mô hình test mà dự án chọn. Hãy kiểm tra lệnh compile/test/run thực tế của build khi thay đổi cấu trúc test; không giả định chỉ cần bật module path là mọi test framework đã có đủ quyền truy cập.

## 6. Đồng bộ khi dùng Maven

Trong Maven, compiler plugin quản lý mức Java mục tiêu; Surefire chạy test. Ví dụ cấu hình phần cốt lõi:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>${maven.compiler.release}</release>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <useModulePath>true</useModulePath>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Trong ví dụ, version của JUnit và Maven plugins được quản lý tập trung bởi parent POM hoặc `pluginManagement`/dependency management của dự án; không nên để các module con tự chọn những version không đồng bộ.

- `maven.compiler.release` thống nhất release target cho compiler.
- Dependency có scope `test` chỉ phục vụ test lifecycle và không trở thành dependency runtime thông thường của ứng dụng.
- `useModulePath` cho phép Surefire dùng module path khi phát hiện cấu trúc mô-đun phù hợp.
- Maven vẫn cần JDK/toolchain đúng phiên bản và dependency được resolve đầy đủ cho từng lifecycle.

Nếu dự án dùng Failsafe cho integration test, hãy đồng bộ cấu hình module path và JVM arguments tương tự với Surefire. Kiểm tra cả unit test và integration test vì hai plugin có thể chạy ở các phase và cấu hình riêng.

## 7. Test trong named module và quyền reflection

Test có thể được tổ chức theo hai hướng:

**Test module riêng**

Test là một named module độc lập, có descriptor riêng và khai báo `requires` tới mô-đun ứng dụng. Cách này phù hợp để kiểm tra API công khai và hành vi quan sát được qua ranh giới mô-đun. Ví dụ ở phần 4 sử dụng mô hình này.

**Test chạy qua test classpath hoặc được ghép vào mô-đun đang kiểm thử**

Nhiều dự án dùng JUnit thông qua test source set mặc định của build tool. Khi đó test có thể thuộc unnamed module hoặc được build tool cấu hình để chạy cùng mô-đun chính. Nếu framework cần reflection sâu vào package của ứng dụng, package đó phải được mở đúng phạm vi.

Ví dụ mở package nội bộ cho một framework test cụ thể:

```java
module com.example.app {
    exports com.example.app.api;
    opens com.example.app.internal to org.junit.platform.commons;
}
```

Chỉ thêm `opens` khi test framework thực sự cần truy cập thành viên không public. Tên mô-đun của framework phải được xác nhận từ module descriptor của dependency đang dùng. Nếu test chạy trong unnamed module, cấu hình runtime có thể cần `--add-opens` với target `ALL-UNNAMED`; đây là quyền runtime được cấp có chủ đích, không phải thay đổi module descriptor trong artifact.

Không xuất package internal chỉ để test truy cập được class private/package-private. Hãy cân nhắc test qua public API, test module có thiết kế rõ ràng hoặc cấu hình patch-module phù hợp với build tool khi cần white-box testing.

## 8. Phân biệt dependency compile, test và runtime

Dependency có thể cần ở một số giai đoạn nhất định:

| Loại dependency | Compile ứng dụng | Compile/chạy test | Chạy ứng dụng |
|---|---:|---:|---:|
| Thư viện ứng dụng dùng trực tiếp | Có | Có theo dependency graph | Có nếu dùng lúc runtime |
| Thư viện chỉ dùng để biên dịch annotation/code generation | Có thể có | Theo nhu cầu | Thường không |
| JUnit/test engine/assertion library | Không | Có | Không |
| Driver hoặc adapter chỉ dùng ở runtime | Có thể không | Có thể cần cho integration test | Có |
| Công cụ test fixture | Không | Có | Không |

Trong JPMS, descriptor thể hiện quan hệ đọc mô-đun của mã ứng dụng. Build tool lại quản lý dependency theo configuration/scope. Hai lớp phải khớp nhưng không cần có cùng danh sách.

Một thư viện được khai báo trong Gradle `testImplementation` hoặc Maven `test` scope không nên bị thêm vào dependency runtime chỉ vì test cần nó. Ngược lại, nếu ứng dụng cần một thư viện khi chạy nhưng build chỉ khai báo trong test configuration, test có thể chạy qua còn production lại thiếu dependency.

## 9. Cách chẩn đoán lỗi không đồng bộ

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Compile báo `module not found` | Dependency thiếu trên module path hoặc tên trong `requires` sai | Kiểm tra descriptor của JAR bằng `jar --describe-module` và module path của compile task |
| Compile thành công nhưng runtime báo `FindException` | Runtime module path thiếu mô-đun cần thiết | So sánh dependency runtime với đồ thị `requires` |
| Runtime báo `IllegalAccessError` | Package không được export phù hợp hoặc descriptor runtime khác compile | Kiểm tra `exports`, tên module và phiên bản artifact |
| Reflection bị từ chối | Package chưa mở cho module gọi reflection | Kiểm tra `opens`, caller module và runtime arguments |
| Test không tìm thấy class ứng dụng | Test runner dùng sai classpath/module path hoặc thiếu test dependency | Kiểm tra cấu hình test compile và test runtime riêng biệt |
| Test chạy trên máy dev nhưng fail CI | JDK/toolchain hoặc module path giữa hai môi trường khác nhau | In JDK thực tế của từng task, kiểm tra wrapper và cấu hình CI |
| Chạy ứng dụng với JDK cũ bị lỗi class version | Runtime thấp hơn release target | Nâng runtime hoặc hạ release target có chủ đích |
| JUnit không truy cập được test/member | Test package hoặc package ứng dụng cần reflection chưa được mở | Mở đúng package cho module framework hoặc cấu hình test runtime có chủ đích |
| App chạy bằng IDE nhưng không chạy bằng launcher | IDE tự bổ sung module path/VM arguments | So sánh module path, main module, main class và VM arguments của hai cách chạy |

Các công cụ JDK hữu ích:

```powershell
java -version
javac -version
jar --describe-module --file path/to/library.jar
jar --list --file path/to/application.jar
```

- `java -version` và `javac -version` giúp xác nhận JDK thực tế của terminal. Build tool có thể dùng toolchain khác terminal mặc định, vì vậy cũng cần kiểm tra log của task.
- `jar --describe-module` xác nhận tên module và các directive được đóng gói trong JAR.
- `jar --list` kiểm tra descriptor và class/resource có mặt trong artifact.

Với Gradle, có thể chạy task bằng wrapper và xem log chi tiết khi cần xác định tham số thực tế. Với Maven, dùng Maven Wrapper của dự án và xem cấu hình effective POM khi nghi ngờ plugin hoặc property bị ghi đè. Wrapper giúp đồng bộ phiên bản build tool giữa máy cá nhân và CI; toolchain giúp đồng bộ JDK cho các task Java.

## 10. Checklist đồng bộ trước khi phát hành

- Chốt JDK/toolchain và Java release target trong cấu hình build chung.
- Dùng cùng release target cho main source và test source.
- Xác nhận `module-info.java` khai báo đúng tên mô-đun, `requires`, `exports` và `opens`.
- Đưa modular dependencies lên module path trong compile và runtime.
- Giữ dependency test trong test configuration; không làm rò test framework vào runtime của ứng dụng.
- Chọn rõ test model: named test module, test classpath hoặc patch-module theo yêu cầu.
- Cấp quyền reflection tối thiểu cho framework cần thiết.
- Xác nhận main module và main class trong launcher/build configuration.
- Chạy test bằng đúng JDK/toolchain và module graph tương thích với runtime.
- Kiểm tra modular JAR thực tế bằng `jar --describe-module`.
- Chạy ứng dụng từ artifact đã đóng gói, không chỉ từ IDE hoặc output directory.
- Dùng wrapper và cấu hình build được quản lý chung để CI và máy phát triển có kết quả nhất quán.

Đồng bộ compile, test và run là việc giữ cùng một hợp đồng mô-đun qua toàn bộ vòng đời ứng dụng. Khi JDK, release target, dependency graph, module path và quyền truy cập được cấu hình có chủ đích, kết quả biên dịch sẽ phản ánh sát hơn cách ứng dụng thực sự được kiểm thử và vận hành.
