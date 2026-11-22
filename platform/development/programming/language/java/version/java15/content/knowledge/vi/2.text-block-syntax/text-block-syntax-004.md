# Vị trí dấu đóng và ký tự xuống dòng cuối trong Java text block

## 1. Điều cần nắm

Text block là literal chuỗi nhiều dòng, được viết bằng ba dấu nháy kép mở `"""` và ba dấu nháy kép đóng `"""`. Từ Java 15, đây là cú pháp chính thức; Java 17, 21 và các phiên bản Java hiện đại tiếp tục hỗ trợ. Điểm dễ nhầm nhất là **vị trí của dấu đóng quyết định liệu chuỗi kết quả có chứa ký tự xuống dòng cuối (`\n`) hay không**.

Hai cách viết dưới đây khác nhau về dữ liệu:

```java
String withFinalNewline = """
        hello
        """;

String withoutFinalNewline = """
        hello""";
```

- `withFinalNewline` có giá trị `"hello\n"`: dòng chứa `hello` đã kết thúc bằng newline, còn dấu đóng nằm ở dòng kế tiếp.
- `withoutFinalNewline` có giá trị `"hello"`: dấu đóng nằm ngay sau chữ `hello`, nên không có newline cuối.

Đây là **giá trị thật của String**, ảnh hưởng tới việc so sánh chuỗi, ghi file, tạo payload và kiểm thử. Khoảng trắng thụt lề trong mã nguồn còn chịu quy tắc xử lý *incidental indentation* của text block; cần xét riêng với newline cuối.

## 2. Dấu mở, nội dung và dấu đóng

Một text block có cấu trúc:

```java
String message = """
        Dòng thứ nhất
        Dòng thứ hai
        """;
```

Một dấu xuống dòng thực sự **bắt buộc xuất hiện sau ba dấu nháy kép mở** (có thể có khoảng trắng trước dấu xuống dòng đó). Dòng bắt đầu bằng nội dung sau dấu xuống dòng mở đầu, và newline ngay sau dấu mở **không được thêm vào đầu chuỗi**. Dấu đóng có thể đứng ở dòng riêng hoặc ngay sau nội dung cuối. Dấu đóng không bắt buộc có newline ngay trước nó.

Cách không hợp lệ:

```java
// Không biên dịch: nội dung bắt đầu ngay sau dấu mở.
String invalid = """hello""";
```

Nếu chỉ cần một dòng, dùng literal thông thường `"hello"` là đơn giản nhất; text block phát huy tác dụng khi chứa nhiều dòng hoặc nội dung có nhiều dấu nháy kép.

## 3. Dấu đóng trên dòng riêng: có newline cuối

```java
String text = """
        first
        second
        """;
```

Giá trị thực là `"first\nsecond\n"`. Khi đọc theo từng dòng nguồn, sau `first` có xuống dòng và sau `second` cũng có xuống dòng. Dấu đóng ở dòng bên dưới không xóa newline trước nó.

Ký tự xuống dòng của text block được chuẩn hóa thành LF (`'\n'`, U+000A), kể cả khi file mã nguồn dùng CRLF. Do đó, nếu một giao thức yêu cầu CRLF (`"\r\n"`), không thể suy luận rằng text block sẽ tự giữ CRLF của file nguồn.

## 4. Dấu đóng ngay sau nội dung: không có newline cuối

```java
String text = """
        first
        second""";
```

Giá trị thực là `"first\nsecond"`. Không có dấu xuống dòng nào giữa `second` và dấu đóng, vì vậy `text.endsWith("\n")` trả về `false`.

Có thể áp dụng cho chuỗi SQL, JSON, văn bản hoặc output cần kiểm soát chính xác ký tự kết thúc. Tuy nhiên, đừng mặc định rằng mọi công cụ nhận dữ liệu đều bỏ qua newline: khi độ chính xác quan trọng, hãy kiểm tra giá trị cuối cùng.

## 5. Ví dụ chạy được trên Java 17+

Tạo file `TextBlockEndingDemo.java`:

```java
public class TextBlockEndingDemo {
    public static void main(String[] args) {
        String a = """
                alpha
                beta
                """;

        String b = """
                alpha
                beta""";

        System.out.println(a.equals("alpha\nbeta\n"));
        System.out.println(b.equals("alpha\nbeta"));
        System.out.println(a.endsWith("\n"));
        System.out.println(b.endsWith("\n"));
        System.out.println(a.length());
        System.out.println(b.length());
    }
}
```

Biên dịch và chạy:

```bash
javac TextBlockEndingDemo.java
java TextBlockEndingDemo
```

Output chính xác:

```text
true
true
true
false
11
10
```

Độ dài của `"alpha\nbeta\n"` là 11 ký tự UTF-16: `alpha` (5) + `\n` (1) + `beta` (4) + `\n` (1). Chuỗi không có newline cuối dài 10 ký tự. Cả hai ví dụ có cùng nội dung nhìn thấy khi hiển thị trên nhiều công cụ, nên kiểm tra `equals`, `endsWith` hoặc mã ký tự sẽ chắc chắn hơn quan sát bằng mắt.

## 6. Vị trí dấu đóng còn ảnh hưởng thụt lề

Java loại bỏ khoảng trắng thụt lề chung được xem là *incidental indentation*, giúp viết text block gọn trong mã nguồn mà không đưa toàn bộ khoảng trắng căn lề vào giá trị. Dấu đóng nằm ở dòng riêng cũng tham gia xác định lề chung.

Ví dụ:

```java
String normal = """
        left
          right
        """;
```

Giá trị là `"left\n  right\n"`: sau khi loại lề chung, `right` còn hai dấu cách đứng trước.

Nếu dịch dấu đóng sang phải hoặc trái trong dòng riêng, mức lề chung có thể thay đổi. Vì vậy, **di chuyển dấu đóng vừa có thể tác động tới newline cuối, vừa có thể tác động tới số dấu cách ở đầu các dòng**. Khi chỉ muốn loại bỏ newline cuối, đặt dấu đóng ngay sau ký tự cuối của nội dung và kiểm tra chuỗi kết quả; khi cần giữ khoảng trắng đầu dòng một cách chính xác, cân nhắc `\s` hoặc các phép dựng chuỗi rõ nghĩa.

Không nhầm khoảng trắng với newline: `"hello "`, `"hello\n"` và `"hello"` là ba chuỗi khác nhau.

## 7. Cách điều khiển ký tự cuối một cách có chủ ý

### 7.1. Muốn có một newline cuối

Để dấu đóng ở dòng kế tiếp sau dòng nội dung cuối:

```java
String payload = """
        success
        """;
// Giá trị: "success\n"
```

### 7.2. Muốn không có newline cuối

Đặt dấu đóng ngay sau nội dung:

```java
String payload = """
        success""";
// Giá trị: "success"
```

### 7.3. Muốn kết thúc bằng nhiều newline

Có thể chèn thêm các dòng trống trước dấu đóng. Cách viết dưới đây có hai newline sau `success`:

```java
String payload = """
        success

        """;
// Giá trị: "success\n\n"
```

Nếu việc đếm các dòng trống trong mã nguồn trở nên khó đọc, hãy viết rõ các ký tự kết thúc bằng phép nối chuỗi:

```java
String payload = """
        success"""+ "\n\n";
```

### 7.4. Muốn giữ dòng mã nguồn nhưng không đưa newline vào chuỗi

Dấu gạch chéo ngược `\` ngay trước dấu xuống dòng trong text block là *line continuation*: nó loại bỏ xuống dòng đó khỏi giá trị. Đây là cú pháp được hỗ trợ, nhưng chỉ dùng khi giúp mã dễ đọc; vị trí dấu đóng thường rõ ràng hơn nếu mục đích chỉ là bỏ newline cuối.

```java
String compact = """
        abc\
        def
        """;
// Giá trị: "abcdef\n"
```

Dòng chứa `abc\` không tạo dấu xuống dòng trong chuỗi; newline sau `def` vẫn còn do dấu đóng ở dòng riêng.

## 8. Các lỗi phổ biến và cách kiểm tra

1. **Tưởng text block luôn thêm newline cuối.** Sai: chỉ có newline cuối nếu nội dung nguồn có newline ngay trước dấu đóng (hoặc dùng escape/dựng chuỗi tạo ra newline). So sánh ví dụ dấu đóng cùng dòng và khác dòng.
2. **Tưởng dấu đóng trên dòng riêng tự tạo ra một dòng trống.** Sai: dấu xuống dòng sau dòng cuối chỉ thêm một `\n`; muốn một dòng trống cuối đúng nghĩa cần thêm một newline nữa.
3. **Chỉ nhìn `System.out.println(text)` để kết luận.** `println` tự thêm newline, làm khó phân biệt newline đã nằm trong `text` hay do phương thức in ra. Dùng `text.endsWith("\n")`, `length()` và `equals(...)`.
4. **Cho rằng kết thúc dòng theo hệ điều hành được giữ nguyên.** Sai: newline nguồn trong text block chuẩn hóa thành LF. Cần CRLF thì dựng rõ `"\r\n"`.
5. **Dời dấu đóng mà không kiểm tra indentation.** Khi dấu đóng đứng riêng, vị trí thụt lề có thể làm thay đổi lề chung được loại bỏ. Hãy chạy so sánh chuỗi kỳ vọng sau khi chỉnh sửa.

Một kiểm thử ngắn, không phụ thuộc vào output hiển thị:

```java
String query = """
        SELECT 1""";
if (!query.equals("SELECT 1")) {
    throw new AssertionError("Unexpected ending or indentation");
}
```

## 9. Ghi nhớ

- Dấu mở `"""` phải có xuống dòng ngay sau nó; newline mở đầu không trở thành ký tự đầu chuỗi.
- **Dấu đóng ở dòng riêng sau nội dung cuối:** newline ở cuối dòng nội dung được giữ trong chuỗi (thường là `\n`).
- **Dấu đóng ngay sau nội dung cuối:** không có newline cuối do cách đặt dấu đóng.
- Dấu đóng trên dòng riêng cũng có thể tham gia xác định incidental indentation.
- Hãy kiểm tra giá trị chuỗi bằng so sánh và độ dài khi payload cần chính xác từng ký tự.

Những quy tắc này thuộc cú pháp text block hiện hành của Java, phù hợp để sử dụng trên Java 17+ và các phiên bản Java mới hơn.