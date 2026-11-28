# Đọc release notes, đặc tả và JEP áp dụng cho JDK đang dùng

> Phạm vi bài viết: Java SE 27 và JDK 27. Mốc thông tin được đối chiếu đến ngày 27/11/2026; các mốc hỗ trợ thương mại được ghi rõ theo nhà cung cấp.

## 1. Mục đích và cách phân biệt ba nguồn tài liệu

Khi nâng cấp JDK hoặc đánh giá một tính năng Java mới, cần đọc ba loại tài liệu bổ trợ cho nhau:

- **Release notes** cho biết một bản JDK cụ thể đã thay đổi điều gì: tính năng mới, thay đổi mặc định, API hoặc tùy chọn bị loại bỏ, lỗi đã sửa, vấn đề tương thích và các cập nhật bảo mật.
- **Đặc tả Java SE/JDK** xác định hành vi và hợp đồng kỹ thuật của nền tảng: cú pháp và ngữ nghĩa ngôn ngữ, bytecode và JVM, API chuẩn, cùng đặc tả các công cụ JDK.
- **JEP (JDK Enhancement Proposal)** giải thích một thay đổi lớn được đề xuất hoặc triển khai trong OpenJDK: vấn đề cần giải quyết, mục tiêu, thiết kế, lựa chọn, rủi ro và trạng thái phát triển.

Ba nguồn trả lời ba câu hỏi khác nhau. Release notes cho biết thay đổi đã xuất hiện trong bản phát hành nào và có thể ảnh hưởng hệ thống ra sao. Đặc tả xác định hành vi được chuẩn hóa. JEP giải thích lý do và quá trình thiết kế của một cải tiến. Không nên dùng riêng một nguồn để kết luận rằng một tính năng đã ổn định hoặc tương thích với ứng dụng.

## 2. Xác định chính xác JDK đang được sử dụng

Trước khi mở tài liệu, hãy xác định JDK thực sự chạy trong môi trường cần đánh giá. Máy phát triển, máy build, container và máy production có thể dùng các bản phân phối hoặc bản cập nhật khác nhau.

Chạy các lệnh sau trong đúng môi trường:

```bash
java --version
javac --version
java -XshowSettings:properties -version
```

Đối chiếu ít nhất các thông tin sau:

- Nhà cung cấp và bản phân phối JDK, chẳng hạn Oracle JDK hoặc một bản dựng OpenJDK.
- Phiên bản runtime và build đầy đủ, không chỉ số phiên bản major như `27`.
- Đường dẫn JDK đang được chọn qua `JAVA_HOME`, `PATH`, cấu hình toolchain hoặc image container.
- Phiên bản `javac` dùng để biên dịch và phiên bản JVM dùng để chạy ứng dụng.

`java --version` và `javac --version` có thể trỏ đến hai bản cài đặt khác nhau nếu cấu hình môi trường chưa nhất quán. Với Maven, Gradle hoặc CI, hãy kiểm tra thêm log phiên bản của chính tiến trình build và cấu hình toolchain. Khi đọc tài liệu, chọn release notes của đúng nhà cung cấp và đúng dòng phiên bản đang triển khai.

Đặc tả Java SE và JEP của OpenJDK là nguồn chung để hiểu nền tảng. Tuy vậy, gói cài đặt, bản vá, chính sách hỗ trợ, giấy phép và một số tiện ích có thể khác giữa các nhà cung cấp. Không suy rộng lịch hỗ trợ hoặc chi tiết riêng của Oracle JDK cho mọi bản phân phối OpenJDK.

## 3. Vai trò và thứ tự đọc tài liệu

| Nguồn | Dùng để trả lời | Nên kiểm tra |
| --- | --- | --- |
| Release notes của bản phát hành chính | JDK mới thêm, đổi hoặc loại bỏ điều gì? | New features, removed features, deprecated/obsolete options, compatibility, known issues và khác biệt giữa các bản phân phối |
| Release notes của các bản cập nhật | Bản cập nhật có sửa lỗi hoặc lỗ hổng nào? | Ngày phát hành, build, security baseline, CVE, lỗi đã sửa và dữ liệu múi giờ/locale |
| Java Language Specification (JLS) | Cú pháp, kiểu dữ liệu và ngữ nghĩa của mã Java thay đổi thế nào? | Quy tắc biên dịch, pattern matching, biểu thức, câu lệnh và kiểm tra kiểu |
| Java Virtual Machine Specification (JVMS) | Class file và JVM phải tuân thủ hành vi nào? | Bytecode, định dạng class file, xác minh, liên kết và thực thi |
| Java SE API Specification | API chuẩn nào được cung cấp và có chữ ký/hành vi ra sao? | Package, module, class, interface, method, exception và trạng thái preview |
| JDK Tool Specifications | Công cụ đi kèm JDK nhận tùy chọn và hành vi nào? | `java`, `javac`, `jar`, `javadoc`, `jcmd` và các công cụ chẩn đoán |
| JEP | Vì sao thay đổi được thiết kế theo cách đó và trạng thái của nó là gì? | Motivation, Goals, Non-Goals, Description, Risks, Testing, phiên bản đích và trạng thái |

### 3.1. Đọc release notes trước

Bắt đầu từ trang release notes của phiên bản đích. Đọc phần tổng quan và các mục sau:

1. **Major New Functionality / New Features**: xác định thay đổi ảnh hưởng trực tiếp đến ngôn ngữ, API, JVM, bảo mật, hiệu năng hoặc công cụ.
2. **Removed Features and Options**: tìm API, cờ JVM, thuộc tính hệ thống và hành vi đã bị loại bỏ.
3. **Deprecated hoặc obsolete**: xác định thành phần đang được khuyến nghị thay thế hoặc đã mất tác dụng. `Deprecated` nghĩa là thành phần vẫn còn nhưng không nên dùng cho mã mới và có thể bị loại bỏ sau này. `Obsolete` thường cho biết tùy chọn đã lỗi thời ở cấp triển khai, có thể bị bỏ qua hoặc phát cảnh báo. `Removed` nghĩa là thành phần đã bị loại khỏi bản phát hành.
4. **Compatibility**: xem thay đổi có ảnh hưởng mã nguồn, liên kết nhị phân hoặc hành vi khi chạy hay không.
5. **Notable Issues Resolved / Other Notes**: kiểm tra lỗi đã sửa, thay đổi mặc định, giới hạn nền tảng, thay đổi bảo mật và thay đổi vận hành.
6. **Differences Between Oracle JDK and OpenJDK**: đọc khi môi trường sử dụng bản phân phối của Oracle hoặc cần so sánh hai bản dựng.

Không chỉ đọc ghi chú của bản GA. Nếu nâng cấp từ một bản cập nhật cũ lên bản cập nhật mới, cần đọc cả ghi chú của các bản cập nhật nằm giữa hai mốc. Trang consolidated release notes giúp xem lịch sử các bản GA của cùng một dòng JDK trên một trang.

### 3.2. Đọc đặc tả theo loại thay đổi

- Khi thay đổi liên quan đến cú pháp, biểu thức, kiểu dữ liệu hoặc quy tắc biên dịch, tra **JLS**.
- Khi thay đổi liên quan đến bytecode, class file, xác minh, liên kết hoặc hành vi JVM, tra **JVMS**.
- Khi sử dụng hoặc thay thế một API chuẩn, tra **Java SE API Specification** và JavaDoc của API đó.
- Khi thay đổi liên quan đến công cụ, tùy chọn dòng lệnh hoặc quy trình đóng gói, tra **JDK Tool Specifications** và phần tương ứng trong release notes.

Trang đặc tả Java SE 27 cung cấp JLS, JVMS, API Specification và Tool Specifications. Trang API cũng phân biệt API thuộc Java SE với API riêng của JDK. Các module có tên bắt đầu bằng `java` thuộc Java SE; các module bắt đầu bằng `jdk` là API JDK và không nhất thiết có mặt trong mọi bản triển khai Java SE.

Khi so sánh hai phiên bản, ưu tiên tài liệu API có chú giải khác biệt giữa Java SE 26 và Java SE 27. Tài liệu này giúp tìm chính xác chữ ký được thêm, thay đổi hoặc loại bỏ. Sau đó mở JavaDoc của API để kiểm tra hợp đồng, ngoại lệ, thread-safety và ghi chú tương thích trước khi sửa mã.

### 3.3. Đọc JEP để hiểu thiết kế và trạng thái

Một JEP thường trình bày vấn đề, mục tiêu, phạm vi không thực hiện, thiết kế, phương án thay thế, tác động, rủi ro và kế hoạch kiểm thử. Khi đọc JEP, cần xác nhận:

- JEP đang ở trạng thái nào và có được đưa vào đúng bản JDK đang dùng hay chưa.
- JEP mô tả tính năng hoàn chỉnh, preview, incubator hay thay đổi nội bộ của JDK.
- Có yêu cầu bật cờ, thêm module hoặc cấu hình runtime hay không.
- API, cú pháp hoặc hành vi cuối cùng có khớp với đặc tả và release notes của bản phát hành hay không.

JEP là tài liệu thiết kế và theo dõi cải tiến, không thay thế đặc tả Java SE. Không phải mọi thay đổi trong release notes đều có JEP; nhiều bản sửa lỗi, cập nhật bảo mật và thay đổi nhỏ được ghi bằng mã lỗi hoặc quy trình CSR (Compatibility & Specification Review), nơi xem xét thay đổi đặc tả và API. Ngược lại, việc một JEP được đề xuất hoặc thảo luận không chứng minh rằng tính năng đã có trong JDK đang chạy.

## 4. Trạng thái Java 27 tại ngày 27/11/2026

JDK 27 phát hành GA ngày 15/09/2026. Theo trang consolidated release notes của Oracle, bản cập nhật Oracle JDK 27 mới nhất được liệt kê tại mốc bài viết là **27.0.1.1**, phát hành ngày 17/11/2026, build `27.0.1.1+4`. Bản cập nhật này tuân theo Java SE 27 Specification (JSR 402, ngày 15/09/2026).

Trong danh mục Oracle tại cùng thời điểm, JDK 27 là feature release mới nhất, không phải LTS; JDK 25 là bản LTS mới nhất. Oracle nêu lịch cung cấp cập nhật cho JDK 27 đến tháng 03/2027, khi JDK 28 thay thế. Đây là thông tin vòng đời của Oracle; thời hạn hỗ trợ thực tế cần được xác nhận theo nhà cung cấp và hợp đồng đang sử dụng.

Khi kiểm tra một hệ thống Java 27, hãy ghi lại cả phiên bản major lẫn bản cập nhật. Chỉ ghi “Java 27” là chưa đủ để xác định bản vá bảo mật và lỗi đã có trong runtime.

## 5. Các JEP nổi bật được đưa vào JDK 27

Release notes Java 27 liệt kê chín JEP nổi bật. Bốn tính năng trong số này ở trạng thái preview và một API ở trạng thái incubator; các tính năng còn lại được phát hành mà không mang nhãn preview/incubator trong danh sách này.

| JEP | Nội dung | Trạng thái trong JDK 27 | Ý nghĩa khi đọc tài liệu |
| --- | --- | --- | --- |
| [JEP 532](https://openjdk.org/jeps/532) | Primitive Types in Patterns, `instanceof`, and `switch` | Preview lần thứ năm | Mở rộng pattern matching và `instanceof`/`switch` cho kiểu nguyên thủy; cần đọc JLS và ghi chú preview trước khi dùng |
| [JEP 531](https://openjdk.org/jeps/531) | Lazy Constants | Preview lần thứ ba | API giữ dữ liệu bất biến với thời điểm khởi tạo linh hoạt; cần xác nhận API preview và cách bật preview |
| [JEP 533](https://openjdk.org/jeps/533) | Structured Concurrency | Preview lần thứ bảy | Gom nhóm các tác vụ đồng thời thành một đơn vị công việc để quản lý lỗi, hủy và quan sát |
| [JEP 537](https://openjdk.org/jeps/537) | Vector API | Incubator lần thứ mười hai | Biểu diễn phép tính vector để tận dụng lệnh phần cứng; API incubator chưa phải hợp đồng ổn định |
| [JEP 527](https://openjdk.org/jeps/527) | Post-Quantum Hybrid Key Exchange for TLS 1.3 | Được đưa vào JDK 27, không gắn nhãn preview trong release notes | Kết hợp trao đổi khóa kháng lượng tử với thuật toán truyền thống; cần kiểm thử tương thích TLS với hệ thống đối tác |
| [JEP 538](https://openjdk.org/jeps/538) | PEM Encodings of Cryptographic Objects | Preview lần thứ ba | Bổ sung API mã hóa/giải mã khóa, chứng thư và CRL theo định dạng PEM |
| [JEP 523](https://openjdk.org/jeps/523) | Make G1 the Default Garbage Collector in All Environments | Được đưa vào JDK 27 | G1 trở thành GC mặc định trong mọi môi trường HotSpot khi không chỉ định GC khác |
| [JEP 534](https://openjdk.org/jeps/534) | Compact Object Headers by Default | Được đưa vào JDK 27 | Compact object headers trở thành bố cục mặc định của HotSpot; trên kiến trúc 64-bit, header giảm từ 96 bit xuống 64 bit |
| [JEP 536](https://openjdk.org/jeps/536) | JFR In-Process Data Redaction | Được đưa vào JDK 27 | JFR che dấu đối số dòng lệnh và giá trị ban đầu của biến môi trường/system properties trong bản ghi |

Bảng trên là điểm bắt đầu để tìm tài liệu, không phải danh sách đầy đủ mọi thay đổi trong JDK 27. Release notes còn mô tả các cập nhật về bảo mật, locale, thời gian, công cụ, I/O, GC và nhiều lỗi đã sửa.

### 5.1. Phân biệt preview và incubator

**Preview feature/API** đã được triển khai và mô tả đủ để thử nghiệm, nhưng chưa phải tính năng ổn định của nền tảng. Thiết kế có thể thay đổi hoặc bị loại bỏ ở bản phát hành sau. Với Java 27, mã nguồn sử dụng preview cần bật preview khi biên dịch và chạy bằng JDK 27:

```bash
javac --enable-preview --release 27 -d out src/Main.java
java --enable-preview -cp out Main
```

Không nên biên dịch mã preview bằng một JDK rồi chạy bằng một JDK feature release khác. Cờ preview gắn với phiên bản JDK cụ thể. Nếu sản phẩm chưa chấp nhận rủi ro thay đổi API hoặc cú pháp, hãy đợi tính năng trở thành chính thức trước khi đưa vào hợp đồng công khai.

**Incubator API** được cung cấp để thu thập phản hồi trong quá trình hoàn thiện API hoặc công cụ. API có thể thay đổi đáng kể và thường nằm trong module incubator. Cần đọc JEP, JavaDoc và hướng dẫn module của đúng bản JDK; không xem incubator API là API ổn định tương đương Java SE API.

Preview và incubator có mục đích khác nhau. Preview áp dụng cho tính năng ngôn ngữ, VM hoặc API đã được triển khai ở trạng thái preview. Incubator dành cho API/công cụ đang được thử nghiệm. Cả hai đều cần quyết định chủ động về phạm vi sử dụng, kiểm thử và kế hoạch thay thế.

### 5.2. Ví dụ về thay đổi cần chú ý khi nâng cấp lên Java 27

Release notes là nơi phát hiện các thay đổi có thể làm hỏng script hoặc ứng dụng dù mã nguồn không sử dụng tính năng mới:

- Trên Linux, tùy chọn `-Djdk.lang.Process.launchMechanism=VFORK` đã bị loại bỏ. Release notes hướng dẫn dựa vào cơ chế mặc định `POSIX_SPAWN` hoặc chuyển sang `FORK` nếu cần chỉ định cơ chế.
- Các tùy chọn launcher/VM `-noclassgc`, `-noverify`, `-verifyremote` và `-Xverify:none` đã bị loại bỏ. Cần rà soát script khởi động, cấu hình container và tham số trong pipeline để xóa hoặc thay thế các tùy chọn không còn được hỗ trợ.
- `ThreadPoolExecutor.finalize()` đã bị loại bỏ. Mã kế thừa `ThreadPoolExecutor` mà ghi đè phương thức này hoặc gọi `super.finalize()` cần được kiểm tra và cập nhật.
- Thuộc tính `java.locale.useOldISOCodes` không còn tác dụng và tạo cảnh báo. Dữ liệu cấu hình nên dùng mã ngôn ngữ hiện hành như `he`, `yi` và `id` thay cho các mã cũ `iw`, `ji` và `in`.
- G1 trở thành GC mặc định trong mọi môi trường HotSpot. Cần đo lại heap, throughput, độ trễ và thời gian khởi động ở tải đại diện, nhất là khi môi trường trước đây tự chọn Serial GC.
- Compact object headers trở thành mặc định trong HotSpot. Đây là thay đổi bố cục đối tượng nội bộ; cần kiểm thử thư viện native, agent, công cụ chẩn đoán và ứng dụng có phụ thuộc vào chi tiết triển khai JVM.
- JFR che dấu một số dữ liệu nhạy cảm ngay trong tiến trình trước khi dữ liệu rời khỏi tiến trình. Cần xác minh cấu hình quan sát và quy trình xử lý bản ghi vẫn cung cấp đủ dữ liệu chẩn đoán mà không làm lộ bí mật.
- TLS 1.3 được bổ sung hybrid key exchange kháng lượng tử. Cần kiểm thử handshake, proxy, thiết bị trung gian và hệ thống đối tác có giới hạn về thuật toán hoặc độ dài thông điệp.

Các ví dụ trên là thay đổi được ghi nhận trong release notes Java 27. Khi áp dụng vào hệ thống thật, hãy mở mục tương ứng để xem điều kiện nền tảng, cờ thay thế, phạm vi ảnh hưởng và các ngoại lệ trước khi sửa cấu hình.

## 6. Quy trình đọc tài liệu khi đánh giá một lần nâng cấp

Có thể áp dụng quy trình sau cho mọi lần chuyển JDK, kể cả khi chỉ nâng bản cập nhật trong cùng một dòng major.

1. **Lập bản kê runtime.** Ghi nhà cung cấp, phiên bản đầy đủ, build, hệ điều hành, kiến trúc CPU và nơi chạy ứng dụng. Kiểm tra riêng máy phát triển, CI, image build và production.
2. **Chọn đúng đích nâng cấp.** Xác định phiên bản JDK và bản cập nhật cần dùng. Xác minh lịch hỗ trợ, chính sách cập nhật bảo mật và điều khoản của nhà cung cấp.
3. **Đọc release notes theo khoảng nâng cấp.** Bắt đầu từ phiên bản hiện tại, đọc mọi ghi chú GA/update cho đến phiên bản đích. Tập trung vào removed, deprecated, obsolete, security, compatibility và thay đổi mặc định.
4. **Lập danh sách tác động.** Với mỗi thay đổi, đánh dấu ảnh hưởng đến mã nguồn, bytecode/liên kết, hành vi runtime, bảo mật, hiệu năng, công cụ build hoặc vận hành.
5. **Tra JEP liên quan.** Xác nhận JEP đã được đưa vào bản đích hay chưa; kiểm tra trạng thái preview/incubator và yêu cầu bật cờ/module. Đọc phần Risks, Compatibility và Testing.
6. **Đối chiếu đặc tả.** Dùng JLS cho thay đổi ngôn ngữ, JVMS cho thay đổi JVM/class file và API Specification cho thay đổi API. Kiểm tra JavaDoc và bản API có chú giải khác biệt.
7. **Thử biên dịch theo đúng mức Java.** Dùng `javac --release 27` hoặc cấu hình tương đương để kiểm soát API và ngôn ngữ mục tiêu. Cấu hình này không thay thế việc chạy thử trên đúng runtime đích.
8. **Kiểm thử trên bản JDK đích.** Chạy unit/integration/system tests; kiểm tra TLS, serialization, locale/time zone, xử lý tiến trình, GC, bộ nhớ, khởi động, JFR và các script vận hành có liên quan.
9. **Ghi lại quyết định.** Lưu phiên bản đã kiểm tra, nguồn tài liệu, thay đổi cần sửa, kết quả kiểm thử, tính năng preview được bật (nếu có) và các rủi ro còn chấp nhận.

### 6.1. Phân loại tương thích

Khi đánh giá một thay đổi, phân loại tác động theo ba dạng:

- **Source compatibility**: mã nguồn cũ còn biên dịch được hay không. Ví dụ: một method bị loại bỏ hoặc quy tắc ngôn ngữ thay đổi.
- **Binary compatibility**: class file đã biên dịch có còn liên kết và nạp được hay không. Ví dụ: thay đổi chữ ký API hoặc thành phần JVM mà bytecode phụ thuộc.
- **Behavioral compatibility**: chương trình vẫn chạy nhưng kết quả hoặc hành vi runtime có thay đổi hay không. Ví dụ: GC mặc định, xử lý TLS, locale, routing hoặc thời điểm phát sinh cảnh báo.

Một ứng dụng có thể vẫn biên dịch thành công nhưng thay đổi hành vi khi chạy. Vì vậy, kiểm thử nâng cấp phải bao gồm cả runtime và cấu hình triển khai, không chỉ build thành công.

## 7. Cách áp dụng vào một tình huống cụ thể

Giả sử một dịch vụ đang chạy JDK 25 và nhóm muốn chuyển sang JDK 27 để dùng các cải tiến runtime.

1. Ghi nhận nhà cung cấp JDK 25, bản cập nhật đang chạy và cấu hình JVM hiện tại.
2. Mở release notes JDK 27 và consolidated release notes; đọc cả thay đổi GA lẫn bản cập nhật 27.0.1.1.
3. Tìm mọi tùy chọn đã bị loại bỏ trong script khởi động, Dockerfile, manifest triển khai và cấu hình của dịch vụ. Tìm cả thuộc tính hệ thống được đánh dấu deprecated/obsolete.
4. Nếu muốn dùng Structured Concurrency hoặc Lazy Constants, mở JEP 533/JEP 531, kiểm tra API JavaDoc và ghi rõ đây là preview lần lượt thứ bảy/thứ ba trong JDK 27. Chỉ bật preview khi nhóm chấp nhận theo dõi thay đổi ở các feature release sau.
5. Nếu muốn dùng Vector API, đọc JEP 537 và tài liệu module incubator; đo hiệu năng trên phần cứng mục tiêu và chuẩn bị phương án thay thế.
6. Với thay đổi G1 và compact object headers, chạy benchmark và kiểm thử tải bằng cùng dữ liệu, giới hạn CPU/bộ nhớ và cấu hình container như production.
7. Với TLS và JFR, kiểm thử kết nối đến hệ thống đối tác và xác minh bản ghi chẩn đoán theo yêu cầu bảo mật.
8. Chạy bộ kiểm thử trên JDK 27.0.1.1 của đúng nhà cung cấp, triển khai canary nếu quy trình phát hành cho phép, theo dõi lỗi và chỉ mở rộng sau khi đạt tiêu chí vận hành.

Trong ví dụ này, JEP giúp chọn tính năng cần đánh giá; đặc tả giúp xác minh hợp đồng; release notes cho biết các thay đổi thực tế có thể tác động tới hệ thống. Kết quả cuối cùng phải dựa trên runtime và bản phân phối đã được kiểm thử.

## 8. Danh sách kiểm tra trước khi kết luận

- [ ] Đã xác định đúng nhà cung cấp, bản phân phối, phiên bản đầy đủ và build của JDK đang chạy.
- [ ] Đã đọc release notes của bản GA và mọi bản cập nhật trong khoảng nâng cấp.
- [ ] Đã rà soát tính năng bị loại bỏ, deprecated/obsolete, thay đổi mặc định và vấn đề tương thích.
- [ ] Đã kiểm tra JEP liên quan và xác nhận trạng thái final, preview hoặc incubator.
- [ ] Đã tra JLS, JVMS, API Specification hoặc Tool Specifications đúng với loại thay đổi.
- [ ] Đã phân loại tác động source, binary và behavioral.
- [ ] Đã xác minh các cờ preview/module và phiên bản JDK cần thiết.
- [ ] Đã chạy build và kiểm thử trên đúng runtime đích, bao gồm kiểm thử bảo mật và hiệu năng có liên quan.
- [ ] Đã ghi lại nguồn, ngày đối chiếu, bản cập nhật, kết quả và rủi ro còn lại.

## 9. Nguồn tài liệu chính thức

- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — thay đổi lớn, tính năng mới, thành phần bị loại bỏ, vấn đề đã sửa và khác biệt giữa Oracle JDK/OpenJDK.
- [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html) — release notes hợp nhất của các bản GA và cập nhật JDK 27.
- [Java SE 27 and JDK 27 Specifications](https://docs.oracle.com/en/java/javase/27/docs/specs/index.html) — JLS, JVMS, Java SE API, JDK Tool Specifications và các đặc tả liên quan.
- [Java SE 27 API Documentation](https://docs.oracle.com/en/java/javase/27/docs/api/index.html) — JavaDoc API của Java SE và JDK 27.
- [JDK Releases](https://ops.java/releases/) — lịch phát hành và mốc hỗ trợ của các dòng JDK; cần xác nhận theo nhà cung cấp.
- [The Arrival of Java 27](https://blogs.oracle.com/java/the-arrival-of-java-27) — tổng quan các JEP nổi bật và nhóm cải tiến trong JDK 27.
- [JEP Index](https://openjdk.org/jeps/0) — tra cứu đề xuất cải tiến của OpenJDK.

Khi tài liệu trực tuyến được cập nhật, hãy ghi ngày đối chiếu và phiên bản JDK cụ thể trong ghi chú kỹ thuật của dự án. Điều này giúp người đọc phân biệt thông tin đúng tại thời điểm đánh giá với thông tin mới được bổ sung ở các bản cập nhật sau.
