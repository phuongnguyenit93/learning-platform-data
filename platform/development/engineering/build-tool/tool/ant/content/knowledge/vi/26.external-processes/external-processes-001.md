# Gọi công cụ hệ thống bằng exec trong Apache Ant

Trong một quy trình build, không phải công việc nào cũng được thực hiện bằng task Java có sẵn của Ant. Build có thể cần gọi Git để lấy thông tin phiên bản, chạy trình biên dịch bên ngoài, thực thi script triển khai, gọi công cụ kiểm tra mã nguồn hoặc chạy chương trình đóng gói do hệ thống cung cấp.

Apache Ant cung cấp task <exec> để khởi chạy một chương trình bên ngoài và kết nối nó với buildfile. Task này cho phép chọn executable, truyền tham số, đặt thư mục làm việc, thiết lập biến môi trường, chuyển hướng stdin/stdout/stderr, đặt timeout và xử lý mã thoát.

Điểm quan trọng là <exec> khởi chạy chương trình được chỉ định. Nó không tự động hiểu cú pháp shell như pipe, redirect, biến shell hoặc toán tử nối lệnh. Khi cần những tính năng đó, phải gọi shell một cách tường minh và truyền câu lệnh cho shell.

## 1. Khi nào dùng task exec?

Task exec phù hợp khi build cần chạy một công cụ độc lập bên ngoài Ant, ví dụ:

- Gọi Git để lấy commit hash hoặc kiểm tra working tree.
- Chạy chương trình Java, Node.js, Python hoặc compiler bên ngoài.
- Gọi script đóng gói, triển khai hoặc kiểm tra môi trường.
- Chạy công cụ dòng lệnh như zip, tar, curl hoặc CLI nội bộ.
- Khởi chạy tiện ích hệ thống để tạo dữ liệu hoặc chuyển đổi file.

Ví dụ đơn giản:

~~~xml
<target name="show-java-version">
    <exec executable="java">
        <arg value="-version" />
    </exec>
</target>
~~~

Chạy:

~~~bash
ant show-java-version
~~~

Ant khởi chạy chương trình java và truyền tham số -version. Output của tiến trình được chuyển vào log của Ant theo hành vi mặc định.

Task exec luôn chạy một tiến trình hệ điều hành riêng. Điều này khác với task java khi fork=false, nơi lớp Java có thể chạy ngay trong JVM đang điều phối Ant.

## 2. Cấu trúc cơ bản của task exec

Cấu trúc tổng quát:

~~~xml
<exec executable="duong-dan-hoac-ten-chuong-trinh"
      dir="thu-muc-lam-viec"
      failonerror="true">
    <arg value="tham-so-thu-nhat" />
    <arg value="tham-so-thu-hai" />
</exec>
~~~

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| executable | Chương trình cần khởi chạy |
| dir | Thư mục làm việc hiện tại của tiến trình con |
| arg | Một tham số truyền cho chương trình |
| env | Biến môi trường bổ sung hoặc thay đổi cho tiến trình con |
| failonerror | Có làm build thất bại khi chương trình trả mã thoát khác 0 hay không |
| failifexecutionfails | Có làm build thất bại nếu Ant không thể khởi chạy chương trình hay không |
| resultproperty | Property nhận mã thoát của tiến trình |
| timeout | Giới hạn thời gian chạy, tính bằng mili giây |
| output / error | File nhận stdout và stderr |
| outputproperty / errorproperty | Property nhận stdout và stderr |
| input / inputstring | File hoặc chuỗi cung cấp cho stdin |
| spawn | Khởi chạy tiến trình nền và không chờ kết quả theo cách thông thường |

Một task exec có thể chỉ cần executable và arg. Các thuộc tính khác nên được thêm khi quy trình thực sự cần kiểm soát thư mục, môi trường, thời gian hoặc output.

## 3. Chọn executable

Thuộc tính executable chỉ định chương trình mà Ant cần gọi. Có thể dùng tên chương trình nếu nó có trong PATH của môi trường chạy Ant:

~~~xml
<exec executable="git">
    <arg value="--version" />
</exec>
~~~

Hoặc chỉ định đường dẫn tuyệt đối:

~~~xml
<exec executable="/usr/bin/git">
    <arg value="--version" />
</exec>
~~~

Trên Windows:

~~~xml
<exec executable="C:/Program Files/Git/bin/git.exe">
    <arg value="--version" />
</exec>
~~~

Dùng đường dẫn tuyệt đối khi build cần một phiên bản công cụ cụ thể hoặc môi trường CI có nhiều bản cài. Nếu dùng tên ngắn như git, java hoặc node, kết quả phụ thuộc PATH mà tiến trình Ant nhận được.

### 3.1. executable không phải toàn bộ dòng lệnh

Không đặt cả lệnh và tham số vào executable như một chuỗi duy nhất:

~~~xml
<!-- Không nên -->
<exec executable="git status --short" />
~~~

Ant mong executable là chương trình cần khởi chạy. Các tham số nên được khai báo riêng bằng arg:

~~~xml
<exec executable="git">
    <arg value="status" />
    <arg value="--short" />
</exec>
~~~

Cách tách này giúp Ant truyền từng đối số đúng ranh giới, đặc biệt khi một đối số có khoảng trắng hoặc ký tự đặc biệt.

## 4. Truyền tham số bằng arg

Nested element arg xác định tham số của chương trình. Cách an toàn và dễ đọc nhất thường là dùng một arg value cho mỗi đối số.

Ví dụ gọi Git:

~~~xml
<exec executable="git" dir=".">
    <arg value="log" />
    <arg value="-1" />
    <arg value="--oneline" />
</exec>
~~~

Chương trình nhận ba đối số riêng: log, -1 và --oneline.

### 4.1. Dùng value cho đối số có khoảng trắng

Nếu một đối số chứa khoảng trắng, đặt toàn bộ giá trị trong một arg:

~~~xml
<exec executable="git">
    <arg value="log" />
    <arg value="--format=%h %s" />
</exec>
~~~

Ant truyền --format=%h %s như một đối số duy nhất. Không cần tự thêm dấu nháy shell quanh giá trị vì Ant đang truyền đối số trực tiếp cho executable.

Ví dụ gọi công cụ nhận một đường dẫn có khoảng trắng:

~~~xml
<exec executable="java">
    <arg value="-jar" />
    <arg value="tools/report generator.jar" />
    <arg value="build/reports" />
</exec>
~~~

Đối số tools/report generator.jar vẫn là một tham số duy nhất. Đây là lý do nên ưu tiên value thay vì ghép toàn bộ command line thành một chuỗi.

### 4.2. Dùng line khi cần phân tích một chuỗi tham số

arg hỗ trợ thuộc tính line để truyền một dòng chứa nhiều tham số:

~~~xml
<exec executable="git">
    <arg line="status --short --branch" />
</exec>
~~~

Ant phân tích dòng thành các đối số theo quy tắc của task. Cách này ngắn hơn nhưng việc xử lý khoảng trắng và dấu nháy có thể khó đọc hơn. Với đường dẫn hoặc giá trị có khoảng trắng phức tạp, nên dùng các phần tử arg value riêng.

Không nhầm line với cú pháp shell. Việc viết pipe hoặc redirect vào line không làm Ant tự khởi chạy shell.

### 4.3. Truyền tham số tùy chọn

Các CLI thường dùng tham số dạng --name value hoặc --name=value. Cả hai đều có thể truyền bằng arg:

~~~xml
<exec executable="tool">
    <arg value="--output" />
    <arg value="build/result.json" />
    <arg value="--format=json" />
</exec>
~~~

Hãy xem tài liệu của chương trình được gọi để biết nó yêu cầu dạng tham số nào. Ant không diễn giải ý nghĩa của các tham số đó.

## 5. Đặt thư mục làm việc bằng dir

Thuộc tính dir xác định thư mục hiện tại (working directory) của tiến trình con. Nó ảnh hưởng đến cách chương trình giải quyết các đường dẫn tương đối mà chương trình nhận được.

Ví dụ:

~~~xml
<exec executable="git" dir="modules/service">
    <arg value="status" />
    <arg value="--short" />
</exec>
~~~

Git chạy trong modules/service, vì vậy nó kiểm tra repository và file theo ngữ cảnh thư mục đó.

Một ví dụ khác gọi script trong thư mục tools:

~~~xml
<exec executable="python" dir="tools">
    <arg value="generate.py" />
    <arg value="--input" />
    <arg value="../config/api.yml" />
    <arg value="--output" />
    <arg value="../build/generated" />
    <env key="PYTHONUTF8" value="1" />
</exec>
~~~

Đường dẫn tương đối của arg được chương trình con giải quyết theo working directory, không nhất thiết theo thư mục chứa build.xml. Vì vậy, khi thay đổi dir, cần kiểm tra lại tất cả đường dẫn tương đối truyền cho executable.

Đường dẫn của chính executable cũng cần được xác định rõ. Khi cần độ ổn định cao, dùng đường dẫn tuyệt đối hoặc một property đã được chuẩn hóa thay vì dựa vào vị trí tương đối khó đoán.

## 6. Truyền biến môi trường bằng env

Một số công cụ lấy cấu hình từ biến môi trường như JAVA_HOME, PATH, NODE_ENV, LANG hoặc biến riêng của ứng dụng. Task exec hỗ trợ nested element env.

Ví dụ:

~~~xml
<exec executable="node" dir="tools" failonerror="true">
    <env key="NODE_ENV" value="production" />
    <env key="APP_VERSION" value="1.4.0" />
    <arg value="build.js" />
</exec>
~~~

Tiến trình Node nhận hai biến môi trường được đặt trước khi thực thi.

Có thể đặt một biến thông thường bằng value:

~~~xml
<env key="MODE" value="production" />
~~~

Với biến chứa danh sách đường dẫn như PATH, dùng thuộc tính path để Ant xử lý dấu phân cách phù hợp với hệ điều hành:

~~~xml
<env key="PATH" path="/opt/tools/bin" />
~~~

Mặc định, tiến trình con kế thừa môi trường của Ant rồi nhận các biến được khai báo trong nested env. Thuộc tính newenvironment="true" yêu cầu tạo môi trường mới chỉ từ các khai báo env, không kế thừa toàn bộ biến hiện có:

~~~xml
<exec executable="tool" newenvironment="true">
    <env key="PATH" path="/opt/tools/bin" />
    <env key="LANG" value="C.UTF-8" />
    <arg value="--version" />
</exec>
~~~

Khi bật newenvironment, phải cung cấp mọi biến môi trường mà chương trình cần, bao gồm PATH hoặc biến hệ thống khác nếu cần. Nếu thiếu, chương trình có thể không khởi động hoặc hoạt động khác dự kiến.

Không ghi mật khẩu, token hoặc secret trực tiếp vào buildfile. Dùng secret store hoặc cơ chế biến môi trường của CI, đồng thời giới hạn việc in môi trường ra log.

## 7. Chuyển hướng stdin, stdout và stderr

Một chương trình dòng lệnh có thể nhận dữ liệu từ stdin, in kết quả ra stdout và ghi lỗi ra stderr. Task exec cho phép cấu hình các luồng này.

### 7.1. Gửi dữ liệu qua stdin

Dùng input để đọc dữ liệu từ file:

~~~xml
<exec executable="python" input="config/request.json">
    <arg value="tools/process_request.py" />
</exec>
~~~

Hoặc dùng thuộc tính inputstring cho dữ liệu ngắn:

~~~xml
<exec executable="tools/validator"
      inputstring="sample input">
    <arg value="--stdin" />
</exec>
~~~

Khi cần nhiều dòng, file input thường rõ ràng và dễ tái sử dụng hơn. Không dùng input và inputstring đồng thời trong cùng một task.

### 7.2. Ghi stdout vào file

Thuộc tính output chỉ định file nhận stdout:

~~~xml
<exec executable="git" output="build/git-status.txt">
    <arg value="status" />
    <arg value="--short" />
</exec>
~~~

Nếu thư mục build chưa tồn tại, hãy tạo nó trước bằng mkdir.

### 7.3. Ghi stderr riêng

Thuộc tính error chỉ định file nhận stderr:

~~~xml
<exec executable="tool"
      output="build/tool.out"
      error="build/tool.err">
    <arg value="validate" />
</exec>
~~~

Khi không đặt error hoặc errorproperty riêng, stderr có thể được gộp vào đích output. Nếu cần tách kết quả và thông báo lỗi, hãy khai báo cả hai đích.

### 7.4. Thu output vào property

Có thể lưu stdout và stderr vào property:

~~~xml
<exec executable="git"
      outputproperty="git.commit"
      errorproperty="git.error">
    <arg value="rev-parse" />
    <arg value="--short" />
    <arg value="HEAD" />
</exec>

<echo message="Commit: ${git.commit}" />
~~~

Property chỉ có giá trị sau khi tiến trình kết thúc. Property của Ant thông thường bất biến, vì vậy nếu property cùng tên đã được thiết lập trước đó, kết quả mới không thay thế nó.

### 7.5. Ghi nối tiếp bằng append

Thuộc tính append điều khiển việc ghi file output/error:

~~~xml
<exec executable="tool"
      output="build/logs/tool.log"
      append="true">
    <arg value="run" />
</exec>
~~~

append="true" nối nội dung mới vào cuối file. Giá trị mặc định false ghi file theo chế độ thay thế nội dung cũ. Thuộc tính này áp dụng cho file output/error, không phải để nối chuỗi vào property.

## 8. Xử lý mã thoát với failonerror và resultproperty

Sau khi chương trình kết thúc, hệ điều hành trả về một mã thoát (exit code). Theo quy ước phổ biến, 0 nghĩa là thành công và giá trị khác 0 báo trạng thái lỗi hoặc kết quả đặc biệt. Tuy nhiên, ý nghĩa cụ thể phụ thuộc chương trình được gọi.

Task exec có hai thuộc tính cần phân biệt:

- failonerror quyết định build có thất bại khi tiến trình trả mã thoát khác 0 hay không.
- failifexecutionfails quyết định build có thất bại khi Ant không thể khởi chạy tiến trình hay không.

Hai tình huống khác nhau:

1. Ant không tìm thấy executable hoặc không thể tạo tiến trình: chương trình chưa chạy.
2. Ant khởi chạy được chương trình, nhưng chương trình kết thúc với mã khác 0: tiến trình đã chạy và tự báo lỗi.

Mặc định failonerror là false, nên mã thoát khác 0 không tự động làm build thất bại. Mặc định failifexecutionfails là true, nên lỗi khởi chạy thường làm task thất bại.

### 8.1. Dừng build khi lệnh thất bại

Với bước bắt buộc như biên dịch bằng compiler ngoài hoặc kiểm tra artifact, đặt failonerror="true":

~~~xml
<exec executable="git" failonerror="true">
    <arg value="diff" />
    <arg value="--check" />
</exec>
~~~

Nếu Git trả mã khác 0, target và build có thể thất bại ngay. Cách này phù hợp khi bước kiểm tra là điều kiện bắt buộc để tiếp tục pipeline.

### 8.2. Lưu mã thoát để tự xử lý

Nếu muốn build tiếp tục để báo cáo hoặc thực hiện cleanup, đặt resultproperty và giữ failonerror=false:

~~~xml
<exec executable="tool"
      failonerror="false"
      resultproperty="tool.exit">
    <arg value="validate" />
</exec>

<echo message="Tool exit code: ${tool.exit}" />

<condition property="tool.success">
    <equals arg1="${tool.exit}" arg2="0" />
</condition>

<fail unless="tool.success"
      message="External validation failed." />
~~~

Trong ví dụ, Ant lưu mã thoát vào tool.exit. Task condition tạo property tool.success nếu mã là 0. Task fail sau đó làm build thất bại nếu điều kiện không đạt.

Cách này cho phép chèn bước thu thập log hoặc lưu báo cáo trước khi dừng build.

### 8.3. Không thể khởi chạy executable

Thuộc tính failifexecutionfails điều khiển lỗi khởi chạy:

~~~xml
<exec executable="optional-tool"
      failifexecutionfails="false"
      failonerror="false"
      resultproperty="optional-tool.exit">
    <arg value="--version" />
</exec>
~~~

Cấu hình này cho phép bỏ qua một số lỗi thực thi. Tuy nhiên, nếu Ant không thể tạo tiến trình, resultproperty có thể không được thiết lập như một mã thoát hợp lệ. Vì vậy, không nên dùng nó như một cách để bảo đảm luôn có resultproperty.

Chỉ đặt failifexecutionfails="false" khi công cụ thật sự là tùy chọn và build có nhánh xử lý trường hợp công cụ không tồn tại. Với compiler, validator hoặc công cụ tạo artifact bắt buộc, giữ mặc định failifexecutionfails="true".

## 9. Giới hạn thời gian bằng timeout

Một công cụ có thể bị treo do chờ input, kết nối mạng hoặc deadlock. Thuộc tính timeout giới hạn thời gian chạy của tiến trình, tính bằng mili giây.

Ví dụ giới hạn 60 giây:

~~~xml
<exec executable="python"
      dir="tools"
      timeout="60000"
      failonerror="true">
    <arg value="integration_check.py" />
</exec>
~~~

Nếu tiến trình chạy quá thời gian, Ant dừng tiến trình theo cơ chế timeout của task và báo lỗi thực thi. Timeout không thay thế kiểm tra mã thoát: một tiến trình kết thúc sớm với mã khác 0 vẫn cần được xử lý bằng failonerror hoặc resultproperty.

Hãy chọn timeout theo đặc điểm công cụ:

- Lệnh hiển thị phiên bản thường chỉ cần vài giây.
- Kiểm tra tĩnh hoặc chuyển đổi file có thể cần vài phút.
- Tác vụ mạng cần thời gian đủ cho kết nối nhưng phải có giới hạn để CI không chờ vô hạn.

Nếu công cụ có timeout riêng, có thể cấu hình cả timeout của Ant và timeout nội bộ của công cụ. Timeout của Ant là lớp bảo vệ cuối để tiến trình không giữ build quá lâu.

## 10. Chạy tiến trình nền bằng spawn

Mặc định, exec chờ tiến trình kết thúc rồi mới tiếp tục target. Đặt spawn="true" để khởi chạy tiến trình nền và trả quyền điều khiển cho Ant mà không chờ tiến trình hoàn tất:

~~~xml
<exec executable="java" spawn="true">
    <arg value="-jar" />
    <arg value="tools/local-server.jar" />
</exec>
~~~

Cách này có thể dùng khi cần khởi động một dịch vụ cục bộ cho một quy trình bên ngoài. Tuy nhiên, spawn không phù hợp nếu build cần đọc mã thoát, chờ output hoàn tất hoặc kiểm tra kết quả trước khi chạy target tiếp theo.

Các chức năng thu thập stdin, stdout, stderr và resultproperty phụ thuộc vào việc Ant theo dõi tiến trình. Khi spawn=true, không thể dùng quy trình chuyển hướng I/O và thu kết quả thông thường như một lệnh đồng bộ. Hãy kiểm tra tài liệu phiên bản Ant đang dùng trước khi kết hợp các thuộc tính liên quan.

Một tiến trình nền cũng có thể còn chạy sau khi target Ant kết thúc. Buildfile cần có cách dừng tiến trình hoặc quản lý vòng đời dịch vụ, nếu không các lần build tiếp theo có thể đụng cổng hoặc tài nguyên đang bị chiếm.

Nếu cần chạy test, validator hoặc compiler và phải biết thành công/thất bại, giữ spawn=false (mặc định).

## 11. Gọi shell khi cần pipe, redirect hoặc nối lệnh

Task exec không tự xử lý cú pháp shell. Ví dụ sau không hoạt động như mong đợi:

~~~xml
<exec executable="git status --short | grep modified" />
~~~

Ant sẽ cố tìm một executable có tên chứa cả chuỗi đó. Để dùng pipe, cần gọi shell rõ ràng.

### 11.1. Gọi shell trên Linux/macOS

Ví dụ dùng sh -c:

~~~xml
<exec executable="/bin/sh" dir="." failonerror="true">
    <arg value="-c" />
    <arg value="git status --short | grep modified" />
</exec>
~~~

Lệnh sau -c được shell phân tích, nên pipe có ý nghĩa.

### 11.2. Gọi shell trên Windows CMD

Ví dụ dùng cmd.exe /c:

~~~xml
<exec executable="cmd.exe" failonerror="true">
    <arg value="/c" />
    <arg value="ver" />
</exec>
~~~

Các lệnh built-in của CMD như dir, copy hoặc set không phải lúc nào cũng là executable độc lập. Chúng cần được gọi thông qua cmd.exe /c.

### 11.3. Gọi PowerShell

Nếu cần cú pháp PowerShell, gọi powershell.exe hoặc pwsh.exe tùy môi trường:

~~~xml
<exec executable="powershell.exe" failonerror="true">
    <arg value="-NoProfile" />
    <arg value="-NonInteractive" />
    <arg value="-Command" />
    <arg value="Get-ChildItem -File | Select-Object -ExpandProperty Name" />
</exec>
~~~

Trên môi trường có PowerShell 7, có thể dùng pwsh thay cho powershell.exe. Cần xác nhận executable có trên PATH hoặc chỉ định đường dẫn cụ thể.

### 11.4. Shell làm thay đổi cách xử lý quote và ký tự đặc biệt

Khi truyền lệnh qua shell, có nhiều lớp phân tích:

1. XML đọc thuộc tính và entity.
2. Ant phân tích arg.
3. Shell phân tích chuỗi sau -c, /c hoặc -Command.
4. Chương trình cuối cùng nhận đối số.

Vì vậy, quote và escape cần đúng với cả XML lẫn shell. Nếu không cần pipe hoặc redirect, gọi executable trực tiếp bằng arg value sẽ đơn giản và ít rủi ro hơn.

Không nối dữ liệu do người dùng nhập vào chuỗi shell mà không kiểm soát. Một ký tự như ;, |, &, $, dấu nháy hoặc dấu ngoặc có thể mang ý nghĩa điều khiển trong shell. Với tham số dữ liệu thông thường, truyền bằng arg value để tránh để shell diễn giải chúng.

## 12. Chọn lệnh theo hệ điều hành

Một build có thể chạy trên Windows, Linux hoặc macOS. Nếu executable khác nhau theo hệ điều hành, có thể dùng điều kiện os của task exec hoặc các target riêng.

Ví dụ minh họa hai lệnh theo hệ điều hành:

~~~xml
<target name="show-platform">
    <exec executable="cmd.exe" os="Windows 10">
        <arg value="/c" />
        <arg value="ver" />
    </exec>

    <exec executable="/bin/uname" os="Linux">
        <arg value="-a" />
    </exec>
</target>
~~~

Tên hệ điều hành được Ant so sánh với thông tin hệ thống mà JVM cung cấp. Tên có thể khác giữa các bản Windows hoặc JDK, vì vậy hãy kiểm tra giá trị thực tế nếu dùng thuộc tính os để lọc.

Một cách khác là dùng condition để đặt property theo hệ điều hành, sau đó điều phối target riêng. Với build đa nền tảng, tránh viết một lệnh shell dài cố xử lý mọi hệ điều hành trong cùng một chuỗi.

Nếu có thể dùng một công cụ Java hoặc CLI đa nền tảng, ưu tiên nó để giảm số nhánh cấu hình.

## 13. Kiểm soát executable được tìm thấy trong PATH

Khi executable chỉ là tên ngắn như git, Ant và hệ điều hành phải tìm chương trình trong PATH. Điều này thuận tiện nhưng có thể khiến build dùng nhầm phiên bản.

Task exec có thuộc tính resolveExecutable để yêu cầu Ant phân giải executable theo PATH thành đường dẫn thực tế. Tùy chọn này có từ Ant 1.6.3 và mặc định là false.

Ví dụ:

~~~xml
<exec executable="git" resolveExecutable="true">
    <arg value="--version" />
</exec>
~~~

Nếu cần một phiên bản công cụ cố định, cách chắc chắn hơn là cấu hình đường dẫn tuyệt đối qua property hoặc thiết lập PATH của CI một cách rõ ràng. resolveExecutable giúp tìm chương trình nhưng không kiểm tra phiên bản hoặc bảo đảm chương trình đó đúng với yêu cầu của dự án.

Có thể lưu đường dẫn công cụ trong property:

~~~xml
<property name="git.executable" value="git" />

<exec executable="${git.executable}" failonerror="true">
    <arg value="rev-parse" />
    <arg value="--short" />
    <arg value="HEAD" />
</exec>
~~~

Khi cần, build có thể nhận property từ dòng lệnh hoặc file cấu hình để chỉ định executable khác.

## 14. Ví dụ thực tế: lấy commit hash và ghi vào file phiên bản

Một quy trình phát hành có thể ghi commit hash vào file metadata để truy vết artifact.

~~~xml
<project name="inventory" default="build-metadata" basedir=".">
    <property name="build.dir" location="build" />
    <property name="metadata.file"
              location="${build.dir}/build-info.txt" />

    <target name="build-metadata">
        <mkdir dir="${build.dir}" />

        <exec executable="git"
              dir="."
              failonerror="true"
              outputproperty="git.commit">
            <arg value="rev-parse" />
            <arg value="HEAD" />
        </exec>

        <echo file="${metadata.file}"
              message="commit=${git.commit}" />
    </target>
</project>
~~~

Task git chạy trong thư mục repository và trả commit hash qua stdout. Ant lưu output vào property git.commit, sau đó task echo ghi metadata vào file.

Nếu repository không phải Git hoặc build được chạy từ source archive không có thư mục .git, task exec sẽ thất bại. Nếu Git chỉ là tùy chọn, cần kiểm tra điều kiện trước khi gọi hoặc thiết kế nhánh fallback rõ ràng.

Có thể mở rộng metadata bằng version, build timestamp hoặc tên branch, nhưng không nên đưa thông tin bí mật hoặc đường dẫn nội bộ nhạy cảm vào artifact công khai.

## 15. Ví dụ thực tế: gọi compiler hoặc công cụ đóng gói ngoài

Giả sử dự án cần chạy một công cụ CLI để tạo file schema:

~~~xml
<target name="generate-schema">
    <mkdir dir="build/generated" />

    <exec executable="schema-tool"
          dir="."
          timeout="120000"
          failonerror="true">
        <arg value="generate" />
        <arg value="--input" />
        <arg value="src/main/schema" />
        <arg value="--output" />
        <arg value="build/generated" />
        <arg value="--language" />
        <arg value="java" />
    </exec>
</target>
~~~

Target này chỉ hoàn tất khi schema-tool kết thúc thành công. Nếu công cụ trả mã khác 0, build dừng vì failonerror=true. Nếu công cụ không khởi chạy được, failifexecutionfails mặc định cũng làm task thất bại.

Có thể thêm output và error để lưu log riêng:

~~~xml
<exec executable="schema-tool"
      dir="."
      timeout="120000"
      failonerror="true"
      output="build/logs/schema.stdout.log"
      error="build/logs/schema.stderr.log">
    <arg value="generate" />
    <arg value="--input" />
    <arg value="src/main/schema" />
    <arg value="--output" />
    <arg value="build/generated" />
</exec>
~~~

Hãy tạo build/logs trước khi gọi task. Đường dẫn executable và tham số phải phù hợp với CLI thực tế của công cụ.

## 16. Ví dụ thực tế: gọi script theo hệ điều hành

Nếu dự án có script triển khai khác nhau cho Windows và Linux, có thể tách target:

~~~xml
<target name="deploy-linux">
    <exec executable="/bin/sh" dir="." failonerror="true">
        <arg value="scripts/deploy.sh" />
        <arg value="staging" />
    </exec>
</target>

<target name="deploy-windows">
    <exec executable="cmd.exe" dir="." failonerror="true">
        <arg value="/c" />
        <arg value="scripts\deploy.bat staging" />
    </exec>
</target>
~~~

Target tương ứng cần được chọn theo môi trường. Nếu dùng script .bat, gọi qua cmd.exe /c. Nếu dùng script shell, gọi qua /bin/sh hoặc interpreter phù hợp.

Với script cần nhận nhiều đối số, nên truyền từng arg value khi không dùng shell. Nếu gọi qua /c hoặc -c, shell có thể phân tích lại chuỗi và cần xử lý quote theo quy tắc của nó.

## 17. Những lỗi thường gặp

### 17.1. Ant báo không tìm thấy executable

Kiểm tra tên chương trình, PATH của tiến trình Ant, quyền thực thi và đường dẫn tuyệt đối. Trên Windows, xác nhận đúng phần mở rộng .exe, .cmd hoặc .bat và gọi shell phù hợp khi cần.

### 17.2. Tham số có khoảng trắng bị tách sai

Dùng một arg value cho mỗi đối số. Tránh ghép cả command line vào executable hoặc dùng line cho đường dẫn có khoảng trắng phức tạp.

### 17.3. Pipe hoặc redirect không hoạt động

Ant không tự khởi chạy shell. Gọi /bin/sh -c, cmd.exe /c hoặc PowerShell -Command khi thực sự cần cú pháp shell.

### 17.4. Lệnh chạy trong sai thư mục

Đặt dir rõ ràng và kiểm tra đường dẫn tương đối mà chương trình nhận được. Working directory của tiến trình con có thể khác thư mục chứa buildfile.

### 17.5. Build không thất bại dù công cụ trả mã khác 0

Mặc định failonerror=false. Đặt true nếu bước bắt buộc phải thành công, hoặc dùng resultproperty để kiểm tra mã thoát rồi gọi fail ở bước sau.

### 17.6. Build thất bại dù chương trình không trả mã lỗi

Nếu Ant không thể khởi chạy executable, failifexecutionfails mặc định true sẽ làm task thất bại. Đây khác với trường hợp chương trình chạy xong và trả mã khác 0.

### 17.7. Tiến trình chạy mãi

Đặt timeout theo nhu cầu. Đồng thời kiểm tra chương trình có đang chờ stdin, kết nối mạng hoặc một dịch vụ bên ngoài hay không.

### 17.8. Property output không có giá trị

Property được thiết lập sau khi tiến trình kết thúc và chỉ có thể được đặt nếu task thực sự thu được output. Đặt tên property mới cho mỗi lần chạy; Ant property thông thường bất biến.

### 17.9. newenvironment làm công cụ không tìm thấy

Khi newenvironment=true, tiến trình không kế thừa toàn bộ biến môi trường của Ant. Hãy khai báo PATH và các biến cần thiết bằng nested env.

### 17.10. Dùng spawn rồi chờ resultproperty

spawn chạy tiến trình nền và trả quyền điều khiển ngay. Build không thể sử dụng quy trình thu mã thoát thông thường cho một tiến trình chưa hoàn tất. Giữ spawn=false nếu cần kết quả.

## 18. Thực hành tốt khi tích hợp công cụ hệ thống

- **Gọi executable trực tiếp khi có thể.** Dùng executable và arg value thay vì ghép một chuỗi shell.
- **Chỉ gọi shell khi cần shell syntax.** Pipe, redirect, biến shell và nối lệnh cần interpreter tường minh.
- **Tách executable và tham số.** Mỗi arg value là một đối số rõ ràng, đặc biệt với đường dẫn có khoảng trắng.
- **Đặt dir rõ ràng.** Giúp công cụ tìm input và output theo một working directory ổn định.
- **Truyền environment có chủ đích.** Chỉ dùng newenvironment=true khi sẵn sàng cung cấp đầy đủ biến cần thiết.
- **Dừng build khi bước bắt buộc thất bại.** Dùng failonerror=true cho compiler, validator và công cụ tạo artifact.
- **Phân biệt lỗi khởi chạy và mã thoát.** failifexecutionfails xử lý việc không tạo được tiến trình; failonerror xử lý mã thoát khác 0.
- **Đặt timeout cho lệnh có thể treo.** Chọn giới hạn phù hợp với thời gian chạy bình thường.
- **Lưu output khi cần chẩn đoán.** Tách stdout và stderr nếu hai luồng có mục đích khác nhau.
- **Không dùng spawn cho bước cần kết quả.** Build đồng bộ dễ kiểm soát thứ tự và lỗi hơn.
- **Không đưa secret vào command line hoặc log.** Dùng cơ chế secret của CI và tránh echo biến nhạy cảm.
- **Kiểm tra công cụ trong CI.** Xác nhận executable, phiên bản và quyền chạy trong đúng môi trường build.
- **Giữ nhánh theo hệ điều hành tối thiểu.** Nếu có thể dùng CLI đa nền tảng, tránh duy trì nhiều script gần giống nhau.
- **Tài liệu hóa yêu cầu cài đặt.** Ghi rõ công cụ bên ngoài, phiên bản tối thiểu và cách cấu hình đường dẫn.

## 19. Kết luận

Task <exec> cho phép Apache Ant gọi công cụ hệ thống và chương trình bên ngoài trong một quy trình build. Thuộc tính executable xác định chương trình, nested arg truyền tham số, dir đặt thư mục làm việc và env thiết lập biến môi trường. Các thuộc tính input, output, error cùng property tương ứng giúp kết nối stdin, stdout và stderr với buildfile.

Để điều khiển kết quả, dùng failonerror cho mã thoát khác 0, failifexecutionfails cho lỗi không thể khởi chạy tiến trình, resultproperty để lưu mã thoát và timeout để giới hạn thời gian. Task exec không tự phân tích cú pháp shell; khi cần pipe, redirect hoặc nối lệnh, phải gọi shell tường minh. Gọi executable trực tiếp, truyền đối số riêng, đặt working directory và environment rõ ràng giúp build dễ tái tạo, an toàn và dễ chẩn đoán.

## Tài liệu tham khảo

- [Apache Ant Exec Task](https://ant.apache.org/manual/Tasks/exec.html)
- [Apache Ant Exec Task — Environment Variables](https://ant.apache.org/manual/Tasks/exec.html#env)
- [Apache Ant Redirector Type](https://ant.apache.org/manual/Types/redirector.html)

