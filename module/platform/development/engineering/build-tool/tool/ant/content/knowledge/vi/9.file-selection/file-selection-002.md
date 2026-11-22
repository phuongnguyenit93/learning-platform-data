# Mẫu Ant với dấu `*`, dấu `?` và dấu `**`

Trong Apache Ant, các task làm việc với tập tệp thường dùng **pattern** để chọn file theo tên và đường dẫn. Ba ký tự đại diện thường gặp là `*`, `?` và `**`. Chúng giúp build chọn mã nguồn, tài nguyên, file cấu hình, test hoặc đầu ra cần xử lý mà không phải liệt kê từng đường dẫn.

Các pattern của Ant có cú pháp riêng, gần với glob của hệ thống file. Chúng không phải biểu thức chính quy (regular expression). Điểm quan trọng nhất là phân biệt wildcard trong một thành phần đường dẫn với wildcard có thể đi qua nhiều cấp thư mục:

- `*` khớp với không hoặc nhiều ký tự trong một thành phần đường dẫn.
- `?` khớp với đúng một ký tự trong một thành phần đường dẫn.
- `**` khớp với không hoặc nhiều cấp thư mục.

Ví dụ, `src/*.java` chọn các file Java nằm trực tiếp trong `src`; `src/**/*.java` chọn file Java ở các cấp bên dưới `src`, bao gồm cả file ngay trong `src` vì `**/` có thể khớp với không cấp thư mục nào.

## 1. Pattern được dùng ở đâu trong Ant?

Pattern xuất hiện trong nhiều task và data type có chức năng chọn tệp. Phổ biến nhất là `FileSet`, thường được dùng bên trong `<copy>`, `<delete>`, `<jar>`, `<zip>`, `<javac>` hoặc các task khác nhận tập file.

Ví dụ:

~~~xml
<fileset dir="src/main/java">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
</fileset>
~~~

`dir` là thư mục gốc để Ant quét. Các pattern trong `include` và `exclude` được so khớp với đường dẫn tương đối của từng file bên dưới thư mục đó.

Có thể dùng thuộc tính `includes` và `excludes` ngay trên FileSet:

~~~xml
<fileset dir="src/main/resources"
         includes="**/*.yml,**/*.properties"
         excludes="**/local/**,**/*.secret.yml"/>
~~~

Hoặc dùng các phần tử lồng nhau:

~~~xml
<fileset dir="src/main/resources">
    <include name="**/*.yml"/>
    <include name="**/*.properties"/>
    <exclude name="**/local/**"/>
    <exclude name="**/*.secret.yml"/>
</fileset>
~~~

Các include được kết hợp theo kiểu OR: file khớp với ít nhất một include thì đủ điều kiện được chọn. Các exclude cũng được kết hợp theo kiểu OR: chỉ cần khớp một exclude là file bị loại. Nếu một FileSet không khai báo include, Ant mặc định xem tất cả file trong base directory là ứng viên, sau đó áp dụng exclude và default excludes.

## 2. Dấu `*`: khớp không hoặc nhiều ký tự trong một thành phần đường dẫn

Dấu `*` đại diện cho không hoặc nhiều ký tự trong một path segment. Nó không tự đi xuyên qua dấu phân cách thư mục `/`.

Ví dụ với thư mục:

~~~text
src/
├── App.java
├── AppTest.java
├── UserService.java
└── service/
    ├── UserService.java
    └── OrderService.java
~~~

Pattern:

~~~text
src/*.java
~~~

chỉ chọn các file Java nằm trực tiếp trong `src`, chẳng hạn `App.java`, `AppTest.java` và `UserService.java`. Nó không chọn `src/service/UserService.java`, vì dấu `*` không vượt qua dấu `/` để đi vào thư mục con.

Một số pattern thường dùng:

| Pattern | Ý nghĩa |
|---|---|
| `*.java` | File có phần mở rộng `.java` ngay dưới thư mục gốc của FileSet |
| `App*.java` | File Java có tên bắt đầu bằng `App` trong thư mục gốc |
| `*Test.java` | File Java kết thúc bằng `Test.java` trong thư mục gốc |
| `config/*.yml` | File YAML nằm trực tiếp trong thư mục `config` |
| `**/*Test.java` | File Java có tên kết thúc bằng `Test.java` ở mọi cấp thư mục |

Ví dụ chọn các file cấu hình trực tiếp trong một thư mục:

~~~xml
<fileset dir="config">
    <include name="*.yml"/>
    <include name="*.properties"/>
</fileset>
~~~

Nếu file cấu hình nằm trong thư mục con như `config/database/dev.yml`, pattern `*.yml` không chọn được file đó. Cần dùng `**/*.yml` khi muốn quét nhiều cấp.

## 3. Dấu `?`: khớp đúng một ký tự

Dấu `?` đại diện cho đúng một ký tự trong một thành phần đường dẫn. Nó hữu ích khi tên file có một vị trí thay đổi nhưng số ký tự ở vị trí đó đã biết.

Ví dụ:

~~~text
reports/
├── test1.xml
├── test2.xml
├── test10.xml
├── testA.xml
└── tests.xml
~~~

Pattern:

~~~text
test?.xml
~~~

chọn `test1.xml`, `test2.xml`, `testA.xml` và `tests.xml`. Nó không chọn `test10.xml` vì sau `test` có hai ký tự trước `.xml`; dấu `?` chỉ khớp đúng một ký tự.

Một số ví dụ:

| Pattern | Tên khớp | Tên không khớp |
|---|---|---|
| `file?.txt` | `file1.txt`, `fileA.txt` | `file10.txt`, `file.txt` |
| `app-?.jar` | `app-1.jar`, `app-a.jar` | `app-12.jar` |
| `Test?.java` | `Test1.java`, `TestA.java` | `Test10.java` |
| `config-??.yml` | `config-vi.yml`, `config-en.yml` | `config-v.yml`, `config-vie.yml` |

`?` không có nghĩa là một ký tự tùy chọn. Nó yêu cầu phải có đúng một ký tự ở vị trí đó. Nếu muốn khớp không hoặc nhiều ký tự, hãy dùng `*`.

## 4. Dấu `**`: khớp không hoặc nhiều cấp thư mục

Dấu `**` là wildcard đặc biệt cho đường dẫn: nó có thể khớp với không hoặc nhiều thư mục. Thông thường, nó được đặt thành một path segment riêng, thường đi kèm dấu `/` ở hai bên.

Ví dụ:

~~~text
src/
├── App.java
├── service/
│   ├── UserService.java
│   └── internal/
│       └── Cache.java
└── web/
    └── controller/
        └── UserController.java
~~~

Pattern:

~~~text
**/*.java
~~~

chọn tất cả file `.java` bên dưới thư mục gốc, gồm `App.java`, `service/UserService.java`, `service/internal/Cache.java` và `web/controller/UserController.java`.

Pattern:

~~~text
service/**/*.java
~~~

chọn các file Java trong `service` và các cấp thư mục con của nó. Vì `**/` có thể khớp với không cấp thư mục nào, pattern này cũng chọn `service/UserService.java`, ngoài các file sâu hơn như `service/internal/Cache.java`.

Một số pattern thường gặp:

| Pattern | Ý nghĩa |
|---|---|
| `**/*.java` | Mọi file Java ở tất cả cấp thư mục |
| `src/**/*.xml` | File XML ở mọi cấp dưới `src` |
| `**/test/**` | Nội dung nằm trong thư mục có tên `test` ở bất kỳ cấp nào |
| `**/*Test.java` | File Java có tên kết thúc bằng `Test.java` ở mọi cấp |
| `com/example/**` | Nội dung nằm dưới cây thư mục `com/example` |
| `**` | Mọi đường dẫn file được quét trong base directory |

Khi chọn toàn bộ mã nguồn trong một dự án, pattern `**/*.java` thường phù hợp hơn `*.java` vì package Java thường được tổ chức thành nhiều thư mục con.

## 5. Kết hợp `*`, `?` và `**`

Ba wildcard có thể xuất hiện trong cùng một pattern. Mỗi ký tự đảm nhiệm một phạm vi khác nhau.

Ví dụ chọn các file test có tên gồm `Test`, một ký tự phiên bản và phần mở rộng `.java` trong mọi package:

~~~text
**/Test?.java
~~~

Ví dụ chọn file cấu hình có tên bắt đầu bằng `application-`, tiếp theo là một hoặc nhiều ký tự, kết thúc bằng `.yml`, ở mọi thư mục:

~~~text
**/application-*.yml
~~~

Ví dụ chọn các file có hậu tố `-dev` hoặc `-prod` trong thư mục cấu hình, với một ký tự môi trường:

~~~text
config/*-?.yml
~~~

Pattern không phải regular expression. Những cú pháp như `[0-9]`, nhóm `(...)`, phép OR `|` hay quantifier `{2,4}` không có ý nghĩa regex trong Ant file pattern. Nếu cần chọn theo điều kiện phức tạp hơn, hãy dùng selector, mapper hoặc task xử lý riêng phù hợp.

## 6. Đường dẫn được so khớp tương đối với `dir`

Trong FileSet, pattern được so sánh với đường dẫn tương đối bên dưới `dir`, không phải với đường dẫn tuyệt đối trên máy.

Ví dụ:

~~~xml
<fileset dir="project">
    <include name="src/**/*.java"/>
</fileset>
~~~

Với cấu trúc:

~~~text
project/
├── src/
│   ├── Main.java
│   └── service/
│       └── UserService.java
└── test/
    └── MainTest.java
~~~

Pattern `src/**/*.java` được so với các đường dẫn tương đối `src/Main.java` và `src/service/UserService.java`. File `test/MainTest.java` không khớp vì nó nằm ngoài nhánh `src`.

Để chọn test, có thể dùng một FileSet khác:

~~~xml
<fileset dir="project">
    <include name="test/**/*.java"/>
</fileset>
~~~

Khi viết pattern, luôn xác định base directory trước. Cùng một chuỗi pattern nhưng đặt trên hai `dir` khác nhau có thể chọn hai tập file hoàn toàn khác nhau.

Ant sử dụng dấu `/` làm dấu phân cách trong pattern để build file dễ di chuyển giữa Windows, Linux và macOS. Hãy ưu tiên viết `src/**/*.java`, kể cả khi đang chạy trên Windows; không cần thay bằng dấu `\\` trong pattern.

## 7. Include, exclude và thứ tự chọn file

Một FileSet có thể có nhiều include và exclude. Cách hiểu thông thường:

1. Ant quét file bên dưới `dir`.
2. Nếu có include pattern, file phải khớp ít nhất một include.
3. File khớp bất kỳ exclude pattern nào sẽ bị loại.
4. Default excludes được áp dụng nếu không tắt.

Ví dụ chỉ lấy source Java trong `src`, bỏ source sinh tự động và file thử nghiệm:

~~~xml
<fileset dir="src">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
    <exclude name="**/*Test.java"/>
</fileset>
~~~

Một file phải khớp `**/*.java` trước. Sau đó, file nằm trong thư mục `generated` hoặc có tên kết thúc bằng `Test.java` bị loại.

Nếu cần dùng lại một nhóm pattern ở nhiều FileSet, có thể định nghĩa `patternset`:

~~~xml
<patternset id="production.java.patterns">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
    <exclude name="**/*Test.java"/>
</patternset>

<fileset id="main.sources" dir="src/main/java">
    <patternset refid="production.java.patterns"/>
</fileset>

<fileset id="legacy.sources" dir="legacy/src">
    <patternset refid="production.java.patterns"/>
</fileset>
~~~

Cả hai FileSet dùng chung quy tắc chọn file nhưng có thư mục gốc riêng. Thay đổi pattern trong một chỗ sẽ áp dụng cho cả hai.

### 7.1. Default excludes

Ant có một nhóm default excludes để bỏ qua các tệp/thư mục thường không thuộc nội dung build, chẳng hạn metadata của hệ thống quản lý phiên bản hoặc file backup. Mặc định, FileSet áp dụng các default excludes này.

Có thể điều khiển bằng thuộc tính `defaultexcludes`:

~~~xml
<fileset dir="workspace"
         includes="**/*"
         defaultexcludes="no"/>
~~~

Chỉ tắt default excludes khi thật sự muốn đưa cả những file đó vào tập xử lý. Nếu không, giữ mặc định giúp tránh đóng gói `.git`, metadata SCM hoặc file tạm ngoài ý muốn.

### 7.2. Phân biệt hoa thường

FileSet mặc định so khớp pattern có phân biệt chữ hoa và chữ thường. Có thể đặt `casesensitive="false"` khi cần hành vi không phân biệt hoa thường:

~~~xml
<fileset dir="config" casesensitive="false">
    <include name="**/*.YML"/>
</fileset>
~~~

Nếu build chạy trên nhiều hệ điều hành, hãy chọn một quy tắc nhất quán. Hành vi của filesystem có thể khác nhau giữa các máy, nhưng thuộc tính `casesensitive` điều khiển phép so khớp pattern của Ant.

## 8. Dùng pattern trong các task thực tế

### 8.1. Chọn source để biên dịch

~~~xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includes="**/*.java"
           excludes="**/generated/**"
           includeantruntime="false">
    </javac>
</target>
~~~

Trong nhiều build, thuộc tính `srcdir` của `javac` kết hợp cơ chế tìm source riêng của task. Nếu cần pattern include/exclude phức tạp, hãy kiểm tra cấu hình `javac` đang dùng và có thể xác định source set qua nested source/path hoặc FileSet phù hợp với phiên bản Ant. Không phải task nào nhận Path cũng nhận trực tiếp FileSet; pattern phải đặt ở đúng nested element mà task hỗ trợ.

### 8.2. Copy tài nguyên theo phần mở rộng

~~~xml
<target name="copy-resources">
    <mkdir dir="build/classes"/>
    <copy todir="build/classes">
        <fileset dir="src/main/resources">
            <include name="**/*.properties"/>
            <include name="**/*.yml"/>
            <exclude name="**/local/**"/>
        </fileset>
    </copy>
</target>
~~~

Task `copy` nhận FileSet, nên pattern quyết định chính xác tài nguyên nào được sao chép. Thư mục con được giữ theo cấu trúc tương đối dưới thư mục nguồn khi copy vào destination.

### 8.3. Đóng gói JAR và loại bỏ file không mong muốn

~~~xml
<target name="package">
    <jar destfile="dist/application.jar">
        <fileset dir="build/classes">
            <include name="**/*.class"/>
            <include name="**/*.properties"/>
            <exclude name="**/*Test.class"/>
        </fileset>
    </jar>
</target>
~~~

Ở đây JAR chỉ chứa class và property resource được chọn. Các class test bị loại khỏi artifact phát hành. Trong dự án thực tế, cần bổ sung manifest, tài nguyên và thư viện theo cấu trúc đóng gói mà ứng dụng yêu cầu.

## 9. Phân biệt wildcard Ant với wildcard shell và regex

Cùng ký tự `*` có thể xuất hiện trong shell, Ant và regular expression, nhưng cách diễn giải không giống nhau.

| Ngữ cảnh | `*` | `?` | `**` |
|---|---|---|---|
| Ant file pattern | Không hoặc nhiều ký tự trong một path segment | Một ký tự trong một path segment | Không hoặc nhiều cấp thư mục |
| Shell glob phổ biến | Không hoặc nhiều ký tự trong tên/path segment | Một ký tự | Tùy shell; có thể cần bật globstar |
| Regular expression | Quantifier lặp ký tự/nhóm đứng trước | Quantifier tùy chọn cho ký tự/nhóm đứng trước | Hai quantifier `*` liên tiếp, không có ý nghĩa “mọi cấp thư mục” tự động |

Ví dụ, trong Ant `**/*.java` có nghĩa là file Java ở mọi cấp thư mục. Trong regular expression, chuỗi `**/*.java` không phải biểu thức hợp lệ theo ý nghĩa tương tự. Nếu cần dùng regex, hãy chọn task hoặc selector có hỗ trợ regex và đọc cú pháp riêng của nó.

Cũng không nên phụ thuộc vào shell để mở rộng pattern khi truyền cho Ant. Pattern trong `build.xml` thường được Ant xử lý trực tiếp. Khi truyền pattern qua command line cho một task hoặc script, hãy kiểm tra shell có tự mở rộng wildcard trước khi chương trình nhận đối số hay không.

## 10. Những lỗi thường gặp khi viết pattern

| Pattern hoặc cấu hình | Kết quả ngoài dự kiến | Cách điều chỉnh |
|---|---|---|
| `*.java` | Không lấy source trong package con | Dùng `**/*.java` |
| `src/*.java` | Không lấy file trong `src/service/` | Dùng `src/**/*.java` |
| `Test?.java` | Không khớp `Test10.java` | Dùng `Test*.java` nếu số ký tự có thể dài tùy ý |
| `file?.xml` | Không khớp `file.xml` hoặc `file12.xml` | Dùng `file*.xml` nếu muốn 0 hoặc nhiều ký tự |
| `**/generated/**` | Không loại thư mục có tên gần giống nhưng không đúng segment `generated` | Kiểm tra đường dẫn tương đối và vị trí segment |
| Pattern dùng `\\` | Khó di chuyển giữa hệ điều hành hoặc không khớp như mong muốn | Dùng `/` trong Ant pattern |
| Include đúng nhưng vẫn thiếu file | File bị exclude hoặc default excludes loại bỏ | Kiểm tra toàn bộ include/exclude và `defaultexcludes` |
| Pattern khớp trên máy này nhưng không trên máy khác | Khác biệt chữ hoa/thường | Dùng quy tắc tên file thống nhất hoặc đặt `casesensitive` rõ ràng |
| Dùng cú pháp `[0-9]` như regex | Ant không hiểu character class theo nghĩa regex | Dùng `?`/`*` hoặc selector/task hỗ trợ regex |

## 11. Cách kiểm tra tập file được chọn

Khi pattern phức tạp, hãy kiểm tra kết quả FileSet trước khi dùng nó để xóa, copy hoặc đóng gói. Có thể dùng `<pathconvert>` và `<path>` để in các đường dẫn được chọn:

~~~xml
<path id="selected.sources">
    <fileset dir="src">
        <include name="**/*.java"/>
        <exclude name="**/generated/**"/>
    </fileset>
</path>

<pathconvert property="selected.sources.list"
             refid="selected.sources"
             pathsep="&#10;"/>

<target name="show-selected-sources">
    <echo message="Selected files:${line.separator}${selected.sources.list}"/>
</target>
~~~

`pathconvert` chuyển tập đường dẫn thành property dạng chuỗi để log. Với tập file lớn, log có thể dài; có thể dùng task `copy` tới thư mục tạm hoặc task kiểm tra phù hợp để xác nhận tập file. Trước khi áp dụng pattern vào `<delete>` hoặc thao tác phát hành, nên xác nhận base directory và danh sách file được chọn.

Một quy trình debug hiệu quả:

1. In `dir` của FileSet hoặc property đường dẫn được dùng làm base.
2. Bắt đầu bằng một include đơn giản như `**/*` để xác nhận Ant quét đúng thư mục.
3. Thêm từng pattern include rồi kiểm tra kết quả.
4. Thêm exclude sau khi include đã chọn đúng tập file.
5. Kiểm tra default excludes và `casesensitive`.
6. Chỉ sau khi tập file đúng mới dùng nó trong copy, delete, jar hoặc zip.

## Kết luận

Trong Ant file pattern, `*` khớp không hoặc nhiều ký tự trong một path segment, `?` khớp đúng một ký tự, còn `**` khớp không hoặc nhiều cấp thư mục. Pattern được so khớp với đường dẫn tương đối bên dưới `dir` của FileSet; include chọn các file phù hợp, exclude loại file không mong muốn và default excludes có thể tiếp tục bỏ qua metadata thông dụng. Dùng `**/*.java` khi cần quét source ở mọi package, `*` và `?` cho các phần tên file trong một thư mục, và luôn kiểm tra tập file thực tế trước khi dùng pattern cho thao tác có ảnh hưởng như copy, delete hoặc đóng gói.
