# Kiểm tra phiên bản Surefire/Failsafe trước khi dựa vào tùy chọn bỏ qua

## 1. Vì sao phải kiểm tra phiên bản trước khi gõ `-DskipTests`?

Trong Maven, một lệnh quen thuộc như:

```bash
mvn clean verify -DskipTests=true
```

không có một ý nghĩa bất biến đối với **mọi phiên bản Maven Surefire và Maven Failsafe Plugin**. Trên một số bản Failsafe cũ, nó có thể khiến cả unit tests lẫn integration tests đều bị bỏ qua. Nhưng **từ Failsafe 3.6.0**, `-DskipTests` mặc định **không còn bỏ qua integration tests của Failsafe**; nó vẫn bỏ qua unit tests do Surefire chạy.

Sự khác biệt này rất đáng chú ý nếu CI từng dùng `-DskipTests` để “đóng gói nhanh không chạy test”, rồi nâng plugin mà không rà soát script. Sau nâng cấp, integration test có thể vẫn được thực thi, chạm database, external services hoặc làm job thất bại ngoài dự kiến.

**Các nguyên tắc cần nhớ:**

- `-DskipTests=true`: bỏ qua **việc chạy unit tests của Surefire**; trên Failsafe **3.6.0+** thì **không tự bỏ qua integration tests** theo user-property binding mặc định.
- `-DskipITs=true`: yêu cầu **Failsafe bỏ qua integration tests**.
- `-DskipTests=true -DskipITs=true`: rõ ràng bỏ qua **chạy cả hai loại test**, nhưng theo mặc định **test source vẫn được biên dịch**.
- `-Dmaven.test.skip=true`: yêu cầu **Compiler Plugin, Surefire và Failsafe** bỏ qua **biên dịch test** và **thực thi test**.
- **Cấu hình POM/parent/profile có thể đổi tác dụng thực tế**: nếu Failsafe khai `<skipITs>${skipTests}</skipITs>` thì property `skipTests` trên CLI lại có thể tác động Failsafe dù binding mặc định ở 3.6.x đã thay đổi.

Bài học dùng **Surefire 3.6.1 và Failsafe 3.6.1** làm ví dụ chính, đồng thời đối chiếu hành vi Failsafe 3.5.x. Mục tiêu không phải học thuộc mọi biến thể mà là biết **xác minh version, user property, effective POM và test reports** trước khi kết luận.

## 2. Phân biệt hai plugin và vị trí trong Maven lifecycle

Maven Surefire Plugin và Maven Failsafe Plugin thuộc cùng hệ sinh thái nhưng được sử dụng cho các loại kiểm thử khác nhau:

| Đặc điểm | Surefire | Failsafe |
| --- | --- | --- |
| Mục đích phổ biến | Unit tests | Integration tests |
| Goal thực thi | `surefire:test` | `failsafe:integration-test` |
| Goal kiểm tra cuối | Kết quả thường làm fail tại goal test | `failsafe:verify` đánh giá kết quả IT |
| Phase | `test` | `integration-test` và `verify` |
| Pattern tên lớp mặc định | `*Test.java`, `Test*.java`, `*Tests.java`, `*TestCase.java` | `*IT.java`, `IT*.java`, `*ITCase.java` |
| Thư mục báo cáo | `target/surefire-reports` | `target/failsafe-reports` |
| Skip thực thi riêng | `-DskipTests=true` | `-DskipITs=true` |
| Skip biên dịch test chung | `-Dmaven.test.skip=true` | `-Dmaven.test.skip=true` |

Pattern mặc định có thể được thay đổi bằng `includes/excludes`, provider hoặc cấu hình test discovery; tên class không đủ chứng minh một test được chạy.

### Maven lifecycle có các phase nào liên quan?

```text
validate
  |
compile
  |
test-compile
  |
test                   -> surefire:test
  |
package
  |
pre-integration-test
  |
integration-test       -> failsafe:integration-test (nếu cấu hình)
  |
post-integration-test
  |
verify                 -> failsafe:verify (nếu cấu hình)
```

Với project packaging `jar`, Surefire thường được lifecycle bind vào phase `test`. Failsafe **không tự chạy IT chỉ vì dependency JUnit hoặc file `*IT.java` có trong project**: cần cấu hình plugin/executions phù hợp.

### Vì sao Failsafe tách `integration-test` và `verify`?

Failsafe không dừng build ngay lập tức tại phase `integration-test` khi bài IT thất bại, để các bước dọn môi trường tại `post-integration-test` còn có cơ hội chạy. Sau đó `failsafe:verify` đọc kết quả và làm build fail khi thích hợp.

Vì vậy để xác nhận **đầy đủ integration tests**, nên dùng:

```bash
mvn clean verify
```

Không dùng riêng `mvn integration-test` làm bằng chứng toàn bộ kiểm thử đã được xác minh: phase `verify` chưa xảy ra. Tương tự, `mvn test` dừng trước các phase Failsafe thường dùng.

## 3. Bảng ý nghĩa của các flag trên Failsafe 3.6.1

Bảng dưới áp dụng khi POM **không chủ động ánh xạ các cờ khác** vào cấu hình plugin, đồng thời Failsafe `integration-test` và `verify` đã được bind đúng:

| Lệnh | Surefire unit tests | Failsafe integration tests | Biên dịch `src/test/java` |
| --- | --- | --- | --- |
| `mvn clean verify` | Chạy | Chạy | Có |
| `mvn clean verify -DskipTests=true` | Bỏ qua chạy | **Vẫn chạy** | Có |
| `mvn clean verify -DskipITs=true` | **Vẫn chạy** | Bỏ qua chạy | Có |
| `mvn clean verify -DskipTests=true -DskipITs=true` | Bỏ qua chạy | Bỏ qua chạy | Có |
| `mvn clean verify -Dmaven.test.skip=true` | Bỏ qua chạy | Bỏ qua chạy | **Bỏ qua** |
| `mvn clean verify -DskipTests=false -DskipITs=false` | Chạy | Chạy | Có |

**Không áp dụng nguyên bảng cho Failsafe 3.5.x.** Với các bản cũ mà tham số `skipTests` của Failsafe được gắn vào property `skipTests`, lệnh `-DskipTests` có thể làm cả hai plugin skip. Từ Failsafe 3.6.0, user-property binding này được bỏ: muốn chỉ skip IT dùng `skipITs`.

### `skipTests` và `maven.test.skip` không tương đương

Khi bạn dùng:

```bash
mvn clean verify -DskipTests=true -DskipITs=true
```

Maven vẫn thực hiện phase `test-compile` trong cấu hình bình thường. Do đó lỗi Java syntax hoặc dependency thiếu trong `src/test/java` **vẫn có thể khiến build fail**, dù không có test method nào chạy.

Nhưng với:

```bash
mvn clean verify -Dmaven.test.skip=true
```

Maven Compiler Plugin bỏ `testCompile`, còn Surefire/Failsafe bỏ test execution. Cờ này mạnh hơn nhiều: build có thể thành công dù test source đang không biên dịch được.

**Lưu ý:** `maven.test.skip` tác động đến **test compilation**, không tự bỏ biên dịch `src/main/java`. Một project có các plugin tùy biến phụ thuộc test output vẫn có thể gặp lỗi khác khi bỏ test compilation.

### Cách viết cờ trong shell

```bash
mvn verify -DskipTests
mvn verify -DskipTests=true
```

Đối với boolean property này, cả hai dạng thường được hiểu là bật. Để script/CI dễ đọc, hãy ưu tiên ghi tường minh `=true` hoặc `=false`.

## 4. Thay đổi quan trọng giữa Failsafe 3.5.x và 3.6.x

### Trước 3.6.0

Tài liệu archived của Failsafe 3.5.6 mô tả:

```bash
mvn install -DskipTests
```

có thể bỏ qua test của cả Surefire và Failsafe. `skipTests` là user property được plugin Failsafe bản đó tiếp nhận. Khi muốn chỉ bỏ integration tests, dùng `-DskipITs`.

### Từ 3.6.0

Failsafe đánh dấu tham số `skipTests` **deprecated**, và nó **không còn bind với user property `skipTests`**. Tài liệu 3.6.x phân biệt rõ:

```bash
# Skip unit tests của Surefire, Failsafe IT vẫn chạy:
mvn clean verify -DskipTests=true

# Skip integration tests của Failsafe, unit tests vẫn chạy:
mvn clean verify -DskipITs=true

# Skip thực thi cả hai loại test:
mvn clean verify -DskipTests=true -DskipITs=true

# Skip cả biên dịch test:
mvn clean verify -Dmaven.test.skip=true
```

Đây là hành vi **mặc định** không bị POM custom override. Nếu bạn sửa từ một build cũ, không nên chỉ nâng version trong POM rồi giữ nguyên quan niệm cũ về skip flags.

### `<skipTests>` trong cấu hình Failsafe vẫn có thể hoạt động

Từ 3.6.x, điều bị loại bỏ là **tự gán user property `skipTests` cho tham số Failsafe**, không phải lập tức cấm mọi XML cấu hình có tên `<skipTests>`.

Ví dụ dưới đây là một **plugin fragment**, không phải POM độc lập:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.6.1</version>
    <configuration>
        <skipTests>true</skipTests>
    </configuration>
</plugin>
```

Failsafe 3.6.x vẫn có thể tôn trọng giá trị này theo tài liệu tham số, dù nó đã deprecated. Cách đặt **rõ ý định** hơn là:

```xml
<configuration>
    <skipITs>true</skipITs>
</configuration>
```

Nhưng **đừng commit skip=true cố định** nếu công việc cần chạy IT trong CI: integration tests có thể bị bỏ qua không ai chú ý.

## 5. Tìm phiên bản Surefire/Failsafe thực tế trong dự án

### 5.1. `mvn -version` không trả lời version Surefire/Failsafe

```bash
mvn -version
```

Lệnh này hiển thị version Maven distribution và Java runtime chạy Maven. Dù Maven 3.9.x đang chạy, plugin Surefire có thể là 2.22.2, 3.2.5, 3.5.6 hoặc 3.6.1, tùy POM và cấu hình kế thừa.

Không kết luận “Surefire 3.6.1” chỉ vì đang dùng Maven mới.

### 5.2. Kiểm tra trong POM

Plugin version có thể được khai trực tiếp:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.6.1</version>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <version>3.6.1</version>
        </plugin>
    </plugins>
</build>
```

Hoặc quản lý tại parent `build/pluginManagement`. Nếu plugin version được quản lý nhưng một plugin chưa được kích hoạt, nó có thể **không chạy**. Cụ thể, Surefire thường có default lifecycle binding cho `jar`, còn Failsafe thường đòi execution tùy project.

**Không nhầm version JUnit dependency với version Surefire Plugin.** `org.junit.jupiter:junit-jupiter:5.11.4` là thư viện test, không phải Maven test runner version.

### 5.3. Kiểm tra effective POM và active profiles

```bash
mvn help:effective-pom
mvn help:effective-pom -Dverbose
mvn help:active-profiles
```

Với multi-module, hãy dùng đúng POM:

```bash
mvn -f modules/customer-service/pom.xml help:effective-pom
```

Path module chỉ minh họa. Trong effective POM tìm:

```text
maven-surefire-plugin
maven-failsafe-plugin
<version>...</version>
<skipTests>...</skipTests>
<skipITs>...</skipITs>
<executions>...</executions>
```

Cấu hình thực tế có thể đến từ parent, profile, `pluginManagement` hoặc child override. **Một mục trong pluginManagement không tự chứng minh plugin đã chạy.** Cần xem cả `build/plugins`, lifecycle binding và logs.

### 5.4. Kiểm tra plugin version thật trong build log

```bash
mvn -B -ntp clean verify
```

Tìm plugin headers có dạng:

```text
--- surefire:3.6.1:test (...) @ skip-demo ---
--- failsafe:3.6.1:integration-test (...) @ skip-demo ---
--- failsafe:3.6.1:verify (...) @ skip-demo ---
```

Đây là **hình thức log minh họa**, không phải stdout nguyên văn: execution ID, prefix/log layout có thể khác. Hãy xác định **plugin name, version, goal và module** thực sự.

Nếu không thấy Failsafe, có thể `failsafe:integration-test`/`failsafe:verify` chưa được bind hoặc Maven chưa chạy tới phase đó. Không tự suy ra rằng cờ skip đã có hiệu lực.

### 5.5. Xem parameters và User Property đúng phiên bản

```bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-surefire-plugin -Dgoal=test -Ddetail
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-failsafe-plugin -Dgoal=integration-test -Ddetail
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-failsafe-plugin -Dgoal=verify -Ddetail
```

Hoặc gọi mục trợ giúp bằng tọa độ đầy đủ và version pin:

```bash
mvn org.apache.maven.plugins:maven-surefire-plugin:3.6.1:help -Ddetail=true -Dgoal=test
mvn org.apache.maven.plugins:maven-failsafe-plugin:3.6.1:help -Ddetail=true -Dgoal=integration-test
mvn org.apache.maven.plugins:maven-failsafe-plugin:3.6.1:help -Ddetail=true -Dgoal=verify
```

Các goal `help` phải được Maven resolve plugin từ repository nếu chưa có cache. Trong kết quả mô tả tìm `skipTests`, `skipITs`, `skip`, `skipExec` và **User Property**. Nhờ đó biết cờ CLI nào thực sự ánh xạ tới parameter.

## 6. Ví dụ Java 17 hoàn chỉnh: quan sát unit test và integration-style test

Ví dụ này dùng **một module** Java 17. Hai test classes đều đơn giản, không cần database; hậu tố `IT` chỉ để minh họa cách Failsafe nhận diện integration-test class. Dự án yêu cầu Maven 3.6.3+ tương thích plugin versions, JDK 17+, Internet hoặc Maven repository mirror có JUnit/plugins.

### 6.1. Cấu trúc thư mục

```text
skip-demo/
├── pom.xml
└── src/
    ├── main/java/dev/lesson/Sum.java
    └── test/java/dev/lesson/
        ├── SumTest.java
        └── SumIT.java
```

### 6.2. `skip-demo/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>skip-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.1</version>
                <executions>
                    <execution>
                        <id>run-integration-tests</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích từng phần:**

- `maven.compiler.release=17` yêu cầu Compiler Plugin tạo Java 17 bytecode và dùng Java 17 platform APIs.
- `junit-jupiter` với `scope=test` cung cấp JUnit Jupiter API và engine cho các tests.
- Surefire phiên bản **3.6.1** chạy tests `*Test.java` theo lifecycle mặc định.
- Failsafe phiên bản **3.6.1** có execution gồm `integration-test` và `verify`, các goal được bind tới default phases phù hợp.
- POM **không khai `skipTests` hoặc `skipITs` cố định**, tránh các custom mapping che kết quả thực nghiệm.
- Project không cần thêm plugin cho database hoặc server; đây là ví dụ test lifecycle tối giản.

### 6.3. Main source `src/main/java/dev/lesson/Sum.java`

```java
package dev.lesson;

public final class Sum {
    private Sum() {
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static void main(String[] args) {
        System.out.println("SUM=" + add(2, 3));
    }
}
```

### 6.4. Unit test `src/test/java/dev/lesson/SumTest.java`

```java
package dev.lesson;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class SumTest {
    @Test
    void addsNumbers() {
        assertEquals(5, Sum.add(2, 3));
    }
}
```

Tên `SumTest` khớp pattern Surefire; test có một assertion và không in stdout tùy ý.

### 6.5. Integration-style test `src/test/java/dev/lesson/SumIT.java`

```java
package dev.lesson;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class SumIT {
    @Test
    void handlesNegativeResult() {
        assertEquals(-1, Sum.add(2, -3));
    }
}
```

Tên `SumIT` khớp pattern Failsafe. Dù đây là một assertion đơn giản chứ không tích hợp hệ thống ngoài, nó giúp phân biệt **plugin nào thực sự thực thi class**.

### 6.6. Chạy baseline không skip

Từ thư mục `skip-demo/`:

```bash
mvn -version
mvn -B -ntp clean verify
```

Khi dependency resolve và test pass, kết quả **về mặt nội dung**:

```text
Surefire: chạy dev.lesson.SumTest, 1 test passed
Failsafe: chạy dev.lesson.SumIT, 1 test passed
Build: SUCCESS
```

Đây là **tóm tắt kết quả mong đợi**, không phải stdout Maven nguyên văn. Log thực có thêm headers, tên plugin, execution ID, các cột Runs/Failures/Errors/Skipped.

Vì chạy `clean` trước `verify`, các report files mới thường xuất hiện:

```text
target/surefire-reports/TEST-dev.lesson.SumTest.xml
target/failsafe-reports/TEST-dev.lesson.SumIT.xml
target/failsafe-reports/failsafe-summary.xml
target/test-classes/dev/lesson/SumTest.class
target/test-classes/dev/lesson/SumIT.class
```

Báo cáo cụ thể phụ thuộc phiên bản/provider/config. Hãy xem **Tests run** trong report XML/text và test class names, không chỉ `BUILD SUCCESS`.

### 6.7. Thí nghiệm A — chỉ skip Surefire

```bash
mvn -B -ntp clean verify -DskipTests=true
```

Với POM mẫu, dự kiến:

- `SumTest` không được thực thi bởi Surefire.
- `SumIT` **vẫn được thực thi** bởi Failsafe 3.6.1.
- Test source vẫn biên dịch, có `target/test-classes`.
- Build pass nếu IT pass.

Đây là điểm mà tài liệu archived Failsafe 3.5.6 có thể cho kết quả khác. Do đó phải kiểm tra version trước khi dùng cờ.

### 6.8. Thí nghiệm B — chỉ skip Failsafe

```bash
mvn -B -ntp clean verify -DskipITs=true
```

Với POM mẫu:

- `SumTest` được Surefire chạy.
- Failsafe bỏ qua `SumIT` và việc đánh giá IT tương ứng.
- Test sources vẫn được biên dịch.

### 6.9. Thí nghiệm C — skip thực thi cả hai, vẫn compile test sources

```bash
mvn -B -ntp clean verify -DskipTests=true -DskipITs=true
```

Với POM mẫu:

- Cả Surefire và Failsafe đều bỏ qua **thực thi tests**.
- `SumTest.class` và `SumIT.class` vẫn có thể được Compiler Plugin tạo trong `target/test-classes`.
- Main classes/JAR vẫn build thông thường.

Đây là lựa chọn phù hợp hơn nếu bạn muốn tiết kiệm thời gian chạy tests **nhưng vẫn phát hiện lỗi biên dịch test sources**.

### 6.10. Thí nghiệm D — skip luôn việc biên dịch tests

```bash
mvn -B -ntp clean verify -Dmaven.test.skip=true
```

Dự kiến:

- Compiler Plugin bỏ test compilation.
- Surefire/Failsafe bỏ test execution.
- Main sources vẫn được compile; JAR có thể được đóng gói.
- Sau `clean`, thường không có các file test class mới trong `target/test-classes`.

**Cảnh báo:** đây không phải cách “chỉ bỏ unit tests”; nó bỏ hẳn một lớp kiểm tra quan trọng.

### 6.11. Chạy Java main và phân biệt với test result

Sau một lần build thành công:

```bash
java -cp target/classes dev.lesson.Sum
```

**Stdout chính xác của chương trình Java main:**

```text
SUM=5
```

Dòng `SUM=5` chỉ chứng minh main class chạy được. Nó **không** chứng minh Surefire hoặc Failsafe đã thực thi tests. Để xác minh test thực sự chạy, phải dùng logs và reports.

## 7. Nếu test source bị lỗi compile thì mỗi cờ xử lý ra sao?

Giả sử `SumTest.java` có một dòng cố tình sai:

```java
// Đoạn minh họa lỗi; KHÔNG dùng thay cho test source chuẩn:
int value = "not an integer";
```

Đây là **dòng Java cố ý không compile**, dùng để hiểu cơ chế.

Với:

```bash
mvn clean verify -DskipTests=true -DskipITs=true
```

Compiler Plugin vẫn biên dịch `src/test/java` nên có thể fail ở `test-compile`, **trước khi Surefire/Failsafe kịp bỏ thực thi**.

Với:

```bash
mvn clean verify -Dmaven.test.skip=true
```

bước test compilation bị bỏ qua và lỗi ấy có thể không được phát hiện trong invocation đó.

Sau thí nghiệm, hoàn nguyên source và chạy full tests. Không để cờ `maven.test.skip` làm CI báo PASS trong khi test sources đã hỏng.

## 8. Khi POM tự ánh xạ cờ, hành vi có thể đổi

### 8.1. Mapping một property tùy chỉnh cho cả hai plugin

Trong một parent POM, có thể thấy:

```xml
<properties>
    <skipAllTests>false</skipAllTests>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.6.1</version>
            <configuration>
                <skipTests>${skipAllTests}</skipTests>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <version>3.6.1</version>
            <configuration>
                <skipITs>${skipAllTests}</skipITs>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây chỉ là **đoạn cấu hình**; cần thêm Failsafe executions nếu muốn các ITs được bind. Trong trường hợp này:

```bash
mvn clean verify -DskipAllTests=true
```

có thể bỏ chạy cả hai suites do **tự mapping qua POM**, không phải do plugin tự biết property `skipAllTests`.

### 8.2. Failsafe 3.6.x vẫn có thể bị tác động bởi `skipTests` theo custom POM

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.6.1</version>
    <configuration>
        <skipITs>${skipTests}</skipITs>
    </configuration>
</plugin>
```

Với POM dạng này, `-DskipTests=true` có thể làm Failsafe skip ITs **thông qua biểu thức cấu hình**. Điều đó không trái với tài liệu Failsafe 3.6.x: plugin chỉ **không tự gắn** tham số `skipTests` với user property `skipTests` theo mặc định nữa.

Vì thế khi gặp “đã dùng Failsafe 3.6.1 nhưng kết quả khác bảng”, việc đầu tiên là xem **effective POM** và active profiles.

### 8.3. `pluginManagement` có phải tự chạy Failsafe?

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Không. Đây là phần **quản lý version/configuration** cho plugin khi nó được dùng. Nếu Failsafe không có executions được kích hoạt, `mvn verify` có thể không chạy một IT nào. Không nhầm việc “không chạy IT” do Failsafe **không được bind** với “không chạy IT” do `skipITs`.

## 9. Những cờ thường bị nhầm là skip

| Tham số/property | Thực chất làm gì | Vì sao không thay skip flags? |
| --- | --- | --- |
| `maven.test.failure.ignore=true` | Cho phép build tiếp tục dù có test failures theo plugin behavior | **Tests vẫn chạy**, nhưng failure có thể bị bỏ qua |
| `test=SumTest` | Lọc unit test class Surefire chạy | Không tắt mọi test |
| `it.test=SumIT` | Lọc integration test Failsafe chạy | Không tắt mọi IT |
| `failIfNoTests=false` | Điều chỉnh xử lý tình huống không tìm thấy test | Không làm test thất bại trở thành pass |
| `maven.test.skip.exec=true` | Property cũ cho `skipExec` | **Deprecated**; không khuyến nghị dùng |
| `skipAfterFailureCount` | Dừng sau số test failures nhất định khi được hỗ trợ | Không phải skip toàn bộ tests; Surefire/Failsafe có property riêng |
| `maven.test.skip=true` | Bỏ test compilation/execution | Mạnh hơn skip runtime, không dùng nếu muốn giữ test compile |

Khi dùng một tên tham số mới, hãy tra **goal parameter documentation đúng version**. Chẳng hạn một plugin có thể có parameter trong XML nhưng không có user property tương ứng, hoặc thay binding theo version.

## 10. Rủi ro trong CI và khi nâng plugin

### 10.1. Một command CI cũ đổi nghĩa sau upgrade

Job có:

```bash
mvn -B -ntp clean deploy -DskipTests
```

Khi team nâng Failsafe từ 3.5.x lên 3.6.x, integration tests có thể bắt đầu chạy trong job deploy. Nếu test thiết lập container, kết nối DB hoặc cần secret, hệ quả có thể là kéo dài build, lỗi environment, hoặc gây side effect không mong muốn.

Nên tách các job:

- **Unit test job:** `mvn clean test`.
- **Full verification job:** `mvn clean verify`; xác minh Surefire và Failsafe report counts.
- **Build không chạy test có lý do riêng:** `mvn clean package -DskipTests=true -DskipITs=true` khi cần (chú ý `package` vốn chưa vào phase Failsafe thông thường).
- **Biên dịch test cũng bị bỏ:** `mvn clean package -Dmaven.test.skip=true` chỉ trong trường hợp thật sự có lý do hợp lệ.

Nếu project có custom executions trước `package` hoặc plugin khác, mọi command vẫn cần kiểm tra effective lifecycle.

### 10.2. Chạy test nào để chứng minh migration an toàn?

Sau nâng plugin:

1. Chạy `mvn clean verify` **không có skip flags**.
2. Kiểm tra một số test class cụ thể từ mỗi loại đã chạy và PASS.
3. Chạy `mvn clean verify -DskipTests=true` và xác nhận Surefire skip/Failsafe chạy.
4. Chạy `mvn clean verify -DskipITs=true` và xác nhận Surefire chạy/Failsafe skip.
5. Nếu cần, chạy cả hai flags và đối chiếu test compilation.
6. Cập nhật CI scripts, tài liệu team, build matrix và release checklist.

Không chỉ thay version plugin rồi dựa vào `BUILD SUCCESS`, vì build có thể báo thành công khi **0 tests được chạy**.

### 10.3. Multi-module khác nhau

Một reactor có thể chứa:

- Module A chỉ có unit tests.
- Module B chứa integration tests và bind Failsafe.
- Module C là parent/aggregator packaging `pom`.
- Module D có profile test riêng.

Cùng một command ở root có thể cho hành vi khác nhau theo module. Trong logs và reports cần ghi **module name + plugin version + test count**, không gom tất cả thành một kết luận “Surefire đã chạy”.

## 11. Đọc Surefire và Failsafe reports đúng cách

Sau `mvn clean verify`, các report files thường có dạng:

```text
target/surefire-reports/
    TEST-dev.lesson.SumTest.xml
    dev.lesson.SumTest.txt

target/failsafe-reports/
    TEST-dev.lesson.SumIT.xml
    dev.lesson.SumIT.txt
    failsafe-summary.xml
```

Một report file có thể không tồn tại khi test runner bị skip. Các plugin versions/providers khác nhau có thể thay output chi tiết, nhưng tên thư mục là quy ước phổ biến.

Để chấm build có chạy test hay không:

- Kiểm tra `Tests run` của Surefire và Failsafe riêng.
- Xem `Failures`, `Errors`, `Skipped`.
- Đọc test class names để chắc chắn đúng suite.
- Dùng `clean` tránh report cũ làm bằng chứng sai.
- Nếu không có reports, xem lý do plugin không chạy: không bind, phase chưa tới, cờ skip, test discovery không khớp.
- Nếu có IT failures, bảo đảm `failsafe:verify` đã chạy và báo trạng thái thích hợp.

**BUILD SUCCESS không bằng TESTS PASS.** Một build không có test nào vẫn có thể success. Báo cáo chất lượng phải nêu **tests thực thi thực tế**.

## 12. Quy trình chẩn đoán khi cờ skip không như dự đoán

### Bước 1: lấy POM và plugin versions thực tế

```bash
mvn -version
mvn help:active-profiles
mvn help:effective-pom
```

Xác định chính xác Surefire/Failsafe versions, binding và skip config; không suy từ Maven version.

### Bước 2: chạy baseline không skip

```bash
mvn -B -ntp clean verify
```

Xác minh có cả `surefire:test` và `failsafe:integration-test`/`failsafe:verify` trong log nếu project cần cả hai suites.

### Bước 3: kiểm tra skip từng plugin

```bash
mvn -B -ntp clean verify -DskipTests=true
mvn -B -ntp clean verify -DskipITs=true
mvn -B -ntp clean verify -DskipTests=true -DskipITs=true
mvn -B -ntp clean verify -Dmaven.test.skip=true
```

Mỗi invocation đều có `clean` nên report lần trước không bị lấy nhầm. Chỉ chạy tất cả trong môi trường phù hợp, vì integration tests thật có thể cần resources và services.

### Bước 4: so sánh với docs goal version

```bash
mvn org.apache.maven.plugins:maven-failsafe-plugin:3.6.1:help -Ddetail=true -Dgoal=integration-test
mvn org.apache.maven.plugins:maven-failsafe-plugin:3.6.1:help -Ddetail=true -Dgoal=verify
```

Tra `skipTests`, `skipITs` và user properties. Với Failsafe khác version, thay số phiên bản trong command.

### Bước 5: đọc log chi tiết khi cần

```bash
mvn -B -ntp -e clean verify
mvn -B -ntp -X clean verify
```

`-e` hỗ trợ stacktrace; `-X` có nhiều thông tin resolver/goal/parameters nhưng có thể lộ đường dẫn, URLs nội bộ, một phần environment hoặc secrets. Chỉ dùng khi cần, **không công khai log chưa lọc thông tin nhạy cảm**.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `-DskipTests` không bỏ integration tests | Failsafe 3.6.x đã đổi property binding | Dùng `-DskipITs=true` hoặc custom config có chủ đích |
| Cùng cờ nhưng CI cũ và mới khác nhau | Phiên bản Surefire/Failsafe hoặc parent/profile khác | So sánh effective POM và goal docs của từng phiên bản |
| `-DskipTests` vẫn lỗi biên dịch test | Test compilation không bị bỏ | Sửa test source hoặc hiểu rõ `maven.test.skip` |
| `-DskipITs` không thấy tác dụng | Failsafe không được bind hoặc Maven chưa tới phase IT | Kiểm tra lifecycle goals, chạy `verify` |
| `BUILD SUCCESS` dù IT báo fail | Chỉ chạy `integration-test`, thiếu `failsafe:verify`, hoặc failure-ignore | Bind cả hai goals và chạy `verify` |
| Không có Surefire test report | Tên test không match, plugin skip, wrong provider hoặc không có tests | Xem patterns, effective config, log discovery |
| Report cũ xuất hiện dù đang skip | Không clean `target` trước lần test | Dùng `mvn clean ...` và kiểm tra timestamps |
| Test failure được bỏ qua nhưng log vẫn báo failure | `maven.test.failure.ignore` | Không dùng nó để lờ lỗi chất lượng |
| Maven không tìm được plugin | Repo/mirror/plugin repository lỗi | Giải quyết plugin resolution trước khi kiểm tra flags |
| Test JUnit không được phát hiện | JUnit engine/provider/version và test naming không phù hợp | Kiểm tra JUnit dependency, Surefire provider và patterns |
| Build profile fast vẫn skip khi đã bỏ CLI flag | Property skip ở parent/profile còn bật | Xem active profiles/effective POM và cấu hình giá trị mặc định |
| Failsafe 3.6.x vẫn skip khi dùng `skipTests` | POM ánh xạ `skipTests` sang `skipITs` hoặc khai `skipTests` trực tiếp | Tìm custom configuration trong effective POM |

## 14. Câu hỏi tự kiểm tra

**Câu 1:** Failsafe 3.6.1, Surefire 3.6.1, không custom mapping. Lệnh `mvn clean verify -DskipTests=true` có bỏ integration tests không?

**Đáp án:** Không theo binding mặc định. Surefire skip unit tests, Failsafe vẫn chạy integration tests khi được bind.

**Câu 2:** Bạn muốn chạy unit tests nhưng bỏ integration tests. Cờ nào phù hợp?

**Đáp án:** `-DskipITs=true`. Phải có unit tests được Surefire phát hiện và goal Failsafe được bind thì so sánh mới có ý nghĩa.

**Câu 3:** Dùng `-DskipTests=true -DskipITs=true`, test Java source còn được compile không?

**Đáp án:** Thông thường có. Hai cờ bỏ test execution, không tự bỏ test compilation.

**Câu 4:** Dùng `-Dmaven.test.skip=true`, bạn còn chắc chắn phát hiện lỗi cú pháp test Java không?

**Đáp án:** Không. Compiler Plugin có thể bỏ qua test compilation nên lỗi test source không được phát hiện trong build ấy.

**Câu 5:** `mvn -version` có trả lời Failsafe đang là 3.5.6 hay 3.6.1 không?

**Đáp án:** Không. Cần xem effective POM hoặc build log/goal description.

**Câu 6:** Chạy `mvn integration-test` và thấy build không fail có đủ chứng minh IT pass không?

**Đáp án:** Không. Failsafe thiết kế để đánh giá cuối ở `verify`, sau teardown. Hãy chạy `mvn verify`.

**Câu 7:** Failsafe 3.6.1 nhưng `-DskipTests=true` vẫn skip IT. Có thể do gì?

**Đáp án:** Parent/profile/child POM tự khai `<skipITs>${skipTests}</skipITs>` hoặc `<skipTests>`, khiến user property tác động qua expression.

**Câu 8:** Có nên dùng `maven.test.failure.ignore=true` để rút ngắn build?

**Đáp án:** Không. Nó không bỏ test execution, mà thay cách xử lý failure; có nguy cơ tạo build xanh giả.

## 15. Checklist trước khi dùng tùy chọn bỏ qua trong CI

- [ ] Đã kiểm tra Surefire version **thực sự chạy**.
- [ ] Đã kiểm tra Failsafe version **độc lập** với Surefire.
- [ ] Đã xem effective POM, plugin management, executions và active profiles.
- [ ] Đã biết dự án dùng Failsafe 3.5.x hay 3.6.x; không mượn nguyên hướng dẫn sai version.
- [ ] Hiểu `-DskipTests` của Surefire và việc Failsafe 3.6.0+ không tự nhận cờ đó.
- [ ] Hiểu `-DskipITs` dùng bỏ integration tests.
- [ ] Hiểu `-Dmaven.test.skip` có tác động tới test compilation.
- [ ] Không dùng `skipExec` hoặc `maven.test.skip.exec` deprecated cho cấu hình mới.
- [ ] Failsafe có cả `integration-test` và `verify` goals nếu cần IT quality gate.
- [ ] Đã chạy baseline `mvn clean verify` không skip và kiểm tra có tests thực sự chạy.
- [ ] Đã kiểm tra Surefire/Failsafe reports mới, counts, failures và skips.
- [ ] Không lấy `BUILD SUCCESS` đơn lẻ làm bằng chứng kiểm thử đủ.
- [ ] Không che lỗi bằng `maven.test.failure.ignore`.
- [ ] CI jobs có cờ skip đều có lý do và đường full verification thay thế.
- [ ] Sau nâng plugin, đã chạy lại bảng thực nghiệm các cờ trước khi phát hành.

**Tóm tắt:** Không có “một cờ skip cho mọi phiên bản Maven test plugins”. Điểm thay đổi quan trọng là **Failsafe 3.6.0+ không còn tự nhận `skipTests` user property**, dù Surefire vẫn nhận nó. Nếu muốn skip IT hãy dùng `-DskipITs=true`; nếu muốn skip cả unit và IT execution hãy dùng **cả hai flags**; nếu muốn bỏ cả biên dịch test thì mới cân nhắc `-Dmaven.test.skip=true`. Luôn xác nhận **version + effective POM + execution log + report counts** trước khi chốt build behavior.

## Tài liệu tham khảo chính thức

- [Apache Maven Surefire Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html)
- [Apache Maven Failsafe Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/skipping-tests.html)
- [Surefire — surefire:test Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Failsafe — failsafe:integration-test Parameters](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Failsafe — failsafe:verify Parameters](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
- [Surefire/Failsafe — What's New in 3.6.x](https://maven.apache.org/surefire/maven-surefire-plugin/whats-new-3-6-x.html)
- [Archived Failsafe 3.5.6 — Skipping Tests](https://maven.apache.org/surefire-archives/surefire-3.5.6/maven-failsafe-plugin/examples/skipping-tests.html)
- [Surefire — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)

*Ví dụ pin Surefire/Failsafe 3.6.1 nhằm minh họa khác biệt từ 3.6.0. Nếu build của bạn dùng các phiên bản khác, hãy tra đúng goal documentation và test trên POM hiệu lực trước khi áp dụng cờ.*
