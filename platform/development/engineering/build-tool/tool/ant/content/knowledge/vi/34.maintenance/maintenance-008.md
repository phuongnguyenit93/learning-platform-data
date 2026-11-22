# Đọc và cải tiến buildfile cũ mà vẫn giữ hợp đồng đầu ra trong Apache Ant

## 1. Bảo trì buildfile không chỉ là làm XML dễ đọc hơn

Một dự án Java tồn tại nhiều năm có thể có file **build.xml** dài, nhiều target, lặp đường dẫn, dùng thư viện cũ hoặc chứa các quy tắc ngầm mà không ai còn nhớ rõ. Việc đổi tên property, tách target hay rút gọn file XML có vẻ đơn giản, nhưng một thay đổi nhỏ trong Apache Ant có thể khiến:

- JAR đổi tên, đổi thư mục hoặc mất một resource mà ứng dụng cần lúc chạy.
- Script triển khai gọi target cũ bị lỗi dù target mới chạy thành công.
- Manifest của JAR thiếu **Main-Class**, làm mất khả năng chạy bằng lệnh **java -jar**.
- Class được compile bằng Java version khác, làm artifact không chạy trên máy khách hàng.
- CI vẫn báo **BUILD SUCCESSFUL** nhưng gói phát hành không còn giống gói mà consumer mong đợi.

Vì vậy, mục tiêu của bảo trì là **cải thiện khả năng hiểu, khả năng sửa và tính ổn định của buildfile trong khi giữ nguyên hợp đồng đầu ra đã được các bên sử dụng**.

**Hợp đồng đầu ra (output contract)** không chỉ là một tên tệp. Nó gồm mọi điều mà hệ thống khác có lý do chính đáng để dựa vào: lệnh gọi Ant, tên target, mã thoát, đường dẫn artifact, nội dung gói, thông tin manifest, định dạng báo cáo, cách tìm dependency, những file được copy, vị trí sinh tài liệu và hành vi mà CI/CD quan sát.

Ví dụ, hệ thống triển khai đang đọc **deploy/catalog-cli.jar** sau khi chạy **ant release**. Nếu ta đổi output thành **dist/app.jar** mà không cập nhật consumer, refactor đã phá hợp đồng dù bản JAR mới vẫn chạy trên máy phát triển.

## 2. Xác định chính xác điều gì phải được giữ

Trước khi sửa, cần mô tả hợp đồng theo các lớp sau:

| Lớp hợp đồng | Ví dụ | Vì sao quan trọng |
|---|---|---|
| **Điểm gọi công khai** | **ant**, **ant release**, **ant test**, **ant -Denv=prod package** | CI và script người dùng gọi target/property theo tên |
| **Đường dẫn đầu ra** | **dist/catalog-cli.jar**, **deploy/catalog-cli.jar** | Tool downstream thường đọc một vị trí cố định |
| **Danh sách tệp đầu ra** | JAR, ZIP, Javadoc, XML report, checksum | Có thể có nhiều consumer hơn một job deploy |
| **Nội dung artifact** | Class, resource, configuration, file service descriptor | Thiếu một entry cũng có thể gây lỗi runtime |
| **Metadata artifact** | Manifest, version, Main-Class, classpath, timestamp | Ảnh hưởng tới runtime, khả năng truy vết và checksum |
| **Tương thích runtime** | Bytecode Java 8, tên main class | Build thành công chưa chắc ứng dụng chạy đúng |
| **Tác dụng phụ có chủ ý** | Copy file vào staging, tạo reports, xóa thư mục tạm | Pipeline khác có thể dựa vào sản phẩm trung gian |
| **Trạng thái và báo cáo** | Mã thoát khác 0 khi test lỗi, đường dẫn report XML | CI cần phân biệt đạt/thất bại và đọc kết quả |
| **Cấu hình nhận từ ngoài** | **-Drelease.version=...**, **build.properties**, biến môi trường | Consumer dựa vào khả năng chọn phiên bản/môi trường |

Không phải mọi byte của artifact đều luôn là hợp đồng. Ví dụ, nếu JAR cũ nhúng thời điểm build hiện tại, hai lần chạy cùng source có thể có checksum khác nhau. Cần **xác định mức tương đương mà dự án cam kết**:

1. **Tương đương giao diện:** tên target, tham số, tên file và vị trí không đổi.
2. **Tương đương nội dung/khả năng chạy:** lớp Java, resource, manifest và hành vi ứng dụng vẫn phù hợp.
3. **Tương đương byte-for-byte:** checksum của artifact trùng nhau dưới cùng đầu vào và toolchain đã chốt.

Nếu consumer xác thực SHA-256 hoặc ký JAR, mức byte-for-byte có thể bắt buộc. Nếu artifact cũ chứa timestamp biến thiên, phải tách metadata động và quy tắc so sánh một cách minh bạch; không được tuyên bố refactor giữ nguyên byte chỉ vì tên file giống nhau.

## 3. Cách đọc một build.xml cũ

### 3.1. Bắt đầu từ project, default target và basedir

Ví dụ:

~~~xml
<project name="legacy-catalog" default="release" basedir=".">
    <!-- Các property, path, target nằm ở đây -->
</project>
~~~

Ba thuộc tính đáng chú ý:

- **name** là tên dự án trong ngữ cảnh Ant và log; có thể được script dựa vào.
- **default** là target chạy khi người dùng chỉ gọi **ant**.
- **basedir** ảnh hưởng cách giải quyết nhiều đường dẫn tương đối, đặc biệt file và thư mục do task truy cập.

Không nên thay default target chỉ vì tên mới dễ hiểu hơn. Nếu CI chỉ gọi **ant**, đổi từ **release** sang **test** sẽ thay hành vi của mọi job không chỉ định target.

### 3.2. Vẽ đồ thị phụ thuộc của target

Giả sử:

~~~xml
<target name="prepare"/>
<target name="compile" depends="prepare"/>
<target name="test" depends="compile"/>
<target name="release" depends="test"/>
~~~

Luồng mục tiêu:

~~~text
prepare → compile → test → release
~~~

Khi gọi **ant release**, Ant lập kế hoạch theo quan hệ **depends**. Trong một lần thực thi Ant, target phụ thuộc đã chạy thì thường không được chạy lại chỉ vì nhiều target khác cùng tham chiếu đến nó. Thứ tự trong **depends** cũng có ý nghĩa với những target có tác dụng phụ.

Đọc cả **target được gọi trực tiếp** và các target mà nó phụ thuộc. Một target tên **package** có thể thực hiện thêm việc copy, sinh version file hoặc xóa thư mục. Đổi dependencies có thể làm thay đổi artifact dù phần XML tạo JAR không hề bị sửa.

### 3.3. Phân biệt khai báo ở cấp project và bên trong target

Không phải mọi phần tử trong build.xml đều nằm trong target. Các khai báo cấu hình ở cấp project, ví dụ **property**, **path**, **taskdef**, có thể được Ant xử lý trong giai đoạn cấu hình project; target được chạy sau theo lịch thực thi.

Điều này quan trọng khi một thư viện chỉ được tạo ở target **prepare** nhưng **taskdef** lại khai báo ở cấp project và cần lớp từ thư viện đó. Việc chỉ thêm **depends="prepare"** cho target sử dụng task có thể chưa bảo đảm thư viện đã sẵn có lúc taskdef được đăng ký. Cần hiểu thứ tự Ant cấu hình project và lúc task thực thi.

### 3.4. Theo dấu property tới nguồn định nghĩa đầu tiên

Ví dụ:

~~~xml
<property file="build.properties"/>
<property name="dist.dir" location="dist"/>
<property environment="env"/>
~~~

Property của Ant có tính chất **gần như bất biến sau khi đã được đặt**: một lần gán sau thường không ghi đè giá trị đã tồn tại. Tham số từ lệnh **-D** là user property có ưu tiên cao; các file property, khai báo property và môi trường cần được phân tích theo **thứ tự nạp và phạm vi**.

Vì thế, khi chuyển một property xuống file khác hoặc đổi thứ tự import, giá trị thực tế có thể đổi dù nội dung key/value trông giống nhau. Trước khi “gom các property cho gọn”, hãy tìm:

- Tên key đang được dùng trong những task và target nào.
- Giá trị đến từ **-D**, file properties, environment hay khai báo tại XML.
- Giá trị có thể được truyền từ caller hay không.
- Đường dẫn sử dụng **location** hay **value**, và việc chuẩn hóa đường dẫn có làm thay đổi cách dùng không.

**Property là một phần của giao diện build** khi script bên ngoài truyền nó. Đổi tên **-Ddeploy.dir** thành **-Dpublish.dir** có thể là thay đổi không tương thích dù bên trong buildfile đã cập nhật tất cả tham chiếu.

### 3.5. Kiểm tra các cấu trúc Ant ảnh hưởng đầu ra

| Cấu trúc | Cần quan sát |
|---|---|
| **fileset / patternset** | Đường dẫn gốc, includes, excludes, default excludes, thư mục rỗng |
| **copy / move / delete** | Thứ tự thực thi, overwrite, flatten, filtering, encoding, file đích |
| **javac** | srcdir, destdir, source/target/release, debug, classpath, includeantruntime, encoding |
| **jar / zip / war** | basedir, fileset, manifest, duplicate, compress, entry timestamps |
| **path / classpathref** | Thư mục gốc package, JAR nào được nạp và theo phạm vi nào |
| **exec / java** | Exit code, tham số, working dir, môi trường, failonerror |
| **available / condition / uptodate** | Nhánh điều kiện có thể bị đổi theo trạng thái file trên máy |
| **import / include** | Đường dẫn file con, mục tiêu trùng tên, cách override và resolution |
| **macrodef / presetdef / antcall** | Cách truyền thuộc tính, phạm vi property, thực thi target phụ |

Một điều kiện **if/unless** trong target hoặc một **fileset** mặc định bỏ qua một số file có thể khiến hai môi trường sinh kết quả khác nhau. Khi bảo trì, hãy quan sát **file thực sự vào/ra của task**, không chỉ tên target.

## 4. Lập bản mô tả hiện trạng trước khi sửa

Với buildfile không rõ lịch sử, hãy tạo một **baseline quan sát được** trên một commit cố định và môi trường có thể mô tả lại.

### 4.1. Ghi lại công cụ và lệnh đã chạy

~~~bash
ant -version
java -version
ant -diagnostics
ant -f build.xml -projecthelp
ant -f build.xml -verbose release
~~~

**-projecthelp** hỗ trợ nhận diện target có mô tả, nhưng không bảo đảm hiển thị đầy đủ mọi target hoặc hợp đồng của chúng. **-verbose** giúp thấy các bước thao tác, file được xử lý và đường dẫn được sử dụng. Ghi cả phiên bản Ant, JDK, hệ điều hành, các file property, tham số **-D**, biến môi trường có ảnh hưởng và target thực tế.

Nếu build có thao tác upload/triển khai, hãy chạy phần **kiểm tra/đóng gói** trong môi trường an toàn hoặc dùng chế độ thử được dự án hỗ trợ; không gọi target phát hành thật chỉ để thu thập baseline. Với task xóa/copy file, nên dùng workspace riêng để tránh đụng dữ liệu thật.

### 4.2. Lưu dấu vết của artifact và báo cáo

Trên PowerShell, có thể liệt kê các file đã tạo:

~~~powershell
Get-ChildItem -LiteralPath dist, deploy -Recurse -File |
    Select-Object FullName, Length
Get-FileHash -Path dist/catalog-cli.jar -Algorithm SHA256
jar tf dist/catalog-cli.jar
~~~

Trên shell Unix có công cụ tương ứng:

~~~bash
find dist deploy -type f -print
sha256sum dist/catalog-cli.jar
jar tf dist/catalog-cli.jar
~~~

Nên lưu manifest và các entry quan trọng bên trong archive ở nơi đối chiếu riêng. **jar tf** cho biết danh sách entry nhưng không chứng minh nội dung byte của mỗi entry trùng nhau. Khi cần so sánh sâu, giải nén hai archive vào hai thư mục tạm riêng rồi so sánh nội dung, timestamp và metadata theo mức hợp đồng yêu cầu.

Một bản ghi baseline có thể trông như sau:

~~~text
Command        : ant -f build.xml release
Ant/JDK        : <phiên bản thực tế>
Source revision: <commit đang khảo sát>
Result         : BUILD SUCCESSFUL, exit code 0
Outputs        :
  dist/catalog-cli.jar
  deploy/catalog-cli.jar
JAR manifest   :
  Main-Class: example.catalog.Main
  Implementation-Version: 2.4.0
Required entry :
  catalog.properties
Consumer       : deploy script đọc deploy/catalog-cli.jar
SHA-256        : <giá trị tính từ file đã tạo>
~~~

Đây là **mẫu ghi nhận**, không phải dữ liệu đã chạy thực tế. Với ứng dụng có kiểm thử hoặc báo cáo, bổ sung vị trí report và quy ước exit code khi lỗi.

### 4.3. Tìm consumer của buildfile

Hợp đồng thường nằm ngoài build.xml: script CI, batch/shell deploy, hướng dẫn vận hành, task lịch định kỳ, Dockerfile hoặc phần mềm khác đọc trực tiếp file sinh ra. Hãy tìm các chuỗi như **ant release**, **dist/**, **deploy/**, tên JAR, tên report và các property **-D** trong toàn bộ phạm vi dự án liên quan.

Ví dụ, nếu script deploy chứa:

~~~bash
java -jar deploy/catalog-cli.jar
~~~

thì đường dẫn **deploy/catalog-cli.jar** và manifest **Main-Class** là đầu ra mà refactor cần bảo tồn. Nếu một API downstream nhận file **catalog.properties** nằm ở gốc JAR, đổi file đó sang **config/catalog.properties** là thay đổi hành vi dù các file class không đổi.

## 5. Ví dụ thực hành: đọc buildfile cũ rồi cải tiến có kiểm soát

Giả sử một dự án đã phát hành thành công nhiều năm, và các job phụ thuộc vào lệnh **ant release**. Đầu ra cam kết:

~~~text
build/classes/                # class và resource trung gian
dist/catalog-cli.jar          # artifact đóng gói
deploy/catalog-cli.jar        # bản sao để deploy
~~~

Manifest của JAR chứa **Main-Class: example.catalog.Main** và **Implementation-Version: 2.4.0**. Ứng dụng được biên dịch cho Java 8. Yêu cầu bảo trì là giảm lặp đường dẫn mà **giữ nguyên những điều trên**.

### 5.1. Buildfile ban đầu

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="legacy-catalog" default="release" basedir=".">
    <target name="prepare">
        <mkdir dir="build/classes"/>
        <mkdir dir="dist"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="src/java"
               destdir="build/classes"
               source="8"
               target="8"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="release" depends="compile">
        <copy todir="build/classes">
            <fileset dir="src/resources" includes="**/*"/>
        </copy>

        <jar destfile="dist/catalog-cli.jar"
             basedir="build/classes"
             includes="**/*">
            <manifest>
                <attribute name="Main-Class"
                           value="example.catalog.Main"/>
                <attribute name="Implementation-Version"
                           value="2.4.0"/>
            </manifest>
        </jar>

        <copy file="dist/catalog-cli.jar"
              tofile="deploy/catalog-cli.jar"/>
    </target>
</project>
~~~

Hãy đọc theo **đường đi của dữ liệu**:

~~~text
src/java         -> javac   -> build/classes
src/resources    -> copy    -> build/classes
build/classes    -> jar     -> dist/catalog-cli.jar
dist/*.jar       -> copy    -> deploy/catalog-cli.jar
~~~

Nếu chỉ xem tác vụ **jar**, ta có thể bỏ sót **copy resources** hoặc bản sao **deploy**. Nếu chỉ nhìn **BUILD SUCCESSFUL**, ta vẫn chưa chứng minh cấu trúc archive được giữ.

### 5.2. Bước cải tiến đầu tiên: đặt tên đường dẫn và giá trị lặp

Để cải thiện khả năng hiểu, đưa những literal đang lặp vào property và giữ nguyên target, quan hệ depends, đối số task, thứ tự xử lý:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="legacy-catalog" default="release" basedir=".">
    <property name="src.java.dir" location="src/java"/>
    <property name="src.resources.dir" location="src/resources"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="dist"/>
    <property name="deploy.dir" location="deploy"/>
    <property name="artifact.name" value="catalog-cli.jar"/>
    <property name="artifact.version" value="2.4.0"/>
    <property name="main.class" value="example.catalog.Main"/>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${src.java.dir}"
               destdir="${classes.dir}"
               source="8"
               target="8"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="release" depends="compile">
        <copy todir="${classes.dir}">
            <fileset dir="${src.resources.dir}" includes="**/*"/>
        </copy>

        <jar destfile="${dist.dir}/${artifact.name}"
             basedir="${classes.dir}"
             includes="**/*">
            <manifest>
                <attribute name="Main-Class"
                           value="${main.class}"/>
                <attribute name="Implementation-Version"
                           value="${artifact.version}"/>
            </manifest>
        </jar>

        <copy file="${dist.dir}/${artifact.name}"
              tofile="${deploy.dir}/${artifact.name}"/>
    </target>
</project>
~~~

Với cùng giá trị property, dự định của refactor là **không thay target công khai, nguồn đầu vào, đường dẫn đầu ra, cấu hình compiler, resource, manifest hoặc thứ tự thao tác**.

Tuy nhiên, có một chi tiết quan trọng: property mới cũng có thể bị ảnh hưởng bởi giá trị **-D** truyền từ ngoài. Ví dụ, nếu caller dùng **-Ddist.dir=/tmp/output**, đầu ra của buildfile cải tiến có thể thay đổi, trong khi buildfile cũ với đường dẫn literal không thay đổi. Đây là một **khả năng cấu hình mới**, cần quyết định có thuộc hợp đồng mong muốn hay không và ghi nhận bằng phép đối chiếu trên các cách gọi được hỗ trợ. Không nên mặc định mọi phép trích literal thành property là tương đương cho mọi môi trường.

### 5.3. Khi nên dừng ở bước nhỏ này

Không cần tách 20 file XML hoặc tạo framework mới chỉ để tránh bảy đường dẫn lặp. Nếu việc đặt tên property đã khiến luồng build dễ đọc và các consumer không bị ảnh hưởng, đó là một cải tiến có giá trị.

Sau khi đã hiểu đầy đủ cấu trúc và có bằng chứng bảo toàn đầu ra, mới cân nhắc tách macro dùng chung, gom classpath hoặc chia file import. Độ phức tạp mới luôn cần được cân bằng với khả năng bảo trì thực tế.

## 6. Những thay đổi nhìn nhỏ nhưng dễ phá hợp đồng

### 6.1. Thay target hoặc default target

Đổi:

~~~xml
<project default="release">
~~~

thành:

~~~xml
<project default="test">
~~~

có thể khiến job gọi đơn giản **ant** ngừng tạo artifact. Đổi target **release** thành **package** còn làm script gọi **ant release** báo lỗi.

Nếu cần tên mới nhưng consumer còn dùng tên cũ, có thể giữ một target tương thích:

~~~xml
<target name="package" depends="compile">
    <!-- Các bước đóng gói đã được chuyển vào đây -->
</target>

<target name="release" depends="package"
        description="Legacy public target for existing callers"/>
~~~

Đây chỉ là ví dụ cách giữ **điểm gọi**; việc chuyển các thao tác bên trong phải bảo đảm chúng vẫn diễn ra đúng thứ tự và không lặp. Nếu target **release** cũ còn tạo thêm file hoặc report, wrapper mới cũng phải giữ tác dụng đó.

### 6.2. Thay quan hệ depends hoặc điều kiện target

Giả sử trước đây **release** phụ thuộc **test**; đổi thành phụ thuộc trực tiếp **compile** có thể khiến artifact được phát hành ngay cả khi test thất bại. Đổi **if/unless** cũng có thể tạo khác biệt khi caller truyền property hoặc khi một file trung gian có sẵn.

Với target có tác dụng phụ như xóa thư mục, tải dependency, sửa version file hoặc upload, thay thứ tự phụ thuộc có thể ảnh hưởng cả dữ liệu ngoài artifact. Nên phân biệt **phần tối ưu hóa mong muốn** với thay đổi hành vi cần được phê duyệt.

### 6.3. Sửa fileset cho “gọn”

Ví dụ cũ:

~~~xml
<fileset dir="src/resources" includes="**/*"/>
~~~

Nếu thay bằng:

~~~xml
<fileset dir="src/resources" includes="**/*.properties"/>
~~~

thì file JSON, XML, template hoặc metadata dịch vụ có thể biến mất khỏi JAR. Một package Java chạy đúng ở chức năng smoke test vẫn có thể lỗi ở nhánh runtime dùng resource bị thiếu.

Thay **default excludes**, tên thư mục gốc, **includeemptydirs**, **flatten** hoặc kiểu copy **filtering** cũng có thể đổi nội dung. Khi di chuyển copy sang target khác, phải bảo đảm resource vẫn được copy **trước khi** Ant tạo JAR.

### 6.4. Thay cấu hình javac

Thay **source="8" target="8"** bằng **release="17"** không phải refactor thuần cấu trúc: class mới có thể không chạy trên Java 8. Ngược lại, **source/target** không hoàn toàn giống **release** vì **release** còn giới hạn API nền tảng Java được phép dùng trong quá trình compile.

Các thuộc tính **encoding**, **includeantruntime**, **debug**, **classpath**, **bootclasspath** và annotation processors cũng có thể thay bytecode hoặc hành vi. Muốn nâng mức Java, hãy ghi thành thay đổi hợp đồng tương thích runtime và xác minh với môi trường tiêu thụ thực tế.

### 6.5. Đổi cấu hình jar/zip hoặc manifest

Các lựa chọn như **includes**, **excludes**, **manifest**, **filesonly**, **duplicate**, **compress**, encoding tên entry và thời điểm sửa đổi có thể làm thay đổi nội dung hoặc checksum. Nếu consumer chạy:

~~~bash
java -jar deploy/catalog-cli.jar
~~~

thì thiếu **Main-Class** là lỗi rõ ràng. Nếu consumer kiểm tra chữ ký hoặc checksum, thay đổi metadata ZIP cũng có thể phá hợp đồng byte-for-byte ngay cả khi nội dung class vẫn giống nhau.

Không nên bật thêm filtering hoặc tự ghi timestamp hiện tại vào manifest chỉ để dễ xem log. Thời điểm phát hành thực tế có thể được quản lý ở release record bên ngoài JAR.

### 6.6. Gộp lệnh bằng antcall, macrodef hoặc import

Các công cụ tổ chức buildfile rất hữu ích, nhưng không phải phép thay thế vô điều kiện:

- **macrodef** tạo một thao tác tái sử dụng; thuộc tính và nested elements phải được truyền đúng. Nó phù hợp khi nhiều nơi thực sự cùng một cấu trúc task.
- **presetdef** đặt cấu hình mặc định cho một task/type; cần hiểu việc ghi đè thuộc tính ở nơi sử dụng.
- **antcall** gọi target khác trong một ngữ cảnh Ant mới; property có quy tắc truyền kế thừa và target có thể thực thi lại, không giống hệt quan hệ **depends** trong cùng project execution.
- **import/include** đưa nội dung buildfile khác vào; cần để ý tên target, cách ghi đè, thứ tự định nghĩa và đường dẫn tương đối khi file được tách ra.

Đặc biệt, chuyển một target phụ thuộc bằng **depends** thành gọi qua **antcall** chỉ để “tái sử dụng” có thể khiến một số tác vụ chạy nhiều lần, phát sinh output hoặc làm thay đổi giá trị property ở ngữ cảnh con. Chỉ thực hiện khi chủ đích về scope và vòng đời rõ ràng.

## 7. Lộ trình cải tiến theo từng thay đổi nhỏ

Một cách làm giúp giảm rủi ro:

1. **Khoanh phạm vi:** chọn một target hoặc nhóm output liên quan, xác định consumer và đường dẫn artifact.
2. **Lưu hiện trạng:** chạy các lệnh mà consumer thực sự gọi ở môi trường được kiểm soát; lưu log, kết quả, danh sách file, manifest, checksum khi phù hợp.
3. **Chỉ đổi cấu trúc:** đặt tên property, bổ sung mô tả, loại bỏ một đoạn lặp đã chứng minh tương đương; giữ nguyên tham số task và thứ tự chạy.
4. **Đối chiếu lại:** chạy cùng lệnh, cùng tập đầu vào, cùng Ant/JDK; so tên target, exit code, file sinh ra, nội dung/metadata quan trọng.
5. **Ghi rõ hợp đồng:** đưa thông tin target, đường dẫn artifact, runtime version và property công khai vào tài liệu của dự án.
6. **Tách thay đổi hành vi:** nếu muốn đổi phiên bản Java, bổ sung test, chuẩn hóa timestamp hoặc đổi đường dẫn output, hãy thực hiện như một thay đổi riêng với consumer được cập nhật.

Sự phân tách này giúp một thay đổi **đổi cấu trúc** được đánh giá theo tiêu chí giữ nguyên hợp đồng; còn một thay đổi **đổi hành vi** được đánh giá theo yêu cầu mới và ảnh hưởng triển khai. Không nên trộn hai loại vào một bản sửa lớn khi không cần thiết.

### Một bảng ghi quyết định refactor mẫu

| Thay đổi | Kỳ vọng ảnh hưởng hợp đồng | Bằng chứng cần thu thập |
|---|---|---|
| Đặt tên cho đường dẫn đang lặp | Không đổi với bộ cấu hình đã chốt | Paths trước/sau và input property |
| Thêm mô tả cho target | Không đổi output | Target vẫn gọi và chạy như cũ |
| Tách XML thành import | Có nguy cơ đổi scope/path | Output, property, target override, path resolution |
| Dùng antcall thay depends | Có thể đổi số lần thực thi | Task execution log và tác dụng phụ |
| Đổi Java source/target/release | Thay đổi tương thích runtime | Bytecode và chạy trên Java được hỗ trợ |
| Bật copy filtering | Có thể đổi bytes resource | Entry content và encoding |
| Đổi vị trí JAR | Phá đường dẫn đã công bố | Caller/deploy script đã cập nhật hay chưa |
| Chuẩn hóa timestamp ZIP | Có thể đổi checksum nhưng tăng tái lập | Hợp đồng byte-level và policy artifact |

## 8. Kiểm tra bảo toàn đầu ra như thế nào?

Không có một phép kiểm duy nhất bao phủ mọi hợp đồng. Cần chọn phép đối chiếu tương ứng với điều consumer thật sự dùng.

### 8.1. So sánh điểm gọi và trạng thái

Các lệnh hiện có như:

~~~bash
ant -f build.xml release
ant -f build.xml test
ant -f build.xml -Dartifact.version=2.4.0 release
~~~

cần tiếp tục có ý nghĩa trong các điều kiện được hỗ trợ. Giữ tên target và input property; bảo đảm khi test thất bại, Ant vẫn trả exit code khác 0 nếu đây là điều CI mong đợi.

Nếu refactor bổ sung tên target mới, chưa nên xóa tên cũ khi consumer vẫn còn gọi. Một target tương thích có thể đóng vai trò alias trong giai đoạn chuyển tiếp.

### 8.2. So sánh cây file và byte artifact

Chạy bản cũ và bản mới từ **hai checkout/workspace độc lập** nhưng cùng commit đầu vào cần so sánh, cùng JDK/Ant, cùng dependency, cùng property và cùng điều kiện build. Nếu chạy liên tiếp trong một workspace, output cũ có thể còn sót, làm so sánh sai lệch.

Ghi rõ:

- Danh sách file sinh ra và đường dẫn tương đối.
- Kích thước, checksum khi có yêu cầu byte-level.
- Danh sách entry của JAR/ZIP, vị trí resource, tên class và manifest.
- Quyền file hoặc metadata cần thiết cho deploy trên nền tảng mục tiêu.
- Exit code và report mà hệ thống CI đọc.

Lưu ý: một JAR cũ không có timestamp ổn định có thể có checksum khác nhau giữa **hai lần chạy cùng phiên bản buildfile**. Khi đó cần quan sát độ biến thiên nền trước khi quy lỗi cho refactor. Có thể đối chiếu nội dung entry sau giải nén và đặt kế hoạch riêng nếu muốn đưa build sang chế độ tái lập byte-for-byte.

### 8.3. So sánh hành vi chạy thực tế

Một JAR chứa đúng tên file nhưng không tương thích runtime vẫn có thể phá hợp đồng. Với ứng dụng có Main-Class, kiểm tra:

~~~bash
java -jar deploy/catalog-cli.jar
~~~

Trên Java version mà sản phẩm tuyên bố hỗ trợ, dùng dữ liệu kiểm tra an toàn và quan sát exit code. Với library JAR không có main, thử một chương trình tiêu thụ tối thiểu hoặc bộ tích hợp phù hợp thay vì chạy java -jar.

Trong trường hợp báo cáo XML, code generation, Javadoc hoặc file cấu hình sinh ra, consumer tương ứng mới là thước đo: report path cần tồn tại, schema phù hợp, resource vẫn đọc được và cấu hình cần thiết không bị thay đổi.

### 8.4. Điều kiện chấp nhận một thay đổi

Một refactor có thể được coi là giữ hợp đồng khi các **điểm gọi được hỗ trợ** còn hoạt động, output được đặt đúng nơi, các nội dung/metadata có ý nghĩa được bảo toàn và không xuất hiện side effect mới không mong muốn. Nếu một điểm khác biệt là có chủ đích, hãy ghi rõ nó là **thay đổi hợp đồng được phê duyệt**, không lẫn với kết quả của refactor trung tính.

## 9. Các sự cố thường gặp khi bảo trì

| Hiện tượng sau khi sửa | Nguyên nhân có khả năng | Hướng điều tra |
|---|---|---|
| **ant** chạy nhưng không còn tạo JAR | Default target hoặc depends thay đổi | So project default và đồ thị target |
| **ant release** báo target không tồn tại | Đã đổi tên/xóa target công khai | Giữ alias hoặc cập nhật caller có chủ đích |
| JAR tạo được nhưng thiếu file cấu hình | Copy/fileset thay đổi, chạy sau jar | So entry JAR, excludes và thứ tự task |
| CI không tìm thấy artifact | dist/deploy path hoặc tên file đổi | So consumer script và cây file đầu ra |
| Local chạy được, CI lỗi | Ant/JDK, path, case sensitivity, env hoặc property khác | Chốt thông tin môi trường và lệnh chạy |
| Ứng dụng không chạy được với Java cũ | source/target/release đổi | Kiểm tra bytecode và runtime hỗ trợ |
| Cùng source nhưng checksum JAR đổi | Timestamp, manifest, archive metadata hoặc toolchain | So entry và metadata, không chỉ file name |
| Build mới chạy chậm/target chạy hai lần | Đổi depends sang antcall hoặc thay incremental behavior | Đọc log target execution và state file |
| Bản cũ đọc -Dkey, bản mới không còn | Property bị đổi tên hoặc ghi sớm | Tìm nguồn/ưu tiên property |
| File report vẫn có nhưng CI báo thất bại | Report path/format, exit code hoặc task failonerror thay đổi | Kiểm tra hợp đồng CI và logger |
| Build xóa nhầm dữ liệu | basedir hoặc biến output/clean dir bị đổi | Kiểm tra resolved path và phạm vi delete |

### Trường hợp 1 — “Cleanup” xóa quá rộng

Một target cũ có thể chỉ xóa **build/classes**, còn refactor dùng:

~~~xml
<delete dir="build"/>
~~~

Nếu **build/** còn chứa report hoặc file do người dùng sinh mà công việc tiếp theo cần, thay đổi này không tương đương. Xác định **quyền sở hữu thư mục** trước khi mở rộng phạm vi delete; tránh dùng cleanup như một bước tự động trên workspace chưa được kiểm soát.

### Trường hợp 2 — Tối ưu build tăng dần làm sai file được đóng gói

Ant **javac** có thể bỏ qua biên dịch một số file nếu class được coi là mới hơn source. Việc chuyển thư mục output hoặc thay điều kiện incrementality có thể khiến file .class cũ còn sót hoặc bị bỏ qua. Đánh giá refactor nên có trường hợp **clean workspace** và trường hợp **build tăng dần**, vì hợp đồng của hai cách gọi có thể khác nhau.

Không nên kết luận “không thay đổi” chỉ vì build lần thứ hai báo thành công khi output cũ vẫn có sẵn. Cần biết file nào thực sự được tạo ở lần build vừa chạy.

### Trường hợp 3 — Di chuyển build fragment sang file import

Nếu tách một đoạn build.xml thành **build/common.xml**, các đường dẫn tương đối trong fragment cần được xem xét theo cách Ant giải quyết path và project đang chạy, không mặc định chúng trở thành đường dẫn tương đối với file XML mới. Tên target có thể bị trùng hoặc có cơ chế override khác. Đừng chỉ xem XML đã parse được; phải kiểm tra đường dẫn đầu ra, target resolution và giá trị property thực tế.

### Trường hợp 4 — Thay task tùy biến

Một custom task được định nghĩa qua **taskdef** có thể dựa vào Ant classpath, phiên bản dependency hoặc một tham số undocumented. Thay nó bằng task tích hợp chỉ vì kết quả dễ đọc hơn có thể làm đổi nội dung file, mã thoát hoặc thứ tự thao tác. Trước khi thay, ghi cụ thể task đó đọc gì, ghi gì, xử lý lỗi thế nào và bên ngoài quan sát gì.

## 10. Khi cần đổi hợp đồng, hãy công bố rõ thay đổi

Đôi khi mục tiêu thật sự là nâng Java version, đổi tên artifact, thêm checksum, chuẩn hóa ZIP timestamp hoặc thay quy trình deploy. Những việc đó có thể cần thiết, nhưng không nên được ghi nhận như **refactor không đổi hành vi**.

Cách xử lý phù hợp là:

1. Mô tả đầu ra cũ, đầu ra mới và consumer bị ảnh hưởng.
2. Xác định phương thức tương thích trong thời gian chuyển tiếp: giữ target alias, copy thêm file cũ hoặc cung cấp cấu hình chọn phiên bản.
3. Cập nhật CI, script deploy, tài liệu và quy trình vận hành cùng với thay đổi.
4. Áp dụng kiểm tra trên môi trường tiêu thụ thực tế, quan sát kết quả rồi loại bỏ giao diện cũ khi đã hết consumer.

Ví dụ, nếu muốn đổi **deploy/catalog-cli.jar** sang **release/catalog-cli-2.5.0.jar**, có thể tạm thời tạo cả hai đường dẫn nếu chính sách cho phép. Nhưng cần biết rõ file nào là artifact chính thức, file nào là cầu nối tương thích và khi nào được phép xóa cầu nối. Không để một bản sao cũ âm thầm tồn tại vô thời hạn mà không có quyền sở hữu.

## 11. Checklist thực hành khi nhận một buildfile cũ

Trước khi thay đổi:

- Xác định **default target**, các target gọi từ CI, properties bên ngoài và basedir.
- Vẽ đồ thị **depends** của luồng build liên quan.
- Tìm file XML được **import/include**, taskdef, macrodef và công cụ ngoài mà Ant gọi.
- Lập danh mục output: tên, vị trí, nội dung, metadata và tác dụng phụ có chủ đích.
- Ghi một baseline có Ant/JDK version, source revision, lệnh và tham số thật.

Khi cải tiến:

- Chỉ sửa một nhóm hành vi nhỏ và chọn tên/đường dẫn dễ hiểu.
- Giữ thứ tự xử lý, classpath, includes/excludes và cấu hình compile/package trừ khi thay đổi được chấp thuận.
- Kiểm tra property precedence; tránh vô tình thay khả năng nhận tham số **-D**.
- Giữ target công khai hoặc tạo đường tương thích khi consumer chưa đổi.
- Không trộn việc dọn dẹp file hoặc nâng cấp toolchain vào một refactor thuần cấu trúc.

Trước khi coi là hoàn tất:

- Chạy lại đúng lệnh consumer dùng, với cùng đầu vào và môi trường đã chốt.
- Đối chiếu file đầu ra, manifest, resource, bytecode, report và exit code tương ứng.
- Ghi rõ khác biệt nào là chủ đích, khác biệt nào chưa giải thích được.
- Cập nhật tài liệu hợp đồng để lần bảo trì sau không phải đoán lại.

## 12. Kết luận

Khi đọc một buildfile Ant cũ, hãy xem nó như một **giao diện đang được tiêu thụ**, không chỉ là một tệp XML cần làm đẹp. Cách hiểu chính xác bắt đầu từ **project/default target → đồ thị depends → property và classpath → luồng file đầu vào/đầu ra → consumer**.

Cải tiến an toàn thường là những bước nhỏ: đặt tên cho đường dẫn, làm rõ target, giảm lặp ở nơi có bằng chứng và giữ nguyên hành vi được cam kết. Thước đo thành công là **người dùng và hệ thống downstream vẫn gọi được cùng giao diện và nhận đúng artifact**, trong khi buildfile trở nên dễ đọc, dễ chẩn đoán và dễ thay đổi hơn ở tương lai.

### Tài liệu tham khảo

- [Apache Ant Manual — Using Apache Ant](https://ant.apache.org/manual/using.html): project, target, depends, properties, path-like structures.
- [Apache Ant Manual — Running Ant](https://ant.apache.org/manual/running.html): cách gọi target, -projecthelp, -verbose và -diagnostics.
- [Apache Ant Manual — Property Task](https://ant.apache.org/manual/Tasks/property.html): cách định nghĩa property và hành vi gán giá trị.
- [Apache Ant Manual — Javac Task](https://ant.apache.org/manual/Tasks/javac.html): compile classpath và các tham số ảnh hưởng bytecode.
- [Apache Ant Manual — Copy Task](https://ant.apache.org/manual/Tasks/copy.html): file copy, filtering và cấu hình file set.
- [Apache Ant Manual — Jar Task](https://ant.apache.org/manual/Tasks/jar.html): manifest và nội dung archive.
- [Apache Ant Manual — Import Task](https://ant.apache.org/manual/Tasks/import.html): tách buildfile và target override.
- [Apache Ant Manual — AntCall Task](https://ant.apache.org/manual/Tasks/antcall.html): gọi target con và ngữ cảnh property.
- [Apache Ant Manual — Macrodef Task](https://ant.apache.org/manual/Tasks/macrodef.html): khai báo thao tác tái sử dụng trong Ant.
