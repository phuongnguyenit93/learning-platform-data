# Đọc yêu cầu Java và ma trận hỗ trợ của framework

Khi nâng cấp ứng dụng Java, một câu hỏi thường xuất hiện rất sớm: **“Framework hiện tại có hỗ trợ JDK muốn nâng cấp không?”**. Câu trả lời không thể dựa vào việc chương trình biên dịch thành công, một bài viết ngắn nói “chạy được trên Java mới”, hoặc một bảng chỉ ghi phiên bản Java tối thiểu. Đối với sản phẩm chạy lâu dài, đội kỹ thuật cần biết chính xác **phiên bản framework nào**, **phiên bản JDK nào**, **cấu hình build/runtime nào**, **đến thời điểm nào** và **theo mức bảo đảm nào** được nhà phát hành hỗ trợ.

Chẳng hạn, một framework có thể công bố “requires Java 17 or later”. Câu này cho biết ngưỡng tối thiểu ở một phạm vi nhất định, nhưng **không mặc nhiên xác nhận mọi JDK tương lai đều nằm trong ma trận đã kiểm thử hoặc được hỗ trợ chính thức**. Một phiên bản framework khác có thể được thử với JDK 21 nhưng yêu cầu plugin Gradle mới để build, hoặc có extension/native-image integration chưa hỗ trợ môi trường đó.

Bài học này hướng dẫn cách đọc **Java requirements** và **support matrix** của framework trong bối cảnh **Java Advance Compatibility Migration**; từ việc tìm đúng nguồn tài liệu, giải nghĩa các trạng thái hỗ trợ, kiểm tra dependency và build tool, đến lập bảng quyết định, lên lộ trình migration và kiểm chứng bằng các bài test đại diện.

> **Nguyên tắc:** Chỉ kết luận một tổ hợp được framework hỗ trợ sau khi xác định được phạm vi, phiên bản, thời điểm và nguồn chính thức của phát biểu đó. Những bảng trong bài dùng tên và số phiên bản giả định để minh họa phương pháp đọc, **không phải thông báo hỗ trợ hiện hành của bất kỳ framework cụ thể nào**.

## 1. “Hỗ trợ Java” có nhiều nghĩa

### 1.1. JDK tối thiểu không phải là JDK tối đa đã kiểm chứng

Cần phân biệt:

- **Minimum Java version:** phiên bản Java thấp nhất mà framework yêu cầu để chạy hoặc biên dịch theo tài liệu.
- **Supported Java versions:** những phiên bản JDK nằm trong cam kết hỗ trợ của framework ở một thời điểm và một release line cụ thể.
- **Tested / certified Java versions:** các phiên bản runtime được đội phát triển/vendor đưa vào test hoặc certification matrix.
- **Known to work / compatible in practice:** một cấu hình có thể chạy trong thực tế nhưng chưa có cam kết chính thức.
- **Unsupported / end of support:** không còn nằm trong cam kết hỗ trợ hoặc đã bị loại khỏi support window.
- **Unknown / not documented:** không tìm thấy bằng chứng rõ; **không được tự đổi thành “supported” hoặc “unsupported”**.

Ví dụ tài liệu giả định:

```text
Framework Alpha 4.2
- Requires Java 17 or higher
- Tested on Java 17 and Java 21
- Java 25 validation is planned
```

Diễn giải đúng:

1. Java 17 là ngưỡng tối thiểu được công bố.
2. Java 17 và 21 có bằng chứng “tested” theo tài liệu này.
3. Java 25 chưa được chứng minh ở cấp “tested” chỉ từ dòng mô tả trên.
4. Không thể tự suy ra Java 25 bị cấm chạy, cũng không thể tự khẳng định Java 25 đã được hỗ trợ chính thức.
5. Nếu có support contract, phải tra đúng chính sách hỗ trợ thương mại thay vì coi “tested” luôn đồng nghĩa có SLA.

### 1.2. Hỗ trợ để chạy không đồng nghĩa hỗ trợ để build

Một project Java có thể sử dụng nhiều JDK khác nhau trong cùng pipeline:

```text
Developer IDE JDK          : 21
Maven/Gradle daemon JDK    : 21
Java compiler toolchain   : 21
javac --release           : 17
Test execution JVM        : 17 và 21
Production runtime        : 17
Framework minimum runtime : 17
```

Tổ hợp này có thể hợp lý. Mã ứng dụng được biên dịch bằng compiler Java 21 nhưng phát hành bytecode/API target Java 17. Tuy nhiên, framework plugin, annotation processor hoặc test runner có thể có yêu cầu JDK riêng.

Khi tài liệu ghi “Java 21 required”, phải kiểm tra nó áp dụng cho **runtime**, **build tool**, **compiler**, **native image builder**, hay chỉ **một plugin phát triển**.

### 1.3. Hỗ trợ Java SE khác hỗ trợ Jakarta EE và application server

Đặc biệt với ứng dụng web hoặc enterprise:

- **Java SE/JDK:** runtime Java mà JVM cung cấp.
- **Jakarta EE API:** tập hợp API và specification cho ứng dụng enterprise.
- **Jakarta EE implementation/application server:** ví dụ server chạy ứng dụng và cung cấp container services.
- **Servlet container:** có phạm vi API khác full Jakarta EE server.
- **Framework:** có thể chạy trên servlet container, reactive server hoặc embedded server với yêu cầu riêng.

Một phiên bản server công bố hỗ trợ Java 21 không tự động bảo đảm framework/ORM/driver trong ứng dụng cũng hỗ trợ Java 21. Ngược lại, framework chạy được trên Java 21 không có nghĩa application server cũ có thể nạp artifact mới.

## 2. Những tầng compatibility cần đọc cùng nhau

Một ứng dụng thực tế có thể đi qua chuỗi:

```text
                 Java runtime (vendor, version, OS, arch)
                              |
                              v
                       Application server
                              |
                              v
                       Framework core
                              |
                  +-----------+-----------+
                  |           |           |
                  v           v           v
                 ORM      HTTP stack    Security
                  |           |           |
                  +-----------+-----------+
                              |
                              v
                  Application code / libraries
                              |
                              v
                    Drivers / native / agents

Build-time riêng:
JDK -> Maven/Gradle -> plugins -> annotation processors -> artifact
```

Mỗi tầng có thể công bố ma trận riêng. Để quyết định nâng JDK, không được chỉ đọc trang framework core rồi bỏ qua những thành phần nằm trên đường chạy quan trọng.

| Tầng | Câu hỏi cần xác nhận | Nguồn thông tin hữu ích |
|---|---|---|
| JVM/JDK | Vendor, release, update level, OS/architecture có được sản phẩm sử dụng/hỗ trợ không? | Tài liệu JDK vendor và runtime support policy |
| Framework core | Phiên bản framework nào yêu cầu/hỗ trợ JDK đích? | Reference guide và support matrix của framework |
| Framework plugins | Plugin build, starter, CLI, code generator có cùng release line không? | Plugin docs và release notes |
| Application server | Server/container có chạy được JDK đích và framework version không? | Server compatibility matrix |
| ORM, security, HTTP | Module tích hợp và thư viện bắc cầu có tương thích? | BOM, release notes, issue tracker, compatibility docs |
| Build tool | Gradle/Maven version có thể chạy trên JDK đích không? | Ma trận runtime/build của build tool |
| Test tools | JUnit, mocking/bytecode, coverage và agents có hỗ trợ JDK đích? | Tài liệu của từng tool |
| Driver/native | JDBC driver, JNI, TLS provider, native image toolchain có được kiểm chứng? | Vendor docs và OS/arch matrix |
| App artifact | Class-file major và Java API target có đúng? | Cấu hình compiler và inspect artifact |
| Hạ tầng | Base image, container runtime, CA store và deployment pipeline có hỗ trợ? | CI/image/deployment documentation |

Đừng nhầm một hệ thống “khởi động được” với toàn bộ tổ hợp đã được hỗ trợ. Một lỗi trong ORM, bytecode proxy hoặc JDBC driver có thể chỉ xuất hiện khi xử lý một nghiệp vụ hiếm.

## 3. Nguồn tài liệu nào có giá trị cao nhất?

### 3.1. Thứ tự ưu tiên nguồn

Khi cần chứng minh một tổ hợp được hỗ trợ, nên ưu tiên:

1. **Reference documentation chính thức cho đúng framework version.**
2. **Support / compatibility matrix và lifecycle policy của vendor** nếu có.
3. **Release notes, migration guide và known issues** của đúng release line.
4. **BOM/dependency management và plugin compatibility docs** cho các thành phần đi kèm.
5. **JDK vendor, build tool và application-server docs** tương ứng.
6. **Issue tracker chính thức** để làm rõ bug hoặc giới hạn chưa cập nhật vào tài liệu.
7. Bài viết cộng đồng, Stack Overflow, blog, kinh nghiệm vận hành — hữu ích để tìm dấu hiệu, nhưng **không thay thế cam kết chính thức**.

Nếu có hai nguồn khác nhau, cần xem chúng có nói đến cùng release line và cùng loại “support” hay không. Một trang marketing nói “Java 21 ready” có thể không có cùng độ chính xác với bảng compatibility và migration guide.

### 3.2. Tài liệu theo phiên bản, không phải trang “latest” mặc định

Nhiều website đưa người đọc đến tài liệu của **bản mới nhất**, ngay cả khi ứng dụng đang chạy một framework version cũ.

Ví dụ giả định:

```text
Ứng dụng đang dùng: Framework Alpha 3.8
Trang mở mặc định: Framework Alpha 5.0 latest
Bảng latest: "Requires Java 21"
```

Sẽ sai nếu kết luận Alpha 3.8 yêu cầu Java 21 chỉ vì đọc trang của Alpha 5.0. Cũng sai nếu lấy thông tin “Java 25 supported” của bản mới áp dụng cho branch cũ.

Trước khi ghi nhận yêu cầu Java, xác minh:

- URL/tài liệu có chọn đúng version.
- Dòng release hoặc minor version có đúng không.
- Trang có dành cho OSS, enterprise hay commercial edition không.
- Release notes có giới hạn cụ thể hơn trang tổng quan không.
- Tài liệu có ngày cập nhật hoặc ghi chú cho các patch releases nào không.

### 3.3. Vì sao thời điểm kiểm tra quan trọng?

Một release line có thể được cập nhật để hỗ trợ JDK mới ở một patch release, hoặc ngừng nhận bản vá sau khi hết vòng đời. Cùng một câu “supports Java 21” cần được đặt vào thời điểm:

```text
Checked on: 2026-11-12
Product line: Alpha 4.x
Exact release: Alpha 4.2.6
Claim: Java 21 is supported
Source: official versioned documentation
Support status: maintained / limited / EOL (verify separately)
```

Đây là biểu mẫu minh họa cách ghi chứng cứ, không phải thông tin thật về Alpha. Trong một migration kéo dài nhiều tháng, **nên kiểm tra lại support matrix trước khi freeze release**.

### 3.4. Phân biệt “không thấy trong tài liệu” và “không được hỗ trợ”

Nếu một JDK không xuất hiện trong bảng, có thể có nhiều tình huống:

- JDK quá mới, chưa được nhà phát hành thử nghiệm.
- Bảng chỉ liệt kê các phiên bản LTS, không phải mọi release.
- Tài liệu chưa được cập nhật.
- Support chỉ áp dụng cho một edition hoặc bản patch cụ thể.
- Framework vẫn có thể chạy nhưng vendor chưa cam kết.
- Framework thật sự không hỗ trợ; cần bằng chứng hoặc xác nhận rõ.

Quy tắc báo cáo nên dùng ba trạng thái tách biệt: **Supported**, **Unsupported**, **Not verified**. Không tự suy đoán từ sự im lặng của tài liệu.

## 4. Cách đọc những cụm từ thường gặp trong support matrix

| Cụm từ | Cách hiểu cẩn trọng | Hành động cần làm |
|---|---|---|
| `Minimum Java 17` | Ngưỡng chạy/biên dịch tối thiểu trong phạm vi được nêu | Kiểm tra JDK mới hơn có nằm trong supported/tested list không |
| `Java 21 compatible` | Có tuyên bố về tương thích với Java 21 nhưng cần xác nhận mức bảo đảm | Đọc scope, patch release, limitations |
| `Tested on Java 17, 21` | Những runtime đã được thử theo quy trình nào đó | Phân biệt tested và support SLA |
| `Certified on JDK vendor X` | Certification cho vendor/phân phối cụ thể | Kiểm tra vendor/edition/OS/architecture |
| `Java 25 support added in 4.3.2` | Support bắt đầu từ patch đã nêu | Không áp dụng cho 4.3.0/4.2.x nếu không có bằng chứng |
| `Runs on Java 17+` | Có tuyên bố biên độ rộng | Tìm exclusions, known issues và lifecycle |
| `Requires Java 21 for build` | Công cụ build cần JDK 21 | Không tự suy ra runtime của artifact bắt buộc Java 21 |
| `Java 21 baseline` | Release line đã nâng mức nền tảng | Xác minh minimum runtime và bytecode output |
| `Not tested with Java 25` | Chưa có chứng nhận kiểm thử từ nguồn này | Đặt trạng thái Not verified và lên test/trao đổi vendor |
| `End of maintenance` | Hết hoặc giảm bảo trì theo policy | Kiểm tra chính sách security fixes và migration path |

Điểm quan trọng: nhiều câu dùng cùng từ “support” nhưng có **quyền lợi khác nhau**. OSS community support, vendor enterprise support và support qua một bản distribution có thể có điều kiện không giống nhau.

## 5. Minimum runtime, build JDK và target bytecode

### 5.1. Class-file major version

JVM chỉ có thể nạp những class-file versions mà nó hỗ trợ. Các mốc thường gặp:

| Java | Class-file major |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

Nếu artifact mang major 65, JVM Java 17 không thể nạp class đó dù POM ghi “Java 17 compatible”.

Để kiểm tra một class trong JAR:

```shell
javap -verbose -classpath framework-or-app.jar com.example.Main
```

Dòng `major version: 61` biểu thị class-file version tương ứng Java 17. Nhưng kiểm tra một class không đủ chứng minh toàn bộ nested/shaded JAR hoặc dependencies bắc cầu cũng cùng mức.

### 5.2. `--release` khác `--source` và `--target`

Với `javac` hiện đại:

```shell
javac --release 17 -d build/classes src/com/example/App.java
```

`--release 17` giới hạn các khả năng source, bytecode và Java SE platform API phù hợp release 17 trong phạm vi compiler hỗ trợ.

Ngược lại, `--source 17 --target 17` không cung cấp đầy đủ sự bảo vệ khỏi việc vô tình gọi Java API mới hơn nếu compiler dùng platform libraries của JDK mới. Vì vậy, khi framework còn hỗ trợ Java 17 nhưng CI dùng JDK 21, `--release 17` là cách có ý nghĩa để thể hiện policy của chính ứng dụng.

**Tuy nhiên:** `--release` không tự kiểm tra minimum Java của các third-party JAR, code generator, agents và native dependencies.

### 5.3. Một framework có thể hỗ trợ chạy JDK 21 nhưng vẫn tạo library target Java 17

Điều này không mâu thuẫn. Một framework build bằng JDK mới có thể phát hành artifact dùng trên nhiều JDK, và ứng dụng tương thích có thể được biên dịch cho Java 17.

Ngược lại, một plugin build yêu cầu Java 21 nhưng project output vẫn target Java 17 cũng có thể là cấu hình có chủ đích. Cần đọc đúng mục “Building”, “Running” và “Supported JDKs” của từng thành phần.

## 6. Ví dụ ma trận giả định: học cách đọc thay vì học thuộc version

Giả sử tổ chức khảo sát ba dòng framework:

| Framework release | Java tối thiểu | JDK được tài liệu ghi đã thử | Tình trạng bảo trì | Nhận định sơ bộ |
|---|---:|---|---|---|
| Alpha 3.x | 11 | 11, 17 | Maintenance ending | Không chọn cho migration dài hạn nếu support sắp kết thúc |
| Alpha 4.x | 17 | 17, 21 | Active | Ứng viên khi muốn chạy Java 21 |
| Alpha 5.x | 21 | 21, 25 | Active | Ứng viên khi sẵn sàng tăng runtime floor lên Java 21 |

**Tất cả tên và số trong bảng này đều giả định**; mục đích là học cách suy luận. Nếu ứng dụng còn một consumer chạy Java 17, việc nâng lên Alpha 5.x có minimum Java 21 sẽ phá vỡ hợp đồng consumer đó. Nếu mục tiêu chạy Java 25 nhưng Alpha 4.x chỉ ghi tested đến 21, cần xem thêm patch notes và chứng cứ hỗ trợ trước khi xác nhận.

### 6.1. Tạo bảng quyết định cho ứng dụng cụ thể

Ví dụ ứng dụng `order-service`:

```text
Current:
  Framework: Alpha 3.4
  Runtime JDK: 17
  Build JDK: 17
  Deployment: Linux x86_64
  Database driver: D 2.x
  Target: JDK 21

Candidate:
  Framework: Alpha 4.2
  Runtime JDK: 21
  Build JDK: 21
  Database driver: D 3.x
```

Bảng quyết định nên thêm các cột:

- Source URL/document version.
- Claim type: minimum, tested, officially supported, EOL.
- JDK vendor và OS/architecture.
- Mức hỗ trợ của framework plugins và driver.
- Rủi ro known issues.
- Bộ test phải chạy.
- Kết quả cuối: supported / not verified / unsupported / blocked.

Không chỉ ghi “framework OK” vì nó che giấu phạm vi đã xác minh.

### 6.2. Giao của các tập hỗ trợ

Nếu môi trường sản phẩm gồm nhiều thành phần, danh sách JDK có thể chọn phải nằm trong **giao** của các tập được các thành phần bắt buộc hỗ trợ.

Ví dụ giả định:

```text
Framework Alpha 4.x  : {17, 21}
Build tool B         : {17, 21, 25}
Application server C : {11, 17, 21}
JDBC driver D        : {17, 21}

Intersection         : {17, 21}
```

Khi muốn chọn Java 25, bảng trên chưa có căn cứ. Nhưng cũng không đủ để dừng ở bước tính giao: dữ liệu này phải cùng thời điểm, cùng OS/architecture và cùng bản patch release, đồng thời các restrictions của từng thành phần được đáp ứng.

## 7. Spring ecosystem: đọc version theo từng lớp

### 7.1. Spring Framework và Spring Boot không phải một sản phẩm

Trong hệ Spring, có nhiều dòng version:

- Spring Framework core.
- Spring Boot.
- Spring Data.
- Spring Security.
- Spring Cloud release train.
- Spring Integration/Batch và những project liên quan.
- Embedded server, servlet/reactive stack.
- Hibernate/JPA, logging, testing và các dependency do BOM quản lý.

Khi tra một Spring Boot version, cần xác minh:

1. Minimum Java/JDK được công bố cho **Spring Boot version đó**.
2. Những phiên bản Spring Framework và thư viện đi kèm được quản lý.
3. Yêu cầu Maven/Gradle và **Spring Boot build plugin**.
4. Embedded server và Jakarta/Servlet baseline.
5. Spring Cloud release train có tương thích với Boot release line không nếu ứng dụng dùng Spring Cloud.
6. Java vendor/runtime và native-image support nếu có.
7. Patch release nào sửa các vấn đề với JDK mới.

Không nên suy từ “Spring Framework chạy trên Java X” rằng mọi bản Spring Boot hoặc Spring Cloud đều hỗ trợ Java X.

### 7.2. Ví dụ cách ghi bằng chứng

```text
Component           : Spring Boot
Exact version       : <version from project>
Reference docs      : <versioned URL>
Minimum runtime JDK : <documented value>
Tested JDKs         : <documented list>
Build plugin version: <version in project>
Gradle/Maven support: <documented requirement>
Spring Cloud train  : <value if applicable>
Known issues        : <links to version-specific notes>
Decision            : supported / blocked / not verified
```

Đây là biểu mẫu, không phải bảng điền sẵn bằng các version mới nhất. Khi một đội nói “nâng Spring” mà chỉ ghi một dòng, khả năng bỏ sót dependency alignment là rất cao.

### 7.3. Chuyển đổi `javax.*` và `jakarta.*` là trục riêng

Một migration framework có thể đồng thời chuyển từ Java EE namespaces cũ sang Jakarta EE namespaces mới. Đây **không phải** thay đổi class-file version đơn thuần.

Ví dụ một import cũ:

```java
import javax.persistence.Entity;
```

Một API Jakarta Persistence mới có thể sử dụng:

```java
import jakarta.persistence.Entity;
```

Nếu framework release line yêu cầu Jakarta APIs, source code, JPA provider, servlet container và các thư viện tích hợp cần chuyển đồng bộ. Chạy trên JDK mới không tự đổi những packages này.

### 7.4. Embedded server và cloud release train

Một phiên bản Spring Boot có thể đi kèm một embedded server cụ thể, còn Spring Cloud có ma trận tương thích riêng với các dòng Boot. Cần tra **bảng tương thích giữa các phiên bản**, không chọn các bản “mới nhất” độc lập.

Đối với ứng dụng chạy WAR trên server ngoài, còn phải đọc support matrix của server/container đó. Một WAR build bằng Boot/Framework mới nhưng server cung cấp Servlet API cũ có thể bị lỗi dù JDK được hỗ trợ.

## 8. Quarkus, Micronaut và các framework AOT/native

### 8.1. Framework có bước augmentation/build-time code generation

Một số framework hiện đại làm nhiều việc ở build time: annotation processing, bytecode generation, augmentation hoặc native-image preparation. Vì vậy, Java runtime requirements có thể chia:

- JDK để chạy framework và ứng dụng JVM.
- JDK để build application.
- JDK/định dạng và phiên bản GraalVM/Mandrel/native-image để tạo native executable.
- Minimum Java của Maven/Gradle plugins.
- JDK tối thiểu của CLI và test tools.
- Hỗ trợ extensions theo từng phiên bản framework.

Không nên đọc một câu “supports Java 21” rồi suy ra tất cả extensions và native image configurations cũng đã được chứng nhận.

### 8.2. Quarkus: platform BOM và extension matrix

Khi đọc tài liệu Quarkus, nên kiểm tra đúng phiên bản platform và extension, bởi chúng thường được quản lý theo BOM hoặc curated platform dependencies.

Những câu hỏi:

- Quarkus release đang dùng yêu cầu Java nào?
- JVM mode và native mode có cùng ma trận hỗ trợ không?
- Build tool plugin cần JDK/Gradle/Maven version nào?
- Native image toolchain yêu cầu platform và OS/architecture nào?
- Các extension database, messaging, security có cùng phiên bản nền tảng?
- Có migration note nào về cấu hình, namespace hoặc API đã thay đổi?

### 8.3. Micronaut: runtime và annotation processing

Với Micronaut hoặc framework phụ thuộc mạnh vào compile-time processing, cần xác nhận processor/plugin/build tool phiên bản tương thích với JDK/compiler. Một ứng dụng có thể chạy trên một JDK nhưng annotation processor cũ gặp lỗi khi build bằng javac mới.

Nên kiểm tra riêng:

- Micronaut Framework release line.
- Micronaut Gradle/Maven plugin.
- Annotation processors và generated code.
- Data/Serialization/Security modules nếu dùng.
- Native support và AOT features.
- Các runtime JDK thực sự được framework kiểm thử.

### 8.4. JVM mode và native image là hai ma trận

Ví dụ giả định:

| Chế độ | JDK sử dụng | Công cụ bổ sung | Cần kiểm tra |
|---|---|---|---|
| JVM application | OpenJDK/Temurin/Oracle/... | Java launcher | JDK runtime và dependencies |
| Native executable | GraalVM/Mandrel hoặc native-image toolchain tương thích | C compiler, libc, OS image | Native toolchain version, OS/architecture, reflection/resource config |
| Container JVM | JRE/JDK trong base image | Container runtime | CPU architecture, CA store, libc, JVM flags |
| Container native | Native executable + runtime libraries | OS base image | ABI, dynamic libraries và compatibility |

Một dòng framework hỗ trợ JDK 21 **không tự chứng minh** Native Image của cùng ứng dụng chạy được trên mọi Linux distro.

## 9. Jakarta EE, servlet container và ứng dụng triển khai ngoài

### 9.1. Container support là một điều kiện bắt buộc

Ứng dụng enterprise có thể chạy trên:

- Servlet container.
- Full Jakarta EE application server.
- Embedded server.
- Một runtime do tổ chức đóng gói riêng.

Các thành phần này có thể công bố phiên bản Java khác nhau. Khi nâng JDK, hãy xem:

1. Server version hiện tại có hỗ trợ JDK mới không?
2. Nếu cần nâng server, ứng dụng có phải đổi Jakarta EE specification level không?
3. Java/Jakarta API do server cung cấp có xung đột với JAR đóng cùng WAR/EAR không?
4. Các provider như JPA, CDI, transaction, messaging có tương thích?
5. Tài liệu server có phân biệt community support và commercial support không?
6. OS/architecture của môi trường đích có nằm trong certification list không?

### 9.2. Tránh hai bản API/provider không tương thích

Ví dụ một ứng dụng có thể đóng gói một bản servlet/JPA API trong WAR nhưng server đã cung cấp phiên bản khác. Lỗi này không được giải quyết bằng cách nâng JDK.

Nên xác định scope dependency (ví dụ `provided` ở Maven khi container cung cấp API), kiểm tra effective dependency graph và thử deploy lên đúng server. Không chỉ chạy unit test trong IDE rồi kết luận đã tương thích.

### 9.3. Server version và JDK phải có kế hoạch cập nhật cùng nhau

Nếu server cũ EOL hoặc không được chứng nhận trên JDK mục tiêu, có thể cần bước trung gian:

```text
Legacy JDK + Legacy server
          |
          v
Supported newer server on current JDK
          |
          v
Newer server + Target JDK
```

Hoặc tổ chức có thể chọn nâng cả hai trong một release nếu đã có integration test và rollback plan đủ tốt. Phương án nào tối ưu tùy dependency và yêu cầu dịch vụ; không nên đưa một khuyến nghị chung cho mọi application server.

## 10. Framework release line và vòng đời hỗ trợ

### 10.1. “Chạy được” không giải quyết bài toán bảo trì

Một bản framework cũ có thể chạy trên Java 21 sau khi thêm vài flags, nhưng release line đó đã hết security maintenance. Khi đó migration chỉ giải quyết runtime trước mắt và để lại một rủi ro sản phẩm dài hạn.

Hãy đọc lifecycle policy:

- General availability (GA) và ngày phát hành.
- Support window của major/minor line.
- OSS maintenance so với commercial support.
- Security-only maintenance phase.
- End of maintenance và End of Support (EOL/EOS).
- Điều kiện hỗ trợ cho bản LTS.
- Yêu cầu update lên patch release mới nhất của dòng đang hỗ trợ.
- Quy tắc hỗ trợ JDK releases không phải LTS.

### 10.2. Có thể cần nâng framework trước khi nâng JDK

Nếu framework hiện tại không hỗ trợ JDK mục tiêu, một lộ trình điển hình là:

```text
Framework cũ + JDK hiện tại
       |
       v
Framework mới đã hỗ trợ JDK hiện tại
       |
       v
Kiểm thử chức năng và dữ liệu
       |
       v
Framework mới + JDK mục tiêu
       |
       v
Kiểm thử runtime/JVM và phát hành
```

Lợi ích là tách lỗi do nâng framework khỏi lỗi do nâng JDK. Tuy nhiên, cách này chỉ áp dụng nếu có **vùng giao hỗ trợ** giữa hai framework lines và hai JDK versions. Nếu framework mới không chạy trên JDK cũ, có thể phải thiết kế một bước nâng đồng thời hoặc môi trường song song.

### 10.3. Không chọn bản “latest” khi chưa xem release train

Một major release mới có thể:

- Nâng minimum JDK.
- Đổi Jakarta/Servlet baseline.
- Thay đổi property names hoặc autoconfiguration.
- Yêu cầu plugin build mới.
- Thay đổi Hibernate, Netty, Jackson hoặc logging versions.
- Loại bỏ API đã deprecated.
- Làm một số integrations cần upgrade theo.

Hãy chọn release **được hỗ trợ và tương thích với toàn stack**, không chỉ chọn số version cao nhất của một artifact.

## 11. Kiểm kê dự án trước khi đọc ma trận

### 11.1. Thông tin tối thiểu

Lập inventory cho từng application hoặc deployable:

| Trường | Ví dụ cần ghi |
|---|---|
| Service name | `order-service` |
| Framework + exact version | Framework release/patch hiện tại |
| Java runtime | Vendor, version, update level |
| Java build | JDK của Maven/Gradle/compiler |
| Packaging | JAR/WAR/EAR/container/native |
| Server/container | Embedded hoặc external server version |
| Platform | OS, architecture, container base image |
| Build tool + plugin | Maven/Gradle và plugin version |
| Critical dependencies | ORM, security, HTTP, JDBC, messaging, logging |
| Agents/native | Coverage, APM, JNI, TLS provider |
| Desired JDK | JDK target và target release date |
| Support contract | OSS/commercial và expiry |
| Owner | Team chịu trách nhiệm xác minh/triển khai |

### 11.2. Phân biệt version khai báo và version thực tế

Ví dụ POM chỉ ghi starter dependency nhưng framework BOM chọn nhiều transitive dependencies. Người đọc phải phân biệt:

- Version được khai báo trực tiếp.
- Version được parent POM hoặc BOM quản lý.
- Version cuối cùng được dependency resolution chọn.
- Version thực tế nằm trong fat JAR/container image.
- Version của plugin build và những thư viện đi theo plugin.

Một lỗi rất phổ biến là tra compatibility của dependency declaration thay vì bản thực sự được đóng vào artifact.

### 11.3. Lệnh nhận diện công cụ thực tế

Một số lệnh hữu ích khi thực hiện kiểm kê:

```shell
java -version
javac -version
./mvnw -version
./gradlew --version
```

Chỉ chạy các lệnh có tool tồn tại trong repo. Trên Windows, wrapper thường có `mvnw.cmd` hoặc `gradlew.bat`. Kết quả `java -version` trong terminal chưa chắc giống runtime production; phải kiểm tra trong container/VM/service context thực tế.

## 12. Đọc Maven project để đối chiếu framework requirement

### 12.1. Framework và dependencies thường được quản lý qua parent/BOM

Ví dụ cấu trúc POM:

```xml
<properties>
    <java.version>21</java.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>platform-bom</artifactId>
            <version>5.2.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Tên `com.example:platform-bom` và version trên chỉ là mẫu. BOM quản lý dependency versions, nhưng không mặc nhiên chứng minh mọi module trong BOM hỗ trợ Java 21. Cần đối chiếu đúng thông tin framework, integration và JDK requirements của platform version.

### 12.2. Kiểm tra effective POM

```shell
./mvnw help:effective-pom
```

Effective POM tổng hợp parent, dependency management, profiles và các cấu hình được kế thừa. Nó giúp trả lời:

- Java compiler configuration cuối cùng là gì?
- Framework BOM nào đang được import?
- Plugin phiên bản nào được dùng?
- Profile nào có thể thay đổi requirements?
- Module nào override cấu hình?

Đối với multi-module, cần xem từng module quan trọng; không nên suy từ một parent POM rằng toàn bộ child đều kế thừa giống nhau.

### 12.3. Xem dependency tree

```shell
./mvnw dependency:tree
```

Thông tin này giúp xác định version ORM, HTTP, logging, security và driver thực tế được chọn. Nếu có dependency conflict, cần hiểu Maven mediation và dependencyManagement trước khi quyết định một tổ hợp “framework version X + library version Y” là chính xác.

### 12.4. Kiểm soát minimum JDK trong Maven

Maven Enforcer Plugin có thể được dùng để chặn build chạy bằng một JDK ngoài phạm vi policy. Ví dụ khái niệm:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-build-jdk</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireJavaVersion>
                        <version>[21,22)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Version plugin và range chỉ minh họa syntax; phải lựa chọn theo support matrix thực tế. Rule trên kiểm tra **JDK dùng để thực hiện Maven goal trong phạm vi cấu hình**, không phải xác thực mọi runtime mà artifact sẽ chạy.

### 12.5. Compiler release khác Maven runtime

Trong POM có thể đặt:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Nếu compiler hỗ trợ `--release 17`, main code có thể target Java 17 ngay cả khi Maven process chạy trên JDK mới. Nhưng application framework hoặc dependency JAR mới có thể yêu cầu Java 21, khiến runtime Java 17 thất bại. **Compiler target không thể hạ mức JDK mà framework binary đã yêu cầu.**

## 13. Đọc Gradle project để đối chiếu framework requirement

### 13.1. Version của Gradle và framework plugin đều quan trọng

Gradle version phải có khả năng chạy trên JDK dùng làm daemon. Đồng thời, plugin framework có thể yêu cầu Gradle version/JDK riêng.

```shell
./gradlew --version
./gradlew dependencies
```

Lệnh `dependencies` có thể sinh report lớn cho những configurations; nên chọn scope phù hợp trong dự án multi-project.

### 13.2. Gradle Java toolchains

Ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Toolchain khai báo JDK dùng để compile hoặc cho những task được tích hợp. Nó không phải tuyên bố rằng framework đang dùng chính thức hỗ trợ Java 21. Cũng không buộc mọi task tùy chỉnh hoặc plugin đều dùng đúng toolchain.

Nếu ứng dụng cần build bằng JDK 21 nhưng library output target Java 17:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Cần kiểm tra dependencies và chạy test trên Java 17 nếu đó là runtime thấp nhất được cam kết.

### 13.3. Xem dependency được chọn

```shell
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency example-core --configuration runtimeClasspath
```

Tên `app` và `example-core` chỉ là ví dụ. Khi framework BOM quản lý versions, dùng report để xác nhận version cuối cùng và lý do chọn, không chỉ đọc version catalog.

### 13.4. Plugin dùng JDK riêng hoặc đòi Gradle phiên bản mới

Một nâng cấp framework có thể đòi nâng build plugin trước. Vì vậy cần đọc đồng thời:

- Framework runtime support.
- Gradle framework-plugin compatibility.
- Gradle runtime JVM matrix.
- Java compiler toolchain support.
- Kotlin/Groovy/Scala compiler versions nếu dự án dùng.
- Test plugin và instrumentation tool versions.

Cùng một dòng “Java 21 supported” không giải quyết những mối quan hệ này.

## 14. Framework BOM và dependency alignment

### 14.1. Vì sao BOM quan trọng khi nâng JDK?

Một framework thường phát hành BOM/dependency constraints đã được kiểm thử cho một tập thư viện. Khi tự nâng riêng Hibernate, Netty, Jackson hoặc security libraries vượt khỏi tập đó, ứng dụng có thể chạy trong tổ hợp mà framework vendor chưa xác nhận.

Ví dụ giả định:

```text
Framework Alpha 4.2 BOM:
  core         4.2.x
  orm          6.y
  json         2.z
  http-server  11.w
```

Không nên gán các số trên cho framework thật. Bài học là version set cần được hiểu như **một tổ hợp đã được release line quản lý**.

### 14.2. Override dependency không sai tuyệt đối, nhưng phải có chứng cứ

Một số lý do hợp lệ để override:

- Khắc phục CVE quan trọng trước khi framework BOM cập nhật.
- Cần driver mới hỗ trợ database hoặc JDK mục tiêu.
- Xử lý bug đã có patch ở thư viện con.
- Thực hiện migration theo giai đoạn.

Tuy nhiên, cần kiểm tra tương thích binary/API, chạy integration test và ghi lại lý do. Không tự coi “dependency mới nhất” là luôn tương thích với framework đang dùng.

### 14.3. Release train và các phiên bản liên kết

Với những hệ sinh thái có release train (ví dụ các extension/platform modules), một release train có thể tương thích với một tập framework versions xác định. Đừng nâng core framework lên bản mới mà giữ toàn bộ integration modules cũ chỉ vì build chưa báo lỗi.

Nên đặt nguyên tắc:

> Mỗi release candidate phải có một danh sách version đã resolve, được đối chiếu với matrix của framework và các tích hợp bắt buộc.

## 15. Đọc release notes và migration guide cho đúng mục đích

### 15.1. Support matrix nói “được hỗ trợ”; migration guide nói “cần đổi gì”

Một bảng support có thể xác nhận runtime Java 21, nhưng không thể liệt kê hết những thay đổi khi nâng major framework:

- Đổi package/namespace.
- Property và default configuration thay đổi.
- Endpoint hoặc serialization behavior thay đổi.
- Deprecated API bị loại bỏ.
- Thay đổi module access, reflection và classloading.
- Security default được thắt chặt.
- ORM schema/dialect behavior đổi.
- Embedded server và servlet baseline mới.
- Native-image reflection/resource configuration mới.
- Test framework hoặc startup lifecycle mới.

Do đó, sau khi xác nhận target combination được hỗ trợ, phải đọc **migration guide cho đường nâng cụ thể từ version hiện tại lên version mục tiêu**.

### 15.2. Đọc qua các mốc trung gian

Nếu ứng dụng đang ở framework major 2 và muốn lên major 5, đừng chỉ đọc release notes major 5. Cần đối chiếu những breaking changes ở 3, 4 và 5, bao gồm các yêu cầu Java đã tăng theo từng giai đoạn.

Ví dụ quy trình:

```text
Current release
      |
      v
Read next major migration guide
      |
      v
Identify source/API/config changes
      |
      v
Repeat for following release lines
      |
      v
Choose supported target patch version
```

### 15.3. Known issues có thể sửa kết luận ma trận

Một matrix ghi “Java 21 supported” nhưng issue tracker có một known bug ảnh hưởng tính năng quan trọng của ứng dụng. Khi đó, rủi ro cần ghi nhận:

```text
Framework/JDK pair: officially supported
Feature: AOT native + specific database extension
Known issue: affects current patch release
Workaround: available / unavailable
Decision: blocked for our workload until patched
```

Một tổ hợp được hỗ trợ tổng thể không bảo đảm mọi tính năng cấu hình đặc biệt đều hoạt động. Kết luận production readiness phải dựa trên workload thật.

## 16. Tài liệu OSS, commercial support và JDK vendor

### 16.1. Một phiên bản có thể có nhiều hình thức hỗ trợ

Ví dụ một framework release line có thể:

- Hết bảo trì OSS nhưng còn bản hỗ trợ thương mại.
- Được một distributor duy trì với patch riêng.
- Có extended support cho một số nền tảng/JDK.
- Chỉ hỗ trợ security patches, không nhận feature requests.
- Cần dùng một artifact repository hoặc build vendor riêng.

Nếu sản phẩm phụ thuộc vào cam kết SLA, phải kiểm tra entitlement và support contract. Không suy từ thông báo cộng đồng rằng tổ chức vẫn có quyền nhận bản vá theo điều khoản thương mại.

### 16.2. JDK vendor có thể ảnh hưởng certification

Các bản OpenJDK-based distributions thường có tính tương thích Java SE cao, nhưng một vendor support matrix có thể chỉ chứng nhận một số distributions, OS và architectures. Đặc biệt chú ý:

- Vendor và update train.
- Linux distribution/Windows Server version.
- CPU architecture, ví dụ x86_64 và aarch64.
- FIPS/TLS/crypto provider configuration.
- JVM flags hoặc các runtime options được framework hỗ trợ.
- Container runtime và native-image environment.

Nếu nhóm development thử bằng một JDK distribution trên macOS, đó chưa phải bằng chứng chứng nhận production trên một vendor khác ở Linux ARM64.

## 17. Framework requirements khác compatibility của bản phát hành ứng dụng

### 17.1. Minimum framework Java chỉ là một điều kiện

Một framework hỗ trợ Java 17 và 21, nhưng ứng dụng có thể vô tình:

- Compile module bằng `--release 21`.
- Dùng library mang class major 65.
- Dùng Java agent chưa hỗ trợ JVM target.
- Phụ thuộc vào internal JDK API bị hạn chế.
- Sử dụng native library không có binary cho architecture đích.
- Có code dùng Java API đã loại bỏ.
- Có serialization/certificate/TLS behavior thay đổi.

Kết quả là **framework compatible** nhưng **application incompatible**. Vì vậy, ma trận framework hỗ trợ quyết định khả năng lựa chọn mục tiêu, còn acceptance tests quyết định liệu ứng dụng của bạn đã sẵn sàng hay chưa.

### 17.2. Cùng framework/JDK vẫn có nhiều deployment configurations

Ví dụ:

| Runtime | Framework | Đóng gói | Rủi ro bổ sung |
|---|---|---|---|
| Java 21 | Alpha 4.x | Executable JAR | Embedded server, startup flags |
| Java 21 | Alpha 4.x | WAR | External server và Jakarta API |
| Java 21 | Alpha 4.x | Container | Base image, cert store, architecture |
| Java 21 | Alpha 4.x | Native binary | Native-image toolchain, reflection config |

Đây là bảng tình huống giả định. Việc một hàng vượt qua test không có nghĩa mọi hàng còn lại đều được hỗ trợ giống nhau.

## 18. Thiết kế ma trận kiểm chứng cho dự án

Một ma trận tốt có ít nhất hai lớp: **vendor support evidence** và **application validation results**.

### 18.1. Lớp 1: vendor support evidence

| ID | Thành phần | Version | JDK candidate | Claim | Bằng chứng | Trạng thái |
|---|---|---|---|---|---|---|
| F-01 | Framework core | Chính xác patch | 21 | Supported | Tài liệu đúng version | Verified |
| F-02 | Build plugin | Chính xác patch | 21 | Tested | Plugin docs | Verified |
| F-03 | Application server | Chính xác patch | 21 | Không tìm thấy | Chưa có nguồn | Not verified |
| F-04 | JDBC driver | Chính xác patch | 21 | Unsupported | Support matrix | Blocked |

Những trạng thái trong bảng chỉ minh họa cách ghi; không phải xác nhận của sản phẩm thực tế.

### 18.2. Lớp 2: test results

| ID | Kịch bản | Runtime | Kết quả | Bằng chứng |
|---|---|---|---|---|
| T-01 | Startup/healthcheck | Java 21 | Pass/Fail | CI log, test run |
| T-02 | API/serialization | Java 21 | Pass/Fail | Contract tests |
| T-03 | Database transaction | Java 21 | Pass/Fail | Integration tests |
| T-04 | Security/authentication | Java 21 | Pass/Fail | Security tests |
| T-05 | Load/performance | Java 21 | Pass/Fail | Benchmark |
| T-06 | Graceful shutdown | Java 21 | Pass/Fail | Runtime log |
| T-07 | Rollback compatibility | Java 17/21 | Pass/Fail | Release test |

Không gộp “vendor support confirmed” và “test passed” thành một ô Yes/No vì chúng trả lời hai câu hỏi khác nhau.

### 18.3. Trạng thái và mức chứng cứ

Một bộ nhãn đơn giản:

- **VERIFIED_SUPPORTED:** đã có nguồn chính thức đúng version/phạm vi.
- **VERIFIED_UNSUPPORTED:** nguồn chính thức xác nhận không được hỗ trợ.
- **NOT_VERIFIED:** chưa có bằng chứng đầy đủ.
- **CONDITIONAL:** chỉ hỗ trợ khi đáp ứng patch, OS, edition hoặc cấu hình cụ thể.
- **APPLICATION_TEST_PASS:** ứng dụng đã vượt test của tổ chức; là nhãn độc lập với vendor support.
- **BLOCKED:** có rào cản đã biết, cần xử lý trước rollout.

Giữ hai loại trạng thái riêng để tránh một test tự viết bị trình bày thành certification của vendor.

## 19. Bước-by-bước đọc ma trận framework cho một migration

### Bước 1: Ghi mục tiêu

Ví dụ:

```text
Workload               : order-service
Current Java runtime   : 17
Target Java runtime    : 21
Framework currently    : <exact current version>
Deployment model       : JAR in Linux container
Required OS/arch       : Linux x86_64, Linux aarch64
Support needed until   : <business support horizon>
```

Không chọn framework version mục tiêu trước khi biết yêu cầu runtime, vòng đời và platform.

### Bước 2: Đọc requirements của bản hiện tại

Kiểm tra xem framework đang dùng đã hỗ trợ JDK mục tiêu chưa. Nếu có, một đợt nâng chỉ JDK có thể khả thi và ít biến động hơn. Nếu không, cần khảo sát bản framework mới hơn.

Dù matrix ghi hỗ trợ, vẫn phải xem patch-specific known issues và các integration bắt buộc.

### Bước 3: Chọn những framework release lines ứng viên

Lập bảng:

```text
Candidate A: giữ framework hiện tại nếu được hỗ trợ
Candidate B: nâng minor/patch trong release line hiện tại
Candidate C: nâng major sang release line còn bảo trì dài hạn
```

So sánh support window, breaking changes, dependency BOM, cost migration và thời hạn duy trì. Không tự động chọn major mới nhất.

### Bước 4: Kiểm tra giao hỗ trợ của cả stack

Cho từng ứng viên, kiểm tra:

- Framework core và plugins.
- Spring Cloud/extension train nếu có.
- Application server/embedded server.
- ORM, driver, security, HTTP, messaging.
- Build tool và compiler toolchain.
- Test tools và Java agent.
- OS/architecture/native image.
- JDK distribution và patch level nếu vendor quy định.

### Bước 5: Đọc migration guide và phân loại thay đổi

Tách các nhóm:

- Source/API changes.
- Build tool/plugin changes.
- Dependency upgrades.
- Configuration defaults.
- Jakarta namespaces.
- JVM/module access/bytecode.
- Data/protocol migrations.
- Deployment and observability changes.

Những thay đổi độc lập có thể được tách thành từng PR để giảm rủi ro.

### Bước 6: Tạo baseline và golden tests

Trước khi sửa framework/JDK:

- Ghi resolved dependency graph.
- Ghi framework/BOM/plugin versions.
- Lưu bytecode target và artifact checksums.
- Lưu startup logs và JVM options.
- Chạy unit/integration tests trên runtime hiện tại.
- Chụp contract/serialization fixtures cho những dữ liệu quan trọng.
- Ghi metrics latency, memory, GC và connection pools.

### Bước 7: Nâng có kiểm soát

Có thể:

1. Nâng build tool/plugins nếu cần.
2. Nâng framework lên bản còn chạy được trên JDK hiện tại nếu có thể.
3. Cập nhật source/config/namespace.
4. Xác minh tính năng và dữ liệu.
5. Đổi JDK runtime sang target.
6. Chạy toàn bộ CI/validation matrix.
7. Canary và theo dõi production.

Nếu không có đường đi từng bước do yêu cầu Java của framework, cần một kế hoạch nâng đồng thời rõ ràng và môi trường staging đủ sát production.

### Bước 8: Lưu bằng chứng cuối cùng

Quyết định phải kèm exact versions, source links, ngày kiểm tra, resolved graph, CI logs và lý do chấp nhận rủi ro. Không để một câu “đã test Java 21 rồi” trở thành tài liệu duy nhất cho bản phát hành.

## 20. Ví dụ thực hành: chọn giữa giữ framework và nâng framework

Giả sử ứng dụng đang chạy:

```text
Framework Alpha 3.6
Java 17
Maven 3.x
Embedded Server S 9.x
Driver D 2.x
```

Mục tiêu là Java 21. Sau khi tra tài liệu, nhóm thu được thông tin **giả định**:

| Thành phần | Bản hiện tại với Java 21 | Bản ứng viên với Java 21 |
|---|---|---|
| Framework Alpha | Not verified | Supported ở Alpha 4.2 |
| Server S | Unsupported | Supported ở S 10.x |
| Driver D | Supported | Supported ở D 3.x |
| Maven/plugins | Plugin cũ chưa xác minh | Plugin mới được xác minh |
| Security module | Patch cũ EOL | Patch mới active |

Kết luận hợp lý không phải “Alpha 3.6 chắc chắn lỗi”, mà là **tổ hợp hiện tại chưa đủ điều kiện để được tuyên bố hỗ trợ**. Một ứng viên hợp lý là nâng framework/server/plugins theo documented migration path rồi thử Java 21.

### 20.1. Kế hoạch triển khai giả định

```text
Release 1:
  Update Maven/plugins
  Fix dependency conflicts
  Keep Java 17

Release 2:
  Upgrade Framework Alpha + Server S
  Adapt configuration/source
  Keep Java 17 if supported by new stack

Release 3:
  Switch production to Java 21
  Run compatibility and performance tests

Release 4:
  Remove temporary compatibility flags
  Close legacy support issues
```

Nếu framework mới chỉ hỗ trợ Java 21, Release 2 và Release 3 có thể phải gộp. Support matrix giúp chỉ ra **đường đi khả thi**, còn quản lý release quyết định mức chấp nhận rủi ro.

### 20.2. Kịch bản rollback

Nếu phiên bản mới đã thay đổi database schema hoặc message format, rollback JAR/framework về phiên bản trước có thể không đọc được dữ liệu mới. Vì vậy:

- Kiểm tra backward/forward schema compatibility.
- Dùng expand-then-contract nếu có thể.
- Giữ migration scripts và database backups theo chính sách.
- Chỉ bật producer gửi giá trị mới khi consumers đã sẵn sàng.
- Ghi rõ version pairing cho từng release.

Ma trận framework hỗ trợ Java không bao quát tự động compatibility dữ liệu nghiệp vụ; đây là một rủi ro riêng.

## 21. Ma trận JDK kiểm thử trong CI

### 21.1. Tách compile và test JVM

Ví dụ ứng dụng muốn hỗ trợ cả Java 17 và 21:

```text
Compile:
  JDK 21 compiler
  --release 17

Test:
  Java 17 runtime
  Java 21 runtime

Package:
  JAR with compatible bytecode
  dependencies verified for minimum Java 17
```

Nếu framework bản mục tiêu yêu cầu Java 21, ma trận trên không còn phù hợp cho framework application. Khi đó cần nâng minimum runtime hoặc giữ một branch/artifact riêng cho consumer Java 17.

### 21.2. Test startup chỉ là cửa đầu

Một matrix hợp lý gồm:

| Nhóm test | Tại sao quan trọng khi nâng JDK/framework? |
|---|---|
| Startup và healthcheck | Phát hiện lỗi classloading/config sớm |
| HTTP contract | Endpoint, validation, JSON behavior |
| Database/JPA | Query dialect, lazy loading, transactions |
| Security/TLS | Authentication, certificate, crypto defaults |
| Messaging | Serialization, converters, retries, schema |
| Scheduling/async | Executor behavior, shutdown, context propagation |
| Reflection/proxy | Module encapsulation, instrumentation |
| Native/JNI | OS/architecture/ABI |
| Performance | Memory, latency, GC, thread usage |
| Packaging/deployment | WAR/JAR/container/native image |
| Rollback | Dữ liệu và protocol giữa phiên bản cũ/mới |

Bộ test phải đi qua các integrations có thật trong sản phẩm; không nên chỉ copy một “framework demo” rồi coi là đã kiểm chứng cả workload.

### 21.3. Thử đúng artifact cuối cùng

Nếu build sinh fat JAR, Docker image hoặc native binary, phải thử đúng artifact đó. Một Maven/Gradle `test` thành công trên classpath của IDE có thể khác dependency và runtime layout khi đóng gói production.

Nên ghi:

- SHA-256/digest của artifact.
- Framework/BOM resolved versions.
- Runtime Java version và vendor.
- Container image digest nếu áp dụng.
- Test report theo OS/architecture.
- Known deviations và waivers.

## 22. Các khác biệt về Java runtime thường lộ khi nâng framework

### 22.1. Reflection và strong encapsulation

Các framework và thư viện bytecode cũ có thể truy cập sâu vào JDK internals. Khi nâng JDK, reflective access có thể bị chặn theo JPMS/strong encapsulation.

Triệu chứng:

```text
java.lang.reflect.InaccessibleObjectException
```

Thay vì thêm hàng loạt `--add-opens` rồi tuyên bố hỗ trợ, hãy kiểm tra bản framework/agent mới có hỗ trợ JDK mục tiêu không. Dùng flags mở package chỉ là biện pháp có cân nhắc, phạm vi tối thiểu và kế hoạch loại bỏ.

### 22.2. Dependency bị loại khỏi JDK

Một số APIs từng nằm trong JDK cũ không còn được cung cấp theo cách trước đây. Mã hoặc framework cũ có thể cần dependency thay thế. Khi đọc migration guide, hãy phân biệt **JDK removal** với **framework breaking change** để sửa đúng lớp.

### 22.3. Bytecode libraries và proxies

ORM, AOP, mocking, serialization và framework internals có thể sử dụng ASM/Byte Buddy hoặc những thư viện xử lý class file. Với JDK mới, chúng cần hiểu major class-file version tương ứng.

Một framework release note ghi “Java 21 support” có thể chỉ trở nên đúng từ patch release đã nâng bytecode library. Đó là lý do phải xác định exact patch version, không chỉ major line.

### 22.4. TLS, cryptography và certificates

JDK hoặc framework mới có thể thay đổi các thuật toán và protocols được bật mặc định. Các hệ thống kết nối server cũ đôi khi chỉ lỗi khi mở TLS connection, kết nối LDAP hoặc gọi external APIs.

Đọc JDK security release notes và kiểm tra end-to-end trên môi trường đích; support matrix core framework không tự bảo đảm sự tương thích với các endpoint bên ngoài.

### 22.5. Observability và production agents

Các Java agents dành cho APM, profiling, tracing và coverage có thể can thiệp bytecode hoặc sử dụng JVM instrumentation. Chúng có support matrix riêng. Một service có thể chạy tốt khi không gắn agent nhưng lỗi khi deploy với `-javaagent`.

Do đó, trong staging phải bật các agents và JVM flags giống production, hoặc ghi rõ những khác biệt cần kiểm chứng.

## 23. Cách phát hiện tài liệu dễ gây hiểu lầm

### 23.1. Một câu chung không kèm version

```text
"Our framework works with modern Java."
```

Không đủ. Cần exact version, JDK release, điều kiện và thời điểm.

### 23.2. Thông tin “latest” áp vào bản đang dùng

```text
Framework latest supports Java 25
Ứng dụng đang ở framework 3.x
```

Chưa có kết luận. Phải đọc tài liệu branch 3.x hoặc một upgrade path thích hợp.

### 23.3. Chỉ có “minimum Java 17”

Điều này không bảo đảm Java 21/25 đã được thử. Cần bảng supported/tested JDKs hoặc xác nhận vendor.

### 23.4. Một issue cá nhân nói “works for me”

Hữu ích như tín hiệu để thử, nhưng không phải cam kết support. Ngoài ra có thể không cùng OS, JDK vendor, dependency graph hoặc feature usage.

### 23.5. Một build thành công trên Java mới

Biên dịch không kiểm tra đầy đủ native runtime, dynamic class loading, database dialect, TLS, serialization và rollout compatibility. Phải có test matrix thực tế.

### 23.6. Dựa vào một BOM nhưng override nhiều modules

Nếu ứng dụng đã override một lượng lớn dependencies khỏi BOM, phạm vi support chính thức có thể thay đổi. Nên ghi rõ overrides và chạy tests đặc thù.

### 23.7. Nhầm minimum JDK của plugin với minimum JDK của artifact

Plugin build có thể đòi Java 21 trong khi artifact target Java 17, hoặc ngược lại. Cần xem tài liệu riêng cho builder và runtime.

### 23.8. Nhầm “support ends on date X” với “binary ngừng chạy ngày X”

EOL nói về cam kết maintenance/support, không có nghĩa JVM sẽ cố tình ngừng chạy binary vào ngày đó. Tuy nhiên, EOL là rủi ro bảo mật/vận hành lớn và phải ảnh hưởng quyết định migration.

## 24. Các câu hỏi cần gửi vendor hoặc framework maintainer

Nếu tài liệu chưa rõ, nên hỏi cụ thể thay vì hỏi chung “có hỗ trợ Java mới không?”:

1. Framework release **X.Y.Z** được hỗ trợ chính thức trên **JDK release và vendor** nào?
2. Hỗ trợ có bao gồm **OS/architecture** đang chạy production không?
3. Bản patch tối thiểu nào thêm support cho JDK mục tiêu?
4. Support có áp dụng cho **build plugin**, annotation processors và CLI không?
5. Framework có chạy được trên runtime mục tiêu khi đóng gói WAR trong **server version A** không?
6. Các module ORM, security, messaging và native-image extensions có cùng certification không?
7. Có known issues liên quan JDK mục tiêu không, và workaround/bản vá tương ứng là gì?
8. Release line còn nhận security fixes đến khi nào?
9. Có migration guide từ version đang chạy sang candidate version không?
10. Có những configuration/JVM flags bị loại khỏi phạm vi hỗ trợ không?

Ghi lại phản hồi và ngày xác nhận cùng hồ sơ migration. Với hợp đồng thương mại, làm rõ trường hợp nào được vendor support escalation.

## 25. Troubleshooting khi ma trận và thực tế không khớp

### 25.1. Framework nói hỗ trợ Java 21, nhưng app lỗi `UnsupportedClassVersionError`

**Nguyên nhân khả dĩ:** một module hoặc dependency đã target Java cao hơn production runtime, hoặc runtime thực tế không phải Java 21 như cấu hình dự kiến.

**Kiểm tra:** `java -version` ở môi trường thật, major class file trong JAR và nested dependencies, Docker image/runtime startup.

**Cách xử lý:** chọn dependency/artifact phù hợp hoặc nâng runtime đúng theo policy; không xem support framework như bằng chứng mọi JAR trong app có cùng class major.

### 25.2. Build tool không chạy trên JDK mới

**Nguyên nhân:** Gradle/Maven/plugin version cũ có yêu cầu runtime khác.

**Kiểm tra:** build tool support matrix và `./gradlew --version`/`./mvnw -version`.

**Cách xử lý:** nâng wrapper/plugin theo phiên bản được hỗ trợ, kiểm soát toolchains và chạy lại build trong CI.

### 25.3. Build thành công nhưng ORM lỗi trong integration test

**Nguyên nhân:** ORM version/dialect hoặc JDBC driver không tương thích với framework/server/database, hoặc thay đổi Jakarta API.

**Kiểm tra:** resolved dependency tree, ORM/JPA release notes, database dialect và server support matrix.

**Cách xử lý:** chọn tổ hợp được quản lý bởi BOM hoặc một override đã được chứng minh qua integration test.

### 25.4. Framework mới yêu cầu `jakarta.*` nhưng app còn `javax.*`

**Nguyên nhân:** migration Java EE/Jakarta EE chưa hoàn chỉnh, không đơn thuần là JDK mismatch.

**Kiểm tra:** imports, WAR dependencies, container-provided APIs, transitive libraries và migration guide.

**Cách xử lý:** chuyển namespaces/implementations theo release line và chạy contract/integration tests.

### 25.5. Dùng JDK mới chỉ lỗi khi bật APM agent

**Nguyên nhân:** agent/bytecode transformer không hỗ trợ class-file version hoặc JVM internals của JDK đích.

**Kiểm tra:** agent compatibility matrix và version thực tế trong deployment.

**Cách xử lý:** nâng agent, thử với cấu hình observability giống production.

### 25.6. Java 21 chạy được trên máy dev nhưng lỗi trong container ARM64

**Nguyên nhân:** khác OS/CPU, native libraries, libc, JDK distribution hoặc architecture-specific dependency.

**Kiểm tra:** image digest, architecture, framework/native extension matrix.

**Cách xử lý:** chọn base image và native artifacts có hỗ trợ đúng target; chạy thử trên architecture tương ứng.

### 25.7. Tài liệu framework hiện “supported”, nhưng security scan báo EOL

**Nguyên nhân:** support có thể chỉ còn ở một edition khác, trang hướng dẫn cũ, hoặc release line đã qua maintenance window.

**Kiểm tra:** lifecycle policy mới nhất của đúng release line và support contract.

**Cách xử lý:** chọn patch/branch còn bảo trì hoặc có exception/mitigation được phê duyệt rõ ràng.

### 25.8. Không tìm thấy JDK mục tiêu trong matrix

**Nguyên nhân:** chưa được xác minh hoặc không nằm trong phạm vi tài liệu.

**Kiểm tra:** patch release notes, official issue tracker, vendor confirmation.

**Cách xử lý:** đánh dấu `NOT_VERIFIED`, không tự tuyên bố supported; cân nhắc nâng framework hoặc đổi target JDK nếu dự án bắt buộc có support chính thức.

## 26. Checklist đọc support matrix

### Phạm vi tài liệu

- [ ] Đã xác định exact framework version và release line.
- [ ] Đang đọc tài liệu đúng version, không nhầm trang latest.
- [ ] Có link nguồn chính thức và ngày kiểm tra.
- [ ] Phân biệt minimum, tested, certified, supported và EOL.
- [ ] Đã kiểm tra patch release tối thiểu bổ sung hỗ trợ JDK.
- [ ] Đã đọc migration guide và known issues của đường nâng.

### Java và môi trường

- [ ] Đã tách build JDK, compiler toolchain, target bytecode và runtime JDK.
- [ ] Đã ghi vendor, update level, OS và architecture.
- [ ] Đã xác minh compiler/build tool có hỗ trợ JDK đích.
- [ ] Đã đối chiếu class-file major và minimum Java của dependencies.
- [ ] Đã xác nhận native-image requirements nếu áp dụng.
- [ ] Đã rà soát JVM flags, agents, security/TLS và module access.

### Framework và hệ sinh thái

- [ ] Framework core nằm trong release line còn phù hợp.
- [ ] Build plugin, BOM và release train được căn chỉnh.
- [ ] Application server/embedded server có support phù hợp.
- [ ] ORM, security, HTTP, messaging và JDBC drivers được xác minh.
- [ ] Jakarta/Servlet specification level đúng với framework/server.
- [ ] Extensions và native libraries có matrix riêng nếu cần.
- [ ] Không có override dependency quan trọng chưa được kiểm thử.

### Quyết định migration

- [ ] Có bảng candidate combinations và trạng thái chứng cứ.
- [ ] Đã xác định tổ hợp được hỗ trợ trong suốt support horizon của sản phẩm.
- [ ] Đã phân loại blockers và những mục chưa xác minh.
- [ ] Có test matrix theo JDK/OS/architecture thực tế.
- [ ] Đã lưu resolved dependency graph và artifact checksum.
- [ ] Có canary, monitoring và rollback plan.
- [ ] Bản release không được phê duyệt chỉ vì “build thành công”.

## 27. Bài tập tình huống

### Bài tập 1: Diễn giải câu “Java 17 or later”

Tài liệu giả định:

```text
Framework Beta 3.5 requires Java 17 or later.
CI officially tests Java 17 and Java 21.
Support for Java 25 is under investigation.
```

Hãy trả lời:

1. Minimum Java có thể xác nhận là bản nào?
2. Java 21 có bằng chứng nào?
3. Có thể đánh dấu Java 25 là officially supported không?
4. Nếu sản phẩm bắt buộc có vendor support, cần tra tiếp thông tin gì?
5. Nếu một plugin build yêu cầu Java 21, có mâu thuẫn gì khi runtime vẫn Java 17 không?

### Bài tập 2: Chọn framework cho ứng dụng nhiều thành phần

Một ứng dụng sử dụng:

```text
Framework: F 2.x
Application server: S 8.x
JDBC driver: D 1.x
Gradle: G old release
Runtime: Java 17
Target: Java 21
```

Sau khi tra đúng docs, bạn phát hiện F 2.x chưa được xác minh với Java 21, S 8.x không hỗ trợ Java 21, nhưng D 1.x có hỗ trợ.

Hãy lập bảng quyết định gồm: supported / unsupported / not verified, evidence source, candidate version và test/upgrade action. Nêu rõ vì sao không thể coi “driver hỗ trợ Java 21” là kết luận cho cả ứng dụng.

### Bài tập 3: Framework và BOM mismatch

Một framework release line đã được vendor kiểm thử với một tập thư viện trong BOM, nhưng ứng dụng override ORM và JSON lên hai bản mới hơn. Hãy trình bày:

- Điều gì vẫn có thể suy ra từ framework support matrix?
- Những điểm nào nằm ngoài tập phiên bản đã được kiểm thử?
- Cần thu thập dependency graph nào?
- Những integration tests nào cần ưu tiên?
- Khi nào nên chờ BOM mới hoặc nâng framework line?

### Bài tập 4: Build JDK và runtime khác nhau

Ứng dụng build bằng JDK 21, cấu hình `javac --release 17`, chạy trên Java 17. Plugin Gradle lại yêu cầu Gradle mới chạy trên JDK 21.

Hãy vẽ ma trận tách:

```text
Gradle daemon JDK
Compiler toolchain
Source/bytecode/API target
Test runtime JDK
Production runtime JDK
Framework minimum runtime
```

Xác định điều kiện nào phải được xác minh trong tài liệu của Gradle, plugin và framework.

### Bài tập 5: Quyết định nâng theo giai đoạn

Một framework mới đòi Java 21, còn framework cũ chạy Java 17 và đã EOL. Dịch vụ đang chịu ràng buộc thời gian bảo trì ngắn.

Hãy đề xuất cách giảm rủi ro khi buộc phải nâng framework và JDK gần như đồng thời: staging environment, golden data, dependency graph, feature flags, canary, rollback và support confirmation.

## Kết luận

Đọc yêu cầu Java và ma trận hỗ trợ của framework là một **hoạt động thu thập và đối chiếu bằng chứng**, không phải tìm một dòng version duy nhất. “Minimum Java”, “tested”, “certified”, “supported” và “end of support” có ý nghĩa khác nhau; tài liệu của framework core cũng không thay thế ma trận của build plugin, application server, driver, native-image toolchain và các extensions.

Trong Java Advance Compatibility Migration, hãy bắt đầu bằng việc xác định exact versions và workload, đọc tài liệu đúng release line, kiểm tra vòng đời hỗ trợ và những patch-specific known issues, sau đó tìm **giao của các tổ hợp được hỗ trợ** trong toàn bộ stack. Dùng Maven/Gradle để xác minh resolved versions, kiểm tra bytecode/runtime constraints và chạy integration tests trên JDK, OS và artifact thực tế. Chỉ khi cả **support evidence** và **application validation** đều đạt yêu cầu, nhóm mới có cơ sở vững chắc để tuyên bố tổ hợp framework–JDK sẵn sàng cho production.

