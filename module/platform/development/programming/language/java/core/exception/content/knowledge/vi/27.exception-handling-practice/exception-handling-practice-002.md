# So sánh xử lý ngoại lệ tại chỗ với lan truyền bằng `throws` trong Java

Trong Java, khi một phương thức gặp lỗi, người viết chương trình thường có hai hướng chính: **bắt và xử lý ngoại lệ ngay tại chỗ** bằng `try`–`catch`, hoặc **để ngoại lệ lan truyền tới tầng gọi** và, với checked exception, khai báo khả năng đó bằng `throws`. Hai cách đều hợp lệ trong ngữ cảnh thích hợp nhưng mang trách nhiệm khác nhau. Chọn sai có thể làm mất thông tin chẩn đoán, che một thất bại thành “thành công”, ép tầng thấp biết về chính sách nghiệp vụ của tầng cao, hoặc khiến tài nguyên không được dọn đúng.

Câu hỏi quan trọng nhất không phải “có viết được `catch` ở đây không?” mà là:

> **Tầng hiện tại có đủ thông tin và quyền quyết định để xử lý lỗi một cách đúng đắn không?**

Nếu có một chiến lược phục hồi được hợp đồng cho phép và trạng thái vẫn hợp lệ, xử lý tại chỗ có thể phù hợp. Nếu chưa, nên **chuyển trách nhiệm** bằng cách để ngoại lệ đi lên hoặc chuyển đổi nó thành một ngoại lệ thích hợp hơn nhưng **giữ `cause`**. `throws` không phải cơ chế “sửa lỗi”; nó là một phần hợp đồng phương thức đối với các ngoại lệ checked có thể thoát ra.

## 1. Hai hướng giải quyết và sơ đồ luồng điều khiển

### Xử lý tại chỗ

Một phương thức bắt ngoại lệ và tự thực hiện chính sách xử lý:

```java
String displayName(String raw) {
    try {
        return normalizeName(raw);
    } catch (InvalidNameException exception) {
        return "Unknown"; // Chỉ đúng nếu fallback này được hợp đồng cho phép.
    }
}
```

Đây là **mã minh họa chưa độc lập**, cần định nghĩa `normalizeName(...)` và `InvalidNameException`. Khi `catch` kết thúc bình thường và trả fallback, phương thức không còn chuyển ngoại lệ vừa bắt tới người gọi. Điều này hữu ích khi `Unknown` thật sự là một kết quả hợp lệ, nhưng nguy hiểm nếu ứng dụng đang xử lý thanh toán, xác thực hoặc cập nhật dữ liệu bắt buộc phải thành công.

### Lan truyền cho tầng gọi

Phương thức để ngoại lệ checked đi ra và công bố trong chữ ký:

```java
String loadConfiguration() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.properties"));
}
```

Đây là **đoạn phương thức minh họa**, cần đặt trong một lớp Java. Nó không quyết định có dùng cấu hình mặc định, thử nguồn khác, thông báo người dùng hay hủy khởi động. Lựa chọn đó thuộc tầng gọi có đủ ngữ cảnh.

```text
Tầng thấp: load()
       |
       +-- đọc thành công -----------------> trả dữ liệu
       |
       +-- IOException
                |
                +-- A: catch tại đây
                |        |
                |        +-- phục hồi hợp lệ --> trả kết quả bình thường
                |        +-- không phục hồi --> ném lại / chuyển lỗi
                |
                +-- B: throws IOException
                         |
                         v
                   Tầng gọi quyết định
                         |
                  +------+------+
                  |             |
                 catch        throws tiếp
                  |             |
              xử lý tại      tầng cao hơn
              ranh giới
```

Một lời gọi có thể có nhiều tầng `throws` liên tiếp. Ngoại lệ chỉ dừng lan truyền khi có handler thực sự xử lý nó, hoặc khi nó đến ranh giới thực thi thích hợp mà không có handler. Đừng giả định `throws` tạo một `catch` ngầm.

## 2. Bảng so sánh nhanh

| Tiêu chí | `try`–`catch` xử lý tại chỗ | Lan truyền bằng `throws` |
| --- | --- | --- |
| Trách nhiệm chính | Xác định và thực hiện chính sách xử lý tại tầng hiện tại | Chuyển trách nhiệm xử lý cho người gọi |
| Ngoại lệ có ra khỏi phương thức? | Không, **nếu** được xử lý xong và không ném lại | Có thể, nếu đường thực thi phát sinh ngoại lệ đó |
| Ảnh hưởng chữ ký | Không nhất thiết phải khai báo ngoại lệ đã được xử lý hoàn toàn | Checked exception thoát ra thường phải có trong `throws` hoặc kiểu cha phù hợp |
| Cần có fallback/retry? | Chỉ khi đó là chính sách thực sự hợp lệ | Không cần tự quyết định fallback ở tầng thấp |
| Bảo toàn stack/cause | Phải cẩn thận khi log, bọc hoặc ném lại | Ngoại lệ gốc tiếp tục lan lên nếu không thay bằng wrapper |
| Tái sử dụng tầng thấp | Có thể kém nếu tầng thấp tự áp chính sách của UI/API | Thường tốt hơn khi tầng cao quyết định theo bối cảnh |
| Phù hợp với | Lỗi có thể phục hồi ngay, validation tại boundary, cleanup cục bộ | I/O, lỗi tầng hạ tầng hoặc trường hợp tầng hiện tại không đủ quyền xử lý |
| Rủi ro nổi bật | Nuốt lỗi, trả thành công giả, trạng thái thay đổi dở dang | Lộ ngoại lệ tầng thấp ra API không phù hợp hoặc bỏ quên nơi xử lý cuối |

Hai cách **không loại trừ nhau**. Một phương thức có thể bắt ngoại lệ tầng thấp rồi ném **ngoại lệ mới phù hợp với tầng trừu tượng**; hoặc bắt một loại lỗi có thể phục hồi nhưng để loại khác lan lên. Thiết kế tốt thường kết hợp chúng qua các ranh giới rõ ràng.

## 3. `throw` khác `throws` thế nào?

Dễ nhầm lẫn vì tên gần giống nhau:

```java
void read() throws java.io.IOException {
    throw new java.io.IOException("read failed");
}
```

Đây là **phương thức Java minh họa** đặt trong lớp. Trong đoạn này:

- `throw expression;` là **câu lệnh thực thi**, làm luồng điều khiển rời nhánh thông thường bằng một đối tượng `Throwable`.
- `throws IOException` là **mệnh đề trong chữ ký** khai báo checked exception có thể thoát ra khỏi phương thức.
- Viết `throws` không tự tạo hoặc ném lỗi. Phương thức khai báo `throws IOException` vẫn có thể trả kết quả bình thường.
- Viết `throw new IOException(...)` bên trong phương thức thường đòi hỏi bắt lại lỗi, hoặc khai báo `throws IOException` (hoặc kiểu cha được phép) vì `IOException` là checked exception.
- Đối với unchecked exceptions như `IllegalArgumentException`, `IllegalStateException` hay `NullPointerException`, Java **không yêu cầu** khai báo `throws`, mặc dù có thể khai báo để cung cấp thông tin.

`throws` cũng không phải câu lệnh yêu cầu JVM “bỏ qua lỗi”. Ngoại lệ vẫn có thể lan ngược qua các lời gọi, chạy `finally` theo quy tắc Java, rồi tới handler gần nhất tương ứng.

## 4. Checked và unchecked exception: tác động tới cách chọn

### Checked exception

Các lớp kế thừa `Exception` nhưng không kế thừa `RuntimeException` thường là **checked exception**, ví dụ `IOException`, `SQLException`, `InterruptedException`. Trình biên dịch kiểm tra rằng chúng được **bắt** hoặc **khai báo/lan truyền** phù hợp.

```java
void load() throws java.io.IOException {
    readFromDisk();
}
```

Đây là mã minh họa, `readFromDisk()` phải là phương thức được khai báo trong ứng dụng. Nếu không có `try`–`catch` xử lý `IOException`, chữ ký `throws` báo cho người gọi biết rủi ro đó.

### Unchecked exception

`RuntimeException` và các lớp con là ngoại lệ unchecked. Những lỗi này có thể lan lên mà **không cần `throws`** trong chữ ký:

```java
int parsePositive(String input) {
    int value = Integer.parseInt(input);
    if (value <= 0) {
        throw new IllegalArgumentException("value must be positive");
    }
    return value;
}
```

Đây là phương thức minh họa đặt trong lớp. Cả `NumberFormatException` (từ `parseInt`) và `IllegalArgumentException` đều unchecked. Tác giả không bị trình biên dịch buộc thêm `throws`, nhưng người gọi vẫn có thể bắt chúng khi có chính sách xử lý phù hợp.

**Không đồng nhất checked với “phục hồi được” và unchecked với “không được bắt”.** Việc chọn nơi xử lý phụ thuộc **hợp đồng, khả năng khôi phục trạng thái và chính sách nghiệp vụ**, chứ không chỉ loại ngôn ngữ. Chẳng hạn, `NumberFormatException` có thể là lỗi nhập liệu dự kiến tại ranh giới UI; còn `IOException` có thể là sự cố không thể phục hồi tại một tiến trình và phải kết thúc yêu cầu.

## 5. Ví dụ Java 17+: cùng lỗi, ba cách phân chia trách nhiệm

Tạo tệp **`LocalVsThrowsDemo.java`**:

```java
import java.io.IOException;

public class LocalVsThrowsDemo {
    static String fetch(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("storage unavailable");
        }
        return "REAL_DATA";
    }

    static String handleLocally(boolean fail) {
        try {
            return fetch(fail);
        } catch (IOException exception) {
            return "CACHED_DATA"; // Giả định fallback hợp lệ cho màn hình.
        }
    }

    static String propagate(boolean fail) throws IOException {
        return fetch(fail);
    }

    static String translate(boolean fail) {
        try {
            return fetch(fail);
        } catch (IOException original) {
            throw new IllegalStateException("cannot assemble report", original);
        }
    }

    static String handleAtBoundary(boolean fail) {
        try {
            return propagate(fail);
        } catch (IOException exception) {
            return "REQUEST_FAILED:" + exception.getMessage();
        }
    }

    public static void main(String[] args) {
        System.out.println("localSuccess=" + handleLocally(false));
        System.out.println("localFallback=" + handleLocally(true));
        System.out.println("propagateSuccess=" + handleAtBoundary(false));
        System.out.println("boundaryFailure=" + handleAtBoundary(true));

        try {
            translate(true);
        } catch (IllegalStateException exception) {
            System.out.println("wrapper="
                    + exception.getClass().getSimpleName());
            System.out.println("cause="
                    + exception.getCause().getClass().getSimpleName());
            System.out.println("causeMessage="
                    + exception.getCause().getMessage());
        }
    }
}
```

Chạy trên Java 17 trở lên:

```bash
javac --release 17 LocalVsThrowsDemo.java
java LocalVsThrowsDemo
```

Đầu ra:

```text
localSuccess=REAL_DATA
localFallback=CACHED_DATA
propagateSuccess=REAL_DATA
boundaryFailure=REQUEST_FAILED:storage unavailable
wrapper=IllegalStateException
cause=IOException
causeMessage=storage unavailable
```

Phân tích ba chính sách:

1. `handleLocally` bắt `IOException` và trả `CACHED_DATA`. Kết quả là một **hoàn tất bình thường**. Chỉ đúng khi dữ liệu cache được chấp nhận và ứng dụng phân biệt nguồn dữ liệu nếu cần.
2. `propagate` khai báo `throws IOException`, không tự quyết định phản hồi. `handleAtBoundary` là nơi biết cách chuyển lỗi thành trạng thái thất bại của request. Chuỗi `"REQUEST_FAILED:..."` chỉ nhằm dễ quan sát trong demo; hệ thống thật nên dùng kiểu kết quả hoặc mã lỗi an toàn, không dựa vào việc phân tích chuỗi.
3. `translate` bắt `IOException` rồi ném `IllegalStateException` có **cause**. Nó đổi tầng ngữ nghĩa mà không loại bỏ lỗi kỹ thuật gốc. Đây không phải “xử lý xong” theo nghĩa phục hồi: caller vẫn thấy thất bại.

Ví dụ có `boolean fail` để tạo lỗi **xác định**, không phụ thuộc file hay mạng thật. Một test liên quan tới hệ thống lưu trữ thực tế sẽ cần dữ liệu môi trường và cách cô lập riêng.

## 6. Thế nào là xử lý tại chỗ đúng nghĩa?

Một nhánh `catch` không thể coi là phục hồi chỉ vì nó có log:

```java
try {
    savePayment();
} catch (Exception exception) {
    System.out.println(exception.getMessage());
}
// Bên dưới vẫn trả thành công: nguy hiểm.
```

Đây là mã minh họa, không phải chương trình chạy độc lập. Nếu `savePayment()` thất bại mà code tiếp tục gửi thông báo “đã thanh toán”, hệ thống che lỗi thật.

**Xử lý tại chỗ hợp lệ** phải có một hợp đồng rõ. Ví dụ:

- Validation input: từ chối giá trị sai định dạng, giữ trạng thái chưa sửa và trả lỗi cụ thể.
- Dữ liệu tùy chọn: trả giá trị mặc định được cho phép, đồng thời bảo đảm caller hiểu đó là fallback khi cần.
- Retry có kiểm soát: chỉ thử lại lỗi tạm thời, có giới hạn và kiểm tra tác dụng phụ/idempotency.
- Một bản ghi lỗi độc lập trong batch: đánh dấu bản ghi đó thất bại rồi xử lý bản ghi kế, nếu trạng thái các bản ghi được cách ly.

**Không phù hợp để nuốt tại chỗ** nếu phát hiện bất biến nội bộ bị phá vỡ, dữ liệu vừa bị cập nhật dở hoặc một thao tác ngoài hệ thống có thể đã xảy ra nhưng chưa xác định kết quả.

Một bảng quyết định hữu ích:

| Câu hỏi | Nếu “có” | Nếu “không” |
| --- | --- | --- |
| Tầng này hiểu chính xác loại lỗi và tác động? | Có thể phân loại để xử lý | Truyền lên tầng có đủ ngữ cảnh |
| Có trạng thái hợp lệ sau khi phục hồi? | Có thể trả fallback/retry theo hợp đồng | Dừng thao tác và truyền thất bại |
| Có quyền quyết định chính sách nghiệp vụ? | Xử lý tại chỗ có thể hợp lý | Không tự biến lỗi thành kết quả |
| Có bảo đảm không phát sinh tác dụng phụ trùng lặp? | Có thể cân nhắc retry | Không retry tự động |
| Tầng gọi có cần biết việc fallback đã xảy ra? | Trả metadata/kiểu kết quả phù hợp | Có thể trả giá trị thông thường nếu đúng hợp đồng |

Nếu phục hồi tại chỗ, ghi log/metric ở mức phù hợp cho tình huống dự kiến. Đừng gắn một `catch` rộng quanh toàn bộ phương thức chỉ để chương trình “không bao giờ ném exception”.

## 7. Lan truyền bằng `throws` giúp tách chính sách khỏi cơ chế

Một module tầng thấp nên tập trung vào việc **thực thi**: đọc file, gọi database, gửi request hoặc biến đổi dữ liệu. Tầng cao có thể quyết định:

- Khi khởi động ứng dụng: lỗi đọc cấu hình bắt buộc có thể khiến việc khởi động **thất bại**.
- Khi hiển thị tính năng không thiết yếu: lỗi đọc một nguồn tùy chọn có thể dùng cache.
- Khi chạy batch: lỗi của một input độc lập có thể được ghi vào báo cáo lỗi của bản ghi đó.
- Khi xử lý yêu cầu API: lỗi I/O có thể thành phản hồi lỗi ổn định, trong khi stack trace được ghi trong log nội bộ.

Nếu repository luôn bắt `IOException` rồi trả chuỗi rỗng, nó đã **áp chính sách fallback cho mọi tầng** dù service A cần dừng còn service B có thể phục hồi. Để ngoại lệ lan truyền qua `throws` giúp tái sử dụng tầng thấp và đặt chính sách ở nơi sở hữu quyết định.

Tuy nhiên, `throws IOException` từ tầng repository đi xuyên qua mọi API công khai có thể làm lộ **chi tiết công nghệ** ra tầng nghiệp vụ. Trong trường hợp đó, có thể **dịch ngoại lệ** ở ranh giới phù hợp để cân bằng tái sử dụng với ngữ nghĩa API.

## 8. Dịch ngoại lệ: bắt nhưng không phục hồi

Có ba kiểu hành động trong một `catch`:

1. **Recover:** xử lý lỗi thành công và trả kết quả hợp lệ.
2. **Rethrow:** `throw error;` để giữ chính đối tượng exception và chuỗi nguyên nhân đã có.
3. **Translate/wrap:** `throw new DomainException("context", error);` để cung cấp loại lỗi ở tầng cao hơn và giữ cause.

Ví dụ đoạn minh họa trong ứng dụng:

```java
try {
    repository.load(customerId);
} catch (java.io.IOException original) {
    throw new CustomerLoadException(
            "Cannot load customer " + customerId, original);
}
```

Đoạn này yêu cầu `repository`, `customerId` và lớp `CustomerLoadException` có constructor nhận `(String, Throwable)`. Nó là **dịch ngoại lệ**, không phải phục hồi. Caller vẫn phải quyết định báo thất bại hay xử lý loại lỗi mới.

**Tránh cách sai:**

```java
catch (java.io.IOException original) {
    throw new IllegalStateException(original.getMessage());
}
```

Đây chỉ sao chép message; nó không đặt `getCause()` là `original`, nên mất đường truy vết `IOException`, stack gốc, cause sâu hơn và suppressed exceptions.

Khi dịch ngoại lệ, message nên cung cấp **ngữ cảnh thao tác**, không lặp hoặc lộ toàn bộ dữ liệu kỹ thuật. Có thể ghi chính `Throwable` ở ranh giới log thích hợp thay vì chỉ `getMessage()`.

## 9. Kiểm soát checked exception qua nhiều tầng

Giả sử các phương thức đều có trách nhiệm rõ ràng:

```java
void lowLevel() throws java.io.IOException {
    throw new java.io.IOException("read failed");
}

void service() throws java.io.IOException {
    lowLevel();
}

void requestBoundary() {
    try {
        service();
    } catch (java.io.IOException exception) {
        reportFailure(exception);
    }
}
```

Đây là **cụm phương thức minh họa bên trong một lớp**, phụ thuộc `reportFailure(...)`. Khi `lowLevel()` ném `IOException`, `service()` không xử lý nên để lỗi đi lên qua chữ ký `throws`. `requestBoundary()` bắt và báo thất bại theo chính sách của nó. Khai báo `throws` ở `service()` không có nghĩa `service()` đã làm bất cứ điều gì để sửa lỗi.

Điều quan trọng với **checked exception**: nếu một phương thức gọi code có thể ném checked exception và không bắt được hết các trường hợp thoát ra, chữ ký phải cho phép ngoại lệ tương ứng. Trong override/interface, phương thức override **không được mở rộng tập checked exceptions** vượt hợp đồng phương thức cha. Vì vậy API có thể định hướng chỗ nào nên dịch ngoại lệ hoặc dùng một loại ngoại lệ miền nghiệp vụ đã được định nghĩa.

Đối với **unchecked exception**, chữ ký không bắt buộc khai báo. Một phương thức có thể ghi `throws IllegalStateException` để giúp đọc tài liệu, nhưng điều đó không tạo bảo đảm rằng chỉ duy nhất loại này có thể được ném.

## 10. Ví dụ Java 17+: tầng thấp truyền lỗi, tầng ngoài xử lý và giữ tài nguyên

Trong nhiều chương trình, vấn đề không chỉ nằm ở chỗ **bắt hay ném** mà còn ở việc **dọn tài nguyên** khi ngoại lệ lan truyền. `try-with-resources` cho phép dọn resource ngay tại nơi sở hữu dù trách nhiệm xử lý lỗi ở tầng cao hơn.

Tạo tệp **`PropagationAndCleanupDemo.java`**:

```java
import java.io.IOException;

public class PropagationAndCleanupDemo {
    static final class DemoResource implements AutoCloseable {
        private final boolean failClose;
        int closeCount;

        DemoResource(boolean failClose) {
            this.failClose = failClose;
        }

        String read(boolean failRead) throws IOException {
            if (failRead) {
                throw new IOException("read failed");
            }
            return "OK";
        }

        @Override
        public void close() throws IOException {
            closeCount++;
            if (failClose) {
                throw new IOException("close failed");
            }
        }
    }

    static String readAndPropagate(
            DemoResource resource, boolean failRead) throws IOException {
        try (resource) {
            return resource.read(failRead);
        }
    }

    static void observe(String label, boolean failRead, boolean failClose) {
        DemoResource resource = new DemoResource(failClose);
        try {
            String result = readAndPropagate(resource, failRead);
            System.out.println(label + " result=" + result);
        } catch (IOException error) {
            System.out.println(label + " primary=" + error.getMessage());
            System.out.println(label + " suppressed="
                    + error.getSuppressed().length);
            if (error.getSuppressed().length > 0) {
                System.out.println(label + " cleanup="
                        + error.getSuppressed()[0].getMessage());
            }
        }
        System.out.println(label + " closes=" + resource.closeCount);
    }

    public static void main(String[] args) {
        observe("success", false, false);
        observe("readFailure", true, false);
        observe("closeFailure", false, true);
        observe("bothFailure", true, true);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 PropagationAndCleanupDemo.java
java PropagationAndCleanupDemo
```

Đầu ra:

```text
success result=OK
success closes=1
readFailure primary=read failed
readFailure suppressed=0
readFailure closes=1
closeFailure primary=close failed
closeFailure suppressed=0
closeFailure closes=1
bothFailure primary=read failed
bothFailure suppressed=1
bothFailure cleanup=close failed
bothFailure closes=1
```

Giải thích:

- `readAndPropagate(...)` giữ trách nhiệm **đóng tài nguyên** tại nơi mở phạm vi sử dụng bằng `try (resource)` và để `IOException` lan truyền bằng `throws`. Nó không cần tự quyết định cách hiển thị hoặc xử lý lỗi ở tầng ngoài.
- `observe(...)` đóng vai trò tầng gọi quyết định cách báo lỗi; trong demo nó in ra console. Ứng dụng thật nên biến trạng thái thành kết quả rõ ràng và ghi log có ngữ cảnh.
- Khi thân `try` lỗi nhưng `close()` thành công, lỗi đọc lan ra bình thường.
- Khi chỉ `close()` lỗi, ngoại lệ đóng tài nguyên đi ra như lỗi chính. Đừng đánh giá thao tác “đã thành công” nếu việc đóng resource quan trọng với tính đúng đắn dữ liệu.
- Khi **cả `read()` và `close()` cùng lỗi**, lỗi đọc là ngoại lệ chính và lỗi đóng được giữ trong `getSuppressed()`. Nhờ đó xử lý tại tầng ngoài **không làm mất nguyên nhân ban đầu**.
- `closeCount=1` ở mọi trường hợp cho thấy `try-with-resources` dọn tài nguyên trên cả đường thành công và thất bại.

Mã dùng `try (resource)` với biến resource có giá trị effectively final, được Java 9+ hỗ trợ. Nó là kỹ thuật dọn tài nguyên, **không phải** cơ chế rollback mọi thay đổi nghiệp vụ đã thực hiện trước ngoại lệ.

## 11. Phân biệt `finally`/`try-with-resources` với xử lý lỗi

Khi để exception lan truyền, Java vẫn thực hiện các `finally` phù hợp trên đường thoát. Tuy nhiên, nếu chính `finally` ném một ngoại lệ khác hoặc `return`, nó có thể **thay thế** ngoại lệ đang truyền:

```java
try {
    throw new IllegalArgumentException("original");
} finally {
    throw new IllegalStateException("cleanup failed");
}
```

Đây là đoạn minh họa; caller thường nhận `IllegalStateException`, không phải lỗi gốc. `try/finally` thủ công không tự thêm `original` vào suppressed exceptions. Vì thế, ngay cả khi lựa chọn `throws` đúng, cách viết cleanup sai có thể che mất nguyên nhân.

Khuyến nghị:

- Ưu tiên `try-with-resources` cho `AutoCloseable`, đặc biệt khi `close()` có thể ném.
- Không `return` trong `finally` để tránh nuốt ngoại lệ.
- Nếu dọn dẹp thủ công có thể thất bại, thiết kế cách giữ lỗi chính và báo lỗi cleanup; không tùy tiện bỏ lỗi cleanup nghiêm trọng.
- Không đánh dấu nghiệp vụ thành công trong `finally`, vì `finally` còn chạy khi thao tác thất bại.
- Test cả tình huống lỗi chính và lỗi dọn dẹp cùng xảy ra.

**Lan truyền lỗi** và **giải phóng resource** là hai trách nhiệm khác nhau: một phương thức có thể dọn tài nguyên tại chỗ nhưng tiếp tục chuyển ngoại lệ cho tầng gọi xử lý.

## 12. `InterruptedException`: khi nào nên lan truyền?

`InterruptedException` là checked exception thường báo rằng luồng đang chờ tại điểm hỗ trợ ngắt nhận yêu cầu hủy. Nếu phương thức có thể khai báo `throws InterruptedException`, truyền ngoại lệ lên tầng có trách nhiệm dừng tác vụ thường là cách phù hợp:

```java
String takeNext(java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
```

Đây là đoạn phương thức minh họa. Nó không biết có nên hủy vòng xử lý, dừng worker hay thông báo người gọi, nên chuyển trách nhiệm cho tầng cao.

Nếu đang triển khai `Runnable.run()` (không khai báo checked exception) và một lời gọi chờ ném `InterruptedException`, một hướng thường hợp lý là khôi phục cờ ngắt và thoát công việc:

```java
@Override
public void run() {
    try {
        processBlockingWork();
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        return;
    }
}
```

Đây là **mảnh code trong lớp triển khai `Runnable`** có phương thức `processBlockingWork()` ném `InterruptedException`. Nó không độc lập. Việc `Thread.currentThread().interrupt()` quan trọng vì nhiều API chờ xóa cờ interrupted status khi ném `InterruptedException`; khôi phục giúp mã quản lý luồng biết tác vụ được yêu cầu ngắt.

Không bắt `InterruptedException` rồi lặp lại vô hạn như chưa có chuyện gì, trừ khi có một hợp đồng đặc biệt quy định rõ việc tiêu thụ yêu cầu ngắt. Khi xử lý ngắt, việc tiếp tục cũng phải bảo đảm tài nguyên/trạng thái nhất quán.

## 13. Bắt ngoại lệ hẹp, không lấy `catch (Exception)` làm công thức chung

Một số tình huống nên bắt nhiều loại ngoại lệ, nhưng hãy chọn theo **chính sách xử lý** thay vì vì tiện viết.

Ví dụ:

```java
try {
    loadOptionalMetadata();
} catch (java.io.FileNotFoundException missing) {
    useOptionalDefault();
}
```

Đoạn này cần `loadOptionalMetadata()` và `useOptionalDefault()`. Nó chỉ phục hồi khi đúng ngoại lệ “không tìm thấy file tùy chọn”. Những `IOException` khác như mất quyền đọc hoặc lỗi thiết bị vẫn có thể lan lên nếu phương thức khai báo `throws` phù hợp.

Ngược lại:

```java
try {
    loadOptionalMetadata();
} catch (Exception ignored) {
    useOptionalDefault();
}
```

Đoạn này bắt quá rộng: `NullPointerException` do bug, lỗi chuyển đổi bất ngờ hoặc lỗi khác đều có thể bị che thành “không có metadata”. Nó làm tín hiệu chẩn đoán khó nhìn thấy.

Với multi-catch, các loại ngoại lệ trong cùng `catch` nên thực sự chia sẻ một chính sách xử lý:

```java
catch (java.net.SocketTimeoutException
        | java.net.ConnectException transientError) {
    recordTransientFailure(transientError);
}
```

Đây là mảnh minh họa trong phương thức có thể gặp các lỗi mạng ấy và đã khai báo `recordTransientFailure`. Đừng mặc định rằng mọi lỗi mạng đều được retry: request đã tạo side effect hay chưa và tính idempotent vẫn là điều phải xem xét.

## 14. Ranh giới API, lỗi nghiệp vụ và trải nghiệm người gọi

Tầng gọi có thể là controller HTTP, command-line interface, scheduled job hoặc một batch processor. Cùng một ngoại lệ hạ tầng có thể dẫn tới những quyết định khác nhau:

| Ranh giới | Chính sách có thể hợp lý | Cần tránh |
| --- | --- | --- |
| HTTP API | Chuyển lỗi sang mã/phản hồi ổn định, log `Throwable` | Trả chuỗi chi tiết kỹ thuật, token hoặc stack cho client |
| CLI | In thông báo có ích, trả exit code thất bại | Trả exit code `0` sau khi thao tác lỗi |
| Batch | Ghi kết quả lỗi cho item độc lập và tiếp tục item khác | Trộn trạng thái item lỗi vào kết quả thành công |
| Startup | Dừng khởi động nếu cấu hình bắt buộc thiếu | Dùng cấu hình mặc định không được hợp đồng cho phép |
| UI dữ liệu tùy chọn | Hiển thị cache/fallback khi cho phép | Coi fallback là dữ liệu đã cập nhật thành công |
| Giao dịch tài chính | Thất bại rõ ràng, rollback/đối soát | Nuốt lỗi và ghi “đã thanh toán” |

Ranh giới cuối có thể **bắt để kết thúc yêu cầu thất bại**, không nhất thiết **phục hồi thành thành công**. Hãy phân biệt hai mục tiêu:

- *Catch to recover*: sửa được tình trạng và có kết quả hợp lệ.
- *Catch to report*: chặn ngoại lệ ở nơi giao tiếp, giữ trạng thái thất bại và chuyển thành báo cáo được phép.

Cả hai đều là xử lý tại chỗ ở một ranh giới, nhưng kết quả nghiệp vụ khác nhau. Một ngoại lệ có thể được lan truyền qua `throws` ở nhiều tầng rồi cuối cùng được bắt để báo lỗi mà không có fallback nào.

## 15. Dữ liệu đã thay đổi trước khi lỗi: `throws` không tự rollback

Ví dụ:

```java
void reserve(Order order) throws java.io.IOException {
    order.markReserved();
    remoteService.confirmReservation(order);
}
```

Đây là đoạn minh họa cần `Order` và `remoteService`; nó **không độc lập**. Nếu `markReserved()` đã thay trạng thái rồi `confirmReservation()` ném `IOException`, việc lan truyền ngoại lệ không tự làm `order` trở về trạng thái trước đó.

Ngược lại, `catch` rồi trả fallback ở đây cũng không tự sửa lỗi; nó có thể che việc remote service đã nhận yêu cầu nhưng client không biết kết quả.

Phải bổ sung chính sách nhất quán:

1. Validate toàn bộ điều kiện có thể kiểm tra trước thay đổi.
2. Xác định transaction boundary cho cập nhật cùng kho dữ liệu.
3. Nếu việc remote có tác dụng phụ, cân nhắc idempotency key, outbox hoặc đối soát thay vì retry mù.
4. Khi không chắc kết quả thật, dùng trạng thái như `PENDING_RECONCILIATION` thay vì `SUCCESS`.
5. Test trạng thái sau lỗi, không chỉ việc ngoại lệ có được ném.

Vì vậy, `throws` **bảo toàn tín hiệu lỗi**, nhưng không bảo toàn trạng thái dữ liệu thay cho một transaction hoặc giao thức nghiệp vụ đúng đắn.

## 16. Lan truyền ngoại lệ trong lambda và API bất đồng bộ

Một điểm cần chú ý trong Java: các functional interfaces thông dụng như `Supplier<T>` và `Runnable` **không khai báo checked exception**. Bởi vậy, không thể tự do truyền `IOException` từ lambda dùng làm `CompletableFuture.supplyAsync(...)` mà không xử lý hoặc bọc.

Ví dụ minh họa:

```java
CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
    try {
        return readFromStorage();
    } catch (java.io.IOException original) {
        throw new java.util.concurrent.CompletionException(
                "Read failed asynchronously", original);
    }
});
```

Đoạn này cần khai báo/import `CompletableFuture`, định nghĩa `readFromStorage()` trả `String` và ném `IOException`. `CompletionException` là unchecked nên lambda có thể ném nó; constructor có `cause` giữ lỗi gốc.

Phía quan sát:

```java
try {
    String value = future.join();
} catch (java.util.concurrent.CompletionException wrapper) {
    Throwable cause = wrapper.getCause();
    // Phân loại cause, báo thất bại; không giả vờ thành công.
}
```

Đây cũng là mã minh họa cần `future` đã khai báo. `join()` báo lỗi qua lớp bọc bất đồng bộ; nếu cần xác định nguyên nhân, hãy kiểm tra `getCause()` và các lớp wrapper có thể có.

Ở một `ExecutorService`, `Future.get()` có thể ném `ExecutionException` khi công việc thất bại. Checked `InterruptedException` từ **luồng đang chờ** có ý nghĩa khác với ngoại lệ do tác vụ tạo ra. Đừng biến tất cả thành cùng một `RuntimeException("failed")` chỉ để khỏi suy nghĩ về hợp đồng.

## 17. Kiểm thử lựa chọn xử lý tại chỗ và lan truyền

Bộ kiểm thử nên xác nhận **không chỉ loại exception**, mà cả hiệu quả của chính sách:

| Ca kiểm thử | Với xử lý tại chỗ | Với lan truyền |
| --- | --- | --- |
| Công việc thành công | Trả kết quả thực | Trả kết quả thực |
| Lỗi thuộc loại phục hồi được | Trả fallback hợp lệ và ghi nhận nếu cần | Caller nhận lỗi và tự quyết định |
| Lỗi bất ngờ/bug | Không âm thầm biến thành thành công | Lỗi đi lên đúng lớp nguyên nhân |
| Cleanup chạy sau lỗi | Tài nguyên được dọn, trạng thái hợp lệ | Tài nguyên được dọn, lỗi vẫn còn |
| Body và `close()` cùng lỗi | Không che primary; giữ suppressed | Caller thấy primary và suppressed |
| Lỗi được dịch thành wrapper | Caller nhìn thấy wrapper phù hợp và cause còn nguyên | Wrapper tiếp tục lan lên tầng sở hữu xử lý |
| Trạng thái đã thay đổi một phần | Có rollback/compensation được kiểm chứng | Caller biết thất bại và có chính sách xử lý trạng thái |
| Ngắt tác vụ | Bảo toàn hoặc truyền tín hiệu ngắt | `InterruptedException` được truyền đúng hợp đồng |

Ví dụ với JUnit 5 (mã minh họa, cần JUnit dependency và import `org.junit.jupiter.api.Assertions.*`):

```java
@Test
void propagatePreservesIOException() {
    IOException error = assertThrows(IOException.class,
            () -> service.propagate(true));
    assertEquals("storage unavailable", error.getMessage());
}

@Test
void recoverOnlyWithAllowedFallback() {
    assertEquals("CACHED_DATA", service.handleLocally(true));
}

@Test
void translatedErrorKeepsCause() {
    IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.translate(true));
    assertInstanceOf(IOException.class, error.getCause());
}
```

Đây là **mảnh test**, không phải chương trình độc lập: cần khai báo `service`, `@Test`, `IOException` và cấu hình JUnit Jupiter. Trên Java 17 thuần JDK, bạn có thể viết một hàm assertion trong `main` hoặc dùng code runnable ở ví dụ trước để quan sát hành vi.

Một test thấy fallback không đủ để chứng minh phục hồi an toàn nếu dữ liệu đã bị cập nhật. Khi có state, phải assert luôn hậu điều kiện: tài nguyên đã đóng, transaction không commit sai, không có sự kiện `SUCCESS` sau lỗi và dữ liệu người gọi nhận khớp hợp đồng.

## 18. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Khai báo `throws` là đã xử lý lỗi.” | `throws` chỉ công bố checked exception có thể thoát ra | Đặt `catch`/policy ở tầng thực sự sở hữu quyết định |
| Bắt `Exception` rồi trả thành công | Che cả lỗi bất ngờ và trạng thái không hợp lệ | Chỉ bắt loại biết cách phục hồi, nếu không truyền lỗi |
| `catch` chỉ `printStackTrace()` rồi tiếp tục | Ghi log không đồng nghĩa phục hồi | Chuyển thất bại lên hoặc sửa trạng thái hợp lệ |
| Wrapper mới chỉ chứa `error.getMessage()` | Mất cause và stack gốc | Dùng constructor `(message, error)` |
| Bắt lỗi trong repository và trả mặc định cho mọi caller | Tầng thấp áp chính sách sai ngữ cảnh | Lan truyền hoặc dịch exception, để tầng cao quyết định |
| Đưa `IOException` ra toàn bộ API domain không cân nhắc | Rò rỉ chi tiết hạ tầng | Dịch ngoại lệ tại ranh giới domain khi có giá trị |
| Không dọn tài nguyên vì đã `throws` | Rò file/socket/DB connection | Dùng `try-with-resources` hoặc cleanup phù hợp |
| `finally` ném lỗi cleanup làm mất lỗi chính | Chẩn đoán sai nguyên nhân | Bảo toàn primary/suppressed, ưu tiên try-with-resources |
| Retry mọi exception | Dễ tăng tải/side effect, che bug | Chỉ retry có phân loại và idempotency |
| Bắt `InterruptedException` rồi bỏ qua | Mất yêu cầu hủy công việc | Truyền tiếp hoặc khôi phục cờ và kết thúc theo hợp đồng |
| Kiểm thử chỉ “không crash” | Không phát hiện thành công giả | Assert loại lỗi, cause, state và cleanup |
| `throws Exception` tùy tiện ở mọi tầng | Hợp đồng quá rộng và khó biết loại lỗi | Khai báo các checked exception có ý nghĩa hoặc dùng abstraction thích hợp |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Phương thức `void read() throws IOException` chắc chắn sẽ ném ngoại lệ mỗi khi gọi?  
**Đáp án:** Không. `throws` chỉ khai báo khả năng; phương thức vẫn có thể hoàn tất bình thường.

**Câu 2.** `throw new IOException("failed")` và `throws IOException` khác gì?  
**Đáp án:** `throw` là câu lệnh ném object; `throws` là một phần chữ ký để khai báo checked exception có thể thoát ra.

**Câu 3.** Repository biết thao tác đọc file thất bại nhưng không biết caller có được dùng cache hay không. Nên làm gì?  
**Đáp án:** Thường nên lan truyền `IOException` hoặc dịch lỗi ở ranh giới phù hợp để tầng sở hữu chính sách quyết định.

**Câu 4.** Khi bắt `NumberFormatException` từ đầu vào người dùng, trả trạng thái `INVALID_INPUT` có thể hợp lệ không?  
**Đáp án:** Có, nếu đó là tình huống dự kiến, chưa cập nhật dữ liệu và kết quả phản ánh lỗi thật.

**Câu 5.** `catch (IOException e) { throw new IllegalStateException(e.getMessage()); }` đã giữ cause chưa?  
**Đáp án:** Chưa. Dùng `new IllegalStateException("context", e)` để liên kết ngoại lệ gốc.

**Câu 6.** Để `IOException` lan truyền từ `try-with-resources` có làm `close()` bị bỏ qua không?  
**Đáp án:** Không. Resource vẫn được đóng theo quy tắc của `try-with-resources`; nếu body và close cùng lỗi, lỗi close thường nằm trong `getSuppressed()` của lỗi body.

**Câu 7.** Một phương thức trả `"CACHED_DATA"` từ nhánh catch có nghĩa thao tác nguồn đã thành công chưa?  
**Đáp án:** Không. Đó là phục hồi bằng fallback, chỉ hợp lệ nếu hợp đồng cho phép và caller không bị đánh lừa về nguồn/kết quả.

**Câu 8.** Có phải mọi `RuntimeException` đều cần thêm `throws RuntimeException`?  
**Đáp án:** Không. Ngoại lệ unchecked không bắt buộc phải khai báo.

**Câu 9.** Vì sao `throws` không tự bảo đảm transaction rollback?  
**Đáp án:** Nó chỉ truyền ngoại lệ; dữ liệu đã thay đổi cần chính sách transaction/rollback/compensation riêng.

**Câu 10.** Khi xử lý `InterruptedException` trong `Runnable.run()`, cần chú ý gì?  
**Đáp án:** Không nuốt yêu cầu ngắt; nếu không truyền tiếp được, thường khôi phục interrupted status rồi rời tác vụ theo hợp đồng.

**Câu 11.** Tầng HTTP bắt ngoại lệ để trả phản hồi thất bại có nhất thiết là “recover thành công” không?  
**Đáp án:** Không. Đó có thể chỉ là chuyển một thất bại nội bộ thành phản hồi lỗi an toàn tại ranh giới.

**Câu 12.** Khi nào nên vừa `catch` vừa ném mới?  
**Đáp án:** Khi cần dịch lỗi sang tầng trừu tượng thích hợp, thêm ngữ cảnh có ích và giữ cause, nhưng chưa thể phục hồi kết quả nghiệp vụ.

## 20. Tài liệu tham khảo

- [Java Language Specification §11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): cơ chế ngoại lệ, checked/unchecked và kiểm tra khả năng ném.
- [Java Language Specification §8.4.6 — Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): khai báo `throws` trong chữ ký phương thức.
- [Java SE 17 — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, stack trace và suppressed exceptions.
- [Java SE 17 — `IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): ngoại lệ checked cho nhiều thao tác I/O.
- [Java SE 17 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng tài nguyên của `try-with-resources`.

**Tổng kết:** *Bắt tại chỗ* khi tầng hiện tại có thể xử lý đúng và bảo đảm trạng thái hợp lệ. *Lan truyền bằng `throws`* khi tầng hiện tại chưa đủ ngữ cảnh hoặc quyền quyết định; việc đó giữ trách nhiệm ở tầng cao và không tự xử lý lỗi. Nếu cần đổi loại ngoại lệ, hãy dùng wrapper có `cause`. Trong mọi trường hợp, phải dọn tài nguyên đúng, không che lỗi gốc và kiểm thử cả trạng thái sau thất bại.