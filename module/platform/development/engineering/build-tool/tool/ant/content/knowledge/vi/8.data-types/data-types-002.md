# Đối tượng tham chiếu, phạm vi id và tái sử dụng refid

Trong Apache Ant, nhiều task cần dùng chung một cấu hình dữ liệu. Ví dụ, task javac và task java có thể cùng cần một classpath; nhiều task sao chép hoặc đóng gói có thể cùng cần một tập hợp tệp; nhiều thư mục nguồn có thể dùng chung quy tắc include và exclude. Nếu khai báo lặp lại toàn bộ cấu hình ở từng nơi, build file sẽ dài, dễ sai khác và khó bảo trì.

Ant cho phép đặt tên cho một số đối tượng dữ liệu bằng thuộc tính id, sau đó tham chiếu lại đối tượng đó bằng refid. Cơ chế này giúp tái sử dụng cấu hình trong cùng một Ant project, đồng thời tách phần định nghĩa dữ liệu khỏi các task sử dụng dữ liệu.

Bài học tập trung vào ba vấn đề: đối tượng nào có thể được tham chiếu, phạm vi mà một id có hiệu lực, và cách sử dụng refid để chia sẻ hoặc kết hợp dữ liệu.

## 1. Phân biệt id, refid và property

### 1.1. id đặt tên cho đối tượng dữ liệu

Một data type hỗ trợ thuộc tính id có thể đăng ký đối tượng của nó vào bảng tham chiếu của Ant project. Ví dụ:

    <path id="compile.classpath">
        <pathelement location="lib/api.jar" />
        <pathelement location="lib/runtime.jar" />
    </path>

Trong ví dụ này:

- path tạo một đối tượng biểu diễn đường dẫn classpath.
- id="compile.classpath" đặt tên tham chiếu cho đối tượng đó.
- Các phần tử pathelement xác định những mục thuộc classpath.

Sau khi đối tượng được đăng ký, các task khác có thể sử dụng tên đó mà không cần khai báo lại từng JAR.

### 1.2. refid lấy lại đối tượng đã được định nghĩa

Khi một task hoặc data type hỗ trợ tham chiếu, ta dùng refid để trỏ tới đối tượng đã đăng ký:

    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.classpath" />
    </javac>

refid="compile.classpath" cho biết classpath của task javac lấy từ đối tượng đã định nghĩa trước đó. Tên tham chiếu phải khớp chính xác với giá trị id.

### 1.3. id/refid khác property

Property và reference đều giúp tránh lặp cấu hình, nhưng chúng đại diện cho những thứ khác nhau.

| Cơ chế | Lưu trữ | Cách sử dụng | Ví dụ |
|---|---|---|---|
| property | Một giá trị như chuỗi, số hoặc đường dẫn đã biểu diễn thành chuỗi | Nội suy bằng ${property.name} | property name="lib.dir" |
| id | Một đối tượng data type được đăng ký trong project | Được lấy lại bằng refid ở nơi hỗ trợ tham chiếu | path id="compile.classpath" |
| refid | Không tạo đối tượng mới; nó chỉ ra đối tượng đã có | Gắn vào thuộc tính hoặc phần tử con hỗ trợ reference | classpath refid="compile.classpath" |

Ví dụ, lib.dir là một giá trị đường dẫn và có thể dùng trong thuộc tính dir:

    <property name="lib.dir" location="lib" />
    <fileset dir="${lib.dir}" includes="*.jar" />

Trong khi đó, compile.classpath là một đối tượng path đã được xây dựng từ nhiều thành phần. Không thể thay refid bằng cú pháp nội suy property như ${compile.classpath} rồi mong Ant tự chuyển đối tượng thành classpath.

Một property có thể chứa chuỗi tên tham chiếu, nhưng bản thân chuỗi đó vẫn không phải đối tượng được đăng ký bằng id. Hãy dùng đúng cơ chế theo loại dữ liệu cần truyền.

## 2. Những data type thường được tái sử dụng

Không phải mọi phần tử XML trong Ant đều là data type và không phải mọi data type đều hỗ trợ id hoặc refid. Hãy kiểm tra tài liệu của từng loại trước khi dùng. Một số kiểu dữ liệu thường gặp có khả năng tham chiếu gồm:

| Data type | Công dụng | Ví dụ sử dụng |
|---|---|---|
| path | Tập hợp đường dẫn, thường dùng làm classpath hoặc source path | classpath refid="..." |
| fileset | Tập hợp tệp được chọn theo thư mục và mẫu include/exclude | fileset refid="..." |
| patternset | Tập hợp quy tắc chọn hoặc loại trừ đường dẫn tương đối | patternset refid="..." |
| filterset | Tập hợp các phép thay thế token khi lọc nội dung tệp | filterset refid="..." |
| mapper | Quy tắc ánh xạ tên đường dẫn nguồn sang tên đích | mapper refid="..." |

Các task cụ thể quyết định vị trí có thể đặt reference. Ví dụ, task javac có phần tử con classpath; task copy và zip có thể nhận fileset; task copy có thể dùng filterset hoặc mapper trong các trường hợp tương ứng.

Không nên giả định rằng chỉ cần một phần tử có tên giống data type là nó có thể nhận refid. Thuộc tính này phải được phần tử hoặc task hỗ trợ.

## 3. Tái sử dụng path cho classpath

### 3.1. Định nghĩa classpath một lần

Classpath thường được dùng ở nhiều bước: biên dịch mã nguồn, chạy ứng dụng, chạy công cụ hoặc thực thi test. Ta có thể gom các thư viện vào một path:

    <path id="application.classpath">
        <pathelement location="lib/api.jar" />
        <pathelement location="lib/runtime.jar" />
        <fileset dir="lib/optional" includes="*.jar" />
    </path>

Đối tượng application.classpath chứa hai JAR được chỉ định trực tiếp và tất cả JAR khớp mẫu trong lib/optional.

### 3.2. Dùng cùng classpath ở nhiều task

Task biên dịch có thể tham chiếu path đó:

    <target name="compile">
        <mkdir dir="build/classes" />

        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="application.classpath" />
        </javac>
    </target>

Task chạy ứng dụng cũng có thể sử dụng cùng đối tượng:

    <target name="run" depends="compile">
        <java classname="com.example.Main" fork="true">
            <classpath>
                <pathelement location="build/classes" />
                <path refid="application.classpath" />
            </classpath>
        </java>
    </target>

Trong target run, classpath gồm thư mục chứa lớp đã biên dịch và các thành phần của application.classpath. Phần tử path refid được đặt bên trong một path mới để kết hợp nhiều mục.

Cách tổ chức này giúp khi thêm hoặc thay một thư viện dùng chung, ta chỉ cần cập nhật định nghĩa application.classpath. Các task tham chiếu nó sẽ nhận cấu hình đã cập nhật khi build được chạy.

### 3.3. Mở rộng một path đã có

Đôi khi test cần tất cả thư viện của ứng dụng cộng thêm thư viện kiểm thử. Không cần sao chép lại các mục của classpath nền:

    <path id="application.classpath">
        <fileset dir="lib/application" includes="*.jar" />
    </path>

    <path id="test.classpath">
        <path refid="application.classpath" />
        <pathelement location="lib/test/junit.jar" />
        <pathelement location="lib/test/hamcrest.jar" />
    </path>

Sau đó task biên dịch test có thể dùng:

    <javac srcdir="src/test/java"
           destdir="build/test-classes"
           includeantruntime="false">
        <classpath>
            <pathelement location="build/classes" />
            <path refid="test.classpath" />
        </classpath>
    </javac>

Ở đây, test.classpath kết hợp classpath ứng dụng với các thư viện test. Việc tham chiếu một path bên trong một path khác giúp tạo cấu hình theo tầng: path nền chứa dependency chung, path chuyên biệt bổ sung phần cần riêng.

## 4. Tái sử dụng fileset

### 4.1. Định nghĩa tập hợp tệp bằng id

Một fileset chọn tệp dựa trên thư mục gốc và các mẫu include/exclude. Ví dụ:

    <fileset id="documentation.files" dir="docs">
        <include name="**/*.md" />
        <exclude name="drafts/**" />
    </fileset>

Đối tượng documentation.files đại diện cho các tệp Markdown trong thư mục docs, trừ nội dung nằm dưới docs/drafts.

### 4.2. Dùng lại trong nhiều task

Có thể dùng cùng tập hợp tệp cho thao tác sao chép và đóng gói:

    <target name="copy-documentation">
        <copy todir="build/docs">
            <fileset refid="documentation.files" />
        </copy>
    </target>

    <target name="archive-documentation">
        <zip destfile="dist/documentation.zip">
            <fileset refid="documentation.files" />
        </zip>
    </target>

Cả hai task dùng cùng quy tắc chọn tệp. Nếu cần loại thêm một loại tệp khỏi tài liệu phát hành, sửa định nghĩa fileset tại một nơi thay vì tìm từng task để sửa.

Một fileset được định nghĩa bằng id vẫn giữ thư mục gốc và các bộ lọc của nó. Khi tham chiếu lại bằng refid, không nên giả định có thể tùy ý thay dir hoặc thêm cấu hình khác ngay trên reference. Nếu cần một tập hợp khác, hãy tạo fileset mới hoặc xây dựng một data type bao ngoài phù hợp.

## 5. Tái sử dụng patternset

Patternset lưu các mẫu chọn và loại trừ, thường được dùng bên trong fileset. Điểm hữu ích là cùng một bộ quy tắc có thể áp dụng cho nhiều thư mục gốc khác nhau.

Ví dụ định nghĩa:

    <patternset id="java.source.patterns">
        <include name="**/*.java" />
        <exclude name="**/generated/**" />
        <exclude name="**/legacy/**" />
    </patternset>

Áp dụng cho mã nguồn chính:

    <fileset dir="src/main/java">
        <patternset refid="java.source.patterns" />
    </fileset>

Áp dụng cho mã nguồn test:

    <fileset dir="src/test/java">
        <patternset refid="java.source.patterns" />
    </fileset>

Cả hai fileset đều chọn tệp Java và loại trừ các đường dẫn tương đối khớp quy tắc. Vì thư mục gốc khác nhau, tập hợp tệp thực tế vẫn khác nhau.

Patternset đặc biệt hữu ích khi một quy ước lọc cần được dùng nhất quán ở nhiều target, ví dụ bỏ qua thư mục sinh tự động, tệp tạm hoặc mã nguồn cũ trong nhiều thao tác đóng gói.

## 6. Tái sử dụng filterset và mapper

### 6.1. Filterset cho thay thế token

Khi cần thay token trong tệp văn bản trong lúc sao chép, có thể khai báo một filterset dùng chung:

    <filterset id="application.filters">
        <filter token="APP_VERSION" value="1.2.0" />
        <filter token="APP_ENV" value="staging" />
    </filterset>

Sau đó dùng trong task copy:

    <copy todir="build/config">
        <fileset dir="config/templates" includes="*.properties" />
        <filterset refid="application.filters" />
    </copy>

Nếu tệp nguồn chứa token dạng @APP_VERSION@ hoặc @APP_ENV@ theo cấu hình delimiters mặc định của filterset, Ant thay chúng bằng giá trị tương ứng khi copy. Hãy lưu ý rằng filtering có thể làm thay đổi nội dung tệp; chỉ áp dụng cho tệp văn bản có token được thiết kế rõ ràng. Không bật filtering trên ảnh, JAR, PDF hoặc tệp nhị phân.

### 6.2. Mapper cho quy tắc đổi tên

Mapper mô tả cách chuyển tên nguồn thành tên đích. Ví dụ, mapper có thể đổi phần mở rộng:

    <mapper id="java-to-class"
            type="glob"
            from="*.java"
            to="*.class" />

Ở vị trí hỗ trợ mapper, có thể tham chiếu nó:

    <copy todir="build/mapped">
        <fileset dir="generated-source" includes="*.java" />
        <mapper refid="java-to-class" />
    </copy>

Ví dụ chỉ minh họa cơ chế tái sử dụng mapper. Việc đổi tên tệp Java thành .class không biên dịch mã nguồn; task javac mới là công cụ biên dịch Java. Trong build thực tế, mapper thường hữu ích khi copy, move hoặc đồng bộ các tệp có quy tắc đổi tên cụ thể.

## 7. Phạm vi của id và thời điểm đối tượng được tạo

### 7.1. id thuộc phạm vi của Ant project

Một id được đăng ký trong bảng tham chiếu của Ant project. Vì vậy, các target trong cùng project có thể dùng lại đối tượng đã đăng ký, miễn là đối tượng đã được tạo trước khi target sử dụng nó được thực thi.

Ví dụ, khai báo path ở cấp project:

    <project name="sample" default="run">

        <path id="tool.classpath">
            <pathelement location="lib/tool.jar" />
        </path>

        <target name="compile-tool">
            <echo message="Compile tool with shared classpath" />
        </target>

        <target name="run" depends="compile-tool">
            <java classname="com.example.Tool" fork="true">
                <classpath refid="tool.classpath" />
            </java>
        </target>

    </project>

Ở đây, tool.classpath được khai báo ở cấp project nên các target trong project có thể tham chiếu nó. id không phải biến cục bộ chỉ nhìn thấy trong một target.

### 7.2. Đối tượng được định nghĩa bên trong target

Data type cũng có thể được tạo trong một target. Khi đó, target tạo đối tượng cần được thực thi trước target sử dụng reference.

    <target name="define-runtime-path">
        <path id="runtime.classpath">
            <pathelement location="build/classes" />
            <fileset dir="lib/runtime" includes="*.jar" />
        </path>
    </target>

    <target name="run-app" depends="define-runtime-path">
        <java classname="com.example.Main" fork="true">
            <classpath refid="runtime.classpath" />
        </java>
    </target>

Dependency depends="define-runtime-path" bảo đảm target định nghĩa path được chạy trước target run-app. Nếu bỏ dependency và target sử dụng được gọi trước, reference có thể chưa tồn tại tại thời điểm task cần nó.

Vì vậy, khi đặt data type bên trong target, hãy thể hiện thứ tự tạo và sử dụng bằng dependency. Nếu dữ liệu là cấu hình chung, không phụ thuộc vào một bước xử lý cụ thể, khai báo ở cấp project thường dễ theo dõi hơn.

### 7.3. id phải duy nhất trong project

Không dùng cùng một id để đăng ký hai đối tượng khác nhau trong cùng project. Ví dụ sau là cấu hình không hợp lệ về mặt thiết kế:

    <path id="shared.classpath">
        <pathelement location="lib/a.jar" />
    </path>

    <path id="shared.classpath">
        <pathelement location="lib/b.jar" />
    </path>

Hãy đặt tên khác nhau cho từng đối tượng:

    <path id="main.classpath">
        <pathelement location="lib/main.jar" />
    </path>

    <path id="test.classpath">
        <pathelement location="lib/test.jar" />
    </path>

Tên ID nên mô tả vai trò và loại dữ liệu để dễ tìm nơi định nghĩa và nơi sử dụng. Các tên như main.classpath, test.classpath, source.files thường rõ ràng hơn tên chung như data1 hoặc shared.

## 8. Phạm vi khi chia build thành nhiều file hoặc project

### 8.1. Các file được import

Khi dùng import, build file được import tham gia vào cùng Ant project. Vì thế, các target và data type được khai báo trong các file import có thể phối hợp với các phần khác của project thông qua các cơ chế của Ant, trong đó có reference ID.

Ví dụ, build file chính định nghĩa path:

    <path id="shared.classpath">
        <fileset dir="lib" includes="*.jar" />
    </path>

    <import file="tasks/compile.xml" />

File tasks/compile.xml có thể sử dụng reference này trong task phù hợp:

    <project name="compile-tasks">
        <target name="compile">
            <javac srcdir="src/main/java"
                   destdir="build/classes"
                   includeantruntime="false">
                <classpath refid="shared.classpath" />
            </javac>
        </target>
    </project>

Các file import vẫn là một phần của cùng project được nạp bởi build file chính. Do đó, cần tránh trùng ID giữa các file để không gây xung đột trong cùng bảng tham chiếu.

### 8.2. Build file chạy như một project Ant khác

Cần phân biệt import với task ant. Khi task ant gọi một build file khác, Ant tạo hoặc chạy một project con với ngữ cảnh riêng. Không nên giả định mọi reference ID trong project cha tự động có mặt trong project con.

Task ant có cơ chế cấu hình việc kế thừa reference, nhưng việc truyền reference phải được chủ động thiết lập và đối tượng phải phù hợp với project đích. Trong nhiều trường hợp, cách đơn giản và rõ ràng hơn là khai báo lại data type cần thiết trong build file con hoặc truyền dữ liệu qua property/file cấu hình phù hợp.

Điểm cần nhớ là: reference ID không phải tên toàn cục của máy. Nó thuộc một project Ant cụ thể và không tồn tại xuyên suốt các lần chạy Ant độc lập.

## 9. Quy tắc khi dùng refid

Khi tham chiếu đối tượng, hãy lưu ý:

1. ID phải được định nghĩa bằng một data type hỗ trợ thuộc tính id.
2. Reference phải được sử dụng ở vị trí hỗ trợ loại dữ liệu tương ứng.
3. Tên refid phải khớp chính xác với ID đã đăng ký.
4. Đối tượng phải tồn tại trước khi task sử dụng nó được thực thi.
5. Một ID chỉ nên đại diện cho một đối tượng trong cùng project.
6. Không nhầm reference ID với property hoặc tên target.
7. Khi cần kết hợp thêm dữ liệu, tạo data type mới và đặt reference cũ bên trong nó nếu loại dữ liệu hỗ trợ cách kết hợp đó.
8. Không giả định mọi data type đều hỗ trợ id hoặc mọi task đều nhận refid; kiểm tra tài liệu Ant của phần tử cụ thể.

Với các phần tử sử dụng trực tiếp refid, thường nên coi reference là cấu hình đã định nghĩa hoàn chỉnh. Nếu cần thay đổi thư mục, include hoặc thành phần classpath, hãy tạo đối tượng mới hoặc xây dựng đối tượng tổng hợp. Cách này tránh làm cho một reference dùng chung có hành vi khác nhau tùy nơi sử dụng.

## 10. Các lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Ant báo không tìm thấy reference | ID chưa được khai báo hoặc target định nghĩa đối tượng chưa chạy | Kiểm tra spelling và dependency giữa target tạo với target dùng |
| Reference trỏ sai loại đối tượng | Dùng ID của fileset ở vị trí yêu cầu path hoặc ngược lại | Đối chiếu kiểu dữ liệu mà phần tử nhận yêu cầu |
| Build báo trùng ID | Nhiều data type trong cùng project đăng ký cùng một ID | Đặt tên duy nhất và tìm các định nghĩa ID trùng |
| Thay đổi một nơi nhưng nhiều task cùng thay đổi kết quả | Nhiều task đang dùng chung một reference | Kiểm tra các nơi dùng refid và tách đối tượng nếu cần cấu hình riêng |
| Task không nhận refid | Phần tử đó không hỗ trợ reference hoặc cú pháp đặt sai cấp | Kiểm tra tài liệu task và đặt reference ở đúng phần tử con |
| Muốn thêm phần tử nhưng reference không cho phép | Đang dùng reference như thể nó là khai báo mới | Tạo path/fileset mới và tham chiếu đối tượng cũ bên trong nếu được hỗ trợ |
| Reference có trong file cha nhưng không có trong build con | Hai build file thuộc hai project Ant khác nhau | Khai báo lại hoặc cấu hình cơ chế kế thừa reference có chủ đích |
| Kết quả chọn tệp khác dự kiến | Pattern tương đối được áp dụng trên thư mục gốc khác nhau | Kiểm tra dir của fileset và các include/exclude trong patternset |

Khi điều tra, hãy tìm cả nơi định nghĩa ID lẫn nơi sử dụng refid. Chỉ đọc task đang lỗi có thể chưa đủ vì nguyên nhân có thể nằm ở target khác tạo đối tượng hoặc ở build file được import.

Có thể dùng lệnh sau để xem các target và thông tin thực thi chi tiết hơn:

    ant -verbose compile

Mức verbose hỗ trợ theo dõi quá trình build, nhưng để xác định chính xác ID được tạo ở đâu, hãy tìm các khai báo id="..." và các vị trí refid="..." trong các build file liên quan.

## 11. Ví dụ tổng hợp: tái sử dụng dữ liệu trong build file

Ví dụ sau kết hợp property, path, patternset và fileset trong một project:

    <project name="reference-example" default="package">

        <!-- Property là giá trị cấu hình dạng chuỗi/đường dẫn. -->
        <property name="lib.dir" location="lib" />
        <property name="main.src" location="src/main/java" />
        <property name="test.src" location="src/test/java" />
        <property name="build.dir" location="build" />

        <!-- Path là đối tượng classpath có thể được tham chiếu. -->
        <path id="main.classpath">
            <fileset dir="${lib.dir}/main" includes="*.jar" />
        </path>

        <!-- Patternset là bộ quy tắc có thể dùng cho nhiều fileset. -->
        <patternset id="java.patterns">
            <include name="**/*.java" />
            <exclude name="**/generated/**" />
        </patternset>

        <!-- Fileset nguồn dùng lại cùng quy tắc pattern. -->
        <fileset id="main.java.files" dir="${main.src}">
            <patternset refid="java.patterns" />
        </fileset>

        <target name="compile">
            <mkdir dir="${build.dir}/classes" />
            <javac srcdir="${main.src}"
                   destdir="${build.dir}/classes"
                   includeantruntime="false">
                <classpath refid="main.classpath" />
            </javac>
        </target>

        <target name="copy-source-list">
            <mkdir dir="${build.dir}/source-list" />
            <copy todir="${build.dir}/source-list">
                <fileset refid="main.java.files" />
            </copy>
        </target>

        <target name="package" depends="compile,copy-source-list">
            <mkdir dir="dist" />
            <zip destfile="dist/application.zip">
                <fileset dir="${build.dir}/classes" />
            </zip>
        </target>

    </project>

Trong ví dụ:

- Property giữ các đường dẫn gốc để tránh lặp chuỗi.
- Path main.classpath gom các JAR dùng khi biên dịch.
- Patternset java.patterns định nghĩa quy tắc chọn mã nguồn.
- Fileset main.java.files dùng lại patternset và có thể được nhiều task tham chiếu.
- Các target dùng reference ở đúng vị trí mà task hỗ trợ.

Ví dụ này minh họa cách tổ chức dữ liệu; trong dự án thực tế, cần bảo đảm các thư mục và JAR được chỉ định tồn tại. Target copy-source-list sao chép tệp nguồn vào thư mục staging riêng chỉ để minh họa việc dùng lại fileset; không nên đưa mã nguồn vào artifact phát hành nếu yêu cầu sản phẩm không cho phép.

## 12. Nguyên tắc tổ chức reference dễ bảo trì

- Đặt ID theo vai trò cụ thể, chẳng hạn compile.classpath, test.classpath, source.files hoặc release.filters.
- Định nghĩa dữ liệu dùng chung ở vị trí dễ tìm, thường gần đầu build file hoặc trong file cấu hình được import.
- Chỉ chia sẻ đối tượng khi các nơi sử dụng thực sự cần cùng một cấu hình.
- Tách reference khi hai nhóm task cần quy tắc khác nhau, dù chúng có vẻ giống nhau ban đầu.
- Với dữ liệu được tạo bên trong target, khai báo dependency để bảo đảm target tạo chạy trước target dùng.
- Kiểm tra ID trùng khi chia build thành nhiều file import.
- Phân biệt rõ reference trong cùng project với dữ liệu truyền sang project con.
- Ghi chú mục đích của reference có nhiều thành phần hoặc được nhiều target sử dụng.

Khi dùng id và refid đúng cách, build file có thể tái sử dụng cấu hình path, tập hợp tệp, bộ lọc và mapper mà không phải lặp lại từng chi tiết. Việc hiểu rõ phạm vi project và thời điểm đối tượng được tạo giúp tránh lỗi reference không tồn tại, trùng ID hoặc dùng nhầm kiểu dữ liệu.

