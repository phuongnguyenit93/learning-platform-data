# Xác minh nguồn tải Ant, JAR mở rộng và dependency để bảo vệ chuỗi build

Một dự án dùng **Apache Ant** có thể có `build.xml` rất đơn giản nhưng vẫn phụ thuộc vào nhiều thành phần chạy với quyền của tài khoản build: bản phân phối Ant, JDK, các task mở rộng, thư viện Java và công cụ được gọi từ task. Nếu chỉ kiểm tra mã nguồn của dự án mà bỏ qua nguồn gốc các thành phần này, bản build có thể chạy mã không mong muốn ngay trong bước biên dịch, kiểm thử hoặc đóng gói.

Trong chủ đề **An toàn build** của module **Build Tool Ant**, bài học này hướng dẫn **xác minh nguồn tải Ant, JAR mở rộng và dependency**. Trọng tâm là chuỗi tin cậy từ nơi phát hành đến tệp thực sự được thực thi, cách kiểm tra checksum và chữ ký số, cách cố định phiên bản và cách ngăn một dependency chưa kiểm tra lọt vào classpath.

## 1. Vì sao cần xác minh cả Ant lẫn thư viện?

Apache Ant thực thi các task mô tả trong `build.xml`. Một số task nằm sẵn trong Ant, nhưng Ant cũng có thể nạp class từ JAR bên ngoài bằng `<taskdef>`, `<typedef>`, Antlib hoặc classpath. Những class này là mã Java có quyền thực thi, không chỉ là dữ liệu được đọc.

Ví dụ những nơi có thể đưa mã vào quy trình:

| Thành phần | Ví dụ | Rủi ro nếu không xác minh |
|---|---|---|
| **Bản phân phối Ant** | Gói `apache-ant-...-bin.zip` hoặc `.tar.gz` | Tệp Ant/JAR lõi bị thay đổi; bản chạy khác với bản dự kiến |
| **Ant extension / Antlib** | JAR định nghĩa task riêng, Apache Ivy, task do nhà cung cấp phát hành | Mã của task chạy trong quá trình build, có thể đọc tệp và gọi lệnh với quyền runner |
| **Dependency biên dịch và chạy** | Thư viện trong `lib/`, thư viện tải từ Maven repository, dependency bắc cầu | JAR bị thay thế, sai phiên bản, tải từ kho không đúng, có mã độc hoặc lỗ hổng |
| **Công cụ ngoài** | JDK, compiler, CLI tải trên mạng, script cài đặt | Chương trình chạy bên ngoài JVM và tác động vào môi trường build |

Ba câu hỏi cần trả lời cho mỗi artifact:

1. **Nguồn**: Nó đến từ dự án/nhà phát hành nào, URL hoặc repository nào, ai kiểm soát nguồn đó?
2. **Tính toàn vẹn và xác thực**: Byte tải về có khớp bản mong đợi không? Có chữ ký từ người phát hành đã được xác thực không?
3. **Tính lặp lại**: Lần build sau có sử dụng đúng phiên bản và đúng byte, kể cả khi cache hoặc repository thay đổi không?

Ba câu hỏi này liên quan nhưng không đồng nghĩa. HTTPS bảo vệ quá trình truyền tải đến một máy chủ đã xác thực; checksum kiểm tra byte; chữ ký số xác nhận rằng dữ liệu được ký bởi khóa tương ứng; còn kiểm tra lỗ hổng và giấy phép là bước đánh giá **mức độ phù hợp để sử dụng**. Một JAR có checksum khớp vẫn có thể chứa lỗ hổng hoặc đến từ nhà cung cấp không đáng tin cậy.

## 2. Chuỗi tin cậy từ tải xuống đến lúc nạp class

Hình dung mỗi lần sử dụng công cụ hoặc dependency là một chuỗi:

~~~text
Trang / repository chinh thuc
             |
             v
Xac dinh ten artifact va phien ban CU THE
             |
             v
Tai artifact qua HTTPS + tai checksum / signature
             |
             v
Kiem tra hash va chu ky voi nguon tin cay
             |
             v
Luu artifact da xac minh vao kho duoc quan ly
             |
             v
Nạp vao ANT_HOME/lib, -lib, classpath hoac taskdef
             |
             v
Build, test, package
~~~

Điểm then chốt là **xác minh trước khi thực thi hoặc nạp class**. Nếu một JAR độc hại đã nằm trong `ANT_HOME/lib` và được JVM nạp khi Ant khởi động, thì việc tạo target `verify` chạy *bên trong Ant* không còn là hàng rào đầy đủ. Với thành phần cần cho chính việc khởi động Ant, hãy xác minh bằng bước độc lập ở shell, CI bootstrap hoặc môi trường cài đặt trước khi gọi `ant`.

Đối với dependency chỉ được sử dụng trong một target sau đó, có thể kiểm tra hash trong target đi trước, rồi mới thực thi `<taskdef>` hoặc `<javac>` sử dụng JAR.

## 3. Chọn đúng nguồn tải Apache Ant

### 3.1. Ưu tiên trang và kho phân phối chính thức

Bắt đầu từ website của dự án Apache Ant:

- Trang dự án và tài liệu: https://ant.apache.org/
- Trang tải bản phân phối nhị phân: https://ant.apache.org/bindownload.cgi
- Hạ tầng phát hành Apache: `https://downloads.apache.org/ant/`
- Kho lưu trữ các bản phát hành cũ: `https://archive.apache.org/dist/ant/`

Các đường dẫn này thể hiện các **vai trò khác nhau**. Trang chủ giúp tìm bản phát hành và hướng dẫn xác minh. Khu vực `downloads.apache.org` cung cấp các bản hiện hành theo cách tổ chức của Apache. Kho `archive.apache.org` dành cho bản phát hành cũ và không đồng nghĩa với đề xuất dùng bản cũ trong hệ thống mới.

Hãy kiểm tra tên dự án, phiên bản, nền tảng và định dạng tệp. Ví dụ tên gói nhị phân Ant có thể có dạng:

~~~text
apache-ant-X.Y.Z-bin.zip
apache-ant-X.Y.Z-bin.tar.gz
~~~

Trong thực tế, `X.Y.Z` phải được thay bằng **phiên bản cụ thể được dự án phê duyệt**. Không dùng nhãn như `latest` làm đầu vào cho pipeline phát hành nếu yêu cầu tái lập bản build. Cũng không nên tin một trang quảng cáo, URL rút gọn hoặc bản mirror lạ chỉ vì tên file có chuỗi `apache-ant`.

**Nguồn tải hợp lệ là điểm bắt đầu, chưa phải xác minh cuối cùng.** Phần còn lại là kiểm tra byte, khóa ký và đường dẫn Ant được thực sự khởi chạy.

### 3.2. Dùng SHA-512 để phát hiện sai lệch dữ liệu

Trang phát hành Apache thường cung cấp file checksum (ví dụ đuôi `.sha512`) cùng với gói phát hành. Một checksum là giá trị tính từ **toàn bộ byte của tệp**. Nếu một byte thay đổi thì giá trị hash gần như chắc chắn thay đổi.

Ví dụ dùng shell trên Linux, với tên tệp đã tải từ trang phát hành:

~~~bash
archive="apache-ant-X.Y.Z-bin.zip"

# File .sha512 da tai tu trang phat hanh.
cat "$archive.sha512"

# Tinh SHA-512 tren file zip thuc te.
sha512sum "$archive"
~~~

Trên macOS, tùy công cụ được cài:

~~~bash
shasum -a 512 "apache-ant-X.Y.Z-bin.zip"
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash -LiteralPath '.\apache-ant-X.Y.Z-bin.zip' -Algorithm SHA512 |
    Format-List Algorithm,Hash,Path
~~~

So sánh chuỗi hex trong kết quả tự tính với chuỗi hex mong đợi do nguồn phát hành cung cấp. Một số tệp `.sha512` chỉ chứa mã hash; số khác có thêm tên tệp hoặc định dạng riêng. Đừng mặc định mọi tệp `.sha512` đều có thể truyền thẳng cho `sha512sum -c` nếu chưa xem định dạng của chúng.

- **Khớp**: tệp tải về có cùng nội dung với tệp mà checksum mô tả.
- **Không khớp**: dừng lại; loại bỏ file tải về, kiểm tra nguồn, cache, proxy và tải lại từ nguồn tin cậy.
- **Không có checksum đáng tin**: chưa có bằng chứng đủ về tính toàn vẹn; không lấy hash tính ngay từ tệp vừa tải rồi coi đó là giá trị chuẩn.

Lưu ý an toàn: nếu kẻ tấn công có thể thay **cả gói tải về và tệp checksum trên cùng nguồn**, checksum tự nó không chứng minh danh tính người phát hành. Khi có chữ ký phát hành, cần xác minh cả chữ ký.

### 3.3. Kiểm tra chữ ký PGP/GPG của bản phát hành

Bản phát hành phần mềm Apache thường có tệp chữ ký ASCII-armored với đuôi `.asc`. Chữ ký giúp kiểm tra nội dung có được ký bằng khóa riêng tương ứng hay không.

Giả sử đã tải đủ:

~~~text
apache-ant-X.Y.Z-bin.zip
apache-ant-X.Y.Z-bin.zip.sha512
apache-ant-X.Y.Z-bin.zip.asc
KEYS
~~~

Tệp `KEYS` là danh sách khóa công khai được giới thiệu qua kênh của dự án; cần tìm liên kết hiện hành tại trang Ant/Apache. Quy trình ví dụ:

~~~bash
# Xem fingerprint truoc khi quyet dinh tin cay vao khoa.
gpg --show-keys --with-fingerprint KEYS

# Nhap khoa cong khai da kiem tra nguon va fingerprint.
gpg --import KEYS

# Kiem tra chu ky tren DUNG file archive da tai.
gpg --verify \
    apache-ant-X.Y.Z-bin.zip.asc \
    apache-ant-X.Y.Z-bin.zip
~~~

Sau khi chạy `gpg --verify`, hãy đọc thông tin người ký và **fingerprint** của khóa đã dùng, sau đó đối chiếu với thông tin người phát hành được xác minh qua kênh đáng tin cậy độc lập. Một dòng `Good signature` chỉ khẳng định chữ ký khớp dữ liệu **với khóa công khai đang có**. Nếu khóa công khai cũng do kẻ tấn công cung cấp, phép kiểm tra toán học có thể thành công mà nguồn phát hành vẫn giả mạo.

GPG có thể in cảnh báo chưa thiết lập mức tin cậy của khóa dù chữ ký hợp lệ. Đừng bỏ qua điều đó; phân biệt rõ **chữ ký hợp lệ về kỹ thuật** và **đã xác thực đúng khóa của người phát hành**.

Nếu không tìm thấy chữ ký hoặc không xác minh được fingerprint, hãy xử lý theo chính sách của dự án: không cho gói đi tiếp vào pipeline phát hành cho đến khi có nguồn tin cậy hoặc một hình thức xác minh tương đương đã được phê duyệt.

### 3.4. Kiểm tra bản Ant thực sự đang chạy

Đôi khi máy đã cài nhiều phiên bản Ant và hệ thống chạy một bản khác với file vừa xác minh. Sau khi cài đặt bản đã tin cậy, kiểm tra:

~~~bash
command -v ant
ant -version
printf 'ANT_HOME=%s\n' "$ANT_HOME"
~~~

Trên Windows PowerShell:

~~~powershell
Get-Command ant | Format-List Source
ant -version
Write-Output "ANT_HOME=$env:ANT_HOME"
~~~

Các lệnh này giúp xác định launcher và phiên bản nhìn thấy từ `PATH`; chúng **không thay thế** kiểm tra checksum/chữ ký của gói cài đặt. Với môi trường CI, nên trỏ rõ đường dẫn Ant đã được cài từ artifact đã xác minh, thay vì dựa vào một cài đặt ngẫu nhiên của máy runner.

## 4. Xác minh JAR mở rộng: nơi Ant có thể nạp mã

Ant hỗ trợ nhiều cách bổ sung task và type:

- Đặt JAR vào thư mục `lib` của bản cài Ant, thường là `ANT_HOME/lib`.
- Đặt JAR vào thư mục thư viện người dùng, thường là `~/.ant/lib`.
- Thêm thư viện bằng tham số dòng lệnh `-lib`.
- Chỉ định `classpath` hoặc `classpathref` khi khai báo `<taskdef>` hay `<typedef>`.

Các vị trí đó thuộc **bề mặt thực thi** của bản build. Vì vậy cần xác minh từng JAR ở các vị trí này, kể cả khi không có khai báo tải dependency rõ ràng trong `build.xml`.

### 4.1. Sử dụng nguồn xác định và version cố định

Giả sử một custom Ant task được phát hành thành tệp:

~~~text
vendor-task-2.4.1.jar
~~~

Một bản ghi nguồn có ích nên bao gồm:

| Trường | Giá trị minh họa |
|---|---|
| Tên | `vendor-task` |
| Phiên bản | `2.4.1` |
| Nguồn tải | URL HTTPS của nhà phát hành/kho artifact được phê duyệt |
| Dấu vân tay byte | SHA-256 hoặc SHA-512 của JAR cụ thể |
| Chữ ký (nếu có) | Tệp chữ ký và fingerprint khóa của nhà phát hành |
| Mục đích | Task tạo mã trong build |
| Vị trí sử dụng | `tools/antlib/vendor-task-2.4.1.jar` |
| Người/phương thức phê duyệt | Quy trình review trong dự án |

Tên, phiên bản và hash ở đây chỉ minh họa một **mẫu quản lý**, không phải thông tin về một JAR thật. Không suy ra nguồn gốc từ tên file hoặc trường `Implementation-Vendor` bên trong manifest vì chính người tạo JAR có thể viết các trường này.

### 4.2. Bảng kiểm tra thủ công với JDK

Với JAR đã tải về:

~~~bash
sha256sum tools/antlib/vendor-task-2.4.1.jar

# Liet ke class va resource trong JAR.
jar tf tools/antlib/vendor-task-2.4.1.jar

# Chi kiem tra chu ky JAR neu nha phat hanh co ky theo co che JAR signing.
jarsigner -verify -verbose -certs tools/antlib/vendor-task-2.4.1.jar
~~~

Trên macOS có thể thay `sha256sum` bằng `shasum -a 256`; trên Windows dùng:

~~~powershell
Get-FileHash -LiteralPath '.\tools\antlib\vendor-task-2.4.1.jar' -Algorithm SHA256
~~~

`jar tf` chỉ liệt kê các mục trong JAR, hữu ích khi phát hiện nội dung bất thường hoặc thiếu tệp dự kiến; **không chứng minh** nhà phát hành đáng tin.

`jarsigner -verify` chỉ có ý nghĩa về chữ ký JAR nếu artifact thực sự được ký bằng cơ chế Java JAR signing. Một JAR không có chữ ký JAR không tự động là mã độc; có thể nhà phát hành dùng chữ ký PGP bên ngoài `.asc` hoặc quy trình xác minh khác. Ngược lại, một chữ ký JAR hợp lệ cũng cần được xem xét chứng chỉ, danh tính người ký và tình trạng tin cậy phù hợp. Đừng nhầm `jar.asc` được GPG xác minh với chữ ký nhúng trong `META-INF/` của JAR.

### 4.3. Chỉ nạp task sau khi đã xác minh

Cấu trúc có lợi cho dự án:

~~~text
project/
├── build.xml
├── scripts/
│   └── verify-sources.sh       # Buoc bootstrap ngoai Ant neu can
├── tools/
│   └── antlib/
│       └── vendor-task-2.4.1.jar
├── verification/
│   └── approved-artifacts.txt
└── src/
~~~

Một ví dụ khái niệm trong `build.xml`:

~~~xml
<project name="secure-ant-example" default="use-extension">
    <property name="extension.jar"
              location="tools/antlib/vendor-task-2.4.1.jar"/>

    <target name="verify-extension">
        <!-- Gia tri truyen tu manifest duoc review hoac CLI da tin cay. -->
        <fail unless="extension.expected.sha256"
              message="Thieu SHA-256 da duoc phe duyet cho extension"/>

        <available file="${extension.jar}"
                   type="file"
                   property="extension.jar.present"/>
        <fail unless="extension.jar.present"
              message="Khong co file extension JAR"/>

        <checksum file="${extension.jar}"
                  algorithm="SHA-256"
                  property="extension.actual.sha256"/>

        <condition property="extension.hash.ok">
            <equals arg1="${extension.actual.sha256}"
                    arg2="${extension.expected.sha256}"
                    casesensitive="false"
                    trim="true"/>
        </condition>

        <fail unless="extension.hash.ok"
              message="Hash extension JAR khong khop; dung build"/>
    </target>

    <target name="use-extension" depends="verify-extension">
        <!-- Thay class va ten task bang extension thuc te. -->
        <taskdef name="vendorTask"
                 classname="example.vendor.ant.VendorTask"
                 classpath="${extension.jar}"/>
        <vendorTask/>
    </target>
</project>
~~~

Đây là **mẫu minh họa cho JAR/task có thật ở dự án**; tên class `example.vendor.ant.VendorTask` và phiên bản JAR là giả định. Giá trị `extension.expected.sha256` phải được cấp từ một bản ghi đã kiểm duyệt, chẳng hạn property file được quản lý hoặc tham số `-Dextension.expected.sha256=...`. Không lấy “expected” bằng cách tự tính lại từ JAR chưa kiểm tra ở ngay bước đó.

Ant chạy `verify-extension` trước `use-extension` do quan hệ `depends`. Sau khi hash khớp, JAR mới được dùng trong `taskdef`. Tuy nhiên, cách này chỉ bảo vệ khi JAR **chưa được nạp từ nơi khác**; nếu extension đã bị đặt trong `ANT_HOME/lib` hoặc `~/.ant/lib`, cần kiểm tra nó **trước khi khởi động Ant**.

### 4.4. Thu hẹp thư viện nạp lúc khởi động

Các tùy chọn lệnh có thể hữu ích trong môi trường đã được kiểm soát:

~~~bash
ant -nouserlib -noclasspath -lib tools/antlib build
~~~

Ý nghĩa:

- `-nouserlib`: không lấy thêm JAR từ thư mục thư viện người dùng `~/.ant/lib`.
- `-noclasspath`: không lấy thêm từ biến môi trường `CLASSPATH` theo cơ chế Ant.
- `-lib tools/antlib`: bổ sung các JAR/classes được chỉ định từ đường dẫn tin cậy.

**Quan trọng:** `-lib` bổ sung thư viện chứ không cô lập hoàn toàn Ant khỏi thư viện đã có trong `ANT_HOME/lib`. Nếu muốn giảm rủi ro bị nạp nhầm, hãy dùng bản Ant đã xác minh và quản lý cả `ANT_HOME/lib`; tránh dùng JAR tùy ý từ thư mục home trên runner dùng chung. Thư mục được cấp cho `-lib` cũng phải chứa **chỉ** các JAR đã xác minh.

Để xem thông tin chẩn đoán cài đặt, có thể dùng `ant -diagnostics` trong môi trường nội bộ. Kết quả có thể chứa đường dẫn và thông tin cấu hình của máy; đừng tự động đưa toàn bộ đầu ra lên log công khai.

## 5. Xác minh dependency biên dịch và chạy

Trong dự án Ant, dependency có thể đến từ nhiều mô hình:

1. JAR được lưu cùng repository trong `lib/`.
2. JAR được CI tải xuống trước rồi đưa vào thư mục `lib/` hoặc cache.
3. JAR được giải quyết qua Apache Ivy, Maven repository hoặc công cụ quản lý khác.
4. Dependency bắc cầu: thư viện A phụ thuộc vào B, C; các JAR này không nhất thiết được liệt kê trực tiếp trong `build.xml`.

Xác minh chỉ các dependency trực tiếp là chưa đủ. Nếu bản build nạp một JAR bắc cầu, JAR đó cũng cần được quản lý nguồn, phiên bản và nội dung.

### 5.1. Pin phiên bản bằng tọa độ đầy đủ

Với hệ sinh thái Maven, một artifact thường được định danh bằng:

~~~text
groupId : artifactId : version
~~~

Ví dụ minh họa:

~~~text
org.apache.commons : commons-lang3 : 3.14.0
~~~

Đường dẫn Maven tương ứng có thể có dạng:

~~~text
org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar
~~~

Tọa độ xác định **bản phát hành được yêu cầu**. Hash xác định **byte của file thực sự được nhận**. Hai lớp kiểm soát này bổ sung cho nhau, vì một file có tên phù hợp vẫn có thể bị thay thế nếu kho, proxy, cache hoặc quy trình sao chép bị xâm phạm.

Đừng dùng:

~~~text
latest.release
latest.integration
1.+
[1.0,)
SNAPSHOT (cho artifact phat hanh can tinh lap lai)
~~~

trong chuỗi build cần cố định phiên bản. Các mẫu này minh họa những cách chọn phiên bản động hoặc thay đổi theo thời gian; cơ chế cụ thể tùy công cụ quản lý dependency.

### 5.2. Chỉ tải từ repository được phê duyệt

Maven Central có endpoint HTTPS chính thức:

~~~text
https://repo.maven.apache.org/maven2/
~~~

Với dependency nội bộ, dùng artifact repository do tổ chức kiểm soát và cấu hình quyền truy cập phù hợp. Không thêm một repository lạ chỉ để “lấy được JAR” sau khi repository chính bị lỗi. Nếu cùng tọa độ có trên nhiều repository, thứ tự resolver hoặc chính sách của công cụ có thể quyết định bản nào được chọn; đó là nguồn gây **nhầm lẫn nguồn dependency**.

Một bản ghi dependency nên giữ ít nhất:

~~~text
groupId / org
artifactId / name
version
packaging / classifier (neu co)
repository / nguon duoc phe duyet
SHA-256 hoac SHA-512
ly do su dung
trang thai review
~~~

Các file `.sha1`, `.md5` trong repository cũ có thể hỗ trợ phát hiện lỗi truyền tải nhưng không nên dùng làm kiểm tra bảo mật duy nhất khi cần chống thay thế có chủ đích. Ưu tiên SHA-256/SHA-512, chữ ký đáng tin cậy khi có và chính sách artifact repository.

### 5.3. Ví dụ kiểm tra dependency trước khi biên dịch

Giả sử có JAR `verified-libs/commons-lang3-3.14.0.jar` và file cấu hình được quản lý `verification/checksums.properties`:

~~~properties
# Gia tri ben duoi la PLACEHOLDER, can thay bang SHA-256 that da xac minh.
commons.lang3.expected.sha256=REPLACE_WITH_APPROVED_64_HEX_SHA256
~~~

`build.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="dependency-check" default="compile" basedir=".">

    <property name="deps.dir" location="verified-libs"/>
    <property name="classes.dir" location="build/classes"/>
    <property file="verification/checksums.properties"/>

    <target name="verify-dependencies">
        <fail unless="commons.lang3.expected.sha256"
              message="Chua khai bao SHA-256 duoc phe duyet"/>

        <available
            file="${deps.dir}/commons-lang3-3.14.0.jar"
            type="file"
            property="commons.lang3.present"/>
        <fail unless="commons.lang3.present"
              message="Thieu commons-lang3-3.14.0.jar"/>

        <checksum
            file="${deps.dir}/commons-lang3-3.14.0.jar"
            algorithm="SHA-256"
            property="commons.lang3.actual.sha256"/>

        <condition property="commons.lang3.verified">
            <equals arg1="${commons.lang3.actual.sha256}"
                    arg2="${commons.lang3.expected.sha256}"
                    casesensitive="false"
                    trim="true"/>
        </condition>

        <fail unless="commons.lang3.verified"
              message="Dependency hash khong khop: commons-lang3"/>
    </target>

    <target name="compile" depends="verify-dependencies">
        <mkdir dir="${classes.dir}"/>

        <javac srcdir="src"
               destdir="${classes.dir}"
               includeantruntime="false">
            <classpath>
                <pathelement
                    location="${deps.dir}/commons-lang3-3.14.0.jar"/>
            </classpath>
        </javac>
    </target>
</project>
~~~

Sau khi người phụ trách đã xác minh và ghi đúng hash thực vào property file, thực hiện:

~~~bash
ant compile
~~~

Ant tính SHA-256 từ JAR đang có trên đĩa. Nếu khác hash đã phê duyệt, task `<fail>` dừng build **trước khi** JAR được đưa vào classpath của `javac`. Với nhiều dependency, có thể lặp lại cơ chế này hoặc tạo một manifest digest và script bootstrap độc lập để kiểm tra toàn bộ artifact.

Ví dụ trên minh họa kiểm tra integrity ở mức build; để đáp ứng yêu cầu chuỗi cung ứng, còn cần kiểm soát **ai có quyền thay đổi** file chứa hash. Nếu một thay đổi không được review có thể sửa đồng thời JAR và `checksums.properties`, cơ chế đối chiếu hash có thể bị vượt qua.

### 5.4. Dependency bắc cầu với Apache Ivy

Ant là công cụ build; nó không tự động cung cấp toàn bộ cơ chế giải quyết dependency bắc cầu giống Maven. **Apache Ivy** là một công cụ có thể tích hợp với Ant để giải quyết và quản lý dependency.

Ví dụ cấu hình đơn giản của `ivy.xml`:

~~~xml
<ivy-module version="2.0">
    <info organisation="example.org" module="sample-app"/>

    <dependencies>
        <dependency org="org.apache.commons"
                    name="commons-lang3"
                    rev="3.14.0"/>
    </dependencies>
</ivy-module>
~~~

Ví dụ `ivysettings.xml` dùng endpoint Maven Central được chỉ định rõ:

~~~xml
<ivysettings>
    <settings defaultResolver="central"/>
    <resolvers>
        <ibiblio name="central"
                 m2compatible="true"
                 root="https://repo.maven.apache.org/maven2/"/>
    </resolvers>
</ivysettings>
~~~

Đây là **cấu hình minh họa**, yêu cầu đã cài và khai báo Ivy với Ant; không phải tính năng tự xuất hiện trong Ant thuần. `rev="3.14.0"` cố định revision được yêu cầu nhưng chưa phải bản khóa đầy đủ của mọi dependency bắc cầu và mọi file đã tải.

Đối với một pipeline cần tái lập cao:

- Quản lý phiên bản cụ thể cho cả dependency trực tiếp và bản đã giải quyết bắc cầu.
- Lưu danh mục những JAR thực sự tham gia build, gồm tọa độ và hash.
- Dùng repository/mirror được phê duyệt và hạn chế resolver không rõ nguồn.
- Kiểm tra dữ liệu từ cache: một lần tải hợp lệ trước đây không chứng minh file cache hiện tại chưa bị thay thế.
- Bảo vệ và ghi nhận sự thay đổi của file khai báo dependency, repository settings và manifest digest.

Tùy phiên bản và công cụ, khả năng kiểm tra checksum của resolver có thể khác nhau. Checksum do cùng máy chủ không đáng tin cung cấp chỉ giải quyết một phần bài toán; đừng mặc định “download thành công” nghĩa là dependency đã được xác minh toàn diện.

## 6. Lập danh mục và khóa nội dung artifact

Một cách quản lý dễ review là giữ bảng kê phụ thuộc cùng dự án hoặc trong hệ thống artifact đã được phê duyệt:

| Loại | Tên/tọa độ | Phiên bản | Đường dẫn/kho | Hash đã duyệt | Sử dụng ở đâu |
|---|---|---|---|---|---|
| Công cụ | Apache Ant | `X.Y.Z` | Apache official release | SHA-512 + xác minh chữ ký | CI bootstrap |
| Antlib | `vendor-task` | `2.4.1` | Kho nhà cung cấp | SHA-256; chữ ký nếu có | `taskdef` |
| Dependency | `org.apache.commons:commons-lang3` | `3.14.0` | Maven Central/mirror duyệt | SHA-256 | `javac`/runtime |
| Công cụ ngoài | JDK | Bản được duyệt | Nhà phân phối JDK | Digest/chữ ký nhà cung cấp | JVM chạy Ant |

Mỗi bản ghi nên trỏ tới bằng chứng kiểm tra, ví dụ URL chính thức, dấu vân tay người ký, phiếu review cập nhật phiên bản. Với artifact nội bộ, nên có quy tắc **không ghi đè byte của một phiên bản đã phát hành**. Nếu nội dung thay đổi, phát hành phiên bản/nhãn mới, cập nhật hash và review lại.

Thay vì tải lại tùy ý ở mỗi lần build, CI có thể sử dụng một kho artifact nội bộ chỉ cho phép nhập sau khi kiểm tra. Tuy nhiên, việc nằm trong mirror nội bộ không tự động làm một JAR trở nên đáng tin: quy trình nhập, quyền ghi và lưu trữ của mirror cũng là một phần của chuỗi tin cậy.

## 7. Kiểm soát thư mục `lib`, classpath và cache

Một số nguồn phụ thuộc “ẩn” dễ bị bỏ qua:

~~~text
ANT_HOME/lib/             # JAR phan phoi cua Ant va thu vien bo sung
~/.ant/lib/               # JAR o user home
ANT_OPTS                  # Tham so JVM cua Ant
CLASSPATH                 # Bien moi truong co the tac dong classpath
ant -lib ...              # Thu vien chi dinh qua dong lenh
build.xml <taskdef ...>   # Classpath dinh nghia custom task
project/lib/              # Thu vien trong repository
Ivy / repository cache    # File co the duoc tai tu truoc
~~~

Trong CI:

1. Dùng image/runner được quản lý, có JDK và Ant đã xác minh, quyền ghi vào thư mục công cụ bị giới hạn.
2. Xác định rõ các thư viện bổ sung được phép nạp.
3. Không dựa vào cache của một người dùng hoặc một runner không được kiểm soát.
4. Ghi lại phiên bản Ant/JDK và tập JAR được dùng cho bản build phát hành.
5. Cảnh giác với tham số môi trường hoặc init script có thể chèn hành vi ngoài `build.xml`.

Có thể dùng `ant -nouserlib -noclasspath` để loại bỏ hai đường nạp ngoài dự kiến; song vẫn cần kiểm tra phần `ANT_HOME/lib` và các `-lib` được cấp chủ động. Không nên coi một tùy chọn lệnh là thay thế cho quản lý quyền của môi trường build.

Đặc biệt, nếu tác vụ trước khi verify đã dùng `taskdef` từ JAR không kiểm tra, thì hash check diễn ra **quá muộn**. Hãy lập quan hệ phụ thuộc hoặc tách bootstrap để bảo đảm thứ tự xác minh.

## 8. Khi checksum, chữ ký hoặc nguồn tải có vấn đề

### 8.1. Checksum không khớp

**Triệu chứng:** SHA-256/SHA-512 tự tính khác giá trị đã được phê duyệt.

Khả năng: file tải chưa đầy đủ, tải nhầm phiên bản, cache bị hỏng, mirror trả sai dữ liệu hoặc có thay thế không hợp lệ.

**Cách xử lý:** dừng build; không sửa hash “expected” cho khớp file vừa tải. Xóa file nghi vấn trong vùng cách ly, lấy lại từ nguồn đã kiểm tra, so sánh bằng chứng và cập nhật phiên bản chỉ thông qua review. Nếu lỗi xảy ra trong kho nội bộ, kiểm tra log và quyền ghi kho.

### 8.2. Chữ ký hợp lệ nhưng khóa chưa đáng tin

**Triệu chứng:** GPG báo chữ ký toán học hợp lệ nhưng chưa thiết lập mức tin cậy, hoặc fingerprint khác với người ký dự kiến.

**Cách xử lý:** tìm fingerprint qua nguồn có thẩm quyền và kênh tin cậy độc lập; xác định đúng người phát hành. Không nhập một khóa mới từ cùng link lạ rồi coi việc chữ ký hợp lệ là bằng chứng đủ.

### 8.3. Task tự động tải dependency từ HTTP hoặc mirror lạ

**Triệu chứng:** log cho thấy URL không nằm trong danh sách phê duyệt, dùng HTTP thuần hoặc endpoint có tên gần giống kho chính thức.

**Cách xử lý:** cấu hình lại resolver về HTTPS và danh sách kho được duyệt, dừng lấy artifact qua fallback không kiểm soát. Đánh giá lại các JAR đã nằm trong cache từ nguồn này.

### 8.4. Một version nhưng hai máy có hai nội dung JAR

**Triệu chứng:** cùng tên `lib/example-1.0.jar` nhưng checksum khác nhau giữa developer và CI.

**Cách xử lý:** xác minh nguồn của từng file, xem artifact có bị ghi đè hoặc build lại nhưng giữ nguyên version không, dùng digest đã phê duyệt để xác định byte đúng. Không dựa vào tên file hoặc timestamp đơn thuần.

### 8.5. Chữ ký và hash đều đúng nhưng dependency vẫn có rủi ro

Kiểm tra nguồn gốc và integrity không đồng nghĩa với kiểm tra lỗ hổng bảo mật hoặc hành vi của mã nguồn. Dependency có thể là bản phát hành chính chủ nhưng chứa lỗ hổng đã biết. Cần thêm đánh giá advisories/CVE, phiên bản hỗ trợ, SBOM, giấy phép và quyền hoạt động của build runner theo nhu cầu dự án.

## 9. Quy trình cập nhật Ant và dependency an toàn

Ví dụ khi muốn nâng cấp một JAR hoặc Ant:

1. **Đề xuất thay đổi cụ thể:** tên artifact, phiên bản cũ/mới, lý do và dự án phát hành.
2. **Xác định nguồn:** đi từ website chính thức tới endpoint phát hành; tránh link do bên thứ ba gửi không được xác nhận.
3. **Tải và kiểm tra:** lấy artifact, checksum mạnh và chữ ký nếu có; xác minh fingerprint của người ký.
4. **Ghi nhận:** lưu tọa độ, URL nguồn, digest của byte thực tế, ngày kiểm tra, người review, ghi chú thay đổi.
5. **Kiểm tra trên môi trường cách ly:** build và test với đúng artifact đã được xác minh; cân nhắc quét lỗ hổng và kiểm tra license.
6. **Cập nhật manifest/version pin:** thay đổi file cấu hình và digest có review, tránh ghi đè nhầm một version cũ.
7. **Chạy pipeline phát hành:** nạp Ant/JAR từ kho đã quản lý và từ chối bất kỳ artifact nào lệch digest.
8. **Giữ bằng chứng:** lưu log xác minh ở mức cần thiết mà không làm lộ thông tin đăng nhập hoặc khóa bí mật.

Một thay đổi phiên bản có thể ảnh hưởng cả dependency bắc cầu, vì vậy quy trình cập nhật cần xem danh sách artifact **thực tế** sau resolution, không chỉ một dòng `rev="..."` vừa được sửa.

## 10. Ví dụ pipeline có bước xác minh trước khi gọi Ant

Một lược đồ CI tổng quát:

~~~text
Checkout source da review
        |
        v
Bootstrap JDK + Ant tu artifact da duyet
        |
        v
Verify Ant release checksum + chu ky / provenance
        |
        v
Verify cac JAR trong ANT_HOME/lib, antlib, project/lib
        |
        v
Resolve dependency tu kho allowlist
        |
        v
Verify digest toan bo dependency da resolve
        |
        v
ant -nouserlib -noclasspath -f build.xml build
        |
        v
Test + kiem tra artifact dau ra + luu ket qua build
~~~

Để hình dung bootstrap đơn giản, giả sử một môi trường đã chuẩn bị tệp manifest có checksum SHA-256 được phê duyệt **từ trước**:

~~~text
# verification/approved.sha256
# Moi dong theo dinh dang "hash  duong-dan".
# Thay boi cac hash thuc te da review; khong dung hash tu tinh tu file nghi van.
<64-hex-sha256>  tools/antlib/vendor-task-2.4.1.jar
<64-hex-sha256>  verified-libs/commons-lang3-3.14.0.jar
~~~

Sau khi thay placeholder bằng mã hash thật, môi trường Linux có `sha256sum` có thể kiểm tra:

~~~bash
sha256sum --check verification/approved.sha256
ant -nouserlib -noclasspath -f build.xml build
~~~

Đây là **minh họa cơ chế**: các dòng chứa `<64-hex-sha256>` chưa phải digest hợp lệ; phải thay bằng 64 ký tự hex thật trước khi sử dụng. File manifest cần được review và bảo vệ quyền sửa. Trên macOS có thể dùng công cụ phù hợp để kiểm tra SHA-256; trên Windows có thể viết bước tương đương với `Get-FileHash`. Bước này nên chạy trước khi Ant nạp các JAR được liệt kê.

Nếu CI sử dụng Ant tải về mỗi lần chạy, cần bổ sung phần xác minh gói Ant, ví dụ SHA-512 và PGP như phần đầu bài, **trước khi** trỏ `PATH`/`ANT_HOME` đến bản vừa tải.

## 11. Những hiểu lầm dễ gây mất an toàn

**“Tải qua HTTPS nên chắc chắn là JAR chính chủ.”** HTTPS xác nhận kết nối tới máy chủ theo hệ thống chứng chỉ, nhưng không chứng minh JAR bên trong do đúng người phát hành tạo, không ngăn một mirror hợp lệ bị xâm phạm và không tự kiểm tra bản phát hành.

**“Có file `.sha1` là đủ.”** SHA-1 và MD5 không còn phù hợp làm cơ chế chống thay thế có chủ đích trong thiết kế bảo mật mới. Dùng SHA-256/SHA-512 và chữ ký đáng tin khi có.

**“Hash khớp nghĩa là an toàn tuyệt đối.”** Hash chỉ đối chiếu byte với giá trị đã biết. Nếu bản giá trị chuẩn cũng không được bảo vệ, hoặc chính bản phát hành có lỗ hổng, hash không giải quyết vấn đề.

**“JAR đã có trong `~/.ant/lib` nên không cần xem nữa.”** Đây chính là nơi có thể chứa phần mở rộng được Ant nạp ngoài kiểm soát của repository. Trên máy phát triển hay runner chung, cần thống kê và áp chính sách.

**“Version cố định tức là nội dung cố định.”** Thực tế một version trên repository không được bảo vệ có thể bị ghi đè, hoặc cache bị thay đổi. Cần pin cả version lẫn hash.

**“Kiểm tra hash trong target đầu tiên bảo vệ được Ant startup.”** Không đúng nếu JAR nghi vấn đã được Ant nạp trước khi target chạy. Thành phần bootstrap phải được xác minh ở bước độc lập trước khi khởi động.

**“JAR ký số thì không thể có mã độc.”** Chữ ký gắn byte với khóa ký; đánh giá độ tin cậy, danh tính nhà phát hành và kiểm tra rủi ro hành vi vẫn cần thiết.

## 12. Bài thực hành

### Bài 1 — Xác minh gói Ant

Chọn một phiên bản cụ thể từ trang Apache Ant chính thức. Tải archive, file `.sha512` và `.asc` nếu có. Thực hiện:

1. Tính SHA-512 bằng công cụ trên hệ điều hành đang dùng và so với file do Apache phát hành.
2. Lấy thông tin khóa ký từ kênh chính thức, kiểm tra fingerprint qua nguồn tin cậy và chạy `gpg --verify`.
3. Ghi lại nguồn tải, tên file, phiên bản, hash và fingerprint. Giải thích vì sao chỉ dùng `ant -version` là chưa đủ.

### Bài 2 — Phát hiện JAR bị thay đổi

Tạo một bản sao **trong thư mục thử nghiệm** của JAR đã kiểm tra, rồi cố ý thay đổi một byte trên bản sao. Tính lại SHA-256 của bản sao và so sánh với digest đã lưu.

Kết luận: đổi tên file không làm digest thay đổi, nhưng sửa nội dung byte làm digest không khớp. Không thử sửa file nằm trong kho dự án/CI đang sử dụng.

### Bài 3 — Chặn dependency trước khi compile

Áp dụng target `verify-dependencies` ở phần 5 vào một dự án nhỏ. Điền SHA-256 thật đã xác minh của dependency. Đổi JAR sang file khác cùng tên hoặc cố tình nhập sai digest và quan sát Ant dừng **trước** `<javac>`. Sau đó khôi phục JAR/digest đúng và chạy lại.

### Bài 4 — Kiểm tra thư viện nạp ngầm

Trên môi trường thử nghiệm, ghi lại:

~~~bash
ant -version
ant -diagnostics
ant -nouserlib -noclasspath -version
~~~

Đối chiếu đường dẫn Ant và các vị trí thư viện. Lưu ý không đăng công khai đầu ra chẩn đoán nếu nó chứa thông tin hệ thống hoặc cấu hình nội bộ. Trả lời: “Một file JAR trong thư mục nào có thể được nạp trước target xác minh đầu tiên?”

### Bài 5 — Đánh giá danh sách dependency bắc cầu

Nếu dự án có Ivy hoặc resolver khác, xuất danh sách các artifact đã giải quyết (kể cả transitive). Với từng artifact, ghi lại repository, version và SHA-256. Đánh dấu những artifact thiếu bằng chứng nguồn gốc hoặc được chọn qua version động. Thử chế độ build không mạng với cache đã được phê duyệt để xem còn dependency nào được lấy ngầm.

## 13. Ghi nhớ khi áp dụng cho bản build phát hành

Một chuỗi build đáng tin cậy bắt đầu từ **bản Ant được xác minh** và tiếp tục xuyên suốt **JAR mở rộng, classpath, dependency trực tiếp và bắc cầu**. Cần cố định nguồn tải, phiên bản, digest và chữ ký khi có; kiểm soát ai được thay đổi manifest; đồng thời đặt phép kiểm tra **trước thời điểm JAR được thực thi**. Sau khi chứng minh đúng nguồn và đúng byte, vẫn cần đánh giá tính phù hợp của dependency về bảo mật, giấy phép và khả năng bảo trì.

### Tài liệu tham khảo

- [Apache Ant — Trang chính thức](https://ant.apache.org/)
- [Apache Ant — Binary distributions](https://ant.apache.org/bindownload.cgi)
- [Apache Ant Manual — Checksum task](https://ant.apache.org/manual/Tasks/checksum.html)
- [Apache Ant Manual — Taskdef task](https://ant.apache.org/manual/Tasks/taskdef.html)
- [Apache Ant Manual — Command-line options](https://ant.apache.org/manual/running.html)
- [Apache Ivy — Documentation](https://ant.apache.org/ivy/)
- [Apache Software Foundation — Release distribution and verification](https://www.apache.org/dev/release.html)
- [Maven Central — Repository](https://repo.maven.apache.org/maven2/)
