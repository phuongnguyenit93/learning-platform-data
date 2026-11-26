# Quản lý tài nguyên bằng try-with-resources khi không cần dùng tên tài nguyên trong thân khối

Trong Java 22, tính năng *unnamed variables and patterns* cho phép dùng dấu gạch dưới (`_`) để khai báo một biến không cần tên. Một trường hợp hữu ích là khai báo tài nguyên trong `try-with-resources` khi chương trình chỉ cần hành động mở, khóa hoặc đăng ký tài nguyên, còn tham chiếu đến đối tượng không được sử dụng trong thân khối `try`.

Ví dụ, khi lấy một `FileLock`, chương trình cần giữ khóa trong lúc ghi dữ liệu và tự động giải phóng khóa khi kết thúc. Nếu không cần gọi phương thức nào trên đối tượng `FileLock`, có thể khai báo `var _ = channel.lock()` thay vì đặt một tên như `lock` rồi để biến đó không được dùng.

Cú pháp này là tính năng ngôn ngữ Java đã được hoàn thiện từ JDK 22 theo JEP 456. Khi biên dịch với Java 22 trở lên, không cần bật preview feature.

## 1. Vấn đề khi tài nguyên không cần được tham chiếu

`try-with-resources` được giới thiệu để quản lý vòng đời của những đối tượng cần được đóng hoặc giải phóng sau khi sử dụng. Tài nguyên phải triển khai `AutoCloseable` (hoặc một kiểu con như `Closeable`).

Ví dụ quen thuộc:

```java
try (var reader = Files.newBufferedReader(path)) {
    String line = reader.readLine();
    process(line);
}
```

Ở đây, biến `reader` cần có tên vì thân khối `try` gọi `reader.readLine()`.

Nhưng có trường hợp chương trình chỉ cần tạo tài nguyên để kích hoạt một hành vi, giữ hành vi đó trong suốt phạm vi khối `try`, rồi để `close()` hoàn tất việc dọn dẹp. Một ví dụ là lấy khóa tệp: chương trình cần giữ khóa trong lúc thao tác trên `FileChannel`, nhưng không cần dùng trực tiếp đối tượng `FileLock`.

Trước Java 22, ta thường đặt một tên cho biến tài nguyên dù không tham chiếu đến nó:

```java
try (var lock = channel.lock()) {
    channel.write(buffer);
}
```

Tên `lock` không được dùng trong thân khối. Điều này vẫn hợp lệ, nhưng không thể hiện rõ rằng việc bỏ qua tham chiếu là có chủ ý.

## 2. Dùng biến không tên trong khai báo tài nguyên

Java 22 cho phép viết dấu gạch dưới (`_`) thay cho tên biến trong khai báo tài nguyên:

```java
try (var _ = channel.lock()) {
    channel.write(buffer);
}
```

Trong ví dụ này:

- `channel.lock()` vẫn được thực thi và trả về một đối tượng `FileLock`.
- `var` để trình biên dịch suy luận kiểu của tài nguyên từ biểu thức khởi tạo.
- `_` cho biết chương trình không cần tên để tham chiếu đến đối tượng tài nguyên.
- Khi rời khỏi khối `try`, Java vẫn gọi `close()` trên tài nguyên đã khai báo. Với `FileLock`, thao tác này giải phóng khóa.

Biến không tên không làm mất đối tượng tài nguyên và cũng không bỏ qua việc khởi tạo. Nó chỉ thể hiện rằng mã nguồn không cần truy cập đối tượng thông qua một tên biến.

Có thể dùng kiểu tường minh thay cho `var` nếu muốn:

```java
try (FileLock _ = channel.lock()) {
    channel.write(buffer);
}
```

Cả hai cách đều khai báo một resource variable không tên. Dùng `var` thường gọn hơn khi kiểu trả về đã rõ từ lời gọi phương thức.

## 3. Ví dụ hoàn chỉnh: ghi tệp trong khi giữ khóa

Giả sử một ứng dụng cần ghi thêm dữ liệu vào tệp log. Ứng dụng mở `FileChannel`, lấy khóa độc quyền của tệp trong lúc ghi, sau đó tự động giải phóng khóa và đóng channel.

```java
package com.example;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class LockedAppender {

    public static void append(Path path, byte[] data) throws IOException {
        try (FileChannel channel = FileChannel.open(
                    path,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND);
             var _ = channel.lock()) {

            channel.write(ByteBuffer.wrap(data));
        }
    }
}
```

Hai tài nguyên được khai báo trong cùng một câu lệnh `try`:

1. `channel` có tên vì thân khối cần gọi `channel.write(...)`.
2. `FileLock` được tạo bởi `channel.lock()`. Thân khối chỉ cần khóa được giữ trong thời gian ghi nên khai báo nó bằng `var _`.

Khi kết thúc khối `try`, Java đóng tài nguyên theo thứ tự ngược với thứ tự khởi tạo: giải phóng `FileLock` trước, sau đó đóng `FileChannel`. Trình tự này phù hợp vì khóa được tạo trên channel và cần được giải phóng trước khi channel đóng.

Trong ví dụ, `FileChannel` và `FileLock` đều là tài nguyên có thể quản lý bằng try-with-resources. Phương thức khai báo `throws IOException` vì các thao tác mở, khóa, ghi và đóng có thể phát sinh `IOException`.

## 4. Nhiều tài nguyên không tên trong cùng một try

Java cho phép khai báo nhiều biến không tên trong cùng danh sách tài nguyên. Điều này hữu ích khi nhiều tài nguyên chỉ cần được tạo và tự động đóng, không cần tham chiếu trong thân khối.

```java
try (var _ = openFirstResource();
     var _ = openSecondResource()) {

    performOperation();
}
```

Điều kiện là kiểu của từng biểu thức khởi tạo phải là kiểu triển khai `AutoCloseable`. Các tài nguyên vẫn được khởi tạo từ trái sang phải và đóng theo thứ tự ngược lại. Nếu khởi tạo một tài nguyên ở phía sau thất bại, những tài nguyên đã khởi tạo thành công trước đó vẫn được đóng.

Mỗi dấu `_` là một khai báo biến không tên riêng biệt. Vì không có tên để tham chiếu, có thể khai báo nhiều biến không tên trong cùng phạm vi mà không gặp xung đột tên.

## 5. Vòng đời tài nguyên và xử lý exception vẫn giữ nguyên

Việc dùng `_` chỉ thay đổi cách viết tên biến. Quy tắc quản lý tài nguyên của try-with-resources không thay đổi:

- Biểu thức khởi tạo tài nguyên vẫn được đánh giá khi đi vào câu lệnh `try`.
- Khi thân khối kết thúc bình thường hoặc kết thúc đột ngột do exception hay `return`, Java vẫn gọi `close()` trên các tài nguyên đã khởi tạo thành công.
- Nhiều tài nguyên được đóng theo thứ tự ngược với thứ tự khai báo.
- Nếu thân khối ném exception và `close()` cũng ném exception, exception từ thao tác đóng được ghi nhận là *suppressed exception* trên exception chính. Có thể xem chúng bằng `getSuppressed()`.

Ví dụ dưới đây cho thấy tài nguyên không tên vẫn được đóng khi thân khối ném exception:

```java
try (var _ = acquireResource()) {
    doWork(); // Nếu ném exception, tài nguyên vẫn được đóng.
}
```

Tên biến không ảnh hưởng đến exception mà phương thức `close()` có thể ném. Nếu kiểu tài nguyên khai báo `close()` có checked exception, mã gọi vẫn phải xử lý exception đó bằng `catch` hoặc khai báo `throws` phù hợp.

## 6. Giới hạn và cách chọn giữa _ với tên biến

Biến không tên phù hợp khi chương trình chỉ cần hiệu ứng vòng đời của tài nguyên, chẳng hạn giữ một khóa trong phạm vi khối lệnh hoặc bảo đảm một đối tượng được đóng tự động. Nếu thân khối cần đọc trạng thái, gọi phương thức hoặc truyền tài nguyên sang nơi khác, hãy dùng tên biến bình thường.

| Nhu cầu | Cách khai báo phù hợp |
|---|---|
| Chỉ cần tài nguyên được đóng tự động | `try (var _ = openResource())` |
| Cần gọi phương thức trên tài nguyên trong thân khối | `try (var resource = openResource())` |
| Cần kiểm tra trạng thái khóa | `try (var lock = channel.lock())` |

Một số giới hạn cần nhớ:

- `_` chỉ dùng trong những vị trí Java cho phép khai báo biến không tên. Nó không phải tên biến thông thường và không thể được tham chiếu trong biểu thức.
- Trong try-with-resources, hãy dùng dạng khai báo như `var _ = expression` hoặc `ResourceType _ = expression`. Không thể dùng `_` như một tham chiếu đến tài nguyên đã khai báo ở nơi khác.
- Kiểu suy luận hoặc kiểu khai báo của tài nguyên vẫn phải đáp ứng yêu cầu của try-with-resources: triển khai `AutoCloseable`.
- Cú pháp này cần mức ngôn ngữ Java 22 trở lên. Dự án biên dịch với source/release thấp hơn Java 22 không thể dùng cách khai báo này.
- Dùng `_` không tự động xử lý checked exception, không bỏ qua lỗi khi khởi tạo và không thay đổi thời điểm gọi `close()`.

## 7. Khi nào nên sử dụng?

Nên dùng biến tài nguyên không tên khi tất cả điều kiện sau đều đúng:

1. Tài nguyên cần được khởi tạo để thiết lập một trạng thái hoặc thực hiện một thao tác.
2. Trạng thái đó cần được duy trì trong phạm vi khối `try`.
3. Thân khối không cần tham chiếu đến đối tượng tài nguyên.
4. Việc dọn dẹp có thể được thực hiện qua `close()` của `AutoCloseable`.

Các ví dụ thường gặp là giữ khóa tệp trong khi thao tác trên channel, đăng ký một phạm vi tài nguyên có cơ chế tự giải phóng, hoặc quản lý một đối tượng chỉ có ý nghĩa thông qua hành động đóng khi kết thúc phạm vi.

Nếu đối tượng cần được dùng trong thân khối, hãy giữ tên biến để mã nguồn thể hiện rõ mục đích truy cập.

## Kết luận

Biến không tên trong try-with-resources giúp diễn đạt rõ trường hợp tài nguyên cần được tạo và tự động đóng nhưng không cần được tham chiếu trong thân khối. Cú pháp `var _ = expression` giữ nguyên toàn bộ cơ chế khởi tạo, đóng tài nguyên và xử lý exception của try-with-resources. Đây là một cách viết gọn và rõ ý hơn cho những tài nguyên chỉ phục vụ vòng đời hoặc hiệu ứng quản lý phạm vi trong Java 22 trở lên.

## Tài liệu tham khảo

- [JEP 456: Unnamed Variables & Patterns](https://openjdk.org/jeps/456)
- [Java Language Specification, Java SE 22 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se22/html/jls-14.html#jls-14.20.3)
- [Java SE 22 API — AutoCloseable](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java SE 22 API — FileLock](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileLock.html)
