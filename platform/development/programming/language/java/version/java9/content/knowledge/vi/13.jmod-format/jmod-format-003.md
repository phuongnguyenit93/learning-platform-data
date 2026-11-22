# Tạo, mô tả, liệt kê và giải nén JMOD bằng công cụ jmod

**jmod** là công cụ dòng lệnh đi kèm JDK để tạo và kiểm tra archive JMOD. JMOD đóng gói nội dung của một module Java thành các phần riêng: class, file cấu hình, native library, native command, header, legal notice và man page.

Bốn thao tác chính trong bài:

- **create:** tạo file .jmod từ nội dung module và các thư mục tài nguyên đi kèm.
- **describe:** đọc module descriptor và hiển thị thông tin module.
- **list:** liệt kê tên các entry đang có trong archive.
- **extract:** giải nén các entry ra một thư mục để kiểm tra hoặc xử lý.

JMOD đặc biệt hữu ích khi chuẩn bị module cho **jlink** để tạo custom runtime image. Nó không phải định dạng thay thế cho modular JAR dùng trực tiếp trên runtime module path.

## 1. JMOD là gì và dùng trong trường hợp nào?

Một modular JAR chủ yếu đóng gói class và resource Java. JMOD có thể chứa thêm những thành phần cần thiết khi liên kết một runtime image, chẳng hạn:

| Khu vực trong JMOD | Nội dung | Tùy chọn tạo tương ứng |
|---|---|---|
| classes/ | module-info.class, class Java và resource | --class-path |
| bin/ | Native command đi kèm module | --cmds |
| conf/ | File cấu hình | --config |
| include/ | Header file, thường phục vụ native integration | --header-files |
| legal/ | License và legal notice | --legal-notices |
| lib/ | Native library | --libs |
| man/ | Man page | --man-pages |

Các thư mục này là những section bên trong archive, không phải các package Java.

JMOD phù hợp khi:

- Đóng gói một module để đưa vào quy trình liên kết bằng jlink.
- Một module cần đi kèm native library, command hoặc cấu hình.
- Cần kiểm tra chính xác module descriptor và các file đã được đóng gói.
- Cần trích xuất archive để kiểm tra nội dung hoặc phục vụ quy trình build.

**Phân biệt JMOD và modular JAR:**

- Modular JAR có thể được đặt trên runtime module path để chạy ứng dụng Java.
- JMOD là định dạng phục vụ các công cụ JDK, đặc biệt là jlink. Lệnh java --module-path không nạp trực tiếp file .jmod.
- Nếu cần phân phối thư viện để ứng dụng khác dùng trực tiếp, modular JAR thường là định dạng phù hợp. Nếu cần cung cấp module cho quá trình tạo runtime image, JMOD có thể là lựa chọn phù hợp.

Không nên đổi đuôi một file JAR thành .jmod để giả lập JMOD. Hãy dùng đúng công cụ jmod create.

## 2. Kiểm tra phiên bản và cú pháp của jmod

jmod nằm trong thư mục bin của JDK. Cần dùng JDK có công cụ này, không chỉ cài JRE.

Kiểm tra phiên bản:

~~~bash
jmod --version
~~~

Xem các chế độ và tùy chọn đang được JDK hỗ trợ:

~~~bash
jmod --help
~~~

Các chế độ liên quan đến bài học:

~~~text
jmod create [OPTIONS] <jmod-file>
jmod describe <jmod-file>
jmod list <jmod-file>
jmod extract [--dir <directory>] <jmod-file>
~~~

Có thể xem trợ giúp bổ sung:

~~~bash
jmod --help-extra
~~~

Một số tùy chọn có thể khác nhau giữa các bản JDK. Khi build trên CI hoặc máy khác, hãy kiểm tra jmod --help của đúng JDK đang chạy.

## 3. Tạo JMOD bằng jmod create

### Chuẩn bị module

jmod create nhận nội dung class từ thư mục hoặc application JAR thông qua --class-path. Với module có tên, đầu vào cần chứa module descriptor đã biên dịch là module-info.class.

Ví dụ cấu trúc source:

~~~text
src/
└── com.acme.greeting/
    ├── module-info.java
    └── com/
        └── acme/
            └── greeting/
                └── Main.java
~~~

**Module descriptor — src/com.acme.greeting/module-info.java:**

~~~java
module com.acme.greeting {
    exports com.acme.greeting;
}
~~~

**Class chạy ứng dụng — src/com.acme.greeting/com/acme/greeting/Main.java:**

~~~java
package com.acme.greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JMOD");
    }
}
~~~

Biên dịch module:

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out, jmods | Out-Null
javac --module-source-path src -d out -m com.acme.greeting
~~~

**Bash:**

~~~bash
mkdir -p out jmods
javac --module-source-path src -d out -m com.acme.greeting
~~~

Sau khi biên dịch, thư mục out/com.acme.greeting chứa module-info.class và các class của module. Đây là đầu vào cho tùy chọn --class-path.

### Cú pháp tạo cơ bản

~~~bash
jmod create --class-path <module-output-directory> <module-name>.jmod
~~~

Ví dụ:

~~~bash
jmod create --class-path out/com.acme.greeting jmods/com.acme.greeting.jmod
~~~

Lệnh tạo archive jmods/com.acme.greeting.jmod từ nội dung đã biên dịch. Đường dẫn đầu ra là vị trí file JMOD; thư mục cha cần tồn tại trước khi chạy lệnh.

### Các tùy chọn thường dùng

| Tùy chọn | Tác dụng |
|---|---|
| --class-path <path> | Đưa class và resource của module vào section classes/; nhận application JAR hoặc thư mục chứa class |
| --cmds <path> | Đưa native command vào bin/ |
| --config <path> | Đưa file cấu hình vào conf/ |
| --header-files <path> | Đưa header file vào include/ |
| --legal-notices <path> | Đưa license/legal notice vào legal/ |
| --libs <path> | Đưa native library vào lib/ |
| --man-pages <path> | Đưa man page vào man/ |
| --module-version <version> | Ghi phiên bản module |
| --main-class <class-name> | Ghi main class của module |
| --target-platform <platform> | Ghi thông tin nền tảng đích |
| --compress zip-0 đến zip-9 | Chọn mức nén; mặc định là zip-6 |
| --date <date-time> | Đặt timestamp cho các entry theo định dạng ISO-8601 |

Ví dụ tạo archive với metadata trên một dòng lệnh:

~~~bash
jmod create --class-path out/com.acme.greeting --module-version 1.0.0 --main-class com.acme.greeting.Main --compress zip-6 --date 2026-01-01T00:00:00Z jmods/com.acme.greeting.jmod
~~~

PowerShell cũng có thể chạy nguyên lệnh một dòng như trên. Nếu muốn nối nhiều dòng trong PowerShell, dùng dấu backtick ở cuối dòng; Bash dùng dấu gạch chéo ngược:

**PowerShell:**

~~~powershell
jmod create `
  --class-path out/com.acme.greeting `
  --module-version 1.0.0 `
  --main-class com.acme.greeting.Main `
  --compress zip-6 `
  --date 2026-01-01T00:00:00Z `
  jmods/com.acme.greeting.jmod
~~~

**Bash:**

~~~bash
jmod create \
  --class-path out/com.acme.greeting \
  --module-version 1.0.0 \
  --main-class com.acme.greeting.Main \
  --compress zip-6 \
  --date 2026-01-01T00:00:00Z \
  jmods/com.acme.greeting.jmod
~~~

--date giúp kiểm soát timestamp của entry, hữu ích trong quy trình build cần kết quả ổn định hơn. Để build có thể tái lập, vẫn cần giữ ổn định nội dung đầu vào, JDK và các tùy chọn tạo archive.

Nếu module có native library hoặc native command, hãy chọn đúng nội dung cho nền tảng đích. Không đóng gói binary của Windows rồi kỳ vọng nó chạy trên Linux. --target-platform ghi metadata nền tảng; nó không tự biên dịch hay chuyển đổi native binary sang nền tảng khác.

## 4. Mô tả module bằng jmod describe

Sau khi tạo JMOD, dùng:

~~~bash
jmod describe jmods/com.acme.greeting.jmod
~~~

Với ví dụ đã đặt module version và main class, kết quả có dạng:

~~~text
com.acme.greeting@1.0.0
exports com.acme.greeting
requires java.base mandated
main-class com.acme.greeting.Main
~~~

Ý nghĩa:

- com.acme.greeting@1.0.0: tên module và phiên bản.
- exports com.acme.greeting: package được export theo module descriptor.
- requires java.base mandated: module phụ thuộc vào java.base; đây là dependency mặc định của module Java thông thường.
- main-class ...: main class được ghi trong metadata của JMOD.

Nếu archive được tạo với --target-platform, phần mô tả còn có thể hiển thị platform tương ứng.

jmod describe hữu ích khi cần xác nhận module name, version, exports, requires, main class hoặc target platform. Lệnh này mô tả module descriptor và metadata; nó không liệt kê toàn bộ tên file trong archive.

Nếu jmod describe báo lỗi module descriptor, hãy kiểm tra đầu vào của jmod create: thư mục class có đúng module-info.class hay không, descriptor có hợp lệ và có đúng module cần đóng gói hay không.

## 5. Liệt kê nội dung archive bằng jmod list

Dùng:

~~~bash
jmod list jmods/com.acme.greeting.jmod
~~~

Với ví dụ tối giản, kết quả:

~~~text
classes/module-info.class
classes/com/acme/greeting/Main.class
~~~

Tên entry có tiền tố section:

- classes/ chứa module descriptor, class và resource.
- bin/, conf/, include/, legal/, lib/, man/ lần lượt chứa các thành phần tương ứng nếu chúng được thêm khi tạo JMOD.

Ví dụ, nếu tạo JMOD với --libs native/ và --config config/, jmod list sẽ hiển thị các entry thuộc lib/ và conf/.

jmod list chỉ in tên entry. Nó không hiển thị nội dung bên trong từng file và cũng không ghi file ra ổ đĩa. Muốn xem nội dung, dùng jmod extract.

## 6. Giải nén archive bằng jmod extract

Cú pháp:

~~~bash
jmod extract --dir <output-directory> <jmod-file>
~~~

Ví dụ:

~~~bash
jmod extract --dir extracted jmods/com.acme.greeting.jmod
~~~

Sau khi chạy, thư mục extracted có cấu trúc:

~~~text
extracted/
└── classes/
    ├── module-info.class
    └── com/
        └── acme/
            └── greeting/
                └── Main.class
~~~

Nếu archive có native library, config hoặc legal notice, các section tương ứng cũng được tạo trong thư mục đích:

~~~text
extracted/
├── bin/
├── classes/
├── conf/
├── include/
├── legal/
├── lib/
└── man/
~~~

Chỉ những section có entry mới xuất hiện.

Sau khi giải nén, có thể kiểm tra file, so sánh với đầu vào hoặc đưa các file đã trích xuất vào một bước xử lý khác. jmod extract giải nén nội dung archive; nó không cài đặt module, không tự thêm module vào runtime image và không thay đổi module descriptor.

Nên chỉ định --dir rõ ràng để biết chính xác nơi file được ghi. Nếu thư mục đích đã có nội dung, kiểm tra trước khi giải nén để tránh trộn các file cũ và mới.

## 7. Ví dụ hoàn chỉnh: create → describe → list → extract → jlink

Thực hiện theo thứ tự từ thư mục dự án có cấu trúc src/com.acme.greeting như phần 3.

**Bước 1 — biên dịch module:**

~~~bash
javac --module-source-path src -d out -m com.acme.greeting
~~~

**Bước 2 — tạo thư mục JMOD và tạo archive:**

~~~bash
jmod create --class-path out/com.acme.greeting --module-version 1.0.0 --main-class com.acme.greeting.Main jmods/com.acme.greeting.jmod
~~~

**Bước 3 — xem thông tin module:**

~~~bash
jmod describe jmods/com.acme.greeting.jmod
~~~

**Bước 4 — xem danh sách entry:**

~~~bash
jmod list jmods/com.acme.greeting.jmod
~~~

**Bước 5 — giải nén để kiểm tra:**

~~~bash
jmod extract --dir extracted jmods/com.acme.greeting.jmod
~~~

**Bước 6 — liên kết JMOD vào runtime image:**

~~~bash
jlink --module-path jmods --add-modules com.acme.greeting --output image
~~~

**Bước 7 — chạy ứng dụng từ image đã tạo:**

PowerShell:

~~~powershell
& ./image/bin/java.exe -m com.acme.greeting/com.acme.greeting.Main
~~~

Bash:

~~~bash
./image/bin/java -m com.acme.greeting/com.acme.greeting.Main
~~~

Kết quả:

~~~text
Hello from JMOD
~~~

Ví dụ này đã được kiểm tra bằng OpenJDK 24: biên dịch thành công, tạo JMOD, đọc được thông tin module, liệt kê và giải nén được entry, sau đó jlink tạo runtime image và ứng dụng chạy thành công từ image.

## 8. Vì sao không chạy JMOD trực tiếp bằng java?

Không chạy như sau:

~~~bash
java --module-path jmods --add-modules com.acme.greeting -m com.acme.greeting/com.acme.greeting.Main
~~~

Thư mục jmods chứa file .jmod, không phải modular JAR hoặc exploded module dành cho runtime module path. Trên OpenJDK 24, phép thử này báo:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.acme.greeting not found
~~~

Cách dùng đúng:

- Dùng jmod để tạo, mô tả, liệt kê và giải nén archive.
- Dùng jlink để liên kết JMOD cùng các module phụ thuộc thành runtime image.
- Chạy ứng dụng bằng Java launcher bên trong runtime image.
- Nếu cần chạy module trực tiếp bằng java --module-path, dùng modular JAR hoặc thư mục exploded module.

Điểm này đặc biệt quan trọng khi thiết kế pipeline build: tạo được JMOD chưa có nghĩa ứng dụng có thể khởi chạy trực tiếp từ thư mục JMOD.

## 9. Lỗi thường gặp và cách xử lý

**Không tìm thấy lệnh jmod**

Kiểm tra đang dùng JDK và thư mục bin của JDK đã nằm trong PATH. Có thể gọi bằng đường dẫn đầy đủ tới jmod.exe trên Windows hoặc jmod trên Unix-like systems.

**Tạo JMOD báo lỗi module descriptor**

Đảm bảo đã biên dịch module và thư mục --class-path chứa module-info.class hợp lệ. Không đưa thư mục source src/ thay cho thư mục output đã biên dịch.

**Dùng sai thư mục cho --class-path**

Giá trị phải trỏ tới thư mục chứa trực tiếp module-info.class và cây package, hoặc application JAR phù hợp. Nếu trỏ vào thư mục cha out/, công cụ có thể không tìm thấy descriptor ở vị trí mong đợi.

**Nhầm --class-path với runtime classpath**

--class-path ở đây là đầu vào để đóng gói section classes/ của JMOD. Nó không làm JMOD trở thành file có thể chạy trực tiếp bằng java -cp hay java --module-path.

**jmod describe không hiển thị file cần tìm**

Lệnh này mô tả module descriptor. Dùng jmod list để xem tên entry, rồi jmod extract để lấy nội dung.

**Giải nén nhưng không thấy resource**

Kiểm tra resource đã được sao chép vào thư mục output của module trước khi chạy jmod create hay chưa. javac biên dịch source Java nhưng không tự sao chép mọi file tài nguyên tùy ý trong source tree.

**JMOD có native library nhưng không dùng được trên máy khác**

Kiểm tra kiến trúc và hệ điều hành của native binary. --target-platform ghi thông tin platform, không chuyển đổi binary. Cần chuẩn bị JMOD đúng nền tảng cho runtime image đích.

**Không tạo lại được archive có cùng timestamp**

Có thể dùng --date để đặt thời gian entry cố định. Đồng thời cần giữ ổn định JDK, file đầu vào và các tùy chọn nén/metadata trong pipeline.

## 10. Checklist sử dụng jmod

1. Xác nhận JDK đang dùng có lệnh jmod; kiểm tra jmod --version và jmod --help.
2. Biên dịch module trước và xác nhận module-info.class nằm ở gốc thư mục output.
3. Dùng jmod create --class-path để đóng gói class/resource; thêm các section bin, conf, include, legal, lib, man khi module thực sự cần.
4. Dùng --module-version, --main-class, --target-platform, --compress và --date khi phù hợp.
5. Chạy jmod describe để xác nhận module descriptor và metadata.
6. Chạy jmod list để xác nhận các entry cần thiết đã được đóng gói.
7. Dùng jmod extract --dir để kiểm tra nội dung thật khi cần.
8. Đưa JMOD vào jlink để tạo runtime image; không đặt file JMOD trực tiếp lên runtime module path của lệnh java.
9. Chạy ứng dụng từ runtime image và kiểm tra kết quả thực tế.

jmod create, describe, list và extract giải quyết bốn công việc khác nhau trong quy trình đóng gói module. Kiểm tra cả module descriptor lẫn danh sách entry trước khi đưa archive vào jlink giúp phát hiện sớm lỗi thiếu class, resource, metadata hoặc thành phần native.