# Dòng trống, dòng cuối và lề trái trong text block Java

## 1. Ba vấn đề cần phân biệt

Từ Java 15, **text block** là cú pháp chính thức của Java để viết `String` nhiều dòng bằng cặp dấu `"""`. Tính năng này vẫn được sử dụng trong Java hiện đại (Java 17 trở lên). Khi đọc một text block, cần phân biệt:

1. **Dòng trống**: dòng không có ký tự nội dung giữa các dòng văn bản. Dòng trống tạo thêm dấu xuống dòng trong giá trị chuỗi, dù các dấu cách/tab nằm riêng trên dòng trống thường bị loại bỏ.
2. **Dòng cuối**: vị trí của dấu đóng `"""` quyết định có giữ ký tự xuống dòng `\n` ở cuối chuỗi hay không. Đặt dấu đóng trên dòng riêng thường giữ `\n` của dòng nội dung trước đó.
3. **Lề trái**: Java loại bỏ phần thụt lề chung không có ý nghĩa (*incidental indentation*). Dòng chứa dấu đóng, khi nó nằm riêng, cũng ảnh hưởng đến lượng thụt lề bị loại bỏ.

**Phân biệt quan trọng:** Dấu kết thúc dòng **ngay sau `"""` mở** là bắt buộc trong cú pháp nhưng **không tự trở thành `\n` đầu chuỗi**. Những dòng trống thực sự *tiếp theo* mới có thể tạo `\n` đầu chuỗi.

## 2. Java xử lý khoảng trắng trong text block theo thứ tự nào?

Khi biên dịch text block, Java xác định nội dung từ **sau dấu kết thúc dòng của dấu mở** đến **ngay trước ba dấu nháy kép của dấu đóng**. Sau đó, Java xử lý theo thứ tự:

1. **Chuẩn hóa dấu kết thúc dòng:** CR và CRLF trong nội dung được chuẩn hóa thành LF, tức ký tự `\n` trong giá trị Java.
2. **Loại bỏ khoảng trắng không đáng kể:** Java tính lề chung và xóa phần thụt lề chung ở đầu các dòng; khoảng trắng ở cuối dòng bị loại bỏ. Các dòng chỉ có khoảng trắng được xem là dòng trống khi xác định lề chung.
3. **Diễn giải escape sequence:** Các escape như `\n`, `\s` hoặc dấu gạch chéo ngược nối dòng (`\` ngay trước xuống dòng) được xử lý **sau** bước loại bỏ khoảng trắng.

Thứ tự này giải thích vì sao một dấu cách gõ trực tiếp ở cuối dòng thường không được giữ, trong khi `\s` có thể giữ được đúng một dấu cách. Đồng thời, khoảng trắng dùng để căn mã nguồn không nhất thiết xuất hiện trong chuỗi kết quả.

## 3. Dòng trống: một dòng trống tạo thêm một dấu xuống dòng

Xét ví dụ:

~~~java
String message = """
        dòng A

        dòng B
        """;
~~~

Ở giữa `dòng A` và `dòng B` có **một dòng trống**. Giá trị thực của chuỗi là:

~~~text
dòng A\n\ndòng B\n
~~~

Trong cách biểu diễn trên, `\n` là **hai ký tự hiển thị** dùng để mô tả một dấu xuống dòng thực. Hai `\n` liên tiếp giữa A và B có nghĩa: kết thúc dòng A, rồi kết thúc dòng trống. Dấu `\n` cuối tồn tại vì dấu đóng ở dòng tiếp theo.

### Dòng trống ở đầu

~~~java
String leadingBlank = """

        A""";
~~~

Giá trị là `"\nA"`. Dấu kết thúc dòng bắt buộc sau `"""` mở không được tính; dòng trống bổ sung ngay phía dưới nó mới tạo `\n` đầu tiên.

### Dòng trống chỉ có dấu cách hoặc tab

Một dòng nằm giữa hai dòng nội dung dù có chứa một ít space/tab vẫn là dòng **trống về mặt nội dung**. Java loại bỏ những ký tự khoảng trắng thừa trên dòng đó khi xử lý text block, nhưng **giữ ký tự xuống dòng** đánh dấu kết thúc dòng trống.

Nếu bạn thực sự muốn giữ một dấu cách ở dòng trống (hoặc cuối dòng), hãy dùng escape `\s` một cách có chủ đích; đừng dựa vào các dấu cách cuối dòng khó quan sát trong IDE.

## 4. Dòng cuối: dấu đóng quyết định `\n` kết thúc

So sánh hai cách đặt dấu đóng:

~~~java
String withFinalNewline = """
        A
        B
        """;

String withoutFinalNewline = """
        A
        B""";
~~~

| Trường hợp | Giá trị chuỗi | Lý do |
| --- | --- | --- |
| `withFinalNewline` | `"A\nB\n"` | Sau `B` có một dấu kết thúc dòng **trước** dấu đóng ở dòng riêng. |
| `withoutFinalNewline` | `"A\nB"` | Dấu đóng đặt ngay sau `B`; giữa `B` và dấu đóng không có xuống dòng. |

Dấu đóng `"""` đặt ở dòng riêng **không phải** là ký tự thuộc chuỗi; chính ký tự kết thúc dòng của dòng `B` mới tạo `\n` cuối. Dấu đóng đặt cùng dòng với nội dung cũng không tự thêm xuống dòng.

Một dòng trống ngay trước dấu đóng sẽ tạo **thêm một `\n`**:

~~~java
String twoFinalNewlines = """
        A

        """;
~~~

Giá trị ở đây là `"A\n\n"`. Nếu chỉ muốn `"A\n"` thì không chèn dòng trống bổ sung.

### Text block rỗng và chỉ chứa một dấu xuống dòng

~~~java
String empty = """
        """;

String oneNewline = """

        """;
~~~

`empty` có giá trị `""`, độ dài 0. `oneNewline` có giá trị `"\n"`, độ dài 1. Như vậy, một text block không mặc định chứa ít nhất một `\n`; số dấu xuống dòng phụ thuộc chính xác vào các dòng nội dung thực tế.

### Khi muốn giữ dấu đóng ở dòng riêng nhưng bỏ `\n` cuối

Escape **nối dòng** có thể bỏ dấu xuống dòng vật lý cuối nội dung:

~~~java
String joined = """
        A
        B\
        """;
~~~

Giá trị là `"A\nB"`. Dấu `\` phải đứng **ngay trước** dấu kết thúc dòng để hoạt động như nối dòng; không để dấu cách ở giữa. Khi cấu trúc cho phép, đặt dấu đóng ngay sau nội dung thường dễ đọc hơn; nối dòng hữu ích nếu muốn giữ cách trình bày dấu đóng trên dòng riêng.

## 5. Lề trái: Java loại bỏ thụt lề chung như thế nào?

Java cho phép thụt lề text block phù hợp với mã nguồn nhưng không bắt chuỗi kết quả nhận toàn bộ dấu cách đó. Để xác định mức lề chung, Java xét:

- Số ký tự khoảng trắng đầu dòng của **các dòng nội dung không trống**.
- Số ký tự khoảng trắng đứng trước dấu đóng **nếu dấu đóng ở dòng riêng**.
- Dòng chỉ chứa khoảng trắng (ngoài dòng dấu đóng được xét riêng) **không làm giảm mức lề chung**.

Java lấy mức thụt lề nhỏ nhất trong các dòng được xét và loại bỏ tương ứng ở đầu mỗi dòng nội dung. Khoảng thụt lề *tương đối* giữa các dòng vẫn được bảo toàn.

### Dấu đóng thẳng hàng với nội dung ít thụt nhất

~~~java
String normal = """
        root
            child
        """;
~~~

Dòng `root` và dấu đóng cùng lề trái; `child` thụt thêm bốn dấu cách. Giá trị là `"root\n    child\n"`: lề chung bị xóa, còn bốn dấu cách tương đối trước `child`.

### Dấu đóng lùi trái để chủ động giữ lề trong chuỗi

~~~java
String keepLeft = """
        root
            child
    """;
~~~

Lần này dấu đóng đứng **trái hơn** `root` bốn dấu cách. Vì vậy, mức lề chung bị xóa nhỏ đi, kết quả là `"    root\n        child\n"`. Bốn dấu cách đầu `root` và tám dấu cách đầu `child` là **một phần của giá trị String**.

Hệ quả thực tế: thay đổi riêng vị trí dấu đóng có thể làm thay đổi toàn bộ lề trái của kết quả, ngay cả khi các dòng văn bản giữ nguyên. Nếu cả nội dung lẫn dấu đóng cùng dịch chuyển một lượng thụt lề, khoảng trắng tương đối thường giữ nguyên.

**Lưu ý về tab:** Java xử lý các ký tự khoảng trắng đầu dòng theo ký tự, không theo độ rộng hiển thị của tab trong trình soạn thảo. Để tránh sai lệch khó thấy, nên thống nhất dùng dấu cách khi định dạng text block.

## 6. Ví dụ Java 17+ chạy độc lập và quan sát chính xác

Tạo tệp **`TextBlockWhitespaceDemo.java`** với toàn bộ mã sau:

~~~java
public class TextBlockWhitespaceDemo {
    public static void main(String[] args) {
        String innerBlank = """
                A

                B
                """;

        String withFinal = """
                A
                B
                """;

        String noFinal = """
                A
                B""";

        String leadingBlank = """

                A""";

        String keepMargin = """
                left
                    deeper
            """;

        String trailingSpace = """
                X\s
                """;

        String noTrailingViaBackslash = """
                X\
                """;

        String empty = """
                """;

        show("innerBlank", innerBlank);
        show("withFinal", withFinal);
        show("noFinal", noFinal);
        show("leadingBlank", leadingBlank);
        show("keepMargin", keepMargin);
        show("trailingSpace", trailingSpace);
        show("noTrailingViaBackslash", noTrailingViaBackslash);
        show("empty", empty);
    }

    private static void show(String title, String value) {
        String visible = value.replace(" ", ".").replace("\n", "\\n");
        System.out.println(title + " = [" + visible + "]");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 TextBlockWhitespaceDemo.java
java TextBlockWhitespaceDemo
~~~

Kết quả stdout (đã kiểm tra bằng trình biên dịch Java ở chế độ ngôn ngữ 17):

~~~text
innerBlank = [A\n\nB\n]
withFinal = [A\nB\n]
noFinal = [A\nB]
leadingBlank = [\nA]
keepMargin = [....left\n........deeper\n]
trailingSpace = [X.\n]
noTrailingViaBackslash = [X]
empty = []
~~~

Hàm `show` giúp kết quả dễ kiểm chứng: mỗi dấu cách thực được thay bằng dấu chấm `.`, mỗi ký tự xuống dòng thực được hiển thị thành `\n`. Hàm chỉ biến đổi **bản hiển thị**; giá trị text block ban đầu không bị sửa đổi.

Đọc kết quả:

- `innerBlank`: giữa A và B có một dòng trống; chuỗi vẫn có `\n` cuối.
- `withFinal` / `noFinal`: cùng nội dung A, B nhưng khác nhau đúng một `\n` cuối.
- `leadingBlank`: dòng trống ngay đầu nội dung tạo `\n` đầu.
- `keepMargin`: dấu đóng nằm trái hơn hai dòng nội dung, nên chuỗi giữ bốn/tám dấu cách tương ứng.
- `trailingSpace`: `\s` giữ một dấu cách ngay trước `\n`; dấu cách này hiện thành `.`.
- `noTrailingViaBackslash`: escape nối dòng xóa `\n` cuối.
- `empty`: có dấu mở và đóng hợp lệ nhưng chuỗi hoàn toàn rỗng.

## 7. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Coi dấu xuống dòng bắt buộc sau `"""` mở là `\n` đầu chuỗi | Dự đoán sai số dòng và độ dài | Chỉ tính các dấu xuống dòng trong **nội dung** sau dấu mở. |
| Nghĩ dòng trống giữa hai dòng văn bản sẽ tự bị xóa | Thiếu một `\n` khi dự đoán kết quả | Dòng trống vẫn giữ dấu kết thúc dòng; chỉ khoảng trắng thừa trên dòng bị loại bỏ. |
| Chuyển `"""` đóng xuống dòng riêng chỉ để đẹp mã | Vô tình thêm `\n` cuối | Đặt dấu đóng cùng dòng nội dung nếu không muốn `\n` cuối. |
| Thụt dấu đóng lùi trái mà không chú ý | Chuỗi giữ thêm khoảng trắng ở đầu các dòng | Kiểm tra lề nhỏ nhất trong nội dung và dòng dấu đóng. |
| Dùng nhiều tab và space để căn dòng | Lề nhìn bằng mắt có thể không trùng số ký tự bị loại bỏ | Ưu tiên dấu cách nhất quán và kiểm tra giá trị thực. |
| Gõ dấu cách cuối dòng để cố giữ chúng trong chuỗi | Các dấu cách đó thường bị chuẩn hóa bỏ | Dùng `\s` khi cần biểu diễn dấu cách cuối dòng một cách rõ ràng. |
| Dùng `\` nối dòng rồi thêm dấu cách sau nó | Dấu xuống dòng không được nối như dự tính | Đặt `\` ngay sát ký tự kết thúc dòng. |

## 8. Quy tắc tự kiểm tra nhanh

Khi không chắc một text block tạo ra chuỗi nào, hãy thực hiện theo thứ tự: **xác định đoạn nội dung thực** (bỏ dấu mở và dấu đóng), **đánh dấu mọi dòng trống và xuống dòng cuối**, **xác định mức thụt lề chung kể cả dòng dấu đóng**, rồi mới **áp dụng escape sequence**. Cách kiểm tra này đúng với ngữ nghĩa text block hiện hành, không cần dựa vào cú pháp preview hoặc tính năng đã lỗi thời.

Tài liệu chuẩn của ngôn ngữ: [Java Language Specification, `3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se27/html/jls-3.html#jls-3.10.6).