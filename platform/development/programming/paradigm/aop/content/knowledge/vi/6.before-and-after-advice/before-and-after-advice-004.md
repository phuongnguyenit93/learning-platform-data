# Advice khi kết thúc bất kể thành công hay thất bại trong AOP

> **Mục tiêu học tập:** Hiểu advice chạy khi rời một join point theo cả nhánh hoàn tất bình thường lẫn nhánh ném ngoại lệ (*after/finally advice*); phân biệt nó với advice chỉ chạy trước, chỉ chạy sau thành công, chỉ chạy sau thất bại và advice bao quanh; biết thiết kế thao tác dọn dẹp, đo lường và quan sát mà không làm sai kết quả hoặc che giấu ngoại lệ của chương trình.

## 1. Vì sao cần một advice chạy ở cả hai nhánh?

Giả sử chương trình muốn ghi rằng một thao tác đã **kết thúc**, bất kể thao tác trả về giá trị mong muốn hay ném lỗi. Nếu đặt dòng ghi nhận chỉ sau lời gọi nghiệp vụ thì khi lời gọi ném ngoại lệ, chương trình có thể không tới được dòng ghi nhận đó.

~~~java
String result = processOrder();
System.out.println("Operation finished");
~~~

Đây là **mảnh mã minh họa**, không phải chương trình chạy độc lập. Nếu `processOrder()` ném ngoại lệ, câu `println` tiếp theo không chạy theo đường thực thi thông thường.

Tư duy AOP đặt ra một **mối quan tâm xuyên suốt**: ghi dấu kết thúc, giải phóng phạm vi quan sát, đóng một bộ đo hoặc thu dọn ngữ cảnh cho nhiều điểm thực thi. Khi áp dụng cho những join point được pointcut chọn, **after/finally advice** diễn đạt: *“Thực hiện hành vi này khi hoạt động đang được quan sát rời khỏi phạm vi tương ứng, bất kể hoàn tất bình thường hay bất thường.”*

Điều đó hữu ích cho việc quan sát, thu dọn trạng thái và phục hồi ngữ cảnh dùng chung. Nhưng cần hiểu thật chính xác **kết thúc hoạt động nào**, **ngoại lệ đi qua ranh giới nào**, **advice nào được kích hoạt**, và **những trường hợp không có một lần thoát thông thường nào**.

## 2. Đặt after/finally advice trong mô hình thành phần AOP

Các khái niệm liên quan:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Join point** | Điểm/sự kiện được mô hình AOP nhận diện | Một lần thực thi phương thức `charge()` |
| **Pointcut** | Điều kiện lựa chọn tập join point | Chọn các thao tác thanh toán cần quan sát |
| **Advice** | Hành vi bổ sung tại các điểm được chọn | Ghi dấu bắt đầu/kết thúc |
| **Aspect** | Mô-đun tổ chức một mối quan tâm xuyên suốt | Theo dõi thời lượng giao dịch |
| **Weaving** | Cách kết hợp advice với chương trình gốc | Chèn/kết nối logic quan sát tại những điểm phù hợp |

After/finally advice là **một loại advice**, nghĩa là nó trả lời câu hỏi *“hành vi bổ sung chạy khi nào so với join point?”*. Nó không tự trả lời *“điểm nào được chọn?”*; câu hỏi đó thuộc **pointcut**.

Giả sử một pointcut chọn thực thi `charge()` và `refund()`. Cùng một after/finally advice có thể được áp dụng khi mỗi lần thực thi được chọn rời phạm vi, dù trả về bình thường hay ném ngoại lệ.

**Không có một cú pháp thống nhất cho tất cả hệ AOP.** Tên gọi *after*, *finally*, *after (finally)*, *after-returning* và *after-throwing* có thể được tài liệu hóa khác nhau tùy mô hình. Bài này dùng **after/finally** để chỉ loại advice muốn chạy ở **cả hai cách thoát**; khi triển khai phải kiểm tra hợp đồng thực tế của công cụ.

## 3. Hai cách hoàn tất cần phân biệt

Với một join point đại diện cho thực thi phương thức thông thường, có hai kiểu kết thúc chính mà ta cần quan sát:

1. **Hoàn tất bình thường:** phương thức chạy tới cuối hoặc thực hiện `return`; caller tiếp tục với kết quả (có thể là `void`).
2. **Hoàn tất bằng ngoại lệ:** phương thức hoặc một hoạt động bên trong ném ngoại lệ, và ngoại lệ đi ra khỏi ranh giới join point đang được quan sát.

Mô hình ý tưởng:

~~~text
                   Vào join point được chọn
                              |
                              v
                     Thực thi phần gốc
                              |
                 +------------+-------------+
                 |                          |
                 v                          v
           Return bình thường       Thoát bằng ngoại lệ
                 |                          |
                 +------------+-------------+
                              |
                              v
                     After/finally advice
                              |
                 +------------+-------------+
                 |                          |
                 v                          v
         Caller nhận kết quả        Ngoại lệ tiếp tục lan truyền
         theo hợp đồng gốc           theo hợp đồng gốc
~~~

Sơ đồ diễn tả **trường hợp lý tưởng khi advice không tự làm thay đổi kết quả**, và một hoạt động thực sự có cơ hội thoát khỏi phạm vi theo hai đường trên.

**Không phải mọi lần “có lỗi ở đâu đó” đều là hoàn tất bằng ngoại lệ của join point.** Nếu phương thức tự bắt ngoại lệ rồi trả về giá trị bình thường, join point bên ngoài đã **hoàn tất bình thường**. Nếu một tác vụ bất đồng bộ ném lỗi ở luồng khác sau khi phương thức lập lịch đã trả về, method join point ban đầu cũng không tự trở thành một lần thoát do ngoại lệ.

## 4. So sánh before, after-returning, after-throwing, after/finally và around

| Loại advice khái niệm | Khi nào chạy? | Điều cần nhớ |
|---|---|---|
| **Before** | Trước khi vào hoạt động được chọn, theo ranh giới được công cụ xác định | Không chứng minh phần gốc sau đó sẽ chạy thành công |
| **After-returning** | Khi hoạt động được quan sát hoàn tất bình thường | Thích hợp với kết quả thành công ở cấp ranh giới, không nhất thiết thành công nghiệp vụ |
| **After-throwing** | Khi hoạt động được quan sát thoát bằng ngoại lệ được cơ chế nhận diện | Chỉ phản ánh ngoại lệ **đi ra khỏi** phạm vi được chọn |
| **After/finally** | Khi hoạt động được quan sát rời phạm vi bình thường **hoặc** do ngoại lệ | Thích hợp để ghi dấu kết thúc, dọn dẹp hoặc phục hồi ngữ cảnh |
| **Around** | Bao quanh hoạt động được chọn, thường có khả năng điều khiển việc tiếp tục phần gốc | Có thể mô phỏng hành vi finally qua `try/finally`, nhưng không phải mọi around advice đều giữ nguyên luồng gốc |

After/finally **không phải** “after-returning cộng với after-throwing” theo nghĩa bắt buộc công cụ sẽ thực thi hai advice độc lập. Về mặt **điều kiện kích hoạt mong muốn**, after/finally bao phủ cả hai kiểu thoát. Cơ chế tổ chức và thứ tự có thể khác.

### 4.1. Ví dụ nhầm lẫn hay gặp

Một thao tác `pay()` trả về một đối tượng `PaymentResult.failed()` nhưng **không ném ngoại lệ**. Ở góc nhìn thực thi phương thức, đó là **normal return**. Một after-returning advice có thể chạy dù kết quả nghiệp vụ là “thất bại”.

Ngược lại, một thao tác có thể xử lý nghiệp vụ thành công nhưng advice khác ném ngoại lệ trong quá trình điều phối. Điều gì được quan sát là “thoát bằng ngoại lệ” phụ thuộc ranh giới kết hợp advice. Vì vậy cần phân biệt **trạng thái nghiệp vụ** với **cách phương thức kết thúc**.

## 5. Vì sao after/finally hữu ích với mối quan tâm xuyên suốt?

Trong một ứng dụng có hàng chục thao tác, cùng một chính sách có thể cần ghi nhận thời điểm kết thúc hoặc phục hồi trạng thái tại nhiều vị trí. Nếu mỗi phương thức tự viết các khối `try/finally`, chính sách sẽ phân tán và dễ thiếu nhất quán.

Một after/finally advice có thể tập trung hành vi:

- Ghi dấu `operation finished` ngay khi rời một ranh giới đã chọn.
- Cập nhật bộ đếm số lần **hoàn tất phạm vi**, bất kể bình thường hay ngoại lệ.
- Hoàn tất phép đo thời lượng từ một mốc bắt đầu tương ứng.
- Xóa hoặc phục hồi ngữ cảnh tạm thời gắn với đúng phạm vi lời gọi.
- Dọn dẹp tài nguyên **do chính lớp chính sách đã tạo và sở hữu**, theo hợp đồng rõ ràng.
- Ghi nhận sự kiện “đã rời thao tác” mà không giả định thành công.

Đây là các ví dụ phù hợp khi hành vi áp dụng ở nhiều join point và có thể diễn đạt thành chính sách độc lập với nghiệp vụ. Nếu thao tác dọn dẹp đòi hỏi hiểu sâu trạng thái nội bộ của một giao dịch cụ thể, việc giấu nó trong aspect có thể làm chương trình khó giải thích và kiểm chứng.

## 6. Tư duy try/finally trong Java để hiểu after/finally advice

Trong Java, khối `finally` được thực thi khi điều khiển rời một khối `try` theo cách thông thường, kể cả `return` hoặc ném ngoại lệ, **nếu quá trình thực thi thật sự đi qua cơ chế unwinding tương ứng**.

Ví dụ ngắn:

~~~java
static int calculate() {
    try {
        return 7;
    } finally {
        System.out.println("finish");
    }
}
~~~

Đoạn trên là **mã minh họa rời**, không phải tệp độc lập. Khi gọi `calculate()` bình thường, `finally` chạy **trước khi** caller nhận giá trị `7`.

Với ngoại lệ:

~~~java
static void fail() {
    try {
        throw new IllegalArgumentException("invalid");
    } finally {
        System.out.println("finish");
    }
}
~~~

Nếu caller gọi `fail()`, thông báo `finish` xuất hiện trong khi ngoại lệ vẫn tiếp tục lan truyền, miễn là khối finally hoàn tất bình thường.

Đây là **phép tương tự ngữ nghĩa**. After/finally advice không bắt buộc được công cụ triển khai bằng chính cú pháp `try/finally` trong source. Bộ máy AOP có thể weaving bytecode, xử lý tại call site, wrapper hoặc cơ chế khác. Nó phải tôn trọng các giới hạn của mô hình join point tương ứng.

### 6.1. “Bất kể thành công hay thất bại” có phạm vi

Khẳng định hợp lý là:

> Khi một join point **được chọn, được cơ chế quan sát và rời phạm vi theo con đường mà advice hỗ trợ**, after/finally advice nhằm chạy ở cả đường hoàn tất bình thường và đường ném ngoại lệ.

Không được hứa rằng advice chạy **sau mọi sự cố có thể xảy ra**. Chẳng hạn, tiến trình bị kết thúc cưỡng bức, JVM bị dừng ngay, hệ thống mất điện hoặc một vòng lặp không kết thúc có thể khiến không có sự kiện rời phạm vi để kích hoạt after/finally.

## 7. Ví dụ Java 17 hoàn chỉnh: kết quả bình thường và ngoại lệ

Ví dụ sau dùng Java thuần, không phụ thuộc thư viện ngoài. Một phương thức `invokeObserved` đóng vai trò wrapper mô phỏng **before advice**, **after-returning**, **after-throwing** và **after/finally** cho lời gọi đồng bộ.

**Đây là chương trình mô phỏng khái niệm**, không phải một implementation AOP tự weaving. Trong AOP thực sự, pointcut sẽ chọn join point và cơ chế weaving gắn advice tương ứng.

Lưu tệp `FinallyAdviceDemo.java`:

~~~java
import java.util.concurrent.Callable;

public class FinallyAdviceDemo {
    static <T> T invokeObserved(String operation, Callable<T> work)
            throws Exception {
        System.out.println("[before] " + operation);
        try {
            T result = work.call();
            System.out.println("[after-returning] " + operation);
            return result;
        } catch (Exception error) {
            System.out.println("[after-throwing] " + operation
                    + ": " + error.getMessage());
            throw error;
        } finally {
            System.out.println("[after-finally] " + operation);
        }
    }

    public static void main(String[] args) throws Exception {
        int value = invokeObserved("success", () -> {
            System.out.println("[business] success");
            return 42;
        });
        System.out.println("[caller] value=" + value);

        try {
            invokeObserved("failure", () -> {
                System.out.println("[business] failure");
                throw new IllegalStateException("boom");
            });
        } catch (IllegalStateException error) {
            System.out.println("[caller] caught=" + error.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với Java 17 hoặc mới hơn:

~~~bash
javac FinallyAdviceDemo.java
java FinallyAdviceDemo
~~~

Stdout chính xác:

~~~text
[before] success
[business] success
[after-returning] success
[after-finally] success
[caller] value=42
[before] failure
[business] failure
[after-throwing] failure: boom
[after-finally] failure
[caller] caught=boom
~~~

### 7.1. Đọc từng dòng của lần thành công

1. Wrapper in `[before] success`.
2. Lambda nghiệp vụ chạy và in `[business] success`.
3. `work.call()` trả `42`, nên nhánh `after-returning` chạy.
4. Trước khi hàm wrapper thực sự trả `42`, `finally` chạy và in `[after-finally] success`.
5. Caller mới có thể in `[caller] value=42`.

Điều đó cho thấy **after/finally advice đi trước bước caller nhận kết quả** theo wrapper này, dù lệnh `return result` nằm trong `try`.

### 7.2. Đọc lần thất bại

1. Lambda in `[business] failure`, rồi ném `IllegalStateException("boom")`.
2. Wrapper bắt ngoại lệ trong `catch (Exception error)`, in nhánh `after-throwing` và ném lại **chính ngoại lệ đó**.
3. `finally` vẫn chạy và in `[after-finally] failure`.
4. Caller bắt ngoại lệ và in `[caller] caught=boom`.

Điều này minh họa rằng **after/finally chạy ở cả hai nhánh**. Nó không nuốt ngoại lệ gốc; `throw error` bảo toàn đối tượng ngoại lệ trong tình huống này.

### 7.3. Những giới hạn của chương trình minh họa

- `Callable<T>` cho phép lambda ném `Exception`. Khối `catch (Exception)` ở ví dụ **không bắt các loại `Error`**, nhưng `finally` vẫn có thể chạy khi `Error` gây unwinding bình thường.
- Phần `after-returning` là mã `println` đặt trong `try`; nếu chính thao tác ghi nhận này ném lỗi, nhánh `catch` của wrapper cũng có thể bắt nó. Vì vậy đây là mô phỏng dễ hiểu **trên đường chạy bình thường**, không cam kết cùng cơ chế phân loại ngoại lệ của mọi hệ AOP khi nhiều advice được kết hợp.
- Không có pointcut được áp dụng tự động; chỉ lời gọi đi qua `invokeObserved` mới có hành vi bổ sung.
- Một advice thực có thể được cấu hình theo thứ tự khác, chạy quanh phạm vi khác hoặc có ràng buộc khác về ngoại lệ và giá trị trả về. Luôn dựa vào hợp đồng của cơ chế AOP đang dùng.

## 8. Gắn advice vào join point nào thì “kết thúc” có nghĩa gì?

Không nên hiểu “kết thúc” như một sự kiện chung của cả hệ thống. Cần chọn chính xác loại join point.

| Loại điểm theo mô hình hỗ trợ | “Kết thúc” được hiểu theo ranh giới nào? |
|---|---|
| **Method execution** | Phần thực thi phương thức được quan sát kết thúc bình thường hoặc ném ngoại lệ |
| **Method call** | Hoạt động gọi tại call site được quan sát rời phạm vi theo ngữ nghĩa công cụ |
| **Constructor execution** | Phạm vi thực thi constructor tương ứng kết thúc; không tự đồng nghĩa toàn bộ vòng đời đối tượng đã thành công |
| **Field get/set** | Hoạt động truy cập trường kết thúc nếu mô hình cho phép can thiệp loại điểm đó |
| **Sự kiện ở ranh giới khác** | Phụ thuộc sự kiện và cách công cụ định nghĩa lifecycle |

Một mô hình AOP chỉ hỗ trợ method invocation qua proxy **không đương nhiên can thiệp vào constructor, field access hay mọi lời gọi nội bộ**. Sau/finally advice không thể chạy tại một loại điểm mà công cụ hoàn toàn không nhận diện.

### 8.1. Method call và execution khác nhau

Một method có thể được gọi từ nhiều vị trí. Advice tại call site và advice tại method execution có thể bao những vùng khác nhau; nếu cả hai cùng tồn tại, việc ghép các lời gọi lồng nhau có thể tạo ra nhiều lần ghi nhận.

Thời điểm vào/ra của một join point không nên được suy từ tên phương thức mà không xác định **loại điểm** và **phạm vi weaving**.

## 9. After/finally không bảo đảm “thành công”

Một thao tác có thể trả về bình thường nhưng trạng thái nghiệp vụ là thất bại:

~~~java
record PaymentResult(boolean accepted, String reason) {}

PaymentResult pay() {
    return new PaymentResult(false, "insufficient balance");
}
~~~

Đây là mảnh Java minh họa, không phải chương trình độc lập. Method `pay()` trong ví dụ **trả về bình thường** một kết quả `accepted=false`. After-returning advice gắn với method execution có thể được kích hoạt; after/finally cũng có thể chạy.

Nếu muốn ghi hai số liệu **số lời gọi đã kết thúc** và **số thanh toán được chấp nhận**, cần hai tiêu chí khác nhau:

- Số **lời gọi đã kết thúc**: đếm khi rời đúng phạm vi.
- Số **thanh toán thành công theo nghiệp vụ**: đọc hợp đồng `PaymentResult.accepted()` tại nơi có thể xác định kết quả, nếu cơ chế cho phép và việc quan sát phù hợp.

Một ngoại lệ cũng có thể được bắt và xử lý **bên trong** method. Nếu cuối cùng method trả về bình thường, after-throwing ở ranh giới method bên ngoài không tự chạy cho ngoại lệ nội bộ đã được xử lý.

**Rút ra:** “Sau khi hoàn tất” là ngữ nghĩa **luồng điều khiển**; “thành công” có thể là ngữ nghĩa **nghiệp vụ**. Hai khái niệm cần tài liệu và kiểm thử riêng.

## 10. Câu hỏi quan trọng: after/finally có thấy ngoại lệ bị bắt bên trong không?

Xét:

~~~java
int load() {
    try {
        return parseValue();
    } catch (IllegalArgumentException error) {
        return -1;
    }
}
~~~

Đây là đoạn mã minh họa. Nếu `parseValue()` ném `IllegalArgumentException`, method `load()` có thể trả `-1\) bình thường. Một after/finally advice đặt ở **method execution của `load()`** vẫn chạy vì method hoàn tất; nhưng việc đó **không chứng minh có một ngoại lệ thoát qua join point `load()`**.

Một after-throwing advice ở chính ranh giới `load()` thường không có ngoại lệ để quan sát trong trường hợp này, vì ngoại lệ đã được xử lý bên trong.

Ngược lại, nếu advice được gắn vào join point tương ứng với `parseValue()` và ngoại lệ thoát ra từ chính method đó, advice tại ranh giới `parseValue()` có thể nhìn thấy đường thất bại.

Do đó cần luôn nói rõ: **“ngoại lệ thoát khỏi điểm nào?”**. Không thể dựa vào một dòng log after/finally để kết luận nơi phát sinh lỗi hoặc trạng thái cuối của toàn yêu cầu.

## 11. Advice chạy cuối có thể vô tình che giấu ngoại lệ gốc

Trong Java, nếu một khối `finally` tự ném ngoại lệ, nó có thể thay thế kết quả đang chờ trả về hoặc ngoại lệ đang lan truyền.

Ví dụ rời:

~~~java
static int example() {
    try {
        return 5;
    } finally {
        throw new IllegalStateException("logging failed");
    }
}
~~~

Method này **không trả về `5` bình thường**; ngoại lệ trong finally thay thế việc return. Đây là lý do một after/finally advice phục vụ quan sát phải đặc biệt thận trọng.

Cũng có trường hợp:

~~~java
static void exampleFailure() {
    try {
        throw new IllegalArgumentException("business failed");
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
~~~

Ngoại lệ `cleanup failed` thay thế đường ném ngoại lệ `business failed` trong đoạn này. Không được coi hai ngoại lệ tự động được giữ song song khi tự viết kiểu `finally` trên.

### 11.1. Nguyên tắc khi viết advice quan sát

Với advice chỉ nhằm ghi log hoặc thống kê, mục tiêu thường là **không làm thay đổi hành vi nghiệp vụ**. Cần thiết kế để lỗi của logger/telemetry không tùy tiện che nguyên nhân gốc. Cách chọn chính sách lỗi tùy mức độ bắt buộc của quan sát: ghi nhận best-effort, chuyển lỗi sang kênh khác hoặc để hoạt động thất bại có chủ đích.

Nếu việc dọn dẹp là **bắt buộc để bảo toàn an toàn/tính đúng đắn**, không nên tự động nuốt mọi ngoại lệ của cleanup. Khi nhiều lỗi xảy ra, cơ chế báo lỗi phải được định nghĩa rõ và có kiểm thử.

### 11.2. Vì sao tránh return trong finally?

~~~java
static int badExample() {
    try {
        throw new IllegalStateException("root problem");
    } finally {
        return 10;
    }
}
~~~

Đoạn này là mã minh họa có chủ đích về **anti-pattern**. Trong Java, return của finally sẽ che đường ném ngoại lệ đang chờ và khiến caller nhận `10`. Một advice mô phỏng after/finally không nên vô tình làm điều tương tự bằng cách thay kết quả hay bỏ qua hành vi gốc.

## 12. After/finally so với try-with-resources

Java có **try-with-resources**, cơ chế quản lý tài nguyên thực thi `AutoCloseable.close()` ngay khi thoát phạm vi. Khi cả xử lý chính lẫn `close()` đều ném lỗi, Java có cơ chế **suppressed exceptions** để thường giữ ngoại lệ chính, đồng thời lưu lỗi đóng tài nguyên như ngoại lệ phụ.

Ví dụ:

~~~java
try (var stream = openStream()) {
    consume(stream);
}
~~~

Đây là mã khái niệm không độc lập; `openStream` và `consume` chưa được định nghĩa. Nó minh họa **quyền sở hữu tài nguyên**: mã mở stream có thể quản lý vòng đời tại đúng vị trí bằng try-with-resources.

After/finally advice có thể hữu ích khi aspect sở hữu một **ngữ cảnh theo lời gọi** cần thu dọn trên nhiều phương thức. Nhưng nó không nên thay thế tùy tiện cho việc quản lý tài nguyên nghiệp vụ có chủ đích ở lớp sở hữu tài nguyên.

Ví dụ, kết nối hoặc stream được mở bên trong một nhánh nghiệp vụ và phải đóng theo hợp đồng riêng thường nên được quản lý tại ranh giới sở hữu đó. Một aspect chỉ biết rằng phương thức “đã kết thúc” có thể **không biết** tài nguyên nào còn hợp lệ hoặc cần bàn giao cho caller.

## 13. Dọn dẹp ngữ cảnh theo luồng: dùng finally đúng cách

Một trường hợp phù hợp với mô hình before + after/finally là **đặt tạm một ngữ cảnh** (ví dụ mã tương quan phục vụ trace) khi vào hoạt động và **phục hồi ngữ cảnh trước đó** khi rời hoạt động.

Khó khăn nảy sinh khi lời gọi **lồng nhau**: lớp bên trong không nên đơn giản xóa sạch ngữ cảnh của lớp ngoài. Cần ghi nhớ trạng thái trước khi vào và phục hồi đúng sau khi thoát.

### 13.1. Chương trình Java 17 có thể chạy độc lập

Lưu tệp `ContextCleanupDemo.java`:

~~~java
import java.util.concurrent.Callable;

public class ContextCleanupDemo {
    private static final ThreadLocal<String> CONTEXT = new ThreadLocal<>();

    static <T> T withContext(String value, Callable<T> operation)
            throws Exception {
        String previous = CONTEXT.get();
        CONTEXT.set(value);

        try {
            return operation.call();
        } finally {
            if (previous == null) {
                CONTEXT.remove();
            } else {
                CONTEXT.set(previous);
            }
        }
    }

    static String context() {
        return String.valueOf(CONTEXT.get());
    }

    public static void main(String[] args) throws Exception {
        System.out.println("before=" + context());

        withContext("outer", () -> {
            System.out.println("outer-enter=" + context());

            withContext("inner", () -> {
                System.out.println("inner=" + context());
                return null;
            });

            System.out.println("outer-restored=" + context());
            return null;
        });

        System.out.println("after-outer=" + context());

        try {
            withContext("failure", () -> {
                System.out.println("failing=" + context());
                throw new IllegalStateException("boom");
            });
        } catch (IllegalStateException error) {
            System.out.println("caught=" + error.getMessage());
        }

        System.out.println("after-error=" + context());
    }
}
~~~

Chạy:

~~~bash
javac ContextCleanupDemo.java
java ContextCleanupDemo
~~~

Stdout chính xác:

~~~text
before=null
outer-enter=outer
inner=inner
outer-restored=outer
after-outer=null
failing=failure
caught=boom
after-error=null
~~~

### 13.2. Bài học của ví dụ

- Trước khi vào phạm vi, `ThreadLocal` chưa có giá trị trên luồng hiện tại, nên `String.valueOf(null)` cho chuỗi `"null"`.
- Phạm vi `inner` giữ lại `previous="outer"`, rồi sau đó **phục hồi outer** thay vì xóa.
- Khi phạm vi `outer` kết thúc, giá trị trước đó là null nên `remove()` tránh giữ giá trị không còn cần trên thread.
- Lần gọi `failure` ném `IllegalStateException`; `finally` vẫn phục hồi giá trị trước, nên caller thấy `after-error=null`.

Đây là **wrapper Java thuần** minh họa hành vi dọn dẹp tương tự after/finally. Nó không tự weaving và chỉ chạy khi caller gọi `withContext`.

### 13.3. Cảnh báo với bất đồng bộ

`ThreadLocal` gắn với **luồng hiện tại**. Khi một hoạt động tạo tác vụ để chạy trên thread khác, việc kết thúc của lời gọi tạo tác vụ và kết thúc thực sự của công việc **không đồng nghĩa**. Không được mặc định ngữ cảnh trong ví dụ được truyền sang thread khác, đặc biệt khi dùng thread pool hoặc các mô hình đồng thời khác.

Nếu ngữ cảnh cần đi qua tác vụ bất đồng bộ, phải có cơ chế **truyền/ngắt kết nối và dọn dẹp** phù hợp tại chính ranh giới chạy tác vụ; after/finally ở phương thức lập lịch ban đầu không tự quản lý vòng đời công việc ở thread khác.

## 14. Before và after/finally phải ghép đúng phạm vi

Khi trước hoạt động tạo trạng thái tạm, sau hoạt động phải thu dọn **đúng trạng thái tương ứng**.

Một lỗi phổ biến:

~~~text
before: tăng depth của context
after-finally: gán depth = 0
~~~

Nếu các join point lồng nhau, việc xóa về 0 ở nhánh bên trong có thể phá trạng thái của nhánh bên ngoài. Cần cấu trúc dạng **stack**, bộ đếm cân bằng hoặc cơ chế lưu-phục hồi.

Tương tự, nếu after/finally đọc thời điểm bắt đầu để tính duration, phải bảo đảm mỗi **lần thực thi** có bản ghi bắt đầu riêng. Không dùng một biến toàn cục đơn giản cho tất cả yêu cầu đồng thời.

### 14.1. “Một lần trước, một lần sau” không tự được bảo đảm bởi nhiều aspect

Nếu pointcut before và pointcut after không giống nhau, hoặc một advice khác khiến phần gốc không được gọi, có thể xuất hiện tình trạng mất cân đối. Một ranh giới **around** dùng `try/finally` bao đúng phần thực thi được tiếp tục đôi khi dễ diễn đạt cặp vào/ra hơn, nhưng vẫn cần tuân thủ semantics của cơ chế AOP.

Khi có nhiều advice, điểm vào/ra và thứ tự thực tế phải được kiểm chứng. Không dùng tên advice làm bằng chứng mọi nhánh hoạt động đã được bao phủ.

## 15. Thứ tự nhiều advice: after/finally nào chạy trước?

Giả sử hai aspect cùng áp dụng cho một join point:

- Một aspect đo thời lượng.
- Một aspect đặt ngữ cảnh trace và thu dọn ngữ cảnh khi kết thúc.

Nếu aspect đo thời lượng nằm **bên ngoài** aspect ngữ cảnh, phép đo có thể bao gồm chi phí thiết lập/thu dọn trace. Nếu nằm bên trong, phép đo có thể không bao gồm những bước đó.

Mô hình lồng nhau:

~~~text
outer.before
    inner.before
        business
    inner.after-finally
outer.after-finally
~~~

Đây là thứ tự trong trường hợp **các lớp bao được lồng theo sơ đồ**. Công cụ AOP có thể có quy tắc ưu tiên hoặc cấu hình sắp xếp riêng; không tự suy ra thứ tự chỉ từ tên class hoặc thời điểm khai báo.

### 15.1. Ngoại lệ từ advice phía trong

Nếu advice phía trong ném lỗi khi thu dọn, advice phía ngoài có thể nhìn thấy một đường thoát khác với ngoại lệ gốc, tùy semantics kết hợp. Điều này quan trọng khi thiết kế bộ đo, logger và chính sách xử lý lỗi.

Hãy kiểm thử **cả tình huống phần gốc ném lỗi** và **tình huống một advice tự phát sinh lỗi**, thay vì chỉ kiểm tra output của nhánh thành công.

## 16. Không phải mọi thất bại đều kích hoạt after/finally

Cụm “bất kể thành công hay thất bại” có điều kiện tiên quyết: **join point cần quan sát phải đã được kích hoạt và có một đường rời phạm vi mà công cụ xử lý**.

Những tình huống cần phân biệt:

1. **Pointcut không chọn điểm:** lời gọi không khớp tên, chữ ký hoặc điều kiện động → after/finally của pointcut này không chạy.
2. **Điểm ngoài mô hình join point:** công cụ không hỗ trợ loại điểm (ví dụ field access khi chỉ có method proxy) → không có điểm để gắn advice.
3. **Không đi qua weaving/runtime path:** caller gọi thẳng đối tượng đích thay vì proxy cần thiết → cơ chế proxy không quan sát.
4. **Điểm chưa thật sự xảy ra:** nhánh mã không được thực thi → không có lần gọi tương ứng.
5. **Lỗi xảy ra trước điểm được chọn:** ví dụ đánh giá đối số ném lỗi trước khi constructor execution bắt đầu → after/finally ở constructor execution không có hoạt động đã bắt đầu để xử lý.
6. **Hoạt động chưa kết thúc:** method chờ vô hạn hoặc một vòng lặp không rời phạm vi → chưa có sự kiện “after”.
7. **Tiến trình dừng bất thường:** runtime bị kết thúc cưỡng bức, mất điện hoặc cơ chế kết thúc không unwind thông thường → không có bảo đảm chạy cleanup.
8. **Một around advice bao ngoài bỏ qua phần gốc:** điểm thực thi phần gốc có thể không phát sinh; việc một advice after có chạy hay không phụ thuộc chính xác phạm vi và cách các advice được tổ chức.

Không được biến after/finally thành một cơ chế **bảo đảm giao sự kiện bền vững** cho mọi tình huống. Với yêu cầu kiểm toán không được mất bản ghi trong cả sự cố tiến trình, cần cơ chế lưu trữ/đồng bộ giao dịch hoặc thiết kế bền vững tương ứng.

## 17. Advice kết thúc và tác vụ bất đồng bộ: kết thúc của cái gì?

Giả sử:

~~~java
Future<?> future = executor.submit(() -> performLongJob());
~~~

Đây là mảnh Java minh họa, chưa phải chương trình độc lập. Nếu after/finally advice được gắn vào **method lập lịch hoặc submit**, nó có thể chạy khi method trả về `Future`, trong khi công việc thực sự vẫn chưa hoàn tất.

Các mốc thời gian khác nhau:

~~~text
T0: vào submit(...)
T1: submit(...) trả Future      ← method execution kết thúc
T2: tác vụ bắt đầu trên worker
T3: tác vụ hoàn tất / thất bại  ← vòng đời công việc kết thúc
~~~

After/finally tại join point của `submit` phản ánh ranh giới **T1**. Muốn quan sát **T3**, cần một join point hoặc cơ chế callback/hoàn tất phù hợp với vòng đời tác vụ.

Một phương thức có thể trả `CompletionStage` hoặc đối tượng đại diện hoạt động bất đồng bộ. Trả đối tượng đại diện bình thường không đồng nghĩa tác vụ sẽ hoàn tất thành công. Advice gắn vào method return không tự biết kết quả cuối của tác vụ, trừ khi cơ chế có thêm hợp đồng theo dõi trạng thái ấy.

## 18. Advice kết thúc và resource cleanup: ai sở hữu tài nguyên?

Thao tác dọn dẹp nên đi cùng **quyền sở hữu**. Một aspect có thể tạo một timer hoặc context scope ở before/around và thu dọn nó ở after/finally. Nhưng nếu tài nguyên do nghiệp vụ mở rồi trả tham chiếu cho caller sử dụng tiếp, một advice “thấy method kết thúc” không nên tùy tiện đóng tài nguyên đó.

Ví dụ, method `openStream()` trả về một `InputStream` cần được caller đọc sau khi lời gọi kết thúc. Nếu after/finally đóng stream ngay khi method trả, caller nhận một tài nguyên không sử dụng được.

Do đó, không nên đánh đồng:

- **Kết thúc một lời gọi method.**
- **Kết thúc quyền sở hữu tài nguyên.**
- **Kết thúc toàn bộ giao dịch hay yêu cầu.**

After/finally được đặt đúng khi phạm vi của việc dọn dẹp **thực sự kết thúc cùng join point**. Nếu vòng đời dài hơn, cần ranh giới khác.

## 19. Điều kiện động trong pointcut có thể làm số lần finally khác dự đoán

Một pointcut có thể chọn `processOrder` chỉ khi đối số `priority=true`. Những lời gọi `processOrder(false)` vẫn có thể thực thi nghiệp vụ, nhưng không khớp pointcut và **không có after/finally advice của pointcut đó**.

Pseudocode mô hình:

~~~text
pointcut observed:
    execution(processOrder(boolean priority))
    AND priority = true

after-finally observed:
    record("selected invocation finished")
~~~

Đây **không phải cú pháp của một công cụ AOP cụ thể**. Ý nghĩa: after/finally diễn ra khi **join point được chọn** rời phạm vi. Không thể lấy số dòng record để suy ra tổng mọi lời gọi `processOrder` nếu pointcut chỉ bao phủ một tập con.

Ngoài điều kiện động, phạm vi weaving cũng có thể giới hạn việc quan sát. Số lần advice xuất hiện phải được diễn giải theo **tập join point thực sự được chọn và đi qua cơ chế can thiệp**.

## 20. Thiết kế bộ đo thời lượng với after/finally

Một ví dụ hữu ích là đo thời gian đồng bộ:

~~~text
before:
    t0 = monotonicTime()

after-finally:
    elapsed = monotonicTime() - t0
    recordElapsed(elapsed)
~~~

Pseudocode trên là mô hình khái niệm. Trong Java, một nguồn thời gian đo khoảng là `System.nanoTime()`; giá trị của nó có ý nghĩa đo **chênh lệch** chứ không đại diện mốc thời gian lịch.

Các điểm cần kiểm tra:

- Mỗi lần join point được chọn có **t0 riêng**, kể cả lời gọi lồng nhau và đồng thời.
- `t0` phải được tạo ở ranh giới phù hợp và sẵn có khi after/finally chạy.
- Thời lượng phản ánh **phần nào được bao bởi advice**, không tự động toàn bộ vòng đời nghiệp vụ.
- Kết thúc bằng ngoại lệ vẫn có thời lượng; muốn phân loại thành công/thất bại cần thông tin bổ sung.
- Nếu logger/metrics bị lỗi, không được vô ý che giấu ngoại lệ nghiệp vụ.
- Chi phí của chính hệ thống đo cần được đánh giá ở các join point tần suất cao.

Không nên in một giá trị thời lượng cụ thể như thể đó là stdout xác định: số đo phụ thuộc máy và môi trường thực thi.

## 21. Các lỗi phổ biến khi thiết kế after/finally advice

### 21.1. Ghi nhãn “SUCCESS” khi chỉ biết đã thoát

Sai: after/finally luôn ghi `SUCCESS`. Điều đó làm nhánh ngoại lệ cũng bị báo thành công.

Sửa: ghi `FINISHED` nếu chỉ biết đã rời phạm vi; ghi thành công/thất bại dựa trên **đúng thông tin kết quả/ngoại lệ** được cho phép.

### 21.2. Giữ `ThreadLocal` sau khi lời gọi kết thúc

Nếu before đặt context mà after/finally không xóa/phục hồi, thread pool có thể tái sử dụng luồng chứa context cũ. Sửa bằng cấu trúc lưu-phục hồi theo phạm vi và kiểm thử cả nhánh lỗi lẫn nhánh lồng nhau.

### 21.3. Thao tác trong finally làm mất ngoại lệ gốc

Ghi log, serialize dữ liệu hoặc đóng tài nguyên có thể tự lỗi. Cần hợp đồng xử lý lỗi riêng, tránh thay thế nguyên nhân chính một cách không mong muốn.

### 21.4. Cho rằng after/finally luôn được chạy một lần

Một vòng lặp vô hạn không thoát; một around advice có thể bỏ qua phần gốc; pointcut có thể không khớp; một cơ chế có thể quan sát điểm ở nhiều lớp bao khác nhau. Phải đo số lần theo **đúng join point, đúng runtime path**.

### 21.5. Nhầm return của method với hoàn tất công việc bất đồng bộ

Nếu method trả handle của tác vụ đang chạy, after/finally của method chỉ quan sát method. Muốn đo công việc phải xác định ranh giới hoàn tất tác vụ.

### 21.6. Dọn dẹp tài nguyên không thuộc quyền sở hữu

Một aspect tự động đóng đối tượng trả về hoặc tài nguyên do caller còn sử dụng có thể phá hợp đồng API. Dọn dẹp phải gắn với chủ thể sở hữu tài nguyên.

### 21.7. Bỏ qua thứ tự nhiều advice

Một aspect thay đổi ngữ cảnh và một aspect đọc ngữ cảnh có thể tương tác khác nhau tùy thứ tự vào/ra. Cần quy định ranh giới, thứ tự và kiểm thử hành vi cùng hoạt động.

## 22. Quy trình thiết kế và xác minh một after/finally advice

1. **Nêu chính xác mục tiêu:** ghi “đã rời phạm vi”, dọn ngữ cảnh, đo thời lượng hay thực hiện chính sách nào?
2. **Chọn loại join point:** method execution, method call hoặc loại khác có được công cụ hỗ trợ?
3. **Định nghĩa pointcut:** điểm nào được bao gồm, loại trừ, điều kiện động nào có thể khiến advice không chạy?
4. **Xác định ranh giới hoàn tất:** return bình thường, ngoại lệ đi ra khỏi join point, hay lifecycle dài hơn như tác vụ bất đồng bộ?
5. **Xác định quyền sở hữu dữ liệu/tài nguyên:** after/finally chỉ thu dọn trạng thái thuộc đúng phạm vi.
6. **Thiết kế chính sách lỗi của advice:** nếu cleanup/logging tự lỗi thì làm gì, có bảo toàn nguyên nhân gốc không?
7. **Xét lồng nhau, đồng thời và thứ tự aspect:** có cần lưu-phục hồi ngữ cảnh, dữ liệu theo từng lần gọi hay cấu hình ưu tiên?
8. **Kiểm thử nhánh return:** advice chạy đúng số lần, caller nhận nguyên kết quả.
9. **Kiểm thử nhánh throw:** advice chạy đúng số lần, ngoại lệ gốc và loại lỗi không bị mất khi không có chủ đích.
10. **Kiểm thử không khớp và đường ngoài weaving:** không gán nhầm việc không có advice thành lời gọi thành công.
11. **Kiểm thử vòng đời bất đồng bộ nếu có:** kết thúc method và kết thúc tác vụ có được phân biệt?
12. **Quan sát trên môi trường thực:** ghi rõ công cụ AOP, loại join point được hỗ trợ và phạm vi weaving; không suy từ một ví dụ wrapper Java thuần sang mọi công cụ.

Một chính sách after/finally tốt phải **đúng về phạm vi, đúng về thời điểm và an toàn với lỗi**, không chỉ tạo đủ hai dòng log trong một ví dụ đơn giản.

## 23. Bài tập tự kiểm tra

### Bài 1. Trả về bình thường

Một method `getTotal()` trả số `0` bình thường. Pointcut chọn method đó. After/finally advice có chạy không?

**Đáp án:** theo semantics after/finally thông thường, có, khi join point được quan sát kết thúc bình thường. Giá trị `0` không tự biến lời gọi thành thất bại.

### Bài 2. Ngoại lệ thoát khỏi method

Một method ném `IllegalArgumentException` ra caller. After-returning, after-throwing và after/finally có vai trò gì?

**Đáp án:** after-returning gắn vào ranh giới method **không được kích hoạt cho đường throw**; after-throwing phù hợp với đường ngoại lệ; after/finally nhằm chạy khi rời phạm vi ở đường này. Cơ chế cụ thể quyết định thứ tự và điều kiện chi tiết.

### Bài 3. Ngoại lệ được xử lý nội bộ

Method `load()` bắt một ngoại lệ rồi trả `-1`. Một after-throwing gắn vào `load()` có được kích hoạt vì “từng có lỗi bên trong” không?

**Đáp án:** không chỉ vì lý do đó. Ở ranh giới `load()`, method trả về bình thường. After/finally vẫn chạy khi method rời phạm vi.

### Bài 4. Vòng lặp không kết thúc

Một method được chọn bị kẹt trong vòng lặp vô hạn. After/finally đã chắc chắn chạy chưa?

**Đáp án:** chưa. Không có lần rời phạm vi bình thường/ngoại lệ để kích hoạt hành vi “after”.

### Bài 5. Ngoại lệ từ advice

Một thao tác nghiệp vụ ném `IllegalStateException("business")`, sau đó lời gọi ghi log trong `finally` cũng ném `IllegalArgumentException("log")`. Caller có chắc nhận lỗi nghiệp vụ ban đầu không?

**Đáp án:** không. Nếu viết Java `finally` trực tiếp mà ném ngoại lệ mới, lỗi đó có thể thay thế ngoại lệ đang lan truyền. Cần chính sách lỗi/cleanup rõ và kiểm thử.

### Bài 6. Tác vụ bất đồng bộ

Một method `enqueue()` trả về nhanh, còn worker xử lý sau vài phút. After/finally tại method `enqueue` biểu thị điều gì?

**Đáp án:** nó biểu thị lời thực thi `enqueue` rời phạm vi; không tự chứng minh worker đã hoàn tất hay thành công.

### Bài 7. Ngữ cảnh lồng nhau

Một outer advice đặt context “outer”; inner advice đặt “inner”. Inner kết thúc. Nên khôi phục giá trị nào?

**Đáp án:** giá trị **“outer”** trước đó, không xóa toàn bộ, nếu hợp đồng yêu cầu context lồng nhau.

### Bài 8. Pointcut không khớp

Một method `saveDraft()` không thuộc pointcut chọn `submit*`. After/finally advice của pointcut đó có phải chạy vì method đã kết thúc không?

**Đáp án:** không. Chỉ những join point **được chọn và được cơ chế can thiệp quan sát** mới thuộc phạm vi advice này.

## 24. Ghi nhớ

- **After/finally advice** diễn tả hành vi khi rời một join point đã được chọn, ở cả **normal return** và **exceptional exit** theo semantics của công cụ.
- **After-returning**, **after-throwing** và **after/finally** là những ý nghĩa khác nhau; không dùng từ “after” mà bỏ qua khác biệt.
- “Kết thúc” chỉ nói về **ranh giới được quan sát**, không tự nói “thành công nghiệp vụ”, “toàn bộ yêu cầu hoàn tất” hay “tác vụ bất đồng bộ hoàn tất”.
- Sau khi chạy advice, **giá trị trả về và ngoại lệ gốc** nên được bảo toàn theo hợp đồng; mã trong finally tự ném lỗi có thể làm thay đổi điều đó.
- Khi dọn dẹp, phải đúng **quyền sở hữu tài nguyên**, đúng **phạm vi ngữ cảnh** và an toàn với **lời gọi lồng nhau/đồng thời**.
- **Pointcut** quyết định những điểm có advice; **weaving** và runtime path quyết định những điểm thực sự được quan sát. Một hoạt động ngoài mô hình join point sẽ không được cứu bằng một after/finally advice rộng.
- Các tình huống không thoát thông thường, chấm dứt tiến trình và tác vụ đang chạy lâu hơn method không có bảo đảm “advice cuối sẽ chạy”.

Hãy luôn đặt hai câu hỏi khi thiết kế: **“Chính xác hoạt động nào đã kết thúc?”** và **“Nếu chính advice này thất bại thì kết quả/ngoại lệ của hoạt động gốc còn được giữ đúng hay không?”**. Đó là ranh giới giữa một after/finally advice dễ kiểm chứng và một hành vi kỹ thuật có thể vô tình làm thay đổi chương trình.
