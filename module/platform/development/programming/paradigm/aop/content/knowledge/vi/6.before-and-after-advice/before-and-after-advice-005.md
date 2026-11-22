# Phân biệt hành vi sau hoàn tất với hành vi luôn dọn dẹp trong AOP

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, **AOP**), một **advice** có thể chạy trước, sau hoặc bao quanh một điểm can thiệp (*join point*). Ở phía “sau”, có ba tình huống rất dễ bị nhầm:

1. Thao tác chính **trả về bình thường**: có kết quả thành công (có thể là `null` hoặc phương thức `void`).
2. Thao tác chính **kết thúc bằng ngoại lệ**: không có giá trị trả về thành công của lần gọi đó.
3. Dù theo nhánh nào, một số công việc **phải được dọn dẹp khi rời khỏi phạm vi**: giải phóng tài nguyên đã sở hữu, kết thúc bối cảnh đo đạc hoặc khôi phục trạng thái tạm thời.

Các mô hình AOP thường diễn tả tương ứng bằng **after-returning**, **after-throwing** và **after/finally**. Trong bài này, “hành vi sau hoàn tất thành công” được dùng để nói đến **after-returning**, còn “luôn dọn dẹp” là hành vi kiểu **finally** sau khi phạm vi điều khiển đã được thiết lập. Tên `after completion` trong một số thư viện có thể chỉ nhánh *cả thành công lẫn lỗi*, vì thế phải xem **ngữ nghĩa thực tế**, không chỉ dựa vào tên gọi.

Một khía cạnh quan sát có thể muốn ghi thời gian xử lý ở cả hai nhánh, nhưng chỉ thông báo “thành công” khi phương thức thực sự trả về bình thường. Nhầm hai ý này dẫn đến log sai, rò rỉ tài nguyên hoặc vô tình che khuất ngoại lệ nghiệp vụ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt chính xác **before**, **after-returning**, **after-throwing**, **after/finally** và **around** trong ngữ cảnh kết thúc một lời gọi.
- Giải thích vì sao “sau khi phương thức kết thúc” không tự đồng nghĩa “sau khi phương thức thành công”.
- Chọn advice phù hợp cho ghi nhận kết quả, kiểm toán, đo thời lượng, xử lý ngoại lệ và dọn tài nguyên.
- Mô tả thứ tự chạy khi có nhiều advice lồng nhau, cả đường trả về và đường ném lỗi.
- Chỉ ra được khi nào `finally` có hiệu lực và các trường hợp nó không thể bảo đảm việc dọn dẹp thực tế.
- Giữ nguyên **kết quả trả về, ngoại lệ gốc và số lần thực thi** đối với advice chỉ nhằm quan sát.
- Phân biệt việc một phương thức **trả về đối tượng tác vụ bất đồng bộ** với lúc công việc bất đồng bộ thực sự hoàn thành.
- Viết và đọc một ví dụ Java 17 chạy được, đối chiếu chính xác đầu ra thành công, thất bại và đường gọi bỏ qua proxy.

## 2. Mô hình tư duy: một điểm vào, nhiều đường kết thúc

Giả sử có chức năng `reserveTicket(id)`:

```text
Người gọi
   |
   v
[Before advice: ghi bắt đầu]
   |
   v
[Thao tác giữ vé]
   |
   +---- Trả về bình thường ----> [After-returning: ghi thành công]
   |                                      |
   +---- Ném ngoại lệ ------------> [After-throwing: ghi thất bại]
                                          |
                                 [After/finally: dọn dẹp]
                                          |
                                 Trả kết quả hoặc ném lỗi
```

Sơ đồ trên mô tả **hai nhánh kết quả hội tụ vào bước dọn dẹp**, không có nghĩa nhánh trả về và nhánh lỗi đều chạy. Một lần thực thi bình thường đi qua một trong hai nhánh kết quả, sau đó thực hiện phần dọn dẹp đã được thiết lập. Nếu chính advice trước đó ném lỗi hoặc chuyển hướng điều khiển trước khi phần dọn dẹp được thiết lập, phạm vi bao phủ sẽ khác.

### 2.1. Bảng so sánh ý nghĩa

| Loại hành vi | Điều kiện chạy | Có thể gắn với dữ kiện nào? | Dùng khi |
| --- | --- | --- | --- |
| **Before** | Trước điểm được chọn | Đối số, metadata, đối tượng liên quan | Ghi bắt đầu, kiểm tra điều kiện trước khi tiếp tục |
| **After-returning** | Thao tác/chuỗi bên trong trả về bình thường | Giá trị trả về nếu cơ chế hỗ trợ | Ghi thành công, quan sát kết quả hợp lệ |
| **After-throwing** | Thao tác/chuỗi bên trong kết thúc bằng ngoại lệ | Ngoại lệ được ném nếu được hỗ trợ | Ghi thất bại, phân loại lỗi |
| **After/finally** | Khi rời phạm vi đã được bảo vệ, bình thường hoặc do ngoại lệ | Một số dữ kiện ngữ cảnh, không tự có cả return/error | Thu hồi tài nguyên, kết thúc bối cảnh |
| **Around** | Bao quanh điểm và quyết định việc chuyển tiếp | Đối số trước, kết quả/lỗi sau khi tiếp tục | Điều phối đúng thứ tự, đo thời gian, tài nguyên có vòng đời |

**Chú ý về từ ngữ:** Nhiều mô hình gọi advice vô điều kiện là `after` hoặc `after finally`; một số API khác dùng tên `after completion`. Ngược lại, “completed successfully” thường mô tả **after-returning**. Cần kiểm tra hợp đồng của công nghệ để tránh đọc sai chữ “completion”.

### 2.2. Hoàn tất bình thường không nhất thiết là nghiệp vụ thành công

Một phương thức có thể trả về bình thường nhưng báo thất bại bằng dữ liệu:

```java
record PaymentResult(boolean approved, String reason) {}

PaymentResult charge() {
    return new PaymentResult(false, "DECLINED");
}
```

Đây là đoạn minh họa độc lập về mặt cú pháp Java nhưng chưa có chương trình `main`. `charge()` **trả về bình thường** nên về ngữ nghĩa điều khiển sẽ phù hợp với **after-returning**. Tuy nhiên kết quả `approved=false` cho biết thanh toán bị từ chối theo miền nghiệp vụ.

Vì thế:

- **After-returning** nói về cách kết thúc lời gọi, không tự xác nhận thành công nghiệp vụ.
- **After-throwing** nói về cách kết thúc do ngoại lệ, không tự quyết định lỗi đó có thể phục hồi hay không.
- **After/finally** nói về dọn dẹp khi rời phạm vi, không tự nói thao tác đã commit, được xác nhận hay được người dùng chấp nhận.

Nếu cần ghi “đã thanh toán thành công”, hãy kiểm tra **hợp đồng kết quả hoặc sự kiện nghiệp vụ được xác nhận**, không đơn giản dựa vào việc phương thức không ném lỗi.

## 3. Từ cách kết thúc đến hành vi cần chọn

Thay vì học lại định nghĩa dài của từng advice, hãy đi từ **kết cục tại đúng join point đang được quan sát**. Một lời gọi đồng bộ có hai đường thoát chính: trả về bình thường (*normal completion*) hoặc thoát bằng ngoại lệ (*exceptional completion*). Hai đường này dẫn tới hành vi ghi nhận khác nhau, nhưng **cả hai đều có thể cần giải phóng tài nguyên mà advice sở hữu**.

~~~text
Join point được chọn và thực sự đi qua cơ chế can thiệp
    |
    +-- Trả về bình thường ----> after-returning (quan sát kết quả)
    |                               |
    |                               +--> after/finally (dọn phạm vi)
    |
    +-- Ném lỗi ra biên -------> after-throwing (quan sát lỗi)
                                    |
                                    +--> after/finally (dọn phạm vi)
~~~

Sơ đồ mô tả điều kiện theo nghĩa khái niệm, **không cam kết thứ tự cú pháp của nhiều advice riêng biệt trong mọi công cụ**. Với around advice triển khai bằng `try/catch/finally`, luồng điều khiển có thể được đọc trực tiếp theo các khối lồng nhau. Nếu một advice phía trong ném hoặc chuyển đổi lỗi, tầng ngoài quan sát **kết cục của cả tầng trong**, chứ không nhất thiết kết cục nguyên thủy của target.

### 3.1. Nhánh return: biết *đã trả về*, chưa biết *thành công nghiệp vụ*

After-returning được chọn khi join point kết thúc bình thường; `null`, `false`, `Result.failure(...)` hoặc giá trị số `0` vẫn là **normal return** nếu không có ngoại lệ thoát ra. Phương thức `void` cũng có thể kết thúc bình thường, nhưng không có đối tượng kết quả để lấy như một return value thông thường. Cơ chế binding kết quả và lựa chọn method `void` cần kiểm tra ở công cụ AOP cụ thể.

Nếu chỉ cần ghi số lượt method hoàn tất bình thường, after-returning có thể phù hợp. Nếu muốn ghi đơn hàng **đã lưu bền vững** hoặc thanh toán **được xác nhận**, phải quan sát trạng thái nghiệp vụ hoặc ranh giới xác nhận tương ứng; một normal return chưa đủ.

After-returning thường dùng để quan sát kết quả. Nếu chính việc xuất metric/log từ advice ném lỗi, caller vẫn có thể gặp lỗi **sau khi target đã trả thành công**. Vì vậy lỗi của advice phải có chính sách riêng, không được mặc định luôn vô hại.

### 3.2. Nhánh throw: theo dõi *lỗi thoát khỏi biên*, không phải mọi lỗi từng phát sinh

After-throwing phản ứng khi một ngoại lệ phù hợp **thoát ra khỏi join point được chọn**. Nếu target bắt một `IOException` bên trong rồi trả dữ liệu dự phòng, method ngoài kết thúc bình thường: after-throwing trên method ấy không tự chạy chỉ vì từng có `throw` ở sâu bên trong.

Java có `Throwable`, `Exception`, `RuntimeException` và `Error`, nhưng cách bind/lọc loại lỗi tùy công nghệ. Quan sát lỗi khác với nuốt, thay hay phục hồi từ lỗi. Khi advice chỉ có nhiệm vụ ghi nhận, cần bảo toàn đối tượng/ý nghĩa ngoại lệ của target theo hợp đồng; một exception mới do logger hoặc formatter ném ra có thể che nguyên nhân ban đầu.

### 3.3. Nhánh rời phạm vi: dọn đúng tài nguyên bất kể return hay throw

After/finally dành cho công việc cần thực hiện khi **rời phạm vi đang được bảo vệ**, không dùng nhãn `SUCCESS` chỉ vì cleanup chạy. Điểm then chốt là advice đã thực sự bao phủ phạm vi đó; nếu pointcut không khớp, phần gốc không được chuyển tiếp, JVM bị kết thúc đột ngột hoặc thao tác không bao giờ rời phạm vi, không thể hứa “luôn chạy” theo nghĩa tuyệt đối.

Với một resource do advice tự sở hữu, sơ đồ tối giản:

~~~java
// Minh họa Java, Resource và proceed() chưa được định nghĩa.
Resource resource = openAdviceResource();
try {
    return proceed();
} finally {
    resource.close();
}
~~~

Nếu bước `openAdviceResource()` thất bại thì chưa có resource để đóng. Nếu advice phải mở **nhiều** tài nguyên nối tiếp, phải bảo vệ cả các tài nguyên đã mở thành công khi bước mở tiếp theo thất bại. Với `AutoCloseable`, `try-with-resources` thường diễn đạt quyền sở hữu và quy tắc *suppressed exceptions* rõ hơn một `finally` tự viết.

## 4. Điểm khác biệt quyết định: ghi nhận trạng thái hay hoàn trả quyền sở hữu?

Một bộ ghi log kết quả và một bộ dọn context không có cùng tiêu chí hoàn thành. Khi target trả về bình thường, logic quan sát có thể sử dụng return value; khi target throw, bộ ghi lỗi có thể dùng exception; nhưng **bộ dọn context, khóa hoặc resource do advice lấy phải xét cả hai**.

Ví dụ trong bài toán giữ vé:

- `reserveTicket("T-1")` trả `ReservationResult(rejected=true)`: after-returning có thể chạy vì method trả bình thường; after-throwing không chạy ở biên này; cleanup vẫn cần thực hiện.
- `reserveTicket("T-2")` ném `IllegalStateException` ra caller: after-throwing có thể chạy nếu pointcut và loại lỗi phù hợp; after-returning của cùng biên không chạy; cleanup vẫn cần thực hiện.
- Một advice ghi audit lỗi khi xuất sự kiện: đây là **lỗi phát sinh từ advice**. Kết quả caller quan sát phụ thuộc cấu trúc bao, chính sách lỗi và thứ tự các advice.
- Một kết nối do caller truyền vào còn cần được sử dụng sau khi lời gọi trả về: advice không được tự động đóng kết nối ấy chỉ vì có after/finally. Quyền sở hữu quyết định nơi cleanup.

Vì vậy hãy viết hai hợp đồng khác nhau: **khi nào một event được ghi** và **ai có trách nhiệm đóng/phục hồi tài nguyên nào**. Tránh biến cùng một nhánh “after” thành nơi mặc định vừa log thành công, vừa ghi lỗi, vừa đóng tất cả resource.

## 5. Ba câu hỏi trước khi chọn advice

1. **Biên nào đang được quan sát?** Method call, method execution hay proxy invocation; trả một `CompletionStage` có thể chỉ là trả handle chứ chưa phải completion của tác vụ nền. Kết cục được xét theo *biên đã chọn*, không theo cảm nhận “request đã xong”.
2. **Lời gọi rời biên theo đường nào?** Normal return (kể cả `null`, `void`, kết quả báo thất bại), exception thoát ra, hay thao tác tiếp tục bất đồng bộ. Việc chọn after-returning/after-throwing phải dựa trên đường này.
3. **Ai sở hữu tài nguyên và lỗi từ cleanup phải xử lý ra sao?** Cleanup có thể thất bại; với `try/finally` thông thường, lỗi trong `finally` có thể che return hoặc exception đang chờ. Không được tùy tiện nuốt lỗi cleanup nghiêm trọng, cũng không được để một lỗi telemetry tùy chọn đổi kết quả nghiệp vụ ngoài ý định.

Các phần tiếp theo dùng **ma trận đường điều khiển, ví dụ Java 17 có ba nhánh và tình huống tài nguyên thật** để kiểm chứng các quyết định trên. Điều cốt lõi của bài là phân biệt **mốc quan sát kết cục** với **trách nhiệm giải phóng tài nguyên** trong cùng một luồng thực thi.

## 6. So sánh bằng ma trận đường điều khiển

| Tình huống ở thao tác bên trong | After-returning | After-throwing | After/finally |
| --- | --- | --- | --- |
| Trả về `"OK"` | Có | Không | Có |
| Trả về `null` bình thường | Có theo ngữ nghĩa hoàn tất; binding phải phù hợp | Không | Có |
| Phương thức `void` kết thúc bình thường | Có nếu advice không đòi bind giá trị không hợp lệ | Không | Có |
| Trả `Result.failure` bình thường | Có | Không | Có |
| Ném `IllegalArgumentException` | Không | Có nếu khớp điều kiện ngoại lệ | Có |
| Ném `IOException` | Không | Có nếu khớp điều kiện ngoại lệ | Có |
| Advice trước đó chặn, không hề thực thi điểm đang xét | Phụ thuộc phạm vi và chuỗi bên trong có thực sự được vào hay không | Phụ thuộc phạm vi | Chỉ nếu cấu trúc finally của advice đã được thiết lập |
| Phương thức trả `CompletableFuture` đang pending | Có thể thấy lời gọi tạo future đã trả về | Không chỉ vì future có thể thất bại sau này | Dọn dẹp phạm vi lời gọi tạo future, chưa chắc dọn sau tác vụ async |

Đây là **ma trận ý tưởng**. Một biểu thức advice có thể bị giới hạn thêm bởi pointcut, kiểu giá trị ràng buộc hoặc loại join point; bảng không khẳng định một advice được khai báo sẽ tự động áp dụng tại mọi điểm.

### 6.1. Kết thúc phương thức không phải hoàn tất giao dịch

Một phương thức có thể trả về trước khi giao dịch ngoài, ghi xuống đĩa, gửi mạng hoặc công việc phụ thực sự được xác nhận. Ghi `SUCCESS` ở after-returning **chưa chứng minh** dữ liệu đã commit hoặc bên nhận đã chấp nhận.

Nếu cần sự kiện “đã xác nhận đặt vé”, phải chọn **ranh giới nghiệp vụ có cam kết rõ ràng** hoặc dữ liệu kết quả thể hiện trạng thái xác nhận; không suy ra điều đó từ lifecycle chung của một lời gọi.

## 7. Ví dụ Java 17 độc lập: ba nhánh và một bước dọn dẹp

Ví dụ này dùng **JDK dynamic proxy** để minh họa hành vi bổ sung quanh phương thức giao diện. Mã này **không biến đổi bytecode của lớp đích** và không tự can thiệp lời gọi trực tiếp, constructor hay mọi loại join point AOP. Nó chỉ làm rõ thứ tự before, after-returning, after-throwing và finally, hoàn toàn chạy được bằng Java 17 trở lên.

Tạo tệp `AdviceCompletionDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AdviceCompletionDemo {
    interface TicketPort {
        String book(String ticketCode);
    }

    static final class TicketService implements TicketPort {
        @Override
        public String book(String ticketCode) {
            if (ticketCode == null || ticketCode.isBlank()) {
                throw new IllegalArgumentException("Mã vé rỗng");
            }
            return "BOOKED:" + ticketCode;
        }
    }

    private static Object invokeTarget(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static TicketPort withAdvice(TicketPort target) {
        return (TicketPort) Proxy.newProxyInstance(
                TicketPort.class.getClassLoader(),
                new Class<?>[] { TicketPort.class },
                (proxy, method, args) -> {
                    if (!method.getName().equals("book")) {
                        return invokeTarget(method, target, args);
                    }

                    System.out.println("[BEFORE] book");
                    System.out.println("[ACQUIRE] context");
                    try {
                        Object result;
                        try {
                            result = invokeTarget(method, target, args);
                        } catch (Throwable error) {
                            System.out.println("[AFTER_THROWING] "
                                    + error.getClass().getSimpleName());
                            throw error;
                        }

                        System.out.println("[AFTER_RETURNING] " + result);
                        return result;
                    } finally {
                        System.out.println("[CLEANUP] context");
                    }
                });
    }

    public static void main(String[] args) {
        TicketPort observed = withAdvice(new TicketService());

        System.out.println("CALLER " + observed.book("T-7"));

        try {
            observed.book(" ");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER_ERROR " + error.getMessage());
        }

        System.out.println("DIRECT " + new TicketService().book("T-9"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 AdviceCompletionDemo.java
java AdviceCompletionDemo
```

Đầu ra chính xác:

```text
[BEFORE] book
[ACQUIRE] context
[AFTER_RETURNING] BOOKED:T-7
[CLEANUP] context
CALLER BOOKED:T-7
[BEFORE] book
[ACQUIRE] context
[AFTER_THROWING] IllegalArgumentException
[CLEANUP] context
CALLER_ERROR Mã vé rỗng
DIRECT BOOKED:T-9
```

### 7.1. Phân tích đường thành công

1. Proxy nhận lời gọi `observed.book("T-7")`, in `[BEFORE]` và ghi bước tạo bối cảnh minh họa.
2. `invokeTarget` chuyển lời gọi tới phương thức đích; đích trả `BOOKED:T-7`.
3. Không phát sinh lỗi ở thân đích, nên nhánh `catch` bên trong không chạy. Dòng `[AFTER_RETURNING]` được in.
4. Trước khi `return result` thực sự trả điều khiển ra khỏi `try`, khối `finally` in `[CLEANUP]`.
5. Người gọi nhận kết quả, sau đó in `CALLER BOOKED:T-7`.

`[ACQUIRE] context` và `[CLEANUP] context` chỉ là **mô phỏng vòng đời tài nguyên**, không phải hệ thống mở/đóng tài nguyên thật. Mục đích là thấy đúng thời điểm dọn dẹp.

### 7.2. Phân tích đường ngoại lệ

Với `observed.book(" ")`, `ticketCode.isBlank()` là `true` nên đích ném `IllegalArgumentException`.

- Reflection bọc lỗi đích trong `InvocationTargetException`; `invokeTarget` bóc `getCause()` và ném lại nguyên nhân ban đầu.
- Khối `catch` bên trong in `[AFTER_THROWING] IllegalArgumentException`, rồi ném lại đúng đối tượng lỗi.
- Khối `finally` bên ngoài vẫn in `[CLEANUP]` trước khi ngoại lệ đến người gọi.
- Người gọi bắt ngoại lệ và in thông báo `Mã vé rỗng`.
- Không có `[AFTER_RETURNING]` cho lần gọi lỗi.

### 7.3. Vì sao lời gọi trực tiếp không có advice?

`new TicketService().book("T-9")` dùng trực tiếp đối tượng đích, không đi qua proxy. Do đó chỉ in `DIRECT BOOKED:T-9`. Đây là giới hạn của **cơ chế proxy đang minh họa**, không phải khẳng định mọi cơ chế weaving đều bỏ qua lời gọi trực tiếp.

Một cơ chế biến đổi bytecode phù hợp có thể can thiệp tại điểm thực thi khác; mỗi công nghệ có mô hình join point và phạm vi kết hợp riêng.

### 7.4. Vì sao đặt phần dọn dẹp trong `finally` ngoài?

Cấu trúc được chọn là:

```text
before
acquire
try:
    try:
        result = proceed-to-target
    catch error:
        after-throwing(error)
        throw error
    after-returning(result)
    return result
finally:
    cleanup
```

Đây là **giả mã cấu trúc**, giúp tránh viết phần dọn dẹp hai lần. Nó bảo đảm cleanup chạy khi đoạn bên trong kết thúc theo return hoặc throw trong phạm vi try, theo ngữ nghĩa Java thông thường. Dòng `[AFTER_RETURNING]` nằm **ngoài khối catch cho target**, nên nếu việc ghi success tự gặp lỗi, ta không gán nhầm nó là lỗi do phương thức đích tạo ra.

Nếu `[ACQUIRE]` là thao tác cấp phát tài nguyên thật và có thể lỗi, cần cấu trúc lại việc nhận/quản lý tài nguyên để chỉ dọn những gì đã cấp thành công; không dựa máy móc vào vị trí hai câu `println` này.

## 8. Ví dụ ranh giới tài nguyên thật: try-with-resources

Trong Java, lựa chọn thường rõ hơn cho đối tượng có vòng đời là **try-with-resources**. Nó bảo vệ việc đóng tài nguyên đã mở thành công và có quy tắc xử lý lỗi đóng khác với một `finally` thủ công.

Ví dụ độc lập, lưu thành `ResourceAdviceDemo.java`:

```java
public class ResourceAdviceDemo {
    static final class TraceScope implements AutoCloseable {
        TraceScope() {
            System.out.println("OPEN");
        }

        @Override
        public void close() {
            System.out.println("CLOSE");
        }
    }

    static String run(boolean fail) {
        try (TraceScope ignored = new TraceScope()) {
            if (fail) {
                throw new IllegalArgumentException("Đích thất bại");
            }
            return "OK";
        }
    }

    public static void main(String[] args) {
        System.out.println("RESULT " + run(false));
        try {
            run(true);
        } catch (IllegalArgumentException error) {
            System.out.println("ERROR " + error.getMessage());
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 ResourceAdviceDemo.java
java ResourceAdviceDemo
```

Đầu ra:

```text
OPEN
CLOSE
RESULT OK
OPEN
CLOSE
ERROR Đích thất bại
```

Đây là ví dụ về **cơ chế dọn dẹp Java** để áp dụng khi xây dựng một advice có tài nguyên. Nó không phải một aspect đầy đủ hay bằng chứng mọi hệ AOP hỗ trợ nguồn tài nguyên tự động giống nhau. Nếu `close()` ném lỗi khi thân `try` cũng đã ném lỗi, Java try-with-resources có thể giữ lỗi thân try là lỗi chính và đính lỗi đóng dưới dạng **suppressed exception**.

### 8.1. Advice phải sở hữu đúng tài nguyên

Một advice chỉ nên đóng tài nguyên nó sở hữu hoặc được hợp đồng giao trách nhiệm đóng. Ví dụ nếu người gọi đưa vào một `InputStream` và giữ quyền sở hữu, advice không nên tự động đóng stream chỉ vì lời gọi đã kết thúc. Ngược lại, nếu advice tự mở scope đo đạc, nó phải khôi phục scope theo đúng vòng đời được định nghĩa.

Dùng câu hỏi: “Ai cấp phát? Ai sở hữu? Trường hợp nào được phép đóng? Nếu đã đóng rồi thì sao?” trước khi biến một hành vi dọn dẹp thành chính sách cắt ngang.

## 9. Thứ tự khi có nhiều advice và aspect

Khi các aspect lồng nhau, thứ tự before và sau không nhất thiết giống nhau. Giả sử:

```text
Outer(
   Inner(
      Task()
   )
)
```

Nếu cả Outer và Inner đều ghi trước, sau thành công và dọn dẹp, đường bình thường có thể theo cấu trúc:

```text
Outer before
Inner before
Task
Inner after-returning
Inner finally
Outer after-returning
Outer finally
```

Khi Task ném lỗi:

```text
Outer before
Inner before
Task throws
Inner after-throwing
Inner finally
Outer after-throwing
Outer finally
```

Đây là **thứ tự mô hình A(B(Task))** với các khối bao quanh được tổ chức theo cấu trúc này. Thứ tự ưu tiên mặc định giữa nhiều aspect không được suy ra từ tên lớp hay thứ tự viết trong file; phải tra quy tắc của cơ chế đang dùng và kiểm chứng bằng chương trình.

### 9.1. Một advice bên trong có thể thay kết quả mà advice bên ngoài quan sát

Nếu Inner bắt lỗi rồi trả một giá trị thay thế, Outer có thể thấy **đường trả về bình thường** của chuỗi bên trong, dù Task đã ném lỗi. Khi đó:

- Inner có thể chạy logic xử lý lỗi của chính nó.
- Outer có thể chạy after-returning vì thứ nó quan sát là **Inner(Task)** đã hoàn tất bình thường.
- Không có mâu thuẫn: hai advice đang quan sát **hai ranh giới khác nhau**.

Tương tự, nếu Inner trả kết quả nhưng after-returning của Inner ném lỗi, Outer có thể đi vào nhánh after-throwing. Muốn phân tích đúng phải biết **ranh giới điều khiển mà mỗi advice bao quanh**.

### 9.2. Retry và đo thời gian

```text
Timing(Retry(Task))  -> thời gian toàn bộ chuỗi thử lại
Retry(Timing(Task))  -> thời gian riêng từng lần thử (nếu mỗi lần qua Timing)
```

Việc giải phóng tài nguyên theo lần thử hay theo cả chuỗi sẽ khác nhau. Một scope dành riêng cho từng lần gọi bên trong retry phải được dọn theo từng lần; một scope dành cho toàn bộ yêu cầu có thể cần bao ngoài. Không đặt dọn dẹp sai vòng đời rồi giả định `finally` tự sửa được thiết kế đó.

## 10. Bất đồng bộ: “trả về” chưa chắc “công việc đã hoàn tất”

Đây là một trong những sai lầm khó phát hiện nhất.

Một phương thức có thể nhanh chóng trả về `CompletableFuture<Result>`, một đối tượng đại diện cho công việc chạy tiếp:

```java
CompletableFuture<String> loadAsync() {
    return CompletableFuture.supplyAsync(() -> slowOperation());
}
```

Đây là **mã minh họa**; `slowOperation()` cần được định nghĩa trong chương trình thực.

Trong một cơ chế can thiệp **lời gọi phương thức**, after-returning có thể chạy **ngay khi `loadAsync()` trả về đối tượng future**, dù tác vụ bên trong vẫn đang chạy và có thể thành công hoặc thất bại sau đó.

Nếu finally đóng tài nguyên mà công việc trong future vẫn cần dùng, ta có thể **đóng quá sớm**.

### 10.1. Hai nghĩa của “completion”

| Sự kiện | Điều đã biết | Điều chưa chắc |
| --- | --- | --- |
| `loadAsync()` trả một future | Việc tạo/trả đối tượng future kết thúc bình thường | Tác vụ bất đồng bộ hoàn thành hay chưa |
| Future hoàn tất thành công | Kết quả bất đồng bộ đã có | Chưa chắc thao tác ngoài như hệ thống thanh toán đã được xác nhận theo nghĩa nghiệp vụ |
| Future hoàn tất ngoại lệ | Phép tính bất đồng bộ báo lỗi | Không có kết quả thành công của tác vụ |
| Scope của advice quanh lời gọi kết thúc | Vòng đời đồng bộ của lời gọi đã đóng | Tài nguyên được công việc async sử dụng có thể vẫn cần sống |

Để theo dõi **kết quả bất đồng bộ**, một chính sách có thể cần gắn callback lên future hoặc dùng cơ chế context-aware do kiến trúc định nghĩa. Chẳng hạn, `whenComplete((value, error) -> ...)` được gọi khi future hoàn tất; cách `error` được biểu diễn có thể là ngoại lệ bọc của cơ chế future.

### 10.2. Lựa chọn thời điểm dọn dẹp với async

- Nếu tài nguyên chỉ phục vụ **việc tạo future**, có thể đóng khi phương thức trả về.
- Nếu tài nguyên phục vụ **tác vụ trong future**, phải quản lý vòng đời xuyên qua completion thật, đồng thời truyền đúng quyền sở hữu tới tác vụ.
- Nếu bối cảnh gắn với luồng hiện tại, chuyển việc sang luồng khác có thể làm mất bối cảnh; cần cơ chế truyền và khôi phục riêng.
- Nếu callback có thể chạy trên luồng khác, phần dọn dẹp phải an toàn đồng thời và tránh đóng trùng.

Không dùng duy nhất finally bao quanh phương thức tạo future để tuyên bố “mọi công việc bất đồng bộ đã được dọn”. Phạm vi dọn dẹp phải tương ứng với **vòng đời thực của tài nguyên**.

## 11. Kiểm toán, log và ý nghĩa thành công

Một chính sách kiểm toán thường cần trả lời “ai làm gì, khi nào, kết quả nào đã được xác nhận”. Dùng lifecycle advice mà không định nghĩa tiêu chí thành công sẽ dễ sinh sự kiện sai.

Ví dụ `submitOrder()` có thể:

1. Trả một mã yêu cầu để xử lý sau (đồng bộ return, nghiệp vụ chưa hoàn tất).
2. Ném lỗi vì đầu vào không hợp lệ (throw).
3. Trả một kết quả `REJECTED` bình thường (return nhưng nghiệp vụ từ chối).
4. Hoàn tất xử lý thành công và dữ liệu đã được xác nhận (thành công nghiệp vụ).

After-returning chỉ xác nhận **mục 1, 3, 4 đi qua đường trả về bình thường**; nó không phân biệt nghiệp vụ đã xác nhận hay chưa nếu không đọc hợp đồng kết quả.

### 11.1. Ghi nhận sự kiện đúng ranh giới

- Với log kỹ thuật: có thể dùng before + after-returning/after-throwing + finally để theo dõi mọi kết quả lời gọi.
- Với đo thời gian: có thể lấy mốc bắt đầu và dùng finally ghi thời lượng, dù thành công hay lỗi, miễn phạm vi được bảo vệ đúng.
- Với sự kiện “đơn đã được xuất”: cần căn cứ vào **trạng thái nghiệp vụ được xác nhận** chứ không chỉ một lần return.
- Với tài nguyên: đóng ở nơi sở hữu đúng vòng đời, không đóng đối tượng của người gọi khi hợp đồng không cho phép.
- Với kiểm soát quyền: nếu kiểm tra thất bại ở before, phải bảo đảm công việc chính không chạy; không đợi after-returning mới quyết định có cho phép.

## 12. Lỗi dọn dẹp: thiết kế và xử lý một cách có chủ đích

### 12.1. Làm mất lỗi gốc

Mã sau có rủi ro:

```java
try {
    operation();
} finally {
    throw new IllegalStateException("Cleanup failed");
}
```

Đây là **đoạn minh họa**, `operation()` chưa được định nghĩa. Nếu `operation()` đã ném lỗi khác, lỗi từ finally có thể thay thế lỗi gốc. Nếu operation trả về thành công, người gọi vẫn nhận ngoại lệ cleanup.

Điều này không luôn sai về nghiệp vụ: có trường hợp đóng tài nguyên thất bại thực sự phải khiến thao tác báo lỗi. Nhưng quyết định ấy phải được thiết kế, không nảy sinh vô tình do code logging.

### 12.2. Lỗi cleanup có được bỏ qua không?

Không có quy tắc “bỏ qua mọi lỗi dọn dẹp” áp dụng cho tất cả:

- Với tài nguyên quan trọng, lỗi đóng/flush có thể làm mất dữ liệu và cần được báo.
- Với phép đo best-effort, lỗi hệ đo không nhất thiết nên làm thất bại nghiệp vụ.
- Với kiểm toán bắt buộc, việc ghi thất bại có thể thay đổi quyền thực hiện nghiệp vụ và đòi hỏi cơ chế tin cậy hơn là vài dòng log.

Cần phân biệt **nghĩa vụ vận hành**, **độ tin cậy** và **hợp đồng API**, rồi quyết định rõ cách giữ ngoại lệ chính, cách đính lỗi phụ hoặc điều kiện làm thao tác thất bại.

### 12.3. Dọn dẹp không đồng nghĩa rollback

`finally` có thể gọi `unlock()` hoặc `close()`. Nó **không tự đảo ngược** các cập nhật dữ liệu đã xảy ra. Rollback giao dịch phụ thuộc cơ chế giao dịch và ranh giới nghiệp vụ; nếu tác vụ đã gửi yêu cầu mạng hoặc phát sự kiện, những tác dụng phụ đó có thể đã xảy ra.

Đừng viết `after/finally` rồi tin rằng hệ thống “quay về trạng thái ban đầu” khi ném lỗi. Đó là hai trách nhiệm khác nhau.

## 13. Kiểm thử từng nhánh của advice

Chỉ kiểm tra lời gọi thành công chưa đủ. Một bộ kiểm thử phù hợp nên bao phủ:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Đích trả kết quả bình thường | After-returning và cleanup chạy; after-throwing không chạy |
| Đích ném ngoại lệ | After-throwing và cleanup chạy; lỗi gốc đến người gọi |
| Đích trả `null` hoặc `void` | Không nhầm thành throw, binding return phù hợp |
| Đích trả đối tượng `Result.failure` | Không suy luận thành công nghiệp vụ chỉ từ normal return |
| Advice before ném lỗi | Xác định scope nào đã được thiết lập và tài nguyên nào cần dọn |
| Advice after-returning ném lỗi | Quan sát ngoại lệ ra ngoài và cleanup; không nhầm là lỗi từ target |
| Cleanup ném lỗi | Xác minh lỗi gốc được giữ hay bị che và chính sách mong muốn |
| Lời gọi ngoài pointcut | Không chạy advice ngoài phạm vi |
| Lời gọi bỏ qua proxy hoặc lớp chưa được weaving | Ghi nhận giới hạn của cơ chế |
| Hai aspect lồng nhau | Kiểm tra thứ tự và phạm vi của từng advice |
| Tác vụ trả future trước khi hoàn tất | Phân biệt return của phương thức và completion của future |
| Nhiều luồng cùng gọi | Bối cảnh và tài nguyên mỗi lời gọi không lẫn nhau |

### 13.1. Phát hiện dọn dẹp hai lần hoặc thiếu dọn dẹp

Nếu cùng một thao tác được bọc bởi hai lớp quản lý tài nguyên, có thể có hai lời gọi `close()` hoặc khôi phục trạng thái sai thứ tự. Nếu một advice chỉ cleanup sau thành công, tài nguyên có thể bị rò rỉ khi ném lỗi.

Một kiểm thử tốt nên đếm **số lần chiếm/nhả** tài nguyên và điều kiện đúng của chúng, thay vì chỉ nhìn một dòng log xuất hiện.

### 13.2. Chẩn đoán có hệ thống

Khi cleanup không chạy hoặc chạy sai:

1. Kiểm tra pointcut có khớp điểm mong muốn và loại join point có được hỗ trợ không.
2. Kiểm tra code đã được weaving hoặc lời gọi thật đi qua proxy/interceptor chưa.
3. Kiểm tra advice có thiết lập vùng try/finally **trước** điểm có thể phát sinh lỗi hay không.
4. Xác định lỗi đến từ target, advice trước, advice sau hay cleanup.
5. Kiểm tra có nhiều aspect đang thay đổi đường điều khiển không.
6. Kiểm tra vòng đời tài nguyên kết thúc đồng bộ hay bất đồng bộ.
7. Kiểm tra các đường return, throw, cancellation và kết thúc bất thường tương ứng.
8. Kiểm tra after-returning có đang gắn nhãn “thành công nghiệp vụ” cho kết quả từ chối không.
9. Kiểm tra việc ghi log/kiểm toán có làm lộ dữ liệu nhạy cảm hoặc che lỗi gốc không.

## 14. Sai lầm thường gặp

| Hiểu sai hoặc lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng “after” luôn là “thành công” | Ghi trạng thái sai ở nhánh lỗi | Phân biệt after-returning, after-throwing, after/finally |
| Dùng after-returning để đóng mọi tài nguyên | Rò rỉ khi target ném lỗi | Dùng phạm vi finally/đóng tài nguyên theo vòng đời |
| Ghi “SUCCESS” vì phương thức không ném lỗi | Nhầm `Result.failure` hoặc công việc còn pending | Đọc hợp đồng kết quả và ranh giới xác nhận |
| Dùng after-throwing để cleanup nhưng quên đường bình thường | Rò rỉ hoặc thiếu khôi phục khi thành công | Tách cleanup thành hành vi bao phủ cả hai nhánh |
| Nghĩ `finally` luôn chạy trong mọi sự cố | Kỳ vọng sai khi VM dừng cưỡng bức | Thiết kế khôi phục tài nguyên ngoài tiến trình khi cần |
| Đặt `try` sau nhiều bước cấp phát | Không dọn phần đã cấp khi bước sau lỗi | Thiết kế thứ tự cấp phát/giải phóng rõ ràng |
| Ném lỗi/return trong finally mà không xét hậu quả | Che ngoại lệ hoặc đổi kết quả gốc | Xử lý lỗi dọn dẹp có chủ đích |
| Đóng tài nguyên của người gọi | Gây lỗi ở lần sử dụng tiếp theo | Xác định rõ ownership |
| Cho rằng finally quanh hàm trả future đồng nghĩa future đã xong | Đóng quá sớm, mất bối cảnh | Buộc cleanup vào completion thật nếu tài nguyên sống qua async |
| Không xét nhiều aspect lồng nhau | Sai thứ tự đo, retry, cleanup | Xác định precedence và kiểm thử đường chạy |
| Chỉ test nhánh thành công | Không phát hiện rò rỉ/lỗi che khuất | Test return, throw, lỗi advice và bypass |

## 15. Bài tập vận dụng có đáp án

### Bài 1 — Chọn advice đúng

Bạn muốn ghi thời lượng xử lý của mọi lời gọi thuộc một nhóm phương thức, kể cả lời gọi thất bại; đồng thời muốn ghi kích thước kết quả khi trả về bình thường.

**Đáp án:** Có thể dùng scope bắt đầu đo trước lời gọi và kết thúc đo bằng hành vi kiểu finally, đồng thời dùng after-returning để quan sát kích thước kết quả. Nếu kết quả là `null` hoặc `void`, phải tuân thủ hợp đồng binding phù hợp. Không dùng after-returning làm nơi duy nhất kết thúc đồng hồ vì nhánh throw bị bỏ sót.

### Bài 2 — Kết quả từ chối

`authorize()` trả `AuthorizationResult(false)` mà không ném ngoại lệ. After-throwing có chạy vì “xác thực thất bại” không?

**Đáp án:** Không. Về luồng điều khiển, phương thức đã trả về bình thường. After-returning là nhánh phù hợp; việc xác định được phép hay bị từ chối phải đọc giá trị bên trong đối tượng kết quả.

### Bài 3 — Dọn dẹp và lỗi gốc

Một lời gọi ném `IOException` rồi `finally` ném `IllegalStateException`. Người gọi chắc chắn nhận `IOException` không?

**Đáp án:** Không. Trong `try/finally` Java thông thường, ngoại lệ từ finally có thể thay ngoại lệ gốc. Có thể cần thiết kế giữ lỗi chính và ghi lỗi phụ; try-with-resources có quy tắc suppressed exception hữu ích khi tài nguyên `AutoCloseable` được sử dụng đúng.

### Bài 4 — Lỗi trước khi vào vùng bảo vệ

Một advice cấp tài nguyên A thành công, cấp B thất bại, rồi mới dự kiến đi vào `try/finally` để đóng A/B. A có chắc được đóng không?

**Đáp án:** Không. Nếu lỗi xảy ra trước khi đi vào `try`, phần `finally` đó không được thiết lập. Cần tổ chức scope sao cho mỗi tài nguyên cấp thành công có đường đóng khi bước tiếp theo thất bại.

### Bài 5 — Future còn chạy

`sendAsync()` trả `CompletableFuture` chưa hoàn tất. Advice `after-returning` in `SUCCESS` và `finally` đóng kết nối mà tác vụ trong future còn sử dụng. Có những vấn đề nào?

**Đáp án:** Hàm đã trả về future nhưng tác vụ chưa chắc thành công. Log `SUCCESS` có thể sai nghĩa, và kết nối có thể bị đóng quá sớm. Cần phân biệt completion của lời gọi đồng bộ với completion của công việc bất đồng bộ và gắn ownership/cleanup vào vòng đời thật.

### Bài 6 — Hai lớp around

Có `Outer(Inner(Task))`. Task trả `OK`, nhưng after-returning của Inner ném lỗi. Outer có nhất thiết chạy after-returning không?

**Đáp án:** Không. Outer quan sát chuỗi Inner(Task); khi Inner ném lỗi, Outer có thể đi vào nhánh after-throwing dù Task đã trả `OK`. Cần xét ranh giới mà từng advice bao quanh, không chỉ kết quả của thân Task.

### Bài 7 — Retry và finally

Một advice retry gọi tác vụ ba lần; mỗi lần tạo một scope theo dõi riêng. Bạn nên dọn scope theo từng lần hay một lần ngoài cùng?

**Đáp án:** Nếu mỗi lần thử sở hữu scope riêng, phải dọn **theo từng lần**, kể cả khi lần đó thất bại rồi được thử lại. Scope chung của toàn yêu cầu có thể đặt bên ngoài chuỗi retry nếu đó là vòng đời đã định. Không để một scope theo lần thử tồn tại qua các lần gọi sau mà không có chủ đích.

## 16. Ghi nhớ

- **After-returning** chỉ gắn với **trả về bình thường**; điều này chưa bảo đảm thành công nghiệp vụ.
- **After-throwing** gắn với **đường ném ngoại lệ**; dữ liệu lỗi khác dữ liệu kết quả thành công.
- **After/finally** nhằm **dọn dẹp khi rời phạm vi được bảo vệ**, thường bao phủ cả return lẫn throw, nhưng không hứa chạy trong mọi sự cố của tiến trình.
- Việc dọn dẹp chỉ đúng khi **phạm vi và quyền sở hữu tài nguyên** đã được xác định; lỗi cleanup có thể che lỗi gốc nếu xử lý bất cẩn.
- **Nhiều aspect lồng nhau** làm thay đổi thứ tự; một advice bên ngoài quan sát kết quả của chuỗi bên trong, có thể khác kết quả đích trực tiếp.
- Với tác vụ bất đồng bộ, **phương thức trả future** và **future thật sự hoàn tất** là hai thời điểm khác nhau.
- Đối với advice chỉ quan sát, hãy **bảo toàn kết quả, ngoại lệ và số lần thực thi**, kiểm thử cả nhánh thành công, lỗi, cleanup failure và đường bypass.
