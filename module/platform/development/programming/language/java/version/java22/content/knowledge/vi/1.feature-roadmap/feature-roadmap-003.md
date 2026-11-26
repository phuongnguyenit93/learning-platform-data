# Vai trò của Java 22 trong lịch sử phát triển và lựa chọn JDK còn được hỗ trợ

Java 22 là một cột mốc trong quá trình Java chuyển sang nhịp phát hành tính năng đều đặn sáu tháng. Bản phát hành này đưa nhiều cải tiến về ngôn ngữ, thư viện, công cụ và hiệu năng vào nền tảng; một số tính năng đã ổn định ngay trong Java 22, còn một số API preview tiếp tục được hoàn thiện ở Java 24 và Java 25.

Tuy nhiên, Java 22 là bản phát hành **non-LTS**. Ở thời điểm biên soạn, ngày 24 tháng 11 năm 2026, JDK 27 là bản phát hành tính năng mới nhất, còn JDK 25 là bản LTS mới nhất theo lộ trình của Oracle. Vì thế, giá trị của Java 22 hiện nay chủ yếu nằm ở việc hiểu lịch sử tiến hóa của nền tảng và nhận diện những tính năng đã trưởng thành; khi chọn JDK cho hệ thống mới, cần căn cứ vào phiên bản còn được nhà cung cấp hỗ trợ.

## 1. Java 22 nằm ở đâu trong lịch sử phát hành Java?

Java 22 được phát hành GA ngày 19 tháng 3 năm 2024, sau Java 21 và trước Java 23. Đây là một feature release trong chu kỳ phát hành sáu tháng. Mỗi feature release có thể bổ sung tính năng ngôn ngữ, API, cải tiến JVM hoặc công cụ; các bản cập nhật trong cùng dòng phiên bản tiếp tục sửa lỗi và lỗ hổng bảo mật.

Từ Java 9, cách đánh số phiên bản cũng thay đổi: số phiên bản đầu tiên là số feature release. Vì vậy, Java 22 là tên phiên bản nền tảng/JDK, còn một phiên bản như `25.0.5.1` biểu thị dòng tính năng 25 cùng các mức cập nhật và bản vá tương ứng.

| Phiên bản | Thời điểm GA | Vai trò trong chu kỳ |
| --- | --- | --- |
| Java 21 | Tháng 9 năm 2023 | LTS trước Java 22 |
| Java 22 | Tháng 3 năm 2024 | Feature release, non-LTS |
| Java 23 | Tháng 9 năm 2024 | Feature release, non-LTS |
| Java 24 | Tháng 3 năm 2025 | Feature release, non-LTS |
| Java 25 | Tháng 9 năm 2025 | LTS mới nhất theo lộ trình Oracle tại thời điểm biên soạn |
| Java 26 | Tháng 3 năm 2026 | Feature release, non-LTS |
| Java 27 | Tháng 9 năm 2026 | Feature release mới nhất tại thời điểm biên soạn, non-LTS |
| Java 28 | Dự kiến tháng 3 năm 2027 | Kế hoạch phát hành, có thể thay đổi |
| Java 29 | Dự kiến tháng 9 năm 2027 | LTS tiếp theo theo kế hoạch hiện tại của Oracle, có thể thay đổi |

Chu kỳ này giúp Java đưa cải tiến đến người phát triển thường xuyên. Nhóm phát triển có thể thử nghiệm tính năng mới ở các feature release, trong khi những dự án cần vòng đời ổn định có thể chọn một dòng LTS và nhận các bản cập nhật trong thời gian dài hơn theo cam kết của nhà cung cấp JDK.

## 2. Vai trò của Java 22 đối với sự tiến hóa của nền tảng

Java 22 không phải một phiên bản LTS để làm nền tảng triển khai lâu dài. Nó là một bước chuyển tiếp quan trọng: nhiều khả năng mới được giới thiệu hoặc tiếp tục thử nghiệm, sau đó được hoàn thiện ở những phiên bản tiếp theo.

Một số ví dụ tiêu biểu:

| Nội dung xuất hiện trong Java 22 | Diễn biến sau Java 22 | Ý nghĩa hiện nay |
| --- | --- | --- |
| Unnamed Variables & Patterns | Final ngay trong Java 22 | Cú pháp gọn hơn khi một biến hoặc thành phần pattern không được sử dụng |
| Foreign Function & Memory API | Final trong Java 22 | API chuẩn để Java gọi mã native và truy cập bộ nhớ ngoài heap |
| Launch Multi-File Source-Code Programs | Final trong Java 22 | Launcher chạy chương trình nguồn được tách thành nhiều file |
| Stream Gatherers | Preview trong Java 22, final trong Java 24 | Mở rộng Stream bằng các phép biến đổi trung gian có thể tùy chỉnh |
| Class-File API | Preview trong Java 22, final trong Java 24 | API chuẩn để đọc, tạo và biến đổi class file |
| Scoped Values | Preview trong Java 22, final trong Java 25 | Truyền dữ liệu ngữ cảnh bất biến theo phạm vi thực thi |
| Flexible Constructor Bodies | Preview trong Java 22, final trong Java 25 | Cho phép kiểm tra hoặc chuẩn hóa dữ liệu trước lời gọi constructor cha |
| Compact Source Files & Instance Main Methods | Preview trong Java 22, final trong Java 25 | Giảm cú pháp cần thiết cho chương trình Java nhỏ và bài học nhập môn |

Các ví dụ trên cho thấy hai điều cần phân biệt khi đọc tài liệu Java:

- Một tính năng được giới thiệu trong Java 22 không có nghĩa mọi phiên bản Java sau đó đều giữ nguyên trạng thái preview của nó. Một số tính năng đã trở thành API hoặc cú pháp final ở phiên bản mới hơn.
- Mã nguồn dùng preview API hoặc preview language feature phải được đánh giá theo đúng phiên bản JDK. Khi tính năng được hoàn thiện, chữ ký API, quy tắc sử dụng hoặc cách bật tính năng có thể khác so với bản preview ban đầu.

Vì vậy, học Java 22 vẫn hữu ích để hiểu quá trình hình thành tính năng và lý do các API hiện đại được thiết kế như hiện nay. Khi viết ứng dụng mới, nên dùng phiên bản final của tính năng trên một JDK còn được hỗ trợ, thay vì giữ ứng dụng ở JDK 22 chỉ vì tính năng được giới thiệu tại đó.

## 3. Feature release, update release và LTS khác nhau thế nào?

### 3.1. Feature release

Feature release là phiên bản nền tảng mới, ví dụ Java 22, 23, 24 hoặc 25. Một feature release có thể bổ sung hoặc thay đổi API, cú pháp ngôn ngữ, hành vi JVM và công cụ. Do đó, nâng cấp giữa hai feature release cần kiểm tra tương thích, dù Java luôn chú trọng duy trì khả năng tương thích.

### 3.2. Update release

Update release là bản cập nhật trong cùng dòng feature release, thường chứa bản sửa lỗi, cải thiện ổn định và bản vá bảo mật. Ví dụ `25.0.5` vẫn thuộc dòng Java 25. Khi vận hành production, cần theo dõi và cài đặt các bản cập nhật bảo mật phù hợp thay vì chỉ cài một bản JDK ban đầu rồi giữ nguyên trong thời gian dài.

Theo quy ước version string của Java, bốn thành phần đầu có ý nghĩa như sau:

| Thành phần | Ý nghĩa | Ví dụ trong `25.0.5.1` |
| --- | --- | --- |
| FEATURE | Dòng feature release | `25` |
| INTERIM | Bản phát hành trung gian tương thích | `0` |
| UPDATE | Mức cập nhật tương thích | `5` |
| PATCH | Bản vá khẩn cấp | `1` |

Không nên so sánh các bản JDK chỉ bằng tên nhà cung cấp hoặc chuỗi phiên bản rút gọn. Cần kiểm tra cả feature version, mức update, bản build và nguồn phân phối.

### 3.3. LTS — Long-Term Support

LTS là nhãn vòng đời hỗ trợ do nhà cung cấp JDK công bố cho một số dòng phát hành. Nhãn này giúp tổ chức lập kế hoạch vận hành dài hạn, nhưng không tự động bảo đảm mọi bản phân phối Java đều có cùng thời gian cập nhật, cùng mức hỗ trợ hoặc cùng điều khoản sử dụng.

OpenJDK cung cấp nền tảng và mã nguồn cho các bản phát hành Java; Oracle, Eclipse Adoptium, Amazon, Azul, Microsoft, Red Hat và các nhà cung cấp khác có thể phát hành các bản dựng JDK cùng chính sách cập nhật và hỗ trợ riêng. Vì vậy, khi nói một phiên bản Java còn được hỗ trợ, cần xác định rõ **bản phân phối nào**, **nhà cung cấp nào**, **hình thức hỗ trợ nào** và **thời điểm kết thúc hỗ trợ nào**.

## 4. Những dòng JDK nên cân nhắc ở thời điểm hiện tại

Bảng dưới đây dùng **lộ trình hỗ trợ thương mại Oracle Java SE** làm ví dụ cụ thể. Các mốc này không phải cam kết hỗ trợ chung cho mọi bản phân phối OpenJDK. Ngày kết thúc cũng có thể được điều chỉnh theo chính sách và hợp đồng của nhà cung cấp.

| JDK | Phân loại theo Oracle | Mốc hỗ trợ Oracle được công bố | Cách cân nhắc |
| --- | --- | --- | --- |
| 25 | LTS mới nhất | Premier Support đến tháng 9 năm 2030; Extended Support đến tháng 9 năm 2033 | Lựa chọn mặc định đáng cân nhắc cho dự án mới cần vòng đời dài |
| 21 | LTS | Premier Support đến tháng 9 năm 2028; Extended Support đến tháng 9 năm 2031 | Phù hợp khi framework hoặc hệ thống hiện tại cần thêm thời gian trước khi chuyển lên Java 25 |
| 17 | LTS | Premier Support kết thúc tháng 9 năm 2026; Extended Support đến tháng 9 năm 2029 | Chỉ nên tiếp tục cho hệ thống hiện hữu khi nhà cung cấp còn cam kết hỗ trợ; cần có kế hoạch nâng cấp |
| 27 | Non-LTS mới nhất | Premier Support đến tháng 3 năm 2027 theo roadmap Oracle hiện tại | Dùng khi cần thử nghiệm tính năng mới và đội ngũ chấp nhận nhịp nâng cấp ngắn |
| 22 | Non-LTS | Premier Support Oracle kết thúc tháng 9 năm 2024 | Không nên chọn làm nền tảng mới cho production ở thời điểm hiện tại |

Oracle công bố Java 25 là LTS mới nhất và dự kiến Java 29 sẽ là LTS tiếp theo vào tháng 9 năm 2027. Đây là kế hoạch của Oracle; mốc LTS và lịch hỗ trợ có thể khác ở nhà cung cấp khác. Với Java 17, cần phân biệt Premier Support đã kết thúc với Extended Support vẫn còn trong roadmap: hai mức hỗ trợ này không tương đương nhau.

Các mốc Premier Support và Extended Support trong bảng là quyền lợi hỗ trợ thương mại dành cho khách hàng Oracle đáp ứng điều kiện hỗ trợ tương ứng. Chúng không tự động áp dụng cho mọi người tải hoặc sử dụng JDK. Điều khoản license cho phép sử dụng phần mềm và quyền nhận hỗ trợ thương mại là hai nội dung cần kiểm tra riêng.

### 4.1. Chọn Java 25 cho hệ thống mới cần vòng đời dài

Java 25 là lựa chọn hợp lý để bắt đầu một dự án mới nếu các framework, thư viện, plugin build, agent giám sát và môi trường triển khai đã hỗ trợ phiên bản này. Đây là dòng LTS mới nhất theo Oracle tại thời điểm biên soạn, có thời gian hỗ trợ được công bố dài hơn các feature release thông thường.

Trước khi chốt Java 25, cần xác nhận:

- Framework chính thức hỗ trợ Java 25 và có bản phát hành phù hợp với hệ thống.
- Các thư viện, annotation processor, plugin Maven/Gradle, công cụ phân tích mã và agent runtime tương thích.
- Image container, máy chủ ứng dụng, nền tảng cloud và hệ thống giám sát có bản dựng phù hợp.
- Nhà cung cấp JDK có lịch phát hành bản vá bảo mật và mức hỗ trợ đáp ứng yêu cầu vận hành.

### 4.2. Giữ Java 21 khi cần thời gian chuyển đổi

Java 21 vẫn là dòng LTS có mốc Oracle Premier Support đến tháng 9 năm 2028. Đây có thể là lựa chọn phù hợp nếu ứng dụng hiện tại đã ổn định trên Java 21 nhưng một số dependency hoặc framework chưa sẵn sàng cho Java 25.

Nếu chọn Java 21, nên xác định rõ thời điểm đánh giá lại Java 25, theo dõi các bản cập nhật và kiểm tra điều khoản hỗ trợ của nhà cung cấp. Không nên xem việc giữ nguyên một major version là lý do để bỏ qua các bản cập nhật bảo mật.

### 4.3. Tiếp tục Java 17 cần có kế hoạch nâng cấp

Java 17 vẫn là một dòng LTS, nhưng theo roadmap Oracle, Premier Support kết thúc vào tháng 9 năm 2026. Extended Support được công bố đến tháng 9 năm 2029. Điều này có nghĩa là mức dịch vụ hỗ trợ đã thay đổi; tổ chức cần xem lại quyền lợi, chi phí và loại bản vá nhận được theo hợp đồng thực tế.

Với hệ thống đang chạy Java 17, nên lập kế hoạch đánh giá Java 21 hoặc Java 25, kiểm tra framework và dependency, sau đó nâng cấp qua môi trường thử nghiệm. Không nên hiểu nhãn LTS là cam kết rằng một dòng JDK sẽ luôn nhận cùng mức hỗ trợ miễn phí từ mọi nhà cung cấp.

### 4.4. Dùng Java 27 khi chấp nhận nhịp cập nhật nhanh

Java 27 là feature release mới nhất tại thời điểm biên soạn, phù hợp với nhóm phát triển muốn tiếp cận cải tiến mới và có khả năng kiểm thử, phát hành nâng cấp thường xuyên. Theo Oracle, đây là non-LTS và mốc Premier Support hiện tại kết thúc vào tháng 3 năm 2027.

Chọn feature release cho production chỉ khi tổ chức có quy trình cập nhật JDK đều đặn, tự kiểm tra tương thích và đã xác nhận chính sách hỗ trợ của nhà cung cấp. Nếu yêu cầu là duy trì một phiên bản ổn định trong nhiều năm, ưu tiên dòng LTS.

## 5. Cách đánh giá một JDK có thực sự còn được hỗ trợ

Trước khi đưa JDK vào dự án, hãy trả lời các câu hỏi sau:

1. **Ai cung cấp bản JDK?** Ghi rõ tên nhà cung cấp và tên bản phân phối; cùng một Java feature version có thể có nhiều binary distribution.
2. **Bản phát hành nào đang được dùng?** Ghi lại feature version, update version, build number và kiến trúc hệ điều hành.
3. **Nhà cung cấp còn phát hành security update không?** Kiểm tra trang support roadmap hoặc lịch cập nhật chính thức.
4. **Hình thức hỗ trợ là gì?** Phân biệt community support, public update, Premier Support, Extended Support và hỗ trợ theo hợp đồng.
5. **Khi nào cần nâng cấp?** Ghi rõ ngày kết thúc cập nhật, ngày kết thúc hỗ trợ và phiên bản đích dự kiến.
6. **Điều khoản sử dụng có phù hợp không?** Kiểm tra license của đúng bản phân phối, phiên bản, mục đích triển khai và hình thức phân phối ứng dụng.

Lưu ý rằng khả năng tải được một bản JDK cũ không chứng minh bản đó còn nhận bản vá bảo mật. Tương tự, một JDK chạy được ứng dụng không đồng nghĩa framework, nhà cung cấp cloud hoặc tổ chức vận hành còn hỗ trợ cấu hình đó.

## 6. Quy trình chọn và nâng cấp JDK cho dự án

### Bước 1. Chốt mục tiêu vòng đời

Xác định hệ thống cần ổn định dài hạn hay cần cập nhật tính năng thường xuyên. Với hệ thống nghiệp vụ production có chu kỳ vận hành nhiều năm, thường nên chọn LTS. Với thư viện, công cụ hoặc sản phẩm có khả năng nâng cấp thường xuyên, có thể thử feature release nếu nhà cung cấp hỗ trợ và pipeline kiểm thử đủ tốt.

### Bước 2. Kiểm tra tương thích trước khi đổi JDK

Đọc ma trận tương thích của framework, thư viện và công cụ build. Kiểm tra những thành phần nhạy cảm như reflection, truy cập API nội bộ của JDK, JNI/FFM, agent, bytecode instrumentation, plugin và cấu hình JVM. Release notes của từng JDK nêu các thay đổi có thể ảnh hưởng đến tương thích.

Khi đánh giá nâng cấp, cần phân biệt ba lớp tương thích:

- **Source compatibility**: mã nguồn hiện tại có biên dịch được hay không.
- **Binary compatibility**: class file đã biên dịch có liên kết và nạp được hay không.
- **Behavioral compatibility**: chương trình có giữ hành vi mong đợi khi chạy hay không.

Một dự án có thể biên dịch thành công nhưng vẫn gặp thay đổi hành vi khi chạy. Vì vậy, kiểm thử tích hợp, kiểm thử hiệu năng và kiểm thử trên môi trường gần production vẫn cần thiết.

### Bước 3. Khóa phiên bản trong môi trường build

Không nên để máy cá nhân, CI và production tự chọn JDK khác nhau. Hãy khai báo toolchain hoặc cấu hình JDK rõ ràng trong Maven/Gradle, pipeline CI và container image. Khi build bằng JDK mới hơn nhưng cần tạo bytecode tương thích với một phiên bản cũ hơn, sử dụng tùy chọn `--release`:

```bash
# Xác định JDK đang được dùng
java --version
javac --version

# Biên dịch với API, ngôn ngữ và bytecode của Java 25
javac --release 25 -d out src/Main.java
```

`--release` giúp giới hạn API Java mà mã nguồn được phép sử dụng theo phiên bản mục tiêu. Nó không thay thế việc chọn JDK runtime phù hợp khi triển khai. Ví dụ, nếu ứng dụng cần chạy trên Java 21 thì target build phải là Java 21 và môi trường runtime phải đáp ứng phiên bản đó.

### Bước 4. Kiểm thử và triển khai có kiểm soát

Chạy unit test, integration test, kiểm thử khởi động, kiểm thử tải và kiểm thử các luồng có dùng reflection hoặc native code. Triển khai thử trên staging hoặc một nhóm instance nhỏ, theo dõi log, lỗi, bộ nhớ, thời gian phản hồi và mức sử dụng CPU trước khi mở rộng.

### Bước 5. Duy trì cập nhật

Sau khi chọn JDK, cần có lịch kiểm tra update release và bản vá bảo mật. Theo dõi thông báo từ nhà cung cấp, cập nhật bản vá trong cùng feature line khi phù hợp, kiểm thử hồi quy và lưu lại phiên bản đã triển khai. Khi major version sắp hết hỗ trợ, bắt đầu đánh giá phiên bản kế tiếp đủ sớm để tránh nâng cấp gấp.

## 7. Khuyến nghị theo tình huống

| Tình huống | Hướng lựa chọn |
| --- | --- |
| Bắt đầu dự án backend mới, cần vận hành dài hạn | Ưu tiên JDK 25 LTS nếu framework và dependency tương thích |
| Ứng dụng đang chạy Java 21 ổn định | Tiếp tục cập nhật trong dòng 21 và lên kế hoạch chuyển sang 25 |
| Ứng dụng đang chạy Java 17 | Kiểm tra chính sách hỗ trợ hiện tại của nhà cung cấp và lập kế hoạch chuyển sang 21 hoặc 25 |
| Muốn thử các cải tiến mới nhất | Dùng JDK 27 trong môi trường phát triển/kiểm thử; chỉ triển khai khi chấp nhận nhịp nâng cấp ngắn và có hỗ trợ phù hợp |
| Đang dùng Java 22 | Đánh giá nâng cấp lên một dòng còn hỗ trợ; không giữ Java 22 chỉ vì dự án từng sử dụng tính năng được giới thiệu ở phiên bản này |

## 8. Kết luận về vai trò của Java 22

Java 22 là một feature release quan trọng trong chu kỳ phát hành sáu tháng của Java. Nó giới thiệu các khả năng đã trở thành nền tảng ổn định, đồng thời tạo môi trường preview để một số API và cú pháp tiếp tục được hoàn thiện ở Java 24 và Java 25.

Ở thời điểm hiện tại, nên học Java 22 để hiểu quá trình phát triển của nền tảng và các tính năng đã trưởng thành từ giai đoạn này. Khi chọn JDK để phát triển hoặc vận hành, hãy ưu tiên dòng LTS còn được nhà cung cấp cam kết cập nhật, xác minh tương thích của toàn bộ hệ sinh thái và duy trì bản vá bảo mật. Theo lộ trình Oracle được tham chiếu trong bài, Java 25 là LTS mới nhất; Java 21 vẫn còn Premier Support, còn Java 22 đã qua mốc Premier Support của Oracle.

## 9. Tài liệu tham khảo

- [JDK 22 Release Notes — Oracle](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html)
- [The Arrival of Java 22 — Oracle](https://blogs.oracle.com/java/the-arrival-of-java-22)
- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html)
- [JDK 27 Release Notes — Oracle](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [JDK 27.0.1.1 Release Notes — Oracle, 17 November 2026](https://www.oracle.com/java/technologies/javase/27-0-1-1-relnotes.html)
- [The Arrival of Java 27 — Oracle](https://blogs.oracle.com/java/the-arrival-of-java-27)
- [Runtime.Version — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Runtime.Version.html)
- [JEP 322 — Time-Based Release Versioning](https://openjdk.org/jeps/322)
