# Quản lý thứ tự build và sản phẩm phụ thuộc giữa các dự án trong Apache Ant

Khi một hệ thống Java được chia thành nhiều dự án hoặc module, mỗi dự án thường có buildfile riêng và tạo ra một sản phẩm trung gian như JAR, WAR, thư viện dùng chung hoặc thư mục tài nguyên. Dự án phía sau chỉ có thể biên dịch hoặc đóng gói đúng khi sản phẩm mà nó phụ thuộc đã được tạo xong và có thể tìm thấy ở vị trí đã thống nhất.

Apache Ant cho phép tổ chức quy trình nhiều dự án bằng cách điều phối các build con. Buildfile gốc xác định thứ tự các module, gọi buildfile của từng module, truyền cấu hình cần thiết và tập hợp các artifact thành sản phẩm cuối. Hai cơ chế thường dùng là task ant để gọi một buildfile cụ thể và task subant để gọi cùng một target trên nhiều buildfile.

Điểm cần nắm vững là dependency giữa target trong một buildfile và dependency giữa các dự án là hai phạm vi khác nhau. Thuộc tính depends chỉ mô tả thứ tự target trong cùng project Ant. Để gọi target thuộc buildfile khác, cần dùng cơ chế điều phối như ant hoặc subant, rồi thể hiện thứ tự module trong buildfile gốc.

## 1. Mô hình một hệ thống gồm nhiều dự án

Giả sử ứng dụng Inventory được chia thành ba module:

- common: cung cấp các lớp và tiện ích dùng chung.
- service: sử dụng common để xử lý nghiệp vụ.
- web: sử dụng service và common để cung cấp giao diện hoặc API.

Cấu trúc thư mục có thể như sau:

~~~text
inventory-suite/
├── build.xml
├── build/
│   └── artifacts/
├── dist/
└── modules/
    ├── common/
    │   ├── build.xml
    │   └── src/main/java/
    ├── service/
    │   ├── build.xml
    │   └── src/main/java/
    └── web/
        ├── build.xml
        └── src/main/java/
~~~

Mỗi module chịu trách nhiệm xây dựng sản phẩm của chính nó. Buildfile gốc điều phối thứ tự:

~~~text
common.jar
    |
    v
service.jar
    |
    v
web.jar
    |
    v
inventory-suite distribution
~~~

Module common không phụ thuộc hai module còn lại nên có thể build trước. Module service cần common.jar để biên dịch. Module web cần cả common.jar và service.jar. Gói phân phối cuối cùng chỉ được tạo sau khi các artifact cần thiết đã sẵn sàng.

Cách tổ chức này tạo ra một đồ thị phụ thuộc có hướng. Một module là prerequisite của module khác khi sản phẩm của nó được module phía sau sử dụng.

## 2. Phân biệt depends trong cùng project với phụ thuộc giữa các project

Trong một buildfile, thuộc tính depends của target khai báo target khác trong cùng project cần chạy trước:

~~~xml
<target name="compile" depends="prepare">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false" />
</target>
~~~

Quan hệ này không tự gọi buildfile của module khác. Ví dụ, nếu service cần common.jar được tạo bởi modules/common/build.xml, khai báo:

~~~xml
<target name="compile-service" depends="build-common" />
~~~

chỉ có ý nghĩa nếu target build-common đã được định nghĩa trong cùng buildfile điều phối. Ant không tự hiểu tên target hoặc tên module trong một buildfile khác.

Buildfile gốc có thể tạo target trung gian để gọi các build con:

~~~xml
<target name="build-common">
    <ant antfile="build.xml"
         dir="modules/common"
         target="jar" />
</target>

<target name="build-service" depends="build-common">
    <ant antfile="build.xml"
         dir="modules/service"
         target="jar" />
</target>
~~~

Ở đây, depends nối các target điều phối trong buildfile gốc. Task ant bên trong từng target gọi buildfile riêng của module.

Có thể hiểu:

- depends điều khiển thứ tự target trong một project Ant.
- ant gọi một buildfile khác như một build con.
- subant gọi cùng một target hoặc một cấu hình build trên nhiều buildfile.
- Artifact như JAR là sản phẩm vật lý mà module sau nhận làm đầu vào.

Không nên nhầm quan hệ giữa các module với quan hệ depends trong một buildfile. Hãy mô tả rõ cả thứ tự gọi build con lẫn đường dẫn artifact mà module tiêu thụ cần dùng.

## 3. Gọi một buildfile khác bằng task ant

Task ant thực hiện một buildfile khác trong một project Ant con. Những thuộc tính quan trọng:

| Thuộc tính | Vai trò |
|---|---|
| antfile | Buildfile cần chạy; mặc định là build.xml |
| dir | Thư mục làm basedir cho project con |
| target | Target cần gọi trong buildfile con |
| inheritAll | Có truyền các property thông thường từ project cha hay không |
| inheritRefs | Có kế thừa các reference của project cha hay không |
| output | File nhận output của build con |
| outputproperty | Property nhận output của build con |
| useNativeBasedir | Điều khiển việc dùng basedir gốc được khai báo trong buildfile con thay vì thư mục được truyền qua dir |

Ví dụ gọi target jar trong module common:

~~~xml
<target name="build-common">
    <ant antfile="build.xml"
         dir="modules/common"
         target="jar"
         inheritAll="false" />
</target>
~~~

Task ant gọi build.xml trong thư mục modules/common và yêu cầu target jar. Build con chạy đồng bộ: task ant chỉ hoàn tất sau khi build con kết thúc. Vì vậy, target kế tiếp trong buildfile cha có thể dựa vào việc build con đã hoàn thành.

Nếu không chỉ định target, Ant dùng target mặc định được khai báo trong project con. Với build nhiều module, nên chỉ định target rõ ràng để người đọc biết buildfile cha đang yêu cầu module tạo sản phẩm nào.

### 3.1. Gọi nhiều target trong build con

Có thể gọi nhiều target của build con bằng các nested element target:

~~~xml
<ant antfile="build.xml"
     dir="modules/common"
     inheritAll="false">
    <target name="clean" />
    <target name="jar" />
</ant>
~~~

Các target được yêu cầu sẽ được thực hiện theo dependency của chúng. Nếu jar đã depends vào compile, Ant xử lý prerequisite theo đồ thị trong project common.

Trong quy trình thông thường, target jar nên tự khai báo dependency nội bộ cần thiết. Buildfile cha chỉ cần gọi target công khai của module, thay vì lặp lại các bước prepare, compile và package ở bên ngoài.

### 3.2. Xử lý basedir

Thuộc tính dir xác định thư mục làm việc của build con. Điều này quan trọng vì đường dẫn tương đối trong buildfile con được phân giải theo basedir của project con.

Ví dụ, trong modules/service/build.xml:

~~~xml
<property name="src.dir" location="src/main/java" />
<property name="classes.dir" location="build/classes" />
~~~

Hai đường dẫn trên được tính từ thư mục modules/service khi buildfile được gọi với dir="modules/service".

Nếu không chỉ định dir, task ant dùng basedir của project cha làm thư mục cơ sở cho build con. Khi các module có cây thư mục riêng, nên đặt dir rõ ràng để đường dẫn nguồn, output và dependency dễ dự đoán.

## 4. Truyền property từ buildfile gốc sang module

Mỗi module thường cần nhận một số cấu hình chung:

- Phiên bản phát hành.
- Thư mục tập hợp artifact.
- Profile hoặc môi trường build.
- Đường dẫn JAR của module phụ thuộc.
- Cờ biên dịch hoặc encoding.

Có thể truyền các property này qua nested element property của task ant:

~~~xml
<property name="app.version" value="1.4.0" />
<property name="artifact.dir" location="build/artifacts" />

<target name="build-common">
    <ant antfile="build.xml"
         dir="modules/common"
         target="jar"
         inheritAll="false">
        <property name="app.version" value="${app.version}" />
        <property name="artifact.dir" value="${artifact.dir}" />
    </ant>
</target>
~~~

Build con nhận hai giá trị được truyền rõ ràng. Trong child buildfile, có thể đặt mặc định:

~~~xml
<property name="app.version" value="0.0.0-dev" />
<property name="artifact.dir" location="dist" />
~~~

Property được truyền vào build con đã được thiết lập trước khi các giá trị mặc định trong buildfile con được xử lý. Vì property Ant thông thường bất biến, các khai báo mặc định phía sau không thay thế giá trị đã nhận.

### 4.1. Hiểu inheritAll

Task ant mặc định kế thừa property từ project cha. Khi inheritAll="true", các property của cha được đưa sang build con. Điều này thuận tiện với build nhỏ nhưng có thể vô tình truyền nhiều cấu hình không liên quan, khiến module phụ thuộc vào môi trường của buildfile gốc.

Khi đặt inheritAll="false", build con chỉ nhận các property được truyền rõ ràng như user property hoặc nested property. Đây thường là cách tốt cho module có giao diện build rõ ràng: module chỉ nhận các giá trị mà buildfile cha chủ động cung cấp.

Ví dụ:

~~~xml
<ant antfile="build.xml"
     dir="modules/service"
     target="jar"
     inheritAll="false">
    <property name="app.version" value="${app.version}" />
    <property name="artifact.dir" value="${artifact.dir}" />
    <property name="common.jar" value="${common.jar}" />
</ant>
~~~

Cách này giúp service nhận đúng phiên bản, thư mục artifact và dependency cần thiết mà không phụ thuộc vào mọi property nội bộ của project cha.

### 4.2. Tránh trùng tên property

Nếu project cha và project con dùng cùng tên property cho ý nghĩa khác nhau, kế thừa property có thể tạo ra hành vi khó hiểu. Nên đặt tên có tiền tố hoặc quy ước rõ ràng, ví dụ:

- suite.version: phiên bản chung của toàn bộ sản phẩm.
- suite.artifact.dir: nơi lưu artifact dùng chung.
- service.common.jar: đường dẫn dependency common của service.
- web.service.jar: đường dẫn dependency service của web.

Property của Ant bất biến sau lần thiết lập đầu tiên. Vì vậy, một property được truyền từ cha có thể khiến giá trị mặc định trong build con không còn tác dụng. Hãy xác định property nào là cấu hình đầu vào và property nào là mặc định riêng của module.

## 5. Truyền sản phẩm phụ thuộc giữa các module

Thứ tự build chỉ có ích khi module tiêu thụ biết chính xác artifact ở đâu. Cần thống nhất hợp đồng đầu ra giữa module tạo sản phẩm và module sử dụng sản phẩm.

Ví dụ quy ước tên:

~~~text
build/artifacts/
├── common-1.4.0.jar
├── service-1.4.0.jar
└── web-1.4.0.jar
~~~

Module common tạo common-1.4.0.jar. Module service nhận đường dẫn đó làm classpath khi biên dịch. Module web nhận cả common-1.4.0.jar và service-1.4.0.jar.

Trong buildfile gốc, định nghĩa đường dẫn:

~~~xml
<property name="suite.version" value="1.4.0" />
<property name="suite.artifact.dir" location="build/artifacts" />

<property name="common.jar"
          location="${suite.artifact.dir}/common-${suite.version}.jar" />
<property name="service.jar"
          location="${suite.artifact.dir}/service-${suite.version}.jar" />
<property name="web.jar"
          location="${suite.artifact.dir}/web-${suite.version}.jar" />
~~~

Sau khi common được build, đường dẫn common.jar được truyền sang service. Sau khi service được build, service.jar được truyền sang web.

Không nên để module sau tự đoán vị trí artifact bằng cách ghép nhiều đường dẫn tương đối không thống nhất. Hãy chọn một quy ước output và tên file, rồi dùng property để truyền đường dẫn đầy đủ.

### 5.1. Dùng artifact làm classpath

Buildfile của service có thể nhận common.jar và đưa vào javac:

~~~xml
<property name="common.jar" location="../common/dist/common.jar" />

<target name="compile">
    <mkdir dir="build/classes" />

    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"
           encoding="UTF-8">
        <classpath>
            <pathelement location="${common.jar}" />
        </classpath>
    </javac>
</target>
~~~

Khi buildfile cha truyền property common.jar, giá trị mặc định trong service không thay thế nó. Khi chạy service độc lập, module vẫn có thể dùng đường dẫn mặc định nếu artifact common tồn tại ở vị trí tương ứng.

Đây là cách giúp module có thể được build độc lập trong môi trường phát triển và vẫn được điều phối bởi buildfile tổng hợp.

### 5.2. Kiểm tra artifact trước khi sử dụng

Nếu module phụ thuộc không tạo ra file như mong đợi, javac có thể báo lỗi classpath hoặc không tìm thấy kiểu dữ liệu. Có thể kiểm tra artifact trước khi gọi build con:

~~~xml
<target name="check-common">
    <available file="${common.jar}"
               type="file"
               property="common.jar.available" />
    <fail unless="common.jar.available"
          message="Required common artifact is missing: ${common.jar}" />
</target>
~~~

Trong quy trình chuẩn, target service phụ thuộc target build-common nên file phải được tạo trước. Kiểm tra tường minh vẫn hữu ích khi artifact có thể bị xóa, bị đặt sai tên hoặc được cung cấp từ một nguồn bên ngoài.

Đừng chỉ kiểm tra sự tồn tại nếu cần bảo đảm artifact đúng phiên bản. Với yêu cầu chặt hơn, có thể lưu checksum, metadata version hoặc xác minh nội dung manifest trước khi sử dụng.

## 6. Tạo đồ thị build trong buildfile gốc

Buildfile gốc là nơi thích hợp để mô tả thứ tự module. Ví dụ:

~~~xml
<project name="inventory-suite"
         default="release"
         basedir=".">

    <property name="suite.version" value="1.4.0" />
    <property name="suite.artifact.dir" location="build/artifacts" />

    <property name="common.jar"
              location="${suite.artifact.dir}/common-${suite.version}.jar" />
    <property name="service.jar"
              location="${suite.artifact.dir}/service-${suite.version}.jar" />

    <target name="prepare">
        <mkdir dir="${suite.artifact.dir}" />
    </target>

    <target name="build-common" depends="prepare">
        <ant antfile="build.xml"
             dir="modules/common"
             target="jar"
             inheritAll="false">
            <property name="app.version" value="${suite.version}" />
            <property name="artifact.dir" value="${suite.artifact.dir}" />
        </ant>
    </target>

    <target name="build-service" depends="build-common">
        <ant antfile="build.xml"
             dir="modules/service"
             target="jar"
             inheritAll="false">
            <property name="app.version" value="${suite.version}" />
            <property name="artifact.dir" value="${suite.artifact.dir}" />
            <property name="common.jar" value="${common.jar}" />
        </ant>
    </target>

    <target name="build-web" depends="build-service">
        <ant antfile="build.xml"
             dir="modules/web"
             target="jar"
             inheritAll="false">
            <property name="app.version" value="${suite.version}" />
            <property name="artifact.dir" value="${suite.artifact.dir}" />
            <property name="common.jar" value="${common.jar}" />
            <property name="service.jar" value="${service.jar}" />
        </ant>
    </target>

    <target name="release" depends="build-web">
        <zip destfile="dist/inventory-suite-${suite.version}.zip">
            <fileset dir="${suite.artifact.dir}">
                <include name="*.jar" />
            </fileset>
        </zip>
    </target>
</project>
~~~

Buildfile gốc thể hiện rõ thứ tự:

1. prepare tạo thư mục artifact.
2. build-common gọi buildfile common và tạo common.jar.
3. build-service chỉ chạy sau build-common và nhận đường dẫn common.jar.
4. build-web chỉ chạy sau build-service và nhận common.jar cùng service.jar.
5. release tạo gói phân phối sau khi các module đã hoàn thành.

Task ant là thao tác đồng bộ nên khi target build-common hoàn tất, Ant mới chuyển sang target build-service. Quan hệ depends ở buildfile gốc làm thứ tự này rõ ràng và có thể quan sát bằng log.

Trong các buildfile module, target jar nên tự depends vào compile hoặc target chuẩn bị tương ứng. Như vậy, mỗi module vẫn chịu trách nhiệm quy trình nội bộ của mình.

## 7. Ví dụ buildfile của module tạo JAR

Buildfile modules/common/build.xml có thể đơn giản:

~~~xml
<project name="common" default="jar" basedir=".">
    <property name="app.version" value="dev" />
    <property name="artifact.dir" location="dist" />
    <property name="src.dir" location="src/main/java" />
    <property name="classes.dir" location="build/classes" />

    <target name="clean">
        <delete dir="build" />
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}" />
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8" />
    </target>

    <target name="jar" depends="compile">
        <mkdir dir="${artifact.dir}" />
        <jar destfile="${artifact.dir}/common-${app.version}.jar"
             basedir="${classes.dir}" />
    </target>
</project>
~~~

Khi gọi độc lập từ thư mục modules/common:

~~~bash
ant jar
~~~

Module dùng giá trị mặc định app.version=dev và artifact.dir=dist.

Khi được gọi từ buildfile gốc, các nested property app.version và artifact.dir được truyền vào, nên module tạo JAR đúng phiên bản và đúng thư mục artifact chung.

Đây là một hợp đồng đơn giản: build con nhận property đầu vào và tạo một artifact có tên xác định. Buildfile cha không cần biết module biên dịch bao nhiêu source file hoặc có bao nhiêu target nội bộ.

## 8. Ví dụ buildfile của module tiêu thụ JAR

Module service cần common.jar:

~~~xml
<project name="service" default="jar" basedir=".">
    <property name="app.version" value="dev" />
    <property name="artifact.dir" location="dist" />
    <property name="common.jar" location="../common/dist/common-dev.jar" />
    <property name="src.dir" location="src/main/java" />
    <property name="classes.dir" location="build/classes" />

    <target name="clean">
        <delete dir="build" />
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}" />

        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath>
                <pathelement location="${common.jar}" />
            </classpath>
        </javac>
    </target>

    <target name="jar" depends="compile">
        <mkdir dir="${artifact.dir}" />
        <jar destfile="${artifact.dir}/service-${app.version}.jar"
             basedir="${classes.dir}" />
    </target>
</project>
~~~

Module service không tự build common trong buildfile của nó. Nó sử dụng common.jar đã được cung cấp. Buildfile gốc chịu trách nhiệm bảo đảm common được build trước và truyền đúng đường dẫn.

Tách trách nhiệm như vậy tránh việc nhiều module tự gọi lẫn nhau theo các hướng khó theo dõi. Buildfile gốc điều phối; buildfile module thực hiện công việc nội bộ và công bố artifact.

## 9. Gọi cùng một target trên nhiều dự án bằng subant

Khi nhiều module độc lập có cùng target, ví dụ clean hoặc test, có thể dùng task subant để gọi target đó trên nhiều buildfile.

Ví dụ chạy target test trong mọi module có build.xml ngay dưới thư mục modules:

~~~xml
<target name="test-all">
    <subant target="test"
            inheritAll="false"
            failonerror="true">
        <fileset dir="modules">
            <include name="*/build.xml" />
        </fileset>
    </subant>
</target>
~~~

Task subant tìm các buildfile theo FileSet rồi gọi target test trong từng build. Cách này giảm việc khai báo lặp một task ant cho từng module.

Có thể dùng subant cho các thao tác chung như:

- clean trên nhiều module.
- test trên các module độc lập.
- validate buildfile hoặc kiểm tra tài liệu.
- Chạy một target chuẩn hóa trên tập dự án được chọn.

### 9.1. Không dùng thứ tự quét FileSet làm đồ thị dependency

Khi module phụ thuộc sản phẩm của module khác, không nên dựa vào thứ tự file mà FileSet tìm thấy để bảo đảm build đúng. Thứ tự duyệt file có thể không thể hiện quan hệ phụ thuộc nghiệp vụ và có thể thay đổi theo môi trường hoặc cấu trúc thư mục.

Với module có quan hệ producer-consumer, hãy khai báo target điều phối rõ ràng bằng depends và gọi ant theo đúng thứ tự. Dùng subant cho các module độc lập hoặc các thao tác có cùng target mà không cần thứ tự đặc biệt.

Nếu muốn điều phối một danh sách buildfile theo thứ tự xác định, hãy tạo danh sách tường minh hoặc các target trung gian thay vì dùng wildcard rộng rồi hy vọng kết quả quét khớp thứ tự dependency.

### 9.2. Cấu hình buildpath của subant

Subant hỗ trợ các cách chỉ định buildfile thông qua buildpath và các resource collection như FileSet hoặc FileList. Với một danh sách module cố định, FileList có thể thể hiện rõ từng buildfile hơn:

~~~xml
<subant target="clean"
        inheritAll="false"
        failonerror="true">
    <filelist dir="."
              files="modules/common/build.xml,modules/service/build.xml,modules/web/build.xml" />
</subant>
~~~

FileList giúp liệt kê rõ các buildfile cần chạy. Tuy vậy, với dependency giữa các module, vẫn nên dùng các target điều phối riêng để thể hiện prerequisite và truyền artifact path cần thiết.

## 10. Phân biệt ant, subant và antcall

Ba task này có mục đích khác nhau:

| Task | Phạm vi | Trường hợp phù hợp |
|---|---|---|
| ant | Gọi một buildfile/project con cụ thể | Gọi target jar của module common hoặc service |
| subant | Gọi buildfile trên một tập dự án | Chạy clean/test trên nhiều module |
| antcall | Gọi target khác trong cùng buildfile hiện tại | Tái sử dụng một target trong cùng project |

Ví dụ antcall:

~~~xml
<target name="prepare-release">
    <antcall target="compile" />
    <antcall target="test" />
</target>
~~~

antcall không phải cơ chế gọi buildfile module khác. Nếu cần chạy target trong modules/common/build.xml, dùng ant hoặc subant.

Không nên lạm dụng antcall để tạo đồ thị phụ thuộc phức tạp trong cùng project. Thuộc tính depends thường rõ ràng hơn khi một target luôn cần target khác chạy trước.

## 11. Truyền reference và classpath giữa các build

Task ant có thuộc tính inheritRefs để kế thừa reference từ project cha. Mặc định inheritRefs là false. Có thể bật khi thực sự cần dùng lại reference, nhưng cần hiểu rủi ro:

- Reference có thể chứa đối tượng gắn với project cha.
- Không phải mọi datatype hoặc reference đều có thể dùng an toàn trong project con.
- Tên reference trùng nhau có thể gây xung đột.
- Một Path chứa đường dẫn tương đối có thể được hiểu khác khi basedir của child thay đổi.

Thông thường, truyền property chứa đường dẫn artifact rõ ràng sẽ dễ kiểm soát hơn truyền cả reference classpath.

Ví dụ, thay vì cố kế thừa reference compile.classpath từ cha, truyền các dependency dưới dạng property:

~~~xml
<ant antfile="build.xml"
     dir="modules/service"
     target="jar"
     inheritAll="false"
     inheritRefs="false">
    <property name="common.jar" value="${common.jar}" />
</ant>
~~~

Build con tự tạo classpath bằng Path dựa trên property common.jar. Cách này giữ module độc lập với object nội bộ của project cha.

Nếu thật sự cần reference, task ant có thể dùng nested reference để ánh xạ refid từ project cha sang tên trong project con. Chỉ dùng khi reference đó được thiết kế để chia sẻ và đường dẫn của nó có ý nghĩa trong cả hai project. Với build nhiều module, property artifact path thường là giao diện ổn định và dễ đọc hơn.

## 12. Xử lý lỗi khi build module phụ thuộc

Một build con thất bại thường phải làm buildfile gốc dừng lại. Nếu common không tạo được JAR, service không nên tiếp tục biên dịch với artifact cũ hoặc artifact thiếu.

Với task ant, lỗi từ build con được truyền về build cha và làm target gọi thất bại. Với subant, thuộc tính failonerror mặc định là true; khi một build con lỗi, task báo lỗi và build cha thất bại.

Ví dụ:

~~~xml
<target name="build-service" depends="build-common">
    <ant antfile="build.xml"
         dir="modules/service"
         target="jar"
         inheritAll="false">
        <property name="common.jar" value="${common.jar}" />
    </ant>
</target>
~~~

Không nên cấu hình bỏ qua lỗi chỉ để pipeline tiếp tục nếu module phía sau cần artifact vừa được tạo. Nếu muốn chạy các bước thu log hoặc cleanup sau khi một module thất bại, hãy thiết kế riêng target xử lý lỗi và ghi nhận trạng thái rõ ràng.

### 12.1. Kiểm tra artifact đầu ra sau build

Có thể kiểm tra file được tạo:

~~~xml
<target name="build-common" depends="prepare">
    <ant antfile="build.xml"
         dir="modules/common"
         target="jar"
         inheritAll="false">
        <property name="app.version" value="${suite.version}" />
        <property name="artifact.dir" value="${suite.artifact.dir}" />
    </ant>

    <available file="${common.jar}"
               type="file"
               property="common.jar.created" />
    <fail unless="common.jar.created"
          message="Common module did not create the expected JAR." />
</target>
~~~

Việc kiểm tra này phát hiện trường hợp build con kết thúc mà artifact mong đợi không nằm ở đúng vị trí hoặc tên file không khớp. Nếu artifact có thể tồn tại từ lần build trước, hãy xóa hoặc cách ly output cũ trước khi build để tránh nhầm file cũ với kết quả mới.

## 13. Xây dựng và dọn dẹp theo đúng thứ tự

Thứ tự build thường đi từ module nền đến module tiêu thụ:

~~~text
common -> service -> web -> distribution
~~~

Thứ tự clean thường ngược lại khi thao tác dọn dẹp cần giữ các sản phẩm mà module khác còn sử dụng. Ví dụ, nếu web hoặc service cần artifact common để hoàn tất một bước cleanup, hãy clean consumer trước rồi mới clean producer.

Tuy nhiên, nếu clean chỉ xóa thư mục build riêng của từng module và không cần đọc artifact phụ thuộc, các module có thể được dọn theo thứ tự bất kỳ. Hãy xác định tác dụng thực tế của target clean thay vì mặc định thứ tự ngược luôn bắt buộc.

Một target clean-all có thể gọi từng buildfile:

~~~xml
<target name="clean-all">
    <ant antfile="build.xml" dir="modules/web" target="clean" />
    <ant antfile="build.xml" dir="modules/service" target="clean" />
    <ant antfile="build.xml" dir="modules/common" target="clean" />
    <delete dir="build/artifacts" />
    <delete dir="dist" />
</target>
~~~

Target này clean các module theo thứ tự consumer trước, producer sau, rồi xóa thư mục artifact tổng hợp.

## 14. Tổ chức sản phẩm phụ thuộc ở thời gian biên dịch và thời gian chạy

Một module có thể cần dependency ở hai giai đoạn:

- Compile-time: compiler cần các kiểu dữ liệu được tham chiếu trong mã nguồn.
- Runtime: JVM cần các lớp và resource để thực thi ứng dụng.

Ví dụ service biên dịch với common.jar. Khi web chạy, nó có thể cần cả service.jar và common.jar. Việc chỉ đưa dependency vào classpath javac không tự động làm chúng xuất hiện trong gói phân phối.

Có thể tổ chức runtime distribution:

~~~text
inventory-suite/
├── bin/
│   └── run.sh
├── lib/
│   ├── common-1.4.0.jar
│   ├── service-1.4.0.jar
│   └── web-1.4.0.jar
└── conf/
    └── application.properties
~~~

Buildfile gốc có thể copy artifact vào lib và tạo ZIP:

~~~xml
<target name="distribution" depends="build-web">
    <mkdir dir="dist/inventory-suite/lib" />

    <copy todir="dist/inventory-suite/lib">
        <fileset dir="${suite.artifact.dir}">
            <include name="common-${suite.version}.jar" />
            <include name="service-${suite.version}.jar" />
            <include name="web-${suite.version}.jar" />
        </fileset>
    </copy>

    <copy todir="dist/inventory-suite/conf">
        <fileset dir="config">
            <include name="*.properties" />
        </fileset>
    </copy>

    <zip destfile="dist/inventory-suite-${suite.version}.zip"
         basedir="dist/inventory-suite" />
</target>
~~~

Cần thêm script hoặc manifest Class-Path phù hợp để ứng dụng chạy với các JAR trong lib. Không nên giả định rằng việc đóng gói nhiều JAR vào ZIP tự động khiến JVM nhận biết chúng; script khởi chạy phải cung cấp classpath hoặc dùng cơ chế nạp dependency tương ứng.

## 15. Giữ phiên bản dependency nhất quán

Một lỗi phổ biến trong build nhiều module là common.jar và service.jar được tạo từ các phiên bản không tương thích. Ví dụ web được build với service 1.4.0 nhưng lại đóng gói common 1.3.0.

Hãy dùng một property phiên bản chung trong buildfile gốc và truyền nó cho mọi module:

~~~xml
<property name="suite.version" value="1.4.0" />
~~~

Tên artifact có thể chứa cùng version:

~~~text
common-1.4.0.jar
service-1.4.0.jar
web-1.4.0.jar
~~~

Nếu các module có vòng đời phiên bản độc lập, cần mô tả rõ phiên bản dependency tương thích thay vì buộc tất cả cùng số version. Có thể truyền riêng common.version và service.version khi cần.

Không nên dùng tên artifact không có version nếu thư mục repository có thể chứa sản phẩm của nhiều lượt build. Tên có version giúp phát hiện nhầm lẫn và hỗ trợ lưu nhiều bản phát hành.

## 16. Build độc lập và build tổng hợp

Một module tốt nên hỗ trợ cả hai cách sử dụng:

1. Build độc lập trong thư mục module với các giá trị mặc định hoặc dependency đã cài đặt.
2. Build từ buildfile gốc với các property được truyền rõ ràng và thứ tự module được điều phối.

Ví dụ, service có thể mặc định common.jar ở vị trí tương đối trong workspace để lập trình viên chạy riêng. Buildfile gốc lại truyền đường dẫn artifact tập trung vào build/artifacts.

Điều này giúp module dễ phát triển mà không làm build tổng hợp phụ thuộc vào cấu hình máy cá nhân.

Một số nguyên tắc:

- Target công khai của module nên có tên ổn định như compile, test, jar, clean.
- Target jar nên phụ thuộc vào compile.
- Buildfile module nên cung cấp default cho property cần thiết khi chạy độc lập.
- Buildfile gốc nên truyền property rõ ràng và đặt inheritAll=false khi muốn giới hạn cấu hình.
- Artifact đầu ra phải có tên và vị trí nhất quán.
- Module tiêu thụ nên kiểm tra dependency đầu vào khi có thể.

## 17. Khi nào dùng subant, khi nào dùng ant?

Chọn ant khi:

- Gọi một module cụ thể.
- Cần truyền các artifact path riêng cho module đó.
- Cần thể hiện dependency rõ ràng giữa producer và consumer.
- Cần chọn target khác nhau cho từng module.

Chọn subant khi:

- Nhiều module có cùng cấu trúc build.
- Muốn chạy cùng target trên nhiều buildfile.
- Các module độc lập hoặc thứ tự không phải yếu tố quan trọng.
- Có thể chọn tập buildfile bằng FileSet, FileList hoặc buildpath.

Nếu một module phụ thuộc module khác, cách dễ hiểu thường là target điều phối rõ ràng với task ant. Không dùng subant quét wildcard như một bộ lập lịch dependency vì nó không tự phân tích sản phẩm nào cần được tạo trước.

## 18. Lỗi thường gặp

### 18.1. Nghĩ rằng depends gọi được target ở buildfile khác

depends chỉ tham chiếu target trong cùng project. Dùng ant hoặc subant để gọi buildfile con, rồi dùng depends để sắp xếp target điều phối ở buildfile gốc.

### 18.2. Module sau chạy trước khi artifact được tạo

Kiểm tra target điều phối có khai báo depends đúng không. Task ant chạy đồng bộ, nhưng nếu target cha không khai báo quan hệ prerequisite, Ant không tự biết thứ tự module cần thiết.

### 18.3. Sai basedir khiến đường dẫn dependency không tìm thấy

Khi gọi build con, kiểm tra dir và cách các đường dẫn tương đối được phân giải. Dùng property location hoặc truyền đường dẫn đầy đủ để giảm phụ thuộc vào thư mục gọi lệnh.

### 18.4. Property mặc định của module ghi đè cấu hình mong muốn

Property Ant bất biến. Nếu build cha truyền property vào child, giá trị mặc định khai báo sau trong child không thay thế nó. Kiểm tra tên property và dùng inheritAll phù hợp.

### 18.5. Kế thừa quá nhiều property

inheritAll mặc định true có thể truyền cấu hình nội bộ không cần thiết sang build con. Dùng inheritAll=false và truyền các property module cần qua nested property.

### 18.6. Kế thừa reference classpath không an toàn

Reference có thể chứa object hoặc đường dẫn gắn với project cha. Mặc định inheritRefs=false là lựa chọn an toàn hơn; ưu tiên truyền artifact path và để module tự tạo Path.

### 18.7. Dùng subant wildcard cho module có dependency

Tập buildfile được tìm thấy không phải đồ thị dependency. Tạo target điều phối và gọi module theo thứ tự tường minh.

### 18.8. Artifact cũ che giấu lỗi build mới

Nếu file JAR cũ vẫn còn, module tiêu thụ có thể vô tình dùng nó dù producer không tạo artifact mới. Clean output hoặc kiểm tra timestamp/checksum/version trước khi sử dụng.

### 18.9. Compile có dependency nhưng runtime thiếu dependency

Classpath biên dịch và runtime là hai cấu hình riêng. Hãy đưa các JAR cần thiết vào gói phân phối và script khởi chạy.

### 18.10. Bỏ qua lỗi của build con

Nếu common build thất bại, không tiếp tục build service dựa trên artifact cũ. Giữ hành vi fail-fast hoặc thu thập lỗi có kiểm soát trước khi quyết định bước tiếp theo.

## 19. Thực hành tốt

- **Dùng buildfile gốc làm bộ điều phối.** Để mỗi module tự quản lý compile, test và package nội bộ.
- **Mô hình hóa quan hệ producer-consumer.** Module tạo JAR phải chạy trước module sử dụng JAR đó.
- **Dùng depends cho target điều phối.** depends không gọi project khác nhưng nối các bước orchestration trong buildfile gốc.
- **Dùng ant cho module có dependency cụ thể.** Truyền target và artifact path rõ ràng.
- **Dùng subant cho các thao tác đồng nhất trên module độc lập.** Không dựa vào thứ tự quét wildcard để lập lịch dependency.
- **Đặt basedir rõ ràng.** Mỗi child build nên chạy trong thư mục module tương ứng.
- **Giới hạn property inheritance.** Dùng inheritAll=false và truyền các property module thực sự cần.
- **Hạn chế kế thừa reference.** Truyền đường dẫn artifact thay vì object classpath của project cha khi có thể.
- **Đặt quy ước artifact ổn định.** Dùng tên có module và version, lưu trong thư mục chung hoặc repository đã thống nhất.
- **Kiểm tra đầu ra producer.** Xác nhận file tồn tại và đúng phiên bản trước khi consumer biên dịch.
- **Giữ compile-time và runtime dependency đầy đủ.** Module chạy được sau khi đóng gói phải nhận đủ các JAR cần thiết.
- **Dừng khi prerequisite thất bại.** Tránh build tiếp với artifact cũ hoặc thiếu.
- **Giữ khả năng build độc lập.** Mỗi module nên có default hợp lý và target công khai.
- **Dọn output cũ có chủ đích.** Tránh artifact cũ bị nhầm là kết quả của lần build hiện tại.

## 20. Kết luận

Quản lý nhiều dự án trong Apache Ant cần hai lớp điều phối: mỗi buildfile quản lý thứ tự target nội bộ bằng depends, còn buildfile gốc gọi các build con bằng ant hoặc subant và xác định thứ tự giữa các module. Khi module tiêu thụ cần sản phẩm của module khác, buildfile gốc phải bảo đảm producer hoàn thành trước, truyền đường dẫn artifact và giữ phiên bản nhất quán.

Task ant phù hợp để gọi một module cụ thể và truyền property riêng. Task subant phù hợp khi cần chạy cùng target trên nhiều buildfile, đặc biệt với các module độc lập. Dùng inheritAll=false và truyền cấu hình tường minh giúp giảm phụ thuộc ngầm; dùng artifact path ổn định giúp module không cần chia sẻ object nội bộ của project cha. Khi đồ thị build rõ ràng, các module có thể được phát triển riêng, build tổng hợp dễ theo dõi và gói phân phối có thể tái tạo.

## Tài liệu tham khảo

- [Apache Ant Ant Task](https://ant.apache.org/manual/Tasks/ant.html)
- [Apache Ant SubAnt Task](https://ant.apache.org/manual/Tasks/subant.html)
- [Apache Ant Targets and Dependencies](https://ant.apache.org/manual/targets.html)
- [Apache Ant Property Task](https://ant.apache.org/manual/Tasks/property.html)
- [Apache Ant Path-like Structures](https://ant.apache.org/manual/using.html#path)

