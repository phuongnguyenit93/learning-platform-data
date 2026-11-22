# Dùng biến final hoặc effectively final trong try-with-resources

## Mục tiêu

Từ Java 9, câu lệnh try-with-resources có thể nhận một biến tài nguyên đã được khai báo và khởi tạo ở bên ngoài:

~~~java
BufferedReader reader = createReader();

try (reader) {
    // Đọc dữ liệu
}
~~~

Cách viết này hữu ích khi tài nguyên cần được chuẩn bị trước khối try, được truyền vào từ một nơi khác, hoặc cần được kiểm tra trước khi mở. Biến được đặt trong phần khai báo tài nguyên phải là final hoặc effectively final và kiểu của nó phải triển khai AutoCloseable.

## 1. final và effectively final

Hai khái niệm này mô tả việc một biến có bị gán lại hay không.

- **final:** biến được khai báo với từ khóa final. Sau khi được gán giá trị, biến không thể trỏ sang đối tượng khác.
- **Effectively final:** biến không có từ khóa final, nhưng được sử dụng như một biến final: sau lần khởi tạo hoặc lần gán duy nhất hợp lệ, không có phép gán lại và không có thao tác tăng hoặc giảm giá trị của chính biến đó.

Ví dụ:

~~~java
final BufferedReader fixedReader =
        new BufferedReader(new StringReader("fixed"));

BufferedReader effectiveReader =
        new BufferedReader(new StringReader("effective"));
~~~

Cả hai biến đều có thể được dùng trực tiếp trong phần tài nguyên:

~~~java
try (fixedReader) {
    System.out.println(fixedReader.readLine());
}

try (effectiveReader) {
    System.out.println(effectiveReader.readLine());
}
~~~

fixedReader là biến final tường minh. effectiveReader là biến effectively final vì không được gán lại sau khi khởi tạo.

Một biến khai báo trước rồi được gán đúng một lần cũng có thể là effectively final, miễn là biến đã được gán chắc chắn trước khi dùng:

~~~java
BufferedReader reader;
reader = new BufferedReader(new StringReader("ready"));

try (reader) {
    System.out.println(reader.readLine());
}
~~~

Từ khóa final không làm cho đối tượng trở nên bất biến. Nó chỉ ngăn việc gán lại biến để biến tham chiếu sang một đối tượng khác. Các thao tác làm thay đổi trạng thái bên trong đối tượng vẫn có thể thực hiện được. Ví dụ, gọi reader.readLine() làm thay đổi vị trí đọc của BufferedReader, nhưng không gán lại biến reader.

## 2. Dùng biến đã có trong try-with-resources

Cú pháp cơ bản là đặt tên biến tài nguyên trong cặp ngoặc của try:

~~~java
BufferedReader reader =
        new BufferedReader(new StringReader("Java resource"));

try (reader) {
    String line = reader.readLine();
    System.out.println(line);
}
~~~

Khi biên dịch, Java kiểm tra các điều kiện sau:

1. Biến đã được khởi tạo chắc chắn tại vị trí bắt đầu câu lệnh try.
2. Biến là final hoặc effectively final.
3. Kiểu của biến triển khai AutoCloseable. Closeable kế thừa AutoCloseable, vì vậy các lớp như BufferedReader cũng đáp ứng điều kiện này.
4. Phần tài nguyên tham chiếu đến biến hiện có, chẳng hạn try (reader).

Khi khối try kết thúc, Java tự động gọi close() trên tài nguyên. Biến được khai báo bên ngoài vẫn nằm trong phạm vi truy cập sau khối try, nhưng đối tượng mà nó tham chiếu đã được đóng. Không tiếp tục dùng tài nguyên đó như thể nó vẫn đang mở.

## 3. Ví dụ hoàn chỉnh có thể chạy

Tệp TryWithResourcesVariables.java:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class TryWithResourcesVariables {
    public static void main(String[] args) throws IOException {
        final BufferedReader finalReader =
                new BufferedReader(new StringReader("explicit final"));

        try (finalReader) {
            System.out.println(finalReader.readLine());
        }

        BufferedReader effectiveReader =
                new BufferedReader(new StringReader("effectively final"));

        try (effectiveReader) {
            System.out.println(effectiveReader.readLine());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 TryWithResourcesVariables.java
java TryWithResourcesVariables
~~~

Kết quả chuẩn:

~~~text
explicit final
effectively final
~~~

Ví dụ minh họa hai cách đáp ứng cùng một quy tắc: khai báo final tường minh hoặc để biến trở thành effectively final. Cả hai tài nguyên đều được đóng tự động khi khối tương ứng kết thúc.

## 4. Sử dụng nhiều biến tài nguyên

Có thể liệt kê nhiều biến đã được khai báo bên ngoài, phân tách bằng dấu chấm phẩy:

~~~java
BufferedReader reader =
        new BufferedReader(new StringReader("input"));
StringWriter writer = new StringWriter();

try (reader; writer) {
    writer.write(reader.readLine());
}

System.out.println(writer.toString());
~~~

Mỗi biến được dùng làm tài nguyên phải đáp ứng điều kiện final hoặc effectively final và có kiểu triển khai AutoCloseable. Java đóng các tài nguyên theo thứ tự ngược với thứ tự liệt kê: writer được đóng trước, sau đó đến reader.

## 5. Khi nào biến không còn effectively final?

Một biến không còn effectively final nếu có phép gán lại sau khi khởi tạo. Ví dụ, sau khi thực hiện reader = anotherReader, không thể dùng reader trong try (reader) vì biến đã bị gán lại.

Các thao tác tăng hoặc giảm trực tiếp biến, như count++, ++count, count-- hoặc --count, cũng không phù hợp với quy tắc effectively final. Phép gán kết hợp như count += 1 cũng là phép gán lại.

Hãy phân biệt hai tình huống:

- reader.readLine() hoặc reader.close() gọi phương thức trên đối tượng; chúng không gán lại biến tham chiếu.
- reader = anotherReader thay đổi đối tượng mà biến tham chiếu; thao tác này làm mất tính effectively final.

Nếu cần thay tài nguyên bằng một đối tượng khác, hãy dùng một biến mới phù hợp với vòng đời tài nguyên đó. Nếu biến phải được bảo vệ rõ ràng khỏi việc gán lại, khai báo nó với final.

## 6. Vòng đời và xử lý ngoại lệ

Try-with-resources tự đóng tài nguyên khi khối try kết thúc, kể cả khi khối phát sinh ngoại lệ hoặc kết thúc bằng return, break hay continue. Với nhiều tài nguyên, việc đóng diễn ra theo thứ tự ngược với thứ tự khai báo hoặc liệt kê.

Nếu phần thân try phát sinh ngoại lệ và close() cũng phát sinh ngoại lệ, ngoại lệ từ phần thân vẫn là ngoại lệ chính. Ngoại lệ phát sinh khi đóng được lưu dưới dạng suppressed exception và có thể lấy bằng getSuppressed() trên ngoại lệ chính. Nếu phần thân không phát sinh ngoại lệ nhưng close() thất bại, ngoại lệ từ thao tác đóng được truyền ra ngoài.

Quy tắc final hoặc effectively final chỉ kiểm soát việc gán lại biến tài nguyên. Nó không thay đổi cơ chế tự đóng tài nguyên và xử lý ngoại lệ của try-with-resources.

## 7. Lỗi thường gặp

| Tình huống | Kết quả hoặc cách xử lý |
|---|---|
| Dùng try (reader) nhưng biến đã bị gán lại | Không biên dịch vì biến không còn effectively final. |
| Nghĩ rằng đối tượng không được phép thay đổi trạng thái | Hiểu sai. Có thể gọi phương thức làm thay đổi trạng thái đối tượng; chỉ việc gán lại biến mới bị ngăn. |
| Dùng biến sau khi khối try kết thúc | Biến có thể vẫn truy cập được, nhưng tài nguyên đã đóng. |
| Dùng kiểu không triển khai AutoCloseable | Không thể dùng kiểu đó làm tài nguyên của try-with-resources. |
| Dùng biến chưa được khởi tạo chắc chắn | Không biên dịch vì tài nguyên chưa có giá trị tại điểm sử dụng. |

## 8. Checklist khi áp dụng

Trước khi dùng một biến đã khai báo bên ngoài trong try-with-resources, hãy xác nhận:

- Biến đã được khởi tạo chắc chắn trước câu lệnh try.
- Biến được khai báo final hoặc không bị gán lại nên là effectively final.
- Kiểu của đối tượng triển khai AutoCloseable.
- Không còn đoạn mã nào cần sử dụng tài nguyên sau khi khối try đã đóng nó.
- Nếu liệt kê nhiều tài nguyên, thứ tự đóng ngược có phù hợp với quan hệ phụ thuộc giữa chúng hay không.

Cú pháp try (resourceVariable) giúp quản lý vòng đời của tài nguyên đã được chuẩn bị ở bên ngoài khối try, đồng thời giữ nguyên cơ chế đóng tự động và xử lý ngoại lệ của try-with-resources.