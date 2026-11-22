# Đặt quyền tệp theo hệ điều hành và kiểm soát phạm vi xóa

Trong một build Ant, ngoài việc biên dịch và đóng gói, ta thường phải chuẩn bị quyền truy cập cho script, đánh dấu một số tệp chỉ đọc hoặc dọn các kết quả trung gian cũ. Những thao tác này liên quan trực tiếp tới hệ điều hành và có thể gây mất dữ liệu nếu đường dẫn hoặc phạm vi xử lý được cấu hình sai.

Ant cung cấp các task như chmod, attrib và delete để thực hiện những công việc này. Tuy nhiên, quyền POSIX trên Linux/macOS, thuộc tính tệp của Windows và quyền truy cập ACL là những cơ chế khác nhau. Tương tự, xóa một tệp được chọn bằng fileset khác hoàn toàn với xóa đệ quy cả một thư mục.

Bài học này trình bày cách đặt quyền tệp theo từng hệ điều hành, cách tổ chức target có điều kiện, và cách giới hạn thao tác xóa vào đúng thư mục đầu ra do build tạo ra.

## 1. Phân biệt quyền tệp giữa các hệ điều hành

### 1.1. Linux và macOS: quyền POSIX

Trên Linux và macOS, quyền truy cập truyền thống của tệp được biểu diễn bằng các nhóm quyền cho:

- Owner: người sở hữu tệp.
- Group: nhóm sở hữu tệp.
- Others: những người dùng còn lại.

Mỗi nhóm có ba quyền cơ bản:

- Read (r): đọc nội dung tệp hoặc liệt kê nội dung thư mục.
- Write (w): sửa nội dung tệp hoặc thay đổi mục bên trong thư mục.
- Execute (x): chạy tệp thực thi; đối với thư mục, cho phép đi xuyên qua/truy cập các mục bên trong nếu có quyền phù hợp.

Ví dụ, quyền dạng số thường gặp:

| Mode | Ý nghĩa | Trường hợp sử dụng thường gặp |
|---|---|---|
| 644 | Owner đọc/ghi; group và others chỉ đọc | Tệp cấu hình hoặc tài liệu thông thường |
| 600 | Chỉ owner đọc/ghi | Tệp chứa dữ liệu riêng tư, nếu chính sách owner phù hợp |
| 755 | Owner đọc/ghi/chạy; group và others đọc/chạy | Script hoặc thư mục cần truy cập công khai |
| 700 | Chỉ owner đọc/ghi/chạy | Script hoặc thư mục riêng của một tài khoản |

Ví dụ, một script cần quyền thực thi có thể được đặt thành 755. Tệp cấu hình thông thường thường không cần quyền thực thi. Không nên đặt 777 chỉ để tránh lỗi quyền vì như vậy mọi người dùng đều có thể đọc, sửa và thực thi tệp theo quyền POSIX.

Quyền thực tế còn phụ thuộc owner, group, ACL mở rộng, mount options và umask. Vì vậy, đặt mode 644 hoặc 755 không tự động giải quyết mọi vấn đề truy cập nếu người chạy build không phải owner hoặc không thuộc group thích hợp.

### 1.2. Windows: thuộc tính tệp và ACL

Windows có các thuộc tính tệp như Read-only, Hidden, System và Archive. Chúng không tương đương hoàn toàn với ba nhóm quyền read/write/execute của POSIX.

Ví dụ, đánh dấu Read-only bằng lệnh attrib không tạo ra một ACL bảo đảm chỉ một nhóm người dùng được phép đọc. Quyền truy cập thực tế của Windows được kiểm soát bằng Access Control List (ACL), thường được quản lý qua giao diện bảo mật hoặc công cụ như icacls.

Cần phân biệt:

| Cơ chế | Dùng để làm gì? | Ví dụ |
|---|---|---|
| POSIX mode | Phân quyền owner/group/others trên hệ thống tệp POSIX | chmod 755 script.sh |
| Windows file attributes | Đánh dấu trạng thái như read-only, hidden, archive, system | attrib +R settings.properties |
| Windows ACL | Quy định tài khoản hoặc nhóm nào được phép đọc, sửa, xóa, thực thi | icacls trên thư mục hoặc tệp |

Nếu yêu cầu là đánh dấu tệp không nên bị sửa thông thường trên Windows, thuộc tính Read-only có thể hữu ích. Nếu yêu cầu là giới hạn ai được đọc hoặc ghi dữ liệu, phải cấu hình ACL phù hợp. Không dùng attrib thay cho ACL.

### 1.3. Không giả định một cấu hình quyền dùng chung cho mọi OS

Một lệnh chmod 755 có ý nghĩa rõ ràng trên hệ thống POSIX nhưng không phải cách đặt ACL Windows. Ngược lại, thuộc tính Hidden hoặc Read-only của Windows không thay thế được quyền execute của script trên Linux.

Khi build hỗ trợ nhiều hệ điều hành, hãy xác định chính xác yêu cầu theo từng nền tảng:

- Script shell trên Linux/macOS cần quyền thực thi.
- Script batch trên Windows thường được gọi qua cơ chế của Windows và không cần chmod.
- Tệp cấu hình có thể cần quyền đọc phù hợp, nhưng không nhất thiết cần quyền thực thi.
- Tài liệu phát hành thường chỉ cần quyền đọc.
- Tệp chứa thông tin nhạy cảm cần quyền truy cập giới hạn theo chính sách của hệ điều hành.

## 2. Dùng task chmod trên hệ điều hành POSIX

### 2.1. Đặt quyền cho một tệp

Task chmod của Ant thay đổi quyền theo cách tương đương lệnh chmod trên hệ điều hành Unix-like. Ví dụ:

~~~xml
<target name="set-launcher-permission">
    <chmod file="${basedir}/bin/run.sh" perm="755" />
</target>
~~~

Thuộc tính:

- file chỉ định tệp cần thay đổi.
- perm chỉ định mode mới, ví dụ 755 hoặc 644.

Trước khi gọi task, hãy bảo đảm tệp đã được tạo hoặc được sao chép vào đúng vị trí. Nếu build chạy trên hệ điều hành không hỗ trợ thao tác chmod theo cách này, target cần được điều kiện hóa để không thực thi nhầm nền tảng.

### 2.2. Đặt quyền cho nhóm tệp

Task chmod hỗ trợ lựa chọn tệp theo thư mục và mẫu. Ví dụ, đặt quyền thực thi cho các script trong thư mục bin:

~~~xml
<target name="set-script-permissions">
    <chmod dir="${basedir}/bin"
           includes="**/*.sh"
           perm="755" />
</target>
~~~

Có thể dùng fileset để chỉ rõ tập hợp tệp:

~~~xml
<target name="set-script-permissions">
    <chmod perm="755">
        <fileset dir="${basedir}/bin">
            <include name="**/*.sh" />
            <exclude name="**/examples/**" />
        </fileset>
    </chmod>
</target>
~~~

Ví dụ thứ hai giúp kiểm soát chính xác các script được chọn. Các mẫu include và exclude được tính tương đối từ thư mục gốc của fileset. Hãy kiểm tra phạm vi mẫu để tránh đặt quyền cho các tệp không thuộc sản phẩm.

### 2.3. Đặt quyền cho thư mục và nội dung

Quyền execute trên thư mục POSIX có nghĩa là có thể truy cập hoặc đi xuyên qua thư mục, không phải “chạy thư mục” như chạy một chương trình. Một thư mục cần quyền x để người dùng truy cập các tệp bên trong theo đường dẫn.

Khi đặt quyền cho thư mục, cần cân nhắc riêng quyền của thư mục và quyền của các tệp con. Không nên dùng cùng một mode cho tất cả loại đối tượng nếu script, tài liệu và cấu hình có yêu cầu khác nhau.

Ví dụ, có thể đặt quyền cho một thư mục phát hành riêng:

~~~xml
<chmod dir="${basedir}/dist" perm="755" />
~~~

Với các cây thư mục phức tạp, hãy dùng các tập hợp tệp hoặc target riêng để xử lý file và directory theo mục đích. Kiểm tra tài liệu task chmod của phiên bản Ant đang dùng để xác nhận các thuộc tính lựa chọn file/directory phù hợp.

## 3. Dùng task attrib trên Windows

Task attrib của Ant thay đổi các thuộc tính tệp theo cơ chế của Windows. Ví dụ đánh dấu tệp cấu hình là Read-only:

~~~xml
<target name="mark-default-config-readonly">
    <attrib file="${basedir}/dist/config/default.properties"
            readonly="true" />
</target>
~~~

Khi cần bỏ trạng thái Read-only:

~~~xml
<attrib file="${basedir}/dist/config/default.properties"
        readonly="false" />
~~~

Task attrib cũng hỗ trợ các thuộc tính như hidden, system và archive. Ví dụ:

~~~xml
<attrib file="${basedir}/dist/internal.txt"
        hidden="true" />
~~~

Không nên dùng thuộc tính Hidden như một biện pháp bảo mật. Tệp ẩn vẫn có thể được tìm và đọc bởi người có quyền truy cập. Nếu cần giới hạn quyền đọc/ghi, hãy dùng ACL Windows.

Nếu cần cấu hình ACL bằng icacls, có thể gọi công cụ hệ thống qua task exec trong target chỉ dành cho Windows. Cấu hình tài khoản, nhóm và quyền phải lấy từ chính sách môi trường triển khai; không ghi cứng một tài khoản cá nhân vào build file dùng chung.

## 4. Chọn task theo hệ điều hành bằng điều kiện Ant

### 4.1. Xác định hệ điều hành

Ant có điều kiện os để nhận diện nền tảng. Có thể tạo property khi hệ điều hành thuộc một family:

~~~xml
<condition property="is.windows">
    <os family="windows" />
</condition>

<condition property="is.unix">
    <os family="unix" />
</condition>
~~~

Property chỉ được thiết lập khi điều kiện đúng. Sau đó, target có thể dùng thuộc tính if hoặc unless để quyết định có chạy hay không.

### 4.2. Tách target theo nền tảng

Ví dụ, cùng một quy trình có thể đặt quyền cho script trên POSIX và đánh dấu tệp cấu hình trên Windows:

~~~xml
<condition property="is.windows">
    <os family="windows" />
</condition>

<condition property="is.unix">
    <os family="unix" />
</condition>

<target name="set-unix-permissions" if="is.unix">
    <chmod file="${basedir}/dist/bin/run.sh" perm="755" />
</target>

<target name="set-windows-attributes" if="is.windows">
    <attrib file="${basedir}/dist/config/default.properties"
            readonly="true" />
</target>

<target name="configure-platform-files"
        depends="set-unix-permissions,set-windows-attributes">
    <echo message="Platform-specific file settings processed" />
</target>
~~~

Khi chạy target configure-platform-files, Ant kiểm tra điều kiện của từng target con. Target không phù hợp với hệ điều hành hiện tại sẽ được bỏ qua.

Family unix bao gồm các hệ điều hành Unix-like mà Ant nhận diện theo cơ chế Os của nó. Nếu build chỉ hỗ trợ một nhóm hệ điều hành cụ thể, hãy kiểm tra chính xác family và phiên bản OS cần hỗ trợ thay vì coi mọi nền tảng đều tương đương.

### 4.3. Giữ target dùng chung độc lập với lệnh riêng của OS

Nên để các bước biên dịch, kiểm thử và đóng gói dùng chung. Chỉ tách những thao tác thực sự khác nhau theo hệ điều hành, ví dụ chmod, attrib hoặc gọi công cụ native.

Cách này giúp target chính dễ đọc:

~~~xml
<target name="prepare-release"
        depends="copy-release-files,configure-platform-files">
    <echo message="Release directory is ready" />
</target>
~~~

Target copy-release-files có thể dùng chung, còn configure-platform-files điều phối các target theo OS.

## 5. Kiểm soát phạm vi xóa bằng task delete

### 5.1. Xóa một tệp cụ thể

Khi chỉ cần xóa một tệp tạm, dùng thuộc tính file:

~~~xml
<delete file="${basedir}/build/temporary.txt" />
~~~

Đường dẫn này chỉ định một tệp cụ thể. Cách khai báo rõ ràng như vậy phù hợp với các tệp trung gian có tên cố định.

### 5.2. Xóa cả một thư mục đầu ra

Khi muốn dọn toàn bộ kết quả build, có thể dùng:

~~~xml
<delete dir="${basedir}/build" />
~~~

Với thuộc tính dir, Ant xóa thư mục được chỉ định cùng nội dung bên trong theo cơ chế đệ quy. Đây là thao tác có phạm vi lớn; nếu đường dẫn trỏ nhầm vào thư mục chứa mã nguồn hoặc dữ liệu người dùng, dữ liệu có thể bị mất.

Một target clean thông dụng:

~~~xml
<property name="build.dir" location="${basedir}/build" />
<property name="dist.dir" location="${basedir}/dist" />

<target name="clean">
    <delete dir="${build.dir}" />
    <delete dir="${dist.dir}" />
</target>
~~~

Chỉ đưa vào clean những thư mục thực sự do build tạo ra và có thể tái tạo. Không xóa src, config do người dùng quản lý, thư mục repository .git, thư mục home hoặc workspace cha.

### 5.3. Xóa một tập hợp tệp bằng fileset

Nếu chỉ muốn xóa tệp tạm theo mẫu, hãy dùng fileset thay vì xóa cả thư mục:

~~~xml
<delete>
    <fileset dir="${basedir}/build">
        <include name="**/*.tmp" />
        <include name="**/*.bak" />
        <exclude name="keep/**" />
    </fileset>
</delete>
~~~

Trong ví dụ:

- Thư mục gốc được giới hạn ở build.
- Chỉ các tệp có phần mở rộng tmp hoặc bak được chọn.
- Nội dung nằm trong keep được loại trừ.

Mẫu include/exclude được tính tương đối từ thư mục gốc fileset. Hãy chú ý rằng include rộng như **/* có thể chọn gần như toàn bộ nội dung. Nếu mục tiêu chỉ là xóa một loại tệp, hãy viết mẫu càng cụ thể càng tốt.

### 5.4. Xóa thư mục rỗng sau khi xóa tệp

Khi dùng fileset để xóa các tệp, các thư mục cha có thể còn lại sau khi tệp đã bị xóa. Thuộc tính includeemptydirs của task delete cho phép xóa các thư mục rỗng thuộc tập hợp xử lý:

~~~xml
<delete includeemptydirs="true">
    <fileset dir="${basedir}/build/cache">
        <include name="**/*.tmp" />
    </fileset>
</delete>
~~~

Chỉ bật includeemptydirs khi việc dọn cả thư mục rỗng là đúng mục tiêu. Nếu có thư mục rỗng được giữ lại làm cấu trúc cần thiết, không nên bật tùy chọn này cho tập hợp đó.

## 6. Thiết kế target clean an toàn

### 6.1. Chỉ xóa thư mục đầu ra đã xác định

Hãy khai báo rõ các thư mục output của dự án:

~~~xml
<property name="build.dir" location="${basedir}/build" />
<property name="reports.dir" location="${build.dir}/reports" />
<property name="dist.dir" location="${basedir}/dist" />
~~~

Sau đó target clean có thể xóa các khu vực đó:

~~~xml
<target name="clean">
    <echo message="Removing generated build outputs under ${build.dir}" />
    <delete dir="${build.dir}" />
    <delete dir="${dist.dir}" />
</target>
~~~

Việc dùng basedir làm gốc giúp đường dẫn dễ dự đoán khi chạy từ thư mục dự án. Không nên lấy một đường dẫn xóa tùy ý từ tham số người dùng hoặc biến môi trường mà không kiểm tra nó có nằm trong vùng output được phép hay không.

### 6.2. Không xóa trực tiếp thư mục gốc dự án

Các cấu hình nguy hiểm cần tránh:

~~~xml
<!-- Không làm như thế này -->
<delete dir="${basedir}" />

<!-- Không dùng một property chưa được kiểm soát làm đích xóa -->
<delete dir="${cleanup.path}" />
~~~

Lệnh đầu có thể xóa toàn bộ dự án. Lệnh thứ hai có thể xóa ngoài phạm vi dự kiến nếu cleanup.path bị truyền sai hoặc bị ghi đè từ bên ngoài.

Nếu cần hỗ trợ thư mục output tùy chỉnh, hãy xác thực đường dẫn trước khi gọi delete. Đừng chỉ kiểm tra chuỗi có chứa từ build hay không; hãy kiểm tra đường dẫn đã chuẩn hóa và mối quan hệ thực sự với thư mục gốc được phép. Nếu không có cơ chế xác thực đáng tin cậy, giữ đường dẫn output cố định trong build file là lựa chọn an toàn hơn.

### 6.3. Dùng fileset cho thao tác dọn có phạm vi hẹp

Ví dụ chỉ xóa báo cáo HTML được sinh tự động:

~~~xml
<target name="clean-reports">
    <delete>
        <fileset dir="${basedir}/build/reports">
            <include name="**/*.html" />
            <include name="**/*.xml" />
        </fileset>
    </delete>
</target>
~~~

Cách này không xóa các tệp khác trong reports. Nếu muốn dọn toàn bộ báo cáo cũ và thư mục con, có thể xóa riêng reports.dir sau khi xác nhận đây là thư mục output được tạo tự động.

### 6.4. Giữ mặc định báo lỗi khi không xóa được

Task delete mặc định báo lỗi khi thao tác xóa thất bại. Với target clean bắt buộc, nên giữ hành vi này để CI biết bước dọn dẹp không hoàn tất.

Task có các tùy chọn như failonerror và quiet để điều chỉnh cách xử lý lỗi/thông báo. Chỉ dùng cách bỏ qua lỗi khi đó là chủ đích rõ ràng, chẳng hạn tệp tùy chọn có thể không tồn tại và việc không xóa được không ảnh hưởng kết quả. Không đặt quiet hoặc failonerror=false một cách đại trà chỉ để log trông sạch hơn; điều đó có thể che giấu tệp bị khóa hoặc quyền truy cập sai.

## 7. Quyền tệp và phạm vi xóa trong một quy trình phát hành

Một target phát hành có thể thực hiện các bước:

1. Xóa staging cũ do build quản lý.
2. Tạo lại thư mục staging.
3. Sao chép JAR, tài liệu và cấu hình mẫu.
4. Đặt quyền thực thi cho script trên POSIX hoặc thuộc tính phù hợp trên Windows.
5. Tạo gói ZIP hoặc artifact cuối cùng.

Ví dụ:

~~~xml
<project name="release-example" default="release" basedir=".">

    <property name="build.dir" location="${basedir}/build" />
    <property name="stage.dir" location="${build.dir}/release-stage" />
    <property name="dist.dir" location="${basedir}/dist" />

    <condition property="is.windows">
        <os family="windows" />
    </condition>

    <condition property="is.unix">
        <os family="unix" />
    </condition>

    <target name="clean-stage">
        <delete dir="${stage.dir}" />
    </target>

    <target name="copy-release-files" depends="clean-stage">
        <mkdir dir="${stage.dir}/bin" />
        <mkdir dir="${stage.dir}/config" />

        <copy file="${basedir}/build/libs/application.jar"
              todir="${stage.dir}" />
        <copy file="${basedir}/scripts/run.sh"
              todir="${stage.dir}/bin" />
        <copy file="${basedir}/config/default.properties"
              todir="${stage.dir}/config" />
    </target>

    <target name="set-unix-permissions"
            depends="copy-release-files"
            if="is.unix">
        <chmod file="${stage.dir}/bin/run.sh" perm="755" />
    </target>

    <target name="set-windows-attributes"
            depends="copy-release-files"
            if="is.windows">
        <attrib file="${stage.dir}/config/default.properties"
                readonly="true" />
    </target>

    <target name="release"
            depends="set-unix-permissions,set-windows-attributes">
        <mkdir dir="${dist.dir}" />
        <zip destfile="${dist.dir}/application.zip"
             basedir="${stage.dir}" />
    </target>

</project>
~~~

Ví dụ này minh họa thứ tự và cách phân nhánh theo OS. Trong một dự án thực tế, tệp script chạy trên Windows có thể là run.bat hoặc run.cmd thay vì run.sh; hãy dùng fileset và target copy riêng để đưa đúng launcher vào từng gói. Ví dụ cũng giả định JAR và các tệp đầu vào đã được tạo hoặc tồn tại.

Nếu cả hai target thiết lập quyền đều bị bỏ qua do một hệ điều hành không thuộc family windows hoặc unix, target release vẫn có thể tiếp tục. Nếu dự án chỉ hỗ trợ Windows và Linux/macOS, có thể thêm bước kiểm tra OS không hỗ trợ và dừng build bằng fail để tránh phát hành gói chưa được cấu hình quyền như mong đợi.

## 8. Quyền tệp khi lưu trong Git và khi phát hành

Git lưu nhận biết bit executable cho tệp thông thường trên các hệ thống hỗ trợ. Vì vậy, một script shell có thể đã được commit với trạng thái executable. Khi checkout trên Linux, quyền thực thi có thể được khôi phục theo cấu hình Git và hệ thống tệp.

Tuy nhiên:

- Không nên giả định mọi hệ điều hành và cấu hình Git giữ nguyên tất cả POSIX mode bits.
- Windows không sử dụng quyền execute POSIX theo cùng cách.
- ACL và quyền thực tế có thể khác giữa máy phát triển, runner CI và máy triển khai.
- Quy trình đóng gói có thể không bảo toàn quyền nếu định dạng hoặc công cụ phát hành không lưu metadata đó.

Nếu script cần chạy trên Linux/macOS, hãy kiểm tra quyền sau checkout và sau khi giải nén artifact. Nếu build có trách nhiệm chuẩn bị quyền, hãy đặt quyền ở bước staging trước khi đóng gói và kiểm tra trên runner tương ứng.

Với Windows, nếu yêu cầu là giới hạn quyền đọc/ghi theo tài khoản, hãy thiết lập ACL trong môi trường triển khai. Thuộc tính readonly không thay thế kiểm soát truy cập bảo mật.

## 9. Symlink, tệp đang mở và khác biệt hệ thống tệp

Các hệ điều hành có cách xử lý khác nhau đối với symbolic link, junction, tệp đang được tiến trình khác mở và quyền xóa thư mục. Một thao tác xóa có thể thất bại vì:

- Tệp đang bị ứng dụng hoặc antivirus giữ handle.
- Người chạy build không có quyền xóa.
- Thư mục chứa tệp read-only hoặc ACL không cho phép xóa.
- Đường dẫn đi qua symbolic link hoặc junction.
- Hệ thống tệp hoặc tiến trình khác đang thay đổi cùng thư mục.

Khi build xử lý thư mục có symbolic link hoặc junction, cần kiểm tra hành vi của fileset và delete trên hệ điều hành đích. Không nên giả định một thao tác xóa đệ quy sẽ luôn xử lý link giống hệt thư mục thật. Với dữ liệu quan trọng, hãy giới hạn clean vào thư mục staging do build tạo và không để đường dẫn output trỏ vào cây thư mục do người dùng quản lý.

Trên Windows, một tệp có thuộc tính Read-only có thể khiến thao tác xóa gặp lỗi tùy task và cách hệ thống xử lý. Nếu target clean cần xóa tệp do build đánh dấu Read-only, hãy chủ động bỏ thuộc tính trước khi xóa bằng attrib trên Windows, trong một target có điều kiện phù hợp. Chỉ làm điều đó với các tệp output mà build sở hữu.

## 10. Kiểm tra trước và sau thao tác

Ant delete không có chế độ dry-run tổng quát để bảo đảm mọi thao tác xóa sẽ chỉ hiển thị mà không thực hiện. Vì vậy, trước khi bật target clean:

1. Đọc giá trị basedir và các property đường dẫn output.
2. Xác nhận mỗi thuộc tính dir trỏ tới thư mục build/dist dự kiến.
3. Kiểm tra fileset include/exclude và thư mục gốc của fileset.
4. Dùng echo hoặc log để hiển thị phạm vi sẽ xử lý.
5. Nếu có đường dẫn động, kiểm tra đường dẫn đã chuẩn hóa và giới hạn trong vùng được phép.
6. Chạy trên một workspace thử nghiệm nếu target mới có phạm vi xóa rộng.

Ví dụ in thông tin trước khi xóa:

~~~xml
<target name="clean">
    <echo message="Project base: ${basedir}" />
    <echo message="Build output to remove: ${build.dir}" />
    <echo message="Distribution output to remove: ${dist.dir}" />

    <delete dir="${build.dir}" />
    <delete dir="${dist.dir}" />
</target>
~~~

Echo chỉ hiển thị đường dẫn; nó không tự xác thực đường dẫn an toàn. Người viết build vẫn phải bảo đảm các property được thiết lập đúng.

Sau thao tác, kiểm tra log và mã thoát của Ant. Nếu delete thất bại vì quyền hoặc tệp đang mở, cần xử lý nguyên nhân cụ thể thay vì bỏ qua lỗi để pipeline tiếp tục như thể đã clean thành công.

## 11. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Script chạy được trên máy này nhưng không chạy trên Linux CI | Thiếu bit execute hoặc quyền bị mất khi đóng gói | Dùng chmod trong target Unix và kiểm tra sau khi giải nén |
| chmod không có tác dụng trên Windows | chmod không phải cơ chế ACL của Windows | Dùng attrib cho thuộc tính tệp hoặc icacls cho ACL, trong target Windows |
| Tệp vẫn bị người khác sửa dù đã readonly | Read-only không thay thế ACL bảo mật | Cấu hình ACL đúng tài khoản/nhóm |
| Ant không xóa được thư mục build | Tệp đang mở, quyền xóa thiếu hoặc có thuộc tính hạn chế | Kiểm tra tiến trình giữ tệp, quyền và thuộc tính của output |
| Target clean xóa nhầm dữ liệu | dir trỏ sai hoặc fileset include quá rộng | Giới hạn root, kiểm tra property và thu hẹp mẫu |
| Các thư mục rỗng vẫn còn sau khi xóa fileset | includeemptydirs chưa bật | Bật includeemptydirs nếu thật sự muốn xóa thư mục rỗng |
| Tệp tạm không bị xóa | Mẫu include không khớp đường dẫn tương đối hoặc exclude loại nhầm | Kiểm tra base dir và các mẫu |
| Build vẫn tiếp tục sau khi dọn dẹp lỗi | failonerror=false hoặc lỗi bị che bởi cấu hình quiet | Giữ failonerror mặc định cho bước bắt buộc và kiểm tra log |
| Windows không xóa được tệp read-only | Thuộc tính Read-only còn bật | Bỏ thuộc tính trên đúng output trước khi xóa |
| Gói phát hành thiếu quyền hoặc launcher phù hợp | Chỉ xử lý quyền mà không phân nhánh nội dung theo OS | Đóng gói launcher và metadata phù hợp từng nền tảng |

## 12. Nguyên tắc duy trì an toàn

- Phân biệt POSIX mode, Windows file attributes và Windows ACL.
- Dùng chmod cho quyền POSIX trên hệ điều hành phù hợp; dùng attrib cho thuộc tính Windows; dùng ACL tooling khi cần phân quyền tài khoản.
- Tạo target có điều kiện theo OS để tránh gọi lệnh không được hỗ trợ.
- Đặt quyền tối thiểu cần thiết; không dùng 777 để che lỗi permission.
- Chỉ xóa thư mục do build tạo và có thể tái tạo.
- Dùng fileset include/exclude khi chỉ cần xóa một nhóm tệp.
- Chỉ bật includeemptydirs khi muốn dọn các thư mục rỗng.
- Giữ failonerror mặc định cho bước clean bắt buộc.
- In phạm vi xử lý để người vận hành có thể nhận biết target đang tác động tới đâu.
- Kiểm tra quyền và kết quả xóa trên từng hệ điều hành mà dự án công bố hỗ trợ.

Một build Ant đáng tin cậy cần kiểm soát được cả quyền truy cập lẫn phạm vi thao tác tệp. Khi target đặt quyền theo đúng cơ chế của hệ điều hành và target clean chỉ tác động lên output đã xác định, quy trình phát hành sẽ ít phụ thuộc vào máy cá nhân và giảm nguy cơ xóa nhầm dữ liệu.

