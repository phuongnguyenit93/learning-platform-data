# Vì sao `throws` không có nghĩa phương thức luôn phát sinh lỗi trong Java

Một phương thức Java có thể khai báo `throws IOException` nhưng chạy thành công hàng nghìn lần mà **không ném một ngoại lệ `IOException` nào**. Từ khóa `throws` mô tả **khả năng ngoại lệ truyền ra khỏi phương thức theo hợp đồng kiểu**; nó không phải câu lệnh ném lỗi, không khiến JVM tự tạo ngoại lệ, và không bảo đảm rằng điều kiện gây lỗi sẽ xảy ra.

Ví dụ:

~~~java
static String readSetting(boolean sourceAvailable)
        throws java.io.IOException {
    if (!sourceAvailable) {
        throw new java.io.IOException("Không có nguồn cấu hình");
    }
    return "READY";
}
~~~

Đây là **phương thức minh họa**, cần đặt trong một lớp Java. Khi gọi `readSetting(true)`, nhánh `throw` không chạy và phương thức trả `"READY"` bình thường. Khi gọi `readSetting(false)`, phương thức tạo rồi ném `IOException`. Cả hai khả năng đều phù hợp với cùng một chữ ký `throws IOException`.

## 1. Phân biệt rõ `throws` và `throw`

`throws IOException` là **khai báo khả năng** của phương thức/constructor, còn `throw new IOException("failed");` là **hành động ném** nếu luồng chạy đi tới câu lệnh. Một `try/catch` ở caller chỉ xử lý ngoại lệ **thật sự truyền tới handler**; nó không tự tạo thất bại.

Vì vậy, một phương thức có thể khai báo `throws IOException` dù thân hiện tại chỉ `return`, hoặc có nhánh `throw` nhưng không đi qua nhánh ấy trong một lần gọi cụ thể. Đây là mấu chốt của bài: **khả năng theo chữ ký không đồng nghĩa xác suất hoặc bảo đảm thất bại**. Các ví dụ tiếp theo kiểm tra trực tiếp sự khác biệt bằng nhiều đường chạy.

## 2. Cơ chế: khả năng theo hợp đồng và sự kiện khi chạy

Trình biên dịch xem **chữ ký phương thức** và các biểu thức có khả năng ném ngoại lệ để kiểm tra quy tắc *checked exceptions*. JVM lúc chạy mới thực thi những nhánh lệnh thực sự được chọn.

Đối với phương thức:

~~~java
static String load(boolean available)
        throws java.io.IOException {
    if (!available) {
        throw new java.io.IOException("Nguồn không khả dụng");
    }
    return "Dữ liệu";
}
~~~

Luồng điều khiển có hai đường:

~~~text
                     Gọi load(available)
                               |
                     available == true?
                        /             \
                      Có              Không
                       |                 |
                 return "Dữ liệu"    throw IOException
                       |                 |
                Kết thúc bình thường   Kết thúc bất thường
                       |                 |
                  Caller nhận String  Tìm catch phù hợp
~~~

Khai báo `throws IOException` vẫn giống nhau trên cả hai đường. Nó tồn tại **trước khi có giá trị thực tế của tham số**. Để đánh giá kết quả một lần gọi cụ thể, cần biết giá trị đầu vào, trạng thái tài nguyên, nhánh điều kiện, các lời gọi bên dưới và môi trường thực thi.

Lưu ý: Java không dựa vào `throws` để bảo đảm rằng phương thức *chắc chắn* thực hiện lệnh `throw`. Kể cả khi phần thân hiện tại không có đường ném checked exception, khai báo `throws` vẫn có thể hợp lệ; nó có thể thể hiện hợp đồng API hoặc để ngỏ khả năng triển khai khác.

## 3. Ví dụ Java 17+ độc lập: cùng `throws`, có lần thành công và có lần thất bại

Tạo tệp **`ThrowsPossibilityDemo.java`**:

~~~java
import java.io.IOException;

public class ThrowsPossibilityDemo {
    interface Provider {
        String load() throws IOException;
    }

    static class ConstantProvider implements Provider {
        @Override
        public String load() {
            return "constant";
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("Declared only: " + declaredOnly());
        } catch (IOException e) {
            System.out.println("Declared only failed");
        }

        for (boolean available : new boolean[] {true, false}) {
            try {
                System.out.println(
                        "Available: " + readSetting(available));
            } catch (IOException e) {
                System.out.println("Failure: " + e.getMessage());
            }
        }

        Provider provider = new ConstantProvider();
        try {
            System.out.println("Provider: " + provider.load());
        } catch (IOException e) {
            System.out.println("Provider failed");
        }

        System.out.println("Handled locally: " + loadOrDefault(false));

        try {
            System.out.println("Forwarded: " + forward(true));
        } catch (IOException e) {
            System.out.println("Forwarded failed");
        }

        System.out.println("Unchecked: " + requireText("ok"));
    }

    static String declaredOnly() throws IOException {
        return "constant";
    }

    static String readSetting(boolean available) throws IOException {
        if (!available) {
            throw new IOException("setting unavailable");
        }
        return "ready";
    }

    static String loadOrDefault(boolean available) {
        try {
            return readSetting(available);
        } catch (IOException e) {
            return "default";
        }
    }

    static String forward(boolean available) throws IOException {
        return readSetting(available);
    }

    static String requireText(String value) {
        if (value == null) {
            throw new IllegalArgumentException("value must not be null");
        }
        return value;
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac ThrowsPossibilityDemo.java
java ThrowsPossibilityDemo
~~~

**Stdout chính xác:**

~~~text
Declared only: constant
Available: ready
Failure: setting unavailable
Provider: constant
Handled locally: default
Forwarded: ready
Unchecked: ok
~~~

### Giải thích theo từng tình huống

**1. Chỉ khai báo, không ném trong thân hàm.** `declaredOnly()` có chữ ký `throws IOException` nhưng chỉ trả chuỗi. Caller phải viết mã hợp lệ với hợp đồng checked exception; trong lần chạy này khối `catch` không hoạt động.

**2. Cùng một phương thức, hai kết quả.** `readSetting(true)` trả `"ready"` và không có ngoại lệ. `readSetting(false)` đi vào nhánh `throw new IOException(...)`. Vì vậy cùng chữ ký `throws IOException` không chỉ ra rằng mọi lần gọi đều thất bại.

**3. Chữ ký interface rộng hơn triển khai cụ thể.** `Provider.load()` cho phép ném `IOException`. `ConstantProvider.load()` ghi đè phương thức mà không khai báo ngoại lệ checked nào. Gọi qua biến kiểu `Provider` vẫn được trình biên dịch đánh giá theo chữ ký `Provider.load()`; đó là lý do khối `try/catch` ở `main` có ý nghĩa dù triển khai đang dùng luôn trả chuỗi.

**4. Phương thức xử lý lỗi bên trong.** `loadOrDefault(false)` gọi phương thức có thể ném `IOException` nhưng tự bắt và trả `"default"`. Bên gọi `loadOrDefault` không phải xử lý `IOException` theo chữ ký của phương thức này, vì ngoại lệ đó không thoát ra trong đường thực thi được thiết kế.

**5. Phương thức trung gian chuyển tiếp.** `forward(true)` khai báo `throws IOException` do gọi `readSetting(...)` mà không bắt. Khi `available` là `true`, phương thức vẫn thành công: quyền *cho phép lan truyền* không phải nghĩa vụ *phải ném*.

**6. Unchecked exception có thể ném mà không khai báo.** `requireText(...)` không có `throws` nhưng vẫn có thể ném `IllegalArgumentException` khi đầu vào là `null`. Đây là ví dụ đối xứng: sự xuất hiện hoặc vắng mặt của `throws` không đủ để khẳng định phương thức sẽ chạy thành công hay thất bại trong mọi trường hợp.

## 4. Tại sao compiler buộc xử lý khi lần gọi thực tế có thể thành công?

Với checked exception, người gọi thường phải **bắt hoặc khai báo** ngoại lệ có thể truyền ra theo hợp đồng phương thức.

Ví dụ:

~~~java
static void caller() throws java.io.IOException {
    String value = readSetting(true);
    System.out.println(value);
}
~~~

Đây là phương thức minh họa trong cùng lớp với `readSetting`. Lời gọi sử dụng giá trị literal `true`, nhưng phương thức được khai báo `throws IOException` nên `caller()` vẫn phải thỏa nghĩa vụ checked exception. Trình biên dịch không biến việc “đầu vào hiện tại có vẻ an toàn” thành cam kết rằng checked exception không thể truyền ra.

Nếu bỏ `throws IOException` trong chữ ký `caller()` mà cũng không có `try/catch`, trình biên dịch báo lỗi vì `IOException` chưa được bắt hoặc khai báo.

Cách xử lý tại caller:

~~~java
static void callerHandled() {
    try {
        String value = readSetting(true);
        System.out.println(value);
    } catch (java.io.IOException e) {
        System.out.println("Không đọc được: " + e.getMessage());
    }
}
~~~

Ở lần gọi với `true`, nhánh `catch` không chạy. Nhưng **mã nguồn vẫn có trách nhiệm cho tình huống lỗi mà hợp đồng cho phép**.

Đối với mã thật, khả năng ném ngoại lệ có thể thay đổi theo hệ thống tệp, mạng, quyền truy cập, trạng thái thread hoặc việc triển khai API. Vì vậy compiler không thể coi một lần thử nghiệm thành công là bằng chứng hợp đồng không bao giờ thất bại.

## 5. Khai báo `throws` không bắt buộc có `throw` trực tiếp

Một phương thức có thể khai báo `throws IOException` dù trong thân không hề viết `throw new IOException(...)`:

~~~java
static String readUtf8(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

Phương thức này sử dụng `Files.readString`, một API có thể ném `IOException`. Nếu thao tác đọc thành công, `readUtf8` trả kết quả. Nếu API ném `IOException`, ngoại lệ đi qua `readUtf8` vì không có xử lý bên trong.

Vì thế cần phân biệt hai nguồn có thể làm ngoại lệ đi ra khỏi phương thức:

1. **Ném trực tiếp:** thân phương thức thực thi `throw new IOException(...)`.
2. **Lan truyền từ lời gọi bên dưới:** phương thức gọi API khác, API đó ném ngoại lệ và tầng hiện tại không bắt.

Trong cả hai tình huống, `throws IOException` khai báo khả năng truyền ra ngoài, không khẳng định nhánh lỗi sẽ xảy ra.

Nếu người viết bắt và xử lý trọn vẹn mọi `IOException` có thể phát sinh trong thân hàm rồi trả kết quả bình thường, khai báo `throws IOException` có thể không còn cần thiết về mặt biên dịch. Tuy nhiên việc giữ hoặc bỏ nó có thể liên quan đến **hợp đồng công khai** của API và khả năng tương thích với các bên gọi.

## 6. `throws` còn thể hiện hợp đồng ở interface và lớp trừu tượng

Hãy xem khai báo:

~~~java
interface DataSource {
    String fetch() throws java.io.IOException;
}
~~~

Đây là interface minh họa. Nó không chứa phần thân triển khai nên không có lệnh ném nào để quan sát. Nó cho phép các triển khai gặp lỗi I/O theo hợp đồng.

Một triển khai đơn giản có thể luôn thành công:

~~~java
final class MemoryDataSource implements DataSource {
    @Override
    public String fetch() {
        return "cached";
    }
}
~~~

Một triển khai khác có thể cần tài nguyên bên ngoài:

~~~java
final class FileDataSource implements DataSource {
    private final java.nio.file.Path path;

    FileDataSource(java.nio.file.Path path) {
        this.path = path;
    }

    @Override
    public String fetch() throws java.io.IOException {
        return java.nio.file.Files.readString(path);
    }
}
~~~

Đây là các đoạn kiểu Java 17 có thể đặt cùng một tệp với interface trong ngữ cảnh phù hợp. `MemoryDataSource` không cần khai báo `throws IOException` vì bản triển khai không làm phát sinh lỗi đó; `FileDataSource` có thể khai báo và ném khi thao tác đọc thất bại.

Nếu mã gọi thông qua tham chiếu kiểu `DataSource`, trình biên dịch dựa vào chữ ký `DataSource.fetch()` để buộc xử lý hoặc khai báo `IOException`. Lời gọi runtime có thể được điều phối tới bất kỳ implementation hợp lệ nào.

Khi ghi đè phương thức, lớp con **không được mở rộng checked exceptions** vượt quá các loại mà hợp đồng phương thức cha cho phép. Việc không khai báo checked exception, hoặc thu hẹp loại ngoại lệ checked, thường hợp lệ. Quy tắc này giúp caller dùng kiểu cha mà không phải thay đổi hợp đồng checked khi chọn một implementation khác.

## 7. `throws` cũng không liệt kê mọi ngoại lệ runtime có thể xảy ra

Khai báo:

~~~java
static int parse(String text) {
    return Integer.parseInt(text);
}
~~~

không có `throws`, nhưng `parse("abc")` có thể ném `NumberFormatException`, một lớp con của `RuntimeException`. Unchecked exceptions không bắt buộc được liệt kê trong mệnh đề `throws`.

Tương tự, phương thức có `throws IOException` **vẫn có thể** ném `IllegalArgumentException`, `NullPointerException` hoặc lỗi unchecked khác trên đường thực thi. Mệnh đề `throws IOException` không có nghĩa “chỉ có đúng một kiểu lỗi là `IOException`”, cũng không phải một cơ chế bảo đảm an toàn tuyệt đối.

Các ngoại lệ checked thường là những loại mà Java bắt người gọi phải cân nhắc theo hợp đồng kiểu; các ngoại lệ unchecked có thể được nêu trong JavaDoc hoặc trong `throws` để giúp đọc API, nhưng điều đó không biến chúng thành checked.

Ví dụ khai báo hợp lệ:

~~~java
static int positive(String value)
        throws IllegalArgumentException {
    int result = Integer.parseInt(value);
    if (result <= 0) {
        throw new IllegalArgumentException("Giá trị phải dương");
    }
    return result;
}
~~~

Chữ ký trên chứa `throws IllegalArgumentException`, nhưng caller **không bắt buộc** viết `try/catch` vì `IllegalArgumentException` là unchecked. Dù vậy nó vẫn có thể bị ném khi đầu vào sai; `throws` ở đây đóng vai trò tài liệu hợp đồng hơn là áp đặt nghĩa vụ biên dịch.

## 8. Không phải lúc nào phương thức không khai báo `throws` cũng an toàn

Đặt cạnh nhau:

| Khai báo | Điều có thể xảy ra khi chạy | Nghĩa vụ compile-time thông thường |
| --- | --- | --- |
| `String fetch() throws IOException` | Có thể trả chuỗi hoặc ném `IOException` | Caller phải bắt/khai báo `IOException` |
| `String constant() throws IOException` | Trong triển khai đang xét, chỉ trả chuỗi | Caller vẫn xử lý theo chữ ký checked |
| `String safeFetch()` có `catch IOException` bên trong | Có thể dùng fallback và trả chuỗi; tùy logic còn có thể ném lỗi unchecked | Caller không bị buộc bởi `IOException` nếu nó không thoát ra trong hợp đồng |
| `int parse(String s)` không khai báo `throws` | Có thể trả số hoặc ném `NumberFormatException` | Không bắt buộc bắt unchecked exception |
| `void fail()` luôn `throw new IllegalStateException(...)` | Mỗi lần đi tới `throw` thì kết thúc bất thường | Không cần `throws` vì unchecked |

Từ đó rút ra:

- **Có `throws` không suy ra luôn thất bại.**
- **Không có `throws` không suy ra luôn thành công.**
- **Bắt một checked exception không có nghĩa thao tác ban đầu luôn được hoàn thành:** đôi khi chỉ dừng lỗi có kiểm soát hoặc trả fallback.
- **Không được dùng chỉ riêng chữ ký `throws` để tính tỉ lệ lỗi:** muốn biết tỉ lệ, cần dữ liệu vận hành hoặc phân tích điều kiện thất bại.

## 9. `throws` và quan hệ với `return`

Một phương thức khai báo trả về `String` hoặc `int` vẫn có thể ném ngoại lệ. Những đường thực thi **hoàn tất bình thường** phải trả giá trị theo quy tắc kiểu của phương thức; đường `throw` kết thúc bất thường nên không cần tạo giá trị.

~~~java
static int compute(boolean valid)
        throws java.io.IOException {
    if (!valid) {
        throw new java.io.IOException("Không thể tính");
    }
    return 42;
}
~~~

Đây là phương thức minh họa. Với `compute(true)`, caller nhận `42`; với `compute(false)`, caller không nhận một giá trị `int` nào từ lần gọi đó. JVM chuyển điều khiển sang cơ chế tìm handler.

Mệnh đề `throws IOException` **không thay `return`** và không tự “bật” một nhánh lỗi. Nếu mã chỉ có:

~~~java
static int invalid() throws java.io.IOException {
    System.out.println("Chạy");
}
~~~

thì phương thức **không biên dịch** vì có thể kết thúc bình thường mà không trả `int`. Việc thêm `throws IOException` không sửa được lỗi thiếu giá trị trả về. Đường `throw` thực sự mới là đường kết thúc bất thường.

Ngược lại, phương thức sau biên dịch hợp lệ:

~~~java
static int alwaysFail() throws java.io.IOException {
    throw new java.io.IOException("Không có kết quả");
}
~~~

Phương thức chỉ gồm một đường `throw`, nên không có đường nào hoàn tất bình thường để phải trả `int`. Tuy nhiên **điều khiến phương thức luôn ném ở đây là thân hàm**, không phải riêng mệnh đề `throws`. Đừng dùng ví dụ này để suy ra mọi phương thức có `throws` đều hành xử như vậy.

## 10. Caller nên sử dụng `throws` thế nào?

Khi đọc API:

~~~java
public String loadConfiguration() throws java.io.IOException
~~~

hãy hiểu: “Kết quả thông thường là một `String`, nhưng trong những điều kiện được thiết kế hoặc thực thi cho phép, lỗi I/O có thể lan ra. Bên gọi cần có quyết định theo hợp đồng checked exception.”

Caller có hai cách cơ bản.

### Bắt ở tầng biết cách xử lý

~~~java
static String loadOrFallback(java.nio.file.Path path) {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException e) {
        return "default";
    }
}
~~~

Đây là một phương thức minh họa. `catch` chỉ chạy khi việc đọc thất bại bằng `IOException`. Nó **không** chạy khi đọc thành công. Trả chuỗi `"default"` chỉ hợp lệ nếu cấu hình mặc định được phép theo hợp đồng; không nên dùng fallback để che lỗi của một tệp bắt buộc.

### Chuyển tiếp để tầng trên quyết định

~~~java
static String loadRequired(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

Ở cách này, tầng hiện tại không có thông tin để chọn fallback. Caller bên ngoài có thể quyết định cho người dùng chọn tệp khác, dừng khởi tạo hoặc báo lỗi. Nếu đọc thành công, không có ngoại lệ để chuyển tiếp.

### Khi nào cần khai báo loại cụ thể?

Ưu tiên `throws IOException` nếu thất bại được mô tả chính xác bằng `IOException`. Khai báo quá rộng như `throws Exception` có thể khiến bên gọi phải xử lý nhóm lỗi không cần thiết và làm hợp đồng khó hiểu. Dù vậy các API kế thừa hoặc một số ranh giới framework có thể đã có chữ ký rộng; cần tôn trọng hợp đồng sẵn có.

## 11. Các hiểu lầm thường gặp

### “Có `throws` thì chắc chắn phương thức ném ngoại lệ”

Sai. `throws` khai báo **khả năng**, không thực hiện lệnh ném. Phương thức có thể trả kết quả bình thường vì điều kiện gây lỗi không xảy ra.

### “Có `throws IOException` nghĩa là phương thức phải chứa `throw new IOException`”

Sai. Ngoại lệ có thể phát sinh từ một lời gọi bên dưới và lan truyền. Thậm chí một phương thức chỉ trả hằng số vẫn được phép giữ khai báo `throws IOException`.

### “Caller có `catch` nghĩa là catch sẽ luôn chạy”

Sai. `catch` chỉ được thực thi khi có ngoại lệ phù hợp thực sự truyền đến vùng xử lý đó. Khi `try` hoàn tất bình thường, nhánh `catch` được bỏ qua.

### “Đã có `throws` thì compiler tự bắt lỗi giúp mình”

Sai. `throws` không xử lý lỗi, chỉ chuyển nghĩa vụ checked cho caller (hoặc khai báo khả năng truyền từ phương thức). Khi runtime phát sinh ngoại lệ mà không có handler phù hợp, ngoại lệ vẫn truyền ra khỏi luồng gọi hiện tại.

### “Không có `throws` thì không có ngoại lệ”

Sai. Unchecked exceptions như `IllegalArgumentException`, `NumberFormatException` hoặc `NullPointerException` có thể được ném mà không cần khai báo.

### “Khai báo `throws IOException` nghĩa là xác suất lỗi cao”

Sai. Chữ ký không mã hóa tần suất, độ nghiêm trọng hay khả năng phục hồi. Một API đọc dữ liệu ổn định có thể hầu như luôn thành công, trong khi API khác gặp lỗi rất thường xuyên; cả hai có thể có cùng chữ ký.

### “Lời gọi với tham số an toàn không cần quan tâm checked exception”

Không thể suy ra như vậy chỉ từ một tham số. Trình biên dịch theo hợp đồng của lời gọi và quy tắc ngôn ngữ; nó không thử chạy hoặc chứng minh mọi điều kiện môi trường đều an toàn để tự loại bỏ nghĩa vụ checked.

### “Triển khai nào của interface cũng phải có `throws` y hệt”

Không. Ghi đè một phương thức cho phép checked exception thường có thể bỏ khai báo hoặc thu hẹp ngoại lệ checked. Tuy nhiên nếu caller dùng biến có **kiểu interface**, compiler vẫn dựa vào chữ ký interface.

### “`throws` trả về một đối tượng Exception”

Sai. `throws` là phần của khai báo phương thức, không phải một phần của danh sách tham số hay kiểu giá trị trả về. Giá trị trả về thuộc `return` khi phương thức thành công; đối tượng ngoại lệ do `throw` hoặc lời gọi bên dưới ném khi có lỗi.

### “`throws Exception` là cách chuẩn cho mọi phương thức”

Không. Khai báo rộng khiến người gọi khó biết loại thất bại cần xử lý. Hãy chọn loại cụ thể khi có thể, theo hợp đồng API và kiến trúc chương trình.

## 12. Thực hành: dự đoán kết quả và xác minh bằng Java

Xét phương thức:

~~~java
static String choose(int code)
        throws java.io.IOException {
    if (code == 1) {
        return "ok";
    }
    if (code == 2) {
        throw new java.io.IOException("bad input source");
    }
    return "fallback";
}
~~~

Đây là đoạn phương thức minh họa.

| Lời gọi | Kết quả |
| --- | --- |
| `choose(1)` | Trả `"ok"` |
| `choose(2)` | Ném `IOException("bad input source")` |
| `choose(3)` | Trả `"fallback"` |

Chữ ký `throws IOException` không đổi giữa ba lời gọi. Việc chọn đường xử lý do giá trị `code` quyết định.

### Câu hỏi tự kiểm tra

1. Nếu phương thức `static String name() throws IOException { return "A"; }` không có `throw`, nó có hợp lệ không? Caller phải làm gì khi gọi qua chữ ký đó?
2. Nếu gọi `readSetting(true)` thành công, nhánh `catch (IOException e)` có chạy không?
3. Một phương thức không viết `throw` nhưng gọi `Files.readString` có thể để `IOException` truyền ra ngoài không?
4. Vì sao `MemoryDataSource.fetch()` có thể bỏ `throws IOException` trong khi interface `DataSource.fetch()` có khai báo đó?
5. `static int value() throws IOException { System.out.println("x"); }` có biên dịch không? Vì sao?
6. Một phương thức `throws IOException` có thể ném `IllegalArgumentException` dù không liệt kê nó trong chữ ký không?
7. Trường hợp nào cho thấy một phương thức **luôn ném lỗi**? Bạn cần xem mỗi chữ ký `throws`, hay phải xem các đường thực thi của phần thân?
8. Khi nào nên bắt `IOException` ở tầng hiện tại, và khi nào nên cho phép lan truyền bằng `throws`?
9. Có thể ước lượng xác suất lỗi từ mệnh đề `throws` không?
10. Tại sao việc kiểm thử một lần thành công không chứng minh phương thức không bao giờ ném ngoại lệ?
11. Caller đang có biến kiểu `Provider`. Dù đối tượng runtime là `ConstantProvider`, vì sao lời gọi `provider.load()` vẫn phải tuân thủ `throws IOException`?
12. Nếu phương thức nội bộ bắt hoàn toàn `IOException` và trả một giá trị fallback hợp lệ, caller của phương thức đó có bắt buộc xử lý `IOException` nữa không?

### Đáp án gợi ý

1. Có; caller tuân thủ nghĩa vụ checked exception theo chữ ký, chẳng hạn bắt hoặc khai báo.
2. Không, vì không có ngoại lệ phù hợp truyền tới `catch`.
3. Có, vì ngoại lệ có thể lan truyền từ lời gọi bên dưới.
4. Ghi đè được phép thu hẹp hoặc loại bỏ checked exceptions; caller dùng kiểu interface vẫn dựa vào hợp đồng interface.
5. Không; phương thức có đường hoàn tất bình thường mà không trả `int`, `throws` không thay `return`.
6. Có, `IllegalArgumentException` là unchecked.
7. Phải phân tích luồng điều khiển thực tế; chỉ `throws` không đủ kết luận.
8. Bắt khi tầng đó biết cách xử lý đúng; chuyển tiếp khi tầng trên có trách nhiệm quyết định.
9. Không, mệnh đề chỉ nêu khả năng loại ngoại lệ, không có số liệu xác suất.
10. Lần thử nghiệm chỉ bao phủ một trạng thái và đường thực thi.
11. Compiler nhìn chữ ký `Provider.load()` có `throws IOException`.
12. Nếu phương thức không khai báo `throws IOException` và đã xử lý checked exception bên trong thì caller không bắt buộc xử lý lỗi đó theo hợp đồng.

## 13. Ghi nhớ

**`throws` là thông tin về khả năng ngoại lệ thoát khỏi một phương thức, không phải một hành động phát sinh lỗi và cũng không phải cam kết rằng lỗi chắc chắn xảy ra.** Có thể gọi cùng một phương thức rồi nhận kết quả bình thường hoặc gặp ngoại lệ tùy đầu vào và điều kiện thực thi. Hiểu đúng `throws` giúp đọc hợp đồng API, thiết kế xử lý checked exceptions và dự đoán luồng thực thi mà không nhầm giữa *khả năng thất bại* với *một lần thất bại thực sự*.