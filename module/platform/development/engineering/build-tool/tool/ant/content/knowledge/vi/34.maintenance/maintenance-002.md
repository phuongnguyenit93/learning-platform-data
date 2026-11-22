# Tách cấu hình, định nghĩa tái sử dụng và luồng công việc chính trong Apache Ant

Khi dự án còn nhỏ, một file `build.xml` có thể chứa tất cả: đường dẫn nguồn, thư mục đầu ra, classpath, các lệnh copy, biên dịch Java, kiểm thử và đóng gói. Cách viết này nhanh ở giai đoạn đầu, nhưng khi build có nhiều target, nhiều môi trường hoặc nhiều người bảo trì, việc thay đổi một thông số dễ kéo theo sửa mã XML ở nhiều nơi. Một đoạn lệnh bị sao chép nhiều lần còn có thể được cập nhật không đồng đều, gây ra kết quả khác nhau giữa các target.

Với **Apache Ant**, nên phân tách ba trách nhiệm:

1. **Cấu hình:** các giá trị thay đổi theo dự án hoặc môi trường, chẳng hạn `src.dir`, `build.dir`, `dist.dir`, tên artifact và tùy chọn biên dịch.
2. **Định nghĩa tái sử dụng:** các khối khai báo được nhiều nơi dùng lại, chẳng hạn `<path>`, `<fileset>`, `<patternset>`, `<macrodef>`, `<presetdef>` hoặc target chung.
3. **Luồng công việc chính:** những target thể hiện thứ tự thực thi, ví dụ `clean → init → compile → resources → package`, trong đó `depends` diễn tả quan hệ phụ thuộc.

Sự phân chia này giúp người đọc tìm đúng nơi cần sửa: đổi tên thư mục đầu ra trong cấu hình, đổi hành vi copy chung trong định nghĩa và đổi thứ tự các giai đoạn trong luồng công việc. Mục tiêu là giữ build **rõ ràng, tái sử dụng được và có thể dự đoán**, không phải tăng số lượng file một cách máy móc.

## 1. Vì sao một `build.xml` lớn khó bảo trì?

Xét ví dụ rút gọn:

~~~xml
<project name="legacy-demo" default="package" basedir=".">
    <target name="compile">
        <mkdir dir="build/classes"/>
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false"/>
    </target>

    <target name="copy-main">
        <copy todir="build/classes">
            <fileset dir="src/main/resources"
                     excludes="**/*.tmp"/>
        </copy>
    </target>

    <target name="copy-assets">
        <copy todir="build/assets">
            <fileset dir="src/assets"
                     excludes="**/*.tmp"/>
        </copy>
    </target>

    <target name="package" depends="compile,copy-main,copy-assets">
        <jar basedir="build/classes"
             destfile="dist/demo.jar"/>
    </target>
</project>
~~~

Cấu hình này bộc lộ một số vấn đề khi quy mô tăng:

- Đường dẫn `build/classes` được lặp lại; nếu đổi thư mục output, phải sửa nhiều vị trí.
- Hai target copy có cấu trúc gần giống nhau; muốn thay đổi quy tắc loại trừ file cần cập nhật ở nhiều nơi.
- `package` mô tả công việc cuối cùng nhưng không tách riêng phần chuẩn bị đường dẫn đầu ra.
- Classpath, tên artifact, phiên bản Java và tùy chọn môi trường có thể dần bị nhúng trực tiếp vào các task.
- Người mới cần đọc một khối XML lớn để xác định cấu hình nào là đầu vào và target nào tạo kết quả cuối cùng.

Tách trách nhiệm cho phép thay đổi một phần mà ít tác động đến các phần còn lại. Tuy nhiên, không nên trừu tượng hóa mọi task đơn giản: một lệnh `<mkdir>` dùng đúng một lần có thể giữ trực tiếp trong target `init`.

## 2. Mô hình tổ chức ba lớp

Một cấu trúc gọn cho dự án Ant:

~~~text
maintainable-ant/
├── build.xml                    # Luồng công việc chính
├── config/
│   └── build.properties         # Giá trị cấu hình
├── ant/
│   └── common.xml               # Định nghĩa dùng chung
├── src/
│   └── main/
│       ├── java/
│       │   └── demo/
│       │       └── Main.java
│       └── resources/
│           └── app.properties
├── lib/                         # JAR phụ thuộc nếu dự án dùng
└── out/                         # Output sinh ra, có thể xóa
    ├── build/
    └── dist/
~~~

Sơ đồ quan hệ:

~~~mermaid
flowchart TD
    P[config/build.properties<br/>Giá trị cấu hình] --> B[build.xml<br/>Điều phối target]
    D[ant/common.xml<br/>Path, macro, định nghĩa] --> B
    B --> T[clean, init, compile, resources, package]
    T --> O[out/build và out/dist]
~~~

Trong cấu trúc này, `config/` và `ant/` chứa **đầu vào do nhóm phát triển bảo trì**. Thư mục `out/` chứa **kết quả được sinh ra**. Phân biệt hai loại thư mục rất quan trọng: không đặt file định nghĩa Ant bên trong thư mục mà target `clean` sẽ xóa.

Thực tế dự án có thể dùng tên khác như `build-support/`, `build-logic/` hoặc `properties/`. Điều quan trọng là ý nghĩa và quyền sở hữu của từng phần rõ ràng.

## 3. Tách giá trị cấu hình vào file properties

Tạo `config/build.properties`:

~~~properties
# Cac duong dan tuong doi so voi basedir cua build.
src.dir=src/main/java
resources.dir=src/main/resources
lib.dir=lib

# Chi chua output duoc sinh ra.
build.dir=out/build
dist.dir=out/dist

# Thong tin artifact va tuy chon chung.
artifact.name=maintainable-demo.jar
java.encoding=UTF-8
~~~

File `.properties` phù hợp cho cấu hình dạng `key=value`. Có thể giữ chú thích và nhóm các property theo mục đích. Các giá trị đường dẫn này được dùng trong task Ant, thay vì lặp lại chuỗi đường dẫn tại từng nơi.

Trong file chính, nạp bằng:

~~~xml
<property file="config/build.properties"/>
~~~

Sau khi nạp, sử dụng biến theo cú pháp `${tên.property}`:

~~~xml
<mkdir dir="${build.dir}"/>
<mkdir dir="${dist.dir}"/>
~~~

### Property trong Ant thường được gán một lần

Một đặc điểm quan trọng của Ant là **property thông thường có tính bất biến sau khi được đặt**: lần khai báo sau không tự ghi đè giá trị đã có. Cơ chế này ảnh hưởng trực tiếp đến thứ tự nạp cấu hình.

Ví dụ:

~~~xml
<project name="property-order" default="show" basedir=".">
    <property name="build.dir" value="out/custom"/>
    <property file="config/build.properties"/>

    <target name="show">
        <echo message="build.dir = ${build.dir}"/>
    </target>
</project>
~~~

Ở đây `build.dir` được gán `out/custom` trước nên giá trị `build.dir=out/build` trong file properties không thay thế nó. Nếu muốn file properties cung cấp mặc định, hãy đặt việc nạp file ở vị trí phù hợp **trước những định nghĩa phụ thuộc vào nó**.

### Ghi đè bằng tham số lệnh

Ant hỗ trợ truyền property qua `-D`:

~~~bash
ant -f build.xml -Dbuild.dir=out/ci-build package
~~~

Giá trị truyền qua command line có độ ưu tiên phù hợp để tùy biến cấu hình build, và `<property file="..."/>` không tự ghi đè giá trị này. Nhờ đó một buildfile có thể dùng tại máy phát triển và CI với các thư mục output khác nhau mà không cần sửa mã XML.

Trên Windows PowerShell, nếu đường dẫn có dấu cách, đặt toàn bộ đối số property trong dấu nháy phù hợp, ví dụ:

~~~powershell
ant -f build.xml "-Dbuild.dir=out/CI Build" package
~~~

**Lưu ý về cấu hình dẫn xuất:** nếu `classes.dir` được định nghĩa từ `build.dir`, cần đặt `build.dir` trước thời điểm `classes.dir` được thiết lập. Vì Ant không tự cập nhật property đã gán, thay đổi `build.dir` sau đó không làm `classes.dir` tự tính lại. Ví dụ ở phần tiếp theo sẽ tính `classes.dir` khi file định nghĩa chung được import.

### Các loại giá trị nên đưa ra file cấu hình

| Nhóm | Ví dụ | Lý do |
|---|---|---|
| Thư mục | `src.dir`, `resources.dir`, `build.dir`, `dist.dir` | Dễ đổi bố cục dự án, môi trường CI |
| Artifact | `artifact.name` | Không phải sửa trực tiếp task đóng gói |
| Công cụ | Tùy chọn compiler, encoding, path đến công cụ phụ trợ | Tập trung các giá trị thay đổi |
| Chế độ build | Cờ bật/tắt phần việc có kiểm soát | Dễ quan sát cấu hình thực tế |
| Môi trường | Đường dẫn cục bộ, endpoint thử nghiệm | Tách các giá trị phụ thuộc môi trường |

Không nên commit mật khẩu, token hay khóa bí mật vào file properties trong repository. Với giá trị nhạy cảm, sử dụng cơ chế truyền bí mật của môi trường chạy hoặc CI, đồng thời tránh in giá trị qua `<echo>`.

## 4. Tập trung các định nghĩa tái sử dụng vào `ant/common.xml`

Tạo `ant/common.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-common">

    <!-- Gia tri dan xuat: su dung property da nap tu build.xml. -->
    <property name="classes.dir"
              location="${build.dir}/classes"/>

    <!-- Path dung chung cho cac task can dependency Java. -->
    <path id="compile.classpath">
        <fileset dir="${lib.dir}"
                 includes="**/*.jar"
                 erroronmissingdir="false"/>
    </path>

    <!-- Mot thao tac copy co tham so, co the goi nhieu lan. -->
    <macrodef name="copy-resource-tree">
        <attribute name="from"/>
        <attribute name="to"/>
        <sequential>
            <copy todir="@{to}">
                <fileset dir="@{from}">
                    <exclude name="**/*.tmp"/>
                </fileset>
            </copy>
        </sequential>
    </macrodef>

</project>
~~~

File này định nghĩa ba thành phần phục vụ tái sử dụng:

1. **`classes.dir`:** giá trị dẫn xuất từ thư mục output; chỉ cần thay đổi `build.dir` là mọi task dùng `classes.dir` đều nhận đường dẫn tính theo cùng nguồn.
2. **`compile.classpath`:** một tham chiếu `id` đến tập JAR trong `lib.dir`; các task Java có thể dùng lại bằng `refid`.
3. **`copy-resource-tree`:** một macro có hai tham số `from` và `to`, bao gồm quy tắc bỏ qua file `.tmp`. Những nơi cần copy không phải chép lại toàn bộ cấu trúc `<copy>`.

Thuộc tính `erroronmissingdir="false"` giúp `fileset` của classpath không báo lỗi nếu thư mục `lib` chưa được tạo vì dự án chưa có JAR phụ thuộc. Nếu dự án yêu cầu nhất định phải có thư mục này, nên bỏ cơ chế cho phép thiếu và báo lỗi rõ ràng.

### `${property}` và `@{attribute}` khác nhau thế nào?

Đây là hai cách tham chiếu có mục đích khác nhau:

- `${build.dir}` là property của Ant project, được nạp/tạo theo quy tắc property của Ant.
- `@{from}` là **attribute của `macrodef`**, lấy giá trị tại từng lần gọi macro.

Khi gọi:

~~~xml
<copy-resource-tree from="src/main/resources"
                    to="out/build/classes"/>
~~~

Ant thay `@{from}` và `@{to}` theo lời gọi đó. Cùng một macro có thể dùng cho cặp thư mục khác mà không cần đổi property toàn cục.

## 5. Giữ `build.xml` làm điểm vào và điều phối target

File `build.xml` chính:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="maintainable-demo"
         default="package"
         basedir=".">

    <!-- 1. Nap thong so truoc khi dinh nghia dung chung. -->
    <property file="config/build.properties"/>

    <!-- 2. Nap cac macro, path va gia tri dan xuat. -->
    <import file="ant/common.xml"/>

    <!-- 3. Dinh nghia luong cong viec. -->
    <target name="clean" description="Remove generated output">
        <delete dir="${build.dir}" failonerror="true"/>
        <delete dir="${dist.dir}" failonerror="true"/>
    </target>

    <target name="init">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="${java.encoding}"
               includeantruntime="false">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>

    <target name="resources" depends="init">
        <copy-resource-tree from="${resources.dir}"
                            to="${classes.dir}"/>
    </target>

    <target name="package"
            depends="compile,resources"
            description="Compile and assemble distributable JAR">
        <jar basedir="${classes.dir}"
             destfile="${dist.dir}/${artifact.name}"/>
    </target>

</project>
~~~

Với ví dụ này, file chính vẫn đủ rõ để nhìn ra các bước của build nhưng không chứa lại toàn bộ cấu hình copy và classpath. Nội dung Java, tài nguyên và thư viện thuộc cấu trúc dự án; nếu không có thư mục `src/main/resources` thì cần bỏ target copy tương ứng hoặc cung cấp thư mục theo cấu hình thực tế.

### Cách Ant thực hiện chuỗi target

Lệnh:

~~~bash
ant -f build.xml package
~~~

Dựa trên quan hệ `depends`:

~~~mermaid
flowchart LR
    I[init] --> C[compile]
    I --> R[resources]
    C --> P[package]
    R --> P
~~~

`package` chỉ chạy sau khi các target phụ thuộc đã hoàn thành theo quy tắc của Ant. Trong một lần chạy cùng project, `init` không phải chạy hai lần dù `compile` và `resources` đều phụ thuộc vào nó.

Muốn dọn output rồi tạo mới:

~~~bash
ant -f build.xml clean package
~~~

Ở đây `clean` được yêu cầu trực tiếp qua dòng lệnh. **`package` không phụ thuộc vào `clean`** vì build thông thường không nên tự động xóa toàn bộ đầu ra trước mỗi lần chạy. Cách tách này giữ được khả năng build tăng dần và cho phép người sử dụng chủ động chọn clean build.

Chạy Ant từ một thư mục khác có thể dùng tham số `-f` với đường dẫn đầy đủ đến `build.xml`. Khi tính đường dẫn dự án, lưu ý giá trị `basedir` và file đang được Ant nạp; không mặc định thư mục làm việc của mọi command line là nơi chứa buildfile.

### Đọc tên target và mô tả

Có thể xem các target công khai có mô tả:

~~~bash
ant -f build.xml -projecthelp
~~~

Thêm `description` cho target mà người dùng/CI cần gọi trực tiếp (chẳng hạn `clean`, `package`) giúp file build tự giải thích được giao diện sử dụng. Các target nội bộ như `init` có thể không cần mô tả nếu không được dùng trực tiếp.

## 6. `<import>` kết nối các phần như thế nào?

Task `<import file="ant/common.xml"/>` nạp định nghĩa từ file XML khác vào **cùng ngữ cảnh project Ant**. Nó phù hợp khi muốn tách các phần của một build có chung property, path, macro và target.

Trong ví dụ:

1. `build.xml` nạp `config/build.properties`.
2. `<import>` nạp `ant/common.xml`.
3. `ant/common.xml` tạo `classes.dir` dựa trên `build.dir` đã có và đăng ký `compile.classpath` cùng macro.
4. Target `compile` và `resources` trong file chính sử dụng định nghĩa đó.

### Đường dẫn trong file được import

Cần phân biệt:

- Đường dẫn trong thuộc tính `file` của `<import>` được xử lý trong mối quan hệ với file có lệnh import.
- Đường dẫn tương đối của nhiều task khi thực thi vẫn theo `basedir` của Ant project, không tự động chuyển sang thư mục của file XML được import.

Vì vậy, nếu `ant/common.xml` khai báo `<fileset dir="lib">`, đừng mặc định thư mục này là `ant/lib`. Trong cấu trúc của bài học, property `lib.dir=lib` mô tả thư mục `lib/` ở gốc project.

Khi thật sự cần tài nguyên nằm cạnh file được import, Ant cung cấp property đặc biệt theo tên project được import (chẳng hạn `ant.file.ant-common` với project name tương ứng). Có thể xác định thư mục bằng task `<dirname>` rồi xây dựng đường dẫn từ đó:

~~~xml
<dirname property="ant.common.dir"
         file="${ant.file.ant-common}"/>
~~~

Cách này hữu ích nếu file dùng chung đi kèm cấu hình/template riêng bên cạnh nó. Tuy nhiên chỉ nên thêm khi có nhu cầu cụ thể, tránh tăng số property dẫn xuất không cần thiết.

### Trùng tên target giữa file chính và file được import

Ant cho phép file chính **ghi đè** một target cùng tên từ file được import. Điều này có thể có chủ đích, nhưng dễ gây bất ngờ khi nhiều nhóm cùng sửa file:

~~~xml
<!-- ant/common.xml -->
<target name="prepare">
    <echo message="Common prepare"/>
</target>
~~~

~~~xml
<!-- build.xml -->
<target name="prepare">
    <echo message="Project prepare"/>
</target>
~~~

Target tên `prepare` trong file chính được ưu tiên theo cơ chế import. Trong trường hợp cần gọi target gốc đã được import, Ant hỗ trợ tên có tiền tố theo project được import, chẳng hạn `ant-common.prepare` khi phù hợp với tên project/prefix đang dùng.

Để hạn chế va chạm không chủ đích, hãy đặt tên rõ nghĩa, ví dụ `common.init-tools` thay vì dùng lại các tên chung chung quá nhiều, và quy định file nào sở hữu target điều phối.

## 7. Chọn cơ chế tái sử dụng phù hợp

Ant có nhiều cơ chế chia sẻ logic, nhưng không phải cơ chế nào cũng thích hợp cho cùng một nhu cầu.

| Cơ chế | Dùng khi | Ví dụ |
|---|---|---|
`<property>` / `<property file>` | Chia sẻ giá trị cấu hình | `build.dir`, `artifact.name` |
`<path id=...>` và `refid` | Chia sẻ classpath hay tập đường dẫn | Compile/test cùng dùng thư viện |
`<fileset>` / `<patternset>` với `id/refid` | Tái sử dụng danh sách file hoặc mẫu include/exclude | Nhiều task dùng chung tập tài nguyên |
`<macrodef>` | Dùng lại chuỗi task có tham số | Copy, kiểm tra, đóng gói nhiều thư mục |
`<presetdef>` | Dùng lại cấu hình mặc định của một task | Cùng encoding và cờ biên dịch |
`<import>` | Chia tệp định nghĩa trong cùng Ant project | `build.xml` nạp `ant/common.xml` |
`<include>` | Nạp target từ file khác với cơ chế đặt tên target có tiền tố | Tách các nhóm target lớn |
`<ant>` / `<subant>` | Gọi buildfile/project riêng hoặc nhiều build con | Multi-module có buildfile độc lập |
`depends` | Diễn tả luồng target trong cùng project | `package` cần `compile` |

### Chia sẻ một `path` bằng `id` và `refid`

Đã định nghĩa trong `ant/common.xml`:

~~~xml
<path id="compile.classpath">
    <fileset dir="${lib.dir}"
             includes="**/*.jar"
             erroronmissingdir="false"/>
</path>
~~~

Sử dụng:

~~~xml
<javac srcdir="${src.dir}"
       destdir="${classes.dir}"
       includeantruntime="false">
    <classpath refid="compile.classpath"/>
</javac>
~~~

`id` đặt tên một đối tượng tham chiếu trong Ant project; `refid` lấy lại đối tượng đó. Cách này tránh lặp toàn bộ `<fileset>` thư viện ở từng task, đồng thời tạo một nơi thống nhất để cập nhật classpath.

### Tái sử dụng bộ quy tắc lọc file

Ví dụ chia sẻ một `patternset`:

~~~xml
<patternset id="common.resource.patterns">
    <include name="**/*"/>
    <exclude name="**/*.tmp"/>
    <exclude name="**/*.bak"/>
</patternset>
~~~

Một task copy sử dụng lại:

~~~xml
<copy todir="${classes.dir}">
    <fileset dir="${resources.dir}">
        <patternset refid="common.resource.patterns"/>
    </fileset>
</copy>
~~~

Nếu nhiều task áp dụng cùng một quy tắc lọc, việc dùng chung `patternset` làm giảm nguy cơ target này quên loại trừ `.tmp` nhưng target khác vẫn loại trừ.

### `macrodef` hay `presetdef`?

`macrodef` phù hợp với **một nhóm thao tác có tham số**:

~~~xml
<macrodef name="copy-tree">
    <attribute name="source"/>
    <attribute name="target"/>
    <sequential>
        <mkdir dir="@{target}"/>
        <copy todir="@{target}">
            <fileset dir="@{source}"/>
        </copy>
    </sequential>
</macrodef>
~~~

Gọi:

~~~xml
<copy-tree source="src/main/resources"
           target="out/build/classes"/>
~~~

`presetdef` hữu ích khi muốn **tạo biến thể của một task** có sẵn với các thuộc tính mặc định:

~~~xml
<presetdef name="javac-standard">
    <javac encoding="UTF-8"
           debug="true"
           includeantruntime="false"/>
</presetdef>
~~~

Sau đó:

~~~xml
<javac-standard srcdir="${src.dir}"
                destdir="${classes.dir}"/>
~~~

Không cần tạo macro cho mỗi task một dòng; chỉ tách khi quy tắc dùng lại thật sự mang ý nghĩa và có nhiều nơi cần áp dụng.

## 8. Thiết kế luồng công việc bằng `depends`

Một build dễ bảo trì cần phân biệt **công việc phải làm** với **thứ tự công việc**. Trong Ant, target giữ các thao tác; thuộc tính `depends` khai báo những target cần hoàn tất trước.

Ví dụ luồng thông thường:

~~~mermaid
flowchart TD
    A[init] --> B[compile]
    A --> C[resources]
    B --> D[test]
    C --> E[package]
    D --> E
    E --> F[verify artifact]
~~~

Sơ đồ này minh họa cách mở rộng quy trình, không phải khẳng định ví dụ `build.xml` ở phần 5 đã chứa target `test` hoặc `verify`. Khi bổ sung các target đó, phải triển khai task kiểm thử/xác minh thực tế và cập nhật dependencies phù hợp.

### Những nguyên tắc thiết kế target

1. **Target đại diện một mục đích rõ ràng.** `compile` phụ trách biên dịch; `package` phụ trách tạo artifact; `clean` phụ trách dọn output.
2. **Phụ thuộc diễn tả yêu cầu thực sự.** Chỉ đặt `depends="compile"` nếu target cần kết quả biên dịch.
3. **Hạn chế phụ thuộc vào hiệu ứng bên ngoài.** Một target đòi file được tạo ở target khác nên khai báo quan hệ thay vì chỉ giả định người dùng sẽ gọi đúng thứ tự.
4. **Chọn target mặc định có ý nghĩa.** `default="package"` cho phép `ant` chạy quy trình chính của dự án.
5. **Không ép clean vào mọi build.** Dọn output nên là lựa chọn có chủ ý, trừ khi quy trình thực sự đòi trạng thái sạch.

### Vì sao không dùng `<antcall>` thay `depends` cho mọi target?

`<antcall>` cho phép gọi target của build hiện tại trong ngữ cảnh Ant project con với cơ chế truyền property/reference riêng. Nó hữu ích trong một số tình huống tham số hóa đặc biệt, nhưng không phải lựa chọn đơn giản nhất để diễn tả quan hệ bắt buộc giữa các target của cùng build.

Nếu `package` luôn cần `compile`, viết:

~~~xml
<target name="package" depends="compile">
    <!-- Tao artifact o day -->
</target>
~~~

thường dễ đọc hơn so với nhúng một lời gọi `<antcall target="compile"/>`. Dùng `depends` cũng giúp Ant quản lý target đã chạy trong cùng lượt thực thi và biểu diễn được đồ thị phụ thuộc.

## 9. Khác biệt giữa `<import>`, `<include>` và build con

Khi một dự án lớn có nhiều nhóm target, có thể cần phân tách nhiều file XML hơn. Lúc đó, cần chọn cách kết nối đúng:

### `<import>`: hợp nhất các định nghĩa

~~~xml
<import file="ant/common.xml"/>
~~~

Các định nghĩa được nạp vào project đang chạy; target từ file import có thể tương tác với target chính và có cơ chế override của import. Phù hợp cho macro, path và nhóm target dùng chung.

### `<include>`: đưa target vào dưới tên có tiền tố

~~~xml
<include file="ant/checks.xml"/>
~~~

`<include>` thiên về việc nạp nhóm target với tên được đặt tiền tố, giúp tránh va chạm target giữa nhiều file. Cách đặt tiền tố thực tế phụ thuộc vào `name` của project được include và các thuộc tính điều chỉnh prefix nếu được cấu hình. Khi muốn tách từng nhóm target thành không gian tên dễ nhận diện, đây là lựa chọn đáng cân nhắc.

### `<ant>`: chạy một buildfile riêng

~~~xml
<target name="build-child">
    <ant antfile="module-a/build.xml"
         target="package"
         inheritAll="false"/>
</target>
~~~

`<ant>` dùng để chạy build của một project/buildfile con; cách truyền property, basedir và reference khác với import trực tiếp trong cùng project. Ví dụ `inheritAll="false"` thể hiện mong muốn giới hạn property kế thừa, nhưng một số property nội tại và các giá trị được truyền rõ ràng vẫn phải được hiểu theo quy tắc Ant.

Nếu một nhóm mã nguồn có vòng đời build và file `build.xml` độc lập, có thể dùng `<ant>`/`<subant>`. Nếu chỉ muốn dùng lại một bước copy, `<macrodef>` đơn giản hơn. Không nên biến mọi target nhỏ thành một buildfile con chỉ để tách file.

## 10. Quản lý cấu hình theo môi trường mà không nhân bản buildfile

Một nhu cầu phổ biến là máy phát triển dùng thư mục `out/build`, còn CI dùng thư mục riêng theo job.

Có thể giữ cấu hình mặc định trong `config/build.properties` rồi truyền giá trị khác khi chạy:

~~~bash
# Ban build mac dinh cho dev
ant -f build.xml package

# Ban build cho CI, cach ly output
ant -f build.xml -Dbuild.dir=out/ci/build -Ddist.dir=out/ci/dist package
~~~

Với cấu trúc ở phần 5, `classes.dir` được tính sau khi nạp property nên phản ánh `build.dir` đã được truyền khi Ant bắt đầu. Mục đích không phải hard-code tên môi trường vào nhiều nhánh `<if>`, mà là để cấu hình điều khiển các giá trị khác nhau.

Nếu dự án thật sự có nhiều tập giá trị, có thể tách các file properties theo mục đích và xác định **thứ tự nạp** rõ ràng. Vì property thường không bị ghi đè, file nạp trước có thể giữ giá trị ưu tiên so với file nạp sau. Các file nhạy cảm hoặc cấu hình cục bộ nên được quản lý theo chính sách riêng của dự án, tránh đưa secret vào source control.

### Phân biệt “cấu hình” và “logic”

Nên là property:

~~~properties
artifact.name=service.jar
dist.dir=out/dist
~~~

Nên là logic trong XML:

~~~xml
<jar destfile="${dist.dir}/${artifact.name}"
     basedir="${classes.dir}"/>
~~~

Nếu mọi thay đổi tên artifact đều phải chỉnh sửa `<jar>`, việc tách cấu hình chưa hiệu quả. Ngược lại, đẩy toàn bộ chuỗi lệnh XML vào một property văn bản cũng không làm logic dễ hiểu hơn.

## 11. Tách cấu hình nhưng vẫn bảo đảm lỗi rõ ràng

Khi chuyển giá trị ra file, dễ xuất hiện lỗi thiếu hoặc gõ sai property. Nếu task nhận một chuỗi chưa được thay thế như `${some.dir}`, đường dẫn và thông báo lỗi có thể trở nên khó hiểu.

Có thể kiểm tra cấu hình bắt buộc trước khi thực hiện công việc:

~~~xml
<target name="validate-config">
    <fail unless="src.dir"
          message="Missing required property: src.dir"/>
    <fail unless="build.dir"
          message="Missing required property: build.dir"/>
    <fail unless="dist.dir"
          message="Missing required property: dist.dir"/>
</target>
~~~

Sau đó khai báo:

~~~xml
<target name="init" depends="validate-config">
    <mkdir dir="${classes.dir}"/>
    <mkdir dir="${dist.dir}"/>
</target>
~~~

`<fail unless="...">` kiểm tra property đã được đặt, **không bảo đảm giá trị là đường dẫn hợp lệ hoặc không rỗng**. Nếu cần kiểm soát sâu hơn, dùng `<condition>`, `<available>` hoặc task xác minh thích hợp để kiểm tra từng điều kiện.

Trong dự án yêu cầu bảo vệ output, nên xác định rõ giá trị `build.dir`/`dist.dir` được phép trỏ đến đâu; tránh một lựa chọn tùy tiện cho `clean` xóa dữ liệu không thuộc output của build.

### Không che lỗi bằng target tùy chọn thiếu minh bạch

Nếu file `config/build.properties` bắt buộc, sự vắng mặt của nó nên được phát hiện sớm. Một cách là khai báo property của file và kiểm tra các giá trị quan trọng, hoặc thêm bước xác minh file cấu hình. Nếu một thư mục resources bắt buộc, đừng đặt tất cả `fileset` thành “bỏ qua khi thiếu” chỉ để build kết thúc xanh.

Chỉ cho phép thiếu những đầu vào **thật sự không bắt buộc**, và mô tả điều kiện đó rõ ràng trong build.

## 12. Kế hoạch tách file từ một buildfile cũ

Việc cải tổ một `build.xml` đang dùng nên tiến hành theo những bước nhỏ, có thể đối chiếu kết quả:

1. **Xác định giao diện hiện tại.** Ghi các target mà người dùng/CI gọi, lệnh đầy đủ, tập đầu vào và đường dẫn artifact được tạo. Phân biệt build sạch với build tăng dần.
2. **Lập danh sách property.** Tìm đường dẫn và giá trị lặp lại, phân loại giá trị nào thuộc cấu hình và giá trị nào là logic của target.
3. **Tách cấu hình trước.** Đưa các giá trị phù hợp vào `config/build.properties`; giữ nguyên tên target và luồng build.
4. **Tách định nghĩa tái sử dụng.** Đưa `path`, `patternset`, `macrodef` hoặc các target chung có chủ đích vào `ant/common.xml`, dùng `<import>` theo thứ tự property thích hợp.
5. **Giữ file chính dễ đọc.** Để các target điều phối và quan hệ `depends` tại điểm vào chính; tránh giấu luồng build trong hàng loạt macro.
6. **Đối chiếu hành vi.** Các target quan trọng cần tạo đúng output và mã thoát như trước; thay đổi tổ chức file không được làm mất resource, dependency hoặc bước kiểm thử.
7. **Ghi hướng dẫn sử dụng.** Mô tả target mặc định, lệnh clean build, cách ghi đè property và thư mục output. Đây là phần hỗ trợ nhóm bảo trì về sau.

Đây là quy trình đề xuất khi cải tổ build thật; những đoạn code ở bài học chỉ là ví dụ minh họa cấu trúc và không thay thế việc xác minh với dự án cụ thể.

### Dấu hiệu tách file đã đủ

- Khi đổi một đường dẫn, nhóm phát triển biết ngay file properties cần sửa.
- Khi thay đổi quy tắc copy hoặc classpath chung, chỉ có một định nghĩa có trách nhiệm điều khiển.
- Khi cần biết cách tạo JAR, đọc `build.xml` là nhận ra thứ tự target.
- Khi gặp lỗi, log vẫn cho phép xác định target, task và file cấu hình liên quan.
- Người mới không cần mở nhiều lớp gọi lồng nhau để hiểu quy trình cơ bản.

Nếu phải chuyển qua bốn, năm file XML chỉ để tìm một lệnh `<mkdir>` hoặc mọi target đều gọi macro chỉ chứa một task, cấu trúc có thể đã bị chia nhỏ quá mức.

## 13. Những sai lầm thường gặp khi bảo trì Ant

### Đặt file định nghĩa vào thư mục sẽ bị `clean` xóa

Ví dụ đặt `common.xml` dưới `build/` trong khi `clean` chạy `<delete dir="build"/>` sẽ làm mất file đầu vào của chính build. Tách `ant/` (source do người bảo trì sở hữu) khỏi `out/` (output có thể xóa) giúp tránh lỗi này.

### Định nghĩa property sau khi task/definition đã dùng

Ví dụ `classes.dir` được tính từ `build.dir` trước khi nạp property mong muốn. Vì property thông thường bất biến, thiết lập muộn có thể không thay đổi giá trị đã gán. Hãy nạp giá trị cơ sở trước và tạo giá trị dẫn xuất sau.

### Nhân bản macro thay vì tái sử dụng

Nếu nhiều target chứa cùng một khối `<copy>` và cùng quy tắc loại trừ, một lần sửa chính sách copy phải cập nhật nhiều vị trí. Dùng macro hoặc patternset để giữ một nguồn định nghĩa.

### Lạm dụng `<antcall>` cho luồng tuyến tính

Thay vì dùng `depends` để Ant biết thứ tự công việc, nhiều lời gọi `<antcall>` có thể làm người đọc khó theo dấu property và target đang chạy. Dùng `depends` cho luồng trong một project; chỉ dùng lời gọi build/target đặc biệt khi có nhu cầu riêng.

### Trùng tên `id`, macro hoặc target giữa các file import

Hai file chung có tên tham chiếu giống nhau có thể gây va chạm hoặc tạo hành vi ghi đè không rõ ràng. Đặt tên có ngữ cảnh, như `compile.classpath` và `resources.common.patterns`; với target import, hiểu rõ cơ chế tiền tố và ưu tiên.

### Giấu toàn bộ luồng build trong file “common”

File định nghĩa chung chỉ nên sở hữu hành vi thật sự dùng chung. Nếu file chính chỉ còn vài dòng import và không cho thấy các bước build, người bảo trì sẽ khó hiểu điểm vào và quan hệ phụ thuộc.

### Cấu hình riêng từng máy nằm trong repository

Đường dẫn cứng như `C:\Users\Alice\...` hoặc thư mục tuyệt đối của một máy làm build khó chạy trên máy khác. Dùng đường dẫn tương đối, property cấu hình và giá trị được truyền từ môi trường phù hợp.

### Xem refactor cấu trúc là lý do thay đổi chức năng

Tách file nên bảo toàn kết quả build hiện có. Không nên đồng thời đổi compiler, loại bỏ test hoặc đổi nội dung artifact nếu mục tiêu chỉ là giúp bảo trì dễ hơn; nếu cần sửa nghiệp vụ build, hãy mô tả riêng.

## 14. Tình huống thực hành

### Bài tập A — Đổi thư mục output cho CI

Giả sử build trên máy phát triển dùng `out/build` nhưng CI cần `out/job-42/build`. Với cấu trúc đã tách:

~~~bash
ant -f build.xml \
  -Dbuild.dir=out/job-42/build \
  -Ddist.dir=out/job-42/dist \
  clean package
~~~

Trên Linux/macOS, dấu `\` ở cuối dòng trong ví dụ là ký tự tiếp dòng của shell. Trên Windows PowerShell, nên viết một dòng hoặc dùng ký tự tiếp dòng phù hợp của PowerShell:

~~~powershell
ant -f build.xml "-Dbuild.dir=out/job-42/build" "-Ddist.dir=out/job-42/dist" clean package
~~~

**Cần giải thích:** vì `classes.dir` được tính từ `build.dir` sau khi nạp property, mã XML trong target `compile` không cần đổi.

### Bài tập B — Cả tài nguyên chính và tài nguyên báo cáo đều cần loại file `.tmp`

Đề xuất dùng một `<patternset>` hoặc `<macrodef>` ở file định nghĩa chung. Hai lời gọi có thể truyền thư mục `from` và `to` khác nhau; không sao chép lại nhiều lần chính sách loại trừ.

Ví dụ:

~~~xml
<copy-resource-tree from="${resources.dir}"
                    to="${classes.dir}"/>
<copy-resource-tree from="src/report-assets"
                    to="${dist.dir}/report-assets"/>
~~~

Hai lần gọi dùng chung macro nhưng có dữ liệu khác nhau; chỉ nên thêm lời gọi thứ hai nếu dự án thực sự có thư mục `src/report-assets` và yêu cầu đóng gói tương ứng.

### Bài tập C — Target `package` chạy khi chưa có tài nguyên

Nếu `package` cần cả mã Java và tài nguyên, cần khai báo:

~~~xml
<target name="package" depends="compile,resources">
    <jar destfile="${dist.dir}/${artifact.name}"
         basedir="${classes.dir}"/>
</target>
~~~

Phần phụ thuộc bảo đảm các target chuẩn bị nội dung hoàn thành trước khi tạo JAR. Đừng chỉ trông chờ người chạy lệnh luôn nhớ gọi `resources` bằng tay.

### Bài tập D — Nhiều nhóm cần dùng chung thao tác đóng gói

Nếu quy trình đóng gói gồm nhiều task lặp lại giữa các module, có thể tách một `<macrodef>` được tham số hóa hoặc dùng buildfile chung phù hợp. Nhưng nếu từng module có cách đóng gói và vòng đời hoàn toàn riêng, dùng `<ant>`/`<subant>` để gọi các buildfile độc lập có thể rõ ràng hơn so với ép tất cả module vào một macro lớn.

## 15. Mẫu mô tả kiến trúc build cho người bảo trì

Một README ngắn bên cạnh `build.xml` có thể ghi:

~~~text
Build system: Apache Ant
Entry point: build.xml
Default target: package

Configuration:
  config/build.properties
  - src.dir, resources.dir, lib.dir
  - build.dir, dist.dir, artifact.name, java.encoding

Shared definitions:
  ant/common.xml
  - classes.dir
  - compile.classpath
  - copy-resource-tree macro

Main targets:
  clean       : remove generated outputs
  init        : create output directories
  compile     : compile Java sources
  resources   : copy resources
  package     : assemble JAR after compile and resources

Usage:
  ant -f build.xml package
  ant -f build.xml clean package
  ant -f build.xml -Ddist.dir=out/ci/dist package

Generated outputs:
  out/build/
  out/dist/
~~~

Người tiếp nhận dự án chỉ cần đọc mô tả này và `build.xml` là biết đâu là điểm vào, đâu là cấu hình, đâu là phần dùng chung và output nào có thể bị xóa. Nếu quy trình thay đổi, giữ phần mô tả này đồng bộ với build thật.

Điểm mấu chốt của bảo trì Ant là **đưa mỗi loại trách nhiệm về đúng nơi**. File properties diễn đạt các giá trị có thể thay đổi; file định nghĩa chung diễn đạt hành vi lặp lại; file `build.xml` chính cho thấy các bước và thứ tự thực thi. Khi cả ba phần rõ ràng, việc đổi môi trường, thêm task, sửa classpath hoặc mở rộng pipeline sẽ ít gây tác động ngoài ý muốn hơn.
