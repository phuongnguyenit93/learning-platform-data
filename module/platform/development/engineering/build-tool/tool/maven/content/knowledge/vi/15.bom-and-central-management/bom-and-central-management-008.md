# Thiết kế BOM nội bộ cho các thư viện cần đồng bộ phiên bản trong Maven

Khi một tổ chức phát triển nhiều thư viện Java dùng chung — ví dụ thư viện logging, metrics, HTTP client, security hoặc model — các ứng dụng có thể vô tình sử dụng những tập phiên bản không tương thích. Một dự án dùng `text-utils:1.4.0`, dự án khác dùng `text-utils:1.2.0`; cùng lúc đó cả hai có thể phụ thuộc những phiên bản khác nhau của `metrics-api` và thư viện bắc cầu.

**BOM (Bill of Materials) của Maven** là một **POM artifact chuyên dùng để quản lý tập phiên bản dependency**. Tổ chức phát hành một BOM nội bộ, ví dụ `vn.example.platform:company-libraries-bom:1.0.0`. Các ứng dụng chỉ cần **import BOM trong `dependencyManagement`** rồi khai báo những thư viện chúng thực sự dùng mà không lặp lại version. Nhờ đó, nhiều thư viện được nâng cấp **theo một bộ version đã được kiểm chứng**.

Bài học này hướng dẫn thiết kế BOM nội bộ từ đầu: phạm vi quản lý, cấu trúc XML, cách consumer import, thứ tự ưu tiên, ví dụ Java 17 chạy được, phát hành và nâng cấp BOM, những giới hạn cần tránh và cách kiểm tra trên Maven.

## 1. BOM là gì, và nó giải quyết vấn đề nào?

Trong Maven 3.9.x, BOM thông dụng là một project có:

- `<packaging>pom</packaging>` và `<modelVersion>4.0.0</modelVersion>`;
- các khai báo phiên bản được quản lý trong `<dependencyManagement><dependencies>`;
- tọa độ Maven độc lập `groupId:artifactId:version` để có thể publish như một POM artifact;
- các consumer nhập danh sách managed dependencies bằng dependency `type=pom` và `scope=import`.

Ví dụ một bộ phiên bản được BOM quản lý:

| Thư viện | Tọa độ artifact | Version trong BOM 1.0.0 |
| --- | --- | --- |
| Text utilities | `vn.example.libs:text-utils` | `1.4.0` |
| Metrics API | `vn.example.libs:metrics-api` | `2.2.0` |
| HTTP adapter | `vn.example.libs:http-adapter` | `3.1.2` |
| Authentication client | `vn.example.libs:auth-client` | `1.7.0` |

Đây là **bộ ví dụ nội bộ**, không phải các artifact được cam kết tồn tại trên Maven Central. BOM version `1.0.0` định danh **một tập version được tổ chức duyệt**; các thư viện bên trong **không bắt buộc** cùng version với BOM hoặc cùng version với nhau.

BOM giúp:

1. **Tạo một nguồn quản lý version:** version của thư viện dùng chung được ghi ở một nơi có review và release.
2. **Giảm lệch giữa các dự án:** nhiều application import cùng một BOM release thường nhận cùng tập version managed cho những artifact tương ứng.
3. **Nâng cấp theo bộ đã kiểm thử:** thay `company-libraries-bom:1.0.0` bằng `1.1.0` có thể nâng đồng thời các dependency thuộc BOM.
4. **Tách chính sách version khỏi quan hệ parent:** mỗi ứng dụng có thể giữ parent POM riêng (chẳng hạn Spring Boot parent) nhưng import BOM chung.
5. **Hỗ trợ audit và rollback:** BOM version được pin giúp truy vết khi một thư viện thay đổi và cho phép quay lại tập version cũ.

**BOM không phải cơ chế tải hoặc thêm tất cả thư viện vào ứng dụng.** Nó chỉ quản lý version/metadata cho dependency khi dependency được khai báo hoặc được đưa vào dependency graph.

## 2. Phân biệt BOM với parent POM, aggregator và SBOM

| Khái niệm | Mục đích | Quan hệ với consumer |
| --- | --- | --- |
| **Maven BOM** | Quản lý versions của một bộ dependencies | Consumer `import` từ `dependencyManagement` |
| **Parent POM** | Chia sẻ mô hình build: properties, dependency/plugin management, cấu hình và execution theo inheritance | Consumer dùng một thẻ `<parent>` trực tiếp |
| **Aggregator POM** | Xây dựng nhiều module trong một reactor | Aggregator khai báo `<modules>`, không tự tạo inheritance |
| **SBOM — Software Bill of Materials** | Thống kê thành phần thực sự có trong sản phẩm phục vụ kiểm kê/bảo mật | Thường xuất ra JSON/XML theo CycloneDX hoặc SPDX, không phải Maven BOM import |

Một Maven project có thể là parent và aggregator cùng lúc, hoặc có `dependencyManagement` vừa được kế thừa vừa được consumer import. Nhưng trong tổ chức, tốt nhất phân biệt rõ vai trò từng artifact.

**Maven chỉ cho một `<parent>` trực tiếp**, trong khi consumer có thể import BOM trong `dependencyManagement`. Vì vậy BOM hữu ích cho đội có nhiều kiểu ứng dụng hoặc nhiều parent khác nhau.

Maven BOM cũng **khác SBOM**: BOM quản lý một bộ version có thể được dùng; SBOM ghi lại những thành phần cụ thể của một bản phần mềm thực tế. Nếu cần báo cáo lỗ hổng hoặc giấy phép, vẫn phải phân tích dependency graph/artifact đã build và phát hành SBOM phù hợp.

## 3. DependencyManagement không phải Dependencies

Đây là nguyên tắc quan trọng nhất khi thiết kế BOM.

### 3.1. Quản lý version trong BOM

Đoạn XML trong POM BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.libs</groupId>
            <artifactId>text-utils</artifactId>
            <version>1.4.0</version>
        </dependency>
        <dependency>
            <groupId>vn.example.libs</groupId>
            <artifactId>metrics-api</artifactId>
            <version>2.2.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Các mục này xác định **version được ưu tiên khi artifact tương ứng có mặt trong dependency graph**. Bản thân chúng **không tự thêm `text-utils` hay `metrics-api`** vào ứng dụng.

### 3.2. Consumer tự chọn thư viện cần dùng

Một consumer đã import BOM có thể chỉ khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>vn.example.libs</groupId>
        <artifactId>text-utils</artifactId>
    </dependency>
</dependencies>
```

Consumer này nhận `text-utils:1.4.0` từ BOM. Nó **không tự nhận `metrics-api`** chỉ vì BOM quản lý phiên bản của thư viện đó.

Nếu consumer muốn dùng cả hai, thêm cả hai mục vào `<dependencies>`; Maven xác định version từ BOM.

### 3.3. BOM có thể quản lý dependency bắc cầu

Giả sử consumer phụ thuộc `http-adapter` và dependency POM của `http-adapter` yêu cầu `metrics-api`. BOM có thể điều khiển version của `metrics-api` khi nó xuất hiện trong dependency graph của consumer. Đó là điểm hữu ích của dependency management so với việc dựa hoàn toàn vào quy tắc nearest definition.

Tuy nhiên, việc ép version không bảo đảm binary compatibility. Nếu `http-adapter` chỉ tương thích `metrics-api:1.x` mà BOM chọn `2.2.0`, ứng dụng vẫn có thể gặp `NoSuchMethodError` hoặc sai hành vi. Do đó BOM là **một tập version đã được kiểm chứng**, không phải quy tắc “chọn phiên bản cao nhất”.

**Giới hạn:** `dependencyManagement` cho dependencies của project **không tự quản lý dependency nội bộ của các Maven plugins**. Muốn chuẩn hóa plugin versions, dùng `<build><pluginManagement>` trong POM/parent hoặc chính sách build riêng.

## 4. Thiết kế phạm vi và nguyên tắc quản trị một BOM nội bộ

Trước khi viết XML, tổ chức nên xác định **BOM này có trách nhiệm với bộ nào**.

### 4.1. Chọn một ranh giới hợp lý

Một BOM tốt thường quản lý những thư viện có vòng đời tương thích hoặc thuộc cùng một platform:

- `company-core-bom`: thư viện dùng chung như logging bridge, metrics contracts, tracing facade.
- `company-service-bom`: tập dependency đã được test cùng cho các service.
- `company-data-bom`: clients/serializers và connectors của nền tảng dữ liệu.
- `company-java17-bom`: bộ phiên bản dành cho runtime/JDK 17 khi tổ chức vẫn duy trì phiên bản khác cho Java 21.

Đây là **ví dụ tên**, không nhất thiết tổ chức phải chia thành bốn BOM. Tránh “BOM duy nhất cho mọi thứ” nếu thư viện dùng cho Android, desktop, Spring Boot, Micronaut và backend có nhu cầu tương thích hoàn toàn khác nhau.

Một BOM quá rộng khiến các thay đổi nhỏ gây đợt kiểm thử lớn; BOM quá vụn tạo nhiều imports và tranh chấp thứ tự ưu tiên. Chọn phạm vi dựa trên **ma trận tương thích và chủ sở hữu**, không chỉ dựa vào cấu trúc team.

### 4.2. Chỉ quản lý artifact thực sự cần thiết

Với các thư viện cùng nền tảng, quản lý rõ groupId, artifactId, version và **type/classifier** khi cần. Chẳng hạn test fixture có classifier có thể là artifact identity khác với JAR chính; việc quản lý version phải xét type/classifier thực tế.

Các quyết định cần đưa ra:

- **Internal-only hay cả third-party?** BOM có thể quản lý cả dependency bên ngoài nếu đó là một phần của platform được kiểm chứng. Không nên copy toàn bộ ecosystem chỉ vì thấy trong `dependency:tree`.
- **Version release hay snapshot?** Đối với BOM được dùng ở production, ưu tiên các release version bất biến; snapshot phù hợp hơn với giai đoạn thử nghiệm có kiểm soát.
- **Tương thích JDK?** Ghi rõ JDK tối thiểu, phiên bản framework và môi trường đã chạy test.
- **Quản lý scope?** Ưu tiên để consumer tự chọn `test`, `runtime`, `provided` nếu có thể; đừng áp scope tùy ý cho tất cả.
- **Nguồn artifacts?** Các thư viện nội bộ và BOM cần được publish vào repository manager Maven được cấp quyền.

### 4.3. Đừng dùng BOM để ép mọi ứng dụng kéo mọi dependency

Một BOM thuần thường chỉ có `dependencyManagement`. Đưa hàng chục thư viện vào `<dependencies>` của một parent chung có thể làm tất cả child nhận các dependencies không cần thiết, tăng kích thước classpath, rủi ro license/CVE và xung đột.

Kết hợp đúng là **BOM cung cấp version; consumer chọn dependency**, không phải BOM đóng vai “starter” kéo mọi thư viện.

## 5. POM BOM nội bộ đầy đủ trên Maven 3.9.x

Giả sử doanh nghiệp sở hữu hai Java library:

- `vn.example.libs:text-utils:1.4.0`;
- `vn.example.libs:metrics-api:2.2.0`.

BOM sẽ được publish dưới tọa độ:

```text
vn.example.platform:company-libraries-bom:pom:1.0.0
```

File `company-libraries-bom/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.platform</groupId>
    <artifactId>company-libraries-bom</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <name>Company Libraries BOM</name>
    <description>Verified internal dependency versions</description>

    <properties>
        <text-utils.version>1.4.0</text-utils.version>
        <metrics-api.version>2.2.0</metrics-api.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>vn.example.libs</groupId>
                <artifactId>text-utils</artifactId>
                <version>${text-utils.version}</version>
            </dependency>
            <dependency>
                <groupId>vn.example.libs</groupId>
                <artifactId>metrics-api</artifactId>
                <version>${metrics-api.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

**Phân tích cấu trúc:**

- `packaging=pom` giúp Maven 3.x coi đây là một POM artifact, không phải thư viện JAR.
- `groupId/artifactId/version` định danh BOM. **BOM version 1.0.0 không buộc các library cùng version 1.0.0.**
- `properties` nội bộ giúp người quản trị BOM đọc và nâng version rõ ràng.
- `dependencyManagement` chỉ ghi các phiên bản quản lý. Nó không có `<modules>` và không cần chứa mã Java.
- Khi consumer **import** BOM, Maven nhập tập managed dependencies từ BOM. Consumer không nên mặc định rằng có thể sửa `text-utils.version` trong POM của mình để thay thế mọi chỗ tham chiếu đã được nội suy trong BOM import; để override an toàn, khai báo managed dependency rõ tại consumer hoặc phát hành BOM phù hợp.

Đối với Maven 4, Apache Maven đã giới thiệu thêm **packaging `bom`** khi dùng model POM mới; bài này cố ý dùng **`packaging=pom` và model 4.0.0** vì đó là mẫu tương thích rộng với Maven 3.x. Không đổi sang `<packaging>bom</packaging>` trong ví dụ chạy bằng Maven 3.9.x.

## 6. Consumer import BOM và khai báo dependencies không có version

Trong POM của một application riêng, thêm BOM **đúng chỗ**:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.platform</groupId>
            <artifactId>company-libraries-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

BOM import **chỉ hợp lệ theo cơ chế này trong `dependencyManagement`**, với `type=pom` và `scope=import`. Không đặt BOM vào `<dependencies>` thường rồi kỳ vọng Maven dùng nó để quản lý phiên bản.

Sau import, application chọn dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>vn.example.libs</groupId>
        <artifactId>text-utils</artifactId>
    </dependency>
    <dependency>
        <groupId>vn.example.libs</groupId>
        <artifactId>metrics-api</artifactId>
    </dependency>
</dependencies>
```

Không có `<version>` tại hai dependencies ở đây là **có chủ ý** vì BOM đã quản lý chúng. Nếu quên import BOM và không có parent/management khác cung cấp version, Maven có thể báo lỗi thiếu version cho dependency.

**Cơ chế không đổi source Java**: mã Java vẫn import API của thư viện theo package/class. BOM không tạo class mới, không sinh JAR runtime và không thay thế repository manager có đủ artifacts.

## 7. Thực hành hoàn chỉnh Java 17: hai thư viện và một application

Ví dụ này dùng toàn bộ **thư viện tự viết**, tránh dependency vào hệ sinh thái giả định. Ta cài hai JAR vào local Maven repository, cài BOM rồi build application theo versions do BOM quản lý.

### 7.1. Cây thư mục

```text
bom-lab/
├── company-libraries-bom/
│   └── pom.xml
├── text-utils/
│   ├── pom.xml
│   └── src/main/java/vn/example/libs/text/TextUtil.java
├── metrics-api/
│   ├── pom.xml
│   └── src/main/java/vn/example/libs/metrics/MetricCode.java
└── order-service/
    ├── pom.xml
    └── src/main/java/vn/example/app/Main.java
```

Cả bốn thư mục là **các Maven project độc lập** trong ví dụ. Không tạo root aggregator bắt buộc, nhờ vậy tránh vòng phụ thuộc/repository timing khi một reactor cố import BOM nằm trong module khác chưa được cài/publish.

File BOM chính là `company-libraries-bom/pom.xml` ở mục 5.

### 7.2. Thư viện text-utils:1.4.0

File `text-utils/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example.libs</groupId>
    <artifactId>text-utils</artifactId>
    <version>1.4.0</version>
    <packaging>jar</packaging>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `text-utils/src/main/java/vn/example/libs/text/TextUtil.java`:

```java
package vn.example.libs.text;

import java.util.Locale;

public final class TextUtil {
    private TextUtil() {
    }

    public static String upper(String value) {
        return value.toUpperCase(Locale.ROOT);
    }
}
```

`Locale.ROOT` giúp chuyển chữ hoa ổn định cho chuỗi tiếng Anh minh họa, không phụ thuộc locale máy chạy.

### 7.3. Thư viện metrics-api:2.2.0

File `metrics-api/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example.libs</groupId>
    <artifactId>metrics-api</artifactId>
    <version>2.2.0</version>
    <packaging>jar</packaging>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `metrics-api/src/main/java/vn/example/libs/metrics/MetricCode.java`:

```java
package vn.example.libs.metrics;

public final class MetricCode {
    private MetricCode() {
    }

    public static String value() {
        return "MTR-2.2";
    }
}
```

Version `2.2.0` trong POM là tọa độ JAR. Chuỗi `"MTR-2.2"` chỉ là dữ liệu do mã Java trả về cho bài tập, không phải cơ chế Maven tự chèn số phiên bản.

### 7.4. Consumer application dùng BOM

File `order-service/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example.app</groupId>
    <artifactId>order-service</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>vn.example.platform</groupId>
                <artifactId>company-libraries-bom</artifactId>
                <version>1.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>vn.example.libs</groupId>
            <artifactId>text-utils</artifactId>
        </dependency>
        <dependency>
            <groupId>vn.example.libs</groupId>
            <artifactId>metrics-api</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Lưu ý quan trọng:

- `order-service` **không có parent là BOM** và không có version của `text-utils`/`metrics-api` trong `<dependencies>`.
- Version application `1.0.0` khác khái niệm với version BOM `1.0.0`, dù ví dụ này trùng số. Thay BOM không tự thay version ứng dụng.
- Plugin Compiler vẫn được cấu hình độc lập. BOM không tự quản lý plugin versions.
- Hai thư viện đã build/được resolve là dependency của ứng dụng; BOM không được add như một runtime JAR.

File `order-service/src/main/java/vn/example/app/Main.java`:

```java
package vn.example.app;

import vn.example.libs.text.TextUtil;
import vn.example.libs.metrics.MetricCode;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(TextUtil.upper("service=ready"));
        System.out.println("METRIC=" + MetricCode.value());
    }
}
```

### 7.5. Build theo đúng thứ tự

Đứng trong thư mục `bom-lab`. Cần **JDK 17+**, Maven 3.9.x tương thích và quyền tải Maven build plugins cho lần chạy đầu.

```bash
java -version
mvn --version

# Cài hai library artifacts vào ~/.m2/repository
mvn -B -f text-utils/pom.xml clean install
mvn -B -f metrics-api/pom.xml clean install

# Cài BOM POM artifact; không tạo JAR cho BOM
mvn -B -f company-libraries-bom/pom.xml install

# Consumer import BOM và resolve hai library versions
mvn -B -f order-service/pom.xml clean package
```

Thứ tự cài libraries và BOM trên đây chỉ là **một trình tự dễ hiểu**. Về mặt model, BOM POM thuần có thể cài trước libraries; điều quan trọng là trước khi consumer build, BOM và những artifacts nó cần phải resolve được. Nếu chạy từ máy sạch không mạng, chưa có plugin trong local repository thì `clean install` vẫn có thể thất bại.

Khi chạy CI nhiều repositories, cần publish đúng artifact trước khi consumer lấy từ remote repository. `mvn install` ở trên **chỉ cài vào local repository của máy**, chưa đưa gì lên máy của developer khác hoặc Maven repository manager công ty.

### 7.6. Chạy Java và kiểm tra stdout chính xác

Bản JAR `order-service` mặc định là **JAR thường**, không nhúng hai thư viện nội bộ và không khai báo `Main-Class` trong manifest. Để chạy, đặt **cả ba JAR** vào classpath.

Trên Linux/macOS, từ `bom-lab`:

```bash
java -cp "order-service/target/order-service-1.0.0.jar:text-utils/target/text-utils-1.4.0.jar:metrics-api/target/metrics-api-2.2.0.jar" vn.example.app.Main
```

Trên Windows PowerShell, classpath ngăn cách bằng dấu chấm phẩy:

```powershell
java.exe -cp "order-service/target/order-service-1.0.0.jar;text-utils/target/text-utils-1.4.0.jar;metrics-api/target/metrics-api-2.2.0.jar" vn.example.app.Main
```

**Stdout chính xác của Java program** (không phải Maven build log):

```text
SERVICE=READY
METRIC=MTR-2.2
```

Đây là đầu ra của hai class do ta tự viết và xây dựng theo BOM. Nếu bỏ các library JAR khỏi classpath, chương trình có thể thiếu class khi chạy. Điều này không có nghĩa BOM bị import sai: **BOM không biến JAR thông thường thành fat JAR**.

### 7.7. Xác minh version thật Maven đã resolve

```bash
mvn -f order-service/pom.xml dependency:tree -Dincludes=vn.example.libs
mvn -f order-service/pom.xml help:effective-pom -Doutput=target/effective-pom.xml
```

Các goal ở đây dùng **Maven Dependency Plugin** và **Maven Help Plugin**. Chúng có thể cần tải plugin lần đầu và in log khác nhau theo phiên bản; không dùng log cố định làm bằng chứng.

Điểm cần tìm trong tree:

```text
vn.example.libs:text-utils:jar:1.4.0:compile
vn.example.libs:metrics-api:jar:2.2.0:compile
```

Đây là **hai node mong đợi**, không phải toàn bộ output Maven. Trong effective POM, mục management nhập từ BOM phải cung cấp versions như trên, còn khai báo dependency hiệu lực dùng chúng. Đừng kết luận chỉ từ các JAR đã có trong `~/.m2/repository`: local repository có thể lưu nhiều versions từng tải trước đây mà không phải versions đã được chọn cho build hiện tại.

## 8. Nhiều BOM hoặc parent cùng quản lý một artifact: ưu tiên thế nào?

Đây là điểm dễ gây xung đột trong tổ chức lớn. Giả sử ứng dụng dùng **BOM framework** và **BOM nội bộ**; cả hai cùng quản lý `commons-logging` hoặc một thư viện khác.

### 8.1. Hai imported BOM cùng khai báo version

Ví dụ trong `dependencyManagement` của consumer:

```xml
<dependencies>
    <dependency>
        <groupId>vn.example.platform</groupId>
        <artifactId>company-libraries-bom</artifactId>
        <version>1.0.0</version>
        <type>pom</type>
        <scope>import</scope>
    </dependency>
    <dependency>
        <groupId>com.example.platform</groupId>
        <artifactId>framework-bom</artifactId>
        <version>3.0.0</version>
        <type>pom</type>
        <scope>import</scope>
    </dependency>
</dependencies>
```

Đây là **đoạn XML** nằm trong `<dependencyManagement>`. `framework-bom` và version nêu trên là tọa độ ví dụ; không cam kết có artifact tại repository công khai.

Nếu **cả hai BOM quản lý cùng một artifact key**, Maven theo tài liệu về *Importing Dependencies* thường dùng **khai báo từ BOM được import trước**, khi consumer chưa tự khai báo managed entry đó. Thứ tự ở đây có nghĩa. Không nên để việc reorder imports tình cờ làm đổi versions quan trọng.

### 8.2. Consumer khai báo managed entry tường minh

Một cách override có chủ đích là khai báo artifact được quản lý **tại POM consumer**:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>vn.example.libs</groupId>
            <artifactId>text-utils</artifactId>
            <version>1.5.0</version>
        </dependency>
        <dependency>
            <groupId>vn.example.platform</groupId>
            <artifactId>company-libraries-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Với artifact key tương ứng, **managed entry trực tiếp trong POM hiện tại** được ưu tiên hơn entry import từ BOM. Tuy nhiên, phiên bản `1.5.0` phải thật sự tồn tại và được kiểm thử với phần còn lại. Override nhiều thư viện như vậy có thể làm mất ý nghĩa “một bộ đã được thử nghiệm” của BOM.

Một dependency **trực tiếp khai báo version** tại `<dependencies>` cũng có thể làm version trực tiếp đó được dùng thay vì version mặc định do dependency management cung cấp cho khai báo ấy. Vì thế nếu đội muốn kiểm soát bằng BOM, nên lint/review những direct versions ngoài danh sách ngoại lệ.

### 8.3. Parent POM, BOM và sự ưu tiên

Nếu consumer có parent quản lý cùng một artifact, hoặc nhiều BOM được import theo chuỗi, cần xét **effective model** và Maven precedence/merge; không tự suy ra rằng “BOM nội bộ luôn thắng parent” hay “framework BOM luôn thắng” trên mọi sơ đồ inheritance.

Quy trình chắc chắn:

1. Ghi lại tọa độ parent, imported BOMs và thứ tự declarations.
2. Tìm managed entries trùng `groupId/artifactId/type/classifier`.
3. Kiểm tra `help:effective-pom` để xác định management cuối cùng.
4. Kiểm tra `dependency:tree` trong đúng module/scope để biết version thật được resolve.
5. Có test tích hợp với artifacts chịu ảnh hưởng, không chỉ sửa XML.

**Không nên kỳ vọng override property bên trong imported BOM bằng cách đặt property cùng tên ở consumer** sẽ luôn chỉnh được version đã được BOM nội suy. Nên dùng local managed entry có chủ đích, hoặc nâng version BOM chính thức.

## 9. Thiết kế quy trình phát hành BOM nội bộ

Một BOM có ích khi nó đại diện cho **bộ versions có kiểm chứng**, không phải danh sách version mới nhất được viết thủ công.

### 9.1. Phân vai giữa các nhóm

- **Chủ thư viện** phát hành version JAR theo API/semver hoặc quy ước nội bộ đã công bố, kèm changelog, compatibility notes và tests.
- **Chủ BOM/platform** chọn tổ hợp library versions, quản lý compatibility matrix, đánh giá changelog và phê duyệt release BOM.
- **Chủ ứng dụng** quyết định thời điểm nâng BOM, chạy test/triển khai và ghi nhận ngoại lệ nếu phải override.
- **CI/repository administrators** bảo đảm artifacts được publish, phân quyền, signatures/checksums, secret management và retention.

Không nhất thiết mỗi BOM có một “release train” cùng version. Có thể chọn version thư viện độc lập, còn BOM version là **mốc công bố tập versions**.

### 9.2. Pipeline phát hành gợi ý

1. **Chốt phạm vi:** xác định group/artifact nào được BOM quản lý, bao gồm third-party libraries nào là một phần platform.
2. **Kiểm thử các thư viện:** build/test riêng từng thư viện với Maven/JDK mục tiêu; publish **artifact release bất biến** vào kho nội bộ.
3. **Tạo release candidate của BOM:** ghim phiên bản cụ thể vào `dependencyManagement`, ghi changelog và lý do nâng version.
4. **Build/test các consumer đại diện:** chạy unit, integration và compatibility tests trên service mẫu, batch job, thư viện và các nền tảng liên quan.
5. **Đối chiếu dependency graph:** kiểm tra convergence, exclusions, version overrides, dependency tree và sản phẩm đóng gói.
6. **Rà soát bảo mật, license và reproducibility:** scan CVE/license, kiểm tra artifact integrity và JDK/framework compatibility.
7. **Publish BOM POM release mới** vào repository manager, cùng changelog và ma trận hỗ trợ.
8. **Nâng theo đợt:** consumer đổi đúng BOM version, review PR, chạy CI rồi rollout có giám sát.
9. **Giữ bản BOM trước để rollback:** không publish đè cùng một release version.

Với local lab, `mvn -f company-libraries-bom/pom.xml install` là đủ để kiểm chứng việc import trên máy. Trong thực tế, `mvn deploy` với `distributionManagement` và settings credentials mới là đường phát hành ra remote Maven repository. Không đưa token/password vào POM hoặc source control.

### 9.3. Quản lý phiên bản BOM

Ví dụ:

| BOM release | text-utils | metrics-api | Ý nghĩa |
| --- | --- | --- | --- |
| `1.0.0` | `1.4.0` | `2.2.0` | Baseline đã thử nghiệm |
| `1.1.0` | `1.5.0` | `2.2.1` | Bổ sung API text + sửa lỗi metrics |
| `2.0.0` | `2.0.0` | `3.0.0` | Có thể có breaking changes cần migration |

Bảng này chỉ minh họa **quy ước release**; Maven không yêu cầu BOM version theo SemVer hoặc tự tăng major/minor/patch. Tổ chức nên công bố quy ước: khi nào phát hành BOM major, minor, patch; khi nào version increment của thư viện được coi là incompatible.

**Quan trọng:** một consumer pin `company-libraries-bom:1.0.0` **không tự nhận** phiên bản do BOM 1.1.0 quản lý. Nó phải thay version BOM import (hoặc cơ chế version selection khác được tổ chức cho phép) và test lại. Tránh dùng version ranges/`-SNAPSHOT` ở production nếu mục tiêu là khả năng tái lập.

## 10. Kiểm thử và quality gates cho BOM

BOM không tự chứng minh rằng mọi thư viện trong tập có thể chạy cùng nhau. Nên kết hợp kiểm thử nhiều tầng:

| Tầng kiểm tra | Câu hỏi | Công cụ/phương án |
| --- | --- | --- |
| POM schema/model | BOM là POM artifact hợp lệ, import được không? | `mvn validate`, consumer import build |
| Version completeness | Có thiếu version của library do BOM quản lý không? | Effective POM, dependency management review |
| Resolvability | Artifact/POM của từng version có ở repository không? | CI với local repo sạch, Maven dependency resolution |
| Dependency convergence | Nhiều đường đang yêu cầu version khác nhau không? | Maven Enforcer `dependencyConvergence` |
| Upper-bound policy | Resolver có chọn bản thấp hơn bản dependency nào yêu cầu không? | Maven Enforcer `requireUpperBoundDeps` |
| Binary/API compatibility | Bộ library đã chọn có chạy cùng nhau không? | Integration tests, test ứng dụng đại diện |
| Security/license | Có CVE, license hoặc policy vi phạm không? | Scanner phù hợp và SBOM của artifacts |
| Java/platform | Bộ thư viện có dùng bytecode/framework quá mới không? | Test bằng JDK mục tiêu, enforcer/bytecode checks |
| Release reproducibility | Consumer có build giống nhau với cùng BOM pin không? | CI matrix, clean resolution, checksum |

Ví dụ cấu hình Maven Enforcer Plugin trên một **consumer project**, chỉ áp dụng khi thực sự muốn bắt lỗi dependency convergence:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>check-dependency-convergence</id>
            <phase>validate</phase>
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
```

Đây là **đoạn XML đặt trong `<build><plugins>` của consumer**, không phải mục `dependencyManagement` trong BOM. Rule `dependencyConvergence` sẽ kiểm tra đường dependency graph có những version không nhất quán; không nên mặc định nó phát hiện mọi duplicate class, lỗi API hay security issue.

`requireUpperBoundDeps` có chính sách khác `dependencyConvergence`: nó tập trung vào việc không chọn version thấp hơn yêu cầu của các đường dependency; không nên dùng tên hai rule thay thế nhau mà không hiểu mục đích.

Trong hệ thống thực tế, có thể phải cấu hình exclusions/scopes ngoại lệ theo policy; mỗi ngoại lệ cần ghi lý do và test thay vì tắt rule toàn cục.

## 11. Những lỗi thiết kế BOM thường gặp

| Hiện tượng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Consumer báo thiếu version dependency | Quên `type=pom`/`scope=import` hoặc BOM không quản lý artifact đó | Kiểm tra import trong `dependencyManagement` và tọa độ |
| Maven không tìm được BOM | BOM chưa install/deploy, repository/mirror/credentials sai | Publish BOM POM artifact, kiểm tra settings và version |
| Build báo cyclic POM/import | BOM import consumer hoặc dùng module import vòng | Tách BOM độc lập, phát hành trước, bỏ circular relationships |
| Consumer có BOM nhưng không tự tải thư viện | `dependencyManagement` không tự add dependency | Thêm artifact cần dùng vào `<dependencies>` |
| Cùng dependency bị quản lý bởi hai BOM khác version | Imported BOM declarations chồng lấn | Kiểm tra thứ tự và effective POM, thống nhất policy |
| Consumer thêm `<version>` trực tiếp và lệch BOM | Version khai báo tường minh hoặc local managed override | Xóa override không cần, hoặc quản lý ngoại lệ có test |
| Đổi property version trong consumer nhưng BOM import không đổi | Property của imported BOM được xử lý trong model BOM | Override bằng local dependencyManagement hoặc BOM release mới |
| Nâng BOM khiến runtime `NoSuchMethodError` | Bộ versions không tương thích nhị phân/hành vi | Rollback BOM; test API/integration và cải thiện compatibility matrix |
| BOM 1.0.0 trỏ tới thư viện chưa publish | BOM chứa tọa độ không resolve được khi consumer dùng | Publish libraries trước/đúng lúc, test trên repository sạch |
| BOM chứa `<dependencies>` thật và bị dùng như parent | Trộn vai trò manager với starter/parent | Thiết kế BOM thuần `dependencyManagement`; tách starter |
| Plugin build thay version ngoài dự kiến | BOM không quản lý plugin dependencies/versions | Quản lý plugin qua parent `pluginManagement` |
| Nhìn thấy nhiều JAR trong cache rồi kết luận version lệch | Cache lưu nhiều version quá khứ | Kiểm tra `dependency:tree` và runtime classpath |
| Xóa bản BOM cũ để ép nâng cấp | Consumer đã pin BOM cũ không resolve được | Giữ release immutable và retention policy phù hợp |
| BOM version trùng số với library, nhầm release | Nhầm version của tập với version của artifact thành viên | Dùng changelog và ma trận BOM→libraries |

### Cảnh báo về imported BOM là một submodule chưa cài đặt

Tài liệu Maven cảnh báo không nên **import một POM được định nghĩa ở submodule của POM hiện tại** khi BOM chưa thể resolve từ repository, và tránh quan hệ parent/import vòng. Cùng một reactor không bảo đảm mọi tổ hợp import có thể được giải quyết theo thứ tự mong muốn, bởi Maven cần đọc model/dependency management **trước khi** có các artifact mới.

Vì vậy ví dụ ở mục 7 dùng các project độc lập và cài BOM trước khi consumer build. Trong sản phẩm thật, ưu tiên publish BOM như một artifact độc lập trước khi giao consumer mới dùng; nếu cần tích hợp trong multi-module, hãy thiết kế build order và kiểm thử trên máy sạch có chủ đích.

## 12. BOM cho tổ chức nhiều framework hoặc nhiều parent

Một tổ chức có thể có:

- các microservice kế thừa Spring Boot parent;
- thư viện Java thuần dùng một parent tối giản;
- project có parent nội bộ chuyên chất lượng build;
- ứng dụng Quarkus hoặc Micronaut có BOM riêng.

Áp thêm **BOM nội bộ** giúp chia sẻ version của một số artifact `vn.example.libs:*` mà không bắt toàn bộ dự án đổi parent. Tuy nhiên, có thể gặp giao nhau giữa platform BOM và framework BOM:

- **Không import BOM tràn lan** nếu framework đã bảo đảm version của phần lớn ecosystem.
- **Ưu tiên một BOM chịu trách nhiệm một nhóm artifact rõ ràng**; với phần chồng lấn, quy định ai thắng và xác minh bằng effective POM.
- **Đừng thay framework BOM bằng BOM nội bộ “tự chế”** mà không kiểm tra test compatibility.
- **Đánh dấu nhóm version do đội platform quản lý** và nhóm version ứng dụng có thể override có kiểm soát.
- Nếu phải dùng hai BOM, thứ tự import và local dependencyManagement phải được review như code, không phải chi tiết trình bày.

Một thói quen tốt là viết tài liệu ngắn kèm mỗi BOM release:

```text
company-libraries-bom 1.1.0
- Supported Java: 17, 21
- text-utils: 1.5.0
- metrics-api: 2.2.1
- Required framework range: theo compatibility matrix đã kiểm thử
- Consumer migration: đổi import BOM 1.0.0 → 1.1.0
- Breaks or exceptions: xem changelog và release test report
```

Thông tin trên là mẫu minh họa; phải thay bằng kết quả kiểm chứng thực tế của tổ chức, không tự suy compatibility từ số version.

## 13. Quy trình nâng cấp và rollback ở consumer

Giả sử consumer dùng:

```xml
<dependency>
    <groupId>vn.example.platform</groupId>
    <artifactId>company-libraries-bom</artifactId>
    <version>1.0.0</version>
    <type>pom</type>
    <scope>import</scope>
</dependency>
```

Khi có BOM 1.1.0, chỉ thay:

```xml
<version>1.1.0</version>
```

trong **đúng mục BOM import**, không thay tất cả phiên bản trong POM bằng tìm kiếm văn bản. Trước khi merge:

1. Chạy `dependency:tree` và lưu tập version cũ.
2. Thay BOM import sang bản mới.
3. Chạy `help:effective-pom`/`dependency:tree` để xem chính xác artifact nào đổi version.
4. Chạy compile, unit test, integration tests và test đóng gói với JDK/CI chuẩn.
5. Kiểm tra runtime, backward compatibility, bảo mật và metrics production sau rollout.
6. Nếu gặp lỗi, revert version BOM và **các sửa đổi liên quan**; build lại với repository giữ bản release cũ.

**Rollback BOM không tự rollback sản phẩm đã deploy**: nếu ứng dụng đã được release, cần quy trình rollback deployment/artefact khác. Duy trì nhiều BOM releases có kiểm soát giúp các ứng dụng nâng cấp theo tốc độ riêng mà vẫn tái lập được build cũ.

## 14. Câu hỏi tự luyện và đáp án

**Câu 1.** BOM `company-libraries-bom:1.0.0` quản lý `text-utils:1.4.0` và `metrics-api:2.2.0`. Consumer chỉ khai báo dependency `text-utils`. Có tự tải `metrics-api` không?

**Đáp án:** Không chỉ vì BOM quản lý nó. `metrics-api` chỉ xuất hiện nếu consumer khai báo nó hoặc một dependency thực tế khác đưa nó vào như dependency bắc cầu. BOM không tự thêm cả bộ thư viện.

**Câu 2.** Consumer import hai BOM X và Y. Cả hai quản lý cùng artifact A, consumer không khai báo managed entry A. Theo Maven dependency management import, version nào có thể được ưu tiên?

**Đáp án:** Thông thường khai báo từ BOM import **đứng trước** được dùng đối với key trùng, theo Maven Dependency Mechanism. Phải xác minh bằng effective POM và tree vì parent, local entries và các type/classifier khác có thể ảnh hưởng.

**Câu 3.** Một ứng dụng đã có Spring Boot parent nhưng cần đồng bộ `vn.example.libs:*` với các service khác. Có cần đổi sang organization parent không?

**Đáp án:** Không bắt buộc. Import BOM nội bộ ở `dependencyManagement` của ứng dụng; giữ parent hiện có nếu tương thích. Review sự chồng lấn management và dùng effective POM để xác định versions.

**Câu 4.** Tổ chức phát hành BOM 1.2.0 nhưng consumer vẫn pin 1.1.0. Consumer có tự nâng lên 1.2.0 không?

**Đáp án:** Không, khi dùng release cố định. Consumer cần thay version import theo quy trình nâng cấp đã kiểm chứng.

**Câu 5.** Maven Compiler Plugin của ứng dụng dùng version sai. Tăng version compiler trong BOM có sửa được không?

**Đáp án:** Không theo cơ chế BOM dependency management thông thường. Plugin version/config thuộc `pluginManagement`/`build/plugins` của project hoặc parent POM, không phải managed project dependencies của BOM.

**Câu 6.** Sau khi đổi BOM, unit tests thành công nhưng production gặp `NoSuchMethodError`. Có thể kết luận “BOM Maven bị lỗi” không?

**Đáp án:** Chưa đủ dữ liệu. Cần xem dependency tree và runtime class loading: BOM có thể đã chọn version hợp lệ nhưng không tương thích API với thư viện tiêu thụ, hoặc runtime có JAR khác, duplicate class hay classloader khác. Kiểm tra binary compatibility và test toàn bộ đường chạy.

## Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism: Dependency Management, Importing Dependencies và BOM](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Enforcer — Dependency Convergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html)
- [Apache Maven Enforcer — Require Upper Bound Dependencies](https://maven.apache.org/enforcer/enforcer-rules/requireUpperBoundDeps.html)
