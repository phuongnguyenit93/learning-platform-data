# Đọc cây phụ thuộc và truy tìm đường dẫn dẫn đến một thư viện

Một ứng dụng Java thường sử dụng nhiều thư viện bên ngoài. Bạn có thể chỉ khai báo một vài dependency trực tiếp trong build script hoặc `pom.xml`, nhưng khi build tool phân giải chúng, nó còn tìm thêm các thư viện mà những dependency đó cần. Vì vậy, classpath thực tế có thể chứa hàng chục hoặc hàng trăm module mà bạn chưa từng khai báo trực tiếp.

Khi một thư viện xuất hiện trong ứng dụng, câu hỏi quan trọng không chỉ là “thư viện này có trong classpath không?” mà còn là “dependency nào đã đưa nó vào?”. Cây phụ thuộc (dependency tree) giúp nhìn thấy quan hệ trực tiếp và bắc cầu. Từ cây đó, bạn có thể lần theo đường đi từ project đến một thư viện cụ thể, hiểu vì sao nó được chọn, xác định phiên bản và scope/configuration, rồi quyết định cách xử lý nếu thư viện không mong muốn hoặc gây xung đột.

Ví dụ, build script chỉ khai báo `web-client`, nhưng cây phụ thuộc có thể trông như sau:

```text
my-app
└── web-client
    ├── http-core
    │   └── logging-api
    └── json-support
        └── logging-api
```

`logging-api` là dependency bắc cầu (transitive dependency). Có hai đường đi dẫn đến cùng một module. Build tool sẽ phân giải các yêu cầu đó và chọn một phiên bản phù hợp theo quy tắc của công cụ, cấu hình và metadata dependency.

## 1. Dependency trực tiếp và dependency bắc cầu

**Dependency trực tiếp** là thư viện mà project khai báo rõ ràng trong build script hoặc POM. Ví dụ Gradle:

```groovy
dependencies {
    implementation 'com.example:web-client:2.4.0'
}
```

Ví dụ Maven:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>web-client</artifactId>
    <version>2.4.0</version>
</dependency>
```

Khi `web-client` phụ thuộc vào `http-core` và `json-support`, các thư viện đó có thể được đưa vào graph mà không cần project khai báo từng thư viện riêng. Chúng là dependency bắc cầu của `my-app`.

```text
my-app
└── web-client:2.4.0                 (trực tiếp)
    ├── http-core:5.1.0              (bắc cầu)
    │   └── logging-api:1.3.0        (bắc cầu)
    └── json-support:3.2.0           (bắc cầu)
        └── logging-api:1.2.0        (bắc cầu)
```

Sơ đồ trên mô tả các phiên bản được yêu cầu trên từng nhánh. Nó chưa khẳng định cả hai phiên bản `logging-api` đều được đưa vào runtime classpath. Build tool cần giải quyết xung đột giữa những yêu cầu đó và thường chọn một phiên bản cho cùng module trong một configuration.

### Vì sao cần đọc dependency bắc cầu?

Dependency bắc cầu có thể ảnh hưởng đến:

- **Classpath:** lớp và tài nguyên nào có thể được ứng dụng sử dụng khi biên dịch hoặc chạy.
- **Kích thước artifact:** thư viện nào được đóng gói cùng ứng dụng, nếu kiểu đóng gói của dự án gom dependency.
- **Tương thích:** hai thư viện có thể yêu cầu các phiên bản API khác nhau của cùng một module.
- **Bảo mật:** một thư viện gián tiếp có thể chứa phiên bản có lỗ hổng.
- **Thời gian build:** graph lớn hơn có thể làm tăng thời gian phân giải, tải và xử lý dependency.
- **Tính tái lập:** thay đổi metadata hoặc version được chọn có thể làm thay đổi classpath dù mã nguồn project không đổi.

Không nên thêm mọi dependency bắc cầu thành dependency trực tiếp chỉ vì nhìn thấy chúng trong cây. Hãy khai báo trực tiếp khi mã nguồn của project thật sự sử dụng API của thư viện đó hoặc khi project cần kiểm soát version theo chính sách rõ ràng.

## 2. Cây phụ thuộc biểu diễn điều gì?

Dependency tree là cách trình bày một phần của dependency graph dưới dạng phân cấp. Mỗi nhánh cho biết dependency nào yêu cầu dependency tiếp theo.

Ví dụ:

```text
application
├── framework-web:4.2
│   ├── framework-core:4.2
│   │   └── logging-api:2.0
│   └── json-adapter:1.8
│       └── json-core:3.1
└── metrics-client:2.5
    └── logging-api:1.7 -> 2.0
```

Đọc từ trên xuống dưới:

1. `application` khai báo `framework-web:4.2` và `metrics-client:2.5`.
2. `framework-web` yêu cầu `framework-core` và `json-adapter`.
3. `framework-core` yêu cầu `logging-api:2.0`.
4. `metrics-client` yêu cầu `logging-api:1.7`, nhưng graph cuối cùng chọn `2.0` cho module đó. Mũi tên trong sơ đồ minh họa sự thay thế phiên bản; định dạng hiển thị thực tế phụ thuộc build tool.

Một cây phụ thuộc có thể cho biết:

- Dependency gốc nào đưa một module vào graph.
- Đường dẫn trực tiếp hoặc bắc cầu dẫn đến module.
- Phiên bản được khai báo/yêu cầu và phiên bản được chọn.
- Scope hoặc configuration mà dependency thuộc về.
- Một số lý do chọn version, chẳng hạn conflict resolution, constraint, rule hoặc platform.
- Dependency nào bị loại trừ, không được chọn hoặc không thuộc configuration đang xem, tùy mức chi tiết của báo cáo.

### Cây phụ thuộc không phải danh sách mọi JAR trên máy

Kết quả phụ thuộc vào project, configuration, repository, thuộc tính môi trường và các quy tắc phân giải đang có hiệu lực. Một thư viện có thể xuất hiện trong `runtimeClasspath` nhưng không xuất hiện trong `testRuntimeClasspath` của một module khác; một thư viện có thể được yêu cầu trong test nhưng không có trong production runtime.

Vì thế, khi điều tra một lỗi, hãy xem đúng configuration mà tác vụ đang sử dụng. Không kết luận rằng thư viện “không có trong dự án” chỉ vì nó không xuất hiện trong một cây phụ thuộc khác.

## 3. Đọc cây phụ thuộc bằng Gradle

Gradle cung cấp task `dependencies` để in dependency graph của một project configuration.

### Xem các configuration và dependency

Trong project Gradle có Java plugin, chạy:

```shell
./gradlew dependencies
```

Trên Windows:

```powershell
.\gradlew.bat dependencies
```

Lệnh này in báo cáo dependency theo các configuration có thể xem được. Dự án nhiều module có thể có rất nhiều configuration, vì vậy kết quả dài là bình thường.

Để giới hạn vào configuration thường dùng:

```shell
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Trên Windows:

```powershell
.\gradlew.bat dependencies --configuration compileClasspath
.\gradlew.bat dependencies --configuration runtimeClasspath
```

Hai configuration này trả lời hai câu hỏi khác nhau:

- `compileClasspath`: những dependency cần thiết để biên dịch source set `main`.
- `runtimeClasspath`: những dependency cần thiết để chạy source set `main`.

Ví dụ, một thư viện chỉ cần trong lúc biên dịch có thể xuất hiện ở `compileClasspath` mà không có trong `runtimeClasspath`, tùy cách khai báo dependency và mô hình plugin.

### Xem dependency của một module trong multi-project build

Nếu build có các module `app`, `domain` và `infra`, hãy chỉ rõ project:

```shell
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :domain:dependencies --configuration compileClasspath
```

Trên Windows:

```powershell
.\gradlew.bat :app:dependencies --configuration runtimeClasspath
```

Đường dẫn `:app:dependencies` chỉ task trong project `app`. Nếu bỏ đường dẫn project, bạn có thể xem dependency của project hiện tại hoặc root project, tùy thư mục và cách gọi wrapper.

### Nhận biết ký hiệu trong báo cáo Gradle

Gradle có thể dùng các ký hiệu để biểu thị trạng thái dependency. Một số dạng thường gặp:

| Dạng hiển thị | Cách hiểu |
|---|---|
| `group:module:1.2` | Module được phân giải ở version `1.2`. |
| `1.1 -> 1.2` | Có yêu cầu version `1.1`, nhưng version được chọn là `1.2`. |
| `(*)` | Nhánh đã được trình bày trước đó trong báo cáo được rút gọn để tránh lặp. |
| `(c)` | Constraint được hiển thị trong graph. |
| `FAILED` | Không phân giải được dependency hoặc có lỗi trong quá trình phân giải. |

Ký hiệu cụ thể có thể thay đổi theo loại dependency và phiên bản Gradle. Khi cần biết chính xác lý do chọn một phiên bản, hãy dùng `dependencyInsight` thay vì chỉ suy luận từ mũi tên trong cây.

## 4. Dùng `dependencyInsight` để tìm đường dẫn đến một thư viện trong Gradle

`dependencies` cho bạn cái nhìn tổng quan. Khi đã biết tên thư viện cần điều tra, task `dependencyInsight` giúp trả lời sâu hơn: module này được yêu cầu từ đâu và vì sao phiên bản cuối cùng được chọn?

Ví dụ, tìm `logging-api` trong runtime classpath của project:

```shell
./gradlew dependencyInsight --dependency logging-api --configuration runtimeClasspath
```

Trên Windows:

```powershell
.\gradlew.bat dependencyInsight --dependency logging-api --configuration runtimeClasspath
```

Trong multi-project build:

```shell
./gradlew :app:dependencyInsight --dependency logging-api --configuration runtimeClasspath
```

`--dependency` nhận chuỗi để lọc module cần tìm. Có thể dùng tên module hoặc một phần định danh phù hợp. `--configuration` xác định graph cần điều tra. Nếu không chỉ rõ configuration phù hợp, task có thể không tìm thấy dependency hoặc báo cáo một graph không liên quan đến lỗi.

### Đọc kết quả `dependencyInsight`

Ví dụ minh họa rút gọn:

```text
logging-api:2.0
  Variant runtime:
    Selection reasons:
      - By conflict resolution: between versions 1.7 and 2.0

logging-api:1.7 -> 2.0
\--- metrics-client:2.5
     \--- runtimeClasspath

logging-api:2.0
\--- framework-core:4.2
     \--- framework-web:4.2
          \--- runtimeClasspath
```

Đây chỉ là ví dụ minh họa định dạng. Ý nghĩa cần chú ý:

- `logging-api:2.0` là version được chọn trong configuration đang xem.
- `1.7 -> 2.0` cho thấy một nhánh yêu cầu `1.7`, nhưng kết quả phân giải là `2.0`.
- Các dòng thụt lề chỉ ra đường đi từ dependency gốc đến module đang được tìm.
- `Selection reasons` giải thích quy tắc hoặc yếu tố khiến Gradle chọn version đó.

Khi có nhiều đường dẫn, hãy ghi lại tất cả dependency gốc liên quan. Một module có thể được đưa vào graph qua nhiều thư viện khác nhau; chỉ loại bỏ một nhánh chưa chắc đã làm module biến mất.

### Lần theo đường dẫn từ project đến thư viện

Giả sử kết quả cho biết:

```text
com.example:logging-api:2.0
\--- com.example:framework-core:4.2
     \--- com.example:framework-web:4.2
          \--- runtimeClasspath
```

Bạn có thể diễn giải:

1. Project có dependency `framework-web` trong `runtimeClasspath`.
2. `framework-web` yêu cầu `framework-core`.
3. `framework-core` yêu cầu `logging-api`.
4. Do đó, `logging-api` được đưa vào ứng dụng qua đường dẫn `framework-web -> framework-core -> logging-api`.

Nếu có một đường đi khác qua `metrics-client`, hãy ghi lại riêng đường đi đó. Đây là căn cứ để quyết định nên cập nhật thư viện gốc, khai báo version trực tiếp, thêm constraint hay loại trừ một dependency.

## 5. Đọc cây phụ thuộc bằng Maven

Maven Dependency Plugin cung cấp goal `dependency:tree` để in cây dependency của project.

Chạy:

```shell
mvn dependency:tree
```

Kết quả minh họa:

```text
com.example:my-app:jar:1.0.0
+- com.example:web-client:jar:2.4.0:compile
|  +- com.example:http-core:jar:5.1.0:compile
|  |  \- com.example:logging-api:jar:2.0:compile
|  \- com.example:json-support:jar:3.2.0:compile
|     \- com.example:logging-api:jar:1.7:compile (omitted for conflict with 2.0)
\- com.example:metrics-client:jar:2.5.0:runtime
```

Định dạng trên minh họa cách Maven biểu diễn groupId, artifactId, type, version và scope. Cây thật có thể dài hơn và phụ thuộc vào phiên bản Maven Dependency Plugin.

### Lọc cây theo một thư viện

Nếu muốn tìm riêng `logging-api`, dùng `includes`:

```shell
mvn dependency:tree -Dincludes=com.example:logging-api
```

Có thể lọc theo group hoặc artifact. Ví dụ:

```shell
mvn dependency:tree -Dincludes=com.example:*
mvn dependency:tree -Dincludes=*:logging-api
```

Pattern include của Dependency Plugin hỗ trợ các thành phần tọa độ dependency; cú pháp cụ thể có thể mở rộng với type, classifier và version. Khi lọc, hãy dùng đúng `groupId` và `artifactId` của module.

### Hiển thị cả dependency bị loại do conflict

Maven thường rút gọn cây và ẩn các dependency bị loại khỏi kết quả cuối cùng. Thêm `-Dverbose` để xem các node bị bỏ qua và lý do:

```shell
mvn dependency:tree -Dverbose
```

Kết hợp với bộ lọc:

```shell
mvn dependency:tree -Dverbose -Dincludes=com.example:logging-api
```

Thông tin `omitted for conflict` giúp bạn thấy một nhánh đã yêu cầu version nào và version nào được chọn theo quy tắc mediation của Maven.

### Giới hạn theo scope

Maven dependency tree có thể được giới hạn theo scope:

```shell
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dscope=test
```

Các scope Maven như `compile`, `provided`, `runtime`, `test`, `system` và `import` có quy tắc truyền dependency khác nhau. Đọc cây theo đúng scope giúp bạn xác định thư viện có mặt khi biên dịch, chạy hoặc chỉ chạy kiểm thử.

## 6. Cách lần theo đường dẫn trong Maven

Giả sử cây phụ thuộc rút gọn là:

```text
com.example:my-app:jar:1.0.0
\- com.example:reporting:jar:3.0:compile
   \- com.example:chart-engine:jar:2.1:compile
      \- org.example:xml-parser:jar:4.0:compile
```

Đường dẫn đến `xml-parser` là:

```text
my-app
  -> reporting:3.0
  -> chart-engine:2.1
  -> xml-parser:4.0
```

Để điều tra:

1. Chạy `mvn dependency:tree -Dincludes=org.example:xml-parser`.
2. Nếu cần biết các nhánh bị loại, thêm `-Dverbose`.
3. Ghi lại dependency trực tiếp của project ở đầu mỗi nhánh.
4. Đọc scope để biết đường dẫn thuộc compile, runtime hay test.
5. Mở POM của dependency cha trong repository hoặc source tương ứng để xem khai báo dependency đã đưa thư viện vào.

Dependency tree thường đủ để tìm đường dẫn. Nếu cần xem dependency khai báo trong POM hiệu lực sau khi kế thừa parent, profile và dependency management, có thể dùng:

```shell
mvn help:effective-pom
```

Effective POM giúp hiểu cấu hình Maven sau khi áp dụng kế thừa và interpolation. Nó không thay thế dependency tree: POM cho biết cấu hình khai báo, còn dependency tree cho biết graph đã phân giải.

## 7. Hiểu version được yêu cầu và version được chọn

Một module có thể được nhiều dependency yêu cầu ở các version khác nhau. Ví dụ:

```text
web-framework -> logging-api:1.7
metrics-client -> logging-api:2.0
my-app        -> logging-api:1.5
```

Dependency graph cần một kết quả phân giải cho module `logging-api` trong configuration đang xét. Cách chọn version của Gradle và Maven khác nhau.

### Gradle: conflict resolution và selection reasons

Trong quy tắc mặc định, khi các dependency yêu cầu nhiều version của cùng module, Gradle thường chọn version cao nhất theo quy tắc so sánh version của nó. Các constraint, rich version, platform, resolution rule hoặc component metadata có thể ảnh hưởng kết quả.

Ví dụ `dependencyInsight` có thể hiển thị:

```text
logging-api:2.0
Selection reasons:
  - By conflict resolution: between versions 1.7 and 2.0
```

Điều này cho biết Gradle thấy ít nhất hai yêu cầu version và đã chọn `2.0` theo conflict resolution. Đừng chỉ dựa vào quy tắc “version cao hơn” nếu project có constraint hoặc rule tùy chỉnh; hãy đọc selection reasons trong báo cáo.

### Maven: nearest definition

Maven thường dùng quy tắc *nearest definition* (định nghĩa gần nhất): dependency xuất hiện ở độ sâu ít hơn tính từ project có ưu tiên. Nếu hai dependency có cùng độ sâu, thứ tự khai báo trong POM có thể quyết định dependency nào được chọn.

Ví dụ:

```text
my-app
├── library-a
│   └── common-util:1.4
└── library-b
    └── helper
        └── common-util:2.0
```

`common-util:1.4` ở độ sâu hai, còn `common-util:2.0` ở độ sâu ba. Theo nearest definition, Maven chọn `1.4`. Đây là một điểm khác biệt quan trọng với cách Gradle mặc định giải quyết xung đột version.

Nếu hai nhánh cùng yêu cầu `common-util` ở độ sâu bằng nhau, thứ tự khai báo dependency trong POM có thể ảnh hưởng kết quả. Để kiểm soát version rõ ràng, có thể dùng `dependencyManagement` hoặc khai báo dependency trực tiếp theo chính sách dự án.

### Không nhầm dependency management với dependency declaration

Trong Maven, phần `dependencyManagement` quản lý version và một số thuộc tính cho dependency khi chúng được khai báo. Chỉ đưa một dependency vào `dependencyManagement` không tự động thêm nó vào classpath.

Ví dụ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>common-util</artifactId>
            <version>2.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Module chỉ được sử dụng khi có dependency declaration trong `<dependencies>` ở project hoặc một dependency cha truyền xuống. `dependencyManagement` cung cấp quy tắc version cho declaration đó.

Gradle cũng có dependency constraints và platform để quản lý version tập trung. Constraint ảnh hưởng quá trình chọn version khi module được yêu cầu; bản thân constraint không nhất thiết thêm module vào graph.

## 8. Từ cây phụ thuộc đến quyết định sửa lỗi

Sau khi tìm được đường dẫn, hãy xác định mục tiêu trước khi thay đổi dependency. Các cách xử lý phổ biến gồm:

- Nâng version của dependency trực tiếp đã đưa thư viện cũ vào graph.
- Khai báo dependency trực tiếp nếu mã nguồn project sử dụng API của thư viện đó.
- Thêm constraint hoặc quản lý version tập trung để thống nhất phiên bản.
- Loại trừ dependency bắc cầu khi thật sự không cần nó và có giải pháp thay thế phù hợp.
- Chọn version tương thích của thư viện cha nếu nó không hỗ trợ version mới.
- Cập nhật plugin/platform/BOM quản lý một nhóm dependency.

Không nên thêm một `force` hoặc exclusion chỉ để làm cây trông gọn hơn. Thay đổi resolution có thể khiến thư viện cha không tương thích với version mới được chọn. Sau khi điều chỉnh, cần chạy lại kiểm thử phù hợp và đọc cây phụ thuộc mới để xác nhận kết quả.

## 9. Loại trừ dependency bắc cầu trong Gradle

Nếu một dependency cụ thể không cần module bắc cầu nào đó, Gradle cho phép khai báo exclusion trên dependency:

```groovy
dependencies {
    implementation('com.example:legacy-client:1.8.0') {
        exclude group: 'org.example', module: 'old-logging-bridge'
    }
}
```

Exclusion trên dependency này loại module khỏi nhánh được khai báo. Nếu một dependency khác cũng đưa `old-logging-bridge` vào graph, module vẫn có thể xuất hiện qua nhánh kia. Vì vậy, sau khi thêm exclusion, hãy chạy lại `dependencies` hoặc `dependencyInsight` để xác nhận module đã biến mất khỏi configuration.

Không nên exclude một thư viện chỉ vì bạn không thấy nó được import trực tiếp. Một dependency cha có thể cần nó ở runtime hoặc dùng reflection/service loading. Hãy đọc tài liệu của thư viện cha và kiểm tra chức năng thực tế trước khi loại bỏ.

## 10. Loại trừ dependency bắc cầu trong Maven

Trong Maven, exclusion được khai báo bên trong dependency cha:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.8.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.example</groupId>
            <artifactId>old-logging-bridge</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Exclusion áp dụng cho nhánh dependency được khai báo. Nếu một dependency khác đưa cùng module vào graph, nó vẫn có thể còn trong cây. Dùng lại:

```shell
mvn dependency:tree -Dincludes=org.example:old-logging-bridge -Dverbose
```

để kiểm tra còn đường dẫn nào khác hay không.

Nếu ứng dụng cần thư viện thay thế, hãy khai báo dependency thay thế một cách rõ ràng và bảo đảm API tương thích. Exclusion chỉ loại một nhánh; nó không tự cung cấp chức năng thay thế.

## 11. Phân biệt scope và configuration khi điều tra

Một thư viện có thể có mặt trong một classpath nhưng không có mặt trong classpath khác. Đây là lý do cần chọn đúng scope/configuration khi đọc cây.

### Gradle configurations thường gặp

Với Java plugin, một số configuration quen thuộc:

| Configuration | Mục đích |
|---|---|
| `compileClasspath` | Dependency cần khi biên dịch mã nguồn chính. |
| `runtimeClasspath` | Dependency cần khi chạy ứng dụng chính. |
| `testCompileClasspath` | Dependency cần khi biên dịch mã kiểm thử. |
| `testRuntimeClasspath` | Dependency cần khi chạy kiểm thử. |
| `annotationProcessor` | Bộ xử lý annotation dùng khi biên dịch source set chính. |

Các configuration này được tạo bởi Java plugin và plugin liên quan. Dự án có thể thêm configuration riêng hoặc dùng plugin framework có mô hình khác.

Ví dụ, thư viện test framework thường được khai báo bằng `testImplementation`, nên không xuất hiện trong `runtimeClasspath` của ứng dụng chính. Nếu tìm nó trong configuration đó, kết quả có thể rỗng dù thư viện vẫn được dùng khi chạy test.

### Maven scopes thường gặp

| Scope | Ý nghĩa khái quát |
|---|---|
| `compile` | Mặc định; có trong compile classpath và thường được truyền bắc cầu. |
| `provided` | Cần khi biên dịch và test nhưng môi trường chạy dự kiến cung cấp. |
| `runtime` | Không cần cho compile classpath của project hiện tại nhưng cần khi chạy. |
| `test` | Chỉ dùng cho compile/test runtime của kiểm thử, không truyền như dependency runtime thông thường. |
| `system` | Tham chiếu JAR theo đường dẫn cục bộ; thường khó di chuyển và không khuyến khích. |
| `import` | Dùng trong `dependencyManagement` để nhập BOM có packaging `pom`. |

Scope có quy tắc truyền dependency theo quan hệ giữa project cha và project tiêu thụ. Khi đọc cây, hãy để ý scope ở từng nhánh thay vì chỉ nhìn tên module.

## 12. Tìm nguồn gốc một thư viện có lỗ hổng hoặc không mong muốn

Khi công cụ bảo mật báo một thư viện có vấn đề, báo cáo thường cung cấp tọa độ như `group:artifact:version`. Hãy dùng đúng tọa độ đó để tìm dependency graph.

Ví dụ với Gradle:

```shell
./gradlew :app:dependencyInsight \
  --dependency vulnerable-library \
  --configuration runtimeClasspath
```

Với Maven:

```shell
mvn dependency:tree -Dverbose -Dincludes=org.example:vulnerable-library
```

Quy trình điều tra:

1. Xác nhận tọa độ và version bị báo cáo.
2. Xác định module và configuration/scope bị ảnh hưởng.
3. Tìm mọi đường dẫn từ dependency trực tiếp đến module có vấn đề.
4. Xác định version được yêu cầu ở từng nhánh và version cuối cùng được chọn.
5. Tìm dependency gốc có thể nâng cấp hoặc cấu hình quản lý version.
6. Chọn cách sửa ít ảnh hưởng nhất: nâng thư viện cha, constraint/BOM hoặc exclusion có chủ đích.
7. Chạy lại dependency report và các kiểm thử cần thiết.
8. Lưu lại version cuối cùng, source của dependency và bằng chứng xác nhận vấn đề đã được xử lý.

Một thư viện có thể xuất hiện trong nhiều configuration hoặc nhiều module. Đừng chỉ sửa một module nếu báo cáo bảo mật cho thấy nhiều artifact có cùng dependency bắc cầu.

## 13. Xuất báo cáo dependency để chia sẻ hoặc lưu trữ

Khi điều tra trên CI hoặc cần gửi thông tin cho đồng đội, bạn có thể lưu dependency tree vào tệp.

PowerShell:

```powershell
.\gradlew.bat :app:dependencies --configuration runtimeClasspath |
    Out-File -Encoding utf8 runtime-dependencies.txt
```

Linux/macOS:

```shell
./gradlew :app:dependencies --configuration runtimeClasspath \
  > runtime-dependencies.txt
```

Maven:

```shell
mvn dependency:tree -Dverbose > dependency-tree.txt
```

Hãy lưu ý rằng báo cáo phụ thuộc có thể chứa tên module nội bộ, repository hoặc thông tin về cấu trúc hệ thống. Chỉ chia sẻ theo chính sách của dự án. Không đưa credentials hoặc token vào lệnh hay báo cáo.

Với Maven, có thể xuất cây theo định dạng khác nếu plugin phiên bản đang dùng hỗ trợ, ví dụ dạng JSON hoặc DOT. Xem trợ giúp của goal để biết các tham số chính xác:

```shell
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-dependency-plugin -Dgoal=tree -Ddetail
```

## 14. Một quy trình thực tế để truy tìm dependency

Khi cần biết một thư viện đến từ đâu, thực hiện tuần tự:

1. **Xác định module:** lỗi hoặc báo cáo xảy ra ở module nào?
2. **Xác định classpath:** compile, runtime, test hay configuration riêng?
3. **Lấy tọa độ thư viện:** group, artifact và version từ log hoặc báo cáo.
4. **In cây tổng quan:** dùng Gradle `dependencies` hoặc Maven `dependency:tree`.
5. **Lọc thư viện cần tìm:** dùng Gradle `dependencyInsight` hoặc Maven `-Dincludes`.
6. **Lần ngược từng nhánh:** tìm dependency trực tiếp đầu tiên đã đưa thư viện vào graph.
7. **Đọc lý do chọn version:** xem conflict, constraint, platform, nearest definition hoặc selection reason.
8. **Chọn cách xử lý:** nâng dependency cha, quản lý version, thêm dependency trực tiếp hoặc exclusion khi phù hợp.
9. **Tái tạo báo cáo:** xác nhận graph sau thay đổi.
10. **Kiểm tra hành vi:** chạy compile, test và các kiểm thử runtime liên quan.

Ví dụ, nếu `xml-parser:4.0` xuất hiện trong ứng dụng nhưng không được khai báo trực tiếp, dependencyInsight có thể chỉ ra đường đi `reporting -> chart-engine -> xml-parser`. Bạn có thể kiểm tra phiên bản `reporting` mới hơn có loại bỏ dependency cũ hoặc nâng parser lên version đã được hỗ trợ hay không. Nếu cần loại bỏ nhánh, xác nhận `chart-engine` không cần parser đó ở runtime trước khi thêm exclusion.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Dependency không khai báo trong build script thì không thể có trong classpath | Dependency bắc cầu có thể được đưa vào bởi thư viện trực tiếp. |
| Dependency tree chỉ hiển thị những gì project khai báo | Nó hiển thị graph đã phân giải cho configuration/scope đang xem, gồm dependency bắc cầu. |
| Một thư viện xuất hiện hai lần nghĩa là có hai JAR cùng version trong classpath | Hai nhánh có thể yêu cầu cùng module; build tool thường phân giải thành một version cho graph tương ứng. |
| Chạy một cây dependency bất kỳ đủ để giải thích lỗi | Phải chọn đúng module và compile/runtime/test configuration hoặc Maven scope. |
| Version được yêu cầu luôn là version được chọn | Conflict resolution, constraints, platform hoặc Maven mediation có thể chọn version khác. |
| Gradle và Maven luôn chọn version xung đột theo cùng quy tắc | Gradle mặc định thường chọn version cao nhất; Maven thường dùng nearest definition. |
| Exclusion ở một nhánh sẽ xóa module khỏi toàn bộ graph | Một nhánh khác vẫn có thể đưa module vào. |
| Đưa version vào Maven `dependencyManagement` tự thêm thư viện vào classpath | `dependencyManagement` quản lý version cho dependency được khai báo; nó không tự thêm dependency. |
| `compileClasspath` và `runtimeClasspath` giống nhau | Hai configuration có mục đích khác nhau và có thể chứa tập dependency khác nhau. |
| Nâng version trực tiếp luôn giải quyết được dependency bắc cầu | Thư viện cha, constraint hoặc quy tắc resolution có thể vẫn ảnh hưởng; phải kiểm tra graph sau thay đổi. |

## 16. Bài thực hành

Thực hành trên một dự án Java có ít nhất hai dependency trực tiếp và một dependency bắc cầu:

1. Chạy `./gradlew dependencies --configuration runtimeClasspath` hoặc `mvn dependency:tree` để xem cây tổng quan.
2. Chọn một thư viện không được khai báo trực tiếp trong build script/POM và tìm nhánh đưa nó vào graph.
3. Với Gradle, chạy `dependencyInsight --dependency <module> --configuration runtimeClasspath`. Với Maven, dùng `dependency:tree -Dincludes=<groupId>:<artifactId> -Dverbose`.
4. Ghi lại tất cả đường dẫn dẫn đến thư viện, version được yêu cầu ở mỗi nhánh và version được chọn.
5. Tìm một module được yêu cầu ở hai version khác nhau. So sánh quy tắc chọn version của Gradle và Maven.
6. Xem cùng thư viện trong compile classpath và runtime classpath. Giải thích vì sao kết quả có thể khác nhau.
7. Tạo một exclusion trong ví dụ thử nghiệm. Chạy lại cây và xác định module còn được đưa vào qua nhánh nào khác không.
8. Trong Maven, thêm một version vào `dependencyManagement` rồi kiểm tra rằng nó không tự xuất hiện nếu chưa có dependency declaration.
9. Thử nâng dependency trực tiếp đã đưa thư viện cũ vào graph. Kiểm tra lại version được chọn và chạy test.
10. Lưu dependency tree thành tệp và ghi chú đường dẫn dependency để một thành viên khác có thể tái hiện kết quả.

Sau bài thực hành, bạn cần đọc được quan hệ trực tiếp/bắc cầu, xác định đúng configuration hoặc scope, lần theo mọi đường dẫn dẫn đến một thư viện, giải thích vì sao version được chọn và biết cách xác nhận một thay đổi dependency đã có hiệu lực. Đây là kỹ năng nền tảng để xử lý xung đột thư viện, điều tra lỗ hổng bảo mật và kiểm soát classpath trong dự án Java.
