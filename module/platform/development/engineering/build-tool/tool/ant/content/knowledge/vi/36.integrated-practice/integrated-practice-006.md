# Tách build chung bằng macrodef, import và extension-point trong Apache Ant

## 1. Bài toán: nhiều buildfile lặp cùng một quy trình

Khi mới học Apache Ant, chúng ta thường viết toàn bộ công việc vào một **build.xml**: tạo thư mục, chạy **javac**, chép resources, đóng JAR và kiểm tra artifact. Cách này dễ hiểu với một dự án nhỏ. Nhưng khi có nhiều ứng dụng Java cùng dùng Ant, việc sao chép nguyên các target sang từng ứng dụng nhanh chóng tạo ra vấn đề:

- Một dự án quên đặt **encoding** trong **javac**, dự án khác lại dùng nhầm JDK hoặc classpath.
- Khi cần sửa cách copy resources hoặc đóng gói, người bảo trì phải thay nhiều buildfile.
- Thêm một bước kiểm tra cho riêng ứng dụng A có nguy cơ làm ảnh hưởng cả ứng dụng B.
- Các target và property trùng tên bị ghi đè khó phát hiện khi tách file thiếu kế hoạch.

Ant có ba cơ chế bổ trợ rất phù hợp để giải quyết bài toán:

| Cơ chế | Mục đích | Trả lời câu hỏi |
|---|---|---|
| **macrodef** | Định nghĩa một *thao tác* có tham số, có thể gọi nhiều nơi | “Làm sao dùng lại cùng chuỗi task với đầu vào khác?” |
| **import** | Ghép các định nghĩa từ buildfile chung vào project đang thực thi | “Làm sao dùng chung các macro, target và hook giữa nhiều buildfile?” |
| **extension-point** | Khai báo điểm móc để project hoặc file import khác đóng góp target riêng | “Làm sao thêm hành vi vào một giai đoạn mà không sửa trực tiếp buildfile chung?” |

Ba cơ chế có vai trò khác nhau. **macrodef** giống một thao tác dùng lại; **import** chia sẻ định nghĩa giữa file; **extension-point** tạo điểm mở rộng trong đồ thị target. Dùng chúng đúng chỗ giúp giữ một quy trình chung nhưng vẫn cho phép mỗi ứng dụng có phần tùy biến.

Trong bài thực hành, ta sẽ tách một buildfile đơn thành ba file XML mà vẫn giữ giao diện:

~~~text
ant clean verify
~~~

và vẫn tạo artifact:

~~~text
out/dist/demo.jar
~~~

## 2. Thiết kế trước: hợp đồng đầu ra và ranh giới dùng chung

Giả sử một ứng dụng Java đơn giản cần:

1. Biên dịch Java source bằng JDK 17, encoding UTF-8.
2. Copy resource từ **src/main/resources** vào cùng gốc class directory.
3. Sinh một file thông tin ứng dụng vào **META-INF/build-info.txt**.
4. Đóng **build/classes** thành **build/dist/demo.jar**.
5. Xác nhận file JAR tồn tại; khi cần có thể nối thêm kiểm thử riêng.

Người hoặc pipeline gọi Ant chỉ cần biết **clean**, **compile**, **stage**, **package**, **verify**. Ta sẽ giữ những tên target công khai này, giữ đường dẫn JAR, dữ liệu class/resource và thứ tự xử lý.

Ranh giới tách phần chung được chọn như sau:

~~~text
build/common.xml
  ├── macrodef compile-java
  ├── macrodef stage-resources
  ├── target clean / compile / stage / package / verify
  └── extension-point before-package / after-package

build/checks.xml
  └── target check-jar
        extensionOf="after-package"

build.xml của ứng dụng
  ├── đường dẫn và tên artifact riêng
  ├── import common.xml
  ├── import checks.xml
  └── target write-app-metadata
        extensionOf="before-package"
~~~

**common.xml** sẽ không biết application name hay output path cụ thể. Nó lấy các giá trị này từ project chính. Project chính lựa chọn **tên artifact, thư mục mã nguồn, thư mục output** và đóng góp metadata của ứng dụng vào điểm mở rộng trước khi đóng JAR.

## 3. Chuẩn bị cấu trúc dự án thực hành

~~~text
ant-modular-demo/
├── build.xml
├── build/
│   ├── common.xml
│   └── checks.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── Main.java
        └── resources/
            └── config.properties
~~~

Ở cấu trúc trên, thư mục **build/** ban đầu chứa *build definitions* (**common.xml**, **checks.xml**). Để tránh xóa nhầm các file này, output do Ant sinh sẽ được đặt vào **out/** trong các ví dụ hoàn chỉnh bên dưới. Đường dẫn artifact chính thức của bài thực hành là **out/dist/demo.jar**.

Đây là một quyết định quan trọng về **quyền sở hữu file**: không nên dùng target **clean** xóa một thư mục vừa chứa đầu ra sinh tự động, vừa chứa XML nguồn phải được giữ lại.

Vì vậy, cấu trúc khi đã build thành công sẽ là:

~~~text
ant-modular-demo/
├── build.xml
├── build/
│   ├── common.xml
│   └── checks.xml
├── src/
│   └── main/...
└── out/                        # Ant sinh ra, có thể xóa bằng clean
    ├── classes/
    │   ├── example/Main.class
    │   ├── config.properties
    │   └── META-INF/build-info.txt
    └── dist/
        └── demo.jar
~~~

**src/main/java/example/Main.java**:

~~~java
package example;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from a modular Ant build!");
    }
}
~~~

**src/main/resources/config.properties**:

~~~properties
application.name=ant-modular-demo
application.mode=example
~~~

Bài thực hành dùng cú pháp XML tiêu chuẩn của **Apache Ant 1.10.x** và JDK 17 trở lên. **extension-point** được hỗ trợ trong Ant từ dòng 1.8; các task thông dụng khác đã có từ trước. Ví dụ không cần thư viện bên ngoài JDK/Ant.

## 4. macrodef: tách những thao tác thường lặp

### 4.1. Macro khác target ở điểm nào?

Một **target** là nút của đồ thị build. Nó có tên, có thể được gọi qua lệnh **ant target-name**, và có thể khai báo **depends**, **if** hoặc **unless**.

Một **macrodef** lại định nghĩa một *loại task mới* gồm nhiều task con trong **sequential**. Nó có **attribute** để nhận giá trị khác nhau mỗi lần gọi. Macro thường được sử dụng **bên trong target**; nó không tạo một target public mới và không có đồ thị **depends** riêng.

Ví dụ, hai ứng dụng khác nhau đều cần **mkdir** rồi **javac**; điểm thay đổi chỉ là source path và output path. Đó là ứng viên tốt cho macrodef:

~~~xml
<macrodef name="compile-java">
    <attribute name="source"/>
    <attribute name="destination"/>
    <attribute name="java-version" default="17"/>
    <sequential>
        <mkdir dir="@{destination}"/>
        <javac srcdir="@{source}"
               destdir="@{destination}"
               release="@{java-version}"
               encoding="UTF-8"
               includeantruntime="false"/>
    </sequential>
</macrodef>
~~~

Khi sử dụng:

~~~xml
<compile-java source="src/main/java"
              destination="out/classes"
              java-version="17"/>
~~~

Ant sẽ thực thi chuỗi **mkdir → javac** theo các giá trị được truyền.

### 4.2. Phân biệt @{attribute} và property của Ant

Trong macrodef:

- **@{source}** là tham chiếu **attribute của macro**. Giá trị được truyền riêng cho từng lần gọi.
- **${source.dir}** là tham chiếu **property của Ant project**. Giá trị đến từ buildfile, file properties hoặc tham số **-D** theo quy tắc của Ant.

Ví dụ:

~~~xml
<property name="source.dir" location="src/main/java"/>

<compile-java source="${source.dir}"
              destination="out/classes"/>
~~~

Ở đây project quyết định **source.dir**, sau đó truyền giá trị vào attribute **source**. Tách hai loại tham chiếu giúp macro không phụ thuộc vào tên property của một ứng dụng cụ thể.

Một macro thứ hai copy resources:

~~~xml
<macrodef name="stage-resources">
    <attribute name="from"/>
    <attribute name="to"/>
    <sequential>
        <mkdir dir="@{to}"/>
        <copy todir="@{to}">
            <fileset dir="@{from}" includes="**/*"/>
        </copy>
    </sequential>
</macrodef>
~~~

Macro này giữ cấu trúc thư mục resource tính từ **from**, và đưa chúng vào **to**. Với ví dụ, **config.properties** sẽ có mặt ở gốc output classes.

### 4.3. Khi macro có quá nhiều tham số

Không nên biến mọi bước build thành một macro lớn với hàng chục attribute và nhánh điều kiện. Một macro có trách nhiệm rõ, như **compile-java** hay **stage-resources**, thường dễ kiểm tra hơn. Những quyết định lớn về **target nào chạy trước**, **khi nào đóng gói** và **khi nào kiểm tra** nên nằm ở đồ thị target thay vì ẩn trong macro.

Nếu macro cần nhận một nhóm task con tùy biến, Ant còn hỗ trợ nested element trong **macrodef**. Ví dụ minh họa:

~~~xml
<macrodef name="with-output-dir">
    <attribute name="dir"/>
    <element name="steps"/>
    <sequential>
        <mkdir dir="@{dir}"/>
        <steps/>
    </sequential>
</macrodef>

<with-output-dir dir="out/reports">
    <steps>
        <echo file="out/reports/info.txt"
              message="Report directory is ready"/>
    </steps>
</with-output-dir>
~~~

Đây là cách truyền một phần tử con có cấu trúc; nó hữu ích khi cần chèn một chuỗi task tùy chọn vào một thao tác chung. Không cần dùng nested element cho mọi macro nếu vài attribute đã diễn đạt đủ nhiệm vụ.

## 5. import: chia sẻ định nghĩa giữa nhiều buildfile

### 5.1. File build/common.xml

Tạo **build/common.xml** với nội dung đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="common">
    <!-- Các thao tác chia sẻ -->
    <macrodef name="compile-java">
        <attribute name="source"/>
        <attribute name="destination"/>
        <attribute name="java-version" default="17"/>
        <sequential>
            <mkdir dir="@{destination}"/>
            <javac srcdir="@{source}"
                   destdir="@{destination}"
                   release="@{java-version}"
                   encoding="UTF-8"
                   includeantruntime="false"/>
        </sequential>
    </macrodef>

    <macrodef name="stage-resources">
        <attribute name="from"/>
        <attribute name="to"/>
        <sequential>
            <mkdir dir="@{to}"/>
            <copy todir="@{to}">
                <fileset dir="@{from}" includes="**/*"/>
            </copy>
        </sequential>
    </macrodef>

    <!-- Các hook mở rộng được khai báo trước khi sử dụng. -->
    <extension-point name="before-package"
                     description="Optional tasks before packaging"/>
    <extension-point name="after-package"
                     description="Optional checks after packaging"/>

    <target name="clean" description="Remove generated outputs">
        <delete dir="${output.dir}"/>
    </target>

    <target name="compile" description="Compile Java source">
        <compile-java source="${source.dir}"
                      destination="${classes.dir}"
                      java-version="${java.release}"/>
    </target>

    <target name="stage" depends="compile"
            description="Copy application resources">
        <stage-resources from="${resources.dir}"
                         to="${classes.dir}"/>
    </target>

    <target name="package" depends="stage,before-package"
            description="Package the application JAR">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/${jar.name}"
             basedir="${classes.dir}"
             includes="**/*"/>
    </target>

    <target name="verify" depends="package,after-package"
            description="Build and run additional checks"/>
</project>
~~~

Điểm quan trọng:

**common.xml không tự quyết định source.dir hoặc jar.name.** Nó khai báo các target chung nhưng chờ project nhập nó cung cấp property. Điều đó giúp cùng file chung phục vụ nhiều ứng dụng.

**stage depends="compile"** bảo đảm Java class đã được biên dịch trước khi resources được copy vào classes directory. **package depends="stage,before-package"** bảo đảm resources và các phần mở rộng trước đóng gói đã được thực thi. **verify depends="package,after-package"** chỉ chạy hook kiểm tra sau khi có JAR.

Target **clean** xóa duy nhất **output.dir**, được project chính đặt là **out**. Nó không xóa **build/common.xml** hay **build/checks.xml**.

### 5.2. File build/checks.xml

Tạo **build/checks.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="checks">
    <target name="check-jar" extensionOf="after-package"
            description="Verify that the packaged JAR exists">
        <available file="${dist.dir}/${jar.name}"
                   type="file"
                   property="jar.exists"/>
        <fail unless="jar.exists"
              message="Expected JAR was not created"/>
        <echo message="Found ${dist.dir}/${jar.name}"/>
    </target>
</project>
~~~

Trong file này, **extensionOf="after-package"** đăng ký **check-jar** là một target mở rộng cho extension point có tên **after-package**. Khi Ant thực thi **after-package** trong đồ thị phụ thuộc của **verify**, target **check-jar** được chạy như một phần của hook đó.

Đây là kiểm tra file tồn tại để minh họa cơ chế extension-point; nó chưa phải bộ unit test hay kiểm chứng toàn bộ nội dung JAR.

### 5.3. File build.xml của ứng dụng

File **build.xml** ở root:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="demo-app" default="verify" basedir=".">
    <!-- Cấu hình thuộc sở hữu của ứng dụng -->
    <property name="source.dir" location="src/main/java"/>
    <property name="resources.dir" location="src/main/resources"/>
    <property name="output.dir" location="out"/>
    <property name="classes.dir" location="out/classes"/>
    <property name="dist.dir" location="out/dist"/>
    <property name="jar.name" value="demo.jar"/>
    <property name="java.release" value="17"/>

    <!-- Đưa các định nghĩa chung vào project hiện tại -->
    <import file="build/common.xml"/>
    <import file="build/checks.xml"/>

    <!-- Tùy biến riêng của ứng dụng, không sửa common.xml -->
    <target name="write-app-metadata" extensionOf="before-package">
        <mkdir dir="${classes.dir}/META-INF"/>
        <echo file="${classes.dir}/META-INF/build-info.txt"
              message="module=demo-app"
              encoding="UTF-8"/>
    </target>
</project>
~~~

Đây là file mà người dùng gọi:

~~~bash
ant -f build.xml clean verify
~~~

Lệnh **clean** xóa output đã sinh, còn **verify** sử dụng các target từ **common.xml** và các hook do ứng dụng/ **checks.xml** đóng góp. Các property ở project chính được chia sẻ cho các định nghĩa đã import trong cùng project Ant.

### 5.4. Luồng thực thi của ví dụ

~~~mermaid
flowchart TD
    V["verify"] --> P["package"]
    V --> After["after-package (extension-point)"]
    P --> Stage["stage"]
    P --> Before["before-package (extension-point)"]
    Stage --> Compile["compile"]
    Compile --> MacroJ["compile-java (macrodef)"]
    Stage --> MacroR["stage-resources (macrodef)"]
    Before --> Meta["write-app-metadata"]
    After --> Check["check-jar"]
    Meta --> Jar["package: jar"]
    Check --> Result["Check artifact exists"]
~~~

Đồ thị này biểu diễn các quan hệ quan trọng; trong Ant, **target** là đơn vị được lập lịch theo **depends** còn macrodef là chuỗi task chạy bên trong target gọi nó. Thứ tự dự kiến khi gọi **verify** là:

1. **compile** tạo các file class.
2. **stage** copy config.properties vào classes directory.
3. **before-package** kích hoạt **write-app-metadata** tạo META-INF/build-info.txt.
4. **package** đóng các nội dung đó thành out/dist/demo.jar.
5. **after-package** kích hoạt **check-jar** kiểm tra artifact tồn tại.
6. **verify** hoàn tất vì mọi target phụ thuộc đã đạt.

Khi một target phụ thuộc được nhiều target tham chiếu trong cùng lần Ant execution, Ant thường chỉ chạy target đó một lần. Điều này giúp chia sẻ các bước chuẩn bị mà không phải gọi lại chúng thủ công.

## 6. extension-point: tạo hook mà không sửa target chung

### 6.1. Điểm khác biệt giữa extension-point và target thông thường

Một **extension-point** là điểm nối trong đồ thị phụ thuộc. Nó được khai báo bằng:

~~~xml
<extension-point name="before-package"/>
~~~

Extension point **không chứa task XML thực thi trực tiếp** như mkdir hay copy. Thay vào đó, các target khác đăng ký tham gia:

~~~xml
<target name="generate-build-info" extensionOf="before-package">
    <echo message="Write build information before package"/>
</target>
~~~

Khi một target khác phụ thuộc **before-package**, Ant chạy những target đã mở rộng điểm đó. Nhờ vậy, **common.xml** có thể định nghĩa thời điểm tùy biến được phép xảy ra mà không cần biết mỗi dự án sẽ làm gì tại thời điểm ấy.

### 6.2. Nhiều target cùng nối vào một hook

Giả sử cần thêm kiểm tra resource trước khi đóng JAR:

~~~xml
<target name="check-config" extensionOf="before-package">
    <available file="${classes.dir}/config.properties"
               type="file"
               property="config.present"/>
    <fail unless="config.present"
          message="config.properties is missing"/>
</target>
~~~

Lúc này **before-package** có ít nhất hai target mở rộng: **write-app-metadata** và **check-config**. Điều quan trọng là **không nên dựa vào thứ tự ngẫu nhiên của các target đóng góp cùng một extension point** để triển khai chuỗi thao tác có phụ thuộc ngữ nghĩa.

Nếu **check-config** cần chạy sau **write-app-metadata**, hãy khai báo quan hệ rõ ràng:

~~~xml
<target name="check-config"
        depends="write-app-metadata"
        extensionOf="before-package">
    <!-- Kiểm tra ở đây -->
</target>
~~~

Nếu hai target độc lập, có thể cùng mở rộng mà không cần phụ thuộc nhau. Nếu không thể biểu đạt phụ thuộc một cách rõ và ổn định, hãy tạo một target điều phối thay vì dùng thứ tự xuất hiện trong file import làm quy tắc ngầm.

### 6.3. Hook trước và sau khác nhau ở đâu?

Trong ví dụ:

~~~xml
<target name="package" depends="stage,before-package">
    <jar .../>
</target>

<target name="verify" depends="package,after-package"/>
~~~

**before-package** chạy trước phần thân của target **package**; nó phù hợp để tạo hoặc kiểm tra file cần được đóng vào JAR.

**after-package** chạy khi **package** đã là một dependency được hoàn thành; nó phù hợp để kiểm tra artifact đã tạo, sinh checksum, đọc manifest hoặc chạy kiểm tra chỉ cần JAR.

Điểm quan trọng: Ant không tự biết “before” hay “after” qua tên. Chính **quan hệ depends** đặt các hook vào đúng thời điểm. Nếu đổi **verify depends="after-package,package"**, một extension sau đóng gói có thể chạy quá sớm, trước khi JAR tồn tại.

## 7. Import không giống gọi Ant project con

### 7.1. Cơ chế import

Phần tử:

~~~xml
<import file="build/common.xml"/>
~~~

đưa các định nghĩa của **common.xml** vào **project Ant hiện tại**. Các target từ file chung có thể được gọi như target của project chính, và thường dùng cùng project properties. Đây là lý do bản thực hành có thể gọi **ant verify** dù target **verify** được định nghĩa trong **common.xml**.

Import không phải chạy một tiến trình Ant riêng, cũng không tự tạo một module build độc lập có output/classpath tách biệt. Nếu mục tiêu là điều phối nhiều dự án độc lập, Ant còn có các task như **ant** và **subant**, nhưng đó là một quyết định kiến trúc khác với import.

### 7.2. Nếu target trùng tên

Giả sử **common.xml** đã định nghĩa:

~~~xml
<target name="package" depends="stage,before-package">
    <!-- Đóng gói mặc định -->
</target>
~~~

Project chính cũng có thể định nghĩa một target **package**. Với cơ chế **import**, target trong project nhập có thể **override** target cùng tên của file được import. Ant cung cấp cách gọi target gốc bằng tên có tiền tố project import, ví dụ **common.package**, tùy tên project/prefix được khai báo.

Cơ chế đó hữu ích khi cần thay thế hành vi có chủ đích, nhưng **không nên override chỉ để thêm một bước nhỏ**. Nếu build chung đã có **before-package** và **after-package**, đăng ký target với **extensionOf** thường rõ ràng hơn, vì không cần nhân bản toàn bộ thân của target **package**.

Đồng thời, nếu bạn đổi tên **project name="common"** trong file dùng chung hoặc cấu hình **as** khi import, những tên có prefix mà caller dựa vào có thể thay đổi. Đây cũng là một phần hợp đồng của hệ thống build nếu đã được các script sử dụng.

### 7.3. Đường dẫn tương đối khi import

Một điểm dễ mắc lỗi là **đường dẫn tương đối bên trong file import**. Không nên giả định rằng mọi **location="lib/tool.jar"** trong **build/common.xml** đều được giải tương đối với thư mục **build/**. Với import, nhiều thao tác file/property vẫn làm việc trong ngữ cảnh và **basedir của project chính**.

Nếu thư viện dùng chung cần đọc một file nằm cạnh chính nó, có thể dùng thuộc tính Ant cung cấp cho file được import. Với **project name="common"**, Ant đặt property **ant.file.common** trỏ tới file đã import. Từ đó tính thư mục của file:

~~~xml
<dirname property="common.home" file="${ant.file.common}"/>

<path id="common.tools.path">
    <pathelement location="${common.home}/lib/helper.jar"/>
</path>
~~~

Đoạn này phù hợp khi đường dẫn tương đối với **vị trí common.xml** là điều mong muốn. Còn source code và output của mỗi ứng dụng nên đi theo property do project chính truyền vào, tránh việc file chung giả định một thư mục **src/** cố định cho tất cả dự án.

### 7.4. Vì sao không dùng antcall thay cho extension-point?

**antcall** gọi một target trong ngữ cảnh thực thi Ant con và có quy tắc truyền/nhận property khác với quan hệ target **depends** trong cùng execution. Nó không đơn giản là một từ đồng nghĩa với **extensionOf**.

Nếu thay đồ thị:

~~~text
verify -> package -> before-package -> app hooks
~~~

bằng nhiều **antcall** rải rác để gọi từng hook, người bảo trì phải xử lý thêm property scope, trình tự thực thi và khả năng target bị chạy lại. Sử dụng **extension-point** khi cần cho nhiều buildfile đóng góp target vào một phase chung thường giữ đồ thị dễ đọc hơn.

## 8. Mở rộng ví dụ cho ứng dụng thứ hai

Giả sử repository có hai ứng dụng **catalog** và **billing**. Cả hai đều cần compile, copy resource, package, verify; nhưng package riêng có tên JAR và metadata khác nhau:

~~~text
repo/
├── ant-common/
│   ├── common.xml
│   └── checks.xml
├── catalog/
│   ├── build.xml
│   └── src/main/...
└── billing/
    ├── build.xml
    └── src/main/...
~~~

Ở **catalog/build.xml**:

~~~xml
<project name="catalog" default="verify" basedir=".">
    <property name="source.dir" location="src/main/java"/>
    <property name="resources.dir" location="src/main/resources"/>
    <property name="output.dir" location="out"/>
    <property name="classes.dir" location="out/classes"/>
    <property name="dist.dir" location="out/dist"/>
    <property name="jar.name" value="catalog.jar"/>
    <property name="java.release" value="17"/>

    <import file="../ant-common/common.xml"/>
    <import file="../ant-common/checks.xml"/>

    <target name="catalog-metadata" extensionOf="before-package">
        <mkdir dir="${classes.dir}/META-INF"/>
        <echo file="${classes.dir}/META-INF/build-info.txt"
              message="module=catalog" encoding="UTF-8"/>
    </target>
</project>
~~~

Ở **billing/build.xml**:

~~~xml
<project name="billing" default="verify" basedir=".">
    <property name="source.dir" location="src/main/java"/>
    <property name="resources.dir" location="src/main/resources"/>
    <property name="output.dir" location="out"/>
    <property name="classes.dir" location="out/classes"/>
    <property name="dist.dir" location="out/dist"/>
    <property name="jar.name" value="billing.jar"/>
    <property name="java.release" value="17"/>

    <import file="../ant-common/common.xml"/>
    <import file="../ant-common/checks.xml"/>

    <target name="billing-metadata" extensionOf="before-package">
        <mkdir dir="${classes.dir}/META-INF"/>
        <echo file="${classes.dir}/META-INF/build-info.txt"
              message="module=billing" encoding="UTF-8"/>
    </target>
</project>
~~~

Khi chạy từ từng thư mục:

~~~bash
ant -f build.xml clean verify
~~~

thì **catalog** sinh **catalog/out/dist/catalog.jar**, còn **billing** sinh **billing/out/dist/billing.jar**. Mỗi project có output và classloader/configuration riêng theo lệnh Ant được gọi; cả hai dùng định nghĩa chung trong **ant-common**.

Ví dụ này còn lặp một số property — việc lặp *cấu hình riêng của ứng dụng* có thể chấp nhận được. Chỉ nên trừu tượng hóa thêm khi đã xác định được một quy ước ổn định thay vì tạo một hệ thống cấu hình phức tạp mới.

## 9. Các vấn đề dễ gặp khi tách build chung

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| **Cannot find imported file** | Đường dẫn trong import giải từ nơi không mong đợi | Kiểm tra vị trí build.xml, basedir và đường dẫn import |
| **Unknown element compile-java** | Macro chưa được định nghĩa/import trước khi được dùng | Kiểm tra file import, tên macro và phạm vi khai báo |
| **Property not found / file path sai** | Property ứng dụng chưa được đặt hoặc bị đặt quá sớm | Kiểm tra nguồn, ưu tiên và thứ tự khởi tạo property |
| **JAR thiếu resource** | Hook tạo file chạy sau package, copy resources sai thời điểm | Đối chiếu depends và entry trong JAR |
| **Extension target không chạy** | target không dùng extensionOf đúng tên hoặc extension-point không nằm trong dependencies | Kiểm tra khai báo hook, URI/tên và đường đi tới verify |
| **Hook chạy trước file cần kiểm tra** | Thứ tự depends bị đảo, các extension phụ thuộc ngầm vào nhau | Thêm depends tường minh và đặt hook đúng phase |
| **Một target bị override bất ngờ** | File import và project chính cùng định nghĩa target name | Kiểm tra target collision, tên có prefix, dùng hook khi chỉ cần bổ sung |
| **Build sạch xóa cả XML chung** | output directory trùng thư mục source build definitions | Tách out/ khỏi build/ chứa file import |
| **Hai module sinh cùng một JAR** | Output path hoặc jar.name bị hard-code trong file chung | Di chuyển cấu hình đường dẫn/naming sang project từng module |
| **Thay macro làm hỏng nhiều dự án** | Macro là hợp đồng chia sẻ, thiếu kiểm thử consumer | Kiểm tra đầu ra của từng project dùng macro trước khi đổi |

### Tình huống A: extension-point trống

Không phải ứng dụng nào cũng cần **write-app-metadata**. Nếu project chỉ import **common.xml** nhưng không đóng góp target cho **before-package**, hook đó có thể không làm gì. Đây là hành vi có chủ đích: định nghĩa chung có một chỗ mở rộng nhưng không bắt buộc module nào cũng phải có tính năng bổ sung.

Nếu việc tạo metadata là bắt buộc cho mọi ứng dụng, hãy đưa nó vào target chung hoặc thiết lập một target kiểm tra bắt buộc. Đừng dùng một hook hoàn toàn tùy chọn để ngầm đảm bảo một đầu ra thiết yếu.

### Tình huống B: file chung tham chiếu tên property không đồng nhất

Một ứng dụng dùng **src.main**, ứng dụng khác dùng **source.dir**, nhưng common.xml chỉ biết **source.dir**. Nếu quên khai báo property đó, Ant có thể xử lý giá trị chưa giải được hoặc thất bại ở đường dẫn. Nên **quy ước bộ property bắt buộc** cho file chung và kiểm tra sớm trong một target chuẩn bị, ví dụ:

~~~xml
<target name="validate-config">
    <fail unless="source.dir" message="Missing source.dir"/>
    <fail unless="classes.dir" message="Missing classes.dir"/>
    <fail unless="dist.dir" message="Missing dist.dir"/>
    <fail unless="jar.name" message="Missing jar.name"/>
</target>

<target name="compile" depends="validate-config">
    <!-- Gọi compile-java -->
</target>
~~~

Trong bài thực hành hoàn chỉnh ở trên, **compile** chưa phụ thuộc vào target kiểm tra này để phần ví dụ tập trung vào ba cơ chế chính. Với nhiều consumer và CI, việc thêm **validate-config** là một bước tăng khả năng chẩn đoán rõ ràng.

### Tình huống C: nhiều hook cần thứ tự xác định

Nếu phải sinh **version.properties** trước khi **sign-artifact** đọc file đó, nên khai báo **depends** giữa các target thay vì trông đợi thứ tự import. Với thao tác ký JAR, cần đặt extension sau khi đóng gói chứ không trộn vào hook trước package; đồng thời cần xem xét lại đường dẫn/identity của artifact nếu ký làm thay đổi byte.

### Tình huống D: target được override không còn gọi triển khai gốc

Khi project chính định nghĩa lại **package**, target có thể che định nghĩa mặc định trong common.xml. Nếu chỉ định làm thêm một bước kiểm tra mà vô tình override **package** bằng target không đóng JAR, các script vẫn gọi đúng tên **ant package** nhưng mất output.

Phương án phù hợp nhất cho việc *bổ sung* là sử dụng extension point. Chỉ override có chủ đích khi thực sự muốn *thay thế* hành vi, và xác định cách gọi target gốc qua prefix khi cần.

## 10. Quan sát và kiểm tra kết quả bài thực hành

Với các file đã tạo, chạy tại root **ant-modular-demo**:

~~~bash
ant -version
java -version
ant -f build.xml -projecthelp
ant -f build.xml clean verify
~~~

Khi cần xem các target được chạy và file đã xử lý:

~~~bash
ant -f build.xml -verbose clean verify
~~~

Sau một lần build thành công, có thể xem nội dung JAR:

~~~bash
jar tf out/dist/demo.jar
~~~

Những entry cần xuất hiện:

~~~text
example/Main.class
config.properties
META-INF/build-info.txt
~~~

Với manifest do Ant thêm, cũng có thể thấy **META-INF/MANIFEST.MF**. Danh sách này mô tả kết quả được mong đợi từ cấu hình ví dụ; không phải output đã được thực thi trong tài liệu.

Kiểm tra khả năng chạy ứng dụng bằng classpath:

~~~bash
java -cp out/dist/demo.jar example.Main
~~~

Ví dụ không tự thêm **Main-Class** vào manifest nên không mặc định yêu cầu lệnh **java -jar out/dist/demo.jar** hoạt động. Nếu dự án có hợp đồng dùng java -jar, cần bổ sung Main-Class trong bước đóng gói và giữ hợp đồng đó khi tách file.

### So sánh đầu ra trước và sau khi tách

Khi chuyển một dự án đang tồn tại sang cấu trúc này, cần ghi nhận và so sánh **hợp đồng trước refactor**. Những mục quan trọng:

| Hạng mục | Ví dụ quan sát |
|---|---|
| Lệnh công khai | **ant clean verify**, **ant package** |
| Đường dẫn artifact | **out/dist/demo.jar** |
| Nội dung archive | Class, resources, META-INF/build-info.txt |
| Java compatibility | Bytecode phù hợp với runtime công bố |
| Target order | compile → stage → hook → jar → check |
| Trạng thái khi lỗi | Compile hoặc check thất bại phải khiến build thất bại |
| Property được caller truyền | **-Djar.name=...**, đường dẫn nguồn/đích nếu được hỗ trợ |

Với build có timestamp động hoặc khác biệt về phiên bản JDK/Ant, checksum JAR có thể thay đổi dù logic không thay đổi. Nếu cam kết yêu cầu **byte-for-byte reproducibility**, cần chốt toolchain, dependency và metadata archive một cách riêng biệt. Không kết luận tách build thành công chỉ từ thông báo **BUILD SUCCESSFUL**; hãy kiểm tra output mà consumer sử dụng.

## 11. Cách tổ chức code Ant để bảo trì lâu dài

Một cấu trúc tốt thường có ba lớp:

**Lớp thao tác — macrodef.** Chứa các thao tác nhỏ có trách nhiệm rõ ràng, nhận attribute thay vì đọc những property mang tính riêng tư của một ứng dụng. Ví dụ: compile-java, stage-resources, tạo checksum, kiểm tra đường dẫn.

**Lớp luồng thực thi — target và extension-point.** Tổ chức quan hệ depends, quy định phase: chuẩn bị, biên dịch, xử lý resource, trước package, package, sau package. Hook chỉ nên xuất hiện ở những chỗ thực sự có nhu cầu mở rộng.

**Lớp cấu hình project — build.xml chính.** Chọn source path, artifact name, compiler release, import common.xml và khai báo các target mở rộng. Đây là nơi mỗi dự án ghi rõ khác biệt của mình.

Một số quy tắc thực hành:

1. Giữ **target public** ổn định nếu CI và developer đã dùng chúng.
2. Đưa logic chung vào file import, nhưng giữ **input/output của mỗi module** do module sở hữu.
3. Dùng **macrodef** khi nhiều chuỗi task chỉ khác tham số; dùng **extension-point** khi muốn thêm một target vào phase có sẵn.
4. Tránh dùng **target override** cho các mở rộng nhỏ; nếu override cần thiết, mô tả rõ hành vi thay thế và cách giữ tương thích.
5. Quản lý đường dẫn tương đối theo chủ ý: **basedir của caller** cho mã nguồn/output, đường dẫn gắn với **ant.file.<project>** cho tài nguyên nằm cạnh file chung.
6. Khi nhiều extension target có thứ tự phụ thuộc, khai báo **depends** tường minh.
7. Không để **clean** xóa file nguồn hoặc file XML dùng để định nghĩa build.
8. Sau thay đổi macro/import/hook, kiểm tra các project cùng sử dụng file chung và output mà chúng đã cam kết.

## 12. Bài tập tự thực hành

**Bài tập 1 — Thay tên artifact.** Trong build.xml chính, đổi **jar.name** từ **demo.jar** sang **demo-tools.jar**. Dự đoán output mới, sau đó chạy **ant clean verify** và kiểm tra file **out/dist/demo-tools.jar**. Phần code trong common.xml không cần sửa vì tên JAR là input của project.

**Bài tập 2 — Thêm hook kiểm tra resource.** Khai báo target **check-config** với **extensionOf="before-package"**; dùng **available** và **fail** để bảo đảm **config.properties** đã có trong classes directory. Xóa tạm resource khỏi workspace thử nghiệm rồi quan sát thông báo lỗi. Khôi phục file sau bài tập.

**Bài tập 3 — Thêm kiểm tra sau package.** Trong checks.xml, thêm target dùng **jar tf** qua task **exec** để in entry của JAR sau khi đóng gói. Đặt **failonerror="true"** nếu muốn lỗi lệnh ngoài làm build thất bại. Cân nhắc tính khả chuyển của lệnh và JDK trên các runner khác nhau.

**Bài tập 4 — Tạo module thứ hai.** Tạo project billing theo mẫu ở phần 8, đặt tên **billing.jar**, module metadata riêng và import cùng file chung. Quan sát rằng cả hai project vẫn tạo artifact đúng thư mục riêng mà không cần sao chép macrodef.

**Bài tập 5 — Phân tích một thay đổi không tương thích.** Thử tưởng tượng một người đổi **package depends="stage,before-package"** thành **package depends="before-package,stage"**. Hãy nêu điều gì có thể xảy ra nếu hook cần đọc resource do target stage tạo. Sau đó trả quan hệ depends về thứ tự đúng.

## 13. Kết luận

Trong Apache Ant, **macrodef**, **import** và **extension-point** là ba công cụ khác nhau để tổ chức build có thể tái sử dụng:

- **macrodef** đóng gói *cách thực hiện một thao tác* và nhận tham số qua **@{attribute}**.
- **import** đưa *các định nghĩa chung* vào project chính, nhưng cần quản lý namespace, target trùng tên và đường dẫn tương đối.
- **extension-point** cho phép *gắn target riêng vào một phase* mà không phải sửa hoặc override target chung.

Khi kết hợp đúng, file chung sở hữu các bước compile/copy/package; ứng dụng sở hữu cấu hình và extension; CI tiếp tục gọi target công khai và nhận đúng artifact. Chính việc giữ **hợp đồng đầu ra** cùng đồ thị dependencies rõ ràng làm cho cấu trúc modular có giá trị lâu dài, không chỉ số dòng XML được giảm đi.

### Tài liệu tham khảo

- [Apache Ant Manual — MacroDef](https://ant.apache.org/manual/Tasks/macrodef.html): attribute, sequential và nested element.
- [Apache Ant Manual — Import](https://ant.apache.org/manual/Tasks/import.html): cơ chế đưa target từ file khác vào project, override và tên target có prefix.
- [Apache Ant Manual — Extension-Point](https://ant.apache.org/manual/extension.html): khai báo extension-point, extensionOf và quan hệ với depends.
- [Apache Ant Manual — Using Ant](https://ant.apache.org/manual/using.html): project, target, property, path và import.
- [Apache Ant Manual — Property](https://ant.apache.org/manual/Tasks/property.html): khai báo và mức ưu tiên property.
- [Apache Ant Manual — Javac](https://ant.apache.org/manual/Tasks/javac.html), [Copy](https://ant.apache.org/manual/Tasks/copy.html) và [Jar](https://ant.apache.org/manual/Tasks/jar.html): task nền tảng trong ví dụ.
