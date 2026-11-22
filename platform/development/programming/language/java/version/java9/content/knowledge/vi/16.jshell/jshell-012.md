# Quản lý nguồn đầu vào tin cậy và đóng JShell khi hoàn tất

JShell cho phép nhập và thực thi Java ngay trong một phiên tương tác. Mỗi snippet có thể gọi API của JDK, thư viện bên ngoài, truy cập file, đọc biến môi trường, mở kết nối mạng hoặc khởi chạy tiến trình con theo quyền của tiến trình JShell. Vì vậy, nguồn mã và thư viện được nạp vào JShell cần được kiểm tra trước khi thực thi. Khi công việc kết thúc, cần đóng tài nguyên đã mở và thoát phiên đúng cách.

Hai mục tiêu của quy trình này là:

- **Tin cậy nguồn đầu vào:** biết mã đến từ đâu, kiểm tra nội dung và dependency, giới hạn quyền của môi trường chạy.
- **Kết thúc phiên có kiểm soát:** đóng tài nguyên, dừng tác vụ nền, thoát JShell và kiểm tra tiến trình đã kết thúc.

## 1. Những nguồn đầu vào cần kiểm tra

Đầu vào của JShell không chỉ là dòng Java được nhập tại dấu nhắc. Cần xem xét toàn bộ những thành phần có thể ảnh hưởng đến việc thực thi:

| Nguồn | Ví dụ | Rủi ro cần đánh giá |
|---|---|---|
| Mã nhập trực tiếp | Biểu thức, method, class được dán vào JShell | Mã có thể đọc, sửa hoặc gửi dữ liệu bằng quyền của người dùng hiện tại |
| Script JShell | Tệp .jsh được nạp bằng /open | Script có thể chứa nhiều snippet và lệnh có tác dụng phụ |
| Thư viện bên ngoài | JAR trong classpath hoặc module path | Mã thư viện cũng được thực thi trong tiến trình; dependency có thể kéo theo dependency khác |
| Mã khởi tạo | Startup script hoặc cấu hình khởi chạy tùy chỉnh | Nội dung có thể được thực thi trước khi người dùng bắt đầu thao tác |
| Dữ liệu và cấu hình | File cấu hình, biến môi trường, system properties | Có thể chứa bí mật, đường dẫn hoặc endpoint nhạy cảm |
| Nội dung tải từ mạng | Script, JAR, ví dụ mã hoặc lệnh từ website | Nguồn có thể bị giả mạo, thay đổi hoặc chứa mã độc |

Không xem một đoạn mã là an toàn chỉ vì nó ngắn, có vẻ dễ hiểu hoặc được chia sẻ trong tài liệu. Một lời gọi method có thể dẫn tới code khác trong thư viện, đọc file, gọi mạng hoặc tạo tiến trình con.

## 2. Hiểu đúng quyền thực thi của JShell

JShell thực thi mã Java trong môi trường của tiến trình và có thể sử dụng các quyền mà tài khoản đang chạy có. Ví dụ, mã có thể:

- Đọc các file mà tài khoản có quyền đọc và ghi vào các file mà tài khoản có quyền ghi.
- Đọc biến môi trường và system properties có sẵn trong tiến trình.
- Kết nối tới hệ thống mạng mà máy có thể truy cập.
- Tạo thread, mở socket, khởi chạy tiến trình con hoặc sử dụng thư viện native.
- Gọi các API của thư viện đã được đưa vào classpath hoặc module path.

Do đó, không chạy script chưa kiểm tra bằng tài khoản quản trị hoặc trên máy có sẵn thông tin đăng nhập production. Không đưa mật khẩu, access token, private key, cookie hay dữ liệu khách hàng vào snippet để thử nghiệm.

**JShell không phải sandbox cho mã Java không đáng tin cậy.** Không dựa vào Security Manager để cách ly mã: cơ chế này đã bị đánh dấu loại bỏ từ JDK 17 và bị vô hiệu hóa hoàn toàn từ JDK 24. Cần kiểm soát quyền ở cấp hệ điều hành và môi trường chạy.

## 3. Xác minh nguồn mã trước khi thực thi

Trước khi nhập mã hoặc nạp một tệp .jsh:

1. Xác định tác giả, repository hoặc nhà phát hành. Ưu tiên nguồn chính thức và kênh phân phối đã được tổ chức phê duyệt.
2. Kiểm tra URL, tên repository, nhánh, tag hoặc commit. Không dựa vào tên file hay tên tài khoản giống với nguồn chính thức.
3. Đọc toàn bộ script, kể cả các đoạn được gọi gián tiếp, import, khai báo class và lệnh JShell.
4. Tìm các hành động có tác dụng phụ như đọc/ghi file, gọi mạng, xử lý credential, chạy ProcessBuilder, Runtime.exec, tạo thread hoặc tải thêm mã.
5. Xác nhận script chỉ thực hiện các thao tác cần thiết cho mục đích thử nghiệm.
6. Nếu không xác minh được nguồn hoặc không hiểu một đoạn mã quan trọng, không nạp đoạn đó vào phiên có quyền truy cập dữ liệu thật.

Không thực thi trực tiếp lệnh terminal được sao chép từ một trang web hoặc cuộc trò chuyện chưa xác minh. Hãy đọc lệnh, hiểu từng tham số và kiểm tra đường dẫn đích trước khi chạy.

### Kiểm tra tính toàn vẹn của tệp

Nếu nhà phát hành cung cấp checksum, hãy so sánh checksum của tệp tải về với giá trị lấy từ một kênh tin cậy độc lập. Ví dụ:

Trên Linux:

~~~bash
sha256sum trusted-demo.jsh
~~~

Trên macOS:

~~~bash
shasum -a 256 trusted-demo.jsh
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash .\trusted-demo.jsh -Algorithm SHA256
~~~

Checksum chỉ xác nhận tệp có khớp với giá trị tham chiếu. Nếu giá trị tham chiếu cũng lấy từ cùng một nguồn không đáng tin, phép so sánh không chứng minh được nguồn phát hành là hợp lệ.

Với artifact có chữ ký số, kiểm tra chữ ký và danh tính signer theo quy trình tin cậy của tổ chức. Chữ ký hợp lệ cho biết nội dung được ký bởi khóa tương ứng; vẫn cần xác minh khóa đó thực sự thuộc nhà phát hành mong đợi.

## 4. Kiểm soát thư viện và dependency

Thư viện được nạp vào JShell có cùng khả năng thực thi mã trong tiến trình. Một JAR không rõ nguồn gốc có thể chứa mã chạy ngay khi class được khởi tạo hoặc khi method của nó được gọi.

Khi sử dụng dependency:

- Chỉ lấy JAR từ repository hoặc registry đã được phê duyệt.
- Cố định phiên bản dependency; tránh phiên bản động hoặc tải artifact không xác định.
- Kiểm tra dependency bắc cầu, bởi một thư viện có thể kéo theo nhiều thư viện khác.
- Dùng checksum, chữ ký hoặc cơ chế xác minh dependency của build tool khi tổ chức hỗ trợ.
- Không đưa cả thư mục chứa JAR tùy ý vào classpath.
- Chỉ cấp classpath và module path chứa những thư viện thực sự cần thiết.

Ví dụ, nếu cần một thư viện đã được phê duyệt:

~~~bash
jshell --class-path lib/approved-client.jar
~~~

Lệnh này chỉ thêm JAR vào classpath; nó không xác minh độ an toàn của JAR. Việc kiểm tra nguồn gốc và tính toàn vẹn phải hoàn tất trước khi khởi chạy.

Đối với dự án Maven hoặc Gradle, nên dùng cấu hình dependency được quản lý trong repository, kiểm tra cây dependency và bật cơ chế khóa hoặc xác minh dependency phù hợp. Không tải dependency ngẫu nhiên từ một URL rồi đưa trực tiếp vào JShell.

## 5. Tạo môi trường chạy có quyền tối thiểu

Khi kiểm thử mã đáng tin nhưng có thể tác động đến file hoặc dịch vụ, hãy dùng tài khoản và thư mục làm việc dành riêng cho thử nghiệm:

- Chạy bằng tài khoản thông thường, không có quyền administrator hoặc root.
- Dùng thư mục thử nghiệm riêng; chỉ cấp quyền đọc/ghi cho những file cần thiết.
- Không mount thư mục chứa SSH key, credential, source code nhạy cảm hoặc dữ liệu production vào môi trường thử nghiệm.
- Dùng dữ liệu giả lập và endpoint thử nghiệm.
- Giới hạn biến môi trường và system properties ở mức cần thiết.
- Đặt timeout và giới hạn tài nguyên cho các tác vụ có thể chạy lâu.
- Ghi lại JDK, phiên bản thư viện và cấu hình môi trường để có thể tái hiện kết quả.

Với mã chưa thể xác minh đầy đủ hoặc có nguồn gốc không chắc chắn, không chạy trong phiên JShell thông thường trên máy làm việc. Nếu việc kiểm tra là cần thiết, hãy dùng VM hoặc container dùng một lần với tài khoản không đặc quyền, filesystem hạn chế, giới hạn CPU/bộ nhớ, network bị tắt hoặc chỉ cho phép endpoint cần thiết và không gắn secret. Container chỉ cung cấp lớp cách ly khi được cấu hình đúng; không xem container mặc định là ranh giới bảo mật tuyệt đối.

## 6. Nạp script có kiểm soát

Trước khi dùng /open, hãy xem nội dung tệp .jsh bằng trình soạn thảo hoặc công cụ đọc văn bản. Xác nhận:

- Tệp đến từ repository hoặc nguồn đã được xác minh.
- Mọi snippet và lệnh JShell đều nằm trong phạm vi công việc.
- Không có lệnh xóa dữ liệu, thay đổi cấu hình, tải mã hoặc gửi dữ liệu ra ngoài ngoài dự kiến.
- Dependency và đường dẫn file được chỉ định rõ.
- Không có credential hoặc dữ liệu nhạy cảm được hard-code.

Khi cần kiểm tra nhanh một script, hãy mở trong môi trường thử nghiệm với dữ liệu giả lập. Không nạp tệp từ thư mục Downloads hoặc thư mục chia sẻ chung chỉ vì tên tệp có vẻ quen thuộc.

Một quy trình đơn giản:

~~~text
$ jshell --version
$ jshell
jshell> /open trusted-demo.jsh
jshell> /list
~~~

Lệnh /list giúp xem các snippet đã được nạp. Nó không phải công cụ kiểm tra bảo mật và không thay thế việc review nội dung script trước khi thực thi. Nếu script có hành động bên ngoài, cần kiểm tra kết quả và tác động trên môi trường thử nghiệm.

## 7. Quản lý bí mật và dữ liệu nhạy cảm

JShell phù hợp để thử nghiệm nhanh, nhưng lịch sử và script có thể lưu lại nội dung đã nhập. Cần coi chúng như file mã nguồn có thể được người khác đọc.

- Không nhập trực tiếp mật khẩu, token, private key, session cookie hoặc chuỗi kết nối có thông tin xác thực.
- Không lưu credential vào file .jsh, tệp lịch sử, command line hoặc repository.
- Không in toàn bộ biến môi trường, system properties hoặc nội dung cấu hình ra màn hình/log.
- Không chia sẻ ảnh chụp màn hình hoặc lịch sử phiên nếu chúng có dữ liệu nhạy cảm.
- Nếu cần xác thực với dịch vụ, dùng cơ chế cấp credential thử nghiệm có thời hạn ngắn và quyền tối thiểu.
- Thu hồi credential thử nghiệm sau khi hoàn tất nếu quy trình cấp phát yêu cầu.

Nếu phát hiện bí mật đã được nhập hoặc lưu vào file lịch sử, xử lý như một lần lộ thông tin: xóa bản sao theo quy trình lưu trữ, thu hồi hoặc xoay vòng credential và kiểm tra nơi tệp đã được đồng bộ.

## 8. Đóng tài nguyên trước khi thoát

Thoát JShell không thay thế việc giải phóng mọi tài nguyên mà snippet đã mở. Hãy đóng rõ ràng những đối tượng có vòng đời riêng:

- Đóng stream, reader, writer và file handle.
- Đóng JDBC connection, statement và result set.
- Đóng HTTP client, socket và các client kết nối dịch vụ khi API yêu cầu.
- Dừng ExecutorService, scheduler và thread do snippet tạo.
- Hủy tác vụ đang chạy và đóng tài nguyên tạm.
- Dừng tiến trình con hoặc dịch vụ thử nghiệm do phiên khởi chạy.
- Xóa file tạm nếu không cần lưu lại.

Với tài nguyên hỗ trợ AutoCloseable, ưu tiên try-with-resources trong đoạn mã thực thi:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

try (var reader = Files.newBufferedReader(Path.of("sample.txt"))) {
    System.out.println(reader.readLine());
}
~~~

Khi khối try kết thúc, reader được đóng tự động kể cả khi có exception. Với tài nguyên sống lâu hơn một snippet, hãy giữ tham chiếu và gọi close hoặc shutdown tương ứng trước khi thoát.

Ví dụ, nếu đã tạo executor:

~~~java
import java.util.concurrent.Executors;

var executor = Executors.newSingleThreadExecutor();
executor.submit(() -> System.out.println("Task completed"));
executor.shutdown();
~~~

shutdown ngăn nhận task mới và cho phép task đã gửi hoàn tất. Nếu cần chờ hoàn tất, dùng awaitTermination với timeout phù hợp; nếu hết thời gian, xử lý tác vụ còn lại theo chính sách của ứng dụng. Không để thread nền hoặc tác vụ chờ vô hạn.

## 9. Thoát JShell đúng cách

Khi đã hoàn tất công việc và đóng tài nguyên, dùng lệnh:

~~~text
jshell> /exit
~~~

/exit kết thúc phiên JShell và trả quyền điều khiển về terminal hoặc shell đã khởi chạy nó. Đây là cách thoát thông thường, giúp người dùng kết thúc REPL một cách rõ ràng.

Nếu cần thoát trong một script thao tác có kiểm soát, hãy hoàn tất việc ghi kết quả và đóng tài nguyên trước khi gọi /exit. Không dùng lệnh thoát để thay cho cleanup.

Sau khi thoát:

1. Xác nhận dấu nhắc terminal của hệ điều hành xuất hiện trở lại.
2. Kiểm tra lệnh hoặc script đã trả mã thoát phù hợp nếu phiên được chạy từ automation.
3. Xác nhận tiến trình con, server thử nghiệm hoặc tác vụ nền do snippet tạo đã dừng.
4. Kiểm tra file tạm và dữ liệu thử nghiệm, giữ lại hoặc xóa theo yêu cầu công việc.
5. Xóa credential tạm và thu hồi quyền truy cập nếu đã cấp.
6. Không để lại cửa sổ terminal, phiên JShell hoặc tiến trình thử nghiệm không còn sử dụng.

Nếu terminal vẫn bị giữ sau khi /exit, hãy xác định thread hoặc tiến trình nào còn hoạt động. Đóng tài nguyên, dừng executor và kết thúc tiến trình con theo cách phù hợp. Không kết thúc cưỡng bức một tiến trình trước khi xác định nó có đang ghi dữ liệu hoặc thực hiện công việc cần hoàn tất hay không.

## 10. Quy trình thực hành từ đầu đến cuối

Một quy trình an toàn, có thể lặp lại:

1. Xác định mục tiêu thử nghiệm, JDK cần dùng và các quyền thực sự cần thiết.
2. Lấy script và dependency từ nguồn đã được phê duyệt.
3. Kiểm tra repository, phiên bản, checksum hoặc chữ ký theo chính sách tổ chức.
4. Đọc script, xác định thao tác file, network, credential, process và tác dụng phụ.
5. Chuẩn bị tài khoản, thư mục, dữ liệu và endpoint thử nghiệm với quyền tối thiểu.
6. Khởi chạy JShell từ đúng JDK; chỉ thêm classpath/module path đã xác minh.
7. Nạp script và chạy các bước cần thiết; quan sát output và log.
8. Đóng stream, kết nối, executor và tiến trình con do phiên tạo ra.
9. Dùng /exit để thoát JShell.
10. Kiểm tra tiến trình, file tạm, dữ liệu thử nghiệm và credential còn tồn tại; dọn dẹp theo chính sách.

Nếu cần lưu script để dùng lại, chỉ lưu mã đã review và không chứa bí mật. Việc lưu một tệp .jsh không làm cho nội dung trở nên đáng tin; lần sử dụng sau vẫn cần xác minh nguồn và dependency.

## 11. Lỗi thường gặp

| Tình huống | Rủi ro hoặc nguyên nhân | Cách xử lý |
|---|---|---|
| Script từ nguồn không rõ | Có thể chứa lệnh hoặc code thực thi ngoài mục tiêu | Dừng trước /open; xác minh nguồn và review toàn bộ tệp |
| Checksum không khớp | Tệp tải về bị thay đổi, sai phiên bản hoặc giá trị tham chiếu không đúng | Không thực thi; tải lại từ nguồn tin cậy và xác minh giá trị tham chiếu |
| JAR không rõ nguồn trong classpath | Mã thư viện có thể chạy với quyền của phiên | Gỡ khỏi classpath, xác minh nguồn và dependency trước khi dùng |
| Script đọc được bí mật | JShell đang chạy với quyền của tài khoản hiện tại | Dừng thử nghiệm, đánh giá dữ liệu đã truy cập và xoay vòng bí mật nếu bị lộ |
| /exit nhưng tiến trình vẫn còn | Thread, executor hoặc tiến trình con chưa dừng | Xác định tác vụ còn hoạt động, đóng tài nguyên và dừng đúng tiến trình |
| File tạm hoặc kết nối còn tồn tại | Cleanup chưa hoàn tất hoặc tài nguyên nằm ngoài vòng đời JShell | Đóng rõ ràng và kiểm tra trạng thái bên ngoài |
| Muốn cách ly mã bằng Security Manager | Cơ chế không còn là lựa chọn sandbox được hỗ trợ trên JDK hiện đại | Dùng ranh giới cách ly ở cấp hệ điều hành, VM hoặc container được cấu hình hạn chế |

## 12. Checklist nghiệm thu

- [ ] Đã xác định nguồn của mọi đoạn mã, script và thư viện được nạp.
- [ ] Đã kiểm tra nội dung script trước khi dùng /open.
- [ ] Đã xác minh checksum hoặc chữ ký khi nguồn cung cấp thông tin xác thực.
- [ ] Dependency được cố định phiên bản và lấy từ repository đã phê duyệt.
- [ ] Không có credential hoặc dữ liệu nhạy cảm trong snippet, script hay lịch sử.
- [ ] JShell chạy bằng tài khoản không đặc quyền trong môi trường phù hợp.
- [ ] Mã chưa tin cậy được kiểm tra trong môi trường cách ly có giới hạn.
- [ ] Các stream, connection, executor và tiến trình con đã được đóng hoặc dừng.
- [ ] Đã dùng /exit và xác nhận terminal nhận lại quyền điều khiển.
- [ ] File tạm, dữ liệu thử nghiệm và credential được xử lý theo chính sách.
- [ ] Không còn phiên hoặc tiến trình thử nghiệm không cần thiết.

**Tiêu chí hoàn thành:** nguồn mã và dependency đã được xác minh theo mức phù hợp với rủi ro; phiên JShell chỉ chạy với quyền cần thiết; mọi tài nguyên và tác vụ do phiên tạo ra đã được xử lý; JShell đã thoát bằng /exit và môi trường thử nghiệm đã được dọn dẹp.