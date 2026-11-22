# Phân biệt ngoại lệ ngoài cùng với nguyên nhân sâu nhất trong Java

Khi một thao tác Java thất bại, ngoại lệ mà tầng trên cùng **bắt được hoặc nhìn thấy** không nhất thiết là ngoại lệ **đã bắt đầu chuỗi thất bại ở tầng thấp nhất**. Một tầng I/O có thể ném `IOException`; tầng dịch vụ bắt lỗi I/O rồi ném `IllegalStateException` có `IOException` làm nguyên nhân; tầng khởi động tiếp tục bọc lỗi dịch vụ thành `RuntimeException`. Khi đó có ba đối tượng ngoại lệ khác nhau và ba thông điệp phục vụ những ngữ cảnh khác nhau.

Cách gọi hữu ích:

- **Ngoại lệ ngoài cùng (outermost exception)** là đối tượng `Throwable` đang được quan sát tại điểm xử lý hoặc ghi log, ví dụ tham số `ex` trong `catch` của tầng trên cùng. Nó có thể là đối tượng mới được tạo để bọc lỗi ở tầng bên dưới.
- **Nguyên nhân trực tiếp (immediate cause)** là kết quả của `outer.getCause()` khi khác `null`.
- **Nguyên nhân sâu nhất (deepest cause, đôi khi gọi root cause theo nghĩa kỹ thuật)** là đối tượng ở cuối một chuỗi `getCause()` hữu hạn, nơi `getCause() == null`.
- **Lỗi phụ (suppressed exception)** được truy cập bằng `getSuppressed()`; nó là một nhánh khác, **không tự động thuộc chuỗi `getCause()`**.

**Điểm quan trọng:** “nguyên nhân sâu nhất trong chuỗi `Throwable`” không tự động đồng nghĩa với **nguyên nhân gốc rễ về nghiệp vụ, hạ tầng hoặc vận hành**. Chuỗi cause chỉ là các liên kết ngoại lệ mà mã nguồn đã tạo; muốn tìm lỗi thực sự cần kết hợp dữ liệu đầu vào, log, trạng thái hệ thống và bối cảnh thao tác.

Bài này giải thích cách đọc outermost/cause/deepest, cách bảo toàn thông tin khi bọc ngoại lệ, cách phân biệt cause với suppressed, cách tránh mất nguyên nhân và cách duyệt chuỗi an toàn trên Java 17+.

## 1. Một lỗi có thể đi qua nhiều tầng và đổi tên ngoại lệ

Giả sử ứng dụng có ba tầng:

~~~text
Tầng khởi động ứng dụng: start()
    └── Tầng dịch vụ: service()
        └── Tầng đọc dữ liệu: repository()
~~~

Ở tầng thấp nhất, `repository()` gặp sự cố đọc thiết bị và ném:

~~~java
throw new java.io.IOException("ổ đĩa không phản hồi");
~~~

Tầng `service()` không thể tải cấu hình. Thay vì ném nguyên `IOException` trực tiếp, tầng này có thể bọc:

~~~java
catch (java.io.IOException ex) {
    throw new IllegalStateException("không tải cấu hình", ex);
}
~~~

Tầng `start()` tiếp tục cung cấp ngữ cảnh khởi động:

~~~java
catch (IllegalStateException ex) {
    throw new RuntimeException("khởi động thất bại", ex);
}
~~~

Đối tượng cuối cùng mà người gọi `start()` nhìn thấy là `RuntimeException("khởi động thất bại")`. Nhưng `getCause()` của nó trỏ tới `IllegalStateException("không tải cấu hình")`, và `getCause()` của đối tượng đó trỏ tới `IOException("ổ đĩa không phản hồi")`.

Cấu trúc đối tượng:

~~~text
RuntimeException: khởi động thất bại     ← OUTERMOST tại caller
    │
    └── cause → IllegalStateException: không tải cấu hình
                    │
                    └── cause → IOException: ổ đĩa không phản hồi
                                     │
                                     └── cause → null  ← DEEPEST
~~~

Khi ứng dụng bắt `RuntimeException`, Java **không tự động truyền ngoại lệ sâu nhất vào biến `catch`**. Biến đó tham chiếu tới ngoại lệ đang được ném ra ngoài; muốn xem nguyên nhân sâu hơn, bạn cần gọi `getCause()` theo từng tầng.

## 2. Bốn khái niệm cần phân biệt

| Khái niệm | Cách xác định | Ý nghĩa thực tế |
| --- | --- | --- |
| Outermost | Đối tượng vừa được bắt, nhận từ API hoặc ghi log | Phân loại lỗi ở ranh giới hiện tại; thường mang ngữ cảnh dễ hiểu đối với tầng gọi |
| Immediate cause | `outer.getCause()` | Lỗi gần nhất dẫn tới việc tạo/wrap outermost |
| Deepest cause | Tầng cuối theo chuỗi `getCause()` tới `null` | Ngoại lệ ở đáy chuỗi liên kết nguyên nhân đã được ghi lại |
| Suppressed | `outer.getSuppressed()` hoặc suppressed trên một cause bất kỳ | Các lỗi phụ, thường phát sinh khi dọn dẹp tài nguyên trong lúc lỗi chính đang tồn tại |

Ví dụ:

~~~java
Throwable deepest = new java.io.IOException("không đọc được");
Throwable middle = new IllegalStateException("dịch vụ thất bại", deepest);
Throwable outer = new RuntimeException("yêu cầu thất bại", middle);

System.out.println(outer.getMessage());                    // yêu cầu thất bại
System.out.println(outer.getCause().getMessage());         // dịch vụ thất bại
System.out.println(outer.getCause().getCause().getMessage()); // không đọc được
~~~

Đây là **đoạn minh họa nằm trong một phương thức**. Ba đối tượng có **danh tính riêng**. Một đối tượng exception được tạo tại tầng cao không xóa đối tượng tầng thấp nếu constructor có lưu cause đúng cách.

Từ “ngoài cùng” mang tính **tương đối so với điểm quan sát**. Nếu bạn bắt ngay tại `repository()`, `IOException` có thể là đối tượng được bắt ở đó. Nếu dịch vụ đã bọc và truyền lỗi lên, `IllegalStateException` là outermost tại caller của dịch vụ. Nếu tầng khởi động lại bọc, `RuntimeException` mới là outermost tại caller ngoài cùng.

Không nên gắn cho một lớp ngoại lệ một vai trò “outermost” cố định ở mọi bối cảnh.

## 3. Chương trình Java 17+ hoàn chỉnh: duyệt từ ngoài cùng xuống sâu nhất

Lưu tệp `CauseChainDemo.java`:

~~~java
import java.io.IOException;

public class CauseChainDemo {
    static void repository() throws IOException {
        throw new IOException("ổ đĩa không phản hồi");
    }

    static void service() {
        try {
            repository();
        } catch (IOException ex) {
            throw new IllegalStateException("không tải cấu hình", ex);
        }
    }

    static void start() {
        try {
            service();
        } catch (IllegalStateException ex) {
            throw new RuntimeException("khởi động thất bại", ex);
        }
    }

    public static void main(String[] args) {
        try {
            start();
        } catch (RuntimeException outer) {
            System.out.println("Ngoài cùng: " + outer.getMessage());
            Throwable current = outer;
            int level = 0;
            while (current != null) {
                System.out.println("Tầng " + level + ": "
                        + current.getClass().getSimpleName()
                        + " - " + current.getMessage());
                if (current.getCause() == null) {
                    System.out.println("Sâu nhất: " + current.getMessage());
                }
                current = current.getCause();
                level++;
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 CauseChainDemo.java
java CauseChainDemo
~~~

Stdout chính xác:

~~~text
Ngoài cùng: khởi động thất bại
Tầng 0: RuntimeException - khởi động thất bại
Tầng 1: IllegalStateException - không tải cấu hình
Tầng 2: IOException - ổ đĩa không phản hồi
Sâu nhất: ổ đĩa không phản hồi
~~~

### Phân tích luồng từng tầng

1. `repository()` tạo và ném một đối tượng `IOException` vì mô phỏng lỗi I/O.
2. `service()` bắt `IOException` và tạo **đối tượng mới** `IllegalStateException("không tải cấu hình", ex)`. Tham số thứ hai liên kết lỗi I/O thành **cause**.
3. `start()` bắt `IllegalStateException`, tạo thêm đối tượng `RuntimeException("khởi động thất bại", ex)` với lỗi dịch vụ làm cause.
4. `main()` nhận chính `RuntimeException` từ tầng khởi động; đó là **outermost tại `main`**.
5. Vòng lặp bắt đầu từ outermost và gọi `getCause()` từng tầng tới `null`. Lỗi sâu nhất theo chuỗi là `IOException("ổ đĩa không phản hồi")`.
6. Trong ví dụ, mọi constructor bọc đều **giữ nguyên cause**, nên không tầng nào bị mất khỏi chuỗi.

Đầu ra này cố ý chỉ in **class đơn giản và message** để ổn định. Stack trace thật còn chứa các frame theo tệp và số dòng, là thông tin nên ghi lại khi chẩn đoán lỗi thực tế.

## 4. `getCause()` là liên kết nguyên nhân, không phải “ngoại lệ Java tự tìm”

`Throwable.getCause()` trả về **tham chiếu nguyên nhân đã được thiết lập** cho đối tượng, hoặc `null` khi không có nguyên nhân khả dụng. Nó không tự truy vấn hệ thống, không phân tích stack trace để suy luận lỗi sâu hơn và không tự tìm ra “root cause” từ log.

Hai cách liên kết phổ biến:

~~~java
// Cách 1: Constructor nhận message và cause.
throw new IllegalStateException("bước nghiệp vụ thất bại", original);
~~~

~~~java
// Cách 2: Một số Throwable cũ hỗ trợ initCause.
// Dùng khi nguyên nhân chưa được khởi tạo trước đó.
IllegalStateException wrapper = new IllegalStateException("bước nghiệp vụ thất bại");
wrapper.initCause(original);
throw wrapper;
~~~

Hai đoạn là **minh họa trong ngữ cảnh có `original` khác `null`**. Không được áp dụng `initCause()` tùy tiện sau một constructor đã thiết lập cause, kể cả thiết lập thành `null`. Phần lớn mã Java mới nên ưu tiên constructor `(message, cause)` khi lớp ngoại lệ cung cấp.

Việc bọc lỗi **không bắt buộc**: nếu tầng trên không có lý do thêm ngữ cảnh hoặc đổi hợp đồng, có thể `throw ex;` (ném lại cùng đối tượng) và không tạo thêm tầng cause. Một chuỗi sâu 10 lớp không mặc nhiên hữu ích hơn chuỗi ngắn nếu các lớp chỉ lặp lại thông điệp.

Cũng không nên tạo một ngoại lệ mới mà **bỏ qua lỗi gốc**:

~~~java
// Không tốt nếu cần bảo toàn thông tin điều tra.
catch (IOException ex) {
    throw new IllegalStateException("không tải cấu hình");
}
~~~

Khi đó `IllegalStateException` có `getCause() == null` dù `IOException` thực sự đã xảy ra. Người chỉ nhìn chuỗi `getCause()` ở ngoài sẽ **không thể tìm lại** lỗi I/O chỉ từ đối tượng wrapper mới này.

Nên dùng:

~~~java
catch (IOException ex) {
    throw new IllegalStateException("không tải cấu hình", ex);
}
~~~

Lưu ý về ví dụ: các khối `catch` trên cần đặt trong một phương thức có `try` chứa lời gọi phát sinh `IOException`.

## 5. Ngoại lệ sâu nhất có phải nguyên nhân gốc rễ thực sự không?

Không nhất thiết. **Deepest cause là một thuật ngữ về cấu trúc dữ liệu**, còn **root cause trong chẩn đoán vận hành** là câu trả lời cho “vì sao hệ thống không đạt kết quả mong muốn”.

Ví dụ 1: Chuỗi `IllegalStateException → IOException`, lỗi sâu nhất `IOException("Connection reset")`. Nhưng nguyên nhân vận hành có thể là cấu hình mạng, proxy, chính sách firewall, hết kết nối hoặc máy chủ quá tải. Bản thân `IOException` không chỉ ra duy nhất nguyên nhân đó.

Ví dụ 2: `InvalidOrderException → NumberFormatException`. Đối tượng sâu nhất có thể là `NumberFormatException`, nhưng lỗi nghiệp vụ cốt lõi có thể là dữ liệu CSV sai định dạng hoặc một hợp đồng API cho phép chuỗi rỗng đi qua.

Ví dụ 3: tầng thấp ném `NullPointerException`, tầng cao bọc thành `ServiceException`. `NullPointerException` ở cuối chuỗi có thể phản ánh một bug, nhưng muốn tìm nguyên nhân cần nhìn biến nào `null`, yêu cầu nào kích hoạt và code nào vi phạm bất biến.

Vì thế khi phân tích sự cố:

- Bắt đầu từ **outermost** để hiểu thao tác cấp cao nào thất bại.
- Đọc **toàn bộ cause chain**, không chỉ hai đầu.
- Đối chiếu **stack trace**, log, input và trạng thái chạy.
- Kiểm tra **suppressed exceptions**, đặc biệt khi dùng tài nguyên.
- Kết luận nguyên nhân gốc rễ thực sự từ **bằng chứng thực thi**, không chỉ vì một đối tượng nằm ở vị trí sâu nhất.

Nhiều thư viện gọi kết quả truy đến cuối `getCause()` là `rootCause` trong API. Đây là cách đặt tên tiện dụng, nhưng không phải một phép chứng minh tự động về nguyên nhân vận hành.

## 6. Nếu `getCause()` là `null`

`null` có thể có nhiều ý nghĩa:

1. Đối tượng thực sự là lỗi ban đầu và không có wrapper trước nó.
2. Người viết API chưa thiết lập cause, dù lỗi hiện tại phát sinh sau một lỗi khác.
3. Lỗi được chủ động công bố như thất bại nghiệp vụ độc lập, không có nguyên nhân dạng `Throwable` cần ghi lại.
4. Một wrapper bị tạo sai cách, làm mất chuỗi nguyên nhân.

Vì vậy **không được suy ra** rằng ngoại lệ có `getCause() == null` chắc chắn là lỗi đầu tiên từng xảy ra trong cả ứng dụng.

Ví dụ:

~~~java
// Đoạn minh họa đặt trong phương thức.
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    IllegalStateException wrapped = new IllegalStateException("dữ liệu không hợp lệ");
    System.out.println(wrapped.getCause() == null); // true
}
~~~

`NumberFormatException` đã xảy ra, nhưng `wrapped` không lưu nó. Trong log của `wrapped`, nguyên nhân sâu nhất kỹ thuật chính là `wrapped`; đó chỉ là **đáy chuỗi còn lại**, không phải toàn bộ lịch sử hệ thống.

Đừng gọi `outer.getCause().getMessage()` một cách vô điều kiện. Nếu cause là `null`, bạn sẽ gây `NullPointerException` mới ngay trong logic xử lý lỗi.

## 7. Một ngoại lệ duy nhất cũng có thể là outermost và deepest

Không phải lúc nào cũng có ba tầng:

~~~java
try {
    throw new IllegalArgumentException("tuổi âm");
} catch (IllegalArgumentException ex) {
    System.out.println(ex == ex);                  // true
    System.out.println(ex.getCause() == null);     // true
}
~~~

Đoạn minh họa chỉ chứa **một đối tượng ngoại lệ**, vừa là đối tượng được bắt ở ngoài cùng của ví dụ, vừa là tầng cuối trong chuỗi cause. Câu `ex == ex` chỉ minh họa đồng nhất đối tượng; trong code thật bạn sẽ so sánh với một tham chiếu khác nếu cần kiểm tra có tạo wrapper mới hay không.

Khi viết một hàm `deepestCause(Throwable t)`, nếu `t` khác `null` và `t.getCause() == null`, kết quả theo định nghĩa kỹ thuật thường chính là `t`, **không phải `null`**. Ngược lại, nếu API của bạn chọn trả `null` để biểu thị “không có cause riêng”, đó là một **hợp đồng khác** cần đặt tên và tài liệu rõ ràng.

## 8. `cause` là chuỗi liên kết; `suppressed` là các nhánh phụ

`Throwable` không chỉ có một tham chiếu tới cause, mà còn có **mảng suppressed exceptions**. Để hình dung:

~~~text
IllegalStateException: không nạp được dữ liệu  ← outermost
    |
    └── Caused by: IOException: đọc tệp lỗi   ← deepest theo getCause()
                       |
                       ├── Suppressed: IOException: đóng tệp lỗi
                       └── Suppressed: ... (nếu có thêm)
~~~

Trong cấu trúc này:

- Outermost là `IllegalStateException` vì nó đang được bắt ở tầng trên.
- `IllegalStateException.getCause()` trỏ tới `IOException("đọc tệp lỗi")`.
- `IOException("đọc tệp lỗi").getCause()` là `null`, nên đó là deepest cause.
- Lỗi `IOException("đóng tệp lỗi")` nằm trong **`getSuppressed()` của lỗi đọc**, không phải trong `getCause()`.
- `outermost.getSuppressed()` có thể rỗng, dù một cause bên dưới có suppressed exception.

**Quan hệ khác nhau:** cause trả về tối đa **một tham chiếu trực tiếp** trên mỗi `Throwable`, còn suppressed có thể gồm **nhiều đối tượng**. Mỗi suppressed exception lại có thể có cause và suppressed của riêng nó.

Một trình duyệt chỉ chạy:

~~~java
Throwable current = outermost;
while (current != null) {
    System.out.println(current);
    current = current.getCause();
}
~~~

sẽ **không in các suppressed exceptions**. Đó không phải bug trong `getCause()`; người viết mã chỉ đang duyệt một loại liên kết.

## 9. Chương trình Java 17+: nhìn cause và suppressed cùng lúc

Lưu tệp `SuppressedCauseChainDemo.java`:

~~~java
import java.io.IOException;

public class SuppressedCauseChainDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("đóng tệp lỗi");
        }
    }

    static void read() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("đọc tệp lỗi");
        }
    }

    static void service() {
        try {
            read();
        } catch (IOException ex) {
            throw new IllegalStateException("không nạp được dữ liệu", ex);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IllegalStateException outer) {
            Throwable root = outer.getCause();
            System.out.println("Ngoài cùng: " + outer.getMessage());
            System.out.println("Sâu nhất: " + root.getMessage());
            System.out.println("Suppressed ngoài cùng: " + outer.getSuppressed().length);
            System.out.println("Suppressed nguyên nhân: " + root.getSuppressed().length);
            System.out.println("Lỗi phụ: " + root.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SuppressedCauseChainDemo.java
java SuppressedCauseChainDemo
~~~

Stdout chính xác:

~~~text
Ngoài cùng: không nạp được dữ liệu
Sâu nhất: đọc tệp lỗi
Suppressed ngoài cùng: 0
Suppressed nguyên nhân: 1
Lỗi phụ: đóng tệp lỗi
~~~

Giải thích:

1. Trong `read()`, thân `try-with-resources` ném `IOException("đọc tệp lỗi")` làm **ngoại lệ chính**.
2. Khi rời phần thân, Java tự gọi `Resource.close()` và gặp `IOException("đóng tệp lỗi")`; lỗi đóng được thêm vào **suppressed** của lỗi đọc.
3. `service()` bắt lỗi đọc (đã có suppressed), rồi tạo một `IllegalStateException` mới có lỗi đọc làm cause.
4. `main()` bắt `IllegalStateException` làm outermost. Vì wrapper mới không được gắn suppressed, `outer.getSuppressed().length == 0`.
5. Nguyên nhân của wrapper là `IOException("đọc tệp lỗi")`, nên `root.getSuppressed().length == 1`.
6. Chương trình lấy phần tử đầu `getSuppressed()[0]` vì đường thực thi của **ví dụ cố định này** chắc chắn tạo một suppressed exception. Trong code tổng quát phải kiểm tra độ dài mảng trước khi truy cập.

Nếu chỉ đọc `outer.getMessage()`, bạn mất thông tin về lỗi đọc. Nếu chỉ đọc `outer.getCause().getMessage()`, bạn bỏ qua lỗi đóng. Cả hai đều có thể quan trọng, nhưng mang vai trò khác nhau.

## 10. Cách đọc `printStackTrace()` và phần `Caused by:`

`Throwable.printStackTrace()` của một chuỗi wrapper thông thường có thể xuất ra một dạng như:

~~~text
java.lang.RuntimeException: khởi động thất bại
    at Example.start(Example.java:...)
    at Example.main(Example.java:...)
Caused by: java.lang.IllegalStateException: không tải cấu hình
    at Example.service(Example.java:...)
    ...
Caused by: java.io.IOException: ổ đĩa không phản hồi
    at Example.repository(Example.java:...)
    ...
~~~

Đây là **sơ đồ minh họa**, không phải đầu ra cố định từ tệp `CauseChainDemo.java`: tên lớp/tệp, số dòng, cách rút gọn frame và in stack trace phụ thuộc mã thực tế.

Khi đọc từ trên xuống:

- Dòng đầu mô tả **outermost** mà ta đang in.
- Mỗi phần `Caused by:` thể hiện một liên kết cause sâu hơn.
- Phần `Caused by:` cuối cùng thường tương ứng với **deepest cause của chuỗi hữu hạn**.
- Dòng `Suppressed:` nếu có là lỗi phụ, có thể xuất hiện dưới **bất kỳ tầng Throwable nào**, không chỉ ở outermost.
- Các dòng `... N more` (khi xuất hiện) là cách rút gọn các frame stack trùng ở chuỗi liên quan; chúng **không** phải đối tượng ngoại lệ mới.

Đừng đồng nhất *dòng stack trace cao nhất* với *đáy chuỗi cause*. Outermost có stack trace riêng tại thời điểm wrapper được tạo; deepest có stack trace riêng của nó, thường gần vị trí phát sinh lỗi cấp thấp.

## 11. Stack trace và chuỗi cause là hai chiều thông tin khác nhau

Một `Throwable` có thể có stack trace với các frame gọi hàm nhưng **không có cause**. Ngược lại, một wrapper có `cause` nhưng được cấu hình không ghi stack trace ở chính nó. Vì vậy:

- `getStackTrace()` trả các **frame** được ghi nhận cho đối tượng hiện tại.
- `getCause()` trả **đối tượng Throwable khác** được chỉ định là nguyên nhân.
- `getSuppressed()` trả **các đối tượng Throwable khác** được ghi nhận như lỗi phụ.

Ví dụ nếu:

~~~java
Throwable error = new IllegalArgumentException("sai dữ liệu");
Throwable wrapper = new IllegalStateException("không xử lý được", error);
~~~

thì `wrapper.getStackTrace()` không phải “cùng thứ” với `wrapper.getCause().getStackTrace()`. Chúng mô tả các điểm tạo/ghi trace khác nhau của các đối tượng khác nhau.

Khi ném lại cùng đối tượng bằng `throw ex;`, Java **không mặc định tạo wrapper mới**, nên danh tính và chuỗi cause vẫn như cũ. Khi `throw new SomeException("...", ex);`, bạn có một đối tượng ngoài cùng mới, thường mang stack trace ở vị trí wrap.

Việc `fillInStackTrace()` hoặc `setStackTrace()` có thể thay đổi trace của đối tượng theo hợp đồng API, nên không nên giả định một stack trace bất biến mãi mãi trong mọi thư viện. Tuy nhiên những thay đổi đó không tự tạo thêm liên kết cause.

## 12. Hàm tìm nguyên nhân sâu nhất: trường hợp đơn giản

Với các ngoại lệ do ứng dụng tạo bằng cách bọc bình thường, chuỗi cause thường hữu hạn và kết thúc ở `null`. Khi chắc chắn không có vòng lặp, cách viết dễ hiểu là:

~~~java
// Mã minh họa bên trong một lớp.
static Throwable deepestCause(Throwable error) {
    if (error == null) {
        return null;
    }
    Throwable current = error;
    while (current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
~~~

Ví dụ:

~~~java
Throwable low = new java.io.IOException("I/O lỗi");
Throwable outer = new IllegalStateException("dịch vụ lỗi", low);

System.out.println(deepestCause(outer) == low); // true
~~~

Các đoạn này là **minh họa cần đặt trong một lớp**, với phương thức `deepestCause` nằm cùng phạm vi truy cập hoặc được gọi đúng cách. Hàm trả về ngoại lệ cuối theo `getCause()`, không truy cập `getSuppressed()`.

Nhưng đoạn `while` đơn giản **giả định chuỗi không có vòng tham chiếu**. Trong mã công cụ chẩn đoán phải xử lý đầu vào tùy ý từ các thư viện khác, nên phòng trường hợp chuỗi `getCause()` bất thường bị lặp.

## 13. Chuỗi `cause` có thể bị tạo thành vòng: không có “đáy” hữu hạn

Java không cho một đối tượng tự dùng **chính nó** làm cause qua `initCause`, nhưng mã tùy chỉnh vẫn có thể tạo **vòng giữa nhiều đối tượng** nếu ghép các liên kết `cause` sai cách.

Ví dụ A trỏ tới B, B trỏ về A:

~~~text
Exception("A") ──cause──> Exception("B")
      ^                         |
      └────────cause────────────┘
~~~

Nếu dùng vòng lặp `while (current.getCause() != null)` thông thường, nó sẽ chạy vô hạn. Cách duyệt an toàn nên theo dõi những **đối tượng Throwable đã thấy theo danh tính tham chiếu**, và nếu gặp lại đối tượng cũ thì báo có vòng thay vì tự tuyên bố một deepest cause.

Tệp `CauseWalkerDemo.java`:

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class CauseWalkerDemo {
    static void printChain(Throwable outer) {
        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());
        Throwable current = outer;
        int index = 0;

        while (current != null) {
            if (!visited.add(current)) {
                System.out.println("Phát hiện vòng: " + current.getMessage());
                return;
            }
            System.out.println(index + ": " + current.getMessage());
            Throwable next = current.getCause();
            if (next == null) {
                System.out.println("Đáy chuỗi: " + current.getMessage());
                return;
            }
            current = next;
            index++;
        }
    }

    public static void main(String[] args) {
        Exception a = new Exception("A");
        Exception b = new Exception("B");
        a.initCause(b);
        b.initCause(a);
        printChain(a);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CauseWalkerDemo.java
java CauseWalkerDemo
~~~

Stdout chính xác:

~~~text
0: A
1: B
Phát hiện vòng: A
~~~

Ở ví dụ này **không tồn tại deepest cause theo định nghĩa “`getCause() == null`”**: đi mãi sẽ quay lại A. Đây là chuỗi được tạo cố ý để kiểm thử an toàn, không phải thiết kế ngoại lệ nên dùng trong ứng dụng.

`IdentityHashMap` được dùng để so sánh theo **danh tính đối tượng (`==`)**, không phụ thuộc vào `equals()` tùy chỉnh nếu có. Bất kỳ công cụ duyệt cả cause và suppressed cũng cần tính tới khả năng một đối tượng bị tham chiếu lặp lại theo nhiều đường khác nhau.

## 14. `getSuppressed()` có thể nằm ở bất kỳ tầng nào

Khi phân tích ngoại lệ ngoài cùng `outer`, bạn không nên chỉ tìm suppressed ở `outer` rồi kết luận toàn bộ chuỗi không có lỗi phụ. Một lỗi phụ có thể gắn vào cause thứ nhất, thứ hai hoặc sâu hơn:

~~~text
Outer A
└── cause B
     ├── suppressed S1
     ├── suppressed S2
     └── cause C
          └── suppressed S3
~~~

Đoạn trên là **sơ đồ quan hệ**, không biểu diễn thứ tự thực thi tuyệt đối. Nếu mục tiêu là hiển thị đầy đủ một chuỗi thất bại, bạn cần xem **cả `getCause()` và `getSuppressed()` trên từng đối tượng đã gặp**, với cơ chế tránh vòng lặp/trùng tham chiếu.

Nói ngắn gọn:

- Chỉ lấy **deepest cause**: đi theo `getCause()`.
- Muốn **tất cả lỗi liên quan**: đi cả cause và suppressed, lưu visited theo danh tính.
- Muốn **nguyên nhân vận hành thực sự**: kết hợp thêm dữ liệu hệ thống và hiểu biết về thao tác.

Một suppressed exception cũng có thể chỉ ra lỗi tài nguyên quan trọng, ví dụ không lưu được dữ liệu khi đóng stream; trong vài tình huống, lỗi phụ đó đáng xử lý hơn một phần của lỗi ngoài cùng. Thứ tự trong cây Throwable là mô hình lưu trữ **thông tin ngoại lệ**, không phải bảng xếp hạng mức độ ưu tiên khắc phục sự cố.

## 15. Khi nào nên bọc ngoại lệ và khi nào ném lại?

**Bọc ngoại lệ** thích hợp khi một tầng muốn thêm ngữ cảnh có giá trị hoặc chuyển từ lỗi kỹ thuật sang lỗi thuộc hợp đồng của tầng đó.

Ví dụ tầng đọc file:

~~~java
// Đoạn minh họa trong catch (IOException ex).
throw new ConfigurationLoadException("Không nạp được cấu hình", ex);
~~~

Đoạn này cần lớp `ConfigurationLoadException` được định nghĩa với constructor nhận `(String, Throwable)`. Nó nên giải thích thao tác mà tầng hiện tại đảm nhận và giữ cause.

**Ném lại cùng ngoại lệ** thích hợp khi tầng hiện tại không có phương án xử lý, và loại ngoại lệ vẫn là hợp đồng hợp lý cho caller:

~~~java
// Đoạn minh họa trong catch (IOException ex),
// phương thức chứa có throws IOException.
throw ex;
~~~

Không nên bọc liên tiếp ở mọi tầng chỉ với thông điệp gần như nhau:

~~~text
RuntimeException("lỗi")
└── RuntimeException("lỗi")
    └── RuntimeException("lỗi")
        └── IOException("lỗi đọc")
~~~

Chuỗi trên giữ được cause nhưng có thể làm log dài và khó đọc mà không tăng khả năng điều tra. Ngược lại, việc **bỏ cause** khi bọc tạo ra outermost không còn liên kết tới nguồn lỗi. Hãy chọn cách bọc theo **ranh giới abstraction và thông tin mới thực sự bổ sung**, không theo thói quen.

Trong API công khai, cũng cần cân nhắc thông điệp và thông tin chẩn đoán có thể chứa dữ liệu nhạy cảm; giữ cause nội bộ phù hợp với chính sách log và thông tin trả cho người dùng.

## 16. Các wrapper quen thuộc trong Java

Nhiều API tạo một ngoại lệ ở ranh giới thực thi để báo rằng một tác vụ/phản chiếu/chuỗi hoàn thành bất thường. Một số ví dụ:

- `ExecutionException` thường xuất hiện khi gọi `Future.get()` và tác vụ đã thất bại; nguyên nhân của nó có thể là ngoại lệ do tác vụ ném.
- `CompletionException` thường xuất hiện trong một số đường của `CompletableFuture` và có thể bọc lỗi thực tế ở cause.
- `InvocationTargetException` có thể xuất hiện khi gọi phương thức qua reflection; `getCause()` hoặc API lịch sử `getTargetException()` giúp xem lỗi phát sinh từ phương thức được gọi.
- Các lớp ngoại lệ riêng của framework cũng có thể bọc `IOException`, `SQLException` hoặc một exception nghiệp vụ.

Không nên **tự động bỏ mọi lớp wrapper** mà không xem điều kiện lỗi. Ví dụ `ExecutionException` nói cho caller biết **đường lỗi liên quan tới kết quả tác vụ bất đồng bộ**, còn cause có thể nói lỗi nào xảy ra bên trong. Cả hai ngữ cảnh đều hữu ích.

Một lưu ý khác: `Future.get()` cũng có thể ném những loại lỗi khác như `InterruptedException` hoặc `CancellationException`. Không nên suy luận rằng mọi exception xuất hiện ở API bất đồng bộ đều chắc chắn có cause hoặc có tầng sâu hơn.

## 17. Thu thập dữ liệu lỗi tại ranh giới xử lý

Một chiến lược chẩn đoán tốt khi xử lý ngoại lệ cấp cao:

1. **Ghi tên thao tác và bối cảnh an toàn**, ví dụ loại request, id giao dịch không nhạy cảm, giai đoạn xử lý.
2. **Giữ ngoại lệ ngoài cùng**, vì nó cho biết tầng nào coi sự cố là thất bại.
3. **Giữ toàn bộ Throwable khi log** thay vì chỉ chuỗi `getMessage()`; một logger phù hợp có thể hiển thị stack trace, cause và suppressed.
4. **Truy theo `getCause()`** khi cần nhóm lỗi theo tầng hoặc tìm exception cấp thấp nhất.
5. **Kiểm tra `getSuppressed()`** trên những tầng có tài nguyên được đóng hoặc logic cleanup.
6. **Không ghi log cùng ngoại lệ ở mọi tầng** nếu chỉ chuyển tiếp; log lặp gây nhiễu và làm khó xác định số sự cố thực tế.
7. **Không phụ thuộc vào message cố định** làm API điều khiển logic; ưu tiên loại ngoại lệ, mã lỗi được tài liệu hóa hoặc kết quả có cấu trúc.

Ví dụ minh họa ngắn:

~~~java
// Đoạn minh họa trong catch (Exception ex).
logger.error("Không xử lý được yêu cầu", ex);
~~~

`logger` trong ví dụ cần là logger có API phù hợp với chữ ký `error(String, Throwable)`. Đây là **mẫu ý tưởng**, không phải chương trình độc lập; mục tiêu là cho hệ thống log nhận **đối tượng Throwable**, giữ thông tin cause/suppressed thay vì chỉ `ex.getMessage()`.

Ở tầng API trả về cho người dùng, có thể hiển thị thông điệp an toàn, trong khi log nội bộ giữ thông tin chi tiết theo chính sách quan sát hệ thống. Không tự động đẩy toàn bộ stack trace tới người dùng cuối.

## 18. Các lỗi thường gặp

| Nhầm lẫn | Hệ quả | Cách sửa |
| --- | --- | --- |
| Ngoại lệ bắt ở `catch` luôn là lỗi gốc | Bỏ qua wrapper, không tìm được lỗi tầng thấp | Duyệt `getCause()` khi cần |
| `outer.getCause()` luôn là deepest cause | Nếu có nhiều tầng, đó chỉ là nguyên nhân trực tiếp | Duyệt tới cause cuối hoặc phát hiện vòng |
| `getCause() == null` chứng minh lỗi chưa từng có nguyên nhân khác | Cause có thể không được ghi lại khi bọc | Kiểm tra code tạo exception và log liên quan |
| Bọc ngoại lệ mà bỏ đối tượng gốc | Mất quan hệ nguyên nhân và trace của lỗi trước | Dùng constructor `(message, cause)` |
| `throw ex` tạo thêm một wrapper | Thực tế thường ném lại cùng đối tượng | Phân biệt rethrow với `throw new` |
| Chỉ xem suppressed ở outermost | Lỗi phụ có thể nằm ở một cause sâu hơn | Xem suppressed trên từng tầng Throwable |
| Coi suppressed chính là cause | Sai mô hình quan hệ | Phân biệt `getCause()` và `getSuppressed()` |
| Luôn tin deepest cause là nguyên nhân vận hành cuối cùng | Có thể chẩn đoán sai lỗi hệ thống/dữ liệu | Đối chiếu input, môi trường, stack trace, logs |
| Gọi `getCause().getMessage()` không kiểm tra `null` | Có thể tạo `NullPointerException` trong handler | Kiểm tra `getCause()` trước |
| Duyệt `getCause()` vô hạn với Throwable tùy ý | Có thể gặp vòng tham chiếu | Theo dõi visited bằng identity |
| Chỉ log `ex.getMessage()` | Mất stack trace, cause, suppressed | Log đối tượng exception đầy đủ |
| Bọc ngoại lệ mọi tầng với thông điệp lặp | Cause chain dài, nhiễu log | Chỉ bọc tại ranh giới có ngữ cảnh mới |
| Dùng `getSuppressed()[0]` mà không kiểm tra | `ArrayIndexOutOfBoundsException` nếu mảng rỗng | Kiểm tra độ dài trước khi truy cập |

## 19. Bài tập tự kiểm tra

**Câu 1.** `RuntimeException("start", IllegalStateException("service", IOException("read")))`: ngoại lệ nào ngoài cùng?

**Đáp án:** `RuntimeException("start")` nếu đó là đối tượng caller đang bắt hoặc quan sát ở ranh giới hiện tại.

**Câu 2.** Đối tượng nào sâu nhất nếu chuỗi `getCause()` kết thúc ở `IOException("read")`?

**Đáp án:** `IOException("read")`.

**Câu 3.** `outer.getCause()` có luôn trả deepest cause không?

**Đáp án:** Không. Nó trả **nguyên nhân trực tiếp**; phải tiếp tục đi theo `getCause()` để tìm tầng cuối.

**Câu 4.** Nếu outermost có `getCause() == null`, có thể kết luận không có lỗi cấp thấp từng xảy ra không?

**Đáp án:** Không. Lỗi có thể không được lưu vào cause khi tạo wrapper.

**Câu 5.** `IOException` sâu nhất có một suppressed `IOException("close fail")`. Lỗi đóng có nằm trong chuỗi `getCause()` không?

**Đáp án:** Không chỉ vì nó là suppressed. Phải xem `getSuppressed()` của đối tượng chứa lỗi phụ.

**Câu 6.** Muốn giữ lỗi gốc khi chuyển `IOException` thành `IllegalStateException`, nên viết gì?

**Đáp án:** `throw new IllegalStateException("mô tả tầng mới", ex);`.

**Câu 7.** Nếu chỉ có một đối tượng ngoại lệ và `getCause() == null`, đối tượng nào là deepest cause theo cách duyệt kỹ thuật?

**Đáp án:** Chính đối tượng đó.

**Câu 8.** Khi chuỗi `getCause()` có vòng A → B → A, có deepest cause hữu hạn không?

**Đáp án:** Không. Mã duyệt phải phát hiện vòng và báo chuỗi bất thường.

**Câu 9.** Một outermost wrapper có stack trace riêng, còn cause có stack trace riêng. Hai trace có nhất thiết giống nhau không?

**Đáp án:** Không; hai đối tượng có thể được tạo tại các vị trí khác nhau.

**Câu 10.** Vì sao không nên chẩn đoán chỉ bằng deepest cause?

**Đáp án:** Vì đó chỉ là đáy chuỗi liên kết ngoại lệ, chưa chắc chỉ ra nguyên nhân vận hành/kinh doanh thật sự; vẫn cần ngữ cảnh và bằng chứng bổ sung.

## 20. Tài liệu tham khảo chính thức

- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `initCause()`, `getSuppressed()`, `addSuppressed()`, `printStackTrace()` và stack trace.
- [Java SE 17 API — `IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): ngoại lệ checked thường xuất hiện ở tầng I/O.
- [Java SE 17 API — `ExecutionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): exception wrapper cho kết quả tác vụ thất bại.
- [Java SE 17 API — `CompletionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html): wrapper trong xử lý hoàn thành bất đồng bộ.
- [Java SE 17 API — `InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): lỗi phát sinh khi gọi thông qua reflection.
- [Java Language Specification 17 — §11, Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): phân cấp, ném và xử lý ngoại lệ.
- [Java Language Specification 17 — §14.20.3, `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): cơ chế suppressed exceptions khi đóng tài nguyên.

**Kết luận:** ngoại lệ ngoài cùng là đối tượng được quan sát tại điểm xử lý; nguyên nhân sâu nhất là điểm cuối hữu hạn của liên kết `getCause()`; còn `getSuppressed()` lưu các nhánh lỗi phụ khác. Hãy giữ cause khi bọc, kiểm tra suppressed ở những tầng liên quan, và kết hợp toàn bộ stack trace cùng bối cảnh thực thi trước khi kết luận nguyên nhân gốc rễ của sự cố.
