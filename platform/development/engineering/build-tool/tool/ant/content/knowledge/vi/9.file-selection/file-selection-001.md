# FileSet, DirSet và thư mục gốc khi quét tệp

## Mục tiêu

Apache Ant thường cần tìm một nhóm tệp hoặc thư mục để biên dịch, sao chép, đóng gói, xóa hoặc đưa vào classpath. Thay vì liệt kê từng đường dẫn, Ant cung cấp các kiểu dữ liệu `FileSet` và `DirSet`. Cả hai đều dựa trên cơ chế quét thư mục và chọn các mục theo các mẫu include/exclude.

Điểm quan trọng nhất khi dùng chúng là xác định đúng **thư mục gốc của lần quét**:

- Thuộc tính `dir` của `fileset` hoặc `dirset` chỉ định thư mục gốc để quét.
- Các mẫu `include` và `exclude` được tính tương đối từ thư mục gốc đó.
- `FileSet` trả về các tệp phù hợp.
- `DirSet` trả về các thư mục phù hợp.

Thư mục gốc của một set không đồng nghĩa với `basedir` của project. `basedir` giúp Ant giải quyết các đường dẫn tương đối được khai báo trong buildfile; còn `dir` xác định cây thư mục cụ thể mà set sẽ quét.

## 1. FileSet và DirSet là gì?

### 1.1. FileSet chọn tệp

`FileSet` biểu diễn một tập hợp các tệp nằm trong một thư mục gốc và thỏa mãn các điều kiện chọn. Ví dụ:

~~~xml
<fileset dir="src">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
</fileset>
~~~

Set trên quét cây thư mục `src`, chọn các tệp Java ở mọi cấp thư mục và loại các tệp nằm trong thư mục có tên `generated`.

Kết quả là một tập hợp các tệp. Các thư mục được duyệt để tìm tệp, nhưng bản thân thư mục không trở thành phần tử của FileSet.

### 1.2. DirSet chọn thư mục

`DirSet` có cấu trúc khai báo gần giống FileSet, nhưng kết quả là các thư mục phù hợp với mẫu.

~~~xml
<dirset dir="modules">
    <include name="*/classes"/>
    <exclude name="legacy/**"/>
</dirset>
~~~

Set này quét từ thư mục `modules`, chọn các thư mục `classes` nằm ngay bên trong từng thư mục con cấp một, rồi loại các thư mục nằm dưới nhánh `legacy` theo mẫu loại trừ.

DirSet không trả về các tệp nằm trong những thư mục đó. Nếu cần danh sách tệp, hãy dùng FileSet.

### 1.3. So sánh nhanh

| Đặc điểm | FileSet | DirSet |
|---|---|---|
| Mục đích | Chọn tệp | Chọn thư mục |
| Thư mục gốc | Thuộc tính `dir` | Thuộc tính `dir` |
| Mẫu chọn | Tính tương đối từ thư mục gốc | Tính tương đối từ thư mục gốc |
| Kết quả | Các tệp phù hợp | Các thư mục phù hợp |
| Trường hợp thường gặp | Nguồn Java, tài nguyên, file cấu hình, file cần đóng gói | Thư mục lớp đã biên dịch, thư mục module, thư mục cần đưa vào classpath |

Cả hai dùng chung cách viết pattern và nhiều tùy chọn quét. Khác biệt cốt lõi là loại mục mà chúng đưa vào tập kết quả.

## 2. Thư mục gốc của lần quét

### 2.1. Thuộc tính dir xác định gốc của FileSet hoặc DirSet

Xét buildfile:

~~~xml
<project name="scan-demo" default="show" basedir=".">
    <fileset id="java.sources" dir="src">
        <include name="**/*.java"/>
    </fileset>

    <path id="source.path">
        <fileset refid="java.sources"/>
    </path>

    <target name="show">
        <pathconvert property="source.list" refid="source.path"/>
        <echo message="Sources: ${source.list}"/>
    </target>
</project>
~~~

Ở đây có hai khái niệm khác nhau:

- `basedir="."` là thư mục cơ sở của project. Dấu chấm biểu thị thư mục hiện tại của buildfile theo cách Ant xác định project base.
- `dir="src"` là thư mục gốc riêng của FileSet. Vì nó là đường dẫn tương đối, Ant giải quyết nó từ project basedir.

Sau khi giải quyết, FileSet quét bên trong thư mục `src`. Pattern `**/*.java` bắt đầu tính từ `src`, không tính từ project basedir.

Nếu project nằm ở `/work/sample`, thư mục gốc của FileSet sẽ là `/work/sample/src`. Pattern `**/*.java` vì vậy có thể chọn:

~~~text
src/App.java
src/main/java/org/example/Main.java
src/test/java/org/example/MainTest.java
~~~

Các đường dẫn tương đối được biểu diễn theo thư mục gốc của FileSet. Task nhận set có thể dùng các đường dẫn này để duy trì cấu trúc thư mục khi sao chép hoặc xử lý.

### 2.2. Pattern không cần lặp lại tên thư mục gốc

Khi khai báo:

~~~xml
<fileset dir="src">
    <include name="**/*.java"/>
</fileset>
~~~

Pattern đúng là `**/*.java`, vì nó được tính từ `src`.

Không cần viết:

~~~xml
<fileset dir="src">
    <include name="src/**/*.java"/>
</fileset>
~~~

Cách viết thứ hai đang tìm một nhánh `src` nằm bên trong thư mục gốc đã là `src`. Nếu cây thư mục không có `src/src`, kết quả sẽ rỗng.

Ví dụ tương tự với DirSet:

~~~xml
<dirset dir="modules">
    <include name="**/classes"/>
</dirset>
~~~

Pattern `**/classes` được tính từ `modules`; không viết `modules/**/classes`.

### 2.3. Project basedir và set dir có thể khác nhau

Giả sử buildfile có cấu trúc:

~~~text
workspace/
├── build.xml
├── app/
│   └── src/
└── shared/
    └── config/
~~~

Có thể khai báo:

~~~xml
<project name="workspace" default="show" basedir=".">
    <fileset id="app.sources" dir="app/src">
        <include name="**/*.java"/>
    </fileset>

    <fileset id="shared.config" dir="shared/config">
        <include name="**/*.properties"/>
    </fileset>

    <target name="show">
        <echo message="Application sources are selected from app/src"/>
        <echo message="Shared configuration is selected from shared/config"/>
    </target>
</project>
~~~

Project có một `basedir`, nhưng mỗi FileSet có thể có thư mục gốc riêng. Điều này cho phép một buildfile quét nhiều vùng khác nhau trong cùng workspace.

Nếu muốn một set quét từ thư mục cha hoặc một vị trí ngoài project, có thể dùng đường dẫn tương đối có `..` hoặc một property chứa đường dẫn tuyệt đối:

~~~xml
<property name="shared.root" location="../shared"/>
<fileset id="shared.files" dir="${shared.root}">
    <include name="**/*"/>
</fileset>
~~~

Ở đây, `location` giúp property `shared.root` biểu diễn một vị trí đã được Ant giải quyết theo project basedir. FileSet sau đó dùng giá trị đó làm gốc quét.

### 2.4. Thư mục gốc không phải là một mục được chọn

`dir` chỉ xác định điểm bắt đầu duyệt cây thư mục. Với DirSet, các pattern chọn những thư mục nằm bên dưới gốc; bản thân thư mục gốc không được xem như một thư mục con để pattern chọn.

Ví dụ:

~~~xml
<dirset dir="modules">
    <include name="**"/>
</dirset>
~~~

Set này chọn các thư mục con bên dưới `modules` theo pattern, chứ không dùng chính `modules` làm một phần tử kết quả. Nếu cần đưa chính thư mục gốc vào một path, hãy khai báo nó trực tiếp bằng `pathelement` hoặc một phần tử path phù hợp:

~~~xml
<path id="module.path">
    <pathelement location="modules"/>
    <dirset dir="modules">
        <include name="**/classes"/>
    </dirset>
</path>
~~~

Cách kết hợp này đưa thư mục gốc vào path một cách tường minh, đồng thời thêm các thư mục con đã chọn.

## 3. Cách viết pattern include và exclude

FileSet và DirSet sử dụng quy tắc pattern của Ant. Pattern được viết theo đường dẫn tương đối với thư mục gốc của set.

### 3.1. Các ký tự đại diện

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| `*` | Khớp không hoặc nhiều ký tự trong một thành phần đường dẫn | `*.xml` |
| `?` | Khớp đúng một ký tự trong một thành phần đường dẫn | `Test?.java` |
| `**` | Khớp qua nhiều cấp thư mục | `**/*.java` |

Dấu gạch chéo `/` được dùng trong pattern để phân cách thành phần đường dẫn, kể cả khi build chạy trên Windows. Ant xử lý đường dẫn theo quy tắc của hệ thống.

Một số ví dụ:

- `*.xml`: các tệp XML ngay trong thư mục gốc.
- `config/*.properties`: các tệp properties ngay trong thư mục con `config`.
- `**/*.java`: các tệp Java ở mọi cấp bên dưới thư mục gốc.
- `**/test/**`: các mục nằm bên dưới một thư mục có tên `test`.
- `**/Test?.java`: các tệp Java có tên bắt đầu bằng `Test`, theo sau là một ký tự trước phần mở rộng.

### 3.2. Dùng include để chọn nội dung cần lấy

Có thể đặt một pattern trong thuộc tính `includes`:

~~~xml
<fileset dir="src" includes="**/*.java"/>
~~~

Hoặc dùng phần tử con `include`:

~~~xml
<fileset dir="src">
    <include name="**/*.java"/>
    <include name="**/*.properties"/>
</fileset>
~~~

Nhiều pattern include được kết hợp theo phép hợp: một tệp được chọn nếu nó khớp ít nhất một pattern include và không bị loại bởi exclude.

Dùng phần tử con thường dễ đọc hơn khi có nhiều pattern hoặc cần chú thích từng nhóm.

### 3.3. Dùng exclude để loại nội dung

Exclude loại các mục khớp với pattern khỏi kết quả:

~~~xml
<fileset dir="src">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
    <exclude name="**/temporary/**"/>
</fileset>
~~~

Trong ví dụ này, FileSet lấy các tệp Java, nhưng loại những tệp nằm trong các nhánh `generated` và `temporary`.

Có thể hiểu điều kiện kết quả như sau:

1. Xác định những mục nằm dưới thư mục gốc.
2. Chọn mục khớp ít nhất một include. Nếu không khai báo include, mặc định mọi mục phù hợp với loại set đều được xem là có thể chọn.
3. Loại mục khớp bất kỳ exclude nào.
4. Áp dụng các quy tắc mặc định và tùy chọn quét khác.

Vì vậy, exclude có tác dụng loại bỏ một phần kết quả ngay cả khi mục đó đã khớp include.

### 3.4. Phân biệt pattern một cấp và nhiều cấp

Giả sử thư mục gốc là `src`:

~~~text
src/
├── Main.java
├── config/
│   └── app.properties
└── modules/
    └── billing/
        └── Billing.java
~~~

Với FileSet:

~~~xml
<fileset dir="src">
    <include name="*.java"/>
</fileset>
~~~

Chỉ `Main.java` ở ngay trong thư mục gốc khớp pattern.

Nếu dùng:

~~~xml
<fileset dir="src">
    <include name="**/*.java"/>
</fileset>
~~~

thì cả `Main.java` và `modules/billing/Billing.java` được chọn.

Đây là khác biệt quan trọng khi buildfile cần quét đệ quy. Nếu vô tình dùng pattern chỉ có một cấp, các tệp nằm sâu trong module có thể bị bỏ sót.

## 4. Các cách khai báo pattern

### 4.1. Thuộc tính includes và excludes

Có thể viết nhiều pattern trực tiếp trong thuộc tính:

~~~xml
<fileset
    dir="src"
    includes="**/*.java,**/*.properties"
    excludes="**/generated/**,**/legacy/**"/>
~~~

Các pattern có thể được phân cách bằng dấu phẩy hoặc khoảng trắng. Khi pattern phức tạp, dùng phần tử con sẽ dễ quan sát hơn.

### 4.2. Phần tử include và exclude

~~~xml
<fileset dir="resources">
    <include name="**/*.xml"/>
    <include name="**/*.properties"/>
    <exclude name="**/examples/**"/>
</fileset>
~~~

Cách này giúp mỗi điều kiện nằm trên một dòng riêng. Nó cũng thuận tiện khi cần thêm ghi chú để người bảo trì hiểu tại sao một nhóm tệp được chọn hoặc loại.

### 4.3. Đọc pattern từ tệp

Nếu danh sách pattern dài hoặc được dùng chung trong quy trình build, có thể lưu chúng trong một tệp văn bản rồi tham chiếu bằng `includesfile` hoặc `excludesfile`.

~~~xml
<fileset dir="src">
    <includesfile name="config/source-includes.txt"/>
    <excludesfile name="config/source-excludes.txt"/>
</fileset>
~~~

Mỗi dòng trong tệp danh sách chứa một pattern. Cách này giúp thay đổi quy tắc quét mà không cần sửa nhiều vị trí trong buildfile.

Các tệp danh sách cũng cần được giải quyết theo vị trí mà Ant sử dụng cho thuộc tính `name`; hãy tổ chức chúng trong project một cách rõ ràng để tránh phụ thuộc vào thư mục terminal.

### 4.4. Tái sử dụng PatternSet

Có thể khai báo một `patternset` để dùng lại các quy tắc chọn:

~~~xml
<patternset id="production.sources">
    <include name="**/*.java"/>
    <exclude name="**/test/**"/>
    <exclude name="**/generated/**"/>
</patternset>

<fileset id="production.files" dir="src">
    <patternset refid="production.sources"/>
</fileset>

<fileset id="test.files" dir="src">
    <include name="**/test/**/*.java"/>
</fileset>
~~~

PatternSet tách quy tắc chọn khỏi thư mục gốc. Nhờ đó, cùng một bộ include/exclude có thể được áp dụng cho các FileSet hoặc DirSet khác nhau khi cần.

Thư mục gốc vẫn do thuộc tính `dir` của từng set quyết định. Việc tái sử dụng PatternSet không làm thay đổi gốc quét.

## 5. Các tùy chọn quét thường gặp

FileSet và DirSet có các tùy chọn điều khiển cách DirectoryScanner xử lý cây thư mục.

| Thuộc tính | Tác dụng | Giá trị thường dùng |
|---|---|---|
| `dir` | Thư mục gốc để quét | Đường dẫn tương đối hoặc tuyệt đối |
| `includes` | Các pattern được chọn | Mặc định không giới hạn bằng include |
| `excludes` | Các pattern bị loại | Không có exclude do người dùng khai báo |
| `defaultexcludes` | Có áp dụng danh sách loại trừ mặc định của Ant không | `true` |
| `casesensitive` | Có phân biệt chữ hoa/chữ thường khi khớp pattern không | `true` |
| `followsymlinks` | Có đi theo symbolic link khi quét không | `true` |
| `erroronmissingdir` | Có báo lỗi nếu thư mục gốc không tồn tại không | `true` |

### 5.1. Default excludes

Ant áp dụng một danh sách pattern loại trừ mặc định để bỏ qua một số tệp và thư mục phụ trợ của hệ thống quản lý phiên bản hoặc công cụ khác. Danh sách cụ thể có thể thay đổi theo phiên bản Ant.

Mặc định `defaultexcludes="true"` giúp tránh vô tình đưa các thư mục metadata như `.git` hoặc `.svn` vào tập tài nguyên.

Có thể tắt bằng:

~~~xml
<fileset dir="." defaultexcludes="false">
    <include name="**/*"/>
</fileset>
~~~

Chỉ tắt tùy chọn này khi thật sự cần lấy cả những mục thường bị loại trừ. Nếu không, build có thể vô tình sao chép hoặc đóng gói dữ liệu phụ trợ không mong muốn.

### 5.2. Phân biệt chữ hoa và chữ thường

Mặc định pattern được so khớp có phân biệt chữ hoa/chữ thường. Ví dụ:

~~~xml
<fileset dir="src" casesensitive="true">
    <include name="**/*.java"/>
</fileset>
~~~

Pattern `*.java` không đồng nghĩa với `*.JAVA` khi so khớp phân biệt chữ hoa/chữ thường.

Nếu muốn việc so khớp không phân biệt chữ hoa/chữ thường:

~~~xml
<fileset dir="src" casesensitive="false">
    <include name="**/*.java"/>
</fileset>
~~~

Hãy cân nhắc tính nhất quán giữa các hệ điều hành. Một build có thể chạy trên hệ thống tệp không phân biệt chữ hoa/chữ thường nhưng thất bại trên hệ thống phân biệt chữ hoa/chữ thường nếu pattern dựa vào cách viết tên không nhất quán.

### 5.3. Symbolic link

Tùy chọn `followsymlinks` điều khiển việc scanner có đi theo symbolic link hay không.

~~~xml
<fileset dir="workspace" followsymlinks="false">
    <include name="**/*.java"/>
</fileset>
~~~

Khi không đi theo symbolic link, scanner tránh duyệt vào các đích liên kết theo quy tắc của Ant. Điều này hữu ích khi cây thư mục có liên kết đến vùng dữ liệu ngoài project hoặc có cấu trúc liên kết vòng.

Nếu build cần lấy nội dung thông qua symbolic link, hãy kiểm tra cấu hình và hành vi trên hệ điều hành thực tế.

### 5.4. Thư mục gốc không tồn tại

Mặc định, nếu thư mục được chỉ định trong `dir` không tồn tại, Ant báo lỗi khi quét. Đây thường là hành vi hữu ích vì nó phát hiện sớm lỗi cấu hình hoặc lỗi chuẩn bị workspace.

Nếu trường hợp thư mục chưa tồn tại được xem là bình thường và muốn set rỗng thay vì lỗi, có thể dùng `erroronmissingdir="false"`:

~~~xml
<fileset dir="optional-resources" erroronmissingdir="false">
    <include name="**/*"/>
</fileset>
~~~

Tùy chọn này không tạo thư mục. Nếu một bước sau cần thư mục đó, phải tạo nó bằng task phù hợp như `mkdir`.

## 6. FileSet trong các task Ant

FileSet thường được đặt lồng trong task nhận một tập hợp tệp. Một số trường hợp phổ biến là copy, delete, jar và các task biên dịch hoặc đóng gói có hỗ trợ resource collection.

### 6.1. Sao chép các tệp được chọn

~~~xml
<project name="copy-selected-files" default="copy" basedir=".">
    <property name="source.root" location="src"/>
    <property name="destination.dir" location="build/resources"/>

    <target name="copy">
        <copy todir="${destination.dir}">
            <fileset dir="${source.root}">
                <include name="**/*.properties"/>
                <include name="**/*.xml"/>
                <exclude name="**/examples/**"/>
            </fileset>
        </copy>
    </target>
</project>
~~~

FileSet chọn các tệp từ `source.root`. Task copy nhận tập hợp đó và sao chép vào `destination.dir`.

Theo mặc định, copy giữ cấu trúc đường dẫn tương đối của các tệp bên trong FileSet. Vì vậy, tệp `config/app.properties` bên dưới thư mục gốc sẽ tiếp tục nằm trong nhánh `config` tại đích, thay vì bị dồn tất cả vào cùng một thư mục.

Nếu muốn làm phẳng cấu trúc, task copy có tùy chọn riêng như `flatten`. Đó là quyết định của task sử dụng set, không phải thay đổi thư mục gốc của FileSet.

### 6.2. Xóa một nhóm tệp

~~~xml
<target name="clean-generated-files">
    <delete>
        <fileset dir="build">
            <include name="**/*.tmp"/>
            <include name="**/*.bak"/>
        </fileset>
    </delete>
</target>
~~~

FileSet giới hạn phạm vi các tệp mà task delete nhận được. Dùng thư mục gốc cụ thể và pattern rõ ràng giúp tránh chọn nhầm tài nguyên ngoài vùng cần dọn dẹp.

Không dùng pattern quá rộng trong task xóa nếu chưa xác định chính xác thư mục gốc và các mục sẽ được chọn.

### 6.3. Đóng gói tài nguyên

~~~xml
<target name="package-resources">
    <jar destfile="build/app.jar">
        <fileset dir="resources">
            <include name="**/*"/>
            <exclude name="**/*.psd"/>
            <exclude name="**/draft/**"/>
        </fileset>
    </jar>
</target>
~~~

Jar nhận các tệp phù hợp và đưa chúng vào archive. Các đường dẫn tương đối trong FileSet trở thành cấu trúc bên trong archive.

Nếu tài nguyên cần được đặt dưới một thư mục con trong archive, có thể dùng `zipfileset`, một kiểu set mở rộng cho archive có thuộc tính `prefix`:

~~~xml
<jar destfile="build/app.jar">
    <zipfileset dir="resources" prefix="app">
        <include name="**/*.xml"/>
    </zipfileset>
</jar>
~~~

Ở đây, `dir` vẫn là gốc quét trên hệ thống tệp, còn `prefix` quy định thư mục đích bên trong archive. Hai khái niệm này độc lập với nhau.

## 7. DirSet trong path và các tác vụ dùng thư mục

DirSet hữu ích khi task cần các thư mục như những phần tử độc lập. Một tình huống điển hình là xây dựng classpath từ nhiều thư mục lớp đã biên dịch.

~~~xml
<project name="dirset-classpath" default="show" basedir=".">
    <property name="module.build.root" location="modules"/>

    <path id="module.classpath">
        <dirset dir="${module.build.root}">
            <include name="*/classes"/>
        </dirset>
    </path>

    <target name="show">
        <property name="module.classpath.text" refid="module.classpath"/>
        <echo message="Module classpath: ${module.classpath.text}"/>
    </target>
</project>
~~~

DirSet chọn các thư mục `classes` nằm dưới các thư mục module cấp một. Path gom các vị trí đó thành một cấu trúc đường dẫn mà task khác có thể tham chiếu bằng `refid`.

Ví dụ, nếu cây thư mục là:

~~~text
modules/
├── billing/
│   └── classes/
├── catalog/
│   └── classes/
└── reporting/
    └── source/
~~~

pattern `*/classes` chọn:

~~~text
billing/classes
catalog/classes
~~~

Nó không chọn `reporting/source`, vì thư mục đó không khớp pattern. Cũng không chọn các tệp nằm trong hai thư mục classes; DirSet chỉ đưa chính các thư mục phù hợp vào kết quả.

Không phải task nào cũng nhận DirSet. Trước khi đặt một set lồng trong task, hãy xem task có hỗ trợ DirSet hoặc resource collection tương ứng hay không. Path là một nơi thường dùng để kết hợp các loại phần tử đường dẫn.

## 8. Dùng chung một thư mục gốc cho nhiều set

Một project có thể định nghĩa thư mục gốc một lần rồi tạo nhiều FileSet và DirSet từ đó:

~~~xml
<project name="shared-scan-root" default="show" basedir=".">
    <property name="workspace.root" location="workspace"/>

    <fileset id="java.files" dir="${workspace.root}">
        <include name="**/*.java"/>
        <exclude name="**/generated/**"/>
    </fileset>

    <fileset id="config.files" dir="${workspace.root}">
        <include name="**/*.properties"/>
        <include name="**/*.xml"/>
    </fileset>

    <dirset id="module.dirs" dir="${workspace.root}">
        <include name="*"/>
    </dirset>

    <path id="java.path">
        <fileset refid="java.files"/>
    </path>
    <path id="config.path">
        <fileset refid="config.files"/>
    </path>
    <path id="module.path">
        <dirset refid="module.dirs"/>
    </path>

    <target name="show">
        <pathconvert property="java.list" refid="java.path"/>
        <pathconvert property="config.list" refid="config.path"/>
        <pathconvert property="module.list" refid="module.path"/>

        <echo message="Java files: ${java.list}"/>
        <echo message="Config files: ${config.list}"/>
        <echo message="Module directories: ${module.list}"/>
    </target>
</project>
~~~

Ba set cùng quét từ `workspace.root`, nhưng mỗi set có mục đích và pattern riêng. Khi thay đổi thư mục gốc, chỉ cần cập nhật property dùng chung.

Trong ví dụ, pattern của DirSet được viết theo đường dẫn tương đối từ `workspace.root`. Nếu muốn chọn thư mục module ở nhiều cấp, có thể dùng pattern như `**/classes` hoặc một mẫu phù hợp với cấu trúc thực tế.

## 9. Chẩn đoán khi kết quả quét không như mong đợi

Khi FileSet hoặc DirSet trả về rỗng hoặc thừa mục, hãy kiểm tra theo thứ tự sau.

### 9.1. Kiểm tra thư mục gốc

In đường dẫn property đang được dùng làm `dir`:

~~~xml
<echo message="Scan root: ${source.root}"/>
~~~

Đảm bảo thư mục đó đúng vị trí và tồn tại. Nếu cần, dùng đường dẫn tuyệt đối để đối chiếu với cấu trúc workspace.

Một lỗi phổ biến là nghĩ pattern được tính từ project basedir trong khi thực tế nó được tính từ thư mục gốc của set. Ví dụ, với `dir="src"`, pattern `**/*.java` là đủ; không cần thêm `src/` vào pattern.

### 9.2. Kiểm tra pattern có đúng cấp không

Nếu chỉ nhận được tệp ở thư mục gốc mà bỏ sót thư mục con, xem lại việc dùng `*` thay vì `**`.

~~~xml
<!-- Chỉ khớp tệp Java ở ngay trong src -->
<fileset dir="src">
    <include name="*.java"/>
</fileset>

<!-- Khớp tệp Java ở mọi cấp dưới src -->
<fileset dir="src">
    <include name="**/*.java"/>
</fileset>
~~~

### 9.3. Kiểm tra exclude và default excludes

Một mục có thể khớp include nhưng vẫn bị loại bởi exclude hoặc danh sách default excludes. Tạm thời bỏ các điều kiện loại trừ trong môi trường thử nghiệm để xác định nguyên nhân, rồi khôi phục cấu hình đúng.

Nếu cần quét cả metadata của công cụ quản lý phiên bản, kiểm tra `defaultexcludes`. Chỉ tắt nó khi biết rõ tác động.

### 9.4. Phân biệt kết quả FileSet và DirSet

Nếu đang mong đợi danh sách tệp nhưng dùng DirSet, kết quả sẽ chỉ chứa thư mục. Ngược lại, FileSet không trả về các thư mục như phần tử kết quả.

Hãy chọn kiểu dữ liệu dựa vào thứ mà task cần nhận:

- Tệp cần copy, đóng gói hoặc xử lý: FileSet.
- Thư mục cần đưa vào một path hoặc xử lý như các vị trí riêng: DirSet.
- Danh sách đường dẫn được chỉ định rõ ràng, không cần quét theo pattern: cân nhắc FileList hoặc các phần tử path phù hợp.

### 9.5. In danh sách để kiểm tra

Task `pathconvert` chuyển một Path thành chuỗi dễ đọc trong log. Vì FileSet và DirSet là các resource collection, hãy đặt set vào trong một Path rồi tham chiếu Path đó:

~~~xml
<fileset id="selected.files.id" dir="src">
    <include name="**/*.java"/>
</fileset>

<path id="selected.path">
    <fileset refid="selected.files.id"/>
</path>

<target name="inspect">
    <pathconvert property="selected.files" refid="selected.path"/>
    <echo message="Selected: ${selected.files}"/>
</target>
~~~

Danh sách in ra giúp xác nhận thư mục gốc và pattern đang tạo ra những mục nào trước khi dùng set trong bước copy, compile hoặc package.

## 10. Bảng chọn nhanh

| Nhu cầu | Cách làm |
|---|---|
| Quét tệp Java trong một cây thư mục | FileSet với `dir` và `**/*.java` |
| Chọn các thư mục lớp đã biên dịch | DirSet với pattern như `**/classes` |
| Quét thư mục con của project | Đặt `dir` tương đối với project basedir |
| Quét một vị trí ngoài project | Dùng đường dẫn tương đối có `..` hoặc property tuyệt đối |
| Loại thư mục sinh tự động | Thêm exclude như `**/generated/**` |
| Dùng chung quy tắc include/exclude | Khai báo PatternSet và tham chiếu bằng `refid` |
| Quét mọi cấp thư mục | Dùng `**` trong pattern |
| Chỉ quét cấp gốc | Dùng pattern không có `**/` ở đầu |
| Muốn tập kết quả là tệp | FileSet |
| Muốn tập kết quả là thư mục | DirSet |

## 11. Tự kiểm tra cấu hình quét

Trước khi sử dụng FileSet hoặc DirSet trong target, hãy trả lời các câu hỏi sau:

1. Thư mục gốc của set là gì? Giá trị của `dir` có được giải quyết đúng theo project basedir không?
2. Pattern được viết tương đối với thư mục gốc hay đang vô tình lặp lại tên thư mục gốc?
3. Cần chọn tệp hay chọn thư mục? Set đang dùng có đúng loại kết quả không?
4. Pattern có dùng `*`, `?` và `**` đúng cấp thư mục không?
5. Có exclude nào loại nhầm mục cần dùng không?
6. Default excludes có ảnh hưởng đến kết quả không?
7. Thư mục gốc có tồn tại và có đúng cấu trúc dự kiến không?
8. Task nhận set có hỗ trợ loại resource collection đang truyền vào không?
9. Đường dẫn tương đối của kết quả có cần được giữ nguyên khi copy hoặc đóng gói không?

Khi nắm rõ mối quan hệ giữa project basedir, thuộc tính `dir` và pattern tương đối, việc quét tệp trong Ant sẽ dễ dự đoán hơn. Hãy coi `dir` là điểm bắt đầu của mỗi lần quét, viết pattern từ điểm đó, rồi chọn FileSet hoặc DirSet theo loại mục mà task cần xử lý.
