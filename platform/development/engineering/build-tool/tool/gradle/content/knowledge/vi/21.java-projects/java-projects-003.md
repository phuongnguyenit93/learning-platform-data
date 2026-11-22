# Java Library plugin và ranh giới api với implementation trong Gradle

## 1. Tình huống: thư viện nào cần “lộ” cho project sử dụng?

Giả sử một nhóm phát triển **thư viện Java** tên `:library`. Thư viện có API công khai trả về đối tượng `Greeting` từ module `:contracts`, nhưng dùng một module `:engine` chỉ để thực thi bên trong phương thức. Project `:app` sử dụng `:library` và cần:

- Biên dịch được code gọi các phương thức công khai của `:library` và thao tác với `Greeting`.
- Không vô tình import `Engine`, bởi đó là chi tiết triển khai mà thư viện muốn tự do thay đổi.
- Khi chạy ứng dụng, vẫn có `:engine` trên runtime classpath để phương thức nội bộ hoạt động.

Nếu thư viện đưa tất cả dependencies vào một classpath công khai, consumer có thể dựa vào thứ vốn không thuộc hợp đồng API. Nếu thư viện giấu cả dependency dùng trong **chữ ký công khai**, consumer lại có thể gặp lỗi compile như “class file not found”.

Gradle giải quyết bài toán ấy bằng **Java Library plugin** và hai dependency scopes chính:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api(project(":contracts"))
    implementation(project(":engine"))
}
~~~

**Quy tắc cốt lõi:** `api` dành cho dependency mà **consumer cần khi biên dịch dựa trên API của thư viện**; `implementation` dành cho dependency mà **bản thân thư viện cần**, nhưng consumer không cần để biên dịch với API của nó. Dependency `implementation` **vẫn thường được cung cấp cho consumer ở runtime**.

Bài học này thuộc mục **Dự án Java** của module Build Tool Gradle, tập trung đúng ranh giới giữa `api` và `implementation`, cách nhận diện ABI, classpath và project dependency.

### Sau bài học, bạn có thể

1. Phân biệt plugin `java` với `java-library` và biết lúc nào dùng plugin nào.
2. Dùng `api`/`implementation` đúng theo **public binary interface** (ABI), không dựa vào `import` một cách máy móc.
3. Hiểu classpaths của **producer** và **consumer** ở compile/runtime.
4. Đọc `apiElements`/`runtimeElements`, `compileClasspath`/`runtimeClasspath` và mối liên hệ `extendsFrom`.
5. Nhận biết `compileOnlyApi`, `compileOnly`, `runtimeOnly`, `annotationProcessor`, `testImplementation`.
6. Chạy một project **Java 17 đa module** hoàn chỉnh, không cần tải thư viện từ Maven Central, để xác nhận ranh giới compile/runtime.
7. Thực hiện thí nghiệm cố ý khai báo sai dependency rồi giải thích lỗi compiler một cách chính xác.
8. Đọc báo cáo Gradle, đối chiếu Groovy DSL và kiểm tra metadata khi publish thư viện.
9. Hiểu lợi ích **compile classpath nhỏ**, incremental compilation/compile avoidance và kiến trúc tránh rò rỉ dependency.
10. Phân biệt ranh giới `api`/`implementation` với **Java access modifier**, Java Platform Module System và an toàn bảo mật.

## 2. Vì sao `java-library` khác `java`?

### 2.1. Plugin `java`

Trong một project Java thông thường:

~~~kotlin
plugins {
    id("java")
}

dependencies {
    implementation("org.example:internal-helper:1.0")
}
~~~

Đây là **đoạn minh họa cú pháp**, với tọa độ `org.example:internal-helper:1.0` giả định, không phải project chạy được nếu chưa có repository và artifact thật.

Plugin `java` cung cấp các source sets, compilation tasks, `jar`, `test`, `build` và những configurations chuẩn như `implementation`, `compileOnly`, `runtimeOnly`, `compileClasspath`, `runtimeClasspath`.

Plugin `java` thích hợp cho nhiều project Java, nhưng **không tạo sẵn dependency bucket `api` cho main library API**. Nếu bạn viết `api("...")` khi chỉ áp dụng `java`, build có thể báo không nhận ra `api` vì chưa có Java Library plugin hoặc plugin khác cung cấp nó.

### 2.2. Plugin `java-library`

~~~kotlin
plugins {
    id("java-library")
}
~~~

`java-library` **áp dụng và mở rộng** các khả năng của plugin `java`. Nó thêm mô hình **API/implementation separation** phục vụ library được project khác tiêu thụ, cả trong multi-project build lẫn khi publish external artifact.

Với `java-library`, bạn có thể khai báo:

~~~kotlin
dependencies {
    api("com.example:public-contract:1.0")
    implementation("com.example:private-engine:1.0")
}
~~~

Hai tọa độ ở ví dụ này chỉ dùng để diễn giải, không giả định tồn tại. Điều quan trọng là **mục đích của dependency**:

- `api`: library làm lộ một số kiểu/khả năng trong API mà compiler của consumer cần.
- `implementation`: dependency sử dụng để xây dựng/triển khai library, không cần để compiler của consumer hiểu các chữ ký công khai của library.

**Không đồng nghĩa** “`api` = public class” và “`implementation` = private class”. Chúng là **dependency configurations trong Gradle**; Java `public`/`private` là **access modifiers bên trong Java**. Hai tầng có liên quan nhưng không phải cùng một cơ chế.

### 2.3. Ứng dụng dùng plugin gì?

Một project ứng dụng chạy `main` thường dùng:

~~~kotlin
plugins {
    id("application")
}

application {
    mainClass.set("demo.app.Main")
}
~~~

Plugin `application` bao gồm Java support, cung cấp `run` và các tasks tạo distribution. Ứng dụng **không cần** áp dụng `java-library` chỉ vì nó phụ thuộc vào một thư viện Java Library.

Nếu bạn tạo một module vừa là thư viện có public API vừa có entry point riêng, hãy xác định rõ mục tiêu; không nên thêm plugin không cần thiết chỉ để nhận một task. Ví dụ chạy ở mục 6 có `:library` dùng `java-library` và `:app` dùng `application`.

## 3. Quy tắc chọn `api` hay `implementation`

Một cách đọc thực tế:

> Một dependency cần `api` nếu **kiểu từ dependency đó xuất hiện trong binary API mà consumer cần biên dịch dựa vào**. Nếu nó chỉ được dùng làm chi tiết triển khai, ưu tiên `implementation`.

### 3.1. Trường hợp cần `api`

Các trường hợp điển hình:

- Kiểu từ dependency là **superclass** hoặc **interface** mà public class của bạn extends/implements.
- Kiểu từ dependency xuất hiện trong **public/protected method parameter**.
- Kiểu từ dependency xuất hiện trong **public/protected method return type**.
- Kiểu từ dependency xuất hiện trong **public field**.
- Kiểu từ dependency nằm trong **generic parameter** của phương thức công khai, ví dụ `List<ExternalType>`.
- Kiểu annotation từ dependency được xuất bản trong public API mà compiler consumer cần hiểu.
- Một số package-private signatures hoặc compiler-visible metadata cũng có thể cần dependency trên compile classpath, tùy cách javac sử dụng class files.

Ví dụ public API:

~~~java
package demo.library;

import demo.contract.Greeting;

public final class PublicGreeter {
    public static Greeting createGreeting(String name) {
        return new Greeting(name);
    }
}
~~~

`Greeting` xuất hiện trong kiểu trả về `public static Greeting ...`. Consumer muốn biên dịch lệnh:

~~~java
Greeting value = PublicGreeter.createGreeting("Linh");
~~~

sẽ cần class `Greeting` của module `:contracts` trên compile classpath. Vì vậy trong `:library` cần:

~~~kotlin
dependencies {
    api(project(":contracts"))
}
~~~

### 3.2. Trường hợp thường dùng `implementation`

- Kiểu chỉ được dùng trong **method body**.
- Dependency chỉ xuất hiện trong **private field**/private method không ảnh hưởng compiler consumer.
- Thư viện là adapter, parser, storage driver hoặc helper nội bộ không lộ trong chữ ký API.
- Implementation có thể thay mà giữ API ổn định.
- Một framework được dùng bên trong module nhưng consumer không cần reference các kiểu đó khi compile.

Ví dụ:

~~~java
package demo.library;

import demo.contract.Greeting;
import demo.engine.Engine;

public final class PublicGreeter {
    public static String render(Greeting value) {
        return Engine.decorate(value.name());
    }
}
~~~

`Engine` chỉ được gọi trong **thân phương thức**, không nằm trong public return type hoặc parameter type. `:library` cần `Engine` để compile và chạy, nhưng compiler của `:app` không nhất thiết cần `Engine`. Khai báo đúng:

~~~kotlin
dependencies {
    api(project(":contracts"))
    implementation(project(":engine"))
}
~~~

**Nguyên tắc thực tế:** Bắt đầu bằng `implementation`, chỉ chuyển sang `api` khi có bằng chứng compiler consumer cần class từ dependency đó như một phần API. Cách này giữ ranh giới và classpath gọn hơn.

### 3.3. Không quyết định chỉ dựa trên dòng import

Một file Java có:

~~~java
import demo.contract.Greeting;
import demo.engine.Engine;
~~~

**Cả hai đều là import**, nhưng không có nghĩa cả hai phải là `api`. Tên xuất hiện trong import chỉ chứng minh **source của library** dùng chúng. Phải xem **chữ ký công khai, superclass/interface, fields, generics và compiler-visible annotations**.

Ngược lại, một kiểu có thể được nhắc bằng fully-qualified name mà **không có import**:

~~~java
public demo.contract.Greeting greeting() {
    return new demo.contract.Greeting("Linh");
}
~~~

Nó vẫn nằm trong public return type nên vẫn là API dependency.

### 3.4. Mức độ nhìn thấy của Java không đủ quyết định mọi ngoại lệ

Tài liệu chính thức của Gradle lưu ý: mặc dù quy tắc ABI là hướng dẫn tốt, **javac trong một số trường hợp cần class của dependency dù kiểu chỉ nằm trong private member**, ví dụ do type annotations hoặc overload resolution phức tạp.

Nếu compiler consumer thật sự cần class ấy:

- Dùng `api` nếu dependency cũng cần ở runtime.
- Dùng `compileOnlyApi` nếu class đó chỉ cần để compile consumer và không nên kéo vào runtime.
- Cân nhắc **thiết kế lại API** để không làm lộ kiểu nội bộ hoặc compiler metadata không mong muốn.

Không “cố bảo vệ” `implementation` bằng cách bỏ qua lỗi `class file for ... not found` của consumer; hãy giải thích được vì sao compiler cần kiểu đó.

## 4. Bảng quyết định nhanh

| Kiểu sử dụng dependency trong `:library` | Scope thường đúng | Lý do |
| --- | --- | --- |
| Public method trả về `external.Type` | `api` | Consumer cần kiểu trả về để compile |
| Public method nhận `external.Type` | `api` | Kiểu parameter là phần của API |
| Public class extends external superclass | `api` | Consumer cần hiểu binary superclass |
| Public interface extends external interface | `api` | External interface thuộc hợp đồng API |
| Public field có kiểu external | `api` | Kiểu field lộ cho compiler |
| Public method trả về `List<external.Type>` | `api` | External type có trong generic signature |
| External type chỉ dùng trong method body | `implementation` | Không lộ vào ABI |
| Adapter helper chỉ dùng trong private logic | `implementation` | Chi tiết triển khai |
| Annotation cần cho consumer compile nhưng được cung cấp ở runtime từ nơi khác | `compileOnlyApi` | Cần cho compiler consumer, không mang runtime artifact |
| API cần thư viện ở compile và runtime | `api` | Truyền xuống cả compile/runtime consumer |
| Thư viện chỉ cần để compile mã của module hiện tại | `compileOnly` | Không công bố cho consumer |
| Driver/implementation chỉ cần khi chạy, không compile | `runtimeOnly` | Chỉ runtime |
| Annotation processor được gọi khi biên dịch | `annotationProcessor` | Classpath processor riêng |
| Thư viện chỉ dùng cho tests của module | `testImplementation` | Không phải production dependency |

Bảng là **nguyên tắc lựa chọn**, không thay cho việc compile thử consumer hoặc kiểm tra metadata/variants của plugin cụ thể.

## 5. Ranh giới hiện ra ở classpath nào?

Đây là phần quan trọng nhất: `implementation` **không** đồng nghĩa “consumer không bao giờ nhận dependency”. Nó có nghĩa **không lộ trên consumer compile classpath thông qua API variant của library**, nhưng **vẫn được mang theo khi consumer cần runtime variant**.

### 5.1. Góc nhìn producer `:library`

~~~text
:library

Dependency buckets:
    api                 -> :contracts
    implementation      -> :engine
                              |
                              + kế thừa api

Resolvable configurations:
    compileClasspath    -> :contracts + :engine
    runtimeClasspath    -> :contracts + :engine (+ runtimeOnly nếu có)

Outgoing variants:
    apiElements         -> API-visible dependencies: :contracts
    runtimeElements     -> Runtime dependencies: :contracts + :engine
~~~

Trong Java Library plugin, `implementation` kế thừa `api`. Điều đó giúp bản thân library compile với các dependency API lẫn implementation. Nhưng `apiElements` chỉ kế thừa những phần cần công bố cho **consumer compile** (trong đó có `api` và `compileOnlyApi`), không tự đưa `implementation` thuần túy vào.

`runtimeElements` được nối với `implementation`/`runtimeOnly`, do đó runtime graph có `api` gián tiếp qua `implementation` và có các implementation dependencies thật sự cần khi chạy.

### 5.2. Góc nhìn consumer `:app`

`:app` chỉ có **một khai báo project dependency**:

~~~kotlin
dependencies {
    implementation(project(":library"))
}
~~~

Nhưng khi Gradle resolve hai nhu cầu khác nhau, kết quả có thể khác:

~~~text
:app compileClasspath --(needs java-api)--> :library apiElements
                                               |
                                               +-- :contracts
                                               (KHÔNG :engine nếu không có đường khác)

:app runtimeClasspath --(needs java-runtime)--> :library runtimeElements
                                                    |
                                                    +-- :contracts
                                                    +-- :engine
~~~

Vì sao như vậy?

1. `compileClasspath` của consumer thường yêu cầu `org.gradle.usage=java-api`.
2. `runtimeClasspath` thường yêu cầu `org.gradle.usage=java-runtime`.
3. `:library` công bố `apiElements` và `runtimeElements` với attributes/capabilities tương ứng.
4. Gradle chọn một **variant tương thích** cho mỗi nhu cầu, không chỉ so tên configuration.
5. Các dependency declarations trong variant được chọn quyết định nhánh transitive graph.

**Ngoại lệ quan trọng:** Nếu app có thêm dependency trực tiếp hoặc một đường khác tới `:engine`, nó **vẫn có thể** nằm trong compileClasspath. Ranh giới `implementation` của `:library` chỉ nói về **đường dependency được xuất từ library**, không phải một luật cấm module trên toàn graph.

### 5.3. Bảng classpath đầy đủ

| Scope khai báo tại library | Compile library | Runtime library | Compile consumer | Runtime consumer |
| --- | --- | --- | --- | --- |
| `api` | Có | Có | **Có** | Có |
| `implementation` | Có | Có | **Không qua library API variant** | Có |
| `compileOnly` | Có | Không | Không | Không |
| `compileOnlyApi` | Có | Không | **Có** | Không |
| `runtimeOnly` | Không | Có | Không | Có |
| `testImplementation` | Trong test library | Trong test library | Không | Không |
| `annotationProcessor` | Classpath processor của library | Không tự đi vào runtime | Không | Không |

“Có” ở đây là quan hệ **dependency scope** cơ bản khi plugin/metadata hợp lệ; phiên bản/variant/artifact cuối cùng còn chịu ảnh hưởng resolution và các đường dependency khác.

## 6. Bài thực hành Java 17 hoàn chỉnh: bốn project, không cần Maven Central

Chúng ta tạo một multi-project build với:

- `:contracts`: định nghĩa kiểu `Greeting` dùng trong API công khai.
- `:engine`: định nghĩa class `Engine` chỉ dùng trong thân phương thức library.
- `:library`: plugin `java-library`; `api(project(":contracts"))`, `implementation(project(":engine"))`.
- `:app`: plugin `application`; chỉ có `implementation(project(":library"))`.

Ví dụ **không có external module dependencies**, nên có thể chạy offline sau khi có bản Gradle/JDK phù hợp. Đây là bài Java 17 tự đầy đủ, không có module giả.

### 6.1. Cây thư mục

~~~text
java-library-boundary-lab/
├── settings.gradle.kts
├── contracts/
│   ├── build.gradle.kts
│   └── src/main/java/demo/contract/Greeting.java
├── engine/
│   ├── build.gradle.kts
│   └── src/main/java/demo/engine/Engine.java
├── library/
│   ├── build.gradle.kts
│   └── src/main/java/demo/library/PublicGreeter.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/Main.java
~~~

Root project **không cần** `build.gradle.kts` cho ví dụ này; `settings.gradle.kts` đủ để Gradle biết các subprojects. Nếu project convention của bạn yêu cầu root build script, có thể thêm file rỗng. Chưa có Wrapper thì lệnh `./gradlew` chưa sẵn; xem mục 6.13.

### 6.2. settings.gradle.kts

~~~kotlin
rootProject.name = "java-library-boundary-lab"

include(":contracts", ":engine", ":library", ":app")
~~~

`include(...)` tạo bốn Gradle project paths, không phải khai báo Java packages. Package Java được xác định trong các file `.java`.

### 6.3. contracts/build.gradle.kts

~~~kotlin
plugins {
    id("java")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Module `:contracts` chỉ chứa một public record đơn giản. Plugin `java` đã đủ để module này trở thành một project Java có outgoing API/runtime variants mà project khác có thể dùng. Không cần thêm `java-library` nếu nó không có dependencies cần phân loại thành API/implementation.

### 6.4. contracts/src/main/java/demo/contract/Greeting.java

~~~java
package demo.contract;

public record Greeting(String name) {
}
~~~

`record` là tính năng Java phù hợp với Java 17. Public type `Greeting` sẽ xuất hiện trong **return type và method parameter** của `PublicGreeter`. Vì vậy `:contracts` là **API dependency** của `:library`.

### 6.5. engine/build.gradle.kts

~~~kotlin
plugins {
    id("java")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

### 6.6. engine/src/main/java/demo/engine/Engine.java

~~~java
package demo.engine;

public final class Engine {
    private Engine() {
    }

    public static String decorate(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Class `Engine` được khai báo `public` để source trong **module `:library`** có thể gọi nó từ package khác. Điều này **không có nghĩa** consumer `:app` tự có `:engine` trên compile classpath.

Đây là minh chứng quan trọng: **Java public access** và **Gradle API dependency exposure** thuộc hai tầng khác nhau.

### 6.7. library/build.gradle.kts — trọng tâm bài học

~~~kotlin
plugins {
    id("java-library")
}

group = "demo.library"
version = "1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    api(project(":contracts"))
    implementation(project(":engine"))
}
~~~

Giải thích:

1. `java-library` tạo bucket `api` bên cạnh `implementation`, và các tiêu chuẩn công bố API/runtime.
2. `api(project(":contracts"))` làm cho compiler của consumer có thể nhìn thấy type `Greeting` qua đường phụ thuộc vào library.
3. `implementation(project(":engine"))` giúp **library tự compile và run** với Engine, đồng thời mang Engine sang **consumer runtime** khi library được dùng.
4. Compiler của consumer **không tự nhận Engine** thông qua `apiElements` của library.
5. `group` và `version` giúp default capability/artifact coordinates của library có tên dễ nhận diện trong báo cáo; không ảnh hưởng ý nghĩa `api` vs `implementation`.
6. Không cần khai báo `repositories { mavenCentral() }` vì dependencies ở đây là **project dependencies trong cùng build**.

### 6.8. library/src/main/java/demo/library/PublicGreeter.java

~~~java
package demo.library;

import demo.contract.Greeting;
import demo.engine.Engine;

public final class PublicGreeter {
    private PublicGreeter() {
    }

    public static Greeting createGreeting(String name) {
        return new Greeting(name);
    }

    public static String render(Greeting greeting) {
        return Engine.decorate(greeting.name());
    }
}
~~~

Đọc public signatures:

- `public static Greeting createGreeting(String name)`: trả về `Greeting` → `:contracts` là **API dependency**.
- `public static String render(Greeting greeting)`: nhận `Greeting` → `:contracts` tiếp tục là **API dependency**.
- `Engine.decorate(...)`: chỉ trong method body; signature của `render` trả về `String` → `:engine` là **implementation dependency**.

Nếu bỏ `implementation(project(":engine"))`, library có thể không compile vì `Engine` không nằm trên compileClasspath của chính library. Nếu đổi `api(project(":contracts"))` thành `implementation(project(":contracts"))`, library vẫn compile được, nhưng app có thể mất khả năng compile mã dùng `Greeting` như public API. Hai lỗi này có nguyên nhân **khác nhau**.

### 6.9. app/build.gradle.kts

~~~kotlin
plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":library"))
}

application {
    mainClass.set("demo.app.Main")
}
~~~

App không khai báo `:contracts` hay `:engine` trực tiếp. Nó nhận đúng transitive API dependency và runtime dependencies qua biến thể của `:library`.

### 6.10. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.contract.Greeting;
import demo.library.PublicGreeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        Greeting greeting = PublicGreeter.createGreeting("Linh");

        System.out.println(PublicGreeter.render(greeting));
        System.out.println("engine-on-runtime-classpath=" +
                (Main.class.getClassLoader()
                    .getResource("demo/engine/Engine.class") != null));
    }
}
~~~

Đây là Java 17 **runnable**. App source import `Greeting` và `PublicGreeter` nhưng **không import Engine**. Dòng kiểm tra `getResource(...)` dùng runtime classloader để xem class file `Engine.class` có mặt không; nó không chứng minh rằng app có thể import Engine lúc compile.

### 6.11. Chạy ứng dụng qua Gradle

Đứng ở thư mục root:

~~~bash
gradle --quiet :app:run
~~~

Stdout **chính xác của mã Java**, với bốn modules đúng như trên:

~~~text
Hello, Linh!
engine-on-runtime-classpath=true
~~~

Giải thích:

- App compile thấy `Greeting` nhờ `:library` công bố dependency `:contracts` qua `apiElements`.
- App compile thấy `PublicGreeter` qua project dependency `:library`.
- Library compile thấy `Engine` nhờ `implementation(project(":engine"))`.
- Khi `:app:run`, Java runtime classpath chứa cả `:library`, `:contracts` và `:engine` nhờ runtime variant; do đó `Engine.class` có mặt và `render` chạy được.
- Không có network dependency bên ngoài trong project mẫu; nếu build không chạy, kiểm tra Gradle/JDK, các tên file/package và settings.

Lệnh đầy đủ khi không cần chỉ stdout Java:

~~~bash
gradle :app:compileJava
gradle :app:run
gradle :app:build
~~~

Các lệnh này có thể in status `UP-TO-DATE`, `NO-SOURCE` hoặc log Gradle tùy version/môi trường. Chỉ hai dòng ở trên là **stdout cố định từ chương trình**.

### 6.12. Kiểm tra artifact/distribution

Plugin `application` còn cung cấp:

~~~bash
gradle :app:installDist
~~~

Distribution thường nằm ở `app/build/install/app` và có script chạy trong `bin/`. Trên macOS/Linux:

~~~bash
./app/build/install/app/bin/app
~~~

Trên Windows PowerShell/cmd, script tương ứng là `app\build\install\app\bin\app.bat`.

Distribution do Application plugin tạo mang theo các runtime dependencies cần thiết, thường trong thư mục `lib/`. Nếu app chạy đúng qua Gradle mà distribution gặp lỗi, kiểm tra nội dung distribution/classpath và những rules đóng gói của project; đừng tự cho rằng chỉ cần JAR của app là đủ cho mọi dependencies.

### 6.13. Dùng Gradle Wrapper đúng cách

Nếu project có `gradlew`/`gradlew.bat`, ưu tiên:

~~~bash
# macOS/Linux
./gradlew --quiet :app:run
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Windows:

~~~bat
gradlew.bat --quiet :app:run
gradlew.bat :app:dependencies --configuration compileClasspath
gradlew.bat :app:dependencies --configuration runtimeClasspath
~~~

Nếu project mới chưa có Wrapper, dùng bản Gradle phù hợp đã cài để chạy `gradle wrapper`. Build cần một JDK 17 toolchain được tìm thấy hoặc cơ chế provisioning đã cấu hình; `java { toolchain... }` không bảo đảm máy tự có JDK 17.

## 7. Xác minh ranh giới bằng báo cáo dependency graph

### 7.1. Consumer compileClasspath

~~~bash
gradle :app:dependencies --configuration compileClasspath
~~~

Trong dự án mẫu, cây được rút gọn về mặt ý nghĩa:

~~~text
compileClasspath
\--- project :library
     \--- project :contracts
~~~

Đoạn này **không phải stdout cố định**; Gradle có thể in markers, thông tin variant hoặc indent khác tùy bản. Điểm cần kiểm tra: `:contracts` là transitive dependency khi compile app, **`:engine` không nằm trên đường API mà library xuất**.

### 7.2. Consumer runtimeClasspath

~~~bash
gradle :app:dependencies --configuration runtimeClasspath
~~~

Sơ đồ rút gọn:

~~~text
runtimeClasspath
\--- project :library
     +--- project :contracts
     \--- project :engine
~~~

Ở runtime, library cần `Engine` để thực hiện `render`, nên `:engine` xuất hiện. Đồng thời `:contracts` vẫn có vì record `Greeting` được tham chiếu runtime.

**Đừng suy luận** rằng mọi `implementation` của thư viện bị loại khỏi consumer hoàn toàn. Đây chính là hiểu lầm thường gặp nhất của bài học.

### 7.3. Producer outgoingVariants

~~~bash
gradle :library:outgoingVariants --variant apiElements
gradle :library:outgoingVariants --variant runtimeElements
~~~

Bạn sẽ thấy các attributes/capabilities/artifacts của variants công bố, ví dụ:

~~~text
Variant apiElements:
  org.gradle.usage = java-api

Variant runtimeElements:
  org.gradle.usage = java-runtime
~~~

Đây là **trích đoạn minh họa**. Báo cáo thực tế có thể cho category, JVM version, library elements, artifacts và secondary variants (classes/resources). Nó không phải một listing đơn giản của mọi dependencies nếu bạn chỉ đọc những dòng `Attributes`.

### 7.4. Consumer resolvableConfigurations

~~~bash
gradle :app:resolvableConfigurations --configuration compileClasspath
gradle :app:resolvableConfigurations --configuration runtimeClasspath
~~~

Tìm các ý:

- `compileClasspath`: yêu cầu Usage `java-api`; kế thừa `compileOnly` và `implementation` của **app**.
- `runtimeClasspath`: yêu cầu Usage `java-runtime`; kế thừa `runtimeOnly` và `implementation` của **app**.

**Lưu ý:** `app:implementation` là một declaration cho `project(":library")`. Nó **không phải** `library:implementation`. Hai project có configurations riêng; Gradle chọn producer variant qua project dependency.

### 7.5. dependencyInsight để xem lựa chọn thực tế

~~~bash
gradle :app:dependencyInsight --dependency library --configuration compileClasspath
gradle :app:dependencyInsight --dependency library --configuration runtimeClasspath
~~~

Tùy Gradle version, `dependencyInsight` có thể hiển thị selected variant và bảng requested/provided attributes; `--all-variants` cung cấp thêm thông tin khi được hỗ trợ:

~~~bash
gradle :app:dependencyInsight --dependency library --configuration compileClasspath --all-variants
~~~

Nhìn `java-api` vs `java-runtime` và những attributes khác. Những reports giúp giải thích **variant nào được chọn**, không chỉ module nào có trong graph.

## 8. Thí nghiệm có chủ đích: đổi `api` thành `implementation` và quan sát lỗi

Thí nghiệm này **cố ý làm build không compile**, không phải trạng thái cuối cần giữ.

Trong `library/build.gradle.kts`, đổi:

~~~kotlin
dependencies {
    api(project(":contracts"))
    implementation(project(":engine"))
}
~~~

thành:

~~~kotlin
dependencies {
    implementation(project(":contracts"))
    implementation(project(":engine"))
}
~~~

Bản thân `:library` vẫn có thể compile: nó có `Greeting` và `Engine` trên compileClasspath. Nhưng `:app` đang dùng `Greeting` trong source và API của PublicGreeter.

Chạy build sạch của app:

~~~bash
gradle :app:clean :app:compileJava
~~~

Trong điều kiện app chỉ phụ thuộc `:library` như project mẫu, compiler có thể báo dạng lỗi:

~~~text
package demo.contract does not exist
cannot find symbol: class Greeting
class file for demo.contract.Greeting not found
~~~

**Đây là các thông điệp lỗi đại diện, không phải toàn bộ stdout cố định** của javac. Lỗi chính là `:contracts` không còn được xuất qua compile variant của `:library`, dù library riêng vẫn biên dịch thành công.

### 8.1. Cách sửa đúng

Khôi phục:

~~~kotlin
dependencies {
    api(project(":contracts"))
    implementation(project(":engine"))
}
~~~

Rồi chạy lại:

~~~bash
gradle :app:compileJava
gradle --quiet :app:run
~~~

App trở lại trạng thái hợp lệ. Đừng “vá” bằng cách thêm `implementation(project(":contracts"))` vào mọi consumer một cách máy móc, khi `Greeting` thật sự thuộc **API public của library**.

### 8.2. Khi nào thêm trực tiếp vào consumer là hợp lý?

Nếu ứng dụng có **quan hệ nghiệp vụ trực tiếp** với `:contracts` độc lập với library, khai báo `implementation(project(":contracts"))` ở app là có lý do. Nhưng nếu mọi consumer của library đều cần `Greeting` để gọi public methods, trách nhiệm **công bố dependency ở API** thuộc về library.

Nguyên tắc thiết kế: **Producer mô tả đúng hợp đồng API; consumer khai báo đúng dependency thật sự của chính nó**. Không biến việc thiếu `api` thành nợ kỹ thuật phân tán trên hàng chục projects.

## 9. Thí nghiệm ngược: đưa Engine vào API có tốt không?

Giả sử bạn chuyển:

~~~kotlin
dependencies {
    api(project(":contracts"))
    api(project(":engine"))
}
~~~

Đây vẫn có thể là cấu hình Gradle hợp lệ, nhưng sẽ **làm `:engine` xuất hiện trên compile classpath của app**, khiến consumer có thể import:

~~~java
import demo.engine.Engine;
~~~

và compile code sử dụng `Engine` dù library **không định nghĩa Engine là hợp đồng API công khai**.

Hệ quả:

- Consumer dễ phụ thuộc chi tiết triển khai.
- Thay Engine bằng một implementation khác trở thành breaking change đối với consumer đã lỡ sử dụng.
- Compile classpath phình to, tăng khả năng xung đột dependency.
- Mỗi thay đổi ABI của Engine có thể làm tăng số downstream projects cần xem xét compile lại.
- Không nhất thiết phá chức năng ngay hôm nay, nhưng ranh giới kiến trúc yếu đi.

**Không** nên cho mọi thư viện nội bộ vào `api` “cho đỡ lỗi compile”. Chỉ promote lên API khi public contract hoặc compiler consumer **thực sự cần**.

### 9.1. Cố ý import Engine từ app khi nó vẫn là implementation

Nếu giữ cấu hình **đúng** của mục 6, rồi thêm vào `app/src/main/java/demo/app/Main.java`:

~~~java
// Đoạn cố ý gây lỗi, KHÔNG đưa vào project runnable ở mục 6.
import demo.engine.Engine;
~~~

sau đó gọi `Engine.decorate(...)` trong `main`, `:app:compileJava` có thể báo:

~~~text
package demo.engine does not exist
cannot find symbol: variable Engine
~~~

Khi chạy bằng `:app:run`, code gốc vẫn tìm thấy `Engine.class` **ở runtime**. Hai điều đó không mâu thuẫn: **compile classpath khác runtime classpath**.

Nếu app **cần chủ đích** dùng Engine trực tiếp, nó có thể tự khai báo `implementation(project(":engine"))`. Khi đó Engine có trên compile classpath từ **một đường trực tiếp khác**, không phải vì `:library` đã thay đổi chính sách xuất API.

### 9.2. `implementation` không phải sandbox bảo mật

Engine có thể tồn tại trên runtime classpath của app. Người viết app có thể chủ đích thêm direct dependency, reflection hoặc cơ chế class loading để truy cập class. Vì thế `implementation` **không phải access-control security boundary**, không ngăn người dùng đọc JAR, và không thay thế Java visibility, JPMS exports, code signing hay quyền truy cập hệ thống.

Nó là **hợp đồng quản lý dependency ở compile time/variant metadata**, giúp tránh sử dụng không chủ đích và hỗ trợ bảo trì.

## 10. Thử riêng bằng javac/java, không dựa vào Gradle

Đây là phương pháp tốt để thấy rõ **hai classpaths khác nhau**. Các file Java đã được định nghĩa đầy đủ ở mục 6.

### 10.1. macOS/Linux

~~~bash
mkdir -p out/contracts out/engine out/library out/app

javac -d out/contracts \
  contracts/src/main/java/demo/contract/Greeting.java

javac -d out/engine \
  engine/src/main/java/demo/engine/Engine.java

javac -cp "out/contracts:out/engine" -d out/library \
  library/src/main/java/demo/library/PublicGreeter.java

# Compiler của consumer KHÔNG nhận out/engine.
javac -cp "out/contracts:out/library" -d out/app \
  app/src/main/java/demo/app/Main.java

# Runtime của consumer CÓ nhận out/engine.
java -cp "out/app:out/library:out/contracts:out/engine" demo.app.Main
~~~

Stdout:

~~~text
Hello, Linh!
engine-on-runtime-classpath=true
~~~

Điểm cần thấy: app compiler không cần `out/engine` để biên dịch Main, nhưng chạy `PublicGreeter.render(...)` cần Engine trong runtime classpath.

### 10.2. Windows PowerShell/cmd

~~~bat
mkdir out\contracts
mkdir out\engine
mkdir out\library
mkdir out\app

javac -d out\contracts contracts\src\main\java\demo\contract\Greeting.java
javac -d out\engine engine\src\main\java\demo\engine\Engine.java

javac -cp "out\contracts;out\engine" -d out\library library\src\main\java\demo\library\PublicGreeter.java
javac -cp "out\contracts;out\library" -d out\app app\src\main\java\demo\app\Main.java

java -cp "out\app;out\library;out\contracts;out\engine" demo.app.Main
~~~

Trên Windows, classpath entries dùng dấu `;`; trên Unix dùng dấu `:`. Nếu thư mục `out` đã có files cũ từ lần thử khác, nên bắt đầu trong workspace sạch hoặc dọn đúng thư mục output do chính thí nghiệm tạo.

### 10.3. Những lệnh javac/java này chứng minh điều gì?

- Chứng minh các file Java đúng package/class, code Java 17 chạy được.
- Chứng minh compiler consumer **không cần** Engine trong ví dụ.
- Chứng minh runtime **cần** Engine vì implementation library gọi nó.

Nhưng chúng **không tự chứng minh** Gradle đã cấu hình `apiElements`/`runtimeElements` đúng. Muốn xác minh Gradle variant selection, chạy `:app:dependencies`/`dependencyInsight` cùng `:app:run` như mục 7.

## 11. Groovy DSL tương đương

Nếu bạn dùng `build.gradle` thay vì `build.gradle.kts`, logic `api`/`implementation` không đổi. Đây là các **phiên bản thay thế** của scripts ở mục 6; không giữ đồng thời hai DSL scripts cùng mục đích trong một project.

### 11.1. settings.gradle

~~~groovy
rootProject.name = 'java-library-boundary-lab'
include ':contracts', ':engine', ':library', ':app'
~~~

### 11.2. contracts/build.gradle và engine/build.gradle

Cả hai module có thể dùng nội dung:

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

### 11.3. library/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

group = 'demo.library'
version = '1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    api project(':contracts')
    implementation project(':engine')
}
~~~

### 11.4. app/build.gradle

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
    implementation project(':library')
}

application {
    mainClass = 'demo.app.Main'
}
~~~

Giữ nguyên bốn file Java ở mục 6. Kết quả `gradle --quiet :app:run` vẫn là:

~~~text
Hello, Linh!
engine-on-runtime-classpath=true
~~~

Kotlin DSL cần `api(project(":contracts"))`, trong khi Groovy cho phép `api project(':contracts')`. Cả hai gọi vào cùng dependency configurations do Java Library plugin tạo.

## 12. `apiElements`, `runtimeElements` và `extendsFrom`

### 12.1. Tại sao không resolve trực tiếp `api`?

`api` và `implementation` là **declarable dependency scopes**. Chúng là những nơi đặt dependency declarations, không phải configuration thường dùng để lấy file classpath. Gradle hướng tới tách roles:

| Vai trò | Ví dụ | Công dụng |
| --- | --- | --- |
| Declarable | `api`, `implementation`, `runtimeOnly` | Khai báo dependency |
| Resolvable | `compileClasspath`, `runtimeClasspath` | Resolve artifacts/variants cho task |
| Consumable | `apiElements`, `runtimeElements` | Công bố variant cho consumer |

Đừng gọi `configurations.getByName("api").files` để “xem dependencies”: declarable scope hiện đại không phải configuration hợp lệ để resolve trực tiếp.

### 12.2. Các quan hệ inheritance tiêu biểu của Java Library

~~~text
api
  |
  v
implementation ----------> compileClasspath
  |                             ^
  |                             |
  +--------------------> runtimeClasspath <--- runtimeOnly

api ---------------------> apiElements
compileOnlyApi ----------> apiElements

implementation ----------> runtimeElements
runtimeOnly -------------> runtimeElements
~~~

Đọc chính xác:

- `implementation` **kế thừa** dependency declarations từ `api`.
- `compileClasspath` kế thừa `compileOnly` và `implementation`.
- `runtimeClasspath` kế thừa `runtimeOnly` và `implementation`.
- `apiElements` kế thừa `api` và `compileOnlyApi`.
- `runtimeElements` kế thừa `runtimeOnly` và `implementation`.
- `compileOnly` kế thừa `compileOnlyApi`, nên library compile với những type này.

Sơ đồ là đồ hình quan hệ declarations, **không phải task execution DAG**. `extendsFrom` không tự sao chép attributes hoặc vai trò declarable/resolvable/consumable.

### 12.3. Vì sao dùng variants chứ không phụ thuộc tên configuration?

Một consumer đang compile thường yêu cầu Usage `java-api`; khi chạy thường yêu cầu `java-runtime`. Producer `:library` công bố hai variants với attributes khác nhau. Gradle chọn bằng **variant-aware dependency resolution**, không phải so sánh `"compileClasspath"` với `"apiElements"` bằng tên.

Cần xem thêm `org.gradle.category`, `org.gradle.libraryelements`, `org.gradle.jvm.version` và capabilities khi giải quyết project dependencies phức tạp. Trong ví dụ cơ bản, Java ecosystem plugin cấu hình những attributes này giúp selection xảy ra tự nhiên.

## 13. `compileOnlyApi`: API cần khi biên dịch nhưng không cần ở runtime

Java Library plugin có `compileOnlyApi` dùng cho dependencies mà **consumer compiler cần** nhưng **consumer runtime không cần theo hợp đồng**.

Ví dụ điển hình:

- Annotation types được compiler cần để đọc một public API nhưng được môi trường runtime cung cấp sẵn hoặc chỉ có ý nghĩa compile.
- Một kiểu được javac cần khi phân tích class files nhưng dependency không nên được cung cấp như runtime dependency.
- Các hợp đồng đã được platform/container cung cấp theo chính sách rõ.

Kotlin DSL:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    compileOnlyApi("org.example:provided-annotations:1.0")
}
~~~

Đây là **đoạn minh họa**, module `org.example:provided-annotations:1.0` không được khẳng định tồn tại và cần repository phù hợp nếu dùng external dependency.

Sự khác biệt:

| Scope | Compile library | Compile consumer | Runtime consumer |
| --- | --- | --- | --- |
| `compileOnly` | Có | Không qua API variant | Không |
| `compileOnlyApi` | Có | Có | Không |
| `api` | Có | Có | Có |
| `implementation` | Có | Không qua API variant | Có |

### 13.1. Vì sao không dùng compileOnlyApi cho mọi API type?

Nếu public API thực sự dùng type cần có khi chạy (như `Greeting` trong ví dụ), `compileOnlyApi` là lựa chọn **sai** trừ khi runtime environment có một provider được đảm bảo. App compile có thể pass nhưng runtime gặp `NoClassDefFoundError`/`ClassNotFoundException`.

Với `:contracts` chứa `Greeting` và app dùng record, `api(project(":contracts"))` là lựa chọn đúng trong project mẫu. Đừng đổi thành `compileOnlyApi` chỉ để làm runtime graph nhỏ.

### 13.2. Compiler có thể cần dependency tưởng như private

Một số trường hợp Type annotation/overload resolution làm compiler yêu cầu class từ một dependency mà bạn nghĩ chỉ xuất hiện trong private implementation. Tài liệu Gradle thừa nhận những tình huống này.

Quy trình:

1. Compile **module consumer thật** thay vì chỉ compile library.
2. Đọc lỗi `class file for ... not found`.
3. Xác định class đó xuất hiện trong binary ABI/annotations/compiler metadata nào.
4. Nếu runtime cần class, dùng `api`; nếu chỉ compile và runtime đã được cung cấp riêng, xem `compileOnlyApi`.
5. Nếu đó là leak không mong muốn, **thiết kế lại** public API/annotations.
6. Test cả compile và runtime để bảo đảm không tạo thiếu dependency.

## 14. `runtimeOnly`, `compileOnly`, `testImplementation` và `annotationProcessor`

### 14.1. runtimeOnly

~~~kotlin
dependencies {
    runtimeOnly("org.example:database-driver:1.0")
}
~~~

Là cú pháp minh họa. Dùng cho thư viện chỉ cần lúc thực thi (ví dụ driver được nạp qua `ServiceLoader`/reflection). Nó **không tự** có trong compileClasspath của module, nhưng có trong runtime graph tương ứng và có thể được library publish qua runtime variant.

Không dùng `runtimeOnly` cho kiểu xuất hiện trong method signature mà cần compiler consumer biết.

### 14.2. compileOnly

~~~kotlin
dependencies {
    compileOnly("org.example:provided-api:1.0")
}
~~~

Dành cho dependency library cần **chỉ lúc biên dịch**, không export cho consumer compile/runtime qua API variant. Ví dụ các API được environment/container cung cấp theo hợp đồng.

Nếu consumer cũng phải nhìn thấy type ở public API của library, `compileOnly` có thể không đủ; xem `compileOnlyApi`.

### 14.3. testImplementation

~~~kotlin
dependencies {
    testImplementation("org.example:test-tool:1.0")
}
~~~

Đây chỉ là thư viện test module này, không phải phần API hay runtime production của consumers. Dù unit tests của `:library` nhìn thấy `Engine` qua classpaths main/test, điều đó **không chứng minh** `:app` có Engine lúc compile.

### 14.4. annotationProcessor

~~~kotlin
dependencies {
    annotationProcessor("org.example:code-generator:1.0")
}
~~~

Dùng classpath processor riêng cho build-time Java annotation processing. Không nên đưa một annotation processor vào `api` chỉ vì nó giúp generate source, trừ khi một type từ nó **thật sự thuộc hợp đồng API** — đó là chuyện khác.

Các tọa độ `org.example` trong mục 14 đều giả định, không dùng làm dependencies của project runnable ở mục 6.

## 15. Hậu quả hiệu năng: compile classpath nhỏ và compile avoidance

### 15.1. Vì sao không đưa mọi thứ vào api?

Mọi dependency `api` của library có thể được đưa vào compile classpath của nhiều downstream consumers. Một project lớn sẽ:

- Compile với classpath nhiều JAR hơn.
- Tăng khả năng dính các type không thuộc hợp đồng công khai.
- Có thêm version conflicts/ambiguous APIs.
- Có thể gây thêm recompilation khi thay đổi API dependency.
- Làm người dùng thư viện khó xác định dependency nào thật sự được hỗ trợ.

Với `implementation`, consumer compile classpath **không cần** mang những implementation-only dependencies của library, giảm cơ hội bị ảnh hưởng bởi thay đổi nội bộ.

### 15.2. Incremental compilation/compile avoidance

Gradle có thể tránh biên dịch lại consumer khi dependency thay đổi **implementation-only** mà **binary ABI** không đổi, nhờ classpath snapshotting và compile avoidance trong Java ecosystem. Đây là lợi ích lớn của `java-library` khi library được dùng bởi nhiều project.

Ví dụ:

~~~text
:app -> :library -> :engine

Thay code trong Engine.decorate():
    "Hello, " + name + "!"
thành:
    "Hi, " + name + "!"
~~~

Nếu **chữ ký công khai của `:library` không đổi**, compiler của `:app` không cần nhìn thấy một API mới. Gradle **có thể** tránh recompile `:app` trong những điều kiện phù hợp. Nhưng runtime output phải đổi theo implementation mới, nên `:engine` và liên quan runtime vẫn được build/package theo task graph.

**Không tuyên bố luôn luôn không recompile:** Annotation processors, thay đổi ABI thật, task plugin tùy chỉnh, generated code, incremental state hoặc project configuration khác có thể buộc compile lại.

### 15.3. Thay API sẽ có tác động khác

Nếu bạn sửa chữ ký:

~~~java
public static Greeting createGreeting(String name)
~~~

thành một chữ ký không tương thích, downstream consumers gọi phương thức có thể phải sửa source và recompile. Việc chuyển một dependency từ `implementation` lên `api` cũng làm thay đổi compile graph/metadata của consumer. Đây là thay đổi hợp đồng thư viện, cần test và review rõ.

## 16. Public API “rò rỉ” implementation: ví dụ sai và cách xử lý

Giả sử trong `:library` bạn thêm phương thức công khai:

~~~java
// Đoạn minh họa sửa PublicGreeter; cố ý KHÔNG giữ trong ví dụ chạy được.
public static demo.engine.Engine currentEngine() {
    return null;
}
~~~

Bây giờ `Engine` **xuất hiện trong public return type**, nên từ góc độ compiler/ABI, module `:engine` không còn hoàn toàn là implementation-only.

Bạn có ba lựa chọn:

1. Nếu chính sách thư viện **cố ý công bố Engine như API**, chuyển dependency sang `api(project(":engine"))` và xem đó là phần hợp đồng compatibility.
2. Nếu muốn giữ Engine nội bộ, **đổi public API** để trả về một interface/DTO/hợp đồng ổn định thuộc library hoặc module contract.
3. Nếu compiler consumer cần type nhưng runtime do container cung cấp, có thể cân nhắc `compileOnlyApi` **chỉ khi** biết runtime provisioning chắc chắn; không phải lựa chọn mặc định cho một Engine mà library gọi ở runtime.

Ví dụ hướng tái cấu trúc:

~~~java
// Java conceptual API: chỉ công bố dữ liệu/hợp đồng ổn định.
public interface MessageRenderer {
    String render(String value);
}
~~~

Library có thể dùng Engine ở implementation để thực hiện `MessageRenderer`, nhưng consumer chỉ biết contract. Đây là cách thiết kế API rõ và bền hơn việc công bố mọi helper của library.

### 16.1. Generic signatures cũng là API

~~~java
// Demo chữ ký API; cần khai báo types và class context đầy đủ.
public java.util.List<demo.contract.Greeting> getGreetings();
~~~

`Greeting` xuất hiện trong generic return type, nên module `:contracts` vẫn là API dependency. Dù JVM type erasure có thể khiến runtime descriptor chỉ chứa `List`, javac đọc generic `Signature` attribute từ classfile để kiểm tra kiểu.

### 16.2. Public annotations có thể làm lộ dependency

Nếu một annotation từ module bên ngoài xuất hiện trên public class/method hoặc compiler phải đọc type annotations, consumer có thể cần annotation class. Chọn `api` hoặc `compileOnlyApi` tùy **runtime contract**, không coi mọi annotation đương nhiên chỉ là implementation detail.

## 17. Xuất bản thư viện: Gradle Module Metadata và Maven POM

### 17.1. Trong multi-project build

Khi `:app` dùng:

~~~kotlin
implementation(project(":library"))
~~~

Gradle biết producer `:library` và có thể chọn `apiElements`/`runtimeElements` bằng variant-aware resolution. Đây là trường hợp dễ thấy nhất của `api` vs `implementation`.

### 17.2. Khi publish Maven repository

Nếu thư viện dùng `java-library` cùng `maven-publish`, Gradle có thể tạo Gradle Module Metadata và Maven POM mô tả separation phù hợp.

Ví dụ snippet **minh họa publishing**, không phải cấu hình đầy đủ của project mẫu:

~~~kotlin
import org.gradle.api.publish.maven.MavenPublication

plugins {
    id("java-library")
    id("maven-publish")
}

group = "demo.library"
version = "1.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
~~~

Không chạy `publish` trong ví dụ chính vì chưa khai báo repository để publish và chưa xét credentials. `from(components["java"])` dùng Java component có variants phù hợp.

Với Maven POM do Gradle Java Library plugin tạo, thông thường:

- `api` dependencies được biểu diễn trong Maven **compile** scope.
- `implementation` dependencies được biểu diễn trong Maven **runtime** scope.
- Gradle Module Metadata có thể biểu đạt variant attributes/dependencies phong phú hơn POM.

Điều này giúp consumer Gradle hoặc Maven nhận compile/runtime graph hợp lý hơn, trong giới hạn metadata format và cách từng tool hiểu scopes.

### 17.3. Không phải mọi Maven POM đều giữ ranh giới sạch

Nhiều thư viện Maven không phân biệt dependency dùng **để build chính thư viện** với dependency cần khi **biên dịch consumer**, nên đưa quá nhiều libraries vào Maven compile scope. Nếu bạn phụ thuộc một artifact như vậy, downstream compile classpath có thể lớn hơn mong muốn dù **project của bạn** dùng `java-library` đúng.

Trong trường hợp metadata upstream sai, có thể phải dùng component metadata rules hoặc tìm một phiên bản/library có metadata chính xác. Đừng kỳ vọng `java-library` tự sửa metadata của mọi thư viện bên ngoài.

### 17.4. Không dùng API để “giảm số dòng POM”

Việc phân chia scopes cần theo public ABI và runtime semantics, không theo mong muốn làm POM ngắn. Một public API dùng type bên ngoài nhưng chỉ khai báo `implementation` là metadata sai; consumer có thể không compile. Một library đưa mọi implementation dependency vào `api` có thể compile “dễ” nhưng công bố hợp đồng quá rộng.

### 17.5. Version compatibility khi nâng dependency

Nếu public API dùng type từ dependency X, nâng major version X có thể làm **consumer source/binary compatibility** thay đổi. Với implementation-only dependency, bạn thường có nhiều tự do hơn để nâng/thay, miễn là library vẫn giữ chức năng và ABI đúng.

Cũng cần xem runtime transitive conflicts: consumer có thể có dependency khác tới cùng module, và Gradle sẽ giải quyết version/variant dựa trên toàn graph. `implementation` không ngăn xung đột runtime tự động.

## 18. Java Platform Module System (JPMS) không thay thế api/implementation

Nếu bạn tạo `module-info.java` và dùng Java modules:

~~~java
// Ví dụ khái niệm, yêu cầu các modules thực sự có module names đúng.
module demo.library {
    requires transitive demo.contracts;
    requires demo.engine;
    exports demo.library;
}
~~~

Ở JPMS:

- `exports` xác định package nào được lộ từ module Java.
- `requires transitive` làm cho dependency module được đọc bắc cầu theo quan hệ module cho consumers.
- `requires` biểu đạt dependency module trực tiếp; không tự trở thành `requires transitive`.

Các directives này là **Java module system metadata**, không phải cú pháp Gradle `api`/`implementation`. Nếu dùng module-path, bạn phải đảm bảo **hai tầng mô hình nhất quán**:

- Dependency public trong Java module graph có thể cần `requires transitive`.
- Cùng dependency ở Gradle có thể cần `api`.
- Dependency nội bộ thường dùng `requires` và `implementation`.

Đoạn `module-info.java` ở trên chỉ là minh họa; project runnable ở mục 6 chạy **classpath**, không tạo JPMS modules và không cần module descriptors. Đừng thêm nó vào project lab khi chưa tạo module names cho `:contracts`/`:engine`.

## 19. Test và kiểm chứng ranh giới của thư viện

### 19.1. Test compile từ consumer thật

`testImplementation` của **:library** có thể thấy implementation dependencies của library theo Java plugin configuration hierarchy. Vì vậy chỉ viết unit test bên trong library có thể **không phát hiện** rằng API dependency đã khai báo sai.

Một consumer test module như `:app` có giá trị hơn cho lỗi này:

1. Chỉ khai báo `implementation(project(":library"))`.
2. Viết source sử dụng **public API**.
3. Compile `:app:compileJava`.
4. Đảm bảo không khai báo `:contracts` trực tiếp chỉ để “vá”.
5. Chạy `:app:run`/smoke test để thấy runtime dependencies đầy đủ.
6. So sánh `compileClasspath`/`runtimeClasspath` theo đúng scopes.

### 19.2. Test publish/consumer metadata

Với thư viện được publish, thêm integration test tiêu thụ artifact **như một external module** từ repository thử nghiệm (không chỉ project dependency) có thể phát hiện POM/Module Metadata sai. Kiểm tra:

- Consumer compile được các signatures public.
- Runtime của consumer có các implementation dependencies cần thiết.
- Tọa độ group/name/version và artifacts đúng.
- Không tự lộ dependency nội bộ không cần ở compile.
- Public ABI không vô tình chứa types bị thiếu.

### 19.3. Kiểm tra package và binary API

JDK `javap` giúp đọc các signatures đã biên dịch:

~~~bash
gradle :library:classes

# macOS/Linux (đã compile xong)
javap -public -classpath "library/build/classes/java/main:contracts/build/classes/java/main" demo.library.PublicGreeter
~~~

Trên Windows:

~~~bat
javap -public -classpath "library\build\classes\java\main;contracts\build\classes\java\main" demo.library.PublicGreeter
~~~

Output sẽ có hai public methods của library dùng `Greeting` và `String`, **không** có `Engine` trong public signatures của project mẫu. Đây là một cách kiểm tra **ABI thực tế**, khác đọc dòng `import` trong Java source.

Không dự đoán toàn bộ stdout `javap` cố định vì version/format javap khác nhau. Điều cần xác minh là có phương thức tạo/trả `Greeting`, render nhận `Greeting`, không có public signature nào chứa Engine.

## 20. Cách đọc lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng sửa |
| --- | --- | --- |
| `Unresolved reference: api` hoặc `Could not find method api()` | Project chỉ áp dụng `java` hoặc plugin không tạo `api` | Áp dụng `java-library` trên **producer library** |
| `class file for ... not found` khi consumer compile | Public ABI của producer dùng type nhưng dependency chỉ ở `implementation` | Chuyển sang `api`/`compileOnlyApi` hoặc sửa API |
| Consumer compile thấy Engine dù library dùng `implementation` | Consumer có **đường khác** tới Engine, dependency trực tiếp, metadata khác | Dùng `dependencies --configuration compileClasspath` để truy vết |
| Library compile không tìm thấy Engine | Library chưa khai báo `implementation(project(":engine"))` hoặc sai source/package | Khai báo đúng dependency và project path |
| Compile app pass, runtime báo `NoClassDefFoundError` | Thư viện cần dependency lúc chạy nhưng scope sai, exclude, hoặc distribution thiếu | Xem `runtimeClasspath`, dùng `implementation`/`runtimeOnly` đúng và kiểm tra distribution |
| `No matching variant of project ...` | Attributes/capabilities/JVM target hoặc plugin producer sai | Xem `outgoingVariants`/`resolvableConfigurations` và toolchains |
| `Cannot choose between variants` | Nhiều producer variants tương thích nhưng thiếu thông tin phân biệt | Xem attributes/capabilities, rules phù hợp |
| Compile downstream chạy lại nhiều lần | API/ABI thay đổi, `api` khai báo quá rộng, processors hoặc classpath khác | So sánh ABI, thu hẹp `api`, kiểm tra compile avoidance |
| Library test pass nhưng app compile fail | Test của library thấy impl dependencies, không mô phỏng consumer compile | Thêm consumer integration build |
| Published consumer lỗi còn project dependency chạy được | Metadata Maven POM/Gradle Module Metadata không như kỳ vọng | Test publication từ repository thử nghiệm |
| App compile không có Engine nhưng runtime thấy Engine | **Hành vi đúng** của `implementation` | Không sửa nếu Engine là detail triển khai |
| External library xuất nhiều dependency compile hơn mong muốn | Upstream Maven POM đưa impl dependencies vào compile scope | Xem metadata thực, constraints/rules/upstream fix |

### 20.1. Đừng sửa sai bằng classpath tùy tiện

Khi gặp lỗi public type không có trong consumer compile, đừng tự thêm `files("path/to/internal.jar")` vào compiler args hoặc bỏ compile checks. Những cách đó che việc **library công bố sai hợp đồng API**. Sửa đúng ở producer và kiểm tra graph.

### 20.2. Đừng dùng `api` để chữa lỗi runtime-only

Nếu một driver không xuất hiện trong public signatures và chỉ cần khi chạy, `runtimeOnly` hoặc `implementation` mới là hướng phù hợp. Đưa nó vào `api` chỉ làm compile graph lớn mà không giải thích bản chất dependency.

### 20.3. Đừng nhầm dependency module với source visibility

`api(project(":contracts"))` không tự biến mọi class của module `:contracts` thành “API được bảo đảm ổn định”. Bạn vẫn cần chính sách package, public surface, compatibility và tài liệu. Gradle có thể cho compiler consumer thấy một artifact; **những kiểu nào nên được sử dụng** vẫn là trách nhiệm thiết kế thư viện.

## 21. Mười bước thiết kế thư viện Java có API ranh giới tốt

1. **Xác định consumer thực tế.** Library được dùng bởi module Java nào, JVM target nào, có publish Maven không?
2. **Liệt kê public/protected signatures.** Superclasses, interfaces, method params/returns, fields, generics, annotations.
3. **Đánh dấu dependency có type trong ABI.** Những dependency này có thể cần `api` hoặc `compileOnlyApi`.
4. **Đánh dấu dependency chỉ dùng trong implementation.** Ưu tiên `implementation`.
5. **Tách compile-only và runtime-only** khi mục đích thật sự khác nhau; không cho tất cả vào `api`.
6. **Dùng `java-library` ở producer**, `application`/`java` ở consumer theo nhu cầu.
7. **Viết consumer test module chỉ phụ thuộc library.** Để compiler phát hiện public API leak.
8. **Xem dependency graph ở cả compile/runtime.** Dùng `:app:dependencies` và `dependencyInsight`.
9. **Kiểm thử runtime/distribution và publication.** Không chỉ compile library.
10. **Review API changes và performance.** Tránh mở rộng `api` không cần thiết; ghi rõ các thay đổi breaking/semver theo policy dự án.

## 22. Bài tập và đáp án

### Bài 1. Chọn scope cho public return type

Thư viện có:

~~~java
public demo.contract.Greeting createGreeting(String name);
~~~

`Greeting` thuộc module `:contracts`. Scope nào ở producer?

**Đáp án:** `api(project(":contracts"))`, vì consumer compiler cần biết `Greeting` trong public return type và module này cũng cần có ở runtime trong ví dụ.

### Bài 2. Chọn scope cho helper nội bộ

Thư viện gọi:

~~~java
String result = demo.engine.Engine.decorate(name);
~~~

nhưng chỉ trong thân một method trả về `String`. Scope nào?

**Đáp án:** `implementation(project(":engine"))`, vì Engine là chi tiết triển khai; library compile/runtime cần nó, consumer compile không cần được công bố qua library API.

### Bài 3. java hay java-library?

Producer muốn viết `api(project(":contracts"))` nhưng chỉ có:

~~~kotlin
plugins {
    id("java")
}
~~~

**Đáp án:** Áp dụng `id("java-library")` ở producer. Plugin `java-library` mở rộng `java` và tạo bucket `api` đúng mục đích. App không nhất thiết phải dùng `java-library`.

### Bài 4. Consumer có thấy implementation khi compile không?

`:app` chỉ `implementation(project(":library"))`. Library khai báo `implementation(project(":engine"))`. App có tự import Engine được không?

**Đáp án:** Không qua API variant của library, nếu không có dependency path nào khác tới Engine. Nếu app có direct `implementation(project(":engine"))` riêng thì compiler app có thể thấy Engine qua đường đó.

### Bài 5. Consumer có thấy Engine khi chạy không?

App code **không import Engine** nhưng gọi `PublicGreeter.render(...)`, bên trong dùng Engine. Engine có được Gradle đưa vào runtime graph không?

**Đáp án:** Có trong project mẫu vì `runtimeElements` của library chứa các implementation dependencies cần chạy. Vì vậy stdout có `engine-on-runtime-classpath=true`.

### Bài 6. Public generic type

Method công khai có chữ ký:

~~~java
public java.util.List<demo.contract.Greeting> listGreetings();
~~~

`Greeting` trong generic type có phải API dependency?

**Đáp án:** Có. Generic `Signature` có thể được compiler consumer sử dụng, nên `:contracts` là API dependency.

### Bài 7. Chỉ nhìn import có đủ không?

Một file import cả `Greeting` và `Engine`. Có nhất thiết dùng `api` cho cả hai?

**Đáp án:** Không. Xem types xuất hiện trong compiler-visible ABI, không chỉ dòng import. Engine có thể chỉ nằm trong method body và được đặt ở implementation.

### Bài 8. Thay api bằng implementation ở producer

Trong lab, sửa `api(project(":contracts"))` thành `implementation(project(":contracts"))`. Library vẫn compile. Vì sao app có thể fail?

**Đáp án:** Consumer compile graph chọn `apiElements` của library, không nhận `:contracts` nếu chỉ được khai báo như implementation. App đang dùng `Greeting` từ public API nên javac thiếu type.

### Bài 9. Lệnh kiểm tra

Bạn muốn so sánh classpaths của app. Dùng lệnh nào?

**Đáp án:**

~~~bash
gradle :app:dependencies --configuration compileClasspath
gradle :app:dependencies --configuration runtimeClasspath
~~~

Để xem producer variants, thêm `gradle :library:outgoingVariants --variant apiElements` và `--variant runtimeElements`.

### Bài 10. Lỗi runtime sau khi dùng compileOnlyApi

Một library API trả về `Greeting`, consumer compile pass nhờ `compileOnlyApi(project(":contracts"))`, nhưng runtime không có `:contracts`. Cách sửa?

**Đáp án:** Nếu runtime thật sự cần `Greeting`, phải có runtime provisioning; trong project bình thường, dùng `api(project(":contracts"))`. `compileOnlyApi` chỉ đúng cho dependency được bảo đảm không cần mang runtime artifact qua thư viện.

### Bài 11. Vì sao library unit test chưa đủ?

Tests của producer có thể import Engine dù Engine được khai báo implementation. Vậy đã xác minh consumer compile boundary chưa?

**Đáp án:** Chưa. Tests của producer thường thấy implementation classpath của producer. Cần compile một consumer module chỉ phụ thuộc library và xem compileClasspath của nó.

### Bài 12. Lợi ích của implementation

Bạn thay nội dung method của Engine mà không đổi public ABI của library. Lợi ích có thể là gì?

**Đáp án:** Gradle có thể tránh downstream recompilation trong điều kiện phù hợp, do consumer compile classpath không cần Engine. Tuy nhiên kết quả tùy ABI, processors, task state và build logic; không bảo đảm mọi thay đổi đều không recompile.

### Bài 13. Public annotation

Một annotation class từ dependency ngoài được dùng trong public API và javac của consumer cần đọc nó. Scope nào?

**Đáp án:** `api` nếu cần ở runtime, hoặc `compileOnlyApi` nếu chỉ cần khi compile và runtime provisioning phù hợp. Không tự giữ `implementation` nếu consumer compile thất bại.

### Bài 14. App output

Với bốn projects được giữ nguyên như mục 6, `gradle --quiet :app:run` sẽ in gì?

**Đáp án:**

~~~text
Hello, Linh!
engine-on-runtime-classpath=true
~~~

### Bài 15. Có phải implementation bảo mật Engine?

App có thể tìm Engine bằng runtime classloader. `implementation` có ngăn mọi mã app truy cập Engine không?

**Đáp án:** Không. Nó là compile dependency exposure policy của library, không phải sandbox hoặc security boundary. Java access modifiers/JPMS/security practices là các tầng riêng.

### Bài 16. Maven publish

Thư viện `java-library` publish bằng `maven-publish`. `api` và `implementation` thường được biểu diễn như thế nào trong generated Maven POM?

**Đáp án:** `api` vào Maven compile scope, `implementation` vào runtime scope, với những giới hạn theo metadata/variant và cách publish cụ thể. Gradle Module Metadata biểu đạt nhiều thông tin variant-aware hơn.

## 23. Bảng ghi nhớ cuối bài

| Bạn muốn biết | Quy tắc/biện pháp |
| --- | --- |
| Library cần export type cho compiler consumer | `api` |
| Library dùng dependency chỉ trong thân phương thức | `implementation` |
| Consumer cần type lúc compile nhưng runtime không mang theo | Cân nhắc `compileOnlyApi` |
| Dependency chỉ khi module hiện tại compile | `compileOnly` |
| Dependency chỉ khi chạy | `runtimeOnly` |
| Library khai báo `api` ở plugin nào? | `java-library` |
| App có cần `java-library` không? | Không; `application`/`java` thường đủ |
| Library compile thấy gì? | Cả `api` và `implementation` |
| App compile nhận gì qua library? | `apiElements` và API-related dependency graph |
| App runtime nhận gì qua library? | `runtimeElements` với `api` + `implementation` + `runtimeOnly` phù hợp |
| Có nhiều đường khác kéo impl dependency vào app compile? | Có thể; xem full graph |
| `implementation` có giấu Engine khỏi JVM runtime? | Không |
| `apiElements`/`runtimeElements` là gì? | Consumable variants của Java Library |
| `compileClasspath`/`runtimeClasspath` là gì? | Resolvable configurations |
| `api`/`implementation` là gì? | Declarable dependency scopes |
| Public API dùng `ExternalType` trong generic/signature | Kiểm tra ABI, thường cần `api` |
| Vì sao tránh `api` bừa bãi? | Compile classpath nhỏ, giảm leak, hỗ trợ compile avoidance |
| Chẩn đoán consumer thiếu public type | Compile consumer thật, xem `dependencies`/`dependencyInsight` |
| Chẩn đoán no matching variant | Xem attributes, JVM version và outgoing/consumer configurations |

**Kết luận:** Với **Java Library plugin**, ranh giới `api` và `implementation` là **hợp đồng dependency dành cho consumer compilation**, không chỉ là cách tổ chức build script. Hãy dùng `api` cho dependencies xuất hiện trong public binary API và `implementation` cho dependencies nội bộ. Bản thân library cần cả hai để compile, còn consumer thường chỉ nhận `api` trên compile classpath nhưng nhận cả `api` và `implementation` trên runtime classpath. Xác minh điều đó bằng **một consumer module thật**, báo cáo configurations/variants và chạy ứng dụng Java 17.

## 24. Tài liệu tham khảo chính thức

- [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html) — `api`/`implementation` separation, ABI, `compileOnlyApi`, configuration hierarchy và publishing.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) — source sets, `compileClasspath`, `runtimeClasspath` và tasks Java cơ bản.
- [Gradle — Variant Selection and Attribute Matching](https://docs.gradle.org/current/userguide/variant_aware_resolution.html) — `java-api`, `java-runtime`, variants và artifact selection.
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html) — declarable/resolvable/consumable roles và `extendsFrom`.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) — `dependencies` và `dependencyInsight`.
- [Gradle — Building Java and JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html) — Java project structure và compile/testing workflow.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html) — Java component publishing và metadata.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html) — `include(":library", ":app")` và project dependencies.
