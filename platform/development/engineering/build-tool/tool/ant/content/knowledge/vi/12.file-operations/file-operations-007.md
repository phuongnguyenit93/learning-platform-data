# Xử lý ghi đè, tệp chỉ đọc và thư mục rỗng trong Apache Ant

Các task thao tác tệp của Apache Ant như copy, move và delete có những tùy chọn kiểm soát cách xử lý khi file đích đã tồn tại, khi file đích ở trạng thái chỉ đọc và khi tập file có chứa thư mục rỗng. Những tùy chọn này có ý nghĩa khác nhau; dùng nhầm có thể khiến build bỏ qua file cần cập nhật, thất bại khi ghi đè hoặc xóa nhiều dữ liệu hơn dự kiến.

Bài học này tập trung vào ba nhóm hành vi:

- **Ghi đè:** quyết định khi nào file nguồn được chép lên file đích đã tồn tại.
- **Tệp chỉ đọc:** cho phép hoặc chuẩn bị quyền ghi trước khi thay thế hay xóa file.
- **Thư mục rỗng:** quyết định có sao chép hoặc xóa các thư mục không chứa file hay không.

Hiểu đúng từng thuộc tính giúp buildfile xử lý dữ liệu nhất quán giữa máy phát triển và môi trường CI.

## 1. Ghi đè file với task copy

Task copy sao chép file hoặc một tập tài nguyên sang file hoặc thư mục đích. Khi file đích đã tồn tại, Ant mặc định chỉ sao chép nếu file nguồn mới hơn file đích hoặc file đích chưa tồn tại.

Ví dụ:

~~~xml
<copy file="config/default.properties"
      tofile="build/config/application.properties" />
~~~

Với cấu hình mặc định:

- Nếu file đích chưa có, Ant tạo file đích.
- Nếu file nguồn mới hơn file đích, Ant sao chép nội dung nguồn sang đích.
- Nếu file đích mới hơn hoặc có thời gian sửa đổi tương đương theo độ chính xác của hệ thống file, Ant thường bỏ qua việc sao chép.

Cơ chế này giúp tránh ghi lại những file không thay đổi và hỗ trợ các quy trình build tăng dần. Tuy nhiên, nếu mục tiêu là luôn thay thế file đích bằng nội dung nguồn, cần dùng thuộc tính overwrite.

### 1.1. Thuộc tính overwrite

Thuộc tính overwrite quyết định có ghi đè file đích ngay cả khi file đích mới hơn nguồn hay không. Giá trị mặc định là false.

~~~xml
<copy file="config/application.properties"
      tofile="build/config/application.properties"
      overwrite="true" />
~~~

Khi overwrite="true", Ant sao chép file nguồn sang file đích đã tồn tại mà không dựa vào việc so sánh thời gian sửa đổi để bỏ qua file đích mới hơn.

Ví dụ:

~~~text
Nguồn:  config/application.properties
        Modified: 10:00

Đích:   build/config/application.properties
        Modified: 11:00
~~~

Nếu overwrite không được bật, file đích mới hơn nên Ant có thể giữ nguyên file đích. Nếu overwrite="true", nội dung từ nguồn được chép sang đích dù file đích có thời gian sửa đổi mới hơn.

Cần dùng tùy chọn này có chủ đích. Nếu thư mục đích chứa cấu hình do người vận hành chỉnh sửa, overwrite="true" có thể xóa những thay đổi đó bằng cách thay thế file bằng bản nguồn.

### 1.2. Ghi đè một tập file bằng FileSet

Task copy có thể nhận FileSet để sao chép nhiều file. Thuộc tính overwrite áp dụng cho toàn bộ thao tác copy:

~~~xml
<copy todir="dist/config"
      overwrite="true">
    <fileset dir="config">
        <include name="**/*.properties" />
        <exclude name="local/**" />
    </fileset>
</copy>
~~~

Trong ví dụ, Ant sao chép các file Properties được chọn từ config sang dist/config. Những file đích đã tồn tại vẫn được thay thế, kể cả khi chúng mới hơn file nguồn.

Nếu không muốn ghi đè file local do người dùng quản lý, hãy loại chúng bằng exclude hoặc tách chúng khỏi tập file nguồn. Không nên bật overwrite trên một tập file quá rộng nếu chưa hiểu rõ dữ liệu nào sẽ bị thay thế.

### 1.3. Độ chính xác thời gian sửa đổi

Khi overwrite=false, Ant quyết định file có cần sao chép hay không dựa trên thời gian sửa đổi. Các hệ thống file khác nhau có độ chính xác timestamp khác nhau; một số môi trường có thể chỉ lưu thời gian theo đơn vị giây hoặc có độ lệch đồng hồ giữa máy nguồn và máy đích.

Task copy có thuộc tính granularity để điều chỉnh khoảng dung sai khi so sánh thời gian. Mặc định thường là 1.000 ms, và có thể là 2.000 ms trên các hệ thống DOS. Chỉ thay đổi granularity khi đã xác định vấn đề do độ chính xác timestamp hoặc đồng hồ giữa các hệ thống.

Ví dụ:

~~~xml
<copy todir="dist"
      granularity="2000">
    <fileset dir="build/output">
        <include name="**/*" />
    </fileset>
</copy>
~~~

Không nên dùng overwrite="true" chỉ để che giấu một vấn đề timestamp nếu yêu cầu thực tế vẫn là chỉ sao chép file mới hơn. Hãy chọn thuộc tính theo chính sách cập nhật mong muốn.

## 2. Ghi đè file đích chỉ đọc bằng force

Một file đích có thể tồn tại nhưng được đánh dấu chỉ đọc. Trên một số hệ điều hành hoặc hệ thống file, việc thay thế file đó có thể thất bại do thuộc tính hoặc quyền ghi.

Task copy có thuộc tính force để cho phép ghi đè file đích chỉ đọc. Thuộc tính này được hỗ trợ từ Apache Ant 1.8.2 và mặc định là false.

~~~xml
<copy file="build/new-config.properties"
      tofile="dist/config/application.properties"
      force="true" />
~~~

force giải quyết vấn đề file đích chỉ đọc; nó không có nghĩa là luôn ghi đè mọi file bất kể timestamp. Cần phân biệt hai thuộc tính:

| Thuộc tính | Câu hỏi mà thuộc tính giải quyết | Mặc định |
|---|---|---|
| overwrite | Có thay thế file đích ngay cả khi file đích mới hơn nguồn không? | false |
| force | Có cho phép ghi đè file đích chỉ đọc không? | false |

Nếu muốn thay thế cả file đích mới hơn lẫn file đích chỉ đọc, có thể cần bật cả hai:

~~~xml
<copy file="build/new-config.properties"
      tofile="dist/config/application.properties"
      overwrite="true"
      force="true" />
~~~

Trong cấu hình này:

- overwrite="true" yêu cầu thay thế ngay cả khi file đích mới hơn.
- force="true" cho phép xử lý file đích chỉ đọc.
- Nếu hệ điều hành, hệ thống file hoặc quyền của tiến trình vẫn từ chối thao tác, Ant vẫn có thể báo lỗi.

Không nên bật force cho mọi thao tác copy nếu không cần. Thuộc tính này có thể làm thay đổi trạng thái chỉ đọc của file đích để thực hiện ghi, vì vậy hãy giới hạn phạm vi FileSet và thư mục đích.

## 3. Xử lý file chỉ đọc trên Windows và Unix-like

Trạng thái chỉ đọc có cách biểu diễn và ảnh hưởng khác nhau giữa các hệ điều hành. Trên Windows, file thường có thuộc tính Read-only. Trên Unix-like, quyền truy cập được biểu diễn bằng các bit read, write và execute của owner, group và others.

### 3.1. Dùng force khi copy file đích chỉ đọc

Đối với task copy, cách trực tiếp là:

~~~xml
<copy todir="dist/config"
      force="true">
    <fileset dir="build/config">
        <include name="**/*.properties" />
    </fileset>
</copy>
~~~

Ant sẽ cố gắng ghi đè các file đích chỉ đọc trong tập file được chọn. Nếu file đích mới hơn nguồn và overwrite vẫn là false, file đó vẫn có thể bị bỏ qua theo quy tắc timestamp. Nếu cần thay thế bất kể timestamp, kết hợp overwrite="true".

### 3.2. Gỡ thuộc tính Read-only trên Windows bằng attrib

Task attrib thay đổi thuộc tính file trên Windows. Có thể đặt readonly="false" để gỡ trạng thái chỉ đọc trước khi copy hoặc delete:

~~~xml
<attrib readonly="false">
    <fileset dir="dist/config">
        <include name="**/*.properties" />
    </fileset>
</attrib>

<copy todir="dist/config" overwrite="true">
    <fileset dir="build/config">
        <include name="**/*.properties" />
    </fileset>
</copy>
~~~

Task attrib hiện chỉ có hiệu lực trên Windows theo mặc định. Nó không phải giải pháp đa nền tảng. Nếu build chạy trên Linux hoặc macOS, không nên dựa vào attrib để thay đổi quyền file.

### 3.3. Quyền file trên Unix-like

Task chmod của Ant gọi công cụ chmod và chỉ có hiệu lực trên Unix hoặc các hệ thống tương thích. Có thể dùng nó để cấp quyền ghi trước khi xử lý file:

~~~xml
<chmod perm="u+w">
    <fileset dir="dist/config">
        <include name="**/*.properties" />
    </fileset>
</chmod>
~~~

Lưu ý quan trọng: trên Unix-like, xóa một file thường phụ thuộc vào quyền ghi và quyền tìm kiếm (execute) trên thư mục chứa file, chứ không chỉ quyền ghi của chính file đó. Vì vậy, nếu delete thất bại, hãy kiểm tra quyền trên thư mục cha và quyền sở hữu; chỉ thêm quyền ghi cho file chưa chắc đã giải quyết được vấn đề xóa.

Từ Ant 1.10.0 có task setpermissions sử dụng hỗ trợ NIO của Java để thay đổi một tập con quyền file theo cách ít phụ thuộc hệ điều hành hơn. Task này không thể thay thế mọi khả năng riêng của chmod hoặc attrib và chỉ áp dụng được với tài nguyên hỗ trợ việc thay đổi quyền.

## 4. Xóa file chỉ đọc

Task delete không có thuộc tính force tương tự copy. Nếu hệ điều hành từ chối xóa file do thuộc tính hoặc quyền truy cập, cần chuẩn bị quyền phù hợp trước khi gọi delete.

Ví dụ trên Windows:

~~~xml
<target name="clean-generated-config">
    <attrib readonly="false">
        <fileset dir="build/config">
            <include name="**/*.tmp" />
        </fileset>
    </attrib>

    <delete>
        <fileset dir="build/config">
            <include name="**/*.tmp" />
        </fileset>
    </delete>
</target>
~~~

Target này thực hiện hai bước:

1. Gỡ thuộc tính Read-only khỏi các file tạm được chọn.
2. Xóa các file khớp mẫu.

Trên Unix-like, hãy kiểm tra quyền ghi và execute của thư mục chứa file, quyền sở hữu và các cơ chế bảo vệ bổ sung như sticky bit. Task chmod có thể thay đổi quyền theo mô hình Unix; task attrib không phải công cụ cho môi trường này.

### 4.1. Không nhầm quiet với force

Task delete có thuộc tính quiet. Khi quiet="true", Ant không báo lỗi trong một số tình huống file hoặc thư mục không tồn tại hoặc không thể xóa; tùy chọn này cũng ngụ ý failonerror="false".

~~~xml
<delete file="build/optional.tmp"
        quiet="true" />
~~~

quiet chỉ điều chỉnh cách báo lỗi và trạng thái build. Nó không cấp quyền ghi, không gỡ thuộc tính Read-only và không bảo đảm file đã được xóa.

Nếu cần build dừng khi xóa thất bại, hãy giữ failonerror mặc định là true. Chỉ dùng failonerror="false" hoặc quiet="true" khi quy trình thật sự cho phép bỏ qua lỗi đó và có cách quan sát trạng thái file còn lại.

## 5. Sao chép thư mục rỗng với includeEmptyDirs

Một FileSet có thể chọn cả file và cấu trúc thư mục. Khi copy một FileSet sang thư mục khác, Ant mặc định sao chép cả những thư mục rỗng được FileSet đưa vào. Thuộc tính includeEmptyDirs của task copy mặc định là true.

Ví dụ:

~~~xml
<copy todir="dist">
    <fileset dir="src/main/resources">
        <include name="**/*" />
    </fileset>
</copy>
~~~

Giả sử cây nguồn:

~~~text
src/main/resources/
├── config/
│   └── app.properties
├── templates/
│   └── email.html
└── empty/
~~~

Sau khi copy, thư mục dist có thể giữ cấu trúc:

~~~text
dist/
├── config/
│   └── app.properties
├── templates/
│   └── email.html
└── empty/
~~~

Thư mục empty không chứa file nhưng vẫn được sao chép vì includeEmptyDirs mặc định là true.

Nếu không muốn tạo các thư mục rỗng trong đích, đặt:

~~~xml
<copy todir="dist" includeEmptyDirs="false">
    <fileset dir="src/main/resources">
        <include name="**/*" />
    </fileset>
</copy>
~~~

Thuộc tính này chỉ kiểm soát các thư mục rỗng được đưa vào FileSet. Những thư mục cha cần thiết để chứa file đã sao chép vẫn phải được tạo.

### 5.1. Khi nào nên giữ thư mục rỗng?

Thư mục rỗng có thể mang ý nghĩa cấu trúc đối với ứng dụng hoặc quy trình triển khai. Ví dụ, thư mục uploads, logs, plugins hoặc data có thể được tạo sẵn để ứng dụng ghi dữ liệu sau khi cài đặt.

Nếu bỏ các thư mục này, ứng dụng có thể phải tự tạo chúng khi khởi động. Điều đó không phải lúc nào cũng sai, nhưng cần thống nhất rõ bên nào chịu trách nhiệm tạo thư mục.

Ngược lại, nếu thư mục rỗng chỉ là dấu vết của cây nguồn và không có ý nghĩa khi triển khai, includeEmptyDirs="false" giúp gói đầu ra gọn hơn.

## 6. Xóa thư mục rỗng với includeemptydirs

Task delete có cách xử lý thư mục rỗng khác với copy. Khi dùng nested FileSet, mặc định Ant xóa các file được chọn nhưng không xóa thư mục rỗng. Thuộc tính includeemptydirs của delete mặc định là false.

Ví dụ:

~~~xml
<delete>
    <fileset dir="build">
        <include name="**/*.tmp" />
    </fileset>
</delete>
~~~

Ant xóa các file .tmp được chọn. Nếu một thư mục trở nên rỗng sau thao tác, thư mục đó vẫn có thể được giữ lại vì includeemptydirs chưa được bật.

Muốn xóa cả các thư mục rỗng trong phạm vi FileSet, đặt:

~~~xml
<delete includeemptydirs="true">
    <fileset dir="build">
        <include name="**/*.tmp" />
    </fileset>
</delete>
~~~

Ant xóa các file khớp mẫu và có thể loại bỏ các thư mục rỗng. Việc một thư mục có rỗng hay không được xác định từ trạng thái thực tế trên filesystem; mẫu include/exclude không biến một thư mục còn file thành thư mục có thể xóa.

### 6.1. Xóa toàn bộ thư mục build

Nếu mục tiêu là xóa toàn bộ thư mục build cùng mọi nội dung bên trong, dùng thuộc tính dir:

~~~xml
<delete dir="build" />
~~~

Cách này khác với xóa qua FileSet:

| Cách viết | Phạm vi |
|---|---|
| <delete dir="build"/> | Xóa cây thư mục build và chính thư mục build |
| <delete><fileset dir="build"/></delete> | Xóa các file được FileSet chọn; mặc định không xóa thư mục rỗng |
| <delete includeemptydirs="true"><fileset dir="build"/></delete> | Xóa file và cho phép xóa thư mục rỗng theo phạm vi FileSet |

Cần đặc biệt chú ý đường dẫn dir. Một giá trị sai có thể xóa nhầm dữ liệu. Khi cần lọc theo mẫu, hãy dùng FileSet với basedir rõ ràng và include/exclude cụ thể.

## 7. Phân biệt mặc định của copy, move và delete

Các task có hành vi mặc định khác nhau. Không nên giả định rằng cùng một thuộc tính sẽ có cùng mặc định ở mọi task.

| Thuộc tính | copy | move | delete |
|---|---|---|---|
| overwrite | false: chỉ copy nếu đích không tồn tại hoặc nguồn mới hơn | true: mặc định ghi đè đích theo quy tắc của move | Không áp dụng như copy |
| force | false: không ghi đè đích chỉ đọc nếu hệ thống từ chối | false: xử lý đích chỉ đọc khi được bật | Không có thuộc tính force tương ứng |
| includeEmptyDirs / includeemptydirs | true: copy thư mục rỗng | true: move thư mục rỗng trong FileSet | false: không xóa thư mục rỗng qua FileSet |

Move có hành vi mặc định overwrite khác copy. Khi dùng move, nguồn chỉ bị xóa sau khi nội dung được chuyển thành công đến đích. Vì move có thể thay đổi vị trí dữ liệu và xóa nguồn, hãy kiểm tra rõ đích và chính sách ghi đè trước khi chạy.

## 8. Ví dụ tổng hợp: chuẩn bị thư mục triển khai

Giả sử ứng dụng có thư mục staging chứa file đã build và cần sao chép sang dist. Yêu cầu:

- Cập nhật file đầu ra nếu nguồn mới hơn.
- Cho phép thay thế file đích chỉ đọc.
- Giữ lại các thư mục rỗng cần thiết cho runtime.
- Có target dọn dẹp file tạm và thư mục rỗng.

Một buildfile có thể tổ chức như sau:

~~~xml
<project name="inventory" default="deploy-staging" basedir=".">
    <property name="staging.dir" location="build/staging" />
    <property name="dist.dir" location="dist" />

    <target name="copy-staging"
            description="Copy staged application files">
        <copy todir="${dist.dir}"
              force="true"
              includeEmptyDirs="true">
            <fileset dir="${staging.dir}">
                <include name="**/*" />
                <exclude name="**/*.tmp" />
            </fileset>
        </copy>
    </target>

    <target name="clean-temporary"
            description="Remove temporary files and empty directories">
        <delete includeemptydirs="true">
            <fileset dir="${staging.dir}">
                <include name="**/*.tmp" />
            </fileset>
        </delete>
    </target>

    <target name="deploy-staging"
            depends="copy-staging"
            description="Prepare the deployment directory">
        <echo message="Staging files copied to ${dist.dir}" />
    </target>
</project>
~~~

Target copy-staging sử dụng force để xử lý file đích chỉ đọc, nhưng overwrite vẫn là false. Vì vậy, file đích mới hơn nguồn vẫn được giữ nguyên. Các thư mục rỗng được copy vì includeEmptyDirs là true.

Target clean-temporary dùng FileSet để chỉ chọn file .tmp và bật includeemptydirs để xóa các thư mục rỗng trong phạm vi xử lý. Nó không xóa toàn bộ staging.

Nếu yêu cầu triển khai là thay thế mọi file đích bất kể timestamp, thêm overwrite="true" vào task copy. Nếu dist chứa file cấu hình do người vận hành chỉnh sửa, cần loại những file đó khỏi FileSet hoặc xử lý riêng để không ghi đè dữ liệu cần giữ.

## 9. Quy trình xử lý an toàn

Trước khi dùng copy, move hoặc delete, hãy xác định rõ:

1. Thư mục nguồn và đích là gì?
2. File đích mới hơn có cần được giữ lại không?
3. Có file đích chỉ đọc hay không?
4. File chỉ đọc cần được ghi đè, gỡ thuộc tính hay giữ nguyên?
5. Các thư mục rỗng có ý nghĩa với ứng dụng không?
6. Thao tác có xóa nguồn hoặc dữ liệu đích không?
7. Nếu có lỗi, build nên dừng hay được phép tiếp tục?

Với thao tác có nguy cơ ghi đè hoặc xóa dữ liệu, nên bắt đầu bằng tập file hẹp, dùng verbose để quan sát các file được xử lý và kiểm tra đầu ra trên môi trường thử nghiệm trước khi áp dụng rộng.

## 10. Kết luận

Trong Apache Ant, overwrite kiểm soát việc thay thế file đích mới hơn, force cho phép ghi đè file đích chỉ đọc trong task copy hoặc move, còn includeEmptyDirs và includeemptydirs kiểm soát thư mục rỗng trong các thao tác sao chép và xóa. Những thuộc tính này giải quyết các vấn đề riêng và không thể thay thế cho nhau.

Hãy nhớ mặc định của copy là overwrite=false, force=false, includeEmptyDirs=true; delete dùng FileSet có includeemptydirs=false. Khi xử lý file chỉ đọc, copy có thể dùng force, còn delete cần chuẩn bị quyền hoặc thuộc tính phù hợp với hệ điều hành. Khi xóa cả cây thư mục, hãy phân biệt delete dir với delete qua FileSet để kiểm soát đúng phạm vi dữ liệu bị tác động.

## Tài liệu tham khảo

- [Apache Ant Copy Task](https://ant.apache.org/manual/Tasks/copy)
- [Apache Ant Move Task](https://ant.apache.org/manual/Tasks/move)
- [Apache Ant Delete Task](https://ant.apache.org/manual/Tasks/delete)
- [Apache Ant Attrib Task](https://ant.apache.org/manual/Tasks/attrib)
- [Apache Ant SetPermissions Task](https://ant.apache.org/manual/Tasks/setpermissions)

