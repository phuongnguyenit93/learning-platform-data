# Tạo classpath từ thư mục lớp và tập JAR trong Apache Ant

Khi biên dịch hoặc chạy một ứng dụng Java, trình biên dịch và JVM cần biết nơi tìm các lớp mà ứng dụng sử dụng. Danh sách vị trí đó được gọi là classpath. Trong Apache Ant, datatype Path giúp mô tả classpath theo cách có thể tái sử dụng trong nhiều task.

Một classpath thường kết hợp hai loại đầu vào:

- Thư mục chứa các file .class đã biên dịch. Thư mục này phải là gốc của cây package, tức là thư mục nằm phía trên các package như com/example.
- Các file JAR chứa thư viện hoặc module đã đóng gói.

Ant cho phép tạo một Path bằng phần tử pathelement cho thư mục hoặc file riêng lẻ, và bằng FileSet để chọn nhiều JAR theo mẫu. Sau đó, Path có thể được tham chiếu trong task javac, java hoặc các task khác có hỗ trợ thuộc tính path-like.

## 1. Classpath dùng để làm gì?

Classpath là danh sách các vị trí mà Java tìm kiếm lớp và tài nguyên. Khi biên dịch, javac cần tìm các kiểu dữ liệu được mã nguồn tham chiếu. Khi chạy, JVM cần tìm các lớp mà chương trình sử dụng.

Ví dụ, một ứng dụng có thể dùng:

- Các lớp tiện ích nội bộ đã biên dịch trong thư mục dependencies/classes.
- Thư viện bên ngoài trong thư mục lib.
- Các lớp của chính ứng dụng sau khi được biên dịch vào build/classes.

Cấu trúc dự án minh họa:

~~~text
inventory/
├── build.xml
├── src/
│   └── main/
│       └── java/
│           └── com/example/inventory/Main.java
├── dependencies/
│   └── classes/
│       └── com/example/shared/DateFormatter.class
├── lib/
│   ├── commons-lang3-3.14.0.jar
│   └── jackson-databind-2.17.0.jar
└── build/
    └── classes/
~~~

Khi Main.java import com.example.shared.DateFormatter, trình biên dịch phải tìm thấy thư mục dependencies/classes trên classpath. Khi mã nguồn sử dụng lớp từ commons-lang3 hoặc Jackson, các JAR tương ứng cũng phải có trên classpath.

Điểm quan trọng là classpath chứa **thư mục gốc của package tree**, không phải thư mục package cuối cùng. Với file:

~~~text
dependencies/classes/com/example/shared/DateFormatter.class
~~~

đường dẫn classpath cần là dependencies/classes. Không đặt trực tiếp dependencies/classes/com/example/shared vì Java sẽ ghép tên package từ thư mục gốc của classpath.

## 2. Tạo Path bằng pathelement

Trong Ant, có thể khai báo datatype Path ở cấp project:

~~~xml
<path id="compile.classpath">
    <pathelement location="dependencies/classes" />
</path>
~~~

Path có id compile.classpath để các task khác tham chiếu lại.

Phần tử pathelement thường dùng thuộc tính location khi thêm một vị trí đơn lẻ:

~~~xml
<pathelement location="dependencies/classes" />
~~~

location có thể trỏ đến thư mục chứa lớp đã biên dịch hoặc một file JAR cụ thể. Ant phân giải đường dẫn tương đối theo basedir của project.

Ngoài location, pathelement còn có thuộc tính path để nhận một danh sách đường dẫn phân tách theo quy ước của hệ điều hành. Tuy nhiên, khi thêm một thư mục hoặc một file riêng, location thường rõ ràng và ít phụ thuộc vào dấu phân cách hơn.

Ví dụ thêm hai thư mục lớp và một JAR riêng:

~~~xml
<path id="compile.classpath">
    <pathelement location="dependencies/classes" />
    <pathelement location="modules/shared/classes" />
    <pathelement location="lib/legacy-api.jar" />
</path>
~~~

Các phần tử được ghép thành một Path duy nhất. Các task sử dụng Path không cần tự nối chuỗi classpath bằng dấu chấm phẩy hoặc dấu hai chấm.

## 3. Thêm nhiều JAR bằng FileSet

Khi thư mục lib có nhiều thư viện, khai báo từng JAR bằng pathelement sẽ dài và phải sửa buildfile mỗi khi thêm thư viện. Có thể đặt một FileSet bên trong Path để chọn file theo mẫu:

~~~xml
<path id="compile.classpath">
    <pathelement location="dependencies/classes" />

    <fileset dir="lib">
        <include name="**/*.jar" />
    </fileset>
</path>
~~~

Trong cấu hình này:

1. pathelement thêm thư mục dependencies/classes.
2. FileSet quét thư mục lib.
3. include name="**/*.jar" chọn các JAR ở thư mục lib và mọi thư mục con.
4. Mỗi file được chọn trở thành một phần tử đường dẫn của Path.

Nếu chỉ muốn lấy JAR nằm trực tiếp trong lib, có thể dùng:

~~~xml
<fileset dir="lib">
    <include name="*.jar" />
</fileset>
~~~

Khác biệt nằm ở **/*.jar và *.jar:

- *.jar chỉ khớp file JAR trực tiếp trong thư mục gốc của FileSet.
- **/*.jar khớp file JAR trong thư mục gốc và các thư mục con.

Có thể thêm exclude để bỏ một nhóm JAR:

~~~xml
<path id="compile.classpath">
    <pathelement location="dependencies/classes" />

    <fileset dir="lib">
        <include name="**/*.jar" />
        <exclude name="**/*-sources.jar" />
        <exclude name="**/*-javadoc.jar" />
    </fileset>
</path>
~~~

Các file source và javadoc thường không cần cho classpath biên dịch hoặc chạy ứng dụng. Exclude giúp tránh đưa nhầm các artifact phục vụ tài liệu vào danh sách thư viện.

## 4. Kết hợp thư mục lớp và tập JAR trong một classpath

Một cấu hình điển hình có thể gom cả thư mục lớp và các JAR thành một Path:

~~~xml
<project name="inventory" default="compile" basedir=".">
    <property name="src.dir" location="src/main/java" />
    <property name="build.classes.dir" location="build/classes" />
    <property name="dependency.classes.dir" location="dependencies/classes" />
    <property name="lib.dir" location="lib" />

    <path id="compile.classpath">
        <pathelement location="${dependency.classes.dir}" />
        <fileset dir="${lib.dir}">
            <include name="**/*.jar" />
        </fileset>
    </path>

    <target name="compile">
        <mkdir dir="${build.classes.dir}" />

        <javac srcdir="${src.dir}"
               destdir="${build.classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath" />
        </javac>
    </target>
</project>
~~~

Khi chạy:

~~~bash
ant compile
~~~

Ant thực hiện target compile. Task javac nhận classpath đã khai báo và sử dụng nó để tìm các kiểu dữ liệu được mã nguồn tham chiếu.

Dòng:

~~~xml
<classpath refid="compile.classpath" />
~~~

tham chiếu đến Path đã định nghĩa ở cấp project. Không cần lặp lại danh sách thư mục và JAR bên trong từng task.

Nếu mã nguồn không phụ thuộc lớp bên ngoài, có thể không cần classpath tùy chỉnh. Khi dự án có dependency nội bộ hoặc thư viện bên ngoài, hãy thêm đúng vị trí chứa các lớp đó.

## 5. Tái sử dụng Path trong nhiều task

Một lợi ích của Path có id là nhiều task có thể dùng chung cùng danh sách dependency. Ví dụ, javac dùng classpath để biên dịch và java dùng classpath để chạy chương trình.

Classpath biên dịch thường chứa thư mục lớp của các module phụ thuộc và các JAR bên ngoài. Classpath chạy cần thêm thư mục chứa lớp của chính ứng dụng.

~~~xml
<project name="inventory" default="run" basedir=".">
    <property name="src.dir" location="src/main/java" />
    <property name="build.classes.dir" location="build/classes" />
    <property name="dependency.classes.dir" location="dependencies/classes" />
    <property name="lib.dir" location="lib" />

    <path id="compile.classpath">
        <pathelement location="${dependency.classes.dir}" />
        <fileset dir="${lib.dir}">
            <include name="**/*.jar" />
        </fileset>
    </path>

    <path id="runtime.classpath">
        <pathelement location="${build.classes.dir}" />
        <path refid="compile.classpath" />
    </path>

    <target name="compile">
        <mkdir dir="${build.classes.dir}" />
        <javac srcdir="${src.dir}"
               destdir="${build.classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath" />
        </javac>
    </target>

    <target name="run" depends="compile">
        <java classname="com.example.inventory.Main" fork="true">
            <classpath refid="runtime.classpath" />
        </java>
    </target>
</project>
~~~

Ở đây:

- compile.classpath chứa thư mục lớp phụ thuộc và các JAR.
- runtime.classpath thêm build/classes, nơi javac tạo các lớp của ứng dụng.
- runtime.classpath tham chiếu compile.classpath để không phải khai báo lại các JAR.
- Target run phụ thuộc compile, nên các lớp ứng dụng được tạo trước khi chạy Main.

Nếu thiếu build/classes trong runtime.classpath, JVM có thể không tìm thấy lớp Main dù biên dịch đã thành công. Ngược lại, nếu thiếu thư viện ngoài, chương trình có thể lỗi khi nạp lớp hoặc gọi mã phụ thuộc trong thời gian chạy.

## 6. Dùng Path lồng nhau và refid

Path hỗ trợ tham chiếu một Path khác bằng refid. Điều này cho phép chia classpath thành các nhóm có mục đích riêng.

Ví dụ:

~~~xml
<path id="internal.classes">
    <pathelement location="modules/shared/classes" />
    <pathelement location="modules/domain/classes" />
</path>

<path id="external.libraries">
    <fileset dir="lib">
        <include name="**/*.jar" />
    </fileset>
</path>

<path id="compile.classpath">
    <path refid="internal.classes" />
    <path refid="external.libraries" />
</path>
~~~

Cấu trúc này có ba nhóm:

1. internal.classes chứa các thư mục lớp của module nội bộ.
2. external.libraries chứa các JAR của thư viện bên ngoài.
3. compile.classpath kết hợp hai nhóm để task biên dịch sử dụng.

Khi một thư viện được thêm hoặc thay đổi, chỉ cần cập nhật external.libraries. Khi vị trí module nội bộ thay đổi, chỉ cần chỉnh internal.classes. Các task tham chiếu compile.classpath vẫn giữ nguyên.

Cần khai báo Path có id trước khi tham chiếu nó. id phải duy nhất trong phạm vi project. Nếu tham chiếu sai tên hoặc một id chưa tồn tại, Ant sẽ báo lỗi khi xử lý buildfile.

## 7. Hiển thị classpath để chẩn đoán

Khi build gặp lỗi không tìm thấy lớp, việc xem classpath thực tế có thể giúp xác định đường dẫn bị thiếu. Task pathconvert chuyển một Path thành chuỗi property:

~~~xml
<pathconvert property="compile.classpath.text"
             refid="compile.classpath" />

<target name="show-classpath">
    <echo message="Compile classpath: ${compile.classpath.text}" />
</target>
~~~

Sau đó chạy:

~~~bash
ant show-classpath
~~~

Ant sẽ hiển thị các phần tử đường dẫn được phân giải. Dấu phân cách phụ thuộc hệ điều hành, thường là dấu chấm phẩy trên Windows và dấu hai chấm trên Linux/macOS.

Không nên ghi toàn bộ classpath vào log ở mọi lần build nếu danh sách rất dài. Hãy giữ target chẩn đoán riêng và chỉ chạy khi cần kiểm tra.

## 8. Đường dẫn tương đối, basedir và cấu trúc thư mục

Khi tạo classpath, hãy thống nhất thư mục cơ sở của các đường dẫn. Ví dụ:

~~~xml
<project name="inventory" basedir=".">
    <property name="lib.dir" location="lib" />
    <property name="classes.dir" location="dependencies/classes" />

    <path id="dependency.classpath">
        <pathelement location="${classes.dir}" />
        <fileset dir="${lib.dir}">
            <include name="**/*.jar" />
        </fileset>
    </path>
</project>
~~~

Thuộc tính location giúp Ant phân giải vị trí dựa trên project. Cách này thường rõ ràng hơn việc ghép chuỗi đường dẫn bằng dấu gạch chéo trong nhiều nơi.

Một số lưu ý:

- Thư mục classpath phải là gốc của package tree.
- FileSet cần trỏ đúng thư mục chứa JAR; nếu lib rỗng hoặc mẫu không khớp, classpath sẽ thiếu thư viện.
- Nếu dùng đường dẫn tuyệt đối, buildfile có thể bị phụ thuộc vào máy cụ thể.
- Nếu gọi Ant từ thư mục làm việc khác, hãy hiểu rõ cách shell tìm buildfile và cách project xác định basedir.
- Không đặt thư mục nguồn Java chưa biên dịch vào classpath như thể nó là thư mục lớp; javac nhận nguồn qua srcdir hoặc sourcepath theo mục đích tương ứng.

## 9. Các lỗi classpath thường gặp

### 9.1. Không tìm thấy package hoặc class

Thông báo như package ... does not exist hoặc cannot find symbol thường có nghĩa là classpath không chứa lớp cần thiết, hoặc mã nguồn đang tham chiếu sai tên package/class.

Hãy xác định JAR hoặc thư mục lớp thực sự chứa lớp đó, rồi kiểm tra phần tử tương ứng trong Path. Nếu lớp nằm trong JAR, bảo đảm FileSet include mẫu JAR đó.

### 9.2. Chỉ thêm thư mục lib mà không thêm file JAR

Một thư mục chứa JAR không tự động tương đương classpath có tất cả JAR bên trong. Nếu chỉ thêm:

~~~xml
<pathelement location="lib" />
~~~

Java sẽ xem lib như một thư mục lớp; nó không tự động tìm tất cả file JAR bên trong thư mục đó. Để thêm JAR, dùng FileSet:

~~~xml
<fileset dir="lib">
    <include name="**/*.jar" />
</fileset>
~~~

### 9.3. Chỉ thêm JAR nhưng thiếu thư mục lớp

Nếu module nội bộ đã được biên dịch ra thư mục dependencies/classes, cần thêm thư mục đó bằng pathelement. JAR bên ngoài không thể thay thế các lớp nội bộ chưa được đóng gói.

### 9.4. Dùng sai thư mục gốc của package

Nếu class nằm tại dependencies/classes/com/example/DateUtil.class, classpath phải chứa dependencies/classes. Đặt classpath đến dependencies/classes/com/example sẽ làm Java tìm sai vị trí package.

### 9.5. Biên dịch thành công nhưng chạy lỗi

Classpath biên dịch và classpath chạy có thể khác nhau. Một thư viện có thể đã có trong classpath của javac nhưng không có trong classpath của task java. Hãy tạo runtime.classpath riêng gồm output classes của ứng dụng và các dependency cần thiết khi chạy.

### 9.6. Có nhiều phiên bản của cùng một thư viện

Nếu lib chứa nhiều phiên bản JAR cùng khai báo một class, kết quả có thể phụ thuộc thứ tự tìm kiếm trên classpath. Hãy giữ một phiên bản được chọn rõ ràng, loại các JAR thừa và tránh dựa vào thứ tự file hệ thống trả về.

## 10. Thực hành tốt khi tổ chức classpath

- **Tạo Path có id cho nhóm dependency dùng chung.** Không lặp danh sách JAR ở từng javac hoặc java task.
- **Tách thư mục lớp nội bộ và thư viện bên ngoài.** Tên Path như internal.classes, external.libraries, compile.classpath và runtime.classpath giúp người đọc hiểu mục đích.
- **Dùng pathelement location cho một vị trí cụ thể.** Dùng FileSet khi cần chọn nhiều JAR theo mẫu.
- **Chọn mẫu JAR có chủ đích.** Dùng *.jar nếu chỉ lấy thư mục lib trực tiếp; dùng **/*.jar nếu cần quét thư mục con.
- **Đặt đúng gốc package.** Classpath phải trỏ đến thư mục nằm phía trên các package.
- **Không ghép chuỗi thủ công nếu không cần.** Path và refid giúp Ant xử lý dấu phân cách theo nền tảng.
- **Giữ dependency nhất quán giữa compile và runtime.** Các thư viện cần khi chạy phải xuất hiện trong runtime.classpath.
- **Kiểm tra classpath khi chẩn đoán.** Dùng pathconvert trong target riêng để xem các vị trí đã được phân giải.
- **Quản lý phiên bản JAR.** Không để nhiều phiên bản trùng lặp gây kết quả khó dự đoán.
- **Không đưa thư mục build hoặc thư viện không cần thiết vào mọi classpath.** Chỉ thêm những vị trí phục vụ đúng mục tiêu của task.

## 11. Kết luận

Trong Apache Ant, datatype Path dùng để xây dựng classpath từ nhiều vị trí. pathelement location thêm thư mục lớp hoặc một file cụ thể; FileSet kết hợp với include **/*.jar giúp thêm cả tập JAR từ một thư mục. Đặt Path có id và tham chiếu bằng refid giúp nhiều task dùng chung cùng một cấu hình.

Khi biên dịch, hãy đưa các thư mục lớp phụ thuộc và JAR cần thiết vào compile.classpath. Khi chạy ứng dụng, hãy tạo runtime.classpath bao gồm thư mục output của chính ứng dụng cùng các dependency cần thiết. Kiểm tra đúng basedir, gốc package và danh sách JAR sẽ giúp tránh lỗi thiếu class và làm cho buildfile dễ bảo trì hơn.

