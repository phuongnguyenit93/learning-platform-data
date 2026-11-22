# Thư mục chứa mã được sinh tự động và thời điểm tạo mã

Trong một dự án Java, không phải mọi tệp mã nguồn đều do lập trình viên viết trực tiếp. Một số tệp được tạo từ schema, API specification, file cấu hình, annotation hoặc metadata của quá trình build. Ví dụ, công cụ có thể sinh Java class từ OpenAPI, Protocol Buffers, Avro, hoặc annotation processor có thể tạo implementation cho một interface.

Những tệp này được gọi là **generated source** — mã nguồn được sinh tự động. Chúng vẫn có thể được compiler biên dịch như mã Java thông thường, nhưng cách quản lý và thời điểm xuất hiện phụ thuộc vào công cụ sinh mã và build tool.

Hiểu vị trí lưu trữ và thời điểm tạo mã giúp trả lời các câu hỏi thực tế:

- Vì sao một package chỉ xuất hiện sau khi chạy Gradle hoặc Maven?
- Vì sao IDE báo không tìm thấy một lớp được sinh tự động dù mã nguồn đã khai báo sử dụng lớp đó?
- Khi nào cần chạy tác vụ generate riêng, khi nào chỉ cần compile?
- Có nên sửa trực tiếp một tệp trong `build/generated` hoặc `target/generated-sources` không?
- Vì sao thư mục chứa mã được sinh tự động biến mất sau khi chạy `clean`?

## 1. Mã được sinh tự động là gì?

Mã được sinh tự động là đầu ra của một công cụ hoặc một bước xử lý dựa trên đầu vào có cấu trúc. Thay vì tự viết mọi class, method hoặc resource, lập trình viên khai báo thông tin ở một dạng phù hợp hơn; công cụ sẽ chuyển thông tin đó thành tệp mà ứng dụng có thể sử dụng.

Một số ví dụ phổ biến:

| Đầu vào | Công cụ hoặc cơ chế | Đầu ra có thể được tạo |
|---|---|---|
| OpenAPI specification | OpenAPI Generator hoặc plugin tương ứng | Java client, model, interface hoặc server stub |
| `.proto` schema | Protocol Buffers compiler/plugin | Java message class và service stub |
| Avro schema | Avro code generator | Java class biểu diễn record |
| Java annotation | Annotation processor như MapStruct hoặc Dagger | Implementation class, factory hoặc component |
| Database schema | Công cụ như jOOQ code generation | Java class biểu diễn bảng, record và kiểu dữ liệu |
| Template và thông tin build | Tác vụ Gradle/Maven tự định nghĩa | Java class chứa version, build metadata hoặc cấu hình đã chuẩn hóa |
| Resource/configuration | Plugin hoặc tác vụ build | Tệp resource, metadata hoặc descriptor |

Ví dụ, một dự án có thể định nghĩa API trong `api/openapi.yml`. Công cụ đọc specification rồi sinh ra các class Java tương ứng. Khi API thay đổi, lập trình viên sửa specification và chạy lại bước generate. Các class được sinh sẽ phản ánh specification mới.

Điểm quan trọng là mã nguồn được sinh có **nguồn đầu vào có thể tái tạo**. Nguồn đó có thể là schema, specification, annotation, template, cấu hình hoặc dữ liệu của dự án. Khi cần thay đổi hành vi của mã được sinh, thông thường phải sửa đầu vào hoặc cấu hình công cụ sinh mã, rồi chạy lại quá trình generate.

## 2. Phân biệt mã nguồn, mã nguồn được sinh và bytecode

Ba loại tệp thường xuất hiện cạnh nhau trong dự án Java nhưng có mục đích khác nhau:

| Loại | Ví dụ | Vai trò |
|---|---|---|
| Mã nguồn do lập trình viên viết | `src/main/java/com/example/OrderService.java` | Đầu vào trực tiếp cho compiler |
| Mã nguồn được sinh | `build/generated/sources/.../OrderMapperImpl.java` | Đầu ra của generator hoặc annotation processor; sau đó có thể được compiler biên dịch |
| Bytecode đã biên dịch | `build/classes/java/main/com/example/OrderService.class` | Đầu ra `.class` mà JVM có thể nạp và thực thi |

Mã nguồn được sinh vẫn là mã nguồn. Tệp `OrderMapperImpl.java` có thể được mở và đọc như một tệp Java, nhưng nó thường được tạo lại từ annotation hoặc cấu hình. Tệp `OrderMapperImpl.class` là kết quả của bước biên dịch mã nguồn đó.

Không nên nhầm thư mục chứa mã nguồn được sinh với thư mục chứa class file. Ví dụ, trong Gradle Java plugin, hai vị trí thường gặp là:

```text
build/
├── generated/
│   └── sources/
│       └── annotationProcessor/
│           └── java/
│               └── main/
│                   └── com/example/OrderMapperImpl.java
└── classes/
    └── java/
        └── main/
            └── com/example/OrderMapperImpl.class
```

Đường dẫn cụ thể có thể khác khi dự án dùng plugin hoặc generator khác. Cần xem cấu hình build và output của tác vụ thực tế để xác định chính xác.

Ngoài mã nguồn và bytecode, build còn có thể sinh resource, metadata, file cấu hình, báo cáo, descriptor hoặc artifact đóng gói. Những loại đầu ra này cũng cần được đặt ở vị trí và gắn với tác vụ phù hợp.

## 3. Những vị trí thường chứa mã được sinh tự động

### 3.1. Trong dự án Gradle

Với dự án sử dụng Java plugin của Gradle, thư mục `build/` là vùng lưu sản phẩm build mặc định. Đây là nơi phù hợp để đặt đầu ra do các tác vụ build tạo ra, vì `clean` có thể xóa vùng này và các lần build sau có thể tái tạo đầu ra.

Một số đường dẫn thường gặp:

| Đường dẫn | Nội dung thường gặp |
|---|---|
| `build/generated/sources/` | Java source hoặc source của ngôn ngữ khác được sinh bởi plugin/tác vụ |
| `build/generated/sources/annotationProcessor/java/main/` | Java source được sinh trong quá trình annotation processing cho source set `main` |
| `build/generated/sources/annotationProcessor/java/test/` | Java source được sinh trong quá trình annotation processing cho source set `test` |
| `build/generated/resources/main/` | Resource được sinh cho source set `main`, nếu dự án cấu hình vị trí này |
| `build/classes/java/main/` | Bytecode của mã nguồn chính sau khi biên dịch |
| `build/classes/java/test/` | Bytecode của mã nguồn kiểm thử sau khi biên dịch |
| `build/libs/` | JAR hoặc artifact đóng gói |

Đây là các quy ước thường dùng của Gradle Java plugin và các plugin liên quan, không phải quy tắc bắt buộc cho mọi generator. Một plugin có thể sử dụng thư mục con riêng bên dưới `build/`; dự án cũng có thể cấu hình một output directory khác.

### 3.2. Trong dự án Maven

Maven thường đặt sản phẩm build dưới thư mục `target/`. Một số vị trí phổ biến:

| Đường dẫn | Nội dung thường gặp |
|---|---|
| `target/generated-sources/` | Mã nguồn được sinh cho source set chính |
| `target/generated-sources/annotations/` | Mã nguồn được sinh bởi annotation processing trong cấu hình Maven Compiler Plugin thông thường |
| `target/generated-test-sources/` | Mã nguồn được sinh cho kiểm thử |
| `target/classes/` | Bytecode và resource đã xử lý của ứng dụng chính |
| `target/test-classes/` | Bytecode và resource của kiểm thử |
| `target/` | JAR, WAR, báo cáo và các sản phẩm build khác |

Tên thư mục và cách tích hợp source root phụ thuộc plugin Maven. Khi một plugin sinh mã, plugin thường đăng ký thư mục output để Maven compiler biết cần biên dịch những tệp nào.

### 3.3. Thư mục do IDE hoặc plugin riêng tạo ra

IDE có thể đánh dấu một thư mục là **Generated Sources Root** để hỗ trợ autocomplete, điều hướng và phân tích kiểu. Một số plugin cũng có thể tạo mã vào thư mục riêng trong dự án hoặc trong vùng build của IDE.

Việc IDE đánh dấu thư mục là generated source chỉ giúp IDE hiểu vai trò của thư mục. Điều đó không tự động chứng minh rằng Gradle hoặc Maven cũng đã đưa thư mục ấy vào source set khi build từ command line. Build tool vẫn cần được cấu hình đúng để quá trình biên dịch độc lập với IDE.

Không có một tên thư mục duy nhất áp dụng cho mọi loại generated source. Khi điều tra, hãy tìm cấu hình của plugin/tác vụ và kiểm tra output thực tế thay vì suy luận chỉ từ tên package hoặc tên thư mục trong IDE.

## 4. Thời điểm mã được sinh ra trong quy trình build

Mã được sinh có thể xuất hiện ở nhiều thời điểm. Cần phân biệt tác vụ sinh mã độc lập với annotation processing được thực hiện bên trong lần biên dịch Java.

### 4.1. Sinh mã trước khi biên dịch

Một generator có thể chạy thành tác vụ riêng. Ví dụ, generator đọc OpenAPI specification và ghi các tệp `.java` vào `build/generated/sources/openapi/main`.

Luồng khái quát:

```text
OpenAPI specification / schema / template
                 |
                 v
           Tác vụ generate
                 |
                 v
     build/generated/sources/...
                 |
                 v
             compileJava
                 |
                 v
       build/classes/java/main
```

Trong trường hợp này, tác vụ generate phải hoàn tất trước khi `compileJava` đọc các source file được sinh. Build tool cần biết quan hệ phụ thuộc giữa hai tác vụ. Nếu chạy compile mà không có quan hệ đó, compiler có thể bắt đầu trước khi tệp nguồn được tạo và báo lỗi không tìm thấy lớp hoặc package.

### 4.2. Sinh mã trong quá trình annotation processing

Annotation processor là cơ chế mở rộng của Java compiler. Processor đọc annotation và thông tin kiểu trong quá trình biên dịch, sau đó có thể tạo thêm tệp nguồn hoặc resource.

Ví dụ, MapStruct đọc mapper interface và annotation liên quan, rồi tạo implementation class. Tệp implementation có thể xuất hiện trong thư mục generated source của annotation processor khi `compileJava` đang chạy.

Luồng xử lý khái quát:

```text
Java source + annotation + annotation processor
                    |
                    v
                compileJava
                    |
                    v
           Java compiler gọi processor
                    |
                    v
       Processor tạo thêm Java source
                    |
                    v
      Compiler xử lý các source được sinh
                    |
                    v
              .class files
```

Trong Java compiler, annotation processing có thể diễn ra qua nhiều vòng. Một processor tạo source ở vòng hiện tại; compiler có thể đưa source mới vào các vòng xử lý tiếp theo. Vì vậy, với annotation processor, không nhất thiết phải có một tác vụ Gradle riêng mang tên `generateSources` chạy trước `compileJava`.

Với Java plugin của Gradle, processor thường được khai báo qua cấu hình `annotationProcessor` cho mã chính và `testAnnotationProcessor` cho mã kiểm thử. Ví dụ cấu trúc khai báo:

```groovy
dependencies {
    annotationProcessor 'group:processor-artifact:version'
    testAnnotationProcessor 'group:test-processor-artifact:version'
}
```

Các tọa độ dependency ở trên là chỗ giữ chỗ để thể hiện cấu trúc khai báo. Dự án cần thay bằng processor artifact và version thực tế. Annotation processor cần nằm trên processor path tương ứng; chỉ thêm một thư viện vào compile classpath không phải lúc nào cũng đủ để kích hoạt nó.

### 4.3. Sinh resource và đóng gói

Không phải generator nào cũng tạo `.java`. Một tác vụ có thể tạo resource như file properties, JSON, certificate metadata hoặc descriptor. Những tệp này cần được tạo trước tác vụ xử lý/đóng gói resource tương ứng.

Ví dụ luồng tổng quát:

```text
Thông tin đầu vào
       |
       v
generateResources
       |
       v
build/generated/resources/main
       |
       v
processResources
       |
       v
build/resources/main
       |
       v
JAR chứa resource đã xử lý
```

Thứ tự thực tế phụ thuộc cấu hình tác vụ và plugin. Nếu resource được sinh nhưng không được khai báo là đầu vào của `processResources`, tệp có thể tồn tại trên đĩa nhưng không xuất hiện trong JAR.

### 4.4. Sinh mã trong lúc chạy ứng dụng

Một số thư viện tạo class hoặc proxy trong lúc ứng dụng đang chạy. Ví dụ, framework có thể tạo proxy cho dependency injection, lazy loading hoặc interception. Những class này có thể được tạo trong bộ nhớ hoặc ghi ra một thư mục tạm tùy triển khai.

Đây là **runtime code generation**, khác với source generation trong quá trình build. Không nên mặc định rằng class được tạo lúc runtime sẽ xuất hiện trong `build/generated/sources`. Nếu cần chẩn đoán, phải xem cơ chế của framework và log/runtime configuration tương ứng.

## 5. Gradle xác định khi nào cần sinh mã như thế nào?

Gradle tổ chức build bằng task graph. Mỗi task biểu diễn một công việc; task có thể khai báo đầu vào, đầu ra và phụ thuộc vào task khác.

Ví dụ quan hệ:

```text
generateApiSources
        |
        | compileJava phụ thuộc vào task này
        v
    compileJava
        |
        v
      classes
        |
        v
        jar
```

Khi người dùng yêu cầu `jar`, Gradle xác định các task cần chạy để tạo JAR. Nếu `compileJava` phụ thuộc vào `generateApiSources`, task generate sẽ được đưa vào task graph và chạy trước khi compile cần sử dụng đầu ra của nó.

Gradle không chạy mọi task có tên bắt đầu bằng `generate` trong mọi lần build. Một task chỉ chạy khi được yêu cầu trực tiếp hoặc cần thiết thông qua quan hệ phụ thuộc của task khác.

### 5.1. Đăng ký đầu ra và quan hệ phụ thuộc

Ví dụ dưới đây minh họa một task Gradle tạo một Java class từ version của dự án. Đây là generator đơn giản để thể hiện cách khai báo đầu vào, đầu ra và thứ tự; trong dự án thực tế, phần thân task có thể gọi OpenAPI Generator, Protocol Buffers compiler hoặc công cụ chuyên dụng khác.

```groovy
plugins {
    id 'java'
}

def generatedSourcesDir = layout.buildDirectory.dir(
    'generated/sources/buildInfo/main'
)

tasks.register('generateBuildInfo') {
    inputs.property('projectVersion', project.version.toString())
    outputs.dir(generatedSourcesDir)

    doLast {
        def javaFile = generatedSourcesDir.get()
            .file('com/example/generated/BuildInfo.java')
            .asFile

        javaFile.parentFile.mkdirs()
        javaFile.text = """package com.example.generated;

public final class BuildInfo {
    public static final String VERSION = "${project.version}";

    private BuildInfo() {
    }
}
"""
    }
}

sourceSets {
    main {
        java.srcDir(generatedSourcesDir)
    }
}

tasks.named('compileJava') {
    dependsOn(tasks.named('generateBuildInfo'))
}
```

Các phần quan trọng:

- `generatedSourcesDir` xác định thư mục chứa Java source được sinh bên dưới `build/`.
- `inputs.property(...)` khai báo version là đầu vào của generator. Khi version thay đổi, Gradle có thể xác định task cần chạy lại.
- `outputs.dir(...)` khai báo thư mục mà task tạo ra. Gradle dùng thông tin này cho kiểm tra up-to-date và cơ chế build cache khi task đáp ứng các điều kiện tương ứng.
- `doLast` thực hiện việc ghi tệp trong giai đoạn thực thi task, không phải ngay khi Gradle đọc build script.
- `sourceSets.main.java.srcDir(...)` thêm thư mục generated source vào Java source set chính.
- `compileJava.dependsOn(...)` bảo đảm task generate chạy trước khi biên dịch.

Sau khi cấu hình, có thể chạy:

```bash
./gradlew generateBuildInfo
./gradlew compileJava
```

Lệnh đầu chỉ yêu cầu generator. Lệnh thứ hai cũng kéo generator vào task graph do `compileJava` phụ thuộc vào nó. Trong dự án thật, thường chỉ cần yêu cầu task cấp cao như `classes`, `build` hoặc tác vụ chạy ứng dụng; Gradle sẽ tự tính các dependency cần thiết.

Khi một task có kiểu dữ liệu riêng, nên khai báo input/output bằng các property chuyên dụng như `RegularFileProperty`, `DirectoryProperty`, `Property` và annotation `@Input`, `@OutputDirectory`. Cách đó giúp hợp đồng task rõ ràng hơn và hỗ trợ incremental build, configuration cache hoặc build cache tốt hơn so với một task chỉ có logic tùy ý trong `doLast`.

### 5.2. Không tạo mã ngay trong configuration phase

Gradle có giai đoạn cấu hình và giai đoạn thực thi. Trong configuration phase, Gradle đọc build script, tạo mô hình project và xác định các task liên quan. Task action mới chạy trong execution phase khi task thực sự được chọn để thực thi.

Với generator, nên khai báo vị trí output và hành động tạo tệp trong task action. Nếu ghi tệp ngay khi build script được đánh giá, mã có thể bị sinh cả khi người dùng chỉ yêu cầu một tác vụ không liên quan, làm build khó dự đoán và ảnh hưởng khả năng cache.

Một build script được cấu hình tốt có thể được đọc để lập task graph mà chưa cần tạo bất kỳ generated source nào. Mã chỉ xuất hiện khi task tạo nó được thực thi.

### 5.3. Up-to-date check, build cache và clean

Gradle theo dõi đầu vào và đầu ra đã khai báo của task. Nếu đầu vào không thay đổi và đầu ra vẫn tồn tại, task có thể được đánh dấu `UP-TO-DATE` và không cần chạy lại. Nếu đầu ra bị xóa, task cần chạy để tái tạo nó. Nếu đầu vào thay đổi, task thường phải thực thi lại.

Build cache có thể cho phép Gradle khôi phục đầu ra của một task tương thích từ cache thay vì chạy lại generator. Điều này phụ thuộc task có khai báo input/output đầy đủ và được thiết kế để có kết quả xác định hay không.

Lệnh:

```bash
./gradlew clean
```

sẽ xóa thư mục build mặc định của project. Các generated source được đặt trong `build/` vì vậy cũng bị xóa. Chúng sẽ được tạo lại khi task generate tương ứng chạy trong một build tiếp theo.

Nếu generator không khai báo input/output đúng, Gradle có thể không nhận ra khi nào cần chạy lại, hoặc có thể bỏ qua việc tạo mã trong trường hợp cần thiết. Đây là lý do hợp đồng input/output của task quan trọng đối với tính đúng đắn của build, không chỉ để tăng tốc.

## 6. Maven xác định thời điểm sinh mã như thế nào?

Maven tổ chức build theo lifecycle và các phase. Plugin có thể gắn goal vào một phase để Maven thực hiện goal đó ở đúng thời điểm.

Một số phase liên quan đến việc chuẩn bị và biên dịch source:

| Phase | Ý nghĩa khái quát |
|---|---|
| `generate-sources` | Sinh mã nguồn chính |
| `process-sources` | Xử lý mã nguồn trước khi biên dịch |
| `generate-resources` | Sinh resource chính |
| `process-resources` | Xử lý và sao chép resource |
| `compile` | Biên dịch mã nguồn chính |
| `generate-test-sources` | Sinh mã nguồn kiểm thử |
| `process-test-sources` | Xử lý mã nguồn kiểm thử |
| `generate-test-resources` | Sinh resource kiểm thử |
| `test-compile` | Biên dịch mã nguồn kiểm thử |

Ví dụ, một plugin sinh Java source có thể gắn goal vào phase `generate-sources`. Khi người dùng chạy:

```bash
mvn generate-sources
```

Maven thực hiện các goal được gắn vào phase đó và các phase trước nó trong lifecycle tương ứng. Khi chạy:

```bash
mvn compile
```

Maven đi qua các phase trước `compile`, vì vậy bước generate được gắn vào `generate-sources` cũng được thực hiện trước khi biên dịch.

Với annotation processing qua Maven Compiler Plugin, processor có thể chạy trong lần compiler thực hiện goal `compile` hoặc `testCompile`, tương tự cơ chế annotation processing của `javac`. Khi đó, không nhất thiết phải có một goal generate độc lập gắn vào `generate-sources`.

Maven thường đặt đầu ra generated source trong `target/generated-sources/`, nhưng plugin có thể dùng vị trí khác và cần đăng ký source root tương ứng. `mvn clean` xóa `target/`, do đó generated source trong vùng này sẽ được tái tạo ở build tiếp theo.

## 7. Cấu trúc thư mục minh họa cho một dự án Gradle

Một dự án Java có cả mã nguồn do lập trình viên viết, mã nguồn từ generator, resource và bytecode có thể được tổ chức như sau:

```text
sample-app/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/          # Mã nguồn do lập trình viên viết
│   │   └── resources/                # Resource do lập trình viên quản lý
│   └── test/
│       ├── java/
│       └── resources/
├── api/
│   └── openapi.yml                   # Đầu vào của API generator
├── build/
│   ├── generated/
│   │   ├── sources/
│   │   │   ├── openapi/main/         # Java source do generator tạo
│   │   │   └── annotationProcessor/
│   │   │       └── java/main/        # Java source do processor tạo
│   │   └── resources/main/           # Resource được sinh
│   ├── classes/
│   │   └── java/main/                # Bytecode sau compile
│   ├── resources/main/               # Resource sau processResources
│   └── libs/                          # Artifact đã đóng gói
├── build.gradle
└── settings.gradle
```

Đây là cấu trúc minh họa, không phải cây thư mục bắt buộc. Một dự án chỉ có một loại generator sẽ không có đủ mọi thư mục trên. Tên thư mục con cũng có thể được cấu hình bởi plugin.

Điểm cần nhận ra là `src/` thường chứa đầu vào do dự án quản lý lâu dài; `build/` chứa đầu ra có thể tái tạo. Generator đọc đầu vào trong `api/` hoặc `src/`, ghi kết quả vào `build/generated/`, compiler đọc cả source root thông thường lẫn generated source root, rồi ghi bytecode vào `build/classes/`.

## 8. Có nên commit mã được sinh vào Git không?

Không có một câu trả lời đúng cho mọi dự án. Quyết định phụ thuộc vào việc mã có thể tái tạo ổn định hay không, generator có sẵn trong môi trường build hay không, và quy trình phát hành yêu cầu gì.

### 8.1. Trường hợp thường không commit

Với generated source có thể tạo lại từ schema, annotation, template hoặc dependency đã khai báo, thông thường nên đặt đầu ra trong `build/` hoặc `target/` và không commit. Ví dụ:

- Implementation do annotation processor tạo.
- Java model sinh từ OpenAPI specification.
- Java message class sinh từ `.proto` file.
- Resource hoặc metadata chỉ cần trong quá trình build.

Lợi ích là repository tránh chứa nhiều tệp dẫn xuất, giảm nguy cơ source được sinh bị lệch so với schema và tránh merge conflict ở các tệp mà con người không trực tiếp quản lý.

### 8.2. Trường hợp có thể cần commit

Một số dự án chủ động commit generated source, chẳng hạn:

- Môi trường phát hành không cài hoặc không thể chạy generator.
- Generated source là artifact được phân phối như một phần API công khai.
- Quy trình review yêu cầu kiểm tra diff của mã được sinh.
- Generator hoặc đầu vào không còn khả dụng để tái tạo một phiên bản lịch sử.
- Chính sách của dự án yêu cầu lưu kết quả sinh để hỗ trợ người tiêu thụ source.

Nếu commit generated source, cần ghi rõ nguồn đầu vào, phiên bản generator, lệnh tái tạo và quy tắc đồng bộ. Nếu không, người sửa schema có thể quên cập nhật mã đã commit hoặc người sửa mã được sinh có thể tạo ra khác biệt không thể tái tạo.

### 8.3. Quy tắc khi sửa lỗi trong generated source

Giả sử `OrderMapperImpl.java` được sinh từ `OrderMapper.java` và annotation mapping. Nếu implementation có logic sai, trước tiên hãy xem annotation, mapping expression, cấu hình processor hoặc version processor. Sửa trực tiếp `OrderMapperImpl.java` có thể giải quyết tạm thời lỗi ở lần build hiện tại, nhưng lần generate tiếp theo có thể ghi đè thay đổi.

Với mã được sinh từ schema, hãy sửa schema hoặc cấu hình generator. Với mã được sinh từ template, hãy sửa template. Với mã do annotation processor tạo, hãy sửa annotation hoặc đầu vào mà processor sử dụng. Chỉ sửa trực tiếp output khi dự án có chủ đích quản lý output đó như source được commit và quy định rõ cách cập nhật.

## 9. Làm sao để biết mã được sinh khi nào và ở đâu?

Khi một lớp xuất hiện hoặc biến mất bất ngờ, hãy lần theo tác vụ tạo nó thay vì chỉ tìm tên lớp trong thư mục source.

### 9.1. Xem danh sách task Gradle

```bash
./gradlew tasks --all
```

Lệnh này hiển thị các task có thể được gọi. Tìm tên task liên quan đến `generate`, `openapi`, `proto`, `jooq`, `compileJava` hoặc tên plugin được dự án sử dụng.

### 9.2. Xem task graph mà không thực thi

```bash
./gradlew compileJava --dry-run
```

`--dry-run` cho biết các task Gradle dự kiến thực thi theo thứ tự mà không thực hiện task action. Có thể dùng để kiểm tra task generate có được nối vào `compileJava` hay không.

Nếu generator không xuất hiện trong task graph, hãy kiểm tra xem task đó có được gắn làm dependency của compile task hoặc source output hay không. Nếu nó được gọi bởi một plugin khác hoặc diễn ra bên trong compiler, cách quan sát sẽ khác.

### 9.3. Xem log thực thi

```bash
./gradlew compileJava --info
```

Log mức `--info` giúp quan sát task được thực thi, bị bỏ qua hay được đánh dấu `UP-TO-DATE`. Nếu cần chi tiết hơn, có thể dùng `--debug`, nhưng log có thể rất dài và chứa nhiều thông tin môi trường.

### 9.4. Kiểm tra output sau khi task chạy

Trên Linux/macOS:

```bash
find build/generated -type f
```

Trên Windows PowerShell:

```powershell
Get-ChildItem -Path build/generated -Recurse -File
```

Nếu thư mục chưa tồn tại, có thể task generate chưa chạy, generator không tạo đầu ra cho cấu hình hiện tại, hoặc plugin sử dụng một output directory khác. Kiểm tra cấu hình task và log để phân biệt các trường hợp này.

### 9.5. Kiểm tra source set và compiler output

Với Gradle, hãy kiểm tra `sourceSets`, `compileJava` và các task generator trong build script hoặc plugin convention. Cần xác nhận hai điều:

1. Generated source directory có được đưa vào source set mà compiler sử dụng không?
2. Task tạo directory đó có chạy trước khi compiler cần đọc nó không?

Một file có tồn tại trên ổ đĩa không có nghĩa nó đã thuộc source set. Ngược lại, một source directory có thể được khai báo dù thư mục chưa tồn tại; nó chỉ có nội dung sau khi task tạo mã thực thi.

## 10. Những lỗi thường gặp khi quản lý generated source

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `cannot find symbol` với lớp được sinh | Generator chưa chạy hoặc generated source chưa thuộc source set | Kiểm tra task graph, source set và output directory |
| Build từ IDE thành công nhưng command line thất bại | IDE tự chạy generator hoặc đánh dấu source root mà build script chưa cấu hình | Chạy Gradle/Maven từ terminal và kiểm tra cấu hình build thực tế |
| Lỗi chỉ xuất hiện sau `clean` | Output trước đó còn sót lại, nhưng task generate chưa được nối vào compile | Chạy `compileJava --dry-run`, kiểm tra dependency và chạy lại từ trạng thái sạch |
| Generated source không cập nhật khi schema đổi | Input của generator chưa được khai báo hoặc task không nhận ra thay đổi | Kiểm tra task inputs và cấu hình plugin |
| Sửa generated source nhưng thay đổi biến mất | Generator ghi đè output ở lần chạy sau | Sửa schema, annotation, template hoặc cấu hình gốc |
| Java source đã được sinh nhưng không có `.class` | Source chưa được compile hoặc compile thất bại | Kiểm tra source set, log `compileJava` và lỗi compiler |
| `.class` có trong output nhưng ứng dụng không nạp được | Runtime classpath hoặc artifact đóng gói thiếu lớp | Kiểm tra runtime classpath và nội dung JAR |
| Resource được sinh nhưng không có trong JAR | Resource output chưa được nối với `processResources` hoặc cấu hình đóng gói | Kiểm tra resource source set và task dependency |
| Generator chạy ở mọi build dù đầu vào không đổi | Input/output khai báo thiếu hoặc task không tương thích up-to-date/cache | Khai báo đầy đủ input/output và kiểm tra task implementation |

Một quy tắc chẩn đoán hữu ích là đi theo thứ tự: **đầu vào generator → task tạo mã → generated source root → compiler → class output → runtime classpath**. Mỗi mắt xích có một loại lỗi riêng.

## 11. Các nguyên tắc thiết kế thư mục và tác vụ sinh mã

Khi cấu hình một generator mới, nên giữ các nguyên tắc sau:

1. **Đặt output vào vùng build có thể xóa và tái tạo.** Với Gradle thường là bên dưới `build/generated/`; với Maven thường là bên dưới `target/generated-sources/` hoặc thư mục tương ứng.
2. **Phân biệt input với output.** Schema, specification, template và cấu hình là đầu vào; Java source hoặc resource được tạo ra là đầu ra.
3. **Khai báo task dependency rõ ràng.** Compile hoặc process resource phải chờ generator hoàn thành khi cần dùng output của nó.
4. **Đăng ký generated source/resource root.** Tệp đã được tạo chỉ được compiler hoặc resource processor sử dụng nếu nó nằm trong source set/đường dẫn đầu vào tương ứng.
5. **Khai báo input/output đầy đủ.** Build tool cần biết khi nào output còn hợp lệ và khi nào phải tạo lại.
6. **Giữ generator có thể tái tạo.** Cùng một đầu vào và phiên bản công cụ nên tạo ra kết quả ổn định trong phạm vi mà công cụ hỗ trợ.
7. **Không để mã do task sinh bị trộn với mã con người quản lý.** Việc tách thư mục giúp `clean`, IDE, review và source control xử lý đúng vai trò của từng tệp.
8. **Ghi lại cách tái tạo khi output được commit.** Người khác cần biết lệnh, phiên bản generator và đầu vào tương ứng.

## 12. Lần theo một generated source từ đầu vào đến JVM

Giả sử ứng dụng dùng một OpenAPI specification để tạo Java client. Có thể lần theo quy trình theo các bước sau:

1. **Xác định đầu vào:** tìm file `openapi.yml` và cấu hình generator.
2. **Xác định tác vụ:** tìm task hoặc Maven goal chịu trách nhiệm chạy generator.
3. **Xác định output:** tìm thư mục chứa các `.java` được sinh, ví dụ `build/generated/sources/openapi/main`.
4. **Xác định source root:** kiểm tra Gradle source set hoặc Maven generated source registration.
5. **Xác định thời điểm:** kiểm tra generator chạy độc lập trước compile hay chạy trong annotation processing.
6. **Xác định bytecode:** sau compile, tìm class tương ứng trong `build/classes/java/main` hoặc output directory đã cấu hình.
7. **Xác định runtime:** kiểm tra class và dependency có nằm trong runtime classpath hoặc artifact được đóng gói hay không.

Nếu bước 3 có source nhưng bước 4 chưa được cấu hình, compiler có thể không biên dịch source đó. Nếu bước 4 đúng nhưng bước 2/5 thiếu dependency, compiler có thể chạy trước generator. Nếu bước 6 thành công nhưng ứng dụng vẫn lỗi khi chạy, cần kiểm tra classpath và nội dung artifact.

## 13. Tổng kết luồng xử lý

Mã được sinh tự động là một phần của cấu trúc dự án và quy trình build. Nó có thể được tạo bởi task độc lập trước khi biên dịch, bởi annotation processor ngay trong quá trình compiler chạy, hoặc bởi framework trong lúc ứng dụng đang thực thi. Mỗi trường hợp có thời điểm, thư mục và cơ chế quản lý riêng.

Trong dự án Gradle, generated source thường được lưu bên dưới `build/generated/`; trong Maven, thường nằm dưới `target/generated-sources/`. Các thư mục này là vùng output có thể được xóa và tái tạo. Compiler chỉ sử dụng generated source khi thư mục được đăng ký vào source set hoặc được tích hợp qua cơ chế annotation processing phù hợp.

Khi build tool biết đầy đủ đầu vào, đầu ra và quan hệ phụ thuộc, nó có thể tạo mã đúng thời điểm, biên dịch đúng source và bỏ qua những công việc không cần chạy lại. Vì vậy, muốn hiểu một tệp Java được sinh từ đâu, hãy lần theo đầu vào và task tạo nó trước, rồi kiểm tra cách generated source được nối vào quá trình biên dịch.
