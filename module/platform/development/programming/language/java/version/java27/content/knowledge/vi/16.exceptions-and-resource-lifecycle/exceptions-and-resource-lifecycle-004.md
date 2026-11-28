# Cause, suppressed exception và bảo toàn ngữ cảnh lỗi

Khi một thao tác Java thất bại, thông tin quan trọng không chỉ là **“đã có lỗi”**, mà còn gồm **lỗi gốc xảy ra ở đâu, nguyên nhân trực tiếp là gì và những lỗi phụ nào đã phát sinh trong khi dọn dẹp tài nguyên**. Nếu chỉ ném ngoại lệ mới chứa một thông báo ngắn, ứng dụng có thể đánh mất thông tin cần thiết để chẩn đoán sự cố.

Trong Java 27, lớp **Throwable** cung cấp ba cơ chế trung tâm:

- **Message**: thông điệp cho biết thao tác nào thất bại.
- **Cause**: ngoại lệ đã dẫn đến ngoại lệ hiện tại, tạo thành *chuỗi nguyên nhân* (*exception chain*).
- **Suppressed exceptions**: các ngoại lệ được giữ kèm ngoại lệ chính, thường là lỗi khi đóng tài nguyên hoặc những lỗi phụ không được chọn làm lỗi chính.

Bài học tập trung vào các API Java hiện hành: **Throwable**, **getCause()**, **getSuppressed()**, **addSuppressed()**, **try-with-resources**, **AutoCloseable**, cùng cách chuyển và ghi log ngoại lệ qua nhiều tầng ứng dụng. Những ví dụ dùng Java chuẩn, không cần preview feature hay thư viện bên ngoài.

## 1. Phân biệt lỗi chính, cause và suppressed exception

Giả sử một ứng dụng thực hiện các bước:

1. Mở tệp chứa dữ liệu khách hàng.
2. Đọc và phân tích nội dung.
3. Đóng luồng đọc.
4. Thông báo kết quả cho tầng dịch vụ.

Nếu việc đọc thất bại, sau đó thao tác đóng luồng cũng thất bại, ứng dụng có **hai sự cố liên quan đến cùng một hoạt động**.

- Lỗi đọc là **primary exception**: lỗi chính làm hoạt động thất bại.
- Lỗi đóng luồng là **suppressed exception**: lỗi phát sinh trong khi dọn dẹp, được lưu lại thay vì che mất lỗi chính.

Nếu tầng dịch vụ bắt lỗi đọc và tạo một ngoại lệ mang ý nghĩa nghiệp vụ, ngoại lệ mới là lỗi ở tầng dịch vụ; lỗi đọc được gắn vào nó làm **cause**.

Sơ đồ quan hệ:

~~~mermaid
flowchart TD
    A["ServiceException: tải dữ liệu thất bại"]
    B["IOException: đọc dữ liệu thất bại"]
    C["IOException: đóng tài nguyên B thất bại"]
    D["IOException: đóng tài nguyên A thất bại"]
    A -->|"getCause()"| B
    B -.->|"getSuppressed()[0]"| C
    B -.->|"getSuppressed()[1]"| D
~~~

| Thông tin | API | Ý nghĩa |
|---|---|---|
| Thông điệp lỗi | **getMessage()** | Mô tả ngắn về lỗi hiện tại |
| Nguyên nhân trực tiếp | **getCause()** | Ngoại lệ dẫn đến ngoại lệ hiện tại, hoặc **null** |
| Các lỗi bị giữ lại | **getSuppressed()** | Mảng ngoại lệ phụ được gắn với ngoại lệ hiện tại |
| Stack trace | **getStackTrace()**, **printStackTrace()** | Dấu vết các lời gọi; thường kèm cause và suppressed khi in |
| Gắn lỗi phụ | **addSuppressed(Throwable)** | Dùng khi cần bảo toàn thêm lỗi độc lập cùng hoạt động |

**Cause và suppressed không thay thế nhau**. Cause thể hiện quan hệ “lỗi này xảy ra vì lỗi kia”. Suppressed thể hiện “trong khi xử lý hoặc dọn dẹp lỗi chính, còn xảy ra các lỗi khác mà không được bỏ qua”.

## 2. Throwable và cấu trúc thông tin ngoại lệ

Các ngoại lệ và lỗi có thể ném trong Java đều là đối tượng thuộc lớp **Throwable** hoặc lớp con của nó. Hai nhánh quen thuộc là **Exception** và **Error**; **RuntimeException** nằm trong nhánh Exception.

Những method quan trọng:

~~~java
Throwable failure = new IllegalStateException("Không thể xử lý yêu cầu");

String message = failure.getMessage();
Throwable cause = failure.getCause();
Throwable[] suppressed = failure.getSuppressed();

System.out.println(message);               // Không thể xử lý yêu cầu
System.out.println(cause);                 // null
System.out.println(suppressed.length);     // 0
~~~

Việc **getCause()** trả về **null** không khẳng định thao tác không có nguyên nhân sâu xa; chỉ có nghĩa đối tượng Throwable hiện tại không lưu một cause đã xác định.

**getSuppressed()** trả về một mảng, không phải **null**. Khi không có lỗi phụ, mảng có độ dài 0. Với một Throwable sử dụng cơ chế suppression thông thường, **addSuppressed** có thể bổ sung nhiều phần tử vào danh sách đó.

### 2.1. Chú ý về stack trace

Một Throwable thường ghi lại stack trace khi đối tượng được tạo. Stack trace thể hiện đường gọi mã nguồn và thường chứa thông tin như tên lớp, method và số dòng (tùy môi trường, cách biên dịch và cấu hình).

Stack trace của ngoại lệ mới không tự thay thế stack trace của cause. Khi được liên kết đúng, cả hai cùng xuất hiện trong kết quả chẩn đoán:

~~~java
try {
    throw new java.io.IOException("Tệp dữ liệu không đọc được");
} catch (java.io.IOException original) {
    IllegalStateException wrapped = new IllegalStateException(
        "Không thể tải báo cáo",
        original
    );

    wrapped.printStackTrace();
}
~~~

Khi in stack trace, Java thể hiện ngoại lệ ngoài cùng và phần **Caused by** cho ngoại lệ gốc. Nếu ngoại lệ có suppressed exceptions, bản in cũng thể hiện các phần **Suppressed** tương ứng.

Không nên dùng **getMessage()** làm nguồn duy nhất để điều tra lỗi: thông điệp có thể thiếu ngữ cảnh, còn cause và suppressed mới chỉ ra đường đi đầy đủ của thất bại.

## 3. Bảo toàn cause khi chuyển lỗi qua các tầng

Khi chuyển một lỗi từ tầng kỹ thuật sang tầng ứng dụng, nên **giữ cause** bằng constructor nhận **Throwable**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String loadConfiguration(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException cause) {
        throw new IllegalStateException(
            "Không thể đọc cấu hình tại " + path.getFileName(),
            cause
        );
    }
}
~~~

Trong ví dụ:

- **Files.readString** có thể ném **IOException**.
- Tầng ứng dụng tạo **IllegalStateException** với thông báo thể hiện thao tác cấp cao thất bại.
- **cause** được truyền làm tham số thứ hai, giữ nguyên ngoại lệ gốc và stack trace của nó.
- Người gọi nhận một ngoại lệ mang ý nghĩa tầng ứng dụng nhưng vẫn truy vết được vấn đề I/O.

Đối chiếu:

| Cách chuyển lỗi | Bảo toàn nguyên nhân? | Đánh giá |
|---|---|---|
| **throw cause;** | Có, giữ nguyên đối tượng và kiểu ngoại lệ | Tốt khi API có thể truyền nguyên lỗi |
| **throw new IllegalStateException("Lỗi tải cấu hình", cause);** | Có, qua **getCause()** | Tốt tại ranh giới giữa các tầng |
| **throw new IllegalStateException(cause.getMessage());** | **Không** | Làm mất liên kết cause và stack trace gốc |
| **throw new IllegalStateException("Lỗi tải cấu hình");** | **Không** | Chỉ còn thông điệp mới |
| **return null;** sau khi bắt lỗi | **Không** | Dễ biến lỗi I/O thành lỗi null khó chẩn đoán |

Không nên bắt và gói lại tất cả ngoại lệ ở mọi method. Chỉ tạo ngoại lệ mới khi cần đổi **ngữ nghĩa**, **hợp đồng API** hoặc thêm một ngữ cảnh có ích.

### 3.1. Custom exception có constructor nhận cause

Với domain exception riêng, hãy cung cấp constructor bảo toàn nguyên nhân:

~~~java
public final class ConfigurationLoadException extends RuntimeException {

    public ConfigurationLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Sử dụng:

~~~java
static String readSettings(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException cause) {
        throw new ConfigurationLoadException(
            "Đọc thiết lập thất bại",
            cause
        );
    }
}
~~~

Nếu API muốn dùng **checked exception**, có thể khai báo lớp con của **Exception** và giữ cùng mẫu **super(message, cause)**. Lựa chọn checked hay unchecked phụ thuộc hợp đồng và khả năng phục hồi của người gọi; cả hai đều hỗ trợ cause.

### 3.2. Đọc chuỗi cause

Khi nhận lỗi ở ranh giới ứng dụng, có thể duyệt các nguyên nhân:

~~~java
static void showCauseChain(Throwable error) {
    Throwable current = error;
    int level = 0;

    while (current != null) {
        System.out.println(level + ": "
            + current.getClass().getSimpleName()
            + ": " + current.getMessage());

        current = current.getCause();
        level++;
    }
}
~~~

Đây là ví dụ cho những ngoại lệ được tạo theo quy ước thông thường. Một hệ thống chẩn đoán tổng quát cần tránh vòng lặp vô hạn nếu gặp lớp Throwable tùy biến có **getCause()** trả về quan hệ bất thường. Trong ứng dụng thực, ghi log nguyên Throwable thường đủ để xem cả cause và suppressed mà không cần tự viết code duyệt cây.

## 4. initCause dùng khi nào?

**Throwable.initCause(Throwable)** cho phép gắn cause cho một Throwable đã được tạo nhưng **chưa** thiết lập nguyên nhân. Cơ chế này vẫn tồn tại và hoạt động trên Java 27, chủ yếu phục vụ các kiểu ngoại lệ không có constructor nhận cause.

~~~java
IOException original = new IOException("Lỗi đọc tệp");

IllegalStateException wrapper =
    new IllegalStateException("Không thể nhập dữ liệu");

wrapper.initCause(original);

System.out.println(wrapper.getCause() == original); // true
~~~

Các giới hạn:

- **initCause** được phép gọi tối đa **một lần** cho mỗi đối tượng.
- Không được đặt một Throwable làm cause của chính nó.
- Nếu Throwable được tạo bằng constructor nhận cause, kể cả cause được truyền là **null**, thì không thể gọi lại **initCause**.
- Không cần dùng **initCause** khi lớp ngoại lệ đã hỗ trợ **(String, Throwable)** hoặc **(Throwable)**.

Với mã Java mới, **constructor có cause** thường đơn giản và an toàn hơn. Không dùng **initCause** như một bước cập nhật tùy ý sau khi đã phát tán đối tượng ngoại lệ.

## 5. Suppressed exception là gì?

Khi Java cần giữ một ngoại lệ để ném ra ngoài, nhưng có một ngoại lệ khác xảy ra trong quá trình dọn dẹp, lỗi sau có thể được gắn thành **suppressed** của lỗi chính.

Mẫu điển hình:

1. Khối **try** ném **IOException("Đọc dữ liệu thất bại")**.
2. Khi thoát **try**, Java gọi **close()** trên tài nguyên.
3. **close()** cũng ném **IOException("Đóng luồng thất bại")**.
4. Lỗi đọc vẫn là ngoại lệ được ném ra ngoài.
5. Lỗi đóng được lưu trong **primary.getSuppressed()**.

~~~java
try {
    // Xử lý dữ liệu và phát sinh một lỗi.
} finally {
    // Nếu close() cũng lỗi và lỗi không được quản lý đúng,
    // ngoại lệ đóng tài nguyên có thể che mất lỗi gốc.
}
~~~

Thay vì tự viết logic phức tạp trong **finally**, hãy dùng **try-with-resources** cho đối tượng **AutoCloseable**. Cú pháp này được Java hỗ trợ và còn áp dụng trong Java 27.

## 6. try-with-resources bảo toàn lỗi như thế nào?

Với một resource:

~~~java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    return reader.readLine();
}
~~~

**reader** được đóng tự động khi rời khối try, kể cả khi có lỗi hoặc **return**.

Theo Java Language Specification 27 (§14.20.3):

- Tài nguyên trong header được khởi tạo **từ trái sang phải**.
- Các tài nguyên khởi tạo thành công được đóng **theo thứ tự ngược lại**.
- Nếu khởi tạo tài nguyên sau thất bại, những tài nguyên trước đó đã khởi tạo thành công vẫn được đóng.
- Lỗi khi đóng một tài nguyên không ngăn Java cố gắng đóng các tài nguyên còn lại.
- Nếu đã có lỗi chính, lỗi đóng được lưu thành **suppressed**.

### 6.1. Bốn tình huống quan trọng

| Thân try | Khi đóng tài nguyên | Lỗi được ném ra ngoài |
|---|---|---|
| Thành công | Đóng thành công | Không có ngoại lệ |
| Thất bại với lỗi **A** | Đóng thành công | **A** |
| Thành công | Đóng ném lỗi **B** | **B** |
| Thất bại với lỗi **A** | Đóng ném lỗi **B** | **A**, trong đó **B** là suppressed |

Ví dụ cuối cùng giải thích vì sao nên xem cả **getSuppressed()** trong quá trình chẩn đoán I/O.

### 6.2. Ví dụ Java đầy đủ: hai tài nguyên đều đóng thất bại

Lưu thành tệp **SuppressedDemo.java**:

~~~java
import java.io.IOException;

public class SuppressedDemo {

    static final class FailingResource implements AutoCloseable {
        private final String name;

        FailingResource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            throw new IOException("Đóng " + name + " thất bại");
        }
    }

    static void process() throws IOException {
        try (
            var first = new FailingResource("A");
            var second = new FailingResource("B")
        ) {
            throw new IOException("Xử lý dữ liệu thất bại");
        }
    }

    public static void main(String[] args) {
        try {
            process();
        } catch (IOException primary) {
            System.out.println("Primary: " + primary.getMessage());

            for (Throwable suppressed : primary.getSuppressed()) {
                System.out.println("Suppressed: " + suppressed.getMessage());
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 27:

~~~bash
javac SuppressedDemo.java
java SuppressedDemo
~~~

Kết quả:

~~~text
Primary: Xử lý dữ liệu thất bại
Suppressed: Đóng B thất bại
Suppressed: Đóng A thất bại
~~~

Vì tài nguyên được khởi tạo theo thứ tự **A → B**, Java gọi **close()** theo thứ tự **B → A**. Lỗi của B xuất hiện trước trong danh sách suppressed, rồi đến lỗi của A.

Điều đáng chú ý là lỗi chính từ thân **try** không bị lỗi dọn dẹp thay thế. Cả ba thông tin vẫn được lưu để chẩn đoán.

### 6.3. Khi phần thân không ném lỗi nhưng close() có lỗi

Nếu khối **try** hoàn tất bình thường mà việc đóng B ném lỗi, ngoại lệ đóng B trở thành lỗi chính. Nếu tiếp đó đóng A cũng ném lỗi, lỗi đóng A được gắn là suppressed của lỗi B.

Như vậy, danh sách suppressed không bắt buộc phải chứa lỗi đến từ thân khối try; nó phụ thuộc ngoại lệ nào đã trở thành **primary** trước đó.

### 6.4. Khi khởi tạo tài nguyên thất bại

Xét:

~~~java
try (
    var first = openFirstResource();
    var second = openSecondResource()
) {
    performWork(first, second);
}
~~~

Nếu **openSecondResource()** ném lỗi, Java không chạy thân try. Nhưng **first** đã khởi tạo thành công nên được đóng. Nếu **first.close()** cũng ném lỗi, lỗi đóng được suppressed dưới ngoại lệ xuất phát từ **openSecondResource()**.

Đây là một lý do khác để tránh mở nhiều tài nguyên bằng cách tự quản lý phức tạp mà không có cơ chế dọn dẹp an toàn.

## 7. getSuppressed() và addSuppressed()

### 7.1. Đọc suppressed exceptions

Mỗi Throwable có method:

~~~java
Throwable[] details = error.getSuppressed();

for (Throwable detail : details) {
    System.out.println(detail.getClass().getName());
    System.out.println(detail.getMessage());
}
~~~

**getSuppressed()** trả về một mảng chứa các lỗi phụ được lưu trên chính đối tượng **error**. Các lỗi phụ có thể tiếp tục có cause hoặc suppressed của riêng chúng.

**Không đánh đồng**:

- **error.getCause()** là quan hệ nguyên nhân.
- **error.getSuppressed()** là các lỗi bị giữ lại khi chọn một lỗi để lan truyền.

Nếu bạn gói một exception có suppressed:

~~~java
IOException original = new IOException("Đọc thất bại");
original.addSuppressed(new IOException("Đóng thất bại"));

RuntimeException wrapper =
    new IllegalStateException("Tải dữ liệu thất bại", original);
~~~

Thì:

~~~java
System.out.println(wrapper.getCause() == original);  // true
System.out.println(wrapper.getSuppressed().length);   // 0
System.out.println(wrapper.getCause().getSuppressed().length); // 1
~~~

Suppressed của **original** vẫn được giữ nguyên trên **original**. Nó **không tự động được sao chép** sang danh sách suppressed của wrapper. Khi trình bày toàn bộ chuỗi ngoại lệ, cả cause và suppressed của cause vẫn có thể được hiển thị.

### 7.2. Tự thêm suppressed khi có nhiều lỗi độc lập

Ngoài **try-with-resources**, đôi khi bạn muốn xử lý nhiều tác vụ độc lập, tiếp tục chạy dù một số tác vụ lỗi, sau đó báo cáo tất cả thất bại.

Ví dụ:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

static void writeAll(List<Path> paths) throws IOException {
    IOException aggregate = null;

    for (Path path : paths) {
        try {
            Files.writeString(path, "Dữ liệu mẫu");
        } catch (IOException error) {
            if (aggregate == null) {
                aggregate = new IOException(
                    "Có tệp không thể ghi thành công", error
                );
            } else {
                aggregate.addSuppressed(error);
            }
        }
    }

    if (aggregate != null) {
        throw aggregate;
    }
}
~~~

Ở đây:

- Ngoại lệ đầu tiên được giữ làm **cause** của ngoại lệ tổng hợp.
- Những thất bại tiếp theo được gắn qua **addSuppressed()**.
- Nếu không có lỗi nào, method hoàn thành bình thường.

Cách tổng hợp này chỉ phù hợp khi các thao tác **độc lập**, có thể tiếp tục an toàn sau một lỗi và chương trình muốn báo cáo nhiều thất bại trong một lần. Nếu một lỗi khiến trạng thái không còn an toàn, nên dừng xử lý thay vì tiếp tục tùy tiện.

### 7.3. Quy tắc của addSuppressed()

**Throwable.addSuppressed(Throwable)** có các quy tắc:

- Không chấp nhận **null**: ném **NullPointerException**.
- Không thể thêm chính đối tượng Throwable làm suppressed của nó: ném **IllegalArgumentException**.
- Mặc định hỗ trợ nhiều suppressed exceptions.
- Một số lớp Throwable đặc biệt có thể tắt suppression qua protected constructor; lúc đó **addSuppressed** không lưu thêm lỗi và **getSuppressed()** trả về mảng rỗng.

**Không** lạm dụng **addSuppressed()** thay vì **cause** khi quan hệ thực tế là lỗi này gây ra lỗi kia. Với tài nguyên hỗ trợ **AutoCloseable**, hãy để **try-with-resources** quản lý lỗi đóng thay vì tự gọi addSuppressed.

## 8. Vì sao finally có thể che mất lỗi gốc?

Khối **finally** luôn được xem xét khi rời một khối try theo các quy tắc của ngôn ngữ. Nếu lệnh trong **finally** đột ngột kết thúc bằng một ngoại lệ mới, ngoại lệ mới có thể thay thế lý do khiến khối try kết thúc trước đó.

Ví dụ:

~~~java
static void unsafeCleanup() {
    try {
        throw new IllegalArgumentException("Lỗi xử lý chính");
    } finally {
        throw new IllegalStateException("Lỗi khi dọn dẹp");
    }
}
~~~

Ngoại lệ được lan truyền ra ngoài là **IllegalStateException("Lỗi khi dọn dẹp")**. Lỗi **IllegalArgumentException** trong thân try không tự động được đính kèm làm cause hay suppressed.

Đây là cách mã có thể **đánh mất nguyên nhân quan trọng nhất**. Tương tự, một **return** trong finally có thể che đi ngoại lệ đang được ném từ try; nên tránh dạng điều khiển luồng như vậy.

### 8.1. Giải pháp hiện hành

Đối với tài nguyên như **InputStream**, **Reader**, **Connection** hoặc đối tượng **AutoCloseable** khác, ưu tiên:

~~~java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    return reader.readLine();
}
~~~

Nếu chỉ có những tác vụ dọn dẹp không thuộc AutoCloseable, thiết kế chúng để:

1. Hạn chế thất bại ở cleanup khi khả thi.
2. Nếu cleanup có thể ném lỗi, quyết định rõ lỗi nào là primary.
3. Khi đã có lỗi chính và cleanup cũng lỗi, lưu lỗi cleanup bằng suppressed thay vì thay thế lỗi chính.
4. Chỉ tự viết logic phức tạp khi **try-with-resources** không thể giải quyết trường hợp đó.

Không nên thay try-with-resources bằng logic **try/finally** thủ công chỉ để “kiểm soát thêm”, vì dễ bỏ sót tình huống ngoại lệ trong khi khởi tạo hoặc đóng nhiều tài nguyên.

## 9. Cách ghi log mà không làm mất ngữ cảnh

Trong ứng dụng có nhiều tầng, ngoại lệ có thể được bắt ở lớp truy cập dữ liệu, dịch vụ, API và giao diện. Nếu tầng nào cũng ghi log cùng một stack trace, kết quả thường là **trùng lặp thông tin**.

Một nguyên tắc thực tế:

- Tại tầng bên trong, **thêm ngữ cảnh và truyền lỗi lên** khi thật sự cần.
- Tại một ranh giới có trách nhiệm xử lý lỗi cuối cùng, **ghi log Throwable đầy đủ**.
- Không chỉ ghi **error.getMessage()** nếu cần giữ cause và suppressed.
- Đừng tiết lộ khóa bí mật, token, mật khẩu, nội dung cá nhân hoặc đường dẫn nhạy cảm trong thông điệp trả cho người dùng.

Dùng API **java.util.logging.Logger** của Java 27:

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

public class FailureLogger {
    private static final Logger LOG =
        Logger.getLogger(FailureLogger.class.getName());

    static void report(Throwable error, String requestId) {
        LOG.log(
            Level.SEVERE,
            "Xử lý yêu cầu thất bại, requestId=" + requestId,
            error
        );
    }
}
~~~

Overload **Logger.log(Level, String, Throwable)** liên kết lỗi vào log record. Handler/formatter thích hợp có thể hiển thị đầy đủ chuỗi cause và suppressed.

Không nên thay thế bằng:

~~~java
// Không đầy đủ để chẩn đoán:
System.err.println(error.getMessage());
~~~

Trong ví dụ hoặc chương trình CLI nhỏ, **error.printStackTrace(System.err)** hữu ích để quan sát lỗi. Trong hệ thống production, ưu tiên logger có cấu trúc và chính sách lưu log, phân quyền và bảo vệ dữ liệu phù hợp.

## 10. Ví dụ tích hợp: bảo toàn cause và suppressed qua tầng dịch vụ

Ví dụ dưới đây liên kết ba tầng thông tin trong một chương trình chạy độc lập.

Lưu vào tệp **ErrorContextDemo.java**:

~~~java
import java.io.IOException;

public class ErrorContextDemo {

    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("Đóng nguồn dữ liệu thất bại");
        }
    }

    static final class DataServiceException extends RuntimeException {
        DataServiceException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void readSource() throws IOException {
        try (var resource = new Resource()) {
            throw new IOException("Đọc nguồn dữ liệu thất bại");
        }
    }

    static void loadReport() {
        try {
            readSource();
        } catch (IOException original) {
            throw new DataServiceException(
                "Không thể tạo báo cáo tổng hợp", original
            );
        }
    }

    public static void main(String[] args) {
        try {
            loadReport();
        } catch (DataServiceException error) {
            System.out.println("Service: " + error.getMessage());

            Throwable cause = error.getCause();
            System.out.println("Cause: " + cause.getMessage());

            for (Throwable suppressed : cause.getSuppressed()) {
                System.out.println(
                    "Suppressed: " + suppressed.getMessage()
                );
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 27:

~~~bash
javac ErrorContextDemo.java
java ErrorContextDemo
~~~

Kết quả:

~~~text
Service: Không thể tạo báo cáo tổng hợp
Cause: Đọc nguồn dữ liệu thất bại
Suppressed: Đóng nguồn dữ liệu thất bại
~~~

Luồng lỗi:

~~~mermaid
flowchart TD
    A["readSource(): IOException khi đọc"]
    B["close(): IOException khi đóng"]
    C["Primary IOException"]
    D["loadReport(): DataServiceException"]
    E["main(): đọc cause và suppressed"]
    A --> C
    B -.->|"add suppressed tự động"| C
    C -->|"new DataServiceException(..., original)"| D
    D --> E
~~~

Đây là mẫu quan trọng trong ứng dụng thực tế: **mỗi tầng thêm ngữ cảnh có ý nghĩa nhưng không làm mất lỗi gốc hoặc lỗi dọn dẹp**.

## 11. Phân biệt checked, unchecked và Error

Các cơ chế cause/suppressed dùng cho toàn bộ họ Throwable, nhưng cách ứng dụng **bắt và xử lý** phải phù hợp với loại lỗi.

| Loại | Ví dụ | Hướng xử lý |
|---|---|---|
| Checked exception | **IOException**, **SQLException** | Khai báo/lan truyền qua **throws**, hoặc xử lý/gói tại ranh giới phù hợp |
| Unchecked exception | **IllegalArgumentException**, **IllegalStateException** | Sửa điều kiện, hợp đồng, hoặc xử lý ở tầng có trách nhiệm |
| **Error** | **OutOfMemoryError**, **StackOverflowError** | Thường không phục hồi bằng catch chung; cần xem tình trạng runtime |

Không dùng **catch (Throwable e)** để “xử lý mọi lỗi” trong luồng nghiệp vụ thông thường. Nó còn bắt cả **Error**, có thể che các vấn đề nghiêm trọng của môi trường chạy.

Cũng không nên bắt **Exception** rồi trả giá trị mặc định mà không có quy tắc rõ ràng, vì lỗi quan trọng có thể biến mất.

### 11.1. Không làm mất tín hiệu ngắt luồng

Khi code bắt **InterruptedException**, cần đặc biệt cẩn thận. Tình trạng interrupt là tín hiệu điều phối tác vụ và không nên bị nuốt.

Nếu method có thể khai báo **throws InterruptedException**, cách tốt nhất thường là để ngoại lệ truyền lên.

Nếu bắt ở ranh giới không thể khai báo, hãy phục hồi trạng thái interrupt và giữ cause khi chuyển lỗi:

~~~java
static void waitForWork() {
    try {
        Thread.sleep(1000);
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();

        throw new IllegalStateException(
            "Tác vụ bị yêu cầu ngừng", interrupted
        );
    }
}
~~~

**Thread.currentThread().interrupt()** giúp khôi phục cờ ngắt đã bị xóa khi **InterruptedException** được ném. Ví dụ này dùng lỗi unchecked để minh họa; với hệ thống có quy tắc hủy tác vụ riêng, hãy tuân thủ hợp đồng của API đó thay vì luôn gói lỗi thành **IllegalStateException**.

## 12. Đọc cause và suppressed trong bài kiểm thử

Khi code phải bảo toàn ngữ cảnh, nên kiểm tra cả cấu trúc Throwable thay vì chỉ so sánh thông điệp.

Ví dụ kiểm tra với các câu lệnh Java cơ bản:

~~~java
IOException original = new IOException("Lỗi đọc");
IOException closeFailure = new IOException("Lỗi đóng");

original.addSuppressed(closeFailure);

IllegalStateException wrapper =
    new IllegalStateException("Lỗi báo cáo", original);

if (wrapper.getCause() != original) {
    throw new AssertionError("Không bảo toàn cause");
}

Throwable[] suppressed = wrapper.getCause().getSuppressed();

if (suppressed.length != 1 || suppressed[0] != closeFailure) {
    throw new AssertionError("Không bảo toàn suppressed");
}
~~~

Cần kiểm tra thêm ở các tình huống:

1. Thân try lỗi nhưng close thành công.
2. Thân try thành công nhưng close lỗi.
3. Cả thân try và close đều lỗi.
4. Nhiều tài nguyên close lỗi, thứ tự suppressed đúng.
5. Có lỗi khi khởi tạo tài nguyên sau; tài nguyên trước vẫn được đóng.
6. Chuyển lỗi qua tầng dịch vụ nhưng vẫn giữ cause và suppressed ở tầng gốc.

Trong dự án dùng framework kiểm thử, có thể dùng các assertion tương ứng; không cần đổi cách thiết kế Throwable.

## 13. Những lỗi phổ biến cần tránh

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| **throw new RuntimeException(e.getMessage())** | Mất cause và stack trace gốc | Dùng constructor **(message, cause)** |
| Chỉ in **getMessage()** | Không thấy chuỗi cause/suppressed | Log hoặc in đối tượng Throwable |
| Gọi **initCause()** nhiều lần | **IllegalStateException** | Đặt cause qua constructor ngay từ đầu |
| Dùng **initCause()** sau constructor có cause | Không hợp lệ dù cause ban đầu là **null** | Không đặt cause lần hai |
| Tự đóng tài nguyên trong finally với lệnh có thể ném lỗi | Có thể che mất lỗi gốc | Ưu tiên **try-with-resources** |
| Tin rằng **getSuppressed()** chứa toàn bộ cause chain | Nhầm hai quan hệ khác nhau | Duyệt cause và suppressed theo đúng cấu trúc |
| Gói một Throwable rồi mong suppressed được sao chép lên wrapper | Bỏ sót lỗi phụ nếu chỉ đọc wrapper | Kiểm tra **wrapper.getCause().getSuppressed()** |
| Gọi **addSuppressed(null)** hoặc tự thêm chính Throwable | Ném ngoại lệ khi thêm | Chỉ thêm một lỗi phụ hợp lệ và khác đối tượng chính |
| Catch rồi bỏ qua ngoại lệ | Mất thông tin sự cố | Xử lý thực sự, hoặc truyền/gói lỗi có cause |
| Ghi log ở mọi tầng trước khi rethrow | Nhiều stack trace trùng lặp | Ghi log ở một ranh giới chịu trách nhiệm |
| Ghi toàn bộ dữ liệu đầu vào vào message lỗi | Có thể rò rỉ thông tin nhạy cảm | Chỉ giữ mã lỗi, ID tương quan và ngữ cảnh an toàn |
| Bắt **InterruptedException** rồi bỏ qua | Mất tín hiệu hủy/ngắt | Truyền lên hoặc khôi phục interrupt |
| Bắt rộng **Throwable** trong nghiệp vụ | Che cả **Error** nghiêm trọng | Bắt những loại ngoại lệ có thể xử lý |
| Coi suppressed là “lỗi không quan trọng” | Bỏ qua dấu hiệu không giải phóng tài nguyên | Chẩn đoán và xử lý khi cleanup thất bại |

## 14. Checklist bảo toàn ngữ cảnh lỗi

Khi viết code có thể ném ngoại lệ, hãy tự kiểm tra:

- [ ] Thông điệp mới nói rõ **thao tác nào** thất bại, thay vì chỉ “có lỗi”.
- [ ] Nếu gói lỗi, constructor nhận **cause** gốc.
- [ ] Nếu dùng tài nguyên **AutoCloseable**, ưu tiên **try-with-resources**.
- [ ] Không có **return** hoặc ngoại lệ mới trong finally làm che lỗi chính.
- [ ] Nếu có nhiều lỗi độc lập, lựa chọn primary và suppressed có chủ đích.
- [ ] Khi chẩn đoán, xem cả **getCause()** lẫn **getSuppressed()**.
- [ ] Có một nơi ghi log đầy đủ Throwable, tránh log trùng lặp.
- [ ] Thông điệp ra ngoài không tiết lộ mật khẩu, token hoặc dữ liệu nhạy cảm.
- [ ] Không nuốt **InterruptedException** hoặc các lỗi nghiêm trọng khác.
- [ ] Bài kiểm thử kiểm tra cấu trúc cause và suppressed, không chỉ so sánh message.

## 15. Ghi nhớ

- **Cause** trả lời “vì sao ngoại lệ hiện tại xuất hiện”, được truy cập qua **getCause()**.
- **Suppressed exception** giữ lỗi phụ bị bỏ qua khi một lỗi khác được chọn làm primary, truy cập qua **getSuppressed()**.
- Dùng **new SomeException(message, cause)** để truyền lỗi qua ranh giới tầng ứng dụng mà không mất nguyên nhân.
- **try-with-resources** tự quản lý việc đóng **AutoCloseable** và giữ lỗi đóng bằng suppressed.
- Nhiều tài nguyên được khởi tạo **từ trái sang phải** và đóng **từ phải sang trái**.
- Một ngoại lệ được gói không tự nhận bản sao suppressed của cause; chúng vẫn nằm trên đối tượng cause.
- **initCause()** chỉ nên dùng khi không có constructor nhận cause, và chỉ thiết lập được một lần.
- **addSuppressed()** hữu ích cho những trường hợp tổng hợp nhiều lỗi độc lập, không phải phương án thay thế chung cho cause.
- Không để lỗi cleanup, logging hoặc conversion làm mất stack trace gốc.
- Việc log, trả lỗi và theo dõi thất bại phải phù hợp ranh giới trách nhiệm của từng tầng.

## Tài liệu tham khảo

- [Java SE 27 API — Throwable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 27 API — AutoCloseable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java Language Specification 27 — §14.20.3 try-with-resources](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.20.3)
- [Java SE 27 API — IOException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/IOException.html)
- [Java SE 27 API — Logger](https://docs.oracle.com/en/java/javase/27/docs/api/java.logging/java/util/logging/Logger.html)
- [Java SE 27 API — Thread](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html)
