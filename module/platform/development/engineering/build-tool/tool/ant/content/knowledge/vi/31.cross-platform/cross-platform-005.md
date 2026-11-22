# Kiểm soát quyền thực thi, liên kết tượng trưng và xuống dòng khi build đa nền tảng bằng Apache Ant

Một bản build Apache Ant chạy tốt trên Linux có thể hỏng ngay khi chuyển sang Windows, hoặc vẫn tạo được gói ZIP nhưng người dùng Linux không chạy được script sau khi giải nén. Nguyên nhân đôi khi không nằm ở mã Java mà ở ba thuộc tính của tệp:

1. **Quyền thực thi** (*executable permission*): tệp có được hệ điều hành cho phép chạy như một chương trình/script hay không.
2. **Liên kết tượng trưng** (*symbolic link, symlink*): một đường dẫn tham chiếu đến đường dẫn khác, có thể nằm trong hoặc ngoài thư mục đang đóng gói.
3. **Kiểu xuống dòng** (*line endings*): dùng LF hay CRLF, ảnh hưởng đáng kể đến shell script và một số công cụ dòng lệnh.

Trong module **Build Tool Ant**, chủ đề **Đa nền tảng**, bài này hướng dẫn cách nhận diện và kiểm soát cả ba vấn đề trong quá trình chuẩn bị, sao chép và đóng gói bản phân phối. Các ví dụ ưu tiên cơ chế chuẩn của Ant, đồng thời chỉ rõ giới hạn do hệ điều hành, hệ thống tệp và công cụ giải nén quyết định.

## 1. Vì sao cùng một tệp lại hoạt động khác nhau?

### 1.1. Quyền thực thi không giống nội dung tệp

Trên các hệ thống Unix như Linux và macOS, quyền truy cập thường được thể hiện bằng ba nhóm người dùng: owner, group và others. Mỗi nhóm có thể có quyền đọc (`r`), ghi (`w`), thực thi (`x`).

Ví dụ:

~~~text
-rw-r--r--  run.sh     # 644: doc/ghi cho owner, doc cho group va others
-rwxr-xr-x  run.sh     # 755: owner co rwx, group va others co r-x
~~~

Nếu `run.sh` có nội dung hợp lệ nhưng thiếu quyền `x`, lệnh `./run.sh` thường thất bại với `Permission denied`. Lệnh `sh run.sh` hoặc `bash run.sh` có thể vẫn chạy nếu shell có quyền đọc nội dung, bởi lúc này **shell** là chương trình được thực thi trực tiếp.

Trên Windows, NTFS chủ yếu sử dụng ACL và các quy tắc khởi chạy khác. Thuộc tính POSIX `755` không ánh xạ trực tiếp thành quyền thực thi của một tệp `.cmd`/`.bat` như trên Unix. Vì vậy thao tác `chmod` có ý nghĩa chủ yếu ở môi trường Unix hoặc trong metadata của một số định dạng gói.

### 1.2. Symlink là một đường dẫn, không phải bản sao

Ví dụ trên Unix:

~~~text
releases/
  app-1.2.0/
  app-1.3.0/
current -> releases/app-1.3.0
~~~

`current` là đường dẫn liên kết. Khi truy cập `current`, hệ thống cố truy cập tài nguyên được trỏ đến. Nếu `releases/app-1.3.0` bị xóa hoặc di chuyển, `current` có thể trở thành **liên kết gãy** (*dangling symlink*).

Trong một bản phân phối, hành vi của symlink còn phụ thuộc vào cách sao chép và đóng gói:

- Giữ nguyên symlink: bản phân phối cần chứa thông tin liên kết và đường dẫn đích phải có nghĩa sau khi giải nén.
- Sao chép nội dung đích: liên kết bị chuyển thành tệp/thư mục thông thường; có thể tăng kích thước gói.
- Bỏ qua liên kết: dữ liệu được liên kết có thể biến mất khỏi artifact.

Không nên mặc định rằng mọi task của Ant, hệ thống kiểm soát phiên bản hay phần mềm giải nén sẽ xử lý symlink giống nhau.

### 1.3. LF và CRLF khác nhau ở cấp byte

Một dòng văn bản có thể kết thúc bằng:

| Kiểu | Ký tự | Dạng byte | Hay gặp ở |
|---|---|---|---|
| **LF** | `\n` | `0A` | Unix, Linux, macOS hiện đại, shell script |
| **CRLF** | `\r\n` | `0D 0A` | Nhiều tệp văn bản trên Windows, script `.bat`/`.cmd` |
| **CR** | `\r` | `0D` | Định dạng cũ, hiếm dùng trong dự án hiện đại |

Một file shell có dòng đầu `#!/bin/sh` nhưng lưu bằng CRLF có thể khiến Unix cố tìm trình thông dịch `/bin/sh\r`. Triệu chứng thường thấy là `bad interpreter` hoặc `/bin/sh^M: no such file or directory`. Chỉ thêm quyền `+x` **không sửa được** lỗi xuống dòng đó.

Ngược lại, một số công cụ Windows xử lý LF tốt; tuy vậy script batch truyền thống thường được phân phối ở dạng CRLF để tránh khác biệt giữa các phiên bản công cụ.

## 2. Bản đồ trách nhiệm trong quy trình Ant

Một quy trình đa nền tảng nên phân biệt **nội dung source** và **tệp xuất bản**:

~~~text
src/ va scripts/                Git checkout tren moi he dieu hanh
       |
       v
<copy> vao build/staging/       Tao ban sao de dong goi
       |
       v
<fixcrlf>                     Chuan hoa xuong dong cua tap tin van ban
       |
       v
<chmod> (Unix)                 Cap quyen chay cho script trong staging
       |
       v
<zip> / <tar>                  Dong goi, khai bao metadata quyen neu ho tro
       |
       v
Kiem tra tren he dich         Giai nen, kiem tra lien ket, chay script
~~~

Thứ tự này quan trọng: một thao tác sửa nội dung như `<fixcrlf>` có thể ghi lại tệp, vì thế nên thiết lập quyền thực thi **sau khi** chuẩn hóa văn bản nếu có thể. Đặt các biến đổi vào thư mục staging giúp bản sao trong gói nhất quán mà không thay đổi tệp nguồn do Git quản lý.

Một bảng định hướng nhanh:

| Vấn đề cần xử lý | Cơ chế phù hợp | Giới hạn cần nhớ |
|---|---|---|
| Cấp quyền chạy cho `.sh` trên Unix | Task `<chmod>` hoặc quy ước file mode trong Git | Phụ thuộc hệ điều hành và hệ thống tệp; quyền sau giải nén có thể thay đổi |
| Khai báo mode bên trong ZIP/TAR | `<zipfileset filemode="...">` hoặc `<tarfileset mode="...">` | Metadata trong gói không bảo đảm công cụ giải nén ở mọi nền tảng sẽ áp dụng |
| Tạo symlink | `<symlink>`, hoặc bước triển khai chuyên biệt của hệ điều hành | Phụ thuộc hỗ trợ và quyền tạo liên kết của môi trường |
| Chuẩn hóa EOL | `<fixcrlf>`, `.gitattributes` | Chỉ áp dụng cho tệp văn bản; không sửa nhị phân |
| Kiểm chứng bản phân phối | Kiểm tra sau giải nén trên hệ điều hành mục tiêu | Phải dùng đúng phiên bản/cấu hình môi trường phát hành |

## 3. Quản lý quyền thực thi bằng `<chmod>`

Ant cung cấp task `<chmod>` để thay đổi permission trên hệ điều hành hỗ trợ lệnh `chmod`, thường là các hệ Unix.

Ví dụ đơn giản:

~~~xml
<target name="make-script-executable">
    <chmod file="build/staging/bin/start.sh"
           perm="755"
           osfamily="unix"/>
</target>
~~~

Ở ví dụ trên:

- `file` chỉ đường dẫn tệp cần xử lý.
- `perm="755"` yêu cầu quyền `rwxr-xr-x`.
- `osfamily="unix"` giới hạn thao tác ở hệ điều hành phù hợp; không kỳ vọng tác dụng POSIX tương đương trên Windows.

Có thể áp dụng cho nhiều script trong một thư mục:

~~~xml
<target name="set-unix-permissions">
    <chmod dir="build/staging"
           includes="bin/**/*.sh"
           perm="755"
           osfamily="unix"/>
</target>
~~~

Nếu thư mục đầu vào có cả mã nguồn và dữ liệu, hãy chọn pattern chính xác. Không nên cấp `755` bừa bãi cho file cấu hình, private key, báo cáo hay file chứa dữ liệu nhạy cảm. Với một script chỉ dùng trong nội bộ, quyền `700` hoặc `750` có thể phù hợp hơn; mode phải dựa trên nhu cầu truy cập thực tế.

### Permission của file khác permission của thư mục

Đối với thư mục trên Unix, quyền `x` cho phép **truy cập/đi qua** đường dẫn khi đã biết tên phần tử. Quyền `r` cho phép liệt kê nội dung, tùy các quyền và điều kiện khác. Một thư mục đóng gói có mode `644` có thể khiến người dùng không vào được, dù file bên trong có vẻ đọc được.

Với bản phân phối thông thường:

~~~text
build/staging/          755 (thu muc)
build/staging/bin/      755 (thu muc)
build/staging/bin/run.sh 755 (script)
build/staging/config/   755 (thu muc)
build/staging/config/app.properties 644 (file cau hinh)
~~~

Các giá trị này là **ví dụ**, không phải chính sách an toàn cho mọi loại dữ liệu. File chứa khóa bí mật có thể cần mode hạn chế hơn nhiều và thường không nên đưa vào gói phân phối.

### Git có thể lưu executable bit

Trong repository Git, trạng thái file thông thường thường xuất hiện là `100644` hoặc `100755`. Trên hệ Unix, có thể dùng:

~~~bash
chmod +x scripts/start.sh
git add scripts/start.sh
git ls-files --stage scripts/start.sh
~~~

Nếu làm việc trong môi trường không quản lý executable bit theo kiểu POSIX, có thể đặt bit trong chỉ mục Git:

~~~bash
git update-index --chmod=+x scripts/start.sh
git ls-files --stage scripts/start.sh
~~~

Kết quả được mong đợi cho script là mode `100755` trong chỉ mục. Đây là metadata mà Git lưu; trên Windows, việc checkout file không bảo đảm tệp nhận được quyền POSIX như trên Linux. Vì vậy vẫn cần kiểm tra trên môi trường đích hoặc cấu hình mode khi tạo archive.

## 4. Ghi mode vào tệp ZIP/TAR khi đóng gói

Chỉ gọi `chmod` trước khi tạo ZIP có thể chưa đủ, bởi bước copy, zip và extract có thể xử lý metadata khác nhau. Apache Ant có thể ghi file mode Unix vào các entry của ZIP thông qua `<zipfileset>`.

Ví dụ chia file thường và script thực thi thành hai nhóm **không trùng file**:

~~~xml
<target name="package-zip">
    <mkdir dir="dist"/>

    <zip destfile="dist/application.zip">
        <!-- File thuong: 644. Thu muc: 755. -->
        <zipfileset dir="build/staging"
                    excludes="bin/**/*.sh"
                    filemode="644"
                    dirmode="755"/>

        <!-- Script shell: 755. -->
        <zipfileset dir="build/staging"
                    includes="bin/**/*.sh"
                    filemode="755"
                    dirmode="755"/>
    </zip>
</target>
~~~

`filemode` và `dirmode` là các giá trị mode Unix dạng bát phân. Ở đây file thường nhận `644`, thư mục nhận `755`, script shell nhận `755`. Cách phân nhóm giúp không vô tình cho tất cả file quyền thực thi.

Với gói TAR, `<tarfileset>` cũng có khả năng khai báo mode:

~~~xml
<target name="package-tar">
    <mkdir dir="dist"/>

    <tar destfile="dist/application.tar">
        <tarfileset dir="build/staging"
                    excludes="bin/**/*.sh"
                    mode="644"/>

        <tarfileset dir="build/staging"
                    includes="bin/**/*.sh"
                    mode="755"/>
    </tar>
</target>
~~~

Mode của **entry thư mục** và cách xử lý symlink có thể chịu ảnh hưởng của task, version Ant và định dạng lưu trữ; khi dùng TAR để phân phối trên Unix, hãy kiểm tra cả mode thư mục sau khi giải nén. Đừng suy diễn rằng một archive chứa metadata đúng thì Windows hoặc một công cụ giải nén bất kỳ sẽ phục hồi metadata đó y hệt.

Lưu ý: khả năng thực thi vẫn cần các điều kiện khác, ví dụ hệ thống tệp không bị mount với tùy chọn `noexec` và đường dẫn chứa script có đủ quyền truy cập.

## 5. Tạo và quản lý liên kết tượng trưng

### 5.1. Symlink tuyệt đối và tương đối

Giả sử thư mục phát hành:

~~~text
dist/
  releases/
    app-1.3.0/
  current -> releases/app-1.3.0
~~~

Đường dẫn `releases/app-1.3.0` là ví dụ **tương đối** theo vị trí link `dist/current`. Khi di chuyển cả thư mục `dist` sang một máy khác, link tương đối có cơ hội tiếp tục dùng được nếu cấu trúc bên trong được giữ nguyên.

Trái lại, một link như:

~~~text
current -> /home/developer/builds/app-1.3.0
~~~

là link tuyệt đối gắn với máy xây dựng, thường không phù hợp để phân phối. Một đường dẫn tuyệt đối trên Linux cũng không có nghĩa tương đương trên Windows.

### 5.2. Task `<symlink>` trong Ant

Ant có task `<symlink>` để thao tác với symbolic link ở hệ thống hỗ trợ. Ví dụ tạo tên `current` trỏ tới bản phát hành:

~~~xml
<target name="link-current" depends="stage"
        if="is.unix">
    <symlink action="single"
             link="build/current"
             resource="releases/app-1.3.0"
             overwrite="true"/>
</target>
~~~

Để sử dụng điều kiện `if="is.unix"`, cần xác định property trước đó:

~~~xml
<condition property="is.unix">
    <os family="unix"/>
</condition>
~~~

Đây là **mẫu cấu hình cho môi trường có hỗ trợ symlink**, không phải đảm bảo tất cả máy đều tạo được link. Cách resolve `resource` và hỗ trợ link đích tương đối cần được kiểm tra theo phiên bản Ant/JDK và hệ thống tệp. Với môi trường đóng gói thực tế, hãy chọn đường dẫn đích có nghĩa trong bố cục cuối cùng.

Trên Windows, việc tạo symlink có thể phụ thuộc quyền của tiến trình, chế độ Developer Mode, loại file system và cách công cụ thao tác với filesystem. Nếu bản phân phối phải chạy được trên mọi hệ, việc thay symlink bằng file cấu hình chỉ phiên bản hiện tại hoặc một cơ chế chọn thư mục sau khi cài đặt có thể dễ kiểm soát hơn.

### 5.3. Sao chép symlink không giống sao chép tệp thường

Task `<copy>` hoặc các cơ chế quét FileSet có thể xử lý link theo cách khác nhau tùy nền tảng và cấu hình. Các tình huống thường gặp:

- **Đi theo liên kết** rồi sao chép nội dung đích.
- **Không đi theo** và bỏ qua liên kết trong tập tệp.
- **Giữ nguyên liên kết** nếu cơ chế và định dạng đích thực sự hỗ trợ.

Không mặc định rằng `<copy>` bảo toàn symlink. Thuộc tính `followsymlinks` ở một số loại FileSet hoặc DirectoryScanner quyết định việc quét theo liên kết, nhưng **không đồng nghĩa** với một cam kết lưu lại symlink như symlink trong artifact.

Nếu đóng gói bằng ZIP, hãy kiểm tra công cụ tạo gói có lưu đúng loại entry liên kết không và công cụ giải nén trên máy đích có khôi phục được hay không. Nếu workflow buộc phải bảo toàn symlink, TAR cùng quy trình tạo/giải nén được kiểm soát trên Unix thường là ứng viên để cân nhắc, nhưng vẫn cần xác minh hành vi thực tế.

### 5.4. Bốn rủi ro cần nhận biết

| Rủi ro | Triệu chứng | Cách xử lý |
|---|---|---|
| Link gãy | `No such file or directory` khi truy cập `current` | Kiểm tra đường dẫn đích sau khi copy/giải nén và thứ tự tạo link. |
| Link vòng | Các đường dẫn trỏ lẫn nhau, quét thư mục thất bại hoặc lặp | Tránh cấu trúc tự tham chiếu; chọn phạm vi quét rõ ràng. |
| Link ra ngoài thư mục build | Bản gói vô tình chứa file từ nơi khác hoặc thay đổi theo máy build | Không đi theo link ngoài staging; duyệt các nguồn được phép đưa vào artifact. |
| Thiếu hỗ trợ trên Windows | Checkout link thành file thường, hoặc không thể tạo symlink | Dùng môi trường có hỗ trợ, hoặc cung cấp phương án không phụ thuộc symlink. |

Symlink và hard link là hai khái niệm khác nhau. Hard link tham chiếu tới cùng đối tượng dữ liệu trong cùng filesystem theo cơ chế riêng; các hướng dẫn ở đây dành cho **symbolic link**.

## 6. Chuẩn hóa xuống dòng với `<fixcrlf>`

Ant cung cấp task `<fixcrlf>` để biến đổi kết thúc dòng của **tệp văn bản**. Đây là giải pháp thích hợp khi script trong repository được checkout trên nhiều nền tảng nhưng bản phân phối cần kiểu EOL nhất định.

### 6.1. Chỉ định EOL theo loại script

~~~xml
<target name="normalize-line-endings">
    <!-- Shell script: LF. -->
    <fixcrlf srcdir="build/staging/bin"
             includes="**/*.sh"
             eol="lf"
             eof="remove"
             tab="asis"
             fixlast="true"
             encoding="UTF-8"/>

    <!-- Windows batch: CRLF. -->
    <fixcrlf srcdir="build/staging/bin"
             includes="**/*.bat,**/*.cmd"
             eol="crlf"
             eof="remove"
             tab="asis"
             fixlast="true"
             encoding="UTF-8"/>
</target>
~~~

Ý nghĩa các thuộc tính:

| Thuộc tính | Vai trò |
|---|---|
| `srcdir` | Thư mục nguồn chứa các tệp cần xử lý |
| `includes` | Chỉ chọn các tệp thuộc nhóm mong muốn |
| `eol="lf"` | Chuyển kết thúc dòng sang LF |
| `eol="crlf"` | Chuyển kết thúc dòng sang CRLF |
| `eol="asis"` | Giữ nguyên kiểu kết thúc dòng hiện tại |
| `eof="remove"` | Loại bỏ ký tự kết thúc file kiểu cũ nếu có (khác với dấu xuống dòng cuối file) |
| `tab="asis"` | Giữ nguyên tab, tránh các biến đổi không cần thiết |
| `fixlast="true"` | Thêm dấu xuống dòng ở cuối dòng cuối khi thiếu |
| `encoding="UTF-8"` | Đọc nội dung theo encoding đã chỉ định |

`eof` ở đây liên quan đến ký tự EOF truyền thống như `Ctrl+Z`, **không** có nghĩa xóa toàn bộ dấu xuống dòng cuối file. Với tệp có encoding khác UTF-8, cần dùng encoding thật sự của nguồn thay vì giả định UTF-8.

Chỉ dùng `<fixcrlf>` cho văn bản. Không chạy nó trên `.jar`, `.zip`, `.class`, ảnh, font, file chứng chỉ nhị phân hay mọi file trong thư mục bằng một pattern quá rộng. Chuyển byte trong tệp nhị phân có thể làm hỏng dữ liệu mà tác vụ đóng gói vẫn không báo lỗi rõ ràng.

### 6.2. Ví dụ một lỗi từ CRLF trong shell script

File `scripts/start.sh`:

~~~sh
#!/bin/sh
echo "Starting application"
~~~

Nếu nội dung có byte `0D 0A` và chạy trực tiếp trên Linux, thông báo có thể như:

~~~text
./start.sh: /bin/sh^M: bad interpreter: No such file or directory
~~~

Để xử lý, thực hiện chuẩn hóa EOL ở staging rồi cấp executable bit:

~~~xml
<target name="prepare-shell-script">
    <mkdir dir="build/staging/bin"/>
    <copy file="scripts/start.sh"
          tofile="build/staging/bin/start.sh"/>

    <fixcrlf srcdir="build/staging/bin"
             includes="start.sh"
             eol="lf"
             fixlast="true"/>

    <chmod file="build/staging/bin/start.sh"
           perm="755"
           osfamily="unix"/>
</target>
~~~

Hai thao tác này giải quyết **hai nguyên nhân khác nhau**: `fixcrlf` làm sạch ký tự `\r` trong shebang; `chmod` cho phép chạy trực tiếp trên Unix.

## 7. Kết hợp Git `.gitattributes` với Ant

Git có thể tự chuẩn hóa line ending khi lưu/checkout file, nhưng behavior còn phụ thuộc cấu hình và nội dung repository. Dùng `.gitattributes` để mô tả rõ quy ước theo loại file:

~~~gitattributes
# De Git phan biet van ban/nhị phan khi phu hop.
* text=auto

# Script Unix va file xau hinh text phan phoi theo LF.
*.sh text eol=lf
*.xml text eol=lf
*.properties text eol=lf

# Script Windows.
*.bat text eol=crlf
*.cmd text eol=crlf

# Khong chuyen line ending cua file nhi phan.
*.jar binary
*.zip binary
*.png binary
*.jpg binary
*.class binary
~~~

Quy ước này giảm nguy cơ nội dung thay đổi ngoài ý muốn giữa hai máy. Tuy nhiên:

- `.gitattributes` tác động thông qua quá trình Git checkout/add; nó không tự sửa các tệp đã được copy hoặc generate bởi các công cụ khác.
- Những tệp đã được thêm vào repository trước khi đặt quy ước có thể cần một lần chuẩn hóa index có chủ đích và review diff.
- Ant `<fixcrlf>` vẫn hữu ích để đảm bảo đầu ra staging đúng chuẩn bất kể trạng thái checkout.
- Line ending trong repository và permission trong archive là hai trục độc lập. Một file có LF đúng nhưng thiếu executable bit vẫn có thể không chạy được.

Không nên dùng `git config --global core.autocrlf` làm giải pháp duy nhất cho một repository dùng chung vì nó phụ thuộc cấu hình cá nhân và có thể không diễn đạt chính xác quy ước theo đuôi tệp.

## 8. Một `build.xml` minh họa toàn bộ quy trình

Giả sử dự án chỉ cần phân phối hai script và một file cấu hình:

~~~text
portable-demo/
├── build.xml
├── scripts/
│   ├── start.sh
│   └── start.cmd
├── config/
│   └── app.properties
└── build/                      # Tao khi build
~~~

Nội dung mẫu của các file:

`scripts/start.sh`:

~~~sh
#!/bin/sh
echo "Application started on Unix"
~~~

`scripts/start.cmd`:

~~~bat
@echo off
echo Application started on Windows
~~~

`config/app.properties`:

~~~properties
app.name=portable-demo
~~~

File `build.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="portable-demo" default="dist" basedir=".">

    <property name="build.dir" location="build"/>
    <property name="stage.dir" location="${build.dir}/staging"/>
    <property name="dist.dir" location="dist"/>

    <target name="prepare">
        <mkdir dir="${stage.dir}/bin"/>
        <mkdir dir="${stage.dir}/config"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="stage" depends="prepare">
        <!-- Ban sao chuan bi phan phoi, khong bien doi source. -->
        <copy todir="${stage.dir}/bin">
            <fileset dir="scripts"
                     includes="*.sh,*.cmd"/>
        </copy>

        <copy todir="${stage.dir}/config">
            <fileset dir="config"
                     includes="*.properties"/>
        </copy>
    </target>

    <target name="normalize-eol" depends="stage">
        <fixcrlf srcdir="${stage.dir}/bin"
                 includes="**/*.sh"
                 eol="lf"
                 eof="remove"
                 tab="asis"
                 fixlast="true"
                 encoding="UTF-8"/>

        <fixcrlf srcdir="${stage.dir}/bin"
                 includes="**/*.cmd"
                 eol="crlf"
                 eof="remove"
                 tab="asis"
                 fixlast="true"
                 encoding="UTF-8"/>
    </target>

    <target name="unix-permissions" depends="normalize-eol">
        <!-- Co tac dung POSIX tren he dieu hanh phu hop. -->
        <chmod file="${stage.dir}/bin/start.sh"
               perm="755"
               osfamily="unix"/>
    </target>

    <target name="dist" depends="unix-permissions">
        <zip destfile="${dist.dir}/portable-demo.zip">
            <!-- Dinh nghia mode cua archive cho file thuong. -->
            <zipfileset dir="${stage.dir}"
                        excludes="bin/**/*.sh"
                        filemode="644"
                        dirmode="755"/>

            <!-- Ghi mode thuc thi cho shell script trong ZIP. -->
            <zipfileset dir="${stage.dir}"
                        includes="bin/**/*.sh"
                        filemode="755"
                        dirmode="755"/>
        </zip>

        <echo message="Da tao: ${dist.dir}/portable-demo.zip"/>
    </target>

</project>
~~~

Đứng tại thư mục `portable-demo`, chạy:

~~~bash
ant dist
~~~

Khi dự án thay đổi source hoặc script, Ant tạo/cập nhật staging và ZIP theo cơ chế của các task liên quan. Để đảm bảo không lấy nhầm sản phẩm cũ trong lần kiểm tra phát hành, có thể dọn đầu ra trước:

~~~xml
<target name="clean">
    <delete dir="build"/>
    <delete dir="dist"/>
</target>
~~~

Sau đó:

~~~bash
ant clean dist
~~~

Ví dụ này **không tạo symlink** vì yêu cầu hỗ trợ trên nhiều hệ điều hành khác nhau. Khi một target Unix cần symlink để triển khai, hãy tạo link ở bước riêng phù hợp môi trường và kiểm tra link sau bước triển khai. Điều này tránh buộc cả gói ZIP đa nền tảng phụ thuộc khả năng khôi phục symbolic link của công cụ giải nén trên máy đích.

## 9. Cách kiểm tra sau build trên các hệ điều hành

### Trên Linux hoặc macOS

Kiểm tra quyền và trạng thái symlink:

~~~bash
ls -l build/staging/bin/start.sh
ls -l build/current
test -L build/current && echo "is symlink"
readlink build/current
~~~

Để xem liệu tệp có CRLF hay không, có thể dùng công cụ kiểm tra byte:

~~~bash
od -An -tx1 build/staging/bin/start.sh
~~~

Trong kết quả, cuối dòng LF chứa byte `0a`; CRLF chứa `0d 0a`. Trên môi trường có `file`, lệnh dưới đây cũng thường nhận diện dạng kết thúc dòng:

~~~bash
file build/staging/bin/start.sh
~~~

Kiểm tra script:

~~~bash
./build/staging/bin/start.sh
~~~

Nếu lỗi `Permission denied`, xác minh `x` bit và quyền trên các thư mục cha; nếu lỗi interpreter có ký tự `^M`, kiểm tra EOL; nếu script chạy nhưng báo `command not found`, kiểm tra logic script và môi trường chạy thay vì mặc định cho rằng lỗi file mode.

Để đánh giá gói, cần **giải nén vào thư mục sạch** và kiểm tra lại permission, EOL và liên kết ở bản đã giải nén. Quyền trong thư mục staging không đủ để đảm bảo quyền ở thư mục đích sau bước extract.

### Trên Windows PowerShell

Kiểm tra file và nơi lưu sản phẩm:

~~~powershell
Get-ChildItem .\build\staging\bin
Get-Item .\dist\portable-demo.zip
cmd /c .\build\staging\bin\start.cmd
~~~

Với symlink mà Windows thực sự nhận diện, có thể xem thông tin link:

~~~powershell
Get-Item .\build\current | Format-List FullName,LinkType,Target
~~~

Nếu đường dẫn không tồn tại hoặc checkout link bị chuyển thành nội dung khác, kết quả truy vấn có thể khác. Khi gặp lỗi quyền truy cập trên Windows, cần xem ACL và chính sách hệ thống; không áp công thức `chmod 755` của Unix vào mọi trường hợp.

Để phát hiện EOL, hãy kiểm tra byte hoặc dùng trình biên tập có chế độ hiển thị LF/CRLF. Không mở file nhị phân bằng công cụ tự thay line ending.

### Kiểm tra ZIP ở phía nhận

Có thể liệt kê tệp bằng công cụ ZIP/JDK:

~~~bash
jar tf dist/portable-demo.zip
~~~

Lệnh `jar tf` chủ yếu liệt kê **tên entry**; nó không chứng minh executable mode đã được khôi phục hay symlink đã được bảo toàn. Để kiểm tra permission, cần dùng công cụ xem metadata archive hoặc giải nén bằng công cụ thực sự được người dùng sử dụng và đo lại quyền sau giải nén.

## 10. Khi gặp lỗi, khoanh vùng nguyên nhân như thế nào?

| Thông báo/triệu chứng | Nguyên nhân thường gặp | Điều cần làm |
|---|---|---|
| `./start.sh: Permission denied` | Thiếu bit `x`, thiếu quyền đi qua thư mục cha hoặc filesystem có `noexec` | Xem `ls -l`, thư mục cha, tùy chọn mount; áp dụng mode phù hợp. |
| `/bin/sh^M: bad interpreter` | Script dùng CRLF | Chuẩn hóa về LF bằng `fixcrlf` hoặc quy ước Git. |
| `start.cmd` chạy khác trên Windows | Dòng kết thúc/encoding hoặc lệnh batch không phù hợp | Kiểm tra CRLF, encoding và phiên bản shell. |
| `current: No such file or directory` dù thấy link | Symlink gãy hoặc đích không có sau khi copy | Kiểm tra `readlink` và vị trí đích trong bản phân phối. |
| Symlink biến thành file thường | Công cụ checkout/copy/archive không giữ symlink | Xác định bước làm thay đổi loại tệp; điều chỉnh quy trình hoặc tránh phụ thuộc link. |
| `<symlink>` thất bại trên Windows | Thiếu quyền/tính năng hỗ trợ symlink | Xem quyền của tiến trình, chính sách hệ điều hành và phương án thay thế. |
| Script chạy trong staging nhưng không chạy sau unzip | Mode không được lưu hoặc không được giải nén bảo toàn | Khai báo `filemode`, thử công cụ extract đích, hoặc có bước cấp quyền sau cài đặt. |
| Artifact bị hỏng sau xử lý EOL | `fixcrlf` áp lên file nhị phân hoặc sai encoding | Giới hạn `includes` chỉ cho văn bản và khôi phục artifact từ nguồn sạch. |
| Máy này build được, máy kia lỗi | Khác hệ điều hành, shell, Git checkout, JDK, filesystem, extractor | So sánh byte EOL, file mode và link trên hai máy trước khi sửa mã Java. |

Một số lỗi có thể xảy ra cùng lúc. Ví dụ file `start.sh` vừa thiếu quyền `x`, vừa có CRLF. Sửa một vấn đề rồi chạy lại có thể làm lộ vấn đề còn lại. Hãy kiểm tra từng thuộc tính riêng thay vì chỉ đổi tên file hoặc chạy lại build liên tục.

## 11. Hướng tổ chức repository và CI để ít phát sinh lỗi

### Tách script theo nền tảng

Một cấu trúc dễ quản lý:

~~~text
scripts/
  unix/
    start.sh
    stop.sh
  windows/
    start.cmd
    stop.cmd
config/
  app.properties
build/
  staging/
dist/
~~~

Đặt EOL rõ ràng cho từng nhóm và chỉ chạy task dành riêng cho nền tảng khi phù hợp. Không cần ép script Windows có quyền POSIX `755` nếu nó không được chạy như shell script Unix.

### Đừng phụ thuộc vào symlink khi không cần thiết

Ví dụ chọn phiên bản hiện hành có thể thực hiện qua file cấu hình `current-version.properties` thay vì link `current` khi muốn phân phối qua các nền tảng có khả năng quản lý symlink khác nhau. Nếu symlink là yêu cầu triển khai thực sự, hãy ghi rõ bước tạo nó trong môi trường đích.

### Chuẩn hóa ở cả source và artifact

Một lớp bảo vệ từ Git và một lớp từ build bổ trợ cho nhau:

- `.gitattributes` định nghĩa quy ước nội dung lưu và checkout của repository.
- `<fixcrlf>` đảm bảo script được đưa vào staging có EOL mong muốn.
- `<chmod>` xử lý bit thực thi ở Unix.
- `<zipfileset>`/`<tarfileset>` mô tả metadata khi đóng gói.
- Kiểm tra sau extract xác nhận hành vi mà người dùng nhận được.

### Chạy kiểm tra trên hệ điều hành đích

Đối với dự án cần hỗ trợ Linux và Windows, chỉ build trên một máy không đủ để kết luận toàn bộ pipeline đa nền tảng hoạt động. Kiểm tra tối thiểu nên chạy script thực tế sau khi lấy artifact từ bản build và giải nén trên hệ tương ứng. Với macOS hoặc các môi trường Unix khác, chú ý thêm sự khác biệt về hệ thống tệp, công cụ `stat`, lệnh shell và chính sách thực thi.

## 12. Bài thực hành

### Bài 1 — Thiếu quyền thực thi

Trên Linux/macOS, tạo một file `run.sh` có nội dung:

~~~sh
#!/bin/sh
echo "OK"
~~~

Quan sát sự khác biệt giữa:

~~~bash
chmod 644 run.sh
./run.sh

chmod 755 run.sh
./run.sh
~~~

Sau đó, cấu hình target Ant dùng `<chmod>` để áp `755` trong staging. Giải thích vì sao `sh run.sh` có thể chạy ngay cả khi `./run.sh` không chạy được.

### Bài 2 — Sai kiểu xuống dòng

Tạo bản sao `run.sh` có CRLF. Quan sát cách shell Unix xử lý dòng shebang. Thêm `<fixcrlf eol="lf">` và chạy lại. Kết luận xem nguyên nhân là permission hay EOL, hoặc cả hai.

### Bài 3 — Liên kết tương đối

Trên môi trường hỗ trợ symlink, tạo:

~~~text
dist/
  releases/
    1.0/
      readme.txt
  current -> releases/1.0
~~~

Di chuyển cả thư mục `dist` sang đường dẫn khác rồi kiểm tra `current`. Đổi link sang đường dẫn tuyệt đối của máy ban đầu và so sánh hành vi. Ghi lại thời điểm link gãy.

### Bài 4 — Giải nén trên nền tảng đích

Đóng gói file `run.sh` với `<zipfileset filemode="755">`. Giải nén bằng công cụ thực sự được dùng trong dự án, sau đó kiểm tra `ls -l` và chạy file. So sánh với gói không đặt mode. Quan sát sự khác nhau giữa *metadata chứa trong archive* và *quyền trên file sau khi giải nén*.

## 13. Kết luận

Khi xây dựng bản phân phối đa nền tảng bằng Apache Ant, cần quản lý **nội dung** và **metadata của file** như hai phần riêng. Quyền thực thi giúp script chạy đúng trên Unix; symlink cần cấu trúc đường dẫn và khả năng hỗ trợ của filesystem; còn LF/CRLF phải phù hợp với loại script và công cụ đọc nó. Quy trình bền vững là: chọn file nguồn rõ ràng, đưa vào staging, chuẩn hóa EOL, đặt permission phù hợp, đóng gói với metadata cần thiết, rồi kiểm chứng trên môi trường đích.

### Tài liệu tham khảo

- [Apache Ant Manual — Chmod task](https://ant.apache.org/manual/Tasks/chmod.html)
- [Apache Ant Manual — FixCRLF task](https://ant.apache.org/manual/Tasks/fixcrlf.html)
- [Apache Ant Manual — Symlink task](https://ant.apache.org/manual/Tasks/symlink.html)
- [Apache Ant Manual — Zip task](https://ant.apache.org/manual/Tasks/zip.html)
- [Apache Ant Manual — Tar task](https://ant.apache.org/manual/Tasks/tar.html)
- [Git documentation — gitattributes](https://git-scm.com/docs/gitattributes)
