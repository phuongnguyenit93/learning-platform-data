# IllegalArgumentException và IllegalStateException trong Java

`IllegalArgumentException` và `IllegalStateException` là hai ngoại lệ **unchecked** quan trọng của Java, đều kế thừa `RuntimeException`. Chúng có thể cùng xuất hiện khi một lời gọi phương thức không thể được chấp nhận, nhưng mô tả **hai nguyên nhân vi phạm hợp đồng khác nhau**:

- **`IllegalArgumentException`**: *đối số do caller cung cấp không hợp lệ* theo tiền điều kiện của phương thức. Ví dụ `setAge(-2)` khi tuổi phải không âm, hoặc `setPort(70000)` khi cổng chỉ cho phép 1–65535.
- **`IllegalStateException`**: *trạng thái của đối tượng/hệ thống tại thời điểm gọi không cho phép thực hiện thao tác*. Ví dụ `send()` trước `connect()`, `write()` sau `close()`, hoặc `confirm()` khi đơn hàng đã bị hủy.

Cả hai không phải là “mức độ nghiêm trọng” khác nhau; **sự khác biệt nằm ở lý do lời gọi vi phạm hợp đồng**. Nếu caller chỉ cần sửa giá trị được truyền để lời gọi hợp lệ, `IllegalArgumentException` thường đúng hơn. Nếu cùng đối số ấy có thể hợp lệ tại một thời điểm khác sau khi trạng thái đổi, `IllegalStateException` thường diễn đạt tốt hơn.

Bài này trình bày phân cấp lớp, đặc điểm checked/unchecked, tiêu chí lựa chọn, các trường hợp giao thoa, ví dụ Java 17 biên dịch/chạy được, constructor/message/cause, JavaDoc, kiểm thử, đồng thời lưu ý rằng không phải mọi lỗi đầu vào hoặc lỗi nghiệp vụ đều nên biểu diễn bằng exception.

## 1. Vị trí trong hệ phân cấp ngoại lệ Java

Sơ đồ rút gọn:

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Error
    └── java.lang.Exception
        └── java.lang.RuntimeException
            ├── java.lang.IllegalArgumentException
            │   └── java.lang.NumberFormatException
            ├── java.lang.IllegalStateException
            ├── java.lang.NullPointerException
            └── java.lang.IndexOutOfBoundsException
```

Những điều cần nắm:

1. `IllegalArgumentException` và `IllegalStateException` là **hai lớp cùng nằm trực tiếp dưới `RuntimeException`**, không phải lớp cha/con của nhau.
2. `NumberFormatException` là một lớp con của `IllegalArgumentException`. Khi `Integer.parseInt("abc")` thất bại, caller có thể bắt bằng `catch (NumberFormatException e)` hoặc một handler rộng hơn `catch (IllegalArgumentException e)`.
3. `NullPointerException` và `IndexOutOfBoundsException` cũng là unchecked exception, nhưng **không** phải lớp con của `IllegalArgumentException`. Chúng có ý nghĩa riêng.
4. `catch (RuntimeException e)` có thể bắt cả `IllegalArgumentException` lẫn `IllegalStateException`, nhưng vì quá rộng, handler phải thực sự có chính sách thích hợp nếu muốn xử lý cả hai.
5. `catch (Exception e)` cũng bắt cả hai vì `RuntimeException extends Exception`; điều này không có nghĩa chúng trở thành checked exception.

Hai lớp `IllegalArgumentException` và `IllegalStateException` được cung cấp sẵn trong `java.lang`, vì vậy mã Java thông thường không cần `import` để sử dụng chúng.

## 2. Vì sao chúng là unchecked exception?

Một **checked exception** nằm trong phần của nhánh `Exception` không thuộc `RuntimeException`. Khi một phương thức có thể ném checked exception, Java yêu cầu mã gọi bắt hoặc khai báo nó (`catch-or-declare`) theo quy tắc kiểm tra tại thời điểm biên dịch.

Hai exception đang học là **unchecked**:

```java
static void checkQuantity(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity phải lớn hơn 0");
    }
}
```

Đây là **phương thức minh họa**, không có `main`. Không cần ghi:

```java
static void checkQuantity(int quantity)
        throws IllegalArgumentException {
    // ...
}
```

Mệnh đề `throws IllegalArgumentException` là hợp lệ nhưng **không bắt buộc** và không khiến caller bị buộc viết `catch`. Điều tương tự đúng với `IllegalStateException`.

**Unchecked không có nghĩa được Java tự xử lý.** Khi một trong hai exception được ném, luồng thực thi bị ngắt bất thường và exception lan lên call stack cho đến khi có handler tương thích. Nếu không có handler thích hợp, luồng xử lý có thể kết thúc thất bại; cách chương trình và môi trường phản ứng còn phụ thuộc nơi exception được ném.

Hãy phân biệt ba việc:

- **Bắt buộc bởi compiler:** không, đối với cả hai.
- **Có thể chủ động bắt:** có, khi tầng đang xét biết cách phục hồi hoặc phản hồi.
- **Cần thiết kế hợp đồng và giám sát lỗi:** có, dù không ghi `throws`.

## 3. Câu hỏi quyết định: sai đối số hay sai trạng thái?

Khi cân nhắc hai exception, hãy hỏi:

**(A) Caller đã truyền một giá trị không nằm trong miền giá trị hợp lệ của phương thức?**

Nếu đúng, `IllegalArgumentException` là ứng viên tự nhiên. Ví dụ một method `setRetryCount(int count)` quy định `count >= 0` và nhận `-1`.

**(B) Lời gọi bị từ chối chủ yếu do trạng thái hiện tại của đối tượng hoặc thứ tự các thao tác?**

Nếu đúng, `IllegalStateException` thường thích hợp. Ví dụ `write()` chỉ được gọi sau `open()` và trước `close()`.

**(C) Cả hai điều kiện cùng có thể sai?**

Hãy xác định **hợp đồng nào được kiểm tra trước**, đâu là nguyên nhân chính cần phản hồi, và giữ thứ tự kiểm tra ổn định, dễ hiểu. Đừng biến việc chọn exception thành suy luận về mức độ lỗi; hãy diễn đạt điều caller cần sửa.

Bảng ngắn:

| Lời gọi | Điều kiện vi phạm | Lựa chọn thường phù hợp |
| --- | --- | --- |
| `setVolume(-1)` | Âm, ngoài miền được cho phép | `IllegalArgumentException` |
| `setPort(70000)` | Cổng vượt giới hạn | `IllegalArgumentException` |
| `connect(null)` | Thiếu đối tượng bắt buộc | Thường `NullPointerException` / `Objects.requireNonNull` |
| `send(data)` trước `connect()` | Chưa có kết nối đang hoạt động | `IllegalStateException` |
| `commit()` hai lần khi chỉ cho phép một lần | Gọi sai pha thực thi | `IllegalStateException` |
| `Iterator.remove()` trước `next()` | Thao tác sai trạng thái iterator | `IllegalStateException` theo hợp đồng Iterator |
| `Integer.parseInt("x")` | Chuỗi không ở định dạng số hợp lệ | `NumberFormatException`, một loại `IllegalArgumentException` |
| `list.get(100)` khi chỉ có vài phần tử | Chỉ số ngoài phạm vi | `IndexOutOfBoundsException`, không phải `IllegalArgumentException` |
| `requireNonNull(null)` | Tham chiếu null vi phạm tiền điều kiện | `NullPointerException` |
| Giao diện báo sản phẩm hết hàng | Nhánh nghiệp vụ bình thường | Thường kiểu kết quả nghiệp vụ; không tự mặc định dùng một trong hai |

Các ví dụ trên minh họa **ý nghĩa hợp đồng**; với API thư viện thực tế, hãy ưu tiên đúng exception mà JavaDoc API ấy đã quy định.

## 4. Ví dụ chạy được: kiểm tra đối số bằng `IllegalArgumentException`

Lưu **`IllegalArgumentDemo.java`**:

```java
public class IllegalArgumentDemo {
    static int percentOf(int value, int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException(
                    "percent phải thuộc [0, 100]: " + percent);
        }
        return value * percent / 100;
    }

    public static void main(String[] args) {
        System.out.println("Hợp lệ: " + percentOf(200, 25));

        try {
            percentOf(200, 120);
            System.out.println("Không tới dòng này");
        } catch (IllegalArgumentException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        System.out.println("Kết thúc");
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac -encoding UTF-8 --release 17 IllegalArgumentDemo.java
java IllegalArgumentDemo
```

**Stdout chính xác** trên console hỗ trợ UTF-8:

```text
Hợp lệ: 50
Bắt: percent phải thuộc [0, 100]: 120
Kết thúc
```

Phân tích:

1. Giá trị `percent = 25` nằm trong miền hợp lệ, method trả `50`.
2. `percent = 120` vi phạm tiền điều kiện độc lập với trạng thái của đối tượng.
3. Method ném `IllegalArgumentException` trước khi tính toán.
4. `catch` bắt lỗi, in thông điệp rồi tiếp tục sau khối xử lý.
5. Dòng `"Không tới dòng này"` không được in vì lệnh `percentOf(200, 120)` kết thúc bất thường.

Điều caller cần sửa là **giá trị tham số**, không phải gọi `open()` hay chuyển pha trạng thái.

Lưu ý ví dụ dùng `int` để minh họa tiền điều kiện; các hệ thống tài chính không nên mặc định dùng công thức nhân/chia số nguyên như mẫu nghiệp vụ chính thức vì có vấn đề làm tròn và tràn số.

## 5. Ví dụ chạy được: trạng thái đối tượng bằng `IllegalStateException`

Lưu **`IllegalStateDemo.java`**:

```java
public class IllegalStateDemo {
    static class Session {
        private boolean connected;

        void connect() {
            if (connected) {
                throw new IllegalStateException(
                        "Phiên đã kết nối");
            }
            connected = true;
            System.out.println("Đã kết nối");
        }

        void send(String message) {
            if (!connected) {
                throw new IllegalStateException(
                        "Phải connect trước khi send");
            }
            System.out.println("Đã gửi: " + message);
        }

        void disconnect() {
            if (!connected) {
                throw new IllegalStateException(
                        "Phiên chưa kết nối");
            }
            connected = false;
            System.out.println("Đã ngắt kết nối");
        }
    }

    public static void main(String[] args) {
        Session session = new Session();

        try {
            session.send("hello");
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        session.connect();
        session.send("hello");
        session.disconnect();

        try {
            session.send("again");
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 IllegalStateDemo.java
java IllegalStateDemo
```

**Stdout chính xác**:

```text
Bắt: Phải connect trước khi send
Đã kết nối
Đã gửi: hello
Đã ngắt kết nối
Bắt: Phải connect trước khi send
```

Thông điệp `"hello"` hoàn toàn hợp lệ. Vấn đề của lời gọi đầu là **session chưa kết nối**. Sau `connect()`, cùng một lời gọi `send("hello")` thành công. Khi đã `disconnect()`, lời gọi `send("again")` lại không được phép.

Đây là dấu hiệu đặc trưng của `IllegalStateException`: **lời gọi hợp lệ phụ thuộc vào vòng đời/trạng thái đối tượng**. Trong ví dụ, trạng thái được tối giản thành biến `boolean`; mã mạng thật còn có thể có lỗi I/O, timeout, ngắt kết nối bất ngờ và vấn đề đồng bộ đa luồng.

## 6. Một method có thể dùng cả hai loại exception

Có nhiều API cần kiểm tra cả **đối số** và **trạng thái**. Ví dụ một công cụ cấu hình chỉ cho phép sửa tham số trước khi được kích hoạt:

```java
void setMaxConnections(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException(
                "maxConnections phải dương");
    }
    if (started) {
        throw new IllegalStateException(
                "Không thể đổi sau khi start");
    }
    maxConnections = value;
}
```

Đây là **phương thức minh họa** trong một class có field `started` và `maxConnections`. Hai nhánh có lý do khác nhau:

- `value <= 0`: tham số sai; caller phải chọn một số dương.
- `started == true`: trạng thái sai; caller phải đổi cấu hình trước khi khởi động hoặc dùng một API cấu hình nóng được hỗ trợ.

Thứ tự kiểm tra trong ví dụ ưu tiên bắt đối số không hợp lệ trước. Nếu đang chạy rồi caller gọi `setMaxConnections(-5)`, exception nhận được là `IllegalArgumentException`. Nếu đảo thứ tự kiểm tra, caller sẽ nhận `IllegalStateException` cho cùng tình huống. **Java không tự quyết định thứ tự ưu tiên**; đó là một phần thiết kế hợp đồng.

Cần chọn thứ tự có chủ đích, đặc biệt đối với API công khai. Khi nhiều điều kiện đều sai, tài liệu và test nên phản ánh điều kiện nào được báo trước nếu điều đó quan trọng đối với caller.

## 7. Chương trình đầy đủ: đối số và trạng thái cùng tồn tại

Lưu **`ArgumentAndStateDemo.java`**:

```java
public class ArgumentAndStateDemo {
    static class Job {
        private int priority = 1;
        private boolean submitted;

        void changePriority(int priority) {
            if (priority < 1 || priority > 5) {
                throw new IllegalArgumentException(
                        "priority phải từ 1 đến 5");
            }
            if (submitted) {
                throw new IllegalStateException(
                        "Job đã submit");
            }
            this.priority = priority;
        }

        void submit() {
            if (submitted) {
                throw new IllegalStateException(
                        "Không submit hai lần");
            }
            submitted = true;
        }

        int priority() {
            return priority;
        }
    }

    public static void main(String[] args) {
        Job job = new Job();

        try {
            job.changePriority(0);
        } catch (IllegalArgumentException e) {
            System.out.println("Đối số: " + e.getMessage());
        }

        job.changePriority(3);
        job.submit();

        try {
            job.changePriority(4);
        } catch (IllegalStateException e) {
            System.out.println("Trạng thái: " + e.getMessage());
        }

        System.out.println("Priority hiện tại: " + job.priority());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ArgumentAndStateDemo.java
java ArgumentAndStateDemo
```

**Stdout chính xác**:

```text
Đối số: priority phải từ 1 đến 5
Trạng thái: Job đã submit
Priority hiện tại: 3
```

Ở lần đầu, `priority = 0` không thuộc miền cho phép dù job chưa submit. Lần tiếp theo `priority = 3` hợp lệ, cập nhật thành công. Sau khi `submit()` chuyển trạng thái, `changePriority(4)` dùng một giá trị **hợp lệ về mặt miền**, nhưng không thể áp dụng ở trạng thái đã submit. Giá trị cũ `3` được giữ lại.

Ví dụ cũng cho thấy **không để exception xảy ra sau khi đã sửa một phần trạng thái quan trọng**, nếu có thể kiểm tra trước. Đây là một nguyên tắc thiết kế API đáng lưu ý.

## 8. Một câu hỏi khó: đối số “đúng dạng” nhưng không hợp lệ trong trạng thái hiện tại?

Ví dụ gọi `moveTo("PAID")` khi đơn hàng đang ở `CANCELLED`. `"PAID"` có thể là tên trạng thái hợp lệ trong hệ thống, nhưng **chuyển từ CANCELLED sang PAID** lại bị cấm.

Có hai cách nhìn:

- Nếu hợp đồng mô tả **đối số `targetState` chỉ được nằm trong tập các trạng thái có thể chuyển đến từ trạng thái hiện tại**, thì đối số có thể được coi là không hợp lệ.
- Nếu hợp đồng mô tả **đối tượng đã ở trạng thái không cho phép bất kỳ thao tác chuyển này**, `IllegalStateException` có thể là lựa chọn tự nhiên hơn.

Một quy ước hữu ích là phân biệt:

1. **Giá trị không hợp lệ ở mọi trạng thái** → thiên về `IllegalArgumentException`. Ví dụ tên trạng thái không tồn tại.
2. **Giá trị hợp lệ nhưng thao tác bị cấm do trạng thái hiện tại** → thiên về `IllegalStateException`.
3. **Kết quả nghiệp vụ dự kiến như “đơn không thể thanh toán vì đã hủy”** → cân nhắc trả kiểu kết quả domain thay vì ném unchecked exception.

Đây là vùng **có lựa chọn thiết kế**, không phải chỗ Java áp đặt một đáp án duy nhất. Điều quan trọng hơn việc tranh luận tên loại là **tính nhất quán, khả năng hiểu hợp đồng và chính sách phản hồi thực tế**.

## 9. `NumberFormatException` là trường hợp cụ thể của `IllegalArgumentException`

Một ví dụ JDK phổ biến:

```java
int value = Integer.parseInt("123");
```

Khi chuỗi không phân tích được thành số nguyên, `Integer.parseInt` ném `NumberFormatException`, là **lớp con của `IllegalArgumentException`**.

Ví dụ Java 17 độc lập **`NumberFormatHierarchyDemo.java`**:

```java
public class NumberFormatHierarchyDemo {
    public static void main(String[] args) {
        try {
            Integer.parseInt("abc");
        } catch (IllegalArgumentException e) {
            System.out.println("Loại: "
                    + e.getClass().getSimpleName());
            System.out.println("Là NumberFormatException: "
                    + (e instanceof NumberFormatException));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 NumberFormatHierarchyDemo.java
java NumberFormatHierarchyDemo
```

**Stdout chính xác**:

```text
Loại: NumberFormatException
Là NumberFormatException: true
```

Dù handler khai báo `IllegalArgumentException`, object runtime thực tế vẫn là `NumberFormatException`. Điều này có ích nếu tầng hiện tại muốn phản hồi chung cho mọi đối số sai.

Nếu cần xử lý khác nhau, handler cụ thể phải đứng trước handler cha:

```java
try {
    parseInput();
} catch (NumberFormatException e) {
    handleNumberFormat(e);
} catch (IllegalArgumentException e) {
    handleOtherInvalidArgument(e);
}
```

Đây là **khung minh họa**, các phương thức phụ cần được định nghĩa. Không được đảo hai handler khi handler cha đứng trước khiến handler con trở nên không thể tới được.

## 10. Đừng dùng `IllegalArgumentException` thay cho mọi lỗi đầu vào

Một số API JDK dùng **lớp unchecked chuyên biệt**:

- Tham chiếu bắt buộc bằng `null` có thể dẫn tới `NullPointerException`, đặc biệt khi dùng `Objects.requireNonNull`.
- Chỉ số ngoài phạm vi trong collection có thể là `IndexOutOfBoundsException`.
- Chuỗi số không hợp lệ thường là `NumberFormatException` (một nhánh của `IllegalArgumentException`).
- Một phương thức có thể chọn **custom exception** để caller phân biệt lỗi nghiệp vụ đặc thù.

Ví dụ `Objects.requireNonNull`:

```java
String normalized(String value) {
    java.util.Objects.requireNonNull(
            value, "value không được null");
    if (value.isBlank()) {
        throw new IllegalArgumentException(
                "value không được rỗng");
    }
    return value.trim();
}
```

Đây là **phương thức minh họa**. `null` được phân biệt khỏi chuỗi rỗng về mặt hợp đồng: đầu tiên ném `NullPointerException` có message rõ ràng, còn chuỗi chỉ chứa khoảng trắng bị từ chối bằng `IllegalArgumentException`.

Không có luật Java ép mọi mã ứng dụng dùng một tổ hợp exception như trên. Nhưng việc sử dụng các loại JDK đúng ngữ nghĩa giúp caller đọc API và dự đoán lỗi tốt hơn.

## 11. Lỗi “sai đối số” có thể đến từ dữ liệu người dùng

Một tham số sai không nhất thiết là bug của lập trình viên. Đầu vào từ HTTP, biểu mẫu, file hoặc CLI có thể sai một cách **dự kiến**. `IllegalArgumentException` vẫn có thể được ném ở một API yêu cầu tiền điều kiện chặt, nhưng nơi tiếp nhận dữ liệu bên ngoài cần cân nhắc cách **chuyển sang phản hồi hợp lệ**.

Ví dụ người dùng nhập `-5` cho số lượng. Nếu đây là một nhánh thường gặp trong UI, giải pháp có thể tốt hơn là:

1. Kiểm tra giá trị ở **ranh giới nhập liệu**.
2. Trả tập lỗi xác thực có cấu trúc, chỉ ra trường nào không hợp lệ.
3. Chỉ đưa đối tượng hợp lệ vào domain service.
4. Dùng `IllegalArgumentException` như một **hàng rào bảo vệ invariant API**, không làm cơ chế điều khiển mọi nhánh UI bình thường.

Một exception unchecked không nên vô tình biến yêu cầu người dùng sai thành lỗi máy chủ chung. Hệ thống HTTP thường cần ánh xạ thành phản hồi 4xx hoặc thông điệp nghiệp vụ thích hợp theo thiết kế, nhưng **không thể suy từ superclass một mã HTTP duy nhất đúng cho mọi tình huống**.

Điều cần tránh là bắt `IllegalArgumentException` tại ranh giới rồi luôn giả định “đó chắc chắn là lỗi của người dùng”. Nó có thể phát sinh từ **bug ở code nội bộ**, thư viện hoặc một lời gọi sai khác bên trong service.

## 12. `IllegalStateException` không chỉ áp dụng cho một đối tượng đơn lẻ

“State” có thể là:

- Vòng đời đối tượng: created → open → closed.
- Pha giao dịch: new → active → committed/rolled back.
- Trạng thái workflow: draft → approved → published.
- Trạng thái tài nguyên: connected/disconnected, initialized/uninitialized.
- Trạng thái điều phối ở một thành phần: hệ thống chưa sẵn sàng nhận tác vụ.
- Một invariant đã bị vi phạm nên không thể thực hiện hành động hiện tại.

Ví dụ bộ đọc dữ liệu:

```java
class DataReader {
    private boolean open;

    void open() {
        if (open) {
            throw new IllegalStateException("Đã mở");
        }
        open = true;
    }

    String read() {
        if (!open) {
            throw new IllegalStateException(
                    "Chưa mở hoặc đã đóng");
        }
        return "data";
    }

    void close() {
        open = false;
    }
}
```

Đây là **class minh họa không có `main`**. Các method `open` và `read` có hợp đồng phụ thuộc trạng thái. `close` trong ví dụ được thiết kế idempotent (gọi nhiều lần không ném lỗi); đây là **lựa chọn thiết kế** chứ không phải mọi resource Java đều phải từ chối hoặc chấp nhận đóng hai lần theo cùng một cách.

Khi một API thực có giao diện `AutoCloseable` hoặc `Closeable`, hãy tuân thủ hợp đồng đóng tài nguyên cụ thể, kể cả checked `IOException` nếu được khai báo, thay vì mặc định thay thế mọi lỗi đóng bằng `IllegalStateException`.

## 13. Mô hình state machine giúp quy tắc rõ ràng hơn

Khi có nhiều trạng thái, thay vì một số boolean dễ mâu thuẫn, có thể dùng `enum` và bảng chuyển trạng thái:

| Trạng thái hiện tại | Hành động | Trạng thái tiếp theo / Kết quả |
| --- | --- | --- |
| `NEW` | `start()` | `RUNNING` |
| `RUNNING` | `finish()` | `DONE` |
| `NEW` | `finish()` | `IllegalStateException` |
| `DONE` | `start()` | `IllegalStateException` |
| `RUNNING` | `start()` | `IllegalStateException` |

Nếu một hành động nhận đối số, có thể thêm quy tắc riêng về miền hợp lệ của đối số và dùng `IllegalArgumentException` khi thích hợp.

Ví dụ runnable **`StateMachineDemo.java`**:

```java
public class StateMachineDemo {
    enum Phase {
        NEW, RUNNING, DONE
    }

    static class Task {
        private Phase phase = Phase.NEW;

        void start() {
            if (phase != Phase.NEW) {
                throw new IllegalStateException(
                        "start chỉ hợp lệ ở NEW");
            }
            phase = Phase.RUNNING;
        }

        void finish() {
            if (phase != Phase.RUNNING) {
                throw new IllegalStateException(
                        "finish chỉ hợp lệ ở RUNNING");
            }
            phase = Phase.DONE;
        }

        Phase phase() {
            return phase;
        }
    }

    public static void main(String[] args) {
        Task task = new Task();

        try {
            task.finish();
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        task.start();
        task.finish();
        System.out.println("Phase: " + task.phase());

        try {
            task.start();
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 StateMachineDemo.java
java StateMachineDemo
```

**Stdout chính xác**:

```text
Bắt: finish chỉ hợp lệ ở RUNNING
Phase: DONE
Bắt: start chỉ hợp lệ ở NEW
```

Một state machine minh bạch giúp quyết định lúc nào lỗi là **trạng thái không phù hợp** và ngăn thao tác làm mất invariant. Trong ứng dụng phức tạp, còn phải xét transaction, timeout và concurrency, nhưng cốt lõi vẫn là **kiểm tra trạng thái trước khi chuyển đổi**.

## 14. Constructor và cách đặt message cho hai exception

Cả `IllegalArgumentException` và `IllegalStateException` đều có các constructor quen thuộc:

```java
new IllegalArgumentException();
new IllegalArgumentException("Sai giá trị");
new IllegalArgumentException(new RuntimeException("gốc"));
new IllegalArgumentException("Không thể nhận giá trị", cause);

new IllegalStateException();
new IllegalStateException("Chưa khởi tạo");
new IllegalStateException(new RuntimeException("gốc"));
new IllegalStateException("Không thể đổi trạng thái", cause);
```

Đây là **các biểu thức minh họa**, với biến `cause` kiểu `Throwable` được giả định đã khai báo. Cả hai lớp cho phép truyền detail message và cause theo constructor.

Mục đích:

- **Message** giải thích hợp đồng nào bị vi phạm, kỳ vọng gì, và giá trị/trạng thái hiện tại là gì nếu được phép tiết lộ.
- **Cause** giữ một Throwable phát sinh trước đó khi bạn chủ động chuyển abstraction.
- **Stack trace** giúp xác định nơi object exception mới được tạo.
- **Suppressed exceptions** là dữ liệu riêng trên `Throwable`, không tự được gắn chỉ vì chọn một trong hai lớp này.

Message có thể là `null` nếu constructor được gọi mà không cung cấp chi tiết. Tuy nhiên, trong API công khai có nhiều nhánh lỗi, message rõ ràng giúp giảm thời gian chẩn đoán.

Tránh message chỉ ghi `"invalid"` hoặc `"bad state"` mà không có ngữ cảnh.

## 15. Viết message để caller và người bảo trì hiểu cách sửa

Một thông điệp tốt thường bao gồm:

1. **Tên tham số hoặc tên thao tác**: `timeoutMillis`, `priority`, `send`.
2. **Điều kiện hợp lệ mong đợi**: phải dương, nằm trong khoảng, phải gọi `open` trước.
3. **Dữ liệu thực tế thích hợp**: ví dụ `-1` hoặc phase `CLOSED`.
4. **Không đưa thông tin nhạy cảm**: token, mật khẩu, dữ liệu định danh hoặc nội dung request bí mật.
5. **Không dùng văn bản message làm mã lỗi ổn định**; nội dung có thể thay đổi hoặc được bản địa hóa.

Ví dụ message cho `IllegalArgumentException`:

```java
throw new IllegalArgumentException(
        "pageSize phải thuộc [1, 100], nhận: " + pageSize);
```

Ví dụ message cho `IllegalStateException`:

```java
throw new IllegalStateException(
        "Không thể send khi phase=" + phase
        + "; cần phase=CONNECTED");
```

Đây là **hai câu lệnh minh họa**, giả định biến `pageSize` và `phase` nằm trong phạm vi. Chúng cung cấp điều kiện sửa rõ hơn là chỉ ghi `"error"`.

Trong API trả lỗi ra người dùng, nên chuyển exception thành mã lỗi/trạng thái hiển thị được biên soạn, không phát tán message kỹ thuật không qua rà soát.

## 16. `IllegalArgumentException`, `NullPointerException` và hợp đồng null

Lựa chọn liên quan null cần nhất quán. Nếu API không chấp nhận `null`, Java cung cấp:

```java
import java.util.Objects;

class NameService {
    static String normalize(String name) {
        Objects.requireNonNull(name, "name không được null");
        if (name.isBlank()) {
            throw new IllegalArgumentException(
                    "name không được chỉ có khoảng trắng");
        }
        return name.strip();
    }
}
```

Đây là **class minh họa không có `main`**, dùng Java 17. `Objects.requireNonNull` ném `NullPointerException` nếu `name == null`. Chuỗi chỉ gồm khoảng trắng bị ném `IllegalArgumentException` theo hợp đồng riêng.

Nếu một codebase đã chọn `IllegalArgumentException` cho mọi loại input sai kể cả null, đó có thể là quy ước nội bộ; nhưng khi sử dụng một API JDK có contract cụ thể, **không nên thay thế dự đoán về exception đã được tài liệu hóa**.

Quan trọng: `Objects.requireNonNull` chỉ xác thực điều kiện không null; nó không tự bảo đảm chuỗi không rỗng, dữ liệu đúng định dạng, hoặc trạng thái đối tượng hợp lệ.

## 17. Có nên dùng `IllegalStateException` để bọc lỗi hệ thống không?

`IllegalStateException` có constructor với `cause`, nên có thể dùng để mô tả “thành phần không sẵn sàng vì một lỗi thấp hơn”. Nhưng điều đó nên **phù hợp với ngữ nghĩa** của API.

Ví dụ code cấp dịch vụ có thể không muốn công bố checked `IOException` và muốn thể hiện rằng không thể tiếp tục vì trạng thái khởi tạo:

```java
try {
    initializeFromFile();
} catch (java.io.IOException e) {
    throw new IllegalStateException(
            "Không thể khởi tạo cấu hình", e);
}
```

Đây là **đoạn minh họa**, cần `initializeFromFile()` được định nghĩa.

Lưu ý:

- `IllegalStateException` mới có stack trace ở nơi tạo wrapper.
- `getCause()` giữ `IOException` gốc, gồm thông điệp/trace riêng.
- Wrapper là unchecked, nên hợp đồng checked exception của tầng gọi đã đổi.
- Lựa chọn này chỉ phù hợp nếu lỗi thật sự biểu thị trạng thái không thể thực hiện thao tác của tầng hiện tại.
- Nếu lỗi I/O là một phần quan trọng của hợp đồng cần caller xử lý cụ thể, tiếp tục khai báo `IOException` hoặc dùng một checked domain exception có thể thích hợp hơn.

Không viết `throw new IllegalStateException(e.getMessage())` nếu mục tiêu giữ nguyên nhân: cách đó **không gắn `cause`**.

## 18. Ví dụ Java 17: bọc cause và nhận diện loại runtime

Lưu **`CauseDemo.java`**:

```java
import java.io.IOException;

public class CauseDemo {
    static void readConfig() throws IOException {
        throw new IOException("Tệp cấu hình hỏng");
    }

    static void startService() {
        try {
            readConfig();
        } catch (IOException e) {
            throw new IllegalStateException(
                    "Service chưa sẵn sàng", e);
        }
    }

    public static void main(String[] args) {
        try {
            startService();
        } catch (IllegalStateException e) {
            System.out.println("Loại: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 CauseDemo.java
java CauseDemo
```

**Stdout chính xác**:

```text
Loại: IllegalStateException
Message: Service chưa sẵn sàng
Cause: IOException
Cause message: Tệp cấu hình hỏng
```

Wrapper cho phép tầng service bổ sung ngữ cảnh mà không làm mất nguyên nhân. Tuy nhiên, bọc một lỗi kỹ thuật thành `IllegalStateException` phải được cân nhắc tương thích API; caller vốn bắt `IOException` sẽ không còn nhận nó trực tiếp.

Nếu exception bị bọc rồi lại bọc ở nhiều tầng, hãy tránh tạo nhiều wrapper lặp thông tin mà không tăng ngữ cảnh. Cause chain có ích nhưng quá nhiều lớp bọc làm trace dài và chẩn đoán khó đọc.

## 19. `catch` cụ thể và thứ tự handler

Hai loại là sibling classes: `IllegalArgumentException` không kế thừa `IllegalStateException` và ngược lại. Có thể bắt riêng:

```java
try {
    doWork();
} catch (IllegalArgumentException e) {
    reportInvalidArgument(e);
} catch (IllegalStateException e) {
    reportInvalidState(e);
}
```

Đây là **mã khung minh họa**, các phương thức phải được định nghĩa. Hai handler cho phép chọn phản ứng khác nhau theo **hợp đồng của operation**.

Nếu muốn xử lý giống nhau, multi-catch cũng hợp lệ:

```java
catch (IllegalArgumentException | IllegalStateException e) {
    System.out.println("Không thực hiện được: " + e.getMessage());
}
```

Đây là **đoạn handler minh họa**. Tham số multi-catch ngầm định `final`, không thể gán lại.

Vì cả hai đều là `RuntimeException`, một `catch (RuntimeException e)` có thể bắt chúng cùng những runtime exception khác. Chọn handler rộng chỉ khi ranh giới đó thực sự đủ trách nhiệm xử lý mọi loại đã bắt; không nuốt tất cả exception chỉ để chương trình tiếp tục.

Nếu có `catch (RuntimeException e)` cùng các catch cụ thể, **handler cụ thể phải đứng trước** handler cha để tránh unreachable catch.

## 20. Cách kết nối với API đã tồn tại trong JDK

Nhìn một số contract tiêu biểu:

- `Iterator.remove()` có thể ném `IllegalStateException` khi `next()` chưa được gọi hoặc `remove()` đã được gọi sau `next()` gần nhất.
- `java.util.Scanner` có thể ném `IllegalStateException` nếu scanner đã đóng và gọi các thao tác không được phép.
- `Integer.parseInt` dùng `NumberFormatException` đối với chuỗi không parse được.
- `Objects.requireNonNull` dùng `NullPointerException` khi đối số bị thiếu.
- `List.get(index)` thường ném `IndexOutOfBoundsException` nếu chỉ số sai.

Tuy nhiên, không nên suy diễn rằng **mọi lớp JDK “đã đóng” đều phải ném `IllegalStateException`**. Ví dụ một số API stream hoặc file có thể ném `IOException`, `UncheckedIOException`, hoặc loại chuyên biệt theo hợp đồng riêng.

Cách học đúng là hiểu **ý nghĩa chung** của hai exception, rồi đọc JavaDoc chính xác của từng API để biết những điều kiện và loại exception mà API đó cam kết.

## 21. Ví dụ: `Iterator.remove()` và trạng thái của iterator

`Iterator.remove()` là một ví dụ có ý nghĩa rõ về trạng thái gọi phương thức.

Lưu **`IteratorStateDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;

public class IteratorStateDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(Arrays.asList("A", "B"));
        Iterator<String> it = values.iterator();

        try {
            it.remove();
        } catch (IllegalStateException e) {
            System.out.println("remove trước next: IllegalStateException");
        }

        System.out.println("next: " + it.next());
        it.remove();
        System.out.println("Sau remove: " + values);

        try {
            it.remove();
        } catch (IllegalStateException e) {
            System.out.println("remove hai lần: IllegalStateException");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 IteratorStateDemo.java
java IteratorStateDemo
```

**Stdout chính xác** với `ArrayList` trên Java 17:

```text
remove trước next: IllegalStateException
next: A
Sau remove: [B]
remove hai lần: IllegalStateException
```

Trước `next()`, iterator chưa có phần tử hiện hành phù hợp để xóa. Sau `next()`, một lần `remove()` hợp lệ. Nếu lại gọi `remove()` mà không có `next()` mới, trạng thái iterator không cho phép tiếp tục xóa.

Đây là **lỗi thứ tự sử dụng API**, không phải giá trị của một tham số, vì `remove()` không nhận tham số nào.

## 22. Không nên dùng exception để thay cho mọi kết quả nghiệp vụ

Giả sử người dùng cố mua số lượng lớn hơn tồn kho. Một API có thể lựa chọn:

- Trả một kiểu kết quả như `InsufficientStock`, `Rejected` hoặc `Result<Success, Failure>` theo ngôn ngữ của dự án.
- Ném một custom domain exception khi hệ thống coi đây là thất bại ngoại lệ cần lan tới handler chung.
- Dùng một unchecked exception khi hành vi là **vi phạm tiền điều kiện đã công bố**, không phải nhánh nghiệp vụ thường gặp.

`IllegalArgumentException` hoặc `IllegalStateException` không phải lúc nào cũng diễn đạt tốt việc sản phẩm hết hàng; ví dụ “số lượng đặt hợp lệ, nhưng tồn kho thay đổi” mang ý nghĩa nghiệp vụ khác với “đối số âm” hoặc “session chưa mở”.

Chọn exception theo **hợp đồng mong muốn**:

| Trường hợp | Phản ứng thường phù hợp |
| --- | --- |
| Caller lập trình sai giá trị theo tiền điều kiện | `IllegalArgumentException` |
| Caller gọi sai pha/lifecycle | `IllegalStateException` |
| Người dùng nhập dữ liệu sai thường xuyên | Trả lỗi xác thực có cấu trúc ở ranh giới |
| Từ chối nghiệp vụ dự kiến | Kết quả domain hoặc exception được thiết kế rõ |
| Hệ thống I/O thất bại | `IOException` hoặc wrapper/domain exception theo hợp đồng |
| Ngắt tác vụ | Giữ ý nghĩa `InterruptedException`/cờ interrupt theo hợp đồng |
| Bug nội bộ gây NPE | Sửa nguyên nhân; không mặc định đổi NPE thành một trong hai loại |

Không có quy tắc “mọi exception unchecked đều là bug” hay “mọi exception checked đều khôi phục được”. Ngữ cảnh và hợp đồng quyết định.

## 23. Thứ tự validation và tính nguyên tử của thay đổi trạng thái

Một method tốt nên kiểm tra **trước** khi thực hiện những side effect khó hoàn tác, nếu có thể:

```java
void update(int newLimit) {
    if (newLimit < 1) {
        throw new IllegalArgumentException(
                "newLimit phải dương");
    }
    if (closed) {
        throw new IllegalStateException(
                "Không thể update sau close");
    }
    limit = newLimit;
}
```

Đây là **phương thức minh họa**, với các field `closed` và `limit`.

Nếu đổi thứ tự để ghi `limit` trước rồi mới kiểm tra `closed`, phương thức có thể ném `IllegalStateException` **sau khi đã làm thay đổi trạng thái**, khiến caller hiểu nhầm rằng thao tác hoàn toàn chưa có tác dụng. Trong các trường hợp đơn giản, kiểm tra trước khi gán giúp duy trì bất biến.

Nhưng trong hệ thống có giao dịch hoặc I/O, “kiểm tra trước” không đủ để bảo đảm tính nguyên tử tuyệt đối. Side effect có thể xảy ra ở bên ngoài, transaction có thể thất bại giữa chừng, và nhiều luồng có thể đua nhau thay đổi trạng thái. Cần công cụ đồng bộ/transaction tương ứng.

## 24. Concurrency: kiểm tra trạng thái và thay đổi phải phối hợp

Một sai lầm là kiểm tra trạng thái của một đối tượng chia sẻ rồi thay đổi không đồng bộ:

```java
if (!closed) {
    // Thread khác có thể close() tại đây.
    doWork();
}
```

Đây là **mã khung minh họa**, chưa phải một thiết kế thread-safe. Giữa kiểm tra và `doWork()` có thể có một luồng khác làm thay đổi trạng thái. Điều này gọi là khoảng đua **check-then-act**.

Tùy hợp đồng, có thể:

- Bảo vệ vùng kiểm tra và chuyển trạng thái bằng `synchronized` hoặc lock.
- Dùng một phép chuyển trạng thái nguyên tử với `AtomicReference` và `compareAndSet`.
- Chỉ cho phép một luồng sở hữu đối tượng; tài liệu hóa rằng class không thread-safe.
- Sử dụng transaction hoặc primitive đồng bộ phù hợp khi trạng thái tồn tại ngoài bộ nhớ Java.

Không nên coi việc ném `IllegalStateException` tự nó giải quyết concurrency. Nó chỉ **báo một bất biến bị vi phạm hoặc một thao tác bị từ chối** ở thời điểm code kiểm tra.

Một biến `volatile boolean closed` có thể cải thiện khả năng nhìn thấy cập nhật giữa các luồng nhưng **không tự biến chuỗi check-then-act thành thao tác nguyên tử**.

## 25. Ví dụ nguyên tử hóa một chuyển trạng thái

Chương trình **`AtomicStateDemo.java`** dùng `AtomicReference` để chỉ cho phép chuyển từ `NEW` sang `STARTED` một lần:

```java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicStateDemo {
    enum State {
        NEW, STARTED
    }

    static class SingleStart {
        private final AtomicReference<State> state =
                new AtomicReference<>(State.NEW);

        void start() {
            if (!state.compareAndSet(State.NEW, State.STARTED)) {
                throw new IllegalStateException(
                        "Đã start trước đó");
            }
        }

        State state() {
            return state.get();
        }
    }

    public static void main(String[] args) {
        SingleStart task = new SingleStart();
        task.start();
        System.out.println("State: " + task.state());

        try {
            task.start();
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 AtomicStateDemo.java
java AtomicStateDemo
```

**Stdout chính xác**:

```text
State: STARTED
Bắt: Đã start trước đó
```

`compareAndSet` kiểm tra và cập nhật tham chiếu trong một thao tác nguyên tử ở phạm vi biến `state`, tránh hai lời gọi cùng chuyển thành công từ `NEW`. Đây **không phải** bằng chứng rằng mọi side effect của một công việc đã được đồng bộ; nếu `start()` còn mở kết nối hay ghi file, cần kiểm soát chúng theo hợp đồng riêng.

Kiểu exception `IllegalStateException` vẫn phản ánh thao tác lặp lại không được phép ở **trạng thái hiện tại**.

## 26. Dùng JavaDoc `@throws` để công bố hợp đồng

Vì hai exception không buộc xuất hiện trong chữ ký method, **tài liệu** đóng vai trò quan trọng:

```java
/**
 * Cấu hình giới hạn kết nối trước khi server khởi động.
 *
 * @param limit số kết nối, từ 1 đến 500
 * @throws IllegalArgumentException nếu limit ngoài [1, 500]
 * @throws IllegalStateException nếu server đã khởi động
 */
public void configure(int limit) {
    if (limit < 1 || limit > 500) {
        throw new IllegalArgumentException(
                "limit ngoài [1, 500]");
    }
    if (started) {
        throw new IllegalStateException(
                "Server đã khởi động");
    }
    maxConnections = limit;
}
```

Đây là **phương thức minh họa** trong class có field `started` và `maxConnections`. JavaDoc `@throws` mô tả **điều kiện xảy ra lỗi**. Không bắt buộc phải viết trong chữ ký:

```java
public void configure(int limit)
        throws IllegalArgumentException, IllegalStateException
```

Đây là **dòng khai báo minh họa**. Ghi unchecked exceptions trong `throws` là hợp lệ, nhưng không áp nghĩa vụ catch-or-declare cho caller. JavaDoc thường là nơi phù hợp hơn để mô tả các tiền điều kiện và trạng thái.

Nếu code dự án có chính sách công bố `throws` cho một số unchecked exceptions, phải phân biệt rõ đó là **quy ước tài liệu/thiết kế**, không phải yêu cầu kiểm tra checked exceptions của compiler.

## 27. Thứ tự catch và hành vi lan truyền

Khi một phương thức ném `IllegalArgumentException` hoặc `IllegalStateException`, Java chuyển điều khiển tới handler phù hợp theo quy tắc của `try/catch`. Nếu handler kết thúc bình thường, chương trình tiếp tục **sau cấu trúc `try/catch`**, không tự chạy lại lời gọi đã thất bại.

```java
try {
    setPort(70000);
    System.out.println("Không tới đây");
} catch (IllegalArgumentException e) {
    System.out.println("Giá trị cổng sai");
}
System.out.println("Tiếp tục sau catch");
```

Đây là mảnh mã minh họa cần `setPort` được khai báo. Nếu không có handler phù hợp, exception tiếp tục lan lên caller. Các `finally` liên quan vẫn có quy tắc hoàn tất riêng; một `finally` ném lỗi mới có thể che lỗi đang truyền, còn `try-with-resources` có thể giữ lỗi `close()` bằng suppressed exceptions. Những quy tắc đó áp dụng **cho mọi loại exception**, không phải hành vi riêng của hai lớp đang so sánh.

Điều quan trọng của bài: bắt được một `IllegalStateException` **không có nghĩa** state đã được phục hồi. Handler phải bảo đảm hậu điều kiện hợp lệ hoặc tiếp tục báo thất bại cho ranh giới sở hữu chính sách.

## 28. Catch rộng có thể che giấu bug

Ví dụ nguy hiểm:

```java
try {
    processOrder();
} catch (RuntimeException ignored) {
    return "SUCCESS";
}
```

Đây là **mã khung phản ví dụ**, chưa định nghĩa `processOrder` và phương thức chứa. Handler bắt cả những lỗi tiền điều kiện, lỗi trạng thái, `NullPointerException`, lỗi chỉ số và những lỗi runtime khác, rồi trả một kết quả **thành công giả**.

Thay vào đó, một ranh giới HTTP/CLI/job cần:

- Xác định liệu failure thuộc **đầu vào của caller** hay **bug/trạng thái nội bộ**.
- Ghi nhận thông tin phù hợp để chẩn đoán mà không lộ dữ liệu nhạy cảm.
- Trả trạng thái thất bại đúng hợp đồng, không coi catch được exception là đã khôi phục thành công.
- Giữ `cause`/stack trace khi chuyển abstraction.
- Chọn xử lý cụ thể khi thực sự có khả năng phục hồi; các lỗi bất ngờ có thể cần được báo cho hệ thống giám sát.

**Không nên tự động ánh xạ tất cả `IllegalArgumentException` thành “người dùng nhập sai”.** Một thư viện nội bộ có thể ném nó vì service đã tính tham số sai, tức là một bug ở phía server.

## 29. Khi nào tạo custom exception thay vì dùng hai lớp này?

`IllegalArgumentException` và `IllegalStateException` diễn đạt tốt các vi phạm hợp đồng phổ biến. Nếu caller thực sự cần **phân biệt một điều kiện chuyên biệt**, custom exception có thể hữu ích:

```java
class InvalidWorkflowStateException
        extends IllegalStateException {
    InvalidWorkflowStateException(String message) {
        super(message);
    }
}
```

Đây là **class minh họa**, chưa có `main`. Loại mới vẫn unchecked và vẫn thuộc nhánh `IllegalStateException`, nên caller có thể catch cụ thể hoặc catch cha.

Tương tự một ứng dụng có thể xây:

```java
class InvalidCommandArgumentException
        extends IllegalArgumentException {
    InvalidCommandArgumentException(String message) {
        super(message);
    }
}
```

Tuy nhiên, không cần tạo class riêng nếu sự khác biệt chỉ nằm trong một chuỗi message mà caller không cần phân loại theo kiểu. Nhiều class exception vô nghĩa làm API khó học hơn.

Nếu điều kiện mới là **thất bại nghiệp vụ dự kiến** (ví dụ số dư không đủ), cân nhắc kiểu kết quả/domain error hoặc custom exception riêng với hợp đồng rõ, thay vì ép mọi chuyện vào hai loại Java core.

## 30. Kiểm thử nên kiểm tra loại exception và bất biến

Chỉ kiểm tra rằng “một exception đã được ném” là chưa đủ. Nên kiểm tra:

- **Đúng loại** `IllegalArgumentException` cho đối số sai.
- **Đúng loại** `IllegalStateException` cho thứ tự/trạng thái sai.
- **Đúng message/mã lỗi** nếu đó là hợp đồng test, tránh phụ thuộc vào wording không ổn định.
- **Không thay đổi trạng thái ngoài ý muốn** sau lời gọi thất bại.
- **Lời gọi hợp lệ vẫn thành công**.
- **Thử lại sau chuyển trạng thái hợp lệ** hoạt động theo đúng quy tắc.
- **Cause** được giữ nếu code wrap một exception khác.
- Các trường hợp gần biên: 0, -1, giá trị tối đa, state đã đóng/đã hoàn tất, gọi trùng lặp.

JUnit có `assertThrows` để kiểm tra kiểu exception và có thể xem `getMessage()`, `getCause()`. Nếu không sử dụng JUnit, có thể viết phép thử thuần Java để chứng minh.

## 31. Chương trình Java 17 tự kiểm tra hai loại exception

Lưu **`ArgumentStateAssertionsDemo.java`**:

```java
public class ArgumentStateAssertionsDemo {
    static class Counter {
        private boolean closed;
        private int value;

        void add(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException(
                        "amount phải dương");
            }
            if (closed) {
                throw new IllegalStateException(
                        "Counter đã đóng");
            }
            value += amount;
        }

        void close() {
            closed = true;
        }

        int value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter();

        try {
            counter.add(0);
            throw new AssertionError("Thiếu IllegalArgumentException");
        } catch (IllegalArgumentException e) {
            if (!"amount phải dương".equals(e.getMessage())) {
                throw new AssertionError("Sai message đối số");
            }
            System.out.println("PASS argument");
        }

        counter.add(5);
        counter.close();

        try {
            counter.add(3);
            throw new AssertionError("Thiếu IllegalStateException");
        } catch (IllegalStateException e) {
            if (!"Counter đã đóng".equals(e.getMessage())) {
                throw new AssertionError("Sai message trạng thái");
            }
            System.out.println("PASS state");
        }

        if (counter.value() != 5) {
            throw new AssertionError("Đã sửa trạng thái sai");
        }
        System.out.println("PASS invariant");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ArgumentStateAssertionsDemo.java
java ArgumentStateAssertionsDemo
```

**Stdout chính xác**:

```text
PASS argument
PASS state
PASS invariant
```

Ví dụ chủ động dùng `AssertionError` để test thất bại, không phụ thuộc tùy chọn `-ea`. Kết quả chứng minh cả hai đường ném exception đúng loại và **giá trị `counter` vẫn bằng 5** sau khi lời gọi không hợp lệ bị từ chối.

Trong dự án thực, test đa luồng, giao dịch hoặc tài nguyên có thể cần thêm công cụ chuyên biệt; mẫu này chỉ chứng minh hợp đồng đối số/trạng thái của đối tượng đơn giản.

## 32. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Hai loại exception giống nhau vì đều là RuntimeException.” | Cùng là unchecked nhưng khác ý nghĩa: đối số sai so với trạng thái không cho phép. |
| “`IllegalArgumentException` là checked vì tên có Exception.” | Sai. Nó kế thừa `RuntimeException` nên unchecked. |
| “`IllegalStateException` chỉ xuất hiện khi đối tượng bị hỏng hoàn toàn.” | Không. Nó có thể báo thao tác sai pha như `send` trước `connect`. |
| “Mọi input sai đều phải ném `IllegalArgumentException`.” | Không. Có loại JDK chuyên biệt và lỗi xác thực dự kiến có thể dùng kết quả cấu trúc. |
| “Mọi trạng thái nghiệp vụ không mong muốn đều phải ném `IllegalStateException`.” | Không. Một kết quả domain hợp lệ có thể phù hợp hơn exception. |
| “Cần ghi `throws IllegalStateException` để compiler cho ném.” | Không. Đây là unchecked exception. |
| “Một handler `catch (IllegalArgumentException)` bắt cả IllegalStateException.” | Không. Chúng là sibling classes. |
| “`NumberFormatException` không liên quan IllegalArgumentException.” | Sai. Nó là subclass của `IllegalArgumentException`. |
| “`NullPointerException` là subclass của IllegalArgumentException.” | Sai. Đây là nhánh riêng dưới `RuntimeException`. |
| “Đã catch được exception nghĩa là thao tác thành công.” | Không. Handler còn phải có logic khôi phục hoặc báo thất bại đúng. |
| “Đối số hợp lệ thì method luôn thành công.” | Không nếu trạng thái, I/O hoặc các điều kiện khác chưa phù hợp. |
| “Thay một loại exception bằng loại kia không ảnh hưởng caller.” | Có thể ảnh hưởng handler, log, test, tài liệu và mã phục hồi. |
| “Message có thể dùng làm mã điều khiển nghiệp vụ.” | Không nên. Message có thể thay đổi hoặc được bản địa hóa. |
| “`volatile` biến kiểm tra và update state thành nguyên tử.” | Không. Cần cơ chế đồng bộ/phép chuyển trạng thái phù hợp. |
| “Exception unchecked không bao giờ cần log/tài liệu.” | Sai. Hợp đồng và chẩn đoán vẫn rất quan trọng. |
| “Sai giá trị trong input HTTP luôn là bug phía server.” | Không. Cần phân biệt lỗi xác thực người dùng với vi phạm invariant trong code nội bộ. |

## 33. Câu hỏi tự kiểm tra

**1. `setRate(-1)` khi rate phải không âm nên cân nhắc loại nào?**  
`IllegalArgumentException`, vì giá trị tham số không thuộc miền cho phép.

**2. `start()` gọi lại khi process đã STARTED và chỉ cho start một lần?**  
`IllegalStateException` thường phù hợp, vì lời gọi sai trạng thái/vòng đời.

**3. `send("hi")` thất bại khi chưa kết nối, trong khi chuỗi hợp lệ?**  
`IllegalStateException` vì nguyên nhân chính là trạng thái kết nối.

**4. `NumberFormatException` là checked hay unchecked? Là subclass của lớp nào đang học?**  
Unchecked, thuộc nhánh `IllegalArgumentException`.

**5. Có phải khai báo `throws IllegalArgumentException` trong chữ ký method không?**  
Không. Có thể tài liệu hóa bằng JavaDoc `@throws`.

**6. `catch (IllegalArgumentException e)` có bắt `IllegalStateException` không?**  
Không, vì hai lớp không kế thừa nhau.

**7. Nếu dùng `catch (RuntimeException e)` thì có bắt cả hai không?**  
Có, nhưng cũng có thể bắt nhiều loại runtime exception khác; cần tránh handler quá rộng nếu không có chính sách đúng.

**8. `Objects.requireNonNull(null)` thường ném gì?**  
`NullPointerException`.

**9. Khi giá trị hợp lệ nhưng object đã CLOSED, nên thiên về loại nào?**  
`IllegalStateException`, nếu hợp đồng mô tả thao tác không cho phép ở trạng thái đó.

**10. Nếu giá trị đối số sai và object cũng đã CLOSED, Java tự ưu tiên lỗi nào?**  
Không. Thứ tự kiểm tra và hợp đồng do người thiết kế API quyết định.

**11. Khi bọc `IOException` thành `IllegalStateException`, làm sao giữ nguyên nhân?**  
Sử dụng constructor `new IllegalStateException("...", e)` và giữ `e` ở `getCause()`.

**12. Có thể ném `IllegalStateException` khi một object đã gọi `close()` không?**  
Có nếu hợp đồng class quy định thao tác tiếp theo bị cấm và loại đó phù hợp; nhiều API cụ thể có thể dùng exception khác.

**13. Vì sao không nên coi mọi `IllegalArgumentException` trong server là lỗi do người dùng?**  
Nó có thể do code nội bộ truyền tham số sai; chỉ ranh giới biết nguồn dữ liệu mới có thể phân loại chính xác.

**14. `IllegalStateException` có ngăn race condition không?**  
Không. Exception chỉ báo lỗi; cần đồng bộ/atomic transition nếu trạng thái dùng chung giữa nhiều luồng.

**15. Nếu method ném IAE rồi được catch ở caller, Java có tự chạy lại lời gọi ấy không?**  
Không. Caller quyết định có thử lại với đối số khác hay không.

**16. Nên đặt JavaDoc thế nào cho API có cả hai loại?**  
Ghi `@throws IllegalArgumentException` cho tiền điều kiện giá trị và `@throws IllegalStateException` cho điều kiện state/vòng đời.

**17. Tên loại nào hợp lý hơn khi `Iterator.remove()` được gọi trước `next()`?**  
`IllegalStateException` theo hợp đồng của `Iterator`.

**18. Nếu trong một tính năng hết hàng là nhánh bình thường, có bắt buộc dùng một trong hai exception không?**  
Không. Có thể trả kết quả nghiệp vụ có trạng thái hoặc custom domain error phù hợp.

**19. Tại sao không bắt tất cả `RuntimeException` rồi trả thành công?**  
Vì có thể che lỗi thực sự, làm mất invariant và khiến caller hiểu nhầm thao tác hoàn tất.

**20. Trong một method có cả input và state validation, tại sao nên kiểm tra trước side effect?**  
Để tránh thay đổi một phần đối tượng rồi ném lỗi, khiến trạng thái và tín hiệu trả về không nhất quán.

## 34. Checklist thiết kế và review

Khi quyết định giữa `IllegalArgumentException` và `IllegalStateException`:

1. **Xác định tiền điều kiện của đối số:** miền hợp lệ, null, phạm vi, định dạng, quan hệ giữa các tham số.
2. **Xác định invariant/trạng thái của object:** pha hoạt động, resource đã mở/đóng, kết nối, workflow.
3. **Phân biệt lỗi giá trị với lỗi vòng đời:** cùng giá trị có thành công khi state đổi không?
4. **Xem API chuẩn có một loại ngoại lệ chuyên biệt hơn không:** `NumberFormatException`, `IndexOutOfBoundsException`, `NullPointerException`, v.v.
5. **Xem đây có phải nhánh nghiệp vụ dự kiến không:** có cần kiểu kết quả/domain status thay vì exception?
6. **Định nghĩa thứ tự validation:** khi nhiều điều kiện cùng sai, lỗi nào được báo trước?
7. **Kiểm tra trước các side effect nếu có thể:** không sửa một phần state rồi mới ném lỗi dễ tránh.
8. **Dùng message hữu ích, an toàn:** tên tham số/trạng thái và giá trị không nhạy cảm.
9. **Không dùng message để định tuyến logic:** dùng loại exception hoặc mã lỗi có cấu trúc.
10. **Công bố hợp đồng bằng JavaDoc `@throws`:** dù không bắt buộc viết trong chữ ký.
11. **Không ép caller catch unchecked exception ở mọi tầng:** chỉ xử lý nơi có trách nhiệm thực sự.
12. **Tại ranh giới nhập liệu, phân loại lỗi từ người dùng với bug nội bộ:** không ánh xạ mù quáng.
13. **Nếu wrap lỗi khác, bảo toàn cause:** dùng constructor `(String, Throwable)`.
14. **Nếu dùng nhiều thread, bảo vệ check-then-act:** lock/atomic/ownership theo thiết kế.
15. **Kiểm thử cả đối số sai và state sai:** cùng các đường hợp lệ và trường hợp gần biên.
16. **Kiểm tra invariant sau failure:** exception không được che việc cập nhật trạng thái sai.
17. **Xem ảnh hưởng tương thích API:** đổi loại exception có thể làm hỏng handler của caller.
18. **Không nuốt RuntimeException rồi báo thành công giả.**
19. **Không dùng `Error` để diễn đạt lỗi đối số/trạng thái ứng dụng.**
20. **Cân nhắc custom exception chỉ khi cần phân biệt tình huống thực sự.**

## 35. Tổng kết

`IllegalArgumentException` và `IllegalStateException` đều là **unchecked RuntimeException**, không buộc caller catch-or-declare. Khác biệt quyết định là **nguồn gốc của lời gọi không hợp lệ**:

- **`IllegalArgumentException`** dành cho **tham số caller truyền không thỏa tiền điều kiện**, chẳng hạn giá trị âm, ngoài khoảng hoặc định dạng bị từ chối.
- **`IllegalStateException`** dành cho **thao tác không được phép vì trạng thái hiện tại**, chẳng hạn dùng object trước khởi tạo, sau khi đóng hoặc lặp một transition không hợp lệ.

Một API có thể cần cả hai: kiểm tra đối số, rồi kiểm tra state, rồi mới thay đổi dữ liệu. Java không tự quyết định thứ tự ưu tiên nếu cả hai vi phạm. Khi có loại JDK cụ thể hơn như `NullPointerException`, `IndexOutOfBoundsException` hoặc `NumberFormatException`, hãy theo đúng hợp đồng API đang sử dụng.

Quan trọng hơn cả tên exception là **hợp đồng rõ ràng, xử lý ở đúng ranh giới, message an toàn, bảo toàn cause, kiểm thử invariant và phân biệt thất bại bất thường với kết quả nghiệp vụ dự kiến**.
