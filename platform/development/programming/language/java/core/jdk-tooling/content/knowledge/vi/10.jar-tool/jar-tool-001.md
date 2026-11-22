# Lệnh jar trong JDK

JAR (Java ARchive) là định dạng archive dựa trên ZIP, dùng để gom class file, tài nguyên, metadata và đôi khi cả module descriptor vào một tệp. Công cụ **jar** đi kèm JDK giúp tạo, liệt kê, cập nhật, giải nén và kiểm tra JAR. Đây là công cụ đóng gói; nó không biên dịch mã nguồn Java và cũng không tự bảo đảm một JAR có thể chạy độc lập.

Bài viết trình bày các thao tác jar thường dùng trong dự án Java, từ đóng gói class file đến tạo executable JAR, modular JAR và multi-release JAR. Các ví dụ lệnh dùng cú pháp của JDK hiện đại; hãy kiểm tra jar --help trên JDK đang cài vì một số tùy chọn chỉ có ở những phiên bản nhất định.

## 1. JAR là gì?

Một tệp JAR là archive ZIP có quy ước cấu trúc và metadata dành cho hệ sinh thái Java. Nó có thể chứa:

- Các tệp .class đã được biên dịch.
- Tài nguyên như properties, XML, JSON, ảnh hoặc tệp cấu hình.
- Thư mục META-INF chứa manifest và metadata khác.
- Module descriptor module-info.class ở gốc archive nếu đó là modular JAR.
- Các chữ ký số và tệp liên quan nếu archive được ký.

Ví dụ cấu trúc JAR:

~~~text
app.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        └── Main.class
~~~

JAR thường dùng để:

- Phân phối thư viện Java.
- Đóng gói ứng dụng để chạy bằng Java launcher.
- Đóng gói module cho Java Platform Module System (JPMS).
- Chứa tài nguyên mà ứng dụng đọc qua class loader.
- Phân phối các phiên bản class khác nhau trong multi-release JAR.

### JAR không đồng nghĩa với executable JAR

Một JAR chỉ là archive. Muốn chạy bằng lệnh java -jar, archive phải có điểm vào được khai báo trong manifest, thường là thuộc tính Main-Class. Ứng dụng cũng cần có đủ thư viện phụ thuộc theo cách đóng gói hoặc cấu hình classpath phù hợp.

Một JAR thư viện có thể không có Main-Class và vẫn hoàn toàn hợp lệ để được ứng dụng khác sử dụng.

## 2. Cú pháp tổng quát của jar

Cú pháp phổ biến:

~~~bash
jar [OPTIONS] [FILES]
~~~

Công cụ jar có các chế độ thao tác chính:

| Chế độ | Tùy chọn dài | Tùy chọn ngắn | Công dụng |
|---|---|---|---|
| Create | --create | -c | Tạo archive mới |
| List | --list | -t | Liệt kê nội dung archive |
| Update | --update | -u | Thêm hoặc thay thế entry trong archive |
| Extract | --extract | -x | Giải nén toàn bộ hoặc một số entry |
| Describe module | --describe-module | -d | Hiển thị module descriptor hoặc tên automatic module |
| Validate | --validate | Không có dạng ngắn tương ứng | Kiểm tra một số ràng buộc của archive, đặc biệt multi-release JAR |

Các tùy chọn thường gặp:

- --file hoặc -f: tên tệp archive.
- --verbose hoặc -v: in chi tiết các entry được xử lý.
- --manifest hoặc -m: dùng tệp manifest được cung cấp.
- --main-class hoặc -e: khai báo lớp chính cho JAR có thể khởi chạy.
- --module-version: ghi phiên bản module khi tạo modular JAR hoặc cập nhật JAR phù hợp.
- -C: chuyển thư mục làm việc cho các tệp tiếp theo trong lệnh jar.
- --no-compress hoặc -0: lưu entry mà không nén.
- --date: đặt timestamp cho các entry trên JDK có hỗ trợ.
- --release: đưa các tệp tiếp theo vào thư mục phiên bản của multi-release JAR.

Không nên ghép tùy chọn một cách tùy ý. Một số tùy chọn chỉ hợp lệ trong chế độ create/update hoặc extract. Có thể xem cú pháp chính xác của JDK hiện tại bằng:

~~~bash
jar --help
jar --version
~~~

## 3. Chuẩn bị ví dụ Java

Tạo một chương trình nhỏ:

~~~text
jar-demo/
└── src/
    └── com/
        └── example/
            └── Main.java
~~~

Nội dung src/com/example/Main.java:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Biên dịch mã nguồn bằng JDK 17 trở lên:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Sau khi biên dịch, class file nằm tại:

~~~text
out/
└── com/
    └── example/
        └── Main.class
~~~

Lưu ý:

- javac tạo class file; jar chỉ đóng gói các tệp đã có.
- Tùy chọn -d out đặt thư mục đầu ra cho compiler.
- Cấu trúc package được tạo bên dưới out.
- Khi dùng -C out trong lệnh jar, đường dẫn bên trong archive bắt đầu từ thư mục out, vì vậy entry sẽ là com/example/Main.class.

## 4. Tạo JAR bằng --create

Tạo archive chứa toàn bộ nội dung thư mục out:

~~~bash
jar --create --file app.jar -C out .
~~~

Có thể viết ngắn:

~~~bash
jar -c -f app.jar -C out .
~~~

Giải thích:

- --create yêu cầu tạo archive.
- --file app.jar đặt tên tệp đầu ra.
- -C out chuyển vào thư mục out trước khi lấy các tệp tiếp theo.
- Dấu chấm chỉ toàn bộ nội dung trong thư mục hiện tại sau khi chuyển bằng -C.

Để in các entry trong quá trình tạo:

~~~bash
jar --create --verbose --file app.jar -C out .
~~~

Tùy chọn -C rất hữu ích để kiểm soát đường dẫn bên trong archive. Nếu chạy jar từ thư mục dự án và đưa trực tiếp đường dẫn out/com/example/Main.class mà không dùng -C, entry có thể chứa thêm tiền tố out/. Khi đó class loader có thể không tìm được lớp theo tên package dự kiến.

### Tạo archive từ một số tệp cụ thể

Có thể chỉ định tệp cần đưa vào archive:

~~~bash
jar --create --file selected.jar -C out com/example/Main.class
~~~

Lệnh trên chỉ đóng gói class file Main.class. Nếu ứng dụng cần thêm resource hoặc class phụ thuộc, phải đưa chúng vào archive hoặc cung cấp qua cơ chế phụ thuộc khác.

### Tạo JAR không nén

Mặc định, jar nén các entry theo cơ chế ZIP. Có thể lưu entry mà không nén bằng:

~~~bash
jar --create --no-compress --file app-stored.jar -C out .
~~~

Không nén có thể hữu ích trong một số quy trình cần giảm chi phí giải nén hoặc đóng gói lại, nhưng archive thường lớn hơn. Hãy đo trên workload thực tế trước khi chọn.

## 5. Liệt kê và kiểm tra nội dung JAR

Dùng --list để xem danh sách entry:

~~~bash
jar --list --file app.jar
~~~

Dạng ngắn:

~~~bash
jar -tf app.jar
~~~

Dùng --verbose để xem thêm metadata như kích thước và timestamp:

~~~bash
jar --list --verbose --file app.jar
~~~

Ví dụ, archive vừa tạo cần có entry tương tự:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Main.class
~~~

Thứ tự hoặc một số thư mục trung gian được liệt kê có thể khác tùy phiên bản công cụ và cách tạo archive. Điều quan trọng là đường dẫn entry phải khớp với package và tên lớp.

Có thể dùng jar --list trước khi phát hành để kiểm tra:

- Class file có nằm đúng đường dẫn package không.
- Resource cần thiết có được đóng gói không.
- Có vô tình đưa tệp build, log hoặc cấu hình cục bộ vào archive không.
- Manifest có xuất hiện như mong đợi không.
- Archive có chứa các tệp trùng tên hoặc entry không mong muốn không.

## 6. Giải nén JAR bằng --extract

Giải nén toàn bộ archive vào thư mục hiện tại:

~~~bash
jar --extract --file app.jar
~~~

Dạng ngắn:

~~~bash
jar -xf app.jar
~~~

Chỉ định thư mục giải nén trên JDK hỗ trợ tùy chọn --dir:

~~~bash
jar --extract --file app.jar --dir extracted
~~~

Hoặc dùng -C để chỉ định thư mục đích:

~~~bash
jar --extract --file app.jar -C extracted
~~~

Có thể giải nén một số entry cụ thể bằng cách nêu tên entry sau các tùy chọn:

~~~bash
jar --extract --file app.jar com/example/Main.class
~~~

Nếu thư mục đích đã có tệp cùng tên, chế độ extract mặc định có thể ghi đè. Tùy chọn --keep-old-files hoặc -k trên JDK hỗ trợ có thể giữ nguyên tệp hiện có.

Chỉ giải nén archive đáng tin cậy hoặc kiểm tra nội dung và đường dẫn entry trước khi giải nén vào thư mục nhạy cảm. Tránh giải nén trực tiếp archive không rõ nguồn gốc vào thư mục dự án hoặc thư mục hệ thống.

## 7. Cập nhật JAR bằng --update

--update thêm entry mới hoặc thay thế entry cùng tên trong archive hiện có. Ví dụ, sau khi tạo app.jar, có thể thêm thư mục resources:

~~~text
resources/
└── app.properties
~~~

Cập nhật:

~~~bash
jar --update --file app.jar -C resources .
~~~

Nếu archive đã có entry cùng đường dẫn, entry được cập nhật bằng nội dung mới. Các entry khác vẫn được giữ lại.

Có thể dùng verbose để quan sát:

~~~bash
jar --update --verbose --file app.jar -C resources .
~~~

Cần nhớ:

- --update yêu cầu archive đã tồn tại.
- Tên và đường dẫn entry được tính từ thư mục làm việc hiện tại của jar sau tùy chọn -C.
- Lệnh update không phải công cụ xóa entry. Muốn loại bỏ nội dung, thường tạo lại archive từ tập tệp mong muốn.
- Khi cập nhật executable JAR, không làm mất hoặc vô tình thay đổi manifest cần thiết.
- Nếu thay class file, phải bảo đảm các class và resource liên quan vẫn tương thích.

## 8. Manifest và executable JAR

**Manifest** là tệp metadata thường nằm tại META-INF/MANIFEST.MF. Manifest gồm các thuộc tính dạng tên: giá trị, chia thành các dòng; mỗi section được ngăn cách bởi dòng trống.

Một manifest tối thiểu có thể là:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main

~~~

Dòng trống cuối cùng kết thúc main section. Manifest dùng UTF-8 với các quy tắc định dạng và giới hạn dòng riêng; nếu có giá trị dài hoặc ký tự đặc biệt, nên để công cụ jar tạo thuộc tính thay vì tự nối chuỗi không đúng định dạng.

### Tạo executable JAR bằng --main-class

Với thư mục out chứa Main.class:

~~~bash
jar --create --file app.jar --main-class com.example.Main -C out .
~~~

Sau đó chạy:

~~~bash
java -jar app.jar
~~~

Output:

~~~text
Hello, Java!
~~~

Truyền tham số ứng dụng sau tên JAR:

~~~bash
java -jar app.jar "JDK tooling"
~~~

Output:

~~~text
Hello, JDK tooling!
~~~

### Dùng manifest tự tạo

Có thể cung cấp manifest riêng:

~~~bash
jar --create --file app-manifest.jar --manifest manifest.mf -C out .
~~~

Nếu manifest.mf có Main-Class, JAR có thể được chạy bằng java -jar. Có thể xem manifest sau khi tạo bằng cách liệt kê hoặc giải nén archive rồi đọc META-INF/MANIFEST.MF.

Không nên vừa cung cấp manifest có Main-Class vừa đặt một giá trị --main-class khác nếu không có chủ đích. Hãy giữ một nguồn cấu hình điểm vào rõ ràng.

### Dependencies của executable JAR

Khai báo Main-Class chỉ xác định lớp chính, không tự đóng gói mọi thư viện mà ứng dụng cần.

Một ứng dụng có thể xử lý dependency bằng:

- Đóng gói thư viện theo cấu trúc mà ứng dụng hoặc launcher hỗ trợ.
- Dùng manifest Class-Path để tham chiếu các JAR khác theo quy tắc URL tương đối.
- Dùng build tool tạo executable/fat JAR theo cơ chế của plugin.
- Dùng module path nếu ứng dụng được tổ chức thành các named module.

Khi chạy bằng java -jar, launcher sử dụng classpath được xác định cho chế độ JAR và manifest; không coi -cp là cách bổ sung classpath thông thường cho cùng lệnh.

## 9. Modular JAR và lệnh --describe-module

Một **modular JAR** chứa module-info.class ở gốc archive. Module descriptor khai báo tên module, requires, exports, opens và các thông tin module khác.

Ví dụ module-info.java:

~~~java
module com.example.app {
    exports com.example.app;
}
~~~

Sau khi biên dịch module, giả sử đầu ra nằm trong thư mục mods/com.example.app và chứa module-info.class ở gốc thư mục đó. Có thể đóng gói:

~~~bash
jar --create --file app-module.jar --main-class com.example.app.Main -C mods/com.example.app .
~~~

Tùy chọn --main-class ghi lớp chính cho module JAR phù hợp. Tùy chọn --module-version có thể ghi phiên bản module:

~~~bash
jar --create --file app-module.jar \
  --main-class com.example.app.Main \
  --module-version 1.0 \
  -C mods/com.example.app .
~~~

Kiểm tra module descriptor:

~~~bash
jar --describe-module --file app-module.jar
~~~

Lệnh này hiển thị thông tin module được đọc từ archive. Nếu JAR không có module descriptor, công cụ có thể báo không tìm thấy descriptor hoặc hiển thị thông tin automatic module tùy trường hợp và phiên bản JDK.

Chạy modular JAR qua module path:

~~~bash
java --module-path app-module.jar -m com.example.app
~~~

Với modular JAR có Main-Class, cú pháp chạy module vẫn dựa trên module path và module name. Với JAR thường không có module descriptor, chế độ java -jar và classpath là cách chạy phổ biến hơn.

## 10. Multi-release JAR

**Multi-release JAR** cho phép một archive chứa các phiên bản class hoặc resource dành riêng cho các phiên bản Java khác nhau. Runtime chọn entry phù hợp với phiên bản Java đang chạy, miễn là manifest đánh dấu archive là multi-release.

Cấu trúc ví dụ:

~~~text
multi-release.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 21/
│           └── com/example/Feature.class
└── com/
    └── example/
        └── Feature.class
~~~

Các class trong gốc archive là phiên bản cơ sở. Các entry bên dưới META-INF/versions/N được dùng cho runtime phiên bản N trở lên theo quy tắc multi-release JAR.

Có thể tạo multi-release JAR bằng tùy chọn --release. Ví dụ, thư mục base chứa class cơ sở và thư mục java21 chứa class thay thế cho Java 21:

~~~bash
jar --create --file library.jar -C base . --release 21 -C java21 .
~~~

Tùy chọn --release đặt các tệp tiếp theo vào thư mục phiên bản tương ứng trong archive. Công cụ jar thiết lập metadata multi-release cần thiết khi tạo archive theo cơ chế này.

Kiểm tra cấu trúc:

~~~bash
jar --list --file library.jar
~~~

Với JDK hỗ trợ, có thể kiểm tra tính nhất quán của multi-release JAR:

~~~bash
jar --validate --file library.jar
~~~

Việc validate tập trung vào các quy tắc nhất quán của API giữa các phiên bản trong multi-release JAR; nó không thay thế việc chạy test trên từng phiên bản Java mục tiêu.

## 11. Tạo archive có thể tái lập

Trong build pipeline, hai lần build cùng source có thể tạo JAR khác nhau nếu metadata như timestamp, thứ tự entry hoặc nội dung manifest thay đổi.

Một số nguyên tắc để tăng khả năng tái lập:

- Dùng cùng phiên bản JDK và công cụ build.
- Kiểm soát danh sách tệp đầu vào và loại bỏ tệp tạm.
- Tạo manifest ổn định.
- Không đóng gói log, cache hoặc dữ liệu phụ thuộc môi trường.
- Nếu JDK hỗ trợ --date, đặt timestamp archive theo một giá trị chuẩn đã thống nhất.
- Kiểm tra checksum của artifact sau khi build.

Ví dụ dùng timestamp cố định trên JDK hỗ trợ tùy chọn --date:

~~~bash
jar --create --file app.jar --date 2024-01-01T00:00:00Z -C out .
~~~

Cần xác minh cú pháp --date trong jar --help của JDK đang dùng. Tính tái lập hoàn toàn còn phụ thuộc thứ tự đầu vào, compiler, manifest, resource filtering và các bước build khác.

## 12. JAR, ký số và kiểm tra tính toàn vẹn

Công cụ jar đóng gói archive; nó không tự thực hiện quy trình ký số. JDK cung cấp các công cụ liên quan:

- **keytool** quản lý keystore, key pair và certificate.
- **jarsigner** ký JAR và xác minh chữ ký.
- **jar** tạo hoặc thao tác nội dung archive.

Ví dụ xác minh chữ ký của một JAR:

~~~bash
jarsigner --verify --verbose --certs app.jar
~~~

Kết quả xác minh cần được đánh giá cùng nguồn certificate, trust policy và quy trình phân phối. Một JAR có chữ ký hợp lệ không tự động có nghĩa là mã bên trong an toàn; chữ ký chủ yếu hỗ trợ xác thực nguồn và phát hiện thay đổi so với nội dung đã ký.

Khi cập nhật nội dung một JAR đã ký, chữ ký hiện có có thể không còn hợp lệ. Sau khi thay đổi, cần ký lại theo quy trình phát hành và xác minh lại artifact.

## 13. Lỗi thường gặp

### Could not find or load main class

Nguyên nhân có thể là Main-Class sai, class file không nằm đúng đường dẫn package, hoặc executable JAR thiếu lớp chính. Kiểm tra manifest và danh sách entry bằng jar --list.

### Invalid or corrupt jarfile

Archive có thể bị hỏng, tải chưa đầy đủ hoặc không phải JAR/ZIP hợp lệ. Kiểm tra kích thước, checksum và tạo lại artifact từ nguồn build tin cậy.

### No main manifest attribute

JAR không có thuộc tính Main-Class. Tạo lại với --main-class hoặc cung cấp manifest chứa Main-Class nếu mục tiêu là chạy bằng java -jar.

### NoClassDefFoundError hoặc ClassNotFoundException

Một dependency hoặc class cần thiết không có trong classpath/module path tại runtime. Main-Class không tự đóng gói dependency. Kiểm tra manifest Class-Path, cấu hình launcher hoặc cách build executable JAR.

### Resource không tìm thấy

Resource có thể bị đóng gói sai đường dẫn hoặc không được đưa vào archive. Kiểm tra entry bằng jar --list và đọc resource qua class loader theo đường dẫn tương ứng.

### Update nhưng nội dung cũ vẫn còn

Lệnh --update thêm hoặc thay thế entry; nó không xóa entry không còn trong thư mục nguồn. Nếu muốn archive chỉ chứa tập tệp mới, hãy tạo lại archive từ đầu với danh sách đầu vào chính xác.

### Modular JAR không phân giải được

Kiểm tra module-info.class có ở gốc JAR không, module name, requires, exports và module path. Dùng jar --describe-module và java --show-module-resolution để hỗ trợ chẩn đoán.

### Chữ ký không hợp lệ sau khi cập nhật

Thay đổi nội dung archive có thể làm chữ ký cũ không còn phù hợp. Ký lại bằng jarsigner theo quy trình phát hành và xác minh sau khi ký.

## 14. Checklist sử dụng jar

- Biên dịch mã nguồn trước khi đóng gói; jar không thay thế javac.
- Chọn đúng tệp và thư mục đầu vào để tránh đóng gói dữ liệu không cần thiết.
- Dùng -C để kiểm soát đường dẫn entry bên trong archive.
- Kiểm tra nội dung bằng jar --list trước khi phân phối.
- Khai báo Main-Class khi cần chạy bằng java -jar.
- Xác định rõ dependency của ứng dụng; Main-Class không tự đưa thư viện phụ thuộc vào JAR.
- Giữ module-info.class ở gốc archive khi tạo modular JAR.
- Dùng --release đúng cách khi tạo multi-release JAR.
- Kiểm tra archive bằng jar --describe-module hoặc --validate khi phù hợp.
- Không coi --update là thao tác xóa; tạo lại archive nếu cần loại bỏ entry.
- Ký lại và xác minh JAR sau khi thay đổi nội dung của archive đã ký.
- Giữ phiên bản JDK và quy trình build nhất quán để artifact dễ tái lập.

## 15. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| JAR | Archive dựa trên ZIP theo quy ước Java |
| Entry | Một tệp hoặc thư mục được lưu trong archive |
| Manifest | Metadata trong META-INF/MANIFEST.MF |
| Main-Class | Thuộc tính xác định lớp chính cho executable JAR |
| Executable JAR | JAR có thể được khởi chạy bằng java -jar |
| Modular JAR | JAR có module-info.class ở gốc archive |
| Multi-release JAR | JAR chứa các phiên bản class/resource theo release Java |
| --create | Tạo archive mới |
| --list | Liệt kê entry trong archive |
| --update | Thêm hoặc thay thế entry |
| --extract | Giải nén entry |
| -C | Chọn thư mục làm việc cho các tệp tiếp theo |
| jarsigner | Công cụ ký và xác minh chữ ký JAR |
| keytool | Công cụ quản lý keystore và certificate |

Cần nhớ ba việc cốt lõi: **javac tạo class file, jar đóng gói class file và tài nguyên, còn java khởi chạy ứng dụng từ JAR nếu archive có cấu hình điểm vào phù hợp**. Kiểm tra entry, manifest, dependency và module descriptor trước khi phát hành giúp tránh phần lớn lỗi đóng gói và chạy ứng dụng Java.