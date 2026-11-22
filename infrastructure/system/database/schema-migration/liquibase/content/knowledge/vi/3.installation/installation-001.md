# Chuẩn bị Java, Liquibase CLI và trình điều khiển JDBC

## 1. Mục tiêu và bối cảnh

Để Liquibase quản lý thay đổi cơ sở dữ liệu, máy thực thi migration phải có môi trường Java phù hợp, công cụ Liquibase và khả năng kết nối đến hệ quản trị cơ sở dữ liệu. Một lỗi ở bất kỳ mắt xích nào — Java không khởi động, CLI không tìm thấy, thiếu JDBC driver, sai URL hoặc thiếu quyền — đều khiến quy trình triển khai schema không thể bắt đầu.

Bài học thuộc chương **Cài đặt** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở bài này, chúng ta chuẩn bị nền tảng chạy công cụ trước khi thực hiện các migration thật.

Sau khi học, bạn cần có khả năng:

- Kiểm tra môi trường Java và chọn phiên bản Java tương thích với bản Liquibase dự định sử dụng.
- Cài Liquibase Command Line Interface (CLI), xác minh lệnh hoạt động và nhận biết nơi cấu hình của CLI được đọc.
- Hiểu vai trò của JDBC driver, chọn đúng driver cho database và đưa thư viện vào classpath.
- Cấu hình một kết nối mẫu, giữ bí mật thông tin xác thực và kiểm tra kết nối trước khi thay đổi schema.
- Phân biệt vấn đề do Java, do Liquibase, do JDBC, do mạng và do quyền của tài khoản database.

Bài sử dụng **PostgreSQL** làm ví dụ thống nhất, nhưng phương pháp chuẩn bị áp dụng tương tự cho MySQL, MariaDB, SQL Server, Oracle và các hệ quản trị được Liquibase hỗ trợ. Cú pháp, phiên bản tương thích và thành phần có sẵn trong bộ cài có thể thay đổi giữa các phiên bản Liquibase; khi triển khai thực tế, phải đối chiếu tài liệu phát hành của đúng bản đang dùng.

## 2. Ba thành phần cần chuẩn bị tương tác với nhau thế nào?

Ở cách dùng CLI trực tiếp, đường đi của một lệnh Liquibase có thể hình dung như sau:

~~~text
Người vận hành / CI pipeline
          |
          v
   Liquibase CLI
          |
          v
  Môi trường thực thi Java
          |
          +--> Đọc changelog và cấu hình Liquibase
          |
          +--> Nạp JDBC driver (*.jar)
                     |
                     v
                 JDBC URL
                     |
                     v
           Máy chủ cơ sở dữ liệu
                     |
                     v
       Schema + lịch sử DATABASECHANGELOG
~~~

**Java** cung cấp môi trường để các thành phần Liquibase chạy. **Liquibase CLI** nhận tham số, đọc changelog và điều khiển quá trình kiểm tra hoặc thực thi migration. **JDBC driver** là thư viện cho phép ứng dụng Java nói chuyện với một loại database cụ thể. **Database** phải đang chạy, cho phép kết nối từ máy thực thi và cấp đúng quyền cho tài khoản migration.

Các bước kiểm tra nên đi từ ngoài vào trong: đầu tiên chạy được Java, tiếp theo gọi được Liquibase, rồi xác minh driver và cuối cùng kiểm tra kết nối đến database. Cách làm này giúp thu hẹp lỗi nhanh hơn.

| Thành phần | Cần chuẩn bị | Cách kiểm tra cơ bản |
|---|---|---|
| Java | JDK hoặc runtime tương thích theo bản Liquibase được chọn | Lệnh java -version; nếu dùng JDK, thêm javac -version |
| Liquibase CLI | Bộ cài chính thức, đường dẫn thực thi và cấu hình môi trường | Lệnh liquibase --version |
| JDBC driver | File JAR phù hợp với loại database, phiên bản Java và hệ quản trị | Driver nằm trong classpath, Liquibase nạp được lớp driver |
| Database | Máy chủ hoạt động, database/schema tồn tại, có mạng và tài khoản hợp lệ | Kiểm tra host/port, xác thực và thử lệnh Liquibase kết nối |
| Changelog | Tệp đầu vào đúng định dạng và đường dẫn truy cập được | Lệnh liquibase validate sau khi cấu hình đủ điều kiện |

## 3. Chuẩn bị Java

### 3.1. Phân biệt JDK, JRE và JAVA_HOME

Java Development Kit (**JDK**) bao gồm công cụ để phát triển Java như trình biên dịch javac và môi trường để chạy ứng dụng Java. Java Runtime Environment (**JRE**) tập trung vào khả năng chạy ứng dụng. Trong dự án Java hoặc Spring Boot, nên dùng JDK vì ngoài Liquibase, quá trình phát triển và build cũng cần trình biên dịch. Một số bộ cài Liquibase hoặc môi trường đóng gói có thể cung cấp runtime riêng; không nên giả định tất cả các kiểu phân phối đều như nhau.

**JAVA_HOME** là biến môi trường thường được công cụ Java dùng để tìm thư mục cài Java. **PATH** là danh sách thư mục hệ điều hành tìm kiếm khi người dùng gọi lệnh. Nếu JAVA_HOME trỏ đến bản Java không phù hợp hoặc PATH chứa nhiều bản Java theo thứ tự khó kiểm soát, CLI có thể chạy với runtime khác bản bạn mong đợi.

Không có một phiên bản Java duy nhất phù hợp với mọi bản Liquibase và JDBC driver. Trước khi tải xuống, nên xác nhận ba thông tin trong tài liệu chính thức: yêu cầu Java của phiên bản Liquibase, yêu cầu Java của JDBC driver và phiên bản JDK dự án đang dùng. Chọn một tổ hợp đã được hỗ trợ thay vì chỉ chọn bản mới nhất theo thói quen.

### 3.2. Kiểm tra Java trên Windows PowerShell

~~~powershell
java -version
javac -version
$env:JAVA_HOME
Get-Command java
~~~

Ý nghĩa:

- **java -version**: xác nhận Java có thể thực thi và hiển thị phiên bản runtime.
- **javac -version**: kiểm tra bộ biên dịch khi đã cài JDK.
- **$env:JAVA_HOME**: xem đường dẫn JDK được cấu hình cho phiên PowerShell hiện tại.
- **Get-Command java**: xem hệ điều hành đang phân giải lệnh java đến tệp nào.

Ví dụ, nếu lệnh java hoạt động nhưng javac không được tìm thấy, có thể máy đang dùng runtime không chứa bộ biên dịch hoặc PATH chưa trỏ tới thư mục bin của JDK. Tình trạng đó không luôn ngăn CLI hoạt động, nhưng sẽ ảnh hưởng việc phát triển ứng dụng Java.

Để cấu hình Java trên Windows, cài JDK từ nhà cung cấp đáng tin cậy, đặt JAVA_HOME trỏ tới **thư mục gốc JDK**, rồi thêm thư mục **bin** của JDK vào PATH. Đóng và mở terminal mới trước khi kiểm tra lại. Không đặt JAVA_HOME trỏ thẳng tới tệp java.exe hoặc tới thư mục bin.

Ví dụ mô tả đường dẫn, cần thay bằng thư mục thực tế:

~~~text
JAVA_HOME = C:\Program Files\Java\<jdk-directory>
PATH      = ...;%JAVA_HOME%\bin
~~~

Ký hiệu trong dấu ngoặc nhọn ở ví dụ trên chỉ là phần cần thay, không phải một đường dẫn có thể sử dụng nguyên văn.

### 3.3. Kiểm tra Java trên macOS hoặc Linux

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
command -v java
~~~

Trên các hệ điều hành này, cấu hình JAVA_HOME và PATH phụ thuộc cách cài JDK, shell và môi trường chạy dịch vụ. Một lệnh hoạt động trong terminal cá nhân chưa chắc hoạt động trong tiến trình CI hoặc container vì chúng có bộ biến môi trường khác nhau.

### 3.4. Tiêu chí hoàn tất bước Java

Bước Java được coi là chuẩn bị tốt khi lệnh java chạy ổn định, phiên bản đáp ứng yêu cầu Liquibase, người vận hành biết runtime đang được chọn từ đâu và môi trường CI/CD có thể dùng cùng dòng phiên bản Java. Ghi nhận phiên bản đã kiểm thử để tránh thay đổi runtime ngoài ý muốn giữa các môi trường.

## 4. Cài đặt Liquibase CLI

### 4.1. CLI là gì và khác gì thư viện liquibase-core?

**Liquibase CLI** là công cụ chạy trực tiếp từ terminal để kiểm tra changelog, xem migration đang chờ và thực thi lệnh quản trị schema. Đây là lựa chọn phù hợp để học Liquibase độc lập với ứng dụng hoặc để pipeline CI/CD thực hiện migration theo một bước riêng.

**liquibase-core** là thư viện Java có thể được đưa vào ứng dụng như Spring Boot để khởi chạy Liquibase theo vòng đời ứng dụng. Nếu đang kiểm tra CLI, bạn phải bảo đảm CLI có driver và cấu hình kết nối của chính nó; việc đã thêm JDBC driver vào dependencies của ứng dụng Spring Boot không tự động làm driver đó xuất hiện trong classpath của CLI.

Có thể sử dụng cả CLI và thư viện trong cùng một dự án, nhưng nên chỉ định rõ công cụ nào chịu trách nhiệm chạy migration trên một database ở từng giai đoạn phát hành.

### 4.2. Các bước cài CLI theo cách thủ công

1. Truy cập kênh phân phối chính thức của Liquibase và chọn bản CLI tương thích với hệ điều hành, Java và yêu cầu của dự án.
2. Tải bản phân phối phù hợp, kiểm tra nguồn tải và checksum hoặc chữ ký nếu nhà phát hành cung cấp.
3. Giải nén hoặc cài đặt theo hướng dẫn của đúng gói đã tải.
4. Xác định tệp lệnh thực thi Liquibase và thêm thư mục chứa nó vào PATH nếu muốn gọi lệnh từ mọi thư mục.
5. Mở terminal mới rồi chạy lệnh kiểm tra phiên bản.
6. Ghi nhận phiên bản CLI vào tài liệu môi trường hoặc cấu hình pipeline để việc chạy trên các máy được tái lập.

Ví dụ trên Windows, sau khi cài đặt ở một thư mục riêng, cấu trúc có thể như sau (tên tệp cụ thể tùy bộ cài):

~~~text
C:\Tools\Liquibase\
    liquibase.bat
    ...
~~~

Bạn có thể gọi trực tiếp tệp batch nếu chưa thêm PATH:

~~~powershell
& "C:\Tools\Liquibase\liquibase.bat" --version
~~~

Sau khi PATH được cấu hình:

~~~powershell
liquibase --version
Get-Command liquibase
~~~

Trên Linux/macOS, cách gọi tùy bộ cài, thường có thể kiểm tra bằng:

~~~bash
liquibase --version
command -v liquibase
~~~

Nếu CLI hiển thị phiên bản nhưng Java hệ thống chưa được tìm thấy, hãy kiểm tra loại gói cài đã sử dụng: một số cách phân phối có cơ chế cung cấp runtime riêng. Mục tiêu là hiểu **runtime thực tế** đang được dùng, không chỉ thấy một lệnh trả về thành công.

### 4.3. Cố định phiên bản CLI khi làm việc nhóm

Không nên để mỗi người dùng một bản CLI tùy ý nếu dự án yêu cầu kết quả migration có thể tái lập. Các phiên bản có thể thay đổi cú pháp lệnh, cách xử lý changelog, tính năng được hỗ trợ hoặc yêu cầu Java. Với CI/CD, nên cố định phiên bản CLI trong image hoặc quy trình cài đặt; khi nâng cấp, thử lại validate, SQL dự kiến và migration trên database kiểm thử.

Có thể tìm hướng dẫn chính thức tại trang tài liệu Liquibase: https://docs.liquibase.com/. Dựa vào tài liệu đúng phiên bản sẽ tránh nhầm giữa cú pháp lệnh cũ và mới.

## 5. Chuẩn bị JDBC driver

### 5.1. JDBC driver là gì?

Java Database Connectivity (**JDBC**) cung cấp API chuẩn để chương trình Java làm việc với cơ sở dữ liệu. Mỗi hệ quản trị thường có driver riêng thực thi giao thức kết nối của nó. Driver thường được phân phối dưới dạng tệp JAR.

Liquibase dùng JDBC driver để mở kết nối đến database, đọc metadata và thực thi câu lệnh SQL. Nếu thiếu driver, Liquibase có thể đọc được tệp changelog nhưng sẽ không kết nối được với cơ sở dữ liệu đích.

Ba thông tin cần phân biệt:

- **JDBC URL**: địa chỉ và thông số kết nối, gồm loại database, host, port và tên database hoặc service.
- **Driver class**: lớp Java triển khai driver, chẳng hạn org.postgresql.Driver.
- **Driver JAR**: tệp thư viện chứa lớp driver, phải hiện diện trong classpath của tiến trình Liquibase.

### 5.2. Một số driver và JDBC URL phổ biến

| Hệ quản trị | Driver class thường dùng | Ví dụ JDBC URL |
|---|---|---|
| PostgreSQL | org.postgresql.Driver | jdbc:postgresql://localhost:5432/liquibase_demo |
| MySQL | com.mysql.cj.jdbc.Driver | jdbc:mysql://localhost:3306/liquibase_demo |
| MariaDB | org.mariadb.jdbc.Driver | jdbc:mariadb://localhost:3306/liquibase_demo |
| SQL Server | com.microsoft.sqlserver.jdbc.SQLServerDriver | jdbc:sqlserver://localhost:1433;databaseName=liquibase_demo |
| Oracle | oracle.jdbc.OracleDriver | jdbc:oracle:thin:@//localhost:1521/ORCLPDB1 |

Các URL là **ví dụ cú pháp**, không khẳng định máy chủ hay database tương ứng đã tồn tại. Tham số SSL/TLS, xác thực, mã hóa kết nối, timezone, schema mặc định và những tùy chọn khác phụ thuộc driver cùng chính sách của từng hệ thống. Ví dụ SQL Server có thể yêu cầu tham số mã hóa/chứng chỉ; môi trường production cần dùng cấu hình xác thực chứng chỉ đúng chuẩn.

### 5.3. Lựa chọn và tải JAR

Để chọn driver:

1. Xác định đúng hệ quản trị và phiên bản database.
2. Đối chiếu phiên bản Java đang sử dụng.
3. Chọn bản JDBC driver hỗ trợ cả Java và database đó.
4. Tải từ nhà phát hành driver hoặc kho hiện vật đáng tin cậy, kiểm tra metadata, checksum nếu có.
5. Ghi nhận phiên bản driver đã kiểm thử và dùng nhất quán giữa các môi trường.

Ví dụ nguồn tài liệu chính thức cho PostgreSQL JDBC: https://jdbc.postgresql.org/.

Một số bản phân phối CLI có kèm sẵn driver cho các database thông dụng, nhưng thành phần được đóng gói có thể khác nhau. Vì vậy, hãy kiểm tra thực tế trước khi tải thêm JAR: thêm nhiều phiên bản của cùng một JDBC driver vào classpath có thể gây xung đột khó chẩn đoán.

### 5.4. Classpath có vai trò gì?

**Classpath** cho Java biết nơi tìm lớp và thư viện khi chạy. Trong trường hợp CLI, classpath phải cho phép Liquibase nạp được JDBC driver. Chỉ tải JAR xuống ổ đĩa chưa đủ; driver phải được CLI tìm thấy khi khởi động và kết nối.

Tùy gói cài Liquibase, có thể đặt driver trong thư mục thư viện mà CLI nạp hoặc khai báo rõ bằng tham số **--classpath**. Cách khai báo tường minh thường dễ kiểm soát trong ví dụ và pipeline.

Ví dụ cấu trúc của một workspace học tập:

~~~text
liquibase-lab/
├── liquibase.properties
├── drivers/
│   └── postgresql.jar
└── db/
    └── changelog/
        └── db.changelog.yaml
~~~

Tên **postgresql.jar** là tên quy ước trong ví dụ: cần dùng tệp JAR thật của PostgreSQL JDBC, có thể giữ tên phiên bản gốc hoặc đổi tên nhưng không được tạo một file rỗng. Khi đổi phiên bản, cập nhật đúng đường dẫn tương ứng.

Từ thư mục liquibase-lab, lệnh CLI có thể tham chiếu driver:

~~~powershell
liquibase --classpath=drivers/postgresql.jar --version
~~~

Lệnh trên giúp minh họa cách truyền classpath, nhưng **chỉ kiểm tra phiên bản CLI chưa chứng minh driver có thể kết nối**. Cần có bước kết nối đến database để kiểm tra driver thực sự.

Nếu chạy lệnh từ thư mục khác, đường dẫn tương đối tới JAR và changelog có thể bị phân giải khác. Vì vậy, hãy xác định thư mục làm việc trong tài liệu, dùng đường dẫn tuyệt đối khi cần, hoặc đưa toàn bộ thư mục làm việc vào cấu hình pipeline một cách ổn định.

### 5.5. Phân biệt JDBC driver của CLI với driver trong ứng dụng

Trong một ứng dụng Spring Boot, JDBC driver có thể được quản lý bằng Maven hoặc Gradle như một dependency. Khi chạy độc lập, Liquibase CLI là tiến trình riêng và không mặc nhiên dùng các dependency đó.

Đây là nguyên nhân thường gặp của tình huống “ứng dụng kết nối PostgreSQL được nhưng chạy Liquibase CLI lại báo không tìm thấy org.postgresql.Driver”. Cách xử lý là cấu hình JDBC JAR cho đúng tiến trình đang thực thi Liquibase.

## 6. Thiết lập kết nối mẫu với PostgreSQL

### 6.1. Các giả định cần có

Ví dụ tiếp theo giả định:

- PostgreSQL đã chạy và có thể truy cập từ máy thực thi CLI.
- Database học tập **liquibase_demo** đã tồn tại.
- Tài khoản **liquibase_migrator** đã được tạo và có quyền cần thiết để quản lý schema của môi trường học tập.
- JDBC driver PostgreSQL tương thích đã được đặt tại drivers/postgresql.jar.
- Liquibase CLI và Java đã vượt qua bước kiểm tra phiên bản.

Tên database, username, host và port đều phải thay theo môi trường thực tế. Liquibase không tự tạo máy chủ PostgreSQL hoặc database chỉ nhờ điền JDBC URL.

### 6.2. Tệp liquibase.properties

Tạo tệp cấu hình Liquibase tại thư mục làm việc mong muốn:

~~~properties
changeLogFile=db/changelog/db.changelog.yaml
url=jdbc:postgresql://localhost:5432/liquibase_demo
username=liquibase_migrator
driver=org.postgresql.Driver
~~~

Ý nghĩa từng thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| changeLogFile | Đường dẫn tệp changelog gốc để Liquibase đọc |
| url | JDBC URL đến database đích |
| username | Tài khoản đăng nhập database |
| driver | Tên lớp JDBC driver, có thể khai báo rõ khi cần |

Trong môi trường thật, tránh đặt password trực tiếp vào file được commit. Liquibase hỗ trợ cấu hình từ nhiều nguồn, bao gồm tham số và biến môi trường. Có thể cấp bí mật qua **LIQUIBASE_COMMAND_PASSWORD** hoặc cách quản lý secret phù hợp với phiên bản CLI và nền tảng đang dùng.

Ví dụ môi trường PowerShell có thể đọc tên biến:

~~~powershell
# Biến do cơ chế cấp secret của môi trường cung cấp.
# Chỉ kiểm tra đã có giá trị hay chưa, không in mật khẩu thật.
[bool]($env:LIQUIBASE_COMMAND_PASSWORD)
~~~

Lệnh này chỉ trả về True hoặc False để cho biết biến đã có giá trị hay chưa; không in nội dung bí mật. Khi thực hành, chỉ cần bảo đảm bí mật đã được cấp cho tiến trình Liquibase; không cần in nó ra để chứng minh có giá trị.

Không lưu thông tin mật khẩu trong mã nguồn, file Markdown hoặc command history. Với pipeline, dùng hệ thống secret của CI/CD và giới hạn người có quyền đọc biến bí mật.

### 6.3. Changelog tối thiểu cho bước kiểm tra

Để lệnh validate có đầu vào, có thể tạo changelog YAML tối thiểu:

~~~yaml
databaseChangeLog: []
~~~

Changelog trên không có changeset nên chưa yêu cầu thêm bảng hoặc cột nào. Nó chỉ nhằm xác minh CLI có thể đọc và phân tích một tệp changelog cơ bản. Các bài thực hành migration tiếp theo sẽ thêm changeset có định danh và nội dung thay đổi thật.

Nếu dự án đã có changelog chính, hãy dùng đúng changelog đó và kiểm tra yêu cầu tương thích của dự án, không thay thế hoặc xóa nội dung hiện có chỉ để chạy ví dụ.

### 6.4. Chạy kiểm tra

Mở terminal tại thư mục liquibase-lab; bảo đảm thông tin xác thực đã được cấp theo cách an toàn. Có thể sử dụng:

~~~powershell
liquibase --defaults-file=liquibase.properties --classpath=drivers/postgresql.jar validate
~~~

**validate** kiểm tra tính hợp lệ của cấu hình/changelog theo phạm vi Liquibase hỗ trợ. Tùy phiên bản và cấu hình, lệnh có thể cần kết nối database; thành công của validate không đủ để khẳng định migration sẽ chạy an toàn trên dữ liệu production.

Sau khi cấu hình đã đủ, dùng lệnh sau để xem danh sách changeset chờ thực thi:

~~~powershell
liquibase --defaults-file=liquibase.properties --classpath=drivers/postgresql.jar status --verbose
~~~

**status** là bước hợp lý để kiểm tra đường kết nối, vì Liquibase phải làm việc với thông tin lịch sử triển khai ở database. Trên database mới, quá trình khởi tạo hoặc kiểm tra bảng theo dõi có thể xảy ra tùy lệnh và phiên bản; vì thế nên thử trên database học tập và dùng tài khoản có quyền phù hợp.

Với changelog rỗng, kết quả kỳ vọng là không có changeset cần chạy. Nếu báo lỗi, đọc thông báo để phân loại: lỗi khởi động Java, lỗi CLI, thiếu JDBC class, không kết nối được máy chủ, xác thực bị từ chối hoặc không đủ quyền.

Không cần gọi **update** để xác minh việc cài công cụ nếu mục tiêu chỉ là kiểm tra chuẩn bị môi trường. Khi bắt đầu migration thật, cần review changeset và SQL dự kiến trước khi cập nhật schema.

## 7. Quyền truy cập database và bảo mật kết nối

JDBC driver tải được và URL đúng chưa đủ. Tài khoản chạy Liquibase cần có quyền để đọc metadata và thực hiện những thay đổi mà changelog yêu cầu. Tùy hệ quản trị và cách tổ chức schema, các quyền thường liên quan đến tạo/sửa/xóa bảng, chỉ mục, ràng buộc, thay đổi dữ liệu và quản lý các bảng lịch sử của Liquibase.

Nên tách hai loại tài khoản nếu kiến trúc cho phép:

- **Tài khoản migration**: được cấp quyền DDL/DML cần thiết trong schema cụ thể, sử dụng trong bước phát hành có kiểm soát.
- **Tài khoản ứng dụng**: có quyền runtime hạn chế hơn, thường chủ yếu đọc/ghi dữ liệu nghiệp vụ, không cần quyền tự ý đổi schema.

Việc cấp quyền cụ thể phụ thuộc PostgreSQL, MySQL, SQL Server hoặc hệ quản trị khác. Không nên cấp quyền quản trị toàn máy chủ chỉ để tránh lỗi permission trong buổi cài đặt.

Với database ngoài máy cục bộ, ngoài URL đúng còn cần kiểm tra DNS, mạng, firewall, cổng, allowlist và TLS. Cấu hình môi trường thật nên ưu tiên kết nối mã hóa và kiểm tra chứng chỉ thay vì tắt xác minh chứng chỉ để vượt qua lỗi ban đầu.

## 8. Tách bạch cấu hình từng môi trường

Development, staging và production có thể dùng cùng changelog nhưng khác JDBC URL, tài khoản, cơ chế cấp bí mật và quyền. Không viết cứng tài khoản production trong tệp học tập. Mỗi môi trường nên cấp biến cấu hình tại thời điểm chạy, bảo đảm pipeline không vô tình trỏ vào database khác.

Ví dụ bảng phân chia trách nhiệm:

| Thành phần | Thường cố định theo dự án | Thay đổi theo môi trường |
|---|---|---|
| Changelog | Có | Không nên tự phân nhánh vô cớ |
| Phiên bản Liquibase CLI | Có, theo bộ phiên bản đã kiểm thử | Chỉ khác khi có chủ đích |
| JDBC driver | Có, theo loại database và phiên bản tương thích | Có thể khác nếu database thật sự khác |
| JDBC URL | Không | Có |
| Username/password | Không | Có |
| Quyền kết nối và mạng | Không | Có |
| Schema mặc định hoặc search path | Theo quy ước dự án | Có thể khác và phải kiểm tra |

Khi chạy trong Spring Boot hoặc CI/CD, đường dẫn tệp và classpath có thể khác với terminal cá nhân. Chỉ có thể coi môi trường đã được chuẩn bị khi **chính tiến trình sẽ chạy migration** đọc được driver, changelog và secret tương ứng.

## 9. Các lỗi thường gặp khi chuẩn bị

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| java không được nhận diện | Java chưa cài hoặc PATH chưa đúng | Cài JDK phù hợp, kiểm tra JAVA_HOME, PATH và mở terminal mới |
| UnsupportedClassVersionError | Runtime Java quá cũ so với thư viện | Đối chiếu yêu cầu Java của CLI/JAR, kiểm tra runtime thực tế |
| liquibase không được nhận diện | Chưa cài CLI hoặc thư mục lệnh chưa có trong PATH | Gọi trực tiếp executable, kiểm tra PATH và lệnh --version |
| ClassNotFoundException: org.postgresql.Driver | Driver class không nằm trong classpath | Kiểm tra file JAR, đường dẫn --classpath và tên lớp |
| No suitable driver | Driver không phù hợp với JDBC URL hoặc chưa được nạp | Kiểm tra tiền tố JDBC URL, loại và phiên bản driver |
| Connection refused | Máy chủ không lắng nghe ở host/port hoặc bị từ chối kết nối | Kiểm tra DB đang chạy, cổng, cấu hình listen và firewall |
| Connection timeout | Không tới được server qua mạng hoặc kết nối bị chặn | Kiểm tra DNS, route, VPN, security group và firewall |
| Authentication failed | Sai username/password hoặc chính sách xác thực | Kiểm tra secret được cấp, database đích và quyền đăng nhập |
| Permission denied | Tài khoản thiếu quyền trên schema/đối tượng | Xem quyền của tài khoản migration, phân biệt quyền login và quyền DDL |
| Database/schema not found | Sai tên database, schema hoặc cấu hình JDBC | Kiểm tra URL, schema mặc định và đối tượng tồn tại |
| Changelog not found | Sai đường dẫn hoặc working directory | Kiểm tra changeLogFile và thư mục đang chạy CLI |
| Checksum validation failed | Changeset đã áp dụng bị sửa so với lịch sử | Đối chiếu changelog và lịch sử; không tự xóa checksum để bỏ qua lỗi |
| SSL/TLS handshake error | Cấu hình mã hóa hoặc chứng chỉ chưa tương thích | Kiểm tra cấu hình TLS của driver và chứng chỉ tin cậy |

Khi gặp lỗi, đọc **lỗi đầu tiên có ý nghĩa** trong log. Một thông báo “Liquibase failed” chung chung thường không đủ để kết luận vấn đề nằm ở công cụ. Chẳng hạn, “driver class not found” xảy ra trước giai đoạn xác thực, trong khi “password authentication failed” cho thấy tiến trình đã đi đủ xa để thử đăng nhập vào database.

### 9.1. Kiểm tra host và port riêng trên Windows

Với PostgreSQL chạy cục bộ ở port 5432:

~~~powershell
Test-NetConnection -ComputerName localhost -Port 5432
~~~

Bước này chỉ kiểm tra kết nối TCP tới cổng; kết quả thành công **không** chứng minh database, người dùng hoặc mật khẩu đúng. Cần kiểm tra thêm bằng JDBC/Liquibase.

### 9.2. Rủi ro khi có nhiều bản Java hoặc JDBC driver

Máy lập trình viên đôi khi có nhiều JDK. Lệnh java -version trong một shell có thể khác runtime được IDE hoặc CI sử dụng. Tương tự, nhiều JAR của cùng một driver có thể làm lớp không mong muốn được nạp trước. Giảm rủi ro bằng cách cố định phiên bản, đơn giản hóa classpath và ghi lại thông tin đã kiểm thử.

## 10. Checklist xác minh cài đặt

Trước khi chuyển sang bài thực hành migration, hãy tự kiểm tra:

1. Tôi biết phiên bản Liquibase CLI đang sử dụng và yêu cầu Java của bản đó.
2. Lệnh java -version trả về runtime dự định dùng; nếu làm dự án Java, JDK được cấu hình phù hợp.
3. Lệnh liquibase --version chạy được từ môi trường sẽ thực thi migration.
4. Tôi biết loại database, phiên bản, host, port, tên database và schema đích.
5. JDBC driver đúng loại và tương thích Java/database có sẵn trong classpath của CLI.
6. Tôi có tài khoản migration được cấp đúng quyền cần thiết.
7. JDBC URL trỏ vào đúng môi trường; mật khẩu được cấp qua cơ chế secret an toàn.
8. Changelog gốc tồn tại ở đường dẫn mà Liquibase sẽ đọc.
9. Lệnh validate hoàn tất theo kỳ vọng; bước status hoặc kiểm tra kết nối phù hợp không báo lỗi driver, mạng hay xác thực.
10. Tôi có thể tái lập cấu hình này trên máy khác hoặc CI mà không phải chia sẻ mật khẩu trong repository.

Đạt checklist này nghĩa là các điều kiện kỹ thuật cơ bản để chạy Liquibase đã sẵn sàng. Nó **không** bảo đảm mọi changeset đều đúng hoặc rollback an toàn; các nội dung đó cần được thiết kế và kiểm chứng trong những bài migration tiếp theo.

## 11. Tình huống thực hành tự kiểm tra

Giả sử một nhóm muốn dùng Liquibase CLI để triển khai thay đổi cho PostgreSQL trong môi trường dev. Bạn đã cài JDK và CLI, nhưng lệnh status báo thiếu lớp org.postgresql.Driver.

Hãy phân tích theo thứ tự:

1. Java có chạy được không? Nếu CLI đã khởi động và báo thiếu driver, vấn đề có thể không nằm ở việc cài Java.
2. JDBC URL có tiền tố jdbc:postgresql: đúng không?
3. Tệp JAR có phải PostgreSQL JDBC driver thật và tương thích với Java đang dùng không?
4. Đường dẫn --classpath có đúng so với thư mục làm việc của tiến trình CLI không?
5. Có nhiều bản JDBC driver cùng tồn tại gây xung đột không?
6. Sau khi nạp được driver, liệu kết nối đã qua xác thực và quyền schema hay chưa?

**Kết quả mong đợi:** người học xác định được lỗi xuất hiện ở bước nạp JDBC driver và sửa đúng classpath/driver. Nếu lỗi tiếp theo chuyển thành “connection refused” hoặc “authentication failed”, đó là bằng chứng tiến trình đã tiến sang giai đoạn kết nối, cần tiếp tục chẩn đoán máy chủ hoặc thông tin xác thực. Không nên thay đổi changelog, xóa DATABASECHANGELOG hoặc cấp quyền quản trị toàn database chỉ để giải quyết lỗi tìm driver.

## 12. Ghi nhớ

Chuẩn bị môi trường Liquibase là bảo đảm một chuỗi phụ thuộc hoạt động đúng: **Java chạy được → Liquibase CLI khởi động được → JDBC driver được nạp → kết nối tới đúng database bằng tài khoản có quyền phù hợp → changelog được đọc và kiểm tra**.

Một cấu hình tốt còn phải tái lập được giữa máy cá nhân, Spring Boot và CI/CD. Hãy cố định phiên bản Java, Liquibase và driver đã kiểm thử; quản lý bí mật ngoài mã nguồn; ghi rõ đường dẫn và môi trường thực thi; chỉ bắt đầu cập nhật schema khi các bước kiểm tra trước đó đã thành công.

