# Kiểm tra quy ước mã bằng Checkstyle

Checkstyle là công cụ phân tích tĩnh mã nguồn Java để phát hiện những chỗ không tuân theo quy ước định dạng và quy tắc chất lượng mà nhóm đã thống nhất. Công cụ đọc mã nguồn, kiểm tra cấu trúc và báo các vi phạm như dòng quá dài, import wildcard, thiếu dấu ngoặc nhọn, khoảng trắng không đúng hoặc Javadoc chưa đạt yêu cầu.

Trong một dự án Apache Ant, Checkstyle có thể được tích hợp thành một target riêng. Khi đó, lập trình viên có thể chạy kiểm tra từ terminal, còn CI có thể thực hiện cùng một cấu hình trước khi cho phép build hoặc phát hành. Quy tắc được lưu trong tệp cấu hình và quản lý cùng mã nguồn, giúp kết quả nhất quán giữa các máy.

Checkstyle tập trung vào quy ước và một số quy tắc phân tích mã nguồn. Nó không thay thế compiler, unit test, kiểm tra bảo mật hay review thiết kế. Một chương trình có thể biên dịch thành công nhưng vẫn vi phạm Checkstyle; ngược lại, mã nguồn không có vi phạm Checkstyle vẫn có thể chứa lỗi logic.

## 1. Checkstyle kiểm tra điều gì?

Checkstyle đọc các tệp Java và áp dụng tập hợp module kiểm tra được khai báo trong cấu hình. Mỗi module chịu trách nhiệm cho một quy tắc hoặc nhóm quy tắc.

Các nhóm quy tắc thường dùng:

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Định dạng | Indentation, LineLength, WhitespaceAround | Giữ mã nguồn dễ đọc và nhất quán |
| Cấu trúc mã | NeedBraces, AvoidNestedBlocks | Khuyến khích cấu trúc rõ ràng |
| Import | AvoidStarImport, CustomImportOrder | Quản lý import nhất quán |
| Naming | TypeName, MethodName, ConstantName | Thống nhất cách đặt tên |
| Javadoc | JavadocType, JavadocMethod | Chuẩn hóa tài liệu API |
| Modifier | ModifierOrder, RedundantModifier | Giữ khai báo rõ ràng |
| Kích thước và độ phức tạp | MethodLength, CyclomaticComplexity | Phát hiện phương thức hoặc cấu trúc quá phức tạp theo ngưỡng nhóm đặt ra |

Checkstyle có nhiều module hơn các ví dụ trên. Không nên bật tất cả quy tắc ngay lập tức cho một codebase cũ. Hãy chọn một tập quy tắc phù hợp, áp dụng nhất quán và tăng dần mức kiểm tra khi nhóm đã xử lý được các vi phạm hiện có.

## 2. Checkstyle hoạt động cùng Ant như thế nào?

Checkstyle không phải task có sẵn trong Ant core. Muốn gọi task Checkstyle từ build file, cần đưa thư viện Checkstyle vào môi trường của Ant và đăng ký task bằng taskdef.

Luồng cơ bản:

~~~text
build.xml
   |
   +-- taskdef
   |     |
   |     +-- nạp Checkstyle Ant task từ thư viện Checkstyle
   |
   +-- target checkstyle
         |
         +-- đọc config/checkstyle.xml
         |
         +-- chọn các tệp Java bằng fileset
         |
         +-- chạy các module kiểm tra
         |
         +-- ghi báo cáo
         |
         +-- quyết định build tiếp tục hay thất bại
~~~

Cần phân biệt ba thành phần:

- **Checkstyle tool JAR:** chứa công cụ và task Ant; phải được Ant nạp.
- **Tệp cấu hình:** định nghĩa những quy tắc cần áp dụng.
- **Fileset:** xác định mã nguồn nào sẽ được kiểm tra.

Việc khai báo Checkstyle trong classpath của Ant không tự động thêm thư viện đó vào classpath biên dịch hoặc runtime của ứng dụng. Đây là công cụ build, không phải dependency ứng dụng.

## 3. Chuẩn bị Checkstyle cho dự án

### 3.1. Chọn và cố định phiên bản

Chọn một phiên bản Checkstyle tương thích với JDK chạy Ant và cú pháp Java mà dự án sử dụng. Phiên bản Checkstyle quá cũ có thể không phân tích được cú pháp Java mới; phiên bản mới có thể yêu cầu JDK mới hơn.

Không nên tải một bản bất kỳ hoặc dùng tên động như latest. Hãy chốt phiên bản cụ thể, lưu artifact vào kho công cụ được quản lý và ghi nhận checksum theo quy trình dependency của dự án.

Ví dụ cấu trúc:

~~~text
my-ant-project/
├── build.xml
├── config/
│   ├── checkstyle.xml
│   └── checkstyle-suppressions.xml
├── tools/
│   └── checkstyle/
│       └── checkstyle-<version>-all.jar
├── src/
│   ├── main/java/
│   └── test/java/
└── build/
    └── reports/
~~~

Tên checkstyle-<version>-all.jar là dạng minh họa. Thay <version> bằng phiên bản thật đã được dự án chọn. Artifact dạng all thường đóng gói các dependency cần thiết của Checkstyle; nếu dùng JAR không chứa dependency, phải cung cấp đầy đủ các thư viện phụ thuộc trong classpath của task.

### 3.2. Đăng ký task bằng taskdef

Checkstyle cung cấp resource checkstyletask.properties để Ant đăng ký task. Ví dụ:

~~~xml
<property name="checkstyle.jar"
          location="${basedir}/tools/checkstyle/checkstyle-<version>-all.jar" />

<path id="checkstyle.tool.classpath">
    <pathelement location="${checkstyle.jar}" />
</path>

<taskdef resource="checkstyletask.properties"
         classpathref="checkstyle.tool.classpath" />
~~~

Khi build file được nạp, Ant sử dụng classpath trên để tìm resource và lớp triển khai task Checkstyle. Sau đó, target có thể gọi phần tử checkstyle.

Nếu dùng artifact không phải bản all, hãy thêm tất cả dependency cần thiết vào path. Nếu taskdef báo không tìm thấy resource hoặc class, kiểm tra tên JAR, phiên bản, classpath và các dependency đi kèm.

Có thể đăng ký task bằng tên lớp cụ thể nếu cấu hình dự án yêu cầu, nhưng dùng resource đi kèm Checkstyle giúp tránh phải tự ánh xạ tên task sang implementation class.

## 4. Tạo tệp cấu hình checkstyle.xml

### 4.1. Cấu trúc Checker và TreeWalker

Cấu hình Checkstyle thường có module gốc tên là Checker. Các module kiểm tra được đặt trực tiếp dưới Checker hoặc bên trong TreeWalker, tùy loại quy tắc.

- Checker xử lý các kiểm tra ở mức tệp hoặc luồng đầu vào, ví dụ độ dài dòng và bộ lọc suppression.
- TreeWalker phân tích cây cú pháp Java và chạy các module cần cấu trúc cú pháp, ví dụ quy tắc import, naming hoặc dấu ngoặc.

Ví dụ cấu hình cơ bản:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">

<module name="Checker">

    <module name="LineLength">
        <property name="fileExtensions" value="java" />
        <property name="max" value="120" />
    </module>

    <module name="TreeWalker">
        <module name="AvoidStarImport" />
        <module name="NeedBraces" />
        <module name="WhitespaceAround" />
    </module>

</module>
~~~

Trong ví dụ:

- LineLength giới hạn dòng Java ở 120 ký tự.
- AvoidStarImport yêu cầu import từng lớp thay vì dùng wildcard.
- NeedBraces yêu cầu dùng dấu ngoặc nhọn cho các cấu trúc điều khiển theo quy tắc của module.
- WhitespaceAround kiểm tra khoảng trắng quanh các toán tử và token được hỗ trợ.

Đây là cấu hình khởi đầu, không phải bộ quy tắc bắt buộc cho mọi dự án. Nhóm có thể điều chỉnh giới hạn dòng, bổ sung naming/Javadoc hoặc bỏ những quy tắc không phù hợp với convention hiện tại.

### 4.2. Đặt quy tắc ở đúng cấp

Không phải module nào cũng đặt trong TreeWalker. Ví dụ, LineLength là module trực tiếp của Checker trong cấu hình trên. Các module cần phân tích cây cú pháp Java được đặt bên trong TreeWalker.

Nếu đặt module sai cấp, Checkstyle có thể báo cấu hình không hợp lệ hoặc không khởi tạo được module. Khi thêm một quy tắc, hãy tra tài liệu module để xác định parent module, thuộc tính bắt buộc, giá trị mặc định và phiên bản hỗ trợ.

### 4.3. Điều chỉnh thuộc tính của module

Nhiều module có thể được cấu hình bằng phần tử property. Ví dụ, có thể điều chỉnh giới hạn độ dài dòng:

~~~xml
<module name="LineLength">
    <property name="fileExtensions" value="java" />
    <property name="max" value="100" />
</module>
~~~

Một số module hỗ trợ nhiều thuộc tính khác nhau. Không nên sao chép thuộc tính từ module này sang module khác nếu chưa kiểm tra tài liệu; tên và kiểu giá trị thuộc tính phụ thuộc từng module.

## 5. Chọn tệp Java bằng fileset

Ant dùng fileset để xác định tập hợp tệp cần kiểm tra. Ví dụ chỉ kiểm tra mã nguồn chính:

~~~xml
<checkstyle config="${basedir}/config/checkstyle.xml">
    <fileset dir="${basedir}/src/main/java"
             includes="**/*.java" />
</checkstyle>
~~~

Mẫu **/*.java chọn các tệp Java trong thư mục gốc và các thư mục con. Nếu dự án có mã nguồn test, có thể tạo một fileset riêng:

~~~xml
<checkstyle config="${basedir}/config/checkstyle.xml">
    <fileset dir="${basedir}/src/main/java"
             includes="**/*.java" />
    <fileset dir="${basedir}/src/test/java"
             includes="**/*.java" />
</checkstyle>
~~~

Có thể loại trừ mã nguồn được sinh tự động hoặc thư mục không thuộc phạm vi quy ước của nhóm:

~~~xml
<fileset dir="${basedir}/src"
         includes="**/*.java"
         excludes="**/generated/**,**/vendor/**" />
~~~

Chỉ loại trừ thư mục khi có lý do rõ ràng. Nếu loại trừ quá rộng, mã nguồn quan trọng sẽ không được kiểm tra. Nên ghi chú phạm vi loại trừ trong build file hoặc tài liệu dự án.

Nếu dự án dùng nhiều source root, hãy thêm từng fileset tương ứng. Không nên trỏ fileset vào toàn bộ workspace hoặc thư mục build vì có thể quét nhầm mã nguồn sinh tự động, mã đã biên dịch hoặc thư viện được giải nén.

## 6. Tạo target Checkstyle trong build.xml

### 6.1. Target kiểm tra và lưu báo cáo

Ví dụ target cơ bản:

~~~xml
<property name="checkstyle.config"
          location="${basedir}/config/checkstyle.xml" />
<property name="checkstyle.report.dir"
          location="${basedir}/build/reports" />
<property name="checkstyle.report"
          location="${checkstyle.report.dir}/checkstyle.xml" />

<target name="prepare-checkstyle-report">
    <mkdir dir="${checkstyle.report.dir}" />
</target>

<target name="checkstyle" depends="prepare-checkstyle-report">
    <checkstyle config="${checkstyle.config}"
                failOnViolation="true">
        <fileset dir="${basedir}/src/main/java"
                 includes="**/*.java" />
        <formatter type="xml"
                   toFile="${checkstyle.report}" />
    </checkstyle>
</target>
~~~

Target này thực hiện các bước:

1. Tạo thư mục báo cáo.
2. Đọc tệp cấu hình Checkstyle.
3. Chọn mã nguồn Java trong src/main/java.
4. Chạy các module kiểm tra.
5. Ghi kết quả theo định dạng XML.
6. Làm build thất bại nếu có vi phạm theo chính sách failOnViolation.

Thuộc tính failOnViolation điều khiển việc task có làm build thất bại khi phát hiện vi phạm hay không. Với CI, nên bật để quy tắc chất lượng trở thành điều kiện của pipeline. Nếu đặt false, task có thể tạo báo cáo nhưng build vẫn tiếp tục; khi đó cần có bước khác đọc kết quả và quyết định trạng thái.

### 6.2. Lưu báo cáo dễ đọc

Có thể tạo báo cáo plain text bên cạnh XML:

~~~xml
<checkstyle config="${checkstyle.config}"
            failOnViolation="true">
    <fileset dir="${basedir}/src/main/java"
             includes="**/*.java" />
    <formatter type="plain"
               toFile="${checkstyle.report.dir}/checkstyle.txt" />
    <formatter type="xml"
               toFile="${checkstyle.report}" />
</checkstyle>
~~~

Báo cáo plain text thuận tiện để đọc trong terminal hoặc tải về. XML phù hợp cho hệ thống CI, dashboard hoặc công cụ tổng hợp kết quả.

Nếu build thất bại do vi phạm, hãy giữ báo cáo làm artifact của job để lập trình viên biết file, dòng và module gây lỗi. Cấu hình pipeline cần lưu báo cáo ngay cả khi bước Checkstyle trả về trạng thái thất bại.

## 7. Điều khiển mức độ nghiêm ngặt

### 7.1. failOnViolation

Khi failOnViolation="true", vi phạm được Checkstyle phát hiện sẽ làm task báo lỗi theo cấu hình. Đây là lựa chọn phù hợp khi nhóm muốn mọi thay đổi mới phải tuân theo quy ước.

Khi failOnViolation="false", task có thể hoàn tất và tạo báo cáo mà không làm build thất bại chỉ vì vi phạm. Cách này hữu ích trong giai đoạn đầu áp dụng cho codebase cũ, nhưng không nên để trạng thái cảnh báo kéo dài mà không có kế hoạch xử lý.

Có thể tách hai target:

~~~xml
<target name="checkstyle-report">
    <checkstyle config="${checkstyle.config}"
                failOnViolation="false">
        <fileset dir="${basedir}/src/main/java"
                 includes="**/*.java" />
        <formatter type="xml"
                   toFile="${checkstyle.report}" />
    </checkstyle>
</target>

<target name="checkstyle-strict">
    <checkstyle config="${checkstyle.config}"
                failOnViolation="true">
        <fileset dir="${basedir}/src/main/java"
                 includes="**/*.java" />
        <formatter type="plain" />
    </checkstyle>
</target>
~~~

Target report dành cho việc thu thập và xem kết quả; target strict dành cho pipeline hoặc bước xác nhận bắt buộc. Cả hai nên dùng cùng config để không tạo ra hai bộ quy tắc khác nhau.

### 7.2. Severity của từng module

Module Checkstyle có thể cấu hình mức severity, thường gồm error, warning, info hoặc ignore. Mức severity giúp phân loại mức độ quan trọng của vi phạm trong báo cáo.

Ví dụ:

~~~xml
<module name="TreeWalker">
    <module name="AvoidStarImport">
        <property name="severity" value="error" />
    </module>
    <module name="NeedBraces">
        <property name="severity" value="warning" />
    </module>
</module>
~~~

Severity phân loại thông điệp. Cách task Ant quyết định thất bại còn phụ thuộc cấu hình failOnViolation và hành vi của phiên bản Checkstyle/task đang dùng. Hãy kiểm tra tài liệu phiên bản dự án và xác nhận bằng một ví dụ vi phạm có chủ đích trước khi dựa vào severity để phân nhánh CI.

Không nên coi mọi warning là vô hại. Nhóm cần thống nhất quy tắc nào là bắt buộc và quy tắc nào chỉ mang tính khuyến nghị.

## 8. Dùng suppression có kiểm soát

Trong codebase hiện hữu, có thể có một số tệp chưa thể tuân theo quy tắc mới ngay lập tức. Checkstyle hỗ trợ suppression để bỏ qua một số vi phạm có phạm vi xác định.

Có thể khai báo SuppressionFilter trong cấu hình:

~~~xml
<module name="Checker">
    <module name="SuppressionFilter">
        <property name="file"
                  value="${config_loc}/checkstyle-suppressions.xml" />
    </module>

    <module name="TreeWalker">
        <module name="AvoidStarImport" />
        <module name="NeedBraces" />
    </module>
</module>
~~~

Đường dẫn config_loc là biến cấu hình thường được truyền vào Checkstyle để trỏ tới thư mục chứa config. Nếu dùng biến này, hãy bảo đảm task Ant cung cấp property tương ứng hoặc thay bằng đường dẫn rõ ràng phù hợp với cấu trúc dự án.

Một tệp suppression có thể có dạng:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE suppressions PUBLIC
    "-//Checkstyle//DTD SuppressionFilter Configuration 1.2//EN"
    "https://checkstyle.org/dtds/suppressions_1_2.dtd">

<suppressions>
    <suppress checks="LineLength"
              files="LegacyAdapter\.java"
              lines="40-45"
              message=".*" />
</suppressions>
~~~

Ví dụ này minh họa việc giới hạn suppression theo tên tệp, dòng và loại check. Hãy điều chỉnh biểu thức chính quy theo đúng đường dẫn và thông điệp thực tế của báo cáo.

Suppression nên hẹp và có lý do:

- Chỉ loại trừ tệp hoặc dòng thật sự cần thiết.
- Ghi chú lý do và thời hạn xử lý nếu đó là ngoại lệ tạm thời.
- Không loại trừ toàn bộ module hoặc toàn bộ thư mục chỉ để build xanh.
- Rà soát suppression khi mã nguồn được chỉnh sửa hoặc quy tắc được cập nhật.

Nếu một quy tắc không phù hợp với dự án, hãy quyết định rõ có nên thay đổi cấu hình chung hay không. Không dùng suppression để che lỗi thiết kế cấu hình.

## 9. Tích hợp Checkstyle vào luồng build

### 9.1. Chạy độc lập

Lập trình viên có thể chạy:

~~~text
ant checkstyle
~~~

Lệnh này chỉ chạy target Checkstyle cùng các dependency của target đó. Đây là cách nhanh để kiểm tra mã nguồn trước khi commit.

Có thể chạy target nghiêm ngặt:

~~~text
ant checkstyle-strict
~~~

Tên target phụ thuộc build file dự án. Hãy thống nhất tên giữa tài liệu và cấu hình CI.

### 9.2. Gắn với target verify hoặc ci

Có thể tạo target tổng hợp:

~~~xml
<target name="verify"
        depends="compile,checkstyle,test" />

<target name="ci"
        depends="clean,verify,package" />
~~~

Khi gọi ant ci, Ant thực hiện các target phụ thuộc theo đồ thị dependency. Nếu Checkstyle hoặc test làm build thất bại, target tổng hợp không thể hoàn tất thành công.

Không nên để target package hoặc deploy bỏ qua Checkstyle nếu quy trình phát hành yêu cầu kiểm tra này. Hãy xác định rõ target nào là luồng chính của CI và bảo đảm các job release gọi đúng target đó.

### 9.3. Kiểm tra mã nguồn mới hay toàn bộ codebase

Một số nhóm chỉ muốn kiểm tra phần mã thay đổi trong pull request, trong khi vẫn chạy full Checkstyle định kỳ. Checkstyle Ant task nhận fileset; có thể cấp danh sách tệp thay đổi bằng một bước tạo danh sách hoặc fileset động phù hợp.

Tuy nhiên, không nên làm cho target local và CI dùng bộ quy tắc khác nhau mà không có lý do. Nếu CI chỉ kiểm tra mã thay đổi, vẫn nên có một job định kỳ kiểm tra toàn bộ codebase để phát hiện vi phạm tồn đọng hoặc config drift.

## 10. Tổ chức cấu hình theo dự án

### 10.1. Giữ cấu hình trong repository

Nên lưu các tệp sau cùng mã nguồn:

~~~text
config/
├── checkstyle.xml
└── checkstyle-suppressions.xml

tools/
└── checkstyle/
    └── checkstyle-<version>-all.jar

build/
└── reports/
    ├── checkstyle.xml
    └── checkstyle.txt
~~~

Nhờ đó, mọi lập trình viên và runner CI sử dụng cùng phiên bản công cụ và cùng quy tắc. Nếu nhóm thay đổi quy ước, thay đổi config sẽ được review như một phần của mã nguồn.

Thư mục build/reports là đầu ra sinh tự động, thường có thể bỏ qua trong Git và lưu dưới dạng artifact CI. Công cụ Checkstyle và config là đầu vào build, cần được quản lý phiên bản theo chính sách dự án.

### 10.2. Truyền property cho cấu hình

Nếu config cần dùng đường dẫn tương đối, có thể truyền property cho Checkstyle task:

~~~xml
<checkstyle config="${checkstyle.config}"
            properties="${basedir}/config/checkstyle.properties"
            failOnViolation="true">
    <fileset dir="${basedir}/src/main/java"
             includes="**/*.java" />
</checkstyle>
~~~

Tệp properties có thể chứa các giá trị được tham chiếu từ cấu hình Checkstyle, tùy cơ chế property expansion của phiên bản task. Hãy xác nhận tên property và thứ tự nạp trong tài liệu Checkstyle tương ứng. Không nhầm Ant project property với property file mà Checkstyle sử dụng để mở rộng giá trị trong config.

## 11. Checkstyle và các công cụ chất lượng khác

Checkstyle chỉ là một phần của quy trình chất lượng mã. Các công cụ khác có mục tiêu khác nhau:

| Công cụ hoặc bước | Mục tiêu chính |
|---|---|
| Checkstyle | Quy ước mã, định dạng, cấu trúc và một số quy tắc tĩnh |
| javac | Kiểm tra mã nguồn có biên dịch được hay không |
| Unit test | Xác minh hành vi của các thành phần theo test case |
| Integration test | Kiểm tra sự phối hợp giữa nhiều thành phần |
| Static analysis chuyên sâu | Phát hiện một số lỗi logic, bug pattern hoặc vấn đề bảo mật |
| Code review | Đánh giá thiết kế, khả năng bảo trì, yêu cầu nghiệp vụ và rủi ro |

Không nên dùng Checkstyle như bằng chứng duy nhất rằng mã nguồn không có bug. Một class có thể tuân thủ hoàn toàn quy tắc định dạng nhưng vẫn tính sai kết quả hoặc xử lý exception không đúng.

Một pipeline thường chạy theo thứ tự:

~~~text
checkout source
      |
      v
prepare tools/dependencies
      |
      v
Checkstyle
      |
      v
compile
      |
      v
unit tests
      |
      v
package
      |
      v
publish artifact
~~~

Chạy Checkstyle sớm giúp phát hiện lỗi quy ước trước khi tốn thời gian cho các bước build nặng hơn. Thứ tự chính xác có thể thay đổi theo dependency của dự án, nhưng các bước kiểm tra bắt buộc cần được nối vào target CI.

## 12. Xử lý codebase cũ khi bắt đầu áp dụng

Nếu dự án có nhiều năm mã nguồn, bật hàng chục quy tắc với failOnViolation="true" có thể làm toàn bộ build thất bại ngay lập tức. Có thể triển khai theo giai đoạn:

1. Chọn một nhóm quy tắc nhỏ, rõ ràng và có lợi ích cao.
2. Chạy Checkstyle trên toàn bộ mã nguồn để tạo báo cáo hiện trạng.
3. Sửa các vi phạm phổ biến hoặc ảnh hưởng lớn.
4. Dùng suppression hẹp cho phần mã cũ chưa thể xử lý.
5. Bật failOnViolation trong CI cho các quy tắc đã thống nhất.
6. Bổ sung quy tắc mới theo từng đợt và review tác động.
7. Loại bỏ suppression khi phần mã liên quan đã được sửa.

Nếu muốn tránh đưa thêm vi phạm mới trong khi chưa sửa hết codebase, nhóm có thể so sánh báo cáo với baseline hoặc chỉ kiểm tra các tệp thay đổi. Cơ chế baseline cần được quản lý cẩn thận để không biến thành danh sách bỏ qua vô thời hạn.

Không nên tự động xóa hoặc sửa toàn bộ mã nguồn chỉ để làm Checkstyle hết lỗi. Một số thay đổi định dạng có thể ảnh hưởng diff, merge conflict hoặc làm khó review. Hãy dùng formatter và thay đổi theo từng phạm vi có thể kiểm soát.

## 13. Các lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Ant báo không nhận ra task checkstyle | Chưa đăng ký taskdef hoặc thiếu Checkstyle JAR | Kiểm tra taskdef resource, classpath và dependency |
| Không tìm thấy checkstyletask.properties | Artifact không chứa resource hoặc classpath trỏ sai | Dùng distribution phù hợp và kiểm tra nội dung JAR |
| Checkstyle không phân tích được cú pháp Java mới | Phiên bản Checkstyle quá cũ so với source language | Nâng phiên bản công cụ đã được dự án phê duyệt |
| Config báo module không hợp lệ | Module đặt sai cấp hoặc tên/property không đúng | Kiểm tra tài liệu module và vị trí dưới Checker/TreeWalker |
| Không tìm thấy tệp cấu hình | Đường dẫn config tương đối được tính từ thư mục làm việc khác dự kiến | Dùng basedir và location để tạo đường dẫn rõ ràng |
| Không có tệp nào được kiểm tra | Fileset sai thư mục gốc hoặc include/exclude không khớp | Kiểm tra source root và mẫu **/*.java |
| Báo cáo không được tạo | Thư mục đích chưa tồn tại hoặc quyền ghi không đủ | Tạo thư mục trước và kiểm tra quyền |
| Build vẫn thành công dù có vi phạm | failOnViolation=false hoặc target không nằm trong luồng CI | Bật failOnViolation và nối target vào verify/ci |
| Quá nhiều vi phạm trong codebase cũ | Quy tắc được bật quá rộng cùng lúc | Áp dụng theo giai đoạn và dùng suppression có kiểm soát |
| CI và local cho kết quả khác nhau | Phiên bản Checkstyle hoặc config khác nhau | Cố định artifact/config và in phiên bản công cụ trong log |
| Tệp sinh tự động bị báo lỗi | Fileset bao gồm thư mục generated hoặc build | Loại trừ đúng thư mục không thuộc phạm vi kiểm tra |

Khi điều tra, hãy xác định lỗi thuộc bước nạp task, đọc config, chọn tệp, chạy module hay ghi báo cáo. Mỗi loại có nguyên nhân khác nhau; thay đổi rule config sẽ không giải quyết được lỗi classpath hoặc quyền ghi tệp.

## 14. Checklist tích hợp Checkstyle với Ant

- [ ] Đã chọn phiên bản Checkstyle tương thích với JDK và cú pháp Java của dự án.
- [ ] Đã lưu artifact Checkstyle ở vị trí được quản lý và cố định phiên bản.
- [ ] Đã đăng ký task bằng taskdef với đầy đủ classpath.
- [ ] Đã tạo config/checkstyle.xml và đặt module đúng cấp.
- [ ] Đã xác định source root cần kiểm tra bằng fileset.
- [ ] Đã loại trừ có chủ đích các mã nguồn sinh tự động hoặc không thuộc phạm vi.
- [ ] Đã tạo thư mục báo cáo trước khi chạy task.
- [ ] Đã cấu hình formatter phù hợp để lưu báo cáo.
- [ ] Đã quyết định failOnViolation theo chính sách của dự án.
- [ ] Đã nối target Checkstyle vào verify hoặc CI nếu đây là bước bắt buộc.
- [ ] Đã quản lý suppression hẹp, có lý do và có thể rà soát.
- [ ] Đã bảo đảm local và CI dùng cùng công cụ và cấu hình.

## 15. Nguyên tắc duy trì

- Coi Checkstyle là một bước kiểm tra mã nguồn độc lập trong build Ant.
- Cố định phiên bản Checkstyle và quản lý JAR cùng công cụ build.
- Giữ config trong repository để nhóm và CI dùng cùng quy tắc.
- Chọn rule phù hợp với convention của dự án, không bật mọi rule một cách máy móc.
- Dùng fileset để giới hạn đúng source root.
- Tạo báo cáo XML hoặc plain text để hỗ trợ xử lý vi phạm.
- Bật failOnViolation cho những quy tắc đã trở thành điều kiện bắt buộc.
- Dùng suppression có phạm vi hẹp và có lý do.
- Không nhầm Checkstyle với compiler, test hoặc công cụ phân tích bảo mật.
- Kiểm tra phiên bản công cụ, cấu hình và target CI để tránh sai khác giữa các môi trường.

Khi Checkstyle được tích hợp thành target Ant rõ ràng, quy ước mã trở thành một phần có thể thực thi và kiểm tra lặp lại của quy trình build. Nhóm có thể thống nhất cách viết Java, phát hiện sớm vi phạm và giữ kết quả kiểm tra nhất quán trên máy phát triển lẫn CI.

