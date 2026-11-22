# Magic và version của Java class file

Mỗi class Java sau khi biên dịch được lưu dưới dạng **class file** có cấu trúc nhị phân theo đặc tả JVM. Ở đầu mỗi class file có một dấu nhận dạng cố định gọi là **magic number** `CAFEBABE`. Ngay sau đó là hai trường version: `minor_version` và `major_version`.

Hai trường version cho biết định dạng class file mà compiler đã tạo. JVM dùng chúng để quyết định class file có thuộc định dạng mà runtime hỗ trợ hay không. Nếu ứng dụng được biên dịch bằng JDK mới hơn runtime đang chạy, lỗi thường gặp là `UnsupportedClassVersionError`.

## 1. Magic number CAFEBABE

Bốn byte đầu tiên của một class file hợp lệ là:

~~~text
CA FE BA BE
~~~

Đây là giá trị hexadecimal của magic number `0xCAFEBABE`. Nó là dấu nhận dạng nhị phân của Java class file, không phải mã văn bản hay phiên bản Java.

Khi JVM hoặc công cụ phân tích đọc class file, magic number giúp nhận biết dữ liệu có đúng định dạng class file hay không. Nếu bốn byte đầu không khớp, tệp có thể không phải class file, bị hỏng, hoặc bạn đang đọc nhầm định dạng dữ liệu. Đổi phần mở rộng của một tệp thành .class không biến nội dung tệp đó thành class file hợp lệ.

Magic number không cho biết class được biên dịch bằng JDK của nhà cung cấp nào. Muốn biết phiên bản định dạng, cần đọc các trường minor và major ngay sau bốn byte magic.

## 2. Cấu trúc header và vị trí version

Phần đầu class file được tổ chức theo thứ tự:

| Offset byte | Kích thước | Trường | Ý nghĩa |
|---:|---:|---|---|
| 0–3 | 4 byte | `magic` | Magic number `0xCAFEBABE` |
| 4–5 | 2 byte | `minor_version` | Phiên bản phụ |
| 6–7 | 2 byte | `major_version` | Phiên bản chính |
| 8 trở đi | Thay đổi | `constant_pool_count` và constant pool | Bắt đầu phần cấu trúc tiếp theo |

Các giá trị nhiều byte được lưu theo thứ tự **big-endian**: byte có trọng số cao đứng trước. Vì vậy, hai byte `00 3D` biểu diễn số hexadecimal `0x003D`, tức số thập phân 61.

Sau header, class file còn có constant pool, access flags, tên class và superclass, danh sách interface, fields, methods và attributes. Version nằm trong header nên có thể kiểm tra mà chưa cần phân tích toàn bộ bytecode.

## 3. Major version ánh xạ tới phiên bản Java

Mỗi thế hệ Java SE có một major class-file version tương ứng. Các mốc thường gặp:

| Java SE | Major version | Hexadecimal |
|---:|---:|---:|
| 1.0.2–1.1 | 45 | `0x002D` |
| 1.2 | 46 | `0x002E` |
| 1.3 | 47 | `0x002F` |
| 1.4 | 48 | `0x0030` |
| 5 | 49 | `0x0031` |
| 6 | 50 | `0x0032` |
| 7 | 51 | `0x0033` |
| 8 | 52 | `0x0034` |
| 9 | 53 | `0x0035` |
| 10 | 54 | `0x0036` |
| 11 | 55 | `0x0037` |
| 12 | 56 | `0x0038` |
| 13 | 57 | `0x0039` |
| 14 | 58 | `0x003A` |
| 15 | 59 | `0x003B` |
| 16 | 60 | `0x003C` |
| 17 | 61 | `0x003D` |
| 18 | 62 | `0x003E` |
| 19 | 63 | `0x003F` |
| 20 | 64 | `0x0040` |
| 21 | 65 | `0x0041` |
| 22 | 66 | `0x0042` |
| 23 | 67 | `0x0043` |
| 24 | 68 | `0x0044` |
| 25 | 69 | `0x0045` |
| 26 | 70 | `0x0046` |

Từ Java 1.2 trở đi, major version tăng một đơn vị theo mỗi bản Java SE. Có thể tính nhanh cho các bản hiện đại: `major = Java feature version + 44`. Ví dụ Java 17 có major 61; Java 21 có major 65; Java 26 có major 70.

Với các class file rất cũ thuộc major 45, minor version có thể mang giá trị lịch sử khác 0. Không nên áp dụng quy tắc minor bằng 0 cho mọi định dạng class file trong lịch sử.

## 4. Minor version và preview feature

Với class file Java hiện đại không dùng preview feature, minor version thường là `0`. Ví dụ class file Java 17 thông thường có version `61.0`.

Từ cơ chế preview feature được giới thiệu trong Java 12, class file được biên dịch có sử dụng preview feature mang minor version `65535` (hexadecimal `0xFFFF`). Giá trị này báo rằng class file phụ thuộc preview feature của đúng bản Java đó.

Để biên dịch và chạy mã dùng preview feature, phải bật preview ở cả hai bước và dùng cùng bản Java tương ứng. Ví dụ với JDK 21:

~~~sh
javac --release 21 --enable-preview -d out src/com/example/PreviewExample.java
java --enable-preview -cp out com.example.PreviewExample
~~~

Class file preview của Java 21 có major version 65 và minor version 65535. JVM Java 21 cần được khởi chạy với `--enable-preview` để nạp class đó. JVM của bản Java khác không thể dùng class file preview ấy như class file thông thường, kể cả khi major version có thể tương thích về mặt định dạng.

`--enable-preview` phải đi cùng `--release` hoặc `-source` được đặt ở phiên bản hiện tại của compiler. Không thể dùng compiler JDK 26 để tạo class file preview của Java 21 bằng cách đặt `--release 21 --enable-preview`; preview chỉ áp dụng cho bản phát hành của chính compiler đó.

## 5. Ví dụ kiểm tra version bằng javac và javap

Tạo file `src/com/example/VersionInfo.java`:

~~~java
package com.example;

public class VersionInfo {
    public static void main(String[] args) {
        System.out.println("class-file-check");
    }
}
~~~

Biên dịch để nhắm tới Java 17:

~~~sh
mkdir -p out
javac --release 17 -d out src/com/example/VersionInfo.java
~~~

Chạy bằng Java 17 hoặc runtime mới hơn:

~~~sh
java -cp out com.example.VersionInfo
~~~

Kết quả stdout:

~~~text
class-file-check
~~~

Dùng `javap -verbose` để xem thông tin version của class file:

~~~sh
javap -verbose -classpath out com.example.VersionInfo
~~~

Trong phần đầu kết quả, tìm hai dòng tương tự:

~~~text
minor version: 0
major version: 61
~~~

Vì compiler dùng `--release 17`, class file thông thường có major 61 và minor 0. Kết quả này phản ánh version của class file thực tế, không chỉ phiên bản của lệnh `javac` đang được cài.

Có thể dùng `javap -verbose` với class name đầy đủ hoặc truyền đường dẫn tới class file. Khi có nhiều class cùng tên trong các thư mục hoặc JAR khác nhau, hãy chỉ định đúng classpath để không kiểm tra nhầm bản.

## 6. Đọc tám byte đầu bằng công cụ hex

Trên Linux hoặc macOS, nếu đã có tiện ích `xxd`, có thể đọc tám byte đầu:

~~~sh
xxd -g 1 -l 8 out/com/example/VersionInfo.class
~~~

Với class file Java 17 chuẩn, kết quả phần byte đầu là:

~~~text
ca fe ba be 00 00 00 3d
~~~

Diễn giải:

- `ca fe ba be`: magic number.
- `00 00`: minor version bằng 0.
- `00 3d`: major version bằng 61, tức Java 17.

Trên Windows PowerShell, có thể đọc byte trực tiếp mà không cần cài tiện ích hex:

~~~powershell
$bytes = [System.IO.File]::ReadAllBytes('out\com\example\VersionInfo.class')
$bytes[0..7] | ForEach-Object { $_.ToString('X2') }
~~~

Tám giá trị in ra lần lượt phải là `CA FE BA BE 00 00 00 3D` đối với class file Java 17 thông thường. Nếu khác, hãy kiểm tra lại đường dẫn file, compiler target và việc có đang đọc đúng artifact hay không.

Đọc hex hữu ích khi cần xác minh file trực tiếp, ví dụ trong script build, pipeline kiểm tra artifact hoặc khi `javap` không có sẵn. Tuy vậy, `javap -verbose` thường dễ đọc hơn vì nó diễn giải trường version thay cho việc yêu cầu người đọc tự đổi số hexadecimal.

## 7. Vì sao class file version không nhất thiết bằng phiên bản JDK đang cài?

JDK dùng để biên dịch có thể mới hơn runtime tối thiểu mà ứng dụng hỗ trợ. Ví dụ, JDK 26 có thể biên dịch source với target Java 17 bằng:

~~~sh
javac --release 17 -d out src/com/example/VersionInfo.java
~~~

Kết quả class file có major version 61 thay vì 70. Như vậy, phiên bản JDK chạy compiler và phiên bản class file đầu ra là hai khái niệm khác nhau.

`--release` được khuyến nghị khi cần tương thích một Java release cũ hơn. Nó đặt mức ngôn ngữ, target bytecode và tập API nền tảng tương ứng. Chỉ dùng `-source` và `-target` riêng lẻ không đảm bảo mã nguồn tránh gọi API chỉ xuất hiện ở JDK mới hơn.

Ví dụ, compiler mới có thể chấp nhận một API có từ Java 21 dù bạn chỉ đặt `-target 17`. Class file có major 61 nhưng khi chạy trên Java 17 vẫn có thể gặp lỗi thiếu method hoặc class. `--release 17` ngăn việc biên dịch tham chiếu API Java SE không có trong release 17.

Ngoài compiler command line, Gradle Java Toolchains, cấu hình Maven compiler plugin và IDE cũng có thể chọn JDK hoặc target release riêng. Khi version class file không như mong đợi, hãy kiểm tra cấu hình thực tế của tác vụ build đã tạo artifact.

## 8. Lỗi UnsupportedClassVersionError

Thông báo thường gặp:

~~~text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
(class file version 65.0), this version of the Java Runtime
only recognizes class file versions up to 61.0
~~~

Trong ví dụ này:

- `65.0` là class file Java 21.
- `61.0` là mức tối đa runtime Java 17 hỗ trợ.
- Runtime Java 17 không thể nạp class file Java 21 đó.

Cách xử lý tùy mục tiêu:

1. **Nâng runtime** lên Java 21 hoặc mới hơn nếu ứng dụng yêu cầu bytecode Java 21.
2. **Biên dịch lại** bằng `javac --release 17` nếu ứng dụng phải chạy trên Java 17 và source/dependency tương thích.
3. **Kiểm tra dependency** vì một thư viện JAR có thể được biên dịch bằng Java mới hơn dù class của ứng dụng chính vẫn nhắm tới Java cũ.
4. **Kiểm tra tiến trình thực tế** để bảo đảm script, container, service, IDE và CI đều dùng runtime đúng phiên bản.

Không phải lúc nào đổi `JAVA_HOME` cũng giải quyết được lỗi. Một ứng dụng có thể được khởi chạy bằng đường dẫn `java` khác với lệnh `java` trong terminal. Hãy kiểm tra đúng tiến trình chạy ứng dụng.

## 9. Phân biệt lỗi version và lỗi định dạng class file

| Lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `UnsupportedClassVersionError` | Major/minor version không được runtime hỗ trợ hoặc preview chưa được bật đúng cách | So sánh class-file version với runtime và kiểm tra preview flag |
| `ClassFormatError` | Class file sai cấu trúc, không hợp lệ hoặc có dữ liệu không được chấp nhận | Kiểm tra magic, kích thước, nguồn artifact và quá trình đóng gói |
| `NoClassDefFoundError` | JVM không tìm thấy class cần thiết khi nạp hoặc liên kết | Kiểm tra classpath/module path và dependency |
| `ClassNotFoundException` | Cơ chế nạp class được yêu cầu không tìm thấy tên class | Kiểm tra tên class, classloader và classpath |

`UnsupportedClassVersionError` là một dạng `ClassFormatError`, nhưng nguyên nhân cụ thể là version không được hỗ trợ. Không nên kết luận mọi lỗi nạp class đều do major version; cần đọc loại exception và thông tin chi tiết.

## 10. Quy trình kiểm tra class file version

Khi một class không chạy được trên môi trường đích, có thể làm theo quy trình:

1. Xác định đúng file .class hoặc JAR mà runtime đang nạp.
2. Dùng `javap -verbose` để đọc `minor version` và `major version`.
3. Nếu cần, đọc tám byte đầu để xác nhận magic và version ở dạng hex.
4. Đối chiếu major version với Java release mà runtime hỗ trợ.
5. Kiểm tra minor version; nếu là 65535, xác nhận class dùng preview feature và chạy với đúng Java release cùng `--enable-preview`.
6. Kiểm tra `java -version` của đúng tiến trình chạy ứng dụng.
7. Kiểm tra `javac -version`, `--release`, toolchain và compiler plugin của quá trình build.
8. Kiểm tra tất cả JAR dependency vì một dependency có thể yêu cầu Java cao hơn ứng dụng.
9. Build lại artifact với target phù hợp hoặc nâng runtime theo yêu cầu.

Nếu dùng Gradle, kiểm tra JVM chạy Gradle và toolchain biên dịch; hai cấu hình này có thể khác nhau. Nếu dùng Maven, kiểm tra JDK của Maven và cấu hình compiler plugin. Với ứng dụng đóng gói trong container, kiểm tra cả image runtime vì nó quyết định JVM thực tế.

## 11. Checklist

- [ ] Bốn byte đầu của class file là `CA FE BA BE`.
- [ ] Đọc đúng minor version tại byte 4–5 và major version tại byte 6–7.
- [ ] Đối chiếu major version với Java release mục tiêu.
- [ ] Hiểu minor version 65535 là dấu hiệu class file dùng preview feature.
- [ ] Dùng `javap -verbose` để kiểm tra artifact.
- [ ] Dùng `--release` để biên dịch tương thích release cũ khi cần.
- [ ] Kiểm tra dependency và class file trong JAR.
- [ ] Xác minh đúng runtime được dùng để khởi chạy ứng dụng.
- [ ] Chỉ bật `--enable-preview` khi class file preview yêu cầu và đúng release hỗ trợ.

Magic number `CAFEBABE` xác nhận dấu nhận dạng class file; major version cho biết thế hệ định dạng; minor version bổ sung thông tin phiên bản phụ và trạng thái preview. Khi đọc đúng ba phần này, bạn có thể xác định nhanh một class file được tạo cho Java nào và tìm đúng nguyên nhân khi runtime từ chối nạp nó.