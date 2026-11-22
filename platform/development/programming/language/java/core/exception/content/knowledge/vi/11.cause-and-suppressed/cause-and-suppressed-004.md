# Suppressed exception và quan hệ với try-with-resources trong Java

Trong Java, một thao tác có thể ném **nhiều ngoại lệ liên quan tới cùng một lần thực hiện**: công việc chính thất bại, rồi thao tác đóng tài nguyên cũng thất bại. Nếu chương trình chỉ giữ ngoại lệ sau cùng, thông tin về lỗi ban đầu có thể bị che khuất. Cơ chế **suppressed exceptions** của `Throwable` cho phép gắn những ngoại lệ phụ vào **ngoại lệ chính (primary exception)** mà không làm mất đối tượng lỗi ban đầu.

`try-with-resources` là nơi cơ chế này thường xuất hiện: Java tự động đóng các tài nguyên `AutoCloseable`. Khi thân `try` đang ném exception A và `close()` lại ném exception B, **A thường tiếp tục là exception chính; B được lưu trong `A.getSuppressed()`**. Đây là điểm khác biệt quan trọng so với một khối `finally` thông thường có thể ném B và che mất A.

Bài này đi từ khái niệm, API của `Throwable`, thứ tự khởi tạo/đóng, các tình huống một hoặc nhiều tài nguyên thất bại, `getCause()` so với `getSuppressed()`, việc vô hiệu hóa suppression, đến cách kiểm thử Java 17+.

## 1. Vì sao cần suppressed exception?

Hình dung việc ghi tệp:

1. Mở kết nối hoặc tệp.
2. Thực hiện thao tác ghi.
3. Thao tác ghi ném `IOException("write failed")`.
4. Chương trình cố đóng tài nguyên.
5. `close()` ném `IOException("close failed")`.

Cả hai lỗi đều cần được biết. **Lỗi ghi** giải thích vì sao tác vụ chính thất bại; **lỗi đóng** có thể gợi ý tài nguyên không được giải phóng đúng, hoặc thao tác flush/close chưa hoàn tất.

Nếu dùng cleanup thủ công thiếu bảo vệ:

```java
try {
    writeData();
} finally {
    closeResource();
}
```

đây là **mã khung minh họa**, chưa có định nghĩa hai phương thức. Khi `writeData()` ném lỗi A và `closeResource()` ném B, theo quy tắc hoàn tất của `finally`, **B có thể thay thế A** như exception lan ra ngoài. Java không tự nối A thành cause hoặc suppressed của B trong cấu trúc `try/finally` đó.

Nếu dùng `try-with-resources`:

```java
try (SomeResource resource = open()) {
    resource.writeData();
}
```

đây cũng là **mã khung**, với `SomeResource` triển khai `AutoCloseable`. Khi thân `try` ném A và `close()` ném B, cơ chế do Java thực hiện sẽ cố giữ **A là primary** và gắn **B vào danh sách suppressed của A**, với những điều kiện cụ thể như suppression của primary không bị vô hiệu hóa.

**Suppressed không có nghĩa “lỗi không đáng quan tâm”.** Nó chỉ mô tả quan hệ ưu tiên khi nhiều lỗi cùng xuất hiện; hệ thống vẫn cần kiểm tra, ghi nhận và xử lý những ảnh hưởng của lỗi cleanup.

## 2. Ba loại thông tin phải phân biệt: primary, cause và suppressed

| Khái niệm | Ý nghĩa | Cách truy cập |
| --- | --- | --- |
| **Primary exception** | Ngoại lệ chính đang được ném hoặc được handler nhận trong một tình huống | Chính biến exception ở `catch`, chẳng hạn `e` |
| **Cause** | Ngoại lệ là nguyên nhân dẫn đến một ngoại lệ khác, thường khi một tầng bọc/chuyển loại lỗi | `e.getCause()` |
| **Suppressed exception** | Ngoại lệ phụ được lưu cùng primary thay vì thay thế nó | `e.getSuppressed()` |

Ví dụ nghiệp vụ:

- Repository ném `IOException` do không đọc được tệp.
- Service tạo `ConfigurationException("Không thể khởi động", ioError)`. `ioError` trở thành **cause** của wrapper.
- Khi resource được đóng, `close()` ném lỗi khác; nếu lỗi đó được suppressed vào `ioError`, nó nằm trong **`ioError.getSuppressed()`**, không tự động chuyển sang danh sách suppressed của wrapper.
- Caller có thể phải theo cả **chuỗi cause** lẫn **các suppressed exception trên từng node** để chẩn đoán đầy đủ.

Cause và suppressed không phải hai tên gọi cho cùng một mảng. Một `Throwable` có thể có **một cause** và **nhiều suppressed exceptions**, mỗi object lại có stack trace riêng.

## 3. API của `Throwable`: `getSuppressed()` và `addSuppressed()`

Các phương thức quan trọng:

```java
public final synchronized void addSuppressed(Throwable exception)
public final synchronized Throwable[] getSuppressed()
```

Đây là **chữ ký API minh họa** (không phải khai báo được tự viết lại trong ứng dụng). `addSuppressed` gắn một Throwable phụ vào đối tượng hiện tại; `getSuppressed` trả về **mảng các suppressed exception** đã được ghi nhận.

Những tính chất cần hiểu:

- `getSuppressed()` trả mảng, không phải một exception đơn lẻ.
- Với object không có suppressed exception, kết quả là **mảng rỗng**, không phải `null`.
- Mảng được trả về là một **bản sao**; thay phần tử của mảng đó không sửa danh sách nội bộ trên Throwable.
- Các phần tử có thứ tự theo lúc được thêm; với `try-with-resources`, thường gắn với **thứ tự đóng tài nguyên**.
- `addSuppressed(null)` không hợp lệ và ném `NullPointerException`.
- Không được tự suppress chính object vào nó: `e.addSuppressed(e)` ném `IllegalArgumentException` vì **self-suppression** không hợp lệ.
- Nếu suppression đã được vô hiệu hóa khi tạo Throwable, `addSuppressed` không lưu thêm lỗi phụ như bình thường.

Bạn hiếm khi phải tự gọi `addSuppressed` nếu đang dùng `try-with-resources` chuẩn; Java sẽ thực hiện việc liên kết khi đúng tình huống.

## 4. Ví dụ đầu tiên: tự thêm một lỗi phụ

Lưu tệp **`SuppressedApiDemo.java`**:

```java
public class SuppressedApiDemo {
    public static void main(String[] args) {
        IllegalStateException primary =
                new IllegalStateException("Lỗi thao tác");
        IllegalArgumentException cleanup =
                new IllegalArgumentException("Lỗi cleanup");

        primary.addSuppressed(cleanup);

        System.out.println("Primary: " + primary.getMessage());
        System.out.println("Số suppressed: "
                + primary.getSuppressed().length);
        System.out.println("Phụ: "
                + primary.getSuppressed()[0].getMessage());
        System.out.println("Cùng object phụ: "
                + (primary.getSuppressed()[0] == cleanup));
        System.out.println("Cause là null: "
                + (primary.getCause() == null));
    }
}
```

Biên dịch/chạy trên Java 17+:

```bash
javac -encoding UTF-8 --release 17 SuppressedApiDemo.java
java SuppressedApiDemo
```

**Stdout chính xác** với console UTF-8:

```text
Primary: Lỗi thao tác
Số suppressed: 1
Phụ: Lỗi cleanup
Cùng object phụ: true
Cause là null: true
```

Kết quả cho thấy danh sách suppressed chứa **đúng object `cleanup`** (không có đối tượng mới được tạo chỉ để suppress), và không liên quan tới `getCause()`. `getMessage()` của primary vẫn là `"Lỗi thao tác"`.

Nếu muốn đọc nhiều lỗi phụ, hãy **duyệt mảng** từ `getSuppressed()`. Trong ứng dụng thật, không giả định luôn có phần tử `[0]`; cần kiểm tra độ dài trước khi lấy chỉ số.

## 5. `try-with-resources` tự động kết nối primary và suppressed

`try-with-resources` dùng dạng:

```java
try (Resource resource = open()) {
    work(resource);
} catch (SomeException e) {
    handle(e);
}
```

Đây là **khung minh họa**, các kiểu và phương thức chưa định nghĩa. Giả sử `Resource implements AutoCloseable`, quá trình là:

1. Đánh giá biểu thức khởi tạo resource.
2. Nếu thành công, chạy thân `try`.
3. Khi rời thân `try`, Java **cố gọi `close()`** trên resource khác `null`.
4. Nếu thân `try` đã ném A, lúc `close()` ném B, Java **gắn B vào A bằng cơ chế suppressed** nếu việc thêm lỗi được hỗ trợ.
5. Sau cleanup, exception chính được chuyển đến handler thích hợp; `catch` gắn trực tiếp với câu lệnh đó chạy **sau khi đã cố đóng tài nguyên**.

Nếu thân `try` kết thúc bình thường mà `close()` ném B, thì **B không có A để bám vào** và trở thành exception chính.

Điểm cốt lõi là `try-with-resources` không cố “bắt hết lỗi” để chương trình thành công. Nó quản lý tài nguyên và **bảo toàn đường lan truyền ngoại lệ** theo một cấu trúc ít dễ mắc lỗi hơn `finally` tự viết.

## 6. Ví dụ đầy đủ: thân `try` lỗi, `close()` cũng lỗi

Lưu **`PrimaryAndSuppressedDemo.java`**:

```java
public class PrimaryAndSuppressedDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close() chạy");
            throw new IllegalStateException("Không đóng được");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Thực hiện công việc");
            throw new IllegalArgumentException("Dữ liệu không hợp lệ");
        } catch (IllegalArgumentException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Số suppressed: "
                    + e.getSuppressed().length);
            for (Throwable secondary : e.getSuppressed()) {
                System.out.println("Suppressed: "
                        + secondary.getMessage());
            }
        }
        System.out.println("Sau try/catch");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 PrimaryAndSuppressedDemo.java
java PrimaryAndSuppressedDemo
```

**Stdout chính xác:**

```text
Thực hiện công việc
close() chạy
Primary: Dữ liệu không hợp lệ
Số suppressed: 1
Suppressed: Không đóng được
Sau try/catch
```

Lý giải:

- `IllegalArgumentException` là lỗi A từ thân `try`.
- `Resource.close()` chạy khi rời block và ném `IllegalStateException` B.
- Java không thay A bằng B. B được thêm vào `A.getSuppressed()`.
- `catch (IllegalArgumentException e)` nhận **A**, không phải B.
- Lệnh sau cấu trúc chạy vì handler đã kết thúc bình thường.

Nếu chỉ có handler `catch (IllegalStateException e)` ở cùng tầng, nó **không** bắt A chỉ vì A có B kiểu `IllegalStateException` trong danh sách suppressed. Việc chọn `catch` dựa trên **kiểu exception chính đang được ném**, không dựa trên các suppressed exceptions.

## 7. Nếu chỉ `close()` thất bại thì sao?

Nếu thân `try` chạy bình thường và `close()` ném exception, lỗi đóng trở thành lỗi chính của câu lệnh. Không có primary cũ để suppress vào.

Lưu **`CloseOnlyDemo.java`**:

```java
public class CloseOnlyDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đóng tài nguyên");
            throw new IllegalStateException("Đóng lỗi");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Thân try hoàn tất");
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
            System.out.println("Suppressed: "
                    + e.getSuppressed().length);
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 CloseOnlyDemo.java
java CloseOnlyDemo
```

**Stdout chính xác:**

```text
Thân try hoàn tất
Đóng tài nguyên
Bắt: Đóng lỗi
Suppressed: 0
```

Thao tác trong thân `try` đã hoàn thành, nhưng **toàn bộ câu lệnh try-with-resources vẫn thất bại** vì không đóng được tài nguyên. Không nên báo thành công cuối cùng nếu hợp đồng thao tác đòi hỏi đóng hoặc flush thành công.

Đây là một sai lầm về thuật ngữ phổ biến: “exception phát sinh trong close luôn là suppressed”. **Không đúng**; nó chỉ là suppressed nếu có một exception đang được ưu tiên giữ lại (hoặc có một lỗi đóng xảy ra trước trong quá trình đóng nhiều resource).

## 8. Nhiều tài nguyên: thứ tự khởi tạo và đóng

Với:

```java
try (Resource first = open("A");
     Resource second = open("B");
     Resource third = open("C")) {
    performWork();
}
```

đây là **mã khung minh họa**. Java đánh giá các phần khai báo tài nguyên **từ trái sang phải**: A, B, C. Khi rời block, tài nguyên đã khởi tạo thành công được cố đóng **từ phải sang trái**: C, B, A.

Nếu thân `try` ném exception A0 và cả ba `close()` đều ném C0, B0, A1, thì A0 vẫn là primary; các lỗi đóng có thể được thêm suppressed theo **C0 → B0 → A1**.

Nếu thân `try` không ném lỗi, nhưng `close()` của C ném C0 trước, C0 trở thành primary. Khi `close()` của B rồi A tiếp tục ném, chúng có thể được suppressed **vào C0**.

Không nhầm thứ tự trong phần khai báo với thứ tự trong `getSuppressed()`; thứ tự suppressed gắn với các lỗi phát sinh thực tế trong quá trình dọn dẹp.

## 9. Ví dụ: nhiều lỗi đóng trong khi thân `try` đã có primary

Lưu **`MultipleCloseFailuresDemo.java`**:

```java
public class MultipleCloseFailuresDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
            throw new IllegalStateException("Lỗi đóng " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B");
             Resource c = new Resource("C")) {
            System.out.println("Trong try");
            throw new IllegalArgumentException("Lỗi xử lý");
        } catch (IllegalArgumentException e) {
            System.out.println("Chính: " + e.getMessage());
            System.out.println("Số phụ: " + e.getSuppressed().length);
            for (Throwable secondary : e.getSuppressed()) {
                System.out.println("Phụ: " + secondary.getMessage());
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 MultipleCloseFailuresDemo.java
java MultipleCloseFailuresDemo
```

**Stdout chính xác:**

```text
Mở A
Mở B
Mở C
Trong try
Đóng C
Đóng B
Đóng A
Chính: Lỗi xử lý
Số phụ: 3
Phụ: Lỗi đóng C
Phụ: Lỗi đóng B
Phụ: Lỗi đóng A
```

Mỗi `Resource.close()` ném lỗi, nhưng Java vẫn cố đóng tất cả tài nguyên đã khởi tạo thành công. Lỗi của C, B, A được giữ lại thay vì thay thế primary từ thân `try`.

Điều này **không tự chứng minh cleanup thành công**. Việc `close()` đã được gọi không có nghĩa mỗi resource đã được giải phóng hoàn toàn. Suppressed exception chính là bằng chứng cần xem xét thêm trạng thái tài nguyên.

## 10. Nếu thân `try` thành công nhưng hai `close()` cùng thất bại

Đây là trường hợp khó hơn: không có lỗi chính từ thân `try`. Java đóng tài nguyên sau cùng trước, và **ngoại lệ đóng đầu tiên được ném sẽ là primary**. Những lỗi đóng tiếp theo sẽ được giữ làm suppressed vào primary đó.

Ví dụ đầy đủ **`CloseBecomesPrimaryDemo.java`**:

```java
public class CloseBecomesPrimaryDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
            throw new IllegalStateException("Lỗi " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("Work thành công");
        } catch (IllegalStateException e) {
            System.out.println("Primary: " + e.getMessage());
            for (Throwable secondary : e.getSuppressed()) {
                System.out.println("Suppressed: "
                        + secondary.getMessage());
            }
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 CloseBecomesPrimaryDemo.java
java CloseBecomesPrimaryDemo
```

**Stdout chính xác:**

```text
Work thành công
Đóng B
Đóng A
Primary: Lỗi B
Suppressed: Lỗi A
```

B được đóng trước A, nên lỗi B trở thành primary. Khi việc đóng A cũng lỗi, lỗi A trở thành suppressed của lỗi B.

**Không có quy tắc “resource khai báo đầu tiên luôn là primary”.** Primary phụ thuộc đường thực thi: có lỗi từ thân `try` hay không, thứ tự đóng và lỗi nào xuất hiện trước khi các resource đang được quản lý được dọn dẹp.

## 11. Khởi tạo tài nguyên thất bại: cleanup vẫn có thể tạo suppressed

Với nhiều resource, một constructor hoặc factory ở vị trí sau có thể ném exception trước khi thân `try` bắt đầu. Java vẫn cố đóng những resource **đã khởi tạo thành công trước đó**.

Giả sử:

- Resource A đã mở thành công.
- Đang tạo resource B thì constructor ném `IllegalArgumentException`.
- Java cố đóng A.
- `A.close()` ném `IllegalStateException`.

Lỗi khởi tạo B có thể là **primary**, còn lỗi đóng A là **suppressed** của lỗi khởi tạo B. Thân `try` không được thực thi.

Ví dụ Java 17 **`InitializationSuppressedDemo.java`**:

```java
public class InitializationSuppressedDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Khởi tạo " + name);
            if ("B".equals(name)) {
                throw new IllegalArgumentException("Không tạo được B");
            }
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
            throw new IllegalStateException("Không đóng được " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("Không chạy đến đây");
        } catch (IllegalArgumentException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Số suppressed: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 InitializationSuppressedDemo.java
java InitializationSuppressedDemo
```

**Stdout chính xác:**

```text
Khởi tạo A
Khởi tạo B
Đóng A
Primary: Không tạo được B
Số suppressed: 1
Suppressed: Không đóng được A
```

A được tạo thành công và do cấu trúc try-with-resources quản lý. B ném lỗi trong constructor, nên B **không được xem là resource khởi tạo thành công để Java gọi `close()`**, nhưng A vẫn được đóng.

Quy tắc này rất hữu ích cho những chuỗi mở file, stream, socket hoặc tài nguyên kết nối: lỗi ở tài nguyên sau không khiến các tài nguyên trước bị bỏ quên.

## 12. Tài nguyên `null` có tạo suppressed exception không?

Trong try-with-resources, resource specification có thể chứa tham chiếu `null`. Nếu resource là `null`, Java **không gọi `close()` trên tham chiếu đó**. Bởi vậy resource `null` không tự tạo lỗi đóng và không bổ sung suppressed exception chỉ vì bằng `null`.

Lưu **`NullResourceSuppressedDemo.java`**:

```java
public class NullResourceSuppressedDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("Lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (Resource missing = null) {
            throw new IllegalArgumentException("Lỗi trong try");
        } catch (IllegalArgumentException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed: "
                    + e.getSuppressed().length);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 NullResourceSuppressedDemo.java
java NullResourceSuppressedDemo
```

**Stdout chính xác:**

```text
Primary: Lỗi trong try
Suppressed: 0
```

Mặc dù `Resource.close()` được viết để luôn ném exception, method đó không được gọi vì biến tài nguyên `missing` là `null`. Ngoại lệ chính vẫn là `IllegalArgumentException` từ thân `try`, với danh sách suppressed rỗng.

Phân biệt: **đọc hoặc gọi method trên resource `null` ở thân `try` vẫn có thể ném `NullPointerException`**. Điều try-with-resources làm an toàn ở đây là bỏ qua *lời gọi close tự động* cho tham chiếu `null`, không phải làm mọi thao tác trên `null` trở nên hợp lệ.

## 13. `getCause()` khác `getSuppressed()` trong ứng dụng thực

Xét hệ thống:

- Thao tác mạng ném `IOException`.
- Khi đóng stream, `close()` cũng ném `IOException` khác; lỗi đóng bị suppressed vào lỗi mạng.
- Tầng dịch vụ bọc lỗi mạng bằng `ServiceException` có `cause` là exception mạng.

Khi caller nhận `ServiceException`:

```text
ServiceException                  (wrapper)
└── cause -> IOException A        (lỗi chính ở tầng I/O)
    └── suppressed -> IOException B   (lỗi đóng stream)
```

**Không phải** `ServiceException.getSuppressed()` sẽ tự chứa B. B nằm trên object A, được wrapper lưu làm cause.

Ví dụ **`CauseVsSuppressedDemo.java`**:

```java
import java.io.IOException;

public class CauseVsSuppressedDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void repository() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        }
    }

    static void service() {
        try {
            repository();
        } catch (IOException e) {
            throw new IllegalStateException("Service failed", e);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IllegalStateException wrapper) {
            Throwable cause = wrapper.getCause();
            System.out.println("Wrapper: " + wrapper.getMessage());
            System.out.println("Cause: " + cause.getMessage());
            System.out.println("Wrapper suppressed: "
                    + wrapper.getSuppressed().length);
            System.out.println("Cause suppressed: "
                    + cause.getSuppressed().length);
            System.out.println("Lỗi phụ: "
                    + cause.getSuppressed()[0].getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 CauseVsSuppressedDemo.java
java CauseVsSuppressedDemo
```

**Stdout chính xác:**

```text
Wrapper: Service failed
Cause: read failed
Wrapper suppressed: 0
Cause suppressed: 1
Lỗi phụ: close failed
```

Cần xem **cả chuỗi cause và danh sách suppressed tại những object liên quan**. Chỉ gọi `wrapper.getSuppressed()` rồi kết luận “không có lỗi cleanup” sẽ bỏ sót B trên object `cause`.

## 14. `printStackTrace()` hiển thị suppressed như thế nào?

`Throwable.printStackTrace()` in ra mô tả exception và các stack frame. Khi có suppressed exceptions, dạng trình bày thông thường gồm những dòng có nhãn `Suppressed:`; quan hệ cause được thể hiện riêng dưới nhãn `Caused by:`.

Ví dụ minh họa không yêu cầu đầu ra cố định:

```java
try {
    runOperation();
} catch (Exception e) {
    e.printStackTrace();
}
```

Đây là **mã khung**; `runOperation()` phải được định nghĩa. `printStackTrace()` không đối số in ra **standard error** (`System.err`), không phải stdout, và định dạng có thể phụ thuộc JVM, số dòng nguồn, cách build và vị trí code.

Một mô tả tương tự:

```text
java.io.IOException: read failed
    at ...
    Suppressed: java.io.IOException: close failed
        at ...
```

Đây chỉ là **mẫu trực quan**, không phải stack trace thực được kiểm chứng theo số dòng. Trong API logging hỗ trợ `Throwable`, truyền trực tiếp đối tượng exception thường giúp giữ thông tin stack trace, cause và suppressed tốt hơn chỉ log `e.getMessage()`.

**`getMessage()` và `toString()` mặc định không tự liệt kê suppressed exceptions.** Nếu log chỉ chuỗi ngắn mà không giữ đối tượng Throwable hoặc các quan hệ của nó, các lỗi cleanup có thể bị mất khỏi hệ thống quan sát.

## 15. `addSuppressed()` không phải `initCause()`

Hai cơ chế giải quyết hai loại quan hệ:

```java
Throwable primary = new IllegalStateException("Work failed");
Throwable secondary = new IllegalArgumentException("Cleanup failed");

primary.addSuppressed(secondary);
```

Điều đó không làm `primary.getCause()` trở thành `secondary`. Muốn thể hiện nguyên nhân của một wrapper có thể dùng constructor chứa cause:

```java
Throwable root = new IllegalArgumentException("Input failed");
Throwable wrapper =
        new IllegalStateException("Service failed", root);
```

Đây là **các đoạn minh họa độc lập**. Một Throwable có thể có cause và nhiều suppressed. Trong cơ chế try-with-resources, việc thêm suppressed phục vụ **lỗi phụ phát sinh khi đang thực hiện cleanup**, chứ không biểu diễn rằng lỗi cleanup là nguyên nhân tạo ra lỗi công việc trước đó.

**Không dùng `initCause()` để gắn mọi lỗi đóng vào một cause chain.** Điều đó làm mờ quan hệ thời gian và nghiệp vụ; với `try-with-resources` nên đọc danh sách suppressed được tạo sẵn.

## 16. Quy tắc tự thêm suppressed: không dùng `null` và không self-suppression

`addSuppressed` có quy tắc an toàn riêng để tránh dữ liệu sai:

```java
IllegalStateException e =
        new IllegalStateException("Primary");
e.addSuppressed(new IllegalArgumentException("Cleanup"));

// e.addSuppressed(null); // Ném NullPointerException.
// e.addSuppressed(e);    // Ném IllegalArgumentException.
```

Đây là **đoạn minh họa**. Lệnh thứ hai và thứ ba được comment để không phá ví dụ. Trong ứng dụng thực, một thuật toán tự động quản lý danh sách lỗi cần tránh **gắn chính primary vào primary**, đồng thời không truyền exception `null`.

`getSuppressed()` trả mảng mới; bạn có thể lọc, duyệt và in các phần tử như dữ liệu đọc. Đừng thay phần tử trên mảng kết quả rồi kỳ vọng thay đổi danh sách suppressed nội bộ.

Nếu tự triển khai cleanup phức tạp, hãy cân nhắc API `AutoCloseable`/`try-with-resources` để tránh phải tự quản lý hàng loạt quy tắc như thứ tự thêm lỗi, exception checked/unchecked và các trạng thái thất bại khi khởi tạo.

## 17. Có thể tắt suppression trong một lớp ngoại lệ tùy chỉnh

`Throwable` có constructor protected:

```java
protected Throwable(String message, Throwable cause,
                    boolean enableSuppression,
                    boolean writableStackTrace)
```

Tham số `enableSuppression` cho phép lớp con **tắt khả năng ghi suppressed exceptions**. Đây là trường hợp ít gặp trong ứng dụng nghiệp vụ nhưng quan trọng khi suy luận chính xác: `try-with-resources` vẫn cố gắn lỗi đóng, nhưng primary đã tắt suppression thì `getSuppressed()` có thể vẫn rỗng.

Ví dụ độc lập **`SuppressionDisabledDemo.java`**:

```java
public class SuppressionDisabledDemo {
    static class NoSuppressionException extends Exception {
        NoSuppressionException(String message) {
            super(message, null, false, true);
        }
    }

    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close bị lỗi");
            throw new IllegalStateException("cleanup failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new NoSuppressionException("work failed");
        } catch (NoSuppressionException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed: "
                    + e.getSuppressed().length);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 SuppressionDisabledDemo.java
java SuppressionDisabledDemo
```

**Stdout chính xác:**

```text
close bị lỗi
Primary: work failed
Suppressed: 0
```

Dù `close()` ném `IllegalStateException`, object primary không lưu suppressed do `enableSuppression=false`. Điều đó **không làm `close()` thành công**, và không có nghĩa lỗi phụ chưa từng xảy ra.

Thực hành: đừng tắt suppression nếu ứng dụng cần chẩn đoán lỗi cleanup đồng thời. Cũng không nhầm `enableSuppression` với `writableStackTrace`; đó là hai tùy chọn khác nhau. Tắt writable stack trace ảnh hưởng các frame của exception, còn tắt suppression ảnh hưởng danh sách lỗi phụ.

## 18. Lưu ý về một lỗi rất hiếm: self-suppression khi đóng

Cơ chế suppression yêu cầu **primary và suppressed không phải cùng object**. `Throwable.addSuppressed(this)` không hợp lệ.

Đa số `close()` tạo exception mới hoặc ném một object độc lập, nhưng nếu ứng dụng cố tình **tái sử dụng đúng cùng exception instance** cả ở thân `try` và trong `close()`, thao tác liên kết suppressed có thể gặp lỗi self-suppression. Đây là một lý do nữa để **không tái sử dụng exception object toàn cục** cho các tình huống độc lập.

Trong thiết kế thông thường:

- Mỗi thất bại nên có Throwable riêng, trừ trường hợp có lý do và hợp đồng rất rõ.
- Để Java giữ primary/suppressed tự động.
- Nếu tự dùng `addSuppressed`, kiểm tra không tự thêm chính object đó và không truyền `null`.
- Khi gặp dấu vết khó hiểu từ một cơ chế đặc biệt, đừng vội giả định rằng try-with-resources đã ghi mọi lỗi được mong đợi; kiểm tra cả cách thư viện tạo và tái sử dụng exception.

Không cần triển khai self-suppression bằng ví dụ mặc định vì đây không phải cách sử dụng hợp lệ của API; hiểu giới hạn này là đủ để tránh một nhóm bug hiếm nhưng khó chẩn đoán.

## 19. Cleanup thủ công bằng `finally` có nguy cơ che lỗi chính

So sánh hai cấu trúc:

**Cleanup thủ công có thể làm mất primary:**

```java
try {
    doWork();
} finally {
    resource.close(); // Nếu cũng ném lỗi, có thể che lỗi do doWork().
}
```

**Try-with-resources giữ lỗi phụ có cấu trúc:**

```java
try (Resource resource = openResource()) {
    doWork();
}
```

Cả hai đều là **mã khung minh họa**, cần định nghĩa `Resource` và các phương thức. `finally` không tự có quy tắc ghi suppressed vào primary nếu cleanup ném exception mới. Nếu nguyên nhân lỗi chính phải được giữ, một mã `finally` ngây thơ là rủi ro.

Nếu một API cũ không triển khai `AutoCloseable`, có thể **viết adapter implements AutoCloseable** thay vì tự xử lý mọi tình huống primary/suppressed. Điều đó vẫn phải bảo đảm adapter thực sự sở hữu tài nguyên, đóng đúng đối tượng và không đóng nhầm resource dùng chung.

## 20. Ví dụ adapter cho API cũ

Một thư viện cũ có thể chỉ có phương thức `release()`:

```java
class LegacySession {
    void work() {
        throw new IllegalArgumentException("work failed");
    }

    void release() {
        throw new IllegalStateException("release failed");
    }
}

class SessionAdapter implements AutoCloseable {
    private final LegacySession session;

    SessionAdapter(LegacySession session) {
        this.session = session;
    }

    void work() {
        session.work();
    }

    @Override
    public void close() {
        session.release();
    }
}
```

Đây là **hai lớp minh họa**. Sử dụng chúng trong một phương thức:

```java
try (SessionAdapter session =
             new SessionAdapter(new LegacySession())) {
    session.work();
}
```

Khi `work()` ném `IllegalArgumentException` và `release()` ném `IllegalStateException`, try-with-resources giữ lỗi công việc là primary và gắn lỗi release suppressed (với mặc định suppression đang bật).

Đừng cố “sửa” lỗi bằng cách bắt rồi bỏ qua mọi `Exception` trong `close()`: làm vậy có thể mất dấu một sự cố cleanup thật sự. Nếu một lỗi đóng có thể được xem là vô hại theo hợp đồng, chính adapter hoặc tầng cao hơn phải quyết định dựa trên **loại lỗi cụ thể**, không bỏ qua tất cả.

## 21. Checked exception từ `AutoCloseable.close()` ảnh hưởng chữ ký phương thức

`AutoCloseable.close()` có khai báo:

```java
void close() throws Exception;
```

Đây là **chữ ký API**. Vì vậy khi kiểu tĩnh của resource là `AutoCloseable`, compiler có thể yêu cầu handler hoặc mệnh đề `throws Exception` cho việc đóng.

Ví dụ:

```java
static void run(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("Trong try");
    }
}
```

Đây là **phương thức minh họa**, dùng cú pháp Java 9+ đối với biến tham số effectively final. `throws Exception` đến từ khả năng `close()` ném checked `Exception`, ngay cả khi thân `try` không ném lỗi.

Nếu kiểu tĩnh là một lớp con override `close()` không khai báo checked exception, nghĩa vụ `throws` có thể hẹp hơn hoặc biến mất. Nếu là `java.io.Closeable`, phương thức `close()` khai báo `throws IOException`, hẹp hơn hợp đồng chung của `AutoCloseable`.

Mối liên quan với suppressed: **khi close ném checked exception**, nó có thể là primary hoặc suppressed tùy đường thực thi. Dù đang xét trường hợp suppressed, chữ ký của tài nguyên vẫn được compiler phân tích; không được bỏ qua xử lý checked exception chỉ vì bạn nghĩ lỗi đóng sẽ luôn được suppress.

## 22. Resource đóng thứ tự nào và có dừng khi một `close()` lỗi không?

Câu trả lời là: **đóng theo thứ tự ngược khai báo và vẫn cố đóng các tài nguyên còn lại đã khởi tạo thành công**.

Ví dụ ba resource A, B, C:

```text
Khởi tạo: A -> B -> C
Thân try chạy
Đóng:      C -> B -> A
```

Nếu `C.close()` ném, Java không tự bỏ qua B và A. Nó vẫn cố đóng B và A; nếu chúng cũng ném, các lỗi được giữ theo primary/suppressed như đã phân tích.

Đây là khác biệt lớn so với code tự viết như:

```java
finally {
    c.close();
    b.close();
    a.close();
}
```

Đây là **mã khung phản ví dụ**. Nếu `c.close()` ném, `b.close()` và `a.close()` có thể không bao giờ chạy, trừ khi lập trình viên tự thêm handler riêng. Try-with-resources sinh cơ chế dọn dẹp phù hợp để hạn chế tình trạng đó.

**Lưu ý:** nếu một resource bằng `null`, Java bỏ qua lời gọi close trên nó, nhưng vẫn xử lý các resource khác theo thứ tự. Nếu khởi tạo tài nguyên sau thất bại, chỉ những resource **đã khởi tạo thành công trước đó** được cố đóng.

## 23. Khi nào `getSuppressed()` rỗng?

Có nhiều lý do hợp lệ:

1. Thân `try` không có lỗi và các `close()` đều thành công.
2. Thân `try` ném lỗi, nhưng `close()` không ném lỗi nào.
3. Thân `try` ném lỗi và resource là `null` nên không có close tự động trên resource đó.
4. Thân `try` thành công, chỉ một `close()` ném: exception đóng là **primary**, không phải suppressed.
5. Một Throwable tùy chỉnh đã **tắt suppression**.
6. Một exception được tạo bên ngoài try-with-resources mà chưa có ai gọi `addSuppressed`.
7. Bạn đang kiểm tra **wrapper** trong khi các suppressed nằm trên **cause** của wrapper.

Vì vậy, **`getSuppressed().length == 0` không đủ để chứng minh không có lỗi cleanup ở toàn bộ tác vụ**. Cần biết object đang kiểm tra, đường gọi thực tế, loại resource và việc có wrapper/cause hay không.

Đây cũng là lý do nên log lỗi dưới dạng Throwable có cấu trúc, thay vì chỉ in một message rồi vứt bỏ object.

## 24. Kiểm thử lỗi đồng thời bằng Java 17

Một bài kiểm thử tốt không chỉ xác nhận “đã ném exception”; nó cần xác nhận **ngoại lệ chính đúng loại** và **lỗi cleanup đã được giữ lại**, không làm đổi primary.

Ví dụ **`SuppressedAssertionsDemo.java`**:

```java
public class SuppressedAssertionsDemo {
    static class FailingResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("cleanup");
        }
    }

    static void run() {
        try (FailingResource resource = new FailingResource()) {
            throw new IllegalArgumentException("work");
        }
    }

    public static void main(String[] args) {
        try {
            run();
            throw new AssertionError("Không có lỗi chính");
        } catch (IllegalArgumentException e) {
            if (!"work".equals(e.getMessage())) {
                throw new AssertionError("Sai primary");
            }

            Throwable[] others = e.getSuppressed();
            if (others.length != 1
                    || !(others[0] instanceof IllegalStateException)
                    || !"cleanup".equals(others[0].getMessage())) {
                throw new AssertionError("Sai suppressed");
            }

            System.out.println("PASS: primary và suppressed chính xác");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 SuppressedAssertionsDemo.java
java SuppressedAssertionsDemo
```

**Stdout chính xác:**

```text
PASS: primary và suppressed chính xác
```

Ví dụ chủ động dùng `throw new AssertionError(...)` để test thất bại, không phụ thuộc tùy chọn `-ea` của từ khóa `assert`. Trên đường đúng, có một suppressed exception kiểu `IllegalStateException` với message `"cleanup"`.

Một bộ test đầy đủ còn nên kiểm tra khi **chỉ close thất bại**, **nhiều close thất bại**, **khởi tạo resource thất bại**, và **resource bằng null**, vì những đường này có primary/suppressed khác nhau.

## 25. Những lỗi hiểu sai thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Suppressed là ngoại lệ đã bị xử lý hết và không cần quan tâm.” | Nó vẫn là một lỗi cần chẩn đoán; suppressed chỉ giữ quan hệ lỗi phụ so với primary. |
| “`close()` ném lỗi thì lỗi đó luôn là suppressed.” | Nếu thân `try` thành công, lỗi close đầu tiên có thể là primary. |
| “Có một tài nguyên thì chỉ có một lỗi cần xử lý.” | Thân `try` và `close()` có thể ném hai exception khác nhau. |
| “Khi nhiều close cùng thất bại, chỉ tài nguyên đóng cuối được giữ.” | Try-with-resources cố đóng các resource còn lại và có thể giữ các lỗi đóng dưới dạng suppressed. |
| “Suppressed chính là `getCause()`.” | Không; `getCause()` và `getSuppressed()` mô tả các quan hệ khác nhau. |
| “Wrapper tự sao chép suppressed của cause.” | Không tự động. Suppressed thường vẫn nằm trên object gốc là cause. |
| “`getSuppressed()` trả `null` khi không có lỗi.” | Nó trả **mảng rỗng**. |
| “Chỉ `try-with-resources` mới dùng được `addSuppressed()`.” | Không; `addSuppressed()` là API public của `Throwable`, nhưng Java tự dùng trong try-with-resources khi phù hợp. |
| “Gọi `e.addSuppressed(e)` là hợp lệ.” | Không. Java cấm self-suppression. |
| “`addSuppressed(null)` chỉ bị bỏ qua.” | Không; tham số `null` không hợp lệ. |
| “Nếu `getSuppressed()` rỗng thì chắc chắn không từng có lỗi close.” | Không nhất thiết: có thể close là primary, suppression tắt, hoặc lỗi nằm trên cause. |
| “`finally` và try-with-resources tự quản lý lỗi giống nhau.” | Không. `finally` ném lỗi mới có thể che primary; try-with-resources có cơ chế suppressed. |
| “Tất cả exception đều hỗ trợ ghi suppressed.” | Lớp con có thể tắt suppression bằng constructor thích hợp. |
| “`printStackTrace()` chỉ hiện message primary.” | Thông thường nó còn hiển thị frames, cause và suppressed khi có. |
| “Mọi lời gọi close đều thành công vì Java tự gọi.” | Auto-close nghĩa là Java **cố gọi**, không bảo đảm cleanup thành công. |
| “Checked exception từ close không cần xét vì sẽ luôn bị suppressed.” | Không; close có thể là primary và compiler vẫn kiểm tra hợp đồng checked exception. |

## 26. Câu hỏi tự kiểm tra

**Câu 1.** Thân `try-with-resources` ném A, `close()` ném B. Ngoại lệ chính là gì?  
**Đáp án:** Thông thường A. B được gắn suppressed vào A nếu suppression đang bật và không vi phạm quy tắc thêm suppressed.

**Câu 2.** Thân `try` chạy thành công, `close()` ném B. B nằm ở đâu?  
**Đáp án:** B là exception chính của cấu trúc; không có A trước đó để gắn suppressed.

**Câu 3.** Tài nguyên A khai báo trước B, cả hai `close()` lỗi và thân `try` không lỗi. Ngoại lệ nào là primary?  
**Đáp án:** Lỗi từ `B.close()`, vì B đóng trước; lỗi từ `A.close()` thường trở thành suppressed của lỗi B.

**Câu 4.** Thân `try` ném A, resource C đóng trước B rồi A-resource. Nếu cả ba close cùng lỗi, thứ tự suppressed theo thứ tự nào?  
**Đáp án:** Theo thứ tự lỗi phát sinh khi đóng: C, B, A-resource.

**Câu 5.** Factory resource thứ hai ném exception trong khi resource thứ nhất đã mở. Resource thứ nhất có được đóng không?  
**Đáp án:** Java cố đóng resource đã khởi tạo thành công trước đó; lỗi đóng có thể suppressed vào lỗi khởi tạo.

**Câu 6.** `getSuppressed()` trả về gì nếu không có suppressed?  
**Đáp án:** Một mảng `Throwable[]` rỗng.

**Câu 7.** Có thể gọi `primary.addSuppressed(primary)` để đánh dấu lỗi lặp không?  
**Đáp án:** Không. Self-suppression bị cấm và ném `IllegalArgumentException`.

**Câu 8.** Một wrapper có `getCause()` là exception A, còn B suppressed trên A. `wrapper.getSuppressed()` có tự chứa B không?  
**Đáp án:** Không. Cần kiểm tra `wrapper.getCause().getSuppressed()` đối với trường hợp đó.

**Câu 9.** `printStackTrace()` khác `getMessage()` như thế nào?  
**Đáp án:** `getMessage()` chỉ trả thông điệp; `printStackTrace()` in mô tả lỗi, stack frames và có thể gồm cause/suppressed, theo cách trình bày của runtime.

**Câu 10.** Nếu suppression bị tắt trên primary, `getSuppressed().length` có thể là bao nhiêu dù close lỗi?  
**Đáp án:** Có thể bằng 0, vì object không lưu suppressed được thêm như bình thường.

**Câu 11.** `finally { resource.close(); }` có thể che lỗi chính như thế nào?  
**Đáp án:** Nếu thân `try` đã ném A và `close()` trong `finally` ném B, `finally` kết thúc bất thường bằng B và B có thể thay A là exception được ném ra.

**Câu 12.** Resource `null` có tự ném lỗi đóng không?  
**Đáp án:** Không. Try-with-resources bỏ qua lời gọi `close()` tự động cho tham chiếu `null`.

**Câu 13.** Vì sao cần test cả trường hợp lỗi công việc và lỗi cleanup đồng thời?  
**Đáp án:** Để bảo đảm không làm mất primary và suppressed được giữ đúng loại, đúng thứ tự, thay vì chỉ xác nhận có một exception được ném.

**Câu 14.** Suppressed có giống kết quả rollback hoặc phục hồi tài nguyên không?  
**Đáp án:** Không. Nó chỉ bảo toàn thông tin lỗi; rollback/cleanup thành công cần cơ chế riêng.

## 27. Checklist thực hành

Khi viết hoặc review mã xử lý tài nguyên:

1. **Tài nguyên có `AutoCloseable` không?** Nếu có, ưu tiên `try-with-resources`.
2. **Thân `try` có thể ném lỗi gì?** Nhận diện primary có thể xuất hiện.
3. **`close()` có thể ném lỗi gì?** Xem hợp đồng checked/unchecked và ảnh hưởng dữ liệu.
4. **Nếu cả hai lỗi đồng thời, primary có được giữ không?** Kiểm tra `getSuppressed()` thay vì chỉ message.
5. **Nếu chỉ close lỗi, chương trình có coi đó là lỗi chính không?**
6. **Nếu nhiều resource, thứ tự khởi tạo trái→phải, đóng phải→trái có được hiểu đúng không?**
7. **Nếu một constructor/factory thất bại, những resource trước đó đã mở có được cố đóng không?**
8. **Nếu resource bằng `null`, cleanup có bỏ qua nó và vẫn đóng những resource khác không?**
9. **Có exception wrapper không?** Theo `getCause()` đến primary gốc và kiểm tra suppressed tại đúng object.
10. **Suppression có bị tắt ở custom exception không?** Nếu có, tác động chẩn đoán đã được hiểu chưa?
11. **Có mã tự gọi `addSuppressed` không?** Kiểm tra không truyền `null` hoặc chính primary.
12. **Có `finally` nào ném exception mới che lỗi chính không?**
13. **Logging có ghi object Throwable, stack trace, cause và suppressed khi cần không?**
14. **Kiểm thử đã có trường hợp simultaneous work + cleanup failures chưa?**
15. **Đã xác định chính sách sau lỗi cleanup chưa?** Dữ liệu có thể cần rollback, kết nối có thể hỏng, hoặc tác vụ không được báo thành công.

## 28. Ghi nhớ quan trọng

**Suppressed exception là một Throwable phụ được gắn vào exception chính qua `addSuppressed()` và được đọc bằng `getSuppressed()`.** Nó không phải cause, không tự làm lỗi biến mất, và không tự phục hồi tác vụ.

**`try-with-resources` là cơ chế tạo suppressed phổ biến nhất**. Khi công việc chính ném A và `close()` ném B, Java thường giữ A làm primary và đính B dưới dạng suppressed. Nếu công việc chính không ném lỗi, lỗi close đầu tiên có thể trở thành primary; với nhiều resource, những lỗi close tiếp theo được đính suppressed theo thứ tự đóng ngược khai báo.

Khi chẩn đoán, hãy xem **đúng object**: wrapper có thể chứa nguyên nhân A qua `getCause()`, trong khi suppressed B nằm trên A. Khi thiết kế, ưu tiên quản lý tài nguyên bằng `try-with-resources`, kiểm tra cả đường thất bại kép, giữ nguyên nhân gốc và không coi việc đã gọi `close()` là bảo đảm cleanup thành công.
