# Đọc JEP và tài liệu API theo phiên bản để tránh sao chép cú pháp preview đã thay đổi

Java 22 giới thiệu nhiều tính năng có trạng thái khác nhau: một số đã trở thành tính năng chính thức, một số chỉ ở giai đoạn preview, một số nằm trong incubator. Trong các phiên bản tiếp theo, một tính năng có thể được hoàn thiện, đổi thiết kế, tiếp tục preview, vẫn ở incubator hoặc bị rút lại. Vì vậy, khi học một tính năng Java 22 để dùng trong ứng dụng hiện đại, cần tra cứu theo đúng phiên bản JDK và xác minh trạng thái hiện tại trước khi sao chép ví dụ.

Bài này hướng dẫn cách đọc JEP, release notes, Java Language Updates và API Specification để xác định một tính năng có thể dùng ở JDK nào, cần cờ biên dịch nào và ví dụ cũ còn đúng hay không. Mốc đối chiếu hiện tại là ngày 24/11/2026; JDK 27 là phiên bản Java SE mới nhất đã phát hành tại thời điểm này.

Sau bài học, bạn có thể:

- Phân biệt tính năng final, preview, incubator, deprecated và withdrawn.
- Lần theo lịch sử một tính năng qua các JEP và phiên bản JDK.
- Chọn đúng tài liệu ngôn ngữ, API và release notes cho phiên bản cần triển khai.
- Biết khi nào cần `--enable-preview`, `--add-modules` hoặc không cần cờ đặc biệt.
- Kiểm tra lại ví dụ trước khi đưa vào mã nguồn, build pipeline hoặc tài liệu nội bộ.

## 1. Vì sao phải đọc tài liệu theo phiên bản?

Tên một tính năng có thể giữ nguyên trong nhiều phiên bản, trong khi cú pháp, chữ ký API, cách cấu hình hoặc trạng thái phát hành đã thay đổi. Một bài viết được viết cho JDK 22 có thể mô tả đúng trạng thái ở JDK 22 nhưng không còn là hướng dẫn đúng cho JDK 27.

Ví dụ, trong JDK 22:

- Unnamed Variables and Patterns đã là tính năng chính thức, dùng được mà không bật preview.
- Stream Gatherers và Class-File API mới ở giai đoạn preview.
- Scoped Values ở lần preview thứ hai.
- Vector API vẫn là incubator.
- String Templates ở lần preview thứ hai, nhưng sau đó bị rút khỏi kế hoạch phát hành.

Đến các JDK sau, Stream Gatherers và Class-File API đã trở thành API chính thức; Scoped Values và Flexible Constructor Bodies cũng đã final. String Templates không được phát hành trong JDK 23. Một đoạn code chỉ được gắn nhãn “Java 22 feature” vì thế chưa đủ thông tin để quyết định có thể dùng nó ở hiện tại.

Hãy luôn tách ba câu hỏi:

1. **Tính năng được giới thiệu ở đâu?** Tìm JEP và phiên bản đầu tiên có tính năng đó.
2. **Tính năng ở trạng thái nào trong phiên bản cần dùng?** Kiểm tra JEP tiếp theo, release notes và danh sách preview/incubator của đúng JDK.
3. **Cú pháp và API chính xác hiện tại là gì?** Đọc Java Language Updates, API Specification và ví dụ gắn với phiên bản đích.

## 2. Hiểu đúng các trạng thái của tính năng

JEP (JDK Enhancement Proposal) mô tả mục tiêu, phạm vi, thiết kế và tiến trình của một thay đổi trong OpenJDK. JEP giúp lần theo quá trình phát triển, nhưng để xác nhận tính năng đã có trong một bản JDK phát hành hay chưa, hãy đối chiếu thêm release notes và tài liệu của bản đó.

| Trạng thái | Ý nghĩa thực tế | Cách sử dụng và kiểm tra |
|---|---|---|
| Final / permanent | Tính năng đã trở thành một phần chính thức của Java SE hoặc JDK tương ứng. | Dùng theo API Specification và ngôn ngữ của phiên bản đích; không cần cờ preview cho tính năng đó. |
| Preview | Thiết kế và triển khai được cung cấp để thử nghiệm, nhưng chưa phải tính năng cố định. Nó có thể tiếp tục thay đổi hoặc bị rút. | Phải bật preview khi biên dịch và chạy bằng JDK của chính release chứa preview đó. Kiểm tra JEP và tài liệu preview của từng release. |
| Incubator | API thử nghiệm, thường được cung cấp trong một module riêng để nhận phản hồi và tiếp tục phát triển. | Kiểm tra module và tài liệu incubator; thường cần thêm module bằng `--add-modules`. Không giả định API đã ổn định. |
| Deprecated | API hoặc tính năng vẫn tồn tại nhưng đã được đánh dấu không nên tiếp tục dùng; tài liệu thường nêu lý do và hướng thay thế. | Đọc thông tin `since`, `forRemoval` và API thay thế. Deprecated không tự động có nghĩa là đã bị xóa. |
| Withdrawn / removed | Đề xuất bị rút trước khi phát hành, hoặc tính năng/API đã bị loại khỏi JDK. | Không dùng mã từ bản preview cũ làm hướng dẫn cho JDK hiện tại. Tìm thông báo rút lại và giải pháp thay thế được hỗ trợ. |

### Preview không phải incubator

Preview được định nghĩa trong JEP 12. Một preview có thể là thay đổi ngôn ngữ, JVM hoặc API. Nó được bật tường minh, có thể được điều chỉnh qua nhiều vòng preview, trở thành final hoặc bị loại bỏ. Mỗi phiên bản preview là một mục tiêu riêng; code dùng preview của release cũ không được bảo đảm sẽ biên dịch hoặc chạy trên release mới.

Incubator được mô tả trong JEP 11. Một incubator API thường được đưa vào module riêng và có thể thay đổi đáng kể hoặc bị xóa trong phiên bản sau. Ví dụ quen thuộc là `jdk.incubator.vector`. Incubator không đồng nghĩa với preview language feature và không dùng `--enable-preview` để thay cho việc thêm module.

### Deprecated không đồng nghĩa với legacy đã bị xóa

Khi thấy API bị deprecated, hãy mở trang API của chính lớp hoặc phương thức đó để xem ghi chú thay thế. Nếu có `forRemoval=true`, việc loại bỏ được dự kiến trong một phiên bản tương lai; nếu không, API vẫn có thể còn trong JDK nhưng không nên chọn cho mã mới khi đã có phương án thay thế phù hợp. Không dùng API đã bị xóa chỉ vì một tutorial cũ vẫn còn hiển thị trên Internet.

## 3. Quy trình tra cứu một tính năng Java 22

### Bước 1: Xác định phiên bản đích

Ghi rõ phiên bản dùng cho từng môi trường:

- JDK dùng để biên dịch.
- JDK chạy trong môi trường phát triển và CI.
- JDK chạy trên production.
- Phiên bản Java mà thư viện hoặc ứng dụng cần hỗ trợ.

Các phiên bản này có thể khác nhau. Nếu cần tương thích với Java 22, hãy xác định rõ mục tiêu Java 22 trong build. Nếu dự án chạy trên JDK 27, hãy kiểm tra trạng thái của tính năng trên JDK 27 thay vì dựa vào tài liệu JDK 22.

Kiểm tra toolchain thực tế:

```bash
java --version
javac --version
```

Nếu IDE, Maven hoặc Gradle chọn một JDK khác với terminal, kết quả kiểm tra trong terminal chưa đủ. Hãy xác minh toolchain, compiler và runtime mà build pipeline thực sự sử dụng.

### Bước 2: Mở JEP gốc và đọc lịch sử của tính năng

Tìm JEP theo số hoặc tên tính năng tại [OpenJDK JEP Index](https://openjdk.org/jeps/0). Đọc ít nhất:

- **Summary / Goals:** tính năng giải quyết vấn đề gì và phạm vi đến đâu.
- **Motivation:** vì sao thay đổi được đề xuất.
- **Description:** cú pháp, API, quy tắc và hành vi được mô tả.
- **Risks and Assumptions:** giới hạn hoặc rủi ro đã biết.
- **Status / Release:** tình trạng và phiên bản liên quan được ghi trên JEP.

Sau đó tìm các JEP tiếp theo có cùng tên tính năng. Một tính năng được preview nhiều lần thường có JEP riêng cho mỗi lần; JEP mới có thể ghi rõ điểm khác so với vòng trước. Đừng chỉ đọc JEP đầu tiên rồi cho rằng cú pháp vẫn giữ nguyên.

### Bước 3: Đối chiếu release notes của JDK

Release notes cho biết thay đổi nào thực sự có trong bản phát hành, gồm tính năng mới, preview, incubator, deprecated và removed. Tài liệu này giúp phát hiện trường hợp một đề xuất từng được nhắc đến nhưng không có mặt trong bản phát hành cuối cùng.

Với Java 22, bắt đầu từ [JDK 22 Release Notes](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html) hoặc [JDK 22 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-22.html). Khi cần dùng phiên bản mới hơn, mở release notes và migration guide tương ứng của phiên bản đó.

### Bước 4: Đọc tài liệu ngôn ngữ hoặc API đúng phiên bản

Chọn tài liệu theo loại thay đổi:

| Bạn đang tra cứu | Tài liệu nên mở |
|---|---|
| Cú pháp, quy tắc kiểu, constructor, pattern hoặc `switch` | Java Language Updates và Java Language Specification (JLS) của đúng release. |
| Lớp, interface, method, tham số và ngoại lệ | API Specification của đúng release. |
| API preview | Trang Preview API và trang API có nhãn `PREVIEW` của đúng release. |
| Module incubator | Module Summary và package documentation của module trong JDK đích. |
| Cờ compiler hoặc launcher | `javac` và `java` command specifications của đúng JDK. |
| Thay đổi khi nâng cấp | Release Notes, Migration Guide, Deprecated API và Removed Features của release đích. |

Các trang tài liệu Oracle có đường dẫn theo phiên bản. Ví dụ:

- [Java SE 22 API Specification](https://docs.oracle.com/en/java/javase/22/docs/api/index.html)
- [Java SE 22 Preview API](https://docs.oracle.com/en/java/javase/22/docs/api/preview-list.html)
- [Java Language Changes for Java SE 22](https://docs.oracle.com/en/java/javase/22/language/java-language-changes.html)
- [Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/index.html)
- [Java SE 27 Preview API](https://docs.oracle.com/en/java/javase/27/docs/api/preview-list.html)
- [Java Language Changes by Release — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)

Đừng bỏ qua phần Preview API trong Javadoc. Trang này liệt kê các API preview và nhắc rằng chúng có thể bị loại bỏ trong các bản triển khai sau. Trang New API cho biết API mới được thêm vào release; trang Deprecated API giúp phát hiện API không còn được khuyến nghị.

### Bước 5: Kiểm tra cờ biên dịch và chạy

Preview language/API feature và incubator module có cách bật khác nhau.

**Ví dụ với preview feature của JDK 22:** dùng `javac` và `java` thuộc JDK 22:

```bash
javac --enable-preview --release 22 -d out src/Main.java
java --enable-preview -cp out Main
```

`--enable-preview` cần có ở bước biên dịch và bước chạy. Theo quy tắc của preview, compiler phải thuộc đúng release chứa preview; runtime cũng phải là JDK của release đó. Không thể dùng `--enable-preview` của JDK 27 để bật một preview chỉ tồn tại trong JDK 22.

**Ví dụ với incubator module Vector API của JDK 22:**

```bash
javac --add-modules jdk.incubator.vector -d out src/VectorDemo.java
java --add-modules jdk.incubator.vector -cp out VectorDemo
```

`--add-modules` yêu cầu module được phân giải khi biên dịch và chạy. Với named module, kiểm tra tài liệu module để khai báo dependency tương ứng trong `module-info.java`. Không thêm `--enable-preview` chỉ vì API mang nhãn incubator.

Nếu chương trình dùng cả preview feature lẫn incubator module, cần truyền cả hai loại cờ ở những bước tương ứng. Cấu hình trong IDE phải được phản ánh ở Maven/Gradle và CI; nếu chỉ bật trong IDE, bản build hoặc production có thể thất bại.

Với tính năng đã final, không cần bật preview cho tính năng đó. Nếu dùng `--release`, tùy chọn này giúp biên dịch theo quy tắc ngôn ngữ và tập API công khai của phiên bản mục tiêu; nó không biến một preview cũ thành API final và cũng không thay thế việc chọn đúng JDK khi thử preview.

### Bước 6: Biên dịch, chạy và xác minh trên JDK đích

Sau khi đọc tài liệu, tạo ví dụ tối thiểu và kiểm tra trên JDK cần hỗ trợ. Đừng chỉ dựa vào syntax highlighting hoặc code completion của IDE. Hãy xác nhận:

- Mã biên dịch với đúng compiler và đúng cờ.
- Mã chạy với đúng runtime và đúng cờ.
- Chữ ký method, package và module tồn tại trong phiên bản đó.
- Kết quả và hành vi đúng như tài liệu mô tả.
- Không có API deprecated hoặc removed bị dùng nhầm từ tutorial cũ.

Khi nâng cấp JDK, biên dịch lại và chạy test trên phiên bản mới. Nếu tính năng từng ở preview/incubator, xem lại toàn bộ lịch sử JEP và thay đổi API trước khi sửa code.

## 4. Ví dụ về vòng đời của các tính năng Java 22

Bảng sau cho thấy cùng một tính năng có thể đi qua nhiều trạng thái. Các mốc này giúp xác định tài liệu cần mở khi chuyển từ JDK 22 sang JDK mới hơn.

| Tính năng | Trạng thái ở JDK 22 | Diễn biến sau đó | Cách hiểu khi dùng hiện nay |
|---|---|---|---|
| Unnamed Variables and Patterns | Final — [JEP 456](https://openjdk.org/jeps/456) | Đã là tính năng chính thức trong Java 22. | Dùng theo ngôn ngữ hiện hành; không cần bật preview. |
| Foreign Function & Memory API | Final — [JEP 454](https://openjdk.org/jeps/454) | Hoàn tất sau các vòng incubator/preview trước JDK 22. | Dùng API final trong tài liệu của JDK mục tiêu; không sao chép các ví dụ FFM từ vòng incubator cũ. |
| Stream Gatherers | Preview — [JEP 461](https://openjdk.org/jeps/461) | Preview lần hai ở JDK 23 ([JEP 473](https://openjdk.org/jeps/473)), final ở JDK 24 ([JEP 485](https://openjdk.org/jeps/485)). | Nếu target JDK 24 trở lên, đọc API final của phiên bản đích; không bật preview theo hướng dẫn JDK 22. |
| Class-File API | Preview — [JEP 457](https://openjdk.org/jeps/457) | Preview lần hai ở JDK 23 ([JEP 466](https://openjdk.org/jeps/466)), final ở JDK 24 ([JEP 484](https://openjdk.org/jeps/484)). | Dùng package và chữ ký API final theo JDK đích; ví dụ JDK 22 có thể khác. |
| Scoped Values | Preview lần hai — [JEP 464](https://openjdk.org/jeps/464) | Preview lần ba ở JDK 23 ([JEP 481](https://openjdk.org/jeps/481)), lần bốn ở JDK 24 ([JEP 487](https://openjdk.org/jeps/487)), final ở JDK 25 ([JEP 506](https://openjdk.org/jeps/506)). | Dùng API final từ JDK 25 trở lên; không bê nguyên mẫu preview JDK 22. |
| Flexible Constructor Bodies | Preview — [JEP 447](https://openjdk.org/jeps/447), tên ban đầu là Statements before `super(...)` | Preview lần hai ở JDK 23 ([JEP 482](https://openjdk.org/jeps/482)), lần ba ở JDK 24 ([JEP 492](https://openjdk.org/jeps/492)), final ở JDK 25 ([JEP 513](https://openjdk.org/jeps/513)). | Dùng quy tắc final theo JDK 25 trở lên; khi đọc bài JDK 22, nhận diện đây chỉ là preview đầu tiên. |
| String Templates | Preview lần hai — [JEP 459](https://openjdk.org/jeps/459) | Đề xuất preview lần ba [JEP 465](https://openjdk.org/jeps/465) bị rút; tính năng không được phát hành trong JDK 23. | Không sử dụng cú pháp hoặc API preview cũ trong code hiện đại. Đọc thông báo rút lại trước khi tham khảo tutorial. |
| Vector API | Incubator lần thứ bảy — [JEP 460](https://openjdk.org/jeps/460) | Vẫn ở incubator; JDK 27 có vòng thứ mười hai theo [JEP 537](https://openjdk.org/jeps/537). | Đây vẫn là API incubator ở mốc hiện tại; kiểm tra module, JEP và tài liệu của JDK đang triển khai. |

Các ví dụ này thể hiện những kết quả khác nhau của quá trình phát triển:

- **Final ngay ở Java 22:** JEP 454 và JEP 456 đã hoàn tất; không cần bật preview chỉ vì bài học nói về Java 22.
- **Preview rồi final:** Stream Gatherers, Class-File API, Scoped Values và Flexible Constructor Bodies đã đi qua nhiều vòng. Hãy đọc JEP cuối cùng và API docs final trước khi dùng.
- **Preview bị rút:** String Templates cho thấy một preview không bảo đảm sẽ trở thành tính năng chính thức. JEP 465 từng được dự kiến cho JDK 23 nhưng đã bị rút trước khi phát hành.
- **Incubator tiếp tục kéo dài:** Vector API vẫn cần được xem như API đang thử nghiệm, dù đã có mặt trong nhiều phiên bản JDK.

## 5. Ví dụ thực hành: xác minh một đoạn code trước khi sử dụng

Giả sử bạn tìm thấy một ví dụ Stream Gatherers trong bài viết nói về Java 22. Trước khi đưa vào dự án chạy JDK 27, hãy làm theo trình tự:

1. Xác định ví dụ gắn với JEP 461, tức Stream Gatherers preview trong JDK 22.
2. Mở JEP 473 để xem vòng preview thứ hai ở JDK 23 và JEP 485 để xem phiên bản final ở JDK 24.
3. Mở tài liệu API JDK 27, tìm `java.util.stream.Gatherer`, `Gatherers` và `Stream.gather`.
4. So sánh chữ ký method và hành vi trong Javadoc JDK 27 với đoạn code cũ.
5. Biên dịch bằng JDK 27 mà không bật preview cho Stream Gatherers, sau đó chạy test.

Một ví dụ khác là String Templates. Nếu một tutorial Java 22 hướng dẫn bật preview và dùng cú pháp template, đừng coi đó là tính năng đã được giữ lại. Hãy kiểm tra JEP 459, JEP 465 và Java Language Changes của JDK 23 trở đi. Tài liệu Oracle xác nhận đề xuất đã bị rút và JDK 23 không bao gồm tính năng này.

Hai tình huống trên nhắc rằng số phiên bản trong tiêu đề bài viết không thay thế việc xác minh trạng thái của tính năng ở môi trường triển khai.

## 6. Checklist trước khi sao chép một ví dụ Java

- [ ] Xác định JDK mục tiêu của dự án và JDK thực sự dùng để biên dịch/chạy.
- [ ] Tìm JEP gốc và các JEP tiếp theo của cùng tính năng.
- [ ] Đọc release notes để xác nhận tính năng có trong bản phát hành.
- [ ] Phân loại chính xác: final, preview, incubator, deprecated hay withdrawn/removed.
- [ ] Mở Java Language Updates hoặc API Specification đúng phiên bản.
- [ ] Kiểm tra Preview API, module và package nếu tính năng chưa final.
- [ ] Xác định cờ compiler/runtime cần thiết; không nhầm `--enable-preview` với `--add-modules`.
- [ ] Biên dịch và chạy ví dụ trên JDK đích, sau đó chạy test.
- [ ] Ghi rõ phiên bản JDK và trạng thái tính năng trong tài liệu nội bộ để người đọc biết phạm vi áp dụng.

## 7. Nguồn tài liệu chính thức nên lưu lại

- [OpenJDK JEP Index](https://openjdk.org/jeps/0) — tra cứu đề xuất và lịch sử phát triển.
- [JEP 11: Incubator Modules](https://openjdk.org/jeps/11) — trạng thái và mục đích của incubator module.
- [JEP 12: Preview Features](https://openjdk.org/jeps/12) — vòng đời và cách bật preview.
- [JDK 22 Release Notes](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html) — những gì được phát hành trong JDK 22.
- [Java SE 22 Preview API](https://docs.oracle.com/en/java/javase/22/docs/api/preview-list.html) — danh sách API preview trong JDK 22.
- [Java SE 27 Preview API](https://docs.oracle.com/en/java/javase/27/docs/api/preview-list.html) — danh sách API preview trong JDK 27.
- [Java Language Changes by Release — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html) — trạng thái tính năng ngôn ngữ theo release.
- [Java SE Specifications](https://docs.oracle.com/javase/specs/index.html) — JLS và JVMS theo phiên bản.
- [JDK 22 `javac` Command](https://docs.oracle.com/en/java/javase/22/docs/specs/man/javac.html) và [JDK 22 `java` Command](https://docs.oracle.com/en/java/javase/22/docs/specs/man/java.html) — tùy chọn biên dịch và chạy.
- [JDK 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/index.html) — API của phiên bản mới nhất đã phát hành tại ngày 24/11/2026.

Khi đọc tài liệu Java 22, hãy giữ nguyên bối cảnh lịch sử của release đó, sau đó kiểm tra lại tính năng trên JDK đích. Một JEP cho biết tính năng được đề xuất và phát triển ra sao; release notes xác nhận nội dung của bản phát hành; tài liệu ngôn ngữ và API xác định cú pháp, chữ ký và hành vi mà chương trình có thể dựa vào. Kết hợp cả ba nguồn giúp tránh dùng nhầm cú pháp preview đã đổi, API incubator đã thay đổi hoặc tính năng đã bị rút khỏi Java.
