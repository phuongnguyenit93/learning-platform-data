# Tổ chức thư viện trong ANT_HOME/lib, thư mục người dùng và -lib

Apache Ant có thể mở rộng khả năng build bằng các thư viện bổ sung: thư viện cung cấp task mới, kiểu dữ liệu mới, hoặc phần phụ trợ mà một task có sẵn cần dùng. Để Ant có thể nạp những lớp Java này, JAR phải nằm trên **classpath của chính Ant** tại thời điểm Ant khởi động.

Ant cung cấp ba vị trí phổ biến để tổ chức thư viện mở rộng:

- **ANT_HOME/lib**: thư viện dùng chung trong một bản cài đặt Ant.
- **~/.ant/lib**: thư viện riêng của tài khoản người dùng đang chạy Ant.
- **-lib**: bổ sung đường dẫn thư viện cho một lần gọi Ant.

Ba cách này có phạm vi ảnh hưởng và cách quản lý khác nhau. Chọn đúng vị trí giúp build dễ cài đặt, dễ chia sẻ và tránh việc một dự án vô tình phụ thuộc vào cấu hình riêng trên máy của người phát triển.

## 1. Ant cần thư viện ở classpath nào?

Cần phân biệt classpath của Ant với classpath của ứng dụng đang được build.

**Classpath của Ant** được dùng để nạp các lớp thực thi công cụ build, chẳng hạn:

- Lớp triển khai một custom task.
- Lớp cung cấp một kiểu dữ liệu hoặc bộ chuyển đổi tùy chỉnh.
- Thư viện phụ thuộc mà custom task cần để hoạt động.
- Thư viện hỗ trợ cho một task mở rộng.

Ví dụ, một JAR chứa lớp **com.example.ant.GenerateReportTask** phải được Ant nhìn thấy trước khi build file khai báo và gọi task đó.

**Classpath của ứng dụng** lại phục vụ quá trình biên dịch hoặc chạy chương trình Java. Nó thường được cấu hình trong các task như **javac** và **java**:

~~~xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       classpath="lib/application-dependency.jar"/>
~~~

Thuộc tính **classpath** ở đây cung cấp dependency cho trình biên dịch Java. Nó không tự đưa JAR vào classpath khởi động của Ant và không làm cho một custom task mới có thể được Ant nạp.

Có thể hình dung hai phạm vi như sau:

~~~text
Ant launcher
    |
    +-- Classpath của Ant
    |      +-- ANT_HOME/lib
    |      +-- thư mục thư viện của người dùng
    |      +-- các đường dẫn bổ sung qua -lib
    |      |
    |      +-- custom task / custom type / thư viện phụ trợ
    |
    +-- Đọc build.xml và thực thi các target
           |
           +-- javac / java
                  |
                  +-- Classpath của ứng dụng
                         +-- dependency của mã nguồn hoặc chương trình
~~~

Nếu lỗi báo Ant không tìm thấy task hoặc không nạp được lớp triển khai task, hãy kiểm tra classpath của Ant. Nếu lỗi xảy ra khi biên dịch hoặc chạy ứng dụng vì thiếu một dependency, hãy kiểm tra classpath của ứng dụng.

## 2. Thư viện dùng chung trong ANT_HOME/lib

**ANT_HOME** thường trỏ đến thư mục cài đặt Apache Ant. Bên trong thư mục này có thư mục **lib**, nơi Ant launcher tự tìm các JAR thư viện của Ant và các thư viện mở rộng được cài đặt cùng bản Ant đó.

Ví dụ cấu trúc thư mục:

~~~text
apache-ant/
├── bin/
│   ├── ant
│   └── ant.bat
├── lib/
│   ├── ant.jar
│   ├── ant-launcher.jar
│   ├── custom-task.jar
│   └── custom-task-dependency.jar
└── ...
~~~

Trên Windows, vị trí thường có dạng:

~~~text
%ANT_HOME%\lib
~~~

Trên Linux hoặc macOS:

~~~text
$ANT_HOME/lib
~~~

Khi Ant được khởi chạy bằng bản cài đặt này, các JAR trong thư mục **ANT_HOME/lib** được đưa vào classpath của Ant. Vì thế, custom task có thể được khai báo trong build file mà không cần chỉ định lại đường dẫn JAR ở từng dự án.

Ví dụ build file sử dụng một custom task:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="report-build" default="report">

    <taskdef name="generate-report"
             classname="com.example.ant.GenerateReportTask"/>

    <target name="report">
        <generate-report output="build/report.html"/>
    </target>

</project>
~~~

Nếu JAR chứa **GenerateReportTask** đã được cài trong **ANT_HOME/lib**, Ant có thể nạp lớp khi xử lý phần tử **taskdef**.

**Phạm vi ảnh hưởng:** thư viện trong **ANT_HOME/lib** thường được mọi người dùng chung bản cài đặt Ant đó nhìn thấy. Đây là lựa chọn phù hợp khi tổ chức muốn quản trị tập trung một bộ task mở rộng cho nhiều dự án và nhiều tài khoản trên cùng môi trường.

Tuy nhiên, thay đổi thư mục này có thể ảnh hưởng đến mọi build dùng bản Ant tương ứng. Một JAR mới có thể xung đột phiên bản với thư viện khác, làm thay đổi hành vi của task hoặc khiến một dự án cũ không còn chạy được. Trên máy do hệ điều hành hoặc công cụ quản trị cài Ant, thư mục cài đặt cũng có thể yêu cầu quyền quản trị khi ghi.

Do đó, chỉ nên đặt vào đây những thư viện đã được xác định là thành phần dùng chung và được quản lý phiên bản rõ ràng.

## 3. Thư viện riêng của tài khoản người dùng: ~/.ant/lib

Ant cũng hỗ trợ thư mục thư viện riêng theo tài khoản người dùng. Đường dẫn mặc định thường được biểu diễn là:

~~~text
${user.home}/.ant/lib
~~~

Trong đó **user.home** là thuộc tính thư mục home mà JVM sử dụng cho tiến trình Ant.

Đường dẫn thường gặp:

| Hệ điều hành | Thư mục thư viện người dùng |
|---|---|
| Windows | **%USERPROFILE%\.ant\lib** |
| Linux | **$HOME/.ant/lib** |
| macOS | **$HOME/.ant/lib** |

Ví dụ, một người dùng Windows có thể có cấu trúc:

~~~text
C:\Users\developer\
└── .ant/
    └── lib/
        ├── custom-task.jar
        └── custom-task-dependency.jar
~~~

Trên Linux hoặc macOS:

~~~text
/home/developer/
└── .ant/
    └── lib/
        ├── custom-task.jar
        └── custom-task-dependency.jar
~~~

Nếu thư mục chưa tồn tại, có thể tự tạo **.ant/lib** rồi chép các JAR cần thiết vào đó. Khi Ant launcher chạy dưới tài khoản này, các JAR trong thư mục người dùng được nạp như thư viện bổ sung của Ant.

**Phạm vi ảnh hưởng:** thư viện chỉ gắn với tài khoản người dùng tương ứng. Người dùng khác trên cùng máy không tự động nhận được thư viện này. Cách tổ chức này hữu ích khi một cá nhân cần custom task cho nhiều dự án nhưng không có quyền sửa bản cài đặt Ant dùng chung.

Điểm cần lưu ý là cấu hình này tạo ra một dependency ngầm theo máy và tài khoản. Một build có thể chạy trên máy của người phát triển vì JAR đã nằm trong **.ant/lib**, nhưng thất bại trên máy CI hoặc máy của đồng nghiệp nếu họ chưa cài thư viện đó.

Vì vậy, không nên coi thư mục người dùng là nơi lưu trữ dependency bắt buộc của một dự án cần được tái tạo trên nhiều máy. Hãy ghi lại yêu cầu môi trường hoặc đưa cách cung cấp thư viện vào quy trình build của dự án.

## 4. Bổ sung thư viện cho một lần chạy bằng -lib

Tùy chọn **-lib** cho phép thêm đường dẫn vào classpath của Ant ngay khi gọi lệnh. Đây là cách linh hoạt khi cần thử nghiệm một thư viện, chạy một dự án với bộ task riêng hoặc thiết lập môi trường build mà không thay đổi thư mục cài đặt và thư mục người dùng.

Cú pháp cơ bản:

~~~bash
ant -lib path/to/library.jar target-name
~~~

Ví dụ trên Windows:

~~~powershell
ant -lib "C:\tools\ant-extra\custom-task.jar" report
~~~

Ví dụ trên Linux hoặc macOS:

~~~bash
ant -lib "$HOME/tools/ant-extra/custom-task.jar" report
~~~

Nếu custom task có các JAR phụ thuộc, có thể khai báo nhiều tùy chọn **-lib**:

~~~bash
ant \
  -lib "tools/ant-extra/custom-task.jar" \
  -lib "tools/ant-extra/custom-task-dependency.jar" \
  report
~~~

Trên PowerShell:

~~~powershell
ant `
  -lib "C:\tools\ant-extra\custom-task.jar" `
  -lib "C:\tools\ant-extra\custom-task-dependency.jar" `
  report
~~~

Có thể dùng **-lib** nhiều lần trong cùng lệnh. Mỗi đường dẫn có thể chỉ đến JAR/ZIP hoặc một thư mục chứa các lớp đã biên dịch theo cấu trúc package. Nếu thư mục chỉ chứa các JAR khác, hãy chỉ định từng JAR cần nạp bằng **-lib** hoặc đặt chúng trong một thư mục thư viện được Ant launcher tự quét như **ANT_HOME/lib** hay **.ant/lib**.

Tùy chọn này có các đặc điểm:

- Chỉ áp dụng cho tiến trình Ant được khởi chạy bằng lệnh đó.
- Không cần sửa **ANT_HOME** hoặc thư mục thư viện của người dùng.
- Có thể chỉ định nhiều thư viện bằng nhiều tùy chọn **-lib**.
- Người chạy lệnh phải cung cấp đúng đường dẫn trên máy hiện tại.
- Khi gọi Ant ở lần tiếp theo, cần truyền lại các tùy chọn nếu vẫn muốn dùng các thư viện đó.

Do đó, **-lib** phù hợp cho thao tác thử nghiệm, build cục bộ có chủ đích hoặc script gọi Ant đã quản lý rõ các JAR cần thiết.

### Ví dụ build file sử dụng thư viện được cung cấp qua -lib

Giả sử JAR **custom-task.jar** chứa lớp **com.example.ant.GenerateReportTask**. Build file có thể khai báo:

~~~xml
<project name="report-build" default="report">

    <taskdef name="generate-report"
             classname="com.example.ant.GenerateReportTask"/>

    <target name="report">
        <generate-report output="build/report.html"/>
    </target>

</project>
~~~

Gọi build:

~~~bash
ant -lib "tools/ant-extra/custom-task.jar" report
~~~

Ant launcher nạp JAR vào classpath của Ant trước khi xử lý build file. Khi đến **taskdef**, Ant có thể tìm thấy lớp triển khai custom task.

Nếu lớp triển khai cần thêm thư viện phụ trợ, các JAR đó cũng phải có mặt trên classpath của Ant:

~~~bash
ant \
  -lib "tools/ant-extra/custom-task.jar" \
  -lib "tools/ant-extra/report-engine.jar" \
  report
~~~

Đưa riêng JAR của custom task vào classpath nhưng bỏ sót dependency của nó có thể dẫn đến lỗi **ClassNotFoundException** hoặc **NoClassDefFoundError** khi Ant nạp hay thực thi task.

## 5. So sánh ba vị trí tổ chức thư viện

| Tiêu chí | **ANT_HOME/lib** | **~/.ant/lib** | **-lib** |
|---|---|---|---|
| Phạm vi | Bản cài đặt Ant | Tài khoản người dùng | Một lần gọi Ant |
| Nơi cấu hình | Thư mục Ant | Thư mục home | Dòng lệnh hoặc script |
| Có cần sửa cài đặt Ant? | Có | Không | Không |
| Người dùng khác có tự dùng được? | Thường có nếu dùng chung bản Ant | Không | Chỉ khi họ chạy lệnh có cùng tham số |
| Phù hợp | Môi trường dùng chung, quản trị tập trung | Công cụ cá nhân | Thử nghiệm hoặc build có cấu hình tường minh |
| Rủi ro chính | Ảnh hưởng nhiều dự án dùng cùng Ant | Dependency ngầm theo tài khoản | Quên truyền tham số hoặc sai đường dẫn |

Có thể chọn theo câu hỏi sau:

- Nếu thư viện là thành phần chuẩn mà mọi dự án trên một bản Ant cần dùng, quản trị nó trong **ANT_HOME/lib**.
- Nếu thư viện chỉ phục vụ công việc cá nhân và không muốn thay đổi cài đặt Ant chung, dùng **~/.ant/lib**.
- Nếu chỉ cần thư viện cho một lần chạy hoặc muốn script chỉ rõ dependency cần nạp, dùng **-lib**.

Không nên đặt cùng một thư viện ở cả ba nơi nếu không có lý do cụ thể. Việc lặp lại nhiều bản sao có thể gây khó hiểu khi nâng cấp hoặc điều tra xung đột phiên bản.

## 6. Thư viện trong build file và classpath của taskdef

Ngoài các vị trí do Ant launcher quản lý, build file có thể chỉ định classpath trực tiếp cho một khai báo task hoặc type. Cách này hữu ích khi thư viện thuộc riêng một dự án và muốn thể hiện đường dẫn ngay trong cấu hình build.

Ví dụ:

~~~xml
<project name="report-build" default="report">

    <taskdef name="generate-report"
             classname="com.example.ant.GenerateReportTask">
        <classpath>
            <pathelement location="tools/ant-extra/custom-task.jar"/>
            <pathelement location="tools/ant-extra/report-engine.jar"/>
        </classpath>
    </taskdef>

    <target name="report">
        <generate-report output="build/report.html"/>
    </target>

</project>
~~~

Trong ví dụ này, phần tử **classpath** lồng bên trong **taskdef** cung cấp các JAR cho việc nạp lớp task. Khi đường dẫn được quản lý trong repository của dự án, nhóm có thể xem và cập nhật cấu hình cùng với build file.

Cần phân biệt:

- **-lib** bổ sung thư viện ở cấp Ant launcher, trước khi build file được xử lý.
- **classpath** trong **taskdef** gắn với việc nạp lớp cho định nghĩa task/type tương ứng.
- **classpath** của **javac** hoặc **java** phục vụ dependency của ứng dụng.

Chọn đúng cấp cấu hình giúp giới hạn phạm vi ảnh hưởng và làm rõ thư viện đang phục vụ công cụ build hay chương trình được build.

## 7. Quản lý phiên bản và tránh xung đột thư viện

Các thư viện trong **ANT_HOME/lib** và **.ant/lib** có thể được nhiều dự án sử dụng. Vì thế, nâng cấp một JAR ở các vị trí này có thể làm thay đổi kết quả của những build không hề được chỉnh sửa.

Một số nguyên tắc quản lý hữu ích:

**Giữ phiên bản rõ ràng.** Ghi lại tên và phiên bản của custom task cùng các thư viện phụ thuộc. Tránh thay JAR bằng một bản mới nhưng giữ nguyên tên file khiến người khác không biết môi trường đã thay đổi.

**Không để nhiều phiên bản cùng một thư viện trên classpath.** Nếu hai JAR cung cấp cùng một lớp hoặc các phiên bản API không tương thích, kết quả nạp lớp có thể phụ thuộc vào thứ tự classpath. Hãy loại bỏ bản không cần thiết và thống nhất phiên bản được dùng.

**Quản lý cả dependency bắc cầu.** JAR của custom task có thể phụ thuộc vào một hoặc nhiều thư viện khác. Cần cung cấp đủ các JAR đó trong cùng phạm vi classpath. Chỉ cài JAR chính mà thiếu dependency sẽ khiến task lỗi khi nạp hoặc chạy.

**Ghi lại yêu cầu môi trường.** Nếu build bắt buộc một custom task nằm trong **ANT_HOME/lib** hoặc **.ant/lib**, tài liệu cài đặt cần nói rõ điều đó. Nếu có thể, hãy để script build truyền **-lib** hoặc cấu hình classpath của task một cách tường minh.

**Kiểm tra trên môi trường sạch.** Build chạy thành công trên máy cá nhân chưa chứng minh rằng mọi dependency đã được khai báo. Thử chạy với tài khoản hoặc máy không có các JAR tùy chỉnh trong thư mục người dùng sẽ giúp phát hiện dependency ngầm.

**Tin cậy nguồn JAR.** JAR trên classpath của Ant có thể chứa mã được thực thi trong quá trình build. Chỉ sử dụng thư viện từ nguồn đáng tin cậy và quản lý quyền ghi vào các thư mục thư viện dùng chung.

## 8. Kiểm tra cấu hình thư viện khi Ant không tìm thấy task

Khi Ant báo không tìm thấy custom task, có thể kiểm tra theo thứ tự:

1. Xác nhận đang gọi đúng bản Ant và đúng **ANT_HOME**.
2. Kiểm tra JAR thực sự tồn tại trong thư mục dự kiến.
3. Kiểm tra JAR có chứa lớp được khai báo trong **classname** hay không.
4. Kiểm tra các JAR phụ thuộc của lớp task đã được cung cấp đầy đủ.
5. Kiểm tra Ant được chạy bằng tài khoản nào để xác định đúng thư mục **.ant/lib**.
6. Nếu dùng **-lib**, kiểm tra lệnh có truyền đúng đường dẫn cho lần gọi hiện tại hay không.

Một số lệnh hữu ích:

~~~bash
ant -version
ant -diagnostics
ant -verbose report
~~~

- **ant -version** cho biết phiên bản Ant đang được gọi.
- **ant -diagnostics** cung cấp thông tin chẩn đoán về môi trường Ant và JVM.
- **ant -verbose report** hiển thị thêm thông tin trong lúc chạy target, hữu ích khi lần theo quá trình nạp và thực thi task.

Nếu cần kiểm tra xem một thư viện trong thư mục người dùng có làm thay đổi hành vi hay không, có thể chạy Ant với tùy chọn **-nouserlib**:

~~~bash
ant -nouserlib report
~~~

Tùy chọn này yêu cầu Ant không sử dụng các JAR trong thư mục thư viện người dùng. Nếu build chỉ lỗi sau khi tắt thư viện người dùng, hãy kiểm tra dependency mà build đang lấy từ **.ant/lib**. Đây là cách khoanh vùng vấn đề trong môi trường, không phải cách sửa lâu dài nếu task thực sự cần thư viện đó.

## 9. Tổ chức thư viện trong môi trường nhóm và CI

Một dự án có thể chạy trên nhiều máy phát triển và trên máy CI. Nếu custom task chỉ được cài thủ công vào **ANT_HOME/lib** của một máy, build sẽ phụ thuộc vào trạng thái riêng của máy đó.

Có thể cân nhắc các cách tổ chức sau:

**Môi trường phát triển cá nhân:** dùng **.ant/lib** nếu thư viện phục vụ nhiều dự án cá nhân. Ghi lại tên và phiên bản thư viện để có thể cài lại trên máy khác.

**Máy build dùng chung:** quản trị **ANT_HOME/lib** như một phần của bộ công cụ build đã được chuẩn hóa. Khi thay đổi thư viện, cần cập nhật và kiểm tra bản cài đặt Ant được nhóm sử dụng.

**CI hoặc script build:** truyền **-lib** với các JAR đã được cung cấp trong workspace hoặc trong thư mục công cụ đã chuẩn bị. Script phải chỉ rõ các dependency cần thiết để lần chạy có thể tái tạo được.

Ví dụ script gọi Ant với thư viện trong workspace:

~~~bash
ant \
  -lib "tools/ant/custom-task.jar" \
  -lib "tools/ant/report-engine.jar" \
  package
~~~

Đường dẫn trong ví dụ là tương đối với thư mục làm việc nơi lệnh được gọi. CI cần bảo đảm các JAR đó đã được checkout, tải về hoặc chuẩn bị trước khi chạy lệnh.

Nếu thư viện được tải từ kho artifact, nên khóa phiên bản cụ thể và kiểm soát nguồn tải. Không nên dựa vào một file JAR được chép thủ công mà không biết phiên bản hoặc nguồn gốc.

Một môi trường build dễ tái tạo phải trả lời được: Ant phiên bản nào được dùng, custom task nào cần thiết, các JAR nằm ở đâu, phiên bản nào được nạp và script nào cung cấp chúng.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Giải thích |
|---|---|
| Đặt JAR vào thư mục **lib** của dự án là Ant tự nạp | Thư mục **lib** của dự án không tự động trở thành classpath của Ant. Cần dùng **-lib**, cấu hình **taskdef** hoặc một vị trí thư viện mà launcher quản lý. |
| **javac classpath** giúp Ant tìm thấy custom task | Classpath của **javac** phục vụ biên dịch ứng dụng, không phải classpath khởi động của Ant. |
| **~/.ant/lib** dùng chung cho mọi tài khoản | Đây là thư mục theo tài khoản người dùng chạy Ant. |
| **ANT_HOME/lib** chỉ ảnh hưởng một dự án | Nó ảnh hưởng đến các lần chạy sử dụng cùng bản cài đặt Ant. |
| Dùng **-lib** một lần thì lần chạy sau vẫn có thư viện | **-lib** chỉ áp dụng cho tiến trình được gọi với tham số đó. |
| Chỉ cần JAR custom task, không cần dependency | Nếu lớp task phụ thuộc JAR khác, các JAR đó cũng phải có mặt trên classpath thích hợp. |
| Một thư viện có thể được chép vào nhiều nơi mà không có tác động | Nhiều bản sao hoặc nhiều phiên bản có thể gây xung đột và khó xác định lớp nào được nạp. |

## 11. Nguyên tắc lựa chọn

Khi tổ chức thư viện mở rộng cho Apache Ant, hãy bắt đầu từ phạm vi sử dụng:

- **Dùng chung theo bản cài đặt:** đặt JAR trong **ANT_HOME/lib** và quản lý tập trung.
- **Dùng riêng theo tài khoản:** đặt JAR trong **~/.ant/lib**, đồng thời ghi nhận đây là cấu hình môi trường cá nhân.
- **Dùng riêng cho một lần gọi:** truyền JAR qua **-lib** để lệnh build thể hiện rõ thư viện cần nạp.
- **Dùng riêng cho một định nghĩa task trong dự án:** cân nhắc khai báo classpath lồng trong **taskdef** để đường dẫn nằm cùng build file.

Điều quan trọng là xác định đúng classpath mà thư viện cần tham gia. Thư viện mở rộng Ant phải được Ant launcher hoặc định nghĩa task nạp; dependency của chương trình Java phải được cấu hình cho task biên dịch hoặc chạy ứng dụng. Khi phân biệt được hai phạm vi và chọn vị trí lưu thư viện theo đúng phạm vi sử dụng, việc cài đặt, nâng cấp và tái tạo môi trường build sẽ dễ kiểm soát hơn.

