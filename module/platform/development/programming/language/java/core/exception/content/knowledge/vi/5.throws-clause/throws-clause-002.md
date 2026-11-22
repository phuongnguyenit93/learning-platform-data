# Khai báo một hoặc nhiều kiểu ngoại lệ với mệnh đề `throws` trong Java

## 1. Mục tiêu học tập

Một phương thức có thể hoàn thành bình thường hoặc kết thúc bằng ngoại lệ. Trong Java, mệnh đề `throws` của phương thức hoặc constructor cho người đọc và trình biên dịch biết những **kiểu ngoại lệ** mà lời gọi có thể truyền ra ngoài, đặc biệt là các *checked exception*.

Sau bài học, bạn có thể:

- Viết đúng cú pháp `throws` với **một** kiểu hoặc **nhiều** kiểu ngoại lệ, phân cách bằng dấu phẩy.
- Phân biệt mệnh đề khai báo `throws` với câu lệnh ném ngoại lệ `throw`.
- Hiểu cách trình biên dịch kiểm tra checked exception và cách bên gọi dùng `try/catch` hoặc tiếp tục khai báo `throws`.
- Chọn kiểu ngoại lệ cụ thể hay kiểu cha thích hợp, tránh khai báo quá rộng.
- Áp dụng `throws` trong phương thức, constructor, phương thức triển khai interface và phương thức ghi đè.
- Phân biệt danh sách `throws` với cú pháp `multi-catch`, đồng thời nhận diện một số lỗi biên dịch phổ biến.

Các ví dụ dùng Java 17+; nhiều ví dụ là chương trình độc lập có thể chạy bằng `javac` và `java`.

## 2. `throws` dùng để làm gì?

Trong khai báo phương thức, `throws` xuất hiện **sau danh sách tham số, trước thân phương thức**:

```java
public String load() throws java.io.IOException {
    // Thân phương thức.
    return "data";
}
```

Đây là một mảnh mã phương thức. Nó khai báo rằng phương thức **được phép truyền** `IOException` ra bên ngoài. Nó không có nghĩa mỗi lần gọi đều thực sự ném ngoại lệ. Việc không ném lỗi trong phần thân ví dụ trên vẫn hợp lệ.

Cú pháp tổng quát:

```text
[modifiers] ReturnType methodName(parameters)
        throws ExceptionType1, ExceptionType2, ... {
    // statements
}
```

Trong cú pháp trên, `ExceptionType1` và `ExceptionType2` là tên kiểu, không phải đối tượng. Từng kiểu phải là một lớp con của `Throwable` hoặc một biến kiểu có ràng buộc tương thích. Thực tế thường dùng tên lớp con của `Exception`; Java vẫn cho phép khai báo kiểu unchecked như `IllegalArgumentException`.

Ví dụ khai báo **một kiểu**:

```java
void readFile() throws java.io.IOException {
    // Đọc tệp; một lời gọi API bên trong có thể ném IOException.
}
```

Ví dụ khai báo **nhiều kiểu**:

```java
void process() throws java.io.IOException, java.text.ParseException {
    // Có thể thất bại khi đọc dữ liệu hoặc phân tích nội dung.
}
```

Hai đoạn vừa rồi là **các phương thức minh họa**, không phải chương trình `main` độc lập. Chúng cho thấy cách đặt các kiểu sau `throws`, cách nhau bằng dấu **phẩy**. Có thể xuống dòng giữa các kiểu để dễ đọc; xuống dòng không thay đổi ý nghĩa khai báo.

### Danh sách `throws` không phải danh sách các ngoại lệ chắc chắn sẽ phát sinh

- `throws IOException`: phương thức có thể để ngoại lệ tương thích với `IOException` truyền ra.
- `throws IOException, ParseException`: phương thức có thể truyền một ngoại lệ thuộc nhóm I/O hoặc nhóm phân tích dữ liệu (hoặc các ngoại lệ phù hợp với các kiểu đó) trên **những đường thực thi khác nhau**.
- Một lần ném bình thường sẽ truyền **một đối tượng `Throwable`** tại một thời điểm; danh sách `throws` không yêu cầu phương thức ném tất cả kiểu đã liệt kê.
- Không bắt buộc thứ tự ưu tiên giữa các kiểu trong `throws`; thay đổi vị trí tên lớp không thay đổi quy tắc kiểm tra ngoại lệ của trình biên dịch.
- Không có giới hạn bắt buộc phải liệt kê hết mọi `RuntimeException` hay `Error` có thể xảy ra.

## 3. Phân biệt `throw` và `throws`

Đây là hai vai trò khác nhau: `throws IOException, ParseException` **liệt kê hai kiểu lỗi có thể thoát** trong chữ ký, còn `throw new ParseException("invalid", 0);` **ném một đối tượng cụ thể** khi nhánh thực thi đi tới câu lệnh. `throws` không tạo đối tượng, không ghi log và không bắt lỗi.

Điểm quan trọng của bài này là **cú pháp liệt kê**: sau `throws` dùng dấu **phẩy** (`throws IOException, ParseException`); dấu `|` chỉ dùng trong multi-catch (`catch (IOException | ParseException ex)`). Bên gọi phải xử lý các checked exception có thể thoát theo hợp đồng, dù phần lớn lần chạy thành công. Phân biệt sâu hơn hành động ném và hợp đồng khai báo được thực hành riêng ở bài `throw` so với `throws`.

## 4. Vì sao checked exception phải được bắt hoặc khai báo?

Phân cấp liên quan:

```text
Throwable
├── Error                         (unchecked)
│   └── ...
└── Exception
    ├── IOException               (checked)
    │   └── FileNotFoundException (checked)
    ├── ParseException            (checked)
    └── RuntimeException          (unchecked)
        ├── IllegalArgumentException
        └── NullPointerException
```

Đây là sơ đồ rút gọn các lớp tiêu biểu. Một ngoại lệ là **checked** khi kiểu của nó không thuộc nhánh `RuntimeException` hoặc `Error` của `Throwable`.

Quy tắc cơ bản: nếu phần thân phương thức/constructor **có thể phát sinh checked exception** mà không được xử lý tại chỗ, khai báo `throws` của phương thức/constructor phải liệt kê kiểu đó hoặc một **kiểu cha** phù hợp.

Có hai lựa chọn ở bên gọi:

1. **Bắt và xử lý** bằng `try/catch` khi có khả năng phục hồi tại đây.
2. **Tiếp tục khai báo** bằng `throws` để đẩy trách nhiệm xét xử lý lên phương thức gọi tiếp theo.

Các ngoại lệ unchecked có thể được bắt và có thể được khai báo, nhưng trình biên dịch **không buộc** phải khai báo hay bắt chúng.

Về mặt kiểm tra ngoại lệ, lời gọi đến một phương thức được khai báo `throws IOException` được xem là có thể ném checked exception thuộc kiểu đó, dù một lần chạy cụ thể không bao giờ xảy ra lỗi. Vì vậy, mã bên gọi phải thỏa hợp đồng dựa trên **chữ ký được nhìn thấy khi biên dịch**.

## 5. Khai báo một kiểu: chương trình chạy hoàn chỉnh

Tạo tệp **`SingleThrowsDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;

public class SingleThrowsDemo {
    static String firstLine(Reader source) throws IOException {
        try (BufferedReader reader = new BufferedReader(source)) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        String result = firstLine(new StringReader("alpha\nbeta"));
        System.out.println(result);
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac SingleThrowsDemo.java
java SingleThrowsDemo
```

`stdout` chính xác:

```text
alpha
```

Giải thích:

- `BufferedReader.readLine()` khai báo có thể ném `IOException`. Mặc dù nguồn là `StringReader` và ca thử chạy thành công, `firstLine` vẫn phải xử lý hoặc khai báo khả năng xảy ra checked exception từ phương thức API mà nó gọi.
- `firstLine(...) throws IOException` chọn **truyền trách nhiệm** xử lý lên bên gọi.
- `main(...) throws IOException` tiếp tục khai báo nên ví dụ vẫn biên dịch hợp lệ. Nếu checked exception thực sự thoát khỏi `main`, chương trình không có handler trong mã ví dụ này.
- `try-with-resources` đóng `BufferedReader` và nguồn được bọc sau khi sử dụng, kể cả khi quá trình đọc báo lỗi; một lỗi từ `close()` cũng thuộc hợp đồng kiểm tra ngoại lệ tương ứng.

Trường hợp muốn xử lý lỗi thay vì truyền tiếp:

```java
try {
    String line = firstLine(source);
    System.out.println(line);
} catch (java.io.IOException failure) {
    System.err.println("Cannot read data: " + failure.getMessage());
}
```

Đây chỉ là **mảnh minh họa**, giả định biến `source` đã được khai báo hợp lệ và phương thức `firstLine` có sẵn. `catch` nên có hành động hữu ích: trả kết quả thất bại, ghi nhận ngữ cảnh, phục hồi hoặc truyền lại nguyên nhân, tùy ứng dụng.

## 6. Khai báo nhiều kiểu: một phương thức có các đường lỗi khác nhau

Khi việc xử lý có nhiều khả năng thất bại cần phân biệt, danh sách `throws` giữ lại thông tin cụ thể cho người gọi.

Tạo tệp **`MultipleThrowsDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.text.ParseException;

public class MultipleThrowsDemo {
    static int readScore(Reader source)
            throws IOException, ParseException {
        try (BufferedReader reader = new BufferedReader(source)) {
            String line = reader.readLine();

            if (line == null) {
                throw new ParseException("missing score", 0);
            }

            try {
                return Integer.parseInt(line);
            } catch (NumberFormatException failure) {
                ParseException parsed =
                        new ParseException("invalid score", 0);
                parsed.initCause(failure);
                throw parsed;
            }
        }
    }

    public static void main(String[] args) {
        try {
            int score = readScore(new StringReader("85"));
            System.out.println("valid=" + score);
        } catch (IOException | ParseException failure) {
            System.out.println("unexpected="
                    + failure.getClass().getSimpleName());
        }

        try {
            readScore(new StringReader("bad"));
        } catch (IOException | ParseException failure) {
            System.out.println("invalid="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac MultipleThrowsDemo.java
java MultipleThrowsDemo
```

`stdout` chính xác:

```text
valid=85
invalid=ParseException
```

**Vì sao cần hai kiểu checked exception?**

- `reader.readLine()` và thao tác đóng reader có thể báo `IOException`.
- Một dòng trống hoặc chứa dữ liệu không phải số được phương thức này chủ động chuyển thành `ParseException`; trường hợp chuyển đổi thất bại giữ `NumberFormatException` ban đầu ở `getCause()`.
- Cả `IOException` và `ParseException` có thể đi ra khỏi `readScore`, nên khai báo đầy đủ `throws IOException, ParseException`.
- `main` dùng `catch (IOException | ParseException failure)` để bắt hai loại ở cùng một handler. Đây là **multi-catch**; dấu `|` chỉ hợp lệ trong `catch` thích hợp, **không** phải trong danh sách `throws`.

Ví dụ có tính quyết định: `StringReader("85")` cho dữ liệu hợp lệ, còn `StringReader("bad")` tạo `ParseException` như mô tả. Không phụ thuộc file, mạng hay quyền truy cập của máy.

### Khi cần xử lý hai kiểu bằng hai cách khác nhau

Đoạn mã minh họa dùng các phương thức đã khai báo phía trên:

```java
try {
    int score = readScore(source);
    saveScore(score);
} catch (ParseException failure) {
    reportInvalidInput(failure);
} catch (IOException failure) {
    reportReadFailure(failure);
}
```

Đây là **mảnh minh họa**, không phải chương trình chạy độc lập: cần khai báo `source`, `saveScore`, `reportInvalidInput` và `reportReadFailure`. Khi hành động phục hồi khác nhau, các `catch` riêng biệt thường dễ đọc hơn multi-catch.

## 7. Kiểu ngoại lệ khai báo phải bao phủ đường lỗi nào?

Giả sử một phương thức có thể phát sinh `FileNotFoundException`, là lớp con của `IOException`. Cả hai chữ ký sau đều có thể thỏa kiểm tra ngoại lệ:

```java
void loadA() throws java.io.FileNotFoundException {
    // ...
}

void loadB() throws java.io.IOException {
    // ...
}
```

Hai đoạn này là **chữ ký minh họa**. Khai báo kiểu cha bao phủ ngoại lệ con, nhưng cũng mở rộng hợp đồng đối với bên gọi. Cụ thể:

- `throws FileNotFoundException`: người gọi biết loại lỗi checked được khai báo tương đối hẹp.
- `throws IOException`: người gọi phải chuẩn bị cho nhiều loại lỗi thuộc nhóm I/O hơn.
- `throws Exception` hoặc `throws Throwable`: hợp pháp trong những trường hợp thích hợp, nhưng thường quá rộng đối với API ứng dụng vì giảm độ rõ ràng và khiến bên gọi phải xử lý kiểu rộng.
- Khai báo cả `throws FileNotFoundException, IOException` có thể hợp lệ nhưng **dư thừa** về khả năng checked exception vì `IOException` đã bao phủ `FileNotFoundException`.
- Không cần thêm `RuntimeException` vào danh sách chỉ để chương trình biên dịch.

**Quy tắc thiết kế:** ưu tiên danh sách những kiểu checked exception có ý nghĩa độc lập với bên gọi; dùng kiểu cha khi API thật sự muốn cho phép họ lớp con đó. Không thêm các kiểu lỗi chỉ để “phòng hờ” vô căn cứ.

### Danh sách khai báo không đồng nghĩa cơ chế xử lý

`throws` không tự tạo retry, fallback, ghi log hay rollback. Khi checked exception xảy ra, nếu thân phương thức không bắt được nó, việc thực thi hoàn thành đột ngột và lỗi lan lên bên gọi. Nếu không có handler tương thích trong chuỗi gọi, nó có thể đi đến handler lỗi không được bắt của luồng.

Cũng đừng mặc định rằng một kiểu ngoại lệ đã khai báo chắc chắn xuất hiện trong từng lời gọi. Khai báo chỉ là hợp đồng về **khả năng** phát sinh.

## 8. `throws` trong constructor

Constructor cũng liệt kê **một hoặc nhiều loại checked exception**, ngăn bằng dấu phẩy, khi khởi tạo phải đọc hoặc kiểm tra dữ liệu. Ví dụ khai báo một constructor xử lý cả I/O và sai định dạng:

```java
// Đặt trong lớp Config, với java.io.Reader được caller cung cấp.
Config(java.io.Reader source)
        throws java.io.IOException, java.text.ParseException {
    int first = source.read();
    if (first != '{') {
        throw new java.text.ParseException("expected '{'", 0);
    }
}
```

Đây là **mảnh constructor minh họa**, không phải tệp Java độc lập. `source.read()` có thể ném `IOException`; phép kiểm tra định dạng có thể ném `ParseException`. Nơi gọi `new Config(reader)` phải bắt hoặc khai báo **cả hai** kiểu checked exception. Constructor không có kiểu trả về, và `throws` đặt sau danh sách tham số, trước thân. Nếu constructor ném, lời gọi `new` không trả đối tượng đã khởi tạo thành công; phương thức gọi không được tự xem thất bại như một kết quả hợp lệ.

Với constructor phức tạp, quản lý resource và cleanup đúng cách; ví dụ này không đóng `Reader` vì ownership của nguồn đầu vào vẫn thuộc caller.

## 9. `throws` và ghi đè phương thức (`override`)

Nếu interface công bố **nhiều loại checked exception**, implementation có thể khai báo tập hẹp hơn, không được thêm loại checked rộng hơn/không tương thích. Ví dụ:

```java
// Hai khai báo minh họa, cần đặt trong tệp Java thích hợp.
interface DocumentSource {
    String load() throws java.io.IOException, java.text.ParseException;
}

class ParsedSource implements DocumentSource {
    @Override
    public String load() throws java.text.ParseException {
        return "valid"; // Triển khai này không phát sinh lỗi I/O.
    }
}
```

`ParsedSource.load()` bỏ `IOException`, giữ `ParseException`; đây là cách thu hẹp hợp đồng hợp lệ. Thay bằng `throws Exception` sẽ không hợp lệ vì mở rộng phạm vi checked exception. Tuy nhiên, khi lời gọi đi qua biến có kiểu tĩnh `DocumentSource`, compiler vẫn áp dụng **hai** loại checked exception của interface, không dựa vào implementation có thể được chọn lúc chạy.

Điểm riêng của danh sách nhiều kiểu là việc thu hẹp có thể bỏ **một nhánh lỗi** hoặc dùng subtype hợp lệ của nhánh đó. Không phải mọi override đều phải sao chép nguyên danh sách `throws` của interface.

## 10. Mệnh đề `throws` trong các chữ ký API

Mệnh đề này có thể xuất hiện trong:

- Phương thức thường, kể cả `static`.
- Phương thức `abstract` và khai báo phương thức của interface.
- Phương thức `default` của interface.
- Constructor, bao gồm constructor có phạm vi `public`, `protected` hoặc package-private.
- Phương thức có tham số kiểu tổng quát; trong những trường hợp nâng cao, loại ngoại lệ cũng có thể là một **biến kiểu** bị chặn trên bởi `Throwable`.

Ví dụ khai báo hợp đồng:

```java
interface Repository {
    byte[] read(String key) throws java.io.IOException;
}

abstract class Importer {
    abstract void importData() throws java.io.IOException,
            java.text.ParseException;
}
```

Đây là hai khai báo kiểu hợp lệ để minh họa chữ ký; chúng không chứa `main`. Những phương thức không có thân này vẫn dùng `throws` để công bố trách nhiệm xử lý checked exception cho bên triển khai và bên gọi.

### `throws` không thuộc phần phân biệt overload

Không thể tạo hai phương thức chỉ khác danh sách `throws`:

```java
// Không hợp lệ nếu đặt cả hai trong cùng một lớp:
void execute() throws java.io.IOException { }
void execute() throws java.text.ParseException { }
```

Đây là **ví dụ sai có chủ ý**: Java không xem hai chữ ký là hai overload khác nhau chỉ vì mệnh đề `throws` khác nhau. Hãy phân biệt phương thức bằng tên hoặc tham số khi thật sự có hai thao tác khác nhau.

### `throws` không làm thay đổi kiểu trả về

Một phương thức `int parse() throws ParseException` vẫn có kiểu trả về `int` trên đường thành công. Nếu lỗi được ném, không có giá trị `int` trả về cho lời gọi đó; luồng điều khiển đi theo cơ chế ngoại lệ. `throws` không phải kiểu union hoặc một wrapper kiểu `Result`.

## 11. `throws` và biểu thức lambda

Thân lambda cũng phải tương thích với tập checked exception mà **phương thức chức năng đích** cho phép.

Ví dụ hợp lệ bằng interface tự định nghĩa:

```java
import java.io.IOException;

@FunctionalInterface
interface IoAction {
    void run() throws IOException;
}

public class LambdaThrowsDemo {
    public static void main(String[] args) throws IOException {
        IoAction action = () -> {
            System.out.println("action completed");
        };
        action.run();
    }
}
```

Lưu thành **`LambdaThrowsDemo.java`** rồi chạy:

```bash
javac LambdaThrowsDemo.java
java LambdaThrowsDemo
```

`stdout`:

```text
action completed
```

Nếu thân lambda thực sự ném `IOException`, nó hợp lệ với `IoAction` vì phương thức chức năng cho phép `throws IOException`. Nhưng một lambda được gán cho `Runnable` không thể tự ném checked `IOException` ra ngoài thân, vì `Runnable.run()` không khai báo checked exception.

Điều này giải thích vì sao thêm `throws IOException` vào **phương thức bao ngoài** chưa đủ để cho một lambda kiểu `Runnable` ném checked exception không tương thích: quy tắc kiểm tra của thân lambda phụ thuộc kiểu chức năng mà lambda được gán vào.

## 12. Các lỗi cú pháp và thiết kế thường gặp

| Viết sai / quan niệm sai | Vấn đề | Cách đúng |
| --- | --- | --- |
| `void f() throw IOException` | `throw` không dùng để khai báo | `void f() throws IOException` |
| `void f() throws new IOException()` | `throws` cần kiểu, không phải đối tượng | `void f() throws IOException` |
| `void f() throws IOException \| ParseException` | Dùng nhầm dấu `|` của multi-catch | `void f() throws IOException, ParseException` |
| `throw IOException;` | `throw` cần biểu thức có kiểu `Throwable` | `throw new IOException();` hoặc ném lại biến đã bắt |
| Gọi phương thức `throws IOException` mà không bắt/khai báo | Không thỏa checked exception | Dùng `catch (IOException e)` hoặc khai báo `throws IOException` |
| `throws Exception` cho mọi lỗi | Làm hợp đồng rộng và buộc xử lý chung | Ưu tiên các kiểu checked cụ thể có ý nghĩa |
| Chỉ thêm `throws` rồi coi như đã xử lý sự cố | Ngoại lệ vẫn có thể lan ra ngoài | Xác định ranh giới ứng dụng chịu trách nhiệm xử lý |
| Thêm checked exception rộng hơn khi `override` | Có thể vi phạm hợp đồng phương thức cha | Giữ nguyên, thu hẹp hoặc bỏ checked exception |
| Cho rằng danh sách `throws` bảo đảm kiểu lỗi sẽ xuất hiện | Khai báo chỉ mô tả khả năng | Kiểm tra đường thực thi và nguyên nhân thực tế |
| Nghĩ `throws` bắt buộc cho mọi `RuntimeException` | Unchecked exception không bị kiểm tra bắt buộc | Có thể không khai báo, nhưng tài liệu API vẫn nên rõ |

Một trường hợp nữa: trong `catch (FileNotFoundException | IOException e)`, hai lựa chọn nằm cùng cây kế thừa nên multi-catch không hợp lệ vì có quan hệ cha-con. Trong **danh sách `throws`**, việc liệt kê cả hai kiểu lại không mang ý nghĩa khác biệt hữu ích vì `IOException` đã bao phủ `FileNotFoundException`. Cú pháp và quy tắc của `throws` và `catch` cần được xét riêng.

## 13. Cách viết hợp đồng ngoại lệ rõ ràng

### 13.1. Chọn kiểu mô tả đúng nguồn lỗi

Ví dụ một hàm đọc dữ liệu và giải mã định dạng: `throws IOException, ParseException` giúp người gọi phân biệt lỗi truy cập dữ liệu và lỗi phân tích nội dung. Nếu chỉ dùng `throws Exception`, người gọi mất bớt khả năng biết cần bắt loại cụ thể nào mà không phải kiểm tra sâu hơn.

### 13.2. Giữ nguyên nguyên nhân khi chuyển tầng

Nếu bạn cần chuyển `NumberFormatException` thành một checked `ParseException`, hãy lưu ngoại lệ ban đầu dưới dạng `cause` như ví dụ `MultipleThrowsDemo`. Stack trace và nguyên nhân gốc giúp phân tích khi nhiều tầng API cùng truyền ngoại lệ.

### 13.3. Không dùng `throws` để thay kiểm tra đầu vào

Hợp đồng `throws IllegalArgumentException` có thể là tài liệu hữu ích, nhưng vẫn phải kiểm tra đầu vào phù hợp ở chỗ cần thiết. Tự thêm tên kiểu vào chữ ký không tạo ra câu lệnh kiểm tra.

### 13.4. Sử dụng `@throws` trong JavaDoc

`@throws IOException` là **thẻ tài liệu**, giải thích điều kiện lỗi. Nó không thay thế mệnh đề `throws` trong khai báo phương thức khi checked exception cần được khai báo. Khi xây dựng API public, nên dùng cả chữ ký chính xác và tài liệu giải thích điều kiện thất bại.

Ví dụ chữ ký kèm JavaDoc:

```java
/**
 * Đọc cấu hình từ nguồn cung cấp.
 *
 * @param source nguồn dữ liệu
 * @return nội dung cấu hình
 * @throws java.io.IOException nếu thao tác đọc thất bại
 * @throws java.text.ParseException nếu nội dung không hợp lệ
 */
String loadConfig(java.io.Reader source)
        throws java.io.IOException, java.text.ParseException {
    // Phần thân minh họa được giản lược.
    return "";
}
```

Đây là **mảnh phương thức minh họa** về tài liệu API và chữ ký. Trong sản phẩm thật, phần thân phải thực hiện công việc đã cam kết; không dùng bản giả lập để thay logic đọc/parse.

## 14. Câu hỏi tự kiểm tra

1. **Cú pháp một kiểu checked exception là gì?** Ví dụ: `void load() throws IOException`.
2. **Hai kiểu được phân cách thế nào?** Bằng dấu phẩy: `throws IOException, ParseException`.
3. **`throws` có thực sự ném đối tượng ngoại lệ không?** Không. Câu lệnh `throw` hoặc thao tác phát sinh lỗi tại runtime mới thực hiện việc ném.
4. **Phương thức khai báo `throws IOException` nhưng một lần chạy không ném lỗi có hợp lệ không?** Có.
5. **Gọi API có checked exception mà không bắt, bạn phải làm gì?** Khai báo tiếp kiểu được phép truyền lên bằng `throws` hoặc kiểu cha tương thích.
6. **`throws IOException | ParseException` có đúng không?** Không. Dấu `|` dành cho multi-catch; `throws` dùng dấu phẩy.
7. **`RuntimeException` bắt buộc phải khai báo trong `throws`?** Không. Nó là unchecked.
8. **Một phương thức triển khai interface `throws IOException` có thể bỏ `throws` không?** Có, nếu phần thân hợp lệ và không truyền checked exception không được phép.
9. **Có thể overload hai phương thức chỉ khác mệnh đề `throws`?** Không.
10. **`throws IOException, ParseException` nghĩa là cả hai được ném cùng lúc?** Không. Mỗi lần ném truyền một đối tượng ngoại lệ; hai kiểu biểu diễn các khả năng.

## 15. Tài liệu chính thức (Java 17)

- [Java Language Specification §8.4.6 — Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): cú pháp và quy tắc khai báo kiểu ngoại lệ.
- [Java Language Specification §8.8.5 — Constructor Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.5): mệnh đề `throws` trong constructor.
- [Java Language Specification §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): kiểm tra checked exception.
- [Java Language Specification §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): giới hạn checked exception khi ghi đè.
- [Java Language Specification §14.20 — The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): `catch` và multi-catch.
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html), [ParseException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParseException.html): các kiểu checked exception trong ví dụ.

**Điểm cần nhớ:** Sau `throws` là **một hoặc nhiều kiểu ngoại lệ**, ngăn cách bằng dấu phẩy. Mệnh đề này công bố hợp đồng để trình biên dịch và bên gọi xác định trách nhiệm với checked exception; nó không tự tạo, bắt hoặc sửa một lỗi nào.
