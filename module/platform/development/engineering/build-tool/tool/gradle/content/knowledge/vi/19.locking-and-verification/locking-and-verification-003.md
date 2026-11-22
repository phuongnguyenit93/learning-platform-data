# Tạo, cập nhật và kiểm tra dependency lockfile trong Gradle

Trong một dự án Java, cùng một dòng dependency có thể cho ra những phiên bản khác nhau theo thời gian. Chẳng hạn, `implementation("org.apache.commons:commons-lang3:3.+")` yêu cầu **một phiên bản phù hợp thuộc nhánh 3.x**, không chỉ định một phiên bản cố định. Khi Maven repository xuất bản phiên bản mới, build ở máy khác hoặc trên CI có thể phân giải ra module version khác, kể cả khi source code và build script không đổi.

**Dependency locking** là cơ chế của Gradle lưu lại **các phiên bản đã thực sự được phân giải** thành tệp `gradle.lockfile` và dùng trạng thái đó để kiểm tra, ràng buộc những lượt phân giải tiếp theo. Nhờ vậy, bạn có thể giữ dependency graph ổn định trong công việc hằng ngày, đồng thời **cập nhật có chủ đích** khi muốn nâng phiên bản.

Bài học này thuộc phần **Khóa và xác minh** của Build Tool Gradle. Nội dung hướng dẫn từ nguyên lý đến thực hành: bật khóa, tạo lockfile, đọc nội dung, cập nhật toàn bộ hay chọn lọc, xác minh trạng thái, tổ chức lockfiles trong multi-project, dùng `DEFAULT`/`STRICT`/`LENIENT`, phân biệt khóa phiên bản và xác minh checksum, xử lý lỗi thường gặp và đưa quy trình kiểm tra vào Git/CI.

> **Nguyên tắc cốt lõi:** Lockfile ghi **phiên bản dependency sau khi Gradle resolution**, không ghi byte hash của JAR, không thay thế khai báo dependency và không bảo đảm artifact cùng tọa độ là an toàn. Muốn kiểm tra tính toàn vẹn artifact, cần thêm **dependency verification**.

## 1. Dependency locking giải quyết vấn đề gì?

Giả sử `build.gradle.kts` có:

```kotlin
dependencies {
    implementation("com.example:client:1.+")
}
```

Đây là **notation minh họa**, không yêu cầu artifact `com.example:client` tồn tại. Nếu hai thời điểm resolution nhìn thấy các phiên bản khác nhau:

```text
Ngày A:
  requested: com.example:client:1.+
  resolved:  com.example:client:1.4

Ngày B:
  requested: com.example:client:1.+
  resolved:  com.example:client:1.5
```

Build có thể hành xử khác dù bạn không sửa source. Không chỉ dependency trực tiếp thay đổi: **transitive dependencies** cũng có thể bị nâng cấp bởi conflict resolution, platform constraints hoặc việc nhà phát hành cập nhật metadata.

Khi locking đã được kích hoạt và trạng thái phù hợp được tạo, Gradle ghi phiên bản **đã chọn** vào lockfile. Ở lần resolution sau, phiên bản đó được ràng buộc, không tự trôi theo một release mới chỉ vì nó phù hợp với version selector động.

### Có khóa nghĩa là đã “đóng băng” toàn bộ build chưa?

Không. Lockfile không tự cố định:

- JDK/toolchain, Gradle Wrapper version, OS, compiler flags và môi trường build.
- Nội dung của một artifact bị **thay đổi nhưng giữ nguyên version** (đặc biệt là các dependency dạng changing hoặc `-SNAPSHOT`).
- File do project khác build, local file dependencies hoặc source dependencies được xử lý theo cơ chế riêng.
- Gradle plugins và buildscript classpath **nếu chưa khóa riêng các configurations liên quan**.
- Những configurations chưa được bật locking hoặc chưa từng được resolve trong lúc ghi lock.

Vì vậy cần kết hợp lockfile với Gradle Wrapper, source control, dependency verification, các phiên bản toolchain phù hợp và CI tests khi cần tính tái lập cao.

## 2. Phân biệt declared version, resolved version và locked version

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Declared/requested** | `3.+`, `[3.16,4.0)`, `3.16.0` | Ràng buộc mà build author yêu cầu trong DSL/metadata |
| **Resolved/selected** | `3.17.0` | Phiên bản Gradle thực sự chọn cho một configuration |
| **Locked** | `org.apache.commons:commons-lang3:3.17.0` | Phiên bản đã được lưu trong lock state và dùng để kiểm tra resolution sau này |
| **Artifact checksum** | SHA-256 của JAR | Dấu vân tay **nội dung bytes**, do dependency verification quản lý, không phải dependency locking |

Một tuyên bố `implementation("g:a:1.0")` **không chắc làm resolved version luôn bằng 1.0**; các dependency khác hoặc constraints có thể khiến Gradle chọn 1.2.0 nếu các rules cho phép. Lockfile ghi bản **đã chọn**, không đơn giản copy số version ở build script.

Gradle dùng trạng thái khóa như một **strict version constraint** khi resolve: nếu build khai báo version mới không tương thích với phiên bản đã khóa, resolution thất bại và yêu cầu cập nhật lock state có chủ đích.

### `version catalog` khác `gradle.lockfile`

Trong `gradle/libs.versions.toml`, bạn có thể ghi:

```toml
[versions]
commonsLang = "3.16.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commonsLang" }
```

Version Catalog giúp **quản lý khai báo version tập trung**, nhưng không lưu toàn bộ các transitive modules đã được Gradle chọn cho mỗi resolved configuration. Lockfile mới là trạng thái khóa **sau resolution**. Hai cơ chế bổ sung nhau, không thay thế nhau.

Tương tự, BOM/platform hoặc dependency constraints có thể giới hạn hay điều phối versions; chúng không tự tạo một lockfile trừ khi bạn bật locking và ghi lock state.

## 3. Bật dependency locking đúng chỗ

Gradle bật locking theo **configuration**, bởi mỗi configuration là một dependency graph có thể resolve riêng. Với Java project, bạn thường quan tâm `compileClasspath`, `runtimeClasspath`, `testCompileClasspath`, `testRuntimeClasspath`, `annotationProcessor`, `testAnnotationProcessor`, v.v.

### Cách A: bật cho tất cả project configurations

Trong `build.gradle.kts`:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Đây là cách gọn cho project cần lưu trạng thái dependencies của các configurations **có thể resolve**. Khi một configuration chỉ là dependency bucket dùng để khai báo và không thể resolve, việc kích hoạt locking trên nó không tạo ra một lock state thực sự.

**Lưu ý quan trọng:** `lockAllConfigurations()` trên project **không tự khóa `buildscript` configurations**. Đây cũng **không phải một lệnh tự phân giải mọi configuration**: lockfile chỉ ghi những configuration được giải quyết trong execution cụ thể.

### Cách B: chỉ khóa những configurations có chủ đích

Ví dụ với project đã áp dụng Java plugin:

```kotlin
configurations.named("compileClasspath") {
    resolutionStrategy.activateDependencyLocking()
}

configurations.named("runtimeClasspath") {
    resolutionStrategy.activateDependencyLocking()
}
```

Nếu chỉ bật hai configuration này, bạn không được giả định test classpaths hay annotation processor dependencies cũng đã bị khóa. Cách chọn lọc hữu ích khi bạn hiểu rõ quy trình CI nào resolve configuration nào, và muốn giảm phạm vi thay đổi.

### Tắt locking cho một configuration

Khi build đã bật lock rộng nhưng một configuration không cần khóa:

```kotlin
configurations.named("someResolvableConfiguration") {
    resolutionStrategy.deactivateDependencyLocking()
}
```

Đoạn này là **mảnh ghép**, chỉ dùng khi configuration có tên đó đã được tạo và bạn có lý do hợp lệ để bỏ locking. Tránh vô hiệu hóa production runtimeClasspath chỉ để build đang lỗi có thể chạy: điều đó giấu đi sai lệch cần kiểm tra.

## 4. Ví dụ chạy được: ứng dụng Java 17 với lockfile

Để thấy trọn vòng đời **tạo → kiểm tra → cập nhật**, dùng một project Java độc lập, một external dependency đã có trên Maven Central và Gradle Wrapper. Ví dụ dùng **version cố định ban đầu**; locking vẫn hữu ích vì nó lưu graph được phân giải và giúp kiểm soát thay đổi. Phần sau sẽ bàn về dynamic version selectors.

### 4.1. Cấu trúc thư mục

```text
dependency-locking-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/...
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
```

Cần Gradle Wrapper hợp lệ, JDK tương thích với Gradle version đang sử dụng và Java 17 toolchain sẵn có hoặc có thể được provision theo cấu hình môi trường. Cần internet hoặc Gradle cache phù hợp để tải Commons Lang từ Maven Central.

### 4.2. Tệp `settings.gradle.kts`

```kotlin
rootProject.name = "dependency-locking-demo"
```

### 4.3. Tệp `build.gradle.kts` — đầy đủ

```kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.16.0")
}

dependencyLocking {
    lockAllConfigurations()
}
```

Giải thích:

- `application` áp dụng Java plugin, thêm task `run` và các configurations cần thiết.
- `mavenCentral()` là nơi Gradle tra dependencies ngoài.
- Java toolchain chọn JDK dùng cho các task Java theo cấu hình build.
- `implementation(...)` đưa Commons Lang vào compile/runtime classpaths phù hợp.
- `lockAllConfigurations()` kích hoạt locking trên các project configurations, **không tự resolve chúng**.
- Chưa có `gradle.lockfile` thì phải thực hiện bước tạo lock state; ở chế độ mặc định, việc thiếu state mới không tự tạo lock nếu không có thao tác ghi.

### 4.4. Tệp `src/main/java/demo/Main.java`

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    public static void main(String[] args) {
        String text = StringUtils.capitalize("gradle");
        System.out.println("Hello " + text);
    }
}
```

`StringUtils.capitalize("gradle")` trả `"Gradle"`. Chương trình không cần `test` dependency hay annotation processor nên ví dụ tập trung vào một module bên ngoài.

### 4.5. Lệnh kiểm tra ban đầu

Linux/macOS:

```bash
./gradlew --version
./gradlew run --quiet
```

PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat run --quiet
```

Khi build hợp lệ, **stdout do Java Main tạo ra** là:

```text
Hello Gradle
```

`run` đang dùng dependencies đã resolve cho application runtime. Có thể có console output riêng từ Gradle hoặc cảnh báo của môi trường; hai từ `Hello Gradle` là kết quả cần xác minh từ Java source.

Chạy `run` lần đầu khi **chưa có lockfile** trong `DEFAULT` mode không có nghĩa khóa đã được viết. Phải dùng bước `--write-locks` để sinh state.

## 5. Tạo `gradle.lockfile` lần đầu bằng `--write-locks`

Từ root project ví dụ:

```bash
./gradlew dependencies --write-locks --console=plain
```

Trên Windows:

```powershell
.\gradlew.bat dependencies --write-locks --console=plain
```

Task `dependencies` là **báo cáo dependency graph**, không phải task compile; khi kết hợp `--write-locks` nó buộc resolve các configurations phù hợp và cho Gradle ghi trạng thái khóa của những configuration được resolve.

Sau khi lệnh thành công, kỳ vọng có tệp:

```text
dependency-locking-demo/
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.lockfile
└── src/...
```

Trong ví dụ chỉ có một external module, một **đoạn minh họa** của `gradle.lockfile` có thể giống:

```properties
# This is a Gradle generated file for dependency locking.
# Manual edits can break the build and are not advised.
# This file is expected to be part of source control.
org.apache.commons:commons-lang3:3.16.0=compileClasspath,runtimeClasspath,testCompileClasspath,testRuntimeClasspath
empty=annotationProcessor,testAnnotationProcessor
```

**Không coi khối này là bản lockfile đảm bảo đúng từng dòng** cho mọi version Gradle/Java plugin. Danh sách configurations được ghi và dòng `empty` phụ thuộc configurations thực sự được giải quyết và có bật locking; thứ tự các entries/configurations được Gradle sắp xếp để dễ diff. Hãy đọc **file thật được Gradle tạo** trong project.

### Cách đọc từng dòng

Một dòng dạng:

```text
group:artifact:version=configuration1,configuration2
```

nghĩa là artifact `group:artifact:version` có trong **resolved graph** của các configurations được liệt kê. Một dòng `empty=annotationProcessor,testAnnotationProcessor` nói các configurations ấy được ghi nhận là **không có external modules** trong resolution đó.

Không nên sửa `empty=` bằng tay để cố làm configuration “hợp lệ”, cũng không nên tự gõ module version trong lockfile. **Gradle là nơi sinh và cập nhật trạng thái khóa.**

### Chưa thấy lockfile thì kiểm tra gì?

- `dependencyLocking { lockAllConfigurations() }` đã được áp dụng đúng **project** chưa?
- Task vừa chạy có thực sự resolve một configuration **có khóa** hay không?
- Bạn đang ở root project nào? Với multi-project, lockfile có thể nằm ở **thư mục của subproject**.
- Lệnh có thất bại trong quá trình resolution không? Gradle **không ghi lock state nếu build thất bại**.
- Dùng `dependencies --configuration runtimeClasspath --write-locks` để kiểm tra riêng một configuration khi cần, nhưng nhớ cách đó **không khóa luôn tất cả configurations khác**.

**Điều không nên làm:** tạo một file `gradle.lockfile` rỗng bằng tay rồi coi như đã khóa. File có định dạng và semantics cụ thể, phải được tạo qua quá trình resolution.

## 6. `--write-locks` chỉ lưu những configurations đã được resolve

Đây là một bẫy rất thường gặp. `--write-locks` **không biến mọi dependency declaration thành entry** nếu configuration không được resolve trong lượt chạy.

Ví dụ:

```bash
./gradlew compileJava --write-locks
```

Lệnh này có thể ghi lock state cho **compileClasspath** và các configurations khác được Gradle thực sự yêu cầu, nhưng **không bảo đảm runtimeClasspath, testRuntimeClasspath hoặc annotationProcessor của các source sets khác đều được resolve**.

Tương tự:

```bash
./gradlew dependencies --configuration runtimeClasspath --write-locks
```

chỉ chủ động xem/resolve runtimeClasspath; nếu sau đó bật `STRICT` cho test configurations mà chưa tạo state tương ứng, build có thể fail khi test cần resolve một cấu hình chưa có khóa.

### Cách khuyến nghị cho một Java project

```bash
./gradlew dependencies --write-locks
```

Khi dùng Java plugin/Gradle CLI bình thường, task `dependencies` xem nhiều **resolvable configurations** trong project đó. Nhưng đừng suy từ tên task rằng **mọi** custom configuration/variant được plugin nội bộ tạo ra cũng luôn được giải. Với những configuration đặc biệt, hãy chỉ định:

```bash
./gradlew dependencies --configuration someConfiguration --write-locks
```

**Lưu ý:** tên `someConfiguration` chỉ là placeholder; thay bằng một resolvable configuration tồn tại thật.

### Tránh resolve tất cả configurations tùy tiện

Một số ecosystems có configurations chỉ hợp lệ trên một hệ điều hành, một kiến trúc CPU hoặc môi trường có toolchain nhất định. Việc ép resolve mọi configuration có thể dẫn đến lỗi không liên quan. Hãy chọn các configurations **thực sự dùng trong build/CI** và thiết kế quy trình khóa phù hợp.

Nếu cần custom task để resolve nhiều configurations, tài liệu Gradle có ví dụ `resolveAndLockAll`; phải cân nhắc Configuration Cache vì truy cập `configurations` trực tiếp từ task action không tương thích với mô hình isolated task actions. Trong phần lớn Java project, báo cáo `dependencies` và các task thực tế đã đủ.

## 7. Kiểm tra `gradle.lockfile` bằng Git ngay sau khi tạo

Với repository Git:

```bash
git status --short
git diff -- gradle.lockfile
```

Khi file **chưa được Git track**, `git diff -- gradle.lockfile` có thể **không hiển thị nội dung** dù file đã có. `git status --short` sẽ cho bạn biết đó là file mới `?? gradle.lockfile`. Sau khi kiểm tra nội dung và quyết định commit:

```bash
git add gradle.lockfile
git diff --cached -- gradle.lockfile
```

Thực hiện `git commit` theo quy trình của nhóm; đây là hướng dẫn, bài học không tự commit.

**Lockfile nên được commit vào source control.** Nếu chỉ có ở máy developer mà không có trên CI, bạn không có cùng baseline để kiểm tra các dependencies. Đừng thêm `gradle.lockfile` vào `.gitignore` theo thói quen bỏ qua mọi file chứa chữ “lock”.

Không nên commit những tệp khác chỉ vì `git add .` khi repository có secrets hoặc artifacts chưa được kiểm tra. Với bài demo, `git add gradle.lockfile` là lựa chọn rõ phạm vi.

## 8. Chạy build với lock state đã có: điều gì được kiểm tra?

Sau khi tạo lockfile, chạy:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew clean run
```

Trong `DEFAULT` lock mode, khi Gradle resolve một configuration **đã có lock state**, nó áp dụng phiên bản khóa và kiểm tra sự nhất quán:

1. Các module/version đã khóa phải khớp với resolved graph tương ứng.
2. Một locked module bị thiếu hoặc version không phù hợp sẽ dẫn đến lỗi resolution.
3. Resolved graph không được có thêm external dependencies ngoài lock state tương ứng.
4. Nếu khai báo trực tiếp phiên bản **không tương thích** với locked version, dependency constraints có thể xung đột.

Bởi thế, build thành công ở một configuration đã khóa chứng tỏ **resolution của configuration đó tuân theo lock state**. Nó **không chứng minh** những configuration chưa được resolve trong lượt build cũng đã được kiểm tra.

### Ví dụ đối chiếu declared và locked version

Giả sử lockfile giữ:

```text
org.apache.commons:commons-lang3:3.16.0=...
```

Bạn sửa trong DSL thành:

```kotlin
implementation("org.apache.commons:commons-lang3:3.17.0")
```

Nhưng **chưa cập nhật lockfile**. Trong Gradle locking mặc định, locked `3.16.0` hoạt động như strict constraint; khai báo trực tiếp `3.17.0` yêu cầu một bản mới hơn, dẫn đến xung đột resolution. Đó là **cơ chế bảo vệ**, không phải Gradle “quên tải bản mới”.

Sửa đúng bằng thao tác cập nhật khóa đã được review, không xóa lockfile hoặc tắt locking để vượt lỗi.

Một tình huống ngược lại đáng nhớ: nếu khai báo trực tiếp yêu cầu bản `3.16.0` nhưng lockfile chứa `3.17.0`, Gradle có thể giữ bản `3.17.0` do constraint của lockfile vẫn thỏa yêu cầu phiên bản thấp hơn. Đây là lý do phải kiểm tra **resolved version**, không chỉ nhìn `implementation("...")`.

## 9. Cập nhật toàn bộ lock state bằng `--write-locks`

Khi bạn chủ động muốn giải resolution theo các rules hiện tại (ví dụ mới đổi dependency declarations, nâng constraints hoặc muốn chọn bản mới cho dynamic selector), dùng:

```bash
./gradlew dependencies --write-locks
```

**Tác dụng:** những configurations thực sự được resolve sẽ ghi lại lock state mới. Với các configurations được resolve, trạng thái khóa cũ có thể bị cập nhật/thay thế.

**Không nhầm với lệnh chỉ kiểm tra.** `--write-locks` là thao tác **có thể ghi file trong repository**. Nếu chỉ cần kiểm tra build/CI, không truyền flag này.

Đối với thay đổi lớn, quy trình nên là:

1. Sửa `build.gradle.kts` hoặc `libs.versions.toml`/dependency constraints theo mục tiêu.
2. Chạy `./gradlew dependencies --write-locks` ở project liên quan.
3. So `git diff` và kiểm tra version nào đổi, dependency transitive nào thêm/bỏ.
4. Chạy compile, test, runtime smoke tests và kiểm tra security/licensing nếu cần.
5. Commit **cả thay đổi declaration lẫn lockfile** trong một pull request có lý do nâng cấp.

**Đừng chạy `--write-locks` theo thói quen mỗi lần CI build.** Việc đó có thể ghi đè baseline thay vì kiểm tra drift và làm một dependency update không được duyệt thành “kết quả mới được chấp nhận”.

## 10. Cập nhật **có chọn lọc** bằng `--update-locks`

Gradle có CLI flag:

```bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3
```

`--update-locks` nhận danh sách **`group:name`**, không nhận `group:name:version`; có thể phân cách nhiều modules bằng dấu phẩy. Nó **ngầm bao gồm việc ghi lock state** như `--write-locks`, nhưng dùng khóa hiện có để **giữ những module khác** ở version đã khóa, ngoại trừ các module được phép update và thay đổi bắt buộc bởi các resolution rules.

Ví dụ nâng Commons Lang trong demo:

**Bước A — sửa khai báo:**

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

**Bước B — chỉ định update module:**

```bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3
```

**Bước C — kiểm tra:**

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew clean run
```

**Bước D — review lockfile:**

```bash
git diff -- build.gradle.kts gradle.lockfile
```

Trong ví dụ, lock entry của Commons Lang phải chuyển từ `3.16.0` sang `3.17.0` ở những configurations đã được resolve/cập nhật tương ứng. Với dependencies khác, Gradle cố giữ khóa cũ nhưng **các transitive modules vẫn có thể bị ảnh hưởng** nếu resolution constraints bắt buộc — không hứa rằng chỉ đúng một dòng thay đổi trong mọi graph.

### Nhiều modules trong một lệnh

```bash
./gradlew dependencies --update-locks org.slf4j:slf4j-api,org.apache.commons:commons-lang3
```

Các pattern wildcard Gradle cho phép khi cập nhật:

```text
org.apache.commons:*
*:guava
org.springframework.spring*:spring*
```

Dùng wildcard khi thực sự muốn một **nhóm** modules được phép update; với PR bảo trì nhỏ, chọn group:name cụ thể thường làm diff dễ review hơn.

### Tại sao `--update-locks` vẫn có thể lỗi?

- Module được target không xuất hiện trong graph của configuration đang resolve; lệnh không có gì để nâng cho configuration đó.
- Build khai báo hoặc constraints **không cho phép** version mới.
- Repository không có artifact/metadata tương ứng.
- Một capability conflict, variant mismatch hoặc dependency verification failure vẫn tồn tại.
- Một module liên quan bị khóa ở version không tương thích và các resolution rules không thể đáp ứng tất cả constraints.

Vì thế, selective update **không phải lệnh ép mọi dependency thành phiên bản bất kỳ**. Nó chỉ cho phép Gradle giải lại theo các rules hiện có trong phạm vi update.

## 11. Quy trình demo “khóa cũ gây lỗi, sau update thì pass”

Sau khi đã có `gradle.lockfile` lưu `3.16.0`:

1. Đổi version trong `build.gradle.kts` từ `3.16.0` thành `3.17.0`.
2. Chạy `./gradlew dependencies --configuration runtimeClasspath` **không có** `--write-locks`/`--update-locks`. Kỳ vọng Gradle báo conflict giữa version mới và lock cũ ở configuration đang được kiểm tra.
3. Chạy `./gradlew dependencies --update-locks org.apache.commons:commons-lang3`. Vì task `dependencies` có thể resolve nhiều configurations trong **project hiện tại**, Gradle cập nhật các lock entries tương ứng.
4. Chạy lại `./gradlew dependencies --configuration compileClasspath` và `--configuration runtimeClasspath` không có update flags.
5. Chạy `./gradlew clean run --quiet`, chương trình vẫn in `Hello Gradle`.
6. Review `git diff -- build.gradle.kts gradle.lockfile` và commit hai thay đổi cùng nhau.

Điều kiểm chứng được là: **trước update, build bị chặn khi declared version không còn tương thích với lock; sau update hợp lệ, resolved version và lock state khớp nhau**. Không cần phụ thuộc vào một text lỗi chính xác vì thông báo chi tiết có thể khác theo Gradle version.

Không nên cố test xung đột bằng một module vô danh/tọa độ chưa từng tồn tại trên repository, vì lúc đó lỗi có thể là **artifact not found**, không phải locking conflict.

## 12. Chế độ `DEFAULT`, `STRICT` và `LENIENT`

Gradle cung cấp `LockMode`. Các mode này khác nhau về cách xử lý lock state thiếu hoặc dependency graph thay đổi.

| LockMode | Khi đã có lock state | Khi configuration bật locking nhưng chưa có state | Phù hợp |
| --- | --- | --- | --- |
| `DEFAULT` | Pin versions và kiểm tra graph phải khớp lock state | Không yêu cầu phải tồn tại state cho mọi configuration | Workflow thông thường sau khi đã tạo lockfile |
| `STRICT` | Giữ kiểm tra như DEFAULT | **Fail resolution** nếu configuration locked không có state | CI/repository yêu cầu mọi locked configuration phải có baseline |
| `LENIENT` | Giữ dynamic versions trong phạm vi lock nhưng cho phép thay đổi graph linh hoạt hơn | Không có cùng mức enforcement với STRICT | Thử nghiệm/nightly có chủ đích, không nên làm mặc định cho release |

Theo tài liệu Gradle, `LENIENT` có thể cho phép **thêm/bớt dependencies** và thay đổi transitive versions trong những tình huống mà DEFAULT sẽ fail; nó **không** mang lại độ nghiêm ngặt của STRICT.

### Khai báo mode trong Kotlin DSL

Ví dụ bổ sung vào `build.gradle.kts`:

```kotlin
import org.gradle.api.artifacts.dsl.LockMode

// ... plugins/repositories/dependencies ở phần còn lại của file.

dependencyLocking {
    lockAllConfigurations()
    lockMode.set(LockMode.STRICT)
}
```

`LockMode` thuộc `org.gradle.api.artifacts.dsl`. Khi dùng nguyên đoạn trong file, đặt `import` ở **đầu file**, trước `plugins`. Kotlin DSL hiện đại có thể dùng cú pháp assignment `lockMode = LockMode.STRICT` cho Gradle `Property`; cách `.set(...)` là rõ ràng về kiểu.

**Thứ tự triển khai an toàn:** bật locking, **tạo đủ lock state**, commit file rồi mới dùng STRICT để enforce trên mọi configuration cần kiểm tra. Nếu bật STRICT ngay nhưng chạy `dependencies` không resolve được một configuration cần khóa hoặc file bị thiếu, lần resolution liên quan sẽ fail — đúng với mục tiêu STRICT.

### Không nên dùng `LENIENT` để “sửa lỗi”

Nếu một nâng cấp dependency làm DEFAULT fail, giải pháp bình thường là **review thay đổi và cập nhật lockfile**. Đổi `lockMode` sang LENIENT có thể cho phép drift mà bạn định khóa ngay từ đầu.

Tương tự, STRICT không làm các configurations được lock **tự động resolve**. Nó chỉ yêu cầu lock state tồn tại **khi một configuration đã bật locking được resolve**.

## 13. Multi-project: mỗi project có lockfile riêng

Xét:

```text
repo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.lockfile              # Nếu root có locked/resolved dependencies
├── api/
│   ├── build.gradle.kts
│   └── gradle.lockfile          # Trạng thái của :api
└── app/
    ├── build.gradle.kts
    └── gradle.lockfile          # Trạng thái của :app
```

Gradle mặc định dùng **một `gradle.lockfile` cho mỗi project/subproject**, chứ không phải một file cho toàn repository. Nếu `:app` phụ thuộc `:api`, mỗi project có thể có những resolvable configurations và external transitive dependencies khác nhau, vì vậy trạng thái khóa cũng khác.

Một `build.gradle.kts` của subproject:

```kotlin
plugins {
    `java-library`
}

repositories {
    mavenCentral()
}

dependencyLocking {
    lockAllConfigurations()
}
```

Đây là **mảnh ghép minh họa**; không bắt buộc các subprojects đều dùng `java-library`. Điểm quan trọng là locking được áp dụng **đúng project** có configurations cần khóa.

### Cảnh báo: root `dependencies` không bao trùm mọi subproject

```bash
./gradlew dependencies --write-locks
```

thường chạy task `dependencies` của **root project**, không tự chạy báo cáo cho toàn bộ subprojects. Trong repository nhiều module, muốn tạo/cập nhật lock state cho cả `:api` và `:app`, yêu cầu rõ:

```bash
./gradlew :api:dependencies :app:dependencies --write-locks
```

Hoặc chạy lần lượt:

```bash
./gradlew :api:dependencies --write-locks
./gradlew :app:dependencies --write-locks
```

Dùng đường dẫn tuyệt đối `:api:dependencies` thay vì phụ thuộc vào cơ chế task selector từ thư mục làm việc.

Khi chỉ nâng một dependency ở `:app`, có thể chọn:

```bash
./gradlew :app:dependencies --update-locks org.apache.commons:commons-lang3
```

Nhưng nếu `:api` cũng resolve dependency đó và cần update lock state, phải giải/ghi lại `:api` có chủ đích. Một file lock trong `:app` không tự sửa file lock của `:api`.

### Included builds, `buildSrc` và build logic

Composite builds/included builds và `buildSrc` có thể có **cấu trúc project/configuration riêng**. Không được nghĩ lockfile của root build tự quản lý mọi external dependency của build logic; hãy xác định build nào thực sự resolve classpath nào và áp dụng locking phù hợp trong build tương ứng.

Đặc biệt, `plugins { ... }` và buildscript classpaths có cơ chế resolution riêng so với main source set dependencies. Nếu mục tiêu là khóa plugin/build logic, phải đọc đúng phần Gradle plugin management và buildscript locking thay vì chỉ bật `lockAllConfigurations()` ở `:app`.

## 14. Khóa riêng buildscript classpath

Một số legacy/convention build scripts dùng:

```kotlin
buildscript {
    repositories {
        mavenCentral()
    }

    dependencies {
        classpath("com.example:legacy-build-plugin:1.0")
    }

    configurations.classpath {
        resolutionStrategy.activateDependencyLocking()
    }
}
```

Đây là **mảnh ghép minh họa**: `com.example:legacy-build-plugin:1.0` không phải artifact được xác nhận tồn tại; chỉ dùng với plugin thực tế tương thích. Ý nghĩa là: `buildscript.configurations.classpath` cần được bật locking **riêng** nếu muốn khóa classpath của chính build script.

File lock tương ứng thường có tên:

```text
buildscript-gradle.lockfile
```

Khác với project dependency state thông thường:

```text
gradle.lockfile
```

Khi muốn ghi buildscript lock state, phải kích hoạt giải buildscript configuration với `--write-locks`; một lệnh dành cho source dependencies không nhất thiết giải/ghi đủ mọi plugin-resolution route.

**Giới hạn:** locking project configurations không đồng nghĩa toàn bộ plugin versions trong `plugins { }` đã được khóa giống main dependency graph. Hãy cố định plugin versions trong `settings.gradle.kts`/version catalog và kiểm tra cơ chế plugin verification/metadata thích hợp.

## 15. File format: mỗi entry nói điều gì?

Một lockfile Gradle hiện đại có dạng:

```text
# This is a Gradle generated file for dependency locking.
# Manual edits can break the build and are not advised.
# This file is expected to be part of source control.
com.google.guava:guava:33.2.1-jre=compileClasspath,runtimeClasspath
org.apache.commons:commons-lang3:3.17.0=compileClasspath,runtimeClasspath
empty=annotationProcessor
```

Đây là **ví dụ format**, không phải output của project demo vì demo không dùng Guava. Các dòng không phải câu lệnh Gradle DSL; đó là **dữ liệu khóa**:

- `com.google.guava:guava:33.2.1-jre`: module và phiên bản đã được chọn.
- `=compileClasspath,runtimeClasspath`: các configurations chứa module đó trong lock state.
- `empty=annotationProcessor`: một configuration được ghi nhận là không có external modules.
- Header ghi chú đây là file Gradle tạo và cần đưa vào source control.

Lockfile thường sắp xếp các dependencies và configurations theo thứ tự để diff dễ review. **Không tự đổi format, xóa dòng `empty` hoặc sửa version bằng tay**. Một thao tác manual edit có thể khiến lockfile không khớp resolution graph và gây lỗi khó đoán.

### Legacy lockfiles cần lưu ý khi nâng Gradle

Các Gradle rất cũ từng lưu **mỗi locked configuration một file** ở `gradle/dependency-locks/`. Gradle 6.4+ dùng định dạng **một lockfile mỗi project**, nhưng vẫn hỗ trợ đọc dạng cũ trong giai đoạn chuyển tiếp.

Theo hướng dẫn nâng cấp Gradle 9.x, việc đọc **legacy dependency lock files** đã bị deprecate và **Gradle 10 sẽ không đọc chúng**. Khi bảo trì repository cũ, dùng `--write-locks`/`--update-locks` để chuyển dần sang định dạng mới; phải resolve **đủ các configurations** cần migrate, không chỉ một task tình cờ.

Không tự xóa các lockfiles cũ trước khi đã tạo được và xác minh file mới cho tất cả configurations quan trọng.

## 16. Lockfile tùy biến vị trí: khi nào mới nên làm?

Mặc định `gradle.lockfile` ở root **của từng project** giúp người khác dễ biết phải tìm ở đâu. Gradle cho phép cấu hình vị trí lockfile khi có lý do hợp lệ, ví dụ build có nhiều Scala binary versions cần các bộ dependencies khác nhau.

Đoạn bổ sung minh họa:

```kotlin
val binaryFlavor = "standard"

dependencyLocking {
    lockFile = file("locking/gradle-$binaryFlavor.lockfile")
}
```

Khi dùng thật, mỗi project/buildscript cần lockfile riêng để tránh ghi đè state của nhau. Đừng thay đường dẫn theo timestamp hay dữ liệu ngẫu nhiên: làm vậy phá tính ổn định và khiến CI khó biết file nào phải được commit.

Các build profiles có lock states riêng cần được định nghĩa thật rõ. Một `gradle.lockfile` đơn nhất chỉ đại diện cho những configurations và resolution inputs đã được ghi; nếu cùng project thay đổi dependencies theo `-Penv=prod`/OS/feature flags, cần thiết kế locking để không ghi đè vô tình giữa các môi trường không tương thích.

## 17. `ignoredDependencies`: linh hoạt nhưng ảnh hưởng tính tái lập

Gradle cho phép bỏ một số dependency khỏi lock state:

```kotlin
dependencyLocking {
    lockAllConfigurations()
    ignoredDependencies.add("com.example.internal:*")
}
```

Đây là **ví dụ chính sách giả định**. Các module khớp pattern này sẽ không được ghi/kiểm tra theo lock state, dù dependencies transitive của chúng vẫn có thể được ghi nếu không bị ignore riêng.

Điều cần hiểu:

- Pattern dùng `group:name`; wildcard có thể ở cuối group/name.
- `*:* ` không phải cú pháp được chấp nhận để bỏ khóa toàn bộ.
- Các ignored dependencies được áp dụng theo project scope đến các configurations đã bật khóa.
- Bỏ qua một dependency không có nghĩa bỏ qua transitive dependencies của nó.
- Tính reproducibility giảm nếu một dependency không được khóa có version động.

Nếu mục tiêu của bạn là các builds nhất quán để phát hành, **tránh ignore cho dependency cốt lõi**. Đừng dùng `ignoredDependencies` như cách nhanh để làm mất một dòng đang gây conflict; cần giải thích tác động và xin review.

## 18. Dependency locking khác Dependency Verification

Hai khái niệm này thường cùng xuất hiện nhưng **đảm nhiệm câu hỏi khác nhau**:

| Cơ chế | Câu hỏi trả lời | File thường gặp |
| --- | --- | --- |
| Dependency locking | **Những phiên bản module nào được phép resolve?** | `gradle.lockfile` trong từng project |
| Dependency verification | **Artifact/metadata tải được có đúng checksum/chữ ký đã tin cậy không?** | `gradle/verification-metadata.xml` |
| Version catalog | **Nhóm khai báo version/alias như thế nào?** | `gradle/libs.versions.toml` |
| Gradle Wrapper | **Dùng Gradle distribution/version nào?** | `gradle/wrapper/gradle-wrapper.properties` |
| Dependency cache | **Đã tải artifact/metadata nào ở máy này?** | Gradle user home cache, không thay thế lockfile |

Giả sử module bị xuất bản lại với **cùng tọa độ và version nhưng bytes khác**. Dependency locking có thể vẫn hài lòng vì module version không đổi. **Dependency verification** mới là lớp bảo vệ checksum/signature nếu được cấu hình đúng.

Để khởi tạo dependency verification metadata, Gradle có lệnh như:

```bash
./gradlew --write-verification-metadata sha256 dependencies
```

Nó tạo/cập nhật `gradle/verification-metadata.xml` khi các artifacts/metadata được resolve qua Gradle. **Kiểm tra kỹ file đó trước khi commit:** việc bootstrap checksum ban đầu **tin vào những artifact đang có ở repository**, nên nếu đã bị thay bằng phiên bản độc hại thì ghi checksum tự động không làm artifact trở nên đáng tin.

**Không nhầm CLI:**

- `--write-locks`: cập nhật phiên bản module đã resolve vào `gradle.lockfile`.
- `--update-locks g:a`: cập nhật có chọn lọc một số module trong khóa.
- `--write-verification-metadata sha256`: ghi checksum artifact/metadata để phục vụ verification.

Một repository có thể dùng **cả khóa và xác minh** để bảo vệ tốt hơn; hai file phải được review theo quy trình phù hợp.

## 19. Dynamic versions và changing dependencies: cảnh báo quan trọng

Ví dụ dynamic selector:

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.+")
}
```

Sau khi có lockfile, dynamic selector này được ràng buộc vào selected version theo lock state trong các configurations đã khóa. Để nâng version có chủ đích, chạy `--update-locks org.apache.commons:commons-lang3` hoặc toàn bộ `--write-locks`, rồi review.

Với một dependency `1.0-SNAPSHOT` hoặc dependency được đánh dấu `changing`, nhà phát hành có thể thay **artifact content** nhưng giữ group/name/version. Lockfile chỉ khóa **tọa độ/version**, không khóa nội dung bytes của changing module. Gradle docs cảnh báo khi ghi lock state chứa changing dependencies vì tính tái lập không được đảm bảo.

**Khuyến nghị:**

1. Với production releases, ưu tiên versions rõ ràng và tránh changing modules trừ khi thật sự cần.
2. Nếu cần dynamic versions cho thử nghiệm, khóa lại trong CI/release workflow và cập nhật theo PR riêng.
3. Dùng dependency verification và repository policies khi cần tính toàn vẹn/supply-chain safety.
4. Không suy rằng `--refresh-dependencies` tự cập nhật lockfile. Flag này **refresh trạng thái dependency metadata/cache**, không phải lệnh viết khóa; khi khóa hợp lệ vẫn ràng buộc version selection.
5. `--offline` không biến một artifact chưa có trong local Gradle cache thành available; khóa phiên bản và cache tải artifact là hai vấn đề khác nhau.

## 20. Cách xác minh lockfile trong CI

Mục tiêu CI là **phát hiện lệch**, không âm thầm tạo khóa mới. Một pipeline Java đơn giản có thể chạy:

```bash
./gradlew dependencies --console=plain
./gradlew clean test --console=plain
./gradlew run --quiet
```

Các lệnh giả định project demo dùng Application plugin và `Main` có sẵn. `dependencies` chủ động kiểm tra dependency graphs của project hiện tại; compile/test/run kiểm tra hành vi thực. **Không thêm `--write-locks` vào các bước này**, vì như vậy CI có thể cho phép lock state bị viết lại và che đi sai lệch.

Nếu muốn chặt chẽ hơn, sau khi khóa đầy đủ các configurations cần thiết và đưa file vào Git, bật:

```kotlin
import org.gradle.api.artifacts.dsl.LockMode

dependencyLocking {
    lockAllConfigurations()
    lockMode.set(LockMode.STRICT)
}
```

Nhớ đặt `import` ở đầu file, không chèn giữa plugins. STRICT giúp CI fail khi một configuration có locking nhưng thiếu lock state.

### Kiểm tra Git có file khóa trong repo

```bash
git status --short
git ls-files gradle.lockfile
```

Trong multi-project, các lockfiles con có thể được liệt kê bằng các pattern hoặc lệnh liệt kê file của Git tùy cấu trúc repository. Điều cần xác nhận là **đúng lockfiles đã được commit**, không chỉ tồn tại trong workspace local.

`git diff --exit-code -- gradle.lockfile` có thể hữu ích để chắc rằng một bước **không được phép ghi file** đã không sửa một file tracked. Nhưng nó **không thay thế verification dependency graph**, và không phát hiện mọi file mới untracked. Lệnh đúng để kiểm tra compliance là **Gradle resolution khi bật locking**, chứ không phải chỉ xem Git diff.

### Multi-project CI

Thay vì chỉ chạy root:

```bash
./gradlew :api:dependencies :app:dependencies --console=plain
./gradlew :api:build :app:build --console=plain
```

Chỉ ví dụ nếu các subprojects `:api`, `:app` tồn tại và có các tasks đó. Với repository nhiều plugins/custom source sets, lựa chọn task giúp resolve toàn bộ các configurations release/test quan trọng. Nếu CI không bao giờ resolve một configuration, nó không thể kiểm tra lock state của configuration đó bằng cách tình cờ chạy task khác.

## 21. Quy trình review PR nâng dependency chuẩn

Một pull request nâng dependencies tốt nên có các phần:

1. **Lý do cập nhật:** lỗi bảo mật, bug fix, compatibility hoặc chủ đích nâng tính năng.
2. **Thay đổi DSL/catalog:** những phiên bản trực tiếp được khai báo mới.
3. **Lệnh update dùng:** `--update-locks g:a` khi chọn lọc hoặc `--write-locks` khi cập nhật có phạm vi rộng.
4. **Lockfile diff:** module nào thay version, xuất hiện hoặc biến mất, có transitive modules nào thay đổi bất ngờ không?
5. **Phạm vi projects/configurations:** root, `:app`, `:lib`, test, annotationProcessor, buildscript nếu liên quan.
6. **Tương thích:** compile/test/runtime checks trên JDK và Gradle Wrapper phù hợp.
7. **An toàn:** dependency verification, nguồn artifact, licensing/vulnerability review khi chính sách yêu cầu.
8. **Không có thay đổi ngoài phạm vi:** lockfile khác không bị sửa tình cờ, source/artifacts/secrets không lẫn vào commit.

Lập luận quan trọng: **“Lockfile đổi vì tôi chạy build” không phải lý do đủ để chấp nhận dependency upgrade.** Cần giải thích tại sao các versions được chọn mới là chủ đích.

Một cách tổ chức bảo trì dễ review là **mỗi PR một nhóm nâng cấp nhỏ**, tránh trộn nâng Gradle Wrapper/JDK/plugin/JUnit và hàng chục transitive versions khi không có nhu cầu. Với cập nhật bảo mật khẩn cấp, selective update cùng test phù hợp có thể giảm nguy cơ.

## 22. Những thông báo lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và khắc phục |
| --- | --- | --- |
| `Cannot find a version of ...` sau khi đổi declared version | Lock state vẫn ràng buộc version cũ không tương thích | Kiểm tra `dependencyInsight`, rồi cập nhật khóa có chủ đích |
| Báo lock state thiếu trong `STRICT` mode | Configuration đang được resolve chưa có lock state | Chạy `dependencies --write-locks`/task liên quan để tạo state, review và commit |
| Resolved graph chứa dependency mới ngoài lock | Build script/plugin/metadata thêm dependency, lockfile chưa update | Xác định nguồn mới, cập nhật có review thay vì tắt locking |
| Lockfile còn module mà resolution không có | Dependency bị gỡ/loại hoặc graph thay đổi | Chạy update lock với scope đúng và xem diff, không xóa tay |
| `--write-locks` không tạo file | Không có resolvable configuration locked được resolve, hoặc lệnh fail | Kiểm tra plugin, configuration, command scope và errors |
| `--write-locks` ghi root nhưng không ghi subproject | Chỉ chạy root `dependencies` | Chạy `:subproject:dependencies --write-locks` cụ thể |
| Sau selective update vẫn có version khác đổi | Transitive constraints/version conflict buộc thay đổi liên quan | So `dependencyInsight` và diff, kiểm tra compatibility |
| `--update-locks g:a` không đổi gì | Version declaration/constraints không cho phép bản mới hoặc configuration không chứa module | Kiểm tra module và resolved graph, chọn đúng configuration |
| `--refresh-dependencies` không nâng bản đã khóa | Refresh cache không thay lock state | Dùng `--update-locks`/`--write-locks` nếu muốn nâng |
| CI pass dù thiếu lockfile ở một cấu hình | DEFAULT không fail nếu configuration chưa có state, hoặc CI chưa resolve config | Dùng STRICT sau khi tạo khóa đầy đủ và test đúng configurations |
| SNAPSHOT có nội dung khác dù version không đổi | Locking không khóa bytes | Tránh changing deps cho release; dùng verification |
| Dependency verification fail nhưng lockfile vẫn đúng | Artifact checksum/signature không khớp metadata | Điều tra nguồn artifact, không tắt verification tùy tiện |
| Build chạy offline không tải được dependency khóa | Artifact chưa có local cache | Cấp cache hoặc online resolution đúng repository |
| Legacy `gradle/dependency-locks/` gây cảnh báo khi nâng Gradle 9 | Định dạng lock cũ đang bị deprecate | Migrate sang per-project `gradle.lockfile`, resolve đầy đủ |
| `implementation` được khóa nhưng buildscript plugin vẫn thay version | Project locking không bao phủ buildscript/plugin management mặc định | Khóa/điều phối plugin versions riêng theo đúng Gradle mechanism |
| Project dependency không có dòng GAV trong lock như external module | Locking mô hình hóa resolved external modules theo configuration | Xem Gradle project dependencies và các external transitives thật sự resolve |
| Version Catalog đổi nhưng lockfile chưa khác | Configuration chưa resolve hoặc locked version vẫn thỏa constraint | Xem selected versions và nhiệm vụ đang chạy |
| `empty=...` bị xem là rác | Đây là lock state cho configuration không có module | Không xóa tay; để Gradle quản lý |

**Đừng đoán nguyên nhân chỉ từ một câu lỗi rút gọn.** Dùng `dependencies --configuration ...`, `dependencyInsight`, log `--info` hoặc `--stacktrace` khi cần. Khi lỗi liên quan verification, xem báo cáo verification riêng.

## 23. Cách phân biệt các lệnh thường bị dùng sai

| Lệnh | Việc thực hiện | Có chủ động ghi lockfile? |
| --- | --- | --- |
| `./gradlew dependencies` | Hiển thị graphs và kiểm tra khóa hiện có cho configurations được resolve | **Không**, nếu không kèm write flags |
| `./gradlew dependencies --write-locks` | Resolve rồi tạo/cập nhật trạng thái khóa | **Có** |
| `./gradlew dependencies --update-locks g:a` | Cho phép cập nhật một module được chọn, ghi trạng thái mới | **Có**, ngầm write locks |
| `./gradlew compileJava` | Biên dịch Java source, resolve compile dependencies cần thiết | **Không** nếu không kèm write flags |
| `./gradlew test` | Biên dịch/chạy test và resolve dependencies liên quan | **Không** nếu không kèm write flags |
| `./gradlew dependencies --refresh-dependencies` | Refresh resolution/cache metadata khi cần | **Không** cập nhật lock state |
| `./gradlew dependencies --offline` | Dùng metadata/artifacts cache hiện có | **Không**, và có thể fail nếu cache thiếu |
| `./gradlew dependencies --write-verification-metadata sha256` | Sinh checksum metadata để xác minh artifact | **Không phải** viết dependency lockfile |

Lưu ý: `--write-locks` và `--update-locks` là **các Gradle CLI options**, không phải tên của Gradle tasks. Đừng cố viết `tasks.register("writeLocks")` chỉ để có một lệnh giống đó; bản thân CLI đã có cơ chế chính thức.

## 24. Bài tập thực hành

### Bài tập 1: Đoán file khóa

Trong project Java có `implementation("org.apache.commons:commons-lang3:3.16.0")`, kích hoạt `lockAllConfigurations()` rồi chạy:

```bash
./gradlew dependencies --write-locks
```

**Hỏi:** Tệp nào nên xuất hiện và được commit?

**Đáp:** `gradle.lockfile` tại thư mục **project hiện tại**. Nó liệt kê phiên bản Commons Lang đã resolve và các configurations tương ứng; có thể có `empty=...` cho cấu hình rỗng.

### Bài tập 2: Tăng declared version nhưng không update lock

Giữ lock Commons Lang 3.16.0, đổi declaration thành 3.17.0 rồi chạy:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

**Đáp:** Khi declared version mới không tương thích với locked constraint, Gradle sẽ báo resolution conflict. Đó là hành vi mong muốn giúp phát hiện upgrade chưa được duyệt.

### Bài tập 3: Update chọn lọc

Lệnh nào cho phép Commons Lang được nâng nhưng vẫn giữ các modules khác trong lock state nếu resolution rules cho phép?

```bash
./gradlew dependencies --update-locks org.apache.commons:commons-lang3
```

**Đáp:** Lệnh trên dùng group:name và ngầm ghi trạng thái khóa mới. Vẫn phải review transitive changes và kiểm tra đủ configurations của project.

### Bài tập 4: Root và subproject

Có `:api` và `:app` đã bật locking. Chạy `./gradlew dependencies --write-locks` tại root có bảo đảm tạo hai subproject lockfiles không?

**Đáp:** Không. Phải yêu cầu các task của subprojects, ví dụ:

```bash
./gradlew :api:dependencies :app:dependencies --write-locks
```

### Bài tập 5: STRICT khác DEFAULT

Một configuration đã bật locking nhưng chưa có lock state. Khi được resolve, mode nào được thiết kế để fail vì thiếu state?

**Đáp:** `LockMode.STRICT`. DEFAULT không tự yêu cầu mọi locked configuration có state, nhưng vẫn dùng/kiểm tra state khi nó đã có.

### Bài tập 6: Thư viện bị republish cùng version

Một JAR đổi bytes nhưng group/name/version không đổi. Lockfile có tự báo lỗi checksum không?

**Đáp:** Không. Locking tập trung vào module versions, còn checksum/signature thuộc **Dependency Verification**.

### Bài tập 7: Tại sao không ghi lại lock trên CI mỗi lần?

**Đáp:** Vì CI nên kiểm tra **baseline đã commit**. Nếu chạy `--write-locks` tự động ở mỗi build, nó có thể âm thầm chấp nhận graph mới thay vì fail và yêu cầu review.

### Bài tập 8: Đọc dòng `empty=`

Dòng `empty=annotationProcessor` có nghĩa annotation processing bị tắt không?

**Đáp:** Không. Nó nói configuration đó **được resolve khi ghi lock và không có module dependencies**. Compiler/task annotation processing có thể còn bị ảnh hưởng bởi nhiều yếu tố khác; dòng `empty` không phải option tắt compiler feature.

### Bài tập 9: Dynamic version nhưng có lock

Build script khai báo `3.+`, khóa đã chọn `3.17.0`. Repository phát hành `3.18.0`. Gradle có tự nâng trong build bình thường không?

**Đáp:** Không đối với configuration đã khóa hợp lệ: lock state ràng buộc resolved version. Muốn nâng phải update lock có chủ đích.

### Bài tập 10: Bản lock ở một configuration

`runtimeClasspath` đã khóa, `testRuntimeClasspath` chưa được resolve. Chạy `./gradlew run` rồi thấy PASS. Có thể khẳng định tests cũng dùng lock state hợp lệ không?

**Đáp:** Không. Cần resolve/test đúng test configurations, và dùng STRICT nếu muốn bắt buộc state cho từng locked configuration.

## 25. Checklist cuối cùng

- [ ] Biết rõ project/configurations nào cần locking.
- [ ] Đã bật `lockAllConfigurations()` hoặc `activateDependencyLocking()` ở đúng project.
- [ ] Đã tạo lock state bằng `--write-locks` cùng các task/configurations thực sự cần resolve.
- [ ] Đã kiểm tra `gradle.lockfile` trong thư mục project/subproject đúng.
- [ ] Đã review nội dung các module versions, `empty=` và transitive changes.
- [ ] Đã commit lockfiles cùng source declarations được dùng để tạo chúng.
- [ ] CI chạy Gradle **không có write flags** để phát hiện drift.
- [ ] Đã cân nhắc `LockMode.STRICT` sau khi có đủ baseline.
- [ ] Khi upgrade có dùng `--update-locks group:name` hoặc `--write-locks` với review rõ.
- [ ] Không tự chỉnh lockfile bằng tay, không coi refresh cache là update.
- [ ] Không dùng locking để giả vờ xác minh bytes hoặc tính an toàn của dependency.
- [ ] Nếu dùng multi-project/buildscript/included build, đã rà **cả những lockfiles/configurations riêng**.
- [ ] Đã kiểm tra compile, test và runtime behavior sau nâng dependency.
- [ ] Nếu nâng Gradle 9.x/10, đã xem trạng thái **legacy lockfiles** và kế hoạch migrate.

## Tài liệu chính thức

- [Gradle — Locking Versions / Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): bật locking, tạo/cập nhật `gradle.lockfile`, lock modes, update chọn lọc, giới hạn.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--write-locks`, `--update-locks`, `--refresh-dependencies`, `--offline`.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html): vai trò declarable/resolvable/consumable và nguồn các configurations.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight`, selected versions.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksums, signatures, `gradle/verification-metadata.xml` và nguy cơ bootstrap từ nguồn chưa tin cậy.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): dynamic/changing dependencies, caching và refresh.
- [Gradle — Upgrading Within Gradle 9.x](https://docs.gradle.org/current/userguide/upgrading_version_9.html): trạng thái deprecation của legacy dependency lock files.
- [Gradle — LockMode API](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/dsl/LockMode.html): `DEFAULT`, `STRICT`, `LENIENT`.
