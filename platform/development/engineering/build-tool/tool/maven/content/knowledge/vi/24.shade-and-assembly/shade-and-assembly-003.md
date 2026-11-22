# Maven Shade Plugin và cấu hình phạm vi artifact được gộp

## 1. Bài toán: vì sao không nên nhét mọi dependency vào một JAR?

Một ứng dụng Java thường được biên dịch thành một JAR chỉ chứa **class và resource của chính dự án**. Những thư viện như Apache Commons Lang, Jackson, JDBC driver hoặc HTTP client thường là các JAR riêng, được Maven quản lý qua `<dependencies>`. Để triển khai một chương trình CLI bằng một file duy nhất, ta có thể dùng **Maven Shade Plugin** tạo một **uber JAR (fat JAR)**: hợp nhất nội dung từ artifact chính và các dependency được chọn vào một archive.

Tuy nhiên, chọn sai phạm vi có thể gây nhiều vấn đề:
- **Thiếu class khi chạy:** ứng dụng được compile với một library nhưng bạn lại loại library đó khỏi uber JAR.
- **JAR quá lớn:** các dependencies chỉ được dùng trong môi trường khác hoặc không cần cho một executable vẫn bị đóng gói.
- **Trùng class/resource:** nhiều thư viện có cùng đường dẫn trong JAR, đặc biệt `META-INF/services` hoặc license/metadata.
- **Xung đột classpath:** một bản thư viện nhúng vào uber JAR va chạm với cùng thư viện do ứng dụng khác cung cấp.
- **Sai POM xuất bản:** nội dung dependency đã gộp không khớp metadata cho Maven consumers.
- **Kiểm thử giả an toàn:** `mvn test` có đầy đủ dependency classpath nhưng `java -jar` ở môi trường sạch lại thiếu class.

Trọng tâm của bài này là **quyết định artifact nào được gộp**, đặc biệt qua `artifactSet`, `includes`, `excludes`, và phân biệt chúng với `filters` (chọn file bên trong artifact). Các tính năng liên quan như resource transformers, relocation và minimization được trình bày để tránh dùng nhầm khi điều khiển phạm vi.

Ví dụ dùng **Maven Shade Plugin 3.6.2**, Maven 3.9.x, Maven Compiler Plugin 3.13.0, Java 17, Commons Lang 3.17.0, Commons Codec 1.17.1 và JUnit Jupiter 5.11.4. Phiên bản Shade được ghim để nội dung có thể đối chiếu với đúng tài liệu Apache Maven.

### Kết quả học tập

Sau bài này, bạn có thể:
1. Giải thích Shade khác Maven JAR Plugin và Maven Assembly Plugin.
2. Tách **dependency graph**, **artifact selection**, **class/resource filtering** và **runtime classpath** thành bốn khái niệm.
3. Viết whitelist/blacklist artifact bằng `artifactSet/includes/excludes` với tọa độ `groupId:artifactId:type:classifier` và wildcard.
4. Dùng `filters` cho file/class entries mà không nhầm với việc bỏ cả artifact.
5. Biết tác động của scope `compile`, `runtime`, `provided`, `test` và transitive dependencies.
6. Tạo uber JAR có `Main-Class`, chạy `java -jar` và xác nhận class có/không có bằng `jar tf`.
7. Cân nhắc `dependency-reduced-pom`, `shadedArtifactAttached`, `minimizeJar`, `relocations` và `ServicesResourceTransformer`.
8. Chẩn đoán `NoClassDefFoundError`, resource collision, signature errors, vấn đề ServiceLoader và CI.

## 2. Shade hoạt động ở giai đoạn nào của Maven?

### 2.1. Plugin goal và phase

Shade có goal:

```text
org.apache.maven.plugins:maven-shade-plugin:3.6.2:shade
```

Goal `shade:shade` được gắn mặc định với **phase `package`** khi bạn khai báo execution phù hợp. Nó yêu cầu Maven project và giải quyết project dependencies ở **scope runtime**. Với project `packaging=jar` thông thường:

```text
validate
   |
compile              -> compiler:compile
   |
test-compile         -> compiler:testCompile
   |
test                 -> surefire:test
   |
package
   |-- jar:jar        -> tạo JAR chính ban đầu
   |-- shade:shade    -> tạo shaded JAR từ tập artifacts được chọn
   |
verify / install / deploy
```

Sơ đồ trên rút gọn lifecycle. Shade có default phase `package` **không có nghĩa nó tự chạy trong mọi dự án JAR**. Bạn cần khai báo plugin goal trong `<executions>`, ví dụ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây chỉ là đoạn POM. Khi gọi `mvn clean package`, Maven đi qua các phase trước, JAR Plugin tạo JAR ban đầu rồi Shade xử lý theo cấu hình. **Gọi trực tiếp `mvn shade:shade` không tự bảo đảm các bước compile/package trước đó đã chạy**; với dự án mới hoặc khi kiểm tra từ sạch, nên gọi lifecycle.

### 2.2. Những lớp dữ liệu Shade dùng

Hãy phân biệt bốn tập:

| Tập dữ liệu | Công cụ/khái niệm | Câu hỏi |
| --- | --- | --- |
| Dependency graph | Maven `<dependencies>`, scope, transitive resolution | Dự án biết những artifact nào? |
| Artifact selection | Shade `<artifactSet>` | Artifact nào được đọc để gộp vào uber JAR? |
| Archive content selection | Shade `<filters>` | Sau khi chọn artifact, class/resource entries nào được giữ? |
| Runtime classpath | `java -jar` hoặc classpath do launcher/container cung cấp | Lúc chạy class nào thật sự tìm được? |

Một dependency **xuất hiện trong `mvn dependency:tree`** không đồng nghĩa bytecode của nó có trong shaded JAR. Ngược lại, loại một JAR bằng Shade `artifactSet` **không xóa khai báo dependency khỏi POM hoặc compile classpath**. Đó là hai quyết định riêng.

### 2.3. Chọn phạm vi khác tạo relocation

- **Selection:** lấy/không lấy JAR của một dependency. Ví dụ loại `commons-codec:commons-codec` hoàn toàn khỏi uber JAR.
- **Filtering:** lấy JAR nhưng loại `META-INF/*.SF` hoặc một class cụ thể bên trong.
- **Relocation:** đổi namespace bytecode của những class đã gộp, chẳng hạn `org.apache.commons.lang3` thành `com.example.internal.lang3`.
- **Minimization:** thử xóa các class được phân tích là không dùng, dựa trên phân tích phụ thuộc tĩnh.

Chúng không thay thế cho nhau. Loại toàn bộ JAR vì chỉ không muốn một vài resources có thể gây `ClassNotFoundException`; di chuyển namespace bằng relocation không tự làm JAR nhỏ đi; minimize không giải quyết lựa chọn môi trường runtime.

## 3. artifactSet: cơ chế chọn hoặc loại artifact nguyên khối

### 3.1. Cấu trúc cơ bản

`artifactSet` chứa hai danh sách:

```xml
<artifactSet>
    <includes>
        <include>com.example:shade-scope-lab</include>
        <include>org.apache.commons:commons-lang3</include>
    </includes>
    <excludes>
        <exclude>commons-codec:commons-codec</exclude>
    </excludes>
</artifactSet>
```

Ý nghĩa:
- `includes` là **whitelist**: chỉ các artifact match pattern mới được lựa chọn.
- `excludes` là **blacklist**: những artifact match bị loại, ngay cả khi có match ở includes.
- Nếu không khai báo includes, selection thường xét các runtime-resolved artifacts theo default và loại những artifact match excludes.
- Sau khi chọn artifact, filters/transformers vẫn có thể tác động đến nội dung file bên trong.

**Mẹo an toàn:** khi dùng whitelist, hãy **bao gồm artifact chính của dự án** (`com.example:shade-scope-lab` trong ví dụ). Shade xét artifact chính qua cơ chế chọn artifact; một whitelist chỉ nhắc tới dependency có nguy cơ khiến main application classes không được đưa vào output. Vì vậy phải kiểm tra `com/example/shadelab/App.class` có ở shaded JAR, không chỉ xem các thư viện.

### 3.2. Tọa độ composite và classifier

Apache Maven Shade Plugin 3.6.2 nhận pattern dựa trên:

```text
groupId:artifactId:type:classifier
```

Trong đó:
- `groupId`: nhóm phát hành artifact, ví dụ `org.apache.commons`.
- `artifactId`: tên artifact, ví dụ `commons-lang3`.
- `type`: thường `jar`, nhưng project có thể dùng artifact type khác.
- `classifier`: biến thể như `tests`, `sources` hoặc custom classifier; classifier rỗng với main JAR.

Cú pháp rút gọn được Shade cho phép:

```text
org.apache.commons                => org.apache.commons:*:*:*
org.apache.commons:commons-lang3  => org.apache.commons:commons-lang3:*:*
com.example:lib:tests             => com.example:lib:*:tests
```

Khi cần chính xác classifier/type có thể dùng bốn vế, ví dụ:

```xml
<exclude>com.example:sample:jar:tests</exclude>
```

Đừng nhầm phần tử thứ ba trong cú pháp rút gọn ba vế với version. **Version không phải một trường trong pattern artifactSet**; Shade so pattern với artifact được Maven resolve. Muốn chọn một version khác, xử lý ở Maven dependency management/exclusions, không viết `groupId:artifactId:1.2.3` rồi tin đó là version filter.

### 3.3. Wildcard và glob-like match

Shade hỗ trợ `*` và `?` trong các vế tọa độ artifact:

```xml
<artifactSet>
    <includes>
        <include>com.example:shade-scope-lab</include>
        <include>org.apache.commons:*</include>
    </includes>
    <excludes>
        <exclude>*:commons-codec</exclude>
        <exclude>*:*-tests</exclude>
    </excludes>
</artifactSet>
```

Ý nghĩa:
- `org.apache.commons:*` nhận nhiều artifacts thuộc group này **nếu chúng có mặt trong tập resolved artifacts**.
- `*:commons-codec` loại artifactId `commons-codec` bất kể group.
- `*:*-tests` loại artifactId có hậu tố `-tests`, **không phải** classifier `tests`; muốn lọc classifier phải viết syntax thích hợp cho classifier.

Lưu ý wildcard **không tải toàn bộ artifact từ Maven Central**. Nó chỉ match những artifact đã có trong tập mà Shade xét, hoặc những artifact được cung cấp theo cơ chế khác được plugin hỗ trợ. `artifactSet` không phải một truy vấn tìm mọi thư viện có cùng groupId.

### 3.4. Includes và excludes có thể cùng tồn tại

Hãy xem tập minh họa:

```text
Project artifact:
  com.example:shade-scope-lab:jar:1.0.0

Project dependencies đã resolve:
  org.apache.commons:commons-lang3:jar:3.17.0
  commons-codec:commons-codec:jar:1.17.1
  org.junit.jupiter:junit-jupiter:jar:5.11.4 (test)
```

Khi khai báo:

```xml
<artifactSet>
    <includes>
        <include>com.example:shade-scope-lab</include>
        <include>org.apache.commons:commons-lang3</include>
    </includes>
    <excludes>
        <exclude>commons-codec:commons-codec</exclude>
    </excludes>
</artifactSet>
```

tập được chọn trong ví dụ sẽ gồm **main artifact và commons-lang3**. Commons Codec không được chọn, dù có `scope=compile` trong POM; JUnit có `scope=test` nên không thuộc tập runtime dependency mà `shade:shade` thông thường yêu cầu resolve.

Trong whitelist trên, exclude Codec là **dòng minh họa bổ sung** (Codec đã không có tên trong includes). Trong dự án có wildcard rộng hoặc một parent thêm includes, dòng exclude tường minh là cách ghi rõ ý định loại Codec. Không lấy “dòng excludes có mặt” làm bằng chứng duy nhất rằng đúng artifact đã bị loại: hãy kiểm tra JAR thực tế.

### 3.5. artifactSet không chạy đệ quy theo cây của từng include

Giả sử dependency A kéo transitive dependencies B và C. Maven resolve chúng thành những artifact riêng. Nếu `artifactSet.includes` chỉ nhận A, Shade **không tự hiểu rằng phải nhận luôn B và C chỉ vì chúng là con của A**. Mỗi resolved artifact được xét độc lập theo pattern.

Điều đó có thể gây lỗi runtime: class A tham chiếu B, nhưng B không có trong shaded JAR. Đừng cho rằng gộp một thư viện top-level luôn tạo closure đầy đủ của runtime dependencies. Cách kiểm tra:
1. `mvn dependency:tree` để nhìn dependency graph đã giải quyết.
2. Đối chiếu từng dependency cần ở runtime với `artifactSet`.
3. Xem archive bằng `jar tf` và chạy executable từ môi trường/classpath sạch.

Nếu muốn whitelist một họ thư viện, dùng group pattern thích hợp **chỉ khi mọi artifact trong họ đều được phép nhúng**; các dependency ngoài group đó vẫn phải được đưa vào riêng khi cần.

## 4. Maven dependency scope và Shade selection

### 4.1. Goal shade cần dependency resolution ở runtime scope

Metadata goal `shade:shade` 3.6.2 công bố **requires dependency resolution: runtime**. Điều này giúp giải thích vì sao runtime dependencies thường được xét, còn test-only dependencies không có mặt trong uber JAR theo mặc định.

| Dependency scope | Có trong compile classpath? | Có ở runtime theo Maven? | Hành vi cần chú ý khi shade |
| --- | --- | --- | --- |
| `compile` | Có | Có | Thường là ứng viên được gộp, trừ khi artifactSet loại |
| `runtime` | Không cần cho main Java compilation | Có | Thường là ứng viên được gộp |
| `provided` | Có | Thông thường do môi trường khác cung cấp | Không tự coi là dependency sẽ được nhúng |
| `test` | Có trong test compile/runtime | Không thuộc app runtime | Không được gộp mặc định |
| `import` | Chỉ dùng trong dependencyManagement cho BOM | Không phải runtime artifact | Không có JAR để nhúng |

Đây là bảng khái niệm cho Maven 3 và các scopes thông dụng. Ngoài scope, còn có transitivity, optional dependencies, exclusions và các plugin-specific mechanisms. Không dựa vào bảng để kết luận tuyệt đối cho mọi custom packaging.

**Quan trọng:** khai báo `<scope>provided</scope>` không phải lệnh cho Shade loại một artifact vốn vẫn được chọn theo cách khác; nó chủ yếu là quyết định dependency resolution/classpath. `artifactSet` là bộ lọc cuối cho các artifact mà Shade có thể xét.

### 4.2. Exclusion trong dependency POM khác artifactSet exclusion

**Dependency exclusion** loại artifact khỏi dependency graph của một tuyến khai báo:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>some-library</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.unwanted</groupId>
            <artifactId>unused-transitive</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Đây là **đoạn minh họa**, không thuộc ví dụ runnable, và phải dùng tọa độ thật nếu áp dụng.

**Shade artifactSet exclusion** chỉ nói “đừng gộp artifact này vào shaded output”, trong khi dependency vẫn có thể xuất hiện ở `dependency:tree`, compile/runtime graph hoặc metadata POM đã công bố. Nếu một dependency thực sự không cần ở bất kỳ đâu, hãy xem lại POM dependency graph thay vì chỉ giấu khỏi shaded JAR.

### 4.3. Optional và transitive dependencies

`<optional>true</optional>` ảnh hưởng việc dependency truyền sang consumers, nhưng không phải cách tổng quát để quyết định Shade có chọn artifact của **dự án hiện tại** hay không. Nếu bạn khai báo một library optional trực tiếp và nó được resolve như dependency của project, hãy kiểm tra hành vi Shade trong setup thực tế.

Tương tự, loại một artifact transitive bằng `artifactSet.excludes` có thể khiến uber JAR thiếu class của thư viện khác. Nếu A dùng B lúc runtime, vẫn phải bảo đảm B có mặt trong bundle hoặc được external runtime cung cấp. Đừng chỉ nhìn việc Maven compilation thành công.

## 5. filters: chọn nội dung trong từng artifact, không phải chọn artifact

### 5.1. Hai tầng lựa chọn

**`artifactSet`:** chọn cả archive/JAR ở mức tọa độ.

**`filters`:** từ những archive đã chọn, giữ hoặc bỏ những entry paths `com/example/Foo.class`, `META-INF/...`, `config/*.properties`.

Ví dụ loại signature metadata trên tất cả artifacts đang được Shade xử lý:

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

`<artifact>*:*</artifact>` match tọa độ artifact theo wildcard; các `<exclude>` bên trong filter là **đường dẫn entry trong JAR**, không phải Maven GAV. Các pattern file dùng kiểu Ant-like paths. Đây là cách ngăn lưu signature files không còn hợp lệ sau khi thay nội dung archive. Không loại `META-INF/LICENSE` hoặc `NOTICE` vô điều kiện: các file này có thể chứa điều kiện pháp lý cần bảo toàn/phân phối.

### 5.2. Ví dụ lọc một package nhất định từ library

Đoạn POM minh họa:

```xml
<filters>
    <filter>
        <artifact>org.apache.commons:commons-lang3</artifact>
        <includes>
            <include>org/apache/commons/lang3/**</include>
        </includes>
        <excludes>
            <exclude>org/apache/commons/lang3/experimental/**</exclude>
        </excludes>
    </filter>
</filters>
```

Nó có nghĩa: **từ Commons Lang3 đã được chọn**, chỉ lấy entries match một package path rồi áp excludes cụ thể. Tên `experimental` chỉ là pattern ví dụ (không khẳng định bản 3.17.0 có directory đó). Trường hợp thực tế cần xét các internal helpers/resources khác và chạy test, vì lọc một package có thể làm mất class mà code cần.

Đặc biệt, include filter có thể **ngầm loại mọi entry không match includes** của artifact đó. Tài liệu Shade cho biết `excludeDefaults=false` có thể điều chỉnh behavior này trong cấu hình liên quan, nhưng phải đọc đúng version và không suy diễn rằng thêm includes vào filter luôn “chỉ thêm vài file” mà không đổi các file còn lại.

### 5.3. Nhiều filter áp trên cùng artifact

Khi nhiều filters cùng match một artifact, tài liệu Shade mô tả selection trên file entries như **giao của các tập được phép**. Một global signature filter cộng với một package include filter có thể khiến output hẹp hơn mong muốn.

Đừng nghĩ các filter được cộng hợp `union` để giữ mọi entry mà bất kỳ filter nào chọn. Với mỗi archive, hãy mô phỏng:
1. Artifact có được chọn từ `artifactSet` không?
2. Filter nào áp vào artifact?
3. Những entry paths nào vượt qua **tất cả filters**?
4. Transformers có cần đọc tài nguyên đã bị loại không?

Ví dụ nếu `META-INF/services/**` bị filter mất, `ServicesResourceTransformer` không thể phục hồi provider descriptors đã bị loại. Build có thể thành công nhưng `ServiceLoader` không tìm được implementation ở runtime.

## 6. Resource transformers: gộp metadata an toàn

Nhiều JAR cùng có một entry path, ví dụ `META-INF/services/javax.xml.parsers.SAXParserFactory` hoặc `reference.conf`. Nếu Shade chỉ chép một bản và loại bản khác, application behavior có thể sai. Resource transformers xử lý các tài nguyên cần phối hợp.

### 6.1. ManifestResourceTransformer

Để `java -jar` biết main class, dùng:

```xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
        <mainClass>com.example.shadelab.App</mainClass>
    </transformer>
</transformers>
```

Transformer tạo/điều chỉnh `Main-Class` trong `META-INF/MANIFEST.MF`. Đừng nhầm bước này với việc xác nhận main class **thật sự có trong output**: nếu whitelist vô tình bỏ project artifact, JAR vẫn có thể có manifest nhưng `java -jar` không tìm được App.

### 6.2. ServicesResourceTransformer

Khi dùng thư viện Java SPI như JDBC drivers, JSON providers, logging adapters hoặc plugin loader, nhiều JAR có files dưới `META-INF/services/`. Có thể thêm:

```xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
</transformers>
```

Transformer này **gộp service entries** từ nhiều archive và cập nhật tên implementation phù hợp khi relocation. Tuy nhiên không nên add rồi nghĩ rằng mọi trùng resource trong hệ thống đã được giải quyết: Spring metadata, `reference.conf`, `META-INF/spring`, XML và các framework descriptors có semantics riêng. Phải chọn transformer thích hợp và test runtime.

### 6.3. AppendingTransformer và các resource khác

Với tài nguyên có nhiều dòng độc lập cần nối, `AppendingTransformer` có thể hữu ích. Ví dụ config có dạng `reference.conf` thường cần merge chứ không thể chọn ngẫu nhiên một bản. Với LICENSE/NOTICE, xem các transformer tương ứng và yêu cầu license của dependencies.

**Bài toán artifact scope vẫn là bước đầu tiên.** Transformer không tạo ra các dependency mà `artifactSet` đã bỏ; nó chỉ xử lý resources của những archive thực sự đi qua shading.

## 7. Ví dụ Java 17 hoàn chỉnh: chỉ gộp Commons Lang, không gộp Commons Codec

Ví dụ này cố tình khai báo **hai dependencies compile** nhưng trong shaded JAR **chỉ gộp một thư viện**. Chương trình sử dụng Commons Lang3 để đảo chuỗi; Commons Codec được khai báo nhằm chứng minh rằng một dependency có trong `dependency:tree` **không bắt buộc có trong shaded output**.

### 7.1. Cấu trúc thư mục

```text
shade-scope-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/shadelab/
    │   └── App.java
    └── test/java/com/example/shadelab/
        └── AppTest.java
```

Yêu cầu: Maven 3.9.x, JDK 17+, kết nối repository cho lần tải plugins/dependencies đầu tiên.

### 7.2. `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>shade-scope-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>

        <!-- Có trong graph, nhưng không được chọn để gộp -->
        <dependency>
            <groupId>commons-codec</groupId>
            <artifactId>commons-codec</artifactId>
            <version>1.17.1</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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
                        <id>bundle-selected-artifacts</id>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <artifactSet>
                                <includes>
                                    <include>com.example:shade-scope-lab</include>
                                    <include>org.apache.commons:commons-lang3</include>
                                </includes>
                                <excludes>
                                    <exclude>commons-codec:commons-codec</exclude>
                                </excludes>
                            </artifactSet>
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
                                    <mainClass>com.example.shadelab.App</mainClass>
                                </transformer>
                            </transformers>
                            <minimizeJar>false</minimizeJar>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích những quyết định quan trọng:**

1. Cả Commons Lang3 và Commons Codec đều khai báo `scope=compile` ngầm định; chúng có mặt trong Maven dependency graph.
2. `artifactSet.includes` chọn **main project artifact** và **Commons Lang3**. `excludes` ghi rõ Codec không được gộp.
3. JUnit chỉ là test dependency, không nằm trong runtime-resolved artifacts của Shade trong ví dụ.
4. Global filter loại các signature entries thường trở nên vô hiệu sau khi bytecode/resources được tái đóng gói.
5. `ManifestResourceTransformer` thêm Main-Class để chạy bằng `java -jar`.
6. `minimizeJar=false` để không vô tình làm thiếu class vì phân tích reachable code; đó là điểm xuất phát an toàn khi học selection.
7. `createDependencyReducedPom=false` **chỉ nhằm giữ POM thử nghiệm dễ quan sát**: không tự tạo reduced POM. Nếu xuất bản shaded JAR như một library cho project khác, phải xem lại metadata để tránh dependencies đã nhúng vẫn được tải lặp. Default của Shade là true, không phải false.
8. Plugin versions được ghim để giảm biến động; output path của JAR phụ thuộc `artifactId` và `version`.

### 7.3. `src/main/java/com/example/shadelab/App.java`

```java
package com.example.shadelab;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String reverse(String value) {
        return StringUtils.reverse(value);
    }

    public static void main(String[] args) {
        String input = "Maven Shade";
        System.out.println("original=" + input);
        System.out.println("reversed=" + reverse(input));
    }
}
```

Code Java hợp lệ trên Java 17, chỉ phụ thuộc Commons Lang3. `StringUtils.reverse` trả về chuỗi đảo ký tự. `Commons Codec` **không được import/call**; đó là lý do demo vẫn chạy khi không gộp Codec.

### 7.4. `src/test/java/com/example/shadelab/AppTest.java`

```java
package com.example.shadelab;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class AppTest {
    @Test
    void reversesText() {
        assertEquals("edahS nevaM", App.reverse("Maven Shade"));
    }
}
```

Test này khớp pattern `*Test` của Surefire và có một method thành công. Nó chứng minh logic trước `package`, nhưng **chưa chứng minh dependency đã được chọn đúng vào JAR**; đó là nhiệm vụ của `jar tf` và `java -jar` phía dưới.

### 7.5. Chạy clean package

Tại thư mục `shade-scope-lab`:

```bash
mvn -version
mvn clean package
```

Với JDK 17+ và khi các dependencies có thể tải/resolve, Maven:
1. Compile App.java bằng Compiler Plugin.
2. Compile và chạy AppTest bằng Surefire.
3. JAR Plugin tạo archive ban đầu.
4. Shade Plugin tạo shaded archive theo whitelist và filters.

Sau `BUILD SUCCESS`, JAR kết quả chính thường là:

```text
target/shade-scope-lab-1.0.0.jar
```

Vì `shadedArtifactAttached` mặc định false, Shade thay main artifact của project (trong trường hợp tên output không bị cấu hình đặc biệt). Có thể có một file `original-...jar` để giữ artifact trước shading, nhưng không dựa vào tên file phụ đó để triển khai.

### 7.6. Kiểm tra class/resource entries

Lệnh không phụ thuộc hệ điều hành:

```bash
jar tf target/shade-scope-lab-1.0.0.jar
```

Tìm những entries sau trong danh sách output:

```text
com/example/shadelab/App.class
org/apache/commons/lang3/StringUtils.class
META-INF/MANIFEST.MF
```

Và **không** kỳ vọng thấy:

```text
org/apache/commons/codec/digest/DigestUtils.class
org/junit/jupiter/api/Test.class
```

Lý do:
- Project artifact và Commons Lang3 đã được chọn.
- Commons Codec có dependency trong POM nhưng bị artifactSet loại.
- JUnit là test-scope, không phải runtime dependency được Shade gộp.
- `AppTest.class` không thuộc main project JAR mặc định và không nên thấy trong uber JAR thông thường.

Lệnh `jar tf` in cả những entries khác, chẳng hạn `META-INF`, package subdirectories, license files và các class khác của Commons Lang3. Các dòng trên chỉ là **những vị trí cần quan sát**, không phải stdout đầy đủ của `jar tf`.

### 7.7. Chạy executable JAR

```bash
java -jar target/shade-scope-lab-1.0.0.jar
```

**Stdout chính xác của chương trình Java:**

```text
original=Maven Shade
reversed=edahS nevaM
```

Không cần truyền Commons Lang3 bằng `-cp` khi chạy với `java -jar`: bytecode `StringUtils` đã được gộp vào archive. Commons Codec vắng mặt nhưng **chương trình vẫn chạy** vì App không sử dụng nó.

**Ranh giới đảm bảo:** đây là ví dụ được thiết kế để cho output xác định; không phải mọi ứng dụng đều chạy được sau khi bạn loại một dependency compile. Nếu code thật có tham chiếu tới Codec lúc runtime, phép loại đó sẽ làm hỏng chương trình.

### 7.8. Kiểm tra dependency graph và sự khác biệt

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree
```

Bạn vẫn sẽ thấy Commons Lang3, Commons Codec và JUnit (test) theo graph Maven. Nhưng chúng **không tự động đồng nghĩa đều đã có class bên trong shaded JAR**.

Một bảng đối chứng:

| Thành phần | Dependency graph | Shaded JAR | Vai trò |
| --- | --- | --- | --- |
| App.class của project | Main artifact | Có | Điểm vào |
| Commons Lang3 | Có, compile | Có | App sử dụng |
| Commons Codec | Có, compile | **Không** | Không dùng trong demo |
| JUnit Jupiter | Có, test | **Không** | Chỉ kiểm thử |

Đừng bỏ Commons Codec khỏi POM **chỉ để kiểm chứng artifactSet**: giữ nó trong graph ở demo này là điều giúp quan sát rõ khác biệt. Trong project thật, nếu library hoàn toàn không được dùng, bỏ nó khỏi POM thường tốt hơn để giảm dependency footprint và rủi ro bảo trì.

## 8. Thí nghiệm đối chứng: loại sai artifact và đưa nó trở lại

### 8.1. Nếu loại thư viện App thật sự dùng

Tạm thêm `org.apache.commons:commons-lang3` vào `<excludes>` hoặc xóa nó khỏi `<includes>`, rồi:

```bash
mvn clean package
java -jar target/shade-scope-lab-1.0.0.jar
```

Maven compilation và unit test có thể vẫn thành công, vì Commons Lang3 vẫn có trên **compile/test classpath**. Nhưng `java -jar` không có `StringUtils` trong bundle, nên thường báo:

```text
java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
```

Đây là **dạng lỗi dự kiến** (phần stack trace đầy đủ, dòng thông báo và JVM details có thể khác). Lý do không phải Java compiler không tìm được dependency; đó là **runtime classpath trong shaded JAR thiếu thư viện**.

**Khôi phục** Commons Lang3 trong includes và bỏ exclusion trước khi dùng project như ví dụ chính.

### 8.2. Nếu muốn gộp cả Commons Codec

Thêm:

```xml
<include>commons-codec:commons-codec</include>
```

vào whitelist và **bỏ**:

```xml
<exclude>commons-codec:commons-codec</exclude>
```

khỏi blacklist, rồi build sạch lại. Khi đó một entry như `org/apache/commons/codec/digest/DigestUtils.class` được kỳ vọng có trong shaded JAR. App vẫn in hai dòng như trước vì không gọi Codec. Bài học ở đây là **sự hiện diện của Codec được điều khiển bằng artifactSet**, không phải bằng việc code có `import` hay không.

### 8.3. Thử bỏ whitelist, chỉ giữ blacklist

Một dạng POM khác:

```xml
<artifactSet>
    <excludes>
        <exclude>commons-codec:commons-codec</exclude>
    </excludes>
</artifactSet>
```

Trong dạng này, Shade xét các resolved runtime artifacts theo mặc định, rồi loại Commons Codec. Khi dependency graph lớn, tập được gộp có thể **rộng hơn whitelist ban đầu**. Đây là cách hữu ích nếu phần lớn dependencies đều cần và chỉ một vài artifact phải loại.

**Chọn whitelist khi cần kiểm soát rất chặt**, nhưng phải cập nhật danh sách khi graph thêm runtime transitive dependencies. **Chọn blacklist khi phần lớn graph cần đóng gói**, nhưng kiểm tra số dependency tăng sau các lần nâng version. Không có đáp án tối ưu cho mọi dự án.

## 9. Những cấu hình nâng cao liên quan đến phạm vi

### 9.1. Relocation không loại artifact

Khi dự án dùng một dependency dễ xung đột namespace với runtime khác, có thể relocation:

```xml
<relocations>
    <relocation>
        <pattern>org.apache.commons.lang3</pattern>
        <shadedPattern>com.example.shadelab.internal.lang3</shadedPattern>
    </relocation>
</relocations>
```

Đây là **đoạn cấu hình tùy chọn**, không có trong POM runnable gốc. Khi được áp dụng, Shade có thể đổi paths, bytecode references tương ứng, và entry `StringUtils.class` sẽ nằm dưới namespace mới. Khi đó kiểm tra JAR phải tìm class theo **đường dẫn đã relocate**, không còn đường dẫn gốc.

Relocation không mặc nhiên làm class ít đi hoặc loại những dependency ngoài artifactSet. Nó cũng có rủi ro với tên class nằm trong string/reflection, metadata framework, serialization và native resources; cần integration tests đầy đủ.

### 9.2. minimizeJar không phải whitelist

Tham số:

```xml
<minimizeJar>true</minimizeJar>
```

kích hoạt chức năng giảm classes bằng **phân tích phụ thuộc tĩnh**. Shade Plugin sử dụng `jdependency` cho việc này; độ chính xác phụ thuộc giới hạn của công cụ phân tích. Những class chỉ được gọi thông qua reflection, ServiceLoader, cấu hình XML/YAML, serialization, JNI hoặc plugin discovery có thể không được nhận biết đầy đủ.

Từ Shade 3.5.0 có `entryPoints` để tinh chỉnh các class được xem là điểm xuất phát:

```xml
<entryPoints>
    <entryPoint>com.example.shadelab.App</entryPoint>
</entryPoints>
```

Chỉ dùng khi `minimizeJar=true` và đã kiểm tra behavior runtime. Trong bài thực hành, đặt false để kết quả lựa chọn chỉ phụ thuộc artifactSet và filters, dễ quan sát hơn.

### 9.3. shadedArtifactAttached và classifier

Theo mặc định `shadedArtifactAttached=false`, shaded archive có thể trở thành **main artifact**, thay archive gốc. Nếu muốn giữ cả JAR gốc và shaded JAR như **artifact kèm classifier**, dùng:

```xml
<shadedArtifactAttached>true</shadedArtifactAttached>
<shadedClassifierName>all</shadedClassifierName>
```

Lúc đó thường có hai sản phẩm:
- `shade-scope-lab-1.0.0.jar`: JAR chính, chưa gộp dependencies.
- `shade-scope-lab-1.0.0-all.jar`: shaded artifact có classifier `all`.

Đây là **một phương án đóng gói khác**, không có trong POM chạy thử. Nếu chọn classifier, hãy cập nhật script deploy/CI và `java -jar` để dùng đúng file. Đừng dựa vào wildcard chọn ngẫu nhiên `target/*.jar` vì có thể chạy nhầm bản thin JAR.

### 9.4. dependency-reduced-pom và việc xuất bản thư viện

Shade Plugin 3.6.2 mặc định:

```xml
<createDependencyReducedPom>true</createDependencyReducedPom>
```

Khi bật, plugin có thể tạo `dependency-reduced-pom.xml` để phản ánh dependencies đã được gộp, tránh Maven consumer tự tải lại những dependency có bytecode nằm trong shaded JAR. Đây là **metadata xuất bản**, không phải một thao tác xóa file JAR khỏi shaded output.

Ví dụ runnable đặt `false` để bạn chỉ cần tập trung vào artifact selection trong một **standalone executable**. Nhưng khi phát hành artifact làm **library** cho project khác, `false` có thể khiến POM được publish vẫn khai báo các thư viện đã nhúng, gây duplicate classes hoặc classpath conflicts. Khi ấy cần thiết kế reduced POM, classifier/relocation và kiểm tra published metadata.

**Lưu ý:** library bị artifactSet loại khỏi uber JAR vẫn có thể cần là dependency bình thường để consumer tải thêm. Đừng làm reduced POM vô tình loại mất những dependency **không được nhúng nhưng vẫn cần ở runtime**.

### 9.5. outputFile và finalName

Shade có `outputFile` để chỉ định trực tiếp đường dẫn output; khi dùng `outputFile`, plugin docs ghi nó có tác dụng khác việc thay/attach main artifact và bỏ qua một số tham số như `finalName`, `shadedArtifactAttached`, `shadedClassifierName` và `createDependencyReducedPom`. Đừng cấu hình chúng cùng lúc rồi mong tất cả đều hoạt động.

`<build><finalName>` chủ yếu điều khiển tên output; nó **không tự chọn artifact nào được gộp**. Nếu bạn đang debug sự khác nhau giữa thin/shaded JAR, hãy kiểm tra tên và artifact association thay vì giả định file mới nhất là shaded file.

### 9.6. extraArtifacts và extraJars từ dòng 3.6.x

Shade Plugin có:
- `extraArtifacts`: bổ sung những artifact được chỉ định bằng tọa độ versioned; những artifact này được resolve **không transitive**.
- `extraJars`: bổ sung những đường dẫn JAR local có sẵn.

Các tính năng này xuất hiện từ 3.6.0, nhưng không nên dùng như cách thay thế quản lý dependencies qua POM. Đặc biệt `extraArtifacts` **không tự kéo toàn bộ cây dependencies** của artifact bổ sung. Nếu library thực sự là dependency cần thiết cho application runtime, thông thường nên khai báo ở `<dependencies>` với scope đúng rồi dùng `artifactSet` để kiểm soát nhúng.

### 9.7. shadeGroupFilter và chọn theo namespace

`shadedGroupFilter` có thể giới hạn artifact theo prefix groupId. Nhưng nó không phải bộ chọn duy nhất; cùng với artifactSet nó có thể khiến scope hẹp hơn, và groupId prefix có thể bao nhiều library không mong muốn. Khi cần audit chắc chắn, danh sách includes/excludes rõ ràng và kiểm tra jar entries giúp giảm nhầm lẫn.

## 10. Vấn đề trùng resource và các ràng buộc không thể bỏ qua

### 10.1. Signature files sau khi gộp

Các JAR đã ký có thể chứa `META-INF/*.SF`, `*.RSA`, `*.DSA`. Khi Shade hợp nhất/đổi nội dung, metadata chữ ký cũ có thể không còn hợp lệ. Global filters thường loại những signature entries này; nếu không, JVM có thể gặp lỗi digest/signature.

**Đây không phải “vô hiệu hóa an ninh” cho một artifact có yêu cầu bảo toàn chữ ký**: nếu tổ chức yêu cầu signed JAR, bạn cần thiết kế lại quá trình ký sau khi build. Không nên tùy tiện bỏ chữ ký để che lỗi khi security policy yêu cầu xác minh publisher.

### 10.2. Services và META-INF resources

`ServiceLoader` cần provider descriptors dưới `META-INF/services/`. Nếu chỉ một entry từ nhiều JAR được giữ, ứng dụng có thể không load được provider dù mọi class đều có mặt. Khi thích hợp, dùng `ServicesResourceTransformer`; đồng thời **không filter mất thư mục này**.

Đừng loại bỏ `META-INF/LICENSE`/`NOTICE` chỉ để giảm vài KB nếu chúng chứa license obligations. Và không thêm filters quá rộng kiểu `META-INF/**` mà không có kiểm toán: ngoài signatures, Maven/project artifacts còn chứa metadata framework khác.

### 10.3. Duplicate classes và dependency convergence

Khi hai dependency đưa vào cùng một fully qualified class, Shade có thể cảnh báo overlap hoặc lấy một class ngoài ý muốn. `artifactSet` cho phép loại một artifact, nhưng phải hiểu nguyên nhân duplicate: dependency version conflict, library forks, API split hoặc có hai implementation.

Nên kết hợp:
- `mvn dependency:tree` và dependency mediation/management;
- kiểm tra các phiên bản được resolve thực tế;
- kiểm tra class/resource entries sau shade;
- test runtime representative path;
- relocation khi thực sự cần cô lập một dependency package.

Không dùng relocation như “thuốc chữa” mọi version mismatch. Nếu API của project cần tương tác với consumer khác, di chuyển namespace sai chỗ còn có thể phá public API.

## 11. Shade, Assembly và Spring Boot repackage khác nhau

| Tiêu chí | Maven Shade Plugin | Maven Assembly Plugin | Spring Boot Maven Plugin |
| --- | --- | --- | --- |
| Mục tiêu phổ biến | Uber JAR bằng cách hợp nhất chọn lọc nội dung | Tạo distribution archive (ZIP/TAR/JAR...) hoặc layout tùy descriptor | Repackage ứng dụng Boot thành executable archive |
| Chọn dependency artifacts | `artifactSet` | Assembly descriptors/dependency sets | Plugin repackage exclusions/includes tương ứng |
| Lọc từng class/resource entry | `filters` | Tùy assembly descriptor/processing, khác Shade | Không tương đương Shade file filters |
| Relocate bytecode package | Có `relocations` | Không phải tính năng trọng tâm | Thường không relocate libraries theo kiểu Shade |
| Merge `META-INF/services` | Có `ServicesResourceTransformer` | Cần giải pháp phù hợp riêng | Dependency layout/launcher riêng, không tương đương flat shade |
| Output deployment | Một archive với class entries đã trộn | Distribution có thể có lib/ và config/ riêng | Executable Boot JAR với nested libraries/launcher |

**Shade không tự động luôn tốt hơn Assembly.** Nếu team muốn ZIP gồm `bin/`, `lib/`, `config/` để cập nhật từng library, Assembly có thể thích hợp hơn. Nếu build Spring Boot executable, Boot repackage thường giữ cấu trúc nested JAR riêng; không nên áp dụng Shade bừa lên toàn bộ starters mà không hiểu loader và metadata.

Mục tiêu bài này là **quản lý phạm vi artifact được hợp nhất bằng Shade**, không phải so sánh đầy đủ mọi mô hình đóng gói của Maven.

## 12. Hướng dẫn debug từng lớp

### 12.1. Khi ứng dụng compile thành công nhưng `java -jar` fail

**Triệu chứng:** `NoClassDefFoundError` hoặc `ClassNotFoundException`.

1. Xác định FQCN/class path trong lỗi.
2. `mvn dependency:tree` để tìm artifact cung cấp class đó.
3. Kiểm tra scope và transitive dependencies.
4. Kiểm tra `artifactSet.includes/excludes`; với whitelist, artifact transitive có thể không được match.
5. Kiểm tra `filters` có loại file `.class` không.
6. Kiểm tra relocation có đổi package/class name không.
7. Dùng `jar tf target/...jar` xác nhận entry thực sự có mặt.
8. Nếu chỉ xuất hiện khi framework load qua reflection/ServiceLoader, xem thêm transformers/minimizeJar.
9. Chạy lại JAR từ clean build và environment không có thư viện ngoài ý muốn.

### 12.2. Khi JAR quá lớn

Kiểm tra:
- có gộp những runtime dependencies không cần trong artifact cụ thể không;
- whitelist/blacklist đang quá rộng;
- dependency graph có bản trùng hoặc runtime libraries nặng;
- có packaging nhúng resources rất lớn hoặc binaries không;
- có thể chuyển một phần thành external runtime dependency với contract triển khai rõ ràng không.

`minimizeJar` có thể giảm dung lượng, nhưng **không nên bật ngay mà không chạy integration test/reflective loading test**. Khi dùng filters để bỏ files, nhớ rằng missing service resources hoặc license files có thể gây lỗi/pháp lý.

### 12.3. Khi bản shaded phát hành không đúng

Một thư viện được shaded vào main artifact nhưng published POM vẫn khai báo dependency ấy có thể làm consumers nhận duplicate code. Kiểm tra `createDependencyReducedPom`, attach mode, classifier và output association. Nếu dùng `outputFile`, đừng mặc định output được attach/deploy.

Chạy lần lượt:

```bash
mvn -version
mvn clean package
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree
jar tf target/shade-scope-lab-1.0.0.jar
```

Nếu cần soi cấu hình:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-shade-plugin:3.6.2" -Dgoal=shade -Ddetail=true
```

`help:effective-pom` cho biết POM/config sau inheritance/profiles, `help:describe` cho biết metadata plugin; chỉ `jar tf`, run/test thực tế và artifact metadata mới chứng minh nội dung đã được đóng gói đúng.

### 12.4. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `mvn package` không tạo shaded JAR | Plugin chưa có `<execution>` cho `shade` | Bind goal vào `package` |
| JAR có manifest nhưng không chạy được main | Main class bị loại do whitelist/filter hoặc tên class sai | Thêm main artifact vào includes và kiểm tra entries |
| `NoClassDefFoundError` khi chạy `java -jar` | Dependency bị artifactSet/filter loại hoặc minimize xóa class | Kiểm tra graph → selection → entries |
| `mvn test` PASS nhưng executable FAIL | Test dùng compile/test classpath, artifact runtime thiếu | Thêm smoke test `java -jar` |
| Commons Codec còn trong dependency:tree nhưng không ở JAR | Đúng: artifactSet chỉ ảnh hưởng shaded output | Không coi đó là lỗi Maven resolution |
| Dependency bị loại nhưng classpath khi deploy vẫn có nó | Runtime/container cung cấp JAR ngoài | Kiểm tra deployment classpath, POM consumer |
| Whitelist theo groupId không gộp thư viện transitive khác group | Mỗi resolved artifact được match riêng | Include runtime closure cần thiết |
| Tên classifier bị hiểu là version | Composite artifact coordinate có type/classifier, không version | Kiểm tra syntax `group:artifact:type:classifier` |
| `filters` loại signature nhưng cũng mất ServiceLoader | Filter `META-INF/**` quá rộng | Chỉ loại chính xác file signatures, merge services |
| `SignatureException`/digest mismatch | Signature files không còn phù hợp sau repackaging | Xem packaging/signing policy và filters |
| Hai library có `META-INF/services` trùng | Không có transformer phù hợp | `ServicesResourceTransformer`, test ServiceLoader |
| JAR quá nhỏ và thiếu class khi bật minimize | Reflection/dynamic reachability không được nhận diện | Tắt minimize/đặt entryPoints và test |
| JAR có class ở package mới | Relocation đổi namespace | Kiểm tra shadedPattern và bytecode |
| Published POM tải thêm dependency đã nhúng | Reduced POM bị tắt hoặc attach/publish sai | Kiểm tra `createDependencyReducedPom` |
| CI chạy nhầm thin JAR | Nhiều file jar với classifier/original | Chỉ định chính xác file artifact |
| Exclude pattern gõ sai nhưng không có hiệu lực | Pattern không match resolved artifacts | Đối chiếu GAV + type/classifier và output |
| License/NOTICE bị mất | Filter quá rộng | Giữ attribution, kiểm tra license compliance |

## 13. Bài tập tự đánh giá

**Bài tập 1 — chọn artifact.** Một project khai báo Commons Lang3 và Commons Codec, nhưng `artifactSet.includes` chỉ có project + Lang3. Vì sao Codec vẫn có trong `dependency:tree`? Vì Shade selection **không xóa dependency khỏi Maven graph**.

**Bài tập 2 — type/classifier.** Pattern `com.example:lib:tests` dùng ba vế nghĩa gì? Với cú pháp rút gọn của Shade, `tests` được hiểu là **classifier**, không phải version.

**Bài tập 3 — wildcard.** `<include>org.apache.commons:*</include>` có tự tìm và tải tất cả Commons artifacts trên Maven Central không? **Không**. Nó chỉ match artifacts đã được Maven resolve cho quá trình Shade xét.

**Bài tập 4 — transitive.** Artifact A phụ thuộc B; whitelist chỉ chứa A, không chứa B. B có chắc được gộp không? **Không**; mỗi resolved artifact được match riêng. Phải xác nhận B nằm trong tập selection hoặc runtime ngoài cung cấp.

**Bài tập 5 — archive filtering.** `<filter><artifact>*:*</artifact><excludes><exclude>META-INF/*.SF</exclude></excludes></filter>` loại gì? **Signature file entries** trong các artifact match, không loại cả Maven artifact.

**Bài tập 6 — runtime.** App sử dụng `StringUtils.reverse`, nhưng Shade loại Commons Lang3 khỏi uber JAR. Vì sao `mvn test` có thể PASS mà `java -jar` FAIL? Vì compile/test classpath có thư viện, runtime bundle không có.

**Bài tập 7 — project artifact.** Vì sao whitelist nên xét cả `com.example:shade-scope-lab`? Vì main project artifact cũng đi qua artifact selection; nếu thiếu, main class có thể không được đưa vào shaded archive.

**Bài tập 8 — transformer.** Hai JAR có các file `META-INF/services/com.example.Plugin` riêng. Nếu không merge, điều gì xảy ra? Có thể mất providers. Xem `ServicesResourceTransformer`.

**Bài tập 9 — minimized JAR.** Một class chỉ được tạo qua `Class.forName` ở runtime. Tại sao `minimizeJar=true` có rủi ro? Phân tích reachability tĩnh có thể không thấy cách dùng động.

**Bài tập 10 — published metadata.** Tại sao `createDependencyReducedPom=false` có thể phù hợp để quan sát demo executable nhưng rủi ro khi publish library? Vì POM công bố có thể khai báo lại dependency đã nhúng.

## 14. Checklist trước khi đưa Shade config vào CI

- [ ] Biết project dùng Shade vì cần **uber JAR** hay thực ra cần distribution ZIP/Boot executable.
- [ ] Đã ghim Maven Shade Plugin version và kiểm tra `shade:shade` được bind vào `package`.
- [ ] Đã phân biệt Maven dependency graph với tập artifacts được shade.
- [ ] Khi dùng whitelist, bao gồm **main project artifact** và mọi runtime dependencies cần thiết.
- [ ] Hiểu includes/excludes là tọa độ artifact, không phải file paths/version strings.
- [ ] Với transitive graph, không giả định include A tự include tất cả con của A.
- [ ] Đã kiểm tra Maven scopes và external runtime dependencies.
- [ ] Đã dùng `filters` chỉ để lọc entries cần thiết và giữ license/NOTICE/service metadata.
- [ ] Đã chọn transformers phù hợp, đặc biệt manifest và ServiceLoader khi cần.
- [ ] Không bật `minimizeJar` nếu chưa test reflection/framework paths.
- [ ] Nếu dùng relocation, đã test public API, SPI, serialization và runtime.
- [ ] Đã quyết định replace main artifact hay attach classifier, tránh deploy nhầm.
- [ ] Đã cân nhắc `createDependencyReducedPom` khi phát hành cho Maven consumers.
- [ ] Chạy `mvn clean package` và mở `jar tf` để xác nhận class có và không có.
- [ ] Có smoke test `java -jar` trên classpath/môi trường sạch, ngoài unit tests.
- [ ] Đã xem license/security policy của dependencies đóng gói, tránh nhúng thư viện không được phép.

**Kết luận:** `artifactSet` là **cửa chọn artifact đầu vào**, `filters` là **cửa chọn class/resource entry bên trong**, còn transformers, relocations và minimization điều chỉnh cách những thứ đã chọn được hợp nhất. Chỉ dựa vào `dependency:tree` hoặc `BUILD SUCCESS` không đủ: phải **đọc nội dung shaded JAR** và **chạy thật** để chắc rằng phạm vi gộp vừa đủ, không thiếu class và không mang theo dependency không mong muốn.

### Tài liệu chính thức và nguồn tham khảo

- [Maven Shade Plugin 3.6.2 — shade:shade, artifactSet, filters và các parameters](https://maven.apache.org/plugins/maven-shade-plugin/shade-mojo.html)
- [Maven Shade Plugin — Selecting Contents for Uber JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/includes-excludes.html)
- [Maven Shade Plugin — Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html)
- [Maven Shade Plugin — Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html)
- [Maven Shade Plugin — Relocating Classes](https://maven.apache.org/plugins/maven-shade-plugin/examples/class-relocation.html)
- [Maven Shade Plugin — Attaching the Shaded Artifact](https://maven.apache.org/plugins/maven-shade-plugin/examples/attached-artifact.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven Central — Commons Lang3 3.17.0](https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.17.0)
- [Maven Central — Commons Codec 1.17.1](https://central.sonatype.com/artifact/commons-codec/commons-codec/1.17.1)
