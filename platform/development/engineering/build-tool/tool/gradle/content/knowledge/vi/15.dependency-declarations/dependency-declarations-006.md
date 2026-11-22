# Dependency giữa các project và lựa chọn API được công khai trong Gradle

## 1. Vấn đề: module nào được phép nhìn thấy thư viện của module khác?

Một ứng dụng Java thường được chia thành nhiều module để tách trách nhiệm: giao diện, xử lý nghiệp vụ, hợp đồng dữ liệu, truy cập database hoặc các thành phần dùng chung. Với Gradle, mỗi module có thể là một **project con** trong cùng một **multi-project build**. Một project có thể khai báo phụ thuộc vào project khác, và Gradle sẽ tự phối hợp việc biên dịch, thử nghiệm và cung cấp classpath phù hợp.

Tuy nhiên, **phụ thuộc vào một project** không tự có nghĩa là **mọi dependency của project đó đều được công khai cho code ở project tiêu thụ**.

Ví dụ:

```text
:app  ──────>  :core  ──────>  :contracts
                  |
                  +---- sử dụng lớp Greeting từ contracts
```

Giả sử `:core` có phương thức công khai trả về `Greeting` thuộc `:contracts`. Khi viết code `:app`, trình biên dịch có cần nhìn thấy lớp `Greeting` không? **Có**, nếu kiểu này xuất hiện trong mã hoặc chữ ký public mà app cần biên dịch. Vì vậy `:core` nên khai báo `api(project(":contracts"))` nếu `Greeting` thật sự là một phần của API mà `:core` công bố.

Ngược lại, nếu `:core` chỉ dùng một thư viện để thực hiện logic **bên trong**, và không để kiểu từ thư viện đó xuất hiện trong hợp đồng biên dịch của bên dùng, `implementation(project(":contracts"))` thường là lựa chọn phù hợp hơn.

Sau bài này, bạn sẽ:

1. Hiểu `project(":module")` và điều kiện để các project nằm trong cùng build.
2. Phân biệt **project dependency**, **external module dependency** và **file dependency**.
3. Hiểu chính xác `api` so với `implementation`, đặc biệt ở **compile classpath** và **runtime classpath**.
4. Biết khi nào một kiểu dữ liệu là một phần của **public API** của thư viện.
5. Tự chạy dự án Java 17 gồm ba project, thay đổi khai báo dependency và quan sát lỗi biên dịch.
6. Đọc cây dependency và các biến thể `apiElements`/`runtimeElements` bằng lệnh Gradle.
7. Tránh công khai dependency quá rộng, tạo vòng phụ thuộc hoặc làm build thiếu khả năng tái lập.

## 2. Từ một project đến multi-project build

Một project Gradle thường có script `build.gradle` hoặc `build.gradle.kts` để mô tả plugin, dependency và task của chính nó. Multi-project build có một **root project** và các project con được khai báo từ file settings.

Ví dụ Groovy DSL trong `settings.gradle`:

```groovy
rootProject.name = 'project-api-demo'

include 'contracts', 'core', 'app'
```

Gradle hiểu các project path:

| Project path | Thư mục mặc định | Trách nhiệm ví dụ |
| --- | --- | --- |
| `:` | Root build | Điều phối và cấu hình chung nếu có |
| `:contracts` | `contracts/` | Định nghĩa kiểu/hợp đồng được chia sẻ |
| `:core` | `core/` | Triển khai nghiệp vụ sử dụng hợp đồng |
| `:app` | `app/` | Ứng dụng sử dụng API của core |

Dấu `:` đứng đầu là **đường dẫn project từ root**, không phải dấu phân cách thư mục hệ điều hành. `project(':core')` tham chiếu **project con** đã được đưa vào cùng build; nó không có nghĩa Gradle sẽ tự tải module có tên `core` từ Maven Central.

Trong Java multi-project, các project thường có source set riêng:

```text
project-api-demo/
├── settings.gradle
├── contracts/
│   ├── build.gradle
│   └── src/main/java/...
├── core/
│   ├── build.gradle
│   └── src/main/java/...
└── app/
    ├── build.gradle
    └── src/main/java/...
```

Mỗi project có task như `:core:compileJava` hoặc `:app:build`, và dependency giữa project giúp Gradle tự xác định công việc nào cần hoàn thành trước để project tiêu thụ có classpath hợp lệ.

### 2.1. Project dependency khác external dependency

Trong Groovy DSL:

```groovy
dependencies {
    implementation project(':core')
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

- `project(':core')`: dùng thành phần do project `:core` của **cùng build** tạo/công bố.
- `'org.apache.commons:commons-lang3:3.14.0'`: dùng module bên ngoài theo tọa độ `group:artifact:version`; Gradle cần repository phù hợp để resolve nó.

Trong Kotlin DSL:

```kotlin
dependencies {
    implementation(project(":core"))
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Với project dependency nội bộ, Gradle có thể chọn output/classes hoặc artifact thích hợp theo variant và loại dependency; không nên khẳng định mọi lần build đều phải tạo một JAR vật lý trước khi biên dịch consumer. Cơ chế selection sẽ được giải thích ở mục 7.

### 2.2. Khi nào không dùng `project(...)`?

Nếu một module đã được phát hành như thư viện Maven độc lập và nằm ngoài build này, thông thường dùng:

```groovy
dependencies {
    implementation 'com.example.training:math-utils:1.2.0'
}
```

Nếu cần phối hợp **nhiều build độc lập** cùng phát triển, Gradle có cơ chế composite build qua `includeBuild(...)`. Đây không phải cùng khái niệm với `include 'core'`; `project(':core')` không tự truy cập project ở một build ngoài được include theo cơ chế composite. Đừng thay hai cơ chế cho nhau một cách máy móc.

## 3. Plugin `java-library` và hai cấu hình quan trọng

Gradle cung cấp plugin `java` cho project có mã Java. Plugin `java-library` bổ sung mô hình **thư viện Java có API công khai** và những dependency configuration phù hợp.

Trong `core/build.gradle`:

```groovy
plugins {
    id 'java-library'
}
```

Khi áp dụng `java-library`, bạn có thể khai báo:

```groovy
dependencies {
    api project(':contracts')
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

Với Kotlin DSL, cú pháp hợp lệ là:

```kotlin
plugins {
    id("java-library")
}

dependencies {
    api(project(":contracts"))
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Cách dùng `api` có ý nghĩa khi project **là thư viện**: nó cho consumer biết một dependency cần hiện diện khi **biên dịch code sử dụng thư viện**. Còn `implementation` nói dependency cần cho phần triển khai nội bộ; nó không tự được đưa vào **compile classpath bắc cầu** của consumer.

**Quan trọng:** `api` được cung cấp bởi `java-library`, không phải cấu hình mặc định cho mọi project chỉ áp dụng `java` hoặc `application`. Với ứng dụng, dùng `implementation` cho dependency trực tiếp thường là đúng; ứng dụng không phải thư viện dùng để công bố API cho consumer tiếp theo.

Để tránh nhầm, hãy liên hệ với mục đích của project:

| Loại project | Plugin phổ biến | Dependency configuration |
| --- | --- | --- |
| Thư viện cung cấp public Java API | `java-library` | `api` khi cần công khai; `implementation` khi chi tiết nội bộ |
| Ứng dụng Java có `main` | `application` | `implementation`, `runtimeOnly`, `testImplementation`... |
| Module Java không có consumer như thư viện | `java` | `implementation`, `compileOnly`, `runtimeOnly`... |

## 4. `api` khác `implementation` ở compile classpath như thế nào?

Giả sử:

```text
:app --implementation--> :core
:core --api------------> :contracts
```

Khi app biên dịch, Gradle cần tạo classpath có thư viện `:core` và những dependency mà `:core` công bố trên **API variant**. Vì `:contracts` được khai báo `api`, các lớp public thích hợp trong `:contracts` có thể được sử dụng trong code `:app`.

Nếu đổi thành:

```text
:app --implementation--> :core
:core --implementation--> :contracts
```

thì `:contracts` vẫn cần để biên dịch **chính `:core`**, và thường vẫn là dependency runtime của `:core`. Nhưng nó **không được truyền bắc cầu vào compile classpath của `:app` chỉ nhờ dependency lên `:core`**.

Bảng tóm tắt:

| Khai báo trong `:core` | `:core` tự biên dịch với dependency? | `:app` nhận qua API compile của `:core`? | Thường được tính vào runtime dependency của `:core`? |
| --- | --- | --- | --- |
| `api project(':contracts')` | Có | Có | Có |
| `implementation project(':contracts')` | Có | Không | Có |
| `compileOnly project(':contracts')` | Có | Không | Không tự thêm vào runtime |
| `runtimeOnly project(':contracts')` | Không dùng cho compile của core | Không | Có |
| `compileOnlyApi project(':contracts')` | Có | Có trên compile API | Không tự thêm vào runtime |

`compileOnlyApi` là một lựa chọn chuyên biệt của Java Library plugin khi kiểu được công bố ra API **chỉ cần cho compile**, nhưng runtime không được kỳ vọng mang dependency đó tự động. Nó cần được dùng thận trọng; đa số API Java thông thường dùng `api` hoặc `implementation` là đủ.

**Ghi nhớ:** từ góc độ một **library consumer**, điểm khác biệt then chốt của `api` và `implementation` là **đường đi của dependency vào compile classpath bắc cầu**. Không diễn giải `implementation` là “bí mật tuyệt đối”: thư viện nội bộ vẫn có thể có mặt ở runtime, trong phân phối hoặc khi quan sát dependency graph.

## 5. “API được công khai” nghĩa là gì trong Java?

Từ `api` ở Gradle không có nghĩa đơn giản là mọi class bên trong module đều public. Ở Java, một public API của thư viện là **những thành phần mà code bên ngoài phải biết để viết/biên dịch chương trình sử dụng thư viện**.

Ví dụ:

```java
package demo.core;

import demo.contracts.Greeting;

public final class Greeter {
    public Greeting greet(String who) {
        return new Greeting("Xin chào, " + who + "!");
    }
}
```

Lớp `Greeter` thuộc `:core` có phương thức public trả về `Greeting`, còn `Greeting` thuộc `:contracts`. Consumer cần **biết định nghĩa của `Greeting`** nếu viết:

```java
Greeting value = new Greeter().greet("Gradle");
System.out.println(value.text());
```

Vì kiểu đó xuất hiện ở chữ ký public, `:core` **để lộ contract type** của `:contracts`. Trong mô hình Java Library, `api project(':contracts')` là khai báo tự nhiên nếu `:core` muốn consumer sử dụng API này mà không phải tự khai báo thêm `:contracts`.

Những dấu hiệu khác cho thấy một dependency có thể thuộc API:

- Kiểu của **tham số** trong public method/constructor.
- Kiểu **giá trị trả về** của public method.
- **Superclass** hoặc **interface** public mà class của thư viện kế thừa/triển khai.
- Kiểu trong public field, generic type argument, generic bound hoặc public annotation mà consumer cần sử dụng.
- Kiểu ngoại lệ checked được khai báo trong API công khai, nếu consumer cần nhận diện/xử lý.
- Các lớp/hợp đồng trong public surface mà công cụ biên dịch hoặc người dùng thư viện cần đọc.

Ví dụ:

```java
public interface GreetingService {
    demo.contracts.Greeting greet(String name);
}
```

Đây cũng là public signature phụ thuộc vào `Greeting`, dù không có code xử lý dữ liệu trong interface.

Ngược lại:

```java
package demo.core;

import demo.contracts.Greeting;

public final class GreetingFacade {
    public String greetMessage(String name) {
        Greeting greeting = new Greeting("Xin chào, " + name + "!");
        return greeting.text();
    }
}
```

Ở ví dụ này, public signature chỉ gồm `String`, còn `Greeting` là một **chi tiết triển khai nội bộ**. Nếu consumer chỉ gọi `new GreetingFacade().greetMessage("Gradle")`, consumer không cần tham chiếu trực tiếp kiểu `Greeting` ở compile time. Khi đó `implementation project(':contracts')` thường phù hợp hơn, miễn là runtime của ứng dụng có dependency cần thiết.

**Đừng quyết định chỉ bằng việc có dòng `import` trong source của thư viện.** Một dependency có thể được import ở code internal nhưng không lộ ra API; ngược lại một kiểu có thể được tham chiếu bằng fully qualified name trong chữ ký public mà không có import.

## 6. Dự án thực hành ba module Java 17 — bản chạy thành công với `api`

Phần này tạo một build hoàn chỉnh gồm:

```text
:contracts -- công bố record Greeting
:core      -- công bố lớp Greeter, có public method trả Greeting
:app       -- dùng Greeter và Greeting để in lời chào
```

Ứng dụng sẽ chạy được **khi `:core` khai báo `api project(':contracts')`**.

### 6.1. Yêu cầu và cây file

Cần JDK 17 và Gradle tương thích với JDK 17, có thể dùng Gradle Wrapper của dự án. Dùng tên thư mục:

```text
project-api-demo/
├── settings.gradle
├── contracts/
│   ├── build.gradle
│   └── src/main/java/demo/contracts/Greeting.java
├── core/
│   ├── build.gradle
│   └── src/main/java/demo/core/Greeter.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/Main.java
```

Không cần repository Maven Central vì ví dụ chỉ dùng project nội bộ và Java standard library. Các plugin `java-library` và `application` là plugin tích hợp của Gradle.

**File gốc `settings.gradle`:**

```groovy
rootProject.name = 'project-api-demo'

include 'contracts', 'core', 'app'
```

**File `contracts/build.gradle`:**

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

**File `contracts/src/main/java/demo/contracts/Greeting.java`:**

```java
package demo.contracts;

public record Greeting(String text) {
}
```

`record` là tính năng Java hiện đại có trong Java 17. Nó tự cung cấp accessor `text()` cho thành phần `text` và constructor `new Greeting(String)`.

**File `core/build.gradle`:**

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    api project(':contracts')
}
```

**File `core/src/main/java/demo/core/Greeter.java`:**

```java
package demo.core;

import demo.contracts.Greeting;

public final class Greeter {
    public Greeting greet(String who) {
        return new Greeting("Xin chào, " + who + "!");
    }
}
```

**File `app/build.gradle`:**

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':core')
}

application {
    mainClass = 'demo.app.Main'
}
```

**File `app/src/main/java/demo/app/Main.java`:**

```java
package demo.app;

import demo.contracts.Greeting;
import demo.core.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        Greeting greeting = new Greeter().greet("Gradle");
        System.out.println(greeting.text());
    }
}
```

### 6.2. Chạy build

Nếu project đã có Wrapper, dùng Wrapper đó. Nếu vừa tạo thư mục từ các file trên và **chưa có Wrapper**, cần cài sẵn một bản Gradle tương thích rồi chạy một lần tại root:

```bash
gradle wrapper
```

Trên Linux/macOS:

```bash
./gradlew :app:run --quiet
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat :app:run --quiet
```

Với JDK/Gradle phù hợp, stdout do `Main.main` tạo là:

```text
Xin chào, Gradle!
```

`--quiet` giảm log Gradle, nhưng có thể vẫn có thông báo môi trường đặc biệt. Dòng trên là output của ứng dụng, không phải toàn bộ log công cụ.

### 6.3. Gradle đã đưa project nào vào compile classpath?

Cấu hình quan hệ của ví dụ:

```text
:app
  implementation -> :core
                       api -> :contracts

:app:compileClasspath
  |
  +--> :core
  +--> :contracts       (bắc cầu qua API variant của :core)
```

Điểm quan trọng: code `Main.java` **không** có `implementation project(':contracts')` trực tiếp trong `app/build.gradle`. Nó vẫn có thể import `demo.contracts.Greeting` vì `:core` **đã công khai** dependency ấy qua `api`.

Tác động lên task:

- `:contracts:compileJava` biên dịch record `Greeting`.
- `:core:compileJava` biên dịch `Greeter`, cần kiểu `Greeting`.
- `:app:compileJava` biên dịch `Main`, cũng nhìn thấy `Greeting` vì dependency bắc cầu.
- `:app:run` chạy ứng dụng với runtime classpath thích hợp.

Gradle dùng mô hình dependency và task/provider để chuẩn bị những output liên quan. Không nên đoán thứ tự chi tiết của mọi dòng log khi build song song; quan hệ đúng là project tiêu thụ phải có artifact/classes cần thiết trước khi biên dịch hoặc chạy.

## 7. Thí nghiệm cốt lõi: đổi `api` thành `implementation`

Trong `core/build.gradle`, **chỉ đổi một dòng**:

**Trước:**

```groovy
dependencies {
    api project(':contracts')
}
```

**Sau:**

```groovy
dependencies {
    implementation project(':contracts')
}
```

Vẫn giữ nguyên `Greeter.java` và `Main.java` của mục 6. Sau đó tại root, thử biên dịch lại phần ứng dụng:

```bash
./gradlew :app:clean :app:compileJava --console=plain
```

**Kết quả mong đợi: `:app:compileJava` thất bại**, vì `Main.java` import `demo.contracts.Greeting` nhưng `:contracts` không còn được cung cấp trên compile classpath của `:app` chỉ nhờ `implementation project(':core')`. Thông báo cụ thể tùy phiên bản JDK/Gradle, có thể gồm lỗi liên quan đến package `demo.contracts` không tồn tại hoặc không resolve được `Greeting`.

Trong khi đó, `:core` tự biên dịch thành công vì dependency `implementation project(':contracts')` vẫn có mặt trên **compile classpath của chính `:core`**. Nó chỉ không được **phơi bày bắc cầu** trên compile classpath của consumer.

**Phải hiểu đúng kết quả:** đổi `api` thành `implementation` không nhất thiết loại `:contracts` khỏi **runtime dependency** của `:app`. Java Library plugin thường công bố cả API và implementation dependency thông qua runtime variant. Vấn đề ở đây là compile visibility của consumer, không phải chứng minh artifact biến mất hoàn toàn khỏi mọi nơi.

### 7.1. Cách sửa thứ nhất: khôi phục API đúng theo hợp đồng

Nếu `Greeter.greet()` phải **tiếp tục trả về `Greeting`**, nên khôi phục:

```groovy
dependencies {
    api project(':contracts')
}
```

Rồi chạy:

```bash
./gradlew :app:clean :app:run --quiet
```

Output ứng dụng trở lại:

```text
Xin chào, Gradle!
```

Đây là lựa chọn phù hợp khi `Greeting` thực sự là một phần của hợp đồng công khai của `:core`.

### 7.2. Cách sửa thứ hai: thiết kế lại API để che kiểu nội bộ

Nếu muốn `Greeting` chỉ là chi tiết triển khai, có thể **đổi public signature** của `Greeter` để chỉ trả về `String`.

Thay nội dung `core/src/main/java/demo/core/Greeter.java` bằng:

```java
package demo.core;

import demo.contracts.Greeting;

public final class Greeter {
    public String greetMessage(String who) {
        Greeting greeting = new Greeting("Xin chào, " + who + "!");
        return greeting.text();
    }
}
```

Đổi `app/src/main/java/demo/app/Main.java` thành:

```java
package demo.app;

import demo.core.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(new Greeter().greetMessage("Gradle"));
    }
}
```

Lúc này `core/build.gradle` **giữ `implementation project(':contracts')`**. Chạy:

```bash
./gradlew :app:clean :app:run --quiet
```

Stdout vẫn là:

```text
Xin chào, Gradle!
```

Khác biệt nằm ở **API contract**: consumer không cần biết hay import `Greeting` nữa; `:core` che cách tạo và xử lý thông điệp. Đây thường là cách thiết kế tốt nếu `Greeting` không cần trở thành phần của API.

### 7.3. Cách thứ ba: consumer phụ thuộc trực tiếp, nhưng cân nhắc thiết kế

Một cách kỹ thuật để code `Main` ban đầu biên dịch khi `:core` dùng `implementation` là **app tự khai báo thêm**:

```groovy
dependencies {
    implementation project(':core')
    implementation project(':contracts')
}
```

Điều này hợp lệ khi `:app` **thực sự sử dụng trực tiếp** contract và chủ ý khai báo dependency đó. Tuy nhiên, nếu `:core` công bố `Greeting` trong public method nhưng không công bố dependency qua API, cấu hình của thư viện vẫn dễ gây khó chịu cho consumer khác. Đừng dùng cách thứ ba để che một API design sai khi phát hành thư viện cho nhiều người sử dụng.

**Kết luận thí nghiệm:** việc lựa chọn `api` hay `implementation` phải đi theo **hợp đồng public của thư viện**, không chỉ theo mong muốn “ít dependency hơn” hoặc chỉ vì một lần build bị lỗi.

## 8. `apiElements` và `runtimeElements`: nhìn sâu vào Gradle variant-aware resolution

Gradle không chỉ coi dependency là “tập JAR”. Với Java Library plugin, Gradle công bố những **variant** phù hợp nhu cầu của consumer:

- **API variant** (thường có cấu hình outgoing `apiElements`): mô tả những thành phần và dependency cần cho consumer **biên dịch**.
- **Runtime variant** (thường có `runtimeElements`): mô tả những thành phần và dependency cần cho consumer **chạy**.

Khi `:app:compileJava` cần dependency từ `:core`, Gradle chọn biến thể phù hợp compile usage của consumer. Khi `:app:run` cần runtime classpath, Gradle chọn biến thể phù hợp runtime usage.

Mô hình giản lược:

```text
:core
   |
   +--> apiElements
   |      |
   |      +--> api dependencies
   |      +--> API output/classes/artifact phù hợp
   |
   +--> runtimeElements
          |
          +--> api dependencies
          +--> implementation dependencies
          +--> runtimeOnly dependencies
          +--> runtime output/artifact phù hợp
```

Dấu mũi tên ở đây mô tả **loại dependency được công bố**, không phải mọi chi tiết metadata/attribute mà Gradle thực tế sử dụng. Gradle có thể có nhiều variant theo JVM target, thư viện classes/JAR, capabilities hoặc plugin khác.

Vì thế:

- **`api`** ảnh hưởng **public compile dependency graph** của consumer.
- **`implementation`** phục vụ nội bộ của thư viện nhưng vẫn được đưa vào **runtime graph** khi cần.
- **`runtimeOnly`** không cần cho compile nhưng có thể cần khi chạy.
- **`compileOnly`** có thể cần để biên dịch nhưng không tự được đưa vào runtime của consumer.

Không suy luận rằng Gradle luôn phải thực thi `:core:jar` để project `:app` biên dịch: lựa chọn variant và artifact có thể sử dụng thư mục classes/outputs nếu được công bố và phù hợp. Điều quan trọng là **dependency metadata và kết quả đầu vào được cung cấp chính xác**, không phải tên file trung gian.

### 8.1. Xem variant từ CLI

Tại root của project mục 6, thử:

```bash
./gradlew :core:outgoingVariants
```

Lệnh này giúp quan sát các variant mà project công bố, gồm `apiElements` và `runtimeElements` khi plugin tương ứng tạo chúng. Tùy phiên bản Gradle, output có thể trình bày attributes, capabilities, artifact và biến thể phụ; không cố học thuộc một log nguyên văn.

Để tập trung vào một variant (nếu phiên bản Gradle hỗ trợ tùy chọn đó):

```bash
./gradlew :core:outgoingVariants --variant apiElements
./gradlew :core:outgoingVariants --variant runtimeElements
```

Đọc kết quả cùng `core/build.gradle` để hiểu vì sao một dependency chỉ xuất hiện trong runtime variant hoặc xuất hiện ở cả API/runtime.

## 9. Đọc dependency graph trước và sau khi thay đổi

Hai lệnh đáng nhớ tại root:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
```

Với `:core` khai báo `api project(':contracts')`, compile graph của app thường cho thấy `:contracts` đi theo `:core`, chẳng hạn một cách biểu diễn giản lược:

```text
compileClasspath
\--- project :core
     \--- project :contracts
```

Với `:core` đổi thành `implementation project(':contracts')`, compile graph của app không còn cần hiển thị `:contracts` như transitive compile dependency qua `:core`:

```text
compileClasspath
\--- project :core
```

Nhưng runtime graph của app vẫn có thể gồm:

```text
runtimeClasspath
\--- project :core
     \--- project :contracts
```

Đây là các **sơ đồ mô tả cấu trúc phụ thuộc kỳ vọng** chứ không phải cam kết output dòng lệnh từng ký tự; Gradle có thể in thêm metadata variant, đánh dấu constraint hoặc trình bày tree khác.

Dùng `dependencyInsight` khi cần biết vì sao một module được chọn:

```bash
./gradlew :app:dependencyInsight --configuration compileClasspath --dependency contracts
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency contracts
```

Điều quan trọng là kiểm tra **đúng configuration**. Một module xuất hiện trong `runtimeClasspath` không tự chứng minh nó cũng có trong `compileClasspath`. Ngược lại, `compileOnly` có thể xuất hiện khi biên dịch nhưng không xuất hiện trong runtimeClasspath.

Nếu cần biết project path nào đang có, chạy:

```bash
./gradlew projects
```

Task `projects` giúp xác nhận `:contracts`, `:core` và `:app` đã được settings include. Nếu Gradle báo không tìm thấy `project ':core'`, hãy kiểm tra file settings và tên project trước khi nghi repository Maven.

## 10. Những dependency configuration liên quan đến API

Ngoài `api` và `implementation`, người học sẽ gặp:

| Cấu hình | Mục đích chính | Có được công khai cho consumer compile theo Java Library API? |
| --- | --- | --- |
| `api` | Dependency thuộc hợp đồng public của thư viện | Có |
| `implementation` | Dependency cần để biên dịch/triển khai nội bộ | Không, dù thường có ở runtime |
| `compileOnly` | Chỉ có mặt để biên dịch project hiện tại | Không |
| `compileOnlyApi` | Compile-only dependency cần công bố cho consumer biên dịch | Có, nhưng không tự thêm vào runtime |
| `runtimeOnly` | Chỉ cần ở runtime | Không |
| `testImplementation` | Dependency cho mã test của chính project | Không |
| `testRuntimeOnly` | Dependency chỉ cần khi chạy test của project | Không |

Đừng dùng `api` cho thư viện JUnit chỉ vì muốn mọi module viết test. Mỗi project tự quản lý test dependencies phù hợp, hoặc nhóm có thể áp dụng một **convention plugin** để cấu hình test thống nhất. Test dependency của `:core` không tự trở thành API công khai của `:core`.

### 10.1. `api` không làm mọi dependency “xuất hiện ở tất cả project”

`api` chỉ ảnh hưởng **consumer của project/library đó** theo các variant tương ứng. Ví dụ `:reports` không phụ thuộc vào `:core` thì không tự nhận `:contracts` chỉ vì `:core` dùng `api`.

Tương tự, nếu `:app` chỉ là ứng dụng cuối chuỗi, nó không cần `java-library` để tự cung cấp API bắc cầu cho một project khác. Dùng `implementation project(':core')` trong ứng dụng là hợp lý; việc `:core` dùng `api` hay `implementation` được quyết định ở **library**.

### 10.2. `api` không quyết định Java access modifier

Một class `package-private` trong `:contracts` vẫn chịu quy tắc truy cập Java. `api project(':contracts')` không biến class đó thành public. Cơ chế Gradle kiểm soát **classpath availability**; Java compiler kiểm soát **type access**, package visibility, module system và ngữ nghĩa ngôn ngữ.

### 10.3. `implementation` không phải biện pháp bảo mật

Nếu một class nằm trong runtime artifact, code runtime hoặc công cụ phân tích vẫn có thể nhìn thấy nó trong nhiều bối cảnh. `implementation` không mã hóa JAR, không ẩn bytecode và không ngăn reverse engineering. Nó chỉ mô tả **hợp đồng dependency**, đặc biệt ở compile classpath của consumer.

## 11. Vì sao không nên đặt tất cả dependency thành `api`?

Một giải pháp “cho chắc” là dùng `api` với mọi dependency của thư viện. Cách này có thể khiến code consumer biên dịch dễ hơn trước mắt, nhưng có hệ quả dài hạn:

1. **Lộ chi tiết triển khai:** consumer có thể bắt đầu import những kiểu đáng ra chỉ thuộc code nội bộ của thư viện.
2. **Classpath biên dịch phình to:** consumer thấy thêm nhiều dependency không cần thiết.
3. **Tăng ảnh hưởng của thay đổi:** sửa dependency API có thể khiến nhiều project tiêu thụ phải xem xét lại phần biên dịch liên quan.
4. **Gia tăng ràng buộc nâng cấp:** consumer có thể vô tình phụ thuộc trực tiếp vào version hoặc kiểu mà library không hề định duy trì làm public contract.
5. **Xung đột dependency:** nhiều API transitively công bố các module/variant có thể khiến graph khó kiểm soát hơn.
6. **Giảm tính đóng gói:** thư viện trở thành điểm lan truyền mọi dependency ra toàn bộ hệ thống.

Ngược lại, dùng `implementation` cho một dependency mà **public signature cần đến** khiến consumer gặp lỗi compile hoặc phải khai báo “vá” dependency trực tiếp. Vì vậy không có quy tắc đúng là “luôn implementation” hay “luôn api”; lựa chọn phải dựa trên public API thực.

Một nguyên tắc dễ áp dụng:

> **Chỉ công khai những dependency mà người dùng thư viện thực sự cần để biên dịch và sử dụng hợp đồng public được thiết kế.** Những gì chỉ phục vụ cách triển khai bên trong nên để ở `implementation`.

## 12. Tác động đến incremental compilation và tốc độ build

Khi build nhiều project lớn, Gradle cố gắng tránh thực hiện lại công việc không cần thiết. Việc phân tách `api`/`implementation` hỗ trợ mô hình này:

- Sự thay đổi trong **chi tiết implementation** không nhất thiết yêu cầu mọi consumer được biên dịch lại nếu API nhìn từ consumer vẫn tương thích và các điều kiện theo dõi của Gradle cho phép.
- Một sự thay đổi trong **public API** có thể ảnh hưởng đến consumer và kích hoạt công việc liên quan.
- Một dependency được công bố qua `api` có thể mở rộng phạm vi compile classpath của consumer hơn mức cần thiết.

Không nên hứa rằng chỉ thay một từ khóa thành `implementation` sẽ luôn giảm thời gian build một con số cố định. Còn nhiều yếu tố khác: loại plugin, cách biên dịch, Gradle version, annotation processor, cache, thay đổi file nguồn, parallel execution và cấu hình build.

Để quan sát thực tế:

```bash
./gradlew :app:compileJava --console=plain
./gradlew :app:compileJava --console=plain
```

Ở lần hai, một số task có thể `UP-TO-DATE`. Sau khi sửa public signature hoặc implementation, hãy quan sát task nào chạy lại với `--info`. Đây là cách học tác động của dependency metadata bằng chứng cứ, thay vì dựa trên cảm giác.

## 13. Project dependency, build order và task graph

Khi `:app` phụ thuộc `:core`, `:core` lại phụ thuộc `:contracts`, Gradle hiểu cần chuẩn bị output của những module liên quan.

```text
:contracts:compileJava
          |
          v
:core:compileJava
          |
          v
:app:compileJava
          |
          v
:app:run
```

Sơ đồ là cách nhìn đơn giản khi các task thực sự phải tạo output lần đầu. Trong một lần build đã có cache hoặc output cập nhật, một số task có thể `UP-TO-DATE` hoặc được xử lý theo cách khác. Gradle có thể dùng các variant/class directories và những task chuyên biệt khác, nên danh sách task thật không nhất thiết chỉ có bốn dòng trên.

**Không cần tự thêm một chuỗi `dependsOn` thủ công chỉ để biên dịch project dependency**:

```groovy
dependencies {
    implementation project(':core')
}
```

Cấu hình project dependency đã đưa quan hệ dữ liệu và những artifact/provider thích hợp vào mô hình Gradle. Khi task tiêu thụ compile classpath, Gradle biết nó cần output của project khác. Chèn `dependsOn(':core:build')` vào `:app:compileJava` một cách tùy tiện có thể thực hiện dư test/packaging và tạo vòng hoặc quan hệ ngoài ý định.

### 13.1. Đừng tạo vòng phụ thuộc

Ví dụ sai:

```text
:app -> :core -> :contracts -> :app
```

Một vòng dependency khiến Gradle không thể tạo thứ tự hợp lệ cho nhiều task và có thể báo circular dependency. Đây thường là dấu hiệu trách nhiệm module chưa được tách tốt.

Cách xử lý thường dùng:

- Tách hợp đồng/chung kiểu sang project `:contracts` độc lập.
- Cho module cấp cao phụ thuộc module cấp thấp, tránh module thấp phụ thuộc ngược module cao.
- Di chuyển interface sang module trung lập, triển khai interface ở module khác và inject implementation khi chạy.
- Xem lại các dependency dùng chỉ để test, hoặc tách test fixture module nếu thực sự cần.

Không chữa vòng bằng cách đổi `api` thành `implementation` rồi mong Gradle tự phá vòng. Cả hai vẫn là **dependency từ project này sang project kia**, chỉ khác phạm vi classpath công bố.

## 14. Kotlin DSL: cú pháp tương đương và import đúng

Ví dụ `core/build.gradle.kts` tương đương:

```kotlin
plugins {
    id("java-library")
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

dependencies {
    api(project(":contracts"))
}
```

Ví dụ `app/build.gradle.kts`:

```kotlin
plugins {
    application
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

dependencies {
    implementation(project(":core"))
}

application {
    mainClass.set("demo.app.Main")
}
```

Ví dụ `settings.gradle.kts`:

```kotlin
rootProject.name = "project-api-demo"
include("contracts", "core", "app")
```

Các file Java ở mục 6 giữ nguyên, chỉ thay DSL Gradle. Đừng đặt cả `build.gradle` và `build.gradle.kts` với cấu hình trái ngược trong cùng thư mục rồi giả định Gradle gộp chúng. Chọn một DSL cho từng script một cách nhất quán.

**Lưu ý về accessor:** `api(...)` là dependency configuration do Java Library plugin cung cấp và có thể sử dụng bằng Kotlin DSL khi plugin đã được khai báo phù hợp. Nếu một project chưa áp dụng `java-library`, Kotlin có thể báo `Unresolved reference: api`. Đó không phải lỗi của dependency project `:contracts`, mà là **configuration `api` chưa tồn tại** trong model hiện tại.

### 14.1. Nếu viết build logic tùy chỉnh

Trong plugin hoặc mã cấu hình chung, có thể dùng API Gradle tường minh:

```kotlin
dependencies.add("api", project(":contracts"))
```

Đây là **đoạn minh họa** chỉ hợp lệ khi đang ở ngữ cảnh có `dependencies`, `project(...)` phù hợp và Java Library plugin đã tạo configuration `api`. Cách dùng bằng chuỗi không tự khởi tạo configuration thiếu. Với build script thông thường, cú pháp `api(project(":contracts"))` dễ đọc và cho IDE kiểm tra tốt hơn.

## 15. Module lồng nhau và project path

Không phải project nào cũng ở ngay dưới root:

```text
platform/
├── settings.gradle
└── services/
    ├── billing/
    └── catalog/
```

Settings có thể dùng:

```groovy
rootProject.name = 'platform'
include ':services:billing'
include ':services:catalog'
```

Một project khác muốn phụ thuộc vào billing có thể khai báo:

```groovy
dependencies {
    implementation project(':services:billing')
}
```

Path `:services:billing` là đường dẫn trong **model project Gradle**, không nhất thiết là một tọa độ Maven. Theo mặc định, Gradle ánh xạ vào thư mục tương ứng, nhưng settings có thể tùy biến `projectDir` cho project path.

Nếu Gradle báo không tìm thấy project path, đừng ngay lập tức thêm repository Maven. Hãy chạy `./gradlew projects` và đọc cấu hình `include`. Vấn đề có thể chỉ là typo trong project path hoặc project chưa được đưa vào build.

## 16. Công bố thư viện ra ngoài build: ý nghĩa của API metadata

Khi các project nằm trong cùng multi-project build, Gradle có thể sử dụng variant-aware project dependency để biết mối quan hệ `api`/`implementation`. Khi phát hành một thư viện cho người khác qua Maven repository, metadata đóng vai trò tương tự.

Ví dụ thư viện `:core` dùng:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}
```

Cấu hình publishing cần thêm group, version, publication và repository phù hợp nếu thực sự muốn phát hành. Đây **không phải** phần cần có để chạy ví dụ ba project ở mục 6.

Với `java-library`, Gradle có thể công bố thông tin API/runtime variants qua **Gradle Module Metadata** cho consumer Gradle khi publication được cấu hình đúng. Maven POM có mô hình scope riêng, không biểu diễn mọi thuộc tính variant của Gradle một cách hoàn toàn tương đương.

Vì vậy:

- **Trong cùng build:** dùng project dependency và Gradle variants.
- **Qua repository Maven:** dùng tọa độ đã publish; metadata quyết định consumer nhận những dependency nào.
- **Khi publish:** xem kỹ API/runtime dependency graph trước khi phát hành, vì thay đổi `api` có thể ảnh hưởng tới consumer ngoài repository của bạn.

Đừng hiểu `api` là lệnh tự động upload một artifact lên Maven. Nó là **dependency configuration**, không phải lệnh publishing.

## 17. Những vấn đề thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `Project with path ':core' could not be found` | Chưa `include` project hoặc sai path | Sửa `settings.gradle`, kiểm tra `./gradlew projects` |
| `Could not find method api()` trong Groovy DSL | Project không có configuration `api` | Áp dụng `java-library` nếu đây là library, hoặc dùng configuration đúng |
| `Unresolved reference: api` trong Kotlin DSL | `api` accessor chưa có do plugin/model | Dùng `id("java-library")` đúng chỗ, đồng bộ cấu hình |
| `:app` không import được `Greeting` | `:core` dùng `implementation` nhưng app đang cần kiểu thuộc `:contracts` | Dùng `api` nếu đó là public contract, hoặc khai báo direct dependency nếu chủ ý |
| App compile được nhưng runtime thiếu class | Có dependency chỉ `compileOnly` hoặc package/runtime dependency sai | Kiểm tra `runtimeClasspath` và loại dependency |
| `:core` compile lỗi dù app đúng | `:core` chưa khai báo dependency trực tiếp mà code core sử dụng | Thêm dependency vào chính `:core` |
| API compile graph quá lớn | Thư viện dùng `api` cho quá nhiều chi tiết nội bộ | Thu hẹp sang `implementation` khi không lộ public type |
| Consumer lệ thuộc thư viện triển khai | Code consumer import lớp transitively available nhưng không phải public contract | Thiết kế lại API, khai báo dependency trực tiếp nếu cần |
| Task compile chạy lặp nhiều | Thay đổi ABI/classpath/plugin/annotation processor hoặc chưa bật tối ưu phù hợp | Dùng `--info`, đọc task states, xem dependency graph |
| Circular dependency giữa project | Các project phụ thuộc vòng | Tách contract/interface, điều chỉnh hướng dependency |
| Lệnh `:app:build` không tìm thấy | Sai project path hoặc plugin/task không tạo task mong muốn | Kiểm tra `projects`, `:app:tasks --all` |
| `:contracts` có mặt ở runtime nhưng không ở compile graph của app | `:core` khai báo `implementation` | Đây là đúng semantics; xem public API cần gì |
| Package-private class không import được dù `api` | Java access modifier không cho phép | Sửa thiết kế visibility, không phải dependency configuration |
| Đã tạo `jar` nhưng project khác không thấy kiểu mới | Sai project path, package, dependency variant hoặc chưa dùng output mới | Kiểm tra settings, graph, source set, compiled output |
| Muốn dùng một build ngoài bằng `project(':other')` | `project(...)` chỉ trỏ project của build hiện tại | Xem composite build `includeBuild` hoặc published module dependency |
| Thêm `api` để “bảo mật” code | `api`/`implementation` không điều khiển bảo mật bytecode | Dùng cơ chế bảo mật riêng, thiết kế API chuẩn |

### 17.1. Quy trình debug ngắn

1. **Xác định project nào thất bại:** `:contracts:compileJava`, `:core:compileJava` hay `:app:compileJava`?
2. **Kiểm tra settings:** root có `include` đúng project path chưa?
3. **Kiểm tra plugin:** module đó là Java library hay application? Có `api` configuration không?
4. **Kiểm tra code consumer:** đang import trực tiếp kiểu nào và kiểu đó thuộc project nào?
5. **Kiểm tra public signature:** dependency đó có mặt trong phương thức/field/interface được công khai hay chỉ ở implementation?
6. **So sánh graph:** `compileClasspath` và `runtimeClasspath` của đúng consumer.
7. **Xác minh lại bằng lệnh thật:** chạy `:app:clean :app:compileJava` rồi `:app:run`.
8. **Chỉ sau đó mới cân nhắc tuning:** tránh thêm `api` cho mọi dependency chỉ để dập một lỗi cụ thể.

## 18. Bài tập thực hành mở rộng

### Bài tập A — đo compile visibility bằng một thay đổi

Dùng project mục 6, ghi lại output ứng dụng với `api project(':contracts')`. Đổi sang `implementation project(':contracts')`, chạy `:app:clean :app:compileJava`, và giải thích vì sao app thất bại dù core vẫn biên dịch.

**Đáp án định hướng:** chữ ký public của `Greeter.greet` trả `Greeting` nhưng kiểu `Greeting` đã bị che khỏi compile classpath bắc cầu của app. Lỗi không nằm ở nội dung chuỗi lời chào hay lệnh `run`.

### Bài tập B — xem hai graph khác nhau

Chạy:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
```

So sánh trước/sau khi đổi `api` thành `implementation` trong core. Vì sao runtime graph vẫn có thể chứa contracts dù compile graph của app không còn bắc cầu tới contracts?

### Bài tập C — đổi thiết kế public API

Thay `Greeter.greet` trả `Greeting` bằng `Greeter.greetMessage` trả `String` như mục 7.2. Giữ `implementation project(':contracts')` trong core. Viết lại app mà không import `Greeting` và chạy ứng dụng. Giải thích cách module core giấu chi tiết triển khai trong API.

### Bài tập D — thêm một thư viện bên ngoài

Trong `:core`, muốn dùng `org.apache.commons.lang3.StringUtils` chỉ bên trong `Greeter`, hãy thêm repository Maven Central thích hợp và:

```groovy
dependencies {
    api project(':contracts')
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

Giải thích vì sao `commons-lang3` nên là `implementation` nếu không có kiểu nào của thư viện đó xuất hiện trong public API của `:core`. Kiểm tra compile classpath của app để thấy thư viện này không tự phải là API dependency.

### Bài tập E — test dependency không được lộ

Trong `:core`, thêm JUnit Jupiter bằng `testImplementation` và cấu hình `test` phù hợp. Tại sao không nên chuyển JUnit thành `api` chỉ để app có thể viết test? Mỗi module cần quản lý test classpath của nó thế nào?

### Bài tập F — thử một project path lồng nhau

Đổi `:contracts` thành `:shared:contracts` bằng cách điều chỉnh settings, thư mục/projectDir và dependency. Chạy `projects`, sửa `project(':contracts')` thành `project(':shared:contracts')`, rồi build. Tại sao chỉ đổi tên thư mục mà không sửa settings/dependency là chưa đủ?

### Bài tập G — vòng phụ thuộc

Giả lập bằng sơ đồ `:app -> :core -> :contracts -> :app`. Không cần chạy build lỗi. Hãy đề xuất cách tách một interface trung lập hoặc đảo hướng phụ thuộc để graph không còn chu trình.

### Bài tập H — xem outgoing variants

Chạy:

```bash
./gradlew :core:outgoingVariants
./gradlew :app:dependencyInsight --configuration compileClasspath --dependency contracts
```

Ghi lại sự khác biệt giữa thông tin producer `:core` công bố và graph mà consumer `:app` yêu cầu. Những dữ liệu này liên quan thế nào đến việc Gradle chọn API variant?

### Câu hỏi tự kiểm tra

1. `project(':core')` trỏ đến đâu, khác external module dependency thế nào?
2. Nếu root `settings.gradle` không `include 'core'` thì `project(':core')` có tự tìm trên Maven Central không?
3. `java-library` cung cấp thêm khả năng gì cho việc phân tách API/implementation?
4. Nếu public method của core trả `demo.contracts.Greeting`, vì sao contracts thường phải là `api` dependency?
5. Với `implementation project(':contracts')` ở core, contracts có còn được dùng để biên dịch chính core không?
6. Vì sao runtime classpath của app có thể chứa contracts dù compile classpath của app không chứa?
7. Khi core chỉ dùng Greeting bên trong và trả `String`, `implementation` có phù hợp hơn không?
8. `apiElements` và `runtimeElements` mô tả hai loại nhu cầu của consumer như thế nào?
9. `compileOnlyApi` khác `api` về runtime ở đâu?
10. Vì sao một application module thường chỉ cần `implementation project(':core')`, không cần `api`?
11. Việc đổi tất cả dependency thành `api` có tác hại gì cho độ đóng gói và build performance?
12. `api` có tự biến một class `package-private` thành public không?
13. Gradle có nhất thiết phải tạo JAR của core trước khi biên dịch app không?
14. `compileClasspath` và `runtimeClasspath` giúp debug hai loại lỗi khác nhau thế nào?
15. Vì sao không nên tạo vòng project dependency?
16. Multi-project `include 'core'` khác composite build `includeBuild(...)` thế nào?
17. Vì sao `implementation` không phải công cụ bảo mật bytecode?
18. Cần kiểm tra gì khi app import được kiểu từ một dependency transitive nhưng thư viện chủ không hề định công bố kiểu đó?

**Ghi nhớ:** Trong multi-project Gradle, `project(':module')` tạo phụ thuộc giữa những project đã được khai báo trong settings. Với thư viện dùng `java-library`, **`api` công bố dependency cần thiết để consumer biên dịch public contract**, còn **`implementation` giữ dependency ở phạm vi triển khai của thư viện và runtime phù hợp nhưng không truyền nó bắc cầu qua API compile**. Hãy chọn dựa trên **chữ ký public thật của mã Java**, kiểm tra bằng `compileClasspath`/`runtimeClasspath` và dùng task dependency/variant resolution của Gradle thay vì tự nối đường dẫn JAR thủ công.