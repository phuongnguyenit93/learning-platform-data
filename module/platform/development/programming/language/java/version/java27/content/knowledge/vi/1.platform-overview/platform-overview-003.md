# Xác định trạng thái phát hành và phạm vi tính năng của Java 27

*Cập nhật theo thông tin công khai đến ngày 27-11-2026.*

Java 27 là bản phát hành tính năng đã hoàn tất (General Availability — GA) từ ngày 15-09-2026. Vì vậy, khi học hoặc đánh giá Java 27 ở thời điểm hiện tại, cần xem đây là một phiên bản JDK đã phát hành chính thức, không còn là bản Early Access. Tuy nhiên, Java 27 thuộc nhóm **non-LTS** theo lộ trình hỗ trợ của Oracle. Một số tính năng trong bản phát hành đã trở thành hành vi/API chuẩn, trong khi một số tính năng vẫn ở trạng thái Preview hoặc Incubator và cần được đánh giá riêng trước khi đưa vào sản phẩm.

Bài này xác định mốc phát hành, vòng đời hỗ trợ và phạm vi thay đổi nổi bật của Java 27. Trọng tâm là phân biệt phần đã ổn định với phần còn thử nghiệm, để lựa chọn cách học, thử nghiệm, nâng cấp và triển khai phù hợp.

## 1. Java 27, JDK 27 và Java SE 27 có nghĩa gì?

Các tên gọi thường được dùng thay thế nhau trong hội thoại, nhưng chúng mô tả những lớp khác nhau:

- **Java SE 27** là phiên bản đặc tả nền tảng Java. Đặc tả mô tả ngôn ngữ, máy ảo và các API thuộc nền tảng chuẩn.
- **JDK 27** là bộ công cụ phát triển triển khai phiên bản Java SE 27, gồm trình biên dịch **javac**, máy ảo và các công cụ phát triển, chẩn đoán.
- **Java 27** là cách gọi ngắn thường dùng cho phiên bản nền tảng/JDK này.

Một nhà cung cấp có thể đóng gói và phân phối JDK 27 theo cách riêng. Vì vậy, số phiên bản Java SE xác định nền tảng tương thích, còn lịch cập nhật, bản vá và điều khoản hỗ trợ cần được kiểm tra theo nhà cung cấp JDK đang sử dụng.

## 2. Trạng thái phát hành tại ngày 27-11-2026

### 2.1. Java 27 đã GA

Oracle công bố JDK 27 General Availability vào ngày **15-09-2026**. Release Notes ghi phiên bản nền tảng là 27 và build GA ban đầu là **27+35**. Điều này có nghĩa JDK 27 đã qua giai đoạn phát triển Early Access và có thể được sử dụng làm nền tảng phát triển, kiểm thử hoặc vận hành theo chính sách hỗ trợ của tổ chức.

Các mốc phiên bản Oracle đã công bố:

| Mốc | Ngày | Ý nghĩa |
|---|---|---|
| JDK 27 GA | 15-09-2026 | Bản phát hành tính năng Java SE 27 chính thức |
| JDK 27.0.1 | 20-10-2026 | Bản cập nhật cho dòng JDK 27 |
| JDK 27.0.1.1 | 17-11-2026 | Bản cập nhật GA mới nhất được ghi trong Release Notes Oracle tại ngày cập nhật bài này |

Bản Oracle JDK 27.0.1.1 có full version string **27.0.1.1+4**, tuân theo đặc tả Java SE 27. Bản cập nhật này bao gồm dữ liệu múi giờ IANA 2026e và các bản sửa lỗi bảo mật. Đây là số phiên bản của bản phân phối Oracle; các nhà cung cấp OpenJDK khác có thể có lịch phát hành và cách đánh số bản cập nhật riêng.

**GA và LTS là hai khái niệm khác nhau.** GA cho biết phiên bản đã được phát hành chính thức. LTS mô tả cam kết hỗ trợ dài hạn của nhà cung cấp. Một phiên bản có thể đã GA nhưng vẫn là non-LTS, như Java 27.

### 2.2. Java 27 thuộc nhóm non-LTS

Theo Oracle Java SE Support Roadmap cập nhật ngày 20-10-2026:

- Java 25 là bản LTS.
- Java 26 và Java 27 là các bản non-LTS.
- Oracle ghi mốc Premier Support của Java 27 đến tháng 03-2027.
- Java 28 được lên lịch vào tháng 03-2027.
- Java 29 được dự kiến là bản LTS tiếp theo vào tháng 09-2027.

Các mốc cho Java 28 và Java 29 là kế hoạch tại thời điểm công bố; Oracle lưu ý phân loại LTS và thời điểm có thể thay đổi. Bảng hỗ trợ này là chính sách của Oracle, không phải cam kết bắt buộc đối với mọi bản phân phối OpenJDK.

Non-LTS không có nghĩa là phiên bản chưa ổn định hoặc không thể chạy production. Nó có nghĩa là thời hạn hỗ trợ thương mại của nhà cung cấp ngắn hơn so với bản LTS. Khi một bản feature release tiếp theo được phát hành, bản non-LTS trước đó có thể bị xem là đã được thay thế trong chính sách hỗ trợ của nhà cung cấp. Do đó, hệ thống cần thời gian bảo trì dài nên chọn bản Java dựa trên ma trận hỗ trợ thực tế của nhà cung cấp, thay vì chỉ dựa vào số phiên bản mới nhất.

### 2.3. Cách hiểu đúng về mốc hỗ trợ

Khi kiểm tra vòng đời Java 27, cần trả lời riêng ba câu hỏi:

1. **Phiên bản đã GA chưa?** Có. JDK 27 GA từ ngày 15-09-2026.
2. **Phiên bản có phải LTS không?** Không theo lộ trình Oracle được công bố tại ngày cập nhật bài này.
3. **Bản phân phối đang dùng được cập nhật và hỗ trợ đến khi nào?** Tra cứu trang hỗ trợ của đúng nhà cung cấp và đúng gói JDK. Không suy ra thời hạn hỗ trợ của Temurin, Oracle JDK, Corretto, Zulu hoặc bản phân phối khác từ bảng của Oracle.

Khi ghi nhận phiên bản trong dự án, nên lưu cả nhà cung cấp và full version string. Chỉ ghi **Java 27** có thể chưa đủ để xác định chính xác bản vá đang chạy.

## 3. Phạm vi tính năng nổi bật của JDK 27

Oracle công bố **9 JDK Enhancement Proposals (JEPs)** cho JDK 27. Trong đó có bốn tính năng Preview và một API Incubator. Bốn JEP còn lại được đưa vào bản phát hành mà không mang trạng thái Preview/Incubator.

Bảng dưới đây tổng hợp trạng thái của chín JEP theo thông tin phát hành Java 27:

| JEP | Tính năng | Trạng thái trong JDK 27 | Phạm vi chính |
|---|---|---|---|
| [JEP 527](https://openjdk.org/jeps/527) | Post-Quantum Hybrid Key Exchange for TLS 1.3 | Chuẩn trong bản phát hành | Trao đổi khóa lai cho TLS 1.3, kết hợp thuật toán truyền thống và thuật toán kháng lượng tử |
| [JEP 538](https://openjdk.org/jeps/538) | PEM Encodings of Cryptographic Objects | Preview lần 3 | API mã hóa/giải mã khóa, chứng chỉ và danh sách thu hồi chứng chỉ theo định dạng PEM |
| [JEP 532](https://openjdk.org/jeps/532) | Primitive Types in Patterns, instanceof, and switch | Preview lần 5 | Mở rộng pattern matching và các cấu trúc instanceof, switch cho kiểu nguyên thủy |
| [JEP 523](https://openjdk.org/jeps/523) | Make G1 the Default Garbage Collector in All Environments | Chuẩn trong bản phát hành | Chọn G1 làm garbage collector mặc định trong mọi môi trường HotSpot |
| [JEP 534](https://openjdk.org/jeps/534) | Compact Object Headers by Default | Chuẩn trong bản phát hành | Dùng compact object headers làm bố cục header mặc định trên HotSpot |
| [JEP 531](https://openjdk.org/jeps/531) | Lazy Constants | Preview lần 3 | API cho hằng số có thể khởi tạo trì hoãn |
| [JEP 533](https://openjdk.org/jeps/533) | Structured Concurrency | Preview lần 7 | Tổ chức nhóm tác vụ đồng thời như một đơn vị để quản lý lỗi, hủy và quan sát |
| [JEP 537](https://openjdk.org/jeps/537) | Vector API | Incubator lần 12 | Biểu diễn phép tính vector để tận dụng lệnh vector của CPU |
| [JEP 536](https://openjdk.org/jeps/536) | JFR In-Process Data Redaction | Chuẩn trong bản phát hành | Che dữ liệu nhạy cảm trong bản ghi Java Flight Recorder ngay trong tiến trình |

### 3.1. Ngôn ngữ Java: kiểu nguyên thủy trong pattern matching

**JEP 532 — Primitive Types in Patterns, instanceof, and switch** tiếp tục mở rộng pattern matching để hỗ trợ kiểu nguyên thủy trong các ngữ cảnh pattern, đồng thời cho phép instanceof và switch làm việc với các kiểu nguyên thủy.

Điểm quan trọng là JEP này vẫn ở **Preview lần thứ năm** trong Java 27. Đây chưa phải cú pháp chuẩn có cam kết ổn định cho mọi phiên bản Java sau này. Khi thử nghiệm, cần bật Preview và kiểm tra lại mã nguồn khi chuyển sang JDK khác.

### 3.2. Bảo mật: trao đổi khóa lai cho TLS 1.3 và định dạng PEM

Java 27 có hai thay đổi đáng chú ý trong thư viện bảo mật:

- **JEP 527 — Post-Quantum Hybrid Key Exchange for TLS 1.3** bổ sung trao đổi khóa lai cho TLS 1.3. Cách tiếp cận này kết hợp một thuật toán trao đổi khóa truyền thống với một thuật toán hướng tới khả năng kháng tấn công từ máy tính lượng tử. Mục tiêu là giữ được tính bảo mật nếu ít nhất một thành phần trao đổi khóa vẫn an toàn. Ứng dụng sử dụng API **javax.net.ssl** có thể hưởng lợi từ các thuật toán được hỗ trợ mà không cần thay đổi mã nguồn trong trường hợp cấu hình và các đầu cuối TLS tương thích.
- **JEP 538 — PEM Encodings of Cryptographic Objects** cung cấp API để mã hóa và giải mã các đối tượng khóa mật mã, chứng chỉ và danh sách thu hồi chứng chỉ theo định dạng PEM. Trong Java 27, API này vẫn là **Preview lần thứ ba**, vì vậy chưa nên xem nó là hợp đồng API ổn định.

Hai thay đổi này giải quyết hai lớp công việc khác nhau: JEP 527 tác động đến quá trình thương lượng khóa của kết nối TLS; JEP 538 giúp ứng dụng thao tác với dữ liệu và tệp chứa đối tượng mật mã.

### 3.3. Hiệu năng và bộ nhớ: G1 và compact object headers

**JEP 523 — Make G1 the Default Garbage Collector in All Environments** đưa G1 thành garbage collector mặc định trong mọi môi trường HotSpot. Trước thay đổi này, một số môi trường có thể chọn Serial GC làm mặc định. Khi ứng dụng không chỉ định garbage collector trên dòng lệnh, JVM sẽ chọn G1.

Điều đó không có nghĩa G1 luôn là lựa chọn tối ưu cho mọi workload. Ứng dụng có yêu cầu đặc biệt về thông lượng, độ trễ, dung lượng bộ nhớ hoặc thời gian khởi động vẫn cần benchmark trên workload thực tế và xem xét cấu hình GC phù hợp.

**JEP 534 — Compact Object Headers by Default** đưa compact object headers thành bố cục header mặc định của đối tượng trong HotSpot. Trên kiến trúc 64-bit, kích thước header được giảm từ 96 bit xuống 64 bit. Mục tiêu là giảm mức tiêu thụ heap, tăng mật độ triển khai và cải thiện tính cục bộ dữ liệu.

Đây là thay đổi ở cách JVM biểu diễn đối tượng trong bộ nhớ. Phần lớn ứng dụng Java thông thường không cần sửa mã nguồn chỉ để sử dụng mặc định này. Tuy vậy, khi nâng cấp JDK, hệ thống có sử dụng agent, công cụ chẩn đoán hoặc thành phần phụ thuộc sâu vào chi tiết nội bộ JVM cần được kiểm thử trên đúng bản JDK đích.

### 3.4. Khởi tạo và đồng thời: Lazy Constants, Structured Concurrency

Hai API sau tiếp tục ở trạng thái Preview:

- **JEP 531 — Lazy Constants (Preview lần 3)** giới thiệu API cho đối tượng chứa dữ liệu không thể thay đổi nhưng có thể được khởi tạo vào thời điểm cần thiết. JVM có thể xem lazy constant như hằng số thực sự để áp dụng các tối ưu hóa tương tự trường final. Tính năng này hữu ích khi việc tạo dữ liệu tốn chi phí nhưng không phải lúc nào cũng cần ngay khi ứng dụng khởi động.
- **JEP 533 — Structured Concurrency (Preview lần 7)** tổ chức một nhóm tác vụ chạy trên nhiều luồng như một đơn vị công việc. Cách tổ chức này giúp quản lý vòng đời tác vụ, lỗi, hủy tác vụ và khả năng quan sát rõ ràng hơn so với việc quản lý nhiều tác vụ độc lập.

Cả hai API đều chưa được hoàn tất. Có thể dùng chúng để học và thử nghiệm trong môi trường kiểm soát, nhưng cần tránh tạo phụ thuộc production dài hạn vào chữ ký API Preview.

### 3.5. Tính toán vector: Vector API

**JEP 537 — Vector API (Incubator lần 12)** tiếp tục cung cấp API biểu diễn phép tính vector, cho phép JVM biên dịch phép tính thành các lệnh vector phù hợp trên CPU được hỗ trợ. API này hướng đến workload như xử lý dữ liệu số, phân tích dữ liệu, tính toán khoa học và suy luận AI.

Vector API vẫn là **Incubator**, không phải API Java SE đã ổn định. Khi thử nghiệm, cần chủ động đưa module **jdk.incubator.vector** vào module graph, đồng thời kiểm tra khả năng hỗ trợ của JDK và CPU mục tiêu. Không nên coi mã sử dụng API incubator là giao diện tương thích lâu dài.

### 3.6. Quan sát và chẩn đoán: JFR In-Process Data Redaction

**JEP 536 — JFR In-Process Data Redaction** mở rộng Java Flight Recorder để che các đối số dòng lệnh cùng giá trị ban đầu của biến môi trường và system properties trong bản ghi. Việc che dữ liệu diễn ra ngay trong tiến trình trước khi dữ liệu rời khỏi tiến trình, giúp giảm nguy cơ thông tin nhạy cảm bị lộ qua dữ liệu chẩn đoán.

Tính năng này hỗ trợ an toàn hơn khi thu thập và chia sẻ JFR recording. Dù vậy, không nên suy luận rằng mọi loại bí mật trong mọi nguồn dữ liệu đều tự động được che. Nhóm vận hành vẫn cần kiểm tra cấu hình ghi, nội dung bản ghi và quy trình lưu trữ/chia sẻ dữ liệu chẩn đoán.

## 4. Phân biệt tính năng chuẩn, Preview và Incubator

Đây là bước quan trọng nhất khi xác định phạm vi sử dụng của Java 27.

| Trạng thái | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Tính năng chuẩn trong bản phát hành | Đã được đưa vào JDK 27 mà không mang nhãn Preview hoặc Incubator | Có thể sử dụng theo đặc tả/API của Java 27; vẫn cần kiểm tra thay đổi tương thích trong Release Notes |
| Preview | Được triển khai để nhận phản hồi thực tế nhưng chưa phải hợp đồng ổn định; có thể thay đổi hoặc bị loại bỏ ở bản sau | Phải chủ động bật Preview khi biên dịch và chạy |
| Incubator | API hoặc công cụ đang được phát triển để thu thập phản hồi; có thể thay đổi đáng kể | Phải chủ động đưa module Incubator vào sử dụng và chấp nhận rủi ro thay đổi API |

Trong Java 27:

- **Bốn JEP Preview:** 531, 532, 533 và 538.
- **Một JEP Incubator:** 537.
- **Bốn JEP không mang trạng thái Preview/Incubator:** 523, 527, 534 và 536.

### 4.1. Bật Preview khi thử nghiệm

Với mã nguồn sử dụng Preview feature của JDK 27, compiler và runtime đều cần bật Preview. Ví dụ:

~~~bash
javac --release 27 --enable-preview Example.java
java --enable-preview Example
~~~

Cần biên dịch bằng JDK 27 tương ứng. Preview feature gắn với từng bản phát hành; việc bật Preview trên JDK khác không biến một tính năng Preview của Java 27 thành API ổn định.

### 4.2. Sử dụng API Incubator

Với Vector API, module **jdk.incubator.vector** phải được đưa vào module graph. Ví dụ khi chạy ứng dụng:

~~~bash
java --add-modules jdk.incubator.vector -cp app.jar com.example.Main
~~~

Lệnh cụ thể khi biên dịch hoặc chạy bằng Gradle/Maven phụ thuộc cách dự án cấu hình module và toolchain. Cần cấu hình cả môi trường biên dịch lẫn môi trường chạy, sau đó kiểm tra cảnh báo Incubator do JDK phát ra.

Không nên bỏ qua trạng thái Preview/Incubator khi ghi tài liệu kỹ thuật. Nếu một thư viện hoặc ứng dụng sử dụng các API này, cần ghi rõ phiên bản JDK yêu cầu và kế hoạch xử lý khi API thay đổi.

## 5. Chín JEP không phải toàn bộ nội dung của Java 27

Danh sách chín JEP chỉ bao gồm những thay đổi được tách thành các đề xuất JEP nổi bật. JDK 27 còn có nhiều cải tiến và bản sửa lỗi khác trong JVM, compiler, thư viện, bảo mật, I/O, dữ liệu múi giờ, công cụ chẩn đoán và các thành phần nền tảng.

Một số ví dụ được nêu trong thông tin phát hành:

- Cập nhật các thành phần mật mã hậu lượng tử và cải thiện hiệu năng của một số thuật toán mật mã.
- Bổ sung lệnh **jcmd VM.security_properties** để xem các security properties đang hoạt động.
- Cải thiện tối ưu hóa của C2, G1 và các phép tính vector.
- Cải thiện I/O, chẩn đoán file descriptor và khả năng đọc dữ liệu thread dump dạng JSON.
- Cập nhật dữ liệu múi giờ IANA theo từng bản cập nhật JDK.

Do đó, khi cần biết đầy đủ một bản JDK 27 cụ thể đã thay đổi những gì, phải đọc Release Notes của đúng bản cập nhật, không chỉ đọc danh sách JEP. Các bản cập nhật như 27.0.1 và 27.0.1.1 còn có thể bổ sung bản vá bảo mật, cập nhật dữ liệu múi giờ và điều chỉnh hành vi mà không tạo ra một feature release mới.

Cũng cần phân biệt JDK với các sản phẩm trong hệ sinh thái. JavaFX 27 hoặc Helidon 27 có thể được phát hành cùng thời điểm với JDK 27, nhưng chúng là các sản phẩm/framework riêng; không nên cộng chúng vào danh sách tính năng Java SE chỉ vì cùng mang số phiên bản 27.

## 6. Cách xác định JDK đang dùng và đánh giá phạm vi nâng cấp

Khi kiểm tra một máy hoặc pipeline, trước hết xác minh phiên bản thực tế của runtime và compiler:

~~~bash
java -version
javac -version
~~~

Hai lệnh có thể trả về phiên bản khác nhau nếu PATH, JAVA_HOME hoặc cấu hình toolchain trỏ đến các JDK khác nhau. Vì vậy, không nên chỉ nhìn tên thư mục cài đặt hoặc cấu hình IDE rồi kết luận ứng dụng đang chạy Java 27.

Một quy trình đánh giá nâng cấp có thể thực hiện theo thứ tự sau:

1. **Xác định bản phân phối:** ghi lại vendor, full version string, kiến trúc và hệ điều hành của JDK.
2. **Kiểm tra trạng thái hỗ trợ:** tra roadmap của nhà cung cấp để xác định bản cập nhật bảo mật, thời hạn hỗ trợ và phiên bản thay thế.
3. **Đọc Release Notes:** tập trung vào mục New Features, Removed Features and Options, Deprecated APIs/Features và các ghi chú tương thích.
4. **Phân loại API đang dùng:** xác định mã nguồn có dùng Preview API, Incubator API, API nội bộ hoặc tùy chọn JVM có hành vi thay đổi hay không.
5. **Kiểm thử trên JDK đích:** biên dịch lại, chạy unit/integration test, kiểm tra TLS, GC, bộ nhớ, thời gian khởi động và công cụ quan sát.
6. **Cập nhật bản vá:** chọn bản cập nhật mới nhất được nhà cung cấp hỗ trợ cho dòng JDK đã chọn; không dừng ở bản GA ban đầu nếu đã có bản vá mới hơn.

Khi nâng cấp từ một bản Java trước đó, nên kiểm tra cả ba lớp tương thích:

- **Tương thích mã nguồn:** mã nguồn hiện tại có biên dịch được hay không.
- **Tương thích nhị phân:** thư viện và class đã biên dịch có liên kết/chạy được hay không.
- **Tương thích hành vi:** chương trình có còn hoạt động đúng khi runtime, GC, bảo mật hoặc thư viện thay đổi hay không.

Release Notes JDK 27 có mô tả các loại vấn đề tương thích này và liệt kê những thay đổi có thể ảnh hưởng khi chuyển phiên bản.

## 7. Khi nào nên chọn Java 27?

Java 27 phù hợp khi dự án cần đánh giá các cải tiến mới của nền tảng, muốn kiểm thử sớm những thay đổi về bảo mật, hiệu năng hoặc runtime, và có khả năng cập nhật JDK theo chu kỳ feature release. Đội ngũ cũng cần có pipeline kiểm thử đủ tốt để phát hiện thay đổi tương thích giữa các bản cập nhật.

Nếu hệ thống cần thời hạn hỗ trợ dài, chu kỳ nâng cấp chậm hoặc chính sách vận hành yêu cầu một bản LTS, hãy đối chiếu các bản LTS còn được nhà cung cấp hỗ trợ. Tại thời điểm bài này được cập nhật, Java 25 là bản LTS hiện hành trong roadmap Oracle; Java 29 mới chỉ là kế hoạch LTS tiếp theo. Lựa chọn cuối cùng vẫn phụ thuộc vào nhà cung cấp JDK, nền tảng triển khai và chính sách hỗ trợ của tổ chức.

Có thể dùng quy tắc sau để ra quyết định:

| Nhu cầu | Hướng đánh giá |
|---|---|
| Học và thử nghiệm tính năng mới của Java 27 | Dùng JDK 27 GA hoặc bản cập nhật mới hơn được nhà cung cấp hỗ trợ |
| Dùng tính năng Preview | Chỉ bật Preview trong môi trường thử nghiệm có kiểm soát; chuẩn bị khả năng sửa mã khi API thay đổi |
| Thử Vector API | Chấp nhận trạng thái Incubator, kiểm tra CPU/JDK và không coi API là hợp đồng ổn định |
| Vận hành hệ thống cần hỗ trợ dài hạn | Chọn bản LTS theo roadmap của nhà cung cấp và chính sách của tổ chức |
| Nâng cấp ứng dụng hiện hữu | Đọc Release Notes, kiểm tra tương thích và benchmark workload thực tế trước khi triển khai |

## 8. Kết luận về trạng thái và phạm vi Java 27

Tại ngày 27-11-2026, Java 27 là một feature release đã GA từ tháng 09-2026; bản Oracle JDK 27.0.1.1 được phát hành ngày 17-11-2026. Java 27 thuộc nhóm non-LTS theo roadmap Oracle, với mốc Premier Support được ghi đến tháng 03-2027.

Phạm vi nổi bật của bản phát hành gồm cải tiến ngôn ngữ, bảo mật TLS hậu lượng tử, garbage collection, bố cục object header, khởi tạo hằng số, đồng thời có cấu trúc, tính toán vector và chẩn đoán JFR. Trong chín JEP nổi bật, bốn JEP đã vào bản phát hành mà không mang nhãn Preview/Incubator; bốn JEP vẫn Preview và một JEP vẫn Incubator. Sự phân biệt này quyết định cách bật tính năng, mức độ ổn định của API và rủi ro khi nâng cấp.

Khi đánh giá Java 27, hãy kiểm tra đồng thời ba yếu tố: bản JDK cụ thể đang chạy, trạng thái của từng tính năng được sử dụng và chính sách hỗ trợ của nhà cung cấp. Cách kiểm tra này giúp tránh nhầm một bản GA với một bản LTS, hoặc nhầm một API Preview/Incubator với API chuẩn của nền tảng.

## 9. Nguồn tham khảo chính thức

- [The Arrival of Java 27 — Oracle, 15-09-2026](https://blogs.oracle.com/java/the-arrival-of-java-27): thông báo GA và tổng quan chín JEP.
- [JDK 27 Release Notes — Oracle](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): mô tả tính năng, Preview/Incubator, thay đổi và vấn đề tương thích.
- [JDK 27.0.1.1 Release Notes — Oracle, 17-11-2026](https://www.oracle.com/java/technologies/javase/27-0-1-1-relnotes.html): phiên bản cập nhật, dữ liệu múi giờ và bản vá bảo mật.
- [Oracle Java SE Support Roadmap, cập nhật 20-10-2026](https://www.oracle.com/java/technologies/java-se-support-roadmap.html): phân loại LTS/non-LTS và thời hạn hỗ trợ của Oracle.
- [JEP Index — OpenJDK](https://openjdk.org/jeps/0): tra cứu đề xuất và trạng thái của từng JEP.
- [RFC 9954 — Hybrid Key Exchange in TLS 1.3](https://www.rfc-editor.org/rfc/rfc9954): nền tảng giao thức cho trao đổi khóa lai trong TLS 1.3.
