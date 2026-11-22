# Đọc đồ thị dependency trước khi quyết định thay đổi cấu hình Gradle

## 1. Mục tiêu: hiểu điều gì đang thực sự được giải quyết

Trong Gradle, dòng khai báo `implementation 'group:artifact:version'` chỉ diễn tả **yêu cầu ban đầu** của một project. Thư viện thực sự nằm trên classpath có thể khác yêu cầu vì dependency bắc cầu (*transitive*), xung đột phiên bản, constraint, platform/BOM, quy tắc chọn phiên bản, variant, hoặc dependency locking. Nếu sửa `build.gradle` chỉ bằng cách nhìn một dòng khai báo, bạn có thể:

- Nâng cấp/thay phiên bản nhưng classpath thực tế không thay đổi.
- Xóa một khai báo trực tiếp mà thư viện vẫn xuất hiện qua đường dẫn bắc cầu khác.
- Loại một dependency đang cần ở runtime và gây `NoClassDefFoundError`.
- Dùng `resolutionStrategy.force` để che triệu chứng, làm mất dấu nguyên nhân thực.
- Sửa nhầm `compileClasspath` trong khi lỗi chỉ ở `testRuntimeClasspath`.
- Thay version mà không nhận ra nó do BOM, constraint hoặc lockfile đang quyết định.

**Nguyên tắc:** trước khi thay dependency, phải trả lời **đúng project, đúng configuration, artifact nào được yêu cầu, phiên bản/variant nào được chọn, ai kéo nó vào và vì sao chọn như vậy**. Sau khi sửa, đọc lại **chính những báo cáo đó** và chạy các kiểm chứng liên quan.

Bài học thuộc **Mô hình dependency** của Gradle, không phải đồ thị *task dependency*. Những task như `dependencies` hoặc `dependencyInsight` chỉ là công cụ **xem đồ thị các module/thành phần** được giải quyết cho một configuration.

## 2. Bốn lớp thông tin cần tách riêng

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Declared/requested dependency** | Một project hoặc dependency khác yêu cầu module và phiên bản nào. | `commons-codec:commons-codec:1.15` |
| **Resolved/selected component** | Gradle chọn phiên bản thành phần nào cho một configuration. | `commons-codec:commons-codec:1.16.0` |
| **Path/origin** | Chuỗi module nào dẫn đến dependency, trực tiếp hay bắc cầu. | `app → httpclient → commons-codec` |
| **Variant/artifact** | Gradle chọn biến thể phù hợp yêu cầu compile/runtime, thuộc tính, capabilities, nền tảng; sau đó lấy artifact tương ứng. | Biến thể `java-api` cho compile, `java-runtime` cho runtime ở các thành phần công bố variant tương ứng. |

**Không nhầm resolved version với số phiên bản bạn thấy trong `build.gradle`.** Chỉ khi đã đọc báo cáo resolution mới có cơ sở khẳng định phiên bản được dùng trong classpath cụ thể.

Cũng cần tách **graph resolution** (chọn thành phần/biến thể theo metadata và rules) khỏi **artifact resolution** (lấy file JAR/AAR...). Một module có thể được lựa chọn trong dependency graph nhưng thất bại tải artifact vì kết nối, xác thực hoặc checksum; sửa version chưa chắc giải quyết nguyên nhân.

### 2.1. Cấu trúc cây và một mũi tên chọn phiên bản

Đây là **ví dụ sơ đồ minh họa**, không phải output cố định của mọi dự án:

```text
runtimeClasspath
+--- org.example:client:2.0
|    \--- org.example:codec:1.2 -> 1.5
\--- org.example:codec:1.5
```

Đọc theo thứ tự:

1. `runtimeClasspath` là configuration đang được giải quyết.
2. `client:2.0` yêu cầu bắc cầu `codec:1.2`.
3. Dự án cũng yêu cầu `codec:1.5` trực tiếp.
4. Biểu diễn `1.2 -> 1.5` nghĩa **yêu cầu 1.2 nhưng cuối cùng chọn 1.5 trong configuration này**.
5. Không thể kết luận chỉ từ mũi tên rằng nguyên nhân là conflict mặc định; constraint, platform hoặc rule cũng có thể tham gia. Phải chạy `dependencyInsight` để xem **Selection reasons**.

## 3. Chọn đúng configuration trước khi đọc báo cáo

Configuration vừa biểu diễn **phạm vi sử dụng**, vừa có **vai trò** trong dependency management. Với Gradle hiện đại, nên phân biệt:

| Vai trò | Ví dụ với Java plugin | Chức năng |
| --- | --- | --- |
| **Declarable / dependency bucket** | `implementation`, `compileOnly`, `runtimeOnly`, `testImplementation` | Nơi bạn **khai báo** dependency. |
| **Resolvable** | `compileClasspath`, `runtimeClasspath`, `testCompileClasspath`, `testRuntimeClasspath` | Nơi Gradle **chọn thành phần và file** cho quá trình compile/test/run. |
| **Consumable** | `apiElements`, `runtimeElements` ở các project/plugin thích hợp | Biến thể đầu ra mà project khác có thể tiêu thụ. |

`implementation` **không phải** là nơi cần lấy tập JAR đã resolved để điều tra conflict. Hãy dùng `runtimeClasspath` hoặc `compileClasspath` theo đúng tình huống. Một report trên configuration bucket không-resolvable có thể chỉ hiển thị khai báo hoặc dấu `(n)`, không đại diện cho cây resolved cuối cùng.

**Chọn scope theo triệu chứng:**

| Triệu chứng | Configuration nên xem đầu tiên |
| --- | --- |
| Compile mã nguồn chính thất bại vì thiếu API | `compileClasspath` |
| Ứng dụng khởi động lỗi class/classpath | `runtimeClasspath` |
| Test không compile | `testCompileClasspath` |
| Test chạy thất bại vì thiếu/bất tương thích library | `testRuntimeClasspath` |
| Không rõ configuration nào tồn tại | Task `resolvableConfigurations` để liệt kê các configuration có thể resolve. |
| Plugin hoặc dependency của chính build script | `buildEnvironment` (không phải `runtimeClasspath` của app). |

Tên configuration **phụ thuộc plugin**. Java, Android Gradle Plugin, Kotlin Multiplatform và plugin riêng có những configuration khác nhau. Với Android, phải chọn đúng variant như `debugRuntimeClasspath` hoặc `releaseRuntimeClasspath` (nếu project có chúng), chứ không giả định lúc nào cũng tồn tại `runtimeClasspath` chung.

### 3.1. Multi-project: chọn đúng project

Trong multi-project build, task `dependencies` mặc định báo cáo **một project**, không tự gom toàn bộ các subproject:

```bash
./gradlew -q :app:dependencies --configuration runtimeClasspath
./gradlew -q :service:dependencies --configuration testRuntimeClasspath
```

Hai lệnh trên **chỉ chạy được** nếu project có đường dẫn `:app` và `:service` như ví dụ. Nếu đang ở single-project Java build, dùng `./gradlew -q dependencies --configuration runtimeClasspath`.

Với Gradle Wrapper trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat`. Mọi lệnh trong bài giả định chạy tại root có Wrapper hợp lệ và JDK tương thích.

## 4. Công cụ 1: dependencies — nhìn toàn cảnh đồ thị

Task `dependencies` tích hợp trong Gradle, không cần cài plugin ngoài:

```bash
./gradlew dependencies
./gradlew -q dependencies --configuration compileClasspath
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencies --configuration testRuntimeClasspath
```

Lệnh đầu hiển thị báo cáo nhiều configuration nên có thể rất dài; khi chẩn đoán một lỗi, ưu tiên `--configuration` đúng. Cờ `-q` / `--quiet` làm log gọn hơn, không đổi đồ thị dependency. Đây là lệnh **đọc báo cáo**, không làm thay đổi `build.gradle`, nhưng lần đầu có thể truy cập repository và tải metadata/artifacts vào cache tùy loại resolution.

### 4.1. Đọc ký hiệu thường gặp

| Ký hiệu trong report | Cách hiểu đúng |
| --- | --- |
| `+---` và `\---` | Nhánh/thành phần trong cây dependency. |
| `1.0 -> 2.0` | Module được yêu cầu ở phiên bản 1.0, resolution chọn 2.0. |
| `(*)` | Nhánh bắc cầu đã được mở rộng ở vị trí trước đó, nên lặp lại chỉ hiển thị gốc. **Không có nghĩa bị bỏ dependency**. |
| `(c)` | Một **constraint**, không phải dependency mới được tải bởi chính dòng đó. Tìm dòng module thực sự được chọn trong cây. |
| `(n)` | Dependency/configuration không phân giải được trong ngữ cảnh report. Không suy diễn là “Gradle đã chọn version đó”. |
| `FAILED` | Có yêu cầu không giải quyết thành công; đọc nguyên nhân từ phần lỗi để phân biệt không tìm thấy module, sai repository, xác thực, variant mismatch... |

Ví dụ **minh họa** cách đọc BOM/constraint và nhánh lặp:

```text
runtimeClasspath
+--- org.example:library-a:1.0
|    \--- org.example:util:2.0
+--- org.example:library-b:1.0
|    \--- org.example:util:2.0 (*)
\--- org.example:example-bom:1.0
     \--- org.example:util:2.0 (c)
```

`(*)` cho thấy `util` cũng được yêu cầu từ nhánh B nhưng cây con đã xuất hiện trước đó. `(c)` từ BOM biểu thị version constraint cho util, **không phải một JAR độc lập cùng tên**. Khi thấy nhiều đường đến cùng một module, chỉ loại một đường có thể **không** làm module biến mất.

### 4.2. Hãy đọc cả cha của dependency

Gặp `commons-codec` trong cây không đủ để biết vì sao nó có mặt. Hãy theo thụt lề từ module đó lên các node cha:

- Node nằm ngay dưới configuration: thường là yêu cầu trực tiếp hoặc platform/constraint gắn ngay ở cấu hình.
- Node nằm dưới một module khác: là đường yêu cầu **bắc cầu**.
- Node xuất hiện ở nhiều nhánh: có **nhiều đường dẫn**. Nếu muốn loại, phải kiểm tra tất cả đường dẫn và xác định library vẫn cần ở đâu.
- Cùng module với nhiều requested versions: Gradle sẽ thực hiện conflict/constraint/rule resolution và chọn theo quy tắc hiện có.

**Quan trọng:** cây `dependencies` cho bạn xem **kết quả cuối**, nhưng không phải lúc nào cũng nêu đủ chi tiết *lý do* Gradle chọn một phiên bản hay một variant. Đó là lúc dùng `dependencyInsight`.

## 5. Công cụ 2: dependencyInsight — vì sao chọn phiên bản này?

Để điều tra một module duy nhất trong một configuration:

```bash
./gradlew -q dependencyInsight \
  --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec
```

Cờ `--dependency` nhận tên `group:artifact` hoặc chuỗi khớp một phần. Nên dùng **group:artifact** khi có thể để tránh khớp nhầm nhiều module có tên gần giống. Cờ `--configuration` nên luôn ghi rõ, kể cả ở Java project nơi task có thể mặc định `compileClasspath`; một kết luận về compile classpath chưa chắc áp dụng cho runtime.

### 5.1. Những thông tin đáng đọc nhất

Báo cáo `dependencyInsight` thường trình bày:

1. **Selected component/version**: module và version cuối cùng được chọn.
2. **Selection reasons**: vì sao được chọn, thí dụ conflict resolution, dependency constraint, forced selection, rule, requested version.
3. **Paths leading to this component**: các nhánh yêu cầu nó từ project/configuration.
4. **Variant attributes** nếu metadata cho phép: loại variant được cung cấp/chọn và yêu cầu của consumer.

Một phần output có thể có nội dung đại ý:

```text
commons-codec:commons-codec:1.16.0
   Selection reasons:
      - By conflict resolution: between versions 1.16.0 and 1.15

commons-codec:commons-codec:1.15 -> 1.16.0
\--- runtimeClasspath
```

**Đây là sơ đồ đầu ra rút gọn**, không phải cam kết chính xác từng dòng hay thứ tự từ mọi phiên bản Gradle. Khi thấy `By conflict resolution`, kiểm tra những version được yêu cầu từ đâu, rồi đánh giá **version cuối cùng** có tương thích và đáp ứng yêu cầu dự án không.

### 5.2. Các “Selection reasons” thường gặp

| Reason | Diễn giải | Bước tiếp theo |
| --- | --- | --- |
| **By conflict resolution** | Có nhiều yêu cầu phiên bản, Gradle chọn version thích hợp theo quy tắc resolution. | Truy hai hay nhiều đường gây xung đột; đọc compatibility và test. |
| **By constraint** | Constraint/BOM tham gia chọn version. | Tìm platform/constraint, không chỉ tìm `implementation`. |
| **Forced** | Phiên bản bị áp đặt bởi force/enforced platform hoặc chiến lược tương tự. | Tìm nơi đặt force/platform, đánh giá tính cần thiết. |
| **Selected by rule** | Dependency resolution rule đổi kết quả lựa chọn. | Tìm rules, dependency substitution/component selection. |
| **Was requested** | Phiên bản/nguồn yêu cầu trực tiếp hoặc bắc cầu; có thể kèm ghi chú `because`. | Xem module cha và khai báo liên quan. |
| **By ancestor** | Rich version `strictly` ở một nhánh bậc trên chi phối lựa chọn. | Kiểm tra mức version strict và cách lan truyền. |

Có thể có **nhiều reason cùng lúc**; không mặc định lúc nào cũng có duy nhất một lý do.

### 5.3. Các cờ hữu ích

```bash
./gradlew -q dependencyInsight --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec --single-path

./gradlew -q dependencyInsight --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec --all-variants
```

- `--single-path` chỉ hiện **một** đường đến module, hữu ích khi output quá dài; **không dùng** nó để khẳng định chỉ có một nguồn kéo dependency.
- `--all-variants` yêu cầu bổ sung thông tin các variants khi Gradle/metadata hỗ trợ. Khi có lỗi do variant, attributes hoặc capability, điều tra này hữu ích hơn việc đổi version một cách mù quáng. Tính hữu ích phụ thuộc metadata được công bố của module.
- Với mâu thuẫn sâu về variant selection, xem cả `resolvableConfigurations` của consumer và `outgoingVariants` của project producer (nếu plugin tạo những report đó).

## 6. Ví dụ chạy được: nhìn requested khác selected

Mục này tạo một **Java project thực hành**, khai báo hai phiên bản của cùng module để mô phỏng conflict có thể quan sát. Dùng Gradle Wrapper hợp lệ, JDK tương thích; cần mạng để tải dependency từ Maven Central lần đầu.

**File `settings.gradle`:**

```groovy
rootProject.name = 'dependency-graph-lab'
```

**File `build.gradle`:**

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    // Hai yêu cầu cho cùng một group:artifact để quan sát conflict:
    implementation 'commons-codec:commons-codec:1.15'
    implementation 'commons-codec:commons-codec:1.16.0'

    // JUnit 4 chỉ phục vụ test; nó có dependency bắc cầu.
    testImplementation 'junit:junit:4.13.2'
}

tasks.named('test', Test) {
    useJUnit()
}
```

Hai khai báo `commons-codec` được đặt **cố ý để làm bài tập phân tích**, không phải cách nên viết build sản xuất. Gradle thường chọn phiên bản mới hơn trong hai yêu cầu tương thích khi không có strict constraint/force/rule khác — ở ví dụ này là `1.16.0`. Chọn version cao hơn **không bảo đảm** API/ABI hoặc runtime compatibility; đó là vấn đề cần kiểm thử.

### 6.1. Đọc runtimeClasspath

```bash
./gradlew -q dependencies --configuration runtimeClasspath
```

Bạn sẽ tìm những dòng tương tự (lược bỏ header của report và những dòng có thể phát sinh do Gradle/version môi trường):

```text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- commons-codec:commons-codec:1.15 -> 1.16.0
\--- commons-codec:commons-codec:1.16.0
```

Điều quan trọng là `requested 1.15` đã được chuyển thành `selected 1.16.0`. Đừng nhìn chỉ dòng đầu rồi kết luận runtime đang dùng 1.15.

Sau đó:

```bash
./gradlew -q dependencyInsight \
  --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec
```

Tìm `Selection reasons` và hai đường yêu cầu. Trong dự án ví dụ này, lý do là **conflict resolution** giữa `1.15` và `1.16.0`. Đồ thị chỉ có một component version được chọn cho module đó trong configuration.

### 6.2. So sánh với testRuntimeClasspath

```bash
./gradlew -q dependencies --configuration testRuntimeClasspath
./gradlew -q dependencyInsight \
  --configuration testRuntimeClasspath \
  --dependency org.hamcrest:hamcrest-core
```

Với metadata chuẩn của `junit:junit:4.13.2`, bạn thường thấy `org.hamcrest:hamcrest-core:1.3` được JUnit kéo vào ở test classpath. Nó không phải dependency trực tiếp của ứng dụng và không nhất thiết có trong `runtimeClasspath` chính. Đây là lý do phải hỏi "**lỗi xảy ra ở classpath nào?**" trước khi dùng `exclude` hoặc chỉnh `runtimeOnly`.

### 6.3. Thêm bài test Java 17 để kiểm tra tác động

Tạo **`src/test/java/CodecTest.java`**:

```java
import org.junit.Test;
import static org.junit.Assert.assertEquals;
import org.apache.commons.codec.binary.Hex;

public class CodecTest {
    @Test
    public void encodesAsciiBytes() {
        byte[] bytes = new byte[] {0x61, 0x62};
        assertEquals("6162", Hex.encodeHexString(bytes));
    }
}
```

Chạy:

```bash
./gradlew test --console=plain
```

Khi các repository có thể truy cập và cấu hình đúng, test **PASS**; `Hex.encodeHexString` của Commons Codec biến hai byte `0x61`, `0x62` thành chuỗi `6162`. Task test không in `6162` ra stdout: đây là **giá trị được so sánh trong assertion**. Kết quả console cụ thể tùy trạng thái cache/up-to-date và Gradle version. Nếu test FAIL, đọc report kiểm thử thay vì giả định mâu thuẫn version là nguyên nhân duy nhất.

### 6.4. Một thay đổi nhỏ có thể không đổi classpath

Hãy **chỉ trong bản project thực hành**, xóa dòng:

```groovy
implementation 'commons-codec:commons-codec:1.15'
```

giữ lại:

```groovy
implementation 'commons-codec:commons-codec:1.16.0'
```

Chạy lại `dependencies` và `dependencyInsight`. Requested 1.15 biến mất, nhưng **selected version vẫn là 1.16.0**. Đây là minh họa thực tế cho quy tắc: **một thay đổi trong khai báo không đồng nghĩa thay đổi effective dependency graph**.

Nếu nhu cầu là giảm rủi ro cho production, thay đổi này thường dễ review hơn việc lập tức áp dụng global `force`. Tuy nhiên hãy kiểm tra các cấu hình khác và task test trước khi kết luận an toàn.

## 7. Quy trình “đọc trước – quyết định – kiểm chứng sau”

### Bước 1 — Xác định triệu chứng và phạm vi

Ghi lại lỗi thực tế và nơi xuất hiện:

- Compile: thiếu symbol hoặc API thay đổi? Kiểm tra `compileClasspath`.
- Runtime: `NoClassDefFoundError`, `NoSuchMethodError` hoặc classpath conflict? Kiểm tra `runtimeClasspath`.
- Test: mismatch chỉ ở test? Kiểm tra `testRuntimeClasspath` hoặc `testCompileClasspath`.
- Plugin build: lỗi ở `plugins`/buildscript? Kiểm tra `buildEnvironment` và plugin resolution chứ không chỉ dependencies ứng dụng.
- Android/multiplatform: đúng build variant, source set, flavor và target?

Ghi đúng project path `:app` / `:lib`. Một lỗi ở `:service` không nhất thiết được phản ánh trong report của root project.

### Bước 2 — Lưu baseline **trước khi sửa**

Trên Bash (Linux/macOS) hoặc shell hỗ trợ redirection tương ứng:

```bash
./gradlew -q dependencies --configuration runtimeClasspath \
  > deps-runtime-before.txt

./gradlew -q dependencyInsight --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec \
  > codec-insight-before.txt
```

Hai file trên là log kiểm tra cho project đang khảo sát; có thể lưu **ngoài repository** nếu nhóm không muốn commit chúng. Nếu dùng Windows PowerShell, chạy lệnh trên **một dòng** với `.\gradlew.bat` và toán tử `>`; lưu ý encoding của output redirect phụ thuộc phiên bản PowerShell. Không nên chỉnh `build.gradle` trước khi biết baseline.

Ghi thêm môi trường: phiên bản Gradle Wrapper (`./gradlew --version`), JDK, repository, chế độ offline/online, lockfile có hay không; việc resolve dependency động trong thời điểm khác có thể khác nếu không khóa version.

### Bước 3 — Tìm nguyên nhân, không chỉ tìm tên JAR

Dựa vào báo cáo:

1. **Đi theo cây** từ root configuration đến module có vấn đề.
2. **So requested → selected** và ghi cả hai version.
3. **Dùng dependencyInsight** để tìm mọi path và selection reasons.
4. **Kiểm tra constraint/BOM** nếu gặp `(c)` hoặc `By constraint`.
5. **Kiểm tra rule/force/lock** nếu lý do không phải conflict mặc định.
6. **Kiểm tra variant** khi xuất hiện lỗi `No matching variant`, capabilities hoặc attributes.
7. **Khoanh vùng đúng usage**: compile, runtime, test, debug/release.

Đừng coi `dependencies` là danh sách “toàn bộ file đã được tải” hay bằng chứng một module không bao giờ xuất hiện ở cấu hình khác.

### Bước 4 — Viết giả thuyết và chọn biện pháp nhỏ nhất

Ví dụ báo cáo kết luận: “`commons-codec` được yêu cầu ở 1.15 trực tiếp và 1.16.0 trực tiếp; `runtimeClasspath` chọn 1.16.0 bằng conflict resolution”. Lúc đó mới quyết định:

- Nếu hai khai báo lặp vô ý: xóa hoặc cập nhật khai báo cũ.
- Nếu transitive kéo version không mong muốn: thử nâng dependency trực tiếp cấp cha, hoặc thêm constraint hợp lý nếu version cần kiểm soát.
- Nếu platform/BOM chủ định căn chỉnh nhiều module: thay BOM/platform tại nguồn, không override một thành viên tùy tiện.
- Nếu lỗi chỉ là sai variant: sửa usage/attributes/capabilities/configuration, không mặc nhiên hạ version.
- Nếu phụ thuộc không cần thiết và chỉ đến từ đường dẫn cụ thể: mới cân nhắc `exclude` có phạm vi hẹp.

**Không vội dùng `resolutionStrategy.force`**: nó áp đặt version, có thể che những yêu cầu khác và làm nguyên nhân khó thấy. Nếu policy thật sự cần version chặt, tìm hiểu dependency constraints, rich version `strictly`, `prefer`, `reject` hoặc platform/BOM, và đánh giá khả năng truyền constraint cho consumer.

### Bước 5 — Chỉ sửa một nhóm nguyên nhân, rồi so sánh “after”

Sau thay đổi thử nghiệm:

```bash
./gradlew -q dependencies --configuration runtimeClasspath \
  > deps-runtime-after.txt

./gradlew -q dependencyInsight --configuration runtimeClasspath \
  --dependency commons-codec:commons-codec \
  > codec-insight-after.txt

./gradlew test --console=plain
```

So sánh before/after bằng công cụ diff của nhóm, đọc cả changes trên `compileClasspath` và `testRuntimeClasspath` khi liên quan. Đối với ứng dụng Java, chạy integration/smoke tests quan trọng, vì dependency resolve thành công **không** đồng nghĩa tất cả mã runtime tương thích. Nếu thay đổi liên quan tới bảo mật, đối chiếu advisories từ nguồn chính thức và kiểm tra dependency verification/lock state theo chính sách tổ chức.

## 8. Quyết định thay đổi theo dấu hiệu của đồ thị

| Quan sát | Điều phải kiểm tra | Hướng xử lý ưu tiên |
| --- | --- | --- |
| `1.1 -> 1.5` | Module nào yêu cầu 1.1, vì sao 1.5 được chọn? | `dependencyInsight`, rồi thống nhất khai báo/version khi cần. |
| Nhiều nhánh tới một module | Có còn path khác nếu bỏ một khai báo? | Chỉ loại dependency khi đã xét mọi path. |
| `(c)` hoặc **By constraint** | Constraint từ platform, BOM, project hay thư viện nào? | Sửa ở nơi khai báo policy hoặc constraint có chủ đích. |
| **Forced** | Có enforced platform, force hoặc rule không? | Kiểm tra chủ ý và loại force không cần thiết. |
| **Selected by rule** | Substitution/selection rule nào can thiệp? | Sửa rule/metadata theo chính sách, không chồng thêm force. |
| **No matching variant** | Consumer yêu cầu attributes/capabilities nào, producer cung cấp gì? | Kiểm tra variants/configurations, thay vì sửa version ngẫu nhiên. |
| `FAILED` hoặc `(n)` | Repository, credentials, metadata, network, role của configuration? | Xác định nguyên nhân resolution cụ thể trước khi sửa. |
| Chỉ lỗi ở `testRuntimeClasspath` | Dependency chỉ của test hay transitive? | Chỉnh `testImplementation`/test runtime đúng chỗ. |
| Dependency “không biến mất” sau `exclude` | Có nhánh khác yêu cầu module? | Đọc lại cây, giới hạn exclude đúng cạnh. |
| Không thay đổi version dù sửa `libs.versions.toml` | Có dependency/constraint, BOM hoặc lockfile đang quyết định? | Truy nguồn version bằng insight; kiểm tra mọi khai báo liên quan. |

### 8.1. Dependency constraints không phải dependency trực tiếp

Ví dụ **minh họa API**:

```groovy
dependencies {
    implementation 'commons-codec:commons-codec:1.15'

    constraints {
        implementation('commons-codec:commons-codec:1.16.0') {
            because 'Mức phiên bản được nhóm kiểm thử'
        }
    }
}
```

Constraint **tham gia chọn phiên bản** khi module có mặt trong graph; nó không tự thêm module như `implementation` trực tiếp. Report có thể hiển thị dấu `(c)` và `dependencyInsight` có lý do `By constraint`. Đây là đoạn **thay thế để minh họa**, không thêm vào bài thực hành mục 6 cùng hai version nếu bạn chưa chủ đích thử một biến thể giải quyết khác.

Không nhầm constraint thông thường với `strictly`: một yêu cầu/constraint version thông thường có thể được nâng theo đồ thị; `strictly` thu hẹp tập phiên bản cho phép và có thể khiến resolution thất bại nếu các điều kiện không tương thích.

### 8.2. Exclude chỉ khi có bằng chứng

Ví dụ một dependency có transitive module không cần dùng:

```groovy
dependencies {
    implementation('commons-beanutils:commons-beanutils:1.9.4') {
        exclude group: 'commons-collections', module: 'commons-collections'
    }
}
```

Đây là **ví dụ cú pháp**, không phải đề xuất dùng phiên bản cũ ở production. Exclusion gắn vào **một cạnh dependency**; nếu đường dẫn khác cũng kéo `commons-collections` thì module vẫn có thể xuất hiện. Chỉ dùng sau khi hiểu chức năng của thư viện bị loại; có trường hợp compile thành công nhưng runtime thiếu class. Tránh global exclude tràn lan khi chưa đánh giá toàn bộ graph.

### 8.3. Dynamic version, cache và dependency locking

Nếu dự án khai báo `1.+` hoặc khoảng phiên bản động, lần resolve ở những thời điểm khác nhau có thể chọn phiên bản mới khi repository có bản phát hành mới. Các chính sách cache metadata và thời gian kiểm tra làm kết quả có thể thay đổi ngay cả khi file build không đổi.

- Ưu tiên **version cố định đã kiểm thử** khi cần reproducibility.
- Nếu tổ chức cho phép dynamic version, dùng **dependency locking** cho configuration quan trọng và quản lý lockfile bằng quy trình rõ ràng.
- Đọc lại report **trước và sau** thay đổi; đánh giá bản khóa nếu lockfile được cập nhật.
- `--refresh-dependencies` buộc Gradle kiểm tra lại metadata/caches theo cơ chế của nó; **không phải** “sửa mọi conflict” hay lý do để bỏ kiểm tra graph.
- `--offline` chỉ dùng artifact/metadata có sẵn trong cache; nếu chưa được tải, resolution có thể fail. Không đồng nhất offline failure với “version không tồn tại ở Maven Central”.

**Cẩn trọng với `--write-locks`**: nếu dependency locking đang bật, cờ này có thể tạo hoặc **ghi đè** trạng thái lockfile cho các configuration được resolve. Nó không phải bước xem report read-only, nên không chạy khi chỉ muốn chẩn đoán.

## 9. Variant-aware resolution: một module không chỉ có một JAR

Một module/project Gradle có thể công bố nhiều variants với các **attributes** như usage (Java API hay Java runtime), JVM version, library elements, target platform và capabilities. Consumer có attributes yêu cầu tương ứng. Gradle chọn variant và artifact phù hợp, không đơn thuần lấy JAR có cùng group/name/version.

Những điều cần biết:

- `compileClasspath` và `runtimeClasspath` có **usage khác nhau**. Với Java library đã công bố variants đầy đủ, Gradle có thể chọn `apiElements` ở compile và `runtimeElements` ở runtime.
- Một thư viện được xuất bản bằng Maven POM đơn giản có thể không có cùng lượng metadata variant như một Gradle project với Gradle Module Metadata. Đừng suy ra mọi module đều có tên variants giống nhau.
- Lỗi `No matching variant of project :lib was found` thường là dấu hiệu attributes/capabilities/usage không khớp. Điều tra đúng configuration/variant trước khi áp đặt phiên bản hoặc bỏ dependency.

Lệnh gợi ý (trên project có `:lib`):

```bash
./gradlew -q :app:resolvableConfigurations
./gradlew -q :lib:outgoingVariants
./gradlew -q :app:dependencyInsight \
  --configuration runtimeClasspath --dependency lib --all-variants
```

Các lệnh trên **không chạy được y nguyên** nếu project không có `:app`/`:lib` hoặc không có report task tương ứng. Trên single-project Java demo, dùng `./gradlew -q resolvableConfigurations` và `dependencyInsight` cho module thực tế. Đọc attributes hiển thị trong báo cáo và so sánh bên consumer/producer.

### 9.1. Vì sao lỗi variant không phải lúc nào cũng là lỗi version?

Giả sử consumer yêu cầu một Java runtime variant phù hợp JVM đang dùng, nhưng producer chỉ cung cấp biến thể tương thích một JVM cao hơn hoặc chỉ có API variant. Cùng version module vẫn có thể không được chọn vì **không có matching variant**. Việc hạ version một cách mù quáng có thể tạo thêm lỗi. Cần xác minh:

1. Consumer đang resolve configuration nào?
2. Attributes mà configuration đó yêu cầu là gì?
3. Producer công bố những variants nào?
4. Java toolchain/target compatibility/capability nào đang hạn chế việc chọn?
5. Có plugin hoặc component metadata rule nào làm biến đổi attributes?

Chỉ sau khi biết nguyên nhân mới quyết định đổi plugin, target JVM, variant metadata hoặc dependency.

## 10. Những nơi khác có thể điều khiển graph

Nếu version được chọn không khớp trực giác, hãy xem **những điểm khai báo có thể ảnh hưởng resolution**, nhưng chỉ sau khi báo cáo cho biết dấu hiệu thích hợp:

| Nguồn | Tác động cần tìm |
| --- | --- |
| `build.gradle` / `build.gradle.kts` | Khai báo `implementation`, `runtimeOnly`, test scopes, constraints. |
| `gradle/libs.versions.toml` | Version catalog định nghĩa alias/version khai báo; không đảm bảo selected version cuối. |
| Platform hoặc BOM | Căn chỉnh/áp đặt constraints cho một nhóm module. |
| `enforcedPlatform` | Chính sách cưỡng chế version có thể lan sang consumers trong một số trường hợp. |
| `constraints { }` | Ràng buộc phiên bản được giải quyết, có thể dùng rich versions. |
| `resolutionStrategy` | Force, substitutions, component selection/replacement rules. |
| `gradle.lockfile` và lockfiles liên quan | Cố định kết quả resolution theo configuration đang được lock. |
| `settings.gradle` / repository management | Nơi chọn repositories, content filters, plugin resolution. |
| Dependency metadata từ repository | POM, Gradle Module Metadata, transitive relations, variants/capabilities. |

**Không chỉnh tất cả những nơi này cùng lúc.** Lý tưởng là xác định **một nguyên nhân**, áp dụng **một thay đổi có thể review**, rồi xác nhận selected graph và tests.

## 11. Các lỗi phân tích thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| Chỉ tìm `implementation 'x:y:v'` rồi kết luận runtime đang dùng v. | Resolution có thể chọn version khác. | Xem `runtimeClasspath` và `dependencyInsight`. |
| Chạy `dependencies` ở root khi lỗi ở `:app`. | Report sai project. | Chỉ rõ `:app:dependencies`. |
| Xem bucket `implementation` thay vì resolved classpath. | Không thấy cây resolution cuối. | Chọn `compileClasspath`/`runtimeClasspath`. |
| Đọc `(*)` là dependency đã bị loại. | Đó là subtree lặp được thu gọn. | Tìm nơi subtree đã được mở rộng. |
| Đọc `(c)` là một thư viện được tải thêm. | Constraint không tự kéo artifact vào graph. | Tìm occurrence của module và reason. |
| Đọc `1.2 -> 1.5` là chỉ do “Gradle luôn chọn newest”. | Có thể là constraint/forced/rule. | Đọc selection reasons. |
| Chỉ dùng `--single-path` để kết luận đường duy nhất. | Cờ cố ý ẩn các path khác. | Bỏ `--single-path` khi cần điều tra mọi nguồn. |
| Exclude module ngay khi thấy tên bất ngờ. | Có thể là runtime dependency quan trọng. | Truy nguồn và test đầy đủ. |
| Force version khi chưa hiểu conflict. | Che nguyên nhân; risk incompatibility. | Thử upgrade nguồn yêu cầu hoặc constraint có lý do. |
| Cho rằng `--refresh-dependencies` luôn làm đổi version. | Chỉ ảnh hưởng kiểm tra cache/metadata, không thay luật chọn. | Phân biệt cache với resolution strategy. |
| Đổi build file nhưng không xem lockfile. | Lock có thể giữ hoặc từ chối graph mới. | Kiểm tra trạng thái dependency locking. |
| Thấy `FAILED` và đổi version ngay. | Có thể do repository, credentials, network hoặc variant. | Đọc lỗi gốc và metadata. |
| Coi dependency report là báo cáo task graph. | Hai loại graph khác nhau. | Dùng `dependencies` cho module; `--dry-run` cho task graph. |

## 12. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài 1 — Hai yêu cầu, một phiên bản được chọn

Dùng nguyên `build.gradle` mục 6:

1. Chạy `dependencies --configuration runtimeClasspath`.
2. Ghi hai requested versions của `commons-codec`.
3. Ghi selected version.
4. Chạy `dependencyInsight --dependency commons-codec:commons-codec --configuration runtimeClasspath` và đọc `Selection reasons`.
5. Xóa yêu cầu 1.15 rồi chạy lại hai báo cáo.

**Đáp án trọng tâm:** requested 1.15 và 1.16.0, selected 1.16.0 (trong ví dụ không bị policy bên ngoài can thiệp). Khi bỏ 1.15, selected version vẫn 1.16.0 nhưng path/conflict reason thay đổi.

### Bài 2 — Dependency chỉ xuất hiện trong test

Chạy `dependencies --configuration runtimeClasspath` và `dependencies --configuration testRuntimeClasspath`. Tìm `org.hamcrest:hamcrest-core` do JUnit 4 kéo theo. Giải thích vì sao không nên sửa `runtimeClasspath` chỉ vì thư viện xuất hiện trong test scope.

### Bài 3 — Chỉ báo cáo một đường dẫn

Chạy hai lần `dependencyInsight` cho cùng một module: lần đầu không cờ phụ, lần hai thêm `--single-path`. Vì sao kết quả lần hai không đủ để đưa ra quyết định loại bỏ tất cả các nguồn kéo dependency?

### Bài 4 — Constraint và exclusion

Đọc ví dụ `constraints` trong mục 8.1 và `exclude` trong mục 8.2. So sánh:

- Constraint tham gia **chọn version**, không thêm module trực tiếp.
- Exclude cắt một số **đường dẫn yêu cầu**, có thể làm module mất khỏi graph chỉ nếu không còn đường cần module đó.

Nêu rủi ro khi loại module đang cần ở runtime.

### Bài 5 — Multi-project / variant

Giả sử lỗi chỉ xảy ra khi chạy `:service:test` trong multi-project build. Nên bắt đầu từ `:service:dependencies --configuration testRuntimeClasspath` hay báo cáo root? Nếu gặp `No matching variant`, cần xem những attributes nào trước khi đổi version?

### Bài 6 — Báo cáo trước/sau

Với một thay đổi dependency được giao, chuẩn bị bảng review:

| Trường | Trước | Sau |
| --- | --- | --- |
| Project và configuration | ... | ... |
| Module group:name | ... | ... |
| Requested versions | ... | ... |
| Selected version | ... | ... |
| Selection reasons | ... | ... |
| Dependency paths | ... | ... |
| Variant / attributes nếu liên quan | ... | ... |
| Kết quả compile/test/runtime checks | ... | ... |

Chỉ đánh dấu “xong” khi đã biết **điều gì đổi thật** trong resolved graph và đã kiểm tra hành vi build.

### Câu hỏi nhanh

1. **`implementation` có luôn là configuration được resolve không?** Không; với Java plugin, nó là bucket khai báo, còn classpath cần xem là `compileClasspath`/`runtimeClasspath`.
2. **`1.15 -> 1.16.0` nghĩa là có hai JAR version 1.15 và 1.16.0 được dùng cùng lúc?** Không; Gradle cho biết yêu cầu chuyển sang một version được chọn cho module trong graph đó.
3. **`(*)` nghĩa là bị loại bỏ không?** Không; nhánh lặp được thu gọn.
4. **`(c)` là gì?** Dependency constraint.
5. **Tại sao vẫn cần `dependencyInsight` khi đã có cây?** Để biết lý do chọn version và những đường kéo dependency.
6. **Có nên dùng `force` hoặc `exclude` ngay không?** Không; cần biết nguyên nhân và tác động.
7. **Bỏ một direct dependency có đảm bảo module biến mất?** Không, nó có thể còn được kéo bởi dependency bắc cầu khác.
8. **Graph resolve thành công có đảm bảo application chạy được không?** Không; cần kiểm tra compile/test/runtime và khả năng tương thích.
9. **`--write-locks` có phải lệnh xem thuần túy không?** Không; có thể ghi lockfiles.
10. **Tại sao `--all-variants` hữu ích khi có lỗi matching?** Nó hiển thị thêm thông tin variants được công bố để phân tích attributes/usage.

## 13. Tài liệu chính thức

- **Gradle — Viewing Dependencies**: cách dùng `dependencies`, `dependencyInsight`, ký hiệu cây, selection reasons, `--single-path`, `--all-variants`: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- **Gradle — Creating Dependency Configurations**: declarable/resolvable/consumable và inheritance: https://docs.gradle.org/current/userguide/declaring_configurations.html
- **Gradle — Declaring Dependency Constraints**: constraint/BOM, rich versions: https://docs.gradle.org/current/userguide/dependency_constraints.html
- **Gradle — Declaring Versions and Ranges**: `strictly`, `prefer`, `reject`: https://docs.gradle.org/current/userguide/dependency_versions.html
- **Gradle — How to Exclude Transitive Dependencies**: tác động từng path và rủi ro: https://docs.gradle.org/current/userguide/how_to_exclude_transitive_dependencies.html
- **Gradle — Locking Versions**: dependency locking và `--write-locks`: https://docs.gradle.org/current/userguide/dependency_locking.html
- **Gradle — Variants and Attributes**: lựa chọn artifact/variants: https://docs.gradle.org/current/userguide/variant_attributes.html
- **Gradle — Using Resolution Rules**: force, substitutions và selection rules: https://docs.gradle.org/current/userguide/resolution_rules.html
- **Gradle — Best Practices for Dependencies**: đổi cấu hình có chủ đích: https://docs.gradle.org/current/userguide/best_practices_dependencies.html

**Kết luận:** Đừng sửa dependency chỉ vì thấy một version trong script hoặc một JAR trên máy. Hãy xác định đúng **project → configuration → requested paths → selected component/variant → selection reasons**, rồi chỉ thay điều cần thay và **đối chiếu before/after** cùng kiểm thử.