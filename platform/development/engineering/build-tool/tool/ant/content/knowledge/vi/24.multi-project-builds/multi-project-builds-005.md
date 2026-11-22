# Truyền property, param và reference giữa các lần gọi

Khi một dự án Ant được chia thành nhiều build file hoặc nhiều module, một build có thể gọi build khác để biên dịch, kiểm thử hoặc đóng gói từng phần. Các lần gọi này cần chia sẻ thông tin như phiên bản phát hành, thư mục output, cấu hình môi trường và các đối tượng dữ liệu như classpath hoặc fileset.

Ant có ba cơ chế thường gặp cho việc này:

- **Property** truyền các giá trị cấu hình như chuỗi, phiên bản và đường dẫn.
- **Param** là phần tử lồng trong task `<antcall>`, dùng để truyền property cho target được gọi.
- **Reference** truyền một đối tượng data type đã được đăng ký bằng `id`, chẳng hạn `path`, sang project hoặc target được gọi khi cơ chế đó hỗ trợ.

Cần phân biệt gọi target trong cùng build, gọi một build file con và gọi nhiều build file theo lô. Mỗi trường hợp có phạm vi property và reference khác nhau. Hiểu đúng phạm vi giúp tránh lỗi thiếu property, dùng nhầm classpath và cấu hình child build không thể ghi đè như mong đợi.

## 1. Phân biệt property, param và reference

### 1.1. Property là giá trị cấu hình

Property của Ant lưu một giá trị như chuỗi, số, phiên bản hoặc đường dẫn. Ví dụ:

~~~xml
<property name="release.version" value="2.5.0" />
<property name="dist.dir" location="${basedir}/dist" />
~~~

Trong task, property được dùng bằng cú pháp `${tên-property}`:

~~~xml
<echo message="Release: ${release.version}" />
<mkdir dir="${dist.dir}" />
~~~

Property phù hợp với dữ liệu đơn giản. Nó không phải một đối tượng classpath hoặc fileset, và không thể thay thế reference ID.

### 1.2. Param truyền property qua antcall

Khi dùng task `<antcall>` để gọi một target khác trong cùng build file, có thể truyền giá trị bằng phần tử `<param>`:

~~~xml
<target name="release">
    <antcall target="package">
        <param name="package.variant" value="full" />
    </antcall>
</target>
~~~

Target `package` có thể đọc `${package.variant}`. Param là cách đặt giá trị đầu vào cho lần gọi target đó. Nó không phải một biến có thể thay đổi qua lại sau khi target bắt đầu chạy.

### 1.3. Reference truyền một đối tượng dữ liệu

Một số data type của Ant có thể được đăng ký bằng `id` rồi tham chiếu bằng `refid`. Ví dụ:

~~~xml
<path id="shared.compile.path">
    <pathelement location="lib/api.jar" />
    <pathelement location="lib/runtime.jar" />
</path>
~~~

Đối tượng `shared.compile.path` có thể được dùng trong task hỗ trợ phần tử `classpath`:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <classpath refid="shared.compile.path" />
</javac>
~~~

Khi gọi một project khác, Ant có thể chuyển reference một cách tường minh qua phần tử `<reference>`. Không phải mọi object hay mọi task đều hỗ trợ truyền reference; data type phải có khả năng được sao chép hoặc dùng trong project đích.

### 1.4. Bảng so sánh

| Cơ chế | Truyền gì? | Cú pháp thường gặp | Ví dụ |
|---|---|---|---|
| Property | Giá trị cấu hình | `<property name="..." value="..."/>` | `release.version=2.5.0` |
| Param | Property cho target được gọi bằng antcall | `<param name="..." value="..."/>` | `package.variant=full` |
| Reference | Đối tượng data type có ID | `<reference refid="..." torefid="..."/>` | Path classpath dùng chung |

Property và param truyền giá trị. Reference truyền một đối tượng dữ liệu. Không viết `${shared.compile.path}` để lấy một path object; hãy dùng `refid` ở vị trí được hỗ trợ.

## 2. Phạm vi project và nguyên tắc kế thừa

Khi Ant gọi một build file khác bằng task `<ant>`, build file con chạy trong một Ant project riêng. Project con có bảng property và bảng reference riêng. Các giá trị hoặc reference từ project cha chỉ có mặt trong project con theo quy tắc kế thừa và truyền dữ liệu của task gọi.

Sơ đồ khái quát:

~~~text
Parent Ant project
    |
    +-- properties
    |     +-- release.version
    |     +-- dist.dir
    |
    +-- references
    |     +-- shared.compile.path
    |
    +-- <ant> child-build.xml
            |
            +-- Child Ant project
                  +-- inherited / explicitly passed properties
                  +-- explicitly passed references
                  +-- child-local targets and data types
~~~

Một target được gọi bằng `depends` vẫn chạy trong cùng project và dùng cùng property/reference. Một target được gọi bằng `<antcall>` chạy trong một project thực thi mới, với các property/reference được truyền theo quy tắc của antcall.

Ant property thông thường là bất biến: sau khi một property đã được thiết lập, các lần khai báo thông thường tiếp theo không ghi đè giá trị đó. Vì vậy, phải thiết kế tên property và quy tắc kế thừa rõ ràng, nhất là khi child build cần giá trị riêng.

## 3. Gọi build file con bằng task ant

### 3.1. Cấu trúc dự án nhiều module

Giả sử một dự án có build file chính và hai module:

~~~text
enterprise-app/
├── build.xml
├── lib/
│   └── shared-api.jar
├── dist/
└── modules/
    ├── catalog/
    │   ├── build.xml
    │   └── src/
    └── billing/
        ├── build.xml
        └── src/
~~~

Build file gốc điều phối các module. Mỗi module có thể có target compile và package riêng. Task `<ant>` gọi build file con:

~~~xml
<target name="build-catalog">
    <ant antfile="${basedir}/modules/catalog/build.xml"
         dir="${basedir}/modules/catalog"
         target="package" />
</target>
~~~

Các thuộc tính quan trọng:

- `antfile`: build file cần gọi.
- `dir`: thư mục làm việc/base directory của build file con.
- `target`: target cần thực thi trong build file con.
- `inheritAll`: điều khiển việc kế thừa property.
- `inheritRefs`: điều khiển việc kế thừa reference.

Nếu bỏ `target`, Ant sử dụng default target của build file con. Nên chỉ rõ target khi build cha cần một hành động cụ thể.

### 3.2. Child build dùng property được truyền từ cha

Build file cha:

~~~xml
<project name="enterprise-app" default="package-all" basedir=".">

    <property name="release.version" value="2.5.0" />
    <property name="dist.dir" location="${basedir}/dist" />

    <target name="build-catalog">
        <ant antfile="${basedir}/modules/catalog/build.xml"
             dir="${basedir}/modules/catalog"
             target="package"
             inheritAll="true">
            <property name="module.name" value="catalog" />
            <property name="module.output.dir"
                      location="${dist.dir}/catalog" />
        </ant>
    </target>

    <target name="package-all" depends="build-catalog" />
</project>
~~~

Build file con `modules/catalog/build.xml`:

~~~xml
<project name="catalog" default="package">

    <target name="package">
        <echo message="Version: ${release.version}" />
        <echo message="Module: ${module.name}" />
        <echo message="Output: ${module.output.dir}" />
        <mkdir dir="${module.output.dir}" />
        <!-- Compile và đóng gói module catalog -->
    </target>

</project>
~~~

Với `inheritAll="true"`, các property của project cha được truyền sang project con theo quy tắc của Ant. Các property khai báo lồng trong task `<ant>` cũng được cung cấp cho lần gọi con. Nhờ vậy, child build có thể dùng version chung và nhận thêm tên module hoặc thư mục output riêng.

Hãy dùng `basedir` hoặc đường dẫn tuyệt đối khi cần đường dẫn ổn định. Thuộc tính `dir` quyết định thư mục làm việc của child build; các đường dẫn tương đối trong child build thường được hiểu theo base directory của project con.

### 3.3. Truyền property tường minh

Có thể truyền một giá trị cụ thể qua phần tử property lồng trong `<ant>`:

~~~xml
<ant antfile="${basedir}/modules/billing/build.xml"
     dir="${basedir}/modules/billing"
     target="package"
     inheritAll="false">
    <property name="release.version" value="${release.version}" />
    <property name="module.name" value="billing" />
    <property name="module.output.dir"
              location="${dist.dir}/billing" />
</ant>
~~~

Cách này hữu ích khi muốn child build chỉ nhận các giá trị mà nó thực sự cần. Tuy nhiên, với `inheritAll="false"`, các user properties như tham số truyền bằng `-D` vẫn được kế thừa theo quy tắc của Ant; property thông thường do build file cha định nghĩa cần được truyền tường minh nếu child cần dùng.

Đặt `inheritAll` thành false không có nghĩa là không thể truyền property. Các phần tử property lồng trong task vẫn có thể cung cấp dữ liệu cho child build.

## 4. Điều khiển inheritAll

### 4.1. inheritAll=true

Mặc định, task `<ant>` dùng `inheritAll="true"`. Các property của project cha được kế thừa vào project con, cùng với user properties. Đây là cách thuận tiện khi nhiều module cần dùng chung các giá trị như version, thư mục gốc hoặc profile.

Ưu điểm:

- Ít phải khai báo lại property.
- Child build có thể dùng cấu hình chung.
- Thích hợp với hệ thống module được thiết kế cùng một bộ property.

Rủi ro:

- Child build có thể phụ thuộc ngầm vào nhiều property của cha.
- Property cùng tên trong child có thể không có tác dụng vì giá trị đã được truyền sang và Ant property là bất biến.
- Module khó chạy độc lập nếu thiếu cấu hình mà trước đây nó nhận ngầm từ parent.

### 4.2. inheritAll=false

Khi đặt `inheritAll="false"`, các property thông thường của project cha không được tự động kế thừa; các user properties vẫn được truyền. Những giá trị khác cần thiết nên được truyền rõ bằng phần tử property hoặc propertyset.

Ví dụ:

~~~xml
<ant antfile="modules/report/build.xml"
     dir="modules/report"
     target="package"
     inheritAll="false">
    <property name="release.version" value="${release.version}" />
    <property name="report.format" value="pdf" />
</ant>
~~~

Cách này tạo hợp đồng đầu vào rõ ràng cho module report. Nếu sau này parent có thêm property riêng, child không tự động phụ thuộc vào nó.

### 4.3. Chọn chính sách phù hợp

| Trường hợp | Cách chọn |
|---|---|
| Các module luôn dùng chung cấu hình gốc và được quản lý như một hệ thống | Có thể dùng inheritAll=true |
| Module cần chạy độc lập và chỉ nhận vài đầu vào xác định | Dùng inheritAll=false và truyền property tường minh |
| CI truyền version bằng -D | User property vẫn được kế thừa; có thể truyền lại rõ nếu muốn thể hiện hợp đồng |
| Parent có nhiều property nội bộ không liên quan child | Dùng inheritAll=false để giảm phụ thuộc ngầm |

Đối với dự án lớn, truyền tường minh thường làm ranh giới module dễ hiểu hơn. Nếu dùng inheritAll=true, nên tài liệu hóa các property mà child build thực sự phụ thuộc.

## 5. Dùng propertyset để truyền một nhóm property

Khi cần truyền nhiều property theo một quy tắc, task `<ant>` hỗ trợ nested `<propertyset>`. Propertyset chọn một nhóm property theo tên, prefix hoặc quy tắc lọc.

Ví dụ:

~~~xml
<property name="release.version" value="2.5.0" />
<property name="release.channel" value="stable" />
<property name="build.number" value="1842" />
<property name="internal.debug" value="true" />

<target name="build-module">
    <ant antfile="modules/catalog/build.xml"
         dir="modules/catalog"
         target="package"
         inheritAll="false">
        <propertyset>
            <propertyref prefix="release." />
            <propertyref name="build.number" />
        </propertyset>
    </ant>
</target>
~~~

Trong ví dụ, child nhận các property có prefix `release.` và property `build.number`. Property `internal.debug` không được chọn bởi propertyset này.

Propertyset hữu ích khi có một nhóm property dùng chung theo convention. Hãy tránh chọn quá rộng như toàn bộ property nếu mục tiêu là giới hạn hợp đồng giữa parent và child.

Tên và khả năng lọc property phụ thuộc cú pháp Ant của nested propertyset. Khi dùng các selector nâng cao, hãy kiểm tra tài liệu phiên bản Ant mà dự án cố định.

## 6. Truyền reference giữa các project

### 6.1. Vì sao cần reference?

Một path classpath có thể chứa nhiều JAR và thư mục. Nếu mỗi child build phải khai báo lại từng mục, cấu hình dễ bị lệch giữa các module.

Build file cha có thể định nghĩa reference:

~~~xml
<path id="shared.compile.path">
    <pathelement location="${basedir}/lib/shared-api.jar" />
    <pathelement location="${basedir}/lib/common-utils.jar" />
</path>
~~~

Sau đó truyền reference vào build file con:

~~~xml
<ant antfile="${basedir}/modules/catalog/build.xml"
     dir="${basedir}/modules/catalog"
     target="compile"
     inheritAll="false">
    <reference refid="shared.compile.path"
               torefid="module.compile.path" />
</ant>
~~~

Ở đây:

- `refid` là ID của đối tượng trong project cha.
- `torefid` là tên ID mà project con sẽ dùng.
- Child build có thể tham chiếu đối tượng bằng `refid="module.compile.path"`.

Build file con:

~~~xml
<target name="compile">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="module.compile.path" />
    </javac>
</target>
~~~

Đây là cách truyền path có chủ đích mà không cần child tự dựng lại danh sách JAR.

### 6.2. Điều kiện và giới hạn của reference

Reference khác property. Một reference ID chỉ có ý nghĩa trong bảng reference của project mà nó được đăng ký. Nó không tự xuất hiện trong child project nếu không được kế thừa hoặc truyền.

Không phải mọi object đều có thể truyền an toàn giữa project. Data type phải hỗ trợ cơ chế reference/copy phù hợp. Các đối tượng có trạng thái gắn chặt với project cha hoặc chứa tài nguyên không thể chia sẻ có thể không phù hợp.

Khi truyền reference:

- Kiểm tra ID nguồn đã được khai báo trước khi task gọi chạy.
- Dùng `torefid` để đặt tên rõ ràng trong project đích.
- Đảm bảo task trong child nhận đúng loại data type.
- Tránh dùng một reference như nơi lưu trạng thái có thể bị thay đổi giữa các module.
- Nếu child cần cấu hình khác, tạo path/fileset riêng thay vì giả định reference dùng chung có thể được sửa độc lập.

### 6.3. inheritRefs

Mặc định, task `<ant>` không kế thừa toàn bộ reference của project cha. Thuộc tính `inheritRefs="true"` yêu cầu Ant truyền các reference theo cơ chế kế thừa của task:

~~~xml
<ant antfile="modules/catalog/build.xml"
     dir="modules/catalog"
     target="compile"
     inheritRefs="true" />
~~~

Khi dùng cách này, child có thể nhận các reference đủ điều kiện từ parent theo ID tương ứng. Tuy nhiên, truyền toàn bộ reference có thể tạo phụ thuộc ngầm và khiến child khó chạy độc lập.

Đối với một module chỉ cần một hoặc hai path cụ thể, nested `<reference>` thường thể hiện hợp đồng rõ hơn:

~~~xml
<ant antfile="modules/catalog/build.xml"
     dir="modules/catalog"
     target="compile"
     inheritRefs="false">
    <reference refid="shared.compile.path"
               torefid="module.compile.path" />
</ant>
~~~

Không nhầm `inheritRefs` với `inheritAll`: một thuộc tính điều khiển reference, thuộc tính còn lại điều khiển property. Bật kế thừa property không đồng nghĩa reference cũng được truyền.

## 7. Truyền param và reference với antcall

### 7.1. antcall gọi target trong cùng build file

Task `<antcall>` gọi một target khác trong cùng build file, nhưng tạo ngữ cảnh project thực thi mới cho lần gọi đó. Nó không giống việc khai báo `depends`.

Ví dụ:

~~~xml
<target name="package">
    <echo message="Package variant: ${package.variant}" />
</target>

<target name="release">
    <antcall target="package">
        <param name="package.variant" value="full" />
    </antcall>
</target>
~~~

Khi chạy `ant release`, target package được gọi với property `package.variant` có giá trị full trong lần gọi đó.

### 7.2. Truyền nhiều param

Có thể truyền nhiều tham số:

~~~xml
<target name="release">
    <antcall target="package">
        <param name="release.version" value="${release.version}" />
        <param name="package.variant" value="full" />
        <param name="include.docs" value="true" />
    </antcall>
</target>
~~~

Target package dùng các property này để điều khiển cách đóng gói:

~~~xml
<target name="package">
    <echo message="Version: ${release.version}" />
    <echo message="Variant: ${package.variant}" />
    <echo message="Include docs: ${include.docs}" />
</target>
~~~

Các param được truyền cho lần gọi target và được xử lý như property của project con. Vì property bất biến, không nên coi param là biến tạm có thể gán lại nhiều lần trong cùng một ngữ cảnh.

### 7.3. Truyền reference qua antcall

Nếu target được gọi cần một data type đã định nghĩa, có thể dùng nested reference:

~~~xml
<path id="package.path">
    <pathelement location="build/classes" />
    <fileset dir="lib" includes="*.jar" />
</path>

<target name="release">
    <antcall target="package">
        <param name="package.variant" value="full" />
        <reference refid="package.path"
                   torefid="child.package.path" />
    </antcall>
</target>

<target name="package">
    <echo message="Creating package variant: ${package.variant}" />
    <!-- Task sử dụng child.package.path -->
</target>
~~~

Trong target package, reference được dùng tại vị trí phù hợp, ví dụ:

~~~xml
<path id="archive.classpath">
    <path refid="child.package.path" />
</path>
~~~

Khi dùng antcall, cần cân nhắc kỹ vì target được gọi trong project context mới. Nếu chỉ muốn chạy nhiều bước tuần tự trong cùng một project và chia sẻ property/reference hiện tại, `depends` thường rõ ràng hơn.

### 7.4. inheritAll và inheritRefs với antcall

`<antcall>` cũng có chính sách kế thừa property và reference. Mặc định, property được kế thừa; reference không được kế thừa tự động theo cùng cách. Có thể kiểm soát bằng `inheritAll` và `inheritRefs`, đồng thời truyền property bằng `<param>` và reference bằng `<reference>`.

Hãy dùng param để biểu diễn các đầu vào riêng của lần gọi và reference để chuyển data type cần thiết. Nếu target chỉ cần dependency cố định, không cần dùng antcall để truyền dữ liệu vòng quanh; dùng target dependency trong cùng project.

## 8. Khi nào dùng depends, antcall hay ant?

| Cơ chế | Dùng khi | Phạm vi thực thi |
|---|---|---|
| `depends` | Target cần target khác chạy trước trong cùng build | Cùng project, cùng property/reference |
| `antcall` | Cần gọi lại một target trong cùng build với một tập property/param riêng | Project context mới cho lần gọi |
| `ant` | Cần gọi build file/module khác | Project con riêng |
| `subant` | Cần gọi cùng một target hoặc build file trên nhiều module/thư mục con | Nhiều child project |

Ví dụ dùng `depends`:

~~~xml
<target name="compile" />
<target name="test" depends="compile" />
<target name="package" depends="test" />
~~~

Không cần truyền property hay reference giữa các target vì chúng chạy trong cùng project.

Ví dụ dùng `ant` để gọi module độc lập:

~~~xml
<ant antfile="modules/catalog/build.xml"
     dir="modules/catalog"
     target="package" />
~~~

Ví dụ dùng `antcall` khi cùng một target cần được gọi với một tham số khác:

~~~xml
<antcall target="package">
    <param name="package.variant" value="minimal" />
</antcall>
~~~

Không lạm dụng antcall để tạo nhiều biến thể của target nếu có thể mô hình hóa chúng bằng target riêng hoặc property đầu vào rõ ràng. Nhiều lần antcall có thể làm đồ thị build khó theo dõi và tạo cảm giác property được chia sẻ như biến mutable trong khi thực tế là các project context riêng.

## 9. Điều phối nhiều module bằng subant

Task `<subant>` hỗ trợ gọi build file trong nhiều thư mục con. Nó hữu ích khi một repository có nhiều module độc lập và cần chạy cùng một target trên từng module.

Ví dụ:

~~~xml
<target name="compile-all-modules">
    <subant target="compile"
            failonerror="true"
            inheritall="false">
        <fileset dir="${basedir}/modules"
                 includes="*/build.xml" />
        <property name="release.version"
                  value="${release.version}" />
    </subant>
</target>
~~~

Fileset chọn các build file trong thư mục con modules. Subant gọi target compile trên từng build file được chọn. Property lồng truyền version cho từng child build.

Tên thuộc tính của subant cần theo cú pháp của task và phiên bản Ant được dự án sử dụng; ví dụ trên dùng các thuộc tính thường gặp của task subant. Hãy xác nhận tài liệu tương ứng nếu build dùng thêm `inheritrefs`, `genericantfile` hoặc buildpath.

### 9.1. Cấu trúc module cần nhất quán

Nếu dùng subant để chạy hàng loạt, các module nên có một hợp đồng target thống nhất, ví dụ:

- `clean`: xóa output do module tạo.
- `compile`: biên dịch mã nguồn.
- `test`: chạy test.
- `package`: tạo artifact module.

Một module thiếu target được gọi có thể khiến subant thất bại. Hãy thống nhất cấu trúc build file và tên target giữa các module hoặc tạo một lớp điều phối phù hợp.

### 9.2. Dừng khi một module thất bại

Với release pipeline, thường đặt `failonerror="true"` để lỗi ở một module làm lần điều phối thất bại. Nếu cho phép tiếp tục để thu thập báo cáo từ tất cả module, hãy xử lý trạng thái lỗi rõ ràng và bảo đảm bước package tổng hợp không chạy khi module bắt buộc thất bại.

Không nên để build tổng hợp báo thành công chỉ vì subant đã thử gọi mọi module. Kết quả của từng child build cần được phản ánh vào mã thoát cuối cùng của job.

## 10. Property precedence và các lỗi do bất biến

Ant property thường chỉ được thiết lập một lần. Điều này ảnh hưởng trực tiếp đến việc truyền property giữa các lần gọi.

Ví dụ parent truyền:

~~~xml
<property name="release.channel" value="stable" />

<ant antfile="modules/catalog/build.xml"
     dir="modules/catalog"
     target="package">
    <property name="release.channel" value="preview" />
</ant>
~~~

Không nên dựa vào ví dụ như trên để giả định child có thể ghi đè một giá trị đã được truyền từ parent. Nếu property cùng tên đã có trong child project do inheritance, giá trị truyền sang có thể đã được thiết lập trước khi build file con khai báo property. Khi một property đã có, khai báo thông thường sau đó không thay đổi nó.

Để tránh xung đột:

- Chọn một nguồn có thẩm quyền cho mỗi property.
- Dùng tên riêng cho property local của module.
- Nếu cần giá trị khác nhau giữa các module, truyền tên property riêng hoặc một property đầu vào có ý nghĩa rõ ràng.
- Dùng `inheritAll="false"` khi child không cần toàn bộ property thông thường của parent.
- Không dùng property như biến đếm hoặc biến trạng thái có thể cập nhật nhiều lần.

Ví dụ tách tên:

~~~xml
<property name="release.channel" value="stable" />

<ant antfile="modules/catalog/build.xml"
     dir="modules/catalog"
     target="package"
     inheritAll="false">
    <property name="module.package.channel" value="preview" />
</ant>
~~~

Child build đọc `module.package.channel` cho cấu hình riêng, trong khi `release.channel` vẫn có thể là metadata chung được truyền nếu cần.

## 11. Truyền đường dẫn và xử lý basedir

Một lỗi thường gặp trong dự án nhiều module là truyền đường dẫn tương đối nhưng child build lại chạy với base directory khác.

Giả sử parent có:

~~~xml
<property name="repo.root" location="${basedir}" />
<property name="dist.root" location="${repo.root}/dist" />
~~~

Khi gọi child:

~~~xml
<ant antfile="${repo.root}/modules/catalog/build.xml"
     dir="${repo.root}/modules/catalog"
     target="package"
     inheritAll="false">
    <property name="module.output.dir"
              location="${dist.root}/catalog" />
</ant>
~~~

Dùng `location` giúp Ant chuẩn hóa giá trị đường dẫn thành đường dẫn tuyệt đối. Điều này giảm phụ thuộc vào thư mục hiện tại khi chạy lệnh Ant từ terminal hoặc CI.

Cần phân biệt:

- `basedir` của parent: thư mục gốc project cha.
- `dir` trong task ant: thư mục làm việc/base directory cho child build.
- `antfile`: file build được gọi.
- `location` trong property: tạo property đường dẫn dựa trên vị trí được chỉ định.

Không nên ghép thủ công các dấu phân cách `/` hoặc `\` theo hệ điều hành khi Ant có thể chuẩn hóa đường dẫn qua `location` và `basedir`.

## 12. Ví dụ tổng hợp: parent truyền property và path cho hai module

Build file gốc:

~~~xml
<project name="multi-module" default="package-all" basedir=".">

    <property name="release.version" value="2.5.0" />
    <property name="dist.dir" location="${basedir}/dist" />
    <property name="repo.root" location="${basedir}" />

    <path id="shared.module.classpath">
        <pathelement location="${repo.root}/lib/shared-api.jar" />
        <pathelement location="${repo.root}/lib/common-utils.jar" />
    </path>

    <target name="build-catalog">
        <ant antfile="${repo.root}/modules/catalog/build.xml"
             dir="${repo.root}/modules/catalog"
             target="package"
             inheritAll="false"
             inheritRefs="false">
            <property name="module.name" value="catalog" />
            <property name="module.version" value="${release.version}" />
            <property name="module.output.dir"
                      location="${dist.dir}/catalog" />
            <reference refid="shared.module.classpath"
                       torefid="module.compile.path" />
        </ant>
    </target>

    <target name="build-billing">
        <ant antfile="${repo.root}/modules/billing/build.xml"
             dir="${repo.root}/modules/billing"
             target="package"
             inheritAll="false"
             inheritRefs="false">
            <property name="module.name" value="billing" />
            <property name="module.version" value="${release.version}" />
            <property name="module.output.dir"
                      location="${dist.dir}/billing" />
            <reference refid="shared.module.classpath"
                       torefid="module.compile.path" />
        </ant>
    </target>

    <target name="package-all"
            depends="build-catalog,build-billing">
        <echo message="All modules packaged for ${release.version}" />
    </target>

</project>
~~~

Mỗi module build file có thể dùng cùng hợp đồng đầu vào:

~~~xml
<project name="module" default="package">

    <target name="compile">
        <mkdir dir="build/classes" />
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false">
            <classpath refid="module.compile.path" />
        </javac>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="${module.output.dir}" />
        <!-- Tạo artifact module và đặt vào module.output.dir -->
        <echo message="Packaging ${module.name} version ${module.version}" />
    </target>

</project>
~~~

Build file module không cần biết toàn bộ cấu hình nội bộ của parent. Nó chỉ cần các đầu vào đã thống nhất: module.name, module.version, module.output.dir và reference module.compile.path.

Ví dụ này giả định hai module có cùng cấu trúc source và cùng cần shared classpath. Nếu module billing có dependency riêng, hãy bổ sung path của nó trong child build hoặc truyền reference riêng; không nên thêm mọi thư viện của mọi module vào path dùng chung.

## 13. Bảo trì hợp đồng giữa các build file

Khi nhiều nhóm sở hữu các module khác nhau, cần ghi rõ hợp đồng giữa parent và child:

| Thành phần | Ví dụ | Trách nhiệm |
|---|---|---|
| Target đầu vào | `package` | Child phải cung cấp target này |
| Property bắt buộc | `module.version` | Parent truyền version |
| Property đầu ra | `module.output.dir` | Child tạo artifact tại vị trí đã thống nhất |
| Reference bắt buộc | `module.compile.path` | Parent cung cấp classpath dùng chung |
| Dependency nội bộ | JAR hoặc module API | Child khai báo thêm dependency riêng |
| Trạng thái lỗi | mã thoát khác 0 | Child phải làm lần gọi thất bại khi package không thành công |

Nên tài liệu hóa:

- Property nào bắt buộc và property nào tùy chọn.
- Giá trị hợp lệ và đơn vị của từng property.
- Reference nào được truyền, thuộc loại data type gì.
- Target nào parent được phép gọi.
- Child tạo output ở đâu và theo tên nào.
- Quy ước mã thoát và cách báo lỗi.
- Phiên bản Ant/JDK tối thiểu.

Khi thay đổi tên property hoặc ID reference, cập nhật cả build file cha, child build và tài liệu hợp đồng trong cùng một thay đổi. Đổi tên một phía có thể làm build chỉ thất bại khi target tương ứng được gọi.

## 14. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Child build không thấy property của parent | `inheritAll=false` hoặc property không được truyền tường minh | Thêm nested property/propertyset hoặc bật kế thừa phù hợp |
| Child không dùng được version truyền từ command line | Gọi build với tên property khác hoặc giá trị không được truyền | Kiểm tra `-D`, tên property và inheritance |
| Property trong child không ghi đè giá trị parent | Property đã được thiết lập trước; Ant property bất biến | Dùng tên property riêng hoặc thiết kế lại nguồn giá trị |
| Reference không tồn tại trong child | Reference không được kế thừa mặc định hoặc thiếu nested reference | Dùng `inheritRefs` có chủ đích hoặc nested `<reference>` |
| Task con báo sai kiểu reference | ID được truyền trỏ tới data type không phù hợp | Kiểm tra data type và vị trí sử dụng `refid` |
| Module dùng sai thư mục output | Đường dẫn tương đối được hiểu theo basedir khác | Dùng `location`, `dir` và property đường dẫn rõ ràng |
| antcall làm target chạy trong trạng thái khó đoán | Lạm dụng antcall và dựa vào property/reference ngầm | Dùng `depends` cho dependency cố định và truyền đầu vào rõ |
| Một module lỗi nhưng build tổng hợp vẫn thành công | Cấu hình bỏ qua lỗi hoặc không kiểm tra trạng thái child | Dùng fail-on-error behavior phù hợp và kiểm tra mã thoát |
| subant không tìm thấy module | Fileset không khớp build.xml hoặc cấu trúc module không đồng nhất | Kiểm tra include, thư mục gốc và target của từng module |
| Module chạy được độc lập nhưng lỗi khi gọi từ parent | Child đang phụ thuộc ngầm vào property/reference của parent | Khai báo hợp đồng đầu vào và test child độc lập |
| Parent và child dùng các giá trị version khác nhau | Property cùng tên được thiết lập ở nhiều nguồn | Chọn một nguồn có thẩm quyền và truyền nhất quán |

Khi điều tra, hãy kiểm tra lần lượt tên target, thư mục làm việc, property đầu vào và reference ID. Log của Ant thường cho biết build file con nào đang chạy; có thể dùng `-verbose` để quan sát thêm quá trình gọi task.

## 15. Nguyên tắc thiết kế

- Dùng `depends` khi target chỉ cần chạy trước trong cùng project.
- Dùng `ant` khi cần gọi build file/module có project context riêng.
- Dùng `antcall` khi thực sự cần gọi target với đầu vào riêng; không dùng thay cho mọi dependency.
- Dùng property cho giá trị đơn giản như version, tên module và đường dẫn.
- Dùng param trong `antcall` để truyền property cho lần gọi target.
- Dùng reference cho data type như path khi task hỗ trợ truyền reference.
- Hiểu rõ `inheritAll` và `inheritRefs` là hai cơ chế độc lập.
- Dùng `inheritAll="false"` khi muốn child chỉ nhận cấu hình được chọn.
- Truyền reference tường minh khi child chỉ cần một số đối tượng cụ thể.
- Nhớ property của Ant là bất biến; tránh thiết kế như biến có thể ghi đè.
- Chuẩn hóa đường dẫn bằng `basedir`, `dir` và `location`.
- Chuẩn hóa hợp đồng target/property/reference giữa các module.

Khi property, param và reference được dùng đúng mục đích, các build file có thể phối hợp mà vẫn giữ ranh giới module rõ ràng. Parent chịu trách nhiệm điều phối và cung cấp đầu vào; child chịu trách nhiệm thực hiện target theo hợp đồng đã công bố. Cách tổ chức này giúp build nhiều dự án dễ kiểm soát hơn và giảm phụ thuộc ngầm giữa các module.

