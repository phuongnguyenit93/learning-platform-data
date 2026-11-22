# Thứ tự phụ thuộc, phụ thuộc chung và chu kỳ target trong Apache Ant

Trong Apache Ant, thuộc tính depends của một target khai báo những target phải hoàn thành trước khi target đó được thực hiện. Khi nhiều target cùng dùng một bước chuẩn bị, Ant có thể đi qua các nhánh phụ thuộc mà vẫn chỉ thực hiện target dùng chung một lần trong cùng một lượt build. Ngược lại, nếu các target phụ thuộc vòng tròn vào nhau, Ant không thể xác định thứ tự hợp lệ và sẽ báo lỗi chu kỳ.

Hiểu rõ ba điểm này giúp thiết kế buildfile có luồng thực thi dễ dự đoán: xác định đúng bước tiên quyết, khai báo thứ tự theo danh sách dependency và giữ đồ thị phụ thuộc không có chu trình.

## 1. Cách khai báo quan hệ phụ thuộc

Một target có thể khai báo thuộc tính depends. Giá trị của thuộc tính là danh sách tên các target cần chạy trước target hiện tại, phân tách bằng dấu phẩy.

~~~xml
<target name="prepare">
    <mkdir dir="build" />
</target>

<target name="compile" depends="prepare">
    <javac srcdir="src/main/java"
           destdir="build"
           includeantruntime="false" />
</target>
~~~

Khi chạy lệnh:

~~~bash
ant compile
~~~

Ant thực hiện target prepare trước, sau đó mới thực hiện các task bên trong target compile. Quan hệ này có thể đọc theo cách: compile cần prepare hoàn tất trước khi bắt đầu.

Nếu một target cần nhiều bước tiên quyết, có thể liệt kê nhiều tên:

~~~xml
<target name="package" depends="compile,copy-resources">
    <jar destfile="build/app.jar" basedir="build/classes" />
</target>
~~~

Trong ví dụ, cả compile và copy-resources đều phải hoàn tất trước khi package chạy. Ant lần lượt xử lý các dependency theo thứ tự được khai báo; mỗi dependency cũng được xử lý các prerequisite của chính nó trước.

Tên target trong depends phải khớp với target đã khai báo trong cùng project. Nếu tham chiếu đến một tên không tồn tại hoặc viết sai tên, Ant sẽ báo lỗi khi xây dựng thứ tự thực thi.

## 2. Thứ tự thực hiện dependency

Có thể hình dung quan hệ phụ thuộc như một đồ thị có hướng. Nếu target B khai báo depends="A", có một quan hệ từ bước tiên quyết A đến bước cần nó B: A phải chạy trước B.

Ví dụ:

~~~xml
<project name="build-order" default="package">
    <target name="prepare">
        <echo message="Prepare output directory" />
    </target>

    <target name="compile" depends="prepare">
        <echo message="Compile source code" />
    </target>

    <target name="copy-resources" depends="prepare">
        <echo message="Copy application resources" />
    </target>

    <target name="package" depends="compile,copy-resources">
        <echo message="Create application package" />
    </target>
</project>
~~~

Khi chạy target package, thứ tự có thể đọc được như sau:

~~~text
prepare
   |
   +----> compile --------+
   |                      |
   +----> copy-resources -+----> package
~~~

Trình tự thực hiện là:

1. prepare tạo thư mục đầu ra.
2. compile chạy sau prepare để biên dịch mã nguồn.
3. copy-resources chạy sau prepare để sao chép tài nguyên.
4. package chạy sau khi cả compile và copy-resources đã hoàn tất.

Trong danh sách depends="compile,copy-resources", Ant xử lý nhánh compile trước rồi đến nhánh copy-resources. Nếu đổi thành depends="copy-resources,compile", thứ tự hai nhánh sẽ đổi theo danh sách đó, nhưng cả hai vẫn phải hoàn tất trước package.

Cần phân biệt thứ tự dependency với thứ tự khai báo các target trong file XML. Việc đặt target compile trước target package trong buildfile không tự tạo ra quan hệ phụ thuộc. Muốn package chờ compile, phải khai báo depends hoặc thiết kế một quan hệ tương ứng. Hãy dùng depends để diễn đạt thứ tự cần thiết thay vì dựa vào vị trí các thẻ target trong file.

Các task bên trong một target cũng có thứ tự riêng: theo mặc định, Ant thực hiện lần lượt theo thứ tự chúng xuất hiện trong target. Vì vậy, một dependency target hoàn tất trước khi Ant bắt đầu các task của target phụ thuộc; sau đó các task của target hiện tại mới chạy theo thứ tự khai báo.

## 3. Nhiều dependency và thứ tự danh sách

Một target có thể phụ thuộc vào một hoặc nhiều target. Khi có nhiều dependency trực tiếp, danh sách trong thuộc tính depends xác định thứ tự Ant duyệt các nhánh đó.

Ví dụ:

~~~xml
<target name="first">
    <echo message="First prerequisite" />
</target>

<target name="second">
    <echo message="Second prerequisite" />
</target>

<target name="final" depends="first,second">
    <echo message="Final step" />
</target>
~~~

Khi chạy ant final, Ant thực hiện first, sau đó second, rồi mới đến final. Nếu đổi danh sách thành depends="second,first", thứ tự hai target tiên quyết cũng đổi.

Nếu các target có dependency lồng nhau, Ant xử lý prerequisite trước target đang cần nó. Ví dụ:

~~~xml
<target name="base">
    <echo message="Base" />
</target>

<target name="compile" depends="base">
    <echo message="Compile" />
</target>

<target name="verify" depends="compile">
    <echo message="Verify" />
</target>

<target name="package" depends="compile,verify">
    <echo message="Package" />
</target>
~~~

Khi package yêu cầu compile và verify, Ant đi theo nhánh compile trước. Tiếp theo, khi xử lý verify, dependency compile đã được thực hiện nên Ant không chạy lại compile. Sau đó package mới chạy.

Trình tự là base, compile, verify, package. Ví dụ này cũng cho thấy target được tham chiếu trực tiếp và gián tiếp vẫn được xử lý theo quan hệ phụ thuộc, không phải mỗi lần xuất hiện tên target trong danh sách là một lần thực thi mới.

## 4. Phụ thuộc chung: một prerequisite phục vụ nhiều target

Trong dự án thực tế, nhiều công việc thường cần cùng một bước chuẩn bị. Chẳng hạn, compile và copy-resources đều cần thư mục build tồn tại; test và package đều cần mã nguồn đã biên dịch.

Thay vì lặp lại task tạo thư mục trong từng target, hãy tách bước dùng chung thành một target riêng:

~~~xml
<project name="shared-prerequisite" default="release">
    <target name="prepare" description="Create build directories">
        <mkdir dir="build/classes" />
        <mkdir dir="build/test-classes" />
    </target>

    <target name="compile" depends="prepare"
            description="Compile application sources">
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false" />
    </target>

    <target name="copy-resources" depends="prepare"
            description="Copy application resources">
        <copy todir="build/classes">
            <fileset dir="src/main/resources" />
        </copy>
    </target>

    <target name="verify" depends="compile"
            description="Run verification steps">
        <echo message="Run verification checks here" />
    </target>

    <target name="package" depends="compile,copy-resources"
            description="Create the application JAR">
        <jar destfile="build/app.jar" basedir="build/classes" />
    </target>

    <target name="release" depends="verify,package"
            description="Prepare the release artifact">
        <echo message="Release artifact is ready" />
    </target>
</project>
~~~

Đồ thị dependency của release có thể biểu diễn như sau:

~~~text
release
  |
  +----> verify
  |        |
  |        +----> compile
  |                 |
  |                 +----> prepare
  |
  +----> package
           |
           +----> compile       (đã thực hiện)
           |        |
           |        +----> prepare (đã thực hiện)
           |
           +----> copy-resources
                    |
                    +----> prepare (đã thực hiện)
~~~

Với lệnh ant release, trình tự thực hiện là:

1. prepare: tạo các thư mục cần thiết.
2. compile: biên dịch mã nguồn.
3. verify: thực hiện bước kiểm tra.
4. copy-resources: sao chép tài nguyên.
5. package: tạo file JAR.
6. release: hoàn tất bước chuẩn bị phát hành.

Target prepare là prerequisite chung của compile và copy-resources. Target compile cũng được dùng chung bởi verify và package. Ant chỉ thực hiện mỗi target một lần trong cùng lượt build, vì vậy khi package yêu cầu compile lần nữa, compile không bị chạy lặp.

Đây là cách tổ chức quan trọng khi buildfile có nhiều nhánh. Một target chuẩn bị có thể phục vụ nhiều target phía sau mà không cần sao chép cùng một nhóm task vào nhiều nơi.

## 5. Ant chỉ thực hiện một target một lần trong cùng lượt build

Khi Ant xử lý dependency của một target, nó ghi nhận những target đã được thực hiện. Nếu một target xuất hiện trong nhiều nhánh của đồ thị, Ant bỏ qua lần gặp tiếp theo trong cùng lượt build.

Ví dụ:

~~~xml
<target name="init">
    <echo message="Initialize once" />
</target>

<target name="compile" depends="init">
    <echo message="Compile" />
</target>

<target name="test" depends="init">
    <echo message="Test" />
</target>

<target name="all" depends="compile,test">
    <echo message="All done" />
</target>
~~~

Khi chạy ant all, target init chỉ in thông báo một lần. Dù compile và test đều phụ thuộc vào init, Ant không thực hiện lại init khi chuyển từ nhánh compile sang nhánh test.

Phạm vi của quy tắc này là một lượt thực thi Ant. Nếu chạy hai lệnh Ant độc lập, chẳng hạn:

~~~bash
ant compile
ant test
~~~

thì mỗi lệnh là một lượt build riêng. Target init có thể chạy một lần trong lệnh đầu và một lần nữa trong lệnh thứ hai.

Tương tự, nếu gọi nhiều target trong cùng một lệnh:

~~~bash
ant compile test
~~~

Ant xử lý các target được yêu cầu theo thứ tự trên dòng lệnh; target đã thực hiện trong lượt đó không bị thực hiện lại chỉ vì target tiếp theo cũng phụ thuộc vào nó.

Không nên nhầm quy tắc “một lần trong một lượt build” với cơ chế kiểm tra file đầu ra. Ant không tự kết luận target không cần chạy chỉ vì file đích đã tồn tại. Nếu target nằm trong đồ thị dependency và chưa được thực hiện trong lượt hiện tại, target vẫn được xử lý. Việc một task có bỏ qua công việc hay không còn phụ thuộc vào logic của task, điều kiện và cấu hình cụ thể.

## 6. Chu kỳ target là gì?

Đồ thị dependency hợp lệ phải có hướng đi từ các bước tiên quyết đến các bước cần chúng mà không quay trở lại một target đã nằm trên đường đi. Nếu một target phụ thuộc trực tiếp hoặc gián tiếp vào chính nó, buildfile tạo ra chu kỳ (circular dependency).

Chu kỳ trực tiếp:

~~~xml
<target name="compile" depends="package">
    <echo message="Compile sources" />
</target>

<target name="package" depends="compile">
    <echo message="Create package" />
</target>
~~~

Ở đây:

- compile cần package chạy trước.
- package lại cần compile chạy trước.

Ant không thể tìm ra target nào nên chạy đầu tiên. Khi phân tích dependency, Ant phát hiện chu kỳ và báo lỗi circular dependency. Build không thể thực hiện đồ thị target này theo một thứ tự hợp lệ.

Chu kỳ cũng có thể gồm ba target hoặc nhiều hơn:

~~~xml
<target name="prepare" depends="package" />
<target name="compile" depends="prepare" />
<target name="package" depends="compile" />
~~~

Quan hệ lúc này là package cần compile, compile cần prepare, còn prepare lại cần package. Dù không có target nào phụ thuộc trực tiếp vào chính nó, đường đi vẫn quay về điểm bắt đầu nên đây vẫn là chu kỳ.

## 7. Cách nhận biết và sửa chu kỳ dependency

Khi Ant báo circular dependency, hãy đọc các tên target trong thông báo để lần theo đường đi quay vòng. Sau đó xem lại ý nghĩa thực tế của từng target: bước nào tạo dữ liệu đầu vào, bước nào tiêu thụ dữ liệu đó và bước nào chỉ nên chạy sau cùng.

Một quy trình xử lý hữu ích:

1. Xác định target xuất hiện đầu tiên trong chu kỳ và lần theo các thuộc tính depends liên quan.
2. Vẽ lại quan hệ prerequisite → target để thấy đường đi quay trở lại.
3. Xác định bước chuẩn bị chung đang bị khai báo sai hướng hoặc bị gắn vào quá nhiều target.
4. Tách phần việc dùng chung thành một target nền, rồi để các target tiêu thụ phụ thuộc vào target nền đó.
5. Bỏ quan hệ depends ngược chiều; giữ luồng một chiều từ chuẩn bị, biên dịch, kiểm tra đến đóng gói.
6. Chạy lại target gốc và kiểm tra thứ tự các thông báo hoặc task thực tế.

Ví dụ, nếu buildfile cũ khai báo compile phụ thuộc package vì compile cần một thư mục do package tạo ra, trong khi package lại phụ thuộc compile, cần tách thao tác tạo thư mục ra khỏi package:

~~~xml
<target name="prepare">
    <mkdir dir="build/classes" />
</target>

<target name="compile" depends="prepare">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false" />
</target>

<target name="package" depends="compile">
    <jar destfile="build/app.jar" basedir="build/classes" />
</target>
~~~

Giờ đây, prepare tạo đầu vào cần thiết, compile sử dụng thư mục đó để tạo bytecode, còn package dùng bytecode để tạo JAR. Dependency đi theo một hướng và không có target nào cần target phía sau quay lại nó.

Nếu hai công việc thực sự cần dữ liệu của nhau, không nên giải quyết bằng cách tạo hai target phụ thuộc vòng tròn. Hãy chia quy trình thành các giai đoạn nhỏ hơn: target thứ nhất tạo dữ liệu trung gian, target thứ hai xử lý dữ liệu đó, rồi một target điều phối gọi các giai đoạn theo thứ tự. Nếu bản chất công việc là một thuật toán lặp, hãy triển khai vòng lặp trong task hoặc chương trình chuyên biệt thay vì mô tả vòng lặp bằng depends.

## 8. Phân biệt dependency với các cơ chế khác

Thuộc tính depends chỉ mô tả thứ tự giữa các target. Nó không phải công cụ quản lý toàn bộ trạng thái của build.

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| depends | Bảo đảm target tiên quyết chạy trước target hiện tại | package phụ thuộc compile |
| if / unless trên target | Điều kiện để target hiện tại được thực hiện | Chỉ chạy target khi property được đặt hoặc chưa được đặt |
| Điều kiện và thuộc tính | Quyết định giá trị cấu hình hoặc kiểm tra trạng thái | Kiểm tra property, file, thư mục |
| Task | Thực hiện công việc cụ thể | javac, copy, jar, delete |
| Task phụ thuộc file đầu vào/đầu ra | Quyết định cách xử lý dựa trên dữ liệu và trạng thái file | javac bỏ qua một số nguồn không cần biên dịch lại |

Một target có thể có dependency ngay cả khi bản thân target bị bỏ qua bởi điều kiện if hoặc unless. Các target được khai báo trong depends vẫn là prerequisite cần được Ant xử lý theo đồ thị. Vì vậy, đừng dùng điều kiện trên target để thay thế việc thiết kế dependency đúng hướng.

Tương tự, khai báo depends không tự bảo đảm file đầu ra luôn mới nhất, không tải thư viện và cũng không tự giải quyết xung đột dependency. Những yêu cầu đó cần task, cấu hình và công cụ phù hợp.

## 9. Những lỗi thiết kế thường gặp

### 9.1. Lặp lại cùng task chuẩn bị ở nhiều target

Nếu compile và test đều cần tạo thư mục build, sao chép cùng task mkdir vào cả hai target khiến cấu hình trùng lặp. Hãy tách target prepare dùng chung và để các target cần nó khai báo depends="prepare".

### 9.2. Khai báo depends theo chiều ngược

Nếu package cần file class do compile tạo ra, package phải phụ thuộc compile. Khai báo compile phụ thuộc package sẽ đảo ngược quan hệ dữ liệu và có thể tạo chu kỳ.

### 9.3. Cho rằng target xuất hiện trước trong XML sẽ tự chạy trước

Thứ tự thẻ target trong buildfile không thay thế quan hệ depends. Hãy khai báo rõ prerequisite để người đọc và Ant cùng hiểu thứ tự cần thiết.

### 9.4. Khai báo một prerequisite nhiều lần để mong nó chạy lại

Một target chỉ được thực hiện một lần trong cùng lượt build. Nếu cần cùng một thao tác thực hiện ở hai thời điểm khác nhau, hãy tách thành hai target với mục đích riêng, hoặc thiết kế lại luồng task; không thể buộc Ant chạy lại cùng target chỉ bằng cách liệt kê tên nó ở nhiều nhánh.

### 9.5. Dùng target clean làm dependency chung một cách tùy tiện

Nếu mọi target đều phụ thuộc clean, mỗi lần chạy compile hoặc test đều xóa đầu ra trước đó. Điều này có thể làm build chậm và gây mất kết quả cần tái sử dụng. Thông thường, clean nên là target người dùng gọi rõ ràng khi muốn dọn dẹp, hoặc được đặt trong một target tổng hợp có chủ đích.

### 9.6. Tạo target điều phối nhưng vẫn khai báo dependency ngược

Một target all hoặc release có thể gom nhiều nhánh công việc. Tuy nhiên, target thành phần không nên phụ thuộc ngược trở lại target điều phối. Chỉ target điều phối phụ thuộc vào các target thành phần, theo một hướng rõ ràng.

## 10. Nguyên tắc tổ chức dependency dễ bảo trì

- **Mô hình hóa theo luồng dữ liệu.** Bước tạo đầu vào chạy trước bước tiêu thụ đầu vào.
- **Tách prerequisite chung.** Nếu nhiều target cần cùng một bước, tạo target nền có tên thể hiện mục đích.
- **Giữ dependency một chiều.** Tổ chức theo các giai đoạn như prepare → compile → verify → package → release.
- **Dùng danh sách depends có chủ đích.** Thứ tự các tên target trong danh sách là thứ tự Ant xử lý các nhánh trực tiếp.
- **Không dựa vào vị trí khai báo trong XML.** Khai báo quan hệ bằng depends để luồng thực thi rõ ràng.
- **Tránh target quá lớn.** Một target nên đại diện cho một giai đoạn có mục tiêu dễ hiểu.
- **Kiểm tra bằng một target gốc thực tế.** Chạy target tổng hợp và quan sát thứ tự task để phát hiện prerequisite bị thiếu hoặc khai báo sai.
- **Giữ target hỗ trợ độc lập với target điều phối.** Target con không nên quay lại phụ thuộc target all hoặc release.

## 11. Kết luận

Thuộc tính depends tạo nên đồ thị thực thi của buildfile Ant. Ant xử lý các prerequisite trước target cần chúng, duy trì thứ tự theo danh sách dependency và chỉ thực hiện một target một lần trong cùng lượt build, kể cả khi target đó là prerequisite chung của nhiều nhánh. Một đồ thị dependency hợp lệ phải không có chu kỳ; nếu một target trực tiếp hoặc gián tiếp phụ thuộc vào chính nó, Ant sẽ báo lỗi và không thể hoàn thành thứ tự thực thi.

Khi thiết kế buildfile, hãy bắt đầu từ luồng dữ liệu và thứ tự công việc thực tế. Tách bước chuẩn bị dùng chung, khai báo quan hệ theo một hướng và giữ target điều phối ở phía sau các target thành phần. Cách tổ chức này làm cho build dễ đọc, dễ mở rộng và dễ tìm nguyên nhân khi một bước chạy sai thứ tự.

