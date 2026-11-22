# Rủi ro khi dùng chung ngoại lệ có thông tin nguyên nhân hoặc lỗi phụ thay đổi

Trong Java, một ngoại lệ (`Throwable`) không chỉ là tên lớp và thông điệp. Nó còn có thể mang **nguyên nhân** (`cause`), **ngoại lệ bị đính kèm** (`suppressed exceptions`) và **stack trace**. Những thông tin ấy giúp chẩn đoán sự cố, nhưng cũng khiến một đối tượng ngoại lệ trở thành nơi chứa **trạng thái thay đổi được**. Nếu tái sử dụng *cùng một đối tượng ngoại lệ* cho nhiều yêu cầu, nhiều lần thử hoặc nhiều luồng, dữ liệu của sự cố này có thể lẫn vào sự cố khác.

Ví dụ, request A và request B cùng sử dụng một `static final RuntimeException`. Khi A thêm ngoại lệ đóng tài nguyên vào `addSuppressed(...)` còn B ghi một lỗi đóng tài nguyên khác lên **cùng đối tượng**, log của A hoặc B có thể xuất hiện cả hai lỗi. Nếu một luồng gọi `fillInStackTrace()` để “cập nhật” vị trí ném, stack trace chung có thể đổi ngay trước lúc luồng khác ghi log. Dù các thao tác đơn lẻ có thể có bảo vệ đồng bộ nội bộ, **quyền sở hữu ngữ cảnh lỗi giữa các tác vụ vẫn sai**.

Bài này giải thích trạng thái nào của `Throwable` có thể thay đổi, `initCause()` giới hạn việc gán cause ra sao, vì sao suppressed exceptions dễ bị tích tụ, tác động của chia sẻ giữa các luồng, và cách cô lập lỗi mà vẫn cân nhắc hiệu năng.

## 1. Mô hình tư duy: một lần thất bại nên có ngữ cảnh lỗi riêng

Một ngoại lệ dùng để báo một sự cố cụ thể thường liên hệ các thông tin:

- **Lỗi chính**: thao tác nào thất bại và thông điệp phù hợp với sự cố đó.
- **Nguyên nhân** (*cause*): đối tượng ngoại lệ ở tầng thấp gây ra hoặc được dùng làm nguyên nhân cho lỗi chính.
- **Lỗi phụ** (*suppressed exceptions*): những lỗi bổ sung cần được giữ lại, chẳng hạn `close()` thất bại sau khi thân `try` đã ném lỗi chính.
- **Stack trace**: vị trí ghi nhận ngăn xếp lời gọi của đối tượng ngoại lệ, thường từ lúc khởi tạo.
- **Ngữ cảnh quan sát**: mã yêu cầu, tác vụ, thời điểm và logger xử lý, đôi khi nằm ngoài `Throwable`.

Hai yêu cầu độc lập dù cùng thất bại vì một loại lỗi cũng nên có **hai bản ghi sự cố phân biệt được**. Cùng loại ngoại lệ không có nghĩa phải dùng cùng đối tượng.

```text
Request A
  -> Exception A
       cause      -> IOException A
       suppressed -> CleanupException A
       stack      -> vị trí xảy ra A

Request B
  -> Exception B
       cause      -> IOException B
       suppressed -> CleanupException B
       stack      -> vị trí xảy ra B
```

Nếu dùng chung `Exception S`:

```text
Request A ------+
                +--> Exception S
Request B ------+       |
                        +--> cause: chỉ một nguyên nhân được gán
                        +--> suppressed: lỗi phụ của cả A lẫn B
                        +--> stack: vị trí tạo chung hoặc vị trí được ghi lại sau
```

Khi đọc một bản ghi log, ta không còn biết chắc dữ liệu nào thực sự thuộc về sự cố đang được báo nếu ứng dụng liên tục thêm hoặc chỉnh sửa thông tin chung.

## 2. `Throwable` chứa những phần trạng thái nào?

| Thuộc tính | API liên quan | Có thể thay đổi theo cách nào? | Rủi ro khi chia sẻ |
| --- | --- | --- | --- |
| Message | `getMessage()` | Thông điệp của lớp `Throwable` thường được đặt ở constructor; lớp con có thể cung cấp trạng thái riêng | Một thông điệp cố định không mô tả từng yêu cầu |
| Cause | `getCause()`, `initCause(Throwable)` | Nếu chưa được khởi tạo, `initCause` cho phép gán **một lần** | Luồng/request đầu tiên chiếm quyền gán; phần còn lại không thể đặt nguyên nhân của mình |
| Suppressed | `addSuppressed(Throwable)`, `getSuppressed()` | Có thể thêm nhiều ngoại lệ phụ khi suppression được bật | Danh sách tiếp tục tích lũy lỗi từ các sự cố khác nhau |
| Stack trace | `fillInStackTrace()`, `getStackTrace()`, `setStackTrace(...)` | Có thể được ghi lại hoặc thay đổi nếu writable stack trace được bật | Stack được thấy tại lúc ghi log có thể không phản ánh nơi lỗi của request hiện tại |
| Trường bổ sung trong lớp con | Getter/setter của lớp tùy biến | Tùy thiết kế lớp ngoại lệ | Race, dữ liệu cũ hoặc dữ liệu bị ghi đè giữa các luồng |

**Điểm quan trọng:** `static final Exception ERROR = ...` chỉ khiến **tham chiếu `ERROR` không được gán sang đối tượng khác**; nó không làm trạng thái của đối tượng `Throwable` bất biến.

Một lời gọi `throw ERROR;` cũng không tự tạo đối tượng mới. Hai lần ném có thể chuyển **chính cùng tham chiếu** qua các nhánh `catch`.

## 3. `initCause()` chỉ gán nguyên nhân một lần

Một số constructor của `Throwable` cho phép đặt cause ngay lúc tạo:

```java
new IllegalStateException("Cannot process order", originalError);
```

Đây là đoạn minh họa với biến `originalError` đã có kiểu `Throwable`. Cách này đặt nguyên nhân ngay khi tạo đối tượng và thường thích hợp khi chuyển lỗi từ tầng thấp sang tầng có ý nghĩa nghiệp vụ.

`Throwable.initCause(cause)` phục vụ những lớp ngoại lệ được khởi tạo **chưa gán cause**. Tuy nhiên:

1. Chỉ có thể gán cause một lần. Sau lần thành công, các lần `initCause(...)` tiếp theo ném `IllegalStateException`.
2. Ngay cả khi constructor đã khởi tạo cause bằng `null`, `initCause` vẫn có thể bị cấm bởi cause đã được coi là khởi tạo.
3. `initCause(this)` bị từ chối vì một throwable không thể là nguyên nhân trực tiếp của chính nó.
4. `initCause` **không phải setter để thay cause theo request**. Đừng dùng cùng một ngoại lệ rồi kỳ vọng mỗi lần thất bại sẽ có một `getCause()` mới.

Ví dụ minh họa bên trong một phương thức:

```java
Exception shared = new Exception("shared");
shared.initCause(new java.io.IOException("request A"));

try {
    shared.initCause(new java.io.IOException("request B"));
} catch (IllegalStateException rejected) {
    System.out.println("Cause was already initialized");
}
```

Sau nhánh trên, `shared.getCause()` vẫn liên hệ lỗi `"request A"`. Nếu request B dùng `shared` để báo thất bại, người đọc log có thể tưởng lỗi của A là nguyên nhân của B.

Java có cơ chế đồng bộ cho việc khởi tạo cause một lần, nhưng việc “chỉ một luồng thắng” không biến việc dùng chung thành đúng nghiệp vụ. Với hai luồng chạy đồng thời, luồng nào có thể gán cause trước là yếu tố không nên dùng làm nguồn quyết định dữ liệu chẩn đoán.

## 4. `addSuppressed()` có thể trộn lỗi của nhiều tác vụ

`Throwable.addSuppressed(Throwable)` được thiết kế để **giữ các lỗi phụ liên quan đến cùng một thất bại chính**, thường xảy ra trong `try-with-resources`. Ví dụ thân `try` ném `IOException("read failed")`, rồi `close()` cũng ném `IOException("close failed")`: Java thường giữ lỗi đọc là chính và gắn lỗi đóng tài nguyên thành suppressed exception.

Điều đó **không** có nghĩa `addSuppressed` là kho dữ liệu để nhiều request dùng chung. Nếu A và B cùng giữ một throwable và lần lượt gọi:

```java
shared.addSuppressed(new java.io.IOException("cleanup of A"));
shared.addSuppressed(new java.io.IOException("cleanup of B"));
```

thì `shared.getSuppressed()` có thể chứa **cả hai**. Đoạn này minh họa hậu quả khi sử dụng sai một `Throwable` dùng chung, không phải cách thiết kế nên áp dụng.

`addSuppressed` có hỗ trợ sử dụng an toàn ở mức thao tác thêm, nhưng **không tự phân nhóm suppressed exceptions theo request**. `getSuppressed()` trả một mảng chụp tại thời điểm gọi; lần đọc sau có thể chứa thêm phần tử mới. Thứ tự thêm khi các luồng chạy đồng thời không phải cách đáng tin để xác định yêu cầu nào xảy ra trước.

Ngoài ra, `addSuppressed(null)` và `addSuppressed(this)` là các tình huống không hợp lệ; Java từ chối thay vì ghi danh sách như thông thường. Một throwable được tạo với `enableSuppression=false` sẽ không ghi nhận suppressed exceptions, dù mã cố thêm chúng. Tắt suppression để giảm chi phí là **đánh đổi dữ liệu chẩn đoán**, không phải cách sửa lỗi trộn request.

## 5. Ví dụ Java 17+: một ngoại lệ dùng chung tích lũy ngữ cảnh của hai luồng

Ví dụ sử dụng hai luồng khác nhau cố tình thêm lỗi phụ từ hai tác vụ vào một `Throwable` chung. Để đầu ra ổn định, chương trình đợi cả hai luồng kết thúc rồi sắp xếp tên lỗi trước khi in; thứ tự thêm thực tế không cần cố định. Đây là **mã minh họa phản ví dụ** để hiểu rủi ro.

Tạo tệp **`SharedThrowableRiskDemo.java`**:

```java
import java.io.IOException;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;

public class SharedThrowableRiskDemo {
    private static final IllegalStateException SHARED = createShared();

    private static IllegalStateException createShared() {
        return new IllegalStateException("shared failure");
    }

    private static void addCleanupFailure(
            String request, CountDownLatch start) {
        try {
            start.await();
            SHARED.addSuppressed(
                    new IOException("cleanup " + request));
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("createdAt="
                + SHARED.getStackTrace()[0].getMethodName());

        SHARED.initCause(new IOException("backend A"));
        boolean secondCauseRejected = false;
        try {
            SHARED.initCause(new IOException("backend B"));
        } catch (IllegalStateException expected) {
            secondCauseRejected = true;
        }

        CountDownLatch start = new CountDownLatch(1);
        Thread a = new Thread(() -> addCleanupFailure("A", start));
        Thread b = new Thread(() -> addCleanupFailure("B", start));
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        String contexts = String.join(",",
                Arrays.stream(SHARED.getSuppressed())
                        .map(Throwable::getMessage)
                        .sorted()
                        .toList());

        System.out.println("secondCauseRejected="
                + secondCauseRejected);
        System.out.println("cause=" + SHARED.getCause().getMessage());
        System.out.println("suppressedCount="
                + SHARED.getSuppressed().length);
        System.out.println("suppressedContexts=" + contexts);

        SHARED.fillInStackTrace();
        System.out.println("refreshedAt="
                + SHARED.getStackTrace()[0].getMethodName());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 SharedThrowableRiskDemo.java
java SharedThrowableRiskDemo
```

Đầu ra:

```text
createdAt=createShared
secondCauseRejected=true
cause=backend A
suppressedCount=2
suppressedContexts=cleanup A,cleanup B
refreshedAt=main
```

Ý nghĩa từng kết quả:

- `SHARED` được tạo bởi `createShared()`. Stack trace ban đầu ghi nhận vị trí tạo đối tượng, dù sau đó đối tượng được dùng lại từ nhiều nơi.
- `initCause` gán `"backend A"` thành công; cố gán `"backend B"` bị từ chối. Cause còn lại **không phản ánh** yêu cầu B.
- Hai luồng độc lập thêm hai lỗi `cleanup A` và `cleanup B`; một bản ghi in toàn bộ ngoại lệ chung có thể kèm cả hai. Việc thêm có đồng bộ nội bộ không thể sửa được vấn đề **lẫn ngữ cảnh nghiệp vụ**.
- `fillInStackTrace()` trong `main` thay thông tin stack của **chính đối tượng chung**. Nếu một luồng khác đang chuẩn bị ghi nó ra log, dữ liệu được trình bày có thể khác theo thời điểm quan sát.

Trong thực tế, lỗi đóng tài nguyên nên gắn với ngoại lệ chính **của đúng thao tác có tài nguyên đó**. Ví dụ cố tình đưa chúng vào một đối tượng chung để chứng minh vì sao việc tái sử dụng như vậy nguy hiểm.

## 6. `fillInStackTrace()` và `setStackTrace()` làm mất định vị sự cố

Theo cách khởi tạo thông thường, `Throwable` ghi nhận stack trace tại lúc được tạo. Nếu tạo ngoại lệ chung khi khởi động ứng dụng rồi ném lại ở nhiều điểm, stack trace có thể liên tục chỉ về mã khởi tạo chứ không về nơi lỗi thực sự xảy ra.

Một số mã cố “sửa” vấn đề bằng cách gọi:

```java
shared.fillInStackTrace();
throw shared;
```

Đây là đoạn mã minh họa bên trong một phương thức có biến `shared`. `fillInStackTrace()` ghi lại thông tin stack cho **cùng đối tượng** khi có thể ghi stack. Nếu luồng A gọi trước rồi luồng B gọi sau, A không có một bản sao riêng để giữ dấu vết của mình: stack chung có thể đã bị B thay đổi trước lúc được định dạng hoặc phân tích.

`setStackTrace(StackTraceElement[])` cũng có thể thay đổi cách stack được hiển thị của throwable có stack ghi được. Việc thay đổi stack để trông như sự cố xuất phát từ vị trí khác đặc biệt nguy hiểm khi điều tra lỗi. Không nên “đánh dấu request” bằng cách chỉnh stack của lỗi chung.

`getStackTrace()` trả về **mảng bản sao** của phần tử stack, vì vậy chỉnh sửa một phần tử trong mảng vừa nhận không tự cập nhật stack lưu trong `Throwable`. Nhưng điều đó không làm chính đối tượng `Throwable` trở thành bất biến: các API cập nhật stack vẫn tồn tại, và mỗi lần đọc có thể quan sát một trạng thái khác sau khi thread khác thay đổi.

Việc logger chụp stack khi gọi hay định dạng trễ còn tùy backend/formatter. Nếu dùng logging bất đồng bộ, càng không nên dựa vào việc một `Throwable` được chia sẻ và tiếp tục thay đổi sau lời gọi log sẽ luôn xuất hiện với trạng thái tại đúng thời điểm log.

## 7. “Thread-safe” ở từng phương thức không bảo đảm ngữ cảnh chính xác

Cần phân biệt hai câu hỏi:

1. **Tính an toàn dữ liệu ở cấp thao tác:** khi hai luồng cùng thêm suppressed exception, cấu trúc lưu trữ có bị phá hỏng hay không?
2. **Tính đúng đắn nghiệp vụ:** các lỗi đó có thuộc cùng một sự cố chính và cùng một báo cáo chẩn đoán hay không?

Một API có thể có đồng bộ nội bộ nhưng vẫn sai nếu ứng dụng cho hai luồng **cùng sở hữu** một đối tượng mang ngữ cảnh. Java không tự biết `IOException("cleanup A")` thuộc request A còn `IOException("cleanup B")` thuộc request B. Một logger cũng không thể tách chúng thành hai sự cố chính xác chỉ dựa trên `getSuppressed()` của object chung.

Ví dụ về một chuỗi thao tác mà ứng dụng tưởng là “nhất quán”:

```text
Luồng A: chuẩn bị ghi log cho request A
Luồng B: thêm suppressed của request B
Luồng A: đọc getCause và getSuppressed rồi ghi log
Luồng B: gọi fillInStackTrace
Luồng A: định dạng các khung stack
```

Không có một snapshot nghiệp vụ **nguyên tử** bao gồm mọi trường cause, suppressed, stack, thông điệp bổ sung và metadata của request. Hơn nữa, khi đối tượng nguyên nhân (`getCause()`) cũng được chia sẻ và thay đổi, ngay cả một ngoại lệ wrapper mới của request A có thể tham chiếu đến dữ liệu không thuộc A.

**Chốt thiết kế:** an toàn luồng không thay thế cho quy tắc **mỗi thất bại cần có ngữ cảnh và quyền sở hữu riêng**.

## 8. Thiết kế đúng: tạo ngoại lệ riêng cho mỗi sự cố

Thông thường, một thao tác bắt được lỗi gốc sẽ tạo exception có ý nghĩa ở tầng của nó và **giữ nguyên nhân ngay trong constructor**:

```java
try {
    storage.save(order);
} catch (java.io.IOException cause) {
    throw new IllegalStateException(
            "Cannot save order " + order.id(), cause);
}
```

Đây là **đoạn minh họa** trong một phương thức có `storage`, `order` và kiểu trả về/kiểu nguồn phù hợp; không phải chương trình độc lập. Mỗi lần chạy nhánh `catch` tạo một `IllegalStateException` mới, liên kết với lỗi `IOException` của chính lần lưu đó.

Nếu cần ghi lỗi phụ, hãy thêm vào **ngoại lệ chính của cùng lần xử lý**, hoặc để `try-with-resources` thực hiện đúng quy tắc suppressed:

```java
try (Resource resource = openResource()) {
    resource.process();
}
```

Đây là đoạn minh họa cần các lớp/hàm `Resource`, `openResource` và `process` của ứng dụng. Khi cả thân `try` và `close()` đều ném lỗi, Java giữ ngoại lệ chính và thêm lỗi đóng tài nguyên thành suppressed. Không dùng một throwable global làm nơi tiếp nhận lỗi đóng tài nguyên của mọi request.

### Ví dụ Java 17+: hai request có đối tượng lỗi độc lập

Tạo tệp **`IsolatedThrowableDemo.java`**:

```java
import java.io.IOException;

public class IsolatedThrowableDemo {
    private static IllegalStateException fail(String request) {
        IOException cause = new IOException("storage " + request);
        IllegalStateException error = new IllegalStateException(
                "request " + request + " failed", cause);
        error.addSuppressed(new IOException("cleanup " + request));
        return error;
    }

    public static void main(String[] args) {
        IllegalStateException a = fail("A");
        IllegalStateException b = fail("B");

        System.out.println("differentErrors=" + (a != b));
        System.out.println("differentCauses="
                + (a.getCause() != b.getCause()));
        System.out.println("messageA=" + a.getMessage());
        System.out.println("causeA=" + a.getCause().getMessage());
        System.out.println("causeB=" + b.getCause().getMessage());
        System.out.println("suppressedA="
                + a.getSuppressed()[0].getMessage());
        System.out.println("suppressedB="
                + b.getSuppressed()[0].getMessage());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 IsolatedThrowableDemo.java
java IsolatedThrowableDemo
```

Đầu ra:

```text
differentErrors=true
differentCauses=true
messageA=request A failed
causeA=storage A
causeB=storage B
suppressedA=cleanup A
suppressedB=cleanup B
```

Khi dùng các đối tượng riêng, ngữ cảnh của A không bị B thêm vào. Ví dụ trên **mô phỏng** một lỗi cleanup bằng `addSuppressed` để kiểm tra việc cách ly, không có nghĩa mọi exception nên thêm lỗi suppressed thủ công. Trong ứng dụng thật, suppressed exception chỉ phù hợp khi nó thực sự là lỗi phụ của thất bại chính.

Cách này có chi phí cấp phát và thu thập stack, nhưng đó cũng chính là dữ liệu cần để truy nguyên một sự cố thực. Nếu số lỗi quá lớn, hãy xem nguyên nhân tạo lỗi bất thường và đo hiệu năng trước khi quyết định bỏ dữ liệu chẩn đoán.

## 9. Các trường hợp chia sẻ gián tiếp cũng cần chú ý

### 9.1. Wrapper mới nhưng cause vẫn là object chung

Ví dụ:

```java
static final java.io.IOException SHARED_CAUSE =
        new java.io.IOException("upstream unavailable");

RuntimeException a =
        new IllegalStateException("request A failed", SHARED_CAUSE);
RuntimeException b =
        new IllegalStateException("request B failed", SHARED_CAUSE);
```

Đây là **đoạn minh họa thuộc phần khai báo lớp/phương thức**, không phải một chương trình độc lập. `a != b`, nhưng `a.getCause() == b.getCause()`. Nếu `SHARED_CAUSE` có suppressed exceptions hoặc stack thay đổi, các wrapper đều tham chiếu tới thông tin đó.

Có trường hợp một sự cố gốc thực sự ảnh hưởng nhiều thao tác, ví dụ hệ thống khởi động thất bại và nhiều luồng cùng nhận một nguyên nhân. Việc chia sẻ **tham chiếu** khi đó có thể phản ánh quan hệ thật, nhưng cần thiết kế rõ **ai sở hữu và có được sửa cause nữa không**. Nếu mỗi request thất bại độc lập thì không nên dùng chung cause toàn cục.

### 9.2. Exception cache hoặc singleton để “tối ưu”

Dùng `static final Exception FAILURE = new Exception("failed")` tiết kiệm việc tạo mới ở các lần gọi sau, nhưng đi kèm stack trace ở nơi tạo đầu tiên và nguy cơ thông tin lỗi phụ lẫn vào nhau. Cần cân nhắc riêng chi phí theo tần suất sự cố, ngữ cảnh chẩn đoán và nhu cầu lưu stack/cause.

Một số hệ thống có thể dùng **đối tượng tín hiệu nhẹ có hợp đồng rất hẹp**, không mang ngữ cảnh request và vô hiệu hóa cả việc ghi stack lẫn suppression:

```java
final class FixedSignal extends RuntimeException {
    FixedSignal() {
        super("fixed signal", null, false, false);
    }
}
```

Đây chỉ là **khai báo lớp minh họa**, chưa phải chương trình độc lập. Constructor bốn tham số đã xác lập cause thành `null` và tắt suppression/stack writable. Nếu tái sử dụng đối tượng thuộc lớp này làm tín hiệu điều khiển nội bộ, hãy bảo đảm không thêm trạng thái mutable ở lớp con, không dùng nó để báo các lỗi cần stack thực, và tài liệu hóa ranh giới sử dụng. Đây là một ngoại lệ thiết kế có chủ đích, không phải mặc định cho tất cả failure.

Ngay cả với tín hiệu kiểu này, dùng kiểu kết quả/enum hoặc nhánh điều khiển bình thường thường dễ hiểu hơn khi tình huống thật sự là trạng thái dự kiến. Đừng dùng exception làm lệnh điều khiển chung chỉ vì đã tắt stack trace.

### 9.3. `ThreadLocal<Throwable>` chưa chắc giải quyết được vấn đề

Một throwable riêng cho mỗi `Thread` có thể tránh việc **hai thread đồng thời sửa cùng object**, nhưng executor thread thường được tái sử dụng cho nhiều request nối tiếp. Nếu không tạo lại/đặt lại đúng ngữ cảnh, suppressed exceptions và cause từ request cũ vẫn tồn tại. `ThreadLocal` còn có rủi ro giữ dữ liệu qua vòng đời worker và làm tăng sử dụng bộ nhớ nếu không dọn đúng chỗ.

Do đó, “mỗi thread một exception” vẫn khác “mỗi lần thất bại một exception”. Đơn vị sở hữu lỗi nên gắn với **sự cố/operation**, không mặc nhiên gắn với tuổi thọ của thread.

## 10. Tác động đến ghi log, theo dõi lỗi và bảo mật

Khi logger nhận cả `Throwable`, backend thường có thể ghi tên lớp ngoại lệ, stack trace, `Caused by:` và `Suppressed:`. Đó là một lợi thế chẩn đoán, nhưng lại phơi bày tác động của đối tượng dùng chung rõ hơn.

- **Log sai request:** lỗi phụ từ B xuất hiện trong log request A, gây hiểu nhầm hoặc làm người trực vận hành theo dấu nhầm.
- **Stack trace cũ hoặc bị thay:** stack chỉ về đoạn khởi tạo singleton, hoặc về thread vừa gọi `fillInStackTrace()`, không về nơi đã phát sinh lỗi của record đang xem.
- **Chẩn đoán không nhất quán:** cùng một tham chiếu throwable được log ở hai thời điểm có thể hiển thị số suppressed exceptions khác nhau.
- **Nguy cơ lộ dữ liệu giữa người dùng:** nếu message/cause/suppressed chứa dữ liệu riêng của request, việc dùng chung có thể khiến chi tiết của người dùng này xuất hiện trong bản ghi liên quan người dùng khác. Cần tránh đưa bí mật vào exception message ngay từ đầu.
- **Gom nhóm lỗi sai:** các hệ thống theo dõi lỗi có thể dựa vào stack và loại exception để nhóm sự cố; stack dùng chung hoặc bị chỉnh sửa làm nhóm lỗi kém chính xác.

Để giảm rủi ro, log tại ranh giới rõ trách nhiệm, chuyển **đối tượng ngoại lệ riêng của sự cố** cùng mã tương quan an toàn, giữ cause khi bọc lỗi và tránh ghi cùng stack trace nhiều lần không cần thiết. Việc dùng logging bất đồng bộ không làm một object dùng chung trở thành bất biến.

Đừng tạo một ngoại lệ mới **chỉ để chép message** và bỏ cause: `new IllegalStateException(shared.getMessage())` sẽ làm mất ngữ cảnh nguyên nhân thực. Nếu thật sự cần một ngoại lệ mới, lấy nguyên nhân *đúng của operation* và chuyển vào constructor phù hợp. Một nguyên nhân đã chia sẻ vẫn nên được đánh giá kỹ trước khi tham chiếu.

## 11. Hiệu năng: nên tối ưu đường lỗi thế nào?

Rủi ro chia sẻ throwable thường nảy sinh từ ý định tiết kiệm việc tạo ngoại lệ và stack trace. Đánh đổi cần phân tích ở cấp hệ thống:

| Lựa chọn | Lợi ích tiềm năng | Hạn chế quan trọng |
| --- | --- | --- |
| Tạo ngoại lệ mới cho mỗi failure | Ngữ cảnh/cause/suppressed/stack riêng | Có cấp phát và chi phí chụp stack |
| Dùng singleton throwable có stack | Giảm số đối tượng tạo mới | Stack cũ, trạng thái mutable dùng chung, log khó truy nguyên |
| Singleton tín hiệu không stack/suppression, không có ngữ cảnh | Có thể giảm chi phí trong một hợp đồng nội bộ đặc biệt | Mất stack; dễ bị dùng sai cho failure thật |
| Kết quả có cấu trúc cho trạng thái bình thường | Không tạo ngoại lệ trong nhánh dự kiến | Phải thiết kế API, gọi và kiểm tra kết quả rõ ràng |
| Giới hạn tốc độ log/lấy mẫu, đo lỗi theo metric | Giảm tải ghi log trùng lặp | Vẫn phải lưu đủ chẩn đoán cho lỗi cần điều tra |

Khi một kiểu lỗi xảy ra với tần suất cao, câu hỏi đầu tiên nên là: **đây có thật là ngoại lệ hay một kết quả thường xuyên theo hợp đồng API?** Nếu không tìm thấy mục tiêu là tình trạng dự kiến, `Optional`, enum hoặc kiểu kết quả có thể phù hợp hơn việc liên tục ném exception.

Nếu vẫn phải dùng exception, đo trên đúng JDK, tải thực và độ sâu stack. Java Microbenchmark Harness (JMH) hữu ích để đo chi phí tạo ngoại lệ; profiler và metrics giúp nhận biết tác động tới CPU, cấp phát, GC và log. Không suy ra từ một benchmark rằng việc bỏ stack trace cho mọi lỗi là an toàn.

Đặc biệt, `Throwable.addSuppressed` có thể khiến đối tượng dùng chung sống lâu chứa ngày càng nhiều tham chiếu tới ngoại lệ phụ và các object liên quan. Điều này tạo nguy cơ **giữ bộ nhớ lâu hơn cần thiết**, ngoài lỗi chẩn đoán. Không dùng danh sách suppressed như lịch sử sự cố vô hạn.

## 12. Checklist khi xem lại mã nguồn

Khi tìm thấy một `Throwable` được dùng qua nhiều yêu cầu hoặc luồng, kiểm tra:

1. Object đó được tạo **mỗi lần thất bại**, mỗi thread, hay một lần ở `static final`/cache?
2. Cause đã được đặt ngay khi tạo chưa? Có mã gọi `initCause` cho các request khác nhau không?
3. `addSuppressed` có chỉ nhận lỗi phụ thuộc **cùng một thao tác**, hay trộn dữ liệu của nhiều tác vụ?
4. Có nơi gọi `fillInStackTrace()` hoặc `setStackTrace(...)` trên object đang được dùng chung không?
5. Logger có thể định dạng sự kiện sau khi một thread khác đã sửa throwable không? Chức năng của backend cần được xác nhận.
6. Wrapper mới có đang giữ tham chiếu đến **cause toàn cục mutable** không?
7. Có cache/`ThreadLocal` khiến trạng thái lỗi sống lâu hơn một operation không?
8. Có thể thay ngoại lệ cho tình huống dự kiến bằng kiểu kết quả, hoặc giới hạn log thay vì dùng singleton throwable không?
9. Nếu cố ý dùng tín hiệu throwable không stack, hợp đồng có thực sự bảo đảm không chứa ngữ cảnh request hay dữ liệu cần điều tra không?
10. Trường hợp xấu nhất có làm log của người dùng này chứa thông tin của người dùng khác không?

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `static final RuntimeException SHARED = new RuntimeException("failed");` có đồng nghĩa đối tượng không thể thay đổi?  
**Trả lời:** Không. `final` chỉ cố định tham chiếu của trường. `Throwable` vẫn có các trạng thái như cause chưa khởi tạo, suppressed list và stack trace mà API cho phép cập nhật.

**Câu 2.** Hai request cùng gọi `shared.addSuppressed(...)`; phương thức hỗ trợ đồng bộ thì dữ liệu có được tách riêng không?  
**Trả lời:** Không. Danh sách vẫn thuộc **cùng một đối tượng**; đồng bộ thao tác không tự chia phần tử theo request.

**Câu 3.** Sau khi gọi `initCause(causeA)` thành công, có thể gọi `initCause(causeB)` để thay cause không?  
**Trả lời:** Không. Lần thứ hai bị từ chối bằng `IllegalStateException`.

**Câu 4.** Ném lại cùng exception từ hai method có tự tạo hai stack trace độc lập không?  
**Trả lời:** Không. Đây vẫn là một đối tượng. Nếu gọi `fillInStackTrace`, bạn cập nhật stack gắn với đối tượng chung, không tạo bản sao riêng.

**Câu 5.** Hai wrapper `new IllegalStateException("A", common)` và `new IllegalStateException("B", common)` có cause khác nhau không?  
**Trả lời:** Không. Chúng có object wrapper riêng nhưng vẫn giữ **cùng tham chiếu** `common`; nếu nó mang dữ liệu mutable, cả hai cùng nhìn thấy.

**Câu 6.** `getSuppressed()` trả về mảng riêng, vậy Throwable đã bất biến chưa?  
**Trả lời:** Chưa. Mảng trả về là bản chụp tại thời điểm gọi; một thread khác vẫn có thể thêm suppressed exception vào object gốc.

**Câu 7.** Đổi từ singleton throwable có stack sang singleton không stack có giải quyết tất cả nguy cơ không?  
**Trả lời:** Không. Nó bỏ một nguồn trạng thái chẩn đoán, đồng thời làm mất khả năng tìm vị trí lỗi. Chỉ cân nhắc khi đó là tín hiệu nội bộ không chứa ngữ cảnh request, có hợp đồng rõ và đã đo.

**Câu 8.** Cách an toàn thông thường khi hai request thất bại độc lập là gì?  
**Trả lời:** Tạo exception riêng cho từng sự cố, giữ cause đúng của sự cố trong constructor, chỉ gắn suppressed exceptions thực sự thuộc sự cố đó, rồi ghi log theo mã tương quan phù hợp.

## 14. Tham khảo API

- [Java 17 — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `initCause`, `addSuppressed`, `getSuppressed`, `getStackTrace`, `fillInStackTrace` và các constructor điều khiển suppression/stack trace.
- [Java 17 — `RuntimeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): các constructor đặt cause, suppression và writable stack trace.
- [Java 17 — `AutoCloseable` và `try-with-resources`](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): ví dụ ngoại lệ chính và suppressed exceptions khi đóng tài nguyên.

**Ghi nhớ:** một `Throwable` là **một đối tượng có trạng thái chẩn đoán**, không phải chỉ là mã lỗi bất biến. `initCause` không cho phép thay nguyên nhân tùy ý; suppressed exceptions có thể tích lũy; stack trace có thể bị cập nhật. Tái sử dụng object này giữa các sự cố độc lập dễ trộn dữ liệu và làm log sai sự thật. Hãy ưu tiên **mỗi sự cố có ngoại lệ riêng**, giữ cause đúng, dùng suppressed theo đúng quan hệ lỗi phụ và tối ưu đường lỗi dựa trên số liệu thực tế.