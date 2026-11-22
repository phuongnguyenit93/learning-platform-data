# Đọc Effective POM để xác minh cấu hình sau kế thừa trong Maven

## 1. Vì sao cần xem Effective POM?

Trong dự án Maven, file `pom.xml` mà lập trình viên mở ra **không nhất thiết chứa toàn bộ cấu hình Maven thực sự sử dụng**. Một module có thể chỉ khai báo vài dòng, trong khi giá trị cuối cùng đến từ nhiều lớp:

- **Super POM**: cấu hình mặc định mà Maven cung cấp.
- **Parent POM**: cấu hình kế thừa từ một hoặc nhiều POM cha.
- **POM của module hiện tại**: khai báo riêng, có thể ghi đè hoặc hợp nhất với giá trị kế thừa.
- **Profile đang kích hoạt**: bổ sung hoặc thay đổi cấu hình tùy môi trường, điều kiện và tham số chạy.
- **Nội suy thuộc tính (interpolation)**: giải quyết các biểu thức như `${project.version}` hoặc `${maven.compiler.release}` ở những vị trí Maven hỗ trợ.

**Effective POM** là mô hình POM kết quả mà Maven tính toán cho một project trong ngữ cảnh build cụ thể. Đọc Effective POM giúp trả lời: “Sau khi Maven áp dụng kế thừa và các cấu hình liên quan, giá trị cuối cùng ở đâu, là gì và vì sao nó xuất hiện?”.

Tình huống thực tế:

- POM con không khai báo `<version>` nhưng artifact vẫn có phiên bản.
- Compiler Plugin sử dụng một phiên bản mà POM con không ghi trực tiếp.
- Một dependency không có `<version>` ở POM con nhưng Maven vẫn giải quyết được phiên bản.
- Một thuộc tính từ parent bị module con ghi đè.
- CI bật một profile khác máy cá nhân nên cấu hình build khác nhau.
- POM con rất ngắn, nhưng Maven vẫn có các plugin, repository và đường dẫn mặc định.

Lệnh dùng để xem là **`help:effective-pom`** thuộc **Maven Help Plugin**.

## 2. Lệnh cơ bản để xem hoặc lưu Effective POM

Đứng tại thư mục có `pom.xml` của project cần kiểm tra:

```bash
mvn help:effective-pom
```

Maven Help Plugin tạo bản biểu diễn XML của effective POM. Khi chạy không có `output`, Maven hiển thị nội dung qua console cùng những thông tin thực thi cần thiết.

Để lưu thành file dễ tìm kiếm, dùng:

```bash
mvn help:effective-pom -Doutput=effective-pom.xml
```

Tham số `-Doutput` của goal này chỉ định **tệp kết quả**; plugin ghi file dưới dạng UTF-8. Tệp có thể rất dài vì chứa các giá trị mặc định và kế thừa; không nên sao chép toàn bộ vào `pom.xml` nguồn.

Có thể khóa phiên bản Maven Help Plugin để mọi người dùng cùng hành vi và có tham số nguồn gốc `verbose`:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
```

Trong đó:

- `-B` là batch mode, phù hợp script không tương tác.
- `-ntp` giảm hiển thị tiến độ tải artifact.
- `org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom` là tọa độ đầy đủ của plugin/goal, tránh phụ thuộc phiên bản plugin được suy ra từ cấu hình hoặc plugin resolution.
- `-Dverbose=true` yêu cầu Help Plugin thêm **XML comment cho biết nguồn gốc** của phần tử cấu hình; tính năng này có từ Maven Help Plugin 3.2.0.
- `-Doutput=effective-pom.xml` ghi kết quả vào file được chỉ định.

Nếu dự án đã có Maven Wrapper, thay `mvn` bằng `./mvnw` (Linux/macOS) hoặc `.\mvnw.cmd` (Windows PowerShell) để dùng phiên bản Maven mà dự án đã chốt.

**Điều kiện chạy:** cần Maven hoặc Maven Wrapper hoạt động được, POM hợp lệ, parent được phân giải và plugin Help có sẵn trong cache hoặc có thể tải từ repository. Lỗi tải parent/plugin là lỗi phải xử lý trước khi kỳ vọng có effective POM.

## 3. Effective POM là kết quả của những lớp cấu hình nào?

Sơ đồ khái niệm:

```text
Super POM (mặc định của Maven)
              |
              v
Parent POM (có thể nhiều cấp)
              |
              v
POM của module con + các profile có hiệu lực
              |
              v
Maven xử lý kế thừa, hợp nhất, giá trị mặc định và nội suy
              |
              v
Effective POM của module trong ngữ cảnh chạy hiện tại
```

Đây là **sơ đồ khái niệm**, không phải lời khẳng định Maven thực thi từng phép biến đổi theo đúng một đường tuyến tính như hình. Điểm cần nhớ: kết quả là **một mô hình cấu hình đã được tính toán**, không phải một file cha hoặc con đơn lẻ.

### 3.1. Super POM

Super POM cung cấp một số mặc định cho project Maven. Chẳng hạn, dự án `jar` sử dụng các quy ước về source, test và output:

```text
src/main/java
src/main/resources
src/test/java
src/test/resources
target/classes
target/test-classes
```

Những đường dẫn này và phần cấu hình có liên quan có thể được phản ánh trong effective POM, dù POM của module không tự khai báo chúng.

### 3.2. Parent POM

POM con khai báo quan hệ kế thừa bằng `<parent>`:

```xml
<parent>
    <groupId>com.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../parent/pom.xml</relativePath>
</parent>
```

Đoạn XML trên là **một phần** của `<project>`, không phải file POM độc lập. Nó chỉ cách Maven tìm POM cha qua tọa độ và đường dẫn tương đối. Trong POM con, `groupId` và `version` có thể được kế thừa từ cha, còn `artifactId` xác định module con.

### 3.3. Giá trị do module con khai báo

Module con có thể ghi đè một số thuộc tính hoặc hợp nhất các danh sách, plugin và cấu hình theo quy tắc của Maven. Không phải mọi phần tử được xử lý theo nguyên tắc “con thay toàn bộ cha”: có phần tử vô hướng ghi đè, có phần tử danh sách hợp nhất theo khóa nhận diện và quy tắc riêng. Vì vậy cần **đọc kết quả thực tế** thay vì tự đoán từ hai file.

### 3.4. Profile

Profile có thể kích hoạt qua `-P<id>`, điều kiện trong POM hoặc cấu hình liên quan. Khi profile có hiệu lực, các thay đổi của nó được tính vào effective POM. **So sánh effective POM khi có/không có profile** là cách xác minh một thay đổi phụ thuộc môi trường.

## 4. Ví dụ thực hành: project cha–con có thể chạy

Tạo cấu trúc dự án sau. Parent nằm ở thư mục `parent`, module ứng dụng ở thư mục `app`; quan hệ kế thừa dùng `relativePath` tường minh. **Không cần parent liệt kê `<modules>` để ví dụ kế thừa này hoạt động**.

```text
maven-effective-demo/
├── parent/
│   └── pom.xml
└── app/
    ├── pom.xml
    └── src/
        └── main/
            └── java/
                └── com/
                    └── example/
                        └── training/
                            └── App.java
```

Ví dụ cần **JDK 17+**, Apache Maven 3 phù hợp và kết nối repository khi chưa có plugin/dependency trong cache.

### 4.1. `parent/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.training</groupId>
    <artifactId>training-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <demo.label>parent-value</demo.label>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
                <scope>test</scope>
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
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Ý nghĩa các quyết định:

- `<packaging>pom</packaging>`: parent đóng vai trò POM cấu hình và không yêu cầu đóng gói thành JAR.
- `project.build.sourceEncoding` và `maven.compiler.release`: thuộc tính dùng chung, cho phép con sử dụng UTF-8 và cấu hình compiler cho Java 17.
- `demo.label`: giá trị có chủ đích để kiểm tra module con có ghi đè được không.
- `dependencyManagement`: quản lý phiên bản và một số thông tin dependency cho những module **thực sự khai báo sử dụng** dependency đó.
- `pluginManagement`: quản lý phiên bản/cấu hình plugin. Nó **không tự thêm một execution mới** vào mọi module; module hoặc lifecycle phải sử dụng plugin phù hợp.

### 4.2. `app/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example.training</groupId>
        <artifactId>training-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../parent/pom.xml</relativePath>
    </parent>

    <artifactId>training-app</artifactId>
    <packaging>jar</packaging>

    <properties>
        <demo.label>child-value</demo.label>
    </properties>

    <dependencies>
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
                <artifactId>maven-compiler-plugin</artifactId>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>dev</id>
            <properties>
                <demo.mode>development</demo.mode>
            </properties>
        </profile>
    </profiles>
</project>
```

Các điểm để dự đoán **trước** khi chạy Help Plugin:

1. Module con **không khai báo** `groupId` và `version` trực tiếp nhưng kế thừa `com.example.training` và `1.0.0` từ parent.
2. `artifactId` của ứng dụng là `training-app`, không phải `training-parent`.
3. `packaging` của ứng dụng là `jar` theo khai báo riêng. Đừng suy ra rằng nó phải là `pom` chỉ vì parent có `packaging=pom`.
4. `maven.compiler.release` trong module con vẫn là `17` dù file con không khai báo.
5. `demo.label` có giá trị cuối cùng `child-value` vì module con ghi đè parent.
6. `maven-compiler-plugin` được module con khai báo không có version; cấu hình version `3.14.1` được quản lý trong `pluginManagement` của parent.
7. Dependency `junit-jupiter` được module con **khai báo sử dụng** nhưng không ghi version; `dependencyManagement` từ parent cung cấp `5.11.4`. `scope=test` chỉ cho phép dùng trong các ngữ cảnh test phù hợp.
8. Thuộc tính `demo.mode` từ profile `dev` chỉ được đưa vào mô hình có hiệu lực khi profile đó được kích hoạt; hiện tại profile chưa được đặt `activeByDefault`.

### 4.3. `app/src/main/java/com/example/training/App.java`

```java
package com.example.training;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Effective POM demo");
    }
}
```

Lớp `public` và tên file `App.java` phù hợp Java 17. Chương trình này cố tình không đọc thuộc tính `demo.label`: **Maven property không tự trở thành Java system property**. Những giá trị trong `pom.xml` phục vụ cấu hình build; muốn đưa chúng vào runtime cần cơ chế cụ thể như filter resources, tham số JVM hoặc cấu hình plugin thích hợp.

Để thử build sau khi kiểm tra cấu hình, từ thư mục `app` chạy:

```bash
mvn -B -ntp clean package
java -cp target/classes com.example.training.App
```

**Stdout chính xác của lệnh `java` thứ hai**, nếu compile thành công:

```text
Effective POM demo
```

Log của `mvn clean package` có thêm các dòng INFO, thông báo tải artifact và kết quả build; không đồng nhất với stdout Java ở trên. Nếu module không có test, có thể không có test nào được thực thi dù đã khai báo JUnit.

## 5. Sinh Effective POM của đúng module

Từ gốc của ví dụ, đi vào thư mục ứng dụng:

```bash
cd app
mvn -version
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
```

Thao tác này hướng Help Plugin tới `app/pom.xml`; parent được tìm tại `../parent/pom.xml` nhờ `relativePath` đã khai báo. File `effective-pom.xml` là **kết quả chẩn đoán** ở thư mục làm việc của project, không phải tệp build nguồn phải duy trì bằng tay.

Nếu đang ở thư mục khác hoặc trong hệ thống CI, có thể chọn POM bằng `-f`, ví dụ:

```bash
mvn -f app/pom.xml help:effective-pom -Doutput=app-effective-pom.xml
```

Với `-f`, hãy kiểm tra đường dẫn file output thực tế, vì đường dẫn tương đối còn phụ thuộc cách plugin xử lý base directory và thư mục chạy. Để tránh nhầm, cách nhất quán trong bài thực hành là **`cd app` rồi chạy lệnh**.

Maven Help Plugin cũng có tên goal ngắn:

```bash
mvn help:effective-pom -Doutput=effective-pom.xml
```

Nếu Maven không phân giải được tiền tố `help` hoặc cần chắc chắn phiên bản hỗ trợ `verbose`, dùng tọa độ plugin đầy đủ như lệnh đầu mục.

**Chú ý** với project đa module: `help:effective-pom` là một goal loại aggregator và có thể xử lý nhiều project trong phiên build. Khi cần kiểm tra một module cụ thể, chạy trực tiếp từ module đó hoặc chỉ rõ đúng POM/phạm vi reactor, sau đó kiểm tra tên artifact trong output để tránh diễn giải nhầm POM của module khác.

## 6. Đọc kết quả theo một checklist có mục tiêu

Tệp effective POM dài vì có thể chứa nhiều mục mặc định. **Không cần đọc từng dòng từ đầu đến cuối.** Hãy tìm các vùng cần xác minh và so sánh với parent/child POM.

| Vấn đề cần kiểm tra | Vị trí/từ khóa trong effective POM | Kết quả kỳ vọng của ví dụ |
| --- | --- | --- |
| Tọa độ module | `project/groupId`, `project/artifactId`, `project/version` | `com.example.training:training-app:1.0.0` |
| Loại đóng gói | `project/packaging` | `jar` |
| Java release | `project/properties/maven.compiler.release` | `17` |
| Encoding | `project/properties/project.build.sourceEncoding` | `UTF-8` |
| Giá trị ghi đè | `project/properties/demo.label` | `child-value` |
| Phiên bản JUnit | `project/dependencies/dependency` với `junit-jupiter` | `5.11.4` |
| Compiler plugin | `project/build/plugins/plugin` với `maven-compiler-plugin` | `3.14.1` |
| Quản lý compiler plugin | `project/build/pluginManagement/plugins/plugin` | `maven-compiler-plugin` phiên bản `3.14.1` |
| Profile `dev` đang bật? | `project/properties/demo.mode` | Có `development` khi bật `-Pdev` |

Cần xác định **đúng nhánh XML**. Tên `version` xuất hiện rất nhiều lần: một lần cho artifact project, nhiều lần ở dependency, plugin, parent. Tìm chuỗi `<version>3.14.1</version>` đơn thuần chưa đủ; phải kiểm tra nó nằm trong plugin có `artifactId=maven-compiler-plugin`.

**Một đoạn minh họa** về phần kết quả liên quan (không phải toàn bộ effective POM, thứ tự thẻ và chi tiết có thể khác theo Maven/Help Plugin):

```xml
<groupId>com.example.training</groupId>
<artifactId>training-app</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
<properties>
    <demo.label>child-value</demo.label>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Đoạn này **chỉ minh họa các giá trị cần đối chiếu**, không phải file XML độc lập hoặc lời cam kết thứ tự sắp xếp các property trong output thật.

Một phần khác cần đọc là danh sách dependency:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

Đây cũng là **trích đoạn khái niệm** bên trong danh sách `dependencies` của effective POM. Phiên bản `5.11.4` được quản lý ở parent; ở POM con, khai báo sử dụng dependency không ghi trực tiếp phiên bản.

Nếu chỉ thấy một dependency trong `dependencyManagement` mà không có trong `dependencies`, điều đó **không chứng minh dependency được đưa lên classpath**. `dependencyManagement` chủ yếu cung cấp defaults cho các dependency được khai báo và một số cơ chế quản lý khác; phải đọc đúng `dependencies` và khi cần xem cây dependency đã giải quyết.

## 7. Dùng `-Dverbose=true` để truy dấu nguồn cấu hình

Nếu chỉ biết giá trị cuối cùng, đôi khi vẫn chưa đủ. Ví dụ có ba POM cha và một profile, cần xác định **dòng nào đưa compiler release vào build**.

Thực hiện:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-verbose.xml
```

`verbose` là tham số của Help Plugin, được hỗ trợ từ phiên bản **3.2.0**. Khi bật, plugin thêm **comment XML mô tả vị trí nguồn** cho các phần tử trong kết quả. Bình luận có thể giúp lần theo file và dòng cấu hình liên quan; định dạng chi tiết tùy phiên bản plugin.

Quy trình đọc:

1. Tìm đoạn chứa giá trị cần kiểm tra, ví dụ `maven.compiler.release`, `maven-compiler-plugin` hoặc `demo.label`.
2. Xem chú thích nguồn gốc cạnh phần tử đó, xác định nó đến từ POM cha, POM con hoặc cấu hình khác.
3. Mở **file nguồn tương ứng** và kiểm tra khai báo.
4. Nếu là phần tử được hợp nhất từ nhiều nguồn, đọc phần cấu hình liên quan ở các cấp thay vì gán toàn bộ nội dung sau merge cho một dòng duy nhất.
5. Thay đổi file nguồn, sinh lại effective POM, kiểm tra kết quả.

Không sửa comment trong `effective-verbose.xml` để “đổi nguồn gốc”; đó là output của công cụ. Cũng đừng coi comment của plugin là tài liệu chi tiết giải thích toàn bộ thuật toán merge, đặc biệt khi một phần tử đã được kết hợp từ nhiều nguồn.

## 8. So sánh trước và sau khi bật profile

Trong `app/pom.xml` có profile `dev`:

```xml
<profiles>
    <profile>
        <id>dev</id>
        <properties>
            <demo.mode>development</demo.mode>
        </properties>
    </profile>
</profiles>
```

Đoạn này đã có trong POM con hoàn chỉnh ở mục 4.2. Hãy tạo hai bản effective POM bằng **hai lượt chạy**:

```bash
mvn -B -ntp help:effective-pom -Doutput=effective-default.xml
mvn -B -ntp -Pdev help:effective-pom -Doutput=effective-dev.xml
```

Sau đó kiểm tra:

- `effective-default.xml` không có property `demo.mode=development` do profile `dev` cung cấp, **giả định không có cấu hình bên ngoài kích hoạt profile cùng tên**.
- `effective-dev.xml` có property `demo.mode` với giá trị `development` trong phần properties hiệu lực.
- Các phần parent/child không bị profile tác động, như tọa độ project và compiler release, vẫn có thể giữ nguyên.

Để kiểm tra profile đang kích hoạt trong **đúng ngữ cảnh lệnh**, dùng:

```bash
mvn help:active-profiles
mvn -Pdev help:active-profiles
```

Kết quả của `help:active-profiles` giúp xác nhận profile nào thật sự bật; đừng chỉ suy từ việc `<profile>` có mặt trong file. Ngoài `-P`, Maven có thể kích hoạt profile theo điều kiện JDK, OS, property, file hoặc từ `settings.xml`. Vì vậy cùng một commit nhưng hai máy có thể tạo effective POM khác nhau.

**Điều quan trọng:** nội dung được áp dụng từ active profile có thể ảnh hưởng mô hình kế thừa, nhưng bản thân các `<profile>` container từ parent không nên bị hiểu là các profile độc lập luôn được “copy nguyên trạng” để bật thủ công ở con. Khi kiểm tra, cần quan sát **các tác động đã kích hoạt**.

## 9. Dùng Effective POM để kiểm tra dependency và plugin management

Hai cơ chế thường gây ngộ nhận:

### 9.1. `dependencyManagement` quản lý, `dependencies` sử dụng

Trong ví dụ:
- Parent khai báo `org.junit.jupiter:junit-jupiter:5.11.4` ở `dependencyManagement`.
- Child khai báo `org.junit.jupiter:junit-jupiter` ở `dependencies`, không có `version`.
- Effective POM của child cho phép quan sát dependency đã nhận phiên bản `5.11.4` trong mô hình hiệu lực.

Nếu bỏ dependency ở POM con nhưng vẫn giữ parent `dependencyManagement`, Maven **không tự đưa JUnit lên runtime/test classpath chỉ vì parent quản lý nó**. Khi đó effective POM vẫn có thể có mục quản lý tương ứng, nhưng không phải dependency trực tiếp trong `dependencies`.

Để xem dependency tree đã được giải quyết (kể cả dependency bắc cầu), dùng Maven Dependency Plugin:

```bash
mvn dependency:tree
```

`help:effective-pom` dùng để kiểm tra mô hình cấu hình, còn `dependency:tree` dùng để khảo sát dependency graph thực tế. Chúng giải đáp hai câu hỏi khác nhau.

### 9.2. `pluginManagement` quản lý, `plugins`/lifecycle sử dụng

Trong ví dụ:
- Parent quản lý `maven-compiler-plugin:3.14.1`.
- Child khai báo plugin trong `<build><plugins>` mà không ghi version.
- Effective POM hiển thị version plugin đã được xác định từ quản lý kế thừa.

**Không kết luận** rằng mọi plugin trong `pluginManagement` đều được thực thi. Sự thực thi phụ thuộc vào binding mặc định của packaging/lifecycle, các goal được khai báo trong `executions`, lệnh CLI và cấu hình plugin thực tế.

Một plugin có thể có cấu hình **mặc định bên trong chính plugin**, không hiện thành tất cả các giá trị XML riêng trong effective POM. Muốn kiểm tra goal và tham số runtime, đọc tài liệu plugin, dùng `mvn help:describe` hoặc log debug có kiểm soát khi cần. Effective POM rất hữu ích nhưng không thay thế việc quan sát build.

### 9.3. BOM nhập khẩu không giống parent

Một dự án có thể dùng `<dependencyManagement>` với dependency `<type>pom</type>`, `<scope>import</scope>` để nhập BOM, nhằm quản lý nhiều phiên bản dependency. **Import BOM không giống kế thừa `<parent>`**: BOM được nhập vào vùng dependency management, không trở thành parent POM và không tự mang mọi cấu hình build/plugin của BOM vào project. Khi kiểm tra, cần xem đúng vùng `dependencyManagement` và kết quả phiên bản dependency được áp dụng.

## 10. Khi Effective POM khác mong đợi: cách chẩn đoán theo từng bước

Giả sử POM con mong muốn Java 17 nhưng effective POM hiện một giá trị khác.

**Bước 1 — Kiểm tra lệnh và đúng project.**

```bash
mvn -version
mvn help:effective-pom -Doutput=effective-pom.xml
```

Chạy từ module dự định kiểm tra. Trong repository nhiều module, đọc tọa độ `groupId:artifactId:version` trong kết quả; không nhầm với effective POM của parent hay module khác.

**Bước 2 — Tìm thuộc tính và vị trí thật.**

Tìm `maven.compiler.release` trong `properties` và xem `maven-compiler-plugin` trong `build/plugins`, bao gồm `configuration` của plugin nếu có. Nếu plugin khai báo `<release>` trực tiếp, cấu hình đó có thể khác cách đặt property. Đừng chỉ nhìn một chuỗi xuất hiện bất kỳ trong file.

**Bước 3 — Tìm nguồn bằng verbose.**

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-verbose.xml
```

Đọc các comment xuất xứ, so lại parent và child POM, xem phần nào được ghi đè và phần nào được merge.

**Bước 4 — Kiểm tra profile và ngữ cảnh kích hoạt.**

```bash
mvn help:active-profiles
```

Nếu local và CI khác nhau, so sánh lệnh Maven thật (đặc biệt `-P` và các `-D` có liên quan), JDK/OS, cấu hình `settings.xml`/profile và các biến môi trường được phép ảnh hưởng tới POM.

**Bước 5 — Sửa đúng nguồn và đo lại.**

Không chỉnh file effective POM. Sửa khai báo trong parent/child POM, BOM hoặc profile **đang có hiệu lực**, rồi sinh lại output và chạy build/test thích hợp. Nếu lệnh build vẫn khác dự đoán, kiểm tra thêm cấu hình thật của plugin và các giá trị được truyền trên CLI.

## 11. Những lỗi thường gặp và nguyên nhân

| Hiện tượng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `No plugin found for prefix 'help'` | Plugin prefix không được phân giải hoặc không truy cập được plugin repository | Dùng tọa độ đầy đủ `org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom`; kiểm tra mạng/repository |
| `Non-resolvable parent POM` | Sai tọa độ parent, `relativePath`, parent chưa được tải/cài hoặc repository không truy cập được | Đối chiếu `<parent>` và vị trí file, kiểm tra kho Maven |
| Tệp effective POM không xuất hiện | `-Doutput` sai đường dẫn, không có quyền ghi, lệnh đã lỗi hoặc chạy từ sai thư mục | Xem exit code; dùng đường dẫn đơn giản và kiểm tra thư mục thực tế |
| POM con không có `groupId/version` nhưng vẫn build được | Parent cung cấp các trường này | Đọc `project/groupId` và `project/version` trong effective POM |
| Phiên bản compiler plugin khác dự đoán | Có `pluginManagement`, parent POM, version/plugin khác hoặc cấu hình lifecycle | Đối chiếu `build/plugins` và `build/pluginManagement` với `verbose` |
| Có JUnit trong management nhưng test không tìm thấy | Chưa khai báo JUnit thực sự trong `dependencies` hoặc scope không phù hợp | Kiểm tra dependency trực tiếp, dùng `dependency:tree` |
| Profile cấu hình rồi nhưng property không xuất hiện | Profile chưa được kích hoạt hoặc bị điều kiện khác chi phối | Chạy `help:active-profiles`, thử `-Pdev` |
| Property con có giá trị khác parent | Con ghi đè giá trị của cha hoặc profile làm thay đổi | Tìm nguồn và thứ tự cấu hình ở POM liên quan |
| Không tìm thấy giá trị của một tham số plugin | Plugin có default riêng không nhất thiết hiện hết dưới dạng XML | Đọc plugin descriptor/docs và log chạy goal |
| Hai máy có effective POM khác nhau | Maven/JDK khác phiên bản, profile auto-activation, settings hoặc tham số CLI khác | Ghi nhận phiên bản và ngữ cảnh, so output cùng điều kiện |
| Effective POM có cấu hình đúng nhưng build thất bại | POM hiệu lực chưa chứng minh mã/test/repository/permissions hợp lệ | Chạy `validate`/`test`/`verify` và xem lỗi thực tế |
| File effective POM vô tình vào commit | Output chẩn đoán nằm trong source tree, Git phát hiện là file mới | Loại khỏi commit, đưa vào đường dẫn output tạm hoặc thêm ignore hợp lý |

## 12. Những giới hạn cần nhớ khi diễn giải kết quả

1. **Effective POM không phải bản sao nguyên văn của POM cha và con.** Nó là kết quả tính toán và có thể dài hơn nhiều vì chứa mặc định, quản lý và các giá trị đã được xử lý.
2. **Không phải mọi khác biệt trong môi trường đều hiện trong Effective POM.** Settings, repository mirror, chứng chỉ, credentials, JDK thực tế, trạng thái cache và các tham số runtime của plugin có thể cần công cụ khác.
3. **Không phải dependency tree đầy đủ.** Effective POM thể hiện mô hình khai báo/quản lý dependency; việc giải quyết dependency bắc cầu và phạm vi cụ thể cần `dependency:tree`, bản thân hiệu lực còn tùy resolution.
4. **Không tự chứng minh build thành công.** Việc sinh được effective POM không thay cho `mvn test` hoặc `mvn verify`.
5. **Không tự nói tường tận nguyên nhân merge**. `-Dverbose` giúp tìm origin, nhưng khi nhiều nguồn hợp nhất cần đọc các POM liên quan.
6. **Không có ý nghĩa “mọi thứ đã frozen”.** Nếu profile/JDK/settings/CLI hoặc plugin version đổi, kết quả có thể thay đổi dù source POM không thay đổi.
7. **Không thay thế POM nguồn.** Không đưa `effective-pom.xml` sinh ra làm POM chỉnh sửa chính; cập nhật POM cha/con, profile và quản lý dependency/plugin tại nguồn.
8. **Không mặc định chia sẻ log/config cho bên ngoài.** Effective POM có thể lộ URL repository nội bộ, metadata tổ chức và giá trị property nhạy cảm nếu dự án đã nội suy chúng vào cấu hình. Kiểm tra và lọc trước khi chia sẻ.

### Effective POM khác Effective Settings

- `mvn help:effective-pom`: tập trung vào **mô hình project** sau kế thừa, nội suy và active profiles.
- `mvn help:effective-settings`: tập trung vào **settings Maven hiệu lực** sau kết hợp global/user settings, chẳng hạn mirror, proxy, server và cấu hình liên quan. Cẩn thận khi xuất/chia sẻ settings vì có thể liên quan bí mật.
- `mvn help:active-profiles`: chỉ ra các profile đang có hiệu lực trong ngữ cảnh chạy hiện tại.
- `mvn dependency:tree`: khảo sát cây dependency Maven đã giải quyết.

Chọn công cụ theo câu hỏi cần trả lời; không dùng một file effective POM để kết luận cả bốn loại thông tin.

## 13. Bài tập kiểm tra kế thừa bằng kết quả thực tế

Dùng hai POM ở mục 4. Sau khi tạo file và đứng trong thư mục `app`:

1. Chạy `mvn help:effective-pom -Doutput=effective-default.xml`, mở file này.
2. Xác minh module có tọa độ `com.example.training:training-app:1.0.0` dù child POM không trực tiếp ghi `groupId` và `version`.
3. Tìm `maven.compiler.release`, xác minh `17` đến từ parent.
4. Tìm `demo.label`, xác minh `child-value` của child thay `parent-value`.
5. Tìm `junit-jupiter` ở cả `dependencies` lẫn `dependencyManagement`, xác minh `5.11.4` được áp dụng; phân biệt quản lý và khai báo sử dụng.
6. Tìm `maven-compiler-plugin` trong `build/plugins` và `pluginManagement`, kiểm tra phiên bản `3.14.1`.
7. Chạy lại với `-Dverbose=true`, xác định nguồn các phần tử quan trọng bằng comment.
8. Sinh thêm `effective-dev.xml` với `-Pdev` và đối chiếu thuộc tính `demo.mode=development`.
9. Chạy `mvn -B -ntp clean package` rồi `java -cp target/classes com.example.training.App`; nếu build thành công, stdout Java là `Effective POM demo`.
10. Thay thử một property trong **POM con**, chạy lại Help Plugin và xác nhận output thay đổi theo cấu hình mới. Khôi phục thay đổi thử nghiệm nếu chỉ dùng để học.

**Tiêu chí hoàn thành:** Bạn có thể chỉ ra *giá trị hiệu lực*, *nhánh XML nơi nó xuất hiện*, *nguồn POM/profile đưa ra giá trị* và *lệnh tái kiểm tra*. Đó là cách dùng Effective POM để xác minh cấu hình Maven sau kế thừa một cách có căn cứ.

## Tài liệu chính thức

- [Apache Maven — Introduction to the POM (Super POM, inheritance, interpolation)](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven Help Plugin — help:effective-pom parameters](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Help Plugin — Usage](https://maven.apache.org/plugins/maven-help-plugin/usage.html)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
