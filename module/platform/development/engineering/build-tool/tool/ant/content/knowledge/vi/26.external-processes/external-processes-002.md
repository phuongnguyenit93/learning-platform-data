# Truyền đối số bằng arg và tránh lỗi tách chuỗi lệnh trong Apache Ant

Khi build file Ant cần chạy một chương trình bên ngoài, task exec cho phép chỉ định chương trình cần khởi chạy và truyền các đối số cho chương trình đó. Cách truyền đối số quyết định chương trình nhận được bao nhiêu tham số, mỗi tham số chứa nội dung gì và những đường dẫn có dấu cách được xử lý ra sao.

Một lỗi phổ biến là ghép toàn bộ lệnh thành một chuỗi rồi đưa vào arg line. Khi chuỗi có dấu cách, dấu nháy, ký tự đặc biệt hoặc đường dẫn dài, Ant có thể tách thành những đối số khác với ý định. Cách ổn định hơn là khai báo executable riêng và truyền từng đối số bằng một phần tử arg.

Bài học này tập trung vào task exec, các dạng arg, cách xử lý khoảng trắng và ký tự đặc biệt, cách truyền danh sách đường dẫn, kiểm soát mã thoát và những trường hợp cần gọi shell một cách có chủ đích.

## 1. Chương trình bên ngoài và đối số dòng lệnh

Một tiến trình thường được khởi chạy với hai thành phần:

- **Executable**: chương trình hoặc file thực thi cần chạy.
- **Arguments**: các đối số được truyền cho chương trình đó.

Ví dụ lệnh:

~~~bash
java -jar "tools/report generator.jar" --output "build/reports/final report.html"
~~~

Có thể hiểu thành các thành phần:

| Vị trí | Giá trị |
|---|---|
| Executable | java |
| Argument 1 | -jar |
| Argument 2 | tools/report generator.jar |
| Argument 3 | --output |
| Argument 4 | build/reports/final report.html |

Dấu nháy kép trong ví dụ shell giúp shell gom phần có dấu cách thành một đối số. Khi cấu hình trực tiếp bằng Ant, bạn không cần tự thêm dấu nháy để giữ một giá trị có khoảng trắng thành một đối số. Phần tử arg sẽ xác định ranh giới đối số.

Ví dụ tương đương trong Ant:

~~~xml
<exec executable="java" failonerror="true">
    <arg value="-jar"/>
    <arg value="tools/report generator.jar"/>
    <arg value="--output"/>
    <arg value="build/reports/final report.html"/>
</exec>
~~~

Ở đây, mỗi phần tử arg tạo một đối số riêng. Đối số chứa dấu cách vẫn được truyền như một giá trị duy nhất.

## 2. Task exec trong Apache Ant

Task exec chạy một chương trình bên ngoài Ant. Bạn chỉ định chương trình bằng thuộc tính executable, rồi khai báo các đối số bằng những phần tử arg lồng bên trong.

Cấu trúc cơ bản:

~~~xml
<exec executable="program-name"
      dir="working-directory"
      failonerror="true">
    <arg value="first-argument"/>
    <arg value="second-argument"/>
</exec>
~~~

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| executable | Tên hoặc đường dẫn chương trình cần chạy. |
| dir | Thư mục làm việc của tiến trình con. |
| failonerror | Nếu là true, build thất bại khi chương trình trả mã thoát khác 0. |
| failifexecutionfails | Quyết định Ant có thất bại nếu không thể khởi chạy chương trình hay không. |
| timeout | Giới hạn thời gian chạy, tính bằng mili giây. |
| output | File nhận standard output. |
| error | File nhận standard error. |
| outputproperty | Property nhận standard output. |
| errorproperty | Property nhận standard error. |
| resultproperty | Property nhận mã thoát của chương trình. |
| newenvironment | Điều khiển việc dùng môi trường tiến trình mới hay kế thừa môi trường hiện tại. |
| spawn | Chạy tiến trình theo cách tách khỏi tiến trình Ant, không chờ kết quả theo luồng thông thường. |

Ví dụ:

~~~xml
<exec executable="git"
      dir="."
      failonerror="true">
    <arg value="status"/>
    <arg value="--short"/>
</exec>
~~~

Ant chạy Git trong thư mục làm việc của project và truyền hai đối số status và --short.

### 2.1. executable không phải một chuỗi lệnh hoàn chỉnh

Thuộc tính executable chỉ nên chứa tên hoặc đường dẫn của chương trình. Không nối các đối số vào cùng thuộc tính.

Không nên viết:

~~~xml
<exec executable="git status --short"/>
~~~

Ant sẽ tìm chương trình có tên tương ứng với toàn bộ giá trị đó, thay vì hiểu git là executable và phần còn lại là arguments.

Hãy viết:

~~~xml
<exec executable="git" failonerror="true">
    <arg value="status"/>
    <arg value="--short"/>
</exec>
~~~

Cách tách này cũng giúp thay đổi từng tham số dễ dàng hơn.

### 2.2. Đường dẫn executable có dấu cách

Nếu đường dẫn chương trình chứa khoảng trắng, đặt toàn bộ đường dẫn vào thuộc tính executable:

~~~xml
<property name="tool.exe"
          location="tools/Build Utilities/formatter.exe"/>

<exec executable="${tool.exe}" failonerror="true">
    <arg value="--version"/>
</exec>
~~~

Không cần tự bọc giá trị executable trong dấu nháy kép. Ant nhận đường dẫn như một giá trị thuộc tính và xử lý việc khởi chạy tiến trình.

Khi có thể, dùng property với location để tạo đường dẫn đầy đủ. Điều này giảm phụ thuộc vào thư mục hiện tại và tránh lỗi khi build được gọi từ vị trí khác.

### 2.3. Thư mục làm việc với dir

Thuộc tính dir chỉ định thư mục làm việc của tiến trình con. Nó ảnh hưởng đến cách chương trình bên ngoài diễn giải các đường dẫn tương đối mà chương trình nhận được.

Ví dụ:

~~~xml
<exec executable="git"
      dir="module-a"
      failonerror="true">
    <arg value="status"/>
</exec>
~~~

Git chạy trong thư mục module-a. Thư mục làm việc của tiến trình con không đồng nghĩa với việc thay đổi basedir của toàn bộ Ant project.

Nếu một đường dẫn đầu vào cần trỏ đến đúng file bất kể dir, hãy tạo property đường dẫn đầy đủ bằng location rồi truyền property đó qua arg value.

## 3. Dùng arg value để truyền một đối số

value là cách nên ưu tiên khi truyền từng đối số riêng. Mỗi phần tử arg value biểu thị một đối số, kể cả khi giá trị chứa khoảng trắng.

Ví dụ:

~~~xml
<exec executable="report-tool" failonerror="true">
    <arg value="generate"/>
    <arg value="--title"/>
    <arg value="Monthly Sales Report"/>
    <arg value="--format"/>
    <arg value="html"/>
</exec>
~~~

Chương trình nhận năm đối số:

1. generate
2. --title
3. Monthly Sales Report
4. --format
5. html

Giá trị Monthly Sales Report là một đối số duy nhất vì nó nằm trong một phần tử arg value.

### 3.1. Không cần thêm dấu nháy kép quanh value

Ví dụ đúng:

~~~xml
<arg value="Monthly Sales Report"/>
~~~

Không nên viết:

~~~xml
<arg value="&quot;Monthly Sales Report&quot;"/>
~~~

Trong ví dụ thứ hai, dấu nháy được mã hóa thành nội dung của đối số. Chương trình có thể nhận dấu nháy như ký tự thực sự thay vì chỉ nhận phần văn bản ở giữa.

Khi dùng arg value, ranh giới đối số đã được xác định bởi cấu trúc XML. Không cần thêm dấu nháy như khi gõ lệnh trong shell.

### 3.2. Truyền đường dẫn có khoảng trắng

Giả sử project có cấu trúc:

~~~text
project/
├── build.xml
├── input files/
│   └── sales data.csv
└── build/
    └── monthly reports/
~~~

Khai báo đường dẫn:

~~~xml
<property name="input.file"
          location="input files/sales data.csv"/>
<property name="output.file"
          location="build/monthly reports/sales summary.html"/>
~~~

Truyền vào chương trình:

~~~xml
<exec executable="report-tool" failonerror="true">
    <arg value="--input"/>
    <arg value="${input.file}"/>
    <arg value="--output"/>
    <arg value="${output.file}"/>
</exec>
~~~

Mỗi đường dẫn là một đối số độc lập, dù chứa nhiều khoảng trắng. Ant không cần bạn tự nối dấu nháy kép vào giá trị.

### 3.3. Truyền đối số rỗng

Một số chương trình phân biệt giữa không có đối số và một đối số có giá trị rỗng. Nếu chương trình cần nhận chuỗi rỗng, có thể khai báo:

~~~xml
<arg value=""/>
~~~

Điều này khác với việc bỏ hẳn phần tử arg. Hãy chỉ truyền đối số rỗng khi giao diện dòng lệnh của chương trình yêu cầu.

## 4. Dùng arg line và nguyên nhân dễ tách sai

line nhận một chuỗi giống dòng lệnh rồi phân tích chuỗi đó thành nhiều đối số. Cách này có thể hữu ích với cấu hình cũ, nhưng dễ gây nhầm lẫn khi chuỗi có dấu cách, dấu nháy hoặc ký tự đặc biệt.

Ví dụ:

~~~xml
<exec executable="report-tool" failonerror="true">
    <arg line="generate --format html --title &quot;Monthly Sales Report&quot;"/>
</exec>
~~~

Ant phân tích chuỗi line thành nhiều đối số theo quy tắc tách dòng lệnh. Dấu nháy kép trong chuỗi có thể được dùng để gom các từ thành một đối số. Tuy nhiên, khi lệnh phức tạp, việc phải lồng dấu nháy XML, dấu nháy của command line và cú pháp của shell khiến cấu hình khó đọc và dễ sai.

Nên viết lại thành:

~~~xml
<exec executable="report-tool" failonerror="true">
    <arg value="generate"/>
    <arg value="--format"/>
    <arg value="html"/>
    <arg value="--title"/>
    <arg value="Monthly Sales Report"/>
</exec>
~~~

Cách viết này thể hiện ranh giới từng đối số trực tiếp trong XML.

### 4.1. Vì sao line dễ tạo lỗi?

Giả sử bạn viết:

~~~xml
<arg line="--message Build completed successfully"/>
~~~

Chuỗi này được phân tích thành nhiều đối số:

- --message
- Build
- completed
- successfully

Nếu chương trình mong đợi một giá trị duy nhất sau --message, nó có thể báo lỗi hoặc chỉ đọc từ đầu tiên.

Viết bằng value:

~~~xml
<arg value="--message"/>
<arg value="Build completed successfully"/>
~~~

Bây giờ chương trình nhận đúng một giá trị cho tùy chọn message.

### 4.2. Khi nào vẫn cần line?

Có thể gặp build file cũ sử dụng line, hoặc cần tương thích với một cấu hình command line đã có. Khi giữ lại line, hãy nhớ:

- Chuỗi được phân tích thành nhiều đối số.
- Dấu nháy dùng để nhóm từ thuộc về quy tắc phân tích của Ant.
- Dấu nháy bên ngoài của XML chỉ dùng để bao thuộc tính.
- Cú pháp của shell không tự động được áp dụng cho line.
- Không nên nối dữ liệu người dùng vào một chuỗi line rồi hy vọng việc tách luôn đúng.

Với build file mới, ưu tiên nhiều phần tử arg value riêng biệt. Chỉ dùng line khi có lý do tương thích rõ ràng và chuỗi đã được kiểm soát.

## 5. Các dạng arg khác: file, path và pathref

Ngoài value và line, Ant cung cấp những cách truyền dữ liệu phù hợp với file và path.

### 5.1. arg file

Dùng file khi đối số là đường dẫn file:

~~~xml
<exec executable="file-inspector" failonerror="true">
    <arg value="--input"/>
    <arg file="${input.file}"/>
</exec>
~~~

Đây là cách diễn đạt rõ rằng đối số tiếp theo là một file. Có thể dùng value nếu muốn truyền chính xác một chuỗi đường dẫn. Chọn một cách thống nhất trong build file để người đọc dễ nhận biết.

### 5.2. arg path

path truyền một path dưới dạng một đối số, với các phần tử được phân tách bằng ký tự phân cách path của hệ điều hành hiện tại.

Ví dụ:

~~~xml
<path id="tool.classpath">
    <pathelement location="lib/core.jar"/>
    <pathelement location="lib/reporting.jar"/>
    <pathelement location="build/classes"/>
</path>

<exec executable="java" failonerror="true">
    <arg value="-cp"/>
    <arg pathref="tool.classpath"/>
    <arg value="com.example.ReportMain"/>
</exec>
~~~

Nếu dùng trực tiếp path, có thể viết:

~~~xml
<arg path="lib/core.jar;lib/reporting.jar"/>
~~~

Tuy nhiên, dấu phân cách path khác nhau giữa các hệ điều hành. Path reference giúp Ant tự xử lý cách ghép đường dẫn phù hợp.

### 5.3. arg pathref

pathref tham chiếu đến một path đã được khai báo bằng id:

~~~xml
<path id="runtime.path">
    <pathelement location="build/classes"/>
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>

<exec executable="java" failonerror="true">
    <arg value="-classpath"/>
    <arg pathref="runtime.path"/>
    <arg value="com.example.Main"/>
</exec>
~~~

Đây là cách hữu ích khi cùng một classpath được sử dụng ở nhiều task hoặc target. Khi thư viện thay đổi, bạn cập nhật path một lần thay vì sửa từng chuỗi lệnh.

### 5.4. Path là một đối số, không phải nhiều đối số

Khi dùng:

~~~xml
<arg pathref="runtime.path"/>
~~~

Ant tạo một giá trị path đã ghép và truyền nó như một đối số. Nếu chương trình yêu cầu mỗi thư viện là một đối số riêng, hãy tạo từng phần tử arg value tương ứng thay vì dùng một path.

Cần đọc giao diện dòng lệnh của chương trình để xác định nó mong đợi một đối số classpath hay danh sách đối số riêng.

## 6. Ví dụ gọi công cụ có tùy chọn và đường dẫn phức tạp

Giả sử một công cụ đóng gói nhận các tham số:

~~~text
packager build
    --source <source-directory>
    --destination <archive-file>
    --label <release-label>
    --verbose
~~~

Build file Ant:

~~~xml
<project name="external-tool-demo" default="package" basedir=".">

    <property name="tool.executable"
              location="tools/Packager/bin/packager.exe"/>
    <property name="source.dir"
              location="build/distribution files"/>
    <property name="archive.file"
              location="dist/release candidate/application.zip"/>
    <property name="release.label"
              value="Release Candidate 2"/>

    <target name="package">
        <exec executable="${tool.executable}"
              dir="."
              failonerror="true"
              timeout="120000">
            <arg value="build"/>
            <arg value="--source"/>
            <arg value="${source.dir}"/>
            <arg value="--destination"/>
            <arg value="${archive.file}"/>
            <arg value="--label"/>
            <arg value="${release.label}"/>
            <arg value="--verbose"/>
        </exec>
    </target>

</project>
~~~

Các giá trị có khoảng trắng vẫn được truyền đúng vì mỗi giá trị nằm trong một arg value. timeout giới hạn thời gian thực thi ở 120.000 mili giây. Nếu chương trình chạy quá lâu, Ant xử lý theo cấu hình timeout của task.

Để kiểm tra đường dẫn trước khi chạy công cụ, có thể dùng task available:

~~~xml
<target name="package" depends="check-input">
    <exec executable="${tool.executable}" failonerror="true">
        <arg value="build"/>
        <arg value="--source"/>
        <arg value="${source.dir}"/>
        <arg value="--destination"/>
        <arg value="${archive.file}"/>
    </exec>
</target>

<target name="check-input">
    <available file="${source.dir}"
               type="dir"
               property="source.exists"/>
    <fail unless="source.exists"
          message="Source directory does not exist: ${source.dir}"/>
</target>
~~~

Ví dụ này minh họa việc xác nhận thư mục nguồn trước khi chạy chương trình bên ngoài. Trong build thực tế, hãy bảo đảm target tạo thư mục nguồn được khai báo trong dependency nếu thư mục đó là đầu ra của một bước trước.

## 7. Phân biệt exec với java

Ant có task java dành riêng cho việc chạy một lớp Java hoặc một module Java. Task exec dùng để chạy chương trình bên ngoài nói chung, bao gồm cả executable Java nếu bạn chủ động gọi lệnh java.

Ví dụ dùng task java:

~~~xml
<java classname="com.example.Main"
      fork="true"
      failonerror="true">
    <classpath>
        <pathelement location="build/classes"/>
    </classpath>
    <arg value="--config"/>
    <arg value="config/application settings.xml"/>
</java>
~~~

Ví dụ dùng exec để gọi Java launcher:

~~~xml
<exec executable="java" failonerror="true">
    <arg value="-cp"/>
    <arg pathref="runtime.path"/>
    <arg value="com.example.Main"/>
    <arg value="--config"/>
    <arg value="config/application settings.xml"/>
</exec>
~~~

Nếu mục tiêu là chạy lớp Java, task java thường thuận tiện hơn vì Ant hiểu trực tiếp class name, module và classpath. Dùng exec khi cần gọi một executable cụ thể hoặc cần mô phỏng chính xác cách chạy công cụ bên ngoài.

Dù dùng task nào, nguyên tắc truyền đối số vẫn giống nhau: mỗi arg value là một đối số riêng, và giá trị có dấu cách không cần tự thêm dấu nháy.

## 8. Ant không tự chạy lệnh qua shell

Một điểm quan trọng: task exec thường khởi chạy executable trực tiếp. Ant không mặc định gửi toàn bộ chuỗi qua shell để shell diễn giải các toán tử như pipe, chuyển hướng hoặc wildcard.

Ví dụ:

~~~xml
<exec executable="echo">
    <arg value="hello &amp;&amp; goodbye"/>
</exec>
~~~

Đối số được truyền cho chương trình echo. Ký tự && không tự động có nghĩa là chạy hai lệnh nối tiếp qua shell.

Tương tự, các ký tự sau không mặc nhiên được shell xử lý khi truyền trực tiếp cho executable:

- |
- >
- &
- *
- $()
- ;

Kết quả cụ thể phụ thuộc vào chương trình được gọi. Một số chương trình có thể tự diễn giải các ký tự này như cú pháp riêng, nhưng đó là hành vi của chương trình, không phải shell của hệ điều hành.

### 8.1. Nếu cần pipe hoặc chuyển hướng, phải gọi shell rõ ràng

Nếu thật sự cần shell, hãy chỉ định shell làm executable và truyền cú pháp shell cho nó.

Ví dụ trên hệ thống Unix:

~~~xml
<exec executable="sh" failonerror="true">
    <arg value="-c"/>
    <arg value="printf '%s\n' 'build started' | tee build.log"/>
</exec>
~~~

Ở đây sh là executable. Đối số thứ nhất là -c, đối số thứ hai là toàn bộ chuỗi lệnh mà shell sẽ phân tích.

Trên Windows, có thể gọi cmd.exe với /c, nhưng quy tắc quote và escape của cmd khác shell Unix:

~~~xml
<exec executable="cmd.exe" failonerror="true">
    <arg value="/d"/>
    <arg value="/c"/>
    <arg value="echo Build started"/>
</exec>
~~~

/d tắt việc chạy các lệnh AutoRun của cmd, còn /c yêu cầu cmd thực hiện chuỗi lệnh rồi thoát. Với pipeline Windows phức tạp, nên đặt lệnh vào file .cmd hoặc .bat riêng và gọi file đó bằng Ant thay vì xây dựng một chuỗi quote lồng nhiều tầng.

### 8.2. Không ghép dữ liệu không tin cậy vào shell command

Khi gọi sh -c hoặc cmd /c, shell sẽ phân tích chuỗi lệnh. Nếu chèn dữ liệu tùy ý từ bên ngoài vào chuỗi này, ký tự đặc biệt có thể biến thành cú pháp lệnh.

Ví dụ, một tên file chứa dấu chấm phẩy hoặc dấu & có thể làm thay đổi cách shell diễn giải chuỗi nếu được nối trực tiếp vào command.

Khi chỉ cần truyền dữ liệu cho chương trình, hãy gọi executable trực tiếp và dùng từng arg value. Chỉ dùng shell khi thực sự cần tính năng của shell và dữ liệu đưa vào chuỗi shell đã được kiểm soát hoặc xử lý đúng theo quy tắc của shell đó.

## 9. Ký tự đặc biệt trong XML và trong đối số

Có hai lớp cú pháp cần phân biệt:

1. Cú pháp XML dùng để đọc build file.
2. Cách chương trình đích diễn giải đối số sau khi Ant truyền nó.

Một số ký tự phải được escape trong XML:

| Ký tự muốn truyền | Cách viết trong thuộc tính XML |
|---|---|
| & | &amp; |
| < | &lt; |
| > | &gt; |
| " bên trong giá trị được bao bằng " | &quot; |
| ' | &apos; (khi cần) |

Ví dụ:

~~~xml
<exec executable="search-tool" failonerror="true">
    <arg value="--query"/>
    <arg value="sales &amp; inventory"/>
    <arg value="--expression"/>
    <arg value="amount &gt; 100"/>
</exec>
~~~

Sau khi XML được phân tích, chương trình nhận nội dung có dấu & và > như các ký tự bình thường trong đối số.

Escape XML không giống escape shell. &amp; giúp XML hợp lệ; nó không biến & thành một toán tử hoặc ký tự đặc biệt theo quy tắc của shell.

### 9.1. Dấu nháy là dữ liệu hay cú pháp?

Khi viết:

~~~xml
<arg value="A report for finance"/>
~~~

Dấu nháy kép ở hai đầu chỉ là dấu phân cách thuộc tính XML, không nằm trong đối số.

Nếu chương trình thực sự cần nhận dấu nháy kép như ký tự dữ liệu, bạn có thể viết:

~~~xml
<arg value="&quot;A report for finance&quot;"/>
~~~

Khi đó, giá trị đối số bao gồm cả hai dấu nháy kép. Chỉ làm điều này nếu giao diện chương trình yêu cầu dấu nháy là một phần của dữ liệu.

## 10. Kiểm soát mã thoát của chương trình

Một chương trình bên ngoài thường trả về mã thoát (exit code). Theo quy ước phổ biến, mã 0 biểu thị thành công và mã khác 0 biểu thị một trạng thái lỗi hoặc kết quả đặc biệt. Tuy nhiên, ý nghĩa cụ thể phụ thuộc vào chương trình.

### 10.1. Dùng failonerror để dừng build

Nếu mọi mã thoát khác 0 đều được xem là lỗi, đặt:

~~~xml
<exec executable="validator"
      failonerror="true">
    <arg value="--check"/>
    <arg value="build/classes"/>
</exec>
~~~

Khi chương trình trả mã khác 0, Ant báo lỗi và build không tiếp tục target theo luồng thông thường.

Đây là lựa chọn phù hợp với compiler, formatter hoặc công cụ đóng gói mà lỗi thực thi cần làm build thất bại.

### 10.2. Lấy mã thoát bằng resultproperty

Có trường hợp mã thoát khác 0 là một kết quả có ý nghĩa chứ không phải lỗi nghiêm trọng. Khi đó, đặt failonerror="false" và nhận mã thoát bằng resultproperty:

~~~xml
<exec executable="validator"
      failonerror="false"
      resultproperty="validator.exit.code">
    <arg value="--check"/>
    <arg value="build/classes"/>
</exec>
~~~

Sau đó kiểm tra mã thoát:

~~~xml
<target name="verify-validator">
    <exec executable="validator"
          failonerror="false"
          resultproperty="validator.exit.code">
        <arg value="--check"/>
        <arg value="build/classes"/>
    </exec>

    <condition property="validator.passed">
        <equals arg1="${validator.exit.code}" arg2="0"/>
    </condition>

    <fail unless="validator.passed"
          message="Validator reported a problem. Exit code: ${validator.exit.code}"/>
</target>
~~~

Trong ví dụ này, Ant tự quyết định build có thất bại hay không dựa trên property được tạo từ mã thoát.

Lưu ý rằng property Ant thông thường chỉ được đặt một lần trong một project. Nếu target có thể được chạy nhiều lần với kết quả khác nhau trong cùng một lượt build, không nên dựa vào việc ghi đè cùng một resultproperty.

### 10.3. Phân biệt không khởi chạy được với chương trình trả lỗi

Có hai tình huống khác nhau:

- **Không thể khởi chạy executable**: ví dụ đường dẫn sai, file không tồn tại hoặc hệ điều hành từ chối khởi chạy.
- **Executable đã chạy nhưng trả mã khác 0**: chương trình thực thi và chủ động trả về trạng thái lỗi hoặc kết quả đặc biệt.

failifexecutionfails điều khiển hành vi khi Ant không thể khởi chạy tiến trình. failonerror điều khiển phản ứng với mã thoát khác 0.

Ví dụ cấu hình rõ ràng:

~~~xml
<exec executable="${tool.executable}"
      failifexecutionfails="true"
      failonerror="true">
    <arg value="--version"/>
</exec>
~~~

Nếu công cụ bắt buộc phải có, hãy để lỗi không khởi chạy làm build thất bại. Nếu công cụ là tùy chọn, có thể chọn chính sách khác và kiểm tra sự tồn tại của executable trước khi gọi.

## 11. Thu thập standard output và standard error

Khi chạy công cụ bên ngoài, bạn có thể muốn lưu thông tin chương trình in ra để chẩn đoán hoặc dùng trong bước tiếp theo.

### 11.1. Ghi output vào file

~~~xml
<exec executable="compiler"
      failonerror="true"
      output="build/logs/compiler.out"
      error="build/logs/compiler.err">
    <arg value="--compile"/>
    <arg value="src"/>
</exec>
~~~

output nhận standard output, còn error nhận standard error. Hãy tạo thư mục log trước khi chạy:

~~~xml
<mkdir dir="build/logs"/>
~~~

### 11.2. Lưu output vào property

Có thể dùng outputproperty và errorproperty:

~~~xml
<exec executable="version-tool"
      failonerror="true"
      outputproperty="tool.version.text"
      errorproperty="tool.version.error">
    <arg value="--version"/>
</exec>

<echo message="Tool information: ${tool.version.text}"/>
~~~

Cách này hữu ích khi output ngắn và cần dùng tiếp trong build. Với output lớn, hãy ghi ra file để tránh đưa nội dung dài vào property và log.

Standard output và standard error là hai luồng khác nhau. Một số chương trình ghi thông báo tiến độ vào stderr dù thao tác thành công, nên không nên mặc định rằng stderr luôn có nghĩa chương trình thất bại.

## 12. Biến môi trường và thư mục làm việc

Một tiến trình con kế thừa môi trường của Ant theo cấu hình mặc định. Bạn có thể bổ sung hoặc ghi đè biến môi trường bằng phần tử env.

Ví dụ:

~~~xml
<exec executable="node"
      dir="."
      failonerror="true">
    <env key="NODE_ENV" value="production"/>
    <env key="BUILD_LABEL" value="release candidate"/>
    <arg value="scripts/build.js"/>
    <arg value="--output"/>
    <arg value="build/web assets"/>
</exec>
~~~

Trong ví dụ, Node chạy trong thư mục project, nhận hai biến môi trường và các đối số được truyền riêng.

Thuộc tính newenvironment ảnh hưởng đến việc kế thừa môi trường hiện tại. Nếu đặt newenvironment="true", tiến trình sử dụng môi trường được khai báo mới thay vì mặc định kế thừa toàn bộ môi trường của Ant. Khi dùng chế độ này, cần khai báo đủ biến môi trường mà công cụ cần, chẳng hạn PATH nếu chương trình phụ thuộc vào các executable khác.

Không nên đặt newenvironment="true" nếu bạn chỉ muốn thêm một hoặc hai biến. Mặc định kế thừa môi trường rồi bổ sung các phần tử env thường đơn giản hơn.

## 13. Xử lý timeout và tiến trình chạy nền

### 13.1. Giới hạn thời gian chạy

Có thể đặt timeout để tránh build bị treo vô thời hạn:

~~~xml
<exec executable="integration-test-runner"
      timeout="300000"
      failonerror="true">
    <arg value="--suite"/>
    <arg value="smoke"/>
</exec>
~~~

Giá trị 300000 là 300.000 mili giây, tương đương 5 phút.

Chọn timeout dựa trên thời gian chạy bình thường của công cụ và môi trường CI. Timeout quá ngắn có thể làm build thất bại giả; timeout quá dài làm chậm việc phát hiện tiến trình bị treo.

### 13.2. spawn chạy tiến trình tách khỏi Ant

Thuộc tính spawn="true" yêu cầu Ant khởi chạy tiến trình theo cách không chờ tiến trình hoàn tất như thông thường. Cách này phù hợp với một số chương trình nền cần tiếp tục chạy sau khi Ant chuyển sang bước khác.

Ví dụ:

~~~xml
<exec executable="local-server"
      spawn="true">
    <arg value="--port"/>
    <arg value="8080"/>
</exec>
~~~

Khi dùng spawn, Ant không thể theo dõi kết quả hoàn tất theo cách thông thường. Không nên dùng spawn cho compiler, test runner hoặc công cụ đóng gói mà target tiếp theo cần biết chắc tiến trình đã hoàn thành.

Nếu cần khởi chạy server cho integration test, phải có cách chờ server sẵn sàng và dừng server sau khi test. Chỉ đặt spawn rồi chạy test ngay có thể dẫn đến lỗi do server chưa khởi động xong.

## 14. Các lỗi tách đối số thường gặp

### 14.1. Một giá trị bị tách thành nhiều đối số

Nguyên nhân: dùng line với chuỗi có khoảng trắng mà không nhóm các từ theo đúng cú pháp.

Cách khắc phục: dùng một arg value cho mỗi đối số cần truyền.

### 14.2. Đường dẫn chứa khoảng trắng bị hiểu sai

Nguyên nhân: ghép đường dẫn vào một chuỗi command line và để parser tách theo dấu cách.

Cách khắc phục:

~~~xml
<arg value="${output.file}"/>
~~~

Không cần tự nối dấu nháy kép vào giá trị.

### 14.3. Đưa cả đối số vào executable

Nguyên nhân: viết executable thành tool --option value.

Cách khắc phục: chỉ đặt tên chương trình trong executable, sau đó khai báo từng đối số bằng arg.

### 14.4. Nhầm cú pháp XML với cú pháp shell

Nguyên nhân: cho rằng &amp;, dấu nháy hoặc dấu > trong XML có cùng ý nghĩa với shell.

Cách khắc phục: escape XML để build file hợp lệ; chỉ gọi shell khi thật sự cần shell diễn giải toán tử.

### 14.5. Dùng wildcard nhưng mong shell tự mở rộng

Khi gọi trực tiếp executable, chuỗi *.jar thường được truyền nguyên vẹn cho chương trình. Shell không tự mở rộng wildcard nếu Ant không gọi shell.

Nếu muốn truyền danh sách file cụ thể, hãy dùng fileset hoặc path để Ant xác định danh sách, rồi xây dựng đối số theo định dạng mà công cụ đích yêu cầu.

### 14.6. Lệnh chạy được trên máy phát triển nhưng thất bại trên CI

Một số nguyên nhân:

- executable không nằm trong PATH của CI.
- Đường dẫn tương đối được tính từ thư mục làm việc khác.
- Tên file hoặc thư mục có khoảng trắng.
- Công cụ phụ thuộc biến môi trường chưa được thiết lập.
- Dấu phân cách path khác nhau giữa Windows và Unix.
- Phiên bản công cụ trên CI khác với máy phát triển.

Hãy dùng property location cho đường dẫn quan trọng, đặt dir rõ ràng và kiểm tra executable trong môi trường CI.

### 14.7. Dùng sai mã thoát

Một số chương trình dùng mã thoát khác 0 cho kết quả như không có thay đổi hoặc không tìm thấy. Nếu failonerror="true", Ant sẽ xem đó là lỗi build.

Hãy đọc tài liệu của chương trình để hiểu mã thoát. Nếu mã khác 0 là trạng thái hợp lệ, dùng resultproperty và kiểm tra rõ từng trường hợp.

## 15. Mẫu build file thực tế

Ví dụ sau kết hợp executable, đối số có khoảng trắng, path reference, output, mã thoát và dependency giữa các target.

~~~xml
<project name="external-command-build" default="verify" basedir=".">

    <property name="tool.executable"
              location="tools/Report Generator/report.exe"/>
    <property name="input.file"
              location="data/monthly sales.csv"/>
    <property name="output.file"
              location="build/reports/monthly summary.html"/>
    <property name="log.dir"
              location="build/logs"/>

    <path id="tool.runtime.path">
        <pathelement location="lib/report-core.jar"/>
        <pathelement location="lib/report-format.jar"/>
    </path>

    <target name="prepare">
        <mkdir dir="${log.dir}"/>
        <mkdir dir="build/reports"/>
    </target>

    <target name="run-report" depends="prepare">
        <exec executable="${tool.executable}"
              dir="."
              failifexecutionfails="true"
              failonerror="true"
              timeout="180000"
              output="${log.dir}/report.out"
              error="${log.dir}/report.err">
            <arg value="generate"/>
            <arg value="--input"/>
            <arg file="${input.file}"/>
            <arg value="--output"/>
            <arg file="${output.file}"/>
            <arg value="--classpath"/>
            <arg pathref="tool.runtime.path"/>
            <arg value="--title"/>
            <arg value="Monthly Sales Summary"/>
        </exec>
    </target>

    <target name="verify" depends="run-report">
        <available file="${output.file}"
                   type="file"
                   property="report.exists"/>
        <fail unless="report.exists"
              message="Report was not created: ${output.file}"/>
        <echo message="Report created: ${output.file}"/>
    </target>

</project>
~~~

Luồng xử lý:

~~~text
prepare
   |
   v
run-report
   |
   v
verify
~~~

Target prepare tạo thư mục đầu ra. Target run-report gọi chương trình bên ngoài với các đối số riêng biệt và ghi log. Target verify kiểm tra file báo cáo đã được tạo.

Các đường dẫn chứa dấu cách vẫn là một đối số nhờ arg file. Classpath được ghép theo quy tắc path của hệ điều hành bằng pathref. Nếu công cụ báo lỗi hoặc trả mã thoát khác 0, Ant dừng ở target run-report.

Các đường dẫn JAR và executable trong ví dụ chỉ là cấu trúc minh họa. Hãy thay bằng vị trí công cụ thực tế của dự án.

## 16. Quy trình lựa chọn cách truyền đối số

Khi viết một task exec, có thể làm theo trình tự:

1. Xác định chính xác executable cần chạy.
2. Đặt executable riêng trong thuộc tính executable.
3. Liệt kê các đối số theo đúng thứ tự mà chương trình yêu cầu.
4. Dùng một arg value cho mỗi đối số.
5. Dùng arg file cho đường dẫn file hoặc arg pathref cho danh sách path.
6. Dùng property location cho đường dẫn cần ổn định và tránh phụ thuộc thư mục hiện tại.
7. Đặt dir nếu chương trình cần chạy trong một thư mục cụ thể.
8. Chọn failonerror hoặc resultproperty theo ý nghĩa mã thoát của chương trình.
9. Chỉ gọi shell nếu cần pipe, redirect hoặc tính năng shell khác.
10. Nếu dùng shell, truyền chuỗi lệnh như một đối số riêng cho shell và tránh ghép dữ liệu không tin cậy vào chuỗi đó.
11. Chạy build trên hệ điều hành mục tiêu để xác nhận executable, đường dẫn, biến môi trường và quy tắc phân tách path.

Điểm quan trọng nhất là giữ ranh giới giữa executable và từng argument rõ ràng trong build file. Khi cấu hình được biểu diễn thành các phần tử XML riêng, bạn có thể đọc, sửa và chẩn đoán lệnh mà không phải tự phân tích một chuỗi command line dài.

## 17. Ghi nhớ

- Task exec chạy một chương trình bên ngoài Ant.
- executable chỉ chứa tên hoặc đường dẫn chương trình, còn đối số được khai báo riêng.
- Mỗi arg value truyền một đối số duy nhất, kể cả khi giá trị chứa dấu cách.
- arg line phân tích một chuỗi thành nhiều đối số và dễ gây lỗi khi có nhiều tầng quote; ưu tiên các phần tử arg value.
- arg file phù hợp với đường dẫn file; arg path và arg pathref truyền danh sách đường dẫn theo quy tắc hệ điều hành.
- dir đặt thư mục làm việc của tiến trình con.
- Ant không mặc định dùng shell để diễn giải pipe, redirect, wildcard hoặc toán tử.
- Ký tự đặc biệt phải được escape đúng ở lớp XML; điều đó không thay thế quy tắc escape của shell.
- failonerror xử lý mã thoát khác 0; failifexecutionfails xử lý trường hợp không khởi chạy được chương trình.
- resultproperty, outputproperty và errorproperty giúp thu thập kết quả từ tiến trình.
- Chỉ dùng spawn khi không cần chờ tiến trình hoàn tất theo luồng thông thường.
- Khi cần shell, gọi shell rõ ràng và kiểm soát nội dung command string.

Khi truyền đối số bằng các phần tử arg riêng, build file Ant sẽ ít gặp lỗi do tách chuỗi, xử lý đường dẫn có khoảng trắng ổn định hơn và dễ chạy nhất quán giữa máy phát triển với môi trường CI.

