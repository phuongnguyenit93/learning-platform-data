# Vai trò của BOM và công cụ quản lý dependency

Một ứng dụng Java thường không chỉ dùng một thư viện Jackson. Tùy nhu cầu, ứng dụng có thể cần `jackson-databind`, `jackson-core`, `jackson-annotations`, module hỗ trợ `java.time`, module đọc YAML hoặc những module định dạng khác. Các thư viện này có quan hệ phụ thuộc với nhau và thường được phát hành theo cùng một dòng phiên bản.

Nếu khai báo phiên bản riêng cho từng thư viện, cấu hình build dễ bị lệch: `jackson-databind` ở một phiên bản, `jackson-core` ở phiên bản khác, còn module ngày giờ lại ở một phiên bản thứ ba. BOM và công cụ quản lý dependency giúp tập trung chính sách phiên bản, để các thành phần tương thích được chọn đồng bộ và build có thể tái lập.

## 1. Dependency là gì và vì sao cần quản lý phiên bản?

Một dependency là thư viện hoặc module mà project cần để biên dịch, kiểm thử hoặc chạy. Dependency có thể được khai báo trực tiếp hoặc được kéo vào gián tiếp bởi một dependency khác.

Ví dụ, khi project khai báo `jackson-databind`, dependency graph có thể có dạng khái quát:

```text
Ứng dụng
  |
  +-- jackson-databind
  |      +-- jackson-core
  |      +-- jackson-annotations
  |
  +-- jackson-datatype-jsr310
  |
  +-- jackson-dataformat-yaml
```

Các cạnh trong graph biểu diễn quan hệ phụ thuộc; sơ đồ chỉ minh họa nhóm thư viện, không phải danh sách đầy đủ hoặc một cam kết về mọi cạnh phụ thuộc ở tất cả phiên bản.

Dependency được khai báo trực tiếp trong build file là **direct dependency**. Dependency được một thư viện khác kéo vào là **transitive dependency**. Project có thể không khai báo `jackson-core` trực tiếp nhưng vẫn nhận nó vì `jackson-databind` cần thư viện này.

Khi nhiều dependency yêu cầu các phiên bản khác nhau của cùng một artifact, công cụ build phải giải quyết xung đột. Nếu mỗi module Jackson được pin độc lập, graph có thể chứa những phiên bản không được kiểm thử cùng nhau. Hậu quả có thể là lỗi liên kết lớp hoặc phương thức khi chạy, lỗi serialize/deserialize, hoặc hành vi khác nhau giữa môi trường phát triển và CI.

## 2. BOM là gì?

BOM là viết tắt của **Bill of Materials**. Trong hệ sinh thái Maven, BOM thường là một POM có `packaging` là `pom`, tập trung khai báo các phiên bản dependency tương thích trong phần `dependencyManagement`.

Một BOM đóng vai trò như bảng quy ước phiên bản cho một nhóm thư viện. Với Jackson, BOM có thể quản lý phiên bản của `jackson-databind`, `jackson-core`, `jackson-annotations`, các datatype module và dataformat module thuộc cùng dòng phát hành.

BOM chủ yếu cung cấp **metadata quản lý phiên bản**. Bản thân việc import BOM không có nghĩa là tất cả thư viện được liệt kê trong BOM sẽ tự động trở thành dependency có mặt trên classpath của ứng dụng. Project vẫn phải khai báo những thư viện thực sự cần dùng.

Phân biệt hai việc:

- **Dependency declaration:** nói rằng project cần thư viện nào.
- **Dependency management:** nói rằng khi thư viện đó được sử dụng, phiên bản hoặc chính sách chọn phiên bản nào nên được áp dụng.

Đây là khác biệt quan trọng nhất khi đọc cấu hình BOM.

## 3. BOM của Jackson quản lý những gì?

Jackson được chia thành nhiều artifact. Một số artifact thường gặp:

| Artifact | Vai trò |
|---|---|
| `jackson-annotations` | Các annotation như `@JsonProperty`, `@JsonIgnore`, `@JsonCreator` |
| `jackson-core` | Nền tảng streaming với parser và generator JSON |
| `jackson-databind` | Ánh xạ giữa JSON và object Java |
| `jackson-datatype-jsr310` | Hỗ trợ các kiểu ngày giờ trong `java.time` |
| `jackson-dataformat-yaml` | Đọc và ghi dữ liệu YAML qua hệ sinh thái Jackson |

Các artifact trên có thể nằm trong những Maven group khác nhau nhưng vẫn thuộc cùng hệ sinh thái Jackson. Vì vậy, chỉ nhìn `groupId` để kết luận rằng các module có thể dùng phiên bản tùy ý là không an toàn.

Khi dùng Jackson BOM, project chọn một phiên bản BOM làm mốc. BOM đó cung cấp các phiên bản tương ứng cho những artifact mà nó quản lý. Nhờ vậy, khi thêm một module Jackson mới, người phát triển thường chỉ cần khai báo tọa độ thư viện mà không phải tự tìm và nhập lại phiên bản riêng.

Phiên bản ghi trong ví dụ bên dưới chỉ nhằm minh họa cú pháp. Khi áp dụng vào project, hãy chọn một phiên bản Jackson còn được hỗ trợ và tương thích với baseline Java, Spring Boot cùng các thư viện khác của ứng dụng.

## 4. Quản lý dependency bằng Maven

Maven phân biệt phần khai báo dependency của project với phần quản lý phiên bản trong `dependencyManagement`.

### 4.1. Import Jackson BOM

Đặt BOM trong `dependencyManagement` của `pom.xml`:

```xml
<properties>
    <!-- Phiên bản minh họa; thay bằng phiên bản đã được project phê duyệt. -->
    <jackson.version>2.17.2</jackson.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>${jackson.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Các thành phần cần chú ý:

- `groupId` và `artifactId` xác định BOM cần import.
- `version` chọn bộ metadata phiên bản.
- `type` là `pom`, vì BOM là một POM metadata.
- `scope` là `import`, cho Maven biết cần nhập các mục `dependencyManagement` của BOM vào cấu hình quản lý dependency hiện tại.

`scope=import` được dùng cho dependency kiểu POM trong `dependencyManagement`; đây không phải scope runtime hay compile của thư viện ứng dụng.

### 4.2. Khai báo thư viện mà project thực sự sử dụng

Sau khi import BOM, khai báo dependency trong phần `dependencies` bình thường:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-yaml</artifactId>
    </dependency>
</dependencies>
```

Các dependency không cần khai báo `<version>` vì Maven lấy phiên bản được quản lý từ BOM. Project vẫn chỉ nhận các thư viện đã khai báo trực tiếp cùng những dependency bắc cầu của chúng; import BOM không tự thêm toàn bộ module Jackson vào classpath.

Nếu một dependency có version được ghi trực tiếp trong `dependencies`, khai báo trực tiếp đó có thể làm lệch chính sách mà BOM đang cung cấp. Khi chủ đích là để BOM quản lý, nên bỏ version riêng khỏi các dependency thuộc BOM.

### 4.3. BOM và dependencyManagement trong Maven

`dependencyManagement` có thể được viết trực tiếp trong POM của project hoặc nhận các quy tắc từ một BOM được import. Nó cung cấp mặc định quản lý cho dependency khi chúng xuất hiện trong dependency graph.

Nó không thay thế `dependencies`:

```xml
<!-- Quản lý phiên bản, không tự thêm thư viện vào project. -->
<dependencyManagement>
    <dependencies>
        <!-- Các quy tắc quản lý dependency nằm ở đây. -->
    </dependencies>
</dependencyManagement>

<!-- Khai báo những thư viện project cần sử dụng. -->
<dependencies>
    <!-- Các dependency thực tế nằm ở đây. -->
</dependencies>
```

Maven cũng có thể dùng `dependencyManagement` để quản lý phiên bản của dependency bắc cầu. Vì thế, một project có thể kiểm soát phiên bản của artifact được thư viện khác kéo vào mà không cần khai báo artifact đó như một dependency trực tiếp chỉ để đặt version.

Khi nhiều BOM cùng quản lý một artifact, hoặc khi POM cha và POM con cùng khai báo chính sách cho artifact đó, cần xem xét thứ tự và độ ưu tiên của các quy tắc Maven. Không nên import nhiều BOM chồng lấn rồi giả định rằng BOM có version mới hơn luôn thắng. Hãy kiểm tra effective POM và dependency tree để biết Maven thực sự áp dụng phiên bản nào.

## 5. Quản lý dependency bằng Gradle

Gradle có cơ chế platform để tiêu thụ BOM. Một platform đưa các dependency constraint vào quá trình giải quyết dependency của configuration.

### 5.1. Dùng platform với Jackson BOM

Ví dụ với Gradle Groovy DSL:

```groovy
dependencies {
    implementation platform('com.fasterxml.jackson:jackson-bom:2.17.2')

    implementation 'com.fasterxml.jackson.core:jackson-databind'
    implementation 'com.fasterxml.jackson.datatype:jackson-datatype-jsr310'
    implementation 'com.fasterxml.jackson.dataformat:jackson-dataformat-yaml'
}
```

Ví dụ Kotlin DSL có cách viết tương đương:

```kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:2.17.2"))

    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml")
}
```

`platform(...)` thêm các constraint của BOM vào dependency graph. Nó không tự khai báo tất cả module Jackson là dependency của project. Các dòng `implementation` vẫn thể hiện thư viện mà ứng dụng cần sử dụng.

### 5.2. Platform và enforcedPlatform

Gradle cung cấp hai cách tiêu thụ platform thường gặp:

- `platform(...)` đưa các version constraint từ BOM vào quá trình giải quyết. Đây thường là lựa chọn phù hợp để bắt đầu vì vẫn cho Gradle áp dụng quy tắc giải quyết phiên bản và các constraint khác trong graph.
- `enforcedPlatform(...)` áp đặt phiên bản từ platform mạnh hơn, có thể ghi đè những yêu cầu phiên bản khác. Khi được công bố qua metadata của một thư viện, chính sách ép phiên bản có thể ảnh hưởng đến consumer của thư viện đó.

Không nên chọn `enforcedPlatform` chỉ vì muốn “chắc chắn mọi nơi cùng một version”. Nó có thể áp đặt quyết định lên cả dependency graph của module tiêu thụ. Hãy dùng khi project thực sự cần chính sách ép phiên bản và đã hiểu phạm vi ảnh hưởng.

Nếu cần ràng buộc chặt một artifact, Gradle còn có dependency constraints và rich version constraints như `strictly`, `prefer` hoặc `reject`. Tuy nhiên, với một nhóm module Jackson phát hành cùng nhau, quản lý bằng BOM thường thể hiện ý định đồng bộ rõ ràng hơn việc đặt constraint thủ công cho từng artifact.

## 6. BOM của Spring Boot và BOM của Jackson

Trong ứng dụng Spring Boot, BOM của Spring Boot thường đã quản lý phiên bản cho nhiều thư viện bên thứ ba, trong đó có các module Jackson phù hợp với dòng Spring Boot đang dùng.

Ví dụ, với Maven, project có thể kế thừa `spring-boot-starter-parent`, hoặc import `spring-boot-dependencies` BOM nếu không dùng parent POM. Với Gradle, project có thể dùng cơ chế dependency management được cấu hình cùng Spring Boot hoặc native Gradle platform.

Khi Spring Boot BOM đã quản lý Jackson, thông thường không cần import thêm Jackson BOM độc lập. Import thêm một BOM khác có thể tạo ra hai nguồn chính sách cùng quản lý `jackson-core`, `jackson-databind` hoặc các module khác. Nếu cần nâng Jackson ngoài phiên bản mà Spring Boot đang quản lý, phải xem xét ma trận tương thích của Spring Boot và toàn bộ Jackson module, sau đó cấu hình override có chủ đích.

Ví dụ Maven khi không kế thừa Spring Boot parent:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Khi đó, các dependency do Spring Boot BOM quản lý có thể được khai báo không cần version riêng. Giá trị `${spring-boot.version}` phải được định nghĩa ở nơi phù hợp trong POM.

Ví dụ Gradle native platform:

```groovy
dependencies {
    implementation platform("org.springframework.boot:spring-boot-dependencies:${springBootVersion}")
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Trong project thực tế, hãy tuân theo một cơ chế quản lý dependency nhất quán đã được cấu hình cho Spring Boot. Không thêm Jackson BOM thứ hai chỉ để lặp lại những phiên bản mà Boot BOM đã quản lý.

## 7. BOM khác gì version catalog và lockfile?

Ba khái niệm này thường xuất hiện cùng nhau nhưng giải quyết các vấn đề khác nhau.

| Cơ chế | Vai trò | Có tự thêm thư viện vào classpath không? |
|---|---|---|
| BOM / platform | Cung cấp chính sách hoặc constraint phiên bản cho một nhóm dependency | Không; project vẫn khai báo dependency cần dùng |
| Gradle version catalog | Đặt alias cho tọa độ, version và plugin để build file dễ đọc, tập trung hơn | Không; alias chỉ được dùng khi khai báo dependency/plugin |
| Dependency lockfile | Ghi lại phiên bản đã được resolve để những lần build sau giữ kết quả ổn định theo lock | Không; lock không thay thế dependency declaration |

Ví dụ version catalog có thể đặt alias `jackson-databind` để build file không phải lặp lại chuỗi tọa độ. Nhưng alias tự nó không phải BOM và không tự đồng bộ mọi dependency bắc cầu của Jackson. Có thể khai báo alias cho chính BOM rồi đưa alias đó vào `platform(...)`.

Lockfile cũng có vai trò khác: BOM mô tả chính sách phiên bản mong muốn, còn lockfile ghi nhận kết quả đã được chọn cho một configuration hoặc dependency graph. Khi cập nhật BOM, lockfile có thể cần được cập nhật có kiểm soát để phản ánh graph mới.

## 8. Vì sao nên đồng bộ phiên bản các module Jackson?

Jackson có các module phối hợp với nhau qua API và SPI. `jackson-databind` sử dụng nền tảng `jackson-core` và metadata từ `jackson-annotations`; các module như `jackson-datatype-jsr310` tích hợp vào Databind để cung cấp serializer/deserializer cho kiểu dữ liệu bổ sung.

Nếu các module không thuộc cùng bộ phiên bản tương thích, có thể phát sinh các vấn đề như:

- `NoSuchMethodError` hoặc `NoClassDefFoundError` khi runtime gặp API không có trong phiên bản class thực tế được nạp.
- Module không đăng ký hoặc không hoạt động như mong đợi do khác biệt API/SPI.
- Kết quả serialize/deserialize khác nhau giữa máy phát triển, môi trường kiểm thử và production vì dependency graph được resolve khác nhau.
- Lỗi chỉ xuất hiện ở một nhánh code ít được kiểm thử, khiến việc truy nguyên khó hơn.

BOM giảm rủi ro lệch phiên bản bằng cách cung cấp bộ version đã được dự định sử dụng cùng nhau. BOM không bảo đảm mọi phiên bản của mọi thư viện bên ngoài đều tương thích; project vẫn phải chọn BOM phù hợp với Java, Spring Boot và các dependency còn lại.

## 9. Kiểm tra dependency graph khi có xung đột

Khi gặp lỗi runtime hoặc nghi ngờ một module Jackson đang bị kéo vào sai phiên bản, hãy xem dependency graph đã được công cụ build resolve.

### 9.1. Maven

Xem các dependency Jackson trong graph:

```bash
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson
```

Xem POM sau khi Maven hợp nhất parent POM, profile và dependency management:

```bash
./mvnw help:effective-pom
```

`dependency:tree` cho biết dependency đến từ nhánh nào và phiên bản nào được chọn. `effective-pom` giúp kiểm tra BOM hoặc parent POM nào đang cung cấp quy tắc quản lý. Khi cần tập trung, có thể chuyển output effective POM vào file rồi tìm `jackson-databind`, `jackson-core` hoặc `jackson-bom`.

### 9.2. Gradle

Xem dependency graph của runtime:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Truy tìm lý do Gradle chọn một phiên bản cụ thể:

```bash
./gradlew dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
```

`dependencyInsight` hữu ích vì nó cho thấy những yêu cầu phiên bản, constraint và lý do chọn phiên bản. Khi lỗi chỉ xuất hiện ở compile hoặc test, hãy kiểm tra configuration tương ứng như `compileClasspath` hoặc `testRuntimeClasspath` thay vì mặc định cho rằng `runtimeClasspath` đại diện cho mọi trường hợp.

### 9.3. Quy trình xử lý xung đột

Khi thấy Jackson module có phiên bản không đồng bộ, hãy lần lượt:

1. Xác định module nào có phiên bản khác và configuration nào đang sử dụng nó.
2. Truy ngược dependency kéo phiên bản đó vào graph.
3. Kiểm tra project đang dùng Jackson BOM hay Spring Boot BOM, và quy tắc nào thực sự có hiệu lực.
4. Loại bỏ version khai báo riêng không cần thiết hoặc sửa chính sách BOM/constraint tại đúng nơi quản lý.
5. Chạy lại dependency report để xác nhận graph đã chọn phiên bản mong muốn.
6. Chạy compile và test liên quan để xác nhận thay đổi không làm hỏng tích hợp.

Không nên giải quyết xung đột bằng cách thêm một dependency cùng artifact ở nhiều nơi với các version khác nhau. Cách đó làm cấu hình khó hiểu và không xử lý tận gốc nguồn version conflict.

## 10. Những sai lầm thường gặp

### 10.1. Nghĩ rằng import BOM sẽ thêm mọi thư viện

Import BOM chỉ nhập chính sách quản lý. Nếu code sử dụng `JavaTimeModule`, project vẫn phải có dependency `jackson-datatype-jsr310` (trực tiếp hoặc thông qua một dependency khác phù hợp). Chỉ import BOM sẽ không cung cấp class `JavaTimeModule`.

### 10.2. Ghi version riêng cho từng module dù đã dùng BOM

Khi project đã chọn BOM làm nguồn quản lý, việc pin version riêng cho một module có thể tạo ra lệch phiên bản. Chỉ override khi có lý do kỹ thuật rõ ràng và đã kiểm tra tính tương thích.

### 10.3. Import nhiều BOM mà không kiểm tra thứ tự ưu tiên

Một artifact có thể được nhiều BOM quản lý. Không nên suy luận kết quả chỉ từ thứ tự file hoặc số version nhìn thấy. Hãy dùng `effective-pom`, `dependency:tree` hoặc `dependencyInsight` để xác nhận kết quả thực tế.

### 10.4. Nhầm version catalog với dependency constraints

Version catalog giúp đặt tên và tập trung khai báo. Nó không tự thay thế BOM hoặc cơ chế resolve phiên bản. Nếu cần đồng bộ cả nhóm artifact và dependency bắc cầu, hãy sử dụng platform/BOM hoặc constraints phù hợp.

### 10.5. Dùng enforcedPlatform như biện pháp chữa mọi xung đột

`enforcedPlatform` có thể áp đặt phiên bản lên graph rộng hơn dự kiến, đặc biệt khi metadata được truyền đến project tiêu thụ thư viện. Chỉ dùng khi chính sách ép phiên bản là yêu cầu thực sự; nếu không, ưu tiên `platform` và quản lý constraint rõ ràng.

## 11. Chọn cách quản lý phù hợp cho project

| Bối cảnh | Cách tiếp cận phù hợp |
|---|---|
| Project Java dùng trực tiếp nhiều Jackson module | Import Jackson BOM bằng Maven hoặc Gradle platform |
| Project Spring Boot dùng các starter thông thường | Ưu tiên BOM/dependency management mà Spring Boot đã cung cấp |
| Project cần thêm module Jackson nhưng giữ bộ version hiện tại | Khai báo module mới và để BOM hiện có quản lý version |
| Project cần nâng riêng Jackson khỏi version do Spring Boot quản lý | Kiểm tra tương thích rồi override có chủ đích tại một nguồn quản lý tập trung |
| Gradle build cần alias dependency dễ đọc | Dùng version catalog, có thể kết hợp với platform |
| CI cần tái lập dependency graph | Kết hợp chính sách version với dependency locking phù hợp |

Khi project có nhiều module Gradle hoặc nhiều POM Maven con, nên đặt chính sách version tại cấp quản lý chung phù hợp để các module không tự chọn những bộ Jackson khác nhau. Các module con vẫn khai báo đúng dependency mà chúng sử dụng; cấu hình trung tâm chịu trách nhiệm về version policy.

## 12. Ghi nhớ

BOM là metadata mô tả một bộ phiên bản dependency tương thích. Maven nhập BOM qua `dependencyManagement` với `type=pom` và `scope=import`; Gradle tiêu thụ BOM qua `platform(...)` hoặc `enforcedPlatform(...)`. Cả hai công cụ vẫn yêu cầu project khai báo các thư viện thực sự cần dùng.

Với Jackson, BOM giúp các module như Databind, Core, Annotations, datatype và dataformat đi cùng một chính sách phiên bản. Trong ứng dụng Spring Boot, hãy kiểm tra BOM của Spring Boot trước vì nó thường đã quản lý Jackson. Khi có xung đột, đọc dependency graph và effective configuration để tìm nguồn version thực tế, rồi sửa tại nguồn quản lý thay vì thêm các version rời rạc.
