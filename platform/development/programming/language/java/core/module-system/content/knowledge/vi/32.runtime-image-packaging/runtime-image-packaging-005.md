# Compression, strip debug và reproducibility

## 1. Mục tiêu khi đóng gói runtime image

Khi dùng **jlink** để tạo runtime image cho ứng dụng modular, có thể điều chỉnh nội dung và cách lưu trữ image nhằm giảm dung lượng phân phối, loại bỏ thông tin chỉ phục vụ debug và giúp quy trình build có thể tái lập.

Ba mục tiêu này liên quan nhưng khác nhau:

- **Compression** giảm kích thước một số tài nguyên trong runtime image, đổi lại có thể phát sinh chi phí giải nén hoặc xử lý khi chạy.
- **Strip debug** loại bỏ metadata debug khỏi các module được đưa vào image, giúp image gọn hơn.
- **Reproducibility** hướng tới việc tạo ra cùng một kết quả từ cùng bộ đầu vào và cấu hình build, để có thể kiểm chứng, so sánh và phát hành đáng tin cậy.

Không nên chọn cấu hình chỉ dựa trên kích thước nhỏ nhất. Runtime image phải còn đủ module, tài nguyên và khả năng chẩn đoán cần thiết cho môi trường triển khai. Cần đo kích thước, thời gian khởi động và kiểm thử chức năng trên image thực tế.

## 2. Compression với jlink

Tùy chọn **--compress** điều khiển cách jlink nén tài nguyên trong image. Các mức thường gặp:

| Tùy chọn | Ý nghĩa |
|---|---|
| **--compress=0** | Không bật cơ chế compression của jlink |
| **--compress=1** | Dùng constant string sharing để giảm trùng lặp chuỗi trong dữ liệu class |
| **--compress=2** | Nén tài nguyên bằng ZIP |

Ví dụ tạo image có ZIP compression:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=2 \
  --output runtime-image
~~~

**--compress=2** thường phù hợp khi ưu tiên giảm kích thước image để phân phối hoặc lưu trữ. Việc nén có thể làm tăng chi phí xử lý khi tài nguyên được truy cập, nên cần đo thời gian khởi động và hành vi ứng dụng thay vì giả định image nhỏ hơn luôn chạy nhanh hơn.

Nếu muốn dùng constant string sharing:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=1 \
  --output runtime-image
~~~

Mức 1 xử lý việc chia sẻ chuỗi hằng lặp lại trong dữ liệu class. Đây không phải ZIP compression và không nên so sánh trực tiếp với mức 2 như hai mức nén cùng một thuật toán.

Có thể tắt compression để có cấu hình cơ sở khi đo:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=0 \
  --output runtime-image
~~~

Hãy kiểm tra **jlink --help** của đúng JDK đang dùng vì tùy chọn và cách diễn giải có thể thay đổi giữa các bản phát hành. Khi so sánh, giữ nguyên module đầu vào và mọi tùy chọn khác; chỉ thay mức compression để kết quả đo có ý nghĩa.

## 3. Strip debug với --strip-debug

Tùy chọn **--strip-debug** yêu cầu jlink loại bỏ thông tin debug khỏi các module được đưa vào runtime image:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --strip-debug \
  --output runtime-image
~~~

Thông tin debug trong bytecode có thể bao gồm metadata về dòng nguồn, biến cục bộ và thông tin phục vụ debugger. Loại bỏ metadata này có thể giảm dung lượng image. Đổi lại, việc gỡ lỗi sau triển khai có thể khó hơn vì debugger hoặc công cụ chẩn đoán mất một phần thông tin ánh xạ về mã nguồn.

Cần phân biệt phạm vi của **jlink --strip-debug** với việc biên dịch ứng dụng:

- Nếu module ứng dụng được đưa vào image qua module path, jlink xử lý các module đó cùng các module runtime theo tùy chọn strip.
- Nếu ứng dụng được phân phối riêng dưới dạng JAR trên classpath bên ngoài image, jlink không sửa nội dung JAR đó.
- Với class do dự án biên dịch, **javac -g:none** có thể tắt việc sinh thông tin debug ngay từ bước compile.

Ví dụ:

~~~bash
javac -g:none -d out src/com/example/Main.java
~~~

Nếu cần debug trong môi trường staging hoặc hỗ trợ điều tra sự cố, có thể giữ artifact có debug metadata riêng cho mục đích chẩn đoán và tạo runtime image phát hành với **--strip-debug**. Cần bảo đảm cách lưu trữ artifact debug phù hợp với quy trình phát hành và truy cập nội bộ.

Không nên loại bỏ debug metadata trước khi hoàn tất kiểm thử nếu nhóm phát triển còn cần dùng debugger để xác định lỗi. Hãy quyết định theo yêu cầu vận hành và chính sách hỗ trợ của ứng dụng.

## 4. Các tùy chọn giảm dung lượng liên quan

Ngoài compression và strip debug, jlink có thể loại bỏ một số thành phần không cần cho runtime:

- **--no-header-files** bỏ các native header files.
- **--no-man-pages** bỏ các trang hướng dẫn.
- **--strip-debug** bỏ debug metadata trong module image.
- **--compress=2** nén tài nguyên bằng ZIP.

Ví dụ:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=2 \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output runtime-image
~~~

Hai tùy chọn **--no-header-files** và **--no-man-pages** thường phù hợp với image chỉ dùng để chạy ứng dụng. Nếu image còn phục vụ phát triển hoặc biên dịch mã native, hãy kiểm tra xem có cần giữ header files hay không.

Việc bỏ man pages không làm thay đổi logic ứng dụng, nhưng có thể khiến người vận hành không tra cứu được tài liệu cục bộ trong image. Hãy bảo đảm tài liệu vận hành được cung cấp ở nơi khác nếu cần.

Ngoài ra, lựa chọn module qua **--add-modules** thường ảnh hưởng đáng kể đến kích thước image. Trước khi tối ưu compression, hãy xác định module gốc và phụ thuộc thực sự cần thiết. Không loại bỏ module chỉ để giảm vài MB nếu chức năng ứng dụng còn cần module đó ở runtime.

## 5. Ví dụ cấu hình runtime image cho phát hành

Giả sử ứng dụng modular có tên **com.example.app**, các module ứng dụng đã biên dịch nằm trong **mods**, và JDK hiện tại cung cấp các module trong **$JAVA_HOME/jmods**.

Có thể tạo image tối ưu cho phát hành:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=2 \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --launcher app=com.example.app/com.example.app.Main \
  --output runtime-image
~~~

Trên Windows PowerShell, dấu phân cách các phần tử trong module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --compress=2 --strip-debug --no-header-files --no-man-pages --launcher app=com.example.app/com.example.app.Main --output runtime-image
~~~

Thay tên module và main class bằng giá trị của dự án. Thư mục output phải chưa tồn tại hoặc được dọn theo quy trình build có kiểm soát trước khi chạy lệnh.

Nếu ứng dụng dùng service provider, hãy xác định có cần **--bind-services** hay không. Khi dùng tùy chọn này, các provider có thể được liên kết vào image theo metadata service. Cần cố định module path và các provider đầu vào để lần build sau không vô tình thu nhận thêm module mới.

Có thể lưu các tùy chọn jlink đã dùng vào file:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=2 \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --save-opts jlink-options.txt \
  --output runtime-image
~~~

File **jlink-options.txt** giúp lưu lại cấu hình dòng lệnh để xem xét và tái sử dụng. File này không tự khóa phiên bản JDK, module đầu vào hoặc môi trường hệ điều hành; các thông tin đó vẫn cần được quản lý riêng.

## 6. Reproducibility là gì?

Một build có tính tái lập khi cùng một bộ đầu vào và cấu hình được sử dụng lại, quy trình tạo ra kết quả tương đương có thể kiểm chứng. Có hai mức thường được quan tâm:

- **Functional reproducibility:** runtime image có cùng module, cùng cấu hình và hành vi ứng dụng như bản build tham chiếu.
- **Bit-for-bit reproducibility:** mọi file đầu ra có cùng byte và cùng hash giữa các lần build.

Hai mức này không giống nhau. Hai runtime image có thể chạy giống nhau nhưng khác hash do metadata, timestamp hoặc khác biệt từ toolchain. Nếu yêu cầu phát hành cần so sánh hash chính xác, phải kiểm tra thực tế trên cùng môi trường và không mặc định rằng jlink bảo đảm bit-for-bit reproducibility trong mọi trường hợp.

Reproducibility là thuộc tính của toàn bộ pipeline, gồm artifact ứng dụng, JDK, module đầu vào, tùy chọn jlink, môi trường build và cách đóng gói kết quả. Chỉ lưu lại một câu lệnh jlink chưa đủ để tái lập toàn bộ image.

## 7. Cố định đầu vào và môi trường build

Để các lần build có thể so sánh, nên kiểm soát các yếu tố sau:

1. **JDK:** dùng cùng nhà cung cấp, phiên bản, bản vá và build number. Ghi lại kết quả của **java --version** và **jlink --version**.
2. **Nền tảng:** tạo image cho đúng hệ điều hành và kiến trúc đích. Runtime image thường phụ thuộc nền tảng, nên image Linux không thể mặc định thay thế image Windows hoặc macOS.
3. **Module đầu vào:** dùng đúng phiên bản JAR/module đã được xác minh hash. Tránh thay đổi nội dung thư mục module path giữa các lần build.
4. **Module graph:** cố định danh sách **--add-modules**, cách dùng **--bind-services** và các module provider được phép tham gia.
5. **Tùy chọn đóng gói:** giữ ổn định compression, strip debug, header/man pages, launcher và các tùy chọn khác.
6. **Artifact ứng dụng:** cấu hình build JAR có thể tái lập, bao gồm thứ tự nội dung và metadata archive nếu quy trình cần so sánh hash.
7. **Môi trường:** ghi lại hệ điều hành, kiến trúc, locale và các biến môi trường liên quan đến build.
8. **Đường dẫn và đầu ra:** dùng thư mục build sạch, đường dẫn đầu vào cố định và không ghi đè image đang được phát hành.

Nếu module path lấy nội dung từ nhiều thư mục, hãy ghi lại chính xác các thư mục và phiên bản module. Việc một thư viện được nâng phiên bản hoặc một provider mới xuất hiện có thể làm thay đổi module graph và image đầu ra.

## 8. Lưu lại bằng chứng của mỗi lần build

Một manifest build có thể lưu các thông tin:

~~~text
Application: com.example.app
JDK vendor: <vendor>
JDK version: <version and build>
Operating system: <OS and version>
Architecture: <architecture>
Module roots: com.example.app
Module path inputs: <immutable artifact list>
Compression: 2
Strip debug: true
No header files: true
No man pages: true
Bind services: false
Launcher: app=com.example.app/com.example.app.Main
Output: runtime-image
~~~

Các giá trị trong dấu ngoặc nhọn là chỗ điền dữ liệu thực tế. Không dùng manifest mẫu này như bằng chứng rằng image đã được tạo với cấu hình tương ứng; nó phải được sinh hoặc lưu cùng build thực tế.

Nên lưu thêm:

- Lệnh jlink đầy đủ hoặc file **--save-opts**.
- Hash của từng JAR/module đầu vào.
- Hash của image hoặc từng file trong image.
- Log build và kết quả kiểm thử.
- Danh sách module có trong image.

Nhờ đó, khi có sự cố hoặc cần so sánh hai bản phát hành, có thể xác định thay đổi đến từ JDK, module đầu vào, tùy chọn đóng gói hay ứng dụng.

## 9. Kiểm chứng runtime image

Sau khi tạo image, kiểm tra phiên bản Java và module có trong image:

~~~bash
runtime-image/bin/java --version
runtime-image/bin/java --list-modules
~~~

Có thể liệt kê nội dung module image bằng công cụ **jimage** từ JDK:

~~~bash
jimage list runtime-image/lib/modules
~~~

Kiểm tra launcher:

~~~bash
runtime-image/bin/app
~~~

Nếu không tạo launcher riêng, chạy module trực tiếp:

~~~bash
runtime-image/bin/java -m com.example.app/com.example.app.Main
~~~

Để đo dung lượng trên Linux/macOS:

~~~bash
du -sh runtime-image
~~~

Trên PowerShell:

~~~powershell
$bytes = (Get-ChildItem -LiteralPath runtime-image -Recurse -File | Measure-Object -Property Length -Sum).Sum
"{0:N2} MB" -f ($bytes / 1MB)
~~~

Khi so sánh compression, tạo các image riêng với **--compress=0**, **--compress=1** và **--compress=2**, giữ các yếu tố còn lại giống nhau. Ghi lại dung lượng, thời gian khởi động và kết quả workload đại diện.

Không nên đo một lần duy nhất. Thời gian khởi động có thể chịu ảnh hưởng của cache hệ điều hành, JIT, tải đĩa và môi trường chạy. Dùng cùng máy, cùng workload, nhiều lượt đo và ghi rõ phương pháp để kết quả có thể so sánh.

## 10. Kiểm tra tính tái lập giữa hai lần build

Một quy trình kiểm tra cơ bản:

1. Build image lần thứ nhất trong thư mục sạch.
2. Lưu manifest, log, danh sách module và hash của đầu vào.
3. Build lại lần thứ hai từ cùng bộ artifact, cùng JDK và cùng tùy chọn trong một thư mục sạch khác.
4. So sánh cây thư mục, kích thước và hash file.
5. Nếu hash khác, xác định file nào khác và kiểm tra metadata, timestamp, nội dung module hoặc khác biệt toolchain.
6. Chạy smoke test và các kiểm thử chức năng trên cả hai image.
7. Lưu kết quả so sánh cùng manifest để làm bằng chứng phát hành.

Ví dụ tính hash cho một file trên Linux:

~~~bash
sha256sum runtime-image/lib/modules
~~~

Trên PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 runtime-image\lib\modules
~~~

Có thể so sánh hash của từng file thay vì chỉ so sánh một file lớn. Với image chứa nhiều file, cần có script hoặc công cụ build tạo danh sách đường dẫn và hash theo thứ tự ổn định.

Nếu yêu cầu là bit-for-bit reproducibility, phải xử lý cả khác biệt metadata và đóng gói. Nếu chỉ yêu cầu image có hành vi tương đương, cần kiểm tra module graph, file cấu hình, resource và test runtime. Hãy ghi rõ tiêu chí mà pipeline đang xác nhận.

## 11. Các lỗi thường gặp khi tối ưu

**Image nhỏ hơn nhưng khởi động chậm hơn**

Compression có thể giảm dữ liệu lưu trữ nhưng tăng chi phí xử lý khi truy cập. Đo trên môi trường triển khai thực tế và chọn mức phù hợp với mục tiêu.

**Mất khả năng debug sau khi strip**

**--strip-debug** loại bỏ metadata debug khỏi module trong image. Nếu cần điều tra sự cố, giữ artifact có thông tin debug riêng hoặc tạo image chẩn đoán cho môi trường phù hợp.

**Thư viện ứng dụng vẫn còn debug metadata**

Nếu ứng dụng JAR được phân phối riêng trên classpath, **jlink --strip-debug** không xử lý JAR đó. Có thể cấu hình compiler như **javac -g:none** hoặc tùy chọn tương ứng của build tool nếu thực sự muốn bỏ metadata từ bước compile.

**Image thay đổi dù câu lệnh jlink giống nhau**

Kiểm tra JDK build, OS/architecture, hash module đầu vào, provider được tìm thấy, module path và metadata của artifact. Cùng câu lệnh không đảm bảo cùng đầu ra nếu môi trường hoặc đầu vào đã thay đổi.

**Module mới xuất hiện trong image**

Nếu dùng **--bind-services**, một provider mới trên module path có thể được liên kết vào image. Cố định tập module đầu vào và kiểm tra danh sách module sau build.

**Build không thể tái lập trên máy khác**

Runtime image thường gắn với nền tảng và JDK cụ thể. Tạo image riêng cho từng OS/architecture bằng toolchain đã khóa phiên bản; lưu lại manifest và artifact đầu vào của từng nền tảng.

## 12. Quy trình đóng gói đề xuất

1. Xác định module gốc và các phụ thuộc cần có trong runtime image.
2. Khóa JDK vendor/version/build và nền tảng đích.
3. Tạo artifact module từ nguồn với cấu hình build có thể tái lập.
4. Lưu hash và manifest của module đầu vào.
5. Chọn **--compress** theo mục tiêu dung lượng và thời gian chạy.
6. Chọn **--strip-debug** theo nhu cầu chẩn đoán và hỗ trợ.
7. Chỉ bật **--no-header-files** và **--no-man-pages** khi image không cần các thành phần đó.
8. Lưu cấu hình jlink bằng **--save-opts** và ghi lại các tùy chọn thực tế.
9. Tạo image trong thư mục sạch, kiểm tra module list và chạy smoke test.
10. Đo kích thước, startup và workload đại diện.
11. Build lần thứ hai từ cùng đầu vào để kiểm tra tính tái lập theo tiêu chí của dự án.
12. Lưu hash, log, manifest và kết quả kiểm thử cùng bản phát hành.

## 13. Ghi nhớ

- **--compress=0** tắt compression; **--compress=1** dùng constant string sharing; **--compress=2** dùng ZIP compression trên các JDK hỗ trợ các mức này.
- **--strip-debug** bỏ debug metadata của các module được đóng gói vào image.
- **javac -g:none** điều khiển debug metadata ở bước biên dịch class của ứng dụng.
- **--no-header-files** và **--no-man-pages** loại bỏ thành phần không cần thiết cho nhiều runtime deployment.
- **--save-opts** lưu lại tùy chọn jlink để kiểm tra và tái sử dụng, nhưng không khóa JDK hoặc module đầu vào.
- Reproducibility cần cố định toolchain, module, artifact, cấu hình và môi trường.
- So sánh hash để kiểm tra byte-for-byte; chạy kiểm thử để xác nhận hành vi runtime.
- Luôn đo compression và kiểm thử image trên đúng nền tảng sẽ triển khai.

Một runtime image tốt cần đáp ứng cả kích thước, khả năng chẩn đoán và tính tái lập của quy trình phát hành. Hãy chọn compression và strip debug dựa trên số liệu đo được, đồng thời lưu đầy đủ JDK, module đầu vào, lệnh jlink và kết quả xác minh để có thể tạo lại và kiểm tra bản image sau này.
