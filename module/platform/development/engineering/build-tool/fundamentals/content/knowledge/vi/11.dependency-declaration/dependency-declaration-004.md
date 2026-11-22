# Phạm vi hoặc cấu hình phụ thuộc theo nhu cầu sử dụng

Khi khai báo dependency trong Gradle, cần chọn configuration phản ánh đúng cách project sử dụng thành phần đó. Một thư viện có thể cần để biên dịch mã nguồn chính, chỉ cần khi chạy ứng dụng, chỉ dùng trong test, hoặc phải xuất hiện trong API công khai của một thư viện khác. Chọn đúng configuration giúp Gradle tạo classpath phù hợp, công bố đúng dependency cho project tiêu thụ và tránh đưa những thư viện không cần thiết vào môi trường runtime.

Trong Gradle, những tên như `implementation`, `api`, `compileOnly` và `runtimeOnly` là **dependency configurations**. Chúng biểu diễn phạm vi sử dụng và cách dependency tham gia vào các classpath hoặc variant. Không nên chọn configuration chỉ theo thói quen; hãy bắt đầu từ câu hỏi: dependency được dùng ở source set nào, cần ở compile time hay runtime, và có phải là một phần của API mà consumer nhìn thấy hay không?

## 1. Configuration quyết định dependency được dùng ở đâu

Ví dụ khai báo cơ bản:

~~~groovy
dependencies {
    implementation 'org.example:core-library:1.0'
    runtimeOnly 'org.example:database-driver:1.0'
    testImplementation 'org.example:test-support:1.0'
}
~~~

Ba dependency trên có mục đích khác nhau:

- `core-library` cần cho mã nguồn chính và runtime của project.
- `database-driver` chỉ cần khi chạy ứng dụng.
- `test-support` chỉ phục vụ việc biên dịch và chạy test.

Gradle dùng configuration để xây dựng dependency graph và các classpath tương ứng. Khi task biên dịch cần compile classpath, Gradle resolve configuration dành cho biên dịch. Khi task chạy ứng dụng hoặc test cần runtime classpath, Gradle resolve configuration dành cho runtime.

Có thể hình dung:

~~~text
dependencies {}
      |
      v
Dependency configurations
      |
      +--------------------------+
      |                          |
      v                          v
compileClasspath           runtimeClasspath
      |                          |
      v                          v
Java compiler              Application / test runtime
~~~

Configuration là một đối tượng trong Gradle model. Nó có thể chứa dependency được khai báo trực tiếp, kế thừa dependency từ configuration khác, có attributes để chọn variant, và có vai trò trong việc cung cấp hoặc tiêu thụ thành phần.

## 2. Bắt đầu từ nhu cầu sử dụng dependency

Trước khi chọn configuration, hãy xác định bốn yếu tố:

1. **Source set nào sử dụng thư viện?** Mã nguồn chính, mã nguồn test hay một source set riêng?
2. **Cần ở giai đoạn nào?** Biên dịch, chạy ứng dụng, chạy test hay xử lý annotation?
3. **Có xuất hiện trong API công khai không?** Consumer của thư viện có cần dependency đó trên compile classpath của họ không?
4. **Ai cung cấp dependency khi runtime?** Project tự đóng gói thư viện, hay môi trường triển khai đã cung cấp nó?

Bảng định hướng:

| Nhu cầu | Configuration thường dùng |
|---|---|
| Mã nguồn chính dùng thư viện khi biên dịch và ứng dụng cần nó khi chạy | `implementation` |
| Thư viện được công khai qua API của một Java library | `api` |
| Chỉ cần thư viện để biên dịch; runtime được cung cấp từ môi trường khác | `compileOnly` |
| Chỉ cần thư viện khi chạy ứng dụng | `runtimeOnly` |
| Chỉ dùng trong mã nguồn test | `testImplementation` |
| Chỉ cần khi biên dịch mã nguồn test | `testCompileOnly` |
| Chỉ cần khi chạy test | `testRuntimeOnly` |
| Công cụ xử lý annotation lúc biên dịch | `annotationProcessor` hoặc `testAnnotationProcessor` |
| Dependency chỉ dùng trong API compile của consumer nhưng không cần ở runtime | `compileOnlyApi` trong Java Library plugin |

Các configuration cụ thể có sẵn phụ thuộc plugin đã áp dụng. Java plugin cung cấp các configuration chính cho ứng dụng Java; Java Library plugin bổ sung các configuration liên quan đến API công khai của thư viện.

## 3. implementation: dependency nội bộ của project

`implementation` là lựa chọn phổ biến cho dependency mà mã nguồn chính cần để biên dịch và ứng dụng cần trên runtime classpath.

Ví dụ:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.example:validation-library:1.0'
}
~~~

Project có thể import class của validation library trong `src/main/java`. Dependency đó xuất hiện trên compile classpath của chính project và runtime classpath của ứng dụng.

Với một ứng dụng Java thông thường, phần lớn thư viện trực tiếp mà mã nguồn ứng dụng sử dụng nên bắt đầu ở `implementation`.

### Vì sao implementation thường là mặc định tốt?

Trong một thư viện được tiêu thụ bởi project khác, `implementation` cho biết dependency phục vụ cách thư viện thực hiện công việc bên trong. Consumer không cần nhìn thấy dependency đó trên compile API của họ chỉ vì thư viện sử dụng nó nội bộ.

Ví dụ, một thư viện có class nội bộ dùng JSON parser để đọc file cấu hình, nhưng các phương thức public chỉ nhận và trả về kiểu do chính thư viện định nghĩa. Consumer không cần import kiểu của JSON parser để gọi API công khai. Dependency JSON parser có thể nằm trong `implementation`.

Cách khai báo này giúp giới hạn compile classpath của consumer và giảm việc vô tình công khai dependency như một phần API.

### implementation không có nghĩa dependency không được dùng lúc chạy

Một nhầm lẫn phổ biến là nghĩ `implementation` chỉ dùng khi compile. Thực tế, dependency `implementation` tham gia compile classpath của project và runtime variant/classpath tương ứng. Nó không được công khai trên compile API của consumer như dependency `api`, nhưng vẫn có thể cần thiết khi consumer chạy thư viện.

Vì vậy, nếu code của project gọi một thư viện trong runtime, không nên chuyển nó sang `compileOnly` chỉ để giảm số dependency tải xuống.

## 4. api: dependency được công khai qua API của thư viện

`api` được cung cấp bởi Java Library plugin. Nó dành cho dependency mà kiểu hoặc thành phần của nó xuất hiện trong API công khai của thư viện và consumer cần dependency đó khi biên dịch mã nguồn sử dụng thư viện.

Áp dụng plugin:

~~~groovy
plugins {
    id 'java-library'
}
~~~

Khai báo dependency API:

~~~groovy
dependencies {
    api 'org.example:public-model:1.0'
    implementation 'org.example:internal-engine:1.0'
}
~~~

Giả sử thư viện cung cấp:

~~~java
package org.example.catalog;

import org.example.model.Product;

public interface CatalogService {
    Product findById(String id);
}
~~~

Nếu `Product` đến từ dependency `public-model`, kiểu này xuất hiện trong chữ ký public của `CatalogService`. Consumer cần biết kiểu `Product` khi biên dịch mã nguồn gọi `findById`. Vì thế, dependency tương ứng nên được khai báo bằng `api`.

Ngược lại, nếu `internal-engine` chỉ được dùng bên trong implementation và không xuất hiện trong chữ ký public, `implementation` phù hợp hơn.

### Những vị trí có thể làm dependency trở thành API

Một dependency thường cần khai báo bằng `api` nếu kiểu của nó xuất hiện trong:

- Kiểu trả về của public/protected method.
- Tham số của public/protected method hoặc constructor.
- Public field hoặc property.
- Superclass hoặc interface mà consumer cần nhìn thấy.
- Generic signature hoặc kiểu lồng nhau trong API công khai.
- Annotation hoặc kiểu public khác mà consumer cần để biên dịch/diễn giải API.

Không cần biến mọi dependency thành `api` chỉ vì nó được import trong một class public. Điều quan trọng là consumer có cần dependency đó để biên dịch và sử dụng API hay không.

### api và implementation trong dependency graph

Với Java Library plugin, dependency `api` được công bố trong API variant của thư viện để consumer có thể dùng khi biên dịch. Dependency `implementation` không được đưa vào compile API của consumer, nhưng vẫn thuộc runtime variant để thư viện hoạt động khi chạy.

~~~text
Java Library
    |
    +-- api: public-model
    |       |
    |       +--> Consumer compile classpath
    |       +--> Runtime variant
    |
    +-- implementation: internal-engine
            |
            +--> Library compile classpath
            +--> Runtime variant
            +--> Không công khai trên consumer compile API
~~~

Nếu một ứng dụng chỉ là consumer cuối cùng, thường không cần áp dụng Java Library plugin chỉ để khai báo `api`. Dùng `implementation` cho dependency trực tiếp của ứng dụng là cách phổ biến.

## 5. compileOnly: chỉ cần trên compile classpath

`compileOnly` dành cho dependency mà source code cần để biên dịch, nhưng dependency đó không được đưa vào runtime classpath thông thường của project.

Ví dụ:

~~~groovy
dependencies {
    compileOnly 'org.example:provided-api:1.0'
}
~~~

Trường hợp sử dụng thường gặp là API được môi trường triển khai cung cấp. Ví dụ, một servlet container có thể cung cấp Servlet API lúc chạy ứng dụng; project cần API đó để biên dịch controller/filter nhưng không muốn đóng gói thêm một bản API vào artifact.

`compileOnly` cũng có thể phù hợp với annotation hoặc API chỉ cần trong quá trình biên dịch, tùy cách công cụ xử lý chúng.

### Điều cần kiểm tra trước khi dùng compileOnly

Câu hỏi quan trọng là: **ai sẽ cung cấp class đó khi ứng dụng chạy?**

Nếu không có thư viện trong runtime classpath hoặc môi trường triển khai, ứng dụng có thể gặp lỗi như `ClassNotFoundException` hoặc `NoClassDefFoundError` khi đường thực thi cần class đó.

Do đó, `compileOnly` chỉ phù hợp khi có một nguồn cung cấp runtime rõ ràng hoặc class đó thực sự không cần ở runtime.

### compileOnly không thay thế annotationProcessor

Một thư viện annotation processor cần được chạy bởi compiler trong quá trình biên dịch. Chỉ khai báo nó bằng `compileOnly` không có nghĩa compiler sẽ tự động thực thi processor. Với Java plugin, cần dùng configuration `annotationProcessor` cho processor của source set chính.

Ví dụ với Lombok:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.0'
    annotationProcessor 'org.projectlombok:lombok:1.0'
}
~~~

Phiên bản minh họa cần được thay bằng phiên bản thực tế tương thích của project. Hai khai báo có hai vai trò: annotation có thể cần trên compile classpath để source code nhận diện; processor được cung cấp cho compiler để thực hiện xử lý annotation.

## 6. runtimeOnly: chỉ cần khi chạy ứng dụng

`runtimeOnly` dành cho dependency không cần để biên dịch mã nguồn, nhưng cần có khi ứng dụng chạy.

Ví dụ điển hình là JDBC driver:

~~~groovy
dependencies {
    runtimeOnly 'org.example:database-driver:1.0'
}
~~~

Mã nguồn có thể chỉ sử dụng JDBC API chuẩn, còn driver được nạp khi runtime theo cấu hình kết nối. Compiler không cần driver để biên dịch mã nguồn sử dụng các interface JDBC chuẩn.

Một số ví dụ khác:

- JDBC driver được chọn qua cấu hình runtime.
- Logging implementation/provider khi API logging được compile riêng.
- Thư viện chỉ được nạp động qua reflection hoặc service loading.
- Module bổ sung chỉ cần trong một chế độ chạy cụ thể.

### runtimeOnly không có trên compile classpath

Nếu mã nguồn trực tiếp import class từ dependency, `runtimeOnly` sẽ không phù hợp vì compiler không nhìn thấy dependency đó trên compile classpath.

Nếu code cần class ở cả compile và runtime, dùng `implementation` hoặc `api` tùy việc dependency có thuộc API công khai của thư viện hay không.

## 7. Các configuration dành cho test

Java plugin tách dependency của mã nguồn test khỏi dependency của mã nguồn chính. Điều này giúp thư viện chỉ dùng trong test không bị đưa vào artifact ứng dụng.

### testImplementation

`testImplementation` dành cho dependency mà test cần khi biên dịch và chạy.

~~~groovy
dependencies {
    testImplementation 'org.example:test-fixtures:1.0'
}
~~~

Ví dụ: JUnit Jupiter API, Mockito hoặc thư viện tạo dữ liệu test. Các dependency này được dùng bởi test source set và thường không thuộc runtime của ứng dụng chính.

Trong Java plugin, `testImplementation` kế thừa dependency từ `implementation`, vì test thường cần dùng cả code chính và dependency mà code chính sử dụng.

### testCompileOnly

`testCompileOnly` dành cho dependency chỉ cần khi biên dịch test. Ví dụ có thể là một annotation hoặc API được môi trường test cung cấp ở runtime.

Nếu test thực sự cần class đó khi chạy, phải đảm bảo runtime có dependency tương ứng qua configuration phù hợp.

### testRuntimeOnly

`testRuntimeOnly` dành cho dependency chỉ cần khi chạy test.

Ví dụ, một test framework có thể cần launcher ở runtime, hoặc test dùng một database driver chỉ trong quá trình thực thi.

~~~groovy
dependencies {
    testRuntimeOnly 'org.example:test-launcher:1.0'
}
~~~

### Test annotation processor

Nếu test source set sử dụng annotation processor riêng, có thể khai báo vào `testAnnotationProcessor`.

Ví dụ tổng quát:

~~~groovy
dependencies {
    testAnnotationProcessor 'org.example:test-processor:1.0'
}
~~~

### Bảng phân biệt dependency test

| Configuration | Biên dịch test | Chạy test | Runtime ứng dụng chính |
|---|---:|---:|---:|
| `testImplementation` | Có | Có | Không |
| `testCompileOnly` | Có | Không theo configuration này | Không |
| `testRuntimeOnly` | Không | Có | Không |
| `testAnnotationProcessor` | Processor được dùng khi compile test | Không phải dependency test runtime | Không |

Các cấu hình test có quan hệ kế thừa với cấu hình chính theo Java plugin. Vì vậy, test thường nhìn thấy các dependency chính cần thiết để compile và chạy test. Điều đó không có nghĩa dependency chỉ dùng trong test sẽ tự động đi vào runtime của ứng dụng.

## 8. annotationProcessor: công cụ chạy trong lúc biên dịch

Annotation processor là công cụ được Java compiler thực thi để đọc annotation và có thể sinh mã nguồn hoặc tài nguyên bổ sung trong quá trình compile.

Java plugin cung cấp configuration `annotationProcessor` cho source set chính. Với test, dùng `testAnnotationProcessor`.

Ví dụ:

~~~groovy
dependencies {
    compileOnly 'org.example:code-annotations:1.0'
    annotationProcessor 'org.example:code-processor:1.0'
}
~~~

Cần phân biệt:

- Thư viện annotation có thể cần để source code biên dịch được.
- Annotation processor là thành phần compiler thực thi.
- Mã nguồn được sinh ra có thể trở thành input cho các task biên dịch tiếp theo.
- Processor không tự động là dependency runtime của ứng dụng.

Không nên đặt processor vào `implementation` chỉ vì nó có liên quan đến compile. Làm vậy có thể đưa công cụ build vào runtime classpath dù ứng dụng không cần nó.

Một số framework gom annotation và processor trong cùng artifact, một số tách thành artifact riêng. Hãy đọc hướng dẫn của thư viện để biết cần khai báo một hay nhiều dependency.

## 9. compileOnlyApi: chỉ công khai cho compile API của consumer

Java Library plugin cung cấp `compileOnlyApi` cho dependency cần có trên compile classpath của chính thư viện và compile API của consumer, nhưng không cần ở runtime variant.

Ví dụ, một thư viện có public API tham chiếu đến một kiểu annotation hoặc kiểu compile-time mà môi trường runtime không cần:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    compileOnlyApi 'org.example:compile-time-contract:1.0'
}
~~~

Configuration này ít dùng hơn `api` và `implementation`. Chỉ chọn nó khi đã xác định dependency phải được nhìn thấy khi consumer biên dịch, đồng thời không phải dependency runtime của thư viện.

Nếu consumer cần dependency đó để chạy, `compileOnlyApi` không đáp ứng yêu cầu runtime. Khi không chắc chắn, hãy kiểm tra chữ ký API, classpath của consumer và metadata publication của library.

## 10. Configuration không chỉ là tên scope

Trong Gradle, configuration là một đối tượng có thể tham gia vào nhiều vai trò. Để hiểu dependency được khai báo ở đâu và được dùng như thế nào, cần phân biệt ba vai trò phổ biến:

| Vai trò | Ý nghĩa | Ví dụ |
|---|---|---|
| Declarable | Nơi khai báo dependency hoặc constraint | `implementation`, `api`, `runtimeOnly` |
| Resolvable | Configuration được resolve thành dependency graph/classpath | `compileClasspath`, `runtimeClasspath` |
| Consumable | Configuration cung cấp variant/artifact cho project khác | `apiElements`, `runtimeElements` |

Các plugin thường tạo các configuration riêng cho từng vai trò. Cách tách này giúp build script khai báo nhu cầu, task resolve classpath và project khác tiêu thụ variant theo mục đích.

### Configuration khai báo dependency

`implementation`, `api` và `runtimeOnly` là các ví dụ về configuration mà người dùng thường khai báo dependency trong khối `dependencies`.

~~~groovy
dependencies {
    implementation 'org.example:core:1.0'
}
~~~

Đây là nơi mô tả project cần dependency nào và dependency đó có vai trò gì.

### Configuration có thể resolve

`compileClasspath` và `runtimeClasspath` là các configuration được Gradle resolve để tạo tập hợp dependency cho một mục đích.

- `compileClasspath` chứa những dependency cần cho compiler của source set.
- `runtimeClasspath` chứa những dependency cần khi chạy source set.

Thông thường, không khai báo dependency trực tiếp vào configuration resolvable như thể nó là bucket khai báo. Hãy khai báo vào configuration đúng mục đích như `implementation` hoặc `runtimeOnly` để các configuration classpath kế thừa và resolve theo mô hình plugin.

### Configuration có thể được consumer sử dụng

Với Java Library plugin, các configuration như `apiElements` và `runtimeElements` đại diện cho variant mà project khác có thể tiêu thụ. Chúng có attributes và artifact phù hợp với mục đích compile hoặc runtime.

Consumer không nhất thiết tải đúng cùng một tập dependency cho mọi mục đích. Gradle có thể chọn variant API khi consumer cần compile classpath và variant runtime khi consumer cần runtime classpath.

## 11. Quan hệ kế thừa giữa các configuration

Configuration có thể kế thừa dependency từ configuration khác thông qua quan hệ `extendsFrom`. Plugin Java thiết lập các quan hệ để test và runtime nhận được những dependency cần thiết.

Mô hình đơn giản:

~~~text
implementation
      |
      +--------------------+
      |                    |
      v                    v
compileClasspath     runtimeClasspath

testImplementation
      |
      +---- inherits implementation dependencies
      |
      v
testCompileClasspath / testRuntimeClasspath
~~~

Đây là sơ đồ khái quát; quan hệ cụ thể có thêm các configuration như `compileOnly`, `runtimeOnly` và những variant khác.

Khi tự tạo configuration, cần hiểu rõ nó có kế thừa dependency nào và được resolve ở đâu. Nếu vô tình kế thừa một configuration quá rộng, task có thể nhận nhiều dependency hơn cần thiết. Nếu không kế thừa đúng, task có thể thiếu thư viện dù dependency đã được khai báo ở nơi khác.

### extendsFrom trong custom configuration

Ví dụ, một công cụ kiểm tra riêng cần dùng chung dependency từ một configuration khác:

~~~groovy
configurations {
    customTool
}

configurations.customTool.extendsFrom(configurations.implementation)
~~~

Đây chỉ là minh họa API kế thừa. Trong thiết kế thực tế, cần cân nhắc có thực sự muốn custom tool nhận toàn bộ dependency ứng dụng hay nên có một configuration riêng chỉ chứa các thư viện của công cụ đó. Không nên dùng kế thừa rộng chỉ để khắc phục lỗi thiếu classpath.

## 12. Dependency scope ảnh hưởng đến consumer như thế nào?

Khác biệt giữa `api` và `implementation` thể hiện rõ khi project là thư viện được project khác sử dụng.

Giả sử có hai project:

~~~text
:catalog-library
       |
       | consumed by
       v
:catalog-app
~~~

`catalog-library` có dependency `public-model` và `internal-engine`.

Nếu `public-model` xuất hiện trong public API, khai báo bằng `api`. Nếu `internal-engine` chỉ được dùng trong implementation, khai báo bằng `implementation`.

Khi `catalog-app` biên dịch:

- Nó cần nhìn thấy `public-model` để biên dịch mã nguồn sử dụng API của catalog library.
- Nó không cần nhìn thấy `internal-engine` trên compile classpath chỉ vì catalog library dùng engine nội bộ.

Khi `catalog-app` chạy, runtime variant của catalog library vẫn phải cung cấp dependency cần thiết để thư viện hoạt động.

Điều này có ý nghĩa với module hóa: API compile của consumer nên chỉ chứa những dependency mà consumer thực sự cần nhìn thấy. Công khai quá nhiều dependency khiến thay đổi implementation của library dễ ảnh hưởng compile graph của các project khác.

### Ví dụ hai project

Library:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:public-model:1.0'
    implementation 'org.example:internal-engine:1.0'
}
~~~

Application:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation project(':catalog-library')
}
~~~

Ứng dụng tiêu thụ library qua project dependency. Gradle dùng metadata và variant của library để xây dựng compile/runtime classpath tương ứng.

Nếu public API của library đổi và loại bỏ dependency `public-model` khỏi chữ ký public, dependency đó có thể được chuyển từ `api` sang `implementation` nếu vẫn cần nội bộ. Đây là thay đổi về contract mà library công bố cho consumer.

## 13. Dependency configuration và variant selection

Một dependency module có thể cung cấp nhiều variant. Ví dụ, cùng một module có variant cho compile và runtime, hoặc variant cho những nền tảng/phiên bản JVM khác nhau.

Gradle sử dụng metadata và attributes để chọn variant phù hợp với configuration đang resolve. Những thuộc tính thường liên quan gồm:

- Usage: thành phần dành cho compile hay runtime.
- Category: library, platform hoặc documentation.
- Library elements: dạng artifact, ví dụ JAR.
- Target JVM version: phiên bản JVM mà variant hướng tới.
- Các attribute do plugin hoặc nền tảng bổ sung.

Do đó, configuration không chỉ quyết định dependency nào được nhìn thấy; nó còn góp phần quyết định **variant nào** của dependency được chọn.

Nếu Gradle báo lỗi không tìm được variant phù hợp, cần xem attributes của consumer configuration và attributes của các variant mà producer cung cấp. Chỉ đổi từ `implementation` sang `runtimeOnly` theo cảm tính có thể che khuất vấn đề thực sự.

## 14. Platform và dependency constraints

Configuration cũng có thể nhận platform/BOM hoặc dependency constraint để quản lý phiên bản thống nhất. Đây là cách quản lý version; nó không thay thế việc chọn scope theo nhu cầu sử dụng.

Ví dụ:

~~~groovy
dependencies {
    implementation platform('org.example:example-bom:1.0')
    implementation 'org.example:module-a'
    implementation 'org.example:module-b'
}
~~~

Platform cung cấp constraints để Gradle chọn phiên bản phù hợp cho các module liên quan. Dependency module vẫn cần được khai báo vào configuration đúng với cách project sử dụng.

Một version catalog như `gradle/libs.versions.toml` có thể đặt tên alias và tập trung version:

~~~toml
[versions]
example = "1.0"

[libraries]
core = { module = "org.example:core", version.ref = "example" }
~~~

Build script có thể dùng alias đó:

~~~groovy
dependencies {
    implementation libs.core
}
~~~

Version catalog giúp quản lý tọa độ/version dễ đọc và nhất quán; configuration `implementation` vẫn quyết định phạm vi sử dụng của dependency. Đổi alias không tự biến dependency từ runtime thành compile-only hoặc API.

## 15. Dependency bên ngoài, project dependency và file dependency

Configuration được chọn dựa trên mục đích sử dụng, bất kể dependency đến từ repository hay project khác. Tuy vậy, nguồn dependency có thể ảnh hưởng metadata và khả năng variant selection.

### External module dependency

Được khai báo bằng tọa độ module:

~~~groovy
dependencies {
    implementation 'org.example:core-library:1.0'
}
~~~

Gradle tìm metadata và artifact trong repository đã cấu hình, sau đó resolve dependency graph.

### Project dependency

Dùng khi một project cần project khác trong cùng build:

~~~groovy
dependencies {
    implementation project(':shared-library')
}
~~~

Gradle có thể sử dụng variant của project được tham chiếu. Với Java Library, consumer nhận API/runtime variant phù hợp thay vì chỉ nhìn vào một file JAR không có metadata.

### File dependency

Dùng khi cần tham chiếu trực tiếp một file:

~~~groovy
dependencies {
    implementation files('libs/vendor-tool.jar')
}
~~~

File dependency thường không mang metadata module đầy đủ như dependency được phân phối qua repository. Gradle không thể suy ra đầy đủ dependency bắc cầu chỉ từ file JAR. Nếu cần quản lý dependency lâu dài, module repository hoặc project dependency thường cung cấp thông tin tốt hơn.

Dù là external module, project hay file dependency, vẫn cần đặt nó vào configuration phù hợp: compile/runtime/test/API.

## 16. Ví dụ tổng hợp cho một Java library

Giả sử project tạo một thư viện Java có public API, dùng JSON parser nội bộ, annotation processor, và test bằng JUnit.

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    // Public API exposes types from this module.
    api 'org.example:public-model:1.0'

    // Used internally by the library implementation.
    implementation 'org.example:json-engine:1.0'

    // Available for compilation, supplied by the runtime environment.
    compileOnly 'org.example:provided-api:1.0'

    // Annotation processor executed by the compiler.
    annotationProcessor 'org.example:code-processor:1.0'

    // Test-only libraries.
    testImplementation 'org.example:test-framework:1.0'
    testRuntimeOnly 'org.example:test-launcher:1.0'
}
~~~

Có thể đọc từng khai báo theo nhu cầu:

| Dependency | Configuration | Lý do |
|---|---|---|
| public-model | `api` | Kiểu của dependency xuất hiện trong public API |
| json-engine | `implementation` | Chỉ dùng bên trong library |
| provided-api | `compileOnly` | Compile cần, runtime do môi trường cung cấp |
| code-processor | `annotationProcessor` | Compiler cần thực thi processor |
| test-framework | `testImplementation` | Test cần compile và runtime |
| test-launcher | `testRuntimeOnly` | Chỉ cần khi chạy test |

Nếu project là application cuối cùng thay vì library, thông thường sẽ không cần `api` cho dependency trực tiếp. Phần lớn dependency của ứng dụng có thể dùng `implementation`, còn driver hoặc provider chỉ cần lúc chạy dùng `runtimeOnly`.

## 17. Cách kiểm tra dependency đã vào đúng configuration chưa

Không nên chỉ nhìn vào khối `dependencies` rồi kết luận classpath đã đúng. Hãy xem report mà Gradle resolve.

### Xem compile classpath

~~~shell
./gradlew :app:dependencies --configuration compileClasspath
~~~

Lệnh này hiển thị dependency graph của compile classpath trong project `app`.

### Xem runtime classpath

~~~shell
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

So sánh hai report giúp nhận biết dependency nào chỉ có khi compile, dependency nào xuất hiện ở runtime và dependency nào được kéo vào bắc cầu.

### Xem vì sao một dependency được chọn

~~~shell
./gradlew :app:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Thay tên dependency và configuration theo project cần điều tra. Report có thể cho biết dependency đến từ nhánh nào, phiên bản nào được chọn và các lý do phân giải liên quan.

### Kiểm tra configuration của test

~~~shell
./gradlew :app:dependencies --configuration testRuntimeClasspath
~~~

Lệnh này giúp xác định thư viện test và dependency chính nào xuất hiện trong runtime classpath của test.

Các report này chỉ phản ánh project và configuration được resolve trong lần chạy. Với project nhiều module, cần chỉ rõ project path; cùng tên configuration có thể tồn tại ở nhiều project với nội dung khác nhau.

## 18. Những lỗi chọn configuration thường gặp

| Lỗi khai báo | Hậu quả có thể gặp | Cách xử lý |
|---|---|---|
| Dùng `compileOnly` cho thư viện cần ở runtime | Thiếu class khi chạy | Chuyển sang `implementation` hoặc bảo đảm môi trường runtime cung cấp |
| Dùng `runtimeOnly` cho class được import trực tiếp | Compiler không tìm thấy class | Dùng `implementation` hoặc `api` theo vai trò |
| Dùng `implementation` cho kiểu xuất hiện trong public API của library | Consumer có thể không compile được khi sử dụng API | Dùng `api` nếu consumer cần dependency đó để compile |
| Dùng `api` cho mọi dependency | Compile API của consumer bị mở rộng không cần thiết | Giữ dependency nội bộ ở `implementation` |
| Khai báo annotation processor bằng compileOnly | Processor không được compiler thực thi đúng cách | Dùng `annotationProcessor` hoặc configuration tương ứng |
| Đưa thư viện test vào `implementation` | Dependency test có thể đi vào runtime sản phẩm | Dùng `testImplementation` |
| Đưa dependency vào configuration resolvable tùy tiện | Cấu trúc dependency không theo vai trò plugin mong đợi | Khai báo vào configuration dành cho dependency |
| Dùng file dependency cho thư viện có nhiều transitive dependencies | Thiếu metadata và dependency bắc cầu | Ưu tiên module repository hoặc project dependency |
| Cho rằng version catalog quyết định scope | Dependency vẫn có thể vào sai classpath | Chọn configuration trong khối dependencies |

## 19. Quy trình chọn configuration theo nhu cầu

Khi thêm một dependency mới, có thể đi theo quy trình:

1. **Xác định source set**: mã nguồn chính, test hay source set riêng?
2. **Xác định compile/runtime**: code có import class trực tiếp không? Runtime có cần thư viện đó không?
3. **Xác định API visibility**: nếu là library, consumer có cần dependency trên compile classpath để dùng public API không?
4. **Xác định ai cung cấp runtime**: project đóng gói thư viện hay container/môi trường triển khai cung cấp?
5. **Xác định loại công cụ**: đây là thư viện runtime, annotation processor hay công cụ chỉ phục vụ build?
6. **Chọn configuration**: implementation, api, compileOnly, runtimeOnly hoặc cấu hình test/processor tương ứng.
7. **Resolve và kiểm tra**: xem compileClasspath, runtimeClasspath hoặc testRuntimeClasspath để xác nhận kết quả.

Có thể dùng bảng quyết định ngắn:

| Câu hỏi | Nếu có | Nếu không |
|---|---|---|
| Mã nguồn chính import hoặc cần dependency để compile? | Xem `implementation`, `api` hoặc `compileOnly` | Xem `runtimeOnly` nếu chỉ cần lúc chạy |
| Dependency cần trong runtime của ứng dụng? | Chọn configuration có runtime participation | `compileOnly` nếu chỉ compile |
| Dependency xuất hiện trong public API của library? | `api` | `implementation` nếu dùng nội bộ |
| Dependency chỉ dùng cho test? | `testImplementation` / `testCompileOnly` / `testRuntimeOnly` | Configuration của source set chính |
| Đây là annotation processor? | `annotationProcessor` hoặc `testAnnotationProcessor` | Configuration theo cách code sử dụng |

Một configuration đúng phải mô tả đúng nhu cầu thực tế của dependency, không chỉ làm cho build hiện tại hết lỗi. Khi chọn đúng, compile classpath của project có đủ kiểu cần thiết, runtime có đúng thư viện cần thiết, consumer chỉ nhìn thấy API dependencies cần công khai, và các thư viện phục vụ test/build không bị đưa nhầm vào sản phẩm.
