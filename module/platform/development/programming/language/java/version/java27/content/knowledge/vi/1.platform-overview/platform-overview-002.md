# Đọc phiên bản JDK, số build và chính sách hỗ trợ của nhà phân phối

Khi kiểm tra một môi trường Java, chỉ biết máy đang chạy “Java 27” là chưa đủ. Cần xác định chính xác bản cập nhật, số build, nhà phân phối đã đóng gói JDK và thời hạn họ còn cung cấp bản vá. Các thông tin này giúp đối chiếu lỗi, chọn đúng bản tải về và lập kế hoạch cập nhật an toàn.

Bài viết dùng JDK 27 làm ví dụ và lấy ngày 27-11-2026 làm mốc tra cứu. Lịch phát hành và hỗ trợ có thể thay đổi; khi áp dụng cho hệ thống thật, hãy kiểm tra lại trang chính thức của nhà phân phối đang sử dụng.

## 1. Phân biệt phiên bản Java, bản phân phối và số build

Một bản cài đặt JDK có nhiều lớp thông tin:

- **Phiên bản nền tảng (feature release):** chẳng hạn Java 27. Đây là phiên bản Java SE mà JDK triển khai.
- **Bản phân phối (distribution):** bộ JDK do một nhà cung cấp xây dựng, kiểm thử và phát hành, ví dụ Oracle JDK hoặc Eclipse Temurin. Các bản phân phối có thể dựa trên cùng mã nguồn OpenJDK nhưng có lịch phát hành, cách đóng gói, hỗ trợ nền tảng và chính sách hỗ trợ riêng.
- **Phiên bản cập nhật:** cho biết JDK đã nhận những đợt sửa lỗi, cập nhật bảo mật và bản vá nào.
- **Số build:** nhận diện một lần build cụ thể của bộ JDK. Hai bản build có thể cùng số phiên bản nhưng khác số build.
- **Chính sách hỗ trợ:** xác định thời gian nhà phân phối tiếp tục phát hành cập nhật, loại hỗ trợ cung cấp và điều kiện để nhận hỗ trợ.

Vì vậy, hai máy cùng báo Java 27 chưa chắc đang chạy cùng một bản JDK. Khi ghi nhận môi trường, nên lưu cả tên nhà phân phối, chuỗi phiên bản đầy đủ và số build.

## 2. Kiểm tra JDK đang được dùng

Chạy các lệnh sau trong terminal:

```shell
java -version
javac -version
java -XshowSettings:properties -version
```

`java -version` hiển thị phiên bản của runtime mà lệnh `java` tìm thấy qua `PATH`. `javac -version` hiển thị phiên bản của trình biên dịch mà lệnh `javac` tìm thấy. Hai lệnh có thể trỏ đến hai bản cài đặt khác nhau nếu máy có nhiều JDK hoặc cấu hình `PATH` chưa đồng nhất.

Lệnh `java -XshowSettings:properties -version` in các system property của runtime. Tập trung vào những khóa sau:

| System property | Ý nghĩa khi kiểm tra môi trường |
| --- | --- |
| `java.version` | Chuỗi phiên bản của Java Runtime Environment đang chạy. Có thể chuyển thành `Runtime.Version` để đọc từng thành phần. |
| `java.version.date` | Ngày phiên bản runtime, theo định dạng `YYYY-MM-DD`. |
| `java.vendor` | Nhà cung cấp của Java Runtime Environment. |
| `java.vendor.version` | Phiên bản riêng do nhà cung cấp công bố; thuộc tính này có thể không được cung cấp. |
| `java.vm.vendor` | Nhà cung cấp của phần triển khai Java Virtual Machine. |
| `java.vm.name` | Tên phần triển khai JVM. |
| `java.vm.version` | Phiên bản phần triển khai JVM. |
| `java.specification.version` | Phiên bản feature của đặc tả Java mà runtime triển khai, ví dụ `27`. |
| `java.home` | Thư mục cài đặt runtime đang được tiến trình sử dụng. |

`java.vendor` và `java.vm.vendor` trả lời hai câu hỏi gần nhau nhưng không đồng nghĩa: một thuộc tính mô tả nhà cung cấp runtime, thuộc tính còn lại mô tả nhà cung cấp phần triển khai JVM. `java.vendor.version` là tùy chọn nên không nên coi việc thiếu thuộc tính này là lỗi.

Để biết terminal đang chọn tệp thực thi nào, có thể kiểm tra đường dẫn:

```powershell
# Windows PowerShell
Get-Command java -All
Get-Command javac -All
```

```shell
# Linux hoặc macOS
command -v java
command -v javac
```

IDE, Gradle, Maven, container hoặc dịch vụ đang chạy có thể được cấu hình dùng một JDK khác với terminal hiện tại. Khi điều tra một ứng dụng cụ thể, hãy kiểm tra phiên bản ngay trong tiến trình đó hoặc trong cấu hình runtime của công cụ khởi chạy; kết quả từ terminal chỉ xác nhận JDK mà terminal đang tìm thấy.

## 3. Đọc cấu trúc chuỗi phiên bản

Với JDK 10 trở lên, chuỗi phiên bản tuân theo cấu trúc:

```text
FEATURE.INTERIM.UPDATE.PATCH
```

| Thành phần | Cách hiểu |
| --- | --- |
| `FEATURE` | Bộ đếm feature release, tăng sau mỗi feature release. Java 27 có giá trị `27`. |
| `INTERIM` | Bộ đếm interim release. Trong mô hình phát hành sáu tháng hiện tại, giá trị này là `0`; thành phần được giữ lại cho khả năng sử dụng trong tương lai. |
| `UPDATE` | Bộ đếm update release, dành cho các bản cập nhật tương thích để sửa lỗ hổng bảo mật, hồi quy và lỗi. |
| `PATCH` | Bộ đếm emergency patch, dùng khi cần phát hành bản vá khẩn cấp cho vấn đề nghiêm trọng. |

Các thành phần bằng `0` ở cuối không được viết ra. Ví dụ, `27.0.1` đã thể hiện feature `27`, interim `0`, update `1`, patch `0`; không cần ghi thành `27.0.1.0`.

### Ví dụ: `27.0.1.1+4`

Oracle công bố chuỗi phiên bản đầy đủ `27.0.1.1+4` cho JDK 27.0.1.1 phát hành ngày 17-11-2026. Có thể đọc như sau:

| Phần | Giá trị | Ý nghĩa |
| --- | --- | --- |
| Feature | `27` | Dòng Java 27. |
| Interim | `0` | Không có interim release riêng trong chu kỳ hiện tại. |
| Update | `1` | Update release thứ nhất của dòng 27. |
| Patch | `1` | Thành phần emergency patch có giá trị 1. |
| Build | `4` sau dấu `+` | Số build của phiên bản được phát hành. |

Dấu `+` phân tách số build khỏi số phiên bản. Vì thế, `27.0.1.1` và `27.0.1.1+4` không phải hai feature release khác nhau: phần đầu là số phiên bản, còn `+4` nhận diện build. Số build tăng theo các build được promote và được đặt lại khi một thành phần của số phiên bản thay đổi.

Chuỗi phiên bản còn có thể chứa thông tin pre-release và thông tin build bổ sung. Ví dụ, hậu tố `-ea` biểu thị bản Early Access đang trong quá trình phát triển; không nên xem một bản có dấu hiệu pre-release là bản GA ổn định. Phần thông tin bổ sung do nhà triển khai cung cấp cũng có thể khác nhau giữa các bản phân phối.

Không nên tự tách chuỗi phiên bản bằng cách giả định mọi phần sau dấu chấm đều có cùng ý nghĩa. Java cung cấp API `Runtime.Version` để phân tích và so sánh phiên bản theo đúng quy tắc của nền tảng.

### Đọc phiên bản từ bên trong chương trình

`Runtime.version()` trả về phiên bản của runtime đang thực thi chương trình. Các phương thức `feature()`, `interim()`, `update()`, `patch()` và `build()` cho phép lấy từng thành phần:

```java
Runtime.Version version = Runtime.version();

System.out.println("Full version: " + version);
System.out.println("Feature: " + version.feature());
System.out.println("Interim: " + version.interim());
System.out.println("Update: " + version.update());
System.out.println("Patch: " + version.patch());
System.out.println("Build: " + version.build().orElse(-1));
System.out.println("Pre-release: " + version.pre().orElse("GA"));

System.out.println("Vendor: " + System.getProperty("java.vendor"));
System.out.println("Vendor version: "
        + System.getProperty("java.vendor.version", "not provided"));
System.out.println("VM vendor: " + System.getProperty("java.vm.vendor"));
System.out.println("VM version: " + System.getProperty("java.vm.version"));
System.out.println("Java home: " + System.getProperty("java.home"));
```

Giá trị `-1` ở ví dụ trên chỉ là giá trị thay thế để thể hiện rằng runtime không cung cấp số build. Trong chương trình thực tế, có thể xử lý trực tiếp `Optional<Integer>` do `build()` trả về.

Khi viết mã mới, dùng `feature()`, `interim()` và `update()` theo ý nghĩa hiện tại. Các phương thức `major()`, `minor()` và `security()` của `Runtime.Version` đã deprecated từ Java 10 vì tên cũ không còn mô tả đúng ý nghĩa các thành phần trong mô hình phát hành theo thời gian.

## 4. Xác định nhà phân phối và bản build

Không nên chỉ dựa vào dòng chữ `OpenJDK` hoặc số `27` để kết luận nguồn gốc của JDK. Hãy kết hợp các dấu hiệu:

1. Đọc `java.vendor`, `java.vendor.version`, `java.vm.vendor` và `java.vm.name` từ runtime.
2. Đọc toàn bộ chuỗi phiên bản và build từ `java -version` hoặc `Runtime.version()`.
3. Kiểm tra `java.home` để biết runtime đang chạy đến từ thư mục nào.
4. Đối chiếu với trang phát hành chính thức của nhà phân phối, bao gồm tên gói, hệ điều hành, kiến trúc CPU và checksum của tệp tải về khi cần xác minh nguồn cài đặt.

Các nhà phân phối có thể xây dựng từ cùng một dòng OpenJDK nhưng phát hành binary vào thời điểm khác nhau, bổ sung nhãn nhận diện riêng hoặc cung cấp build cho những hệ điều hành và kiến trúc khác nhau. Vì vậy, không mặc định số build của Oracle JDK sẽ giống số build của mọi bản phân phối khác, cũng không lấy một chuỗi phiên bản của nhà cung cấp này để kết luận trạng thái cập nhật của nhà cung cấp khác.

## 5. Đọc chính sách hỗ trợ của nhà phân phối

**LTS là cam kết hỗ trợ của nhà phân phối đối với một dòng phát hành, không phải lời bảo đảm rằng mọi JDK mang cùng số phiên bản đều có cùng thời hạn hỗ trợ.** Khi đọc roadmap, cần phân biệt ít nhất các khái niệm sau:

- **LTS (Long-Term Support):** dòng phát hành được nhà phân phối duy trì trong một khoảng thời gian dài hơn, thường có nhiều đợt cập nhật định kỳ.
- **Non-LTS:** dòng phát hành có thời gian duy trì ngắn hơn. Khi feature release mới xuất hiện, dòng non-LTS trước đó có thể nhanh chóng bị thay thế.
- **Community support:** người dùng báo lỗi qua cộng đồng hoặc dự án; việc xử lý thường theo quy trình phát triển và phát hành của dự án.
- **Commercial support:** hỗ trợ theo hợp đồng, có thể bao gồm SLA, tư vấn, bản vá hoặc backport theo điều kiện của nhà cung cấp dịch vụ.
- **End of Availability / End of Support Life:** mốc nhà phân phối ngừng cung cấp binary mới hoặc ngừng duy trì một dòng phát hành. Cần đọc định nghĩa của chính roadmap vì hai mốc này có thể không hoàn toàn giống nhau.

### Ví dụ chính sách tại ngày 27-11-2026

| Nhà phân phối | Trạng thái Java 27 | Thông tin hỗ trợ cần lưu ý |
| --- | --- | --- |
| Oracle | Java 27 là non-LTS. Oracle ghi GA tháng 09-2026 và Premier Support đến tháng 03-2027; roadmap không có Extended Support cho dòng này. Java 25 là LTS mới nhất của Oracle tại thời điểm tra cứu. | Các mốc Premier/Extended trong bảng Oracle áp dụng cho các bản Oracle JDK được hỗ trợ thương mại dành cho Oracle Customers. Oracle xem các bản non-LTS trước đó là đã bị thay thế khi feature release mới xuất hiện. Quyền sử dụng theo giấy phép và quyền nhận hỗ trợ thương mại cần được kiểm tra riêng. |
| Eclipse Adoptium (Eclipse Temurin) | Bảng phát hành hiện tại liệt kê Temurin 27 với bản mới nhất tháng 11-2026 là `jdk-27.0.1.1+4`, và dự kiến bản tiếp theo vào tháng 01-2027. Java 27 không được đánh dấu LTS trong bảng; Java 25 được đánh dấu LTS. | Adoptium cung cấp community support cho các binary phát hành; Eclipse không trực tiếp bán dịch vụ hỗ trợ thương mại. Người cần SLA có thể tìm nhà cung cấp thương mại trong danh sách Adoptium công bố. Adoptium cam kết hỗ trợ các dòng LTS ít nhất bốn năm. |

Hai dòng trong bảng minh họa vì sao cần đọc đúng roadmap của nhà cung cấp đang dùng. Mốc Premier Support của Oracle không tự động áp dụng cho Temurin; cam kết LTS của Adoptium cũng không tạo ra quyền hỗ trợ thương mại từ Oracle. Các ngày trong roadmap có thể được cập nhật, nên hãy mở lại nguồn chính thức trước khi đưa ra quyết định vận hành.

Giấy phép sử dụng, thời gian phát hành bản cập nhật công khai và quyền được hỗ trợ có SLA là những vấn đề riêng. Một bản JDK có thể được tải miễn phí nhưng điều đó không tự động có nghĩa nhà phân phối cung cấp hỗ trợ thương mại miễn phí cho hệ thống production.

### Cách đọc một roadmap

Khi đánh giá một dòng JDK cho hệ thống, hãy trả lời lần lượt:

1. Nhà phân phối có đánh dấu đúng dòng phiên bản này là LTS không?
2. Ngày GA, ngày phát hành bản cập nhật gần nhất và mốc kết thúc cập nhật là khi nào?
3. Nhà phân phối còn phát hành bản vá bảo mật cho dòng đó không? Lịch cập nhật là hàng tháng, hàng quý hay theo chu kỳ riêng?
4. Hỗ trợ là cộng đồng hay thương mại? Có SLA, thời gian phản hồi, bản vá backport và phạm vi nền tảng nào?
5. Điều kiện giấy phép và entitlement nào áp dụng cho cách sử dụng của tổ chức?
6. Các framework, thư viện, hệ điều hành, kiến trúc CPU và công cụ triển khai của hệ thống có hỗ trợ dòng JDK đó không?

Không suy ra thời hạn hỗ trợ chỉ từ chữ `LTS` hoặc từ số phiên bản. Hãy ghi nhận cả tên nhà phân phối, ngày tra cứu và liên kết roadmap để người vận hành có thể xác minh lại.

## 6. Đặt Java 27 vào đúng bối cảnh phát hành

Java sử dụng mô hình phát hành feature theo chu kỳ sáu tháng. JDK 27 phát hành GA ngày 15-09-2026. Tại mốc 27-11-2026, release notes của Oracle ghi nhận JDK 27.0.1.1 phát hành ngày 17-11-2026 với chuỗi đầy đủ `27.0.1.1+4`.

Theo roadmap Oracle cập nhật ngày 20-10-2026:

- Java 27 là non-LTS; Oracle Premier Support dự kiến kết thúc tháng 03-2027 và không có Extended Support trong bảng roadmap.
- Java 25 là LTS mới nhất của Oracle, với Premier Support đến tháng 09-2030 và Extended Support đến tháng 09-2033.
- Oracle dự kiến Java 29 là LTS tiếp theo vào tháng 09-2027; đây là kế hoạch được công bố tại thời điểm tra cứu và có thể thay đổi.

Điều này có nghĩa JDK 27 phù hợp khi dự án cần dùng feature release mới và chấp nhận chu kỳ nâng cấp ngắn. Với hệ thống cần thời gian duy trì dài, hãy xem xét dòng LTS mà nhà phân phối cam kết hỗ trợ, đồng thời kiểm tra tương thích của ứng dụng và hạ tầng trước khi chọn phiên bản.

## 7. Quy trình kiểm tra trước khi đưa JDK vào sử dụng

Một quy trình kiểm tra ngắn có thể áp dụng cho máy phát triển, máy chủ và container:

1. Chạy `java -version` và `javac -version` để xác nhận runtime và compiler.
2. Chạy `java -XshowSettings:properties -version` để ghi nhận vendor, vendor version, VM vendor, VM version, ngày phiên bản và `java.home`.
3. Xác nhận đường dẫn thực thi và cấu hình JDK của IDE, build tool, service hoặc container đang chạy ứng dụng.
4. So sánh chuỗi phiên bản đầy đủ và số build với security baseline/release notes của đúng nhà phân phối.
5. Đối chiếu dòng phát hành với roadmap hỗ trợ, giấy phép và phạm vi hỗ trợ thương mại cần thiết.
6. Ghi lại kết quả cùng ngày kiểm tra; đặt lịch rà soát lại trước mốc kết thúc hỗ trợ hoặc mỗi đợt cập nhật bảo mật.

Một bản ghi kiểm kê tối thiểu nên có dạng:

| Trường | Ví dụ |
| --- | --- |
| Feature release | `27` |
| Version đầy đủ | `27.0.1.1` |
| Build | `4` |
| Nhà phân phối | Giá trị thực đọc từ `java.vendor` |
| VM vendor | Giá trị thực đọc từ `java.vm.vendor` |
| Version date | Giá trị thực đọc từ `java.version.date` |
| Java home | Giá trị thực đọc từ `java.home` |
| LTS / non-LTS | Theo roadmap của nhà phân phối |
| Hỗ trợ đến | Ngày theo roadmap của đúng nhà phân phối |
| Nguồn xác minh | Liên kết release notes và support roadmap |

Khi có đủ các trường này, nhóm phát triển có thể xác định chính xác môi trường đang chạy, so sánh hai bản build, kiểm tra trạng thái bản vá và quyết định thời điểm nâng cấp dựa trên cam kết hỗ trợ thực tế.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html) — phiên bản và build JDK 27.0.1.1+4, ngày phát hành và security baseline.
- [Version-String Format for JDK 27](https://docs.oracle.com/en/java/javase/27/install/version-string-format.html) — ý nghĩa các thành phần feature, interim, update và patch.
- [Runtime.Version API (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Runtime.Version.html) — phân tích chuỗi phiên bản, build number và các phương thức hiện hành.
- [System class (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html#getProperties()) — định nghĩa các system property về phiên bản, nhà cung cấp và runtime.
- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) — phân loại LTS/non-LTS và thời hạn hỗ trợ của Oracle.
- [Eclipse Temurin Support](https://adoptium.net/support) — community support, commercial support và roadmap phát hành Temurin.
