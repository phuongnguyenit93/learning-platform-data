# Ghi đè phiên bản có chủ đích và kiểm tra Effective POM trong Maven

## 1. Bối cảnh: BOM quản lý phiên bản nhưng đôi khi cần ngoại lệ

Trong một hệ thống Maven có nhiều thư viện và module, **Bill of Materials (BOM)** giúp quản lý đồng bộ phiên bản của một nhóm artifact. Thay vì mỗi module ghi một phiên bản cho từng dependency, các module **import BOM** và khai báo những thư viện thực sự sử dụng trong `<dependencies>`.

Tuy nhiên, đôi khi bạn cần dùng **một phiên bản khác với phiên bản BOM quản lý**, chẳng hạn:
- vá một lỗi hoặc vấn đề bảo mật đã được xác minh;
- sử dụng một API được bổ sung ở phiên bản mới hơn;
- thử một bản phát hành tương thích trước khi tổ chức cập nhật toàn bộ BOM;
- tránh một phiên bản có lỗi hồi quy trong môi trường cụ thể.

Đây là **intentional version override — ghi đè phiên bản có chủ đích**. Nó phải được thể hiện rõ trong POM, có lý do và có kiểm chứng. Không nên “thử đổi version cho đến khi build xanh” hoặc lệ thuộc một cách tình cờ vào thứ tự dependency.

Ví dụ tình huống:

```text
team-bom:1.0.0
├── org.apache.commons:commons-text:1.11.0
└── org.apache.commons:commons-lang3:3.14.0

Ứng dụng import team-bom:1.0.0
├── commons-text:1.12.0       <- ngoại lệ được khai báo tường minh
└── commons-lang3:3.14.0      <- giữ phiên bản do BOM quản lý
```

Hai phiên bản Commons Text `1.11.0` và `1.12.0`, cùng Commons Lang `3.14.0`, là các phiên bản phát hành thực tế. Đây là **bài thực hành chọn phiên bản**, không có nghĩa mọi bộ phiên bản tùy ý kết hợp đều tương thích.

**Mục tiêu học tập:** biết viết ghi đè đúng chỗ, phân biệt cách ghi đè và phạm vi của chúng, xem **Effective POM** để xác nhận mô hình Maven đã hợp nhất, rồi dùng **dependency:tree** và test để kiểm chứng artifact thực sự được giải quyết.

## 2. Các khái niệm phải phân biệt trước khi ghi đè

### 2.1. dependencies — thư viện mà module sử dụng

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-text</artifactId>
    </dependency>
</dependencies>
```

Đây là **đoạn POM**. Dependency không ghi version có thể được Maven hoàn thiện từ `dependencyManagement` của project, parent hoặc BOM import. Nhưng nếu thiếu một nguồn quản lý phiên bản hợp lệ, build có thể lỗi vì Maven không biết version cần dùng.

### 2.2. dependencyManagement — nơi quản lý version

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-text</artifactId>
            <version>1.11.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

`dependencyManagement` cung cấp thông tin mặc định hoặc quản lý cho các dependency khớp. **Chỉ có khai báo ở đây không tự thêm thư viện vào classpath.** Muốn dùng Commons Text trong source của module, vẫn cần dependency trong `<dependencies>` hoặc được đưa vào graph bằng một dependency phù hợp.

`dependencyManagement` còn có thể điều chỉnh version của **transitive dependencies**, và theo tài liệu Maven, dependency management có ưu tiên hơn quy tắc chọn đường phụ thuộc gần nhất trong trường hợp quản lý transitive dependency.

### 2.3. BOM được import

BOM trong Maven 3 thường là một POM `<packaging>pom</packaging>` chứa `dependencyManagement`. Project tiêu thụ import nó bằng một dependency **bên trong `dependencyManagement`**, với:

```xml
<dependency>
    <groupId>com.example.training</groupId>
    <artifactId>team-bom</artifactId>
    <version>1.0.0</version>
    <type>pom</type>
    <scope>import</scope>
</dependency>
```

`<scope>import</scope>` ở đây không phải một runtime/test dependency scope thông thường. Nó yêu cầu Maven **thay thế mục import bằng danh sách dependency đã quản lý của BOM được chỉ định**.

*Không* thêm mục BOM này vào `<dependencies>` cấp project rồi kỳ vọng nó hoạt động như BOM import. Không dùng `scope=import` cho dependency type `jar`. Import BOM **khác kế thừa parent POM**: import tập trung vào danh sách dependency được quản lý, không mang toàn bộ cấu hình build/plugin của BOM vào project.

## 3. Quy tắc ưu tiên khi muốn ghi đè phiên bản

Không có một câu “BOM luôn thắng” áp dụng cho mọi tình huống. Cần phân biệt nguồn cấu hình và cách Maven hợp nhất.

| Trường hợp | Hành vi nên hiểu | Cách kiểm tra |
| --- | --- | --- |
| Project import BOM, không tự quản lý artifact | Version đến từ BOM được import | Effective POM: `dependencyManagement` |
| Project có mục **tường minh** cùng artifact trong `dependencyManagement` | Mục khai báo trực tiếp trong POM hiện tại ưu tiên hơn mục mang vào từ imported BOM | Effective POM, xem version cuối |
| POM con ghi đè một mục quản lý từ parent | Khai báo quản lý tại POM con được ưu tiên theo quy tắc kế thừa | Effective POM của POM con |
| Hai BOM được import cùng quản lý một artifact, project không tự ghi đè | BOM **được import trước** cung cấp version cho mục trùng | Kiểm tra import order và Effective POM |
| Dependency **trực tiếp** tự ghi `<version>` | Đã chỉ định version cụ thể cho dependency trực tiếp, thay vì nhận mặc định từ management | Xem `dependencies` trong Effective POM và dependency tree |
| Plugin dependency có version conflict | `dependencyManagement` của project **không quản lý graph dependency của plugin theo cùng cách** | Kiểm tra plugin configuration/graph riêng |

Trong ví dụ bài này, app sẽ import `team-bom` rồi thêm khai báo riêng cho `commons-text` trong cùng `dependencyManagement`. Chính mục khai báo riêng ấy làm ngoại lệ có chủ đích. Mục `commons-lang3` không bị ghi đè nên tiếp tục nhận version từ BOM.

**Chú ý về identity:** khi dependency có `type` hoặc `classifier` không mặc định, management phải khớp chính xác khóa liên quan; chỉ so `groupId:artifactId` rồi bỏ qua biến thể là chưa đủ để giải thích mọi kết quả.

## 4. Bài thực hành đầy đủ: BOM riêng + ứng dụng Java 17

Ta tạo hai project Maven **độc lập** trong một thư mục thực hành:

```text
bom-override-demo/
├── team-bom/
│   └── pom.xml
└── app/
    ├── pom.xml
    └── src/
        └── main/
            └── java/
                └── com/example/override/App.java
```

Hai thư mục là hai Maven project có POM riêng; **không khai báo một reactor parent `<modules>` trong ví dụ**. Điều này có chủ đích: Maven phải **resolve được BOM trước khi app import nó**. Vì vậy chúng ta sẽ cài BOM vào local repository trước khi build app.

Yêu cầu: JDK 17 trở lên, Maven 3 tương thích, và mạng truy cập Maven Central hoặc repository nội bộ có đủ plugin/dependency. Maven Wrapper có thể thay `mvn` nếu mỗi project đã chuẩn bị Wrapper; ví dụ dưới đây dùng lệnh `mvn` được cài đặt.

### 4.1. File team-bom/pom.xml — khai báo baseline versions

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.training</groupId>
    <artifactId>team-bom</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-text</artifactId>
                <version>1.11.0</version>
            </dependency>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.14.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

POM này hợp lệ và chỉ quản lý phiên bản hai thư viện. Nó **không tự biên dịch Java, không tự tải hai thư viện vào classpath để chạy chương trình**, và không cần có `src/main/java`. `<packaging>pom</packaging>` phù hợp vai trò BOM.

Trong dự án thực tế, BOM thường được publish lên repository của tổ chức. Ở bài này, chúng ta dùng `mvn install` để cài POM BOM vào local repository, tránh phải cấu hình server deploy.

### 4.2. Cài BOM trước khi build app

Tại thư mục `bom-override-demo`, chạy:

```bash
mvn -B -ntp -f team-bom/pom.xml install
```

Lệnh sẽ cài artifact POM `com.example.training:team-bom:1.0.0` vào local repository của máy chạy Maven, thường theo đường dẫn:

```text
~/.m2/repository/com/example/training/team-bom/1.0.0/
    team-bom-1.0.0.pom
```

Đường dẫn thực tế có thể khác nếu cấu hình `settings.xml` hoặc `-Dmaven.repo.local`. Việc có BOM trong local repository đảm bảo app có thể import nó **tại thời điểm xây dựng effective model**.

Nếu chưa `install` và BOM không có trong remote repository, app có thể báo `Non-resolvable import POM`. Đừng diễn giải lỗi đó là quy tắc override bị sai; đó là lỗi **không tìm thấy BOM**.

### 4.3. File app/pom.xml — import BOM và override một version

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.training</groupId>
    <artifactId>bom-override-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <!-- Import bộ version chuẩn của nhóm -->
            <dependency>
                <groupId>com.example.training</groupId>
                <artifactId>team-bom</artifactId>
                <version>1.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>

            <!-- Ngoại lệ có chủ đích: dùng Commons Text 1.12.0 -->
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-text</artifactId>
                <version>1.12.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-text</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Phân tích theo đúng cấu trúc:

1. `<dependencyManagement>` import `team-bom:1.0.0` qua `type=pom` và `scope=import`.
2. Cùng `<dependencyManagement>` có một **mục quản lý tường minh** cho `commons-text:1.12.0`. Đây là nơi ghi đè phiên bản của BOM.
3. `<dependencies>` khai báo `commons-text` và `commons-lang3` **không ghi version**; Maven sẽ lấy version đã được quản lý.
4. Vì chỉ `commons-text` được ghi đè, `commons-lang3` tiếp tục sử dụng `3.14.0` từ BOM.
5. POM không có dependency `team-bom` ở `<dependencies>`. BOM import không phải thư viện được nạp vào runtime.
6. `maven-compiler-plugin` chỉ là cấu hình plugin build, không được quản lý bởi team BOM theo ví dụ này.

Đặt khai báo quản lý ngoại lệ ngay sau import giúp người đọc thấy rõ “baseline + override”. Thứ tự dòng này **không phải lý do bản override thắng**: nó là một khai báo quản lý **trực tiếp của POM hiện tại**, không phải một entry có thứ tự ưu tiên bất kỳ từ nhiều BOM.

### 4.4. File app/src/main/java/com/example/override/App.java

```java
package com.example.override;

import org.apache.commons.lang3.StringUtils;
import org.apache.commons.text.StringEscapeUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("HTML: " + StringEscapeUtils.escapeHtml4("A & B"));
        System.out.println("Lang: " + StringUtils.upperCase("maven"));
    }
}
```

Đây là Java 17 hợp lệ. `StringEscapeUtils.escapeHtml4` có trong Commons Text của bài; `StringUtils.upperCase` có trong Commons Lang. Ứng dụng gọi trực tiếp hai thư viện, nên POM **khai báo trực tiếp hai dependency** thay vì dựa vào transitive dependency.

Khi đã build thành công và đưa đủ project dependencies lên classpath, **hai dòng do chương trình in** là:

```text
HTML: A &amp; B
Lang: MAVEN
```

Không coi output này là bằng chứng Maven đã chọn Commons Text phiên bản `1.12.0`, vì các phương thức trên tồn tại ở nhiều phiên bản. Việc xác minh **version được resolve** phải dùng dependency tree.

## 5. Xác minh Effective POM: phiên bản sau import và override

Maven Help Plugin có goal `help:effective-pom` để hiển thị **effective model** sau kế thừa, import BOM, nội suy và những active profile của lần build.

Từ thư mục `app`:

```bash
cd app
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Doutput=effective-pom.xml
```

Hoặc cách ngắn nếu Maven đã resolve được plugin prefix `help`:

```bash
mvn help:effective-pom -Doutput=effective-pom.xml
```

Tệp `effective-pom.xml` dài hơn source `pom.xml` nhiều lần vì còn chứa các giá trị mặc định và cấu hình được Maven tổng hợp. **Đừng copy cả file effective POM thay thế POM nguồn**: nó là kết quả chẩn đoán, không phải nơi cần sửa.

### 5.1. Kiểm tra đúng nhánh dependencyManagement

Trong effective POM, tìm `<dependencyManagement>` rồi xác định entry:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-text</artifactId>
    <version>1.12.0</version>
</dependency>
```

**Đây là trích đoạn các phần tử quan trọng**, không phải cam kết toàn bộ định dạng hoặc thứ tự thẻ của tệp tạo thật. Điểm cần kiểm là **`commons-text` được quản lý ở version `1.12.0`**, không còn `1.11.0` cho cùng entry trong effective dependency management của ứng dụng.

Trong cùng vùng dependency management, `commons-lang3` vẫn được quản lý ở `3.14.0`. Vì bản override chỉ nhắm Commons Text, đó là một phép kiểm soát phạm vi thay đổi.

### 5.2. Kiểm tra dependencies của chính ứng dụng

Tiếp tục tìm nhánh `<dependencies>` ở cấp `<project>`, **không nhầm** với `<dependencies>` nằm trong `<dependencyManagement>`. Với ví dụ này, entry dùng Commons Text dự kiến có version được hoàn thiện thành `1.12.0`, còn Commons Lang thành `3.14.0`.

Nếu chỉ tìm chuỗi `1.12.0` trong XML mà không xác định entry nằm ở **`dependencyManagement` hay `dependencies`**, rất dễ kết luận sai. Effective POM có thể có nhiều phiên bản cho **những artifact khác nhau**, thậm chí cùng tên artifact trong các ngữ cảnh quản lý và build plugin riêng.

### 5.3. Truy dấu nguồn bằng -Dverbose=true

Khi muốn biết **giá trị đến từ đâu**, dùng:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-verbose.xml
```

Tham số `verbose` (Maven Help Plugin 3.2.0 trở lên) yêu cầu bổ sung XML comments về **nguồn gốc phần tử**. Trong bài thực hành, tìm `commons-text` trong `dependencyManagement` rồi xem chú thích gần đó để xác định mục `1.12.0` đến từ POM ứng dụng thay vì entry `1.11.0` của BOM.

**Giới hạn cần nhớ:** origin comments là gợi ý truy dấu input; khi có merge/phân giải nhiều cấp, một comment không nhất thiết mô tả toàn bộ chuỗi thuật toán dẫn tới giá trị cuối. Kết luận phải dựa trên effective model kết hợp với POM nguồn.

### 5.4. Kiểm chứng baseline trước khi override

Để nhìn thấy khác biệt rõ ràng, thử trên bản sao của bài thực hành hoặc một lượt chỉnh POM có kiểm soát:

1. Trong `app/pom.xml`, **tạm thời bỏ duy nhất dependency quản lý Commons Text `1.12.0`**, giữ nguyên BOM import và direct dependencies không có version.
2. Chạy `help:effective-pom -Doutput=effective-baseline.xml`.
3. Tìm managed version `commons-text:1.11.0` trong effective POM.
4. **Khôi phục mục override `1.12.0`**, chạy lại `help:effective-pom -Doutput=effective-override.xml`.
5. So sánh đúng `commons-text`: trước `1.11.0`, sau `1.12.0`. `commons-lang3` vẫn `3.14.0`.

Không cần chỉnh `team-bom/pom.xml` để thay đổi riêng app; đó chính là lợi ích của override cục bộ có chủ đích. Đừng giữ hai mục quản lý trực tiếp duplicate cho Commons Text trong cùng POM.

## 6. Effective POM chưa đủ: xác minh version resolved bằng dependency:tree

Effective POM giúp kiểm tra **cấu hình mô hình**. Để xác minh Maven thực sự giải quyết dependency nào cho project, dùng Maven Dependency Plugin:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree
```

Có thể lọc hai artifact bài thực hành:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree -Dincludes=org.apache.commons:commons-text,org.apache.commons:commons-lang3
```

Trong cây của app, các tọa độ **được chọn** cần tương ứng:

```text
org.apache.commons:commons-text:jar:1.12.0:compile
org.apache.commons:commons-lang3:jar:3.14.0:compile
```

Hai dòng trên là **mốc đối chiếu**, không phải bản sao nguyên văn toàn bộ stdout. Tree thực tế còn thể hiện thụt dòng, dependency root, nhánh bắc cầu và các mục khác. `commons-lang3` có thể xuất hiện như dependency direct và/hoặc có nhánh transitive bị rút gọn.

Muốn xem vì sao một version bắc cầu bị bỏ qua:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree -Dverbose=true
```

`-Dverbose=true` của **Dependency Plugin** dùng để hiển thị thêm các node bị bỏ qua do conflict/duplicate trong định dạng được hỗ trợ. Nó **khác** `-Dverbose=true` của **Help Plugin**, vốn bổ sung origin comments trong effective POM. Cùng tên tham số nhưng hai plugin thực hiện hai mục đích khác nhau.

Để lưu báo cáo:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree -DoutputFile=dependency-tree.txt
```

Khi so sánh baseline và override, đổi tên output cho từng lượt, ví dụ `dependency-baseline.txt` và `dependency-override.txt`; tránh ghi đè bằng một tên duy nhất rồi tưởng đã có đủ hai phiên bản.

### Điều gì xảy ra nếu dependency management và tree có vẻ khác?

Hãy kiểm tra theo thứ tự:

- Đã chạy lệnh tại đúng module `app` hoặc chỉ đúng POM bằng `-f` chưa?
- Có direct dependency khai báo `<version>` tường minh không?
- Có profile/parent POM bổ sung management hoặc dependency không?
- Artifact bạn đọc có cùng `groupId:artifactId:type:classifier` không?
- Có `scope`, `optional` hoặc `exclusions` loại một đường bắc cầu không?
- Artifact version có thực sự tải/resolve được từ repository không?
- Lệnh Help Plugin và Dependency Plugin có chạy **cùng settings/profile/Maven version** không?

Đừng sửa file effective POM để làm dependency tree trông giống kỳ vọng. Chỉnh POM nguồn, sinh lại, rồi kiểm chứng.

## 7. Build và chạy Java 17 sau khi đã chốt version

Sau khi BOM được `install` và app đã có POM override, từ thư mục `app`:

```bash
mvn -B -ntp clean package
```

Lệnh đi qua các phase default lifecycle đến `package`, biên dịch Java và tạo `target/bom-override-app-1.0.0.jar` nếu build thành công. JAR thông thường này **không phải fat JAR**: dependencies Commons Text/Lang không tự được gói chung chỉ nhờ `packaging=jar`.

Để chạy chương trình mà không cần tự ghép classpath khác nhau giữa Linux và Windows, dùng Maven Exec Plugin `exec:java`, vốn xây dựng classpath từ project và dependencies:

```bash
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=com.example.override.App
```

Chương trình in:

```text
HTML: A &amp; B
Lang: MAVEN
```

Đây là **output của chương trình**. Log Maven/plugin có thể khác tùy CLI flag và môi trường. Nếu dùng `-q`, phần log thông thường được giảm bớt; không sử dụng log đó làm phép kiểm phiên bản.

Chú ý:
- `exec:java` chạy class trong cùng JVM của Maven, không phải một tiến trình Java tách biệt; với ứng dụng phức tạp có thread hoặc xử lý signal, cần nghiên cứu hướng chạy phù hợp.
- Nếu chỉ chạy `java -cp target/classes com.example.override.App` mà không thêm JAR dependency, có thể gặp `ClassNotFoundException` vì `target/classes` không chứa Commons Text/Lang.
- Nếu compile/test lỗi sau override, không nên chỉ ép build tiếp; kiểm tra compatibility API và transitive dependency tree rồi điều chỉnh có căn cứ.

## 8. Ba cách “ghi đè” và hậu quả khác nhau

### 8.1. Ghi đè trong dependencyManagement của project — cách phù hợp bài này

```xml
<dependencyManagement>
    <dependencies>
        <!-- BOM import nằm trong cùng danh sách -->
        <dependency>
            <groupId>com.example.training</groupId>
            <artifactId>team-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <!-- Quyết định phiên bản do project kiểm soát -->
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-text</artifactId>
            <version>1.12.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đoạn này **đã nằm trong POM hoàn chỉnh ở mục 4.3**, không phải phần thứ hai cần thêm trùng. Nó thể hiện chính sách ở một chỗ, giúp những dependency dùng `commons-text` nhận version phù hợp khi Maven áp dụng management.

Phù hợp khi:
- project cần tạm thay một version BOM;
- nhiều module kế thừa parent có cùng ngoại lệ;
- muốn kiểm soát cả những đường phụ thuộc bắc cầu liên quan.

### 8.2. Ghi version ngay ở dependency trực tiếp

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-text</artifactId>
        <version>1.12.0</version>
    </dependency>
</dependencies>
```

Ở đây project **nói rõ** dependency trực tiếp là `1.12.0`, không cần nhận version mặc định từ BOM. Điều này có thể đủ cho **một module** dùng trực tiếp Commons Text.

Tuy nhiên:
- Bạn có thể lặp version ngoại lệ ở nhiều module;
- Nó không phải chính sách quản lý version chung cho mọi transitive path của các module khác;
- Nếu muốn parent của tổ chức làm nguồn quản lý tập trung, đặt ngoại lệ ở đúng `dependencyManagement` thường phù hợp hơn.

**Không thêm hai dependency trực tiếp trùng tọa độ Commons Text với version khác nhau** rồi mong Maven an toàn phân xử. Duplicate dependency declaration là cấu hình khó bảo trì và có thể bị Maven cảnh báo/lỗi.

### 8.3. Thay version trong parent POM hoặc BOM nguồn

Nếu cả tổ chức đã thống nhất cập nhật, có thể sửa **BOM nguồn** `1.11.0 → 1.12.0` rồi phát hành **một phiên bản BOM mới**, chẳng hạn `team-bom:1.1.0`. Sau đó các project import version BOM mới.

Lợi ích: mọi consumer có thể nhận bộ version chuẩn mới, không cần duy trì ngoại lệ lâu dài. Đổi lại, đây là **tác động phạm vi rộng**, đòi kiểm thử tính tương thích, cập nhật release note và CI của các module bị ảnh hưởng.

**Không tái xuất bản cùng một tọa độ BOM release với nội dung thay đổi** nếu repository và quy trình release yêu cầu immutability; hãy phát hành version mới để build có thể tái lập.

## 9. Ghi đè bằng property: đúng ngữ cảnh parent, không nhầm import BOM

Một số parent POM dùng properties để biểu diễn version:

```xml
<properties>
    <commons.text.version>1.11.0</commons.text.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-text</artifactId>
            <version>${commons.text.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn POM minh họa**. Nếu child **kế thừa parent POM** phù hợp, nó có thể ghi đè property trong child và thay đổi version sau nội suy theo cơ chế inheritance/interpolation.

Tuy nhiên, **đừng suy ra cùng cách luôn có tác dụng với một BOM được import**. Một BOM import là mô hình POM riêng; các properties nội bộ dùng để tính version trong BOM thường được nội suy **trong ngữ cảnh BOM**, rồi các managed entries được import. Chỉ tạo `<commons.text.version>1.12.0</commons.text.version>` trong app **không bảo đảm đổi** version Commons Text của BOM import.

Ví dụ trong bài này, team BOM đã khai báo version trực tiếp `1.11.0`, không dùng property tên `commons.text.version`. Vì thế cách chắc chắn, dễ kiểm chứng là **khai báo riêng một managed dependency ở app** như mục 4.3, thay vì cố thay property không được BOM công bố cho mục đích override.

**Nguyên tắc:** Nếu dùng một framework/parent cụ thể có cơ chế ghi đè property được tài liệu chính thức hỗ trợ, hãy làm theo tài liệu của framework đó. Với Maven BOM import tổng quát, chủ động ghi đè dependency management và kiểm tra effective POM là cách ít gây hiểu nhầm.

## 10. Trường hợp hai BOM cùng quản lý một dependency

Giả sử app import hai BOM:

```text
platform-a-bom
└── commons-text:1.11.0

platform-b-bom
└── commons-text:1.12.0

app
├── import platform-a-bom
└── import platform-b-bom
```

Nếu app **không** tự quản lý `commons-text`, Maven áp dụng quy tắc import: **entry từ BOM được khai báo/import trước** được chọn cho mục trùng (giả định cả hai BOM đã resolve hợp lệ và không có thay đổi do management từ nguồn khác).

Đó là quy tắc **thứ tự BOM import**, không phải nearest-wins của dependency tree. Hai điều này thuộc hai giai đoạn khác nhau của mô hình dependency.

Nếu app thêm:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-text</artifactId>
    <version>1.12.0</version>
</dependency>
```

**ngay trong `<dependencyManagement><dependencies>` của app**, thì entry tường minh sẽ có ưu tiên thay cho giá trị từ BOM import, như ví dụ chính của bài. Nếu cần phiên bản cụ thể, **đừng chỉ đảo vị trí hai BOM** cho đến khi tình cờ nhận version mong muốn; thể hiện override có chủ đích giúp reviewer thấy chính sách rõ ràng.

### Nhận diện entry quản lý

Đối với dependency management, Maven phân biệt các entry qua các yếu tố như `groupId`, `artifactId`, `type` và `classifier`. Ví dụ `jar` thường và `test-jar` có classifier `tests` là biến thể khác; một entry quản lý JAR chính không nhất thiết điều chỉnh đúng một test JAR có classifier.

Khi một override dường như “không thắng”, kiểm tra đúng key thay vì chỉ so tên thư viện giống nhau.

## 11. Ghi đè từ POM con với parent POM

Ví dụ hệ thống doanh nghiệp:

```text
company-parent/pom.xml
└── dependencyManagement
    └── commons-text:1.11.0

service-a/pom.xml
├── parent: company-parent
├── dependencyManagement
│   └── commons-text:1.12.0
└── dependencies
    └── commons-text (không ghi version)
```

Đây là sơ đồ minh họa, **không phải nội dung repo hiện có**. Với parent-child inheritance, Maven cho phép POM con ghi đè một managed dependency từ parent bằng khai báo tường minh cho cùng artifact. Do đó `service-a` nhận version `1.12.0`; các module anh em không tự bị thay đổi nếu chúng vẫn kế thừa quản lý `1.11.0`.

Cách kiểm tra:
1. Chạy `mvn -f service-a/pom.xml help:effective-pom` với đúng cấu hình profile.
2. Đọc `dependencyManagement` cuối cùng của `service-a`.
3. Chạy `mvn -f service-a/pom.xml dependency:tree` để xem phiên bản resolved thực tế.
4. Xác nhận những module khác không bị ảnh hưởng không mong muốn.
5. Sau khi toàn hệ thống đã sẵn sàng, đưa cập nhật vào parent/BOM chung và xóa override cục bộ thừa.

**Không nhầm** parent-child inheritance với BOM import: parent POM có thể mang `pluginManagement`, `build`, properties và nhiều loại cấu hình khác, còn import BOM chỉ nhắm các managed dependency.

## 12. Profile và tham số CLI có thể thay đổi kết quả

Có thể có những profile khác nhau:

```xml
<profiles>
    <profile>
        <id>next</id>
        <dependencyManagement>
            <dependencies>
                <dependency>
                    <groupId>org.apache.commons</groupId>
                    <artifactId>commons-text</artifactId>
                    <version>1.12.0</version>
                </dependency>
            </dependencies>
        </dependencyManagement>
    </profile>
</profiles>
```

Đây là **một đoạn để chèn vào `<project>`** của một POM phù hợp, không phải POM riêng. Với POM hiện tại đã có override `1.12.0` trong dependency management, thêm profile `next` cùng version **không thay đổi kết quả**. Nếu bạn muốn dùng profile để bật/tắt một ngoại lệ, cần thiết kế POM sao cho baseline không đồng thời có một override cố định ngoài profile.

Kiểm tra hai ngữ cảnh:

```bash
mvn help:active-profiles
mvn -Pnext help:active-profiles

mvn help:effective-pom -Doutput=effective-default.xml
mvn -Pnext help:effective-pom -Doutput=effective-next.xml
```

Các lệnh phải chạy từ đúng module/POM mà bạn muốn phân tích. Khi dùng `-Pnext`, Maven tính lại effective model cho **lượt chạy này**. Không suy rằng `-P` được lưu giữa các lệnh.

Các user properties `-D...` cũng có thể ảnh hưởng giá trị được nội suy trong POM, nhưng **không phải mọi BOM version đều được thiết kế để override qua property**. Hãy kiểm tra effective POM thay vì chỉ dựa vào tên biến được truyền.

## 13. Rủi ro và nguyên tắc an toàn khi thay version

### 13.1. BOM có thể là bộ version đã được kiểm thử đồng thời

BOM thường đại diện cho tập thư viện được chọn để hoạt động cùng nhau. Nâng một dependency riêng lẻ có thể:
- thay đổi API hoặc hành vi runtime;
- kéo thêm/bớt dependency bắc cầu;
- tạo xung đột phiên bản trong đồ thị;
- làm test chạy khác với baseline;
- bỏ qua giả định tương thích của framework hoặc stack đang dùng.

**Ghi đè thành công không phải bằng chứng tương thích.** Effective POM đúng chỉ chứng minh Maven đã tạo mô hình như mong đợi; dependency tree đúng chỉ chứng minh version được resolve. Phải chạy test phù hợp, tối thiểu unit test và integration test trong ngữ cảnh ứng dụng.

### 13.2. Nên ghi nhận lý do ghi đè

Trong code review hoặc issue tracking, nên có các thông tin:
- Artifact bị override: đầy đủ `groupId:artifactId:type:classifier` khi cần;
- Version baseline từ BOM và version chọn thay;
- Lý do: API bug, compatibility fix, CVE đã xác minh hoặc dependency policy;
- Phạm vi: một module hay toàn bộ parent project;
- Cách kiểm chứng: effective POM, dependency tree, test/report;
- Điều kiện gỡ override: phiên bản BOM chung nào sẽ thay thế.

Một chú thích ngắn trong POM có thể hữu ích, nhưng đừng ghi URL nội bộ có secret, dữ liệu xác thực hay thông tin nhạy cảm vào comment.

### 13.3. Không dùng management sai phạm vi

`<dependencyManagement>` của project dùng để quản lý **project dependencies**. Nó không có nghĩa tự động điều chỉnh mọi dependency transitively của Maven plugins, build extensions hay Maven runtime. Nếu xung đột xuất hiện trong plugin classloader, cần điều chỉnh **plugin configuration/versions/dependencies** đúng nơi và kiểm tra tài liệu plugin.

Đừng đưa `exec-maven-plugin` hoặc `maven-compiler-plugin` vào `<dependencies>` như một thư viện runtime chỉ để chốt plugin version. Các plugin thuộc `<build><plugins>` hoặc `<pluginManagement>`.

## 14. Lỗi thường gặp khi override BOM

| Hiện tượng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| `Non-resolvable import POM` | Chưa install/deploy BOM; sai tọa độ, repository hoặc quyền mạng | Install BOM đúng version hoặc cấu hình repository hợp lệ |
| `dependencies.dependency.version is missing` | Import BOM không khớp artifact hoặc POM chưa có management | Kiểm tra groupId/artifactId/type/classifier và effective POM |
| Commons Text vẫn ở `1.11.0` | Đã thêm property nhưng BOM import không lấy property đó, hoặc sửa sai POM | Khai báo managed override tường minh rồi đọc effective POM |
| Cấu hình có version `1.12.0` nhưng tree khác | Có direct version, management/profile/parent khác hoặc artifact key khác | So `dependencies`, `dependencyManagement` và dependency tree |
| Không thấy Commons Text trong dependency tree | Chỉ khai báo management, chưa dùng dependency thực tế | Thêm dependency hoặc xác định đường transitive |
| Tree có version đúng nhưng ứng dụng lỗi runtime | Binary/API compatibility hoặc transitive dependency khác | Kiểm tra test, stack trace và runtime classpath |
| Đổi thứ tự hai BOM làm version đổi | Hai BOM trùng managed entry và first import wins | Đặt override rõ ràng, xác minh trước/sau |
| User nghĩ BOM import giống parent | Import không mang toàn bộ build/plugin config của BOM | Phân biệt BOM import và `<parent>` |
| File effective POM không thấy comment nguồn | Chưa bật `-Dverbose=true` hoặc Help Plugin quá cũ | Dùng phiên bản Help Plugin hỗ trợ verbose |
| `mvn dependency:tree` thành công nhưng build vẫn thất bại | Resolve graph đúng không đảm bảo source/test tương thích | Chạy compile/test/verify và xem lỗi thực tế |
| CI và máy local chọn version khác nhau | POM/profile/settings/BOM cache/Maven version khác | Đối chiếu command, repository, effective POM và dependency tree |
| Java báo thiếu Commons Text class | Chạy bằng `java -cp target/classes` không có dependencies | Dùng `exec:java` hoặc xây classpath đầy đủ |
| Override nhầm test JAR bằng quản lý JAR chính | Khác `type/classifier` | Khai báo đúng variant và đọc effective model |

### Quy trình gỡ lỗi theo thứ tự

1. Chạy `mvn -version` để biết Maven và JDK thực tế.
2. Xác định **POM đang được Maven build** và BOM có resolve được không.
3. Chạy `help:effective-pom -Dverbose=true`, kiểm tra **managed version** và nguồn gốc của nó.
4. Chạy `dependency:tree`, kiểm tra artifact/version thực sự được đưa vào graph.
5. So sánh phiên bản baseline/override và các transitive dependencies có thể khác.
6. Chạy `clean verify`, kiểm tra test và mã thoát thay vì chỉ nhìn “tạo được POM”.
7. Khi đã xác minh, mô tả ngoại lệ trong code review và lên kế hoạch đưa về BOM chung.

## 15. Bài tập thực hành nâng cao

### Bài 1: Baseline và override

- Cài `team-bom:1.0.0` theo mục 4.2.
- Xóa tạm **một** managed entry Commons Text `1.12.0` trong app.
- Sinh `effective-baseline.xml` và `dependency-baseline.txt`.
- Khôi phục entry `1.12.0`.
- Sinh `effective-override.xml` và `dependency-override.txt`.
- Chỉ rõ những vị trí thể hiện `1.11.0 → 1.12.0` và xác nhận Commons Lang vẫn `3.14.0`.

### Bài 2: Đổi version trực tiếp thay vì quản lý

- Tạm bỏ managed override của Commons Text.
- Ghi `<version>1.12.0</version>` trong **dependency trực tiếp** của app.
- Kiểm tra effective POM và dependency tree có cùng version được chọn không.
- So sánh độ dễ quản trị khi 10 module cùng phải làm ngoại lệ này.

### Bài 3: BOM mới thay cho ngoại lệ

- Tạo bản phát hành BOM mới (ví dụ `1.1.0`) với Commons Text `1.12.0`; không sửa bản release `1.0.0` đã dùng.
- Chọn BOM mới trong app và gỡ managed override cục bộ.
- Xem effective POM và dependency tree của app có giữ version mong muốn không.
- Từ đó giải thích vì sao override thường là **giải pháp có thời hạn**, còn việc cập nhật BOM chung là hướng chuẩn hóa sau khi được kiểm thử.

### Bài 4: Giải thích một xung đột có nhiều BOM

- Giả sử BOM A quản lý dependency X là `1.0`, BOM B quản lý X là `2.0`.
- Nếu không có managed entry riêng trong app, BOM nào thắng khi A import trước?
- Nếu app tự quản lý X version `2.0`, kết quả nào được chờ đợi?
- Thứ tự import BOM và quy tắc nearest dependency path có phải cùng một quy tắc không?

**Tiêu chí hoàn thành:** Người học có thể chỉ ra **version chuẩn từ BOM**, **khai báo override tường minh**, **giá trị sau hợp nhất trong Effective POM**, **version được resolve trong dependency tree**, và **bằng chứng test** trước khi chấp nhận thay đổi.

## 16. Tóm tắt

- BOM giúp quản lý tập version; import đúng bằng `<type>pom</type>` và `<scope>import</scope>` trong `<dependencyManagement>`.
- Khi cần ngoại lệ, khai báo **một managed dependency tường minh** cho artifact tại POM áp dụng, thay vì sửa trực tiếp file effective POM hoặc dựa vào thứ tự BOM một cách ngẫu nhiên.
- **POM hiện tại có thể ưu tiên hơn managed entries từ imported BOM**; khi hai BOM trùng nhau mà không có override, BOM import trước thường thắng.
- Viết version trong dependency trực tiếp là cách khác, nhưng không thay thế chính sách management tập trung cho nhiều module.
- Không giả định một property của app luôn ghi đè property nội bộ của BOM import.
- **Effective POM** xác nhận cấu hình Maven đã hợp nhất; **dependency:tree** xác nhận dependency resolved; **build/test** mới kiểm chứng chức năng thực tế.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Dependency Mechanism (management, BOM và import precedence)](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference, dependencyManagement](https://maven.apache.org/pom.html)
- [Maven Help Plugin — help:effective-pom và verbose](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Commons Text — Release History](https://commons.apache.org/proper/commons-text/changes.html)
- [Exec Maven Plugin — exec:java usage](https://www.mojohaus.org/exec-maven-plugin/usage.html)
