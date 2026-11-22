# Giới hạn với self-cause, self-suppression và giá trị `null` trong Java

Đối tượng `Throwable` có hai cơ chế liên kết lỗi cần phân biệt: **cause** — nguyên nhân trực tiếp của một ngoại lệ — và **suppressed exceptions** — các ngoại lệ phụ bị giữ lại khi một ngoại lệ khác đang được truyền ra ngoài. Cả hai giúp giữ bối cảnh chẩn đoán, nhưng Java đặt ra những quy tắc khác nhau về việc tham chiếu tới **chính đối tượng đó** và cách xử lý giá trị `null`.

Bốn quy tắc quan trọng nhất:

- **Self-cause bị cấm:** `ex.initCause(ex)` ném `IllegalArgumentException`. Một ngoại lệ không thể được chỉ định là nguyên nhân trực tiếp của chính nó qua API này.
- **Self-suppression bị cấm:** `ex.addSuppressed(ex)` cũng ném `IllegalArgumentException`. Một ngoại lệ không thể suppress chính nó.
- **`null` có thể là cause:** `initCause(null)` hoặc constructor nhận cause bằng `null` là hợp lệ. Tuy nhiên, `initCause(null)` vẫn **tiêu thụ quyền khởi tạo cause một lần duy nhất**.
- **`null` không thể là suppressed exception:** `ex.addSuppressed(null)` ném `NullPointerException`. Muốn không có lỗi phụ thì **không gọi `addSuppressed`**, thay vì truyền `null`.

Điểm dễ gây lỗi là kiểm tra bằng `getCause() == null` rồi nghĩ rằng chưa từng khởi tạo cause. Giá trị trả về `null` chỉ có nghĩa chưa biết hoặc không có nguyên nhân; nó **không phản ánh** liệu quyền gọi `initCause` đã được sử dụng hay chưa.

Bài này giải thích hợp đồng Java SE 21 của `Throwable.initCause()`, `addSuppressed()`, `getCause()`, `getSuppressed()`, tình huống đặc biệt khi tắt suppression, hệ quả trong `try-with-resources` và các mẫu thiết kế giúp tránh làm mất thông tin lỗi. Các ví dụ chạy bằng JDK **17 trở lên**.

## 1. Phân biệt cause và suppressed exception trước khi xét giới hạn

Một ngoại lệ có thể chứa cả một cause lẫn nhiều suppressed exceptions:

```text
DataLoadException("cannot load")
  |
  +-- getCause() --> IOException("read failed")
  |                     |
  |                     +-- getSuppressed()[0]
  |                           --> IOException("close failed")
  |
  +-- getSuppressed()[0]
        --> RuntimeException("secondary cleanup")
```

Sơ đồ trên là **mô hình quan hệ**, không phải cú pháp Java. Nó cho thấy hai quan hệ có thể tồn tại trên các đối tượng khác nhau trong cùng một đồ thị lỗi.

| Tiêu chí | Cause | Suppressed |
| --- | --- | --- |
| Mục đích | Giải thích tại sao ngoại lệ hiện tại xảy ra | Giữ những ngoại lệ phụ đã bị bỏ qua để một lỗi khác được truyền ra |
| API thiết lập | Constructor nhận `Throwable cause` hoặc `initCause(cause)` | `addSuppressed(exception)` |
| API đọc | `getCause()` | `getSuppressed()` |
| Số lượng qua API chuẩn | Tối đa một tham chiếu cause cho mỗi `Throwable` | Danh sách nhiều phần tử, theo thứ tự thêm |
| Giá trị khi không có | `null` | Mảng `Throwable[]` rỗng |
| Truyền `null` lúc thiết lập | Được chấp nhận trong các constructor phù hợp và `initCause(null)` | Không hợp lệ: `NullPointerException` |
| Trỏ tới chính đối tượng | `initCause(this)` bị từ chối | `addSuppressed(this)` bị từ chối |
| Cơ chế phổ biến | Bọc lỗi khi đi qua các tầng nghiệp vụ | `try-with-resources` khi đóng tài nguyên cũng phát sinh lỗi |

**Không có quan hệ tự động một-một giữa cause và suppressed.** Một ngoại lệ bị suppress không tự trở thành cause; một cause không tự xuất hiện trong `getSuppressed()`.

## 2. Self-cause: `initCause(this)` bị từ chối

`Throwable.initCause(Throwable cause)` dùng để gắn một nguyên nhân sau khi đối tượng đã được tạo, thường để hỗ trợ các lớp ngoại lệ cũ không có constructor nhận cause.

Chữ ký:

```java
public synchronized Throwable initCause(Throwable cause)
```

Theo Javadoc Java 21, nếu tham số chính là đối tượng `Throwable` đang được cập nhật, phương thức ném **`IllegalArgumentException`**. Hệ quả là:

```java
Exception failure = new Exception("failure");
failure.initCause(failure); // Sai: tự làm nguyên nhân của chính mình.
```

Đây là **đoạn cố ý gây ngoại lệ lúc chạy**, không phải lỗi biên dịch. Việc tự liên kết làm cause vô nghĩa về mặt quan hệ nhân quả và có nguy cơ tạo đồ thị chẩn đoán không hợp lệ.

Điểm so sánh quan trọng:

```java
Exception a = new Exception("same");
Exception b = new Exception("same");

a.initCause(b); // Hợp lệ: a và b là HAI đối tượng khác nhau.
```

Hai đối tượng có thể cùng kiểu, cùng message, thậm chí có stack trace tương tự; điều Java cấm là truyền **chính tham chiếu tới a** làm cause của a. Phép kiểm tra dựa trên **danh tính đối tượng**, không phải việc hai ngoại lệ có nội dung giống nhau.

### Ví dụ chạy được: tự gắn cause bị từ chối

Lưu thành `SelfCauseDemo.java`:

```java
public class SelfCauseDemo {
    public static void main(String[] args) {
        Exception failure = new Exception("failure");

        try {
            failure.initCause(failure);
        } catch (IllegalArgumentException ex) {
            System.out.println("self=" + ex.getClass().getSimpleName());
        }

        System.out.println("causeAfterRejected=" + failure.getCause());

        Exception original = new Exception("original");
        failure.initCause(original);
        System.out.println("linked=" + (failure.getCause() == original));

        try {
            failure.initCause(new Exception("replacement"));
        } catch (IllegalStateException ex) {
            System.out.println("secondInit="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SelfCauseDemo.java
java SelfCauseDemo
```

Kết quả:

```text
self=IllegalArgumentException
causeAfterRejected=null
linked=true
secondInit=IllegalStateException
```

Phân tích:

1. Lần gọi `initCause(failure)` bị từ chối vì self-cause.
2. Đối tượng vẫn có thể gắn cause hợp lệ sau đó, vì lần gọi bị từ chối chưa đặt cause thành công.
3. Gắn `original` thành công, nên so sánh danh tính `==` trả `true`.
4. Lần gọi `initCause` kế tiếp bị từ chối vì cause đã được khởi tạo.

Không nên xử lý self-cause bằng cách âm thầm bỏ qua rồi trả lỗi không có nguyên nhân nếu sự cố đó phản ánh thiết kế exception chaining sai. Hãy xác định đúng ngoại lệ gốc và ngoại lệ wrapper.

## 3. Khởi tạo cause được phép **một lần**, kể cả khi đặt `null`

Đây là chi tiết quan trọng hơn việc `getCause()` trả gì.

Khi tạo một đối tượng bằng constructor **không nhận cause**, ví dụ `new Exception("message")`, trạng thái cause ban đầu là **chưa được khởi tạo**. Bạn có thể gọi `initCause(...)` **một lần**.

Sau khi gọi:

```java
Exception failure = new Exception("failure");
failure.initCause(null); // Hợp lệ và tiêu thụ một lần khởi tạo.
```

`getCause()` vẫn trả `null`. Nhưng một lần `initCause(...)` khác sẽ ném **`IllegalStateException`**, ngay cả khi lần đầu đã truyền `null`.

Với constructor **đã nhận tham số cause**, ví dụ `new Exception("message", null)`, cause được xem là **đã khởi tạo**, dù giá trị của nó là `null`. Vì thế `initCause(...)` cũng không được gọi sau constructor ấy.

| Cách tạo / thao tác | `getCause()` | Có được gọi `initCause(...)` sau đó không? |
| --- | --- | --- |
| `new Exception("x")` | `null` | **Có**, nếu chưa từng gọi `initCause` |
| `new Exception("x").initCause(null)` | `null` | **Không**, đã khởi tạo một lần |
| `new Exception("x", null)` | `null` | **Không**, cause đã được khai báo trong constructor |
| `new Exception("x", original)` | `original` | **Không**, đã khởi tạo trong constructor |
| `new Exception("x").initCause(original)` | `original` | **Không**, lần khởi tạo đã được dùng |

Các constructor `Throwable(Throwable cause)` và `Throwable(String message, Throwable cause)` có cùng giới hạn được nêu trong Javadoc; các lớp con có thể có constructor tương ứng.

### Ví dụ Java 17+: `null` vẫn được coi là một lần khởi tạo

Lưu thành `NullCauseDemo.java`:

```java
public class NullCauseDemo {
    public static void main(String[] args) {
        Exception deferred = new Exception("deferred");

        System.out.println("initial=" + deferred.getCause());
        deferred.initCause(null);
        System.out.println("afterNull=" + deferred.getCause());

        try {
            deferred.initCause(new Exception("late"));
        } catch (IllegalStateException ex) {
            System.out.println("repeat="
                    + ex.getClass().getSimpleName());
        }

        Exception fromConstructor = new Exception("ctor", null);
        System.out.println("ctorCause=" + fromConstructor.getCause());

        try {
            fromConstructor.initCause(new Exception("late"));
        } catch (IllegalStateException ex) {
            System.out.println("ctorAlreadyInitialized="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 NullCauseDemo.java
java NullCauseDemo
```

Kết quả:

```text
initial=null
afterNull=null
repeat=IllegalStateException
ctorCause=null
ctorAlreadyInitialized=IllegalStateException
```

Bài học ở đây: **`getCause() == null` không đủ để suy ra có thể gọi `initCause(...)`**. Không có API công khai thông thường để hỏi “đã gọi initCause chưa?”; hãy chọn cách thiết kế nhất quán, ưu tiên constructor nhận cause khi tạo một ngoại lệ wrapper mới.

Một số lớp ngoại lệ có thể override `getCause()` vì lý do tương thích với cơ chế chaining cũ. Khi dùng lớp chuyên biệt, nên đọc hợp đồng của lớp đó thay vì suy đoán mọi trạng thái nội bộ từ giá trị trả về.

## 4. Self-suppression: `addSuppressed(this)` bị từ chối

Chữ ký:

```java
public final synchronized void addSuppressed(Throwable exception)
```

Hàm `addSuppressed` ghi một lỗi phụ vào danh sách của một lỗi chính. Đối tượng phụ **phải là một tham chiếu `Throwable` khác với chính đối tượng chính**.

Ví dụ sai:

```java
Exception failure = new Exception("work");
failure.addSuppressed(failure); // IllegalArgumentException
```

Đây là mã hợp lệ khi biên dịch, nhưng ném lỗi lúc thực thi. Nền tảng lỗi là **self-suppression**: một ngoại lệ vừa tự là lỗi chính, vừa tự là lỗi phụ của chính nó.

Hai ngoại lệ có **cùng message nhưng khác đối tượng** thì không phải self-suppression:

```java
Exception primary = new Exception("same text");
Exception extra = new Exception("same text");

primary.addSuppressed(extra); // Hợp lệ.
```

Sự khác nhau được xác định bằng danh tính đối tượng. `addSuppressed` **không thay thế** ngoại lệ chính, không biến `extra` thành cause và không tự ném lại `extra`. Nó chỉ bổ sung liên kết lỗi phụ.

### Ví dụ Java 17+: phân biệt self và một đối tượng khác

Lưu thành `SelfSuppressionDemo.java`:

```java
public class SelfSuppressionDemo {
    public static void main(String[] args) {
        Exception failure = new Exception("failure");

        try {
            failure.addSuppressed(failure);
        } catch (IllegalArgumentException ex) {
            System.out.println("self="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("afterSelf="
                + failure.getSuppressed().length);

        Exception secondary = new Exception("failure");
        failure.addSuppressed(secondary);

        System.out.println("count=" + failure.getSuppressed().length);
        System.out.println("sameObject="
                + (failure.getSuppressed()[0] == failure));
        System.out.println("secondaryMessage="
                + failure.getSuppressed()[0].getMessage());
    }
}
```

```bash
javac -encoding UTF-8 SelfSuppressionDemo.java
java SelfSuppressionDemo
```

Kết quả:

```text
self=IllegalArgumentException
afterSelf=0
count=1
sameObject=false
secondaryMessage=failure
```

Nhìn vào `sameObject=false` có thể thấy lỗi phụ **không phải đối tượng chính**, dù hai đối tượng có cùng thông điệp. Lần self-suppression bị từ chối không tạo phần tử mới trong danh sách.

## 5. Giá trị `null`: phân biệt chính xác ba API

Ba thao tác có chữ ký gần giống nhau nhưng hợp đồng khác nhau:

| Biểu thức | Kết quả |
| --- | --- |
| `ex.initCause(null)` | **Hợp lệ** nếu cause chưa từng được khởi tạo; tiêu thụ quyền khởi tạo |
| `new Exception("message", null)` | **Hợp lệ**; cause được xem là đã khởi tạo thành `null` |
| `ex.addSuppressed(null)` | **`NullPointerException`** |
| `ex.getCause()` khi không có/không rõ nguyên nhân | Trả `null` |
| `ex.getSuppressed()` khi không có suppressed exceptions | Trả mảng **rỗng**, không phải `null` |
| `throw null;` | Hợp lệ ở mức cú pháp nhưng khi chạy ném **`NullPointerException`** |
| `ex.setStackTrace(null)` | **`NullPointerException`**, thuộc API stack trace khác |

Lý do là mỗi API có mục đích riêng:

- **Cause `null`:** cho biết không có thông tin nguyên nhân. Có những ngoại lệ độc lập không cần cause.
- **Suppressed `null`:** không mô tả một đối tượng ngoại lệ nào. Danh sách suppressed chỉ nhận các đối tượng `Throwable` thực sự.
- **`throw null`:** câu lệnh ném cần một tham chiếu ngoại lệ; JVM tạo/ném `NullPointerException` khi biểu thức đánh giá thành `null`.

Không dùng `null` để làm dấu phân cách trong danh sách suppressed. Nếu không có lỗi phụ, để danh sách rỗng.

### Ví dụ Java 17+: xử lý `addSuppressed(null)`

Lưu thành `SuppressedNullDemo.java`:

```java
public class SuppressedNullDemo {
    public static void main(String[] args) {
        Exception primary = new Exception("main");

        try {
            primary.addSuppressed(null);
        } catch (NullPointerException ex) {
            System.out.println("nullRejected="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("empty="
                + (primary.getSuppressed().length == 0));

        try {
            throw null;
        } catch (NullPointerException ex) {
            System.out.println("throwNull="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 SuppressedNullDemo.java
java SuppressedNullDemo
```

Kết quả:

```text
nullRejected=NullPointerException
empty=true
throwNull=NullPointerException
```

Ở ví dụ trên, lỗi `NullPointerException` từ `addSuppressed(null)` là lỗi về **tham số API**. Lỗi từ `throw null` là lỗi do **câu lệnh ném một giá trị tham chiếu bằng `null`**. Cả hai là cùng một loại `NullPointerException` nhưng đến từ hai cơ chế khác nhau.

## 6. Khi tắt suppression, Java vẫn kiểm tra tham số không hợp lệ

`Throwable` có constructor bảo vệ:

```java
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
```

Một lớp ngoại lệ con có thể gọi constructor tương ứng của `Exception` để đặt `enableSuppression=false`. Khi suppression bị tắt:

- `getSuppressed()` luôn trả mảng rỗng.
- `addSuppressed(other)` với **đối tượng khác hợp lệ** không ghi gì vào danh sách.
- **Nhưng** `addSuppressed(null)` vẫn ném `NullPointerException`.
- **Và** `addSuppressed(this)` vẫn ném `IllegalArgumentException`.
- Cờ `enableSuppression` và `writableStackTrace` là hai thiết lập độc lập; tắt suppression không tự yêu cầu stack trace bị tắt.

Đây là một điểm tinh tế trong Javadoc: khi suppression bị vô hiệu hóa, `addSuppressed` chỉ không lưu dữ liệu, **không bỏ qua bước xác thực đối số**.

### Ví dụ Java 17+: kiểm tra chế độ suppression disabled

Lưu thành `DisabledSuppressionDemo.java`:

```java
public class DisabledSuppressionDemo {
    static final class NoSuppressionException extends Exception {
        NoSuppressionException(String message) {
            super(message, null, false, true);
        }
    }

    public static void main(String[] args) {
        NoSuppressionException primary =
                new NoSuppressionException("main");

        primary.addSuppressed(new Exception("ignored"));
        System.out.println("count=" + primary.getSuppressed().length);

        try {
            primary.addSuppressed(null);
        } catch (NullPointerException ex) {
            System.out.println("null="
                    + ex.getClass().getSimpleName());
        }

        try {
            primary.addSuppressed(primary);
        } catch (IllegalArgumentException ex) {
            System.out.println("self="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("finalCount="
                + primary.getSuppressed().length);
    }
}
```

```bash
javac -encoding UTF-8 DisabledSuppressionDemo.java
java DisabledSuppressionDemo
```

Kết quả:

```text
count=0
null=NullPointerException
self=IllegalArgumentException
finalCount=0
```

Lớp `NoSuppressionException` tắt danh sách suppressed ở constructor. Việc thêm một ngoại lệ hợp lệ không có tác dụng; hai đối số không hợp lệ vẫn bị từ chối. Trong triển khai nghiệp vụ thông thường, **không nên tắt suppression chỉ để giảm dung lượng log**, bởi việc này làm mất thông tin về các lỗi cleanup.

## 7. Vì sao self-suppression có thể xuất hiện trong `try-with-resources`?

Thông thường, thân `try` và `close()` tạo **hai đối tượng ngoại lệ độc lập**. Java giữ lỗi thân làm primary và gọi `primary.addSuppressed(closeFailure)`. Nếu lập trình viên cố tình dùng lại **chính cùng một đối tượng `Throwable`** ở cả hai nơi, lời gọi nội bộ có thể trở thành:

```java
Throwable primary = shared;
Throwable closeFailure = shared;

primary.addSuppressed(closeFailure); // Self-suppression!
```

Đây là mô hình giải thích, không phải mã sinh ra theo từng dòng giống hệt bởi mọi trình biên dịch. Khi `primary == closeFailure`, `addSuppressed` bị từ chối bằng `IllegalArgumentException`. Như vậy một lỗi về **cách tổ chức đối tượng ngoại lệ** có thể làm thay đổi ngoại lệ cuối cùng thoát ra thay vì giữ lỗi chính theo quy tắc thông thường.

### Chương trình Java 17+: cố ý ném lại cùng một đối tượng

Lưu thành `SameThrowableResourceDemo.java`:

```java
public class SameThrowableResourceDemo {
    static final IllegalStateException SHARED =
            new IllegalStateException("shared failure");

    static class BadResource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close");
            throw SHARED;
        }
    }

    public static void main(String[] args) {
        try (BadResource resource = new BadResource()) {
            System.out.println("body");
            throw SHARED;
        } catch (IllegalArgumentException ex) {
            System.out.println("observed="
                    + ex.getClass().getSimpleName());
            System.out.println("causeIsShared=" + (ex.getCause() == SHARED));
        }
    }
}
```

```bash
javac -encoding UTF-8 SameThrowableResourceDemo.java
java SameThrowableResourceDemo
```

Kết quả theo quy tắc `Throwable.addSuppressed` trên JDK 17+:

```text
body
close
observed=IllegalArgumentException
causeIsShared=true
```

Quá trình:

1. Thân `try` ném `SHARED`.
2. Java gọi `close()` và `close()` cũng ném **chính tham chiếu `SHARED`**.
3. Logic giữ ngoại lệ chính cố gắn `SHARED` vào danh sách suppressed của **chính `SHARED`**.
4. `addSuppressed` ném `IllegalArgumentException` do self-suppression. Trong JDK thông thường, ngoại lệ `IllegalArgumentException` ấy giữ `SHARED` làm cause.
5. `catch (IllegalArgumentException)` bắt lỗi mới. Đây không phải kết quả mong muốn của một cơ chế cleanup bình thường.

**Ví dụ này là bài học về trường hợp cần tránh**, không phải hướng dẫn xây lớp tài nguyên. Dùng một đối tượng exception toàn cục và ném đi ném lại giữa nhiều tầng có thể gây trace cũ, cause/suppressed khó quản lý và các vấn đề đa luồng.

### Cách đúng: tạo hai đối tượng lỗi riêng

Lưu thành `DistinctResourceFailureDemo.java`:

```java
public class DistinctResourceFailureDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IllegalStateException("body failed");
        } catch (IllegalStateException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("count=" + ex.getSuppressed().length);
            System.out.println("suppressed="
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 DistinctResourceFailureDemo.java
java DistinctResourceFailureDemo
```

Kết quả:

```text
primary=body failed
count=1
suppressed=close failed
```

Lỗi thân và lỗi đóng là hai đối tượng mới, vì vậy `try-with-resources` có thể giữ lỗi thân làm primary và đính kèm lỗi đóng như dự kiến.

## 8. Nguyên tắc chọn ngoại lệ chính khác với tự tạo quan hệ cause

Trong `try-with-resources`, ngoại lệ đã tồn tại từ thân `try` được ưu tiên và ngoại lệ `close()` sau đó có thể bị suppress. Điều này không có nghĩa lỗi đóng **gây ra** lỗi thân.

Ngược lại, khi một tầng service bắt `IOException` rồi tạo `ServiceException`, ngoại lệ tầng thấp mới là **nguyên nhân** theo chuỗi cause của lỗi wrapper.

```java
try {
    repositoryOperation();
} catch (IOException ex) {
    throw new ServiceException("Unable to process request", ex);
}
```

Đây là **đoạn minh họa**, giả định `repositoryOperation() throws IOException` và `ServiceException` có constructor nhận cause. Đối tượng `ex` là cause của ngoại lệ mới; nó **không phải suppressed** theo mặc định.

Một thiết kế có thể chứa cả hai quan hệ:

```text
ServiceException("request failed")
    └── cause → IOException("read failed")
                   └── suppressed[0] → IOException("close failed")
```

Khi đọc log, cần xét cause chain và suppressed ở từng tầng. Không nên làm phẳng tất cả thành một message rồi đánh mất sự khác biệt giữa **lỗi gây ra lỗi khác** và **lỗi phát sinh phụ trong cleanup**.

## 9. `getSuppressed()` trả mảng độc lập và có thể rỗng

Với `Throwable.getSuppressed()`:

- Nếu chưa có ngoại lệ bị suppress, trả về mảng **rỗng**.
- Nếu suppression bị tắt, cũng trả về mảng **rỗng**, kể cả khi đã thử thêm một ngoại lệ hợp lệ.
- Mảng trả về là dữ liệu để đọc; **thay đổi các phần tử trên mảng trả về không sửa danh sách suppressed đang lưu**.
- Các phần tử mảng là **tham chiếu tới các đối tượng `Throwable` thực tế**, không phải bản sao sâu của từng đối tượng. Các đối tượng lỗi liên quan vẫn có thể có cause/stack trace riêng.

Đoạn minh họa trong một phương thức:

```java
Exception root = new Exception("root");
Exception first = new Exception("first");
root.addSuppressed(first);

Throwable[] snapshot = root.getSuppressed();
snapshot[0] = new Exception("replacement");

System.out.println(root.getSuppressed()[0].getMessage());
// In ra: first
```

Không được dùng `getSuppressed() == null` để kiểm tra không có lỗi phụ; API công bố mảng, nên dùng `getSuppressed().length == 0`.

Nếu muốn lưu danh sách thông tin lỗi vào cấu trúc khác, cần phân biệt **sao chép mảng tham chiếu** với **sao chép các đối tượng Throwable**. Không nên tự sửa dữ liệu chẩn đoán của các ngoại lệ đang được chia sẻ chỉ để đổi cách hiển thị log.

## 10. Có thể có cùng một đối tượng suppressed nhiều lần không?

`addSuppressed` cấm **một ngoại lệ suppress chính nó**, nhưng Javadoc không đặt yêu cầu tự động khử trùng lặp theo message hoặc danh tính đối với **các đối tượng khác với chủ thể**.

Ví dụ:

```java
Exception primary = new Exception("primary");
Exception sameExtra = new Exception("extra");

primary.addSuppressed(sameExtra);
primary.addSuppressed(sameExtra);

System.out.println(primary.getSuppressed().length); // 2
```

Đây là đoạn minh họa trong phương thức. Hai lần thêm cùng một đối tượng **khác với primary** được ghi thành hai phần tử theo thứ tự gọi. Điều đó không gây lỗi self-suppression vì `sameExtra != primary`.

Tuy nhiên, lặp cùng một lỗi phụ trong danh sách có thể làm log khó đọc và gây hiểu nhầm là hai lần lỗi độc lập. Nếu tự xây bộ thu thập lỗi, hãy quyết định rõ chính sách khử lặp bằng **danh tính** hay **sự kiện**, không dựa đơn giản vào việc hai thông điệp lỗi bằng nhau.

## 11. Cause khác `null` nhưng truy cập không an toàn vẫn gây NPE

Một lỗi thực hành rất phổ biến:

```java
Exception ex = new Exception("independent");
System.out.println(ex.getCause().getMessage()); // NPE khi cause == null
```

Đây là ví dụ **cố ý gây lỗi lúc chạy**. `getCause()` có thể trả `null`; phải kiểm tra trước khi dereference.

Mẫu hợp lệ:

```java
Throwable cause = ex.getCause();
if (cause == null) {
    System.out.println("No known cause");
} else {
    System.out.println(cause.getMessage());
}
```

Trong ví dụ sau, `ex` đã tồn tại trong scope. Với `getSuppressed()` thì không cần kiểm tra array `null` theo hợp đồng chuẩn, nhưng vẫn phải kiểm tra **độ dài** trước khi truy cập phần tử đầu:

```java
Throwable[] extras = ex.getSuppressed();
if (extras.length > 0) {
    System.out.println(extras[0].getMessage());
}
```

Không nên viết `ex.getSuppressed()[0]` mà không kiểm tra nếu ứng dụng có thể không tạo lỗi phụ. Những mã như vậy thường làm phát sinh `ArrayIndexOutOfBoundsException` trong lúc đang xử lý một ngoại lệ khác, che khuất lỗi cần phân tích.

## 12. Thiết kế exception mới: chọn constructor nhận cause thay vì `initCause` muộn

Khi có quyền thiết kế một lớp ngoại lệ riêng, cách thường rõ ràng nhất là khai báo constructor nhận cause:

```java
class DataLoadException extends Exception {
    DataLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là **lớp hợp lệ**, không chứa `main` để chạy độc lập. Khi dùng:

```java
throw new DataLoadException("Cannot load configuration", original);
```

Ngoại lệ mới đã có cause chính xác từ lúc tạo. Không cần gọi thêm `initCause()` và cũng tránh nguy cơ vô tình khởi tạo hai lần.

`initCause()` vẫn hữu ích khi bạn buộc phải tích hợp một kiểu ngoại lệ cũ không cung cấp constructor nhận cause. Nếu dùng, hãy gọi **ngay sau khi khởi tạo** và chỉ một lần:

```java
LegacyException wrapper = new LegacyException("operation failed");
wrapper.initCause(original);
throw wrapper;
```

Đây là **mẫu minh họa** với `LegacyException` không có constructor cause, có chữ ký `initCause` phù hợp, và `original` là một `Throwable` khác với `wrapper`. Việc trì hoãn gắn cause cho đến sau khi ngoại lệ đã đi qua nhiều tầng làm trạng thái lỗi khó đoán hơn.

**Không chuyển một ngoại lệ thành cause của chính nó** để “giữ nguyên stack trace”. Nếu cần ném lại đúng lỗi đó, dùng `throw original;` (khi kiểu checked phù hợp với chữ ký phương thức). Nếu cần thêm ngữ cảnh, tạo **wrapper khác** và truyền `original` làm cause.

## 13. Các trường hợp khác về chu trình tham chiếu

Java cấm *self-cause trực tiếp* qua `initCause(this)` và *self-suppression trực tiếp* qua `addSuppressed(this)`. Không nên suy ra rằng các API này **tự kiểm tra mọi chu trình tham chiếu phức tạp**.

Ví dụ, hai đối tượng được tạo chưa có cause có thể được liên kết sai thành vòng gián tiếp:

```java
Exception a = new Exception("A");
Exception b = new Exception("B");

a.initCause(b);
b.initCause(a); // Không phải b.initCause(b); tạo chu trình gián tiếp.
```

Đây là mã minh họa **không nên áp dụng**. Cả hai lời gọi đều không truyền chính đối tượng nhận vào làm tham số, nên giới hạn self-cause trực tiếp không tự bảo vệ khỏi vòng gián tiếp kiểu A → B → A. Các công cụ in lỗi có thể phát hiện và đánh dấu chu trình để tránh in vô hạn, nhưng việc tạo quan hệ không có ý nghĩa này vẫn làm thông tin điều tra kém tin cậy.

Tương tự, tránh tạo những mạng liên kết cause/suppressed qua lại giữa nhiều đối tượng nếu không có ý nghĩa thật về nguyên nhân và cleanup. Xử lý tập hợp lỗi theo mô hình **hướng từ lỗi báo cáo về nguyên nhân hoặc lỗi phụ**, không biến nó thành một đồ thị vòng tùy ý.

Nếu cần nhiều lỗi độc lập trong một bước xử lý, dùng một ngoại lệ tổng hợp với các suppressed exceptions **khác đối tượng chính**, hoặc một cấu trúc kết quả tổng hợp có chủ đích. Không tạo cause giả để xếp nhiều lỗi ngang hàng.

## 14. Những sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| `ex.initCause(ex)` | `IllegalArgumentException` do self-cause | Tạo wrapper khác và gắn `ex` làm cause của wrapper |
| `ex.addSuppressed(ex)` | `IllegalArgumentException` do self-suppression | Chỉ thêm đối tượng lỗi phụ riêng biệt |
| `ex.addSuppressed(null)` | `NullPointerException` | Không thêm gì nếu không có lỗi phụ |
| `ex.getCause() == null` rồi mặc định có thể gọi `initCause` | Có thể gặp `IllegalStateException` | Gắn cause lúc tạo hoặc theo dõi chính sách khởi tạo một lần |
| `new Exception("x", null)` rồi gọi `initCause(real)` | `IllegalStateException` | Dùng constructor với cause thật ngay từ đầu |
| `initCause(null)` rồi cố thay cause sau | `IllegalStateException` | Chỉ khởi tạo once; dùng null khi thực sự không có cause |
| Tắt suppression rồi nghĩ đối số `null`/self được bỏ qua | Vẫn gặp NPE/IAE | Luôn truyền một đối tượng lỗi hợp lệ, khác primary |
| Dùng chung một exception instance cho thân `try` và `close()` | Có thể gây self-suppression từ mã đóng tự động | Tạo ngoại lệ mới cho mỗi sự cố độc lập |
| Chỉ kiểm tra `getSuppressed() != null` | Không kiểm tra được danh sách rỗng | Kiểm tra `getSuppressed().length > 0` |
| Truy cập `getCause().getMessage()` không kiểm tra | NPE khi cause vắng mặt | Kiểm tra `getCause() != null` trước |
| Truy cập `getSuppressed()[0]` khi không có lỗi phụ | `ArrayIndexOutOfBoundsException` | Kiểm tra độ dài mảng |
| Bọc lỗi chỉ bằng message | Mất stack trace/cause/suppressed gốc | Truyền đối tượng gốc vào constructor nhận cause |
| Tạo chu trình cause gián tiếp | Dấu vết khó đọc, có thể xuất hiện cảnh báo circular reference | Giữ đồ thị nguyên nhân có ý nghĩa và không có vòng |
| Thêm cùng một lỗi phụ nhiều lần | Có thể nhân bản cùng đối tượng trong log | Xác định chính sách deduplication khi tổng hợp |

## 15. Checklist khi phân tích một lỗi có cause và suppressed

1. **Xác định đối tượng đang được ném:** primary là đối tượng nào, kiểu gì, message nào?
2. **Đọc cause:** `getCause()` có `null` không? Nếu có, đừng suy ra rằng `initCause` chưa từng chạy.
3. **Đọc suppressed:** `getSuppressed()` có bao nhiêu phần tử? Các đối tượng phụ có được tạo ở thời điểm cleanup/đóng tài nguyên không?
4. **Kiểm tra danh tính:** có phải mã đang cố thêm chính primary vào danh sách suppressed hoặc gắn nó làm cause của chính nó không?
5. **Rà soát khởi tạo:** cause được thiết lập qua constructor hay `initCause`? Có gọi nhiều lần không?
6. **Xét các giá trị null:** cause có thể không có; suppressed không được thêm `null`; các câu lệnh `throw null` và dereference `getCause()` cần xử lý riêng.
7. **Xem chế độ suppression:** lớp ngoại lệ custom có tắt suppression không? Việc thiếu suppressed trong log đôi khi do chính thiết kế lớp.
8. **Xem logic `try-with-resources`:** lỗi thân/đóng có tạo các đối tượng riêng biệt không? Có phát sinh self-suppression khi tái ném một singleton exception không?
9. **Xem ranh giới tầng:** nếu bọc lỗi, wrapper có giữ nguyên đối tượng gốc làm cause không?
10. **Chỉ log bằng thông tin đáng tin:** `printStackTrace()` có thể hiển thị cause và suppressed, nhưng thông tin liên kết do code cung cấp vẫn cần được thiết kế đúng.

## 16. Tự kiểm tra

**Câu 1.** `ex.initCause(ex)` phát sinh lỗi gì?  
**`IllegalArgumentException`** vì một đối tượng không thể là cause trực tiếp của chính nó.

**Câu 2.** `ex.addSuppressed(ex)` phát sinh lỗi gì?  
**`IllegalArgumentException`** vì self-suppression.

**Câu 3.** `ex.initCause(null)` có hợp lệ không? Có thể gọi lại `initCause(real)` sau đó không?  
**Hợp lệ nếu trước đó cause chưa được khởi tạo. Không gọi lại được**: lần đầu đã tiêu thụ quyền khởi tạo.

**Câu 4.** `new Exception("x", null)` có cho phép gắn một cause khác sau này bằng `initCause` không?  
**Không.** Constructor nhận cause đã khởi tạo cause thành `null`.

**Câu 5.** `ex.addSuppressed(null)` ném gì?  
**`NullPointerException`**. Danh sách rỗng được biểu diễn bằng mảng rỗng từ `getSuppressed()`, không bằng phần tử null.

**Câu 6.** Khi `enableSuppression=false`, gọi `addSuppressed(null)` có bị từ chối không?  
**Có**, vì API vẫn xác thực đối số.

**Câu 7.** Hai ngoại lệ khác đối tượng nhưng cùng message có thể tạo quan hệ cause hoặc suppressed không?  
**Có** khi quan hệ đó có ý nghĩa: điều bị cấm ở đây là đối tượng tự liên kết với chính nó, không phải trùng message.

**Câu 8.** Trong `try-with-resources`, thân và `close()` cùng ném một singleton exception instance có thể gây lỗi gì?  
**Self-suppression**, có thể dẫn tới `IllegalArgumentException` khi Java cố gắn ngoại lệ vào chính nó.

**Câu 9.** `getSuppressed() == null` có phải cách kiểm tra không có lỗi phụ?  
**Không.** Phương thức trả mảng, thường rỗng nếu không có lỗi phụ.

**Câu 10.** `getCause() == null` có chứng minh cause chưa từng được khởi tạo không?  
**Không.** Cause có thể đã được đặt thành `null` qua constructor hoặc `initCause(null)`.

## Tài liệu tham khảo

- [Java SE 21 — `Throwable.initCause()`, `getCause()`, `addSuppressed()`, `getSuppressed()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html).
- [JLS Java SE 21 — §14.20.3: `try-with-resources` và suppressed exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS Java SE 21 — §14.18: `throw` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.18).

**Ghi nhớ:** Java cho phép cause bằng `null` nhưng chỉ cho phép khởi tạo cause **một lần**; `getCause()==null` không chứng minh trạng thái còn được khởi tạo. Trong khi đó, suppressed exception phải là một đối tượng `Throwable` **khác chính đối tượng chứa nó và khác `null`**. Tuân thủ những giới hạn này giúp bảo toàn thông tin lỗi gốc và tránh tạo ra ngoại lệ mới ngay trong quá trình xử lý lỗi.
