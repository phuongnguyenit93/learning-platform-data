# Phân biệt tính năng chính thức, preview và incubator

Khi đọc tài liệu Java 26, bạn sẽ gặp các nhãn như *Fourth Preview*, *Second Preview* và *Eleventh Incubator*. Những nhãn này cho biết mức độ ổn định và cách sử dụng của từng tính năng. Chúng không nói rằng JDK phát hành chưa chính thức: JDK 26 đã là bản phát hành GA, nhưng bên trong bản phát hành đó vẫn có các tính năng đang thử nghiệm.

Phạm vi bài học là trạng thái tính năng trong JDK 26, đồng thời cập nhật vòng đời đến JDK 27 — bản Java mới nhất tại ngày 27/11/2026. JDK 25 hiện là bản LTS mới nhất. Vì vậy, khi chọn API cho dự án, hãy kiểm tra cả phiên bản JDK mục tiêu lẫn trạng thái hiện tại của JEP.

## 1. Phân biệt bản phát hành và trạng thái tính năng

JDK 26 GA có nghĩa Oracle/OpenJDK đã phát hành bộ JDK 26 để sử dụng. Điều đó không biến mọi tính năng được đóng gói trong JDK 26 thành API ổn định. Một bản phát hành có thể chứa đồng thời:

- Tính năng đã hoàn tất và được hỗ trợ như một phần ổn định của nền tảng hoặc JDK.
- Tính năng preview: đã được thiết kế và triển khai đủ để dùng thử, nhưng vẫn có thể thay đổi hoặc bị rút lại.
- API incubator: API đang được thử nghiệm qua một module riêng, có thể đổi thiết kế hoặc bị loại bỏ.

Trong giao tiếp hằng ngày, mọi người đôi khi gọi tính năng đã hoàn tất là “chính thức”. Tuy nhiên, “chính thức” không phải nhãn vòng đời chính xác của JEP. Trong bài này, thuật ngữ **đã final / ổn định** chỉ tính năng không còn mang trạng thái Preview hoặc Incubator trong bản phát hành được xét. Một JEP đã final cũng không nhất thiết tạo ra API Java SE: có JEP thay đổi JVM, garbage collector hoặc công cụ của JDK.

## 2. Ba trạng thái cần nhận biết

| Tiêu chí | Đã final / ổn định | Preview | Incubator |
| --- | --- | --- | --- |
| Mục đích | Cung cấp tính năng đã hoàn tất cho sử dụng thông thường | Cho cộng đồng dùng thử một thiết kế đã được đặc tả và triển khai, rồi gửi phản hồi | Đưa API hoặc công cụ chưa đủ ổn định ra dùng thử sớm |
| Phạm vi thường gặp | Ngôn ngữ, API Java SE, API JDK, JVM hoặc công cụ | Tính năng ngôn ngữ, JVM hoặc API preview | API và công cụ JDK trong module incubator |
| Trạng thái | Đã final trong phiên bản đó | Tạm thời; có thể preview tiếp, được final hoặc bị rút | Tạm thời; có thể thay đổi, được final hoặc bị loại bỏ |
| Cách bật | Dùng như tính năng thông thường, theo yêu cầu phiên bản JDK | Phải bật ở cả lúc biên dịch và chạy bằng `--enable-preview` | Phải đưa module vào module graph, thường bằng `--add-modules` |
| Rủi ro nâng cấp | Thấp hơn; vẫn phải kiểm tra thay đổi tương thích của từng bản JDK | Mã phụ thuộc preview gắn với đúng phiên bản Java đã biên dịch | Tên module, package, chữ ký API hoặc cách hoạt động có thể đổi giữa các bản JDK |
| Cách dùng phù hợp | Ứng dụng và thư viện thông thường | Thử nghiệm có kiểm soát, đánh giá thiết kế và chuẩn bị nâng cấp | Thử nghiệm API, đo hiệu năng và làm proof of concept |

### Tính năng đã final

Tính năng đã final không cần cờ preview. Nếu đó là API Java SE, API đã trở thành một phần ổn định của đặc tả Java SE ở phiên bản tương ứng. Nếu đó là cải tiến JVM hoặc công cụ JDK, nó có thể là tính năng ổn định của bản JDK mà không phải API Java SE.

Ví dụ trong JDK 26:

- **JEP 517 — HTTP/3 for the HTTP Client API:** bổ sung hỗ trợ HTTP/3 cho HTTP Client API. Release Notes không gắn nhãn Preview hoặc Incubator cho JEP này.
- **JEP 522 — G1 GC: Improve Throughput by Reducing Synchronization:** giảm đồng bộ giữa luồng ứng dụng và luồng GC để cải thiện throughput của G1.
- **JEP 516 — Ahead-of-Time Object Caching with Any GC:** mở rộng AOT object cache để dùng được với các garbage collector khác nhau, bao gồm ZGC.

Đây là các ví dụ đã final trong JDK 26. Chúng không cần `--enable-preview`. Dù vậy, vẫn phải kiểm tra tài liệu API, điều kiện nền tảng và ghi chú tương thích khi nâng cấp JDK.

### Tính năng Preview

Preview là tính năng đã có thiết kế và triển khai đủ để cộng đồng đánh giá bằng tình huống thực tế, nhưng chưa được cam kết là dạng cuối cùng. Sau một hoặc nhiều vòng preview, tính năng có thể được tinh chỉnh rồi final, tiếp tục preview, hoặc bị rút khỏi JDK.

Trong JDK 26 có bốn JEP preview tiêu biểu:

| JEP trong JDK 26 | Tính năng | Vòng preview |
| --- | --- | --- |
| JEP 530 | Primitive Types in Patterns, `instanceof`, and `switch` | Lần thứ tư |
| JEP 526 | Lazy Constants | Lần thứ hai |
| JEP 525 | Structured Concurrency | Lần thứ sáu |
| JEP 524 | PEM Encodings of Cryptographic Objects | Lần thứ hai |

Ví dụ, Primitive Types in Patterns mở rộng pattern matching để hỗ trợ kiểu nguyên thủy trong các ngữ cảnh pattern, `instanceof` và `switch`. Dù đã được preview nhiều lần, tính năng này vẫn là preview trong JDK 26; số lần preview không tự động biến nó thành API ổn định.

Để thử một preview feature của Java 26, dùng JDK 26 cho cả biên dịch và chạy:

```bash
# Biên dịch mã có sử dụng preview feature của Java 26
javac --enable-preview --release 26 -d out src/Main.java

# Chạy bằng JDK 26 và bật preview ở runtime
java --enable-preview -cp out Main
```

Hai bước đều cần `--enable-preview`. Chỉ bật ở compiler hoặc chỉ bật ở runtime đều chưa đủ. Cờ này bật nhóm preview feature của bản phát hành đang dùng; không có cơ chế chọn bật riêng một preview feature.

Class file sử dụng preview feature của Java 26 gắn với Java 26. Nó không thể được nạp bằng một bản Java khác, kể cả khi bản mới hơn cũng bật `--enable-preview`. Khi chuyển sang JDK mới, hãy đọc JEP tương ứng, cập nhật mã theo phiên bản preview mới và biên dịch lại.

### API Incubator

Incubator chủ yếu dành cho API và công cụ JDK cần thêm thời gian thử nghiệm trước khi chốt thiết kế. Các module incubator thường có tiền tố `jdk.incubator.`. Chúng thuộc phạm vi JDK, không phải API Java SE tiêu chuẩn; tài liệu API của module sẽ ghi rõ trạng thái incubating.

Ví dụ của Java 26 là **JEP 529 — Vector API (Eleventh Incubator)**. Vector API cho phép biểu diễn phép tính theo vector/SIMD để JVM có thể biên dịch thành chỉ thị vector phù hợp với CPU hỗ trợ. API nằm trong module `jdk.incubator.vector` và vẫn được ghi rõ là incubating trong Java 26 API Specification.

Với chương trình chạy trên classpath, cần thêm module lúc biên dịch và lúc chạy:

```bash
# Biên dịch mã dùng Vector API của JDK 26
javac --add-modules jdk.incubator.vector -d out src/Main.java

# Chạy và đưa module incubator vào module graph
java --add-modules jdk.incubator.vector -cp out Main
```

Nếu ứng dụng là named module, khai báo phụ thuộc trong `module-info.java`:

```java
module com.example.app {
    requires jdk.incubator.vector;
}
```

`--add-modules` và `--enable-preview` giải quyết hai việc khác nhau. Vector API trong Java 26 là incubator, nên cần module incubator; không bật preview chỉ vì API này chưa final. Khi biên dịch hoặc chạy, JDK có thể phát cảnh báo incubator — đây là dấu hiệu cần chú ý khi đánh giá rủi ro nâng cấp.

## 3. Trạng thái của các tính năng Java 26 khi chuyển sang Java 27

Một tính năng có thể tiếp tục mang trạng thái tạm thời qua nhiều bản JDK. Theo JDK 27 Release Notes, các tính năng sau vẫn chưa final:

| Tính năng | Trạng thái trong JDK 26 | Trạng thái trong JDK 27 |
| --- | --- | --- |
| Primitive Types in Patterns, `instanceof`, and `switch` | JEP 530 — Preview lần 4 | JEP 532 — Preview lần 5 |
| Lazy Constants | JEP 526 — Preview lần 2 | JEP 531 — Preview lần 3 |
| Structured Concurrency | JEP 525 — Preview lần 6 | JEP 533 — Preview lần 7 |
| PEM Encodings of Cryptographic Objects | JEP 524 — Preview lần 2 | JEP 538 — Preview lần 3 |
| Vector API | JEP 529 — Incubator lần 11 | JEP 537 — Incubator lần 12 |

Điều này cho thấy không nên suy luận “đã preview nhiều lần thì chắc sắp final”. Trạng thái chỉ thay đổi khi JEP và tài liệu của bản phát hành mới xác nhận điều đó. Nếu dự án nâng từ Java 26 lên Java 27, hãy xem lại cả số JEP lẫn chữ ký API; không giả định mã preview hoặc incubator của Java 26 sẽ dùng nguyên trạng trên Java 27.

## 4. Chọn trạng thái phù hợp cho dự án

- **Ứng dụng production hoặc thư viện công khai:** ưu tiên API đã final. Với preview hoặc incubator, chỉ đưa vào khi nhóm chấp nhận chi phí cập nhật, kiểm thử tương thích và khả năng phải thay thế API.
- **Đánh giá một thiết kế ngôn ngữ hoặc API mới:** preview phù hợp để thử nghiệm trên đúng JDK mục tiêu. Đặt cờ preview rõ ràng trong cấu hình build và runtime; không để cờ chỉ tồn tại trên máy lập trình viên.
- **Thử nghiệm API hiệu năng hoặc công cụ mới:** incubator phù hợp cho benchmark và proof of concept. Đóng gói module cần thiết, kiểm thử trên các kiến trúc CPU mục tiêu và chuẩn bị phương án thay thế nếu API thay đổi hoặc bị loại bỏ.
- **Nâng cấp JDK:** kiểm tra Release Notes, JEP và API Specification của cả phiên bản hiện tại lẫn phiên bản đích. Xác nhận lại cờ compiler, cờ runtime, module requirements và thư viện phụ thuộc.

Một quy trình kiểm tra ngắn trước khi dùng tính năng mới:

1. Xác định JDK thực tế của compiler và runtime bằng `javac --version` và `java --version`.
2. Tra JEP của tính năng và xem nhãn trong Release Notes của đúng phiên bản JDK.
3. Nếu là Preview, bật `--enable-preview` ở cả biên dịch và chạy, rồi khóa đúng JDK tương ứng.
4. Nếu là Incubator, xác định module `jdk.incubator.*` và thêm module ở cả môi trường biên dịch lẫn runtime.
5. Trước khi phát hành hoặc nâng cấp, kiểm thử lại trên JDK đích và xác nhận tính năng đã final hay vẫn còn provisional.

## 5. Ghi nhớ

- **GA của JDK** xác nhận bản JDK đã phát hành; nó không xác nhận mọi tính năng bên trong đều final.
- **Preview** là tính năng đã được đặc tả và triển khai để lấy phản hồi; bật bằng `--enable-preview` ở cả compile time và run time.
- **Incubator** là API/công cụ JDK đang thử nghiệm trong module riêng; thêm module bằng `--add-modules`.
- **Final** mới là trạng thái phù hợp để mặc định xây dựng phụ thuộc dài hạn. Vẫn phải xét phạm vi Java SE hay JDK và yêu cầu phiên bản tối thiểu.
- Số vòng preview/incubator chỉ là lịch sử lặp lại, không phải thước đo đảm bảo rằng lần kế tiếp sẽ final.

## Tài liệu tham khảo

- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html) — danh sách JEP và trạng thái tính năng của Java 26.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — xác minh các preview và incubator tiếp tục trong Java 27.
- [Java Language Changes Summary, Java SE 26](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-summary.html) — phân biệt ngôn ngữ đã permanent và preview.
- [Java SE 26 API Specification Overview](https://docs.oracle.com/en/java/javase/26/docs/api/overview-summary.html) — phân biệt API Java SE trong module `java.*` và API JDK trong module `jdk.*`.
- [Java Virtual Machine Specification, Java SE 26 — Preview Features](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-1.html) — quy tắc bật preview và giới hạn tương thích class file.
- [The `javac` Command, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — tùy chọn `--enable-preview`, `--release` và `--add-modules`.
- [Package `jdk.incubator.vector`, Java SE 26 & JDK 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html) — trạng thái incubator và API Vector.
- [JEP 11 — Incubator Modules](https://openjdk.org/jeps/11) và [JEP 12 — Preview Features](https://openjdk.org/jeps/12) — cơ chế vòng đời của incubator và preview.
