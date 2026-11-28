# Cách đọc đặc tả, API Docs và ghi chú tương thích

Khi học một thay đổi của Java, cần trả lời được ba câu hỏi: tài liệu nào mô tả hành vi chính thức, tính năng đang ở mức ổn định nào, và thay đổi đó ảnh hưởng ra sao đến mã nguồn, bytecode cùng hành vi lúc chạy. Một bài giới thiệu hoặc ví dụ chạy được chưa đủ để kết luận rằng API đã ổn định, có trong mọi bản phân phối JDK, hoặc an toàn khi nâng cấp.

Với Java 26, hãy dùng tài liệu được đóng phiên bản `26` để xác định nội dung của release này. Sau đó kiểm tra tài liệu release hiện hành để biết trạng thái tính năng đã thay đổi hay chưa. Tại ngày 27-11-2026, Java 27 là feature release hiện hành; Java 26 đã qua mốc kết thúc hỗ trợ tháng 9-2026 trong lịch hỗ trợ được công bố. Chính sách cập nhật thực tế còn tùy nhà cung cấp JDK và hợp đồng hỗ trợ của tổ chức. Vì vậy, tài liệu Java 26 phù hợp để hiểu chính xác Java 26 đã cung cấp gì, nhưng không tự động chứng minh một runtime Java 26 vẫn là lựa chọn được hỗ trợ cho production. [Lịch phát hành và hỗ trợ JDK](https://ops.java/releases/?lang=en) · [Tài liệu JDK 26](https://docs.oracle.com/en/java/javase/26/docs/) · [Ghi chú JDK 27](https://www.oracle.com/java/technologies/javase/27all-relnotes.html).

## 1. Chọn đúng nguồn theo câu hỏi

Java có nhiều loại tài liệu vì mỗi tài liệu trả lời một nhóm câu hỏi khác nhau. Hãy chọn tài liệu theo điều cần xác minh, thay vì chỉ tìm một bài viết có tên tính năng.

| Cần xác minh | Tài liệu nên đọc | Phạm vi chính |
|---|---|---|
| Cú pháp, kiểu dữ liệu, chuyển đổi kiểu, phạm vi biến, pattern matching, `switch`, quy tắc biên dịch | **Java Language Specification (JLS)** | Ngữ nghĩa và quy tắc của ngôn ngữ Java. |
| Định dạng `.class`, bytecode, xác minh class, nạp, liên kết và khởi tạo lớp, lệnh JVM | **Java Virtual Machine Specification (JVMS)** | Hợp đồng ở mức máy ảo và class file. |
| Chữ ký, tham số, giá trị trả về, ngoại lệ và hành vi của lớp hoặc phương thức | **Java SE API Specification** | Hợp đồng API chuẩn của nền tảng Java SE. |
| API chỉ có trong JDK cụ thể, công cụ chẩn đoán, quản trị hoặc triển khai | **JDK API Specification** và **Tool Specifications** | API và công cụ thuộc JDK; không mặc nhiên có trên mọi implementation Java SE. |
| Lý do thiết kế, phạm vi, phương án và vòng đời một tính năng | **JDK Enhancement Proposal (JEP)** | Bối cảnh thiết kế và trạng thái đề xuất. |
| Thay đổi theo từng release, API bị thêm/bỏ/deprecate, tùy chọn JVM bị thay đổi, lỗi đã biết | **Release Notes** | Những thay đổi cần chú ý khi dùng hoặc nâng cấp JDK. |
| Các bước nâng cấp ứng dụng, thư viện và công cụ | **JDK Migration Guide** | Quy trình kiểm tra và xử lý rủi ro khi chuyển phiên bản. |
| Chi tiết thay đổi của đặc tả hoặc API giữa hai release | **Platform Specification**, phụ lục API diff và **CSR** | Đối chiếu thay đổi đã được xem xét cho release. |

Trang [Java SE 26 & JDK 26 Specifications](https://docs.oracle.com/en/java/javase/26/docs/specs/index.html) là điểm vào hữu ích: trang này liên kết JLS, JVMS, API Specification, Tool Specifications và các đặc tả định dạng liên quan. Với một thay đổi của nền tảng, Platform Specification cho biết nội dung chuẩn; release notes bổ sung những thay đổi thực tế và vấn đề tương thích. Hai nguồn này bổ sung cho nhau. Release notes không thay thế toàn bộ đặc tả.

### JLS, JVMS và API Specification khác nhau thế nào?

- **JLS** mô tả ngôn ngữ mà lập trình viên viết: biểu thức, câu lệnh, kiểu, overload, pattern, quy tắc kiểm tra kiểu và ngữ nghĩa thực thi. Ví dụ, khi cần biết primitive pattern có hợp lệ trong một ngữ cảnh `switch` hay không, hãy tra JLS của đúng release và tài liệu cập nhật ngôn ngữ tương ứng.
- **JVMS** mô tả máy ảo xử lý class file: cấu trúc class file, bytecode, xác minh, nạp, liên kết, khởi tạo và các vùng dữ liệu lúc chạy. Khi cần hiểu vì sao một class file không thể được nạp bởi một runtime cụ thể, hãy kiểm tra phiên bản class file và quy tắc trong JVMS.
- **Java SE API Specification** mô tả hợp đồng mà mã ứng dụng có thể gọi. Một API có thể được mô tả bằng Javadoc mà không làm thay đổi cú pháp ngôn ngữ; ngược lại, một thay đổi JLS không nhất thiết tạo thêm lớp hay phương thức.

Một quy tắc thực tế là: dùng JLS để xác nhận điều gì hợp lệ trong mã nguồn, JVMS để xác nhận điều gì xảy ra với class file và máy ảo, API Specification để xác nhận hợp đồng khi gọi thư viện. Không suy luận một điều từ tài liệu thuộc lớp khác.

### Phân biệt Java SE API và JDK API

Trong trang API Docs, hãy nhìn tên module trước khi dựa vào một lớp hoặc phương thức. Các module có tên bắt đầu bằng `java` thường chứa Java SE APIs; module bắt đầu bằng `jdk` chứa JDK-specific APIs và không nhất thiết tồn tại trong mọi implementation của Java SE. Đây là khác biệt quan trọng khi cần chạy ứng dụng trên nhiều nhà cung cấp JDK.

Ví dụ:

- `java.net.http` chứa HTTP Client và WebSocket APIs. Đây là API thuộc Java SE.
- `jdk.incubator.vector` chứa Vector API ở trạng thái incubator. Tên module cho thấy đây là API thuộc JDK và đang trong giai đoạn thử nghiệm.

Vì thế, đừng kết luận một API là chuẩn Java SE chỉ vì nó xuất hiện trong trang JDK API Docs. Kiểm tra module, package, trạng thái preview/incubator và tài liệu của nhà cung cấp runtime mà ứng dụng sẽ sử dụng. [Tổng quan API Java 26](https://docs.oracle.com/en/java/javase/26/docs/api/index.html).

## 2. Quy trình đọc một thay đổi Java

Có thể áp dụng quy trình sau cho HTTP/3, pattern matching, Structured Concurrency, Vector API, API bảo mật hoặc thay đổi của JVM.

1. **Chốt phiên bản và nhà cung cấp.** Ghi rõ JDK đang đọc là 26, 27 hay một phiên bản khác; phân biệt Java SE version với số bản cập nhật như `27.0.1.1`. Nếu vấn đề phụ thuộc implementation, ghi thêm nhà cung cấp, hệ điều hành và kiến trúc CPU.
2. **Đọc mục tương ứng trong Release Notes.** Xác định thay đổi nằm ở ngôn ngữ, thư viện, bảo mật, công cụ hay JVM. Đọc cả phần Important Changes, Removed, Deprecated, Known Issues và Differences Between Oracle JDK and OpenJDK nếu có liên quan.
3. **Mở JEP được liên kết.** Đọc động cơ, phạm vi, giới hạn, phương án thay thế và trạng thái. JEP giải thích thiết kế; việc JEP được đề xuất hoặc chấp thuận không tự chứng minh tính năng đã có trong một JDK phát hành.
4. **Đối chiếu tài liệu chuẩn.** Với thay đổi ngôn ngữ, đọc JLS và Java Language Updates. Với thay đổi API, mở đúng module và lớp trong API Docs. Với bytecode hoặc runtime, đọc JVMS và Tool Specifications.
5. **Kiểm tra trạng thái tính năng.** Tìm nhãn Preview, Incubator, Deprecated hoặc Removed; kiểm tra tính năng xuất hiện ở release nào và có tiếp tục thay đổi ở release sau không.
6. **Đọc ghi chú tương thích và kiểm chứng.** Phân loại rủi ro source, binary hay behavioral; dùng toolchain của phiên bản đích, kiểm tra thư viện bên thứ ba và chạy test trên runtime mục tiêu.

Nếu cần so sánh Java 25 với Java 26, hãy dùng phần API Specification có chú giải khác biệt (annotated API specification) và danh sách CSR đã được duyệt của release. Cách này giúp nhận ra chính xác API nào được thêm, đổi hoặc đánh dấu deprecation, thay vì chỉ dựa vào bản tóm tắt tính năng. [Ghi chú JDK 26](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html).

## 3. Cách đọc một trang API Docs

Đừng dừng ở phần mô tả ngắn trong bảng Method Summary. Mở chi tiết của lớp và phương thức để kiểm tra toàn bộ điều kiện sử dụng.

1. **Module và package:** xác định API thuộc Java SE hay JDK, và module nào cần được ứng dụng đọc.
2. **Khai báo và chữ ký:** xem kiểu trả về, generic type, modifier, tham số và interface được triển khai. Chữ ký cho biết cách gọi; phần mô tả mới cho biết ý nghĩa.
3. **Mô tả hành vi:** đọc các điều kiện trước, kết quả, trạng thái sau lời gọi, trường hợp lỗi và giới hạn. Nếu có `Implementation Requirements`, đây là yêu cầu mà implementation phải đáp ứng.
4. **Parameters, Returns và Throws:** xác minh ý nghĩa từng tham số, giá trị trả về và ngoại lệ được ném. Không tự giả định rằng một phương thức bất đồng bộ sẽ ném mọi lỗi trực tiếp tại điểm gọi; lỗi có thể được biểu diễn qua đối tượng kết quả bất đồng bộ.
5. **Since:** cho biết API element được giới thiệu từ phiên bản nào. `Since: 26` không có nghĩa mọi runtime đang chạy ứng dụng đều là Java 26; nó chỉ cho biết mốc xuất hiện của element.
6. **API Note và Implementation Note:** API Note cung cấp giải thích hoặc hướng dẫn. Implementation Note mô tả chi tiết của implementation được tài liệu nói đến; không tự nâng chi tiết đó thành cam kết chung cho mọi JDK.
7. **Deprecated:** đọc lý do deprecate, phiên bản bắt đầu deprecate, có ý định loại bỏ hay không và API thay thế được đề xuất.

### Ví dụ: đọc API `HttpClient` và HTTP/3

Trong JDK 26, Release Notes nêu HTTP/3 cho HTTP Client API và liên kết tới JEP 517. Khi mở [`java.net.http.HttpClient`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html), hãy đọc phần mô tả lớp, builder, `HttpClient.Version`, các option và phần chọn protocol version.

Tài liệu cho biết implementation mặc định hỗ trợ HTTP/1.1, HTTP/2 và HTTP/3. Tuy nhiên, HTTP/3 không tự động được chọn làm mặc định; ứng dụng phải đặt phiên bản ưu tiên hoặc option phù hợp. HTTP/3 chỉ dùng với URI scheme `https`, và implementation mặc định không dùng HTTP/3 khi có proxy. Cấu hình `SSLContext` hoặc `SSLParameters` cũng có thể khiến client không hỗ trợ HTTP/3 và phát sinh `UnsupportedProtocolVersionException`.

Đây là cách đọc một hợp đồng API có ích: tách riêng việc API có khả năng hỗ trợ protocol, cách yêu cầu protocol, điều kiện mạng/TLS và hành vi khi implementation không đáp ứng. Câu “Java 26 hỗ trợ HTTP/3” không đồng nghĩa mọi request sẽ luôn chạy bằng HTTP/3. Khi triển khai, cần kiểm tra server, proxy, TLS, cấu hình client và protocol thực tế trên môi trường đích.

### Đọc nhãn `@since` và `@Deprecated`

`@since` cho biết mốc API được giới thiệu. Với API bị deprecate, đọc cả annotation `@Deprecated` và phần mô tả `@deprecated` trong Javadoc:

```java
@Deprecated(since = "26", forRemoval = true)
public void oldOperation() { }
```

- `since` cho biết phiên bản mà element được đánh dấu deprecated.
- `forRemoval = true` thể hiện ý định loại bỏ element trong một phiên bản tương lai; hãy lên kế hoạch chuyển đổi.
- `forRemoval = false` vẫn có nghĩa không nên dùng API đó cho mã mới, nhưng tại thời điểm đánh dấu chưa có ý định loại bỏ cụ thể.
- Phần `@deprecated` nên giải thích lý do và chỉ ra API thay thế. Đọc kỹ khác biệt ngữ nghĩa trước khi thay thế, vì API mới có thể không tương đương hoàn toàn.

Deprecated không có nghĩa API đã bị xóa ở release hiện tại. Muốn biết API còn tồn tại hay đã bị loại bỏ, hãy kiểm tra API Docs và mục Removed APIs trong Release Notes của phiên bản đích. [Tài liệu `Deprecated`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Deprecated.html).

## 4. Phân biệt tính năng chính thức, Preview và Incubator

Đây là bước bắt buộc khi học các tính năng mới của Java 26. Một tính năng có thể được giới thiệu trong release notes nhưng vẫn chưa phải API hoặc cú pháp ổn định.

| Trạng thái | Ý nghĩa | Cách sử dụng và quyết định |
|---|---|---|
| **Final / Permanent** | Đã trở thành một phần ổn định của đặc tả hoặc API ở release tương ứng. | Dùng theo hợp đồng được mô tả; vẫn phải kiểm tra yêu cầu runtime và tương thích như mọi API khác. |
| **Preview** | Đã được đặc tả và triển khai để lấy phản hồi, nhưng còn tạm thời; có thể thay đổi, tiếp tục preview hoặc bị rút lại. | Phải bật preview khi biên dịch và chạy bằng đúng release. Chỉ dùng khi chấp nhận rủi ro thay đổi và có kế hoạch chuyển đổi. |
| **Incubator** | API hoặc công cụ thử nghiệm được cung cấp qua module/package riêng của JDK. | Thường cần thêm module tường minh, API có thể thay đổi đáng kể hoặc bị bỏ; cô lập việc sử dụng và tránh tạo phụ thuộc lâu dài. |
| **Deprecated** | API vẫn có thể dùng nhưng đã bị khuyến cáo không nên dùng. | Đọc lý do, API thay thế và `forRemoval`; xử lý cảnh báo trước khi nâng cấp tiếp. |
| **Removed** | API, công cụ hoặc tùy chọn đã bị loại khỏi release. | Tìm hướng thay thế trong Release Notes và Migration Guide; mã nguồn hoặc lệnh khởi động còn phụ thuộc có thể không biên dịch hoặc khởi chạy được. |

Preview và incubator là hai trạng thái khác nhau. Preview có thể là tính năng ngôn ngữ, VM hoặc API; trạng thái và giới hạn của nó được ghi trong tài liệu release. Incubator thường được nhận diện qua module riêng, ví dụ `jdk.incubator.vector`. Không dùng `--enable-preview` như một cách bật mọi tính năng thử nghiệm: incubator module có cơ chế module riêng và thường cần `--add-modules`.

### Preview gắn với release

Với tính năng preview của Java 26, dùng `javac` của JDK 26 và bật preview khi biên dịch; khi chạy cũng phải bật preview trên JDK 26:

```bash
# Biên dịch mã dùng preview feature của Java 26
javac --release 26 --enable-preview -d out src/example/Main.java

# Chạy bằng JDK 26 và bật preview
java --enable-preview -cp out example.Main
```

Hai bước phải cùng bật preview. Class file sử dụng preview feature bị gắn với release đã biên dịch; JVM của release khác không được phép nạp class file preview đó, kể cả khi runtime mới cũng bật preview. Do đó, bytecode dùng preview của Java 26 không phải một artifact có thể chuyển nguyên trạng sang Java 27. Muốn thử lại trên Java 27, hãy biên dịch lại bằng JDK 27 và kiểm tra phiên bản preview mới của tính năng.

Ví dụ, Primitive Types in Patterns, `instanceof`, and `switch` là **preview lần thứ tư** trong Java 26 (JEP 530). Sang Java 27, tính năng này vẫn là preview lần thứ năm (JEP 532). Đây là bằng chứng thực tế rằng số lần preview không phải nhãn trang trí: thiết kế và quy tắc có thể tiếp tục thay đổi giữa các release. [Java Language Changes Summary 26](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-summary.html) · [Java Language Changes Summary 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html) · [JVMS 26, phần Preview Features](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-1.html).

### Incubator module và Vector API

Vector API của Java 26 là **Incubator lần thứ mười một** (JEP 529), được cung cấp trong module `jdk.incubator.vector`. Trong Java 27, API tiếp tục là **Incubator lần thứ mười hai** (JEP 537). Vì đây là module incubator, hãy kiểm tra đúng API Docs của release, thêm module khi biên dịch/chạy và cô lập phần mã phụ thuộc vào nó. Không xem việc module có mặt trong JDK API Docs là bằng chứng rằng nó đã trở thành Java SE API ổn định.

```bash
# Ví dụ cấu hình module incubator cho JDK 26
javac --release 26 --add-modules jdk.incubator.vector -d out src/example/VectorDemo.java
java --add-modules jdk.incubator.vector -cp out example.VectorDemo
```

Khi cân nhắc sử dụng lâu dài, hãy kiểm tra lại trạng thái ở release hiện hành, xem thay đổi API giữa các release và đánh giá xem có thể thay thế bằng API chuẩn hoặc triển khai riêng hay không. [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) · [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html).

### Một số ví dụ trạng thái trong Java 26 và Java 27

| Chủ đề | Trạng thái trong Java 26 | Trạng thái trong Java 27 | Điều cần rút ra |
|---|---|---|---|
| HTTP/3 trong HTTP Client API | API được bổ sung cho `java.net.http`; release notes không đánh dấu là preview. | API tiếp tục có trong tài liệu Java 27. | Đây là API Java SE; vẫn phải đọc điều kiện chọn protocol, TLS và proxy trong API Docs. |
| Primitive types trong patterns, `instanceof`, `switch` | Preview lần thứ tư. | Preview lần thứ năm. | Chưa phải cú pháp ổn định; phải bật preview và biên dịch lại theo release. |
| Structured Concurrency | Preview API lần thứ sáu. | Preview API lần thứ bảy. | Chưa nên xem API là hợp đồng ổn định giữa các release. |
| Vector API | Incubator lần thứ mười một trong `jdk.incubator.vector`. | Incubator lần thứ mười hai. | Đây là JDK incubator module, cần kiểm tra thay đổi API và module khi nâng cấp. |
| PEM Encodings of Cryptographic Objects | Preview API lần thứ hai. | Preview API lần thứ ba. | Với API bảo mật preview, phải kiểm tra cả trạng thái tính năng lẫn chính sách bảo mật của runtime triển khai. |

Bảng này ghi rõ release để tránh hiểu nhầm trạng thái của một tính năng ở Java 26 là trạng thái của Java hiện hành. Trước khi chọn API cho dự án, luôn mở release notes và API Docs của đúng JDK mục tiêu.

## 5. Đọc ghi chú tương thích khi nâng cấp

Release Notes của JDK 26 phân biệt ba loại tương thích chính:

| Loại tương thích | Câu hỏi cần trả lời | Ví dụ rủi ro |
|---|---|---|
| **Source compatibility** | Mã nguồn cũ có biên dịch được mà không cần sửa không? | Một khai báo hoặc cách gọi API không còn hợp lệ với compiler mới. |
| **Binary compatibility** | Class file đã biên dịch có thể liên kết với thư viện/runtime mới mà không lỗi không? | Một phương thức hoặc kiểu mà bytecode tham chiếu đã bị loại bỏ hoặc thay đổi không tương thích. |
| **Behavioral compatibility** | Chương trình có giữ nguyên ý nghĩa và kết quả khi chạy không? | Chương trình vẫn biên dịch và liên kết, nhưng kết quả định dạng ngày/tiền tệ, lựa chọn protocol hoặc hành vi mặc định thay đổi. |

Một lần nâng cấp có thể giữ được source compatibility nhưng vẫn có behavioral change. Vì vậy, “biên dịch thành công” không đủ để kết luận ứng dụng đã tương thích. Cần chạy test tích hợp và kiểm tra hành vi thực tế. [JDK 26 Release Notes — Kinds of Compatibility](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html).

### Những mục cần rà soát trong Release Notes

- **Major New Functionality / New Features:** hiểu tính năng mới và giới hạn sử dụng.
- **Important Changes and Information:** tìm thay đổi mặc định, hành vi thư viện, JVM và bảo mật có thể tác động dù không đổi chữ ký API.
- **Removed Features and Options:** kiểm tra API, công cụ, module hoặc tùy chọn JVM đã bị xóa.
- **Deprecated Features and Options:** xác định phần nào cần thay thế trước một lần nâng cấp tiếp theo.
- **Known Issues:** kiểm tra lỗi đã biết có liên quan tới hệ điều hành, kiến trúc, GC, TLS hoặc thư viện đang dùng.
- **Differences Between Oracle JDK and OpenJDK:** xác minh khác biệt implementation nếu hệ thống dùng nhiều bản phân phối.
- **Security Updates:** kiểm tra bản vá, thuật toán, chứng thư, TLS và security properties theo chính sách triển khai.

Với thay đổi API, đối chiếu API diff và CSR. Với thay đổi hành vi hoặc tùy chọn JVM, đọc phần ghi chú chi tiết và hướng dẫn migration. Nếu nâng cấp qua nhiều feature release, đọc release notes của từng release trung gian; không chỉ so sánh phiên bản ban đầu với phiên bản cuối.

### Dùng Migration Guide và công cụ kiểm tra

Migration Guide đưa ra quy trình thực tế: chạy ứng dụng trên JDK đích, cập nhật thư viện/công cụ, biên dịch lại khi cần, phân tích phụ thuộc và kiểm tra test. Với JDK hiện đại, dùng `--release` để chỉ định phiên bản Java mà sản phẩm cần hỗ trợ:

```bash
# Biên dịch bằng JDK mới nhưng giới hạn ngôn ngữ, bytecode và API theo Java 26
javac --release 26 -d out src/example/Main.java
```

`--release 26` giúp compiler kiểm tra mã theo quy tắc ngôn ngữ, class file và API của Java 26. Nó không kiểm tra thay cho bạn các thư viện bên thứ ba, hành vi khi chạy, cấu hình hệ điều hành hoặc sự khác biệt giữa các nhà cung cấp JDK. Không dùng riêng một tùy chọn tạo bytecode cũ để kết luận API tương thích; cần giới hạn cả API nền tảng theo release mục tiêu.

Dùng `jdeps` để phát hiện phụ thuộc tới API nội bộ của JDK:

```bash
jdeps -jdkinternals application.jar
```

Nếu kết quả cho thấy phụ thuộc vào internal APIs, tìm API được hỗ trợ thay thế và loại bỏ phụ thuộc đó. `jdeps` là phân tích tĩnh nên không phát hiện đầy đủ trường hợp truy cập bằng reflection; cần kết hợp kiểm tra mã nguồn, cấu hình và test runtime. Migration Guide cũng khuyến nghị nâng cấp thư viện, plugin build và IDE lên phiên bản hỗ trợ JDK mục tiêu.

Đối với tính năng preview, `--release` phải khớp release của preview và `--enable-preview` cần có ở cả compile lẫn runtime. Đối với incubator module, kiểm tra tên module và dùng `--add-modules` theo tài liệu của release đó. Đừng đưa cờ preview hoặc incubator vào cấu hình production chỉ để làm cho build qua; trước tiên phải quyết định rõ việc chấp nhận API chưa ổn định và cách quản lý rủi ro.

## 6. Kiểm chứng theo từng nhóm chủ đề của Java 26

Khi đọc các cải tiến được giới thiệu trong module Java 26, hãy áp dụng đúng bộ tài liệu cho từng nhóm:

- **HTTP và mạng:** đọc Release Notes, JEP liên quan, API Docs của `java.net.http`, phần protocol selection, TLS, proxy, timeout, cancellation và xử lý response body. Kiểm tra bằng server và mạng tương tự môi trường thật.
- **Pattern matching:** đọc Java Language Updates và JLS của đúng release; kiểm tra bảng Preview Features trước khi dùng primitive patterns. Các pattern đã final ở release trước vẫn có thể dùng mà không bật preview; phần primitive patterns của Java 26 vẫn cần bật preview.
- **Structured Concurrency:** đọc JEP và API Docs của preview API, chú ý vòng đời task, cancellation, exception, shutdown và giới hạn của từng preview. Không suy luận rằng API ở lần preview thứ sáu có chữ ký giống lần thứ bảy.
- **Vector API:** đọc module `jdk.incubator.vector`, điều kiện module và tài liệu kiến trúc CPU. Đo hiệu năng trên workload thực tế; khả năng vector hóa và lợi ích phụ thuộc phần cứng, dữ liệu và cách viết phép tính.
- **Bảo mật:** đọc Release Notes, Security Updates, API Docs và tài liệu thuật toán/thuộc tính bảo mật. Kiểm thử handshake TLS, trust store, chứng thư, provider và cấu hình triển khai; không suy luận một thuật toán được hỗ trợ đồng nghĩa nó được bật trong mọi cấu hình.
- **Tối ưu JVM:** đọc ghi chú thay đổi GC, JIT, AOT, class loading và tùy chọn VM. Đối chiếu cờ JVM đang dùng với danh sách obsolete/removed; đo bằng workload đại diện, cùng cấu hình heap, GC, CPU và dữ liệu. Một mô tả tối ưu trong release notes là thông tin về thay đổi, không phải cam kết ứng dụng sẽ nhanh hơn trong mọi môi trường.

Với các thay đổi hiệu năng, ghi lại số liệu trước và sau nâng cấp: throughput, latency theo percentile, CPU, heap, allocation, pause time và thời gian khởi động. Dùng công cụ quan sát như JDK Flight Recorder khi phù hợp. Tránh thay đổi đồng thời JDK, GC flags, thư viện và tải thử nghiệm vì sẽ khó xác định nguyên nhân của chênh lệch.

## 7. Checklist trước khi chấp nhận một API hoặc nâng cấp JDK

- [ ] Đã ghi rõ Java SE/JDK release, số bản cập nhật, nhà cung cấp, hệ điều hành và kiến trúc triển khai.
- [ ] Đã mở tài liệu có version trùng với release cần xác minh.
- [ ] Đã xác định nguồn phù hợp: JLS, JVMS, Java SE API, JDK API, Tool Specification, JEP hay Release Notes.
- [ ] Đã kiểm tra module/package để biết API thuộc Java SE hay JDK-specific.
- [ ] Đã xác minh trạng thái Final, Preview, Incubator, Deprecated hoặc Removed.
- [ ] Nếu là Preview, đã dùng đúng JDK release và bật preview khi biên dịch lẫn chạy.
- [ ] Nếu là Incubator, đã kiểm tra module, cờ module và thay đổi giữa các release.
- [ ] Đã đọc mô tả chi tiết, `Since`, `Throws`, API Note, Implementation Note và thông tin deprecation của API liên quan.
- [ ] Đã phân loại rủi ro source, binary và behavioral; đã đọc các mục Removed, Deprecated, Known Issues và Security Updates.
- [ ] Đã biên dịch theo phiên bản mục tiêu bằng `--release`, kiểm tra internal API bằng `jdeps` và cập nhật thư viện/công cụ.
- [ ] Đã chạy test tích hợp, test bảo mật và benchmark phù hợp trên runtime gần với môi trường triển khai.
- [ ] Đã xác nhận JDK mục tiêu còn được nhà cung cấp hỗ trợ và đã có kế hoạch cập nhật bản vá bảo mật.

## Tài liệu tham khảo chính thức

- [Java SE 26 & JDK 26 Specifications](https://docs.oracle.com/en/java/javase/26/docs/specs/index.html)
- [Java Language Specification — Java SE 26](https://docs.oracle.com/javase/specs/jls/se26/html/)
- [Java Virtual Machine Specification — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/index.html)
- [Java SE & JDK 26 API Specification](https://docs.oracle.com/en/java/javase/26/docs/api/index.html)
- [Java Language Updates — Release 26](https://docs.oracle.com/en/java/javase/26/language/index.html)
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [Oracle JDK Migration Guide — Release 26](https://docs.oracle.com/en/java/javase/26/migrate/index.html)
- [Preparing for Migration](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html)
- [The `javac` Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Java Language Changes Summary — Release 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [JDK Releases and Support Timeline](https://ops.java/releases/?lang=en)

*Cập nhật nội dung: 27-11-2026. Trạng thái tính năng và chính sách hỗ trợ có thể thay đổi theo release hoặc nhà cung cấp; hãy kiểm tra lại tài liệu phiên bản đích trước khi triển khai.*
