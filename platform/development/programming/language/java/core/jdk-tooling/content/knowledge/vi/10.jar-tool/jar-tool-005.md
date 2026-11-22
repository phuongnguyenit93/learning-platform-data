# Cập nhật JAR bằng công cụ jar của JDK

## Mục tiêu

Sau bài này, bạn có thể cập nhật một JAR đã tồn tại bằng JDK jar tool; thêm file mới hoặc thay thế class/resource theo đúng đường dẫn bên trong archive; cập nhật manifest; hiểu vì sao lệnh update không xóa các entry cũ; xử lý JAR đã ký; và kiểm tra artifact sau khi cập nhật.

## 1. Cập nhật JAR là gì?

JAR (Java Archive) là một archive dựa trên định dạng ZIP, thường chứa class file, resource, metadata và manifest. Một JAR có thể được dùng làm dependency trên classpath, làm executable JAR hoặc làm modular JAR.

Cập nhật JAR là thay đổi nội dung archive hiện có, ví dụ:

- Thay một class file sau khi biên dịch lại.
- Thêm hoặc thay resource như file properties, XML, JSON, ảnh hoặc template.
- Cập nhật thuộc tính trong manifest.
- Thêm module descriptor hoặc metadata module khi cần.

Công cụ jar đi kèm JDK hỗ trợ chế độ update qua tùy chọn -u hoặc --update. Chế độ này làm việc với một JAR đã tồn tại. Nếu archive chưa tồn tại, hãy tạo nó bằng --create trước.

Cần hiểu đúng phạm vi: jar --update thêm entry mới hoặc thay entry có cùng tên đường dẫn bên trong archive. Nó không biên dịch source code, không tự cập nhật dependency, không chạy test và không tự đồng bộ việc xóa file trong thư mục nguồn.

## 2. Cú pháp cơ bản

Cú pháp tổng quát:

~~~bash
jar --update --file app.jar files...
~~~

Trong đó:

- --update (hoặc -u) chọn chế độ cập nhật.
- --file app.jar (hoặc -f app.jar) chỉ định JAR cần cập nhật.
- files là các file hoặc thư mục được thêm vào archive.

Ví dụ thêm một resource:

~~~bash
jar --update --file app.jar config/app.properties
~~~

Lệnh này thêm file app.properties vào archive theo đường dẫn được xác định từ thư mục làm việc hiện tại. Nếu archive đã có entry cùng đường dẫn, nội dung entry được thay bằng file đầu vào.

Có thể bật verbose để xem các entry được xử lý:

~~~bash
jar --update --verbose --file app.jar config/app.properties
~~~

Các dạng viết ngắn tương ứng:

~~~bash
jar -uf app.jar config/app.properties
~~~

Khi mới học, nên dùng tên tùy chọn đầy đủ để dễ đọc và tránh nhầm lẫn thứ tự tham số.

## 3. Đường dẫn trong JAR và tùy chọn -C

Một entry trong JAR có tên đường dẫn nội bộ. Tên đường dẫn này quan trọng vì class loader, framework hoặc ứng dụng tìm class/resource theo chính đường dẫn đó.

Giả sử file nằm trên đĩa:

~~~text
build/classes/
└── com/
    └── example/
        └── Service.class
~~~

Muốn entry trong JAR có tên:

~~~text
com/example/Service.class
~~~

Hãy chuyển thư mục làm việc của jar tool về build/classes trước khi thêm file:

~~~bash
jar --update --file app.jar -C build/classes com/example/Service.class
~~~

Tùy chọn -C DIR thay đổi thư mục gốc dùng để lấy các file theo sau nó. Phần đường dẫn được ghi vào archive là đường dẫn tương đối bên dưới DIR.

Nếu bỏ -C và chạy từ thư mục project:

~~~bash
jar --update --file app.jar build/classes/com/example/Service.class
~~~

entry có thể mang cả tiền tố build/classes. Khi đó JVM sẽ không tìm thấy class theo tên com.example.Service trên classpath thông thường, vì đường dẫn nội bộ không khớp với package.

Có thể dùng nhiều cặp -C trong cùng một lệnh:

~~~bash
jar --update --file app.jar ^
  -C build/classes com/example/Service.class ^
  -C build/resources config/app.properties
~~~

Dấu ^ ở trên là ký tự nối dòng của Windows Command Prompt. Trong PowerShell hoặc Linux/macOS, cách nối dòng khác nhau; để tránh nhầm shell, có thể viết toàn bộ lệnh trên một dòng:

~~~bash
jar --update --file app.jar -C build/classes com/example/Service.class -C build/resources config/app.properties
~~~

Lệnh này cập nhật class và resource từ hai thư mục khác nhau, đồng thời giữ đúng đường dẫn tương đối bên trong JAR.

## 4. Thêm file mới và thay thế entry cũ

### Thêm resource mới

Giả sử ứng dụng cần thêm file config/app.properties vào JAR:

~~~bash
jar --update --file app.jar -C build/resources config/app.properties
~~~

Sau khi cập nhật, liệt kê archive:

~~~bash
jar --list --file app.jar
~~~

Tìm entry config/app.properties trong danh sách. Có thể dùng verbose để xem thông tin chi tiết hơn:

~~~bash
jar --list --verbose --file app.jar
~~~

### Thay thế một class đã biên dịch

Nếu đã sửa Service.java và biên dịch lại thành Service.class, hãy cập nhật đúng entry:

~~~bash
javac -d build/classes src/com/example/Service.java
jar --update --file app.jar -C build/classes com/example/Service.class
~~~

Entry com/example/Service.class trong JAR sẽ được thay bằng file class mới có cùng đường dẫn nội bộ.

Lưu ý:

- Phải biên dịch source trước khi cập nhật JAR.
- Các class phụ thuộc hoặc API thay đổi cũng có thể cần được biên dịch và cập nhật đồng bộ.
- Cập nhật một class không tự động cập nhật các class liên quan.
- Nếu thay đổi cấu trúc package, tên class hoặc API công khai, hãy kiểm tra mọi consumer của JAR.

### Cập nhật nhiều file cùng lúc

Có thể truyền nhiều file trong một lần update:

~~~bash
jar --update --file app.jar -C build/classes . -C build/resources .
~~~

Lệnh này thêm hoặc thay các entry có tên tương ứng trong hai thư mục. Nó không xóa entry cũ khỏi JAR chỉ vì entry đó không còn tồn tại trong thư mục đầu vào. Đây là điểm khác biệt quan trọng giữa update archive và tạo lại archive từ một tập file hoàn chỉnh.

## 5. Cập nhật manifest

Manifest là file metadata nằm tại:

~~~text
META-INF/MANIFEST.MF
~~~

Manifest có thể chứa thuộc tính như:

- Main-Class: class entry point của executable JAR.
- Implementation-Title: tên implementation.
- Implementation-Version: phiên bản implementation.
- Specification-Title và Specification-Version: thông tin specification.
- Class-Path: các thư viện phụ thuộc bổ sung theo cú pháp manifest.

### Cập nhật Main-Class

Nếu JAR đã có class entry point nhưng cần đổi main class:

~~~bash
jar --update --file app.jar --main-class com.example.Main
~~~

Thuộc tính Main-Class phải dùng fully qualified class name, không có đuôi .class. Class tương ứng phải thực sự có trong archive hoặc classpath cần thiết.

Có thể kiểm tra manifest bằng cách trích xuất:

~~~bash
jar --extract --file app.jar META-INF/MANIFEST.MF
~~~

Sau đó đọc file META-INF/MANIFEST.MF trong thư mục hiện tại.

### Thêm hoặc cập nhật manifest attributes

Tạo file manifest-additions.mf:

~~~text
Implementation-Title: Example Application
Implementation-Version: 1.2.0
Build-Revision: abc123

~~~

Manifest phải có dòng trống kết thúc phần attributes. Dòng cuối có newline là cần thiết để parser đọc đầy đủ thuộc tính.

Cập nhật archive:

~~~bash
jar --update --file app.jar --manifest manifest-additions.mf
~~~

Các thuộc tính trong file manifest đầu vào được đưa vào manifest của JAR; thuộc tính cùng tên có thể được cập nhật. Sau khi thay đổi, hãy trích xuất manifest để xác nhận nội dung thực tế.

Không nên tùy tiện thay toàn bộ manifest của một thư viện hoặc ứng dụng đã được build bởi hệ thống khác. Manifest có thể chứa Class-Path, module metadata, package sealing, digest hoặc thông tin triển khai mà ứng dụng phụ thuộc.

### Cập nhật manifest khác với thêm file thông thường

Không nên đưa file manifest vào JAR như một resource bất kỳ ở một đường dẫn tùy ý. Dùng --manifest hoặc --main-class để jar tool xử lý metadata đúng vị trí và định dạng.

## 6. Cập nhật JAR không tự xóa entry

Chế độ --update hỗ trợ thêm và thay thế entry, nhưng không cung cấp thao tác delete entry trong JAR.

Ví dụ, archive có:

~~~text
config/old.properties
config/new.properties
~~~

Sau khi chạy:

~~~bash
jar --update --file app.jar -C build/resources config/new.properties
~~~

entry config/old.properties vẫn tồn tại nếu không có thao tác khác. jar tool không xem thư mục đầu vào như bản sao chuẩn để tự xóa mọi entry không còn xuất hiện.

### Khi cần xóa entry

Cách an toàn và dễ tái lập nhất là tạo lại JAR từ tập đầu vào đã được chọn lọc:

1. Lấy source/build outputs chuẩn của artifact.
2. Bỏ file không còn cần khỏi tập đầu vào.
3. Tạo một JAR mới với đúng class, resource và manifest cần thiết.
4. Kiểm tra nội dung, chạy test và ký lại JAR nếu quy trình yêu cầu.

Nếu buộc phải thao tác từ archive hiện có, hãy giải nén vào thư mục staging, xóa file cần bỏ trong staging, rồi tạo archive mới từ nội dung còn lại. Giữ riêng manifest và kiểm tra nó được đưa vào JAR mới đúng cách.

Ví dụ minh họa quy trình:

~~~bash
jar --extract --file app.jar --dir staging
~~~

Sau đó xóa file không còn cần trong thư mục staging bằng công cụ của hệ điều hành, rồi đóng gói lại:

~~~bash
jar --create --file app-new.jar --manifest staging/META-INF/MANIFEST.MF -C staging .
~~~

Trước khi dùng quy trình này cho artifact thật, hãy kiểm tra cấu trúc staging, manifest và các file chữ ký. Nếu archive đã ký, không sao chép nguyên các file chữ ký cũ vào artifact đã thay đổi; hãy thực hiện quy trình ký lại theo chính sách phát hành.

Không ghi đè ngay archive production. Tạo app-new.jar, xác minh và chạy thử trước, sau đó mới thay artifact trong quy trình triển khai được kiểm soát.

## 7. JAR đã ký: phải xử lý chữ ký sau khi cập nhật

JAR có thể được ký bằng jarsigner. Chữ ký sử dụng digest của các entry và metadata trong manifest để phát hiện thay đổi nội dung.

Khi cập nhật một JAR đã ký:

- Nếu thay đổi nội dung của một entry đã được ký, digest không còn khớp và xác minh chữ ký của entry đó sẽ thất bại.
- Nếu thêm entry mới sau khi ký, entry mới chưa có chữ ký của signer cũ.
- JAR có thể chứa các entry đã ký và entry chưa ký; điều này không tương đương một artifact đã được ký đầy đủ theo chính sách phát hành.
- Sửa manifest cũng có thể ảnh hưởng đến dữ liệu digest/chữ ký.

Quy trình khuyến nghị là hoàn tất mọi thay đổi trước, sau đó ký artifact cuối cùng bằng khóa và quy trình được tổ chức cho phép.

Xác minh chữ ký:

~~~bash
jarsigner --verify --verbose --certs app.jar
~~~

Đọc toàn bộ warning và kết quả, đặc biệt là entry chưa ký, certificate chain, thuật toán bị vô hiệu hóa và trạng thái timestamp. Nếu quy trình phát hành yêu cầu warning nghiêm trọng làm thất bại, dùng thêm tùy chọn --strict:

~~~bash
jarsigner --verify --strict --verbose --certs app.jar
~~~

Không bỏ qua cảnh báo chỉ vì lệnh trả về mã thoát 0. Hãy xác minh đúng certificate, signer và chính sách trust của môi trường triển khai.

Không chia sẻ private key, keystore password hoặc token trong command line, script, log hay tài liệu. Việc ký phải dùng quy trình quản lý khóa an toàn của tổ chức.

## 8. Cập nhật modular JAR và multi-release JAR

### Modular JAR

Từ Java 9, JAR có thể chứa module descriptor module-info.class ở root. Có thể kiểm tra module:

~~~bash
jar --describe-module --file library.jar
~~~

Khi cần cập nhật module descriptor hoặc metadata module, phải bảo đảm descriptor phù hợp với các package, dependency và exported/opened packages thực tế. Ví dụ cập nhật module descriptor đã biên dịch:

~~~bash
jar --update --file library.jar -C build/module-classes module-info.class
~~~

Nếu module descriptor thay đổi, hãy kiểm tra lại module graph và chạy thử trên module path. Một JAR có module-info.class không thể được xem như một JAR classpath bình thường trong mọi trường hợp; cách phân giải phụ thuộc cách ứng dụng sử dụng nó.

### Multi-release JAR

Multi-release JAR có thể chứa các phiên bản class khác nhau theo thư mục:

~~~text
com/example/Service.class
META-INF/versions/17/com/example/Service.class
META-INF/versions/21/com/example/Service.class
~~~

JVM chọn phiên bản entry phù hợp với release runtime theo quy tắc multi-release JAR, nếu manifest đánh dấu Multi-Release: true.

Khi cập nhật một phiên bản dành riêng cho Java 17, dùng tùy chọn --release:

~~~bash
jar --update --file library.jar --release 17 -C build/classes-17 com/example/Service.class
~~~

Cần bảo đảm entry ở root vẫn cung cấp implementation tương thích với Java version nền thấp nhất mà thư viện hỗ trợ. Các bản versioned phải được kiểm tra cùng nhau, tránh việc một release nhận API khác biệt hoặc thiếu class.

## 9. Ví dụ thực hành hoàn chỉnh

Ví dụ này tạo executable JAR, chạy thử, cập nhật class rồi chạy lại.

### Bước 1: tạo source

Tạo file src/com/example/Main.java:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("version=1");
    }
}
~~~

### Bước 2: biên dịch

~~~bash
javac -d build/classes src/com/example/Main.java
~~~

### Bước 3: tạo JAR lần đầu

~~~bash
jar --create --file app.jar --main-class com.example.Main -C build/classes .
~~~

### Bước 4: chạy và xác nhận output ban đầu

~~~bash
java -jar app.jar
~~~

Output:

~~~text
version=1
~~~

### Bước 5: sửa source và biên dịch lại

Đổi nội dung main thành:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("version=2");
    }
}
~~~

Biên dịch lại:

~~~bash
javac -d build/classes src/com/example/Main.java
~~~

### Bước 6: cập nhật class trong JAR

~~~bash
jar --update --file app.jar -C build/classes com/example/Main.class
~~~

### Bước 7: chạy lại

~~~bash
java -jar app.jar
~~~

Output:

~~~text
version=2
~~~

Tên class và đường dẫn entry không thay đổi nên manifest Main-Class vẫn trỏ đúng com.example.Main. Trong ví dụ thực tế, nếu thay đổi dependency, package, module hoặc manifest, cần cập nhật và kiểm tra các thành phần tương ứng.

## 10. Kiểm tra JAR sau khi cập nhật

Không nên kết luận thành công chỉ vì lệnh jar không báo lỗi. Cần xác minh nội dung archive và khả năng sử dụng.

### Kiểm tra danh sách entry

~~~bash
jar --list --file app.jar
~~~

Xác nhận class/resource mới có đúng đường dẫn nội bộ và entry cũ không mong muốn không còn (nếu đã rebuild).

### Kiểm tra manifest

~~~bash
jar --extract --file app.jar META-INF/MANIFEST.MF
~~~

Đọc các thuộc tính như Main-Class, Implementation-Version, Class-Path và Multi-Release.

### Kiểm tra class và module

Dùng javap để kiểm tra class cụ thể:

~~~bash
javap -classpath app.jar -p com.example.Main
~~~

Nếu JAR là modular:

~~~bash
jar --describe-module --file app.jar
~~~

### Chạy smoke test

Với executable JAR:

~~~bash
java -jar app.jar
~~~

Với library JAR, tạo hoặc chạy một ứng dụng kiểm tra nhỏ sử dụng đúng class/resource được cập nhật. Không phải JAR nào cũng có Main-Class hoặc được chạy trực tiếp bằng -jar.

### Kiểm tra chữ ký

Nếu JAR được ký:

~~~bash
jarsigner --verify --verbose --certs app.jar
~~~

Xác nhận mọi entry cần được bảo vệ đều có signer phù hợp và không có warning ngoài chính sách cho phép.

### So sánh checksum

Sau khi hoàn tất, có thể tính checksum để ghi nhận artifact:

Linux/macOS:

~~~bash
sha256sum app.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash app.jar -Algorithm SHA256
~~~

Lưu checksum cùng version/build metadata để nhận diện chính xác artifact đã được kiểm tra và phát hành.

## 11. Các lỗi thường gặp

### JAR không tồn tại

**Dấu hiệu:** jar --update báo không mở được archive.

**Nguyên nhân:** đường dẫn file sai hoặc archive chưa được tạo.

**Cách xử lý:** kiểm tra thư mục hiện tại và tên file. Nếu chưa có archive, dùng --create để tạo JAR.

### Entry có sai đường dẫn package

**Dấu hiệu:** JAR có class file nhưng JVM báo ClassNotFoundException hoặc NoClassDefFoundError.

**Nguyên nhân:** file được thêm với tiền tố thư mục build không mong muốn hoặc sai package path.

**Cách xử lý:** dùng -C để chọn thư mục gốc, sau đó dùng jar --list để xác nhận entry có dạng com/example/Main.class.

### Cập nhật thư mục nhưng file cũ vẫn còn

**Dấu hiệu:** entry đã xóa khỏi thư mục build vẫn xuất hiện trong JAR.

**Nguyên nhân:** --update chỉ thêm/thay entry, không xóa entry vắng mặt trong input.

**Cách xử lý:** tạo lại JAR từ tập file chuẩn hoặc giải nén vào staging, xóa file không cần rồi đóng gói archive mới.

### Manifest không thay đổi như mong đợi

**Dấu hiệu:** java -jar vẫn chạy main class cũ hoặc thuộc tính version không cập nhật.

**Nguyên nhân:** manifest file không được truyền qua --manifest, tên attribute sai, thiếu dòng kết thúc hoặc đang kiểm tra nhầm JAR.

**Cách xử lý:** dùng --main-class hoặc --manifest, trích xuất META-INF/MANIFEST.MF và đọc nội dung sau update.

### Chữ ký JAR không còn hợp lệ

**Dấu hiệu:** jarsigner verify báo digest error hoặc entry chưa được ký.

**Nguyên nhân:** thay đổi entry đã ký hoặc thêm entry sau khi ký.

**Cách xử lý:** hoàn tất cập nhật trước, sau đó ký lại artifact cuối cùng và xác minh chữ ký.

### Ứng dụng đang chạy vẫn dùng class cũ

**Dấu hiệu:** file JAR trên đĩa đã cập nhật nhưng ứng dụng vẫn cho kết quả cũ.

**Nguyên nhân:** class loader đã nạp class vào JVM; thay đổi file JAR trên đĩa không tự động thay thế class đã nạp trong process đang chạy.

**Cách xử lý:** triển khai artifact mới theo quy trình của ứng dụng và restart/redeploy process khi cần. Không coi việc thay file trên đĩa là hot reload.

### Cập nhật class nhưng quên dependency liên quan

**Dấu hiệu:** lỗi NoSuchMethodError, NoSuchFieldError hoặc linkage error sau khi cập nhật.

**Nguyên nhân:** class mới được biên dịch dựa trên API khác với class/dependency còn lại trong JAR hoặc runtime.

**Cách xử lý:** build lại toàn bộ artifact từ source/dependency đã khóa phiên bản, kiểm thử integration và tránh vá một class đơn lẻ nếu thay đổi API có ảnh hưởng dây chuyền.

## 12. Quy trình cập nhật an toàn

1. Xác định chính xác JAR và version hiện tại.
2. Sao lưu artifact hoặc tạo bản làm việc mới.
3. Xác định entry cần thêm/thay và đường dẫn nội bộ mong muốn.
4. Biên dịch lại class/resource từ source chuẩn.
5. Cập nhật trên bản sao hoặc artifact staging.
6. Kiểm tra danh sách entry và manifest.
7. Chạy unit/integration/smoke test phù hợp.
8. Nếu JAR có chữ ký, ký lại artifact cuối cùng và verify.
9. Tính checksum, ghi version/build metadata.
10. Phát hành hoặc triển khai theo quy trình có thể rollback.

Với sản phẩm được build tự động bằng Gradle hoặc Maven, nên sửa source và build lại JAR bằng pipeline thay vì vá trực tiếp artifact đã phát hành. Thao tác jar --update phù hợp cho việc học, kiểm tra, sửa resource có kiểm soát hoặc xử lý artifact đặc biệt khi bạn hiểu rõ cấu trúc và nguồn gốc của nó.

## 13. Checklist ghi nhớ

- [ ] Dùng --update để cập nhật archive đã tồn tại.
- [ ] Hiểu entry được xác định bằng đường dẫn nội bộ trong JAR.
- [ ] Dùng -C để tránh thêm thừa thư mục gốc vào entry path.
- [ ] Biên dịch class trước khi cập nhật class file.
- [ ] Xác nhận entry trùng tên được thay thế đúng nội dung.
- [ ] Không giả định --update tự xóa entry cũ.
- [ ] Dùng --manifest hoặc --main-class để cập nhật metadata.
- [ ] Kiểm tra module-info.class và multi-release entries khi JAR có module/versioned classes.
- [ ] Xử lý chữ ký sau khi thay đổi nội dung JAR.
- [ ] Dùng jar --list, javap, jarsigner và smoke test để xác minh.
- [ ] Không kỳ vọng process JVM đang chạy tự nạp lại class sau khi file JAR thay đổi.
- [ ] Lưu checksum và giữ khả năng rollback.

## 14. Tài liệu tham khảo chính thức

- [The jar Command — Java SE 27 Tool Specification](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html) — chế độ create/update/list/extract, -C, manifest, main class, module và multi-release JAR.
- [The jar Command — Java SE 24 Tool Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html) — cú pháp và ví dụ cập nhật JAR bằng --update.
- [The jarsigner Command — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html) — cấu trúc chữ ký, digest, xác minh và cảnh báo đối với JAR đã ký.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html) — định dạng manifest, entry và chữ ký JAR.
- [The javap Command — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html) — kiểm tra nội dung class file bên trong JAR.

Cập nhật JAR là thao tác trực tiếp lên archive. Hãy xác định đúng entry path, hiểu giới hạn của update, xác minh manifest/chữ ký và kiểm thử artifact mới trước khi triển khai.
