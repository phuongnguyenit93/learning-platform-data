# Thu nhỏ trường hợp lỗi và xác định thay đổi đầu tiên gây hồi quy

Một chương trình Java chạy tốt trên JDK cũ rồi xuất hiện lỗi sau khi nâng cấp **không có nghĩa bản JDK mới chắc chắn có bug**. Trong một đợt migration thực tế, nhóm thường đồng thời nâng Maven/Gradle, dependency, Java agent, container image, database driver hoặc sửa source code. Nếu không tách các thay đổi này, ta dễ chọn sai nguyên nhân và đưa ra một workaround che triệu chứng thay vì sửa lỗi tương thích.

Có hai kỹ thuật quan trọng:

- **Thu nhỏ trường hợp lỗi (*minimal reproducible example*, MRE):** chỉ giữ lại code, dữ liệu và điều kiện tối thiểu mà **cùng một lỗi vẫn xảy ra**.
- **Xác định thay đổi đầu tiên gây hồi quy (*regression localization*):** tìm ranh giới giữa một trạng thái **known good** và một trạng thái **known bad**, sau đó kiểm tra cơ chế nhân quả của thay đổi nghi vấn.

Mục tiêu là tạo một ca lỗi người khác có thể chạy lại, chứng minh một thay đổi cụ thể đã kích hoạt kết quả sai, và biến phát hiện thành regression test. Trong Java Advance Compatibility Migration, đây là cách phân biệt lỗi do JDK, dependency, module access, classloader, serialization, dữ liệu hoặc cấu hình hạ tầng.

## 1. Trước tiên, định nghĩa lỗi bằng hành vi quan sát được

“Java 21 làm ứng dụng lỗi” là một mô tả không đủ. Một báo cáo dùng được cần chỉ rõ:

1. **Đầu vào/thao tác:** request, method, command hoặc fixture nào?
2. **Expected:** kết quả hay invariant nào phải được bảo đảm?
3. **Actual:** exception, response, bytes hoặc metric nào sai?
4. **Môi trường:** JDK feature/update/build, vendor, OS, container, JVM flags.
5. **Artifact:** Git SHA, JAR/container digest, dependency versions.
6. **Tần suất:** 10/10, 3/50 hay chỉ dưới tải đồng thời?
7. **Đối chứng:** lần chạy trên JDK/bản ứng dụng cũ có thực sự tương đương không?

Ví dụ:

> Với artifact checksum H và fixture F, khi gọi `POST /orders` trên JDK 21 build B, ứng dụng trả HTTP 500 cùng `InaccessibleObjectException` trong 5/5 lần. Cùng artifact, fixture và cấu hình tương đương trên JDK 17 build A trả HTTP 201 trong 5/5 lần.

Ví dụ này chưa quy lỗi cho JDK mà chỉ mô tả **điều đã kiểm chứng**.

### 1.1. Failure signature

Một *failure signature* là tập đặc trưng giúp đảm bảo mọi bước thu nhỏ vẫn là cùng bug.

| Trường | Ví dụ |
|---|---|
| Trigger | API request X hoặc test Y |
| Expected | HTTP 201; dữ liệu thỏa invariant |
| Actual | HTTP 500 hoặc output sai |
| Exception chính | `NoSuchMethodError`, `VerifyError`, `InaccessibleObjectException` |
| Vị trí | Class/method/stack frame quan trọng |
| Input | Fixture ID và bytes quan trọng |
| Runtime | JDK, JVM flags, agent |
| Tần suất | 10/10 hoặc 4/100 |
| Artifact | SHA-256 và Git commit |

Khi không có exception, oracle có thể là **kết quả số học sai**, **timestamp lệch**, **SPI provider biến mất**, **GC pause tăng vượt ngưỡng** hoặc **bytes sau serialize không đúng hợp đồng**.

### 1.2. Triệu chứng khác nguyên nhân

~~~text
Triệu chứng: HTTP 500
        |
        v
Lỗi trực tiếp: ServiceConfigurationError
        |
        v
Thiếu provider trong META-INF/services
        |
        v
Cơ chế: Shade task ghi đè file service trùng tên
        |
        v
Thay đổi kích hoạt: commit sửa plugin packaging
~~~

HTTP 500 là biểu hiện bên ngoài; không phải root cause. Tương tự, thấy lỗi lần đầu sau khi nâng JDK chưa chứng minh JDK là nơi sai.

## 2. Chụp bằng chứng trước khi thay đổi môi trường

Đừng vội xóa flags hoặc nâng dependency khi chưa có bản trạng thái gốc. Nếu mỗi lần thử đồng thời thay một loạt yếu tố, dữ liệu điều tra mất khả năng so sánh.

Tạo một *evidence bundle*:

~~~text
repro/
  README.md                 Expected/actual và cách chạy
  environment.txt          JDK/vendor/build, OS, locale/zone
  revision.txt             Git SHA
  artifact.sha256          Hash JAR/container
  runtime-options.txt      JVM flags/agents đã redacted
  dependency-tree.txt      Runtime dependency resolution
  input.bin                Fixture bytes đã tổng hợp
  expected.txt
  actual.txt
  stacktrace.txt
  test-report.xml
~~~

Có thể thu thập JDK/toolchain identity bằng:

~~~bash
java -version
java -XshowSettings:properties -version
mvn -version
# hoặc
gradle --version
~~~

Với HotSpot process còn chạy và có quyền chẩn đoán:

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
~~~

`12345` chỉ là PID minh họa. Không đưa toàn bộ command line, environment, heap dump hoặc logs chứa secrets/customer data vào issue công khai.

### 2.1. JDK chạy Maven khác JDK compile/test

`mvn -version` cho biết JVM chạy Maven, **không nhất thiết là `javac` được Compiler Plugin dùng hoặc test JVM được Surefire fork**. Nếu dùng toolchains, cần xác minh cả compiler, test và runtime thực tế.

Đối với một lỗi compile, ghi compiler vendor/version và `--release`. Với lỗi runtime, ghi JDK của service process/container. Với lỗi test, in `java.version` trong test JVM để tránh suy đoán.

### 2.2. So sánh cùng binary

~~~text
Artifact checksum H
       |
       +-- JDK 17 --> PASS
       |
       +-- JDK 21 --> FAIL
~~~

Cùng một artifact giúp cô lập khác biệt runtime. Tuy nhiên, artifact phải chứa bytecode chạy được trên cả hai JDK; dùng class file Java 21 trên JDK 17 sẽ ném `UnsupportedClassVersionError` một cách hợp lý, không phải một regression bí ẩn.

Nếu bug nằm trong compiler/build, thay vì cùng artifact phải so sánh **cùng source và cùng dependency/flags** trên từng compiler.

## 3. Hai nhóm yếu tố cần thu nhỏ

**Nhóm chương trình/dữ liệu:**

- Số controller, service và method.
- Request payload, file bytes, SQL rows.
- Dependency, annotation processors và plugins.
- Số threads, retry, scheduler.
- Đường gọi thực sự gây lỗi.

**Nhóm môi trường:**

| Trục | Giá trị cần cố định hoặc thử |
|---|---|
| JDK | Feature/update/build/vendor |
| Compiler | `javac`, `--release`, preview flags |
| Build | Maven/Gradle/plugin versions |
| Dependencies | Compile/runtime graph |
| Runtime | JVM options, GC, Java/native agents |
| Packaging | Classpath, module path, shade, nested JAR |
| OS/container | Base image, CPU/RAM, architecture |
| i18n | Locale, charset, timezone, TZDB |
| Data | Schema/version, serialized bytes |
| External services | TLS, database driver, broker |

Cách làm có ích thường là **thay đúng một trục trong mỗi thí nghiệm**. Nhưng có bug chỉ xuất hiện khi nhiều yếu tố tương tác; khi đó không được ép mọi lỗi về một thủ phạm duy nhất.

## 4. MRE là ca lỗi nhỏ nhưng trung thực

Một MRE tốt có:

- Hướng dẫn build/run ngắn và rõ.
- Input hoặc data fixture có thể chia sẻ.
- Cấu hình/JDK/dependencies được cố định.
- Expected/actual và điều kiện PASS/FAIL.
- Ít thành phần không cần thiết.
- Không thay đổi điều kiện gây ra bug.

MRE **không nhất thiết là một file Java**. Lỗi `ServiceLoader` có thể cần JAR đã shade; lỗi JNI/JVMTI cần native agent; lỗi concurrency cần nhiều threads; lỗi database isolation có thể cần database container nhỏ.

### 4.1. Tránh thu nhỏ làm mất nguyên nhân

Nếu source file lỗi chứa bytes Windows-1252, việc mở rồi lưu thành UTF-8 trong editor có thể làm lỗi biến mất. Nếu packaging làm mất `META-INF/services`, chạy test từ `target/classes` thay cho shaded JAR cũng có thể làm triệu chứng biến mất.

Khi mỗi bước giảm bớt code, phải tự hỏi: **Lỗi có còn đúng failure signature không?** Nếu không, phục hồi điều kiện vừa xóa rồi kiểm tra tiếp.

### 4.2. Quy trình lặp

~~~text
Ứng dụng lớn bị lỗi
       |
       v
Viết reproduction command + oracle
       |
       v
Bỏ một nhóm code/data/config
       |
       v
Chạy lại trong môi trường cố định
       |
       +-- Cùng FAIL: giữ bản nhỏ hơn
       |
       +-- PASS: phục hồi phần vừa bỏ
       |
       +-- UNKNOWN: lặp/điều tra test
       |
       v
Tiếp tục đến MRE phù hợp
~~~

Gợi ý thứ tự: giảm input → bỏ UI/network không liên quan → giảm business layers → giảm dependencies → giảm JVM flags/agents → thu nhỏ packaging hoặc thread count nếu bug vẫn tái hiện. Đây là một hướng đi, không phải thứ tự bắt buộc.

## 5. Thiết kế oracle PASS / FAIL / SKIP / UNKNOWN

Một test dùng cho MRE hoặc bisection phải phân biệt:

| Kết quả | Ý nghĩa |
|---|---|
| **PASS** | Test chạy hợp lệ và hành vi đúng |
| **FAIL** | Test chạy hợp lệ và lỗi đúng failure signature |
| **SKIP** | Revision/môi trường không kiểm tra hợp lệ |
| **UNKNOWN** | Kết quả không đủ chắc chắn hoặc flaky |
| **ERROR** | Harness/hạ tầng hỏng không liên quan bug |

Một Maven build fail do không tải được dependency không đủ để đánh dấu **BAD** cho commit đang tìm. Một test được thêm sau commit good nhưng không tồn tại ở commit cũ cũng là **harness problem**, không phải một bug ứng dụng.

Oracle tốt kiểm tra hợp đồng nghiệp vụ hoặc exception cần tìm. Oracle chỉ dựa vào một dòng log có thể thất bại khi framework đổi wording mà ứng dụng vẫn đúng.

## 6. Delta debugging: loại bớt điều kiện có hệ thống

*Delta debugging* thử các tập con của input/config để giữ phần nhỏ còn gây lỗi. Giả sử:

~~~text
S = {
  flag A, flag B, flag C,
  dependency X, dependency Y,
  record 1...100
}
~~~

Một thuật toán `ddmin` chia S thành các nhóm, thử từng nhóm và phần bù. Nếu một tập con vẫn FAIL, ta tiếp tục chia nhỏ tập đó; nếu không, tăng số nhóm để tìm một phép loại bỏ nhỏ hơn.

Pseudocode:

~~~text
function ddmin(config):
    n = 2

    while size(config) >= 2:
        parts = split(config, n)
        reduced = false

        for part in parts:
            if test(part) == FAIL:
                config = part
                n = max(2, n - 1)
                reduced = true
                break

        if reduced:
            continue

        for part in parts:
            candidate = config - part
            if test(candidate) == FAIL:
                config = candidate
                n = max(2, n - 1)
                reduced = true
                break

        if reduced:
            continue

        if n >= size(config):
            break

        n = min(size(config), n * 2)

    return config
~~~

### 6.1. Những giới hạn quan trọng

Một tập con có thể **không hợp lệ**: dependency Y cần API X, JVM flag chỉ có tác dụng với một GC khác, fixture cần schema revision cụ thể, hoặc race condition cần ít nhất hai threads. Test không build được trong trường hợp này không có nghĩa nó PASS hay FAIL.

Một lỗi cũng có thể do tương tác:

~~~text
JDK 21 + agent A --> FAIL
JDK 21 không agent --> PASS
JDK 17 + agent A --> PASS
~~~

Không thể loại riêng JDK hoặc agent mà vẫn giữ bug. Kết quả 1-minimal không phải chứng minh một nguyên nhân duy nhất; nó là tập điều kiện nhỏ hữu ích để giải thích/kiểm thử.

## 7. Ví dụ hoàn chỉnh: `NoSuchMethodError` do runtime dependency cũ

Giả sử app được compile với API v2 nhưng runtime nạp API v1. Lỗi xảy ra khi bytecode gọi method v2 không tồn tại trong class của v1.

### 7.1. API v1

File `src/api-v1/com/example/api/Feature.java`:

~~~java
package com.example.api;

public final class Feature {
    private Feature() {}

    public static String legacyName() {
        return "old";
    }
}
~~~

### 7.2. API v2

File `src/api-v2/com/example/api/Feature.java`:

~~~java
package com.example.api;

public final class Feature {
    private Feature() {}

    public static String legacyName() {
        return "new";
    }

    public static String versionName() {
        return "v2";
    }
}
~~~

### 7.3. Caller

File `src/app/Repro.java`:

~~~java
import com.example.api.Feature;

public final class Repro {
    public static void main(String[] args) {
        System.out.println(Feature.versionName());
    }
}
~~~

### 7.4. Compile với dependency mới

Ví dụ trên Unix shell có JDK hỗ trợ `jar --create`:

~~~bash
mkdir -p build/api-v1 build/api-v2 build/app lib

javac -d build/api-v1 \
  src/api-v1/com/example/api/Feature.java
jar --create --file lib/api-v1.jar -C build/api-v1 .

javac -d build/api-v2 \
  src/api-v2/com/example/api/Feature.java
jar --create --file lib/api-v2.jar -C build/api-v2 .

javac -cp lib/api-v2.jar -d build/app \
  src/app/Repro.java
~~~

### 7.5. Hai lần chạy chỉ khác runtime JAR

~~~bash
# GOOD
java -cp "build/app:lib/api-v2.jar" Repro

# BAD
java -cp "build/app:lib/api-v1.jar" Repro
~~~

Trên Windows classpath separator thường là `;`. Lần GOOD in `v2`; lần BAD có thể ném `NoSuchMethodError`. Tất cả source/caller bytecode và JDK đều giữ nguyên, chỉ runtime dependency đổi.

Điểm chứng minh: bug như vậy **không nhất thiết do JDK nâng cấp**; một dependency mismatch được đưa vào deployment cũng đủ tạo ra lỗi trong cùng thời điểm migration.

### 7.6. Kiểm tra bytecode và signatures

~~~bash
javap -classpath lib/api-v1.jar \
  -public com.example.api.Feature

javap -classpath lib/api-v2.jar \
  -public com.example.api.Feature

javap -classpath build/app -c Repro
~~~

`javap` cho thấy `Feature.versionName()` chỉ xuất hiện trong v2 và caller có call site tới method đó.

Trong ứng dụng thực tế, hãy xác định **class nào được nạp từ JAR nào** qua classpath/runtime class loading log, không chỉ nhìn compile dependency tree.

## 8. Ví dụ phụ thuộc default charset khi nâng JDK

Code tối giản:

~~~java
import java.nio.charset.Charset;

public final class CharsetRepro {
    public static void main(String[] args) {
        byte[] input = {(byte) 0xE9};
        String value = new String(input);

        System.out.println(Charset.defaultCharset());
        value.codePoints().forEach(cp ->
            System.out.printf("U+%04X%n", cp));
    }
}
~~~

Byte `0xE9` có thể biểu diễn `é` trong Windows-1252 hoặc ISO-8859-1, nhưng **không phải một chuỗi UTF-8 hợp lệ độc lập**. `new String(input)` dùng default charset theo API, nên kết quả khác nhau khi default charset đổi.

Từ **JDK 18**, JEP 400 đưa default charset của các Java APIs trong phạm vi JEP sang UTF-8. Nếu JDK cũ chạy trên hệ có default Windows-1252 và JDK mới dùng UTF-8, cùng bytes có thể giải mã khác. Nếu JDK cũ vốn đã mặc định UTF-8, ví dụ này **không nhất thiết tái hiện khác biệt**.

### 8.1. Thu nhỏ đúng

1. Lưu nguyên input bytes, không copy qua editor có thể thay encoding.
2. Ghi `Charset.defaultCharset()` ở cả hai JVM.
3. Bỏ database/API layer nhưng giữ `new String(input)`.
4. In code points và so sánh.
5. Xác nhận encoding thật từ hợp đồng dữ liệu.
6. Sửa bằng `Charset` tường minh.

Ví dụ nếu dữ liệu nguồn quy định ISO-8859-1:

~~~java
import java.nio.charset.StandardCharsets;

String decoded =
    new String(input, StandardCharsets.ISO_8859_1);
~~~

Cơ chế gây lỗi là **giả định default charset**, còn thay đổi JDK là trigger. Đây là khác biệt giữa nguyên nhân thiết kế và thay đổi đầu tiên làm sai kết quả.

## 9. Chọn known-good/known-bad trước khi tìm kiếm nhị phân

Để tìm lỗi trong Git history, cần một commit PASS và một commit FAIL **trên cùng JDK/môi trường**. Nếu good chạy trên Java 17 còn bad trên Java 21, cả source và runtime đổi; không thể suy ra commit nào gây lỗi từ hai điểm này.

### 9.1. Ma trận 2×2

| | JDK 17 | JDK 21 |
|---|---|---|
| App A cũ | PASS | PASS |
| App B mới | PASS | FAIL |

Bảng này gợi ý **tương tác giữa app B và JDK 21**. Nếu A và B đều fail trên JDK 21 với cùng artifact/conditions, nên ưu tiên kiểm tra runtime/JVM options/agent. Nếu chỉ B fail trên cả hai JDK, source/dependency changes đáng nghi hơn.

### 9.2. Những trục có thể bisect

- Git source commits.
- Dependency/plugin versions.
- JDK feature releases hoặc patch builds.
- Container images.
- JVM flags.
- APM/JVMTI agent versions.
- Schema migration revisions.
- Cấu hình framework.

Không cần mặc định `git bisect` là bước đầu tiên; hãy chọn trục mà bằng chứng cho thấy đã thay đổi.

## 10. `git bisect` tìm commit đầu tiên làm test chuyển trạng thái

Giả sử HEAD đã được xác nhận BAD còn tag `v2.0.0` là GOOD trong môi trường có cùng JDK/fixture.

~~~bash
git bisect start
git bisect bad HEAD
git bisect good v2.0.0
~~~

Git checkout một commit trung gian. Chạy oracle; nếu PASS:

~~~bash
git bisect good
~~~

Nếu FAIL đúng signature:

~~~bash
git bisect bad
~~~

Lặp đến khi tìm được commit nghi vấn, sau đó:

~~~bash
git bisect log
git bisect reset
~~~

**Lưu hoặc cô lập thay đổi đang dở trước khi bisect.** Git sẽ checkout những commits khác nhau; dùng worktree riêng nếu cần để không ảnh hưởng nhánh làm việc hiện tại.

### 10.1. Vì sao nhanh?

Trong phạm vi khoảng 128 commits và một oracle ổn định, bisection lý tưởng cần khoảng 7 phép thử trung gian thay vì thử tuần tự gần 128 commits. Thực tế có thể tốn hơn khi merge history phức tạp, có commits không build được hoặc test flaky.

### 10.2. Tự động với `git bisect run`

~~~bash
git bisect start
git bisect bad HEAD
git bisect good v2.0.0
git bisect run ./scripts/bisect-regression.sh
git bisect log
git bisect reset
~~~

Quy ước exit code quan trọng:

| Exit code từ script | `git bisect` hiểu |
|---|---|
| `0` | GOOD |
| `1..127` trừ `125` | BAD |
| `125` | SKIP, không đánh giá hợp lệ |
| `128` trở lên | Không phải kết quả good/bad bình thường, có thể làm quá trình dừng |

Một script mẫu:

~~~sh
#!/bin/sh

# JAVA_HOME, dependency repository và fixture đã cố định.

mvn -q -DskipTests package
build_rc=$?

if [ "$build_rc" -ne 0 ]; then
    exit 125
fi

mvn -q -Dtest=CompatibilityRegressionTest test
test_rc=$?

if [ "$test_rc" -eq 0 ]; then
    exit 0
fi

# Chỉ đánh BAD nếu test failure đúng bug đang tìm.
# Nếu Maven lỗi hạ tầng/test thiếu, cần phân loại SKIP.
exit 1
~~~

Khuôn khổ này cần bổ sung logic phân biệt test assertion và lỗi hạ tầng. Nếu `CompatibilityRegressionTest` chỉ được thêm sau mốc good, chạy script trên commit cũ có thể báo test không tồn tại. Khi ấy dùng harness **nằm ngoài worktree được bisect**, hoặc đánh dấu các revisions không kiểm thử hợp lệ.

### 10.3. Commit đầu tiên FAIL khác root cause

Ví dụ:

~~~text
Commit A: code ngầm dùng default locale
Commit B: thêm dữ liệu tiếng Thổ Nhĩ Kỳ
Commit C: đổi default locale của container
~~~

Test có thể chỉ fail từ C, nhưng lỗi thiết kế đã tồn tại ở A. Kết quả bisect nói “C là điểm chuyển PASS → FAIL trong phạm vi thử nghiệm”, chưa đủ để khẳng định C là toàn bộ nguyên nhân.

### 10.4. Bisection không luôn đơn điệu

~~~text
GOOD -> BAD -> GOOD (revert) -> BAD (bug tái xuất hiện)
~~~

Khi có revert/merge hoặc nhiều nguyên nhân độc lập, mô hình một ranh giới có thể không phù hợp. Cần xem commit graph, thử các commits lân cận và cân nhắc phạm vi ancestor của release đang điều tra.

## 11. Thu hẹp JDK release/build

Nếu cùng artifact PASS trên JDK 17 nhưng FAIL trên JDK 21, thử các JDK trung gian:

~~~text
JDK 17: PASS
JDK 18: ?
JDK 19: ?
JDK 20: ?
JDK 21: FAIL
~~~

Nếu JDK 18 là bản đầu tiên FAIL trong ma trận, có thể nghiên cứu JDK 18 release notes và JEPs, ví dụ default charset theo JEP 400. Nhưng đó vẫn là **earliest tested failing feature release**, chưa phải một OpenJDK source commit cụ thể.

### 11.1. Kiểm tra update builds và vendor

~~~text
21.0.2: PASS
21.0.3: PASS
21.0.4: FAIL
21.0.5: FAIL
~~~

Một bug có thể được backport hoặc fix khác nhau theo vendor/update branch. Ghi đủ vendor/build number. Tránh dùng “Java 21” như nhãn duy nhất khi so sánh patch updates.

### 11.2. Điều kiện khiến version bisection không hợp lệ

- Bytecode Java 21 không chạy được trên Java 17.
- JVM flags chỉ tồn tại ở bản mới.
- Java agent không hỗ trợ bản cũ.
- Container base image/OS cũng đổi.
- Dependency yêu cầu Java version cao hơn.
- TLS truststore, timezone data hoặc locale thay đổi độc lập.

Đánh dấu SKIP hoặc thiết kế lại phép so sánh, không ép mọi startup failure thành cùng regression.

### 11.3. Muốn xác định source commit của JDK cần bước khác

Thử JDK releases chỉ thu hẹp version range. Muốn xác định chính xác một commit OpenJDK có thể cần tự build những revisions JDK, cố định công cụ compiler và chạy MRE trên từng build. Đây là điều tra nâng cao; báo cáo ứng dụng nên trung thực về mức đã xác định.

## 12. Phân tích binary/classpath và toolchain theo mục đích

Khi gặp `NoSuchMethodError`, `NoClassDefFoundError`, `ClassCastException` hoặc `UnsupportedClassVersionError`, xác minh class thực sự được nạp từ đâu.

Với Maven:

~~~bash
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency some-library \
  --configuration runtimeClasspath
~~~

Với HotSpot Unified Logging:

~~~bash
java -Xlog:class+load=info \
  -jar app.jar
~~~

Đọc classloading source/module/class loader, đặc biệt khi artifact đã shade/repackage.

### 12.1. `javap` kiểm tra signature và bytecode level

~~~bash
javap -verbose -classpath target/classes \
  com.example.Service
~~~

Class-file major 61 tương ứng Java 17, major 65 tương ứng Java 21. Với một runtime `NoSuchMethodError`, xem method descriptors trên JAR đang chạy, không chỉ source code hiện tại.

### 12.2. `jdeps` chỉ phát hiện quan hệ tĩnh

~~~bash
jdeps --summary app.jar
jdeps --jdk-internals app.jar
~~~

`jdeps` hữu ích để tìm dependency và JDK internals, nhưng không đảm bảo tìm những class nạp qua reflection, `ServiceLoader` hoặc tên chuỗi trong configuration. Nếu bug liên quan SPI/plugin, phải giữ service metadata trong MRE và chạy artifact cuối.

### 12.3. Compiler và test JVM là hai trục

Với Maven Toolchains, compiler có thể là JDK 21 với `--release 17` trong khi Surefire fork JVM 17. Build xanh trên Maven JVM 21 không chứng minh compatibility Java 17. Ghi identity mỗi process và kiểm tra target bytecode/dependencies.

## 13. JVM flags, agents và native crash

Một lỗi sau nâng JDK có thể do `-XX` flag bị loại bỏ, Java agent transformer không hiểu class file mới, module access thay đổi hoặc native JVMTI agent không tương thích.

Ví dụ startup có:

~~~text
-Xms2g
-Xmx2g
-XX:+UseG1GC
-Xlog:gc*
--add-opens=java.base/java.lang=ALL-UNNAMED
-javaagent:/opt/agents/apm.jar
-agentpath:/opt/profiler/libprofiler.so
~~~

Thu nhỏ theo nhóm:

1. App không agent bên thứ ba.
2. App chỉ có APM agent.
3. App chỉ có native profiler.
4. App có cả hai.
5. Chọn đúng JDK/build và workload.
6. Sau đó giảm những tuning flags không cần thiết.

Nếu một JVM flag đã removed gây:

~~~text
Unrecognized VM option ...
Could not create the Java Virtual Machine.
~~~

MRE đôi khi chỉ cần `java <flag thực tế> -version`. Nhưng không dùng một flag giả định để khẳng định bug của JDK đích.

Nếu JVM crash native và có `hs_err_pid*.log`, xem JDK vendor/build, `problematic frame`, native library, agent path, OS/architecture và stack. Chạy thử trong môi trường cô lập, không liên tục làm crash production.

## 14. Khi bug là flaky, race condition hoặc timeout

Một lần PASS không đủ để đánh dấu known good nếu lỗi xuất hiện theo xác suất:

~~~text
JDK 17: 0/50 failures
JDK 21: 12/50 failures
~~~

Bảng cho thấy tần suất khác nhau, chưa chứng minh bản cũ **không bao giờ** gặp lỗi.

### 14.1. Giữ điều kiện concurrency

Không vô tình xóa bug bằng cách:

- Giảm số thread xuống một.
- Thêm lock trong test harness.
- Chuyển asynchronous task thành synchronous call.
- Thêm logging nặng làm đổi scheduling.
- Giảm workload xuống dưới ngưỡng xuất hiện lỗi.

MRE cho race vẫn có thể cần thread pool và stress loop; ghi seed, iterations, CPU limit và các flags liên quan.

### 14.2. Thiết kế chính sách retry

Khi bisect một lỗi flaky:

- BAD khi có đúng failure signature và đủ bằng chứng.
- GOOD khi đã chạy số lần theo ngưỡng tự đặt, không lỗi.
- UNKNOWN khi vẫn chưa chắc.
- SKIP khi revision không thể test.

Không gán UNKNOWN thành GOOD chỉ vì công cụ bisect cần một câu trả lời ngay.

### 14.3. Performance regression cần benchmark có cấu trúc

Một timeout đơn lẻ trên CI không đủ. Cần cùng dataset, concurrency, CPU/RAM, warmup, sampling settings và nhiều lượt đo. Xem p50/p95/p99, throughput, allocation, GC, RSS, CPU throttling.

Nếu thêm JFR/profiler, kiểm tra overhead của công cụ quan sát; có thể đo so sánh **không agent** rồi mới bật agent.

## 15. Database, broker và network có thể không bỏ được khỏi MRE

Một lỗi chỉ xuất hiện với transaction isolation của PostgreSQL có thể biến mất khi thay bằng H2. Điều đó không chứng minh database không liên quan; fake database có thể không giữ cùng semantics.

MRE vẫn có thể dùng:

- Database container nhỏ với schema và vài dòng dữ liệu.
- Test broker với một event format/ordering cụ thể.
- TLS server kiểm thử với policy/certificate fixture.
- Một data file theo đúng legacy charset.
- Một shaded JAR chứa `META-INF/services` thực tế.

### 15.1. Dùng dữ liệu tổng hợp nhưng giữ trigger

Không gửi production customer data, credentials, keys hoặc full heap dump cho vendor. Nếu bug nằm ở tên tiếng Việt dạng Unicode tổ hợp, thay bằng một tên tổng hợp **có cùng đặc tính code points**, không thay bằng ASCII rồi làm lỗi biến mất.

### 15.2. Rollback có thể không còn an toàn

Nếu phiên bản mới đã ghi database/event format mới, quay về JAR cũ không đồng nghĩa rollback dữ liệu. Khi tìm first bad commit, vẫn cần kiểm tra binary cũ đọc/ghi được dữ liệu do bản mới tạo trước khi áp dụng rollback production.

## 16. Thí nghiệm đối chứng để xác nhận nguyên nhân

Sau khi tìm commit/version nghi vấn, thiết kế phép thử có khả năng bác bỏ giả thuyết.

Ví dụ giả thuyết:

> Runtime dùng API JAR cũ không có method mà client bytecode gọi.

Bằng chứng:

1. Giữ cùng JDK/caller bytecode.
2. Runtime dependency v1 → FAIL.
3. Runtime dependency v2 → PASS.
4. `javap` cho thấy method chỉ có ở v2.
5. Class-loading log xác nhận source JAR.
6. Fix dependency graph của artifact cuối → PASS.

Đây là bằng chứng mạnh hơn một commit hash đơn lẻ.

### 16.1. A/B/A

Trong môi trường không có tác động dữ liệu không đảo được:

~~~text
A: cấu hình cũ           PASS
B: chỉ đổi yếu tố nghi ngờ FAIL
A: khôi phục cấu hình cũ PASS
~~~

Kết quả lặp lại giúp củng cố quan hệ nhân quả. Nhưng với database migration/side effects, phải dùng môi trường cô lập và snapshot có thể khôi phục; không tùy tiện làm A/B/A trên production.

### 16.2. Phân biệt bốn khái niệm

- **First bad transition:** thay đổi đầu tiên mà oracle chuyển PASS → FAIL trong phạm vi thử.
- **Trigger:** điều kiện khiến lỗi lộ ra.
- **Latent defect:** giả định sai đã tồn tại nhưng chưa bị kích hoạt.
- **Root cause/fix:** cơ chế và sửa đổi loại bỏ sai sót.

Ví dụ `--add-opens` có thể giảm `InaccessibleObjectException`, nhưng nếu thư viện phụ thuộc JDK internals đã bị đóng, fix bền vững có thể là nâng framework/dùng API chính thức. Workaround không mặc nhiên là giải pháp lâu dài.

## 17. Biến MRE thành test ngăn tái phát

| Nguyên nhân | Regression test phù hợp |
|---|---|
| API runtime mismatch | Binary compatibility/classpath test |
| JPMS reflection | Test đúng JDK với module access |
| Charset phụ thuộc mặc định | Byte fixture + explicit charset |
| DST/timezone | `Clock.fixed`, `ZoneRules`, fixtures |
| `ServiceLoader` sau shade | Black-box test trên JAR cuối |
| Java agent không tương thích | Integration test có agent/JDK |
| Race condition | Stress/concurrency harness |
| Performance regression | Benchmark ổn định theo SLO |
| Schema migration | Integration test với data cũ/mới |

Ví dụ JUnit 5 cho dữ liệu có hợp đồng ISO-8859-1:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class EncodingRegressionTest {
    @Test
    void legacyByteUsesDeclaredCharset() {
        byte[] input = {(byte) 0xE9};

        String decoded = new String(
            input, StandardCharsets.ISO_8859_1);

        assertEquals("é", decoded);
    }
}
~~~

Nếu source thực tế không phải ISO-8859-1, thay bằng charset được tài liệu dữ liệu quy định. Test trên không phụ thuộc default charset, nên ít bị sai khi JDK/OS thay đổi.

**Diagnostic MRE** có thể chứa scripts/fixtures/logs để giải thích bug; **regression test** nên ngắn, ổn định và kiểm tra invariant. Có thể giữ cả hai với mục đích riêng.

## 18. Quy trình chẩn đoán end-to-end

### Giai đoạn A: Xác nhận

1. Ghi expected/actual, failure signature, số lần tái hiện.
2. Thu JDK/build/toolchain/flags/agents, artifact hash.
3. Lưu fixture thực sự gây lỗi.
4. Xác định known good/bad có thể so sánh.

### Giai đoạn B: Cô lập

1. Cùng JAR trên JDK nguồn/đích nếu có thể.
2. Cùng JDK với app/dependency versions khác.
3. Kiểm tra container/OS/environment khác biệt.
4. Bật/tắt từng agent trong môi trường test.
5. Kiểm tra runtime classpath và packaging metadata.

### Giai đoạn C: Thu nhỏ

1. Giảm input.
2. Bỏ business layers không tham gia.
3. Giữ method/class và dependencies tối thiểu.
4. Bảo toàn charset bytes/module layout/concurrency nếu liên quan.
5. Viết reproduction command và oracle.

### Giai đoạn D: Xác định điểm chuyển

1. Nếu do source: dùng `git bisect` với test ổn định.
2. Nếu do JDK: thử feature/update builds cùng binary.
3. Nếu do dependency: so sánh các versions đã pin.
4. Nếu do config/container: đổi một revision mỗi lần.
5. Nếu flaky: lặp, ghi xác suất và giữ UNKNOWN khi cần.

### Giai đoạn E: Chứng minh và sửa

1. Đọc diff của thay đổi nghi vấn.
2. Xây dựng giả thuyết cơ chế có thể kiểm tra.
3. Thử A/B và đối chiếu logs, `javap`, bytes, profiler.
4. Sửa root cause.
5. Test fix ở JDK nguồn/đích và các đường nghiệp vụ liên quan.
6. Chuyển MRE thành regression test.

### Giai đoạn F: Chuyển giao

Báo cáo cả điểm good/bad, những thử nghiệm chưa kết luận, nguyên nhân đã chứng minh đến đâu và rủi ro rollback. Không viết “JDK gây lỗi” nếu chỉ biết nó là bản đầu tiên mà bug xuất hiện.

## 19. Mẫu báo cáo cho nhóm/vender

~~~text
Title: [Java migration] <failure signature>

Expected:
Actual:
Reproduction rate:

Application Git SHA:
Artifact checksum:
JDK vendor/feature/update/build:
OS/architecture/container digest:
Maven/Gradle/plugin versions:
JVM flags/agents:
Runtime dependency/classpath/module path:
Locale/charset/zone if relevant:

Fixture:
Build command:
Run command:
Expected output:
Actual output:

Last known good:
Earliest tested bad:
Bisect result:
Skipped/unknown revisions:

Trigger:
Root-cause hypothesis:
Controlled A/B evidence:
Temporary workaround:
Permanent fix:
Regression test:
Supported JDK matrix:
Rollback risks:
~~~

Đính kèm logs đã redacted hoặc synthetic fixture, không đính kèm production secrets, customer data hoặc native heap/profile dumps chưa được phép chia sẻ.

## 20. Những sai lầm thường gặp

**“Lỗi xuất hiện sau JDK upgrade nên JDK là nguyên nhân.”** Không: source, agent, library hoặc dữ liệu có thể phụ thuộc một hành vi cũ.

**“MRE phải không có dependencies.”** Không nếu chính dependency hoặc packaging là một phần gây lỗi.

**“Xóa mọi JVM flag giúp thu nhỏ.”** Có thể xóa cả điều kiện cần, làm bug biến mất mà không hiểu nguyên nhân.

**“Một lần PASS đủ để biết good.”** Không với race/flaky tests.

**“Build không được ở một commit nghĩa là commit bad.”** Có thể cần SKIP hoặc harness khác.

**“`git bisect` cho root cause.”** Nó cho điểm chuyển theo oracle/history, cần thí nghiệm đối chứng để giải thích.

**“Nâng tất cả dependencies để thử sửa.”** Điều này tạo nhiều biến số và làm mất baseline.

**“`jdeps` không thấy class nên không cần nó.”** Reflection/SPI và config có thể nạp class động.

**“Chỉ cần test class files, không cần artifact cuối.”** Sai với shade, manifest, service metadata, nested JAR và module path.

**“Không thấy exception thì không có regression.”** Wrong result, charset, DST hoặc latency có thể sai âm thầm.

**“Rollback source commit là đủ.”** Không nếu release mới đã ghi dữ liệu/event không tương thích hoặc tạo external side effects.

## 21. Checklist

- [ ] Có expected/actual và failure signature.
- [ ] Có tần suất hoặc số lần tái hiện rõ ràng.
- [ ] Có JDK vendor/update/build của process thật.
- [ ] Có artifact hash, Git SHA, dependency versions và JVM flags.
- [ ] Có fixture đúng bytes và được phép chia sẻ.
- [ ] Có known-good và known-bad trong điều kiện tương đương.
- [ ] Đã thử cùng artifact trên nhiều JDK khi target cho phép.
- [ ] Đã cô lập source/dependency/JDK/container/config.
- [ ] Oracle phân biệt PASS, FAIL, SKIP, UNKNOWN và ERROR.
- [ ] MRE giữ đúng trigger và failure signature.
- [ ] Đã cân nhắc interdependency và tương tác giữa các yếu tố.
- [ ] Đã kiểm tra artifact cuối nếu có packaging/classloader.
- [ ] Đã kiểm tra `javap`, `jdeps` hoặc dependency tree khi phù hợp.
- [ ] Dùng `git bisect` với oracle ổn định, không coi build fail là bad.
- [ ] Đã thu hẹp JDK update/build khi lỗi runtime-specific.
- [ ] Đã xác minh thay đổi nghi vấn bằng A/B.
- [ ] Đã phân biệt trigger, latent defect, first bad và root cause.
- [ ] Đã viết regression test ngăn tái phát.
- [ ] Đã chạy test fix trên JDK/runtime còn hỗ trợ.
- [ ] Đã xét dữ liệu/side effects trước quyết định rollback.
- [ ] Đã redacted secrets trong báo cáo.

## 22. Tài liệu kỹ thuật

- [Git – git bisect](https://git-scm.com/docs/git-bisect): tìm commit, `bisect run`, exit codes và skip.
- [OpenJDK Bug System](https://bugs.openjdk.org/): tra cứu và gửi báo cáo lỗi JDK có MRE.
- [JEP 400 – UTF-8 by Default](https://openjdk.org/jeps/400): ví dụ default charset thay đổi.
- [Java javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): method descriptors và bytecode.
- [Java jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): dependency tĩnh và JDK internals.
- [Java jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): JVM diagnostics.
- [Maven Dependency Plugin dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).
- [Gradle – Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).

Khi áp dụng, đối chiếu command syntax và support matrix của đúng JDK, Git, Maven/Gradle, plugin và OS đang chạy.

## 23. Kết luận

Thu nhỏ trường hợp lỗi không phải thao tác xóa code cho ngắn mà là **giữ đúng cơ chế sai trong một phép thử nhỏ, độc lập và có thể lặp lại**. Xác định thay đổi đầu tiên gây hồi quy đòi một ranh giới known good/known bad đáng tin, kiểm soát các trục thay đổi và dùng bisection phù hợp với source, JDK, dependency hoặc cấu hình.

Điểm chuyển đầu tiên là đầu mối điều tra, **không tự chứng minh root cause**. Sau khi định vị, cần phân tích cơ chế, thử đối chứng A/B, sửa giả định sai, kiểm thử trên các JDK còn hỗ trợ và giữ regression test. Cách làm này giúp Java Advance Compatibility Migration tránh những rollback hoặc workaround theo cảm tính và đưa ra kết luận kỹ thuật có thể xác minh.
