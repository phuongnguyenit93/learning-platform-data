# Fat JAR hoặc uber JAR và nguyên tắc gộp thư viện

Một JAR Java thông thường thường chỉ chứa class và resource của chính project. Khi ứng dụng còn phụ thuộc vào các thư viện bên ngoài, JVM cần tìm những thư viện đó qua classpath hoặc module path lúc chạy. **Fat JAR** (còn gọi là **uber JAR**) là cách đóng gói trong đó class và resource của ứng dụng cùng nội dung cần thiết từ các dependency runtime được đưa vào một JAR lớn hơn.

Đóng gói tất cả vào một file giúp phân phối và khởi chạy đơn giản, nhưng việc gộp nhiều JAR đòi hỏi xử lý cẩn thận các class trùng tên, resource, service provider, manifest, chữ ký và metadata đặc biệt. Một JAR tạo ra được chưa chắc đã chạy đúng: nếu chọn nhầm phiên bản thư viện hoặc làm mất metadata khi gộp, ứng dụng có thể lỗi lúc khởi động hoặc chỉ lỗi khi một chức năng cụ thể được gọi.

## 1. JAR thông thường, executable JAR và Fat JAR

Các khái niệm này liên quan nhưng không đồng nghĩa.

### JAR thông thường

JAR là tệp lưu trữ chứa class, resource và metadata của một thư viện hoặc ứng dụng. JAR được tạo bởi Java tool jar hoặc bởi task jar của Gradle.

Với Java plugin, task jar thường đóng gói đầu ra của source set main. Nếu ứng dụng phụ thuộc vào thư viện bên ngoài, các thư viện đó thường không tự động được chép vào JAR thông thường.

Ví dụ:

~~~text
app.jar
├── META-INF/
└── com/example/app/
    └── Main.class
~~~

Nếu Main sử dụng một lớp từ thư viện Gson, JVM vẫn cần tìm JAR Gson khi chạy.

### Executable JAR

Executable JAR là JAR có khai báo lớp khởi chạy trong manifest, thường là thuộc tính Main-Class.

Ví dụ MANIFEST.MF:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main

~~~

Sau đó có thể chạy:

~~~bash
java -jar app.jar
~~~

Executable JAR không nhất thiết là Fat JAR. Nó có thể chỉ chứa lớp ứng dụng và trỏ đến thư viện ngoài qua thuộc tính Class-Path trong manifest hoặc dựa vào một script khởi chạy cung cấp classpath.

### Fat JAR hoặc uber JAR

Fat JAR là JAR đóng gói cả class và resource của ứng dụng lẫn dependency runtime đã được chọn. Với ví dụ trên, nội dung có thể trông như:

~~~text
app-all.jar
├── META-INF/
├── com/example/app/
│   └── Main.class
└── com/google/gson/
    └── Gson.class
~~~

Các thư viện được giải nén và đưa nội dung vào cùng một archive. Thông thường, Fat JAR cũng được cấu hình Main-Class để có thể chạy bằng java -jar.

Tên **fat JAR** và **uber JAR** thường được dùng thay thế nhau. Đây là cách đóng gói theo quy ước, không phải một định dạng file Java riêng.

| Khái niệm | Chứa class ứng dụng | Chứa dependency runtime | Có thể chạy bằng java -jar |
|---|---:|---:|---:|
| JAR thư viện thông thường | Có thể có | Không nhất thiết | Thường không có Main-Class |
| Executable JAR mỏng | Có | Không nhất thiết | Có, nếu manifest và dependency được cung cấp |
| Fat/uber JAR | Có | Có, được gộp vào archive | Thường có |
| Distribution với thư mục lib | Có trong JAR ứng dụng | Có các JAR riêng | Thường chạy qua script |

## 2. Vì sao cần gộp thư viện?

Giả sử ứng dụng dùng một HTTP client, JSON parser và logging implementation. Nếu chỉ phát hành JAR ứng dụng, người triển khai phải nhận thêm các JAR dependency và cấu hình đúng classpath.

Với một ứng dụng nhỏ, điều đó có thể được thực hiện bằng lệnh:

~~~bash
java -cp "app.jar:lib/*" com.example.app.Main
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
java -cp "app.jar;lib/*" com.example.app.Main
~~~

Fat JAR gom nội dung cần thiết vào một file:

~~~bash
java -jar app-all.jar
~~~

Một số lợi ích:

- Phân phối một artifact duy nhất.
- Lệnh khởi chạy đơn giản.
- Giảm nguy cơ quên một dependency khi triển khai.
- Phù hợp với một số môi trường chạy container, job hoặc command-line application.
- Có thể đóng gói cùng phiên bản dependency đã được chọn trong quá trình build.

Tuy nhiên, Fat JAR không tự giải quyết mọi vấn đề dependency. Nếu hai thư viện yêu cầu các phiên bản không tương thích của cùng một module, build vẫn phải chọn phiên bản phù hợp. Nếu resource bị ghi đè hoặc metadata bị mất khi gộp, ứng dụng có thể chạy sai.

## 3. Gradle task jar và runtimeClasspath

Với Java plugin, task jar tạo JAR từ đầu ra ứng dụng. Dependency runtime thường không được gộp vào task này.

Gradle phân biệt các configuration như:

- **implementation:** dependency cần cho compile và runtime của source set chính.
- **runtimeOnly:** dependency chỉ cần khi chạy.
- **compileOnly:** dependency chỉ cần khi biên dịch và không tự động có trong runtime.
- **testImplementation** và **testRuntimeOnly:** dependency dành cho kiểm thử.

Khi tạo Fat JAR, cần đưa đúng dependency runtime vào archive. Công cụ đóng gói thường sử dụng runtimeClasspath làm nguồn dependency, vì nó chứa các artifact cần thiết khi ứng dụng chạy.

Không nên gộp toàn bộ dependency của mọi configuration. Nếu đưa cả test framework, compiler helper hoặc dependency chỉ dùng khi compile vào Fat JAR, file sẽ lớn hơn và có thể chứa thành phần không cần thiết.

Một điểm cần nhớ: Fat JAR chỉ chứa dependency mà Gradle đã phân giải. Nếu dependency bị thiếu trong metadata, bị exclude nhầm hoặc nằm trong một configuration khác, việc gộp không thể tự phát hiện và bổ sung nó.

## 4. Tạo Fat JAR bằng Gradle Shadow plugin

Gradle Java plugin không cung cấp một task Fat JAR tổng quát có thể tự xử lý mọi quy tắc gộp thư viện. Một lựa chọn phổ biến là **Shadow plugin**, plugin hỗ trợ tạo uber JAR, xử lý resource và relocation package.

Plugin hiện được sử dụng với ID com.gradleup.shadow. Hãy chọn và ghim một phiên bản tương thích với Gradle Wrapper và JDK của dự án; phần version bên dưới là chỗ cần thay bằng phiên bản đã chọn.

Ví dụ build.gradle dùng Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'application'
    id 'com.gradleup.shadow' version '<shadow-plugin-version>'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.google.code.gson:gson:2.11.0'
}

application {
    mainClass = 'com.example.app.Main'
}

tasks.named('shadowJar') {
    archiveClassifier = 'all'

    manifest {
        attributes 'Main-Class': application.mainClass.get()
    }

    mergeServiceFiles()
}

tasks.named('build') {
    dependsOn tasks.named('shadowJar')
}
~~~

Ví dụ Kotlin DSL:

~~~kotlin
import com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar

plugins {
    java
    application
    id("com.gradleup.shadow") version "<shadow-plugin-version>"
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.google.code.gson:gson:2.11.0")
}

application {
    mainClass.set("com.example.app.Main")
}

tasks.named<ShadowJar>("shadowJar") {
    archiveClassifier.set("all")

    manifest {
        attributes["Main-Class"] = application.mainClass.get()
    }

    mergeServiceFiles()
}

tasks.named("build") {
    dependsOn("shadowJar")
}
~~~

Trong ví dụ, shadowJar là task tạo Fat JAR. archiveClassifier đặt hậu tố all để phân biệt artifact gộp với JAR thường. Main-Class chỉ định lớp có phương thức main, còn mergeServiceFiles() xử lý các descriptor của Java ServiceLoader.

Sau khi build:

~~~bash
./gradlew clean build
~~~

Có thể nhận được hai artifact, tên cụ thể phụ thuộc cấu hình version và archive naming:

~~~text
build/libs/
├── app-1.0.jar
└── app-1.0-all.jar
~~~

Chạy Fat JAR:

~~~bash
java -jar build/libs/app-1.0-all.jar
~~~

**Lưu ý:** Ví dụ dùng placeholder cho phiên bản plugin để tránh ghim một phiên bản không phù hợp với Gradle Wrapper của dự án. Thay placeholder bằng phiên bản phát hành tương thích trước khi dùng. Các API cấu hình của plugin cũng cần đối chiếu với phiên bản đang ghim.

## 5. Nguyên tắc gộp class và xử lý class trùng tên

Khi giải nén nhiều JAR vào một archive, có thể gặp hai thư viện chứa cùng một đường dẫn class, ví dụ:

~~~text
org/example/Utils.class
~~~

Một JAR chứa phiên bản A, JAR khác chứa phiên bản B. Hai class cùng tên không thể được ghép bytecode thành một class hợp lệ bằng cách nối file.

Cần quyết định class nào sẽ được dùng:

- Chọn một phiên bản dependency tương thích.
- Loại dependency không cần thiết khỏi graph.
- Dùng relocation nếu hai thư viện cần giữ hai namespace riêng và có thể di chuyển an toàn.
- Thay thư viện có xung đột bằng một implementation tương thích.

Không nên giải quyết class trùng tên bằng cách tùy tiện lấy file đầu tiên hoặc file cuối cùng. Kết quả có thể phụ thuộc thứ tự dependency và gây lỗi như NoSuchMethodError, NoClassDefFoundError hoặc hành vi sai ở runtime.

Trước khi đóng gói, có thể kiểm tra graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Nếu cần tìm nguồn của một module:

~~~bash
./gradlew dependencyInsight --dependency gson --configuration runtimeClasspath
~~~

Gradle giải quyết phiên bản dependency trước khi Shadow đóng gói. Fat JAR thường chứa phiên bản đã được chọn trong runtime classpath, không tự giữ nhiều phiên bản của cùng một module để JVM lựa chọn theo từng thư viện cha.

## 6. Xử lý resource trùng nhau

Không chỉ class mới có thể trùng. Nhiều JAR có thể chứa resource cùng đường dẫn, chẳng hạn:

- META-INF/services/...
- META-INF/MANIFEST.MF
- application.properties
- reference.conf
- File cấu hình logging.
- File schema, XML hoặc metadata của framework.

Nếu hai archive có cùng đường dẫn resource, công cụ đóng gói phải quyết định giữ bản nào, bỏ bản nào hay gộp nội dung.

Có ba tình huống phổ biến:

1. **Resource chỉ cần một bản:** chọn bản phù hợp và loại các bản còn lại.
2. **Resource cần kết hợp nội dung:** dùng transformer để nối hoặc hợp nhất theo định dạng.
3. **Resource xung đột về ý nghĩa:** điều tra thư viện sở hữu resource và chọn cấu hình có chủ đích.

Không có một chiến lược chung an toàn cho mọi resource. Ví dụ, nối hai file cấu hình XML không đảm bảo tạo ra XML hợp lệ; giữ một file đầu tiên có thể làm mất khai báo của thư viện khác.

## 7. ServiceLoader và META-INF/services

Java ServiceLoader tìm implementation thông qua các descriptor nằm trong:

~~~text
META-INF/services/<tên-interface>
~~~

Ví dụ một thư viện có file:

~~~text
META-INF/services/com.example.spi.Formatter
~~~

với nội dung:

~~~text
com.example.json.JsonFormatter
~~~

Một thư viện khác có thể cung cấp:

~~~text
com.example.xml.XmlFormatter
~~~

Nếu Fat JAR chỉ giữ một file service descriptor, provider còn lại có thể biến mất. Ứng dụng khi đó không phát hiện được tất cả implementation dù class của provider vẫn có trong archive.

Với Shadow plugin, có thể dùng:

~~~groovy
tasks.named('shadowJar') {
    mergeServiceFiles()
}
~~~

Trong Kotlin DSL, dùng mergeServiceFiles() trong cấu hình task ShadowJar tương ứng.

Transformer này hợp nhất các file service descriptor để giữ danh sách provider. Khi cấu hình chiến lược xử lý duplicate resource, cần bảo đảm các file META-INF/services/** được chuyển qua transformer thay vì bị loại bỏ trước khi gộp. Cú pháp cụ thể phụ thuộc phiên bản Shadow plugin.

Ví dụ một service descriptor sau khi gộp có thể chứa cả hai provider:

~~~text
com.example.json.JsonFormatter
com.example.xml.XmlFormatter
~~~

Hãy kiểm tra nội dung file trong archive sau khi build và chạy một test sử dụng ServiceLoader để xác nhận các provider vẫn được phát hiện.

## 8. Metadata của framework và resource cần transformer riêng

Một số framework dùng resource trong META-INF hoặc file cấu hình để phát hiện plugin, auto-configuration, schema hay extension.

Ví dụ:

- Spring có metadata cho handlers, schemas và auto-configuration.
- Groovy có metadata cho extension modules.
- Một số thư viện cấu hình dùng reference.conf.
- Logging framework có metadata hoặc plugin registry riêng.

Nếu các file này bị ghi đè, ứng dụng có thể khởi động nhưng không phát hiện đủ integration. Vì vậy, cần đọc hướng dẫn đóng gói của framework và cấu hình transformer phù hợp.

Shadow hỗ trợ các transformer cho một số định dạng. Với resource dạng văn bản có thể nối nội dung, có thể dùng cơ chế append cho đúng đường dẫn, ví dụ:

~~~groovy
tasks.named('shadowJar') {
    append('META-INF/spring.handlers')
    append('META-INF/spring.schemas')
}
~~~

Đây chỉ là ví dụ cho resource mà framework quy định có thể nối. Không nên áp dụng append cho mọi file XML, JSON, properties hoặc resource nhị phân. Mỗi loại cần quy tắc gộp đúng định dạng.

Với các framework phiên bản mới, đường dẫn metadata có thể thay đổi. Hãy kiểm tra resource thực tế của dependency và tài liệu tương ứng với phiên bản framework đang dùng.

## 9. Manifest và Main-Class

Manifest của JAR chứa thông tin mô tả archive. Để chạy Fat JAR bằng java -jar, cần có Main-Class hợp lệ:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main

~~~

Nếu thiếu Main-Class, JVM có thể báo:

~~~text
no main manifest attribute, in app-all.jar
~~~

Nếu khai báo sai tên lớp, JVM có thể báo không tìm thấy hoặc không nạp được main class.

Với Fat JAR, dependency đã được gộp vào archive nên thường không cần khai báo Class-Path cho từng thư viện bên ngoài. Main-Class vẫn cần thiết nếu muốn chạy bằng java -jar.

Một số thư viện có manifest riêng với thuộc tính đặc biệt. Không nên sao chép manifest của một dependency làm manifest chính cho toàn bộ ứng dụng. Hãy tạo manifest phù hợp với ứng dụng và giữ lại các thuộc tính thực sự cần thiết.

## 10. Chữ ký số và file trong META-INF

Một JAR có thể được ký số. Chữ ký thường có các file trong META-INF, ví dụ:

~~~text
META-INF/NAME.SF
META-INF/NAME.RSA
META-INF/NAME.DSA
META-INF/NAME.EC
~~~

Khi thay đổi nội dung JAR bằng cách giải nén và gộp class/resource, chữ ký ban đầu không còn xác nhận đúng nội dung mới. Giữ nguyên signature file từ JAR nguồn có thể làm quá trình xác minh chữ ký thất bại.

Nguyên tắc:

- Không mang chữ ký cũ của dependency vào Fat JAR như thể chúng vẫn xác thực archive mới.
- Loại bỏ signature metadata không còn hợp lệ khi đóng gói lại.
- Nếu tổ chức yêu cầu ký artifact phát hành, hãy ký **Fat JAR cuối cùng** sau khi mọi nội dung đã được gộp.
- Lưu giữ bằng chứng build và quy trình ký theo chính sách phát hành.

Có thể dùng exclude pattern trong cấu hình Shadow nếu phù hợp với plugin và chính sách dự án:

~~~groovy
tasks.named('shadowJar') {
    exclude 'META-INF/*.SF'
    exclude 'META-INF/*.DSA'
    exclude 'META-INF/*.RSA'
    exclude 'META-INF/*.EC'
}
~~~

Không nên loại toàn bộ thư mục META-INF một cách mù quáng vì ở đó còn có service descriptor, license, notice và metadata cần thiết khác.

## 11. Relocation: đổi package để tránh xung đột

**Relocation** là kỹ thuật đổi tên package của class khi tạo Fat JAR. Nó thường được gọi là shading.

Ví dụ, một ứng dụng muốn đóng gói phiên bản riêng của thư viện nằm dưới package org.example.legacy. Có thể chuyển package đó sang namespace nội bộ:

~~~groovy
tasks.named('shadowJar') {
    relocate 'org.example.legacy', 'com.example.app.internal.shaded.legacy'
}
~~~

Khi đó class được đóng gói dưới namespace mới, giảm nguy cơ đụng tên với một thư viện khác dùng cùng package.

Relocation có thể hữu ích khi:

- Hai dependency cần các phiên bản không tương thích của cùng một thư viện.
- Một ứng dụng phân phối thư viện nội bộ và muốn tránh xung đột với dependency của ứng dụng khác.
- Một thư viện được nhúng cần namespace riêng để tránh va chạm trên classpath.

Nhưng relocation có rủi ro:

- Reflection tìm class bằng tên chuỗi có thể không được cập nhật.
- File cấu hình, service descriptor hoặc metadata có thể chứa tên class cũ.
- Serialization, tên class lưu trong dữ liệu hoặc cấu hình bên ngoài có thể bị ảnh hưởng.
- Native method và thư viện native có thể phụ thuộc tên class/package.
- Nếu package bị relocation xuất hiện trong public API, consumer có thể không tương thích.
- Chữ ký số của archive nguồn không còn hợp lệ sau khi biến đổi.

Relocation không phải công cụ thay thế cho conflict resolution. Chỉ dùng khi hiểu rõ dependency cần chuyển, các điểm tham chiếu bằng tên và cách kiểm thử sau khi đóng gói.

## 12. Multi-release JAR và tài nguyên đặc biệt

Một số JAR chứa nhiều phiên bản bytecode trong các thư mục:

~~~text
META-INF/versions/9/
META-INF/versions/17/
~~~

Đây là **multi-release JAR**. JVM có thể chọn implementation phù hợp với phiên bản Java đang chạy nếu manifest có thuộc tính:

~~~text
Multi-Release: true
~~~

Khi gộp nội dung của một multi-release JAR vào Fat JAR, cần bảo toàn cấu trúc META-INF/versions/ và manifest attribute phù hợp. Nếu mất thuộc tính Multi-Release: true, JVM có thể không sử dụng các class phiên bản đặc biệt theo cách mong đợi.

Ngoài ra, một số dependency chứa native library hoặc resource theo hệ điều hành/kiến trúc. Gộp tất cả vào một archive không làm chúng trở thành thư viện đa nền tảng tự động. Ứng dụng vẫn cần cơ chế chọn và nạp đúng native artifact cho môi trường chạy.

## 13. Module descriptor và JPMS

JAR modular có thể chứa module-info.class. Một Fat JAR phẳng gộp nhiều JAR vào một archive không thể đơn giản giữ nguyên tất cả module descriptor của các dependency.

Các module nguồn có thể export package, requires module khác và có ranh giới riêng. Khi giải nén tất cả class vào một JAR, ranh giới module đó không còn được thể hiện như trước.

Do đó:

- Fat JAR phẳng thường được sử dụng như một archive trên classpath; khi đó các lớp của nó thuộc unnamed module.
- Nếu đưa Fat JAR lên module path, archive có thể được xem là một module duy nhất nếu có descriptor hợp lệ, hoặc là automatic module nếu không có descriptor phù hợp.
- Không thể gộp nhiều module-info.class thành một module descriptor chung bằng cách nối file.
- Nếu ứng dụng cần JPMS rõ ràng, hãy giữ các module riêng trên module path hoặc thiết kế một module phát hành có descriptor phù hợp.
- Với ứng dụng cần runtime image tùy chỉnh, có thể xem xét jlink thay vì flatten toàn bộ dependency thành một JAR.

Không nên coi một Fat JAR chạy được bằng java -jar là bằng chứng rằng module boundaries của các dependency vẫn được bảo toàn.

## 14. License, NOTICE và nguồn gốc dependency

Mỗi dependency có thể mang license, copyright notice và file NOTICE riêng. Khi gộp JAR, các file cùng tên có thể đụng nhau.

Nếu chỉ giữ một file LICENSE hoặc NOTICE, thông tin của các dependency khác có thể bị mất. Việc loại toàn bộ META-INF có thể làm mất thông tin pháp lý hoặc metadata cần thiết.

Một quy trình phát hành nên:

- Xác định license của dependency trực tiếp và bắc cầu.
- Thu thập license và notice theo chính sách của tổ chức.
- Gộp hoặc lưu các file pháp lý theo cách giữ được nguồn gốc.
- Kiểm tra điều kiện phân phối của từng thư viện.
- Lưu dependency report hoặc SBOM để biết nội dung Fat JAR được tạo từ những artifact nào.

Fat JAR làm artifact dễ phân phối hơn nhưng cũng làm khó nhận biết thư viện nào cung cấp một class cụ thể nếu không có thông tin build đi kèm.

## 15. Xung đột phiên bản và thứ tự dependency

Fat JAR chỉ có một đường dẫn cho một class trong archive. Nếu hai dependency cùng chứa class trùng đường dẫn, không thể giữ cả hai phiên bản nguyên trạng dưới cùng một tên class.

Ví dụ:

~~~text
library-a -> commons-library:1.0
library-b -> commons-library:2.0
~~~

Nếu cả hai phiên bản có class cùng tên, quá trình gộp cần một quyết định rõ ràng. Gradle thường giải quyết conflict phiên bản trong dependency graph trước khi plugin đóng gói. Hãy xem kết quả:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Và truy nguyên một module:

~~~bash
./gradlew dependencyInsight --dependency commons-library --configuration runtimeClasspath
~~~

Nếu thư viện A không tương thích với phiên bản được chọn, việc tạo Fat JAR vẫn có thể thành công nhưng ứng dụng có thể lỗi khi gọi chức năng của A.

Các lựa chọn xử lý:

- Nâng cấp A để hỗ trợ phiên bản chung.
- Hạ hoặc nâng dependency trực tiếp theo một phiên bản tương thích.
- Dùng constraint hoặc platform để thống nhất phiên bản.
- Exclude dependency bắc cầu không cần thiết và khai báo phiên bản thay thế tương thích.
- Relocate một dependency nếu cần giữ song song và có thể xử lý các tham chiếu liên quan.

## 16. Những lựa chọn đóng gói thay cho Fat JAR

Fat JAR không phải lựa chọn duy nhất để phân phối ứng dụng có dependency.

### Application plugin và thư mục lib

Gradle Application plugin có thể tạo một distribution chứa JAR ứng dụng, các dependency riêng trong thư mục lib và script chạy.

Ví dụ:

~~~kotlin
plugins {
    application
}

application {
    mainClass.set("com.example.app.Main")
}
~~~

Tạo distribution:

~~~bash
./gradlew installDist
~~~

Cấu trúc thường có dạng:

~~~text
build/install/app/
├── bin/
│   ├── app
│   └── app.bat
└── lib/
    ├── app.jar
    ├── gson-2.11.0.jar
    └── other-library.jar
~~~

Script do Gradle tạo cấu hình classpath cho các JAR trong lib. Cách này tránh phải gộp resource và class của tất cả dependency vào một archive.

### Spring Boot executable JAR

Executable JAR của Spring Boot thường đóng gói dependency dưới dạng JAR lồng nhau trong archive, chẳng hạn dưới BOOT-INF/lib, cùng lớp ứng dụng dưới BOOT-INF/classes.

Đây là một cách đóng gói executable archive với loader riêng, không phải kiểu uber JAR phẳng trong đó mọi class của dependency đều được giải nén vào cùng một namespace.

Không nên nhầm cấu trúc Spring Boot executable JAR với Fat JAR do Shadow tạo ra. Cả hai đều có thể chạy bằng java -jar, nhưng cơ chế nạp dependency khác nhau.

### Container image

Một ứng dụng có thể được đóng gói trong container image cùng runtime, JAR và cấu hình môi trường. Cách này phù hợp khi hệ thống triển khai đã sử dụng container orchestration. Tuy vậy, container không tự giải quyết dependency conflict hay metadata bị mất trong JAR.

### So sánh

| Phương án | Cách chứa dependency | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|---|
| Fat/uber JAR | Gộp class và resource vào một JAR | Một file dễ phân phối | Cần xử lý trùng class/resource, service metadata, signature |
| Application distribution | Các JAR riêng trong lib | Giữ nguyên ranh giới archive, dễ kiểm tra | Phải phân phối cả thư mục và script |
| Spring Boot executable JAR | JAR dependency lồng nhau | Loader hỗ trợ nested archive | Phụ thuộc cấu trúc và loader của Spring Boot |
| Container image | JAR hoặc distribution bên trong image | Gói cả runtime và môi trường triển khai | Cần quản lý image, cấu hình và bảo mật container |

## 17. Kiểm tra Fat JAR sau khi tạo

Sau khi chạy task đóng gói, hãy kiểm tra artifact thực tế thay vì chỉ dựa vào trạng thái build thành công.

### Liệt kê nội dung

~~~bash
jar tf build/libs/app-1.0-all.jar
~~~

Kiểm tra một số nội dung quan trọng:

- Class của ứng dụng có trong archive.
- Class của dependency cần thiết có trong archive.
- Service descriptor có được hợp nhất.
- Resource cấu hình cần thiết còn tồn tại.
- Signature metadata cũ đã được xử lý.
- License và NOTICE được giữ theo chính sách.
- Manifest có Main-Class đúng.

### Kiểm tra manifest

Có thể giải nén hoặc dùng công cụ archive để đọc:

~~~text
META-INF/MANIFEST.MF
~~~

Xác nhận giá trị Main-Class khớp tên lớp đầy đủ, bao gồm package.

### Chạy thử bằng đúng runtime

~~~bash
java -jar build/libs/app-1.0-all.jar
~~~

Nếu ứng dụng có nhiều chức năng, hãy chạy smoke test cho các đường sử dụng dependency bắc cầu, ServiceLoader, reflection, resource và native library. Một lần khởi động thành công không chứng minh mọi provider hoặc chức năng đều hoạt động.

### Kiểm tra dependency và module

Trước khi đóng gói:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Nếu ứng dụng dùng JPMS, kiểm tra module descriptor của artifact:

~~~bash
jar --describe-module --file build/libs/app-1.0-all.jar
~~~

Kết quả cần được diễn giải theo cách đóng gói thực tế. Fat JAR phẳng thường không bảo toàn module descriptor của tất cả dependency như các module riêng.

## 18. Quy trình xây dựng Fat JAR có kiểm soát

Một quy trình có thể áp dụng trong dự án:

1. Xác định lớp main và các dependency thực sự cần ở runtime.
2. Kiểm tra runtimeClasspath, version conflict và dependency bị exclude.
3. Chọn plugin đóng gói tương thích với Gradle Wrapper và JDK.
4. Cấu hình Main-Class và tên artifact.
5. Xác định chiến lược xử lý duplicate class và resource.
6. Hợp nhất ServiceLoader descriptor và metadata framework bằng transformer thích hợp.
7. Xử lý signature metadata, manifest, multi-release JAR và module descriptor.
8. Giữ lại license, NOTICE và thông tin nguồn gốc dependency.
9. Tạo artifact và kiểm tra nội dung bằng jar tf.
10. Chạy java -jar và smoke/integration test trên artifact đã đóng gói.
11. Quét dependency và artifact cuối cùng theo chính sách bảo mật của dự án.
12. Ký Fat JAR cuối cùng nếu quy trình phát hành yêu cầu.

Nên kiểm thử chính artifact phát hành. Chạy test trên classpath Gradle không hoàn toàn tương đương với chạy Fat JAR, vì quá trình gộp có thể làm thay đổi resource, service metadata, manifest và class resolution.

## 19. Các lỗi thường gặp khi tạo hoặc chạy Fat JAR

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| no main manifest attribute | Manifest không có Main-Class | Cấu hình main class cho archive |
| Could not find or load main class | Sai tên lớp hoặc lớp không có trong archive | Kiểm tra manifest và jar tf |
| NoClassDefFoundError | Dependency runtime chưa được đóng gói hoặc bị exclude | Kiểm tra runtimeClasspath và nội dung JAR |
| NoSuchMethodError | Class của phiên bản dependency không tương thích được chọn khi gộp | Dùng dependencyInsight, thống nhất version và chạy test |
| ServiceLoader không tìm thấy provider | File META-INF/services bị ghi đè hoặc mất | Dùng service file transformer và kiểm tra archive |
| Framework không tìm thấy plugin hoặc auto-configuration | Metadata framework bị ghi đè hoặc chưa được hợp nhất | Cấu hình transformer theo hướng dẫn framework |
| SecurityException: Invalid signature file digest | Signature metadata cũ còn trong archive sau khi nội dung thay đổi | Loại signature cũ và ký lại artifact cuối cùng nếu cần |
| Resource cấu hình bị thiếu | Duplicate strategy giữ nhầm bản hoặc loại file | Xác định quy tắc merge cho từng resource |
| Lỗi liên quan module hoặc split package | Module descriptor hoặc package boundary không phù hợp với archive phẳng | Giữ module riêng trên module path hoặc chọn phương án đóng gói khác |
| Fat JAR chạy được ở máy này nhưng lỗi ở máy khác | Khác JDK, OS, native library hoặc cấu hình môi trường | Kiểm tra runtime target, nền tảng và native dependencies |

## 20. Những nguyên tắc cần nhớ

- JAR thông thường không tự chứa toàn bộ dependency runtime; executable JAR chỉ cần có entry point phù hợp và không nhất thiết là Fat JAR.
- Fat/uber JAR gộp class và resource của ứng dụng cùng dependency runtime vào một archive.
- Gradle Shadow plugin là một lựa chọn phổ biến để tạo Fat JAR; cần ghim phiên bản tương thích với Gradle Wrapper.
- Class trùng tên không thể ghép bytecode tùy ý; phải giải quyết version conflict hoặc dùng relocation có kiểm soát.
- Resource trùng nhau cần quy tắc xử lý theo định dạng; không có một chiến lược duplicate chung phù hợp với mọi file.
- META-INF/services cần được hợp nhất để ServiceLoader phát hiện đầy đủ provider.
- Manifest cần có Main-Class đúng nếu muốn chạy bằng java -jar.
- Chữ ký JAR nguồn không còn xác thực nội dung sau khi gộp; ký artifact cuối cùng nếu cần.
- Giữ metadata framework, multi-release resources, license và NOTICE theo chính sách.
- Fat JAR phẳng không bảo toàn tự động ranh giới JPMS của các dependency.
- Kiểm tra runtimeClasspath, nội dung archive và chạy test trên chính artifact đã tạo.
- Nếu không cần một file duy nhất, Application distribution hoặc container có thể giữ các JAR riêng và giảm độ phức tạp khi gộp.

Fat JAR giúp việc phân phối ứng dụng Java thuận tiện bằng cách gom các dependency runtime vào một archive. Chất lượng của artifact phụ thuộc vào cách giải quyết phiên bản và xử lý các class, resource, service metadata, manifest, chữ ký và thông tin pháp lý. Chọn chiến lược đóng gói dựa trên môi trường triển khai và kiểm thử chính artifact cuối cùng sẽ giúp tránh lỗi chỉ xuất hiện sau khi phát hành.
