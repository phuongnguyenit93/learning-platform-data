# So sánh build lạnh với build đã có kho phụ thuộc cục bộ trong Maven

## 1. Mục tiêu học tập và câu hỏi cần trả lời

Một dự án Maven có thể mất rất nhiều thời gian ở lần build đầu tiên trên máy mới nhưng chạy nhanh hơn đáng kể ở các lượt tiếp theo. Một nguyên nhân quan trọng là **Maven local repository** đã lưu JAR, POM, Maven plugins và những dependencies bắc cầu vừa được tải từ remote repositories. Tuy nhiên, sự khác biệt về thời gian **không hoàn toàn** do riêng kho Maven: filesystem cache, JVM startup/JIT, DNS/TLS, repository mirror, network congestion, antivirus và test workloads đều có thể ảnh hưởng.

Bài học này hướng dẫn cách so sánh có kiểm soát:

- **Cold dependency-cache build**: chạy cùng Maven goals với một **local repository mới, trống**.
- **Warm dependency-cache build**: chạy lại cùng Maven goals trên **chính local repository đã được lượt cold điền đầy**.
- **Cả hai lượt đều dùng `clean verify`** để cùng phải compile/test/package từ output đã dọn; không đánh đồng cache dependency với incremental build.
- Ghi **wall-clock elapsed time** bằng đồng hồ bên ngoài Maven, kiểm tra exit code và số test, lặp nhiều cặp đo rồi tính trung vị.
- Phân tích phần thời gian có thể quy cho repository cache và phần không thể tách hoàn toàn, đưa ra hướng sử dụng cache trong CI an toàn.

Mục tiêu là tìm ra câu trả lời có căn cứ cho: “Build chậm do Maven cần tải artifact từ xa, hay do chính các công đoạn compile/test/package?” Không dùng một lần bấm nút Build trong IDE rồi kết luận Maven cache đã tăng tốc bao nhiêu.

## 2. Maven local repository lưu những gì?

Maven có **local repository** trên máy đang chạy và **remote repositories** được cấu hình qua POM/settings/super POM. Đường dẫn local mặc định thường là `${user.home}/.m2/repository`, nhưng có thể thay bằng:

```bash
mvn -Dmaven.repo.local=/path/to/isolated-repo -B clean verify
```

Đường dẫn trong lệnh trên là **ví dụ cú pháp**, phải thay bằng một thư mục thực tế được phép ghi. `-Dmaven.repo.local` chọn vị trí **local artifact cache**, không tự thay remote repositories, Maven version, JDK hay project GAV.

Một local repository có thể chứa:

| Nhóm artifact | Ví dụ | Lý do nó có thể được tải |
| --- | --- | --- |
| Dependency trực tiếp | `org.apache.commons:commons-lang3:3.14.0` | Project khai báo ở `<dependencies>` |
| Dependency bắc cầu | JUnit Platform/Jupiter components | Dependency khác cần chúng |
| Maven build plugin | Compiler, Surefire, Resources, Clean, JAR | Maven lifecycle gọi plugin goals |
| Dependency của plugin | Libraries do plugins dùng | Plugin có dependency graph riêng |
| Parent POM/BOM | Project dùng `<parent>`, import BOM | Maven phải xây effective model |
| Metadata / tracking | File mô tả artifact và nguồn repository | Maven Resolver quản lý cache/resolution |
| Artifact đã install | JAR/POM từ `mvn install` | Local repository còn là nơi lưu artifact do developer build |

**Không phải mọi file trong `.m2` là “download cache”.** Maven local repository vừa lưu remote downloads vừa lưu các artifacts được install tại chỗ. Maven Resolver có metadata, locking và các biến thể layout; không nên tự thao tác/xóa các file nội bộ bằng script như một API chính thức.

### 2.1. Các thư mục phải phân biệt

```text
project/
├── pom.xml
├── src/
└── target/                     build output của project

~/.m2/repository/                Maven local repository mặc định
~/.m2/settings.xml               user settings, KHÔNG phải artifact cache
~/.m2/wrapper/dists/             ví dụ nơi Maven Wrapper cache distribution
```

`mvn clean` thường xóa output `target/` của project nhờ Maven Clean Plugin. Nó **không có nhiệm vụ xóa `~/.m2/repository`**. Do đó:

```bash
mvn clean verify
mvn clean verify
```

là hai clean builds của **project output**, nhưng lần thứ hai thường vẫn sử dụng local Maven repository đã warm. Không thể gọi lần thứ hai là “dependency-cold” chỉ vì có chữ `clean`.

### 2.2. Maven Wrapper có cache riêng

Nếu dùng `./mvnw`, lần đầu Wrapper có thể cần tải Maven distribution trước cả khi Maven chạy. Download đó là **Wrapper bootstrap**, không đồng nhất với Maven local repository download. Khi benchmark, cần chạy `./mvnw -version` trước chuỗi đo để **chốt/chuẩn bị Maven distribution**, đồng thời ghi rõ thao tác bootstrap không được tính trong cold artifact-cache build.

Wrapper pin Maven version, **không tự pin JDK hay tự tải mọi project dependency**. Để đối chiếu công bằng, cố định JDK, Maven distribution, Wrapper version và settings.

## 3. Bốn loại “cold/warm” dễ bị nhầm

| Tình huống | `target/` | Maven local repository | Câu hỏi thực sự |
| --- | --- | --- | --- |
| **A. Cold repository, clean build** | Được clean | Mới/trống | Giá tải mới dependencies/plugins + toàn bộ build |
| **B. Warm repository, clean build** | Được clean | Đã chứa dependencies từ A | Chi phí build khi không phải tải lại phần lớn artifacts |
| C. Warm repository, incremental build | Giữ output trước đó | Warm | Lợi ích tránh làm lại compile/resources/test khi có up-to-date checks |
| D. Warm repository, offline clean build | Được clean | Đã có artifacts | Khả năng build khi không truy cập remote |

**Phép so sánh đúng chủ đề này là A so với B**, không phải A so với C hoặc D.

Trong A và B, cả hai lệnh nên giống hệt, chẳng hạn:

```bash
mvn -B -ntp "-Dmaven.repo.local=/absolute/path/to/repo" clean verify
```

Chỉ **trạng thái repository trước lệnh** thay đổi. Tên directory có thể khác giữa các cặp benchmark, nhưng trong mỗi cặp cold/warm phải dùng **cùng path**.

C và D vẫn hữu ích, nhưng là **những thí nghiệm riêng**: incremental caching có thể làm ít công việc hơn; offline mode thay chính sách truy cập remote.

## 4. Điều gì xảy ra trong một cold build?

Quá trình đơn giản hóa:

```text
Maven khởi động và đọc POM/settings
           |
           v
Xây effective POM và plugin/dependency graph
           |
           v
Local repository thiếu JAR/POM/plugin?
           |
       có  |  không
           v
Resolve từ remote repositories/mirrors
           |
           v
Tải artifact/metadata, xác thực/checksum theo cấu hình
           |
           v
Lưu artifact vào local repository
           |
           v
Chạy Clean → Resources → Compile → Test → Package → Verify
           |
           v
Ghi logs, Surefire XML, JAR và thời gian
```

Khi repo trống, Maven có thể phải tải **không chỉ một dependency trực tiếp** mà còn rất nhiều POMs/transitive dependencies/plugin artifacts. Ví dụ project cần Compiler/Surefire plugins, các artifact của JUnit và Apache Commons Lang. Số lượng và thời lượng tải phụ thuộc effective POM, Maven version, mirrors và bộ artifact đã có.

Với repo warm, Maven có thể resolve phần lớn artifact từ đĩa cục bộ, **nhưng không đảm bảo mọi remote request biến mất**: SNAPSHOT update policy, metadata checks, thiếu artifact mới, changed profiles, dynamic version ranges và repository rules vẫn có thể kích hoạt network.

### 4.1. “Cold” của Maven repo không phải “cold” toàn máy

Ngay cả khi `.m2` mới, hệ điều hành có thể vẫn giữ OS file cache, DNS cache, TLS session state hoặc trạng thái antivirus từ một lần chạy khác. CPU có thể đổi tần số; remote repository CDN có thể gần hơn hoặc chậm hơn. Bởi vậy chỉ nói:

> “Lượt cold của **Maven local artifact repository** trong môi trường đo này.”

Không nói “đã mô phỏng máy mới hoàn toàn” trừ khi có môi trường VM/container mới, mạng và cache được kiểm soát sâu hơn.

## 5. Thiết kế benchmark công bằng

### 5.1. Những biến phải giữ cố định

1. **Cùng source commit, POM, dependency versions và profiles.** Không thay code giữa hai lượt.
2. **Cùng Maven version**, tốt nhất dùng Maven Wrapper đã pin.
3. **Cùng JDK** cho Maven, compiler và tests; kiểm `mvn -version`.
4. **Cùng Maven goals**, ví dụ `clean verify` trong cả cold và warm.
5. **Cùng flags**, không thêm `-o`, `-U`, `-DskipTests` hoặc `-T` chỉ cho một bên.
6. **Cùng settings, mirrors, credentials, proxy**, kể cả repository plugin.
7. **Cùng máy/CPU/memory/disk**, hạn chế workloads lớn khác khi đo.
8. **Cùng test workload**; không dùng flaky tests hoặc data thay đổi qua thời gian.
9. **Cùng cách thu thập thời gian**, ưu tiên `time.perf_counter()` hoặc monotonic wall clock.
10. **Cùng điều kiện kết thúc**, kiểm Maven return code và test count.

Không thay log verbosity giữa hai lượt: `-B` không tương tác và `-ntp` tắt thanh tiến độ transfer để console output ổn định hơn. Dùng `-ntp` ở **cả hai**.

### 5.2. Khuyến nghị lặp theo cặp

Một cặp benchmark:

```text
Tạo repo R1 mới (ban đầu trống)
    cold(R1): clean verify
    warm(R1): clean verify
Kết thúc cặp, bỏ R1
Tạo repo R2 mới
    cold(R2): clean verify
    warm(R2): clean verify
...
```

Lặp ít nhất **3 cặp** khi khả thi. Báo **median cold**, **median warm**, **median của chênh lệch trong từng cặp**, và số cặp. Dữ liệu thực tế có thể dao động mạnh do mạng; không khẳng định số đo từ một cặp là “mức tăng tốc của Maven” nói chung.

**Thứ tự cold rồi warm trong cùng cặp là bắt buộc để warm chính repo đã được cold điền đầy.** Nó tạo độ lệch có thể có do OS cache/JIT/điều kiện máy theo thời gian. Nếu cần nghiên cứu nghiêm ngặt, thực hiện thêm những đối chứng nhiệt độ máy, VM snapshots và điều kiện mạng/CPU khác. Với mục tiêu training và CI, paired benchmark đã cung cấp thông tin hữu ích về tác động của dependency repository cache.

## 6. Ví dụ Maven Java 17 có dependencies và tests thật

Ta dùng một project nhỏ, đơn module. Nó được chọn để dễ quan sát tải Commons Lang và JUnit, không nhằm mô phỏng thời lượng của một repository vài triệu dòng.

Cấu trúc:

```text
cache-build-lab/
├── pom.xml
├── src/main/java/demo/cache/
│   ├── PriceLabel.java
│   └── Main.java
├── src/test/java/demo/cache/
│   └── PriceLabelTest.java
└── benchmark.py
```

Điều kiện: JDK 17+, Maven 3.9.x (hoặc Maven 3 hỗ trợ plugins đã pin), Python 3.9+ để chạy script benchmark, truy cập repository/mirror được phép. Thực hành không cần database, container hoặc dịch vụ ngoài Maven repositories.

### 6.1. pom.xml hoàn chỉnh

Tệp `cache-build-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.cache</groupId>
    <artifactId>cache-build-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
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

Những điểm quan trọng cho benchmark:

- Compiler Plugin dùng `release=17`; Java code và tests chạy dưới JDK phù hợp.
- Commons Lang **thực sự được sử dụng** trong production code, vì vậy Maven phải resolve nó cho compile.
- JUnit Jupiter 5.10.2 ở scope test, Surefire 3.2.5 chạy các test methods.
- Clean, Resources, Compiler, Surefire và JAR Plugin được pin, tránh các plugin version ngầm thay đổi giữa lần cold/warm.
- Artifact là một JAR thông thường; không cần `install`, `deploy`, network services hay DB.
- `clean verify` biên dịch, kiểm thử và đóng gói lại ở **cả hai lượt**.

Đây là một project minh họa có artifact version 1.0.0; plugin/dependency versions chỉ được pin để bài tập tái hiện dễ hơn, **không khẳng định chúng là phiên bản mới nhất hoặc có support/security status phù hợp mọi dự án**.

## 7. Production code: PriceLabel.java

Tệp `src/main/java/demo/cache/PriceLabel.java`:

```java
package demo.cache;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class PriceLabel {
    private PriceLabel() {
    }

    public static String format(String rawSku, long cents) {
        String sku = StringUtils.upperCase(
                StringUtils.trimToEmpty(rawSku), Locale.ROOT);
        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku required");
        }
        if (cents < 0) {
            throw new IllegalArgumentException("negative cents");
        }
        return "SKU " + sku + " / " + cents + " cents";
    }
}
```

`StringUtils.trimToEmpty` và `StringUtils.upperCase(String,Locale)` thuộc Commons Lang; nếu dependency không resolve, compile sẽ fail. `Locale.ROOT` bảo đảm uppercase ổn định thay vì phụ thuộc locale máy. `String.isBlank()` có trong Java 11+, nên Java 17 hợp lệ.

Tệp `src/main/java/demo/cache/Main.java`:

```java
package demo.cache;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(PriceLabel.format("  tea  ", 2500));
    }
}
```

Sau `mvn clean verify`, có thể chạy bằng classpath gồm ứng dụng và Commons Lang. Ví dụ trên Linux/macOS khi local repository mặc định được sử dụng:

```bash
java -cp "target/classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" demo.cache.Main
```

Stdout **chính xác của chương trình Java**, nếu classpath có đúng Commons Lang:

```text
SKU TEA / 2500 cents
```

**Quan trọng:** các benchmark ở phần sau đặt `-Dmaven.repo.local` vào **repository tạm**. Khi đó lệnh `java -cp` trỏ `~/.m2` ở trên **không còn đúng vị trí dependency đã tải**. Mục tiêu của bài là so sánh `mvn clean verify`, không bắt buộc chạy Main. Nếu muốn chạy main từ isolated repo, thay đường dẫn JAR theo local repo tương ứng hoặc dùng Exec Plugin để dựng runtime classpath. Đừng nhầm lỗi classpath khi chạy `java` thủ công với lỗi Maven benchmark.

## 8. Unit tests: bốn trường hợp để bảo đảm workload tương đương

Tệp `src/test/java/demo/cache/PriceLabelTest.java`:

```java
package demo.cache;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceLabelTest {

    @Test
    void formatsNormalizedSku() {
        assertEquals("SKU TEA / 2500 cents",
                PriceLabel.format("  tea  ", 2500));
    }

    @Test
    void handlesZeroCents() {
        assertEquals("SKU BOOK / 0 cents",
                PriceLabel.format("book", 0));
    }

    @Test
    void rejectsBlankSku() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> PriceLabel.format("   ", 100));
        assertEquals("sku required", error.getMessage());
    }

    @Test
    void rejectsNegativeCents() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> PriceLabel.format("tea", -1));
        assertEquals("negative cents", error.getMessage());
    }
}
```

Mỗi lượt build có **4 JUnit tests**, kỳ vọng failures/errors/skipped đều bằng 0:

```text
PriceLabelTest: 4 tests
Failures: 0
Errors:    0
Skipped:   0
```

Đây là **expected test summary**, không phải log Maven đã thực sự được chạy. Script đo phải **kiểm lại báo cáo Surefire XML sau từng lượt**: nếu một lượt skip tests hoặc fail thì thời gian của nó không còn so sánh công bằng với lượt thành công còn lại.

Không chọn flag `-DskipTests`, `-Dmaven.test.skip=true` hoặc bỏ `clean` cho riêng warm build; các flags đó làm thay đổi khối lượng công việc, không chỉ thay repository cache.

## 9. Cách đo thủ công: cùng local repository, cold trước warm sau

Trước tiên xác nhận công cụ:

```bash
java -version
mvn -version
```

Nếu repository có Maven Wrapper đã kiểm tra/commit, có thể dùng `./mvnw` và chạy `./mvnw -version` **trước khi bắt đầu timing**. Để ví dụ tự đứng độc lập khi chưa có Wrapper, các lệnh bên dưới dùng `mvn` đã cài.

### 9.1. Linux/macOS

Từ thư mục `cache-build-lab/`:

```bash
REPO="$(mktemp -d)"

# Cold: local artifact repo mới.
time mvn -B -ntp "-Dmaven.repo.local=$REPO" clean verify

# Warm: dùng lại chính repository của cold.
time mvn -B -ntp "-Dmaven.repo.local=$REPO" clean verify
```

`mktemp -d` tạo một directory trống ở vị trí do hệ điều hành chọn. **Lệnh đo thứ hai dùng lại đúng `$REPO`**, do đó phần lớn dependencies/plugins đã được tải ở lượt đầu. Cả hai lệnh đều thực hiện `clean verify`.

Đọc:

- Shell `real`/elapsed time (không so nhầm `user`/`sys` CPU time).
- Maven `BUILD SUCCESS` và exit code.
- Số test có trong Surefire XML.
- Những dòng “Downloading from ...”, “Downloaded from ...” hoặc resolver logs khi có (cách hiển thị phụ thuộc flags/version).
- Kích thước/điểm đặt local repo, thông tin mirror/remote policy.

**Không dùng `rm -rf ~/.m2` để làm cold build.** Lệnh đó có thể xóa cache nhiều dự án và locally installed artifacts. Tạo repo riêng để không tác động dữ liệu thường ngày.

Nếu người đọc định dọn directory `$REPO`, chỉ dọn đúng directory tạm đã tạo cho phép đo theo quy định máy. Bài không yêu cầu script xóa hay sửa cache mặc định của người dùng.

### 9.2. Windows PowerShell

Từ `cache-build-lab/`:

```powershell
$repo = Join-Path $env:TEMP (
    'maven-cache-bench-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $repo | Out-Null

$cold = Measure-Command {
    mvn -B -ntp "-Dmaven.repo.local=$repo" clean verify
    if ($LASTEXITCODE -ne 0) { throw 'Cold Maven build failed' }
}
$warm = Measure-Command {
    mvn -B -ntp "-Dmaven.repo.local=$repo" clean verify
    if ($LASTEXITCODE -ne 0) { throw 'Warm Maven build failed' }
}

Write-Output ("Cold seconds: {0:F3}" -f $cold.TotalSeconds)
Write-Output ("Warm seconds: {0:F3}" -f $warm.TotalSeconds)
```

PowerShell `Measure-Command` trả một `TimeSpan`, lấy `TotalSeconds` (không lấy `Seconds`, vì `Seconds` chỉ là thành phần giây 0–59). `Guid.NewGuid()` giúp tránh tái sử dụng repo cũ. Cần đảm bảo Maven đã cài và truy cập được remote dependencies.

Khi có `mvnw.cmd` trong project, thay `mvn` bằng `.\mvnw.cmd` ở cả hai lệnh. Không đo lần Wrapper tải Maven distribution nếu mục tiêu là **local artifact-cache performance**.

### 9.3. Những trường hợp phép đo thủ công chưa đủ

Hai lần chạy chỉ là **một cặp sample**; mạng lúc đầu có thể nhanh/chậm bất thường. OS/JVM cũng được làm nóng dần. Kết luận tốt hơn cần nhiều cặp và thống kê trung vị. Phần sau có script Python thu thập đồng nhất, không bắt người đọc tính tay và không giả định thời gian cố định.

## 10. Script Python 3 đầy đủ: ba cặp cold/warm, tự kiểm tests

Tạo tệp `cache-build-lab/benchmark.py`. Script:

- Tự chọn `mvnw.cmd`/`mvnw` nếu Wrapper tồn tại, ngược lại dùng `mvn` trên PATH.
- Chạy `-version` trước benchmark để chuẩn bị Maven distribution nếu dùng Wrapper.
- Với mỗi cặp, tạo `TemporaryDirectory` trống làm Maven local repository.
- Chạy **cold `clean verify`**, rồi **warm `clean verify`** trên cùng directory.
- Tính wall-clock bằng `time.perf_counter()`.
- Bỏ phép đo và báo lỗi nếu Maven return code khác 0.
- Đọc **Surefire `TEST-*.xml`** mới và xác nhận chính xác 4 tests, không failure/error/skipped.
- Xác nhận main JAR sau build tồn tại.
- In elapsed seconds của từng cặp, sau đó median cold/warm và median phần trăm chênh lệch.
- Tự thu dọn **chỉ những TemporaryDirectory do script tạo**, không đụng đến `~/.m2`.

```python
from pathlib import Path
from statistics import median
import os
import subprocess
import tempfile
import time
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
PAIRS = 3
WRAPPER = ROOT / ("mvnw.cmd" if os.name == "nt" else "mvnw")
MAVEN = str(WRAPPER) if WRAPPER.is_file() else "mvn"
EXPECTED_JAR = ROOT / "target" / "cache-build-lab-1.0.0.jar"
REPORT_DIR = ROOT / "target" / "surefire-reports"


def call_maven(args):
    result = subprocess.run(
        [MAVEN, *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-45:])
        raise RuntimeError(
            "Maven failed (exit code "
            + str(result.returncode) + "):\n" + tail
        )
    return result.stdout


def check_build_output():
    if not EXPECTED_JAR.is_file():
        raise RuntimeError("Missing expected packaged JAR")

    reports = sorted(REPORT_DIR.glob("TEST-*.xml"))
    if len(reports) != 1:
        raise RuntimeError(
            f"Expected 1 Surefire test suite, found {len(reports)}"
        )

    totals = dict(tests=0, failures=0, errors=0, skipped=0)
    for path in reports:
        suite = ET.parse(path).getroot()
        if suite.tag != "testsuite":
            raise RuntimeError(f"Unexpected XML root in {path}")
        for key in totals:
            totals[key] += int(suite.get(key, "0"))

    if totals != dict(tests=4, failures=0, errors=0, skipped=0):
        raise RuntimeError(f"Unexpected test results: {totals}")

    return EXPECTED_JAR.stat().st_size


def measure(repo):
    args = [
        "-B",
        "-ntp",
        f"-Dmaven.repo.local={repo}",
        "clean",
        "verify",
    ]
    start = time.perf_counter()
    call_maven(args)
    elapsed = time.perf_counter() - start
    jar_bytes = check_build_output()
    return elapsed, jar_bytes


def main():
    # Bootstrap Wrapper/verify Maven before measuring.
    version_log = call_maven(["-version"])
    print(version_log.splitlines()[0])
    cold_times = []
    warm_times = []
    paired_reductions = []

    for number in range(1, PAIRS + 1):
        with tempfile.TemporaryDirectory(
            prefix="maven-local-cache-pair-"
        ) as directory:
            repo = Path(directory).resolve()

            cold, cold_size = measure(repo)
            warm, warm_size = measure(repo)

            if cold_size != warm_size:
                raise RuntimeError(
                    "Packaged JAR size differs within a pair"
                )

            reduction = 100.0 * (cold - warm) / cold
            cold_times.append(cold)
            warm_times.append(warm)
            paired_reductions.append(reduction)

            print(
                f"Pair {number}: cold={cold:.3f}s; "
                f"warm={warm:.3f}s; "
                f"observed_reduction={reduction:.1f}%"
            )

    print(f"Median cold: {median(cold_times):.3f}s")
    print(f"Median warm: {median(warm_times):.3f}s")
    print(
        "Median paired reduction: "
        f"{median(paired_reductions):.1f}%"
    )


if __name__ == "__main__":
    main()
```

### 10.1. Chạy script

Tại project root:

```bash
python3 benchmark.py
```

Windows PowerShell, nếu dùng Python launcher:

```powershell
py -3 benchmark.py
```

Script dùng các package thuộc Python standard library, không cần pip install. Mỗi cặp tạo một local Maven repository mới, vì vậy **cả ba cold lượt đều có thể tải nhiều plugins/dependencies từ xa**, tốn mạng và disk. Đừng chạy lặp lớn trên repository manager có quota hoặc môi trường có giới hạn băng thông mà không xét chi phí.

### 10.2. Định dạng output và ý nghĩa

Script sẽ in **số đo thực tế**, không có một stdout thời gian cố định vì mỗi máy/mạng khác nhau. Mỗi dòng `Pair` chứa elapsed cold, elapsed warm và observed percentage reduction; cuối có median của các nhóm.

Công thức trong từng cặp:

\[
\text{reduction (\%)} =
\frac{T_{\mathrm{cold}}-T_{\mathrm{warm}}}
{T_{\mathrm{cold}}}\times100
\]

Nếu warm chậm hơn cold, phần trăm **âm**; đó là một quan sát cần điều tra chứ không được sửa dữ liệu cho đẹp. Nếu cold và warm gần bằng nhau, phần tải artifacts có thể nhỏ so với compile/test hoặc local mirror đã rất nhanh.

Median của từng nhóm và **median tỷ lệ giảm theo cặp** không nhất thiết bằng cách lấy tỷ số từ hai median. Script trình bày riêng các giá trị đó để tránh suy diễn sai.

### 10.3. Vì sao xác minh JAR size nhưng không gọi đó là reproducible build?

Script kiểm cùng test count và cùng kích thước JAR trong mỗi cặp như một **sanity check**. Hai JAR cùng kích thước **không chứng minh byte giống nhau**. Các entry ZIP timestamps và metadata có thể làm SHA-256 khác dù Java behavior giống nhau. Khi cần reproducibility analysis, phải thiết kế deterministic packaging, output timestamps và so checksum theo chính sách riêng.

### 10.4. Khi script dừng do lỗi

`call_maven()` trả nonzero sẽ khiến script báo những dòng cuối của Maven output. Đó là **failed benchmark sample**, không được đưa vào median như một số đo build thành công.

`check_build_output()` cũng fail nếu Surefire không tạo đúng một `TEST-*.xml`, nếu test count không phải 4 hoặc có errors/failures/skips. Với project thực tế có nhiều suites/tests, phải sửa expected policy cho đúng; không dùng script mẫu như parser tổng quát cho mọi Maven project.

**Bảo mật:** Maven console logs có thể chứa URL nội bộ, đường dẫn hoặc thông tin test nhạy cảm. Chỉ chia sẻ các giá trị đã rà soát; không tải raw logs lên nơi công khai theo thói quen.

## 11. Đọc đúng các thành phần của thời gian build

Wall-clock của một lượt `mvn clean verify` có thể gồm:

| Thành phần | Có ở cold? | Có ở warm? | Nhận định |
| --- | --- | --- | --- |
| Maven JVM startup, đọc settings/POM | Có | Có | Không phải dependency download |
| Tạo Maven effective model và dependency graph | Có | Có | Có thể rẻ hơn nếu metadata sẵn |
| Resolve/tải plugin JAR và dependencies | Có thể nhiều | Thường ít hơn | Đây là mục tiêu so cache |
| Remote metadata/SNAPSHOT check | Tùy policy | Có thể vẫn xảy ra | Warm không đồng nghĩa 0 request |
| Clean `target` | Có | Có | Workload cố định |
| Process resources | Có | Có | Cả hai đều xây lại output |
| Compile source | Có | Có | Không nên bị bỏ qua do incremental |
| Compile/run JUnit tests | Có | Có | Cần cùng test count |
| JAR packaging | Có | Có | Giữ cấu hình plugin như nhau |
| OS page cache/antivirus/JIT effects | Có | Có | Nhiễu khó loại bỏ hoàn toàn |

Trong log Maven, `Total time` mô tả thời gian mà Maven đo nội bộ; thời gian shell/Python đo **cả Maven launcher/JVM startup**. Hai con số có thể khác, nên ghi **loại thời gian** khi so benchmark.

### 11.1. Phân biệt tải lần đầu với dependency graph luôn phải resolve

Maven có thể vẫn phải xây graph, đọc POM, kiểm metadata và tra local cache mỗi lần. “Có file trong cache” không có nghĩa Maven không chạy Maven Resolver nữa. Nhưng không phải tải lại đầy đủ JAR từ remote sẽ thường giúp giảm thời gian khi mạng là một bottleneck.

### 11.2. Repository cache nóng chưa chắc làm build nhanh

Một build CPU-bound với rất nhiều annotation processing, compile hoặc integration tests chậm có thể gần như không thay đổi giữa cold/warm. Một remote mirror nội bộ rất nhanh cũng làm chênh lệch nhỏ. Ngược lại, một corporate proxy chậm hoặc nhiều plugin downloads có thể khiến cold vượt warm rất xa.

**Chỉ có kết quả đo trên workload thật** mới cho phép ưu tiên tối ưu hóa cache so với compiler/test/IO.

## 12. Offline mode: phép thử riêng, không phải warm build tương đương

Maven CLI `-o`/`--offline` yêu cầu Maven **không truy cập remote repositories**.

Sau một lần warm repo:

```bash
mvn -B -o -ntp "-Dmaven.repo.local=/absolute/path/to/warm-repo" clean verify
```

Nếu mọi artifact cần thiết đã được cache với metadata phù hợp, offline build có thể pass. Nếu thiếu một plugin, POM, dependency, artifact platform-specific hoặc snapshot metadata thì offline build fail. **Lần cold với repo trống thường không thể offline thành công** trong một project cần plugins/dependencies chưa có, và không có ý nghĩa so hiệu năng remote download.

Đừng so:

```text
cold online build
warm offline build
```

rồi quy toàn bộ chênh lệch cho Maven cache. Bạn đã thay đổi **cả cache state và network policy**. Offline là một thí nghiệm **khả năng build không cần mạng**, nên giữ riêng bảng kết quả.

### 12.1. dependency:go-offline có tác dụng gì?

Maven Dependency Plugin cung cấp goal `dependency:go-offline` để resolve project dependencies cùng nhiều plugin/report dependencies trước khi offline. Ví dụ, nếu dùng plugin phù hợp với Maven hiện tại:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:go-offline
```

Goal này hữu ích để chuẩn bị cache nhưng **không phải bằng chứng tuyệt đối** mọi build goal/profile/extension sẽ chạy offline: có những dependency chỉ được resolve trong một goal, profile, plugin execution hoặc môi trường runtime cụ thể.

Nếu muốn benchmark **cold download**, đừng chạy `go-offline` trên repo thử nghiệm **trước lượt cold**, vì nó đã warm repo và làm hỏng phép so sánh. Có thể dùng `go-offline` trong một **nghiên cứu khác** về chiến lược prefetch cache của CI, hoặc để chuẩn bị môi trường offline.

## 13. -U, SNAPSHOT, updatePolicy và cache freshness

Maven CLI `-U`/`--update-snapshots` có thể ép kiểm tra remote về missing releases/updated snapshots. SNAPSHOT versions có thể được deploy nhiều lần và remote metadata/updatePolicy quyết định khi nào Maven hỏi lại. Vì vậy một repo đã “warm” nhưng dùng SNAPSHOT vẫn có thể thực hiện network I/O.

Để benchmark tác động **cache artifact download cơ bản**, ví dụ sử dụng **version cố định dạng release** của Commons Lang/JUnit/plugins. Không bật `-U` riêng cho cold hoặc warm. Với dự án dùng SNAPSHOT/metadata động, ghi rõ:

- Có artifact SNAPSHOT nào?
- Remote updatePolicy hiện hành?
- Có `-U` hay `-nsu` hay không?
- Có metadata/POM được update ngoài ý muốn không?
- Mirror/server có cache policy thế nào?

**Chọn một thử nghiệm riêng** nếu muốn đo “warm cache + kiểm tra cập nhật SNAPSHOT” hoặc “dependency update latency”. Không pha lẫn với cold/warm baseline.

## 14. Cache phụ thuộc và build incrementality là hai vấn đề khác nhau

So sánh:

```bash
mvn clean verify
mvn clean verify
```

và:

```bash
mvn verify
mvn verify
```

Khác nhau ở chỗ cặp thứ hai có thể giữ lại `target/classes`, processed resources và test outputs. Maven compiler/plugin/test behavior có thể dùng một số kiểm tra up-to-date, song mức incremental thực tế phụ thuộc plugin/version/configuration. Dòng `mvn verify` không tự có nghĩa Java compile/test được bỏ qua hoàn toàn.

Để đo hiệu quả của local artifact cache, **luôn giữ `clean verify` ở cả hai lượt**, khi đó code vẫn được compile/test/package. Nếu mục tiêu tối ưu iteration development, đo thêm một bảng riêng cho incremental build và ghi rõ source files có thay đổi hay không.

| Benchmark | Câu hỏi | Lệnh hai phía |
| --- | --- | --- |
| Dependency cache | Download/resolution có làm cold chậm? | `clean verify` vs `clean verify` |
| Incremental build | Giữ `target` có giảm công việc? | `verify` sau một build vs `verify` tiếp |
| Compile-only | Test workload ảnh hưởng bao nhiêu? | Đo cùng mục tiêu phase, tách thí nghiệm |
| Offline readiness | Có thể build không cần network? | Warm cache rồi `-o clean verify` |
| Multi-module selection | Chỉ build module liên quan có nhanh hơn? | `-pl/-am` theo graph, khác phạm vi workload |
| Parallelism | `-T` có giảm elapsed time? | Cùng cache state, cùng workload, thread count khác |

Không tự coi `-DskipTests`, `-Dmaven.test.skip` hoặc `-T4` là cách “warm cache” — chúng thay công việc/phân phối CPU.

## 15. Vì sao không nên xóa ~/.m2/repository để làm benchmark?

Một người dùng có thể có hàng GB dependencies, project-local installed artifacts, plugin metadata và private packages trong local Maven repository. Xóa toàn bộ kho để đo cold build:

- Gây mất cache của **nhiều project khác**.
- Gây downloads lớn, tăng tải lên corporate repository manager.
- Có thể làm mất artifacts do `mvn install` mà chưa được deploy ở đâu.
- Làm developer hoặc CI jobs khác chậm đi.
- Không bảo đảm “cold toàn hệ thống” vì OS/Maven Wrapper/network caches vẫn còn.
- Gây rủi ro khi nhiều Maven processes đồng thời dùng cùng local repo.

**Cách đúng:** tạo **một local repository riêng, mới/trống**, trỏ nó qua `-Dmaven.repo.local`, thử trên đó và chỉ dọn directory thử nghiệm do chính workflow tạo ra. Đừng can thiệp default cache của người khác. Trong CI, hãy dùng unique directory hoặc cache policy được vận hành có kiểm soát.

## 16. Cache strategy cho CI

Các CI platforms thường cho phép lưu cache Maven local repository giữa những jobs/runs. Ý tưởng:

```text
Checkout source tại commit N
          |
          v
Khôi phục cache Maven theo key/policy
          |
          v
Maven clean verify
          |
          v
Lưu test reports/artifacts
          |
          v
Lưu cache Maven (nếu policy cho phép)
```

Điều quan trọng là **cache không thay thế artifact provenance hoặc QA**. Dù cache hit, CI vẫn phải compile/test đúng commit.

### 16.1. Cache key nên xét gì?

| Chiều | Vì sao có thể quan trọng |
| --- | --- |
| OS/CPU architecture | Native/classifier artifacts có thể khác |
| JDK major/vendor khi có native/toolchain deps | Classifier và plugin compatibility có thể khác |
| Maven major/version | Resolver/plugin behavior và layout có thể thay |
| POM/parent/BOM/lockfiles | Tập dependency và plugins thay đổi |
| Active profiles | Dependencies có thể khác |
| settings/mirror namespace | Private artifacts và nguồn tải khác |
| Snapshot/update policy | Cache có thể stale, không dùng như immutable release |
| Security boundary | Không tái sử dụng private artifact của dự án/tài khoản khác |

Không nhất thiết mỗi lần `pom.xml` đổi là phải bỏ toàn bộ cache; Maven Resolver vẫn có thể dùng các artifact version cũ hợp lệ và chỉ tải phần thiếu. Cache key có thể chọn chiến lược **strict** hoặc **prefix/fallback**, theo mức độ tin cậy và nguy cơ stale.

### 16.2. Cache Maven an toàn

- Không cache secrets trong `settings.xml`, token/cert private hoặc logs chứa credentials.
- Không dùng chung cache ghi được giữa các job không tin cậy nếu có nguy cơ artifact poisoning.
- Giới hạn quyền đọc/ghi và scope của private dependencies.
- Xử lý repository manager/certificate update thay vì vô hiệu TLS validation.
- Không mặc định tin SHA-256 của local cache bằng artifact remote nếu provenance yêu cầu mạnh: cần verify repository/checksum/signature theo policy.
- Chống cache restore thành nguồn supply-chain không kiểm soát.
- Nếu nhiều job dùng chung một local repository thực, phải lưu ý file locking/concurrent Maven Resolver; ưu tiên một cache snapshot restore riêng cho mỗi job thay vì cùng thao tác vào một thư mục writable.

### 16.3. Cache hit không bằng test pass

Một job có cache hit có thể vẫn fail vì Java source sai, flaky tests, missing configuration, stale SNAPSHOT, dependency conflict hoặc repository permissions. CI chỉ nên promote artifact khi Maven exit code/test reports đạt chính sách.

### 16.4. Tối ưu chi phí thực tế

Đôi khi việc upload/download cache artifact qua CI cache service còn **chậm hơn** truy cập một repository manager nội bộ nhanh. Để quyết định, so:

1. Thời gian restore cache.
2. Thời gian Maven build.
3. Thời gian save cache.
4. Dung lượng cache và chi phí truyền tải.
5. Cache hit rate và tần suất eviction.
6. Mức độ ổn định/quyền truy cập remote repository.

**Thời gian pipeline tổng** mới là chỉ số giá trị kinh doanh; không chỉ nhìn `mvn verify` sau khi cache đã được restore.

## 17. Hai loại elapsed time cần phân biệt

Maven thường in một dòng `Total time`, còn Python script đo từ lúc khởi động Maven command đến khi process kết thúc.

- **External wall-clock**: gồm shell/launcher/JVM startup, xử lý Maven goals và process shutdown.
- **Maven internal Total time**: Maven đo phần do nó quản lý; không nhất thiết gồm toàn bộ launcher overhead.
- **CPU time**: tổng thời gian CPU của process(es), không đồng nhất với elapsed wall-clock.
- **Download elapsed**: phụ thuộc network latency, transfer sizes, TLS/proxy và metadata calls.

Đừng trộn số `real` từ `time`, `TotalSeconds` từ PowerShell và Maven `Total time` vào một chart mà không ghi rõ loại metric. Để benchmark cặp, script sử dụng **một loại metric nhất quán: external monotonic elapsed seconds**.

### 17.1. Median, chênh lệch và bất định

Có thể báo:

| Chỉ số | Ý nghĩa |
| --- | --- |
| N cặp | Số cold/warm pairs chạy hoàn chỉnh |
| Median cold | Trung vị wall-clock của các cold runs |
| Median warm | Trung vị wall-clock của các warm runs |
| Median paired reduction | Trung vị phần trăm giảm trong từng cặp |
| Min/max hoặc IQR | Độ dao động kết quả nếu có nhiều lần đo |
| Failures/missing tests | Loại samples không hợp lệ, không đưa vào thống kê |
| Environment | JDK/Maven, OS, source commit, mirror/network |

Một vài lượt benchmark không đủ để đưa ra cam kết SLA; dùng như phép chẩn đoán. Nếu kết quả có outlier lớn do lỗi remote/CI queue, ghi nhận nguyên nhân và đo lại theo protocol, không âm thầm loại sample bất lợi.

## 18. Kiểm nguồn tải khi đọc Maven logs

Trong cold repo, Maven có thể ghi:

```text
Downloading from ...
Downloaded from ...
```

Đây là **kiểu dòng log minh họa**, không phải bằng chứng mọi artifact đều được tải từ cùng một URL. Maven có thể dùng mirror từ `settings.xml`, repository manager, remote HTTP cache hoặc internal proxy.

Đối với benchmark production:

- Ghi mirror/repository ID và trạng thái network.
- Không log credentials hoặc dùng `-X` một cách bừa bãi trong CI public.
- Kiểm Maven update policies và SNAPSHOTs.
- Nếu cần download count/bytes chính xác, dùng Maven transfer listener/repository manager metrics có kiểm soát.
- Không coi việc log không hiện transfer progress khi có `-ntp` là bằng chứng tuyệt đối không có remote requests: `-ntp` tắt **progress**, không cấm network.

Nếu cold build rất chậm vì một repository endpoint lỗi rồi fallback sang endpoint khác, đây là vấn đề mirror/repository health, không chỉ “Maven chậm”.

## 19. Quyết định tối ưu hóa dựa trên kết quả

### 19.1. Cold chậm hơn warm rất nhiều

Các hướng cần xem:

- Dùng repository manager/mirror gần CI runners.
- Tránh tải lại dependencies/plugins cho mỗi job khi cache restore là an toàn và hiệu quả.
- Pin plugin/dependency versions, tránh version ranges không cần thiết.
- Kiểm các transitive dependencies và plugin graphs không cần.
- Tối ưu repository availability/TLS/proxy/DNS.
- Với job ngắn, xem tổng restore+build+save cost trước khi dùng cache service.

**Không cắt tests hoặc tắt checksum/TLS validation** để làm benchmark trông nhanh hơn.

### 19.2. Cold gần bằng warm

Có thể vì tests/compilation chiếm phần lớn; remote mirror quá nhanh; project ít dependencies; hoặc local OS cache/network conditions khiến chênh lệch khó quan sát. Khi đó cần đo chi tiết:

- Thời gian Maven goals/plugins.
- Thời gian test suites (Surefire XML).
- Compilation/Javac và annotation processing.
- File I/O và compiler daemon/tooling (nếu có).
- Xác minh cold repo thật sự trống trước lượt đầu.
- Kiểm `settings.xml`/mirrors và Maven wrapper bootstrap.

**Không kết luận cache Maven vô dụng** chỉ vì một project mẫu nhỏ có chênh lệch thấp.

### 19.3. Warm chậm hơn cold

Có thể do noise, OS scheduling, antivirus scan, JVM/GC, snapshot update, thread contention hoặc network metadata. Cần:

1. Lặp thêm cặp samples.
2. Xem Maven logs/error/repository requests.
3. Xác nhận tất cả lệnh dùng đúng repo/flags/JDK.
4. Kiểm Surefire test count và POM/profile không đổi.
5. Xem máy có bị CPU throttling, memory pressure hoặc I/O contention.
6. Tránh sửa số đo để cho ra “warm luôn nhanh”.

Một quan sát âm vẫn là kết quả cần được giữ nguyên trong báo cáo.

## 20. Multi-module builds: một reactor có thể che việc tải dependency

Trong Maven Reactor nhiều module, Maven có thể resolve một module artifact từ **reactor project** đang được build thay vì tải nó từ local repository. Khi đó, cold/warm local artifact cache vẫn ảnh hưởng các third-party dependencies và plugins, nhưng **không thể mặc định xem mọi inter-module dependency là network download**.

Khi đo multi-module:

```bash
mvn -B -ntp clean verify
```

phải chạy từ **cùng aggregator root** và cùng active profiles ở hai phía. Không chạy cold cho toàn Reactor nhưng warm chỉ một module:

```bash
mvn -B -ntp -pl :app -am clean verify
```

rồi quy chênh lệch cho cache, vì bạn đã thay số module và số tests thực thi. `-pl`, `-am`, `-amd`, `-rf` là các lựa chọn **Reactor scope**, không phải tùy chọn warm/cold.

Dùng effective POM và dependency tree để xác nhận workload và versions, rồi ghi số modules/tests được build ở mỗi run. Nếu muốn benchmark incremental reactor selection, làm một experiment riêng.

## 21. Dùng build cache cho artifact không đồng nghĩa local Maven dependency cache

Một số build tools/plugins có **build output cache** hoặc remote cache cho results của tasks/compilation/tests. Maven local repository trong bài này chủ yếu cache **artifact dependencies và plugin distribution**, không mặc nhiên cache kết quả compile của project.

Phân biệt:

| Loại cache | Cái gì được tái sử dụng? | Ví dụ |
| --- | --- | --- |
| Maven local repository | Downloaded/installed JARs, POMs, plugins | `.m2/repository` |
| Maven Wrapper distribution cache | Maven binary distribution | `.m2/wrapper/dists` hoặc nơi tương đương |
| Project build outputs | Compiled classes, test outputs, JAR trong target | `target/` |
| OS filesystem cache | Disk pages và metadata hot | Do hệ điều hành quản lý |
| CI cache service | Archived/restored folder do CI config chọn | Maven repo cache snapshot |
| Build tool output cache | Task outputs có thể reuse | Chỉ khi có giải pháp/plugin cụ thể |

Khi một nhóm nói “Maven warm build nhanh”, cần hỏi họ **đã warm loại cache nào**. Thí nghiệm A/B của bài tập chỉ đổi **trạng thái Maven local artifact repo**, đồng thời dùng `clean verify` để giữ khối lượng compile/test theo khả năng kiểm soát.

## 22. Lỗi thường gặp và khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Cold build không download gì | Repo không trống, dùng sai `maven.repo.local` | In absolute repo path và kiểm cách gọi Maven |
| Warm vẫn download nhiều | SNAPSHOT/update policy, artifact mới, metadata | Kiểm profiles, `-U`, repo logs |
| `mvn clean` nhưng không “cold” | Clean chỉ dọn project target | Dùng local repo riêng mới |
| `-o` fail dù warm online pass | Chưa cache đủ plugin/dependency/report artifact | Kiểm missing GAV, làm warm đúng goals |
| Benchmark có thời gian cực lớn lần đầu | Wrapper bootstrap, JDK/Maven download | Chạy Maven `-version` trước đo |
| Script báo test count sai | Surefire không chạy đủ, đổi test names/config | Xem TEST XML và Maven exit code |
| Script báo JAR size khác | Project output không ổn định hoặc đã sửa source | Xem POM, commit, jar contents |
| Windows benchmark không chạy | `mvn` không trên PATH, quoting repo path sai | Dùng `mvnw.cmd`, kiểm `mvn -version` |
| Linux benchmark permission denied | `mvnw` thiếu executable bit | Kiểm git mode/permission của Wrapper |
| Maven 401/403/PKIX | Credentials, proxy/TLS/mirror | So settings và repository policy |
| Cold hàng loạt làm nghẽn proxy | N cặp cùng tải plugins từ remote | Giảm N theo policy, dùng test mirror |
| CI cache hit nhưng verify fail | Build logic/tests sai, cache stale | Giữ QA gate độc lập |
| Maven báo thiếu transitive dependency | POM/remote artifact/version không resolve | Xem effective POM và repo logs |
| `-ntp` không hiện progress | Flag cố ý ẩn thanh tiến độ | Không suy ra “không có mạng” |
| Warm > cold | Scheduler/OS cache/SNAPSHOT/check metadata | Đo nhiều cặp, xem logs |
| Profile khác giữa runs | `.mvn/maven.config`, settings hoặc `-P` | So command/effective POM |
| JDK khác giữa runs | JAVA_HOME/runner JRE khác | So `mvn -version` |
| Compile nhanh do bỏ test | Một bên có `-DskipTests` | So flags và Surefire XML |
| Repo nhiều installed artifacts | Local repo không còn là chỉ download cache | Cần isolated cold repo |
| Cache service restore tốn nhiều phút | Cache archive lớn, WAN xa | Đo tổng pipeline time |
| Offline warm pass nhưng cold online fail | Repository outage/network auth | Không coi là so sánh hiệu năng công bằng |
| Multi-module warm build ít modules | `-pl`/`-am` khác nhau | Giữ Reactor selection như nhau |
| Maven plugin bất ngờ đổi version | Không pin plugin hoặc dynamic ranges | Xem effective POM/plugin resolution |
| Thời gian CPU khác elapsed | Dùng `user`/`sys` thay wall-clock | Dùng `perf_counter` / `real` |
| Xóa toàn bộ `.m2` làm hỏng dự án khác | Xóa cache toàn máy | Chỉ dùng/dọn repo thử nghiệm |

## 23. Bài tự kiểm tra

**Câu 1.** Vì sao `mvn clean verify` lần thứ hai không phải cold dependency build?

Vì `clean` dọn build output, không xóa Maven local artifact repository; dependencies/plugins đã tải vẫn được giữ.

**Câu 2.** Nếu lượt warm không dùng `clean` thì kết quả sai ở đâu?

Bạn đồng thời thay local repository state và giữ compiled/test output. Vì vậy phần giảm thời gian có thể do incremental build chứ không phải riêng dependency cache.

**Câu 3.** `-Dmaven.repo.local=...` có buộc Maven dùng một remote repository khác không?

Không. Nó chọn đường dẫn local repository; remote repositories/mirrors còn phụ thuộc POM/settings.

**Câu 4.** Vì sao không chạy `dependency:go-offline` trước cold benchmark?

Goal này tải dependencies/plugins để chuẩn bị cache, làm repo không còn trống trước lượt cold.

**Câu 5.** `-ntp` có nghĩa Maven không dùng mạng không?

Không. Nó chỉ tắt hiển thị transfer progress. `-o` mới là tùy chọn offline.

**Câu 6.** Có thể dùng `-o` ở warm rồi so trực tiếp với cold online không?

Không phải baseline A/B chuẩn vì chính sách network đã thay; offline readiness là thí nghiệm riêng.

**Câu 7.** Nếu cold 60 giây và warm 20 giây, tỷ lệ giảm elapsed trong cặp là bao nhiêu?

Theo công thức `(60-20)/60 × 100 = 66,7%` (làm tròn một chữ số). Đây chỉ là **phép toán minh họa**, không phải số benchmark thực của project mẫu.

**Câu 8.** Vì sao script đo kiểm cả Surefire XML?

Để tránh so thời gian giữa một build đã chạy đủ 4 tests và một build bị skip/fail; workload phải tương đương.

**Câu 9.** Local repo warm có đảm bảo không còn network request không?

Không. SNAPSHOT metadata, updatePolicy, missing artifacts hoặc profiles mới vẫn có thể gây network.

**Câu 10.** Có thể xóa toàn bộ `~/.m2/repository` để lấy số cold “chuẩn” không?

Không nên. Dùng repository riêng mới/trống an toàn và kiểm soát hơn, tránh mất artifacts của các dự án khác.

**Câu 11.** Khi cold nhanh hơn warm, phải làm gì?

Giữ số liệu, lặp cặp samples và xem timing/network/CPU/cache/test consistency thay vì sửa kết quả để phù hợp giả định.

**Câu 12.** CI restore cache Maven có tự đảm bảo artifact phát hành tương thích không?

Không. Vẫn cần compile/test/verification và quản lý artifact provenance, security, immutability.

## 24. Checklist đo và báo cáo hiệu năng

- [ ] Đã định nghĩa cold **Maven local artifact repository** chứ không phải “máy lạnh hoàn toàn”?
- [ ] Thư mục cold repo mới và trống, không dùng repository mặc định của người khác?
- [ ] Warm dùng lại đúng repo đã điền đầy ở cold?
- [ ] JDK, Maven version, profiles, POM, commit, settings và mirror cố định?
- [ ] Maven Wrapper bootstrap được thực hiện ngoài timing (nếu dùng Wrapper)?
- [ ] Cả hai đều `clean verify`, không đổi `-o`, `-U`, `-T`, skip flags?
- [ ] Dependencies và plugins có version cố định theo policy?
- [ ] Đã đo wall-clock bằng cùng một clock/method?
- [ ] Cả hai builds return code 0?
- [ ] Surefire XML cho cùng số tests, failures/errors/skipped đạt QA?
- [ ] Main JAR xuất hiện sau mỗi lượt, không bị đổi project source/POM?
- [ ] Đã lặp ít nhất vài cặp thay vì dựa vào một run?
- [ ] Báo median cold, median warm và paired reduction; lưu N và sự dao động?
- [ ] Có ghi network/mirror/OS/CPU/memory/toolchain để hiểu giới hạn?
- [ ] Snapshot/updatePolicy, plugin metadata và CI cache policy được ghi rõ?
- [ ] Nếu có offline experiment, giữ riêng, không trộn vào cold/warm?
- [ ] Nếu có incremental experiment, giữ riêng, không trộn với repo cache?
- [ ] Không xóa global `.m2`, không làm rò credentials trong logs?
- [ ] Chi phí restore/save CI cache được tính khi đánh giá tổng pipeline?
- [ ] Kết luận ghi rõ giới hạn: local cache đóng góp, không quy toàn bộ chênh lệch cho Maven Resolver?

**Kết luận:** so sánh chính xác Maven dependency-cache performance cần hai lượt **`clean verify` cùng workload**, một lượt dùng local repo mới/trống và lượt sau dùng **chính repo đã được warm**; đo nhiều cặp, kiểm kết quả build/test, dùng external wall-clock và báo trung vị. `mvn clean` không làm local repository lạnh; `-o`, `-U`, incremental compile, Maven Wrapper bootstrap và CI cache restore là những biến khác phải tách riêng. Khi quan sát được dependency download là bottleneck, mới cân nhắc mirror/cache CI; khi không, tập trung vào compile, tests hoặc build configuration.

### Tài liệu chính thức

- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Apache Maven — Local Repositories](https://maven.apache.org/repositories/local.html)
- [Apache Maven — Configuring Apache Maven](https://maven.apache.org/configure.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — CLI Options Reference](https://maven.apache.org/ref/3.9.7/maven-embedder/cli.html)
- [Apache Maven Clean Plugin — Usage](https://maven.apache.org/plugins/maven-clean-plugin/usage.html)
- [Apache Maven Dependency Plugin — dependency:go-offline](https://maven.apache.org/plugins/maven-dependency-plugin/go-offline-mojo.html)
- [Apache Maven — Multiple Modules and Reactor](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven Surefire Plugin — Usage](https://maven.apache.org/surefire/maven-surefire-plugin/usage.html)
