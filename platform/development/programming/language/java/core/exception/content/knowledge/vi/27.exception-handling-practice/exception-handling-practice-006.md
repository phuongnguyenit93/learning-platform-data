# Tái hiện lỗi chính kèm nhiều suppressed exception

## 1. Mục tiêu thực hành

Một lỗi Java không nhất thiết chỉ gồm một exception. Khi chương trình đang thực hiện công việc thì phát sinh lỗi A, rồi quá trình dọn tài nguyên cũng thất bại với B, C và D, Java phải lựa chọn **lỗi nào đại diện cho thất bại chính** và **giữ những lỗi còn lại ở đâu**. Nếu chọn sai cách cleanup hoặc chỉ log một exception ở ngoài, bạn có thể mất bằng chứng quan trọng.

Trong bài thực hành này, bạn sẽ **chủ động tái hiện một lỗi chính cùng nhiều lỗi bị suppress** bằng `try-with-resources` và một tài nguyên giả triển khai `AutoCloseable`. Không cần làm hỏng file, socket hay database thật.

Sau khi hoàn thành, bạn có thể:

1. Tạo nhiều resource với thứ tự khởi tạo được kiểm soát.
2. Khiến thân `try` ném một `IOException` chính, trong khi nhiều `close()` cũng ném các `IOException` khác.
3. Quan sát Java đóng các resource **theo thứ tự ngược với khai báo** và tiếp tục đóng resource còn lại sau khi một `close()` thất bại.
4. Kiểm tra exception **primary**, số lượng và thứ tự của `getSuppressed()`.
5. Phân biệt lỗi **khởi tạo resource**, lỗi **thân công việc** và lỗi **đóng resource**.
6. Chứng minh một exception được bọc bằng `new IllegalStateException(message, cause)` **không tự chuyển suppressed từ cause sang wrapper**.
7. Viết assertion cho JUnit 5 bằng `assertSame`, `assertEquals` và lịch sử sự kiện thay vì chỉ kiểm tra “có exception”.
8. Hiểu giới hạn của fake: suppressed exception cho biết việc cleanup cũng lỗi, nhưng không chứng minh transaction được rollback hay dữ liệu đã được flush thành công.

### Kiến thức cần có

Bạn nên biết cơ bản về `try`, `catch`, `finally`, checked exception, `IOException` và giao diện `AutoCloseable`. Ví dụ chính dùng cú pháp Java 17 nhưng **không cần thư viện ngoài**, có thể chạy bằng `javac --release 17`. Những đoạn JUnit 5 được đánh dấu rõ là fragment cần một dự án đã cấu hình JUnit.

**Vấn đề trọng tâm:** một thao tác có thể xuất hiện nhiều lỗi cùng lúc, nhưng caller cần một kết cục chính có ý nghĩa. Những lỗi phụ không được phép vô tình xóa hoặc thay thế nguyên nhân chính.

## 2. Primary exception và suppressed exception là gì?

Trong cấu trúc `try-with-resources`, Java đảm nhiệm việc gọi `close()` khi thoát phạm vi. Nếu có nhiều exception, một exception là **primary** và những exception phát sinh trong quá trình cleanup có thể được **đính kèm** qua `Throwable.addSuppressed`.

Ví dụ tình huống:

~~~text
Mở A                       OK
Mở B                       OK
Mở C                       OK
Thực hiện body             IOException("body failed")
Đóng C                     IOException("close C failed")
Đóng B                     IOException("close B failed")
Đóng A                     IOException("close A failed")

Exception được ném ra ngoài:
    primary:    IOException("body failed")
    suppressed: IOException("close C failed")
                IOException("close B failed")
                IOException("close A failed")
~~~

Đây là **sơ đồ mô tả tình huống thực hành**, không phải output chính thức của chương trình. Nó minh họa hai quy tắc:

- Nếu **body đã ném lỗi**, lỗi đó giữ vai trò chính; các lỗi `close()` sau đó được thêm vào `getSuppressed()`.
- Nếu **body hoàn thành bình thường**, lỗi `close()` đầu tiên theo thứ tự đóng ngược trở thành primary; những lỗi đóng tiếp theo được suppress vào nó.

Phần suppressed là **dữ liệu chẩn đoán thật**, không phải “exception đã biến mất và có thể quên”. Nó có thể phản ánh lỗi flush dữ liệu, giải phóng kết nối, trả tài nguyên về pool hoặc đóng một handle khác.

### 2.1. Cause khác suppressed như thế nào?

| Quan hệ | API Java | Ý nghĩa phổ biến |
| --- | --- | --- |
| **Cause** | `getCause()`, constructor chứa `cause` | Ngoại lệ bên trong là nguyên nhân của exception bên ngoài |
| **Suppressed** | `getSuppressed()`, `addSuppressed()` | Ngoại lệ phụ xảy ra cùng lúc với một lỗi chính, thường khi cleanup |
| **Stack trace** | `getStackTrace()` | Những frame được ghi nhận cho từng exception |

Ví dụ `new IllegalStateException("Service failed", ioError)` tạo exception mới có cause là `ioError`. Nếu `ioError` có ba suppressed, ba lỗi này **vẫn thuộc `ioError`**. Không mặc định chúng được chép lên `IllegalStateException`.

Một primary có thể **đồng thời** có cause và suppressed. Khi chẩn đoán, phải đi theo cả hai nhánh thông tin, không chỉ `getCause()`.

## 3. Vì sao cần dùng fake resource để tái hiện?

Để tạo ra lỗi ở đúng thời điểm, đừng phụ thuộc vào việc filesystem hết dung lượng hoặc server đóng kết nối ngẫu nhiên. Điều đó làm test khó lặp lại và nguy hiểm cho dữ liệu. Thay vào đó, tạo một class có thể **chủ động ném exception** theo cờ cấu hình.

Một fake phục vụ mục tiêu này cần:

- Tên resource `A`, `B`, `C` để phân biệt.
- Danh sách `events` ghi thứ tự `open:A`, `close:C`, ...
- `failOpen` để làm constructor ném `IOException`.
- `failClose` để làm `close()` ném `IOException`.
- Thân công việc có thể chủ động ném exception riêng.
- Không dùng thread/sleep/network; trình tự sự kiện **deterministic**.
- Mỗi kịch bản có danh sách sự kiện mới để tránh kết quả bị nhiễm giữa các test.

Cấu hình lỗi tại **constructor** chỉ mô phỏng việc một initializer không hoàn tất. Nó chưa mô phỏng toàn bộ lỗi cấp phát dở bên trong constructor. Trường hợp tài nguyên mở nội bộ rồi constructor lỗi được bàn riêng ở phần sau.

## 4. Chương trình Java 17 hoàn chỉnh

Chương trình `SuppressedPracticeDemo` gồm bốn kịch bản độc lập:

1. `bodyAndThreeClosesFail()` — thân ném lỗi, ba `close()` cũng lỗi.
2. `secondOpenFails()` — A đã mở, B mở lỗi, Java phải đóng A.
3. `onlyClosesFail()` — thân thành công, nhưng ba `close()` cùng lỗi.
4. `wrappedFailure()` — lỗi đọc được wrap; suppressed vẫn nằm trên cause gốc.

Lưu toàn bộ code dưới đây thành file **`SuppressedPracticeDemo.java`**:

~~~java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class SuppressedPracticeDemo {
    static final class TrackedResource implements AutoCloseable {
        private final String name;
        private final List<String> events;
        private final boolean failClose;

        TrackedResource(String name, List<String> events,
                        boolean failOpen, boolean failClose) throws IOException {
            this.name = name;
            this.events = events;
            this.failClose = failClose;
            events.add("open:" + name);
            if (failOpen) {
                throw new IOException("open " + name + " failed");
            }
        }

        @Override
        public void close() throws IOException {
            events.add("close:" + name);
            if (failClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    static String identify(Throwable error) {
        return error.getClass().getSimpleName() + ": " + error.getMessage();
    }

    static void report(String title, List<String> events, Throwable error) {
        System.out.println(title);
        System.out.println("events=" + String.join(", ", events));
        System.out.println("primary=" + identify(error));
        Throwable[] suppressed = error.getSuppressed();
        System.out.println("suppressed-count=" + suppressed.length);
        for (int i = 0; i < suppressed.length; i++) {
            System.out.println("suppressed[" + i + "]=" + identify(suppressed[i]));
        }
    }

    static void bodyAndThreeClosesFail() {
        List<String> events = new ArrayList<>();
        IOException original = new IOException("body failed");
        try (TrackedResource a = new TrackedResource("A", events, false, true);
             TrackedResource b = new TrackedResource("B", events, false, true);
             TrackedResource c = new TrackedResource("C", events, false, true)) {
            events.add("work");
            throw original;
        } catch (IOException error) {
            report("CASE body-and-close", events, error);
            System.out.println("same-primary-object=" + (error == original));
        }
    }

    static void secondOpenFails() {
        List<String> events = new ArrayList<>();
        try (TrackedResource a = new TrackedResource("A", events, false, true);
             TrackedResource b = new TrackedResource("B", events, true, false);
             TrackedResource c = new TrackedResource("C", events, false, true)) {
            events.add("work");
        } catch (IOException error) {
            report("CASE open-failure", events, error);
        }
    }

    static void onlyClosesFail() {
        List<String> events = new ArrayList<>();
        try (TrackedResource a = new TrackedResource("A", events, false, true);
             TrackedResource b = new TrackedResource("B", events, false, true);
             TrackedResource c = new TrackedResource("C", events, false, true)) {
            events.add("work:ok");
        } catch (IOException error) {
            report("CASE close-only", events, error);
        }
    }

    static void wrappedFailure() {
        List<String> events = new ArrayList<>();
        try (TrackedResource a = new TrackedResource("A", events, false, true)) {
            events.add("work");
            throw new IOException("read failed");
        } catch (IOException original) {
            IllegalStateException wrapper =
                    new IllegalStateException("service failed", original);
            report("CASE wrapped", events, wrapper);
            System.out.println("cause=" + identify(wrapper.getCause()));
            System.out.println("cause-suppressed-count="
                    + wrapper.getCause().getSuppressed().length);
        }
    }

    public static void main(String[] args) {
        bodyAndThreeClosesFail();
        secondOpenFails();
        onlyClosesFail();
        wrappedFailure();
    }
}
~~~

### 4.1. Biên dịch và chạy

Cần JDK 17 hoặc mới hơn. Trong thư mục chứa file:

~~~bash
javac --release 17 SuppressedPracticeDemo.java
java SuppressedPracticeDemo
~~~

**Stdout chính xác đã kiểm chứng bằng biên dịch và thực thi thực tế:**

~~~text
CASE body-and-close
events=open:A, open:B, open:C, work, close:C, close:B, close:A
primary=IOException: body failed
suppressed-count=3
suppressed[0]=IOException: close C failed
suppressed[1]=IOException: close B failed
suppressed[2]=IOException: close A failed
same-primary-object=true
CASE open-failure
events=open:A, open:B, close:A
primary=IOException: open B failed
suppressed-count=1
suppressed[0]=IOException: close A failed
CASE close-only
events=open:A, open:B, open:C, work:ok, close:C, close:B, close:A
primary=IOException: close C failed
suppressed-count=2
suppressed[0]=IOException: close B failed
suppressed[1]=IOException: close A failed
CASE wrapped
events=open:A, work, close:A
primary=IllegalStateException: service failed
suppressed-count=0
cause=IOException: read failed
cause-suppressed-count=1
~~~

Đây là output của chính chương trình nêu trên khi chạy độc lập, không dựa vào đường dẫn máy, địa chỉ mạng hay thời điểm scheduler. Nếu bạn đổi tên resource, số lượng resource hoặc chuỗi exception, output thay đổi tương ứng.

### 4.2. Các yếu tố làm ví dụ deterministic

- `events` được ghi trong cùng một thread. Không có executor, không có callback async, không có phụ thuộc scheduling.
- Mỗi phương thức tự tạo `new ArrayList<>()`, do đó lịch sử của kịch bản này không dính vào kịch bản khác.
- Mỗi `TrackedResource.close()` luôn ghi sự kiện **trước khi** ném lỗi (nếu được cấu hình).
- Mỗi exception close có message chứa resource name.
- Thứ tự đóng được **ngôn ngữ Java xác định**: C → B → A.
- `IOException original` ở kịch bản đầu được tạo trước và ném trực tiếp, nên có thể kiểm tra **object identity** bằng `error == original`.

Điều này giúp test chỉ thất bại khi behavior thực sự khác kỳ vọng, không phải vì máy nhanh/chậm.

## 5. Phân tích kịch bản 1: một primary và ba suppressed

Trong `bodyAndThreeClosesFail()`, ba resource đều khởi tạo thành công. Thân `try` ghi `work` rồi ném **chính đối tượng** `original`.

Diễn biến:

~~~text
open A                  thành công
open B                  thành công
open C                  thành công
work                    ghi event
throw original          IOException("body failed")
        |
        v
close C                 ném IOException("close C failed")
        |               -> original.addSuppressed(closeC)
        v
close B                 ném IOException("close B failed")
        |               -> original.addSuppressed(closeB)
        v
close A                 ném IOException("close A failed")
                        -> original.addSuppressed(closeA)
        |
        v
catch (IOException e)
e == original           true
e.getSuppressed()       [closeC, closeB, closeA]
~~~

Quan sát:
- `primary=IOException: body failed` — body failure giữ vai trò chính.
- `suppressed-count=3` — ba lỗi close vẫn được giữ.
- `suppressed[0]` là C, `[1]` là B, `[2]` là A — đúng với thứ tự đóng ngược.
- `same-primary-object=true` — Java không bắt buộc tạo một wrapper mới chỉ vì cleanup lỗi; trong kịch bản này primary chính là object được body ném.

**Điểm học quan trọng:** một exception có thể chứa **nhiều** suppressed, không chỉ một. Nếu code điều tra chỉ gọi `getSuppressed()[0]`, bạn sẽ bỏ sót B và A. Nếu code log chỉ in `error.getMessage()`, thông tin đóng thất bại biến mất khỏi báo cáo.

### 5.1. Điều gì sẽ xảy ra nếu chỉ có hai close lỗi?

Nếu đổi `failClose` của resource B thành `false`, Java vẫn gọi B.close() nhưng nó không ném. Khi đó:
- Event log **vẫn có** `close:B`.
- Primary vẫn là `body failed`.
- Suppressed chỉ chứa close C và close A.
- Thứ tự suppressed là C rồi A; **không có phần tử placeholder** cho B thành công.

Vì vậy không thể dùng độ dài mảng suppressed để suy ra số resource đã đóng. Nó chỉ phản ánh số lỗi phụ được đính kèm, không phải tổng số lần cleanup.

## 6. Phân tích kịch bản 2: lỗi initializer và suppressed từ resource trước

Trong `secondOpenFails()`:
- A mở thành công, nhưng được cấu hình `failClose=true`.
- Constructor B ghi `open:B` rồi ném `IOException("open B failed")`.
- C chưa bao giờ được mở.
- Body không được thực thi.
- Java đóng A; A.close() ném lỗi và được suppress vào lỗi open B.

Sơ đồ:

~~~text
try (A = new Resource(...);
     B = new Resource(...);
     C = new Resource(...)) {
    work();
}

A tạo OK
B constructor throw   <-- primary
C không được tạo
body không chạy
A.close() throw        <-- suppressed
~~~

Vì vậy stdout có:

~~~text
events=open:A, open:B, close:A
primary=IOException: open B failed
suppressed-count=1
suppressed[0]=IOException: close A failed
~~~

**Không xuất hiện `close:B`** vì constructor B không trả về một resource hoàn chỉnh để try-with-resources đăng ký đóng. Không xuất hiện `open:C` hoặc `work` vì Java ngừng đánh giá các initializer tiếp theo khi B ném.

### 6.1. Nếu resource đang mở dở bên trong constructor?

Đây là tình huống khác với A đã mở hoàn chỉnh rồi B thất bại. Ví dụ B constructor mở một file nội bộ, sau đó đọc header bị lỗi. Try-with-resources **không tự gọi `B.close()`** nếu constructor B chưa hoàn thành.

Constructor/factory tạo B phải có **cleanup nội bộ khi partial acquisition thất bại**. Một thiết kế factory có thể sử dụng try/catch để đóng handle mới tạo trước khi ném exception, giữ lỗi init làm chính và thêm lỗi close bằng `addSuppressed()`.

Tuy nhiên cách chuyển quyền sở hữu phải được thiết kế cẩn thận: nếu factory trả về object thành công, object mới chịu trách nhiệm close; nếu factory thất bại, factory vẫn sở hữu và phải dọn những handle đã tạo. Test fake nên tách trường hợp **initializer B không hoàn tất** khỏi trường hợp **resource A đóng bị lỗi sau đó**.

## 7. Phân tích kịch bản 3: body thành công nhưng close thất bại

Trong `onlyClosesFail()`, body chỉ ghi `work:ok` và không ném exception. Nhưng khi thoát scope:

1. C.close() được gọi đầu tiên và ném `IOException("close C failed")`.
2. Java ghi nhận close C là **primary** vì chưa có body exception.
3. B.close() được gọi tiếp, lỗi của nó bị suppress vào primary C.
4. A.close() cũng được gọi và bị suppress.

Output trọng tâm:

~~~text
events=open:A, open:B, open:C, work:ok, close:C, close:B, close:A
primary=IOException: close C failed
suppressed-count=2
suppressed[0]=IOException: close B failed
suppressed[1]=IOException: close A failed
~~~

Đây là sự khác biệt quan trọng với kịch bản 1. **Primary không nhất thiết là exception từ body.** Nó là lỗi đầu tiên có vai trò chính theo luồng thực thi/cleanup của try-with-resources. Khi body thành công và close C lỗi, C trở thành primary.

Nếu body chạy hết mà code lại trả `"SUCCESS"` trong khi `close()` bị catch rỗng, caller có thể nhận thông báo sai. Với một số output stream, lỗi close còn có thể ảnh hưởng đến dữ liệu buffered chưa flush. Nhưng không được suy diễn rằng **mọi** close failure đều làm dữ liệu mất: điều đó tùy hợp đồng resource.

### 7.1. Trường hợp chỉ một close lỗi

Nếu C.close() thành công nhưng B.close() thất bại, B là primary. Nếu A.close() thất bại sau đó, A là suppressed. Nếu cả C/B/A đều thành công, không có exception từ cleanup; kết quả body có thể được trả bình thường.

Bảng kiểm tra nhanh:

| Body | Close C | Close B | Close A | Primary | Suppressed |
| --- | --- | --- | --- | --- | --- |
| Lỗi X | Lỗi C | Lỗi B | Lỗi A | X | C, B, A |
| Lỗi X | OK | Lỗi B | OK | X | B |
| OK | Lỗi C | Lỗi B | Lỗi A | C | B, A |
| OK | OK | Lỗi B | Lỗi A | B | A |
| OK | OK | OK | Lỗi A | A | Không có |
| OK | OK | OK | OK | Không có | Không có |

Thứ tự cột trong bảng là thứ tự **đóng thực tế**. Lưu ý khác thứ tự khai báo resource ở header.

## 8. Phân tích kịch bản 4: wrapper không tự mang suppressed của cause

Trong `wrappedFailure()`:
1. A mở bình thường.
2. Body ném `IOException("read failed")`.
3. A.close() ném `IOException("close A failed")`.
4. Primary gốc `read failed` có **một suppressed** là `close A failed`.
5. `catch` tạo `new IllegalStateException("service failed", original)`.
6. Chương trình in thông tin của **wrapper** và thông tin của **cause**.

Output:

~~~text
CASE wrapped
events=open:A, work, close:A
primary=IllegalStateException: service failed
suppressed-count=0
cause=IOException: read failed
cause-suppressed-count=1
~~~

Điều cần hiểu:
- `wrapper.getSuppressed()` rỗng trong kịch bản này, **không có nghĩa cleanup đã thành công**.
- `wrapper.getCause()` chính là IOException gốc; `wrapper.getCause().getSuppressed()` có một lỗi.
- Java **không tự sao chép** suppressed từ cause lên wrapper mới.
- Một hệ thống log phải in **cause chain và suppressed của từng throwable** nếu muốn đầy đủ bằng chứng.

Đừng sửa bằng cách “copy toàn bộ suppressed lên mọi wrapper” một cách máy móc; điều đó có thể tạo duplicate, nhầm quan hệ nguyên nhân hoặc làm báo cáo khó hiểu. Giữ cause đúng là cách tự nhiên để bảo toàn thông tin.

### 8.1. Cách truy cập đúng khi wrapper có cause

Fragment minh họa:

~~~java
Throwable primary = wrapper.getCause();
if (primary != null) {
    for (Throwable cleanupFailure : primary.getSuppressed()) {
        System.err.println("cleanup: " + cleanupFailure);
    }
}
~~~

`wrapper` giả định đã được tạo từ một exception có cause. Kiểm tra null là cần thiết vì không phải Throwable nào cũng có cause. Với một số exception lồng nhiều tầng, cần đi theo các cause khác nhau và kiểm tra suppressed của **đúng Throwable** chứ không chỉ wrapper ngoài cùng.

## 9. Ma trận kiểm thử nên thực hiện

Đây là những trường hợp quan trọng khi viết test về lifecycle:

| Case | Chương trình mô phỏng | Điều cần assert |
| --- | --- | --- |
| 1 | A/B/C mở thành công, body ném, C/B/A close đều ném | Body là primary, suppressed C/B/A |
| 2 | A mở, B initializer ném, A.close ném | Init B là primary, suppressed A |
| 3 | A/B/C mở thành công, body OK, C/B/A close ném | Close C primary, suppressed B/A |
| 4 | Body ném, close A ném, bọc lỗi vào IllegalStateException | Wrapper cause là body IOException; suppressed ở cause |
| 5 | Body ném, tất cả close OK | Body primary, suppressed rỗng |
| 6 | Body OK, tất cả close OK | Không exception; mọi resource đóng |
| 7 | A init ném ngay | Không mở B/C; body không chạy |
| 8 | C init ném sau A/B mở | B rồi A phải được đóng |
| 9 | C init ném, B/A close đều ném | Init C primary, suppressed B/A |
| 10 | Body OK, chỉ A.close ném | A primary, suppressed rỗng |
| 11 | Body ném, chỉ B.close ném | Body primary, suppressed B |
| 12 | Body có return, close ném | Close exception vẫn có thể ngăn caller nhận return bình thường |

Không cần viết lại toàn bộ chương trình cho từng case. Với fake có cờ failOpen/failClose, bạn đổi cấu hình từng resource và hành vi body. Nhưng hãy tạo **event list mới** và resource mới cho từng test để tránh Throwable/state dùng chung làm test phụ thuộc thứ tự.

### 9.1. Vì sao test chỉ `assertThrows` là chưa đủ?

Một test:

~~~java
assertThrows(IOException.class, () -> process());
~~~

Đây là **fragment JUnit 5**, cần `process()` và JUnit Jupiter. Nó chỉ chứng minh có một IOException thoát ra; nó không cho biết IOException từ body, init hay close, không chứng minh tất cả resource đã được thử đóng và không kiểm tra suppressed.

Một test tốt phải kiểm tra:
- Loại và identity/message của primary.
- Số lượng và thứ tự suppressed.
- Event log khởi tạo, sử dụng, cleanup.
- Không có body event nếu initializer thất bại.
- Resource nào **đã được** và **chưa được** khởi tạo.
- Các hậu điều kiện còn đúng sau lỗi.

## 10. Viết JUnit 5 assertion cho nhiều suppressed

Đoạn sau là **fragment test** giả định `SuppressedPracticeDemo.TrackedResource` nằm cùng package và test đã có JUnit Jupiter. Nó sử dụng `assertSame` để khẳng định đúng object lỗi thân, không chỉ cùng message.

~~~java
@Test
void bodyExceptionStaysPrimaryAndAllCloseFailuresAreSuppressed() {
    List<String> events = new ArrayList<>();
    IOException original = new IOException("body failed");

    IOException thrown = assertThrows(IOException.class, () -> {
        try (var a = new SuppressedPracticeDemo.TrackedResource(
                     "A", events, false, true);
             var b = new SuppressedPracticeDemo.TrackedResource(
                     "B", events, false, true);
             var c = new SuppressedPracticeDemo.TrackedResource(
                     "C", events, false, true)) {
            events.add("work");
            throw original;
        }
    });

    assertSame(original, thrown);
    assertEquals(3, thrown.getSuppressed().length);
    assertEquals("close C failed",
                 thrown.getSuppressed()[0].getMessage());
    assertEquals("close B failed",
                 thrown.getSuppressed()[1].getMessage());
    assertEquals("close A failed",
                 thrown.getSuppressed()[2].getMessage());
    assertIterableEquals(
            List.of("open:A", "open:B", "open:C", "work",
                    "close:C", "close:B", "close:A"),
            events);
}
~~~

Để đưa đoạn test này vào class JUnit 5, cần:
- `import org.junit.jupiter.api.Test;`
- `import java.util.List;`, `import java.util.ArrayList;`, `import java.io.IOException;`
- Static imports `assertThrows`, `assertSame`, `assertEquals`, `assertIterableEquals` từ `org.junit.jupiter.api.Assertions`.
- Class `SuppressedPracticeDemo` và nested `TrackedResource` có thể truy cập trong test (ví dụ cùng package).

### 10.1. Tại sao `assertSame` đáng giá?

Nếu chỉ dùng:

~~~java
assertEquals("body failed", thrown.getMessage());
~~~

bạn có thể đang kiểm tra **một wrapper mới có cùng message**. `assertSame(original, thrown)` chứng minh try-with-resources giữ đúng đối tượng exception được body ném, và các lỗi close được gắn trực tiếp lên đối tượng đó.

Điều này phù hợp cho **bài thực hành về Java exception mechanics**. Trong test nghiệp vụ thông thường, không phải API nào cũng cam kết caller nhận đúng cùng object Throwable; có thể có wrapper hợp lệ. Hãy assert identity khi chính contract cần điều đó.

## 11. Test lỗi khởi tạo resource B

Fragment JUnit 5:

~~~java
@Test
void failedSecondInitializerClosesFirstResource() {
    List<String> events = new ArrayList<>();

    IOException thrown = assertThrows(IOException.class, () -> {
        try (var a = new SuppressedPracticeDemo.TrackedResource(
                     "A", events, false, true);
             var b = new SuppressedPracticeDemo.TrackedResource(
                     "B", events, true, false);
             var c = new SuppressedPracticeDemo.TrackedResource(
                     "C", events, false, true)) {
            events.add("work");
        }
    });

    assertEquals("open B failed", thrown.getMessage());
    assertEquals(1, thrown.getSuppressed().length);
    assertEquals("close A failed",
                 thrown.getSuppressed()[0].getMessage());
    assertIterableEquals(
            List.of("open:A", "open:B", "close:A"), events);
}
~~~

Test này đặc biệt có ích vì nó phân biệt hai trách nhiệm:
- Java tự đóng những resource **đã được khởi tạo thành công trước đó**.
- Code khởi tạo của B chịu trách nhiệm xử lý **những tài nguyên nội bộ của B được cấp phát dở**, nếu có.

Không nên kỳ vọng `close:B` trong event log. Constructor B đã ném trước khi một instance hợp lệ được gán cho biến resource của try-with-resources.

### 11.1. Biến thể C init lỗi

Chuyển `failOpen=true` sang C, cho A/B `failClose=true`. Expected:
- Events: `open:A`, `open:B`, `open:C`, `close:B`, `close:A`.
- Primary: `open C failed`.
- Suppressed: `close B failed` rồi `close A failed`.
- Không có `work`; không có `close:C`.

Đây là bài tập mở rộng có thể dự đoán từ quy tắc, không cần đoán runtime.

## 12. Test lỗi chỉ xuất hiện ở `close()`

Fragment JUnit 5:

~~~java
@Test
void firstCloseFailureBecomesPrimaryWhenBodySucceeds() {
    List<String> events = new ArrayList<>();

    IOException thrown = assertThrows(IOException.class, () -> {
        try (var a = new SuppressedPracticeDemo.TrackedResource(
                     "A", events, false, true);
             var b = new SuppressedPracticeDemo.TrackedResource(
                     "B", events, false, true);
             var c = new SuppressedPracticeDemo.TrackedResource(
                     "C", events, false, true)) {
            events.add("work:ok");
        }
    });

    assertEquals("close C failed", thrown.getMessage());
    assertEquals(2, thrown.getSuppressed().length);
    assertEquals("close B failed",
                 thrown.getSuppressed()[0].getMessage());
    assertEquals("close A failed",
                 thrown.getSuppressed()[1].getMessage());
    assertIterableEquals(
            List.of("open:A", "open:B", "open:C", "work:ok",
                    "close:C", "close:B", "close:A"),
            events);
}
~~~

**Điểm cần nhấn:** mặc dù body đã hoàn thành, toàn bộ lời gọi `try-with-resources` vẫn có thể kết thúc bằng exception do `close()`. Không phải một ngoại lệ chỉ xảy ra “sau nghiệp vụ” thì mặc định có thể nuốt; với output stream, chính lúc đóng có thể phát hiện việc ghi chưa hoàn tất.

Ngược lại, không được kết luận close exception chắc chắn đã undo những thao tác trước đó. Để kiểm chứng dữ liệu, cần test với implementation thật hoặc mô hình trạng thái phù hợp.

## 13. Thử một lỗi giả “quan sát” nhưng không làm hỏng test

Khi nghiên cứu suppressed, hãy tạo ngoại lệ có thông điệp phân biệt:

~~~java
IOException body = new IOException("body failed");
IOException closeA = new IOException("close A failed");
IOException closeB = new IOException("close B failed");
~~~

Đây là fragment Java. Đừng tái sử dụng **cùng một đối tượng exception** cho body và close. Khi compiler sinh cleanup, nó có thể gọi `primary.addSuppressed(closeFailure)`. Nếu `closeFailure == primary`, `Throwable.addSuppressed` cấm self-suppression và có thể ném `IllegalArgumentException`, làm bài thử lệch khỏi tình huống intended.

Để kiểm tra **identity** của suppressed, có thể inject exception riêng cho từng resource:

~~~java
IOException errorB = new IOException("close B failed");
IOException errorA = new IOException("close A failed");
~~~

Fake hỗ trợ constructor nhận hai object này hoặc callback supplier phù hợp, và khi `close()` ném đúng object đã inject, test có thể `assertSame(errorB, suppressed[0])`. Tuy nhiên không cần phức tạp hóa ví dụ chính: kiểm tra type/message/order cùng event log đã diễn đạt hầu hết hành vi.

### 13.1. Vì sao không dùng một singleton Throwable cho cả suite?

`Throwable` là object **có trạng thái**: nó lưu stack trace, cause/suppressed và các thông tin liên quan. Tái sử dụng một exception instance giữa nhiều test có thể giữ các suppressed từ test trước, làm kết quả phụ thuộc thứ tự. Tạo instance mới cho từng case, đặc biệt khi đang dạy `getSuppressed()`.

## 14. Cách Java bảo toàn exception trong try-with-resources

Có thể hình dung Java biên dịch try-with-resources thành logic cleanup có tính chất sau:

~~~java
Throwable primary = null;
try {
    work();
} catch (Throwable thrown) {
    primary = thrown;
    throw thrown;
} finally {
    if (resource != null) {
        if (primary != null) {
            try {
                resource.close();
            } catch (Throwable closeFailure) {
                primary.addSuppressed(closeFailure);
            }
        } else {
            resource.close();
        }
    }
}
~~~

Đây là **pseudocode gần Java để giải thích một resource**, không phải bản dịch bytecode chính xác của mọi compiler/JDK và không phải đoạn code nên tự chép vào production. Với nhiều resource, compiler tạo cleanup lồng nhau để đóng theo thứ tự ngược. Ý nghĩa chính là:

- Nếu đã có primary từ body/initializer, close failure được gắn vào primary.
- Nếu chưa có primary, close failure có thể trở thành exception được ném ra.
- Các resource còn lại vẫn được cleanup theo cấu trúc lồng nhau.
- Compiler lo đúng quy tắc, tránh nhiều lỗi phổ biến của `finally` viết tay.

**Không nên dùng `catch (Throwable)` trong business code chỉ vì pseudocode ở đây làm vậy.** Đó là mô tả cách ngôn ngữ giữ tín hiệu ngoại lệ, không phải hướng dẫn catch mọi `Error` rồi tiếp tục chạy.

### 14.1. Mã `finally` tự viết thường che lỗi chính

Sai lầm quen thuộc:

~~~java
try {
    throw new IOException("body failed");
} finally {
    throw new IOException("close failed");
}
~~~

Đây là **fragment trong phương thức khai báo `throws IOException`**. Exception ném từ `finally` có thể thay thế exception đang lan ra từ body. Nếu tự viết cleanup nhiều resource:

~~~java
try {
    work();
} finally {
    b.close();
    a.close();
}
~~~

Đây là fragment với các biến/hàm chưa định nghĩa. Nếu B.close() ném, lời gọi A.close() có thể không bao giờ diễn ra; hơn nữa lỗi body có thể bị che. Với `AutoCloseable`, ưu tiên try-with-resources trừ khi có yêu cầu lifecycle đặc biệt và đã kiểm thử đủ nhánh.

## 15. Suppressed và cause nằm ở đâu khi log?

Trong ví dụ `wrappedFailure`, có hai object:

~~~text
IllegalStateException("service failed")         <-- wrapper ngoài
    suppressed: []                               <-- rỗng
    cause ->
        IOException("read failed")               <-- exception gốc
            suppressed:
                IOException("close A failed")
~~~

Nếu log chỉ in `wrapper.getMessage()`, bạn mất cả cause và suppressed. Nếu code đọc `wrapper.getSuppressed()` rồi kết luận “không có lỗi close”, kết luận đó **sai đối tượng**.

Khi logger có khả năng in Throwable đầy đủ, truyền exception object (không chỉ message) để nó có cơ hội hiển thị stack trace, cause chain và suppressed. Với ứng dụng nhiều tầng, nên chọn nơi logging chịu trách nhiệm để tránh log lặp lại một lỗi ở mọi catch.

### 15.1. `printStackTrace()` hiển thị các quan hệ

Fragment:

~~~java
try {
    runOperation();
} catch (IOException e) {
    e.printStackTrace();
}
~~~

Đây là fragment với `runOperation` giả định. Trong trường hợp exception có suppressed, output thường có phần `Suppressed: ...` kèm các frame của lỗi phụ và có thể có `... N more` cho những frame chung. Đừng xem `... N more` là lỗi đã mất; đó thường là ký pháp rút gọn stack frames trùng nhau.

Trong production, cân nhắc logging framework và bảo vệ dữ liệu nhạy cảm thay vì in tự do trên stderr. Bài thực hành dùng `report` in định dạng ngắn để stdout tất định, nhưng **không thay thế full stack trace** khi cần điều tra một lỗi thật.

## 16. Kết quả sau lỗi đóng: cleanup không đồng nghĩa rollback

Một trình tự thực tế:

~~~text
Mở output stream
Ghi 1000 byte
Thân công việc kết thúc
close() -> IOException
~~~

Lỗi đóng có thể phản ánh flush buffer thất bại. Nhưng muốn biết 1000 byte đã tồn tại/bền vững bao nhiêu, bạn phải dựa vào contract `OutputStream` cụ thể, filesystem và kiểm thử tích hợp. Một fake ném exception tại close **không thể chứng minh nội dung file thật đã rollback**.

Với JDBC cũng tương tự:
- Connection.close() không phải lệnh thay thế cho transaction rollback theo mọi driver/pool.
- Nếu commit đã xảy ra trước close, lỗi close không tự undo commit.
- Nếu mất kết nối tại commit, trạng thái có thể chưa xác định; cần đối soát.

Khi exception chính báo thao tác thất bại, không tự kết luận “chưa có tác động ngoài hệ thống”. Khi nhiều suppressed liên quan resource khác nhau, log phải giữ đủ ngữ cảnh để biết tài nguyên nào cần cleanup/đối soát bổ sung.

### 16.1. Có nên retry close khi close ném?

Không có một đáp án đúng cho mọi `AutoCloseable`. Một close có thể đã giải phóng tài nguyên rồi mới ném do flush lỗi; retry close có thể không có ích hoặc thậm chí gây side effect mới. Một số implementation bảo đảm close idempotent, số khác không.

Test fake có thể mô phỏng closeCount và trạng thái đóng nếu hợp đồng sản phẩm yêu cầu. Đừng áp đặt “lỗi close = chắc chắn còn mở” hoặc “gọi lần hai luôn an toàn” chỉ từ interface `AutoCloseable`.

## 17. Thêm close counter và cờ trạng thái nếu cần

Ví dụ mở rộng class fake:

~~~java
private int closeCount;
private boolean closed;

@Override
public void close() throws IOException {
    closeCount++;
    closed = true;
    events.add("close:" + name);
    if (failClose) {
        throw new IOException("close " + name + " failed");
    }
}
~~~

Đây là **fragment để thêm vào fake**, không phải một class hoàn chỉnh. Nếu đánh dấu `closed=true` **trước khi ném**, fake đang mô phỏng resource trở thành closed dù close báo lỗi. Nếu đánh dấu sau bước có thể ném, fake mô phỏng không chuyển trạng thái khi close lỗi. Cả hai là **giả định mô hình**; chọn cái khớp contract của resource thật trong test.

Trong một test đơn luồng, một `int` đếm close là đủ. Với code chạy đồng thời, dùng đồng bộ hóa hoặc `AtomicInteger` và đọc sau khi worker thật sự hoàn tất. `Future.isCancelled()` không tự chứng minh close đã chạy xong.

## 18. Test lỗi khi khởi tạo dở bên trong resource

Giả sử cần mở một input stream rồi đọc header trước khi trả object:

~~~java
static ParsedFile openParsedFile(Path path) throws IOException {
    InputStream in = Files.newInputStream(path);
    try {
        Header header = readHeader(in);
        return new ParsedFile(in, header);
    } catch (IOException | RuntimeException failure) {
        try {
            in.close();
        } catch (IOException cleanupError) {
            failure.addSuppressed(cleanupError);
        }
        throw failure;
    }
}
~~~

Đây là **fragment thiết kế**, cần định nghĩa `ParsedFile`, `Header`, `readHeader` và các imports `Files`/`Path`/`InputStream`/`IOException`. Ý tưởng:
1. Factory sở hữu stream sau khi `Files.newInputStream` thành công.
2. Nếu parsing hoặc construction lỗi trước khi ownership được chuyển, factory đóng stream.
3. Nếu close stream cũng lỗi, giữ parsing/construction exception làm primary và thêm close error làm suppressed.
4. Nếu trả object thành công, `ParsedFile` nhận trách nhiệm đóng stream trong `close()`.

Cần xác định thời điểm chuyển quyền sở hữu rất rõ. Nếu constructor `ParsedFile` ném **sau khi đã nhận stream**, code factory phải vẫn xử lý cleanup khi chưa có kết quả trả về. Trường hợp khởi tạo dở là lý do test resource initializer khác với test body failure.

### 18.1. Bài tập nhỏ về khởi tạo dở

Tạo `FakeInputStream` ghi sự kiện:
- `open:stream`;
- `readHeader` ném `IOException("invalid header")`;
- `close:stream` ném `IOException("stream close failed")`.

Expected: lỗi `invalid header` là primary, lỗi `stream close failed` là suppressed. Đồng thời hãy chắc chắn không có object `ParsedFile` được trả về. Đây là một test **factory cleanup**, không phải bằng chứng TWR sẽ close một object chưa khởi tạo xong.

## 19. Đừng tự gộp mọi exception vào một kết quả “thành công”

Nếu code:

~~~java
try (Resource a = openA();
     Resource b = openB()) {
    process(a, b);
} catch (IOException ignored) {
}
return true;
~~~

Đây là fragment giả định các type/hàm đã tồn tại. Nó có thể bỏ qua cả lỗi body và lỗi close/suppressed, rồi trả `true`. Caller mất khả năng phân biệt success với partial failure.

Nếu tầng hiện tại có quyền xử lý, có thể:
- Giữ và truyền exception cùng cause/suppressed.
- Chuyển sang kết quả có cấu trúc `Failure(code, cause)` nếu API sử dụng kiểu kết quả.
- Thực hiện cleanup/rollback hoặc compensation có kiểm soát rồi ghi trạng thái thực.
- Trả `UNKNOWN`/`PENDING` khi side effect bên ngoài chưa thể xác minh.

Không nên chuyển `IOException` thành `Optional.empty()` nếu empty nghĩa là không có dữ liệu; cũng không nên coi close failure là không quan trọng chỉ vì body đã chạy hết.

## 20. Thử nhiều resource mà không bỏ quên lỗi phụ

Một flow có ba resource có thể dùng thông tin:
- Resource ID: `A`/`B`/`C`.
- Loại lỗi: open/body/close.
- Vị trí lỗi chính.
- Danh sách suppressed với thứ tự và resource.
- Thời điểm resource đã hoàn thành init.
- Trạng thái side effect nếu có.
- Correlation ID/job ID trong test hệ thống nhiều request.

Với test đơn luồng và một event list, chỉ cần resource ID và message. Với hệ thống production, message kiểu `"close A failed"` có thể không đủ vì không biết A thuộc request nào. Đừng ghi token hoặc dữ liệu riêng tư chỉ để định danh resource; dùng ID kỹ thuật an toàn.

Một số Throwable ngoài đời có stack trace rút gọn do cấu hình runtime, nhưng `getSuppressed()` là API trực tiếp để đọc lỗi kèm theo. Nếu exception bị wrap nhiều tầng, hãy tìm đúng object primary ở nơi suppressed được gắn.

## 21. Bài tập nâng cao: nhiều suppressed nhưng không phải do close

`Throwable.addSuppressed` là API chung; dù try-with-resources là nguồn sử dụng quen thuộc nhất, ứng dụng cũng có thể chủ động bổ sung những lỗi thứ cấp vào một primary.

Ví dụ tổng hợp ba bước cleanup riêng:

~~~java
IOException primary = new IOException("operation failed");
try {
    cleanupCache();
} catch (IOException e) {
    primary.addSuppressed(e);
}
try {
    cleanupTempFile();
} catch (IOException e) {
    primary.addSuppressed(e);
}
throw primary;
~~~

Đây là **fragment** trong phương thức `throws IOException`, với hai hàm cleanup được giả định. Mẫu chỉ thích hợp nếu đã xác định:
- Primary là lỗi quan trọng nhất cần truyền.
- Hai cleanup không phụ thuộc nhau hoặc được phép thực hiện tiếp khi một bước lỗi.
- Mỗi exception là một object hợp lệ, không trùng primary.
- Không phải chuyển lifecycle của resource sang try-with-resources đơn giản hơn.
- Caller/logging nhận và xử lý lỗi được giữ, không catch rỗng ở tầng ngoài.

Tránh thêm vào primary chính object đó: `primary.addSuppressed(primary)` không hợp lệ. Tránh truyền null. Không giả định mọi Throwable đều bật suppression nếu có constructor tùy chỉnh vô hiệu hóa tính năng này.

## 22. Test bất đồng bộ khi exception bị bọc bởi Future

Nếu flow dùng fake chạy trong một `Callable` qua `ExecutorService.submit`, exception từ task có thể được truyền tới caller bằng `ExecutionException`. Lúc đó:
- `ExecutionException` là wrapper của việc quan sát thất bại qua Future.
- `wrapper.getCause()` là lỗi task ném ra.
- Suppressed của lỗi đóng thường nằm trên **cause**, không tự nằm trên `ExecutionException`.

Fragment JUnit 5:

~~~java
Future<?> future = executor.submit(() -> {
    try (Resource resource = openResource()) {
        doWork(resource);
    }
    return null;
});

ExecutionException wrapper = assertThrows(
        ExecutionException.class, future::get);

Throwable primary = wrapper.getCause();
Throwable[] cleanupFailures = primary.getSuppressed();
~~~

Đây là **fragment**, cần Java concurrency imports, JUnit Jupiter và các loại/hàm `Resource`, `openResource`, `doWork` đã định nghĩa. Trong test thật, nhớ shutdown executor trong cleanup hợp lệ. Không coi `Future.isDone() == true` là task thành công; nó có thể xong do failure/cancellation.

Nếu dùng `CompletableFuture.join()`, wrapper thường là `CompletionException` thay vì `ExecutionException`. Khi cần tìm suppressed, tiếp tục kiểm tra cause gốc. Một callback `whenComplete` ném exception mới có quy tắc ưu tiên riêng; nó không có nghĩa những lỗi observer tự động thành suppressed trên source.

### 22.1. Race với cancellation

`Future.cancel(true)` có thể yêu cầu interrupt nhưng không bảo đảm worker đã thực sự rời `try` và gọi `close()`. Muốn kiểm tra cleanup hoàn tất, dùng latch ở `finally` hoặc một kênh completion riêng. Đọc event log ngay sau khi `cancel()` trả `true` có thể quá sớm, gây test chập chờn. Đây không phải hạn chế của suppressed exceptions mà là vấn đề **vòng đời bất đồng bộ**.

## 23. Những lỗi phổ biến khi tự tái hiện suppressed exception

### 23.1. Chỉ tạo một lỗi đóng nhưng nghĩ có nhiều suppressed

Nếu body không ném và B.close() là close đầu tiên bị lỗi, nó sẽ là primary, **không phải suppressed**. Muốn nhiều suppressed, cần có body/initializer primary trước đó hoặc ít nhất một close failure primary rồi thêm các close failure tiếp theo.

### 23.2. Đóng theo thứ tự A rồi B rồi C

Try-with-resources với resource khai báo A/B/C đóng **C rồi B rồi A**. Nếu event log có thứ tự khác, hãy xem resource đã khai báo theo thứ tự nào, có code đóng thủ công hay không.

### 23.3. Kỳ vọng B.close chạy khi constructor B ném

Initializer không trả object thành công thì TWR không quản lý việc đóng chính B. Nó chỉ đóng các resource đã tạo thành công trước đó.

### 23.4. Chỉ kiểm tra exception ngoài cùng sau khi wrap

Nếu wrapper giữ cause, hãy xem `wrapper.getCause().getSuppressed()`. `wrapper.getSuppressed().length == 0` không chứng minh cleanup không lỗi.

### 23.5. Catch exception rồi ném wrapper không cause

~~~java
catch (IOException e) {
    throw new IllegalStateException("service failed");
}
~~~

Đây là fragment. Nó làm mất đường dẫn cause thông thường tới primary và suppressed, gây khó chẩn đoán. Dùng `new IllegalStateException("service failed", e)` khi bọc.

### 23.6. Catch và chỉ in `getMessage()`

`getMessage()` chỉ là message của một Throwable. Nó không tự liệt kê suppressed/cause/stack. Dùng logger có hỗ trợ Throwable đầy đủ hoặc đọc API trực tiếp.

### 23.7. Giả định mọi resource close lỗi đều chưa giải phóng

`close()` có thể ném trước hoặc sau khi giải phóng một phần tài nguyên. Trạng thái resource thực tùy contract; fake phải thể hiện đúng tình huống đang test.

### 23.8. Dùng cùng một exception ở hai vị trí ném

Làm vậy có thể kích hoạt self-suppression hoặc khiến suppressed từ test trước tồn tại trong test sau. Tạo exception riêng cho body và từng close.

### 23.9. Test chỉ dựa vào số dòng stack trace

Số dòng có thể đổi khi source được format/refactor. Bài thực hành cần assert semantics: primary identity/type, suppressed và event order, thay vì hardcode `Foo.java:47`.

### 23.10. Test không dọn executor hoặc tài nguyên thật

Khi test ngoài ví dụ đồng bộ, luôn quản lý vòng đời executor, temp directory và resource thật. Đừng cố gây lỗi đóng file bằng cách thay đổi permission/dung lượng một cách không kiểm soát trên hệ thống dùng chung.

## 24. Checklist hoàn thành bài thực hành

- [ ] Tạo fake implement `AutoCloseable`, có ID và lịch sử `open/close`.
- [ ] Bố trí ba tài nguyên A/B/C trong một try-with-resources.
- [ ] Body ném IOException có tên riêng.
- [ ] C/B/A close đều ném các IOException **khác object**.
- [ ] Xác nhận body failure là primary.
- [ ] Xác nhận `getSuppressed().length == 3`.
- [ ] Xác nhận suppressed đúng thứ tự C, B, A.
- [ ] Xác nhận `close:C`, `close:B`, `close:A` đều xuất hiện.
- [ ] Dùng `assertSame` để kiểm tra primary object nếu bài test cần identity.
- [ ] Mô phỏng B initializer thất bại, kiểm tra A vẫn đóng, C/body không chạy.
- [ ] Mô phỏng body thành công nhưng ba close fail, kiểm tra close C là primary.
- [ ] Tạo wrapper có cause và kiểm tra suppressed ở cause.
- [ ] Không viết cleanup tự làm mất primary hoặc bỏ quên resource.
- [ ] Không dùng exception singleton tái sử dụng giữa các case.
- [ ] Có ít nhất một test happy path để bảo đảm body và close bình thường.
- [ ] Phân biệt lỗi close với việc rollback/đảm bảo ghi dữ liệu.
- [ ] Chỉ kết luận test chạy đúng khi stdout/assertions phản ánh contract đã định.

## 25. Bài tập mở rộng có đáp án định hướng

### Bài A — Đổi resource B thành close thành công

Trong `bodyAndThreeClosesFail`, sửa B thành `failClose=false`, giữ body fail và A/C close fail. Trước khi chạy, dự đoán:
- Event log vẫn có `close:B`.
- Primary vẫn là `body failed`.
- Suppressed chỉ có `close C failed` và `close A failed`.
- Độ dài suppressed còn 2, đúng thứ tự C rồi A.

### Bài B — Thử C constructor lỗi sau A và B

A và B init thành công, C `failOpen=true`, A/B `failClose=true`. Dự đoán:
- Primary: `open C failed`.
- Suppressed: `close B failed`, `close A failed`.
- Event: `open:A` → `open:B` → `open:C` → `close:B` → `close:A`.
- Không có `close:C` và không có body event.

### Bài C — Không có body exception, chỉ B và A close lỗi

Cho C.close thành công, B/A.close ném. Dự đoán:
- Primary: `close B failed`.
- Suppressed: `close A failed`.
- Đầy đủ event close: C rồi B rồi A.

### Bài D — Một wrapper bên ngoài có nhiều cấp cause

Bọc IOException gốc bằng một `IllegalStateException`, rồi bọc tiếp bằng một `RuntimeException` khác có cause. Dùng `getCause()` hai lần để tìm original; sau đó đọc `getSuppressed()`. Không mong wrapper ngoài tự chứa các suppressed của original. Ghi một báo cáo ngắn phân biệt quan hệ cause và suppressed.

### Bài E — Mô phỏng side effect trước khi close lỗi

Fake có bộ đệm dữ liệu. Trong body ghi một record, sau đó close ném. Hãy xác định liệu record đã ghi vào state giả trước khi close hay chưa. Nếu yêu cầu “không thấy dữ liệu khi lỗi”, thêm staging/commit logic được kiểm thử rõ ràng. **Đừng giả định exception tự rollback state.**

## 26. Tổng kết

Để tái hiện chính xác **một lỗi chính kèm nhiều suppressed exception** trong Java, hãy tạo một fake `AutoCloseable` có thể ném lỗi khi đóng, đưa nhiều resource vào `try-with-resources` rồi chủ động ném exception từ thân hoặc một initializer.

Năm điều quan trọng nhất:

1. **Body/initializer đã ném lỗi:** lỗi đó là primary; close failures phía sau được lưu trong `getSuppressed()`.
2. **Body thành công:** lỗi close đầu tiên theo thứ tự đóng ngược là primary; các close failures tiếp theo là suppressed.
3. **Resource đóng theo thứ tự ngược:** với A/B/C được khai báo, Java đóng C/B/A; một close thất bại không ngăn compiler-generated cleanup thử đóng resource còn lại.
4. **Initializer thất bại:** resource đã mở thành công trước đó được cleanup; object chưa khởi tạo xong không tự được TWR gọi close.
5. **Wrapper có cause không tự sao chép suppressed:** muốn điều tra đủ lỗi, đọc cả `getCause()` lẫn `getSuppressed()` ở đúng đối tượng.

Một test tốt không dừng ở việc “có IOException”: nó kiểm tra **primary identity, số lượng và thứ tự suppressed, event log cùng trạng thái sau lỗi**. Đó là cách biến cơ chế exception handling của Java thành những bảo đảm có thể kiểm chứng, đồng thời tránh hứa quá mức về rollback hoặc thành công của tài nguyên bên ngoài.