# Đọc Java SE Specification, API Specification và release notes chính thức

## 1. Vì sao cần đọc tài liệu chính thức?

Khi học Java 21, ta thường bắt đầu từ sách, bài hướng dẫn hoặc ví dụ trên mạng. Những tài liệu đó hữu ích để tiếp cận nhanh, nhưng đôi khi đã cũ, mô tả hành vi riêng của một thư viện hoặc một nhà cung cấp, hay bỏ qua điều kiện áp dụng của một tính năng. Tài liệu chính thức giúp xác định Java quy định điều gì, API cung cấp những gì và một bản phát hành JDK cụ thể thay đổi ra sao.

Trong phạm vi Java 21, cần phân biệt ba nhóm tài liệu:

- **Java SE Specification** mô tả nền tảng Java SE ở mức đặc tả: ngôn ngữ, máy ảo và các yêu cầu tương thích.
- **Java SE API Specification** mô tả các package, class, interface, method, field, exception và hợp đồng sử dụng API chuẩn.
- **JDK release notes** ghi lại nội dung của một bản phát hành JDK: tính năng, thay đổi, sửa lỗi, vấn đề đã biết và lưu ý vận hành.

Ba nhóm tài liệu trả lời các câu hỏi khác nhau. Không nên dùng release notes để thay thế đặc tả ngôn ngữ, cũng không nên suy ra hành vi của một API chỉ từ ví dụ trong bài viết.

## 2. Java SE Specification gồm những gì?

Đặc tả Java SE xác định nền tảng ở mức chuẩn. Khi cần hiểu một đoạn mã hợp lệ hay không, hoặc bytecode và JVM phải tuân theo quy tắc nào, hai tài liệu cốt lõi cần tra cứu là **Java Language Specification (JLS)** và **Java Virtual Machine Specification (JVMS)**.

### 2.1. Java Language Specification (JLS)

JLS mô tả cú pháp và ngữ nghĩa của ngôn ngữ Java. Tài liệu này trả lời những câu hỏi như:

- Một khai báo biến, kiểu dữ liệu, biểu thức hoặc câu lệnh có hợp lệ không?
- Quy tắc chuyển đổi kiểu, overload, override, kế thừa và truy cập thành viên là gì?
- Generic, lambda expression, pattern matching và hệ thống exception được hiểu như thế nào?
- Compiler phải xử lý một cấu trúc ngôn ngữ theo những quy tắc nào?

Ví dụ, khi hai overload có thể nhận cùng một lời gọi method, hãy tra các quy tắc *method invocation* và *overload resolution* trong JLS. Kết quả không nên được xác định bằng cách đoán từ tên method hoặc bằng một lần thử trên compiler.

Trang chính thức: [Java Language Specification, Java SE 21](https://docs.oracle.com/javase/specs/jls/se21/html/index.html).

### 2.2. Java Virtual Machine Specification (JVMS)

JVMS mô tả máy ảo Java và định dạng class file. Tài liệu này hữu ích khi tìm hiểu:

- Cấu trúc class file và constant pool.
- Tập lệnh bytecode (instruction set) và kiểu dữ liệu mà JVM thao tác.
- Cách nạp, liên kết và khởi tạo class/interface.
- Mô hình runtime, frame, operand stack, exception và hành vi của instruction.

Ví dụ, nếu cần hiểu bytecode `invokevirtual` hoạt động theo quy tắc nào, hoặc vì sao class file có một cấu trúc nhất định, JVMS là nguồn tra cứu phù hợp. JLS mô tả ý nghĩa của chương trình Java ở mức ngôn ngữ; JVMS mô tả hợp đồng ở mức máy ảo. Hai tài liệu liên quan nhưng không thay thế cho nhau.

Trang chính thức: [Java Virtual Machine Specification, Java SE 21](https://docs.oracle.com/javase/specs/jvms/se21/html/index.html).

### 2.3. Đọc đúng phiên bản đặc tả

Luôn chọn đúng phiên bản tương ứng với mục tiêu. Bài học này tập trung vào Java SE 21, vì vậy hãy dùng JLS 21 và JVMS 21 khi xác minh hành vi của Java 21. Một phiên bản đặc tả mới hơn có thể bổ sung hoặc thay đổi quy tắc; không nên tự động áp dụng nội dung đó ngược về Java 21.

Trang tổng hợp các đặc tả: [Java SE Specifications](https://docs.oracle.com/javase/specs/).

## 3. Java SE API Specification (Javadoc)

Java SE API Specification là tài liệu tham chiếu cho API chuẩn được cung cấp bởi nền tảng. Với Java 21, tài liệu HTML chính thức được xuất bản dưới dạng Javadoc tại:

[Java SE 21 API Specification](https://docs.oracle.com/en/java/javase/21/docs/api/index.html).

Javadoc mô tả cấu trúc và hợp đồng API, thường gồm:

- **Package**: nhóm các kiểu có liên quan, chẳng hạn `java.util` hoặc `java.time`.
- **Class và interface**: mục đích, quan hệ kế thừa, interface được triển khai và các kiểu lồng nhau.
- **Constructor và method**: tham số, kiểu trả về, exception có thể được ném, điều kiện sử dụng và kết quả.
- **Field và constant**: ý nghĩa của giá trị được công bố.
- **Ghi chú phiên bản**: thông tin như API được thêm vào phiên bản nào, API bị deprecated hay có giới hạn sử dụng.

Ví dụ, khi cần chọn cấu trúc dữ liệu, hãy tra `java.util` và trang của kiểu cụ thể như `List`, `Map` hoặc `ArrayList`. Đọc mô tả tổng quan, method cần gọi, tham số, giá trị trả về và phần *Implementation Requirements* hoặc *Implementation Note* nếu có. Các phần này giúp phân biệt hợp đồng API với chi tiết triển khai.

### 3.1. Phân biệt hợp đồng API và cách triển khai

API Specification mô tả điều mà người gọi được phép dựa vào. Một số trang còn cung cấp ghi chú triển khai hoặc ví dụ, nhưng chi tiết đó không mặc nhiên là cam kết chung cho mọi implementation.

Chẳng hạn, nếu tài liệu quy định một method trả về một collection nhưng không cam kết collection đó có thể sửa đổi, chương trình không nên phụ thuộc vào khả năng sửa đổi. Hãy kiểm tra chính xác hợp đồng của method; nếu cần một collection có thể thay đổi, hãy tạo bản sao theo nhu cầu.

Tương tự, không suy luận độ phức tạp thời gian, thứ tự duyệt hoặc tính thread-safe nếu tài liệu không cam kết. Khi hợp đồng không hứa hẹn một đặc tính, code cần tránh phụ thuộc vào đặc tính đó.

### 3.2. Theo dõi API được thêm, deprecated hoặc giới hạn

Trong Javadoc, chú ý các thẻ và phần mô tả như `Since`, `Deprecated`, `@deprecated`, `Preview` (nếu được ghi nhận) và các ghi chú liên quan. Chúng giúp trả lời API xuất hiện từ phiên bản nào, có được khuyến nghị thay thế hay có điều kiện sử dụng đặc biệt không.

`Deprecated` có nghĩa API vẫn được nhận diện nhưng không còn được khuyến nghị sử dụng; cần đọc lý do và hướng thay thế được tài liệu chỉ ra. Không nên coi mọi API deprecated là đã bị xóa. Ngược lại, cũng không nên chọn API chỉ vì nó vẫn biên dịch được: hãy kiểm tra trạng thái và hướng dẫn hiện hành của API đó.

## 4. Đọc release notes của JDK 21

Release notes mô tả một bản phân phối JDK cụ thể. Chúng đặc biệt quan trọng khi cài đặt, nâng cấp, triển khai hoặc điều tra khác biệt giữa các bản cập nhật. Hãy bắt đầu từ nguồn của nhà cung cấp JDK mà dự án thực sự sử dụng.

Các nguồn chính thức hữu ích cho JDK 21:

- [Oracle JDK 21 Release Notes](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html) — ghi chú phát hành và các vấn đề liên quan đến Oracle JDK 21.
- [OpenJDK JDK 21 Release Notes](https://jdk.java.net/21/release-notes) — thông tin phát hành của OpenJDK 21.
- [OpenJDK JDK 21 project](https://openjdk.org/projects/jdk/21/) — thông tin dự án và các JEP gắn với phiên bản.

Khi đọc release notes, tập trung vào những phần có ảnh hưởng trực tiếp đến ứng dụng:

1. **New features / Enhancements**: tính năng mới và cải tiến được đưa vào bản phát hành.
2. **Behavioral changes**: thay đổi hành vi mặc định hoặc hành vi có thể quan sát từ ứng dụng.
3. **Removed / Deprecated features and options**: thành phần bị loại bỏ hoặc không còn được khuyến nghị; kiểm tra ảnh hưởng tới build, runtime và quy trình vận hành.
4. **Security**: cập nhật bảo mật và khuyến nghị áp dụng bản cập nhật phù hợp.
5. **Known issues**: lỗi hoặc giới hạn đã biết, kèm điều kiện gặp phải và cách xử lý nếu có.
6. **Bug fixes**: sửa lỗi có thể giải thích vì sao ứng dụng hoạt động khác sau khi nâng cấp.

Release notes thường gắn với một nhà cung cấp và một bản cập nhật cụ thể. Vì vậy, khi ghi nhận một vấn đề, hãy lưu cả nhà cung cấp, phiên bản đầy đủ và số build của JDK đang chạy. Chỉ ghi “Java 21” có thể chưa đủ để tái hiện sự cố.

## 5. Phân biệt Specification, API Specification và release notes

| Nhu cầu tra cứu | Nguồn nên dùng | Điều cần xác minh |
|---|---|---|
| Kiểm tra cú pháp hoặc ngữ nghĩa của mã Java | JLS | Quy tắc ngôn ngữ áp dụng trong Java SE 21 |
| Hiểu class file, bytecode hoặc hành vi JVM | JVMS | Quy tắc máy ảo và định dạng class file |
| Tìm cách dùng `String`, `List`, `Stream` hoặc API chuẩn khác | Java SE 21 API Specification | Hợp đồng, tham số, kết quả, exception và trạng thái API |
| Kiểm tra tính năng hoặc thay đổi của một bản JDK | Release notes của nhà cung cấp | Phiên bản, build, thay đổi và vấn đề đã biết |
| Tìm bối cảnh thiết kế của một thay đổi nền tảng | JEP tương ứng | Mục tiêu, phạm vi và trạng thái của đề xuất |

JEP (JDK Enhancement Proposal) giải thích một đề xuất cải tiến trong hệ sinh thái JDK. JEP hữu ích để hiểu động cơ thiết kế và phạm vi của thay đổi, nhưng khi xác minh quy tắc ngôn ngữ hoặc hợp đồng API, vẫn cần đối chiếu đặc tả và Javadoc chính thức. Với một tính năng preview hoặc incubator, phải kiểm tra rõ trạng thái và phiên bản áp dụng; không coi tính năng preview là hợp đồng ổn định của Java SE.

## 6. Quy trình tra cứu một vấn đề thực tế

Giả sử một chương trình Java 21 không biên dịch được sau khi thay đổi cách gọi một method. Có thể tra cứu theo quy trình sau:

1. **Thu hẹp câu hỏi**: lỗi nằm ở cú pháp, chọn overload, kiểu trả về, API không tồn tại hay cấu hình compiler?
2. **Xác nhận phiên bản**: kiểm tra compiler và JDK thực tế, ví dụ bằng `java -version` và `javac -version` trong đúng môi trường build.
3. **Tra JLS**: nếu câu hỏi liên quan đến cú pháp hoặc ngữ nghĩa, tìm chương và mục tương ứng trong JLS 21.
4. **Tra API Specification**: nếu method hoặc kiểu dữ liệu là nguyên nhân, mở Javadoc Java SE 21 và đọc hợp đồng API.
5. **Đối chiếu release notes**: nếu hành vi khác nhau giữa các bản cập nhật hoặc nhà cung cấp, kiểm tra ghi chú phát hành của đúng JDK đang dùng.
6. **Thử nghiệm tối thiểu**: tạo ví dụ nhỏ tái hiện vấn đề, biên dịch và chạy bằng đúng phiên bản mục tiêu. Dùng kết quả thử nghiệm để kiểm chứng giả thuyết, đồng thời dùng tài liệu làm căn cứ cho quy tắc.
7. **Ghi lại kết luận**: lưu URL, phiên bản tài liệu, nhà cung cấp/build JDK và đoạn quy tắc liên quan để người khác có thể kiểm tra lại.

Ví dụ lệnh kiểm tra phiên bản:

```bash
java -version
javac -version
```

Hai lệnh trên cho biết phiên bản runtime và compiler trong `PATH` hiện tại. Trong dự án thực tế, cần kiểm tra thêm cấu hình toolchain của Gradle hoặc Maven và môi trường CI, vì chúng có thể sử dụng JDK khác với terminal đang mở.

## 7. Cách đọc tài liệu hiệu quả

- **Bắt đầu từ câu hỏi cụ thể** thay vì đọc toàn bộ đặc tả từ đầu đến cuối. Dùng mục lục và tìm kiếm theo thuật ngữ, sau đó đọc cả phần định nghĩa và các mục được tham chiếu.
- **Đọc ngữ cảnh xung quanh**. Một câu trong đặc tả có thể phụ thuộc vào định nghĩa, ngoại lệ hoặc quy tắc ở mục khác.
- **Giữ đúng phiên bản**. Không trộn Javadoc Java 21 với Javadoc của một phiên bản mới hơn khi kết luận về API của Java 21.
- **Phân biệt quy định và ghi chú**. Nội dung đặc tả và hợp đồng API là căn cứ về hành vi được quy định; ghi chú triển khai, ví dụ và bài viết hướng dẫn có vai trò bổ trợ.
- **Kiểm tra nhà cung cấp và build** khi vấn đề liên quan đến runtime, bảo mật hoặc thay đổi phát hành. Các bản phân phối JDK có thể có lịch phát hành và ghi chú riêng.
- **Ưu tiên trạng thái hiện hành**. Khi tài liệu đề cập tính năng preview, incubator, deprecated hoặc removed, xác định rõ trạng thái trong đúng phiên bản; không áp dụng hướng dẫn đã lỗi thời như thể đó là cách dùng hiện hành.

Không cần ghi nhớ toàn bộ JLS, JVMS hay Javadoc. Kỹ năng quan trọng là biết câu hỏi thuộc lớp nào, tìm đúng tài liệu đúng phiên bản và diễn giải chính xác giới hạn của điều tài liệu cam kết.

## 8. Tự kiểm tra

1. Muốn biết một biểu thức Java có hợp lệ và được phân giải overload như thế nào, nên tra tài liệu nào?
2. Muốn hiểu một bytecode instruction và cấu trúc class file, nên tra tài liệu nào?
3. Muốn xác định method của `java.util.List` nhận tham số gì và có thể ném exception nào, nên tra ở đâu?
4. Muốn biết một bản cập nhật JDK có thay đổi hành vi hoặc sửa lỗi nào, nên đọc tài liệu nào và cần ghi lại thông tin phiên bản gì?
5. Vì sao không nên coi một ví dụ triển khai hoặc một tính năng preview là cam kết ổn định của Java SE?

Nếu trả lời được, bạn đã nắm được cách chọn đúng nguồn tra cứu: JLS cho ngôn ngữ, JVMS cho máy ảo, API Specification cho hợp đồng API và release notes cho thay đổi của bản phát hành JDK.
