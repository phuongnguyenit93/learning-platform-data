# Đếm và biểu diễn tập tài nguyên bằng resourcecount và pathconvert

Trong Apache Ant, nhiều task làm việc với một tập tài nguyên (resource collection) thay vì nhận từng tệp riêng lẻ. Ví dụ, một FileSet có thể chọn các tệp Java trong thư mục nguồn, còn một Path có thể tập hợp thư mục class và các thư viện JAR cần cho quá trình biên dịch.

Khi build cần biết tập tài nguyên có bao nhiêu phần tử hoặc cần chuyển một Path thành chuỗi để hiển thị, truyền cho công cụ bên ngoài hay ghi vào báo cáo, Ant cung cấp hai task chuyên dụng:

- **resourcecount** đếm số resource trong một resource collection và lưu kết quả vào property.
- **pathconvert** chuyển một Path hoặc cấu trúc đường dẫn thành chuỗi, cho phép điều chỉnh dấu phân cách và ánh xạ đường dẫn.

Hai task có mục đích khác nhau: một task trả lời câu hỏi “có bao nhiêu resource?”, task còn lại trả lời “biểu diễn đường dẫn của các resource thành chuỗi như thế nào?”. Kết hợp chúng giúp build file quan sát và truyền thông tin về tập đầu vào một cách rõ ràng.

## 1. Resource collection và Path trong Ant

Trước khi dùng hai task, cần phân biệt resource collection với Path.

**Resource collection** là một tập hợp các resource mà task Ant có thể duyệt. Resource có thể là tệp, thư mục hoặc một loại tài nguyên được cung cấp bởi collection tương ứng. Những collection thường gặp gồm:

- **FileSet**: chọn các tệp theo thư mục gốc và include/exclude pattern.
- **FileList**: liệt kê một danh sách đường dẫn tệp cụ thể.
- **Path**: tập hợp các phần tử đường dẫn, thường dùng cho classpath hoặc danh sách thư viện.
- **ZipFileSet**: chọn các mục bên trong tệp ZIP/JAR theo cấu hình của collection.

Ví dụ một FileSet chọn mã nguồn Java:

~~~xml
<fileset id="java.sources" dir="src/main/java">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
</fileset>
~~~

Một Path có thể tập hợp thư mục class và các thư viện:

~~~xml
<path id="compile.path">
    <pathelement location="build/classes"/>
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>
~~~

Trong ví dụ, Path có một phần tử trỏ đến thư mục class và các phần tử được lấy từ những tệp JAR trong thư mục **lib**.

Path là cấu trúc có ý nghĩa đặc biệt với các task nhận classpath hoặc danh sách đường dẫn. Nó có thể được tham chiếu lại bằng **refid**, tránh phải khai báo cùng một danh sách nhiều lần.

## 2. Đếm resource với resourcecount

Task **resourcecount** đếm số resource mà collection lồng bên trong cung cấp và đặt kết quả vào property được chỉ định bằng thuộc tính **property**.

Cú pháp cơ bản:

~~~xml
<resourcecount property="source.count">
    <fileset dir="src/main/java">
        <include name="**/*.java"/>
    </fileset>
</resourcecount>
~~~

Sau khi task thực thi, property **source.count** chứa số lượng resource được chọn bởi FileSet.

Có thể dùng kết quả trong thông điệp:

~~~xml
<target name="inspect-sources">
    <resourcecount property="source.count">
        <fileset dir="src/main/java">
            <include name="**/*.java"/>
        </fileset>
    </resourcecount>

    <echo message="Found ${source.count} Java source resources."/>
</target>
~~~

Nếu thư mục có 12 tệp Java phù hợp, thông điệp sẽ hiển thị số 12. Nếu collection rỗng, kết quả đếm là 0.

### Đếm nhiều loại resource

ResourceCount nhận một resource collection. Vì vậy, có thể đếm resource được tạo từ Path hoặc các collection khác, không chỉ FileSet:

~~~xml
<resourcecount property="compile.entries">
    <path refid="compile.path"/>
</resourcecount>
~~~

Ở đây, task đếm số phần tử resource trong Path đã định nghĩa. Nếu Path chứa thư mục class và ba JAR, số đếm tương ứng là số resource mà Path cung cấp trong cấu hình đó.

Cần hiểu đúng ý nghĩa của con số: ResourceCount đếm **resource trong collection**, không đo kích thước dữ liệu, số dòng mã, số class bên trong JAR hoặc số byte. Muốn đếm tệp nguồn, hãy truyền FileSet chọn đúng các tệp nguồn; muốn đếm các mục đường dẫn, hãy truyền Path tương ứng.

### Đếm tập tệp sau include và exclude

Số lượng được tính trên collection sau khi các quy tắc chọn resource được áp dụng:

~~~xml
<resourcecount property="production.java.count">
    <fileset dir="src">
        <include name="**/*.java"/>
        <exclude name="**/*Test.java"/>
        <exclude name="**/generated/**"/>
    </fileset>
</resourcecount>
~~~

Task không đếm mọi tệp trong thư mục **src** rồi trừ bằng cách thủ công. FileSet tự xác định tập kết quả theo include/exclude; ResourceCount đếm chính tập kết quả đó.

## 3. Property kết quả và tính chất chỉ thiết lập một lần

ResourceCount ghi kết quả vào property. Property chuẩn của Ant có tính chất bất biến sau khi được thiết lập: một property đã tồn tại thường không bị khai báo hoặc task sau ghi đè.

Vì vậy, nếu property đã có giá trị từ trước, chạy ResourceCount với cùng tên property không đảm bảo thay đổi giá trị đó. Nên chọn tên property riêng cho mỗi phép đếm hoặc bảo đảm property chưa được thiết lập trước khi task chạy.

Ví dụ:

~~~xml
<target name="count-java">
    <resourcecount property="java.source.count">
        <fileset dir="src">
            <include name="**/*.java"/>
        </fileset>
    </resourcecount>
    <echo message="Java files: ${java.source.count}"/>
</target>
~~~

Nếu cùng một phép đếm cần thực hiện với các bộ đầu vào khác nhau trong một lượt build, hãy dùng property khác nhau:

~~~xml
<resourcecount property="main.source.count">
    <fileset dir="src/main">
        <include name="**/*.java"/>
    </fileset>
</resourcecount>

<resourcecount property="test.source.count">
    <fileset dir="src/test">
        <include name="**/*.java"/>
    </fileset>
</resourcecount>
~~~

Cách đặt tên này giúp kết quả dễ đọc và tránh nhầm lẫn giữa các tập resource.

### Dùng kết quả đếm trong điều kiện

Có thể sử dụng property đếm làm đầu vào cho task **condition**. Ví dụ, tạo property báo có mã nguồn nếu số lượng lớn hơn 0:

~~~xml
<resourcecount property="source.count">
    <fileset dir="src/main/java">
        <include name="**/*.java"/>
    </fileset>
</resourcecount>

<condition property="has.sources">
    <not>
        <equals arg1="${source.count}" arg2="0"/>
    </not>
</condition>

<target name="compile" if="has.sources">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>
~~~

Property **has.sources** chỉ được thiết lập khi số đếm khác 0. Điều kiện **if** của target kiểm tra sự tồn tại của property đó.

Lưu ý rằng điều kiện **if** trên target kiểm tra property có tồn tại hay không, không đọc chuỗi **true/false** như một biểu thức boolean tổng quát. Trong ví dụ, cách dùng **condition** tạo property chỉ khi điều kiện đúng nên phù hợp với quy tắc này.

## 4. Chuyển Path thành chuỗi với pathconvert

Path là cấu trúc dữ liệu. Khi cần in danh sách đường dẫn, truyền nó cho một task chỉ nhận chuỗi hoặc ghi vào một property để dùng ở nơi khác, có thể dùng **pathconvert**.

Cú pháp cơ bản:

~~~xml
<path id="runtime.path">
    <pathelement location="build/classes"/>
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>

<pathconvert property="runtime.path.text">
    <path refid="runtime.path"/>
</pathconvert>
~~~

Task chuyển các phần tử của Path thành một chuỗi và lưu vào property **runtime.path.text**. Mặc định, dấu phân cách phần tử và dấu phân cách thư mục phù hợp với hệ điều hành đang chạy Ant.

Có thể hiển thị kết quả:

~~~xml
<echo message="Runtime path: ${runtime.path.text}"/>
~~~

Điều này hữu ích khi chẩn đoán classpath hoặc ghi lại danh sách thư viện được sử dụng trong một lượt build.

### Path separator và directory separator

Có hai loại dấu phân cách cần phân biệt:

- **pathsep**: dấu phân cách giữa các phần tử đường dẫn trong chuỗi. Trên Windows thường là dấu chấm phẩy (**;**); trên Unix-like thường là dấu hai chấm (**:**).
- **dirsep**: dấu phân cách giữa các cấp thư mục trong một đường dẫn. Trên Windows thường là dấu gạch chéo ngược (**\\**); trên Unix-like thường là dấu gạch chéo xuôi (**/**).

Có thể chỉ định trực tiếp:

~~~xml
<pathconvert property="path.for.unix"
              pathsep=":"
              dirsep="/">
    <path refid="runtime.path"/>
</pathconvert>
~~~

Hoặc dùng thuộc tính **targetos** để chọn quy ước đường dẫn đích:

~~~xml
<pathconvert property="path.for.windows" targetos="windows">
    <path refid="runtime.path"/>
</pathconvert>

<pathconvert property="path.for.unix" targetos="unix">
    <path refid="runtime.path"/>
</pathconvert>
~~~

**targetos** cho phép yêu cầu cách biểu diễn phù hợp với Windows hoặc Unix. Khi dùng **targetos**, Ant chọn các dấu phân cách tương ứng. Nếu chỉ định riêng **pathsep** hoặc **dirsep**, có thể kiểm soát từng loại dấu phân cách theo yêu cầu cụ thể.

Không nên mặc định chuỗi tạo ra bởi PathConvert luôn phù hợp với mọi công cụ bên ngoài. Một ứng dụng có thể yêu cầu quy ước riêng; hãy chọn separator phù hợp với nơi nhận chuỗi.

## 5. Chuyển đổi đường dẫn bằng map

PathConvert hỗ trợ phần tử lồng **map** để thay thế một tiền tố đường dẫn bằng tiền tố khác trong chuỗi kết quả.

Ví dụ, build chạy trong workspace tại một vị trí cục bộ nhưng báo cáo cần hiển thị đường dẫn chuẩn của máy CI:

~~~xml
<path id="source.path">
    <pathelement location="${basedir}/src/main/java"/>
    <pathelement location="${basedir}/src/main/resources"/>
</path>

<pathconvert property="ci.source.path" targetos="unix">
    <path refid="source.path"/>
    <map from="${basedir}" to="/workspace/inventory"/>
</pathconvert>
~~~

Nếu **basedir** trên máy developer là một thư mục như **D:/work/inventory**, phần tiền tố đó được thay bằng **/workspace/inventory** trong giá trị được chuyển đổi. Việc này hữu ích khi tạo báo cáo, cấu hình hoặc thông tin đường dẫn cần thống nhất giữa các môi trường.

Map chỉ biến đổi cách biểu diễn phần tử đường dẫn trong kết quả của PathConvert. Nó không di chuyển tệp, không tạo thư mục đích và không thay đổi vị trí thật của tài nguyên trên filesystem.

Có thể dùng nhiều map khi cần ánh xạ nhiều tiền tố:

~~~xml
<pathconvert property="mapped.path" targetos="unix">
    <path refid="runtime.path"/>
    <map from="D:/agent/work/app" to="/workspace/app"/>
    <map from="D:/agent/cache" to="/cache"/>
</pathconvert>
~~~

Khi xây dựng ánh xạ, cần đảm bảo tiền tố nguồn phản ánh đúng đường dẫn thực tế và không tạo ra kết quả mơ hồ. Hãy kiểm tra giá trị cuối cùng bằng **echo** trước khi truyền nó cho công cụ khác.

## 6. Xử lý Path rỗng với setonempty

Nếu Path không có phần tử, PathConvert mặc định không thiết lập property đầu ra. Điều này khác với một property đã được thiết lập thành chuỗi rỗng.

Có thể yêu cầu task thiết lập property ngay cả khi kết quả rỗng bằng **setonempty="true"**:

~~~xml
<pathconvert property="optional.path.text" setonempty="true">
    <path/>
</pathconvert>
~~~

Khi đó, property được tạo với giá trị chuỗi rỗng nếu Path không có phần tử. Nếu giữ mặc định, property có thể không tồn tại và tham chiếu sau đó cần xử lý trường hợp này.

Ví dụ, khi ghi log, có thể dùng **setonempty** để đảm bảo property luôn tồn tại:

~~~xml
<pathconvert property="runtime.path.text" setonempty="true">
    <path refid="runtime.path"/>
</pathconvert>

<echo message="Runtime path: [${runtime.path.text}]"/>
~~~

Cặp dấu ngoặc vuông giúp dễ nhận ra chuỗi rỗng trong log. Nếu property không tồn tại, Ant có thể giữ nguyên biểu thức tham chiếu hoặc xử lý theo ngữ cảnh khác; do đó, khi đầu vào có thể rỗng, nên quyết định rõ có cần tạo property rỗng hay không.

Với ResourceCount, một collection rỗng vẫn có số lượng bằng 0. Với PathConvert, việc có thiết lập property khi chuỗi kết quả rỗng hay không được điều khiển bởi **setonempty**.

## 7. Kết hợp resourcecount và pathconvert

Hai task có thể cùng làm việc trên một cấu trúc Path để cung cấp cả số lượng và chuỗi biểu diễn.

~~~xml
<project name="inventory" default="inspect" basedir=".">

    <path id="runtime.path">
        <pathelement location="build/classes"/>
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
    </path>

    <target name="inspect"
            description="Hiển thị số lượng và danh sách resource">

        <resourcecount property="runtime.resource.count">
            <path refid="runtime.path"/>
        </resourcecount>

        <pathconvert property="runtime.path.text"
                     targetos="unix"
                     setonempty="true">
            <path refid="runtime.path"/>
        </pathconvert>

        <echo message="Resource count: ${runtime.resource.count}"/>
        <echo message="Runtime path: ${runtime.path.text}"/>
    </target>

</project>
~~~

Khi chạy **ant inspect**:

1. Ant tạo Path từ thư mục class và các JAR trong thư mục **lib**.
2. ResourceCount đếm số phần tử mà Path cung cấp.
3. PathConvert chuyển Path thành chuỗi dùng separator kiểu Unix.
4. Hai property được in ra để người phát triển kiểm tra.

Nếu có một thư mục class và ba JAR, số lượng resource tương ứng là bốn phần tử. Chuỗi đường dẫn chứa các phần tử được ngăn cách theo quy ước đã chọn.

Ví dụ này cho thấy hai task bổ sung thông tin cho nhau: số đếm cho biết quy mô tập resource, còn chuỗi đường dẫn cho biết những vị trí được đưa vào tập đó.

## 8. Dùng với FileSet để quan sát đầu vào build

Một tình huống phổ biến là cần biết có bao nhiêu tệp nguồn trước khi biên dịch, đồng thời tạo danh sách đường dẫn để ghi log.

~~~xml
<project name="source-inspection" default="inspect" basedir=".">

    <path id="source.path">
        <pathelement location="src/main/java"/>
        <pathelement location="src/main/resources"/>
    </path>

    <target name="inspect"
            description="Đếm và hiển thị tài nguyên nguồn">

        <resourcecount property="java.count">
            <fileset dir="src/main/java">
                <include name="**/*.java"/>
                <exclude name="**/generated/**"/>
            </fileset>
        </resourcecount>

        <resourcecount property="resource.count">
            <fileset dir="src/main/resources"/>
        </resourcecount>

        <pathconvert property="source.path.text"
                     targetos="unix">
            <path refid="source.path"/>
        </pathconvert>

        <echo message="Java source files: ${java.count}"/>
        <echo message="Resource files: ${resource.count}"/>
        <echo message="Source roots: ${source.path.text}"/>
    </target>

</project>
~~~

Ở đây có ba góc nhìn:

- **java.count** đếm các tệp Java sau khi loại thư mục generated.
- **resource.count** đếm các resource được FileSet trong thư mục tài nguyên cung cấp.
- **source.path.text** biểu diễn các thư mục gốc nguồn thành chuỗi.

Không nên nhầm **source.path.text** với danh sách từng tệp Java. Path trên chỉ chứa hai thư mục gốc đã khai báo; nó không tự mở rộng thành mọi tệp con. Muốn đếm từng tệp, dùng FileSet trong ResourceCount như ví dụ đầu.

## 9. Phân biệt chuỗi đường dẫn với cấu trúc Path

PathConvert tạo ra một property dạng chuỗi. Sau khi chuyển đổi, Ant không còn giữ property đó như một đối tượng Path có cấu trúc để các task có thể tự động duyệt từng phần tử.

Nếu task tiếp theo nhận thuộc tính **path** hoặc **classpath**, nên truyền trực tiếp Path bằng **refid** hoặc nested Path khi có thể:

~~~xml
<path id="compile.path">
    <pathelement location="build/classes"/>
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>

<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <classpath refid="compile.path"/>
</javac>
~~~

Nếu chỉ cần log, hiển thị hoặc truyền sang một công cụ nhận chuỗi, PathConvert là phù hợp:

~~~xml
<pathconvert property="compile.path.text" targetos="windows">
    <path refid="compile.path"/>
</pathconvert>
<echo message="Compile path: ${compile.path.text}"/>
~~~

Việc giữ Path dưới dạng cấu trúc cho task Ant giúp tránh tự ghép chuỗi separator và giảm lỗi khi đường dẫn chứa khoảng trắng hoặc khác biệt giữa hệ điều hành. Chỉ chuyển thành chuỗi tại ranh giới cần biểu diễn văn bản.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| ResourceCount trả về 0 | FileSet không khớp pattern, sai thư mục gốc hoặc tất cả tệp bị exclude | Kiểm tra **dir**, include/exclude và tên tệp |
| Số đếm nhỏ hơn mong đợi | Collection chỉ chứa một phần đầu vào hoặc các phần tử bị lọc | Xem lại resource collection thực tế được lồng vào task |
| Property đếm giữ giá trị cũ | Property đã được thiết lập trước đó | Dùng tên property riêng hoặc sắp xếp nguồn cấu hình |
| PathConvert không tạo property | Path rỗng và **setonempty** chưa bật | Bật **setonempty="true"** nếu cần property rỗng |
| Chuỗi đường dẫn dùng sai dấu phân cách | Dùng mặc định của hệ điều hành hiện tại trong khi công cụ đích yêu cầu quy ước khác | Chỉ định **targetos**, **pathsep** hoặc **dirsep** |
| Chuỗi đường dẫn không đúng vị trí mong muốn | Các phần tử Path được khai báo với đường dẫn tương đối hoặc map sai tiền tố | Kiểm tra **basedir**, **location** và các phần tử map |
| Dùng chuỗi PathConvert cho task cần Path | Đã chuyển cấu trúc thành chuỗi và mất ngữ nghĩa collection | Truyền Path qua **refid** hoặc nested Path trực tiếp |

Khi kết quả không như mong đợi, nên kiểm tra lần lượt:

1. Collection có đúng thư mục gốc và pattern không?
2. ResourceCount đang đếm FileSet, Path hay collection nào?
3. Property đích đã được thiết lập trước đó chưa?
4. PathConvert đang dùng separator mặc định hay đã chỉ định target OS?
5. Path có rỗng không và **setonempty** có phù hợp không?
6. Nếu dùng map, tiền tố nguồn có khớp các phần tử đường dẫn không?

## 11. Nguyên tắc sử dụng

- Dùng **resourcecount** khi cần đếm số resource được một collection cung cấp, chẳng hạn số tệp nguồn hoặc số thư viện trong Path.
- Dùng **pathconvert** khi cần biểu diễn Path thành chuỗi cho log, báo cáo hoặc công cụ bên ngoài.
- Tạo property kết quả có tên rõ ràng và tránh dùng lại property đã được thiết lập.
- Dùng **targetos**, **pathsep** và **dirsep** khi định dạng đầu ra phải tuân theo một hệ điều hành cụ thể.
- Dùng **map** khi cần thay thế tiền tố đường dẫn trong chuỗi đầu ra; nhớ rằng map không di chuyển tệp.
- Dùng **setonempty** khi cần bảo đảm property đầu ra tồn tại ngay cả khi Path không có phần tử.
- Giữ Path dưới dạng cấu trúc khi task Ant tiếp theo có thể nhận Path trực tiếp; chỉ chuyển thành chuỗi khi thật sự cần văn bản.

ResourceCount và PathConvert giúp build file mô tả được cả số lượng lẫn cách biểu diễn tập tài nguyên. Khi chọn đúng resource collection và cấu hình rõ separator, property cùng trường hợp rỗng, người phát triển có thể quan sát đầu vào build và truyền thông tin đường dẫn giữa các bước một cách nhất quán.

