# Phân biệt target công khai và target hỗ trợ nội bộ

Trong Apache Ant, một build file có thể chứa nhiều target: một số target là điểm vào mà lập trình viên hoặc CI gọi trực tiếp, số khác chỉ là bước phụ trợ để những target chính dùng lại. Phân biệt hai nhóm này giúp build file có giao diện dễ hiểu, phần trợ giúp gọn và phần triển khai bên trong có thể thay đổi mà không làm người dùng phải nhớ quá nhiều chi tiết.

Ant không có từ khóa `public`, `private` hay cơ chế phân quyền target giống access modifier trong Java. Khái niệm **target công khai** và **target hỗ trợ nội bộ** chủ yếu là quy ước tổ chức build file. Ant có quy ước tên bắt đầu bằng dấu gạch nối (`-`) để đánh dấu target nội bộ và loại target đó khỏi danh sách trợ giúp `-projecthelp`.

## 1. Target công khai là giao diện sử dụng của build file

Target công khai (public target) là bước mà người dùng dự án được khuyến khích gọi trực tiếp. Nó biểu diễn một mục đích ở mức công việc, ví dụ:

- `clean`: xóa kết quả build cũ.
- `compile`: biên dịch mã nguồn.
- `test`: chạy kiểm thử.
- `package`: tạo JAR hoặc gói phân phối.
- `deploy`: triển khai sản phẩm tới môi trường đã cấu hình.

Người dùng không cần biết target phải tạo thư mục nào, copy tài nguyên ra sao hay gọi task nào theo thứ tự nào. Họ chỉ cần biết mục tiêu muốn thực hiện.

Một target công khai thường có tên dễ nhớ và thuộc tính `description` giải thích rõ công việc:

~~~xml
<target name="compile"
        description="Biên dịch mã nguồn Java">
    <!-- Các bước biên dịch được khai báo ở đây -->
</target>

<target name="package"
        description="Đóng gói ứng dụng thành tệp JAR">
    <!-- Các bước đóng gói được khai báo ở đây -->
</target>
~~~

Khi người dùng chạy:

~~~bash
ant compile
ant package
~~~

Ant chọn target theo tên và xử lý các target phụ thuộc của nó trước khi thực hiện phần thân target được yêu cầu.

Target công khai cũng có thể là target mặc định của project:

~~~xml
<project name="inventory" default="package">
    <!-- Các target -->
</project>
~~~

Khi chạy `ant` mà không chỉ định tên target, Ant bắt đầu từ target `package`. Việc chọn target mặc định nên phản ánh hành động thông thường và an toàn mà người dùng mong đợi từ build file.

## 2. Target hỗ trợ nội bộ phục vụ việc triển khai

Target hỗ trợ nội bộ (internal/helper target) mô tả một bước kỹ thuật nhỏ để target khác sử dụng. Người dùng thông thường không cần gọi hoặc ghi nhớ nó như một lệnh riêng.

Ví dụ, trước khi biên dịch, build cần tạo thư mục đầu ra. Có thể tách thao tác này thành target phụ trợ:

~~~xml
<target name="-prepare-output">
    <mkdir dir="build/classes"/>
</target>

<target name="-compile-main" depends="-prepare-output">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>

<target name="compile"
        depends="-compile-main"
        description="Biên dịch mã nguồn Java"/>
~~~

Trong ví dụ:

- `-prepare-output` chuẩn bị thư mục.
- `-compile-main` thực hiện thao tác biên dịch sau khi thư mục đã sẵn sàng.
- `compile` là điểm vào có ý nghĩa với người dùng; nó phụ thuộc vào bước biên dịch nội bộ.

Người dùng gọi `ant compile`, còn build file chịu trách nhiệm điều phối các bước phụ trợ. Nếu sau này cách chuẩn bị thư mục thay đổi, người viết build có thể sửa target nội bộ mà không cần đổi tên lệnh `compile` mà nhóm phát triển hoặc pipeline đang sử dụng.

## 3. Quy ước tên bắt đầu bằng dấu gạch nối

Ant có quy ước: target có tên bắt đầu bằng dấu gạch nối (`-`) được xem là target nội bộ và không được liệt kê trong phần trợ giúp project do `-projecthelp` tạo ra.

Ví dụ:

~~~xml
<target name="clean" description="Xóa kết quả build cũ">
    <delete dir="build"/>
</target>

<target name="compile" description="Biên dịch mã nguồn Java">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>

<target name="-prepare-output">
    <mkdir dir="build/classes"/>
</target>
~~~

Khi chạy:

~~~bash
ant -projecthelp
~~~

Các target `clean` và `compile` xuất hiện trong danh sách trợ giúp vì có mô tả. Target `-prepare-output` không xuất hiện do tên bắt đầu bằng `-`.

Quy ước này hữu ích khi build file có nhiều target kỹ thuật. Người dùng có thể tập trung vào các lệnh ở mức công việc, trong khi các bước triển khai vẫn được khai báo rõ ràng trong XML.

### Dấu gạch nối không phải cơ chế bảo mật

Tên bắt đầu bằng `-` chỉ thể hiện quy ước nội bộ và ảnh hưởng đến việc liệt kê trong trợ giúp. Nó không phải access modifier, không cấp quyền và không bảo vệ thao tác khỏi người có thể đọc hoặc sửa build file.

Target nội bộ vẫn là target của project. Các target khác có thể tham chiếu nó trong `depends`; nó cũng có thể được gọi từ logic build phù hợp. Vì vậy, không dùng tiền tố `-` để bảo vệ bí mật, ngăn truy cập hoặc thay thế kiểm soát quyền đối với môi trường triển khai.

## 4. Không có description khác với tên bắt đầu bằng dấu gạch nối

Hai cách tổ chức này có kết quả khác nhau trong `-projecthelp`:

1. Target không có `description` nhưng tên không bắt đầu bằng `-` thường được đưa vào nhóm **Other targets**.
2. Target có tên bắt đầu bằng `-` được xem là nội bộ và bị ẩn khỏi danh sách trợ giúp project.

Ví dụ:

~~~xml
<target name="init">
    <mkdir dir="build"/>
</target>

<target name="-prepare-classes">
    <mkdir dir="build/classes"/>
</target>

<target name="compile"
        description="Biên dịch mã nguồn Java">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>
~~~

Có thể hiểu cách phân loại như sau:

| Khai báo target | Cách thể hiện trong `-projecthelp` |
|---|---|
| `name="compile"` có `description` | Nhóm Main targets |
| `name="init"` không có `description` | Nhóm Other targets |
| `name="-prepare-classes"` | Không liệt kê trong project help |

Do đó, **bỏ description không đồng nghĩa với ẩn target**. Nếu muốn một bước phụ trợ không xuất hiện trong danh sách trợ giúp, hãy dùng quy ước tên bắt đầu bằng dấu gạch nối. Nếu muốn target vẫn được nhìn thấy nhưng không phải mục tiêu chính, có thể để target không có mô tả; tuy nhiên, nên cân nhắc việc thêm mô tả để người bảo trì hiểu mục đích của nó nếu target cần được biết đến.

## 5. Dùng depends để nối target công khai với target nội bộ

Target nội bộ phát huy tác dụng khi nó được nối vào quy trình thông qua `depends`. Thuộc tính này xác định những target cần hoàn thành trước target hiện tại.

~~~xml
<target name="-prepare-output">
    <mkdir dir="build/classes"/>
    <mkdir dir="build/dist"/>
</target>

<target name="-compile-main" depends="-prepare-output">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>

<target name="compile"
        depends="-compile-main"
        description="Biên dịch mã nguồn Java"/>

<target name="package"
        depends="-compile-main"
        description="Đóng gói ứng dụng thành JAR">
    <jar destfile="build/dist/inventory.jar"
         basedir="build/classes"/>
</target>
~~~

Đồ thị phụ thuộc:

~~~mermaid
flowchart TD
    P["-prepare-output"] --> C["-compile-main"]
    C --> U["compile (công khai)"]
    C --> J["package (công khai)"]
~~~

Người dùng có thể chạy một trong hai lệnh:

~~~bash
ant compile
ant package
~~~

Cả hai đều dùng chung các bước chuẩn bị và biên dịch. Khi một target chung xuất hiện trong nhiều nhánh phụ thuộc của cùng một lượt build, Ant chỉ xử lý target đó một lần trong lượt thực thi project.

Cách tổ chức này giảm lặp lại task. Nếu mỗi target công khai tự khai báo lại thao tác tạo thư mục và biên dịch, khi cần thay đổi đường dẫn hoặc tùy chọn compiler, người bảo trì phải sửa nhiều nơi. Tách phần chung thành helper target giúp các điểm vào cùng dùng một cách triển khai.

### Target công khai cũng có thể là target điều phối

Một target công khai có thể không chứa task nào mà chỉ tập hợp các bước cần thiết:

~~~xml
<target name="verify"
        depends="-compile-main,-run-tests"
        description="Biên dịch và chạy kiểm thử"/>
~~~

Lệnh `ant verify` thể hiện mục tiêu ở mức người dùng. Các bước chi tiết được ủy quyền cho target nội bộ. Cách làm này phù hợp khi target công khai biểu diễn một quy trình gồm nhiều giai đoạn.

Cần đặt thứ tự trong `depends` theo đúng yêu cầu công việc. Nếu target sau cần đầu ra của target trước, quan hệ phụ thuộc phải thể hiện điều đó. Không dựa vào vị trí khai báo target trong file để suy ra thứ tự thực thi.

## 6. Ví dụ build.xml có cả hai nhóm target

Ví dụ dưới đây tổ chức một ứng dụng Java nhỏ. Người dùng có thể gọi `clean`, `compile` hoặc `package`. Các thao tác tạo thư mục và biên dịch được đặt trong target nội bộ.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="inventory" default="package" basedir=".">

    <property name="src.dir" location="src/main/java"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>

    <!-- Các target hỗ trợ nội bộ -->

    <target name="-prepare-output">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="-compile-main" depends="-prepare-output">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"/>
    </target>

    <!-- Các target công khai -->

    <target name="clean"
            description="Xóa kết quả build cũ">
        <delete dir="${build.dir}"/>
    </target>

    <target name="compile"
            depends="-compile-main"
            description="Biên dịch mã nguồn Java"/>

    <target name="package"
            depends="-compile-main"
            description="Đóng gói ứng dụng thành JAR">
        <jar destfile="${dist.dir}/inventory.jar"
             basedir="${classes.dir}"/>
    </target>

</project>
~~~

Cách sử dụng:

~~~bash
# Xem các mục tiêu công khai
ant -projecthelp

# Biên dịch
ant compile

# Đóng gói (target mặc định)
ant

# Xóa kết quả build
ant clean
~~~

Với cấu trúc trên:

- `ant -projecthelp` hiển thị `clean`, `compile`, `package` trong nhóm target có mô tả.
- `-prepare-output` và `-compile-main` không xuất hiện trong phần trợ giúp vì tên bắt đầu bằng dấu gạch nối.
- `ant compile` xử lý `-prepare-output`, rồi `-compile-main`, sau đó hoàn thành target `compile`.
- `ant package` cũng xử lý các bước nội bộ trước khi tạo JAR.
- `ant` chọn `package` vì project khai báo `default="package"`.

Target `clean` được gọi riêng, không nằm trong chuỗi phụ thuộc của `package`. Vì vậy, lệnh đóng gói không tự động xóa thư mục build.

## 7. Chọn mức độ công khai phù hợp

Không phải mọi target đều cần được xem là lệnh dành cho người dùng. Có thể dùng các tiêu chí sau khi thiết kế build file:

| Tiêu chí | Target công khai | Target hỗ trợ nội bộ |
|---|---|---|
| Mục đích | Một công việc người dùng muốn yêu cầu | Một thao tác kỹ thuật phục vụ công việc khác |
| Người gọi chính | Developer, CI hoặc người vận hành | Các target khác trong build |
| Tên | Ngắn, ổn định, diễn đạt hành động | Thường có tiền tố `-` và mô tả chi tiết thao tác |
| Trợ giúp | Nên có `description` để xuất hiện trong Main targets | Có thể dùng tiền tố `-` để ẩn khỏi project help |
| Phạm vi thay đổi | Nên ổn định vì script bên ngoài có thể gọi | Có thể thay đổi cùng cách triển khai bên trong |
| Ví dụ | `clean`, `compile`, `test`, `package` | `-prepare-output`, `-compile-main`, `-copy-resources` |

Một target nên là công khai khi nó biểu diễn một hành động có ý nghĩa độc lập đối với người dùng. Một target nên là nội bộ khi nó chỉ là chi tiết triển khai, thường không cần được gọi riêng và có thể thay đổi cùng cấu trúc build.

Không nên tạo helper target cho từng task đơn lẻ nếu việc tách đó không tăng khả năng dùng lại hoặc làm rõ trách nhiệm. Quá nhiều target nhỏ khiến người đọc phải lần theo nhiều lớp phụ thuộc. Ngược lại, một target công khai quá lớn chứa toàn bộ thao tác của nhiều giai đoạn sẽ khó bảo trì và khó tái sử dụng. Hãy tách theo trách nhiệm thực tế.

## 8. Các lỗi thiết kế thường gặp

| Cách tổ chức | Vấn đề | Cách cải thiện |
|---|---|---|
| Mọi target đều có tên kỹ thuật và xuất hiện trong trợ giúp | Người dùng khó nhận biết lệnh chính | Tạo các điểm vào công khai, đặt helper với tiền tố `-` |
| Bỏ description với mục đích ẩn target | Target vẫn có thể xuất hiện trong Other targets | Dùng quy ước tên bắt đầu bằng `-` nếu đó là helper nội bộ |
| Dùng tiền tố `-` để nghĩ rằng target được bảo vệ | Tiền tố không phải cơ chế phân quyền | Kiểm soát quyền ở môi trường và hệ thống thực thi bên ngoài Ant |
| Lặp lại cùng task ở nhiều target công khai | Sửa cấu hình phải thực hiện ở nhiều nơi | Tách thao tác dùng chung thành helper target |
| Một target công khai chứa quá nhiều bước không liên quan | Khó hiểu và khó tái sử dụng | Chia theo trách nhiệm và nối bằng `depends` |
| Target helper không có mô tả lẫn quy ước tên rõ ràng | Người bảo trì khó hiểu vai trò của nó | Dùng tên helper có ý nghĩa và comment khi cần |
| Phụ thuộc vòng giữa target | Ant không thể sắp xếp thứ tự thực thi | Thiết kế lại đồ thị phụ thuộc để không có chu trình |

Khi đọc một build file lạ, hãy bắt đầu từ các target có mô tả và target mặc định. Sau đó lần theo `depends` để tìm các helper có tiền tố `-`. Cách đọc từ ngoài vào trong giúp hiểu mục tiêu của quy trình trước khi đi sâu vào từng task.

## 9. Ghi nhớ

- Ant không có khai báo access modifier cho target. Công khai và nội bộ là quy ước tổ chức build.
- Target công khai là các điểm vào có ý nghĩa với developer hoặc CI; nên đặt tên rõ ràng và có `description`.
- Target hỗ trợ nội bộ thực hiện các bước kỹ thuật mà target khác cần dùng lại.
- Tiền tố `-` là quy ước đánh dấu target nội bộ và khiến target không được liệt kê trong `-projecthelp`.
- Target không có `description` nhưng không có tiền tố `-` vẫn có thể xuất hiện trong nhóm Other targets.
- Tiền tố `-` không phải cơ chế bảo mật hay phân quyền.
- Dùng `depends` để nối các bước và giữ cho giao diện target công khai ổn định khi chi tiết triển khai thay đổi.

Một build file được tổ chức tốt cho phép người dùng nhìn thấy một tập lệnh ngắn, có ý nghĩa như `clean`, `compile`, `test` và `package`, trong khi Ant vẫn có thể sử dụng các target phụ trợ để thực hiện từng bước kỹ thuật. Ranh giới này làm cho quy trình build dễ khám phá, dễ gọi từ CI và dễ bảo trì khi cách triển khai thay đổi.

