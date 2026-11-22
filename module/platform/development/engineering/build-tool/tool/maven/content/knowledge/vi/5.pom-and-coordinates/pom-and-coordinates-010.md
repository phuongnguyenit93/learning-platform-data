# Kiểm tra tính hợp lệ của POM và phát hiện khai báo trùng trong Maven

## 1. Hiểu đúng một POM hợp lệ

**pom.xml** là Project Object Model (POM): tệp XML mô tả tọa độ dự án, dependency, plugin, cách đóng gói, parent, profile và những quy tắc xây dựng sản phẩm. Maven đọc POM để tạo mô hình dự án trước khi thực thi các pha build.

Một POM có thể **đúng cú pháp XML** mà vẫn **sai mô hình Maven**. Thậm chí POM có thể cho kết quả **BUILD SUCCESS** nhưng chứa **khai báo trùng**, cấu hình không rõ ràng hoặc cảnh báo về tính tương thích với phiên bản Maven sau.

Cần phân biệt bốn mức kiểm tra:

| Mức | Nội dung kiểm tra | Ví dụ lỗi |
| --- | --- | --- |
| XML well-formed | Thẻ mở/đóng, dấu nháy, escape ký tự, lồng thẻ đúng. | Thiếu **</dependency>**, dùng dấu **&** trong XML mà không escape. |
| Mô hình POM | Các phần tử, tọa độ, kiểu đóng gói, parent/dependency có hợp lệ với Maven. | Thiếu artifactId; dependency thiếu version và không được quản lý; sai cấu trúc phần tử. |
| Chất lượng khai báo | Dependency/plugin trùng, version không nhất quán, những cảnh báo Maven chấp nhận tạm thời. | Khai báo cùng **org.slf4j:slf4j-api** hai lần với hai version. |
| Cấu hình hiệu lực và build | Maven nhìn thấy gì sau kế thừa/profile/BOM; plugin/dependency có giải quyết được; mã có build/test được. | Sai parent, profile khác CI, plugin chạy lỗi. |

**Pha validate chỉ là điểm khởi đầu.** Maven phải dựng được mô hình dự án để chạy lifecycle, nhưng Maven 3 có thể phát cảnh báo thay vì dừng build khi tìm thấy dependency/plugin trùng. Thành công ở **mvn validate** không chứng minh **compile**, **test**, **package** hoặc kiểm tra chất lượng đã thực hiện.

Mục tiêu học tập của bài: đọc đúng lỗi POM, xác định **khai báo nào trùng theo khóa Maven**, sửa mà không làm mất quản lý version, và cấu hình một bước kiểm tra có thể đưa vào CI.

## 2. POM tối thiểu đúng để đối chiếu

Tệp **pom.xml** độc lập hợp lệ theo modelVersion 4.0.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>pom-validation-demo</artifactId>
    <version>1.0.0</version>
</project>
~~~

Tọa độ dự án là **vn.example:pom-validation-demo:1.0.0**. Nếu không khai báo **packaging**, Maven mặc định dùng **jar**. Trường hợp này chưa có dependency, plugin hoặc mã nguồn, nhưng vẫn là một mô hình dự án hợp lệ để kiểm tra bằng pha validate.

Các nguyên tắc cần biết:

- **project** là thẻ gốc; **modelVersion** thông dụng trong dự án Maven 3 và nhiều dự án Maven 4 vẫn là **4.0.0**.
- **artifactId** nhận diện riêng artifact của module. Với dự án con có **parent**, **groupId** và **version** có thể được kế thừa, vì thế thiếu hai trường này ở cấp con **không mặc nhiên là lỗi**.
- **dependencies** là danh sách những thư viện module sử dụng; **dependencyManagement** quản lý phiên bản/thông tin mặc định cho dependency được khai báo.
- **build/plugins** xác định plugin dùng trong build; **build/pluginManagement** quản lý phiên bản/cấu hình của plugin.
- Parent POM, profile và BOM có thể làm cấu hình hiệu lực khác nội dung nhìn thấy trong một tệp POM đơn lẻ.

Một trình kiểm tra XML Schema (XSD) giúp kiểm tra cấu trúc XML; nó **không thay thế** toàn bộ quy tắc mô hình, kế thừa, giải quyết dependency và cảnh báo của Maven.

## 3. Kiểm tra bằng lệnh Maven

Nếu repository đã có Maven Wrapper, dùng đúng script của dự án. Trong thư mục chứa **pom.xml**:

Linux/macOS:

~~~bash
./mvnw --version
./mvnw -B -ntp validate
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp validate
~~~

Nếu chưa có Wrapper nhưng Maven đã được cài:

~~~bash
mvn --version
mvn -B validate
~~~

**--version** cho biết Maven và Java đang thực sự được dùng; **-B** bật batch mode; **-ntp** giảm log tiến độ tải với Maven có hỗ trợ tùy chọn này. **validate** là một pha của lifecycle Maven; Maven đọc POM và thực thi những goal đã được bind vào pha này nếu có.

Muốn kiểm tra POM của module khác, dùng **-f**:

~~~bash
mvn -B -f services/api/pom.xml validate
~~~

Khi xem kết quả:

1. Đọc **[ERROR]** để tìm cú pháp XML, vị trí phần tử hoặc điều kiện Maven không thể giải quyết.
2. Đọc **[WARNING]**; đây có thể là khai báo dependency/plugin trùng vẫn chưa làm Maven 3 thất bại.
3. Xem **mã thoát** và dòng kết quả build. **BUILD SUCCESS** có thể đi cùng warning.
4. Nếu có lỗi, ưu tiên lỗi đầu tiên về XML/mô hình trước khi chạy các goal khác.

Không nên bật **-q** khi đang tìm cảnh báo: chế độ quiet có thể làm mất các tín hiệu cần xem. Để kiểm tra file XML đơn thuần khi máy đã cài công cụ phù hợp, có thể chạy **xmllint --noout pom.xml**; đó là phép kiểm tra XML well-formed, **không phải** phép xác thực đầy đủ mô hình Maven.

## 4. Lỗi cú pháp, thiếu version và khai báo trùng là ba việc khác nhau

### 4.1. XML sai cú pháp

Đoạn minh họa **cố ý sai, không phải chương trình/POM để chạy**:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <version>2.0.13</version>
<!-- thiếu thẻ đóng dependency -->
~~~

XML parser không thể tạo cây đúng vì thiếu thẻ đóng. Tương tự, ký tự **&** nguyên dạng trong nội dung XML có thể cần được viết thành **&amp;**. Lúc này phải sửa XML trước; các công cụ Maven như Help Plugin có thể chưa chạy được do POM không phân tích được.

### 4.2. Dependency thiếu version

Đoạn minh họa được đặt bên trong thẻ **project**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
    </dependency>
</dependencies>
~~~

Thiếu **version** chỉ là lỗi khi dependency **không được quản lý phiên bản** thông qua dependencyManagement, parent POM hoặc BOM phù hợp. Nếu đã có quản lý version, để dependency trực tiếp không có version là thực hành đúng.

### 4.3. Khai báo trùng

Hai dependency cùng định danh trong **một danh sách dependencies** có thể khiến Maven cảnh báo như:

~~~text
[WARNING] 'dependencies.dependency.(groupId:artifactId:type:classifier)' must be unique
~~~

Đây là **mẫu nhận diện log**, không cam kết là chuỗi đầy đủ giống mọi phiên bản Maven. Version và vị trí POM có thể được đính kèm. Cảnh báo cần sửa ngay cả khi pha validate hoặc build kết thúc thành công.

## 5. Maven dùng khóa nào để nhận diện dependency trùng?

Đối với khai báo dependency, Maven phân biệt bằng tổ hợp:

**groupId + artifactId + type + classifier**

Với thư viện JAR thông thường, **type** mặc định là **jar**, còn **classifier** thường vắng mặt.

**Version không nằm trong khóa duplicate.** Hai bản của cùng thư viện với version khác nhau vẫn bị coi là khai báo trùng nếu groupId, artifactId, type, classifier giống nhau. **Scope** khác nhau cũng không tạo ra hai khai báo độc lập.

| Trường hợp | Kết luận |
| --- | --- |
| Cùng groupId/artifactId/type/classifier, version 1.0 và 2.0 | **Trùng khai báo** |
| Cùng groupId/artifactId/type/classifier, scope compile và test | **Trùng khai báo** |
| Cùng groupId/artifactId nhưng type jar so với type test-jar | Có thể là **hai artifact khác nhau** |
| Dependency ở **dependencyManagement** và ở **dependencies** | **Hợp lệ** khi dùng để quản lý version rồi khai báo sử dụng |
| Dependency xuất hiện ở hai nhánh **dependency:tree** | Đây là các đường dẫn phụ thuộc **bắc cầu**, chưa phải bằng chứng khai báo trực tiếp trùng |
| Plugin ở **pluginManagement** và ở **plugins** | Có thể là mô hình quản lý rồi sử dụng plugin bình thường |

Khi phát hiện trùng, hãy xem **đúng danh sách nơi Maven cảnh báo**. Không xóa một khai báo chỉ vì thấy tên thư viện hai lần trong nhiều POM hoặc nhiều vị trí có vai trò khác nhau.

## 6. Ví dụ đầy đủ: một POM có dependency khai báo trùng

### 6.1. POM cố ý sai về khai báo

Tạo **pom.xml** dưới đây (XML hợp lệ, nhưng **cố ý có duplicate**):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>pom-validation-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.9</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.13</version>
            <scope>compile</scope>
        </dependency>
    </dependencies>
</project>
~~~

Hai phần tử dependency đều có khóa **org.slf4j:slf4j-api:jar:(không classifier)**. Khác nhau ở version và một nơi ghi scope compile tường minh, nhưng vẫn trùng. Gọi:

~~~bash
mvn -B validate
~~~

Với Maven 3, kết quả có thể là **BUILD SUCCESS kèm WARNING**. Đừng hiểu rằng Maven đã nhất quán chọn version phù hợp theo ý muốn nhóm. Khi hợp nhất nhánh Git hoặc nâng phiên bản dependency, cần xác định phiên bản thực sự muốn sử dụng.

### 6.2. Cách sửa đúng: chỉ một dependency

Chọn **một version đã được đánh giá tương thích** rồi giữ một khai báo:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>pom-validation-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.13</version>
        </dependency>
    </dependencies>
</project>
~~~

Chạy lại **mvn -B validate** và đối chiếu log. Trong dự án có code thực tế, chạy thêm **mvn clean verify** sau khi thay dependency để kiểm tra compile, unit test, các bước xác minh được cấu hình và đóng gói.

Không tự động giữ “dòng cuối cùng” trong POM lỗi: nếu hai version xung đột, review yêu cầu của mã nguồn và chính sách dependency trước khi quyết định.

## 7. dependencyManagement không tự tạo duplicate

Ví dụ đoạn đặt trong **project**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.13</version>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
    </dependency>
</dependencies>
~~~

Đây là cấu hình **đúng**: trong **dependencyManagement**, version được quản lý; trong **dependencies**, module khai báo nhu cầu sử dụng. **dependencyManagement không tự thêm dependency vào classpath**. Hai vị trí có nhiệm vụ khác nhau, vì thế không nên xóa dòng trong dependencies chỉ để “hết trùng”.

Quy tắc tương tự áp dụng cho BOM được import vào dependencyManagement. Một BOM có thể quản lý nhiều version, còn module chọn library nào cần dùng bằng dependencies.

Trong mô hình đa module, parent có thể sở hữu dependencyManagement chung; các module con kế thừa quản lý version. Một dependency được nhắc ở parent và child chưa đủ để kết luận hai khai báo trùng trực tiếp trong một danh sách.

## 8. Phát hiện plugin bị khai báo trùng

Trong **build/plugins**, một plugin được định danh bằng **groupId:artifactId**. Không khai báo cùng plugin hai lần để thêm hai khối cấu hình. Maven 3 có thể cảnh báo; Maven 4 nghiêm khắc hơn và trường hợp khai báo plugin trùng có thể làm build thất bại.

Ví dụ sai: hai thẻ **plugin** cùng mô tả Maven Compiler Plugin (đoạn đặt trong **build/plugins**):

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Cách đúng là **hợp nhất cấu hình vào một plugin**:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Nếu plugin cần nhiều goal hoặc pha khác nhau, hãy khai báo plugin một lần và đặt nhiều **execution** bên trong phần **executions** với id rõ ràng. Việc một plugin xuất hiện trong **pluginManagement** của parent và trong **plugins** của module con có thể là cách dùng hoàn toàn hợp lệ.

Thông báo thường gặp có dạng **build.plugins.plugin.(groupId:artifactId) must be unique**. Khi thấy dạng này, hãy tìm các thẻ plugin trong đúng POM và đúng danh sách được báo.

## 9. Chặn dependency trùng bằng Maven Enforcer

Maven Enforcer Plugin có rule **banDuplicatePomDependencyVersions**. Rule phát hiện những dependency được khai báo trùng theo bốn trường **groupId, artifactId, type, classifier**; khi chạy goal **enforce**, rule có thể khiến build thất bại. Điều này hữu ích cho CI vì một cảnh báo không còn bị bỏ qua.

Đặt **đoạn plugin** sau trong **build/plugins** của POM; đây là đoạn XML cấu hình, không phải tệp POM độc lập:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.3</version>
    <executions>
        <execution>
            <id>check-duplicate-pom-dependencies</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <banDuplicatePomDependencyVersions/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **một phiên bản/plugin rule có trong tài liệu Apache Maven**. Khi dùng trong dự án thật, chọn phiên bản plugin tương thích phiên bản Maven/JDK và chính sách nội bộ. Sau đó chạy:

~~~bash
mvn -B validate
~~~

Với POM lỗi ở mục 6.1, Enforcer sẽ kiểm tra dependency trùng ở pha validate và có thể chặn build. Với POM đã sửa ở mục 6.2, phép kiểm tra này phải vượt qua.

**Phạm vi của rule:** phát hiện dependency **khai báo trùng trong POM**. Nó không tự phát hiện mọi lỗi XML, không thay các quy tắc về plugin trùng và không giải quyết mọi version conflict bắc cầu. Nếu POM sai đến mức Maven không đọc được, Enforcer chưa thể chạy; cần sửa XML/mô hình trước.

Nếu muốn kiểm tra xung đột phiên bản trong dependency graph, có thể nghiên cứu thêm rule **dependencyConvergence** của Enforcer hoặc dùng **mvn dependency:tree**. Đó là bài toán khác với kiểm tra duplicate trực tiếp.

## 10. Xem effective POM và active profiles

Một POM có parent, BOM và profile có thể trông rất khác so với cấu hình hiệu lực mà Maven sử dụng. Maven Help Plugin cung cấp:

~~~bash
mvn help:effective-pom -Dverbose -Doutput=effective-pom.xml
mvn help:active-profiles
~~~

- **help:effective-pom** dựng mô hình hiệu lực sau kế thừa, Super POM, quản lý version và profile. Tùy phiên bản Help Plugin, **-Dverbose** bổ sung chú thích nguồn của các phần tử, giúp tìm POM cha/con.
- **-Doutput=effective-pom.xml** ghi kết quả chẩn đoán vào file dễ tìm kiếm. Đây là **đầu ra sinh ra**, không phải POM nguồn để chỉnh sửa.
- **help:active-profiles** liệt kê profile đang kích hoạt. Nếu CI chạy khác máy phát triển, hãy đối chiếu **-P** và điều kiện kích hoạt profile.

Một dependency có thể xuất hiện qua nhiều nhánh phụ thuộc bắc cầu. Để kiểm tra graph:

~~~bash
mvn dependency:tree
~~~

**Dependency tree** dùng để giải thích nguồn gốc/phân giải dependency. Nó không tự chứng minh hai thẻ dependency trực tiếp bị khai báo trùng trong một POM. Ngược lại, **effective POM** có thể đã hợp nhất phần kế thừa, vì vậy với cảnh báo duplicate trực tiếp vẫn cần tìm và sửa trong các POM gốc.

Không lẫn ba khái niệm: **trùng khai báo trong POM**, **trùng đường đi trong dependency graph**, và **một artifact được quản lý version ở parent rồi được sử dụng ở child**.

## 11. Maven 4.1+: mvnval để kiểm tra POM chuyên biệt

Từ **Apache Maven 4.1.0**, bản phân phối Maven có công cụ **mvnval** nhằm kiểm tra một hoặc nhiều POM mà không chạy lifecycle build. **Maven 3 không mặc nhiên có lệnh này**; kiểm tra phiên bản Maven trước khi sử dụng.

Ví dụ:

~~~bash
# Maven 4.1.0+; kiểm tra pom.xml hiện tại
mvnval

# Raw mode: không truy cập repository
mvnval --mode raw pom.xml

# Kiểm tra nhiều POM
mvnval parent/pom.xml module-a/pom.xml
~~~

**Hai chế độ khác nhau**:

- **raw**: đọc raw POM/model, không cần truy cập repository; hữu ích khi parent hoặc BOM chưa được phát hành. Không thấy được những thông tin chỉ xuất hiện sau kế thừa.
- **effective** (mặc định): kiểm tra raw rồi giải quyết parent/BOM cần thiết để đánh giá mô hình Maven sử dụng; có thể truy cập mạng hoặc cache repository.

Công cụ có thể trả về nhiều vấn đề trong một lượt, với mã thoát như **0** (không có vấn đề), **1** (có ít nhất một lỗi), **4** (chỉ có cảnh báo); **2** thường là tham số lệnh không hợp lệ. Nếu đưa vào CI, hãy xử lý cả lỗi và warning theo chính sách dự án.

**mvnval khác mvn validate**: mvnval là công cụ xác thực mô hình chuyên biệt trong Maven 4.1+, còn **mvn validate** chạy một pha build và các goal được gắn vào đó, như Enforcer nếu có. Với dự án Maven 3, dùng **validate + Enforcer + effective POM + build/test** là quy trình phù hợp.

## 12. Các bẫy thường gặp khi làm dự án đa module

**Parent POM khác module POM.** Parent thường quản lý dependency/plugin và có packaging **pom**. Child có thể kế thừa groupId/version; đừng thêm giá trị lặp lại vô ích chỉ để thỏa một phép kiểm tra tự viết không hiểu inheritance.

**BOM quản lý version, không tự thêm dependency.** Một library xuất hiện trong BOM của parent và dependencies của child thường hoàn toàn đúng. Lỗi duplicate thường nằm trong **cùng danh sách** tương ứng của POM, không phải vì cùng một artifact được nhắc ở nhiều vai trò.

**Plugin management và plugin usage có thể cùng tồn tại.** Plugin được quản lý phiên bản từ parent rồi xuất hiện trong build/plugins để kích hoạt hoặc bổ sung cấu hình. Đây khác với hai thẻ plugin trùng ngay trong build/plugins.

**Profile có thể làm kết quả khác nhau.** Một POM với profile active do biến môi trường hay tham số **-P** có thể tạo dependency/plugin khác CI. Hãy xem active profiles và effective POM trước khi sửa.

**Mô hình đa module có thể có va chạm tọa độ/project.** Nếu nhiều module dùng cùng tọa độ hoặc module được khai báo lặp không chủ đích, Maven có thể gặp lỗi reactor riêng. Cần sửa đúng module/tọa độ; không xử lý bằng cách xóa dependency vô can.

**Không chỉnh effective-pom.xml.** Mọi sửa chữa phải nằm trong **pom.xml** nguồn thích hợp, POM cha hoặc cấu hình được nhóm quản lý.

## 13. Quy trình kiểm tra trước khi merge hoặc đưa vào CI

1. **Xác nhận Maven/JDK** đang dùng bằng **mvn --version** hoặc Wrapper **--version**; dùng cùng phiên bản mà CI dự kiến.
2. **Chạy validate với log đầy đủ**; sửa mọi lỗi XML và mô hình theo thông báo trước khi thử chẩn đoán nâng cao.
3. **Đọc cả WARNING lẫn ERROR** và tìm các cụm **must be unique**, **duplicate declaration**, **version is missing**, **Non-resolvable parent POM**.
4. **Tìm đúng nơi chứa khai báo**: dependencies, dependencyManagement, build/plugins, pluginManagement hoặc các profile. So sánh theo khóa, không chỉ nhìn tên artifact.
5. **Loại bỏ/hợp nhất khai báo thừa**, giữ version nhất quán với dependencyManagement/BOM và yêu cầu tương thích. Nếu do merge Git, review lý do của cả hai thay đổi.
6. **Bật kiểm tra tự động** bằng Enforcer khi cần chặn duplicate trực tiếp. Với Maven 4.1+ có thể bổ sung **mvnval** theo chế độ thích hợp.
7. **Chạy lại validate** để xác nhận warning liên quan đã mất và rule kiểm tra thành công.
8. **Xem effective POM và dependency graph** nếu có parent/profile/BOM hoặc nhiều module.
9. **Chạy test/build thực tế**, chẳng hạn **mvn clean verify**, vì POM qua validate vẫn có thể có lỗi compile, test hoặc plugin ở pha sau.

Trong CI, có thể chạy pha validate sớm, rồi verify; không cần ép mọi dự án cài thêm công cụ ngoài Maven nếu cơ chế Maven và plugin kiểm tra đã đủ. Nếu repository dùng Maven Wrapper, hãy giữ lệnh Wrapper nhất quán giữa máy cá nhân và CI.

## 14. Nhầm lẫn và cách xử lý nhanh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “XML đúng nên POM đúng.” | XML chỉ là một lớp; Maven còn quy tắc mô hình và tính hợp lệ của khai báo. |
| “mvn validate thành công nghĩa là không có cảnh báo.” | Maven 3 có thể trả thành công dù vẫn cảnh báo dependency/plugin trùng. |
| “Version khác nghĩa là dependency khác.” | Khóa duplicate **không gồm version**. |
| “Scope test và compile cho cùng thư viện thì khai báo hai lần.” | Scope khác **không** tránh duplicate khi groupId/artifactId/type/classifier giống nhau. |
| “dependencyManagement và dependencies nhắc cùng artifact là lỗi.” | Hai phần phối hợp để quản lý và sử dụng dependency. |
| “Mỗi plugin execution cần một thẻ plugin.” | Một plugin trong build/plugins có thể chứa nhiều execution. |
| “mvn dependency:tree hiện một thư viện hai lần nghĩa là POM khai báo trùng.” | Dependency graph có nhiều đường đi bắc cầu; phải kiểm tra thẻ nguồn. |
| “Enforcer sửa trùng tự động.” | Enforcer phát hiện và chặn theo rule; vẫn cần sửa POM tại nguồn. |
| “Một bản POM qua Maven 3 là chắc chắn qua Maven 4.” | Maven 4 nghiêm khắc hơn với một số cảnh báo cấu hình; cần kiểm tra phiên bản đích. |

## 15. Bài thực hành

1. Tạo một thư mục mới với **pom.xml lỗi** ở mục 6.1. Chạy **mvn -B validate**, ghi lại warning và nhận diện khóa dependency trùng.
2. Thay bằng **POM đã sửa** ở mục 6.2. Chạy validate lại và kiểm tra warning duplicate đã hết.
3. Bổ sung cấu hình **maven-enforcer-plugin** ở mục 9 vào **build/plugins** của POM lỗi, rồi chạy validate. Quan sát rule dừng build khi gặp dependency trùng.
4. Hợp nhất hai khai báo plugin ở mục 8 thành một plugin; kiểm tra POM không còn cảnh báo plugin duplicate.
5. Nếu môi trường có Maven 4.1+, thử **mvnval --mode raw pom.xml**, so sánh với kết quả **mvn validate**; nhớ rằng hai lệnh kiểm tra ở phạm vi khác nhau.

Điều cần đạt là **phát hiện đúng loại lỗi, sửa tại vị trí có trách nhiệm, giữ nguyên ý nghĩa phụ thuộc và ngăn lỗi lặp lại trong CI**. POM hợp lệ và sạch khai báo trùng làm kết quả build dễ dự đoán hơn và giúp việc nâng phiên bản Maven an toàn hơn.

### Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Maven Enforcer — banDuplicatePomDependencyVersions](https://maven.apache.org/enforcer/enforcer-rules/banDuplicatePomDependencyVersions.html)
- [Apache Maven — Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)
- [Apache Maven — Maven POM Validation Tool (mvnval)](https://maven.apache.org/tools/mvnval.html)
