# Định dạng tự động và tách task kiểm tra với task sửa mã trong Gradle

## 1. Tổng quan: kiểm tra mã không đồng nghĩa sửa mã

Trong một dự án Java, cả nhóm thường thống nhất cách đặt dấu cách, indentation, sắp xếp imports, xuống dòng, dấu ngoặc, newline cuối file và license headers. Có hai nhu cầu khác nhau:

- **Kiểm tra định dạng (format check):** tính dạng chuẩn của file rồi so với nội dung hiện tại. Khi có sai khác, task báo lỗi và danh sách file/đoạn cần sửa, nhưng **không ghi đè source**.
- **Tự động định dạng (format apply/fix):** chủ động sửa bytes của các source files thuộc phạm vi cấu hình để tuân theo formatter.
- **Kiểm thử/biên dịch:** xác nhận mã hợp lệ và hành vi đúng. Một file có thể biên dịch được nhưng format sai; một file đẹp có thể chứa bug.
- **Static analysis/lint:** kiểm tra những rules chất lượng riêng, không phải mọi lỗi đều có auto-fix.

Với Gradle, plugin **Spotless** tạo hai task có ý nghĩa minh bạch:

~~~bash
./gradlew spotlessCheck
./gradlew spotlessApply
~~~

`spotlessCheck` là **verification**. `spotlessApply` là **mutation**. Trong luồng làm việc an toàn, CI chạy `spotlessCheck` để xác minh **chính commit được gửi lên**, còn developer chủ động chạy `spotlessApply` rồi review và commit thay đổi.

~~~text
Developer local                       CI / Pull request
---------------------                 ----------------------
sửa Java source                      checkout đúng commit
       |                                     |
       v                                     v
./gradlew spotlessApply             ./gradlew spotlessCheck
       |                                     |
       v                              +------+------+
git diff / review                     |             |
       |                            PASS           FAIL
       v                              |             |
commit source                        build/test    Reject, không sửa source
       |
       v
./gradlew spotlessCheck
~~~

Nếu CI chạy `spotlessApply` trước `spotlessCheck`, commit ban đầu có thể chưa đúng style nhưng CI vẫn PASS vì code đã bị **sửa trong workspace của runner**. Đó không còn là verification read-only về commit gốc.

**Kết quả học tập:** bạn cài được Spotless trong Gradle Groovy DSL, hiểu `check`/`build`/`spotlessCheck`/`spotlessApply`, tự chạy ví dụ Java 17 với kết quả stdout xác định, biết thiết lập targets/exclusions và CI, tránh sửa generated code, sử dụng formatter versions ổn định, phân biệt Checkstyle và viết kiểm tra/sửa mã thành hai task độc lập khi cần.

Bài sử dụng `build.gradle`/`settings.gradle` (Groovy DSL), Java 17 và Gradle Wrapper. Lệnh Linux/macOS là `./gradlew`; Windows PowerShell dùng `.\gradlew.bat`. Các plugin/formatter versions trong ví dụ **được pin để học**, không có nghĩa mọi repository bắt buộc dùng đúng những phiên bản ấy.

## 2. Hợp đồng của task check và task apply

| Khía cạnh | Check | Apply |
| --- | --- | --- |
| Câu hỏi | Source hiện tại đã đúng format chưa? | Hãy sửa source cho đúng |
| Đọc source | Có | Có |
| Ghi tracked source | **Không** | **Có** |
| Khi vi phạm | Fail với báo cáo/diff | Ghi file được format |
| Trên CI | Nên dùng | Không nên tự chạy trước check |
| Trước commit | Dùng để xác minh | Developer chủ động dùng |
| Tích hợp vào `check` | Có | Không |
| Ảnh hưởng `git diff` | Không tạo source diff | Có thể tạo source diff |
| Spotless task | `spotlessCheck` | `spotlessApply` |

Từ “read-only” ở đây nghĩa là **không sửa mã nguồn**. Một verification build vẫn có thể tạo báo cáo và Gradle metadata/cache ở `build/` hoặc Gradle User Home. Không nên áp một yêu cầu “tuyệt đối không ghi byte nào trên đĩa” cho mọi task `check`.

### 2.1. Anti-pattern: build sửa mã rồi mới kiểm tra

**Không nên** viết trong project có Spotless:

~~~groovy
tasks.named('check') {
    dependsOn 'spotlessApply'
}
~~~

Hoặc:

~~~groovy
tasks.named('compileJava') {
    dependsOn 'spotlessApply'
}
~~~

Nếu task verification/compile tự sửa tracked files:
1. Build có side effects không được chờ đợi.
2. CI không kiểm tra đúng trạng thái commit.
3. IDE có thể thấy file thay đổi trong lúc build.
4. Các task khác có thể quan sát source trước/sau format khác nhau.
5. Người review khó tách formatting diff khỏi feature changes.

**Hướng đúng:**

~~~groovy
tasks.named('check') {
    dependsOn 'spotlessCheck'
}
~~~

Đây là **snippet minh họa** mối quan hệ đúng, không bắt buộc thêm khi dùng Spotless. Spotless Gradle plugin hiện hành thường **tự nối `spotlessCheck` vào `check`** theo mặc định. Nếu tự viết plugin formatter riêng, hãy giữ nguyên nguyên tắc chỉ nối checker vào lifecycle verification.

### 2.2. Idempotence: format hai lần không tạo thêm đổi khác

Một formatter nhất quán thỏa:

~~~text
format(format(source)) == format(source)
~~~

Ví dụ:
- Lần đầu `spotlessApply` có thể thay indentation và import order.
- Lần hai với cùng input/rules/formatter version **không nên tạo thay đổi bytes mới**.
- `spotlessCheck` sau đó PASS.

Nếu apply liên tục tạo diff mới, nghi ngờ có hai formatter xung đột, formatter version khác nhau giữa IDE và Gradle, newline rules không thống nhất, hoặc step không deterministic. Đừng chấp nhận việc formatter liên tục đổi mã là chuyện bình thường.

## 3. `check`, `build` và các task Spotless trong Gradle

Với Java plugin, lifecycle tasks có quan hệ đại ý:

~~~text
build
|-- assemble
|   +-- jar / artifacts
+-- check
    |-- test
    |-- spotlessCheck          (khi Spotless được áp)
    +-- checkstyleMain/Test    (khi Checkstyle được áp)
~~~

Đây là **sơ đồ khái niệm**; graph thực phụ thuộc plugin, Gradle version và source sets.

- `assemble` nhóm việc tạo outputs.
- `check` nhóm các verification tasks, ví dụ unit tests, style checks, static analysis.
- `build` thường phụ thuộc `assemble` và `check`.
- `spotlessCheck` kiểm tra tất cả format groups.
- `spotlessApply` áp dụng format cho tất cả format groups.
- `spotlessJavaCheck` / `spotlessJavaApply` chỉ áp cho Java format group.
- Với custom group `gradleFiles` còn có `spotlessGradleFilesCheck` và `spotlessGradleFilesApply`.

Không phải mọi Gradle project đều có Spotless tasks. `id 'java'` **không tự cài Spotless**; phải khai plugin ngoài `com.diffplug.spotless`.

### 3.1. Tại sao `build` nên FAIL khi sai format?

Khi `check` phụ thuộc `spotlessCheck`, chạy `./gradlew build` có thể fail với style violations dù source Java vẫn compile được. Đây là hành vi mong muốn: build không chỉ tạo JAR mà còn kiểm tra chính sách chất lượng.

Điều **không** mong muốn là `build` tự format để làm mất vi phạm. Developer phải sửa và commit trước khi verification PASS.

### 3.2. Khi cần fail-fast

Trên CI, có thể chạy riêng:

~~~bash
./gradlew spotlessCheck
./gradlew check
~~~

Lệnh đầu giúp thông báo style nhanh trước những unit tests tốn thời gian. Trong một build đã nối Spotless vào `check`, lần sau có thể chỉ `UP-TO-DATE`; đó là Gradle task optimization bình thường. Chạy hai lệnh không bắt buộc nếu bạn chỉ cần `./gradlew check`.

## 4. Công cụ: Spotless, Checkstyle, lint, IDE

### 4.1. Spotless làm gì?

Spotless Gradle plugin cấu hình các **format groups**. Mỗi nhóm gồm:
- **Target files**, chọn bằng `target`, `targetExclude`.
- **Formatter steps**, ví dụ `googleJavaFormat`, `removeUnusedImports`, `trimTrailingWhitespace`, `endWithNewline`.
- Các task kiểm tra và apply theo từng nhóm.
- Aggregate tasks `spotlessCheck` và `spotlessApply`.

Với Java có thể chọn google-java-format, Eclipse formatter hoặc Palantir Java Format theo policy của nhóm. Các steps được áp theo thứ tự; đừng cùng áp nhiều formatter Java mâu thuẫn lên cùng file một cách tùy tiện.

### 4.2. Checkstyle khác Spotless

Gradle **Checkstyle plugin** kiểm tra source Java theo rule configuration, tạo các task như `checkstyleMain`/`checkstyleTest` và nối vào `check`. Checkstyle **không phải autoformatter** mặc định.

**Snippet trong Java project:**

~~~groovy
plugins {
    id 'java'
    id 'checkstyle'
}

checkstyle {
    toolVersion = '10.24.0'
}
~~~

Để chạy thật, cần file `config/checkstyle/checkstyle.xml` chứa rules hợp lệ. Version trên là một giá trị ví dụ, không có nghĩa mới nhất. Khi Checkstyle version thay đổi, runtime JDK requirements của tool cũng có thể thay đổi.

Có thể dùng Checkstyle cùng Spotless, nhưng rules phải **tương thích**: nếu Spotless đẩy imports theo một thứ tự và Checkstyle cấm thứ tự ấy, cả hai tools sẽ làm developers sửa mã liên tục.

### 4.3. Lint không phải luôn auto-fix được

Spotless 7+ còn có một số lint functionality. Một lint violation có thể yêu cầu **con người sửa hoặc suppress** có căn cứ. `spotlessApply` không tự chữa được mọi static analysis issue. `spotlessCheck` FAIL sau khi apply không nhất thiết là plugin bị lỗi; đọc kỹ error message phân biệt formatting diff với lint error.

### 4.4. IDE format-on-save

IDE có thể tự format khi lưu, nhưng IntelliJ/Eclipse/VS Code có engine hoặc profile khác nhau. Nếu CI dùng Google Java Format mà IDE dùng một rule set khác, mọi lần save có thể chống lại `spotlessApply`.

Nên chọn **formatter authority** trong repository/Gradle và đồng bộ IDE nếu có integration. Không phải ép mọi developer dùng cùng một IDE.

## 5. Bài thực hành hoàn chỉnh: Java 17, Spotless check và apply

Bài này sử dụng plugin `com.diffplug.spotless` version `8.11.0` và pin formatter `googleJavaFormat('1.28.0')`, với Java source cố tình chưa format. Phiên bản thực tế của plugin đã được công bố trên Gradle Plugin Portal. Nếu dùng Gradle Wrapper/JVM không tương thích, cần điều chỉnh phiên bản theo release notes trước khi chạy.

### 5.1. Thư mục

~~~text
format-lab/
|-- settings.gradle
|-- build.gradle
|-- .editorconfig
|-- src/main/java/demo/Main.java
|-- gradlew
|-- gradlew.bat
+-- gradle/wrapper/
    |-- gradle-wrapper.jar
    +-- gradle-wrapper.properties
~~~

Điều kiện: Gradle Wrapper chạy được trên JDK 17, Spotless 8.11.0 và google-java-format 1.28.0 có thể được resolve từ plugin/artifact repositories hoặc đã nằm trong cache. Không cần thư viện ứng dụng bên ngoài. Nếu chưa có Wrapper, dùng Gradle đã cài để chạy `gradle wrapper` một lần rồi lưu các file Wrapper trong repository.

### 5.2. `settings.gradle`

~~~groovy
rootProject.name = 'format-lab'
~~~

Plugin resolution có thể yêu cầu truy cập Gradle Plugin Portal. Nếu tổ chức dùng mirror, cấu hình `pluginManagement.repositories` phù hợp ở settings; đừng nhầm nó với repositories của Java dependencies.

### 5.3. `build.gradle` — toàn bộ

~~~groovy
plugins {
    id 'application'
    id 'com.diffplug.spotless' version '8.11.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}

spotless {
    java {
        // Nguồn Java do nhóm sở hữu trong main/test source sets.
        target 'src/*/java/**/*.java'

        // Bảo vệ generated Java nếu nằm trong source tree.
        targetExclude 'src/*/java/**/generated/**'

        // Pin engine version, không chỉ pin plugin version.
        googleJavaFormat('1.28.0')
        removeUnusedImports()
        trimTrailingWhitespace()
        endWithNewline()
    }

    format 'gradleFiles', {
        target '*.gradle', 'gradle/*.gradle'
        trimTrailingWhitespace()
        endWithNewline()
    }
}
~~~

**Giải thích:**
- `application` áp dụng Java plugin và tạo `run` task.
- `com.diffplug.spotless` là plugin ngoài, phải resolve theo cơ chế plugin DSL.
- `java.toolchain` yêu cầu Java 17 cho Java tasks.
- `target` chỉ định source Java cần format, tránh quét toàn bộ project outputs.
- `targetExclude` là ví dụ bảo vệ mã do generator tạo trong source tree; thông thường generated sources nên nằm ở `build/generated`.
- `googleJavaFormat('1.28.0')` cố định **formatter engine** tách biệt khỏi `Spotless 8.11.0`.
- `removeUnusedImports` có thể sửa import declarations, không chỉ spaces; nên chạy compile/tests sau apply.
- `trimTrailingWhitespace` và `endWithNewline` xử lý text whitespace.
- Custom group `gradleFiles` định dạng Gradle scripts bằng các steps nhẹ, không ép Java formatter lên Groovy code.
- `spotlessCheck` được plugin nối vào `check` theo mặc định; **không thêm `spotlessApply` vào check**.

### 5.4. `.editorconfig`

~~~editorconfig
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true

[*.java]
indent_style = space
indent_size = 2
~~~

File này giúp IDE hỗ trợ UTF-8/LF. Google Java Format có rules riêng, không tự đọc mọi key của EditorConfig.

### 5.5. `src/main/java/demo/Main.java` — file chưa định dạng

Lưu nguyên một dòng Java UTF-8:

~~~java
package demo;public class Main{public static void main(String[] args){System.out.println("Spotless check/apply: OK");}}
~~~

Đây là Java hợp lệ, nhưng không đạt Google Java Format. Nó có `package demo`, public class `Main` và `main(String[])` chính xác.

### 5.6. Chạy checker lần đầu

~~~bash
./gradlew spotlessCheck
~~~

**Kỳ vọng:** task `spotlessJavaCheck` báo style violation và fail, thường kèm filename/diff và hướng dẫn `spotlessApply`. Log chính xác thay đổi tùy Gradle/Spotless versions và OS nên không giả tạo một stdout đầy đủ.

**Quan trọng:** File `Main.java` vẫn giữ nguyên một dòng. Checker không làm code pass bằng cách tự sửa nó.

### 5.7. Chạy fixer

~~~bash
./gradlew spotlessApply
~~~

Spotless ghi lại `Main.java` theo style tương đương:

~~~java
package demo;

public class Main {
  public static void main(String[] args) {
    System.out.println("Spotless check/apply: OK");
  }
}
~~~

Hình thức trên là kết quả dự kiến của formatter version đã pin; với dự án thật nên review actual output/diff thay vì xem code mẫu là tài liệu mô tả 100% tất cả formatter algorithms.

Chạy tiếp:

~~~bash
./gradlew spotlessCheck
./gradlew check
./gradlew run --quiet
~~~

**Stdout chính xác của Java chương trình, không tính log Gradle:**

~~~text
Spotless check/apply: OK
~~~

`./gradlew check` có thể hiển thị `test NO-SOURCE` vì lab không có test source; nó vẫn thực hiện verification tasks. `spotlessCheck` phải PASS sau apply nếu không còn vi phạm khác.

### 5.8. Biên dịch/chạy Java không qua Gradle

Với JDK 17 trong PATH:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/Main.java
java -cp out demo.Main
~~~

Stdout:

~~~text
Spotless check/apply: OK
~~~

Hai lệnh này chỉ xác nhận **cú pháp Java/behavior**, không kiểm tra formatting. `javac` không phải Spotless.

### 5.9. Kiểm chứng apply lần hai

~~~bash
./gradlew spotlessApply
git diff --stat
git diff -- src/main/java/demo/Main.java

./gradlew spotlessApply
git diff --stat
~~~

Nếu không thay sources/config/versions giữa hai lần apply thì lần hai **không nên tạo thêm thay đổi mới**. Tuy nhiên `git diff` có thể vẫn hiển thị diff từ lần apply đầu chưa commit. Muốn chứng minh chính xác, so sánh **hash/bytes trước và sau lần hai**, hoặc dùng một checkpoint an toàn.

**Không dùng `git reset --hard` để xóa định dạng khi đang có source changes chưa lưu**, vì có thể làm mất code.

## 6. Chạy check/apply cho từng nhóm file

Spotless cho phép giới hạn phạm vi task:

~~~bash
./gradlew spotlessCheck
./gradlew spotlessJavaCheck
./gradlew spotlessGradleFilesCheck
~~~

- `spotlessCheck`: toàn bộ Java và Gradle scripts đã định nghĩa trong lab.
- `spotlessJavaCheck`: chỉ Java files.
- `spotlessGradleFilesCheck`: chỉ nhóm `gradleFiles`.

Khi muốn sửa từng nhóm:

~~~bash
./gradlew spotlessJavaApply
./gradlew spotlessGradleFilesApply
~~~

Không cần autoformat toàn bộ repo mỗi lần chỉ muốn sửa một file Java. Kiểm tra danh sách tasks thật bằng `./gradlew tasks --all` vì task names tùy groups được cấu hình.

### 6.1. Mục tiêu hẹp tốt hơn glob quá rộng

**Sai dễ gây tác dụng phụ:**

~~~groovy
spotless {
    java {
        target '**/*.java'
        googleJavaFormat('1.28.0')
    }
}
~~~

Nó có thể quét `build/generated`, mã sinh của OpenAPI/protobuf/annotation processor, thậm chí build logic của công cụ khác. Formatter áp lên **output do task khác sở hữu** có thể phá incremental build hoặc khiến mỗi lần generate lại tạo style diff.

**Nên:**

~~~groovy
spotless {
    java {
        target 'src/main/java/**/*.java', 'src/test/java/**/*.java'
        targetExclude 'src/generated/**/*.java'
        googleJavaFormat('1.28.0')
    }
}
~~~

Đây là **snippet thay thế** cấu hình Java của lab, không áp hai blocks trùng phạm vi cùng lúc. Bổ sung `src/integrationTest/java` khi thật sự có source set ấy.

### 6.2. Xử lý generated sources

Những nguồn điển hình:

~~~text
build/generated/sources/annotationProcessor/java/main/
build/generated/sources/openapi/java/
build/generated/sources/protobuf/java/main/
~~~

Đây là các path ví dụ; plugin có thể dùng tên khác. Quy tắc:
- Không để `spotlessApply` tùy ý sửa các outputs đó.
- Nếu muốn generated code đúng style, sửa generator templates/options hoặc tích hợp formatter như **một bước của generator pipeline** có owner rõ.
- Không cho hai tasks cùng ghi một output directory.
- Nếu generated code được commit, phải ghi rõ nó do ai sở hữu, lúc nào regenerate, có apply format không.
- Không bỏ source paths vào `target` theo kiểu quét cả `build/` chỉ vì một file sinh chưa khớp.

### 6.3. Format text files khác

~~~groovy
spotless {
    format 'misc', {
        target '*.gradle', '*.md', '.gitattributes'
        trimTrailingWhitespace()
        endWithNewline()
    }
}
~~~

Snippet này chỉ xử lý text, không thay thế parser-specific Java formatter. Đừng cấu hình text steps với `target '**/*'` rồi vô tình làm hỏng PNG/JAR/ZIP.

## 7. CI chỉ check, không apply

Một workflow kiểm tra mã đáng tin:

~~~text
checkout commit
    |
    v
JDK / Gradle Wrapper setup
    |
    v
spotlessCheck
    |
    +-- FAIL -> báo lỗi, reject PR, không thay tracked source
    |
    +-- PASS -> check / tests / build
                  |
                  v
                publish artifacts nếu policy cho phép
~~~

### 7.1. Ví dụ GitHub Actions

~~~yaml
name: Gradle verification
on: [push, pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Check formatting
        run: ./gradlew spotlessCheck
      - name: Run verification
        run: ./gradlew check
~~~

Đây là snippet CI, không phải bắt buộc dùng GitHub. Các actions, plugin binaries và repositories cần được review/pin theo security policy. Mặc dù `check` có thể đã bao gồm Spotless, bước check riêng đầu là cách **fail-fast**.

**Sai về ý nghĩa verification:**

~~~yaml
- name: Auto-fix before verifying
  run: ./gradlew spotlessApply spotlessCheck
~~~

Lệnh này xác nhận **trạng thái sau sửa**, không còn bảo đảm commit do người đóng góp gửi lên ban đầu đạt style. Muốn bot auto-fix, hãy tạo workflow riêng mở PR/báo diff với quyền ghi và review thích hợp.

### 7.2. Vì sao `--dry-run` không thay `spotlessCheck`?

~~~bash
./gradlew spotlessApply --dry-run
~~~

Gradle sẽ mô tả những tasks **sẽ được chạy** chứ không thực thi formatter logic, nên không sửa **và cũng không kiểm tra style**. Muốn checker read-only, dùng `./gradlew spotlessCheck`.

`./gradlew check --dry-run` hữu ích **để xem wiring/task graph**, không phải bằng chứng verification PASS.

### 7.3. Kiểm tra working tree

~~~bash
git diff --exit-code
git status --short
~~~

`git diff --exit-code` phát hiện tracked file modifications chưa stage, không tự phát hiện mọi untracked files. `git status --short` cho biết thay đổi và untracked files theo Git ignore policy. Gradle có thể tạo outputs bên trong `build/` đã được Git ignore; đó không trái với nguyên tắc checker không sửa tracked sources.

## 8. Java formatting không thay thế Checkstyle/test

| Công cụ | Chức năng | Ghi source? |
| --- | --- | --- |
| `spotlessCheck` | Formatting verification | Không |
| `spotlessApply` | Autoformat source | Có |
| `checkstyleMain` | Java style/static rules | Không theo mặc định |
| PMD/SpotBugs tasks | Static analysis theo plugin | Không theo mặc định |
| `compileJava` | Compile Java | Không nên |
| `test` | Test chương trình | Không nên |
| IDE format-on-save | Editor formatting | Có khi được bật |

Một class Java có thể format hoàn hảo mà vẫn có security bug, race condition hoặc sai nghiệp vụ. Do đó:
- `spotlessCheck PASS` không phải `build PASS`.
- `build PASS` không đảm bảo mọi bug đã được loại.
- Sau apply chạy compile/tests và review diff.
- Chọn Checkstyle/Spotless rules không mâu thuẫn.

### 8.1. Checkstyle và Spotless conflict

Ví dụ Spotless format imports theo Google Java Format, Checkstyle yêu cầu import order khác. Dev chạy apply thì Checkstyle fail, sửa theo Checkstyle thì Spotless fail. Đây là **hai policies không nhất quán**. Giải pháp là sửa cấu hình style, không nối một fixer thứ hai vào `check` rồi tự ghi mã qua lại.

## 9. Multi-project Gradle

Giả sử build gồm `:app` và `:library`:

~~~text
root/
|-- settings.gradle
|-- build.gradle
|-- app/build.gradle
|-- app/src/main/java/...
|-- library/build.gradle
+-- library/src/main/java/...
~~~

### 9.1. Pin plugin version một chỗ

**Root `build.gradle`:**

~~~groovy
plugins {
    id 'com.diffplug.spotless' version '8.11.0' apply false
}
~~~

**`app/build.gradle` hoặc `library/build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'com.diffplug.spotless'
}

spotless {
    java {
        target 'src/*/java/**/*.java'
        googleJavaFormat('1.28.0')
        trimTrailingWhitespace()
        endWithNewline()
    }
}
~~~

Đây là snippets multi-project, chưa phải project chạy độc lập; cần `settings.gradle` include projects và source code thực tế. Root `apply false` **không tự áp plugin vào subprojects**. Mỗi module cần apply Spotless hoặc một convention plugin làm điều đó.

### 9.2. Task paths

~~~bash
./gradlew :app:spotlessCheck
./gradlew :library:spotlessCheck
./gradlew :app:spotlessApply
~~~

Lệnh thứ ba sửa code **của app**, không phải library. Nếu muốn root task kiểm tra cả hai modules:

~~~groovy
tasks.register('formatCheckAll') {
    group = 'verification'
    description = 'Kiểm tra formatting hai modules'
    dependsOn ':app:spotlessCheck', ':library:spotlessCheck'
}
~~~

Đây là snippet trong root và phụ thuộc project/task paths thực sự tồn tại.

### 9.3. Khi nào dùng convention plugin?

Nếu có nhiều projects, nên dùng một **convention plugin** để:
- Áp Spotless có điều kiện theo loại module.
- Pin formatter engines và setup targets/exclusions.
- Không lặp nguyên block vào 20 subprojects.
- Đặt đúng plugin classpath/version khi dùng precompiled script plugins.
- Kiểm thử rằng `spotlessCheck` fail mà không thay source và `spotlessApply` sửa rồi check PASS.
- Tránh cross-project configuration rộng khi không cần.

## 10. Plugin version và engine version là hai cấp khác nhau

~~~groovy
plugins {
    id 'com.diffplug.spotless' version '8.11.0'
}

spotless {
    java {
        googleJavaFormat('1.28.0')
    }
}
~~~

- **Spotless 8.11.0:** Gradle plugin integration/task behavior.
- **google-java-format 1.28.0:** thuật toán format Java source.
- **Gradle Wrapper:** APIs/tool execution compatibility.
- **JDK:** khả năng chạy Gradle/formatter/compiler.

Nếu bỏ version ở `googleJavaFormat()`, formatter default có thể đổi khi nâng Spotless plugin và gây hàng nghìn dòng diff. Pin engine riêng để nâng theo kế hoạch.

### 10.1. Chuyển formatter engine cần PR riêng

Khi đổi Eclipse JDT → Google Java Format hoặc nâng major formatter:
1. Xem release notes/compatibility.
2. Tạo branch/PR chuyên migration style.
3. Pin versions.
4. Chạy `spotlessApply`.
5. Review `git diff --stat` và thay đổi thực tế.
6. Chạy `spotlessCheck`, `compileJava`, `test`.
7. Đồng bộ IDE/convention plugin.
8. Merge có kế hoạch để giảm conflict với feature PR đang mở.

Không nâng formatter trong một PR sửa logic nhỏ mà không báo rõ tác động.

### 10.2. Idempotence khác Gradle `UP-TO-DATE`

`UP-TO-DATE` là trạng thái up-to-date của task theo Gradle, không phải bảo đảm formatter chạy hai lần cho bytes giống nhau trên mọi máy. Để xác minh formatting reproducibility, so sánh files/hashes trước và sau lần apply thứ hai khi inputs/rules không đổi. Nếu lệch, kiểm tra formatter steps và OS/line-ending differences.

## 11. Newline, encoding và Git

Source files có thể bị đổi diff liên tục vì:
- Windows CRLF vs Linux LF.
- Tab/spaces khác style.
- Thiếu newline cuối file.
- Trailing whitespace.
- Editor và Gradle formatter khác nhau.
- UTF-8 BOM hoặc legacy encoding.

### 11.1. Policy bằng EditorConfig + Git attributes

**`.editorconfig`:**

~~~editorconfig
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true

[*.java]
indent_style = space
indent_size = 2
~~~

**`.gitattributes`:**

~~~gitattributes
*.java text eol=lf
*.gradle text eol=lf
*.md text eol=lf
*.properties text eol=lf
~~~

EditorConfig hướng IDE có hỗ trợ; Git attributes kiểm soát normalization/checkout cho text. Chúng bổ sung cho Spotless nhưng không thay parser-based Java formatting. Khi áp quy tắc mới vào repo cũ, nên có PR renormalization riêng.

### 11.2. Đừng format binary

**Sai:**

~~~groovy
spotless {
    format 'everything', {
        target '**/*'
        trimTrailingWhitespace()
        endWithNewline()
    }
}
~~~

Pattern này có thể chạm PNG, JAR, ZIP hoặc generated outputs. Chỉ định text files/globs rõ ràng. Nếu có binary file không bị phát hiện đúng, những transformations text có thể làm hỏng bytes.

## 12. Local developer workflow

Một chu trình hợp lý:

~~~bash
./gradlew spotlessApply
git diff --check
git diff --stat
git diff
./gradlew spotlessCheck
./gradlew test
~~~

Giải thích:
- Apply có thể thay tracked source.
- `git diff --check` phát hiện một số whitespace errors ở diff.
- `git diff --stat` cho biết phạm vi thay đổi.
- `git diff` giúp review từng hunk.
- SpotlessCheck xác nhận định dạng đạt rules.
- Test xác nhận mã không bị ảnh hưởng ngoài ý muốn.

Developer chủ động stage/commit các file đã review. Nếu formatter đổi quá nhiều file ngoài dự kiến, kiểm tra `target`/formatter version trước khi commit.

### 12.1. Git hooks

Có thể cài pre-commit/pre-push hook chạy `spotlessCheck`. Dù Spotless có hỗ trợ một số hook tasks, không mặc định mọi developer clone đã có hook. CI vẫn cần checker để ngăn bypass.

Một workflow rõ ràng là hook kiểm tra và fail với hướng dẫn apply; dev chạy apply, review diff, stage lại, rồi commit/push. Tránh hook auto-edit rồi auto-commit khi chưa review.

### 12.2. IDE format-on-save

Nếu IDE formatter khác Gradle engine, việc autoformat mỗi lần save có thể gây xung đột. Dùng integration formatter phù hợp hoặc coi Gradle `spotlessApply` là phương tiện sửa chuẩn, `spotlessCheck` là nguồn verification cuối. Không cần buộc tất cả developers dùng một IDE cụ thể.

## 13. Khi cần tự viết task check/fix

Một organization có thể có quy tắc text riêng không thuộc formatter hiện có. Hãy vẫn tách:
- `verifyX`: chỉ đọc source, fail khi sai.
- `fixX`: chủ động sửa file, không nối vào `check`.
- Báo cáo sinh ra dưới `build/` nếu cần, có output rõ.
- Không để tasks mutate cùng file đồng thời mà không có owner/order.

### 13.1. Ví dụ kiểm tra newline cuối một file

**Snippet `build.gradle` trong project đã có Java plugin, đồng thời file `docs/config.txt` tồn tại:**

~~~groovy
def docFile = layout.projectDirectory.file('docs/config.txt')

tasks.register('verifyDocFinalNewline') {
    group = 'verification'
    inputs.file(docFile)

    doLast {
        byte[] bytes = docFile.asFile.bytes
        if (bytes.length == 0 || bytes[bytes.length - 1] != (byte) 10) {
            throw new GradleException(
                'docs/config.txt phải kết thúc bằng LF'
            )
        }
    }
}

tasks.register('fixDocFinalNewline') {
    group = 'formatting'

    doLast {
        File file = docFile.asFile
        byte[] bytes = file.bytes
        if (bytes.length == 0 || bytes[bytes.length - 1] != (byte) 10) {
            file.append('\n', 'UTF-8')
        }
    }
}

// CHỈ verify là dependency của check.
tasks.named('check') {
    dependsOn tasks.named('verifyDocFinalNewline')
}
~~~

Đây là **ví dụ học tập**, không phải formatter production:
- File phải có sẵn, nếu chưa có cần error/creation policy riêng.
- Checker chỉ kiểm tra byte cuối LF, không chuẩn hóa toàn bộ CRLF thành LF.
- Fixer mutate file nhưng không được tự cache như task tạo outputs trong `build/`.
- `tasks.named('check')` cần lifecycle check task từ Java/verification plugin; Base plugin đơn thuần có thể không tạo task `check`.
- Nếu cần rules phức tạp, dùng Spotless hoặc formatter chuyên dụng thay vì nhiều Groovy file mutations ad hoc.

Chạy:

~~~bash
./gradlew verifyDocFinalNewline
./gradlew fixDocFinalNewline
./gradlew verifyDocFinalNewline
~~~

Kỳ vọng: nếu file thiếu newline, verify ban đầu FAIL; fix bổ sung newline; verify sau PASS. Không có stdout ứng dụng cố định ngoài thông báo Gradle vì đây là tasks minh họa.

### 13.2. Tránh một task có tên mơ hồ vừa check vừa sửa

**Không nên:**

~~~groovy
tasks.register('format') {
    doLast {
        if (project.hasProperty('fix')) {
            // Ghi source
        } else {
            // Chỉ kiểm tra source
        }
    }
}
~~~

Task này đổi semantics theo flag `-Pfix`, dễ làm CI vô tình mutate file, khó khai input/output và khó audit. Chia thành hai task tên rõ ràng.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| `Task spotlessCheck not found` | Spotless chưa apply vào project | Kiểm tra plugin ID/target module |
| `spotlessJavaCheck FAILED` | Source chưa đúng formatter | Chạy `spotlessJavaApply` local rồi review |
| `spotlessApply` xong check vẫn fail | Lint không fix hoặc formatter conflict | Đọc error và sửa/suppress có căn cứ |
| CI pass dù code sai | CI apply trước check | Bỏ apply khỏi verification |
| `--dry-run` không báo violations | Gradle không chạy task actions | Dùng `spotlessCheck` |
| Checkstyle fail sau apply | Rules mâu thuẫn | Đồng bộ rules/formatter engine |
| Java file không được quét | `target` hoặc `targetExclude` không khớp | Điều chỉnh source globs |
| Generated sources bị sửa | Target quét `build/generated` | Exclude output, sửa generator templates |
| Windows và Linux sửa whitespace liên tục | Git/EditorConfig/IDE khác nhau | Thống nhất LF/UTF-8/style policy |
| Nâng plugin tạo nhiều diffs | Default engine đổi | Pin engine và migration PR |
| Java compile fail nhưng Spotless PASS | Formatter không phải compiler | Chạy `compileJava`/`test` |
| Root `apply false` mà app thiếu tasks | Chưa áp plugin tại app | Apply tại module hoặc convention plugin |
| Plugin không resolve | Plugin ID/version/repository/JDK | Kiểm tra Wrapper, Java runtime, mirrors |
| `git diff` còn sau lần apply hai | Diff từ lần đầu chưa commit | So sánh hashes trước/sau |
| `check` tự sửa source | Sai wiring `dependsOn spotlessApply` | Chỉ nối verification task |
| Static analysis fail nhưng apply không giúp | Lint/bug không auto-fix được | Sửa code/rule thay vì ép apply |

### 14.1. Bộ lệnh chẩn đoán

~~~bash
./gradlew tasks --all
./gradlew spotlessCheck --info
./gradlew spotlessJavaCheck
./gradlew spotlessApply
./gradlew check --dry-run
./gradlew check
./gradlew compileJava
./gradlew test
git diff --stat
git status --short
~~~

- `tasks --all`: tên task thực tế.
- `spotlessCheck`: format verification thật.
- `spotlessApply`: source mutation.
- `check --dry-run`: chỉ quan sát task graph, không thực thi checks.
- `compileJava`/`test`: chức năng Java.
- Git commands: trạng thái working tree.

### 14.2. Khi `check` không chạy Spotless

Spotless mặc định nối `spotlessCheck` vào `check`. Có thể tắt:

~~~groovy
spotless {
    enforceCheck false
}
~~~

Đây là một **snippet thay đổi behavior**. Nó không nên là default vì bỏ quality gate khỏi lifecycle. Nếu tổ chức có lý do để tắt, hãy gọi `spotlessCheck` rõ ràng trên CI hoặc wire lại task check theo policy. **Đừng** thay bằng `spotlessApply`.

### 14.3. Lỗi plugin/JDK compatibility

Nếu không load được Spotless hoặc google-java-format:
1. Xem `./gradlew --version` và JVM chạy Gradle.
2. Kiểm tra plugin/engine versions có hỗ trợ Gradle Wrapper/JDK đó không.
3. Kiểm tra plugin repositories/proxy/offline cache.
4. Nếu formatter dùng syntax Java mới, xem engine compatibility.
5. Không sửa source compatibility bừa bãi khi nguyên nhân là plugin runtime.

## 15. Bài tập kèm đáp án

### Bài 1 — CI nên chạy gì?

**Câu hỏi:** CI chỉ được phát hiện style violations trên commit, không sửa mã. Chạy gì?

**Đáp án:** `./gradlew spotlessCheck` hoặc `check` đã nối Spotless. Không chạy `spotlessApply` trước.

### Bài 2 — Sửa riêng Java

**Câu hỏi:** Dev muốn format Java files mà không đổi Gradle scripts.

**Đáp án:** `./gradlew spotlessJavaApply`. Sau đó xem `git diff` và chạy `spotlessJavaCheck`.

### Bài 3 — Một dòng Java

**Câu hỏi:** `Main.java` một dòng ở lab compile được nhưng `spotlessCheck` fail được không?

**Đáp án:** Có. Java compiler và formatter xác minh hai đặc tính khác nhau.

### Bài 4 — Wrong wiring

**Câu hỏi:** `check.dependsOn spotlessApply` sai vì sao?

**Đáp án:** Nó biến verification thành mutation, CI có thể PASS trên files đã bị sửa.

### Bài 5 — Idempotence

**Câu hỏi:** Sau apply lần thứ hai `git diff` vẫn có, chứng minh lần thứ hai tạo diff mới chưa?

**Đáp án:** Chưa. Diff có thể từ lần đầu chưa commit. Phải so sánh bytes/hashes trước/sau lần hai.

### Bài 6 — Checkstyle

**Câu hỏi:** `checkstyleMain` có autoformat như `spotlessJavaApply` không?

**Đáp án:** Không theo mặc định; Checkstyle kiểm tra và báo violations.

### Bài 7 — Generated files

**Câu hỏi:** Code generator tạo `build/generated`, Spotless chạy `target '**/*.java'` rồi sửa output. Nên làm gì?

**Đáp án:** Exclude generated outputs, dùng globs hẹp, sửa generator/template nếu yêu cầu style.

### Bài 8 — Version drift

**Câu hỏi:** Vì sao nâng Spotless có thể tạo nhiều Java diffs nếu không đổi config?

**Đáp án:** Formatter default/behavior có thể đổi. Pin engine version riêng với plugin version và review migration.

### Bài 9 — Dry-run

**Câu hỏi:** `spotlessApply --dry-run` có thay `spotlessCheck` không?

**Đáp án:** Không, vì nó không thực thi formatter actions.

### Bài 10 — Multi-project

**Câu hỏi:** Root `apply false` có tự áp Spotless cho `:app` không?

**Đáp án:** Không. App cần apply plugin hoặc convention plugin.

### Bài 11 — CI tự sửa

**Câu hỏi:** CI chạy apply rồi check và PASS. Điều này có chứng minh commit gốc đúng style không?

**Đáp án:** Không, chỉ trạng thái đã sửa. CI phải fail nếu code gốc sai.

### Bài 12 — Thực hành

1. Tạo project `format-lab` theo phần 5 với `Main.java` một dòng.
2. Chạy `spotlessCheck`: thấy fail và file không bị sửa.
3. Chạy `spotlessApply` rồi review diff.
4. Chạy `spotlessJavaCheck` và `check`: kỳ vọng PASS.
5. Chạy `run --quiet` và so stdout.
6. Chạy apply lần hai, kiểm tra không có bytes thay đổi mới.
7. Thử thêm Java test file chưa format và xác nhận glob nhận được.
8. Thử tạo `build/generated` file, xác nhận không bị format.
9. Thiết lập CI chỉ chạy checker và xác minh commit chưa format bị từ chối.
10. Nếu thêm Checkstyle, so sánh formatter vs lint violations.

**Tiêu chí hoàn thành:** Bạn biết task nào đọc/kiểm tra và task nào sửa source, hiểu Gradle `check`/`build` lifecycle, chạy được lab Java 17, pin formatter versions, chọn globs đúng và xây CI không tự viết lại mã.

## 16. Checklist đưa vào repository

- [ ] Thống nhất một formatter authority cho Java.
- [ ] Pin Spotless plugin và formatter engine versions.
- [ ] Giữ `spotlessCheck` và `spotlessApply` riêng biệt.
- [ ] `check` chỉ phụ thuộc formatter checker, không phụ thuộc apply.
- [ ] Java source targets bao gồm main/test/source sets cần quản lý.
- [ ] Exclude generated sources và binary files.
- [ ] Có policy UTF-8/LF/Git attributes/EditorConfig.
- [ ] CI fail trên code chưa format, không tự apply.
- [ ] Dev chạy apply rồi review Git diff trước commit.
- [ ] Sau apply chạy compile/tests.
- [ ] Các lint rules không auto-fix được có cách sửa/suppress có lý do.
- [ ] Checkstyle và Spotless rules không xung đột.
- [ ] Multi-project dùng convention plugin thống nhất khi cần.
- [ ] Nâng formatter engine bằng PR có kế hoạch.
- [ ] Kiểm chứng idempotence của formatter.
- [ ] Không dùng destructive Git cleanup như phương pháp format.
- [ ] Kiểm soát Gradle Wrapper/JDK/plugin repositories/security.

## 17. Tài liệu chính thức và tham khảo

- [Spotless Gradle plugin](https://github.com/diffplug/spotless/blob/main/plugin-gradle/README.md): format groups, `spotlessCheck`, `spotlessApply`, Java formatter steps, `enforceCheck` và target/exclusions.
- [Spotless repository](https://github.com/diffplug/spotless): output minh họa và phương pháp khắc phục formatting violations.
- [Gradle Plugin Portal — com.diffplug.spotless](https://plugins.gradle.org/plugin/com.diffplug.spotless): plugin ID, versions và cách khai trong plugins DSL.
- [Gradle — Checkstyle Plugin](https://docs.gradle.org/current/userguide/checkstyle_plugin.html): `checkstyleMain`/`checkstyleTest`, tích hợp `check`.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): `compileJava`, `test`, `check` và `build`.
- [Gradle — Base Plugin](https://docs.gradle.org/current/userguide/base_plugin.html): lifecycle `assemble`/`check`/`build`.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`/`named`/`configureEach`.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): input/output tracking và reproducibility.
- [EditorConfig specification](https://editorconfig.org/): charset, indentation và line endings.
