# Chọn kiểm thử bằng -Dit.test và dùng skipITs đúng phạm vi trong Maven

## 1. Mục tiêu: chỉ chạy IT cần thiết, hoặc bỏ IT mà không bỏ unit test

Trong dự án Java dùng Maven, một bộ kiểm thử thường được chia làm hai nhóm:

- **Unit test (UT):** kiểm tra một hàm/class hoặc hành vi nhỏ, thường không cần database, HTTP service hay filesystem bên ngoài.
- **Integration test (IT):** kiểm tra các thành phần phối hợp: service ↔ repository, client ↔ HTTP endpoint, code ↔ filesystem, ứng dụng ↔ database/container và những ranh giới I/O thực tế.

Trong Maven, **Maven Surefire Plugin** thường chạy UT ở phase `test`; **Maven Failsafe Plugin** chạy IT ở phase `integration-test` và kiểm tra kết quả ở phase `verify`. Nhiều người muốn chạy lại một IT đang lỗi thay vì toàn bộ suite:

```bash
mvn clean verify "-Dit.test=FileStoreIT"
```

Một nhu cầu khác là kiểm tra unit tests, compilation và packaging mà tạm thời chưa chạy IT:

```bash
mvn clean verify -DskipITs=true
```

Hai lệnh này khác bản chất:
- `-Dit.test=...` **chọn IT nào Failsafe sẽ chạy**.
- `-DskipITs` **đề nghị Failsafe bỏ chạy IT**, không phải chỉ chọn một IT.
- `-DskipITs` **không tự tắt Surefire unit tests** và **không mặc nhiên bỏ mọi plugin** gắn vào lifecycle.

Bài này sử dụng **Maven 3.9.x**, **Maven Failsafe Plugin 3.5.2**, **Maven Surefire Plugin 3.5.2**, **Maven Compiler Plugin 3.13.0**, **Java 17** và **JUnit Jupiter 5.11.4**. Phiên bản được ghim vì semantics của `skipTests` trong các bản Failsafe mới **đã thay đổi**; không nên phát biểu một quy tắc áp dụng mãi mãi.

Bạn sẽ học:
1. Cách dùng Failsafe trong default lifecycle và vì sao chạy `mvn verify`.
2. Phân biệt `-Dtest` của Surefire với `-Dit.test` của Failsafe.
3. Chọn một lớp IT, nhiều lớp, wildcard hoặc exclude pattern.
4. Đọc giới hạn chọn method của từng test provider/version.
5. Dùng `-DskipITs` để bỏ **chạy IT** mà giữ **biên dịch test và unit tests**.
6. Phân biệt `skipITs`, `skipTests` và `maven.test.skip`.
7. Viết POM và test files Java 17 hoàn chỉnh, thực hành từng lệnh và xem reports.
8. Chẩn đoán lỗi selector không khớp, CI và multi-module builds.

## 2. Cơ chế: Surefire và Failsafe khác nhau ở đâu?

### 2.1. So sánh nhanh hai Maven plugins

| Nội dung | Surefire | Failsafe |
| --- | --- | --- |
| Mục đích thường gặp | Unit tests | Integration tests |
| Goal chạy test | `surefire:test` | `failsafe:integration-test` |
| Goal xác nhận kết quả IT | Không có goal IT verify tương đương | `failsafe:verify` |
| Lifecycle phase | `test` | `integration-test` và `verify` |
| Default class patterns | `Test*.java`, `*Test.java`, `*Tests.java`, `*TestCase.java` | `IT*.java`, `*IT.java`, `*ITCase.java` |
| Chọn test từ CLI | `-Dtest=CalculatorTest` | `-Dit.test=FileStoreIT` |
| Thư mục báo cáo | `target/surefire-reports` | `target/failsafe-reports` |

Pattern mặc định chỉ có hiệu lực nếu POM chưa override `includes`/`excludes`; Failsafe vẫn có thể nhận những class tên khác qua cấu hình. Test files của cả hai nhóm thường nằm ở `src/test/java` và đều được compiler:testCompile biên dịch vào `target/test-classes`. **Khác biệt chính là plugin phát hiện/chạy chúng trong phase nào**, không phải hai loại bytecode Java khác nhau.

### 2.2. Failsafe không tự chạy nếu chỉ khai báo version

Trong `packaging=jar`, goal Surefire thường được Maven gắn vào phase `test` theo lifecycle mapping mặc định. Nhưng Failsafe IT cần được **cấu hình execution** rõ ràng trong `<build><plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **POM fragment**, không phải file hoàn chỉnh. Cả hai goal có default lifecycle phase tương ứng nên không bắt buộc gắn `<phase>` riêng trong mẫu. Nếu không có execution đúng, `mvn verify` có thể không chạy Failsafe, dù POM có dependency JUnit và file tên `SomethingIT.java`.

### 2.3. Vì sao phải chạy tới verify?

Một vòng đời build thông dụng có các bước:

```text
compile                 -> biên dịch mã ứng dụng
test-compile            -> biên dịch các test classes
test                    -> Surefire chạy UT
package                 -> tạo JAR/WAR
pre-integration-test     -> có thể start server/database/container
integration-test         -> Failsafe chạy IT
post-integration-test    -> có thể stop/cleanup server, database
verify                   -> Failsafe đọc summary, xác nhận IT PASS/FAIL
```

Đây là sơ đồ rút gọn: Maven có thêm các phase khác và plugin executions tùy POM.

Failsafe thiết kế để khi test assertion fail, phần thực thi `integration-test` có thể **ghi lại kết quả** và cho lifecycle đi tiếp tới `post-integration-test` trước khi `failsafe:verify` quyết định build fail. Nếu chạy:

```bash
mvn integration-test
```

Maven dừng trước cleanup và goal verify. **Không dùng BUILD SUCCESS tại mốc integration-test để chứng minh IT pass.** Chuẩn để chạy full pipeline là:

```bash
mvn clean verify
```

Khi có startup/teardown hạ tầng, đây còn là cách tránh bỏ qua bước tắt service do bạn dừng lifecycle quá sớm.

### 2.4. Compile test không đồng nghĩa chạy test

`mvn test-compile` có thể tạo:
- `target/test-classes/com/example/itlab/FileStoreTest.class`;
- `target/test-classes/com/example/itlab/FileStoreIT.class`;
- `target/test-classes/com/example/itlab/UnicodeIT.class`.

Những file bytecode này chỉ chứng minh Java test sources **đã biên dịch**, không chứng minh Surefire/Failsafe đã chạy assertion. Ngược lại, `-DskipITs` có thể khiến IT class được compile nhưng không có IT test method nào chạy trong lần build đó. Phải xem reports và số test executed.

## 3. -Dit.test: bộ lọc cho integration tests

### 3.1. Cú pháp một class

Failsafe có parameter `test` với User Property `it.test`. Để chạy một IT class:

```bash
mvn clean verify "-Dit.test=FileStoreIT"
```

Value có thể chỉ là tên class không đuôi `.java`. Trong trường hợp test nằm trong package hoặc source tree phức tạp, Failsafe cũng hỗ trợ tên/path patterns theo cú pháp tài liệu plugin. Đặt dấu nháy quanh toàn đối số giúp tránh vấn đề ký tự đặc biệt ở PowerShell và một số shells khác.

**Lưu ý:** việc chọn Failsafe test class **không bỏ Surefire UT**. Khi Maven chạy đến phase `verify`, phase `test` đã diễn ra trước đó và Surefire vẫn có thể chạy UT theo cấu hình mặc định.

### 3.2. Một, nhiều hoặc pattern

| Yêu cầu | Lệnh thực hành |
| --- | --- |
| Chỉ FileStoreIT | `mvn clean verify "-Dit.test=FileStoreIT"` |
| Chỉ UnicodeIT | `mvn clean verify "-Dit.test=UnicodeIT"` |
| Hai lớp IT | `mvn clean verify "-Dit.test=FileStoreIT,UnicodeIT"` |
| Mọi lớp kết thúc IT | `mvn clean verify "-Dit.test=*IT"` |
| Lớp có tiền tố File | `mvn clean verify "-Dit.test=File*IT"` |
| Chọn tất cả IT trừ UnicodeIT | `mvn clean verify "-Dit.test=*IT,!UnicodeIT"` |

Theo tài liệu Failsafe, `it.test` hỗ trợ comma-separated class/pattern values, wildcard và exclusion với prefix `!`. Một selector `-Dit.test` thường có ưu tiên so với danh sách `includes/excludes` thông thường của Failsafe; các cơ chế bổ sung như TestNG suites, JUnit groups/tags và provider khác có thể có quy tắc riêng. Với filter phức tạp, cần đối chiếu docs đúng phiên bản và **đọc report** chứ không chỉ nhìn cú pháp.

### 3.3. Chọn method bằng # cần kiểm tra provider

Failsafe có tài liệu về syntax:

```bash
mvn clean verify "-Dit.test=FileStoreIT#writesAndReads"
```

Tuy nhiên, lịch sử hỗ trợ method filtering khác nhau giữa JUnit 4, TestNG và JUnit 5/JUnit Platform. Một số ví dụ trong tài liệu ghi chú riêng **JUnit 4 và TestNG**; với JUnit Jupiter còn cần kiểm tra behavior cho parameterized/dynamic tests và tên method hiển thị.

Vì vậy **phần demo runnable trong bài chỉ khẳng định chắc kết quả khi lọc theo class name**. Bạn có thể thử `#method` trên project của mình, nhưng hãy xác nhận qua Failsafe report xem đúng method đã chạy và kiểm tra provider/version. Đừng hứa mọi cú pháp phương thức của JUnit 4 hoạt động hoàn toàn giống nhau trên JUnit 5.

### 3.4. Không có test khớp: đừng im lặng PASS

Nếu gõ sai:

```bash
mvn clean verify "-Dit.test=FileStroeIT"
```

thay vì `FileStoreIT`, Failsafe 3.5.2 có parameter `failIfNoSpecifiedTests`, mặc định `true`, giúp báo lỗi khi không test nào khớp selector. User Property tương ứng là `failsafe.failIfNoSpecifiedTests`.

Đừng vô hiệu hóa cờ này trên CI chỉ để tránh lỗi selector. Một job xanh nhưng **không có IT nào chạy** thường nguy hiểm hơn một job báo lỗi rõ. `failIfNoTests` (chạy IT không chỉ định selector) và `failIfNoSpecifiedTests` (đã yêu cầu một selector cụ thể) là hai trường hợp khác nhau.

Khi không tìm thấy IT:
1. Kiểm tra chính tả class/package/pattern và chữ hoa/thường.
2. Kiểm tra Failsafe execution đã bind vào lifecycle chưa.
3. Kiểm tra file trong `src/test/java` và class trong `target/test-classes`.
4. Kiểm tra module nào chứa class trong reactor nhiều module.
5. Kiểm tra JUnit engine/test provider và `@Test`.
6. Xem plugin debug logs/`target/failsafe-reports` nếu cần.
7. Chạy một lệnh base `mvn clean verify` không filter để xem convention ban đầu.

### 3.5. Surefire dùng -Dtest, không dùng -Dit.test

Hai selector khác nhau:

```bash
mvn test "-Dtest=FileStoreTest"
mvn verify "-Dit.test=FileStoreIT"
```

- `-Dtest` dành cho **Surefire**.
- `-Dit.test` dành cho **Failsafe**.

Lệnh thứ hai không có nghĩa chỉ chạy FileStoreIT trên toàn build: unit test Surefire vẫn có thể chạy trước. Nếu muốn chọn chính xác một UT và một IT trong cùng vòng đời:

```bash
mvn clean verify "-Dtest=FileStoreTest" "-Dit.test=FileStoreIT"
```

Với project multi-module, một selector được truyền từ root có thể ảnh hưởng các module có plugin goal tương ứng. Nên giới hạn plugin execution vào module đúng hoặc dùng lệnh Maven chọn module có chủ đích.

## 4. skipITs chỉ bỏ Failsafe IT execution

### 4.1. Lệnh chính

```bash
mvn clean verify -DskipITs=true
```

Viết tắt cũng hợp lệ:

```bash
mvn clean verify -DskipITs
```

Trong Failsafe 3.5.2, `skipITs` là User Property của parameter `<skipITs>`. Khi true, Failsafe bỏ **chạy integration tests** và bỏ bước kiểm tra kết quả IT tương ứng theo cơ chế của plugin. Đây là lựa chọn đúng khi bạn muốn một build local nhanh hơn nhưng vẫn giữ Surefire unit tests.

Những gì thường **vẫn thực hiện**:
- compile main Java;
- compile test Java, gồm cả file `*IT.java`;
- Surefire unit tests ở phase `test`;
- đóng gói artifact và những phase/plugins khác không bị điều kiện skip tương ứng.

`skipITs` không đồng nghĩa với “skip toàn bộ Maven verify”. Build vẫn có thể fail vì unit test lỗi, compiler lỗi, JAR packaging lỗi hoặc plugin khác fail.

### 4.2. skipITs không tắt plugin start container hoặc database

Một project thật có thể cấu hình:
- `pre-integration-test`: plugin start database, Jetty hoặc Docker;
- `integration-test`: Failsafe chạy IT;
- `post-integration-test`: plugin stop service;
- `verify`: Failsafe kiểm tra result.

Khi chạy `mvn verify -DskipITs`, **Failsafe biết bỏ IT**, nhưng plugin start/stop được gắn độc lập **không mặc nhiên nhận cờ này**. Nếu vẫn start container, đó không phải Failsafe “không nghe skipITs”.

Giải pháp:
- dùng profile chứa cả các plugin phục vụ integration tests;
- hoặc truyền điều kiện skip phù hợp cho **từng plugin** start/stop và Failsafe;
- bảo đảm cleanup vẫn đúng trong trường hợp test fail hoặc build bị dừng;
- phân biệt job chỉ cần UT với job thực sự cần IT và hạ tầng.

Tự động “skip IT” trong Failsafe không có nghĩa Maven bỏ toàn bộ phase `pre-integration-test` hay `post-integration-test`.

### 4.3. skipITs true có thể bị POM cố định

Một POM fragment như:

```xml
<configuration>
    <skipITs>true</skipITs>
</configuration>
```

đặt trong Failsafe plugin khiến IT bị bỏ mặc định trong module. Đừng đưa cấu hình này vào parent/release build mà không chủ đích; `-Dit.test=FileStoreIT` **không tự override** một cấu hình skip true.

Nếu muốn điều khiển bằng một property có tên riêng, có thể dùng:

```xml
<properties>
    <skip.integration.tests>false</skip.integration.tests>
</properties>
```

và Failsafe config:

```xml
<configuration>
    <skipITs>${skip.integration.tests}</skipITs>
</configuration>
```

Khi ấy CLI thích hợp để đổi property của POM là `-Dskip.integration.tests=true`. Đây là **ví dụ cấu hình thay thế**. POM runnable mục 6 không cần fragment này vì mặc định `skipITs=false` và có thể truyền `-DskipITs=true` trực tiếp.

## 5. Đừng nhầm skipITs, skipTests và maven.test.skip

### 5.1. Semantics theo version Failsafe 3.5.2

Tài liệu chính thức Failsafe **3.5.2** ghi:
- `-DskipITs`: chỉ skip Failsafe integration tests; **test classes vẫn được compile**.
- `-DskipTests`: Surefire hiểu cờ này, và Failsafe 3.5.2 cũng nhận property này; do đó thường skip **cả UT và IT execution**.
- `-Dmaven.test.skip=true`: Compiler Plugin, Surefire và Failsafe đều nhận; **bỏ cả test compilation** và test execution.
- `-Dit.test=SomeIT`: lọc một hoặc nhiều IT classes, **không phải cờ skip**.
- `-Dtest=SomeTest`: lọc Surefire unit tests, **không phải cờ skip IT**.

**Cảnh báo theo phiên bản:** từ **Failsafe 3.6.0**, tài liệu mới ghi Failsafe không còn bind parameter `skipTests` với user property `skipTests` như trước. Vì thế behavior `-DskipTests` có thể khác trong build dùng Failsafe mới hơn; dùng `-DskipITs` sẽ rõ ý định bỏ IT hơn.

### 5.2. Bảng quyết định trên project chuẩn có Surefire/Failsafe 3.5.2

| Lệnh | Unit tests | Integration tests | Compile test sources |
| --- | --- | --- | --- |
| `mvn clean verify` | Có | Có | Có |
| `mvn clean verify "-Dit.test=FileStoreIT"` | Có | Chỉ FileStoreIT | Có |
| `mvn clean verify -DskipITs` | **Có** | **Không** | **Có** |
| `mvn clean verify -DskipTests` | Không | Không (Failsafe 3.5.2) | Có |
| `mvn clean verify -Dmaven.test.skip=true` | Không | Không | **Không** |
| `mvn clean test` | Có | Chưa đến phase IT | Có |
| `mvn clean test-compile` | Chưa chạy | Chưa chạy | Có |

Bảng mô tả các plugin chuẩn khi không có executions khác tự ý chạy test. Nếu project có custom integration plugins hoặc build profiles, chỉ đọc bảng là chưa đủ; cần đọc effective POM và plugin logs. **Đừng dùng `-Dmaven.test.skip` khi bạn vẫn muốn compiler phát hiện test sources bị lỗi.**

### 5.3. Nếu vừa chọn IT vừa skipITs

```bash
mvn clean verify "-Dit.test=FileStoreIT" -DskipITs=true
```

Lệnh vừa yêu cầu selector vừa yêu cầu bỏ thực thi. `skipITs=true` làm Failsafe không chạy IT; không có “quy tắc selector tự bật lại test đã bị skip”. Muốn chạy FileStoreIT, bỏ cờ skip và xác nhận không có parent/profile nào hard-code skip true.

### 5.4. CI phải phân biệt Skipped với Passed

Một job dùng `mvn clean verify -DskipITs` có thể thành công dù **0 IT được thực thi**. Không mô tả job này là “all unit and integration tests passed”. Nên có hai giai đoạn rõ:
- Job phản hồi nhanh: compile + UT + các quality checks phù hợp, chủ động skipITs.
- Job integration/release: chạy `mvn clean verify` với IT thật, collect Failsafe report và yêu cầu PASS.

Nếu IT chậm, có thể chia suite theo tags/modules hoặc chọn test group theo policy, nhưng phải giữ một điểm kiểm soát cuối bao phủ integration behavior quan trọng.

## 6. Ví dụ thực hành hoàn chỉnh: Java 17, JUnit 5, 1 UT và 3 IT

Ta xây dựng một class ghi/đọc file UTF-8. UT kiểm tra validation mà không tạo file. IT thực sự ghi/đọc trong thư mục tạm của JUnit. Đây là một integration boundary với filesystem, đủ để quan sát Maven mà không cần Docker/database hoặc internet service. Trong dự án thực tế, IT thường kiểm tra network/database và có setup/teardown riêng.

### 6.1. Bố cục dự án

```text
failsafe-select-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/itlab/
    │   └── FileStore.java
    └── test/java/com/example/itlab/
        ├── FileStoreTest.java
        ├── FileStoreIT.java
        └── UnicodeIT.java
```

- `FileStoreTest` có suffix `Test`, mặc định Surefire nhận.
- `FileStoreIT`, `UnicodeIT` có suffix `IT`, mặc định Failsafe nhận.
- Cả ba test files nằm dưới `src/test/java` và được testCompile biên dịch.
- Không tạo separate test source roots tùy chỉnh để ví dụ dễ chạy lại trên IDE/CI.

### 6.2. Tệp `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>failsafe-select-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
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
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.2</version>
                <executions>
                    <execution>
                        <id>integration-checks</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích POM:
1. `maven.compiler.release=17` yêu cầu Java compiler 17-compatible bytecode/API.
2. JUnit Jupiter được khai báo `scope=test`; không thêm JUnit runtime dependency cho sản phẩm.
3. Cả Surefire và Failsafe ghim bản `3.5.2`, đủ mới để chạy JUnit Jupiter, và dễ quan sát skip flags.
4. Failsafe gắn hai goals vào lifecycle, đảm bảo `mvn verify` chạy IT và kiểm tra summary.
5. Không đặt `<skipITs>true</skipITs>` hoặc selector cứng; mọi thí nghiệm sẽ điều khiển qua CLI.

### 6.3. File `src/main/java/com/example/itlab/FileStore.java`

```java
package com.example.itlab;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class FileStore {
    private final Path directory;

    public FileStore(Path directory) {
        this.directory = Objects.requireNonNull(directory);
    }

    private Path pathFor(String key) {
        if (key == null || !key.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid key");
        }
        return directory.resolve(key + ".txt");
    }

    public void save(String key, String value) throws IOException {
        Path path = pathFor(key);
        Files.createDirectories(directory);
        Files.writeString(path, Objects.requireNonNull(value),
                StandardCharsets.UTF_8);
    }

    public String load(String key) throws IOException {
        return Files.readString(pathFor(key),
                StandardCharsets.UTF_8);
    }
}
```

`FileStore` kiểm tra key chỉ gồm chữ/số/underscore/dash trước khi tạo file; điều này tránh việc một key kiểu `../escape` trỏ ra ngoài thư mục lưu. `save` ghi chuỗi UTF-8 ra file thật, `load` đọc lại chuỗi UTF-8. Logic vừa đủ cho UT (validation) và IT (filesystem boundary), không cần framework khác.

### 6.4. File `src/test/java/com/example/itlab/FileStoreTest.java`

```java
package com.example.itlab;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertThrows;

final class FileStoreTest {
    @Test
    void rejectsUnsafeKeysBeforeIo() {
        FileStore store = new FileStore(Path.of("not-used"));
        assertThrows(IllegalArgumentException.class,
                () -> store.save("../escape", "data"));
    }
}
```

Đây là **1 unit test method**. `pathFor` ném `IllegalArgumentException` ngay trước thao tác file; test không cần tạo file và không phụ thuộc môi trường. Tên class kết thúc `Test` nên Surefire chọn mặc định.

### 6.5. File `src/test/java/com/example/itlab/FileStoreIT.java`

```java
package com.example.itlab;

import java.io.IOException;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.assertEquals;

final class FileStoreIT {
    @TempDir
    Path tempDir;

    @Test
    void writesAndReads() throws IOException {
        FileStore store = new FileStore(tempDir);
        store.save("greeting", "hello");
        assertEquals("hello", store.load("greeting"));
    }

    @Test
    void overwritesExistingRecord() throws IOException {
        FileStore store = new FileStore(tempDir);
        store.save("state", "old");
        store.save("state", "new");
        assertEquals("new", store.load("state"));
    }
}
```

Hai integration test methods thật sự ghi/đọc file, được JUnit `@TempDir` cấp thư mục tạm cho test. `FileStoreIT` có suffix `IT`, nên Failsafe chọn mặc định. Kết quả khi chỉ chạy `-Dit.test=FileStoreIT` là **2 IT**, không phải 1 (vì một class có hai methods).

### 6.6. File `src/test/java/com/example/itlab/UnicodeIT.java`

```java
package com.example.itlab;

import java.io.IOException;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.assertEquals;

final class UnicodeIT {
    @TempDir
    Path tempDir;

    @Test
    void preservesUtf8Text() throws IOException {
        FileStore store = new FileStore(tempDir);
        store.save("message", "Xin chào Việt Nam");
        assertEquals("Xin chào Việt Nam", store.load("message"));
    }
}
```

Đây là **1 integration test method** độc lập, kiểm tra UTF-8 được giữ qua file I/O. Vì tên class `UnicodeIT` cũng có suffix `IT`, full Failsafe suite sẽ gồm 2 methods trong FileStoreIT và 1 method trong UnicodeIT, tổng 3.

### 6.7. Lệnh baseline

Mở terminal trong thư mục `failsafe-select-lab` và kiểm tra:

```bash
mvn -version
mvn clean verify
```

Yêu cầu Maven 3.9.x và JDK 17+ (hoặc compiler toolchain tương ứng). Lần đầu build Maven có thể tải plugins/JUnit từ repository. Sau khi hoàn tất, kết quả **mong đợi**:

```text
Surefire: FileStoreTest -> 1 UT passed
Failsafe: FileStoreIT  -> 2 IT passed
Failsafe: UnicodeIT    -> 1 IT passed
TOTAL: 1 UT and 3 IT, zero failures
```

Đây là **tóm tắt diễn giải**, không phải toàn bộ Maven stdout chính xác. Các file report thường có:

```text
target/surefire-reports/
target/failsafe-reports/
target/failsafe-reports/failsafe-summary.xml
```

Kiểm tra báo cáo sau lần chạy, không dựa vào output file cũ. `clean` giúp đảm bảo không dùng report của lần trước.

### 6.8. Chỉ chạy một IT class

```bash
mvn clean verify "-Dit.test=FileStoreIT"
```

Kỳ vọng:
- Surefire chạy **1 UT** trong `FileStoreTest` như bình thường.
- Failsafe chạy **2 methods** trong `FileStoreIT`.
- `UnicodeIT` không chạy.
- Goal `failsafe:verify` vẫn xác nhận summary của tập IT vừa được chọn.

Chỉ định một class qua `it.test` không tương đương chạy “chính xác một test method”; nếu class có nhiều `@Test` thì thường tất cả những methods phù hợp trong class đó được chạy.

### 6.9. Chọn hai classes, wildcard, hoặc exclude

```bash
mvn clean verify "-Dit.test=FileStoreIT,UnicodeIT"
mvn clean verify "-Dit.test=*IT"
mvn clean verify "-Dit.test=*IT,!UnicodeIT"
```

- Hai lệnh đầu chọn cả FileStoreIT và UnicodeIT: **3 IT**.
- Lệnh cuối chọn pattern `*IT` rồi loại UnicodeIT: thường còn **2 IT**.
- Surefire vẫn chạy FileStoreTest trừ khi có cấu hình/selector UT riêng.

Dấu phẩy và `!` thuộc syntax Failsafe test selection, không phải cú pháp Maven lifecycle. Quote nguyên đối số để shell không xử lý trước.

### 6.10. Chỉ bỏ chạy integration tests

```bash
mvn clean verify -DskipITs=true
```

Kỳ vọng:
- **1 UT** của Surefire vẫn chạy.
- **0 IT methods executed**.
- Test source files vẫn được biên dịch vào `target/test-classes`.
- Các bước package/verify khác vẫn chạy nếu không bị điều kiện khác bỏ qua.

Khi đọc report phải ghi rõ **IT skipped/not executed**, không ghi “3 IT passed” vì chúng chưa chạy. Không bắt buộc có failsafe-summary mới nếu Failsafe skip; cách nhìn tốt là log plugin và sự có mặt/số lượng IT results sau clean build.

### 6.11. Hai lệnh skip rộng hơn

```bash
mvn clean verify -DskipTests=true
mvn clean verify -Dmaven.test.skip=true
```

Trong cấu hình Failsafe/Surefire **3.5.2**:
- `skipTests` thường skip **cả UT và IT execution**, nhưng Java test sources vẫn được compile.
- `maven.test.skip=true` skip **test compilation lẫn test execution** nhờ Compiler/Failsafe/Surefire.

Nội dung này có điều kiện version, đặc biệt khác so với Failsafe 3.6.x. Luôn ghim plugin versions và thử với effective POM đang dùng.

### 6.12. Thí nghiệm tạo lỗi để hiểu verify

Chỉ để thực hành, tạm sửa expected value trong `UnicodeIT` thành `"Sai"`, rồi chạy:

```bash
mvn clean verify "-Dit.test=UnicodeIT"
```

IT sẽ fail assertion và Failsafe ghi kết quả; sau lifecycle cleanup (nếu có) `failsafe:verify` khiến build thất bại. Không dùng kết quả từ `mvn integration-test` dừng sớm để kết luận toàn bộ pipeline.

**Khôi phục assertion gốc** sau khi quan sát; không commit thí nghiệm gây lỗi vào nhánh dùng cho release.

## 7. Multi-module: chỉ định đúng module có test

Trong reactor nhiều module:

```text
root/
├── core/
├── app/
└── integration-tests/
    └── src/test/java/.../FileStoreIT.java
```

Nếu Failsafe executions được kế thừa cho tất cả modules, lệnh global:

```bash
mvn verify "-Dit.test=FileStoreIT"
```

có thể gây lỗi **no matching tests** ở module không có FileStoreIT. Nguồn gốc không nhất thiết là class thiếu trong cả repository; có thể selector đang bị áp vào module không phù hợp.

Thử chọn module:

```bash
mvn -pl integration-tests -am verify "-Dit.test=FileStoreIT"
```

Lưu ý `-am` còn build các module phụ thuộc, nên nếu Failsafe chạy ở các module ấy và nhận global selector, vẫn có thể fail. **Cách ổn định nhất là đặt Failsafe execution vào đúng module chứa IT**, hoặc thiết kế chuyên biệt cho integration module. Với những module cần cùng Failsafe nhưng không cùng test names, xét cấu hình per-module cẩn thận.

Có thể điều chỉnh `failsafe.failIfNoSpecifiedTests` trong mô hình đã có coverage validation độc lập, nhưng **không tự tắt mặc định** chỉ để build xanh khi selector sai. Test-count reporting phải xác nhận lớp thực sự được chạy.

### 7.1. Class selection không phải JUnit tag selection

JUnit Jupiter có `@Tag("slow")`, `@Tag("db")`... Đó là metadata của JUnit Platform, không phải tên class pattern. `-Dit.test=slow` **không có nghĩa** chọn mọi method có `@Tag("slow")`. Muốn lọc tags, dùng cấu hình provider groups/excludedGroups phù hợp và đọc docs version.

Tương tự, TestNG suiteXmlFiles, includes/excludes files và regex filters có quy tắc ưu tiên riêng. Một ứng dụng dùng nhiều framework nên không suy từ một ví dụ class pattern rằng mọi filter khác hợp nhất theo cùng thuật toán.

## 8. Troubleshooting và kiểm chứng

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `-Dit.test` không chạy gì | Failsafe không được gắn goals, gọi `mvn test` chưa đến IT | Xem executions, chạy `mvn verify` |
| `-Dtest` chỉ lọc UT | Đây là property của Surefire | Dùng `-Dit.test` để lọc Failsafe |
| `-Dit.test=FileStoreIT` vẫn chạy UT | Surefire ở phase test trước Failsafe | Đây là hành vi đúng |
| Selector sai báo no tests | Tên class/pattern/module sai | Kiểm tra typo, target/test-classes |
| `-Dit.test` đi cùng `-DskipITs` không chạy IT | Skip execution đang bật | Tắt skip nếu muốn chạy |
| `-DskipITs` mà UT vẫn chạy | Skip chỉ áp dụng Failsafe IT | Đây là phạm vi mong muốn |
| `-DskipTests` bỏ cả UT/IT trên 3.5.2 | Cả hai plugins nhận cờ | Dùng `skipITs` nếu chỉ skip IT |
| Failsafe version mới khác behavior skipTests | Plugin 3.6.0 thay đổi binding | Kiểm tra version và docs |
| `maven.test.skip` không tạo test class | Compiler cũng nhận cờ này | Chỉ dùng khi chủ động bỏ test compilation |
| `mvn integration-test` thành công dù IT fail | Chưa có failsafe:verify | Dùng `mvn verify` |
| Failsafe không tìm thấy tests | Class naming, source roots, JUnit engine | Kiểm tra POM, naming convention, logs |
| Method selection khác kỳ vọng | Provider/version/parameterized test | Xem Failsafe report và provider docs |
| Có report cũ | Build không clean | Dùng `mvn clean verify` |
| skipITs nhưng server vẫn start | Setup plugin riêng ở pre-integration-test | Đồng bộ profile/skip cho plugin đó |
| CI xanh dù không có IT | Tests skipped mà không có coverage gate | Kiểm tra số test thực thi |
| Multi-module selector lỗi module khác | Failsafe chạy rộng | Giới hạn execution đúng module |
| UT/IT class có ở target nhưng chưa chạy | Chỉ mới testCompile | Xem surefire/failsafe-reports |

### 8.1. Quy trình chẩn đoán có thể lặp lại

1. Chạy `mvn -version`, xác nhận Maven/JDK.
2. Đọc Failsafe/Surefire plugin versions và executions trong `pom.xml`.
3. Xem `mvn help:effective-pom` để kiểm tra parent, profile, skip settings.
4. Xem class names và các file trong `target/test-classes` sau test compilation.
5. Chạy `mvn clean test` để xác nhận UT.
6. Chạy `mvn clean verify` làm baseline UT + IT.
7. Chạy `mvn clean verify "-Dit.test=FileStoreIT"` và xem số IT thực chạy.
8. Chạy `mvn clean verify -DskipITs` và chứng minh UT còn chạy.
9. Khi có hạ tầng ngoài, kiểm tra executions ở pre/post-integration-test.
10. Thu reports trong CI, cảnh báo nếu IT suite không chạy khi job phải chạy IT.

Metadata command hỗ trợ:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-failsafe-plugin:3.5.2" -Dgoal=integration-test -Ddetail=true
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-failsafe-plugin:3.5.2" -Dgoal=verify -Ddetail=true
```

`help:describe` nói Failsafe goal có parameters nào; `help:effective-pom` nói project đang cấu hình gì. **Chỉ Failsafe report của lần chạy thật** cho bạn bằng chứng số tests chạy và status.

## 9. Bài tập tự đánh giá

**Bài 1.** Project có FileStoreTest (1 UT), FileStoreIT (2 IT), UnicodeIT (1 IT). `mvn verify "-Dit.test=UnicodeIT"` chạy gì? **1 UT** ở Surefire và **1 IT** ở Failsafe.

**Bài 2.** Chọn hai IT classes bằng một property? `mvn clean verify "-Dit.test=FileStoreIT,UnicodeIT"`.

**Bài 3.** `mvn clean verify "-Dit.test=FileStroeIT"` gõ sai. Nên mặc định fail hay success? **Fail** với `failsafe.failIfNoSpecifiedTests=true`, giúp không báo xanh giả.

**Bài 4.** Muốn giữ UT nhưng bỏ Failsafe IT: `-DskipITs=true`, không dùng `-DskipTests` ở Failsafe 3.5.2.

**Bài 5.** Bỏ test compilation khác bỏ IT execution thế nào? `maven.test.skip=true` bỏ cả compile tests; `skipITs` chỉ bỏ phần Failsafe IT.

**Bài 6.** Tại sao `mvn integration-test` chưa bảo đảm IT pass? Vì chưa tới `post-integration-test` và `failsafe:verify`.

**Bài 7.** Sau `mvn clean verify "-Dit.test=FileStoreIT"`, expected IT count là bao nhiêu? **2**, vì class có hai `@Test` methods.

**Bài 8.** Nếu plugin start Docker container ở pre-integration-test vẫn chạy khi `skipITs=true`, có sai không? **Không**: skipITs không điều khiển mọi plugin khác.

**Bài 9.** `-Dit.test=FileStoreIT#writesAndReads` luôn chạy đúng một JUnit 5 method trong mọi plugin version? **Không bảo đảm**, phải kiểm tra provider/version và report.

**Bài 10.** CI bỏ IT và hiện thông báo “all integration tests passed”. Sai ở đâu? **Skipped không phải Passed**; phải báo rõ IT chưa được thực thi và có job bắt buộc chạy IT.

## 10. Checklist trước khi gửi PR hoặc thay pipeline

- [ ] Surefire và Failsafe versions được xác định và ghim phù hợp.
- [ ] Failsafe có **hai goals** `integration-test` và `verify`.
- [ ] Dùng `mvn verify` cho full IT thay vì dừng ở integration-test.
- [ ] Unit test theo `*Test` và IT theo `*IT` hoặc pattern được cấu hình rõ.
- [ ] Dùng `-Dit.test` khi chọn IT, không nhầm `-Dtest`.
- [ ] Đã quote selector trong shell và đối chiếu report.
- [ ] Method filtering chỉ dùng khi đã xác minh provider/version.
- [ ] Dùng `-DskipITs` để bỏ riêng Failsafe IT, không tắt UT ngoài ý muốn.
- [ ] Không dùng `maven.test.skip` khi còn cần test compilation.
- [ ] Skip cũng phải áp dụng có chủ đích cho external setup/teardown plugins nếu cần.
- [ ] Không nhầm IT class đã compile với IT method đã thực thi.
- [ ] Nếu build multi-module, giới hạn executions vào module phù hợp.
- [ ] CI phân biệt IT skipped và IT passed, bắt buộc full IT theo quality gate.
- [ ] Khi selector không tìm thấy test, không tắt fail/no-match vô điều kiện.

**Kết luận:** `-Dit.test` là **bộ lọc lựa chọn integration tests của Maven Failsafe Plugin**. `-DskipITs` là cách **bỏ chạy IT mà vẫn giữ unit tests và test compilation** trong workflow thông dụng. Với Failsafe/Surefire 3.5.2, `-DskipTests` rộng hơn và có thể bỏ cả hai nhóm test, còn `-Dmaven.test.skip=true` bỏ luôn biên dịch test. Hãy chạy tới **`verify`**, kiểm tra số tests trong reports và mô tả rõ plugin version khi đưa quy tắc này vào CI.

### Tài liệu chính thức

- [Maven Failsafe Plugin 3.5.2 — Skipping Tests](https://maven.apache.org/surefire-archives/surefire-3.5.2/maven-failsafe-plugin/examples/skipping-tests.html)
- [Maven Failsafe Plugin — Running a Single Test](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/single-test.html)
- [Maven Failsafe Plugin — Inclusions and Exclusions](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html)
- [Maven Failsafe Plugin — integration-test goal](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Maven Failsafe Plugin 3.5.2 — verify goal](https://maven.apache.org/surefire-archives/surefire-3.5.2/maven-failsafe-plugin/verify-mojo.html)
- [Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
- [Maven Surefire Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
