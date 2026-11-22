# Dùng help:effective-pom để truy tìm nguồn cấu hình Maven

## 1. Vì sao pom.xml đang mở chưa phải toàn bộ cấu hình build?

Bạn mở `app/pom.xml` và thấy không khai báo phiên bản `maven-compiler-plugin`, nhưng Maven vẫn biết dùng một phiên bản cụ thể. Bạn không thấy `maven.compiler.release` trong POM của module, nhưng build lại biên dịch theo Java 17. Hoặc một người chạy Maven trên máy của họ nhận phiên bản dependency khác với CI dù hai bên dùng cùng mã nguồn.

Đó là lúc cần xem **effective POM**: mô hình POM cuối cùng mà Maven xây dựng từ cấu hình dự án, parent POM, Super POM, những profile đang hoạt động và quá trình nội suy/ghép cấu hình. Goal `help:effective-pom` của **Maven Help Plugin** xuất mô hình này dưới dạng XML để người học kiểm tra giá trị cuối cùng và xác định nguồn của chúng.

Bài này giải thích cách sử dụng **`help:effective-pom` để truy tìm nguồn cấu hình**. Trọng tâm là phương pháp điều tra một giá trị không xuất hiện, xuất hiện khác mong đợi hoặc bị ghi đè; không chỉ là học thuộc một lệnh.

Sau bài học, bạn có thể:

1. Giải thích khác nhau giữa POM gốc, parent POM, Super POM và effective POM.
2. Chạy `help:effective-pom` bằng một phiên bản Help Plugin xác định, xuất kết quả ra tệp và bật **`verbose`** để đọc chú thích nguồn.
3. Lần theo cấu hình compiler, plugin, dependency và thuộc tính từ POM con, POM cha, profile hoặc cấu hình mặc định.
4. Kết hợp `help:active-profiles`, `help:evaluate`, `help:effective-settings`, `dependency:tree` và log để xác định đúng vấn đề.
5. Phân biệt cái **effective POM cho thấy** với cái nó **chưa chứng minh**: dependencies đã phân giải, thứ tự thực thi goal, giá trị runtime, settings/credential và môi trường CI.
6. Áp dụng quy trình chẩn đoán có thể lặp lại trước khi sửa POM.

**Tình huống mẫu:**

~~~text
app/pom.xml:
    không thấy phiên bản compiler plugin
    không thấy maven.compiler.release
                  |
                  v
          Maven Model Builder
             /    |     \
  app/pom.xml  parent POM  Super POM
              active profiles
                  |
                  v
          Effective POM (XML)
                  |
                  v
    compiler plugin 3.14.0
    maven.compiler.release = 17
                  |
                  v
    Xem nguồn: parent POM? profile? default?
~~~

Đây là mô hình khái quát. Effective POM mô tả **mô hình dự án sau khi Maven kết hợp các nguồn cấu hình**, nhưng không có nghĩa mọi tham số runtime cuối cùng của mọi plugin đã được tính xong.

## 2. Các lớp nguồn cấu hình cần phân biệt

### 2.1. POM trực tiếp của module

Thông thường đây là `pom.xml` tại thư mục module đang build. Nó có thể chứa `<properties>`, `<dependencies>`, `<dependencyManagement>`, `<build>`, `<plugins>`, `<pluginManagement>` và `<profiles>`. Một module thường chỉ khai báo các giá trị đặc thù, vì cấu hình dùng chung đã nằm trong parent.

### 2.2. Parent POM và kế thừa

Một module trỏ đến parent POM bằng `<parent>`. Maven có thể kế thừa thuộc tính, danh sách plugin và dependency, plugin management, dependency management cùng nhiều cấu hình khác theo quy tắc của Maven Model Builder.

Ví dụ module không ghi `maven.compiler.release` nhưng parent có:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

thì giá trị này có thể xuất hiện trong effective POM của module. Khi điều tra, phải xem **đúng chuỗi parent**; một parent có thể lại kế thừa từ parent khác.

`<relativePath>` trong `<parent>` chỉ nơi Maven tìm file POM cha trên đĩa khi áp dụng. Nếu path không phù hợp, Maven có thể tìm parent qua repository tùy cấu hình và báo lỗi nếu không tìm thấy. **Parent** và **aggregator** khác nhau: `<parent>` tạo quan hệ kế thừa; `<modules>` tạo danh sách module được reactor xử lý. Một POM có thể đóng cả hai vai trò, nhưng `<modules>` không tự làm module kế thừa thuộc tính.

### 2.3. Super POM

Maven có một **Super POM** cung cấp các giá trị nền tảng như cấu hình repository mặc định, tên thư mục build và những mặc định khác. Khi bạn không khai báo một trường nào đó, một phần giá trị có thể đến từ Super POM hoặc từ **binding của packaging/phiên bản Maven**, chứ không nhất thiết là do parent POM công ty đặt.

Đừng sửa một file “Super POM” để thay đổi build. Thay đổi cần thiết nên khai báo có chủ đích ở POM của dự án hoặc parent dùng chung và cố định Maven/phiên bản plugin phù hợp.

### 2.4. Profile đang hoạt động

Profile trong `pom.xml` hoặc Maven settings có thể bổ sung/thay đổi phần cấu hình dùng cho môi trường khác nhau. Profile có thể kích hoạt bằng `-P`, thuộc tính `-D`, JDK, hệ điều hành, file hoặc `settings.xml` tùy cấu hình.

Điểm quan trọng: **profile không đơn giản được kế thừa như một đối tượng nguyên vẹn**. Maven xử lý profile trong quá trình dựng model; **tác động của profile đang hoạt động** mới được ghép vào model tương ứng và có thể được kế thừa. Vì vậy khi thấy giá trị khác nhau giữa hai môi trường, phải kiểm tra **profile nào đang hoạt động**, không chỉ so hai file `pom.xml`.

### 2.5. Lệnh Maven và cấu hình ngoài POM

Một số thay đổi đến từ command line và môi trường:

- `-Pdev` chọn profile.
- `-Dmaven.compiler.release=21` hoặc các `-D...` khác có thể chi phối plugin/configuration tại thời điểm thực thi.
- `.mvn/maven.config` có thể cung cấp các tùy chọn Maven cho dự án.
- `~/.m2/settings.xml` và settings toàn cục quản lý mirror, server, proxy, repository/profile.
- Maven Wrapper xác định phiên bản Maven mà dự án chạy; JDK/JAVA_HOME quyết định JVM.
- Environment variables, system properties, plugin configuration và cách plugin đánh giá biểu thức có thể ảnh hưởng kết quả cuối.

**Không giả định toàn bộ nguồn này sẽ hiện thành các dòng trong effective POM.** Cần công cụ bổ trợ để kiểm chứng profile, settings, dependency resolution hoặc tham số plugin runtime.

## 3. Lệnh cơ bản và tùy chọn để truy nguồn

Apache Maven Help Plugin cung cấp goal:

~~~bash
mvn help:effective-pom
~~~

Nó có thể in XML rất dài ra terminal. Khi cần điều tra nghiêm túc, nên cố định phiên bản Help Plugin và ghi ra tệp để tìm kiếm, so sánh.

Bài học dùng **Maven Help Plugin 3.5.2** làm phiên bản minh họa. Bạn có thể gọi đầy đủ tọa độ plugin để tránh phụ thuộc phiên bản được phân giải ngầm:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Doutput=effective-pom.xml
~~~

Các phần của lệnh:

| Thành phần | Tác dụng |
| --- | --- |
| `-B` | Batch mode, phù hợp script/CI |
| `-ntp` | Giảm tiến trình tải artifact trong log |
| `org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom` | Chọn chính xác group, artifact, phiên bản plugin và goal |
| `-Doutput=effective-pom.xml` | Viết effective POM ra tệp UTF-8 thay vì in toàn bộ XML ra console |

Nếu cần biết **từng phần tử đến từ đâu**, dùng:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom-verbose.xml
~~~

Tùy chọn `verbose` (user property `verbose`) được Maven Help Plugin hỗ trợ từ phiên bản **3.2.0**. Khi bật, plugin thêm **chú thích XML về vị trí/nguồn đầu vào** cho các phần tử. Đây là công cụ hữu ích nhất để truy ngược giá trị về parent, POM hiện tại hoặc nguồn mô hình phù hợp.

**Cần lưu ý về chứng cứ:** chú thích do plugin tạo phản ánh vị trí phần tử ở những nguồn model mà Maven biết; sau quá trình ghép, nội suy và quản lý phiên bản, không phải mọi quyết định cuối cùng đều có một “dòng POM duy nhất” giải thích trọn vẹn. Hãy dùng chú thích làm **đầu mối**, sau đó mở file nguồn, kiểm tra profile và xác nhận bằng lệnh Maven phù hợp.

Với phiên bản Help Plugin **trước 3.2.0**, tham số `verbose` không được hỗ trợ. Nếu chạy lệnh cũ mà không thấy chú thích, kiểm tra phiên bản plugin thật; cách dễ tái lập là gọi đủ tọa độ như ví dụ.

### 3.1. Chọn đúng POM của đúng module

Tại một thư mục có `pom.xml`:

~~~bash
mvn -version
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
~~~

Ở reactor nhiều module, goal có tính **aggregator** và có thể xử lý nhiều dự án trong build session. Khi chỉ muốn tìm nguồn cấu hình của `app`, hãy **đi vào chính thư mục `app` có POM phù hợp**, hoặc dùng `-f` trỏ trực tiếp đến POM đó:

~~~bash
mvn -B -ntp -f app/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=app-effective-pom.xml
~~~

Đường dẫn `app/pom.xml` tính từ thư mục hiện tại. Tệp output tương đối có thể được giải quyết theo ngữ cảnh dự án/goal; hãy kiểm tra vị trí tệp thực tế sau lệnh hoặc dùng đường dẫn tuyệt đối khi cần. Không nhầm effective POM của parent `packaging=pom` với effective POM của module ứng dụng.

### 3.2. Bật profile đúng như lệnh build thực tế

Muốn xem cấu hình khi bật profile `local`:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Plocal -Dverbose=true -Doutput=effective-pom-local.xml
~~~

**Quan trọng:** `-Plocal` trong lệnh xem effective POM phải khớp với `-Plocal` của build thực tế. Nếu build dùng `-Denv=prod` để kích hoạt profile bằng property, phải tái hiện điều kiện kích hoạt đó khi chẩn đoán.

### 3.3. Vì sao nên lưu cả bản thường và bản verbose?

Bản thường dễ đọc để xác định **giá trị hiệu lực**. Bản verbose có nhiều chú thích giúp **lần ra nguồn**. Khi so sánh trước/sau một thay đổi, nên tạo hai bản cùng điều kiện Maven, JDK, profile và CLI:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Doutput=effective-pom.xml
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom-verbose.xml
~~~

Chỉ giữ các tệp XML xuất ra để điều tra; đừng tự động commit chúng lên repository. Effective POM có thể chứa cấu hình nội bộ hoặc giá trị từ profile/thuộc tính môi trường. Cần xem trước khi chia sẻ và tránh đưa bí mật vào log/report.

## 4. Ví dụ chạy được: parent POM, module con và profile

Ta tạo dự án Maven nhỏ để thấy một cấu hình “biến mất” khỏi POM con nhưng lại xuất hiện trong effective POM. Dự án có một parent kiêm aggregator và một module Java 17.

Cấu trúc:

~~~text
config-trace/
├── pom.xml
└── app/
    ├── pom.xml
    └── src/
        └── main/
            └── java/
                └── dev/
                    └── example/
                        └── App.java
~~~

### 4.1. Parent POM: config-trace/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>config-trace</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <demo.label>from-parent</demo.label>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.0</version>
                    <configuration>
                        <release>${maven.compiler.release}</release>
                    </configuration>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

Giải thích:

- `<packaging>pom</packaging>` giúp parent làm aggregator; `<modules>` gồm một module `app`.
- `maven.compiler.release=17` và `demo.label=from-parent` là các property từ parent.
- `pluginManagement` đặt phiên bản Compiler Plugin `3.14.0` và `release` dùng property. Nó quản lý cấu hình của plugin khi plugin được sử dụng; đây **không phải** một execution mới tự chạy.
- Không có mã nguồn Java trong parent, nên parent `packaging=pom` không được mong đợi tự compile một Java class.

### 4.2. Module POM: config-trace/app/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>config-trace</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>local</id>
            <properties>
                <demo.label>from-local-profile</demo.label>
            </properties>
        </profile>
    </profiles>
</project>
~~~

Điểm chủ ý của ví dụ:

- POM con **không khai báo** `<version>` của dự án: nó thừa hưởng `1.0.0` từ parent.
- POM con **không khai báo** `maven.compiler.release`: lấy từ parent.
- POM con dùng `maven-compiler-plugin` nhưng **không khai báo version**: phiên bản và configuration được quản lý bởi parent `pluginManagement`.
- Profile `local` của POM con chỉ thay `demo.label` khi được kích hoạt bằng `-Plocal`; không có `<activation>` nên nó không tự bật.

`packaging` của module con không khai báo, vì thế Maven dùng mặc định `jar`. Không nhầm điều đó với `packaging=pom` của parent: POM con vẫn là một dự án JAR có goal compiler, jar theo lifecycle.

### 4.3. Java 17: config-trace/app/src/main/java/dev/example/App.java

~~~java
package dev.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Effective POM demo OK");
    }
}
~~~

Từ thư mục `config-trace/app` (chứa POM con), chạy:

~~~bash
java -version
mvn -version
mvn -B -ntp compile
java -cp target/classes dev.example.App
~~~

Với JDK 17+ và quá trình build thành công, **stdout chính xác của lệnh Java cuối** là:

~~~text
Effective POM demo OK
~~~

Maven có thể tải plugin trong lần đầu. Đây là chương trình chạy đầy đủ và độc lập, không yêu cầu framework hay dependency bên thứ ba.

### 4.4. Truy ra release và plugin version

Ở `config-trace/app`, chạy:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
~~~

Mở `effective-pom.xml` và tìm:

- `<artifactId>app</artifactId>`: đang xem **POM của module**.
- `<packaging>jar</packaging>`: packaging cuối của app.
- `<maven.compiler.release>17</maven.compiler.release>`: property được kế thừa.
- `<artifactId>maven-compiler-plugin</artifactId>` và `<version>3.14.0</version>`: phiên bản plugin được quản lý từ parent.
- `<release>17</release>` hoặc biểu thức tương ứng tại phần cấu hình plugin (tùy giai đoạn nội suy và cách render): hãy kiểm tra cả `maven.compiler.release`, `pluginManagement` lẫn `plugins`.

**Cách truy nguồn:** đọc chú thích XML do `-Dverbose=true` tạo cạnh các phần tử liên quan. Đối chiếu chúng với `../pom.xml`, `app/pom.xml` và các parent khác nếu có. Chú thích minh họa **vị trí đầu vào**, chứ không phải một công cụ xác nhận dependency/plugin đã chạy thành công.

Có thể dùng lệnh tìm văn bản phù hợp hệ điều hành:

Linux/macOS:

~~~bash
grep -n -C 4 "maven.compiler.release" effective-pom.xml
grep -n -C 4 "maven-compiler-plugin" effective-pom.xml
~~~

Windows PowerShell:

~~~powershell
Select-String -Path .\effective-pom.xml -Pattern 'maven.compiler.release','maven-compiler-plugin' -Context 4,4
~~~

Đầu ra grep/Select-String có thể gồm nhiều vị trí. Hãy nhìn **ngữ cảnh XML**: một plugin có thể xuất hiện trong `<pluginManagement>`, `<plugins>` hoặc phần khác, và không phải mọi lần xuất hiện đều có cùng ý nghĩa.

## 5. Truy xem profile đã thay giá trị thế nào

Trong `app/pom.xml` có profile `local` đặt `demo.label=from-local-profile`. Ta so sánh hai trường hợp.

### 5.1. Khi không bật profile

Trong thư mục `config-trace/app`:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-base.xml
mvn -q org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=demo.label -DforceStdout
~~~

Trong điều kiện ví dụ và không có settings/profile khác thay đổi giá trị, lệnh `help:evaluate` dự kiến in:

~~~text
from-parent
~~~

Giá trị được kế thừa từ `config-trace/pom.xml`. Một đoạn XML đặc trưng trong effective POM:

~~~xml
<properties>
    <demo.label>from-parent</demo.label>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Trên thực tế file effective POM có thêm nhiều property/element và comment; đoạn trên chỉ trích các trường cần tìm, **không phải toàn bộ kết quả**.

### 5.2. Khi bật profile local

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Plocal -Dverbose=true -Doutput=effective-local.xml
mvn -q org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Plocal -Dexpression=demo.label -DforceStdout
~~~

Giá trị của `demo.label` trong mô hình sau khi kích hoạt profile `local`:

~~~text
from-local-profile
~~~

So `effective-base.xml` với `effective-local.xml` bằng diff viewer; tìm `demo.label` và chú thích đầu vào cạnh thuộc tính. Sự khác biệt cho thấy profile đã áp dụng vào mô hình; nếu không thấy, hãy kiểm tra profile có thật trong dự án đang chạy hay không và có profile khác cùng sửa thuộc tính không.

### 5.3. Lệnh kiểm tra profile đang hoạt động

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles -Plocal
~~~

`help:active-profiles` cung cấp danh sách profile đang hoạt động cho build, thường kèm nguồn profile. Nó hỗ trợ điều tra các profile từ POM hoặc settings mà bạn không thấy ngay trong tệp POM đang mở.

**Không đánh đồng:** khai báo `<profile>` trong POM **không có nghĩa nó đang hoạt động**. Effective POM phản ánh **tác động của profile đã được kích hoạt**, còn `help:all-profiles` giúp tìm profile có thể sử dụng.

## 6. Quy trình truy nguồn một giá trị cấu hình bất kỳ

Khi gặp một cấu hình “không biết đến từ đâu”, làm theo sáu bước sau.

### Bước 1: tái hiện chính xác ngữ cảnh build

Ghi nhận:

- Đang ở **module** nào, `pom.xml` nào? Nếu cần, chỉ rõ `-f đường/dẫn/pom.xml`.
- Maven/JDK nào? `mvn -version` hoặc `./mvnw -version`.
- Có `-P...`, `-D...`, `.mvn/maven.config` hoặc biến môi trường nào liên quan?
- CI/IDE dùng Maven Runner riêng hay dùng shell/Wrapper?
- Chế độ build là `compile`, `test`, `package` hay goal plugin trực tiếp nào?

Không lấy effective POM của **parent tại thư mục gốc** để kết luận về một module cụ thể khi hai POM có cấu hình khác nhau.

### Bước 2: xuất effective POM cùng điều kiện

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
~~~

Nếu build thực tế có `-Pci`, thêm `-Pci` vào lệnh điều tra. Nếu build thực tế có property kích hoạt profile, thêm property tương ứng. Hãy đảm bảo profile, JDK, Maven, POM và user settings tương đồng với môi trường lỗi.

### Bước 3: tìm đúng XPath/ngữ cảnh XML

Một số vị trí thường gặp:

| Cần truy | Nơi tìm trong effective POM |
| --- | --- |
| Java release | `/project/properties/maven.compiler.release` và phần compiler plugin |
| Phiên bản plugin | `/project/build/plugins/plugin` hoặc `/project/build/pluginManagement/plugins/plugin` |
| Phiên bản dependency trực tiếp | `/project/dependencies/dependency` |
| Phiên bản do dependencyManagement quản lý | `/project/dependencyManagement/dependencies/dependency` |
| Source/resource path | `/project/build/sourceDirectory`, `resources` hoặc `testResources` |
| Version/project coordinates | `/project/groupId`, `artifactId`, `version` |
| Build profiles đã áp dụng | Quan sát kết quả ghép và dùng `help:active-profiles` bổ sung |

Các đường dẫn trên mang tính minh họa theo cấu trúc XML; Maven POM có namespace XML nên XPath trong công cụ thực tế cần xử lý namespace đúng. Tìm bằng text thường đủ cho một vài thuộc tính.

### Bước 4: lần theo chú thích nguồn

Bật `-Dverbose=true` rồi xem comment ở gần phần tử. Từ đó mở parent POM/module POM tương ứng để tìm định nghĩa gốc. Nếu comment gợi đến POM của dependency/parent nằm trong Maven local repository, hãy kiểm tra tọa độ parent và version, không giả định repository tự dùng bản mới nhất.

Cẩn thận nếu thấy nhiều giá trị cùng tên: `<version>` của plugin **khác** `<version>` của dependency; `<source>` trong Compiler Plugin **khác** nguồn file Java. Phải xác định **đường dẫn XML đầy đủ** trước khi ra quyết định.

### Bước 5: kiểm tra bằng công cụ phù hợp

- `help:active-profiles`: profile nào thực sự hoạt động?
- `help:evaluate`: giá trị expression cụ thể là gì ở ngữ cảnh Maven này?
- `help:effective-settings`: settings Maven cuối cùng sau khi ghép user/global settings (có thể chứa thông tin nhạy cảm).
- `dependency:tree`: dependency nào thực sự được phân giải, dependency nào bị chọn qua mediation?
- `help:describe`: mục tiêu, tham số và default phase của một plugin goal.
- Log bình thường hoặc `-X` (chỉ khi cần, tránh ghi lộ credential): plugin version/goal/execution và tham số được dùng thực tế.

### Bước 6: sửa ở cấp phù hợp và so sánh lại

Nếu plugin version bị kế thừa từ parent, cân nhắc sửa parent chung khi đó là chính sách toàn hệ thống, hoặc ghi đè có chủ đích ở module cần khác. Nếu version dependency được quản lý trong BOM, sửa `dependencyManagement` hoặc nâng BOM, thay vì chỉnh từng dependency một cách thiếu hệ thống. Nếu profile không mong muốn được bật, sửa điều kiện kích hoạt hoặc cách gọi CLI/CI.

Sau thay đổi, xuất lại effective POM với **cùng** tham số, xem diff ở phần liên quan, rồi chạy build/test cần thiết để chứng minh vấn đề được giải quyết. **Effective POM là bằng chứng của cấu hình model; build/test là bằng chứng của hành vi thực tế.**

## 7. Các tình huống chẩn đoán phổ biến

### 7.1. Compiler Plugin dùng phiên bản không khai báo trong module

**Triệu chứng:** log có `maven-compiler-plugin:x.y.z:compile` dù module POM không có `<version>`.

**Điều tra:**

1. Tìm `maven-compiler-plugin` trong effective POM.
2. So `build/plugins` với `build/pluginManagement`; chú ý phiên bản trong parent.
3. Đọc comment `verbose` để tìm file nguồn.
4. Xác định packaging `jar` có default binding compiler hay module dùng `<executions>` riêng.
5. Đối chiếu phiên bản hiển thị trong log `compile`, vì effective POM chưa phải chứng cứ goal đã chạy.

**Kết luận hợp lý:** một plugin có thể được **cấu hình version** ở `pluginManagement` nhưng chỉ **được gọi** bởi binding mặc định hoặc execution thích hợp. `pluginManagement` tự nó không có nghĩa Maven sẽ chạy một goal mới.

### 7.2. Java release bị đổi dù POM con không khai báo

**Triệu chứng:** JDK 21 đã cài nhưng dự án dùng Java release 17 hoặc lỗi `release version 21 not supported`.

**Điều tra:**

~~~bash
java -version
javac -version
mvn -version
mvn -q org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=maven.compiler.release -DforceStdout
~~~

Sau đó xem `maven.compiler.release` và cấu hình Compiler Plugin trong effective POM verbose.

**Phân biệt:** `maven.compiler.release=17` chỉ mức Java đích của compiler; nó **không quyết định JDK chạy Maven**. `mvn -version` mới cho thấy Java đang khởi chạy Maven. Compiler có thể dùng JDK khác qua Toolchains. Nếu còn sự khác biệt, xem cấu hình thực sự của goal compiler và Maven Toolchains thay vì suy từ riêng một giá trị XML.

### 7.3. Dependency không có version nhưng build vẫn chọn được

Một dependency trong `<dependencies>` có thể bỏ `<version>` vì parent hoặc BOM đã quản lý nó bằng `<dependencyManagement>`.

Đọc effective POM, tìm chính dependency đó trong `<dependencyManagement>` và `<dependencies>`; kiểm tra giá trị `groupId`, `artifactId`, `type` và `classifier` khi cần. Nếu BOM được import, cần truy tọa độ/version BOM và nội dung BOM tương ứng. **Không phải mọi nguồn version đã được quản lý sẽ có một chú thích đơn giản trỏ duy nhất về POM hiện tại.**

Quan trọng hơn, effective POM **không phải dependency graph đã giải quyết**; nó không tự hiển thị đầy đủ các dependency transitively selected hay cơ chế xung đột. Dùng:

~~~bash
mvn -B -ntp dependency:tree
~~~

khi cần biết phiên bản cuối cùng Maven thực sự chọn cho dependency graph. Với dự án cần tính tái lập cao, cân nhắc cố định phiên bản Maven Dependency Plugin trong quy trình CI.

### 7.4. Profile local và CI cho cấu hình khác nhau

**Triệu chứng:** máy cá nhân dùng `demo.label=from-local-profile`, CI dùng `from-parent`.

**Điều tra:** so profile active bằng `help:active-profiles` và compare effective POM của hai môi trường. Tìm `-P` trong lệnh CI, `.mvn/maven.config` và điều kiện kích hoạt bởi property, JDK, OS hoặc file.

Đừng sửa `pom.xml` chung chỉ để ép giá trị từ môi trường local. Trước tiên xác định nguyên nhân profile không được kích hoạt hoặc bị profile khác ghi đè.

### 7.5. Version plugin khác giữa hai máy

Một team dùng lệnh `mvn package` với Maven core khác bản, parent khác version hoặc plugin không được pin rõ ràng thì phiên bản plugin mặc định/cơ chế phân giải có thể thay đổi. Hai effective POM **cùng nội dung không đủ chứng minh** hai môi trường dùng cùng runtime; hãy đối chiếu `mvn -version`, Maven Wrapper, parent/BOM và log.

Để dễ tái lập: dùng Wrapper, quản lý plugin version quan trọng qua `pluginManagement` hoặc plugin POM rõ ràng, không phụ thuộc vào phiên bản plugin ngầm định khi cần kiểm soát ổn định.

### 7.6. Repository hoặc mirror bất ngờ

`help:effective-pom` có thể cho thấy `<repositories>` hoặc `<pluginRepositories>` trong model, nhưng **mirror, proxy, server credentials và settings profile** có thể được điều khiển bởi `settings.xml`, không nằm hoàn toàn trong effective POM.

Khi cần, dùng:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-settings -Doutput=effective-settings.xml
~~~

**Bảo vệ thông tin nhạy cảm:** effective settings có thể phản ánh server/proxy/credentials hoặc thông tin môi trường nội bộ. Chỉ lưu ở chỗ an toàn và không commit, in ra ticket công khai hay tải lên dịch vụ ngoài. Với `effective-pom` cũng nên kiểm tra dữ liệu trước khi chia sẻ.

### 7.7. Một giá trị ở `-D` dường như không khớp property trong XML

CLI user properties có thể ảnh hưởng cách Maven/plugin đánh giá biểu thức tại runtime mà phần `<properties>` trong effective POM không thể hiện đầy đủ nguồn hoặc thứ tự ưu tiên theo cách bạn mong đợi.

Hãy chạy `help:evaluate` với **cùng** `-D...`, `-P...` và settings như lệnh build; sau đó xem plugin configuration và log thực thi. Đừng kết luận `-D` vô hiệu chỉ vì thấy một property ở parent POM chưa đổi trên màn hình.

## 8. Trường hợp nhiều module: đặt đúng câu hỏi trước khi mở XML

Giả sử reactor:

~~~text
workspace/
├── pom.xml               (parent và aggregator, packaging=pom)
├── api/pom.xml
├── service/pom.xml
└── cli/pom.xml
~~~

Bạn muốn biết vì sao `service` dùng Compiler Plugin version khác `api`. Cần so **effective POM của từng module**:

~~~bash
mvn -B -ntp -f service/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=service-effective.xml
mvn -B -ntp -f api/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=api-effective.xml
~~~

Đây là ví dụ giả định cấu trúc folder thực sự tồn tại. Xem cấu hình parent nào đang được mỗi module kế thừa, module nào ghi đè `plugins` và profile nào active. Nếu chạy từ POM aggregator, Help Plugin có thể xuất nhiều effective POM theo build session, khiến người mới tưởng nội dung của module này là module kia.

Trong dự án đa module, hãy kiểm tra **module header** và artifactId khi nhìn output. Một số goal Help Plugin có hành vi aggregator, vì vậy phạm vi dự án được chọn bằng reactor và `-f` có thể ảnh hưởng số model được xuất. Cách đáng tin là xác định POM hiện tại rồi tìm đúng block của module quan tâm.

## 9. Giới hạn của effective POM: những gì nó không chứng minh

| Câu hỏi | Effective POM có trả lời trọn vẹn? | Cần bổ sung |
| --- | --- | --- |
| Property được khai báo trong model cuối thế nào? | **Thường có** | `help:evaluate` nếu cần kết quả expression |
| Plugin/dependency version cấu hình là bao nhiêu? | **Có thể thấy** phiên bản khai báo/được quản lý | Log plugin, `dependency:tree` nếu hỏi phiên bản resolved |
| Một thuộc tính xuất phát từ parent hay POM con? | **Có đầu mối** nhờ `-Dverbose=true` | Đọc parent chain/profile thực tế |
| Profile nào active? | Chỉ thấy tác động vào model | `help:active-profiles` |
| Artifact nào được tải và conflict dependency xử lý sao? | **Không đầy đủ** | `dependency:tree` và log resolver |
| Plugin goal nào thực sự chạy vào phase nào? | Cấu hình model giúp suy ra một phần | Binding packaging, log build, `help:describe` |
| Runtime Java nào chạy Maven? | **Không** | `mvn -version` |
| JDK nào thực sự biên dịch (Toolchains)? | **Không chắc** | Log Compiler Plugin/Toolchains |
| Mirror, proxy, credential nằm đâu? | **Không đầy đủ** | `help:effective-settings` và cấu hình hệ thống (xử lý an toàn) |
| CI dùng command line/profile nào? | **Không tự biết** ngoài ngữ cảnh lệnh đã gọi | Workflow CI, log job, `.mvn/maven.config` |
| Build chắc chắn thành công? | **Không** | Chạy `compile`, `test`, `verify` và xem kết quả |

Effective POM **không phải một POM để copy thay thế POM gốc**. Nó chứa các giá trị được kế thừa, mặc định và kết quả phối hợp model nhằm mục đích **quan sát**. Chép nguyên tệp này vào `pom.xml` của dự án có thể gây dư thừa, cố định sai môi trường hoặc mất cấu trúc quản lý của parent/profile. Khi cần sửa, hãy sửa đúng nguồn cấu hình.

## 10. Những lỗi hay gặp khi dùng help:effective-pom

### `No plugin found for prefix 'help'`

**Nguyên nhân:** Maven không phân giải được prefix plugin, plugin repository chưa truy cập được hoặc cấu hình resolver lỗi.

**Khắc phục:** thử gọi plugin bằng đầy đủ groupId/artifactId/version/goal như trong bài. Nếu vẫn lỗi, kiểm tra mạng, mirror, settings và cache plugin. Đừng chuyển sang một repository không tin cậy.

### `The goal you specified requires a project to execute`

**Nguyên nhân:** đang chạy tại thư mục không có `pom.xml` hoặc `-f` trỏ sai.

**Khắc phục:** vào đúng module/project hoặc dùng `-f đường/dẫn/pom.xml`; `help:effective-pom` yêu cầu Maven project.

### `Non-resolvable parent POM`

**Nguyên nhân:** Maven không truy cập được parent đúng tọa độ/version, `relativePath` sai hoặc repository/mirror không có artifact.

**Khắc phục:** kiểm tra `<parent>` trong POM con, vị trí parent trên đĩa, local/remote repository và quyền truy cập. Không thay version parent tùy ý vì sẽ làm mất cấu hình đã được team xác nhận.

### Không thấy chú thích nguồn

**Nguyên nhân:** chạy không có `-Dverbose=true` hoặc Help Plugin quá cũ (trước 3.2.0).

**Khắc phục:** gọi full plugin `3.5.2` và bật `-Dverbose=true`; nếu XML xuất ra không như dự kiến, kiểm tra file output mới được tạo và phiên bản plugin trong log.

### File effective POM được tạo nhưng không thấy giá trị vừa thay đổi

**Nguyên nhân có thể:** đang xem output cũ, POM của module khác, profile không active, parent không phải bản đang được phân giải, hoặc CLI/environment khác với lệnh build.

**Khắc phục:** kiểm tra thời gian sửa file output, `-f`, `-P`, `-D`, `help:active-profiles`, `mvn -version` và comment nguồn. Tạo lại file dưới tên khác để so sánh nếu cần.

### Trong file có nhiều chỗ ghi version và không biết chỗ nào hiệu lực

**Nguyên nhân:** version của project, parent, dependency, plugin, report plugin và mục quản lý là các khái niệm riêng; cùng tên `<version>` nhưng ở các đường dẫn XML khác nhau.

**Khắc phục:** đọc cả chuỗi thẻ cha và phân biệt `<dependencies>` với `<dependencyManagement>`, `<plugins>` với `<pluginManagement>`. Với version được chọn từ transitive dependencies, dùng `dependency:tree`.

### `help:evaluate` không in đúng giá trị cần tìm

**Nguyên nhân:** tên expression sai, giá trị không có trong model, shell xử lý tham số, project/profile không đúng hoặc property chỉ có ý nghĩa trong ngữ cảnh plugin runtime.

**Khắc phục:** dùng tên biểu thức chính xác, ví dụ `maven.compiler.release`, `project.version`, `project.build.directory`, kết hợp `-DforceStdout`, và so kết quả với effective POM. Đừng diễn giải một giá trị trống là bằng chứng không có cấu hình trong mọi plugin.

### Log Maven in ra giá trị khác với effective POM

**Nguyên nhân có thể:** plugin ghi đè config theo execution, user property, toolchain, runtime JVM, hoặc effective POM được tạo với ngữ cảnh khác.

**Khắc phục:** đối chiếu cùng lệnh Maven/profile/JDK, nhìn `<executions>` và dùng thông tin từ log/plugin documentation. Bật `-X` khi thực sự cần rồi **lọc dữ liệu nhạy cảm** trước khi chia sẻ.

## 11. Thực hành có đáp án

**Bài 1 — xác định nguồn compiler release.** Dùng hai file POM ở mục 4. Trong `app/pom.xml` không có `maven.compiler.release`. Chạy `help:effective-pom -Dverbose=true`. Giá trị cuối mong đợi là gì và đến từ đâu?

**Đáp án:** `17`, được kế thừa từ `config-trace/pom.xml` của parent; xác minh bằng comment nguồn và thuộc tính trong effective POM.

**Bài 2 — truy phiên bản plugin.** Tại sao module không khai báo `<version>` của Compiler Plugin nhưng vẫn biên dịch được?

**Đáp án:** parent `pluginManagement` đặt `maven-compiler-plugin` `3.14.0`; module sử dụng plugin này và packaging `jar` có các binding compile thông thường. Xem phần `pluginManagement` và `plugins` trong effective POM; so với log compile.

**Bài 3 — profile tác động thế nào?** So sánh output khi chạy không có `-Plocal` và có `-Plocal`.

**Đáp án:** property `demo.label` trong điều kiện bài tập thay từ `from-parent` sang `from-local-profile`. Dùng `help:active-profiles -Plocal` để xác nhận profile, và `help:evaluate` để đọc đúng expression.

**Bài 4 — phân biệt model với dependency resolution.** Effective POM hiện dependency version `2.1`, nhưng người học cần biết vì sao một dependency transitive chọn `2.3`. Chỉ đọc effective POM có đủ không?

**Đáp án:** không. Dùng `mvn dependency:tree` để xem graph và đường đi/version được chọn. Sau đó truy parent/BOM và `dependencyManagement` nếu có.

**Bài 5 — sửa đúng nơi.** Compile plugin version do parent quản lý. Một module cần thử plugin mới, còn các module khác phải ổn định. Bạn sửa đâu?

**Đáp án:** có thể khai báo version/configuration có chủ đích ở module nếu chỉ module đó cần khác, kiểm tra effective POM và chạy build/test; thay parent chung chỉ khi muốn chính sách mới cho toàn bộ các module thừa hưởng.

**Bài 6 — CI dùng cấu hình khác.** Máy cá nhân hiện `demo.label=from-local-profile` nhưng CI hiện `from-parent`. Liệt kê ba thứ nên kiểm tra trước khi sửa POM.

**Đáp án gợi ý:** (1) profile active và `-P`, (2) CLI `-D`, Maven config và settings profile, (3) POM/module và Maven version/Wrapper/JDK thực tế.

## 12. Checklist khi cần truy nguồn cấu hình Maven

- [ ] Xác nhận đúng module, `pom.xml`, Maven version và JDK.
- [ ] Tái hiện chính xác profile `-P`, property `-D` và settings liên quan.
- [ ] Xuất effective POM bằng một phiên bản Maven Help Plugin xác định.
- [ ] Bật `-Dverbose=true` để xem comment về vị trí phần tử nguồn.
- [ ] Phân biệt `dependencies` với `dependencyManagement` và `plugins` với `pluginManagement`.
- [ ] Kiểm tra các parent POM và mặc định của Super POM nếu POM con không khai báo.
- [ ] Xác minh profile đang hoạt động bằng `help:active-profiles` khi thấy khác biệt môi trường.
- [ ] Dùng `help:evaluate` cho expression đơn lẻ; dùng `dependency:tree` cho graph thực sự được phân giải.
- [ ] Phân biệt effective POM với tham số plugin runtime và Maven settings.
- [ ] Không commit hoặc chia sẻ tệp chẩn đoán có chứa thông tin nội bộ/bí mật.
- [ ] Sửa đúng nguồn cấu hình rồi chạy lại effective POM và build/test.
- [ ] Ghi rõ bằng chứng: giá trị cũ, giá trị mới, nguồn và cách đã kiểm chứng.

## 13. Tài liệu chính thức

1. [Maven Help Plugin — help:effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): mô tả goal và tham số `output`, `verbose` (được thêm từ 3.2.0).
2. [Maven Help Plugin — Usage](https://maven.apache.org/plugins/maven-help-plugin/usage.html): mô hình kết quả của `effective-pom`, `effective-settings` và `active-profiles`.
3. [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): cấu trúc POM, Super POM, inheritance, aggregation và interpolation.
4. [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html): cách kích hoạt, ảnh hưởng và giới hạn kế thừa profile.
5. [Apache Maven — POM Reference](https://maven.apache.org/pom.html): cấu trúc `dependencies`, `dependencyManagement`, `plugins` và `pluginManagement`.
6. [Maven Help Plugin — help:active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html): liệt kê profile active.
7. [Maven Help Plugin — help:evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html): đánh giá expression trong project.
