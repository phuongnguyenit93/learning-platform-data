# Phân biệt phụ thuộc target với phụ thuộc giữa tệp nguồn và đầu ra

Trong Apache Ant, từ “phụ thuộc” có thể nói đến hai quan hệ khác nhau. Quan hệ thứ nhất là phụ thuộc giữa các target: target nào phải chạy trước target nào. Quan hệ thứ hai là phụ thuộc giữa các tệp: tệp đầu ra được tạo từ những tệp đầu vào nào, và khi nào đầu ra cần được tạo lại.

Hai quan hệ này thường xuất hiện cùng nhau trong một build, nhưng chúng không thay thế nhau. Thuộc tính `depends` của `<target>` điều khiển thứ tự thực hiện target. Nó không tự kiểm tra tệp nguồn có mới hơn tệp đầu ra hay không. Ngược lại, kiểm tra thời gian sửa đổi của tệp giúp quyết định có cần sinh lại đầu ra, nhưng không tự bảo đảm target tạo đầu ra đã chạy trước target sử dụng đầu ra đó.

Để thiết kế build chính xác, cần mô hình hóa cả luồng công việc ở cấp target và tính mới/cũ của dữ liệu ở cấp tệp.

## 1. Phụ thuộc giữa target là gì?

Một target đại diện cho một bước công việc trong build, chẳng hạn `init`, `compile`, `test`, `package` hoặc `release`. Thuộc tính `depends` khai báo những target phải được thực hiện trước target hiện tại.

~~~xml
<project name="sample-app" default="package">

    <target name="init">
        <mkdir dir="build/classes"/>
    </target>

    <target name="compile" depends="init">
        <echo message="Compile source code"/>
    </target>

    <target name="test" depends="compile">
        <echo message="Run tests"/>
    </target>

    <target name="package" depends="test">
        <echo message="Create application JAR"/>
    </target>

</project>
~~~

Quan hệ target được mô tả như sau:

~~~text
init -> compile -> test -> package
~~~

Khi chạy `ant package`, Ant thực hiện `init`, `compile`, `test` rồi `package`. Khi chạy `ant compile`, chỉ `init` và `compile` nằm trong luồng được yêu cầu.

Một số đặc điểm của `depends`:

- Giá trị là tên các target, phân tách bằng dấu phẩy.
- Ant thực hiện dependency trước target phụ thuộc.
- Dependency có thể có dependency riêng; Ant lần theo toàn bộ graph.
- Một target chỉ được thực hiện một lần trong cùng một lượt chạy project, dù nhiều nhánh cùng phụ thuộc vào nó.
- Target dependency biểu diễn thứ tự công việc, không biểu diễn điều kiện tệp đã mới hay chưa.

Ví dụ, `package depends="test"` có nghĩa target `test` phải được xử lý trước `package`. Nó không có nghĩa Ant sẽ so sánh JAR với mã nguồn để quyết định có bỏ qua `package` hay không.

## 2. Target dependency không tự kiểm tra thời gian sửa đổi của tệp

Xét build file sau:

~~~xml
<project name="sample-app" default="compile">

    <target name="compile">
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile">
        <jar destfile="dist/app.jar"
             basedir="build/classes"/>
    </target>

</project>
~~~

Khi gọi `ant package`, Ant luôn đi qua target `compile` trước `package` trong lượt chạy đó. Quan hệ `depends` không tự hỏi:

- Mã nguồn có thay đổi kể từ lần compile trước không?
- Tệp `.class` đã tồn tại chưa?
- JAR hiện tại có cũ hơn các class hay không?
- Một thư viện trên classpath có vừa thay đổi không?

Việc quyết định có thực sự biên dịch lại mã nguồn hay không thuộc hành vi của task `javac` và compiler adapter. Việc quyết định có cần sinh lại một tệp đầu ra tùy chỉnh thuộc các task kiểm tra tệp như `uptodate`, `dependset` hoặc logic tương ứng trong build.

Do đó, cần phân biệt **target được thực hiện** với **task bên trong target có tạo lại dữ liệu hay không**. Target `compile` có thể được Ant xử lý, nhưng task `javac` bên trong không cần biên dịch tệp nào nếu các class tương ứng đã mới hơn source theo cơ chế incremental của task.

## 3. Phụ thuộc giữa tệp nguồn và đầu ra là gì?

Một quan hệ file dependency mô tả rằng đầu ra được tạo từ một hoặc nhiều đầu vào.

Ví dụ:

~~~text
src/main/java/App.java
          |
          | javac
          v
build/classes/App.class
~~~

Hoặc với một bước sinh mã:

~~~text
schema/customer.xsd
          |
          | schema generator
          v
build/generated/Customer.java
          |
          | javac
          v
build/classes/Customer.class
~~~

Trong quan hệ này, `Customer.java` phụ thuộc vào `customer.xsd`: khi schema thay đổi, mã Java sinh ra có thể cần được tạo lại. `Customer.class` lại phụ thuộc vào `Customer.java`: khi mã Java thay đổi, class tương ứng cần được biên dịch lại.

Đầu ra thường được coi là up-to-date nếu nó tồn tại và không cũ hơn các đầu vào liên quan. Ant có thể sử dụng thời gian sửa đổi (last modified time) để thực hiện phép so sánh này. Đây là một quy tắc freshness dựa trên metadata tệp, khác với quan hệ thứ tự target.

## 4. Task `javac` và biên dịch tăng dần

Task `<javac>` của Ant có cơ chế lựa chọn các tệp nguồn cần biên dịch. Trong cách dùng thông thường với `srcdir` và `destdir`, Ant kiểm tra đầu ra class tương ứng và thời gian sửa đổi để tránh biên dịch lại các source không thay đổi.

~~~xml
<property name="src.dir" location="src/main/java"/>
<property name="classes.dir" location="build/classes"/>

<target name="compile">
    <mkdir dir="${classes.dir}"/>
    <javac srcdir="${src.dir}"
           destdir="${classes.dir}"
           includeantruntime="false"
           encoding="UTF-8"/>
</target>
~~~

Ví dụ, giả sử:

| Tệp | Thời gian sửa đổi |
|---|---|
| `src/main/java/App.java` | 10:00 |
| `build/classes/App.class` | 10:05 |

Nếu không có thay đổi cấu hình hoặc compiler nào buộc phải biên dịch lại, class mới hơn source nên Ant thường không cần biên dịch lại `App.java`.

Nếu `App.java` được sửa lúc 10:10, source mới hơn class. Trong lần chạy tiếp theo, task `javac` nhận diện source đã cũ đầu ra và biên dịch lại.

Nếu `App.class` chưa tồn tại, source cần được biên dịch để tạo đầu ra. Vì vậy, build sạch sau `clean` sẽ buộc compiler tạo lại các class.

### 4.1. Incremental compile không phải dependency graph tổng quát

Cơ chế incremental của `javac` trong Ant giúp tránh công việc không cần thiết đối với các source và class tương ứng. Không nên coi nó là một hệ thống theo dõi mọi loại đầu vào của ứng dụng.

Ví dụ, một source có thể phụ thuộc vào:

- Một JAR trên compile classpath.
- Một file cấu hình được đọc trong quá trình sinh mã.
- Một schema hoặc file định nghĩa API.
- Phiên bản compiler hoặc tùy chọn biên dịch.
- Một source khác hoặc một generated source.

Nếu một JAR trên classpath thay đổi nhưng các tệp `.java` vẫn cũ hơn `.class`, việc lựa chọn source theo timestamp đơn giản có thể không đủ để buộc mọi lớp phụ thuộc được biên dịch lại. Tương tự, thay đổi tùy chọn compiler hoặc phiên bản JDK không nhất thiết làm timestamp của source thay đổi.

Khi thay đổi đầu vào không được task theo dõi, cần thiết kế thêm cơ chế invalidation phù hợp: xóa output cũ, đánh dấu build cần chạy lại, so sánh fingerprint cấu hình hoặc dùng một task quản lý dependency chuyên biệt. Đối với một thay đổi lớn về JDK hay classpath, `clean` rồi build lại thường là cách xác minh rõ ràng.

### 4.2. Xóa source không đồng nghĩa tự xóa class cũ

Giả sử `OldService.java` bị xóa khỏi source tree. Tệp `OldService.class` có thể vẫn còn trong `build/classes` từ lần build trước. Không có source mới hơn để kích hoạt việc biên dịch lại, và compiler không thể suy ra rằng class cũ phải bị xóa chỉ từ việc source không còn xuất hiện.

Vì vậy, target `clean` cần xóa đầu ra build được sinh ra:

~~~xml
<target name="clean">
    <delete dir="build"/>
    <delete dir="dist"/>
</target>
~~~

Sau đó, build sạch tạo lại output từ đúng tập source hiện có. Phạm vi xóa phải là thư mục do build sở hữu; không xóa thư mục chứa dữ liệu nguồn hoặc tệp do người dùng quản lý.

## 5. Dùng `uptodate` để kiểm tra quan hệ giữa file đầu vào và đầu ra

Khi tự viết bước sinh mã hoặc xử lý tài nguyên, có thể dùng task `<uptodate>` để kiểm tra đầu ra có mới hơn đầu vào hay không. Task này đặt một property nếu đầu ra được xem là up-to-date.

Ví dụ một schema tạo ra một Java source:

~~~xml
<project name="schema-build" default="compile">

    <property environment="env"/>
    <property name="schema.file" location="schema/customer.xsd"/>
    <property name="generated.dir" location="build/generated"/>
    <property name="generated.file" location="${generated.dir}/Customer.java"/>

    <target name="check-generated-source">
        <uptodate property="customer.source.current"
                  srcfile="${schema.file}"
                  targetfile="${generated.file}"/>
    </target>

    <target name="generate-source"
            depends="check-generated-source"
            unless="customer.source.current">
        <mkdir dir="${generated.dir}"/>
        <exec executable="${env.SCHEMA_GENERATOR}"
              failonerror="true">
            <arg value="${schema.file}"/>
            <arg value="${generated.file}"/>
        </exec>
    </target>

    <target name="compile" depends="generate-source">
        <mkdir dir="build/classes"/>
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false">
            <src path="${generated.dir}"/>
        </javac>
    </target>

</project>
~~~

Trong ví dụ:

1. `check-generated-source` dùng `<uptodate>` so sánh `customer.xsd` với `Customer.java`.
2. Nếu output tồn tại và không cũ hơn input, task đặt property `customer.source.current`.
3. Target `generate-source` phụ thuộc `check-generated-source`. Nếu property đã được đặt, phần thân target bị bỏ qua bởi `unless`.
4. Nếu output thiếu hoặc input mới hơn output, property không được đặt; generator chạy và tạo lại `Customer.java`.
5. Target `compile` phụ thuộc `generate-source`, vì vậy compiler chỉ bắt đầu sau khi bước sinh source đã được xử lý.

Ví dụ giả định biến môi trường `SCHEMA_GENERATOR` trỏ tới executable của công cụ sinh mã và công cụ nhận hai đối số theo thứ tự input, output. Trong build thực tế, hãy thay bằng lệnh, classpath và tham số của generator đang dùng. Nếu generator có nhiều đầu ra, phải kiểm tra đủ các output cần thiết; chỉ kiểm tra một tệp đại diện có thể bỏ sót output bị thiếu.

`<uptodate>` là task kiểm tra file freshness. `depends` trong ví dụ vẫn có vai trò riêng: nó bảo đảm target kiểm tra và target sinh mã được xử lý trước compile. Nếu bỏ `depends="check-generated-source"`, property có thể chưa được tính tại thời điểm Ant quyết định có bỏ qua `generate-source` hay không.

## 6. `if` và `unless` không thay thế kiểm tra file

Target có thể dùng `if` hoặc `unless` để quyết định có thực hiện phần thân target hay không:

~~~xml
<target name="generate" unless="output.current">
    <!-- Generate output -->
</target>
~~~

Nhưng `unless` chỉ kiểm tra property có tồn tại hay không. Nó không tự so sánh file đầu vào với file đầu ra. Property `output.current` phải được đặt bởi một task trước đó, chẳng hạn `<uptodate>`.

Một cấu trúc hoàn chỉnh thường có hai target:

~~~xml
<target name="check-output">
    <uptodate property="output.current"
              srcfile="src/input.xml"
              targetfile="build/output.dat"/>
</target>

<target name="generate" depends="check-output" unless="output.current">
    <!-- Recreate build/output.dat when it is missing or stale. -->
</target>
~~~

Dependency bảo đảm bước check chạy trước bước generate. `uptodate` quyết định property theo quan hệ input/output. `unless` dùng kết quả đó để bỏ qua phần thân generate khi không cần làm lại.

Cần nhớ điều kiện của target không loại bỏ dependency của target đó. Khi `generate` có `depends="check-output"`, target `check-output` vẫn được xử lý trước; sau đó Ant mới quyết định có chạy các task bên trong `generate` hay không.

## 7. Kết hợp dependency target và dependency file trong một build

Một build có thể dùng cả hai lớp:

- Target dependency xác định thứ tự các bước.
- File dependency xác định bước tạo đầu ra có cần làm lại hay không.

Ví dụ luồng xử lý tài nguyên và biên dịch:

~~~text
Target dependency:

check-schema -> generate-source -> compile -> package
      |                |              |          |
      v                v              v          v
   check input      create .java   create .class  create JAR

File dependency:

customer.xsd -> Customer.java -> Customer.class -> app.jar
~~~

Trong sơ đồ trên, các mũi tên ở dòng target biểu diễn thứ tự target. Các mũi tên ở dòng file biểu diễn quan hệ tạo dữ liệu. Một target có thể kiểm tra file rồi không thực hiện công việc sinh output; nhưng target sau vẫn được phép chạy vì dependency graph đã được đáp ứng.

Nếu chỉ khai báo target dependency:

~~~xml
<target name="compile" depends="generate-source"/>
~~~

thì `generate-source` được xử lý trước compile mỗi lần compile được gọi. Điều đó không tự làm bước generate trở nên incremental.

Nếu chỉ kiểm tra file freshness mà không nối target dependency, build có thể kiểm tra output ở đúng một target nhưng target compile lại không có bảo đảm rằng bước generate đã chạy trước. Hai lớp cần phối hợp để vừa đúng thứ tự, vừa tránh làm lại công việc không cần thiết.

## 8. Chọn công cụ kiểm tra theo loại đầu vào/đầu ra

Ant có nhiều task hỗ trợ thao tác với file. Nên chọn theo quan hệ thực tế cần mô tả.

| Nhu cầu | Cơ chế thường dùng | Ý nghĩa |
|---|---|---|
| Target B cần target A chạy trước | `depends` | Điều phối target, không so sánh tệp |
| Biên dịch Java từ source sang class | `<javac>` | Compiler task có lựa chọn source cần biên dịch theo trạng thái đầu ra |
| So sánh một input với một output | `<uptodate srcfile="..." targetfile="...">` | Đặt property khi output hiện tại theo tiêu chí freshness |
| So sánh một tập input với output | `<uptodate>` cùng nested `<srcfiles>` và mapper phù hợp | Kiểm tra nhiều file đầu vào theo ánh xạ đầu ra |
| Xóa output cũ trước khi build sạch | `<delete>` trong target `clean` | Loại bỏ output còn sót, bao gồm output của source đã bị xóa |
| Sao chép file chỉ khi cần cập nhật | `<copy>` với cấu hình mặc định phù hợp | Tránh ghi lại destination khi không cần theo quy tắc copy của Ant |

Đối với nhiều source và nhiều output, cần xác định ánh xạ rõ ràng. Nếu mỗi input tạo ra một output có tên tương ứng, mapper có thể biểu diễn quan hệ đó. Nếu nhiều input cùng tạo một output tổng hợp, cần kiểm tra toàn bộ input set so với output tổng hợp. Không nên dùng một output đại diện nếu các output còn lại có thể bị xóa hoặc hỏng độc lập.

## 9. Timestamp có giới hạn gì?

Cơ chế freshness dựa trên thời gian sửa đổi đơn giản và nhanh, nhưng nó không phải bằng chứng tuyệt đối rằng nội dung đầu ra tương ứng với nội dung đầu vào.

Một số tình huống cần lưu ý:

- File được thay nội dung nhưng công cụ giữ nguyên timestamp.
- Hệ thống file có độ phân giải timestamp thấp, khiến hai lần ghi gần nhau có thời gian bằng nhau.
- Đồng hồ của máy build hoặc filesystem không đồng nhất.
- Output được khôi phục từ cache hoặc archive với timestamp không phản ánh đúng lịch sử build.
- Compiler option, JDK, classpath hoặc biến môi trường thay đổi nhưng timestamp source không đổi.
- Một source bị xóa khiến output cũ không còn input để so sánh.

Khi các yếu tố này quan trọng, có thể dùng fingerprint hoặc checksum của đầu vào và cấu hình build, lưu lại cùng output. Nếu fingerprint thay đổi, buộc tạo lại output. Một cách đơn giản khác là chạy `clean` trong pipeline phát hành để loại bỏ ảnh hưởng của đầu ra cũ, đổi lại sẽ tốn thời gian build hơn.

Timestamp cũng không mô tả quan hệ nội dung giữa hai tệp. Nó chỉ là quy tắc quyết định thực dụng: nếu input mới hơn output, giả định output đã cũ. Đối với các pipeline cần tái lập chặt chẽ, cần quản lý cả phiên bản công cụ, dependency và tham số sinh đầu ra.

## 10. Cách chẩn đoán khi target chạy nhưng file không được cập nhật

Khi build có vẻ chạy đúng target nhưng output không thay đổi, hãy xác định chính xác lớp nào chịu trách nhiệm:

1. **Target có nằm trong invocation không?** Kiểm tra lệnh Ant, default target và `depends`.
2. **Target có bị bỏ qua bởi `if`/`unless` không?** Tìm property điều kiện và task đặt property đó.
3. **Task có chạy thật không?** Bật `-verbose` hoặc `-debug` để xem task được gọi và file được chọn.
4. **Input/output có đúng đường dẫn không?** Kiểm tra `srcdir`, `destdir`, `srcfile`, `targetfile`, mapper và working directory.
5. **Timestamp có khiến output được xem là mới không?** So sánh thời gian sửa đổi của từng input và output.
6. **Có đầu vào khác chưa được mô hình hóa không?** Kiểm tra classpath, compiler option, JDK, generator version và biến môi trường.
7. **Có output cũ từ source đã xóa không?** Chạy target clean an toàn rồi build lại, sau đó kiểm tra thư mục output.

Lệnh hữu ích:

~~~bash
ant -verbose compile
ant -debug compile
~~~

Có thể dùng PowerShell để xem timestamp:

~~~powershell
Get-Item 'src/main/java/App.java' | Select-Object FullName, LastWriteTime
Get-Item 'build/classes/App.class' | Select-Object FullName, LastWriteTime
~~~

Trên Linux/macOS:

~~~bash
stat src/main/java/App.java
stat build/classes/App.class
~~~

Nếu output không tồn tại, hãy xác định task nào có trách nhiệm tạo nó. Nếu output tồn tại nhưng không được làm mới, xem property freshness và các input thực tế. Nếu source đã bị xóa nhưng class vẫn còn, timestamp check đơn lẻ không giải quyết được; cần clean hoặc một cơ chế quản lý output theo manifest.

## 11. Nguyên tắc thiết kế build có thể dự đoán

Một build Ant rõ ràng nên tuân theo các nguyên tắc:

- Dùng `depends` để thể hiện quan hệ thứ tự giữa các bước có tên.
- Dùng task file freshness để quyết định khi nào cần tạo lại đầu ra.
- Để mỗi target có trách nhiệm rõ ràng và đặt task gần target sở hữu công việc đó.
- Không coi target dependency là cơ chế incremental.
- Không coi timestamp là dependency graph đầy đủ của mọi đầu vào.
- Bảo đảm generator thất bại thì build cũng thất bại, để compile không sử dụng output chưa được tạo đúng.
- Có target `clean` xóa đúng đầu ra build sở hữu.
- Theo dõi những thay đổi về compiler, classpath, tham số và công cụ sinh mã nếu chúng ảnh hưởng đến kết quả.
- Giữ log đủ chi tiết để biết target nào chạy, task nào được gọi và output nào được tạo.

Khi một target luôn phải chạy nhưng phần việc bên trong có thể không cần lặp lại, hãy để target nằm trong dependency graph và đặt logic freshness ở task thích hợp. Cách tổ chức này giữ luồng build dễ hiểu, đồng thời tận dụng incremental processing ở cấp tệp.

## Kết luận

Phụ thuộc target mô tả thứ tự thực hiện các bước build: `depends` bảo đảm target cần thiết được xử lý trước target phụ thuộc. Phụ thuộc giữa tệp nguồn và đầu ra mô tả dữ liệu nào tạo nên dữ liệu nào và đầu ra có cần tạo lại hay không. Task `javac` có cơ chế incremental cho source/class; `<uptodate>` hỗ trợ kiểm tra freshness của các cặp hoặc tập file; `clean` loại bỏ output cũ, kể cả output còn sót sau khi source bị xóa. Một build Ant đáng tin cậy kết hợp cả dependency graph ở cấp target và kiểm soát freshness ở cấp file, đồng thời nhận diện những đầu vào như classpath, compiler options và công cụ sinh mã mà timestamp đơn giản không thể tự theo dõi.
