# Variant là gì và vì sao một component có nhiều biến thể trong Gradle

## 1. Mục tiêu bài học

Một dependency trong Gradle không nhất thiết tương ứng với **một JAR duy nhất dùng cho mọi tình huống**. Một thư viện có thể cung cấp phần **API** để module khác biên dịch, phần **runtime** để ứng dụng chạy, một bộ **test fixtures** phục vụ kiểm thử, các artifact tài liệu hoặc nhiều bản cho các môi trường khác nhau. Người sử dụng thư viện cần đúng phần tương ứng với công việc của mình, không muốn tải và sử dụng mọi thứ một cách mù quáng.

Gradle giải quyết vấn đề đó bằng **variant-aware dependency resolution**: mỗi **component** có thể công bố nhiều **variant** (biến thể). Mỗi variant mô tả cách sử dụng được hỗ trợ, các dependency và artifact đi cùng; Gradle dùng **attributes** và khi cần cả **capabilities** để chọn biến thể thích hợp cho consumer.

Bài học thuộc nhóm **Variant và capability**, tập trung trực tiếp vào câu hỏi: **Variant là gì, và tại sao một component lại có nhiều biến thể?** Sau khi học, bạn có thể:

1. Phân biệt **component**, **module**, **dependency**, **configuration**, **variant**, **artifact**, **attribute** và **capability**.
2. Giải thích vì sao **apiElements** khác **runtimeElements** trong Java library.
3. Hiểu Gradle dùng yêu cầu của consumer để chọn một producer variant tương thích.
4. Nhận diện các variant bổ sung như **testFixturesApiElements**, **testFixturesRuntimeElements**, feature variants và secondary variants.
5. Dùng **outgoingVariants**, **resolvableConfigurations**, **dependencies** và **dependencyInsight** để xem lựa chọn của Gradle.
6. Xây dựng ví dụ **Java 17 + Gradle Groovy DSL** đa module, có API/runtime và test fixtures, chạy được mà không cần thư viện ngoài.
7. Chẩn đoán **No matching variant**, **Cannot choose between variants**, **capability conflict**, sai Java target và thiếu metadata.
8. Biết khi nào nên công bố thêm variant, khi nào chỉ cần một dependency, và những điều cần giữ để publish đúng.

## 2. Một ví dụ trước khi đi vào thuật ngữ

Giả sử module **:greeter** cung cấp class **Greeter** cho ứng dụng **:app**:

~~~groovy
// app/build.gradle
dependencies {
    implementation project(':greeter')
}
~~~

Ứng dụng có ít nhất hai nhu cầu khác nhau:

- Khi **compileJava**, nó cần nhìn thấy API của Greeter và những dependency công khai cần để biên dịch.
- Khi **run**, nó cần class Greeter thật và những dependency triển khai/runtime cần để thực thi.

Nếu cùng một component luôn ép consumer lấy toàn bộ dependency của thư viện ngay lúc compile, những thư viện chỉ dùng nội bộ có thể xuất hiện trên compile classpath của consumer. Điều đó làm coupling lớn hơn, tăng nguy cơ dùng nhầm API nội bộ và giảm một số cơ hội compile avoidance.

Gradle Java Library Plugin công bố thông thường hai outgoing variants quan trọng:

~~~text
Component :greeter
    |
    +-- apiElements
    |      usage: java-api
    |      dependency metadata thích hợp cho compile của consumer
    |
    +-- runtimeElements
           usage: java-runtime
           dependency metadata thích hợp cho execution của consumer
~~~

Khi **:app:compileJava** cần dependency, **compileClasspath** có các attributes mang ý nghĩa **Java API** và Gradle thường chọn **apiElements**. Khi **:app:run** hoặc **runtimeClasspath** cần dependency, Gradle thường chọn **runtimeElements**. Cả hai có thể trỏ đến cùng JAR chính của thư viện, nhưng **dependency graph và ý nghĩa sử dụng không giống nhau**.

**Điểm cốt lõi:** variant không nhất thiết là một file khác. Hai variant có thể chia sẻ một artifact và khác nhau ở attributes, capabilities hoặc dependency metadata.

## 3. Phân biệt các khái niệm dễ bị gọi lẫn

| Thuật ngữ | Vai trò | Ví dụ |
| --- | --- | --- |
| **Component** | Đơn vị phần mềm mà Gradle phân giải, có thể chứa nhiều variants | Project **:greeter**, external module **org.example:greeter:1.0** |
| **Module** | Đơn vị định danh bên repository, thường group:name:version | **org.example:greeter:1.0** |
| **Dependency** | Yêu cầu của consumer đối với một component/feature | **implementation project(':greeter')** |
| **Configuration** | Đối tượng Gradle mô hình hóa scope khai báo, yêu cầu phân giải hoặc biến thể có thể được tiêu thụ | **implementation**, **compileClasspath**, **apiElements** |
| **Variant** | Một cách cung cấp/sử dụng một component, mang attributes, artifacts, dependencies và capabilities | **apiElements**, **runtimeElements** |
| **Artifact** | File/đầu ra cụ thể của variant | JAR, AAR, native library, source JAR |
| **Attribute** | Cặp khóa–giá trị có kiểu mô tả nhu cầu/đặc tính để matching | **org.gradle.usage=java-api** |
| **Capability** | Định danh một tính năng hay năng lực do variant cung cấp | **demo.variants:greeter-test-fixtures:1.0** |
| **Task** | Đơn vị công việc Gradle thực thi | **compileJava**, **jar**, **test** |

Từ **variant** trong Gradle có nghĩa kỹ thuật là một **tập thuộc tính và metadata có thể được chọn khi giải quyết dependency**. Nó không đơn thuần là “phiên bản 1.0 hoặc 2.0”:

- **Version** giúp chọn bản phát hành component.
- **Variant** giúp chọn **cách sử dụng của component đã chọn**.
- **Artifact** là file mà variant cung cấp; một variant có thể cung cấp nhiều artifact.
- **Task** có thể tạo artifact của variant, nhưng bản thân variant không phải task.
- **Configuration** là mô hình Gradle dùng để khai báo hoặc cung cấp variant; không phải mọi configuration đều là một outgoing variant.

Không nên nói **apiElements chính là một bản JAR còn runtimeElements chính là một bản JAR khác**. Thông thường Gradle có thể dùng cùng một JAR chính của Java library trong cả hai nhưng chọn tập dependency khác nhau.

## 4. Vì sao một component cần nhiều variant?

### 4.1. Compile và runtime là hai nhu cầu khác nhau

Một consumer viết source Java cần chữ ký method, public types và những API dependencies liên quan. Khi chạy, consumer cần toàn bộ implementation và runtime dependencies.

Ví dụ trong thư viện Java:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:public-contract:1.0'
    implementation 'org.example:internal-engine:1.0'
    runtimeOnly 'org.example:runtime-driver:1.0'
}
~~~

Đây là **đoạn minh họa**, các tọa độ **org.example** không phải thư viện thật để chạy ngay. Ý nghĩa:

- **api**: dependency cần được cung cấp trên compile classpath của consumer.
- **implementation**: chi tiết triển khai của library, không nên tự động xuất hiện trên compile classpath của consumer.
- **runtimeOnly**: cần lúc chạy nhưng không phải lúc biên dịch.

Trong Java Library Plugin, dependency metadata trên **apiElements** phản ánh phần phù hợp cho API usage; **runtimeElements** phản ánh các dependencies cần cho runtime. Do đó consumer có thể nhìn thấy **contract** khi compile và **engine/driver** khi chạy mà không phải khai báo hai dependency coordinates riêng.

### 4.2. Một thư viện có tính năng bổ sung tùy chọn

Một component có thể có tính năng **JSON support**, **database adapter**, **logging integration** hoặc **test fixtures** không phải consumer nào cũng cần. Nếu ép tất cả consumer tải mọi thứ, dependency graph phình ra và rủi ro xung đột tăng.

Gradle hỗ trợ **feature variants**: producer tạo một capability riêng cho tính năng bổ sung, và consumer có thể yêu cầu capability đó. Feature có thể có artifacts và dependencies riêng. Đây là cách biểu diễn “một thư viện với nhiều khả năng”, không cần giả định mọi tính năng là API chính.

**Test fixtures** là một ví dụ thực tế được Java Test Fixtures Plugin hỗ trợ: thư viện sản xuất có thể xuất bản mã hỗ trợ kiểm thử, nhưng ứng dụng production không nên tự mang fixtures vào runtime.

### 4.3. Nhiều môi trường hoặc nền tảng

Một component có thể cung cấp biến thể theo:

- JVM target version, ví dụ Java 11 hoặc Java 17.
- Runtime Java, JavaScript, Native hoặc Android platform.
- Debug/release hoặc product flavors trong Android Gradle Plugin.
- Library elements: JAR, classes directory, resources hoặc những artifact set khác.
- Usage: API, runtime, native linking hoặc tài liệu.
- Các thuộc tính do plugin/organization định nghĩa có schema matching tương ứng.

Không phải Java Library Plugin mặc định tự build đầy đủ mọi target kể trên. **Plugin và cách producer được cấu hình** quyết định variants thực sự tồn tại. Kotlin Multiplatform và Android Gradle Plugin có mô hình phong phú hơn Java library đơn giản.

### 4.4. Metadata cho consumer tối ưu và đúng hơn

Variant-aware resolution cho phép consumer yêu cầu đúng thứ phù hợp, thay vì dùng nhiều tên configuration “ngầm hiểu” hoặc chọn file bằng classifier thủ công.

Lợi ích gồm:

1. **Correctness:** không chọn artifact chỉ dành cho môi trường không tương thích.
2. **Separation of concerns:** tách compile API, runtime, fixture và feature.
3. **Dependency hygiene:** tránh kéo implementation dependency vào compile scope khi không cần.
4. **Performance:** hỗ trợ compile avoidance, chọn classes directory thay JAR trong các trường hợp tối ưu.
5. **Publishing:** Gradle Module Metadata có thể mô tả nhiều variants với attributes và dependencies khác nhau.
6. **Diagnostics:** Gradle giải thích tại sao một variant phù hợp, không tương thích hoặc mơ hồ.

## 5. Component, producer và consumer: ai đưa ra yêu cầu?

Gradle gọi bên cung cấp dependency là **producer** và bên cần dependency là **consumer**.

~~~text
CONSUMER (:app)
  configuration: compileClasspath
  attributes được yêu cầu:
    org.gradle.usage = java-api
    org.gradle.category = library
    org.gradle.jvm.version = 17
             |
             | dependency project(':greeter')
             v
PRODUCER (:greeter)
  Component java
    |
    +-- apiElements
    |     usage = java-api
    |     category = library
    |     jvm.version = 17
    |
    +-- runtimeElements
          usage = java-runtime
          category = library
          jvm.version = 17
             |
             v
 Gradle chọn variant tương thích theo matching rules
~~~

Khi consumer phân giải **runtimeClasspath**, request thường là **java-runtime**, vì vậy producer có thể được chọn qua **runtimeElements** thay vì **apiElements**.

**Ví dụ về attributes mang tính minh họa:** attributes chính xác mà Gradle liệt kê có thể còn bao gồm **org.gradle.dependency.bundling**, **org.gradle.libraryelements**, **org.gradle.jvm.environment**, cũng như thuộc tính do plugin khác thêm. Không khẳng định ba dòng ở trên là toàn bộ attributes của một build thực.

### 5.1. Producer khai báo khả năng, consumer khai báo nhu cầu

Producer công bố:

- Các **variants** có thể được chọn.
- **Attributes** của từng variant: đây là thư viện gì, dành cho usage/nền tảng/JVM nào.
- **Capabilities** mà variant cung cấp.
- **Artifacts** và **transitive dependencies** gắn với variant.

Consumer mang vào quá trình giải quyết:

- Component được yêu cầu qua dependency.
- **Resolvable configuration** với attributes mong muốn.
- Capabilities yêu cầu tường minh, nếu consumer cần feature khác default.
- Những constraints/rules của dependency resolution.

Gradle chọn một variant **tương thích và được phân biệt đủ rõ** theo attribute schema, không đơn thuần lấy cái tên đầu tiên sắp xếp alphabet.

### 5.2. Matching không phải so sánh chuỗi tuyệt đối cho mọi attribute

Một số attributes cần match chính xác; một số khác có **compatibility rules** và **disambiguation rules**.

Chẳng hạn với **org.gradle.jvm.version**, một producer target Java thấp hơn thường có thể chạy ở JVM mới hơn, trong khi producer chỉ chạy được trên Java mới hơn có thể không tương thích với consumer target cũ. Đây là quy tắc được Gradle JVM ecosystem modeling áp dụng, không phải quy tắc “mọi số nhỏ đều chấp nhận trong mọi plugin”.

Với **org.gradle.usage**, Gradle có quy tắc phân biệt API và runtime phù hợp cho Java ecosystem. Đừng tự suy rằng matching chỉ so sánh **java-api == java-api** mà không có disambiguation/compatibility.

### 5.3. Khi có nhiều ứng viên

Khái quát:

1. Loại các producer variants **không tương thích** với nhu cầu.
2. Đối chiếu những attributes được yêu cầu và attributes mà producer công bố.
3. Dùng quy tắc tương thích và phân biệt của schema để xác định ứng viên thích hợp.
4. Khi còn đúng một kết quả, chọn variant.
5. Nếu không có ứng viên hoặc không thể phân biệt, báo lỗi có giải thích.

Quy trình hiện hành có nhiều bước hơn, gồm cách xử lý các attributes bổ sung mà chỉ producer có; hãy xem tài liệu **Variant Selection and Attribute Matching** cho thuật toán chính xác. Không viết custom disambiguation rule tùy tiện chỉ để làm một lỗi mismatch biến mất.

## 6. Các attributes phổ biến của JVM variants

| Attribute | Ý nghĩa | Giá trị thường thấy |
| --- | --- | --- |
| **org.gradle.usage** | Consumer cần dùng component để làm gì? | **java-api**, **java-runtime** |
| **org.gradle.category** | Loại component | **library**, **platform**, **enforced-platform**, **documentation** |
| **org.gradle.dependency.bundling** | Packaging có chứa dependencies hay không | **external**, **embedded**, **shadowed** |
| **org.gradle.libraryelements** | Dạng phần tử thư viện | **jar**, **classes**, **resources** |
| **org.gradle.jvm.version** | Mức Java mà variant target | **8**, **11**, **17**, **21** |
| **org.gradle.jvm.environment** | Môi trường JVM dự kiến | **standard-jvm**, môi trường Android tương ứng |
| Attributes riêng của plugin | Những đặc điểm do ecosystem/plugin thêm | Kotlin platform, Android build type/flavor |

Các keys và values này là dữ liệu typed attributes, không phải những biến chuỗi có thể đặt bất kỳ mà Gradle luôn hiểu. Dùng Gradle APIs hoặc plugin chuẩn; khi tạo custom attribute cần khai báo type và compatibility/disambiguation schema hợp lý.

### 6.1. Attribute không phải capability

**Attribute** trả lời: “Tôi cần cách dùng nào?” Ví dụ consumer muốn **java-runtime** và target JVM 17.

**Capability** trả lời: “Tôi cần khả năng/tính năng nào?” Ví dụ consumer muốn **test fixtures** của Greeter, không chỉ API production.

Một variant có thể thỏa cả hai: capability **greeter-test-fixtures** và usage **java-runtime**. Vì thế **testFixturesApiElements** và **testFixturesRuntimeElements** là **hai cách sử dụng của cùng feature capability**, không phải một capability cho compile và capability khác cho runtime.

## 7. Java Library Plugin: apiElements và runtimeElements

### 7.1. Cấu hình sinh ra các biến thể

Trong producer **greeter/build.gradle**:

~~~groovy
plugins {
    id 'java-library'
}

group = 'demo.variants'
version = '1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Java Library Plugin tạo outgoing variants, điển hình gồm **apiElements** và **runtimeElements**. Khi consumer khai báo:

~~~groovy
dependencies {
    implementation project(':greeter')
}
~~~

Gradle **không yêu cầu consumer khai báo trực tiếp apiElements hay runtimeElements**. Java plugin tự xây resolvable configurations với attributes, và engine matching chọn variant phù hợp.

### 7.2. compileClasspath và runtimeClasspath

| Phía consumer | Configuration cần giải quyết | Usage thường yêu cầu | Outgoing variant thường được chọn |
| --- | --- | --- | --- |
| Biên dịch source main | **compileClasspath** | **java-api** | **apiElements** |
| Chạy ứng dụng | **runtimeClasspath** | **java-runtime** | **runtimeElements** |
| Biên dịch test | **testCompileClasspath** | **java-api** | API variant của dependency chính/fixture tương ứng |
| Chạy test | **testRuntimeClasspath** | **java-runtime** | Runtime variant của dependency chính/fixture tương ứng |

Từ “thường” là quan trọng: Gradle có thể chọn một **secondary artifact set** của apiElements, hoặc xử lý metadata/compatibility theo hệ sinh thái cụ thể. Không phải mọi external Maven module đều xuất bản cùng kiểu variants như Gradle project.

### 7.3. Không nhầm api/implementation với apiElements/runtimeElements

- **api**, **implementation**, **runtimeOnly** thường là các **dependency configurations** để khai báo dependency ở producer.
- **apiElements**, **runtimeElements** là các **consumable configurations** mô hình hóa outgoing variants để consumer chọn.
- **compileClasspath**, **runtimeClasspath** là các **resolvable configurations** mô hình hóa nhu cầu từ consumer.

Trong thiết kế Gradle hiện đại, mỗi configuration nên có **một vai trò chính**: khai báo dependencies, phân giải dependencies, hoặc được tiêu thụ. Cố gọi **configurations.apiElements.resolve()** như một nơi lấy dependency là nhầm vai trò; dùng **runtimeClasspath/compileClasspath** ở bên consumer để resolve.

### 7.4. Một ví dụ transitive dependency

Producer:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:public-api:1.0'
    implementation 'org.example:internal-codec:1.0'
    runtimeOnly 'org.example:runtime-driver:1.0'
}
~~~

Đây là **đoạn minh họa không thể chạy độc lập** vì **org.example** là tọa độ giả. Nếu được thay bằng các artifact thật:

- Compile classpath của consumer thường nhận **public-api** cùng API của producer, không tự nhận **internal-codec**.
- Runtime classpath của consumer cần **public-api**, **internal-codec** và **runtime-driver** theo metadata.
- Producer cần các dependency triển khai của chính mình để compile và tạo artifact.

**Thư viện implementation vẫn tồn tại trong producer compilation**; điều được tách là dependency nào cần lộ ra **compile classpath của consumer**.

## 8. Vì sao một component có thể thêm test-fixtures variants?

### 8.1. Test fixture là tính năng khác API production

Trong một thư viện, code mẫu, dữ liệu thử, builders hoặc helper để test có thể được nhiều module cần. Không nên đưa chúng vào artifact chính chỉ để ứng dụng production có thể compile.

Khi áp dụng:

~~~groovy
plugins {
    id 'java-library'
    id 'java-test-fixtures'
}
~~~

Gradle tạo source set **testFixtures**, cùng các biến thể liên quan như:

~~~text
Component :greeter
  |
  +-- apiElements
  +-- runtimeElements
  |
  +-- testFixturesApiElements
  +-- testFixturesRuntimeElements
~~~

Các variant test fixtures mang **capability khác** so với main feature, thường có tên tương đương **group:name-test-fixtures:version**. Do đó consumer có thể lấy **main library** để chạy app và **test fixture library** để chạy test mà không bắt tất cả người dùng production lấy fixture.

### 8.2. Consumer yêu cầu fixture có chủ đích

Trong app:

~~~groovy
dependencies {
    implementation project(':greeter')
    testImplementation(testFixtures(project(':greeter')))
}
~~~

Dòng đầu yêu cầu **main capability** của Greeter. Dòng sau yêu cầu **test-fixtures capability** qua DSL **testFixtures(...)**.

**Không cần** tự ghi một dependency tọa độ mới mang classifier giả để dùng fixture. Gradle biết feature variants và chọn API/runtime variant thích hợp theo các attributes của test compile/runtime configurations.

### 8.3. Mức độ kết hợp capability và variant

Ví dụ nếu component **demo.variants:greeter:1.0** công bố:

| Variant | Capability | Usage |
| --- | --- | --- |
| apiElements | demo.variants:greeter:1.0 | java-api |
| runtimeElements | demo.variants:greeter:1.0 | java-runtime |
| testFixturesApiElements | demo.variants:greeter-test-fixtures:1.0 | java-api |
| testFixturesRuntimeElements | demo.variants:greeter-test-fixtures:1.0 | java-runtime |

Bảng mô tả mô hình thông thường từ **java-test-fixtures**. Các attributes/artifacts khác có thể xuất hiện trong báo cáo. Nên hiểu:

- **Hai biến thể API/runtime** cung cấp cùng main capability nhưng phục vụ hai usage.
- **Hai biến thể fixture API/runtime** cung cấp cùng fixture capability nhưng phục vụ hai usage.
- Main feature và fixture feature có **capabilities khác**, do đó có thể cùng tham gia một dependency graph khi consumer yêu cầu cả hai.
- Gradle xử lý những variant có cùng capability để không chọn các provider mâu thuẫn trong một graph; đừng suy từ đó rằng cùng component không thể được phân giải cho compileClasspath và runtimeClasspath riêng biệt của các cấu hình khác nhau.

## 9. Ví dụ Java 17 hoàn chỉnh: một thư viện có main và fixture variants

Bài thực hành dưới đây **không cần thư viện bên ngoài**. Ta dùng **java-library**, **java-test-fixtures** và **application** core plugins, tạo hai project trong cùng Gradle build:

- **:greeter**: công bố API/runtime variants và test fixtures variants.
- **:app**: dùng Greeter trong production, dùng FixtureMessages trong source test.

Ta dùng **JavaExec** để chạy class có main() đặt trong test source set, giúp chứng minh fixture classpath mà không cần thêm JUnit dependency.

### 9.1. Cấu trúc tệp

~~~text
variant-lab/
├── settings.gradle
├── build.gradle
├── gradlew                       # sinh từ Gradle Wrapper
├── gradlew.bat                   # sinh từ Gradle Wrapper
├── gradle/wrapper/...            # sinh từ Gradle Wrapper
├── greeter/
│   ├── build.gradle
│   ├── src/main/java/demo/greeter/Greeter.java
│   └── src/testFixtures/java/demo/greeter/fixtures/FixtureMessages.java
└── app/
    ├── build.gradle
    ├── src/main/java/demo/app/Main.java
    └── src/test/java/demo/app/FixtureSmoke.java
~~~

Nếu repository mới chưa có Wrapper và máy đã cài Gradle CLI phù hợp, chạy **gradle wrapper** ở root để tạo Wrapper. Các lần sau dùng **./gradlew** trên Linux/macOS và **.\gradlew.bat** trên Windows. Cần Gradle version tương thích với JDK đang chạy Gradle và **Java 17 toolchain** có sẵn hoặc được provisioning đúng.

### 9.2. settings.gradle

~~~groovy
rootProject.name = 'variant-lab'
include ':greeter', ':app'
~~~

**:greeter** và **:app** là hai project, **không phải hai variants**. Variants nằm trong component mà plugin của một project công bố.

### 9.3. build.gradle ở root

~~~groovy
plugins {
    id 'base'
}
~~~

Root chỉ có Base plugin. Không phải mọi project đều phải áp dụng Java plugin.

### 9.4. greeter/build.gradle

~~~groovy
plugins {
    id 'java-library'
    id 'java-test-fixtures'
}

group = 'demo.variants'
version = '1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**group/version** được đặt trực tiếp tại **:greeter** để Gradle có định danh rõ cho capability chính và fixture. Tránh giả định giá trị **group** ở root luôn tự kế thừa vào subproject.

### 9.5. greeter/src/main/java/demo/greeter/Greeter.java

~~~java
package demo.greeter;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Đây là API production. Khi ứng dụng compile, nó chỉ cần nhìn thấy class **Greeter** cùng những compile dependencies cần thiết.

### 9.6. greeter/src/testFixtures/java/demo/greeter/fixtures/FixtureMessages.java

~~~java
package demo.greeter.fixtures;

import demo.greeter.Greeter;

public final class FixtureMessages {
    private FixtureMessages() {
    }

    public static String sample() {
        return "fixture=" + Greeter.greet("Fixture");
    }
}
~~~

Java Test Fixtures Plugin cấu hình để fixture source có thể tham chiếu classes của main source set trong cùng project. Vì vậy **FixtureMessages** import **Greeter** mà không cần nhân bản source.

Mã fixture **không tự nằm trong artifact production chính**. Consumer phải yêu cầu feature fixture nếu muốn dùng class này trong test.

### 9.7. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':greeter')
    testImplementation(testFixtures(project(':greeter')))
}

application {
    mainClass = 'demo.app.Main'
}

tasks.register('runFixtureCheck', JavaExec) {
    group = 'verification'
    description = 'Chạy class trong test source set dùng fixture variant'
    dependsOn(tasks.named('testClasses'))
    classpath = sourceSets.test.runtimeClasspath
    mainClass.set('demo.app.FixtureSmoke')
}
~~~

Quan trọng:

1. **implementation project(':greeter')** đặt main capability vào classpath thích hợp của app.
2. **testImplementation(testFixtures(project(':greeter')))** thêm fixture capability vào test source set, không vào production runtime classpath.
3. **runFixtureCheck** cần **testClasses** trước khi chạy, lấy **test.runtimeClasspath** để có compiled test classes, main classes và fixture dependencies.
4. **runFixtureCheck** là JavaExec task riêng, không phải Gradle Test task/JUnit. Bài học không cần external dependency.
5. Không dùng trực tiếp **configurations.apiElements** hay **testFixturesRuntimeElements** ở consumer: Gradle quyết định qua attributes và yêu cầu capability.

### 9.8. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.greeter.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("app=" + Greeter.greet("Gradle"));
    }
}
~~~

### 9.9. app/src/test/java/demo/app/FixtureSmoke.java

~~~java
package demo.app;

import demo.greeter.fixtures.FixtureMessages;

public final class FixtureSmoke {
    private FixtureSmoke() {
    }

    public static void main(String[] args) {
        System.out.println(FixtureMessages.sample());
    }
}
~~~

Class này nằm trong **test source set**, nên Gradle dùng **testImplementation** và **testRuntimeClasspath** của app. Nếu chuyển nó sang **src/main/java** mà giữ fixture dependency chỉ trong testImplementation, compilation của main sẽ không nhìn thấy class FixtureMessages — đó chính là ranh giới mà variant và configuration tạo ra.

### 9.10. Lệnh chạy và kết quả đáng tin

Linux/macOS:

~~~bash
./gradlew --version
./gradlew projects
./gradlew :greeter:outgoingVariants
./gradlew :app:resolvableConfigurations
./gradlew :app:compileJava
./gradlew -q :app:run
./gradlew :app:compileTestJava
./gradlew -q :app:runFixtureCheck
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :greeter:outgoingVariants
.\gradlew.bat :app:resolvableConfigurations
.\gradlew.bat :app:compileJava
.\gradlew.bat -q :app:run
.\gradlew.bat :app:compileTestJava
.\gradlew.bat -q :app:runFixtureCheck
~~~

Dòng stdout **chính xác do class Main in** là:

~~~text
app=Xin chào, Gradle!
~~~

Dòng stdout **chính xác do class FixtureSmoke in** là:

~~~text
fixture=Xin chào, Fixture!
~~~

Gradle có thể in thêm task logs, cảnh báo hoặc thông tin daemon; các đoạn stdout trên là dòng do Java source phát ra, không phải khẳng định toàn bộ console output bất biến.

**Dự án không cần repository Maven bên ngoài** vì tất cả dependency đều là project dependencies và các plugin đều là core plugins Gradle. Khi thêm thư viện bên ngoài cho ứng dụng thực, hãy cấu hình repository phù hợp tại settings của build.

### 9.11. Kiểm tra chương trình Java 17 bằng javac/java

Vì source Java của demo không phụ thuộc API Gradle, bạn có thể xác nhận nội dung class độc lập với task Gradle.

Linux/macOS:

~~~bash
mkdir -p out

javac --release 17 -d out \
  greeter/src/main/java/demo/greeter/Greeter.java \
  app/src/main/java/demo/app/Main.java

javac --release 17 -cp out -d out \
  greeter/src/testFixtures/java/demo/greeter/fixtures/FixtureMessages.java \
  app/src/test/java/demo/app/FixtureSmoke.java

java -cp out demo.app.Main
java -cp out demo.app.FixtureSmoke
~~~

Hai dòng do hai lệnh java cuối in lần lượt:

~~~text
app=Xin chào, Gradle!
fixture=Xin chào, Fixture!
~~~

Trên Windows PowerShell, tạo out bằng **New-Item -ItemType Directory -Force out**, rồi chạy hai lệnh **javac --release 17** với đường dẫn file tương đương trên từng dòng và **java -cp out**. Các lệnh Gradle Wrapper ở mục 9.10 đã có cú pháp PowerShell đầy đủ.

**Chạy javac thủ công chỉ xác minh Java code**, không chứng minh Gradle đã chọn đúng variant. Muốn kiểm chứng variant-aware resolution phải dùng báo cáo/commands của Gradle.

## 10. Quan sát outgoing variants của producer

Task **outgoingVariants** cho biết producer có những consumable variants nào, attributes/capabilities/artifacts tương ứng.

~~~bash
./gradlew :greeter:outgoingVariants
./gradlew :greeter:outgoingVariants --variant apiElements
./gradlew :greeter:outgoingVariants --variant runtimeElements
./gradlew :greeter:outgoingVariants --variant testFixturesApiElements
./gradlew :greeter:outgoingVariants --variant testFixturesRuntimeElements
~~~

Trong một build tương tự demo, report thường có:

~~~text
apiElements
  org.gradle.usage = java-api
  org.gradle.category = library
  capability = demo.variants:greeter:1.0

runtimeElements
  org.gradle.usage = java-runtime
  org.gradle.category = library
  capability = demo.variants:greeter:1.0

testFixturesApiElements
  org.gradle.usage = java-api
  capability = demo.variants:greeter-test-fixtures:1.0

testFixturesRuntimeElements
  org.gradle.usage = java-runtime
  capability = demo.variants:greeter-test-fixtures:1.0
~~~

**Đây là bản tóm tắt minh họa**, không phải nguyên văn toàn bộ console output. Report thực còn có nhiều attributes, artifacts và mô tả khác, tùy Gradle version/plugin.

**Từ báo cáo:** có thể thấy một component đã công bố nhiều variants cùng và khác capability. Người dùng app thông thường không cần tự chọn tên outgoing variant; consumer configurations quyết định phần nào phù hợp.

### 10.1. Secondary variants như classes và resources

**apiElements** có thể bao gồm secondary artifact variants như **classes**. Chúng giúp Gradle trong một số trường hợp dùng trực tiếp thư mục .class khi biên dịch project dependency thay vì trước tiên đóng thành JAR.

Không được nhầm:

- **apiElements** là primary outgoing variant dùng ở dependency graph.
- **classes** có thể là một **secondary artifact set** được chọn trong pha artifact resolution.
- **jar** là task tạo artifact JAR, không phải tên bắt buộc của mọi variant.

Một component có thể có **nhiều primary variants**, trong khi một primary variant lại có **nhiều secondary artifact sets**. Do đó “variant bằng một file” là cách hiểu quá hẹp.

### 10.2. Một configuration có thể chỉ là dependency scope

Khi chạy:

~~~bash
./gradlew :greeter:resolvableConfigurations
~~~

bạn sẽ thấy **resolvable configurations** của producer; kết quả không nhất thiết liệt kê **implementation** theo cách một dependency tree có thể resolve được, bởi **implementation** thường được dùng để khai báo dependencies chứ không được thiết kế để resolve trực tiếp.

Trong Java ecosystem hiện đại:

~~~text
api / implementation / runtimeOnly
         |
         v
dependency scopes (khai báo dependencies)

compileClasspath / runtimeClasspath
         |
         v
resolvable configurations (consumer có yêu cầu)

apiElements / runtimeElements
         |
         v
consumable configurations (producer công bố variants)
~~~

Sự khác biệt vai trò giúp tránh cấu hình tùy tiện một configuration vừa khai báo, vừa resolve, vừa consumable.

## 11. Xem bên consumer: Gradle đã chọn biến thể nào?

### 11.1. Resolvable configurations report

~~~bash
./gradlew :app:resolvableConfigurations
./gradlew :app:resolvableConfigurations --configuration compileClasspath
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath
./gradlew :app:resolvableConfigurations --configuration testCompileClasspath
./gradlew :app:resolvableConfigurations --configuration testRuntimeClasspath
~~~

Báo cáo mô tả requirements của consumer. Đối chiếu **org.gradle.usage**, **org.gradle.category**, **org.gradle.jvm.version** với outgoing variants của **:greeter** để hiểu tại sao Gradle chọn một variant.

### 11.2. Dependency tree

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testCompileClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
~~~

Cùng **project :greeter** có thể xuất hiện trong nhiều reports. Điều đó **không** tự chứng minh Gradle dùng cùng một variant trong tất cả reports. Mỗi resolvable configuration có yêu cầu khác nhau và được giải quyết trong context của nó.

Trong test classpaths của demo, có thể thấy cả dependency vào main feature của **:greeter** và dependency fixture capability. Dependency tree không nhất thiết hiển thị capability hoặc variant bằng một dòng dễ đọc; dùng thêm **dependencyInsight** hoặc outgoing/resolvable reports.

### 11.3. dependencyInsight

~~~bash
./gradlew :app:dependencyInsight \
  --configuration compileClasspath \
  --dependency greeter

./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath \
  --dependency greeter

./gradlew :app:dependencyInsight \
  --configuration testRuntimeClasspath \
  --dependency greeter
~~~

Với shell Windows PowerShell, viết mỗi lệnh trên một dòng, không dùng dấu gạch chéo ngược để nối dòng:

~~~powershell
.\gradlew.bat :app:dependencyInsight --configuration compileClasspath --dependency greeter
.\gradlew.bat :app:dependencyInsight --configuration runtimeClasspath --dependency greeter
.\gradlew.bat :app:dependencyInsight --configuration testRuntimeClasspath --dependency greeter
~~~

Trên Gradle hiện đại, **dependencyInsight --all-variants** có thể bổ sung các variants được xét, tùy trạng thái resolution và phiên bản. Đừng suy một cây dependencies rút gọn là đã hiển thị mọi chi tiết matching.

**Quy tắc quan sát:** kiểm tra báo cáo producer **outgoingVariants** trước, kiểm tra attributes consumer **resolvableConfigurations** sau, cuối cùng dùng **dependencyInsight** để xem quyết định cụ thể.

## 12. Capability là gì và liên quan đến variants ra sao?

### 12.1. Identity và feature

Một component thường có **default capability** trùng với tọa độ **group:name:version**. Ví dụ ở demo:

~~~text
demo.variants:greeter:1.0
~~~

Khi bật Java Test Fixtures Plugin, Gradle tạo capability khác cho fixture:

~~~text
demo.variants:greeter-test-fixtures:1.0
~~~

Không nên nói **test-fixtures là version khác của greeter**: nó là feature của cùng component. Capability cho Gradle biết variant đó cung cấp **khả năng nào**, còn attributes phân biệt **cách sử dụng khả năng ấy**.

### 12.2. Một feature có thể có cả API và runtime variant

~~~text
Main capability
  - apiElements      (java-api)
  - runtimeElements  (java-runtime)

Fixtures capability
  - testFixturesApiElements      (java-api)
  - testFixturesRuntimeElements  (java-runtime)
~~~

Một consumer có thể yêu cầu main capability cho ứng dụng và fixtures capability cho test. Gradle dùng capability matching và attributes cùng nhau.

Hai producer độc lập có thể cung cấp **cùng một capability**, ví dụ hai implementation loại trừ nhau cho cùng một logging binding. Khi cả hai xuất hiện trong một dependency graph, Gradle có thể báo **capability conflict** và cần chính sách lựa chọn rõ. Đây là **mâu thuẫn khả năng**, khác với “không variant nào có attributes tương thích”.

### 12.3. Custom feature variants

Trong một Java library, có thể đăng ký feature **metrics** như sau:

~~~groovy
plugins {
    id 'java-library'
}

group = 'demo.variants'
version = '1.0'

java {
    registerFeature('metrics') {
        usingSourceSet(sourceSets.create('metrics'))
    }
}
~~~

Đoạn này **chỉ minh họa producer configuration**, không phải tệp build độc lập hoàn chỉnh để chạy chức năng metrics. Bạn còn cần source của feature, các dependencies riêng và consumer có yêu cầu feature.

Gradle tạo các configurations cho feature như **metricsApi**, **metricsImplementation**, **metricsApiElements**, **metricsRuntimeElements** và capability mặc định theo quy ước tên của feature, thường có dạng **group:component-metrics:version**.

Consumer có thể yêu cầu capability tường minh:

~~~groovy
dependencies {
    implementation(project(':greeter')) {
        capabilities {
            requireCapability('demo.variants:greeter-metrics')
        }
    }
}
~~~

**Không ghép nguyên hai đoạn custom feature vào demo ở mục 9 nếu chưa thêm source set metrics và cập nhật producer.** Mục tiêu minh họa rằng một producer có thể thêm feature; consumer phải yêu cầu đúng capability.

### 12.4. Khác biệt giữa feature variants và nhiều module tách riêng

Một component với nhiều feature variants phù hợp khi những features cùng thuộc một thư viện, chia sẻ identity/version và muốn Gradle thể hiện API riêng. Nhiều module độc lập phù hợp khi chúng có vòng đời phát hành, ownership, dependency policy hoặc versioning khác nhau.

Không cố biến tất cả module thành variants chỉ để giảm số project trong Gradle. Độ phức tạp variant metadata, capabilities và publishing phải có giá trị thực.

## 13. Gradle Module Metadata và Maven POM

### 13.1. Metadata quyết định consumer biết những biến thể nào

Khi consumer lấy **project dependency**, Gradle có thể trực tiếp biết model của producer. Khi consumer lấy **external dependency** từ repository, Gradle cần đọc metadata được xuất bản.

**Gradle Module Metadata** (file **.module**) mô tả variants, attributes, capabilities, dependencies và artifacts phong phú hơn một Maven POM truyền thống. Maven POM tập trung vào coordinates/scopes/dependencies; Gradle có thể **suy diễn** một số variants từ Maven metadata nhưng không nhất thiết tái tạo được mọi feature và custom attribute của producer.

Vì vậy việc một project dependency sử dụng test fixtures đúng không có nghĩa **mọi bản phát hành Maven bên ngoài** cũng có fixture capability tương đương. Producer cần publish metadata thích hợp và repository phải cung cấp metadata đó.

### 13.2. Xuất bản một Java component

Ví dụ minh họa trong producer:

~~~groovy
plugins {
    id 'java-library'
    id 'java-test-fixtures'
    id 'maven-publish'
}

group = 'demo.variants'
version = '1.0'

publishing {
    publications {
        library(MavenPublication) {
            from components.java
        }
    }
}
~~~

Đây **không phải cấu hình cần thiết để chạy lab nội bộ**, và chưa có repository đích/credentials để publish thật. Nó cho thấy sử dụng **components.java** giúp maven-publish lấy model Java component cùng các variants được công bố.

Khi publish, kiểm tra generated Gradle Module Metadata và POM. Không tự tin rằng một POM sẽ giữ nguyên custom attributes/capabilities của Gradle; khi consumer là Gradle và cần feature variants, **.module metadata** đặc biệt quan trọng.

### 13.3. Compatibility với consumer khác Gradle

Một Maven consumer thông thường không áp dụng đầy đủ Gradle attribute schema. Nếu thư viện cần dùng từ Maven/IDE/tool khác, phải thiết kế artifact, classifier và POM sao cho người sử dụng có thể lấy phần tương ứng.

Không hứa một custom variant được publish sẽ được mọi tool hiểu giống Gradle. Khi feature quan trọng cho nhiều ecosystems, hãy cân nhắc xuất bản module riêng hoặc viết tài liệu rõ ràng.

## 14. Khi nào Gradle báo No matching variant?

Thông báo thường có dạng:

~~~text
No matching variant of project :greeter was found.
The consumer was configured to find a library ...
...
- Variant 'apiElements' ... incompatible because ...
- Variant 'runtimeElements' ... incompatible because ...
~~~

Câu chữ và attributes được liệt kê thay đổi theo Gradle version/plugin; đây chỉ là **dạng lỗi minh họa**.

Một số nguyên nhân:

| Nguyên nhân | Biểu hiện | Hướng sửa |
| --- | --- | --- |
| Consumer yêu cầu Java version quá thấp | Producer target JVM cao hơn yêu cầu | Dùng toolchain/variant tương thích, không hạ thông số trên giấy |
| Khác platform | Consumer yêu cầu JVM, producer chỉ có native/JS/Android variant | Dùng đúng component/plugin hoặc publish JVM variant |
| Usage không tương thích | Yêu cầu java-api nhưng producer công bố khác | Xác nhận producer outgoing variants và consumer attributes |
| Category không đúng | Consumer cần library, producer chỉ có platform | Dùng platform(...) hoặc dependency semantics đúng |
| Không có consumable configuration | Producer chưa áp dụng plugin công bố component/variant | Kiểm tra plugin và canBeConsumed/attributes |
| Custom attributes không match | Producer/consumer dùng type/value/schema khác | Chuẩn hóa attribute key, type, compatibility rules |
| Consumer yêu cầu capability không có | **testFixtures(...)** với library không publish fixtures | Bật java-test-fixtures hoặc sửa yêu cầu |
| Artifact/metadata không có | External module thiếu .module hoặc artifact variant | Kiểm tra metadata, publication và repository |

### 14.1. JVM target mismatch

Trong demo, producer và consumer đều dùng **JavaLanguageVersion.of(17)**. Nếu producer chỉ được biên dịch cho Java 21 nhưng consumer yêu cầu Java 17, Gradle có thể không chọn variant vì **org.gradle.jvm.version** không tương thích.

**Không sửa bằng cách giả mạo attribute producer thành 17 khi bytecode thực tế yêu cầu Java 21.** Giải pháp phải làm artifact thật sự tương thích (compile với JDK/toolchain và API phù hợp), chọn bản producer khác hoặc nâng môi trường consumer nếu được phép.

Cũng phân biệt:

- **JDK chạy Gradle**: môi trường thực thi Gradle/daemon.
- **Java toolchain**: compiler/runtime mà task Java dùng.
- **org.gradle.jvm.version** của outgoing variant: đặc tính target JVM Gradle công bố, thường suy ra từ cấu hình Java plugin.

Chúng có thể khác nhau, nhưng phải nhất quán về khả năng thực tế.

### 14.2. Không chọn đúng category

Nếu consumer yêu cầu **platform** (BOM/dependency constraints) nhưng producer là **library**, hoặc ngược lại, Gradle có thể báo variant category không phù hợp. Dùng cú pháp dependency có ngữ nghĩa đúng:

~~~groovy
dependencies {
    implementation platform('org.example:example-bom:1.0')
}
~~~

Đây là **đoạn cú pháp minh họa**, tọa độ BOM giả. Một platform là dạng component/variant khác một Java library JAR. Đừng ép một JAR library thường đóng vai trò platform chỉ bằng cách sửa classifier.

### 14.3. “No variants exist” khi custom consumable configuration thiếu attributes

Một custom producer có thể tạo configuration tiêu thụ artifact nhưng **không gắn attributes phù hợp**. Variant-aware resolution cần producer công bố variants có attributes; một configuration không attributes không tự đáp ứng yêu cầu.

Gradle hiện đại khuyến nghị định nghĩa các roles rõ ràng và attach attributes ít nhất cho consumable configurations. Không giải quyết bằng cách chọn configuration theo tên thủ công trong dependency declaration theo kiểu legacy nếu có thể thiết kế variants đúng.

## 15. Khi nào Gradle báo Cannot choose between variants?

Lỗi ambiguity có thể xuất hiện nếu nhiều outgoing variants của producer **đều tương thích** với consumer nhưng attribute schema không đủ thông tin hoặc quy tắc phân biệt để chọn một.

Ví dụ bạn tự thêm:

~~~text
producer:
  - blueElements: category=library, usage=java-runtime
  - greenElements: category=library, usage=java-runtime

consumer:
  - cần category=library, usage=java-runtime
~~~

Nếu không có attribute/capability khác phân biệt hai variants, Gradle không thể hiểu blue hay green đúng hơn.

Cách xử lý:

1. Xác định **hai variants thật sự khác nhau ở nghiệp vụ nào**: JVM version, environment, packaging hay feature?
2. Khai báo attribute riêng phù hợp và **đúng type**, có schema compatibility/disambiguation khi cần.
3. Hoặc phân biệt bằng **capability** khi chúng là features khác nhau.
4. Nếu thực tế không có hai cách sử dụng có giá trị, chỉ công bố một variant để tránh ambiguity.
5. Dùng **outgoingVariants** và **resolvableConfigurations** để xác nhận thay vì đặt một resolution rule toàn cục tùy tiện.

Đối với Java Library Plugin chuẩn, các attributes mặc định đã được thiết kế để phân biệt API/runtime usage, nên không nên tự sửa chúng khi chưa hiểu yêu cầu.

## 16. Variant conflict khác capability conflict

Hai loại lỗi dễ bị nhầm:

**No matching/ambiguous variant:** lỗi chọn một cách sử dụng phù hợp từ cùng producer component dựa trên attributes.

**Capability conflict:** một dependency graph có nhiều providers cung cấp cùng một capability không được đồng thời tồn tại theo quy tắc capability resolution; Gradle cần chọn provider hoặc báo xung đột.

Ví dụ ở ecosystem logging, hai implementation khác nhau cùng khai báo capability “SLF4J binding” có thể xung đột. Đây là **ví dụ khái niệm**; capability cần thật sự được nhà sản xuất công bố hoặc consumer gắn metadata rule, không phải Gradle mặc định biết mọi binding nào là đối thủ.

Không dùng **force version** hoặc **exclude** bừa bãi để che mọi capability conflict. Phải quyết định rõ implementation nào được phép cung cấp khả năng đó, và giữ dependency graph nhất quán.

## 17. Variant có phải configuration trong Gradle không?

Câu trả lời là **liên quan chặt nhưng không đồng nhất**.

Ở Java Library Plugin:

- **apiElements** và **runtimeElements** là **consumable configurations** nên đại diện cho outgoing variants.
- **api** và **implementation** là scopes khai báo dependency; không phải outgoing variants tự được consumer chọn.
- **compileClasspath** và **runtimeClasspath** là resolvable configurations với attributes thể hiện nhu cầu của consumer.
- Một consumable configuration có thể có **secondary variants** cho artifact sets, ví dụ classes/resources.
- Khi publish, Gradle Module Metadata có thể chứa variants mô tả từ component và metadata liên quan.

Trong code custom plugin hiện đại, cần sử dụng API configuration roles đúng: **canBeConsumed** cho variants producer, **canBeResolved** cho consumer requests, **canBeDeclared** cho dependency scopes theo Gradle version/API. Tránh để cả ba vai trò bật tùy tiện, đặc biệt trong Gradle mới.

## 18. Thử nghiệm có chủ đích trên Java 17 lab

Mỗi lần thử **một thay đổi**, sau đó hoàn tác.

### Thử 1: Quan sát main variant

Chạy:

~~~bash
./gradlew :greeter:outgoingVariants --variant apiElements
./gradlew :greeter:outgoingVariants --variant runtimeElements
~~~

Ghi **usage**, **capability**, **JVM target**, **artifact**. Xác định điểm giống và khác; không suy từ cùng JAR thành cùng variant.

### Thử 2: Kiểm tra consumer requests

~~~bash
./gradlew :app:resolvableConfigurations --configuration compileClasspath
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath
~~~

So sánh **java-api** với **java-runtime**. Dùng **:app:dependencyInsight** để quan sát quyết định thực tế của Gradle.

### Thử 3: Bỏ fixture dependency ở app

Tạm xóa:

~~~groovy
testImplementation(testFixtures(project(':greeter')))
~~~

Chạy **./gradlew :app:compileTestJava**. Java source FixtureSmoke không nhìn thấy **demo.greeter.fixtures.FixtureMessages**, nên compiler báo không tìm thấy package/class. Khôi phục dòng dependency.

### Thử 4: Bỏ java-test-fixtures ở greeter

Tạm bỏ plugin:

~~~groovy
id 'java-test-fixtures'
~~~

Giữ consumer đang yêu cầu **testFixtures(project(':greeter'))** rồi chạy **:app:compileTestJava**. Gradle không còn fixture capability/variant được cung cấp nên việc resolution thất bại. Khôi phục plugin trước khi tiếp tục.

### Thử 5: Thay Java target

Nếu có sẵn cả Java 17 và một Java toolchain mới hơn, có thể thử một cấu hình target không tương thích để xem Gradle báo **org.gradle.jvm.version**. Không sửa attribute JVM version thành giá trị giả để lừa matching; muốn kiểm chứng nên compile artifact thật sự cho mức version đó và so sánh.

### Thử 6: Kiểm tra ranh giới production/test

Tạm đặt import **FixtureMessages** vào **app/src/main/java/demo/app/Main.java**. Vì fixture dependency chỉ nằm trong testImplementation, **compileJava** không được đảm bảo nhìn thấy class này. Hoàn tác và giữ fixture trong source test. Đây là mục tiêu của khả năng chọn variant theo nhu cầu.

## 19. Những hiểu lầm phổ biến

| Hiểu lầm | Điều đúng hơn |
| --- | --- |
| “Một component chỉ là một JAR.” | Component có thể công bố nhiều variants, artifacts và dependency graphs. |
| “Variant chỉ là version 1.0 hay 2.0.” | Version chọn bản phát hành; variant chọn cách sử dụng của bản đó. |
| “apiElements luôn là một JAR khác runtimeElements.” | Chúng thường có thể chia sẻ JAR chính nhưng khác usage/dependency metadata. |
| “implementation là outgoing variant.” | implementation thường là dependency scope; outgoing variant là apiElements/runtimeElements. |
| “Một project bằng một variant.” | Một project Java có thể công bố nhiều variants; một build gồm nhiều projects. |
| “compileClasspath và apiElements là hai tên gọi tương đương.” | compileClasspath là yêu cầu resolve của consumer; apiElements là khả năng của producer. |
| “Tôi phải ghi tên variant trong implementation project(...).” | Gradle thường tự chọn bằng attributes. |
| “Capability giống attribute.” | Capability mô tả tính năng/identity; attribute mô tả đặc tính và usage. |
| “Fixture phải đưa vào implementation của ứng dụng.” | Test fixtures nên được yêu cầu trong test scope khi cần. |
| “outgoingVariants liệt kê task sẽ chạy.” | Nó liệt kê các variants producer cung cấp, không phải task graph. |
| “Một consumer luôn tải mọi artifact của mọi variant.” | Gradle chọn variant/artifact phù hợp; không tải toàn bộ chỉ vì producer công bố chúng. |
| “No matching variant là thiếu file trong cache.” | Thường là metadata/attribute/capability không tương thích, cần đọc lý do cụ thể. |
| “Có testFixtures plugin nghĩa là test tự chạy.” | Plugin tạo fixture source set/variants; task test vẫn cần test framework và cấu hình riêng nếu muốn chạy test. |
| “Maven POM luôn chứa toàn bộ variants của Gradle.” | Gradle Module Metadata thể hiện variants phong phú hơn POM. |
| “Một variant được lựa chọn cho compile nghĩa runtime cũng phải dùng nó.” | Mỗi resolvable configuration có nhu cầu và resolution riêng. |

## 20. Quy trình chẩn đoán theo ba lớp

### 20.1. Producer có công bố đúng variant không?

~~~bash
./gradlew :greeter:outgoingVariants
./gradlew :greeter:outgoingVariants --all
~~~

Kiểm tra:

- Tên outgoing variant, attributes, capabilities, artifacts.
- Plugin có tạo đúng feature/test-fixtures variant?
- Target JVM version có thực sự tương thích?
- Có hai consumable variants trùng attributes và capability gây ambiguity?
- Nếu external module, metadata publish đã đúng và repository có **.module**?

### 20.2. Consumer đang đòi những gì?

~~~bash
./gradlew :app:resolvableConfigurations --configuration compileClasspath
./gradlew :app:resolvableConfigurations --configuration runtimeClasspath
~~~

Đối chiếu requested **usage**, **category**, **bundling**, **libraryelements**, **jvm.version** và những custom attributes. Nếu consumer yêu cầu fixture, xem capability đó có tồn tại ở producer.

### 20.3. Gradle đã chọn gì và vì sao?

~~~bash
./gradlew :app:dependencyInsight --configuration compileClasspath --dependency greeter
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency greeter
./gradlew :app:dependencyInsight --configuration testRuntimeClasspath --dependency greeter
~~~

Khi lỗi, thử thêm **--stacktrace** hoặc **--info** cho task cần resolve dependency. Không cần xóa toàn bộ cache ngay khi gặp **No matching variant**: cache không thể tự tạo attributes/capability mà producer chưa công bố.

**Sơ đồ ra quyết định:**

~~~text
Gradle không chọn được dependency variant
          |
          v
Producer có outgoing variant đúng?
          |
       Không ----> Kiểm tra plugin, publish, metadata
          |
         Có
          |
          v
Consumer yêu cầu usage/category/JVM gì?
          |
          v
Có variant compatible?
       Không ----> Sửa target/platform/attributes
          |
         Có
          |
          v
Capability được yêu cầu có được cung cấp?
       Không ----> Thêm feature/fixture hoặc sửa dependency
          |
         Có
          |
          v
Còn nhiều candidates không phân biệt?
         Có ----> Bổ sung attributes/schema/capability hợp lý
          |
         Không
          |
          v
Kiểm tra dependencyInsight và artifact resolution
~~~

## 21. Bài tập củng cố

### Bài 1: So sánh API và runtime

Từ lab, đọc **outgoingVariants** của :greeter và **resolvableConfigurations** của :app. Ghi thành bảng hai cột: consumer yêu cầu **java-api** hay **java-runtime**, và producer có variant nào đáp ứng.

### Bài 2: Phân biệt scope

Trong project :greeter, giả sử có một dependency **api** và một **implementation**. Hãy dự đoán dependency nào cần thấy trên consumer **compileClasspath** và dependency nào cần có khi consumer chạy. Giải thích vì sao tách scopes này giúp giảm coupling.

### Bài 3: Bổ sung test fixtures

Xem đường dẫn **src/testFixtures/java** và dòng **testImplementation(testFixtures(project(':greeter')))**. Vì sao fixture không nên tự có trong **:app:runtimeClasspath**? Khi nào consumer thực sự yêu cầu fixture capability?

### Bài 4: Capability và attribute

Với bảng variants ở mục 8, hãy chỉ ra:

- Main API variant mang capability nào?
- Fixture runtime variant mang capability nào?
- Thuộc tính nào phân biệt API và runtime?
- Vì sao một feature có thể có hai variants?

### Bài 5: Tìm lỗi no matching variant

Cho consumer yêu cầu target Java 17 nhưng producer chỉ có variant yêu cầu Java 21. Nên sửa source/toolchain/publishing hay đổi một metadata attribute bất kỳ? Giải thích rủi ro nếu gắn nhãn Java 17 cho bytecode Java 21.

### Bài 6: Thiết kế feature mới

Nếu thư viện Greeter bổ sung tính năng JSON formatter có dependency ngoài, bạn chọn mở rộng main implementation hay feature variant? Cân nhắc: có bao nhiêu consumer cần JSON, dependency có lớn không, API có độc lập không, metadata có được publish đúng không.

### Câu hỏi tự kiểm tra

1. Variant của một component là gì?
2. Vì sao nhiều variants có thể trỏ tới cùng artifact?
3. **apiElements** và **runtimeElements** phục vụ hai usage nào?
4. **implementation** có phải một outgoing variant không?
5. **compileClasspath** có phải outgoing variant của producer không?
6. Attribute **org.gradle.jvm.version** được dùng để xử lý tình huống nào?
7. Tại sao test fixtures có capability riêng?
8. Có nên thêm test fixtures của library vào production implementation không?
9. Khi external Maven component không có Gradle Module Metadata, điều gì có thể mất?
10. **outgoingVariants** và **dependencyInsight** phục vụ hai góc nhìn nào?
11. **No matching variant** khác **capability conflict** như thế nào?
12. Vì sao không nên tự tạo hai outgoing variants có attributes/capability giống hệt nhau?

**Gợi ý đáp án:** (1) một cách sử dụng component với attributes/dependencies/artifacts/capabilities; (2) khác metadata/usage, không nhất thiết khác file; (3) java-api và java-runtime; (4) không, đó là dependency scope; (5) không, đó là consumer resolvable configuration; (6) JVM target compatibility; (7) cho phép yêu cầu fixture độc lập với main feature; (8) thường không; (9) mất khả năng biểu diễn đầy đủ variants/capabilities/custom attributes; (10) producer cung cấp gì và Gradle đã chọn vì sao; (11) khác nhau giữa không compatible và nhiều provider cùng capability; (12) ambiguity.

## 22. Checklist áp dụng và tài liệu chính thức

Khi review một Gradle build có nhiều modules/libraries, hãy kiểm tra:

- [ ] Project sản xuất thư viện có plugin phù hợp, ví dụ **java-library**.
- [ ] Dependency scopes **api/implementation/runtimeOnly** phản ánh API thực tế.
- [ ] Các outgoing variants có attributes/capabilities đúng và không mâu thuẫn.
- [ ] Consumer dùng **compileClasspath/runtimeClasspath** đúng ngữ nghĩa, không resolve trực tiếp dependency scope.
- [ ] Source/test fixtures được tách, yêu cầu bằng **testFixtures(...)** khi cần.
- [ ] JVM toolchains và published target metadata tương thích với Java thực.
- [ ] Custom feature variant chỉ được tạo khi có nhu cầu và metadata rõ.
- [ ] External dependencies được publish kèm Gradle Module Metadata nếu cần variants nâng cao.
- [ ] Không dùng classifier tùy tiện thay cho feature metadata mà Gradle hỗ trợ.
- [ ] **outgoingVariants**, **resolvableConfigurations**, **dependencyInsight** được dùng trước khi chữa lỗi matching.
- [ ] CI chạy test/build trên đúng JDK/Gradle Wrapper và xác minh dependency graph.

### Tham khảo Gradle

- [Gradle — Variant Selection and Attribute Matching](https://docs.gradle.org/current/userguide/variant_aware_resolution.html)
- [Gradle — Variants and Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html)
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — How to Create Feature Variants for a Library](https://docs.gradle.org/current/userguide/how_to_create_feature_variants_of_a_library.html)
- [Gradle — Testing in Java & JVM Projects: Test Fixtures](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Artifact Resolution](https://docs.gradle.org/current/userguide/artifact_resolution.html)
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — Capabilities](https://docs.gradle.org/current/userguide/component_capabilities.html)
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html)

**Kết luận:** Một **component có nhiều variants** vì các consumer không có cùng nhu cầu: compile cần API, chạy cần runtime dependencies, test có thể cần fixtures, và những môi trường khác có thể cần artifact/capability khác. Gradle không chỉ giải quyết **“lấy thư viện phiên bản nào?”** mà còn **“lấy cách sử dụng nào của thư viện đó?”**. Hiểu rõ producer variants, consumer attributes và capabilities giúp phân giải dependency chính xác, giữ production classpath gọn và chẩn đoán được lỗi khi build phát triển.
