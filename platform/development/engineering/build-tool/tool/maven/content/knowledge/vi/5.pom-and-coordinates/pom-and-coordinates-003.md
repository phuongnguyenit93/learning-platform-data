# groupId, artifactId, version và định danh đầy đủ của artifact trong Maven

## 1. Mục tiêu: hiểu Maven đang nói tới dự án hoặc thư viện nào

Trong một dự án Java có Maven, khi viết `pom.xml` bạn sẽ gặp ba trường xuất hiện rất thường xuyên:

```xml
<groupId>com.example.training</groupId>
<artifactId>coordinates-demo</artifactId>
<version>1.0.0</version>
```

Ba giá trị này cho Maven biết **đang nói đến artifact của nhóm nào, tên gì, phiên bản nào**. Chúng thường được viết thành một chuỗi ngắn gọi là **GAV (Group, Artifact, Version)**:

```text
com.example.training:coordinates-demo:1.0.0
```

Học xong bài, bạn cần có thể giải thích từng trường, đọc GAV của một dependency, dự đoán tên JAR/đường dẫn lưu trữ, phân biệt GAV cơ bản với định danh mở rộng, và chỉnh các tọa độ đúng chỗ khi tạo dự án.

Trong Maven, **artifact** là kết quả có thể được định danh và truy xuất từ repository, thường là JAR hoặc POM; có thể là WAR, ZIP hay tệp khác. `pom.xml` mô tả dự án và được xuất bản dưới dạng POM artifact khi cài/triển khai dự án. Với một thư viện Java, Maven có thể xử lý cả tệp `.jar` và `.pom` cho cùng một phiên bản dự án.

Đừng đồng nhất **artifact** với **thư mục dự án**, **Java package**, **tên lớp** hay **chỉ riêng file JAR**. GAV là tọa độ để tìm/định danh dự án hoặc thành phần được xuất bản; Maven dùng thêm những thông tin như extension và classifier khi cần xác định chính xác tệp nào.

## 2. Ba thành phần của GAV

### 2.1. `groupId`: thành phần thuộc nhóm nào?

`groupId` xác định **nhóm dự án hoặc tổ chức** phát hành artifact. Cách đặt tên được Maven khuyến nghị là bắt đầu bằng tên miền mà bạn kiểm soát, **viết đảo thứ tự** giống quy tắc đặt Java package:

- `org.apache.commons`: nhóm của Apache Commons;
- `org.junit.jupiter`: nhóm các artifact JUnit Jupiter;
- `com.example.training`: nhóm minh họa của các bài thực hành;
- `vn.example.platform.shared`: ví dụ một nhóm có phân cấp cho các module dùng chung.

Nếu một tổ chức tạo nhiều thư viện, dùng cùng một `groupId` hoặc các nhóm con tương ứng giúp phân biệt nguồn phát hành và quản lý artifact có trật tự. Hai sản phẩm khác nhau có thể dùng cùng `groupId`, nhưng nên có `artifactId` khác nhau.

**Không phải Java package:** `groupId=com.example.training` không bắt buộc mã nguồn Java có dòng `package com.example.training;`, dù đặt trùng/hợp lý thường giúp dễ quản lý. Maven không tự viết lại mọi `package` trong source chỉ vì bạn đổi `groupId` trong POM.

**Không nên dùng** giá trị `com.example` cho sản phẩm công bố thực tế nếu bạn không có một namespace phù hợp; đây là nhóm minh họa. Trong tổ chức, nên theo quy ước tên miền/namespace đã được quản lý.

### 2.2. `artifactId`: thành phần cụ thể tên gì?

`artifactId` đặt tên cho **một artifact hoặc một module** trong nhóm. Ví dụ trong `com.example.training` có thể có:

```text
com.example.training:core-utils:1.0.0
com.example.training:http-client:1.0.0
com.example.training:coordinates-demo:1.0.0
```

Maven khuyến nghị dùng chữ thường, chữ số và dấu gạch nối, ví dụ `order-api`, `order-service`, `shared-model`. Hãy chọn tên có nghĩa và đủ ổn định vì các dự án khác sẽ khai báo nó làm dependency.

Đối với đóng gói JAR thông thường, tên tệp build mặc định có dạng `artifactId-version.jar`, chẳng hạn `coordinates-demo-1.0.0.jar`. Đây là **hành vi tên mặc định** có thể thay đổi nếu cấu hình `finalName`/plugin; artifact được xuất bản vào repository vẫn được quản lý theo tọa độ và cách plugin xuất bản artifact.

**Không phải Java class:** `artifactId=coordinates-demo` không bắt buộc có lớp `CoordinatesDemo`. Trong ví dụ sau, chúng ta tạo lớp `com.example.training.Main` và vẫn xuất bản artifact tên `coordinates-demo`.

### 2.3. `version`: đang nói đến lần phát hành nào?

`version` phân biệt các phiên bản của **cùng groupId + artifactId**. Ví dụ:

```text
com.example.training:core-utils:1.0.0
com.example.training:core-utils:1.1.0
com.example.training:core-utils:2.0.0
```

Maven không tự cưỡng chế một quy tắc Semantic Versioning đầy đủ cho mọi chuỗi version. Tuy nhiên, cách đặt phiên bản theo `major.minor.patch` là quy ước dễ hiểu: thay đổi lớn có nguy cơ không tương thích thường tăng major; bổ sung tương thích thường tăng minor; sửa lỗi tương thích thường tăng patch. Đây là **quy ước do đội dự án vận hành**, không phải điều Maven tự suy ra từ code.

Hai dạng phiên bản thường gặp:

| Ví dụ | Ý nghĩa |
| --- | --- |
| `1.0.0`, `1.2.3` | Thường dùng cho bản release xác định |
| `1.1.0-SNAPSHOT` | Bản đang phát triển; nội dung có thể được cập nhật giữa các lần build/xuất bản |

**Đừng coi SNAPSHOT là dữ liệu bất biến.** Repository từ xa có thể lưu nhiều bản snapshot theo timestamp/build number, cùng được truy cập qua base version như `1.1.0-SNAPSHOT`. Trái lại, khi muốn build có thể lặp lại, nên ưu tiên phụ thuộc vào release có phiên bản cố định và kiểm soát repository/plugin/JDK.

Version còn có thể được kế thừa từ parent POM, được biểu diễn bằng thuộc tính hoặc chịu quy tắc dependency management. Điều quan trọng là tìm được **giá trị hiệu lực** (effective value), không chỉ đọc một đoạn XML rời rạc.

## 3. Định danh đầy đủ nghĩa là gì?

### 3.1. GAV là cách viết thường dùng

Với một Maven project thông thường, cách đọc ngắn gọn là:

```text
<groupId>:<artifactId>:<version>
```

Ví dụ:

```text
org.apache.commons:commons-lang3:3.17.0
org.junit.jupiter:junit-jupiter:5.11.4
com.example.training:coordinates-demo:1.0.0
```

GAV giúp nhận diện dòng artifact theo namespace/tên/phiên bản trong repository. **Tính duy nhất cần hiểu trong phạm vi repository**: hai repository khác nhau vẫn có thể chứa tệp khác nhau dưới cùng tọa độ; đó là một rủi ro về tính nhất quán và chuỗi cung ứng. Maven cần cả **cấu hình repository/mirror** để biết lấy artifact ở đâu; GAV tự nó không chứa URL nguồn tải.

### 3.2. Khi GAV chưa đủ: extension và classifier

Cùng dự án và cùng phiên bản có thể xuất hiện nhiều artifact vật lý:

```text
coordinates-demo-1.0.0.pom
coordinates-demo-1.0.0.jar
coordinates-demo-1.0.0-sources.jar
coordinates-demo-1.0.0-javadoc.jar
```

Các tệp ví dụ này có cùng GAV, nhưng không cùng **extension** và/hoặc **classifier**. Hai tệp `sources` và `javadoc` chỉ xuất hiện khi quy trình build/xuất bản đã cấu hình tạo và gắn (attach) chúng; Maven không mặc nhiên sinh đủ bốn file cho mọi dự án.

Thông tin cần nắm:

- **extension**: phần mở rộng định dạng artifact, thường là `jar` hoặc `pom`, cũng có thể là `war`, `zip`...
- **classifier** (tùy chọn): nhãn phân biệt những artifact bổ sung có cùng GAV/extension, ví dụ `sources`, `javadoc`, hoặc một biến thể theo nền tảng.
- **baseVersion**: phiên bản nền, đặc biệt hữu ích với SNAPSHOT vì bản đã triển khai từ xa có thể mang timestamp trong tên tệp.

Một số công cụ Maven chấp nhận dạng chuỗi mở rộng như:

```text
groupId:artifactId:extension:version
groupId:artifactId:extension:classifier:version
```

Ví dụ `com.example.training:coordinates-demo:jar:sources:1.0.0` mô tả JAR sources (nếu artifact này đã được xuất bản). Cú pháp chuỗi chính xác có thể khác theo plugin/công cụ; khi khai báo dependency trong POM, sử dụng các thẻ XML như `<type>` và `<classifier>` thay vì đoán thứ tự các thành phần từ một câu lệnh khác.

**Tóm đúng bản chất:** GAV là bộ ba lõi, đủ cho nhiều thao tác Maven thông dụng; để xác định **một file artifact cụ thể** có thể phải xét thêm extension và classifier. `scope` không phải thuộc tính định danh tệp: đó là cách **dự án đang sử dụng dependency**.

## 4. Ví dụ một POM hoàn chỉnh: tự tạo artifact có GAV rõ ràng

Giả sử chúng ta xây dựng một ứng dụng console Java 17 đơn giản. Tạo thư mục:

```text
coordinates-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── training/
                        └── Main.java
```

### 4.1. Tệp `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.training</groupId>
    <artifactId>coordinates-demo</artifactId>
    <version>1.0.0</version>
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

Đây là một POM hợp lệ cho một dự án Maven đơn module. Các plugin và dependency cần mạng hoặc bản sao cục bộ khi tải lần đầu. Version Compiler Plugin được ghim cụ thể để tránh phụ thuộc vào mặc định plugin có thể khác giữa môi trường.

**Ba nơi không được nhầm:**

1. `project/groupId`, `project/artifactId`, `project/version` xác định **dự án đang build**: `com.example.training:coordinates-demo:1.0.0`.
2. `build/plugins/plugin` ở ví dụ có GAV riêng của **Maven Compiler Plugin**: `org.apache.maven.plugins:maven-compiler-plugin:3.13.0`.
3. Nếu sau này thêm `dependencies/dependency`, mỗi thư viện có GAV của chính **thư viện đó**; nó không thay đổi GAV của dự án.

`modelVersion=4.0.0` là phiên bản **mô hình POM**, tuyệt đối không phải version dự án. `packaging=jar` quyết định cách đóng gói của dự án; giá trị mặc định của packaging thường là `jar` với project Java thông thường.

### 4.2. Tệp Java `src/main/java/com/example/training/Main.java`

```java
package com.example.training;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Coordinates demo is running.");
    }
}
```

Mã chỉ in ra một chuỗi. Nó **không truy vấn GAV của POM tại runtime**: tọa độ trong POM là metadata build, không tự biến thành biến Java hay thông điệp trong `main()`. Nếu muốn nhúng version vào ứng dụng, cần cấu hình cơ chế đưa metadata vào resource/manifest khi build.

### 4.3. Lệnh build, chạy và kết quả kiểm chứng

Cần JDK 17+ và Maven tương thích. Mở terminal ở thư mục chứa `pom.xml`:

```bash
mvn -version
mvn clean package
java -cp target/coordinates-demo-1.0.0.jar com.example.training.Main
```

Kết quả **chính xác** của lệnh `java -cp`:

```text
Coordinates demo is running.
```

`mvn clean package` chạy build lifecycle tới phase `package`. Maven biên dịch `Main.java` thành `target/classes/com/example/training/Main.class` và tạo `target/coordinates-demo-1.0.0.jar` theo cấu hình JAR thông thường. Log Maven có thể khác nhau giữa máy; không nên sao chép một đoạn `BUILD SUCCESS` làm “stdout cố định” của cả quy trình.

Chúng ta dùng `java -cp ... com.example.training.Main` vì ví dụ chưa tạo manifest có `Main-Class` cho `java -jar`. Nếu có dependency runtime bổ sung, chỉ thêm JAR của ứng dụng vào classpath chưa chắc đủ.

**Quan sát quan hệ giữa tọa độ và tên JAR:** thay `<artifactId>coordinates-demo</artifactId>` bằng `new-name` thì tên đầu ra mặc định trở thành `new-name-1.0.0.jar`; thay version thành `1.0.1` thì JAR mặc định thành `coordinates-demo-1.0.1.jar` (nếu giữ artifactId cũ). Đừng xem tên file là nguồn duy nhất của định danh, vì `finalName` và plugin có thể điều chỉnh tên đầu ra của build.

### 4.4. Cài artifact vào local Maven repository

Chạy:

```bash
mvn install
```

Lệnh `install` thực thi các phase cần thiết đến `install` và đặt artifact vào **local Maven repository**. Mặc định vị trí trên Linux/macOS là `~/.m2/repository`, trên Windows là `%USERPROFILE%\.m2\repository`, trừ khi người dùng đã thay đổi cấu hình local repository.

Với GAV của ví dụ, bạn sẽ thấy đường dẫn theo quy ước:

```text
~/.m2/repository/
└── com/
    └── example/
        └── training/
            └── coordinates-demo/
                └── 1.0.0/
                    ├── coordinates-demo-1.0.0.jar
                    └── coordinates-demo-1.0.0.pom
```

Ngoài hai tệp chính, thư mục có thể chứa metadata/tracking files do Maven tạo. `mvn install` chỉ làm artifact có thể dùng bởi các dự án Maven **trên máy/local repository đó**, không phát hành lên Maven Central. `mvn deploy` mới liên quan đến xuất bản vào **remote repository** đã cấu hình và cần quyền thích hợp.

## 5. GAV xuất hiện như thế nào khi khai báo dependency?

Một project Maven sử dụng thư viện khác bằng `<dependencies>` trong POM. Ví dụ **đoạn trích** sau (không phải POM đầy đủ) khai báo thư viện Apache Commons Lang:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.17.0</version>
    </dependency>
</dependencies>
```

Tọa độ của **dependency** là:

```text
org.apache.commons:commons-lang3:3.17.0
```

Maven phân giải artifact này qua repository đã cấu hình (và cache cục bộ). Nó còn có thể kéo theo các **transitive dependencies** mà bản thân thư viện khai báo. Dự án của bạn không biến thành `org.apache.commons:commons-lang3:3.17.0`; GAV dự án trong `<project>` và GAV dependency trong `<dependency>` có mục đích khác nhau.

### 5.1. `scope` không phải một phần của GAV

Giả sử bạn chỉ cần JUnit Jupiter cho test:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

`scope=test` nói rằng dự án này dùng artifact trong classpath/test, **không thay đổi tọa độ của JUnit**. Cùng GAV JUnit có thể được các dự án khác khai báo scope khác. Scope mặc định khi không khai báo thường là `compile`; các scope quen thuộc khác gồm `runtime` và `provided`.

| Thành phần | Định danh artifact? | Vai trò |
| --- | --- | --- |
| `groupId` | Có | Nhóm/namespace |
| `artifactId` | Có | Tên thành phần |
| `version` | Có | Phiên bản |
| `type` trong dependency | Liên quan đến extension/classifier được chọn | Chọn loại artifact mà dự án dùng; mặc định là `jar` |
| `classifier` trong dependency | Có, khi cần phân biệt biến thể | Ví dụ `sources`, `javadoc` hoặc biến thể theo OS/CPU |
| `scope` | Không | Xác định nơi dependency xuất hiện trong classpath/quá trình build |
| `optional` | Không | Ảnh hưởng cách dependency được truyền đến project phụ thuộc |

### 5.2. `packaging`, `type` và `classifier` khác nhau thế nào?

- `<packaging>jar</packaging>` ở **cấp project** cho biết Maven sẽ xây dựng kiểu dự án/artifact ra sao qua lifecycle (ví dụ `jar`, `war`, `pom`).
- `<type>jar</type>` ở **cấp dependency** cho biết loại artifact đang tham chiếu. Maven dùng “artifact handler” để ánh xạ type thành extension và đôi khi classifier; không phải lúc nào type cũng chính là phần đuôi file.
- `<classifier>sources</classifier>` phân biệt một artifact bổ sung của cùng GAV và type/extension; ví dụ mã nguồn đóng gói riêng. Mẫu JAR sources chỉ phân giải được nếu repository thật sự có artifact đó.

Ví dụ minh họa yêu cầu một **JAR sources** (giả sử thư viện đã xuất bản biến thể này):

```xml
<dependency>
    <groupId>com.example.training</groupId>
    <artifactId>coordinates-demo</artifactId>
    <version>1.0.0</version>
    <type>jar</type>
    <classifier>sources</classifier>
</dependency>
```

Đoạn này minh họa **cách chỉ định file**, không phải khuyến nghị đưa sources JAR vào runtime classpath: sources thường phục vụ IDE/đọc mã và không chứa bytecode dùng để chạy. Bản POM ở mục 4 không tự tạo sources JAR; cần plugin thích hợp để gắn/xuất bản nó.

**Trường hợp POM artifact:** parent POM hoặc Bill of Materials (BOM) có thể dùng `<type>pom</type>`. Khi import BOM, `<scope>import</scope>` chỉ hợp lệ trong `dependencyManagement` cùng `type=pom`; mục đích là nhập danh sách quản lý version, không biến BOM thành JAR để chạy.

## 6. Maven tìm artifact theo tọa độ ra sao?

Trong layout repository Maven thông dụng, tọa độ được ánh xạ thành đường dẫn. Với bản release JAR không classifier:

```text
<groupId đổi dấu . thành />/<artifactId>/<version>/<artifactId>-<version>.jar
```

Với `com.example.training:coordinates-demo:1.0.0`:

```text
com/example/training/coordinates-demo/1.0.0/coordinates-demo-1.0.0.jar
```

Tệp POM tương ứng:

```text
com/example/training/coordinates-demo/1.0.0/coordinates-demo-1.0.0.pom
```

Nếu có classifier `sources` và extension `jar`:

```text
com/example/training/coordinates-demo/1.0.0/coordinates-demo-1.0.0-sources.jar
```

**Quy tắc không phải URL tuyệt đối**: Maven có thể tìm theo đường dẫn này trong local repository, mirror, repository nội bộ hoặc repository từ xa, tùy `settings.xml`, POM và chính sách repository. Với SNAPSHOT được triển khai từ xa, Maven metadata có thể trỏ đến tệp mang timestamp/build number, vì thế không thể luôn tự ghép một tên file release đơn giản rồi kết luận tệp snapshot tồn tại.

GAV cũng không đảm bảo toàn thế giới chỉ có một binary tương ứng. Nếu hai repository cung cấp tệp khác nhau cho cùng tọa độ, build có nguy cơ không nhất quán. Vì thế quản lý nguồn artifact và checksum/signature chính là một phần của quản trị dependency.

## 7. Kế thừa tọa độ từ parent POM và quản lý phiên bản

Trong dự án Maven nhiều module, POM con có thể kế thừa `groupId` và `version` từ parent. Ví dụ một POM con:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.platform</groupId>
        <artifactId>platform-parent</artifactId>
        <version>2.3.0</version>
    </parent>

    <artifactId>platform-core</artifactId>
</project>
```

Đây là **ví dụ cấu trúc** giả định parent `com.example.platform:platform-parent:2.3.0` đã tồn tại hoặc có thể được tìm qua đường dẫn tương đối/repository; nó không phải dự án build độc lập từ một tệp duy nhất. Nếu không override, effective GAV của module con là:

```text
com.example.platform:platform-core:2.3.0
```

Đừng kết luận `groupId` và `version` “bị thiếu” chỉ vì không xuất hiện ở cấp trên cùng của POM con. Maven có thể kế thừa từ parent. Lệnh:

```bash
mvn help:effective-pom
```

giúp xem cấu hình POM hiệu lực sau kế thừa và một số giá trị mặc định/profile. Nếu mô tả project đa module, `<modules>` thuộc parent/aggregator chỉ định các module tham gia reactor build; nó không thay thế GAV riêng của mỗi module.

Tương tự, một dependency có thể **không ghi trực tiếp `<version>`** nếu phiên bản đó đã được quản lý phù hợp trong `dependencyManagement` hoặc BOM. Vì vậy, để tìm version thực sự sử dụng, cần kết hợp dependency, quản lý phiên bản và effective POM.

**Phân biệt cho đúng:**
- **Parent POM**: hỗ trợ kế thừa cấu hình/metadata, thường có `packaging=pom`.
- **Aggregator POM**: có `modules` để gom các module trong reactor build; một POM có thể đồng thời là parent và aggregator.
- **BOM**: thường là POM tập trung `dependencyManagement` để quản lý phiên bản thư viện.
- Cả ba vẫn là các dự án/artifact có **GAV riêng**, không phải khái niệm thay thế cho `groupId`, `artifactId`, `version`.

## 8. Các sai lầm thường gặp khi đặt hoặc đọc tọa độ

| Hiểu nhầm / lỗi | Cách hiểu và cách xử lý |
| --- | --- |
| “`groupId` chính là Java package” | Đây là namespace Maven; Java package ở trong source, có thể khác |
| “`artifactId` chính là tên class `main`” | Nó là tên artifact/module; class main chỉ là điểm vào chương trình |
| “`version` buộc phải theo Semantic Versioning” | Maven chấp nhận nhiều dạng chuỗi; SemVer là quy ước được khuyến nghị |
| “`1.0-SNAPSHOT` tương đương bản release cố định” | Snapshot có thể thay đổi/tạo bản timestamp, cần quản lý khi muốn build tái lập |
| “GAV nói luôn artifact được tải ở URL nào” | GAV định danh; repository và mirror quyết định nguồn tải |
| “Một GAV chỉ có thể có duy nhất một tệp” | Có thể có POM, JAR, sources, javadoc và biến thể classifier/extension |
| “`scope=test` là một phần của tên artifact” | Scope mô tả cách sử dụng dependency, không phải tọa độ |
| “Đổi `artifactId` trong POM sẽ đổi package của tất cả file Java” | Không; phải điều chỉnh code/package/import nếu mục tiêu thực sự cần |
| “`mvn package` đã phát hành thư viện cho project khác” | Package tạo đầu ra trong `target`; `install` vào local repo, `deploy` lên remote repo |
| “Thiếu version trong POM con tức là POM sai” | Có thể kế thừa parent hoặc quản lý dependency; kiểm tra effective POM |
| “Tên JAR luôn đúng bằng `artifactId-version.jar`” | Đó là quy ước đầu ra thông thường, có thể thay bằng cấu hình build/plugin |

Một lỗi thực tế khác là copy nhầm `groupId` hoặc `artifactId` từ trang hướng dẫn mà không xét **artifact version có thật trong repository**. Chỉ cần một ký tự sai, Maven có thể báo `Could not find artifact`. Dùng tọa độ có căn cứ, kiểm tra repository và version đang phát hành, thay vì tự đoán rằng một version nhất định phải tồn tại.

## 9. Thực hành kiểm tra tọa độ với Maven

Dùng dự án `coordinates-demo` ở mục 4.

**Bước 1: Quan sát GAV của dự án.** Mở `pom.xml`, xác nhận:

```text
groupId    = com.example.training
artifactId = coordinates-demo
version    = 1.0.0
GAV        = com.example.training:coordinates-demo:1.0.0
```

**Bước 2: Đọc kết quả đóng gói.** Chạy:

```bash
mvn clean package
```

Tìm `target/coordinates-demo-1.0.0.jar`. Đọc POM để phân biệt tệp `pom.xml` đầu vào và JAR đầu ra. Maven không sửa Java package theo GAV.

**Bước 3: Quan sát local repository.** Chạy:

```bash
mvn install
```

Tìm thư mục tương ứng theo `com/example/training/coordinates-demo/1.0.0/` trong local repository. So sánh tên JAR/POM với ba trường GAV.

**Bước 4: Xem cấu hình hiệu lực.** Chạy:

```bash
mvn help:effective-pom
```

Tìm các trường `groupId`, `artifactId`, `version`, cấu hình compiler và plugin. Nếu bạn đang ở dự án có parent/BOM, quan sát cách Maven kế thừa/quản lý các giá trị.

**Bước 5: Tự thay đổi có kiểm soát.** Đổi version dự án thành `1.0.1`, build lại và đối chiếu tên JAR mới. Không đổi `version` của Compiler Plugin vì đó là tọa độ **plugin build**, không phải version dự án. Nếu có module khác phụ thuộc bản `1.0.0`, việc đổi version dự án không tự sửa mọi POM của các consumer.

### Câu hỏi tự kiểm tra

1. `groupId`, `artifactId`, `version` có chức năng khác nhau như thế nào?
2. GAV của `org.junit.jupiter:junit-jupiter:5.11.4` có liên hệ gì tới `scope=test`?
3. Vì sao một dự án có thể xuất bản `.jar` và `.pom` cùng GAV?
4. Tọa độ nào dùng để tìm một JAR `sources` nếu nó tồn tại?
5. Khác biệt giữa `mvn package`, `mvn install` và `mvn deploy` là gì?
6. Vì sao hai repository có thể gây rủi ro nếu trả về hai nội dung khác nhau cho cùng GAV?
7. Khi POM con không chứa `groupId` và `version` ở cấp cao nhất, bạn kiểm tra ở đâu?

Hiểu đúng tọa độ Maven sẽ giúp bạn **đọc POM, chọn dependency, phân biệt module, kiểm tra repository và sửa lỗi phân giải artifact**. Quy tắc quan trọng nhất là bắt đầu từ GAV của đối tượng đang xét, rồi hỏi tiếp **artifact nào (extension/classifier), được dùng ở đâu (scope), và được lấy từ repository nào**.

### Tài liệu Apache Maven chính thức

- [Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Naming conventions for groupId, artifactId and version](https://maven.apache.org/guides/mini/guide-naming-conventions.html)
- [Maven Artifacts — coordinates, classifier, extension, baseVersion](https://maven.apache.org/repositories/artifacts.html)
- [Maven Dependencies — coordinates and scopes](https://maven.apache.org/repositories/dependencies.html)
- [Maven Repository Layout](https://maven.apache.org/repositories/layout.html)
- [Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
