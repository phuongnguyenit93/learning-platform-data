# Xây tài nguyên giả lập để kiểm chứng thứ tự và lỗi đóng (AutoCloseable)

> **Chủ đề:** Thực hành tự xây một tài nguyên `AutoCloseable` có thể ghi lại thứ tự cấp phát/giải phóng và chủ động phát sinh lỗi. Dùng nó để kiểm chứng trực tiếp quy tắc `try-with-resources` trong Java 17+: mở từ trái sang phải, đóng từ phải sang trái, đóng trước `catch`/`finally`, giữ ngoại lệ chính và ghi nhận lỗi đóng bằng `getSuppressed()`. Cú pháp bắt đầu từ Java 7 nhưng **vẫn là cơ chế chuẩn của Java hiện đại**, không phải API legacy.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Tự viết một class implements `AutoCloseable` với phương thức `close()` quan sát được.
2. Thiết kế **event log có thứ tự** thay vì chỉ dựa vào console hoặc thời gian thực.
3. Mô phỏng lỗi ở **ba vị trí riêng**: khi cấp phát, trong thân `try` và khi đóng.
4. Dự đoán **loại ngoại lệ chính (primary)**, danh sách **suppressed exceptions** và thứ tự của chúng.
5. Viết các **assertions** để một kết quả sai làm chương trình test thất bại, không chỉ in dòng “có vẻ đúng”.
6. Xác định bẫy ownership và vòng đời: đóng trùng, khởi tạo ngoài header, resource chưa được tạo thành công, `return` sớm, `catch`/`finally` và lỗi khi `close()`.
7. Chuyển cùng chiến lược kiểm chứng sang unit test cho file, channel, JDBC hoặc session tự định nghĩa mà **không cần mở các tài nguyên bên ngoài chỉ để test ngữ nghĩa đóng**.

Cách làm: tạo một lớp giả lập `Probe`. Mỗi lần mở, làm việc hoặc đóng, lớp ghi một chuỗi vào `List<String>`. Một số instance được cấu hình để `close()` ném `IOException` có thể dự đoán. Mọi kịch bản sẽ được chạy riêng và đối chiếu **chính xác** với thứ tự mong đợi.

## 2. Cơ chế Java mà phép thử phải chứng minh

Cấu trúc nhiều tài nguyên:

```java
try (
    Resource first = acquireFirst();
    Resource second = acquireSecond();
    Resource third = acquireThird()
) {
    performWork(first, second, third);
}
```

Đây là **snippet minh họa**, `Resource` và các helper phải là class/method do ứng dụng định nghĩa. Khi mọi bước đều thành công, ngôn ngữ bảo đảm trình tự tương đương:

```text
acquire first
acquire second
acquire third
perform work
close third
close second
close first
```

Lý do: danh sách trong header được **khởi tạo từ trái sang phải**, nhưng việc cleanup được thực hiện **theo thứ tự ngược**, giống ngăn xếp LIFO (*last in, first out*).

Tài nguyên phải có kiểu triển khai `AutoCloseable`. Phương thức được sử dụng để dọn dẹp là `close()`. Khi thân `try` kết thúc bình thường, ném ngoại lệ hoặc gặp `return`, Java vẫn cố đóng những tài nguyên đã khởi tạo thành công, trừ các tình huống kết thúc bất thường nằm ngoài bảo đảm thực thi thông thường (chẳng hạn tiến trình bị cưỡng bức dừng).

### 2.1. Tại sao cần mô phỏng lỗi?

Chỉ kiểm tra một đường “không lỗi” **chưa đủ** để biết code quản lý tài nguyên đúng. Một hệ thống cần biết:

- B.close ném lỗi thì A.close có còn được gọi không? **Có, Java vẫn cố đóng A.**
- Thân try ném lỗi và B.close cũng ném thì caller nhận lỗi nào? **Lỗi thân try là primary**, B.close trở thành suppressed.
- Thân try bình thường nhưng B.close và A.close đều lỗi thì sao? **B.close là primary**, A.close là suppressed.
- Mở A thành công, mở B thất bại thì A có bị bỏ quên không? **Không, A được đóng**, nếu A được đăng ký thành công trong header.
- Có `return` sớm, hay vào `catch`/`finally`, thì close chạy khi nào? **Trước khi trả kết quả ra caller và trước các nhánh catch/finally gắn với statement ấy.**

Các câu trên là những mệnh đề **có thể biến thành assertions thực thi được**. Đây chính là mục tiêu của tài nguyên giả lập.

## 3. Thiết kế một `Probe` có thể quan sát và gây lỗi có kiểm soát

Một đối tượng giả lập nên có những thành phần sau:

| Thành phần | Tác dụng trong phép thử |
| --- | --- |
| `name` | Phân biệt A, B, C; không phụ thuộc ID ngẫu nhiên |
| `events: List<String>` | Lưu thứ tự sự kiện chính xác |
| `failClose` | Bật/tắt việc `close()` ném lỗi theo từng instance |
| `closed` | Phát hiện việc gọi `close()` lặp |
| Constructor | Ghi `open:A`, `open:B`… khi tạo thành công |
| `close()` | Ghi `close:A`… rồi tùy chọn ném `IOException` |
| Factory `acquire(...)` | Ghi `acquire:A`, mô phỏng lỗi mở **trước khi** trả resource |
| `checkEvents(...)` | So sánh danh sách sự kiện thực tế và dự kiến |
| `checkFailure(...)` | Kiểm tra loại, message và thứ tự suppressed exceptions |

### 3.1. Vì sao dùng `List<String>`, không dùng thời gian?

`System.nanoTime()`, timestamps, thread scheduling hay log từ nhiều process có thể làm test khó tái lập và không chứng minh tốt thứ tự của **một luồng thực thi đồng bộ**. Trong demo này, tất cả chạy trong một thread, danh sách `ArrayList` ghi các sự kiện ngay khi xảy ra nên thứ tự trong list chính là thứ tự quan sát.

Mỗi kịch bản dùng **list mới**, để dữ liệu giữa hai test không trộn lẫn. Nội dung log là chuỗi cố định như `open:A`, `close:B`, không phụ thuộc filesystem, database, locale hoặc địa chỉ bộ nhớ.

### 3.2. Ghi nhận “đã cố đóng” khác “đóng thành công”

Trong `close()`, event `close:A` được ghi **trước** khi ném lỗi. Do đó log chứng minh Java **đã gọi close**, không chứng minh tài nguyên ngoài đời thật đã được giải phóng hoàn toàn. Khi dùng API thực tế, `close()` có thể thất bại; ứng dụng phải phân tích loại exception và trạng thái tài nguyên thay vì kết luận “close đã chạy thì chắc chắn thành công”.

### 3.3. Kiểm tra đóng trùng

`AutoCloseable` **không bảo đảm mọi implementation đều cho phép close nhiều lần mà không có hậu quả**. Trong mock, lần `close()` thứ hai bị phát hiện bằng `closed` và ném `IllegalStateException`. Đây là lựa chọn thiết kế của **Probe**, nhằm giúp test phát hiện double-close. Không phải quy tắc rằng Java luôn ném đúng exception này khi đóng lặp một tài nguyên thật.

## 4. Chương trình đầy đủ: sáu kịch bản có assertions

Chương trình sau **độc lập, chạy trên JDK 17+**, không cần thư viện kiểm thử bên ngoài. Nó bao gồm cả tài nguyên giả lập và bộ kiểm tra. Lưu toàn bộ vào tệp `ResourceLifecycleLab.java`.

```java
import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ResourceLifecycleLab {
    static final class Probe implements AutoCloseable {
        final String name;
        final List<String> events;
        final boolean failClose;
        boolean closed;

        Probe(String name, List<String> events, boolean failClose) {
            this.name = name;
            this.events = events;
            this.failClose = failClose;
            events.add("open:" + name);
        }

        @Override
        public void close() throws IOException {
            if (closed) {
                throw new IllegalStateException("double-close:" + name);
            }
            closed = true;
            events.add("close:" + name);
            if (failClose) {
                throw new IOException("close-failed:" + name);
            }
        }
    }

    static Probe acquire(String name, List<String> events,
                         boolean failOpen, boolean failClose) throws IOException {
        events.add("acquire:" + name);
        if (failOpen) {
            throw new IOException("open-failed:" + name);
        }
        return new Probe(name, events, failClose);
    }

    static void checkEvents(String scenario, List<String> actual, String... expected) {
        if (!actual.equals(Arrays.asList(expected))) {
            throw new AssertionError(scenario + " expected=" +
                    Arrays.toString(expected) + " actual=" + actual);
        }
        System.out.println("PASS " + scenario + ": " + String.join(" | ", actual));
    }

    static String detail(Throwable error) {
        return error.getClass().getSimpleName() + ":" + error.getMessage();
    }

    static void checkFailure(Throwable error, String primary,
                             String... suppressed) {
        if (error == null || !detail(error).equals(primary)) {
            throw new AssertionError("primary expected=" + primary + " actual=" + error);
        }
        Throwable[] actual = error.getSuppressed();
        if (actual.length != suppressed.length) {
            throw new AssertionError("suppressed count: " + actual.length);
        }
        for (int i = 0; i < actual.length; i++) {
            if (!detail(actual[i]).equals(suppressed[i])) {
                throw new AssertionError("suppressed[" + i + "]=" + detail(actual[i]));
            }
        }
        System.out.println("primary=" + detail(error));
        for (Throwable child : actual) {
            System.out.println("suppressed=" + detail(child));
        }
    }

    static void normal() throws IOException {
        List<String> events = new ArrayList<>();
        try (Probe a = new Probe("A", events, false);
             Probe b = new Probe("B", events, false);
             Probe c = new Probe("C", events, false)) {
            events.add("body");
        }
        checkEvents("normal", events,
                "open:A", "open:B", "open:C", "body",
                "close:C", "close:B", "close:A");
    }

    static void bodyFailure() {
        List<String> events = new ArrayList<>();
        Throwable error = null;
        try (Probe a = new Probe("A", events, true);
             Probe b = new Probe("B", events, true)) {
            events.add("body");
            throw new IllegalStateException("body-failed");
        } catch (Exception caught) {
            error = caught;
        }
        checkEvents("body-error", events,
                "open:A", "open:B", "body", "close:B", "close:A");
        checkFailure(error, "IllegalStateException:body-failed",
                "IOException:close-failed:B", "IOException:close-failed:A");
    }

    static void closeFailure() {
        List<String> events = new ArrayList<>();
        Throwable error = null;
        try (Probe a = new Probe("A", events, true);
             Probe b = new Probe("B", events, true)) {
            events.add("body");
        } catch (Exception caught) {
            error = caught;
        }
        checkEvents("close-error", events,
                "open:A", "open:B", "body", "close:B", "close:A");
        checkFailure(error, "IOException:close-failed:B",
                "IOException:close-failed:A");
    }

    static void initializationFailure() {
        List<String> events = new ArrayList<>();
        Throwable error = null;
        try (Probe a = acquire("A", events, false, true);
             Probe b = acquire("B", events, true, false);
             Probe c = acquire("C", events, false, false)) {
            events.add("body");
        } catch (Exception caught) {
            error = caught;
        }
        checkEvents("init-error", events,
                "acquire:A", "open:A", "acquire:B", "close:A");
        checkFailure(error, "IOException:open-failed:B",
                "IOException:close-failed:A");
    }

    static String earlyReturn(List<String> events) throws IOException {
        try (Probe a = new Probe("A", events, false);
             Probe b = new Probe("B", events, false)) {
            events.add("return");
            return "OK";
        }
    }

    static void returnFlow() throws IOException {
        List<String> events = new ArrayList<>();
        String result = earlyReturn(events);
        events.add("caller:" + result);
        checkEvents("return", events,
                "open:A", "open:B", "return",
                "close:B", "close:A", "caller:OK");
    }

    static void catchFinally() throws IOException {
        List<String> events = new ArrayList<>();
        try (Probe a = new Probe("A", events, false);
             Probe b = new Probe("B", events, false)) {
            events.add("body");
            throw new IllegalArgumentException("bad input");
        } catch (IllegalArgumentException caught) {
            events.add("catch");
        } finally {
            events.add("finally");
        }
        checkEvents("catch-finally", events,
                "open:A", "open:B", "body",
                "close:B", "close:A", "catch", "finally");
    }

    public static void main(String[] args) throws IOException {
        normal();
        bodyFailure();
        closeFailure();
        initializationFailure();
        returnFlow();
        catchFinally();
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 ResourceLifecycleLab.java
java ResourceLifecycleLab
```

**Stdout chính xác** (đã kiểm tra bằng biên dịch và thực thi với JDK):

```text
PASS normal: open:A | open:B | open:C | body | close:C | close:B | close:A
PASS body-error: open:A | open:B | body | close:B | close:A
primary=IllegalStateException:body-failed
suppressed=IOException:close-failed:B
suppressed=IOException:close-failed:A
PASS close-error: open:A | open:B | body | close:B | close:A
primary=IOException:close-failed:B
suppressed=IOException:close-failed:A
PASS init-error: acquire:A | open:A | acquire:B | close:A
primary=IOException:open-failed:B
suppressed=IOException:close-failed:A
PASS return: open:A | open:B | return | close:B | close:A | caller:OK
PASS catch-finally: open:A | open:B | body | close:B | close:A | catch | finally
```

**Ý nghĩa chữ `PASS`:** Mỗi dòng `PASS` được in **sau khi `checkEvents` xác nhận sự kiện đúng từng vị trí**. Nếu thứ tự khác, hàm ném `AssertionError`, tiến trình không hoàn thành như trên. `checkFailure` còn xác nhận exception chính và danh sách suppressed. Đây là một phép thử thực thụ, không chỉ là minh họa in log.

**Giới hạn của demo:** mọi tình huống giả lập đều có chuỗi thông báo cố định để dễ so sánh. Đối với exception từ API thật, không nên phụ thuộc tuyệt đối vào văn bản `getMessage()`, vì message có thể thay đổi theo driver, nền tảng hoặc phiên bản. Khi test hệ thống, hãy ưu tiên kiểm tra **type, trạng thái hợp đồng, cause và các side effect có ý nghĩa**; so message chỉ khi chính message là một phần của hợp đồng do bạn kiểm soát.

## 5. Đọc kết quả kịch bản 1: khởi tạo xuôi, đóng ngược

Kịch bản `normal()` tạo ba `Probe` trong cùng header:

```java
try (Probe a = new Probe("A", events, false);
     Probe b = new Probe("B", events, false);
     Probe c = new Probe("C", events, false)) {
    events.add("body");
}
```

Đây là **đoạn trích của chương trình đầy đủ ở mục 4**, không biên dịch độc lập. Các constructor thêm `open:A`, `open:B`, `open:C` vào log. Sau body, Java gọi `c.close()`, `b.close()`, `a.close()` đúng thứ tự ngược.

| Bước | Sự kiện | Giải thích |
| --- | --- | --- |
| 1 | `open:A` | Resource đầu được tạo |
| 2 | `open:B` | Resource thứ hai được tạo |
| 3 | `open:C` | Resource thứ ba được tạo |
| 4 | `body` | Bắt đầu và hoàn tất công việc |
| 5 | `close:C` | Đóng tài nguyên cuối khai báo |
| 6 | `close:B` | Đóng tài nguyên ở giữa |
| 7 | `close:A` | Đóng tài nguyên đầu khai báo |

**Điều test chứng minh:** chính sách LIFO, không phải thời điểm biến được dùng lần cuối. Nếu bạn đổi vị trí khai báo A và C, thứ tự mở và đóng tương ứng sẽ đổi. Việc dùng thử resource trong thân theo thứ tự khác **không tự thay đổi** thứ tự đóng đã được quy định bởi header.

## 6. Kịch bản 2: body lỗi, hai `close()` cũng lỗi

Trong `bodyFailure()`:

- A và B được tạo; cả hai `failClose = true`.
- Body ném `IllegalStateException("body-failed")`.
- Java đóng B trước; B.close ném `IOException("close-failed:B")`.
- Java vẫn cố đóng A; A.close ném `IOException("close-failed:A")`.
- Exception từ body được giữ làm **primary**.
- Hai IOException do cleanup được lưu làm **suppressed**, theo thứ tự B rồi A.

Phần quan sát:

```text
PASS body-error: open:A | open:B | body | close:B | close:A
primary=IllegalStateException:body-failed
suppressed=IOException:close-failed:B
suppressed=IOException:close-failed:A
```

### 6.1. Primary exception có ý nghĩa gì?

Primary là đối tượng `Throwable` chính được truyền đến handler ngoài. Trong trường hợp này, nó là `IllegalStateException` từ thân try. `close()` không thay thế đối tượng ấy bằng `IOException` đóng tài nguyên. Người chẩn đoán lỗi vẫn thấy nguyên nhân đầu tiên của công việc thất bại.

`Throwable.getSuppressed()` trả mảng chứa các exception xảy ra **khi Java đóng resource trong lúc primary đã tồn tại**. Nhờ cơ chế này, một lỗi cleanup không âm thầm làm mất lỗi body.

### 6.2. Tại sao vẫn tiếp tục đóng A khi B.close ném lỗi?

Nếu dừng ngay tại B.close, A có thể vẫn giữ file/socket/connection. Java tiếp tục cố đóng các resource đã được khởi tạo và đăng ký, theo thứ tự ngược. Lỗi sau đó được ghi nhận dưới dạng suppressed nếu có primary.

**Phân biệt:** log `close:A` chỉ chứng minh A.close đã được gọi. Trong test, `failClose = true` có nghĩa lời gọi cũng ném lỗi. Với resource thật, có những trường hợp cleanup chỉ giải phóng một phần; việc đóng đã được **thử**, không có nghĩa mọi handle đã được giải phóng thành công.

### 6.3. Suppressed khác cause

- **`getCause()`** mô tả chuỗi nguyên nhân giữa các exception, thường được thiết lập khi wrap: `new DomainFailure("...", original)`.
- **`getSuppressed()`** ghi những exception phụ phát sinh trong quá trình cleanup khi một primary đã tồn tại.
- Trong kịch bản này, không có constructor wrap lỗi body; hai lỗi close nằm ở `getSuppressed()`, **không phải** `getCause()` của `IllegalStateException`.

Đừng tìm lỗi close bằng cách chỉ duyệt `getCause()`. Với stack trace chuẩn, Java có thể hiện các dòng `Suppressed: ...` giúp phân biệt.

## 7. Kịch bản 3: body thành công nhưng các resource đóng thất bại

Trong `closeFailure()`, body chỉ ghi `body`, không ném exception. Sau đó:

1. B.close chạy trước và ném `IOException("close-failed:B")`. Vì chưa có primary từ body, lỗi đóng B trở thành **primary**.
2. A.close vẫn được gọi và ném `IOException("close-failed:A")`; lỗi này trở thành **suppressed** của lỗi B.
3. Handler ngoài nhận lỗi B, với A đính kèm.

```text
PASS close-error: open:A | open:B | body | close:B | close:A
primary=IOException:close-failed:B
suppressed=IOException:close-failed:A
```

**Điều đáng nhớ:** body không ném lỗi **không đồng nghĩa toàn bộ try-with-resources thành công**. Một phương thức có `return` dự kiến cũng có thể bị thay thế bằng exception từ `close()`; caller không nhất thiết nhận kết quả thành công nếu cleanup thất bại.

Với file output, buffered writer, database cursor hoặc tài nguyên phải flush, lỗi từ close có thể rất quan trọng. Khi thiết kế dịch vụ, cần thống nhất liệu close failure có khiến toàn bộ thao tác được coi là thất bại hay không. `try-with-resources` báo lỗi theo luật ngôn ngữ; quyết định mức nghiệp vụ thuộc về ứng dụng.

## 8. Kịch bản 4: mở B lỗi, A đã mở vẫn được đóng

`initializationFailure()` dùng factory `acquire`:

```java
static Probe acquire(String name, List<String> events,
                     boolean failOpen, boolean failClose) throws IOException {
    events.add("acquire:" + name);
    if (failOpen) {
        throw new IOException("open-failed:" + name);
    }
    return new Probe(name, events, failClose);
}
```

Đây là **đoạn trích từ chương trình đầy đủ**, ghi sự kiện `acquire` trước khi có thể ném. Trình tự trong test:

- `acquire("A", ..., false, true)` được gọi; A được tạo và ghi `open:A`.
- `acquire("B", ..., true, false)` được gọi; ghi `acquire:B` rồi ném `IOException("open-failed:B")` **trước khi trả B**.
- Java không chạy tiếp phép acquire C, và **không chạy body**.
- A đã được khởi tạo thành công trong header, nên Java gọi A.close. A.close được cấu hình ném `IOException("close-failed:A")`.
- Lỗi mở B là **primary**; lỗi đóng A là **suppressed**.

```text
PASS init-error: acquire:A | open:A | acquire:B | close:A
primary=IOException:open-failed:B
suppressed=IOException:close-failed:A
```

**Không có `open:B`, `acquire:C` hoặc `body`:** đây là các điều cần test **không xảy ra**, chứ không chỉ test sự kiện có xảy ra. Chương trình đối chiếu toàn bộ list nên một sự kiện thừa sẽ làm test thất bại.

### 8.1. Nếu một constructor đã cấp phát nội bộ rồi mới thất bại?

Giả sử một factory mở file descriptor rồi ném exception **trước khi trả lại đối tượng `AutoCloseable`**. Vì đối tượng chưa khởi tạo/được đăng ký thành công trong header, Java không thể tự nhận quyền quản lý nó. Factory/constructor phải có cơ chế dọn phần tài nguyên nội bộ đã cấp phát.

Vì thế hai tầng trách nhiệm khác nhau:

- `try-with-resources` đảm bảo đóng **các resource đã đăng ký thành công** trong header khi bước tiếp theo thất bại.
- Mỗi factory/constructor phải đảm bảo **tự cleanup phần cấp phát dang dở của chính nó** nếu không thể trả về resource hoàn chỉnh.

Đừng suy ra rằng đặt mọi `new SomeResource(...)` vào header tự xử lý được mọi tình huống rò rỉ trong constructor.

### 8.2. Tại sao nên acquire tài nguyên ngay trong header?

Nếu mở A, B bên ngoài rồi mới viết `try (a; b)`, một lỗi khi tạo B xảy ra **trước khi** statement try-with-resources bắt đầu. A có thể bị bỏ quên. Khi các tài nguyên cùng thuộc một tác vụ, viết phép acquire trực tiếp trong header thường bảo vệ tốt đường lỗi khởi tạo từng phần.

Dạng `try (existingVariable)` chỉ hợp lệ từ Java 9 với biến `final` hoặc *effectively final*; đây vẫn là cú pháp hợp lệ trong Java hiện đại nhưng phải cẩn thận về **khoảng trống cleanup trước try**.

## 9. Kịch bản 5: `return` sớm vẫn phải đóng trước khi caller nhận giá trị

Hàm `earlyReturn(...)` làm:

```java
static String earlyReturn(List<String> events) throws IOException {
    try (Probe a = new Probe("A", events, false);
         Probe b = new Probe("B", events, false)) {
        events.add("return");
        return "OK";
    }
}
```

Đây là **đoạn trích đã biên dịch được trong chương trình ở mục 4**, với `Probe` và các import đã có. Vì `Probe.close()` khai báo `throws IOException`, method khai báo `throws IOException` dù trong kịch bản này cả A và B được cấu hình đóng không lỗi.

Stdout:

```text
PASS return: open:A | open:B | return | close:B | close:A | caller:OK
```

Tại thời điểm method gặp `return "OK"`, Java vẫn cần thực hiện việc đóng B rồi A. Chỉ khi cleanup hoàn tất bình thường, caller mới nhận chuỗi và ghi `caller:OK`.

Trong chương trình thật, các lối thoát như `break`, `continue` hoặc một exception cũng dẫn đến cleanup theo quy tắc của try-with-resources. Trường hợp close ném exception có thể khiến `return` không hoàn tất như dự kiến; vì vậy không nên kiểm tra duy nhất “đã vào câu return” mà bỏ qua lỗi đóng.

## 10. Kịch bản 6: `close()` chạy trước `catch` và `finally`

Đoạn code:

```java
try (Probe a = new Probe("A", events, false);
     Probe b = new Probe("B", events, false)) {
    events.add("body");
    throw new IllegalArgumentException("bad input");
} catch (IllegalArgumentException caught) {
    events.add("catch");
} finally {
    events.add("finally");
}
```

Đây là **đoạn trích trong method `catchFinally()` của chương trình đầy đủ**. Nó xác nhận chính xác:

```text
PASS catch-finally: open:A | open:B | body | close:B | close:A | catch | finally
```

Tức là:

- Thân try ném `IllegalArgumentException`.
- Java đóng B, sau đó A.
- **Chỉ sau đó** mới vào catch phù hợp.
- `finally` của cùng statement chạy sau catch.

Điều này quan trọng nếu bạn muốn ghi log trạng thái cleanup trong catch: tại thời điểm catch chạy, Java **đã thử** đóng các resource do statement quản lý.

**Không hiểu nhầm:** `finally` ở đây vẫn có thể ném exception mới và thay đổi đường thoát. Java không bảo đảm mọi logic trong finally là vô hại. Khi chỉ cần đóng `AutoCloseable`, thường không cần viết lại `close` thủ công trong finally.

## 11. Biên dịch, assertions và kiểm tra chất lượng

### 11.1. Tại sao dùng `AssertionError` tự viết?

Các hàm `checkEvents` và `checkFailure` chủ động ném `AssertionError` khi khác kỳ vọng. Chúng **không** dùng câu lệnh `assert` của Java, vốn phụ thuộc cờ bật assertions `-ea` khi chạy JVM. Vì thế chạy lệnh `java ResourceLifecycleLab` đã đủ để kiểm tra các điều kiện.

Trong dự án dùng JUnit 5, có thể đổi chúng thành `assertEquals`/`assertThrows`/`assertArrayEquals` và chạy bằng test runner, nhưng phần học này **không phụ thuộc thư viện kiểm thử ngoài JDK**. Kịch bản chạy lặp lại được ở môi trường có JDK 17+.

### 11.2. Những điều assertion đang chứng minh

| Kịch bản | Điều assertion phải xác minh |
| --- | --- |
| Normal | A/B/C được mở, body chạy, đóng C/B/A; không thêm sự kiện |
| Body failure | Body là primary, B/A close vẫn được gọi, suppressed theo B→A |
| Close-only failure | B.close là primary, A.close là suppressed |
| Partial initialization | Có acquire B nhưng không open B/C; A được đóng |
| Early return | B/A đóng trước khi caller quan sát `OK` |
| Catch + finally | B/A đóng trước catch và finally |
| No duplicate close | Mỗi resource trong ví dụ chỉ có một sự kiện close; mock có guard nếu bị gọi lặp |
| Error details | Đúng class, message do test tự tạo và số/thứ tự suppressed |

**Một test chỉ in log không mạnh bằng assertion.** Nếu sửa `checkEvents` thành `System.out.println(events)`, chương trình vẫn chạy thành công cả khi thứ tự sai. Hãy giữ các so sánh chính xác và khiến CI thất bại khi có regression.

### 11.3. Vì sao không cần sleep, thread hay tài nguyên thật?

Test này đang kiểm chứng **ngữ nghĩa đóng theo cấu trúc Java**, là quy tắc đồng bộ. Không cần `Thread.sleep`, độ trễ mạng, transaction database hoặc thời gian thực. Dùng nguồn giả giúp tests nhanh, cô lập, không flaky và dễ truy vết.

Khi chuyển sang kiểm thử tích hợp file/JDBC, cần thêm test riêng để xác nhận hành vi thật của API đó, ví dụ dữ liệu đã ghi hoặc connection được trả pool. Mock không chứng minh mọi driver hay filesystem đều hoạt động đúng.

## 12. Mở rộng mock: kiểm thử đóng đúng một lần

Trong chương trình, `Probe.closed` dùng để phát hiện gọi `close()` lặp. Có thể thêm riêng một test **cố ý gây lỗi**:

```java
List<String> events = new ArrayList<>();
Probe probe = new Probe("X", events, false);
probe.close();
probe.close(); // Mock ném IllegalStateException("double-close:X").
```

Đây là **snippet cần đặt trong một method đã có class Probe và khai báo/handle IOException**. Không đưa đoạn này vào `main` của bài chạy bình thường vì nó cố tình kết thúc bằng lỗi. Mục tiêu: cho thấy class giả lập có thể biến double-close thành tín hiệu chẩn đoán.

**Quan trọng:** khi dùng `try (Probe p = ...)`, **không** tự gọi `p.close()` trong body rồi kỳ vọng JVM tự động biết là đã đóng. Thoát scope, Java vẫn gọi `close()`, dẫn đến lần gọi thứ hai. Với mock có guard, điều này được phát hiện. Trong resource thật, đóng trùng có thể không làm gì, hoặc ném lỗi, hoặc ảnh hưởng trạng thái; không có một hành vi thống nhất cho toàn bộ `AutoCloseable`.

### 12.1. Nếu muốn một `close()` idempotent?

Bạn có thể thiết kế custom resource sao cho lần gọi `close()` thứ hai là no-op. Ví dụ:

```java
@Override
public void close() throws IOException {
    if (closed) {
        return;
    }
    closed = true;
    events.add("close:" + name);
    if (failClose) {
        throw new IOException("close-failed:" + name);
    }
}
```

Đây là **mã thay thế để nghiên cứu**, đặt trong class Probe có các field tương ứng. Lưu ý rằng đoạn code đặt `closed = true` trước khi cleanup hoàn tất. Với resource thật, trạng thái “đã cố đóng” có thể khác “đã đóng thành công”, nên cần thiết kế state machine phù hợp (open/closing/closed/failed) thay vì sao chép cơ học logic này.

## 13. Mở rộng mock: đóng khi resource là `null`

Java cho phép biểu thức tài nguyên có giá trị `null`, và cơ chế tự động đóng **không gọi `close()` trên null**. Chẳng hạn:

```java
Probe absent = null;
try (absent) {
    events.add("body");
}
```

Đây là **snippet Java 9+** dùng biến `absent` final/effectively final, với `events` đã có và trong method phù hợp. Nó không tự ném `NullPointerException` chỉ vì tài nguyên null khi đóng. Tuy nhiên, **gọi method trên null trong thân try** vẫn có thể gây `NullPointerException`. Trong thiết kế API, đừng dựa vào tài nguyên null làm “cách bình thường” để bỏ qua cleanup nếu có thể thể hiện logic rõ bằng nhánh điều kiện.

Nếu biến được **gán lại**, nó không còn effectively final nên dạng `try (absent)` không hợp lệ. Cú pháp resource đã khai báo bên ngoài được bổ sung trong Java 9; với resource được khai báo trong header, có thể dùng `try (Probe absent = null)` theo cú pháp từ Java 7.

## 14. Mở rộng kiểm chứng cho lỗi khi mở tài nguyên

Trong `acquire`, cờ `failOpen` được kiểm tra **trước khi constructor trả về Probe**. Đây là tình huống đơn giản, nhưng đủ để khẳng định quy tắc dọn tài nguyên trước đó.

Có thể tạo thêm các kịch bản:

- A.open lỗi ngay: event chỉ có `acquire:A`; không có resource đã đăng ký để đóng.
- A.open thành công, B.open lỗi, A.close thành công: primary là `open-failed:B` và suppressed rỗng.
- A.open và B.open thành công, C.open lỗi, B.close và A.close đều lỗi: primary là `open-failed:C`, suppressed lần lượt `close-failed:B` rồi `close-failed:A`.
- A/B/C đều mở thành công nhưng B.close lỗi: B là lỗi đầu tiên trong cleanup **chỉ nếu C.close thành công**, hoặc là suppressed của lỗi trước đó nếu C.close đã ném.

Một phương pháp test rõ ràng là dùng bảng tham số có các cột `failOpenA/B/C`, `failCloseA/B/C`, `bodyFailure`, sau đó đối chiếu expected event sequence, primary và suppressed. Tránh sinh nhiều kịch bản ngẫu nhiên mà không biết kết quả kỳ vọng; test deterministically trước, rồi mới mở rộng sang property-based testing nếu có framework phù hợp.

### 14.1. Trường hợp open thất bại trước khi trả đối tượng

Nếu có file handle hoặc socket được cấp phát **bên trong constructor** rồi constructor ném lỗi, `try-with-resources` không đóng được một đối tượng mà nó chưa nhận thành công. Để kiểm chứng tầng đó, factory cần một phép thử riêng đối với cleanup nội bộ. Không dùng kết quả `initializationFailure()` của mock để kết luận mọi constructor ngoài đời đều leak-free.

## 15. Một cái nhìn về kiểu checked exception của `close()`

`AutoCloseable.close()` ở interface tổng quát khai báo `throws Exception`. Class Probe override thành `close() throws IOException`, là loại checked exception **hẹp hơn**, hợp lệ theo quy tắc override.

Vì sao `normal()`, `earlyReturn()`, `catchFinally()` trong chương trình khai báo `throws IOException` dù không cấu hình failClose? Compiler xét **khả năng ném ngoại lệ từ chữ ký method `close()`**, không chỉ giá trị cờ `failClose` lúc runtime.

Nếu Probe khai báo:

```java
@Override
public void close() {
    events.add("close:" + name);
}
```

thì đoạn close riêng này không ném checked exception, và code chỉ dùng tài nguyên ấy có thể không cần `throws IOException` vì lý do cleanup. Nhưng các lời gọi khác trong thân try vẫn phải được xét độc lập. Khi mock bắt lỗi bằng `catch (Exception)`, đó là lựa chọn của chương trình thử; ứng dụng thật nên bắt loại exception đúng phạm vi trách nhiệm.

**Không dùng `catch (Throwable)` như mặc định trong logic nghiệp vụ** để “bắt hết mọi thứ”. `Error` thường biểu hiện vấn đề không nên phục hồi tại tầng thông thường. Bộ kiểm thử có thể dùng các API assertion đặc thù, nhưng không vì thế mà thay đổi chính sách xử lý lỗi của production.

## 16. Nhầm lẫn thường gặp giữa primary, suppressed và cause

| Thắc mắc | Cách hiểu đúng |
| --- | --- |
| Body ném lỗi rồi close cũng ném: exception nào đến catch? | Thường là **body exception** (primary) |
| Body bình thường, close B rồi A đều ném: exception nào đến catch? | **B.close** (close đầu tiên theo LIFO) là primary |
| Close B ném, A có còn được đóng? | Java vẫn cố đóng A |
| Lỗi close nằm ở đâu khi đã có primary? | `primary.getSuppressed()` |
| Lỗi close có tự thành `getCause()` của primary? | Không. Cause và suppressed là hai quan hệ khác nhau |
| `close()` được gọi có chứng minh giải phóng thành công không? | Không, nếu close ném lỗi hoặc resource có trạng thái phức tạp |
| Có phải mọi `AutoCloseable.close()` đều idempotent? | Không |
| Có thể dùng event timestamps để suy ra thứ tự tốt hơn list không? | Không cần cho luồng đồng bộ này; list xác định hơn |
| Có phải chạy `java -ea` mới kiểm tra được chương trình trong bài? | Không; code dùng `throw new AssertionError` trực tiếp |

**Lưu ý kỹ thuật:** với các loại `Throwable` đặc biệt được tạo mà suppression bị vô hiệu hóa, `getSuppressed()` có thể không phản ánh các lỗi đóng theo cách thông thường. Các exception được tạo trong demo (`IOException`, `IllegalStateException`) sử dụng suppression chuẩn. Khi phát triển resource custom, tránh tự tái sử dụng cùng một đối tượng `Throwable` cho nhiều lần ném theo cách khó kiểm soát.

## 17. Kiểm chứng trong ứng dụng thực tế: mock và integration test khác nhau

**Unit test bằng Probe** có thể khẳng định:

- Client code của bạn sử dụng `try-with-resources` theo phạm vi dự kiến.
- Lệnh `close()` được gọi theo thứ tự kỳ vọng.
- Các nhánh lỗi vẫn đóng resource đã mở.
- Exception từ body/close được ưu tiên và gắn suppressed theo ngữ nghĩa Java.

**Nhưng nó không tự khẳng định**:

- File đã được ghi bền vững xuống ổ đĩa.
- Channel/socket đã hoàn thành tác vụ bất đồng bộ.
- Kết nối JDBC đã được trả pool mà không rò rỉ hoặc transaction đã commit.
- Một class bên thứ ba thực hiện `close()` đúng hợp đồng đã công bố.

Đối với file, có thể thêm integration test ghi tệp tạm trong `try`, sau đó đọc lại và xóa theo cleanup đáng tin. Đối với JDBC, tạo database test, gọi DAO rồi kiểm tra số connection active/idle hoặc trạng thái transaction theo API của pool. Đối với custom resource, xác minh state cuối hoặc số lần release. Mock chính là lớp **kiểm chứng thứ tự và đường lỗi**, không thay mọi kiểm tra hệ thống.

### 17.1. Không test trên log sản xuất khi có phương án tốt hơn

Log dùng trong production có thể bị xử lý không đồng bộ, gom nhóm hoặc thay định dạng. Trong unit test, truyền một `List<String>`/event sink nội bộ vào resource khiến dữ liệu dễ assert hơn việc dò `stdout`. Với nhiều thread, thay `ArrayList` bằng recorder an toàn luồng theo yêu cầu test, và đừng giả định thứ tự giữa các thread không được đồng bộ.

### 17.2. Mock kiểm chứng thử đóng, không tự kiểm chứng ownership

Một resource được gọi close đúng thứ tự nhưng **không thuộc quyền sở hữu của method** vẫn có thể là lỗi thiết kế. Ví dụ caller mượn một stream, nhưng callee vô ý đặt stream đó vào `try-with-resources` khiến caller không thể tiếp tục dùng. Unit test về ownership phải xác định ai chịu trách nhiệm đóng, không chỉ đếm lời gọi.

## 18. Các lỗi thường gặp khi xây phép thử tài nguyên giả lập

| Sai lầm | Vì sao có vấn đề | Cách khắc phục |
| --- | --- | --- |
| Chỉ in `open/close`, không có assertion | Test vẫn “thành công” khi thứ tự sai | So sánh full event list, ném `AssertionError` nếu khác |
| Dùng timestamps và `sleep` để xác định thứ tự trong một thread | Có nhiễu, tăng thời gian test | Dùng `List<String>` ghi theo thứ tự thực thi |
| Chỉ kiểm tra body không lỗi | Bỏ sót close/initialization failures | Có case body, close và init lỗi độc lập |
| Giả định B.close lỗi thì A.close không được gọi | Đọc sai cơ chế LIFO và suppressed | Assert A.close vẫn xảy ra |
| Chỉ kiểm tra primary message | Bỏ mất lỗi đóng resource | Assert cả `getSuppressed()` |
| Nhầm lỗi đóng với `getCause()` | Debug không thấy suppressed | Đọc hai quan hệ riêng |
| Gọi `close()` thủ công trong body của resource được quản lý | Java sẽ tiếp tục close khi ra scope, có thể double-close | Một owner, một cơ chế quản lý lifetime |
| Mở A, B ngoài header rồi mới `try (a; b)` | Nếu B.open ném, A có thể leak trước scope | Acquire trong header hoặc cleanup trước try |
| Test mock không có quyền phát sinh lỗi | Không kiểm tra được nhánh close failure | Dùng cờ `failClose` cố định |
| Ném cùng một exception object lặp lại từ nhiều nơi | Khó xác định primary/cause/suppressed; có edge case | Tạo exception mới theo mỗi lần lỗi |
| Cho rằng constructor thất bại vẫn được try tự close | Đối tượng chưa đăng ký thành công | Factory chịu cleanup phần cấp phát nội bộ |
| So sánh nguyên message từ driver/file system | Test dễ hỏng theo môi trường | Assert type/status/cause; message chỉ khi tự kiểm soát |
| Nhầm `AssertionError` của test với lỗi người dùng | Test failure bị chuyển thành response nghiệp vụ | Để test runner/CI báo thất bại |
| Xem mock thay cho tích hợp thực tế | Không phát hiện lỗi driver, transaction hay filesystem | Bổ sung integration test ở ranh giới cần thiết |
| Đóng resource trước khi async hoàn tất | Tác vụ dùng handle đã đóng | Thiết kế lifetime phù hợp với completion |

## 19. Bài tập thực hành có lời giải định hướng

**Bài 1 — Đổi thứ tự A/B/C.**  
Trong `normal()`, khai báo thứ tự `C, A, B`; điều chỉnh expected events.

**Đáp án:** Constructor ghi `open:C`, `open:A`, `open:B`; sau body, đóng `B`, `A`, `C`. Không quan trọng bạn tham chiếu resource theo thứ tự nào trong body.

**Bài 2 — B.close lỗi, A.close thành công.**  
Chạy body bình thường với `Probe A` có `failClose=false`, `Probe B` có `failClose=true`.

**Đáp án:** Timeline `open:A → open:B → body → close:B → close:A`. Primary là `IOException("close-failed:B")`. `getSuppressed()` không có lỗi từ A.

**Bài 3 — A.close lỗi, B.close thành công.**  
Đặt `A.failClose=true`, `B.failClose=false`.

**Đáp án:** Vẫn đóng B trước A; vì B.close thành công, lỗi A.close trở thành primary. Suppressed rỗng.

**Bài 4 — Mở C lỗi sau khi A/B thành công.**  
Dùng `acquire("A", ..., false, true)`, `acquire("B", ..., false, true)` và `acquire("C", ..., true, false)`.

**Đáp án:** Có `acquire:C` nhưng không `open:C`/`body`. Đóng B, A. Primary là `IOException("open-failed:C")`, suppressed theo thứ tự `close-failed:B`, `close-failed:A`.

**Bài 5 — Body ném lỗi, close không lỗi.**  
Đặt `failClose=false` cho cả A/B, nhưng trong body ném `IllegalStateException`.

**Đáp án:** Body exception là primary, suppressed rỗng; hai event close vẫn xuất hiện.

**Bài 6 — Body chạy thành công nhưng `return` và close lỗi.**  
Trong `earlyReturn()`, cấu hình B.failClose=true.

**Đáp án:** Thân đạt câu lệnh `return "OK"` nhưng B.close ném `IOException`, nên caller không nhận `OK` như lần chạy thành công. A vẫn được cố đóng. Thiết kế test caller bắt ngoại lệ và assert đúng type.

**Bài 7 — Trường hợp `null`.**  
Đặt resource cuối là null và chạy khối try.

**Đáp án:** Java không gọi `close()` trên giá trị null; các resource khác vẫn đóng theo thứ tự ngược. Nếu thân try gọi method trên null thì có thể phát sinh `NullPointerException` độc lập.

**Bài 8 — Đóng trùng.**  
Trong body, gọi `a.close()` thủ công rồi để try-with-resources kết thúc.

**Đáp án:** Với `Probe` trong bài, lần đóng thứ hai gây `IllegalStateException("double-close:A")`. Ngữ nghĩa cụ thể của lần đóng lặp do implementation quyết định; không dựa vào tình cờ không lỗi trên một tài nguyên khác.

**Bài 9 — Quan sát catch/finally.**  
Thêm event `catch`, `finally` vào một scenario có nhiều resource.

**Đáp án:** Đóng resource trước khi vào catch/finally của cùng try-with-resources statement. Cần assert toàn bộ timeline, không chỉ dòng cuối.

**Bài 10 — Viết unit test theo mẫu production.**  
Biến `Probe` thành một tài nguyên `Lease implements AutoCloseable`. Trong `close()`, gọi `release()` của mock lease provider. Viết test cho một release thành công, một release lỗi, và trường hợp công việc trước đó cũng lỗi.

**Hướng giải:** đo số lần release; không đóng tài nguyên do caller sở hữu; assert primary/suppressed khi đồng thời có lỗi, và assert cleanup được thử dù tác vụ ném exception.

**Bài 11 — Tự mở rộng.**  
Đổi `Probe.close()` sang `throws Exception` (kiểu rộng của `AutoCloseable`), sau đó biên dịch lại các method đang `throws IOException`. Quan sát nơi compiler buộc phải handle hoặc khai báo kiểu rộng hơn.

**Hướng giải:** Đây là tác động của **kiểu checked exception trong chữ ký `close`**, không phải thay đổi thứ tự đóng. Khi thực tế chỉ có lỗi I/O, khai báo `throws IOException` cụ thể hơn giúp API rõ ràng.

**Bài 12 — Thiết kế test matrix.**  
Lập bảng các cờ `failOpen`, `failClose` và `bodyFailure`, nhưng chỉ chọn những tổ hợp có kết quả kỳ vọng rõ: tất cả thành công; lỗi init đầu/giữa/cuối; body lỗi; close lỗi; body+close lỗi; return+close lỗi.

**Hướng giải:** Với từng dòng, viết ba đầu ra kỳ vọng: **event sequence**, **primary type/message**, **ordered suppressed list**. Test đạt khi cả ba cùng đúng.

## 20. Checklist áp dụng ngay khi review code

- Có một class implements `AutoCloseable` với `close()` thực hiện cleanup thật và dễ theo dõi không?
- Mock có ghi event **trong constructor/factory và trong close**, không chỉ trong body không?
- Mỗi scenario có list độc lập và assert **đúng cả thứ tự lẫn số lượng** sự kiện không?
- Lỗi khởi tạo xảy ra **trước khi resource được trả về** hay lỗi đóng một resource đã tồn tại? Hai tình huống cần phân biệt.
- Các resource đã khởi tạo có được cố đóng theo LIFO khi một resource khác lỗi không?
- Body exception, close exception và init exception có được kiểm tra primary/suppressed chính xác không?
- Mỗi resource do scope sở hữu có một nơi chịu trách nhiệm close? Có nguy cơ double-close hoặc đóng resource mượn không?
- API `close()` khai báo checked exception gì, ảnh hưởng đến method `throws` ra sao?
- Test có chạy trên JDK mục tiêu và thất bại bằng assertion thực, không chỉ phụ thuộc `stdout`?
- Sau unit test, có integration test cần thiết cho file/channel/JDBC thực tế không?

## 21. Tài liệu chuẩn để đối chiếu

- [Java Language Specification 17 — `14.20.3, try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): thứ tự khởi tạo/đóng, completion và suppression.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): chữ ký `close()`, hợp đồng vòng đời và lưu ý về idempotence.
- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getSuppressed()`, `getCause()` và thông tin lỗi.
- [Java SE 17 — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): ngoại lệ I/O checked dùng để mô phỏng close failure.
- [Java SE 17 — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): danh sách event dùng cho assertions.

**Ghi nhớ:** Để kiểm chứng `AutoCloseable`, hãy làm tài nguyên **quan sát được** (log sự kiện), **gây lỗi được** (fail open/close) và **kiểm tra được** (assert timeline + primary + suppressed). Khi ba điều kiện này được thực hiện, bạn có thể chứng minh bằng chương trình Java 17+ rằng **mở xuôi, đóng ngược, tiếp tục cleanup khi có lỗi và không làm mất ngoại lệ chính** — những quy tắc vẫn áp dụng trong Java hiện đại.
