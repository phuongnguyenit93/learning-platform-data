# Phân biệt tính năng chính thức, preview, incubator và experimental

Trong hệ sinh thái Java, một tính năng mới có thể được đưa vào JDK để nhà phát triển thử nghiệm trước khi trở thành một phần ổn định của nền tảng. Bốn nhãn thường gặp là **final/permanent (chính thức, ổn định)**, **preview**, **incubator** và **experimental**. Chúng mô tả mức độ hoàn thiện, phạm vi kỹ thuật và cách bật tính năng; chúng không phải bốn cấp phiên bản Java.

Điểm quan trọng khi học Java 27 là **mỗi tính năng có vòng đời riêng**. JDK 27 đã là bản phát hành GA, nhưng bên trong JDK 27 vẫn có những tính năng preview và incubator. Vì vậy, không thể kết luận rằng mọi tính năng có trong một bản JDK GA đều đã ổn định hoặc được bảo đảm tương thích lâu dài.

Nội dung dưới đây lấy JDK 27 làm mốc. Oracle công bố JDK 27 GA ngày 15-09-2026; bản cập nhật Oracle JDK mới nhất có release notes tại thời điểm 27-11-2026 là 27.0.1.1, phát hành ngày 17-11-2026.

## 1. Trước hết: “chính thức” nghĩa là gì?

Trong tài liệu Java, cách gọi chính xác thường là **final** hoặc **permanent**: tính năng đã rời giai đoạn thử nghiệm và được đưa vào bề mặt sản phẩm ổn định tương ứng. “Chính thức” là cách gọi thông dụng, không phải một nhãn vòng đời độc lập do JEP 12 định nghĩa.

Cần phân biệt ba phạm vi:

| Phạm vi | Ý nghĩa | Khả năng tương thích |
| --- | --- | --- |
| **Java SE** | Ngôn ngữ Java, JVM và API thuộc đặc tả Java SE. Các module API cốt lõi thường có tên bắt đầu bằng **java.** | Các bản triển khai Java SE tuân thủ đặc tả phải cung cấp hành vi và API được đặc tả. Đây là lựa chọn phù hợp nhất khi cần tính di động giữa các nhà cung cấp. |
| **JDK** | API và công cụ dành riêng cho JDK, thường nằm trong module có tên bắt đầu bằng **jdk.** | Có thể là chức năng ổn định của JDK nhưng không nhất thiết có trong mọi bản triển khai Java SE. |
| **HotSpot** | Chức năng riêng của máy ảo HotSpot, chẳng hạn lựa chọn hoặc tối ưu hóa bộ thu gom rác và cách bố trí đối tượng | Tính khả dụng và hành vi phụ thuộc JVM, nhà cung cấp, hệ điều hành và kiến trúc. Không nên xem đây là API Java SE di động. |

Do đó, một thay đổi có thể đã **final/production trong HotSpot** mà không phải là API Java SE. Tương tự, một API thuộc JDK có thể đã ổn định nhưng vẫn là API riêng của JDK. Khi đánh giá “chính thức”, hãy kiểm tra cả trạng thái vòng đời lẫn phạm vi Java SE, JDK hay HotSpot.

## 2. Preview: hoàn chỉnh để dùng thử, nhưng chưa vĩnh viễn

**Preview feature** là tính năng của ngôn ngữ Java, máy ảo Java hoặc API Java SE đã được đặc tả và triển khai đầy đủ, nhưng vẫn chưa có trạng thái vĩnh viễn. Mục đích là cho cộng đồng dùng thử trong tình huống thực tế, phát hiện vấn đề về thiết kế, khả năng sử dụng và tương tác với tính năng hiện có, rồi gửi phản hồi cho nhóm phát triển.

Một tính năng preview có thể:

- Được đưa ra preview lần tiếp theo, có thể kèm điều chỉnh.
- Trở thành tính năng final/permanent.
- Bị rút khỏi một bản phát hành sau khi đánh giá.

Không có cam kết rằng mọi tính năng preview cuối cùng đều sẽ trở thành tính năng chính thức. Số thứ tự như “Second Preview”, “Fifth Preview” cho biết tính năng đã trải qua bao nhiêu vòng preview, không phải mức độ ổn định hay bảo đảm tương thích.

### Cách bật preview trong Java 27

Preview bị tắt mặc định. Khi biên dịch, dùng compiler của JDK 27 cùng **--enable-preview** và **--release 27** (hoặc **-source 27**). Khi chạy, dùng runtime cùng feature release 27 và cũng bật **--enable-preview**.

    # Biên dịch mã nguồn có dùng preview feature của Java 27
    javac --release 27 --enable-preview -d out src/Main.java

    # Chạy bằng JDK 27 với preview được bật
    java --enable-preview -cp out Main

Hai bước đều cần cờ bật preview. Chỉ bật ở lúc biên dịch hoặc chỉ bật ở lúc chạy đều không đủ. Cờ này áp dụng cho preview features của feature release đang dùng; nó không biến một tính năng incubator hay experimental thành preview.

Preview gắn với **feature release** cụ thể. Mã đã biên dịch dựa trên preview của Java 27 không được kỳ vọng sẽ tiếp tục biên dịch hoặc chạy nguyên trạng trên một feature release mới hơn. Khi nâng JDK, cần đọc lại release notes và điều chỉnh mã theo trạng thái mới của tính năng.

## 3. Incubator: API hoặc công cụ JDK đang được hoàn thiện

**Incubator feature** là API hoặc công cụ JDK chưa đủ chín để được chuẩn hóa hoặc hoàn thiện ngay. Nhóm phát triển đưa nó vào một module incubator để nhà phát triển có thể thử nghiệm, thu thập kinh nghiệm và phản hồi trước khi quyết định tiếp tục hoàn thiện, chuyển sang trạng thái ổn định hoặc loại bỏ.

Theo cơ chế JEP 11, module incubator thường có tên bắt đầu bằng **jdk.incubator.**. Đây là dấu hiệu quan trọng để nhận biết API đang ở giai đoạn incubator. Các API này thuộc phạm vi JDK; không nên mặc định rằng chúng là một phần của Java SE hoặc có mặt trên mọi bản triển khai Java.

### Ví dụ hiện hành trong Java 27: Vector API

JDK 27 đưa **Vector API (JEP 537)** vào vòng **Twelfth Incubator**. API này cho phép biểu diễn phép tính vector để JVM có thể biên dịch thành các lệnh SIMD phù hợp với CPU được hỗ trợ. Module tương ứng là **jdk.incubator.vector**; tài liệu API Java 27 đánh dấu rõ đây là tính năng incubating và có thể bị loại bỏ trong một bản phát hành tương lai.

Với ứng dụng chạy trên classpath, cần yêu cầu module incubator khi biên dịch và khi chạy:

    # Biên dịch
    javac --add-modules jdk.incubator.vector -d out src/Main.java

    # Chạy
    java --add-modules jdk.incubator.vector -cp out Main

Với ứng dụng dạng module, khai báo phụ thuộc trực tiếp trong module-info.java:

    module com.example.app {
        requires jdk.incubator.vector;
    }

Việc khai báo hoặc thêm module là cơ chế opt-in của incubator. **Không dùng --enable-preview để thay cho --add-modules**. Hai cờ phục vụ hai cơ chế khác nhau.

Khi module incubator thay đổi, tên module, package, API hoặc cách sử dụng có thể thay đổi giữa các feature release. Một API incubator cũng có thể bị loại bỏ thay vì trở thành API ổn định. Vì vậy, cần cô lập phần phụ thuộc này trong mã ứng dụng và kiểm tra lại khi nâng JDK.

## 4. Experimental: cơ chế thử nghiệm chủ yếu của HotSpot

**Experimental feature** thường dùng cho các cải tiến có phạm vi bên trong máy ảo HotSpot. Khác với preview và incubator, experimental không có một quy trình vòng đời chung được JEP 12 quản lý. Đây chủ yếu là quy ước của HotSpot để cho phép thử nghiệm một thay đổi VM trước khi quyết định có đưa nó thành chức năng production hay không.

Các tùy chọn experimental của HotSpot bị khóa mặc định. Tùy chọn:

    -XX:+UnlockExperimentalVMOptions

cho phép mở khóa nhóm tùy chọn này. Sau đó, người dùng còn phải chỉ định cờ riêng của tính năng cần thử nghiệm. Mẫu lệnh dưới đây chỉ minh họa vị trí của cờ; **TenFlagExperimental** là chỗ giữ chỗ, không phải tên một tùy chọn Java có thật:

    java -XX:+UnlockExperimentalVMOptions -XX:+TenFlagExperimental -jar app.jar

Tên cờ, kiểu giá trị và việc cờ có tồn tại hay không phụ thuộc phiên bản HotSpot, nhà cung cấp JDK, hệ điều hành và kiến trúc. Tài liệu launcher Java 27 xếp các tùy chọn **-XX** vào nhóm tùy chọn nâng cao riêng của HotSpot; chúng không được bảo đảm hỗ trợ trên mọi JVM. Tài liệu cũng cảnh báo tùy chọn experimental có thể bị gỡ bỏ hoặc thay đổi hành vi mà không cần thông báo trước.

Không nên nhầm experimental với incubator:

- **Experimental** chủ yếu mở đường cho việc thử nghiệm hành vi hoặc tối ưu hóa của HotSpot.
- **Incubator** đưa API hoặc công cụ JDK chưa hoàn thiện ra cho lập trình viên sử dụng qua module incubator.
- **Preview** dành cho tính năng ngôn ngữ, VM hoặc API Java SE đã được đặc tả và triển khai đầy đủ nhưng chưa vĩnh viễn.

Một tính năng HotSpot sau khi được hoàn thiện có thể trở thành chức năng production. Tuy nhiên, điều đó không tự động biến nó thành API Java SE hoặc bảo đảm nó tồn tại trên các JVM khác.

## 5. Bảng so sánh nhanh

| Tiêu chí | Final / permanent | Preview | Incubator | Experimental |
| --- | --- | --- | --- | --- |
| Mục tiêu | Cung cấp chức năng ổn định | Lấy phản hồi cho tính năng Java SE chưa vĩnh viễn | Hoàn thiện API hoặc công cụ JDK | Thử nghiệm thay đổi, chủ yếu trong HotSpot |
| Mức độ hoàn thiện | Đã được chấp nhận vào bề mặt sản phẩm tương ứng | Đặc tả và triển khai đầy đủ, nhưng còn có thể đổi | Chưa đủ kinh nghiệm để chuẩn hóa hoặc hoàn thiện | Đang thử nghiệm; mức độ hoàn thiện tùy tính năng |
| Cơ chế liên quan | Đặc tả Java SE, JDK hoặc bản phát hành HotSpot | JEP 12 | JEP 11 | Quy ước của HotSpot; không có một JEP lifecycle chung |
| Cách nhận biết | Tài liệu đặc tả/API không còn đánh dấu preview hoặc incubating; release notes mô tả là chức năng phát hành | Release notes/Javadoc ghi Preview; có thể có số thứ tự preview | Module thường có tiền tố **jdk.incubator.** và Javadoc ghi Incubating Feature | Tài liệu VM ghi Experimental; có tùy chọn JVM tương ứng |
| Cách bật | Thường dùng như chức năng phát hành thông thường | **--enable-preview** ở cả compile và runtime | **--add-modules** hoặc khai báo **requires** trong module | **-XX:+UnlockExperimentalVMOptions** và cờ riêng nếu cần |
| Tương thích | Theo cam kết của phạm vi sản phẩm: Java SE, JDK hoặc HotSpot | Chỉ gắn với feature release cụ thể; có thể đổi hoặc bị rút | API/module có thể đổi hoặc bị rút giữa các release | Phụ thuộc triển khai HotSpot và có thể đổi/gỡ mà không báo trước |
| Khuyến nghị | Ưu tiên cho mã production | Dùng thử có kiểm soát, kiểm tra lại ở mỗi release | Giới hạn trong thử nghiệm hoặc phần mã có thể thay thế | Chỉ dùng khi hiểu rõ rủi ro và có kế hoạch kiểm chứng |

## 6. Trạng thái các tính năng đáng chú ý trong JDK 27

Release notes JDK 27 liệt kê chín JEP có ảnh hưởng đáng kể. Trong số đó có bốn preview và một incubator. Đây là ví dụ rõ ràng cho thấy một bản JDK đã GA vẫn có thể chứa nhiều tính năng chưa final.

### Các preview features

| JEP | Tên tính năng trong JDK 27 | Trạng thái |
| --- | --- | --- |
| JEP 532 | Primitive Types in Patterns, instanceof, and switch | Fifth Preview |
| JEP 531 | Lazy Constants | Third Preview |
| JEP 533 | Structured Concurrency | Seventh Preview |
| JEP 538 | PEM Encodings of Cryptographic Objects | Third Preview |

Các tính năng trên cần được sử dụng theo cơ chế preview. Ví dụ, Primitive Types in Patterns mở rộng pattern matching để hỗ trợ kiểu nguyên thủy trong các ngữ cảnh pattern, đồng thời mở rộng **instanceof** và **switch**. Lazy Constants, Structured Concurrency và PEM Encodings là các API preview.

### Tính năng incubator

| JEP | Tên tính năng trong JDK 27 | Trạng thái |
| --- | --- | --- |
| JEP 537 | Vector API | Twelfth Incubator |

Vector API nằm trong module **jdk.incubator.vector**; đây là API incubator của JDK, không phải preview API. Hãy dùng cơ chế module tương ứng và đọc Javadoc của đúng phiên bản JDK đang triển khai.

### Các cải tiến lớn không được đánh dấu preview hoặc incubator

| JEP | Cải tiến | Phạm vi khái quát |
| --- | --- | --- |
| JEP 527 | Post-Quantum Hybrid Key Exchange for TLS 1.3 | Thư viện bảo mật |
| JEP 523 | Make G1 the Default Garbage Collector in All Environments | Hành vi mặc định của HotSpot |
| JEP 534 | Compact Object Headers by Default | Bố trí đối tượng của HotSpot |
| JEP 536 | JFR In-Process Data Redaction | Ghi nhận và giám sát bằng JDK Flight Recorder |

Các cải tiến này được release notes giới thiệu như chức năng của JDK 27, không gắn nhãn preview hoặc incubator. Tuy nhiên, chúng thuộc các phạm vi khác nhau: một số liên quan đến thư viện bảo mật, một số là hành vi riêng của HotSpot hoặc công cụ JDK. Vì thế, không nên suy ra rằng cả bốn đều là API Java SE dùng được trên mọi JVM.

Release notes về các JEP lớn của Java 27 không liệt kê một tính năng experimental riêng. Điều này không có nghĩa mọi bản dựng JDK hoặc mọi nền tảng đều không có cờ HotSpot experimental; hãy kiểm tra tài liệu của đúng bản phân phối và nền tảng đang sử dụng.

## 7. Chọn cơ chế nào khi phát triển ứng dụng?

### Khi triển khai production

Ưu tiên tính năng final/permanent. Nếu cần khả năng chạy trên nhiều nhà cung cấp, ưu tiên API thuộc Java SE và kiểm tra API có nằm trong đặc tả Java SE hay chỉ thuộc JDK. Không dựa vào một JEP hoặc việc tính năng xuất hiện trong JDK GA để kết luận rằng API đã ổn định.

### Khi đánh giá preview

Tạo nhánh hoặc module thử nghiệm riêng, cố định JDK feature release ở cả CI và môi trường chạy, bật preview ở cả compile lẫn runtime. Ghi rõ tính năng preview nào đang được dùng và kiểm tra release notes khi nâng JDK. Tránh phát hành thư viện công khai có phụ thuộc preview vì người dùng thư viện phải chạy đúng feature release tương ứng.

### Khi đánh giá incubator

Đưa phần phụ thuộc incubator vào một lớp bao bọc nội bộ để có thể thay thế khi API đổi hoặc bị loại bỏ. Kiểm tra module name và Javadoc của từng bản JDK. Không để kiểu dữ liệu incubator trở thành hợp đồng công khai của thư viện nếu chưa chấp nhận rủi ro tương thích.

### Khi đánh giá experimental

Chỉ bật cờ experimental khi tài liệu của đúng JVM xác nhận cờ đó tồn tại và giải thích rõ tác động. Kiểm thử trên đúng hệ điều hành, kiến trúc và nhà cung cấp JDK mục tiêu. Theo dõi thay đổi cờ qua từng bản cập nhật và chuẩn bị phương án tắt hoặc thay thế.

## 8. Cách xác minh trạng thái một tính năng

Khi gặp một tính năng mới, có thể kiểm tra theo trình tự sau:

1. **Đọc release notes của đúng feature release.** Tìm tên tính năng, JEP và nhãn như Preview, Second Preview, Incubator hoặc Experimental. Không dùng release notes của một phiên bản khác để suy trạng thái.
2. **Đọc JEP liên quan.** JEP mô tả mục tiêu, phạm vi và quyết định kỹ thuật; sự tồn tại của JEP không tự nó chứng minh tính năng đã final.
3. **Kiểm tra đặc tả và Javadoc.** Đặc tả Java SE cho biết tính năng thuộc nền tảng chuẩn hay không. Javadoc có thể đánh dấu API là Preview hoặc Incubating Feature; tên module giúp nhận ra API JDK-specific.
4. **Kiểm tra tài liệu compiler và launcher.** Preview cần **--enable-preview**; incubator cần giải quyết module; experimental cần tùy chọn HotSpot được tài liệu hóa.
5. **Kiểm tra lại khi nâng JDK.** Một tính năng có thể chuyển từ preview sang preview lần tiếp theo, final hoặc bị rút; API incubator và cờ experimental cũng có thể đổi hoặc biến mất.

JDK Early Access (EA) build là một kênh phát hành sớm để thử nghiệm các thay đổi đang phát triển. EA không phải nhãn thay thế cho preview, incubator hay experimental. Một nguyên mẫu trong EA có thể còn thiếu thành phần và thay đổi lớn; chỉ sử dụng trong phạm vi thử nghiệm mà dự án công bố.

## 9. Kết luận

Hãy đọc bốn nhãn theo đúng phạm vi của chúng: **final/permanent** là trạng thái phát hành ổn định; **preview** là tính năng Java SE đã được triển khai nhưng chưa vĩnh viễn; **incubator** là API hoặc công cụ JDK đang được hoàn thiện; **experimental** chủ yếu là cơ chế thử nghiệm dành cho HotSpot. Cách bật, cam kết tương thích và rủi ro của chúng khác nhau.

Với Java 27, cần nhớ bốn preview (JEP 531, 532, 533, 538) và một incubator (JEP 537). Khi đọc tài liệu hoặc nâng cấp JDK, hãy kiểm tra trạng thái của từng tính năng thay vì gán một trạng thái chung cho toàn bộ phiên bản Java.

## Tài liệu tham khảo

- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — ngày GA, các JEP nổi bật, nhãn preview/incubator và các thay đổi của JDK 27.
- [JDK 27.0.1.1 Release Notes](https://www.oracle.com/java/technologies/javase/27-0-1-1-relnotes.html) — bản cập nhật Oracle JDK ngày 17-11-2026.
- [Significant Changes in JDK 27 Release](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html) — mô tả các preview, incubator và cải tiến lớn của Java 27.
- [Preview Features — Java 27](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html) — định nghĩa preview và cách bật khi biên dịch/chạy.
- [The java Command — Java 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — **--enable-preview**, **--add-modules** và **-XX:+UnlockExperimentalVMOptions**.
- [The javac Command — Java 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — tùy chọn biên dịch preview.
- [Module jdk.incubator.vector — Java 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html) — trạng thái incubator của Vector API.
- [Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/) — phân biệt module Java SE (**java.**) và module riêng của JDK (**jdk.**).
- [Using JDK Preview Features — dev.java](https://dev.java/learn/first-steps/using-preview/) — giải thích vòng đời preview, incubator, experimental và Early Access.
- [JEP 11: Incubator Modules](https://openjdk.org/jeps/11) và [JEP 12: Preview Features](https://openjdk.org/jeps/12) — cơ chế nền tảng cho incubator và preview.
