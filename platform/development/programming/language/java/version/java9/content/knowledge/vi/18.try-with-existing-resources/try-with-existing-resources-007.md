# Tránh sử dụng tài nguyên đã đóng qua tham chiếu bên ngoài

## 1. Vấn đề cần tránh

Trong Java, một tài nguyên như `Reader`, `InputStream`, `Socket` hoặc `Connection` thường đại diện cho một tài nguyên có vòng đời hữu hạn. Khi tài nguyên được đóng bằng `close()`, đối tượng vẫn tồn tại trong bộ nhớ và các biến vẫn giữ tham chiếu đến nó, nhưng đối tượng không còn ở trạng thái có thể sử dụng như trước.

Điều này dễ gây lỗi khi một biến được khai báo bên ngoài khối `try`, được đăng ký vào try-with-resources, rồi tiếp tục được dùng thông qua chính biến đó hoặc một tham chiếu khác sau khi khối kết thúc.

Java 9 cho phép đưa một biến đã khai báo trước vào phần tài nguyên của try-with-resources nếu biến đó là `final` hoặc *effectively final*:

```java
BufferedReader reader = ...;

try (reader) {
    // Sử dụng reader trong thời gian tài nguyên còn mở.
}

// reader vẫn nằm trong phạm vi, nhưng tài nguyên đã đóng.
```

Cú pháp này giúp quản lý một biến tài nguyên có sẵn mà không cần khai báo lại trong phần `try (...)`. Tuy nhiên, nó không kéo dài vòng đời của tài nguyên. Khi luồng điều khiển rời khỏi khối `try`, Java tự động gọi `close()`.

## 2. Tham chiếu còn tồn tại không có nghĩa tài nguyên còn mở

Một biến Java lưu tham chiếu đến đối tượng. Việc đóng tài nguyên tác động lên chính đối tượng, không xóa tham chiếu đang trỏ đến đối tượng đó.

Nếu hai biến cùng trỏ đến một đối tượng:

```java
BufferedReader reader = ...;
BufferedReader alias = reader;
```

thì `reader` và `alias` là hai tham chiếu đến cùng một `BufferedReader`. Khi try-with-resources đóng đối tượng qua `reader`, đối tượng mà `alias` trỏ đến cũng đã đóng. Java không tự đặt `alias` thành `null`, cũng không tạo ra một bản sao tài nguyên độc lập.

Vì vậy, các tình huống sau đều cần tránh:

- Gọi phương thức đọc, ghi hoặc truy cập tài nguyên qua biến gốc sau khi khối try-with-resources kết thúc.
- Giữ một alias trong biến khác, field, collection hoặc đối tượng khác rồi sử dụng alias đó sau khi tài nguyên đã đóng.
- Trả về hoặc chuyển tham chiếu ra ngoài một phương thức trong khi phương thức đó đã đóng tài nguyên.
- Đưa tham chiếu vào callback hoặc tác vụ bất đồng bộ có thể chạy sau thời điểm khối try kết thúc.

Tùy loại tài nguyên, thao tác sau khi đóng có thể ném `IOException`, `SQLException`, `IllegalStateException` hoặc một ngoại lệ khác theo hợp đồng của lớp. Không nên dựa vào một thông báo lỗi cụ thể để xác định trạng thái tài nguyên.

## 3. Ví dụ: alias trỏ đến tài nguyên đã đóng

Ví dụ sau dùng cú pháp try-with-resources dành cho biến có sẵn từ Java 9. Hai biến `reader` và `alias` cùng trỏ đến một `BufferedReader`. Sau khi khối `try` kết thúc, thao tác qua `alias` thất bại vì đối tượng đã được đóng.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ClosedResourceReferenceDemo {
    public static void main(String[] args) throws IOException {
        BufferedReader reader =
                new BufferedReader(new StringReader("Java 9 try-with-resources"));
        BufferedReader alias = reader;

        try (reader) {
            System.out.println(reader.readLine());
        }

        try {
            alias.readLine();
        } catch (IOException ex) {
            System.out.println("Không thể đọc: tài nguyên đã đóng.");
        }
    }
}
```

Lưu mã nguồn trong tệp `ClosedResourceReferenceDemo.java`, sau đó biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 ClosedResourceReferenceDemo.java
java ClosedResourceReferenceDemo
```

Kết quả:

```text
Java 9 try-with-resources
Không thể đọc: tài nguyên đã đóng.
```

Dòng đầu được in khi tài nguyên còn mở. Khi khối `try` kết thúc, Java gọi `reader.close()`. Vì `alias` vẫn trỏ đến cùng đối tượng, lệnh `alias.readLine()` thực hiện trên một `BufferedReader` đã đóng và ném `IOException`. Chương trình bắt ngoại lệ và in thông báo ổn định do chính ví dụ định nghĩa, không phụ thuộc vào nội dung thông báo của JDK.

## 4. Cách tổ chức vòng đời an toàn

### Ưu tiên khai báo tài nguyên ngay trong try-with-resources

Khi tài nguyên được tạo và chỉ được dùng trong một thao tác, hãy khai báo nó trong phần tài nguyên. Phạm vi biến được giới hạn trong khối try, giúp tránh vô tình sử dụng biến sau khi đóng:

```java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line = reader.readLine();
    process(line);
}
```

Cần có các import tương ứng:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
```

### Nếu dùng biến đã khai báo trước, chỉ dùng nó trong khối quản lý

Khi cần dùng cú pháp Java 9 `try (resource)`, hãy bảo đảm biến là `final` hoặc *effectively final* và mọi thao tác với tài nguyên đều hoàn tất trước khi rời khỏi khối:

```java
BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);

try (reader) {
    process(reader.readLine());
}

// Không gọi reader.readLine() hoặc dùng alias của reader ở đây.
```

Không gán lại biến tài nguyên trước hoặc trong quá trình sử dụng theo cách làm mất tính *effectively final*. Cú pháp Java 9 này chỉ giúp tái sử dụng biến hiện có; nó không biến tài nguyên thành đối tượng có thể dùng vô thời hạn.

### Không đóng tài nguyên do bên gọi sở hữu

Một phương thức nhận tài nguyên từ nơi khác cần làm rõ quyền sở hữu. Nếu phương thức chỉ mượn tài nguyên để xử lý, phương thức đó không nên tự đóng tài nguyên. Bên tạo và sở hữu tài nguyên chịu trách nhiệm đóng nó:

```java
static void printFirstLine(BufferedReader reader) throws IOException {
    System.out.println(reader.readLine());
}

static void run(Path path) throws IOException {
    try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        printFirstLine(reader);
    }
}
```

Trong ví dụ này, `run` tạo và sở hữu `reader`, nên `run` quản lý việc đóng. `printFirstLine` chỉ sử dụng tài nguyên được truyền vào và không đóng nó. Nếu một phương thức được thiết kế để nhận quyền sở hữu và đóng tài nguyên, hợp đồng của phương thức cần nói rõ điều đó.

### Khi cần dùng tài nguyên ở nhiều giai đoạn

Nếu tài nguyên phải được dùng ở nhiều bước, hãy đặt các bước đó trong cùng một phạm vi quản lý và chỉ đóng tài nguyên sau lần sử dụng cuối cùng. Nếu vòng đời thực sự thuộc về một thành phần khác, hãy để thành phần sở hữu quản lý việc đóng; không giữ một alias rồi kỳ vọng tài nguyên vẫn mở sau khi chủ sở hữu đã đóng nó.

## 5. Những điểm cần nhớ về try-with-resources

- Kiểu tài nguyên phải triển khai `AutoCloseable`; `Closeable` là một kiểu con thường gặp trong I/O.
- Java tự gọi `close()` khi khối try hoàn tất, kể cả khi có `return` hoặc ngoại lệ làm luồng điều khiển rời khỏi khối.
- Khi khai báo nhiều tài nguyên, Java đóng chúng theo thứ tự ngược với thứ tự khai báo.
- Nếu phần thân try ném ngoại lệ và thao tác đóng cũng ném ngoại lệ, ngoại lệ từ phần thân được giữ làm ngoại lệ chính; ngoại lệ phát sinh khi đóng được ghi nhận dưới dạng *suppressed exception*.
- Biến và alias vẫn có thể truy cập về mặt cú pháp sau khi đóng. Khả năng truy cập biến không chứng minh trạng thái tài nguyên còn hợp lệ.
- Không nên gọi `close()` thủ công trong khối rồi tiếp tục sử dụng tài nguyên. Việc đóng hai lần cũng không được bảo đảm là an toàn cho mọi kiểu `AutoCloseable`.

## 6. Checklist khi review mã nguồn

1. Xác định thành phần nào tạo và sở hữu tài nguyên.
2. Xác định điểm mà try-with-resources sẽ gọi `close()`.
3. Tìm các alias, field, collection, callback hoặc tác vụ có thể giữ tham chiếu đến cùng đối tượng.
4. Bảo đảm mọi thao tác trên tài nguyên kết thúc trước thời điểm đóng.
5. Nếu phương thức chỉ mượn tài nguyên, không đóng tài nguyên trong phương thức đó.
6. Nếu phương thức nhận quyền sở hữu, ghi rõ trách nhiệm đóng trong hợp đồng API.
7. Ưu tiên phạm vi tài nguyên hẹp để vòng đời có thể được đọc trực tiếp từ cấu trúc mã.

Nguyên tắc cốt lõi: sau khi try-with-resources kết thúc, hãy coi tài nguyên đã đóng qua mọi tham chiếu đến cùng đối tượng. Muốn tiếp tục sử dụng, cần một tài nguyên mới hoặc một phạm vi quản lý có vòng đời dài hơn và được xác định rõ quyền sở hữu.