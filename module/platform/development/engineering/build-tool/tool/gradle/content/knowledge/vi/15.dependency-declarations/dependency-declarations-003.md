# compileOnly, runtimeOnly và compileOnlyApi theo plugin

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Khai báo dependency

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Phân biệt chính xác **compileOnly**, **runtimeOnly** và **compileOnlyApi** về classpath của module khai báo và classpath của module tiêu thụ.
2. Hiểu rằng **plugin quyết định configuration nào tồn tại**: Java Plugin, Java Library Plugin, Application Plugin, Java Test Fixtures Plugin và các plugin JVM khác không có bộ configuration hoàn toàn giống nhau.
3. So sánh ba configuration với **implementation** và **api**; chọn đúng trường hợp cần thư viện lúc biên dịch nhưng không ở runtime, hoặc ngược lại.
4. Đọc **compileClasspath**, **runtimeClasspath**, **apiElements** và **runtimeElements**, thay vì suy đoán chỉ từ một dòng trong dependencies { ... }.
5. Thực hành dự án **Gradle Groovy DSL + Java 17** gồm nhiều module: một annotation chỉ dùng nội bộ khi compile, một annotation cần cho consumer khi compile, và một runtime provider chỉ được tải khi chạy.
6. Giải thích các lỗi thiếu class khi biên dịch/chạy, sự khác biệt giữa annotation và annotation processor, hậu quả khi dùng sai compileOnlyApi, cùng những hạn chế khi publish metadata.

**Ghi nhớ trước:** Đây là các **dependency configurations**, không phải kiểu dependency và không phải task. Trong cùng một configuration, bạn có thể khai báo external module, project dependency hoặc file dependency; tên configuration cho biết **nó được đưa vào classpath nào**.

## 1. Hai câu hỏi: compile ở đâu, runtime ở đâu?

Khi đọc khai báo dependency, đừng chỉ hỏi “mã này cần thư viện hay không”. Hãy hỏi bốn câu:

- **Module hiện tại cần nó để compile?**
- **Module hiện tại cần nó để chạy?**
- **Một module khác phụ thuộc module này có cần nó để compile?**
- **Một module khác phụ thuộc module này có cần nó để chạy?**

Ví dụ một Java library **lib** được module **app** sử dụng:

~~~text
           lib (producer)                            app (consumer)
     ┌─────────────────────────┐               ┌──────────────────────────┐
     │ compile lib             │               │ compile app against lib  │
     │ runtime lib             │──────────────>│ runtime app with lib     │
     └─────────────────────────┘               └──────────────────────────┘

  compileOnly    -> lib compile only; không đưa vào runtime, không lộ cho app compile
  runtimeOnly    -> lib runtime; được đưa vào app runtime theo runtime variant phù hợp
  compileOnlyApi -> lib compile và app compile; không đưa vào lib/app runtime
~~~

**Phạm vi của bảng và sơ đồ:** Mô hình Java Library Plugin với một dependency project thông thường sử dụng variants chuẩn của Gradle. Khi một plugin tự định nghĩa variant, Android build type, test fixture hoặc publication sang định dạng metadata khác, cần đọc đúng tài liệu plugin đó.

### 1.1. Ma trận cốt lõi với plugin java-library

| Configuration trong lib | lib compileClasspath | lib runtimeClasspath | app compileClasspath khi dùng project(':lib') | app runtimeClasspath |
|---|---|---|---|---|
| **compileOnly** | Có | Không | Không | Không |
| **runtimeOnly** | Không | Có | Không | Có |
| **compileOnlyApi** | Có | Không | Có | Không |
| **implementation** | Có | Có | Thường không | Có |
| **api** | Có | Có | Có | Có |

“Có” nghĩa là dependency thuộc classpath/variant tương ứng theo mô hình chuẩn, không phải chắc chắn mọi class của dependency sẽ được tải vào JVM. Class loading còn phụ thuộc Java code. “Thường không” ở implementation nêu cơ chế API/implementation separation của java-library; với plugin và metadata khác cần kiểm tra variant đã resolve.

Để hiểu nhanh:
- **compileOnly** = chỉ mình **lib** cần dùng để **compile**.
- **compileOnlyApi** = cả **lib và consumer** cần dùng để **compile**, nhưng **runtime không cần**.
- **runtimeOnly** = cần lúc **chạy**, nhưng **mã chính không compile trực tiếp dựa vào type** của dependency ấy.
- **api** = một phần public API cần cả compile và runtime.
- **implementation** = dependency nội bộ cần compile và runtime trong module, nhưng không phơi ra compile classpath của consumer Java Library theo mô hình chuẩn.

### 1.2. Chúng không phải các task

Đúng:

~~~groovy
dependencies {
    compileOnly 'com.example:annotations:1.0'
    runtimeOnly 'com.example:runtime-provider:1.0'
}
~~~

Không đúng về ý nghĩa:

~~~text
./gradlew compileOnly
./gradlew runtimeOnly
~~~

Hai cái tên này là **configuration dùng khai báo dependency**; không tự trở thành task. Khi muốn xem thư viện được Gradle chọn, resolve **compileClasspath** và **runtimeClasspath** của project phù hợp, thay vì giả định bucket declarable luôn resolve trực tiếp được.

## 2. compileOnly: cần khi compile nhưng không tự mang theo khi chạy

### 2.1. Cơ chế

Ví dụ với Java Plugin:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    compileOnly 'com.example:compile-hints:1.0'
}
~~~

Tên thư viện trên **chỉ minh họa cú pháp**, không phải tọa độ đã được kiểm chứng là tồn tại; đừng chạy nguyên ví dụ nếu repository không chứa nó.

Gradle sẽ đưa compile-hints vào **compileClasspath của main source set**, nhưng không đưa nó vào **runtimeClasspath** chuẩn của module và không coi nó là dependency runtime lan truyền tới consumer. Nó phù hợp khi JDK/compiler cần nhìn thấy một type **lúc biên dịch** nhưng không cần giữ type ấy lúc chạy, hoặc runtime sẽ do môi trường riêng cung cấp.

### 2.2. Trường hợp thường dùng

**Annotation chỉ phục vụ biên dịch:** Một thư viện cung cấp annotation có RetentionPolicy.SOURCE hoặc một loại compile-time hint. Java compiler cần type của annotation để biên dịch mã có gắn annotation; chương trình chạy không cần tải lớp annotation nếu nó không được dùng tại runtime.

**API do container cung cấp:** Ví dụ ứng dụng chạy trong servlet container có thể cần type servlet để compile. Một container phù hợp sẽ cung cấp implementation/library lúc chạy. Khi đó compileOnly có thể đúng nếu bạn **biết chắc** runtime environment cung cấp API cần thiết. Nếu chạy như ứng dụng độc lập không có container, compileOnly sẽ gây thiếu class runtime.

**Thư viện được thay thế tại runtime:** Một số dependency được shading hoặc thay bằng dependency khác lúc runtime. Điều này cần hiểu thật rõ dependency graph và binary compatibility; không coi compileOnly là cách tối ưu size tùy tiện.

**Không dùng compileOnly cho thư viện mà code chính vẫn gọi lúc runtime** nếu không có ai cung cấp thư viện ở runtime. Java compile thành công **không bảo đảm** JVM chạy được.

### 2.3. Biểu hiện của một sai lầm

~~~java
package demo;

import demo.optional.OptionalApi;

public final class Runner {
    public static void main(String[] args) {
        System.out.println(OptionalApi.message());
    }
}
~~~

Đây là **mã minh họa**, không thuộc bài lab hoàn chỉnh. Giả sử OptionalApi được cấp chỉ bởi compileOnly, Java compiler có thể compile Runner. Nhưng nếu chạy mà runtimeClasspath không có OptionalApi, JVM có thể ném NoClassDefFoundError khi cố thực thi lời gọi. **compileOnly không làm class tự xuất hiện trong runtime.**

### 2.4. compileOnly khác annotationProcessor

Nhiều người thấy Lombok hoặc một thư viện annotation và suy rằng compileOnly là đủ để sinh mã. Thực tế:

- **compileOnly** cung cấp type/annotation cho compiler thấy.
- **annotationProcessor** cung cấp **annotation processor** cho Java compiler để thực thi xử lý annotation và sinh mã nếu có.
- Một thư viện kiểu Lombok thường cần được khai báo ở **cả compileOnly và annotationProcessor** theo hướng dẫn tương thích của chính thư viện và Gradle/plugin đang dùng.
- Nếu annotation không có processor cần thực thi (như SOURCE-retention marker trong bài lab), **không cần annotationProcessor**.

Ví dụ hình dạng khai báo, không yêu cầu chạy vì phiên bản phải theo hướng dẫn dự án:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.42'
    annotationProcessor 'org.projectlombok:lombok:1.18.42'
}
~~~

Khi kiểm thử code cần annotation hoặc generated classes, cần xét thêm **testCompileOnly** và **testAnnotationProcessor** hoặc cấu hình test framework riêng nếu phù hợp. Không suy rằng compileOnly của main mặc nhiên được đưa vào mọi test source set.

## 3. runtimeOnly: cần lúc chạy nhưng không phải dependency compile chính

### 3.1. Cơ chế

Một module có thể nạp plugin/provider/driver lúc runtime qua **ServiceLoader**, reflection, framework discovery hoặc cấu hình mà Java source không import type implementation.

Ví dụ:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    // Cần ở runtime nhưng không đưa vào compileClasspath của main.
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.13'
}
~~~

Đây là ví dụ minh họa về một implementation/provider runtime, **không phải ứng dụng logging hoàn chỉnh**. Nếu code sử dụng các class của SLF4J API trực tiếp, bạn vẫn cần dependency API thích hợp khi compile; runtimeOnly của binding không thay thế API ở compileClasspath.

**runtimeOnly** có mặt trên **runtimeClasspath**, không có trong **compileClasspath** của main module; khi một Java library được module khác tiêu thụ, runtimeOnly thường được đưa vào runtime variant của consumer, không vào compile variant.

### 3.2. Các trường hợp phù hợp

- **JDBC driver implementation** khi source chỉ dùng java.sql và provider được nạp bằng DriverManager hoặc tên driver ở runtime.
- **Logging implementation/binding** cần lúc chạy trong khi source biên dịch dựa trên logging API riêng.
- **ServiceLoader provider** được cài ở META-INF/services và tiêu thụ qua giao diện SPI được khai báo riêng.
- **Plugin runtime** được framework tìm và tải từ classpath nhưng app không import trực tiếp các class của plugin khi compile.

**Không nên khai báo runtimeOnly rồi import trực tiếp implementation class trong mã Java chính.** Compiler sẽ không thấy class ấy vì nó không có ở compileClasspath, trừ khi một dependency khác vô tình cung cấp trùng type.

### 3.3. Với dự án java-library, runtimeOnly lan truyền thế nào?

Nếu **lib** có:

~~~groovy
dependencies {
    runtimeOnly project(':runtime-provider')
}
~~~

và **app** có:

~~~groovy
dependencies {
    implementation project(':lib')
}
~~~

thì khi **app chạy** với runtime variant của lib, runtime-provider có thể được mang theo trong runtimeClasspath. Nhưng khi **app compile** hoặc **lib compile**, runtime-provider không được cung cấp qua runtimeOnly.

Điều này khiến runtimeOnly rất phù hợp cho dependency được nạp theo tên mà không cần type lúc biên dịch.

## 4. compileOnlyApi: compile-only nhưng thuộc hợp đồng compile của consumer

### 4.1. Vì sao cần thêm chữ Api?

Trong Java library, có những type bắt buộc phải có khi một project khác compile chống lại thư viện, **nhưng type đó không cần ở runtime**.

Ví dụ:
- Annotation công khai có mục đích compile-time, thuộc chữ ký/API biên dịch của library.
- Một type compile-time API sẽ được thay thế hoặc do runtime environment cung cấp.
- Trong dự án Java Module System, dependency chỉ cần compile và cần expose tới module consumer qua yêu cầu tương ứng.

Nếu chỉ dùng **compileOnly**, consumer không nhận dependency ở compileClasspath. Nếu dùng **api**, consumer cũng nhận ở runtime dù thực tế không cần, làm lộ dependency runtime không mong muốn.

**compileOnlyApi** giải quyết đúng trường hợp ở giữa:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    compileOnlyApi project(':public-hints')
}
~~~

Module :lib compile được nhờ :public-hints, và consumer compile chống lại :lib cũng thấy :public-hints. Nhưng khi chạy app, chỉ khai báo compileOnlyApi **không** làm public-hints xuất hiện ở runtimeClasspath.

### 4.2. compileOnlyApi chỉ có khi plugin cung cấp nó

**Điểm quan trọng của đề bài “theo plugin”:** Bạn không thể mặc định mọi Gradle build đều có configuration compileOnlyApi.

- Plugin **java-library** cung cấp compileOnlyApi để mô hình hóa API cần compile nhưng không cần runtime.
- Plugin **java** thông thường cung cấp compileOnly và runtimeOnly, nhưng không nên giả định compileOnlyApi tồn tại nếu không có java-library hoặc plugin khác tạo nó.
- Plugin **application** áp dụng Java model; có compileOnly/runtimeOnly cho mã Java, còn compileOnlyApi không phải nhu cầu mặc định của ứng dụng và không nên dùng như một configuration luôn sẵn có.
- Plugin **java-gradle-plugin** tự áp dụng java-library và dùng compileOnlyApi cho Gradle API theo cách Gradle Plugin Development Plugin định nghĩa. Đây là ví dụ cụ thể về plugin khác **điều chỉnh dependency model**.
- Plugin **java-test-fixtures** tạo họ configuration riêng cho test fixtures, chẳng hạn testFixturesCompileOnly, testFixturesCompileOnlyApi và testFixturesRuntimeOnly. Chúng **không đồng nghĩa** với compileOnlyApi của main source set.
- Android Gradle Plugin, Kotlin Multiplatform, Scala hoặc plugin bên thứ ba có thể có tên/variant khác. Luôn xem **documentation và configuration thực sự do plugin đó tạo**, không tự sao chép tên Gradle Java sang plugin khác.

### 4.3. Bảng theo plugin

| Plugin hoặc môi trường | compileOnly | runtimeOnly | compileOnlyApi | Ghi chú |
|---|---|---|---|---|
| **java** | Có | Có | Không phải cấu hình main mặc định để dựa vào | Dùng cho Java source set; không có API/implementation separation đầy đủ của java-library |
| **application** | Có thông qua Java Plugin | Có thông qua Java Plugin | Không phải cấu hình mặc định dùng cho ứng dụng | app có run và distribution tasks |
| **java-library** | Có | Có | **Có** | api, implementation, compileOnlyApi tương tác với consumer compile/runtime variants |
| **java-gradle-plugin** | Có | Có | **Có** do plugin áp dụng java-library | Gradle API thường được plugin tự thêm vào compileOnlyApi |
| **java-test-fixtures** cùng Java plugin | Họ configuration của main theo plugin Java | Tương tự main | Có **testFixturesCompileOnlyApi** cho fixtures | Test fixtures có ABI/variant riêng |
| **java-platform** | Không dùng cùng mô hình Java compilation thường | Không dùng cùng mô hình Java runtime thường | Không áp dụng như library source plugin | Khai báo constraints/platform theo API của platform |
| **Plugin bên thứ ba / AGP / KMP** | Phụ thuộc plugin/variant | Phụ thuộc plugin/variant | Không suy đoán | Xem config thực tế và plugin docs |

**Không đánh đồng tên giống nhau:** testFixturesCompileOnlyApi mô tả API compile-time của **fixtures**, còn compileOnlyApi mô tả main Java library. Một external plugin cũng có thể tạo configuration cùng tên nhưng semantics riêng; tra theo phiên bản đang dùng.

### 4.4. api, implementation và compileOnlyApi khác nhau ra sao?

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api project(':public-runtime-api')
    implementation project(':internal-runtime-lib')
    compileOnlyApi project(':compile-hints')
    compileOnly project(':private-compile-hints')
    runtimeOnly project(':runtime-provider')
}
~~~

Đây là **sơ đồ khai báo**, các project path chỉ là ví dụ giả định. Không chạy nguyên mẫu trừ khi đã include các project.

- api: được dùng cho compile và runtime của library/consumer.
- implementation: library compile và runtime; consumer thông thường nhận runtime, không nhận compile variant của implementation.
- compileOnlyApi: library compile + consumer compile, không đi runtime.
- compileOnly: library compile nội bộ, không mang sang compile/runtime consumer.
- runtimeOnly: library runtime và consumer runtime, không được dùng để compile library/consumer.

**Không biến mọi compileOnly thành compileOnlyApi.** Việc expose một dependency nội bộ làm compile classpath consumer phình to và tạo coupling không cần thiết. Chỉ dùng compileOnlyApi khi đó thật sự là **compile-time contract** của public API.

## 5. Gradle variants và metadata: vì sao classpath khác nhau?

### 5.1. Ba nhóm configuration quan trọng

Trong Java Library Plugin, Gradle phân biệt:

1. **Declarable/bucket:** nơi viết dependencies { compileOnly ...; runtimeOnly ...; compileOnlyApi ... }.
2. **Resolvable:** cấu hình được yêu cầu giải quyết thành file, ví dụ compileClasspath, runtimeClasspath, testCompileClasspath, testRuntimeClasspath.
3. **Consumable/outgoing:** những variant project khác có thể yêu cầu, ví dụ apiElements, runtimeElements.

Hình dung:

~~~text
  Module lib:
      compileOnly ------------------+
      compileOnlyApi ---------------+----> lib compileClasspath
      api --------------------------+
      implementation ---------------+

      api + implementation + runtimeOnly ---> lib runtimeClasspath

      api + compileOnlyApi -----------------> apiElements
      api + implementation + runtimeOnly ---> runtimeElements

  Module app:
      compileClasspath ----> chọn lib apiElements
      runtimeClasspath ----> chọn lib runtimeElements
~~~

Đây là sơ đồ **khái niệm**, lược bỏ artifacts/attributes, test configurations và các quan hệ extendsFrom khác. Mục tiêu là hiểu rằng compileOnlyApi đi vào **apiElements** còn runtimeOnly đi vào **runtimeElements**. Các plugin có thể thêm variant và điều kiện riêng.

### 5.2. Không resolve trực tiếp bucket nếu nó không resolvable

Lệnh phù hợp:

~~~bash
./gradlew :lib:dependencies --configuration compileClasspath
./gradlew :lib:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Có thể xem outgoing variants:

~~~bash
./gradlew :lib:outgoingVariants
~~~

Trong bản Gradle hỗ trợ task và với plugin phù hợp, báo cáo có thể hiển thị apiElements/runtimeElements và thông tin capability/attribute/artifact. Output chính xác thay đổi theo phiên bản, không cần so khớp nguyên văn mọi dòng.

Cẩn thận: Gradle có nhiều cấu hình chỉ để khai báo, không cho resolve trực tiếp. Khi chạy dependencies --configuration compileOnly, một phiên bản Gradle có thể chỉ báo những dependency **đã khai báo** hoặc nêu không thể resolve tùy API và nhiệm vụ. Để biết **classpath Java thực sự**, nhìn compileClasspath hoặc runtimeClasspath.

### 5.3. Publish library và metadata

Nếu bạn publish java-library bằng maven-publish:

- Gradle module metadata có thể biểu đạt **compile/runtime variants** chi tiết hơn, gồm sự khác biệt giữa compileOnlyApi và runtimeOnly.
- Maven POM có mô hình scope kém chi tiết hơn Gradle Module Metadata. Không mặc định rằng mọi consumer Maven/Groovy/Kotlin/IDE đều tái tạo **chính xác** các đặc tính compileOnlyApi như Gradle project dependency.
- Nếu API library public có type chỉ compile-only, phải xác minh artifact **đã publish** trong môi trường consumer thực tế: Gradle module metadata, POM, dependency graph và những class mà compiler/JVM cần.
- compileOnly/compileOnlyApi **không** tự quyết định việc đóng gói các class vào JAR, và không bảo đảm shaded/relocated code; build cần cơ chế packaging riêng khi dùng shading.

Nhất là thư viện công khai cho người dùng không kiểm soát, tránh thiết kế public API phụ thuộc class chỉ có compile-time mà runtime lại thiếu nếu class có thể bị JVM cần nạp. Một annotation có **RetentionPolicy.SOURCE** trong bài lab giúp minh họa compile-time-only một cách an toàn.

## 6. Dự án thực hành Java 17 — kiểm chứng cả ba configuration

Bài lab được thiết kế **không cần thư viện ngoài**. Nó tạo năm subprojects trong một build để tách trách nhiệm:

- **:public-hints** tạo một annotation public dùng lúc compile, không tồn tại trong runtime annotation metadata.
- **:internal-hints** tạo một annotation chỉ dùng trong code nội bộ của library khi compile.
- **:runtime-provider** tạo một class chứa thông điệp được library nạp bằng reflection lúc chạy.
- **:lib** áp dụng java-library, dùng cả compileOnlyApi, compileOnly và runtimeOnly.
- **:app** áp dụng application, phụ thuộc project(':lib') và kiểm tra cả classpath compile lẫn runtime.

Cách chia nhiều module là **có chủ đích để nhìn thấy phạm vi**, không phải khuyến nghị mọi dự án thật cần năm module chỉ để viết hai annotation.

### 6.1. Yêu cầu và cấu trúc thư mục

Cần **JDK 17**, Gradle phiên bản tương thích hoặc Wrapper của dự án. Nếu chưa có Wrapper, có thể dùng một bản Gradle đã cài chạy gradle wrapper, sau đó dùng ./gradlew và commit các file Wrapper cần thiết.

~~~text
gradle-scopes-lab/
├── settings.gradle
├── gradlew                     # được tạo bằng Gradle Wrapper
├── gradlew.bat
├── gradle/wrapper/...
├── public-hints/
│   ├── build.gradle
│   └── src/main/java/demo/hints/PublicHint.java
├── internal-hints/
│   ├── build.gradle
│   └── src/main/java/demo/internal/InternalHint.java
├── runtime-provider/
│   ├── build.gradle
│   └── src/main/java/demo/runtime/RuntimeBanner.java
├── lib/
│   ├── build.gradle
│   └── src/main/java/demo/lib/Facade.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/Main.java
~~~

**settings.gradle:**

~~~groovy
rootProject.name = 'gradle-scopes-lab'

include(
    'public-hints',
    'internal-hints',
    'runtime-provider',
    'lib',
    'app'
)
~~~

Không cần repositories { mavenCentral() } trong bài lab vì các dependency đều là **project dependencies** đến module trong cùng build. Lần đầu chạy Gradle Wrapper vẫn có thể cần mạng để tải Gradle distribution, nhưng bản lab không yêu cầu tải external libraries.

### 6.2. Module public-hints: type thuộc API biên dịch

**public-hints/build.gradle:**

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**public-hints/src/main/java/demo/hints/PublicHint.java:**

~~~java
package demo.hints;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface PublicHint {
}
~~~

Annotation này tồn tại **khi compile**. Với RetentionPolicy.SOURCE, nó không được giữ trong .class, nên ứng dụng không cần class annotation khi chạy chỉ vì đã gắn @PublicHint trong source.

### 6.3. Module internal-hints: annotation nội bộ

**internal-hints/build.gradle:**

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**internal-hints/src/main/java/demo/internal/InternalHint.java:**

~~~java
package demo.internal;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.METHOD)
public @interface InternalHint {
}
~~~

Library chỉ sử dụng @InternalHint trên một private method. Người tiêu thụ library không cần annotation này trên compile classpath vì nó **không nằm trong hợp đồng public mà consumer phải biên dịch dựa vào**.

### 6.4. Module runtime-provider: chỉ cần lúc chạy

**runtime-provider/build.gradle:**

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**runtime-provider/src/main/java/demo/runtime/RuntimeBanner.java:**

~~~java
package demo.runtime;

public final class RuntimeBanner {
    private RuntimeBanner() {
    }

    public static String message() {
        return "active";
    }
}
~~~

Class RuntimeBanner được nạp theo tên bằng reflection trong library để cho thấy một **runtimeOnly** module có thể được dùng mà code lib không import type của module đó khi compile.

Reflection ở đây chỉ để minh họa classpath. Dự án production nên cân nhắc **ServiceLoader + SPI**, dependency injection hoặc extension point của framework phù hợp; không biến reflection với hardcoded class names thành kiến trúc mặc định.

### 6.5. Module lib: cấu hình ba phạm vi

**lib/build.gradle:**

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    compileOnlyApi project(':public-hints')
    compileOnly project(':internal-hints')
    runtimeOnly project(':runtime-provider')
}
~~~

Đọc từng dòng:

1. compileOnlyApi public-hints → lib compile được @PublicHint; **app cũng nhận annotation ở compileClasspath** vì app biên dịch chống lại API của lib.
2. compileOnly internal-hints → lib compile được @InternalHint; **app không được tự cấp** annotation nội bộ qua compile variant.
3. runtimeOnly runtime-provider → lib và app runtime có RuntimeBanner; **lib/app compileClasspath không chứa nó** chỉ do khai báo runtimeOnly.

**lib/src/main/java/demo/lib/Facade.java:**

~~~java
package demo.lib;

import demo.hints.PublicHint;
import demo.internal.InternalHint;

@PublicHint
public final class Facade {
    private Facade() {
    }

    @InternalHint
    private static String prefix() {
        return "status=";
    }

    public static String display() {
        try {
            Class<?> backend =
                    Class.forName("demo.runtime.RuntimeBanner");
            Object value = backend.getMethod("message").invoke(null);
            return prefix() + value;
        } catch (ReflectiveOperationException ex) {
            throw new IllegalStateException(
                    "Runtime provider is missing or invalid", ex
            );
        }
    }
}
~~~

**Cơ chế cụ thể:**

- Import PublicHint và InternalHint khiến compiler của lib phải nhìn thấy cả hai module khi **compile**.
- Hai annotation dùng SOURCE retention; code chạy không cần nạp type annotation.
- Facade **không import** demo.runtime.RuntimeBanner. Nó tra tên class tại runtime bằng Class.forName và gọi method tĩnh message.
- Nếu thiếu :runtime-provider trong runtimeClasspath, reflection tạo ClassNotFoundException, được gói thành IllegalStateException rõ nghĩa.
- Đây là ví dụ cố ý sử dụng runtime-only discovery; nếu code thay bằng lời gọi trực tiếp RuntimeBanner.message() trong lib, compiler sẽ không thấy type từ runtimeOnly và báo lỗi. Khi code cần type lúc compile, phải chọn một configuration cấp type vào compileClasspath.

### 6.6. Module app: consumer compile API và chạy runtime provider

**app/build.gradle:**

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation project(':lib')
}
~~~

**app/src/main/java/demo/app/Main.java:**

~~~java
package demo.app;

import demo.hints.PublicHint;
import demo.lib.Facade;

@PublicHint
public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("annotation=compile-only API");
        System.out.println(Facade.display());
    }
}
~~~

**Điểm chứng minh:**

- App **không** khai báo trực tiếp project(':public-hints') mà vẫn **compile được import PublicHint**, do compileOnlyApi trong lib cung cấp annotation cho consumer compile.
- App không import InternalHint hoặc RuntimeBanner; chúng không thuộc compile API được expose.
- App chạy Facade.display(), khi ấy **runtimeClasspath** có :runtime-provider qua runtimeOnly của lib.
- @PublicHint có SOURCE retention, nên app runtime không cần mang theo public-hints.

**Lưu ý thiết kế ứng dụng thật:** Ví dụ cố ý cho app sử dụng annotation transitive để chứng minh compileOnlyApi. Nếu app chủ động dùng type của public-hints cho logic riêng (không chỉ là API contract của lib), nên khai báo dependency trực tiếp để tránh accidental coupling vào dependency transitive.

### 6.7. Chạy lần đầu và kiểm tra stdout

Linux/macOS:

~~~bash
./gradlew :app:run --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:run --quiet
~~~

Nếu chưa có Wrapper, tạo Wrapper bằng Gradle đã cài hoặc tạm dùng gradle :app:run --quiet trong môi trường phù hợp. Với tất cả file đúng path, JDK 17/toolchain sẵn có và bản Gradle tương thích, **đầu ra của Main.main** là:

~~~text
annotation=compile-only API
status=active
~~~

Giải thích theo đường đi:

1. App được compile với PublicHint nhờ :lib compileOnlyApi.
2. JVM chạy App không cần PublicHint vì annotation đã bị loại khỏi .class.
3. App gọi Facade.display().
4. Facade tìm demo.runtime.RuntimeBanner ở **runtimeClasspath**, do :lib runtimeOnly kéo vào.
5. Method message() trả "active"; prefix() trả "status=", nên dòng thứ hai là "status=active".

Đây là stdout do Java app in ra, không bao gồm log Gradle/daemon hoặc thông tin máy. Không đặt một thứ tự task tùy tiện làm expected log vì Gradle quyết định theo task graph.

### 6.8. Xem compileClasspath và runtimeClasspath của từng project

Chạy:

~~~bash
./gradlew :lib:dependencies --configuration compileClasspath
./gradlew :lib:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Kỳ vọng **theo ý nghĩa cấu hình**, không cần đối chiếu y hệt cách Gradle in cây:

| Classpath được resolve | :public-hints | :internal-hints | :runtime-provider | :lib |
|---|---|---|---|---|
| **:lib:compileClasspath** | Có | Có | Không | Bản thân lib, không là project dependency vào chính mình |
| **:lib:runtimeClasspath** | Không | Không | Có | Output của lib do Java plugin kết hợp khi chạy |
| **:app:compileClasspath** | Có | Không | Không | Có |
| **:app:runtimeClasspath** | Không | Không | Có | Có |

Hàng :lib:runtimeClasspath nói về **external/project dependencies trong configuration**, không có nghĩa Gradle luôn in chính output classes của lib như một nhánh phụ thuộc tới chính nó. Table chỉ mô tả nguồn và nơi sử dụng.

**Không chạy dependencies --configuration compileOnly rồi kết luận** rằng đó là compile classpath đầy đủ. Hãy chọn compileClasspath/runtimeClasspath khi điều tra compiler/JVM.

### 6.9. Thử làm hỏng cấu hình có kiểm soát để tự chứng minh

Thử từng tình huống một trong bản copy của bài lab; khôi phục lại trước khi thử tiếp.

**Thí nghiệm A — đổi compileOnlyApi thành compileOnly trong lib:**

~~~groovy
dependencies {
    compileOnly project(':public-hints')
    compileOnly project(':internal-hints')
    runtimeOnly project(':runtime-provider')
}
~~~

- :lib:compileJava vẫn có đủ hai annotation nên có thể thành công.
- :app:compileJava **không còn nhận PublicHint** từ compile variant của lib, vì app chỉ khai báo dependency project(':lib').
- App.java vẫn import demo.hints.PublicHint và annotate @PublicHint → compiler báo package/type không tìm thấy.
- Khôi phục compileOnlyApi để app compile lại. Đây là bằng chứng rõ nhất cho sự khác biệt compileOnlyApi vs compileOnly.

**Thí nghiệm B — bỏ runtimeOnly provider:**

~~~groovy
dependencies {
    compileOnlyApi project(':public-hints')
    compileOnly project(':internal-hints')
}
~~~

- :lib:compileJava và :app:compileJava vẫn có thể thành công.
- Khi :app:run gọi Facade.display(), Class.forName không tìm được RuntimeBanner.
- Kết quả là Java exception có nguyên nhân ClassNotFoundException; **đó là thiếu dependency ở runtime**, không phải compile error.
- Khôi phục runtimeOnly project(':runtime-provider') để chương trình in status=active.

**Thí nghiệm C — đổi runtimeOnly thành compileOnly:**

~~~groovy
dependencies {
    compileOnlyApi project(':public-hints')
    compileOnly project(':internal-hints')
    compileOnly project(':runtime-provider')
}
~~~

- :lib compileClasspath có thêm RuntimeBanner, nhưng code không cần type này khi compile.
- :app runtimeClasspath lại **thiếu runtime provider**, nên chương trình lỗi khi reflection.
- Chỉ đổi tên configuration mà không xét nhu cầu classpath có thể khiến build compile thành công nhưng runtime hỏng.

**Thí nghiệm D — chuyển runtimeOnly thành implementation:**

~~~groovy
dependencies {
    compileOnlyApi project(':public-hints')
    compileOnly project(':internal-hints')
    implementation project(':runtime-provider')
}
~~~

- Library compileClasspath nay chứa runtime-provider dù code chỉ nạp qua reflection.
- :app runtimeClasspath vẫn có runtime-provider qua implementation của lib.
- Chương trình có thể tiếp tục chạy, nhưng compile classpath của lib **rộng hơn cần thiết**. Dùng runtimeOnly sẽ diễn đạt ý định tốt hơn.

### 6.10. Nếu dự án dùng external module thì sao?

Cả ba configuration không bắt buộc dùng project dependency. Sau khi khai báo repository, có thể dùng module notation:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    compileOnly 'com.example:compile-hints:1.0'
    runtimeOnly 'com.example:runtime-provider:1.0'
}
~~~

Đây chỉ là ví dụ **cú pháp**, những tọa độ com.example không được bảo đảm tồn tại. Với library:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    compileOnlyApi project(':public-hints')
}
~~~

Đó là dạng chạy được trong lab vì subproject đã include. Cơ chế compile vs runtime được quyết định bởi **configuration**, không phải dependency là external module hay project.

## 7. Những tình huống chọn configuration theo nhu cầu

### 7.1. Thư viện annotation compile-time nội bộ

Nếu lib dùng một annotation chỉ để linter/compiler phân tích trong private implementation và consumer không cần biết nó:

~~~groovy
dependencies {
    compileOnly project(':internal-hints')
}
~~~

Cần compile, không cần runtime, không export → compileOnly.

### 7.2. Annotation trong API compile-time của Java library

Nếu library công khai một annotation chỉ phục vụ compiler, và consumer cần biết annotation đó khi compile chống lại library:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    compileOnlyApi project(':public-hints')
}
~~~

Cần library compile + consumer compile, không cần runtime → compileOnlyApi. Chỉ dùng khi type thực sự không cần lúc chạy.

### 7.3. JDBC driver / logging binding chỉ được tìm ở runtime

Ví dụ ý tưởng:

~~~groovy
dependencies {
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.13'
}
~~~

Nếu source dùng SLF4J API trực tiếp, nó cũng phải có slf4j-api trên compile classpath thông qua dependency phù hợp. Runtime binding chỉ là phần implementation được phát hiện lúc chạy.

### 7.4. API được runtime environment cung cấp

Nếu compile against một Servlet API do container cung cấp, compileOnly có thể phù hợp. Nhưng nếu public API của một Java library expose các servlet types và consumer phải compile dựa trên chúng, có thể cần compileOnlyApi để consumer thấy type. Cần **xác nhận container thực sự cung cấp đúng binary version lúc chạy**, đặc biệt khi library được dùng bên ngoài container.

### 7.5. Một library cần dependency cả compile lẫn runtime

Nếu code gọi trực tiếp class lúc compile và vẫn cần class đó khi thực thi, implementation hoặc api mới là lựa chọn đúng tùy type có nằm trong public API hay không. Không tự chia mọi thư viện thành một cặp compileOnly + runtimeOnly; cách đó dễ mất nhất quán version và tạo quan hệ metadata không cần thiết.

### 7.6. Một project application nhưng muốn dùng compileOnlyApi

Nếu app chỉ được build thành executable và không publish API cho consumer Java, compileOnlyApi thường **không có vai trò phù hợp**. Khi app thực sự cũng là một library được module khác compile chống lại, hãy thiết kế module thư viện riêng với java-library và đưa API dependency vào đúng module, không ép mọi app plugin phải có compileOnlyApi.

## 8. Test source set và test fixtures: các scope khác tên

### 8.1. Main khác test

Các configuration dành cho **main** không đồng nghĩa với configuration dành cho **test**:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    compileOnly 'com.example:main-hint:1.0'
    runtimeOnly 'com.example:runtime-provider:1.0'

    testCompileOnly 'com.example:test-hint:1.0'
    testRuntimeOnly 'com.example:test-runtime-provider:1.0'
}
~~~

Các tọa độ trong đoạn này minh họa cú pháp, không được xác nhận tồn tại. Nếu test code trực tiếp import annotation type, hãy cấu hình nó trong testCompileOnly hoặc testImplementation theo nhu cầu. Nếu test cần provider runtime, hãy khai báo testRuntimeOnly khi phù hợp.

**Không mặc định** test source set luôn nhìn thấy mọi dependency compileOnly của main như một phần public API. Kiểm tra testCompileClasspath/testRuntimeClasspath thực tế. Test fixtures cũng có classpath/variant độc lập và có thể được xuất bản cho consumer khác.

### 8.2. Plugin java-test-fixtures

Ví dụ:

~~~groovy
plugins {
    id 'java-library'
    id 'java-test-fixtures'
}

dependencies {
    testFixturesCompileOnlyApi project(':fixture-public-hints')
    testFixturesCompileOnly project(':fixture-internal-hints')
    testFixturesRuntimeOnly project(':fixture-runtime-provider')
}
~~~

Các project paths trong đoạn này là **giả định**, không thuộc bài lab chạy được.

- **testFixturesCompileOnlyApi** cung cấp type compile-only cho test fixtures và consumer compile chống lại fixtures.
- **testFixturesCompileOnly** chỉ phục vụ compile implementation của fixtures.
- **testFixturesRuntimeOnly** bổ sung dependency cần lúc chạy fixtures.
- Consumer nhận test fixtures qua notation như testImplementation(testFixtures(project(':lib'))) theo plugin Java Test Fixtures; khi đó Gradle chọn đúng fixtures variant, không phải mặc định main API variant.

### 8.3. Java Gradle Plugin Development Plugin

Khi viết plugin Gradle bằng java-gradle-plugin, Gradle tự áp dụng java-library và thường bổ sung gradleApi() vào compileOnlyApi. Ý nghĩa là plugin implementation cần biên dịch chống lại Gradle API, và consumer plugin có ngữ cảnh API tương ứng; Gradle runtime cung cấp Gradle API. **Không xóa/sửa ngẫu nhiên cấu hình đó** chỉ vì thấy một dependency "compileOnlyApi" không được đóng gói vào JAR.

## 9. Quan hệ với Java Module System (JPMS)

Trong Java 9+, module-info.java có các directive biểu thị dependency lúc compile và runtime. Gradle Java Library documentation chỉ ra ánh xạ khái niệm:

| Java module directive | Gradle configuration |
|---|---|
| requires some.module | implementation |
| requires transitive some.module | api |
| requires static some.module | compileOnly |
| requires static transitive some.module | compileOnlyApi |

Ví dụ **minh họa JPMS**, không phải cấu trúc của bài lab classpath ở mục 6:

~~~java
module com.example.library {
    requires static transitive com.example.annotations;
}
~~~

Cần module thực sự có tên module hợp lệ và Gradle dependency configuration tương ứng. Không chỉ viết module-info.java mà quên dependency trong build.gradle; Gradle hiện không tự bảo đảm hai nơi luôn đồng bộ.

**Cẩn thận:** JPMS có quy tắc module resolution/class loading riêng. Cấu hình Gradle chỉ quyết định classpath/module path theo model; việc một type có thể bị JVM nạp khi runtime hay không vẫn phụ thuộc Java bytecode, module descriptors và code thực tế.

## 10. Kiểm tra và chẩn đoán đúng chỗ

### 10.1. Lệnh dùng thường xuyên

~~~bash
./gradlew :lib:dependencies --configuration compileClasspath
./gradlew :lib:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:compileJava --info
./gradlew :app:run --stacktrace
~~~

- Dùng **dependencies** để xem dependency graph đã resolve của một configuration.
- Dùng **--info** khi cần biết Gradle chọn task/cache/classpath thế nào.
- Dùng **--stacktrace** để xem nguyên nhân lỗi build; nếu lỗi ứng dụng, đọc exception của JVM và root cause như ClassNotFoundException.
- Khi external module xuất hiện nhiều version, dùng dependencyInsight trên đúng **resolvable configuration**.
- Với dependency project, dùng ./gradlew projects để biết tên/path nào được settings.gradle include.

### 10.2. Compile thành công không chứng minh runtime thành công

Một custom Java main có thể compile khi mọi type mà compiler cần đã có, nhưng chạy lỗi vì một thư viện chỉ nằm trong compileOnly. Gradle không tự "chuyển" compileOnly sang runtime để chữa lỗi.

Ngược lại, runtimeOnly có thể đủ cho ServiceLoader/reflection, nhưng sẽ không giúp một source file đang import trực tiếp class implementation compile thành công.

Với compileOnlyApi, cần kiểm tra **consumer compileClasspath**: nếu nó thiếu type public annotation/API, vấn đề nằm ở plugin/library API variant hoặc dependency declaration, không phải runtimeOnly.

### 10.3. Runtime được cung cấp bên ngoài Gradle

Một container, application server hoặc một launcher khác có thể cung cấp những class mà Gradle runtimeClasspath không liệt kê. Đó là cấu hình môi trường, không phải bảo đảm của compileOnlyApi. Hãy tài liệu hóa runtime contract và kiểm chứng thật trên môi trường đích, tránh “chạy được trên máy tôi” vì classpath ngẫu nhiên có thêm JAR.

## 11. Những lỗi thường gặp và hướng sửa

### Lỗi 1 — Could not find method compileOnlyApi() ...

**Khả năng cao:** Project chỉ dùng plugin java/application mà chưa áp dụng java-library, hoặc một plugin khác không định nghĩa configuration đó.

**Cách sửa:** Xác minh plugin đang áp dụng tại đúng project. Nếu đây là library public, áp dụng java-library để dùng compileOnlyApi. Nếu chỉ là ứng dụng, xem compileOnly có đáp ứng nhu cầu không. Không tự tạo configuration cùng tên và nghĩ semantics của java-library sẽ tự xuất hiện.

### Lỗi 2 — ClassNotFoundException sau khi dùng compileOnly

**Nguyên nhân:** Class thực sự cần runtime nhưng bạn chỉ cấp nó khi compile.

**Cách sửa:** Nếu app sở hữu implementation, chuyển sang implementation hoặc api theo public API. Nếu môi trường ngoài chịu trách nhiệm cung cấp class, kiểm tra container/launcher và binary version; nếu chỉ cần provider runtime, cấu hình runtimeOnly phù hợp.

### Lỗi 3 — Java compiler không thấy implementation từ runtimeOnly

**Nguyên nhân:** runtimeOnly không có trong compileClasspath.

**Cách sửa:** Đưa type dùng trực tiếp vào compile classpath qua implementation hoặc api tùy hợp đồng. Nếu mục đích là reflection/ServiceLoader, source nên chỉ tham chiếu API/contract phù hợp khi compile và để implementation vào runtimeOnly.

### Lỗi 4 — Consumer không import được annotation mà library dùng

**Nguyên nhân:** Library khai báo annotation trong compileOnly, không phải compileOnlyApi, trong khi annotation là một phần API compile-time mà consumer cần.

**Cách sửa:** Nếu library thật sự expose annotation/compile-time type, dùng java-library + compileOnlyApi. Nếu consumer chỉ tự chọn dùng annotation mà không liên quan hợp đồng của library, khai báo dependency trực tiếp tại consumer.

### Lỗi 5 — Dùng compileOnlyApi nhưng runtime cần type

**Nguyên nhân:** Một class/interface/annotation được phản chiếu lúc runtime hoặc có binary linkage cần type đó, nhưng bạn chỉ cấp compile-only.

**Cách sửa:** Đánh giá lại runtime contract: nếu cần class ở runtime, dùng api hoặc một runtime dependency/provider được quản lý phù hợp. Một annotation có RetentionPolicy.RUNTIME thường có thể cần type annotation ở runtime khi reflection hoặc framework xử lý nó.

### Lỗi 6 — Annotation processor không chạy

**Nguyên nhân:** Thêm dependency vào compileOnly nhưng quên annotationProcessor, hoặc plugin tương ứng không nhận processor.

**Cách sửa:** Đọc hướng dẫn của thư viện processor, khai báo annotationProcessor và compileOnly/test equivalents đúng scope. Bài lab dùng SOURCE marker **không có processor**, nên không cần annotationProcessor.

### Lỗi 7 — Test thất bại dù main compile thành công

**Nguyên nhân:** Test source set có classpath riêng. Một dependency chỉ compileOnly trong main chưa chắc hiện diện ở test compile/runtime; hoặc một provider cần lúc test không được thêm testRuntimeOnly.

**Cách sửa:** Xem testCompileClasspath/testRuntimeClasspath và khai báo testCompileOnly/testImplementation/testRuntimeOnly/annotationProcessor phù hợp, không đổi bừa toàn bộ dependency main thành implementation.

### Lỗi 8 — Published library hoạt động khác khi consumer dùng Maven

**Nguyên nhân:** Maven POM không diễn đạt Gradle variants đầy đủ như Gradle Module Metadata.

**Cách sửa:** Kiểm tra publication metadata (bao gồm Gradle Module Metadata khi có), scope Maven được tạo và thử build consumer thật. Chỉ dựa vào source build.gradle của library có thể chưa đủ để kết luận consumer Maven nhận đúng compileOnlyApi.

### Lỗi 9 — Tên configuration đổi khi chuyển plugin

**Nguyên nhân:** Plugin java, java-library, java-test-fixtures, Android, Kotlin Multiplatform có những source sets/variants khác nhau.

**Cách sửa:** Kiểm tra docs, các configuration do plugin tạo và resolved classpaths. Không coi compileOnlyApi là tên mọi plugin phải hỗ trợ.

### Lỗi 10 — Dùng api thay compileOnlyApi để chữa lỗi compile

**Nguyên nhân:** api cũng expose dependency ở runtime; có thể làm classpath lớn hơn và đưa thư viện không cần thiết vào runtime.

**Cách sửa:** Nếu type cần cả compile và runtime, dùng api. Nếu chỉ compile của library và consumer, dùng compileOnlyApi. Nếu chỉ module hiện tại compile, dùng compileOnly.

### Lỗi 11 — Tưởng JAR đã chứa runtimeOnly dependency

**Nguyên nhân:** Task jar mặc định của Java plugin đóng gói classes/resources của module, không tự tạo fat JAR chứa mọi dependency runtimeOnly.

**Cách sửa:** Dùng application distribution, launcher/classpath hoặc packaging/plugin thích hợp. Việc dependency có trên runtimeClasspath của task run không tự bảo đảm JAR độc lập được phân phối có kèm thư viện.

### Lỗi 12 — Phân biệt sai dependency type và configuration

**Nguyên nhân:** Cho rằng compileOnly chỉ dùng cho external Maven hoặc runtimeOnly chỉ dùng với JAR local.

**Cách sửa:** Cả ba configuration có thể khai báo external module, project dependency hoặc file dependency theo API plugin. Chọn **source** rồi chọn **scope** dựa trên nhu cầu compile/runtime; hai trục độc lập.

## 12. Checklist trước khi merge thay đổi dependencies

1. Module hiện tại đang là **Java application hay Java library**? Plugin có tạo compileOnlyApi không?
2. Type của dependency có thật sự được compiler của **module hiện tại** dùng?
3. Consumer module có cần type đó để compile public API không?
4. JVM lúc chạy có cần class hoặc annotation đó tồn tại không?
5. Nếu dependency được cấp bởi runtime environment, môi trường nào cung cấp, version nào và được kiểm thử ở đâu?
6. Có dùng Java annotation processor cần configuration riêng không?
7. Có code import trực tiếp class chỉ được khai báo runtimeOnly không?
8. compileClasspath/runtimeClasspath đã được kiểm tra đúng project chưa?
9. Với library, apiElements/runtimeElements có mang đúng dependency cho consumer không?
10. Với test fixtures, đã dùng testFixturesCompileOnlyApi hay nhầm compileOnlyApi của main?
11. Với library publish, metadata Gradle/Maven đã được kiểm tra bằng consumer độc lập chưa?
12. Có bị đưa dependency nội bộ vào API compile classpath của consumer một cách vô ý không?
13. Có đảm bảo Gradle Wrapper/JDK phù hợp và các module project đã include trong settings.gradle không?
14. Kết quả chạy có tái lập trên môi trường CI sạch mà không dựa vào classpath hoặc JAR thủ công của máy cá nhân không?

## 13. Bài tập tự kiểm tra

**Bài 1.** Một annotation SOURCE chỉ được library dùng trên private method. Chọn compileOnly, runtimeOnly hay compileOnlyApi?

**Bài 2.** Một annotation SOURCE nằm trong public contract của library; consumer phải nhìn thấy annotation type để compile code dùng API. Chọn gì và cần plugin nào?

**Bài 3.** Một logging provider chỉ được framework nạp bằng ServiceLoader lúc chạy. Source compile dựa vào một logging API khác. Provider nên nằm ở configuration nào?

**Bài 4.** Trong java-library, lib có compileOnly project(':hints'). App phụ thuộc project(':lib') và trực tiếp import :hints. App có chắc compile không? Sửa thế nào nếu đây là public compile-time API?

**Bài 5.** Nếu library dùng compileOnlyApi project(':annotations') nhưng annotation lại được framework đọc bằng reflection ở runtime, có chắc runtime sẽ tìm thấy type không?

**Bài 6.** Tại sao ứng dụng Java dùng runtimeOnly driver mà vẫn compile thành công khi source chỉ dùng java.sql.DriverManager?

**Bài 7.** Trong lab, đổi lib runtimeOnly project(':runtime-provider') thành compileOnly project(':runtime-provider'). Vì sao app compile vẫn được nhưng run lỗi?

**Bài 8.** Nếu lib có implementation project(':internal') và app có implementation project(':lib'), vì sao app compile không nên dựa vào class thuộc :internal trong mô hình java-library?

**Bài 9.** Plugin java-test-fixtures tạo config nào tương đương compileOnlyApi cho API của fixtures?

**Bài 10.** Có nên dùng compileOnlyApi trong app chỉ vì app dùng một annotation compile-time nội bộ? Vì sao?

**Bài 11.** Một thư viện cần Lombok để compiler sinh getter. Chỉ dùng compileOnly có đủ không? Cần kiểm tra configuration nào khác?

**Bài 12.** Vì sao chạy ./gradlew dependencies --configuration runtimeClasspath chưa đủ để hiểu một lỗi ở app:compileJava?

**Bài 13.** JPMS requires static transitive tương ứng với configuration nào trong Java Library Plugin?

**Bài 14.** Một dependency compile-time public API chỉ có qua Gradle Module Metadata. Có nên mặc định consumer Maven POM-only sẽ nhận chính xác cùng variants không?

### Đáp án gợi ý

1. **compileOnly**; module hiện tại cần lúc compile, consumer và runtime không cần.
2. **compileOnlyApi**, với **java-library** hoặc plugin tạo đúng configuration/variants đó.
3. **runtimeOnly** cho provider; API mà code import trực tiếp cần dependency compile thích hợp.
4. **Không**. compileOnly không expose cho consumer; dùng compileOnlyApi nếu đó là hợp đồng compile-time của library, hoặc app khai báo dependency trực tiếp khi app chủ động dùng annotation.
5. **Không**. compileOnlyApi không cung cấp runtime; nếu framework cần type, phải có runtime contract/dependency phù hợp.
6. java.sql là API JDK, driver implementation có thể được tìm/nạp ở runtime; không cần import trực tiếp driver khi compile.
7. Class được lib nạp bằng Class.forName chỉ có qua runtimeOnly; compileOnly không được chuyển sang app runtime.
8. implementation được coi là chi tiết nội bộ và không lộ ra consumer compile classpath như api; app nên khai báo trực tiếp dependency nó sử dụng.
9. **testFixturesCompileOnlyApi**.
10. Thường **không**; dùng compileOnly là đủ cho annotation nội bộ của app, không phải API được module khác compile chống lại.
11. Thường **không đủ**; processor cần có trên **annotationProcessor** theo tài liệu thư viện, còn annotation type cần compileOnly nếu phù hợp.
12. Một lỗi compile cần xem **compileClasspath**, không chỉ runtimeClasspath. Hai scope có thể chứa tập dependency khác nhau.
13. **compileOnlyApi**.
14. **Không**. Cần thử published metadata và behavior của consumer thực tế, nhất là vì POM không có cùng mô hình variants với Gradle Module Metadata.

## Tài liệu tham khảo chính thức

- [Gradle User Manual — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): api, implementation, compileOnly, runtimeOnly, compileOnlyApi, outgoing variants và JPMS.
- [Gradle User Manual — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): source sets, compile/runtime/test configurations.
- [Gradle User Manual — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html): vai trò declarable, resolvable, consumable và ý nghĩa configuration.
- [Gradle User Manual — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): những configuration do Java/Java Library plugins tạo.
- [Gradle User Manual — Java Test Fixtures Plugin](https://docs.gradle.org/current/userguide/java_test_fixtures_plugin.html): testFixturesCompileOnly, testFixturesCompileOnlyApi và testFixturesRuntimeOnly.
- [Gradle User Manual — Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): plugin tự áp dụng java-library và sử dụng compileOnlyApi cho Gradle API.
- [Gradle User Manual — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencies, dependencyInsight và resolved graphs.
- [Gradle User Manual — Java Module System](https://docs.gradle.org/current/userguide/java_library_plugin.html#sec:java_library_modular): ánh xạ requires static / requires static transitive.

**Ghi nhớ:** **compileOnly** đưa dependency vào compile classpath của module hiện tại, không cung cấp runtime hoặc API compile cho consumer; **runtimeOnly** đưa dependency vào runtime classpath của module và consumer theo variant phù hợp; **compileOnlyApi** là compile-only được **expose tới consumer compile** bởi mô hình Java Library Plugin, nhưng **không đưa vào runtime**. Muốn chọn đúng phải xác định plugin, ai compile, ai chạy và có cần public API type hay không.