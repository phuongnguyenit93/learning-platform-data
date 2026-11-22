# Quản lý phiên bản, scope và loại trừ cho các mô-đun con trong Maven

## 1. Mục tiêu: một chính sách dependency dùng chung, nhiều module chọn dependency riêng

Trong dự án Maven đa module, các module thường sử dụng những thư viện có liên quan nhưng khác mục đích: một module biên dịch mã ứng dụng, một module xử lý văn bản, một module chỉ cần JUnit khi kiểm thử. Nếu mỗi `pom.xml` tự chép phiên bản, scope và exclusions, toàn dự án dễ xảy ra sai lệch: cùng một thư viện nhưng có nhiều version, test framework bị đưa vào runtime, hoặc một dependency bắc cầu không mong muốn xuất hiện trở lại ở module khác.

Maven cung cấp `<dependencyManagement>` để **quản lý thông tin dependency ở một nơi**, thường là parent POM hoặc BOM (Bill of Materials). Những thông tin có thể quản lý gồm:

- **Version:** chọn phiên bản thư viện mà dự án muốn dùng, cả khi module khai báo dependency không ghi `<version>` và trong một số trường hợp dependency bắc cầu.
- **Scope:** cung cấp scope mặc định như `compile`, `test`, `runtime` khi một dependency được chọn, từ đó ảnh hưởng classpath.
- **Exclusions:** loại bỏ một dependency **bắc cầu** theo một đường đi dependency cụ thể, khi biết rõ phải loại gì và vì sao.
- **Type/classifier và một số metadata phù hợp:** các phần của dependency key và cấu hình resolution liên quan.

Điểm phân biệt quan trọng:

> `dependencyManagement` **không tự thêm JAR vào project**. Một module con cần khai báo dependency **trong `<dependencies>`** nếu mã nguồn hoặc runtime của module thực sự sử dụng nó.

Ví dụ parent có thể quản lý `org.apache.commons:commons-text:1.13.1`, nhưng một module không khai báo Commons Text thì không tự có Commons Text trên classpath chỉ vì nó kế thừa parent. Đây là cơ chế **quản lý lựa chọn**, không phải cơ chế **kéo mọi dependency**.

Bài này tập trung vào **cách dùng parent/BOM để quản lý version, scope và exclusions cho các module con**, cách module con dùng/ghi đè quản lý đó, và cách xác minh hiệu lực bằng lệnh Maven. Các ví dụ áp dụng cho POM Maven 4.0.0 model phổ biến và Maven 3.9.x; Maven 4 có thêm khả năng quản lý dự án, vì vậy nên kiểm tra tài liệu đúng phiên bản đang dùng.

## 2. Ba tầng cần tách bạch: quản lý, khai báo, giải quyết dependency

Hãy phân biệt ba nơi/khâu:

~~~text
(1) Parent POM hoặc BOM
    <dependencyManagement>
        các quy tắc version / scope / exclusions
    </dependencyManagement>
                    |
       inheritance hoặc BOM import
                    v
(2) Child POM: module A, B, C...
    <dependencies>
        chỉ những dependency module thật sự cần
    </dependencies>
                    |
                    v
(3) Maven dependency resolution
    - áp dụng dependency management hiệu lực
    - xét scope, optional, exclusions, mediation
    - tạo compile / test / runtime classpath
                    |
                    v
       build, test và chạy ứng dụng
~~~

**Tầng 1 không thay thế tầng 2.** Parent có thể quản lý JUnit nhưng chỉ module có test JUnit mới cần dependency JUnit scope test. **Tầng 2 không đủ để kết luận tầng 3**, vì Maven còn xử lý dependency bắc cầu, version mediation, profile active và overrides ở POM con.

Ví dụ cơ bản trong parent:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Con cần JUnit:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
    </dependency>
</dependencies>
~~~

Khi con kế thừa parent đúng, Maven dùng JUnit `5.11.4` với scope `test`. Nếu con không có `<dependency>` JUnit và không có dependency khác kéo theo nó, không có lý do để JUnit tự lên test classpath chỉ từ bảng management.

Các đoạn XML trên là **mảnh cấu hình đặt trong `<project>`**, không phải tệp POM hoàn chỉnh.

## 3. Parent POM dùng chung dependencyManagement như thế nào?

Một parent POM điển hình có `<packaging>pom</packaging>`, một bộ thuộc tính cấu hình chung và danh sách managed dependencies:

~~~xml
<groupId>org.example.training</groupId>
<artifactId>training-parent</artifactId>
<version>1.0.0</version>
<packaging>pom</packaging>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là một **mảnh của parent POM**, không đủ để build nếu dùng độc lập. Project con khai báo:

~~~xml
<parent>
    <groupId>org.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0</version>
</parent>
<artifactId>text-core</artifactId>
~~~

Con thường kế thừa `groupId` và `version` của parent nếu không khai báo riêng, nhưng `artifactId` là định danh của chính con. Con cũng kế thừa dependency management để dùng khi khai báo dependencies.

**Parent inheritance và aggregation là hai quan hệ khác nhau:**

- Con khai báo `<parent>` để **kế thừa cấu hình**.
- Parent hoặc aggregator khai báo `<modules>` để **Maven reactor biết build những project nào**.
- Việc hai module cùng nằm trong `<modules>` **không tự đưa class từ module này vào classpath module kia**. Cần dependency thông thường giữa hai artifacts.
- Một parent POM có thể được phát hành lên repository và được nhiều project độc lập kế thừa; không bắt buộc cùng một filesystem tree.
- Một BOM cũng có `packaging=pom` nhưng **import BOM** chỉ nhập các mục dependency management, không mặc nhiên kế thừa plugin config hay phần lớn metadata như khai báo `<parent>`.

## 4. Quản lý version: một bản cho module A, B và dependency bắc cầu

Nếu parent quản lý:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
</dependency>
~~~

thì module A/B, khi khai báo `commons-lang3` không ghi version, có thể nhận version `3.17.0` qua effective dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
~~~

Một lợi ích khác: dependency management còn có thể tác động lên **transitive dependencies** trong project dependency graph. Nếu `commons-text` cần `commons-lang3`, Maven có thể dùng version được quản lý thay vì chọn bản chỉ dựa trên đường graph ngắn nhất.

Tuy nhiên:

1. **Version management không tải mọi thư viện được quản lý**. Nó chỉ quyết định thông tin khi artifact được yêu cầu qua dependency graph hợp lệ.
2. **Version management không tự đảm bảo tương thích nhị phân**. Nếu ép một phiên bản quá cũ mà upstream yêu cầu API mới, runtime có thể lỗi `NoSuchMethodError` hoặc linkage error.
3. **Một dependency khai báo version cụ thể ngay ở child có thể ghi đè version quản lý áp dụng cho declaration đó**; cần xem effective POM và graph để biết kết quả.
4. **Dependency management ở child có ưu tiên so với version management kế thừa từ parent** cho entry phù hợp; khi có nhiều BOM import, thứ tự và quản lý cục bộ cũng ảnh hưởng.
5. **Dependency management của project không quản lý các dependencies bên trong plugin realm.** Muốn thay version JAR của plugin phải dùng cơ chế cấu hình plugin/plugin dependencies thích hợp, không hy vọng `<dependencyManagement>` của app thay đổi plugin internals.
6. Việc mọi module sử dụng version được quản lý **không phải là một dependency lockfile** theo nghĩa đóng băng toàn bộ graph. Còn plugins, repositories, ranges, snapshots và runtime environment cần kiểm soát.

Với các thư viện đang thay đổi nhanh, nên quản lý tập version có chủ đích và kiểm tra advisory/compatibility trước khi nâng; các version trong ví dụ dưới đây là phiên bản minh họa đã phát hành, không phải chỉ dẫn chọn version production mới nhất.

## 5. Quản lý scope: compile, test, runtime và overrides ở con

Scope quyết định dependency xuất hiện trong những classpath nào và mức độ được truyền transitively.

| Scope | Tác dụng trong một module | Ví dụ thường gặp |
| --- | --- | --- |
| `compile` | Có trên compile, runtime và test classpaths; mặc định nếu không khai báo. | API do `src/main/java` import. |
| `test` | Chỉ cần cho compile/chạy test, không vào main runtime của ứng dụng. | JUnit, test helper. |
| `runtime` | Không vào main compile; có ở runtime và test. | JDBC driver được nạp động. |
| `provided` | Có ở compile/test, môi trường chạy được kỳ vọng cung cấp; không vào runtime classpath chuẩn do Maven chọn. | Servlet API trong môi trường container cấp sẵn. |
| `system` | Phụ thuộc vào local JAR và `systemPath`, không khuyến nghị. | Hệ thống legacy đặc thù. |
| `import` | Không phải scope classpath của module; chỉ dành cho `type=pom` trong `dependencyManagement`. | Nhập một BOM. |

Parent có thể quản lý scope `test` cho JUnit:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Child không cần lặp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
    </dependency>
</dependencies>
~~~

Khi test code import `org.junit.jupiter.api.Test`, JUnit có mặt trên test classpath. Nhưng `src/main/java` **không** được tự import JUnit chỉ vì dependency đã được quản lý ở parent.

**Child có thể khai báo scope tường minh khác** nếu thật sự có nhu cầu. Ví dụ nếu một thư viện được parent quản lý scope compile nhưng child **chỉ** dùng trong test, child có thể ghi `<scope>test</scope>` ở dependency của chính mình. Giá trị cụ thể trong khai báo child được dùng thay cho default quản lý phù hợp, và không làm scope ở tất cả các sibling thay đổi.

Lưu ý không đổi scope chỉ để sửa tạm một lỗi:

- Mã main dùng class của một dependency `test` → thường sai bố trí source hoặc sai scope.
- Main code trực tiếp import API từ dependency chỉ có `runtime` → compiler không tìm thấy class; nên xét scope `compile` hoặc tách API và implementation.
- Dùng `provided` mà runtime không thực sự cung cấp JAR → có thể thất bại khi chạy ứng dụng.

**Scope được quản lý và scope của transitive dependency** có cơ chế kết hợp riêng. Không suy luận một scope khai báo ở POM của thư viện gián tiếp luôn nguyên trạng trên classpath cuối của app.

## 6. Quản lý exclusions: loại một đường transitive, không cấm toàn hệ thống

**Exclusion** giúp ngăn Maven kéo một artifact bắc cầu qua **một dependency cụ thể**. Ví dụ:

~~~text
text-core
  |
  +-- commons-text:1.13.1
        |
        +-- commons-lang3:3.17.0   <-- transitive từ commons-text
~~~

Trong thực tế, Commons Text `1.13.1` khai báo Commons Lang `3.17.0` là compile dependency. Nếu nhóm muốn **quản lý tường minh đường đưa Commons Lang vào module**, có thể loại nhánh qua Commons Text và khai báo Lang trực tiếp:

~~~text
text-core
  |
  +-- commons-text:1.13.1
  |     |
  |     +-- commons-lang3   (EXCLUDED chỉ từ nhánh này)
  |
  +-- commons-lang3:3.17.0 (DIRECT, vẫn có trên classpath)
~~~

Trong `<dependencyManagement>` của parent:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-text</artifactId>
    <version>1.13.1</version>
    <exclusions>
        <exclusion>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Khi module con chọn `commons-text` qua `<dependencies>` và áp dụng managed exclusion, **đường đi `commons-text → commons-lang3` bị loại**. Nếu module con còn khai báo `commons-lang3` trực tiếp hoặc một nhánh khác kéo nó vào, Lang **vẫn có thể xuất hiện**. Exclusion **không phải global ban**, không xóa artifact đó khỏi tất cả các nhánh của project.

**Ví dụ này chủ yếu để học cú pháp và semantics, không phải lời khuyên luôn phải exclude Lang khỏi Commons Text.** Vì Commons Text thực sự dùng Commons Lang trong implementation, loại Lang mà không đưa lại bằng một dependency phù hợp có thể tạo lỗi runtime. Chỉ dùng exclusions khi có lý do rõ ràng (xung đột, artifact thừa/không an toàn, implementation khác) và đã kiểm tra hậu quả; **đừng exclude ngẫu nhiên những dependency mà upstream cần**.

Điều kiện để exclusions có hiệu lực:

- Đặt trong `<exclusions>` của **dependency liên quan**, ở khai báo child hoặc trong managed dependency entry được áp dụng.
- `<exclusion>` chỉ định **`groupId` và `artifactId`** của artifact muốn chặn; không điền `version` vào entry exclusion.
- Hiệu lực theo **nhánh dependency** mà entry thuộc về, không theo mọi đường dẫn.
- Nếu một nhánh khác vẫn kéo cùng artifact vào, dependency đó vẫn có thể xuất hiện trên classpath cuối.
- Exclusion không ảnh hưởng JAR nội bộ của Maven plugins trừ khi chính cấu hình plugin có cơ chế tương ứng.

Dùng `dependency:tree` để xác định đường kéo artifact vào **trước khi** thêm exclusion, và chạy lại tree/test/runtime sau khi chỉnh. Với yêu cầu chặn một artifact trên toàn graph (ví dụ vì một lỗ hổng bảo mật), Maven Enforcer Plugin với `bannedDependencies` là một cơ chế **kiểm tra/fail build**, còn exclusions cụ thể vẫn cần được áp dụng theo các nhánh gây vi phạm.

## 7. Quản lý chung khác khai báo trực tiếp trong parent dependencies

Một sai lầm dễ gặp là đặt mọi thư viện của tổ chức vào:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**ngay ở parent** rồi mong tất cả module “tự chọn”. Với Maven POM inheritance, `<dependencies>` của parent thường **được kế thừa như các dependency thật**. Điều này có thể làm các module vốn không cần JUnit cũng mang dependency JUnit trong effective model.

Nếu muốn các module tự chọn, đặt trong:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

và chỉ thêm `<dependency>` JUnit tại module thực sự có test JUnit.

Tình huống dùng `<dependencies>` tại parent **không phải luôn sai**: nếu mọi module nhất định cần cùng một dependency ở cùng scope, nhóm có thể chủ động kế thừa. Nhưng với một platform có nhiều loại module (Java library, web service, CLI tool, BOM, parent-only module), **`dependencyManagement` thường là nơi thích hợp để quản lý đồng bộ mà không ép mọi module nhận JAR**.

## 8. Ví dụ hoàn chỉnh: parent quản lý version, scope và exclusion cho hai module Java 17

Ví dụ dưới đây dùng một **parent đồng thời là aggregator**; hai module `text-core` và `app` kế thừa nó. Mã Java 17 dùng Apache Commons Text/Commons Lang và JUnit Jupiter. Mục tiêu là tạo một dự án chạy được, không chỉ minh họa XML rời.

Các tọa độ đã xác nhận tồn tại trong Maven Central:

- `org.apache.commons:commons-text:1.13.1` (POM của bản này kéo `commons-lang3`).
- `org.apache.commons:commons-lang3:3.17.0`.
- `org.junit.jupiter:junit-jupiter:5.11.4`.

Chúng là **version mẫu cố định** cho bài học; khi dùng thực tế hãy xem version/JDK support và security policy hiện tại.

~~~text
managed-deps-demo/
├── pom.xml                                # Parent + aggregator
├── text-core/
│   ├── pom.xml                            # Child 1: core library
│   └── src/
│       ├── main/java/org/example/core/GreetingFormatter.java
│       └── test/java/org/example/core/GreetingFormatterTest.java
└── app/
    ├── pom.xml                            # Child 2: CLI app
    └── src/main/java/org/example/app/Main.java
~~~

### 8.1. Parent POM đầy đủ: managed-deps-demo/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.training</groupId>
    <artifactId>demo-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>text-core</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <!-- Version + scope + exclusion for library using Lang internally. -->
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-text</artifactId>
                <version>1.13.1</version>
                <scope>compile</scope>
                <exclusions>
                    <exclusion>
                        <groupId>org.apache.commons</groupId>
                        <artifactId>commons-lang3</artifactId>
                    </exclusion>
                </exclusions>
            </dependency>

            <!-- Keep Lang available via a deliberate direct dependency. -->
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.17.0</version>
                <scope>compile</scope>
            </dependency>

            <!-- Tests only, not main runtime. -->
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
                <scope>test</scope>
            </dependency>

            <!-- Inter-module dependency version. -->
            <dependency>
                <groupId>org.example.training</groupId>
                <artifactId>text-core</artifactId>
                <version>1.0.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Đây là **một POM hoàn chỉnh**. Những điểm cần xem:

1. Parent quản lý version/scope/exclusions của `commons-text`.
2. Parent quản lý `commons-lang3` riêng; không phụ thuộc hoàn toàn vào nhánh transitive của Commons Text.
3. Parent quản lý JUnit scope test; **không** đặt JUnit trong `project/dependencies` của parent.
4. Parent quản lý version của module `text-core` để `app` không cần lặp version.
5. `pluginManagement` quản lý version Maven Compiler/Surefire. Đây là quản lý **plugin**, không phải project dependency management.
6. `<modules>` cho reactor biết phải build `text-core` và `app`. Nó không tự tạo project dependency giữa hai module.
7. Parent có `packaging=pom`, còn hai child không khai báo packaging nên mặc định `jar`.

### 8.2. Child 1: text-core/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.training</groupId>
        <artifactId>demo-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>text-core</artifactId>

    <dependencies>
        <!-- Commons Text is used directly by source. -->
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-text</artifactId>
        </dependency>

        <!-- Added directly because source/Commons Text still need Lang. -->
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>

        <!-- Only this module uses JUnit in its test sources. -->
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Tệp trên **cố ý không** ghi version/scope/exclusions ở ba dependency:

| Dependency child chọn | Kết quả quản lý từ parent |
| --- | --- |
| `commons-text` | `1.13.1`, `compile` và exclusion `commons-lang3` trên nhánh Commons Text. |
| `commons-lang3` | `3.17.0`, `compile`, được **khai báo trực tiếp**, nên không bị exclusion ở nhánh Commons Text chặn. |
| `junit-jupiter` | `5.11.4`, `test`. |

**Điểm kỹ thuật:** Exclusion không phải lý do để bỏ dependency mà thư viện hoặc code vẫn cần. Trong mẫu, Lang được khai báo **trực tiếp** nên cả mã `GreetingFormatter` và Commons Text vẫn có thể dùng Lang ở runtime. Cách làm này có tính giáo dục về đường dependency; trong một dự án thực tế nếu không có xung đột, thường không cần exclude Lang của Commons Text khi đã dùng version management.

### 8.3. Java source của text-core

Tệp `text-core/src/main/java/org/example/core/GreetingFormatter.java`:

~~~java
package org.example.core;

import java.util.Map;
import org.apache.commons.lang3.StringUtils;
import org.apache.commons.text.StringSubstitutor;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String greeting(String rawName) {
        String name = StringUtils.trimToEmpty(rawName);
        if (name.isEmpty()) {
            name = "guest";
        }
        return StringSubstitutor.replace(
                "Hello, ${name}!",
                Map.of("name", name)
        );
    }
}
~~~

Ở đây:

- `Map` thuộc Java Standard Library; không cần Maven dependency.
- `StringUtils` thuộc Commons Lang; module trực tiếp import nên có direct dependency `commons-lang3`.
- `StringSubstitutor` thuộc Commons Text; module trực tiếp import nên có direct dependency `commons-text`.
- `StringUtils.trimToEmpty` loại khoảng trắng ở hai đầu chuỗi trong ví dụ; nếu đầu vào rỗng/null, dùng `guest`.
- `StringSubstitutor.replace` thay `${name}` bằng value trong map, nên `greeting(" Maven ")` trả `Hello, Maven!`.

Mã dùng API có thật của các thư viện đã chỉ định. Khi dùng JDK 17, `Map.of` và các API trên phù hợp với ví dụ.

### 8.4. Unit test của text-core

Tệp `text-core/src/test/java/org/example/core/GreetingFormatterTest.java`:

~~~java
package org.example.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingFormatterTest {
    @Test
    void formatsNamedAndDefaultGreeting() {
        assertEquals("Hello, Maven!", GreetingFormatter.greeting(" Maven "));
        assertEquals("Hello, guest!", GreetingFormatter.greeting("  "));
    }
}
~~~

Có **một test method** với hai assertions. Vì mã test import `Test` và `Assertions`, `text-core` cần JUnit scope test. Version và scope đến từ parent management; `app` không cần JUnit nếu nó không có test dùng JUnit.

### 8.5. Child 2: app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.example.training</groupId>
        <artifactId>demo-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>demo-app</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.example.training</groupId>
            <artifactId>text-core</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

`app` khai báo `text-core` **trực tiếp**, vì mã app dùng class trong module đó. Version `1.0.0` được quản lý ở parent. `text-core` có các compile dependencies Commons Text/Lang, nên khi Maven giải quyết graph bình thường, chúng có thể xuất hiện **transitively** ở runtime của app; không cần copy thủ công các JAR vào nguồn project.

`app` không trực tiếp import `StringUtils` hay `StringSubstitutor`, vì vậy nó không cần khai báo trực tiếp hai thư viện đó trong chính POM; nếu tương lai app bắt đầu import API của chúng, nên khai báo tương ứng ở app thay vì dựa vào transitive dependency của `text-core`.

### 8.6. Java main của app

Tệp `app/src/main/java/org/example/app/Main.java`:

~~~java
package org.example.app;

import org.example.core.GreetingFormatter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(GreetingFormatter.greeting(" Maven "));
        System.out.println(GreetingFormatter.greeting("   "));
    }
}
~~~

`Main` chỉ import một class từ `text-core`. Đường dependency app → text-core được khai báo trong `app/pom.xml`. Nếu chỉ đặt cả hai module vào `<modules>` mà **không** có app dependency này, Maven không tự cho app compile với class của text-core.

### 8.7. Lệnh build, test và chạy app

Từ root `managed-deps-demo/`:

~~~bash
mvn -B -ntp clean install
~~~

Chọn `install` trong ví dụ để cả artifact `text-core`, `demo-app` và parent POM được cài vào **local Maven repository**, giúp các lệnh chạy riêng trong thư mục `app` tiếp theo giải quyết dependency nội bộ. Build reactor chạy `text-core` trước `app` do app phụ thuộc core. Khi chưa có cache, Maven có thể cần internet để tải plugin/JAR.

Sau khi build/install thành công, chuyển sang module app:

~~~bash
cd app
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
java -cp "target/classes:target/dependency/*" org.example.app.Main
~~~

Lệnh trên dành cho **Bash/Zsh** ở Linux/macOS. Ở Windows PowerShell hoặc CMD, dùng lệnh Java tương ứng:

~~~text
java -cp "target\classes;target\dependency\*" org.example.app.Main
~~~

Goal `copy-dependencies` với `includeScope=runtime` lấy các dependency hiệu lực phục vụ runtime, bao gồm `text-core`, Commons Text và Commons Lang, nhưng không cần JUnit scope test của `text-core`. Lệnh `java` lấy main code từ `target/classes` và các JAR từ `target/dependency`.

**Stdout chính xác của riêng lệnh `java`**, nếu dùng đúng các tệp/code và build thành công:

~~~text
Hello, Maven!
Hello, guest!
~~~

Không mô tả stdout này là toàn bộ log `mvn`: build Maven có các dòng download/compile/test/package/install riêng.

Sau build có thể thấy những tệp trọng tâm:

~~~text
text-core/target/
├── classes/org/example/core/GreetingFormatter.class
├── test-classes/org/example/core/GreetingFormatterTest.class
├── surefire-reports/
│   └── TEST-org.example.core.GreetingFormatterTest.xml
└── text-core-1.0.0.jar

app/target/
├── classes/org/example/app/Main.class
├── demo-app-1.0.0.jar
└── dependency/
    ├── text-core-1.0.0.jar
    ├── commons-text-1.13.1.jar
    └── commons-lang3-3.17.0.jar
~~~

Cây là **minh họa rút gọn các tệp trọng tâm**. Maven và plugin có thể sinh thêm báo cáo, metadata, tệp JAR khác. Tên trong `target/dependency` giả sử runtime dependency resolution có kết quả như POM mẫu và không có overrides ngoài mẫu. Không dùng cây minh họa thay cho việc kiểm tra thư mục thật.

### 8.8. Kiểm tra management đang hoạt động

Từ root:

~~~bash
mvn -pl :text-core help:effective-pom
mvn -pl :text-core dependency:tree
mvn -pl :text-core dependency:tree -Dincludes=org.apache.commons:commons-lang3
mvn -pl :demo-app dependency:tree
~~~

Trong effective POM của text-core, tìm `commons-text` version `1.13.1`, managed exclusion Lang, Commons Lang version `3.17.0` và JUnit scope `test`. Trong dependency tree, Lang có thể hiển thị trực tiếp ở text-core; đừng kết luận exclusion thất bại chỉ vì tên Lang còn trong graph: chính text-core đã khai báo Lang trực tiếp.

Muốn quan sát đầy đủ các đường bị omitted/excluded có thể cần tùy chọn goal/plugin tương ứng; **`dependency:tree` mặc định chủ yếu cho biết graph được chọn**, không phải luôn liệt kê rõ mọi cạnh đã bị loại.

Nếu dùng Maven Wrapper đã commit trong dự án, có thể thay `mvn` bằng `./mvnw` ở root trên Unix/macOS hoặc `.\mvnw.cmd` trên Windows; dự án mẫu không tự tạo Wrapper.

## 9. BOM import: quản lý chung không cần cùng một parent

Một child Maven **chỉ có một parent trực tiếp**, nhưng có thể sử dụng **nhiều BOM** để nhập các tập dependency management. BOM là một artifact POM có `<packaging>pom</packaging>` và thường tập trung các managed dependencies của một hệ thư viện.

Một BOM độc lập tối giản, dùng lại các version trong ví dụ (ví dụ tên `training-bom/pom.xml`):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.training</groupId>
    <artifactId>training-bom</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-text</artifactId>
                <version>1.13.1</version>
                <scope>compile</scope>
                <exclusions>
                    <exclusion>
                        <groupId>org.apache.commons</groupId>
                        <artifactId>commons-lang3</artifactId>
                    </exclusion>
                </exclusions>
            </dependency>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.17.0</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
                <scope>test</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

BOM này là **ví dụ riêng** và **không phải module thứ ba cần thêm vào dự án runnable mục 8**. Muốn import nó thì phải cài đặt hoặc phát hành artifact BOM vào repository Maven mà project sử dụng có thể truy cập. Đừng coi tọa độ `org.example.training:training-bom:1.0.0` đã tồn tại trên Maven Central.

Project muốn nhập BOM đặt trong `<dependencyManagement>`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.training</groupId>
            <artifactId>training-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đoạn này có thể nằm trong **parent khác** hoặc trong child muốn dùng version management của BOM. Nó **không** đưa Commons Text, Lang hay JUnit vào project classpath; module vẫn chọn dependencies thực tế:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-text</artifactId>
    </dependency>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
~~~

**BOM import không tương đương parent inheritance:**

- Nhập **dependencyManagement entries** của BOM.
- Không tự nhập `build/plugins`, `pluginManagement`, `repositories`, `profiles`, Java release hay các cấu hình build khác như nhận parent.
- BOM có thể đưa version, managed scope và managed exclusions của entry được import vào effective dependency management.
- `scope=import` chỉ hợp lệ cho dependency POM trong `dependencyManagement`, không phải scope dùng để import JAR vào compile/test.
- Không dùng `<parent>` để "import thêm một BOM" nếu child đã có parent và chỉ muốn lấy bảng version của BOM.

Trong tổ chức lớn, chiến lược phổ biến là **parent quản lý build plugins/JDK/CI**, còn **BOM quản lý tập version dependencies** có thể chia sẻ cho nhiều dự án dùng parent khác nhau.

## 10. Nhiều BOM, parent và child: quy tắc ưu tiên cần kiểm chứng

Các hệ thống phức tạp có thể có:

~~~text
Cấu hình trong child POM
    |
    +-- dependencyManagement khai báo cụ thể ở child
    +-- parent dependencyManagement được kế thừa
    +-- BOM A được import
    +-- BOM B được import
    +-- dependencies ở child (có thể ghi version/scope trực tiếp)
    +-- transitive dependency graph
~~~

Không nên chỉ nói "BOM import cuối cùng luôn thắng". Các quy tắc chính cần hiểu:

1. **Một dependency declaration ở child ghi `<version>` hoặc `<scope>` tường minh** có thể override giá trị managed tương ứng cho chính dependency đó.
2. **Entry trong `dependencyManagement` của child** có thể override entry trùng trong parent management cho child; quản lý hiệu lực cũng phụ thuộc key gồm groupId/artifactId/type/classifier phù hợp.
3. **Entry được khai báo trực tiếp trong importing POM** có ưu tiên so với entry trùng lấy từ BOM import.
4. Khi **hai BOM import** cùng quản lý một key mà importing POM không khai báo trực tiếp key đó, theo ví dụ chính thức của Maven, **BOM được khai báo trước** thường cung cấp entry được chọn.
5. **Dependency management có ưu tiên so với nearest-definition mediation** khi Maven quyết định version của một transitive dependency thuộc phạm vi project dependency graph.
6. **Project dependency management không áp dụng cho transitive dependencies của plugin** trong effective POM, vì plugin realm là môi trường riêng.
7. Nếu child/parent/profile/BOM nhiều tầng và type/classifier khác nhau, đừng suy từ một tên artifactId; hãy kiểm tra effective POM, dependency tree và mục dependency tương ứng.

Ví dụ:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>platform-a-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>platform-b-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Các tọa độ `org.example:platform-a-bom` và `platform-b-bom` **chỉ minh họa** để giải thích thứ tự import; không được hiểu là BOM thật sẵn có. Nếu hai BOM này cùng quản lý `org.example:shared-api` ở hai version khác nhau, nhập BOM A trước thường quyết định entry được chọn trong điều kiện nêu ở trên. Khi cần version cụ thể, khai báo entry rõ ràng ở importing POM và xác minh kết quả.

**Không dùng thứ tự `<modules>` hoặc thứ tự `-P` để suy ra version preference của BOM**. Đó là những cơ chế khác: reactor aggregation, profile selection và dependency management merge.

## 11. Exclusions trong child có thể ghi đè hay bổ sung như thế nào?

Parent/BOM có thể đặt managed exclusion cho một dependency được dùng ở nhiều module. Tuy nhiên, có thể có module cần chính thư viện đã bị excluded. Cách xử lý phải tùy mục đích:

**Tình huống A – Module không dùng transitive artifact bị loại.** Nếu dependency chính vẫn hoạt động và không cần JAR phụ, managed exclusion có thể phù hợp.

**Tình huống B – Module trực tiếp dùng API của artifact đã bị loại.** Module nên khai báo artifact đó **trực tiếp** với version/scope quản lý phù hợp, như `text-core` ở ví dụ mục 8. Exclusion ở nhánh Commons Text không ngăn dependency Lang direct.

**Tình huống C – Module chỉ muốn loại một transitive artifact từ một dependency riêng.** Có thể khai báo exclusion tại **dependency của chính child**, thay vì áp đặt chính sách đó lên tất cả module qua parent.

Ví dụ mảnh child POM (độc lập với ví dụ runnable ở mục 8):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.example.integrations</groupId>
        <artifactId>remote-client</artifactId>
        <version>1.0.0</version>
        <exclusions>
            <exclusion>
                <groupId>org.example.legacy</groupId>
                <artifactId>legacy-logger</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
</dependencies>
~~~

Đây là **tọa độ giả định**. Exclusion này chỉ chặn `legacy-logger` theo đường từ `remote-client`; nếu artifact đến từ dependency khác, phải đánh giá riêng đường đó. Không tự động thêm bản thay thế nếu upstream cần tính năng của nó mà chưa kiểm tra.

Nếu child cần **thay hẳn managed exclusions của parent** cho cùng dependency, không được mặc định thêm một `<exclusions>` rỗng sẽ xóa toàn bộ danh sách được kế thừa. XML/model merge có quy tắc riêng; cách đáng tin là thiết kế management phù hợp nhu cầu chung, đặt exclusion module-specific vào child khi cần, kiểm tra effective POM/graph và tránh quản lý exclusion toàn cục quá mạnh.

**Tuyệt đối không dùng exclusions như công cụ sửa mọi xung đột version.** Nếu mục tiêu là ép một version duy nhất, thử quản lý version rồi kiểm tra compatibility; exclusion chỉ phù hợp khi bạn thực sự muốn cắt một nhánh dependency.

## 12. Chuyển từ một dependency graph không kiểm soát sang quản lý tập trung

Giả sử có hai module:

~~~text
module-a/
  pom.xml: commons-text:1.13.1
           junit-jupiter:5.11.4 test
module-b/
  pom.xml: commons-text:version khác
           junit-jupiter:version khác test
~~~

Khi muốn thống nhất:

**Bước 1 – Xác định baseline có chủ đích.** Chọn version đã được kiểm tra trên JDK/plugin stack của nhóm; không nhất thiết là version cao nhất xuất hiện ở một máy cá nhân.

**Bước 2 – Chuyển version chung sang parent/BOM.** Khai báo managed entries tại `dependencyManagement` với version/scope/managed exclusions thực sự cần.

**Bước 3 – Giữ dependency declarations ở từng module.** Chỉ bỏ những version/scope/exclusion lặp lại khi chắc chắn management hiệu lực là đúng. **Không xóa nguyên dependency** ở module đang dùng API: xóa sẽ làm classpath thiếu JAR.

**Bước 4 – Xác minh scope.** Nếu JUnit được quản lý scope test, đảm bảo code JUnit thuộc `src/test/java`. Nếu module dùng thư viện ở runtime, kiểm tra runtime classpath chứ không chỉ test compile.

**Bước 5 – Xác minh exclusions.** Tìm đúng đường transitive. Chỉ centralize exclusion nếu chính sách đó đúng cho tất cả module liên quan; nếu là nhu cầu riêng, đặt tại module cần nó.

**Bước 6 – Chạy test/build sạch.** Có thể dùng `mvn -B -ntp clean verify`, rồi kiểm tra `dependency:tree` theo từng module và chạy integration tests cần thiết.

**Bước 7 – Nâng version có kiểm soát.** Thay một version trong parent/BOM có thể ảnh hưởng nhiều child, kể cả module không import API ấy trực tiếp nhưng có dependency bắc cầu. Xem graph, API compatibility, security advisory, release notes và kết quả test toàn reactor.

## 13. Công cụ kiểm chứng: effective-pom, dependency:tree, dependency:analyze

### 13.1. Xem effective POM

Lệnh:

~~~bash
mvn -pl :text-core help:effective-pom
mvn -pl :demo-app help:effective-pom
~~~

Giúp thấy mô hình sau khi Maven xử lý POM, parent, profile và managed declarations. Trong `text-core`, kiểm tra:

- Commons Text `1.13.1`, scope compile, managed exclusion Lang.
- Commons Lang `3.17.0` scope compile.
- JUnit Jupiter `5.11.4` scope test.
- Các plugin versions được quản lý trong `pluginManagement`.

Chú ý: **effective POM không luôn phản ánh trực tiếp tất cả quyết định cuối trong dependency graph**, nhất là transitive resolution và conflict mediation. Dùng thêm dependency tree.

### 13.2. Xem dependency tree của từng module

~~~bash
mvn -pl :text-core dependency:tree
mvn -pl :demo-app dependency:tree
mvn -pl :text-core dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Nên kiểm tra phạm vi:

- `text-core` có JUnit test và Commons Text/Lang compile.
- `demo-app` có `text-core` compile; Commons Text/Lang transitively cần cho runtime.
- `demo-app` không tự có JUnit Jupiter của `text-core` vì dependency `test` của một module **không lan sang downstream project** như compile dependency.
- Exclusion của Lang ở nhánh Commons Text không đồng nghĩa Lang biến mất khỏi graph của text-core do có khai báo trực tiếp.

Đối với các plugin đời mới hoặc alias, có thể dùng group/artifact/version đầy đủ:

~~~bash
mvn -pl :text-core org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

**Không viết báo cáo từ một cây dependency tưởng tượng**: output thực tế có thể khác bởi parent/profile, platform BOM khác, settings hoặc cache/version quản lý. Hãy kiểm tra log của đúng môi trường.

### 13.3. Phân tích “used undeclared” và “unused declared”

~~~bash
mvn -pl :text-core org.apache.maven.plugins:maven-dependency-plugin:3.8.1:analyze
~~~

Goal `dependency:analyze` có thể phát hiện mã biên dịch dùng JAR không khai báo trực tiếp hoặc dependency khai báo mà bytecode không thấy được dùng. Nhưng nó có giới hạn vì reflection, service loading, annotation processing, resource-only dependencies và runtime providers không nhất thiết hiện ra trong bytecode. **Không tự động xóa dependency chỉ vì báo “unused declared”**. Đối chiếu thực tế runtime và test.

### 13.4. Kiểm tra classpath runtime khi có exclusions

Để biết `demo-app` có đủ JAR chạy không, từ thư mục `app` sau khi root đã `install`:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath -DincludeScope=runtime -Dmdep.outputFile=target/runtime-deps.txt
~~~

File `runtime-deps.txt` liệt kê các đường dẫn JAR dependency hiệu lực (không mặc định có `target/classes`). Không hard-code file này vào Git vì đường dẫn repository khác nhau theo máy/OS. Dùng `copy-dependencies` và lệnh `java -cp` của mục 8 để quan sát runtime thật.

## 14. Dependency management và plugin management không trùng nhau

Một parent POM có thể có cả hai:

~~~xml
<dependencyManagement>
    <dependencies>
        <!-- Managed project dependencies: commons-text, JUnit... -->
    </dependencies>
</dependencyManagement>

<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đây là **mảnh cấu hình**. Điểm phân biệt:

| Mục | Đối tượng được quản lý | Điều không được suy ra |
| --- | --- | --- |
| `dependencyManagement` | Project dependencies, version/scope/exclusions của chúng. | Không tự thêm JAR vào mã chính, mã test hay plugin realm. |
| `pluginManagement` | Maven plugins, versions/default configurations khi plugin được sử dụng. | Không tự chạy một plugin goal tùy ý. |
| `build/plugins` | Plugin đang cấu hình cho build, có thể có executions. | Không làm thư viện plugin trở thành project dependency. |
| `plugin/dependencies` | Các JAR bổ sung cho class realm của một plugin cụ thể. | Không làm main source tự import được class từ JAR ấy. |
| `project/dependencies` | Các dependency **thật** của project. | Không quyết định plugin realm một cách trực tiếp. |

Ví dụ parent quản lý `maven-compiler-plugin:3.13.0` và Java release `17`; đó là chính sách build. Quản lý `junit-jupiter:5.11.4` scope test là chính sách project dependency. **Hai chính sách phối hợp nhưng không thay thế nhau.**

## 15. Lưu ý về BOM, scope, optional và security

### 15.1. BOM không tự nhập dependencies

Một project có thể import BOM quản lý hàng trăm thư viện nhưng chỉ dùng vài thư viện. Chỉ những dependency module khai báo trực tiếp hoặc nhận transitively qua graph mới đi vào classpath. Điều này giúp BOM tập trung phiên bản mà không làm module phình to vô cớ.

### 15.2. Scope ở BOM/parent là default quản lý, không phải ràng buộc tuyệt đối

Nếu một module cần dependency chỉ để test, có thể ghi `<scope>test</scope>` tại khai báo child cho dependency đó. Nhưng đừng dùng scope `test` để “giảm JAR production” nếu mã main thực sự import API của nó; compile sẽ thất bại hoặc runtime thiếu class.

### 15.3. Optional không giống exclusion

- `optional=true` tại dependency của **thư viện được phát hành** làm dependency đó thường không lan truyền tự động tới consumer; consumer dùng chức năng tương ứng cần khai báo riêng.
- `exclusions` tại dependency **của consumer** chặn một nhánh transitive cụ thể do consumer chỉ định.
- `dependencyManagement` cung cấp quản lý mặc định khi artifact được chọn.

Không dùng ba cơ chế trên thay thế cho nhau.

### 15.4. Không dùng exclusion để che một artifact nguy hiểm mà không xác minh

Nếu một dependency có lỗ hổng bảo mật, loại một đường transitive chưa chắc loại tất cả đường. Dùng `dependency:tree` để xác định những nhánh còn chứa artifact và kiểm tra bằng policy như Maven Enforcer bannedDependencies hoặc công cụ dependency vulnerability scanning theo quy trình tổ chức. Thay version/implementation có thể cần kiểm tra API compatibility và runtime.

### 15.5. Không hard-code secret và repository credentials

POM/BOM thường được commit hoặc publish. Không ghi username/password/token trong `pom.xml`; dùng Maven `settings.xml` với cơ chế credential phù hợp hoặc secret manager/CI connection. Version management không yêu cầu đưa credentials vào managed entries.

### 15.6. Nâng cấp parent/BOM ảnh hưởng nhiều module

Nên có quy trình kiểm tra chéo: build reactor, dependency tree trên module đại diện, integration tests, classpath runtime và compatibility. Một thay đổi version nhỏ ở BOM có thể tác động code chưa được test trực tiếp nếu dependency transitive nằm trong framework phức tạp.

## 16. Những lỗi thường gặp khi quản lý chung

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và sửa |
| --- | --- | --- |
| Child không compile dù parent đã quản lý version thư viện. | Chỉ có entry trong `dependencyManagement`, child chưa khai báo dependency thật. | Thêm `<dependency>` vào `<dependencies>` của child. |
| JUnit xuất hiện ở một module không có test JUnit. | JUnit bị khai báo trong parent `dependencies` và được kế thừa. | Nếu mục tiêu là cho con tự chọn, chuyển JUnit sang `dependencyManagement`; cân nhắc tác động các module. |
| JUnit có trên runtime classpath của app ngoài mong muốn. | Scope được chọn sai hoặc dependency được khai báo là compile ở child/qua graph khác. | Xem effective POM và dependency tree theo module. |
| Child dùng version khác version parent quản lý. | Child ghi version tường minh, quản lý cục bộ hoặc import BOM khác. | So dependency declaration, child/parent management và thứ tự import. |
| BOM import thành công nhưng plugin compiler version không đổi. | BOM nhập dependency management, không nhập plugin management. | Quản lý plugin qua parent `pluginManagement` hoặc plugin config. |
| `commons-lang3` còn trong dependency tree dù đã exclude từ Commons Text. | Exclusion chỉ theo nhánh; module còn khai báo Lang trực tiếp hoặc nhánh khác kéo nó vào. | Xem toàn graph; xác định path, không suy từ tên artifact xuất hiện. |
| Ứng dụng `NoClassDefFoundError` sau khi exclude. | Đã loại transitive artifact mà upstream implementation vẫn cần. | Cân nhắc bỏ exclusion hoặc khai báo dependency phù hợp; test runtime. |
| Version được managed gây `NoSuchMethodError`. | Version bắt buộc không tương thích API mà thư viện khác sử dụng. | Kiểm tra dependency tree, minimum supported version và compatibility. |
| `mvn -pl :demo-app package` thất bại vì thiếu `text-core`. | Module phụ thuộc chưa có trong repository hoặc chưa được build cùng reactor. | Chạy root `mvn install` hoặc chọn `-am` để build modules dependency. |
| Child chứa dependency `scope=test` nhưng main code import nó. | Scope không đúng cho main compile. | Chuyển code về test source hoặc chọn dependency/scope phù hợp. |
| Nhiều BOM quản lý một key gây version ngoài dự đoán. | Thứ tự import và entry ở importing POM/parent/child tác động. | Xem effective POM, theo dõi entry trùng, xác minh kết quả. |
| Lỗi class của Maven plugin dù project dependencies đúng. | Plugin realm riêng; project dependency management không tác động plugin transitive graph. | Xem plugin version, plugin dependencies và stack trace. |
| Dependency phân tích là “unused” nhưng xóa thì runtime hỏng. | Reflection, JDBC driver, SPI hoặc resource được tải động. | Kiểm tra integration/runtime trước khi bỏ dependency. |
| Parent POM không resolve được khi chạy riêng child. | Tọa độ `<parent>` sai, `relativePath` sai hoặc parent chưa cài/phát hành. | So groupId/artifactId/version và Maven repo, build root khi có source parent. |

**Cách debug nên bắt đầu ở đúng module:** xác định module nào có source sử dụng API → xem dependency declaration của module → xem effective management → chạy dependency tree → kiểm tra test/runtime. Đừng chỉnh exclusions hàng loạt trên parent để “sửa nhanh” mọi module.

## 17. Checklist triển khai dependency policy cho nhiều module

- [ ] Mỗi child khai báo **dependency trực tiếp thực sự dùng**, không chỉ trông chờ parent quản lý.
- [ ] Parent/BOM quản lý **version đã được nhóm kiểm thử**, không sao chép version vào từng child khi không cần.
- [ ] Scope chung `test`/`runtime`/`compile` được chọn có chủ đích; child chỉ override khi có lý do.
- [ ] Exclusions có **lý do và nhánh cụ thể**, không bị hiểu nhầm là global ban.
- [ ] Nếu loại một JAR mà upstream code cần, có dependency thay thế phù hợp hoặc đã kiểm chứng runtime không cần nó.
- [ ] Không đưa dependency chỉ dành cho vài module vào parent `<dependencies>` nếu muốn các module chọn độc lập.
- [ ] BOM import nằm đúng trong `dependencyManagement` với `type=pom` và `scope=import`.
- [ ] Parent inheritance và BOM import được phân biệt; BOM không quản lý plugin version.
- [ ] Nếu nhiều BOM có entry trùng, kiểm tra quy tắc ưu tiên, thứ tự import và effective POM.
- [ ] Đã kiểm tra dependency tree của từng module quan trọng, không chỉ tree của parent.
- [ ] Có bài test và kiểm tra runtime thực tế sau khi thay scope/exclusions.
- [ ] Build đa module đúng thứ tự, dùng reactor `-am` hoặc `install` nếu cần chạy riêng một child.
- [ ] Có kế hoạch nâng parent/BOM, quét vulnerability và kiểm tra license tương ứng.

## 18. Câu hỏi tự kiểm tra

1. **Parent có `<dependencyManagement>` chứa JUnit, tất cả module có tự nhận JUnit không?**  
   Không. `dependencyManagement` chỉ quản lý entry; module cần khai báo dependency (hoặc nhận qua một đường transitive hợp lệ) để đưa JAR vào classpath.

2. **Nếu parent quản lý JUnit scope test, child viết dependency chỉ gồm groupId/artifactId, scope là gì?**  
   Scope test sẽ được áp dụng theo entry management phù hợp.

3. **Child ghi `<scope>compile</scope>` cho dependency mà parent quản lý scope test thì sao?**  
   Child đang cung cấp scope tường minh; kiểm tra effective POM/graph, không giả định scope parent luôn ép mọi child.

4. **Exclusion `commons-lang3` trên Commons Text có cấm Lang ở tất cả module không?**  
   Không. Nó loại Lang qua nhánh Commons Text được áp dụng; một dependency Lang direct hoặc đường khác vẫn có thể đưa Lang vào.

5. **Vì sao bài mẫu vẫn khai báo Commons Lang trực tiếp ở text-core khi đã exclude nó từ Commons Text?**  
   Vì source text-core trực tiếp gọi `StringUtils` và Commons Text có thể cần Lang lúc chạy; exclusion được dùng để minh họa cách kiểm soát từng nhánh, không phải xóa hẳn Lang khỏi project.

6. **BOM import bằng `scope=import` có tự mang theo compiler plugin version không?**  
   Không. Nó nhập dependency management; plugin cần quản lý qua parent/pluginManagement hoặc cấu hình tương ứng.

7. **Nếu hai BOM cùng quản lý một artifact ở hai version, BOM cuối có luôn thắng?**  
   Không. Khi importing POM chưa tự định nghĩa entry đó, Maven cho phép entry của BOM import trước được chọn; cần xem effective model để xác nhận.

8. **Vì sao cùng root `<modules>` chưa đủ để app compile với class text-core?**  
   Aggregation chỉ giúp reactor biết project nào để build. `app/pom.xml` vẫn cần dependency vào `text-core`.

9. **Maven project dependencyManagement có thay version thư viện nội bộ của Surefire Plugin không?**  
   Không trực tiếp. Plugin dependencies thuộc plugin class realm; cơ chế quản lý khác.

10. **Một dependency đã quản lý version có chắc tương thích với mọi upstream?**  
    Không. Quản lý version giúp nhất quán, nhưng không thay thế kiểm tra tương thích binary, test và vulnerability review.

## 19. Tài liệu tham khảo

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): dependency management, scope, transitivity, BOM import và precedence.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): cấu trúc POM, `dependencies`, `dependencyManagement` và inheritance.
- [Apache Maven — Optional & Exclusion Dependencies](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html): exclusion theo dependency edge, optional và các giới hạn.
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor, inheritance vs aggregation, `-pl` và `-am`.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xem graph, version và scope hiệu lực.
- [Apache Maven Dependency Plugin — dependency:analyze](https://maven.apache.org/plugins/maven-dependency-plugin/analyze-mojo.html): phát hiện thiếu/thừa dependency theo bytecode.
- [Apache Maven Dependency Plugin — copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): chuẩn bị các JAR cho runtime classpath.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): kiểm tra cấu hình sau inheritance và profile.
- [Maven Central — Commons Text 1.13.1 POM](https://central.sonatype.com/artifact/org.apache.commons/commons-text/1.13.1/jar): xác minh Commons Text phụ thuộc Commons Lang 3.17.0 trong ví dụ.

**Tổng kết:** Parent POM và BOM giúp thống nhất **version, scope và exclusions**, nhưng **mỗi module vẫn phải chọn dependency mình cần**. Exclusions **chỉ loại trên nhánh dependency cụ thể**, không phải lệnh cấm toàn graph. Khi có nhiều tầng parent/BOM/child, dùng **effective POM**, **dependency tree** và kiểm thử **runtime** để xác nhận chính sách quản lý đã có tác dụng đúng thay vì chỉ đọc vài dòng XML.
