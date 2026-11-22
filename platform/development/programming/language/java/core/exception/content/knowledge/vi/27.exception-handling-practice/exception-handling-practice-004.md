# Tái cấu trúc cleanup thủ công sang try-with-resources

## 1. Mục tiêu của bài thực hành

Khi đọc code Java cũ, chúng ta thường thấy tài nguyên được mở, sử dụng rồi đóng bằng lệnh **close()** viết thủ công. Đoạn code đó có thể hoạt động tốt trên đường thành công, nhưng lỗi xuất hiện giữa chừng có thể khiến lệnh đóng không chạy. Việc chuyển sang **try-with-resources** (TWR) không chỉ là đổi cú pháp; đó là quá trình **xác lập quyền sở hữu tài nguyên, bao phủ mọi đường kết thúc và bảo toàn thông tin exception**.

Bài thực hành này hướng dẫn **tái cấu trúc cleanup thủ công sang try-with-resources** trong Java Core, với các mục tiêu:

1. Xác định chính xác resource nào cần đóng và ai sở hữu resource đó.
2. Nhận diện các phản mẫu: đóng cuối phương thức, đóng trong finally sai phạm vi, đóng nhiều tài nguyên nối tiếp, bỏ qua lỗi khi khởi tạo tài nguyên sau.
3. Đưa các resource **AutoCloseable** vào phạm vi TWR thích hợp mà không đóng sớm hoặc đóng trùng.
4. Hiểu thứ tự close, cách xử lý return và các dạng exception trên đường thành công/thất bại.
5. Giữ lỗi tác vụ làm **primary**, còn lỗi cleanup làm **suppressed** nếu cả hai xảy ra.
6. Thực hiện migration an toàn với các API có checked exceptions, tài nguyên được khai báo trước Java 9+, wrapper và callback.
7. Kiểm thử lại hành vi, trạng thái và quyền sở hữu chứ không chỉ xem code đã biên dịch.

**Định nghĩa ngắn:** Với TWR, Java tự gọi **close()** trên các resource đã mở thành công khi rời phạm vi try. Khi phần thân đã ném Throwable và close tiếp tục thất bại, lỗi close được ghi vào **getSuppressed()** của lỗi chính, miễn là Throwable hỗ trợ suppression.

Không nên suy ra TWR tự thực hiện rollback database, hủy I/O bên ngoài hoặc làm sạch mọi side effect. TWR giải quyết **vòng đời đóng tài nguyên**; tính nguyên tử dữ liệu là một bảo đảm riêng.

## 2. Đọc phản mẫu trước khi sửa

Ví dụ dạng code cũ:

~~~java
// Mã minh họa; cần khai báo các import và API tạo reader phù hợp.
BufferedReader reader = Files.newBufferedReader(path);
String first = reader.readLine();
reader.close();
return first;
~~~

Nếu **readLine()** ném **IOException** hoặc một RuntimeException, lệnh **reader.close()** không chạy. Đây là lỗi **chỉ cleanup ở happy path**.

Một phiên bản có finally:

~~~java
// Mã minh họa theo ngữ cảnh.
BufferedReader reader = Files.newBufferedReader(path);
try {
    return reader.readLine();
} finally {
    reader.close();
}
~~~

Phiên bản này thử close kể cả khi thân try ném exception hoặc return. Nhưng hai điểm vẫn cần xét:

- Nếu **reader.close()** ném exception, nó có thể che exception đọc đã xảy ra trong try.
- Nếu một resource khác được mở trước reader và lỗi xảy ra trước khi đi vào try, phần finally có thể chưa bảo vệ được resource trước đó.

Vì vậy, chuyển sang TWR phải giữ những yêu cầu thực tế của API: đảm bảo đóng đúng resource, đúng phạm vi, đúng thời điểm và truyền đủ lỗi cho caller.

Cách viết hướng tới:

~~~java
// Mã minh họa với imports BufferedReader, Files, Path, IOException.
try (BufferedReader reader = Files.newBufferedReader(path)) {
    return reader.readLine();
}
~~~

Nếu reader mở thành công, TWR chịu trách nhiệm gọi close khi thân try kết thúc bất kể thành công, exception hay return. Nếu mở reader thất bại trước khi có object hợp lệ, không có reader đó để đóng; nếu đã mở những resource TWR trước đó, chúng vẫn được cleanup.

## 3. Trước hết phải xác định ownership

**Ownership** là trách nhiệm quản lý vòng đời: ai được quyền đóng tài nguyên, ai phải đảm bảo close và khi nào quyền đó chuyển sang người khác.

Câu hỏi cần trả lời khi refactor:

| Trường hợp | Ai thường chịu trách nhiệm đóng? | Lưu ý |
| --- | --- | --- |
| Phương thức tự mở file để đọc và chỉ trả dữ liệu | Chính phương thức | TWR ngay trong phương thức thường phù hợp |
| Phương thức nhận InputStream do caller truyền vào | Thường caller, tùy hợp đồng | Không tự đóng bằng TWR nếu không sở hữu |
| Factory trả một InputStream còn mở | Caller nhận ownership | Không TWR quanh resource sẽ trả về |
| Wrapper stream tự đóng delegate khi close | Chủ sở hữu wrapper theo hợp đồng | Tránh đóng trùng delegate không cần thiết |
| Connection do framework quản lý transaction cấp | Framework/transaction boundary | TWR sai phạm vi có thể phá transaction |
| ResultSet/Statement được tạo trong một block ngắn | Phụ thuộc JDBC API và tầng sở hữu | Xác định phạm vi và thứ tự đóng |
| Resource được cache dùng qua nhiều request | Thành phần quản lý cache/application | Không đóng sau mỗi request nếu vẫn được dùng chung |

Nếu mở trong hàm rồi trả về chính resource:

~~~java
// Phản mẫu: phương thức trả về resource đã bị đóng.
InputStream createStream() throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input;
    }
}
~~~

TWR sẽ gọi close **trước khi caller nhận kết quả**. Đây là sai nếu caller muốn tiếp tục đọc stream. Cách đúng là trả stream còn mở và **ghi rõ caller chịu trách nhiệm close**, hoặc đổi API để trả dữ liệu đã đọc hoàn chỉnh trong phạm vi đóng của method.

TWR phù hợp nhất khi **vòng đời resource trùng với phạm vi lexical của try**. Nếu vòng đời dài hơn, đừng ép vào một block quá ngắn.

## 4. Quy trình chuyển đổi an toàn theo từng bước

Một quy trình review/refactor có hệ thống:

**Bước 1 — Đọc đường mở resource.** Tìm chỗ tạo FileInputStream, BufferedReader, Connection, Statement, Socket, ZipFile, Stream hoặc custom AutoCloseable. Nếu mở nhiều resource, ghi thứ tự và điểm từng lần acquire thành công.

**Bước 2 — Phân tích ownership.** Xác định resource hiện thuộc phương thức hay được mượn/chuyển giao. Không “sửa rò rỉ” bằng cách đóng resource của caller trái hợp đồng.

**Bước 3 — Tìm mọi đường thoát.** Ngoại lệ checked, RuntimeException, Error, return sớm, break, continue, các nhánh điều kiện và lỗi khi mở tiếp resource khác.

**Bước 4 — Kiểm tra API close.** Resource có implement AutoCloseable/Closeable không? Close ném checked exception nào? Có đóng delegate bên dưới không? Có yêu cầu đóng ngược thứ tự không?

**Bước 5 — Chọn phạm vi TWR.** Đưa acquisition vào dấu ngoặc của try nếu có thể. Block nên bao toàn bộ thời gian resource được sử dụng nhưng không kéo dài quá lifetime cần thiết.

**Bước 6 — Di chuyển phần xử lý chính.** Giữ logic nghiệp vụ trong thân try, không vô tình gọi lại công việc hoặc thay thứ tự các side effect.

**Bước 7 — Xóa manual close dư.** Khi TWR đã sở hữu resource, bỏ lệnh close cũ tránh đóng hai lần.

**Bước 8 — Giữ hợp đồng exception.** So sánh exception mà caller nhận khi thân try lỗi, close lỗi, cả hai cùng lỗi. Nếu code cũ có bug che primary, cần chủ động cập nhật test theo hành vi đúng mong muốn, không cố bảo tồn bug.

**Bước 9 — Kiểm thử fault injection.** Cho open/work/close lần lượt thất bại; đo đúng số lần close, thứ tự, primary/suppressed và kết quả nghiệp vụ.

**Bước 10 — Xem tác động vận hành.** Theo dõi connection leak, file descriptor, log Throwable đầy đủ, trạng thái transaction và hiệu năng trên các đường dùng thật.

Một refactor được xem là hoàn chỉnh khi **behavioral contract** rõ ràng và test hồi quy PASS; không chỉ khi IDE không còn cảnh báo “resource leak”.

## 5. Phân biệt AutoCloseable và Closeable

Java dùng hai interface liên quan:

~~~java
// Chữ ký khái niệm; đặt trong package chuẩn của JDK.
interface AutoCloseable {
    void close() throws Exception;
}

interface Closeable extends AutoCloseable {
    void close() throws IOException;
}
~~~

**AutoCloseable** là hợp đồng tổng quát cho resource cleanup. **Closeable** thuộc java.io, thu hẹp kiểu checked exception thành IOException. Hai chữ ký trên chỉ minh họa contract, không phải mã dùng để khai báo lại những interface chuẩn.

Nếu biến có kiểu tĩnh **AutoCloseable**, compiler có thể yêu cầu xử lý **Exception** từ close. Nếu biến có kiểu **BufferedReader** hay **InputStream**, close thường được khai báo với IOException. Khi chuyển sang TWR, **đừng bất ngờ mở rộng throws Exception** trên một API public chỉ vì đã đổi kiểu biến sang AutoCloseable quá rộng.

Ví dụ:

~~~java
// Mã minh họa bên trong một phương thức throws IOException.
try (BufferedReader reader = Files.newBufferedReader(path)) {
    return reader.readLine();
}
~~~

Kiểu cụ thể được giữ, nên checked exception có thể được khai báo/điều phối phù hợp với IOException. Trong trường hợp custom resource, nên chọn chữ ký close chặt nhất phản ánh lỗi có thể xảy ra.

**Lưu ý:** Không phải close nào cũng idempotent. AutoCloseable không hứa việc gọi close nhiều lần trên mọi implementation sẽ vô hại. Vì vậy, sau khi chuyển ownership sang TWR, bỏ cleanup cũ thực sự là một bước correctness, không chỉ làm code gọn.

## 6. Ví dụ runnable Java 17+: so sánh before và after

Để không phụ thuộc database hoặc file thật, chương trình sau tạo **Tracked implements AutoCloseable**. Constructor in tên tài nguyên lúc mở; **work()** có thể ném IOException; **close()** in tên khi đóng và cũng có thể ném IOException.

Chương trình gồm:

1. **oldMissingFailureBranch** — resource được mở nhưng không đóng nếu work ném.
2. **oldFinallyMasksWork** — finally đóng resource nhưng che exception công việc.
3. **refactoredWorkFailure** — TWR giữ primary và suppressed.
4. **twoResources** — đóng ngược thứ tự và thử đóng cả hai dù close đều lỗi.
5. **initializationFailure** — resource thứ nhất được đóng nếu mở resource tiếp theo lỗi.
6. **returnWithCleanup** — close chạy trước khi return hoàn tất.
7. **java9ExistingVariable** — từ Java 9, biến local effectively final có thể xuất hiện trong resource specification.

Lưu thành **ResourceRefactorDemo.java**:

~~~java
import java.io.IOException;

public class ResourceRefactorDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;
        private final boolean failClose;
        private boolean closed;

        Tracked(String name, boolean failClose) {
            this.name = name;
            this.failClose = failClose;
            System.out.println("open " + name);
        }

        void work(boolean fail) throws IOException {
            System.out.println("work " + name);
            if (fail) {
                throw new IOException("work " + name + " failed");
            }
        }

        boolean isClosed() {
            return closed;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            closed = true;
            if (failClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    static void oldMissingFailureBranch() throws IOException {
        Tracked resource = new Tracked("legacy", false);
        resource.work(true);
        resource.close();
    }

    static void oldFinallyMasksWork() throws IOException {
        Tracked resource = new Tracked("finally", true);
        try {
            resource.work(true);
        } finally {
            resource.close();
        }
    }

    static void refactoredWorkFailure() throws IOException {
        try (Tracked resource = new Tracked("safe", true)) {
            resource.work(true);
        }
    }

    static void twoResources() throws IOException {
        try (Tracked first = new Tracked("first", true);
             Tracked second = new Tracked("second", true)) {
            throw new IOException("body failed");
        }
    }

    static Tracked openSecondAndFail() throws IOException {
        System.out.println("opening second failed");
        throw new IOException("second open failed");
    }

    static void initializationFailure() throws IOException {
        try (Tracked first = new Tracked("prepared", true);
             Tracked second = openSecondAndFail()) {
            System.out.println("unreachable");
        }
    }

    static String returnWithCleanup() throws IOException {
        try (Tracked resource = new Tracked("return", false)) {
            System.out.println("prepare return");
            return "result";
        }
    }

    static void java9ExistingVariable() throws IOException {
        Tracked existing = new Tracked("existing", false);
        try (existing) {
            existing.work(false);
        }
        System.out.println("existing closed=" + existing.isClosed());
    }

    static void show(IOException problem) {
        System.out.println("primary: " + problem.getMessage());
        for (Throwable secondary : problem.getSuppressed()) {
            System.out.println("suppressed: " + secondary.getMessage());
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println("== Missing failure branch ==");
        try {
            oldMissingFailureBranch();
        } catch (IOException problem) {
            show(problem);
        }

        System.out.println("== Finally masks original ==");
        try {
            oldFinallyMasksWork();
        } catch (IOException problem) {
            show(problem);
        }

        System.out.println("== Refactored ==");
        try {
            refactoredWorkFailure();
        } catch (IOException problem) {
            show(problem);
        }

        System.out.println("== Reverse closing order ==");
        try {
            twoResources();
        } catch (IOException problem) {
            show(problem);
        }

        System.out.println("== Failure during acquisition ==");
        try {
            initializationFailure();
        } catch (IOException problem) {
            show(problem);
        }

        System.out.println("== Early return ==");
        System.out.println("returned: " + returnWithCleanup());

        System.out.println("== Java 9 existing variable ==");
        java9ExistingVariable();
    }
}
~~~

Biên dịch và chạy JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 ResourceRefactorDemo.java
java ResourceRefactorDemo
~~~

Stdout đã được kiểm chứng khi biên dịch và chạy:

~~~text
== Missing failure branch ==
open legacy
work legacy
primary: work legacy failed
== Finally masks original ==
open finally
work finally
close finally
primary: close finally failed
== Refactored ==
open safe
work safe
close safe
primary: work safe failed
suppressed: close safe failed
== Reverse closing order ==
open first
open second
close second
close first
primary: body failed
suppressed: close second failed
suppressed: close first failed
== Failure during acquisition ==
open prepared
opening second failed
close prepared
primary: second open failed
suppressed: close prepared failed
== Early return ==
open return
prepare return
close return
returned: result
== Java 9 existing variable ==
open existing
work existing
close existing
existing closed=true
~~~

**Đọc kết quả theo chuỗi before → after:** Tài nguyên **legacy** không in close vì work ném trước lệnh close thủ công. Tài nguyên **finally** có in close, nhưng người gọi chỉ nhận **close finally failed** — lỗi work bị che. Khi thay bằng **safe** trong TWR, chương trình in lỗi chính **work safe failed** và suppressed **close safe failed**. Đó là cải tiến quan trọng về **thông tin lỗi và vòng đời**, không chỉ giảm số dòng code.

Ví dụ mô phỏng resource đơn giản để có stdout ổn định. Trong ứng dụng thật, close có thể flush, phát sinh I/O, giải phóng lock hoặc gửi lệnh tới server; phải xác minh thêm hợp đồng loại tài nguyên đó.

## 7. Đọc lỗi chính và suppressed sau refactor

TWR giữ ý nghĩa Throwable theo những tình huống:

| Phần thân | Close | Kết quả quan sát |
| --- | --- | --- |
| Thành công | Thành công | Hoàn tất bình thường |
| Ném A | Thành công | A được truyền ra |
| Thành công | Ném B | B có thể trở thành lỗi chính |
| Ném A | Ném B | A là primary, B được thêm vào A.getSuppressed() |
| Return giá trị | Thành công | Close chạy trước khi return hoàn tất |
| Return giá trị | Ném B | Không hoàn tất return bình thường; B truyền ra |
| Mở resource thứ hai ném C | Đóng resource đầu thành công | C truyền ra |
| Mở resource thứ hai ném C | Đóng resource đầu ném D | C primary, D suppressed |

**getCause() và getSuppressed() khác nhau.** Cause mô tả quan hệ lỗi là nguyên nhân của wrapper; suppressed mô tả lỗi phụ xảy ra khi thao tác khác đang thất bại.

Ví dụ:

~~~java
// Mã minh họa trong catch hợp lệ.
catch (IOException primary) {
    System.out.println(primary.getMessage());
    for (Throwable extra : primary.getSuppressed()) {
        System.out.println(extra.getMessage());
    }
}
~~~

Trong ví dụ runnable, **show(IOException)** làm đúng điều này. Nếu một tầng service tạo **new IllegalStateException("read failed", primary)**, suppressed vẫn nằm trên **primary** ở **wrapper.getCause().getSuppressed()**, không tự động xuất hiện trên **wrapper.getSuppressed()**. Vì vậy logger cần hiển thị **toàn bộ cây Throwable**, không chỉ outer message.

Một số Throwable custom có thể tắt suppression bằng constructor chuyên dụng. Khi suppression không được bật, addSuppressed không lưu thông tin; trong trường hợp đó không thể hứa rằng mọi lỗi close được giữ trong getSuppressed. Với exception JDK thông dụng như IOException, cơ chế trên hoạt động như dự kiến.

## 8. Vì sao đặt acquisition trong resource specification?

Phản mẫu khi mở hai tài nguyên:

~~~java
// Phản mẫu theo ngữ cảnh.
Resource a = openA();
Resource b = openB(); // Nếu lỗi, chưa vào try.
try {
    work(a, b);
} finally {
    b.close();
    a.close();
}
~~~

Nếu openB ném exception, a đã mở nhưng finally không hề bắt đầu, nên a bị bỏ quên.

Mẫu tốt hơn:

~~~java
// Minh họa; Resource implements AutoCloseable.
try (Resource a = openA();
     Resource b = openB()) {
    work(a, b);
}
~~~

Java quản lý từng resource đã được mở thành công. Nếu **openB()** thất bại, a được thử đóng. Nếu đóng a cũng thất bại, lỗi cleanup được suppressed vào lỗi khởi tạo B theo cơ chế TWR.

**Một ranh giới quan trọng:** Nếu **openB()** cấp phát tài nguyên nội bộ rồi thất bại trước khi trả về object B, TWR bên ngoài không thể đóng một object chưa được giao. **Factory/constructor** của B phải tự xử lý exception safety cho phần sở hữu nội bộ của nó. TWR không chữa được mọi kiểu resource leak bên trong thư viện.

## 9. Thứ tự đóng nhiều resource và phụ thuộc vòng đời

Trong resource specification:

~~~java
// Minh họa theo ngữ cảnh.
try (Resource first = openFirst();
     Resource second = openSecond(first)) {
    use(second);
}
~~~

Java đóng **second trước first**. Trong ví dụ runnable, stdout cho thấy **close second**, sau đó **close first** dù cả hai close đều ném IOException.

Đây là thiết kế hợp lý khi second phụ thuộc first, nhưng vẫn cần kiểm tra **ownership**. Một wrapper có thể tự đóng delegate trong close; nếu bạn khai báo wrapper và delegate như hai resource độc lập, delegate có thể bị close hai lần. AutoCloseable không bảo đảm mọi close có thể lặp vô hại.

Ví dụ với BufferedReader quấn quanh một Reader:

~~~java
// Minh họa đọc file.
try (BufferedReader buffered =
         new BufferedReader(Files.newBufferedReader(path))) {
    process(buffered);
}
~~~

Trong trường hợp này, close của BufferedReader đóng reader bên dưới theo hợp đồng. Không cần khai báo thêm một biến Reader độc lập chỉ để đóng lại, trừ khi có yêu cầu ownership cụ thể. Nếu tách resource thành nhiều lớp, đảm bảo thứ tự đóng không phá phụ thuộc của wrapper và tránh close trùng.

## 10. Java 9+: sử dụng biến local final hoặc effectively final

Trong Java 7/8, cú pháp resource specification phổ biến là **try (Type variable = expression)**. Từ Java 9, có thể sử dụng một **biến local hoặc tham số kiểu final/effectively final** đã tồn tại:

~~~java
// Mã minh họa Java 9+.
BufferedReader reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
~~~

Cú pháp này chỉ hợp lệ khi biến phù hợp điều kiện final/effectively final. Nếu biến bị gán lại sau khởi tạo, compiler có thể từ chối. Ví dụ chương trình runnable có:

~~~java
// Đoạn trích.
Tracked existing = new Tracked("existing", false);
try (existing) {
    existing.work(false);
}
~~~

Ở đây **existing** không bị gán lại, nên Java 17 biên dịch được. TWR đóng resource khi ra khỏi try; tham chiếu existing vẫn tồn tại trong scope nhưng object đã được đóng. **Có tham chiếu không đồng nghĩa được phép tiếp tục dùng resource**.

### Cạm bẫy khi biến có sẵn được mở bên ngoài

Nếu code làm nhiều thao tác giữa **open** và **try(existing)**, exception trong khoảng đó vẫn có thể làm resource bị bỏ quên:

~~~java
// Phản mẫu theo ngữ cảnh.
Resource existing = open();
prepareOtherState(); // Có thể ném trước try.
try (existing) {
    use(existing);
}
~~~

Khi thực hiện refactor, nên **đưa phạm vi sở hữu bắt đầu càng sát lúc acquisition thành công càng tốt**. Biến có sẵn trong Java 9+ là tiện ích cú pháp, **không bảo đảm cleanup cho những bước thực thi trước khi vào try**.

Một điều khác: Không đặt resource do caller truyền vào trong **try (parameter)** nếu method **không sở hữu** resource đó. Java vẫn gọi close; cú pháp hợp lệ không chứng minh quyết định ownership đúng.

## 11. Refactor với nhiều phương thức return và nhánh điều kiện

Cleanup ở cuối phương thức dễ bị bỏ qua bởi early return:

~~~java
// Phản mẫu theo ngữ cảnh.
Resource resource = openResource();
if (shouldSkip()) {
    return;
}
perform(resource);
resource.close();
~~~

Chuyển thành:

~~~java
// Minh họa.
try (Resource resource = openResource()) {
    if (shouldSkip()) {
        return;
    }
    perform(resource);
}
~~~

TWR đóng resource trước khi phương thức hoàn tất. **return trong thân try** không đồng nghĩa bỏ cleanup. Nhưng **return trong finally** lại là phản mẫu vì có thể che exception/kết quả đang chờ.

Với **break** hoặc **continue** từ một vòng lặp, khi điều khiển rời phạm vi TWR, close cũng được thực hiện. Cần chọn vị trí block theo vòng đời thực tế: resource sống qua toàn bộ vòng lặp hay mỗi iteration mở một resource mới? Nếu cần stream/connection sống qua nhiều iteration, đặt TWR bao quanh vòng lặp; nếu mỗi iteration dùng resource độc lập, đặt TWR bên trong vòng lặp.

Ví dụ minh họa hai chiến lược:

~~~java
// Một resource dùng cho toàn bộ vòng lặp.
try (Resource shared = openResource()) {
    for (Item item : items) {
        process(shared, item);
    }
}

// Resource riêng cho từng item.
for (Item item : items) {
    try (Resource perItem = openResource(item)) {
        process(perItem, item);
    }
}
~~~

Hai đoạn chỉ minh họa thiết kế scope; Resource, Item và các hàm cần được định nghĩa trong project. Cách thứ hai tạo nhiều lần open/close và có thể tốn hơn hoặc đúng hơn tùy contract. Không đổi phạm vi chỉ vì cú pháp dễ viết.

## 12. Khi refactor API không implements AutoCloseable

Không phải mọi tài nguyên đều có close chuẩn. Lock có **unlock()**; một API native có **release(handle)**; transaction có **commit()/rollback()**. Khi đó có thể:

1. Giữ cleanup thủ công với finally đúng phạm vi và chiến lược bảo toàn lỗi.
2. Tạo **adapter AutoCloseable** nếu semantics release phù hợp và ownership rõ ràng.
3. Dùng higher-order helper để bao vòng đời nếu API có những bước commit/rollback đặc biệt.

Ví dụ adapter:

~~~java
// Minh họa theo ngữ cảnh; handle đã acquire thành công.
try (AutoCloseable scope = () -> handle.release()) {
    use(handle);
}
~~~

Do **AutoCloseable.close() throws Exception**, phương thức chứa đoạn này phải khai báo/bắt checked exception phù hợp. Adapter cũng cần xét liệu release có idempotent, release thất bại thì còn trạng thái gì và có cần chuyển ownership sau đó không. Đừng viết adapter chỉ để “đạt chuẩn TWR” nếu nó làm mất semantics transaction.

Một ví dụ với Lock:

~~~java
// Minh họa với java.util.concurrent.locks.Lock.
lock.lock();
try {
    performOperation();
} finally {
    lock.unlock();
}
~~~

Đây vẫn là một cấu trúc phù hợp vì Lock không trực tiếp là AutoCloseable. Đặt lock.lock() trước try bảo đảm unlock chỉ chạy khi việc lấy khóa hoàn tất bình thường. Với **lock.lockInterruptibly()**, nếu InterruptedException xảy ra trước khi nhận khóa, code không được cố unlock. Refactor phải tôn trọng ranh giới acquire thành công.

## 13. Khi chuyển đổi làm thay đổi checked exceptions

Một method cũ có thể không khai báo Exception rộng vì close không được xử lý chính xác hoặc tài nguyên có kiểu cụ thể. Sau refactor, compiler sẽ kiểm tra những checked exceptions mà **close()** trong resource specification có thể ném.

Ví dụ:

~~~java
// Mã minh họa:
static String read(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

BufferedReader.close có thể ném IOException, nên chữ ký throws IOException phù hợp.

Nếu bạn thay kiểu khai báo bằng **AutoCloseable**:

~~~java
// Minh họa; cần xử lý checked Exception từ AutoCloseable.close().
static void process(AutoCloseable resource) throws Exception {
    try (resource) {
        performOperation();
    }
}
~~~

Không nên tùy tiện đổi mọi public method thành **throws Exception** chỉ để biên dịch. Kiểm tra kiểu tĩnh cụ thể, overload API, constructor của wrapper và chính sách exception hiện hữu. Có thể sử dụng resource wrapper có **close() throws IOException** hoặc một exception được định nghĩa rõ hơn nếu đúng semantics.

**Quan trọng:** TWR có thể làm một exception **mà code cũ đang vô tình bỏ qua** trở nên quan sát được, chẳng hạn lỗi close sau khi thân work đã thành công. Đây là thay đổi hành vi cần review theo contract. Không nên catch rồi nuốt tất cả lỗi close chỉ để bảo toàn một hành vi sai trước đó.

## 14. Dọn dẹp và transaction là hai bài toán khác nhau

Refactor close của database Connection bằng TWR không thay thế cho chính sách transaction. Trong JDBC:

- **Connection.close()** liên quan vòng đời connection/handle theo API hoặc pool.
- **commit()** xác nhận transaction.
- **rollback()** thử khôi phục thay đổi chưa commit.
- **setAutoCommit(false)** điều khiển cách JDBC kết thúc transaction theo hợp đồng.
- **close() thất bại** có thể đòi đánh dấu handle không đáng tin, tùy provider/pool.

Mẫu minh họa cho transaction do chính phương thức sở hữu:

~~~java
// Mã minh họa trong phương thức khai báo throws SQLException.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        performSql(connection);
        connection.commit();
    } catch (SQLException workFailure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            workFailure.addSuppressed(rollbackFailure);
        }
        throw workFailure;
    }
}
~~~

Đây là snippet theo ngữ cảnh, không phải một chương trình Java độc lập. Nó chỉ xử lý rollback trong nhánh SQLException bên trong; RuntimeException hoặc Error từ performSql cần được xét riêng nếu contract yêu cầu rollback trong những trường hợp đó. Nếu **setAutoCommit(false)** thất bại trước inner try, nhánh rollback này không chạy dù connection vẫn được TWR thử close.

**Kết luận của mục này:** TWR quản lý close; muốn bảo toàn dữ liệu cần chính sách commit/rollback/compensation riêng. Không dùng refactor tài nguyên để đưa ra lời hứa “mọi lỗi đều không làm thay đổi trạng thái”.

## 15. Xử lý interruption và cancellation trong cleanup

Nếu một luồng đang đợi công việc và ném **InterruptedException**, nó có thể rời thân try sớm. Nếu resource thuộc TWR, Java vẫn chạy close trên đường thoát đó.

~~~java
// Mã minh họa: resource implements AutoCloseable, waitForData
// có thể ném InterruptedException và method có hợp đồng thích hợp.
try (Resource resource = openResource()) {
    waitForData(resource);
}
~~~

Cần phân biệt:

- **InterruptedException**: tín hiệu thao tác chờ của thread bị interrupt.
- **CancellationException**: trạng thái hủy của Future/kết quả.
- **TimeoutException**: một lần chờ quá thời hạn, không tự đóng mọi resource của worker.
- **IOException từ close**: có thể là lỗi phụ khi đường interrupt đã tạo primary exception, hoặc là lỗi chính khi thân try hoàn tất.

TWR không tự cancel một task đang chạy trong thread khác. Nếu caller timeout và đóng resource trong khi worker vẫn sử dụng nó, có thể phát sinh race và lỗi mới. Refactor phải giữ đúng **ownership giữa các thread**.

Khi một phương thức cho phép lan truyền InterruptedException, thường nên truyền lên tầng sở hữu công việc. Nếu không thể truyền checked exception ở Runnable boundary, code có thể cần khôi phục interrupt flag và kết thúc. Chính sách này không được thay bằng catch(Exception) rồi bỏ qua chỉ vì muốn “đảm bảo cleanup”.

## 16. Trường hợp close cũng có side effect

Một số close không chỉ giải phóng bộ nhớ hoặc file descriptor:

- **BufferedWriter.close()** có thể flush dữ liệu được buffer.
- **ZipOutputStream.close()** có thể hoàn tất cấu trúc file nén.
- **Socket.close()** thay đổi khả năng I/O của đầu kết nối.
- **JDBC Connection.close()** có semantics riêng tùy datasource/pool.
- Một custom resource có thể gửi dữ liệu hoặc publish thông tin khi đóng.

Nếu thân try đã trả kết quả nhưng close ném exception, TWR có thể thay kết quả return bằng exception. Điều này thường là chính xác khi hợp đồng coi close là bước bắt buộc để hoàn tất công việc. Nhưng trong thiết kế API, cần xác định rõ **khi nào một thao tác được coi là thành công**.

**Đừng vô điều kiện retry close** sau khi nó ném lỗi: AutoCloseable không bắt buộc mọi implementation hỗ trợ gọi close nhiều lần theo cách idempotent. Hãy đọc contract và xác định trạng thái sau thất bại. Đóng được tài nguyên cũng không có nghĩa byte đã ghi hoặc side effect đã rollback.

Trong code review, tách câu hỏi “close có được thử?” khỏi câu hỏi “thao tác có đạt mục tiêu nghiệp vụ?”. Cả hai phải được xác minh.

## 17. TWR với catch/finally khác vẫn hợp lệ

Một cấu trúc TWR vẫn có thể có catch/finally riêng:

~~~java
// Mã minh họa.
try (Resource resource = openResource()) {
    perform(resource);
} catch (IOException failure) {
    log(failure);
    throw failure;
} finally {
    updateMetrics();
}
~~~

Thứ tự cleanup tự động của resource diễn ra trước khi catch/finally bao ngoài xử lý kết quả lỗi theo cấu trúc này. Catch có thể truy cập primary và suppressed đã được gắn khi close chạy.

Tuy nhiên, **updateMetrics()** trong finally nếu tự ném exception vẫn có thể che lỗi đang được truyền ra. TWR chỉ bảo toàn lỗi từ **close() của các resource trong resource specification** theo cơ chế của nó; nó **không bảo vệ mọi exception khác từ finally do người viết thêm**.

Đừng di chuyển cleanup cũ vào finally bên ngoài TWR nếu không cần. Nếu metrics/logging có thể thất bại, chính sách lỗi của các bước phụ đó cần được xác định: có nên báo lỗi, suppressed, log riêng hay tránh gây hại cho đường lỗi chính?

## 18. Khi có nhiều layer resource và ownership lồng nhau

Ví dụ stream đọc file được bọc qua các layer:

~~~java
// Mã minh họa trong phương thức có imports và throws IOException.
try (InputStream input = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(input);
     DataInputStream data = new DataInputStream(buffered)) {
    return data.readInt();
}
~~~

TWR sẽ đóng **data**, rồi **buffered**, rồi **input**. Nhưng **data.close()** có thể tự đóng buffered, buffered.close() đóng input. Những lần close tiếp theo có thể là redundant. Với nhiều stream JDK, đóng lặp thường được xử lý an toàn theo implementation, nhưng **không suy rộng sang mọi AutoCloseable**.

Một cách gọn hơn khi wrapper sở hữu delegate:

~~~java
// Mã minh họa.
try (DataInputStream data = new DataInputStream(
        new BufferedInputStream(Files.newInputStream(path)))) {
    return data.readInt();
}
~~~

Cách này dựa vào hợp đồng đóng theo chuỗi của wrapper. Nếu constructor của wrapper có thể thất bại sau khi inner resource đã được mở, phải xét exception safety của bước xây wrapper. Khi một factory có khả năng thất bại ở giữa, khai báo riêng resource ở những cấp phù hợp có thể dễ bảo đảm cleanup hơn.

**Không có một quy tắc cơ học “ít dòng hơn luôn an toàn hơn”**. TWR giúp biểu thị sở hữu, nhưng người refactor vẫn cần hiểu close lan truyền qua wrapper như thế nào.

## 19. Khi nào không nên thay toàn bộ manual cleanup bằng TWR?

Một số trường hợp không phù hợp với một block TWR đơn giản:

1. Resource là **borrowed object** mà caller hoặc framework sở hữu.
2. Resource phải tồn tại dài hơn phạm vi phương thức, chẳng hạn trả về stream để caller đọc.
3. Cleanup không phải là close đơn thuần mà cần **commit, rollback hoặc release** theo nhiều trạng thái.
4. Resource được dùng qua các bước bất đồng bộ và kết thúc sau khi method khởi tạo trả về.
5. API close có yêu cầu về thread cụ thể hoặc thứ tự/điều kiện khác TWR.
6. Object không implements AutoCloseable và adapter đơn giản làm sai semantics.
7. Tài nguyên thuộc scope dài hạn như cache, pool hoặc lifecycle của service.

Nếu một resource được tạo trong controller rồi giao cho background worker, đóng nó ngay khi controller return có thể làm worker thất bại. Nếu một connection được transaction manager cấp, đóng trực tiếp có thể phá policy của framework. Các trường hợp này cần thiết kế ownership rõ hơn, không phải chỉ thay cú pháp.

Phần lớn code mở resource để xử lý đồng bộ ngắn hạn vẫn là ứng viên rất tốt cho TWR.

## 20. Regression testing: chứng minh hành vi mới đúng

Chỉ test đường thành công thì refactor có thể trông ổn nhưng vẫn làm mất lỗi khi cleanup thất bại. Cần một resource giả có thể:

- Ghi nhận lần open/close và thứ tự.
- Ném exception trong work.
- Ném exception trong close.
- Tạo lỗi khi mở resource thứ hai.
- Theo dõi trạng thái resource trước và sau return.

Ma trận tối thiểu:

| Acquisition | Work | Close | Assertion quan trọng |
| --- | --- | --- | --- |
| Thành công | Thành công | Thành công | Resource được đóng, kết quả đúng |
| Thành công | Ném A | Thành công | A được truyền, close được gọi |
| Thành công | Thành công | Ném B | B được truyền, không báo thành công giả |
| Thành công | Ném A | Ném B | A primary, B suppressed |
| Mở A thành công, mở B ném C | Không chạy | Close A thành công | C primary, A đã đóng |
| Mở A thành công, mở B ném C | Không chạy | Close A ném D | C primary, D suppressed |
| Mở A và B thành công | Ném C | Close B và A ném D/E | Thứ tự B→A, C primary, suppressed D rồi E |
| Thành công | Return sớm | Thành công | Close trước khi return |
| Thành công | Return sớm | Ném B | Lời gọi ném B thay vì trả kết quả bình thường |
| Thành công | RuntimeException | Thành công | RuntimeException được giữ, close vẫn được thử |

**Một sai lầm của test:** Chỉ viết **assertThrows(IOException.class)** khi cả work lẫn close đều có thể ném IOException. Nếu close che work, test vẫn PASS vì loại IOException không thay đổi. Nên kiểm tra **message do test kiểm soát**, hoặc tốt hơn **object identity của primary**, cùng **getSuppressed()**.

Với JUnit Jupiter có thể sử dụng **assertThrowsExactly**, **assertSame**, **assertEquals** và các asserts về thứ tự event. Đừng cố định số dòng stack trace; số dòng thay đổi theo cách viết source, không phải contract của TWR.

## 21. Test helper để bơm lỗi vào close

Một custom resource phục vụ test có thể có các cờ trạng thái:

~~~java
// Mã minh họa cần đặt trong một class test phù hợp.
final class Probe implements AutoCloseable {
    int closeCalls;
    boolean failClose;

    @Override
    public void close() throws IOException {
        closeCalls++;
        if (failClose) {
            throw new IOException("probe close failed");
        }
    }
}
~~~

Trong test:

~~~java
// Minh họa JUnit; cần static imports JUnit Jupiter tương ứng.
Probe probe = new Probe();
probe.failClose = true;

IOException failure = assertThrowsExactly(IOException.class, () -> {
    try (probe) {
        throw new IOException("work failed");
    }
});

assertEquals("work failed", failure.getMessage());
assertEquals(1, probe.closeCalls);
assertEquals(1, failure.getSuppressed().length);
assertEquals("probe close failed",
             failure.getSuppressed()[0].getMessage());
~~~

Ví dụ này cần JUnit Jupiter trên classpath; nó không phải đoạn Java SE standalone. Cú pháp **try (probe)** hợp lệ từ Java 9 nếu biến local effectively final; việc thay đổi **probe.failClose** không thay đổi reference của biến probe.

Nếu test nhiều tài nguyên, dùng một **List<String> events** để ghi open, work, close. Khi assert, kiểm tra thứ tự sự kiện thay vì chỉ đếm closeCalls. Nếu resource wrapper tự đóng delegate, expectation đếm close phải dựa trên contract cụ thể.

## 22. Những regression về ownership cần kiểm tra

Một migration “đẹp” có thể tạo bug mới:

**Đóng resource của caller:** Hàm nhận InputStream từ caller rồi đặt ngay **try(input)**, khiến stream bị đóng khi caller vẫn muốn sử dụng.

**Đóng trước khi trả resource:** Factory trả resource từ một khối TWR, caller nhận object đã close.

**Đóng double:** TWR tự gọi close nhưng finally cũ vẫn gọi close; custom resource có thể không chịu được lần gọi thứ hai.

**Đóng sai thứ tự:** Resource nền bị đóng trước wrapper còn đang cần flush dữ liệu.

**Mở resource ngoài TWR rồi làm việc trước khi vào try:** Exception trong khoảng đó vẫn gây leak.

**Đổi exception contract vô tình:** Việc TWR bắt đầu truyền lỗi close khiến caller nhận checked exception mới, hoặc đổi lỗi chính so với một bug cũ. Cần document rõ sự thay đổi hợp lý.

**Bỏ rollback tưởng TWR đã làm hết:** Transaction lỗi nhưng dữ liệu có thể vẫn thay đổi dở; phải giữ riêng chính sách transaction.

**Kéo scope dài quá:** Resource giữ file descriptor/connection quá lâu, dù có TWR đúng cú pháp.

**Rút scope ngắn quá:** Resource bị close trước khi async task hoặc lazy stream xử lý xong.

Trước khi merge, hãy xác định **resource lifetime** bằng một ví dụ sử dụng thực tế, không chỉ thông qua khả năng biên dịch.

## 23. Ghi log lỗi sau migration

Một thay đổi dễ thấy là xuất hiện **suppressed exceptions** trong cây lỗi. Ví dụ một IOException từ read được giữ làm primary, trong khi IOException từ close đi theo suppressed. Hãy đảm bảo hệ thống log giữ đầy đủ Throwable:

~~~java
// Mã minh họa với logger hỗ trợ error(String, Throwable).
logger.error("Resource operation failed", failure);
~~~

Nếu chỉ log **failure.getMessage()**, bạn có thể bỏ qua lỗi close hoặc vị trí lỗi gốc. Nếu một service wrap primary thành domain exception, logger phải hiển thị cause chain để còn thấy suppressed trên cause.

Tuy vậy, không nên log ở mọi tầng catch rồi throw lại. Dễ phát sinh nhiều bản log của cùng một sự cố. Ưu tiên giữ Throwable đầy đủ khi truyền lỗi và log một lần tại ranh giới xử lý phù hợp, kèm operation ID, request ID hoặc tên resource không nhạy cảm.

Tránh in đường dẫn nội bộ, token, thông tin xác thực hoặc dữ liệu cá nhân vào message nếu hệ thống log có phạm vi truy cập rộng. Những thông tin này có thể có trong cause/suppressed của resource I/O.

## 24. Checklist cho người review refactor

Trước khi chấp nhận một pull request đổi manual cleanup sang TWR:

1. **Ownership:** Resource thuộc method này hay được caller/framework quản lý?
2. **Acquisition:** Resource được khởi tạo trong resource specification hoặc được bảo vệ ngay sau khi mở thành công?
3. **Lifetime:** TWR đóng đúng lúc, không đóng sớm trước khi caller/worker cần dùng?
4. **Loại API:** Resource implements AutoCloseable/Closeable; chữ ký close và checked exceptions có được xét?
5. **Nhánh thoát:** Exception checked/unchecked, Error, return, break, continue có cleanup đúng?
6. **Lỗi kép:** Work failure vẫn primary và close failure được suppressed?
7. **Thứ tự:** Với nhiều tài nguyên, thứ tự đóng ngược khai báo có phù hợp dependency?
8. **Đóng trùng:** Đã bỏ các finally/close thủ công dư hoặc close trùng delegate?
9. **Khởi tạo thất bại:** Nếu mở resource tiếp theo lỗi, resource đã mở trước có được dọn?
10. **Kết quả:** Nếu close lỗi sau work thành công, caller có thấy thất bại đúng hợp đồng?
11. **Tác dụng phụ:** Transaction/rollback/compensation có còn đầy đủ và tách khỏi close không?
12. **Async:** Resource có đang được dùng bởi một task sống lâu hơn scope TWR không?
13. **Test:** Đã có kịch bản open/work/close failure và kiểm tra primary/suppressed, state, số lần close?
14. **Quan sát:** Logging và monitoring có hiển thị suppressed, cause và không làm mất stack trace không?

Nếu chưa trả lời được câu nào vì hợp đồng API không rõ, đó là tín hiệu cần điều tra trước khi đổi code, không phải lý do vội vàng đặt mọi resource vào một block TWR.

## 25. Các câu hỏi tự kiểm tra

**Hỏi: TWR có luôn đóng resource khi thân try ném exception?**

Có, đối với các resource đã được khởi tạo thành công và thuộc resource specification, theo cơ chế Java thông thường. Nhưng nếu constructor/factory của một resource thất bại trước khi trả object, chính logic bên trong factory phải chịu trách nhiệm giải phóng những thứ nó đã cấp phát nội bộ.

**Hỏi: Nếu body và close cùng ném IOException, caller nhận cái nào?**

Body exception thường là primary; close exception là suppressed khi suppression hoạt động. Không nhầm với finally thủ công có thể khiến close che body.

**Hỏi: Có cần vẫn giữ finally sau khi thay bằng TWR?**

Không cần finally **chỉ để gọi close của chính những resource đã được TWR quản lý**. Có thể vẫn cần finally để cập nhật metric, giải phóng loại resource khác hoặc điều phối nghiệp vụ, nhưng phải xét khả năng phần finally đó tự gây lỗi mới.

**Hỏi: Một resource được mở trước try có dùng try(existing) được không?**

Được trên Java 9+ khi biến final/effectively final. Tuy nhiên, mọi bước thực thi giữa lần mở và lần bắt đầu TWR **không được bảo vệ bởi TWR đó**. Hãy đặt phạm vi gần điểm acquire thành công nhất có thể.

**Hỏi: TWR có tự retry close nếu nó thất bại không?**

Không. Nó gọi close theo quy tắc phạm vi. Retry cleanup là một chính sách riêng và có thể không an toàn nếu close không idempotent.

**Hỏi: Có thể dùng TWR trên Lock hoặc transaction API không?**

Chỉ trực tiếp nếu object implements AutoCloseable với semantics phù hợp; hoặc tạo adapter có kiểm soát. Với Lock/unlock và transaction commit/rollback, không nên dùng một adapter chung khi nó làm mất yêu cầu ownership và phục hồi trạng thái.

**Hỏi: Nếu có hai tài nguyên phụ thuộc nhau, Java đóng theo thứ tự nào?**

Từ resource khai báo cuối sang đầu. Hãy sắp khai báo theo dependency và tránh đóng lặp delegate do wrapper tự sở hữu.

**Hỏi: TWR có giúp operation atomic không?**

Không. Nó bảo đảm cleanup theo phạm vi, nhưng không hoàn tác dữ liệu đã ghi, request đã gửi hoặc trạng thái mutable đã sửa. Cần transaction, idempotency hoặc compensation riêng cho side effect.

## 26. Kết luận thực hành

**Tái cấu trúc cleanup thủ công sang try-with-resources** là cải tiến về **correctness, khả năng bảo trì và thông tin lỗi**. Nó giảm các đường thất bại bị bỏ quên, đóng những resource đã mở thành công, xử lý close ngược thứ tự và giúp giữ lỗi công việc làm primary khi cleanup tiếp tục lỗi.

Nhưng một refactor tốt không chỉ thay **try/finally** bằng dấu ngoặc **try (...)**. Nó phải bảo toàn **quyền sở hữu**, không đóng sớm hoặc đóng trùng, hiểu **checked exceptions**, và có test cho acquisition failure, work failure, close failure, return sớm và lỗi kép. Khi resource gắn với transaction hoặc async, còn phải giữ nguyên contract nghiệp vụ và vòng đời bên ngoài phạm vi method.

**Quy tắc nhớ nhanh:** Nếu method sở hữu một **AutoCloseable** trong một phạm vi ngắn, hãy ưu tiên TWR. Nếu ownership dài hạn, chia sẻ hoặc cleanup mang semantics khác close, hãy thiết kế vòng đời riêng và kiểm thử đầy đủ. Trong cả hai trường hợp, đừng chỉ kiểm tra resource được đóng trên đường thành công — hãy chứng minh tài nguyên và exception được xử lý đúng cả khi mọi thứ thất bại.
