# Kiểm tra khóa tệp, xóa tệp và khác biệt hệ thống tệp trong Apache Ant

Một file `build.xml` có thể chạy tốt trên Linux nhưng thất bại ở Windows khi xóa thư mục `build/`, hoặc đóng gói đủ tài nguyên trên máy phát triển nhưng lại thiếu file khi chạy trên CI. Trong nhiều tình huống, cú pháp XML và tên task đều đúng: vấn đề nằm ở **trạng thái file đang được sử dụng**, **quyền trên hệ thống tệp** hoặc **khác biệt giữa môi trường chạy**.

Bài học này hướng dẫn đọc lỗi và kiểm tra thao tác file trong **Apache Ant** trên Windows, Linux và macOS. Mục tiêu là nhận diện đúng nguyên nhân trước khi thay đổi cấu hình build; biết thiết kế thao tác xóa an toàn và xác nhận kết quả trên những nền tảng dự án cần hỗ trợ.

## 1. Ant thao tác với file như thế nào?

Các task như `<mkdir>`, `<delete>`, `<copy>`, `<move>`, `<javac>`, `<jar>` và `<zip>` đều đọc hoặc ghi lên hệ thống tệp. Ant cung cấp cú pháp XML chung, nhưng việc mở, đóng, đổi tên hay xóa file được thực hiện qua Java và khả năng của filesystem bên dưới. Vì vậy cùng một task có thể gặp điều kiện thực thi khác nhau trên từng máy.

Ví dụ luồng build:

~~~mermaid
flowchart LR
    A[clean: xóa output cũ] --> B[prepare: tạo thư mục]
    B --> C[compile: ghi file class]
    C --> D[package: tạo archive]
    D --> E[test hoặc deploy: sử dụng artifact]
~~~

Một lần `clean` có thể thất bại nếu ứng dụng hoặc chương trình khác vẫn mở artifact được tạo ở lần build trước. Ngược lại, việc `clean` báo thành công **chưa chắc** nghĩa là mọi process đều đã ngừng sử dụng dữ liệu cũ.

Để xử lý được lỗi, cần phân biệt bốn khái niệm:

| Khái niệm | Nội dung | Ví dụ |
|---|---|---|
| **Đường dẫn** | Tên và vị trí file mà task xử lý | `build/classes/Main.class` |
| **Handle/file descriptor** | Tài nguyên mà một process còn giữ khi mở file | JVM đang đọc JAR hoặc ghi log |
| **Quyền truy cập** | Hệ điều hành cho phép tài khoản hiện tại thực hiện thao tác nào | Tài khoản CI không có quyền xóa thư mục |
| **Trạng thái filesystem** | Khả năng lưu trữ, mount, liên kết, cách so sánh tên và timestamp | Ổ mạng, symlink, volume phân biệt hoa/thường |

Thông báo `Unable to delete file` chỉ cho biết **một thao tác xóa đã thất bại**. Chưa đủ bằng chứng để kết luận chắc chắn đó là khóa tệp.

## 2. Khác biệt về việc xóa file đang mở

### Windows: quyền chia sẻ và handle đang mở

Trên Windows, khi ứng dụng mở file, chế độ chia sẻ của handle có thể quyết định việc process khác có được xóa hoặc đổi tên file đó hay không. Nếu một process giữ handle **không cho phép thao tác xóa**, Ant có thể báo không xóa được file hoặc thư mục chứa file đó.

Các nguồn gây ra tình huống này có thể là:

- JVM đang chạy từ một JAR hoặc mở tài nguyên bên trong archive.
- Test tạo file log, report hoặc kết nối dữ liệu nhưng chưa đóng stream.
- IDE, công cụ xem ZIP/JAR hoặc trình quét antivirus vừa mở artifact.
- Chương trình con do Ant gọi còn chạy, dù một target đã kết thúc.
- Một job CI khác cùng dùng thư mục output.

**Không phải mọi file đang mở trên Windows đều cấm xóa:** kết quả phụ thuộc chế độ chia sẻ mà chương trình dùng khi mở handle. Do đó cần kiểm tra đúng handle, không chỉ đếm process đang chạy.

### Linux và macOS: xóa tên file khác với đóng file

Trên nhiều hệ thống tệp kiểu Unix, thao tác xóa file thường thực hiện bằng cơ chế `unlink`: loại bỏ một tên file khỏi thư mục. Một process đang giữ file descriptor vẫn có thể tiếp tục đọc hoặc ghi vào đối tượng file cũ, dù đường dẫn không còn tồn tại.

Điều này dẫn đến hai hệ quả:

1. Trên Linux/macOS, `<delete>` có thể báo thành công trong lúc process vẫn sử dụng dữ liệu đã được mở trước đó.
2. Với file log lớn đã bị xóa nhưng chưa đóng, dung lượng đĩa có thể chưa được giải phóng cho đến khi process đóng descriptor.

Trên Windows, thao tác tương đương có thể thất bại sớm hơn nếu handle ngăn xóa. Nhưng cả hai trường hợp đều cần giải quyết **vòng đời process** thay vì chỉ lặp lại `clean`.

### Bảng khác biệt thường gặp

| Khía cạnh | Windows | Linux | macOS |
|---|---|---|---|
| Xóa file đang mở | Có thể bị ngăn do chế độ chia sẻ handle | Thường có thể unlink tên file | Thường tương tự Unix |
| Chữ hoa/chữ thường | Volume phổ biến không phân biệt; có ngoại lệ | Filesystem phổ biến phân biệt | Phụ thuộc cấu hình volume; APFS thường không phân biệt |
| Phân cách đường dẫn | Hay thấy `C:\work\project` | `/home/user/project` | `/Users/user/project` |
| Quyền xóa | ACL, quyền thư mục, thuộc tính, chính sách hệ thống | Quyền của thư mục cha, ACL, sticky bit, mount | Quyền kiểu Unix, ACL và bảo vệ hệ thống |
| Link | Symlink, junction, reparse point | Symlink | Symlink |
| Hệ thống tệp mạng | SMB, thư mục đồng bộ | NFS, SMB, mount khác | NFS, SMB, mount khác |

Đây là xu hướng thường gặp; **không được suy ra mọi volume trên một hệ điều hành đều có hành vi giống nhau**. Ví dụ tính phân biệt tên hoa/thường do cấu hình filesystem quyết định, không chỉ do Windows, Linux hay macOS.

## 3. Ví dụ `build.xml` có thao tác tạo và xóa output

Xét một dự án đơn giản:

~~~text
portable-ant/
├── build.xml
├── resources/
│   └── config.properties
├── build/                # output sinh ra
└── dist/                 # artifact sinh ra
~~~

File `build.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="portable-ant" default="package" basedir=".">
    <property name="build.dir" location="build"/>
    <property name="dist.dir" location="dist"/>
    <property name="resource.dir" location="resources"/>

    <target name="clean">
        <echo message="Cleaning ${build.dir} and ${dist.dir}"/>
        <delete dir="${build.dir}" failonerror="true"/>
        <delete dir="${dist.dir}" failonerror="true"/>
    </target>

    <target name="prepare">
        <mkdir dir="${build.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="stage" depends="prepare">
        <copy todir="${build.dir}">
            <fileset dir="${resource.dir}" includes="**/*"/>
        </copy>
        <echo file="${build.dir}/build-marker.txt"
              message="Created by Ant"/>
    </target>

    <target name="package" depends="stage">
        <zip destfile="${dist.dir}/portable-ant.zip"
             basedir="${build.dir}"/>
    </target>
</project>
~~~

Chạy:

~~~bash
ant -f build.xml clean package
~~~

Trong file này:

- `location="build"` tạo đường dẫn cho thư mục output tương đối với `basedir` của project. Đây là cách dễ di chuyển hơn so với ghi cứng đường dẫn của một máy.
- `<delete dir="...">` xóa thư mục output và nội dung của nó.
- `failonerror="true"` buộc build báo lỗi khi một thao tác xóa bắt buộc không thực hiện được, tránh tiếp tục với file cũ.
- `stage` sao chép tài nguyên, tạo marker và `package` đóng gói kết quả.

Vì mục tiêu `clean` là loại bỏ output cũ, **không được xem việc âm thầm bỏ qua file còn sót là build sạch thành công**. Nếu archive cũ vẫn tồn tại, lần đóng gói sau có thể tạo kết quả khó tái hiện.

## 4. Đọc lỗi xóa file: task, đường dẫn, file bị ảnh hưởng

Ví dụ thông báo minh họa:

~~~text
clean:
     [echo] Cleaning C:\work\demo\build and C:\work\demo\dist
   [delete] Deleting directory C:\work\demo\dist

BUILD FAILED
C:\work\demo\build.xml:9: Unable to delete file
C:\work\demo\dist\app.jar
~~~

Văn bản cụ thể thay đổi theo phiên bản Ant và lỗi hệ điều hành. Cách đọc:

1. `clean:` là **target** đang chạy.
2. `[delete]` là **task** thực hiện thao tác.
3. `build.xml:9` là vị trí cấu hình Ant liên quan đến thao tác xóa.
4. `C:\work\demo\dist\app.jar` là file cần kiểm tra đầu tiên.
5. Chỉ sau khi xác nhận file, process và quyền truy cập mới có thể kết luận nguyên nhân.

| Dấu hiệu | Nguyên nhân có thể | Bước kiểm tra |
|---|---|---|
`Unable to delete file` | Handle, quyền, thuộc tính chỉ đọc, antivirus, ổ mạng | File đích, process, ACL, filesystem |
`Access is denied` | ACL, chính sách hệ thống, file bị chặn | Tài khoản chạy Ant, quyền trên thư mục |
`The process cannot access the file because it is being used by another process` | Một handle Windows ngăn thao tác | Tìm process đang mở đúng file |
`File not found` | Đường dẫn sai, file đã bị dời hoặc tên khác hoa/thường | `basedir`, tên file thực tế |
`Unable to create directory` | Quyền, parent directory, mount read-only | Thư mục cha và quyền ghi |
Lúc được lúc không | Race condition, chương trình con hoặc antivirus | Thời điểm, PID, các job chạy cùng lúc |

Một file không thể xóa có thể do **đúng một** nguyên nhân hoặc nhiều điều kiện chồng lên nhau. Đọc thông báo đầy đủ và ghi nhận trạng thái của lần lỗi đầu tiên thường hữu ích hơn chạy lại nhiều lần không ghi log.

## 5. Kiểm tra khóa tệp trên Windows

Giả sử Ant thất bại khi xóa `C:\work\demo\dist\app.jar`.

### Bước 1: Xác nhận file tồn tại

PowerShell:

~~~powershell
$target = 'C:\work\demo\dist\app.jar'
Test-Path -LiteralPath $target
Get-Item -LiteralPath $target |
    Select-Object FullName, Length, Attributes, LastWriteTime
~~~

Nếu file không tồn tại nữa, kiểm tra có process khác đã xóa/di chuyển nó sau khi Ant báo lỗi hay không. Nếu file tồn tại, tiếp tục xác định ai đang mở.

### Bước 2: Tìm process/handle liên quan

Có thể xem các process Java:

~~~powershell
Get-Process java, javaw -ErrorAction SilentlyContinue |
    Select-Object Id, ProcessName, Path
~~~

Tuy nhiên, danh sách process Java **không chứng minh** process nào đang khóa file. Nguồn giữ handle có thể là IDE, ứng dụng khác hoặc công cụ bảo mật.

Để tìm handle thực tế:

- Mở **Resource Monitor** → tab **CPU** → ô tìm **Associated Handles**, nhập một phần tên file hoặc đường dẫn.
- Dùng **Process Explorer** (Microsoft Sysinternals) và chức năng tìm Handle/DLL để tìm tên file.
- Nếu đã có công cụ **Handle** của Sysinternals, tìm đường dẫn file và đối chiếu process/PID hiển thị.

Khi kết quả chỉ cho thấy phần tên chung, hãy kiểm tra đường dẫn đầy đủ để tránh nhầm file ở workspace khác.

### Bước 3: Giải phóng handle một cách có kiểm soát

Đóng đúng ứng dụng đang mở JAR, dừng test hoặc script còn chạy, hoặc chờ chương trình con hoàn thành. Chỉ can thiệp vào process mà bạn xác định thuộc phiên build/thử nghiệm của mình. Sau đó chạy lại:

~~~powershell
ant -f build.xml clean package
~~~

**Không nên dừng hàng loạt mọi process Java**, vì IDE, database và dịch vụ khác có thể cũng chạy trên JVM. Nếu vẫn lỗi, kiểm tra quyền truy cập và phần mềm bảo vệ file; kết luận “do khóa tệp” lúc này chưa đủ bằng chứng.

### Các nguồn giữ file thường bị bỏ sót

- Java application chưa được dừng sau khi chạy từ JAR vừa build.
- Test mở `FileInputStream`/`FileOutputStream` nhưng không đóng.
- Công cụ nén/giải nén hoặc IDE vẫn đang xem nội dung archive.
- `<exec>` gọi chương trình ngoài tiếp tục chạy ở nền.
- Antivirus, bộ lập chỉ mục hoặc công cụ đồng bộ truy cập output đúng lúc `clean`.

Nếu lỗi ngắt quãng, ghi lại **đường dẫn, thời điểm, PID/handle (nếu có) và target** khi sự cố xảy ra.

## 6. Kiểm tra file đang mở trên Linux và macOS

Nếu môi trường có công cụ `lsof`, có thể xem process đang mở file cụ thể:

~~~bash
lsof /home/dev/demo/dist/app.jar
~~~

Trên Linux, `fuser` (nếu đã cài) cũng có thể hỗ trợ:

~~~bash
fuser /home/dev/demo/dist/app.jar
~~~

Nếu file đã bị xóa khỏi cây thư mục nhưng vẫn có process giữ descriptor, trên Linux có thể kiểm tra:

~~~bash
lsof +L1
~~~

Khả năng quan sát process tùy quyền người dùng, công cụ được cài và hệ điều hành. Lệnh `lsof +L1` đặc biệt hữu ích khi log đã bị xóa nhưng dung lượng đĩa chưa giảm.

### Một tình huống dễ hiểu nhầm

~~~text
Process A: mở /var/log/app.log và tiếp tục ghi
Ant:       xóa /var/log/app.log thành công
Process A: vẫn ghi vào đối tượng file đã mở trước đó
~~~

Kết quả của `ant clean` không xác nhận process A đã ngừng dùng dữ liệu. Để giải phóng tài nguyên, phải quản lý process/stream đúng vòng đời. Nếu build tạo file mới tại cùng đường dẫn, process A có thể vẫn sử dụng file cũ trong khi file mới thuộc một đối tượng khác.

## 7. Thiết kế `<delete>` an toàn và rõ phạm vi

### Xóa đúng một file

~~~xml
<target name="remove-old-archive">
    <delete file="${dist.dir}/app-old.jar" failonerror="true"/>
</target>
~~~

### Xóa toàn bộ thư mục output thuộc sở hữu build

~~~xml
<target name="clean">
    <delete dir="${build.dir}" failonerror="true"/>
    <delete dir="${dist.dir}" failonerror="true"/>
</target>
~~~

Chỉ xóa thư mục do quy trình build tạo ra. Nếu property có thể được thay đổi từ dòng lệnh bằng `-Dbuild.dir=...`, phải kiểm tra giá trị trong thiết kế build, vì một đường dẫn cấu hình sai có thể khiến task xóa ngoài phạm vi dự kiến. Không dùng thư mục chứa source hoặc dữ liệu người dùng làm output cần `clean`.

### Chỉ xóa loại file tạm cần dọn

~~~xml
<target name="remove-temp" depends="prepare">
    <delete failonerror="true">
        <fileset dir="${build.dir}"
                 includes="**/*.tmp"
                 followsymlinks="false"/>
    </delete>
</target>
~~~

`<fileset>` giới hạn phạm vi vào file kết thúc bằng `.tmp` trong cây `build.dir`. Thuộc tính `followsymlinks="false"` giúp tránh theo symbolic link khi duyệt tập file. Target `prepare` ở đây bảo đảm thư mục được tạo trước khi task quét file.

Với `<fileset>`, luôn đối chiếu `includes`/`excludes`. Một mẫu quá rộng có thể chọn nhầm file; mẫu quá hẹp có thể để lại artifact cũ.

### Khi nào không nên đặt `failonerror="false"`?

Ví dụ:

~~~xml
<delete dir="${build.dir}" failonerror="false"/>
~~~

Nếu build yêu cầu trạng thái sạch để bảo đảm kết quả, việc bỏ qua lỗi xóa có thể khiến Ant dùng lại file cũ rồi báo `BUILD SUCCESSFUL`. Chỉ bỏ qua lỗi đối với thao tác **thật sự tùy chọn**, khi sự tồn tại của file cũ không ảnh hưởng tính đúng đắn. Không dùng tùy chọn này như cách chữa chung cho lỗi file bị khóa.

## 8. Kiểm tra tồn tại không đồng nghĩa kiểm tra khóa

Task `<available>` dùng để kiểm tra một file có tồn tại:

~~~xml
<condition property="archive.exists">
    <available file="${dist.dir}/app.jar" type="file"/>
</condition>
<echo message="archive.exists = ${archive.exists}"/>
~~~

Nhưng:

- **File tồn tại** không có nghĩa file không bị handle chặn xóa.
- **File không tồn tại** không có nghĩa một process Unix đã ngừng dùng file descriptor cũ.
- Việc file đang mở có cấm xóa hay không tùy API, mode chia sẻ và filesystem.

Do đó không sử dụng `<available>` như cơ chế phát hiện khóa độc quyền hoặc bảo đảm an toàn trước `<delete>`. Nếu một khóa chỉ tồn tại rất ngắn do process sắp kết thúc, có thể cân nhắc retry có giới hạn **sau khi đã xác định nguyên nhân**; chờ vô hạn chỉ che lỗi quyền, sai đường dẫn và process bị kẹt.

## 9. Đường dẫn đa nền tảng: `basedir`, dấu `/` và dấu cách

Ưu tiên dùng property `location` và đường dẫn tương đối theo project:

~~~xml
<project name="portable-paths" default="prepare" basedir=".">
    <property name="src.dir" location="src/main/java"/>
    <property name="classes.dir" location="build/classes"/>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <echo message="Source = ${src.dir}"/>
        <echo message="Classes = ${classes.dir}"/>
    </target>
</project>
~~~

Trong thuộc tính đường dẫn của task Ant, viết `src/main/java` với dấu `/` thường di động giữa Windows, Linux và macOS. Ant/Java diễn giải đường dẫn cho hệ điều hành. Tuy nhiên **chương trình ngoài được gọi bằng `<exec>` có thể có cú pháp đường dẫn riêng**, vì thế cần kiểm tra yêu cầu của chính công cụ đó.

### Truyền đường dẫn chứa dấu cách

PowerShell:

~~~powershell
ant -f "C:\work\Build Tool Ant\build.xml" clean
~~~

Linux/macOS:

~~~bash
ant -f "/home/dev/Build Tool Ant/build.xml" clean
~~~

Khi đường dẫn chứa dấu cách, shell cần dấu nháy phù hợp. Trong `build.xml`, giá trị thuộc tính đã nằm trong dấu nháy XML; không tự thêm dấu nháy shell vào giá trị property trừ khi task hoặc chương trình con thực sự yêu cầu.

### Chỉ rõ thư mục làm việc cho công cụ ngoài

~~~xml
<exec executable="git"
      dir="${basedir}"
      failonerror="true">
    <arg value="status"/>
    <arg value="--short"/>
</exec>
~~~

Task `<exec>` có `dir` giúp quy định thư mục làm việc; `<arg>` truyền từng đối số riêng. Ví dụ giả định Git có sẵn trong `PATH` và chỉ minh họa cấu hình lệnh ngoài. Khi chạy các công cụ đặc thù nền tảng, nên xác định rõ chương trình tương ứng cho mỗi môi trường thay vì phụ thuộc vào shell ngầm định.

## 10. Chữ hoa/chữ thường và các quy tắc đặt tên

Giả sử dự án chứa:

~~~text
resources/
└── Config.properties
~~~

nhưng cấu hình tham chiếu:

~~~xml
<copy file="resources/config.properties"
      tofile="${build.dir}/config.properties"/>
~~~

Trên volume không phân biệt chữ hoa/chữ thường, đoạn này có thể vô tình hoạt động. Trên filesystem phân biệt, `Config.properties` và `config.properties` là hai tên khác nhau và Ant không tìm thấy file.

Để tránh lỗi:

1. Ghi đúng chữ hoa/thường của tên file trong `build.xml` và trong nguồn.
2. Không tạo hai file có tên chỉ khác chữ hoa/thường nếu build phải chạy trên volume không phân biệt.
3. Khi phát hiện `File not found` chỉ trên một nền tảng, so sánh tên thật trên đĩa với tên trong log.
4. Không dùng nhánh điều kiện theo hệ điều hành để che lỗi tên file trong repository.

Ngoài ra, Windows có các quy tắc riêng về ký tự không hợp lệ trong tên file (chẳng hạn `<`, `>`, `:`, `"`, `|`, `?`, `*`) và tên dành riêng; Linux/macOS áp dụng những giới hạn khác. Dự án tạo file từ dữ liệu đầu vào cần chọn tên có thể dùng trên tất cả nền tảng được hỗ trợ.

## 11. Quyền truy cập và thuộc tính chỉ đọc

Không xóa được file không nhất thiết là do process khác giữ file:

- **Windows:** quyền ACL, quyền thư mục, thuộc tính read-only, chính sách bảo mật và phần mềm bảo vệ file có thể chặn thao tác.
- **Linux/macOS:** quyền ghi và thực thi trên thư mục cha thường liên quan trực tiếp đến việc xóa tên file; còn có ACL, sticky bit, immutable flag hoặc mount read-only.
- **Container/CI:** đầu ra có thể được tạo bởi UID/tài khoản khác hoặc trên volume được mount ở chế độ không cho ghi.

Kiểm tra trên Linux/macOS:

~~~bash
ls -ld build
ls -l build
~~~

Kiểm tra trên Windows PowerShell:

~~~powershell
Get-Item -LiteralPath '.\build' |
    Select-Object FullName, Attributes
Get-Acl -LiteralPath '.\build' | Format-List
~~~

Những lệnh này giúp quan sát trạng thái, chưa tự động xác định phương án sửa quyền. Điều chỉnh quyền theo ownership của dự án; không cấp quyền rộng một cách vô điều kiện chỉ để `clean` chạy được.

## 12. Symbolic link, junction và phạm vi xóa

Một đường dẫn nằm trong thư mục `build` có thể trỏ sang dữ liệu bên ngoài thông qua symlink hoặc junction:

~~~text
project/
├── build/
│   ├── task.tmp
│   └── shared -> /shared-data     # liên kết minh họa
└── build.xml
~~~

Nếu cấu hình duyệt/xóa đệ quy đi theo liên kết, thao tác có thể chạm đến thư mục không thuộc output của project. Vì vậy:

- Giữ các thư mục `build` và `dist` tách biệt dữ liệu cần bảo quản.
- Cân nhắc `followsymlinks="false"` cho các `<fileset>` khi không muốn quét qua symlink.
- Kiểm tra tác động của từng task trên filesystem thật; không mặc định mọi task xử lý symlink/junction giống nhau.
- Tránh cấu hình `build.dir` trỏ đến thư mục chia sẻ, thư mục gốc hay đường dẫn có thể thay đổi từ bên ngoài mà không kiểm tra.

Trên Windows có thêm junction/reparse point; trên Linux/macOS có symbolic link. Các đối tượng này làm cho **đường dẫn hiển thị** chưa chắc phản ánh **vị trí lưu trữ thực** mà task đang tác động.

## 13. Timestamp và sự khác nhau giữa clean build với incremental build

Một số task sử dụng thời gian sửa đổi file để quyết định có cần tạo lại đầu ra không. Filesystem, đồng hồ máy, độ phân giải timestamp và cơ chế đồng bộ khác nhau có thể tạo ra hành vi không giống nhau.

Ví dụ:

- `<javac>` có thể chọn tập file nguồn cần biên dịch dựa trên trạng thái nguồn và output.
- `<copy>` có thể bỏ qua file đích được cho là mới hơn hoặc đã cập nhật.
- File trên network share hoặc được copy từ máy khác có thể có timestamp bất thường.

Khi chỉ một nền tảng gặp vấn đề “không build lại dù đã sửa file”, hãy kiểm tra timestamp thực tế, trạng thái cache và input/output, rồi thử một clean build trong môi trường kiểm soát. **Không tự động sửa timestamp bằng `touch`** để che khác biệt; việc đó có thể làm mất dấu nguyên nhân thật.

## 14. Race condition: hai build cùng sử dụng một thư mục

Một lỗi tưởng như khóa tệp có thể là xung đột giữa các job:

~~~mermaid
sequenceDiagram
    participant A as Ant job A
    participant FS as build/
    participant B as Ant job B
    A->>FS: ghi build/classes/Main.class
    B->>FS: clean xóa build/
    A->>FS: package đọc Main.class
    FS-->>A: file thiếu hoặc artifact không nhất quán
~~~

Ngay cả nơi cho phép xóa file đang mở, việc hai job dùng chung output có thể khiến build thất bại hoặc tạo artifact không đúng.

Biện pháp:

1. Mỗi job độc lập nên có workspace và thư mục output riêng.
2. Không chạy `clean` song song với `compile` hoặc `package` nếu cùng đụng một output.
3. Chờ chương trình con đóng file trước khi sang giai đoạn xóa.
4. Cẩn thận với `<exec spawn="true">`: chương trình con có thể còn chạy sau khi Ant tiếp tục và vẫn đang giữ file.
5. Trên CI, kiểm tra chính sách dùng lại workspace và quá trình cleanup giữa job.

Thêm delay ngẫu nhiên hoặc retry liên tục không giải quyết được xung đột thiết kế. Cần quy định ai sở hữu output và khi nào được phép xóa.

## 15. Log Ant và công cụ hệ điều hành

Tăng thông tin nhật ký khi một task file bị lỗi:

~~~bash
ant -f build.xml -verbose clean
~~~

Nếu cần thêm thông tin nội bộ:

~~~bash
ant -f build.xml -debug clean
~~~

`-verbose` và `-debug` có thể in ra đường dẫn file đã phân giải, thao tác của task và các thông tin liên quan. Log chi tiết giúp xác định **task nào** và **đường dẫn nào**, trong khi các công cụ hệ điều hành giúp kiểm tra **ai đang giữ file** và **quyền nào áp dụng**.

| Mục đích | Cách kiểm tra |
|---|---|
Xác định task đang thất bại | Dòng `BUILD FAILED`, `build.xml:line`, log `[delete]` |
Xác định đường dẫn đích | Đọc path trong lỗi; in property qua `<echo>` khi cần |
Kiểm tra sự tồn tại | `Test-Path` (Windows), `ls` hoặc `stat` (Unix) |
Tìm process đang mở | Resource Monitor / Process Explorer (Windows); `lsof` hoặc `fuser` (Unix nếu có) |
Kiểm tra quyền | `Get-Acl` (Windows); `ls -ld`, ACL và mount (Unix) |
Kiểm tra xung đột | PID, timestamp log, các job CI và chương trình con |

### Sơ đồ quyết định xử lý lỗi

~~~mermaid
flowchart TD
    A[Ant báo lỗi thao tác file] --> B[Đọc task và đường dẫn trong log]
    B --> C{Tên và vị trí file đúng không?}
    C -->|Không| D[Sửa basedir, path hoặc hoa/thường]
    C -->|Có| E{Quyền hoặc mount có chặn thao tác?}
    E -->|Có| F[Điều chỉnh ownership, quyền hoặc mount]
    E -->|Không| G{Process khác hay job song song đang dùng file?}
    G -->|Có| H[Đóng handle hoặc tách workspace/đổi thứ tự]
    G -->|Chưa rõ| I[Kiểm tra filesystem, link, antivirus, timestamp]
    D --> J[Chạy lại kịch bản ban đầu]
    F --> J
    H --> J
    I --> J
~~~

Đi từ bằng chứng đến giả thuyết giúp tránh việc sửa tùy tiện `build.xml` khi nguyên nhân thật là process chưa đóng file hoặc tài khoản không đủ quyền.

## 16. Ma trận thử nghiệm đa nền tảng

Không thể chứng minh một build di động chỉ bằng việc chạy thành công trên một máy. Cần kiểm tra những tình huống phù hợp với cách dự án sử dụng Ant.

| Kịch bản | Windows | Linux | macOS | Kết quả mong đợi |
|---|---|---|---|---|
Build sạch | Kiểm tra | Kiểm tra | Kiểm tra | Đầy đủ output; build thành công |
Chạy `clean` hai lần | Kiểm tra | Kiểm tra | Kiểm tra | Không phụ thuộc output đã tồn tại |
Workspace có dấu cách | Kiểm tra | Kiểm tra | Kiểm tra | Đường dẫn được phân giải đúng |
Tên file phân biệt hoa/thường | Kiểm tra | Kiểm tra | Kiểm tra | Không có tham chiếu sai |
File đầu ra còn được process mở | Kiểm tra trong môi trường thử | Kiểm tra trong môi trường thử | Kiểm tra trong môi trường thử | Phản ứng được hiểu và báo lỗi phù hợp |
Tài khoản build không sở hữu output | Kiểm tra nếu áp dụng | Kiểm tra nếu áp dụng | Kiểm tra nếu áp dụng | Quyền được thiết lập rõ |
Các job chạy song song | Dùng output riêng | Dùng output riêng | Dùng output riêng | Không xảy ra race condition |

Một chuỗi thử nghiệm cơ bản:

~~~bash
ant -f build.xml clean package
ant -f build.xml clean
ant -f build.xml clean
~~~

Trên PowerShell, cấu trúc câu lệnh `ant` tương tự. Đánh giá cả mã thoát và `BUILD SUCCESSFUL`/`BUILD FAILED`, đồng thời xác nhận nội dung artifact khi build thành công. Với thử nghiệm file bị khóa, chỉ thao tác trên dữ liệu thử nghiệm và process đã xác định.

## 17. Tình huống luyện tập

### Tình huống A — Không xóa được JAR trên Windows

~~~text
clean:
   [delete] Deleting directory C:\demo\dist

BUILD FAILED
C:\demo\build.xml:7: Unable to delete file C:\demo\dist\app.jar
~~~

**Cách xử lý:** tìm file trong đường dẫn đã báo; kiểm tra handle của JVM/IDE/trình xem archive bằng Resource Monitor hoặc Process Explorer. Nếu có process đang sử dụng, dừng đúng process, sau đó thử lại. Nếu không tìm thấy handle, kiểm tra quyền, thuộc tính và công cụ bảo mật. Không vội chuyển `failonerror` sang `false`.

### Tình huống B — Linux xóa log thành công nhưng dung lượng chưa giảm

~~~text
ant clean: BUILD SUCCESSFUL
Filesystem: dung lượng sử dụng gần như không đổi
~~~

**Cách xử lý:** cân nhắc khả năng file đã bị unlink nhưng process còn mở descriptor. Trên Linux, `lsof +L1` có thể giúp xác định trường hợp này. Dừng hoặc cấu hình lại process ghi log theo đúng vòng đời; chạy `clean` thêm lần nữa thường không giải quyết được.

### Tình huống C — Tài nguyên chỉ bị thiếu trên Linux

~~~text
File thật: resources/Config.yaml
Buildfile: resources/config.yaml
~~~

**Cách xử lý:** đối chiếu chữ hoa/thường. Trên filesystem phân biệt, hai tên file khác nhau; sửa tham chiếu trong XML cho khớp tên thực tế và kiểm tra repository.

### Tình huống D — Hai pipeline cùng sử dụng `build/`

~~~text
Job A: compile -> ghi build/classes
Job B: clean   -> xóa build/classes
Job A: package -> thiếu file .class
~~~

**Cách xử lý:** tách workspace hoặc dùng output riêng, hoặc điều phối để hai job không clean/ghi đè lẫn nhau. Retry đơn thuần không giải quyết nguồn xung đột.

### Tình huống E — Output từ container bị lỗi quyền khi host xóa

~~~text
BUILD FAILED
/workspace/build.xml:12: Unable to delete directory /workspace/build
~~~

**Cách xử lý:** kiểm tra UID/GID hoặc tài khoản đã tạo `build/`, quyền thư mục và thông số mount. Sửa cấu hình ownership/quyền cho đồng nhất với tài khoản chạy Ant; không cấp quyền rộng vô điều kiện.

## 18. Mẫu báo cáo lỗi để người khác tái hiện

Ghi thông tin theo cấu trúc:

~~~text
OS / filesystem: Windows + NTFS, hoặc môi trường thực tế
Ant / JDK: phiên bản đang sử dụng
Lệnh: ant -f build.xml clean package
Buildfile: C:\work\demo\build.xml
Target: clean
Task: delete
Vị trí lỗi: C:\work\demo\build.xml:7
File lỗi: C:\work\demo\dist\app.jar
Thông báo gốc: trích nguyên văn từ log
File còn tồn tại sau lỗi: có/không
Process/handle liên quan: PID và ứng dụng nếu đã xác định
Quyền/ownership: kết quả kiểm tra nếu có
Các job cùng output: có/không/chưa biết
Cách tái hiện: build -> chạy app.jar -> ant clean
Kết quả sau sửa: đóng process -> clean thành công -> artifact đúng
~~~

Việc ghi đủ **file đích, task, quyền, trạng thái process và đặc điểm filesystem** giúp tìm đúng nguyên nhân. Cú pháp đường dẫn di động và task Ant chuẩn chỉ là một phần giải pháp: build chạy ổn định trên nhiều nền tảng còn cần kiểm soát quyền sở hữu output, vòng đời file đang mở, cách đặt tên, liên kết và thứ tự các công việc.
