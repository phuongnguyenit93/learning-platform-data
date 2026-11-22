# Giải nén JAR bằng công cụ jar

JAR (Java Archive) là định dạng archive dựa trên ZIP, thường dùng để đóng gói bytecode Java, tài nguyên, manifest và metadata của ứng dụng hoặc thư viện. Giải nén JAR là thao tác lấy các entry bên trong archive ra thành tệp và thư mục trên hệ thống tệp.

Công cụ `jar` đi kèm JDK hỗ trợ liệt kê, tạo, cập nhật và giải nén archive. Khi cần kiểm tra nội dung thư viện, lấy file cấu hình, khôi phục resource hoặc điều tra cấu trúc một artifact, có thể dùng `jar --extract` mà không cần viết chương trình giải nén riêng.

## 1. JAR chứa những gì?

Một JAR là một archive có cấu trúc entry. Mỗi entry có một tên đường dẫn tương đối bên trong archive và có thể là tệp hoặc thư mục. Ví dụ:

~~~text
customer-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── acme/
│       ├── app/
│       │   └── Main.class
│       └── model/
│           └── Customer.class
└── config/
    └── application.properties
~~~

Các loại nội dung thường gặp:

- **Class files:** bytecode Java có phần mở rộng `.class`.
- **Resources:** file cấu hình, template, ảnh, dữ liệu hoặc nội dung khác mà ứng dụng đọc lúc chạy.
- **Manifest:** file `META-INF/MANIFEST.MF`, có thể chứa thông tin phiên bản, lớp chính, class path hoặc thuộc tính của archive.
- **Service metadata:** các file trong `META-INF/services/` dùng với cơ chế service provider.
- **Module metadata:** chẳng hạn `module-info.class` trong JAR modular.
- **Signature metadata:** các file chữ ký trong `META-INF/` đối với artifact đã ký.

Giải nén chỉ lấy các entry ra thành tệp. Nó không dịch ngược bytecode thành mã nguồn Java, không cài thư viện vào JDK và không tự giải nén các JAR lồng bên trong archive.

## 2. Kiểm tra JAR trước khi giải nén

Trước khi lấy nội dung ra, nên xác nhận file archive tồn tại và xem danh sách entry:

~~~bash
jar --list --file customer-app.jar
~~~

Các tùy chọn tương đương dạng ngắn:

~~~bash
jar -tf customer-app.jar
~~~

Ý nghĩa:

- `--list` hoặc `-t`: liệt kê entry trong archive.
- `--file` hoặc `-f`: chỉ định file JAR.
- `-v`: hiển thị chi tiết hơn, bao gồm thông tin entry như kích thước và thời gian khi được hỗ trợ.

Có thể liệt kê ở chế độ verbose:

~~~bash
jar --list --verbose --file customer-app.jar
~~~

hoặc:

~~~bash
jar -tvf customer-app.jar
~~~

Tên entry thường dùng dấu gạch chéo xuôi `/` để phân tách thư mục, kể cả khi chạy trên Windows. Ví dụ entry `com/acme/app/Main.class` là tên cần truyền cho `jar` khi chỉ muốn trích xuất lớp đó.

Nếu archive lớn, việc liệt kê trước giúp xác định đúng entry cần lấy và tránh giải nén toàn bộ dữ liệu không cần thiết.

## 3. Cú pháp giải nén cơ bản

Cú pháp dạng dài:

~~~bash
jar --extract --file archive.jar
~~~

Cú pháp dạng ngắn:

~~~bash
jar -xf archive.jar
~~~

Trong đó:

- `--extract` hoặc `-x`: giải nén entry từ archive.
- `--file` hoặc `-f`: chỉ định archive cần đọc.
- Nếu không chỉ định thư mục đích, các entry được giải nén tương đối với thư mục làm việc hiện tại của terminal.

Ví dụ:

~~~bash
jar --extract --file customer-app.jar
~~~

Sau khi chạy, cấu trúc thư mục bên trong JAR được tạo tại thư mục hiện tại. Nếu archive có `com/acme/app/Main.class`, đường dẫn tương ứng sẽ được tạo bên dưới thư mục làm việc.

Dạng ngắn có thể kết hợp verbose để hiển thị các entry đang được xử lý:

~~~bash
jar -xvf customer-app.jar
~~~

Không nên giải nén archive vào một thư mục dự án đang chứa các file quan trọng nếu chưa biết nội dung của nó. Hãy liệt kê entry và chọn một thư mục đích riêng để dễ kiểm soát kết quả.

## 4. Giải nén vào thư mục đích bằng --dir

Để tách nội dung archive khỏi thư mục làm việc hiện tại, dùng tùy chọn `--dir`:

~~~bash
jar --extract --file customer-app.jar --dir extracted
~~~

Các entry được ghi vào thư mục `extracted`, đồng thời giữ lại cấu trúc thư mục tương đối trong JAR.

Ví dụ, nếu archive có:

~~~text
com/acme/app/Main.class
com/acme/model/Customer.class
config/application.properties
~~~

thì kết quả sẽ có dạng:

~~~text
extracted/
├── com/
│   └── acme/
│       ├── app/Main.class
│       └── model/Customer.class
└── config/
    └── application.properties
~~~

Trên Linux/macOS, có thể tạo thư mục đích trước:

~~~bash
mkdir -p extracted
jar --extract --file customer-app.jar --dir extracted
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force extracted | Out-Null
jar --extract --file customer-app.jar --dir extracted
~~~

Có thể dùng đường dẫn tuyệt đối cho `--dir` nếu script chạy từ nhiều working directory khác nhau. Với dự án chia sẻ trong nhóm, đường dẫn tương đối từ project root thường dễ tái lập hơn.

## 5. Chỉ giải nén một entry hoặc một nhóm entry

Không phải lúc nào cũng cần lấy toàn bộ archive. Có thể truyền tên entry cần trích xuất sau các tùy chọn:

~~~bash
jar --extract --file customer-app.jar --dir extracted com/acme/model/Customer.class
~~~

Lệnh trên chỉ lấy entry `com/acme/model/Customer.class` vào thư mục đích. Nếu cần lấy manifest:

~~~bash
jar --extract --file customer-app.jar --dir extracted META-INF/MANIFEST.MF
~~~

Có thể chỉ định nhiều entry trong cùng một lần gọi:

~~~bash
jar --extract --file customer-app.jar --dir extracted com/acme/app/Main.class com/acme/model/Customer.class config/application.properties
~~~

Trên PowerShell cũng có thể đặt các entry trên cùng một dòng:

~~~powershell
jar --extract --file customer-app.jar --dir extracted com/acme/app/Main.class com/acme/model/Customer.class config/application.properties
~~~

Tên entry phải khớp với đường dẫn được liệt kê trong archive. Hãy dùng dấu `/` trong tên entry thay vì tự đổi sang dấu `\` theo Windows. Nếu truyền tên không tồn tại, `jar` không thể trích xuất entry đó và sẽ báo lỗi hoặc không tìm thấy mục được yêu cầu tùy phiên bản.

Đối với một thư mục entry, kiểm tra danh sách archive để xác định các entry con. Không nên giả định rằng chỉ truyền tên thư mục sẽ luôn hoạt động giống nhau với mọi archive; cách chắc chắn là chỉ định các file entry cần lấy.

## 6. Ví dụ thực hành hoàn chỉnh: tạo, liệt kê và giải nén JAR

Ví dụ này tạo một ứng dụng Java nhỏ, đóng gói thành JAR thực thi, sau đó giải nén và chạy lại các lớp đã trích xuất.

Tạo cấu trúc nguồn:

~~~text
jar-extract-demo/
└── src/
    └── com/
        └── acme/
            ├── app/
            │   └── Main.java
            └── model/
                └── Customer.java
~~~

Tệp `src/com/acme/model/Customer.java`:

~~~java
package com.acme.model;

public class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

Tệp `src/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.model.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("Linh");
        System.out.println("Customer: " + customer.name());
    }
}
~~~

### Bước 1: Biên dịch mã nguồn

Từ thư mục gốc `jar-extract-demo`, tạo thư mục đầu ra và biên dịch:

~~~bash
mkdir -p out
javac -d out src/com/acme/model/Customer.java src/com/acme/app/Main.java
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out src/com/acme/model/Customer.java src/com/acme/app/Main.java
~~~

Sau khi biên dịch, các file class nằm dưới `out/com/acme/`.

### Bước 2: Tạo JAR

Đóng gói các lớp và khai báo lớp chính trong manifest:

~~~bash
jar --create --file customer-app.jar --main-class com.acme.app.Main -C out .
~~~

Tùy chọn `-C out .` yêu cầu jar chuyển vào thư mục `out` khi lấy nội dung để đóng gói; dấu chấm biểu thị toàn bộ nội dung bên trong thư mục đó. Nhờ vậy, JAR chứa đường dẫn package như `com/acme/app/Main.class`, không chứa thêm một thư mục gốc tên `out`.

### Bước 3: Kiểm tra danh sách entry

~~~bash
jar --list --file customer-app.jar
~~~

Trong archive sẽ có các entry tương ứng với `META-INF/MANIFEST.MF`, `com/acme/app/Main.class` và `com/acme/model/Customer.class`. Archive cũng có thể có entry thư mục như `com/` hoặc `META-INF/`.

### Bước 4: Chạy JAR trước khi giải nén

~~~bash
java -jar customer-app.jar
~~~

Output:

~~~text
Customer: Linh
~~~

### Bước 5: Giải nén vào thư mục riêng

~~~bash
mkdir -p extracted
jar --extract --file customer-app.jar --dir extracted
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force extracted | Out-Null
jar --extract --file customer-app.jar --dir extracted
~~~

Sau khi giải nén, cấu trúc chính:

~~~text
extracted/
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── acme/
        ├── app/Main.class
        └── model/Customer.class
~~~

### Bước 6: Xác minh nội dung đã giải nén

Trên Windows PowerShell, có thể xem manifest bằng:

~~~powershell
Get-Content extracted/META-INF/MANIFEST.MF
~~~

Trên Linux/macOS, dùng:

~~~bash
cat extracted/META-INF/MANIFEST.MF
~~~

Manifest có thuộc tính `Main-Class: com.acme.app.Main` vì JAR được tạo với tùy chọn `--main-class`.

Có thể chạy các lớp trực tiếp từ thư mục đã giải nén:

~~~bash
java -cp extracted com.acme.app.Main
~~~

Output:

~~~text
Customer: Linh
~~~

Kết quả giống khi chạy JAR. Điều này xác nhận các class entry đã được trích xuất đúng cấu trúc package và có thể được JVM nạp từ thư mục `extracted`.

## 7. Giải nén manifest và kiểm tra metadata

Manifest là file văn bản đặc biệt nằm ở:

~~~text
META-INF/MANIFEST.MF
~~~

Có thể trích xuất riêng:

~~~bash
jar --extract --file customer-app.jar --dir extracted META-INF/MANIFEST.MF
~~~

Các thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| Manifest-Version | Phiên bản định dạng manifest. |
| Main-Class | Lớp chính khi chạy bằng `java -jar`. |
| Class-Path | Các vị trí dependency được khai báo cho ứng dụng JAR theo quy tắc manifest. |
| Implementation-Title | Tên thành phần triển khai. |
| Implementation-Version | Phiên bản thành phần triển khai. |
| Specification-Version | Phiên bản đặc tả mà thành phần công bố. |

Tên thuộc tính trong manifest không phân biệt chữ hoa/thường theo quy tắc manifest. Giá trị có thể được ghi trên nhiều dòng theo quy tắc continuation của manifest, nên không nên tự phân tích bằng cách giả định mỗi thuộc tính luôn nằm trọn trên một dòng.

Việc giải nén manifest chỉ giúp đọc metadata. Nó không tự cài dependency hoặc sửa classpath. Nếu JAR khai báo `Class-Path`, các đường dẫn đó vẫn phải tồn tại và được phân giải theo quy tắc của ứng dụng khi chạy.

## 8. Giải nén resource và thư mục META-INF

JAR thường chứa resource mà ứng dụng đọc qua class loader. Ví dụ:

~~~text
config/application.properties
templates/email.html
META-INF/services/com.acme.spi.PaymentProvider
~~~

Có thể trích xuất một resource:

~~~bash
jar --extract --file customer-app.jar --dir extracted config/application.properties
~~~

Hoặc lấy service metadata:

~~~bash
jar --extract --file customer-app.jar --dir extracted META-INF/services/com.acme.spi.PaymentProvider
~~~

Các resource được giữ nguyên tên entry và cấu trúc thư mục. Khi kiểm tra nội dung, lưu ý encoding của file resource do chính ứng dụng hoặc định dạng quy định; thao tác giải nén không chuyển đổi encoding.

Một JAR có thể chứa file JAR khác như một entry, chẳng hạn `lib/dependency.jar`. Khi giải nén archive ngoài, file JAR lồng đó vẫn chỉ là một file. Muốn xem nội dung bên trong, phải chạy lệnh jar riêng trên file JAR đã được trích xuất.

## 9. Đường dẫn entry và working directory

Tên entry bên trong JAR là đường dẫn tương đối theo quy ước archive, không phải đường dẫn tuyệt đối trên máy. Ví dụ:

~~~text
com/acme/model/Customer.class
META-INF/MANIFEST.MF
config/app.properties
~~~

Một số điểm cần nhớ:

- Entry path dùng dấu `/` để phân tách thư mục trên mọi hệ điều hành.
- Không thêm ký tự ổ đĩa Windows như `C:\` vào tên entry.
- Không thêm dấu `/` đầu tên entry khi truyền đường dẫn tương đối.
- Đường dẫn tương đối của `--dir` được hiểu từ working directory hiện tại.
- Nếu không chỉ định `--dir`, nội dung được giải nén vào working directory.

Để tránh nhầm thư mục đích, hãy kiểm tra working directory trước khi chạy lệnh:

~~~bash
pwd
~~~

Trên PowerShell:

~~~powershell
Get-Location
~~~

Nếu script chạy từ nhiều vị trí, có thể dùng đường dẫn đích tuyệt đối hoặc tính đường dẫn từ thư mục gốc dự án.

## 10. Archive nhiều phiên bản và module

Một số JAR có cấu trúc multi-release, chứa các lớp thay thế theo phiên bản Java dưới `META-INF/versions/`. Khi liệt kê hoặc giải nén, hãy xem toàn bộ entry để hiểu archive thực sự chứa những phiên bản nào. Không nên nhầm một lớp dưới `META-INF/versions/17/` với lớp ở package root; chúng phục vụ cơ chế multi-release JAR và được JVM chọn theo phiên bản runtime.

JAR modular có thể chứa `module-info.class`. Khi giải nén, file này được trích xuất như một entry class bình thường. Có thể kiểm tra module descriptor của một JAR modular bằng:

~~~bash
jar --describe-module --file modular-library.jar
~~~

Nếu archive không có module descriptor tường minh, JDK có thể mô tả nó như automatic module dựa trên metadata và tên archive. Giải nén không làm thay đổi cách module được định danh hoặc tự động cấu hình module path cho ứng dụng.

## 11. JAR đã ký và việc sửa nội dung sau khi giải nén

JAR có thể chứa metadata chữ ký trong `META-INF/`, chẳng hạn file `.SF`, `.RSA`, `.DSA` hoặc `.EC`. Các file này liên quan tới chữ ký số của archive.

Giải nén chỉ đọc archive và tạo bản sao các entry trên hệ thống tệp. Nếu chỉnh sửa nội dung rồi đóng gói lại, chữ ký cũ không còn xác nhận nội dung archive mới. Không được xem việc giữ lại file chữ ký trong thư mục đã giải nén là bằng chứng rằng archive mới vẫn hợp lệ.

Có thể kiểm tra chữ ký của archive gốc bằng:

~~~bash
jarsigner -verify -verbose -certs customer-app.jar
~~~

Nếu cần phân phối lại archive sau khi thay đổi nội dung, hãy thực hiện quy trình ký lại bằng khóa được tổ chức cho phép và kiểm tra chữ ký mới theo chính sách phát hành.

## 12. An toàn khi giải nén archive

Trước khi giải nén JAR nhận từ nguồn không quen thuộc:

1. Liệt kê entry bằng `jar --list --file` để biết archive định tạo những đường dẫn nào.
2. Giải nén vào một thư mục riêng, mới tạo và không chứa dữ liệu quan trọng.
3. Kiểm tra tên entry, số lượng file và kích thước archive nếu nguồn không đáng tin cậy.
4. Không chạy ngay các file được trích xuất chỉ vì chúng nằm trong một JAR.
5. Không tự viết mã giải nén archive mà thiếu kiểm tra đường dẫn đầu ra và giới hạn tài nguyên.
6. Nếu cần chỉnh sửa hoặc tái đóng gói JAR đã ký, hãy xác định lại trạng thái chữ ký và quy trình phát hành.

Một archive có thể chứa rất nhiều entry hoặc các tệp lớn. Giải nén hàng loạt có thể tiêu tốn dung lượng đĩa đáng kể. Với archive không tin cậy, dùng thư mục tạm riêng và kiểm tra dung lượng trống trước khi trích xuất.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `NoSuchFileException` hoặc không mở được archive | Sai đường dẫn JAR hoặc terminal đang ở working directory khác. | Kiểm tra working directory và đường dẫn file; thử đường dẫn tuyệt đối. |
| `jar` không được nhận diện | JDK chưa có trong PATH hoặc đang dùng môi trường chỉ có runtime. | Kiểm tra `javap --version`, `javac -version` và PATH; cài/chọn JDK phù hợp. |
| Không tìm thấy entry cần lấy | Tên entry sai package path hoặc sai chữ hoa/thường. | Liệt kê archive và sao chép đúng tên entry, dùng dấu `/`. |
| File xuất hiện ở thư mục không mong muốn | Không chỉ định `--dir` hoặc hiểu nhầm working directory. | Dùng `--dir extracted` và kiểm tra `pwd`/`Get-Location`. |
| Thiếu lớp khi chạy các file đã giải nén | Chỉ trích xuất một phần JAR hoặc thiếu dependency bên ngoài. | Giải nén đủ entry cần thiết và cấu hình classpath/module path. |
| JAR lồng bên trong vẫn chưa được giải nén | jar chỉ trích xuất entry trực tiếp của archive đang mở. | Chạy jar riêng trên file JAR lồng đã trích xuất. |
| Chữ ký không còn hợp lệ sau khi sửa | Nội dung đã thay đổi nhưng metadata chữ ký cũ vẫn còn. | Ký lại archive mới bằng quy trình phát hành phù hợp. |
| Giải nén tạo ra nhiều file hơn dự kiến | Archive chứa resource, metadata, multi-release entry hoặc thư mục khác. | Xem danh sách trước và chỉ trích xuất entry cần thiết. |

Nếu cần kiểm tra cú pháp mà phiên bản JDK hiện tại hỗ trợ:

~~~bash
jar --help
~~~

Tùy chọn có thể khác giữa các đời JDK; dùng trợ giúp của chính công cụ đang chạy thay vì dựa vào ví dụ dành cho phiên bản khác.

## 14. Quy trình giải nén JAR khuyến nghị

Khi nhận một JAR cần kiểm tra hoặc trích xuất, thực hiện theo thứ tự:

1. Xác định đường dẫn archive và working directory.
2. Xem danh sách entry bằng `jar --list --file`.
3. Chọn giải nén toàn bộ hay chỉ một số entry.
4. Tạo thư mục đích riêng.
5. Dùng `jar --extract --file archive.jar --dir destination`.
6. Kiểm tra cấu trúc thư mục và các file quan trọng như manifest, class, resource.
7. Nếu cần chạy lớp đã trích xuất, dùng thư mục đích làm classpath và cung cấp dependency còn thiếu.
8. Nếu archive đã ký, xác minh chữ ký của file gốc và không tái sử dụng chữ ký cũ sau khi thay đổi nội dung.
9. Lưu lại lệnh và nguồn artifact nếu kết quả trích xuất được dùng trong điều tra hoặc quy trình build.

Giải nén JAR là thao tác đơn giản nhưng cần kiểm soát đường dẫn và cấu trúc entry. Nắm được `--list`, `--extract`, `--file`, `--dir` và cách chọn entry cụ thể giúp lấy đúng nội dung từ archive, kiểm tra artifact Java và điều tra vấn đề đóng gói một cách có hệ thống.
