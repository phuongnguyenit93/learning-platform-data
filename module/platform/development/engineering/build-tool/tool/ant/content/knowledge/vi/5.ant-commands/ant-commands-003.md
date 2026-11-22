# Khám phá target bằng -projecthelp

Apache Ant cho phép một build file khai báo nhiều target, mỗi target đại diện cho một bước công việc như chuẩn bị thư mục, biên dịch, kiểm thử hoặc đóng gói. Khi mở một dự án Ant chưa quen thuộc, việc đầu tiên thường là tìm xem dự án cung cấp những target nào và target mặc định là gì.

Tùy chọn dòng lệnh `-projecthelp` giúp thực hiện việc đó. Ant đọc build file của dự án rồi hiển thị danh sách target cùng mô tả của chúng. Đây là cách nhanh để khám phá giao diện sử dụng của một build file trước khi quyết định chạy bước nào.

## 1. Cú pháp cơ bản

Chạy lệnh sau trong thư mục chứa `build.xml`:

~~~bash
ant -projecthelp
~~~

Ant cũng cung cấp dạng viết tắt `-p`:

~~~bash
ant -p
~~~

Hai lệnh trên có cùng mục đích: yêu cầu Ant hiển thị thông tin trợ giúp của project đang được nạp. Chúng không yêu cầu chạy một target cụ thể.

Nếu build file có tên khác `build.xml`, dùng tùy chọn `-f` để chỉ rõ file:

~~~bash
ant -f build-ci.xml -projecthelp
~~~

Có thể dùng dạng viết tắt cùng với `-f`:

~~~bash
ant -f build-ci.xml -p
~~~

Đường dẫn sau `-f` được phân giải từ thư mục làm việc hiện tại của lệnh. Nếu đang đứng ngoài thư mục dự án, hãy cung cấp đường dẫn tương đối hoặc tuyệt đối phù hợp:

~~~bash
ant -f path/to/project/build.xml -p
~~~

Trên Windows, có thể dùng dấu gạch chéo ngược trong đường dẫn PowerShell, ví dụ:

~~~powershell
ant -f .\build-ci.xml -projecthelp
~~~

## 2. Ant hiển thị những thông tin nào?

Kết quả trợ giúp thường chia target thành hai nhóm:

- **Main targets**: những target có thuộc tính `description` để mô tả mục đích.
- **Other targets**: những target không có mô tả.

Ví dụ, một build file có thể khai báo:

~~~xml
<project name="inventory" default="package" basedir=".">

    <description>
        Build ứng dụng Inventory.
    </description>

    <target name="init">
        <mkdir dir="build/classes"/>
    </target>

    <target name="clean" description="Xóa kết quả build cũ">
        <delete dir="build"/>
    </target>

    <target name="compile"
            depends="init"
            description="Biên dịch mã nguồn Java">
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false"/>
    </target>

    <target name="package"
            depends="compile"
            description="Đóng gói ứng dụng thành JAR">
        <jar destfile="build/inventory.jar"
             basedir="build/classes"/>
    </target>

</project>
~~~

Trong ví dụ này:

- `clean`, `compile` và `package` có `description`, nên được xếp vào nhóm Main targets.
- `init` không có `description`, nên được xếp vào nhóm Other targets.
- `package` là target mặc định vì project khai báo `default="package"`.
- Phần tử `description` trực tiếp bên trong `project` mô tả toàn bộ build file. Nó khác với thuộc tính `description` đặt trên từng target.

Đầu ra thực tế phụ thuộc phiên bản Ant và đường dẫn build file. Ví dụ minh họa về cách phân nhóm:

~~~text
Buildfile: /workspace/inventory/build.xml

Main targets:

 clean     Xóa kết quả build cũ
 compile   Biên dịch mã nguồn Java
 package   Đóng gói ứng dụng thành JAR

Other targets:

 init

Default target: package
~~~

Tên target là thông tin để gọi bước build; phần mô tả giúp người đọc hiểu mục đích của bước đó mà không cần mở ngay phần thân target.

## 3. Vai trò của thuộc tính description

Thuộc tính `description` của target là thông tin dành cho người đọc và công cụ trợ giúp:

~~~xml
<target name="compile"
        depends="init"
        description="Biên dịch mã nguồn Java">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>
~~~

Ở đây:

- `name="compile"` đặt tên target.
- `depends="init"` khai báo target cần được xử lý trước.
- `description="Biên dịch mã nguồn Java"` giải thích công việc của target trong danh sách trợ giúp.
- `javac` là task thực hiện biên dịch khi target được chạy.

Việc thêm mô tả không làm thay đổi cách thực thi target. Nó không tự thêm dependency, không thay đổi task và cũng không khiến target được chạy tự động.

Nếu target không có mô tả, target vẫn hợp lệ và vẫn có thể được gọi bằng tên. Ant đưa target đó vào nhóm Other targets để người dùng biết rằng nó tồn tại.

### Mô tả target và mô tả project khác nhau

Có hai vị trí dễ nhầm:

~~~xml
<project name="inventory" default="package">

    <description>
        Build ứng dụng Inventory cho các môi trường triển khai.
    </description>

    <target name="package"
            description="Đóng gói ứng dụng thành JAR">
        <jar destfile="build/inventory.jar"
             basedir="build/classes"/>
    </target>

</project>
~~~

Phần tử `<description>` nằm trong `project` mô tả tổng thể build file. Thuộc tính `description` nằm trên `target` mô tả một bước cụ thể và là cơ sở để Ant phân loại target trong phần trợ giúp.

Khi tạo build file cho nhóm phát triển, nên ghi cả mô tả project và mô tả cho những target mà người dùng cần gọi trực tiếp.

## 4. Dùng -projecthelp để khám phá một dự án lạ

Có thể dùng trợ giúp theo một quy trình ngắn:

1. Xác định build file cần khám phá.
2. Chạy `ant -projecthelp` hoặc `ant -f <build-file> -projecthelp`.
3. Đọc tên và mô tả trong nhóm Main targets để tìm các thao tác dành cho người dùng.
4. Xem nhóm Other targets để nhận biết các bước hỗ trợ hoặc target chưa được mô tả.
5. Kiểm tra thuộc tính `default` của phần tử `project` để biết target được chọn khi chạy lệnh `ant` mà không ghi tên.
6. Mở phần khai báo của target cần tìm hiểu để xem task, dependency và điều kiện thực thi.
7. Chỉ chạy target sau khi đã hiểu tác động của nó, đặc biệt với các bước xóa, publish hoặc deploy.

Ví dụ, khi nhìn thấy danh sách:

~~~text
Main targets:

 clean       Remove generated files
 compile     Compile application sources
 test        Run automated tests
 package     Create application archive
 deploy      Deploy application

Other targets:

 init
 prepare
~~~

Có thể nhận ra những bước chính của dự án gồm dọn dẹp, biên dịch, kiểm thử, đóng gói và triển khai. Tuy nhiên, chỉ từ danh sách này chưa thể kết luận `deploy` triển khai tới môi trường nào hoặc có ghi đè tài nguyên hay không. Cần đọc target tương ứng trong build file trước khi thực thi.

### Chọn đúng build file

Một repository có thể chứa nhiều build file cho các mục đích khác nhau, ví dụ:

~~~text
project/
├── build.xml
├── build-ci.xml
├── build-release.xml
└── tools/
    └── build-docs.xml
~~~

Mỗi build file có thể khai báo tập target và target mặc định riêng. Vì vậy, khi cần xem target của quy trình CI, phải chỉ đúng file:

~~~bash
ant -f build-ci.xml -projecthelp
~~~

Nếu vô tình chạy `ant -p` ở thư mục khác, Ant có thể đọc nhầm build file hoặc báo không tìm thấy build file. Hãy xác nhận thư mục hiện tại và đường dẫn truyền cho `-f`.

## 5. -projecthelp không thực thi quy trình build

Mục đích của `-projecthelp` là hiển thị thông tin về các target. Lệnh này không chạy phần thân các target như `clean`, `compile`, `test` hay `package`.

Có thể phân biệt ba thao tác:

| Lệnh | Mục đích |
|---|---|
| `ant -help` | Hiển thị hướng dẫn sử dụng Ant và các tùy chọn dòng lệnh |
| `ant -projecthelp` | Hiển thị các target được khai báo trong project và mô tả của chúng |
| `ant package` | Thực thi target `package` cùng các target phụ thuộc |

Ví dụ, nếu target `clean` chứa task xóa thư mục build, gọi `ant -projecthelp` chỉ liệt kê target `clean`; nó không thực hiện thao tác xóa. Muốn xóa thực sự, người dùng phải gọi:

~~~bash
ant clean
~~~

Dù không chạy các target, Ant vẫn phải nạp và phân tích build file để tạo thông tin trợ giúp. Vì thế, lỗi cú pháp XML, file được import không tồn tại hoặc cấu hình build không thể nạp vẫn có thể làm lệnh trợ giúp thất bại.

## 6. Những điều danh sách trợ giúp không cho biết

Danh sách từ `-projecthelp` hữu ích để tìm tên target, nhưng không thay thế việc đọc build file.

| Thông tin cần biết | Có thể suy ra trực tiếp từ danh sách trợ giúp? | Nơi cần kiểm tra |
|---|---|---|
| Tên target | Có | Phần trợ giúp |
| Mục đích được khai báo của target | Có, nếu target có mô tả | Thuộc tính `description` |
| Target mặc định | Ant có thể hiển thị; nguồn khai báo là thuộc tính `default` | Phần tử `project` |
| Các target phụ thuộc | Không đầy đủ | Thuộc tính `depends` của target |
| Các task sẽ chạy | Không | Phần thân target |
| Điều kiện `if` và `unless` | Không thể hiện đầy đủ trạng thái điều kiện | Khai báo target và property liên quan |
| Tệp đầu ra và thư mục bị thay đổi | Không | Các task và cấu hình của target |
| Target có chạy thành công hay không | Không | Kết quả khi thực thi target |

Đặc biệt, nhóm Main targets không có nghĩa target đó là target mặc định hoặc target quan trọng nhất về mặt kỹ thuật. Nhóm này chỉ phản ánh việc target có mô tả hay không. Một target trong Other targets vẫn có thể là dependency cần thiết của nhiều bước chính.

Tương tự, `-projecthelp` không phải công cụ dựng đồ thị dependency. Nếu muốn hiểu vì sao target `package` kéo theo `compile`, cần đọc khai báo `depends`:

~~~xml
<target name="init">
    <mkdir dir="build/classes"/>
</target>

<target name="compile" depends="init">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>

<target name="package" depends="compile">
    <jar destfile="build/app.jar"
         basedir="build/classes"/>
</target>
~~~

Từ các khai báo này mới xác định được chuỗi công việc:

~~~text
init → compile → package
~~~

## 7. Viết mô tả tốt để -projecthelp hữu ích

Chất lượng danh sách trợ giúp phụ thuộc vào cách người viết build file đặt tên và mô tả target.

### Đặt tên target theo hành động

Tên nên thể hiện công việc:

~~~xml
<target name="clean" description="Xóa kết quả build cũ"/>
<target name="compile" description="Biên dịch mã nguồn Java"/>
<target name="test" description="Chạy kiểm thử tự động"/>
<target name="package" description="Tạo tệp JAR của ứng dụng"/>
~~~

Tên như `do1`, `step2` hoặc `taskA` không giúp người dùng hiểu mục đích nếu không đọc phần thân target.

### Mô tả ngắn gọn và cụ thể

Mô tả tốt nên trả lời câu hỏi target làm gì. Ví dụ:

~~~xml
<target name="publish"
        description="Đưa gói phát hành lên kho artifact nội bộ">
    <!-- Các task publish -->
</target>
~~~

Mô tả này hữu ích hơn một câu chung chung như `Run publish`, vì nó cho biết đích đến của thao tác. Với target có tác động lớn như `deploy`, `publish` hoặc `clean`, mô tả nên làm rõ môi trường hoặc loại dữ liệu bị tác động khi có thể.

### Mô tả các target dành cho người dùng

Những target thường được gọi trực tiếp nên có mô tả. Các target hỗ trợ nội bộ vẫn có thể được giữ không mô tả nếu nhóm muốn danh sách Main targets tập trung vào giao diện sử dụng chính.

Dù target thuộc nhóm nào, tên vẫn phải dễ hiểu và dependency phải được khai báo rõ. Không nên bỏ mô tả chỉ để che giấu một bước có tác động quan trọng; trợ giúp tốt cần giúp người dùng nhận biết các thao tác họ có thể gọi.

## 8. Các lỗi thường gặp khi dùng -projecthelp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ant báo không tìm thấy build file | Đang chạy ở sai thư mục hoặc tên file không đúng | Chuyển tới thư mục dự án hoặc dùng `-f` |
| Danh sách không có target mong muốn | Đang đọc nhầm build file hoặc target chưa được khai báo/import vào project đó | Kiểm tra file với `-f` và các khai báo target |
| Target nằm trong Other targets | Target không có thuộc tính `description` | Đọc phần thân target; thêm mô tả nếu muốn đưa vào nhóm Main targets |
| Target có mô tả nhưng không chạy được | Mô tả chỉ là tài liệu; dependency hoặc task bên trong có thể bị lỗi | Đọc `depends`, điều kiện và task rồi mới chạy |
| Lệnh trợ giúp thất bại do XML | Thẻ không đóng đúng, thuộc tính sai cú pháp hoặc ký tự XML chưa escape | Sửa cú pháp build file |
| Lệnh trợ giúp thất bại do import | Build file tham chiếu một file khác không tồn tại hoặc không đọc được | Kiểm tra đường dẫn và quyền truy cập file được import |

Nếu Ant không thể nạp build file, hãy xử lý lỗi nạp cấu hình trước. Danh sách target chỉ được tạo sau khi Ant đọc được cấu trúc project.

## 9. Ghi nhớ khi làm việc với Ant

`ant -projecthelp` là điểm bắt đầu thuận tiện để khám phá giao diện của một build file:

- Dùng `ant -projecthelp` hoặc dạng viết tắt `ant -p` để liệt kê target.
- Dùng `-f` khi project có nhiều build file hoặc build file không nằm trong thư mục hiện tại.
- Đọc nhóm Main targets để tìm các bước có mô tả; xem cả Other targets vì chúng vẫn có thể là bước hỗ trợ quan trọng.
- Kiểm tra `default` trong phần tử `project` để biết target mặc định.
- Thêm `description` rõ ràng vào các target mà người dùng cần khám phá.
- Đọc `depends`, `if`, `unless` và các task trong target trước khi chạy một quy trình chưa quen thuộc.

Khi build file có tên target rõ ràng và mô tả đầy đủ, `-projecthelp` trở thành một trang trợ giúp ngay trong terminal. Người phát triển có thể nhanh chóng biết project hỗ trợ những thao tác nào, tìm đúng target để đọc tiếp và lựa chọn lệnh thực thi phù hợp.

