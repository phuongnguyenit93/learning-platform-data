# Ràng buộc phiên bản, dependency lock và khả năng tái lập build

Khi nâng cấp Java, việc chọn đúng phiên bản JDK chỉ là một phần của bài toán. Cùng một commit có thể build thành công hôm nay nhưng thất bại tuần sau nếu dependency transitively được cập nhật, một repository trả về artifact khác, plugin build đổi phiên bản, hoặc CI và máy cá nhân dùng toolchain không giống nhau. Nguy hiểm hơn, một dependency mới được chọn có thể tương thích với compiler nhưng làm thay đổi hành vi runtime: khác API, khác thuật toán, khác module metadata, hoặc yêu cầu phiên bản Java cao hơn.

**Ràng buộc phiên bản (version constraints)**, **dependency locking** và **reproducible build** là ba công cụ liên quan nhưng không đồng nghĩa. Constraints mô tả những phiên bản nào được chấp nhận hoặc ưu tiên; locking lưu kết quả chọn phiên bản cụ thể; reproducible build kiểm soát nhiều đầu vào và cách đóng gói để có thể tạo lại kết quả theo một hợp đồng đã xác định.

Bài học này đặt ba cơ chế đó trong bối cảnh **Java Advance Compatibility Migration**: từ kiểm kê dependency cũ, kiểm soát nâng cấp, tạo lockfile, đồng bộ BOM, đến tái lập artifact và kiểm tra khả năng chạy trên JDK đích. Ví dụ sử dụng Gradle và Maven ở mức minh họa; cú pháp và tính năng thực tế cần áp dụng theo phiên bản build tool mà dự án đã chọn.

## 1. Ba mục tiêu phải được tách riêng

Trước hết, hãy phân biệt ba câu hỏi:

1. **Được phép sử dụng phiên bản nào?** Đây là phạm vi của constraints, version ranges, BOM và các quy tắc xung đột phiên bản.
2. **Một lần build đã chọn chính xác phiên bản nào?** Đây là phạm vi của resolved dependency graph và dependency lock.
3. **Chạy lại cùng nguồn có tạo ra đúng artifact và hành vi mong đợi không?** Đây là phạm vi reproducibility và kiểm thử tương thích.

Ví dụ một ứng dụng có hai thư viện:

```text
application
  |
  +-- business-client:2.5.0
  |      |
  |      +-- json-core:2.2.0
  |
  +-- web-adapter:4.1.0
         |
         +-- json-core:2.4.0
```

Dự án khai báo trực tiếp hai thư viện, nhưng phải chọn một phiên bản `json-core` trong cấu hình runtime. Nếu Gradle hoặc Maven áp dụng cơ chế resolution khác nhau, phiên bản được chọn cũng có thể khác.

Giả sử phiên bản `json-core:2.4.0` thay đổi một API hoặc chuyển sang bytecode yêu cầu JDK mới. Một ứng dụng đang nâng từ Java 17 sang 21 có thể đột nhiên sử dụng phiên bản này mà không sửa dòng khai báo dependency trực tiếp nào. Ngược lại, nếu một phiên bản có lỗi bảo mật đã bị khóa quá lâu, build có thể tái lập được nhưng vẫn **không an toàn**.

Vì vậy, không được đánh đồng:

| Khái niệm | Trả lời câu hỏi | Không bảo đảm |
|---|---|---|
| Version constraint | Phiên bản nào được chấp nhận, ưu tiên hoặc từ chối? | Phiên bản đang được chọn luôn giống nhau giữa các lần build |
| BOM/dependency management | Những module nào nên dùng phiên bản đồng bộ? | Toàn bộ dependency graph đã bị khóa tuyệt đối |
| Dependency lock | Kết quả resolution cho các dependency được quản lý là gì? | Byte của artifact, plugin, JDK và môi trường đều giống nhau |
| Checksum/signature verification | Artifact có đúng nội dung/nguồn tin cậy kỳ vọng? | Phiên bản đó tương thích với mã hoặc không có lỗ hổng |
| Reproducible artifact build | Cùng đầu vào có thể sinh byte đầu ra như nhau? | Artifact hoạt động đúng nghiệp vụ trong production |
| Compatibility test | Bản ứng dụng có hoạt động trong tổ hợp JDK/dependency cụ thể? | Repository không thay đổi trong những lần build khác |

Ba lớp đầu là nội dung trọng tâm, nhưng migration đáng tin cậy cần kết hợp cả các lớp sau.

## 2. Dependency trực tiếp, bắc cầu và kết quả resolution

### 2.1. Direct và transitive dependency

Một project thường khai báo direct dependency:

```groovy
dependencies {
    implementation 'org.example:business-client:2.5.0'
    implementation 'org.example:web-adapter:4.1.0'
}
```

Các module này có thể khai báo dependency riêng. Gradle hoặc Maven xây dựng một đồ thị, giải quyết các xung đột phiên bản, rồi tạo classpath/module path cho compile, test và runtime.

Một ứng dụng có thể có nhiều cấu hình:

- Compile classpath.
- Runtime classpath.
- Test compile classpath.
- Test runtime classpath.
- Annotation processor path.
- Plugin/buildscript classpath.
- Cấu hình custom của code generator, native tooling hoặc integration test.

Không nên kiểm tra mỗi runtime dependency rồi kết luận mọi configuration dùng cùng phiên bản. Compiler plugin, annotation processor hoặc test runner có thể tương thích với một JDK nhưng không tương thích với JDK khác.

### 2.2. Khác biệt resolution giữa Gradle và Maven

**Gradle** thường sử dụng cơ chế chọn phiên bản theo rules/metadata và conflict resolution; khi có nhiều yêu cầu phiên bản tương thích, mặc định thường ưu tiên phiên bản cao hơn, trừ khi constraints, capabilities hoặc rule khác điều chỉnh. Cơ chế thực tế còn phụ thuộc nền tảng, metadata và cách khai báo.

**Maven** thường dùng dependency mediation theo **nearest definition**: dependency gần root hơn trong đồ thị có thể được chọn; nếu cùng độ sâu, thứ tự khai báo có thể ảnh hưởng. `dependencyManagement` có thể quản lý phiên bản được sử dụng khi dependency được tham chiếu.

Ví dụ:

```text
app
  +-- A:1.0 -> X:1.5
  +-- B:1.0 -> X:2.0
```

Đừng cho rằng hai build tool chắc chắn ra cùng phiên bản `X`. Cần chạy báo cáo dependency graph bằng chính tool và phiên bản đang được dùng.

### 2.3. Resolved graph mới là đầu vào thực tế

Khi gặp lỗi `NoSuchMethodError`, `ClassNotFoundException` hoặc `UnsupportedClassVersionError`, thông tin trong source declaration chưa đủ. Phải biết:

- Module và phiên bản thực sự có trên classpath.
- Phiên bản nào bị thay thế bởi conflict resolution.
- Module đó được đưa vào từ nhánh dependency nào.
- Artifact thực tế được repository nào cung cấp.
- Compile và runtime có chọn cùng phiên bản không.
- Module mới yêu cầu class-file version/JDK tối thiểu nào.

Một dependency graph được lưu trong CI cùng build metadata giúp tái hiện lỗi và hỗ trợ rollback đáng tin cậy.

## 3. Version constraints là chính sách, không phải lockfile

### 3.1. Fixed version, dynamic version và version range

Một số kiểu khai báo:

| Kiểu | Ví dụ | Ý nghĩa |
|---|---|---|
| Fixed version | `2.3.4` | Yêu cầu một phiên bản cụ thể trong declaration, nhưng resolution vẫn chịu tác động conflict rules |
| Gradle dynamic version | `2.+` hoặc `latest.release` | Có thể chọn phiên bản mới khi metadata thay đổi |
| Version range | `[2.0,3.0)` | Cho phép một dải phiên bản |
| Changing module | `2.3.4-SNAPSHOT` hoặc module được đánh dấu changing | Artifact/metadata có thể thay đổi dù identifier không đổi |
| Strict constraint | `strictly("2.3.4")` ở Gradle | Hạn chế mạnh những phiên bản chấp nhận được |
| Preferred version | `prefer("2.3.4")` ở Gradle | Thể hiện ưu tiên nhưng có thể bị yêu cầu mạnh hơn ghi đè |

Một chuỗi version nhìn cố định chưa bảo đảm kết quả được cố định: nếu repository cho ghi đè artifact cùng version, cùng coordinates vẫn có thể nhận byte khác. Ngược lại, một dependency dùng range vẫn có thể được chọn nhất quán nhờ lockfile, cho đến khi lock được cập nhật theo quy trình.

### 3.2. SemVer chỉ là cam kết của nhà phát hành

Một thư viện đánh version `2.3.4` theo Semantic Versioning có thể hứa rằng patch release không phá API. Tuy nhiên:

- Không phải thư viện nào cũng áp dụng SemVer nghiêm ngặt.
- “Không phá API” có thể chỉ nói đến source compatibility, không bao gồm Java serialization, bytecode, configuration hoặc behavior.
- Một bản minor có thể nâng JDK tối thiểu.
- Một bản dependency mới có thể đổi native library hoặc module metadata.
- Một bug fix có thể tác động đến business logic đang phụ thuộc hành vi cũ.

Hãy coi versioning là tín hiệu hữu ích; chỉ kiểm thử và compatibility contract cụ thể mới cho biết build có phù hợp với migration của dự án hay không.

## 4. Constraints trong Gradle

### 4.1. Khai báo constraint cho dependency bắc cầu

Trong một module Gradle dùng Groovy DSL:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'com.example:application-client:4.0.0'

    constraints {
        implementation('org.example:json-core') {
            version {
                strictly('2.4.3')
            }
            because 'Phiên bản này đã được kiểm thử với JDK mục tiêu'
        }
    }
}
```

`constraints` cho biết quy tắc lựa chọn phiên bản khi module `org.example:json-core` tham gia vào cấu hình. Constraint không tự thêm dependency đó vào classpath nếu chưa có yêu cầu nào đưa nó vào. Nó là chính sách cho đồ thị, không nhất thiết là một direct dependency mới.

`strictly` có thể khiến resolution thất bại khi một module khác yêu cầu phiên bản không tương thích. Đây đôi khi là điều đúng: thay vì âm thầm chọn phiên bản chưa kiểm thử, build báo xung đột để developer quyết định.

### 4.2. Prefer, require và strictly khác nhau

Gradle rich version constraints có thể biểu diễn nhiều mức chính sách. Ví dụ minh họa:

```groovy
dependencies {
    constraints {
        implementation('org.example:codec') {
            version {
                require('[3.1,4.0)')
                prefer('3.4.2')
                reject('3.2.0')
            }
            because 'Chỉ dùng nhánh 3.x đã được xác nhận'
        }
    }
}
```

Ý nghĩa khái quát:

- `require` đặt yêu cầu phiên bản, có thể cho phép cơ chế conflict resolution chọn bản cao hơn khi tương thích.
- `prefer` bày tỏ phiên bản mong muốn, không có cùng sức ràng buộc như strict.
- `strictly` giới hạn những phiên bản được chấp nhận, khiến xung đột hiện ra rõ hơn.
- `reject` loại một hoặc nhiều phiên bản không được phép.

Các khai báo này có thể được phối hợp theo cú pháp Gradle đang dùng, nhưng không nên dùng quá nhiều rule phức tạp mà không có lý do nghiệp vụ hoặc compatibility rõ ràng.

### 4.3. Force không nên là phản xạ đầu tiên

Một số dự án dùng:

```groovy
configurations.configureEach {
    resolutionStrategy {
        force 'org.example:json-core:2.4.3'
    }
}
```

`force` có thể ép kết quả chọn phiên bản, nhưng cũng có thể che nhu cầu thực tế của dependency khác và làm xung đột biến mất khỏi tầm nhìn.

Trong migration, ưu tiên:

1. Xem đường đi đưa dependency vào.
2. Hiểu vì sao các module yêu cầu các version khác nhau.
3. Chọn version được hỗ trợ theo compatibility matrix.
4. Dùng BOM/platform và constraints có lý do rõ ràng.
5. Chỉ force khi có quyết định có kiểm thử và ghi lại cách tháo bỏ.

Không dùng `force` để chữa `NoSuchMethodError` mà chưa xác định binary compatibility của các caller.

### 4.4. Constraint không thay thế version lock

Giả sử chỉ khai báo khoảng `[2.0,3.0)`. Hôm nay Gradle chọn `2.4.3`; sau khi repository có `2.5.0`, một lần resolution mới có thể chọn phiên bản khác. Lockfile lưu **kết quả** đã chọn để những lần build sau không tự cập nhật vô tình.

Đây chính là lý do cần kết hợp chính sách phiên bản và dependency locking.

## 5. Gradle platforms, BOM và alignment

### 5.1. Dùng platform cho một họ module

Khi thư viện gồm nhiều artifact phải dùng phiên bản tương thích lẫn nhau, hãy cân nhắc BOM hoặc platform.

Ví dụ:

```groovy
dependencies {
    implementation platform('org.example:framework-bom:5.2.0')

    implementation 'org.example:framework-core'
    implementation 'org.example:framework-http'
    implementation 'org.example:framework-json'
}
```

`platform` cho phép import dependency constraints từ BOM. Nếu BOM quản lý version các module, consumer có thể bỏ version cụ thể trong từng dependency declaration.

Lợi ích:

- Tránh module core phiên bản này, module HTTP phiên bản khác.
- Đơn giản hóa nâng cấp một họ dependency.
- Truyền chính sách phiên bản tới các module có liên quan.
- Dễ thấy bản BOM đã được chọn cho migration.

Nhưng BOM không chứng minh các transitive dependencies bên ngoài BOM đều an toàn với JDK mới.

### 5.2. `platform` và `enforcedPlatform`

Trong Gradle, `enforcedPlatform` thể hiện yêu cầu mạnh hơn và có thể tác động đến consumer của thư viện khi được công bố. Đây không phải lựa chọn mặc định phù hợp cho mọi library.

Ví dụ:

```groovy
dependencies {
    implementation enforcedPlatform(
        'org.example:framework-bom:5.2.0'
    )
}
```

Nếu một project là library được nhiều ứng dụng tiêu thụ, việc cưỡng ép phiên bản của cả một họ module có thể làm giảm quyền lựa chọn của consumer. Hãy ưu tiên `platform` và constraints thích hợp, dùng `enforcedPlatform` khi đã hiểu hệ quả ở graph tiêu thụ.

### 5.3. Platform không giải quyết mọi loại xung đột

Các thư viện có thể mang metadata capability, biến thể (variants), native classifiers hoặc yêu cầu JVM target khác nhau. Căn chỉnh version không bảo đảm mọi biến thể đều tương thích.

Khi nâng JDK, cần kiểm tra:

- Module metadata và Gradle attributes.
- Target JVM của artifact.
- Các dependency tùy chọn và annotation processors.
- Các native classifier cho OS/architecture.
- API bị loại bỏ hoặc chuyển module.
- Runtime configuration chứ không chỉ compile configuration.

## 6. Version catalogs: nơi khai báo dễ quản lý, không phải lock

Version catalog của Gradle thường đặt tại `gradle/libs.versions.toml`:

```toml
[versions]
framework = "5.2.0"
json = "2.4.3"
junit = "5.11.0"

[libraries]
framework-core = { module = "org.example:framework-core", version.ref = "framework" }
json-core = { module = "org.example:json-core", version.ref = "json" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }

[plugins]
# Plugin versions có thể được quản lý riêng tại đây.
```

Trong build file:

```groovy
dependencies {
    implementation libs.framework.core
    implementation libs.json.core
    testImplementation libs.junit.jupiter
}
```

Catalog giúp thống nhất declaration trong multi-project build và giảm trùng lặp version literals. Nhưng:

- Catalog không khóa mọi transitive dependency.
- Catalog không lưu resolved graph cho từng configuration.
- Catalog không bảo đảm repository không thay byte.
- Catalog không tự khóa Gradle distribution/JDK/plugin build.
- Chỉ sửa catalog mà không cập nhật lock có thể tạo xung đột theo chính sách locking.

Nên xem catalog, BOM và lockfile là ba lớp bổ trợ thay vì ba giải pháp thay thế nhau.

## 7. Dependency locking trong Gradle

### 7.1. Lockfile giữ kết quả resolution

Gradle cung cấp dependency locking để lưu các version đã được giải quyết và sử dụng chúng trong những lần resolution sau. Điều này đặc biệt quan trọng nếu còn dynamic dependency hoặc thay đổi graph qua các bản build tool.

Ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
}

dependencyLocking {
    lockAllConfigurations()
}

dependencies {
    implementation 'org.example:business-client:4.0.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}
```

Ví dụ trên áp dụng locking tới các configuration tương ứng khi được resolve; các configuration không được resolve trong lúc tạo lock có thể cần một thao tác riêng. Nội dung lockfile và cách kích hoạt locking có thể khác giữa các phiên bản Gradle. Không coi mọi configuration đã được khóa chỉ vì block trên có mặt.

### 7.2. Tạo lockfile

Một luồng thường gặp:

```shell
./gradlew :app:dependencies --configuration runtimeClasspath --write-locks
```

Ở cấu hình ví dụ, Gradle resolve `runtimeClasspath` và có thể ghi hoặc cập nhật lock state cho các configuration được resolve. Nếu muốn lock compile/test/annotation processor hoặc các configuration khác, cần chạy những task giải quyết chúng theo chiến lược đã chọn.

Trong một multi-project build, hãy có bước chuẩn hóa tạo/cập nhật lock cho các project và configuration quan trọng. Tệp lock hiện đại có thể mang tên `gradle.lockfile` tại từng project tùy Gradle version và cấu hình.

**Không nên tự chỉnh sửa thủ công toàn bộ lockfile bằng find/replace.** Hãy dùng cơ chế resolution chính thức để thay đổi graph rồi review diff.

### 7.3. Đọc lockfile đúng nghĩa

Một lockfile chứa tập phiên bản module đã được lựa chọn cho phạm vi khóa, không phải bản copy của toàn bộ JAR. Ví dụ minh họa:

```text
org.example:business-client:4.0.0=runtimeClasspath
org.example:json-core:2.4.3=runtimeClasspath
empty=testCompileClasspath
```

Đây chỉ là ví dụ cách diễn đạt lock state; định dạng và nội dung chính xác thuộc phiên bản Gradle. Khi gặp trạng thái `empty` hoặc tên configuration trong file, phải hiểu theo cơ chế locking của tool thay vì xem đó là một dependency.

Không suy luận từ lockfile rằng **artifact bytes** đã được xác thực. Vẫn cần dependency verification hoặc checksum/signature phù hợp.

### 7.4. Cập nhật dependency có kiểm soát

Khi muốn nâng một module cụ thể, Gradle hỗ trợ cơ chế selective update locks, ví dụ:

```shell
./gradlew :app:dependencies \
    --configuration runtimeClasspath \
    --update-locks org.example:json-core
```

Ví dụ có dấu tiếp dòng kiểu Unix shell. Trên Windows PowerShell, chạy lệnh một dòng hoặc sử dụng cú pháp tiếp dòng phù hợp.

Nếu module được chọn bản mới, lock diff cho biết những thay đổi đã được resolution tạo ra. Có thể phát sinh thay đổi transitive dependency khác; cần review toàn bộ diff, không chỉ dòng module chính.

Một quy trình upgrade hợp lý:

1. Tạo nhánh thay đổi dependency và version declaration.
2. Chạy resolution cập nhật lock một cách có mục đích.
3. Xem diff trong lockfile.
4. Kiểm tra license, CVE, release notes và compatibility.
5. Chạy unit/integration tests và thử trên JDK target.
6. Commit declaration, lockfile và metadata liên quan trong cùng một thay đổi.

### 7.5. Lock phải được commit

Nếu mỗi developer giữ lockfile local và không commit, CI sẽ không có cùng tập dependency. Hãy đưa lockfile vào version control, cùng phiên bản build scripts và version catalog.

Một lock diff không phải nhiễu vô nghĩa: nó là bằng chứng rằng graph được chọn đã thay đổi. Trong code review, nên hỏi:

- Vì sao version này thay đổi?
- Đây có phải patch bảo mật hay nâng major/minor?
- Những transitive modules nào đi kèm?
- Bản mới hỗ trợ JDK mục tiêu không?
- Có artifact nào đổi metadata hoặc classifier không?
- Có test liên quan và hướng rollback không?

### 7.6. Lock có giới hạn về phạm vi

Gradle dependency locking không tự động đồng nghĩa mọi đầu vào build đều bất biến. Cần xem xét riêng:

- Plugin versions và plugin resolution.
- Buildscript classpath/custom plugin builds.
- Toolchains/JDK distribution.
- Gradle Wrapper version.
- Native toolchain và compiler khác.
- Remote data hoặc code generation tải qua URL trực tiếp.
- Generated artifacts và annotation processor.
- Environment variables và timestamps.
- Repository có cho overwrite cùng version không.

Các scope ngoài graph đã lock cần được quản lý bằng chính sách riêng.

## 8. Maven: dependencyManagement, BOM và phiên bản tường minh

### 8.1. Maven không có lockfile native tương đương Gradle theo mặc định

Trong Maven, chiến lược phổ biến để kiểm soát phiên bản gồm:

- Cố định version của direct dependencies.
- Dùng `dependencyManagement` trong parent POM.
- Import BOM.
- Dùng Maven Enforcer rules.
- Ghi dependency tree/effective POM cho mục đích kiểm tra.
- Dùng extension/plugin nếu tổ chức cần dependency locking có hành vi riêng.

Không nên trình bày `dependencyManagement` là dependency lock tuyệt đối. Nó quản lý version policy của các artifact được tham chiếu, nhưng kết quả build vẫn có thể bị tác động bởi thay đổi trong POM, dependency ranges, SNAPSHOT, plugin, repository và môi trường.

### 8.2. Cấu hình dependencyManagement

Ví dụ POM có versions cố định:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>json-core</artifactId>
      <version>2.4.3</version>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>org.example</groupId>
    <artifactId>json-core</artifactId>
  </dependency>
</dependencies>
```

`dependencyManagement` chọn version khi module được đưa vào dependency graph. Nó không tự động đưa module `json-core` vào ứng dụng chỉ vì có entry trong block quản lý.

Nếu nâng JDK làm cần `json-core:2.5.0`, có thể thay version quản lý và chạy regression test. Nhưng phải xem các dependency khác có yêu cầu API khác không.

### 8.3. Import Maven BOM

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>platform-bom</artifactId>
      <version>5.2.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
```

Một BOM có thể tập trung các version được thử nghiệm cùng nhau. Khi nâng từ một dòng framework lên dòng khác, việc đổi BOM thường minh bạch hơn sửa hàng chục thư viện riêng lẻ.

Nhưng BOM vẫn cần được kết hợp với:

- Kiểm tra dependency tree.
- Pin plugin versions.
- Toolchain/JDK policy.
- Kiểm tra artifact integrity.
- Tái lập build và compatibility test.

### 8.4. Nearest-wins có thể gây bất ngờ

Trong Maven, nếu hai nhánh mang một transitive dependency khác version, cơ chế mediation có thể chọn phiên bản theo khoảng cách đến root. Thêm một direct dependency hoặc thay thứ tự trong POM có thể thay kết quả ở một tình huống cùng độ sâu.

Để chẩn đoán:

```shell
mvn dependency:tree
```

Có thể dùng filters và verbose output theo phiên bản Maven Dependency Plugin. Nên pin version plugin trong build chính thức, bởi cách viết ngắn như trên có thể phụ thuộc plugin resolution của môi trường.

Đừng coi dependency tree chỉ là một tệp tham khảo; nó phản ánh classpath dự kiến và phải được review khi chuyển Java version.

## 9. Maven Enforcer và kiểm tra dependency convergence

### 9.1. Vì sao cần fail thay vì “build được là đủ”?

Một dependency graph có hai phiên bản gây xung đột có thể vẫn resolve thành một phiên bản và compile thành công. Nhưng runtime mới lộ lỗi binary compatibility.

Maven Enforcer Plugin có thể giúp chặn một số cấu hình không mong muốn bằng những rules như:

- `dependencyConvergence`: phát hiện các đường đi đưa các phiên bản khác nhau của cùng dependency vào graph.
- `requireUpperBoundDeps`: kiểm tra phiên bản được chọn đáp ứng những ràng buộc liên quan đến upper bound.
- `requireMavenVersion`: kiểm soát Maven tối thiểu.
- `requireJavaVersion`: yêu cầu một dải JDK nhất định.
- Các rules khác từ plugin hoặc extension được tổ chức phê duyệt.

Một ví dụ cấu hình:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-enforcer-plugin</artifactId>
      <version>3.5.0</version>
      <executions>
        <execution>
          <id>enforce-dependencies</id>
          <goals>
            <goal>enforce</goal>
          </goals>
          <configuration>
            <rules>
              <dependencyConvergence/>
              <requireUpperBoundDeps/>
            </rules>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

Version trong ví dụ chỉ phục vụ minh họa cú pháp; dự án phải dùng phiên bản plugin đã được lựa chọn và thử với build thực tế. Rules có thể gây thất bại trên graph hiện tại và cần remediation, không nên vô hiệu hóa hàng loạt cho “xanh CI”.

### 9.2. Enforcer không thay thế testing

Một graph hội tụ về một phiên bản duy nhất vẫn có thể không tương thích:

- Jar chứa bytecode quá mới cho JDK cũ.
- Method/constructor đã bị loại bỏ.
- Module encapsulation làm reflection thất bại.
- Native dependency không có classifier phù hợp.
- Config default hoặc serialization behavior thay đổi.

Enforcer là gate về chính sách dependency. Compatibility testing là một gate khác.

### 9.3. Plugin versions cũng cần cố định

Ví dụ cấu hình:

```xml
<build>
  <pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </pluginManagement>
</build>
```

Cần kiểm soát những plugin thực sự được sử dụng trong lifecycle. Cấu hình ở `pluginManagement` là nơi quản lý version/config; không phải plugin nào được đặt ở đó cũng tự động được thực thi.

## 10. Dynamic versions và SNAPSHOT: nguồn gốc build không lặp lại

### 10.1. Gradle dynamic versions

Khai báo:

```groovy
dependencies {
    implementation 'org.example:codec:2.+'
}
```

làm Gradle có thể chọn bản phù hợp mới nhất trong một nhóm, theo caching và metadata hiện có. Khi repository được cập nhật, cùng commit có thể resolve phiên bản khác.

Dynamic version có thể hữu ích trong thí nghiệm hoặc trong một số workflow cập nhật tự động, nhưng không thích hợp làm chính sách mặc định của release không có lock và review.

### 10.2. Maven version ranges

Maven có cú pháp version range như:

```xml
<dependency>
  <groupId>org.example</groupId>
  <artifactId>codec</artifactId>
  <version>[2.0,3.0)</version>
</dependency>
```

Nếu repository công bố thêm bản phù hợp, kết quả resolution có thể thay đổi. Đối với release build cần khả năng truy vết, thường nên chọn version cụ thể và thực hiện nâng cấp có review.

### 10.3. SNAPSHOT và changing modules

`1.0-SNAPSHOT` trong Maven hoặc dependency được đánh dấu changing ở Gradle có thể đại diện cho artifact được build lại nhiều lần trong cùng một version logic.

Điều này làm phát sinh:

- Metadata snapshot được cập nhật.
- Artifact cùng logical version nhưng byte khác.
- Cache khác nhau giữa máy/CI.
- Rollback khó truy tìm.
- Kiểm thử hôm nay không bảo đảm artefact ngày mai giống nhau.

Trong release production, ưu tiên immutable version/digest. Nếu dùng SNAPSHOT cho phát triển, tách rõ pipeline snapshot và release, không quảng bá snapshot như một bản phát hành có thể tái tạo lâu dài.

### 10.4. Cache có thể che thay đổi

Gradle, Maven và repository proxy có cơ chế cache metadata/artifact. Hai máy build có thể nhận kết quả khác nhau do:

- Một máy đã cache version trước.
- Một máy truy cập repository mới.
- Metadata dynamic version đã hết thời gian cache.
- Proxy mirror đồng bộ chậm.
- CI bật chế độ offline hoặc có local repository cũ.

Một build tình cờ thành công nhờ cache không chứng minh dependency resolution được xác định tốt. Khi cần điều tra, hãy so sánh resolved graph, repository source, checksum và cache state; không chỉ xóa toàn bộ cache mà bỏ qua nguyên nhân.

## 11. Repository và artifact immutability

### 11.1. Một coordinates phải xác định một nội dung phát hành

Một artifact Maven thường được định danh bằng:

```text
groupId:artifactId:version[:classifier][@extension]
```

Nếu release repository cho overwrite `org.example:codec:2.4.3` bằng byte mới, lockfile giữ nguyên version vẫn không bảo đảm tải về nội dung giống trước. Đó là lý do chính sách **immutable release artifacts** rất quan trọng.

Cần:

- Không ghi đè release version.
- Kiểm tra checksum/signature nếu hạ tầng hỗ trợ.
- Giới hạn quyền publish.
- Có audit và provenance của nguồn build.
- Dùng repository proxy/mirror được quản trị.
- Lưu artifact gốc của bản phát hành quan trọng.

### 11.2. Thứ tự repositories có thể làm kết quả khác nhau

Một project có thể dùng cả public repository và private repository:

```groovy
repositories {
    maven {
        url = uri('https://repo.example.invalid/releases')
    }
    mavenCentral()
}
```

Nếu cùng tọa độ artifact xuất hiện ở nhiều kho nhưng nội dung khác nhau, quy tắc chọn repository và metadata của build tool trở nên quan trọng. Hãy quy định rõ origin cho internal artifacts, tránh public namespace collision và áp dụng repository content filters khi phù hợp.

URL `example.invalid` chỉ là địa chỉ minh họa. Trong hệ thống thật cần kiểm soát TLS, credentials và quyền truy cập.

### 11.3. Dependency confusion không được giải quyết chỉ bằng lock

Một lockfile có thể lưu version nhưng không đủ để bảo đảm artifact đến từ kho đáng tin cậy. Nếu attacker công bố package cùng tên/coordinates vào một nguồn được build ưu tiên, hoặc repository cấu hình sai, vẫn có rủi ro supply chain.

Các biện pháp có thể gồm:

- Group namespace nội bộ rõ ràng.
- Repository content policies.
- Artifact verification bằng checksum/signature/trust policy.
- Private repository được quản lý.
- CI không có quyền publish tùy tiện.
- SBOM và provenance của release.

## 12. Dependency verification khác dependency locking

### 12.1. Lock phiên bản không xác minh byte

Hai build có thể cùng resolve `org.example:codec:2.4.3` nhưng tải các JAR khác nhau nếu upstream bị ghi đè hoặc repository bị can thiệp. Lockfile chỉ kiểm soát **version resolution**, không xác định nội dung binary ở mức byte.

Gradle hỗ trợ dependency verification qua metadata, có thể bao gồm checksums và chữ ký. Một workflow minh họa:

```shell
./gradlew --write-verification-metadata sha256 help
```

Tùy cấu hình và những dependencies được resolve, công cụ có thể tạo metadata file như `gradle/verification-metadata.xml`. Sau đó cần review nguồn và checksum có thực sự đáng tin không trước khi commit.

**Cảnh báo:** không chạy tự động lệnh ghi verification metadata rồi mặc định chấp nhận mọi checksum vừa được tải từ một nguồn chưa xác minh. Điều đó chỉ ghi nhận trạng thái hiện tại, không tạo trust từ hư không.

### 12.2. Maven và xác minh artifact

Maven sử dụng repository metadata và có các chính sách checksum, nhưng mức bảo đảm khác nhau tùy cấu hình repository/client và cách xử lý checksum failure. Một tổ chức cần độ tin cậy cao có thể dùng repository manager, signature verification, policy kiểm tra artifact và provenance riêng.

Không nên tuyên bố rằng chỉ có POM versions cố định là đã bảo vệ supply chain.

### 12.3. Thứ tự các lớp bảo đảm

```text
Version declaration / BOM
          |
          v
Version constraints
          |
          v
Resolved dependency graph
          |
          v
Lockfile
          |
          v
Artifact checksum/signature verification
          |
          v
Pinned build tool + JDK + environment
          |
          v
Reproducible archive + compatibility tests
```

Mỗi tầng làm giảm một loại biến thiên hoặc rủi ro khác nhau. Không có tầng nào một mình thay thế được mọi tầng còn lại.

## 13. Khả năng tái lập build có nhiều cấp độ

### 13.1. Repeatable dependency resolution

Một build có thể được gọi là “dependency resolution repeatable” khi cùng declaration/lock và repository policy chọn cùng tập module versions.

Đây là điều kiện cần nhưng chưa đủ cho **byte-for-byte reproducibility**.

### 13.2. Repeatable build environment

Cần kiểm soát:

- JDK vendor và version/patch level.
- Java toolchain của compiler và test runtime.
- Gradle/Maven Wrapper hoặc bản Maven được CI cấp.
- OS/architecture và native tools.
- Locale, timezone và file encoding.
- Environment variables ảnh hưởng build.
- Plugin versions và external generators.
- System properties được đưa vào compilation/packaging.
- Remote inputs và thời gian hệ thống.
- Repository mirror và dependency cache.

Một lần nâng JDK có thể thay đổi `javac` output, warning, generated metadata hoặc tool behavior dù graph dependency giữ nguyên.

### 13.3. Byte-for-byte reproducible artifact

Hai lần build từ cùng input được coi là reproducible ở cấp artifact nếu file đầu ra có cùng byte (trong phạm vi được công bố).

Với JAR/ZIP, những yếu tố gây lệch thường gồm:

- Timestamp của archive entries.
- Thứ tự files trong JAR.
- Generated manifests.
- Build timestamp/hostname trong resource.
- Thứ tự iteration của map không ổn định.
- Non-deterministic code generators.
- Thông tin commit không được pin.
- Sự khác nhau giữa JDK compiler/archiver versions.

Mục tiêu không chỉ là hai file chạy được như nhau, mà là có thể tính cùng checksum và truy xuất đúng nguồn gốc artifact.

### 13.4. Reproducible không đồng nghĩa deterministic runtime

Hai JAR có cùng byte vẫn có thể hoạt động khác nhau nếu:

- OS hoặc native library khác nhau.
- Thời gian, locale hoặc timezone khác nhau.
- API/server bên ngoài trả kết quả khác.
- Thread scheduling và concurrency khác.
- JVM flags hoặc GC configuration khác.
- Dữ liệu production khác.

Do đó, reproducible build hỗ trợ chẩn đoán và supply chain, còn runtime compatibility vẫn cần test và quan sát vận hành.

## 14. Tạo archive tái lập với Gradle

Một cấu hình Groovy DSL phổ biến:

```groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Hai ý tưởng:

- Không giữ timestamp nguồn của từng file như một yếu tố làm thay đổi archive.
- Dùng thứ tự entry ổn định trong archive.

Tùy Gradle version, một số hành vi có thể đã được đặt mặc định phù hợp, nhưng việc cấu hình rõ sẽ giúp diễn đạt chính sách.

Vẫn cần kiểm tra các task tạo resource hoặc manifest. Nếu một task tạo `build-info.properties` chứa thời gian hiện tại, JAR sẽ khác byte dù timestamp ZIP và thứ tự entry đã ổn định.

Ví dụ dễ phá reproducibility:

```groovy
tasks.register('generateBuildInfo') {
    doLast {
        file("$buildDir/generated/build-info.txt")
            .text = "builtAt=" + System.currentTimeMillis()
    }
}
```

Đoạn minh họa chỉ ra nguyên nhân biến thiên, **không phải cấu hình khuyến nghị**. Nếu thực sự cần build timestamp, nên xác định cách dùng dữ liệu đó trong release provenance bên ngoài JAR hoặc có policy rõ để xây dựng lại.

## 15. Maven và reproducible builds

Maven hỗ trợ nhiều kỹ thuật tạo archive tái lập, nhưng phải kiểm soát plugin/archiver và source of variation.

Một property thường dùng:

```xml
<properties>
  <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Property này được những plugin/archiver hỗ trợ sử dụng để cố định timestamp của ZIP/JAR entries; không bảo đảm mọi plugin trong build đều đọc property đó.

Trong build thực tế, giá trị có thể được gắn với một timestamp được kiểm soát từ source/release process thay vì timestamp “bây giờ” của mỗi lần build.

Các điểm cần quản lý:

- Version của `maven-jar-plugin` và các packaging plugins.
- Version của `maven-compiler-plugin`.
- Generated source/resource có thứ tự ổn định.
- Manifest metadata, timestamps và file order.
- Runtime JDK được Maven sử dụng.
- Repository release immutability.
- Plugin dependencies và extensions.

Không nên chỉ đặt `outputTimestamp` rồi tuyên bố toàn bộ build chắc chắn tái lập ở mọi hệ điều hành.

## 16. Pin build tool và Java toolchain

### 16.1. Gradle Wrapper

Một dự án Gradle nên commit wrapper files và kiểm soát Gradle distribution version. Điều này tránh tình trạng máy cá nhân dùng Gradle 8.x nhưng CI dùng 9.x.

Lệnh khởi chạy thường dùng:

```shell
./gradlew build
```

Trên Windows:

```text
gradlew.bat build
```

Wrapper kiểm soát bản Gradle được tải theo cấu hình, nhưng còn cần xác minh nguồn và tính toàn vẹn distribution theo chính sách. Gradle Wrapper không tự pin JDK đang chạy daemon hay compile/test toolchains.

### 16.2. Gradle Java Toolchains

Ví dụ:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Mẫu này minh họa việc dùng compiler từ toolchain Java 21 nhưng target API/class-file level Java 17 cho source Java nếu phù hợp. Muốn thực sự hỗ trợ Java 17, phải kiểm tra runtime dependencies, annotation processors và test trên Java 17. `options.release` không tự làm các thư viện bên ngoài tương thích Java 17.

Toolchain resolution có thể chọn JDK vendor khác nhau hoặc patch level khác nhau nếu chưa có policy. Với reproducibility nghiêm ngặt, nên xác định vendor/version và cách cấp JDK trong CI.

### 16.3. Maven Toolchains và Compiler Plugin

Trong Maven, `maven-toolchains-plugin` và cấu hình compiler có thể giúp tách JDK chạy Maven khỏi JDK dùng biên dịch. `maven-compiler-plugin` hỗ trợ `release` khi toolchain/compiler tương ứng cho phép.

Ví dụ ý tưởng:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Điều này ràng buộc API/bytecode target của nguồn Java trong phạm vi compiler plugin hỗ trợ. Nó **không khóa transitive dependencies**, không đảm bảo Maven tự chọn đúng JDK nếu toolchain không cấu hình, và không thay thế runtime tests.

### 16.4. Maven Wrapper

Một dự án Maven có thể dùng Maven Wrapper để cố định Maven distribution. CI nên dùng lệnh wrapper đã được quản lý:

```shell
./mvnw verify
```

Nếu không dùng wrapper, cần pin Maven version qua CI image hoặc cấu hình build environment. Khi nâng JDK, hãy xác nhận cả Maven/Gradle version và các plugins có hỗ trợ JDK mới.

## 17. Dependency lock trong multi-project và microservices

### 17.1. Multi-project Gradle

Trong một monorepo:

```text
root/
  settings.gradle
  build.gradle
  gradle/libs.versions.toml
  core/
  api/
  worker/
  integration-tests/
```

Các subproject có thể dùng constraints chung, version catalog và BOM. Nhưng resolved graphs vẫn có thể khác theo configuration.

Những điều cần quyết định:

- Lockfile tại project nào?
- Cấu hình nào được lock?
- Lock được tạo bằng task nào trong CI?
- Làm sao xử lý một subproject chỉ resolve khi chạy integration tests?
- Plugin management có policy version riêng không?
- Có build included/composite độc lập cần lock riêng không?

Không nên lấy lockfile của module `api` rồi suy ra `worker` dùng đúng tất cả versions. Hai module có thể có runtime dependencies khác nhau.

### 17.2. Microservices không cần ép cùng một graph

Hai service triển khai độc lập có thể cùng dùng một BOM baseline, nhưng không nhất thiết phải khóa toàn bộ modules ở cùng version. Nếu một service cần nâng thư viện vì JDK 21 còn service khác đang ở JDK 17, việc force cả hệ thống dùng một bản có thể tạo regression.

Nên phân biệt:

- **Platform policy:** các version tối thiểu/được phép và bộ thư viện tương thích.
- **Service lock:** resolved graph của từng deployable artifact.
- **Release artifact:** JAR/container image cụ thể đã được kiểm thử.
- **Compatibility contract:** API/protocol giữa services.

Version lock ở cấp service giúp rollback có thể truy vết mà không bắt mọi service deploy đồng bộ.

### 17.3. Shared library và transitive API

Một thư viện có thể vô tình lộ kiểu từ dependency qua public API:

```java
public interface Exporter {
    org.example.json.JsonNode export();
}
```

Khi nâng `org.example.json`, đây không còn chỉ là thay đổi implementation dependency. Consumer có thể compile against public dependency type và chịu ảnh hưởng binary/source compatibility.

Nếu chỉ dùng dependency bên trong implementation, nên tránh làm rò rỉ type vào public API. Với Gradle `java-library`, phân biệt `api` và `implementation` giúp thể hiện điều đó.

## 18. Migration JDK: dependency upgrade phải có chiến lược

### 18.1. Tại sao đổi JDK trước không đủ?

Nâng JDK 8 lên 17, 21 hoặc 25 có thể tác động đến:

- Bytecode target và compiler plugin.
- Framework dựa vào JDK internals.
- Reflection và module encapsulation.
- Jakarta/Java EE API đã thay đổi hoặc không còn đi kèm JDK.
- Annotation processors và bytecode manipulation.
- GC, TLS, crypto providers và security defaults.
- JNI/native dependencies và platform classifiers.
- Test runners, build plugins và Java agents.

Một graph dependency bị khóa từ nhiều năm trước có thể giúp tái lập lỗi rất tốt, nhưng không tự động làm ứng dụng chạy được trên JDK mới.

### 18.2. Thiết lập hai baseline

Nên lưu ít nhất:

| Baseline | JDK | Dependency graph | Mục tiêu |
|---|---|---|---|
| Legacy baseline | JDK đang chạy ổn định | Lock/dependency report hiện tại | Điểm tham chiếu khi phát sinh regression |
| Target baseline | JDK mục tiêu | Graph đã được nâng có kiểm soát | Cấu hình dự kiến phát hành |

Lưu thêm plugin/build-tool version, CI image, JVM flags và kết quả smoke tests để có thể so sánh.

### 18.3. Nâng cấp theo nhóm thay vì đồng loạt

Một trình tự có thể là:

1. Nâng build tool và compiler plugins lên bản hỗ trợ JDK đích.
2. Xác định dependency critical: framework, ORM, JSON, logging, security, bytecode, JDBC và test tooling.
3. Dùng BOM/platform hoặc dependencyManagement để căn chỉnh theo họ.
4. Nâng những thư viện bắt buộc đổi vì JDK incompatibility.
5. Cập nhật lockfile/graph và review transitive changes.
6. Chạy compile/test trên JDK cũ và mới nếu cả hai thuộc support window.
7. Bổ sung integration tests cho các hành vi đã thay đổi.
8. Phát hành canary, theo dõi runtime errors.
9. Chuyển baseline khi đã ổn định.

Không cần áp dụng chính xác cùng thứ tự cho mọi dự án; nguyên tắc là giới hạn kích thước thay đổi và giữ khả năng giải thích mỗi regression.

### 18.4. Không giữ dependency dễ tổn thương chỉ vì lockfile

Lockfile là bằng chứng về những version được chọn, không phải bản cam kết rằng chúng không bao giờ được phép thay đổi. Cần có quy trình cập nhật bảo mật:

- SCA và advisory monitoring theo phạm vi dependency.
- Tạo issue/PR khi CVE hoặc end-of-support ảnh hưởng bản khóa.
- Review compatibility và test.
- Cập nhật lock theo nhóm có kiểm soát.
- Ghi lại lý do và thời điểm nâng.
- Có exception policy nếu chưa nâng được, kèm mitigations và expiry.

Lock phải giúp thay đổi có kiểm soát, không trở thành rào cản khiến dự án mãi dùng thư viện không còn hỗ trợ.

## 19. Chẩn đoán dependency graph trong Gradle

### 19.1. Xem toàn bộ dependency theo configuration

```shell
./gradlew :app:dependencies --configuration runtimeClasspath
```

Báo cáo này giúp xem dependency trees và resolved versions của runtime configuration. Lệnh không tương đương với báo cáo compile, test hoặc annotation processors.

### 19.2. Giải thích vì sao một version được chọn

```shell
./gradlew :app:dependencyInsight \
    --dependency json-core \
    --configuration runtimeClasspath
```

Báo cáo `dependencyInsight` có thể cho biết đường đi yêu cầu dependency và các lý do chọn version tùy Gradle version/metadata.

Trong quá trình migration, đây thường là công cụ tốt hơn việc chỉ đọc `build.gradle` vì conflict resolution có thể thay version được khai báo ở dependency bắc cầu.

### 19.3. Khi lockfile và declaration xung đột

Một lỗi thường gặp:

```text
Version declaration updated
          |
          v
Lockfile vẫn lưu version cũ
          |
          v
Resolution không khớp chính sách khóa
```

Đừng giải quyết bằng cách xóa lockfile rồi commit lại một file mới mà không xem diff. Hãy xác định dependency nào được chủ đích nâng và cập nhật lock theo quy trình.

Nếu lock được tạo trong môi trường cũ nhưng chạy trên OS/JDK mới, các configuration có thể chọn biến thể khác hoặc có thêm dependency điều kiện. Hãy kiểm tra lock scope và platform-specific artifacts thay vì tự kết luận tool hoạt động sai.

## 20. Chẩn đoán dependency graph trong Maven

### 20.1. Dependency tree

```shell
mvn dependency:tree
```

Xem những đường đi đến dependency đích, phiên bản được chọn và modules bị omit do conflict tùy chế độ output/plugin version.

### 20.2. Effective POM

```shell
mvn help:effective-pom
```

Effective POM giúp xác định cấu hình sau khi kết hợp parent, profiles và dependencyManagement. Nhưng nó không thay thế dependency tree: hai báo cáo giải đáp những câu hỏi khác nhau.

### 20.3. Profiles và môi trường

Maven profile có thể được kích hoạt dựa trên JDK, OS, property hoặc những điều kiện khác. Cùng một commit có thể có dependencies khác nhau khi đổi JDK.

Ví dụ cấu hình `activation` theo JDK có thể làm một profile hoạt động trên JDK 21 mà không hoạt động trên JDK 17. Khi đó, source POM không đổi nhưng resolved graph khác.

Trong migration, liệt kê active profiles:

```shell
mvn help:active-profiles
```

Khi xây release, nên ghi lại profile flags và environment điều khiển resolution. Không mặc định POM gốc là toàn bộ cấu hình đã được áp dụng.

## 21. Các lỗi thường gặp và cách phân loại

### Lỗi 1: Build cũ chạy lại ra một dependency version mới

**Triệu chứng:** cùng commit nhưng dependency tree khác nhau hoặc xuất hiện API không tương thích.

**Nguyên nhân:** dynamic version/range, SNAPSHOT, mutable artifact hoặc cache metadata khác.

**Xử lý:** cố định version theo policy, tạo/cập nhật lock, kiểm soát repository, lưu resolved graph.

### Lỗi 2: Compile thành công nhưng runtime ném `NoSuchMethodError`

**Triệu chứng:** class có mặt nhưng method được code gọi không tồn tại ở runtime.

**Nguyên nhân khả dĩ:** compile và runtime classpath chọn version khác, hoặc một thư viện bắc cầu không tương thích binary.

**Xử lý:** so sánh graph của compile/runtime, dùng `dependencyInsight` hoặc `dependency:tree` và kiểm tra version thực sự trong artifact triển khai. Không chỉ thêm một constraint mạnh mà chưa xác định caller cần API nào.

### Lỗi 3: `UnsupportedClassVersionError` sau nâng dependency

**Triệu chứng:** JDK runtime cũ không nạp được class của thư viện mới.

**Nguyên nhân:** dependency đã được build bằng class-file version yêu cầu JDK cao hơn.

**Xử lý:** kiểm tra release notes, dependency metadata và support matrix; chọn version tương thích với runtime đã cam kết hoặc nâng runtime theo kế hoạch.

### Lỗi 4: Lockfile thay đổi quá nhiều sau một PR nhỏ

**Triệu chứng:** một lần nâng direct dependency làm hàng chục modules khác đổi.

**Nguyên nhân khả dĩ:** BOM mới, dynamic versions, changed metadata hoặc một configuration mới được resolve.

**Xử lý:** review từng nhóm thay đổi; kiểm tra platform, repository và lock scope. Tách nâng cấp lớn thành PR có chủ đích nếu cần.

### Lỗi 5: Lockfile không ngăn JAR khác byte

**Triệu chứng:** cùng coordinates/version nhưng checksum trên hai máy không khớp.

**Nguyên nhân:** repository cho overwrite, cache/proxy khác hoặc nguồn artifact bị thay đổi.

**Xử lý:** immutable repository, verification metadata, checksum/signature policy và audit publish. Version lock không đủ.

### Lỗi 6: Maven build đổi kết quả khi thay thứ tự dependency

**Triệu chứng:** một transitive dependency được chọn khác dù version direct ít thay đổi.

**Nguyên nhân:** Maven mediation và dependency graph structure.

**Xử lý:** dùng dependencyManagement/BOM để làm rõ version và kiểm tra dependency tree trong CI.

### Lỗi 7: Cùng graph dependency nhưng JAR checksum khác

**Triệu chứng:** cùng dependencies, khác build output.

**Nguyên nhân:** timestamps, file order, generated content, toolchain hoặc OS/locale.

**Xử lý:** cấu hình reproducible archive, pin build tool/JDK, loại nondeterministic input và so sánh artifact ở môi trường được kiểm soát.

### Lỗi 8: Bản lock “an toàn” nhưng bị cảnh báo lỗ hổng

**Triệu chứng:** SCA phát hiện dependency có CVE dù graph không thay đổi.

**Nguyên nhân:** khóa phiên bản chỉ kiểm soát thay đổi, không đánh giá mức độ bảo mật.

**Xử lý:** cập nhật theo advisory và compatibility test, bổ sung mitigations nếu chưa thể nâng.

### Lỗi 9: Repository private bị thay bằng artifact cùng tên ở public repo

**Triệu chứng:** build lấy package không mong đợi, checksum hoặc behavior sai.

**Nguyên nhân:** repository ordering/content policy và namespace collision.

**Xử lý:** lọc repository theo group, dùng trusted mirrors và artifact verification, kiểm tra provenance.

### Lỗi 10: Một OS resolve native artifact khác OS khác

**Triệu chứng:** Windows chạy được nhưng Linux thiếu native binary hoặc classifier khác.

**Nguyên nhân:** dependency có platform-specific variants hoặc native classifiers.

**Xử lý:** kiểm tra graph theo từng OS/architecture, pin toolchain và thử đóng gói/chạy artifact thật. Lockfile cần hỗ trợ các biến thể được cam kết, không chỉ máy developer.

## 22. Quy trình kiểm soát upgrade bằng pull request

Một dependency upgrade nên có phần mô tả đủ để reviewer hiểu thay đổi:

```text
Dependency: org.example:json-core
Old version: 2.4.3
New version: 2.5.1

Reason:
- Sửa lỗi được công bố / hỗ trợ JDK target

Direct and transitive changes:
- Liệt kê từ lock diff hoặc dependency tree

Compatibility:
- Minimum JDK:
- Source/binary/config/serialization notes:
- Affected modules:

Validation:
- Unit tests:
- Integration tests:
- JDK matrix:
- Smoke test:

Release:
- Canary plan:
- Rollback artifact:
- Owner:
```

Không cần mọi thay đổi nhỏ phải có tài liệu dài, nhưng những dependency cốt lõi như framework, serializer, ORM, crypto, JDBC driver, bytecode tool và Java agent nên có mức kiểm soát cao hơn.

### 22.1. Không tự động cập nhật lock không review

Một bot có thể đề xuất PR cập nhật version và lockfile. Đây là workflow hữu ích nếu CI:

- Chỉ cho phép changeset được định nghĩa.
- Hiển thị transitive diff rõ.
- Chạy build/test trên JDK target.
- Chạy license và security checks.
- Yêu cầu reviewer cho các dependency quan trọng.
- Không tự merge bản major khi chưa có compatibility plan.

Automation giảm lao động lặp lại; nó không thay thế quyết định compatibility.

### 22.2. Lock refresh định kỳ

Nếu dự án không dùng dynamic dependencies và các version đều pin, lock refresh vẫn hữu ích khi thêm/bớt module hoặc thay BOM. Với dynamic dependencies, có thể đặt lịch cập nhật có kiểm soát thay vì để chúng thay đổi tùy lần build.

Một quy trình hợp lý là “mỗi thay đổi dependency có một PR riêng chứa lock diff”, kèm rà soát bảo mật định kỳ. Không cần chỉnh lock hàng ngày nếu graph không đổi.

## 23. Quy trình CI đề xuất cho build có thể tái lập

Một pipeline có thể tổ chức:

```text
Checkout immutable commit
           |
           v
Pin JDK + Gradle/Maven distribution
           |
           v
Load trusted repositories and credentials
           |
           v
Resolve dependencies under version policy + lock
           |
           v
Verify artifact checksums/signatures
           |
           v
Compile + test (JDK compatibility matrix)
           |
           v
Package deterministic JAR/image
           |
           v
Generate dependency graph / SBOM / provenance
           |
           v
Publish immutable artifact
           |
           v
Smoke test + rollout
```

Cần xác định nơi các bí mật được cấp: credentials để tải private dependencies, khóa ký và token publish không được lưu trong repository hay in vào logs.

### 23.1. CI gate cho lockfile

Nếu dùng Gradle locking, pipeline release có thể chạy resolution với chính lockfile đã commit và từ chối thay đổi không mong đợi. Không cho release pipeline tự động ghi lại lockfile rồi âm thầm sử dụng kết quả mới.

Một upgrade hợp lệ phải xuất hiện ở PR thay đổi source/build files, được review và đi qua test.

### 23.2. CI gate cho dependency graph

Lưu dependency graph hoặc SBOM cùng release artifact để có thể trả lời câu hỏi:

- Artifact production này chứa version nào của `json-core`?
- Version đó đến từ dependency trực tiếp hay transitive?
- Có nhiều version của cùng thư viện bị đóng vào fat JAR không?
- Có module nào bị thêm vào mà reviewer không biết không?
- Một CVE mới có ảnh hưởng những release nào?

SBOM là inventory, không tự ngăn lỗ hổng. Nhưng inventory đáng tin cậy giúp đánh giá tác động và lập kế hoạch remediation nhanh hơn.

### 23.3. CI gate cho reproducibility

Với một release quan trọng, có thể build hai lần trong môi trường được kiểm soát và so sánh SHA-256 của artifacts. Nếu khác, phân tích timestamp, file order, resource được sinh ra, JDK/toolchain và source of nondeterminism.

Không nhất thiết yêu cầu byte equality giữa những OS khác nhau nếu sản phẩm chủ động có OS-specific artifacts. Điều quan trọng là tuyên bố rõ phạm vi reproducibility: cùng commit, cùng dependency graph, cùng toolchain/OS, và cùng cấu hình build.

## 24. Bài tập tình huống: migration Java 17 lên 21

Một service có:

```groovy
dependencies {
    implementation 'org.example:legacy-http-client:3.+'
    implementation 'org.example:json-core:2.2.0'
    testImplementation 'org.example:testkit:1.8.0'
}
```

Khi chuyển lên JDK 21, build CI đôi lúc xuất hiện lỗi API trong `legacy-http-client`. Hãy giải quyết theo trình tự:

1. Ghi lại version cụ thể của mọi dependency đã resolve khi lỗi xảy ra.
2. Dùng `dependencyInsight` để tìm các nhánh đòi `legacy-http-client` và transitive dependencies.
3. Xác định bản thư viện được nhà cung cấp hỗ trợ trên JDK 21.
4. Thay `3.+` bằng một version hoặc constraint có chính sách rõ.
5. Căn chỉnh BOM/platform nếu library thuộc một họ dependency.
6. Bật locking cho các configurations quan trọng và tạo lockfile.
7. Commit lockfile cùng thay đổi version declaration.
8. Xác minh artifact integrity từ repository được tin cậy.
9. Chạy tests trên JDK 17/21 nếu còn cam kết cả hai.
10. Tạo immutable release artifact và lưu graph, checksum, toolchain metadata.
11. Thử rollback và theo dõi runtime errors trong canary.

Nếu khi nâng dependency, thư viện mới yêu cầu Java 21 và ứng dụng còn phải chạy Java 17, không thể giải quyết chỉ bằng `--release 17` của code ứng dụng. Phải chọn một bản dependency phù hợp cả hai runtime hoặc điều chỉnh support policy.

## 25. Checklist trước khi phát hành

### Version policy

- [ ] Đã xác định direct, transitive và build/plugin dependencies quan trọng.
- [ ] Đã loại dynamic version/range không được kiểm soát khỏi release path.
- [ ] Đã dùng BOM/platform hoặc dependencyManagement cho các họ thư viện liên quan.
- [ ] Đã phân biệt `strictly`, `prefer`, `require` và force trong Gradle.
- [ ] Có chính sách khi graph gặp xung đột version.
- [ ] Có bản ghi lý do nâng dependency và compatibility evidence.

### Dependency locking

- [ ] Các configuration cần thiết có lockfile/graph policy phù hợp.
- [ ] Lockfile được commit và diff được review.
- [ ] Build release không tự cập nhật lock không có PR.
- [ ] Đã kiểm tra buildscript/plugins/toolchains ngoài phạm vi lock.
- [ ] Snapshot/changing modules đã được quản lý riêng.
- [ ] Có quy trình refresh lock để xử lý bảo mật và nâng JDK.

### Repository và supply chain

- [ ] Release artifacts không bị ghi đè cùng coordinates/version.
- [ ] Repository được giới hạn theo nguồn và namespace tin cậy.
- [ ] Có checksum/signature verification theo policy.
- [ ] Credentials không nằm trong source hoặc build logs.
- [ ] Dependency graph/SBOM và provenance được lưu cùng release.
- [ ] Có cách xác định bản production thực sự chứa thư viện nào.

### Reproducible build

- [ ] Gradle/Maven distribution được pin qua wrapper hoặc CI policy.
- [ ] JDK vendor/version/toolchain và OS target được xác định.
- [ ] Archive timestamps và entry order được quản lý khi cần.
- [ ] Generated resources không chứa input ngẫu nhiên/không kiểm soát.
- [ ] Compiler, annotation processors và packaging plugins có version rõ.
- [ ] Build artifact có checksum và được kiểm tra lại khi cần.

### Java migration

- [ ] Build tool và plugin hỗ trợ JDK đích.
- [ ] Dependency mới hỗ trợ JDK tối thiểu của consumer.
- [ ] Đã chạy dependency graph diagnostics trên compile/test/runtime.
- [ ] Đã kiểm tra Java agent, bytecode tool, ORM, serializer và native dependency.
- [ ] Có unit/integration tests theo JDK support matrix.
- [ ] Có canary/rollback plan và theo dõi lỗi linkage/behavior.
- [ ] Không xem “lockfile không đổi” là bằng chứng ứng dụng đã tương thích.

## Kết luận

Ràng buộc phiên bản, dependency locking và reproducible build giải quyết ba tầng khác nhau của cùng một vấn đề. **Constraints** nói phiên bản nào được phép hoặc được ưu tiên. **Lockfile** giữ kết quả dependency resolution để tránh build vô tình chọn version mới. **Reproducible build** tiến thêm một bước: kiểm soát JDK, build tool, plugin, repository, timestamps và các đầu vào khác để tạo artifact có thể truy vết và tái lập.

Trong Java Advance Compatibility Migration, nên bắt đầu từ dependency graph thật, căn chỉnh các họ thư viện bằng BOM/platform hoặc dependencyManagement, quản lý Gradle lockfile hoặc cơ chế Maven tương ứng theo chính sách, bảo vệ artifact bằng verification và immutable repository, rồi kiểm thử trên JDK đích. Một build được khóa có thể vẫn chứa bug hoặc CVE; một artifact tái lập byte-for-byte vẫn có thể không tương thích runtime. Vì vậy, hãy dùng locking để giúp thay đổi **có kiểm soát**, và dùng compatibility testing, security review và release provenance để bảo đảm thay đổi đó **đúng và an toàn**.

