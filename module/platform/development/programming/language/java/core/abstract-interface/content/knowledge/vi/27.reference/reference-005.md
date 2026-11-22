# Tra cứu Java Language Specification và Javadoc theo chủ đề

Khi cần xác minh một quy tắc Java, hãy bắt đầu bằng cách xác định câu hỏi thuộc về **ngôn ngữ Java** hay **một API cụ thể**. Java Language Specification (JLS) mô tả cú pháp và ngữ nghĩa của ngôn ngữ; Javadoc của Java SE API mô tả hợp đồng sử dụng của lớp, interface, constructor, field và phương thức thư viện. Hai nguồn bổ sung cho nhau nhưng trả lời các loại câu hỏi khác nhau.

## 1. Chọn đúng nguồn

| Câu hỏi cần trả lời | Nguồn nên tra trước | Ví dụ chủ đề |
| --- | --- | --- |
| Mã nguồn có hợp lệ về cú pháp và kiểu không? | JLS | kiểu generic, chuyển đổi kiểu, phạm vi biến, overload phương thức |
| Phương thức nào được chọn tại thời điểm biên dịch? | JLS | overload resolution, method invocation, type inference |
| Phương thức instance nào được gọi lúc chạy? | JLS | overriding, dynamic dispatch, class initialization |
| Phương thức thư viện nhận tham số nào, trả gì, ném exception nào? | Javadoc của API | `List.get`, `Map.get`, `Files.readString` |
| Giá trị trả về có thể thay đổi được không? Điều gì xảy ra với `null`? | Javadoc của API cụ thể | `List.of`, `Optional.of`, `Map.copyOf` |
| Hành vi về thread, khóa và thứ tự bộ nhớ được quy định ra sao? | JLS và Javadoc liên quan | memory model, `synchronized`, `volatile`, concurrency utilities |
| Một lớp có constructor hoặc phương thức nào? | Javadoc của lớp đó | `StringBuilder`, `Path`, `CompletableFuture` |

Quy tắc ngôn ngữ và hợp đồng thư viện có thể cùng xuất hiện trong một vấn đề. Ví dụ, JLS xác định cách Java phân giải lời gọi phương thức; Javadoc xác định phương thức thư viện được chọn làm gì, các điều kiện đầu vào và ngoại lệ được ghi trong hợp đồng.

## 2. Các nguồn chính thức nên lưu

- **JLS Java SE 17:** https://docs.oracle.com/javase/specs/jls/se17/html/index.html
- **Trang chỉ mục đặc tả Java SE:** https://docs.oracle.com/javase/specs/
- **Java SE 17 API Specification:** https://docs.oracle.com/en/java/javase/17/docs/api/index.html
- **Javadoc của `java.util.List`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html

Các liên kết ở trên dùng phiên bản Java SE 17 làm ví dụ tham chiếu. Khi dự án chạy Java 21, 25 hoặc phiên bản khác, hãy mở JLS/API docs tương ứng với phiên bản cần xác minh. Không suy luận rằng một API có trong phiên bản mới cũng tồn tại trong phiên bản cũ.

## 3. Tra JLS theo chủ đề

JLS được chia thành các chương có chủ đề cụ thể. Nếu đã biết loại quy tắc cần tìm, mở chương liên quan trước rồi tìm thuật ngữ trong trang đó.

| Chủ đề | Chương JLS thường liên quan |
| --- | --- |
| Kiểu, giá trị, biến và generic types | Chương 4 — Types, Values, and Variables |
| Chuyển đổi kiểu, boxing/unboxing và chuyển đổi trong ngữ cảnh | Chương 5 — Conversions and Contexts |
| Tên, phạm vi, truy cập và phân giải tên | Chương 6 — Names |
| Package và module | Chương 7 — Packages and Modules |
| Class, constructor, method, overriding và hiding | Chương 8 — Classes |
| Khai báo và thành viên interface | Chương 9 — Interfaces |
| Mảng | Chương 10 — Arrays |
| Exception và checked exceptions | Chương 11 — Exceptions |
| Thực thi và khởi tạo class/interface | Chương 12 — Execution |
| Tương thích nhị phân | Chương 13 — Binary Compatibility |
| Câu lệnh, khối và điều khiển luồng | Chương 14 — Blocks, Statements, and Patterns (tùy phiên bản) |
| Biểu thức, gọi phương thức, lambda và toán tử | Chương 15 — Expressions |
| Definite assignment | Chương 16 — Definite Assignment |
| Thread, monitor, synchronization và memory model | Chương 17 — Threads and Locks |
| Type inference | Chương 18 — Type Inference |
| Ngữ pháp cú pháp | Chương 19 — Syntax |

Tên chương và nội dung chi tiết có thể thay đổi giữa các phiên bản JLS. Hãy dùng mục lục của đúng phiên bản; nếu tìm theo số mục như `15.12`, xác nhận số mục đó trong phiên bản đang đọc.

### Cách tìm một quy tắc trong JLS

1. Viết câu hỏi thành một hành vi cụ thể: “Vì sao lời gọi này chọn overload A thay vì overload B?” hoặc “Khi nào static initializer chạy?”.
2. Chuyển câu hỏi thành thuật ngữ của ngôn ngữ: `method invocation`, `overload resolution`, `class initialization`, `type inference` hoặc `definite assignment`.
3. Mở chương phù hợp trong JLS và tìm thuật ngữ bằng tìm kiếm trên trang (`Ctrl+F`).
4. Đọc toàn bộ mục chứa định nghĩa, các điều kiện áp dụng và các mục được tham chiếu; đừng dựa riêng vào một câu trích rời khỏi ngữ cảnh.
5. So sánh với đoạn mã nhỏ có thể biên dịch. Nếu đang giải thích một lỗi biên dịch, phân biệt rõ kết luận từ quy tắc ngôn ngữ với thông báo cụ thể do compiler đưa ra.

Ví dụ truy vấn web có thể dùng:

```text
site:docs.oracle.com/javase/specs/jls/se17/html/ "method invocation"
site:docs.oracle.com/javase/specs/jls/se17/html/ "class initialization"
site:docs.oracle.com/javase/specs/jls/se17/html/ "type inference"
```

## 4. Tra Javadoc theo lớp hoặc phương thức

Javadoc của một API thường cho biết:

- **Declaration/signature:** tên lớp, kiểu tham số, kiểu trả về, modifier và generic type.
- **Description:** phương thức thực hiện việc gì và ý nghĩa của kết quả.
- **Parameters:** điều kiện hoặc ý nghĩa của từng đối số.
- **Returns:** kết quả trả về, bao gồm các trường hợp đặc biệt được mô tả.
- **Throws:** ngoại lệ có thể hoặc được quy định sẽ ném theo điều kiện nào.
- **API notes, implementation requirements hoặc implementation notes:** hướng dẫn và yêu cầu bổ sung nếu có.
- **Since:** phiên bản Java SE mà API được thêm vào, nếu trang tài liệu cung cấp thông tin này.
- **See Also / inherited methods:** liên kết đến khái niệm hoặc API liên quan.

Khi kiểm tra phương thức, đừng chỉ đọc phần mô tả đầu trang. Tìm đúng overload theo kiểu tham số và đọc phần `Returns`, `Throws` cùng ghi chú liên quan. Hai overload có tên giống nhau có thể có điều kiện hoặc kết quả khác nhau.

Ví dụ truy vấn:

```text
site:docs.oracle.com/en/java/javase/17/docs/api/ "java.util.List" "unmodifiable"
site:docs.oracle.com/en/java/javase/17/docs/api/ "Files.readString"
site:docs.oracle.com/en/java/javase/17/docs/api/ "Optional.of" "NullPointerException"
```

Khi dùng công cụ tìm kiếm, ưu tiên kết quả từ tài liệu Oracle chính thức hoặc nguồn tài liệu chính thức của JDK đang dùng. Blog và câu trả lời diễn đàn hữu ích để tìm từ khóa hoặc ví dụ, nhưng nên quay lại đặc tả/Javadoc để xác nhận hợp đồng.

## 5. Quy trình tra cứu lặp lại được

### Bước 1 — Thu hẹp câu hỏi

Ghi lại đoạn mã tối thiểu, phiên bản Java, kết quả quan sát được và điều cần xác minh. Tránh câu hỏi chung như “Java hoạt động thế nào?”; thay bằng một câu hỏi kiểm chứng được, ví dụ “`List.of` có cho phép thêm phần tử sau khi tạo không?”.

### Bước 2 — Xác định lớp nguồn

- Nếu câu hỏi nói về tính hợp lệ của mã, chọn phương thức nào, phạm vi, kiểu hoặc thứ tự khởi tạo, bắt đầu với JLS.
- Nếu câu hỏi nói về hành vi của thư viện, bắt đầu với Javadoc của lớp/phương thức.
- Nếu có cả hai, đọc cả hai nguồn và ghi rõ nguồn nào hỗ trợ kết luận nào.

### Bước 3 — Khóa phiên bản

Kiểm tra phiên bản source/target, JDK dùng để biên dịch và JDK chạy chương trình. Mở tài liệu cùng phiên bản để tránh dùng API hoặc quy tắc được bổ sung sau đó. Nếu đang nghiên cứu khác biệt phiên bản, so sánh hai bản tài liệu có ghi rõ phiên bản thay vì trộn chúng.

### Bước 4 — Đọc hợp đồng, không chỉ đọc ví dụ

Tìm các từ chỉ điều kiện như “must”, “may”, “throws”, “unless”, “if”, “not supported” và các trường hợp biên. Ví dụ có thể chỉ minh họa một trường hợp; phần đặc tả hoặc Javadoc mới xác định phạm vi hành vi được cam kết.

### Bước 5 — Kiểm chứng bằng chương trình nhỏ

Biên dịch và chạy ví dụ tối thiểu khi câu hỏi có thể kiểm chứng thực nghiệm. Kết quả chạy giúp xác nhận rằng ví dụ tái hiện được hiện tượng, nhưng một lần chạy không thay thế đặc tả: hành vi có thể phụ thuộc vào phiên bản, môi trường hoặc phần chưa được API bảo đảm.

### Bước 6 — Ghi lại kết luận và căn cứ

Ghi tên nguồn, phiên bản, chương/mục JLS hoặc lớp/phương thức Javadoc, quy tắc liên quan và ví dụ tối thiểu. Khi chia sẻ kết quả trong review hoặc tài liệu nội bộ, liên kết trực tiếp đến mục chính xác thay vì chỉ ghi “theo tài liệu Java”.

## 6. Ví dụ: xác minh `List.of` có thể sửa đổi hay không

Câu hỏi: danh sách được tạo bằng `List.of("Ada", "Lin")` có cho phép gọi `add` không?

**Nguồn cần đọc:** Javadoc của `java.util.List`, phần phương thức `of`. Đây là hành vi của API thư viện, nên Javadoc là nguồn trực tiếp để kiểm tra hợp đồng. JLS có thể giải thích cách lời gọi generic được phân giải, nhưng không định nghĩa hợp đồng cụ thể của `List.of`.

Một ví dụ Java 17+ hoàn chỉnh:

```java
import java.util.List;

public class ListOfLookupDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Ada", "Lin");

        try {
            names.add("Grace");
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("List.of result is unmodifiable");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac ListOfLookupDemo.java
java ListOfLookupDemo
```

Stdout chính xác:

```text
List.of result is unmodifiable
```

Ví dụ này minh họa hành vi mong đợi theo hợp đồng API: các list do `List.of` tạo ra là unmodifiable, nên thao tác thay đổi như `add` ném `UnsupportedOperationException`. Không nên khái quát rằng mọi đối tượng triển khai `List` đều không thể sửa đổi; hãy kiểm tra cách tạo và hợp đồng của từng API. Trong chương trình thực tế, không cần cố gọi `add` để “thử” nếu đã đọc tài liệu và biết rõ hợp đồng.

## 7. Phân biệt điều được bảo đảm và điều tình cờ quan sát được

Khi đọc nguồn, hãy phân loại kết luận:

- **Được quy định/bảo đảm:** hành vi được mô tả trong quy tắc JLS hoặc hợp đồng API áp dụng.
- **Không được quy định cụ thể:** tài liệu không cam kết một kết quả duy nhất; tránh phụ thuộc vào kết quả đó.
- **Đặc thù triển khai:** hành vi đến từ compiler/JVM cụ thể nhưng không nên coi là quy tắc Java chung.
- **Quan sát từ ví dụ:** kết quả thực tế của một lần chạy, hữu ích để tái hiện nhưng cần đối chiếu nguồn quy phạm.

Đặc biệt chú ý các cụm “unspecified”, “implementation-dependent” và “implementation-specific” nếu chúng xuất hiện trong tài liệu. Chúng có ý nghĩa khác nhau; không nên tự diễn giải tất cả thành “Java luôn làm như vậy”.

## 8. Những lỗi tra cứu thường gặp

| Lỗi | Cách tránh |
| --- | --- |
| Dùng bài blog làm căn cứ cuối cùng | Dùng bài viết để tìm thuật ngữ, rồi xác minh trong JLS hoặc Javadoc chính thức. |
| Đọc tài liệu của phiên bản khác | Kiểm tra phiên bản JDK và mở đúng bản tài liệu; so sánh phiên bản có chủ đích nếu cần. |
| Tra JLS để tìm hợp đồng của một phương thức thư viện | Mở Javadoc của đúng lớp và overload trước. |
| Tra Javadoc để giải thích quy tắc biên dịch tổng quát | Tìm quy tắc tương ứng trong JLS, chẳng hạn overload resolution hoặc conversion. |
| Chỉ đọc tên phương thức hoặc phần mô tả ngắn | Đọc declaration, parameters, returns, throws và ghi chú liên quan. |
| Nhầm kết quả của một compiler thành quy tắc ngôn ngữ | Phân biệt thông báo compiler với quy tắc normative trong JLS. |
| Khái quát một ví dụ cho toàn bộ API | Xác định chính xác overload, điều kiện đầu vào và các trường hợp được bảo đảm. |
| Trích dẫn trang tài liệu chung chung | Ghi phiên bản và liên kết tới đúng chương/mục hoặc phương thức. |

## 9. Checklist trước khi kết luận

- [ ] Câu hỏi đã được viết thành hành vi cụ thể cần xác minh.
- [ ] Đã phân biệt quy tắc ngôn ngữ với hợp đồng API.
- [ ] Đã mở tài liệu chính thức và kiểm tra phiên bản Java liên quan.
- [ ] Đã đọc mục chính cùng các điều kiện, ngoại lệ và tham chiếu liên quan.
- [ ] Nếu có ví dụ, mã tối thiểu đã biên dịch/chạy hoặc đã ghi rõ vì sao không thể chạy độc lập.
- [ ] Kết quả thực nghiệm được phân biệt với điều mà tài liệu bảo đảm.
- [ ] Kết luận có liên kết đến đúng mục JLS hoặc Javadoc để người khác kiểm tra lại.

Thói quen quan trọng nhất là tìm đúng nguồn cho đúng câu hỏi: **JLS để xác minh quy tắc của ngôn ngữ; Javadoc để xác minh hợp đồng của API**. Chốt phiên bản, đọc điều kiện và ngoại lệ, rồi kiểm chứng bằng ví dụ nhỏ khi phù hợp.
