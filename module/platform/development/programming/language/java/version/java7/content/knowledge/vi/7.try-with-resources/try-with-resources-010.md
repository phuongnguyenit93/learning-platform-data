# Phân biệt suppressed exception với chuỗi nguyên nhân (cause chain) trong Java

## 1. Vì sao cần phân biệt hai loại quan hệ ngoại lệ?

Khi một thao tác thất bại, Java có thể có **nhiều ngoại lệ liên quan** đến cùng một sự cố. Chẳng hạn: thao tác đọc tệp thất bại, rồi lúc giải phóng tài nguyên, `close()` cũng thất bại. Trong một tình huống khác, tầng truy cập dữ liệu ném `IOException`, còn tầng nghiệp vụ muốn thông báo lỗi bằng một `IllegalStateException` và giữ lại nguyên nhân gốc.

Hai tình huống cần **hai quan hệ khác nhau**:

- **Cause (nguyên nhân):** ngoại lệ A được tạo ra để **giải thích hoặc bao bọc** ngoại lệ B là nguyên nhân dẫn tới A. Có thể lần theo chuỗi qua `getCause()`.
- **Suppressed exception (ngoại lệ bị đính kèm):** một lỗi **phụ phát sinh trong lúc xử lý/giải phóng** khi đã có ngoại lệ chính cần giữ. Có thể lấy các lỗi này qua `getSuppressed()`.

Từ **Java 7**, `try-with-resources` tự động đính kèm các lỗi trong `close()` bằng cơ chế *suppression* khi một ngoại lệ khác đang được ưu tiên. Các API `Throwable.getSuppressed()` và `Throwable.addSuppressed(...)` vẫn được dùng trong Java hiện đại.

Điểm quan trọng nhất: **Suppressed exception không phải là `cause`**, và **chuỗi `cause` không tự động chứa các suppressed exception**. Một đối tượng `Throwable` có thể có đồng thời **một nguyên nhân trực tiếp** và **nhiều ngoại lệ suppressed**.

## 2. Ba khái niệm cần nắm: primary, cause và suppressed

**Primary exception (ngoại lệ chính)** là ngoại lệ mà lời gọi cuối cùng ném ra hoặc `catch` đang nhận được. Trong `try-with-resources`, thông thường:

- Nếu **thân `try` ném lỗi**, lỗi đó là ngoại lệ chính. Lỗi xảy ra trong `close()` của tài nguyên sẽ được thêm vào danh sách suppressed của lỗi chính.
- Nếu **thân `try` chạy thành công** nhưng `close()` thất bại, lỗi đóng có thể là ngoại lệ chính.
- Nếu **nhiều tài nguyên cùng thất bại khi đóng**, lỗi đóng đầu tiên theo thứ tự thực tế được ưu tiên nếu không có lỗi từ thân `try`; các lỗi đóng tiếp theo có thể trở thành suppressed.

**Cause** là tham chiếu tới một `Throwable` khác đóng vai trò nguyên nhân cho ngoại lệ hiện tại. Một ngoại lệ có **tối đa một cause trực tiếp** qua `getCause()`; nguyên nhân đó lại có thể có cause của nó, tạo thành *cause chain*.

**Suppressed** là danh sách các `Throwable` phụ gắn trực tiếp với một ngoại lệ. Một ngoại lệ có thể có **0, 1 hoặc nhiều suppressed exception**; mỗi suppressed exception lại có thể có cause hoặc suppressed riêng.

```text
Ngoại lệ chính E
├── cause --------> C1
│                    └── cause -------> C2
├── suppressed[0] -> S1
└── suppressed[1] -> S2

getCause(E)        = C1
getCause(C1)       = C2
getSuppressed(E)   = [S1, S2]
```

Sơ đồ này mô tả **hai hướng liên kết khác nhau**, không phải một chuỗi tuyến tính duy nhất. Nếu cần điều tra toàn bộ một sự cố, đừng chỉ đi qua `getCause()` rồi bỏ qua các nhánh suppressed.

## 3. Các API của `Throwable` hiện còn được sử dụng

```java
Throwable cause = exception.getCause();
Throwable[] extraFailures = exception.getSuppressed();
```

Hai dòng trên là đoạn minh họa trong phương thức, với `exception` là một đối tượng `Throwable` đã có.

| API | Công dụng | Đặc điểm quan trọng |
| --- | --- | --- |
| `Throwable.getCause()` | Lấy nguyên nhân trực tiếp | Trả một `Throwable` hoặc `null` |
| `Throwable.getSuppressed()` | Lấy các lỗi suppressed trực tiếp | Trả về **mảng**, có thể rỗng nhưng không phải `null` |
| Constructor nhận `cause` | Tạo ngoại lệ mới với nguyên nhân | Ví dụ `new IllegalStateException("service failed", original)` |
| `Throwable.initCause(cause)` | Thiết lập nguyên nhân khi API cho phép | Không thể tùy ý thay nguyên nhân đã được khởi tạo; thường nên dùng constructor nhận cause |
| `Throwable.addSuppressed(other)` | Đính kèm một lỗi phụ thủ công | Không thay `cause`, không tự ném lại lỗi `other` |
| `Throwable.printStackTrace(...)` | Hiển thị lỗi cùng quan hệ liên quan | Có thể hiển thị cả nhánh `Suppressed:` và `Caused by:` |

`getSuppressed()` chỉ trả **các lỗi suppressed gắn trực tiếp** lên đối tượng đang gọi. Nó không tự truy vết toàn bộ cause chain và cũng không thu thập đệ quy tất cả suppressed của các nguyên nhân sâu hơn.

`addSuppressed(...)` từ chối `null` và việc tự thêm chính đối tượng làm suppressed; thông thường nên dùng nó khi mã phải quản lý nhiều lỗi thủ công. Với `try-with-resources`, Java đã tự làm thao tác đính kèm thích hợp nên **không cần tự gọi `addSuppressed` cho các lỗi đóng được quản lý bởi cú pháp này**.

Một số lớp `Throwable` có thể được tạo với cơ chế suppression bị tắt thông qua constructor chuyên biệt; khi đó `getSuppressed()` vẫn trả mảng rỗng ngay cả khi có lời gọi thêm. Vì thế không nên suy ra từ mảng rỗng rằng tuyệt đối không có lỗi khác trong mọi hệ thống.

## 4. Cơ chế `try-with-resources` tạo suppressed exception

Từ Java 7, tài nguyên trong `try (...)` phải có kiểu triển khai `AutoCloseable` hoặc một kiểu con như `java.io.Closeable`. Java tự gọi `close()` khi rời vùng tài nguyên, kể cả khi thân `try` ném ngoại lệ. Một ví dụ quy ước:

```java
try (SomeResource resource = openResource()) {
    performWork(resource);
}
```

Đây là **mã giả dạng Java để giải thích quy trình**: `SomeResource`, `openResource()` và `performWork(...)` đại diện cho API ứng dụng, không phải lớp/phương thức sẵn có của JDK. Ví dụ biên dịch và chạy độc lập có ở mục 6.

Giả sử `performWork(...)` ném `IOException("work failed")`, sau đó `resource.close()` ném `IOException("close failed")`. Java không muốn lỗi giải phóng tài nguyên **che mất lỗi từ thao tác chính**. Vì vậy:

```text
Thân try ném:      IOException("work failed")
                       |
                       v
                 PRIMARY EXCEPTION
                       |
                       +-- suppressed: IOException("close failed")
```

Ngoại lệ thoát ra vẫn là `work failed`. `close failed` được đính kèm và lấy được bằng `getSuppressed()`. `getCause()` của ngoại lệ `work failed` **không tự chuyển thành** `close failed`.

Điều đó khác với một lời gọi như:

```java
IOException original = new IOException("file read failed");
IllegalStateException wrapped =
        new IllegalStateException("service unavailable", original);
```

Trong đoạn này, `wrapped.getCause() == original` là `true`, còn `wrapped.getSuppressed().length` mặc định là 0. Không có `try-with-resources` hay lỗi đóng tài nguyên nào được thể hiện ở đây.

### Nếu có hai tài nguyên?

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    performWork();
}
```

Đây cũng là cú pháp minh họa: `Resource` và ba phương thức gọi cần được ứng dụng định nghĩa. Tài nguyên được khởi tạo **từ trái sang phải** và được đóng **từ phải sang trái**. Nếu thân `try` ném lỗi và cả hai `close()` cũng ném lỗi thì ngoại lệ từ thân là chính, còn lỗi từ `second.close()` và `first.close()` được đính kèm theo thứ tự đóng.

Nếu thân `try` **không ném lỗi**, mà cả hai `close()` đều thất bại, lỗi `second.close()` xuất hiện đầu tiên khi đóng và trở thành ngoại lệ chính, còn lỗi `first.close()` sẽ bị đính kèm. Điều này được kiểm thử cụ thể ở chương trình tiếp theo.

## 5. Cause chain: quan hệ nguyên nhân khi chuyển đổi lỗi giữa các tầng

Chuỗi nguyên nhân thường được tạo khi một tầng chương trình **bọc ngoại lệ cũ bằng ngoại lệ mới** có ý nghĩa với tầng gọi:

```java
import java.io.IOException;

static void readConfiguration() {
    try {
        throw new IOException("config not found");
    } catch (IOException original) {
        throw new IllegalStateException(
                "Cannot start application", original);
    }
}
```

Đây là phương thức minh họa bên trong một lớp Java. Dòng `throw new IllegalStateException(..., original)` tạo đối tượng ngoại lệ **mới** và liên kết `original` như nguyên nhân.

```text
IllegalStateException("Cannot start application")
  |
  +-- cause -> IOException("config not found")
```

Nếu tầng khác tiếp tục bọc nó bằng một ngoại lệ mới có cause, chuỗi có thể dài thêm:

```text
ApplicationException
  └── cause: IllegalStateException
               └── cause: IOException
```

Tên `ApplicationException` trong sơ đồ chỉ mang tính ví dụ. Các lớp ở từng tầng **không phải** tự động xuất hiện do JVM; chương trình hoặc thư viện tạo chúng và chuyển `cause` khi bọc lỗi.

**Cách hiểu:** “Vì sao tầng này báo lỗi?” → tìm qua `getCause()` để xem sự cố mà ngoại lệ tầng trên đang giải thích. Còn câu hỏi “Có lỗi nào khác xảy ra trong lúc xử lý hoặc dọn dẹp không?” → kiểm tra `getSuppressed()`.

Không nên gắn lỗi dọn dẹp làm `cause` của lỗi xử lý chính chỉ vì lỗi đó xảy ra sau. Lỗi đóng tài nguyên thường **không gây ra** lỗi đọc/ghi ban đầu, mà là **lỗi độc lập xảy ra trong lúc khôi phục/dọn dẹp**.

## 6. Chương trình Java 17+ hoàn chỉnh: cùng lúc có cause và suppressed

Chương trình sau được thiết kế để chạy **không cần tệp thật hay cơ sở dữ liệu**. Mỗi tài nguyên khi đóng đều cố ý ném `IOException`, giúp quan sát chính xác mối quan hệ giữa lỗi xử lý, lỗi đóng và chuỗi nguyên nhân.

Tạo tệp **`SuppressedVsCauseDemo.java`**:

```java
import java.io.IOException;

public class SuppressedVsCauseDemo {

    static final class FailingResource implements AutoCloseable {
        private final String name;

        FailingResource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("closing " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {

        // Tình huống 1: thân try lỗi và cả hai tài nguyên đóng lỗi.
        try (FailingResource first = new FailingResource("first");
             FailingResource second = new FailingResource("second")) {

            throw new IOException("work failed",
                    new IllegalArgumentException("bad argument"));

        } catch (IOException ex) {
            System.out.println("primary: " + ex.getMessage());
            System.out.println("cause: "
                    + ex.getCause().getClass().getSimpleName()
                    + ": " + ex.getCause().getMessage());
            System.out.println("suppressed count: "
                    + ex.getSuppressed().length);

            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed: "
                        + suppressed.getMessage());
            }
        }

        // Tình huống 2: thân try thành công nhưng đóng đều lỗi.
        try (FailingResource first = new FailingResource("A");
             FailingResource second = new FailingResource("B")) {

            System.out.println("body completed");

        } catch (IOException ex) {
            System.out.println("close primary: "
                    + ex.getMessage());

            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("close suppressed: "
                        + suppressed.getMessage());
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 SuppressedVsCauseDemo.java
java SuppressedVsCauseDemo
```

**Stdout đã kiểm tra:**

```text
closing second
closing first
primary: work failed
cause: IllegalArgumentException: bad argument
suppressed count: 2
suppressed: close second failed
suppressed: close first failed
body completed
closing B
closing A
close primary: close B failed
close suppressed: close A failed
```

### Giải thích tình huống 1

1. Khởi tạo `first` và `second`; không có lỗi ở constructor.
2. Thân `try` ném `IOException("work failed", new IllegalArgumentException("bad argument"))`. Ngoại lệ `IOException` trở thành ngoại lệ chính, còn `IllegalArgumentException` là **cause** được gắn **tường minh trong constructor**.
3. Java bắt đầu đóng tài nguyên theo thứ tự ngược: `second.close()` trước, rồi `first.close()`. Cả hai cố ý ném `IOException` mới.
4. Hai lỗi đóng được tự động đưa vào `ex.getSuppressed()` của `IOException("work failed")`. Chúng **không thay đổi** `ex.getCause()`.
5. `catch` nhận ngoại lệ chính và in: một cause trực tiếp, hai suppressed exception. Cause và suppressed tồn tại **đồng thời trên cùng một đối tượng**.

Có thể minh họa trạng thái thu được:

```text
IOException("work failed")                <- primary
├── cause:
│   └── IllegalArgumentException("bad argument")
├── suppressed[0]:
│   └── IOException("close second failed")
└── suppressed[1]:
    └── IOException("close first failed")
```

### Giải thích tình huống 2

1. Thân `try` chỉ in `body completed`, không ném lỗi.
2. `second.close()` của tài nguyên `B` được gọi trước và ném `IOException("close B failed")`. Do chưa có lỗi từ thân, đây là lỗi chính.
3. `first.close()` của `A` vẫn được thực thi; khi nó cũng ném `IOException("close A failed")`, lỗi này được đính kèm vào lỗi chính từ tài nguyên `B`.
4. Không có câu lệnh bọc lỗi thành cause nào. Vì vậy không nên kết luận rằng lỗi `A` là `cause` của lỗi `B`: đây là **hai lỗi đóng ở hai tài nguyên khác nhau**.

## 7. Cách đọc cây lỗi khi debug

### 7.1. Đọc cause chain khi cần tìm nguyên nhân gốc

```java
Throwable cursor = ex;
while (cursor != null) {
    System.out.println(cursor.getClass().getSimpleName()
            + ": " + cursor.getMessage());
    cursor = cursor.getCause();
}
```

Đoạn trên minh họa trong khối xử lý có biến `ex` kiểu `Throwable`. Nó **chỉ** đi qua chuỗi `getCause()`; sẽ **không hiển thị** những ngoại lệ trong `getSuppressed()`.

Trong mã debug thực tế, có thể dùng `printStackTrace()` hoặc logging framework hỗ trợ hiển thị đầy đủ cây lỗi. Nếu viết hàm duyệt ngoại lệ tổng quát do thư viện ngoài cung cấp, nên đề phòng quan hệ tham chiếu bất thường/có vòng bằng tập đối tượng đã thăm.

### 7.2. Kiểm tra suppressed exception

```java
for (Throwable suppressed : ex.getSuppressed()) {
    System.err.println("Cleanup problem: "
            + suppressed.getMessage());
}
```

Cách này liệt kê **các suppressed exception trực tiếp trên `ex`**. Nếu `ex` chỉ là ngoại lệ được bọc ở tầng trên, suppressed của ngoại lệ gốc có thể nằm trong `ex.getCause().getSuppressed()`, không nằm ngay trên `ex`.

### 7.3. `printStackTrace()` thể hiện cả hai quan hệ

```java
ex.printStackTrace(System.out);
```

Trong stack trace tiêu chuẩn, Java có thể trình bày các nhánh như:

```text
java.io.IOException: work failed
    at ...
    Suppressed: java.io.IOException: close second failed
        at ...
    Suppressed: java.io.IOException: close first failed
        at ...
Caused by: java.lang.IllegalArgumentException: bad argument
    at ...
```

Đây chỉ là **sơ đồ hình thức**, không phải stdout chính xác của ví dụ mục 6: tên phương thức, dòng mã, thứ tự các dòng frame và cách rút gọn stack trace phụ thuộc mã được biên dịch. Hãy quan sát các nhãn **`Suppressed:`** và **`Caused by:`** để hiểu hai nhánh quan hệ.

**Mẹo điều tra:** khi lỗi xảy ra gần lúc đóng tài nguyên, đừng chỉ nhìn dòng thông báo đầu tiên hoặc `getCause()`. Lỗi khi đóng có thể chứa thông tin về việc giải phóng tệp, đóng kết nối, commit/rollback, flush hoặc đóng stream, dù không phải nguyên nhân trực tiếp của lỗi ở thân `try`.

## 8. Khi bọc ngoại lệ, suppressed có bị mất không?

Giả sử thân `try-with-resources` có lỗi chính và có lỗi đóng được suppressed. Tầng phía trên muốn đổi sang ngoại lệ nghiệp vụ:

```java
try (FailingResource resource = new FailingResource("service")) {
    throw new IOException("read failed");
} catch (IOException original) {
    throw new IllegalStateException(
            "Cannot complete request", original);
}
```

Đây là đoạn minh họa đặt trong một lớp có `FailingResource` giống mục 6. Khi `catch` bọc `original` làm cause:

- `IllegalStateException` mới có **cause** là đối tượng `original`.
- Các suppressed exception do đóng tài nguyên vẫn được đính kèm **vào `original`**, không tự di chuyển sang ngoại lệ `IllegalStateException` mới.
- Vì vậy, `wrapper.getSuppressed()` có thể rỗng, trong khi `wrapper.getCause().getSuppressed()` chứa lỗi từ `close()`.

```text
IllegalStateException("Cannot complete request")
  └── cause: IOException("read failed")
                 └── suppressed: IOException("close service failed")
```

Việc bọc lỗi bằng constructor nhận cause là cách thông dụng để **giữ chuỗi nguyên nhân**. Không nên sao chép toàn bộ suppressed vào wrapper theo thói quen: cách làm ấy có thể gây **trùng lặp thông tin** khi logger đã duyệt cả cause và suppressed. Hãy bảo tồn quan hệ nguyên thủy và dựa vào hệ thống log hiển thị đúng cây lỗi, trừ khi hợp đồng API của bạn có nhu cầu khác được xác định rõ.

## 9. `addSuppressed(...)` dùng để làm gì khi không có `try-with-resources`?

Khi tự quản lý nhiều tài nguyên hoặc thực hiện nhiều bước dọn dẹp, mã đôi khi cần giữ một lỗi chính và ghi nhận các lỗi phụ khác. API cho phép:

```java
IOException workError = new IOException("write failed");
IOException cleanupError = new IOException("close failed");

workError.addSuppressed(cleanupError);

System.out.println(workError.getCause());             // null
System.out.println(workError.getSuppressed().length); // 1
```

Đây là các câu lệnh Java có thể đặt trong một phương thức. `addSuppressed` **không tự ném** `workError` hoặc `cleanupError`; nó chỉ thêm mối liên kết. Nếu cần truyền lỗi đi, mã vẫn phải xử lý hoặc ném lỗi chính.

Khác với việc viết:

```java
IOException cleanupError = new IOException("close failed");
IOException wrapped = new IOException("write failed", cleanupError);

System.out.println(wrapped.getCause() == cleanupError); // true
System.out.println(wrapped.getSuppressed().length);      // 0
```

Ở đoạn thứ hai, `cleanupError` trở thành **cause**, không phải suppressed. Điều này có thể khiến người đọc hiểu nhầm rằng thất bại đóng tài nguyên *gây ra* thất bại ghi dữ liệu, trong khi thực tế cả hai xảy ra ở những bước riêng.

**Ưu tiên `try-with-resources`** cho tài nguyên `AutoCloseable`: cú pháp đó tự xử lý thứ tự đóng và việc giữ lại lỗi phụ, ít nguy cơ sai hơn việc tự viết `finally`. Với `try/finally` thủ công, một ngoại lệ phát sinh trong `finally` có thể che ngoại lệ ban đầu nếu bạn không xây dựng logic bảo tồn riêng.

## 10. Những giới hạn và lưu ý trong xử lý thật

### 10.1. Không phải mọi ngoại lệ đều có cause hoặc suppressed

Một `Throwable` mới thường có `getCause() == null` nếu không được gán nguyên nhân, và có `getSuppressed().length == 0` nếu không có lỗi phụ được đính kèm. **Không được gọi `ex.getCause().getMessage()` mà không kiểm tra `null`** trừ khi chương trình bảo đảm cause tồn tại, như trong ví dụ mục 6.

### 10.2. Không phải suppressed luôn là `IOException`

`close()` có thể ném kiểu checked cụ thể, kiểu unchecked hoặc `Error` tùy hợp đồng và cách cài đặt. `Throwable.getSuppressed()` trả `Throwable[]`, **không chỉ `Exception[]`**. Đừng ép toàn bộ suppressed thành `IOException` nếu API tài nguyên không bảo đảm.

### 10.3. `AutoCloseable` cho phép `close() throws Exception`

Khi tài nguyên có kiểu tĩnh `AutoCloseable` chung, `close()` có thể khai báo `throws Exception`. Điều đó ảnh hưởng đến những checked exception mà phương thức phải bắt hoặc khai báo. Những lớp cụ thể như nhiều triển khai `Closeable` có thể khai báo hẹp hơn (ví dụ `IOException`). Đây là **kiểm tra kiểu khi biên dịch**, không phải thuộc tính của cause hay suppressed.

### 10.4. Không gán nghĩa sai cho thứ tự thời gian

Cause thường biểu diễn **quan hệ nguyên nhân/bao bọc**, không phải đơn giản ngoại lệ nào xảy ra trước thì là cause. Suppressed thường ghi lại lỗi phụ xảy ra trong xử lý hoặc dọn dẹp khi lỗi chính đã được ưu tiên. Vì vậy, thứ tự thời gian và quan hệ nguyên nhân không phải cùng một tiêu chí.

### 10.5. Cần giữ ngữ cảnh log có ích

Một hệ thống logging phù hợp có thể hiển thị đầy đủ cause chain và suppressed. Không nên chỉ log `ex.getMessage()` nếu cần điều tra lỗi phức tạp. Đồng thời tránh ghi dữ liệu nhạy cảm như mật khẩu, token, thông tin cá nhân hoặc nội dung yêu cầu riêng tư vào thông điệp lỗi.

### 10.6. Khối `try-with-resources` chỉ tự quản lý tài nguyên được khai báo

Các lỗi từ một tài nguyên nằm ngoài vùng `try (...)` không tự trở thành suppressed trên ngoại lệ bên trong. Cần hiểu rõ tài nguyên nào thuộc vùng tự động đóng và tài nguyên nào do caller sở hữu. Nếu constructor của tài nguyên thất bại giữa chừng, nhà cung cấp tài nguyên cũng phải tự dọn dẹp những phần đã mở trước khi trả về đối tượng thành công.

## 11. Bảng phân biệt nhanh

| Tiêu chí | Cause chain | Suppressed exceptions |
| --- | --- | --- |
| Câu hỏi giải đáp | Vì sao ngoại lệ này được tạo/ném? | Có lỗi phụ nào xảy ra khi xử lý/dọn dẹp? |
| Quan hệ trên một `Throwable` | Một cause trực tiếp (hoặc `null`) | Danh sách 0..n lỗi trực tiếp |
| API để đọc | `getCause()` | `getSuppressed()` |
| API để thêm | Constructor nhận cause; `initCause(...)` khi hợp lệ | `addSuppressed(...)` |
| `try-with-resources` có tự tạo không? | Không tự tạo cause mới chỉ vì đóng tài nguyên lỗi | Có thể tự đính kèm lỗi của `close()` |
| Khi bọc ngoại lệ bằng constructor nhận cause | Ngoại lệ gốc thành cause của wrapper | Suppressed gắn trên ngoại lệ gốc vẫn ở đó |
| Cách duyệt | Theo chuỗi `getCause()` | Qua mảng `getSuppressed()`, và có thể phải duyệt tiếp từng nhánh |
| Cách hiển thị phổ biến trong stack trace | `Caused by:` | `Suppressed:` |

**Tư duy đúng:** `cause` là **quan hệ giải thích lỗi**, còn `suppressed` là **quan hệ bảo tồn lỗi phụ**. Chúng không loại trừ nhau; một ngoại lệ hoàn toàn có thể mang cả hai.

## 12. Bài tập tự luyện và đáp án

**Bài 1.** Thân `try-with-resources` ném `IOException("read failed")`. `close()` cũng ném `IOException("close failed")`. Ngoại lệ nào là chính? Lấy lỗi còn lại bằng phương thức nào?

**Bài 2.** Thân `try` thành công, nhưng có hai tài nguyên `A` và `B` được khai báo theo thứ tự đó. Cả hai `close()` đều thất bại. Lỗi đóng nào trở thành chính?

**Bài 3.** `IllegalStateException service = new IllegalStateException("service failed", original);`. Giá trị `service.getCause()` là gì? Phép tạo này có tự làm `original` thành suppressed không?

**Bài 4.** Một `IOException original` có một suppressed từ `close()`. Bạn tạo `IllegalStateException outer = new IllegalStateException("outer", original);`. Có nên chờ `outer.getSuppressed().length == 1` ngay không?

**Bài 5.** `Throwable t = new Exception("x");`. Khi chưa thêm nguyên nhân hay lỗi phụ, `t.getCause()` và `t.getSuppressed()` lần lượt có giá trị gì?

**Bài 6.** Khi đọc một stack trace có cả `Caused by:` và `Suppressed:`, liệu có thể suy ra lỗi dưới `Suppressed:` là nguyên nhân trực tiếp dẫn tới lỗi `Caused by:` không?

### Đáp án

1. `read failed` là ngoại lệ chính; lỗi `close failed` được đính kèm và lấy bằng `ex.getSuppressed()`.
2. `B.close()` chạy trước theo thứ tự đóng ngược và lỗi của nó trở thành chính nếu không có lỗi thân; lỗi từ `A.close()` là suppressed trên lỗi của `B`.
3. `service.getCause() == original` là `true`. Không: constructor tạo **cause**, không tạo suppressed.
4. Không. `outer` mới thường có danh sách suppressed trực tiếp rỗng. Lỗi đóng vẫn nằm ở `original.getSuppressed()`, truy cập qua `outer.getCause()`.
5. `getCause()` là `null`; `getSuppressed()` trả mảng rỗng, không trả `null`.
6. Không. Hai nhãn thể hiện **hai quan hệ khác nhau**. Lỗi suppressed có thể là thất bại xảy ra **sau** khi lỗi chính đã xảy ra, ví dụ lúc `close()`; nó không mặc nhiên là nguyên nhân của lỗi chính hoặc của cause.

**Tóm tắt:** Trong Java hiện đại, `Throwable.getCause()` diễn tả **chuỗi nguyên nhân** khi ngoại lệ được bọc hoặc gắn cause, còn `Throwable.getSuppressed()` diễn tả **những lỗi phụ được bảo toàn**. Với `try-with-resources`, nếu thân `try` thất bại thì lỗi `close()` thường trở thành suppressed; nếu thân thành công mà đóng nhiều tài nguyên thất bại, lỗi đóng đầu tiên là chính và các lỗi đóng sau có thể được suppressed. Hiểu hai mối quan hệ này giúp đọc stack trace chính xác, không che mất lỗi gốc và thiết kế xử lý tài nguyên an toàn.