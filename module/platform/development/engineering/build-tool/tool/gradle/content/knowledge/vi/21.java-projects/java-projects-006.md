# Javadoc, sources JAR và tài liệu đi kèm thư viện

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Dự án Java

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Javadoc HTML**, **Javadoc JAR**, **sources JAR**, **binary JAR**, README, hướng dẫn sử dụng, LICENSE và tài liệu trong metadata khi phát hành thư viện Java.
2. Viết Javadoc có ích cho **public API** bằng Java 17, dùng đúng thẻ @param, @return, @throws, @since, @deprecated, inline tags như {@link ...} và {@code ...}.
3. Dùng các task **javadoc**, **sourcesJar**, **javadocJar**, **jar**, cùng hai API **withSourcesJar()** và **withJavadocJar()** của Gradle Java Plugin/Java Library Plugin.
4. Biết output mặc định, **archive classifier** và cách kiểm tra tệp bên trong từng JAR/ZIP mà không nhầm sources với bytecode hoặc tài liệu HTML.
5. Tạo dự án **Gradle Groovy DSL + Java 17** độc lập, sinh thư viện, bộ Javadoc, hai JAR tài liệu chuẩn và một ZIP hướng dẫn riêng.
6. Đóng gói **LICENSE vào binary JAR** khi dự án có chính sách cấp phép phù hợp, và đính kèm README/guides trong một archive tài liệu nếu thực sự cần.
7. Dùng **maven-publish**, **from components.java** để publish JAR chính và các documentation variants; biết giới hạn của custom artifact thêm trực tiếp vào publication.
8. Phân tích những rủi ro về Javadoc lỗi, source code rò rỉ dữ liệu, artifact bị đóng gói hai lần, metadata thiếu, IDE không tải được sources hoặc consumer chỉ có binary.
9. Thiết kế một quy trình kiểm tra thư viện trước khi đưa lên repository/CI.

**Thông điệp chính:** Một thư viện dễ sử dụng không chỉ có file .class. **Binary JAR** cho máy chạy, **sources JAR** giúp người đọc/IDE tra cứu nguồn, **Javadoc** mô tả hợp đồng API, còn README/LICENSE/guides và metadata giúp người dùng biết cách cài đặt, sử dụng, cập nhật và tuân thủ điều khoản. Mỗi phần có vai trò, cấu hình Gradle và đường phân phối khác nhau.

## 1. Bản đồ các loại artifact và tài liệu

Giả sử một thư viện có tọa độ Maven:

~~~text
group    = edu.example
artifact = docs-library
version  = 1.0.0
~~~

Sau khi build/publish, ta có thể gặp:

| Artifact hoặc tài liệu | Tên mẫu | Chứa gì? | Được dùng như thế nào? |
|---|---|---|---|
| **Binary JAR** | docs-library-1.0.0.jar | Bytecode .class, resources, manifest và file pháp lý được đóng gói nếu cấu hình | Classpath/module path để compile/run ứng dụng tiêu thụ |
| **Sources JAR** | docs-library-1.0.0-sources.jar | .java nguồn (và nguồn phù hợp của source set) | IDE tải/đính kèm để đọc source, debug và điều hướng |
| **Javadoc HTML** | build/docs/javadoc/index.html | Các trang HTML cho API Java | Đọc trực tiếp trên máy hoặc đăng lên web tài liệu |
| **Javadoc JAR** | docs-library-1.0.0-javadoc.jar | HTML, CSS, JS và các file Javadoc được đóng gói vào JAR | Repository/IDE có thể tải tài liệu của đúng version |
| **README** | README.md | Mục tiêu, cài đặt, ví dụ nhanh, giới hạn | Git repository, tài liệu phát hành, trang giới thiệu |
| **Usage guide** | docs/USAGE.md | Hướng dẫn chi tiết, tình huống và migration | Người dùng đọc ở repository/site/đính kèm |
| **LICENSE / NOTICE** | LICENSE, NOTICE | Nội dung về quyền sử dụng, bản quyền và thông báo cần thiết | Bảo đảm phân phối đúng điều khoản; không phải generated API docs |
| **Docs ZIP bổ sung** | docs-library-1.0.0-docs.zip | README, hướng dẫn và file pháp lý được chọn | Người dùng tải thủ công nếu publisher cung cấp |
| **POM và Gradle Module Metadata** | .pom, .module | Tọa độ, dependencies, variants/metadata publication | Công cụ build phân giải và nhận diện module |

**Chú ý:** Javadoc JAR và sources JAR thường **không phải dependencies cần thêm vào runtimeClasspath**. IDE hoặc công cụ tra cứu sẽ lấy chúng khi cần. Chạy ứng dụng Java không yêu cầu sources.jar hoặc javadoc.jar, trừ một workflow rất chuyên biệt tự đọc chúng.

### 1.1. Không nhầm tài liệu với dependency metadata

- **Javadoc** mô tả cách gọi public classes/methods.
- **Sources JAR** cung cấp code nguồn để đọc.
- **POM/Gradle Module Metadata** mô tả cách một component được giải quyết và phụ thuộc module nào.
- **README** dành cho hướng dẫn tiếp cận và sử dụng.
- **LICENSE** liên quan đến quyền pháp lý; Javadoc không thay thế license.
- **Release notes/changelog** mô tả thay đổi giữa các versions, không thể suy ra từ sources JAR.

Nếu user chỉ tải binary JAR, họ có thể compile code nhưng khó hiểu API. Ngược lại, nếu publish javadoc.jar mà không có binary JAR, thông thường họ vẫn không thể sử dụng thư viện để biên dịch và chạy.

### 1.2. Classifier khác module version

Với Maven artifact cùng group:artifact:version:

~~~text
docs-library-1.0.0.jar          -> artifact chính, không có classifier
docs-library-1.0.0-sources.jar  -> classifier sources
docs-library-1.0.0-javadoc.jar  -> classifier javadoc
docs-library-1.0.0-docs.zip     -> classifier docs, extension zip
~~~

Classifier xác định **loại hiện vật bổ sung của cùng một release**, không phải version khác. Đừng tạo artifactId riêng như docs-library-sources chỉ để giải quyết một sources archive theo convention Maven thông thường.

## 2. Javadoc là gì?

**Javadoc** là công cụ tạo tài liệu API từ source Java và các doc comments đặc biệt. JDK cung cấp công cụ javadoc; Gradle Java Plugin cung cấp task **javadoc** để gọi công cụ này với sources, classpath, destination và options được cấu hình.

Một comment thường:

~~~java
// Đổi tên sang chữ hoa.
public String upper(String value) {
    return value.toUpperCase();
}
~~~

không tự trở thành tài liệu API. Javadoc comment sử dụng cú pháp **/** bắt đầu bằng hai dấu sao và kết thúc bằng */:

~~~java
/**
 * Chuyển chuỗi sang chữ hoa.
 *
 * @param value chuỗi đầu vào
 * @return chuỗi đã chuyển
 */
public String upper(String value) {
    return value.toUpperCase();
}
~~~

Tài liệu mô tả **hợp đồng sử dụng API**: ý nghĩa tham số, giá trị trả về, nullability, lỗi có thể xảy ra, tính bất biến, thread-safety và những giả định quan trọng. Không chỉ lặp lại đúng tên method bằng câu “This method does something”.

### 2.1. Các thẻ thường dùng

| Cú pháp | Mục đích | Lưu ý |
|---|---|---|
| @param | Mô tả tham số hoặc type parameter | Đừng bỏ sót tham số của API công khai |
| @return | Mô tả giá trị trả về | Không dùng cho constructor và void method |
| @throws / @exception | Điều kiện method ném exception | Nêu điều kiện, không chỉ tên exception |
| @since | Từ version nào API xuất hiện | Quy ước version phải nhất quán |
| @deprecated | Lý do bỏ dùng và API thay thế | Phối hợp Java @Deprecated, lifecycle removal |
| {@link SomeClass} | Link tới type/member trong API docs | Tên/type phải resolve được khi generate |
| {@code text} | Hiển thị code inline, escape nội dung như code | Thích hợp cho tên class/method và ký tự đặc biệt |
| @see | Link/tham chiếu đọc thêm | Hữu ích khi API liên quan lẫn nhau |
| @implNote | Ghi chú implementation khi thực sự cần | Không biến chi tiết nội bộ thành contract vô tình |
| @apiNote | Gợi ý cách dùng API | Dùng khi phù hợp với loại tài liệu JavaDoc |

**Ghi chú về Markdown:** Những thẻ Javadoc xuất hiện trong file .java, không phải các lệnh của Gradle. Task javadoc sẽ xử lý chúng khi tạo HTML. Không đặt thẻ @param trong README rồi mong Gradle sinh trang method tương ứng.

### 2.2. Javadoc công khai cần chính xác và có ích

Ví dụ đầy đủ:

~~~java
package edu.example.text;

/**
 * Các tiện ích tạo thông điệp chào.
 *
 * <p>Class này không chứa trạng thái và có thể được gọi
 * từ nhiều luồng với các tham số độc lập.</p>
 *
 * @since 1.0.0
 */
public final class Greeter {

    private Greeter() {
    }

    /**
     * Tạo lời chào với tên đã bỏ khoảng trắng ở hai đầu.
     *
     * <p>Ví dụ: {@code hello(" Lan ")} trả về
     * {@code "Xin chào, Lan!"}.</p>
     *
     * @param name tên người nhận; không được null hoặc chỉ có khoảng trắng
     * @return lời chào tiếng Việt kết thúc bằng dấu chấm than
     * @throws IllegalArgumentException nếu name là null hoặc blank
     * @since 1.0.0
     * @see #hello(String)
     */
    public static String hello(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
~~~

Javadoc này nêu rõ:
- Input name phải hợp lệ.
- Output strip khoảng trắng hai đầu rồi thêm dấu chấm than.
- Null/blank làm method ném IllegalArgumentException.
- Có ví dụ có thể kiểm chứng bằng Java 17.
- Method không dựa vào một global mutable state.

**Đừng viết Javadoc trái code**. Nếu method ném IllegalArgumentException, không ghi @throws NullPointerException. Nếu thay đổi behavior, hãy cập nhật docs cùng source; tài liệu lỗi thời có thể gây hại hơn thiếu tài liệu.

### 2.3. package-info.java

Nếu một package có nhiều public types, đặt mô tả package trong package-info.java:

~~~java
/**
 * API tạo lời chào dạng chuỗi với cách xử lý input ổn định.
 *
 * <p>Điểm vào chính: {@link edu.example.text.Greeter}.</p>
 *
 * @since 1.0.0
 */
package edu.example.text;
~~~

Lưu tại đúng folder **src/main/java/edu/example/text/package-info.java**. Javadoc có thể dùng nội dung này để tạo trang mô tả package. Đừng viết một package-info.java sai package hoặc đặt nó bên ngoài source set rồi mong javadoc task tự tìm.

### 2.4. Public/protected và API thực sự

Javadoc chuẩn thường tập trung vào những API mà user có thể dùng từ ngoài package, không phải một bản dump của mọi private implementation detail. Javadoc command có tùy chọn visibility; cấu hình thường phù hợp với public/protected tùy mục tiêu.

Với Java Library Plugin, api/implementation dependencies và JPMS exports cũng ảnh hưởng cách bạn thiết kế public API, nhưng **không tự khiến Javadoc chỉ tài liệu hóa đúng những package bạn coi là ổn định**. Hãy rà soát public classes được phát hành, tránh để lộ internal packages bằng các public classes không nên có và đừng tin rằng thiếu Javadoc sẽ làm một method “private”.

### 2.5. Link tới API khác

Javadoc hỗ trợ link trong cùng project bằng {@link Type} hoặc {@link #method()}, và có thể dùng tùy chọn link để liên kết tới JDK/API tài liệu ngoài. Với external links, cần bảo đảm URL tài liệu đúng Java version và accessible trong môi trường build; khi CI offline, việc tải metadata liên kết có thể gây lỗi hoặc chậm.

Đừng tắt toàn bộ doclint để giấu broken links/malformed HTML rồi báo chất lượng tài liệu PASS. Khi cần sửa warning, ưu tiên sửa Javadoc comment; chỉ điều chỉnh options sau khi hiểu lý do.

## 3. Java Plugin và các task tài liệu có sẵn

Core Java Plugin tạo task **javadoc** cho main source set. Java Library Plugin mở rộng Java Plugin, nên cũng có task này.

Một build Java cơ bản:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Với source main dưới src/main/java, Gradle biết sources và compile classpath để generate Javadoc.

### 3.1. Task javadoc

Chạy:

~~~bash
./gradlew javadoc
~~~

HTML API docs mặc định nằm dưới:

~~~text
build/docs/javadoc/
    index.html
    edu/example/text/Greeter.html
    ...
~~~

Những tên HTML/class và file phụ thuộc packages thực tế và JDK doclet. Tệp index.html là điểm mở trang tài liệu. Nếu không có Java source hoặc API cần doc, output có thể trống/khác mong đợi; đó không chứng minh Gradle tự tạo public API.

### 3.2. Cấu hình charset và encoding

Khi source có tiếng Việt:

~~~groovy
tasks.named('javadoc', Javadoc) {
    options.encoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.docEncoding = 'UTF-8'
}
~~~

- **encoding** liên quan đến cách javadoc tool đọc source input.
- **charSet** là charset khai báo trong HTML output.
- **docEncoding** điều khiển encoding file tài liệu được ghi.
- File .java/README cần được lưu ở UTF-8 thật; chỉ cấu hình build script không thể sửa nội dung đã bị lưu sai encoding.

Với Java 17, giữ @param/@return/@throws chính xác. Cảnh báo Javadoc có thể được coi là lỗi tùy options, doclint và toolchain. Không bật options.failOnError = false như một giải pháp dài hạn mà không kiểm tra warning.

### 3.3. Đường dẫn output tùy chỉnh

Ví dụ với lazy destination property của Javadoc task:

~~~groovy
tasks.named('javadoc', Javadoc) {
    destinationDirectory = layout.buildDirectory.dir('api-docs')
}
~~~

Khi đó HTML đi tới build/api-docs thay vì mặc định. **Không** đổi path này trong bài lab nếu đang thực hành theo bảng đường dẫn mặc định; snippet là lựa chọn thay thế.

### 3.4. Javadoc cần dependency classpath phù hợp

Nếu public API có kiểu từ một thư viện ngoài, Javadoc cần resolve những type liên quan. Java Plugin cung cấp classpath của source set cho javadoc task. Thiếu dependency hoặc nhầm api/implementation/compileOnlyApi có thể khiến Javadoc không resolve class được.

Javadoc không mặc nhiên tự tải những thư viện chưa khai báo chỉ vì {@link SomeClass} xuất hiện trong comment. Nếu class không có ở source/classpath phù hợp, hãy sửa dependencies hoặc link; đừng gỡ thẻ rồi nghĩ vấn đề đã xử lý.

## 4. Tạo sources JAR bằng withSourcesJar()

Trong Java/Java Library Plugin:

~~~groovy
plugins {
    id 'java-library'
}

java {
    withSourcesJar()
}
~~~

API withSourcesJar() thực hiện hai việc quan trọng:

1. Đăng ký task **sourcesJar** đóng gói sources của main feature.
2. Đăng ký **documentation variant** cho Java component và thêm sourcesJar vào **assemble**.

Với project docs-library version 1.0.0, output thông thường:

~~~text
build/libs/docs-library-1.0.0-sources.jar
~~~

Để tạo riêng:

~~~bash
./gradlew sourcesJar
~~~

Để xem nội dung:

~~~bash
jar --list --file build/libs/docs-library-1.0.0-sources.jar
~~~

Kỳ vọng entry source như:

~~~text
edu/example/text/Greeter.java
edu/example/text/package-info.java
~~~

**sources.jar chứa .java**, không phải JAR dùng để chạy ứng dụng. IDE thường tải source artifact từ module repository, cho phép Ctrl/Cmd+click vào phương thức, đọc comment và debug ở mức nguồn (khi class/source khớp version).

### 4.1. Vì sao không phải tự viết task sourcesJar?

Bạn có thể thấy code cũ:

~~~groovy
tasks.register('sourcesJar', Jar) {
    archiveClassifier.set('sources')
    from sourceSets.main.allSource
}
~~~

Đây là một ví dụ **task tự tạo**, không phải khuyến nghị áp cùng lúc với withSourcesJar(). Trong Gradle Java Plugin hiện đại, withSourcesJar() đã lo task, naming, assemble và documentation variant. Nếu bạn tạo một task cùng tên nữa, có thể gặp lỗi tên trùng hoặc tạo publication khó kiểm soát.

**Dùng API tích hợp trước**, chỉ tự viết task khi có yêu cầu khác biệt rõ ràng (source generation, nonstandard language, selective packaging).

### 4.2. Có nên đưa generated sources vào sources JAR?

Nếu public API có Java source được tạo bởi một producer task (ví dụ code generator), sources JAR cần có chiến lược nhất quán:
- Source được công bố phải tương ứng bytecode đã publish.
- Generated sources cần có producer dependency phù hợp (Provider/task output), không đọc một folder chưa tồn tại.
- Cần cân nhắc bảo mật và license nếu generated code chứa dữ liệu nhạy cảm.
- Không cố coi every build/ folder là source cần phát hành.

Khi cần, cấu hình source sets và tasks đúng API Gradle để source producer và jars có dependency. Không chỉ copy một thư mục output bất kỳ rồi kỳ vọng sourcesJar tự suy ra task order.

### 4.3. Source artifact và source mapping

**Sources JAR không bảo đảm debug 100% chính xác** nếu:
- Compiler sinh bridge/synthetic methods.
- Source được transform/shade trước khi đóng JAR.
- Binary và sources có version không khớp.
- Annotation processor/code generation tạo bytecode có khác biệt.

IDE cần source và binary **cùng một release**; đừng publish nguồn mới với binary cũ dưới cùng version.

## 5. Tạo Javadoc JAR bằng withJavadocJar()

Trong Java/Java Library Plugin:

~~~groovy
plugins {
    id 'java-library'
}

java {
    withJavadocJar()
}
~~~

API này:
1. Dùng task **javadoc** sinh HTML cho main feature.
2. Đăng ký task **javadocJar** đóng gói output của javadoc vào JAR có classifier **javadoc**.
3. Đưa documentation variant vào Java component và thêm task vào **assemble**.

Với project docs-library version 1.0.0:

~~~text
build/libs/docs-library-1.0.0-javadoc.jar
~~~

Tạo:

~~~bash
./gradlew javadocJar
~~~

Kiểm tra:

~~~bash
jar --list --file build/libs/docs-library-1.0.0-javadoc.jar
~~~

Bên trong thường có:

~~~text
index.html
edu/example/text/Greeter.html
...
~~~

**Javadoc JAR không phải Java source JAR**. Nó chứa HTML/assets của docs, không dùng trực tiếp cho Java runtime class loading.

### 5.1. Chỉ chạy javadoc khác với gọi javadocJar

| Task | Kết quả trực tiếp |
|---|---|
| **javadoc** | Cây HTML docs trong build/docs/javadoc (mặc định) |
| **javadocJar** | JAR nén cây HTML docs, phụ thuộc vào javadoc producer |
| **sourcesJar** | JAR chứa Java sources |
| **jar** | Binary JAR của thư viện |
| **assemble** | Artifacts thuộc assemble, gồm jar và các docs jars đã bật |
| **publish** | Artifacts/metadata theo publication(s), repositories đã cấu hình |

Gọi javadocJar thường khiến task javadoc chạy trước khi cần, nếu output chưa sẵn sàng. Không cần tự viết dependsOn(javadoc) khi dùng withJavadocJar().

### 5.2. JavadocJar không tự bao gồm README

Một README.md ở root không nhất thiết nằm trong output của javadoc task, nên **không tự có trong javadocJar**. Nếu muốn publish guides, có các lựa chọn:
- Đăng README/guides lên documentation site và link từ README/POM.
- Tạo một docs ZIP archive riêng, rõ classifier.
- Bổ sung tài liệu hợp lệ vào Javadoc qua doc-files hoặc nhiệm vụ copy với quản lý ownership đúng.

Đừng dùng việc chèn README vào javadocJar rồi tuyên bố mọi IDE sẽ hiển thị nó như Java API docs; IDE thường tìm index.html và trang theo packages.

## 6. Tài liệu đi kèm thư viện nên gồm những gì?

Một gói thư viện dành cho người dùng nên trả lời các câu hỏi sau:

| Tài liệu | Nội dung nên có |
|---|---|
| **README.md** | Thư viện giải quyết bài toán gì, version, Java compatibility, cách thêm dependency, quick start, link API docs |
| **Javadoc** | Public types/methods, @param/@return/@throws, version introduced, lifecycle deprecation |
| **Sources JAR** | Source chính xác của release, đủ để IDE điều hướng/debug |
| **LICENSE** | License áp dụng cho mã và artifact; phải là nội dung pháp lý chính xác do chủ sở hữu chọn |
| **NOTICE** | Thông báo bản quyền/attribution khi chính sách license hoặc third-party materials yêu cầu |
| **CHANGELOG.md** | Breaking changes, deprecations, fixes, migration theo version |
| **docs/** | Hướng dẫn use cases, threading, performance, migration, FAQ |
| **POM/Module Metadata** | Group, artifact, version, dependencies, license/developer/SCM metadata khi phù hợp |
| **Examples** | Mẫu Java 17 có thể compile/run, output đáng tin, hướng dẫn test |
| **Security policy** | Cách báo lỗi bảo mật, supported versions; tùy quy mô release |

**Không phải mọi tài liệu nên đóng chung một JAR.** README/changelog thường phục vụ repository/site; LICENSE hoặc NOTICE đôi khi được đặt trong META-INF của binary; source/Javadoc được publish thành classifiers chuẩn; guides bổ sung có thể là ZIP hoặc site. Hãy tổ chức dựa trên người tiêu thụ và yêu cầu pháp lý của dự án.

### 6.1. LICENSE không phải phần văn bản để AI tự đoán

Bản quyền và license phụ thuộc vào **chủ sở hữu, mã bên thứ ba và điều khoản phân phối**. Ví dụ lab có LICENSE minh họa nội dung thử nghiệm; khi publish thật, thay bằng license đã được chủ sở hữu chọn và kiểm tra yêu cầu third-party notices.

Đừng:
- Ghi tên Apache-2.0/MIT trong POM nhưng file LICENSE lại khác.
- Xóa NOTICE của một dependency chỉ để làm artifact nhỏ.
- Tự tuyên bố tài liệu code từ nhà cung cấp có quyền tái phân phối.
- Đưa vào sources JAR file chứa secrets, private keys hoặc endpoint nội bộ.

### 6.2. POM metadata không thay README

Maven POM và Gradle Module Metadata giúp build tools hiểu module. POM có thể ghi:
- name, description, url,
- licenses,
- developers,
- scm,
- dependencies,
- groupId/artifactId/version.

Những trường này rất quan trọng khi publish công khai, nhưng không thể thay một quick start rõ ràng. Ngược lại, README dễ đọc không giúp Gradle tự biết transitive dependencies nếu metadata xuất bản sai.

## 7. Thực hành hoàn chỉnh: Java 17 library với Javadoc, sources và docs

Ta xây một project Groovy DSL không cần thư viện ngoài. Sau build, ta có:
- Binary JAR chứa Greeter.class.
- Sources JAR chứa Greeter.java và package-info.java.
- HTML docs từ javadoc.
- Javadoc JAR chứa các trang HTML.
- Một ZIP docs phụ có README.md, docs/USAGE.md và LICENSE.
- Maven publication lưu vào **thư mục nội bộ dưới build/** để thử, không upload Maven Central.

### 7.1. Yêu cầu

Cần **JDK 17**, một Gradle version tương thích với Java 17 và bản Gradle Wrapper của project (khuyến nghị). Javadoc tool là một phần JDK; **JRE đơn thuần không có javadoc tool**.

Nếu project chưa có Wrapper, dùng một Gradle đã cài tương thích chạy **gradle wrapper** một lần rồi sử dụng ./gradlew hoặc .\gradlew.bat. Các ví dụ không cần Maven Central để resolve dependency mã nguồn thư viện; Gradle distribution có thể cần tải ở lần đầu tạo/chạy Wrapper.

Cấu trúc:

~~~text
docs-library/
├── settings.gradle
├── build.gradle
├── README.md
├── LICENSE
├── docs/
│   └── USAGE.md
├── consumer/
│   └── demo/
│       └── Main.java
├── gradlew                       # được tạo bởi Wrapper
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    └── main/
        └── java/
            └── edu/example/text/
                ├── Greeter.java
                └── package-info.java
~~~

**Lưu ý:** consumer/demo/Main.java là chương trình Java độc lập dùng để kiểm thử artifact đã build bằng javac/java. Nó **không** thuộc sourceSet main của Gradle library và không tự được đưa vào binary JAR.

### 7.2. settings.gradle

~~~groovy
rootProject.name = 'docs-library'
~~~

### 7.3. build.gradle — đầy đủ

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'edu.example'
version = '1.0.0'
description = 'Thư viện chào hỏi minh họa tài liệu API'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }

    // Hai task/variant tài liệu theo convention của Gradle.
    withSourcesJar()
    withJavadocJar()
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.named('javadoc', Javadoc) {
    options.encoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.docEncoding = 'UTF-8'
}

// Khi phân phối binary, đính kèm file pháp lý của chính project.
tasks.named('jar', Jar) {
    from('LICENSE') {
        into 'META-INF'
        rename { 'LICENSE.txt' }
    }
}

// Archive hướng dẫn riêng, không thay sourcesJar/javadocJar.
def docsZip = tasks.register('docsZip', Zip) {
    group = 'documentation'
    description = 'Đóng gói README, hướng dẫn và license minh họa'

    archiveClassifier.set('docs')

    from('README.md')
    from('docs') {
        into 'guides'
    }
    from('LICENSE') {
        into 'legal'
    }
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            // Bao gồm binary + sources + Javadoc variants.
            from components.java

            // ZIP bổ sung được gắn như custom artifact trực tiếp.
            artifact docsZip

            pom {
                name = 'Docs Library'
                description = 'Thư viện Java 17 minh họa artifacts và Javadoc'
            }
        }
    }
    repositories {
        maven {
            name = 'demo'
            url = layout.buildDirectory.dir('demo-repo')
        }
    }
}
~~~

**Ý nghĩa từng nhóm:**

1. **java-library** cung cấp Java compilation, Javadoc và Java component dành cho library.
2. **maven-publish** cung cấp MavenPublication và task publish.
3. **group/version** quyết định identity của module và tên archive theo convention.
4. **withSourcesJar/withJavadocJar** thêm tasks và documentation variants vào Java component.
5. **tasks.named('javadoc', Javadoc)** cấu hình tool, không tự gọi tool ngay trong configuration.
6. **jar.from('LICENSE')** đưa file pháp lý vào META-INF/LICENSE.txt của binary JAR.
7. **docsZip** tạo ZIP hướng dẫn riêng, classifier docs.
8. **from components.java** đưa JAR chính, sources JAR và Javadoc JAR vào publication.
9. **artifact docsZip** thêm ZIP riêng dưới cùng Maven coordinates, classifier docs; đây là artifact tùy chỉnh ngoài mô hình variants tài liệu chuẩn.
10. **repository demo** là thư mục build/demo-repo local để tự kiểm tra, không gửi artifact lên mạng.

**Không thêm** artifact tasks.named('sourcesJar') hoặc artifact tasks.named('javadocJar') lần nữa vào cùng MavenPublication trong ví dụ này. Chúng đã nằm trong components.java sau withSourcesJar()/withJavadocJar(); đính kèm lặp có thể gây duplicate classifier/extension hoặc warnings.

**Không cần repositories { mavenCentral() }** trong ví dụ này, vì library source không dùng external modules. Nếu bạn thêm Java dependencies ngoài, cấu hình dependency repositories đúng nơi; đừng nhầm nơi **resolve thư viện Java** với nơi **publish** của maven-publish.

### 7.4. File Greeter.java

**src/main/java/edu/example/text/Greeter.java**

~~~java
package edu.example.text;

/**
 * API tạo lời chào đơn giản với quy tắc xử lý input rõ ràng.
 *
 * <p>Class không chứa trạng thái có thể thay đổi.</p>
 *
 * @since 1.0.0
 */
public final class Greeter {

    private Greeter() {
    }

    /**
     * Trả về lời chào dành cho người nhận.
     *
     * <p>Ví dụ {@code hello(" Lan ")} trả về
     * {@code "Xin chào, Lan!"}.</p>
     *
     * @param name tên cần chào; không được null hoặc blank
     * @return lời chào tiếng Việt, đã loại khoảng trắng hai đầu tên
     * @throws IllegalArgumentException nếu name là null hoặc blank
     * @since 1.0.0
     */
    public static String hello(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        return "Xin chào, " + name.strip() + "!";
    }
}
~~~

**Kiểm chứng logic:** Với " Lan ", isBlank() trả false; strip() trả "Lan"; method trả "Xin chào, Lan!". Với null hoặc chỉ khoảng trắng, method ném IllegalArgumentException trước khi gọi strip().

Lớp final và private constructor diễn đạt mô hình utility class: người dùng gọi method static, không tạo instance.

### 7.5. File package-info.java

**src/main/java/edu/example/text/package-info.java**

~~~java
/**
 * Các API hỗ trợ tạo lời chào bằng Java 17.
 *
 * <p>Dùng {@link edu.example.text.Greeter#hello(String)}
 * để tạo thông điệp và xem Javadoc của phương thức
 * để hiểu quy tắc xử lý tên.</p>
 *
 * @since 1.0.0
 */
package edu.example.text;
~~~

Package comment góp phần tạo trang mô tả package trong output của javadoc task. Link tham chiếu đến Greeter#hello(String) có thật trong cùng source set.

### 7.6. README.md

**README.md**

~~~markdown
# Docs Library

Thư viện Java 17 nhỏ minh họa public API và tài liệu kèm release.

## Cài đặt sau khi publication có trong repository

Group: edu.example
Artifact: docs-library
Version: 1.0.0

Gradle Groovy DSL của consumer:

    repositories {
        maven {
            url = uri('/path/to/local/demo-repo')
        }
    }

    dependencies {
        implementation 'edu.example:docs-library:1.0.0'
    }

Đường dẫn repository là ví dụ; thay bằng vị trí thật của bản publish.

## Sử dụng

    import edu.example.text.Greeter;
    System.out.println(Greeter.hello("Lan"));

Kết quả: Xin chào, Lan!

## Tài liệu

- API Javadoc: build/docs/javadoc/index.html khi build local
- Sources JAR và Javadoc JAR được phát hành cùng binary JAR
- Hướng dẫn: docs/USAGE.md
~~~

Trong README, các block thụt bốn khoảng trắng là Markdown code blocks hợp lệ. Đường dẫn repository giả định chỉ là hướng dẫn; khi consumer chạy ở nơi khác, phải chỉ đúng repository nơi publication đã được đẩy.

### 7.7. docs/USAGE.md

**docs/USAGE.md**

~~~markdown
# Hướng dẫn sử dụng Docs Library

## Quy tắc

Greeter.hello(name) bỏ khoảng trắng đầu/cuối và thêm lời chào tiếng Việt.
Nếu name null hoặc blank, phương thức ném IllegalArgumentException.

## Ví dụ

- hello("Lan") -> "Xin chào, Lan!"
- hello("  Minh  ") -> "Xin chào, Minh!"
- hello("   ") -> IllegalArgumentException

## Tương thích

Project minh họa dùng Java 17 toolchain.
Khi phát hành thật, cần kiểm thử Java runtimes được hỗ trợ
và tài liệu hóa giới hạn version/JDK.

## Khắc phục lỗi

Nếu không import được Greeter, kiểm tra tọa độ repository,
group/artifact/version và runtime/compile classpath của consumer.
~~~

README hướng người mới vào nhanh, USAGE đi sâu hơn. **Không cần** ép mọi nội dung này vào Javadoc comment của từng method; các loại tài liệu phục vụ nhu cầu khác nhau.

### 7.8. LICENSE dùng trong ví dụ

**LICENSE**

~~~text
Tutorial-only example licensing notice.

This file is illustrative and does not grant a real-world
license for unrelated code. Before distributing a real library,
the copyright holder must choose and include an appropriate
complete license and any required notices.
~~~

File này là **nội dung minh họa phục vụ bài học**, không phải một văn bản license tiêu chuẩn đủ điều kiện phát hành. Khi tạo sản phẩm thật, phải **thay bằng LICENSE hợp lệ** được chủ sở hữu phê duyệt; kiểm tra nghĩa vụ NOTICE/attribution. Mẫu bài lab cố ý không khai báo một POM license sai với nội dung file, cũng không quảng bá ví dụ này như artifact đủ điều kiện phát hành công khai.

### 7.9. Tạo binary JAR, sources, Javadoc và ZIP

Linux/macOS:

~~~bash
./gradlew clean jar sourcesJar javadoc javadocJar docsZip
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean jar sourcesJar javadoc javadocJar docsZip
~~~

Nếu build thành công, các kết quả dự kiến:

~~~text
build/
├── classes/java/main/
│   └── edu/example/text/Greeter.class
├── docs/javadoc/
│   ├── index.html
│   └── edu/example/text/Greeter.html
├── libs/
│   ├── docs-library-1.0.0.jar
│   ├── docs-library-1.0.0-sources.jar
│   └── docs-library-1.0.0-javadoc.jar
└── distributions/
    └── docs-library-1.0.0-docs.zip
~~~

Các file phụ do Javadoc/doclet tạo có thể khác theo JDK; bảng chỉ nêu những file quan trọng để kiểm chứng.

**Dùng jar tool của JDK để liệt kê:**

~~~bash
jar --list --file build/libs/docs-library-1.0.0.jar
jar --list --file build/libs/docs-library-1.0.0-sources.jar
jar --list --file build/libs/docs-library-1.0.0-javadoc.jar
jar --list --file build/distributions/docs-library-1.0.0-docs.zip
~~~

**Kỳ vọng tìm thấy:**

| Archive | Entry minh chứng |
|---|---|
| Binary | edu/example/text/Greeter.class |
| Binary | META-INF/LICENSE.txt |
| Sources | edu/example/text/Greeter.java |
| Sources | edu/example/text/package-info.java |
| Javadoc | index.html |
| Javadoc | edu/example/text/Greeter.html |
| Docs ZIP | README.md |
| Docs ZIP | guides/USAGE.md |
| Docs ZIP | legal/LICENSE |

**Lưu ý:** jar --list có thể đọc ZIP archive được tạo theo định dạng ZIP, nên được dùng cho docs.zip trong bài lab. Bạn cũng có thể dùng unzip -l trên hệ có công cụ unzip. Thứ tự entries, timestamps, manifest và các assets còn lại không nên được hardcode như stdout chính xác của một nhiệm vụ build.

### 7.10. Kiểm tra source và HTML tại chỗ

Mở **build/docs/javadoc/index.html** qua trình duyệt hoặc IDE file viewer. Tìm Greeter, chữ ký method hello(String), mô tả tham số, giá trị trả về, điều kiện IllegalArgumentException và @since.

Nếu HTML bị lỗi tiếng Việt:
1. Kiểm tra file .java được lưu UTF-8.
2. Kiểm tra options.encoding, charSet, docEncoding của javadoc task.
3. Xác nhận JDK toolchain/locale khi cần.
4. Build lại javadoc sau khi đã sửa source/encoding.

Không coi việc HTML mở được là đủ nếu tài liệu public API bị thiếu hoặc Javadoc warnings bị bỏ qua.

### 7.11. Java 17 consumer dùng binary JAR thật

**consumer/demo/Main.java**

~~~java
package demo;

import edu.example.text.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.hello(" Lan "));
    }
}
~~~

Sau khi tạo **build/libs/docs-library-1.0.0.jar**, biên dịch một consumer **chỉ với binary JAR**. Linux/macOS từ project root:

~~~bash
mkdir -p build/consumer-classes
javac -encoding UTF-8 \
  -cp build/libs/docs-library-1.0.0.jar \
  -d build/consumer-classes \
  consumer/demo/Main.java
java -cp "build/consumer-classes:build/libs/docs-library-1.0.0.jar" demo.Main
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build\consumer-classes | Out-Null
javac -encoding UTF-8 -cp build\libs\docs-library-1.0.0.jar -d build\consumer-classes consumer\demo\Main.java
java -cp "build\consumer-classes;build\libs\docs-library-1.0.0.jar" demo.Main
~~~

**Stdout của Java application**:

~~~text
Xin chào, Lan!
~~~

Điều này chứng minh **binary JAR đủ để compile/run consumer** trong bài lab. Bạn không cần thêm sources.jar/javadoc.jar vào -cp. Mặc dù console Windows có thể cần được cấu hình hiển thị UTF-8 đúng, chuỗi Java được in có nội dung Unicode đúng như trên.

### 7.12. Publish thử vào thư mục repository cục bộ

Chạy:

~~~bash
./gradlew publish
~~~

Maven Publish Plugin tạo những task cần thiết cho publication mavenJava và repository demo. Kết quả được ghi **dưới build/demo-repo**, không gửi lên Maven Central hay một host ngoài.

Một đường dẫn có thể nhìn thấy:

~~~text
build/demo-repo/edu/example/docs-library/1.0.0/
    docs-library-1.0.0.jar
    docs-library-1.0.0-sources.jar
    docs-library-1.0.0-javadoc.jar
    docs-library-1.0.0-docs.zip
    docs-library-1.0.0.pom
    docs-library-1.0.0.module
    ...
~~~

Những checksum files, module metadata và các file phụ khác tùy publishing setup/Gradle version. Đừng ngạc nhiên khi có thêm .sha256/.sha512 hoặc metadata, và đừng coi các tên file trong bảng là danh sách tuyệt đối.

### 7.13. Maven publication của ví dụ

Trong build.gradle:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifact docsZip
            pom {
                name = 'Docs Library'
                description = 'Thư viện Java 17 minh họa'
            }
        }
    }
}
~~~

**from components.java** có ý nghĩa đặc biệt: Java component biết binary artifact cùng **documentation variants** đã đăng ký từ withSourcesJar()/withJavadocJar() và dependency metadata.

Ngược lại, **artifact docsZip** thêm một custom archive trực tiếp vào MavenPublication. Theo tài liệu Gradle, artifact đính kèm kiểu này có thể được publish **ngoài mô hình variant metadata (out of context)**: consumer sẽ không nhất thiết tự khám phá docs.zip như một variant bằng dependency resolution. Người dùng có thể tải trực tiếp archive có classifier docs hoặc bạn thiết kế một outgoing documentation variant riêng nếu cần mô hình tiêu thụ có metadata.

**Không đánh đồng** việc file có trong Maven repository với việc mọi dependency consumer sẽ tự tải hoặc biết mục đích của file đó.

### 7.14. Có cần mavenLocal() không?

Bài lab publish vào build/demo-repo riêng để dễ thấy file thật. Nếu muốn dùng repository ấy trong một project khác:

~~~groovy
repositories {
    maven {
        url = uri('../docs-library/build/demo-repo')
    }
}

dependencies {
    implementation 'edu.example:docs-library:1.0.0'
}
~~~

Đây là **snippet consumer**, đường dẫn tương đối phải điều chỉnh đúng chỗ của consumer project. Nó giải quyết **binary module** theo tọa độ và metadata đã publish. Sources/Javadoc thường được IDE lấy qua cơ chế artifact/variant được hỗ trợ, không phải các dòng implementation riêng.

**publishToMavenLocal** là task khác, ghi vào Maven Local repository của user; nó không đồng nghĩa với publish vào build/demo-repo trong lab. Dùng repository local tách biệt trong bài học giúp không làm bẩn ~/.m2/repository của người dùng.

## 8. Maven Publish Plugin: sources và Javadoc đi theo Java component

### 8.1. Vì sao nên dùng from components.java?

~~~groovy
java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

Đây là cấu hình chuẩn theo Gradle docs để publish library **binary + source + Javadoc**. Các documentation variants được liên kết với component, và Maven Publish Plugin biết tạo output files tương ứng.

Khi một library có api/implementation dependencies, Java component còn mang mô hình dependency/variant metadata cho consumer. Vì thế **from components.java** thường phù hợp hơn viết danh sách artifact bằng tay mà bỏ mất dependencies metadata.

### 8.2. Không đính kèm sources/Javadoc hai lần

Ví dụ sai ý tưởng:

~~~groovy
java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifact tasks.named('sourcesJar')
            artifact tasks.named('javadocJar')
        }
    }
}
~~~

Đây là **anti-pattern**, không nên chép vào lab. Đã có documentation variants trong Java component thì thêm cùng artifacts thủ công có thể gây duplicate classifier/extension hoặc publication conflicts.

Chỉ dùng artifact(...) cho những tài liệu/archives **thực sự bổ sung**, ví dụ docsZip. Nếu muốn điều chỉnh các variants tài liệu chuẩn, xem API AdhocComponentWithVariants và withVariantsFromConfiguration thay vì loại bỏ component rồi tự dựng từ đầu.

### 8.3. Publication của library khác distribution của ứng dụng

- Library thường publish binary JAR với dependency metadata và companions.
- Application có thể tạo start scripts/distribution bằng application plugin.
- Javadoc Jar chỉ giúp tra cứu API, **không** tự đóng gói dependency runtime vào một fat JAR.
- Sources Jar không biến một binary library thành Maven source dependency cần compile lại theo mặc định.

Nếu bạn muốn một runnable application cùng dependencies, đó là bài toán packaging/distribution khác với phát hành thư viện Java kèm Javadoc.

### 8.4. POM metadata và phát hành công khai

Để publish thực tế lên Maven Central hoặc repository doanh nghiệp, có thể cần:
- Name/description/url đầy đủ,
- LICENSE và POM licenses phù hợp,
- Developer/SCM information,
- Artifact signing,
- Changelog, source archive và Javadoc,
- Credentials qua environment/secret manager,
- Chính sách release bất biến và version compatibility.

**Đừng dùng ngay publication demo để phát hành công khai.** LICENSE chỉ là thông báo minh họa; POM còn chưa điền metadata đủ theo repository policy; repository demo cũng chỉ là thư mục build local.

Maven Central đã thay đổi quy trình publish sau khi OSSRH legacy protocol ngừng hoạt động. Hãy tuân theo quy trình hiện hành của nhà cung cấp repository, không giả định maven-publish trực tiếp lên một URL cũ là đủ. Đối với bài lab, publish local hoàn toàn không cần credentials.

## 9. Khi nào cần tùy chỉnh các Javadoc/sources tasks?

### 9.1. Dự án nhiều source sets

Java Plugin có thể có main, test, integrationTest, generated source set... Nhưng **withSourcesJar()** và **withJavadocJar()** áp cho **main feature**. Không tự bảo đảm mọi source set phụ hoặc source test cũng được xuất bản.

Muốn tài liệu hóa một API variant khác, cần thiết kế task, outgoing variants và publication theo source set tương ứng. Không trộn test source code vào sources JAR của library production chỉ vì nó cũng nằm dưới src/.

### 9.2. Không xuất bản tài liệu của implementation nội bộ vô tình

Khi đóng gói source:
- Rà soát public/private code, secrets, cấu hình file paths.
- Phân biệt source repository public với proprietary source code.
- Chỉ publish khi được phép phát hành.
- Không đưa keys, tokens hoặc nội dung test data nhạy cảm vào sources JAR/README/docs ZIP.

**Quan trọng:** Một sources JAR có thể chứa cả implementation source (tùy source set), **không chỉ các public API types**. Từ “sources” không có nghĩa bộ lọc “public only”. Nếu license không cho phép công bố implementation source, cần thiết kế release policy phù hợp hoặc không publish sources artifact ra public repository.

### 9.3. Tùy chỉnh HTML doclet

Gradle Javadoc task cho phép cấu hình:
- source files và classpath,
- title/header/links,
- encoding/charset,
- destinationDirectory,
- custom doclet/options khi cần.

Ví dụ cấu hình heading:

~~~groovy
tasks.named('javadoc', Javadoc) {
    options.windowTitle = 'Docs Library API 1.0.0'
    options.docTitle = 'Docs Library'
    options.encoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.docEncoding = 'UTF-8'
}
~~~

Đây là **snippet tùy chọn** để bổ sung/điều chỉnh task; không phải đoạn phải thay toàn bộ build.gradle của lab. Kiểm tra tính năng options theo Gradle/JDK version thực tế.

### 9.4. Không dùng HTML docs làm dependency runtime

Không khai báo:

~~~groovy
// Sai mục tiêu đối với Java runtime:
dependencies {
    implementation files('build/libs/docs-library-1.0.0-javadoc.jar')
}
~~~

Javadoc JAR chứa HTML/docs, không chứa các public bytecode classes cần thiết. Với Java source consumer, implementation phải trỏ đến **binary library module/JAR**. IDE tự quản lý sources/docs attachment khi hỗ trợ.

### 9.5. Binary compatibility và tài liệu API

Một API được Javadoc mô tả cũng là hợp đồng với người dùng. Nếu đổi method signature, throw behavior, nullability hoặc type:
- Đọc quy tắc SemVer/version của dự án.
- Viết migration guide nếu breaking change.
- Dùng @Deprecated cùng @deprecated documentation khi chuẩn bị loại bỏ.
- Cập nhật Javadoc, README, examples và tests trong cùng thay đổi.
- Đảm bảo sources/Javadoc artifacts được publish **cùng một version** với binary tương ứng.

**Javadoc sinh ra từ code mới nhưng publish chung binary version cũ** là lỗi release nghiêm trọng: IDE có thể dẫn người dùng tới method không tồn tại.

## 10. Javadoc lỗi hoặc thiếu: cách chẩn đoán

### Lỗi 1 — Không tìm thấy task javadoc

**Khả năng:** Project chưa áp dụng java/java-library/application plugin, đang chạy lệnh ở root project không có Java source model, hoặc gõ sai project path trong multi-project build.

**Cách sửa:** Xem plugins block của đúng subproject, chạy ./gradlew :lib:tasks --all để tìm task javadoc và xác nhận Java Plugin có mặt.

### Lỗi 2 — Javadoc HTML trống hoặc thiếu public class

**Nguyên nhân có thể:** Source không nằm trong src/main/java, class thuộc source set khác, class/package không được javadoc task chọn, hoặc visibility options đang ẩn thành phần đó.

**Cách sửa:** Kiểm tra sourceSets.main, task Javadoc.source, package, visibility và task execution report. Đừng tự chuyển nội dung test/private vào public Javadoc nếu không phù hợp.

### Lỗi 3 — Javadoc bị lỗi do @link không resolve

**Nguyên nhân:** Tên type/member sai hoặc classpath cho javadoc thiếu type mà link tham chiếu.

**Cách sửa:** Sửa link đúng chữ ký Java, kiểm tra dependencies/Java compilation và doclint output. Không tắt cảnh báo toàn cục chỉ để build xanh.

### Lỗi 4 — Chữ tiếng Việt bị lỗi

**Nguyên nhân:** File .java được lưu không phải UTF-8; encoding/charset/docEncoding không đồng bộ; terminal/browser render sai.

**Cách sửa:** Lưu source UTF-8, cấu hình các options tương ứng và build lại docs. Kiểm tra file HTML trực tiếp sau khi build.

### Lỗi 5 — Có javadoc nhưng không có javadocJar

**Nguyên nhân:** Bạn chỉ áp Java Plugin mà chưa gọi java.withJavadocJar() hoặc không đăng ký task riêng.

**Cách sửa:** Dùng withJavadocJar() cho Java main feature; chạy ./gradlew javadocJar rồi xem build/libs.

### Lỗi 6 — Không có sourcesJar

**Nguyên nhân:** Chưa gọi withSourcesJar() hoặc task bị lỗi tên/configuration.

**Cách sửa:** Dùng withSourcesJar(), chạy ./gradlew sourcesJar và kiểm tra sources của main feature.

### Lỗi 7 — Đã có sources/Javadoc JAR nhưng không được publish

**Nguyên nhân:** Maven publication không lấy components.java, hoặc docs variants đã bị skip, hoặc publish task không đúng publication/repository.

**Cách sửa:** Dùng from components.java, kiểm tra java { withSourcesJar(); withJavadocJar() }, xem ./gradlew tasks --all và thư mục repo đã publish. Không lặp artifact sourcesJar/javadocJar khi component đã chứa.

### Lỗi 8 — Duplicate artifact với classifier sources/javadoc

**Nguyên nhân:** Vừa withSourcesJar()/withJavadocJar(), vừa artifact thủ công cùng classifier trong một MavenPublication.

**Cách sửa:** Giữ documentation variants được Java component quản lý; loại thao tác đính kèm trùng.

### Lỗi 9 — sources.jar lại chứa .class hoặc binary JAR chứa .java ngoài ý định

**Nguyên nhân:** Dùng sai task type/from paths hoặc copy nhầm source/classes outputs.

**Cách sửa:** Kiểm tra archive bằng jar --list. sourcesJar dùng source set source files; jar dùng compiled classes/resources.

### Lỗi 10 — docs.zip publish được nhưng IDE không tự tải như Javadoc

**Nguyên nhân:** Custom artifact thêm bằng artifact docsZip thường không được mô tả như một standard documentation variant trong module metadata; IDE cũng có convention riêng cho classifier javadoc.

**Cách sửa:** Giữ chuẩn withJavadocJar()/withSourcesJar(); tài liệu tùy chỉnh có thể link từ README/site. Nếu muốn Gradle variants discoverable, thiết kế outgoing configuration/documentation variant có metadata thích hợp.

### Lỗi 11 — Consumer không tải được artifact

**Nguyên nhân:** Sai group/artifact/version, repository URL/credentials, chưa publish hoặc repo không chứa artifact. Cũng có thể IDE download sources bị tắt.

**Cách sửa:** Xem POM/.module và filenames tại repo, kiểm tra repository có ở consumer, kiểm tra settings và artifact resolution. Tách lỗi binary dependency resolution khỏi lỗi “download sources”.

### Lỗi 12 — Javadoc thành công nhưng tài liệu không phản ánh phiên bản

**Nguyên nhân:** Javadoc comment, @since, README/changelog chưa được cập nhật hoặc lỡ publish docs từ code branch khác.

**Cách sửa:** Dùng release pipeline gắn source commit/version, kiểm tra các artifacts được tạo cùng một invocation và review diff.

### Lỗi 13 — Maven Central từ chối release

**Nguyên nhân:** Publication thiếu metadata/signature/license/sources/Javadoc hoặc không đi theo protocol quy định của repository tại thời điểm phát hành.

**Cách sửa:** Theo checklist hiện hành của repository provider, khai báo POM metadata và signing/credentials đúng, chạy local publish trước. Không tự khẳng định mọi Maven repository có cùng điều kiện chấp nhận.

### Lỗi 14 — javadocJar làm build chậm

**Nguyên nhân:** HTML generation tốn thời gian; mỗi lần source/Javadoc input thay đổi cần regenerate.

**Cách sửa:** Dùng Gradle incremental/up-to-date checks, cấu hình hợp lý tài liệu public, CI caching khi an toàn; không bỏ Javadoc chỉ để né lỗi chất lượng docs nếu thư viện cần publish. Có thể phân tách task phát hành và task phát triển tùy project policy.

### Lỗi 15 — Source bị lộ thông tin không được publish

**Nguyên nhân:** withSourcesJar() đóng nguồn main, trong đó có file cấu hình nội bộ, generated secrets, hoặc code bên thứ ba không được phép phân phối.

**Cách sửa:** Kiểm tra nội dung archive trước publish, thiết kế source layout/release policy đúng; không tự phát hành sources chỉ vì plugin cung cấp API dễ gọi.

### Lỗi 16 — LICENSE trong README nhưng không trong binary artifact

**Nguyên nhân:** File repository không tự được đóng gói vào Jar task. Một số license yêu cầu có nội dung/notice đi kèm phân phối binary.

**Cách sửa:** Đọc điều khoản thật, cấu hình jar.from('LICENSE') vào META-INF khi cần, kiểm tra binary JAR bằng jar --list và đừng gắn nhãn license không đúng.

### Lỗi 17 — Build publish local nhưng remote release chưa có

**Nguyên nhân:** publish trong bài lab chỉ ghi vào build/demo-repo, không phải repository bên ngoài.

**Cách sửa:** Phân biệt task publish, publishToMavenLocal, repository names/URLs. Chỉ thêm remote repository/credentials khi chủ sở hữu đã thiết lập quy trình release.

## 11. Thiết kế quy trình kiểm thử chất lượng tài liệu

### 11.1. Checklist trước khi publish

1. Các public types/methods có Javadoc mô tả hành vi, @param/@return/@throws đúng code chưa?
2. Có link tới package/class/member không tồn tại hoặc warnings không được xử lý không?
3. Java source UTF-8, HTML charset và Javadoc encoding có khớp không?
4. Có Java 17 (hoặc target JDK đã cam kết) trong build toolchain chưa?
5. Sources JAR có đúng source tương ứng với binary version không?
6. Javadoc JAR có index.html và các trang API cần thiết không?
7. Binary JAR có classes/resources đúng và không chứa dữ liệu nhạy cảm không?
8. README quick start có thể copy/biên dịch/run trên một consumer sạch không?
9. docs/USAGE.md/changelog có giải thích breaking changes, hạn chế và migration không?
10. LICENSE/NOTICE có nội dung hợp lệ và được đóng gói/phát hành đúng nghĩa vụ không?
11. POM name/description/license/developer/SCM/URL có đầy đủ theo repository policy không?
12. Maven publication có **from components.java** và không đính kèm trùng sources/javadoc không?
13. Các extra artifacts có classifier/extension duy nhất, không xung đột không?
14. Có kiểm tra thư mục repo thử nghiệm sau publish, không chỉ thấy task publish SUCCESS không?
15. Module binary có được consumer resolve theo group:artifact:version không?
16. IDE có thể lấy sources/Javadoc khi repository/metadata hỗ trợ không?
17. Đã kiểm tra source/Javadoc files **không chứa bí mật hoặc tài sản thiếu quyền phân phối** chưa?
18. CI có chạy Javadoc generation và lưu artifact/HTML preview khi cần review không?
19. Các artifacts của một release có được tạo từ cùng commit/version/Java toolchain không?
20. Có kế hoạch giữ/host docs cho các phiên bản cũ để người dùng không bị đứt link không?

### 11.2. Một chuỗi lệnh kiểm tra CI minh họa

~~~bash
./gradlew clean build javadoc sourcesJar javadocJar docsZip
./gradlew publish
jar --list --file build/libs/docs-library-1.0.0-sources.jar
jar --list --file build/libs/docs-library-1.0.0-javadoc.jar
~~~

Trong CI, có thể dùng pipeline tách stage unit tests, docs generation, artifact validation rồi mới release/publish. **Không upload công khai chỉ vì task publish local thành công**. Khi cần release remote, có thể yêu cầu phê duyệt, signing và environment secrets.

### 11.3. README và Javadoc nên được version hóa đồng bộ

Ví dụ thư viện nâng từ 1.0.0 lên 2.0.0 và đổi tên method:
- Changelog ghi breaking change và migration.
- Javadoc public API phản ánh method mới.
- README quick start không còn dùng method đã bị xóa.
- Sources JAR và binary JAR được tạo từ cùng commit.
- POM/module metadata publish version 2.0.0 đúng.
- API docs online theo version (nếu có) vẫn giữ bản 1.0.0 cho user chưa nâng.

**Thói quen tốt:** Review tài liệu như code. Một phương thức đổi signature mà quick start không đổi có thể khiến users gặp lỗi compile mặc dù binary release vẫn đúng.

## 12. Bài tập tự kiểm tra

**Bài 1.** Task javadoc và javadocJar khác nhau ở output gì? Task nào tạo HTML, task nào đóng gói HTML?

**Bài 2.** Với project java-library, hai API nào thêm sources.jar và javadoc.jar vào Java component theo convention?

**Bài 3.** Một IDE muốn mở code nguồn của thư viện trong debugger, cần tìm artifact nào? Binary JAR đã đủ để Java chạy chưa?

**Bài 4.** Khi gọi withSourcesJar() và withJavadocJar(), MavenPublication đã from components.java. Có nên thêm artifact sourcesJar và artifact javadocJar lần nữa không?

**Bài 5.** Task javadoc output ở đâu theo cấu hình mặc định của Java Plugin? Có thể đổi thông qua API nào?

**Bài 6.** Vì sao tiếng Việt trong Javadoc comment có thể hiển thị sai dù Java source compile được?

**Bài 7.** Một public method nhận name và ném IllegalArgumentException nếu null hoặc blank. Hai Javadoc tags nào quan trọng để mô tả input/error?

**Bài 8.** JavadocJar có tự bao gồm README.md và docs/USAGE.md không? Nếu cần phát hành chúng, có những lựa chọn nào?

**Bài 9.** artifact docsZip gắn trực tiếp vào MavenPublication có chắc tạo một Gradle documentation variant discoverable cho mọi consumer không?

**Bài 10.** Một Java library publish binary.jar nhưng sources.jar lại được tạo từ commit khác. Vì sao điều đó nguy hiểm?

**Bài 11.** Một module có file LICENSE ở root nhưng binary JAR không có LICENSE. Tại sao Gradle không tự copy file ấy vào JAR? Sửa ra sao khi license yêu cầu?

**Bài 12.** Người dùng thêm implementation files('docs-library-1.0.0-javadoc.jar') rồi import Greeter thất bại. Nguyên nhân là gì?

**Bài 13.** Khi publish thử vào build/demo-repo, có đang phát hành Maven Central không?

**Bài 14.** Nếu lib còn có sourceSet test và integrationTest, withSourcesJar() có tự đưa toàn bộ test source vào sources.jar không?

**Bài 15.** Vì sao POM metadata và README không thay thế lẫn nhau?

**Bài 16.** Có nên publish sources JAR của mã proprietary với secrets chỉ vì withSourcesJar rất dễ bật không?

**Bài 17.** Một project dùng Java 17 nhưng máy chỉ có JRE, không có JDK/toolchain. Vì sao task javadoc có thể thất bại?

**Bài 18.** Khi đổi output Javadoc bằng destinationDirectory, javadocJar có còn làm việc đúng không nếu dùng Java Plugin wiring chuẩn?

**Bài 19.** Giải thích classifier sources, javadoc, docs khác group/artifact/version như thế nào.

**Bài 20.** Hãy lập trình tự kiểm tra một release để thấy binary, source, Javadoc và docs archive thuộc **cùng** version 1.0.0.

### Đáp án gợi ý

1. **javadoc** sinh cây HTML; **javadocJar** đóng gói cây đó vào JAR.
2. **withSourcesJar()** và **withJavadocJar()** trên java extension.
3. **Sources JAR** cho source attachment; **binary JAR** là thứ ứng dụng cần cho compile/run.
4. **Không**; đã là documentation variants qua components.java, đính kèm lại có thể trùng artifact.
5. Mặc định **build/docs/javadoc**; dùng Javadoc.destinationDirectory nếu muốn thay.
6. Source encoding hoặc Javadoc encoding/charSet/docEncoding không thống nhất.
7. **@param** và **@throws**, cùng mô tả hành vi bằng văn bản có nghĩa.
8. **Không tự động**; dùng README/site, docs ZIP hoặc doc-files/tùy chỉnh build logic.
9. **Không**; artifact đính kèm trực tiếp có thể ngoài metadata variants, cần thiết kế variant nếu muốn discoverable.
10. IDE nhìn source không khớp binary, dẫn đến method/line mapping sai và khó debug.
11. Jar task chỉ đóng outputs/resources được cấu hình; có thể thêm from('LICENSE') vào META-INF khi phù hợp.
12. Javadoc JAR chứa HTML, không chứa Greeter.class; phải dùng binary JAR/module.
13. **Không**; đó là thư mục local trong build, không có remote release.
14. **Không mặc định**; withSourcesJar dành cho main feature.
15. POM hỗ trợ build resolution/metadata; README giải thích sử dụng; mỗi loại có mục đích riêng.
16. **Không**; phải rà soát license, quyền phân phối, secrets và source policy.
17. Javadoc tool thuộc JDK; Java toolchain cần tồn tại/phù hợp.
18. **Có** khi wiring chuẩn giữ task javadoc là producer và javadocJar lấy output của nó.
19. Classifier xác định một archive bổ sung của cùng module version; group/artifact/version định danh module release.
20. Chạy tasks tạo jar/sourcesJar/javadocJar/docsZip, dùng jar --list kiểm tra entries, kiểm tra tên file/version ở build/libs/distributions, publish local rồi đối chiếu POM/.module với artifacts.

## Tài liệu tham khảo chính thức

- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): Javadoc task, sources/Javadoc outputs và Java source sets.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): mô hình Java component, publication và API/library.
- [Gradle API — JavaPluginExtension](https://docs.gradle.org/current/javadoc/org/gradle/api/plugins/JavaPluginExtension.html): withSourcesJar, withJavadocJar, documentation variants.
- [Gradle DSL — Javadoc task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.javadoc.Javadoc.html): Javadoc source, classpath, options và destination.
- [Gradle API — StandardJavadocDocletOptions](https://docs.gradle.org/current/javadoc/org/gradle/external/javadoc/StandardJavadocDocletOptions.html): encoding, charSet, docEncoding và nhiều HTML options.
- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): lazy destinationDirectory và tác vụ file/archive.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): from components.java, MavenPublication, POM metadata, sources/Javadoc publications.
- [Gradle — Customizing Publishing](https://docs.gradle.org/current/userguide/publishing_customization.html): custom artifacts và khác biệt metadata variants với artifact đính kèm trực tiếp.
- [Gradle API — MavenPublication](https://docs.gradle.org/current/javadoc/org/gradle/api/publish/maven/MavenPublication.html): artifact source, classifier và extension.
- [JDK 17 — javadoc Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): JavaDoc comments, doclet, tags và command-line tool.
- [JDK 17 — Documentation Comment Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html): các thẻ Javadoc, HTML và hợp đồng API.

**Ghi nhớ:** **javadoc** sinh HTML API; **withJavadocJar()** đóng gói HTML thành JAR có classifier javadoc; **withSourcesJar()** đóng nguồn thành JAR có classifier sources. **from components.java** publish binary và documentation variants đúng chuẩn. README, LICENSE, guides và docs ZIP là những tài liệu bổ sung cần quản lý rõ ràng; một custom artifact không mặc nhiên trở thành documentation variant trong metadata. Kiểm tra Javadoc, archive entries, published POM/.module và Java 17 consumer trước khi phát hành thư viện.