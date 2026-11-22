# Đánh đổi khi tắt writableStackTrace hoặc tái sử dụng đối tượng ngoại lệ

## 1. Bài toán hiệu năng và giá trị chẩn đoán

Trong Java, tạo một exception thông thường không chỉ có nghĩa cấp phát một object chứa thông điệp. Theo cách triển khai và cấu hình, lúc khởi tạo **Throwable**, JVM còn có thể thu thập dấu vết ngăn xếp (stack trace) để sau này cho biết nơi đối tượng lỗi được tạo, qua những phương thức nào, ở file và dòng nguồn nào. Việc tạo rất nhiều exception có thể gây chi phí CPU, cấp phát, áp lực garbage collector và chi phí ghi log khi in stack trace.

Một số hệ thống muốn tối ưu đường xử lý rất nóng bằng hai kỹ thuật:

1. **Tắt writableStackTrace** cho một loại exception chuyên dụng, khiến đối tượng không thu thập/không giữ stack trace theo cơ chế chuẩn.
2. **Tái sử dụng một đối tượng exception** đã được tạo từ trước, tránh tạo object và thu thập stack trace mới cho mỗi lần ném.

Cả hai đều có thể giảm chi phí trong những tình huống đo đạc cụ thể, nhưng chúng lấy đi hoặc làm sai lệch dữ liệu cần thiết để điều tra lỗi. Mối nguy hiểm lớn nhất không phải chỉ là “log có ít dòng hơn”, mà là **không còn xác định được lần lỗi thực tế phát sinh ở đâu, trong request nào, hay suppressed exceptions của lần nào**.

**Nguyên tắc thiết kế:** ưu tiên giữ exception đầy đủ cho lỗi bất thường cần chẩn đoán; chỉ tối ưu đường exception sau khi đo được đây là nút thắt hiệu năng, xác nhận tác động và có một kênh quan sát khác bù đắp dữ liệu bị mất. Đừng biến ngoại lệ thành đường điều khiển lặp thường xuyên chỉ vì có cách làm stackless.

Bài học này thuộc nhóm **Hiệu năng** trong **Java Core — Exception**: trọng tâm là semantics của Throwable, lợi ích/chi phí của tối ưu và cách ra quyết định, không phải mẹo tăng tốc vô điều kiện.

## 2. Stack trace được tạo và sử dụng như thế nào?

Một **Throwable** chứa các thành phần độc lập nhưng liên quan:

| Thành phần | Công dụng | API thường dùng |
| --- | --- | --- |
| Loại lỗi | Phân loại điều kiện thất bại | **getClass()**, catch theo class |
| Detail message | Diễn giải tình huống hoặc dữ liệu lỗi | **getMessage()** |
| Cause | Một Throwable là nguyên nhân của Throwable khác | **getCause()**, constructor có cause |
| Suppressed exceptions | Các lỗi phụ, thường từ cleanup | **addSuppressed()**, **getSuppressed()** |
| Stack trace | Dấu vết lời gọi được ghi nhận cho Throwable | **getStackTrace()**, **printStackTrace()** |
| Writable stack trace | Quy định Throwable có giữ/chỉnh stack trace theo cơ chế chuẩn không | Constructor được bảo vệ của **Throwable** |

Khi tạo exception theo đường thông thường, constructor của Throwable thường gọi logic **fillInStackTrace()** để ghi nhận ngữ cảnh thực thi vào object. Thời điểm thu nhận trace **thường là lúc xây Throwable**, không phải mỗi lần từ khóa **throw** được thực thi trên cùng một object.

Sau đó, **getStackTrace()** trả về mảng **StackTraceElement**, còn **printStackTrace()** trình bày các frame cùng cause và suppressed. Việc in/log stack trace cũng có thể có chi phí riêng, khác với chi phí thu thập trace ban đầu. Do đó, khi benchmark phải phân biệt:

- **Tạo exception:** cấp phát đối tượng, thực hiện constructor và có thể thu thập trace.
- **Ném và bắt:** chi phí kiểm soát luồng, unwinding tới handler.
- **Lấy stack:** gọi getStackTrace và chuyển dữ liệu thành các frame dễ đọc.
- **Định dạng và xuất log:** chuyển Throwable thành chuỗi, ghi file/console/network.
- **GC:** thu hồi các exception được tạo nhiều lần.

Tắt writableStackTrace có thể tác động tới phần thu thập và lưu trace, nhưng **không làm biến mất mọi chi phí của exception**, không loại bỏ mọi object allocation và không thay đổi luật checked/unchecked hoặc cách catch.

## 3. Constructor bốn tham số của Throwable

Java cung cấp constructor **protected** của Throwable:

~~~java
// Chữ ký API của java.lang.Throwable:
protected Throwable(String message, Throwable cause,
                    boolean enableSuppression,
                    boolean writableStackTrace);
~~~

Hai boolean không đồng nghĩa:

- **enableSuppression:** cho phép Throwable ghi nhận những exception được thêm qua **addSuppressed()**.
- **writableStackTrace:** cho phép Throwable thu thập và duy trì stack trace theo cơ chế chuẩn.

Các class exception con có thể expose cấu hình này qua constructor phù hợp. **Throwable** không mở constructor này như một public factory cho tất cả caller; cách dùng thông thường là kế thừa **Exception**, **RuntimeException** hoặc một class có constructor protected tương ứng, chẳng hạn **RuntimeException(String, Throwable, boolean, boolean)**.

Một class custom điển hình:

~~~java
// Mã minh họa trong file riêng hoặc dưới dạng nested class.
final class LightweightFailure extends RuntimeException {
    LightweightFailure(String message, Throwable cause) {
        super(message, cause, true, false);
        //                  ^ suppression enabled
        //                        ^ writableStackTrace disabled
    }
}
~~~

Cấu hình **true, false** ở đây **giữ suppressed exceptions** nhưng **không giữ stack trace chuẩn**. Nếu đặt **false, true**, ta **tắt suppressed** trong khi vẫn giữ stack trace. Hai trục cấu hình phải được chọn theo yêu cầu chẩn đoán, không tùy tiện gộp thành một cờ “nhẹ”.

Đối với exception có writableStackTrace=false, hợp đồng Throwable nêu constructor không gọi fillInStackTrace theo cách thông thường và các thao tác **fillInStackTrace()** hoặc **setStackTrace(...)** tiếp theo không bổ sung trace chuẩn; **getStackTrace()** trả mảng rỗng. Hành vi của subclass tự override những method này có thể khác, nên nhận định ở đây dành cho cơ chế chuẩn của Throwable/JDK và class ví dụ.

## 4. Ví dụ Java 17+ hoàn chỉnh: ba cấu hình và một exception tái sử dụng

Chương trình này kiểm chứng bằng dữ liệu rõ ràng, không benchmark bằng thời gian nhỏ dễ nhiễu:

- Một exception **fresh** có trace phản ánh hàm tạo/ném ở lần gọi đó.
- Một exception **stackless** có cause và suppressed, nhưng trace rỗng kể cả sau lời gọi fill/set.
- Một exception **suppression disabled** vẫn có stack trace nhưng không lưu lỗi phụ.
- Một exception **shared** được ném hai lần: cùng object, trace vẫn chỉ về nơi tạo ban đầu và suppressed từ lượt trước tiếp tục tồn tại.

Tạo file **StackTraceTradeoffDemo.java**:

~~~java
import java.io.IOException;

public class StackTraceTradeoffDemo {
    static final class ConfiguredFailure extends RuntimeException {
        ConfiguredFailure(String message, Throwable cause,
                          boolean suppression, boolean writableStackTrace) {
            super(message, cause, suppression, writableStackTrace);
        }
    }

    private static final ConfiguredFailure SHARED = makeShared();

    static ConfiguredFailure makeShared() {
        return new ConfiguredFailure("shared failure", null, true, true);
    }

    static void throwNew() {
        throw new ConfiguredFailure("new failure", null, true, true);
    }

    static void throwShared() {
        throw SHARED;
    }

    static String firstAppFrame(Throwable failure) {
        for (StackTraceElement frame : failure.getStackTrace()) {
            if (frame.getClassName().equals(StackTraceTradeoffDemo.class.getName())) {
                return frame.getMethodName();
            }
        }
        return "(none)";
    }

    public static void main(String[] args) {
        try {
            throwNew();
        } catch (ConfiguredFailure failure) {
            System.out.println("fresh origin=" + firstAppFrame(failure));
            System.out.println("fresh has frames=" + (failure.getStackTrace().length > 0));
        }

        ConfiguredFailure stackless = new ConfiguredFailure(
                "stackless", new IOException("root"), true, false);
        System.out.println("stackless frames=" + stackless.getStackTrace().length);
        System.out.println("stackless cause=" + stackless.getCause().getMessage());
        stackless.addSuppressed(new IllegalStateException("cleanup"));
        System.out.println("stackless suppressed=" + stackless.getSuppressed().length);
        stackless.fillInStackTrace();
        stackless.setStackTrace(new StackTraceElement[] {
                new StackTraceElement("Demo", "method", "Demo.java", 1)
        });
        System.out.println("stackless after fill/set=" + stackless.getStackTrace().length);

        ConfiguredFailure noSuppression = new ConfiguredFailure(
                "no suppression", null, false, true);
        noSuppression.addSuppressed(new IOException("secondary"));
        System.out.println("suppression disabled=" + noSuppression.getSuppressed().length);
        System.out.println("suppression-off has frames="
                + (noSuppression.getStackTrace().length > 0));

        ConfiguredFailure first = null;
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                throwShared();
            } catch (ConfiguredFailure failure) {
                if (first == null) {
                    first = failure;
                    failure.addSuppressed(new IOException("from attempt 1"));
                }
                System.out.println("reuse " + attempt + " same=" + (first == failure)
                        + " origin=" + firstAppFrame(failure)
                        + " suppressed=" + failure.getSuppressed().length);
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 StackTraceTradeoffDemo.java
java StackTraceTradeoffDemo
~~~

Stdout đã được kiểm tra khi chạy trên Java 17+:

~~~text
fresh origin=throwNew
fresh has frames=true
stackless frames=0
stackless cause=root
stackless suppressed=1
stackless after fill/set=0
suppression disabled=0
suppression-off has frames=true
reuse 1 same=true origin=makeShared suppressed=1
reuse 2 same=true origin=makeShared suppressed=1
~~~

### Diễn giải kết quả

**Fresh origin = throwNew:** constructor được gọi trong phương thức throwNew. Vì đây là một đối tượng mới có writableStackTrace=true, frame ứng dụng đầu tiên được lưu có tên throwNew. Nó giúp người đọc log truy vết nơi exception được tạo.

**Stackless frames = 0:** constructor được gọi với writableStackTrace=false; không có frame tiêu chuẩn để xác định nơi tạo. Tuy nhiên **getCause()** vẫn trả IOException có message **root**; **getSuppressed()** vẫn có một lỗi cleanup. Tắt stack trace của **wrapper** không tự tắt trace của cause/suppressed là các Throwable khác.

**Stackless after fill/set = 0:** với triển khai được thử, gọi fillInStackTrace và setStackTrace không làm exception có trace trở lại khi flag writableStackTrace đã tắt. Vì thế đây không phải tính năng có thể tùy tiện bật/tắt trên cùng object ở một điểm sau đó.

**Suppression disabled = 0:** IOException được đưa vào addSuppressed nhưng không được lưu. Trong khi đó trace vẫn tồn tại. Điều này cho thấy hai cờ của constructor độc lập.

**Reuse origin = makeShared:** SHARED được tạo trong makeShared, không phải trong mỗi lần throwShared. Khi ném lại cùng object, trace không tự cập nhật theo lần ném mới. **Suppressed=1** ở lần thứ hai không phải lỗi cleanup mới; nó là thông tin được thêm từ lần trước và còn tồn tại trên cùng object.

Điểm cuối cùng là một lý do nghiêm trọng để thận trọng với **singleton exception dùng chung giữa nhiều request**.

## 5. writableStackTrace=false thực sự đánh đổi những gì?

Lợi ích tiềm năng của exception stackless:

- Không phải thu thập stack trace đầy đủ theo constructor chuẩn của Throwable.
- Có thể giảm chi phí CPU và một phần áp lực bộ nhớ khi tạo exception ở tần suất rất cao.
- Khi thật sự không cần từng điểm ném, tránh thu thập dữ liệu không được sử dụng.
- Một trace rỗng cũng làm dữ liệu stack của chính exception đó ngắn hơn khi log.

Nhưng chi phí thông tin bị mất:

- Không có frame nguồn để chỉ ra class/method/line tạo exception.
- Khi lỗi được truyền qua nhiều tầng, caller chỉ còn type, message, cause và context bổ sung nếu có.
- Không thể sau đó gọi **fillInStackTrace()** để lấy lại trace vốn đã bị loại bỏ ở thời điểm lỗi ban đầu.
- Việc phân biệt hai nơi khác nhau cùng ném loại exception có thể trở nên khó khăn.
- Công cụ log/APM hoặc hệ thống tổng hợp lỗi có thể nhóm sai nhiều sự cố chỉ còn cùng type và message.
- Nếu exception được bọc ở tầng cao, trace của wrapper cho biết nơi wrap nhưng không tái tạo được điểm gốc của exception stackless.

**Đánh đổi:** Bạn tiết kiệm một phần chi phí phát sinh tại đường lỗi, nhưng mất chứng cứ kỹ thuật có giá trị cao vào chính lúc cần điều tra. Đối với lỗi hiếm hoặc có ảnh hưởng tới dữ liệu, thường không đáng làm.

### Stackless wrapper không đồng nghĩa mọi trace đều rỗng

Trong ví dụ:

~~~java
// Mã minh họa trong một phương thức phù hợp.
RuntimeException stackless =
    new LightweightFailure("operation failed", new IOException("disk error"));
~~~

Đây là minh họa dùng class **LightweightFailure** ở mục 3. Trace của **stackless** rỗng, nhưng IOException **cause** được tạo như bình thường nên có thể có stack trace riêng. Nếu bạn tắt writableStackTrace trên wrapper để giảm overhead, mà vẫn tạo cause dày và in cây exception đầy đủ, lợi ích thực tế sẽ khác so với trường hợp hoàn toàn không có trace.

Ngược lại, nếu cả cause và wrapper đều bị thay thành các đối tượng không ghi dấu vết, lượng thông tin chẩn đoán mất đi càng lớn. Benchmark phải dùng đúng **chuỗi Throwable thực tế** của hệ thống, không chỉ một object mock.

## 6. enableSuppression và writableStackTrace hoàn toàn độc lập

Bốn tổ hợp cấu hình cần được hiểu rõ:

| enableSuppression | writableStackTrace | Kết quả mong đợi trong cơ chế Throwable chuẩn |
| --- | --- | --- |
| true | true | Có thể giữ suppressed và stack trace |
| true | false | Giữ suppressed; stack trace của chính Throwable rỗng |
| false | true | Không lưu lỗi qua addSuppressed; vẫn có stack trace |
| false | false | Không lưu suppressed và không giữ stack trace |

**Suppressed exception** đặc biệt quan trọng khi dùng **try-with-resources**. Nếu thân try ném lỗi A và **close()** ném lỗi B, cơ chế chuẩn sẽ ưu tiên A, thêm B vào A.getSuppressed() khi A hỗ trợ suppression.

Nếu **A** là một Throwable có **enableSuppression=false**, lỗi B không được giữ bằng **addSuppressed()** trên A. Khi chỉ xem stack trace/cause của A, bạn có thể **mất dấu vết lỗi cleanup**. Đây không chỉ là vấn đề “ít thông tin log” mà có thể che dấu kết quả thu hồi tài nguyên, rollback hoặc close đã thất bại.

Vì vậy, **không nên tắt suppression chỉ để giảm thêm chút overhead** khi API còn có khả năng dùng try-with-resources hoặc bổ sung lỗi phụ. Nếu lỗi phụ có ý nghĩa nghiệp vụ, giữ suppression là yêu cầu quan sát thiết yếu.

**Cách đọc code:** Ở constructor **super(message, cause, suppression, writable)**, boolean đầu nói về suppressed, boolean sau nói về stack trace. Viết tên tham số rõ ràng và dùng factory có tên là cách giảm nhầm lẫn thứ tự.

## 7. Tái sử dụng cùng đối tượng exception khác với tái sử dụng một loại exception

Hai mẫu dễ bị đánh đồng:

~~~java
// Mã minh họa, phương thức được đặt trong class thích hợp.
throw new IllegalStateException("invalid state");
~~~

Mỗi lần chạy tạo **một Throwable mới**, thường có stack trace gắn với lần tạo đó.

~~~java
// Mã minh họa, biến SHARED đã được tạo trước.
throw SHARED;
~~~

Mỗi lần ném dùng **cùng một Throwable đã tồn tại**. Tham chiếu, message, cause, suppressed list và trace đều thuộc về **object đó**. Từ khóa throw **không tạo bản sao Throwable** và không ghi trace mới tự động cho mỗi lần ném.

Có thể giảm cấp phát nhờ reuse, nhưng đổi lại:

1. Stack trace phản ánh nơi tạo object lần đầu, không phản ánh từng lần lỗi.
2. Message cố định khó chứa ngữ cảnh request cụ thể.
3. Cause có thể không liên quan lần ném mới hoặc không được đổi an toàn.
4. Suppressed exceptions có thể tích lũy từ nhiều lần xử lý.
5. Nhiều thread có thể cùng nhìn thấy/chỉnh một exception duy nhất.
6. Các công cụ chẩn đoán, logging và tính năng nhóm lỗi có thể không phân biệt được từng sự kiện.

**Đặc biệt nguy hiểm:** Reuse một exception thông thường **có stack trace** nhưng tưởng trace sẽ tự cập nhật mỗi lần throw. Đó là cách tạo ra một lỗi vừa có dấu vết sai lệch, vừa trông có vẻ rất đáng tin.

## 8. Vì sao không gọi fillInStackTrace() trên exception dùng chung mỗi lần ném?

Có thể gặp ý tưởng:

~~~java
// Phản mẫu minh họa, SHARED là cùng một Throwable mutable.
SHARED.fillInStackTrace();
throw SHARED;
~~~

Điều này không còn giữ được lợi ích “không thu thập trace”: **fillInStackTrace()** làm công việc ghi nhận stack mới. Trong môi trường nhiều luồng, hai request có thể cùng chỉnh stack trace của một object. Lỗi của request A có thể bị ghi lại stack bởi request B trước khi A kịp in log hoặc thu thập dấu vết.

Ngoài ra, **fillInStackTrace()** không xóa suppressed exceptions, không tự đổi cause và không tạo một bản sao độc lập cho từng lần throw. Việc “làm mới stack” không khắc phục bản chất **chia sẻ trạng thái mutable** của Throwable.

Nếu muốn trace đúng cho từng sự cố, cách bình thường và rõ ràng nhất là **tạo một exception riêng cho sự cố đó**. Nếu thật sự đã quyết định không cần trace, một loại exception stackless mới mỗi lần cũng có thể phù hợp hơn singleton chia sẻ, vì vẫn giữ được sự độc lập của message/cause/suppressed.

**Ngoại lệ với writableStackTrace=false:** Với cơ chế Throwable chuẩn, fillInStackTrace bị vô hiệu hóa và không thể dùng để lấy lại trace; đây không phải phương pháp chữa mất dữ liệu sau khi đã tắt.

## 9. Cause, suppressed và message tạo rủi ro khi chia sẻ

Các trường liên quan đến Throwable không nên được giả định là “read-only hoàn toàn” chỉ vì code của bạn không có setter message:

- Một số Throwable có thể cấu hình **cause** khi khởi tạo hoặc qua **initCause()** theo ràng buộc của JDK.
- **addSuppressed()** bổ sung một exception mới vào danh sách suppressed nếu suppression được bật.
- **setStackTrace()** thay đổi biểu diễn stack trace đối với Throwable có writableStackTrace phù hợp.
- **fillInStackTrace()** có thể thay đổi dấu vết theo lần gọi.
- Subclass tùy chỉnh còn có thể có những field mutable riêng.

Ví dụ, SHARED ở phần 4 được tạo với **suppression=true**. Sau lượt xử lý thứ nhất, catch gắn IOException “from attempt 1”. Trong lượt hai, **getSuppressed()** vẫn trả IOException đó, dù việc xử lý lần hai không gặp lỗi close tương ứng.

Điều này có thể dẫn đến:

- Log request thứ hai chứa lỗi cleanup của request thứ nhất.
- Thông tin nhạy cảm từ một tenant/request bị đưa vào log của tenant/request khác.
- Bộ đếm số lỗi phụ bị phình theo số lượt sử dụng.
- Công cụ quan sát báo nguyên nhân lỗi sai.
- Tránh được object allocation nhỏ nhưng gây khó hiểu lâu dài cho vận hành.

Dù **addSuppressed()** có những bảo vệ nội bộ của JDK để quản lý danh sách, điều đó **không biến một Throwable dùng chung thành đại diện đúng cho nhiều sự cố độc lập**. Tính đúng đắn nghiệp vụ và khả năng phân biệt từng lần lỗi là một vấn đề khác với việc một method có được đồng bộ nội bộ hay không.

## 10. Trường hợp đồng thời: cùng Throwable ở nhiều thread

Giả sử hai request A và B cùng dùng một singleton exception:

~~~java
// Mã minh họa; một shared exception được giữ ở field static.
static final RuntimeException REJECTED =
        new RuntimeException("rejected");

static void reject() {
    throw REJECTED;
}
~~~

Khi A và B đều gọi reject(), chúng cùng nhận **cùng một object**. Nếu một nhánh bắt A gọi addSuppressed, setStackTrace hoặc fillInStackTrace, nhánh B có thể quan sát các thay đổi đó. Nhiều logger ghi object Throwable ở thời điểm khác nhau cũng có thể tạo kết quả khác nhau.

Với một singleton stackless và suppression bị tắt, nguy cơ tích lũy dữ liệu giảm đi vì hai cơ chế đã bị vô hiệu hóa, nhưng vẫn có những vấn đề:

- Không có stack trace cho từng sự kiện.
- Cùng cause và message không mô tả từng request.
- Không thể gắn context riêng bằng suppressed.
- Một subclass có field mutable vẫn có thể chia sẻ trạng thái.
- Những logic dùng object identity để nhóm hoặc đếm exception có thể nhầm nhiều sự kiện là một.

Do đó **singleton stackless exception** chỉ có thể là một lựa chọn chuyên biệt khi mọi lần ném có **cùng ý nghĩa, không cần ngữ cảnh per-request**, không được chia sẻ dữ liệu mutable bổ sung và đã có quan sát khác. Với lỗi dữ liệu quan trọng, nên ưu tiên exception riêng cho từng thất bại.

## 11. Exception là điều kiện bất thường hay cơ chế điều khiển luồng?

Một câu hỏi về hiệu năng còn quan trọng hơn việc tắt trace: **vì sao exception xuất hiện với tần suất cao?**

Nếu code dùng exception để đi qua một nhánh xử lý được dự kiến xảy ra hàng triệu lần, hệ thống đang phải trả chi phí throw/catch và có thể cả trace để thực hiện điều mà một kết quả kiểm tra bình thường làm được.

Ví dụ phản mẫu khi đầu vào thường xuyên không phải số:

~~~java
// Mã minh họa trong một hàm đã có text.
int parseOrZero(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ignored) {
        return 0;
    }
}
~~~

Đoạn này biên dịch nếu đặt trong class phù hợp. Nó có thể hợp lý trong ứng dụng nhỏ, nhưng nếu dữ liệu không hợp lệ là trường hợp **rất phổ biến trong hot path** thì tạo exception liên tục có thể đáng đo. Đừng lập tức tìm cách sửa thành “NumberFormatException không stack trace”, vì exception đó do JDK tạo và bạn không kiểm soát constructor của nó.

Các hướng cải thiện đúng hơn tùy bài toán:

1. Dùng parser trả **trạng thái/giá trị** thay vì ném exception cho trường hợp dự kiến.
2. Validate trước những điều kiện có thể kiểm tra rẻ, nhưng phải tránh tái tạo toàn bộ parser hai lần gây chi phí lớn hơn.
3. Phân loại đầu vào không hợp lệ thành một kiểu kết quả rõ ràng, chẳng hạn Optional, Result hoặc mã lỗi.
4. Chỉ dùng exception khi **hợp đồng không thể hoàn tất bình thường** hoặc lỗi thực sự bất thường.
5. Đo lại hiệu năng và độ phức tạp sau khi đổi.

**Chú ý:** Kiểm tra trước không bảo đảm luôn nhanh hơn parse trực tiếp. Nếu trường hợp lỗi rất hiếm, thêm một lượt validation có thể làm đường thành công chậm hơn. Quyết định dựa vào **tần suất thực tế của lỗi** và benchmark có cấu hình phù hợp.

## 12. Nơi có thể cân nhắc exception stackless

Không phải mọi ứng dụng dùng stackless exception đều sai. Một số thư viện hiệu năng cao dùng tín hiệu nội bộ đã biết trước, tần suất lớn, hoặc dùng API để truyền một tình trạng kết thúc đã được dự đoán. Tuy nhiên, cần kiểm tra phạm vi cụ thể:

| Tình huống | Có thể cân nhắc? | Điều kiện bắt buộc |
| --- | --- | --- |
| Trạng thái nội bộ thuần túy, không có dữ liệu per-request, đã đo là hot path | Có, thận trọng | Sự kiện được hiểu rõ, quan sát khác đầy đủ |
| Lỗi parse đầu vào người dùng cần ghi vị trí nguồn | Thường không | Giữ trace, type, message/cause đủ điều tra |
| Exception báo bug vi phạm bất biến không dự đoán trước | Không nên | Trace là dữ liệu cốt lõi để sửa bug |
| Lỗi database/network không ổn định | Thường không | Cần trace, cause, retry context, idempotency |
| Cơ chế dừng nội bộ không được truyền qua API công khai | Có thể | Được đóng gói, tài liệu hóa, có test đầy đủ |
| Singleton exception trong server nhiều tenant | Rủi ro cao | Không rò dữ liệu giữa các request, không dùng suppressed/context |
| Exception dùng trong hot loop làm điều kiện bình thường | Ưu tiên đổi thiết kế | Dùng return/result thay vì throw cho đường dự kiến |

Khi áp dụng stackless cho một API công khai, người sử dụng thư viện có thể không biết bạn đã bỏ stack trace, dẫn đến điều tra lỗi khó hơn. Một quyết định tối ưu ở thư viện có thể đẩy chi phí xử lý sự cố cho nhiều hệ thống downstream. Điều này cần được mô tả rõ trong contract hoặc tài liệu vận hành.

## 13. Phân biệt tối ưu loại exception và tối ưu từng instance

Có ít nhất ba phương án khác nhau:

**A. Exception bình thường, tạo mới:**

~~~java
// Mã minh họa.
throw new IllegalStateException("config changed unexpectedly");
~~~

Ưu tiên cho lỗi thực sự bất thường; có trace đúng, message có thể mô tả tình huống.

**B. Exception stackless, tạo mới:**

~~~java
// Mã minh họa; LightweightFailure từ mục 3.
throw new LightweightFailure("operation not permitted", cause);
~~~

Vẫn cấp phát một object cho sự kiện mới, nhưng bỏ thu thập trace cho object đó. Cause riêng và suppressed riêng có thể giữ ngữ cảnh. Phương án này không phải singleton và ít rủi ro “trộn request” hơn.

**C. Một exception duy nhất tái sử dụng:**

~~~java
// Mã minh họa; SHARED đã được định nghĩa trong class.
throw SHARED;
~~~

Có thể tránh cấp phát trên mỗi lần ném, nhưng trace/message/cause/suppressed thuộc về cùng object. Nếu SHARED có stack trace, vị trí trong trace không được cập nhật tự động; nếu SHARED stackless, không còn vị trí nào trong trace chính để xác định lần ném.

Nên chọn A làm mặc định. Nếu A có vấn đề đã đo, cân nhắc đổi luồng xử lý hoặc B trước khi nghĩ tới C. Không có bảo đảm B luôn đủ nhanh hay C luôn nhanh nhất, bởi chi phí phụ thuộc JVM, compiler, dạng exception, catch path và workload.

## 14. Những hiểu nhầm về fillInStackTrace()

**Throwable.fillInStackTrace()** là method có thể được gọi hoặc override. Nó không phải một lời hứa rằng mọi exception đều luôn có thể tái tạo trace của lần ném trong quá khứ.

Với đối tượng thông thường:

~~~java
// Mã minh họa; failure là Throwable có writableStackTrace=true.
failure.fillInStackTrace();
~~~

Lời gọi làm mới stack trace theo vị trí **đang gọi fillInStackTrace**, không quay về một thời điểm cũ mà JVM chưa ghi lại. Nếu gọi từ catch/logging ở tầng cao, trace mới có thể chỉ ra tầng cao đó và mất vị trí lỗi ban đầu.

Với writableStackTrace=false, **fillInStackTrace()** theo triển khai chuẩn không bổ sung trace; điều này đã được thử trong ví dụ Java 17 mục 4.

Cũng không nên override **fillInStackTrace()** chỉ để trả **this** trên mọi custom exception mà không đánh giá tác động:

~~~java
// Mã minh họa một kiểu custom exception chuyên dụng.
final class NoTraceFailure extends RuntimeException {
    @Override
    public synchronized Throwable fillInStackTrace() {
        return this;
    }
}
~~~

Đây là phương pháp tối ưu từng được sử dụng, nhưng có những khác biệt về thời điểm constructor gọi method có thể override, inheritance, hành vi stack trace và khả năng bảo trì. Constructor có **writableStackTrace=false** thể hiện ý định rõ hơn khi phù hợp với loại Throwable bạn kiểm soát. Tránh xem override này là công thức tối ưu bắt buộc cho mọi exception class.

## 15. Đo hiệu năng đúng cách trước khi đưa ra quyết định

Một phép đo ngắn bằng **System.nanoTime()** bao quanh một vòng lặp throw/catch không đủ để kết luận việc tắt trace hay singleton exception luôn tốt hơn. JIT, escape analysis, class initialization, tiered compilation, CPU scheduling, GC và logging có thể làm các lần chạy khác nhau.

Cách tiếp cận chuẩn hơn là benchmark có khởi động và kiểm soát workload, thường dùng **JMH**. Nếu không thể dùng JMH, chỉ nên coi kết quả đo đơn giản là thông tin sơ bộ, không phải cơ sở quyết định kiến trúc.

Benchmark cần tách các phương án:

1. **Điều kiện bình thường trả status/boolean**.
2. **Tạo mới exception bình thường**, ném và bắt.
3. **Tạo mới custom exception stackless**, ném và bắt.
4. **Tái sử dụng exception bình thường**, ném và bắt.
5. **Tái sử dụng exception stackless**, ném và bắt.

Đồng thời nên có hai nhóm workload:

- **Đường thành công phổ biến:** có thể không tạo exception nào.
- **Đường lỗi theo tần suất thực tế:** ví dụ lỗi 0,01%, 1% hoặc 50% tùy số đo thực.

### Những chỉ số nên theo dõi

| Chỉ số | Vì sao quan trọng? |
| --- | --- |
| Throughput/operations per second | Năng lực xử lý tổng thể của đường mã |
| p50/p95/p99 latency | Mức độ biến động và độ trễ đuôi |
| Allocation bytes/op | Số byte cấp phát có liên quan tới GC |
| GC collections/time | Áp lực thu hồi bộ nhớ |
| CPU sampling/profiling | Constructor, fillInStackTrace, formatting/logging có thật là nút thắt không |
| Error rate và error types | Tần suất exception theo loại và nguồn |
| Chi phí observability | Stack logging, gửi dữ liệu APM, storage/network |
| Khả năng chẩn đoán sự cố | Có xác định được class/method/line và request liên quan không |

Nên đo trên cùng JDK, cùng cấu hình heap/GC, cùng kiểu build, input, mức tải và môi trường gần production. **Không đưa một con số “nhanh hơn X lần” vào tài liệu nếu chưa có benchmark áp dụng đúng ứng dụng**, bởi chi phí thu thập trace và tác động tối ưu phụ thuộc môi trường.

### Đo riêng việc tạo exception và in log

Nếu benchmark chỉ ném và bắt mà không in stack trace, nó có thể bỏ qua chi phí log thực tế. Ngược lại, nếu benchmark ghi toàn bộ stack vào console trong vòng lặp, chi phí I/O dễ áp đảo chi phí Throwable constructor. Cả hai đều có giá trị khi được đặt đúng câu hỏi, nhưng không thể thay thế nhau.

Đối với phương án stackless, benchmark cũng phải xét rằng thiếu trace có thể làm debugging hoặc grouping trong APM trở nên khó hơn. Chi phí vận hành khi một lỗi hiếm khó tái hiện có thể lớn hơn phần tiết kiệm nanosecond trong đường nóng.

## 16. Tác động của JVM, JIT và các tối ưu nội bộ

Không nên khẳng định cấu tạo stack trace có cùng chi phí trên mọi bản Java. HotSpot/JVM có thể sử dụng những tối ưu, biểu diễn nội bộ hoặc đường ném nhanh khác nhau. Một số exception do JVM tạo lặp rất nhiều trong tình huống đặc biệt có thể được tối ưu theo chính sách triển khai, khiến stack trace quan sát khác với các exception do Java code tạo ra.

Vì vậy cần lưu ý:

- Chi phí **new RuntimeException(...)** do mã ứng dụng tạo không đại diện cho tất cả exception JVM sinh ra.
- Một kết quả benchmark trên một phiên bản JDK không chắc chuyển nguyên sang phiên bản khác.
- Tối ưu liên quan tới JIT/hot throw sites có thể khác giữa code đang warm-up và code đã ổn định.
- Một thông điệp hoặc trace thiếu trong điều kiện đặc biệt không chứng minh Throwable nói chung luôn tắt trace.
- Flags JVM liên quan tới tối ưu exception là yếu tố triển khai; không nên dùng chúng như biện pháp thay thế cho thiết kế exception contract rõ ràng.

Nếu nghi JVM đã tối ưu mất một số stack trace trên đường lỗi cực nóng, đối chiếu phiên bản JDK, cờ runtime, số lần tái hiện, cách exception được tạo và log. Không mặc định đó là bằng chứng log pipeline hoặc JDK bị lỗi.

## 17. Stackless exception và logging/APM

Phần mềm quan sát lỗi thường dựa vào tổ hợp:

- Exception class và message.
- Top application frame.
- Full stack trace.
- Cause/suppressed chain.
- Tên service, operation, request ID/trace ID.
- Thread/async context và phiên bản deploy.

Khi writableStackTrace=false, **top application frame trên chính exception không tồn tại**. Công cụ nhóm lỗi chỉ theo loại và message có thể:

- Gộp những lỗi khác nhau vào một nhóm.
- Tăng false-positive khi cảnh báo chung.
- Không biết code path nào phát sinh thường nhất.
- Khiến việc điều tra sau deploy kém chính xác.
- Khó chứng minh một bản sửa đã loại bỏ đúng nơi ném lỗi.

Nếu bắt buộc dùng stackless, cần thay thế bằng metadata **được thiết kế trước**, ví dụ error code, event name, operation identifier, correlation ID và structured log riêng. Các metadata này thường nhẹ hơn full stack trace nhưng **không tương đương** một stack trace thực tế; chúng phụ thuộc vào việc mã tác giả ghi đúng nơi và đúng ngữ cảnh.

**Không đưa raw input nhạy cảm vào message** chỉ để bù stack trace. Dữ liệu trong lỗi và log vẫn phải được bảo vệ, đặc biệt khi exception singleton có thể bị dùng qua nhiều request/tenant.

## 18. Khi cần tạo một exception mới thay vì tái sử dụng

Ưu tiên object mới khi có bất kỳ đặc điểm sau:

- Mỗi thất bại cần message chứa ID hoặc trạng thái riêng.
- Nguyên nhân thực sự khác nhau và cần lưu cause chính xác.
- Có thể phát sinh suppressed exception khi đóng tài nguyên.
- Hai request/threads có thể thất bại đồng thời.
- Cần stack trace đúng vị trí gọi.
- Code phía ngoài có thể gọi **initCause**, **setStackTrace**, **fillInStackTrace** hoặc **addSuppressed**.
- Trạng thái lỗi cần được serialize, retry hoặc đưa qua ranh giới service với ngữ cảnh riêng.
- Lỗi thể hiện vi phạm invariant, bug hoặc thất bại có tác động tới dữ liệu.

Nếu performance thực sự quan trọng, một **fresh stackless custom exception** có thể là giải pháp trung gian: mỗi sự kiện vẫn có identity/cause/suppressed riêng, nhưng bỏ trace chính. Nếu cần trace theo điều kiện, có thể cân nhắc lấy mẫu chỉ một tỷ lệ lỗi có stack trace và giữ metrics tổng thể, song phải thiết kế sampling rõ ràng và tránh đánh mất các sự cố hiếm nghiêm trọng.

Không có một API Throwable tiêu chuẩn nào tự bảo đảm “cứ mỗi 100 lần ném thì ghi trace một lần”. Đây phải là chính sách ứng dụng, được test cùng hiệu năng và khả năng quan sát.

## 19. Một số lỗi dễ mắc với class stackless tùy chỉnh

**Nhầm thứ tự hai boolean constructor.** **super(message, cause, false, true)** tắt suppression nhưng vẫn bật trace, không phải điều ngược lại. Đặt tên tham số/constructor rõ ràng.

**Tưởng stackless cũng mất cause.** Cause là mối liên hệ riêng; **getCause()** có thể vẫn dùng được. Điều cần kiểm tra là đối tượng cause đã được tạo như thế nào.

**Tưởng tắt trace thì suppression tự tắt.** Hai lựa chọn độc lập. Tắt suppression có thể làm mất lỗi cleanup quan trọng.

**Tưởng ném lại cùng exception sẽ tự ghi vị trí mới.** Stack trace thường phản ánh lúc tạo object. Throw không đồng nghĩa fillInStackTrace.

**Tạo singleton có trace rồi dùng trên mọi request.** Log có thể luôn trỏ vào constructor/factory khởi tạo, không phải đường lỗi hiện tại.

**Gọi fillInStackTrace trên singleton chia sẻ.** Có thể triệt tiêu lợi ích hiệu năng và tạo race trong thông tin debug.

**Dùng same-object singleton kèm addSuppressed.** Lỗi cleanup của nhiều lần xử lý có thể bị trộn và lộ dữ liệu giữa các bối cảnh.

**Chỉ benchmark lỗi mà không tính đường thành công.** Nếu lỗi thực tế hiếm, tối ưu đường exception có thể không thay đổi đáng kể latency tổng thể.

**Bỏ stack trace trước khi có cách thay thế.** Khi sự cố hiếm xảy ra, đội vận hành chỉ còn message chung và không thể tìm throw site.

**Coi microbenchmark trên console là kết luận production.** Logging I/O và warm-up có thể lấn át các chi phí cần đo.

**Dùng exception làm cờ vòng lặp.** Nếu một tình huống xảy ra thường xuyên và không phải lỗi, nên cân nhắc API trả kết quả thay vì liên tục ném.

**Tối ưu khi chưa có số liệu.** Nếu hotspot không nằm ở Throwable constructor/stack capture, việc bỏ trace chỉ làm mất khả năng debug mà không đem lại lợi ích đáng kể.

## 20. Testing: đúng semantics trước khi đo tốc độ

Trước khi dùng custom stackless hay reused exception, viết test cho các hợp đồng sau:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Fresh exception bình thường | Có frame tương ứng với nơi tạo |
| Stackless exception | getStackTrace() rỗng |
| Stackless có cause | getCause() vẫn giữ cause theo thiết kế |
| Stackless có suppression=true | addSuppressed lưu lỗi phụ |
| Suppression=false, trace=true | getSuppressed() rỗng dù addSuppressed được gọi; trace vẫn có |
| Gọi fill/set trên stackless | Trace vẫn rỗng theo cơ chế Throwable chuẩn |
| Ném lại shared exception | Cùng object identity, trace không thay theo lần ném |
| Shared exception có suppressed | Lần sau vẫn thấy lỗi từ lần trước; test phát hiện leak |
| Nhiều thread sử dụng shared | Không được mặc định thông tin lỗi thuộc về từng request |
| Caller wrap exception | Cause/suppressed được truy vết đúng, không mất lỗi gốc |

Trong ví dụ chính, phép so **first == failure** khẳng định object reused. **firstAppFrame** chỉ đọc những frame thuộc class ứng dụng, giúp quan sát vị trí tạo mà không phụ thuộc số dòng JDK.

Không nên viết test cố định thời gian “tạo exception phải dưới X nanosecond” trên CI thông thường. Để kiểm tra tốc độ, dùng benchmark có điều kiện môi trường được kiểm soát và báo cáo phạm vi sai số. Unit test tập trung vào **correctness của API và thông tin lỗi**.

### Kiểm tra log thật

Nếu ứng dụng có formatter hoặc APM, tạo một tình huống lỗi test và xác minh:

1. Stackless object được biểu diễn đúng, không làm formatter crash vì trace rỗng.
2. Cause và suppressed của nó vẫn được hiển thị nếu tồn tại.
3. Lỗi bình thường vẫn có frame/dòng nguồn đủ điều tra.
4. Exception shared (nếu có) không bị đưa vào log kèm context của request khác.
5. Các dữ liệu nhạy cảm trong message/cause/suppressed được che theo chính sách.

## 21. Quy trình ra quyết định cho hot path

Một quyết định kỹ thuật hợp lý nên đi theo trình tự:

**Bước 1 — Xác định exception có phải đường xử lý bình thường?** Nếu đúng, cân nhắc thiết kế lại API trả trạng thái/giá trị trước khi tối ưu Throwable.

**Bước 2 — Đo tần suất exception thực tế.** Thu thập số lượng theo loại, request, endpoint, phiên bản, tải và thời gian. Nếu chỉ xảy ra rất ít, overhead có thể không đáng kể.

**Bước 3 — Profile đúng phần tốn chi phí.** Là khởi tạo Throwable, thu stack, xử lý catch, format log, I/O ghi log hay GC? Giải pháp phải nhắm vào nguyên nhân đo được.

**Bước 4 — Chọn thay đổi ít làm mất thông tin nhất.** Ví dụ giảm log trùng, giới hạn logging quá nhiều, thay exception bằng kết quả bình thường, hoặc tạo mới exception stackless chuyên dụng thay vì dùng singleton.

**Bước 5 — Giữ chính sách chẩn đoán.** Nếu cần stackless, bổ sung error code, operation, version và correlation ID, cùng đường bật log/tracing khi cần.

**Bước 6 — Test correctness.** Xác minh cause, suppressed, trace policy, thread safety, không rò dữ liệu và semantics khi throw lại.

**Bước 7 — Benchmark.** Dùng workload gần thực tế, cùng JDK/GC và độ tải, xem cả throughput, latency, allocation, logging và các đường lỗi.

**Bước 8 — Triển khai có kiểm soát.** Dùng rollout, metric và khả năng quay về trace đầy đủ khi phát hiện sự cố. Một thay đổi nhỏ trong Throwable có thể có ảnh hưởng lớn tới khả năng vận hành.

## 22. Câu hỏi thực hành và cách suy luận

**Câu hỏi 1: Nếu stack trace của một exception rỗng, chắc chắn đã dùng writableStackTrace=false?**

Không. Có thể là Throwable được tùy biến, stack trace bị cấu hình lại, một tối ưu JVM hoặc logging chỉ hiển thị thiếu dữ liệu. Hãy xem code tạo exception, kiểu JVM và trạng thái object thật trước khi kết luận.

**Câu hỏi 2: Có thể gọi fillInStackTrace() để khôi phục trace đã bỏ không?**

Không thể khôi phục chính xác một call stack quá khứ mà chưa được lưu lại. Với writableStackTrace=false trên Throwable chuẩn, fillInStackTrace không bổ sung trace. Với Throwable thông thường, gọi method sẽ thu nhận stack của **thời điểm gọi mới**, có thể không phải nơi lỗi gốc.

**Câu hỏi 3: Nếu suppression bị tắt, try-with-resources còn đóng resource không?**

Có. Việc gọi close và việc **lưu exception cleanup vào suppressed** là hai chuyện khác nhau. Khi lỗi chính có suppression=false, lỗi từ close có thể không được lưu trên nó, nhưng cơ chế đóng tài nguyên vẫn được thực hiện theo đường thoát.

**Câu hỏi 4: Reuse exception có phải luôn tạo kết quả sai?**

Không phải mọi trường hợp đều sai. Một số cơ chế nội bộ dùng singleton exception chỉ để báo một trạng thái dự kiến, không có thông tin per-event cần lưu. Tuy nhiên, kiểu API này phải được thiết kế có chủ đích, không chứa trạng thái dùng chung có thể bị sửa sai và phải có phương thức quan sát thích hợp. Không dùng nó làm mặc định cho lỗi cần chẩn đoán.

**Câu hỏi 5: Tại sao shared exception còn suppressed từ lần trước?**

Vì **addSuppressed()** cập nhật chính đối tượng Throwable đang được chia sẻ. Khi ném lại, object đó không được tạo lại nên danh sách suppressed của nó cũng không tự làm mới.

**Câu hỏi 6: Khi bật writableStackTrace=false trên wrapper, cause có còn stack trace không?**

Có thể có, nếu cause được xây dựng bình thường. Cấu hình stack trace của wrapper không tự áp lên mọi Throwable mà nó tham chiếu.

**Câu hỏi 7: Vì sao chưa nên áp dụng ngay cho mọi IllegalArgumentException?**

IllegalArgumentException thường cung cấp bằng chứng rằng caller vi phạm hợp đồng API. Bỏ trace có thể khiến bạn không biết caller nào đưa input sai. Nếu số lần lỗi lớn, trước tiên tìm và sửa caller hoặc validation trước khi loại bỏ thông tin chẩn đoán.

## 23. Checklist trước khi chấp nhận tối ưu

1. **Tính cần thiết:** Đã có profile chứng minh Throwable construction/stack trace nằm trên hot path chưa?
2. **Tần suất:** Exception đang xảy ra bao nhiêu lần, thuộc đường lỗi hiếm hay trường hợp bình thường?
3. **Phạm vi:** Custom exception chỉ dùng nội bộ hay bị lộ qua API cho hệ thống khác?
4. **Cấu hình:** Đã phân biệt enableSuppression với writableStackTrace theo thứ tự constructor chưa?
5. **Trace:** Người dùng còn cần class/method/line theo từng sự cố không?
6. **Cause:** Có giữ nguyên cause thích hợp cho từng lần lỗi không?
7. **Suppressed:** Có thể xảy ra lỗi cleanup không, và có bắt buộc giữ thông tin ấy không?
8. **Object identity:** Có đang reuse cùng Throwable qua nhiều request/thread không?
9. **Thread safety:** Có nguy cơ fillInStackTrace/setStackTrace/addSuppressed làm trộn thông tin không?
10. **Observability:** Có error code, request ID, operation và logging thay thế thông tin trace mất đi không?
11. **Benchmark:** Đã đo trên cùng JDK/workload và tách chi phí tạo exception, throw/catch, format/log, GC chưa?
12. **Tests:** Đã thử stackless, suppressed, cause, reuse và trường hợp lỗi kép chưa?
13. **Rollout:** Có thể bật lại full trace khi cần điều tra sự cố khó tái hiện không?
14. **Bảo mật:** Có kiểm tra ngữ cảnh Throwable dùng chung không làm lộ thông tin giữa user/tenant không?

**Kết luận:** Tắt **writableStackTrace** là đánh đổi **chi phí thu thập stack** lấy **mất dấu vị trí phát sinh lỗi**. Tái sử dụng Throwable còn đánh đổi nhiều hơn: dùng cùng object, cause/message/trace/suppressed qua những sự kiện khác nhau, làm thông tin chẩn đoán dễ sai lệch hoặc trộn giữa request. Hai kỹ thuật không phải lựa chọn tối ưu mặc định. Trong phần lớn mã ứng dụng, hãy **giữ exception bình thường**, sửa nguyên nhân khiến exception xuất hiện quá thường xuyên, và chỉ dùng stackless hoặc reuse sau khi đã đo được lợi ích và xác định được cách bảo toàn đúng nghĩa lỗi, trạng thái và khả năng vận hành.
