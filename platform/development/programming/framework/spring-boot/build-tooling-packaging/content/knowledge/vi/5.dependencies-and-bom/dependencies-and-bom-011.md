# Đọc dependency:tree, dependencies và dependencyInsight để giải thích phiên bản được chọn

## Mục tiêu học tập

Trong ứng dụng Spring Boot, bạn có thể chỉ khai báo một starter hoặc một thư viện nhưng bản build lại tải thêm hàng chục thư viện khác. Đôi khi `pom.xml` hoặc `build.gradle` ghi phiên bản A, còn ứng dụng thực tế dùng phiên bản B; đôi khi hoàn toàn không ghi phiên bản nhưng build vẫn thành công. Để giải thích được điều này, phải đọc **đồ thị phụ thuộc đã được phân giải**, không chỉ đọc các dòng khai báo.

Sau bài học, bạn có thể:

1. Chạy **Maven `dependency:tree`** để thấy thư viện trực tiếp, thư viện bắc cầu và phiên bản đã được chọn.
2. Chạy **Gradle `dependencies`** để nhìn các dependency theo đúng cấu hình như `compileClasspath`, `runtimeClasspath` và `testRuntimeClasspath`.
3. Chạy **Gradle `dependencyInsight`** để trả lời: ai yêu cầu thư viện này, yêu cầu phiên bản nào, phiên bản nào được chọn và **vì sao**.
4. Giải thích sự tham gia của **Spring Boot BOM**, `dependencyManagement`, Gradle platform/constraint, phiên bản khai báo trực tiếp và cơ chế giải quyết xung đột.
5. Điều tra lỗi thực tế như thư viện bị chọn sai phiên bản, nhiều đường dẫn kéo cùng một thư viện, phụ thuộc không có trong runtime và dependency resolution thất bại.

Bài tập trung vào **đọc báo cáo và suy luận dựa trên bằng chứng**. Tên dependency, phiên bản và đường dẫn trong ví dụ được ghi rõ là **mô phỏng** khi không lấy từ một dự án đã chạy; kết quả cuối cùng của dự án bạn phải được xác nhận bằng chính các lệnh trên môi trường đó.

## 1. Mô hình tư duy: khai báo, yêu cầu, quản lý, phân giải

Hình dung dự án `app` khai báo trực tiếp `feature-a` và `feature-b`. Hai thư viện này lại khai báo `common-lib` ở các phiên bản khác nhau:

```text
app
├── feature-a:1.0
│   └── common-lib:2.0
└── feature-b:1.0
    └── common-lib:3.0
```

Đây là **đồ thị yêu cầu ban đầu**, chưa phải kết quả cuối cùng. Công cụ build phải quyết định liệu chọn `common-lib:2.0`, `3.0` hay báo lỗi; câu trả lời phụ thuộc vào Maven/Gradle, phiên bản quản lý từ BOM, quy tắc constraint/force/exclusion, và cấu hình classpath.

| Thuật ngữ | Nghĩa | Cách tìm |
| --- | --- | --- |
| **Phụ thuộc trực tiếp (direct)** | Được chính dự án khai báo trong `dependencies` / `<dependencies>` | Đọc file build và hàng cấp một trong báo cáo |
| **Phụ thuộc bắc cầu (transitive)** | Được kéo vào thông qua dependency khác | Xem các nhánh sâu của dependency tree |
| **Requested version** | Phiên bản hoặc dải phiên bản mà một dependency/constraint yêu cầu | Nhìn đầu bên trái `2.0 -> 3.0` ở Gradle; đọc các đường dẫn yêu cầu |
| **Managed/constrained version** | Phiên bản từ BOM, `dependencyManagement`, Gradle constraint hoặc rule | Xem effective POM, BOM, insight/selection reasons |
| **Selected/resolved version** | Phiên bản công cụ build đã chọn cho **một graph/cấu hình cụ thể** | Maven `dependency:tree`; Gradle `dependencies` và `dependencyInsight` |
| **Classpath** | Tập thư viện phục vụ một mục đích như compile, runtime hoặc test | Maven scope, Gradle `--configuration` phù hợp |

**Ba câu hỏi phải tách riêng:** (1) ai **đưa** thư viện vào đồ thị, (2) ai **đưa ra yêu cầu phiên bản**, (3) quy tắc nào khiến **một phiên bản cụ thể được chọn**. Nhìn thấy một dependency trong BOM chỉ trả lời về **quản lý phiên bản**; không tự chứng minh thư viện đó có mặt trên classpath.

### Vì sao cần nhìn theo classpath?

Một dependency có thể có trong kiểm thử nhưng không có trong runtime; thư viện phục vụ compile có thể khác thư viện được đóng gói để chạy. Maven có khái niệm `scope` (ví dụ `compile`, `runtime`, `test`, `provided`); Gradle có các cấu hình và classpath như `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`. Cùng một tọa độ `group:artifact` có thể được phân giải trong những ngữ cảnh khác nhau với kết quả khác nhau.

Khi hỏi "**phiên bản nào thực sự được dùng?**", luôn xác định **module + cấu hình/classpath + chế độ build** trước khi trả lời.

## 2. Maven: chạy và đọc `dependency:tree`

### Lệnh cơ bản

Ở thư mục gốc có `pom.xml`, chạy Maven Wrapper:

```bash
./mvnw dependency:tree
```

Windows PowerShell:

```powershell
.\mvnw.cmd dependency:tree
```

Lệnh này gọi mục tiêu `tree` của **Maven Dependency Plugin**, tạo cây dependency đã giải quyết cho dự án. Dùng Wrapper để tránh chênh phiên bản Maven giữa máy cá nhân và CI. Lần đầu có thể cần tải plugin và dependency từ kho đã cấu hình.

**Đầu ra mô phỏng** cho ứng dụng có hai nhánh:

```text
[INFO] com.example:demo:jar:0.0.1-SNAPSHOT
[INFO] +- com.example:feature-a:jar:1.0:compile
[INFO] |  \- org.example:common-lib:jar:2.0:compile
[INFO] \- com.example:feature-b:jar:1.0:compile
```

Tất cả tọa độ `com.example` / `org.example` trong cây là **giả định dùng để giải thích**, không khẳng định artifact thực tồn tại. Trong dòng `org.example:common-lib:jar:2.0:compile`:

- `org.example` là `groupId`, `common-lib` là `artifactId`.
- `jar` là kiểu artifact.
- `2.0` là **phiên bản được hiển thị trong cây đã phân giải**.
- `compile` là Maven scope theo dự án đang xét.
- Dấu `+-`, `\-` và thụt lề cho biết **đường dẫn kéo dependency vào**, không biểu thị thứ tự chạy chương trình.

Kết quả thông thường có thể **không hiện tất cả bản đã bị loại khỏi xung đột**. Vì vậy việc thấy `common-lib:2.0` chưa đủ để kết luận "chỉ một thư viện yêu cầu nó"; nhánh `feature-b` có thể yêu cầu phiên bản khác rồi bị bỏ qua trong cây đã chọn.

### Lọc cho bớt nhiễu

```bash
# Xem các nhánh liên quan tới một artifact
./mvnw dependency:tree -Dincludes=org.slf4j:slf4j-api

# Chỉ quan sát các dependency theo phạm vi runtime
./mvnw dependency:tree -Dscope=runtime

# Hiển thị cả những nút bị loại do xung đột nếu plugin hỗ trợ
./mvnw dependency:tree -Dverbose

# Ghi kết quả ra tệp để gửi kèm báo cáo kỹ thuật
./mvnw dependency:tree -DoutputFile=dependency-tree.txt
```

`-Dincludes` nhận pattern tọa độ Maven và lọc **báo cáo**, không làm thư viện khác bị loại khỏi build. Chẳng hạn `org.slf4j:slf4j-api` chỉ là mục tiêu tìm kiếm ví dụ; nếu ứng dụng không dùng SLF4J thì không có kết quả phù hợp.

`-Dverbose` của Maven Dependency Plugin có thể đưa các nút **omitted** vào báo cáo, ví dụ thông tin xung đột/nhân bản (cách hiển thị và mức độ chi tiết tùy phiên bản plugin). Nếu plugin hoặc bản build không hỗ trợ kết quả cần tìm, xác nhận phiên bản `maven-dependency-plugin` đang chạy; đừng mặc định mọi bản cũ cho cùng định dạng. Khi cần định dạng máy đọc, phiên bản plugin mới hỗ trợ `-DoutputType=json`; phải xem phiên bản plugin thực tế, không mặc định có JSON trên mọi máy.

Trên PowerShell, để tránh shell tách tham số chứa dấu đặc biệt, có thể viết `.\mvnw.cmd dependency:tree "-Dincludes=org.slf4j:slf4j-api"`.

### Chọn đúng module Maven

Một repository Maven nhiều module có thể tạo ra **nhiều cây khác nhau**. Đứng ở module có `pom.xml` của ứng dụng hoặc chọn module từ reactor, ví dụ:

```bash
./mvnw -pl :demo dependency:tree
```

Trong ví dụ, `demo` phải là `artifactId` thực tế trong reactor. Đừng lấy tree của module thư viện rồi kết luận đó chính là runtime classpath của module ứng dụng.

## 3. Vì sao Maven chọn một phiên bản?

### Quy tắc nearest definition

Nếu **không có quản lý phiên bản nào khác chi phối**, Maven dùng cơ chế hòa giải phụ thuộc (**dependency mediation**) theo **đường gần gốc hơn**: phiên bản của dependency có đường từ project ngắn hơn sẽ được chọn. Nếu hai đường có cùng độ sâu, đường có khai báo xuất hiện **trước** thắng.

Với đồ thị mô phỏng:

```text
demo
├── feature-a:1.0  ------> common-lib:2.0  (độ sâu 2)
└── feature-b:1.0  ------> common-lib:3.0  (độ sâu 2)
```

Nếu `feature-a` đứng trước `feature-b` trong `pom.xml` và không có `dependencyManagement` liên quan, **Maven có thể chọn `common-lib:2.0`** ở độ sâu bằng nhau theo quy tắc "first declaration wins". Nếu dự án khai báo trực tiếp `common-lib:3.0` thì đường trực tiếp gần gốc hơn các đường bắc cầu và sẽ tác động kết quả. Không suy luận Maven mặc định "chọn phiên bản lớn nhất".

### Vai trò của `dependencyManagement` và BOM

Một Spring Boot Maven project thường kế thừa `spring-boot-starter-parent`, hoặc nhập `spring-boot-dependencies` BOM theo `dependencyManagement`. BOM đưa ra tập phiên bản **được quản lý** cho nhiều thư viện. Khi một dependency tương ứng xuất hiện trong đồ thị và không bị khai báo/ghi đè theo cách có ưu tiên cao hơn, Maven có thể điền/chọn phiên bản do quản lý đặt ra.

Ví dụ trích đoạn **minh họa vai trò BOM**, không phải POM hoàn chỉnh:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-core</artifactId>
    </dependency>
</dependencies>
```

`4.1.2` chỉ là **ví dụ một phiên bản Spring Boot**; hãy đọc phiên bản thật từ POM dự án. Không cần khai báo `spring-core` trực tiếp nếu dependency khác đã kéo nó; đoạn trích chỉ minh họa cú pháp "không ghi version nhưng BOM có thể quản lý". BOM **không tự đưa tất cả dependency trong danh sách vào ứng dụng**.

Quan hệ ưu tiên cần nhớ:

- Phiên bản khai báo **tường minh trên dependency trực tiếp** trong POM của dự án có thể điều khiển phiên bản được dùng, thay cho giá trị quản lý.
- `dependencyManagement` trong effective POM có thể **quyết định phiên bản cho dependency bắc cầu**, ưu tiên hơn cơ chế nearest thông thường.
- `dependencyManagement` của POM hiện tại có thể ghi đè cấu hình quản lý kế thừa; khi nhập nhiều BOM có cùng mục, thứ tự và các khai báo trực tiếp trong dependency management ảnh hưởng kết quả. Luôn xem **effective POM** thay vì đoán bằng thứ tự nhìn thấy trên một file.
- `exclusions`, `optional`, `scope` và profile kích hoạt có thể đổi **sự có mặt** của node trước khi nói về phiên bản được chọn.

### Tìm nơi Maven quản lý phiên bản thực tế

```bash
# Xem mô hình POM đã áp dụng parent, profiles và phần quản lý kế thừa
./mvnw help:effective-pom -Doutput=effective-pom.xml

# Nếu cần giải thích vì sao profile cụ thể thay đổi dependency
./mvnw help:active-profiles

# Đối chiếu dependency thực dùng
./mvnw dependency:tree -Dincludes=org.springframework:spring-core
```

Tệp `effective-pom.xml` là đầu ra phục vụ phân tích. Trong đó tìm `<dependencyManagement>`, tọa độ `groupId/artifactId`, phiên bản và các khai báo liên quan. **Tìm được phiên bản ở effective POM mới chứng minh có quản lý**, chưa chứng minh dependency đó xuất hiện trên classpath; kết hợp với `dependency:tree`.

**Phân biệt plugin:** `dependencyManagement` của dự án không đồng nghĩa cấu hình phiên bản các dependency **của Maven plugin**. Các plugin có classpath riêng. Nếu câu hỏi là về plugin build, chỉ đọc cây dependency ứng dụng có thể không đủ.

## 4. Gradle: dùng `dependencies` cho đúng cấu hình

Trong dự án Gradle, đứng tại thư mục có `gradlew`, `settings.gradle[.kts]` và `build.gradle[.kts]`:

```bash
# Liệt kê những cấu hình và dependency chính của dự án
./gradlew dependencies

# Tập dependency để chạy ứng dụng Java/Spring Boot
./gradlew -q dependencies --configuration runtimeClasspath

# Tập dependency phục vụ compile
./gradlew -q dependencies --configuration compileClasspath

# Tập dependency cho test runtime
./gradlew -q dependencies --configuration testRuntimeClasspath
```

Windows PowerShell dùng `.\gradlew.bat` thay `./gradlew`. Tên cấu hình phụ thuộc plugin/ngôn ngữ/module; các tên ở đây là **thông dụng khi áp dụng Java plugin**, không mặc định tồn tại ở mọi Gradle project.

Chỉ chạy `./gradlew dependencies` không phải lúc nào cũng phù hợp để kết luận về phiên bản cho ứng dụng, vì báo cáo có thể chứa nhiều cấu hình, có cấu hình không phân giải được và cả dependency chỉ dùng cho kiểm thử. Khi đang điều tra **runtime**, hãy chỉ rõ `--configuration runtimeClasspath`.

### Cách đọc ký hiệu trong cây Gradle

Ví dụ đầu ra **mô phỏng** cho tình huống thư viện được yêu cầu ở bản 2.0 nhưng được chọn 3.0:

```text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- com.example:feature-a:1.0
|    \--- org.example:common-lib:2.0 -> 3.0
\--- com.example:feature-b:1.0
     \--- org.example:common-lib:3.0
```

Tọa độ `com.example`/`org.example` chỉ phục vụ mô hình minh họa. Diễn giải:

- `2.0 -> 3.0`: có đường yêu cầu phiên bản **2.0**, Gradle **chọn 3.0** trong cấu hình đang đọc.
- Dòng `common-lib:3.0` từ `feature-b` chỉ ra một đường khác yêu cầu phiên bản đó.
- Kết quả chỉ áp dụng cho `runtimeClasspath` của **project hiện tại**; không tự suy ra các configuration khác cũng chọn bản 3.0.

Các ký hiệu khác theo tài liệu Gradle:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `x -> y` | Yêu cầu phiên bản `x` nhưng thực tế chọn `y` |
| `(*)` | Cây con đã được mở ở vị trí khác nên không in lặp toàn bộ |
| `(c)` | **Constraint** tham gia quản lý phiên bản; bản thân dòng này không có nghĩa dependency được kéo vào |
| `(n)` | Dependency hoặc configuration **không phân giải được** theo ngữ cảnh báo cáo |
| `FAILED` | Một đường yêu cầu không thể được phân giải; cần xem nguyên nhân phía trên/trong log |

**Đừng nhầm `(c)` là thư viện thứ hai:** đây là thông tin constraint. Cũng đừng đọc `(*)` thành "dependency bị bỏ qua"; chỉ là nhánh lặp không được in đầy đủ lần nữa.

### Gradle multi-project và cấu hình không resolvable

Trong build nhiều module, truy vấn đúng project:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
```

`:app:` chỉ là tên module **ví dụ**; thay bằng đường dẫn project thực tế. `implementation`, `api` hoặc `testImplementation` thường là **bucket khai báo**, không phải báo cáo dependency đã phân giải trực tiếp. Nếu cố dùng `--configuration implementation` mà được thông báo không thể resolve, chọn `compileClasspath`, `runtimeClasspath` hoặc cấu hình resolvable tương ứng.

Để xem dependency phục vụ **chạy plugin Gradle** thay vì dependency **ứng dụng**, công cụ khác là:

```bash
./gradlew buildEnvironment
```

Không lấy `buildEnvironment` làm bằng chứng về dependency Java runtime. Trong các cấu hình có dependency resolution failure, báo cáo có thể chỉ có một phần thông tin; cần phân biệt "không có dependency" với "không thể phân giải dependency".

## 5. Gradle: dùng `dependencyInsight` để trả lời **vì sao**

`dependencies` cho bạn **bức tranh tổng thể**. Khi đã tìm được `group:module` cần điều tra, `dependencyInsight` truy ngược các đường yêu cầu và **lý do chọn phiên bản** trong **một configuration**.

```bash
# Phân tích một module cụ thể trên runtime classpath
./gradlew -q dependencyInsight \
  --dependency org.slf4j:slf4j-api \
  --configuration runtimeClasspath
```

Trên Windows PowerShell, viết trên một dòng để không phụ thuộc ký tự nối dòng của bash:

```powershell
.\gradlew.bat -q dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
```

Nếu `org.slf4j:slf4j-api` không có trong `runtimeClasspath` của ứng dụng, báo cáo có thể không tìm thấy kết quả; đó là bằng chứng **cho cấu hình đang hỏi**, chưa đủ nói thư viện không tồn tại ở bất kỳ cấu hình nào. Tham số `--dependency` có thể là `group:name` hoặc một phần tên; dùng đầy đủ tọa độ để tránh khớp nhầm nhiều module.

Các tùy chọn hữu ích:

```bash
# Rút gọn còn một đường kéo dependency vào (nếu nhiều đường)
./gradlew -q dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath --single-path

# Áp dụng cho một subproject cụ thể
./gradlew :app:dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
```

### Một báo cáo insight kể điều gì?

Ví dụ đầu ra **rút gọn, mô phỏng**:

```text
org.example:common-lib:3.0
   Selection reasons:
      - By conflict resolution: between versions 3.0 and 2.0

org.example:common-lib:3.0
\--- runtimeClasspath

org.example:common-lib:2.0 -> 3.0
\--- com.example:feature-a:1.0
     \--- runtimeClasspath
```

Đừng xem đây là log thật của một repo; Gradle thực có thể thêm bảng variant/attribute và trình bày nhiều đường khác nhau. Điều cần đọc là:

1. `org.example:common-lib:3.0` ở đầu cho biết **selected version**.
2. `Selection reasons` nêu **cơ chế** tham gia chọn version.
3. Phần cây phía dưới cho biết **đường nào yêu cầu** module đó.
4. `2.0 -> 3.0` chỉ ra yêu cầu 2.0 đã không được giữ nguyên.
5. Một cấu hình khác có thể cho ra kết quả khác; hãy ghi đầy đủ `project + configuration` khi báo cáo.

### Các lý do chọn phiên bản cần nhận diện

| `Selection reasons` hoặc dấu hiệu | Giải thích |
| --- | --- |
| `By conflict resolution` | Có nhiều yêu cầu phiên bản; thuật toán giải quyết xung đột đã chọn một phiên bản |
| `By constraint` | Constraint/BOM/metadata ràng buộc hoặc góp phần vào lựa chọn |
| `Forced` | Bản được ép qua cơ chế như `enforcedPlatform` hoặc quy tắc `force` |
| `Selected by rule` | Quy tắc phân giải đã tác động lựa chọn |
| `By ancestor` | Yêu cầu nghiêm ngặt (`strictly`) từ đường phụ thuộc ở phía trên ảnh hưởng phiên bản |
| `Was requested` | Yêu cầu dependency hoặc lý do `because(...)` được khai báo và được hiển thị |
| Variant/attributes | Giúp giải thích **biến thể artifact** phù hợp với consumer; không đồng nghĩa riêng với version |

Không phải lần chạy nào cũng có mọi dòng trên. `Selection reasons` có thể chứa **nhiều lý do**. Khi thấy `By constraint`, hãy tìm constraint đến từ đâu; khi thấy `Forced`, kiểm tra ai ép và vì sao. Đừng tự kết luận "Spring Boot BOM ép phiên bản" chỉ vì thấy BOM trong graph.

## 6. Maven và Gradle có thể chọn khác nhau trên cùng đồ thị

Vẫn dùng mô hình giả định:

```text
app
├── feature-a:1.0 -> common-lib:2.0
└── feature-b:1.0 -> common-lib:3.0
```

Giả sử **không có** BOM/constraint/force/loại trừ/phiên bản trực tiếp khác:

| Câu hỏi | Maven | Gradle |
| --- | --- | --- |
| Quy tắc thông thường khi phiên bản xung đột | Chọn đường **gần gốc nhất**; cùng độ sâu thì khai báo trước thắng | Thường chọn **phiên bản cao hơn** trong các yêu cầu có thể chấp nhận |
| Kết quả ví dụ nếu `feature-a` khai báo trước, cùng độ sâu | `common-lib:2.0` | `common-lib:3.0` |
| Báo cáo chính | `dependency:tree` | `dependencies --configuration ...` |
| Để giải thích xung đột | `-Dverbose` (nếu plugin hỗ trợ), `effective-pom`, nhánh trong tree | `dependencyInsight --dependency ... --configuration ...` |
| Cách phiên bản quản lý ảnh hưởng | `dependencyManagement` / Maven BOM có thể ưu tiên hơn nearest | Platform/BOM, dependency constraints, rules, force và rich versions tác động resolution |

**Không biến bảng này thành quy tắc tuyệt đối.** Với Gradle, yêu cầu `strictly`, `reject`, `enforcedPlatform`, `force` hoặc resolution rules có thể tạo kết quả thấp hơn, cao hơn, hoặc lỗi do các ràng buộc không tương thích. Với Maven, BOM và khai báo trực tiếp có thể làm phiên bản được chọn khác kết quả nearest. Đó là lý do **báo cáo hiện tại quan trọng hơn việc đoán thuật toán từ trí nhớ**.

## 7. Tác động của Spring Boot BOM trong hai hệ build

### Maven: quản lý phiên bản qua parent hoặc imported BOM

Trong dự án Maven, Spring Boot parent hoặc một BOM được import vào `dependencyManagement` giúp kiểm soát phiên bản của những tọa độ đã được Spring Boot quản lý. Một dependency được khai báo **không có `<version>`** vẫn có thể phân giải do phiên bản được quản lý. Nếu không được quản lý và cũng không có version ở nơi có thể áp dụng, Maven có thể báo thiếu phiên bản.

Quy trình chứng minh "BOM chọn phiên bản X":

1. Dùng `dependency:tree` để tìm **phiên bản đã phân giải và đường đi** của artifact.
2. Dùng `help:effective-pom` hoặc POM/BOM có hiệu lực để thấy **phiên bản quản lý**.
3. Kiểm tra dependency trực tiếp có ghi `<version>` không, `dependencyManagement` cục bộ có override không, và có profile nào tác động.
4. Kết luận dựa trên **cả kết quả resolution và cấu hình quản lý**, tránh nói "BOM kéo dependency" nếu chỉ có trong danh sách quản lý.

### Gradle: có hai cách quản lý phổ biến

**Cách A: `io.spring.dependency-management` plugin.** Khi áp dụng cùng Spring Boot Gradle plugin theo cách được hỗ trợ, plugin có thể nhập `spring-boot-dependencies` BOM tương ứng với phiên bản Spring Boot. Các dependency được quản lý có thể khai báo không ghi version; plugin xử lý việc quản lý và thay đổi phiên bản theo mô hình của nó.

**Cách B: hỗ trợ BOM gốc của Gradle.** Ví dụ **trích đoạn Groovy DSL**, giả sử build đã áp dụng Java/Spring Boot plugin và công cụ đã giải quyết được `SpringBootPlugin.BOM_COORDINATES`:

```groovy
dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Đoạn trên là **một phần cấu hình**, không phải `build.gradle` hoàn chỉnh. Với Gradle native BOM, `platform(...)` tạo **dependency constraints** (thông thường các phiên bản mang tính khuyến nghị/ràng buộc mềm), nên nếu một dependency khác yêu cầu phiên bản cao hơn và không bị ràng buộc nghiêm ngặt, Gradle có thể chọn bản khác với giá trị BOM. `enforcedPlatform(...)` nghiêm khắc hơn và có thể ép các phiên bản từ BOM; dùng có chủ đích vì có thể ảnh hưởng người tiêu thụ và khả năng tương thích.

**Điểm dễ sai:** chỉ áp dụng Spring Boot Gradle plugin **không đủ để kết luận** mọi dependency được version-managed theo cách A. Hãy xem project đang áp dụng `io.spring.dependency-management` hay dùng `platform`/`enforcedPlatform`, constraints/rules riêng. Đọc `dependencyInsight` để biết **phiên bản thực chọn**, đừng suy diễn từ mỗi dòng BOM.

### Ví dụ đường điều tra Spring Boot starter

Nếu ứng dụng có một starter chứa hoặc kéo thư viện logging, trước hết tìm dependency cụ thể trong `runtimeClasspath`:

```bash
# Maven
./mvnw dependency:tree -Dincludes=org.slf4j:slf4j-api

# Gradle
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
```

Sau đó mở phần quản lý của dự án: Maven effective POM/BOM; Gradle `platform`, plugin quản lý dependency, version constraints và resolution rules. **Không ghi sẵn số phiên bản SLF4J** vào kết luận: nó phụ thuộc bản Spring Boot, dependency cụ thể, cấu hình và override của dự án.

## 8. Điều tra thực tế theo quy trình ba bước

Giả sử bạn gặp lỗi tương thích và nghi ngờ `org.example:common-lib` bị chọn sai phiên bản. Tọa độ này chỉ là **ví dụ minh họa**. Cần trả lời rõ:

**Bước 1 – Cái gì đang được chọn, trong ngữ cảnh nào?**

Maven:

```bash
./mvnw dependency:tree -Dincludes=org.example:common-lib
```

Gradle:

```bash
./gradlew -q dependencies --configuration runtimeClasspath
```

Ghi lại dự án/module, cấu hình hoặc scope, tọa độ đầy đủ và phiên bản hiển thị.

**Bước 2 – Ai kéo vào và vì sao chọn phiên bản đó?**

Maven:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.example:common-lib
./mvnw help:effective-pom -Doutput=effective-pom.xml
```

Gradle:

```bash
./gradlew -q dependencyInsight --dependency org.example:common-lib --configuration runtimeClasspath
```

Theo các đường từ dependency trực tiếp đến dependency mục tiêu. Đối với Maven, đánh giá nearest, dependency management và phiên bản direct. Đối với Gradle, đọc dòng `x -> y` cùng `Selection reasons`, constraint/BOM/rules.

**Bước 3 – Kiểm tra sự hiện diện tại thời điểm chạy/test**

Đừng dừng ở việc phát hiện một phiên bản trong `testRuntimeClasspath` rồi khẳng định nó có mặt ở sản phẩm runtime. Với Spring Boot, xác định executable archive và classpath thực tế khi cần; đối chiếu báo cáo runtime với nội dung đóng gói và logs nếu nghi ngờ một dependency bị exclude/đóng gói khác. Nếu Gradle có module con, dùng đúng `:module:dependencyInsight`.

### Mẫu kết luận có bằng chứng

> Trong module `:app`, cấu hình `runtimeClasspath` chọn `org.example:common-lib:3.0`. Nhánh `feature-a` yêu cầu `2.0` nhưng bị đổi thành `3.0`. `dependencyInsight` ghi `By conflict resolution` và hiển thị thêm nhánh `feature-b` yêu cầu `3.0`. Vì vậy đây là trường hợp giải quyết xung đột phiên bản trong cấu hình runtime, **không phải bằng chứng rằng Spring Boot BOM tự ép `3.0`**.

Đoạn trên là **mẫu kết luận giả định** theo ví dụ mô phỏng; chỉ sử dụng trong báo cáo thật nếu CLI của chính dự án cho các dòng dữ liệu đó.

## 9. Các lỗi phân tích thường gặp

| Nhận định vội vàng | Vì sao sai / cách kiểm tra đúng |
| --- | --- |
| "POM/build script ghi A nên chắc chắn chạy A" | Có dependency management, BOM, transitive, constraints/rules. Xem **resolved tree** theo classpath. |
| "Maven luôn chọn bản mới nhất" | Maven dùng nearest/first tại cùng độ sâu khi không bị quy tắc quản lý khác tác động. |
| "Gradle luôn chọn bản cao nhất" | Chỉ là mặc định phổ biến khi xung đột thông thường; platform, strict constraints, enforced platform, force/rules có thể đổi kết quả. |
| "BOM có thư viện thì ứng dụng chắc chắn tải thư viện đó" | BOM/constraint thường chỉ quản lý phiên bản khi dependency thực sự được yêu cầu. |
| "`(c)` trong Gradle là bản JAR thứ hai" | `(c)` biểu thị constraint, không phải một dependency mới được thêm. |
| "`(*)` nghĩa là không có dependency đó" | `(*)` chỉ cây con lặp không được bung ra lần nữa. |
| "`2.0 -> 3.0` là Maven tự đổi dependency" | Đó là ký pháp thường gặp trong Gradle `dependencies`/insight; kiểm tra báo cáo của đúng công cụ. |
| "Không thấy ở `runtimeClasspath` thì thư viện không được dùng ở đâu" | Có thể chỉ nằm trong `testRuntimeClasspath`, compile-only, buildscript hoặc project khác. |
| "`dependencyInsight` không cần cấu hình" | Hãy truyền `--configuration` khi điều tra; một số plugin có mặc định nhưng đừng dựa vào nó để phân tích runtime. |
| "Thấy `Selected by rule` thì do BOM" | Rule có thể được code build/plugin thêm; phải tìm nguồn rule. |
| "Thấy `Forced` thì nên force phiên bản mong muốn để sửa ngay" | Cưỡng ép có thể tạo xung đột API/ABI. Xác định nguyên nhân và kiểm tra tương thích/test trước. |
| "Đổi một phiên bản là mọi module/configuration đổi theo" | Maven module và Gradle configuration có thể có mô hình quản lý/rules khác nhau. |
| "Lỗi `Could not resolve` có nghĩa dependency không tồn tại" | Có thể do offline/cache, repository, authentication, metadata, TLS, version constraints hoặc artifact thực sự không có. Đọc nguyên nhân. |

### Khi cần kiểm tra dependency không có trong báo cáo

1. Xác nhận lệnh đang chạy ở **đúng module**.
2. Kiểm tra dependency có chỉ được khai báo ở **test**, compile-only, annotation processor hoặc buildscript không.
3. Kiểm tra `exclusions`/`optional`/Maven scope, Gradle dependency constraints, capabilities/variants và profile.
4. Nếu có lỗi resolve, đừng tin cây bị thiếu là danh sách cuối cùng.
5. Nếu dependency bị loại vì conflict, tìm cả đường yêu cầu bị loại (`-Dverbose` nếu Maven plugin hỗ trợ; `dependencyInsight` trong Gradle).
6. Kiểm tra bạn đang chạy **Maven/Gradle Wrapper trong repo** hay một dự án khác đã thay file build từ lần chạy trước.

## 10. Bài thực hành: giải thích được phiên bản, không chỉ chụp kết quả

Sử dụng **một dự án Spring Boot Maven hoặc Gradle** hiện có (chọn đúng hệ build của dự án).

**Phần A – Thu thập bằng chứng:**

1. Chọn một dependency thật có mặt trong classpath, chẳng hạn một thư viện logging hoặc JSON mà starter đang kéo vào. Ghi tọa độ `group:artifact` chính xác.
2. Xem file `pom.xml` hoặc `build.gradle[.kts]`: dependency đó được khai báo trực tiếp hay chỉ đi qua starter? Có ghi version tường minh không?
3. Chạy Maven `dependency:tree` hoặc Gradle `dependencies --configuration runtimeClasspath`. Ghi lại **module**, **classpath**, **đường đi**, **phiên bản thực chọn**.
4. Nếu Maven, chạy `dependency:tree -Dverbose` (khi hỗ trợ) và `help:effective-pom` để truy nguồn phiên bản quản lý. Nếu Gradle, chạy `dependencyInsight --dependency ... --configuration runtimeClasspath`, ghi `Selection reasons` và mọi dấu `x -> y`.
5. Kiểm tra Spring Boot parent/BOM, Gradle platform hay plugin dependency management mà dự án thực sự áp dụng.

**Phần B – Giải thích nguyên nhân bằng câu đầy đủ:**

- "Thư viện X xuất hiện vì dependency Y kéo vào qua đường ...".
- "Ở module ..., cấu hình/runtime scope ..., phiên bản yêu cầu là ...; phiên bản cuối cùng là ...".
- "Bằng chứng phiên bản cuối cùng đến từ lệnh ...".
- "Bằng chứng quy tắc chọn nằm ở ... (nearest/BOM/direct/constraint/conflict/rule)...".
- "Tôi đã kiểm tra test/runtime khác nhau hay giống nhau bằng ...".

**Phần C – Thử nghiệm có kiểm soát (trên nhánh thực hành):**

Tạo một tình huống có hai yêu cầu version khác nhau của cùng module hoặc thay một constraint đã cho. Chạy lại tree/insight, ghi lại **trước → sau**. Đừng force một phiên bản chỉ để bài thực hành "thành công"; thay đổi dependency có thể gây lỗi runtime. Khi xong, hoàn nguyên thay đổi thực hành nếu không định đưa vào codebase.

**Tiêu chí hoàn thành:** người khác đọc báo cáo của bạn có thể tự chạy lại lệnh để kiểm chứng **ai kéo thư viện**, **phiên bản yêu cầu**, **phiên bản được chọn**, **cấu hình/classpath** và **nguyên nhân lựa chọn**. Một ảnh chụp `dependency:tree` hoặc `dependencies` mà không có giải thích cơ chế vẫn chưa đạt.

## Tài liệu chính thức để đối chiếu

- Maven Dependency Plugin – `dependency:tree`, bộ lọc, `-Dverbose` và định dạng xuất: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Maven – Dependency Mechanism (nearest definition, dependency management, BOM): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle – Viewing and Debugging Dependencies (`dependencies`, `dependencyInsight`, ký hiệu và selection reasons): https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Gradle – Dependency Constraints and Conflict Resolution: https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html
- Spring Boot – Managing Dependencies với Gradle (dependency-management plugin hoặc native BOM): https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html

**Ghi nhớ:** câu trả lời đáng tin cho "tại sao phiên bản này được chọn?" luôn ghép **kết quả resolution** với **nguồn yêu cầu và quy tắc quản lý**, trong **đúng module và classpath**.
