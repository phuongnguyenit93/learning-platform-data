# Relocation và kiểm soát xung đột package trong Maven Shade và Assembly

## 1. Vấn đề: hai thư viện có cùng package/class trên classpath

Khi dự án Maven phụ thuộc nhiều JAR, có thể xuất hiện **xung đột class trên classpath**. Ví dụ hai thư viện đều chứa entry:

```text
com/acme/common/Parser.class
```

JVM định danh một class bằng **binary name + defining class loader**, không phải bằng tên file JAR hay Maven `groupId`. Nếu hai JAR trên cùng classpath cung cấp **cùng một binary name** và cùng class loader tìm kiếm, một định nghĩa có thể che định nghĩa còn lại. Kết quả là:

- Code đang mong API mới nhưng JVM nạp định nghĩa cũ → `NoSuchMethodError`.
- Code muốn field/method khác version → `NoSuchFieldError` hoặc `AbstractMethodError`.
- Một thư viện dùng API đã thay đổi hoặc class bytecode không phù hợp → `LinkageError`.
- Thư viện được chọn không khớp với thư viện bạn tưởng đang dùng.
- Khi gộp JAR thành uber JAR, nhiều input có **trùng đường dẫn ZIP entry**; công cụ phải xử lý hoặc loại trừ một bản sao.

Trong Maven, vấn đề này có **hai mức riêng** cần phân biệt:

1. **Xung đột version của cùng một Maven artifact**: ví dụ cả hai nhánh dependency cần `org.example:core` với version khác nhau. Maven dependency mediation thường chỉ chọn **một version** cho cùng dependency key trong graph; bạn không thể coi hai version cùng tồn tại độc lập chỉ bằng việc khai cả hai.
2. **Xung đột class/package giữa các artifact hoặc các bản đã bundle sẵn**: có thể là hai tọa độ Maven khác nhau nhưng cùng chứa `com/acme/common/Parser.class`. Maven chọn version theo GAV không tự phát hiện hay đổi tên mọi class trùng.

**Relocation** của **Maven Shade Plugin** giúp tạo **bản sao riêng dưới namespace khác** cho một số thư viện được gộp vào shaded JAR. Đây là một kỹ thuật tránh xung đột package/class, không phải giải pháp chung cho mọi vấn đề dependency.

### Sau bài học, bạn có thể

- Giải thích khác nhau giữa **shading**, **relocation**, **Maven dependency mediation** và **Assembly packaging**.
- Biết khi nào chuyển một package từ `org.apache.commons.lang3` sang `dev.lesson.internal.shaded.lang3` là hữu ích.
- Hiểu Shade sửa **ZIP entry paths và bytecode references**, không chỉ đổi tên thư mục.
- Biết giới hạn với reflection, `ServiceLoader`, resource files, JNI, serialized data, JPMS và signed JARs.
- Cấu hình `<relocations>`, `<relocation>`, `<pattern>`, `<shadedPattern>`, excludes, transformers và artifact filters.
- Build một ứng dụng Java 17 bằng Maven Shade Plugin 3.6.2 rồi kiểm tra **class file đã relocate** bằng `jar tf` và `javap`.
- Đọc cảnh báo overlapping classes/resources, xác định xung đột gốc và chọn xử lý phù hợp.
- Đánh giá khi nào Assembly Plugin đủ dùng và khi nào cần Shade hoặc tách modules/class loaders.

## 2. Khái niệm cơ bản: shading khác relocation và version mediation

| Khái niệm | Nó thay đổi điều gì? | Không tự giải quyết điều gì? |
| --- | --- | --- |
| **Dependency mediation** | Maven chọn version artifact theo dependency graph, nearest definition/độ sâu và thứ tự khi ngang mức | Không tự rename package/class; không cho cùng một class loader dùng hai định nghĩa trùng binary name |
| **Exclusions** | Loại bỏ dependency theo các cạnh trong graph | Không tự sửa references từ code tới thư viện bị loại |
| **Assembly `jar-with-dependencies`** | Unpack/thu gom project artifact và dependencies vào một JAR cơ bản | Không có bytecode package relocation tương đương Shade |
| **Shade / uber JAR** | Gộp project classes và dependencies thành một output JAR | Không bảo đảm tránh trùng classes/resources nếu không cấu hình |
| **Relocation** | Chuyển classes được shade từ package cũ sang namespace mới, cập nhật references mà shader nhận diện | Không tự đổi Maven GAV; không đảm bảo mọi reflective string/native/resource config được sửa |
| **Resource transformers** | Hợp nhất/chỉnh một số resources và metadata khi shading | Không tự sửa mọi file JSON/YAML/XML/protocol tùy ý |
| **Class loader isolation** | Load hai tên trùng qua các class loaders tách biệt | Không đơn giản hóa trao đổi dữ liệu giữa class loaders; thường phức tạp hơn relocation |

### Ví dụ xung đột version theo Maven

```text
app
├─ dependency-a:1.0
│  └─ shared-core:1.0
└─ dependency-b:2.0
   └─ shared-core:2.0
```

Nếu cả hai khai cùng `groupId:artifactId:type:classifier`, Maven dependency mediation chọn version hiệu lực theo quy tắc graph và quản lý phụ thuộc. **Đừng khẳng định app đang có cả `shared-core:1.0` lẫn `shared-core:2.0` trên runtime classpath chỉ vì hai nhánh yêu cầu hai version.**

Tùy tương thích API, giải pháp ưu tiên thường là:

- **Đồng bộ version** theo BOM/`dependencyManagement` và nâng các thư viện cùng hỗ trợ.
- **Sửa API/mã** để chỉ sử dụng một version.
- **Loại dependency cũ** bằng exclusions sau khi xác nhận thư viện còn chạy đúng.
- Khi bất khả kháng, **shade riêng một thư viện trước** để mang bản copy private, nhưng phải thiết kế đúng luồng publication.

Relocation không phải “chọn giúp Maven hai version từ cùng một GAV rồi dịch chuyển riêng version cũ” ở bước package cuối. Khi Maven đã chỉ resolve một version, Shade **không có bản thứ hai để tự chuyển đổi**.

## 3. Maven Shade Plugin và Maven Assembly Plugin khác nhau ở đâu?

**Maven Shade Plugin** có goal `shade:shade`, thường bind ở phase `package` để tạo uber JAR và hỗ trợ **package relocation** cùng resource transformers.

**Maven Assembly Plugin** tạo các distribution archives như ZIP, TAR, directory hoặc JAR. Descriptor `jar-with-dependencies` có thể unpack dependency JARs và thu gom class/resource vào một JAR; nhưng tài liệu chính thức của Assembly gọi đây là **hỗ trợ cơ bản** cho uber JAR và đề nghị Shade nếu muốn kiểm soát sâu hơn. **Assembly `jar-with-dependencies` không thay thế cơ chế `<relocations>` của Shade.**

| Nhu cầu | Lựa chọn ưu tiên |
| --- | --- |
| Tạo ZIP phân phối chứa `app.jar`, scripts, `lib/*.jar` và docs | Assembly Plugin với descriptor thích hợp |
| Tạo uber JAR đơn giản không cần sửa class namespace | Shade thường rõ ràng hơn để kiểm soát merge; Assembly `jar-with-dependencies` có thể đủ trong một số trường hợp |
| Đổi tên package của dependencies trong output bytecode | **Shade Plugin: `<relocations>`** |
| Merge `META-INF/services` sau khi gộp | Shade `ServicesResourceTransformer` |
| Viết manifest `Main-Class` cho shaded executable JAR | Shade `ManifestResourceTransformer` |
| Chỉ khai báo module dependencies/version | `dependencies` và `dependencyManagement`; chưa cần Shade |
| Tránh lỗi vì hai JAR chứa class trùng tên | Trước tiên xác định class nào cần và vì sao; cân nhắc tách artifact, exclusions, relocation từng bên hoặc class loader isolation |

### Relocation là “namespace isolation” ở bytecode

Ví dụ:

```text
Input dependency JAR:
  org/apache/commons/lang3/StringUtils.class

Relocation:
  pattern = org.apache.commons.lang3
  shadedPattern = dev.lesson.internal.shaded.lang3

Output shaded JAR:
  dev/lesson/internal/shaded/lang3/StringUtils.class
```

Ngoài tên entry, những **bytecode references** từ project hoặc các class được shade tới `org.apache.commons.lang3.StringUtils` được rewrite sang tên mới tương ứng. Vì vậy chương trình đã compile với thư viện gốc vẫn có thể chạy trong shaded artifact mà không cần sửa dòng `import` của source code.

Không thể đạt kết quả tương đương chỉ bằng copy class file vào thư mục ZIP mới: tên type trong constant pool, method descriptors, field types và nhiều reference sites vẫn phải nhất quán với binary names mới.

## 4. Khi nào relocation thực sự cần thiết?

### Tình huống A — library muốn mang một bản dependency private

Bạn phát hành `dev.company:client-sdk` dùng thư viện helper nội bộ, nhưng consumer có thể đang dùng version helper khác. Nếu bundle các classes của helper dưới **package gốc**, người dùng có thể gặp duplicate classes trên classpath.

Relocate helper vào:

```text
dev/company/clientsdk/internal/shaded/helper/...
```

sẽ giảm khả năng consumer có cùng binary names. **Đổi package của bản private**, còn **API public của SDK** nên giữ ổn định.

### Tình huống B — framework/plugin environment có shared classpath

Plugin của một IDE/server/Maven runtime khác có thể chia sẻ class loader hoặc delegate classes, khiến dependency bundle của bạn xung đột với thư viện do host cung cấp. Relocation có thể bảo vệ helper private **nếu class loader constraints và API boundary cho phép**.

Nhưng nhiều framework có cơ chế plugin class loader riêng hoặc public SPI classes phải dùng chung identity. **Không relocate toàn bộ public framework packages** để sửa nhanh lỗi: consumer/host có thể không nhận ra interface implementation đã đổi binary name.

### Tình huống C — hai thư viện khác GAV cùng mang classes trùng

Ví dụ:

```text
legacy-client.jar -> com/acme/protocol/Codec.class
modern-client.jar -> com/acme/protocol/Codec.class
```

Maven có thể giữ cả hai artifact vì GAV khác nhau, nhưng khi bundle, class path bị trùng.

**Quan trọng:** nếu cả hai class cùng tên đã được đưa vào **một** Shade execution và bạn đặt:

```xml
<relocation>
    <pattern>com.acme.protocol</pattern>
    <shadedPattern>dev.lesson.internal.protocol</shadedPattern>
</relocation>
```

thì **cả hai input class cùng pattern đều có thể được chuyển tới cùng một output path**, vẫn bị collision. Relocation **không tự biết cần đổi riêng một thư viện** nếu cả hai chứa cùng binary name. Cách xử lý thường là:

1. Chọn dependency thực sự cần và loại artifact dư nếu có thể.
2. Nếu bắt buộc giữ hai bản, **shade riêng một thư viện thành artifact đã relocate trước**, công bố một bộ tọa độ riêng có quản lý, rồi mới để consumer phụ thuộc cả bản gốc và bản relocated.
3. Hoặc thiết kế isolation bằng class loader/module boundary khác khi cần.

Mô hình hai giai đoạn:

```text
legacy-client-source + legacy dependencies
            |
            v
    Build artifact private
    relocation: com.acme.protocol
           -> dev.company.internal.legacy.protocol
            |
            v
    publish relocated-client artifact
            |
            +-----------------------+
                                    |
modern-client (original namespace) |
            |                       |
            +----------+------------+
                       |
                       v
                  final app
       (two distinct binary namespaces)
```

Cần đảm bảo **mọi bytecode/API/metadata liên quan tới artifact legacy đã được rewrite phù hợp**, và output publish không kéo dependency unrelocated trở lại qua POM.

## 5. Relocation sửa cái gì và không sửa cái gì?

Một relocation hợp lệ thường tác động tới:

- **Tên entry của class** trong shaded ZIP (`org/example/A.class` → `internal/example/A.class`).
- **Binary class names** trong bytecode cùng symbolic references tương ứng.
- Type descriptors/signatures mà bytecode remapper hỗ trợ.
- Một số resource metadata thông qua transformers tương thích.

Nhưng **không nên giả định** relocation tự động sửa mọi dữ liệu ngoài bytecode:

| Nội dung | Rủi ro còn lại | Cách kiểm tra |
| --- | --- | --- |
| `Class.forName("org.example.Plugin")` | Tên class dạng chuỗi động, ghép chuỗi hoặc loaded từ config có thể không được remap đúng | Test reflection path; kiểm tra strings/config và bản Shade đang dùng |
| `ServiceLoader` / `META-INF/services` | Service file path/provider class names cần merge/relocate | Dùng `ServicesResourceTransformer` và test `ServiceLoader.load(...)` |
| Spring/XML/YAML/JSON/Properties config | Có thể chứa FQCN gốc ở dạng text | Kiểm tra resource files, framework startup/smoke tests |
| JNI, native libraries | Symbol names hoặc resource loader paths có thể phụ thuộc package gốc | Test native calls; tránh relocation nếu JNI không tương thích |
| Serialization / persisted class names | `serialVersionUID`/binary type name hoặc serialized format có thể đổi | Kiểm tra backward compatibility, dữ liệu lưu lâu dài |
| Public API types | Client compile/runtime kỳ vọng type ở package gốc | Giữ API public tách khỏi private shaded dependency |
| Signed JAR signature metadata | Chữ ký `META-INF/*.SF`, `*.DSA`, `*.RSA` có thể không còn hợp lệ sau sửa bytes | Loại metadata chữ ký của bản shaded khi phù hợp, kiểm tra compliance/license |
| JPMS `module-info.class` | Module names, exports/opens/uses/provides có thể không phù hợp | Đánh giá module path, test với `java --module-path` hoặc cân nhắc tránh Shade |
| Multi-release JAR | Classes dưới `META-INF/versions/*` cần xử lý nhất quán | Kiểm tra JDK target, Shade version, output JAR entries |
| Resource path hard-coded | `getResource("org/example/config.xml")` có thể trỏ đường cũ | Kiểm tra resource lookup sau shade |

Tùy Shade version, có hỗ trợ xử lý một số string constants; **đó không phải lời hứa rằng mọi chuỗi động hoặc resource tùy ý được rewrite**. Vẫn cần test trên artifact cuối.

## 6. Cấu hình `<relocations>` trong Maven Shade Plugin

Cấu hình chính:

```xml
<relocations>
    <relocation>
        <pattern>org.apache.commons.lang3</pattern>
        <shadedPattern>dev.lesson.internal.shaded.lang3</shadedPattern>
    </relocation>
</relocations>
```

Ý nghĩa:

- `pattern`: package prefix nguồn cần chuyển.
- `shadedPattern`: namespace đích.
- Có thể thêm nhiều `<relocation>` entries khi cần.
- Có thể giới hạn `<includes>`, `<excludes>` để một số classes không bị chuyển.
- Shader sửa đường dẫn class files và bytecode references để duy trì khả năng load/link sau di chuyển.

**Không chọn namespace đích trùng với public packages hoặc namespace của một dependency khác.** Nên dùng prefix sở hữu bởi project, ví dụ `dev.company.product.internal.shaded`, và đặt package private đó bên trong artifact không yêu cầu consumer import trực tiếp.

### Ví dụ chỉ relocate một phần package

```xml
<relocations>
    <relocation>
        <pattern>com.example.utility</pattern>
        <shadedPattern>dev.company.internal.utility</shadedPattern>
        <excludes>
            <exclude>com.example.utility.publicapi.*</exclude>
        </excludes>
    </relocation>
</relocations>
```

Đây là **snippet minh họa**, không áp dụng cho demo đầy đủ vì demo dùng Commons Lang3. Class matching `com.example.utility.publicapi.*` có thể được giữ package gốc; cần kiểm tra **sự tương thích của references từ classes đã relocate tới classes bị exclude**. Loại trừ một vài public classes sai cách có thể tạo biên giới API không nhất quán.

### Quy tắc thực hành khi chọn `pattern`

- **Relocate một package phụ thuộc cụ thể**, thay vì `<pattern>com</pattern>` hoặc `<pattern>org</pattern>`.
- Không relocate classes Java tiêu chuẩn như `java.*`, `javax.*` hoặc `jakarta.*` chỉ để né lỗi version.
- Tránh relocate packages của logging API hoặc public SPI nếu host/consumer phải chia sẻ chính xác class identity.
- Nếu thư viện có nhiều packages riêng, cần biết toàn bộ dependency tree trước khi quyết định pattern.
- Luôn kiểm tra bản final bằng `jar tf` và kiểm thử runtime; chỉ thấy `BUILD SUCCESS` chưa đủ.

## 7. Ví dụ Java 17 chạy được: relocate Apache Commons Lang trong một uber JAR

Ví dụ sau **minh họa relocation thành công**, **không cố ý tạo xung đột class thật**. Chúng ta dùng `org.apache.commons:commons-lang3:3.14.0` vì có class `StringUtils` dễ quan sát.

Mục tiêu:

```text
Trước shade:
  Java source imports org.apache.commons.lang3.StringUtils
  Dependency JAR contains org/apache/commons/lang3/StringUtils.class

Sau shade:
  Output JAR contains
    dev/lesson/app/Main.class
    dev/lesson/internal/shaded/lang3/StringUtils.class

  Main.class references relocated StringUtils in bytecode
  java -jar ... works without an external commons-lang3 JAR
```

### 7.1. Yêu cầu

- JDK 17+.
- Maven 3.x tương thích với các plugin versions được khai.
- Có kết nối Maven Central hoặc repository manager/mirror để tải Maven plugins và Commons Lang3.
- Đứng ở thư mục project khi chạy lệnh.

### 7.2. Cấu trúc project

```text
shade-relocation-lab/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── lesson/
                    └── app/
                        └── Main.java
```

Chỉ cần tạo hai file `pom.xml` và `src/main/java/dev/lesson/app/Main.java`. Thư mục `target/` và shaded JAR sẽ được Maven tạo khi build.

### 7.3. POM hoàn chỉnh — `shade-relocation-lab/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>shade-relocation-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>create-relocated-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <createDependencyReducedPom>true</createDependencyReducedPom>
                            <minimizeJar>false</minimizeJar>

                            <relocations>
                                <relocation>
                                    <pattern>org.apache.commons.lang3</pattern>
                                    <shadedPattern>dev.lesson.internal.shaded.lang3</shadedPattern>
                                </relocation>
                            </relocations>

                            <filters>
                                <filter>
                                    <artifact>*:*</artifact>
                                    <excludes>
                                        <exclude>META-INF/*.SF</exclude>
                                        <exclude>META-INF/*.DSA</exclude>
                                        <exclude>META-INF/*.RSA</exclude>
                                    </excludes>
                                </filter>
                            </filters>

                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>dev.lesson.app.Main</mainClass>
                                </transformer>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích có hệ thống:

1. `packaging=jar`: default lifecycle gọi Jar Plugin tại phase `package` để tạo project JAR cơ bản.
2. Shade Plugin có execution riêng cũng ở `package`, gom project classes và dependencies thành shaded JAR.
3. `<relocation>` chuyển package `org.apache.commons.lang3` sang namespace private `dev.lesson.internal.shaded.lang3`.
4. `<minimizeJar>false</minimizeJar>` giữ các classes chưa được xác định là không dùng; đây là lựa chọn thận trọng khi đang kiểm tra relocation.
5. `ManifestResourceTransformer` ghi `Main-Class: dev.lesson.app.Main` cho executable JAR.
6. `ServicesResourceTransformer` hỗ trợ các file `META-INF/services` nếu có dependency dùng `ServiceLoader`; trong ví dụ đơn giản này không phải phần quan sát chính.
7. `filters` loại các **metadata chữ ký** có thể không còn hợp lệ khi JAR inputs bị chỉnh sửa; **không tự ý xóa** `LICENSE`, `NOTICE` hay metadata pháp lý cần giữ.
8. `createDependencyReducedPom=true` giúp plugin tạo POM giảm dependencies đã embed, có ích khi shaded artifact được publish để tránh consumer kéo thêm bản unshaded ngoài ý muốn. Theo mặc định, plugin có thể sinh `dependency-reduced-pom.xml` ở project basedir; hãy quản lý build output này phù hợp.
9. Không dùng `outputFile` riêng trong demo; do đó Shade Plugin ở cấu hình thông thường có thể **thay main artifact bằng shaded JAR**, để `install/deploy` dùng artifact đã shade. Nếu cấu hình outputFile hoặc attached classifier thì semantics của artifact thay đổi, cần kiểm tra mục 12.

**Lưu ý riêng về signatures:** loại signature metadata trên file shaded **không đồng nghĩa** có quyền bỏ qua chính sách signature/provenance của tổ chức. Khi cần xác thực nguồn artifact, hãy xác minh upstream checksums/signatures **trước shading**, kiểm tra supply-chain policy và ký lại artifact phát hành theo quy trình hợp lệ.

### 7.4. Java source — `src/main/java/dev/lesson/app/Main.java`

```java
package dev.lesson.app;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("RESULT=" + StringUtils.capitalize("hello maven"));
        System.out.println("CLASS=" + StringUtils.class.getName());
    }
}
```

Vì project đang biên dịch với dependency gốc, `import` trong source code **vẫn là `org.apache.commons.lang3.StringUtils`**. Shade Plugin chạy **sau biên dịch**, nên bytecode cuối trong uber JAR được rewrite để trỏ tới relocated class.

**Sau shading, ta kỳ vọng `StringUtils.class.getName()` trả namespace mới.** Đây là cách kiểm chứng trực tiếp hơn chỉ nhìn log `shade:shade`.

### 7.5. Build

Tại project root:

```bash
mvn -version
mvn -B -ntp clean package
```

Khi Maven resolve plugins/dependencies thành công và compiler/shader hoạt động đúng, file chính kỳ vọng là:

```text
target/shade-relocation-lab-1.0.0.jar
```

Tùy Shade configuration, Maven có thể giữ bản JAR trước shading dưới tên dạng `target/original-shade-relocation-lab-1.0.0.jar`. **Đừng dùng nhầm JAR original** để kết luận relocation không có tác dụng.

Plugin cũng có thể tạo `dependency-reduced-pom.xml` tại project root. File này liên quan publication metadata; không tự sửa POM gốc chỉ vì output được tạo. Khi thay đổi policy, xác nhận file nào được sử dụng lúc install/deploy.

### 7.6. Kiểm tra JAR entry paths

Linux/macOS (Bash):

```bash
jar tf target/shade-relocation-lab-1.0.0.jar | grep 'StringUtils.class'
```

Mục tiêu là thấy entry:

```text
dev/lesson/internal/shaded/lang3/StringUtils.class
```

Kiểm tra class thuộc package cũ không còn dưới cùng tên:

```bash
jar tf target/shade-relocation-lab-1.0.0.jar | grep '^org/apache/commons/lang3/StringUtils.class$'
```

**Không có kết quả** ở lệnh kiểm tra thứ hai là điều mong đợi. Trong Bash, `grep` trả exit code 1 khi không match; điều này không đồng nghĩa build Maven thất bại.

Windows PowerShell:

```powershell
jar tf target\shade-relocation-lab-1.0.0.jar | Select-String 'StringUtils.class'
jar tf target\shade-relocation-lab-1.0.0.jar | Select-String '^org/apache/commons/lang3/StringUtils.class$'
```

Không nên coi `jar tf` riêng là toàn bộ phép kiểm: còn phải chứng minh **Main.class đã tham chiếu tới binary name mới**, và runtime thật sự chạy.

### 7.7. Kiểm tra bytecode references bằng `javap`

```bash
javap -classpath target/shade-relocation-lab-1.0.0.jar -c dev.lesson.app.Main
```

Trong disassembly, tìm tham chiếu tới:

```text
dev/lesson/internal/shaded/lang3/StringUtils
```

Dòng chữ cụ thể có thể nằm trong phần comment/method invocation của `javap -c`; đây là **chuỗi cần tìm**, không phải toàn bộ output có thứ tự cố định. Sau shading, bytecode của `Main` phải trỏ tới StringUtils đã relocate.

**Tại sao cần bước này?** Chuyển đường ZIP entry mà không cập nhật references có thể khiến JVM vẫn tìm `org.apache.commons.lang3.StringUtils` và lỗi. Shade Plugin dùng bytecode rewriting, nên thực hành cần kiểm tra cả đường dẫn class lẫn references.

### 7.8. Chạy executable JAR

```bash
java -jar target/shade-relocation-lab-1.0.0.jar
```

**Stdout chính xác từ `Main.main` khi chạy thành công:**

```text
RESULT=Hello maven
CLASS=dev.lesson.internal.shaded.lang3.StringUtils
```

Lý giải:

- `StringUtils.capitalize("hello maven")` viết hoa chữ cái đầu thành `Hello maven`.
- `StringUtils.class` là class literal đã được cập nhật trong bytecode để trỏ tới relocated type.
- `Class.getName()` trả về binary name mới `dev.lesson.internal.shaded.lang3.StringUtils`.

Ứng dụng không cần truyền thêm Commons Lang JAR qua `-cp` vì bytecode của dependency đã được đóng gói vào shaded JAR dưới namespace mới. Nếu không thấy `CLASS=...shaded...`, kiểm tra đang chạy đúng file shaded hay nhầm `original-*.jar`, `<relocations>` và Maven log.

### 7.9. Phân biệt build output với test thực thi

Một `mvn package` thành công chứng minh plugin chạy tới phase đóng gói, **không chứng minh mọi reflection/service loader path đều hoạt động**. Chạy thật `java -jar` là smoke test mức tối thiểu. Với ứng dụng có `ServiceLoader`, config, native code hoặc JPMS, cần thêm integration tests tương ứng.

Demo ở trên có import một dependency đơn giản, nên output kiểm tra relocation rõ ràng. Nó **chưa chứng minh** một tình huống hai phiên bản không tương thích đã được hòa giải; các tình huống xung đột thật cần test riêng theo dependency graph và classpath của consumer.

## 8. Cấu hình chọn artifact nào được đưa vào shaded JAR

Shade Plugin có hai cơ chế dễ nhầm:

- **`artifactSet`**: chọn hoặc loại **dependency artifacts** theo tọa độ patterns.
- **`filters`**: chọn hoặc loại **entries/files** bên trong từng artifact.

Ví dụ fragment cho một plugin Shade:

```xml
<configuration>
    <artifactSet>
        <includes>
            <include>org.apache.commons:commons-lang3</include>
        </includes>
    </artifactSet>
    <relocations>
        <relocation>
            <pattern>org.apache.commons.lang3</pattern>
            <shadedPattern>dev.lesson.internal.shaded.lang3</shadedPattern>
        </relocation>
    </relocations>
</configuration>
```

Đây chỉ là **đoạn cấu hình**. Nó hướng tới việc đưa dependency Commons Lang3 vào shaded output; cần đánh giá nếu project còn có các dependencies runtime khác, vì loại chúng khỏi uber JAR có thể khiến `java -jar` thiếu class.

**Không nhầm:** `artifactSet` quyết định class/resource từ artifact nào được đưa vào output, còn `relocations` quyết định package namespace của những class matching **sau khi lựa chọn nội dung**. Một relocation rule **không tự thêm** một artifact mà `artifactSet` đã loại.

### Ví dụ filter tránh metadata chữ ký không còn hợp lệ

```xml
<filters>
    <filter>
        <artifact>*:*</artifact>
        <excludes>
            <exclude>META-INF/*.SF</exclude>
            <exclude>META-INF/*.DSA</exclude>
            <exclude>META-INF/*.RSA</exclude>
        </excludes>
    </filter>
</filters>
```

Tuy nhiên, **filters sai có thể loại file quan trọng**: `META-INF/services`, Spring auto-configuration metadata, `module-info.class`, XML descriptors hoặc license notices. Khi shade một thư viện phức tạp, hãy bắt đầu với filters tối thiểu có giải thích và test.

### Không dùng `minimizeJar` để “chữa” xung đột khi chưa hiểu graph

`<minimizeJar>true</minimizeJar>` tìm cách loại classes không cần dựa trên phân tích bytecode/reference reachability. Nhưng những class được gọi qua reflection, `ServiceLoader`, DSL/config files hoặc native code có thể không được nhận ra đúng.

**Quy trình:** đầu tiên làm shading/relocation đúng với `minimizeJar=false`, chạy functional/integration tests, rồi mới thử tối ưu và so artifact diff. Nếu sau tối ưu app báo `ClassNotFoundException`, xem lại các entry points/dynamic load paths và cân nhắc tắt minimization.

## 9. Xung đột resources và transformers

Sau khi bundle nhiều JAR, có thể trùng resource entries ngay cả khi class packages đã khác. Các ví dụ:

```text
META-INF/services/com.example.spi.Converter
META-INF/spring.factories
META-INF/plexus/components.xml
META-INF/LICENSE
META-INF/NOTICE
application.properties
logging.properties
```

Không có quy tắc “giữ file đầu tiên luôn đúng” cho mọi loại metadata. Một resource chứa danh sách providers thường cần **merge**, còn một file cấu hình ứng dụng có thể cần **ưu tiên có chủ đích** hoặc **đổi tên**.

### 9.1. ServiceLoader: trường hợp cần `ServicesResourceTransformer`

Một thư viện dùng Java `ServiceLoader` có thể chứa:

```text
META-INF/services/com.example.spi.Converter
```

Nội dung:

```text
com.example.impl.JsonConverter
com.example.impl.XmlConverter
```

Nếu relocation đổi package của service interface hoặc provider classes, **đường dẫn descriptor và tên implementations cũng cần phù hợp**. Nếu nhiều dependency có cùng tên service file, nội dung cần được merge để không mất provider.

Cấu hình Shade:

```xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
</transformers>
```

Transformers loại này xử lý ghép các `META-INF/services` entries và sửa tên classes sau relocation phù hợp. Tuy nhiên, **test thực tế `ServiceLoader.load(MyService.class)` vẫn bắt buộc** nếu ứng dụng dựa vào SPI, đặc biệt khi public API/shared class loader có thể tạo type identity mismatch.

**Tránh relocate public service interface** mà host runtime đang cần để tìm provider nếu phía host không được chuyển namespace tương ứng. Có thể chỉ relocate helper private implementations hoặc dùng thiết kế plugin isolation khác.

### 9.2. Manifest và executable shaded JAR

Để có `java -jar`, Shade có thể dùng:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
    <mainClass>dev.lesson.app.Main</mainClass>
</transformer>
```

Nếu không khai main entry point phù hợp, shaded JAR có thể có toàn bộ classes nhưng `java -jar` báo `no main manifest attribute`. Đừng nhầm lỗi manifest với relocation.

### 9.3. Properties, XML và framework metadata

Một số resources nên merge theo cú pháp riêng thay vì nối chuỗi:

- `META-INF/spring.factories`/Spring auto-configuration metadata có yêu cầu riêng tùy framework/version.
- `META-INF/plexus/components.xml` có transformer cho Plexus descriptors.
- `META-INF/services` có service transformer.
- Properties files có thể có key conflict, ordinal hoặc precedence riêng.
- JSON/XML/YAML files dùng để đăng ký class names cần migration theo framework rules.

Shade có `AppendingTransformer`, `XmlAppendingTransformer`, `ComponentsXmlResourceTransformer` và các transformers khác. **Không áp dụng transformer chỉ vì tên giống**; đọc tài liệu của phiên bản đang dùng và test startup/feature thực tế.

## 10. Duplicate classes: đọc cảnh báo nhưng không chữa bừa

Shade có thể cảnh báo dạng:

```text
... has detected that some files are present in two or more JARs.
When this happens, only one copy of the file is written into the uber jar.
```

Đây là **thông điệp điển hình minh họa**, không cam kết log luôn có đúng câu chữ ở mọi phiên bản. Điều cần làm là tìm **đường dẫn class/resource trùng** và danh sách input artifacts chứa chúng.

### Quy trình tìm nguồn xung đột

1. Chạy `mvn dependency:tree` để xem graph thực tế.
2. Xem log Shade để biết những artifact nào được đưa vào output.
3. Với một class nghi trùng, kiểm tra `jar tf path/to/lib-a.jar` và `jar tf path/to/lib-b.jar`.
4. Nếu trùng class do **cùng thư viện version khác**, trước tiên dùng dependency mediation/management để thống nhất version.
5. Nếu trùng class do **hai artifacts khác GAV** và đều bắt buộc tồn tại, cân nhắc pre-shade một artifact hoặc classloader isolation.
6. Nếu trùng metadata/resource, chọn transformer/filters có chủ đích.
7. Build lại và test output cuối. **Không chỉ ẩn warnings**.

### Các lệnh chẩn đoán

```bash
mvn -B -ntp dependency:tree
mvn -B -ntp dependency:tree -Dverbose
mvn -B -ntp clean package
jar tf target/shade-relocation-lab-1.0.0.jar
```

Lưu ý `dependency:tree -Dverbose` phụ thuộc plugin version/capabilities; nếu cần chính xác, gọi goal bằng fully qualified coordinates/version:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Các lệnh này xem graph Maven và output files; **không đảm bảo liệt kê mọi embedded class** nếu một dependency đã chứa các classes bên thứ ba trong chính JAR của nó.

### “Duplicate class” khác “duplicate resource”

- Hai class cùng binary name: chỉ giữ một bản trong cùng class loader context, gây rủi ro linkage/runtime.
- Hai files `META-INF/services/...`: thường cần merge danh sách providers.
- Hai `LICENSE`/`NOTICE`: cần giữ nghĩa vụ pháp lý, không xóa tùy tiện.
- Hai configs dùng cùng key/file path: phải hiểu precedence của framework hoặc đổi resource path.
- Hai native libs cùng filename: có thể gây lỗi load theo OS/architecture.

**Không giải quyết một warning trùng `META-INF/LICENSE` bằng relocation class package**; đó là hai loại conflict khác nhau.

## 11. Relocation và public API: ranh giới quan trọng nhất của thư viện

Giả sử một SDK public method có signature:

```java
public org.apache.commons.lang3.tuple.Pair<String, String> transform();
```

Đây là **đoạn method signature minh họa**, không phải source class độc lập. Nếu Shade relocate `org.apache.commons.lang3` trong binary SDK public API thành `dev.company.internal.shaded.lang3`, consumer compile với API mà họ mong đợi có thể không tương thích. Đã thay đổi **binary signature**, không còn chỉ là thay thư viện implementation private.

Cách thiết kế tốt hơn:

- Giữ public API dùng Java platform types hoặc các domain API types của SDK.
- Che implementation dependency bên trong classes private/internal.
- Chỉ relocate implementation dependency khi không leak qua public signatures.
- Viết consumer compatibility test dùng một project bên ngoài build SDK để xác minh public API thực sự.
- Dùng semantic versioning khi một thay đổi relocation làm thay đổi API/ABI.

**Relocation không phải luôn là transparent change đối với người dùng thư viện.** Với executable application đóng gói để chạy độc lập, các class private có thể được relocate dễ dàng hơn vì không có consumer biên dịch against API của artifact.

## 12. Publish shaded artifact và dependency-reduced POM

Khi Shade gộp dependency classes vào output JAR, nếu published POM vẫn khai dependency gốc là **transitive runtime dependency**, consumer có thể tải thêm bản **unshaded** của thư viện ấy, tạo xung đột hoặc tăng kích thước classpath.

Vì vậy Shade có cơ chế tạo **dependency-reduced POM**:

```xml
<createDependencyReducedPom>true</createDependencyReducedPom>
```

Đây là cấu hình trong Shade Plugin. Với chế độ mặc định phù hợp, nó có thể tạo `dependency-reduced-pom.xml` để bỏ những dependencies đã gộp khỏi phần dependency metadata dùng khi publish. **Không hiểu nó là “xóa mọi dependency trong project”**: còn phụ thuộc filters, optional/runtime/provided scopes, exclusions và các quyết định shading thực tế.

### Shaded artifact thay main artifact hay attach classifier?

Một số kiểu:

| Cấu hình | Tác dụng |
| --- | --- |
| Shade mặc định, không `outputFile`/classifier riêng | Thường thay artifact chính bằng shaded output |
| `shadedArtifactAttached=true` và `shadedClassifierName=shaded` | Attach shaded artifact thành artifact phụ với classifier thay vì chỉ dùng main artifact |
| `outputFile` custom | Ghi output vào file chỉ định; theo tài liệu Shade, không tự thay main artifact hoặc attach classifier như đường đi mặc định |
| `createDependencyReducedPom=true` | Tạo reduced POM để metadata khớp các dependencies đã embed |

Đừng nghĩ “đặt classifier `shaded` thì mọi consumer tự chọn bản shaded”. Consumer phải phụ thuộc đúng artifact/classifier hoặc project phải publish main artifact theo chiến lược đã định.

### Tránh đổi tên/đường dẫn POM một cách tùy tiện

Theo tài liệu plugin, option `dependencyReducedPomLocation` có những hệ quả đối với basedir trong các execution tiếp theo. Không đặt một đường dẫn tùy ý chỉ để tránh file `dependency-reduced-pom.xml` xuất hiện ở root nếu chưa hiểu hành vi plugin/version.

Nếu repository cần metadata nhất quán cho consumer, hãy test:

- `mvn clean install` trong sandbox.
- Một consumer project mới resolve artifact đã install.
- `mvn dependency:tree` trên consumer.
- Kiểm tra main/classifier thực sự được tải và classpath không có bản dependency gốc không mong đợi.
- Chạy consumer smoke test với artifact đã publish, không chỉ với project workspace.

## 13. Reflection, serialization, JPMS và tình huống khó

### 13.1. Reflection và tên lớp dạng chuỗi

Nếu code gọi:

```java
Class<?> type = Class.forName("org.apache.commons.lang3.StringUtils");
```

đây là **một statement minh họa**. Một số bản Shade có hỗ trợ remap **string constants**, nhưng **không bảo đảm** một chuỗi lớp được ghép động, lấy từ database/config JSON hoặc từ lệnh CLI sẽ được sửa. Nếu app thật dựa vào reflection, cần test toàn bộ workflow và có thể sửa config/loader code hoặc tránh relocate package đó.

Đừng dùng việc `StringUtils.class.getName()` chạy đúng trong demo làm bằng chứng `Class.forName("...")` với mọi kiểu input đều đúng.

### 13.2. Serialization và dữ liệu bền vững

Binary class name có thể xuất hiện trong Java serialization stream hoặc persisted metadata. Sau khi relocation, quá trình deserialize dữ liệu cũ có thể lỗi vì tên lớp khác. Hãy xem tương thích dữ liệu trước khi đưa một shaded class vào disk/network protocol hoặc public API.

### 13.3. JPMS module path

Maven Shade thường được dùng theo **classpath/uber JAR**. Nếu app dùng Java Platform Module System và `module-info.class`, relocation có thể ảnh hưởng `exports`/`opens`/`uses`/`provides`, module names và split-package checks. Đừng giả định cách chạy:

```bash
java -jar target/shade-relocation-lab-1.0.0.jar
```

tương đương:

```bash
java --module-path target/shade-relocation-lab-1.0.0.jar --module module.name
```

Tên `module.name` chỉ minh họa; module path invocation cần module metadata hợp lệ và main class phù hợp. Với JPMS, hãy kiểm tra mục tiêu vận hành rồi quyết định dùng Shade, Maven JLink Plugin hoặc module packaging khác.

### 13.4. Multi-release và binary compatibility

Một multi-release JAR có các classes dành cho những JDK khác nhau dưới `META-INF/versions/N`. Khi shade, phải xem artifact đầu vào có dạng này không, bản plugin có xử lý phù hợp không và runtime tests trên các JDK đích. Một warning liên quan `module-info.class` hoặc multi-release JAR không nên bị xóa bừa bằng filter mà không hiểu hậu quả.

### 13.5. Signed JARs, licensing và supply chain

Gộp và rewrite JAR làm thay đổi bytes, khiến signature metadata gốc không còn chứng minh tính toàn vẹn của output. Filters trong demo giúp tránh lỗi signature metadata mâu thuẫn, nhưng tổ chức vẫn cần:

- Xác minh artifact đầu vào từ repository đáng tin.
- Giữ LICENSE/NOTICE theo yêu cầu pháp lý.
- Ghi nhận SBOM/dependency provenance, kể cả khi package đã relocate.
- Scan vulnerabilities theo **nguồn dependency gốc**; việc đổi package name không vá lỗ hổng.
- Ký/checksum lại artifact phát hành theo policy.

**Relocation không phải biện pháp bảo mật để che giấu thư viện lỗi thời hoặc loại CVE**. Nó chỉ thay namespace trong một số lớp bytecode/resources.

## 14. Khi nào không nên relocation?

Không nên lấy relocation làm phản xạ mặc định với mọi dependency conflict:

- Có thể nâng các dependencies lên version tương thích và giải quyết bằng `dependencyManagement`.
- Consumer cần dùng public API types của chính dependency ấy.
- Library có reflection/JNI/serialization/configuration không thể kiểm soát.
- Có yêu cầu JPMS module path chặt chẽ và relocation làm hỏng module descriptors.
- Một dependency cần được shared giữa host và plugin thông qua class identity.
- Hai input JAR đã chứa cùng FQCN và bạn chưa tách được artifact cần relocate trước merge.
- Việc shade làm mất resource metadata/ServiceLoader providers không thể sửa/test.
- Bạn chỉ cần một distribution ZIP chứa JARs riêng; Assembly Plugin có thể đơn giản và minh bạch hơn.

Một conflict warning có thể chỉ ra **dependency graph không lành mạnh**. Fix đúng ở dependency/model là lựa chọn ưu tiên nếu khả thi.

## 15. Quy trình kiểm tra relocation trước khi release

### Bước 1 — xác minh graph dependency

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

Xác định dependency nào thực sự cung cấp class muốn relocate. Nếu hai dependencies khác nhau cùng đóng class FQCN, đừng để relocation cuối gộp cả hai vào cùng namespace.

### Bước 2 — xem effective plugin config

```bash
mvn help:effective-pom
```

Tìm `maven-shade-plugin`, `relocations`, `filters`, `artifactSet`, `transformers`, `minimizeJar` và `createDependencyReducedPom`. Parent `pluginManagement` có thể ảnh hưởng version/config; phải xem **đúng module**.

### Bước 3 — build sạch

```bash
mvn -B -ntp clean package
```

Dùng `clean` để output cũ không che lỗi. Xem Shade log có duplicate entries, artifact includes/excludes hoặc warnings không.

### Bước 4 — kiểm tra class entries

```bash
jar tf target/shade-relocation-lab-1.0.0.jar
```

Tìm namespace mới, kiểm tra namespace cũ không còn những classes đã được relocate. Đối chiếu service descriptors và resource files cần thiết.

### Bước 5 — kiểm tra bytecode refs

```bash
javap -classpath target/shade-relocation-lab-1.0.0.jar -c dev.lesson.app.Main
```

Xác minh các references trong `Main.class` đã trỏ sang relocated class.

### Bước 6 — chạy executable JAR và test tính năng động

```bash
java -jar target/shade-relocation-lab-1.0.0.jar
```

Với demo, kỳ vọng:

```text
RESULT=Hello maven
CLASS=dev.lesson.internal.shaded.lang3.StringUtils
```

Với ứng dụng thật, bổ sung `ServiceLoader` smoke tests, reflection, config loading, JNI/native, test framework startup và serialized data backward compatibility khi liên quan.

### Bước 7 — kiểm tra consumer/published metadata

```bash
mvn -B -ntp clean install
```

Trong một **project consumer khác**, thử resolve artifact vừa install và chạy code sử dụng API public; xem dependency tree để phát hiện bản unshaded bị kéo theo.

### Bước 8 — so sánh môi trường vận hành

Thử trên các JDK 17+ được hỗ trợ, classpath/module-path setup dự kiến, container/CI runtime đúng và đường release artifact thực tế. Đừng chỉ chạy với `target/classes` vì `target/classes` chứa **bytecode chưa shade** và không chứng minh output JAR được rewrite đúng.

## 16. Bảng chẩn đoán xung đột class/package

| Triệu chứng | Nguyên nhân có thể | Cách điều tra/xử lý |
| --- | --- | --- |
| `NoSuchMethodError` sau khi gộp JAR | Đã load class version khác API compile | Tìm class binary name, dependency tree, duplicate JAR entries |
| `ClassNotFoundException` tên package gốc | Reflection/config dùng tên cũ sau relocation | Kiểm tra FQCN strings, resource metadata, loader code |
| `NoClassDefFoundError` tên package mới | Relocated class hoặc dependency của nó không được embed/không load | Xem `jar tf`, filters, artifactSet, javap bytecode refs |
| `ServiceConfigurationError` | Mất/sai `META-INF/services`, provider class bị relocate mà descriptor không khớp | Dùng ServicesResourceTransformer và test ServiceLoader |
| Maven Shade cảnh báo overlapping classes | Nhiều inputs chứa cùng entry path | Xem input JARs, loại bản dư hoặc shade riêng một artifact trước |
| Sau relocation vẫn còn duplicate class | Cả hai inputs cùng bị relocate tới một output name | Điều chỉnh kiến trúc/tách pre-shade; pattern chung không phân biệt artifact nguồn |
| `NoSuchFieldError` ở consumer | API binary signature/field type thay đổi hoặc class khác version | Kiểm tra public API và compatibility tests |
| `SecurityException: Invalid signature file digest` | Chữ ký cũ của JAR bị thay bytes | Kiểm tra filters chữ ký và policy artifact signing |
| `ClassNotFoundException` khi `minimizeJar=true` | Dynamic/reflection-loaded class bị loại | Tắt minimize, cấu hình entry points phù hợp, test |
| `java -jar` báo no main manifest | Thiếu ManifestResourceTransformer/mainClass hợp lệ | Đọc META-INF/MANIFEST.MF, kiểm tra main class |
| `java -jar` chạy nhưng `java --module-path` lỗi | Module descriptors/classpath vs JPMS khác nhau | Xem module-info, module names, exports/opens, packaging |
| Consumer kéo thêm thư viện gốc | POM publish chưa reduced hoặc artifact classifier không đúng | Kiểm tra reduced POM và consumer dependency tree |
| Bản gốc `original-*.jar` vẫn chứa package cũ | Bạn kiểm tra nhầm JAR trước Shade | Chạy đúng main shaded artifact |
| Ứng dụng thiếu XML/JSON config sau shade | Resource conflict/filter hoặc hard-coded path | Kiểm tra resources, transformer, tests |
| Vulnerability scanner không thấy lib sau relocate | Tên package đã đổi nhưng dependency nguồn vẫn tồn tại | Duy trì SBOM, provenance, scan theo artifact origin |

### Dùng log debug khi thật sự cần

```bash
mvn -B -ntp -e clean package
mvn -B -ntp -X clean package
```

`-e` giúp lấy stacktrace; `-X` in nhiều thông tin resolution/shading và có thể chứa URL repository, local paths, system properties hoặc dữ liệu nhạy cảm. Chỉ dùng tại nơi có quyền phù hợp và **redact thông tin nhạy cảm** trước khi chia sẻ.

## 17. Câu hỏi tự kiểm tra

**Câu 1:** Relocation chỉ đổi tên thư mục trong JAR, không sửa bytecode?

**Đáp án:** Sai. Shade Plugin sửa class entries **và** bytecode symbolic references để các classes có thể link với namespace đã đổi.

**Câu 2:** Maven có hai phiên bản cùng GAV trong dependency graph. Relocation cuối có tự giúp app dùng cả hai?

**Đáp án:** Không. Maven dependency mediation thường chỉ resolve một version của cùng artifact key. Muốn giữ hai bản phải có thiết kế riêng, ví dụ pre-shade một dependency thành artifact/namespace riêng rồi mới consume.

**Câu 3:** Hai JAR khác GAV cùng chứa `com.acme.Parser`. Một relocation `com.acme -> internal.acme` trong final uber JAR có chắc giữ cả hai?

**Đáp án:** Không. Cả hai class có thể bị chuyển tới **cùng output path `internal/acme/Parser.class`**, collision còn nguyên. Cần loại bản dư hoặc xử lý cách ly từng dependency trước khi merge.

**Câu 4:** POM có `<relocation>org.apache.commons.lang3 -> dev.lesson.internal.shaded.lang3`. Có phải sửa `import org.apache.commons.lang3.StringUtils` trong Java source demo trước khi build?

**Đáp án:** Không cần với cách dùng Shade ở phase package. Source compile với dependency gốc; Shade rewrite bytecode sau compile.

**Câu 5:** `ServiceLoader` không tìm được provider sau shade. Nên kiểm tra gì?

**Đáp án:** `META-INF/services` path/provider names, `ServicesResourceTransformer`, public SPI interface identity và việc classes đã relocate. Chạy test ServiceLoader thay vì chỉ nhìn build success.

**Câu 6:** Assembly `jar-with-dependencies` có hỗ trợ `<relocations>` như Shade không?

**Đáp án:** Không. Assembly có hỗ trợ cơ bản cho uber JAR, còn bytecode package relocation thuộc chức năng của Shade.

**Câu 7:** Chạy `mvn clean package` thành công có chứng minh public SDK API tương thích sau relocation?

**Đáp án:** Không. API signatures có thể bị rewrite; cần consumer compatibility tests và xem binary names thực tế.

**Câu 8:** Có nên bật `minimizeJar=true` ngay khi muốn sửa một class conflict?

**Đáp án:** Không nên. Minimization có thể loại classes dùng qua reflection/SPI. Trước tiên hiểu xung đột, chọn đúng artifact/relocation rồi kiểm tra với minimize false.

**Câu 9:** Relocation loại bỏ rủi ro CVE trong Commons Lang3?

**Đáp án:** Không. Đổi package name không vá hành vi có lỗ hổng; phải nâng dependency version, theo dõi SBOM và scan đúng nguồn gốc.

**Câu 10:** Trong demo, `java -jar` in `CLASS=dev.lesson.internal.shaded.lang3.StringUtils` chứng minh điều gì?

**Đáp án:** Chương trình dùng class literal đã tham chiếu namespace mới trong shaded bytecode và class được load thành công; nó không chứng minh mọi reflection/config/ServiceLoader use case đã được xử lý.

## 18. Checklist trước khi chốt Shade relocation

- [ ] Đã xác định root cause: cùng GAV khác version, class trùng giữa khác GAV, resource conflict hay module issue?
- [ ] Đã thử giải pháp đơn giản hơn: update dependency, BOM/dependencyManagement, exclusions.
- [ ] Biết những JARs thực tế được đưa vào Shade output (artifactSet).
- [ ] Chọn `pattern` cụ thể, namespace `shadedPattern` thuộc project và không đụng public API.
- [ ] Không relocate cả hai conflicting inputs vào cùng một output binary name.
- [ ] Nếu phải dùng hai thư viện có package trùng, đã thiết kế pre-shaded artifact hoặc class loader boundary phù hợp.
- [ ] Đã pin Shade Plugin version và kiểm tra compat với Maven/JDK.
- [ ] `Main-Class` đúng nếu cần executable JAR.
- [ ] Có ServicesResourceTransformer khi dependency dùng ServiceLoader.
- [ ] Đã kiểm tra resources (Spring/Plexus/properties/JSON/XML) và các đường FQCN hard-coded.
- [ ] Không xóa LICENSE/NOTICE hoặc che provenance/security policy.
- [ ] Đã xử lý signature metadata của inputs bị rewrite theo đúng chính sách.
- [ ] `minimizeJar` chỉ được bật sau khi kiểm thử dynamic class loading.
- [ ] `createDependencyReducedPom`/classifier/outputFile được thiết kế theo cách publish artifact.
- [ ] Đã xác minh bằng `jar tf` rằng packages mới xuất hiện và packages cũ không còn ngoài mong đợi.
- [ ] Đã dùng `javap -c` kiểm tra bytecode references được rewrite.
- [ ] Đã chạy `java -jar` trên shaded artifact cuối thay vì `target/classes`.
- [ ] Đã test reflection, ServiceLoader, config, serialization, native/JNI, JPMS khi project sử dụng.
- [ ] Đã chạy consumer test nếu shaded artifact là thư viện public.
- [ ] Đã kiểm tra consumer dependency tree để không tải thêm bản unshaded không cần thiết.
- [ ] Đã giữ SBOM/scan vulnerabilities gắn với dependency gốc, không coi relocation là vá bảo mật.

**Kết luận:** **Maven Shade relocation** là một cơ chế đổi **binary namespace của classes được gộp** để tạo một bản dependency private và giảm xung đột classpath. Nó hiệu quả khi được đặt **đúng ranh giới artifact và public API**, kết hợp resource transformers và test runtime. **Assembly** tập trung vào gom/đóng gói phân phối, không thay thế Shade relocation. Với xung đột thật giữa hai class trùng tên, hãy xác định dependency graph và cách build từng artifact trước khi đặt một rule rewrite; **relocation áp dụng chung lên hai bản trùng có thể chỉ di chuyển xung đột sang tên mới**.

## Tài liệu chính thức

- [Apache Maven Shade Plugin — Introduction](https://maven.apache.org/plugins/maven-shade-plugin/)
- [Maven Shade Plugin 3.6.2 — Relocating Classes](https://maven.apache.org/plugins/maven-shade-plugin/examples/class-relocation.html)
- [Maven Shade Plugin — Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html)
- [Maven Shade Plugin — Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html)
- [Maven Shade Plugin — Selecting Contents for Uber JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/includes-excludes.html)
- [Maven Shade Plugin — shade:shade Parameters](https://maven.apache.org/plugins/maven-shade-plugin/shade-mojo.html)
- [Apache Maven Assembly Plugin — Introduction](https://maven.apache.org/plugins/maven-assembly-plugin/)
- [Maven Assembly Plugin — Predefined Descriptors](https://maven.apache.org/plugins/maven-assembly-plugin/descriptor-refs.html)
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Java 17 — Java Virtual Machine Specification: Classes and Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/index.html)
- [Java 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html)
