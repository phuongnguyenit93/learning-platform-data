# Kiểm tra nội dung bằng jar --validate

## 1. Vai trò của jar --validate trong JAR đa phiên bản

JAR đa phiên bản (Multi-Release JAR, viết tắt MR-JAR) cho phép một JAR chứa lớp hoặc tài nguyên thay thế dành cho các phiên bản Java mới hơn, đồng thời vẫn giữ phần nội dung cơ sở để chạy trên các phiên bản cũ hơn.

Một MR-JAR thường có cấu trúc:

~~~text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 11/
│       │   └── com/acme/RuntimeInfo.class
│       └── 17/
│           └── com/acme/RuntimeInfo.class
└── com/
    └── acme/
        └── RuntimeInfo.class
~~~

Phần class ở thư mục gốc là phiên bản cơ sở. Các thư mục **META-INF/versions/11** và **META-INF/versions/17** chứa phiên bản thay thế dành cho Java 11 và Java 17.

Manifest của JAR phải khai báo:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Khi chạy trên Java 17, runtime chọn entry phù hợp cao nhất không vượt quá phiên bản runtime, tức bản trong **META-INF/versions/17** nếu entry đó tồn tại. Khi chạy trên Java 11, runtime chọn bản trong **META-INF/versions/11**; nếu không có, nó dùng bản ở thư mục gốc.

Trong quy trình phát hành, chỉ nhìn thấy các entry trong ZIP chưa đủ để kết luận JAR hợp lệ. Cần kiểm tra cấu trúc, manifest, module descriptor nếu có, và hành vi khi chạy trên những JDK mà thư viện hỗ trợ.

Tùy chọn **--validate** của công cụ **jar** cung cấp bước kiểm tra nội dung archive theo các quy tắc mà phiên bản JDK đang sử dụng hỗ trợ. Đây là một bước hữu ích trong quy trình kiểm tra JAR, đặc biệt khi đóng gói thư viện modular hoặc MR-JAR. Phạm vi kiểm tra cụ thể cần đối chiếu với trợ giúp của đúng JDK; kết quả validate thành công không thay thế việc chạy thử trên từng phiên bản Java mục tiêu.

## 2. Cú pháp cơ bản

Cú pháp thường dùng:

~~~bash
jar --validate --file library.jar
~~~

Có thể viết ngắn hơn bằng các tùy chọn tương đương:

~~~bash
jar --validate -f library.jar
~~~

Trong đó:

- **jar** là công cụ đóng gói và kiểm tra JAR đi kèm JDK.
- **--validate** yêu cầu kiểm tra nội dung archive theo khả năng validate của công cụ hiện tại.
- **--file** hoặc **-f** chỉ định JAR cần kiểm tra.

Trước khi đưa lệnh vào CI, hãy xác định phiên bản công cụ:

~~~bash
jar --version
jar --help
~~~

Trên Windows PowerShell, có thể gọi công cụ từ JDK được chỉ định:

~~~powershell
& "$env:JAVA_HOME\bin\jar.exe" --version
& "$env:JAVA_HOME\bin\jar.exe" --help
& "$env:JAVA_HOME\bin\jar.exe" --validate --file .\build\library.jar
~~~

Hãy dùng công cụ jar cùng JDK mục tiêu của dự án. Nếu máy có nhiều JDK, lệnh jar tìm thấy qua PATH có thể khác với JDK mà ứng dụng sẽ chạy.

## 3. Những gì cần kiểm tra trong một MR-JAR

Một MR-JAR cần giữ đúng các quy tắc đóng gói để runtime chọn được phiên bản lớp hoặc resource mong muốn.

### 3.1. Manifest phải bật Multi-Release

Thuộc tính **Multi-Release: true** trong manifest đánh dấu JAR là đa phiên bản. Nếu thiếu thuộc tính này, các entry dưới **META-INF/versions/** không được xử lý như phiên bản thay thế theo cơ chế MR-JAR.

Kiểm tra manifest bằng:

~~~bash
jar --list --file library.jar
~~~

Có thể trích xuất manifest để xem nội dung:

~~~bash
jar --extract --file library.jar META-INF/MANIFEST.MF
~~~

Sau đó mở file **META-INF/MANIFEST.MF** và xác nhận có dòng:

~~~text
Multi-Release: true
~~~

Nếu sửa manifest, cần đóng gói lại JAR và chạy lại các bước kiểm tra. Không chỉnh trực tiếp một bản JAR đã phát hành rồi bỏ qua việc kiểm thử artifact cuối cùng.

### 3.2. Thư mục phiên bản phải có số phiên bản hợp lệ

Các entry phiên bản được đặt dưới:

~~~text
META-INF/versions/<N>/
~~~

Trong đó **N** là phiên bản Java mà entry bắt đầu có hiệu lực. Cơ chế MR-JAR bắt đầu từ Java 9, do đó các thư mục phiên bản cần tuân theo quy tắc phiên bản của MR-JAR.

Ví dụ:

- **META-INF/versions/9/** dành cho Java 9 trở lên.
- **META-INF/versions/11/** dành cho Java 11 trở lên.
- **META-INF/versions/17/** dành cho Java 17 trở lên.

Không đặt các entry thay thế tùy ý dưới một thư mục không tuân theo quy tắc phiên bản. Hãy kiểm tra đường dẫn thực tế bằng **jar --list --file**.

### 3.3. Entry thay thế phải tương thích với phần cơ sở

Một lớp thay thế cần giữ tên nhị phân và vai trò phù hợp với lớp cơ sở. Nếu phiên bản Java mới thay đổi chữ ký public hoặc hành vi theo cách consumer không dự đoán được, ứng dụng có thể biên dịch được nhưng gặp lỗi khi chạy trên một phiên bản khác.

Khi thiết kế MR-JAR:

- Giữ API public ổn định giữa các phiên bản nếu thư viện cần tương thích nguồn và nhị phân.
- Chỉ thay thế implementation khi có lý do kỹ thuật rõ ràng.
- Giữ các resource và cấu hình cần thiết ở đúng vị trí.
- Không giả định mọi entry trong thư mục phiên bản đều được chọn trên mọi JDK.
- Kiểm thử từng phiên bản Java được công bố hỗ trợ.

### 3.4. Nếu JAR là modular JAR

Một JAR có **module-info.class** là explicit modular JAR. Khi kết hợp với cấu trúc đa phiên bản, cần chú ý vị trí và tính nhất quán của module descriptor cũng như các package được đóng gói.

**jar --validate** có thể thực hiện các kiểm tra về tính hợp lệ và nhất quán của modular JAR mà phiên bản công cụ hỗ trợ. Hãy đọc thông báo của công cụ và kiểm tra thêm module descriptor bằng:

~~~bash
jar --describe-module --file library.jar
~~~

Không coi một JAR có thể mở như ZIP là bằng chứng rằng module descriptor hoặc ranh giới package của nó được thiết kế đúng.

## 4. Dùng jar --validate trong quy trình kiểm tra

Một quy trình thực tế nên kiểm tra artifact sau khi đã đóng gói xong:

1. Tạo JAR từ output đã biên dịch.
2. Kiểm tra danh sách entry bằng **jar --list**.
3. Xác nhận manifest có **Multi-Release: true** nếu đây là MR-JAR.
4. Dùng **jar --validate** để chạy các kiểm tra archive mà JDK hiện tại cung cấp.
5. Nếu JAR có module descriptor, xem module name và descriptor bằng **jar --describe-module**.
6. Chạy thử trên từng JDK mục tiêu để xác nhận runtime chọn đúng implementation.
7. Kiểm tra chữ ký nếu artifact được ký số.

Lệnh kiểm tra:

~~~bash
jar --validate --file build/library.jar
~~~

Không nên dựa vào một chuỗi stdout cố định vì nội dung thông báo có thể khác giữa các JDK. Trong script tự động, hãy kiểm tra exit code của tiến trình và lưu cả stdout/stderr để truy nguyên lỗi.

Ví dụ shell:

~~~bash
if jar --validate --file build/library.jar; then
    echo "JAR validation passed"
else
    echo "JAR validation failed" >&2
    exit 1
fi
~~~

Ví dụ PowerShell:

~~~powershell
& "$env:JAVA_HOME\bin\jar.exe" --validate --file ".\build\library.jar"

if ($LASTEXITCODE -ne 0) {
    throw "JAR validation failed"
}
~~~

Trong PowerShell, **$LASTEXITCODE** chứa exit code của chương trình native gần nhất. Kiểm tra ngay sau lệnh jar để không bị một lệnh khác ghi đè giá trị.

## 5. Ví dụ hoàn chỉnh: tạo và kiểm tra MR-JAR

Ví dụ sau tạo một thư viện có implementation cơ sở và implementation riêng cho Java 17. Chương trình consumer sẽ nhận implementation phù hợp với JDK đang chạy.

Cấu trúc dự án:

~~~text
project/
├── MANIFEST.MF
├── src/
│   ├── base/
│   │   └── com/acme/RuntimeInfo.java
│   ├── java17/
│   │   └── com/acme/RuntimeInfo.java
│   └── app/
│       └── com/acme/Main.java
└── build/
~~~

### 5.1. Viết implementation cơ sở

File **src/base/com/acme/RuntimeInfo.java**:

~~~java
package com.acme;

public final class RuntimeInfo {
    private RuntimeInfo() {
    }

    public static String message() {
        return "Base implementation";
    }
}
~~~

Implementation này được đóng gói ở thư mục gốc của JAR. Nó là phiên bản fallback cho các JDK không có entry thay thế phù hợp.

### 5.2. Viết implementation cho Java 17

File **src/java17/com/acme/RuntimeInfo.java**:

~~~java
package com.acme;

public final class RuntimeInfo {
    private RuntimeInfo() {
    }

    public static String message() {
        return "Java 17 implementation";
    }
}
~~~

Tên package, tên class và chữ ký phương thức public giống với bản cơ sở. Khi chạy trên Java 17 trở lên, runtime có thể chọn entry thay thế trong thư mục phiên bản 17.

### 5.3. Tạo manifest

File **MANIFEST.MF**:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Manifest cần có dòng trống kết thúc phần main attributes; hãy lưu file với newline cuối file để công cụ jar đọc đúng định dạng manifest.

### 5.4. Biên dịch hai phiên bản

Tại thư mục **project**, dùng JDK 17 trở lên:

~~~bash
mkdir -p build/base build/versions/17 build/app
javac --release 11 -d build/base src/base/com/acme/RuntimeInfo.java
javac --release 17 -d build/versions/17 src/java17/com/acme/RuntimeInfo.java
~~~

Lệnh đầu biên dịch implementation cơ sở tương thích Java 11. Lệnh thứ hai biên dịch implementation thay thế cho Java 17.

Trên Windows PowerShell có thể tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force build/base, build/versions/17, build/app
~~~

Sau đó chạy hai lệnh javac tương tự trong cùng thư mục dự án.

### 5.5. Đóng gói Multi-Release JAR

~~~bash
jar --create --file build/runtime-info.jar --manifest MANIFEST.MF -C build/base . --release 17 -C build/versions/17 .
~~~

Phần **-C build/base .** thêm implementation cơ sở vào gốc JAR. Phần **--release 17 -C build/versions/17 .** thêm implementation thay thế vào **META-INF/versions/17/**.

Kiểm tra cấu trúc:

~~~bash
jar --list --file build/runtime-info.jar
~~~

Trong danh sách cần có các entry tương ứng với:

~~~text
META-INF/MANIFEST.MF
com/acme/RuntimeInfo.class
META-INF/versions/17/com/acme/RuntimeInfo.class
~~~

### 5.6. Chạy validate và kiểm tra manifest

~~~bash
jar --validate --file build/runtime-info.jar
jar --extract --file build/runtime-info.jar META-INF/MANIFEST.MF
~~~

Mở manifest đã trích xuất và xác nhận **Multi-Release: true**. Nếu lệnh validate báo lỗi, cần xử lý lỗi trước khi phát hành artifact. Thông báo cụ thể và phạm vi kiểm tra phụ thuộc phiên bản JDK đang chạy công cụ.

### 5.7. Tạo consumer để kiểm tra lựa chọn phiên bản

File **src/app/com/acme/Main.java**:

~~~java
package com.acme;

public class Main {
    public static void main(String[] args) {
        System.out.println(RuntimeInfo.message());
    }
}
~~~

Biên dịch consumer tương thích Java 11:

~~~bash
javac --release 11 -cp build/runtime-info.jar -d build/app src/app/com/acme/Main.java
~~~

Chạy trên JDK 17:

~~~bash
java -cp "build/runtime-info.jar:build/app" com.acme.Main
~~~

Kết quả trên Linux hoặc macOS:

~~~text
Java 17 implementation
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
& "$env:JAVA_HOME\bin\java.exe" -cp "build\runtime-info.jar;build\app" com.acme.Main
~~~

Nếu chạy cùng artifact bằng JDK 11, runtime chọn implementation cơ sở và kết quả là:

~~~text
Base implementation
~~~

Ví dụ cho thấy validate chỉ là một bước trong quy trình. Kiểm thử trên từng JDK mục tiêu mới xác nhận được implementation mà runtime thực sự chọn.

## 6. Phân biệt các công cụ kiểm tra JAR

Mỗi công cụ kiểm tra một khía cạnh khác nhau:

| Công cụ | Mục đích |
|---|---|
| **jar --validate** | Chạy các kiểm tra nội dung và tính nhất quán mà jar tool hiện tại hỗ trợ. |
| **jar --list --file** | Liệt kê entry trong archive để kiểm tra cấu trúc và thư mục phiên bản. |
| **jar --describe-module --file** | Xem tên module và thông tin module descriptor nếu JAR có module metadata. |
| **jarsigner -verify** | Kiểm tra chữ ký số của JAR theo cấu hình và chứng thư liên quan. |
| **jdeps** | Phân tích dependency của class hoặc JAR. |
| **java / java -cp / java --module-path** | Chạy ứng dụng hoặc module để kiểm tra hành vi thực tế trên runtime. |

Một lệnh validate thành công không chứng minh chữ ký số hợp lệ, dependency đã đầy đủ, mọi class có thể nạp hoặc mọi implementation chạy đúng trên tất cả JDK. Hãy chọn công cụ theo câu hỏi cần trả lời và kết hợp các bước kiểm tra khi phát hành thư viện.

## 7. Kiểm thử MR-JAR trên nhiều phiên bản Java

Với thư viện hỗ trợ nhiều JDK, cần kiểm thử từng phiên bản tối thiểu và các phiên bản LTS mà dự án công bố hỗ trợ.

Ví dụ ma trận kiểm thử:

| JDK chạy | Implementation kỳ vọng trong ví dụ | Kết quả cần xác nhận |
|---|---|---|
| Java 11 | Bản ở thư mục gốc | In Base implementation. |
| Java 17 | Bản ở META-INF/versions/17 | In Java 17 implementation. |
| Java 21 | Bản ở META-INF/versions/17 | In Java 17 implementation nếu không có entry phiên bản 21. |

Đối với JDK mới hơn, runtime chọn entry phiên bản cao nhất không vượt quá phiên bản runtime. Nếu JAR có thêm thư mục phiên bản 21, Java 21 sẽ chọn bản đó.

Các kiểm thử nên bao gồm:

- Xác nhận manifest bật multi-release.
- Xác nhận entry cơ sở vẫn có mặt.
- Xác nhận entry phiên bản được đặt đúng thư mục.
- Xác nhận API public giữa các bản thay thế tương thích.
- Chạy consumer trên từng JDK hỗ trợ.
- Kiểm tra resource, reflection, serialization và service loading nếu thư viện sử dụng các tính năng đó.

Không nên chỉ chạy trên JDK mới nhất rồi kết luận JAR tương thích với các JDK cũ hơn.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| jar báo unrecognized option --validate | Lệnh jar không thuộc JDK dự kiến hoặc phiên bản công cụ không hỗ trợ tùy chọn. Kiểm tra jar --version và jar --help. |
| Entry META-INF/versions có trong JAR nhưng runtime không chọn | Manifest thiếu Multi-Release: true hoặc đường dẫn entry không đúng quy tắc. |
| JDK cũ không chạy được JAR | Class ở thư mục gốc được biên dịch bằng target quá mới. Biên dịch bản cơ sở bằng --release phù hợp với JDK thấp nhất hỗ trợ. |
| JDK mới vẫn chạy bản cơ sở | Entry thay thế không đúng tên đường dẫn, phiên bản không phù hợp hoặc manifest không bật multi-release. |
| Consumer gặp NoSuchMethodError trên một JDK | API giữa bản cơ sở và bản thay thế không tương thích. So sánh chữ ký public và chạy kiểm thử nhị phân. |
| Validate thành công nhưng ứng dụng vẫn lỗi | Validate không thực thi toàn bộ ứng dụng. Kiểm tra dependency, module path/classpath và chạy integration test trên JDK mục tiêu. |
| Manifest không được nhận diện | Manifest đặt sai vị trí, sai định dạng hoặc thiếu thuộc tính Multi-Release. Kiểm tra bằng jar --extract. |
| Lệnh trong CI chạy JDK khác máy phát triển | PATH hoặc JAVA_HOME khác nhau. Gọi java và jar từ cùng JDK được cố định trong pipeline. |
| Chữ ký số không còn hợp lệ sau khi sửa JAR | Thay đổi nội dung archive làm chữ ký cũ không còn khớp. Đóng gói và ký lại theo quy trình phát hành. |

## 9. Quy trình đưa kiểm tra vào CI

Một pipeline đơn giản có thể thực hiện các bước:

1. Biên dịch bản cơ sở bằng **--release** của JDK thấp nhất được hỗ trợ.
2. Biên dịch từng implementation thay thế bằng release tương ứng.
3. Tạo JAR với manifest **Multi-Release: true**.
4. Liệt kê entry và xác nhận cấu trúc **META-INF/versions**.
5. Chạy **jar --validate** bằng JDK đã được cố định.
6. Kiểm tra module descriptor nếu artifact là modular JAR.
7. Chạy test trên ma trận JDK hỗ trợ.
8. Ký artifact sau khi hoàn tất các bước thay đổi nội dung.
9. Lưu artifact và log kiểm tra cùng thông tin phiên bản JDK.

Ví dụ script Bash:

~~~bash
set -euo pipefail

JAR_FILE="build/runtime-info.jar"

jar --list --file "$JAR_FILE"
jar --validate --file "$JAR_FILE"

java -version
java -cp "$JAR_FILE:build/app" com.acme.Main
~~~

Trong CI thực tế, nên chạy bước test riêng cho từng JDK trong ma trận. Nếu validate hoặc test thất bại, pipeline phải dừng trước khi publish artifact.

## 10. Checklist trước khi phát hành

- [ ] JAR có manifest với **Multi-Release: true**.
- [ ] Phần implementation cơ sở có mặt ở thư mục gốc.
- [ ] Các entry thay thế nằm dưới **META-INF/versions/<N>/** đúng quy tắc.
- [ ] Bản cơ sở được biên dịch tương thích với JDK thấp nhất được hỗ trợ.
- [ ] Các implementation thay thế giữ API tương thích theo cam kết của thư viện.
- [ ] Đã chạy **jar --validate --file** bằng đúng JDK của pipeline.
- [ ] Đã kiểm tra danh sách entry và manifest của artifact cuối cùng.
- [ ] Đã kiểm tra module descriptor nếu JAR là modular JAR.
- [ ] Đã chạy test trên từng JDK được công bố hỗ trợ.
- [ ] Đã kiểm tra chữ ký số sau khi hoàn tất đóng gói.
- [ ] Đã lưu phiên bản JDK và log kiểm tra để có thể tái lập kết quả.

## 11. Kết luận

**jar --validate** là một bước kiểm tra nội dung JAR theo các quy tắc mà phiên bản jar tool đang dùng hỗ trợ. Trong quy trình làm việc với MR-JAR, hãy dùng nó sau khi đóng gói, đồng thời kiểm tra manifest, cấu trúc **META-INF/versions**, module descriptor nếu có và kết quả chạy thực tế trên từng JDK mục tiêu.

Validate thành công là một tín hiệu tốt về tính nhất quán của archive theo phạm vi công cụ kiểm tra. Để phát hành an toàn, vẫn cần kiểm tra lựa chọn implementation, tương thích API, dependency và chữ ký bằng các công cụ và bài test tương ứng.