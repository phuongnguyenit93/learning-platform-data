# Cài đặt CLI và kiểm tra phiên bản đang sử dụng

## 1. Mục tiêu và vị trí của Liquibase CLI

Liquibase CLI (Command Line Interface) là công cụ dòng lệnh để làm việc trực tiếp với changelog và cơ sở dữ liệu. Qua CLI, người phát triển hoặc pipeline có thể kiểm tra cấu hình, xem trạng thái migration, xác thực changelog, sinh SQL dự kiến, áp dụng changeset và thực hiện một số thao tác quản trị lịch sử triển khai.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, người học cần nắm cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Việc cài CLI và xác định đúng phiên bản là bước chuẩn bị để các thao tác đó có thể được lặp lại và kiểm soát.

Một bộ công cụ hoạt động đúng cần có nhiều thành phần phối hợp:

- **Liquibase CLI**: chương trình nhận lệnh và điều phối migration.
- **Java Runtime**: môi trường chạy Liquibase CLI trong các bản phân phối yêu cầu Java. Phiên bản Java tương thích phụ thuộc phiên bản Liquibase.
- **JDBC driver**: thư viện để Liquibase kết nối tới DBMS như PostgreSQL, MySQL, Oracle hoặc SQL Server.
- **Cấu hình kết nối và changelog**: xác định cơ sở dữ liệu đích, tài khoản migration và tệp changelog cần xử lý.
- **Quyền truy cập**: tài khoản cần đủ quyền cho thay đổi dự kiến và được quản lý an toàn.

Lệnh kiểm tra phiên bản CLI chỉ xác nhận chương trình Liquibase đang được gọi. Nó chưa chứng minh Java, JDBC driver, thông tin kết nối, quyền cơ sở dữ liệu hay changelog đều hoạt động chính xác. Cần kiểm tra từng lớp theo thứ tự.

## 2. Chọn cách cài đặt phù hợp

Có một số cách phổ biến để sử dụng Liquibase:

| Cách sử dụng | Khi phù hợp | Điểm cần kiểm soát |
|---|---|---|
| Cài Liquibase CLI từ gói phân phối chính thức | Phát triển trên máy cá nhân, máy build hoặc máy quản trị | Chọn đúng phiên bản, giải nén vào thư mục ổn định và cấu hình PATH |
| Cài qua package manager của hệ điều hành | Đội ngũ đã có quy trình quản lý phần mềm tập trung | Kiểm tra nguồn gói, phiên bản thực tế và cách pin/khóa phiên bản |
| Chạy Liquibase bằng Docker | Muốn môi trường chạy nhất quán giữa máy lập trình và CI | Pin image tag, mount changelog và driver, truyền secret an toàn |
| Dùng Liquibase thông qua Maven, Gradle hoặc Spring Boot | Dự án Java muốn gắn migration với quy trình build hoặc khởi động ứng dụng | Phân biệt phiên bản plugin, thư viện Liquibase và CLI độc lập |

Với người mới làm quen CLI, cách dễ quan sát nhất là tải gói Liquibase phù hợp từ trang phân phối chính thức, giải nén và chạy trực tiếp. Package manager và Docker cũng phù hợp, nhưng cần hiểu chúng đang cung cấp phiên bản nào và binary nào thực sự được gọi.

Không nên tải chương trình từ nguồn không rõ ràng. Hãy đối chiếu phiên bản, checksum hoặc chữ ký số nếu nhà cung cấp phát hành thông tin xác minh cho gói tải xuống. Trong môi trường doanh nghiệp, nên dùng nguồn phần mềm đã được tổ chức phê duyệt.

## 3. Kiểm tra điều kiện trước khi cài

### 3.1. Xác định hệ điều hành và kiến trúc

Chọn đúng gói cài đặt cho Windows, macOS hoặc Linux và kiến trúc máy đang dùng. Không giải nén gói dành cho một hệ điều hành vào môi trường khác rồi kỳ vọng các script khởi chạy tương thích.

Trên Windows, có thể xem phiên bản hệ điều hành bằng lệnh:

~~~powershell
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsArchitecture
~~~

Trên macOS hoặc Linux:

~~~bash
uname -s
uname -m
~~~

Thông tin này hữu ích khi chọn đúng gói phân phối và kiểm tra lỗi liên quan đến kiến trúc.

### 3.2. Kiểm tra Java

Các bản Liquibase CLI sử dụng Java cần có Java Runtime tương thích. Kiểm tra Java hiện được shell nhận diện:

~~~bash
java -version
~~~

Trên Windows PowerShell cũng dùng được:

~~~powershell
java -version
~~~

Nếu nhận được thông báo không tìm thấy lệnh java, máy có thể chưa cài Java hoặc thư mục chứa java chưa nằm trong PATH. Nếu Java đã được cài, kiểm tra biến JAVA_HOME và PATH để bảo đảm terminal đang sử dụng đúng bản Java.

Yêu cầu phiên bản Java thay đổi theo phiên bản Liquibase và loại gói phân phối. Hãy đối chiếu ma trận tương thích trong tài liệu của đúng bản Liquibase dự định cài; không suy ra rằng mọi bản Liquibase đều chạy với cùng một phiên bản Java. Khi máy có nhiều JDK, nên chọn rõ bản dùng cho CLI và xác minh lại trong một terminal mới.

### 3.3. Chuẩn bị JDBC driver và thông tin DBMS

Liquibase cần JDBC driver phù hợp để giao tiếp với cơ sở dữ liệu. Một số gói hoặc cách tích hợp có thể đã cung cấp driver cần thiết; trong trường hợp chưa có, phải tải driver đúng DBMS và phiên bản tương thích, rồi khai báo trong classpath theo hướng dẫn của bản cài đặt.

Ví dụ tên driver thường gặp:

| DBMS | JDBC driver thường dùng |
|---|---|
| PostgreSQL | PostgreSQL JDBC Driver |
| MySQL | MySQL Connector/J |
| Oracle Database | Oracle JDBC Driver |
| Microsoft SQL Server | Microsoft JDBC Driver for SQL Server |

Không nên nhầm JDBC driver với Liquibase extension. Driver cung cấp khả năng kết nối JDBC tới DBMS; extension bổ sung hoặc mở rộng hành vi của Liquibase. Cả hai đều phải tương thích với phiên bản và môi trường đang dùng.

Chuẩn bị trước URL kết nối, tên schema nếu cần, tài khoản migration và quyền được cấp. Tài khoản chạy migration thường cần quyền DDL và có thể cần quyền đọc/ghi dữ liệu. Không dùng tài khoản ứng dụng runtime hoặc tài khoản quản trị toàn quyền một cách mặc định nếu có thể cấp quyền riêng phù hợp hơn.

## 4. Cài đặt Liquibase CLI từ gói phân phối

### 4.1. Tải và giải nén

1. Mở trang tải Liquibase chính thức và chọn phiên bản, hệ điều hành, kiến trúc cùng edition phù hợp với dự án.
2. Đọc ghi chú phát hành để biết thay đổi đáng chú ý, yêu cầu Java, thay đổi cấu hình và vấn đề tương thích.
3. Tải gói phân phối và kiểm tra checksum hoặc chữ ký nếu có.
4. Giải nén vào thư mục ổn định, dễ quản lý quyền truy cập và nâng cấp.
5. Xác định thư mục chứa script thực thi Liquibase. Gói Windows thường có script .bat; gói Unix-like thường có script thực thi tên liquibase.

Ví dụ bố trí thư mục trên Windows:

~~~text
C:\tools\
  liquibase\
    liquibase.bat
    lib\
    ...
~~~

Ví dụ bố trí trên Linux:

~~~text
/opt/liquibase/
  liquibase
  lib/
  ...
~~~

Đây chỉ là ví dụ vị trí cài đặt. Cấu trúc thực tế phụ thuộc gói được tải. Không di chuyển riêng script khỏi các thư mục thư viện đi kèm nếu cách đóng gói yêu cầu chúng nằm cạnh nhau.

### 4.2. Cấu hình PATH

PATH cho phép gọi Liquibase từ bất kỳ thư mục làm việc nào. Hãy thêm thư mục chứa script thực thi vào PATH, không thêm đường dẫn tới chính file script.

Trên Windows, có thể mở Environment Variables trong System Properties và thêm thư mục cài đặt vào PATH của người dùng hoặc hệ thống theo chính sách máy. Sau khi cập nhật, đóng terminal cũ và mở terminal mới để nạp biến môi trường.

Kiểm tra vị trí chương trình:

~~~powershell
Get-Command liquibase -All
where.exe liquibase
~~~

Trên macOS hoặc Linux:

~~~bash
command -v liquibase
type -a liquibase
~~~

Nếu không muốn thay đổi PATH toàn hệ thống, có thể gọi script bằng đường dẫn đầy đủ. Trên Windows, ví dụ:

~~~powershell
& 'C:\tools\liquibase\liquibase.bat' --version
~~~

Trên Linux:

~~~bash
/opt/liquibase/liquibase --version
~~~

Nếu hệ điều hành báo không có quyền thực thi script Unix-like, kiểm tra quyền file và chỉ cấp quyền thực thi cần thiết theo chính sách máy. Ví dụ:

~~~bash
chmod u+x /opt/liquibase/liquibase
~~~

Không cần chạy lệnh cấp quyền nếu script đã có quyền thực thi.

### 4.3. Cài bằng package manager

Nếu tổ chức quản lý phần mềm qua package manager, hãy làm theo nguồn gói và quy trình đã được phê duyệt. Sau khi cài, vẫn phải chạy liquibase --version và kiểm tra đường dẫn binary được phân giải.

Package manager có thể cập nhật gói theo chính sách hệ thống hoặc cài bản mới khi chạy lệnh nâng cấp. Vì vậy, với môi trường build và production, cần pin phiên bản cụ thể hoặc dùng cơ chế khóa phiên bản của package manager. Không nên giả định rằng lệnh cài mặc định sẽ luôn cài cùng một phiên bản ở mọi thời điểm.

### 4.4. Chạy Liquibase bằng Docker

Docker là lựa chọn hữu ích khi đội ngũ muốn dùng một runtime được đóng gói sẵn mà không cài CLI trực tiếp lên máy. Chọn image chính thức phù hợp và pin tag phiên bản thay vì dùng tag thay đổi theo thời gian.

Ví dụ kiểm tra phiên bản của image:

~~~bash
docker run --rm liquibase/liquibase:<version> --version
~~~

Khi chạy migration thật, cần mount thư mục chứa changelog vào container, cung cấp JDBC driver bổ sung nếu image không có driver cần thiết, và truyền cấu hình kết nối từ secret store hoặc biến môi trường an toàn. Đường dẫn changelog trong container phải khớp với đường dẫn được truyền cho Liquibase.

Không ghi mật khẩu trực tiếp vào Dockerfile, image, file compose được commit hoặc câu lệnh có thể lưu trong shell history. Cũng cần pin image tag và xác minh image được kéo về đúng phiên bản mong muốn.

## 5. Kiểm tra phiên bản Liquibase đang được sử dụng

### 5.1. Lệnh kiểm tra cơ bản

Sau khi cài đặt và cấu hình PATH, mở terminal mới rồi chạy:

~~~bash
liquibase --version
~~~

Lệnh này in ra phiên bản của Liquibase CLI mà shell đang gọi. Nếu có nhiều bản cài trên máy, kết quả chỉ phản ánh binary được tìm thấy đầu tiên theo thứ tự PATH.

Tiếp theo, xem trợ giúp:

~~~bash
liquibase --help
~~~

Trợ giúp cho biết các lệnh và tham số mà bản cài đang hỗ trợ. Khi cần kiểm tra cú pháp một lệnh cụ thể, dùng trợ giúp tương ứng của phiên bản đang cài và đối chiếu tài liệu đúng phiên bản. Không sao chép cú pháp từ hướng dẫn của một bản khác mà không kiểm tra.

### 5.2. Xác định binary thực sự được gọi

Một máy có thể tồn tại nhiều bản Liquibase: bản cài thủ công, bản từ package manager, bản trong thư mục dự án hoặc bản được gọi từ môi trường CI. Nếu phiên bản in ra không như mong đợi, kiểm tra tất cả đường dẫn có thể được phân giải.

Trên Windows PowerShell:

~~~powershell
Get-Command liquibase -All
where.exe liquibase
~~~

Trên macOS hoặc Linux:

~~~bash
type -a liquibase
command -v liquibase
~~~

So sánh đường dẫn được trả về với thư mục cài đặt dự kiến. Nếu nhiều bản cùng tồn tại, điều chỉnh PATH hoặc gọi binary bằng đường dẫn đầy đủ. Sau khi thay đổi PATH, mở terminal mới và chạy lại lệnh kiểm tra.

### 5.3. Kiểm tra Java mà CLI sử dụng

Chạy:

~~~bash
java -version
~~~

Đối chiếu phiên bản Java đang được shell nhận diện với yêu cầu của bản Liquibase đã chọn. Nếu java -version trong terminal cho kết quả khác với Java mà một IDE, service hoặc pipeline sử dụng, hãy kiểm tra môi trường của tiến trình đó riêng biệt. PATH và JAVA_HOME trong terminal tương tác không nhất thiết giống môi trường chạy của service.

### 5.4. Phân biệt phiên bản CLI với phiên bản thư viện trong ứng dụng

Trong dự án Spring Boot, Liquibase có thể được nạp dưới dạng thư viện liquibase-core trong dependency graph. Dự án Maven hoặc Gradle cũng có thể dùng plugin Liquibase với phiên bản riêng. Những thành phần này không nhất thiết có cùng phiên bản với CLI cài trên máy.

Ví dụ:

| Thành phần | Cách xác định |
|---|---|
| Liquibase CLI độc lập | Chạy liquibase --version trong terminal |
| Thư viện Liquibase của ứng dụng | Kiểm tra dependency được resolve trong Maven hoặc Gradle |
| Liquibase Maven/Gradle plugin | Kiểm tra phiên bản plugin trong cấu hình build |
| Liquibase trong Docker | Kiểm tra tag image và chạy --version bên trong image |
| Liquibase trong CI/CD | Kiểm tra image, tool cache hoặc binary mà job thực sự gọi |

Vì vậy, kết quả liquibase --version trên máy lập trình viên không tự chứng minh ứng dụng Spring Boot hoặc pipeline đang sử dụng cùng phiên bản. Cần kiểm tra đúng thành phần thực thi migration trong từng môi trường.

## 6. Kiểm tra cấu hình và khả năng kết nối

Sau khi xác nhận CLI khởi động được, kiểm tra các yếu tố cần thiết để chạy migration.

### 6.1. Cấu hình changelog và kết nối

Liquibase có thể nhận tham số từ dòng lệnh, file cấu hình hoặc biến môi trường. Một file liquibase.properties có thể chứa các thiết lập không nhạy cảm như đường dẫn changelog và driver:

~~~properties
changeLogFile=db/changelog/db.changelog-master.yaml
driver=org.postgresql.Driver
~~~

URL và tài khoản có thể được cung cấp riêng theo môi trường. Nếu dùng file cấu hình, hãy chỉ rõ file mặc định hoặc file được chọn theo cách mà phiên bản CLI hỗ trợ, ví dụ qua tham số --defaults-file. Kiểm tra cách phân giải đường dẫn tương đối: cùng một giá trị có thể trỏ tới file khác nhau nếu working directory thay đổi.

Không commit mật khẩu hoặc secret vào repository. Trong CI/CD, dùng secret store và cơ chế truyền biến môi trường được nền tảng hỗ trợ. Hạn chế in các biến nhạy cảm ra log và tránh đưa mật khẩu trực tiếp vào lịch sử lệnh.

### 6.2. Kiểm tra JDBC driver

Nếu Liquibase không tìm thấy driver, kiểm tra:

1. Đã chọn đúng JDBC driver cho DBMS chưa?
2. File JAR có tồn tại và có thể đọc được không?
3. Driver đã nằm trong classpath mà Liquibase sử dụng chưa?
4. Phiên bản driver có tương thích với Java và DBMS không?
5. Tên driver hoặc JDBC URL có chính xác không?

Không nhầm việc liquibase --version chạy thành công với việc driver đã được nạp. Lệnh xem phiên bản thường không cần kết nối cơ sở dữ liệu.

### 6.3. Kiểm tra kết nối có kiểm soát

Khi cấu hình đã sẵn sàng, có thể dùng lệnh status để xem những changeset nào còn cần chạy. Ví dụ dạng lệnh:

~~~bash
liquibase \
  --url="jdbc:postgresql://localhost:5432/appdb" \
  --username="migration_user" \
  --changelog-file="db/changelog/db.changelog-master.yaml" \
  status
~~~

Ví dụ trên minh họa cấu trúc tham số. Hãy thay URL, tên người dùng và đường dẫn bằng giá trị của môi trường thử nghiệm. Mật khẩu nên được lấy từ secret store hoặc biến môi trường an toàn, không gõ trực tiếp vào lệnh mẫu hay commit vào file cấu hình.

Lệnh status có thể cần kết nối tới cơ sở dữ liệu và đọc lịch sử migration. Nó giúp kiểm tra thêm URL, driver, quyền truy cập và changelog. Tuy nhiên, kết quả status không chứng minh migration sẽ chạy thành công; các câu lệnh DDL/DML vẫn cần được kiểm thử trên DBMS và dữ liệu phù hợp.

## 7. Quản lý phiên bản nhất quán giữa các môi trường

Phiên bản Liquibase ảnh hưởng tới cách đọc changelog, cách sinh SQL, hành vi của một số lệnh và khả năng tương thích với Java, DBMS, driver hoặc extension. Nếu máy lập trình, CI và production chạy các phiên bản khác nhau, cùng một changelog có thể được xử lý khác nhau hoặc xuất hiện lỗi chỉ ở một môi trường.

Một quy trình quản lý phiên bản nên có các nguyên tắc sau:

- Chọn một phiên bản Liquibase được dự án hỗ trợ và ghi rõ trong tài liệu cài đặt hoặc cấu hình build.
- Pin phiên bản CLI, plugin hoặc Docker image; tránh phụ thuộc vào nhãn latest trong pipeline.
- Dùng cùng phiên bản đã được kiểm thử khi review SQL và khi triển khai vào môi trường đích.
- Kiểm tra tương thích giữa Liquibase, Java, JDBC driver, DBMS và extension.
- Đọc release notes trước khi nâng cấp, đặc biệt khi thay đổi phiên bản chính hoặc có thay đổi hành vi.
- Thử nâng cấp trên môi trường kiểm thử với changelog hiện có và migration mới trước khi áp dụng ở production.
- Ghi nhận phiên bản Liquibase thực tế trong log hoặc metadata của lần phát hành để hỗ trợ điều tra.

Không nên nâng cấp CLI giữa một lần triển khai đang diễn ra. Nếu cần thay đổi phiên bản, hãy xem đó là thay đổi công cụ phát hành: kiểm thử, phê duyệt, pin lại cấu hình và triển khai theo quy trình có thể lặp lại.

## 8. Lỗi thường gặp khi cài đặt và kiểm tra phiên bản

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| liquibase không được nhận diện | Chưa cài, PATH chưa đúng hoặc terminal chưa nạp PATH mới | Kiểm tra thư mục cài đặt, PATH và mở terminal mới |
| Lệnh gọi ra phiên bản cũ | Có nhiều bản cài và bản cũ đứng trước trong PATH | Dùng Get-Command -All, where.exe hoặc type -a để tìm binary |
| Không tìm thấy java | Java chưa cài hoặc PATH/JAVA_HOME chưa đúng | Cài Java tương thích và xác minh java -version |
| Lỗi phiên bản Java không tương thích | Liquibase yêu cầu runtime khác với Java hiện tại | Đối chiếu ma trận tương thích và chọn Java phù hợp |
| Không tìm thấy JDBC driver | Driver JAR chưa có trong classpath hoặc cấu hình driver sai | Bổ sung driver phù hợp và kiểm tra classpath |
| Kết nối bị từ chối | URL, cổng, host, quyền mạng hoặc trạng thái DBMS không đúng | Kiểm tra dịch vụ DBMS, DNS, firewall, URL và quyền truy cập |
| Đăng nhập thất bại | Tài khoản, mật khẩu, phương thức xác thực hoặc quyền không đúng | Kiểm tra secret và quyền migration qua kênh an toàn |
| Máy local và CI báo phiên bản khác nhau | Cấu hình tool hoặc image trong pipeline không được pin | Khóa phiên bản và kiểm tra binary/image mà job thực sự sử dụng |
| Changelog không tìm thấy | Working directory hoặc đường dẫn changelog sai | Dùng đường dẫn rõ ràng và kiểm tra file trong môi trường thực thi |

Khi xử lý lỗi, hãy đọc toàn bộ thông báo và xác định lớp gây lỗi: shell, Java, Liquibase, JDBC driver, mạng, xác thực hay changelog. Thay đổi nhiều cấu hình cùng lúc khiến việc tìm nguyên nhân khó hơn.

## 9. Quy trình cài đặt và xác minh đề xuất

Có thể dùng trình tự sau cho một máy phát triển mới:

1. Xác định hệ điều hành, kiến trúc và phiên bản Java sẵn có.
2. Chọn bản Liquibase phù hợp với yêu cầu dự án và ma trận tương thích.
3. Tải gói từ nguồn chính thức, kiểm tra tính toàn vẹn nếu có thông tin xác minh.
4. Giải nén vào thư mục ổn định hoặc cài bằng package manager đã được phê duyệt.
5. Cấu hình PATH và mở terminal mới.
6. Chạy liquibase --version để xác nhận CLI khởi động và ghi nhận phiên bản.
7. Chạy liquibase --help để kiểm tra khả năng hiển thị trợ giúp.
8. Xác định binary thực sự được gọi bằng lệnh tra cứu của hệ điều hành.
9. Kiểm tra Java, JDBC driver và cấu hình changelog.
10. Dùng cơ sở dữ liệu thử nghiệm để kiểm tra kết nối và trạng thái migration.
11. Ghi lại phiên bản công cụ cùng cách cài đặt để thành viên khác và pipeline có thể tái tạo.

Danh sách kiểm tra nhanh:

- [ ] Đúng gói Liquibase và đúng nguồn tải.
- [ ] Phiên bản Java tương thích với bản Liquibase đã chọn.
- [ ] PATH trỏ tới đúng thư mục thực thi.
- [ ] liquibase --version trả về phiên bản mong muốn.
- [ ] Đã xác định binary nếu máy có nhiều bản Liquibase.
- [ ] JDBC driver phù hợp có trong classpath khi cần.
- [ ] Changelog và cấu hình được phân giải từ đúng working directory.
- [ ] Kết nối được kiểm tra trên cơ sở dữ liệu thử nghiệm.
- [ ] Phiên bản công cụ được pin và thống nhất trong CI/CD.
- [ ] Không có mật khẩu hoặc secret bị ghi cứng trong repository hay log.

## 10. Kết luận

Cài đặt Liquibase CLI là bước chuẩn bị môi trường để quản lý migration từ terminal hoặc pipeline. Một cài đặt đáng tin cậy cần xác định đúng gói, Java runtime, PATH, JDBC driver, cấu hình kết nối và phiên bản thực thi. liquibase --version là phép kiểm tra đầu tiên, còn việc xác định binary, xem trợ giúp và thử kết nối trên cơ sở dữ liệu kiểm thử giúp xác minh sâu hơn.

Đối với dự án **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, việc pin phiên bản và kiểm tra nhất quán giữa máy phát triển, công cụ build, Docker và CI/CD tạo nền tảng cho changelog, changeset, precondition, checksum và lịch sử triển khai hoạt động có thể dự đoán. Khi nâng cấp công cụ, cần kiểm tra tương thích và thử với changelog hiện có trước khi dùng ở môi trường quan trọng.
