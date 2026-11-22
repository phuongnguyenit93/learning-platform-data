# Quản lý phiên bản đồng bộ bằng BOM hoặc platform

Trong dự án Java có nhiều module và nhiều thư viện, việc “nâng một dependency lên bản mới” thường không đơn giản là sửa một con số. Một framework có thể phụ thuộc vào hàng chục module cùng họ; HTTP client, JSON serializer, logging, observability và database driver lại có nhiều dependency bắc cầu. Nếu các module được nâng độc lập, classpath có thể chứa những phiên bản chưa từng được kiểm thử cùng nhau. Hệ quả điển hình là source vẫn compile nhưng runtime phát sinh `NoSuchMethodError`, `NoClassDefFoundError`, `ClassCastException`, `ServiceConfigurationError` hoặc hành vi khác dự kiến.

**BOM (Bill of Materials)** trong Maven và **platform** trong Gradle là các cơ chế khai báo bộ phiên bản được quản lý tập trung. Chúng giúp các module chọn một tổ hợp version có chủ đích, dễ nâng cấp và dễ tái lập. Tuy nhiên, BOM không phải một JAR chứa tất cả thư viện, không tự tải mọi dependency và cũng không bảo đảm rằng mọi version được quản lý đều tương thích với JDK, hệ điều hành hoặc môi trường production của ứng dụng.

Bài này trình bày nguyên tắc đồng bộ version, cách áp dụng BOM trên Maven và platform trên Gradle, các quy tắc ưu tiên version, những khác biệt quan trọng giữa hai hệ build và quy trình kiểm chứng dependency graph khi thực hiện **Java Advance Compatibility Migration**.

## 1. Vấn đề cần giải quyết: version drift trong dependency graph

### 1.1. Direct dependency và transitive dependency

Giả sử ứng dụng dùng ba module:

```text
order-service
├── acme-web-client
│   ├── json-core       2.4
│   └── http-core       5.1
├── acme-data-client
│   ├── json-core       2.2
│   └── metrics-api     1.8
└── acme-security
    ├── http-core       5.0
    └── metrics-api     1.9
```

Các số trên chỉ là ví dụ giả định. Dự án có thể khai báo ba dependency trực tiếp nhưng runtime graph chứa nhiều yêu cầu phiên bản khác nhau cho cùng module. Build tool phải giải quyết xung đột và chọn một version trên từng classpath.

Khi một thư viện được compile với `json-core 2.4` nhưng runtime chọn `json-core 2.2`, nó có thể gọi một method chưa tồn tại trong bản 2.2. Khi framework mới yêu cầu `http-core 5.1` nhưng một ràng buộc khác giữ bản 5.0, lỗi có thể chỉ xuất hiện khi request cụ thể chạy.

Không phải lúc nào hai version khác nhau cũng gây lỗi. Nhưng tổ hợp chưa được kiểm thử là một **rủi ro cần xác minh**, không nên mặc định tương thích chỉ vì build hoàn tất.

### 1.2. Đồng bộ không nhất thiết là “mọi module cùng số version”

Một họ thư viện thường phát hành nhiều artifact cùng nhịp và muốn dùng cùng release line. Nhưng nhiều BOM quản lý các artifact từ nhiều nhà cung cấp, với version khác nhau:

| Artifact giả định | Version do BOM quản lý | Lý do |
|---|---|---|
| `acme-core` | `2.7.0` | Thuộc nhóm thư viện nội bộ |
| `acme-http` | `2.7.0` | Cùng release line với core |
| `json-databind` | `2.4.3` | Theo bộ JSON đã được kiểm thử |
| `metrics-api` | `1.9.2` | Theo observability stack |
| `jdbc-driver` | `4.6.1` | Theo database/server support |

Các version chỉ minh họa. Mục tiêu của alignment là **một tổ hợp phiên bản nhất quán và đã được chấp thuận**, không phải ép mọi artifact về cùng version string.

### 1.3. Rủi ro đặc biệt trong migration JDK

Khi nâng từ Java 17 lên Java 21, một framework có thể yêu cầu nâng major version, kéo theo nhiều thư viện mới. Nếu chỉ nâng một số artifact, ứng dụng có thể gặp:

- API mới không có trong dependency runtime được chọn.
- Thư viện bytecode/agent chưa hiểu class-file major version của JDK đích.
- Annotation processor và runtime library không đồng bộ.
- HTTP/JDBC/ORM driver không phù hợp với framework hoặc server.
- Hai phiên bản cùng họ cùng có mặt do shadow/shading hoặc class loader.
- Thư viện dùng namespace `javax.*` nhưng framework đã chuyển sang `jakarta.*`.
- API compile pass nhưng provider/service metadata runtime không khớp.

BOM/platform giúp quản lý **version graph**, nhưng cần kết hợp với compatibility matrix theo JDK và runtime test.

## 2. BOM trong Maven thực chất là gì?

### 2.1. BOM là một POM có dependencyManagement

Maven BOM thường là một artifact có `packaging = pom`, định nghĩa các version được quản lý trong phần `<dependencyManagement>`.

Ví dụ BOM minh họa:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.platform</groupId>
    <artifactId>example-dependencies</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>example-core</artifactId>
                <version>2.7.0</version>
            </dependency>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>example-http</artifactId>
                <version>2.7.0</version>
            </dependency>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>example-observation</artifactId>
                <version>1.9.2</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Tọa độ và version ở ví dụ là giả định để giải thích cơ chế. Không coi chúng là package có thật hay một bộ version đã được nhà cung cấp xác minh.

BOM định nghĩa **version và có thể cả metadata dependency management**, không tự làm ba thư viện xuất hiện trên application classpath. Consumer vẫn phải khai báo dependency cần sử dụng, hoặc dependency xuất hiện qua quan hệ bắc cầu.

### 2.2. Import BOM vào dự án Maven

POM consumer:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.app</groupId>
    <artifactId>order-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <example.platform.version>1.0.0</example.platform.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example.platform</groupId>
                <artifactId>example-dependencies</artifactId>
                <version>${example.platform.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>example-core</artifactId>
        </dependency>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>example-http</artifactId>
        </dependency>
    </dependencies>
</project>
```

Tại đây Maven biết version của `example-core` và `example-http` từ BOM. Các dependency trực tiếp không cần khai báo version lặp lại.

**Lưu ý cú pháp:** BOM được import trong `dependencyManagement` với `type=pom` và `scope=import`. Không nên đặt BOM như một dependency JAR thông thường rồi mong Maven tự áp dụng dependency management.

### 2.3. BOM không tương đương parent POM

Một Maven parent POM có thể quản lý:

- Plugin versions qua `pluginManagement`.
- Build profiles, compiler settings, repositories và properties.
- Dependency versions qua `dependencyManagement`.
- Các cấu hình build chung khác.

Một BOM thường tập trung vào **dependency management** và được import, không cần quan hệ parent. Maven project chỉ có một direct parent, nhưng có thể import nhiều BOM. Cần quản lý xung đột giữa chúng.

| Cơ chế Maven | Nội dung chính | Dùng khi nào |
|---|---|---|
| `<parent>` | Kế thừa cấu hình build và management | Dự án thuộc cấu trúc build chung |
| BOM import | Nhập bộ version dependency | Dùng thư viện/framework cùng stack |
| `<dependencyManagement>` | Quy định quản lý dependency | Parent/BOM/module quản lý version |
| `<dependencies>` | Thêm dependency vào project graph | Khi code/build cần thư viện |
| `<pluginManagement>` | Quản lý version/config plugin | Kiểm soát compiler/test/package plugins |
| `<build><plugins>` | Kích hoạt hoặc cấu hình plugin | Khi lifecycle cần plugin |

Import một BOM không tự import compiler plugin, test plugin hoặc JVM flags của parent framework. Khi nâng JDK, phải rà soát các lớp này riêng.

## 3. Maven: thứ tự ưu tiên và dependency mediation

### 3.1. Dependency management và version khai báo trực tiếp

Giả sử BOM quản lý:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>example-core</artifactId>
    <version>2.7.0</version>
</dependency>
```

Consumer khai báo không có version:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>example-core</artifactId>
</dependency>
```

Maven dùng version được quản lý. Nếu consumer khai báo version tường minh:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>example-core</artifactId>
    <version>2.5.0</version>
</dependency>
```

thì đây là một thay đổi có chủ ý ở dependency declaration của consumer, và không nên mặc định BOM sẽ tự sửa nó thành 2.7.0.

Quy tắc chi tiết còn phụ thuộc dependency ở cấp nào, scope, type/classifier và mô hình kế thừa. Khi điều tra, **xem effective POM và resolved dependency tree**, không suy ra chỉ từ một đoạn XML.

### 3.2. Maven không chọn version giống Gradle

Maven có cơ chế dependency mediation truyền thống: khi có nhiều đường phụ thuộc yêu cầu version khác nhau, quy tắc thường được mô tả bằng **nearest definition**; nếu cùng độ sâu có thể xét thứ tự khai báo. Dependency management trong POM hiện tại có thể quyết định version được dùng cho dependency bắc cầu theo các quy tắc quản lý của Maven.

Không nên hiểu “BOM quản lý version” là một cơ chế cứng giống forced version cho mọi trường hợp. Các khai báo direct với version tường minh, management ở các cấp và cấu trúc dependency graph có thể làm kết quả khác dự tính.

Một sơ đồ minh họa:

```text
order-service
├── client-a
│   └── library-x:1.0
└── client-b
    └── library-x:2.0
```

Nếu không có dependency management phù hợp, Maven áp dụng mediation dựa trên dependency graph. Nếu BOM/management của consumer quản lý `library-x:2.0` và phù hợp trường hợp đó, resolved result có thể được chuẩn hóa về version 2.0.

### 3.3. Nhiều BOM quản lý cùng một artifact

Giả sử project import hai BOM và cả hai cùng quản lý version `library-x`. Trong Maven, thứ tự import có thể quyết định version nào được sử dụng cho các entry trùng nhau; trong trường hợp các BOM imported có cùng dependency được quản lý, **BOM import xuất hiện trước thường thắng** khi không có khai báo quản lý trực tiếp ghi đè.

Ví dụ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>platform-a</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>platform-b</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Nếu có tranh chấp, cách rõ nhất là khai báo một management entry tường minh tại project nơi cần điều chỉnh và ghi lại lý do. Tuy nhiên, override này có thể phá ma trận version đã được framework kiểm thử, nên phải chạy test và lưu quyết định.

Không dựa vào trực giác “BOM import sau luôn ghi đè BOM trước” vì đó không phải quy tắc chung đúng cho Maven.

### 3.4. Parent inheritance và local management

Một POM con có thể kế thừa dependency management từ parent. Các entry quản lý được khai báo tại POM con thường có thể override entry inherited tương ứng. Khi parent, BOM imported và local management cùng tồn tại, cần xem **effective POM** để xác nhận kết quả.

Lệnh khảo sát:

```bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dverbose
```

Trong một số phiên bản plugin, output `dependency:tree -Dverbose` có cách thể hiện omitted/conflict khác nhau. Không dùng text output như nguồn chân lý duy nhất: kiểm tra plugin version và resolved artifact thực tế khi cần.

### 3.5. BOM không quản lý plugin Maven

Một điểm hay bị bỏ sót: `dependencyManagement` quản lý dependency project, còn compiler/surefire/failsafe/shade/codegen plugin thuộc **plugin resolution và pluginManagement**.

Ví dụ:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>${compiler.plugin.version}</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${surefire.plugin.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Các property version cần được khai báo ở parent/project theo chính sách build. Khi nâng Java 17 → 21, BOM dependency tốt vẫn không cứu được một Maven plugin cũ không chạy trên JDK build.

## 4. Gradle platform là gì?

Gradle có **platform dependencies** để tham gia version alignment trên graph. Một Gradle platform có thể được lấy từ:

- Một Maven BOM được import qua `platform("group:artifact:version")`.
- Một project dùng `java-platform` plugin.
- Một platform component có metadata dành riêng cho Gradle.

Về mặt ý tưởng, platform chứa **dependency constraints**, chứ không tự tải toàn bộ implementation JAR vào application runtime.

### 4.1. Import Maven BOM trong Gradle

Ví dụ Groovy DSL:

```groovy
dependencies {
    implementation platform("com.example.platform:example-dependencies:1.0.0")

    implementation "com.example:example-core"
    implementation "com.example:example-http"

    testImplementation platform(
        "com.example.platform:example-dependencies:1.0.0"
    )
}
```

Version của hai dependency được quản lý bằng platform ở configuration tương ứng. Đây là minh họa artifact giả định.

Gradle có resolution strategy và graph semantics khác Maven, nên import **cùng một BOM** không luôn bảo đảm kết quả resolved graph tuyệt đối giống Maven trong mọi trường hợp. Phải kiểm tra với `dependencies` và `dependencyInsight`.

### 4.2. Kotlin DSL tương đương

```kotlin
dependencies {
    implementation(platform("com.example.platform:example-dependencies:1.0.0"))

    implementation("com.example:example-core")
    implementation("com.example:example-http")

    testImplementation(
        platform("com.example.platform:example-dependencies:1.0.0")
    )
}
```

Dù viết Groovy hay Kotlin DSL, điểm cốt lõi là platform phải tham gia đúng configuration nơi dependency được resolve.

### 4.3. Import platform không đồng nghĩa enforce tuyệt đối

Với Gradle, platform thông thường đưa các ràng buộc version vào quá trình resolution. Khi có dependency khác yêu cầu version cao hơn, **Gradle conflict resolution có thể chọn version khác với giá trị được platform gợi ý/quản lý** tùy metadata và constraints.

Vì vậy:

```groovy
implementation platform("com.example.platform:example-dependencies:1.0.0")
```

không có nghĩa mọi artifact trong BOM bị khóa bất biến bằng mọi giá. Để biết version cuối cùng, cần xem graph.

Điều này cũng giúp phân biệt “đồng bộ theo bộ version” với “khóa chính xác toàn bộ graph”. Hai mục tiêu cần các công cụ bổ sung khác nhau.

## 5. Gradle: platform và enforcedPlatform khác nhau thế nào?

### 5.1. platform: ưu tiên tương thích, không cưỡng chế toàn bộ

Ví dụ:

```groovy
dependencies {
    implementation platform("com.example.platform:example-dependencies:1.0.0")
    implementation "com.example:example-core"
}
```

Đây là lựa chọn mặc định hợp lý khi muốn dùng version alignment từ BOM trong ứng dụng hoặc thư viện, sau đó xác minh kết quả resolution. Các constraint có thể tác động khác nhau theo metadata, strictness và dependency request của graph.

### 5.2. enforcedPlatform: ràng buộc mạnh hơn

Gradle có:

```groovy
dependencies {
    implementation enforcedPlatform(
        "com.example.platform:example-dependencies:1.0.0"
    )
    implementation "com.example:example-core"
}
```

`enforcedPlatform` ép các version được quản lý theo nền tảng ở mức mạnh hơn. Nó có thể hữu ích khi một application cần cưỡng chế tổ hợp cụ thể, nhưng gây rủi ro nếu được xuất ra cho consumer khác: enforced constraints có thể **lan theo dependency graph** và ghi đè lựa chọn của consumer.

Vì thế, đừng thêm `enforcedPlatform` cho một reusable library chỉ vì thấy version graph chưa đúng. Với library, thường nên ưu tiên `platform` và ràng buộc được thiết kế rõ, rồi để consumer có quyền quyết định cần thiết.

### 5.3. “Force” không thay thế giải thích tương thích

Một version bị ép thấp hơn yêu cầu tối thiểu của thư viện khác có thể khiến runtime ném `NoSuchMethodError`. Một version bị ép cao hơn cũng có thể mang breaking change. Do đó, ép version chỉ có cơ sở khi đã kiểm tra:

- Vì sao version conflict xuất hiện.
- Artifact nào thực sự cần version khác.
- Có BOM/framework release phù hợp hơn không.
- Compatibility giữa các module sau khi enforce.
- Thử nghiệm trên runtime production.

Nếu cần chọn một version khác BOM để vá CVE, ghi đó là **temporary governed override** với nguồn bằng chứng, test và thời hạn loại bỏ.

## 6. Tạo java-platform project nội bộ

Khi tổ chức có nhiều module Java cùng stack, một platform nội bộ giúp quản lý version ở một nơi.

### 6.1. Cấu trúc multi-project

```text
commerce/
├── settings.gradle
├── dependency-platform/
│   └── build.gradle
├── order-service/
│   └── build.gradle
└── payment-service/
    └── build.gradle
```

Trong `settings.gradle`:

```groovy
rootProject.name = "commerce"

include "dependency-platform"
include "order-service"
include "payment-service"
```

### 6.2. Định nghĩa java-platform project

Trong `dependency-platform/build.gradle`:

```groovy
plugins {
    id "java-platform"
}

dependencies {
    constraints {
        api "com.example:example-core:2.7.0"
        api "com.example:example-http:2.7.0"
        api "com.example:example-observation:1.9.2"
    }
}
```

Với `java-platform`, các khai báo dưới `constraints` tạo version recommendations/constraints cho dependency consumers. Các tọa độ ở ví dụ là giả định.

Trong `order-service/build.gradle`:

```groovy
plugins {
    id "java"
}

dependencies {
    implementation platform(project(":dependency-platform"))

    implementation "com.example:example-core"
    implementation "com.example:example-http"
}
```

`payment-service` cũng có thể import cùng project platform để nhận bộ constraint nhất quán.

### 6.3. Platform có thể import một platform khác

Một tổ chức có thể muốn platform nội bộ dựa trên BOM của framework rồi thêm version cho thư viện nội bộ. Với Gradle `java-platform`, cần cho phép dependency platform trước khi import:

```groovy
plugins {
    id "java-platform"
}

javaPlatform {
    allowDependencies()
}

dependencies {
    api platform(
        "com.example.framework:framework-bom:4.0.0"
    )

    constraints {
        api "com.example:internal-client:2.7.0"
    }
}
```

Đây là mẫu sử dụng platform dependency trong platform project. BOM và version minh họa; cần chọn framework BOM thực tế và kiểm tra Gradle/plugin compatibility.

Không nên chỉ thêm một JAR framework vào dependencies của `java-platform`: mục tiêu là mang dependency constraints, không biến platform thành runtime library.

### 6.4. api và runtime constraints

Trong platform, có thể tồn tại constraints thuộc các variant/phạm vi khác nhau. Nếu platform được công bố cho consumer, cần xác định constraint nào nên áp dụng cho API consumers và constraint nào chỉ liên quan runtime.

Đừng giả định mọi dependency constraint là bắt buộc trong mọi configuration. Khi test, resolve compile và runtime graph của consumer thật để xác nhận constraint được nhìn thấy.

### 6.5. Xuất bản platform

Gradle `java-platform` có thể tham gia publication qua `maven-publish` khi được cấu hình phù hợp. Khi đó Gradle Module Metadata và Maven POM representation có thể mang thông tin khác nhau, nhất là với rich version constraints và variants.

Cần kiểm tra cả consumer Gradle và Maven nếu platform được dùng liên hệ sinh thái. Không giả định mọi rich constraint đặc thù Gradle đều được truyền nguyên nghĩa sang Maven BOM.

## 7. BOM, version catalog, constraints và locking: không phải một thứ

Bốn cơ chế được dùng cùng nhau nhưng giải quyết các vấn đề khác nhau.

| Cơ chế | Chức năng chính | Có tham gia dependency graph resolution? |
|---|---|---|
| Maven BOM | Cung cấp dependency management | Có, theo quy tắc Maven |
| Gradle platform | Cung cấp version constraints/alignment | Có, theo quy tắc Gradle |
| Gradle version catalog | Đặt alias và version cho declaration | Không tự cưỡng chế version được chọn |
| Gradle dependency constraints | Yêu cầu/ưu tiên/ràng buộc version cụ thể | Có |
| Gradle dependency locking | Ghi version resolved để build tái lập | Có, với configuration được lock |
| Dependency verification | Xác minh artifact checksum/signature | Không phải cơ chế chọn version |

### 7.1. Version catalog là từ điển khai báo

Ví dụ `gradle/libs.versions.toml`:

```toml
[versions]
example-platform = "1.0.0"

[libraries]
example-bom = { module = "com.example.platform:example-dependencies", version.ref = "example-platform" }
example-core = { module = "com.example:example-core" }
example-http = { module = "com.example:example-http" }
```

Trong Gradle Groovy DSL:

```groovy
dependencies {
    implementation platform(libs.example.bom)
    implementation libs.example.core
    implementation libs.example.http
}
```

Version catalog giúp tránh lặp group/artifact/version trong build scripts; nó **không tự động căn chỉnh transitive dependencies**. Nếu chỉ dùng alias có version nhưng không import platform/constraint phù hợp, conflict resolution vẫn có thể chọn version khác.

Đặc biệt, version catalog còn có thể khai báo plugin aliases, nhưng việc quản lý **plugin versions** là vấn đề khác với runtime BOM.

### 7.2. Dependency locking để tái lập resolved graph

Một BOM có thể được cập nhật, và Gradle có thể resolve version khác do constraint khác hoặc metadata thay đổi. Dependency locking ghi lại các version resolved cho những configuration được cấu hình locking.

Ví dụ Groovy DSL:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Và một tác vụ tạo/cập nhật lock state:

```bash
./gradlew dependencies --write-locks
```

Cần sử dụng đúng Gradle version và scope task để đảm bảo các configurations quan trọng thực sự đã được resolve và đưa vào lockfile. Đừng coi một lệnh chạy xong là bằng chứng mọi runtime/test configuration đã có lock state. Dùng task build/test phù hợp để resolve các graph cần khóa.

Khi nâng BOM, cập nhật lockfile có chủ đích, review diff và commit cùng code/config migration. Nếu chỉ đổi BOM mà lock chưa đổi, build có thể bị giữ ở version cũ hoặc báo conflict tùy cấu hình.

### 7.3. Dependency verification bảo vệ artifact, không giải quyết alignment

Gradle dependency verification có thể lưu checksums và chữ ký để xác nhận artifact đến từ nguồn dự kiến. Maven cũng có thể dùng checksum/repository policy và các công cụ quản lý supply chain phù hợp.

Một artifact có checksum đúng vẫn có thể là **version không tương thích** với framework. Ngược lại, version phù hợp nhưng artifact bị thay đổi trái phép vẫn là rủi ro. Alignment, locking và verification là các lớp kiểm soát bổ sung, không thay thế nhau.

## 8. Framework BOM và managed versions

Nhiều hệ sinh thái cung cấp BOM chính thức hoặc platform:

- Spring Boot dependency management BOM.
- Các BOM cho nhóm Jackson hoặc Micrometer/Reactor khi dùng đúng stack.
- Một số cloud SDK dùng BOM để căn chỉnh nhiều module.
- Netty và các họ library có nhiều artifact phát hành đồng bộ.
- JUnit hoặc framework testing có nhiều module.
- BOM nội bộ cho các SDK/service client riêng của tổ chức.

Không nên coi ví dụ tên framework là lời khẳng định phiên bản mới nhất hay ma trận hỗ trợ hiện tại. Khi áp dụng thật, xác minh tài liệu chính thức của version/framework đang dùng.

### 8.1. Framework BOM là điểm neo của stack

Một nguyên tắc thực tế: nếu ứng dụng dựa trên một framework lớn, BOM được framework khuyến nghị thường là **điểm khởi đầu** cho các thư viện mà framework kiểm thử.

Ví dụ một ứng dụng Spring Boot dùng Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring.boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Khi đó các dependency thuộc BOM có thể được khai báo không version nếu đúng group/artifact/type/classifier được BOM quản lý. Nếu dự án dùng parent POM của framework, cần kiểm tra dependency management đã được kế thừa hay chưa trước khi import thêm.

Nâng framework BOM từ một release line sang release line khác có thể thay đổi hàng chục version. Vì vậy, thay BOM là **một đơn vị thay đổi lớn**, không chỉ một con số.

### 8.2. Khi nào phải override một version BOM?

Có thể có lý do:

- Một CVE nghiêm trọng đã có bản vá nhưng framework BOM hiện tại chưa cập nhật.
- Một regression được xác nhận ở version được BOM chọn.
- Một driver cần version mới để hỗ trợ server/JDK/OS hiện tại.
- Một tính năng cần thiết chỉ có ở version cụ thể.

Để override có kiểm soát:

1. Ghi artifact, version do BOM quản lý và version mục tiêu.
2. Giải thích nguồn rủi ro hoặc yêu cầu, kèm tài liệu.
3. Đánh giá dependency compatibility của cả họ thư viện.
4. Chạy unit/integration/contract tests trên JDK/runtime mục tiêu.
5. Kiểm tra classpath cuối và SBOM.
6. Có owner và ngày xem xét gỡ override khi BOM chính thức cập nhật.

Không nâng riêng một module trong họ có nhiều artifact liên kết chặt nếu vendor yêu cầu version alignment.

## 9. Ranh giới giữa dependency BOM và build plugins

### 9.1. Maven

Maven BOM import trong `dependencyManagement` không đặt version cho:

- `maven-compiler-plugin`.
- `maven-surefire-plugin` và `maven-failsafe-plugin`.
- `maven-shade-plugin` / `maven-assembly-plugin`.
- Annotation processor plugin hoặc generator plugin.
- Plugin implementation dependencies.

Quản lý plugin qua `pluginManagement`, cấu hình build plugin, parent và wrapper Maven theo chính sách dự án.

### 9.2. Gradle

Platform được thêm vào `implementation`/`runtimeOnly`/`testImplementation` không tự cập nhật version của plugin trong:

```groovy
plugins {
    id "org.example.some-plugin" version "1.2.3"
}
```

Plugin resolution phụ thuộc `pluginManagement`, plugin repositories, included builds và plugin markers. Buildscript classpath và annotation processor classpath cũng cần được kiểm kê riêng.

Nếu nâng JDK mà plugin Gradle không chạy được, thêm BOM cho runtime dependency không giải quyết lỗi đó.

### 9.3. Annotation processor và generator

Lombok, MapStruct, QueryDSL, Protobuf, JAXB/XJC, OpenAPI Generator và các processor/generator khác có thể có:

- API/runtime library.
- Processor hoặc tool artifact.
- Build plugin.
- Version compatibility riêng với compiler/JDK.

Một BOM có thể quản lý vài artifact trong số đó nhưng không phải toàn bộ. Kiểm tra generated source, processor classpath và plugin version theo đúng nhiệm vụ.

## 10. Một BOM không thay thế compatibility matrix theo JDK

### 10.1. Class-file version và API level

Nếu một artifact được biên dịch cho Java 21, class file thường có major version 65. Java 17 chỉ hỗ trợ tới major version 61 và không thể nạp class version 65.

BOM có thể chỉ đến artifact Java 21 mà không có bất kỳ thông tin nào buộc build tool từ chối nó cho runtime Java 17. Build bằng JDK 21 thậm chí có thể compile thành công với artifact đó; lỗi mới xảy ra khi deploy trên JDK 17.

Nếu thư viện phải hỗ trợ Java 17, cần:

- Xác minh min supported JDK của từng dependency.
- Cấu hình compiler `--release 17` cho source do mình biên dịch.
- Kiểm tra binary dependency class-file level khi cần.
- Chạy artifact cuối trên Java 17.
- Kiểm tra API mới, reflection, bytecode instrumentation và runtime behavior.

`--release` không kiểm soát bytecode đã compile sẵn của dependency. BOM cũng không tự kiểm soát API Java nền tảng mà binary đó tham chiếu.

### 10.2. Namespace và framework major version

Một BOM có thể quản lý các thư viện `jakarta.*`, trong khi module khác đang dùng provider `javax.*`. Việc đồng bộ group/artifact versions không tự chuyển import, annotation hoặc generated source từ `javax` sang `jakarta`.

Khi nâng framework major version, cần đánh giá cả **source compatibility, binary compatibility và runtime integration**, đặc biệt với servlet, JPA, validation, JAXB/JAX-WS hoặc security API.

### 10.3. Native libraries và hệ điều hành

Driver JNI/native image/tooling có thể phụ thuộc OS, CPU architecture hoặc libc/base image. BOM quản lý version nhưng không chứng minh binary native có thể nạp trong mọi container. Cần test artifact trên môi trường production tương ứng.

## 11. Đọc dependency graph trước và sau khi áp dụng BOM/platform

### 11.1. Maven commands

```bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw dependency:tree -Dverbose
```

Trong multi-module, có thể chạy ở root hoặc chỉ định module theo khả năng của phiên bản Maven/plugin. Lưu output baseline và output sau thay đổi.

Cần chú ý:

- Dependency nào được quản lý từ BOM.
- Dependency nào có version tường minh ở module.
- Version nào bị omitted do conflict.
- Scope/type/classifier khác nhau.
- Test runtime classpath và plugin classpath.
- Các transitive dependencies đến từ đâu.

### 11.2. Gradle commands

```bash
./gradlew --version
./gradlew projects
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:dependencyInsight --dependency example-core --configuration runtimeClasspath
./gradlew :app:buildEnvironment
```

Phần `dependencyInsight` đặc biệt hữu ích để thấy vì sao một version được chọn, bao gồm selection reason, constraints và các đường yêu cầu version. Thay `:app` và `example-core` bằng module/dependency thực tế.

Không chỉ chạy trên root project nếu dependency nằm trong module con. Một application có thể có resolved graph khác một thư viện dùng chung trong cùng multi-project build.

### 11.3. Lưu kết quả thành bằng chứng

Một bảng inventory có thể là:

| Artifact | Requested version | Selected version | Nguồn constraint/management | Configuration | Ghi chú |
|---|---|---|---|---|---|
| `example-core` | Không ghi version | 2.7.0 | Platform v1 | Runtime | Cùng release line |
| `example-http` | 2.5.0 từ dependency bắc cầu | 2.7.0 | Platform v1 + conflict resolution | Runtime | Cần test transport |
| `example-observation` | 1.8.0 từ client | 1.9.2 | Platform v1 | Runtime | Cần test metrics |
| `example-test` | 3.1.0 | 3.1.0 | Test BOM | Test runtime | Tách test scope |

Dữ liệu trong bảng chỉ minh họa; khi bàn giao thật phải có graph output, URL BOM/release notes, commit và người xác nhận.

## 12. Mâu thuẫn giữa nhiều BOM/platform

### 12.1. Tình huống thường gặp

Một ứng dụng cần framework BOM A và SDK BOM B. Cả hai cùng quản lý version của HTTP client hoặc JSON library:

```text
framework-bom-A
  -> json-library: 2.4

sdk-bom-B
  -> json-library: 2.6
```

Đây không phải bằng chứng một trong hai BOM “sai”. Mỗi BOM có thể được kiểm thử trong ngữ cảnh riêng, và tổ hợp A+B cần được đánh giá.

### 12.2. Cách giải quyết trên Maven

1. Xem effective POM để biết management entry thắng.
2. Xem dependency tree để biết version cuối.
3. Đọc compatibility matrix của framework và SDK.
4. Nếu có release line chính thức hỗ trợ nhau, ưu tiên nâng BOM đến tổ hợp đó.
5. Chỉ thêm local override khi có lý do cụ thể và test đầy đủ.
6. Ghi thứ tự import BOM và các entry override trong tài liệu.

### 12.3. Cách giải quyết trên Gradle

1. Xem resolved graph và `dependencyInsight`.
2. Phân biệt `platform`, `enforcedPlatform` và rich constraints.
3. Kiểm tra có dependency khai báo strict version hoặc `force` từ resolution strategy hay không.
4. Chọn tổ hợp tương thích và kiểm tra bằng integration test.
5. Nếu không thể resolve conflict, có thể cần tách module/class loader, thay SDK hoặc thay framework.

Đừng bắt đầu bằng ép version ở mọi nơi. Điều này che nguồn gốc xung đột và dễ tạo một graph chưa được hỗ trợ.

### 12.4. Đừng dùng exclusion như công cụ alignment chính

Một số dự án loại bỏ transitive dependency qua `exclusions`, rồi thêm version trực tiếp. Exclusion có thể cần thiết để tránh dependency cũ hoặc provider trùng, nhưng không có nghĩa thay thế dependency bằng bản khác sẽ tự tương thích.

Trước khi exclude, xác nhận:

- Dependency bị loại có còn được runtime library dùng không.
- Có module khác kéo lại dependency đó không.
- Exclusion ảnh hưởng compile/test/runtime graph thế nào.
- Service provider/resource metadata có bị mất không.
- Có phương án BOM/framework phù hợp hơn không.

## 13. Dependency resolution khác với duplicate JAR trên classpath

Ngay cả khi BOM/platform chọn một version duy nhất trong build graph, artifact cuối vẫn có thể chứa bản trùng hoặc class xung đột vì:

- Application server tự cung cấp library.
- Uber-JAR/shading đóng gói class từ nhiều artifact.
- Plugin loader dùng class loader riêng.
- Docker image chứa JAR ngoài build system.
- Một vendor JAR nhúng dependency chưa relocate.
- Thư viện nội bộ copy class từ package khác.

Ví dụ, application resolved graph chọn `json-library 2.6` nhưng server có `json-library 2.2` được nạp trước. Lỗi `NoSuchMethodError` lúc runtime vẫn có thể xuất hiện.

Khi kiểm tra lỗi class loading, phải biết class được nạp từ đâu và bởi class loader nào. Với tình huống phức tạp, xem thông tin class loading/JVM logs trong phạm vi phù hợp và kiểm tra artifact/container thật.

**BOM không thay thế kiểm tra classpath thực tế của production.**

## 14. Chính sách version cho multi-module repository

### 14.1. Một nguồn quản lý version rõ ràng

Trong multi-module, nên tránh mỗi module tự định nghĩa version của framework dependencies. Chọn một cơ chế chính:

- Maven parent + imported BOM được quản lý tập trung.
- Gradle root convention plugin + shared platform.
- Platform/BOM được publish nội bộ cho nhiều repository.
- Các override được phép theo quy trình review.

Một module có thể cần version khác có chủ đích, nhưng cần có giải thích và test. Mục tiêu không phải cấm mọi override mà là loại bỏ **drift ngẫu nhiên**.

### 14.2. Không đồng bộ version plugin và runtime bằng cách ngầm định

Có thể định nghĩa version properties hoặc catalog để giảm trùng lặp, nhưng phải giữ rõ phạm vi:

- Runtime dependency BOM/platform.
- Build plugin versions.
- Test tool versions.
- Compiler/JDK toolchain.
- Code generator/annotation processor versions.

Một “platform version” không chứng minh tất cả phạm vi đều có cùng compatibility requirements.

### 14.3. Dự án phát hành library khác ứng dụng

**Application** thường kiểm soát runtime graph cuối cùng, nên có thể chọn một bộ version tương đối chặt chẽ và lock.

**Reusable library** cần tránh ép consumer chọn mọi version nội bộ của nó. Với Gradle, tránh xuất cưỡng chế `enforcedPlatform` trừ khi có lý do rất rõ. Với Maven, hãy công bố dependency metadata hợp lý và kiểm tra các consumer khác nhau.

Khi phát hành library, phải xác định minimum supported dependency versions, runtime JDK support và API surface thay vì chỉ nói “build nội bộ pass với BOM của chúng tôi”.

## 15. Upgrade BOM như một thay đổi lớn có kiểm soát

### 15.1. Vì sao cần đọc diff?

Giả sử BOM v1 quản lý 120 artifacts, BOM v2 thay đổi 65 version. Nếu nhóm chỉ nhìn version BOM mà không xem underlying changes, có thể bỏ lỡ:

- Framework library major bump.
- JSON serialization behavior change.
- ORM mapping hoặc JDBC driver update.
- TLS/HTTP client behavior change.
- Bytecode library được nâng để hỗ trợ JDK mới.
- Logger/provider đổi API.
- Native dependency biến mất hoặc xuất hiện.
- Vulnerability fix kéo theo breaking change.

Nâng BOM phải được xem như nâng một **tập dependency phối hợp**, không phải một dependency đơn lẻ.

### 15.2. Chia quy trình thành các bước

1. Chụp baseline graph, artifact, JDK và test result.
2. Xác định release line BOM/platform đích và min JDK.
3. So sánh resolved graph trước/sau, phân nhóm thay đổi.
4. Đọc release notes/migration guides của các thành phần rủi ro cao.
5. Cập nhật build/plugin/processor nếu cần.
6. Compile source và generated source trên JDK mục tiêu.
7. Chạy unit, integration, contract và smoke tests.
8. Chạy test artifact cuối trên runtime JDK/OS/container đích.
9. Kiểm tra hiệu năng, memory, startup và observability.
10. Review SBOM, CVEs, lockfile, verification metadata và override.
11. Rollout theo chính sách với ngưỡng dừng/rollback.
12. Chốt version matrix và bằng chứng.

### 15.3. Tránh nâng nhiều biến số cùng lúc nếu chưa có baseline

Nâng BOM, JDK, Gradle Wrapper, Spring Boot major, database schema và deployment image trong cùng một commit khiến điều tra regression khó hơn. Có thể cần thay đổi cùng nhau do compatibility constraint, nhưng nên chia thành những bước có lý do và bằng chứng tách biệt khi khả thi.

Một lộ trình hợp lý là chốt build tool/JDK, kiểm tra BOM và dependency stack, rồi kiểm chứng artifact trên runtime đích. Thứ tự chi tiết phụ thuộc hệ thống, không có một chuỗi bắt buộc cho mọi dự án.

## 16. Reproducibility: snapshot, range và dynamic versions

### 16.1. Version range và dynamic version có thể gây drift

Ví dụ:

```groovy
dependencies {
    implementation "com.example:example-core:2.+"
}
```

hoặc Maven version range trong cấu hình dependency có thể cho phép version được chọn thay đổi theo thời gian/repository metadata. Điều này làm khó việc tái hiện binary được phát hành.

Một BOM/platform thường dùng release version cố định, nhưng nếu direct dependency hoặc transitive metadata chứa dynamic/changing version thì resolved graph vẫn có thể thay đổi.

Cần chính sách rõ:

- Hạn chế dynamic/range dependencies ở production.
- Không dùng `SNAPSHOT`/changing modules ngoài môi trường chủ đích.
- Dùng lockfile/resolved dependency record khi phù hợp.
- Pin toolchain, build wrapper và artifact source.
- Tạo SBOM cho artifact cuối và lưu checksum.

### 16.2. Repository provenance và supply chain

Một version coordinate không đủ để chứng minh artifact đến từ nguồn đáng tin cậy. Quản lý repository URL, mirror, checksum/signature, quyền xuất bản và chính sách thay đổi artifact.

Nếu Maven/Gradle resolve cùng tọa độ từ nhiều repository khác nhau, phải xác định repository precedence/provenance. Nếu artifact bị thay đổi sau khi publish, build có thể không tái lập dù version string không đổi.

### 16.3. Lockfile không miễn trừ vulnerability response

Khi cần vá CVE, lockfile giúp thấy chính xác version đang dùng, nhưng vẫn phải cập nhật BOM/platform hoặc override có kiểm soát rồi regenerate lock state. Không dùng “build reproducible” làm lý do giữ dependency dễ tổn thương mãi.

## 17. Bản đồ ra quyết định: chọn BOM hay platform?

### 17.1. Maven application

Ưu tiên import BOM chính thức của framework trong `dependencyManagement`; khai báo dependency cần dùng trong `dependencies`; quản lý plugin ở parent/`pluginManagement`. Nếu có nhiều BOM, kiểm tra collision và effective POM.

### 17.2. Maven multi-module/internal ecosystem

Có thể publish một BOM nội bộ chứa bộ version đã kiểm thử, và dùng parent POM riêng cho build plugins/conventions. Cần quy định BOM versioning, kiểm tra consumer và dependency management override.

### 17.3. Gradle application

Dùng `platform(...)` để tiêu thụ BOM chính thức; dùng `dependencyInsight` xác minh resolution. Nếu cần version tái lập, kết hợp dependency locking. Chỉ dùng `enforcedPlatform(...)` khi hiểu hậu quả cưỡng chế và scope.

### 17.4. Gradle multi-project/internal ecosystem

Dùng `java-platform` project hoặc published platform với constraints. Có thể import platform nhà cung cấp rồi bổ sung constraints nội bộ. Dùng version catalog để đặt alias đẹp và quản lý version khai báo, nhưng không coi catalog là alignment engine.

### 17.5. Mixed Maven/Gradle organization

Nếu tổ chức publish một BOM Maven để cả hai build system tiêu thụ, cần chạy **consumer verification riêng cho Maven và Gradle**, bởi resolution semantics khác nhau. Nếu publish Gradle java-platform, cần kiểm tra Maven POM representation và metadata khi consumer ở Maven không hiểu Gradle-specific rich constraints.

## 18. Ví dụ xuyên suốt: nâng từ Java 17 sang Java 21

Giả sử một hệ thống gồm `order-service` và `payment-service`, dùng một framework web, JSON library, HTTP client, database driver và observability stack. Baseline đang chạy JDK 17; mục tiêu là JDK 21.

### 18.1. Trước migration

Các module tự pin version:

```text
order-service:
  web-framework      A
  json-library       B
  http-client        C
  metrics-library    D

payment-service:
  web-framework      A
  json-library       B-1
  http-client        C-1
  metrics-library    D+1
```

Phát sinh drift không nhất thiết đã gây lỗi, nhưng làm khó việc kiểm chứng khi đổi JDK.

### 18.2. Thiết kế BOM/platform đích

Nhóm chọn một release line framework chính thức hỗ trợ Java 21, rồi quản lý version của các library liên quan trong một platform. Mỗi service chỉ khai báo dependency cần dùng, không tự ghim version trừ khi đã được duyệt.

Với Gradle, `order-service` có thể import:

```groovy
dependencies {
    implementation platform(project(":dependency-platform"))

    implementation "com.example:web-client"
    implementation "com.example:json-adapter"
    implementation "com.example:metrics-adapter"
}
```

Với Maven, module import BOM nội bộ và khai báo dependency không version tương đương.

### 18.3. Kiểm tra sự đồng bộ thực tế

Bản graph sau migration phải cho thấy:

- Cùng một version được chọn cho mỗi module phổ biến theo từng configuration.
- Framework và driver tương thích với nhau theo ma trận hỗ trợ.
- Compiler plugin, processor và test agent hỗ trợ JDK 21.
- Không có duplicate/provider xung đột trong packaged artifact.
- Có bản ghi override nào khác BOM và vì sao.

### 18.4. Kiểm tra trên JDK 21

Chạy compile và test trên JDK mới. Nếu artifact không cần chạy Java 17, có thể target Java 21; nếu còn phải hỗ trợ runtime 17 thì cần `--release 17` và test ở cả hai runtime. BOM không quyết định chính sách bytecode/API target này.

### 18.5. Một lỗi thực tế thường gặp

Sau khi nâng BOM, application compile thành công nhưng test runtime báo:

```text
java.lang.NoSuchMethodError:
  'void com.example.json.JsonProcessor.configure(boolean)'
```

Hướng điều tra:

1. Xem stack trace xác định caller.
2. Kiểm tra caller được compile với version JSON library nào.
3. Dùng dependency tree/insight xác định runtime version.
4. Kiểm tra BOM nhập đúng project/configuration chưa.
5. Xem có direct version pin, strict constraint, enforced platform hoặc transitive conflict không.
6. Xác minh package artifact thực tế có thêm duplicate JAR không.
7. Chọn tổ hợp được hỗ trợ, không chỉ ép version để hết lỗi.
8. Chạy regression test và cập nhật platform/lock state.

## 19. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách phòng tránh |
|---|---|---|
| Nghĩ BOM tự tải mọi dependency | Library không có trên compile/runtime classpath | Khai báo dependency cần dùng trong project |
| Đưa BOM vào `dependencies` như JAR | Không áp dụng dependency management như mong đợi | Import đúng cú pháp Maven BOM |
| Nghĩ BOM quản lý compiler/test plugin | Build tool/plugin có thể không tương thích JDK | Quản lý plugin classpath và version riêng |
| Nghĩ Gradle `platform` luôn force version | Version cuối có thể khác BOM | Dùng `dependencyInsight` và kiểm tra constraints |
| Dùng `enforcedPlatform` trong reusable library vô thức | Force version lan tới consumer | Ưu tiên platform thường và kiểm tra publication |
| Nghĩ version catalog là BOM | Transitive dependency drift vẫn xảy ra | Dùng catalog cho alias, platform cho alignment |
| Nghĩ Maven và Gradle resolve giống nhau | Consumer dùng cùng BOM nhận graph khác | Kiểm tra resolved graph từng build system |
| Import nhiều BOM rồi không xem collision | Version được chọn không như dự kiến | Xem effective POM/insight và ghi override |
| Ghim nhiều direct versions ngoài BOM | Phá version alignment có chủ đích | Giảm pin, có governance cho ngoại lệ |
| Chỉ test compile | Linkage/runtime errors bị bỏ sót | Chạy packaged artifact và integration tests |
| Nghĩ BOM bảo đảm JDK support | Dependency có thể yêu cầu JDK mới hơn runtime | Kiểm tra min JDK/bytecode và runtime tests |
| Dùng exclusion/force để che conflict | Có thể gây thiếu class/provider | Tìm root cause và chọn stack tương thích |
| Không cập nhật lockfile sau nâng BOM | Build không nhận đúng version hoặc không tái lập | Review và regenerate lock state |
| Chỉ xem development classpath | Production/test classpath có dependency khác | Kiểm tra mọi configuration quan trọng |

## 20. Hồ sơ cần lưu khi nâng BOM/platform

Một đợt quản lý version đồng bộ nên bàn giao tối thiểu:

1. **Baseline inventory:** JDK, framework, build tool, dependency graph và versions trước migration.
2. **Platform source:** BOM/platform coordinates, version và nguồn tài liệu chính thức.
3. **Managed version matrix:** các artifact quan trọng được quản lý và lý do chọn version.
4. **Resolved graphs:** compile/runtime/test/processor configurations của từng module.
5. **Conflict report:** các BOM collision, override, force, strict constraint, exclusion và lý do.
6. **Plugin/tool inventory:** Maven/Gradle Wrapper, compiler/test plugins và generators.
7. **JDK compatibility evidence:** min runtime JDK, class-file/API target và provider support.
8. **Verification report:** compile, unit, integration, contract, smoke và test trên packaged artifact.
9. **Supply-chain record:** lockfiles, verification metadata, SBOM/checksum và CVE review.
10. **Release plan:** rollout, metric, ngưỡng dừng, rollback và owner.

### Checklist trước khi chốt

- [ ] Đã xác định một BOM/platform chính làm điểm neo cho dependency stack.
- [ ] Đã phân biệt BOM, parent POM, version catalog, platform và lockfile.
- [ ] Đã import BOM/platform đúng cú pháp và đúng configuration.
- [ ] Đã xác nhận dependencyManagement không tự tải dependency.
- [ ] Đã quản lý build plugins và generator versions riêng.
- [ ] Đã xem effective POM hoặc resolved dependency graph sau thay đổi.
- [ ] Đã xử lý mọi xung đột giữa BOM hoặc platform có chồng chéo.
- [ ] Đã hạn chế direct version pin không có chủ đích.
- [ ] Đã cân nhắc hậu quả của `enforcedPlatform` với consumer library.
- [ ] Đã so sánh graph trước/sau và ghi thay đổi version quan trọng.
- [ ] Đã xác minh framework, driver, provider và JDK target tương thích.
- [ ] Đã chạy test trên artifact và runtime production tương đương.
- [ ] Đã xác minh classpath/package artifact không có duplicate ngoài ý muốn.
- [ ] Đã review lockfile, checksum/signature/SBOM và rủi ro bảo mật.
- [ ] Đã ghi override, chủ sở hữu và điều kiện gỡ bỏ ngoại lệ.
- [ ] Đã chuẩn bị rollback và cập nhật tài liệu version matrix.

**BOM và platform không làm một dependency graph tự nhiên trở nên tương thích; chúng cung cấp cơ chế để tổ chức quản lý version theo một chính sách có thể kiểm chứng.** Maven dùng dependency management và mediation của POM; Gradle dùng platform/constraints và conflict resolution riêng. Kết hợp một nguồn version chung, kiểm tra graph thực tế, kiểm thử trên JDK mục tiêu và quản trị ngoại lệ giúp giảm version drift, hạn chế lỗi linkage và tạo nền tảng đáng tin cậy cho các đợt Java compatibility migration tiếp theo.
