# Xung đột phiên bản và vai trò của chính sách lựa chọn

Một ứng dụng Java thường phụ thuộc vào nhiều thư viện. Mỗi thư viện lại có thể phụ thuộc vào những thư viện khác, và các nhánh phụ thuộc có thể yêu cầu những phiên bản khác nhau của cùng một module. Đây là xung đột phiên bản (version conflict). Công cụ build phải quyết định phiên bản nào được đưa vào classpath, hoặc dừng build nếu không thể tìm được lựa chọn phù hợp.

Chính sách lựa chọn phiên bản (version selection policy) định nghĩa cách dự án xử lý những tình huống đó. Chính sách tốt giúp build có thể dự đoán, tránh việc một dependency mới vô tình thay đổi runtime, giữ tương thích giữa các module và hỗ trợ điều tra lỗi. Chính sách yếu có thể khiến build thành công nhưng ứng dụng gặp `NoSuchMethodError`, `ClassNotFoundException`, lỗi liên kết hoặc hành vi khác nhau giữa máy phát triển và CI.

## 1. Xung đột phiên bản xuất hiện như thế nào?

Giả sử ứng dụng phụ thuộc trực tiếp vào `library-a` và `library-b`. Cả hai cùng phụ thuộc vào `common-core`, nhưng yêu cầu phiên bản khác nhau:

```text
application
├── library-a:2.0
│   └── common-core:1.4
└── library-b:3.0
    └── common-core:2.1
```

Khi build tạo runtime classpath, chỉ một phiên bản của cùng module `common-core` thường được chọn trong một configuration. Công cụ build cần một quy tắc để giải quyết yêu cầu `1.4` và `2.1`.

Xung đột có thể đến từ nhiều nguồn:

- Hai dependency trực tiếp khai báo các phiên bản khác nhau của cùng module.
- Hai dependency bắc cầu (transitive dependencies) kéo về các phiên bản khác nhau.
- Một plugin thêm thư viện vào classpath build hoặc test.
- Một platform/BOM áp dụng constraint khác với phiên bản được yêu cầu trực tiếp.
- Một thư viện đổi dependency trong phiên bản mới, khiến đồ thị phụ thuộc của ứng dụng thay đổi.
- Một dependency dùng dynamic version như `1.+`, `latest.release` hoặc một version range.

Không phải mọi khác biệt phiên bản đều tạo xung đột. Hai module có tên khác nhau có thể cùng tồn tại ở các phiên bản riêng. Xung đột xảy ra khi công cụ cần chọn giữa nhiều yêu cầu cho cùng một module hoặc khi nhiều module cung cấp cùng một capability mà graph không thể chọn đồng thời.

## 2. Vì sao cần chính sách lựa chọn?

Nếu không xác định chính sách, kết quả có thể phụ thuộc vào quy tắc mặc định của công cụ build, metadata của repository hoặc các rule nằm rải rác trong build script. Điều đó tạo ra một số rủi ro.

**Tương thích API:** phiên bản mới có thể xóa hoặc thay đổi method mà dependency khác đang gọi. Compile có thể thành công nếu phần mã liên quan không được kiểm tra, nhưng runtime lại phát sinh lỗi liên kết.

**Tương thích hành vi:** một phiên bản thư viện có thể giữ API nhưng thay đổi mặc định, cách serialize dữ liệu, thuật toán hoặc cách xử lý lỗi.

**Bảo mật:** phiên bản cũ có thể chứa lỗ hổng đã biết; phiên bản mới có thể sửa lỗ hổng nhưng cũng có thể mang thay đổi không tương thích.

**Khả năng tái lập:** dynamic version hoặc repository metadata thay đổi có thể khiến cùng một build file phân giải ra phiên bản khác nhau ở hai thời điểm.

**Tính nhất quán:** các module trong cùng sản phẩm có thể dùng những phiên bản khác nhau của một họ thư viện, dẫn đến lỗi khó dự đoán khi chúng trao đổi object hoặc dữ liệu.

Vì vậy, lựa chọn phiên bản không chỉ là chọn số lớn nhất. Cần cân bằng tương thích, bảo mật, hỗ trợ dài hạn, khả năng cập nhật và độ ổn định của build.

## 3. Cách Gradle giải quyết xung đột phiên bản mặc định

Gradle giải quyết dependency riêng cho từng configuration, ví dụ `compileClasspath`, `runtimeClasspath`, `testCompileClasspath` và `testRuntimeClasspath`. Các configuration có thể có dependency graph và kết quả lựa chọn khác nhau.

Trong trường hợp xung đột phiên bản thông thường của cùng module, Gradle mặc định chọn phiên bản cao nhất trong các phiên bản được yêu cầu, có xét đến các version constraint và rule áp dụng. Đây là chính sách conflict resolution mặc định.

Ví dụ:

```groovy
dependencies {
    implementation 'org.example:common-core:1.4'
    implementation 'org.example:common-core:2.1'
}
```

Với các yêu cầu thông thường như trên, Gradle sẽ chọn `org.example:common-core:2.1` cho configuration tương ứng. Nó không đưa đồng thời cả `1.4` và `2.1` của cùng module vào classpath đó.

Tình huống bắc cầu cũng tương tự:

```text
app
├── library-a:2.0
│   └── common-core:1.4
└── library-b:3.0
    └── common-core:2.1
```

Nếu không có constraint hoặc rule mạnh hơn, Gradle thường chọn phiên bản cao hơn là `2.1`.

### 3.1. Chọn phiên bản cao nhất không đồng nghĩa với an toàn nhất

Quy tắc chọn phiên bản cao nhất là một cơ chế giải quyết graph, không phải đánh giá tương thích API hoặc hành vi. Gradle không tự biết `library-a` có thực sự tương thích với `common-core:2.1` hay không.

Ví dụ, `library-a:2.0` có thể chỉ được kiểm thử với `common-core:1.x`. Nếu `2.1` loại bỏ một method mà `library-a` đang gọi, ứng dụng có thể gặp lỗi runtime. Khi đó build đã giải quyết xung đột theo quy tắc mặc định, nhưng chính sách tương thích của sản phẩm vẫn chưa được bảo đảm.

Vì thế, sau khi chọn phiên bản cần xem xét:

- Release notes và compatibility notes của thư viện.
- Dải phiên bản được nhà cung cấp hỗ trợ.
- Test của ứng dụng và các module phụ thuộc.
- Khả năng tương thích giữa compile classpath và runtime classpath.
- Các bản vá bảo mật và thời gian hỗ trợ của phiên bản.

## 4. Phân biệt version request, constraint và resolution rule

Trong Gradle, các khái niệm sau có vai trò khác nhau:

| Khái niệm | Vai trò |
|---|---|
| Version request | Phiên bản hoặc dải phiên bản mà một dependency khai báo yêu cầu. |
| Dependency constraint | Đưa ra giới hạn hoặc ưu tiên cho phiên bản của module; bản thân constraint không tự thêm dependency vào graph. |
| Platform/BOM | Cung cấp một tập dependency constraint để các module dùng phiên bản nhất quán. |
| Resolution strategy/rule | Điều chỉnh cách Gradle lựa chọn component trong quá trình giải quyết graph. |
| Dependency lock | Ghi lại phiên bản đã được phân giải để những lần build sau dùng cùng kết quả theo lock state. |
| Dependency verification | Kiểm tra artifact tải về theo checksum hoặc chữ ký đã cấu hình; không phải cơ chế chọn phiên bản. |

Một dependency khai báo thư viện cần dùng; constraint định hướng phiên bản của thư viện đó; platform gom nhiều constraint; resolution rule can thiệp vào quá trình lựa chọn; lock giữ lại kết quả đã được phê duyệt. Verification bổ sung kiểm tra tính toàn vẹn và nguồn gốc artifact.

## 5. Dùng dependency constraint để định hướng phiên bản

Constraint cho phép mô tả phiên bản được chấp nhận hoặc mong muốn mà không nhất thiết phải thêm module đó làm dependency trực tiếp.

Ví dụ Groovy DSL:

```groovy
dependencies {
    implementation 'org.example:library-a:2.0'

    constraints {
        implementation('org.example:common-core:2.1') {
            because 'Các module trong ứng dụng đã được kiểm thử với common-core 2.1'
        }
    }
}
```

Constraint `common-core:2.1` tham gia lựa chọn khi module đó xuất hiện trong graph. Nếu không có dependency nào kéo `common-core` vào graph, constraint này không tự thêm nó vào classpath.

### 5.1. Rich version constraints

Gradle hỗ trợ rich version declaration với các mức yêu cầu khác nhau:

- `require`: yêu cầu phiên bản hoặc dải phiên bản; các yêu cầu khác có thể khiến kết quả được nâng lên trong phạm vi phù hợp.
- `prefer`: nêu phiên bản mong muốn khi không có yêu cầu mạnh hơn.
- `strictly`: giới hạn kết quả trong phiên bản hoặc dải phiên bản nghiêm ngặt; nếu các constraint không thể thỏa mãn đồng thời, resolution có thể thất bại.
- `reject`: loại trừ phiên bản hoặc dải phiên bản khỏi tập được chấp nhận.

Ví dụ:

```groovy
dependencies {
    implementation('org.example:common-core') {
        version {
            strictly '[2.1, 2.3['
            prefer '2.2'
            reject '2.1.1'
        }
    }
}
```

Trong ví dụ, dải nghiêm ngặt chấp nhận phiên bản từ `2.1` đến trước `2.3`, ưu tiên `2.2` và loại `2.1.1`. Cú pháp version range dùng dấu ngoặc vuông/tròn để thể hiện biên bao gồm hoặc không bao gồm.

Có thể khai báo constraint riêng:

```groovy
dependencies {
    constraints {
        implementation('org.example:common-core') {
            version {
                strictly '2.2'
            }
            because 'Phiên bản này đã được xác nhận tương thích trong sản phẩm'
        }
    }
}
```

`strictly` hữu ích khi sản phẩm chỉ cho phép một phiên bản hoặc một dải cụ thể. Tuy nhiên, constraint nghiêm ngặt có thể làm build thất bại khi dependency khác yêu cầu phiên bản ngoài dải. Đó là tín hiệu xung đột cần xử lý, không nên tự động nới lỏng nếu chưa hiểu lý do.

### 5.2. `prefer` không phải pin phiên bản

`prefer` thể hiện lựa chọn mong muốn, không bảo đảm phiên bản đó luôn được dùng. Một yêu cầu hoặc constraint mạnh hơn có thể khiến Gradle chọn phiên bản khác. Nếu mục tiêu là khóa chặt, cần xem xét `strictly` hoặc dependency locking thay vì hiểu `prefer` như một lệnh pin.

## 6. Quản lý phiên bản bằng platform và BOM

Khi nhiều module cùng dùng một nhóm thư viện có quan hệ phiên bản, khai báo từng constraint riêng lẻ sẽ khó duy trì. Platform giúp tập trung chính sách phiên bản.

Trong Gradle, một platform thường cung cấp dependency constraints. Java ecosystem cũng sử dụng BOM (Bill of Materials) để công bố các phiên bản thư viện được khuyến nghị hoặc tương thích cùng nhau.

Ví dụ import BOM:

```groovy
dependencies {
    implementation platform('org.example:example-bom:5.0.0')

    implementation 'org.example:client-core'
    implementation 'org.example:client-http'
    testImplementation 'org.example:client-test'
}
```

Khi BOM định nghĩa constraint cho các module đó, Gradle có thể sử dụng các phiên bản do BOM quản lý mà không cần ghi version lặp lại ở từng dependency. BOM không nhất thiết chứa tất cả module; nếu một module không được BOM quản lý thì cần khai báo version hoặc constraint khác.

### 6.1. `platform` và `enforcedPlatform`

`platform(...)` đưa các constraint của platform vào graph theo quy tắc thông thường. Các constraint đó tham gia giải quyết phiên bản cùng với yêu cầu khác.

`enforcedPlatform(...)` áp dụng các phiên bản của platform theo cách cưỡng chế mạnh hơn và có thể ảnh hưởng đến các consumer của thư viện nếu được xuất qua dependency metadata. Điều này có thể hữu ích cho ứng dụng cần một bộ phiên bản cố định, nhưng cần thận trọng khi dùng trong thư viện được chia sẻ vì nó có thể áp đặt lựa chọn lên project tiêu thụ.

Ví dụ:

```groovy
dependencies {
    implementation enforcedPlatform('org.example:example-bom:5.0.0')
}
```

Không nên dùng `enforcedPlatform` chỉ vì muốn “đảm bảo build ổn định” mà chưa xem xét ảnh hưởng đến các dependency khác. Với library, platform thông thường hoặc dependency constraints được thiết kế phù hợp thường linh hoạt hơn.

### 6.2. Tự tạo platform nội bộ

Nhóm có thể tạo Gradle project dùng plugin `java-platform` để quản lý các phiên bản được thống nhất trong tổ chức:

```groovy
plugins {
    id 'java-platform'
}

dependencies {
    constraints {
        api 'org.example:common-core:2.2.0'
        api 'org.example:logging-api:4.1.0'
        api 'org.example:json-codec:3.5.0'
    }
}
```

Các project ứng dụng có thể import platform này:

```groovy
dependencies {
    implementation platform(project(':dependency-platform'))
    implementation 'org.example:common-core'
    implementation 'org.example:logging-api'
}
```

Platform nội bộ giúp thay đổi chính sách phiên bản tại một nơi và làm rõ bộ thư viện đã được xác nhận cùng nhau. Khi nâng version, nhóm có thể chạy test của các module sử dụng platform trước khi phát hành bản platform mới.

## 7. Dùng `force` và resolution rules một cách có kiểm soát

Gradle cung cấp resolution strategy để can thiệp vào lựa chọn dependency. Những cơ chế này có sức mạnh lớn nhưng có thể che giấu nguyên nhân xung đột hoặc làm sai lệch metadata mà thư viện công bố.

### 7.1. `force`

Có thể buộc một configuration dùng một phiên bản cụ thể:

```groovy
configurations.configureEach {
    resolutionStrategy.force 'org.example:common-core:2.2.0'
}
```

`force` có thể hữu ích như biện pháp tạm thời khi cần áp dụng bản vá hoặc xử lý một dependency chưa được cập nhật metadata. Nhưng nó có thể ghi đè lựa chọn mà dependency khác mong đợi. Build thành công không bảo đảm phiên bản bị ép tương thích với mọi consumer.

Nếu dùng force, cần ghi lý do, phạm vi configuration, người chịu trách nhiệm và điều kiện gỡ bỏ. Nên ưu tiên constraint hoặc platform để chính sách hiển thị rõ hơn trong dependency metadata.

### 7.2. `eachDependency`

`eachDependency` cho phép thay đổi requested version trong quá trình resolution:

```groovy
configurations.configureEach {
    resolutionStrategy.eachDependency { details ->
        if (details.requested.group == 'org.example' &&
            details.requested.name == 'common-core') {
            details.useVersion '2.2.0'
            details.because 'Đồng bộ common-core theo chính sách nền tảng'
        }
    }
}
```

Rule có thể áp dụng rộng hơn dự kiến nếu điều kiện không đủ chặt. Hãy kiểm tra group, module và configuration cụ thể, đồng thời dùng `because` để giải thích quyết định.

### 7.3. Component selection rule

Component selection rule cho phép loại một phiên bản khỏi quá trình lựa chọn, chẳng hạn loại các bản phát hành có trạng thái không được chấp nhận hoặc bản có vấn đề đã biết.

```groovy
configurations.configureEach {
    resolutionStrategy.componentSelection {
        all { selection ->
            if (selection.candidate.version == '2.1.1') {
                selection.reject('Phiên bản này có lỗi đã được xác nhận')
            }
        }
    }
}
```

Đây là ví dụ rule đơn giản. Trong thực tế, có thể cần xem component metadata, status scheme hoặc thông tin từ repository. Rule càng rộng càng có nguy cơ làm mất khả năng chọn phiên bản hợp lệ; nên giới hạn module và ghi lại lý do.

### 7.4. Module replacement và dependency substitution

Đôi khi xung đột không nằm ở hai phiên bản của cùng module, mà do một module mới thay thế module cũ hoặc do nhóm muốn thay dependency ngoài bằng project nội bộ.

Gradle có các API module replacement và dependency substitution. Chúng cho phép diễn tả module cũ đã được thay thế, hoặc chuyển một dependency request sang component khác. Đây là quyết định về danh tính component trong graph, không đơn thuần là chọn số phiên bản cao hơn.

Ví dụ substitution trong build logic có thể chuyển module sang project:

```groovy
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute module('org.example:common-core')
            using project(':common-core')
    }
}
```

Khi dùng substitution, cần bảo đảm project thay thế cung cấp API và variant phù hợp với consumer. Nếu không, build có thể thất bại ở compile hoặc runtime dù graph đã chọn đúng component theo rule.

## 8. Xung đột capability và version alignment

Không phải mọi xung đột đều là version conflict của cùng một module. Hai module khác tọa độ có thể cùng khai báo cung cấp một capability. Ví dụ, hai implementation của cùng một logging backend có thể cùng cung cấp capability “logging backend”. Nếu cả hai cùng xuất hiện, Gradle có thể báo capability conflict.

Capability giúp mô tả chức năng mà component cung cấp. Khi các component xung đột về capability, cần lựa chọn implementation phù hợp hoặc cấu hình metadata để thể hiện quan hệ thay thế.

Một vấn đề khác là version alignment. Nhiều module thuộc cùng một thư viện hoặc release train có thể cần dùng cùng phiên bản. Ví dụ `client-core`, `client-json` và `client-http` được phát hành cùng một version. Nếu graph chọn lệch phiên bản giữa các module này, có thể xuất hiện lỗi tương thích.

Platform/BOM là cách phổ biến để align các module cùng release train. Gradle cũng hỗ trợ dependency constraints và alignment qua metadata/rule để đảm bảo các module liên quan được chọn theo cùng một nhóm phiên bản.

Không nên chỉ ép tất cả module có cùng số version vì chúng có thể thuộc các release train khác nhau. Alignment phải dựa trên quan hệ tương thích do nhà cung cấp hoặc tổ chức xác định.

## 9. Dependency locking để giữ kết quả phân giải ổn định

Constraint định nghĩa phiên bản được chấp nhận hoặc ưu tiên. Dependency locking ghi lại các phiên bản thực tế đã được phân giải cho những configuration được bật locking. Đây là hai công cụ bổ trợ nhau.

Bật dependency locking:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Sau đó chạy một task resolution phù hợp với các configuration cần khóa và yêu cầu ghi lock state:

```bash
./gradlew dependencies --write-locks
```

Gradle tạo hoặc cập nhật lockfile theo các configuration đã được resolve. Lock state cần được commit cùng mã nguồn để những lần build sau sử dụng cùng các phiên bản đã được ghi nhận.

Khi chủ động nâng cấp dependency, nhóm có thể chạy lại với `--update-locks` cho module cần cập nhật:

```bash
./gradlew dependencies --update-locks org.example:common-core
```

Sau khi cập nhật, cần xem diff lockfile, chạy test và review thay đổi trước khi commit. Không nên cập nhật toàn bộ lockfile một cách tự động trong mọi build thường ngày vì như vậy mất ý nghĩa kiểm soát thay đổi dependency.

Dependency locking đặc biệt hữu ích khi dùng dynamic version hoặc version range, nhưng nó không thay thế việc chọn version policy tốt. Nó giữ kết quả đã resolve; nhóm vẫn cần quyết định khi nào và vì sao được phép nâng version.

## 10. Dynamic versions và cache của metadata

Gradle hỗ trợ khai báo dynamic version, ví dụ:

```groovy
dependencies {
    implementation 'org.example:common-core:2.+'
}
```

Gradle sẽ tìm phiên bản phù hợp theo metadata repository. Khi có release mới, cùng build file có thể resolve ra phiên bản khác sau khi cache hết hạn hoặc bị refresh. Điều này hữu ích trong một số quy trình thử nghiệm, nhưng có thể làm build khó tái lập.

Có thể điều chỉnh thời gian cache của dynamic version:

```groovy
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor 10, 'minutes'
}
```

Với changing module, ví dụ snapshot hoặc module có cùng version nhưng nội dung được cập nhật, Gradle cũng có cơ chế cache riêng:

```groovy
configurations.configureEach {
    resolutionStrategy.cacheChangingModulesFor 5, 'minutes'
}
```

Giảm thời gian cache làm Gradle kiểm tra metadata thường xuyên hơn và có thể tăng truy cập repository. Tăng thời gian cache giúp build nhanh và ổn định trong một khoảng thời gian, nhưng có thể làm chậm việc nhận bản cập nhật. Chính sách nên dựa trên mục tiêu của nhóm và loại repository.

Khi cần kiểm tra metadata mới, có thể dùng:

```bash
./gradlew build --refresh-dependencies
```

Lệnh này yêu cầu Gradle refresh dependency cache. Nó không tự nâng dependency nếu version declaration hoặc constraints không cho phép, và cũng không thay thế dependency locking.

## 11. Maven và Ant xử lý xung đột như thế nào?

Chính sách lựa chọn phiên bản khác nhau giữa các build tool. Khi chuyển dự án hoặc đọc build cũ, không nên giả định Gradle và Maven chọn cùng một phiên bản chỉ vì cùng có các dependency declaration.

### 11.1. Maven dependency mediation

Maven sử dụng dependency mediation để chọn một phiên bản khi nhiều nhánh phụ thuộc yêu cầu cùng artifact. Quy tắc phổ biến là **nearest definition**: phiên bản được tìm thấy ở độ sâu gần dependency gốc hơn sẽ được ưu tiên. Nếu hai phiên bản ở cùng độ sâu, thứ tự khai báo trong POM có thể quyết định lựa chọn.

Ví dụ:

```text
application
├── library-a
│   └── common-core:1.4       (depth 2)
└── library-b
    └── helper
        └── common-core:2.1   (depth 3)
```

Trong ví dụ, Maven có thể chọn `common-core:1.4` vì nó nằm gần project gốc hơn, dù `2.1` có số version cao hơn. Đây là điểm khác với conflict resolution mặc định của Gradle, vốn thường chọn version cao nhất trong các yêu cầu thông thường.

Maven có thể quản lý phiên bản tập trung qua `dependencyManagement`:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>common-core</artifactId>
      <version>2.2.0</version>
    </dependency>
  </dependencies>
</dependencyManagement>
```

`dependencyManagement` định nghĩa phiên bản mặc định cho dependency khi module được khai báo; nó không tự thêm dependency vào project. Maven cũng hỗ trợ import BOM với `type` là `pom` và `scope` là `import` để chia sẻ tập version management.

### 11.2. Enforcer và kiểm soát convergence trong Maven

Maven Enforcer Plugin có rule như `dependencyConvergence` để phát hiện trường hợp các nhánh phụ thuộc yêu cầu phiên bản khác nhau. Rule này giúp nhóm phát hiện graph không nhất quán thay vì chỉ chấp nhận kết quả mediation.

Ví dụ cấu hình minh họa:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-enforcer-plugin</artifactId>
      <version>3.5.0</version>
      <executions>
        <execution>
          <id>enforce-dependency-convergence</id>
          <goals>
            <goal>enforce</goal>
          </goals>
          <configuration>
            <rules>
              <dependencyConvergence/>
            </rules>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

Rule này có thể khiến build thất bại khi phát hiện nhiều phiên bản trong graph. Khi đó nhóm cần quản lý version bằng dependencyManagement, BOM, exclusion hoặc nâng dependency phù hợp.

### 11.3. Ant và classpath thủ công

Ant không có dependency resolution model chuẩn như Maven hoặc Gradle. Dự án thường tải JAR, đặt vào thư mục `lib` rồi xây dựng classpath qua `path`, `fileset` hoặc thuộc tính.

Ví dụ:

```xml
<path id="application.classpath">
  <fileset dir="lib">
    <include name="*.jar"/>
  </fileset>
</path>
```

Nếu thư mục `lib` chứa nhiều JAR cùng cung cấp class có cùng tên, kết quả có thể phụ thuộc thứ tự classpath và cách classloader tìm lớp. Người quản lý build phải tự quyết định JAR nào được giữ, loại bỏ phiên bản cũ và kiểm tra dependency graph bằng công cụ bổ trợ nếu cần.

## 12. Công cụ quan sát và điều tra phiên bản được chọn

Không nên đoán phiên bản thực tế từ dòng `dependencies` trong build script. Hãy xem kết quả resolution của configuration cụ thể.

### 12.1. Xem dependency tree

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Lệnh này in cây dependency của `runtimeClasspath`. Có thể thay bằng `compileClasspath`, `testRuntimeClasspath` hoặc configuration cần điều tra.

### 12.2. Tìm lý do một module được chọn

```bash
./gradlew dependencyInsight \
  --dependency common-core \
  --configuration runtimeClasspath
```

`dependencyInsight` cho biết module được yêu cầu từ những nhánh nào, phiên bản nào bị thay thế và lý do lựa chọn. Đây thường là lệnh hữu ích nhất khi một version bất ngờ xuất hiện.

Trên Windows PowerShell có thể viết trên một dòng:

```powershell
.\gradlew.bat dependencyInsight --dependency common-core --configuration runtimeClasspath
```

### 12.3. Phát hiện xung đột thay vì tự chọn phiên bản cao nhất

Trong một số project, nhóm muốn build dừng lại khi cùng một module được yêu cầu ở nhiều version. Có thể bật:

```groovy
configurations.configureEach {
    resolutionStrategy.failOnVersionConflict()
}
```

Khi đó Gradle sẽ báo lỗi conflict để nhóm xử lý qua constraint, platform hoặc dependency update. Cách này phù hợp với dự án muốn kiểm soát chặt, nhưng có thể làm build hiện tại thất bại ngay khi xuất hiện graph vốn trước đây được giải quyết tự động. Nên áp dụng có chủ đích và chuẩn bị cách xử lý các xung đột đã tồn tại.

### 12.4. Các lệnh Maven tương ứng

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.example:common-core
```

Lệnh `dependency:tree` giúp xem đường đi của dependency và phiên bản trong graph Maven. Có thể kết hợp Enforcer Plugin để kiểm tra convergence hoặc version policy.

## 13. Xây dựng chính sách lựa chọn phiên bản cho dự án

Một chính sách thực tế nên được định nghĩa ở cấp dự án hoặc tổ chức, không phụ thuộc vào việc từng lập trình viên tự thêm `force` khi build gặp lỗi.

### 13.1. Chọn nguồn quản lý version

Có thể dùng một hoặc kết hợp các cơ chế sau:

- **Version catalog:** tập trung tên alias và version declaration để build script dễ đọc. Catalog không tự thay thế dependency constraint hoặc locking.
- **Platform/BOM:** quản lý các version liên quan và alignment giữa các module.
- **Dependency constraints:** đặt giới hạn, phiên bản ưu tiên hoặc phiên bản nghiêm ngặt cho module.
- **Dependency locking:** ghi lại kết quả resolve đã được phê duyệt.
- **Resolution rules:** xử lý ngoại lệ có chủ đích như module thay thế hoặc loại version có vấn đề.

Không nên nhầm version catalog với lockfile. Catalog mô tả version mà người viết build khai báo; lockfile ghi lại version thực tế đã được resolve cho configuration có bật locking.

### 13.2. Quy tắc nâng cấp

Nhóm nên thống nhất:

1. Ai được đề xuất và phê duyệt nâng dependency?
2. Nâng version đơn lẻ hay nâng cả platform/BOM?
3. Release notes, compatibility matrix và advisory bảo mật nào phải được xem xét?
4. Những test nào phải chạy trước khi cập nhật lockfile?
5. Có cần thử nghiệm trên runtime Java thấp nhất mà sản phẩm hỗ trợ không?
6. Khi phát hiện regression, rollback về version nào và bằng cách nào?

Nâng dependency nên là thay đổi có review, có diff lockfile và có kết quả kiểm thử. Tránh để CI tự resolve dynamic version mới rồi tạo ra kết quả khác nhau mà không có thay đổi được review trong repository.

### 13.3. Xử lý lỗ hổng bảo mật

Khi scanner báo một dependency có lỗ hổng, cần xác định module và version thực sự có mặt trong runtime graph, không chỉ xem version được khai báo trực tiếp. Dependency bắc cầu có thể đưa phiên bản dễ tổn thương vào ứng dụng.

Quy trình xử lý nên gồm:

- Xác định configuration và artifact có chứa module bị ảnh hưởng.
- Dùng `dependencyInsight` hoặc `dependency:tree` để tìm nhánh kéo module vào graph.
- Xác định phiên bản đã vá và dải tương thích của các consumer.
- Cập nhật dependency trực tiếp, platform/BOM hoặc constraint tại nơi phù hợp.
- Chạy test, kiểm tra runtime và cập nhật lock state nếu sử dụng dependency locking.
- Ghi lại lý do và theo dõi ngoại lệ nếu chưa thể nâng ngay.

Không nên ép phiên bản mới nhất chỉ dựa trên số version. Phiên bản đã vá cần tương thích với các thư viện phụ thuộc và runtime mà sản phẩm hỗ trợ.

## 14. Ví dụ: chuẩn hóa một dependency bắc cầu

Giả sử `library-a` và `library-b` kéo về hai phiên bản `common-core` khác nhau. Nhóm đã kiểm thử phiên bản `2.2.0` với toàn bộ ứng dụng và muốn dùng cùng phiên bản đó.

Một cấu hình có thể dùng platform nội bộ:

```groovy
dependencies {
    implementation platform(project(':dependency-platform'))
    implementation 'org.example:library-a:2.0'
    implementation 'org.example:library-b:3.0'
    implementation 'org.example:common-core'
}
```

Trong project `dependency-platform`:

```groovy
plugins {
    id 'java-platform'
}

dependencies {
    constraints {
        api('org.example:common-core:2.2.0') {
            because 'Đã xác nhận tương thích với library-a và library-b'
        }
    }
}
```

Sau đó nhóm có thể xem resolution:

```bash
./gradlew dependencyInsight \
  --dependency common-core \
  --configuration runtimeClasspath
```

Nếu kết quả chọn `2.2.0`, cần tiếp tục kiểm thử ứng dụng và xem metadata của các dependency consumer. Platform giúp thống nhất lựa chọn nhưng không chứng minh tương thích. Nếu một thư viện chỉ hỗ trợ `1.x`, constraint mới có thể làm lộ incompatibility và cần nâng thư viện đó hoặc chọn một version khác đáp ứng tất cả yêu cầu.

## 15. Những điểm cần nhớ

- Xung đột phiên bản xuất hiện khi nhiều nhánh yêu cầu các version khác nhau của cùng module hoặc khi các component xung đột về capability.
- Gradle mặc định thường chọn version cao nhất trong xung đột module thông thường; điều đó không chứng minh version mới nhất tương thích với mọi consumer.
- Dependency constraint tham gia lựa chọn nhưng không tự thêm dependency vào graph.
- `prefer`, `require`, `strictly` và `reject` thể hiện mức ràng buộc khác nhau; cần chọn đúng ý nghĩa thay vì dùng chúng thay thế lẫn nhau.
- Platform/BOM giúp quản lý và align nhóm dependency có quan hệ phiên bản.
- `force` và resolution rules là công cụ can thiệp mạnh; cần giới hạn phạm vi, ghi lý do và kiểm thử.
- Dependency locking giữ kết quả resolve đã phê duyệt; dependency verification kiểm tra tính toàn vẹn artifact và giải quyết một vấn đề khác.
- Maven thường dùng nearest definition trong dependency mediation; Ant thường cần quản lý classpath thủ công.
- `dependencies`, `dependencyInsight` và `mvn dependency:tree` giúp xem graph thực tế thay vì phỏng đoán từ build file.
- Chính sách lựa chọn cần cân bằng tương thích, bảo mật, khả năng tái lập và quy trình nâng cấp có review.

Chính sách lựa chọn phiên bản biến việc giải quyết xung đột từ một quyết định ngầm của công cụ thành quy tắc có thể đọc, kiểm soát và kiểm chứng. Khi dự án kết hợp constraint, platform/BOM, locking và công cụ phân tích dependency đúng mục đích, nhóm có thể nâng thư viện an toàn hơn, phát hiện sớm xung đột và duy trì classpath nhất quán giữa máy phát triển, CI và môi trường chạy thực tế.
