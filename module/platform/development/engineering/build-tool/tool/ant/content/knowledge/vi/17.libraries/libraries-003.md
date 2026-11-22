# Tải tài nguyên bằng get và xác minh checksum

## Mục tiêu

Trong build Java, Ant thường cần tải thư viện, công cụ hoặc gói tài nguyên từ một máy chủ trước khi biên dịch và đóng gói. Task `get` thực hiện việc tải nội dung từ URL xuống hệ thống tệp. Sau khi tải, task `checksum` có thể tính hoặc xác minh mã băm của tệp để phát hiện dữ liệu bị hỏng hoặc không khớp với giá trị mong đợi.

Một quy trình tải đáng tin cậy thường có các bước:

1. Xác định URL, phiên bản và tên tệp đích.
2. Tạo thư mục lưu trữ và tải tài nguyên bằng `get`.
3. Lấy checksum được công bố cho đúng phiên bản tài nguyên.
4. Dùng `checksum` để tính lại mã băm của tệp đã tải.
5. So sánh với checksum mong đợi và dừng build nếu không khớp.
6. Chỉ đưa tài nguyên đã xác minh vào classpath hoặc bước đóng gói tiếp theo.

`get` và `checksum` giải quyết hai việc khác nhau. Tải thành công chỉ cho biết Ant đã nhận được dữ liệu từ URL; nó không chứng minh nội dung đúng với bản phát hành dự kiến. Ngược lại, tính checksum mà không có giá trị chuẩn đáng tin cậy chỉ tạo ra dấu vân tay của tệp hiện tại, chưa xác minh được nguồn gốc của nó.

## 1. Tải một tệp bằng task get

### 1.1. Cấu trúc cơ bản

Task `get` nhận URL nguồn qua thuộc tính `src` và đường dẫn lưu kết quả qua thuộc tính `dest`:

~~~xml
<get src="https://downloads.example.org/tools/tool.zip"
     dest="build/downloads/tool.zip"/>
~~~

- `src` là URL của tài nguyên cần tải.
- `dest` là tệp hoặc thư mục đích trên máy đang chạy Ant.

Nếu `dest` là đường dẫn tệp, Ant lưu nội dung vào đúng tệp đó. Nếu tải nhiều URL bằng resource collection, `dest` phải là thư mục để Ant lưu từng tài nguyên.

Nên khai báo thư mục tải bằng property để dùng lại:

~~~xml
<property name="download.dir" location="build/downloads"/>
<property name="tool.url" value="https://downloads.example.org/tools/tool.zip"/>
<property name="tool.file" location="build/downloads/tool.zip"/>

<target name="download">
    <mkdir dir="${download.dir}"/>
    <get src="${tool.url}" dest="${tool.file}"/>
</target>
~~~

Task `mkdir` bảo đảm thư mục đích đã tồn tại trước khi ghi tệp. Việc đặt URL, thư mục và tên tệp thành property giúp thay đổi phiên bản hoặc vị trí lưu mà không phải sửa nhiều dòng trong buildfile.

### 1.2. URL và các giao thức

Task Get sử dụng các URL scheme được Java runtime hỗ trợ. Những giao thức thường gặp gồm HTTP, HTTPS, FTP và JAR URL. Với tài nguyên tải từ Internet hoặc kho lưu trữ nội bộ, HTTPS thường là lựa chọn phù hợp để bảo vệ dữ liệu trên đường truyền.

Ví dụ:

~~~xml
<get src="https://repo.example.org/releases/library-2.4.jar"
     dest="build/downloads/library-2.4.jar"/>
~~~

Tên tệp đích không bắt buộc phải giống tên cuối của URL. Có thể đặt tên theo quy ước của dự án để dễ tham chiếu trong các target sau.

Nếu URL có query string hoặc tên tài nguyên không rõ ràng, hãy chỉ định `dest` là đường dẫn tệp cụ thể thay vì dựa vào tên được suy ra từ URL.

### 1.3. Tải nhiều URL

Có thể truyền nhiều URL thông qua resource collection lồng trong task get:

~~~xml
<get dest="build/downloads">
    <url url="https://repo.example.org/lib/core-2.4.jar"/>
    <url url="https://repo.example.org/lib/adapter-2.4.jar"/>
    <url url="https://repo.example.org/lib/codec-2.4.jar"/>
</get>
~~~

Ant tải các tài nguyên vào thư mục đích. Theo mặc định, tên tệp được lấy từ phần cuối đường dẫn URL. Khi cần đổi tên hoặc tổ chức lại đường dẫn đầu ra, có thể dùng mapper lồng trong get.

Với một danh sách thư viện có phiên bản cố định, cách khai báo từng URL rõ ràng giúp người đọc biết chính xác build phụ thuộc vào những artifact nào. Với danh sách lớn hoặc thay đổi thường xuyên, có thể quản lý URL trong một tệp cấu hình và tạo resource collection phù hợp.

## 2. Các tùy chọn thường dùng của get

### 2.1. Hiển thị tiến trình tải

Thuộc tính `verbose` bật thông tin tiến trình:

~~~xml
<get src="${tool.url}"
     dest="${tool.file}"
     verbose="true"/>
~~~

Khi bật verbose, Ant hiển thị dấu chấm theo lượng dữ liệu tải được. Điều này hữu ích khi tải tệp lớn và muốn biết task vẫn đang hoạt động.

Thuộc tính `quiet` giới hạn log chủ yếu ở lỗi. Khi chẩn đoán build, nên giữ log đủ rõ để nhận biết URL nào thất bại và task đang tải tệp nào.

### 2.2. Xử lý lỗi tải

Mặc định, lỗi tải là lỗi build. Thuộc tính `ignoreerrors` có thể thay đổi hành vi đó:

~~~xml
<get src="${tool.url}"
     dest="${tool.file}"
     ignoreerrors="false"/>
~~~

Với thư viện bắt buộc để biên dịch hoặc đóng gói, hãy để lỗi tải làm build thất bại. Nếu bật `ignoreerrors="true"`, Ant ghi nhận lỗi nhưng tiếp tục chạy; target sau đó có thể gặp lỗi khó hiểu vì tệp phụ thuộc không tồn tại hoặc không đầy đủ.

Chỉ bỏ qua lỗi khi tài nguyên thực sự tùy chọn và các target sau đã có cách xử lý trường hợp không có tệp đó.

### 2.3. Số lần thử lại và thời gian tải tối đa

Task get hỗ trợ thuộc tính `retries` và `maxtime`:

~~~xml
<get src="${tool.url}"
     dest="${tool.file}"
     retries="3"
     maxtime="300"/>
~~~

- `retries` quy định số lần thử mở URL. Giá trị mặc định là 3.
- Giá trị `retries="1"` có nghĩa là chỉ thử một lần, không thử lại.
- Giá trị `retries="0"` có nghĩa là không thực hiện lần thử tải nào.
- `maxtime` giới hạn thời gian cho một lần tải, tính bằng giây. Giá trị 0 mặc định nghĩa là không giới hạn.

Thử lại giúp xử lý gián đoạn mạng tạm thời. Giới hạn thời gian giúp build không chờ vô hạn khi máy chủ hoặc kết nối bị treo. Chọn thời gian phù hợp với kích thước tệp và tốc độ mạng dự kiến.

### 2.4. Chỉ tải khi bản trên máy chủ mới hơn

Thuộc tính `usetimestamp="true"` cho phép Ant so sánh timestamp của bản cục bộ với timestamp từ máy chủ HTTP:

~~~xml
<get src="${tool.url}"
     dest="${tool.file}"
     usetimestamp="true"/>
~~~

Nếu tệp cục bộ chưa tồn tại, Ant tải tài nguyên. Nếu tệp đã tồn tại và bản từ máy chủ không mới hơn theo timestamp HTTP, việc tải có thể được bỏ qua. Khi tải, timestamp của tệp cục bộ được đặt theo timestamp từ máy chủ.

Tùy chọn này chỉ hoạt động với tải xuống qua HTTP. Nó phụ thuộc vào metadata timestamp do máy chủ cung cấp, không xác minh nội dung bằng checksum.

Không dùng timestamp như bằng chứng rằng tệp cục bộ đúng phiên bản. Một máy chủ có thể không cung cấp timestamp đáng tin cậy, hoặc nội dung thay đổi mà timestamp không phản ánh như mong đợi. Nếu tính toàn vẹn quan trọng, vẫn cần xác minh checksum sau khi tải.

### 2.5. Bỏ qua nếu tệp đích đã tồn tại

Thuộc tính `skipexisting="true"` yêu cầu Ant bỏ qua tệp đã có trên hệ thống tệp:

~~~xml
<get src="${tool.url}"
     dest="${tool.file}"
     skipexisting="true"/>
~~~

Đây là kiểm tra sự tồn tại đơn giản. Ant không xác minh tệp hiện có có đúng nội dung, đúng phiên bản hoặc đúng checksum hay không.

Nếu thư mục tải có thể chứa tệp cũ hoặc bị hỏng, không nên dựa vào skipexisting như một cơ chế xác minh. Có thể tải lại theo timestamp hoặc chính sách ghi đè thích hợp, sau đó luôn chạy checksum.

### 2.6. Cache HTTP và gzip

Một số tùy chọn khác:

- `httpusecaches` điều khiển gợi ý sử dụng cache ở tầng `HttpURLConnection`; đây chỉ là gợi ý cho runtime và proxy, không bảo đảm cache luôn bị bật hoặc tắt.
- `tryGzipEncoding` cho phép Ant yêu cầu nội dung gzip khi máy chủ hỗ trợ và giải nén trong quá trình tải. Tùy chọn này có thể tự động giải nén các nội dung như `.tar.gz`; hãy cân nhắc tên tệp đầu ra và định dạng mong muốn.

Không bật các tùy chọn này chỉ để tăng tốc một cách mặc định. Hãy dùng khi hiểu rõ hành vi máy chủ, định dạng tài nguyên và cách task sau sử dụng tệp đã tải.

### 2.7. Xác thực và header HTTP

Get có thể gửi username/password theo Basic authentication. Cách xác thực này chỉ nên dùng qua HTTPS vì thông tin đăng nhập Basic không được mã hóa ở tầng cơ chế xác thực.

Có thể gửi header tùy chỉnh bằng phần tử `header`:

~~~xml
<get src="https://repo.example.org/private/tool.zip"
     dest="build/downloads/tool.zip">
    <header name="Authorization" value="Bearer TOKEN_VALUE"/>
</get>
~~~

Ví dụ chỉ minh họa cấu trúc. Không nên ghi token thật vào buildfile được commit vào repository. Hãy lấy bí mật từ hệ thống quản lý secret hoặc cơ chế cấp thông tin xác thực của môi trường build.

Từ Ant 1.10.13, thuộc tính `authenticateOnRedirect` điều khiển việc có gửi lại thông tin xác thực khi theo redirect sang địa chỉ mới hay không; mặc định là false. Chỉ bật khi đích redirect đã được tin cậy và việc chuyển tiếp thông tin xác thực là chủ đích.

## 3. Checksum là gì?

Checksum là giá trị băm được tính từ nội dung byte của một tệp. Cùng một thuật toán và cùng một nội dung sẽ tạo ra cùng một giá trị checksum; thay đổi nội dung thường làm giá trị băm thay đổi.

Checksum thường được dùng để:

- Phát hiện tệp tải xuống bị hỏng hoặc bị thay đổi.
- So sánh tệp cục bộ với giá trị được nhà phát hành công bố.
- Kiểm tra một thư viện đã lưu trong cache có còn đúng nội dung dự kiến không.
- Xác nhận tệp được sao chép hoặc chuyển giao không bị thay đổi ngoài ý muốn.

Checksum không tự mô tả tên thư viện, phiên bản, giấy phép hay nhà phát hành. Các thông tin đó cần được ghi riêng trong cấu hình dependency hoặc metadata của dự án.

### 3.1. Thuật toán băm

Task `checksum` mặc định dùng MD5 nếu không chỉ định thuật toán. Tuy nhiên, MD5 và SHA-1 không còn phù hợp cho các mục đích cần khả năng chống va chạm trong môi trường bảo mật.

Với tài nguyên mới, nên chọn SHA-256 hoặc SHA-512 nếu cả nhà phát hành và JDK hỗ trợ:

| Thuật toán | Độ dài digest | Khuyến nghị sử dụng |
|---|---:|---|
| MD5 | 128 bit | Tránh dùng cho kiểm tra bảo mật |
| SHA-1 | 160 bit | Tránh dùng cho kiểm tra bảo mật |
| SHA-256 | 256 bit | Lựa chọn phổ biến cho kiểm tra tính toàn vẹn |
| SHA-512 | 512 bit | Có thể dùng khi hệ thống công bố digest tương ứng |

Thuật toán dùng để xác minh phải giống thuật toán đã dùng để tạo checksum chuẩn. Không thể lấy digest SHA-256 rồi so sánh với giá trị MD5.

## 4. Dùng task checksum để tạo mã băm

### 4.1. Tạo tệp checksum bên cạnh tài nguyên

Cấu hình đơn giản:

~~~xml
<checksum file="build/downloads/tool.zip"
          algorithm="SHA-256"/>
~~~

Nếu không chỉ định `todir`, task ghi tệp checksum bên cạnh tài nguyên. Với thuật toán SHA-256, phần mở rộng mặc định được tạo dựa trên tên thuật toán. Có thể dùng `fileext` để quy định rõ phần mở rộng mong muốn:

~~~xml
<checksum file="build/downloads/tool.zip"
          algorithm="SHA-256"
          fileext=".sha256"/>
~~~

Ví dụ này tạo tệp checksum cạnh `tool.zip` với tên `tool.zip.sha256`. Nội dung mặc định chỉ chứa giá trị checksum.

### 4.2. Lưu checksum vào property

Nếu muốn dùng giá trị checksum trong buildfile thay vì ghi ra tệp:

~~~xml
<checksum file="build/downloads/tool.zip"
          algorithm="SHA-256"
          property="tool.sha256"/>
~~~

Sau task, Ant đặt giá trị digest vào property `tool.sha256`. Có thể in ra log để kiểm tra:

~~~xml
<echo message="SHA-256: ${tool.sha256}"/>
~~~

Cách này chỉ tính checksum của tệp hiện tại. Để xác minh, phải so sánh với giá trị chuẩn đã được cung cấp từ một nguồn đáng tin cậy.

### 4.3. Đặt thư mục chứa checksum

Thuộc tính `todir` quy định thư mục gốc để ghi tệp checksum:

~~~xml
<checksum file="build/downloads/tool.zip"
          todir="build/checksums"
          algorithm="SHA-256"
          fileext=".sha256"/>
~~~

Ant ghi checksum trong thư mục được chỉ định. Khi xác minh sau đó, phải dùng cùng cách tổ chức đường dẫn để task tìm đúng tệp checksum tương ứng.

## 5. Xác minh checksum từ tệp sidecar

### 5.1. Sidecar là gì?

Nhiều kho lưu trữ công bố một tệp checksum riêng bên cạnh artifact. Ví dụ:

~~~text
tool-2.4.1.zip
tool-2.4.1.zip.sha256
~~~

Tệp thứ hai là sidecar chứa checksum của tệp đầu tiên. Ant có thể so sánh checksum tính được với nội dung sidecar bằng thuộc tính `verifyproperty`.

Ví dụ:

~~~xml
<checksum file="build/downloads/tool-2.4.1.zip"
          algorithm="SHA-256"
          fileext=".sha256"
          verifyproperty="tool.checksum.matches"/>
~~~

Task sẽ tìm tệp checksum có tên `tool-2.4.1.zip.sha256`, tính lại SHA-256 của artifact rồi đặt property `tool.checksum.matches` thành `true` hoặc `false`.

Khi dùng `verifyproperty`, task không ghi checksum mới ra tệp hoặc property. Nó dùng nội dung tệp sidecar để xác minh.

Mặc định, định dạng checksum mong đợi là giá trị digest thuần. Nếu nhà phát hành cung cấp sidecar theo định dạng khác, chẳng hạn có thêm tên tệp trên cùng dòng, hãy cấu hình `format` hoặc `pattern` phù hợp với định dạng đó.

### 5.2. Dừng build nếu checksum không khớp

Task checksum đặt property kết quả thành chuỗi true hoặc false. Vì property false vẫn là một property đã tồn tại, không nên dùng `<fail unless="tool.checksum.matches">` để kiểm tra kết quả. Thuộc tính if/unless của fail kiểm tra sự tồn tại của property, không tự diễn giải giá trị boolean của nó.

Có thể dùng condition để tạo cờ lỗi:

~~~xml
<checksum file="build/downloads/tool.zip"
          algorithm="SHA-256"
          fileext=".sha256"
          verifyproperty="tool.checksum.matches"/>

<condition property="tool.checksum.failed">
    <equals arg1="${tool.checksum.matches}" arg2="false"/>
</condition>

<fail if="tool.checksum.failed"
      message="SHA-256 verification failed for tool.zip"/>
~~~

Nếu checksum đúng, property `tool.checksum.failed` không được thiết lập và target tiếp tục. Nếu checksum sai, cờ lỗi được thiết lập và task fail dừng build.

### 5.3. Sidecar phải khớp chính xác với tên và thuật toán

Nếu tải artifact `tool.zip` và sidecar `tool.zip.sha256`, cấu hình checksum phải dùng `fileext=".sha256"`.

Nếu sidecar trên máy có tên khác, task sẽ không tìm thấy đúng tệp. Nếu thuật toán khác, giá trị tính toán sẽ không khớp. Hãy kiểm tra:

- Tên artifact sau khi tải.
- Tên sidecar do máy chủ công bố.
- Phần mở rộng được chỉ định trong `fileext`.
- Thuật toán checksum.
- Định dạng nội dung sidecar.

Không đổi tên sidecar tùy tiện nếu chưa hiểu quy tắc đặt tên của kho lưu trữ.

## 6. Xác minh bằng checksum chuẩn lưu trong property

Không phải máy chủ nào cũng cung cấp sidecar theo định dạng mà task checksum có thể đọc trực tiếp. Một cách khác là lưu digest chuẩn trong tệp properties được quản lý cùng build:

**config/checksums.properties**

~~~properties
tool.sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
~~~

Ví dụ digest trên chỉ là chuỗi minh họa; phải thay bằng giá trị thực do nhà phát hành công bố.

Nạp tệp và xác minh:

~~~xml
<property file="config/checksums.properties"/>

<checksum file="build/downloads/tool.zip"
          algorithm="SHA-256"
          property="${tool.sha256}"
          verifyproperty="tool.checksum.matches"/>
~~~

Trong chế độ này, thuộc tính `property` của task checksum mang ý nghĩa đặc biệt: khi có `verifyproperty`, giá trị của `property` chính là checksum mong đợi, không phải tên property sẽ nhận checksum mới.

Vì vậy, cần viết `property="${tool.sha256}"` để truyền giá trị digest đã nạp. Không viết `property="tool.sha256"`, vì khi đó Ant sẽ so sánh với chuỗi chữ `tool.sha256`, không phải giá trị của property.

Sau đó, kiểm tra kết quả bằng condition và fail như phần trên.

Cách dùng property hữu ích khi:

- Digest chuẩn được lưu trong một tệp cấu hình có kiểm soát phiên bản.
- Dự án cần xác minh nhiều artifact với giá trị chuẩn cố định.
- Kho lưu trữ không cung cấp sidecar hoặc sidecar có định dạng không thuận tiện.

Hãy cập nhật checksum chuẩn cùng lúc với thay đổi phiên bản artifact. Nếu URL trỏ đến phiên bản mới nhưng property vẫn giữ digest của phiên bản cũ, build sẽ thất bại đúng như mong đợi.

## 7. Quy trình hoàn chỉnh: tải artifact và xác minh SHA-256

Ví dụ sau tải một tệp ZIP cùng sidecar SHA-256, sau đó dừng build nếu checksum không khớp:

~~~xml
<project name="download-verified-artifact" default="download" basedir=".">
    <property name="download.dir" location="build/downloads"/>
    <property name="artifact.name" value="tool-2.4.1.zip"/>
    <property name="artifact.url"
              value="https://downloads.example.org/tools/tool-2.4.1.zip"/>
    <property name="artifact.file"
              location="build/downloads/tool-2.4.1.zip"/>
    <property name="checksum.url"
              value="https://downloads.example.org/tools/tool-2.4.1.zip.sha256"/>

    <target name="download">
        <mkdir dir="${download.dir}"/>

        <get src="${artifact.url}"
             dest="${artifact.file}"
             verbose="true"
             retries="3"
             maxtime="300"
             usetimestamp="true"/>

        <get src="${checksum.url}"
             dest="${artifact.file}.sha256"
             retries="3"
             maxtime="60"
             usetimestamp="true"/>

        <checksum file="${artifact.file}"
                  algorithm="SHA-256"
                  fileext=".sha256"
                  verifyproperty="artifact.checksum.matches"/>

        <condition property="artifact.checksum.failed">
            <equals arg1="${artifact.checksum.matches}" arg2="false"/>
        </condition>

        <fail if="artifact.checksum.failed"
              message="SHA-256 mismatch for ${artifact.name}"/>
    </target>
</project>
~~~

Chạy target:

~~~text
ant download
~~~

Luồng thực hiện:

1. Tạo thư mục `build/downloads`.
2. Tải artifact vào đúng tên tệp.
3. Tải sidecar vào tên `tool-2.4.1.zip.sha256`.
4. Tính SHA-256 của artifact và so sánh với sidecar.
5. Nếu sai, fail làm build dừng. Nếu đúng, target kết thúc thành công.

Ví dụ giả định máy chủ cung cấp sidecar chỉ chứa digest thuần và URL checksum dùng quy ước tên `.zip.sha256`. Nếu kho lưu trữ dùng tên hoặc định dạng khác, hãy điều chỉnh URL, `fileext` và `format`/ `pattern` tương ứng.

Trong ví dụ này, `usetimestamp` giúp giảm tải lại khi máy chủ HTTP cung cấp timestamp phù hợp. Dù vậy, checksum vẫn được kiểm tra sau khi task get kết thúc. Khi thay đổi phiên bản artifact, hãy cập nhật URL và checksum sidecar cùng nhau.

## 8. Tải và xác minh nhiều thư viện

Có thể tải nhiều artifact từ một danh sách URL, nhưng cần tổ chức tên tệp và checksum tương ứng rõ ràng. Với một vài thư viện cố định, khai báo từng cặp tải và xác minh thường dễ theo dõi:

~~~xml
<target name="download-libraries">
    <mkdir dir="build/downloads"/>

    <get src="https://repo.example.org/lib/core-2.4.jar"
         dest="build/downloads/core-2.4.jar"/>
    <get src="https://repo.example.org/lib/core-2.4.jar.sha256"
         dest="build/downloads/core-2.4.jar.sha256"/>

    <checksum file="build/downloads/core-2.4.jar"
              algorithm="SHA-256"
              fileext=".sha256"
              verifyproperty="core.checksum.matches"/>

    <condition property="core.checksum.failed">
        <equals arg1="${core.checksum.matches}" arg2="false"/>
    </condition>

    <fail if="core.checksum.failed"
          message="Checksum mismatch: core-2.4.jar"/>

    <get src="https://repo.example.org/lib/adapter-2.4.jar"
         dest="build/downloads/adapter-2.4.jar"/>
    <get src="https://repo.example.org/lib/adapter-2.4.jar.sha256"
         dest="build/downloads/adapter-2.4.jar.sha256"/>

    <checksum file="build/downloads/adapter-2.4.jar"
              algorithm="SHA-256"
              fileext=".sha256"
              verifyproperty="adapter.checksum.matches"/>

    <condition property="adapter.checksum.failed">
        <equals arg1="${adapter.checksum.matches}" arg2="false"/>
    </condition>

    <fail if="adapter.checksum.failed"
          message="Checksum mismatch: adapter-2.4.jar"/>
</target>
~~~

Khi danh sách dài, có thể tổ chức dependency thành các macro hoặc target riêng để giảm lặp. Nếu dùng macro, hãy tạo các property cục bộ cho kết quả checksum và cờ lỗi để mỗi lần gọi không xung đột với property đã được thiết lập trước đó. Property thông thường của Ant chỉ được thiết lập một lần.

Không nên dùng một property kết quả chung cho nhiều lần xác minh trong cùng project nếu cần phân biệt kết quả từng artifact. Có thể dùng `<local>` trong macro hoặc đặt tên property riêng cho từng thư viện.

## 9. Phân biệt checksum với chữ ký số và nguồn gốc artifact

Checksum và chữ ký số thường được nhắc cùng nhau nhưng có mục đích khác nhau.

- **Checksum** xác nhận nội dung tệp có khớp với một digest mong đợi hay không.
- **Chữ ký số** giúp xác minh dữ liệu được ký bởi chủ thể sở hữu khóa ký tương ứng và chưa bị thay đổi sau khi ký.
- **Metadata nguồn gốc** mô tả artifact thuộc dự án nào, phiên bản nào, được phát hành ở đâu và theo quy trình nào.

Nếu tải artifact và checksum từ cùng một máy chủ hoặc cùng một kênh không được xác thực, kẻ có thể thay artifact cũng có thể thay sidecar. Khi đó, hai tệp vẫn khớp checksum dù artifact không phải bản phát hành mong muốn.

Đối với thư viện quan trọng, nên lấy checksum từ một kênh phát hành đáng tin cậy hoặc lưu digest đã được kiểm tra vào repository. Nếu nhà phát hành cung cấp chữ ký số, hãy xác minh chữ ký bằng công cụ và khóa công khai phù hợp. Checksum không thay thế việc xác minh chữ ký.

### 9.1. Ghi nhận nguồn gốc và phiên bản

Để quản lý thư viện tải thủ công, nên lưu metadata rõ ràng:

| Trường | Ví dụ |
|---|---|
| Tên artifact | core |
| Phiên bản | 2.4.0 |
| Nguồn tải | URL kho phát hành chính thức |
| Tệp lưu cục bộ | lib/core-2.4.0.jar |
| Thuật toán checksum | SHA-256 |
| Digest chuẩn | Giá trị SHA-256 đã xác nhận |
| Nguồn checksum | Trang phát hành hoặc metadata đã ký |
| Giấy phép | Tham chiếu giấy phép của artifact |

Các thông tin này giúp người bảo trì biết thư viện đến từ đâu, tại sao phiên bản đó được sử dụng và cách xác minh lại khi cần.

Không nên chỉ ghi một URL chung không có phiên bản nếu máy chủ có thể thay đổi nội dung tại cùng địa chỉ. URL cố định theo phiên bản và checksum được lưu cùng metadata giúp build có thể tái lập hơn.

## 10. Đưa thư viện đã xác minh vào classpath

Sau khi tải và xác minh thành công, có thể đưa thư viện vào Path:

~~~xml
<path id="downloaded.libraries">
    <fileset dir="build/downloads">
        <include name="*.jar"/>
    </fileset>
</path>

<target name="compile" depends="download-libraries">
    <mkdir dir="build/classes"/>

    <javac srcdir="src"
           destdir="build/classes"
           classpathref="downloaded.libraries"
           includeantruntime="false"/>
</target>
~~~

Dependency của target bảo đảm bước tải và xác minh hoàn thành trước khi biên dịch. Nếu checksum mismatch, target download-libraries thất bại và target compile phụ thuộc nó không được thực hiện thành công.

Với dự án có nhiều dependency, nên đặt chúng trong một thư mục hoặc cấu trúc rõ ràng. Không để các JAR cũ từ lần chạy trước trộn với bộ thư viện mới mà không có quy tắc quản lý.

Một lựa chọn khác là tải vào thư mục staging, xác minh xong mới copy hoặc move vào thư mục lib chính thức. Như vậy, thư mục lib chỉ chứa các artifact đã qua xác minh.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Get báo không mở được URL | URL sai, máy chủ không truy cập được, proxy hoặc DNS lỗi | Kiểm tra URL, kết nối và cấu hình proxy |
| Tệp tải xuống không nằm ở vị trí mong muốn | Giá trị dest là thư mục hoặc tên tệp không đúng | Chỉ định đường dẫn tệp đích cụ thể |
| Build tiếp tục dù tải thất bại | Đang bật ignoreerrors | Tắt ignoreerrors với dependency bắt buộc |
| Tệp cũ được giữ lại | Dùng skipexisting hoặc timestamp khiến tải bị bỏ qua | Kiểm tra chính sách cập nhật và chạy xác minh checksum |
| Checksum task không tìm thấy sidecar | Sai fileext hoặc tên sidecar không khớp | Kiểm tra tên tệp thực tế và fileext |
| Checksum luôn sai | Sai thuật toán, sai phiên bản artifact hoặc sidecar không cùng định dạng | Kiểm tra SHA-256/SHA-512 và nội dung digest |
| Checksum property là false nhưng build không fail | Dùng fail unless để kiểm tra property tồn tại | Dùng condition equals false rồi fail if |
| Tệp checksum có cả tên file trên dòng | Định dạng sidecar khác CHECKSUM mặc định | Cấu hình format hoặc pattern tương ứng |
| Build thành công với artifact không mong muốn | Checksum và artifact cùng lấy từ nguồn không đáng tin | Dùng digest từ kênh độc lập hoặc xác minh chữ ký |
| Artifact bị tải lại quá thường xuyên | Timestamp HTTP không phù hợp hoặc cache bị tắt | Kiểm tra metadata máy chủ và tùy chọn get |

### 11.1. Chẩn đoán tải xuống

Khi Get thất bại, kiểm tra:

- URL có đúng tên artifact và phiên bản không.
- Máy build có truy cập được host và port không.
- HTTPS certificate có được Java runtime tin cậy không.
- Máy chủ có yêu cầu xác thực hoặc header riêng không.
- Proxy có được cấu hình đúng không.
- Tệp đích có thể ghi được không.
- Giới hạn `maxtime` có quá ngắn so với kích thước tài nguyên không.

Có thể bật `verbose="true"` để quan sát tiến trình. Khi dùng proxy, Ant có thể sử dụng proxy của hệ điều hành qua tùy chọn dòng lệnh `-autoproxy` trên môi trường Java phù hợp; các môi trường khác có thể cần task `setproxy`.

### 11.2. Chẩn đoán checksum

Nếu xác minh không khớp, không nên tự động tải lại vô hạn hoặc bỏ qua lỗi. Hãy kiểm tra:

1. Artifact tải về có đúng phiên bản dự kiến không.
2. Sidecar có thuộc đúng artifact và đúng phiên bản không.
3. Thuật toán được chọn có khớp thuật toán nhà phát hành công bố không.
4. Sidecar có chứa digest thuần hay kèm tên tệp, dấu cách hoặc định dạng khác không.
5. Có tệp cũ cùng tên từ lần chạy trước không.
6. Giá trị checksum chuẩn trong property file có được cập nhật cùng artifact không.

Nếu checksum sai, hãy coi artifact chưa được xác minh và không đưa nó vào classpath hoặc bước phát hành.

## 12. Thực hành tốt

- Dùng URL có phiên bản cố định, tránh URL trỏ đến bản latest thay đổi theo thời gian.
- Lưu artifact trong thư mục được quản lý riêng như `build/downloads` hoặc `lib`.
- Đặt `retries` và `maxtime` phù hợp với quy mô tải.
- Giữ `ignoreerrors="false"` cho dependency bắt buộc.
- Dùng `usetimestamp` như một tối ưu tải HTTP, không coi nó là xác minh nội dung.
- Dùng SHA-256 hoặc SHA-512 thay cho MD5/SHA-1 khi cần kiểm tra tính toàn vẹn có ý nghĩa bảo mật.
- Xác minh checksum sau khi tải và trước khi dùng artifact.
- Khi sidecar có định dạng riêng, cấu hình format/pattern đúng thay vì giả định mọi tệp checksum đều chỉ có digest.
- Dừng build khi checksum không khớp.
- Lưu digest chuẩn hoặc xác minh chữ ký từ một nguồn đáng tin cậy.
- Không commit thông tin đăng nhập hoặc token truy cập vào buildfile.
- Ghi rõ tên, phiên bản, URL nguồn, thuật toán và digest của thư viện được quản lý thủ công.
- Tải vào staging rồi chuyển sang thư mục lib sau khi xác minh nếu cần tránh dùng nhầm tệp chưa hoàn tất.
- Giữ thư mục dependency sạch, tránh trộn các phiên bản cũ và mới.
- Chỉ đưa artifact đã xác minh vào classpath.

## 13. Tự kiểm tra quy trình tải và xác minh

Trước khi đưa task download vào build chính, hãy tự trả lời:

1. URL có trỏ đến đúng artifact và phiên bản cố định không?
2. Tệp đích có tên và thư mục rõ ràng không?
3. Có tạo thư mục đích trước khi tải không?
4. Get có dừng build khi lỗi tải không?
5. Số lần retry và thời gian tối đa có hợp lý không?
6. Có đang dùng timestamp hoặc skipexisting mà chưa xác minh nội dung không?
7. Checksum chuẩn đến từ sidecar hoặc nguồn độc lập đáng tin cậy nào?
8. Thuật toán có phải SHA-256 hoặc mạnh hơn theo yêu cầu không?
9. Tên sidecar và fileext có khớp chính xác không?
10. Định dạng sidecar có phù hợp với cấu hình checksum không?
11. Kết quả false có thực sự làm build thất bại không?
12. Artifact chỉ được đưa vào classpath sau khi xác minh thành công không?
13. Có ghi lại nguồn gốc và phiên bản của thư viện để người khác tái lập build không?

Khi kết hợp `get` với `checksum`, Ant có thể tự động tải thư viện và kiểm tra nội dung trước khi sử dụng. Quy trình này chỉ có ý nghĩa khi digest chuẩn được lấy từ nguồn đáng tin cậy, lỗi xác minh làm build dừng và metadata phiên bản được quản lý rõ ràng.

## Tài liệu tham khảo

- [Apache Ant — Get Task](https://ant.apache.org/manual/Tasks/get.html)
- [Apache Ant — Checksum Task](https://ant.apache.org/manual/Tasks/checksum.html)

