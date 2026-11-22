# So sánh io.spring.dependency-management với platform và enforcedPlatform của Gradle trong Spring Boot

## 1. Bối cảnh: Vì sao Spring Boot dùng BOM?

Một ứng dụng Spring Boot thường sử dụng nhiều thư viện có quan hệ phụ thuộc: Spring Framework, Jackson, Logback, Micrometer, các Spring Boot starter, driver cơ sở dữ liệu, thư viện kiểm thử… Nếu tự gán phiên bản cho từng thư viện, bạn dễ tạo ra bộ phiên bản chưa được kiểm thử cùng nhau. Spring Boot công bố **BOM (Bill of Materials)** tên `org.springframework.boot:spring-boot-dependencies`, liệt kê phiên bản được quản lý của nhiều module.

BOM giúp **quản lý phiên bản**, không tự bổ sung thư viện vào ứng dụng. Bạn vẫn phải khai báo module thực sự cần, chẳng hạn `org.springframework.boot:spring-boot-starter-web`. Khi BOM quản lý module đó, có thể bỏ version trong dependency declaration.

Trong một build Gradle, có ba cách thường gặp để áp dụng quy tắc phiên bản từ BOM:

1. Plugin cộng đồng Spring `io.spring.dependency-management`: cung cấp mô hình quản lý dependency kiểu Maven và hỗ trợ tùy chỉnh phiên bản qua property của BOM.
2. `platform(...)`: tính năng gốc của Gradle; đưa các phiên bản BOM vào hệ thống **dependency constraints** để tham gia chọn phiên bản.
3. `enforcedPlatform(...)`: cũng là tính năng gốc của Gradle, nhưng yêu cầu phiên bản BOM theo kiểu **bắt buộc** trong dependency graph.

**Phạm vi bài:** So sánh cách chọn version và cấu hình Gradle cho dự án Spring Boot. `org.springframework.boot` là **Spring Boot Gradle plugin** để xây dựng/đóng gói Boot; `io.spring.dependency-management` là plugin riêng phục vụ dependency management. Hai plugin có trách nhiệm khác nhau.

## 2. Bảng so sánh nhanh

| Tiêu chí | `io.spring.dependency-management` | `platform(...)` | `enforcedPlatform(...)` |
|---|---|---|---|
| Cơ chế | Plugin Spring quản lý dependency theo BOM/DSL gần Maven | Native Gradle platform, nhập BOM thành dependency constraints | Native Gradle platform, ép các version BOM theo ràng buộc nghiêm ngặt |
| Khi có Spring Boot Gradle plugin | Boot **tự import** BOM tương ứng khi plugin quản lý dependency được áp dụng | Phải khai báo platform dependency tường minh | Phải khai báo enforced platform dependency tường minh |
| Có thể bỏ version ở dependency thuộc BOM? | Có | Có, trong configuration chịu ảnh hưởng | Có, trong configuration chịu ảnh hưởng |
| Khi thư viện khác yêu cầu version cao hơn BOM | Tuân theo cơ chế quản lý của plugin và các override/force; cần kiểm tra kết quả | Gradle có thể chọn version khác BOM sau conflict resolution | Cố gắng duy trì version từ BOM; có thể xung đột với strict requirement khác |
| Tùy chỉnh property của Spring Boot BOM | Có, ví dụ `slf4j.version` | Không thông qua property BOM | Không thông qua property BOM |
| Tùy chỉnh bằng Gradle constraints/rules | Có thể phối hợp nhưng phải kiểm chứng tương tác | Là cơ chế tự nhiên của Gradle | Có thể thêm quy tắc, nhưng cần xét strict conflict |
| Phạm vi cấu hình | Plugin mặc định quản lý rộng, có DSL để giới hạn configuration | Configuration khai báo và các configuration kế thừa nó | Tương tự `platform` |
| Lan truyền sang consumer | Có tích hợp Maven POM khi publish theo plugin; cách công bố cần kiểm tra | Platform/constraint có thể lan truyền theo variant, metadata và loại publication | Đặc biệt cần thận trọng: phiên bản bị ép có thể lan truyền tới consumer |
| Hiệu năng/cấu hình build | Thêm plugin và cơ chế xử lý dependency | Tích hợp sẵn với Gradle; Spring Boot cho biết thường nhanh hơn | Tích hợp sẵn với Gradle; mức ép version mạnh hơn `platform` |
| Thường chọn khi nào? | Dự án cần Maven-like management hoặc override property trong BOM | Phần lớn dự án muốn dùng cơ chế native và cho phép Gradle hòa giải version | Ứng dụng cần bộ phiên bản cố định theo BOM trong toàn graph, đã cân nhắc ảnh hưởng |

**Không có nghĩa `platform` “bỏ qua BOM”.** BOM vẫn góp constraint và thường xác định version khi không có yêu cầu khác. Sự khác biệt chủ yếu bộc lộ khi dependency graph có các yêu cầu version cạnh tranh.

## 3. Cơ chế nền tảng: từ dependency declaration đến version thực tế

Giả sử một BOM quản lý module giả định `org.example:lib` ở `1.5`; một dependency khác yêu cầu `org.example:lib:1.7`. Đây là **ví dụ số học minh họa**, không phải phiên bản thực tế của thư viện Spring.

- Với `platform`, Gradle xem version `1.5` do BOM mang đến như constraint bình thường. Yêu cầu `1.7` trong graph có thể khiến kết quả chọn `1.7`.
- Với `enforcedPlatform`, version `1.5` trở thành yêu cầu bị ép; Gradle sẽ ưu tiên `1.5` trước yêu cầu phiên bản thông thường khác. Nếu có những yêu cầu `strictly` không tương thích, resolution có thể thất bại thay vì tự “giải quyết ổn thỏa”.
- Với `io.spring.dependency-management`, plugin áp dụng phiên bản quản lý thông qua cơ chế của chính nó (có tính đến khai báo và rule cụ thể). Không nên gán cho nó một kết quả số tuyệt đối trong mọi graph; chạy `dependencyInsight` để xác nhận.

BOM là bộ **quy tắc phiên bản cho module có mặt trong graph**. Nó không đảm bảo tất cả thư viện đều đến từ BOM: thư viện không được BOM quản lý vẫn cần version/constraint từ nơi khác.

Một bản phát hành Spring Boot được thử nghiệm cùng một tập phiên bản dependency nhất định. **Ép mọi phiên bản theo BOM** giúp bám sát tập đó nhưng không tự bảo đảm tương thích với mọi thư viện ngoài BOM. **Cho phép nâng version** có thể cần thiết để sửa lỗi bảo mật, nhưng phải kiểm tra test và khả năng tương thích API/ABI.

## 4. Cách 1 — Dùng io.spring.dependency-management

### 4.1. Plugin này làm gì?

`io.spring.dependency-management` nhập một hoặc nhiều Maven BOM rồi áp dụng dependency management lên dependency của Gradle project, bao gồm cả dependency trực tiếp và bắc cầu theo mô hình của plugin. Nó cung cấp DSL `dependencyManagement { ... }`, hỗ trợ import BOM, ghi đè module version, đọc các version property trong BOM và một số ngữ nghĩa Maven exclusions.

Trong **project đã áp dụng `org.springframework.boot`**, chỉ cần áp dụng thêm `io.spring.dependency-management`: Spring Boot Gradle plugin sẽ **tự import** BOM `spring-boot-dependencies` đúng version của Boot plugin. Không cần viết thêm `dependencyManagement { imports { mavenBom ... } }` chỉ để import lại chính BOM này.

Ví dụ `build.gradle` Groovy hoàn chỉnh về cấu hình build (ứng dụng muốn chạy còn cần lớp Java chính):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Hai dependency không ghi version vì BOM được import tự động khi **cả hai plugin** có mặt. `3.5.16` và `1.1.7` ở đây là các phiên bản minh họa đã được công bố; trong dự án thực tế hãy chọn phiên bản Boot, Gradle Wrapper và JDK tương thích, rồi giữ một nguồn khai báo version thống nhất.

Tương đương Kotlin DSL `build.gradle.kts`:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Các ví dụ được viết cho project Spring Boot dùng Java/Gradle. Chúng không phải file Java độc lập để chạy bằng `javac`; việc chạy Boot còn phụ thuộc nguồn Java và entry point của project.

### 4.2. Plugin riêng không đồng nghĩa tự có Spring Boot BOM

Nếu một module thư viện chỉ áp dụng `java-library` và `io.spring.dependency-management`, **không áp dụng Spring Boot Gradle plugin**, việc tự import Spring Boot BOM có thể cần thiết:

```groovy
// Đoạn cấu hình thêm vào build.gradle của module đã áp dụng
// io.spring.dependency-management nhưng chưa có Boot plugin.
dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.16'
    }
}
```

Tức là **“plugin đã được áp dụng” không có nghĩa “mọi BOM tự được nhập”**. Tự nhập BOM trong module không dùng Boot plugin cũng là cách hợp lệ khi muốn một thư viện chia sẻ cùng tập dependency Spring Boot mà không biến nó thành Boot executable application.

### 4.3. Ưu điểm: override bằng property BOM

Một Maven BOM có thể khai báo nhiều version qua property. Spring Boot BOM công bố các property như `slf4j.version`; với dependency management plugin, có thể điều chỉnh phiên bản được quản lý thông qua giá trị property đó:

```groovy
// Đoạn minh họa trong build.gradle (Groovy DSL)
ext['slf4j.version'] = '2.0.17'
```

Kotlin DSL tương ứng:

```kotlin
extra["slf4j.version"] = "2.0.17"
```

**Đây chỉ là cú pháp minh họa**, không phải khuyến nghị áp dụng phiên bản trên cho một bản Boot cụ thể. Trước khi đổi, tra property chính xác trong “Dependency Versions Properties” của bản Spring Boot đang dùng, xác định những module liên quan và kiểm tra tương thích. Đổi property cho một nhóm module có thể ảnh hưởng đến nhiều dependency hơn bạn dự tính.

Plugin còn cho phép override bằng dependency management tường minh, ví dụ trong một module được quản lý bằng plugin:

```groovy
dependencyManagement {
    dependencies {
        dependency 'com.zaxxer:HikariCP:5.0.0'
    }
}
```

Hãy chọn phiên bản có thật và tương thích với bộ thư viện đang dùng. Nếu publish Maven POM cho thư viện, **override bằng property có thể không được thể hiện đúng trong POM được sinh**, trong khi dependency management override tường minh có thể xuất hiện trong phần `<dependencyManagement>`. Phải kiểm tra artifact publication thực tế trước khi hứa consumer sẽ nhận cùng quy tắc.

### 4.4. Nhiều BOM và exclusions

Plugin hỗ trợ import nhiều BOM. Khi hai BOM quản lý cùng một module, **thứ tự import quan trọng**: trong dependency management plugin, BOM import sau thường thắng cho module trùng theo tài liệu của plugin. Ví dụ tình huống: một BOM chung và một BOM đặc thù nghiệp vụ cùng khai báo version Jackson; chỉ thay đổi thứ tự import cũng có thể thay đổi phiên bản quản lý.

Plugin cũng cung cấp Maven-like exclusions trong DSL và tôn trọng exclusions ở Maven POM theo cơ chế của nó. Đây là khác biệt về tính năng so với chỉ sử dụng native platform constraints. Tuy nhiên, đặc điểm này không có nghĩa mọi exclusion Java/Gradle đều hoàn toàn giống Maven trong tất cả trường hợp (chẳng hạn classifier có giới hạn đã được plugin ghi nhận).

### 4.5. Giới hạn và điều cần nhớ

- Thêm plugin là thêm một lớp xử lý dependency; Spring Boot khuyến nghị cân nhắc native BOM vì thường nhanh hơn.
- Phiên bản quản lý là cơ chế của plugin, không phải Gradle native `platform`; khi phối hợp với `strictly`, platform hoặc resolution rules, phải xem output resolver thực tế.
- Với ứng dụng Boot đang dùng plugin này, tránh nhập BOM Boot lần nữa một cách thừa thãi nếu không có lý do cụ thể.
- Khi xuất bản thư viện, kiểm tra cả file Maven POM và Gradle Module Metadata nếu đối tượng tiêu thụ dùng nhiều build tool khác nhau.

## 5. Cách 2 — Dùng platform(...) gốc của Gradle

### 5.1. Import BOM thành dependency constraints

Gradle có sẵn cơ chế `platform(...)` để dùng một Maven BOM. Nó xem phần `<dependencyManagement>` của POM như các dependency constraints trong graph. Không cần áp dụng `io.spring.dependency-management`.

Ví dụ project Spring Boot bằng Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Ở đây `SpringBootPlugin.BOM_COORDINATES` là constant do Spring Boot Gradle plugin cung cấp. Nó giúp lấy đúng tọa độ và version BOM tương ứng với phiên bản plugin đã áp dụng; không cần tự viết `org.springframework.boot:spring-boot-dependencies:3.5.16` lần nữa.

Kotlin DSL tương đương với hai khai báo `platform`:

```kotlin
dependencies {
    implementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )
    testImplementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )

    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Đoạn Kotlin được chèn trong `build.gradle.kts` có `plugins { java; id("org.springframework.boot") version "3.5.16" }` và `repositories { mavenCentral() }` như ví dụ Groovy. Nó dùng đúng cú pháp Kotlin DSL, nhưng không tự tạo project hoàn chỉnh nếu đứng một mình.

**Vì sao khai báo cả `implementation` và `testImplementation`?** Platform chỉ tác động đến configuration chứa nó hoặc các configuration kế thừa nó. Trong cấu trúc Java plugin, một số configuration test có thể kế thừa từ main implementation; khai báo riêng ở ví dụ giúp thể hiện rõ ý định quản lý version cho cả test. Hãy đối chiếu cấu trúc configuration của dự án thật để tránh lặp không cần thiết.

Với module Java library **không áp dụng Boot plugin**, dùng tọa độ BOM tường minh:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.16')
}
```

Khi nâng phiên bản Spring Boot ở module như vậy, phải cập nhật BOM bằng cơ chế quản lý version tập trung của build; không có constant của plugin để tự đồng bộ.

### 5.2. “Khuyến nghị” có nghĩa gì?

Một version BOM khi nhập bằng `platform` trở thành constraint **không ép tuyệt đối** trong trường hợp thông thường. Nếu một dependency bắc cầu yêu cầu version mới hơn, Gradle có thể chọn version mới hơn theo conflict resolution. Vì vậy:

- Platform giúp **cung cấp version thống nhất khi không có yêu cầu cạnh tranh**.
- Platform cho phép **Gradle hòa giải xung đột** với những version/constraint khác; kết quả có thể lệch BOM.
- Platform **không chặn** tất cả nâng cấp bắc cầu; nếu yêu cầu bảo mật hoặc tính tương thích đòi hỏi version chính xác, cần xem thêm rich version, dependency constraints nghiêm ngặt hoặc chiến lược khác.

Một thay đổi dependency dù không thay dòng `platform` vẫn có thể thay version được chọn. Sau khi nâng thư viện ngoài BOM, luôn xem lại `runtimeClasspath` và kiểm thử.

### 5.3. Tùy chỉnh version bằng cơ chế Gradle

Native `platform` **không đọc override property trong Spring Boot BOM theo cách của plugin**. Ví dụ:

```groovy
ext['slf4j.version'] = '2.0.17'
```

Nếu chỉ dùng `platform`, dòng đó **không tự thay đổi** version SLF4J do BOM import. Muốn đổi, hãy dùng các phương tiện của Gradle, ví dụ một dependency constraint riêng:

```groovy
dependencies {
    constraints {
        implementation('org.slf4j:slf4j-api') {
            version {
                strictly '2.0.17'
            }
            because 'Example of an explicit version constraint'
        }
    }
}
```

Đoạn này đặt strict constraint cho **một module** `slf4j-api`, không tự điều chỉnh toàn bộ các module SLF4J hoặc các property BOM khác. Nếu có strict constraint khác xung đột, resolution có thể thất bại. Nó là một ví dụ về cơ chế kỹ thuật, không phải khuyến nghị tự ý hạ version của thư viện Spring Boot.

Các lựa chọn khác gồm constraint với `require`/`prefer`, `resolutionStrategy.eachDependency` hoặc version catalog kết hợp constraint. **Version catalog** chỉ tập trung tên và phiên bản khai báo; nó không tự nhập BOM hay bảo đảm tất cả transitive dependencies sẽ nhận version ấy.

## 6. Cách 3 — Dùng enforcedPlatform(...) để ép version BOM

Nếu muốn BOM **chi phối mạnh** version của các module mà nó quản lý, Gradle có `enforcedPlatform(...)`.

Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation enforcedPlatform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation enforcedPlatform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Kotlin DSL, trong project đã áp dụng Spring Boot plugin:

```kotlin
dependencies {
    implementation(
        enforcedPlatform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )
    testImplementation(
        enforcedPlatform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )

    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Theo Gradle, `enforcedPlatform` chuyển các version constraint của BOM thành các version mang tính **strict/forced** trong graph. Khi có dependency khác yêu cầu version thông thường cao hơn, enforced BOM thường giữ version của nó. Đây là hành vi cần chủ đích, vì một thư viện đã được biên dịch/kiểm thử với version cao hơn có thể không tương thích với version bị ép thấp xuống.

**Cảnh báo khi publish library:** Enforced platform có ảnh hưởng **bắc cầu** và có thể xuất hiện trong dependency graph của người dùng thư viện khi publication truyền tải được metadata liên quan. Gradle khuyến cáo thận trọng vì người tiêu thụ có thể bị ép dùng version từ BOM của bạn; nếu có xung đột, họ có thể phải loại trừ dependency hoặc điều chỉnh graph. Điều này đặc biệt đáng cân nhắc với SDK/thư viện chia sẻ hơn là một ứng dụng Boot cuối không được dùng làm dependency.

**Đừng dùng enforcedPlatform chỉ để xử lý mơ hồ một xung đột:** nó có thể ép **nhiều module trong BOM**, kể cả module không liên quan trực tiếp đến lỗi. Trước tiên nên dùng `dependencyInsight` xem đường dẫn và nguyên nhân chọn version, rồi mới quyết định phạm vi tác động phù hợp.

## 7. Ví dụ lựa chọn version khi phát sinh xung đột

Giả sử dùng thư viện giả định:

```text
BOM quản lý     org.example:codec:2.3
Module A        -> org.example:codec:2.5
Ứng dụng        -> module A
```

| Phương án | Xu hướng kết quả | Điều cần kiểm tra |
|---|---|---|
| `platform(BOM)` | `codec:2.5` có thể được chọn vì constraint của BOM không khóa version | Xác nhận version với `dependencyInsight` và chạy test |
| `enforcedPlatform(BOM)` | `codec:2.3` bị ép trong graph thông thường; có thể có xung đột strict | Module A có còn chạy với `codec:2.3` không? |
| `io.spring.dependency-management` | Plugin áp dụng version quản lý/override theo cấu hình; không suy luận từ ví dụ native | Plugin có override và rule nào? Resolver chọn version gì? |

**Ví dụ không phải cam kết resolver cho mọi tình huống.** Gradle còn có version range, `strictly`, `reject`, dependency substitution, rule, nhiều BOM và variant metadata. Một BOM khác cũng có thể ràng buộc `codec`. Kết quả phải được xác nhận trên chính cấu hình `runtimeClasspath` hoặc `testRuntimeClasspath` của project.

Một sơ đồ quyết định ngắn:

```text
Một module xuất hiện trong graph
             |
             v
       Module có trong BOM?
          /        \
        Không       Có
         |           |
  Cần version    BOM đóng góp quy tắc
  từ nơi khác          |
                       v
            Plugin management hay native?
                   /          \
               Plugin         Native
                 |              |
       Áp dụng quy tắc    platform / enforcedPlatform
         plugin              /           \
                         constraint     forced/strict
                             |               |
                         Có thể hòa giải   Ưu tiên version
                         version khác      do BOM ép
```

## 8. Phạm vi configuration và multi-module

Trong Gradle, dependency luôn gắn với configuration như `implementation`, `runtimeOnly`, `testImplementation`, `annotationProcessor` hoặc một configuration tự khai báo. `platform` và `enforcedPlatform` **không mặc nhiên áp dụng cho mọi configuration**:

- `implementation(platform(...))` góp constraint cho các resolvable configurations kế thừa `implementation`, ví dụ các classpath chính theo Java plugin.
- Nếu `annotationProcessor` hoặc một custom configuration không kế thừa `implementation`, nó cần constraint/BOM riêng khi cần phiên bản managed.
- `testImplementation` có thể kế thừa một số dependency của main, nhưng không nên suy đoán tất cả cấu hình test tùy chỉnh đều như vậy.
- Trong multi-project build, import BOM ở project A **không tự động** áp dụng cho mọi project B/C. Mỗi module hoặc convention plugin phải khai báo cơ chế quản lý phù hợp.

Ví dụ với Gradle Kotlin DSL cho một module riêng cần BOM ở annotation processor (đây chỉ là khai báo configuration, không có nghĩa bạn luôn cần annotation processor):

```kotlin
dependencies {
    annotationProcessor(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )
}
```

Chỉ dùng constant `SpringBootPlugin.BOM_COORDINATES` nếu plugin Boot có mặt trên classpath của build script. Nếu không, dùng tọa độ BOM cụ thể được quản lý tập trung.

Trong dự án nhiều module, cân nhắc **convention plugin** hoặc **java-platform project** để cả nhóm cùng dùng một cơ chế nhất quán. Tránh áp dụng `io.spring.dependency-management` đồng thời với `platform` cho cùng một BOM trong cùng module chỉ vì “chắc ăn”; cách phối hợp có thể che giấu nguyên nhân chọn version, làm khó debug và nâng cấp.

## 9. Phiên bản lúc build và phiên bản mà consumer nhận

Câu hỏi “trên máy tôi chọn version nào?” khác với “người dùng thư viện của tôi nhận constraint nào?”.

**Khi dùng `io.spring.dependency-management`:** plugin có thể chỉnh Maven POM được `maven-publish` sinh để thêm các mục trong `<dependencyManagement>` nếu dùng global dependency management. Một override property của BOM ở máy bạn **không nhất thiết** được phản ánh thành phiên bản override trong POM được publish; plugin khuyến cáo dùng explicit dependency management override khi cần POM thể hiện thay đổi.

**Khi dùng native `platform`:** constraints thuộc hệ thống Gradle. Việc truyền các constraint tới consumer phụ thuộc `api`/`implementation`, variant được publish, Gradle Module Metadata và cách chuyển đổi sang Maven POM. Không mặc định rằng consumer Maven nhìn thấy đầy đủ mọi quy tắc như Gradle consumer.

**Khi dùng `enforcedPlatform`:** Gradle cảnh báo nó có thể áp đặt version cho consumer theo tính bắc cầu. Đối với một thư viện dùng lại, việc áp đặt cả BOM thường quá rộng. Nếu chỉ muốn ràng buộc một thư viện, cân nhắc một constraint hoặc rich version `strictly` **có phạm vi cụ thể**, cùng kiểm thử với consumer.

Nếu dự án là **dịch vụ Spring Boot cuối cùng** được đóng gói JAR và triển khai (không publish như library dependency), hậu quả lan truyền xuống consumer có thể ít quan trọng hơn. Tuy nhiên, ép version vẫn có thể làm thay đổi dependency graph khi build/test/runtime và dẫn tới lỗi tương thích.

## 10. Quan sát phiên bản thực tế thay vì đoán

Trên Gradle Wrapper của dự án, chạy:

```bash
# Xem dependency graph của runtime
./gradlew dependencies --configuration runtimeClasspath

# Phân tích vì sao một module được chọn
./gradlew dependencyInsight \
  --dependency org.slf4j:slf4j-api \
  --configuration runtimeClasspath

# Kiểm tra dependency graph dành cho test runtime
./gradlew dependencies --configuration testRuntimeClasspath
```

Trên Windows PowerShell hoặc Command Prompt, dùng `gradlew.bat`. Lệnh `dependencyInsight` có thể viết thành một dòng để tránh khác biệt ký tự nối dòng giữa shell:

```text
gradlew.bat dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
```

Quan sát kết quả:

- `->` trong cây dependency cho thấy một yêu cầu version đã được Gradle chọn/điều chỉnh thành version khác.
- Ký hiệu `(c)` đánh dấu dependency constraint; bản thân constraint không có nghĩa module đó được thêm vào runtime.
- `dependencyInsight` hiển thị selection reasons và đường phụ thuộc gây yêu cầu version, hữu ích để phân biệt BOM recommendation với forced/strict constraint.
- Khi dùng `io.spring.dependency-management`, plugin có task `dependencyManagement` giúp liệt kê managed versions (nếu plugin và task khả dụng ở version đang dùng). Task này không thay thế việc xem **resolved version** bằng `dependencyInsight`.

Không trích dẫn version cụ thể như “chắc chắn chọn 2.3” từ một file build mà chưa nhìn thấy toàn bộ graph: version catalog, constraints ở module khác, rule và dependency transitives có thể ảnh hưởng.

Nếu một dependency chưa xuất hiện trong graph, BOM vẫn có thể quản lý version của nó nhưng `dependencyInsight` không hiển thị module đó trên configuration chưa sử dụng. Hãy kiểm tra bạn đang chọn đúng configuration và đã khai báo dependency cần dùng.

## 11. Cách chọn cho một dự án Spring Boot

| Tình huống | Cách cân nhắc |
|---|---|
| Dịch vụ Boot mới, muốn tận dụng dependency resolution mặc định của Gradle | Bắt đầu với `platform` |
| Dự án đã dùng `io.spring.dependency-management`, có nhiều override bằng BOM property hoặc cần Maven-like management | Tiếp tục plugin nếu có nhu cầu rõ; kiểm tra compatibility khi nâng Gradle |
| Ứng dụng cuối cần bám sát version BOM và đã kiểm tra tập dependency | Có thể chọn `enforcedPlatform`, hiểu rằng nó ép cả BOM |
| Thư viện/SDK sẽ được publish cho nhiều consumer | Ưu tiên `platform` hoặc constraint có phạm vi hợp lý; thận trọng với `enforcedPlatform` |
| Nhiều module cùng quản lý version | Dùng convention chung hoặc java-platform project; tránh mỗi module đặt BOM khác nhau ngoài ý muốn |
| Phải override một module để xử lý lỗi | Kiểm tra dependency graph, constraint/rule hoặc plugin override phù hợp; tránh ép cả BOM khi chưa cần |
| Mong muốn build nhanh hơn, ít plugin hơn | Spring Boot cho biết Gradle native BOM support thường nhanh hơn plugin Spring |
| Cần thay đổi version thông qua property do BOM công bố | `io.spring.dependency-management` là lựa chọn có hỗ trợ trực tiếp |

Các khuyến nghị này phụ thuộc cả **Gradle version**, **Spring Boot version**, **cách publish** và **dependency graph**. Không có cách nào tự động đảm bảo rằng mọi cặp dependency đều tương thích; luôn chạy test sau khi override phiên bản.

## 12. Lỗi thường gặp

**Lỗi 1: Chỉ áp dụng Spring Boot Gradle plugin rồi cho rằng BOM đã tự import.** Boot plugin chỉ tự import `spring-boot-dependencies` khi có `io.spring.dependency-management`; nếu chọn native, bạn phải khai báo `platform(...)`/`enforcedPlatform(...)` tường minh.

**Lỗi 2: Áp dụng `io.spring.dependency-management` nhưng không có Boot plugin, rồi bỏ version mọi dependency.** Plugin cần BOM được import hoặc các managed versions được khai báo. Trong library module không dùng Boot plugin, import BOM thủ công nếu cần.

**Lỗi 3: Đặt `ext['slf4j.version']` rồi chờ `platform(...)` cập nhật.** Override property là tính năng của plugin Spring, không phải cách native platform đọc BOM. Dùng Gradle constraints/rules khi chọn native.

**Lỗi 4: Cho rằng `platform` luôn giữ đúng version trong BOM.** Một transitive dependency có yêu cầu cao hơn có thể khiến Gradle chọn version khác; dùng `dependencyInsight` để xem nguyên nhân.

**Lỗi 5: Dùng `enforcedPlatform` trong thư viện công khai mà không tính consumer.** Forced versions có thể lan truyền và xung đột với dependency của ứng dụng tiêu thụ.

**Lỗi 6: Chỉ thêm BOM ở `implementation` rồi cho rằng mọi configuration đều được quản lý.** Với annotation processor, test suite tùy chỉnh, custom task hoặc module khác, cần kiểm tra cấu trúc kế thừa configuration.

**Lỗi 7: Đặt version trực tiếp và BOM cùng lúc mà không xem conflict.** Version viết trong `implementation("group:module:version")` không nhất thiết là version **cuối cùng**. Có thể bị nâng hoặc bị ép, tùy graph và cơ chế management.

**Lỗi 8: Đổi BOM hoặc version property rồi nghĩ artifact publish chắc chắn thể hiện đúng.** Kiểm tra `pom.xml` và `.module` được sinh, cách `api`/`implementation` công bố và kết quả ở một consumer mẫu.

**Lỗi 9: Nhầm version catalog với BOM.** Catalog cung cấp bí danh/khai báo version thuận tiện; BOM/platform cung cấp constraints tham gia giải quyết cả dependency bắc cầu. Có thể dùng cả hai nhưng không đồng nhất chúng.

**Lỗi 10: Xử lý sự cố bằng cách thêm cả ba cơ chế.** Khi dùng đồng thời plugin Spring, `platform` và `enforcedPlatform`, hành vi có thể khó hiểu. Chọn một chiến lược chủ đạo, rồi thêm constraint cụ thể khi có lý do.

## 13. Checklist thực hành và xác minh

1. Xác định module là **Spring Boot application** hay **library**; có áp dụng `org.springframework.boot` hay không.
2. Chọn cơ chế management: Spring plugin, native `platform` hay native `enforcedPlatform`.
3. Kiểm tra đúng version BOM tương ứng với version Spring Boot trong build; không để mỗi module vô tình dùng version Boot khác nhau.
4. Xác nhận các configuration cần quản lý đã được thêm BOM/managed versions đúng phạm vi.
5. Chạy `./gradlew dependencies --configuration runtimeClasspath`, và `dependencyInsight` cho ít nhất một module quan trọng.
6. Nếu có override, lý giải vì sao cần; kiểm tra mọi module liên quan, chạy unit test/integration test và kiểm tra runtime.
7. Nếu publish library, kiểm tra Maven POM/Gradle Module Metadata và thử dùng artifact từ một consumer.
8. Kiểm tra plugin/Gradle/JDK support matrix khi nâng phiên bản; tránh sao chép nguyên mẫu version của một hướng dẫn vào dự án đang chạy cấu hình khác.

### Tài liệu chính thức để tra cứu

- [Spring Boot Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Gradle User Manual — Platforms](https://docs.gradle.org/current/userguide/platforms.html)
- [Gradle User Manual — Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html)
- [Spring Dependency Management Plugin — Reference](https://docs.spring.io/dependency-management-plugin/docs/current/reference/html/)
- [Gradle User Manual — Declaring Dependency Versions](https://docs.gradle.org/current/userguide/dependency_versions.html)

**Ghi nhớ:** `io.spring.dependency-management` phù hợp với cách quản lý và tùy chỉnh BOM gần Maven; `platform` để Gradle hòa giải version dựa trên các constraint; `enforcedPlatform` ép các phiên bản BOM và có thể ảnh hưởng tới consumer. Luôn chọn dựa trên **khả năng kiểm soát version mong muốn**, **phạm vi dependency graph** và **đối tượng sử dụng artifact**, sau đó kiểm tra version thực tế bằng `dependencyInsight`.
