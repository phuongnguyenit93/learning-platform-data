# Thu thập package tree, config và version để tái hiện

Khi một vấn đề Spring Modulith chỉ xuất hiện trong một dự án cụ thể, mô tả như “module không được nhận diện”, “verify báo dependency sai” hoặc “Named Interface không hoạt động” thường chưa đủ để tái hiện. Người hỗ trợ cần biết package nào đang tồn tại, metadata module được khai báo ra sao, dependency thực tế đang dùng phiên bản nào và lỗi xuất hiện trong môi trường nào.

Một bộ dữ liệu tái hiện tốt gồm ba nhóm chính:

1. **Package tree và metadata:** cho biết phạm vi module, package API, package nội bộ, named interface và vị trí các class liên quan.
2. **Build/config:** cho biết Spring Boot, Spring Modulith, plugin, BOM, cấu hình phát hiện module và các thiết lập ảnh hưởng đến hành vi.
3. **Version và môi trường:** cho biết phiên bản thực tế được resolve cùng JDK, build tool, hệ điều hành và lệnh đã chạy.

Mục tiêu là cung cấp đủ bằng chứng để người khác chạy lại cùng tình huống, đồng thời giữ bộ dữ liệu nhỏ và không làm lộ thông tin bí mật của dự án.

## 1. Bắt đầu từ triệu chứng có thể kiểm chứng

Trước khi thu thập file, hãy viết lại vấn đề thành một kết quả cụ thể. Ví dụ:

- `ApplicationModules.of(ShopApplication.class)` không phát hiện module `inventory`.
- `ApplicationModules.verify()` báo dependency từ `order` đến package nội bộ của `inventory`.
- `@NamedInterface("events")` không được nhận diện trong dependency `inventory::events`.
- Một listener hoặc Spring bean không được tạo trong application context.
- Cùng một commit chạy thành công trên máy này nhưng thất bại trong CI.

Ghi rõ hành vi mong đợi và hành vi thực tế. “Không hoạt động” chưa cho biết bước nào thất bại; hãy chỉ ra API, test, lệnh hoặc thao tác tạo ra lỗi.

Một mô tả tốt có dạng:

> Mong đợi `ApplicationModules.of(ShopApplication.class)` nhận diện `inventory` và `order` là hai module. Thực tế, test `verifiesModuleStructure` thất bại với thông báo về dependency đến `com.acme.shop.inventory.internal`. Lỗi xuất hiện trên commit `abc1234` khi chạy bằng JDK 21 và Gradle Wrapper của dự án.

## 2. Thu thập package tree của source code

Package tree giúp xác định package gốc, module con và vị trí class liên quan. Chỉ thu thập các source set có liên quan đến lỗi, thường là `src/main/java`, `src/main/kotlin` và `src/test/java`.

Trên Windows PowerShell, có thể xuất cây thư mục:

~~~powershell
tree /F src\main\java\com\acme\shop
tree /F src\test\java\com\acme\shop
~~~

Nếu dự án dùng Kotlin hoặc có nhiều source set, lấy thêm đúng thư mục liên quan:

~~~powershell
tree /F src\main\kotlin\com\acme\shop
~~~

Trên macOS hoặc Linux:

~~~bash
find src/main/java/com/acme/shop -type f | sort
find src/test/java/com/acme/shop -type f | sort
~~~

Nếu `tree` hoặc `find` tạo ra danh sách quá dài, giới hạn ở package gốc liên quan đến lỗi. Không cần gửi toàn bộ `build`, `target`, `.gradle`, `.git`, thư viện đã tải hoặc thư mục IDE.

Ngoài đường dẫn, hãy cung cấp package declaration và metadata. Có thể tìm các dòng quan trọng bằng `rg`:

~~~bash
rg -n "^(package |.*@ApplicationModule|.*@NamedInterface|.*@Modulithic)" src/main/java src/main/kotlin
~~~

Lệnh tìm kiếm có thể trả về nhiều kết quả. Chỉ đưa vào báo cáo những file thuộc phạm vi tái hiện, đặc biệt:

- Lớp ứng dụng có `@SpringBootApplication` hoặc lớp được truyền vào `ApplicationModules.of(...)`.
- `package-info.java` của base package module.
- `package-info.java` khai báo `@NamedInterface`.
- Class API và class implementation liên quan.
- Class import hoặc inject kiểu từ module khác.
- Publisher, event type và listener nếu lỗi liên quan đến application event.
- Architecture test hoặc context test tái hiện lỗi.

Package declaration trong source là căn cứ xác định tên package. Đường dẫn folder thường phản ánh package nhưng có thể khác trong source set hoặc cấu hình build tùy chỉnh.

## 3. Thu thập metadata module và ranh giới package

Với mỗi module liên quan, ghi lại các thông tin sau:

| Thông tin | Ví dụ | Vì sao cần |
| --- | --- | --- |
| Base package | `com.acme.shop.inventory` | Xác định module được phát hiện từ package nào |
| Module identifier | `inventory` | Đối chiếu dependency và `allowedDependencies` |
| Display name | `Inventory` | Phân biệt tên hiển thị với identifier |
| Public API | `InventoryManagement` | Xác định hợp đồng module công bố |
| Named interface | `inventory::events` | Xác định API bổ sung được công bố |
| Internal package | `inventory.internal` | Phân tích truy cập implementation |
| Allowed dependencies | `catalog::api` | Xác định allowlist mà module tiêu thụ khai báo |

Ví dụ metadata tại base package:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory",
    allowedDependencies = "catalog::api"
)
package com.acme.shop.inventory;
~~~

Ví dụ metadata tại package con:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.inventory.events;
~~~

Hãy gửi nguyên vẹn các file `package-info.java` liên quan, bao gồm cả Javadoc cấp package nếu nó giúp giải thích thiết kế. Đừng chỉ chép tên annotation ra khỏi ngữ cảnh vì vị trí package của annotation có ý nghĩa đối với mô hình.

Nếu ứng dụng dùng `@Modulithic`, hãy cung cấp phần khai báo trên lớp ứng dụng, nhất là các thuộc tính như `additionalPackages`, `sharedModules` hoặc `useFullyQualifiedModuleNames`. Những thuộc tính này có thể ảnh hưởng phạm vi phát hiện module hoặc cách đặt tên trong mô hình.

## 4. Thu thập cấu hình build có liên quan

Người tái hiện cần biết dự án quản lý dependency và plugin như thế nào. Với Gradle, các file thường cần xem gồm:

- `settings.gradle` hoặc `settings.gradle.kts` để biết module/project được include.
- `build.gradle` hoặc `build.gradle.kts` của application module.
- `gradle/libs.versions.toml` nếu dùng version catalog.
- `gradle/wrapper/gradle-wrapper.properties` để biết Gradle Wrapper.
- Các đoạn cấu hình `dependencyManagement`, platform/BOM và Java toolchain nếu được khai báo ở file khác.

Với Maven, thường cần:

- `pom.xml` của module ứng dụng.
- Parent POM hoặc phần `dependencyManagement` liên quan.
- Import BOM Spring Boot và Spring Modulith.
- Cấu hình compiler/plugin có ảnh hưởng đến Java version hoặc test.
- `mvnw` và `.mvn/wrapper/maven-wrapper.properties` nếu dự án dùng Maven Wrapper.

Không cần gửi mọi file cấu hình trong repository. Chọn phần có tác động đến dependency, plugin, source set, component scan hoặc test tái hiện lỗi.

Ví dụ Gradle:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
}

dependencies {
    implementation(platform("org.springframework.modulith:spring-modulith-bom:1.x.y"))
    implementation("org.springframework.modulith:spring-modulith-starter-core")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
}
~~~

Đây chỉ là ví dụ cấu trúc. Khi báo lỗi, hãy gửi giá trị thật từ dự án thay vì thay bằng version minh họa.

Ví dụ Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>1.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Nếu dùng Spring Boot parent hoặc BOM, hãy gửi phần khai báo đó. Không chỉ gửi một dependency đơn lẻ nếu version được quản lý ở parent hoặc platform khác.

## 5. Xác định version thực tế được resolve

Version ghi trong build file không phải lúc nào cũng là version cuối cùng được sử dụng. BOM, constraint, dependency substitution, plugin hoặc dependency bắc cầu có thể quyết định version thực tế.

### Gradle

Trước hết, ghi version của Java và Gradle:

~~~bash
java -version
./gradlew --version
~~~

Sau đó xem dependency cụ thể:

~~~bash
./gradlew dependencyInsight --dependency spring-modulith-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-modulith-events-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot --configuration runtimeClasspath
~~~

Nếu lỗi chỉ xảy ra trong test, kiểm tra thêm test runtime:

~~~bash
./gradlew dependencyInsight --dependency spring-modulith-core --configuration testRuntimeClasspath
~~~

Trong multi-project build, chạy task ở đúng project ứng dụng, ví dụ `./gradlew :shop-app:dependencyInsight ...`. Tên project phải lấy từ `settings.gradle` của chính dự án.

### Maven

Ghi version Maven và JDK:

~~~bash
java -version
./mvnw -version
~~~

Xem dependency Spring Modulith và Spring Boot đã resolve:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.modulith:*
./mvnw dependency:tree -Dincludes=org.springframework.boot:*
~~~

Nếu cần xác minh version được kế thừa hoặc quản lý qua parent/BOM, xem phần tương ứng trong effective POM. Không cần gửi toàn bộ effective POM nếu chỉ một nhóm dependency liên quan đến sự cố.

Khi báo cáo, phân biệt rõ:

- Version được khai báo trực tiếp trong build file.
- Version được quản lý bởi BOM hoặc version catalog.
- Version thực tế được resolve trong `compileClasspath`, `runtimeClasspath` hoặc test classpath.
- Version của plugin build, chẳng hạn Spring Boot Gradle plugin.

Không giả định version plugin Spring Boot luôn bằng version của mọi thư viện Spring Boot trong classpath.

## 6. Thu thập cấu hình Spring ảnh hưởng đến lỗi

Nếu sự cố liên quan đến module discovery, bean registration, event hoặc verification, hãy cung cấp đúng phần cấu hình liên quan:

| Nhóm | Nội dung cần thu thập |
| --- | --- |
| Application class | `@SpringBootApplication`, `@Modulithic`, package declaration |
| Module metadata | `@ApplicationModule`, `allowedDependencies`, `id`, `displayName` |
| Named interface | `@NamedInterface` và package declaration |
| Component scan | `scanBasePackages`, `@ComponentScan`, include/exclude filter |
| Bean registration | `@Bean`, `@Import`, configuration class liên quan |
| Event | Event type, publisher, `@ApplicationModuleListener`, transaction listener nếu có |
| Verification | Test gọi `verify()`, `detectViolations()` hoặc cấu hình `VerificationOptions` |
| Runtime profile | Profile đang active và các property liên quan đến hành vi lỗi |

Nếu lỗi phụ thuộc vào `application.yml`, `application.properties` hoặc profile cụ thể, chỉ gửi các key liên quan. Giữ nguyên tên property và cấu trúc, nhưng thay giá trị bí mật bằng placeholder rõ nghĩa.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://<host>:<port>/<database>
    username: <redacted>
    password: <redacted>
  profiles:
    active: <profile-name>
~~~

Không gửi password, token, API key, private key, certificate, cookie, connection string có credential hoặc giá trị bí mật từ biến môi trường. Không gửi nguyên file `.env`, secret manifest hay toàn bộ cấu hình production.

## 7. Ghi lại môi trường chạy

Hai máy dùng cùng source code vẫn có thể cho kết quả khác nhau do JDK, build tool, profile hoặc hệ điều hành.

Tối thiểu hãy ghi:

| Trường | Ví dụ |
| --- | --- |
| OS | Windows 11, Ubuntu 24.04, macOS |
| JDK vendor/version | Eclipse Temurin 21.0.x |
| Java runtime | Kết quả `java -version` |
| Build tool | Gradle Wrapper 8.x hoặc Maven Wrapper 3.x |
| Spring Boot | Version thực tế được resolve |
| Spring Modulith | Version thực tế được resolve |
| Build profile | Gradle project/task hoặc Maven profile đang dùng |
| Active Spring profile | `local`, `test`, `ci` hoặc tên tương ứng |
| Git revision | Commit hash của source đang tái hiện |

Có thể lấy revision:

~~~bash
git rev-parse --short HEAD
git status --short
~~~

Nếu working tree có thay đổi chưa commit, hãy nói rõ file nào đã được sửa và có liên quan đến lỗi hay không. Không cần gửi diff chứa dữ liệu nhạy cảm; chỉ gửi phần tối thiểu cần để tái hiện.

## 8. Thu thập lệnh chạy và lỗi nguyên vẹn

Ghi chính xác lệnh tạo ra lỗi, gồm task, test selector, profile và các flag quan trọng.

Ví dụ Gradle:

~~~bash
./gradlew test --tests "com.acme.shop.ModularityTests" --stacktrace
~~~

Ví dụ Maven:

~~~bash
./mvnw -Dtest=ModularityTests test
~~~

Khi gửi log:

- Giữ nguyên thông báo lỗi đầu tiên và exception gốc (`Caused by`) có liên quan.
- Gửi đủ phần stack trace cần thiết để thấy class và package liên quan.
- Không chỉ gửi ảnh chụp một dòng lỗi nếu có thể cung cấp text.
- Ghi rõ lệnh kết thúc với exit code nào và lỗi xuất hiện ở compile, test discovery, application context hay verification.
- Nếu lỗi không ổn định, ghi số lần chạy thành công/thất bại và điều kiện làm lỗi xuất hiện.

Nếu log quá dài, cắt phần không liên quan nhưng giữ nguyên exception đầu tiên, toàn bộ chuỗi `Caused by` liên quan và các frame trỏ về source của dự án. Thay token hoặc dữ liệu cá nhân bằng placeholder, không xóa mất cấu trúc exception.

## 9. Tạo một reproduction tối thiểu

Sau khi thu thập package tree và version, rút gọn tình huống thành các file cần thiết để thể hiện lỗi. Một reproduction cho lỗi module verification thường chỉ cần:

~~~text
src/main/java/com/acme/shop
├── ShopApplication.java
├── order
│   ├── package-info.java
│   └── OrderService.java
└── inventory
    ├── package-info.java
    ├── InventoryManagement.java
    └── internal
        └── InventoryManagementImpl.java
src/test/java/com/acme/shop
└── ModularityTests.java
~~~

Giữ lại:

1. Lớp ứng dụng để tạo `ApplicationModules`.
2. `package-info.java` của các module liên quan.
3. Các kiểu API và implementation cần thiết để tạo dependency.
4. Test nhỏ nhất tái hiện lỗi.
5. Phần build config đủ để resolve đúng version.

Loại bỏ logic nghiệp vụ không ảnh hưởng đến lỗi, dữ liệu thật, tích hợp bên ngoài và các module không liên quan. Nếu không thể tạo project tối thiểu, cung cấp một patch hoặc danh sách file đã lược bỏ để người khác có thể tái tạo trong checkout riêng.

Một reproduction hữu ích cần có cả hai điều kiện:

- Có thể chạy bằng một lệnh rõ ràng.
- Cho ra cùng lỗi hoặc kết quả quan sát được như báo cáo ban đầu.

Nếu đã lược bỏ một phần code và lỗi biến mất, ghi rõ phần nào đã bị bỏ. Điều đó có thể là manh mối về dependency hoặc cấu hình bị thiếu.

## 10. Chọn dữ liệu theo loại sự cố

Không phải lỗi nào cũng cần toàn bộ bộ dữ liệu. Dùng bảng sau để chọn đúng phần:

| Triệu chứng | Bằng chứng ưu tiên |
| --- | --- |
| Không phát hiện application module | Application class, base package, package tree, `additionalPackages`, module metadata |
| Không nhận diện named interface | Package tree, `package-info.java`, `@NamedInterface`, `allowedDependencies`, version Modulith |
| `verify()` báo dependency sai | Hai module liên quan, class tạo dependency, package metadata, thông điệp đầy đủ |
| Phát hiện cycle | Dependency liên quan ở cả hai chiều, event listener, API call, graph/verification output |
| Spring không tạo bean | Component scan, stereotype, `@Bean`/`@Import`, active profile, context exception |
| Chỉ lỗi trên CI | Git revision, JDK, build tool, resolved dependency, OS, profile và command |
| Kết quả khác giữa hai version | Dependency tree của cả hai môi trường, BOM/plugin, Java version và test tái hiện |
| Event listener không xử lý | Event class, publisher, listener annotation, transaction semantics, event publication configuration và integration test |

Thu thập dữ liệu theo triệu chứng giúp báo cáo gọn hơn và làm rõ giả thuyết cần kiểm tra.

## 11. Kiểm tra tính an toàn và khả năng tái lập của bộ dữ liệu

Trước khi chia sẻ, kiểm tra:

- Đã loại bỏ credential, token, key, cookie và thông tin kết nối nhạy cảm.
- Package tree không chứa tên khách hàng, tên dự án nội bộ hoặc đường dẫn máy cá nhân nếu không cần thiết.
- Log không chứa payload nghiệp vụ hoặc dữ liệu cá nhân thật.
- Build file không chứa repository credential hoặc secret được nhúng.
- Version được ghi là version thực tế, không chỉ version dự định.
- Commit hash và working tree state được ghi rõ.
- Lệnh chạy có thể thực hiện lại từ thư mục gốc dự án.
- Reproduction giữ nguyên package declaration và `package-info.java` liên quan.
- Không đính kèm thư mục cache, build output hoặc toàn bộ thư mục home.

Nếu cần chia sẻ qua issue công khai, hãy tạo reproduction đã khử nhạy cảm. Không tải source nội bộ hoặc cấu hình production lên dịch vụ công khai khi chưa được phép.

## 12. Mẫu báo cáo sự cố có thể sao chép

Có thể dùng mẫu sau để gửi cho người hỗ trợ:

~~~markdown
# Spring Modulith reproduction report

## 1. Symptom
- Expected:
- Actual:
- First failing test/operation:

## 2. Reproduction
- Repository/revision:
- Command:
- Exit code:
- Reproduction files:

## 3. Package tree
- Application base package:
- Related modules:
- Relevant package-info.java files:
- Public API / named interfaces:
- Internal packages involved:

## 4. Configuration
- Spring Boot configuration:
- @Modulithic:
- @ApplicationModule:
- @NamedInterface:
- allowedDependencies:
- Relevant component/event configuration:

## 5. Resolved versions
- JDK:
- Spring Boot:
- Spring Modulith:
- Gradle/Maven:
- Relevant resolved dependencies:

## 6. Environment
- OS:
- Active profile:
- Git revision and working tree state:

## 7. Error output
Paste the relevant complete exception and stack trace.

## 8. Sanitization
- Secrets redacted:
- Production/customer data removed:
- Other omissions:
~~~

Điền thông tin bằng giá trị thực của dự án. Nếu một mục không áp dụng, ghi `N/A`; nếu chưa xác định được, ghi `Unknown` thay vì đoán.

## 13. Những lỗi thường gặp khi thu thập reproduction

**Chỉ gửi package tree mà không gửi package metadata.** Hai package có cùng tên nhưng annotation `@ApplicationModule` hoặc `@NamedInterface` khác nhau có thể tạo mô hình khác nhau. Gửi các `package-info.java` liên quan.

**Chỉ gửi version trong build file.** Version thực tế có thể bị BOM hoặc dependency constraint điều chỉnh. Gửi kết quả dependency resolution của đúng classpath.

**Gộp version plugin và thư viện thành một giá trị.** Plugin Spring Boot, Spring Boot runtime và Spring Modulith là các thành phần riêng. Ghi từng version.

**Gửi toàn bộ `application.yml`.** File có thể chứa credential hoặc cấu hình production. Chỉ trích đoạn liên quan và khử bí mật.

**Chỉ gửi ảnh chụp log.** Text log giúp tìm exception gốc, package và class dễ hơn. Gửi thông điệp cùng stack trace dưới dạng text đã khử nhạy cảm.

**Không ghi lệnh chạy.** Cùng một test có thể cho kết quả khác khi chạy bằng task, profile hoặc classpath khác. Ghi nguyên lệnh đã tạo lỗi.

**Thu thập quá nhiều file.** Một reproduction lớn khiến người hỗ trợ khó tìm phần tạo lỗi. Bắt đầu từ module và class liên quan rồi chỉ mở rộng khi cần.

**Lược bỏ file metadata để làm reproduction nhỏ hơn.** Nếu lỗi liên quan module boundary, bỏ `package-info.java` có thể làm mất chính điều kiện gây lỗi.

**Không phân biệt lỗi kiến trúc và lỗi Spring context.** `ApplicationModules.verify()` kiểm tra mô hình module; `@SpringBootTest` kiểm tra khả năng khởi tạo context. Ghi rõ bước nào thất bại.

## 14. Checklist trước khi gửi báo cáo

- [ ] Mô tả expected và actual behavior bằng kết quả cụ thể.
- [ ] Cung cấp package tree của source set liên quan.
- [ ] Gửi application class và `package-info.java` của module liên quan.
- [ ] Cung cấp public API, named interface và class tạo dependency.
- [ ] Gửi phần build config, BOM và version catalog liên quan.
- [ ] Ghi JDK, build tool, Spring Boot và Spring Modulith version thực tế.
- [ ] Gửi dependency insight/tree của đúng classpath.
- [ ] Ghi OS, profile, commit hash và working tree state.
- [ ] Ghi lệnh tái hiện và exit code.
- [ ] Gửi exception cùng stack trace đã khử nhạy cảm.
- [ ] Tạo reproduction nhỏ nhất có thể chạy lại.
- [ ] Kiểm tra không còn secret hoặc dữ liệu production trong artifact.

## 15. Kết luận

Một báo cáo Spring Modulith có thể tái hiện cần mô tả được cấu trúc package, metadata module, cấu hình build, version thực tế và lệnh tạo lỗi. Package tree cho thấy module và class ở đâu; `package-info.java` giải thích ranh giới và API; dependency report cho biết thư viện nào thực sự được resolve; log cùng môi trường giúp người khác chạy lại cùng tình huống.

Hãy thu thập theo triệu chứng, giữ lại đúng những file tạo ra lỗi và khử mọi thông tin nhạy cảm trước khi chia sẻ. Khi bộ dữ liệu có thể chạy lại bằng một lệnh rõ ràng và cho cùng kết quả, người hỗ trợ có thể tập trung phân tích nguyên nhân thay vì phải đoán cấu trúc dự án hoặc version đang sử dụng.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Maven — Dependency Plugin: Tree Goal](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
