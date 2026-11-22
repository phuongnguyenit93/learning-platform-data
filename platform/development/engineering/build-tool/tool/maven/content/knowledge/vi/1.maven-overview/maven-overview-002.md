# Mô hình tư duy về Maven: POM, vòng đời, plugin, phụ thuộc và kho artifact

## 1. Bức tranh tổng thể: Maven làm gì?

Apache Maven là công cụ quản lý quá trình **build** và **phụ thuộc** của dự án, đặc biệt phổ biến với Java. Thay vì tự viết một tập lệnh riêng cho từng việc biên dịch, chạy kiểm thử, đóng gói và phát hành, ta mô tả dự án trong `pom.xml` rồi yêu cầu Maven thực hiện một **phase** của vòng đời. Maven tính mô hình dự án, giải quyết những artifact cần dùng và gọi các **goal** của plugin đã gắn vào các phase.

Năm khái niệm cần luôn tách bạch:

| Khái niệm | Trả lời câu hỏi | Vai trò |
| --- | --- | --- |
| **POM** (`pom.xml`) | Dự án là gì và cần cấu hình gì? | Mô tả danh tính, thành phần, phụ thuộc, plugin và cấu hình build. |
| **Lifecycle / phase** | Cần đi đến mốc nào trong quy trình build? | Xác định **thứ tự** các giai đoạn như `compile`, `test`, `package`. |
| **Plugin / goal** | Công việc cụ thể được thực hiện bằng gì? | Compiler biên dịch, Surefire chạy unit test, JAR plugin đóng gói... |
| **Dependency** | Mã nguồn dự án cần những thư viện nào? | Maven xây dựng đồ thị thư viện và classpath theo scope. |
| **Artifact repository** | Maven tìm và lưu gói đã được công bố ở đâu? | Kho local/remote cung cấp POM, JAR, plugin và nhận artifact phát hành. |

Luồng suy nghĩ:

```text
pom.xml (khai báo dự án, dependencies, build/plugins)
   |
   +--> Effective POM (POM hiện tại + parent + cấu hình kế thừa)
   |
   +--> Dependency resolution --> local repository <--> remote repositories
   |
   +--> mvn clean verify
           |            (clean lifecycle rồi default lifecycle đến verify)
           v
       phase theo thứ tự
           |
           v
       plugin goal được gắn vào phase
           |
           +--> compiler:compile --> target/classes
           +--> surefire:test    --> báo cáo unit test
           +--> jar:jar          --> target/<artifactId>-<version>.jar
```

**Điểm cốt lõi:** phase là *mốc thời gian* của build; goal là *hành động*; POM là *bản khai*; dependency là *đầu vào*; repository là *nơi tìm hoặc công bố artifact*. Không nên dùng năm từ này như từ đồng nghĩa.

## 2. POM: bản khai dự án, không phải tập lệnh tuần tự

POM viết tắt của **Project Object Model**. Mỗi dự án Maven có `pom.xml` tại thư mục gốc. Các trường thường gặp:

- `modelVersion`: phiên bản mô hình POM, thông dụng là `4.0.0`; **không phải** phiên bản Java hoặc Maven đang cài.
- `groupId`: nhóm/tổ chức sở hữu, ví dụ `dev.example`.
- `artifactId`: tên định danh của artifact, ví dụ `maven-mental-model`.
- `version`: phiên bản artifact, ví dụ `1.0.0` hoặc `1.0.0-SNAPSHOT`.
- `packaging`: loại đầu ra (`jar`, `war`, `pom`...), mặc định thường là `jar`. Packaging còn quyết định các **goal mặc định** gắn vào lifecycle.
- `properties`: biến cấu hình như mã hóa UTF-8, đích biên dịch Java 17.
- `dependencies`: thư viện dự án sử dụng.
- `build/plugins`: phiên bản/cấu hình plugin thực thi tác vụ build.

Một artifact thường được nhận diện bằng **tọa độ** `groupId:artifactId:version`, kèm `type/extension` và `classifier` khi cần. Ví dụ `dev.example:maven-mental-model:1.0.0` được lưu theo cấu trúc đường dẫn có dạng `dev/example/maven-mental-model/1.0.0/maven-mental-model-1.0.0.jar`. Một bản `-sources.jar` có thể sử dụng classifier `sources` và vẫn thuộc cùng nhóm tọa độ chính.

Maven áp dụng quy ước thư mục để giảm cấu hình:

```text
project/
  pom.xml
  src/
    main/
      java/          # Java production
      resources/     # tài nguyên đi kèm production
    test/
      java/          # mã kiểm thử
      resources/     # tài nguyên kiểm thử
  target/            # sản phẩm sinh ra từ build, có thể xóa/tạo lại
```

POM thực tế được Maven sử dụng là **effective POM**: kết quả sau khi kết hợp POM hiện tại với parent POM, các mặc định và cấu hình/profiles áp dụng. Lệnh `mvn help:effective-pom` giúp xem cấu hình cuối cùng; điều này hữu ích khi một plugin hoặc phiên bản xuất hiện dù không thấy khai báo ngay trong POM con.

Với nhiều module, phân biệt **inheritance** (module kế thừa `<parent>` để dùng chung cấu hình) và **aggregation** (POM tổng hợp khai `<modules>` để Maven xây các module trong một reactor). Một POM có thể làm cả hai, nhưng hai quan hệ này không tự động đồng nhất. POM tổng hợp thường dùng `<packaging>pom</packaging>` và không tự sinh JAR ứng dụng.

## 3. Lifecycle: chọn kết quả cuối, Maven chạy các phase trước đó

Maven có ba lifecycle xây sẵn: **default** (build và phân phối), **clean** (dọn đầu ra build) và **site** (tạo tài liệu site). Mỗi lifecycle gồm các phase có **thứ tự cố định**; gọi một phase sẽ thực hiện các phase đứng trước nó trong **cùng lifecycle**, trong đó chỉ những phase có goal được gắn mới tạo ra công việc.

Một số mốc quan trọng của `default`, theo thứ tự:

| Phase | Điều cần hiểu |
| --- | --- |
| `validate` | Kiểm tra mô hình dự án và những điều kiện cơ bản. |
| `compile` | Biên dịch production code; các bước chuẩn bị resource/source liên quan diễn ra trước. |
| `test` | Biên dịch và chạy unit test; mặc định với dự án JAR thường dùng Surefire. |
| `package` | Tạo gói phân phối (JAR/WAR...) theo packaging. |
| `verify` | Chạy các kiểm tra đã cấu hình đối với kết quả build, gồm integration test nếu có plugin được cấu hình phù hợp. |
| `install` | Cài artifact vào **local repository** để dự án khác trên máy tham chiếu. |
| `deploy` | Đẩy artifact tới **remote repository** đã cấu hình để chia sẻ/phát hành. |

Giữa các mốc còn nhiều phase như `process-resources`, `test-compile`, `pre-integration-test`, `integration-test` và `post-integration-test`. Không nên chạy riêng `integration-test` của một dự án có setup/teardown tích hợp: bước dọn dẹp có thể chỉ hoàn tất khi chạy đến `verify`. **Không phải mọi dự án đều tự động có integration test**; cần plugin và binding tương ứng, thường là Failsafe.

Ví dụ:

- `mvn test`: chạy chuỗi default đến `test`; chưa có nghĩa đã đóng gói JAR.
- `mvn package`: đi qua các phase trước đó, bao gồm `test`, rồi tạo gói.
- `mvn verify`: đi đến `verify`; lựa chọn phù hợp khi muốn kiểm tra build đầy đủ theo cấu hình của dự án.
- `mvn clean verify`: trước hết chạy `clean` trong **clean lifecycle**, sau đó chạy default đến `verify`. `clean` không tự xảy ra khi chỉ gọi `mvn verify`.
- `mvn install`: đi đến `install`, nên cũng chạy những phase trước; không đồng nghĩa với phát hành lên server.
- `mvn deploy`: chỉ sử dụng khi có cấu hình/điều kiện phát hành phù hợp, vì nó đưa artifact lên kho từ xa.

Nếu một unit test thất bại, `mvn package` thông thường dừng trước khi tạo artifact thành công. Không suy luận rằng đã có file trong `target/` thì build hiện tại đã PASS: đó có thể là đầu ra từ lần chạy trước.

## 4. Plugin và goal: ai thực sự làm việc?

Maven core **điều phối**, còn plugin cung cấp các công việc cụ thể. Một plugin có thể có nhiều goal: `maven-compiler-plugin` có `compiler:compile` và `compiler:testCompile`; `maven-surefire-plugin` có `surefire:test`; `maven-jar-plugin` có `jar:jar`.

Đối với `<packaging>jar</packaging>`, Maven có các binding mặc định tiêu biểu:

| Phase | Goal mặc định tiêu biểu |
| --- | --- |
| `process-resources` | `resources:resources` |
| `compile` | `compiler:compile` |
| `process-test-resources` | `resources:testResources` |
| `test-compile` | `compiler:testCompile` |
| `test` | `surefire:test` |
| `package` | `jar:jar` |

Như vậy, `mvn package` **không phải tên một plugin**: đó là yêu cầu đi đến phase `package`, kích hoạt nhiều goal trong suốt quá trình. Ngược lại `mvn dependency:tree` gọi trực tiếp goal của Maven Dependency Plugin; bản thân lời gọi goal này không có nghĩa Maven sẽ tự chạy đầy đủ `compile → test → package`.

Trong `pom.xml`, `<build><plugins>` dùng để khai báo và cấu hình plugin trực tiếp. `<executions>` có thể ràng buộc goal vào phase, thêm task như tạo mã nguồn hoặc kiểm tra chất lượng. Chọn đúng thời điểm thực thi quan trọng hơn chỉ thêm tên plugin vào POM.

Phân biệt:

- `<dependencies>`: dependency mà **mã nguồn ứng dụng/kiểm thử** sử dụng.
- `<build><plugins>`: công cụ mà **Maven dùng để build** dự án. Plugin cũng được tải về từ kho artifact nhưng có classpath và cơ chế giải quyết riêng.
- `<dependencyManagement>`: quản lý phiên bản/scope cho dependency khi chúng được khai báo hoặc đi vào đồ thị tương ứng; chỉ khai báo trong đây **chưa khiến thư viện tự xuất hiện** ở classpath.
- `<pluginManagement>`: quản lý phiên bản/cấu hình plugin để áp dụng khi plugin được dùng, kể cả qua binding mặc định; chỉ đặt một plugin tùy ý vào đây **không tự gắn goal mới** vào lifecycle.

Với dự án nhiều module, tập trung phiên bản plugin và dependency ở parent/BOM giúp các module nhất quán, nhưng phải hiểu sự khác nhau giữa **quản lý cấu hình** và **kích hoạt sử dụng**.

## 5. Dependency: đồ thị thư viện, scope và xung đột phiên bản

Khi khai `<dependency>`, bạn nêu artifact mà code cần. Maven đọc POM của artifact ấy và có thể kéo thêm **transitive dependencies**. Ví dụ ứng dụng A phụ thuộc B, B phụ thuộc C: A có thể dùng C trong classpath phù hợp mà không khai C trực tiếp. Tuy nhiên nếu source A **trực tiếp import lớp của C**, nên khai C trực tiếp để không phụ thuộc tình cờ vào cấu trúc dependency của B.

**Scope** trả lời thư viện có mặt ở giai đoạn nào:

| Scope | Compile production | Runtime | Test | Trường hợp phổ biến |
| --- | --- | --- | --- | --- |
| `compile` (mặc định) | Có | Có | Có | Thư viện app cần biên dịch và chạy. |
| `provided` | Có | Không trong runtime classpath do Maven tạo | Có | API được container/JDK cung cấp khi chạy. |
| `runtime` | Không | Có | Có | JDBC driver hoặc thư viện chỉ dùng khi chạy. |
| `test` | Không | Không | Có | JUnit, Mockito. |
| `system` | Có, qua đường dẫn file tường minh | Có theo khai báo | Có | Trường hợp cũ; nên tránh vì phụ thuộc máy cụ thể. |
| `import` | Không là classpath scope | Không | Không | Chỉ dùng cho POM kiểu `pom` bên trong `dependencyManagement`, thường để nhập BOM. |

Bảng trên nói về classpath trực tiếp của dự án; việc truyền dependency qua nhiều tầng còn chịu quy tắc scope transitive. `provided` và `test` không được truyền tiếp như `compile` thông thường.

Khi đồ thị kéo **hai phiên bản của cùng artifact**, Maven có cơ chế *dependency mediation*: thường chọn định nghĩa **gần dự án nhất** trong cây; nếu cùng độ sâu thì khai báo xuất hiện trước thắng. Bản khai dependency trực tiếp, `dependencyManagement` và BOM có thể giúp kiểm soát kết quả. Không nên tin rằng Maven luôn chọn bản **mới nhất**.

Các công cụ xử lý đồ thị:

- `mvn dependency:tree`: xem dependency trực tiếp và transitive, scope/phiên bản đã chọn.
- `<exclusions>`: loại bỏ một dependency transitive khỏi một đường khai báo cụ thể; cần hiểu đường khác có thể vẫn đưa nó vào.
- `<optional>true</optional>`: với thư viện do bạn phát hành, cho biết dependency đó không mặc định truyền tới người dùng thư viện.
- **BOM**: POM dùng `dependencyManagement` để thống nhất phiên bản cả nhóm artifact; nhập bằng dependency có `<type>pom</type>` và `<scope>import</scope>` bên trong `dependencyManagement`.

Lưu ý rằng `dependencyManagement` của dự án quản lý dependency dự án, **không tự điều khiển dependency nội bộ của Maven plugin**. Để điều chỉnh plugin phải cấu hình đúng plugin và cơ chế quản lý plugin tương ứng.

## 6. Repository: nơi Maven tìm plugin và dependency, nơi nhận bản phát hành

Artifact không chỉ là file JAR. Maven repository có thể chứa **POM, JAR, WAR, plugin và metadata**. Có hai loại chính:

1. **Local repository**: thường ở `~/.m2/repository` trên máy chạy Maven. Đây là cache các artifact đã tải, đồng thời là nơi chứa artifact cài bằng `mvn install`. Nó **khác** thư mục `target/`: `target/` là đầu ra build trong một project, còn local repository là kho dùng chung trên máy.
2. **Remote repository**: Maven Central hoặc repository nội bộ (Nexus, Artifactory...), nơi Maven tải artifact. `mvn deploy` đẩy artifact dự án lên remote repository được cấu hình và được cấp quyền.

Mô hình đơn giản khi cần thư viện `group:lib:1.2.3`:

```text
dependency hoặc build plugin cần artifact
        |
        v
Maven kiểm tra local repository và chính sách cập nhật
        |
        +-- đã có bản phù hợp --> sử dụng
        |
        +-- cần tải/cập nhật --> remote repository / mirror
                                     |
                                     v
                            tải POM + artifact + metadata cần thiết
                                     |
                                     v
                            lưu vào local repository
```

Các điểm cấu hình dễ lẫn:

- `<repositories>` trong POM mô tả nơi tải **project dependencies**; `<pluginRepositories>` mô tả nơi tìm **build plugins**.
- `~/.m2/settings.xml` có thể chứa cấu hình ở cấp máy/người dùng: mirror, proxy, servers/credentials, profiles. Không đưa mật khẩu vào POM của source repository.
- `<distributionManagement>` trong POM có thể khai địa chỉ kho nhận bản `deploy`; chỉ khai `<repositories>` không đồng nghĩa đã thiết lập nơi upload.
- **Mirror** trong `settings.xml` có thể thay đổi endpoint thực tế của những repository được khai; công ty thường dùng repository manager để kiểm soát và cache artifact.
- Bản `1.0.0-SNAPSHOT` thường là bản phát triển có thể được cập nhật theo metadata/chính sách; bản release như `1.0.0` nên được coi là bất biến. Muốn build lặp lại đáng tin, pin phiên bản rõ ràng, tránh dùng version dạng thay đổi tùy ý.

Lệnh hữu ích: `mvn -o verify` chạy **offline** (chỉ thành công nếu các artifact, plugin và metadata cần thiết đã có); `mvn -U verify` yêu cầu Maven kiểm tra cập nhật snapshot/release bị thiếu theo chính sách phù hợp. Không dùng `-U` như giải pháp chung cho mọi lỗi, cũng không vội xóa cả `~/.m2/repository` khi chỉ một artifact có vấn đề.

## 7. Ví dụ thực hành Java 17: một POM kết nối cả năm mảnh ghép

Yêu cầu: JDK 17+, một bản Maven hoạt động được (`mvn -version`), kết nối repository trong lần build đầu tiên. Tạo ba file:

```text
maven-mental-model/
  pom.xml
  src/main/java/demo/App.java
  src/test/java/demo/AppTest.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>maven-mental-model</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
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
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`maven.compiler.release=17` bảo compiler nhắm đến API và bytecode Java 17 (cần JDK phù hợp). Plugin/compiler và plugin/Surefire được pin phiên bản để tránh phụ thuộc tình cờ vào binding/plugin version mặc định. `junit-jupiter` được khai là `test`: có khi biên dịch/chạy test, không phải thư viện runtime của ứng dụng. Vì `packaging=jar`, Maven cũng tự gắn goal đóng gói JAR vào phase `package`.

**File `src/main/java/demo/App.java`:**

```java
package demo;

public final class App {
    private App() {
    }

    public static String message() {
        return "Xin chao Maven";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

**File `src/test/java/demo/AppTest.java`:**

```java
package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Xin chao Maven", App.message());
    }
}
```

Từ thư mục chứa `pom.xml`, chạy:

```bash
mvn clean verify
java -cp target/maven-mental-model-1.0.0.jar demo.App
```

Khi build thành công, lệnh `java` ở trên in ra **chính xác**:

```text
Xin chao Maven
```

Giải thích từng mảnh ghép:

1. Maven đọc `pom.xml` để biết tọa độ dự án, Java 17, JUnit test dependency và plugin cần dùng.
2. Maven tải plugin/JUnit (và dependency transitive của chúng) từ repository nếu local chưa có.
3. `clean` dọn `target/` cũ. Trong default lifecycle, Compiler Plugin biên dịch `App.java`, biên dịch `AppTest.java`; Surefire chạy test theo JUnit Platform. Nếu assertion thất bại, build thất bại.
4. Goal `jar:jar`, gắn theo packaging `jar`, tạo `target/maven-mental-model-1.0.0.jar`. Phase `verify` hoàn tất các kiểm tra đã cấu hình.
5. `java -cp ... demo.App` chạy trực tiếp lớp `demo.App` đã đóng gói. Đây là **JAR thường**: ví dụ chưa khai Main-Class trong manifest, nên lệnh `java -jar ...` **không phải** lệnh chạy đúng trong trường hợp này. JAR thường cũng **không tự nhúng** các dependency runtime của ứng dụng.

Sau đó có thể chạy `mvn install` để lưu artifact này trong local repository tại đường dẫn tương ứng `dev/example/maven-mental-model/1.0.0/`. Lệnh đó không tự upload lên Maven Central.

## 8. Cách đọc một build Maven từ đầu đến cuối

Khi mở một dự án lạ, hãy làm theo thứ tự tư duy sau:

1. **Xác định POM và tọa độ:** tìm `pom.xml`, `groupId/artifactId/version`, `packaging`, parent và modules. Kiểm tra bạn đang đứng ở root dự án hay một module con.
2. **Xác định đích build:** CI chạy `verify`, `package` hay `deploy`? Gọi phase cuối nào, có gọi `clean` trước không?
3. **Ánh xạ phase → goal:** xem packaging và các plugin/`executions` đang gắn goal vào phase. Khi gặp lỗi test, xác định nó đến từ Surefire hay Failsafe; khi lỗi compile, xem Compiler Plugin/JDK.
4. **Đọc dependency graph:** xem `<dependencies>`, scope, `dependencyManagement`/BOM rồi kiểm tra kết quả thực tế bằng `mvn dependency:tree`.
5. **Kiểm tra nơi lấy artifact:** kiểm tra `settings.xml`, mirror, repository nội bộ, cache local và khả năng truy cập. Phân biệt lỗi tải plugin với lỗi tải dependency ứng dụng.

Công cụ chẩn đoán thường dùng:

| Lệnh | Dùng khi nào |
| --- | --- |
| `mvn -version` | Xác minh Maven đang dùng JDK nào, phiên bản nào. |
| `mvn help:effective-pom` | Tìm cấu hình thực tế sau kế thừa/management/profile. |
| `mvn dependency:tree` | Xem dependency transitive và phiên bản/scope được chọn. |
| `mvn help:active-profiles` | Kiểm tra profile đang kích hoạt. |
| `mvn -X verify` | Lấy log debug khi lỗi khó giải thích. |
| `mvn -o verify` | Kiểm tra build offline với cache hiện có. |

Các goal `help:*` và `dependency:*` cũng là goal của plugin; khi chạy lần đầu Maven có thể phải tải plugin tương ứng.

## 9. Những nhầm lẫn thường gặp

**“`mvn package` chỉ gọi plugin đóng gói.”** Sai. Maven thực hiện cả chuỗi phase trước `package` và các goal được gắn, gồm compile và test trong cấu hình JAR thông thường.

**“Khai dependency là JAR đã nằm trong file JAR ứng dụng.”** Sai. Khai dependency ảnh hưởng classpath khi biên dịch/chạy theo scope, còn việc tạo *fat/uber JAR* phải cấu hình công cụ đóng gói tương ứng (ví dụ Shade hoặc Spring Boot plugin, tùy loại dự án).

**“`install` nghĩa là đưa bản build lên server.”** Sai. `install` đưa artifact vào local repository; `deploy` dùng cho remote repository.

**“Plugin và dependency đều là một loại khai báo.”** Sai. Cả hai có thể được tải dưới dạng artifact, nhưng phục vụ hai classpath và mục đích khác nhau: code của dự án và quá trình build.

**“`dependencyManagement` tự thêm mọi thư viện, `pluginManagement` tự chạy mọi plugin.”** Sai. Chúng chủ yếu quản lý phiên bản/cấu hình cho phần được dùng; cần xem dependency thực sự hoặc binding/goal thực sự.

**“Thiếu dependency thì xóa toàn bộ `.m2`.”** Đây là cách sửa quá rộng. Trước tiên kiểm tra tọa độ/phiên bản, scope, mirror, credentials, network, `settings.xml` và artifact lỗi; nếu cache hỏng chỉ xử lý đúng đường dẫn cần thiết.

**“Build chạy trên máy tôi là sẽ chạy ở mọi máy.”** Chưa chắc. JDK, biến môi trường, mirror, profile, plugin version, snapshot và tài nguyên ngoài có thể khác. Muốn build ổn định, pin phiên bản, dùng Maven Wrapper nếu dự án cung cấp, đưa cấu hình chia sẻ vào POM/parent hợp lý, giữ credential ở kênh cấu hình an toàn.

## 10. Tự kiểm tra mô hình tư duy

- Vì sao `mvn test` thường chưa tạo JAR, trong khi `mvn package` có thể tạo? Vì chúng dừng ở hai phase khác nhau của default lifecycle; goal đóng gói thường gắn ở `package`.
- Một thư viện chỉ dùng trong test nên có scope nào? `test`, vì không cần nằm trong runtime classpath của app.
- Vì sao đổi parent POM có thể làm plugin hoạt động khác dù POM con không sửa? Vì effective POM chịu ảnh hưởng cấu hình kế thừa và plugin management.
- Một module đã `mvn install` thành công có tự hiện trên máy đồng đội không? Không; local repository của mỗi máy khác nhau, muốn chia sẻ cần remote repository (hoặc phương thức phân phối khác).
- Nếu muốn biết vì sao phiên bản thư viện X xuất hiện, nên bắt đầu ở đâu? `mvn dependency:tree`, sau đó xem khai báo trực tiếp, `dependencyManagement`/BOM và các đường transitive.

**Câu nhớ nhanh:** *POM khai báo dự án; lifecycle định thứ tự; plugin goal làm việc; dependency cung cấp thư viện; repository lưu và phân phối artifact.* Đọc một build Maven bằng cách nối đúng năm mắt xích này.

## Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Apache Maven Compiler Plugin — Setting the release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Surefire Plugin — Using JUnit 5 Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
