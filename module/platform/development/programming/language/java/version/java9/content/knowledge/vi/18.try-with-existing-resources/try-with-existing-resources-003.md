# Phạm vi biến và quyền sở hữu tài nguyên được đóng

Trong Java, **phạm vi biến (scope)** xác định nơi mã nguồn được phép tham chiếu đến một tên biến. **Vòng đời tài nguyên (resource lifecycle)** xác định khi nào một tài nguyên như luồng đọc, luồng ghi hoặc kết nối phải được đóng. Hai khái niệm có liên quan nhưng không đồng nhất: một biến có thể vẫn nằm trong phạm vi sau khi tài nguyên mà nó tham chiếu đã đóng.

Java 9 mở rộng cú pháp **try-with-resources** để dùng trực tiếp một biến đã khai báo bên ngoài khối `try`, miễn là biến đó là `final` hoặc *effectively final*. Hiểu đúng phạm vi và quyền quản lý việc đóng giúp tránh lỗi dùng tài nguyên sau khi đóng, đóng nhầm tài nguyên của bên gọi và rò rỉ tài nguyên.

## Mục tiêu

- Xác định phạm vi của biến cục bộ, tham số, biến vòng lặp, biến `catch` và biến tài nguyên.
- Phân biệt phạm vi tên biến với thời gian tồn tại và trạng thái mở/đóng của đối tượng.
- Hiểu điều kiện `final` hoặc *effectively final* khi dùng biến có sẵn trong try-with-resources từ Java 9.
- Xác định đoạn mã nào chịu trách nhiệm gọi `close()` và cách xử lý tài nguyên được mượn từ nơi khác.

## 1. Phạm vi biến, vòng đời đối tượng và trạng thái tài nguyên

Ba khái niệm sau cần được tách biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Phạm vi biến | Vùng mã nguồn mà tên biến có thể được sử dụng hợp lệ | Biến khai báo trong một khối `{}` chỉ dùng được trong khối đó và các khối lồng bên trong |
| Vòng đời đối tượng | Thời gian đối tượng còn tồn tại và có thể được tham chiếu | Một đối tượng có thể tiếp tục được dùng qua một tham chiếu khác sau khi biến cục bộ ban đầu ra khỏi phạm vi |
| Trạng thái tài nguyên | Tài nguyên còn mở hay đã đóng | `BufferedReader` có thể đã đóng dù biến `reader` vẫn đang trong phạm vi |

Phạm vi được kiểm tra khi biên dịch. Việc đóng tài nguyên là hành động xảy ra khi chương trình chạy. `close()` không xóa biến, không gán biến thành `null` và không tự làm biến ra khỏi phạm vi.

Việc một đối tượng không còn được tham chiếu có thể khiến nó đủ điều kiện để bộ thu gom rác xử lý, nhưng thời điểm thu gom không xác định. Không dùng garbage collection để thay thế việc đóng tài nguyên có liên kết với hệ điều hành hoặc dịch vụ bên ngoài.

## 2. Phạm vi của các loại biến thường gặp

### 2.1. Biến cục bộ trong khối

Biến khai báo bên trong một khối chỉ có thể được tham chiếu từ vị trí khai báo đến dấu `}` kết thúc khối đó. Các khối lồng bên trong có thể sử dụng biến của khối bên ngoài nếu biến đó vẫn nằm trong phạm vi.

~~~java
if (ready) {
    int count = 1;
    System.out.println(count);
}

// count không còn trong phạm vi tại đây.
~~~

Biến cục bộ phải được gán giá trị chắc chắn trước khi đọc. Java không tự gán giá trị mặc định cho biến cục bộ. Ngược lại, field của đối tượng và biến `static` có giá trị mặc định theo kiểu dữ liệu nếu không được khởi tạo rõ ràng.

### 2.2. Tham số phương thức và constructor

Tham số có phạm vi trong thân phương thức hoặc constructor tương ứng. Mỗi lần gọi phương thức có một lần thực thi riêng với các tham số của lần gọi đó. Tham số không thể được tham chiếu bên ngoài thân khai báo của nó.

### 2.3. Biến trong vòng lặp

Với biến khai báo ngay trong phần khởi tạo của vòng `for`, phạm vi bao gồm điều kiện, phần cập nhật và thân vòng lặp. Biến không còn khả dụng sau vòng lặp.

~~~java
for (int index = 0; index < 3; index++) {
    System.out.println(index);
}

// index không nằm trong phạm vi tại đây.
~~~

Biến khai báo trong vòng lặp `for-each` cũng chỉ dùng được trong thân vòng lặp:

~~~java
for (String name : names) {
    System.out.println(name);
}

// name không nằm trong phạm vi tại đây.
~~~

### 2.4. Biến bắt ngoại lệ

Biến được khai báo trong `catch` chỉ có phạm vi trong khối `catch` tương ứng. Có thể dùng biến đó để ghi log, kiểm tra nguyên nhân hoặc xử lý ngoại lệ; không thể tham chiếu nó sau khi khối `catch` kết thúc.

~~~java
try {
    readFile();
} catch (IOException exception) {
    System.err.println(exception.getMessage());
}

// exception không nằm trong phạm vi tại đây.
~~~

### 2.5. Biến tài nguyên khai báo trong try-with-resources

Khi khai báo tài nguyên ngay trong phần tiêu đề của `try`, biến tài nguyên chỉ khả dụng trong phần khai báo tài nguyên tiếp theo và thân `try`. Nó không khả dụng trong `catch` hoặc `finally` đi kèm.

~~~java
try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
} catch (IOException exception) {
    System.err.println(exception.getMessage());
}

// reader không nằm trong phạm vi tại đây.
~~~

### 2.6. Field và biến cục bộ cùng tên

Field thuộc về đối tượng hoặc lớp; phạm vi truy cập của nó được xác định bởi vị trí khai báo và modifier truy cập. Biến cục bộ có thể che khuất field cùng tên trong một phương thức. Dùng `this.fieldName` để chỉ rõ field của đối tượng khi cần.

~~~java
public class Counter {
    private int value;

    public void setValue(int value) {
        this.value = value;
    }
}
~~~

Trong một vùng phạm vi chồng lấn, Java không cho phép khai báo lại một biến cục bộ với tên đã được dùng bởi biến cục bộ khác ở vùng bên ngoài. Điều này giúp tránh nhầm lẫn về biến đang được tham chiếu.

### 2.7. Biến được lambda sử dụng

Lambda có thể đọc biến cục bộ hoặc tham số nằm bên ngoài nếu biến đó là `final` hoặc *effectively final*. Một biến được xem là *effectively final* khi sau lần gán khởi tạo, chương trình không gán lại nó và không tăng/giảm nó bằng `++` hoặc `--`.

~~~java
String prefix = "file-";
names.forEach(name -> System.out.println(prefix + name));
~~~

Ví dụ trên hợp lệ vì `prefix` không bị gán lại. Nếu thay đổi `prefix` sau khi khởi tạo, lambda không thể capture biến đó theo cách này.

## 3. Quản lý tài nguyên bằng try-with-resources

### 3.1. Tài nguyên có thể tự đóng

Try-with-resources dành cho đối tượng triển khai `AutoCloseable`. `Closeable` là một interface mở rộng `AutoCloseable` và thường được dùng cho luồng I/O. Phương thức `close()` giải phóng tài nguyên mà đối tượng quản lý, ví dụ file descriptor, socket hoặc kết nối.

Khi thoát khỏi thân `try`, Java tự gọi `close()` cho các tài nguyên đã đăng ký, kể cả khi thân `try` kết thúc bằng `return` hoặc phát sinh ngoại lệ. Đây là cách ưu tiên để quản lý tài nguyên có thể đóng.

### 3.2. Cú pháp khai báo tài nguyên

Có thể khai báo và khởi tạo tài nguyên ngay trong tiêu đề `try`: 

~~~java
try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line = reader.readLine();
    System.out.println(line);
}
~~~

Khi dấu ngoặc của khối `try` kết thúc, `reader.close()` được gọi tự động. Biến `reader` khai báo trong tiêu đề chỉ có phạm vi bên trong cấu trúc try-with-resources đó.

### 3.3. Điểm mở rộng từ Java 9: dùng biến đã khai báo bên ngoài

Từ Java 9, phần tiêu đề try-with-resources có thể tham chiếu trực tiếp đến một biến tài nguyên đã được khai báo trước đó. Biến phải là `final` hoặc *effectively final* và kiểu của nó phải triển khai `AutoCloseable`.

~~~java
BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);

try (reader) {
    System.out.println(reader.readLine());
}
~~~

Trong ví dụ này, `reader` được gán một lần và không bị gán lại, vì vậy nó là *effectively final*. Java 9 cho phép dùng nó trong `try (reader)` mà không cần khai báo lại biến tài nguyên.

Nếu biến bị gán lại sau khi khởi tạo, nó không còn *effectively final* và không thể được dùng theo cú pháp này. Khi cần thay đổi tham chiếu, hãy thiết kế lại nơi tạo tài nguyên hoặc dùng một biến tài nguyên riêng có vòng đời rõ ràng.

### 3.4. Phạm vi biến và thời điểm đóng là hai việc khác nhau

Xét biến `reader` được khai báo trước câu lệnh `try (reader)`. Sau khi khối `try` kết thúc:

- Tên `reader` vẫn nằm trong phạm vi của khối bên ngoài nơi nó được khai báo.
- Đối tượng mà `reader` tham chiếu đã được try-with-resources đóng.
- Biến vẫn giữ tham chiếu đến đối tượng; Java không tự gán `reader = null`.
- Không được tiếp tục đọc hoặc ghi qua tài nguyên đã đóng. Hành vi cụ thể sau khi đóng phụ thuộc hợp đồng của từng lớp, vì vậy không nên dựa vào việc gọi phương thức sau `close()`.

Ngược lại, nếu biến được khai báo trực tiếp trong tiêu đề `try`, tên biến không thể được dùng sau cấu trúc try-with-resources đó.

### 3.5. Nhiều tài nguyên và thứ tự đóng

Khi có nhiều tài nguyên trong cùng một tiêu đề, Java khởi tạo chúng từ trái sang phải và đóng chúng theo thứ tự ngược lại. Tài nguyên được khởi tạo sau sẽ được đóng trước. Điều này phù hợp với quan hệ phụ thuộc: tài nguyên được tạo sau thường phụ thuộc vào tài nguyên được tạo trước.

~~~java
try (InputStream input = Files.newInputStream(path);
     BufferedReader reader = new BufferedReader(
         new InputStreamReader(input, StandardCharsets.UTF_8))) {
    System.out.println(reader.readLine());
}
~~~

Trong ví dụ trên, `reader` được đóng trước. Việc đóng `reader` cũng đóng `input` bên dưới vì reader đang bọc input stream. Do đó, không nên đăng ký đồng thời cả một tài nguyên và wrapper chịu trách nhiệm đóng chính tài nguyên đó nếu việc đóng lặp lại không được thiết kế rõ ràng. Một cách đơn giản hơn là dùng `Files.newBufferedReader()` và chỉ quản lý reader ở một nơi.

### 3.6. Ngoại lệ phát sinh khi đóng

Nếu thân `try` phát sinh ngoại lệ và `close()` cũng phát sinh ngoại lệ, ngoại lệ từ thân `try` vẫn là ngoại lệ chính. Ngoại lệ khi đóng được lưu dưới dạng *suppressed exception* và có thể xem qua `getSuppressed()`.

~~~java
try (SomeResource resource = openResource()) {
    performWork(resource);
} catch (IOException exception) {
    for (Throwable suppressed : exception.getSuppressed()) {
        System.err.println("Lỗi khi đóng tài nguyên: " + suppressed.getMessage());
    }
    throw exception;
}
~~~

Nếu thân `try` kết thúc bình thường nhưng `close()` phát sinh ngoại lệ, ngoại lệ khi đóng sẽ được truyền ra ngoài. Vì vậy, không nên bỏ qua lỗi đóng tài nguyên khi nó ảnh hưởng đến tính đúng đắn của chương trình.

## 4. Quyền quản lý việc đóng tài nguyên

Java không có hệ thống ownership/borrow được kiểm tra tĩnh như một số ngôn ngữ khác. Việc ai chịu trách nhiệm gọi `close()` phải được xác định qua thiết kế API và quy ước của chương trình.

### 4.1. Tài nguyên do phương thức tự tạo

Khi một phương thức tự mở file, tạo stream hoặc lấy một tài nguyên mới để dùng nội bộ, phương thức đó thường chịu trách nhiệm đóng tài nguyên trước khi kết thúc. Try-with-resources thể hiện rõ trách nhiệm này và bảo đảm đóng trong cả đường đi bình thường lẫn đường đi có ngoại lệ.

~~~java
public static String firstLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.readLine();
    }
}
~~~

`return` vẫn làm Java đóng `reader` trước khi phương thức thực sự trả kết quả cho bên gọi.

### 4.2. Tài nguyên được mượn từ bên gọi

Khi một phương thức nhận stream, reader hoặc connection từ bên gọi, cần xác định rõ quyền quản lý tài nguyên. Nếu hợp đồng nói bên gọi vẫn sở hữu và sẽ tiếp tục sử dụng tài nguyên, phương thức nhận chỉ nên dùng nó, không tự đóng nó.

~~~java
public static String readFirstLine(BufferedReader reader) throws IOException {
    // Phương thức này chỉ mượn reader và không đóng nó.
    return reader.readLine();
}
~~~

Bên gọi chịu trách nhiệm mở và đóng:

~~~java
try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line = readFirstLine(reader);
    System.out.println(line);
}
~~~

Không dùng `try (reader)` bên trong `readFirstLine()` trong trường hợp này, vì làm vậy sẽ đóng tài nguyên mà bên gọi vẫn đang quản lý. Tên biến hoặc việc truyền tham chiếu vào phương thức không tự động chuyển quyền sở hữu.

### 4.3. Tránh nhiều nơi cùng chịu trách nhiệm đóng

Một tài nguyên có thể được tham chiếu bởi nhiều biến, nhưng điều đó không có nghĩa mọi nơi đều nên đóng nó. Nếu nhiều đoạn mã cùng nghĩ mình là chủ sở hữu, một đoạn có thể đóng tài nguyên trong khi đoạn khác vẫn đang dùng, hoặc một đối tượng có thể bị đóng lặp lại.

Các nguyên tắc thực tế:

- Xác định rõ đoạn mã mở hoặc nhận quyền quản lý tài nguyên.
- Nếu phương thức tạo tài nguyên để dùng nội bộ, phương thức đó nên đóng tài nguyên trước khi trả về.
- Nếu phương thức chỉ mượn tài nguyên từ bên gọi, ghi rõ rằng phương thức không đóng tài nguyên đó.
- Nếu quyền quản lý được chuyển cho đối tượng khác, quy ước chuyển giao phải rõ ràng và chỉ có một bên chịu trách nhiệm đóng.
- Không gọi `close()` thủ công bên trong một khối try-with-resources trừ khi API có lý do cụ thể yêu cầu điều đó.
- Không dùng tài nguyên sau khi phạm vi quản lý của nó kết thúc.

## 5. Ví dụ hoàn chỉnh: biến vẫn trong phạm vi sau khi tài nguyên đóng

Ví dụ sau tương thích với Java 9 trở lên. Chương trình tạo file tạm, đọc một dòng bằng `BufferedReader`, dùng cú pháp Java 9 `try (reader)`, sau đó minh họa rằng biến vẫn tồn tại nhưng tài nguyên đã đóng.

**Tệp:** `ResourceScopeDemo.java`

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;

public class ResourceScopeDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("resource-scope-", ".txt");
        try {
            Files.write(
                file,
                Collections.singletonList("Hello from Java 9"),
                StandardCharsets.UTF_8
            );

            BufferedReader reader =
                Files.newBufferedReader(file, StandardCharsets.UTF_8);

            try (reader) {
                System.out.println(reader.readLine());
            }

            System.out.println("reader is still in scope: " + (reader != null));

            try {
                reader.readLine();
            } catch (IOException exception) {
                System.out.println("read after close: " + exception.getMessage());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~text
javac ResourceScopeDemo.java
java ResourceScopeDemo
~~~

Kết quả:

~~~text
Hello from Java 9
reader is still in scope: true
read after close: Stream closed
~~~

Kết quả cho thấy `reader` vẫn có thể được tham chiếu sau khối `try`, nhưng `BufferedReader` đã đóng nên thao tác đọc tiếp theo phát sinh `IOException`. Khối `finally` chỉ dùng để xóa file tạm; việc đóng reader đã được try-with-resources đảm nhiệm.

## 6. Lỗi thường gặp và cách xử lý

| Lỗi | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Dùng biến ngoài phạm vi | Biến được khai báo trong một khối hoặc tiêu đề `try` đã ra khỏi phạm vi | Khai báo biến ở khối bao ngoài nếu cần dùng ở nhiều vị trí; chỉ mở rộng phạm vi khi thật sự cần |
| Đọc biến cục bộ trước khi gán | Biến cục bộ không có giá trị mặc định | Gán giá trị trên mọi nhánh trước khi sử dụng |
| Dùng tài nguyên sau `close()` | Phạm vi biến vẫn còn nhưng tài nguyên đã đóng | Giới hạn việc sử dụng trong khối try-with-resources hoặc mở tài nguyên mới |
| Dùng `try (resource)` với biến bị gán lại | Biến không còn `final` hoặc *effectively final* | Dùng một biến tài nguyên riêng, không thay đổi tham chiếu trong thời gian quản lý |
| Đóng tài nguyên của bên gọi | Phương thức nhận nhầm tài nguyên được mượn là tài nguyên mình sở hữu | Quy định rõ ownership trong hợp đồng phương thức và để bên sở hữu đóng |
| Đóng cùng tài nguyên ở nhiều nơi | Nhiều alias hoặc wrapper cùng thực hiện `close()` | Chọn một nơi quản lý vòng đời; hiểu wrapper có đóng tài nguyên bên dưới hay không |
| Bỏ qua ngoại lệ khi đóng | `close()` có thể phát sinh ngoại lệ | Xử lý ngoại lệ chính và kiểm tra `getSuppressed()` khi cần chẩn đoán |

## 7. Quy tắc thực hành

1. Đặt biến ở phạm vi hẹp nhất đủ đáp ứng nhu cầu sử dụng; phạm vi hẹp giúp giảm nhầm lẫn và hạn chế việc vô tình dùng sai biến.
2. Phân biệt rõ biến còn truy cập được với đối tượng còn ở trạng thái hợp lệ để sử dụng.
3. Dùng try-with-resources cho tài nguyên triển khai `AutoCloseable` khi đoạn mã hiện tại chịu trách nhiệm đóng tài nguyên.
4. Từ Java 9, dùng `try (resource)` cho biến có sẵn khi biến đó là `final` hoặc *effectively final* và quyền quản lý việc đóng thuộc về đoạn mã hiện tại.
5. Nếu phương thức chỉ mượn tài nguyên từ bên gọi, không tự đóng tài nguyên đó; mô tả rõ quy ước trong tên, tài liệu hoặc hợp đồng API.
6. Với nhiều tài nguyên, xem xét thứ tự khởi tạo, thứ tự đóng và quan hệ giữa wrapper với tài nguyên bên dưới.
7. Không dựa vào garbage collection để đóng file, socket, stream hoặc kết nối.

## 8. Tự kiểm tra

- Một biến khai báo trong thân `if` có được dùng sau dấu `}` của `if` không? Không, vì nó đã ra khỏi phạm vi.
- Một biến `BufferedReader` khai báo trước `try (reader)` có còn trong phạm vi sau khối `try` không? Có, nếu khối bao ngoài vẫn còn; tuy nhiên reader đã đóng.
- Điều kiện để dùng biến có sẵn trong tiêu đề try-with-resources từ Java 9 là gì? Biến phải là `final` hoặc *effectively final* và có kiểu triển khai `AutoCloseable`.
- Try-with-resources đóng nhiều tài nguyên theo thứ tự nào? Đóng ngược thứ tự khai báo, tức tài nguyên được khởi tạo sau sẽ đóng trước.
- Phương thức nhận một stream do bên gọi mở có nên tự đóng stream không? Chỉ khi hợp đồng chuyển quyền quản lý việc đóng cho phương thức; nếu chỉ mượn, bên gọi tiếp tục chịu trách nhiệm.

Điểm cần nhớ: **phạm vi quyết định nơi tên biến được phép xuất hiện; quyền quản lý tài nguyên quyết định ai phải đóng nó; trạng thái đóng quyết định tài nguyên còn dùng được hay không.** Java 9 cho phép dùng biến `final` hoặc *effectively final* đã có trong try-with-resources, nhưng không tự chuyển quyền sở hữu tài nguyên giữa các phần của chương trình.