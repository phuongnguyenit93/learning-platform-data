# Liệt kê JAR bằng công cụ jar

## 1. Liệt kê JAR là gì?

JAR (Java ARchive) là định dạng đóng gói dựa trên ZIP, thường dùng để phân phối class file, tài nguyên và metadata của ứng dụng hoặc thư viện Java. Một JAR có thể chứa:

- Các tệp bytecode `.class`.
- Tài nguyên như `.properties`, ảnh, tệp XML, JSON hoặc văn bản.
- Thư mục package tương ứng với cấu trúc class.
- Manifest tại `META-INF/MANIFEST.MF`.
- Chữ ký và metadata phục vụ việc ký gói.
- Các JAR lồng bên trong một JAR khác, tùy cách đóng gói ứng dụng.

**Liệt kê JAR** là thao tác hiển thị danh sách entry (tệp và thư mục) đang được lưu trong một archive. Thao tác này giúp xác nhận gói có chứa class, resource, manifest hoặc thư viện dự kiến hay không.

Công cụ `jar` đi kèm JDK hỗ trợ thao tác này trực tiếp từ Terminal hoặc Command Prompt. Lệnh liệt kê chỉ đọc tên và thông tin entry; nó không giải nén toàn bộ archive và không chạy ứng dụng.

## 2. Cú pháp cơ bản của jar --list

Dùng cú pháp hiện đại:

```bash
jar --list --file app.jar
```

Trong đó:

- `jar` gọi công cụ quản lý Java Archive của JDK.
- `--list` yêu cầu hiển thị danh sách entry trong archive.
- `--file app.jar` chỉ định tệp JAR cần đọc.

Hai tùy chọn này có dạng viết tắt tương ứng:

```bash
jar -tf app.jar
```

Ở đây, `-t` là list và `-f` là file. Đây là cú pháp ngắn thường gặp trong tài liệu và script cũ.

Có thể xem hướng dẫn của phiên bản JDK đang cài:

```bash
jar --help
```

Các tùy chọn có thể được bổ sung theo phiên bản JDK. Khi làm việc trên nhiều máy hoặc nhiều bản JDK, hãy kiểm tra help của môi trường thực tế.

## 3. JAR chứa những entry nào?

Ví dụ một JAR ứng dụng có thể có cấu trúc:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── example/
│       ├── Main.class
│       └── service/
│           └── UserService.class
└── config/
    └── app.properties
```

Các entry có ý nghĩa:

- `META-INF/MANIFEST.MF`: metadata của archive, có thể khai báo `Main-Class`, phiên bản manifest, thông tin package hoặc metadata khác.
- `com/example/Main.class`: bytecode của class `com.example.Main`.
- `com/example/service/UserService.class`: bytecode của class thuộc package con.
- `config/app.properties`: tài nguyên được ứng dụng đọc khi chạy.

Tên entry bên trong JAR thường dùng dấu gạch chéo xuôi `/` làm dấu phân cách thư mục, kể cả khi JAR được tạo hoặc sử dụng trên Windows.

Một archive cũng có thể chứa entry thư mục riêng như `com/` và `com/example/`. Vì vậy, danh sách có thể hiển thị cả thư mục lẫn tệp. Không phải mọi công cụ đóng gói đều lưu entry thư mục theo cùng một cách.

## 4. Ví dụ thực hành: tạo và liệt kê một JAR

Ví dụ dùng Java 17 trở lên. Tạo tệp `src/com/example/Hello.java`:

```java
package com.example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, JAR!");
    }
}
```

Tạo thư mục đầu ra. Trên Linux/macOS:

```bash
mkdir -p out
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
```

Biên dịch từ thư mục gốc dự án:

```bash
javac --release 17 -d out src/com/example/Hello.java
```

Lệnh này tạo class file tại `out/com/example/Hello.class`.

Tạo JAR có khai báo lớp chính trong manifest:

```bash
jar --create --file app.jar --main-class com.example.Hello -C out .
```

Ý nghĩa:

- `--create`: tạo archive mới.
- `--file app.jar`: đặt tên archive đầu ra.
- `--main-class com.example.Hello`: khai báo lớp chính trong manifest.
- `-C out .`: chuyển vào thư mục `out` trước khi thêm toàn bộ nội dung của thư mục đó vào JAR.

Bây giờ liệt kê nội dung:

```bash
jar --list --file app.jar
```

Đầu ra đại diện có thể gồm:

```text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Hello.class
```

Thứ tự entry và việc hiển thị entry thư mục có thể khác tùy cách archive được tạo. Điểm cần xác nhận là JAR có `META-INF/MANIFEST.MF` và class `com/example/Hello.class`.

Có thể chạy JAR để kiểm tra lớp chính:

```bash
java -jar app.jar
```

Stdout:

```text
Hello, JAR!
```

Lệnh liệt kê xác nhận nội dung archive; lệnh chạy xác nhận JVM có thể khởi chạy ứng dụng theo manifest và runtime hiện tại.

## 5. Liệt kê với thông tin chi tiết bằng --verbose

Nếu chỉ dùng `--list`, kết quả chủ yếu là tên entry. Thêm `--verbose` để xem thêm thông tin:

```bash
jar --list --verbose --file app.jar
```

Dạng viết tắt:

```bash
jar -tvf app.jar
```

Chế độ verbose thường hiển thị:

- Kích thước entry.
- Ngày và thời gian được ghi trong archive.
- Tên entry.

Ví dụ đầu ra minh họa:

```text
     0 Thu Jan 01 00:00:00 UTC 1970 META-INF/
    55 Thu Jan 01 00:00:00 UTC 1970 META-INF/MANIFEST.MF
     0 Thu Jan 01 00:00:00 UTC 1970 com/
     0 Thu Jan 01 00:00:00 UTC 1970 com/example/
   425 Thu Jan 01 00:00:00 UTC 1970 com/example/Hello.class
```

Kích thước và thời gian ở trên chỉ là ví dụ định dạng, không phải giá trị cố định. Chúng phụ thuộc nội dung và thời điểm archive được tạo.

Verbose listing hữu ích khi:

- Muốn kiểm tra một resource có thực sự được đóng gói hay không.
- So sánh kích thước class hoặc resource giữa hai artifact.
- Tìm entry rỗng hoặc tệp có kích thước bất thường.
- Kiểm tra thời gian entry khi điều tra quá trình đóng gói.

Kích thước entry không nhất thiết bằng dung lượng JAR trên đĩa vì ZIP có thể nén dữ liệu và còn có metadata của archive.

## 6. Liệt kê JAR trong thư mục khác hoặc thư viện dependency

Nếu JAR không nằm trong thư mục hiện tại, truyền đường dẫn đến archive:

```bash
jar --list --file build/libs/application.jar
```

Trên Windows PowerShell:

```powershell
jar --list --file .\build\libs\application.jar
```

Để kiểm tra một thư viện dependency:

```bash
jar --list --file lib/commons-library.jar
```

`jar --list` đọc archive trực tiếp nên không cần thêm JAR vào classpath. Classpath chỉ cần khi chạy ứng dụng hoặc khi một công cụ cần phân giải class từ các vị trí khác nhau.

Khi có nhiều JAR, hãy kiểm tra đúng đường dẫn và tên artifact. Hai JAR có thể cùng chứa một class nhưng thuộc các phiên bản thư viện khác nhau.

## 7. Tìm nhanh một entry trong danh sách

`jar --list` không cung cấp cú pháp lọc nội dung theo mẫu như một truy vấn riêng. Có thể chuyển đầu ra qua công cụ lọc của shell.

Linux/macOS, tìm các entry thuộc package `com/example`:

```bash
jar --list --file app.jar | grep 'com/example'
```

Windows PowerShell:

```powershell
jar --list --file app.jar | Select-String 'com/example'
```

Windows Command Prompt:

```bat
jar --list --file app.jar | findstr "com/example"
```

Tìm các file cấu hình có đuôi `.properties` trên Linux/macOS:

```bash
jar --list --file app.jar | grep '\.properties$'
```

Các lệnh lọc trên chỉ xử lý văn bản được `jar` in ra. Chúng không sửa JAR và không xóa entry khỏi archive.

Nếu tên entry có ký tự đặc biệt hoặc cần phân tích chính xác hơn, có thể lưu danh sách vào tệp rồi dùng công cụ xử lý văn bản phù hợp.

## 8. Kiểm tra manifest trong JAR

Khi liệt kê một JAR có manifest, bạn thường thấy entry:

```text
META-INF/MANIFEST.MF
```

Tuy nhiên, `jar --list` chỉ hiển thị tên entry; nó không hiển thị nội dung manifest.

Manifest có thể chứa các thuộc tính như:

```text
Manifest-Version: 1.0
Main-Class: com.example.Hello
```

`Main-Class` cho biết lớp chính mà lệnh `java -jar app.jar` sẽ khởi chạy. Nếu JAR không có manifest hoặc thiếu `Main-Class` hợp lệ, lệnh `java -jar` có thể không chạy được theo cách này.

Nếu có tiện ích `unzip`, có thể đọc manifest mà không giải nén toàn bộ JAR:

```bash
unzip -p app.jar META-INF/MANIFEST.MF
```

Nếu không có `unzip`, có thể dùng `jar --extract --file app.jar META-INF/MANIFEST.MF` trong một thư mục làm việc riêng rồi mở tệp được trích xuất. Lệnh extract có tác dụng ghi tệp ra đĩa, khác với thao tác list chỉ đọc archive.

## 9. JAR có tài nguyên và thư mục package

Không phải mọi entry trong JAR đều là class file. JAR thường chứa resource để ứng dụng đọc trong runtime.

Ví dụ:

```text
app.jar
├── META-INF/MANIFEST.MF
├── com/example/Main.class
├── config/app.properties
├── messages/messages_vi.properties
└── images/logo.png
```

Khi liệt kê, hãy kiểm tra cả resource mà ứng dụng cần:

```bash
jar --list --file app.jar
```

Nếu `config/app.properties` không xuất hiện, có thể resource chưa được đưa vào thư mục đầu vào khi đóng gói hoặc cấu hình build đã loại bỏ nó.

Tên đường dẫn resource trong JAR thường được truy cập từ classpath bằng đường dẫn tương ứng, ví dụ `config/app.properties`. Việc entry có mặt trong archive chưa bảo đảm code đọc resource đã dùng đúng API hoặc đúng class loader.

## 10. Multi-release JAR và các entry theo phiên bản Java

Multi-release JAR cho phép một archive chứa các phiên bản class thay thế cho những runtime Java khác nhau. Các entry bổ sung thường nằm dưới:

```text
META-INF/versions/9/
META-INF/versions/11/
META-INF/versions/17/
```

Ví dụ:

```text
META-INF/MANIFEST.MF
com/example/Feature.class
META-INF/versions/11/com/example/Feature.class
META-INF/versions/17/com/example/Feature.class
```

Khi liệt kê JAR, các đường dẫn trong `META-INF/versions/` giúp nhận ra archive có chứa nội dung theo phiên bản Java.

Để JAR được xem là multi-release JAR, manifest phải khai báo thuộc tính:

```text
Multi-Release: true
```

Chỉ nhìn thấy thư mục `META-INF/versions/` chưa đủ để kết luận runtime sẽ chọn các entry thay thế. Cần kiểm tra cả manifest và cấu trúc archive.

`jar --list` hiển thị các entry đang được lưu trong archive; nó không tự giải thích class nào sẽ được runtime chọn cho một phiên bản Java cụ thể.

## 11. JAR lồng bên trong JAR

Một số ứng dụng đóng gói dependency thành các JAR nằm bên trong archive chính. Ví dụ cấu trúc của một ứng dụng Spring Boot có thể chứa:

```text
BOOT-INF/
├── classes/
│   └── com/example/Main.class
└── lib/
    ├── library-a.jar
    └── library-b.jar
```

Khi chạy:

```bash
jar --list --file application.jar
```

bạn sẽ thấy các entry như `BOOT-INF/lib/library-a.jar`. Công cụ `jar` chỉ liệt kê JAR bên trong như một entry của archive ngoài; nó không tự mở và liệt kê đệ quy các entry của JAR lồng.

Muốn kiểm tra dependency JAR lồng, cần trích xuất entry đó ra một thư mục riêng rồi chạy `jar --list` trên tệp được trích xuất. Với ứng dụng có cấu trúc đóng gói riêng, hãy xem tài liệu của framework hoặc plugin tạo archive để biết vị trí class và dependency.

## 12. Liệt kê JAR khác gì giải nén và phân tích class?

Các công cụ có mục đích khác nhau:

| Công cụ hoặc thao tác | Mục đích |
|---|---|
| `jar --list --file app.jar` | Xem tên entry trong archive |
| `jar --list --verbose --file app.jar` | Xem entry cùng kích thước và thời gian |
| `jar --extract --file app.jar` | Trích xuất nội dung archive ra thư mục |
| `javap -classpath app.jar com.example.Main` | Xem cấu trúc và chữ ký của một class |
| `javap -classpath app.jar -c com.example.Main` | Xem bytecode của method |
| `jdeps app.jar` | Phân tích dependency class và module |
| `jarsigner -verify app.jar` | Kiểm tra chữ ký JAR |

Liệt kê JAR phù hợp khi câu hỏi là “archive có chứa tệp nào?”. Nếu câu hỏi là “method được biên dịch ra sao?”, dùng `javap`. Nếu cần xác định dependency, dùng `jdeps`.

## 13. Kiểm tra chữ ký và tính toàn vẹn

Danh sách entry không chứng minh JAR đáng tin cậy hoặc chữ ký của nó hợp lệ. Một archive có thể liệt kê bình thường nhưng vẫn chứa nội dung không mong muốn.

Nếu JAR được ký, dùng `jarsigner` để kiểm tra chữ ký:

```bash
jarsigner -verify -verbose -certs app.jar
```

Đọc kết quả xác minh và cảnh báo chứng chỉ theo chính sách bảo mật của dự án. Việc xác minh chữ ký khác với việc chỉ xem tên entry.

Khi nhận JAR từ nguồn bên ngoài, nên kiểm tra nguồn phát hành, checksum hoặc chữ ký theo kênh chính thức. Không chạy một JAR chỉ vì lệnh `jar --list` có thể đọc được nội dung của nó.

## 14. Lỗi thường gặp khi liệt kê JAR

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jar` không được nhận diện | Chưa cài JDK hoặc PATH không chứa thư mục `bin` của JDK | Kiểm tra `JAVA_HOME`, PATH và `jar --help` |
| `java.nio.file.NoSuchFileException` | Sai đường dẫn hoặc tên file JAR | Kiểm tra thư mục hiện tại và đường dẫn archive |
| Không thấy class mong đợi | Đóng gói sai thư mục gốc hoặc class chưa được biên dịch | Kiểm tra output của compiler và lệnh tạo JAR |
| Không thấy manifest | Archive được tạo mà không có manifest | Kiểm tra cấu hình đóng gói hoặc tạo manifest phù hợp |
| `java -jar` không chạy dù JAR có class | Manifest thiếu hoặc khai báo sai `Main-Class` | Đọc nội dung manifest và kiểm tra tên class chính |
| Danh sách có JAR lồng nhưng không thấy class bên trong | `jar --list` không mở archive lồng đệ quy | Trích xuất JAR lồng rồi liệt kê riêng |
| Không thấy entry theo phiên bản Java | Archive không chứa versioned entry hoặc đang xem nhầm artifact | Kiểm tra `META-INF/versions/` và đúng file JAR |
| Verbose output quá dài | Archive chứa nhiều dependency và resource | Lọc output bằng `grep`, `Select-String` hoặc `findstr` |
| JAR đọc được nhưng ứng dụng vẫn lỗi | Listing không kiểm tra logic, dependency runtime hay chữ ký | Chạy test, dùng `jdeps`, `jarsigner` và kiểm tra log runtime |

Nếu `jar` báo lỗi archive không hợp lệ hoặc dữ liệu ZIP bị hỏng, hãy lấy lại artifact từ nguồn tin cậy và xác minh checksum. Không nên chỉnh sửa trực tiếp một archive hỏng rồi coi đó là bản build đáng tin cậy.

## 15. Quy trình kiểm tra JAR trong công việc

Khi nhận hoặc tạo một JAR, có thể thực hiện theo trình tự:

1. Xác định chính xác đường dẫn và phiên bản artifact cần kiểm tra.
2. Chạy `jar --list --file <file.jar>` để xem toàn bộ entry.
3. Kiểm tra manifest, class file và resource quan trọng có xuất hiện hay không.
4. Dùng `jar --list --verbose --file <file.jar>` nếu cần kích thước và thời gian entry.
5. Tìm các package hoặc resource cụ thể bằng công cụ lọc của shell.
6. Nếu thấy JAR lồng, trích xuất nó riêng và liệt kê lại.
7. Nếu thấy `META-INF/versions/`, kiểm tra manifest để xác định multi-release JAR.
8. Dùng `javap` để kiểm tra class cụ thể và `jdeps` để phân tích dependency khi cần.
9. Dùng `jarsigner -verify` nếu cần xác minh chữ ký.
10. Chạy test hoặc smoke test để xác nhận ứng dụng hoạt động trên runtime mục tiêu.

Quy trình này giúp phân biệt lỗi đóng gói với lỗi biên dịch, lỗi dependency hoặc lỗi runtime.

## 16. Tổng kết

`jar --list` là lệnh cơ bản để xem các entry bên trong một Java Archive mà không cần giải nén toàn bộ archive.

Những lệnh cần nhớ:

- `jar --list --file app.jar`: liệt kê tên entry.
- `jar -tf app.jar`: dạng viết tắt của thao tác list.
- `jar --list --verbose --file app.jar`: hiển thị thêm kích thước và thời gian.
- `jar --list --file path/to/app.jar`: liệt kê archive ở đường dẫn khác.
- `jar --list --file app.jar | grep ...`: lọc danh sách trên Linux/macOS.
- `jar --list --file app.jar | Select-String ...`: lọc danh sách trong PowerShell.
- `jar --list --file app.jar | findstr ...`: lọc danh sách trong Windows Command Prompt.

Liệt kê JAR giúp kiểm tra cấu trúc archive, manifest, class và resource. Khi cần xem bytecode, phân tích dependency, kiểm tra chữ ký hoặc chạy ứng dụng, hãy kết hợp các công cụ JDK tương ứng để xác minh đúng khía cạnh cần kiểm tra.
