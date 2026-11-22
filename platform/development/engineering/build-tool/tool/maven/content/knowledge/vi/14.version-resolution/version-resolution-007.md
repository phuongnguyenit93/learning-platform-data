# Version range và rủi ro đồ thị Maven thay đổi theo thời gian

Trong Maven, một dependency có thể ghi **phiên bản cụ thể** như `1.4.2` hoặc một **version range** (khoảng phiên bản) như `[1.4,2.0)`. Version range không yêu cầu một artifact duy nhất; nó đặt ra **tập các phiên bản được phép** để Maven giải quyết dựa trên metadata repository, các ràng buộc của những nhánh dependency và cấu hình của lần build.

Điều dễ bị bỏ qua: **cùng một `pom.xml`, cùng một lệnh Maven nhưng chạy vào hai thời điểm khác nhau có thể chọn phiên bản dependency khác nhau**. Khi repository có bản phát hành mới nằm trong range, dữ liệu metadata được cập nhật hoặc môi trường truy cập repository khác đi, đồ thị dependency có thể thay đổi **mà không cần sửa một ký tự trong Git**.

Ví dụ:

```xml
<dependency>
    <groupId>org.example.demo</groupId>
    <artifactId>greeting-lib</artifactId>
    <version>[1.0,2.0)</version>
</dependency>
```

Đây là đoạn XML nằm trong `<dependencies>` của POM, chưa phải một POM đầy đủ. Nó cho phép phiên bản từ `1.0` trở lên nhưng **không bao gồm `2.0`**. Nếu chỉ có `1.1` và `1.2` đáp ứng toàn bộ ràng buộc ở môi trường hiện tại, Maven có thể chọn `1.2`; khi một bản mới đáp ứng range xuất hiện và metadata được làm mới, phiên bản được chọn có thể khác.

> **Nguyên tắc cho build phát hành:** tránh dùng khoảng phiên bản mở hoặc thay đổi động nếu dự án yêu cầu tính tái lập. Ghi rõ phiên bản đã kiểm thử, quản lý phiên bản phụ thuộc bắc cầu và kiểm tra dependency graph sau thay đổi có chủ đích.

Bài học giải thích cú pháp version range của Maven, cơ chế chọn phiên bản, nguồn metadata, sự khác biệt giữa range và `SNAPSHOT`, các rủi ro khi dependency graph thay đổi, và một ví dụ Java 17 giúp quan sát cùng POM chọn hai phiên bản khác nhau sau khi local repository có thêm artifact.

## 1. Tọa độ Maven và yêu cầu phiên bản

Thông thường dependency được nhận diện bằng `groupId:artifactId:version`, cùng `type` và `classifier` khi cần. Với dependency khai báo:

```xml
<dependency>
    <groupId>org.example.demo</groupId>
    <artifactId>greeting-lib</artifactId>
    <version>1.1.0</version>
</dependency>
```

`greeting-lib` có một phiên bản được **đề xuất cụ thể** trong POM. Nhưng theo tài liệu Apache Maven về *Dependency Version Requirement Specification*, một chuỗi đơn như `1.1.0` được gọi là **soft requirement**, còn `[1.1.0]` là **hard requirement** chỉ chấp nhận đúng phiên bản đó. Vì vậy không nên diễn giải mọi chuỗi version cố định thành một ràng buộc cứng tuyệt đối nếu đồ thị có nhiều yêu cầu phiên bản cạnh tranh.

Phân biệt:

| Cách khai báo | Ý nghĩa | Mức độ linh hoạt |
| --- | --- | --- |
| `<version>1.1.0</version>` | Ưu tiên phiên bản 1.1.0 theo cơ chế soft requirement; đây là cách khai báo phiên bản cụ thể phổ biến. | Thông thường ổn định với dependency trực tiếp nếu không có ràng buộc cạnh tranh quan trọng. |
| `<version>[1.1.0]</version>` | Hard requirement chỉ cho phép 1.1.0. | Không cho phép chọn bản khác nếu có ràng buộc cứng không tương thích. |
| `<version>[1.1.0,2.0)</version>` | Hard requirement cho phép mọi version từ 1.1.0, dưới 2.0. | Có thể thay đổi phiên bản được chọn khi các bản khả dụng thay đổi. |
| `<version>[1.1.0,)</version>` | Cho phép 1.1.0 trở lên, không có giới hạn trên. | Rủi ro lớn hơn: có thể nhận cả major release mới. |
| `<version>(,2.0)</version>` | Cho phép mọi version nhỏ hơn 2.0, không có cận dưới. | Có thể chấp nhận bản rất cũ; cần chính sách bổ sung. |

**Lưu ý về thuật ngữ:** một version số duy nhất thường được gọi là “pin version” trong thực hành build vì nó không yêu cầu Maven tìm mọi version trong một khoảng. Nhưng theo đặc tả yêu cầu phiên bản của Maven, nó **khác `[version]` về tính cứng/mềm**. Trong các dự án thực tế, nên dùng version cụ thể kết hợp quản lý dependency và kiểm thử, thay vì dựa vào một cú pháp như bảo đảm duy nhất của tính tái lập.

## 2. Cú pháp version range: dấu ngoặc có ý nghĩa

Maven dùng dấu ngoặc vuông `[ ]` để **bao gồm** cận, ngoặc tròn `( )` để **loại trừ** cận, dấu phẩy để phân cách giới hạn.

| Cú pháp | Tập phiên bản cho phép |
| --- | --- |
| `[1.0,2.0]` | `1.0 ≤ v ≤ 2.0`. |
| `[1.0,2.0)` | `1.0 ≤ v < 2.0`. |
| `(1.0,2.0]` | `1.0 < v ≤ 2.0`. |
| `(1.0,2.0)` | `1.0 < v < 2.0`. |
| `[1.5,)` | `v ≥ 1.5`. |
| `(,1.5]` | `v ≤ 1.5`. |
| `[1.5]` | Chỉ một phiên bản `1.5`. |
| `(,1.0],[1.2,)` | Hai khoảng hợp lại: `v ≤ 1.0` **hoặc** `v ≥ 1.2`; loại khoảng giữa. |
| `(,1.1),(1.1,)` | Mọi phiên bản ngoài `1.1`; có thể dùng để loại phiên bản không mong muốn. |

Với `[1.0,2.0)`, các bản `1.0`, `1.2`, `1.9` có thể nằm trong range nếu Maven so sánh chúng theo thứ tự tương ứng, nhưng bản `2.0` bị loại. Tuy vậy, cần chú ý **qualifier**.

### 2.1. Không được nhầm range với SemVer thuần túy

Maven có quy tắc so sánh phiên bản riêng; nó **không cam kết rằng mọi chuỗi version đều tuân thủ hoàn hảo toàn bộ ngữ nghĩa Semantic Versioning**. Ví dụ, theo Maven POM Reference, `2.0-rc1` được xếp trước `2.0` và **có thể nằm trong `[1.0,2.0)`**. Nếu bạn muốn “chỉ series 1.x, không nhận bất kỳ bản 2.0 preview nào”, khoảng này có thể không đủ để diễn đạt ý muốn.

Ví dụ mô phỏng:

```text
Yêu cầu version: [1.0,2.0)
1.7.5         -> có thể được chấp nhận
1.9.0         -> có thể được chấp nhận
2.0-rc1       -> có thể được chấp nhận theo thứ tự Maven
2.0           -> bị loại vì cận trên mở
2.1.0         -> bị loại
```

Không tự viết logic phân tích version bằng cách tách chuỗi ở dấu chấm rồi so sánh số nguyên; qualifier như `alpha`, `beta`, `rc`, `SNAPSHOT` và cách chuẩn hóa version ảnh hưởng thứ tự thực tế. Khi cần chính sách version nghiêm ngặt, hãy chọn version cụ thể và kiểm tra với Maven/Resolver phiên bản đang sử dụng.

### 2.2. Range nhiều khoảng không có nghĩa một danh sách phiên bản cố định

Dạng:

```xml
<version>(,1.1),(1.1,)</version>
```

không có nghĩa “chọn 1.0 hoặc 1.2” mà có nghĩa **loại `1.1`, cho phép các version khác theo hai khoảng**. Khi repository xuất hiện version mới, nó có thể được chọn nếu thỏa các yêu cầu còn lại. Nếu cần danh sách chính xác vài version đã phê duyệt, hãy quản lý và kiểm soát version ở quy trình build thay vì giả định mọi khoảng là danh sách hữu hạn.

### 2.3. Trường hợp không có version nào phù hợp

Ví dụ POM yêu cầu `[1.5,2.0)` nhưng repository được phép truy cập chỉ có `1.4.0` hoặc `2.0.0`. Maven không thể giải quyết dependency theo range đó; build có thể báo lỗi không tìm được version phù hợp.

Nếu hai nhánh có **hard requirements mâu thuẫn**, chẳng hạn một nhánh chỉ chấp nhận `[1.0]`, nhánh còn lại chỉ chấp nhận `[2.0]` cho cùng một artifact, không tồn tại phiên bản chung và Maven có thể từ chối build. Không có quy tắc “luôn chọn newest” để vượt qua hard constraint.

## 3. Maven chọn version trong range từ đâu?

Để chọn một version thỏa range, Maven cần biết **những version nào đang khả dụng**. Dữ liệu này đến từ các repository mà Maven sử dụng, bao gồm local repository và những remote repository/mirror đã được cấu hình.

Trong một Maven repository theo layout phổ biến, metadata của một artifact có thể ở dạng:

```text
org/example/demo/greeting-lib/
    maven-metadata.xml
    1.1.0/
        greeting-lib-1.1.0.pom
        greeting-lib-1.1.0.jar
    1.2.0/
        greeting-lib-1.2.0.pom
        greeting-lib-1.2.0.jar
```

Nội dung metadata minh họa:

```xml
<metadata>
    <groupId>org.example.demo</groupId>
    <artifactId>greeting-lib</artifactId>
    <versioning>
        <versions>
            <version>1.1.0</version>
            <version>1.2.0</version>
        </versions>
    </versioning>
</metadata>
```

Đây là **mô hình XML rút gọn**, không phải metadata đầy đủ được cam kết ở một repository cụ thể. `maven-metadata.xml` giúp Maven biết những version có sẵn; tuy vậy **metadata không thay thế POM/JAR thật**. Build cũng cần giải quyết được artifact, metadata parent của nó và dependencies liên quan.

Tùy Maven/Resolver, chính sách repository và cache, quá trình thường liên quan tới:

1. Đọc effective POM để xác định dependency và các version requirements.
2. Xác định repository/mirror phù hợp, bao gồm local cache.
3. Dùng metadata để tìm các version ứng viên có thể thỏa range.
4. Kết hợp hard/soft requirements, dependency management và các ràng buộc của những nhánh.
5. Chọn các artifact cần thiết, tải/đọc POM của chúng để thu thập transitive dependencies.
6. Hòa giải xung đột và dựng đồ thị kết quả cho project.

Sơ đồ ở trên mang tính **khái niệm**. Maven Resolver thực hiện collection, conflict resolution và nhiều bước khác; không nên xem đây là thứ tự cố định của mọi phiên bản triển khai nội bộ.

**Điều quyết định:** tập version ứng viên **là dữ liệu bên ngoài POM**. Vì vậy một range khiến kết quả phụ thuộc nhiều hơn vào trạng thái repository.

## 4. Vì sao dependency graph thay đổi theo thời gian?

Giả sử dự án không sửa `pom.xml`:

```xml
<dependency>
    <groupId>org.example.demo</groupId>
    <artifactId>greeting-lib</artifactId>
    <version>[1.0,2.0)</version>
</dependency>
```

Ở các thời điểm giả định:

| Thời điểm | Các version phù hợp được biết đến | Version có thể được chọn | Hệ quả |
| --- | --- | --- | --- |
| T1 | `1.1.0` | `1.1.0` | Đồ thị dùng POM và dependency metadata của bản 1.1.0. |
| T2 | `1.1.0`, `1.2.0` | `1.2.0` | Có thể xuất hiện dependency mới hoặc thay đổi version transitive. |
| T3 | `1.1.0`, `1.2.0`, `1.3.0` | `1.3.0` | API, bytecode, giấy phép, scope hoặc phụ thuộc bắc cầu có thể khác. |

Bảng giả định **không có ràng buộc cạnh tranh khác**, không có quản lý version can thiệp và Maven nhìn thấy cùng repository metadata cập nhật. Nếu có dependencyManagement, hard requirements khác hoặc cache chưa làm mới, version được chọn có thể khác bảng.

Sự thay đổi không dừng ở một node:

```text
Ở T1:
app
└── greeting-lib:1.1.0
    └── codec:1.0.0

Ở T2:
app
└── greeting-lib:1.2.0
    ├── codec:2.0.0
    └── audit-api:1.0.0
```

Đây là **đồ thị minh họa**; tên artifact và version không khẳng định có thật trên Maven Central. Nếu nhà cung cấp thư viện thay đổi dependencies giữa hai release, Maven có thể mang một tập JAR khác vào ứng dụng mà không thay đổi POM app. Điều đó có thể tác động:

- Kết quả compile và các lỗi thiếu method/class.
- Hành vi runtime, cấu hình mặc định, dữ liệu tuần tự hóa.
- Kích thước artifact, image hoặc distribution.
- Tập thư viện chịu kiểm tra an ninh, giấy phép và SBOM.
- Kết quả unit/integration tests, hiệu năng và tương thích nền tảng.
- Thứ tự conflict mediation, nearest-definition và dependencyManagement.

Vì vậy, **không có commit thay đổi** không đủ để kết luận **build giống hệt**.

## 5. Thử nghiệm có thể chạy: cùng POM, hai phiên bản thư viện

Ví dụ này sử dụng **JDK 17+ và Maven 3.x tương thích** để tạo hai bản release giả của cùng một thư viện, cài lần lượt vào **local Maven repository**, rồi quan sát app dùng một version range.

Mục tiêu là minh họa *version resolution* khi **tập artifact khả dụng thay đổi**. Đây là lab dùng tọa độ nội bộ giả lập; nó **không publish lên remote repository** và không cần truy cập dịch vụ ngoài cho thư viện mẫu. Maven vẫn có thể cần tải plugins một lần nếu cache chưa có.

### 5.1. Cấu trúc thư mục

```text
version-range-lab/
├── lib-11/
│   ├── pom.xml
│   └── src/main/java/org/example/range/Greeter.java
├── lib-12/
│   ├── pom.xml
│   └── src/main/java/org/example/range/Greeter.java
└── app/
    ├── pom.xml
    └── src/main/java/org/example/app/App.java
```

Hai thư mục `lib-11` và `lib-12` chứa **cùng groupId/artifactId** nhưng **khác version**. Chúng là **hai release của một artifact**, không phải hai module phải cùng lúc được khai báo trong một aggregator. App dùng version range và sẽ chỉ có **một version được chọn** cho dependency này trong classpath thông thường.

Tạo cấu trúc bằng IDE/editor, hoặc dùng terminal:

Linux/macOS:

```bash
mkdir -p version-range-lab/lib-11/src/main/java/org/example/range
mkdir -p version-range-lab/lib-12/src/main/java/org/example/range
mkdir -p version-range-lab/app/src/main/java/org/example/app
cd version-range-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "version-range-lab/lib-11/src/main/java/org/example/range" | Out-Null
New-Item -ItemType Directory -Force "version-range-lab/lib-12/src/main/java/org/example/range" | Out-Null
New-Item -ItemType Directory -Force "version-range-lab/app/src/main/java/org/example/app" | Out-Null
Set-Location version-range-lab
```

### 5.2. Phiên bản thư viện đầu tiên: `lib-11/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.range.training</groupId>
    <artifactId>greeter-lib</artifactId>
    <version>1.1.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
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

Tệp `lib-11/src/main/java/org/example/range/Greeter.java`:

```java
package org.example.range;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Greeting library version 1.1.0";
    }
}
```

Đây là chương trình **thư viện** nên không có `main`; Maven tạo JAR chứa class `Greeter` khi chạy `package` hoặc `install`.

### 5.3. Phiên bản thư viện mới: `lib-12/pom.xml`

POM thứ hai có tọa độ giống bản đầu nhưng **version 1.2.0**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.range.training</groupId>
    <artifactId>greeter-lib</artifactId>
    <version>1.2.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
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

Tệp `lib-12/src/main/java/org/example/range/Greeter.java`:

```java
package org.example.range;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Greeting library version 1.2.0";
    }
}
```

Hai JAR có cùng FQCN `org.example.range.Greeter` nhưng khác nội dung phương thức `message()`. Đây là thay đổi cố ý để quan sát **chính xác JAR mà app đã nhận**.

### 5.4. POM của ứng dụng: `app/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.range.training</groupId>
    <artifactId>range-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.example.range.training</groupId>
            <artifactId>greeter-lib</artifactId>
            <version>[1.1.0,1.3.0)</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Range `[1.1.0,1.3.0)` cho phép `1.1.0` và `1.2.0`, nhưng không cho phép `1.3.0`. Nó **không có nghĩa chỉ cho phép đúng hai bản này**: nếu có `1.2.5` hoặc một release candidate phù hợp trong repository, Maven cũng phải xét version đó. Lab giả định **không có version cạnh tranh khác** trong các repository được phép truy cập.

Tệp `app/src/main/java/org/example/app/App.java`:

```java
package org.example.app;

import org.example.range.Greeter;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
```

Code app không kiểm tra version rồi rẽ nhánh: nó chỉ gọi một API từ dependency. Chính dependency resolution quyết định phương thức `Greeter.message()` nào có mặt.

### 5.5. Lần chạy thứ nhất: chỉ cài bản 1.1.0

Để kết quả dễ tái hiện, bắt đầu trên môi trường lab **chưa có bất kỳ artifact `org.example.range.training:greeter-lib` nào**; các repository remote cũng không có artifact trùng tọa độ. Nếu local cache có bản 1.2.0 từ trước, bước này **không còn minh họa trạng thái “chỉ có 1.1.0”**. Có thể dùng một local repository riêng cho lab, nhưng phải dùng nhất quán trong mọi lệnh Maven và vẫn cho Maven tải plugin cần thiết.

Từ thư mục `version-range-lab`:

```bash
mvn -B -ntp -f lib-11/pom.xml clean install
mvn -B -ntp -f app/pom.xml clean package dependency:copy-dependencies
mvn -B -ntp -f app/pom.xml dependency:tree -Dincludes=org.example.range.training:greeter-lib
```

`install` đưa thư viện `1.1.0` vào local Maven repository. `dependency:copy-dependencies` của Maven Dependency Plugin đưa dependency được chọn vào `app/target/dependency` theo cấu hình mặc định. `clean` ở đầu lần build app giúp xóa bản artifact cũ trước khi copy dependency mới.

Kết quả được mong đợi trong cây dependency, về mặt nội dung (các dòng log và indent cụ thể có thể khác):

```text
org.example.range.training:greeter-lib:jar:1.1.0:compile
```

Chạy app trên Linux/macOS:

```bash
java -cp "app/target/classes:app/target/dependency/*" org.example.app.App
```

Windows PowerShell:

```powershell
java -cp "app\target\classes;app\target\dependency\*" org.example.app.App
```

**Stdout chính xác của ứng dụng Java trong trạng thái lab này:**

```text
Greeting library version 1.1.0
```

Classpath dùng wildcard `*` để nạp các JAR trong thư mục dependency; cách JVM xử lý wildcard và dấu phân cách là độc lập với Maven POM. Trên Windows dùng `;`, trên Linux/macOS dùng `:`.

### 5.6. Lần chạy thứ hai: thêm bản 1.2.0, không sửa POM app

Từ cùng thư mục `version-range-lab`:

```bash
mvn -B -ntp -f lib-12/pom.xml clean install
mvn -B -ntp -f app/pom.xml clean package dependency:copy-dependencies
mvn -B -ntp -f app/pom.xml dependency:tree -Dincludes=org.example.range.training:greeter-lib
```

Lần này local Maven repository có **hai release** `1.1.0` và `1.2.0` của cùng artifact, trong khi `app/pom.xml` vẫn giữ nguyên range `[1.1.0,1.3.0)`. Nếu không có constraint/repository đặc biệt khác, Maven có thể chọn `1.2.0` vì đây là bản phù hợp cao hơn.

Một dòng dependency tree được mong đợi:

```text
org.example.range.training:greeter-lib:jar:1.2.0:compile
```

Lệnh chạy tương tự:

Linux/macOS:

```bash
java -cp "app/target/classes:app/target/dependency/*" org.example.app.App
```

Windows PowerShell:

```powershell
java -cp "app\target\classes;app\target\dependency\*" org.example.app.App
```

**Stdout chính xác theo trạng thái lab thứ hai:**

```text
Greeting library version 1.2.0
```

**Điều đã thay đổi:** thư viện phiên bản mới xuất hiện trong tập ứng viên Maven nhìn thấy. **Điều không thay đổi:** source code `App.java`, dependency range trong POM app và lệnh build. Đây là ví dụ trực tiếp cho rủi ro **đồ thị thay đổi theo thời gian**.

Nếu kết quả thực tế khác, không được kết luận Maven “hỏng”. Hãy kiểm tra đã cài đúng artifact vào cùng local repository chưa, có bản cao hơn trong range không, remote metadata nào được đọc, có `dependencyManagement` can thiệp không và plugin đang chạy với profile/settings nào.

### 5.7. Quan sát sự khác biệt thay vì chỉ nhìn stdout

Chạy:

```bash
mvn -f app/pom.xml dependency:tree
```

Mỗi lần chạy cho biết phiên bản `greeter-lib` mà Maven dùng. Ngoài ra có thể xem danh sách JAR sau bước `dependency:copy-dependencies`:

Linux/macOS:

```bash
ls app/target/dependency
```

Windows PowerShell:

```powershell
Get-ChildItem app/target/dependency
```

Tên file kỳ vọng tương ứng là `greeter-lib-1.1.0.jar` hoặc `greeter-lib-1.2.0.jar`. Không nên dựa riêng vào tên file để đánh giá bytecode trong sản phẩm; kết hợp cây dependency, checksum (khi cần), tests và kết quả thực thi.

**Giới hạn lab:** việc cài hai phiên bản local không hoàn toàn mô phỏng repository manager thực và chính sách metadata của mạng. Nó cho thấy rủi ro chọn version khác nhau khi tập phiên bản có thể giải quyết thay đổi, chứ không chứng minh mọi build online đều tự nâng version ngay lập tức.

## 6. Dependency version range khác gì dependency bắc cầu và xung đột?

Một project có thể có cả **version range** lẫn nhiều đường dẫn tới cùng artifact:

```text
application
├── adapter-a:1.0
│   └── codec:[1.0,3.0)
└── adapter-b:1.0
    └── codec:2.1.0
```

Ở đây:

- `adapter-a` yêu cầu một **khoảng version** của codec.
- `adapter-b` đưa ra yêu cầu version cụ thể `2.1.0`.
- Maven còn phải xét constraint nào mềm/cứng, đường đi nào gần root, `dependencyManagement` và các ràng buộc còn lại.
- Không thể kết luận chỉ từ hình rằng “Maven chắc chắn lấy latest” hoặc “Maven chắc chắn dùng 2.1.0” trong mọi cấu hình.

### 6.1. Nearest definition không có nghĩa luôn dùng newest

Với các soft requirements, Maven thường dùng nguyên tắc **nearest definition**: khi hai dependency yêu cầu những phiên bản khác nhau của cùng artifact, định nghĩa gần root hơn được ưu tiên; nếu cùng độ sâu, khai báo đầu tiên thường thắng. Điều này giải thích nhiều tình huống mà một phiên bản cũ hơn được chọn dù có bản mới hơn ở nhánh sâu.

Ví dụ riêng về mediation:

```text
app
├── library-a
│   └── codec:1.4.0
└── library-b
    └── helper
        └── codec:2.2.0
```

Không có constraint cứng/dependency management can thiệp, đường `app -> library-a -> codec` gần root hơn, nên `codec:1.4.0` có thể được chọn thay vì `2.2.0`.

**Không áp dụng mù quáng** nearest-wins để bỏ qua hard version ranges. Theo Maven POM Reference, hard requirements giới hạn tập version hợp lệ; nếu không có version thỏa tất cả hard requirements, Maven có thể thất bại.

### 6.2. DependencyManagement có thể thay đổi lựa chọn

Parent POM hoặc chính ứng dụng có thể có:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.codec</groupId>
            <artifactId>codec</artifactId>
            <version>2.2.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn quản lý dependency**, không tự đưa `codec` vào classpath. Khi `codec` được yêu cầu trong graph, quy tắc management có thể điều chỉnh phiên bản và thường có ưu tiên đối với transitive dependencies so với dependency mediation. Tuy nhiên, **version cụ thể trong management cũng không phải giấy phép bỏ qua mọi hard requirement mâu thuẫn**: nếu graph có constraint không thể thỏa, Maven có thể báo lỗi.

Một BOM được import qua `<dependencyManagement>` là cách quản lý một bộ version tương thích, nhưng **BOM không tự tạo tất cả các dependency** và không bảo đảm rằng dependency graph bất biến nếu vẫn còn range hoặc metadata động ở nơi khác.

### 6.3. Sự thay đổi có thể đến từ nhiều tầng

Một build phụ thuộc:
- POM app và POM cha.
- BOM/dependencyManagement và version expressions.
- Dependency ranges trực tiếp hoặc bắc cầu.
- POM metadata của từng artifact đã chọn.
- Repository/mirror và phiên bản artifact thực có thể truy cập.
- Version Maven/Resolver và cấu hình chọn profile.
- Các tham số `-D`, settings và chính sách cache.

Vì vậy, khi hai build khác nhau, không nên chỉ so mỗi `pom.xml` của ứng dụng. Cần so **effective POM**, **dependency tree** và **môi trường resolution**.

## 7. Update policy, cache và lý do version không đổi ngay lập tức

Repository metadata không nhất thiết được Maven tải lại ở **mỗi lần chạy**. Maven có local cache và các chính sách cập nhật theo repository.

Trong `settings.xml` hoặc cấu hình repository thích hợp, `updatePolicy` có thể nhận:

| Giá trị | Ý nghĩa thực dụng |
| --- | --- |
| `always` | Cho phép kiểm tra cập nhật thường xuyên. |
| `daily` | Kiểm tra theo chu kỳ hằng ngày; là mặc định phổ biến theo Maven Settings Reference. |
| `interval:30` | Kiểm tra theo chu kỳ khoảng 30 phút. |
| `never` | Không chủ động kiểm tra lại sau khi đã có dữ liệu trong điều kiện cấu hình đó. |

Thời điểm Maven nhìn thấy phiên bản mới có thể phụ thuộc **repository policy, local cache, phản hồi từ mirror/proxy, offline mode và việc metadata cập nhật có thành công hay không**.

Ví dụ giả định:

```text
T1: repository có greeting-lib 1.1.0
T2: repository publish greeting-lib 1.2.0
T2+1 phút:
    Máy A còn metadata cũ -> có thể vẫn dùng 1.1.0
    Máy B tải metadata mới -> có thể dùng 1.2.0
T3: metadata A được làm mới -> A có thể chọn 1.2.0
```

Đây là biểu diễn **khả năng xảy ra**, không phải lịch cập nhật bắt buộc của mọi Maven version. Kể cả khi dùng chung Git commit, hai runner có local cache và network khác nhau có thể không thấy cùng tập version ứng viên.

### `-U` có phải khóa version không?

Không. `mvn -U ...` yêu cầu Maven buộc kiểm tra cập nhật SNAPSHOT và những trường hợp update theo hành vi phiên bản Maven; nó **không khóa dependency graph**. Việc làm mới metadata/kiểm tra cập nhật có thể làm **lộ ra version mới** trong range. Ngược lại, `-o` (offline) chỉ dựa vào artifact/metadata local sẵn có và có thể thất bại nếu thiếu dependency; **offline cũng không phải cơ chế bảo đảm cùng graph trên mọi máy**, vì mỗi máy có cache khác nhau.

Không dùng “thêm `-U`”, “chạy offline” hoặc “xóa cache ngẫu nhiên” như lời giải đầy đủ cho build không tái lập. Hãy kiểm soát version và repository trước.

## 8. Version range, SNAPSHOT và phiên bản động: ba rủi ro khác nhau

| Cơ chế | Điều có thể thay đổi | Vì sao cần thận trọng? |
| --- | --- | --- |
| `[1.0,2.0)` | Version **được chọn** có thể đổi khi version mới thỏa range xuất hiện. | Cùng POM có thể nhận JAR/POM metadata khác. |
| `1.2.0-SNAPSHOT` | **Nội dung binary** của cùng base version SNAPSHOT có thể được cập nhật ở repository. | Ngay cả khi chuỗi version không đổi, timestamped snapshot/build có thể khác. |
| `LATEST` / `RELEASE` hoặc cơ chế “latest” cũ | Phụ thuộc vào metadata mới nhất; các biểu thức đặc biệt này không nên dùng như giải pháp build hiện đại. | Rủi ro khó tái lập và tương thích khác nhau theo Maven version; nhiều cơ chế đã bị hạn chế/không khuyến nghị. |

**Version range không phải SNAPSHOT**, nhưng một range có thể chứa các bản có qualifier `SNAPSHOT`/prerelease tùy cú pháp và thứ tự Maven. Nếu yêu cầu chỉ dùng releases đã được kiểm thử, **không đủ** khi bạn chỉ nhìn cận trên/cận dưới: cần chính sách repository, lựa chọn version cụ thể và quy tắc kiểm duyệt artifact.

Release artifact lý tưởng nên **bất biến** (*immutable*) tại một GAV. Tuy nhiên, trên repository cấu hình kém, người có quyền có thể ghi đè release hoặc thay POM metadata đã publish. Việc pin version mà artifact bị thay bytecode vẫn làm mất tính tái lập. Vì vậy cần cả **chính sách repository bất biến** và kiểm tra tính toàn vẹn.

## 9. Rủi ro với API, binary và runtime

Một version mới nằm trong range có thể:

1. **Xóa hoặc đổi API** khiến mã Java compile thất bại.
2. **Giữ API compile nhưng đổi behavior** khiến test hoặc nghiệp vụ sai.
3. **Thay transitive dependencies** làm xung đột với những thư viện còn lại.
4. **Tăng Java bytecode target**, ví dụ thư viện mới đòi JDK cao hơn môi trường CI.
5. **Thêm native library hoặc yêu cầu môi trường khác**, gây lỗi runtime trên hệ điều hành/container nhất định.
6. **Đổi logging, serialization hoặc timezone handling**, gây khác biệt dù source app không đổi.
7. **Mang giấy phép mới hoặc phụ thuộc có lỗ hổng**, ảnh hưởng chính sách release.
8. **Thay plugin hoặc cơ chế code generation** nếu sự thay đổi nằm trong plugin dependencies hay extension thay vì project dependencies.

Ví dụ một ứng dụng được compile dựa trên `codec:1.4` nhưng runtime nạp `codec:2.0` có thể gặp `NoSuchMethodError` nếu API không còn tương thích. Cũng có thể ngược lại: compile sử dụng API mới nhưng runtime chỉ có JAR cũ, gây `NoClassDefFoundError` hoặc lỗi khác. Không nên tự kết luận mọi lần chọn version cao hơn đều an toàn.

Chẩn đoán phải xem **dependency tree đã giải quyết, classpath thực, báo cáo test và artifact cuối**. Một dòng `BUILD SUCCESS` chỉ cho biết lệnh Maven báo hoàn thành theo các bước/cấu hình đã chạy.

## 10. Quan sát và lưu bằng chứng đồ thị dependency

Maven Dependency Plugin cung cấp goal `dependency:tree`:

```bash
mvn -B -ntp dependency:tree
```

Khi repository có nhiều module, chọn đúng POM:

```bash
mvn -B -ntp -f app/pom.xml dependency:tree
```

Trong lab, nếu muốn chỉ xem `greeter-lib`:

```bash
mvn -B -ntp -f app/pom.xml dependency:tree -Dincludes=org.example.range.training:greeter-lib
```

Một cây dependency cho bạn biết **phiên bản thực đã được Maven chọn trong lần giải quyết đó**, chứ không chỉ version range được viết trong POM. Nếu artifact không có trong tree khi dùng bộ lọc, kiểm tra scope, optional, exclusions, management và phiên bản plugin trước khi kết luận dependency vắng mặt.

### 10.1. Xuất cây ở định dạng máy đọc

Tùy phiên bản Maven Dependency Plugin, có thể xuất DOT hoặc định dạng cấu trúc khác:

```bash
mvn -f app/pom.xml dependency:tree -DoutputType=dot -DoutputFile=dependency-tree.dot
```

Tệp DOT mô tả node/edge bằng văn bản; muốn xem hình cần công cụ hiển thị DOT như Graphviz. Với Maven Dependency Plugin hỗ trợ JSON:

```bash
mvn -f app/pom.xml dependency:tree -DoutputType=json -DoutputFile=dependency-tree.json
```

JSON output được hỗ trợ từ Maven Dependency Plugin **3.7.0 trở lên**. Không mặc định môi trường Maven cũ có tham số này; xem tài liệu của phiên bản plugin đang dùng.

Một quy trình kiểm tra biến động:

1. Chạy build tại commit đã biết và lưu cây dependency sau resolution.
2. Chạy build ở thời điểm khác hoặc sau thay đổi metadata.
3. So sánh GAV/type/classifier/scope của những artifact quan trọng.
4. Tìm node được thêm/xóa, version đổi, scope đổi.
5. Kiểm tra những POM dependency mới đưa node đó vào.
6. Chạy tests, quét lỗ hổng và xem SBOM khi được yêu cầu.

**Một file tree hoặc SBOM là ảnh chụp của một lần giải quyết**, không tự khóa tương lai. Lưu chúng làm bằng chứng hữu ích nhưng cần pin version/chính sách repository để kiểm soát lần build tiếp theo.

### 10.2. `help:effective-pom` có đủ không?

`mvn help:effective-pom` cho biết mô hình project đã tổng hợp (inheritance, profiles, management...), nhưng **không phải thay thế hoàn toàn cho `dependency:tree`**. Effective POM có thể vẫn chứa một version range ở khai báo; nó không phải bản tóm tắt đầy đủ mọi artifact đã được tải và chọn sau dependency resolution.

Khi debug version range, dùng cả hai:
- **Effective POM:** tìm range đó đến từ POM nào, parent hay profile nào.
- **Dependency tree:** xem version thực tế đã được giải quyết, đường đi và scope.

Nếu lỗi liên quan repository/mirror, kiểm tra thêm `help:effective-settings` và log resolution nhưng không chia sẻ settings chứa bí mật.

## 11. Cách chuyển version range thành phiên bản kiểm soát được

Giả sử project đang khai báo:

```xml
<dependency>
    <groupId>org.example.range.training</groupId>
    <artifactId>greeter-lib</artifactId>
    <version>[1.1.0,1.3.0)</version>
</dependency>
```

Sau khi kiểm tra dependency tree và test phiên bản `1.2.0`, một lựa chọn cho build release là thay bằng:

```xml
<dependency>
    <groupId>org.example.range.training</groupId>
    <artifactId>greeter-lib</artifactId>
    <version>1.2.0</version>
</dependency>
```

Đây là cách khai báo một version cụ thể phổ biến, làm giảm nguy cơ tự động chọn phiên bản mới chỉ vì repository xuất hiện thêm release. Tuy nhiên, như đã giải thích ở mục 1, chuỗi đơn là soft requirement trong đặc tả Maven; sự ổn định của toàn đồ thị còn cần quản lý transitive conflicts.

Nếu cần một hard requirement duy nhất, cú pháp `[1.2.0]` biểu diễn điều đó, nhưng không nhất thiết phải dùng cho mọi dependency thông thường. **Không nên đổi toàn bộ POM sang `[x]` một cách máy móc** mà chưa xem khả năng hợp nhất với BOM, quản lý transitive và các ràng buộc hiện hữu.

### 11.1. Quản lý phiên bản trong parent POM

Với nhiều module dùng cùng thư viện, có thể đặt version trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example.range.training</groupId>
            <artifactId>greeter-lib</artifactId>
            <version>1.2.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Từng module sử dụng thực sự vẫn khai báo dependency:

```xml
<dependencies>
    <dependency>
        <groupId>org.example.range.training</groupId>
        <artifactId>greeter-lib</artifactId>
    </dependency>
</dependencies>
```

`dependencyManagement` không tự thêm artifact vào classpath. Nó cung cấp quy tắc khi một dependency được tham chiếu phù hợp, giúp các module không tự do viết những version ranges khác nhau cho cùng artifact.

### 11.2. BOM không phải lockfile

Import BOM theo `type=pom`, `scope=import` có thể cung cấp tập version tương thích, nhất là với framework lớn. Nhưng **import BOM không tự bảo đảm toàn bộ đồ thị được khóa tuyệt đối**: app vẫn có thể khai báo range ở một nơi khác, transitive graph của các version đã chọn có thể khác, và repository artifacts phải ổn định.

Maven core không mặc định tạo và sử dụng một **lockfile dependency phổ quát giống `package-lock.json`** chỉ từ POM. Nếu tổ chức muốn khóa danh sách artifact thực đã giải quyết, cần chọn công cụ/quy trình hỗ trợ, quản lý những kết quả đó và xác minh trên CI; không tự giả định lưu một cây `dependency:tree` có thể khiến Maven tái sử dụng chính xác cây đó ở lần build sau.

### 11.3. Quản lý plugin và môi trường build

Ngay cả khi tất cả project dependencies đã pin, build vẫn có thể thay đổi nếu:
- Maven plugins không được pin version phù hợp.
- JDK/toolchain khác giữa CI và local.
- Profile, settings, mirrors hoặc repository khác nhau.
- Artifact release bị ghi đè, snapshot được làm mới.
- Build dùng timestamp, dữ liệu môi trường hoặc quy trình packaging không tái lập.

Vì thế cần quản lý cả **Maven Wrapper/version**, JDK, plugin versions và các nguồn đầu vào khác. Dependency range là một nguồn biến động quan trọng, nhưng không phải nguồn duy nhất.

## 12. Khi nào version range có thể chấp nhận được?

Version range không phải lúc nào cũng sai. Nó có thể hợp lý trong những tình huống có chủ đích, ví dụ:

- Một **thư viện/extension** được thiết kế tương thích với nhiều bản API và có bộ kiểm thử ma trận phiên bản.
- Một **tool thử nghiệm** muốn tự tìm version mới trong một series để chạy compatibility testing.
- Một quy trình kiểm thử/nightly **chủ động phát hiện phiên bản mới** và báo thay đổi dependency.
- Một môi trường chạy plugin do nền tảng quản trị, cần biểu diễn một tập version được hỗ trợ hơn là một build phát hành cố định.

Trong các trường hợp này, phải chấp nhận rằng dependency graph có thể thay đổi, và bổ sung:
- CI ghi rõ version thực đã chọn.
- Test nhiều version ở ranh giới/phiên bản mục tiêu.
- Chính sách repository, checksum, nguồn gốc artifact.
- Cơ chế cảnh báo khi graph thay đổi.
- Hạn chế phát hành tự động khi có version chưa được kiểm thử.
- Quy trình review việc nới cận range.

**Không sử dụng range rộng như `[1.0,)` chỉ để “tự động có bản mới nhất” trên một hệ thống cần khả năng triển khai đáng tin cậy.** Điều đó biến repository metadata thành một phần không được review của quyết định thay đổi phần mềm.

## 13. Các lỗi thường gặp

### Lỗi 1 — Hiểu `[1.0,2.0)` là “chỉ nhận version 1.x ổn định”

Maven có quy tắc so sánh qualifier; `2.0-rc1` có thể nằm dưới `2.0` và được range chấp nhận. **Cách tránh:** kiểm tra dữ liệu version thực tế hoặc dùng version cụ thể theo chính sách release.

### Lỗi 2 — Tin rằng cùng POM thì dependency tree bất biến

Một version mới có thể xuất hiện ở repository; cache/metadata được làm mới ở thời điểm khác. **Cách tránh:** pin các version cần thiết và lưu/so graph trước–sau.

### Lỗi 3 — Nhầm `1.2.0` và `[1.2.0]` là một loại requirement

Theo đặc tả Maven, `1.2.0` là soft requirement còn `[1.2.0]` là hard requirement chỉ version đó. **Cách tránh:** đọc rõ syntax và hiểu conflict resolution.

### Lỗi 4 — Cho rằng Maven luôn chọn version cao nhất bất kể graph

Hard requirements, nearest definition, dependencyManagement và những nhánh khác đều ảnh hưởng quyết định. **Cách tránh:** dùng `dependency:tree` của đúng module và đúng profile.

### Lỗi 5 — Dùng `-U` để “giữ build ổn định”

`-U` không khóa version, có thể làm dữ liệu được làm mới và khiến range chọn bản khác. **Cách tránh:** giữ version đã phê duyệt và quản lý repository.

### Lỗi 6 — Dùng `-o` làm phương án khóa dependency

Offline chỉ dựa vào cache local, không đảm bảo hai máy có cache giống nhau. **Cách tránh:** dùng quy trình artifact provenance, repository bất biến và version rõ ràng.

### Lỗi 7 — Chỉ nhìn tên JAR trực tiếp, bỏ qua transitive dependencies

Khi một thư viện đổi từ 1.1 lên 1.2, POM của nó có thể đổi `dependencies`, tạo graph khác. **Cách tránh:** so toàn bộ tree, không chỉ node gốc.

### Lỗi 8 — Chỉ xem effective POM rồi cho rằng đã biết version được giải quyết

Effective POM phản ánh mô hình; dependency resolution còn có metadata, repository và conflict mediation. **Cách tránh:** xem thêm `dependency:tree`.

### Lỗi 9 — Không quản lý dependencyManagement/BOM thống nhất

Các module tự dùng version ranges rộng khác nhau có thể đưa về những lựa chọn khó đoán. **Cách tránh:** dùng parent BOM/management nhất quán và kiểm thử.

### Lỗi 10 — Dùng SNAPSHOT cho build release nhưng tưởng version “cố định”

Một tọa độ `1.2.0-SNAPSHOT` có thể thay binary theo thời điểm. **Cách tránh:** dùng release artifacts bất biến và kiểm tra provenance.

### Lỗi 11 — Chọn version mới nhất theo số mà bỏ qua API compatibility

“Newer” không chứng minh “compatible”. **Cách tránh:** đọc release notes, kiểm tra bytecode/JDK và chạy tests.

### Lỗi 12 — Không biết repository mirror mà Maven thực tế sử dụng

Mirror có cache và update policy riêng; hai môi trường có thể nhìn thấy metadata khác. **Cách tránh:** kiểm tra settings/repository resolution một cách an toàn, không lộ credentials.

### Lỗi 13 — Bỏ qua hard requirement conflict

Một range yêu cầu `[1.0]` và range khác yêu cầu `[2.0]` không có giao. **Cách tránh:** không dùng exclusions hoặc override bừa bãi; điều chỉnh dependency compatibility theo tài liệu và kiểm thử.

### Lỗi 14 — Cho rằng SBOM hoặc log là công cụ pin version

SBOM/tree giúp kiểm toán kết quả **đã xảy ra**, không bắt Maven tự lặp lại lựa chọn ấy. **Cách tránh:** version management, repository bất biến và CI policy.

## 14. Quy trình chẩn đoán khi build hôm nay khác hôm qua

**Bước 1 — Chọn cùng mã nguồn.** Đối chiếu Git commit, POM/parent/BOM, Maven Wrapper và JDK của hai lần build.

**Bước 2 — Ghi các tham số thực sự dùng.** Xem `-P`, `-D`, `-s`, `-o`, `-U`, profile, settings và repository mirror. Đừng công khai password/token.

**Bước 3 — Xem effective POM.** Xác định version ranges ở direct dependencies và các giá trị được kế thừa/quản lý.

**Bước 4 — Xem dependency tree của module bị ảnh hưởng.** Dùng `mvn -f path/to/pom.xml dependency:tree` rồi so GAV/version/scope giữa hai lần build.

**Bước 5 — Xem artifact mới có nằm trong range không.** Kiểm tra metadata/repository history trong kênh quản trị. Không tự chỉnh metadata repository bằng tay.

**Bước 6 — Kiểm tra cache và update policy.** Hai máy có thể khác vì metadata local và chính sách cập nhật khác; không xóa cache đại trà trước khi lưu bằng chứng nguyên nhân.

**Bước 7 — Xác định mọi nhánh transitive bị thay.** Nếu phiên bản một JAR thay đổi, POM của version mới có thể thêm/bỏ dependencies. Xem `dependency:tree` và báo cáo quét bảo mật.

**Bước 8 — Kiểm tra lỗi thực tế.** Chạy compile, unit tests, integration tests và xác minh runtime classpath; không suy đoán chỉ từ version string.

**Bước 9 — Pin version và thống nhất management.** Thay range ở những nơi cần tính tái lập, review các quyết định conflict và kiểm tra effective graph.

**Bước 10 — Khôi phục build có thể kiểm chứng.** Chạy trên runner sạch có quyền truy cập repository được phê duyệt; ghi lại dependency tree/SBOM và artifact checksum cho quy trình phát hành nếu cần.

Không cần chờ lỗi xảy ra mới so graph. Một bước CI tạo báo cáo dependencies sau mỗi lần nâng version giúp phát hiện khác biệt có chủ đích sớm hơn.

## 15. Bài tập tự kiểm tra

**Câu 1.** Dependency có `<version>[1.0,2.0)</version>`. Theo Maven, version 2.0.0 có được chấp nhận không?

**Đáp án:** Không, vì cận trên là ngoặc tròn, loại phiên bản bằng 2.0. Tuy vậy, qualifier trước 2.0 như `2.0-rc1` có thể được xếp nhỏ hơn 2.0 và nằm trong range.

**Câu 2.** Cùng POM dùng `[1.0,2.0)`. Tuần trước repository có 1.1, tuần này có thêm 1.2. Điều gì có thể thay đổi?

**Đáp án:** Khi Maven nhìn thấy metadata mới và không có ràng buộc khác, nó có thể chọn 1.2 thay vì 1.1. POM và source code không đổi nhưng dependency graph có thể khác.

**Câu 3.** `<version>1.2.0</version>` và `<version>[1.2.0]</version>` có giống hệt nhau trong đặc tả Maven không?

**Đáp án:** Không. Chuỗi đơn là soft requirement; ngoặc vuông một giá trị biểu diễn hard requirement chỉ chấp nhận đúng version đó.

**Câu 4.** Tại sao build có thể khác nhau giữa máy A và B dù chúng cùng checkout một commit?

**Đáp án:** Local cache, repository/mirror, metadata, update policy, Maven/JDK, profile và settings có thể khác; version range còn khiến tập phiên bản khả dụng ảnh hưởng lựa chọn.

**Câu 5.** Nếu project dùng version range, chỉ kiểm tra `help:effective-pom` đã đủ để biết JAR nào chạy thực tế chưa?

**Đáp án:** Chưa. Cần xem `dependency:tree` và khi cần cả runtime classpath; effective POM không thay thế kết quả dependency resolution.

**Câu 6.** App phụ thuộc A với range, A phiên bản mới thay đổi dependency B từ 1.0 sang 2.0. App không khai báo B trực tiếp. Graph có thể thay đổi không?

**Đáp án:** Có. POM metadata của A phiên bản mới sẽ đưa tập dependency bắc cầu khác vào graph và có thể tác động conflict mediation.

**Câu 7.** `-o` có đảm bảo một build hoàn toàn tái lập không?

**Đáp án:** Không. Nó chỉ dùng dữ liệu local đang có và có thể lỗi khi thiếu artifact. Hai máy có cache khác nhau có thể cho kết quả khác.

**Câu 8.** Một release build cần cùng artifact sau một tháng. Bạn nên ưu tiên range mở hay version cụ thể đã kiểm thử?

**Đáp án:** Ưu tiên version cụ thể đã kiểm thử, kết hợp managed transitive dependencies, repository release bất biến, pin plugin/JDK và kiểm tra graph theo chính sách.

**Câu 9.** Hai nhánh đưa hai hard requirements không có version giao nhau. Maven có nhất thiết chọn bản gần root hơn không?

**Đáp án:** Không. Hard constraints có thể khiến không có version hợp lệ; khi đó resolution thất bại thay vì tùy tiện chọn bản không thỏa ràng buộc.

**Câu 10.** Trong lab, thêm bản thư viện 1.2.0 bằng `mvn install` có làm version range của app tự đổi trong POM không?

**Đáp án:** Không. POM vẫn chứa `[1.1.0,1.3.0)`; chỉ **version được giải quyết trong lần build tiếp theo** có thể đổi khi metadata local cho biết bản 1.2.0.

## Tài liệu chính thức để tìm hiểu sâu

- [Apache Maven – POM Reference: Dependency Version Requirement Specification](https://maven.apache.org/pom.html): soft/hard requirements, range syntax, version order và qualifier.
- [Apache Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies, nearest definition, dependencyManagement/BOM, scope và exclusions.
- [Apache Maven – Settings Reference](https://maven.apache.org/settings.html): `repositories`, `mirrors`, `updatePolicy`, `checksumPolicy` và settings profile.
- [Apache Maven – Repository Metadata](https://maven.apache.org/repositories/metadata.html): các loại Maven metadata và mục đích quản lý phiên bản.
- [Apache Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): tham số lọc và các định dạng output.
- [Apache Maven Dependency Plugin – dependency:copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): sao chép JAR phụ thuộc đã giải quyết để quan sát runtime classpath trong lab.
- [Apache Maven – Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): parent, inheritance, aggregation, dependencyManagement.
- [Apache Maven – Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): Maven reactor và quan hệ giữa các module.
