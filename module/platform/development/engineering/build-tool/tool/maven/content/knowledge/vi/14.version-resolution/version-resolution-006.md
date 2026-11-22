# Thay đổi phiên bản dependency trong Maven: khai báo trực tiếp và quản lý tập trung

## 1. Vì sao thay một phiên bản có thể ảnh hưởng cả hệ thống?

Giả sử nhóm phát triển có nhiều module Maven cùng sử dụng `org.apache.commons:commons-lang3`. Một module khai `3.14.0`, module khác dùng `3.17.0`, còn một thư viện bắc cầu yêu cầu một bản cũ hơn. Sau một lần nâng cấp, người học thấy:

- Chạy `mvn clean verify` ở module riêng thì thành công, nhưng chạy cả reactor lại có vấn đề ở module khác.
- File POM chứa một phiên bản, còn `mvn dependency:tree` lại hiển thị phiên bản được chọn khác trong một nhánh dependency.
- Một thành viên chỉ sửa `pom.xml` ở module ứng dụng, còn những module dùng thư viện chung chưa được kiểm tra.
- Maven đã cập nhật `dependencyManagement` nhưng thư viện không xuất hiện ở nơi cần dùng, vì module chưa khai báo dependency thực tế.
- Build thành công song runtime báo `NoSuchMethodError` hoặc `ClassNotFoundException` do API và JAR được nạp không tương thích.

Chủ đề này tập trung vào **phân giải phiên bản dependency**: khi cần đổi version, bạn nên chỉnh **khai báo trực tiếp**, **property dùng chung**, **dependencyManagement của POM cha**, hay **BOM được import**? Và sau khi sửa, làm cách nào chứng minh Maven thực sự chọn phiên bản bạn muốn?

Mục tiêu sau khi học:

1. Hiểu thế nào là dependency trực tiếp, dependency bắc cầu và **dependency mediation**.
2. Biết đặt `<version>` trực tiếp khi chỉ một dependency cần kiểm soát cục bộ.
3. Biết gom version vào `<properties>` hoặc `<dependencyManagement>` để nhiều module dùng một quy tắc.
4. Phân biệt `dependencyManagement` với `dependencies`, và `pluginManagement` với quản lý thư viện ứng dụng.
5. Hiểu cách import BOM bằng `<type>pom</type>` và `<scope>import</scope>`.
6. Thử nâng phiên bản Commons Lang trong dự án Java 17/JUnit 5 chạy được; kiểm chứng bằng `dependency:tree`, `help:effective-pom` và test.
7. Lập quy trình thay phiên bản an toàn, kiểm soát tương thích API, dependency bắc cầu, mã chạy và artifact phát hành.

Bài dùng Maven **3.9.x**, JDK **17 trở lên**, các dependency và plugin có phiên bản tường minh. Các số version trong ví dụ là giá trị **minh họa để học cơ chế**; khi áp dụng production, hãy kiểm tra compatibility, chính sách bảo mật và phiên bản được tổ chức phê duyệt.

## 2. Maven giải quyết dependency theo những thông tin nào?

### 2.1. Tọa độ và scope

Một dependency được nhận diện chủ yếu bởi `groupId`, `artifactId`, `type` và `classifier`; version được xác định từ khai báo trực tiếp, phần quản lý dependency và kết quả giải quyết graph. Trong tình huống phổ biến với JAR không classifier, bạn thường viết:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
    <scope>compile</scope>
</dependency>
~~~

Ở đây:

- `groupId:artifactId` là `org.apache.commons:commons-lang3`.
- `version=3.14.0` là phiên bản được yêu cầu trên dependency trực tiếp.
- `scope=compile` áp dụng cho việc biên dịch, chạy ứng dụng và test. Nếu bỏ `<scope>`, Maven dùng **compile** mặc định.
- Không cần thêm `<type>jar</type>` cho dependency JAR thông thường.
- Một dependency có `type` hoặc `classifier` khác có thể là một phần tử quản lý riêng, nên khi quản lý tập trung phải kiểm tra đúng bộ nhận diện của dependency.

Một phiên bản hiển thị trong POM **không tự chứng minh** tất cả module đã sử dụng version đó. Mỗi Maven project có model và dependency graph riêng; cần kiểm tra resolved tree ở project đang quan tâm.

### 2.2. Direct dependency và transitive dependency

Ví dụ ứng dụng `A` phụ thuộc `B`; `B` lại khai dependency đến `C`:

~~~text
A
└── B:1.0
    └── C:1.2
~~~

`B` là dependency trực tiếp của `A`; `C` là dependency **bắc cầu (transitive)**. Maven có thể đưa `C` vào graph và classpath phù hợp scope. Nếu `A` có nhiều nhánh cùng kéo về `C` nhưng với các version khác nhau, Maven cần quyết định **version nào được chọn**.

Đây là lý do nâng version ở một chỗ đôi khi thay đổi JAR thực tế mà bạn không trực tiếp viết `<version>` cho JAR đó.

### 2.3. Dependency mediation: nearest definition

Ví dụ:

~~~text
A
├── B
│   └── C
│       └── D:2.0
└── E
    └── D:1.0
~~~

Đường từ `A` qua `E` đến `D:1.0` **ngắn hơn** đường qua `B`, `C` đến `D:2.0`. Theo quy tắc **nearest definition** của Maven 3, `D:1.0` thường thắng trong graph của `A`, trừ khi `A` có khai báo trực tiếp/quản lý dependency làm thay đổi quyết định.

Nếu hai đường có **cùng độ sâu**, Maven ưu tiên khai báo gặp **trước** theo quy tắc mediation. Vì thế thay thứ tự dependency trực tiếp trong POM đôi khi làm thay version bắc cầu; đây là tình huống cần quản lý rõ thay vì dựa vào vị trí XML tình cờ.

~~~text
A
├── B:1.0
│   └── D:2.0
└── E:1.0
    └── D:1.0
~~~

Nếu hai `D` ở cùng độ sâu và không có cấu hình quản lý/khai báo nào can thiệp, nhánh được khai trước có thể ảnh hưởng phiên bản D được chọn. **Không khuyến nghị sửa dependency bằng cách đảo thứ tự XML** để ép version một cách khó hiểu.

### 2.4. Khai báo trực tiếp có thể loại bỏ sự mơ hồ

Ở project `A`, bạn có thể khai thêm `D` **trực tiếp** nếu mã của `A` sử dụng `D` và muốn chủ động chọn version:

~~~xml
<dependencies>
    <dependency>
        <groupId>example</groupId>
        <artifactId>d</artifactId>
        <version>2.0</version>
    </dependency>
</dependencies>
~~~

Đây là **đoạn mô tả cú pháp**, không phải artifact `example:d` thật được yêu cầu tải trong bài. Nó làm đường `A → D` thành đường trực tiếp và cho Maven một yêu cầu version gần nhất. Phương án này hợp lý khi `A` **trực tiếp sử dụng API của D**. Nếu chỉ muốn thống nhất version của D trên nhiều nhánh transitive mà không thêm dependency trực tiếp không cần thiết, `dependencyManagement` thường phù hợp hơn.

## 3. Cách 1: đổi version ngay tại dependency trực tiếp

### 3.1. Cú pháp

Nếu một project chỉ cần Commons Lang, bạn có thể viết:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
~~~

Khi được phê duyệt nâng cấp, đổi duy nhất phần tử:

~~~xml
<version>3.17.0</version>
~~~

**Không được đặt thêm một dependency có cùng tọa độ với version mới bên cạnh dependency cũ để “ghi đè”.** Khai báo trùng tọa độ trong cùng `<dependencies>` có thể khiến Maven cảnh báo model không hợp lệ và làm build khó dự đoán. Hãy **sửa chính khai báo đang tồn tại**.

### 3.2. Ưu điểm và nhược điểm

| Khía cạnh | Version trực tiếp |
| --- | --- |
| Dễ đọc | Nhìn ngay dependency biết version dự định |
| Phạm vi thay đổi | Hẹp ở project/POM khai báo |
| Project nhỏ | Thường đủ và đơn giản |
| Nhiều module | Dễ xuất hiện nhiều số version bị copy/paste |
| Bảo trì | Muốn nâng đồng bộ phải kiểm tra nhiều POM nếu không có quản lý chung |
| Kiểm chứng | Vẫn cần `dependency:tree` để xem version thực tế và dependency bắc cầu |

Trong một dịch vụ độc lập, chỉ một POM và ít dependency, khai báo trực tiếp có thể là lựa chọn hợp lý. Chuyển sang parent/BOM quá sớm không tự làm dự án tốt hơn nếu nó khiến cấu hình khó đọc.

## 4. Ví dụ Java 17/JUnit 5 chạy được với khai báo version trực tiếp

Ví dụ đầu tiên dùng một POM đơn, không cần parent/BOM. Sau khi chạy được, ta sẽ triển khai cùng mã nguồn theo cách quản lý tập trung.

### 4.1. Cây thư mục

~~~text
version-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/version/App.java
    └── test/java/vn/example/version/AppTest.java
~~~

Tất cả lệnh Maven dưới đây chạy từ thư mục `version-demo` có file `pom.xml`, trừ khi ghi rõ vị trí khác.

### 4.2. POM hoàn chỉnh: `version-demo/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>version-demo</artifactId>
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
            <version>3.14.0</version>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
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
                <configuration>
                    <includeScope>runtime</includeScope>
                    <outputDirectory>${project.build.directory}/runtime-libs</outputDirectory>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Lưu ý:

- `maven.compiler.release=17` chỉ định mức Java cho compiler; máy chạy Maven vẫn cần JDK phù hợp.
- Commons Lang là dependency **compile** mặc định vì `App.java` trực tiếp import `StringUtils`.
- JUnit Jupiter là `test`; test cần nhưng runtime ứng dụng không cần.
- Maven Dependency Plugin được ghim version để thử goal `dependency:tree` và `dependency:copy-dependencies`. Không tự chạy goal copy chỉ vì khai báo plugin: ta sẽ gọi nó rõ ràng.
- `includeScope=runtime` ở goal `copy-dependencies` chọn dependency phù hợp runtime classpath, trong đó có **compile + runtime**, không kéo JUnit `test` vào thư mục lib.
- JAR Plugin mặc định tạo JAR của project **không nhúng mọi dependency**. Để chạy ứng dụng phải cung cấp Commons Lang trên runtime classpath.

### 4.3. Mã Java chính

File `src/main/java/vn/example/version/App.java`:

~~~java
package vn.example.version;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String message() {
        String title = StringUtils.capitalize("maven");
        String action = StringUtils.upperCase("build", Locale.ROOT);
        return title + " " + action;
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

`StringUtils.capitalize` và `StringUtils.upperCase(String, Locale)` tồn tại trong cả hai phiên bản Commons Lang được sử dụng ở bài. `Locale.ROOT` làm việc đổi chữ hoa ổn định, không phụ thuộc locale mặc định của máy. Vì vậy cùng một chương trình có thể kiểm tra cả version cũ và mới mà không thay source.

Stdout mong đợi khi runtime classpath đã đủ:

~~~text
Maven BUILD
~~~

### 4.4. Test JUnit

File `src/test/java/vn/example/version/AppTest.java`:

~~~java
package vn.example.version;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void formatsMessage() {
        assertEquals("Maven BUILD", App.message());
    }
}
~~~

Một test đơn giản nhưng có giá trị: nó biên dịch và chạy đúng đoạn mã sử dụng Commons Lang ở môi trường của Surefire. Tuy nhiên **test PASS không có nghĩa mọi ứng dụng lớn tương thích hoàn toàn** với bản library mới.

### 4.5. Build và chạy

Kiểm tra môi trường:

~~~bash
java -version
mvn -version
~~~

Chạy từ thư mục `version-demo`:

~~~bash
mvn clean verify
mvn dependency:tree
mvn dependency:copy-dependencies
~~~

Khi Maven đã tải artifact cần thiết từ repository, `clean verify` biên dịch Java 17, chạy một test và đóng gói JAR. Kiểm tra:

~~~text
target/
├── classes/vn/example/version/App.class
├── test-classes/vn/example/version/AppTest.class
├── surefire-reports/
├── version-demo-1.0.0.jar
└── runtime-libs/commons-lang3-3.14.0.jar
~~~

`target/runtime-libs` xuất hiện **sau goal copy-dependencies**, không phải tự động sau `verify`. Thư mục `target` cũng có thể chứa nhiều file Maven metadata khác; bảng chỉ liệt kê file cần quan sát.

Trên Linux/macOS:

~~~bash
java -cp "target/version-demo-1.0.0.jar:target/runtime-libs/*" vn.example.version.App
~~~

Trên Windows PowerShell/CMD:

~~~bat
java -cp "target\version-demo-1.0.0.jar;target\runtime-libs\*" vn.example.version.App
~~~

Stdout chính xác:

~~~text
Maven BUILD
~~~

`:` là dấu phân tách classpath trên Linux/macOS; `;` trên Windows. Java launcher hiểu wildcard `*` để lấy các JAR trong một thư mục. Nếu chỉ chạy `java -cp target/version-demo-1.0.0.jar ...` mà không cấp Commons Lang, ứng dụng có thể lỗi `NoClassDefFoundError: org/apache/commons/lang3/StringUtils` khi gọi method. Đó là lỗi **runtime classpath**, không chứng minh Maven chọn version sai.

### 4.6. Đọc version thực tế

~~~bash
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Khi không có override/conflict khác trong ví dụ, bạn tìm thấy node tương đương:

~~~text
org.apache.commons:commons-lang3:jar:3.14.0:compile
~~~

Từ khóa `compile` là Maven scope; số `3.14.0` là version resolved. Tên plugin, prefix và cách thụt cây trong log có thể khác.

Nếu muốn lưu dependency tree cho review, có thể chạy goal với `-DoutputFile=dependency-tree.txt`; file này là báo cáo phát sinh, không phải nguồn cấu hình version. Trong một repository thật, chỉ commit báo cáo khi nhóm có quy định rõ.

## 5. Thí nghiệm: nâng version trực tiếp từ 3.14.0 lên 3.17.0

Giữ nguyên `App.java` và `AppTest.java`. Trong `version-demo/pom.xml`, thay:

~~~xml
<version>3.14.0</version>
~~~

của **đúng dependency `commons-lang3`** thành:

~~~xml
<version>3.17.0</version>
~~~

Đừng thay `<version>1.0.0</version>` của project: đó là phiên bản artifact **của ứng dụng**, không phải phiên bản Commons Lang. Đừng thay phiên bản Compiler Plugin hoặc JUnit ngoài phạm vi thử nghiệm.

Sau đó chạy:

~~~bash
mvn clean verify
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
mvn dependency:copy-dependencies
~~~

Phiên bản resolved trong tree dự kiến là:

~~~text
org.apache.commons:commons-lang3:jar:3.17.0:compile
~~~

Thư mục `target/runtime-libs` sau bước copy mới chứa:

~~~text
commons-lang3-3.17.0.jar
~~~

Vì ví dụ chạy sau `mvn clean verify`, thư mục output cũ được dọn trước khi copy. Nếu không clean, goal copy có thể để lại file JAR version trước trong `runtime-libs`, khiến wildcard classpath nạp **nhiều bản thư viện cùng lúc**. Đó là rủi ro thực tế khi thử version mới; hãy bắt đầu từ một trạng thái sạch.

Chạy lại chương trình như mục 4.5; stdout vẫn là:

~~~text
Maven BUILD
~~~

Test vẫn phải PASS. Điều này cho thấy chương trình mẫu dùng API tồn tại trong hai version, **không** chứng minh tất cả API/dependency transitive của phiên bản mới đã tương thích với mọi ứng dụng.

**Lưu ý rất quan trọng về artifact:** `version-demo-1.0.0.jar` trong ví dụ là JAR thông thường. Nó **không nhúng Commons Lang JAR**. Nâng dependency có thể thay đổi **runtime distribution** (`runtime-libs` và resolved classpath) ngay cả khi JAR ứng dụng riêng lẻ không nhất thiết đổi byte. Nếu dùng fat JAR/Shade hoặc một plugin tạo metadata về dependency, nội dung gói phát hành có thể đổi. Đừng dựa một mình vào checksum của app JAR để kết luận toàn bộ bản phân phối không thay đổi.

## 6. Cách 2: dùng property quản lý version tại một nơi

Thay vì viết số `3.14.0` trực tiếp nhiều lần, có thể đưa nó vào property trong `pom.xml`:

~~~xml
<properties>
    <commons.lang3.version>3.14.0</commons.lang3.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>${commons.lang3.version}</version>
    </dependency>
</dependencies>
~~~

Đây là **trích đoạn POM**; đặt `properties` và `dependencies` trực tiếp dưới `project`, không copy thêm một `<project>` thứ hai. Khi muốn nâng từ `3.14.0` sang `3.17.0`, sửa một dòng property. Maven nội suy `${commons.lang3.version}` trong cấu hình dependency.

### 6.1. Property giải quyết vấn đề gì?

Nó giảm việc copy một số version trong nhiều vị trí **cùng POM hoặc chuỗi POM có kế thừa property**. Tuy nhiên, property **không tự thêm dependency** vào module và **không đảm bảo** mọi dependency có cùng `groupId:artifactId` đều dùng version đó nếu còn khai báo/management khác.

### 6.2. Dùng property ở parent có đủ chưa?

Nếu parent chỉ có:

~~~xml
<properties>
    <commons.lang3.version>3.14.0</commons.lang3.version>
</properties>
~~~

thì module con **không tự có Commons Lang trên classpath**. Module phải khai báo một dependency dùng property đó, ví dụ `<version>${commons.lang3.version}</version>`. Với vài module, lặp một dòng placeholder có thể chấp nhận được; với nhiều module, `dependencyManagement` thường giúp child bỏ cả `<version>`.

### 6.3. CLI user property có thể override version

Nếu POM quản lý version qua property, có thể thử:

~~~bash
mvn -Dcommons.lang3.version=3.17.0 clean verify
~~~

User property `-D` thường có thể thay giá trị được nội suy trong lần build. Đây là cách tiện để kiểm thử version mới **tạm thời**, nhưng cũng là nguồn biến động nếu CI hoặc IDE truyền cờ mà build record không lưu.

Đừng dùng override CLI không được kiểm soát để phát hành hai artifact khác nhau dưới cùng một version ứng dụng. Khi đã chốt upgrade, nên sửa POM/property được review và commit, sau đó xác minh resolved tree trong CI.

## 7. Cách 3: dependencyManagement ở POM cha

`<dependencyManagement>` là cơ chế chính để **quản lý version, scope và một số thuộc tính dependency được áp dụng khi được tham chiếu**. Nó thường nằm trong parent POM khi nhiều module kế thừa chung.

### 7.1. Quy tắc căn bản

Trong **POM cha**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Trong **POM con** có quan hệ `<parent>` hợp lệ:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
~~~

Maven sử dụng version được quản lý (`3.14.0`) cho dependency mà child **thực sự khai báo**. Nếu module không cần Commons Lang và không khai dependency, chỉ vì parent quản lý version **không có nghĩa module đó tự kéo Commons Lang vào classpath**.

Sự khác biệt:

| Vị trí | Quản lý version? | Tự đưa dependency vào project? |
| --- | --- | --- |
| `<dependencies>` | Có thể khai version trực tiếp | **Có**, khi dependency hợp lệ và scope áp dụng |
| `<dependencyManagement>` | **Có** | **Không** |
| `<properties>` | Chỉ cung cấp giá trị có thể được dùng | **Không** |
| `<build><pluginManagement>` | Quản lý Maven plugins | **Không quản lý project dependencies** |

Đừng đưa Commons Lang vào parent `<dependencies>` chỉ để “quản lý version”. Các dependency bình thường ở parent `dependencies` có thể **được kế thừa** vào mọi child, bao gồm module không cần thư viện đó. Đặt version trong parent `dependencyManagement`, còn child tự chọn thư viện nào thực sự dùng, là thiết kế minh bạch hơn.

### 7.2. Parent có thể vừa quản lý vừa dùng property

Ví dụ:

~~~xml
<properties>
    <commons.lang3.version>3.14.0</commons.lang3.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>${commons.lang3.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi muốn đổi version cho mọi module con **đang dùng managed dependency này**, bạn sửa **một giá trị property** rồi build/test lại các module. Parent cho phép mọi child nhận cùng chính sách version, miễn là chúng thực sự khai dependency và không override bằng version/management riêng.

## 8. Ví dụ thứ hai: parent quản lý version, child khai dependency không ghi version

Để kiểm tra inheritance thật, tạo **dự án riêng** `managed-demo`. Mã Java và test được dùng lại từ `version-demo`, nhưng nằm dưới `app/src`.

### 8.1. Cây thư mục

~~~text
managed-demo/
├── pom.xml                     # parent + aggregator
└── app/
    ├── pom.xml                 # project jar con
    └── src/
        ├── main/java/vn/example/version/App.java
        └── test/java/vn/example/version/AppTest.java
~~~

Copy nguyên văn nội dung `App.java` và `AppTest.java` từ mục 4.3–4.4 vào **đúng hai đường dẫn mới**. Đây là việc tổ chức lại source; không phải một chương trình khác.

### 8.2. POM cha đầy đủ: `managed-demo/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>version-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <commons.lang3.version>3.14.0</commons.lang3.version>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>${commons.lang3.version}</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.jupiter.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.1</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.4</version>
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
        </pluginManagement>
    </build>
</project>
~~~

Parent ở đây làm hai vai trò:

- **Aggregator** qua `<modules><module>app</module></modules>` để build parent và app trong reactor.
- **Parent POM** qua quan hệ `<parent>` mà `app/pom.xml` sẽ khai báo.

Lưu ý: `<modules>` **không tự làm child kế thừa**. Nếu app không khai `<parent>`, nó không tự nhận `dependencyManagement` của parent chỉ vì được liệt kê trong reactor.

Hai cấu trúc quản lý khác nhau:

- `dependencyManagement` quản lý **dependencies của ứng dụng**, như Commons Lang/JUnit.
- `pluginManagement` quản lý **plugin build** như Compiler/Surefire/Dependency Plugin. Nó không thay thế `dependencyManagement` và không tự chạy một plugin goal tùy ý chỉ vì plugin xuất hiện ở phần management.

### 8.3. POM con đầy đủ: `managed-demo/app/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example</groupId>
        <artifactId>version-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>version-demo</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <configuration>
                    <includeScope>runtime</includeScope>
                    <outputDirectory>${project.build.directory}/runtime-libs</outputDirectory>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven dùng:

- `vn.example:version-parent:1.0.0` để giải quyết POM cha.
- `commons-lang3` version `3.14.0` (qua parent property và dependencyManagement).
- `junit-jupiter` version `5.11.4` qua parent management; `scope=test` từ chính child.
- Compiler/Surefire/JAR plugin versions từ parent pluginManagement khi plugin được kích hoạt bởi lifecycle mặc định của packaging `jar`.
- Dependency Plugin version `3.8.1` từ parent pluginManagement, vì child khai báo plugin và trực tiếp gọi goal copy-dependencies.

**Không có `<version>` ở hai dependency của child**. Đó là tác dụng dễ nhìn nhất của quản lý tập trung. Hai dependency vẫn thuộc app vì chúng được child khai trong `<dependencies>`.

### 8.4. Build và chạy từ reactor root

Từ thư mục `managed-demo`:

~~~bash
mvn -version
mvn clean package
mvn -pl :version-demo dependency:tree -Dincludes=org.apache.commons:commons-lang3
mvn -pl :version-demo dependency:copy-dependencies
~~~

`mvn clean package` từ gốc reactor build parent `packaging=pom` rồi app `packaging=jar`. Hai command có `-pl :version-demo` chọn đúng module app đã tồn tại; bản demo này chỉ có một module con, không cần `-am`.

Quan sát sau khi build:

~~~text
managed-demo/
├── pom.xml
└── app/
    └── target/
        ├── classes/vn/example/version/App.class
        ├── test-classes/vn/example/version/AppTest.class
        ├── version-demo-1.0.0.jar
        └── runtime-libs/commons-lang3-3.14.0.jar
~~~

Trên Linux/macOS, từ **reactor root**:

~~~bash
java -cp "app/target/version-demo-1.0.0.jar:app/target/runtime-libs/*" vn.example.version.App
~~~

Trên Windows:

~~~bat
java -cp "app\target\version-demo-1.0.0.jar;app\target\runtime-libs\*" vn.example.version.App
~~~

Stdout chính xác:

~~~text
Maven BUILD
~~~

Cả hai dự án trực tiếp và quản lý tập trung cho cùng kết quả vì cùng nguồn Java, version Commons Lang và cách ghép runtime classpath. Sự khác nhau nằm ở **nơi định nghĩa version và cách nhiều module có thể dùng chung quy tắc**.

### 8.5. Nâng version từ một nơi

Trong `managed-demo/pom.xml`, đổi đúng property:

~~~xml
<commons.lang3.version>3.17.0</commons.lang3.version>
~~~

Rồi chạy lại:

~~~bash
mvn clean package
mvn -pl :version-demo dependency:tree -Dincludes=org.apache.commons:commons-lang3
mvn -pl :version-demo dependency:copy-dependencies
~~~

Phiên bản mong đợi trong tree là `3.17.0`, trong thư mục runtime-libs là `commons-lang3-3.17.0.jar`. Child POM **không cần sửa version**. `AppTest` phải PASS, và chương trình vẫn in:

~~~text
Maven BUILD
~~~

Nếu sau này thêm nhiều module con có `<parent>version-parent</parent>` và khai Commons Lang **không kèm version riêng**, chúng có thể nhận cùng managed version. Vẫn phải test mọi module bị ảnh hưởng; thay một property trung tâm có thể mở rộng phạm vi thay đổi hơn một dòng direct dependency.

## 9. Điều gì có ưu tiên khi vừa có direct version vừa có dependencyManagement?

Hiểu thứ tự giúp tránh kiểu nghĩ “parent luôn thắng”. Maven có nhiều cơ chế: khai báo trực tiếp, management, mediation và POM inheritance.

### 9.1. Một dependency trực tiếp khai version riêng

Giả sử parent quản lý Commons Lang `3.14.0`, nhưng child viết:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.17.0</version>
    </dependency>
</dependencies>
~~~

Child đã **chủ động khai phiên bản trực tiếp**. Đối với dependency trực tiếp ấy, version khai ở child thông thường được sử dụng thay vì version do parent quản lý. Không nên chờ `dependencyManagement` của parent ép child về `3.14.0` khi child đã có khai báo explicit version.

Đây là một kỹ thuật override hợp lệ nếu module cần một exception đã được review. Nhưng nếu tổ chức đặt policy “mọi module phải dùng bản 3.14.0” thì child có version riêng có thể vi phạm chính sách; nên dùng kiểm tra automated thay vì chỉ tin parent đã quản lý.

### 9.2. Child có dependencyManagement riêng

Parent:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Child cũng có `dependencyManagement` cho cùng tọa độ với `3.17.0` và dependency thực tế không ghi version. Khi Maven hợp nhất model, khai báo quản lý **ở POM hiện tại** có ưu tiên so với inherited dependencyManagement của parent cho cùng entry. Kết quả version được quản lý ở child sẽ là `3.17.0`.

### 9.3. Managed version và transitive mediation

Giả sử ứng dụng `A` kéo một thư viện `D` qua hai nhánh:

~~~text
A
├── B:1.0 ──> D:1.0
└── C:1.0 ──> D:2.0
~~~

Không quản lý `D`, nearest-definition và thứ tự nhánh có thể quyết định. Nhưng nếu `A` khai trong `dependencyManagement` một version `D:2.0`, Maven có thể điều khiển version `D` được chọn trong **transitive dependencies**, thay vì chỉ dựa trên mediation.

Phần management này **không tự thêm một dependency mới** nếu graph hoàn toàn không cần `D`. Nó là quy tắc áp dụng khi Maven gặp entry phù hợp. Bảng tóm tắt:

| Trường hợp | Version nào chi phối? |
| --- | --- |
| POM hiện tại khai direct dependency có version cụ thể | Version trực tiếp khai báo, theo dependency resolution và các ràng buộc hợp lệ |
| Direct dependency bỏ version, có dependencyManagement hiệu lực | Version được quản lý |
| Transitive dependency có nhiều version, có management ở project hiện tại | Management được áp dụng theo Maven rules và thường ưu tiên hơn mediation |
| Transitive dependency có nhiều version, không có management | Nearest definition; nếu cùng độ sâu, khai báo gặp trước |
| Child có management riêng và parent quản lý cùng entry | Management ở child thường ưu tiên sau model merge |
| Không có dependency trong graph, chỉ có management | Không phát sinh JAR tự động |

**Hãy dùng `dependency:tree` để kiểm chứng trường hợp thật.** Bảng trên là cơ chế cơ bản; version ranges, classifier/type, scope, exclusions, BOM imports hoặc parent chain phức tạp có thể làm kết quả khác suy đoán từ một đoạn POM.

## 10. Dùng BOM để quản lý cả nhóm phiên bản thư viện

### 10.1. BOM là gì?

**BOM (Bill of Materials)** trong Maven là một POM chủ yếu tập hợp các entry quản lý dependency, đặc biệt hữu ích khi một framework hoặc một họ thư viện cần nhiều module có **version tương thích nhau**.

Bạn có thể **import** BOM từ một project độc lập, không cần biến nó thành parent POM. Điều này quan trọng vì một Maven project chỉ có một `<parent>` trực tiếp, nhưng có thể import các BOM hợp lệ vào `dependencyManagement`.

Cú pháp import của Maven 3:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.11.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Trong POM dùng BOM, bạn vẫn khai dependency thật:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Khi BOM đã quản lý đúng entry, `junit-jupiter` không cần viết version riêng. Dù vậy **BOM không tự thêm JUnit vào dự án**. Các module chỉ nhận dependency nào chúng khai báo (hoặc đến qua transitive graph theo quy tắc thông thường).

### 10.2. BOM khác parent POM như thế nào?

| Parent POM | BOM import |
| --- | --- |
| Child khai `<parent>`; chỉ có một parent trực tiếp | Import trong `dependencyManagement`; có thể phối hợp nhiều BOM |
| Có thể truyền properties, pluginManagement, build config, dependencyManagement... | Chủ yếu mang tập managed dependency entries vào POM nhập |
| Phù hợp tổ chức build chung nhiều module trong team | Phù hợp giữ đồng bộ version cho một họ thư viện/framework |
| Có thể đồng thời là aggregator `<modules>` | Không tự làm aggregator hoặc parent cho project nhập |
| Có thể chứa pluginManagement | BOM import không thay thế pluginManagement |

Một kiến trúc phổ biến là **parent POM của tổ chức quản lý Maven plugins và tiêu chuẩn build**, đồng thời import một hoặc nhiều BOM để quản lý version của các framework. Child chỉ khai dependencies nó thực sự sử dụng.

### 10.3. Import nhiều BOM có cùng entry

Nếu hai BOM import cùng quản lý một tọa độ, thứ tự import và khả năng đã có một entry quản lý explicit trong POM nhập đều quan trọng. Trong Maven 3, **khi các BOM import cùng quản lý một tọa độ, BOM được khai trước thường thắng** cho entry trùng, nếu không có quy tắc quản lý explicit/overrides khác ưu tiên hơn.

Vì thế không nên import nhiều BOM trùng nhau rồi mặc định “BOM mới nhất thắng”. Khi cần một version riêng được tổ chức chấp nhận, dùng dependencyManagement explicit trong POM nhập/parent ở cấp phù hợp, và xác minh bằng effective POM + resolved tree.

### 10.4. Không nhầm import BOM với dependency loại pom thông thường

Chỉ `<type>pom</type>` và `<scope>import</scope>` **bên trong `dependencyManagement`** mới tạo hành vi import các managed entries. Đặt một POM dependency có `scope=compile` trong `dependencies` không tự có tác dụng quản lý version như BOM.

Trong ví dụ managed-demo, thay việc parent quản lý JUnit trực tiếp bằng JUnit BOM là một **phương án refactor riêng**, không cần áp dụng đồng thời chỉ để học cách nâng Commons Lang. Nếu có cả BOM và entry explicit cho cùng artifact, cần biết entry nào được chọn theo quy tắc quản lý và model merge.

## 11. Đừng đổi nhầm project version, dependency version và plugin version

Trong một POM có nhiều trường `<version>`:

~~~xml
<project>
    <!-- ... -->
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
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
~~~

Đoạn trên minh họa những vị trí riêng biệt:

- `project.version=1.0.0`: version **artifact ứng dụng** `vn.example:version-demo`.
- `commons-lang3.version=3.17.0` ở dependency: version **thư viện ứng dụng**.
- `maven-compiler-plugin.version=3.14.1`: version **công cụ build**, không phải Commons Lang.
- `junit-jupiter.version=5.11.4`: version thư viện test.

**Lưu ý:** trích đoạn `<project>` có comment `<!-- ... -->` để minh họa vị trí, **không phải POM hoàn chỉnh**. Hãy chạy ví dụ nguyên vẹn ở mục 4 hoặc 8 thay vì copy một snippet như project độc lập.

### 11.1. dependencyManagement không quản lý plugin transitive dependencies

Maven docs nêu rõ: project `dependencyManagement` **không áp dụng cho các transitive dependencies của Maven plugins**. Ví dụ bạn quản lý `commons-lang3` trong project thì không được mặc định kết luận plugin Maven vốn phụ thuộc một bản Commons Lang nào đó sẽ dùng chính version này.

Muốn kiểm soát **plugin version**, dùng `pluginManagement` hoặc `build/plugins` với version rõ. Khi cần thay dependency bên trong một plugin, đó là phạm vi **plugin configuration/dependency** khác với project dependency và cần tài liệu plugin tương ứng.

### 11.2. Đổi project.version không phải nâng dependency

Lệnh/phương pháp thay `project.version` chỉ đổi bản phát hành artifact ứng dụng; nó **không tự nâng** version của các thư viện ngoài. Nếu dependency được khai bằng property `${project.version}` để trỏ tới module cùng reactor thì có thể đổi theo version ứng dụng — nhưng không áp dụng công thức đó bừa bãi cho Commons Lang/JUnit.

Với multi-module, thay `project.version` còn có thể cần đồng bộ các `<parent><version>` và dependency giữa module; hãy dùng quy trình release/versioning đã được tổ chức chuẩn hóa.

## 12. Cách kiểm tra phiên bản Maven thực sự chọn

Một quy trình gỡ lỗi version resolution nên có **ba nguồn bằng chứng**: effective POM, resolved dependency tree và test/runtime.

### 12.1. Đọc dependency tree

Trong project đơn:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Trong reactor có app:

~~~bash
mvn -pl :version-demo dependency:tree
mvn -pl :version-demo dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Các node hiển thị version resolved và scope, ví dụ:

~~~text
org.apache.commons:commons-lang3:jar:3.17.0:compile
~~~

Với xung đột, Maven Dependency Plugin có thể hỗ trợ thông tin verbose/omitted theo goal và phiên bản. Đừng đọc một vài dòng log rồi suy đoán toàn bộ mediation; dùng graph đầy đủ và kiểm tra version plugin goal đang dùng.

### 12.2. Đọc effective POM

~~~bash
mvn help:effective-pom
mvn -pl :version-demo help:effective-pom
~~~

Effective POM cho thấy dependencyManagement, dependencies, properties, parent và profile đã được hợp nhất. Nếu muốn tìm nguồn gốc khai báo, Help Plugin có chế độ verbose:

~~~bash
mvn -pl :version-demo help:effective-pom -Dverbose
~~~

Hãy tìm `<commons.lang3.version>` và entry `org.apache.commons:commons-lang3` trong management và dependencies của **đúng module**.

Một effective POM có version bạn mong muốn **chưa đủ chứng minh** resolved graph và runtime classpath; `dependency:tree` là kiểm tra bổ sung không thể bỏ qua.

### 12.3. Kiểm tra resolved artifact ở runtime

Trong ví dụ:

~~~bash
mvn clean package
mvn dependency:copy-dependencies
~~~

Xem `target/runtime-libs` để xác nhận JAR của Commons Lang version đúng. Sau đó chạy `java -cp` với **đúng thư mục runtime-libs mới**, không trộn một JAR 3.14.0 từ lần thử trước với 3.17.0.

Khi dự án dùng Shade, WAR, Spring Boot packaging, Docker hoặc application server, hãy kiểm tra **bộ phân phối mà tiến trình triển khai thực sự nạp**, không chỉ artifact trong local Maven repository.

### 12.4. Kiểm tra phụ thuộc phiên bản trôi do SNAPSHOT và ranges

Trong dự án phát hành ổn định, nên tránh dùng version range rộng hoặc SNAPSHOT không có quy trình quản lý rõ, bởi cùng POM có thể giải quyết nội dung khác theo thời điểm/repository.

Ví dụ range:

~~~xml
<version>[3.14.0,4.0.0)</version>
~~~

Đây là yêu cầu chọn một version trong khoảng, **không ghim một phiên bản duy nhất**. Nó cũng không thay thế việc đánh giá API/compatibility. Tránh dùng `LATEST`/`RELEASE` theo ví dụ cũ không còn phù hợp với Maven hiện đại. Với release cần truy vết, ghi lại phiên bản thực tế đã resolve và artifact được phát hành.

`-U` có thể yêu cầu Maven kiểm tra metadata/SNAPSHOT mới nhưng không đồng nghĩa “ép dùng version mới nhất của mọi dependency”. `mvn clean` chỉ dọn output trong `target`, không xóa Maven dependency cache.

## 13. Thay version an toàn trong dự án nhiều module: quy trình đề xuất

### Bước 1 — Xác định phạm vi version cần thay

Ghi rõ **tọa độ** `groupId:artifactId`, version cũ và version mục tiêu đã được phê duyệt. Ví dụ:

~~~text
org.apache.commons:commons-lang3
3.14.0 -> 3.17.0
~~~

Đừng đổi theo chuỗi toàn repo `3.14.0` mà không nhìn ngữ cảnh: chuỗi đó có thể xuất hiện ở tài liệu, plugin version khác hoặc dependency có tọa độ khác.

### Bước 2 — Xác định version đến từ đâu

Tìm ở những nơi thực sự có thể quyết định version của project:

- `<dependencies><dependency><version>` trong POM module.
- Property như `<commons.lang3.version>`.
- `<dependencyManagement>` trong parent chain.
- Imported BOM.
- Effective profile đang hoạt động.
- Transitive dependency path và mediation khi không có entry explicit/management tương ứng.

Khi thông tin ở POM con trông thiếu, **đừng vội thêm version**; nó có thể cố ý sử dụng version từ parent/BOM.

### Bước 3 — Chọn một điểm sửa phù hợp

| Tình huống | Nơi nên sửa | Điều phải kiểm tra |
| --- | --- | --- |
| Một project độc lập, version chỉ khai một nơi | Dependency direct `<version>` | Runtime/test của project |
| Nhiều tham chiếu cùng version trong một model | `<properties>` và các reference | Có vị trí nào không dùng property? |
| Nhiều module kế thừa parent chung | Parent `dependencyManagement` hoặc property của parent | Module nào override version? |
| Nhiều artifact của cùng framework phải đồng bộ | BOM version hoặc dependencyManagement tích hợp BOM | Version tương thích và các entry BOM quản lý |
| Chỉ một module cần ngoại lệ | Child direct version hoặc child dependencyManagement | Tương thích với các module khác và policy |
| Version do transitive dependency mang đến | Management ở project dùng, hoặc nâng parent dependency thích hợp | Không phá dependency graph/ABI |
| Plugin build cần nâng | `pluginManagement` hoặc `build/plugins` | Plugin compatibility với Maven/JDK, không nhầm project deps |

Một quy tắc đơn giản: **đổi tại nguồn quản lý thực sự đang quyết định version**, thay vì thêm override ở nhiều tầng khiến lần nâng sau khó kiểm soát.

### Bước 4 — Xem diff và chạy build sạch

Tối thiểu:

~~~bash
mvn clean verify
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Với reactor lớn, nên kiểm tra tất cả module bị ảnh hưởng; nhiều module có thể cần integration test, contract test hoặc runtime smoke test. Có thể dùng `-pl`/`-am` để rút phạm vi khi điều tra, nhưng trước khi release cần build/QA theo pipeline chính thức.

### Bước 5 — Kiểm tra API, binary và hành vi runtime

Một phiên bản mới có thể:

- Đổi hoặc bỏ API làm mã compile không còn.
- Giữ API biên dịch được nhưng thay runtime behavior, gây lỗi logic.
- Kéo transitive dependency khác, thay method/class có sẵn lúc runtime.
- Yêu cầu JDK/bytecode target cao hơn.
- Thay behavior serialization, logging, encodings hoặc chuẩn giao tiếp.
- Sửa lỗ hổng nhưng đồng thời đưa breaking change cần xử lý.

Không đánh đồng `mvn clean package` thành công với tất cả hệ thống đã tương thích. Hãy đọc release notes của thư viện liên quan và chạy kiểm thử theo rủi ro của project.

### Bước 6 — Chốt phát hành và khả năng truy vết

Lưu commit, version mới, Maven/JDK version, active profiles, resolved tree hoặc build report phù hợp, checksum của artifact/distribution và kết quả test. Nếu release artifact được xuất bản lên repository với chính sách bất biến, không ghi đè một version đã phát hành bằng một build có dependency khác mà không thay release identity.

Ưu tiên xây **một artifact chuẩn trên CI**, lưu nó, rồi triển khai chính artifact đó thay vì build lại cùng version trên nhiều máy với settings/profile khác.

## 14. Dependency mediation không thay thế quy tắc tương thích

Giải quyết được một version không đồng nghĩa version ấy là lựa chọn tốt nhất. Maven chọn theo quy tắc model/graph; Maven không tự suy luận compatibility giữa mọi API.

### 14.1. Lỗi khi build

Nếu mã ứng dụng import một method đã bị xóa trong phiên bản mới:

~~~text
cannot find symbol
~~~

là bằng chứng compile classpath không cung cấp API được dùng. Bạn cần xem compiler log, version resolved và release notes; không thể khẳng định “Maven bị lỗi version” chỉ từ thông điệp này.

### 14.2. Lỗi khi chạy

Nếu code compile với một API nhưng runtime classpath lại nạp một bản không tương thích, lỗi có thể là:

~~~text
java.lang.NoSuchMethodError
java.lang.NoClassDefFoundError
java.lang.ClassNotFoundException
~~~

Một JAR bị thiếu cũng có thể gây lỗi tương tự. Hãy xem **classpath thực tế**, class loader, dependency tree, cách đóng gói và phiên bản trong thư mục lib. Đừng vội thêm exclusions hoặc sửa scope khi chưa tìm ra class nào vắng mặt và vì sao.

### 14.3. Dependency convergence

Một dự án có thể có hai đường dependency tới hai version khác nhau của cùng artifact. Maven thông thường chọn một version cuối theo mediation, nhưng việc phụ thuộc hai version khác nhau có thể làm đội ngũ khó nâng cấp.

Maven Enforcer Plugin có rule **`dependencyConvergence`** và **`requireUpperBoundDeps`** để phát hiện những tình huống nhất định. Rule hội tụ chặt có thể gây nhiều cảnh báo/lỗi trong project framework lớn, nên cần policy và exceptions được review thay vì bật bừa toàn bộ rules mà không hiểu. Đây là công cụ bổ sung, **không thay thế** `dependency:tree` và kiểm thử runtime.

### 14.4. Exclusions và optional

- `<exclusions>` có thể loại một dependency bắc cầu qua **một cạnh cụ thể** của graph. Loại nhầm artifact cần lúc chạy có thể gây `NoClassDefFoundError`.
- `<optional>true</optional>` đánh dấu dependency không tự lan sang downstream như dependency bắt buộc; nó **không** nói artifact là an toàn để bỏ trong project khai báo nó.
- Khi muốn đổi version, ưu tiên quản lý/chọn version có chủ đích; chỉ dùng exclusion khi **có căn cứ loại dependency**, không dùng như một “bộ chọn version” mơ hồ.

## 15. Tình huống thực tế: version chung và ngoại lệ đã được phê duyệt

Giả sử công ty có một parent:

~~~text
company-parent
  dependencyManagement:
    commons-lang3 = 3.17.0
    junit-jupiter = 5.11.4
~~~

Các module:

~~~text
service-a
  dependencies:
    commons-lang3 (không ghi version)
service-b
  dependencies:
    commons-lang3 (không ghi version)
legacy-adapter
  dependencies:
    commons-lang3 = 3.14.0 (override có chủ đích)
~~~

`service-a` và `service-b` nhận managed version `3.17.0`. `legacy-adapter` đang chọn bản riêng để xử lý tương thích legacy. Nếu không ghi rõ ngoại lệ, một đồng đội có thể nhầm đó là version “bị bỏ quên” và sửa cưỡng bức, gây lỗi.

Quy trình tốt là:

- Ghi **lý do kỹ thuật** và người chấp thuận ngoại lệ trong tài liệu quản lý dependency/issue nội bộ.
- Có thời hạn/điều kiện loại ngoại lệ, thay vì để tồn tại mãi.
- CI kiểm tra resolved tree của các module quan trọng.
- Test cả module dùng bản chung và module legacy sau khi thay parent.
- Không giả định hai module có cùng parent luôn có cùng classpath nếu một trong hai khai explicit version hoặc profile riêng.

Ví dụ này là **sơ đồ policy**, không phải POM hoàn chỉnh. Để thực hành runnable, dùng mã và POM ở mục 4 và 8.

## 16. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hành động phù hợp |
| --- | --- | --- |
| Child khai dependency không có `version` và Maven báo thiếu | Không có managed entry hiệu lực; parent/BOM chưa được giải quyết hoặc tọa độ không khớp | Xem `<parent>`, dependencyManagement, `type/classifier` và effective POM |
| Đã nâng property ở parent nhưng resolved tree vẫn version cũ | Child direct override hoặc child management/BOM/profile khác | Kiểm tra effective POM đúng module, loại override không chủ đích |
| `dependencyManagement` có Commons Lang nhưng module không thấy thư viện | Management không tự thêm dependency | Khai dependency thật trong `<dependencies>` của module cần |
| Hai nhánh transitive yêu cầu hai version | Nearest-definition hoặc management đang chọn một version | Xem dependency tree và quản lý version phù hợp |
| Maven chọn version khác vì đổi thứ tự dependency | Các đường bằng độ sâu, khai trước thắng | Khai managed version rõ ràng, không dựa vào thứ tự XML |
| Cập nhật `pluginManagement` nhưng project dependency không đổi | Plugin version khác project dependency | Sửa đúng phần `dependencyManagement` hoặc `dependencies` |
| Import BOM nhưng dependency vẫn không được nhận | BOM chỉ quản lý version, không tự thêm dependency | Khai dependency thật, xác nhận BOM đã import đúng |
| BOM version không có tác dụng với entry cụ thể | Entry explicit hoặc BOM khác đang ưu tiên | Xem management order và effective POM |
| Test pass nhưng runtime báo `NoSuchMethodError` | Runtime JAR khác compile hoặc API binary không tương thích | Kiểm tra bản phân phối/classpath, transitive conflicts và smoke test |
| `-Dcommons.lang3.version` trên CI làm build khác developer | Property override theo môi trường | Loại override ngầm hoặc lưu build parameter và kiểm soát phát hành |
| Dùng SNAPSHOT/range khiến build khác ngày | Dependency resolution động hoặc metadata repository thay đổi | Ghim release version và lưu resolved metadata |
| Thư mục runtime-libs có cả hai version | Chưa clean sau khi đổi dependency hoặc packaging copy cũ | Dọn output project, build/copy lại và kiểm tra file thực tế |
| `mvn dependency:tree` có lỗi không tải plugin | Repository, mirror, proxy hoặc Maven Dependency Plugin chưa có trong cache | Phân biệt lỗi tải plugin với lỗi graph; kiểm tra settings |
| CI dùng JDK khác máy developer | Library yêu cầu Java version/bytecode khác hoặc profiles kích hoạt khác | Cố định JDK/Maven, kiểm tra toolchain và active profiles |
| Chỉ sửa version app để “nâng Commons Lang” | Đổi nhầm `project.version` | Phân biệt tọa độ ứng dụng, dependency và plugin version |
| Maven warning duplicate dependency | Khai cùng `groupId:artifactId:type:classifier` nhiều lần trong một POM | Hợp nhất thành một khai báo có version rõ |
| Build một module đơn thành công nhưng reactor lỗi | Các module khác dùng version hoặc API khác | Chạy reactor QA và test các downstream consumers |
| Có version trực tiếp nhưng child vẫn không compile | Scope sai, repo lỗi, API không còn hoặc classpath chưa đúng | Đọc lỗi thật và `dependency:tree` thay vì chỉ đổi version |

Mỗi khi có lỗi, hãy phân biệt ba lớp:

1. **Model/configuration**: POM, parent, property, BOM, profile và effective POM.
2. **Resolution/classpath**: dependency graph, version được chọn, scope và JAR thật.
3. **Behavior**: compile, test, runtime và cách đóng gói triển khai.

Sửa ở đúng lớp thay vì thay version liên tục không có bằng chứng.

## 17. Bài tập cuối bài

**Bài tập A — Direct version.** Dựng `version-demo`, chạy `mvn clean verify`, xem `dependency:tree` có Commons Lang `3.14.0`. Chạy chương trình với runtime-libs, xác nhận `Maven BUILD`. Sau đó đổi direct dependency sang `3.17.0`, build sạch và xác nhận version resolved đã đổi.

**Bài tập B — Property.** Trong POM đơn, thay literal version bằng `${commons.lang3.version}` và đặt property trong `<properties>`. Thử thay một property rồi kiểm tra effective POM. Giải thích lợi ích và giới hạn của property nếu có nhiều module.

**Bài tập C — DependencyManagement.** Tạo `managed-demo` từ hai POM hoàn chỉnh, copy source/test vào `app`. Xóa version trong hai dependency của child nhưng giữ managed entries trong parent. Chạy `mvn clean package` và `mvn -pl :version-demo dependency:tree`. Chứng minh phiên bản thư viện đến từ parent.

**Bài tập D — Override cục bộ.** Trong `managed-demo/app/pom.xml`, thêm `<version>3.17.0</version>` trực tiếp cho Commons Lang trong child, trong khi parent vẫn quản lý `3.14.0`. Dự đoán version resolved, kiểm tra tree, rồi xóa override để về trạng thái quản lý chung.

**Bài tập E — BOM.** Viết snippet import `org.junit:junit-bom:5.11.4` ở `dependencyManagement` và bỏ version của JUnit dependency thực tế. Giải thích vì sao thiếu khai báo trong `dependencies` thì JUnit không tự được thêm vào project.

**Bài tập F — Mediation.** Với graph `A → B → C → D:2.0` và `A → E → D:1.0`, dự đoán version D nếu không có management. Sau đó đề xuất khai báo ở `A/dependencyManagement` để version D được điều khiển tường minh.

**Bài tập G — Build reproducibility.** Một thành viên build với `-Dcommons.lang3.version=3.17.0`, người khác không truyền flag. Hãy giải thích vì sao hai build có thể cùng version ứng dụng nhưng runtime-libs khác. Đề xuất cách CI ghi nhận tham số và artifact thực tế.

**Bài tập H — Review nâng cấp.** Viết checklist cho lần nâng version production: tọa độ, version cũ/mới, nơi quản lý thực sự, effective POM, dependency tree, unit/integration test, kiểm tra Java compatibility, runtime smoke test, release notes và provenance.

Bạn hoàn thành bài khi có thể **chọn đúng điểm sửa** để thay dependency version, giải thích sự khác biệt giữa *direct declaration*, *property*, *dependencyManagement* và *BOM*, rồi **chứng minh bằng Maven output** rằng version được chọn đúng thay vì chỉ nhìn một dòng XML.

## 18. Tài liệu Apache Maven chính thức và nguồn phiên bản

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): direct/transitive dependencies, nearest-definition, management precedence và BOM.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): `dependencies`, `dependencyManagement`, properties, parent, pluginManagement và version requirements.
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor, aggregation và dependency graph giữa module.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): resolved dependency tree và bộ lọc `includes`.
- [Apache Maven Dependency Plugin — copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): `includeScope` và `outputDirectory`.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): xem cấu hình POM sau merge/inheritance.
- [Maven Central — Commons Lang 3.14.0](https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.14.0) và [3.17.0](https://central.sonatype.com/artifact/org.apache.commons/commons-lang3/3.17.0): tọa độ của hai bản thư viện dùng trong bài.
- [Maven Central — JUnit Jupiter 5.11.4](https://central.sonatype.com/artifact/org.junit.jupiter/junit-jupiter/5.11.4): dependency test và JUnit BOM tương ứng.
