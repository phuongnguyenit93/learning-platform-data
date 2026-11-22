# writeReplace, readResolve và thay thế đối tượng trong Java Serialization

## 1. Mục tiêu và phạm vi

Khi tuần tự hóa một object graph bằng `ObjectOutputStream` và khôi phục nó bằng `ObjectInputStream`, Java cho phép đối tượng **tự chỉ định một đối tượng khác thay thế nó**. Hai hook quan trọng là:

- `writeReplace()`: được xét **trước khi ghi đối tượng**; đối tượng có thể đề xuất một đại diện khác để lưu vào stream.
- `readResolve()`: được xét **sau khi đọc và khôi phục đối tượng**; đối tượng đã đọc có thể đề xuất một đối tượng khác để trả về cho nơi sử dụng.

Hai cơ chế này giúp thiết kế **serialization proxy**, bảo vệ bất biến dữ liệu, xây dựng lại tài nguyên chỉ tồn tại lúc chạy và giữ identity của các đối tượng chuẩn hóa (canonical object), chẳng hạn singleton. Cần hiểu rõ giới hạn: thay thế diễn ra trong **quá trình serialization/deserialization**, không có nghĩa biến tham chiếu trong ứng dụng tự đổi ngay khi gọi `writeObject`.

Bài học áp dụng cho Java Object Serialization trong `java.io`, ưu tiên **Java 17+**; các thư viện JSON/XML có quy tắc riêng, không tự động gọi hai hook này.

## 2. Cơ sở: Java ghi một object graph như thế nào?

`ObjectOutputStream.writeObject(obj)` xử lý đối tượng gốc và các đối tượng mà nó tham chiếu tới. Mỗi đối tượng có thể được gán một **handle** trong stream để các tham chiếu lặp lại trỏ về cùng một thực thể đã ghi. Khi đọc, `ObjectInputStream` dùng handle để bảo toàn quan hệ chia sẻ tham chiếu phù hợp với quy tắc giao thức.

Ở cơ chế thông thường:

1. Bên ghi xác định đối tượng cần serialization và kiểm tra có phương thức `writeReplace` thích hợp hay không.
2. Nếu `writeReplace` trả về đại diện khác, Java tiếp tục xử lý **đại diện đó** để ghi. Đối tượng đại diện phải hợp lệ cho serialization (hoặc là một trường hợp đặc biệt được định dạng hỗ trợ, như `null`).
3. Bên đọc khôi phục đối tượng theo mô tả trong stream; đây có thể là **lớp đại diện** chứ không phải lớp gốc.
4. Nếu lớp được khôi phục có `readResolve` thích hợp, giá trị trả về từ phương thức đó thay thế đối tượng đang đọc trong kết quả và bảng tham chiếu tương ứng, với một số giới hạn về chu trình đối tượng.
5. `readObject()` của ứng dụng nhận kết quả cuối cùng và thường cần ép kiểu về hợp đồng mà nó mong đợi.

Sơ đồ cho mẫu proxy:

~~~text
Ứng dụng ghi                         Object stream                  Ứng dụng đọc
Original o                          dạng của Proxy p                Original mới
    |                                      ^                             ^
    | writeReplace()                       |                             |
    +------------------> Proxy p ---------+                             |
                                                                         |
                         ObjectInputStream -> Proxy p' -> readResolve() --+
~~~

Dấu `'` trong sơ đồ chỉ đại diện mới được khôi phục, không phải cùng identity với proxy đã tạo ở bên ghi.

### 2.1. Chữ ký hook chuẩn

Một class triển khai `Serializable` (hoặc `Externalizable` khi phù hợp) có thể khai báo:

~~~java
@Serial
private Object writeReplace() throws ObjectStreamException {
    // Trả về đối tượng có thể lưu vào stream.
    return this;
}

@Serial
private Object readResolve() throws ObjectStreamException {
    // Trả về đối tượng ứng dụng sẽ sử dụng sau khi đọc.
    return this;
}
~~~

Đây là **mã minh họa đặt trong thân một class serializable**, không phải chương trình Java độc lập. `ObjectStreamException` thuộc `java.io`, annotation `@Serial` cũng thuộc `java.io` và được hỗ trợ từ Java 14; có thể bỏ phần `throws` khi phương thức không ném ngoại lệ checked.

Những yêu cầu quan trọng:

- Tên phải chính xác `writeReplace` / `readResolve`, **không có tham số**, kiểu trả về là `Object` trong chữ ký serialization quy định. Có thể dùng modifier truy cập phù hợp: `private`, package-private, `protected` hoặc `public`. Việc kế thừa và khả năng truy cập tuân theo quy tắc Java; hook `private` của superclass không được subclass kế thừa.
- Phương thức không phải API bạn gọi thủ công để điều khiển luồng; `ObjectOutputStream` / `ObjectInputStream` tự phát hiện và gọi chúng khi xử lý đối tượng.
- Vì không phải override một phương thức của `Serializable`, **không ghi `@Override`**. Dùng `@Serial` khi thích hợp để compiler hỗ trợ kiểm tra khai báo.
- Một class serializable có thể chỉ có `writeReplace`, chỉ có `readResolve` hoặc cả hai. Hook ở **class đang thực sự được ghi/đọc**, không nhất thiết ở class được truyền ban đầu.

## 3. `writeReplace()`: thay dạng lưu trước khi ghi

### 3.1. Dùng khi nào?

`writeReplace` thường phù hợp khi model runtime có những thứ không nên/không thể lưu trực tiếp, ví dụ `Thread`, connection, executor, tài nguyên tạm thời, hoặc cấu trúc nội bộ mà bạn không muốn đóng băng thành hợp đồng tương thích lâu dài.

Thay vì ghi mọi field của object thật, hook trả về một **serialization proxy** gồm các trường dữ liệu thiết yếu và đã được chọn lọc. Proxy này tự triển khai `Serializable` và có thể dùng `readResolve` để tái tạo đối tượng hợp lệ.

Cần phân biệt `writeReplace` với `writeObject`:

| Cơ chế | Tác động | Kết quả |
| --- | --- | --- |
| `writeObject(ObjectOutputStream)` (hook của class) | Tùy biến cách lưu field/dữ liệu của chính class | Class vẫn là class của đối tượng được ghi |
| `writeReplace()` | Đề xuất **đối tượng khác** làm dạng biểu diễn trong stream | Class ghi thực tế có thể là class proxy khác |
| `transient` | Bỏ qua field trong cơ chế lưu field mặc định | Không tự tạo proxy, không đổi class của bản ghi |

Đánh dấu `transient` có ích khi field đơn giản chỉ là cache; serialization proxy hữu ích khi cần **kiểm soát toàn bộ dạng lưu** hoặc phải khôi phục bất biến của đối tượng.

### 3.2. Ví dụ chạy được: proxy thay đối tượng chứa `Thread`

Tạo file `ReplacementProxyDemo.java`:

~~~java
import java.io.*;

public class ReplacementProxyDemo {
    static final class TaskSession implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String taskId;
        private final Thread runtimeThread = new Thread();

        TaskSession(String taskId) {
            this.taskId = taskId;
        }

        @Serial
        private Object writeReplace() throws ObjectStreamException {
            return new SessionProxy(taskId);
        }
    }

    private static final class SessionProxy implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String taskId;

        SessionProxy(String taskId) {
            this.taskId = taskId;
        }

        @Serial
        private Object readResolve() throws ObjectStreamException {
            return new TaskSession(taskId);
        }
    }

    public static void main(String[] args) throws Exception {
        TaskSession before = new TaskSession("T-17");
        var bytes = new ByteArrayOutputStream();

        try (var out = new ObjectOutputStream(bytes)) {
            out.writeObject(before);
        }

        try (var in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            TaskSession after = (TaskSession) in.readObject();
            System.out.println(after.taskId);
            System.out.println(after.runtimeThread != null);
            System.out.println(after.getClass() == TaskSession.class);
        }
    }
}
~~~

Biên dịch/chạy từ thư mục có file:

~~~bash
javac ReplacementProxyDemo.java
java ReplacementProxyDemo
~~~

Kết quả chuẩn:

~~~text
T-17
true
true
~~~

Giải thích theo từng bước:

1. `TaskSession` triển khai `Serializable` nhưng có `Thread runtimeThread`, và `Thread` không được thiết kế để serialized như trạng thái thực thi.
2. Trước khi ghi trường của `TaskSession`, `writeReplace()` trả về `SessionProxy`. Dạng lưu chỉ có `taskId`, không chứa thread đang chạy.
3. Khi đọc, Java khôi phục `SessionProxy`, sau đó gọi `SessionProxy.readResolve()`.
4. `readResolve` tạo một `TaskSession` mới bằng constructor, nên `runtimeThread` được khởi tạo mới và kết quả ép kiểu về `TaskSession` hợp lệ.

Nếu bỏ `writeReplace` mà vẫn giữ field `runtimeThread` không `transient`, việc ghi `TaskSession` sẽ gặp `NotSerializableException` khi duyệt trường này. Ví dụ trên chủ động giữ field đó **không transient** để chỉ ra vai trò của proxy.

**Điểm đặc biệt:** `TaskSession.readResolve` không bắt buộc phải có trong ví dụ; đối tượng `TaskSession` không phải loại bản ghi được khôi phục từ stream. Hook cần thiết nằm ở **`SessionProxy`** — lớp thực sự được đọc.

### 3.3. Hợp đồng kiểu và khả năng tương thích

Khi `writeReplace` trả về một proxy có kiểu khác, lời gọi đọc cuối cùng phải nhận một kiểu phù hợp với nơi sử dụng. Proxy được khôi phục rồi `readResolve` trả về `TaskSession`, vì thế biến `TaskSession after` nhận đúng kiểu.

Một thiết kế sai có thể gây `ClassCastException` khi đối tượng thay thế không phù hợp với nơi được tham chiếu, ví dụ một field mong đợi `TaskSession` nhưng kết quả đọc cuối là `String`. Cần kiểm thử khi original object nằm **bên trong collection hoặc field có kiểu cụ thể**, không chỉ khi nó là root được ghi bởi `writeObject`.

Không dựa vào việc proxy che giấu type để coi đó là mã hóa hoặc bảo mật: đối tượng trong stream vẫn có cấu trúc nhị phân có thể phân tích, và code khôi phục vẫn cần kiểm tra dữ liệu.

## 4. `readResolve()`: chuẩn hóa đối tượng sau khi đọc

### 4.1. Phục hồi identity và invariant

Mặc định, đọc một đối tượng serializable thường tạo ra một instance mới khác identity với instance gốc. Với **singleton**, mô hình này làm sai ràng buộc “trong JVM chỉ có một instance”. `readResolve` cho phép thay instance tạm được dựng từ stream bằng instance chuẩn đang tồn tại.

Các tình huống thường gặp:

- Singleton dùng class có constructor riêng; `readResolve` trả về `INSTANCE`.
- Value object được intern/canonicalize theo key; `readResolve` tra registry để trả về instance chuẩn.
- Serialization proxy cần gọi factory/constructor có validation để khôi phục đối tượng thật.

Với dữ liệu phải được xác minh, validation nên nằm ở constructor/factory được gọi khi khôi phục. Nếu dữ liệu không hợp lệ, có thể ném một `InvalidObjectException` (nhánh `ObjectStreamException`), thay vì chấp nhận object sai trạng thái.

### 4.2. Ví dụ chạy được: singleton sau deserialization

Tạo file `ReadResolveSingletonDemo.java`:

~~~java
import java.io.*;

public class ReadResolveSingletonDemo {
    static final class AppConfig implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        static final AppConfig INSTANCE = new AppConfig();

        private AppConfig() {}

        @Serial
        private Object readResolve() throws ObjectStreamException {
            return INSTANCE;
        }
    }

    public static void main(String[] args) throws Exception {
        var bytes = new ByteArrayOutputStream();

        try (var out = new ObjectOutputStream(bytes)) {
            out.writeObject(AppConfig.INSTANCE);
            out.writeObject(AppConfig.INSTANCE);
        }

        try (var in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            AppConfig first = (AppConfig) in.readObject();
            AppConfig second = (AppConfig) in.readObject();

            System.out.println(first == AppConfig.INSTANCE);
            System.out.println(second == AppConfig.INSTANCE);
            System.out.println(first == second);
        }
    }
}
~~~

~~~bash
javac ReadResolveSingletonDemo.java
java ReadResolveSingletonDemo
~~~

Kết quả:

~~~text
true
true
true
~~~

Lần `readObject()` đầu tiên khôi phục một instance tạm, nhưng `readResolve` trả `AppConfig.INSTANCE`. Lần đọc tiếp theo cũng tham chiếu cùng instance singleton; object stream còn có cơ chế handle đối với các tham chiếu lặp lại.

**Giới hạn của ví dụ:** việc `first == second` khi ghi lặp lại cùng object vào **một stream** có thể đúng nhờ cơ chế handle, ngay cả khi không có `readResolve`. Phép so sánh quyết định ở đây là `first == AppConfig.INSTANCE`. Để kiểm chứng kỹ, có thể thử ghi và đọc ở **hai stream độc lập**; canonical singleton vẫn là cùng `INSTANCE` trong một JVM nhờ `readResolve`.

### 4.3. Có nên dùng singleton class như vậy?

Nếu không cần hành vi tạo instance đặc biệt và chỉ muốn singleton an toàn trước các trường hợp Java Serialization phổ biến, Java `enum` với một constant thường đơn giản và mạnh hơn:

~~~java
enum AppConfig {
    INSTANCE
}
~~~

Đây là **định nghĩa enum minh họa**, chưa phải chương trình có `main`. Serialization của enum dùng cơ chế đặc biệt: khi đọc, JVM khôi phục constant đã khai báo theo tên; `writeReplace` và `readResolve` tự khai báo trong enum **không được gọi**. Với các singleton cần giữ dữ liệu runtime riêng, cần cân nhắc lifecycle và thread safety thay vì chỉ dựa vào hook.

## 5. Kết hợp `writeReplace` + `readResolve` theo Serialization Proxy Pattern

Mẫu thường dùng:

1. **Original:** class có invariant mạnh, API nghiệp vụ và trạng thái runtime; implements `Serializable` để hook hoạt động.
2. **Proxy:** class `private static final` hoặc class tách riêng; implements `Serializable`; chỉ giữ dạng dữ liệu ổn định như id, giá trị đơn giản, danh sách key.
3. **Original.writeReplace():** tạo proxy từ trạng thái hợp lệ của original.
4. **Proxy.readResolve():** gọi constructor/factory của original để kiểm tra invariant và khôi phục lại đối tượng.
5. **Original.readObject():** nếu muốn ép mọi quá trình đọc phải đi qua proxy, có thể chặn dạng serialization trực tiếp của original bằng hook ném `InvalidObjectException`.

Đoạn mã sau là **phần được thêm bên trong class Original implements Serializable**, minh họa việc từ chối đọc trực tiếp original mà không đi qua proxy:

~~~java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    throw new InvalidObjectException("Proxy required");
}
~~~

Đây không phải chương trình độc lập. Một phiên bản hoàn chỉnh cần có `writeReplace` trên original, proxy serializable và `readResolve` trên proxy như ví dụ ở mục 3. Trong ứng dụng dùng lâu dài, version của **proxy** mới chính là hợp đồng serialized cần bảo trì; tránh thay đổi cấu trúc proxy tùy tiện, hãy đặt `serialVersionUID` và kế hoạch migration rõ ràng.

### 5.1. Ví dụ ngắn về invariant

Giả sử đối tượng nghiệp vụ `Range` yêu cầu `min <= max`. Không nên tin rằng bytes serialized được đưa vào JVM luôn tạo ra trạng thái hợp lệ. Trong proxy, `readResolve` có thể gọi `new Range(min, max)`; constructor kiểm tra invariant và từ chối dữ liệu vô lý. Nếu cần chuyển lỗi sang ngoại lệ I/O nhất quán:

~~~java
@Serial
private Object readResolve() throws ObjectStreamException {
    try {
        return new Range(min, max);  // Constructor kiểm tra min <= max.
    } catch (IllegalArgumentException ex) {
        InvalidObjectException invalid =
                new InvalidObjectException("Invalid range");
        invalid.initCause(ex);
        throw invalid;
    }
}
~~~

Đây là **mã trong lớp proxy của mô hình Range**, với constructor `Range(int, int)` có sẵn; không phải file độc lập. Việc ném `InvalidObjectException` thông báo rõ dữ liệu đọc vi phạm hợp đồng, tránh để đối tượng lỗi đi vào nghiệp vụ.

## 6. Identity, handle và các giới hạn khó nhận ra

### 6.1. Một object được tham chiếu nhiều lần

`ObjectOutputStream` quản lý identity bằng handle. Nếu hai field trỏ đến **cùng một original object**, Java cố gắng bảo toàn quan hệ chia sẻ khi thay thế và đọc lại: cùng handle đối tượng đã ghi sẽ liên kết với cùng kết quả thay thế thích hợp. `writeReplace` không có nghĩa mỗi tham chiếu trong graph gọi hook để tạo một proxy độc lập vô hạn lần.

Tuy nhiên, không được đồng nhất những khái niệm sau:

- **Identity**: `a == b` là cùng instance trong JVM.
- **Equality**: `a.equals(b)` có thể đúng khi hai instance khác nhau.
- **Canonicalization**: nhiều đối tượng tương đương theo key được ánh xạ về một instance chuẩn khi `readResolve` dùng registry/factory.

`readResolve` có thể chủ động gom **nhiều object trong stream** về cùng một instance, làm thay đổi identity theo chính sách ứng dụng; đó là hành vi có chủ đích, không phải mặc định của mọi lần đọc.

### 6.2. Chu trình tham chiếu khi `readResolve` trả đối tượng mới

`readResolve` được gọi sau khi đối tượng đã đọc được dựng xong, do đó **các tham chiếu tới chính object tạm bên trong graph của nó có thể không được sửa thành object thay thế**. Đặc tả serialization cảnh báo đây là vấn đề với chu trình (`cycle`) hoặc self-reference. Mẫu proxy thường an toàn hơn khi proxy chứa **giá trị bất biến đơn giản**, tránh tham chiếu vòng về original.

Tương tự, nếu `writeReplace` trả proxy có graph lại trỏ về original, việc thay thế và phục hồi tham chiếu có thể tạo ra cấu trúc không như mong đợi. Không nên dùng graph proxy chứa back-reference tùy ý nếu chưa có kiểm thử round-trip.

### 6.3. `readUnshared` không phải biện pháp chống canonicalization

`ObjectInputStream.readUnshared()` kiểm soát cách dùng handle đọc lại. Nhưng đối tượng có `readResolve` vẫn có thể trả về singleton/instance từ registry vốn được chia sẻ bên ngoài stream. Vì vậy, `readUnshared` **không bảo đảm** kết quả là một instance mới duy nhất trong JVM.

### 6.4. `null` và kiểu thay thế

Một hook có thể trả về `null`, nhưng nếu caller hoặc field mong đợi một object cụ thể, hậu quả có thể là `NullPointerException` hoặc vi phạm invariant. Cần thiết kế rõ hợp đồng “được phép null” và kiểm thử. Nếu hook trả instance có kiểu khác, phải phù hợp với tất cả nơi sử dụng trong graph; nếu không, `ClassCastException` hoặc lỗi phục hồi khác có thể xảy ra.

## 7. So sánh với các hook và API liên quan

| Cơ chế | Nơi khai báo | Thời điểm / mục đích |
| --- | --- | --- |
| `writeReplace()` | Class serializable | Trước khi ghi object, đề xuất object thay thế |
| `readResolve()` | Class serializable | Sau khi khôi phục object, đề xuất giá trị cuối cùng |
| `private void writeObject(ObjectOutputStream)` | Class serializable | Tùy chỉnh phần dữ liệu của class được ghi |
| `private void readObject(ObjectInputStream)` | Class serializable | Tùy chỉnh phần dữ liệu của class được đọc |
| `ObjectOutputStream.replaceObject(Object)` | Subclass của stream | Hook mức **stream** (cần bật `enableReplaceObject`) để thay đối tượng theo chính sách riêng |
| `ObjectInputStream.resolveObject(Object)` | Subclass của stream | Hook mức **stream** (cần bật `enableResolveObject`) để thay đối tượng sau bước `readResolve` của class |

Các hook mức stream là cơ chế nâng cao và có hệ quả đối với toàn bộ dữ liệu đi qua stream; chúng khác về ownership và phạm vi so với hai hook mức class. Không cần subclass stream chỉ để tạo proxy hoặc singleton thông thường.

**Lưu ý về type:**

- `Serializable` và `Externalizable` có hỗ trợ hook thay thế theo đặc tả.
- Enum có serialization riêng; các hook thay thế khai báo trên enum bị bỏ qua.
- Record triển khai `Serializable` có thể dùng `writeReplace` / `readResolve`, dù cơ chế ghi/đọc field thông thường của record khác với class serializable truyền thống.
- `serialVersionUID` vẫn liên quan tới class thực sự được lưu/đọc. Proxy không loại bỏ nhu cầu quản lý version hoặc tương thích.

## 8. Lỗi phổ biến và cách xử lý

### 8.1. Hook không chạy

Kiểm tra lớp có thực sự triển khai `Serializable`/`Externalizable` không, tên và chữ ký có đúng không, có vô tình thêm tham số hay dùng `static` không. Với phương thức kế thừa, xét phạm vi truy cập theo quy tắc Java; một hook `private` của lớp cha không tự kế thừa cho lớp con. Kiểm tra object thực tế là enum hoặc record nếu hành vi khác dự đoán. Có thể tạm log ở hook khi làm thí nghiệm, rồi xóa log trước môi trường production.

### 8.2. `NotSerializableException` vẫn xuất hiện

Nếu `writeReplace` trả về **proxy không serializable** hoặc proxy vẫn chứa field không serializable, việc ghi vẫn lỗi. Chỉ nói rằng class gốc đã có `writeReplace` là chưa đủ; phải kiểm tra **đồ thị đối tượng của kết quả thay thế**.

### 8.3. `ClassCastException` khi đọc

Một proxy chỉ có `writeReplace` mà không có `readResolve` phù hợp có thể làm `readObject()` trả về proxy thay vì original. Hoặc `readResolve` trả sai kiểu. Kiểm tra cả kiểu root và kiểu field có tham chiếu đến original; đừng chỉ ép kiểu rồi bỏ qua vấn đề thiết kế.

### 8.4. Singleton bị nhân bản

Nếu class singleton được deserialize mà thiếu hook `readResolve` thích hợp, reader có thể trả một instance mới. Giữ `INSTANCE` ở mức `static final`, constructor không public và triển khai đúng hook; với singleton đơn giản, cân nhắc enum. Nhớ kiểm tra cả inheritance/subclass nếu singleton class không phải `final`.

### 8.5. Trạng thái bị mất hoặc khác trước khi lưu

Proxy chỉ lưu những gì nó chứa. Nếu nó chỉ có id nhưng model nghiệp vụ cần timestamp, owner hoặc trạng thái khác, bản khôi phục có thể thiếu thông tin. Cần xác định **bất biến và dữ liệu phải được bảo toàn** trước khi thiết kế proxy, thay vì lược field để tránh lỗi.

### 8.6. Phiên bản cũ không đọc được

Đổi tên class proxy, xóa field cần thiết, đổi `serialVersionUID` hoặc logic khôi phục có thể khiến bản ghi cũ không tương thích. Hãy dùng fixture serialized của phiên bản cũ và kiểm thử migration. Không thay đổi UID tùy tiện nhằm che `InvalidClassException`.

### 8.7. Deserialization dữ liệu không tin cậy

Serialization proxy và `readResolve` **không tự làm Java deserialization an toàn**. Không tạo `ObjectInputStream` trên dữ liệu không tin cậy nếu có thể tránh; khi cần thiết, đặt `ObjectInputFilter` / quy tắc allowlist, giới hạn kích thước, độ sâu, số tham chiếu và validate dữ liệu. Hook có thể gọi constructor/factory và logic ứng dụng; tuyệt đối không coi hook là lớp kiểm tra bảo mật duy nhất.

## 9. Checklist thiết kế và kiểm thử

1. Đối tượng gốc cần bảo toàn **giá trị** hay **identity**? Nếu chỉ cần các trường đơn giản, có thể không cần hook thay thế.
2. Nếu dùng proxy, đã chọn đủ field cho việc khôi phục, tránh lưu tài nguyên runtime và back-reference tạo chu trình?
3. Proxy có `Serializable`, UID ổn định, và `readResolve` trả kiểu phù hợp với mọi field/caller?
4. Đã kiểm tra input trong constructor/factory hoặc hook, và ném exception thích hợp nếu invalid?
5. Đã kiểm thử round-trip một object, nhiều tham chiếu đến cùng object, giá trị null, collection, dữ liệu lịch sử và trường hợp dữ liệu hỏng?
6. Nếu yêu cầu singleton/canonicalization, đã kiểm tra identity so với instance chuẩn, kể cả qua các stream độc lập?
7. Đã có chiến lược version/migration và kiểm soát dữ liệu không tin cậy?

Khi kiểm thử, nên tách **khả năng ghi được stream**, **khả năng khôi phục giá trị đúng** và **tính đúng đắn của identity/invariant** thành các mục riêng; việc `readObject` không ném exception chưa bảo đảm ba điều đó.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `writeReplace` được gọi ở phía đọc hay phía ghi? Nó có làm biến `original` ngoài ứng dụng trỏ sang proxy sau `writeObject(original)` không?

**Đáp án:** Phía ghi, trước khi ghi đối tượng. Nó không thay đổi biến tham chiếu `original` trong bộ nhớ ứng dụng; chỉ chi phối dạng dữ liệu và ánh xạ tham chiếu được ghi vào stream.

**Câu 2.** Class `Employee` có `writeReplace` trả về `EmployeeProxy`. Khi đọc lại, hook `readResolve` nên đặt ở đâu để trả về `Employee`?

**Đáp án:** Thường ở `EmployeeProxy`, vì stream chứa bản biểu diễn của proxy. `EmployeeProxy.readResolve()` có thể tạo/tra cứu `Employee` hợp lệ và trả về nó.

**Câu 3.** Hai lần đọc cùng singleton từ một stream trả object bằng nhau theo `==`. Điều đó một mình có chứng minh `readResolve` hoạt động?

**Đáp án:** Không. Stream có cơ chế handle để tham chiếu lặp lại. Cần so với singleton chuẩn, hoặc kiểm thử qua nhiều stream độc lập.

**Câu 4.** `readResolve` trả một `String` cho field có kiểu `Employee`. Có rủi ro gì?

**Đáp án:** Kiểu không tương thích; quá trình phục hồi hoặc sử dụng có thể phát sinh `ClassCastException`. Phải bảo toàn hợp đồng kiểu của mọi nơi tham chiếu.

**Câu 5.** Vì sao không nên để proxy trỏ vòng về original?

**Đáp án:** Cơ chế thay thế kết hợp handle và chu trình có thể khiến graph khôi phục khác graph mong đợi; riêng `readResolve` xảy ra sau khi object tạm đã hoàn tất, nên self-reference có thể không được cập nhật. Proxy thuần giá trị giảm rủi ro này.

## 11. Nguồn kỹ thuật để tra cứu sâu

- [Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): chữ ký, phạm vi truy cập và các hook thay thế.
- [Java Object Serialization Specification — Object Output Classes, mục 2.5](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/output.html): `writeReplace`, ánh xạ đối tượng khi ghi.
- [Java Object Serialization Specification — Object Input Classes, mục 3.7](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html): `readResolve`, xử lý handle và giới hạn đối với graph vòng.
- [Java Object Serialization Specification — System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html): serialization graph, enum, record và thay thế.

Hai hook đều là cơ chế **thay thế object ở ranh giới stream**. `writeReplace` chọn dạng lưu, `readResolve` chọn giá trị sử dụng sau khi đọc; khi kết hợp thành serialization proxy, chúng giúp duy trì hợp đồng dữ liệu và bất biến của đối tượng một cách có chủ đích.
