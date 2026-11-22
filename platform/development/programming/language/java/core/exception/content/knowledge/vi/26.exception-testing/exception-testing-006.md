# Tạo fake resource để mô phỏng lỗi khởi tạo hoặc close trong Java

## 1. Tại sao phải thử lỗi ở lúc mở và lúc đóng tài nguyên?

Trong Java, những tài nguyên như file stream, socket, database connection, transaction handle hoặc client của hệ thống ngoài thường có **vòng đời**: khởi tạo/cấp phát → sử dụng → đóng/giải phóng. Lỗi không chỉ xảy ra khi xử lý dữ liệu. Việc **mở tài nguyên** có thể thất bại; việc **đóng tài nguyên** cũng có thể ném exception, kể cả khi phần thân công việc đã chạy thành công.

Nếu chỉ kiểm thử trường hợp “mở được, dùng được, đóng được”, chương trình có thể giấu những lỗi nghiêm trọng:

- Tài nguyên A đã mở, nhưng khởi tạo tài nguyên B thất bại. A có được đóng không?
- Thân `try` ném exception, rồi `close()` cũng ném. Exception nào đến caller? Lỗi phụ có bị mất không?
- Thân `try` hoàn tất bình thường, nhưng `close()` ném. Caller có bị báo thất bại không?
- Có hai resource, mỗi `close()` đều ném. Java có tiếp tục đóng resource còn lại không?
- Constructor thất bại **sau khi đã cấp phát một phần tài nguyên nội bộ**. Ai chịu trách nhiệm dọn phần đã cấp phát đó?
- Resource có bị đóng hai lần, bỏ quên hoặc bị dùng sau khi đóng?
- Một test sử dụng file/network/database thật có tái hiện được lỗi ở **đúng điểm mong muốn**, hay dễ bị chập chờn bởi môi trường?

Một **fake resource** là một implementation thử nghiệm có hành vi được điều khiển bằng dữ liệu và cờ lỗi. Nó có thể ghi lại các sự kiện như `init:A`, `close:B`, đếm lần đóng và chủ động ném `IOException` ở các điểm chỉ định. Nhờ vậy, test tập trung vào **hợp đồng vòng đời**, không phụ thuộc đĩa thật hỏng hay mạng thật mất kết nối.

Mục tiêu của bài này là tạo và sử dụng fake resource với Java 17 để chứng minh thứ tự giải phóng, lỗi chính (*primary exception*), lỗi bị kèm theo (*suppressed exceptions*) và hậu điều kiện khi khởi tạo hoặc đóng thất bại.

## 2. Cơ chế Java phải hiểu trước khi viết fake

### 2.1. `AutoCloseable` là hợp đồng đóng tài nguyên

Giao diện cơ bản:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

Đây là **chữ ký minh họa** của `AutoCloseable`, không phải một file triển khai mới cần tạo. Một class triển khai có thể thu hẹp checked exception, chẳng hạn khai báo `close() throws IOException`. `Closeable` trong `java.io` là một giao diện con có hợp đồng và cách dùng cụ thể cho I/O.

Cú pháp try-with-resources:

~~~java
try (Resource resource = acquire()) {
    use(resource);
}
~~~

Là **fragment minh họa** (cần có `Resource`, `acquire` và `use`). Java tự gọi `close()` khi rời khối, dù thân chạy bình thường hay thoát bởi exception, `return` hoặc một luồng điều khiển được hỗ trợ. Việc đóng tuân theo quy tắc ngoại lệ của try-with-resources; bản thân `close()` có thể ném exception mới.

**Quan trọng:** try-with-resources giúp gọi cleanup cho những resource đã khởi tạo thành công, **không tự động khôi phục side effect** như một lần ghi file, commit database hay gửi HTTP request trước khi lỗi.

### 2.2. Đóng theo thứ tự ngược với lúc khai báo

~~~java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    doWork();
}
~~~

Fragment trên khai báo hai resource. Nếu cả hai khởi tạo thành công, thứ tự đóng là **`second.close()` rồi `first.close()`**. Đây là quy tắc xác định của Java, không phụ thuộc scheduler hay tốc độ máy.

Nếu `openSecond()` ném exception trong quá trình khởi tạo, resource `first` đã được cấp thành công vẫn phải được đóng. Nhưng `second` **không được đăng ký như một resource đã khởi tạo thành công** và không được try-with-resources gọi `close()`. Nếu việc tạo `second` đã mở một socket nội bộ trước khi ném, code khởi tạo của nó có trách nhiệm dọn tài nguyên mở dở.

### 2.3. Lỗi trong body và lỗi trong `close()`

Quy tắc cốt lõi:
- **Thân `try` ném A, `close()` ném B:** A vẫn là lỗi chính, B được gắn vào A qua `getSuppressed()`.
- **Thân chạy bình thường, `close()` ném B:** B trở thành lỗi chính đi ra khỏi try-with-resources.
- **Nhiều resource đóng cùng thất bại:** Java vẫn cố đóng các resource còn lại. Thứ tự đóng ngược quyết định lỗi nào được xem là chính nếu thân không có lỗi.
- **Khởi tạo resource tiếp theo ném A, resource đã mở đóng ném B:** A là lỗi chính, B được kèm như suppressed.

Các quy tắc này rất phù hợp để kiểm thử bằng fake, vì test có thể gây lỗi tại đúng chỗ mà không cần ép filesystem/network thật thất bại.

## 3. Fake resource khác mock và stub ở điểm nào?

Có ba cách mô phỏng thường gặp:

| Loại | Đặc điểm | Khi nào thích hợp |
| --- | --- | --- |
| **Fake** | Có implementation đơn giản có trạng thái thật trong bộ nhớ; ghi sự kiện, thay đổi trạng thái, chủ động ném lỗi theo cấu hình | Kiểm tra vòng đời resource, thứ tự đóng, trạng thái sau failure |
| **Stub** | Trả các giá trị hoặc exception được lập trình sẵn; thường ít logic/trạng thái | Điều khiển kết quả của dependency để test một nhánh |
| **Mock** | Đối tượng do công cụ/hàm tạo để xác minh interaction, số lần gọi, đối số và thứ tự | Test collaborator call contract qua Mockito hoặc cơ chế tương tự |

Các thuật ngữ này có thể giao nhau tùy cộng đồng và framework. Bài này chọn **fake viết bằng Java thuần**, vì implementation có trạng thái (event log, cờ fail, số lần close), tái hiện được hành vi mà không phải phụ thuộc thư viện mock.

Một fake tốt cần:
- **Điều khiển lỗi rõ ràng:** có thể chọn lỗi khi init, khi dùng, khi close.
- **Ghi nhận sự kiện:** bảo đảm test phân biệt `init`, `use`, `close` theo đúng thứ tự.
- **Hành vi deterministic:** không random, không `Thread.sleep` để “đoán” thời điểm lỗi.
- **Có identity:** biết resource nào là A, B, C.
- **Lặp lại được:** mỗi test tạo fresh fake/event log, không để state từ test trước rò sang test sau.
- **Chân thực vừa đủ:** mô phỏng đúng hợp đồng AutoCloseable, không giả định một hành vi cleanup mà tài nguyên thật không cam kết.

Đừng quá mô phỏng toàn bộ database/socket nếu mục tiêu chỉ là xác nhận Java gọi `close()` và giữ exception. Fake quá phức tạp có thể gây bug riêng trong test.

## 4. Ví dụ Java 17 hoàn chỉnh: ba tình huống init/body/close

Chương trình sau đủ để biên dịch/chạy, **không cần JUnit hay thư viện bên thứ ba**. `FakeResource` ghi các sự kiện vào một `List<String>` và có hai cờ độc lập:

- `failInit`: ném `IOException` trong constructor sau khi ghi dấu `init`.
- `failClose`: ghi dấu `close` rồi ném `IOException` khi được gọi đóng.

Hàm `report` ghi lỗi chính và từng exception trong `getSuppressed()`. Ba kịch bản bao phủ các nhánh trọng tâm.

Lưu chính xác thành **`FakeResourceFailureDemo.java`**:

~~~java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class FakeResourceFailureDemo {
    static final class FakeResource implements AutoCloseable {
        private final String name;
        private final List<String> events;
        private final boolean failClose;

        FakeResource(String name, List<String> events,
                     boolean failInit, boolean failClose) throws IOException {
            this.name = name;
            this.events = events;
            this.failClose = failClose;
            events.add("init:" + name);
            if (failInit) {
                throw new IOException("init " + name + " failed");
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

    static void report(String label, List<String> events, IOException failure) {
        events.add("primary:" + failure.getMessage());
        for (Throwable suppressed : failure.getSuppressed()) {
            events.add("suppressed:" + suppressed.getMessage());
        }
        System.out.println(label + " -> " + String.join(" | ", events));
    }

    static void bodyAndCloseFail() {
        List<String> events = new ArrayList<>();
        try (FakeResource a = new FakeResource("A", events, false, true);
             FakeResource b = new FakeResource("B", events, false, true)) {
            events.add("body");
            throw new IOException("body failed");
        } catch (IOException failure) {
            report("body-fail", events, failure);
        }
    }

    static void secondInitFails() {
        List<String> events = new ArrayList<>();
        try (FakeResource a = new FakeResource("A", events, false, true);
             FakeResource b = new FakeResource("B", events, true, false)) {
            events.add("unreachable");
        } catch (IOException failure) {
            report("init-fail", events, failure);
        }
    }

    static void closeOnlyFails() {
        List<String> events = new ArrayList<>();
        try (FakeResource a = new FakeResource("A", events, false, true);
             FakeResource b = new FakeResource("B", events, false, true)) {
            events.add("body:ok");
        } catch (IOException failure) {
            report("close-fail", events, failure);
        }
    }

    public static void main(String[] args) {
        bodyAndCloseFail();
        secondInitFails();
        closeOnlyFails();
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ từ thư mục chứa file:

~~~bash
javac --release 17 FakeResourceFailureDemo.java
java FakeResourceFailureDemo
~~~

**Stdout đã kiểm chứng bằng JDK 17:**

~~~text
body-fail -> init:A | init:B | body | close:B | close:A | primary:body failed | suppressed:close B failed | suppressed:close A failed
init-fail -> init:A | init:B | close:A | primary:init B failed | suppressed:close A failed
close-fail -> init:A | init:B | body:ok | close:B | close:A | primary:close B failed | suppressed:close A failed
~~~

### 4.1. Kịch bản 1 — body và cả hai close cùng lỗi

Trong `bodyAndCloseFail()`:
1. `FakeResource A` khởi tạo thành công.
2. `FakeResource B` khởi tạo thành công.
3. Thân `try` thêm sự kiện `body` rồi ném `IOException("body failed")`.
4. Java gọi `B.close()` trước; nó ghi `close:B` và ném `IOException("close B failed")`.
5. Java tiếp tục gọi `A.close()`; A ghi `close:A` và cũng ném.
6. `catch` nhận lỗi `body failed` làm **primary**, còn hai lỗi đóng nằm trong `failure.getSuppressed()` theo thứ tự B rồi A.

Kiểm tra đáng chú ý: **B và A đều được thử đóng, dù B.close() đã ném exception.** Nếu dùng `finally` tự viết sai, bạn có thể vô tình bỏ qua lần đóng A khi B.close thất bại.

### 4.2. Kịch bản 2 — constructor B lỗi khi A đã mở

Trong `secondInitFails()`:
1. Constructor A ghi `init:A`, khởi tạo thành công.
2. Constructor B ghi `init:B` rồi ném `IOException("init B failed")`.
3. Thân `try` **không chạy**, nên `unreachable` không xuất hiện.
4. A là resource đã tạo thành công, vì vậy Java gọi `A.close()`.
5. B không được gọi `close()` vì constructor không trả một resource hoàn chỉnh.
6. `A.close()` cũng ném, nhưng lỗi `init B failed` giữ vai trò primary; lỗi `close A failed` là suppressed.

Đây là một phép thử thường bị bỏ sót. Nó chứng minh try-with-resources **không chỉ đóng sau khi body bắt đầu**, mà còn cleanup những resource đã khởi tạo thành công trước một resource initializer bị lỗi.

### 4.3. Kịch bản 3 — body thành công, close thất bại

Trong `closeOnlyFails()`, phần thân chỉ thêm `body:ok`. Khi rời khối:
1. B.close() ném lỗi và trở thành **primary**.
2. A.close() vẫn được gọi, lỗi của nó trở thành **suppressed** đi kèm lỗi B.
3. Caller không thể nói toàn bộ thao tác “thành công không có lỗi”, dù body chạy hết.

**Lưu ý nghiệp vụ:** lỗi đóng có thể hoặc không ảnh hưởng tới dữ liệu đã xử lý tùy loại resource. Đối với một số output stream, lỗi `close`/flush có thể đồng nghĩa dữ liệu chưa được ghi đầy đủ. Với resource khác, close lỗi có thể chỉ ảnh hưởng cleanup. Phải biết hợp đồng của resource thật; không tự suy rằng dữ liệu luôn bị mất hoặc luôn đã được lưu.

## 5. Ma trận hành vi của try-with-resources

| Resource initializer | Body | Close | Exception đến caller |
| --- | --- | --- | --- |
| Tất cả thành công | Thành công | Tất cả thành công | Không có exception |
| A mở thành công, B init lỗi | Không chạy | A đóng thành công | Lỗi init B |
| A mở thành công, B init lỗi | Không chạy | A.close lỗi | Init B chính; close A suppressed |
| Tất cả mở thành công | Ném X | Tất cả close thành công | X |
| Tất cả mở thành công | Ném X | B.close ném Y | X chính; Y suppressed |
| Tất cả mở thành công | Thành công | B.close ném Y | Y chính |
| Tất cả mở thành công | Thành công | B.close ném Y, A.close ném Z | Y chính; Z suppressed |
| Tất cả mở thành công | Ném X | B.close ném Y, A.close ném Z | X chính; Y và Z suppressed |
| A init lỗi ngay từ đầu | Không chạy | Không có resource header nào đã khởi tạo hoàn tất | Lỗi init A; cleanup bên trong A do implementation chịu trách nhiệm |

Với bảng này, “lỗi init” là exception được ném ra trong quá trình khởi tạo resource; **lỗi đóng** là exception từ `close()`. Nếu loại lỗi không phải `IOException` mà là `RuntimeException`, nguyên tắc primary/suppressed vẫn áp dụng trong những điều kiện thông thường của try-with-resources.

Một `catch (IOException e)` chỉ nhận IOException phù hợp. Nếu fake ném một unchecked exception không thuộc IOException từ `close()` hoặc body, chương trình cần một catch/throws phù hợp với type đó; không nên catch `Throwable` rộng chỉ để mọi test luôn “pass”.

## 6. Thiết kế fake có thể tiêm lỗi từng điểm

Ở ví dụ runnable, constructor nhận:

~~~java
FakeResource(String name,
             List<String> events,
             boolean failInit,
             boolean failClose) throws IOException
~~~

Đây là **chữ ký fragment** của constructor đã có trong chương trình. Cách dùng hai boolean đủ cho bài học nhỏ. Với test nhiều failure mode, có thể đặt một enum thay vì nhiều boolean để tránh đọc nhầm:

~~~java
enum FailurePoint {
    NONE,
    INIT,
    READ,
    WRITE,
    FLUSH,
    CLOSE
}
~~~

Đây là một **fragment Java 17**, có thể đặt trong một class hoặc file riêng đúng tên. Mỗi enum value mô tả **một vị trí lỗi** được chọn cho một instance. Nếu bạn cần mô phỏng “body lỗi và close cũng lỗi”, cần cho phép nhiều điểm lỗi hoặc tách cấu hình cho lifecycle và operation; đừng dùng một enum duy nhất rồi vô tình loại mất kịch bản lỗi kép.

Một cấu hình fake rõ có thể bao gồm:
- `resourceId`: tên resource để truy vết.
- `failAtInit` hoặc injected exception khi khởi tạo.
- `failAtClose` hoặc injected exception khi đóng.
- `events`: danh sách nhận các event theo thứ tự.
- `closeCount`: số lần đóng để assert.
- `opened`/`closed`: trạng thái vòng đời.
- `payload`/`buffer`: dữ liệu nội bộ nếu test cần kiểm tra việc ghi/đọc.

Đối với test concurrent, `ArrayList` dùng chung giữa thread không tự an toàn. Các thí nghiệm trong `FakeResourceFailureDemo` đều chạy đồng bộ một thread, nên `ArrayList` là đủ. Nếu muốn kiểm thử nhiều thread, dùng cấu trúc thread-safe/cơ chế đồng bộ và điều phối bằng latch, không dùng `Thread.sleep` như một phép chứng minh thứ tự.

### 6.1. Tiêm exception object hay chỉ cờ boolean?

Hai cách đều có giá trị:

**Dùng cờ:**

~~~java
if (failClose) {
    throw new IOException("close failed");
}
~~~

Đơn giản, deterministic, phù hợp dạy quy tắc suppressed.

**Dùng exception do test cung cấp:**

~~~java
if (closeFailure != null) {
    throw closeFailure;
}
~~~

Đây là fragment, `closeFailure` là `IOException` đã được test cung cấp. Ưu điểm là bạn có thể assert **identity**: exception chính hoặc suppressed có phải đúng object đã inject hay không. Cẩn trọng nếu tái sử dụng cùng một exception object giữa nhiều lượt test, vì stack trace và suppressed list gắn với object có thể khiến bằng chứng sai lệch.

Trong test thực, nên tạo exception mới cho từng test, không dùng singleton Throwable toàn suite.

## 7. Kiểm tra event log thay vì chỉ kiểm tra exception class

Một test yếu:

~~~java
assertThrows(IOException.class, () -> useResource());
~~~

Đây là **fragment JUnit 5**, `useResource` là hàm giả định. Nó chỉ chứng minh có một IOException thoát ra; không chứng minh resource đã được đóng, có lỗi bị suppress, hay body có thực sự chạy không.

Một test tốt còn kiểm tra các **hậu điều kiện**:
- `init:A` xảy ra trước `init:B`.
- `close:B` xảy ra trước `close:A` khi cả hai đã khởi tạo.
- `body` không chạy nếu initializer thứ hai lỗi.
- `close()` của resource khởi tạo lỗi không được try-with-resources gọi.
- Mỗi resource đã khởi tạo thành công được đóng **đúng một lần** bởi cấu trúc try-with-resources trong flow đã thử.
- Lỗi chính vẫn đúng object/type/message.
- `getSuppressed()` chứa lỗi close theo đúng số lượng/thứ tự.
- Không còn tài nguyên do test sở hữu bị rò.

Đừng chỉ viết `verify(close())` một lần rồi bỏ qua thứ tự: close của resource B có thể ném làm code tự dọn không đi tiếp tới A. Với event log, lỗi thứ tự hiện ngay trong kết quả.

### 7.1. Thêm bộ đếm close khi cần assert chính xác

Một fake có thể định nghĩa:

~~~java
private int closeCount;

@Override
public void close() throws IOException {
    closeCount++;
    events.add("close:" + name);
    if (failClose) {
        throw new IOException("close " + name + " failed");
    }
}

int closeCount() {
    return closeCount;
}
~~~

Đây là **fragment để thêm vào class fake**, không phải class độc lập. Khi test chạy một thread, bộ đếm `int` đủ dùng. Khi test concurrent cần đồng bộ thích hợp (ví dụ `AtomicInteger`) và chiến lược đọc trạng thái sau khi các task thật sự kết thúc.

**Đóng một lần bởi try-with-resources** không chứng minh close thật của mọi library là idempotent. Nếu business code cũng gọi `close()` thủ công, resource có thể được gọi đóng lần thứ hai; tùy implementation, điều đó có thể gây lỗi hoặc không. Test phải phù hợp hợp đồng resource.

## 8. Ví dụ JUnit 5: assert lỗi khởi tạo và cleanup A

Bên dưới là đoạn **JUnit 5 test minh họa**. Nó giả định bạn đã đưa `FakeResourceFailureDemo` vào cùng package với test và có JUnit Jupiter trong classpath. Các import/static import thích hợp gồm `org.junit.jupiter.api.Test`, `java.util.ArrayList`, `java.util.List`, `java.io.IOException` và `org.junit.jupiter.api.Assertions.*`.

~~~java
@Test
void secondInitializerFailureClosesFirstResource() {
    List<String> events = new ArrayList<>();

    IOException error = assertThrows(IOException.class, () -> {
        try (var a = new FakeResourceFailureDemo.FakeResource(
                     "A", events, false, true);
             var b = new FakeResourceFailureDemo.FakeResource(
                     "B", events, true, false)) {
            events.add("body");
        }
    });

    assertEquals("init B failed", error.getMessage());
    assertEquals(1, error.getSuppressed().length);
    assertEquals("close A failed",
                 error.getSuppressed()[0].getMessage());
    assertIterableEquals(List.of("init:A", "init:B", "close:A"), events);
}
~~~

Điều được kiểm chứng:
- Lỗi init của B là **lỗi chính**, dù close A cũng ném.
- B không có `close:B` trong event log.
- A đã được dọn đúng một lần theo sự kiện `close:A`.
- Phần thân không thực thi vì `body` không xuất hiện.

Không nhất thiết phải thêm Mockito để test thứ tự này. Với fake ghi sự kiện, ta kiểm tra được cả nguyên nhân và lifecycle bằng Java/JUnit cơ bản.

## 9. Ví dụ JUnit 5: body lỗi cộng với nhiều close lỗi

Một test khác:

~~~java
@Test
void bodyFailureIsPrimaryAndCloseFailuresAreSuppressed() {
    List<String> events = new ArrayList<>();

    IOException error = assertThrows(IOException.class, () -> {
        try (var a = new FakeResourceFailureDemo.FakeResource(
                     "A", events, false, true);
             var b = new FakeResourceFailureDemo.FakeResource(
                     "B", events, false, true)) {
            events.add("body");
            throw new IOException("body failed");
        }
    });

    assertEquals("body failed", error.getMessage());
    assertEquals(2, error.getSuppressed().length);
    assertEquals("close B failed",
                 error.getSuppressed()[0].getMessage());
    assertEquals("close A failed",
                 error.getSuppressed()[1].getMessage());
    assertIterableEquals(
            List.of("init:A", "init:B", "body", "close:B", "close:A"),
            events);
}
~~~

Đây là **fragment test JUnit 5**, các import như phần trước. Test không chỉ nhìn thấy IOException mà còn chứng minh **không có lỗi đóng nào che mất IOException của body** và **A vẫn đóng sau khi B.close() thất bại**.

Nếu `getSuppressed().length == 0` dù bạn đã cho close ném, có thể code thực đang dùng cleanup viết tay, resource không được đăng ký trong try-with-resources, hoặc exception đã bị wrap sai cách và bạn đang kiểm tra nhầm đối tượng Throwable ngoài cùng.

## 10. Lỗi lúc mở: constructor không tự được close bởi try-with-resources

Đây là một ranh giới quan trọng:

~~~java
try (ConnectionLike c = new ConnectionLike()) {
    work(c);
}
~~~

Fragment này giả định `ConnectionLike` là AutoCloseable và `work` có sẵn. Nếu constructor `new ConnectionLike()` **ném exception trước khi trả object**, biểu thức khởi tạo resource chưa hoàn tất; try-with-resources **không thể gọi `close()` trên object chưa được gán như một resource đã khởi tạo**.

Điều này khác với case “A mở xong, B khởi tạo thất bại”: Java vẫn đóng **A**, nhưng không tự dọn nội bộ **B**. Nếu B đã mở socket/file handle rồi mới ném do một bước setup thất bại, constructor/factory của B phải xử lý **partial acquisition**.

### 10.1. Thiết kế factory dọn resource mở dở

Giả sử cần mở một input stream rồi đọc header để khởi tạo một object:

~~~java
static ParsedInput openParsed(Path path) throws IOException {
    InputStream in = Files.newInputStream(path);
    try {
        Header header = readHeader(in); // Có thể ném IOException.
        return new ParsedInput(in, header); // Nhận quyền sở hữu stream.
    } catch (IOException | RuntimeException failure) {
        try {
            in.close();
        } catch (IOException closeFailure) {
            failure.addSuppressed(closeFailure);
        }
        throw failure;
    }
}
~~~

Đây là **fragment thiết kế**, cần import `java.io.InputStream`, `java.io.IOException`, `java.nio.file.Files`, `java.nio.file.Path` và định nghĩa `Header`, `ParsedInput`, `readHeader`. Ý tưởng:

1. `Files.newInputStream` mở stream.
2. Nếu bước parse header/thao tác tạo object ném, factory vẫn đang **sở hữu** stream nên cần cố đóng nó.
3. Nếu close cũng lỗi, giữ failure gốc là chính và gắn close failure bằng `addSuppressed`.
4. Nếu khởi tạo thành công, factory **chuyển quyền sở hữu** stream sang `ParsedInput`; class này phải đóng stream khi `close()` được gọi.

Trong code thật, cần xác định rõ **thời điểm chuyển ownership** và liệu constructor `ParsedInput` có thể ném sau khi nhận stream. Nếu constructor có side effect trước khi throw, nhánh catch cần bao quát và không đóng nhầm stream đã chuyển giao. Nếu failure là một loại unchecked khác hoặc error nghiêm trọng, cũng phải có chính sách phù hợp; đoạn fragment trên chỉ minh họa những exception dự kiến.

### 10.2. Không đưa resource chưa mở vào danh sách phải close

Một fake có thể ghi `init:B` rồi ném, nhưng **không nên tự động thêm B vào danh sách “đã mở thành công”**. Trong test, phân biệt:
- `initAttempted`: đã bắt đầu khởi tạo;
- `initialized`: khởi tạo đã hoàn tất;
- `registeredForClose`: tài nguyên đã trở thành đối tượng của try-with-resources;
- `closed`: `close` đã được gọi và kết quả thế nào.

Đối với một constructor ném exception, fake có thể ghi log `initAttempted`, còn không ghi `closed` của chính instance đó. Nếu bạn cần kiểm tra resource nội bộ mở dở, phải có event riêng cho chúng; việc không thấy `close:B` trong trace TWR **không chứng minh các handle nội bộ B đều an toàn**.

## 11. Fake lỗi đóng có ý nghĩa gì đối với resource thật?

`close()` không có một hậu điều kiện phổ quát “đã flush dữ liệu và mọi tác động hoàn tất”. Hợp đồng của từng resource khác nhau:

| Resource | Lỗi khi đóng có thể liên quan | Cần kiểm tra riêng |
| --- | --- | --- |
| `OutputStream` ghi file | Flush/ghi cuối thất bại, lỗi filesystem | File đã ghi được bao nhiêu, dữ liệu có bền vững không |
| `BufferedWriter` | Flush buffer hoặc close delegate gặp lỗi | Dữ liệu đã được chuyển xuống stream chưa |
| JDBC `Connection` | Lỗi giải phóng kết nối; trạng thái transaction có thể khác | Auto-commit, transaction, commit/rollback đã diễn ra |
| JDBC `Statement` / `ResultSet` | Driver cleanup thất bại | Resource lifecycle, driver behavior |
| Socket/channel | Lỗi đóng, thông tin remote không chắc chắn | Có gói tin nào đã gửi/nhận, server đã xử lý chưa |
| Lock/lease handle | Giải phóng thất bại hoặc lease chưa hết hạn | Có process nào còn giữ quyền truy cập không |
| Resource giả tự viết | Bất cứ quy tắc nào bạn cấu hình | Fake có mô phỏng đúng contract của đối tượng thật không |

**Không chuyển mọi lỗi close thành “đã rollback” hoặc “đã ghi thành công”**. Fake giúp kiểm tra Java flow và policy ứng dụng, không chứng minh mọi điều kiện của filesystem, driver hay service xa.

### 11.1. Cleanup khác rollback

Một resource có thể được đóng sau khi thao tác đã gây side effect:
- Đã append file rồi mới lỗi đóng.
- Đã commit database rồi mới lỗi close connection.
- Đã gửi request tạo thanh toán, response bị mất rồi socket close lỗi.

Một `IOException` từ `close()` không tự khôi phục trạng thái trước đó. Nếu tác vụ cần all-or-nothing, sử dụng transaction/staging/atomic publish trong phạm vi hỗ trợ; với nhiều hệ thống khác nhau, cần idempotency, compensation hoặc đối soát. Test fake phải có tình huống **side effect xảy ra trước lỗi** nếu contract cần khẳng định trạng thái sau failure.

## 12. Tránh làm mất lỗi chính khi tự viết `finally`

Anti-pattern:

~~~java
Resource a = openA();
Resource b = openB();
try {
    work(a, b);
} finally {
    b.close();
    a.close();
}
~~~

Đây là **fragment** với các hàm/types giả định. Nếu `b.close()` ném:
- `a.close()` **không được gọi** nếu không có cơ chế bảo vệ riêng.
- Exception từ `b.close()` có thể che mất exception từ `work`.
- Nếu `openB()` ném trước khi vào `try`, phần `finally` cũng **không chạy**, khiến A bị rò.

Try-with-resources xử lý những đường thoát đó đúng ngữ nghĩa Java. Với đa số AutoCloseable, hãy **ưu tiên try-with-resources** thay vì tự viết nhiều tầng `finally` khó kiểm chứng.

### 12.1. Lỗi đóng che lỗi thân

Với cleanup tự viết:

~~~java
try {
    throw new IOException("body failed");
} finally {
    throw new IOException("close failed");
}
~~~

Đây là **fragment** trong một phương thức cho phép `throws IOException`. Exception từ `finally` thay thế điều khiển ném ra ngoài; nếu không bảo quản lỗi thân, bạn mất nguyên nhân ban đầu. Try-with-resources có quy tắc suppressed để tránh vấn đề này khi cả body và close cùng ném.

Đừng đặt `return` trong `finally` để “trả trạng thái mặc định”, bởi nó cũng có thể che exception đang lan ra. Nếu phải cleanup thủ công vì API đặc biệt, hãy thiết kế preservation của lỗi chính và kiểm thử các đường failure.

## 13. `Throwable.getSuppressed()`: đọc đúng nơi chứa lỗi phụ

Khi có một `Throwable primary`:

~~~java
Throwable[] sideFailures = primary.getSuppressed();
for (Throwable secondary : sideFailures) {
    System.err.println("suppressed: " + secondary);
}
~~~

Đây là fragment giả định `primary` có sẵn. `getSuppressed()` trả mảng có thể rỗng; không được luôn truy cập `[0]` khi không có suppressed exception.

Các lỗi suppressed quan trọng vì:
- Cho biết cleanup/close cũng thất bại sau nguyên nhân chính.
- Giúp xác định resource nào có vấn đề.
- Có stack trace riêng, có thể trỏ tới lớp khác.
- Có thể khiến trạng thái tài nguyên không chắc chắn.

Khi ghi log, truyền **Throwable chính** vào logger có khả năng in cause/suppressed để không mất thông tin. Chỉ log `e.getMessage()` hoặc ném wrapper mới không có cause sẽ che chứng cứ.

### 13.1. Khác `cause` ở đâu?

- **Cause:** thường biểu diễn quan hệ “exception ngoài được gây ra bởi exception bên trong”, ví dụ `new IllegalStateException("failed", ioException)`.
- **Suppressed:** biểu diễn lỗi phụ được gắn vào primary, thường là lỗi cleanup khi primary đã tồn tại.

Không coi suppressed là một phần `getCause()` mặc định. Nếu exception có cả cause và suppressed, cần kiểm tra cả hai loại. `Throwable.printStackTrace()` thường hiển thị những quan hệ này; cấu hình logger có thể rút gọn/truncate, nên công cụ phân tích cần giữ đầy đủ khi có thể.

### 13.2. Gắn suppressed thủ công có bẫy gì?

`Throwable.addSuppressed(other)` có những ràng buộc: không thể thêm chính throwable đó làm suppressed của nó, và đối số không được null. Nếu suppression bị vô hiệu hóa khi tạo Throwable theo constructor đặc biệt, việc thêm có thể không có hiệu lực được quan sát. Với những Throwable thông thường tạo bởi `IOException`, hành vi suppression hoạt động như ví dụ.

Đừng viết code luôn `primary.addSuppressed(closeFailure)` trong mọi tình huống mà không biết ownership của exception, vì có thể vô tình thêm nhiều lần hoặc ghi nhận cùng một failure lặp. Try-with-resources thường đáng tin hơn khi chỉ cần dọn AutoCloseable.

## 14. Resource mở thành công nhưng `close()` ném: có đóng hai lần không?

Nếu `close()` ném, không thể kết luận resource đã đóng hoàn toàn hay vẫn mở: điều đó tùy implementation. Ví dụ một close có thể đã giải phóng handle rồi ném lỗi khi flush buffer; gọi `close()` lần nữa chưa chắc giúp dữ liệu được ghi đủ. Ngược lại, một close lỗi sớm có thể để resource chưa được giải phóng.

Fake nên mô phỏng đúng contract khi test chính sách retry-close. Không mặc định:
- `close()` luôn idempotent với mọi loại `AutoCloseable`.
- `close()` ném nghĩa là resource chắc chắn vẫn mở.
- Gọi `close()` hai lần là an toàn.
- Lỗi close chỉ ảnh hưởng log, không ảnh hưởng kết quả.

### 14.1. Test dùng-after-close khi quan trọng

Nếu API của bạn yêu cầu resource không được sử dụng sau `close()`, fake có thể có cờ `closed` và ném `IllegalStateException` khi gọi `read()/write()` sau khi đóng. Kiểm thử phải tách:
- Số lần close được yêu cầu.
- Resource có báo đã đóng không.
- Phương thức business còn gọi resource sau close hay không.

Tuy nhiên đừng áp đặt hành vi “mọi resource đều ném khi đọc sau close” lên tất cả thư viện nếu contract thật khác. Fake phải phản ánh **hợp đồng bạn cần bảo đảm**.

## 15. Mô phỏng lỗi khởi tạo nhiều tầng

Xem một service cần ba tài nguyên:

~~~text
Mở A ──> Mở B ──> Mở C ──> xử lý
          |
          +-- B init lỗi
              |
              +-- A phải được cleanup
              +-- C không được mở
              +-- body không chạy
~~~

Một test đầy đủ nên kiểm tra:
1. Nếu A init lỗi, không có B/C/body.
2. Nếu B init lỗi, A đóng; C/body không chạy.
3. Nếu C init lỗi, B rồi A đóng; body không chạy.
4. Nếu C init lỗi và cả B/A close lỗi, C init là primary, B/A close là suppressed theo thứ tự.
5. Nếu body lỗi, C/B/A đóng ngược; lỗi body vẫn chính.
6. Nếu body thành công và C.close lỗi, B/A vẫn được thử đóng.

Chỉ cần thay cấu hình fake tại mỗi test; không phải tạo database/socket thật với fault ngẫu nhiên.

### 15.1. Constructor partial failure và trách nhiệm dọn nội bộ

Giả sử tạo một `CompositeClient` gồm socket và buffer. Nếu socket đã mở nhưng bước tạo buffer ném, đối tượng CompositeClient có thể chưa hoàn thành construction; outer try-with-resources không gọi `CompositeClient.close()` trên object constructor thất bại. Factory/constructor phải dọn socket trong đường failure.

Test riêng bằng một fake socket sẽ kiểm tra:
- socket tạo thành công;
- bước thứ hai ném;
- socket.close được gọi đúng một lần;
- lỗi bước thứ hai giữ primary nếu socket.close cũng ném.

Việc kiểm tra này khác với test resource A ở header được đóng khi B init fail. Cần biết **resource nào sở hữu handle ở từng giai đoạn**.

## 16. Kiểm thử bất đồng bộ cần thêm đồng bộ hóa

Ví dụ `ExecutorService.submit` gọi một task có try-with-resources. Nếu task ném lỗi body hoặc close, `Future.get()` có thể ném `ExecutionException` với cause tương ứng. Test phải đọc **cause của task**, không chỉ thấy `get()` fail:

~~~java
Future<Void> future = executor.submit(() -> {
    try (FakeResource r = openFake()) {
        performWork(r);
    }
    return null;
});

ExecutionException wrapper = assertThrows(
        ExecutionException.class, future::get);
Throwable cause = wrapper.getCause();
~~~

Đây là **fragment JUnit 5**, giả định `executor`, `FakeResource`, `openFake`, `performWork` và các imports tồn tại. Nếu resource được tạo và dùng trong worker, event log chia sẻ cần thread-safe hoặc phải đọc **sau một điểm đồng bộ** như `get()`/`CountDownLatch.await()`. Một `ArrayList` bị nhiều thread cùng ghi không an toàn; thay bằng synchronized list/queue thích hợp khi cần.

Không dùng `Thread.sleep(100)` rồi assert “close đã gọi”, vì scheduling khác nhau theo máy. Dùng Future completion hoặc latch đảm bảo quan hệ happens-before phù hợp.

### 16.1. Không nhầm cancellation với close thành công

Nếu task đang bị cancel/interrupted:
- Việc Java thoát khỏi try-with-resources khi task thực sự rời scope sẽ kích hoạt cleanup.
- `Future.cancel(true)` chỉ là yêu cầu hủy/interrupt theo implementation và khả năng hợp tác của worker.
- `Future.isCancelled()` **không bảo đảm** `close()` đã được thực thi.
- Nếu worker bị chặn mãi trong API không hỗ trợ interrupt, cleanup cũng có thể chưa chạy.
- Nếu `close()` ném trong khi có exception do interruption, cần kiểm tra primary/suppressed của đường thực thi thực tế.

Test đòi hỏi xác nhận cleanup phải có **kênh xác nhận worker đã thoát** (latch ở `finally`, trạng thái job hoặc cơ chế tương đương), thay vì chỉ assert `cancel(true) == true`.

## 17. Dùng Mockito thay fake viết tay khi nào?

Nếu dependency là interface lớn và mục tiêu chỉ là xác minh số lần gọi `close()`, một mock có thể tiết kiệm code. Ví dụ dạng minh họa cho Mockito:

~~~java
AutoCloseable resource = mock(AutoCloseable.class);
doThrow(new IOException("close failed")).when(resource).close();
~~~

Đây là **fragment Mockito**, cần dependency Mockito, import/static import, và được đặt trong môi trường test phù hợp. `AutoCloseable.close()` khai báo `throws Exception`, nên checked exception `IOException` có thể được cấu hình tại đó theo giao diện.

Nhưng mock không tự chứng minh thứ tự đóng nhiều đối tượng, không tự kiểm tra partial acquisition, cũng không đảm bảo setup fake giống hành vi resource thật. Khi cần test một state machine và nhiều kịch bản lỗi, fake có event log thường dễ đọc hơn. Khi cần xác minh interaction ngắn trong service, Mockito/JUnit là lựa chọn hợp lý.

**Không cần đưa Mockito vào ví dụ Java 17 runnable** của bài này; core behavior được kiểm chứng bằng fake thuần Java.

## 18. Phân biệt “fake xác minh Java semantics” và “integration test xác minh hạ tầng”

Fake resource là một **unit-test double**. Nó không thể tự chứng minh rằng:
- OS đã ghi dữ liệu vào ổ đĩa.
- Socket thật đã giải phóng đúng thời điểm.
- JDBC driver thật xử lý lỗi khi `close` theo giả định.
- Một HTTP request đã bị remote server hủy.
- Connection pool khôi phục về trạng thái sạch sau close exception.
- Resource native/library đóng an toàn khi đang bị interrupt.

Cần dùng integration test bổ sung khi hợp đồng thực tế phụ thuộc vào driver/filesystem/server. Ví dụ database có thể cần thử lỗi kết nối, rollback, close và trạng thái transaction với instance test thật. Tuy nhiên integration test cũng không thể ép mọi lỗi phần cứng xuất hiện deterministic; có thể cần fault injection ở client adapter, proxy hoặc test fixture được kiểm soát.

### 18.1. Lớp adapter giúp test lỗi dễ hơn

Nếu code nghiệp vụ đang trực tiếp gọi `Files.newOutputStream` khắp nơi, khó thay thế bằng fake để chủ động gây lỗi init/close. Có thể đưa điểm tạo resource vào interface/factory:

~~~java
@FunctionalInterface
interface ResourceFactory<R extends AutoCloseable> {
    R open() throws Exception;
}
~~~

Đây là **fragment Java 17**. Hàm nghiệp vụ nhận `ResourceFactory<R>` có thể dùng fake trong unit test và implementation thật trong production. Tuy vậy, chọn kiểu checked exception rộng `Exception` chỉ để minh họa; code sản phẩm nên thu hẹp type khi phù hợp, ví dụ `IOException`.

Dependency injection không cần framework: constructor injection hoặc truyền factory vào phương thức đã đủ cho nhiều test đơn giản. Quan trọng là tạo được seam để tiêm lỗi **tại đúng thời điểm** mà không sửa source business chỉ cho test.

## 19. Kiểm tra nội dung lỗi ngoài message

Test chỉ assert `error.getMessage()` là một bước, nhưng có thể chưa đủ. Cần đánh giá:
- **Exception type** (IOException, SQLException, custom type).
- **Identity** nếu inject chính exception object và test đòi đúng cause.
- **Cause chain**, nếu service bọc exception.
- **Suppressed list** (độ dài, thứ tự, type, message).
- **State** của resource và dữ liệu sau lỗi.
- **Side effect** đã xảy ra trước khi lỗi.
- **Log/reporting** nếu contract yêu cầu.
- **Số lần và thứ tự gọi close**.
- **Leak** khi exception xảy ra trong initializer hoặc body.

Với try-with-resources chuẩn, suppressed được gắn vào exception chính khi lỗi đóng xuất hiện trong quá trình unwinding. Nhưng nếu tầng trên wrap exception bằng `new RuntimeException("...", e)`, bạn phải kiểm tra `e` (cause của wrapper) để tìm suppressed đúng chỗ; đừng giả định suppressed từ cause sẽ tự được sao chép lên wrapper.

### 19.1. Tránh assert stack trace line number trong unit test nghiệp vụ

Có thể assert class/method của Throwable nếu cần điều tra, nhưng hardcode `FakeResourceFailureDemo.java:42` trong unit test là dễ vỡ khi thêm comment hoặc refactor. Mục tiêu của bài là **ngữ nghĩa lifecycle và exception preservation**, không phải layout dòng source. Assert type/cause/suppressed/events sẽ bền vững hơn.

## 20. Những anti-pattern thường gặp

### 20.1. “Test đã thấy IOException, vậy cleanup ổn”

Sai: có thể đó là lỗi init, body hoặc close. Kiểm tra **nguồn lỗi chính, suppressed và event log**.

### 20.2. “Close B ném thì A chắc đã được đóng”

Đúng với try-with-resources đã đăng ký cả A/B và không có yếu tố bất thường phá luồng cleanup; **không đúng** với `finally { b.close(); a.close(); }` tự viết mà không bảo vệ. Hãy test đúng implementation.

### 20.3. “Constructor ném thì TWR sẽ gọi close trên chính object lỗi”

Sai: resource initializer không trả object hoàn chỉnh. TWR chỉ dọn các resource đã khởi tạo thành công trước đó; dọn partial acquisition của constructor/factory là trách nhiệm khác.

### 20.4. “Lỗi close luôn trở thành primary”

Sai: nếu body hoặc một initializer sau đã ném primary, close failure được suppressed. Nếu body thành công, close failure đầu tiên (theo thứ tự đóng) có thể là primary.

### 20.5. “`getSuppressed()[0]` lúc nào cũng có”

Sai: mảng có thể rỗng. Luôn kiểm tra hoặc dùng vòng lặp; không biến code chẩn đoán thành nguồn `ArrayIndexOutOfBoundsException`.

### 20.6. “`close()` ném đồng nghĩa resource chắc chắn chưa đóng”

Sai: implementation có thể đã giải phóng phần lớn tài nguyên rồi mới ném. Chỉ biết tình trạng thật qua contract và quan sát phù hợp.

### 20.7. “Fake có output đúng chứng minh DB thật rollback đúng”

Sai: fake không thay driver và transaction protocol. Cần integration test, transaction semantics và bằng chứng thực tế.

### 20.8. “Chạy nhiều test trên cùng một fake tiện hơn”

Dễ làm sự kiện và trạng thái cũ gây false positive/false negative. Tạo fake mới mỗi test hoặc reset bằng cơ chế rõ ràng, không để suite phụ thuộc thứ tự.

### 20.9. “Chỉ cần gọi `close` từ thread ngoài sau cancel”

Không chắc an toàn với tài nguyên dùng chung; cần ownership/thread-safety đúng. Khi worker chưa ra scope thì cleanup từ ngoài có thể tranh chấp với worker.

### 20.10. “Cứ catch `Throwable` trong fake cho khỏi crash test”

Catch rộng có thể che lỗi thực của logic test. Hãy chỉ catch type mà test đang kiểm tra; để assertion failure/unexpected exception làm test fail.

### 20.11. “Mocking `close()` ném là đủ kiểm thử mọi bug”

Mô phỏng lỗi ở close không bao phủ init thất bại, close order, resource mở dở và side effects. Cần test matrix đầy đủ theo các failure points.

### 20.12. “Suppressed = cause”

Hai cơ chế khác nhau. Lỗi đóng nằm trong suppressed của primary ở try-with-resources, không nhất thiết nằm trong `getCause()`.

## 21. Cây quyết định khi xây bộ kiểm thử fake resource

~~~text
Ứng dụng đang sở hữu tài nguyên AutoCloseable?
|
+-- Khởi tạo mấy resource?
|     +-- Một: thử init-fail / body-fail / close-fail
|     +-- Nhiều: thử fail ở mỗi vị trí init và reverse close
|
+-- Có thể ném ở body?
|     +-- Có: cho body ném X và close ném Y, xác minh X primary
|     +-- Không: cho close ném, xác minh close failure primary
|
+-- Constructor/factory cấp phát nội bộ?
|     +-- Có: test partial acquisition cleanup
|     +-- Không: test close của resource đã init thành công
|
+-- Có side effect bền vững?
|     +-- Có: bổ sung transaction/rollback/compensation test
|     +-- Không: kiểm tra state in-memory và event log
|
+-- Có executor/concurrency?
      +-- Có: đồng bộ bằng latch/future và thread-safe event log
      +-- Không: fake thuần Java là đủ
~~~

Đây là sơ đồ quyết định dành cho thiết kế test. Không phải tất cả dự án cần cùng số lượng case, nhưng mỗi hành vi mà API **cam kết** phải có đường thất bại được kiểm thử.

## 22. Checklist QA cho fake resource

- [ ] Fake triển khai đúng giao diện AutoCloseable hoặc contract resource cần mô phỏng.
- [ ] Có cách inject lỗi ở initializer và ở `close()` một cách deterministic.
- [ ] Với nhiều resource, event log ghi đúng identity và thứ tự init/close.
- [ ] Mỗi test dùng fake/state riêng, không rò dữ liệu giữa tests.
- [ ] Có case tất cả thành công để làm đường baseline.
- [ ] Có case resource A init lỗi: body không chạy, không gọi close trên A khởi tạo thất bại.
- [ ] Có case B init lỗi sau A: A được đóng, B không có `close:B`.
- [ ] Có case body ném X, close ném Y: X primary, Y suppressed.
- [ ] Có case body bình thường, close ném: lỗi close đi ra caller.
- [ ] Có case hai close cùng lỗi: tất cả resource phù hợp vẫn được thử đóng; thứ tự suppressed chính xác.
- [ ] Có case constructor/factory mở resource nội bộ rồi fail: các handle mở dở được dọn theo ownership.
- [ ] Assert type, cause, suppressed, event log và trạng thái resource; không chỉ một dòng message.
- [ ] Không hardcode source line numbers vào test lifecycle.
- [ ] Với concurrency, có điểm đồng bộ chắc chắn trước khi assert cleanup.
- [ ] Không coi Future canceled là bằng chứng worker đã hoàn tất cleanup.
- [ ] Nếu resource thật có transaction/flush, có integration test riêng cho hậu điều kiện.
- [ ] Không log exception trùng/nuốt failure rồi trả success sai.
- [ ] Giữ cause và suppressed khi wrap exception qua các tầng.
- [ ] Không dùng fake để hứa hẹn điều driver/remote service thật không cam kết.

## 23. Bài tập thực hành

Một service cần mở `InputStream` đọc file cấu hình, đồng thời mở `OutputStream` ghi kết quả. Theo thứ tự, nó mở input, mở output, đọc dữ liệu, ghi kết quả rồi thoát khỏi try-with-resources.

Hãy xây một `FakeInput` và `FakeOutput` có các tùy chọn lỗi:
1. Input init lỗi trước khi output bắt đầu; assert output không được mở.
2. Input mở thành công, output init lỗi; assert input được đóng một lần, body không chạy.
3. Body đọc ném `IOException("read failed")`, input close cũng lỗi, output close lỗi; assert lỗi read là primary và hai close failures được suppressed theo **thứ tự đóng ngược**.
4. Body thành công, chỉ output close lỗi; assert caller nhận lỗi close output.
5. Output close lỗi rồi input close lỗi; assert input vẫn được thử đóng.
6. Output constructor mở một file tạm trước khi init lỗi; assert file tạm do factory sở hữu được dọn, không trông chờ TWR gọi `close()` trên object khởi tạo dở.
7. Nếu file output đã ghi một phần trước khi close lỗi, xác định trạng thái đầu ra được phép tồn tại và cách transaction/staging/publish giải quyết tính nhất quán.
8. Với task chạy trên `ExecutorService`, kiểm tra lỗi body/close đi qua `ExecutionException.getCause()`; thêm latch kiểm chứng cleanup khi yêu cầu cancellation.

Dùng một event log cho từng test, inject exception có tên khác nhau (`input-init`, `output-init`, `read`, `write`, `input-close`, `output-close`), rồi assert cả **kết quả ngoại lệ và lịch sử thao tác**. Không cần làm hỏng file hoặc mạng thật để tái hiện các trường hợp lỗi.

## 24. Kết luận

Một fake resource giúp bạn tạo điều kiện thất bại tại **đúng điểm vòng đời** và chứng minh chương trình phản ứng đúng, thay vì trông chờ hệ điều hành hay dependency thật thỉnh thoảng gặp lỗi. Với Java try-with-resources, các thuộc tính quan trọng cần test là:

- Resource đã khởi tạo thành công được đóng theo **thứ tự ngược**.
- Lỗi từ body hoặc initializer được giữ làm **primary** khi cleanup cũng ném lỗi.
- Lỗi `close()` thứ cấp nằm trong **`getSuppressed()`**, không tự xóa lỗi chính.
- Một resource **khởi tạo thất bại** không được TWR tự gọi `close()`, nên constructor/factory phải dọn phần đã cấp phát nội bộ.
- Cleanup không đồng nghĩa rollback các tác động trước đó.

**Kết quả test đáng tin** phải kiểm tra cả exception, suppressed exceptions, thứ tự event và hậu điều kiện resource. Khi áp dụng vào file/socket/database thật, kết hợp unit test dùng fake với integration test ở ranh giới hạ tầng để không suy diễn những bảo đảm mà resource implementation không cung cấp.