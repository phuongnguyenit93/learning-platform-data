# Tổ chức báo cáo kiểm thử, chất lượng mã và tài liệu API

Một quy trình build Java hoàn chỉnh không chỉ tạo ra các tệp `.class` hoặc JAR. Nhóm phát triển còn cần biết test nào đã chạy, test nào thất bại, mã nguồn có vi phạm quy tắc chất lượng hay không và API công khai của dự án gồm những lớp, phương thức nào.

Apache Ant có thể điều phối toàn bộ quy trình này bằng các target riêng. Các công cụ kiểm thử và phân tích mã tạo báo cáo theo định dạng máy đọc được hoặc định dạng dành cho con người; task `javadoc` tạo tài liệu API từ comment trong mã nguồn. Khi đặt các đầu ra vào một cấu trúc thư mục nhất quán, lập trình viên và hệ thống CI có thể tìm, lưu trữ và so sánh kết quả giữa các lần build.

Bài học tập trung vào ba nhóm đầu ra:

- **Báo cáo kiểm thử:** kết quả test dạng XML và HTML.
- **Báo cáo chất lượng mã:** kết quả kiểm tra quy tắc mã nguồn và phân tích bytecode.
- **Tài liệu API:** trang HTML được tạo từ Javadoc của các package và thành phần công khai.

Sau bài học, bạn có thể:

- Thiết kế cấu trúc thư mục báo cáo và tài liệu trong dự án Ant.
- Tạo báo cáo JUnit XML và tổng hợp thành HTML.
- Tích hợp Checkstyle, PMD hoặc SpotBugs vào target Ant.
- Tạo Javadoc bằng task `<javadoc>`.
- Tổ chức target `test`, `reports`, `quality`, `javadocs` và `verify`.
- Phân biệt lỗi kiểm thử, vi phạm quy tắc chất lượng và lỗi tạo tài liệu.
- Chuẩn bị các tệp đầu ra để CI lưu trữ như build artifacts.

## 1. Vì sao cần tổ chức báo cáo?

Nếu mọi công cụ đều ghi kết quả vào thư mục gốc dự án, sau một thời gian thư mục sẽ có nhiều tệp không liên quan: XML test, log, báo cáo HTML, tệp phân tích tĩnh và tài liệu API. Việc này gây khó khăn khi tìm kết quả của một lần build, dọn dẹp đầu ra cũ hoặc cấu hình CI để tải báo cáo.

Nên phân loại đầu ra theo mục đích. Ví dụ:

```text
project/
├── build.xml
├── src/
│   ├── main/java/
│   └── test/java/
├── config/
│   ├── checkstyle.xml
│   └── pmd-ruleset.xml
└── build/
    ├── classes/
    ├── test-classes/
    ├── reports/
    │   ├── tests/
    │   │   ├── xml/
    │   │   └── html/
    │   ├── checkstyle/
    │   ├── pmd/
    │   ├── spotbugs/
    │   └── coverage/
    └── docs/
        └── api/
```

Ý nghĩa:

| Thư mục | Nội dung |
|---|---|
| `build/classes` | Bytecode của mã nguồn ứng dụng. |
| `build/test-classes` | Bytecode của mã nguồn kiểm thử. |
| `build/reports/tests/xml` | Báo cáo test dạng XML, thuận tiện cho CI và công cụ tổng hợp. |
| `build/reports/tests/html` | Báo cáo test dạng HTML để người phát triển đọc. |
| `build/reports/checkstyle` | Kết quả kiểm tra quy tắc và định dạng mã nguồn. |
| `build/reports/pmd` | Kết quả phân tích các mẫu code có rủi ro hoặc khó bảo trì. |
| `build/reports/spotbugs` | Kết quả phân tích bytecode để tìm lỗi tiềm ẩn. |
| `build/reports/coverage` | Báo cáo độ bao phủ kiểm thử nếu dự án cấu hình công cụ coverage. |
| `build/docs/api` | Tài liệu API HTML được tạo bằng Javadoc. |

Các thư mục này là đầu ra có thể tạo lại. Vì vậy, target `clean` thường xóa `build`, còn mã nguồn, cấu hình công cụ và tài liệu viết tay nằm ngoài thư mục đó.

## 2. Tổ chức báo cáo kiểm thử

Báo cáo test thường có hai dạng chính:

- **XML:** cấu trúc dữ liệu để CI đọc, đếm số test, xác định test lỗi và hiển thị kết quả.
- **HTML:** trang tổng hợp để lập trình viên xem nhanh test nào chạy, test nào thất bại và thông báo lỗi.

Không nên chỉ dựa vào thông báo cuối cùng trên terminal. Khi test thất bại, báo cáo XML giúp giữ lại thông tin có cấu trúc, còn HTML giúp điều tra thuận tiện hơn.

### 2.1. Tạo báo cáo XML từ JUnit Platform

Nếu dự án dùng JUnit 5 và task Ant `<junitlauncher>`, có thể dùng listener `legacy-xml` để tạo báo cáo XML theo định dạng tương thích với hệ thống báo cáo JUnit truyền thống.

Ví dụ target:

```xml
<property name="test.xml.dir" location="build/reports/tests/xml" />

<target name="test" depends="compile-tests">
    <mkdir dir="${test.xml.dir}" />

    <junitlauncher printSummary="true"
                   haltOnFailure="true"
                   outputDir="${test.xml.dir}">
        <classpath>
            <pathelement location="build/classes" />
            <pathelement location="build/test-classes" />
            <path refid="test.runtime.classpath" />
        </classpath>

        <test name="com.example.CalculatorTest">
            <listener type="legacy-xml"
                      sendSysOut="true"
                      sendSysErr="true" />
        </test>
    </junitlauncher>
</target>
```

Trong ví dụ:

- `outputDir` chỉ định nơi ghi đầu ra của task.
- `printSummary="true"` hiển thị tóm tắt trên terminal.
- `haltOnFailure="true"` làm build thất bại nếu có test thất bại.
- Listener `legacy-xml` tạo báo cáo XML cho test được chạy.
- `sendSysOut` và `sendSysErr` yêu cầu đưa nội dung stdout/stderr vào báo cáo tương ứng.

Task `<junitlauncher>` có từ Ant 1.10.3. Cấu hình listener và các thuộc tính đầu ra cần tương thích với phiên bản Ant đang dùng. Classpath của task phải có JUnit Platform Launcher và engine phù hợp, chẳng hạn Jupiter Engine.

### 2.2. Tổng hợp XML thành HTML bằng `junitreport`

Task `<junitreport>` của Ant có thể đọc các báo cáo XML theo định dạng JUnit và tạo báo cáo HTML tổng hợp.

```xml
<property name="test.xml.dir" location="build/reports/tests/xml" />
<property name="test.html.dir" location="build/reports/tests/html" />

<target name="test-report" depends="test">
    <mkdir dir="${test.html.dir}" />

    <junitreport todir="${test.xml.dir}">
        <fileset dir="${test.xml.dir}">
            <include name="TEST-*.xml" />
        </fileset>
        <report format="frames" todir="${test.html.dir}" />
    </junitreport>
</target>
```

`fileset` xác định các XML cần tổng hợp. Phần tử `<report>` chỉ định định dạng và thư mục HTML đầu ra. Có thể chọn `format="frames"` hoặc `format="noframes"` tùy cách muốn hiển thị.

Kết quả thường có trang tổng hợp và các trang chi tiết. Khi mở HTML, người đọc có thể xem số lượng test, test thất bại và thông tin lỗi được ghi trong XML.

`junitreport` chỉ tổng hợp các báo cáo XML phù hợp với định dạng mà task hiểu. Nếu test runner tạo một định dạng XML khác, cần dùng bộ chuyển đổi hoặc listener phù hợp trước khi đưa vào task.

### 2.3. Dùng báo cáo XML trong CI

CI thường cần đường dẫn cố định để thu thập báo cáo. Vì vậy, nên giữ quy ước tên và thư mục ổn định:

```text
build/reports/tests/xml/TEST-com.example.CalculatorTest.xml
build/reports/tests/html/index.html
```

Không nên đặt báo cáo theo thư mục tạm của từng lần chạy nếu hệ thống CI không biết nơi lấy chúng. Với mỗi lần build, có thể lưu cả XML và HTML như artifacts:

- XML dùng để hiển thị kết quả test trong giao diện CI.
- HTML dùng để mở chi tiết khi điều tra.
- Log build giúp xác định lỗi xảy ra ở bước nào.

Nếu build thất bại, hãy bảo đảm pipeline vẫn thu thập báo cáo đã tạo trước khi bước thất bại kết thúc job. Cách cấu hình cụ thể phụ thuộc vào nền tảng CI.

## 3. Kiểm tra chất lượng mã bằng Checkstyle

Checkstyle phân tích mã nguồn Java theo các quy tắc đã cấu hình. Công cụ thường được dùng để kiểm tra quy ước đặt tên, import, khoảng trắng, độ dài dòng, cấu trúc mã và một số quy tắc thiết kế.

Checkstyle tập trung vào mã nguồn và quy tắc style. Nó không thay thế compiler, unit test hoặc công cụ phân tích bytecode.

### 3.1. Cấu hình Checkstyle

Tạo tệp `config/checkstyle.xml` để mô tả bộ quy tắc. Ví dụ đơn giản:

```xml
<?xml version="1.0"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">

<module name="Checker">
    <module name="TreeWalker">
        <module name="AvoidStarImport" />
        <module name="UnusedImports" />
        <module name="NeedBraces" />
        <module name="MethodLength">
            <property name="max" value="60" />
        </module>
        <module name="LineLength">
            <property name="fileExtensions" value="java" />
            <property name="max" value="120" />
        </module>
    </module>
</module>
```

Đây là cấu hình minh họa. Dự án thực tế nên thống nhất quy tắc với nhóm phát triển và chọn các module tương thích với phiên bản Checkstyle đang sử dụng.

### 3.2. Khai báo task Checkstyle trong Ant

Checkstyle cung cấp task Ant. Cần đưa JAR Checkstyle và các dependency cần thiết lên classpath của task, sau đó đăng ký task bằng tệp resource đi kèm bản phân phối:

```xml
<path id="checkstyle.classpath">
    <fileset dir="tools/checkstyle">
        <include name="*.jar" />
    </fileset>
</path>

<taskdef resource="checkstyletask.properties"
         classpathref="checkstyle.classpath" />
```

Sau khi task đã được đăng ký, tạo target kiểm tra:

```xml
<target name="checkstyle" depends="init">
    <mkdir dir="build/reports/checkstyle" />

    <checkstyle config="config/checkstyle.xml"
                failOnViolation="false">
        <fileset dir="src/main/java">
            <include name="**/*.java" />
        </fileset>
        <formatter type="plain" />
        <formatter type="xml"
                   toFile="build/reports/checkstyle/checkstyle.xml" />
    </checkstyle>
</target>
```

Task quét các tệp Java trong `src/main/java`, hiển thị kết quả dạng plain và ghi XML vào thư mục báo cáo.

`failOnViolation="false"` phù hợp khi nhóm đang đưa Checkstyle vào dự án và muốn tạo báo cáo trước khi bật quality gate nghiêm ngặt. Khi quy tắc đã ổn định, có thể dùng `failOnViolation="true"` để làm build thất bại nếu có vi phạm.

### 3.3. Báo cáo và quality gate

Nên phân biệt hai mục tiêu:

- **Thu thập thông tin:** tạo báo cáo để nhóm biết các vi phạm hiện có.
- **Chặn build:** làm build thất bại nếu có vi phạm vượt ngưỡng chính sách.

Một nhóm có thể bắt đầu bằng cách ghi nhận báo cáo nhưng chưa chặn build, sau đó sửa dần mã cũ và bật `failOnViolation`. Không nên âm thầm bỏ qua lỗi của task; `failOnViolation` kiểm soát việc vi phạm quy tắc ảnh hưởng đến kết quả build như thế nào.

## 4. Phân tích mẫu code bằng PMD

PMD phân tích mã nguồn để tìm các mẫu có thể gây lỗi, khó bảo trì hoặc không cần thiết. Ví dụ, một số quy tắc có thể phát hiện biến không được sử dụng, điều kiện phức tạp, code trùng lặp hoặc cấu trúc điều khiển đáng ngờ.

PMD và Checkstyle có vùng chức năng giao nhau nhưng trọng tâm khác nhau:

| Công cụ | Trọng tâm |
|---|---|
| Checkstyle | Quy ước, cấu trúc và phong cách mã nguồn. |
| PMD | Mẫu code có vấn đề, độ phức tạp và các quy tắc thiết kế/lập trình. |

### 4.1. Ruleset của PMD

PMD sử dụng ruleset để xác định quy tắc cần chạy. Ví dụ, có thể dùng ruleset Java quickstart đi kèm bản phân phối hoặc tạo ruleset riêng cho dự án.

Ví dụ khung ruleset:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ruleset name="Project Java Rules"
         xmlns="http://pmd.sourceforge.net/ruleset/2.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://pmd.sourceforge.net/ruleset/2.0.0
         https://pmd.sourceforge.net/ruleset_2_0_0.xsd">

    <description>Rules used by this project.</description>

    <rule ref="category/java/bestpractices.xml" />
    <rule ref="category/java/errorprone.xml" />
</ruleset>
```

Ruleset này tham chiếu các nhóm quy tắc có sẵn. Tùy phiên bản PMD, tên category và ruleset có thể thay đổi; hãy dùng tài liệu đúng phiên bản đang cài.

### 4.2. Gọi PMD CLI từ Ant

PMD có thể được chạy như công cụ dòng lệnh. Cách này giúp buildfile không phụ thuộc vào một task Ant cụ thể của PMD:

```xml
<target name="pmd" depends="init">
    <mkdir dir="build/reports/pmd" />

    <exec executable="pmd" failonerror="true">
        <arg value="check" />
        <arg value="--dir" />
        <arg value="src/main/java" />
        <arg value="--rulesets" />
        <arg value="config/pmd-ruleset.xml" />
        <arg value="--format" />
        <arg value="xml" />
        <arg value="--report-file" />
        <arg value="build/reports/pmd/pmd.xml" />
    </exec>
</target>
```

Ví dụ dùng cú pháp CLI của các phiên bản PMD hiện đại. Máy chạy Ant cần có lệnh `pmd` trên `PATH`, hoặc có thể đặt `executable` thành đường dẫn tuyệt đối đến script PMD trong thư mục cài đặt.

Nếu dự án dùng phiên bản PMD cũ, cú pháp CLI có thể khác. Hãy kiểm tra `pmd --help` và tài liệu phiên bản cài đặt trước khi đưa lệnh vào buildfile.

### 4.3. Kiểm soát kết quả PMD

PMD có thể tạo XML, HTML hoặc định dạng khác tùy phiên bản và formatter. XML phù hợp để CI phân tích; HTML thuận tiện khi đọc thủ công.

Không nên bật mọi quy tắc mà không xem xét bối cảnh dự án. Một số quy tắc có thể tạo cảnh báo không phù hợp với kiến trúc hoặc quy ước hiện tại. Hãy chọn ruleset có chủ đích và xử lý cảnh báo theo mức độ ưu tiên.

## 5. Phân tích bytecode bằng SpotBugs

SpotBugs phân tích bytecode Java đã biên dịch để tìm các mẫu có khả năng gây lỗi. Khác với Checkstyle và PMD thường phân tích mã nguồn, SpotBugs làm việc với các lớp `.class`.

SpotBugs có thể phát hiện các vấn đề như:

- Sử dụng tham chiếu null theo cách có rủi ro.
- Lỗi so sánh chuỗi hoặc đối tượng.
- Quên đóng tài nguyên trong một số mẫu code.
- Đồng bộ hóa hoặc truy cập dữ liệu không an toàn.
- Một số lỗi logic phổ biến trong bytecode.

### 5.1. Đăng ký task SpotBugs

SpotBugs có task Ant riêng. Cần cài bản phân phối SpotBugs và đưa thư viện task cùng các thư viện cần thiết vào classpath:

```xml
<path id="spotbugs.classpath">
    <fileset dir="tools/spotbugs/lib">
        <include name="*.jar" />
    </fileset>
</path>

<taskdef name="spotbugs"
         classname="edu.umd.cs.findbugs.anttask.FindBugsTask"
         classpathref="spotbugs.classpath" />
```

Tên thư mục và cách phân phối JAR phụ thuộc bản cài đặt SpotBugs. Hãy bảo đảm task có thể nạp đủ các dependency của bản SpotBugs đã chọn.

### 5.2. Chạy SpotBugs trên lớp đã biên dịch

Ví dụ target:

```xml
<target name="spotbugs" depends="compile">
    <mkdir dir="build/reports/spotbugs" />

    <spotbugs home="tools/spotbugs"
              output="xml"
              outputFile="build/reports/spotbugs/spotbugs.xml"
              effort="default"
              reportLevel="medium">
        <class location="build/classes" />
        <sourcePath path="src/main/java" />
    </spotbugs>
</target>
```

Trong ví dụ:

- `home` chỉ thư mục cài đặt SpotBugs.
- `output="xml"` yêu cầu báo cáo dạng XML.
- `outputFile` chỉ định tệp báo cáo.
- `effort` điều chỉnh mức độ phân tích.
- `reportLevel` điều chỉnh mức độ cảnh báo được đưa vào báo cáo.
- `<class>` chỉ vị trí bytecode cần phân tích.
- `<sourcePath>` cung cấp đường dẫn mã nguồn để báo cáo có thể hiển thị vị trí dễ hiểu hơn.

Cú pháp task và các thuộc tính có thể thay đổi theo phiên bản SpotBugs. Hãy dùng tài liệu Ant task đi kèm bản cài đặt. SpotBugs cần đầu ra biên dịch trước đó, nên target `spotbugs` phụ thuộc vào `compile`.

### 5.3. Phân biệt SpotBugs với kiểm thử

SpotBugs không thực thi unit test và không chứng minh chương trình đúng. Nó phân tích các mẫu bytecode có rủi ro. Một cảnh báo cần được lập trình viên xem xét trong ngữ cảnh mã nguồn; không phải mọi cảnh báo đều là lỗi có thể tái hiện, và việc không có cảnh báo cũng không bảo đảm chương trình không có bug.

## 6. Tạo tài liệu API bằng task `<javadoc>`

Javadoc tạo tài liệu HTML từ comment đặc biệt trong mã nguồn Java. Tài liệu API giúp người dùng thư viện hiểu package, lớp, constructor, phương thức, tham số, giá trị trả về và ngoại lệ.

Ví dụ comment Javadoc:

```java
package com.example;

/**
 * Performs basic arithmetic operations.
 */
public class Calculator {

    /**
     * Adds two integers.
     *
     * @param left the first value
     * @param right the second value
     * @return the sum of the two values
     */
    public int add(int left, int right) {
        return left + right;
    }
}
```

Comment bắt đầu bằng `/**` là Javadoc comment. Các tag như `@param` và `@return` mô tả hợp đồng sử dụng phương thức.

### 6.1. Tạo tài liệu bằng task `javadoc`

Task `<javadoc>` gọi công cụ Javadoc của JDK:

```xml
<property name="src.dir" location="src/main/java" />
<property name="apidocs.dir" location="build/docs/api" />

<target name="javadocs">
    <mkdir dir="${apidocs.dir}" />

    <javadoc destdir="${apidocs.dir}"
             sourcepath="${src.dir}"
             packagenames="com.example.*"
             encoding="UTF-8"
             docencoding="UTF-8"
             charset="UTF-8"
             windowtitle="Example Application API"
             doctitle="Example Application API"
             author="true"
             version="true"
             use="true"
             failonerror="true">
        <link href="https://docs.oracle.com/en/java/javase/17/docs/api/" />
    </javadoc>
</target>
```

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `destdir` | Thư mục chứa tài liệu HTML được tạo. |
| `sourcepath` | Thư mục gốc chứa mã nguồn Java. |
| `packagenames` | Các package cần tạo tài liệu. |
| `encoding` | Encoding của mã nguồn đầu vào. |
| `docencoding` | Encoding dùng để ghi các tệp tài liệu. |
| `charset` | Charset được khai báo trong trang HTML. |
| `windowtitle` | Tiêu đề cửa sổ/trình duyệt. |
| `doctitle` | Tiêu đề hiển thị trong trang tài liệu. |
| `author` | Đưa thông tin `@author` vào tài liệu. |
| `version` | Đưa thông tin `@version` vào tài liệu. |
| `use` | Tạo trang sử dụng API. |
| `failonerror` | Làm build thất bại nếu Javadoc gặp lỗi. |

Phần tử `<link>` liên kết tài liệu API của dự án với tài liệu Java SE bên ngoài. URL phải trỏ đến phiên bản Javadoc phù hợp với mức Java mà dự án sử dụng.

### 6.2. Chọn package và phạm vi truy cập

Javadoc có thể tạo tài liệu cho các thành phần công khai hoặc mở rộng phạm vi để đưa thêm thành phần package/protected/private vào tài liệu. Với thư viện được phát hành cho người dùng, thường nên tạo tài liệu API công khai.

Có thể dùng `access` để chọn phạm vi, tùy phiên bản JDK/Javadoc mà Ant gọi:

```xml
<javadoc destdir="build/docs/api"
         sourcepath="src/main/java"
         packagenames="com.example.*"
         access="public"
         encoding="UTF-8"
         docencoding="UTF-8"
         failonerror="true" />
```

Các giá trị phạm vi thường gồm `public`, `protected`, `package` và `private`. Chỉ nên tạo tài liệu private khi phục vụ mục đích nội bộ; tài liệu API phát hành không nhất thiết phải lộ chi tiết triển khai.

### 6.3. Viết Javadoc cho package bằng `package-info.java`

Để mô tả mục đích của một package, tạo tệp `package-info.java` trong thư mục tương ứng:

```java
/**
 * Provides services for basic arithmetic operations.
 *
 * <p>Classes in this package are intended for simple calculations.</p>
 */
package com.example;
```

Javadoc dùng comment này để tạo phần mô tả package. Với thư viện có nhiều package, `package-info.java` giúp tài liệu có cấu trúc rõ ràng thay vì chỉ liệt kê tên lớp.

### 6.4. Các tag Javadoc thường dùng

| Tag | Dùng cho | Ý nghĩa |
|---|---|---|
| `@param` | Tham số của phương thức hoặc constructor. | Mô tả đầu vào. |
| `@return` | Phương thức có giá trị trả về. | Mô tả kết quả. |
| `@throws` hoặc `@exception` | Ngoại lệ có thể được ném. | Mô tả điều kiện lỗi. |
| `@since` | Lớp, phương thức hoặc API. | Ghi phiên bản đầu tiên có API. |
| `@deprecated` | API không còn khuyến nghị sử dụng. | Giải thích lý do và hướng thay thế. |
| `@see` | Lớp, phương thức hoặc tài liệu liên quan. | Liên kết tham khảo. |
| `@author` | Lớp hoặc package. | Ghi tác giả nếu dự án có quy ước dùng. |
| `@version` | Lớp hoặc package. | Ghi phiên bản theo quy ước dự án. |

Ví dụ phương thức có điều kiện lỗi:

```java
/**
 * Divides one integer by another.
 *
 * @param dividend the value to divide
 * @param divisor the divisor; must not be zero
 * @return the integer quotient
 * @throws ArithmeticException if divisor is zero
 * @since 1.1
 */
public int divide(int dividend, int divisor) {
    return dividend / divisor;
}
```

Javadoc tốt mô tả hợp đồng của API, gồm đầu vào, đầu ra, điều kiện và ngoại lệ. Không nên chỉ lặp lại tên phương thức bằng một câu chung chung.

### 6.5. Liên kết đến API bên ngoài

Khi tài liệu dùng lớp từ thư viện khác, có thể thêm `<link>` để Javadoc tạo liên kết đến tài liệu của thư viện đó:

```xml
<javadoc destdir="build/docs/api"
         sourcepath="src/main/java"
         packagenames="com.example.*">
    <link href="https://docs.oracle.com/en/java/javase/17/docs/api/" />
    <link href="https://junit.org/junit5/docs/current/api/" />
</javadoc>
```

Chỉ thêm liên kết đến tài liệu ngoài thực sự được tham chiếu. Đường dẫn cần trỏ đến trang Javadoc có cấu trúc phù hợp để công cụ tạo liên kết.

## 7. Tổ chức target báo cáo và tài liệu

Mỗi nhóm đầu ra nên có target riêng. Điều này giúp lập trình viên chỉ chạy bước cần thiết trong quá trình phát triển, đồng thời cho phép CI gọi một target tổng hợp khi cần.

Một cấu trúc target thường dùng:

| Target | Nhiệm vụ |
|---|---|
| `init` | Tạo các thư mục build, report và docs. |
| `compile` | Biên dịch mã nguồn ứng dụng. |
| `compile-tests` | Biên dịch mã kiểm thử. |
| `test` | Chạy test và tạo XML. |
| `test-report` | Tổng hợp XML thành HTML. |
| `checkstyle` | Phân tích quy tắc mã nguồn. |
| `pmd` | Phân tích mẫu code có rủi ro. |
| `spotbugs` | Phân tích bytecode. |
| `javadocs` | Tạo tài liệu API. |
| `quality` | Gom các bước phân tích chất lượng. |
| `reports` | Gom các báo cáo kiểm thử và chất lượng. |
| `docs` | Tạo tài liệu API. |
| `verify` | Chạy các kiểm tra cần thiết trước khi chấp nhận build. |
| `clean` | Xóa toàn bộ đầu ra có thể tạo lại. |

Ví dụ target tổng hợp:

```xml
<target name="quality" depends="checkstyle,pmd,spotbugs" />

<target name="reports" depends="test-report,quality" />

<target name="docs" depends="javadocs" />

<target name="verify" depends="test,quality,javadocs" />
```

Ant thực hiện các target phụ thuộc theo thứ tự khai báo và xử lý dependency bắc cầu trước target hiện tại. Một target chỉ được thực hiện tối đa một lần trong cùng lần gọi Ant.

Nếu `test-report` phụ thuộc `test`, khi chạy `ant reports`, Ant sẽ chạy test trước rồi tổng hợp XML. Tương tự, `spotbugs` cần `compile` vì phân tích bytecode đã được tạo ra.

## 8. Ví dụ buildfile tổng hợp

Ví dụ dưới đây minh họa cách gom các đầu ra vào một cấu trúc thống nhất. Các đường dẫn công cụ và dependency cần được thay bằng vị trí cài đặt thực tế của dự án.

```xml
<project name="quality-docs-demo" default="verify" basedir=".">
    <property name="src.dir" location="src/main/java" />
    <property name="test.src.dir" location="src/test/java" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="test.classes.dir" location="${build.dir}/test-classes" />

    <property name="reports.dir" location="${build.dir}/reports" />
    <property name="test.xml.dir" location="${reports.dir}/tests/xml" />
    <property name="test.html.dir" location="${reports.dir}/tests/html" />
    <property name="apidocs.dir" location="${build.dir}/docs/api" />

    <path id="test.runtime.classpath">
        <fileset dir="lib/test">
            <include name="*.jar" />
        </fileset>
    </path>

    <path id="checkstyle.classpath">
        <fileset dir="tools/checkstyle">
            <include name="*.jar" />
        </fileset>
    </path>

    <taskdef resource="checkstyletask.properties"
             classpathref="checkstyle.classpath" />

    <target name="init">
        <mkdir dir="${classes.dir}" />
        <mkdir dir="${test.classes.dir}" />
        <mkdir dir="${test.xml.dir}" />
        <mkdir dir="${test.html.dir}" />
        <mkdir dir="${reports.dir}/checkstyle" />
        <mkdir dir="${reports.dir}/pmd" />
        <mkdir dir="${reports.dir}/spotbugs" />
        <mkdir dir="${apidocs.dir}" />
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false" />
    </target>

    <target name="compile-tests" depends="compile">
        <javac srcdir="${test.src.dir}"
               destdir="${test.classes.dir}"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath>
                <pathelement location="${classes.dir}" />
                <path refid="test.runtime.classpath" />
            </classpath>
        </javac>
    </target>

    <target name="test" depends="compile-tests">
        <junitlauncher printSummary="true"
                       haltOnFailure="true"
                       outputDir="${test.xml.dir}">
            <classpath>
                <pathelement location="${classes.dir}" />
                <pathelement location="${test.classes.dir}" />
                <path refid="test.runtime.classpath" />
            </classpath>
            <test name="com.example.CalculatorTest">
                <listener type="legacy-xml"
                          sendSysOut="true"
                          sendSysErr="true" />
            </test>
        </junitlauncher>
    </target>

    <target name="test-report" depends="test">
        <junitreport todir="${test.xml.dir}">
            <fileset dir="${test.xml.dir}">
                <include name="TEST-*.xml" />
            </fileset>
            <report format="frames" todir="${test.html.dir}" />
        </junitreport>
    </target>

    <target name="checkstyle" depends="init">
        <checkstyle config="config/checkstyle.xml"
                    failOnViolation="false">
            <fileset dir="${src.dir}">
                <include name="**/*.java" />
            </fileset>
            <formatter type="xml"
                       toFile="${reports.dir}/checkstyle/checkstyle.xml" />
        </checkstyle>
    </target>

    <target name="pmd" depends="init">
        <exec executable="pmd" failonerror="true">
            <arg value="check" />
            <arg value="--dir" />
            <arg value="${src.dir}" />
            <arg value="--rulesets" />
            <arg value="config/pmd-ruleset.xml" />
            <arg value="--format" />
            <arg value="xml" />
            <arg value="--report-file" />
            <arg value="${reports.dir}/pmd/pmd.xml" />
        </exec>
    </target>

    <target name="spotbugs" depends="compile">
        <spotbugs home="tools/spotbugs"
                  output="xml"
                  outputFile="${reports.dir}/spotbugs/spotbugs.xml"
                  effort="default"
                  reportLevel="medium">
            <class location="${classes.dir}" />
            <sourcePath path="${src.dir}" />
        </spotbugs>
    </target>

    <target name="javadocs" depends="init">
        <javadoc destdir="${apidocs.dir}"
                 sourcepath="${src.dir}"
                 packagenames="com.example.*"
                 encoding="UTF-8"
                 docencoding="UTF-8"
                 charset="UTF-8"
                 windowtitle="Quality Docs Demo API"
                 doctitle="Quality Docs Demo API"
                 author="true"
                 version="true"
                 use="true"
                 failonerror="true">
            <link href="https://docs.oracle.com/en/java/javase/17/docs/api/" />
        </javadoc>
    </target>

    <target name="quality" depends="checkstyle,pmd,spotbugs" />
    <target name="reports" depends="test-report,quality" />
    <target name="docs" depends="javadocs" />
    <target name="verify" depends="test,quality,javadocs" />

    <target name="clean">
        <delete dir="${build.dir}" />
    </target>
</project>
```

Đây là khung tích hợp để thể hiện cách tổ chức target và thư mục đầu ra. Trước khi dùng trong dự án, cần:

- Cài đúng JAR và dependency của Checkstyle, SpotBugs, JUnit và Ant task tương ứng.
- Đăng ký task SpotBugs nếu chưa có `taskdef` trong cấu hình chung.
- Bảo đảm lệnh PMD CLI tồn tại và cú pháp phù hợp với phiên bản PMD.
- Chọn package thật thay cho `com.example.*`.
- Bảo đảm classpath kiểm thử có đủ API, Launcher và Engine.
- Điều chỉnh cấu hình quality gate theo chính sách nhóm.

## 9. Phân biệt báo cáo, tài liệu API và artifact phát hành

Ba nhóm đầu ra này phục vụ các mục đích khác nhau:

| Nhóm | Người sử dụng chính | Ví dụ | Có phải sản phẩm chạy của ứng dụng không? |
|---|---|---|---|
| Báo cáo kiểm thử | Lập trình viên, QA, CI | JUnit XML/HTML | Không. |
| Báo cáo chất lượng | Lập trình viên, reviewer, CI | Checkstyle, PMD, SpotBugs XML/HTML | Không. |
| Tài liệu API | Người dùng thư viện, lập trình viên tích hợp | Javadoc HTML | Không phải bytecode; là tài liệu đi kèm API. |
| Artifact phát hành | Người dùng hoặc hệ thống triển khai | JAR, WAR, ZIP | Có thể là sản phẩm được triển khai hoặc sử dụng. |

Không nên đưa tất cả báo cáo vào trong JAR ứng dụng nếu sản phẩm không yêu cầu. Hãy lưu báo cáo và tài liệu như artifacts riêng của pipeline hoặc đóng gói tài liệu vào một gói phân phối riêng.

## 10. Quality gate và cách làm build thất bại

Một báo cáo chỉ cung cấp thông tin; quality gate quyết định kết quả kiểm tra có làm build thất bại hay không.

Ví dụ:

- Unit test thất bại: target `test` trả lỗi và target phụ thuộc không tiếp tục theo cấu hình mặc định.
- Checkstyle có vi phạm: `failOnViolation="true"` có thể làm target thất bại.
- PMD phát hiện vi phạm: cách xử lý phụ thuộc exit code, formatter và cấu hình CLI của phiên bản PMD.
- Javadoc có lỗi: `failonerror="true"` làm target tạo tài liệu thất bại khi công cụ trả lỗi.

Trong giai đoạn đầu, nhóm có thể chỉ tạo báo cáo để hiểu tình trạng hiện tại. Khi đã có baseline, hãy đặt ngưỡng rõ ràng để lỗi mới được phát hiện mà không làm cả nhóm bị chặn bởi một lượng lớn cảnh báo cũ chưa xử lý.

Không nên tắt `failonerror` hoặc bỏ qua exit code chỉ để pipeline luôn xanh. Nếu một bước là bắt buộc, hãy để build thể hiện đúng trạng thái thất bại và giữ lại báo cáo để điều tra.

### 10.1. Chạy từng bước hoặc chạy toàn bộ

Trong lúc phát triển, có thể gọi riêng target:

```bash
ant test
ant checkstyle
ant pmd
ant spotbugs
ant javadocs
```

Khi cần chạy toàn bộ kiểm tra:

```bash
ant verify
```

Khi cần cả báo cáo HTML tổng hợp:

```bash
ant reports
```

Việc chia target giúp rút ngắn vòng phản hồi khi chỉ sửa một phần dự án, đồng thời vẫn có một target tổng hợp để CI gọi.

## 11. Tạo tài liệu API có chất lượng

Javadoc chỉ có ích khi comment mô tả đúng hợp đồng API. Một trang HTML được tạo thành công nhưng thiếu nội dung hoặc chỉ lặp lại tên phương thức vẫn khó sử dụng.

### 11.1. Mô tả hành vi, không chỉ tên phương thức

Comment yếu:

```java
/** Adds two numbers. */
public int add(int a, int b) { ... }
```

Comment rõ hơn:

```java
/**
 * Returns the sum of two integer values.
 *
 * <p>The operation uses Java integer arithmetic. If the mathematical
 * result is outside the range of {@code int}, overflow follows the
 * normal Java language rules.</p>
 *
 * @param left the first value
 * @param right the second value
 * @return the sum of {@code left} and {@code right}
 */
public int add(int left, int right) { ... }
```

Mô tả tốt giúp người dùng hiểu hành vi, giới hạn và kết quả mà không cần đọc phần triển khai.

### 11.2. Ghi rõ ngoại lệ và điều kiện đầu vào

Nếu phương thức có thể ném ngoại lệ, hãy mô tả điều kiện xảy ra:

```java
/**
 * Loads a user by identifier.
 *
 * @param id the user identifier; must not be {@code null}
 * @return the matching user
 * @throws IllegalArgumentException if {@code id} is null or blank
 * @throws UserNotFoundException if no user matches the identifier
 */
public User load(String id) { ... }
```

Javadoc nên phản ánh hợp đồng thực tế của phương thức. Nếu hành vi thay đổi, cập nhật comment cùng lúc với code.

### 11.3. Mô tả package và module

Với thư viện nhiều package, hãy dùng `package-info.java` để giải thích trách nhiệm từng package. Nếu dự án có `module-info.java`, cũng nên mô tả module và các package được export để người dùng hiểu bề mặt API công khai.

### 11.4. Kiểm tra tài liệu khi build

Đặt `failonerror="true"` để Javadoc báo lỗi nếu comment hoặc tham chiếu không hợp lệ theo mức kiểm tra mà JDK hỗ trợ. Có thể tăng mức kiểm tra doclint bằng đối số Javadoc phù hợp với phiên bản JDK. Khi bật kiểm tra nghiêm ngặt, cần xử lý dần các comment cũ để tránh quá nhiều lỗi cùng lúc.

## 12. Lưu trữ và xem báo cáo trong CI

Khi Ant chạy trong CI, thư mục `build` thường bị xóa sau job hoặc workspace được tạo mới cho mỗi lần chạy. Nếu muốn nhóm xem lại kết quả, pipeline cần lưu các đầu ra cần thiết trước khi workspace bị dọn.

Nên lưu:

- `build/reports/tests/xml/` để CI đọc kết quả JUnit.
- `build/reports/tests/html/` để người dùng mở báo cáo tổng hợp.
- `build/reports/checkstyle/`, `pmd/`, `spotbugs/` để xem các vi phạm chất lượng.
- `build/docs/api/` nếu tài liệu API cần được xuất bản hoặc lưu như artifact.
- Log Ant để điều tra lỗi ở các bước không tạo được báo cáo.

Một số nguyên tắc:

1. Giữ tên thư mục và tên báo cáo ổn định giữa các lần build.
2. Không ghi báo cáo vào thư mục nguồn.
3. Tách báo cáo theo công cụ để dễ thu thập.
4. Lưu báo cáo ngay cả khi test hoặc quality gate thất bại, nếu CI hỗ trợ chế độ thu thập artifact khi job thất bại.
5. Không lưu token, mật khẩu hoặc dữ liệu nhạy cảm trong báo cáo.
6. Xác định thời gian lưu trữ phù hợp để tránh tích lũy quá nhiều artifact.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có XML test | Listener không được cấu hình hoặc task chưa chạy đến phần test. | Kiểm tra listener, `outputDir`, classpath và log test. |
| `junitreport` không tạo HTML | Không tìm thấy XML, XML sai định dạng hoặc thiếu bộ xử lý XSLT cần thiết. | Kiểm tra FileSet, nội dung XML và môi trường JDK/Ant. |
| Checkstyle báo không tìm thấy task | Chưa đăng ký task hoặc thiếu JAR trên classpath. | Kiểm tra `taskdef`, resource `checkstyletask.properties` và dependency. |
| Checkstyle không tìm thấy cấu hình | Đường dẫn config sai hoặc file XML không hợp lệ. | Kiểm tra `config` và cấu trúc module. |
| PMD không chạy từ Ant | Lệnh PMD không có trên PATH hoặc cú pháp CLI không đúng phiên bản. | Dùng đường dẫn executable rõ ràng và kiểm tra `pmd --help`. |
| SpotBugs không tìm thấy lớp | Chưa chạy compile hoặc chỉ sai thư mục bytecode. | Đặt `depends="compile"` và kiểm tra `class location`. |
| SpotBugs không nạp được dependency | Cấu hình `home` hoặc classpath task thiếu JAR. | Kiểm tra cấu trúc bản cài SpotBugs và dependency. |
| Javadoc không tìm thấy package | `sourcepath` hoặc `packagenames` không khớp cấu trúc nguồn. | Kiểm tra thư mục gốc và tên package. |
| Javadoc báo lỗi encoding | Encoding đầu vào/đầu ra không thống nhất. | Cấu hình `encoding`, `docencoding` và `charset` phù hợp. |
| Báo cáo HTML không có nội dung | XML đầu vào rỗng hoặc không có test được chạy. | Kiểm tra test discovery và thư mục XML. |
| Target tổng hợp chạy sai thứ tự | Thiếu `depends` hoặc phụ thuộc không thể hiện đúng dữ liệu đầu vào. | Khai báo dependency giữa compile, test, report và phân tích bytecode. |
| CI không giữ báo cáo khi build fail | Bước upload artifact chỉ chạy khi job thành công. | Cấu hình CI thu thập artifact ngay cả khi job thất bại. |

## 14. Bài thực hành

Tạo một dự án Ant có cấu trúc:

```text
quality-lab/
├── build.xml
├── config/
│   ├── checkstyle.xml
│   └── pmd-ruleset.xml
├── src/
│   ├── main/java/com/example/Calculator.java
│   └── test/java/com/example/CalculatorTest.java
└── tools/
    ├── checkstyle/
    └── spotbugs/
```

Thực hiện:

1. Tạo các property `build.dir`, `reports.dir`, `test.xml.dir`, `test.html.dir` và `apidocs.dir`.
2. Tạo target `init` để chuẩn bị thư mục đầu ra.
3. Tạo target `compile` và `compile-tests`.
4. Tạo target `test` dùng JUnit Platform và ghi XML.
5. Tạo target `test-report` dùng `junitreport` để tổng hợp HTML.
6. Đăng ký Checkstyle và tạo target `checkstyle` ghi XML.
7. Gọi PMD CLI từ target `pmd` và lưu báo cáo XML.
8. Đăng ký SpotBugs và tạo target `spotbugs` phân tích thư mục class output.
9. Tạo target `javadocs` để sinh tài liệu API HTML.
10. Tạo target `quality`, `reports`, `docs` và `verify` để gom các bước.
11. Tạo target `clean` xóa toàn bộ thư mục `build`.

Các lệnh nên thử:

```bash
ant test
ant test-report
ant checkstyle
ant pmd
ant spotbugs
ant javadocs
ant verify
```

Sau mỗi lệnh, kiểm tra đúng thư mục báo cáo có được tạo hay không. Cố ý tạo một vi phạm Checkstyle hoặc một đoạn code có vấn đề để quan sát cách công cụ ghi kết quả. Sau đó sửa code và chạy lại để so sánh báo cáo.

### Câu hỏi tự kiểm tra

1. Vì sao nên tách báo cáo XML và HTML của JUnit?
2. `junitreport` làm nhiệm vụ gì?
3. Checkstyle chủ yếu kiểm tra khía cạnh nào của mã nguồn?
4. PMD khác Checkstyle ở trọng tâm phân tích nào?
5. SpotBugs phân tích mã nguồn hay bytecode?
6. Vì sao target `spotbugs` nên phụ thuộc `compile`?
7. Task `<javadoc>` tạo ra loại đầu ra nào?
8. `@param`, `@return` và `@throws` mô tả điều gì?
9. Quality gate khác việc tạo báo cáo như thế nào?
10. Vì sao CI nên lưu báo cáo ngay cả khi build thất bại?

### Đáp án gợi ý

- XML thuận tiện cho CI và công cụ tổng hợp; HTML thuận tiện cho con người xem chi tiết.
- `junitreport` đọc các XML báo cáo JUnit và tạo báo cáo HTML tổng hợp.
- Checkstyle kiểm tra quy tắc, cấu trúc và phong cách mã nguồn.
- PMD tập trung vào các mẫu code có rủi ro, độ phức tạp và vấn đề thiết kế/lập trình.
- SpotBugs phân tích bytecode Java đã biên dịch.
- Vì SpotBugs cần các tệp `.class` để phân tích.
- Javadoc tạo tài liệu API dạng HTML từ mã nguồn và comment Javadoc.
- `@param` mô tả tham số, `@return` mô tả kết quả trả về, `@throws` mô tả ngoại lệ.
- Báo cáo cung cấp thông tin; quality gate quyết định vi phạm có làm build thất bại hay không.
- Báo cáo giúp nhóm điều tra lỗi và xác định nguyên nhân dù job không hoàn thành.

## Kết luận

Ant có thể tổ chức một quy trình tài liệu và chất lượng mã bằng các target riêng. JUnit tạo XML và `junitreport` tổng hợp HTML; Checkstyle kiểm tra quy tắc mã nguồn; PMD tìm các mẫu code có rủi ro; SpotBugs phân tích bytecode; task `<javadoc>` tạo tài liệu API. Hãy đặt các đầu ra vào thư mục `build/reports` và `build/docs`, khai báo quan hệ phụ thuộc đúng giữa compile, test, phân tích và tạo tài liệu, rồi cấu hình CI lưu các báo cáo như artifacts. Cách tổ chức này giúp mỗi lần build để lại bằng chứng rõ ràng về kết quả kiểm thử, chất lượng mã và tài liệu của dự án.
