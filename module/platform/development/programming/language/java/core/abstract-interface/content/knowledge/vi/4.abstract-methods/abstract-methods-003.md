# Phương thức abstract trong Java: tham số, kiểu trả về và mệnh đề throws

## 1. Ba thành phần tạo nên hợp đồng của phương thức

Một phương thức `abstract` khai báo **điều mà lớp con hoặc lớp triển khai phải cung cấp** nhưng không có thân phương thức. Bên cạnh tên phương thức, phần khai báo xác định ba khía cạnh quan trọng:

- **Danh sách tham số**: dữ liệu mà người gọi phải truyền vào, theo thứ tự và kiểu xác định.
- **Kiểu trả về**: kiểu kết quả mà người gọi được phép nhận (hoặc `void` nếu không trả về giá trị).
- **Mệnh đề `throws`**: các ngoại lệ checked mà lời gọi có thể cần xử lý hoặc khai báo tiếp.

Ví dụ khai báo trong abstract class:

~~~java
import java.io.IOException;

abstract class DocumentStore {
    public abstract CharSequence load(String id, int version) throws IOException;
}
~~~

Trong khai báo này, `id` là `String`, `version` là `int`, kết quả là `CharSequence`, còn `IOException` là ngoại lệ checked được công bố. Dấu `;` kết thúc khai báo; phương thức abstract **không được có thân `{ ... }`**.

Cùng ý tưởng trong interface:

~~~java
import java.io.IOException;

interface DocumentStore {
    CharSequence load(String id, int version) throws IOException;
}
~~~

Phương thức thông thường được khai báo trong interface như trên mặc nhiên là `public abstract` (có thể viết tường minh). Khi triển khai, phương thức tương ứng phải là `public`. Ngược lại, abstract class có thể khai báo phương thức abstract là `public`, `protected` hoặc package-private, tùy thiết kế API. Một phương thức abstract không thể đồng thời là `private`, `static` hoặc `final`: các đặc tính đó cản trở việc override.

## 2. Tham số: kiểu, thứ tự và khả năng override

### 2.1. Tham số hình thức và đối số thực tế

Ở khai báo `load(String id, int version)`, `id` và `version` là **tham số hình thức**. Trong lời gọi `store.load("manual", 2)`, `"manual"` và `2` là **đối số**. Người gọi phải cung cấp các đối số phù hợp với kiểu, thứ tự và số lượng tham số; Java sẽ kiểm tra tại thời điểm biên dịch.

Tên tham số giúp mã dễ đọc nhưng **không quyết định việc override**. Ví dụ, khai báo `process(String input, int count)` có thể được triển khai bằng `process(String text, int times)` vì hai danh sách kiểu vẫn tương ứng.

Java truyền tham số theo **giá trị**: với kiểu nguyên thủy, phương thức nhận bản sao giá trị; với kiểu tham chiếu, phương thức nhận bản sao giá trị tham chiếu. Do đó, có thể thay đổi trạng thái của đối tượng mutable mà tham chiếu cùng trỏ tới, nhưng gán lại tham số không làm biến tham chiếu ở nơi gọi trỏ sang đối tượng mới.

### 2.2. Quy tắc quan trọng khi override

Khi hiện thực phương thức abstract, phương thức override cần có tên và danh sách kiểu tham số tương ứng theo quy tắc method signature/subsignature của Java. Với ví dụ không dùng generic, hãy coi **số lượng, thứ tự và kiểu tham số phải giữ nguyên**:

~~~java
abstract class MessageFormatter {
    abstract String format(String content, int width);
}

class PlainFormatter extends MessageFormatter {
    @Override
    String format(String text, int width) {
        return text.trim();
    }
}
~~~

`@Override` khiến trình biên dịch xác nhận đây thực sự là override. Nếu vô tình đổi `String` thành `Object`, hoặc đảo thứ tự tham số, khai báo có thể trở thành **overload** khác, còn phương thức abstract cũ vẫn chưa được triển khai. Một lớp con concrete trong tình huống đó sẽ không biên dịch.

Các quy tắc bổ sung:

- **Đổi tên tham số**: được; tên không thuộc method signature.
- **Thêm/bớt/đổi kiểu tham số**: không thay thế được phương thức abstract ban đầu; có thể tạo overload.
- **`String...` (varargs)**: chỉ được đặt ở tham số cuối; ở mức kiểu mảng, `String...` tương ứng `String[]`.
- **`final` trên tham số**: chỉ ngăn gán lại biến tham số trong thân phương thức, không làm thay đổi hợp đồng override.
- **Generic**: quy tắc override có thêm khái niệm subsignature và type erasure; không suy ra rằng mọi khác biệt cú pháp của tham số generic đều là overload hợp lệ.

Đặc biệt, **kiểu trả về và `throws` không tham gia phân biệt hai phương thức overload**. Không thể có hai phương thức cùng tên, cùng danh sách tham số và chỉ khác kiểu trả về hoặc `throws`.

## 3. Kiểu trả về: hợp đồng và covariance

Kiểu trả về xác định điều người gọi có thể sử dụng sau lời gọi. Phương thức có kiểu trả về khác `void` phải trả về biểu thức có kiểu tương thích trên mọi đường thực thi kết thúc bình thường; phương thức `void` không trả về một giá trị.

Khi override phương thức abstract:

| Kiểu trả về của phương thức gốc | Kiểu ở phương thức override | Kết quả |
| --- | --- | --- |
| `int` | `int` | Hợp lệ |
| `int` | `long` | Không hợp lệ (không tự nới kiểu nguyên thủy khi override) |
| `void` | `void` | Hợp lệ |
| `void` | `String` | Không hợp lệ |
| `Number` | `Integer` | Hợp lệ: kiểu tham chiếu con, **covariant return** |
| `CharSequence` | `String` | Hợp lệ: `String` triển khai `CharSequence` |
| `String` | `Object` | Không hợp lệ: trả về rộng hơn |

Ví dụ minh họa (độc lập với chương trình `Main` ở phần sau):

~~~java
abstract class Metric {
    public abstract Number measure(String input);
}

class LengthMetric extends Metric {
    @Override
    public Integer measure(String input) {
        return input.length();
    }
}
~~~

Lớp con có thể trả về `Integer` vì đây là subtype của `Number`. Người gọi nhìn biến qua kiểu `Metric` vẫn có hợp đồng tĩnh là `Number`; còn mã trong `LengthMetric` biết cụ thể kiểu `Integer`.

Với generic, compiler còn áp dụng các quy tắc return-type-substitutability; đôi khi tương thích cần xét kiểu generic hoặc tạo cảnh báo unchecked. Không dựa vào việc ép kiểu bừa để vượt qua lỗi khai báo: hãy thiết kế kiểu trả về từ hợp đồng gốc cho đúng.

## 4. Mệnh đề throws: điều gì được phép phát sinh?

### 4.1. `throws` là khai báo, còn `throw` là hành động

`throws IOException` nằm ở **khai báo phương thức**, thông báo cho compiler và người gọi rằng thao tác có thể hoàn thành bằng ngoại lệ checked này. Trong **thân phương thức**, câu lệnh `throw new IOException("...")` thực sự ném một ngoại lệ.

~~~java
import java.io.IOException;

abstract class FileSource {
    abstract String read(String path) throws IOException;
}
~~~

Không có thân phương thức để ném ngoại lệ ở đây, nhưng bản khai báo vẫn ràng buộc cách người gọi xử lý. Một phương thức có thể liệt kê nhiều kiểu ngoại lệ checked bằng dấu phẩy, ví dụ `throws IOException, java.text.ParseException`, nếu hợp đồng thực sự cần cả hai.

**Checked exceptions** như `IOException`, `ParseException` phải được bắt bằng `try/catch` hoặc được khai báo `throws` tiếp ở phương thức gọi (với các ngoại lệ checked có thể phát sinh). **Unchecked exceptions** là `RuntimeException` cùng các lớp con và `Error` cùng các lớp con; Java không bắt buộc khai báo hay bắt các loại này. Có thể ghi một unchecked exception trong `throws` để mô tả API, nhưng điều đó không tạo thêm nghĩa vụ bắt ngoại lệ cho người gọi.

Không nên khai báo `throws Exception` tràn lan: kiểu quá rộng che mờ trường hợp lỗi và buộc người gọi xử lý quá chung chung. Đừng khai báo một ngoại lệ checked chỉ để làm “danh sách dự phòng” nếu API không cần hợp đồng đó.

### 4.2. Ràng buộc throws khi override

Phương thức override được:

1. Giữ nguyên các ngoại lệ checked đã khai báo.
2. Khai báo **loại checked hẹp hơn** (subtype của loại checked mà phương thức được override cho phép).
3. Bỏ hẳn mệnh đề `throws` nếu bản triển khai không ném ngoại lệ checked.
4. Ném hoặc khai báo unchecked exceptions phù hợp bất kể khai báo gốc, dù API nên tài liệu hóa trường hợp có ý nghĩa.

Phương thức override **không được mở rộng** danh sách checked exceptions bằng kiểu checked rộng hơn hoặc hoàn toàn mới so với hợp đồng của phương thức được override.

Ví dụ hợp lệ:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

abstract class Resource {
    abstract String open(String path) throws IOException;
}

class MissingResource extends Resource {
    @Override
    String open(String path) throws FileNotFoundException {
        throw new FileNotFoundException(path);
    }
}

class FixedResource extends Resource {
    @Override
    String open(String path) {
        return "constant";
    }
}
~~~

`FileNotFoundException` là subtype của `IOException`; còn `FixedResource` bỏ `throws` vì triển khai của nó không cần ném checked exception.

Ví dụ **sai, cố ý không biên dịch**:

~~~java
import java.io.IOException;

abstract class Job {
    abstract void execute() throws IOException;
}

class InvalidJob extends Job {
    @Override
    void execute() throws Exception { // ERROR: Exception rộng hơn IOException
    }
}
~~~

Dù cả hai đều là checked exception, `Exception` rộng hơn `IOException`, nên Java từ chối override đó. Nếu lớp gốc không khai báo checked exception, lớp con cũng không thể tự thêm `throws IOException` cho cùng phương thức override.

### 4.3. Người gọi nhìn kiểu tĩnh, không chỉ nhìn triển khai

Nếu biến được khai báo theo interface hoặc abstract class với `throws IOException`, lời gọi qua biến đó vẫn chịu hợp đồng checked exception, **ngay cả khi đối tượng cụ thể override bằng phương thức không khai báo `throws`**. Trình biên dịch kiểm tra dựa trên khai báo phương thức được chọn theo kiểu tĩnh tại chỗ gọi.

Chẳng hạn, nếu `Resource resource = new FixedResource();` thì `resource.open("x")` vẫn phải đặt trong `try/catch` hoặc phương thức gọi khai báo `throws IOException`; còn `new FixedResource().open("x")` không đòi hỏi việc đó.

## 5. Ví dụ Java 17+: kết nối cả ba phần của hợp đồng

Ví dụ sau kết hợp interface, abstract class, danh sách tham số, kiểu trả về, `throws`, `throw` và xử lý ngoại lệ. Lưu toàn bộ vào tệp **Main.java**.

~~~java
import java.io.IOException;

interface Reader {
    String read(String id) throws IOException;
}

abstract class BaseReader implements Reader {
    protected abstract int sizeOf(String text);

    protected String prefix() {
        return "data:";
    }
}

final class MemoryReader extends BaseReader {
    @Override
    public String read(String id) throws IOException {
        if (id == null || id.isBlank()) {
            throw new IOException("invalid id");
        }
        return prefix() + id;
    }

    @Override
    protected int sizeOf(String text) {
        return text.length();
    }
}

public class Main {
    public static void main(String[] args) {
        BaseReader reader = new MemoryReader();

        try {
            String text = reader.read("notes");
            System.out.println(text);
            System.out.println(reader.sizeOf(text));
            reader.read("");
        } catch (IOException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy (JDK 17 trở lên):

~~~text
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả chuẩn:

~~~text
data:notes
10
caught: invalid id
~~~

Giải thích:

- `Reader.read(String id)` khai báo **một tham số kiểu `String`**, kết quả `String` và `throws IOException`; đây là hợp đồng của interface.
- `BaseReader` là abstract class nên được phép chưa triển khai `read` và tự thêm một phương thức abstract `sizeOf(String)` với kiểu trả về `int`.
- `MemoryReader` là lớp concrete: nó override đủ hai phương thức. `read` dùng quyền truy cập `public` đúng với phương thức từ interface; `sizeOf` giữ `protected`.
- Khi `id` rỗng, `read` thực sự ném `IOException` bằng `throw`. Khối `catch` xử lý ngoại lệ và in thông báo.
- `"data:notes"` có 10 ký tự. Lệnh `reader.read("")` chuyển điều khiển sang `catch`, nên không có dòng kết quả thứ tư.

## 6. Bảng kiểm tương thích khi triển khai

| Thành phần | Yêu cầu khi override phương thức abstract | Lỗi thường gặp |
| --- | --- | --- |
| Tên + tham số | Khớp method signature/subsignature; giữ số lượng, thứ tự và kiểu phù hợp | Đổi `String` thành `Object` rồi tưởng là override |
| Tên tham số | Có thể đổi | Nhầm tên là một phần signature |
| Kiểu trả về | Cùng `void`/kiểu nguyên thủy; kiểu tham chiếu có thể covariant theo luật Java | Đổi `int` thành `long`, hoặc `String` thành `Object` |
| `throws` checked | Giữ nguyên, thu hẹp hoặc bỏ; không thêm loại checked vượt hợp đồng gốc | Đổi `IOException` thành `Exception` |
| Ngoại lệ unchecked | Không bị quy tắc thu hẹp `throws` checked chi phối | Tưởng `RuntimeException` bắt buộc phải khai báo |
| Quyền truy cập | Không giảm khả năng truy cập khi override | Triển khai phương thức interface bằng `protected` |
| Thân phương thức | Khai báo abstract kết thúc bằng `;`; triển khai concrete có thân | Đặt `{ ... }` sau `abstract` hoặc thiếu override |
| `@Override` | Nên dùng để compiler kiểm tra chủ đích | Viết nhầm tham số làm xuất hiện overload không mong muốn |

## 7. Những nhầm lẫn cần tránh

**Nhầm giữa overload và override.** Hai phương thức có tên giống nhau nhưng kiểu/thứ tự tham số khác nhau là các overload. Việc viết thêm overload không thực hiện nghĩa vụ triển khai phương thức abstract đã có. Hãy gắn `@Override` và sửa lỗi compiler thay vì bỏ annotation.

**Nhầm `throws` là lời hứa luôn ném lỗi.** `throws IOException` cho phép tình huống lỗi checked tương ứng được truyền ra ngoài; nó không bắt buộc mỗi lần chạy phải ném ngoại lệ, và không yêu cầu mọi lớp triển khai đều ghi lại cùng mệnh đề `throws`.

**Nhầm kiểu trả về là một phần chữ ký overload.** Không thể giải quyết hai hành vi bằng hai phương thức chỉ khác `String`/ `Object` ở giá trị trả về. Nếu cần hai phép toán khác nhau, đổi tên hoặc danh sách tham số theo một thiết kế rõ ràng.

**Làm hẹp quyền truy cập của interface method.** Một khai báo `String read(String id);` trong interface mặc nhiên là `public abstract`. Lớp hiện thực phải khai báo `public String read(String id)`, không được dùng package-private hoặc `protected`.

**Bỏ quên kiểu tĩnh của người gọi.** Dù một lớp concrete bỏ `throws`, lời gọi qua biến kiểu cha vẫn được kiểm tra theo khai báo ở cha. Khi thiết kế API, nên đưa những checked exceptions có ý nghĩa vào hợp đồng chung ngay từ đầu.

## 8. Tự kiểm tra

1. Một phương thức `abstract Number evaluate(String text) throws IOException;` có thể được override bằng `Integer evaluate(String input)` không? **Có** (giả sử quyền truy cập hợp lệ): `Integer` là kiểu trả về covariant, tên tham số không quan trọng và có thể bỏ `throws`.
2. Có thể đổi tham số thành `Object input` rồi dùng `@Override` không? **Không**, vì đây không còn là cùng phương thức theo signature thông thường; nếu lớp con concrete chưa triển khai `evaluate(String)`, nó sẽ lỗi biên dịch.
3. Có thể đổi `throws IOException` thành `throws Exception` không? **Không**, vì checked exception ở override rộng hơn hợp đồng gốc.
4. Có cần bắt `IOException` nếu gọi qua tham chiếu kiểu cha có khai báo `throws IOException` không? **Có**, hoặc tiếp tục khai báo `throws` ở phương thức gọi, bất kể triển khai cụ thể có thực sự ném lỗi hay không.

Khi đọc một khai báo abstract, hãy xác định riêng **đầu vào**, **kết quả** và **ngoại lệ checked**; khi triển khai, kiểm tra chúng cùng quyền truy cập bằng `@Override`. Đó là cách giữ hợp đồng polymorphism nhất quán giữa người gọi và mọi lớp con.
