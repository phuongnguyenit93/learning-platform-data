# Ghép nội dung bằng concat và cập nhật dấu thời gian bằng touch

Trong Apache Ant, nhiều quy trình build cần ghép các tệp văn bản thành một tệp đầu ra: ghép các phần tài liệu, nối các đoạn cấu hình, tạo danh sách nguồn hoặc tổng hợp báo cáo. Sau khi tạo tệp, build cũng có thể cần cập nhật dấu thời gian (last modified time) của một tệp hoặc một nhóm tệp để các công cụ khác nhận biết thời điểm dữ liệu được tạo hoặc cập nhật.

Ant cung cấp hai task cho hai công việc này:

- **concat** đọc nội dung từ một hoặc nhiều resource theo thứ tự và ghi chúng nối tiếp vào đầu ra.
- **touch** tạo tệp nếu chưa có hoặc cập nhật thời điểm sửa đổi cuối cùng của tệp hiện có.

Concat làm việc với **nội dung**. Touch làm việc với **metadata thời gian** của filesystem. Hiểu sự khác nhau này giúp chọn đúng task khi tạo artifact và điều phối các bước build.

## 1. Ghép nhiều tệp bằng concat

Task **concat** nhận các resource collection lồng bên trong và nối nội dung của chúng theo thứ tự. Kết quả thường được ghi vào một tệp đích thông qua thuộc tính **destfile**.

Ví dụ cơ bản:

~~~xml
<concat destfile="build/all-notes.txt">
    <filelist dir="docs/parts"
              files="01-intro.txt,02-setup.txt,03-usage.txt"/>
</concat>
~~~

Ant đọc lần lượt ba tệp trong FileList rồi nối nội dung vào **build/all-notes.txt**. FileList phù hợp khi thứ tự ghép đã được xác định rõ, chẳng hạn phần mở đầu phải đứng trước nội dung chính và phần kết thúc.

Có thể hình dung kết quả:

~~~text
01-intro.txt
      +
02-setup.txt
      +
03-usage.txt
      |
      v
build/all-notes.txt
~~~

Nếu các tệp nguồn chứa:

~~~text
# Introduction
Welcome to the project.
~~~

và:

~~~text
# Setup
Install the required tools.
~~~

thì đầu ra là nội dung của tệp thứ nhất nối tiếp nội dung tệp thứ hai. Concat không tự hiểu cấu trúc tài liệu hay tiêu đề; nó thực hiện phép nối dữ liệu theo cấu hình.

### Dùng FileSet để chọn tệp theo pattern

Nếu cần ghép tất cả tệp có cùng phần mở rộng trong một thư mục, có thể dùng FileSet:

~~~xml
<concat destfile="build/all-config.txt">
    <fileset dir="config/fragments">
        <include name="**/*.properties"/>
        <exclude name="**/local/**"/>
    </fileset>
</concat>
~~~

FileSet chọn các tệp properties phù hợp với include và loại các tệp nằm dưới thư mục **local**. Thứ tự các resource do collection cung cấp quyết định thứ tự ghép. Nếu thứ tự nội dung có ý nghĩa đối với kết quả, nên dùng FileList với danh sách tệp được sắp xếp tường minh thay vì phụ thuộc vào thứ tự quét thư mục.

## 2. Kiểm soát tệp đích và chế độ append

Thuộc tính **destfile** xác định tệp đầu ra. Khi chạy concat, nội dung được ghi vào tệp này.

Thuộc tính **append** quyết định có nối thêm vào tệp đích đã tồn tại hay không:

~~~xml
<concat destfile="build/history.txt" append="true">
    <filelist dir="logs" files="today.txt"/>
</concat>
~~~

- **append="false"** là chế độ mặc định: nội dung đầu ra thay thế nội dung cũ của tệp đích.
- **append="true"**: nội dung mới được thêm vào cuối tệp đích nếu tệp đã tồn tại.

Nếu task chạy lặp lại với **append="true"**, nội dung nguồn có thể được thêm nhiều lần. Vì vậy, chỉ dùng append khi thực sự muốn tích lũy dữ liệu qua nhiều lượt build, ví dụ tạo nhật ký tổng hợp. Với artifact cần tái tạo giống nhau từ cùng đầu vào, nên dùng chế độ ghi đè mặc định.

Tạo thư mục cha trước khi ghi tệp đích nếu thư mục đó chưa tồn tại:

~~~xml
<target name="merge-docs">
    <mkdir dir="build"/>
    <concat destfile="build/all-docs.txt">
        <filelist dir="docs/parts"
                  files="01-intro.txt,02-api.txt,03-faq.txt"/>
    </concat>
</target>
~~~

## 3. Encoding và line ending khi ghép văn bản

Khi ghép tệp văn bản, cần chú ý encoding của đầu vào và đầu ra. Các tệp có thể được lưu bằng UTF-8, Windows-1252 hoặc encoding khác. Nếu Ant đọc tệp bằng encoding không đúng, ký tự tiếng Việt hoặc ký tự ngoài ASCII có thể bị sai.

Concat có hai thuộc tính quan trọng:

- **encoding**: encoding dùng để đọc các resource đầu vào.
- **outputencoding**: encoding dùng để ghi kết quả.

Ví dụ, nếu mọi tệp nguồn và đầu ra đều là UTF-8:

~~~xml
<concat destfile="build/guide.txt"
        encoding="UTF-8"
        outputencoding="UTF-8">
    <filelist dir="docs/parts"
              files="01-intro.txt,02-setup.txt,03-faq.txt"/>
</concat>
~~~

Nếu không chỉ định, Ant dùng encoding mặc định của JVM hoặc môi trường cho thao tác tương ứng. Khi build chạy trên nhiều máy, không nên dựa vào mặc định nếu nội dung có tiếng Việt hoặc ký tự đặc biệt. Hãy thống nhất encoding của nguồn và đầu ra.

### Đảm bảo mỗi phần kết thúc bằng newline

Một tệp văn bản có thể không có ký tự xuống dòng ở cuối. Khi nối tệp tiếp theo, dòng cuối của tệp trước có thể dính liền với dòng đầu của tệp sau.

Ví dụ, tệp đầu tiên không kết thúc bằng newline:

~~~text
server.port=8080
~~~

Tệp tiếp theo bắt đầu bằng:

~~~text
spring.application.name=inventory
~~~

Nếu nối nguyên trạng, kết quả có thể thành:

~~~text
server.port=8080spring.application.name=inventory
~~~

Dùng **fixlastline="true"** để đảm bảo mỗi resource đầu vào kết thúc bằng ký tự xuống dòng trước khi nối resource kế tiếp:

~~~xml
<concat destfile="build/application.properties"
        encoding="UTF-8"
        outputencoding="UTF-8"
        fixlastline="true">
    <filelist dir="config/fragments"
              files="01-server.properties,02-application.properties"/>
</concat>
~~~

Thuộc tính **eol** cho phép chỉ định kiểu kết thúc dòng trong đầu ra. Các giá trị thường dùng gồm **lf**, **crlf**, **cr**, **unix**, **dos**, **mac** và **asis**. Ví dụ tạo tệp văn bản với line ending LF:

~~~xml
<concat destfile="build/combined.txt"
        encoding="UTF-8"
        outputencoding="UTF-8"
        fixlastline="true"
        eol="lf">
    <fileset dir="docs/parts">
        <include name="*.txt"/>
    </fileset>
</concat>
~~~

Hãy chọn line ending theo yêu cầu của công cụ tiêu thụ tệp. LF thường được dùng trong môi trường Unix-like và repository; CRLF thường gặp trong tệp văn bản Windows. Nếu cần giữ nguyên line ending của nguồn, dùng **asis** và không yêu cầu chuẩn hóa.

## 4. Ghép văn bản và dữ liệu nhị phân

Mặc định, concat xử lý nội dung như văn bản: đọc theo encoding, có thể chuẩn hóa line ending và hỗ trợ các cơ chế lọc văn bản. Với dữ liệu nhị phân, việc chuyển đổi encoding hoặc chèn ký tự xuống dòng sẽ làm hỏng nội dung.

Concat có thuộc tính **binary** để ghép dữ liệu nhị phân mà không xử lý như văn bản:

~~~xml
<concat destfile="build/payload.bin" binary="true">
    <filelist dir="payload/parts"
              files="part-01.bin,part-02.bin,part-03.bin"/>
</concat>
~~~

Chỉ dùng cách này khi định dạng dữ liệu được thiết kế để nối các phần byte theo đúng thứ tự. Không thể tùy tiện nối hai tệp JAR, ZIP, PNG hoặc các định dạng có header, directory hay offset nội bộ rồi kỳ vọng thu được một tệp hợp lệ. Việc ghép byte chỉ đúng khi giao thức hoặc định dạng của dữ liệu quy định cách ghép như vậy.

Không dùng các thiết lập xử lý văn bản như encoding, filter chain hoặc line ending cho dữ liệu nhị phân. Khi xử lý tệp nhị phân, hãy xác định rõ **binary="true"** để tránh chuyển đổi nội dung.

## 5. Các resource collection và thứ tự ghép

Concat có thể nhận nhiều loại resource collection như FileSet, FileList hoặc Path. Ví dụ:

~~~xml
<concat destfile="build/combined.txt" encoding="UTF-8">
    <filelist dir="docs" files="intro.txt,usage.txt"/>
    <fileset dir="docs/examples">
        <include name="*.txt"/>
    </fileset>
</concat>
~~~

Các collection được khai báo theo thứ tự trong XML; các resource trong mỗi collection được xử lý theo thứ tự mà collection cung cấp. Nếu nội dung phụ thuộc vào thứ tự chính xác, nên khai báo một FileList tường minh hoặc chia từng phần thành các collection có thứ tự dễ kiểm soát.

FileList phù hợp với một danh sách hữu hạn, đã biết tên và thứ tự:

~~~xml
<filelist dir="sql"
          files="001-schema.sql,002-data.sql,003-indexes.sql"/>
~~~

FileSet phù hợp với tập tệp được chọn theo pattern:

~~~xml
<fileset dir="sql">
    <include name="*.sql"/>
</fileset>
~~~

Nếu thứ tự migration hoặc thứ tự các đoạn cấu hình quan trọng, không nên dựa vào thứ tự quét của FileSet. Hãy quy định thứ tự bằng tên có tiền tố số và/hoặc dùng FileList.

## 6. Dùng header, footer và filter chain khi cần

Concat có thể thêm nội dung đầu và cuối thông qua các phần tử lồng **header** và **footer**. Điều này hữu ích khi tạo một tệp tổng hợp có phần tiêu đề hoặc phần kết thúc chung.

~~~xml
<concat destfile="build/combined-report.txt"
        encoding="UTF-8"
        outputencoding="UTF-8"
        fixlastline="true">
    <header trim="yes">
        === Build Report ===
    </header>

    <fileset dir="reports">
        <include name="*.txt"/>
    </fileset>

    <footer trim="yes">
        === End of Report ===
    </footer>
</concat>
~~~

Nội dung header được ghi trước các resource, footer được ghi sau các resource. Thuộc tính **trim** điều khiển việc loại bỏ khoảng trắng ở đầu/cuối phần văn bản header/footer theo cấu hình. Khi cần biến đổi nội dung đầu vào trước khi ghép, có thể dùng filter chain hoặc filter set được hỗ trợ bởi task concat.

Ví dụ, filter chain có thể chuẩn hóa hoặc biến đổi văn bản theo từng dòng:

~~~xml
<concat destfile="build/normalized.txt" encoding="UTF-8">
    <filterchain>
        <striplinebreaks/>
    </filterchain>
    <fileset dir="docs/fragments">
        <include name="*.txt"/>
    </fileset>
</concat>
~~~

Các bộ lọc có thể làm thay đổi nội dung, do đó cần dùng đúng với mục đích. Nếu chỉ cần ghép nguyên văn, không thêm filter chain hoặc filter set.

## 7. Cập nhật dấu thời gian bằng touch

Task **touch** cập nhật thời điểm sửa đổi cuối cùng (last modified time) của tệp. Nếu tệp chưa tồn tại, task tạo một tệp rỗng.

Cú pháp đơn giản:

~~~xml
<touch file="build/generated.stamp"/>
~~~

Lệnh này tạo tệp **generated.stamp** nếu chưa có; nếu đã tồn tại, nó cập nhật timestamp của tệp theo thời điểm hiện tại.

Có thể chỉ định thư mục cha được tạo tự động bằng **mkdirs="true"**:

~~~xml
<touch file="build/markers/compile.stamp" mkdirs="true"/>
~~~

Điều này hữu ích khi chỉ cần tạo marker file để ghi nhận một bước đã hoàn tất hoặc một trạng thái đã được xác lập.

**Touch không thay đổi nội dung của tệp đã tồn tại.** Nó cập nhật metadata thời gian của filesystem. Tuy nhiên, nhiều công cụ build dựa vào timestamp để quyết định có cần chạy lại một bước hay không, nên việc thay đổi timestamp có thể ảnh hưởng đến hành vi incremental build.

## 8. Chọn thời điểm bằng datetime hoặc millis

Mặc định, touch dùng thời điểm hiện tại. Khi cần một timestamp xác định, có thể dùng thuộc tính **datetime** hoặc **millis**.

### Dùng datetime

**datetime** nhận một chuỗi ngày giờ; **pattern** xác định định dạng để phân tích chuỗi đó:

~~~xml
<touch file="build/release.marker"
       datetime="2026-11-12 09:30:00"
       pattern="yyyy-MM-dd HH:mm:ss"/>
~~~

Trong ví dụ, timestamp được đặt theo ngày giờ đã chỉ định. Pattern sử dụng cú pháp định dạng ngày giờ của Java SimpleDateFormat. Việc diễn giải timezone theo timezone mặc định của JVM nếu chuỗi không chứa thông tin múi giờ.

### Dùng millis

**millis** nhận số mili giây tính từ Unix epoch (01-01-1970 UTC):

~~~xml
<touch file="build/fixed-time.marker"
       millis="1794475800000"/>
~~~

Cách này hữu ích khi timestamp được cung cấp từ một hệ thống khác dưới dạng số. Cần bảo đảm giá trị có đơn vị mili giây, không phải giây.

Không nên truyền đồng thời **datetime** và **millis** trong cùng một cấu hình. Hãy chọn một cách biểu diễn để tránh mơ hồ. Nếu không cần thời điểm cố định, để task dùng thời gian hiện tại sẽ đơn giản hơn.

## 9. Touch nhiều tệp bằng resource collection

Touch có thể nhận resource collection lồng bên trong để cập nhật timestamp cho một nhóm tệp. Ví dụ:

~~~xml
<touch>
    <fileset dir="build/generated">
        <include name="**/*.java"/>
    </fileset>
</touch>
~~~

Ant cập nhật thời gian sửa đổi của các tệp được chọn trong FileSet. Có thể dùng include/exclude để giới hạn phạm vi:

~~~xml
<touch>
    <fileset dir="build/docs">
        <include name="**/*.html"/>
        <exclude name="**/archive/**"/>
    </fileset>
</touch>
~~~

Khi dùng timestamp cố định, có thể đặt thuộc tính trên task:

~~~xml
<touch datetime="2026-11-12 09:30:00"
       pattern="yyyy-MM-dd HH:mm:ss">
    <fileset dir="build/generated">
        <include name="**/*.java"/>
    </fileset>
</touch>
~~~

Cần thận trọng khi touch một tập tệp rộng. Việc cập nhật timestamp của nhiều tệp có thể khiến công cụ downstream nhận thấy chúng đã thay đổi và chạy lại công việc tương ứng, dù nội dung không đổi.

## 10. Kết hợp concat và touch trong một quy trình

Một quy trình thường gặp là ghép nhiều đoạn văn bản thành một tệp tổng hợp, sau đó tạo marker để biểu thị bước tổng hợp đã hoàn tất.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="documentation" default="assemble" basedir=".">

    <property name="build.dir" location="build"/>
    <property name="parts.dir" location="docs/parts"/>
    <property name="combined.file" location="${build.dir}/guide.txt"/>
    <property name="stamp.file" location="${build.dir}/guide.stamp"/>

    <target name="prepare">
        <mkdir dir="${build.dir}"/>
    </target>

    <target name="assemble" depends="prepare"
            description="Ghép tài liệu và ghi marker hoàn tất">

        <concat destfile="${combined.file}"
                encoding="UTF-8"
                outputencoding="UTF-8"
                fixlastline="true"
                eol="lf">
            <filelist dir="${parts.dir}"
                      files="01-intro.txt,02-install.txt,03-usage.txt"/>
        </concat>

        <touch file="${stamp.file}"/>
        <echo message="Created ${combined.file}"/>
        <echo message="Updated marker ${stamp.file}"/>
    </target>

</project>
~~~

Khi chạy **ant assemble**:

1. Target **prepare** tạo thư mục build.
2. Task **concat** đọc ba tệp theo đúng thứ tự đã khai báo.
3. Nội dung được đọc và ghi bằng UTF-8; nếu một phần không có newline cuối, task bổ sung theo cấu hình.
4. Tệp **guide.txt** được tạo hoặc ghi đè.
5. Task **touch** tạo hoặc cập nhật **guide.stamp** sau khi concat hoàn tất.
6. Thông điệp được in để người dùng biết đầu ra và marker đã được cập nhật.

Marker là một tệp riêng, không chứa nội dung tài liệu. Nó chỉ ghi nhận thời điểm task touch được thực hiện. Nếu concat thất bại, các task phía sau trong cùng target thông thường không chạy, do đó marker không được cập nhật như thể bước ghép đã thành công.

## 11. Timestamp và incremental build

Nhiều công cụ xác định đầu vào đã cũ hay chưa bằng cách so sánh thời gian sửa đổi. Ví dụ, nếu tệp nguồn mới hơn tệp đầu ra, công cụ có thể tạo lại đầu ra.

Touch có thể tác động đến so sánh đó:

- Touch tệp nguồn làm timestamp của nó mới hơn, có thể khiến bước xử lý downstream chạy lại.
- Touch tệp đầu ra có thể làm nó trông mới hơn các nguồn, khiến công cụ dựa trên timestamp bỏ qua việc tái tạo.
- Touch marker sau khi tạo artifact có thể giúp một bước khác biết lần chạy gần nhất đã hoàn thành.
- Touch timestamp về một thời điểm quá khứ hoặc tương lai có thể làm sai lệch kết quả so sánh.

Vì vậy, không nên dùng touch để che giấu đầu ra lỗi thời. Marker chỉ có ý nghĩa khi nó được cập nhật sau khi công việc tạo đầu ra thành công và quy tắc incremental build thực sự dùng marker đó.

Nếu cần quyết định một đầu ra có còn mới so với nhiều tệp nguồn hay không, hãy cân nhắc task **uptodate** hoặc cơ chế phụ thuộc thích hợp. Touch chỉ thay đổi timestamp; nó không tự so sánh nội dung hoặc phát hiện tệp nào đã thay đổi.

Ví dụ, **uptodate** có thể đặt property khi tệp đích không cũ hơn các tệp nguồn:

~~~xml
<uptodate property="guide.current"
          targetfile="build/guide.txt">
    <srcfiles dir="docs/parts">
        <include name="*.txt"/>
    </srcfiles>
</uptodate>
~~~

Sau đó có thể dùng property để quyết định target có cần chạy hay không. Hãy thiết kế marker và điều kiện cập nhật đồng nhất để không bỏ qua thay đổi thực sự của nguồn.

## 12. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Nội dung hai tệp dính trên cùng một dòng | Tệp trước không có newline cuối | Dùng **fixlastline="true"** hoặc chuẩn hóa nguồn |
| Ký tự tiếng Việt bị lỗi | Encoding đầu vào hoặc đầu ra không đúng | Khai báo **encoding** và **outputencoding** phù hợp, thường là UTF-8 |
| Kết quả ghép thay đổi thứ tự | Dùng FileSet trong khi thứ tự resource không được quy định rõ | Dùng FileList với thứ tự tường minh |
| Nội dung cũ vẫn còn ở cuối tệp | Dùng **append="true"** qua nhiều lần build | Dùng chế độ ghi đè nếu cần tái tạo đầu ra |
| Tệp nhị phân bị hỏng | Ghép như văn bản hoặc chuẩn hóa line ending | Dùng **binary="true"** nếu định dạng cho phép nối byte |
| Touch không tạo được tệp | Thư mục cha chưa tồn tại hoặc đường dẫn/quyền ghi không hợp lệ | Tạo thư mục trước hoặc dùng **mkdirs="true"**; kiểm tra quyền |
| Bước build khác chạy lại bất thường | Timestamp bị cập nhật không đúng thời điểm | Kiểm tra nơi dùng touch và logic so sánh timestamp |
| Marker mới hơn nhưng artifact không hợp lệ | Marker được cập nhật trước khi xác nhận bước tạo artifact thành công | Chỉ touch marker sau khi task tạo đầu ra hoàn tất |

## 13. Nguyên tắc sử dụng

- Dùng **concat** để ghép nội dung từ các resource collection vào một tệp đầu ra.
- Dùng **FileList** khi thứ tự ghép có ý nghĩa; dùng **FileSet** khi cần chọn theo pattern.
- Chỉ bật **append** khi muốn tích lũy nội dung giữa nhiều lượt chạy.
- Chỉ định encoding rõ ràng cho văn bản đa ngôn ngữ và chọn line ending phù hợp.
- Dùng **fixlastline** để tránh các đoạn văn bản bị dính nhau khi nguồn không có newline cuối.
- Chỉ dùng **binary** khi định dạng dữ liệu cho phép nối byte trực tiếp.
- Dùng **touch** để tạo marker hoặc cập nhật timestamp; nhớ rằng nội dung tệp hiện có không bị thay đổi.
- Cập nhật marker sau khi bước tạo đầu ra thành công và tránh thay đổi timestamp nguồn một cách tùy tiện.
- Dùng **uptodate** hoặc cơ chế kiểm tra đầu vào/đầu ra khi cần quyết định có phải chạy lại build hay không.

Concat và Touch bổ sung cho nhau trong quy trình xử lý tệp: concat tạo nội dung tổng hợp từ các phần đầu vào, còn touch ghi nhận mốc thời gian của tệp hoặc nhóm tệp. Khi kiểm soát thứ tự resource, encoding, line ending và thời điểm cập nhật marker, build Ant sẽ tạo đầu ra dễ dự đoán và phối hợp tốt hơn với các bước build dựa trên timestamp.

