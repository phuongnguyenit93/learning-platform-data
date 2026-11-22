# Tách tài nguyên theo mục đích sử dụng và kiểm chứng đầu ra trong Maven

## 1. Vấn đề: file nằm trong repository không đồng nghĩa sẽ nằm đúng chỗ khi chạy

Trong Java, **resource** là dữ liệu đi kèm chương trình nhưng không phải mã nguồn `.java`: file `.properties`, `.yaml`, `.json`, văn bản, SQL migration, template, ảnh, chứng chỉ công khai, mô hình dữ liệu hoặc fixture dành cho test. Một số resource là **đầu vào của quy trình sinh mã**, một số được **sinh ra trong build**, và một số cần **được đóng gói trong JAR** để chương trình đọc ở runtime.

Nếu mọi thứ được đặt chung một chỗ rồi bật filtering cho toàn bộ, nhiều lỗi dễ xảy ra:

- Fixture chứa dữ liệu kiểm thử vô tình bị đưa vào JAR sản phẩm.
- Một file nhị phân bị coi là văn bản để thay placeholder, làm hỏng byte.
- File cấu hình cần thay `@project.version@` vẫn giữ nguyên vì chưa bật filtering.
- Biến `${...}` của framework bị Maven thay ngoài ý muốn.
- File generated xuất hiện quá muộn, sau khi Maven đã copy resources.
- Unit test pass do test classpath có file mà JAR phát hành không hề chứa.
- Đường dẫn dùng filesystem như `src/main/resources/...` chạy được trong IDE nhưng không hoạt động sau khi đóng gói JAR.
- Cấu hình chứa secret bị nhúng vào artifact và phát tán ngoài môi trường được phép.

**Mục tiêu:** phân biệt **main resources**, **test resources**, **generated resources**, **source code** và **tài sản nhị phân**; cấu hình sao chép/filtering đúng mục đích; quan sát đường đi từ source tới output; rồi kiểm chứng bằng Maven lifecycle, test classpath, JAR và JVM runtime thực tế.

## 2. Bản đồ đường đi của các loại tài nguyên

Với một Maven project Java dùng packaging `jar` thông thường:

```text
src/main/java/*.java
        │ compiler:compile
        ▼
target/classes/*.class ───────────────────────────────────┐
                                                         │
src/main/resources/**                                    │
        │ resources:resources (process-resources)        │
        ▼                                                │
target/classes/** ───────────────────────────────────────┤
                                                         │ jar:jar (package)
generated resources (nếu đã đăng ký vào project.resources)│
        │ resources:resources                            │
        ▼                                                │
target/classes/** ───────────────────────────────────────┘
                                                         ▼
                                              target/<artifact>.jar

src/test/java/*.java
        │ compiler:testCompile
        ▼
target/test-classes/*.class ──────┐
                                  │ Surefire test classpath
src/test/resources/**             │
        │ resources:testResources │
        ▼                         │
target/test-classes/** ───────────┘

Test classpath thường còn nhìn thấy target/classes và các dependency test.
Nhưng target/test-classes KHÔNG được đóng gói vào main JAR mặc định.
```

Đây là **sơ đồ logic**, không phải log Maven nguyên văn. Hướng di chuyển quan trọng là:

- `src/main/resources` → `target/classes` → JAR chính (với cấu hình jar mặc định).
- `src/test/resources` → `target/test-classes` → classpath lúc chạy test, **không** vào JAR chính.
- `target/generated-resources/...` → `target/classes` **chỉ nếu** generator đã tạo file và Maven đã được chỉ dẫn copy thư mục đó.
- `src/main/java` và `src/test/java` được Compiler Plugin biên dịch, **không** phải Resources Plugin copy như Java source để dùng runtime.

### 2.1. Quy ước thư mục nên hiểu đúng

| Loại dữ liệu | Nơi đặt đầu vào phổ biến | Output kỳ vọng | Có trong JAR chính? |
| --- | --- | --- | --- |
| Cấu hình mặc định sản phẩm | `src/main/resources/config/app.properties` | `target/classes/config/app.properties` | Có |
| Message template/resource text của sản phẩm | `src/main/resources/messages/welcome.txt` | `target/classes/messages/welcome.txt` | Có |
| Image, font hoặc tài sản binary | `src/main/resources/assets/logo.png` | `target/classes/assets/logo.png` | Có nếu đã khai báo copy |
| Fixture riêng cho test | `src/test/resources/fixtures/input.txt` | `target/test-classes/fixtures/input.txt` | **Không**, mặc định |
| Config riêng dành cho test | `src/test/resources/test-config/...` | `target/test-classes/test-config/...` | **Không**, mặc định |
| Resource do generator tạo | `target/generated-resources/demo/generated/build.txt` | `target/classes/generated/build.txt` | Có nếu root được đăng ký/copy |
| Java source được sinh | `target/generated-sources/.../*.java` | Class tại `target/classes` sau compile | Class có thể vào JAR, không copy Java source theo mặc định |
| File cần ở ngoài artifact để vận hành | thư mục cấu hình của môi trường/deployment | file external do launcher/container cấp | Không nhất thiết; thường **không** nên nhúng |

**Resource path được giữ tương đối theo directory root.** Ví dụ root là `src/main/resources`, file `config/app.properties` sẽ có path `config/app.properties` trong `target/classes` và JAR. Đặt directory root nhầm thành `src/main/resources/config` sẽ khiến file được copy thành `app.properties` ở gốc output, dẫn đến ứng dụng tìm `/config/app.properties` thất bại.

## 3. Main resource và test resource phục vụ hai vòng đời khác nhau

Maven dùng hai vùng cấu hình trong POM:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
        </resource>
    </resources>
    <testResources>
        <testResource>
            <directory>src/test/resources</directory>
        </testResource>
    </testResources>
</build>
```

Đây là **đoạn POM**, không phải file hoàn chỉnh. Với layout tiêu chuẩn, Maven đã có giá trị mặc định cho các thư mục này; chỉ cần khai báo tường minh khi muốn đổi chính sách, filtering, include/exclude hoặc thêm đường dẫn.

- **`resources:resources`** thuộc Maven Resources Plugin, được default lifecycle gọi ở `process-resources`, sử dụng **`project.build.resources`**, mặc định ghi vào **`${project.build.outputDirectory}`**, thường là `target/classes`.
- **`resources:testResources`** được default lifecycle gọi ở `process-test-resources`, sử dụng **`project.build.testResources`**, mặc định ghi vào **`${project.build.testOutputDirectory}`**, thường là `target/test-classes`.

**Tách hai loại trong POM khác với việc đặt hai folder có tên khác nhau.** Một test resource chỉ thực sự test-only khi Maven không được cấu hình để copy nó vào output main, và ngược lại.

### 3.1. Lý do không đưa fixture vào main resources

Một file chứa account giả, tập hợp request/response test, dữ liệu lỗi hoặc dump phục vụ kiểm thử không nên đi cùng production artifact nếu không thật sự cần. Nếu fixture nằm ở `src/main/resources`, JAR Plugin mặc định có thể đóng gói nó cùng sản phẩm. Việc file là “chỉ để test” trong ý định của lập trình viên **không khiến Maven tự loại nó**.

Với fixture, đặt vào `src/test/resources` và truy cập bằng test classpath là thiết kế an toàn hơn. Sau build, cần kiểm tra **JAR thật** chứ không chỉ nhìn thư mục source trong repository.

### 3.2. Test resource có thể che main resource cùng tên

Trong test JVM, classpath thường có cả `target/test-classes` và `target/classes`. Nếu cùng một path, chẳng hạn `config/app.properties`, có trong **cả hai output**, class loader có thể trả về bản test thay vì bản sản phẩm tùy thứ tự classpath của runner.

Điều này đôi khi được dùng có chủ đích để override cấu hình khi test, nhưng là rủi ro khi test pass nhờ config khác production. Nên đặt resource test riêng dưới `fixtures/` hoặc `test-config/`, hoặc ghi rõ cơ chế override rồi kiểm tra cả classpath phát hành.

## 4. Filtering: thay placeholder trong text nhưng giữ nguyên những file khác

**Filtering** là việc Maven Resources Plugin đọc resource như văn bản và thay biểu thức cấu hình bằng giá trị có trong project/filtering context. Nó hữu ích cho những thông tin có chủ đích đưa vào artifact, như artifact name, version, channel không nhạy cảm hoặc một URL công khai theo môi trường.

Ví dụ file `src/main/resources/config/app.properties`:

```properties
app.name=@demo.displayName@
app.version=@project.version@
app.environment=@demo.environment@
```

Nếu bật filtering cho chính file này, có delimiter `@...@` và POM định nghĩa các property tương ứng, output sau xử lý có thể là:

```properties
app.name=Resource Lab
app.version=1.0.0
app.environment=local
```

Để tránh làm biến runtime của framework biến mất ngoài ý muốn, có thể cấu hình Resource Plugin **chỉ dùng delimiter `@`**, không bật thêm delimiter mặc định `${...}`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <encoding>UTF-8</encoding>
        <propertiesEncoding>UTF-8</propertiesEncoding>
        <delimiters>
            <delimiter>@</delimiter>
        </delimiters>
        <useDefaultDelimiters>false</useDefaultDelimiters>
    </configuration>
</plugin>
```

**Đây là cấu hình plugin**, nó không tự bật filtering cho mọi resource. Mỗi `<resource>` hoặc `<testResource>` có thuộc tính `<filtering>true/false</filtering>` tương ứng.

### 4.1. Chỉ filter file thực sự cần thay giá trị

Ví dụ main resources có hai nhóm:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>true</filtering>
        <includes>
            <include>config/app.properties</include>
        </includes>
    </resource>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>false</filtering>
        <excludes>
            <exclude>config/app.properties</exclude>
        </excludes>
    </resource>
</resources>
```

Nhóm đầu chỉ lấy `config/app.properties` để thay placeholder. Nhóm sau lấy **các file còn lại** nhưng không filtering. Hai tập này cố tình không trùng nhau, để tránh hiện tượng một file được copy hai lần với chính sách khác nhau hoặc lần copy sau ghi đè output lần trước.

Một file `messages/welcome.txt` chứa ký tự `@demo.displayName@` trong nhóm thứ hai sẽ **giữ nguyên dấu placeholder**. Đó là kết quả đúng nếu file này là template dành cho runtime hoặc đơn giản là thông điệp cần giữ nguyên văn.

### 4.2. Vì sao không filtering nhị phân?

Filtering phải giải mã byte thành ký tự và mã hóa lại sau khi thay thế. Nếu áp dụng bừa lên PNG, ZIP, PDF, font, protobuf binary hoặc file khác không phải text, byte có thể bị sửa hoặc file hỏng. Thực hành an toàn:

- Tách text cần filtering vào một `<resource filtering=true>` có includes rõ ràng.
- Copy các file khác với `filtering=false`.
- Nếu vẫn phải filter trên một nhóm rộng, dùng `nonFilteredFileExtensions` để bảo vệ thêm những đuôi binary đã biết, nhưng đừng xem extension filter là biện pháp thay thế việc phân loại tài nguyên.
- Khi bảo toàn binary có ý nghĩa, so **checksum trước và sau copy**, không kiểm tra “file tồn tại” là đủ.

Maven Resources Plugin 3.3.1 mặc định không filter một số extension ảnh như `jpg`, `jpeg`, `gif`, `bmp`, `png` ngay cả trong tình huống resource filtering. Có thể bổ sung extension khác ở cấu hình plugin, ví dụ:

```xml
<configuration>
    <nonFilteredFileExtensions>
        <nonFilteredFileExtension>zip</nonFilteredFileExtension>
        <nonFilteredFileExtension>pdf</nonFilteredFileExtension>
        <nonFilteredFileExtension>woff2</nonFilteredFileExtension>
    </nonFilteredFileExtensions>
</configuration>
```

Đây là **đoạn bổ sung**, không phải file độc lập. Trong demo bên dưới, chúng ta chọn cách đơn giản và rõ nhất: **tách nhóm filtered và unfiltered ngay trong `<resources>`**.

### 4.3. Encoding: đừng vô tình đổi ký tự tiếng Việt

Với text UTF-8, POM nên khai báo:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Resources Plugin hỗ trợ parameter `encoding` cho văn bản được lọc và `propertiesEncoding` (từ bản plugin hỗ trợ) cho file `.properties`. Nếu file đầu vào đã dùng UTF-8 mà plugin hoặc code lại giải mã theo encoding khác, output có thể lỗi dấu tiếng Việt.

Java `java.util.Properties.load(InputStream)` truyền thống dùng cách đọc theo ISO-8859-1. Nếu resource `.properties` thực sự được lưu UTF-8, có thể đọc qua `InputStreamReader(..., UTF_8)`; ví dụ thực hành sẽ làm như vậy.

### 4.4. Giữ token cho Spring hoặc template engine

Một file Spring có thể chứa `${DB_HOST}` hoặc `${application.port}` để framework xử lý tại runtime. Nếu bật Maven filtering với các delimiter mặc định bao gồm `${...}`, Maven có thể chạm vào các token này hoặc gây xung đột với cú pháp của ứng dụng.

Chọn delimiter chỉ phục vụ Maven, ví dụ `@project.version@`, và `useDefaultDelimiters=false` nếu phù hợp. Quan trọng hơn, **không filter những file hoàn toàn thuộc trách nhiệm cấu hình runtime**. Không nên dựa vào việc “property hiện chưa định nghĩa nên token tình cờ giữ nguyên” như một hợp đồng ổn định.

## 5. Includes, excludes và targetPath: kiểm soát đúng file được copy

Các phần trong một resource declaration:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `directory` | Gốc filesystem lấy file | `src/main/resources` |
| `includes` | Những path/file được phép lấy, tương đối với directory | `config/*.properties` |
| `excludes` | Những path/file cần loại ra, tương đối với directory | `secrets/**` |
| `filtering` | Có thực hiện interpolation hay không | `true` hoặc `false` |
| `targetPath` | Thư mục tương đối bên dưới output mà file được đặt | `META-INF`, khi thật sự muốn đổi layout |

Ví dụ cấu hình khái niệm:

```xml
<resource>
    <directory>src/main/resources</directory>
    <filtering>false</filtering>
    <includes>
        <include>public/**</include>
    </includes>
    <excludes>
        <exclude>public/private/**</exclude>
    </excludes>
    <targetPath>assets</targetPath>
</resource>
```

Nó có ý định copy những file dưới `src/main/resources/public/...`, ngoại trừ `public/private/...`, tới đường dẫn dưới `target/classes/assets/...`. Đường dẫn tương đối từ root và cách `targetPath` ghép path là điều cần kiểm chứng trên artifact cụ thể: không suy đoán classpath resource sau khi đổi targetPath.

**Quy tắc:** chỉnh includes/excludes/targetPath là chỉnh **đường đi đầu ra**, có thể phá code đang gọi `getResourceAsStream("/...")`. Mỗi lần đổi cần kiểm tra path dưới `target/classes` và JAR bằng công cụ thật.

### 5.1. Không nên dùng resources filter để “xóa secrets”

Nếu repository vô tình chứa file `src/main/resources/secrets/passwords.properties`, chỉ đặt một exclude trong POM không thể thay thế chính sách bảo mật nguồn dữ liệu; bản thân file đã có thể bị commit và lộ. Nên ngăn secrets từ đầu bằng secret manager, phân quyền và cơ chế cấp cấu hình/runtime thích hợp.

Nếu build đã tạo artifact chứa secrets, cần xử lý theo quy trình sự cố và thay thế credential, không chỉ xóa file khỏi phiên bản artifact mới.

## 6. Lifecycle: resource được copy ở phase nào?

Maven default lifecycle có các phase liên quan:

```text
validate
initialize
generate-sources
process-sources
generate-resources
process-resources           → resources:resources cho main
compile                     → compiler:compile
generate-test-sources
process-test-sources
generate-test-resources
process-test-resources      → resources:testResources cho test
test-compile                → compiler:testCompile
test                        → surefire:test
package                     → jar:jar
verify
```

Thứ tự được rút gọn để tập trung vào resource; Maven còn nhiều phase khác, và những goal thực tế phụ thuộc packaging, plugin executions và cấu hình.

Một số hệ quả:

- `mvn process-resources` thực hiện các phase trước nó, bao gồm generated resource được bind vào `initialize` hoặc `generate-resources`.
- `mvn test` sẽ đi qua resource copy, compiler, test resource copy, test compile và test goal, nếu các binding tương ứng có trong project.
- `mvn package` đặt main resources và class đã biên dịch vào JAR thường khi plugin/lifecycle phù hợp.
- `mvn compiler:compile` là **gọi goal trực tiếp**, không tự chạy toàn bộ phase trước đó; dễ thiếu resource được sinh trong lifecycle.
- `mvn resources:resources` chạy một goal copy resource tại ngữ cảnh hiện tại; không có nghĩa generator ở `generate-resources` đã chạy trước.
- `mvn -B clean verify` là phép thử tái lập tốt hơn khi cần loại bỏ output cũ.

**Đừng nhầm** `generate-resources` với `process-resources`: một goal sinh resource có thể chạy ở phase trước; goal copy chỉ thấy những file/root đã tồn tại và đã được đăng ký trước khi nó thực thi.

## 7. Generated resources: sinh file rồi đăng ký root trước khi copy

Các tài nguyên do build tạo có thể là manifest dữ liệu, build metadata, schema đã chuyển đổi, file descriptor hoặc resource từ một generator nội bộ. Vì chúng **không nằm sẵn trong `src/main/resources`**, Maven cần biết nơi copy.

Một pipeline an toàn về thứ tự:

```text
initialize
  └─ generator tạo target/generated-resources/demo/generated/build.txt
generate-resources
  └─ build-helper:add-resource đăng ký target/generated-resources/demo
process-resources
  └─ resources:resources copy vào target/classes/generated/build.txt
package
  └─ jar:jar đưa generated/build.txt vào JAR sản phẩm
```

Ví dụ này cố ý để **generator và add-resource ở các phase khác nhau**, tránh việc phải dựa vào thứ tự nhiều execution nằm cùng một phase. Trong dự án thật, generator có thể chạy ở `generate-resources` và **tự đăng ký** root mà không cần Build Helper; tùy tài liệu của plugin.

### 7.1. Vì sao dùng Build Helper?

Goal `org.codehaus.mojo:build-helper-maven-plugin:add-resource` bổ sung danh sách resource directory cho Maven project. Sau khi đăng ký, Maven Resources Plugin có thể copy theo cấu hình thực tế.

Ví dụ **đoạn POM**:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>3.6.0</version>
    <executions>
        <execution>
            <id>register-generated-assets</id>
            <phase>generate-resources</phase>
            <goals>
                <goal>add-resource</goal>
            </goals>
            <configuration>
                <resources>
                    <resource>
                        <directory>${project.build.directory}/generated-resources/demo</directory>
                        <filtering>false</filtering>
                    </resource>
                </resources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

**Đây là đoạn cấu hình plugin**, không tự sinh file. Tài liệu Build Helper ghi default phase của `add-resource` là `generate-resources`. Trong ví dụ chạy được ở phần 9, generator đã tạo file ở `initialize` nên lúc registration chạy, thư mục đã tồn tại.

**Không nhầm `add-resource` với `add-source`.** Resource Plugin copy những file cần được cấp cho runtime; Compiler Plugin biên dịch Java source. Nếu generator tạo `.java`, cần cơ chế generated Java source root, không dùng `add-resource` để giả vờ đã biên dịch nó.

### 7.2. Khi nào không cần Build Helper?

Một plugin như Protobuf/OpenAPI generator có thể tự thêm resource hoặc source root cần thiết theo cơ chế riêng. Nếu đã làm được, không thêm registration trùng chỉ để “cho chắc”. Kiểm tra tài liệu plugin và output: điều cần chứng minh là `target/classes` có file hoặc compiler thấy source, không phải số lượng plugin trong POM.

### 7.3. Sinh mã Java khác sinh resource text

| Đầu ra generator | Mục tiêu Maven | Kiểm chứng |
| --- | --- | --- |
| `*.java` | Source root để Compiler Plugin biên dịch | `target/classes/.../*.class` |
| `*.properties`, `*.json`, `*.txt` | Resource root để Resources Plugin copy/filter | `target/classes/...` chứa file |
| Test fixture sinh động | Test resource root trước `process-test-resources` | `target/test-classes/...`, không trong JAR chính |
| Resource sau compile | Phase/plugin phù hợp trước đóng gói, hoặc workflow riêng | JAR và classpath thật sau packaging |
| Binary được chuyển đổi | Copy **byte nguyên vẹn** và đúng target path | Checksum hoặc kiểm tra bằng parser/tool chuyên dụng |

## 8. Ví dụ sai thường gặp về thứ tự khi đăng ký generated resource

Đừng đặt generator ở `generate-resources` và Build Helper ở `process-resources` rồi mặc định tin rằng registration luôn chạy trước `resources:resources` mặc định trong **cùng phase process-resources**. Các default lifecycle bindings và execution gắn bằng POM có thứ tự thực thi theo Maven, và ở một số cấu hình goal copy mặc định có thể đã chạy **trước** goal đăng ký root.

Có hai cách rõ ràng hơn:

- Generator tạo file ở phase sớm; đăng ký source/resource ở `generate-resources`; copy mặc định ở `process-resources` (cách demo sử dụng).
- Dùng một generator tự đăng ký root; hoặc chủ động thiết kế các executions/phase riêng theo đúng tài liệu và xác minh thứ tự goal trong log.

Dưới đây sẽ dùng **`initialize → generate-resources → process-resources`**, nên không có sự phụ thuộc mơ hồ vào hai execution trong cùng phase.

## 9. Dự án Java 17 chạy được: filtered main, unfiltered main, test fixture, generated resource

Dự án sau là ví dụ có thể thực hành với JDK 17, Maven 3 tương thích, repository cho phép tải Maven plugins/JUnit 5. Dự án không yêu cầu một server riêng hay generator nội bộ. Maven AntRun Plugin sinh một file resource đơn giản, còn Build Helper Plugin đăng ký root.

Bốn nhóm được kiểm chứng:

1. **Main resource cần filtering**: `config/app.properties`.
2. **Main resource giữ nguyên văn**: `messages/welcome.txt`.
3. **Test fixture không được ship**: `fixtures/input.txt`.
4. **Generated main resource**: `generated/build.txt`, tạo dưới `target/generated-resources` rồi được đóng gói vào JAR.

### 9.1. Cấu trúc file do người học tạo

```text
resource-scope-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/resources/ResourceApp.java
    │   └── resources/
    │       ├── config/app.properties
    │       └── messages/welcome.txt
    └── test/
        ├── java/demo/resources/ResourceAppTest.java
        └── resources/fixtures/input.txt
```

**Không tạo sẵn** `target/generated-resources/demo/generated/build.txt`: đây là output Maven phải tạo, giúp ta chứng minh pipeline codegen/resource-copy hoạt động trên một checkout sạch. Cần lưu file tiếng Việt dưới `src/main/resources` ở UTF-8.

### 9.2. POM hoàn chỉnh và có thể dùng để build

Tệp `resource-scope-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>resource-scope-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <demo.displayName>Resource Lab</demo.displayName>
        <demo.environment>local</demo.environment>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>config/app.properties</include>
                </includes>
            </resource>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
                <excludes>
                    <exclude>config/app.properties</exclude>
                </excludes>
            </resource>
        </resources>

        <testResources>
            <testResource>
                <directory>src/test/resources</directory>
                <filtering>false</filtering>
            </testResource>
        </testResources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>generate-main-build-resource</id>
                        <phase>initialize</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/generated-resources/demo/generated"/>
                                <echo
                                    file="${project.build.directory}/generated-resources/demo/generated/build.txt"
                                    encoding="UTF-8">generated=yes</echo>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>build-helper-maven-plugin</artifactId>
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <id>register-generated-main-resources</id>
                        <phase>generate-resources</phase>
                        <goals>
                            <goal>add-resource</goal>
                        </goals>
                        <configuration>
                            <resources>
                                <resource>
                                    <directory>${project.build.directory}/generated-resources/demo</directory>
                                    <filtering>false</filtering>
                                </resource>
                            </resources>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <propertiesEncoding>UTF-8</propertiesEncoding>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Những lựa chọn có chủ đích:**

- Hai `<resource>` lấy cùng `src/main/resources` nhưng hai tập file **không giao nhau**; tránh copy `config/app.properties` một lần filtered rồi lại copy unfiltered.
- `testResources` tách hoàn toàn khỏi `resources`. Fixture chỉ được Resources Plugin đưa vào `target/test-classes`, không tự có trong JAR chính.
- AntRun sinh `generated/build.txt` ở phase `initialize`, trước Build Helper `add-resource` ở `generate-resources`.
- Resources Plugin chạy goal `resources` mặc định ở `process-resources`, sau khi root generated được đăng ký.
- Filtering chỉ dùng delimiter `@`. Thẻ `useDefaultDelimiters=false` tránh tự động nhận thêm cú pháp `${...}` cho file được lọc.
- Phiên bản Maven Compiler Plugin, Surefire và JAR Plugin được chốt; `maven.compiler.release=17` chỉ đặt Java release mục tiêu, không tự tải JDK 17.
- JUnit Jupiter là dependency `test` của project, không phải dependency runtime sản phẩm.

**Lưu ý về POM:** `<echo>` trong AntRun tạo text `generated=yes`. Đây là **ví dụ về generated resource**, không phải cách sản xuất build metadata hoàn chỉnh ở production. Nếu muốn nhúng version/commit, nên có quy trình dữ liệu đầu vào xác định và tránh tạo timestamp ngẫu nhiên khiến build khó tái lập.

### 9.3. File main resource có filtering

Tệp `src/main/resources/config/app.properties`:

```properties
app.name=@demo.displayName@
app.version=@project.version@
app.environment=@demo.environment@
```

File này được POM cho vào nhóm `filtering=true`. Với các POM properties ở trên, sau `process-resources`, nội dung mong đợi tại `target/classes/config/app.properties` là:

```properties
app.name=Resource Lab
app.version=1.0.0
app.environment=local
```

Chỉ cấu hình **giá trị công khai, không nhạy cảm** vào filtered resource. Một token `@secret.key@` mang credential sẽ tạo rủi ro vì artifact chứa bản secret được nhúng; thay bằng secret injection ở runtime khi cần.

### 9.4. File main resource cố ý không filtering

Tệp `src/main/resources/messages/welcome.txt` (UTF-8):

```text
Xin chào! @demo.displayName@ được giữ nguyên.
```

File thuộc nhóm `filtering=false`, vì vậy output ở `target/classes/messages/welcome.txt` **vẫn chứa nguyên** `@demo.displayName@`. Đây là minh họa rằng có một placeholder trông giống Maven token **không khiến Resources Plugin thay** nếu resource không bật filtering.

Tình huống thực tế tương tự là file template có các token dành cho template engine khác, hoặc JSON/YAML cần framework xử lý sau khi ứng dụng chạy.

### 9.5. Test fixture không nằm trong main JAR

Tệp `src/test/resources/fixtures/input.txt`:

```text
fixture-only
```

Maven copy file này tới `target/test-classes/fixtures/input.txt` ở `process-test-resources`, nên unit test có thể đọc qua classpath. Nó **không** được copy vào `target/classes` bởi `resources:resources` theo POM ở trên.

**Không dùng file fixture này làm config mặc định sản phẩm**. Nếu mã trong `src/main/java` cố truy cập `/fixtures/input.txt` khi chạy từ JAR đã phát hành, nó sẽ không có file đó trừ khi runtime cấp thêm một resource cùng tên từ nơi khác.

### 9.6. Java 17: đọc resource từ classpath, không đọc đường dẫn source

Tệp `src/main/java/demo/resources/ResourceApp.java`:

```java
package demo.resources;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class ResourceApp {
    private ResourceApp() {
    }

    public static Properties config() throws IOException {
        try (InputStream in = ResourceApp.class.getResourceAsStream(
                "/config/app.properties")) {
            if (in == null) {
                throw new IOException("Missing resource: /config/app.properties");
            }
            Properties properties = new Properties();
            properties.load(new InputStreamReader(in, StandardCharsets.UTF_8));
            return properties;
        }
    }

    public static String readUtf8(String absoluteClasspathPath)
            throws IOException {
        try (InputStream in =
                     ResourceApp.class.getResourceAsStream(absoluteClasspathPath)) {
            if (in == null) {
                throw new IOException(
                        "Missing resource: " + absoluteClasspathPath);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    public static String summary() throws IOException {
        Properties p = config();
        return p.getProperty("app.name") + " v"
                + p.getProperty("app.version")
                + " [" + p.getProperty("app.environment") + "]";
    }

    public static void main(String[] args) throws IOException {
        System.out.println(summary());
        System.out.println(readUtf8("/messages/welcome.txt").strip());
        System.out.println(readUtf8("/generated/build.txt").strip());
    }
}
```

Giải thích:

- `getResourceAsStream("/config/app.properties")` đọc **classpath resource**. Code này vẫn hoạt động khi file được đóng trong JAR, không yêu cầu thư mục `src/main/resources` tồn tại ở máy triển khai.
- Phương thức `config()` dùng `Properties.load(Reader)` với UTF-8, tránh mặc định ISO-8859-1 của overload `load(InputStream)` khi file thực sự dùng UTF-8.
- `readAllBytes()` có sẵn trong Java 9+, hợp lệ với Java 17.
- `strip()` bỏ khoảng trắng và xuống dòng ở đầu/cuối khi hiển thị, giúp stdout ổn định giữa LF/CRLF. Nó **không sửa file** trong artifact.
- `/generated/build.txt` là file được Maven sinh và copy vào main output. Nếu resource root chưa đăng ký đúng, phương thức đọc ném `IOException` với thông điệp rõ ràng.

### 9.7. JUnit 5 kiểm chứng bốn tình huống riêng

Tệp `src/test/java/demo/resources/ResourceAppTest.java`:

```java
package demo.resources;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ResourceAppTest {

    @Test
    void mainConfigWasFiltered() throws IOException {
        Properties p = ResourceApp.config();
        assertEquals("Resource Lab", p.getProperty("app.name"));
        assertEquals("1.0.0", p.getProperty("app.version"));
        assertEquals("local", p.getProperty("app.environment"));
    }

    @Test
    void unfilteredMainMessageKeepsPlaceholders() throws IOException {
        assertEquals(
                "Xin chào! @demo.displayName@ được giữ nguyên.",
                ResourceApp.readUtf8("/messages/welcome.txt").strip());
    }

    @Test
    void generatedResourceWasCopiedIntoMainClasspath()
            throws IOException {
        assertEquals("generated=yes",
                     ResourceApp.readUtf8("/generated/build.txt").strip());
    }

    @Test
    void testOnlyFixtureIsVisibleToTests() throws IOException {
        assertEquals("fixture-only",
                     ResourceApp.readUtf8("/fixtures/input.txt").strip());
    }
}
```

Có **4 test**; mỗi test kiểm tra một mục đích khác nhau. Kết quả test cuối chứng minh fixture nằm trên **test classpath**, nhưng chưa chứng minh fixture vắng mặt trong JAR phát hành. Việc vắng mặt cần kiểm tra thêm bằng `jar tf` tại phần 9.10.

Test `mainConfigWasFiltered` cố ý kỳ vọng environment mặc định là `local`, vì vậy nếu đổi thành `-Ddemo.environment=ci` và chạy lại **toàn bộ test**, test này có thể thất bại: đó là một giới hạn có chủ đích của ví dụ. Khi thử override environment ở phần 10, chỉ chạy phase copy resource và kiểm tra file, rồi chạy lại build với mặc định để xác nhận QA.

### 9.8. Kiểm tra theo từng phase, không dựa vào file cũ

Đứng tại `resource-scope-lab/`, với JDK 17+ và Maven phù hợp:

```bash
mvn -version
mvn -B clean process-resources
```

Lệnh thứ hai làm sạch `target`, chạy AntRun ở `initialize`, Build Helper ở `generate-resources` và Resources Plugin ở `process-resources`. Sau lệnh này, các file quan trọng dự kiến là:

```text
target/
├── generated-resources/
│   └── demo/
│       └── generated/
│           └── build.txt
└── classes/
    ├── config/app.properties
    ├── messages/welcome.txt
    └── generated/build.txt
```

Ở thời điểm này **Java source chưa được compile** vì chúng ta dừng tại `process-resources`, trước phase `compile`. Nếu thấy file generated có mặt dưới `target/generated-resources` nhưng **không** có dưới `target/classes`, kiểm tra execution `build-helper:add-resource`, thứ tự phase và log `resources:resources`.

### 9.9. Build đầy đủ và chạy thử ứng dụng

Chạy:

```bash
mvn -B clean verify
```

Với POM và mã ở trên, trong môi trường hợp lệ:

1. `clean` xóa output cũ.
2. AntRun tạo `generated/build.txt` trong thư mục sinh mã/tài nguyên.
3. Build Helper đăng ký thư mục generated resources vào project.
4. Resources Plugin copy main resources, thay placeholder ở `config/app.properties` và giữ nguyên `messages/welcome.txt`.
5. Compiler Plugin biên dịch `ResourceApp.java`.
6. Resources Plugin copy test fixture tới `target/test-classes`.
7. Compiler Plugin biên dịch `ResourceAppTest.java`.
8. Surefire chạy **4 test**, kỳ vọng **0 failure, 0 error**.
9. JAR Plugin tạo `target/resource-scope-lab-1.0.0.jar`.

Kiểm tra `target/surefire-reports` để xác nhận test thực sự được chạy, không bị skip. `BUILD SUCCESS` một mình không thay thế test report.

Sau đó chạy chương trình trên Linux/macOS:

```bash
java -cp target/classes demo.resources.ResourceApp
```

Trên Windows PowerShell:

```powershell
java -cp target\classes demo.resources.ResourceApp
```

**Stdout riêng của lệnh Java này**:

```text
Resource Lab v1.0.0 [local]
Xin chào! @demo.displayName@ được giữ nguyên.
generated=yes
```

Chương trình không cần dependency runtime bên ngoài: JUnit chỉ là dependency test, các resource và class sản phẩm nằm dưới `target/classes`. Dấu tiếng Việt được đọc bằng UTF-8 nên không phụ thuộc vào encoding mặc định của `Properties.load(InputStream)`.

### 9.10. Đọc JAR cuối cùng để xác nhận ranh giới main/test

Từ project root, sau `mvn -B clean verify`:

```bash
jar tf target/resource-scope-lab-1.0.0.jar
```

Danh sách entry **phải chứa** các path logic sau (còn các entry khác như manifest/Maven metadata):

```text
demo/resources/ResourceApp.class
config/app.properties
messages/welcome.txt
generated/build.txt
```

Danh sách **không nên chứa**:

```text
fixtures/input.txt
demo/resources/ResourceAppTest.class
```

Vì `fixtures/input.txt` nằm ở `src/test/resources` và `ResourceAppTest.class` ở `target/test-classes`, chúng không thuộc main JAR mặc định. Nếu thấy fixture xuất hiện trong JAR, cần điều tra `<resources>` hoặc plugin packaging có copy test output sang main output hay không.

**Quan trọng:** `jar tf` cho biết đường dẫn entry, không kiểm chứng nội dung filtered `app.properties`. Để kiểm tra cả hai, dùng test Maven, giải nén JAR vào thư mục tạm được kiểm soát hoặc đọc entry bằng chương trình.

### 9.11. Kiểm tra chính classpath của JAR, không chỉ target/classes

Trong ví dụ này có thể chạy class đã đóng gói bằng:

```bash
java -cp target/resource-scope-lab-1.0.0.jar demo.resources.ResourceApp
```

Khi code/resource thực sự được đóng trong JAR, stdout cũng là:

```text
Resource Lab v1.0.0 [local]
Xin chào! @demo.displayName@ được giữ nguyên.
generated=yes
```

**Đừng dùng `java -jar target/resource-scope-lab-1.0.0.jar`**: POM mẫu không khai báo `Main-Class` cho manifest; đây là JAR thư viện/thông thường, nhưng vẫn có thể dùng trong `-cp` với class name.

Lệnh này chứng minh `ResourceApp` và main resources hoạt động từ **JAR đã đóng gói**, tránh một lỗi dễ bỏ sót: unit test thành công do classpath có `target/classes` nhưng artifact phát hành thiếu resource vì cấu hình packaging đặc thù.

## 10. Chứng minh filtering có thể thay đổi theo Maven property

POM có:

```xml
<demo.environment>local</demo.environment>
```

Thử chỉ thay **một lần build** mà không sửa POM:

```bash
mvn -B -Ddemo.environment=ci clean process-resources
```

Sau lệnh này, file `target/classes/config/app.properties` được kỳ vọng chứa:

```properties
app.name=Resource Lab
app.version=1.0.0
app.environment=ci
```

Maven có user property `demo.environment` từ CLI cho session đó; Resources Plugin filtering dùng giá trị có hiệu lực để thay `@demo.environment@`. **Chỉ dùng giá trị demo không nhạy cảm**, không truyền secrets bằng `-D...`.

Đây là một lệnh kiểm chứng **đầu ra tài nguyên**, không phải lệnh chạy đầy đủ unit test. Vì bài test `mainConfigWasFiltered` kỳ vọng mặc định `local`, đừng tiếp tục chạy test ngay trên cấu hình `ci` rồi coi test fail là lỗi Resources Plugin. Để trở lại trạng thái bình thường, chạy:

```bash
mvn -B clean verify
```

Lệnh mới không truyền property override nên POM lại chọn `local` và 4 test dự kiến pass. **Không sửa biến môi trường ở POM khi nhu cầu là kiểm tra một lần**.

### 10.1. Build-time configuration và runtime configuration là hai quyết định

Thay `demo.environment` trong quá trình filtering tạo **một artifact khác về nội dung resource**. Nếu phát hành cùng một version nhưng thay config theo môi trường, build A và build B có thể tạo hai JAR khác byte dù cùng source.

Trong hệ thống cần **build once, deploy many**, thường nên **không bake environment-specific secret/endpoint vào artifact**. Thay vào đó, dùng config external ở runtime (biến môi trường, secret manager, config service, mounted file). Maven filtering chỉ phù hợp với thông tin build-time không nhạy cảm, có chủ đích và được ghi nhận.

## 11. Cấu hình môi trường với profiles: khi nào nên và không nên?

Maven profile có thể thay properties, resources, plugin config hoặc build behavior. Ví dụ một dự án có hai giá trị công khai:

```xml
<profiles>
    <profile>
        <id>dev</id>
        <properties>
            <demo.environment>dev</demo.environment>
        </properties>
    </profile>
    <profile>
        <id>ci</id>
        <properties>
            <demo.environment>ci</demo.environment>
        </properties>
    </profile>
</profiles>
```

Đây là **đoạn POM bổ sung** nếu muốn thử profile; không phải phần đã có trong POM runnable ở trên. Có thể gọi:

```bash
mvn -Pci clean process-resources
```

Với profile đã được khai báo và active, Resources Plugin có thể thay `app.environment=ci`. Nhưng nếu POM không khai báo profile đó, `-Pci` không tạo cấu hình mới từ hư không.

Để kiểm tra profile nào được bật:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.4.0:active-profiles
```

**Cảnh báo:** profile có thể tác động lên dependency/plugin/repository ngoài resource filtering. Với yêu cầu tái lập và bảo mật, hãy giữ profile đơn giản, có tài liệu và kiểm chứng output; không gửi token/credential vào resource rồi đóng gói.

## 12. Kiểm chứng byte nguyên vẹn với file binary

Nếu dự án có file `src/main/resources/assets/logo.png` hoặc `src/main/resources/assets/template.zip` thật, kiểm tra **checksum đầu vào và bản copy** thay vì chỉ dùng `jar tf`.

Trên Linux/macOS có công cụ hỗ trợ:

```bash
sha256sum src/main/resources/assets/logo.png
sha256sum target/classes/assets/logo.png
```

Nếu hai file thực sự là bản copy không filtering, các giá trị SHA-256 phải giống nhau. Trên Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 src\main\resources\assets\logo.png
Get-FileHash -Algorithm SHA256 target\classes\assets\logo.png
```

Đây là **lệnh kiểm tra tùy chọn khi project có file ảnh thật**; dự án runnable phần 9 không cung cấp sẵn ảnh nên không chạy nguyên văn hai lệnh này trước khi tạo file nguồn. Việc không đặt asset binary giả vào ví dụ là có chủ ý: không nên copy một file text có đuôi `.png` rồi tự nhận đó là ảnh hợp lệ.

Nếu file đã được đóng vào JAR, còn cần xác minh entry trong JAR có byte tương ứng. Có thể giải nén entry bằng công cụ `jar` vào thư mục kiểm tra và so checksum với source, hoặc dùng API Java đọc resource bytes từ JAR. Nên thử trên artifact cuối cùng trong CI nếu tài sản có ý nghĩa nghiệp vụ.

## 13. Generated test resources: vẫn phải tách khỏi artifact sản phẩm

Có trường hợp test fixture cũng được sinh tự động, ví dụ một generator tạo bộ dữ liệu JSON để test API. Pipeline đúng thường là:

```text
generate-test-resources
    └─ generator tạo target/generated-test-resources/demo/fixtures/case.json
register test resource root (trước process-test-resources)
    └─ build-helper:add-test-resource nếu generator không tự đăng ký
process-test-resources
    └─ resources:testResources copy vào target/test-classes
test
    └─ Surefire đọc fixture theo test classpath
```

Cần đảm bảo registration xảy ra **trước khi** default `resources:testResources` copy. Tên goal thật là `build-helper:add-test-resource`, khác `add-resource` cho main và khác `add-test-source` cho Java test source.

Ví dụ **đoạn plugin** dành cho một project đã có generator tạo thư mục này ở phase sớm hơn:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>3.6.0</version>
    <executions>
        <execution>
            <id>register-generated-test-fixtures</id>
            <phase>generate-test-resources</phase>
            <goals>
                <goal>add-test-resource</goal>
            </goals>
            <configuration>
                <resources>
                    <resource>
                        <directory>${project.build.directory}/generated-test-resources/demo</directory>
                        <filtering>false</filtering>
                    </resource>
                </resources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

**Đây là cấu hình khái niệm bổ sung, không nằm trong POM chạy được phần 9.** Nó chỉ đăng ký test resource root, không tạo fixture. Muốn thật sự build được, phải có generator trước registration và test classpath phù hợp. Không được đem đoạn này dán nguyên vào POM demo rồi kỳ vọng một JSON file tự xuất hiện.

## 14. Resource thường nằm trong JAR; file external nằm ngoài JAR

Khi code chạy như:

```java
ResourceApp.class.getResourceAsStream("/config/app.properties");
```

Java tìm theo **classpath**, bất kể resource nằm dưới `target/classes`, trong JAR hay được classloader/container cung cấp. Điều đó khác với:

```java
java.nio.file.Files.readString(
        java.nio.file.Path.of("src/main/resources/config/app.properties"));
```

Đoạn thứ hai **phụ thuộc đường dẫn filesystem và thư mục làm việc**; nó có thể chạy từ checkout nhưng thường thất bại khi triển khai chỉ mang JAR. Nó không phải cách đọc một resource đóng gói thông thường.

Nếu một file thật sự cần **thay đổi sau deploy**, **được mount từ container** hoặc **chứa secret runtime**, hãy cố ý thiết kế external configuration path. Khi ấy `Files.readString(Path)` có thể phù hợp, nhưng path phải do launcher/container/env cung cấp và được kiểm tra phân quyền. Đừng giả làm classpath resource rồi trông đợi thay file ngoài JAR được classloader đọc tự động.

### 14.1. Lưu ý khi dùng getResourceAsStream

- `Class.getResourceAsStream("/config/app.properties")` có slash đầu nên tra từ classpath root.
- `ClassLoader.getResourceAsStream("config/app.properties")` thường dùng tên không có slash đầu; đừng trộn hai API mà không sửa path.
- Nếu `getResourceAsStream(...)` trả `null`, resource không tìm thấy trong classpath ở vị trí đó.
- Nếu dùng custom classloader hoặc modular application, phạm vi nhìn thấy resource có thể khác; phải kiểm tra runtime thật.
- Một tên resource trùng trên nhiều JAR có thể khiến kết quả phụ thuộc classpath order. Với dữ liệu quan trọng, dùng namespace path rõ ràng như `com/company/product/config/...`.

## 15. Test classpath và JAR classpath có thể khác nhau như thế nào?

Surefire dùng test runtime classpath, thường chứa `target/test-classes`, `target/classes` và các dependency/test runtime cần thiết. Vì thế unit test có thể đọc `/fixtures/input.txt` từ `target/test-classes`.

Còn khi ứng dụng chạy từ JAR sản phẩm:

```bash
java -cp target/resource-scope-lab-1.0.0.jar demo.resources.ResourceApp
```

classpath ở đây chỉ chứa JAR đã chỉ định. Nó không tự chứa test fixture. Việc một test đọc thành công `/fixtures/input.txt` **không** phải bằng chứng ứng dụng có thể đọc file đó ở production — và theo phân tách đúng, chúng ta còn **mong muốn nó không tồn tại ở production**.

Để kiểm chứng ranh giới:

1. Test phải đọc được fixture từ `target/test-classes`.
2. File fixture không có trong `target/classes` sau clean build.
3. JAR cuối cùng không có entry `fixtures/input.txt`.
4. Chương trình runtime hoạt động nhờ các main/generated resource được đóng gói.
5. Không có cấu hình khác ở CI/release task copy test resources sang main artifact.

Một test **không thể chứng minh sự vắng mặt trong JAR** chỉ bằng việc gọi `getResourceAsStream("/fixtures/input.txt")` khi chạy trong Surefire: test classpath đang cố ý chứa fixture đó. Muốn xác nhận âm tính, cần đọc JAR **sau phase package** hoặc chạy kiểm tra artifact như một bước CI riêng.

## 16. Maven multi-module và tách resource ownership

Trong dự án nhiều module, mỗi module có **resource roots riêng** và artifact riêng:

```text
root/
├── shared-config/
│   └── src/main/resources/config/common.properties
├── service/
│   └── src/main/resources/config/service.properties
└── app/
    └── src/main/resources/messages/welcome.txt
```

Root liệt kê ba module trong `<modules>` chỉ cho Maven Reactor biết phải xây chúng. Nó **không** tự copy `shared-config/src/main/resources` vào output của `service` hoặc `app`.

Nếu `service` cần dùng resource từ `shared-config`, cần thiết kế artifact dependency hoặc cơ chế đóng gói chính thức:

- `service` khai báo dependency vào JAR của `shared-config`, để resource có thể có trên runtime classpath khi dependency đó được cấp.
- Nếu muốn **nhúng** file từ nhiều artifact vào một distribution/fat JAR, cần plugin và quy tắc merge/collision rõ ràng; dependency thông thường không tự nhúng hết JAR con vào JAR chính.
- Không nên làm `service` trỏ thẳng vào `../shared-config/target/classes` vì nó phụ thuộc output vật lý và thứ tự build ngoài hợp đồng artifact.

Nếu hai module cùng chứa `config/app.properties`, runtime classpath có thể trả về bản từ module/JAR nào xuất hiện trước. Nên đặt namespace hoặc tên file phân biệt, không dựa vào thứ tự classpath tình cờ.

## 17. Cấu hình Resources Plugin để phù hợp môi trường và bảo mật

### 17.1. Chốt version plugin

Nên pin phiên bản của Resources Plugin trong POM hoặc `pluginManagement` của parent:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
</plugin>
```

Đây là đoạn để minh họa. Nếu dự án nhiều module dùng parent `pluginManagement`, quản lý tập trung tránh mỗi module tự chọn version plugin khác.

### 17.2. Filtering không phải template engine đa năng

Resources Plugin thay các placeholder theo quy tắc/filtering context, nhưng không có chức năng chung để validate mọi YAML/JSON schema hay chạy một template program logic phức tạp. Nếu input yêu cầu xử lý schema/canonicalization, dùng plugin/code generator chuyên dụng và thêm test kiểm chứng nội dung.

Đặc biệt, filter một file JSON/YAML mà không parse sau đó có thể tạo output cú pháp sai nếu giá trị chứa dấu nháy kép, dấu xuống dòng hoặc ký tự escape. Với config quan trọng, test nên **đọc và parse output như định dạng thật**; không chỉ grep xem token đã thay.

### 17.3. Không nhúng secrets vào artifact

Các giá trị như DB password, token, private key và credential của repository không nên đi vào `src/main/resources` hoặc filtered properties mà sau đó Maven đưa vào JAR. Nếu cần secret lúc chạy, dùng secret manager hoặc cấu hình ngoài JAR, phân quyền và cơ chế rotate phù hợp.

Nếu bắt buộc cần chứng minh một JAR không chứa mẫu dữ liệu nhạy cảm, có thể tích hợp kiểm tra artifact policy riêng, nhưng đừng in secret lên CI log để chứng minh rằng nó vắng mặt.

### 17.4. Reproducible builds

Việc filtering `project.version` cho ra đầu ra có thể được dự đoán. Nhưng nếu filter timestamp hệ thống, hostname, username hoặc dữ liệu không ổn định, hai build từ cùng source có thể có nội dung khác nhau.

Nếu cần **reproducible build** theo byte, còn phải kiểm soát plugin version, JDK, ZIP/JAR entry timestamps, resource order, encoding, file permissions và các input môi trường khác. Để ổn định artifact JAR, có thể nghiên cứu `project.build.outputTimestamp` cùng version JAR Plugin hỗ trợ; đây là một vấn đề bổ sung ngoài việc tách resource roots.

## 18. Những lỗi phổ biến và cách điều tra

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Missing resource: /config/app.properties` | File chưa copy, path root sai, exclude nhầm hoặc jar thiếu entry | `target/classes`, `jar tf`, `getResourceAsStream` |
| Text vẫn chứa `@project.version@` | `filtering=false`, file không thuộc nhóm filtered hoặc delimiter không khớp | POM `<resources>`, plugin configuration, nội dung target |
| File template bị đổi `${...}` ngoài ý muốn | Dùng default delimiters trên file đáng lẽ không filter | Tách nhóm resources, dùng `@` và `useDefaultDelimiters=false` |
| Ảnh/PDF/ZIP hỏng sau copy | File nhị phân bị filtering/encoding làm đổi byte | So SHA-256, đặt `filtering=false` |
| Test fixture có trong JAR chính | Fixture đặt sai ở main resources hoặc build packaging copy quá rộng | `jar tf` và resources config |
| Unit test pass, runtime báo thiếu file | Test classpath rộng hơn runtime, code đọc test fixture | Chạy từ JAR như lệnh phần 9.11 |
| `target/generated-resources` có file nhưng `target/classes` không có | Chưa đăng ký root hoặc registration chạy quá muộn | Log generator/Build Helper/Resources, kiểm tra phase |
| Maven chạy direct `resources:resources` thiếu generated data | Bỏ qua generator được bind ở phase trước | Dùng `mvn process-resources` hoặc lifecycle đầy đủ |
| Build local pass, CI sạch fail | Phụ thuộc generated files/cache từ build trước | `mvn clean verify` trên checkout sạch |
| Config ra dấu tiếng Việt lỗi | Input/Resources Plugin/Java Properties encoding khác nhau | UTF-8, `propertiesEncoding` và `load(Reader)` |
| Hai resource cùng path cho kết quả khác ở test | File trùng ở test-classes và classes hoặc hai JAR | Đổi namespace, kiểm tra classpath và output |
| Một file được copy hai lần, nội dung thất thường | Filtered/unfiltered resource sets giao nhau | Chia includes/excludes thành hai nhóm tách biệt |
| Build thành công nhưng thiếu file trong artifact | Chỉ kiểm tra output tạm hoặc plugin package tùy chỉnh | Kiểm tra JAR cuối và chạy bằng runtime artifact |
| Generated resource có timestamp ngẫu nhiên | Generator sử dụng trạng thái không được pin | Kiểm tra generator inputs, test tái lập |
| Kích hoạt profile khác khiến test fail | Build-time resource thay theo profile, test kỳ vọng cấu hình mặc định | Xem effective POM, profile và kiểm tra output đúng biến thể |
| JAR có resource nhạy cảm | Build đã đóng gói dữ liệu không nên phát hành | Kiểm tra source/config policy và xử lý secrets theo quy trình an toàn |

## 19. Quy trình QA cho resource khi review Pull Request

Một lần review thay đổi resources hoặc generator nên lưu bằng chứng cho các câu hỏi sau:

1. **Phân loại mục đích**: file là main, test-only, generated hay external runtime config?
2. **Xác nhận source root**: đường dẫn POM có đúng cấp thư mục và includes/excludes không?
3. **Kiểm tra filtering**: chỉ những file text dự định thay placeholder mới được filter?
4. **Kiểm tra encoding**: đầu vào, plugin và mã Java đang thống nhất UTF-8 nếu có tiếng Việt?
5. **Kiểm tra binary**: file không được filter và byte/checksum trước–sau giống nhau?
6. **Kiểm tra lifecycle**: generator chạy trước registration/copy; phase `process-resources` được gọi đầy đủ?
7. **Kiểm tra output tạm**: `target/classes` và `target/test-classes` có đúng file, đúng nội dung?
8. **Kiểm tra JAR cuối**: main/generated resources có mặt, test fixture không có mặt?
9. **Kiểm tra runtime**: đọc resource bằng classpath từ JAR chạy thật, không dựa path `src/...`?
10. **Kiểm tra bảo mật**: không nhúng token/credential hoặc dữ liệu test nhạy cảm vào artifact?
11. **Kiểm tra tái lập**: build sạch trên CI, version plugin/JDK/inputs có ổn định?
12. **Kiểm tra test report**: unit/integration test liên quan đã chạy thật, không bị skip?

Các lệnh chủ yếu của ví dụ:

```bash
# Quan sát copy main resources, trước khi compile
mvn -B clean process-resources

# Biên dịch, chạy test và đóng gói
mvn -B clean verify

# Kiểm tra entry của artifact
jar tf target/resource-scope-lab-1.0.0.jar

# Chạy từ classpath của artifact
java -cp target/resource-scope-lab-1.0.0.jar demo.resources.ResourceApp
```

Đây là các bước có mục tiêu khác nhau. Nếu lệnh copy resource đầu tiên pass, **chưa kết luận** Java đã compile. Nếu JAR có entry đúng, **chưa kết luận** nội dung filtered đúng; cần đọc nội dung bằng test hoặc kiểm tra artifact. Nếu unit test pass, **chưa kết luận** test fixture vắng mặt trong JAR; cần xem JAR thực tế.

## 20. Kết luận: ranh giới là hợp đồng của artifact

**Main resources** là dữ liệu chương trình cần khi chạy; **test resources** là dữ liệu chỉ để kiểm thử; **generated resources** là dữ liệu được tạo theo lifecycle và phải được đăng ký/copy đúng thời điểm; **external config** là dữ liệu cố ý nằm ngoài artifact để triển khai và bảo mật.

Trong Maven, việc tách các nhóm này đúng cách cần cả hai phía:

- **Khai báo:** `<resources>`, `<testResources>`, filtering text/binary, source/resource roots và phase của generator.
- **Chứng minh:** file trong `target/classes` hoặc `target/test-classes`, nội dung filtered, checksum của binary, Surefire reports, entry trong JAR và khả năng chạy từ **chính artifact**.

Khi nguồn dữ liệu, mục đích sử dụng, đường đi và đầu ra đều được kiểm tra, dự án mới có cơ sở để phát hành một JAR sạch, đúng cấu hình và có khả năng tái lập.

### Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference, Build Resources](https://maven.apache.org/pom.html)
- [Maven Resources Plugin 3.3.1 — resources:resources](https://maven.apache.org/plugins-archives/maven-resources-plugin-3.3.1/resources-mojo.html)
- [Maven Resources Plugin 3.3.1 — resources:testResources](https://maven.apache.org/plugins-archives/maven-resources-plugin-3.3.1/testResources-mojo.html)
- [Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [MojoHaus Build Helper Maven Plugin — add-resource](https://www.mojohaus.org/build-helper-maven-plugin/add-resource-mojo.html)
- [MojoHaus Build Helper Maven Plugin — add-test-resource](https://www.mojohaus.org/build-helper-maven-plugin/add-test-resource-mojo.html)
- [Maven AntRun Plugin 3.1.0 — antrun:run](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/run-mojo.html)
- [Apache Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
