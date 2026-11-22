# Nhiều lần close thất bại và thứ tự lỗi phụ trong Java

> **Java Core – Exception** · Phần: **Nguyên nhân và lỗi phụ** · Kiến thức Java 7+ về `try-with-resources`, `Throwable.getSuppressed()` và thứ tự đóng tài nguyên; ví dụ chạy với **Java 17+**.

## 1. Vấn đề cần giải quyết

Một đoạn Java có thể mở nhiều tài nguyên: tệp, socket, luồng I/O, kết nối cơ sở dữ liệu hoặc đối tượng tự triển khai `AutoCloseable`. Ngay cả khi thao tác chính thất bại, Java vẫn phải cố giải phóng các tài nguyên đã mở. Nhưng **nếu nhiều lời gọi `close()` cùng ném ngoại lệ**, chương trình nên báo lỗi nào trước? Có mất lỗi chính hay bỏ qua việc đóng tài nguyên còn lại không?

Câu trả lời của `try-with-resources`:

1. **Đóng theo thứ tự ngược với khai báo:** tài nguyên bên phải đóng trước, rồi dần sang trái.
2. **Cố đóng những tài nguyên còn lại** kể cả khi một lệnh `close()` ném lỗi.
3. **Giữ lại primary exception** (*ngoại lệ chính*) đã tồn tại từ initializer hoặc thân `try`, nếu có.
4. **Gắn lỗi từ `close()` vào primary** bằng `Throwable.addSuppressed()`, để đọc bằng `getSuppressed()`.
5. **Nếu chưa có primary**, lỗi đầu tiên xảy ra trong quá trình đóng trở thành primary; các lỗi đóng tiếp theo được suppressed vào exception ấy.

Kết quả là một đối tượng lỗi chính có thể đi kèm **nhiều ngoại lệ phụ**, chứ không phải Java ngừng đóng sau lỗi đầu tiên hoặc ném đồng thời nhiều exception độc lập.

Ví dụ khái quát:

~~~java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    doWork();
}
~~~

Đây là khung mã minh họa; cần định nghĩa các kiểu và phương thức để chạy độc lập. Nếu tất cả mở thành công, thứ tự đóng là **C → B → A**.

- Nếu `doWork()` ném lỗi X và cả ba lệnh đóng đều lỗi, **X là primary**; danh sách suppressed có lỗi đóng **C, B, A** theo thứ tự phát sinh.
- Nếu `doWork()` thành công nhưng cả ba lệnh đóng lỗi, **lỗi đóng C là primary**; suppressed chỉ gồm **lỗi đóng B, A**.
- Nếu C mở thất bại thì body không chạy, C không được đăng ký thành công để đóng; B và A vẫn được đóng theo **B → A**. **Lỗi mở C là primary**, lỗi đóng B/A là suppressed.

Bài này tập trung vào **nhiều lần close thất bại và thứ tự lỗi phụ**. Kỹ năng cần đạt: phân biệt *primary*, *suppressed* và *cause*, dự đoán đúng thứ tự đóng/lỗi, cũng như truy xuất đủ dữ liệu khi debug.

## 2. Phân biệt ba khái niệm: primary, suppressed, cause

### Primary exception

**Primary** là exception đang giữ vai trò chính của đường thất bại. Với try-with-resources, đó thường là exception phát sinh **trước khi bắt đầu đóng** (từ initializer/thân try). Nếu các bước trước đều thành công, lỗi **đầu tiên** trong chuỗi đóng trở thành primary.

Primary là đối tượng đi tới nhánh `catch` tương ứng, nếu được bắt. Nó **không nhất thiết** là exception xảy ra đầu tiên trong toàn bộ ứng dụng: việc đóng có thể chạy sau các bước thành công, và caller cũng có thể bọc ngoại lệ bằng wrapper khác. Luôn xét **phạm vi một cấu trúc try-with-resources**.

### Suppressed exception

Một exception phát sinh trong khi dọn dẹp có thể bị **suppressed** vào primary để không che mất nguyên nhân đang xử lý. API:

~~~java
Throwable[] extra = primary.getSuppressed();
~~~

trả về một mảng các đối tượng `Throwable` đã được gắn làm lỗi phụ. Phần tử ở chỉ số 0 là exception được thêm vào danh sách **sớm nhất**; các phần tử tiếp theo phản ánh thứ tự được thêm.

Trong chuỗi đóng C → B → A, nếu đã có primary và cả ba lần đóng lỗi thì:

~~~text
primary       = body failed
suppressed[0] = close C failed
suppressed[1] = close B failed
suppressed[2] = close A failed
~~~

Đây là ví dụ theo tình huống vừa nêu, không phải quy tắc rằng *mọi* suppressed exception trong Java đều do `close()`. Ứng dụng có thể tự gọi `addSuppressed()`; một thư viện cũng có thể bổ sung thông tin theo chính sách riêng. Thứ tự mảng là **thứ tự thêm vào**, còn thứ tự C/B/A là kết quả cụ thể của cách try-with-resources đóng tài nguyên.

### Cause

`getCause()` thể hiện **exception gây ra** một exception khác trong quan hệ *exception chaining*:

~~~java
throw new IllegalStateException("Cannot save document", ioFailure);
~~~

Đây là mã minh họa, giả định `ioFailure` là một Throwable phù hợp. Wrapper `IllegalStateException` mới có **cause = ioFailure**. Trong khi đó, suppressed exceptions là một danh sách phụ **trên một đối tượng Throwable**, không phải một liên kết cause duy nhất.

| Thuộc tính | Ý nghĩa | API truy xuất |
| --- | --- | --- |
| Primary | Exception chính được ném từ một phạm vi xử lý | Đối tượng nhận ở `catch` |
| Cause | Nguyên nhân được liên kết khi tạo/bọc exception | `ex.getCause()` |
| Suppressed | Các exception phụ được gắn vào cùng đối tượng, thường từ cleanup | `ex.getSuppressed()` |

**Không dùng hai thuật ngữ “cause” và “suppressed” thay thế nhau**: một primary có thể vừa chứa cause vừa chứa nhiều suppressed; từng suppressed cũng có stack trace và cause riêng.

## 3. Quy tắc thứ tự đóng: từ phải sang trái, kể cả khi close lỗi

Các tài nguyên trong header được khởi tạo từ **trái sang phải**, nhưng được đóng từ **phải sang trái**. Ví dụ:

~~~java
try (Resource a = open("A");
     Resource b = open("B");
     Resource c = open("C")) {
    work();
}
~~~

Đây là ví dụ minh họa chưa độc lập. Dòng thời gian nếu tất cả resource đã được khởi tạo:

~~~text
open A
open B
open C
work
close C    ← được gọi đầu tiên
close B    ← vẫn được gọi nếu close C ném lỗi
close A    ← vẫn được gọi nếu close B ném lỗi
~~~

Lý do là ngữ nghĩa của try-with-resources tương đương về mặt cơ chế với các phạm vi tài nguyên lồng nhau: tài nguyên mở sau được đóng trước, theo kiểu *last in, first out*.

Thứ tự này **xác định cả thứ tự lỗi phụ**. Ví dụ nếu body đã có lỗi X và cả C, B, A đều ném khi đóng, Java gặp lỗi đóng C trước, sau đó B, rồi A; lỗi sẽ được thêm vào suppressed theo cùng thứ tự đó.

Nếu một tài nguyên có tham chiếu `null`, phần đóng tự động **không gọi** `close()` trên nó. Nếu việc đóng một resource diễn ra bình thường, nó cũng **không góp exception** vào suppressed. Vì vậy các mục suppressed có thể ít hơn số tài nguyên đã khai báo.

## 4. Chương trình Java 17 hoàn chỉnh và stdout kiểm chứng

Lưu toàn bộ chương trình thành **`SuppressedCloseOrderDemo.java`**. Mọi ví dụ đều dùng cùng một lớp `TracedResource` có thể chủ động gây lỗi ở initializer hoặc `close()`; các message được viết cố định để output không phụ thuộc file hệ thống.

~~~java
import java.io.IOException;

public class SuppressedCloseOrderDemo {
    private static final class TracedResource implements AutoCloseable {
        private final String name;
        private final boolean failClose;

        private TracedResource(String name, boolean failOpen, boolean failClose)
                throws IOException {
            System.out.println("open " + name);
            if (failOpen) {
                throw new IOException("open " + name + " failed");
            }
            this.name = name;
            this.failClose = failClose;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (failClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    private static TracedResource open(
            String name, boolean failOpen, boolean failClose)
            throws IOException {
        return new TracedResource(name, failOpen, failClose);
    }

    private static void report(IOException ex) {
        System.out.println("primary=" + ex.getMessage());
        Throwable[] suppressed = ex.getSuppressed();
        for (int i = 0; i < suppressed.length; i++) {
            System.out.println("suppressed[" + i + "]="
                    + suppressed[i].getMessage());
        }
    }

    private static void bodyFails() {
        System.out.println("== body fails ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true);
             TracedResource c = open("C", false, true)) {
            System.out.println("body");
            throw new IOException("body failed");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void closeOnlyFails() {
        System.out.println("== close only fails ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true);
             TracedResource c = open("C", false, true)) {
            System.out.println("body ok");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void openFails() {
        System.out.println("== open fails ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true);
             TracedResource c = open("C", true, true)) {
            System.out.println("unreachable body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void middleCloseFails() {
        System.out.println("== middle close fails ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true);
             TracedResource c = open("C", false, false)) {
            System.out.println("body ok");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void clean() {
        System.out.println("== clean ==");
        try (TracedResource a = open("A", false, false);
             TracedResource b = open("B", false, false)) {
            System.out.println("body ok");
        } catch (IOException ex) {
            report(ex);
        }
        System.out.println("after");
    }

    public static void main(String[] args) {
        bodyFails();
        closeOnlyFails();
        openFails();
        middleCloseFails();
        clean();
    }
}
~~~

### Biên dịch và chạy

Dùng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 SuppressedCloseOrderDemo.java
java SuppressedCloseOrderDemo
~~~

**Stdout chính xác** đã đối chiếu sau khi biên dịch và chạy:

~~~text
== body fails ==
open A
open B
open C
body
close C
close B
close A
primary=body failed
suppressed[0]=close C failed
suppressed[1]=close B failed
suppressed[2]=close A failed
== close only fails ==
open A
open B
open C
body ok
close C
close B
close A
primary=close C failed
suppressed[0]=close B failed
suppressed[1]=close A failed
== open fails ==
open A
open B
open C
close B
close A
primary=open C failed
suppressed[0]=close B failed
suppressed[1]=close A failed
== middle close fails ==
open A
open B
open C
body ok
close C
close B
close A
primary=close B failed
suppressed[0]=close A failed
== clean ==
open A
open B
body ok
close B
close A
after
~~~

Chương trình được biên dịch với `javac --release 17` và chạy để kiểm chứng output. Không cần file đầu vào, thư viện bên ngoài hay chạy JUnit. Những tình huống gây lỗi đều được bắt và in theo một định dạng ổn định.

## 5. Giải thích tình huống body lỗi và ba close cũng lỗi

Phương thức `bodyFails()` mở A, B, C thành công; thân try in `body` rồi ném:

~~~java
throw new IOException("body failed");
~~~

Lúc đó primary đã tồn tại **trước khi giai đoạn đóng bắt đầu**. Java lần lượt:

1. Gọi `c.close()`, in `close C`, nhận `IOException("close C failed")` và thêm vào suppressed của body exception.
2. Gọi `b.close()`, in `close B`, nhận `IOException("close B failed")` và thêm vào suppressed tiếp theo.
3. Gọi `a.close()`, in `close A`, nhận `IOException("close A failed")` và thêm vào suppressed thứ ba.
4. Chuyển primary `IOException("body failed")` đến catch; handler in primary rồi duyệt mảng suppressed.

**Thứ tự bắt buộc trong cấu trúc này:**

~~~text
primary=body failed
suppressed[0]=close C failed
suppressed[1]=close B failed
suppressed[2]=close A failed
~~~

Đây là lý do quan trọng phải đọc **cả primary lẫn suppressed**. Nếu chỉ in `ex.getMessage()`, bạn chỉ thấy `body failed` và mất dấu ba vấn đề ở quá trình đóng.

**Không nhầm:** không có ba câu lệnh `throw` độc lập cùng thoát khỏi method một lúc. Java tiếp tục thực hiện cleanup và đính kèm ngoại lệ đóng vào một primary duy nhất.

## 6. Giải thích tình huống chỉ close thất bại

Trong `closeOnlyFails()`, mọi tài nguyên khởi tạo thành công và thân try cũng in `body ok`, không có exception trước khi bắt đầu đóng.

- C đóng đầu tiên và ném lỗi. Vì chưa có primary, lỗi `close C failed` được chọn làm **primary**.
- B đóng tiếp theo, cũng ném lỗi; lỗi B được suppressed vào lỗi C.
- A đóng cuối cùng, cũng ném lỗi; lỗi A là suppressed thứ hai.

Output:

~~~text
primary=close C failed
suppressed[0]=close B failed
suppressed[1]=close A failed
~~~

**Lỗi đóng đầu tiên không phải phần tử `suppressed[0]`**, bởi trong trường hợp không có lỗi trước đó, lỗi đóng đầu tiên **đã là primary**. Đây là khác biệt với phần 5, nơi primary tồn tại từ thân try, nên mọi lỗi đóng đều thuộc suppressed.

Từ đó không thể kết luận rằng body thành công thì method chắc chắn thành công: `close()` có thể biến một lần xử lý tưởng như bình thường thành exception.

## 7. Giải thích tình huống initializer cuối thất bại

Trong `openFails()`:

~~~java
try (TracedResource a = open("A", false, true);
     TracedResource b = open("B", false, true);
     TracedResource c = open("C", true, true)) {
    System.out.println("unreachable body");
}
~~~

Đây là đoạn trích từ chương trình đầy đủ, cần catch/throws như bên trên. A và B mở thành công. C bắt đầu khởi tạo, in `open C`, nhưng constructor ném `IOException("open C failed")` **trước khi trả về** một TracedResource thành công.

Hậu quả:

- **Body không chạy**, nên không có dòng `unreachable body`.
- **C không được tự động đóng** bởi resource specification này, vì initializer của C chưa hoàn thành và chưa giao tài nguyên C để quản lý. Không có `close C` trong stdout.
- **B và A đã được đăng ký thành công** nên vẫn được đóng, theo B → A.
- Lỗi mở C là primary; lỗi đóng B rồi A được suppressed theo thứ tự.

~~~text
primary=open C failed
suppressed[0]=close B failed
suppressed[1]=close A failed
~~~

Cần phân biệt **initializer đã bắt đầu làm việc** với **resource đã được khởi tạo thành công**. Nếu một factory tự mở file hoặc socket bên trong rồi thất bại trước khi bàn giao resource, caller không thể tự biết các tài nguyên trung gian ấy. Factory/constructor phải thiết kế cleanup riêng.

## 8. Nếu resource ngoài cùng đóng thành công, lỗi phụ bắt đầu từ đâu?

Trong `middleCloseFails()`:

- C đóng trước và **không lỗi**.
- B đóng tiếp theo, **ném lỗi đầu tiên** → lỗi B là primary.
- A đóng cuối cùng, cũng lỗi → lỗi A là suppressed.

~~~text
primary=close B failed
suppressed[0]=close A failed
~~~

Do C không ném exception, C **không xuất hiện trong mảng suppressed**. Số phần tử của suppressed **không bắt buộc bằng số resource được khai báo**, cũng không bằng số resource đã đóng. Chỉ các exception thực tế được thêm vào danh sách mới xuất hiện.

Ở nhánh `clean()`, cả việc mở, body và đóng đều bình thường, nên **không có primary và không có suppressed**. Chương trình in `after` sau khi mọi tài nguyên được đóng xong. Đó là đối chứng để thấy việc cleanup diễn ra cả khi không có lỗi.

## 9. Bảng quyết định để xác định primary và suppressed

Giả định header là A, B, C từ trái sang phải. Mỗi hàng là một lần chạy độc lập:

| Kịch bản | Thứ tự close được thử | Primary | Danh sách suppressed theo thứ tự |
| --- | --- | --- | --- |
| Body ném X, C/B/A đều lỗi đóng | C, B, A | X | C, B, A |
| Body thành công, C/B/A đều lỗi đóng | C, B, A | Lỗi C | Lỗi B, A |
| Body thành công, C đóng tốt, B/A lỗi | C, B, A | Lỗi B | Lỗi A |
| Body thành công, C/B đóng tốt, A lỗi | C, B, A | Lỗi A | Rỗng |
| C lỗi lúc khởi tạo, B/A lỗi đóng | B, A | Lỗi mở C | Lỗi B, A |
| B lỗi lúc khởi tạo, A lỗi đóng | A | Lỗi mở B | Lỗi A |
| Body ném X, mọi close thành công | C, B, A | X | Rỗng |
| Body và mọi close thành công | C, B, A | Không có | Không có |

**Công thức suy luận:** Ghi ra các resource **đã khởi tạo thành công**. Đảo thứ tự danh sách ấy để tìm chuỗi `close()`. Nếu có exception từ body/initializer, giữ nó làm primary; mỗi lỗi đóng vào suppressed. Nếu chưa có exception chính, lỗi đóng đầu tiên là primary; lỗi đóng sau là suppressed.

Bảng này giả định những exception được tạo bình thường, suppression được bật (mặc định với các exception chuẩn trong ví dụ), không có mã tự gọi `addSuppressed()` ở nơi khác và không có exception mới từ catch/finally ngoài thay thế đường điều khiển.

## 10. Tại sao Java vẫn cố close những resource còn lại?

Mô hình try-with-resources tương đương về hành vi đóng với **các phạm vi tài nguyên lồng nhau**, mỗi tài nguyên có dọn dẹp riêng:

~~~java
try (Resource a = openA()) {
    try (Resource b = openB()) {
        try (Resource c = openC()) {
            doWork();
        }
    }
}
~~~

Đây là cấu trúc minh họa; cần định nghĩa kiểu/method phù hợp. Về mặt quan sát, resource trong cùng một header được xử lý như cấu trúc lồng nhau đó, vì thế tài nguyên tạo cuối rời phạm vi đầu tiên.

Một cách mô tả ý tưởng cho **một** resource (*pseudocode*, không phải bản sao nguyên văn của mã compiler sinh ra):

~~~java
Throwable primary = null;
try {
    body();
} catch (Throwable error) {
    primary = error;
    throw error;
} finally {
    if (resource != null) {
        if (primary != null) {
            try {
                resource.close();
            } catch (Throwable closeError) {
                primary.addSuppressed(closeError);
            }
        } else {
            resource.close();
        }
    }
}
~~~

Các biến/method trong pseudocode là tượng trưng. Với nhiều resource, các phạm vi lồng nhau tiếp tục đóng từ trong ra ngoài ngay cả khi resource phía trong ném lỗi, nên một lần đóng thất bại không đồng nghĩa bỏ qua những tài nguyên còn lại.

Đây là sự khác biệt với đoạn tự gọi close thủ công thiếu xử lý ngoại lệ:

~~~java
c.close();
b.close();
a.close();
~~~

Nếu `c.close()` ném exception ở dòng đầu, hai lời gọi `b.close()` và `a.close()` **có thể không chạy**. Ngay cả khi dùng `finally` thủ công, để tái tạo chính xác cơ chế primary/suppressed của try-with-resources cũng cần quản lý lỗi cẩn thận, dễ thiếu hoặc che nguyên nhân gốc.

## 11. getSuppressed() trả về gì và duyệt như thế nào?

`Throwable.getSuppressed()` trả về một mảng `Throwable[]` chứa các đối tượng đã được đính kèm vào exception đó. Một primary có thể có 0, 1 hoặc nhiều suppressed exception.

Ví dụ:

~~~java
catch (IOException ex) {
    System.err.println("PRIMARY: " + ex);
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("SUPPRESSED: " + suppressed);
    }
}
~~~

Đây là một handler minh họa trong ngữ cảnh try phù hợp, không phải chương trình độc lập.

### Thứ tự trong mảng có ý nghĩa gì?

Theo hợp đồng API, các exception suppressed được trả về theo **thứ tự đã bị suppress/thêm vào**. Try-with-resources đóng theo thứ tự ngược với khai báo, nên nếu mỗi resource ném lỗi khi đóng và đã có primary thì thứ tự mảng thường chính là **thứ tự các lần đóng lỗi**.

Ví dụ nếu C, B, A cùng ném:

~~~text
getSuppressed()[0] → lỗi C.close()
getSuppressed()[1] → lỗi B.close()
getSuppressed()[2] → lỗi A.close()
~~~

Nhưng nếu C.close() thành công, không có phần tử dành cho C. Nếu body đã tự gọi `primary.addSuppressed(extra)` trước khi cleanup, danh sách có thể **chứa extra trước các lỗi close**. Vì vậy không nên suy từ index sang một tài nguyên cụ thể nếu không biết cách exception được xây dựng.

### Có thể tự gọi addSuppressed không?

Có. API:

~~~java
primary.addSuppressed(other);
~~~

gắn một Throwable khác vào primary khi suppression được bật. Nó hữu ích trong các cơ chế cleanup tùy chỉnh, nhưng **không nên tự thêm lại lỗi close** mà try-with-resources đã thêm, vì sẽ gây lặp và làm sai cách diễn giải.

Quy tắc API cần nhớ:

- `addSuppressed(null)` ném `NullPointerException`.
- `primary.addSuppressed(primary)` ném `IllegalArgumentException` vì không cho phép tự suppress chính mình.
- Mặc định các exception chuẩn cho phép suppression. Nếu exception được tạo với suppression disabled, `addSuppressed()` không lưu thêm lỗi phụ.
- `getSuppressed()` trả về một mảng mới mỗi lần gọi; sửa mảng do getter trả về không làm thay đổi danh sách bên trong exception.

Những tính chất này giúp phân biệt suppressed exception với một collection do ứng dụng tự lưu. Trong mã nghiệp vụ thông thường, **đọc suppressed để chẩn đoán** là nhu cầu phổ biến hơn việc tự gọi addSuppressed.

## 12. In stack trace để không bỏ sót lỗi phụ

Nếu chương trình chỉ ghi:

~~~java
System.err.println(ex.getMessage());
~~~

thì sẽ không thể biết primary có bao nhiêu suppressed exception, cũng không nhìn thấy stack trace nguồn gốc của từng lỗi. Đối với debug, hãy giữ cả đối tượng Throwable khi log:

~~~java
ex.printStackTrace();
~~~

Theo API Java, `printStackTrace()` hiển thị exception chính, các cause và những suppressed exception liên quan, với cấu trúc thụt lề giúp phân biệt.

Ví dụ hình thức minh họa:

~~~text
java.io.IOException: body failed
    at ...
    Suppressed: java.io.IOException: close C failed
        at ...
    Suppressed: java.io.IOException: close B failed
        at ...
    Suppressed: java.io.IOException: close A failed
        at ...
~~~

**Đây không phải output tuyệt đối.** Số frame, số dòng, tên lớp và phần rút gọn kiểu `... N more` phụ thuộc call stack và định dạng của JVM. Không nên viết test so sánh nguyên văn toàn bộ `printStackTrace()`.

Với logging framework phù hợp, truyền **đối tượng exception** cho logger, thay vì chỉ lưu message; ví dụ API `java.util.logging`:

~~~java
logger.log(java.util.logging.Level.SEVERE, "Processing failed", ex);
~~~

Đây là đoạn minh họa, giả định có biến `logger` đã khai báo. Một hệ thống quan sát tốt nên lưu được **primary, cause, suppressed và stack trace** nhưng vẫn tuân thủ chính sách tránh log thông tin nhạy cảm.

## 13. Cause và suppressed trong trường hợp bọc exception

Giả sử tầng xử lý không muốn lộ trực tiếp `IOException` đến caller, nên bọc:

~~~java
try {
    executeWork();
} catch (IOException ex) {
    throw new IllegalStateException("Batch processing failed", ex);
}
~~~

Đây là mã minh họa, giả định `executeWork()` khai báo ném IOException.

Nếu `ex` có ba suppressed exception, wrapper mới có:

- `wrapper.getCause() == ex`.
- `ex.getSuppressed()` vẫn chứa ba lỗi close.
- `wrapper.getSuppressed()` **không tự sao chép** ba lỗi ấy sang wrapper.

Muốn xem lỗi đóng, người điều tra cần đi theo **cause** để tới đối tượng `ex` rồi xem suppressed trên đó. Nếu chỉ xem suppressed của wrapper mới, rất có thể mảng rỗng. Đây là lý do công cụ logging nên hỗ trợ **cả cây Throwable**, không chỉ exception ngoài cùng.

**Không nên tự chuyển suppressed sang wrapper bằng cách copy bừa**: một lỗi xuất hiện nhiều lần có thể gây log trùng và làm thay đổi cấu trúc nguyên nhân. Giữ exception gốc làm cause thường đã bảo tồn dữ liệu.

## 14. Khi suppression bị vô hiệu hóa

Một subclass của Throwable có thể dùng constructor bảo vệ để đặt `enableSuppression=false`:

~~~java
class NoSuppressionException extends Exception {
    NoSuppressionException(String message) {
        super(message, null, false, true);
    }
}
~~~

Đây là định nghĩa lớp minh họa, có thể đặt ở cấp top-level hoặc trong class khác. Tham số thứ ba `false` **tắt suppression**, còn tham số thứ tư `true` vẫn cho phép ghi stack trace. Hai tính năng này độc lập.

Nếu một `NoSuppressionException` là primary trong body, còn các lời gọi close sau đó ném lỗi:

- Java vẫn thực hiện cơ chế đóng các tài nguyên đã mở.
- Nó vẫn thử suppress lỗi close vào primary theo quy tắc tương ứng.
- Do **primary tắt suppression**, lỗi close không được lưu trong mảng suppressed.
- `primary.getSuppressed().length` sẽ bằng 0.

Điều này rất quan trọng khi debug một hệ thống sử dụng exception tùy biến: **mảng suppressed rỗng không phải bằng chứng tuyệt đối rằng mọi close đều thành công**. Có thể suppression đã bị tắt theo thiết kế exception.

Đừng tắt suppression hoặc stack trace cho exception nghiệp vụ chỉ để tối ưu hiệu năng mà chưa cân nhắc khả năng chẩn đoán. Nếu quan sát nhiều lỗi cleanup là quan trọng, hãy giữ suppression bật.

## 15. Nếu finally bên ngoài lại throw thì sao?

Với:

~~~java
try (Resource a = openA(); Resource b = openB()) {
    work();
} catch (IOException ex) {
    report(ex);
} finally {
    after();
}
~~~

Đây là cấu trúc minh họa chưa độc lập. Việc đóng a/b xảy ra **trước khi catch/finally của extended try-with-resources** xử lý kết quả. Sau cleanup và xử lý lỗi, một `finally` ở ngoài vẫn được thực thi theo quy tắc Java.

Nếu chính `finally` ngoài ném một exception khác, kết quả điều khiển cuối cùng có thể chuyển sang exception mới; điều đó là **quy tắc của finally**, tách biệt với cơ chế suppressed do try-with-resources tự thực hiện.

Trong mã sản xuất, tránh những đoạn cleanup tự viết phức tạp trong finally khi đã có try-with-resources, và đừng dùng `return` trong finally để vô tình che exception được bảo toàn cẩn thận từ resource cleanup.

## 16. Mở resource cũng có thể lỗi trước khi body bắt đầu

Suppressed không chỉ dành cho trường hợp body đã chạy. Nếu khởi tạo tài nguyên thứ ba thất bại, những tài nguyên trước đó vẫn được đóng và có thể ném exception. Trong ví dụ `openFails()`:

~~~text
open A
open B
open C
close B
close A
primary=open C failed
suppressed[0]=close B failed
suppressed[1]=close A failed
~~~

B và A được đóng dù thân try **không được vào**. Vì thế nếu một chương trình gặp lỗi khởi tạo kết nối/tệp, **vẫn phải xem suppressed** để biết các kết nối/tệp đã mở trước đó có được giải phóng thành công hay không.

Ngược lại, initializer của C đã bắt đầu nhưng không trả về tài nguyên C thành công, nên cấu trúc này không cố `C.close()`. Nếu factory C đã mở resource trung gian rồi thất bại, trách nhiệm cleanup ở chính factory, không ở resource specification đã không nhận được C.

## 17. Sự liên quan của kiểu ngoại lệ close

`AutoCloseable.close()` được khai báo có thể ném `Exception`. Một lớp cụ thể thường thu hẹp kiểu này, như ví dụ `TracedResource.close() throws IOException`. Khi phân tích checked exception ở compile time, Java xem xét những ngoại lệ có thể đến từ initializer, body và close.

Vì vậy một ví dụ:

~~~java
static void handle() throws IOException {
    try (TracedResource resource = open("R", false, true)) {
        System.out.println("work");
    }
}
~~~

là minh họa dựa trên lớp `TracedResource` ở chương trình chính. Phương thức này phải khai báo/handle `IOException`, ngay cả khi body chỉ in text, bởi initializer/close vẫn có thể ném IOException.

Nếu resource có kiểu tĩnh là `AutoCloseable` và `close()` khai báo ném `Exception`, bạn có thể cần xử lý hoặc khai báo kiểu checked rộng hơn. Multi-catch hoặc nhiều catch riêng vẫn áp dụng theo quan hệ subtype.

Không phải mọi close thất bại đều thuộc IOException: các triển khai có thể ném unchecked exception. Cơ chế primary/suppressed căn cứ vào các Throwable thực tế được ném; hãy kiểm tra hợp đồng tài nguyên.

## 18. Những lỗi hiểu sai hay gặp

- **“Nhiều close lỗi thì lỗi cuối cùng thắng.”** Sai: nếu body/initializer đã lỗi, chúng giữ primary; nếu chưa lỗi, **lỗi close đầu tiên** là primary.
- **“Suppressed luôn bắt đầu bằng lỗi resource đóng đầu tiên.”** Chỉ đúng nếu đã có primary trước lúc đóng; nếu chưa có, lỗi đóng đầu tiên chính là primary.
- **“Resource nào khai báo trước đóng trước.”** Sai: đóng từ **phải sang trái**.
- **“B.close lỗi thì A.close không chạy.”** Sai với try-with-resources: Java vẫn cố đóng các tài nguyên trước đó.
- **“Body chạy bình thường nghĩa là không có exception.”** Sai: close có thể tạo primary.
- **“Nếu initializer cuối lỗi thì không resource nào đóng.”** Sai: các resource trước đó đã khởi tạo thành công được đóng.
- **“Initializer lỗi vẫn được tự động close.”** Không nếu nó chưa bàn giao một resource được khởi tạo thành công; factory cần tự cleanup nội bộ.
- **“Lỗi bị suppressed là lỗi đã bị mất.”** Sai: bình thường có thể truy xuất qua `getSuppressed()`.
- **“Suppressed và cause là cùng một danh sách.”** Sai: `getCause()` là liên kết nguyên nhân; `getSuppressed()` trả về mảng lỗi phụ.
- **“Bọc primary vào wrapper sẽ tự chuyển suppressed sang wrapper.”** Sai: suppressed ở primary được giữ khi primary làm cause, không tự copy thành suppressed của wrapper.
- **“Đổi phần tử trong mảng getSuppressed thay đổi Throwable gốc.”** Sai: getter trả mảng mới.
- **“Suppressed rỗng chứng minh close không lỗi.”** Không tuyệt đối; suppression có thể đã bị tắt.
- **“Có ba resource nên luôn có ba suppressed.”** Sai: những resource đóng thành công không tạo lỗi; khi không có primary trước, lỗi close đầu tiên thành primary.
- **“Chỉ cần in message của IOException.”** Dễ mất cả suppressed, cause và dấu vết stack.
- **“Try-with-resources tự rollback những lần ghi file/database.”** Sai: nó quản lý đóng tài nguyên, không tạo transaction.
- **“Finally bên ngoài luôn bảo toàn primary đã có.”** Nếu finally tự ném/return bất thường, nó có thể che hoặc thay đổi đường điều khiển.

## 19. Cách tự giải một bài dự đoán output

Đối với mọi bài có nhiều resource, thực hiện lần lượt:

1. **Ghi danh sách initializer** theo thứ tự từ trái sang phải, đánh dấu initializer đầu tiên không hoàn tất bình thường nếu có.
2. **Ghi những resource đã mở thành công**. Nếu initializer thứ n lỗi, các initializer sau n không chạy.
3. **Xác định body có chạy hay không**, và body có ném exception nào không.
4. **Xác định primary ban đầu**: lỗi initializer/body nếu có; nếu không, chưa có primary trước khi close.
5. **Đảo danh sách tài nguyên thành công** để có thứ tự đóng (bên phải trước).
6. **Duyệt từng close theo thứ tự**. Nếu close thành công: không thêm lỗi. Nếu close lỗi và chưa có primary: chọn nó làm primary. Nếu đã có primary: gắn vào suppressed (trừ khi suppression bị tắt hay trường hợp đặc biệt theo API).
7. **Chỉ sau cleanup mới xét catch/finally ở ngoài**; xem handler có thay đổi hay truyền tiếp exception không.
8. **Viết stdout theo thời gian xảy ra**, không dự đoán theo thứ tự khai báo catch hay theo thứ tự trái→phải của resource.

### Bài tập 1

Khai báo A, B, C. Body ném X; C.close() thành công; B.close() ném Y; A.close() ném Z. Primary và suppressed?

**Đáp án:** primary X; suppressed [Y, Z]. Thứ tự close vẫn C → B → A, nhưng C không đóng góp suppressed vì không lỗi.

### Bài tập 2

Khai báo A, B, C. Body thành công; C.close() ném X; B.close() ném Y; A.close() thành công.

**Đáp án:** primary X; suppressed [Y]. A.close() vẫn được gọi dù có hai lỗi trước đó.

### Bài tập 3

A mở thành công; B khởi tạo thất bại với X; A.close() ném Y.

**Đáp án:** body không chạy. Primary X; suppressed [Y]. B không được close tự động nếu chưa khởi tạo thành công.

### Bài tập 4

Body ném X, và các lần close ném Y rồi Z. Sau đó code bọc X bằng `new IllegalStateException("failed", X)`. Lỗi Y/Z nằm ở đâu?

**Đáp án:** Y và Z là suppressed của X. Wrapper mới có cause là X; suppressed của wrapper không tự chứa Y/Z.

### Bài tập 5

Body thành công, C đóng bình thường, B đóng lỗi X, A đóng lỗi Y. Có thể viết `suppressed[0]=X` không?

**Đáp án:** Không. X là **primary**; suppressed[0] là Y.

### Bài tập 6

Một primary được tạo với suppression disabled; body ném primary, A.close() và B.close() đều lỗi. Có thể dựa vào `getSuppressed().length == 0` để khẳng định hai close thành công không?

**Đáp án:** Không. Các exception cleanup có thể không được lưu do suppression bị tắt.

## 20. Tài liệu Java chính thức

- [Java SE 17 JLS – try-with-resources (mục 14.20.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): cú pháp resource specification, vòng đời tài nguyên và cleanup.
- [Java SE 17 JLS – basic try-with-resources (mục 14.20.3.1)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.1): cơ chế tương đương các try lồng nhau, primary và suppressed.
- [Java SE 17 JLS – extended try-with-resources (mục 14.20.3.2)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.2): phối hợp cleanup với catch và finally.
- [Java SE 17 API – Throwable.addSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#addSuppressed(java.lang.Throwable)): quy tắc gắn exception phụ.
- [Java SE 17 API – Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): mảng exception phụ và thứ tự trả về.
- [Java SE 17 API – AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng phương thức `close()`.
- [Oracle Java Tutorials – try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): ví dụ cơ bản về primary và suppressed; khi cần độ chính xác theo phiên bản, ưu tiên JLS Java 17.

**Kết luận:** Khi có nhiều tài nguyên, Java đóng theo thứ tự **ngược với thứ tự khai báo** và vẫn cố đóng phần còn lại nếu một lần close thất bại. Nếu đã có lỗi từ initializer/body, lỗi đó là **primary**, còn lỗi đóng được thêm vào suppressed theo thứ tự xảy ra. Nếu chỉ close thất bại, **lỗi close đầu tiên là primary**, các lỗi sau là suppressed. Muốn debug đầy đủ, hãy theo dõi cả **primary, cause, suppressed và stack trace**, không chỉ message của lỗi chính.