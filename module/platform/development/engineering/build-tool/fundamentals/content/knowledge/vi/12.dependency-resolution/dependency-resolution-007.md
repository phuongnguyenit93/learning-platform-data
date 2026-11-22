# Đồng bộ các thư viện cần đi cùng một bộ phiên bản

Một ứng dụng Java thường dùng nhiều thư viện thuộc cùng một hệ sinh thái. Ví dụ, Jackson có các module để xử lý JSON, YAML và kiểu dữ liệu Java 8; Spring có nhiều module phục vụ context, web, transaction và dữ liệu; Netty cũng được chia thành nhiều artifact. Các module này thường được phát hành theo một dòng phiên bản tương thích với nhau.

Nếu mỗi module được khai báo phiên bản riêng ở nhiều nơi, dự án có thể vô tình kết hợp những phiên bản không được thiết kế để dùng cùng nhau. Build vẫn có thể biên dịch, nhưng khi chạy có thể gặp `NoSuchMethodError`, `NoClassDefFoundError`, lỗi `ClassCastException` hoặc hành vi không tương thích. Khi nâng cấp, nhóm cũng phải tìm và sửa nhiều dòng cấu hình.

Để giải quyết vấn đề đó, build tool hỗ trợ cơ chế quản lý một **bộ phiên bản thống nhất**. Trong Gradle, cơ chế quan trọng là *platform* và *BOM*. Trong Maven, cơ chế tương ứng là *Bill of Materials* được nhập qua `dependencyManagement`. Các cơ chế này cho phép một nơi định nghĩa phiên bản của nhiều thư viện có liên quan để các module trong dự án cùng sử dụng một bộ phiên bản.

## 1. Vì sao các thư viện cần được đồng bộ phiên bản?

Một thư viện lớn thường được chia thành nhiều artifact nhỏ. Mỗi artifact có thể được phát hành độc lập về mặt đóng gói, nhưng vẫn phụ thuộc vào API hoặc implementation của những artifact cùng dòng.

Ví dụ, ứng dụng dùng hai module Jackson:

```text
application
   |
   +----> jackson-databind
   |
   +----> jackson-datatype-jsr310
```

`jackson-databind` cung cấp chức năng ánh xạ dữ liệu JSON sang object Java. `jackson-datatype-jsr310` bổ sung hỗ trợ cho các kiểu ngày giờ như `LocalDate` và `LocalDateTime`. Hai module có thể cần các API nội bộ hoặc API chung tương thích nhau.

Nếu cấu hình thành:

```groovy
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
    implementation 'com.fasterxml.jackson.datatype:jackson-datatype-jsr310:2.15.4'
}
```

thì dự án đang yêu cầu hai module thuộc hai phiên bản khác nhau. Có thể chúng vẫn hoạt động trong một số trường hợp, nhưng nhóm đang tự chịu rủi ro tương thích và phải kiểm tra từng cặp phiên bản.

Khi thư viện phát hành BOM hoặc platform, nhà cung cấp đã công bố một tập phiên bản được kiểm thử hoặc quản lý cùng nhau. Dự án có thể sử dụng bộ đó thay vì tự chọn từng phiên bản.

### Những lợi ích của đồng bộ phiên bản

- **Tương thích:** các module trong cùng hệ sinh thái dùng phiên bản được thiết kế để phối hợp.
- **Nâng cấp tập trung:** thay đổi bộ phiên bản tại một điểm thay vì sửa nhiều module.
- **Ít xung đột hơn:** dependency bắc cầu được quản lý theo các constraint của platform/BOM.
- **Dễ xem xét:** người đọc build file biết dự án đang theo release train hoặc BOM nào.
- **Tái lập build:** kết hợp bộ phiên bản rõ ràng với dependency locking giúp các lần build chọn cùng graph đã được ghi nhận.

## 2. BOM là gì?

BOM là viết tắt của *Bill of Materials*. Trong hệ sinh thái Maven, BOM thường là một artifact có packaging `pom`, chủ yếu chứa phần `dependencyManagement` để quy định version và metadata cho các dependency liên quan.

Một BOM có thể quản lý nhiều artifact:

```text
jackson-bom:2.17.2
    |
    +---- jackson-databind:2.17.2
    |
    +---- jackson-core:2.17.2
    |
    +---- jackson-annotations:2.17.2
    |
    +---- jackson-datatype-jsr310:2.17.2
```

BOM tập trung thông tin phiên bản. Nó không nhất thiết tự thêm tất cả artifact vào ứng dụng. Module vẫn khai báo những thư viện mà mã nguồn thực sự sử dụng; BOM giúp build tool biết nên dùng phiên bản nào cho các artifact được BOM quản lý.

Điểm này rất quan trọng: **quản lý phiên bản và thêm dependency là hai việc khác nhau**. Import BOM không có nghĩa ứng dụng tự động nhận tất cả thư viện trong BOM vào classpath.

## 3. Dùng BOM trong Gradle

Gradle hỗ trợ Maven BOM thông qua dependency dạng platform. Với Jackson, có thể khai báo:

```groovy
dependencies {
    implementation platform('com.fasterxml.jackson:jackson-bom:2.17.2')

    implementation 'com.fasterxml.jackson.core:jackson-databind'
    implementation 'com.fasterxml.jackson.datatype:jackson-datatype-jsr310'
}
```

`platform(...)` nhập các dependency constraints từ BOM vào configuration. Sau đó, các dependency Jackson được khai báo mà không cần lặp lại version trên từng dòng. Gradle sử dụng các constraint để giải quyết phiên bản của những module mà BOM quản lý.

Nếu chỉ dùng một số module Jackson, hãy khai báo đúng những module đó. Không cần thêm tất cả artifact trong BOM.

### BOM và dependency bắc cầu

Một dependency có thể kéo theo module khác thông qua metadata. Ví dụ `jackson-databind` có thể kéo `jackson-core` và `jackson-annotations`. Khi platform/BOM cung cấp constraint cho những artifact đó, Gradle có thể dùng các constraint trong quá trình giải quyết dependency graph, kể cả khi một artifact được kéo vào theo đường bắc cầu.

Điều này hữu ích hơn việc chỉ đặt cùng một version trong vài dòng dependency trực tiếp. Nếu module khác đưa một phiên bản khác vào graph, constraint của platform vẫn tham gia vào quy trình giải quyết phiên bản.

### `platform` và `enforcedPlatform`

Gradle có hai cách nhập platform thường gặp:

```groovy
dependencies {
    implementation platform('com.fasterxml.jackson:jackson-bom:2.17.2')
}
```

`platform(...)` thêm các constraint theo cơ chế platform thông thường. Nó tham gia giải quyết phiên bản cùng với các dependency và constraint khác trong graph.

```groovy
dependencies {
    implementation enforcedPlatform('com.fasterxml.jackson:jackson-bom:2.17.2')
}
```

`enforcedPlatform(...)` áp đặt các version trong platform mạnh hơn, kể cả khi dependency khác yêu cầu phiên bản khác. Ràng buộc được áp đặt có thể ảnh hưởng đến consumer khi dependency được truyền tiếp qua module được publish. Vì vậy, không nên dùng `enforcedPlatform` như lựa chọn mặc định cho thư viện dùng chung nếu không muốn áp đặt version lên ứng dụng tiêu thụ.

Với ứng dụng cuối hoặc môi trường build do nhóm kiểm soát, `enforcedPlatform` có thể hữu ích khi chính sách yêu cầu một bộ version bắt buộc. Với thư viện được phát hành cho nhiều consumer, platform thông thường thường linh hoạt hơn.

## 4. Tạo platform riêng trong Gradle

Không phải lúc nào dự án cũng có một BOM bên ngoài đáp ứng đúng nhu cầu. Một tổ chức có thể cần thống nhất version của các thư viện nội bộ hoặc kết hợp nhiều thư viện bên ngoài thành một bộ đã được kiểm thử. Gradle hỗ trợ tạo platform riêng bằng plugin `java-platform`.

Ví dụ cấu trúc build:

```text
commerce/
├── settings.gradle
├── dependency-platform/
│   └── build.gradle
├── app/
│   └── build.gradle
└── services/
    └── build.gradle
```

`settings.gradle`:

```groovy
rootProject.name = 'commerce'
include 'dependency-platform', 'app', 'services'
```

`dependency-platform/build.gradle`:

```groovy
plugins {
    id 'java-platform'
}

dependencies {
    constraints {
        api 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
        api 'com.fasterxml.jackson.core:jackson-core:2.17.2'
        api 'com.fasterxml.jackson.core:jackson-annotations:2.17.2'
        api 'com.fasterxml.jackson.datatype:jackson-datatype-jsr310:2.17.2'
    }
}
```

Project `dependency-platform` không cần chứa mã nguồn ứng dụng. Nó mô tả các constraint để những project khác trong build có thể dùng chung.

Trong `app/build.gradle`:

```groovy
dependencies {
    implementation platform(project(':dependency-platform'))

    implementation 'com.fasterxml.jackson.core:jackson-databind'
    implementation 'com.fasterxml.jackson.datatype:jackson-datatype-jsr310'
}
```

Trong `services/build.gradle`:

```groovy
dependencies {
    implementation platform(project(':dependency-platform'))

    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
```

Cả hai module sử dụng cùng bộ constraint. Khi cần nâng cấp Jackson, nhóm thay đổi phiên bản ở `dependency-platform` rồi kiểm tra các module tiêu thụ.

### Constraint không tự thêm thư viện

Trong `java-platform`, khối `constraints` mô tả phiên bản của module. Nó không có nghĩa mọi module tiêu thụ đều tự động nhận các artifact đó vào classpath. `app` vẫn phải khai báo `jackson-databind` nếu mã nguồn sử dụng nó.

Sự tách biệt này giúp platform chỉ định chính sách phiên bản, còn từng module tự khai báo dependency thực sự cần.

## 5. Quản lý constraint và version policy trong Gradle

Platform có thể sử dụng dependency constraints để quy định version. Với build logic lớn, cần phân biệt một số cách chỉ định version:

- **Version yêu cầu:** phiên bản được khai báo trong dependency hoặc constraint và tham gia vào giải quyết xung đột.
- **Preferred version:** phiên bản được ưu tiên khi có thể, nhưng có thể chọn phiên bản khác nếu graph yêu cầu.
- **Strict version:** chỉ cho phép một phiên bản hoặc tập phiên bản được chỉ định; nếu không thể đáp ứng thì resolution thất bại.
- **Rejected version:** phiên bản không được phép chọn.

Ví dụ constraint nghiêm ngặt:

```groovy
dependencies {
    constraints {
        implementation('com.example:critical-library') {
            version {
                strictly '4.2.1'
            }
            because 'Các module của ứng dụng phải dùng cùng bản đã được kiểm thử'
        }
    }
}
```

`strictly` phù hợp khi phiên bản khác thực sự không được chấp nhận. Nếu dùng quá nhiều strict constraint, việc nâng cấp hoặc tích hợp thư viện mới có thể trở nên khó khăn vì các yêu cầu version xung đột sẽ làm resolution thất bại.

Một constraint thông thường thường đủ để điều hướng phiên bản trong platform. Chỉ dùng `strictly`, `reject` hoặc cơ chế áp đặt mạnh khi có chính sách tương thích rõ ràng và nhóm hiểu tác động tới toàn dependency graph.

## 6. Version catalog khác gì platform/BOM?

Gradle version catalog thường được khai báo trong `gradle/libs.versions.toml`. Nó tập trung tên alias, tọa độ và version để build script dùng lại.

Ví dụ:

```toml
[versions]
jackson = "2.17.2"

[libraries]
jackson-bom = { module = "com.fasterxml.jackson:jackson-bom", version.ref = "jackson" }
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind" }
jackson-jsr310 = { module = "com.fasterxml.jackson.datatype:jackson-datatype-jsr310" }
```

Trong build script:

```groovy
dependencies {
    implementation platform(libs.jackson.bom)
    implementation libs.jackson.databind
    implementation libs.jackson.jsr310
}
```

Ở đây có hai vai trò:

- Version catalog cung cấp alias và cách quản lý tọa độ/version ở một nơi.
- BOM được nhập qua `platform(...)` cung cấp constraint để đồng bộ các module thuộc bộ Jackson.

Version catalog một mình không tự đảm bảo mọi dependency bắc cầu trong một họ thư viện được căn chỉnh. Nếu chỉ khai báo nhiều alias với cùng một số version, các module sử dụng alias đó sẽ có version được ghi rõ, nhưng những module được kéo vào theo metadata có thể vẫn cần constraint/platform để được quản lý đồng bộ.

Có thể dùng version catalog và platform cùng nhau. Đây là cách phổ biến để vừa có tên alias dễ đọc, vừa có chính sách version alignment.

## 7. Import Maven BOM trong Maven

Maven hỗ trợ BOM thông qua một dependency có `type` là `pom` và `scope` là `import`, đặt bên trong `dependencyManagement`.

Ví dụ POM của dự án:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>order-service</artifactId>
    <version>1.0.0</version>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.fasterxml.jackson</groupId>
                <artifactId>jackson-bom</artifactId>
                <version>2.17.2</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.datatype</groupId>
            <artifactId>jackson-datatype-jsr310</artifactId>
        </dependency>
    </dependencies>
</project>
```

Maven đọc BOM và dùng các version được quản lý cho những dependency tương ứng. Các dependency thực tế vẫn được khai báo trong `<dependencies>` mà project sử dụng.

### `dependencyManagement` không giống `dependencies`

`dependencies` khai báo thư viện mà project cần. `dependencyManagement` định nghĩa cách quản lý version/scope cho dependency khi chúng được khai báo.

Ví dụ:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đoạn này không tự thêm Jackson vào classpath. Module con hoặc POM hiện tại vẫn phải khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

Khi version được quản lý, dependency có thể bỏ phần `<version>` và nhận version từ `dependencyManagement`.

## 8. Đặt BOM ở POM cha để nhiều module cùng sử dụng

Trong Maven multi-module, BOM hoặc các version được quản lý có thể đặt trong POM cha. Các module con kế thừa chính sách đó và chỉ khai báo những dependency mình thực sự cần.

Ví dụ cấu trúc:

```text
commerce/
├── pom.xml
├── domain/
│   └── pom.xml
├── infrastructure/
│   └── pom.xml
└── app/
    └── pom.xml
```

POM cha:

```xml
<packaging>pom</packaging>

<modules>
    <module>domain</module>
    <module>infrastructure</module>
    <module>app</module>
</modules>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.17.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Trong `domain/pom.xml`, nếu cần Jackson:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

Trong `infrastructure/pom.xml`, nếu cần module hỗ trợ Java Time:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
    </dependency>
</dependencies>
```

Cả hai module nhận cùng chính sách version từ POM cha. Khi nâng cấp BOM, nhóm có một điểm quản lý chính sách chung để xem xét.

## 9. Dùng BOM của framework hay platform do tổ chức quản lý?

Nhiều framework cung cấp BOM chính thức. Ví dụ, Spring Boot có BOM quản lý các dependency mà hệ sinh thái Spring Boot kiểm thử cùng nhau. Một dự án có thể chọn BOM framework làm nền tảng version, sau đó bổ sung constraint cho những thư viện nội bộ hoặc thư viện ngoài phạm vi BOM.

Một tổ chức cũng có thể tạo BOM/platform riêng để:

- Đồng bộ thư viện nội bộ được publish ở repository riêng.
- Chọn một bộ phiên bản đã được kiểm thử cùng nhau.
- Kết hợp version policy của nhiều framework.
- Chặn một số phiên bản đã biết có lỗi hoặc không tương thích.
- Cung cấp một quy ước chung cho nhiều dự án.

Không nên tạo một BOM riêng chỉ để sao chép danh sách version từ một BOM chính thức nếu không có chính sách bổ sung. Nếu framework đã cung cấp release train phù hợp, sử dụng BOM chính thức giúp giảm trách nhiệm duy trì một bản sao version policy.

Khi kết hợp nhiều BOM, cần xác định BOM nào sở hữu version của từng artifact. Nếu hai BOM cùng quản lý một thư viện với version khác nhau, kết quả có thể phụ thuộc vào quy tắc ưu tiên của build tool và cấu hình cụ thể. Hãy kiểm tra effective model hoặc resolved dependency graph thay vì giả định BOM nào cũng có thể chồng lên BOM khác một cách vô hại.

## 10. Đồng bộ phiên bản không có nghĩa mọi thư viện dùng cùng một số version

Một bộ phiên bản thống nhất không có nghĩa tất cả thư viện trong ứng dụng phải mang cùng một số version. Jackson có thể dùng `2.17.2`, Spring Framework dùng `6.1.x`, JUnit dùng `5.11.x` và PostgreSQL driver dùng `42.7.x`.

Điều cần đồng bộ là **các artifact có quan hệ phiên bản với nhau** theo release train hoặc chính sách tương thích của nhà cung cấp. BOM mô tả mối quan hệ đó bằng cách quản lý version cho từng tọa độ.

Ví dụ:

```text
Platform của ứng dụng
    |
    +---- Jackson family: 2.17.2
    |
    +---- Spring family: 6.1.14
    |
    +---- JUnit family: 5.11.3
    |
    +---- PostgreSQL driver: 42.7.4
```

Mỗi nhóm có thể có version riêng. Platform/BOM không ép chúng về một con số chung; nó cung cấp bộ version đã được lựa chọn cho từng module.

## 11. Gradle platform và Maven BOM: điểm giống và khác

| Khía cạnh | Gradle platform | Maven BOM |
|---|---|---|
| Cách biểu diễn phổ biến | Dependency dạng `platform(...)` hoặc project dùng `java-platform` | POM có `dependencyManagement` |
| Mục đích | Cung cấp dependency constraints và version policy | Quản lý version/scope cho dependency |
| Thêm thư viện vào classpath | Không tự thêm mọi module trong platform | Không tự thêm mọi dependency được quản lý trong BOM |
| Dùng từ repository | Có thể import Maven BOM hoặc Gradle platform metadata | Import BOM từ repository |
| Bộ version nội bộ | Tạo project với plugin `java-platform` | Tạo POM BOM riêng |
| Kiểm tra kết quả | `dependencies`, `dependencyInsight` | `dependency:tree`, effective POM |

Hai hệ thống có khái niệm tương đồng nhưng không nên giả định mọi chi tiết resolution giống hệt nhau. Khi dự án chuyển build tool hoặc publish thư viện cho consumer dùng công cụ khác, cần xác nhận metadata được xuất bản và cách consumer diễn giải platform/BOM.

## 12. Version catalog, BOM và dependency locking phối hợp như thế nào?

Ba cơ chế này giải quyết các vấn đề liên quan nhưng khác nhau:

| Cơ chế | Câu hỏi mà nó giải quyết |
|---|---|
| Version catalog | Làm sao đặt tên và khai báo tọa độ/version tập trung trong Gradle? |
| Platform/BOM | Làm sao quản lý và căn chỉnh version của một nhóm artifact liên quan? |
| Dependency locking | Làm sao ghi lại những phiên bản thực tế đã được resolve để lần build sau dùng lại? |

Ví dụ, version catalog có thể khai báo alias cho BOM và thư viện. Platform nhập BOM để đưa constraints vào graph. Dependency locking ghi lại các phiên bản đã được chọn trong từng configuration được lock.

Không cơ chế nào thay thế hoàn toàn cơ chế còn lại. Một catalog không tự bảo đảm dependency bắc cầu được align; một BOM không nhất thiết khóa toàn bộ graph vào một kết quả bất biến; locking không thay thế chính sách tương thích mà BOM cung cấp.

## 13. Khóa phiên bản đã resolve trong Gradle

Sau khi platform/BOM giúp chọn bộ version mong muốn, dự án có thể bật dependency locking để ghi lại kết quả resolution.

Trong `build.gradle`:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Sau đó chạy một task có resolve configuration, đồng thời yêu cầu ghi lock state:

```bash
./gradlew build --write-locks
```

Gradle tạo hoặc cập nhật lock state cho các configuration được cấu hình locking và đã được resolve. Theo cách mặc định hiện nay, lock state được lưu trong tệp `gradle.lockfile` ở thư mục gốc của project; các build cũ có thể dùng định dạng lockfile theo từng configuration trong `gradle/dependency-locks/`.

Khi commit lock state vào repository, các lần build sau có thể dùng cùng các version đã khóa, giảm khả năng dependency bắc cầu thay đổi ngoài dự kiến. Khi nâng cấp BOM hoặc dependency, nhóm cần chủ động cập nhật lock state và xem xét diff.

Dependency locking đặc biệt hữu ích khi dùng version selector linh hoạt, platform có nhiều dependency bắc cầu hoặc cần tái lập kết quả giữa máy phát triển và CI. Nó không thay thế việc chọn version policy hợp lý.

## 14. Kiểm tra phiên bản thực tế được chọn

Không nên chỉ nhìn dòng khai báo BOM rồi giả định toàn bộ graph đã đúng. Hãy xem kết quả dependency resolution.

### Gradle: xem dependency tree

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
```

Lệnh này hiển thị dependency graph của `runtimeClasspath`. Tìm các module thuộc cùng thư viện và xác nhận chúng đang ở các version mong muốn.

### Gradle: tìm lý do một version được chọn

```bash
./gradlew :app:dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

`dependencyInsight` giải thích dependency được yêu cầu từ đâu, constraint nào ảnh hưởng và vì sao một version được chọn. Có thể thay `jackson-databind` bằng module cần kiểm tra.

### Maven: xem dependency tree

```bash
mvn dependency:tree
```

Để lọc một dependency:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

### Maven: xem effective POM

```bash
mvn help:effective-pom
```

Effective POM giúp xem cấu hình sau khi Maven kết hợp POM cha, profile và `dependencyManagement`. Đây là cách hữu ích để xác nhận BOM hoặc version quản lý có được áp dụng như dự kiến hay không.

## 15. Xử lý khi có version conflict

Một dependency graph có thể có nhiều yêu cầu version cho cùng module:

```text
application
   |
   +---- library-A ----> jackson-core 2.15.4
   |
   +---- library-B ----> jackson-core 2.17.2
   |
   +---- platform -----> jackson-core 2.17.2
```

Khi đó, build tool phải giải quyết các yêu cầu theo cơ chế của nó. Thay vì đoán, hãy làm theo các bước:

1. Xác định artifact bị xung đột và configuration đang resolve.
2. Xem module nào yêu cầu từng version.
3. Xác định BOM/platform nào quản lý artifact đó.
4. Kiểm tra constraint, strict version hoặc rule ghi đè đang có.
5. Chọn bộ version tương thích và cập nhật BOM/platform tại nơi sở hữu chính sách.
6. Chạy lại dependency insight/tree để xác nhận kết quả.
7. Chạy kiểm thử phù hợp và cập nhật lock state nếu dự án dùng dependency locking.

Không nên thêm một dòng version ngẫu nhiên ở module đang lỗi chỉ để làm build qua. Cách đó có thể che giấu xung đột nhưng làm version policy của toàn dự án khó hiểu hơn.

## 16. Những rủi ro khi quản lý version không tập trung

**Khai báo version lặp lại.** Nhiều module cùng ghi version của một thư viện. Khi nâng cấp, có thể bỏ sót một nơi.

**Dùng dynamic version thiếu kiểm soát.** Các selector như `1.+` hoặc `latest.release` có thể resolve sang version khác theo thời điểm. Điều này làm build khó tái lập và khiến lỗi xuất hiện dù mã nguồn không đổi.

**Trộn các release train không tương thích.** Các module trong cùng hệ sinh thái có thể gọi API nội bộ hoặc public API đã thay đổi. Chỉ nhìn số version riêng lẻ không đủ để biết chúng có tương thích hay không.

**Áp đặt version quá mạnh.** `enforcedPlatform` hoặc strict constraints có thể ép một dependency bắc cầu dùng version không tương thích với consumer khác. Cần dùng theo chính sách rõ ràng.

**Nhầm catalog với platform.** Version catalog làm cấu hình dễ đọc nhưng không tự thay thế BOM hoặc dependency constraints.

**Import nhiều BOM mà không kiểm tra chồng lấn.** Hai BOM có thể quản lý cùng artifact. Cần xác định nguồn sở hữu version và kiểm tra kết quả resolution.

## 17. Ví dụ hoàn chỉnh với Gradle multi-project

Giả sử build có ba module `app`, `domain` và `integration`, tất cả đều sử dụng một số thư viện Jackson. Tạo project `dependency-platform` để quản lý bộ version.

`settings.gradle`:

```groovy
rootProject.name = 'shop'
include 'dependency-platform', 'app', 'domain', 'integration'
```

`dependency-platform/build.gradle`:

```groovy
plugins {
    id 'java-platform'
}

dependencies {
    api platform('com.fasterxml.jackson:jackson-bom:2.17.2')
}
```

Trong ví dụ này, platform nội bộ nhập BOM chính thức của Jackson và chuyển tiếp các constraint của nó. Nếu cần quản lý thêm thư viện nội bộ, có thể khai báo constraint trong cùng platform:

```groovy
dependencies {
    api platform('com.fasterxml.jackson:jackson-bom:2.17.2')

    constraints {
        api 'com.example:company-json-adapter:1.8.0'
    }
}
```

Module `domain/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api platform(project(':dependency-platform'))
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
```

Module `integration/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation platform(project(':dependency-platform'))
    implementation 'com.fasterxml.jackson.datatype:jackson-datatype-jsr310'
    implementation 'com.example:company-json-adapter'
}
```

Module `app` có thể sử dụng các module nội bộ và platform theo chính sách dự án:

```groovy
plugins {
    id 'application'
}

dependencies {
    implementation platform(project(':dependency-platform'))
    implementation project(':domain')
    implementation project(':integration')
}
```

Ở đây, `dependency-platform` là nơi quản lý bộ version. Các module vẫn khai báo những dependency chúng thực sự sử dụng. Khi cần nâng cấp Jackson, nhóm cập nhật BOM trong platform, kiểm tra dependency graph của các module và chạy kiểm thử tích hợp.

## 18. Ví dụ hoàn chỉnh với Maven multi-module

Maven có thể đạt kết quả tương tự bằng BOM import trong POM cha.

POM gốc:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>shop-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>domain</module>
        <module>integration</module>
        <module>app</module>
    </modules>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.fasterxml.jackson</groupId>
                <artifactId>jackson-bom</artifactId>
                <version>2.17.2</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

POM của module `domain`:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

POM của module `integration`:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
    </dependency>
</dependencies>
```

Các module kế thừa version policy từ parent POM. Khi chạy Maven từ root, reactor xây dựng các module theo quan hệ phụ thuộc. Để xác nhận version thực tế, dùng `mvn dependency:tree` trong từng module hoặc `mvn help:effective-pom`.

## 19. Quy trình nâng cấp một bộ thư viện

Khi cần nâng cấp một release train, nên thực hiện có kiểm soát:

1. Xác định BOM/platform đang quản lý thư viện.
2. Đọc ghi chú phát hành và yêu cầu Java tối thiểu của phiên bản mới.
3. Thay đổi version BOM/platform tại nơi sở hữu chính sách.
4. Resolve lại dependency graph để phát hiện constraint xung đột hoặc module bị kéo về version ngoài dự kiến.
5. Kiểm tra dependency insight/tree của các artifact quan trọng.
6. Chạy unit test, integration test và các build task liên quan.
7. Cập nhật dependency lock state nếu dự án bật locking.
8. Review diff để bảo đảm thay đổi version đúng phạm vi và không làm lộ dependency ngoài ý muốn.

Không nên nâng cấp một module riêng lẻ khỏi bộ version nếu nhà cung cấp không hỗ trợ hoặc nhóm chưa xác minh tương thích. Nếu cần dùng một phiên bản ngoại lệ, hãy ghi rõ lý do và kiểm thử phần tích hợp bị ảnh hưởng.

## 20. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Import BOM là thêm tất cả thư viện trong BOM vào ứng dụng | BOM quản lý version; module vẫn khai báo dependency thực sự cần. |
| Tất cả thư viện trong một bộ phải có cùng số version | Mỗi artifact có version riêng; BOM định nghĩa bộ version tương thích. |
| Version catalog tự căn chỉnh mọi dependency bắc cầu | Catalog tập trung alias/version; platform/BOM hoặc constraints mới cung cấp version alignment. |
| `platform(...)` và `enforcedPlatform(...)` giống nhau | Enforced platform áp đặt version mạnh hơn và có thể ảnh hưởng consumer. |
| Maven `dependencyManagement` tự thêm dependency | Nó quản lý version/scope cho dependency được khai báo ở nơi khác. |
| Dependency locking thay thế BOM | Locking ghi lại version đã resolve; BOM/platform định nghĩa chính sách version. |
| Có BOM là không cần kiểm tra dependency graph | Cần kiểm tra kết quả thực tế vì có thể có constraint khác hoặc nhiều BOM chồng lấn. |
| Chỉ cần sửa version ở module đang lỗi | Nên cập nhật tại nơi quản lý bộ version để các module dùng chung chính sách. |

## 21. Những nguyên tắc nên áp dụng

- Dùng BOM/platform do nhà cung cấp phát hành khi các thư viện thuộc cùng một hệ sinh thái và BOM đó phù hợp với dự án.
- Tạo platform hoặc BOM nội bộ khi tổ chức cần một bộ version đã được kiểm thử và dùng chung.
- Để một nơi sở hữu chính sách version; các module khai báo dependency chúng thực sự cần.
- Kết hợp Gradle version catalog với platform khi cần cả alias tập trung lẫn alignment.
- Dùng `enforcedPlatform` hoặc strict constraints có chủ đích, vì chúng có thể hạn chế consumer hoặc gây resolution failure.
- Kiểm tra dependency graph sau khi thêm hoặc nâng cấp BOM.
- Dùng dependency locking khi cần cố định kết quả resolution giữa các lần build.
- Không xem việc build thành công là bằng chứng duy nhất cho tính tương thích runtime; cần chạy kiểm thử phù hợp.

Đồng bộ các thư viện theo một bộ phiên bản giúp dự án quản lý tương thích ở cấp hệ sinh thái thay vì xử lý từng dependency rời rạc. Gradle platform/BOM và Maven BOM tạo ra một chính sách version tập trung; version catalog giúp khai báo dễ đọc; dependency locking giúp tái lập kết quả đã resolve. Kết hợp đúng các cơ chế này giúp việc nâng cấp và bảo trì dependency có thể kiểm soát hơn.
