# Phân biệt khai báo tài nguyên mới và tham chiếu tài nguyên có sẵn trong try-with-resources

## Mục tiêu

Trong Java, `try-with-resources` quản lý vòng đời của tài nguyên có khả năng tự đóng, chẳng hạn luồng đọc/ghi, reader, writer, socket hoặc kết nối. Khi khối `try` kết thúc, Java tự gọi `close()` cho từng tài nguyên đã đăng ký.

Có hai cách đưa tài nguyên vào phần khai báo của `try`:

1. **Khai báo tài nguyên mới ngay trong header**: tạo biến tài nguyên và khởi tạo nó tại đó.
2. **Tham chiếu biến tài nguyên đã có**: tạo hoặc nhận biến trước đó, sau đó đưa chính biến ấy vào header để Java tự đóng nó.

Cách tham chiếu biến có sẵn được hỗ trợ từ Java 9 và vẫn dùng được trong các phiên bản Java hiện đại như Java 17+. Nội dung dưới đây sử dụng cú pháp hiện hành.

## 1. Điều kiện để một đối tượng là tài nguyên

Đối tượng được dùng trong `try-with-resources` phải triển khai `AutoCloseable`. `Closeable` kế thừa `AutoCloseable`, vì vậy các lớp như `BufferedReader`, `InputStream` và `OutputStream` cũng dùng được.

Khi khối `try` kết thúc bình thường hoặc do exception, Java tự gọi `close()` cho các tài nguyên khác null. Việc đóng vẫn diễn ra khi thân `try` phát sinh exception hoặc thực hiện `return`.

## 2. Cách A — khai báo tài nguyên mới trong header

Cú pháp:

```java
try (ResourceType resource = createResource()) {
    // Sử dụng resource
}
```

Ví dụ:

```java
try (BufferedReader reader =
         new BufferedReader(new StringReader("Hello Java"))) {
    System.out.println(reader.readLine());
}
```

Đặc điểm:

- Biến `reader` được khai báo và khởi tạo ngay trong phần `try (...)`.
- Biến chỉ có phạm vi sử dụng trong thân `try`; không thể truy cập nó ở bên ngoài khối này hoặc trong `catch`/`finally` đi kèm.
- Java tự đóng đối tượng được gán cho biến khi khối `try` kết thúc.
- Biến tài nguyên được khai báo trong header không thể bị gán lại trong thân `try`.

Dùng cách này khi tài nguyên được tạo tại vị trí đó và chỉ cần dùng trong khối `try`. Đây là cách thể hiện rõ nơi tạo và nơi kết thúc vòng đời của tài nguyên.

## 3. Cách B — tham chiếu biến tài nguyên đã có

Từ Java 9, header có thể chứa tên một biến đã được khai báo trước:

```java
BufferedReader reader =
    new BufferedReader(new StringReader("Hello Java"));

try (reader) {
    System.out.println(reader.readLine());
}
```

Trong trường hợp này, `reader` không được khai báo lại. Header đăng ký chính đối tượng mà biến đang tham chiếu để Java tự đóng nó khi khối `try` kết thúc.

Biến được tham chiếu phải là biến `final` hoặc *effectively final*:

- **`final`**: được khai báo với từ khóa `final` và chỉ được gán giá trị một lần.
- **Effectively final**: không cần viết từ khóa `final`, nhưng sau khi được khởi tạo thì không có lệnh gán lại hoặc tăng/giảm giá trị biến.

Ví dụ về biến effectively final:

```java
BufferedReader reader =
    new BufferedReader(new StringReader("Hello Java"));

// Không gán lại reader sau dòng khởi tạo.
try (reader) {
    System.out.println(reader.readLine());
}
```

Cũng có thể khai báo rõ `final`:

```java
final BufferedReader reader =
    new BufferedReader(new StringReader("Hello Java"));

try (reader) {
    System.out.println(reader.readLine());
}
```

Nếu biến đã bị gán lại sau khi khởi tạo, nó không còn effectively final và không thể được dùng theo dạng tham chiếu này. Ví dụ sau không biên dịch:

```java
BufferedReader reader =
    new BufferedReader(new StringReader("First"));

reader = new BufferedReader(new StringReader("Second"));

// Lỗi biên dịch: reader không còn effectively final.
try (reader) {
    System.out.println(reader.readLine());
}
```

Header tham chiếu yêu cầu một biến hợp lệ; không thể thay tên biến bằng một lời gọi tạo đối tượng tùy ý như `try (createReader())`. Nếu muốn tạo tài nguyên ngay tại header, dùng dạng khai báo ở mục 2.

## 4. So sánh hai cách

| Tiêu chí | Khai báo mới trong header | Tham chiếu biến có sẵn |
|---|---|---|
| Nơi tạo/khởi tạo | Ngay trong header | Trước câu lệnh `try` |
| Cú pháp | `try (Reader r = create())` | `try (r)` |
| Khai báo biến | Header tạo biến mới | Không khai báo lại biến |
| Điều kiện final | Biến trong header không thể gán lại | Biến có sẵn phải `final` hoặc effectively final |
| Phạm vi biến | Chỉ trong thân `try` | Theo phạm vi đã khai báo ban đầu |
| Tự động đóng | Có | Có |
| Trạng thái sau khi khối kết thúc | Biến không còn trong phạm vi | Biến còn trong phạm vi nhưng tài nguyên đã đóng |

Điểm khác biệt quan trọng là **phạm vi của biến** và **vòng đời của đối tượng** là hai chuyện riêng. Với dạng tham chiếu, tên biến vẫn có thể được nhìn thấy sau khối `try`, nhưng đối tượng mà nó trỏ tới đã được đóng. Không được tiếp tục đọc, ghi hoặc sử dụng tài nguyên đó như thể nó vẫn mở.

## 5. Ví dụ Java hoàn chỉnh

Ví dụ sau chạy được trên Java 17+. Nó minh họa một tài nguyên được khai báo trong header và một tài nguyên được tạo trước rồi tham chiếu trong header.

Tạo tệp `TryWithResourcesModes.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class TryWithResourcesModes {
    public static void main(String[] args) throws IOException {
        // Cách A: tạo và khai báo tài nguyên trong header.
        try (BufferedReader declared = new BufferedReader(
                new StringReader("created in try header"))) {
            System.out.println("declared: " + declared.readLine());
        }

        // Cách B: tạo biến trước, sau đó tham chiếu chính biến đó.
        BufferedReader existing = new BufferedReader(
                new StringReader("created before try"));

        try (existing) {
            System.out.println("existing: " + existing.readLine());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac TryWithResourcesModes.java
java TryWithResourcesModes
```

Kết quả stdout:

```text
declared: created in try header
existing: created before try
```

Ở ví dụ thứ hai, `existing` là effectively final vì không có lệnh gán lại sau khi khởi tạo. Câu lệnh `try (existing)` dùng đúng đối tượng đã tạo trước đó và tự đóng nó khi khối kết thúc.

## 6. Có thể kết hợp cả hai dạng trong một header

Một danh sách tài nguyên có thể chứa cả biến tham chiếu và biến được khai báo mới. Các mục được phân cách bằng dấu chấm phẩy:

```java
BufferedReader existing =
    new BufferedReader(new StringReader("existing"));

try (
    existing;
    BufferedReader created = new BufferedReader(
        new StringReader("created in header"))
) {
    System.out.println(existing.readLine());
    System.out.println(created.readLine());
}
```

Java xử lý tài nguyên theo thứ tự từ trái sang phải khi khởi tạo hoặc đăng ký, rồi đóng theo thứ tự ngược lại. Với ví dụ trên, `created` được đóng trước, sau đó `existing`.

Chỉ nên đăng ký mỗi tài nguyên một lần trong cùng danh sách. Tránh tự gọi `close()` trong thân `try` khi không có lý do cụ thể, vì Java sẽ tiếp tục thực hiện việc đóng tự động khi thoát khỏi khối.

## 7. Quy tắc vòng đời và xử lý exception

- Java đóng tài nguyên khi khối `try` kết thúc, kể cả khi thân khối ném exception hoặc có lệnh `return`.
- Với nhiều tài nguyên, thứ tự đóng là ngược với thứ tự khai báo/đăng ký. Quy tắc này giúp tài nguyên được mở sau cùng được đóng trước.
- Việc đóng tài nguyên hoàn tất trước khi luồng điều khiển đi vào `catch` hoặc `finally` tương ứng.
- Nếu thân `try` ném exception và `close()` cũng ném exception, exception từ `close()` được lưu dưới dạng *suppressed exception* trên exception chính. Có thể xem chúng bằng `getSuppressed()`.
- Nếu không có exception chính nhưng `close()` phát sinh exception, exception từ việc đóng có thể được truyền ra ngoài và cần được xử lý theo chữ ký phương thức hoặc bằng `catch`.

Dạng tham chiếu không chuyển quyền sở hữu đối tượng theo cơ chế của hệ thống kiểu Java; nó chỉ đăng ký đối tượng để khối `try` gọi `close()`. Vì vậy, chỉ dùng `try (existing)` khi khối này thực sự chịu trách nhiệm đóng tài nguyên. Nếu một phần khác của chương trình còn cần tài nguyên ở trạng thái mở, không đăng ký nó vào khối này.

## 8. Lỗi thường gặp

1. **Tham chiếu biến đã bị gán lại**: biến không còn effectively final nên trình biên dịch từ chối `try (reader)`. Hãy dùng biến không bị gán lại hoặc tạo một biến tài nguyên riêng phù hợp.
2. **Dùng tài nguyên sau khi khối đã kết thúc**: biến có thể vẫn nằm trong phạm vi, nhưng đối tượng đã được đóng. Hãy giới hạn việc sử dụng trong vòng đời của tài nguyên.
3. **Nhầm tham chiếu với tạo mới**: `try (reader)` không tạo reader mới, không sao chép reader và không gọi lại factory. Nó dùng đúng đối tượng đang được biến tham chiếu.
4. **Đưa đối tượng không hỗ trợ đóng vào header**: kiểu tài nguyên phải triển khai `AutoCloseable`; nếu không, mã không biên dịch.
5. **Đóng cùng một tài nguyên nhiều lần**: tránh vừa tự gọi `close()` trong thân khối vừa đăng ký cùng tài nguyên trong header, hoặc đăng ký lặp cùng một đối tượng.
6. **Cho rằng biến tham chiếu sẽ tự được khai báo trong header**: `try (reader)` chỉ dùng biến đã tồn tại; biến phải được khai báo và khởi tạo trước đó, đồng thời thỏa điều kiện `final`/effectively final.

## 9. Chọn cách nào trong thực tế?

- Chọn **khai báo mới trong header** khi khối `try` tự tạo tài nguyên và quản lý trọn vòng đời của nó. Cách này gom nơi khởi tạo, sử dụng và đóng tài nguyên vào một vị trí.
- Chọn **tham chiếu biến có sẵn** khi tài nguyên đã được tạo trước đó hoặc được nhận từ một phương thức khác, và khối `try` sẽ chịu trách nhiệm đóng nó. Cách này tránh phải tạo thêm biến trung gian chỉ để đưa tài nguyên vào `try-with-resources`.
- Nếu tài nguyên cần tiếp tục mở sau khối `try`, không đăng ký nó vào khối đó; hãy đặt phạm vi quản lý tài nguyên ở nơi có vòng đời phù hợp.

Cả hai dạng đều dùng cùng cơ chế tự động đóng của `try-with-resources`. Khác biệt nằm ở nơi khai báo biến, điều kiện final của biến được tham chiếu và phạm vi mà tên biến có thể được sử dụng.
