# Gọi tiếp nhiều lần và nguy cơ lặp tác dụng phụ trong around advice (AOP)

**Around advice** là dạng hành vi bao quanh một điểm can thiệp (*join point*) trong lập trình hướng khía cạnh (Aspect-Oriented Programming, **AOP**). Nó có thể thực hiện việc gì đó **trước**, điều phối việc **tiếp tục chuỗi thực thi**, rồi xử lý **kết quả hoặc lỗi** sau đó. Trong nhiều mô hình AOP, thao tác tiếp tục được gọi là **`proceed`**. Năng lực đặc biệt — và cũng là nguồn rủi ro — là một số cơ chế cho phép around advice **không tiếp tục, tiếp tục một lần hoặc tiếp tục nhiều lần**.

Với advice chỉ để đo thời gian hoặc ghi log, **tiếp tục đúng một lần** thường là cách bảo toàn hợp đồng tự nhiên nhất. Khi chủ động tiếp tục nhiều lần để thử lại (*retry*), chương trình có thể **thực thi nghiệp vụ nhiều lần**: gửi hai email, tạo hai bản ghi, trừ tiền hai lần hoặc phát hai sự kiện. Việc lần đầu báo lỗi/timeout **không chứng minh** lần đầu chưa tạo tác dụng phụ.

Bài học này tập trung vào lý do và cơ chế lặp tác dụng phụ, sự khác biệt giữa các loại hành vi, retry an toàn, idempotency, thứ tự các aspect và cách kiểm thử. Những khả năng của `proceed` phụ thuộc mô hình AOP và bộ weaving đang dùng: **không nên mặc định mọi hệ AOP đều hỗ trợ gọi tiếp nhiều lần, thay đối số hoặc bỏ qua điểm nối**. Ví dụ Java 17 sử dụng JDK dynamic proxy để mô phỏng rõ hai lần gọi tiếp; nó **không phải** một bộ weaving bytecode tổng quát.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích rõ ý nghĩa của `proceed` trong chuỗi around advice và phân biệt nó với lệnh `return`, một lời gọi phương thức thông thường hay vòng lặp tùy ý.
- Xác định những tình huống **0 lần, 1 lần, nhiều lần** tiếp tục và hệ quả đối với kết quả/ngoại lệ.
- Phân biệt **tác dụng phụ (side effect)**, **độ an toàn khi retry**, **idempotency**, **at-most-once**, **at-least-once** và mục tiêu “một hiệu ứng nghiệp vụ”.
- Phân tích vì sao timeout/đứt kết nối có thể đến **sau khi thao tác bên ngoài đã hoàn tất**.
- Thiết kế retry có giới hạn số lần, ngân sách thời gian, bộ lọc lỗi, backoff và khóa chống trùng.
- Phân tích thứ tự `Retry(Logging(Task))` với `Logging(Retry(Task))`.
- Kiểm tra advice không vô tình nhân đôi thao tác chính, kết quả, exception, tài nguyên hay thông tin kiểm toán.
- Nhận biết giới hạn của proxy/interceptor so với weaving thực sự ở các điểm can thiệp khác.

## 2. Proceed là “tiếp tục chuỗi bên trong”, không phải bảo đảm một lần

Hình dung chương trình sau khi kết hợp aspect:

```text
Người gọi
   |
   v
Around A
   |
   +-- before A
   |
   +-- proceed() ------> Around B
   |                         |
   |                         +-- before B
   |                         +-- proceed() ---> Target
   |                         +-- after B
   |
   +-- after A
   |
   v
Người gọi nhận kết quả / ngoại lệ
```

Nếu A gọi `proceed()`, nó thường tiếp tục **chuỗi còn lại** dưới A: có thể là một advice B khác rồi mới đến mã nghiệp vụ đích. Do đó “gọi `proceed` hai lần” không chỉ có khả năng gọi đích hai lần; nó còn có thể chạy **các advice bên trong hai lần**.

Ở một số công nghệ, lời gọi tiếp tục có thể được phép nhiều lần. Ở công nghệ khác, cơ chế có thể hạn chế số lần, hình thức hoặc ngữ nghĩa `proceed`. Người học phải tra hợp đồng của hệ AOP cụ thể; không nên viết một vòng retry nếu framework/weaver không cho phép việc gọi tiếp tương ứng.

### 2.1. Ba lựa chọn cơ bản

| Hành vi của around advice | Luồng thực thi | Tác động dễ gặp |
| --- | --- | --- |
| **0 lần tiếp tục** | Advice tự trả kết quả, chặn hoặc ném lỗi | Đích có thể không chạy, như cache hit hoặc kiểm soát quyền từ chối |
| **1 lần tiếp tục** | Advice chuyển tiếp vào chuỗi bên trong một lần | Dễ bảo toàn hành vi cũ khi chỉ quan sát, nếu không đổi dữ liệu/lỗi |
| **Nhiều lần tiếp tục** | Advice chạy lại chuỗi bên trong | Có thể lặp nghiệp vụ, advice bên trong, log, sự kiện và giao dịch |

Ngay cả trường hợp **một lần** cũng không tuyệt đối bảo đảm chỉ có một tác dụng phụ: phương thức đích có thể tự phát nhiều sự kiện, gọi dịch vụ khác nhiều lần hoặc có retry nằm ở tầng bên trong. Ngược lại, hai lần tiếp tục không nhất thiết tạo hai hiệu ứng nếu nghiệp vụ được thiết kế chống trùng đúng nghĩa. Số lần gọi tiếp và số hiệu ứng nghiệp vụ là **hai đại lượng khác nhau**.

### 2.2. Around advice không chỉ có retry

Around advice còn được dùng để đo thời gian, quản lý bối cảnh, cache, phân quyền, kiểm soát tài nguyên hoặc thay kết quả khi hợp đồng cho phép. Những chính sách đó có đặc điểm khác nhau:

- **Logging/metrics:** thường phải bảo toàn đường thực thi và chỉ gọi tiếp một lần.
- **Cache:** có thể không gọi tiếp khi đã có dữ liệu hợp lệ; cần xác định cache hit có được phép bỏ qua thao tác gốc không.
- **Authorization:** có thể chặn trước khi tiếp tục khi chính sách không cho phép.
- **Retry:** có chủ đích gọi tiếp nhiều lần sau một số lỗi/điều kiện cụ thể.
- **Fallback:** có thể chuyển sang thao tác khác; không mặc định được quyền thay lỗi bằng kết quả khác.
- **Transaction/context:** bao quanh vòng đời, đòi hỏi biết phạm vi và thời điểm dọn dẹp.

Không nên suy luận từ việc mọi tình huống đều dùng around advice rằng chúng có cùng tính an toàn.

## 3. Tác dụng phụ là gì?

**Tác dụng phụ** là thay đổi có thể quan sát được ngoài giá trị trả về trực tiếp của một phép tính. Ví dụ:

| Thao tác | Tác dụng phụ có thể xảy ra | Nếu thực thi hai lần |
| --- | --- | --- |
| Tính `price * quantity` trên dữ liệu bất biến | Thường không có tác dụng phụ bên ngoài | Thường chỉ tốn CPU thêm |
| Đọc một bản ghi | Có thể ghi số lần đọc, ảnh hưởng cache hoặc log | Có thể tăng chi phí và thay thống kê |
| `inventory.decrease(1)` | Giảm tồn kho | Có thể giảm hai đơn vị |
| `account.debit(amount)` | Trừ số dư | Có thể trừ hai lần |
| `email.send(message)` | Gửi thư | Có thể phát hai thư |
| `eventBus.publish(event)` | Công bố sự kiện | Người nhận có thể xử lý lặp |
| `file.append(line)` | Thêm dòng vào tệp | Có thể ghi dòng lặp |
| `insertOrder(request)` | Ghi bản ghi mới | Có thể tạo hai bản ghi nếu không có ràng buộc chống trùng |

Một hàm được gọi là “đọc” cũng không chắc **thuần túy**: nó có thể đếm lượt xem, refresh token, khởi tạo lazy object hoặc gọi API theo dõi. Khi quyết định cho phép `proceed` nhiều lần, cần đánh giá toàn bộ **chuỗi tác dụng phụ phía trong**, không chỉ tên phương thức.

### 3.1. Thao tác thuần túy và thao tác không thuần túy

Một phép tính thuần túy (*pure*) với cùng đầu vào thường trả cùng kết quả và không có tác dụng phụ có thể quan sát được. Lặp phép tính ấy chủ yếu làm tăng chi phí.

Ngược lại, thao tác “tạo đơn”, “gửi tiền”, “đánh dấu đã giao” có thể làm thay đổi trạng thái hệ thống. Gọi lại cùng tham số không đủ chứng minh kết quả và trạng thái cuối sẽ tương đương với một lần gọi.

```text
Pure:          f(x) -> y                  (không đổi trạng thái ngoài)
Side-effect:   g(x) -> y + thay đổi S      (trạng thái ngoài bị tác động)
```

Đó là mô hình giải thích; tính thuần túy thực tế phụ thuộc hiện thực và các phụ thuộc được gọi, không chỉ chữ ký Java.

## 4. Khi nào hai lần gọi tiếp tạo lỗi nghiệp vụ?

Giả sử một around advice thử tối đa hai lần:

```text
try:
    return proceed()
catch transientError:
    return proceed()
```

Đây là **giả mã**, không phải cú pháp một công nghệ AOP cụ thể. Nếu `proceed` lần đầu thực sự tạo đơn hàng rồi lỗi khi xây dựng phản hồi, lần thứ hai có thể tạo **thêm đơn**. Việc code retry trông rất ngắn che giấu hai hoạt động nghiệp vụ thật sự.

### 4.1. Bốn thời điểm lỗi khác nhau

Với tác vụ gửi yêu cầu đến hệ thống bên ngoài:

```text
T0: Chưa gửi yêu cầu
T1: Đã gửi, bên nhận chưa xử lý
T2: Bên nhận đã thực hiện tác dụng phụ
T3: Phản hồi đã về tới người gọi
```

Một timeout có thể xuất hiện do mạng đứt giữa T1 và T2, hoặc **sau T2 nhưng trước T3**. Trong tình huống sau, phía gọi thấy “timeout” nhưng phía nhận **đã làm xong**. Đây là dạng kết quả **không chắc chắn** (*ambiguous outcome*).

Nếu retry ngay lập tức với một yêu cầu mới không nhận diện được trùng lặp, hệ thống bên nhận có thể làm lại. Vấn đề không phải thiếu `catch`, mà là **không biết hiệu ứng đã xảy ra hay chưa**.

### 4.2. Ngoại lệ không tự chứng minh rollback

Một thao tác có thể:

1. Ghi dữ liệu thành công.
2. Gửi sự kiện thành công.
3. Thất bại khi ghi log, đóng kết nối hoặc trả phản hồi.
4. Ném ngoại lệ ra ngoài.

Around advice bắt được ngoại lệ ở bước 4 nhưng không thể kết luận các bước 1–2 chưa diễn ra. Java exception là tín hiệu về **luồng điều khiển của lời gọi quan sát**, không phải biên bản trạng thái của mọi hệ thống bên ngoài.

Vì vậy một chính sách retry phải xét **tính an toàn của thao tác**. Không retry mù quáng mọi `RuntimeException`, `IOException` hay timeout.

## 5. Idempotency: lặp lời gọi nhưng không lặp hiệu ứng đã cam kết

Một thao tác **idempotent** theo nghĩa nghiệp vụ được thiết kế để lặp cùng **yêu cầu logic** mà không tạo thêm hiệu ứng cần tránh. Cách lý tưởng là sau nhiều lần xử lý cùng yêu cầu, trạng thái nghiệp vụ cuối giống với sau một lần xử lý phù hợp.

```text
apply(request) lần 1    -> tạo một hiệu ứng
apply(request) lần 2    -> nhận ra yêu cầu đã xử lý, không tạo hiệu ứng thứ hai
apply(request) lần N    -> vẫn không tạo hiệu ứng mới ngoài hợp đồng
```

Khái niệm này không có nghĩa mọi tín hiệu quan sát đều giống nhau: hệ thống có thể ghi thêm **log các lần thử** nhưng vẫn chỉ có **một khoản thanh toán**.

### 5.1. Idempotency key

Một cách thường gặp là dùng **mã yêu cầu duy nhất** cho một hành động logic:

- Lời gọi đầu sử dụng khóa `REQ-700`.
- Nếu lỗi mạng, lần thử lại phải sử dụng **cùng khóa `REQ-700`**.
- Hệ thống có trách nhiệm thực hiện nghiệp vụ xác định khóa đã hoàn tất hay chưa.
- Nếu hoàn tất, nó trả lại kết quả phù hợp mà không tạo hiệu ứng trùng.
- Nếu vẫn đang xử lý, hệ thống có chính sách rõ cho trạng thái *in progress*, chờ hoặc trả trạng thái để đối soát.

Lưu khóa phải được gắn với danh tính/chủ thể, loại thao tác và nội dung yêu cầu phù hợp. Nếu tái sử dụng cùng khóa nhưng **nội dung khác**, hệ thống nên phát hiện xung đột chứ không âm thầm trả kết quả cũ cho giao dịch mới.

### 5.2. Chỉ lưu khóa trong bộ nhớ chưa đủ cho hệ thống thật

Một `HashMap` trong một tiến trình đơn lẻ không bền khi tiến trình khởi động lại và không tự chia sẻ với các tiến trình khác. Nó cũng không đủ an toàn khi nhiều luồng cùng xử lý một khóa nếu không có phối hợp đồng thời.

Trong hệ thống thật có thể cần:

- Ràng buộc duy nhất hoặc thao tác nguyên tử trên bộ lưu trữ bền vững;
- Ghi trạng thái xử lý cùng hiệu ứng theo ranh giới giao dịch phù hợp;
- Lưu kết quả hoặc trạng thái kết thúc để phục vụ truy vấn/retry;
- Quy tắc xử lý yêu cầu đang chạy, lỗi vĩnh viễn và xung đột payload;
- Cơ chế đối soát nếu hiệu ứng nằm ở hệ thống ngoài, không thể cam kết nguyên tử cùng bộ lưu khóa;
- Chính sách thời hạn lưu khóa đủ dài so với cửa sổ retry và khả năng nhận yêu cầu lặp.

**Idempotency phải được thực hiện ở nơi có quyền kiểm soát hiệu ứng nghiệp vụ**, không chỉ ở around advice phía người gọi.

## 6. Ví dụ Java 17 chạy được: timeout sau khi đã ghi và retry hai lần

Ví dụ dưới đây minh họa điều rất dễ bỏ qua: lần đầu **đã tạo hiệu ứng**, nhưng trước khi nhận phản hồi, người gọi gặp một `ApparentTimeout` giả lập. Around interceptor sẽ thử lại.

Chạy hai phiên bản:

1. **UnsafeCheckout:** không kiểm tra yêu cầu trùng, nên mỗi lần gọi đều tăng số lần ghi nhận giao dịch.
2. **IdempotentCheckout:** nhận ra cùng `requestId`, không tạo giao dịch thứ hai.

Đây là chương trình **mô phỏng trong một tiến trình** với dữ liệu in-memory để thấy đúng luồng điều khiển, **không phải hiện thực idempotency đủ an toàn cho thanh toán thực**.

Lưu toàn bộ mã sau thành tệp `ProceedTwiceDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.Map;

public class ProceedTwiceDemo {
    interface Checkout {
        String charge(String requestId, int cents);
        int actualCharges();
    }

    static final class ApparentTimeout extends RuntimeException {
        ApparentTimeout() {
            super("response lost after commit");
        }
    }

    static final class UnsafeCheckout implements Checkout {
        private int charges;

        @Override
        public String charge(String requestId, int cents) {
            charges++;
            System.out.println("CORE committed #" + charges);
            if (charges == 1) {
                throw new ApparentTimeout();
            }
            return "RECEIPT-" + charges;
        }

        @Override
        public int actualCharges() {
            return charges;
        }
    }

    static final class IdempotentCheckout implements Checkout {
        private final Map<String, String> receipts = new HashMap<>();
        private int charges;
        private boolean first = true;

        @Override
        public String charge(String requestId, int cents) {
            String known = receipts.get(requestId);
            if (known != null) {
                System.out.println("CORE deduplicated " + requestId);
                return known;
            }

            charges++;
            String receipt = "RECEIPT-" + charges;
            receipts.put(requestId, receipt);
            System.out.println("CORE committed #" + charges);

            if (first) {
                first = false;
                throw new ApparentTimeout();
            }
            return receipt;
        }

        @Override
        public int actualCharges() {
            return charges;
        }
    }

    private static Object invokeTarget(
            Method method, Object target, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    static Checkout retryOnce(Checkout target) {
        return (Checkout) Proxy.newProxyInstance(
                Checkout.class.getClassLoader(),
                new Class<?>[]{Checkout.class},
                (proxy, method, args) -> {
                    if (!method.getName().equals("charge")) {
                        return invokeTarget(method, target, args);
                    }

                    for (int attempt = 1; attempt <= 2; attempt++) {
                        System.out.println("ADVICE attempt " + attempt);
                        try {
                            return invokeTarget(method, target, args);
                        } catch (ApparentTimeout error) {
                            if (attempt == 2) {
                                throw error;
                            }
                            System.out.println("ADVICE retry after timeout");
                        }
                    }
                    throw new AssertionError("unreachable");
                });
    }

    public static void main(String[] args) {
        System.out.println("UNSAFE");
        Checkout unsafe = retryOnce(new UnsafeCheckout());
        System.out.println("CALLER " + unsafe.charge("REQ-1", 500));
        System.out.println("CHARGES " + unsafe.actualCharges());

        System.out.println("IDEMPOTENT");
        Checkout safe = retryOnce(new IdempotentCheckout());
        System.out.println("CALLER " + safe.charge("REQ-1", 500));
        System.out.println("CHARGES " + safe.actualCharges());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ProceedTwiceDemo.java
java ProceedTwiceDemo
```

Đầu ra dự kiến chính xác:

```text
UNSAFE
ADVICE attempt 1
CORE committed #1
ADVICE retry after timeout
ADVICE attempt 2
CORE committed #2
CALLER RECEIPT-2
CHARGES 2
IDEMPOTENT
ADVICE attempt 1
CORE committed #1
ADVICE retry after timeout
ADVICE attempt 2
CORE deduplicated REQ-1
CALLER RECEIPT-1
CHARGES 1
```

### 6.1. Giải thích từng đường chạy

**Không chống trùng:**

- Advice in `ADVICE attempt 1`, chuyển tiếp lần đầu.
- `UnsafeCheckout.charge` tăng `charges` lên 1 rồi in `CORE committed #1`. Sau đó nó **cố ý ném timeout giả lập**: lỗi xảy ra sau khi “ghi” đã thực hiện.
- Advice bắt đúng `ApparentTimeout`, in dòng retry và chuyển tiếp **lần thứ hai**.
- Đích tăng `charges` từ 1 lên 2: có **hai hiệu ứng**, dù người gọi chỉ gọi `unsafe.charge(...)` một lần.
- Người gọi nhận `RECEIPT-2`, nhưng đây **không có nghĩa chỉ có một giao dịch**; dòng `CHARGES 2` cho thấy rủi ro.

**Có chống trùng trong phạm vi minh họa:**

- Lần đầu ghi kết quả cho khóa `REQ-1` trước khi ném timeout.
- Lần thử thứ hai giữ **nguyên khóa**, phát hiện `receipts` đã có `REQ-1`.
- Thay vì tăng `charges`, đích in `CORE deduplicated REQ-1` rồi trả lại `RECEIPT-1`.
- Dòng `CHARGES 1` minh họa “hai lần gọi nhưng một hiệu ứng”. Đây là đúng trong **chương trình tuần tự in-memory này**, không phải bằng chứng hoạt động bền vững hoặc an toàn đồng thời của một hệ thống thanh toán.

### 6.2. Vì sao ví dụ vẫn được xem là minh họa around advice?

`retryOnce` bao quanh lời gọi `Checkout.charge` và quyết định **khi nào, bao nhiêu lần** chuyển tiếp vào đối tượng đích. Nó tương tự một around advice có thể gọi `proceed` nhiều lần.

Tuy nhiên, `invokeTarget` ở đây dùng reflection và JDK dynamic proxy, **không phải từ khóa `proceed` của một công nghệ AOP chuyên dụng**. Proxy chỉ chặn những lời gọi đi qua giao diện được đại diện; nếu gọi `new UnsafeCheckout().charge(...)` trực tiếp, logic retry của proxy không chạy.

### 6.3. Điều gì là nguyên nhân chứ không phải triệu chứng?

- **Triệu chứng:** `CHARGES 2` xuất hiện sau một yêu cầu của người gọi.
- **Nguyên nhân trực tiếp:** interceptor chuyển tiếp vào thao tác đích hai lần.
- **Nguyên nhân rủi ro:** đích tạo hiệu ứng không idempotent khi gọi lại cùng yêu cầu logic.
- **Yếu tố kích hoạt:** timeout không phân biệt hiệu ứng đã hoàn tất với hiệu ứng chưa xảy ra.
- **Biện pháp:** quy tắc retry có điều kiện và cơ chế idempotency ở thành phần thực sự sở hữu hiệu ứng.

Chỉ ghi log “attempt=2” giúp quan sát, nhưng **không loại bỏ** lỗi nghiệp vụ.

### 6.4. Giới hạn có chủ đích của code minh họa

- `ApparentTimeout` là lỗi giả lập, không phát sinh từ thư viện mạng.
- Không có cơ sở dữ liệu, khóa giao dịch, kết nối thanh toán hoặc tác vụ thực.
- `HashMap` không chống trùng an toàn khi có hai luồng cập nhật đồng thời hoặc hai tiến trình.
- `IdempotentCheckout` không kiểm tra payload khác nhau sử dụng chung `requestId`; hệ thống thật cần phát hiện xung đột nội dung.
- Không có xử lý trạng thái `IN_PROGRESS`, thời hạn khóa, retry ngân sách thời gian hoặc chiến lược đối soát.
- Mã mẫu bắt **duy nhất `ApparentTimeout`** để retry, thay vì bắt mọi lỗi. Điều này minh họa việc **chọn nhóm lỗi** có chủ ý.
- Kết quả `actualCharges` được gọi qua proxy nhưng không thuộc điều kiện retry, do đó không có `ADVICE attempt` cho phương thức này.
- Dữ liệu `cents` không được dùng để chứng minh tính đúng của giao dịch; mục đích là phân tích **số lần hiệu ứng xảy ra**, không xây dựng ứng dụng tài chính.

## 7. Idempotent không có nghĩa “an toàn để retry mọi lỗi”

Đây là một nhầm lẫn dễ gặp. Idempotency giải quyết **tính lặp của cùng yêu cầu logic**, nhưng retry vẫn cần điều kiện và giới hạn.

### 7.1. Phân loại lỗi trước khi thử lại

| Loại tình huống | Gợi ý đánh giá |
| --- | --- |
| Lỗi kết nối thoáng qua trước khi yêu cầu chắc chắn được gửi | Có thể cân nhắc retry nếu hợp đồng cho phép |
| Timeout nhưng không biết máy chủ đã làm xong chưa | Retry chỉ khi có cơ chế phát hiện trùng hoặc đối soát phù hợp |
| Máy chủ báo quá tải tạm thời | Có thể cân nhắc backoff/jitter và giới hạn ngân sách |
| Dữ liệu sai định dạng, vi phạm bất biến | Retry cùng dữ liệu thường không giúp |
| Không có quyền truy cập | Không retry mù quáng để vượt qua chính sách |
| Xung đột idempotency key với payload khác | Cần báo xung đột/đối soát, không tạo hiệu ứng mới |
| Tác vụ đã xác nhận hoàn tất | Thường nên trả trạng thái/kết quả cũ thay vì thực hiện lại |
| Trạng thái xử lý chưa rõ | Có thể cần truy vấn trạng thái hoặc cơ chế hòa giải |

Một ngoại lệ Java đơn lẻ có thể đại diện cho nhiều trạng thái thực tế; phải đọc hợp đồng của dịch vụ và loại hoạt động chứ không chỉ so sánh tên lớp exception.

### 7.2. Retry phải hữu hạn

Một vòng retry không giới hạn có thể chiếm luồng, liên tục tạo tải cho hệ thống đang gặp sự cố và tăng cơ hội lặp hiệu ứng.

Các tham số thường cần quy định rõ:

- **Số lần thử tối đa** (tính gồm lần đầu hay không phải được định nghĩa nhất quán);
- **Tổng thời gian cho phép** (deadline/budget), không chỉ số lần;
- **Khoảng chờ** có thể tăng dần (*exponential backoff*);
- **Jitter** để tránh nhiều client retry đồng loạt;
- **Điều kiện dừng** trên lỗi vĩnh viễn, hủy tác vụ hoặc cạn ngân sách;
- **Điều kiện an toàn khi lặp tác dụng phụ**, bao gồm khóa idempotency;
- **Điều kiện ghi nhận kết quả** khi cuối cùng vẫn không chắc trạng thái hiệu ứng.

Với `attempt <= 2` trong chương trình mẫu, ta thực hiện **tối đa hai lần thử tổng cộng**: lần gốc và một lần thử lại.

### 7.3. Retry có thể làm tăng tải theo cấp số nhân

Giả sử một lời gọi bên ngoài có tối đa 3 lần thử và thao tác bên trong cũng có tối đa 3 lần. Trong trường hợp mọi tầng đều retry các lần thất bại phù hợp, số lần thực thi ở đích **có thể tới 9**, không phải 3.

Nếu một chuỗi dịch vụ có nhiều tầng đều retry, tải tăng rất nhanh vào đúng lúc hạ tầng đang yếu. Cần quyết định tầng nào chịu trách nhiệm retry và chia sẻ ngân sách chung; đừng đặt retry ở mọi nơi chỉ vì around advice làm việc đó dễ dàng.

## 8. Thứ tự aspect làm thay đổi số lần đo và log

Giả sử ta kết hợp một chính sách retry và một chính sách theo dõi:

```text
Retry(Logging(Target))
```

Nếu Retry gọi tiếp 2 lần, phần Logging nằm **bên trong** có thể chạy **hai lần**. Khi đó log thể hiện hai **attempt**; hữu ích để chẩn đoán từng lần thử.

Ngược lại:

```text
Logging(Retry(Target))
```

Logging ở ngoài thường bao quanh **một lời gọi logic** và có thể ghi **một lần** kết quả cuối, trong khi Retry ở trong tự thực hiện hai attempt.

### 8.1. Minh họa thứ tự

```text
Retry(Logging(Target)):
    Retry begins
        Logging attempt 1
        Target attempt 1 -> timeout
        Logging attempt 1 failed
        Logging attempt 2
        Target attempt 2 -> success
        Logging attempt 2 succeeded
    Retry returns success

Logging(Retry(Target)):
    Logging request begins
        Retry attempt 1 -> timeout
        Retry attempt 2 -> success
    Logging request succeeded
```

Đây là **mô hình cấu trúc**, không phải quy tắc ưu tiên mặc định của mọi công nghệ AOP. Nếu advice bên trong thay đổi kết quả, nuốt lỗi hoặc có pointcut không khớp mọi lần, diễn biến có thể khác. Phải kiểm tra thứ tự và số lần thực thi thực tế.

### 8.2. Đếm logical request, attempt và side effect riêng

Ba loại số liệu nên được phân biệt:

- **Logical request:** một ý định nghiệp vụ do người dùng/hệ thống gửi, ví dụ `REQ-1`.
- **Attempt:** số lần chuỗi tiếp tục thực thi đích hoặc phần bên trong.
- **Committed side effect:** số hiệu ứng nghiệp vụ thực sự được xác nhận.

Một request có thể gồm 2 attempts nhưng chỉ 1 effect, hoặc 2 effects nếu không chống trùng. Nếu chỉ nhìn metric “success=1” ở advice ngoài, ta có thể bỏ sót tác dụng phụ thừa. Nên ghi correlation/request ID và attempt ID riêng, trong giới hạn dữ liệu được phép lưu.

## 9. Tương tác với giao dịch

Một around advice có thể tạo ranh giới giao dịch. Khi kết hợp với retry, thứ tự rất quan trọng:

```text
Transaction(Retry(Target))
Retry(Transaction(Target))
```

Ở cấu trúc đầu, nhiều lần thử có thể diễn ra trong **cùng phạm vi giao dịch** nếu cơ chế đó có ý nghĩa như vậy. Ở cấu trúc sau, mỗi lần thử có thể mở **một giao dịch riêng** nếu transaction advice được thực thi lại.

Không nên tuyên bố một trong hai luôn đúng. Tính phù hợp phụ thuộc lỗi cần xử lý, trạng thái giao dịch sau lỗi, khả năng rollback/commit và hệ thống lưu trữ. Một số lỗi làm giao dịch hiện tại không còn phù hợp để tiếp tục; retry trong cùng giao dịch có thể thất bại hoặc sai logic.

Đặc biệt, **giao dịch cơ sở dữ liệu không tự kéo ngược hiệu ứng ở hệ thống bên ngoài** như email, HTTP hoặc thanh toán. Nếu effect ngoài đã hoàn tất rồi giao dịch DB rollback, chỉ gọi lại toàn bộ phương thức vẫn có thể lặp effect ngoài.

### 9.1. Outbox và xử lý lặp ở người nhận

Khi cần phát sự kiện cùng thay đổi dữ liệu, một **transactional outbox** có thể giúp lưu ý định phát sự kiện trong cùng giao dịch cơ sở dữ liệu. Tuy nhiên việc phát lại bản ghi outbox vẫn có thể xảy ra sau lỗi mạng; phía nhận cũng cần xử lý idempotent/deduplicate nếu không muốn áp hiệu ứng hai lần.

Ở đây trọng tâm không phải triển khai outbox, mà là nhớ rằng **retry và truyền sự kiện là hai tầng bảo đảm khác nhau**. Around advice không thể biến toàn bộ mạng phân tán thành một giao dịch nguyên tử chỉ bằng vài lần gọi `proceed`.

## 10. At-most-once, at-least-once và “exactly once”

Có thể dùng các khái niệm giao nhận sau để hiểu hệ quả:

| Khái niệm | Ý nghĩa trực giác | Đánh đổi |
| --- | --- | --- |
| **At-most-once execution/attempt** | Không tự ý lặp thực thi cùng thao tác trong phạm vi được kiểm soát | Có thể mất cơ hội hoàn tất nếu kết quả không chắc chắn |
| **At-least-once attempts/delivery** | Có thể lặp để tăng khả năng yêu cầu được xử lý | Có thể phát sinh thao tác trùng nếu không chống trùng |
| **Effectively-once effect** | Có thể có nhiều lần thử nhưng hệ thống cố bảo đảm một hiệu ứng nghiệp vụ cho một yêu cầu logic | Cần định danh, lưu trạng thái, phối hợp nhất quán và giới hạn rõ |
| **Exactly-once** | Một cam kết rất mạnh, chỉ có ý nghĩa khi xác định rõ phạm vi thao tác, lỗi và mô hình hệ thống | Không được suy ra từ việc gọi `proceed` hoặc có idempotency key đơn giản |

Trong hệ thống phân tán, việc đạt “exactly once” end-to-end trên tất cả hiệu ứng là rất khó và thường phải được diễn đạt dưới phạm vi giới hạn có thể chứng minh. Dùng cụm từ **một hiệu ứng nghiệp vụ theo khóa yêu cầu** sẽ rõ ràng hơn tuyên bố “mọi thứ chạy đúng một lần”.

Ngay cả khi effect chỉ ghi nhận một lần, log **attempt** có thể xuất hiện nhiều lần — điều đó không nhất thiết là lỗi.

## 11. Hủy tác vụ, timeout và bất đồng bộ

Around advice chạy trong một lời gọi đồng bộ có thể thấy một timeout hoặc nhận về đối tượng đại diện cho tác vụ bất đồng bộ. Điều đó không luôn có nghĩa công việc phía dưới đã dừng.

### 11.1. Cancel không đồng nghĩa rollback

Nếu một luồng gửi yêu cầu mạng, sau đó nhận timeout và hủy tác vụ, máy chủ bên kia **có thể vẫn tiếp tục xử lý**. Việc gọi `Future.cancel(...)` hoặc ngắt luồng ở phía client không chứng minh hiệu ứng bên ngoài được hoàn tác.

Nếu around advice muốn retry sau timeout, điều kiện idempotency và đối soát vẫn cần có dù client nghĩ mình đã “cancel” lần trước.

### 11.2. Future trả về chưa phải hoàn tất công việc

Một phương thức có thể nhanh chóng trả `CompletableFuture<Result>` đang pending. Ở ranh giới phương thức đồng bộ, around advice gọi tiếp một lần rồi nhận **future** là một lần return bình thường. Nếu muốn retry khi future thất bại sau này, phải thiết kế ở **ranh giới completion của future**, không đơn thuần bắt ngoại lệ đồng bộ quanh lời gọi trả future.

Cũng cần quyết định mỗi lần retry có tạo một future mới hay chỉ chờ lại cùng future; chờ lại cùng một future thất bại không biến thành lần thực thi mới. Tương tự, vòng đời tài nguyên và bối cảnh truy vết phải gắn với thời gian xử lý thật, tránh đóng quá sớm.

### 11.3. Retry đồng thời có thể làm trùng hiệu ứng

Hai yêu cầu mang cùng idempotency key có thể đến **gần đồng thời**. Nếu cả hai cùng kiểm tra “chưa tồn tại khóa”, rồi cùng tạo hiệu ứng trước khi đánh dấu hoàn tất, chúng vẫn lặp tác dụng phụ.

Một triển khai đúng thường cần thao tác nguyên tử/khóa duy nhất hoặc một mô hình trạng thái `IN_PROGRESS` có phối hợp. Kiểm tra `containsKey` rồi `put` trong một `HashMap` không đủ, kể cả khi mã chạy ổn trong thử nghiệm tuần tự.

## 12. Khi around advice biến đổi đối số hoặc kết quả

Một số mô hình AOP cho phép `proceed` với đối số thay thế. Điều này làm retry phức tạp hơn:

- Nếu **lần thứ hai dùng idempotency key khác**, bên đích có thể coi là yêu cầu mới và tạo effect thứ hai.
- Nếu lần thứ hai **thay số tiền hoặc sản phẩm**, khóa cũ không nên được dùng để che xung đột nội dung.
- Nếu advice trả **fallback** sau khi lần đầu đã commit nhưng timeout, người gọi có thể tưởng thao tác chưa xảy ra và tự phát yêu cầu mới.
- Nếu advice **nuốt lỗi** sau hết retry, telemetry bên ngoài có thể ghi nhận thành công dù thực tế chưa chắc thành công.
- Nếu advice thực hiện lại quanh **chuỗi aspect** có logic kiểm tra quyền, điều kiện hoặc trạng thái có thể thay đổi giữa các lần thử.

Nói ngắn gọn, gọi tiếp nhiều lần phải có hợp đồng rõ về **đối số nào giữ nguyên, điều kiện dừng, loại lỗi và giá trị trả về cuối**.

### 12.1. Không đổi overload chỉ vì thay đối số runtime

Trong Java, phương thức đã chọn theo overload ở điểm gọi không tự trở thành một overload khác chỉ vì around advice đưa vào một đối tượng runtime có kiểu khác. Khả năng thay đối số theo `proceed` phải tôn trọng kiểu/chữ ký và ngữ nghĩa của cơ chế AOP. Nếu cần gọi một thao tác khác, phải thiết kế rõ đó là **fallback/delegation khác**, không giả định retry tự giải lại overload.

## 13. Dọn dẹp tài nguyên qua nhiều attempt

Khi retry, mỗi lần thử có thể:

- Mở kết nối;
- Chiếm khóa;
- Tạo trace span;
- Gắn bối cảnh vào luồng;
- Mở hoặc tham gia giao dịch;
- Đăng ký callback.

Những tài nguyên đó cần được giải phóng theo **đúng phạm vi**.

```text
RetryScope
    Attempt 1: acquire -> proceed -> fail -> cleanup attempt 1
    Attempt 2: acquire -> proceed -> success -> cleanup attempt 2
    RetryScope cleanup
```

Nếu resource advice nằm **bên trong retry**, mỗi attempt thường được tạo và dọn riêng. Nếu resource advice nằm **ngoài retry**, một scope chung bao cả lần thử. Hai cách có thể đều hợp lệ tùy loại tài nguyên; dùng sai phạm vi có thể dẫn tới mở hai lần nhưng đóng một lần, đóng sớm hoặc cố tái sử dụng transaction đã lỗi.

`finally` đảm bảo chạy trên những đường thoát bình thường/ngoại lệ khi phạm vi đã được thiết lập, **không tự đảm bảo tài nguyên được cấp trước khi vào phạm vi ấy sẽ được dọn**. Nếu cleanup tự ném lỗi, nó còn có thể che lỗi gốc. Nên kiểm tra cả lỗi acquire, lỗi proceed và lỗi close.

## 14. Điểm can thiệp, self-invocation và proxy

Một bộ retry được cài bằng proxy sẽ chỉ hoạt động khi lời gọi **đi qua proxy**. Nếu một phương thức nội bộ của đích gọi trực tiếp `this.charge(...)`, nó có thể không qua lớp retry ngoài. Ngược lại, nếu nhiều proxy bao cùng một đối tượng hoặc một phương thức chứa lời gọi tới một proxy khác, retry có thể bị **lồng nhau**.

Với weaving trực tiếp vào mã/bytecode, loại join point và phạm vi có thể khác. Không nên dùng thành công của ví dụ proxy để kết luận mọi cơ chế AOP hỗ trợ method call, method execution, constructor hay field access có cùng hành vi.

**Một pointcut khớp** không đủ chứng minh số lần thao tác: phải ghi nhận đúng đường gọi và thứ tự các advice trong chương trình thực.

### 14.1. Tránh advice tự gọi chính nó

Nếu trong around advice, thay vì tiếp tục chuỗi bên trong, ta gọi lại cùng phương thức **qua chính proxy đang xử lý**, lời gọi có thể lại kích hoạt advice và tạo recursion không giới hạn:

```text
proxy.charge()
  -> aroundAdvice
       -> proxy.charge()
            -> aroundAdvice
                 -> ...
```

Đây không phải retry được kiểm soát. Cần dùng cơ chế tiếp tục chính thức hoặc đường ủy quyền không tái nhập ngoài ý muốn, và đặt giới hạn số lần rõ ràng.

## 15. Thiết kế một chính sách retry trong around advice

Một quy trình thực tế nên đi theo thứ tự:

1. **Viết hợp đồng nghiệp vụ của thao tác đích.** Tác vụ có side effect không? Side effect nằm ở đâu? Tình huống lỗi sau commit có thể xảy ra không?
2. **Chỉ rõ điều kiện đủ để thử lại.** Loại lỗi nào được xem là tạm thời? Có thông tin xác nhận thất bại chắc chắn hay trạng thái không chắc chắn?
3. **Đặt ranh giới chống trùng.** Yêu cầu logic được nhận diện bằng khóa nào? Ai kiểm soát atomicity và thời hạn khóa?
4. **Quy định ngân sách.** Tối đa bao nhiêu attempt, deadline, backoff/jitter, điều kiện hủy?
5. **Chọn vị trí trong chuỗi aspect.** Retry nằm trong hay ngoài transaction, audit, tracing, metrics và resource scope?
6. **Giữ đối số nhất quán.** Cùng logical request phải giữ idempotency key và payload tương thích, hoặc báo lỗi xung đột.
7. **Bảo toàn lỗi và kết quả.** Khi hết retry, lỗi nào đi ra? Có được trả kết quả trạng thái không chắc chắn không? Không vô tình đổi kết quả.
8. **Quan sát đủ ba số liệu.** Logical request, số attempt, số effect thật; không lấy metric thành công thay bằng chứng không có hiệu ứng lặp.
9. **Kiểm thử cả đường bypass và đa luồng.** Pointcut được chọn, proxy/weaving hoạt động, không có retry lồng hoặc race condition.
10. **Có cách đối soát.** Với trạng thái bên ngoài không chắc chắn, cần khả năng truy vấn trạng thái/giao dịch thay vì luôn gửi thêm một thao tác mới.

### 15.1. Giả mã retry có ngân sách rõ

```text
around request:
    key = stableIdentityOfLogicalRequest(request)
    for attempt in 1..maxAttempts:
        if deadlineExpired():
            return/throw according to operation contract
        try:
            return proceedWithSameRequestAndKey()
        catch error:
            if not retryable(error):
                throw error
            if attempt == maxAttempts:
                throw error
            if outcomeAmbiguous(error) and not safelyDeduplicated(key):
                return/throw unknown-outcome state for reconciliation
            backoffWithinDeadline(attempt)
```

Đây là **giả mã thiết kế**, không phải đoạn triển khai chạy độc lập hay lời bảo đảm một bộ AOP hỗ trợ `proceedWithSameRequestAndKey`. `safelyDeduplicated(key)` biểu thị một **hợp đồng an toàn có cơ sở**, không có nghĩa chỉ kiểm tra một biến Boolean ở client là đủ.

Nếu không thể chứng minh lần thử lại an toàn, **không thử lại tự động** thường tốt hơn cố giấu tình trạng không chắc chắn.

## 16. Ma trận kiểm thử cần có

| Kịch bản | Kỳ vọng cần xác minh |
| --- | --- |
| Thành công ở lần đầu | Một lần tiếp tục, một hiệu ứng, kết quả giữ nguyên |
| Lỗi chắc chắn trước khi có effect | Retry nếu hợp đồng cho phép, không phát sinh effect cũ |
| Timeout sau khi effect đã commit | Không tạo hiệu ứng thứ hai cho cùng logical request |
| Lỗi vĩnh viễn | Không retry vô ích |
| Hết số lần thử | Ngừng đúng ngân sách, truyền lỗi/trạng thái phù hợp |
| Hai request khác nhau | Được phép tạo hai effect khi thực sự là hai yêu cầu |
| Cùng khóa, cùng payload | Hiệu ứng không trùng và có kết quả/trạng thái nhất quán |
| Cùng khóa, payload khác | Bị từ chối/xử lý theo quy tắc xung đột |
| Hai lời gọi cùng khóa đồng thời | Chỉ một effect nếu đó là cam kết idempotency |
| Retry ngoài/ trong metrics | Số logical request và số attempt đúng |
| Retry trong/ngoài transaction | Mỗi phạm vi được tạo, kết thúc hoặc rollback đúng |
| Hủy/timeout nhưng bên nhận vẫn chạy | Có đối soát, không coi cancel là rollback |
| Async future thất bại sau khi method trả | Retry ở đúng ranh giới completion, không chỉ ở method return |
| Đường gọi bỏ qua proxy | Phát hiện cơ chế không chạy thay vì coi là không cần retry |
| Có nhiều around advice | Thứ tự và số lần thực thi advice bên trong đúng |
| Cleanup ném lỗi | Không vô tình che lỗi chính nếu hợp đồng cần giữ nó |

### 16.1. Chỉ test kết quả trả về sẽ bỏ sót lặp effect

Một test như `assertEquals("RECEIPT-2", charge(...))` có thể **đạt** trong trường hợp không chống trùng nhưng vẫn có hai khoản thu. Cần kiểm tra thêm bộ đếm effect, số bản ghi, số sự kiện thực tế hoặc trạng thái của hệ thống lưu trữ.

Nếu là thanh toán, hãy kiểm thử dựa trên **biên bản giao dịch được xác nhận** trong môi trường thử nghiệm, không chỉ một thông báo thành công ở phía client.

## 17. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Gọi `proceed` hai lần vì muốn đo độ ổn định | Có thể làm lại toàn bộ nghiệp vụ | Dùng một lần chuyển tiếp cho monitoring thông thường |
| Retry mọi `Exception` | Retry cả lỗi vĩnh viễn/bất biến | Chỉ chọn lỗi có hợp đồng retry rõ |
| Cho rằng timeout là chưa thực hiện | Effect có thể đã commit trước timeout | Dùng idempotency/đối soát |
| Tạo key mới cho mỗi attempt | Bên nhận coi là yêu cầu mới | Giữ cùng key cho cùng logical request |
| Chỉ deduplicate trong bộ nhớ client | Không chịu được restart/đa instance | Chống trùng ở nơi sở hữu effect với phối hợp bền vững |
| Kiểm tra key rồi ghi effect không nguyên tử | Hai luồng có thể cùng thấy key chưa tồn tại | Ràng buộc duy nhất/atomic state hoặc giao thức tương đương |
| Tin transaction DB tự rollback cả email/HTTP | Tác dụng phụ ngoài transaction không được hoàn tác | Thiết kế outbox/đối soát/dedup ở ranh giới phù hợp |
| Không giới hạn retry | Tăng tải, treo yêu cầu, lặp effect | Max attempts, deadline, backoff/jitter |
| Hai tầng cùng retry độc lập | Số attempt nhân lên | Thống nhất tầng chịu trách nhiệm và ngân sách |
| Đặt metrics ở ngoài retry rồi gọi một lần là một attempt | Bỏ sót các lần thử bên trong | Tách metric request và attempt |
| Catch rồi nuốt lỗi ở attempt cuối | Người gọi nhận trạng thái sai | Giữ lỗi/unknown state đúng hợp đồng |
| Dùng `finally` sai vòng đời | Rò rỉ hoặc đóng tài nguyên quá sớm | Dọn mỗi scope theo ownership, gồm nhánh lỗi |
| Tự gọi proxy từ advice thay vì tiếp tục chuỗi | Dễ lặp đệ quy không giới hạn | Dùng cơ chế proceed/delegation đúng |
| Bắt lỗi đồng bộ cho future rồi tưởng bắt được lỗi async | Future có thể thất bại sau khi phương thức đã return | Gắn xử lý vào completion thật |
| Chỉ nhìn số lần gọi API mà không nhìn effect | Không phát hiện double charge | Kiểm tra trạng thái xác nhận nghiệp vụ |

## 18. Bài tập vận dụng và đáp án

### Bài 1 — Tác dụng phụ lặp

Một thao tác `sendWelcomeEmail(userId)` được bao bởi around advice retry tối đa ba lần khi timeout. Lần đầu thư đã gửi nhưng phản hồi xác nhận bị mất. Điều gì có thể xảy ra?

**Đáp án:** Lần thử lại có thể gửi thêm email cùng nội dung. Timeout không chứng minh email chưa gửi. Cần khóa yêu cầu hoặc cơ chế gửi chống trùng, và phải phân biệt yêu cầu gửi email **một lần** với các attempt kỹ thuật.

### Bài 2 — Chọn thứ tự aspect

Bạn muốn đo **tổng thời gian** cả chuỗi retry nhưng vẫn muốn biết **độ trễ từng attempt**. Nên đặt hai lớp đo ở đâu?

**Đáp án:** Có thể đặt đo tổng bao ngoài `Retry`, và đo từng attempt ở bên trong: `TotalTimer(Retry(AttemptTimer(Target)))`. Cần xác minh thứ tự/precedence thực tế của công nghệ và tránh suy luận đây là thứ tự mặc định.

### Bài 3 — Timeout sau commit

Một request có idempotency key `K1` đã tạo khoản thu, nhưng client mất kết nối. Retry với key `K2` có bảo đảm tránh thu lặp không?

**Đáp án:** Không. Nếu máy chủ coi `K2` là logical request mới, nó có thể tạo khoản thu thứ hai. Cần giữ `K1` cho cùng ý định nghiệp vụ và có cơ chế xử lý key ở phía chịu trách nhiệm effect.

### Bài 4 — Hai luồng cùng key

Hai luồng cùng kiểm tra `!map.containsKey(key)`, cùng nhận `true`, rồi cùng gọi API tạo đơn trước khi `put(key,...)`. Đã đạt idempotency chưa?

**Đáp án:** Chưa. Check-then-act không nguyên tử tạo race condition. Cần bước đăng ký trạng thái/khóa duy nhất có tính atomic trước hoặc trong ranh giới xử lý effect và chính sách cho yêu cầu đang được xử lý.

### Bài 5 — Retry và lỗi nghiệp vụ

Một hàm từ chối đặt hàng vì số lượng âm bằng `IllegalArgumentException`. Around advice bắt mọi `RuntimeException` rồi gọi `proceed` tiếp. Có hữu ích không?

**Đáp án:** Thường không: dữ liệu âm không tự thành hợp lệ khi chạy lại. Retry gây thêm tải và có thể che nguyên nhân thật. Chỉ retry các lỗi tạm thời có điều kiện và hợp đồng an toàn phù hợp.

### Bài 6 — Số lần chạy advice

Cho cấu trúc `A(Retry(B(Target)))`. Retry thử hai lần. Giả sử A và B đều được áp đúng điểm và B bao quanh mỗi attempt. Mỗi advice chạy bao nhiêu lần?

**Đáp án:** A bao toàn bộ yêu cầu nên thường có **một lần kích hoạt**; B nằm trong Retry nên có **hai lần kích hoạt** nếu mỗi attempt tiếp tục qua B. Đó là kết quả của **cấu trúc lồng giả định**, không phải thứ tự mặc định mọi công cụ.

### Bài 7 — Future và retry

Một around advice đồng bộ gọi `proceed` rồi nhận `CompletableFuture`. Future hoàn tất ngoại lệ sau vài giây. Khối `catch` quanh `proceed` có tự bắt lỗi completion đó không?

**Đáp án:** Không. Phương thức đã trả về future bình thường; lỗi xuất hiện sau trong tác vụ bất đồng bộ. Cần xử lý tại ranh giới completion và làm rõ tạo tác vụ mới hay chỉ chờ future cũ, đồng thời giữ tính an toàn của side effect.

### Bài 8 — Chứng minh một hiệu ứng

Một bài test thấy around advice in một dòng `SUCCESS` sau lần retry thứ hai. Có thể khẳng định chỉ một hiệu ứng đã xảy ra không?

**Đáp án:** Không. Ví dụ Java của bài cho thấy người gọi có thể nhận kết quả thành công sau hai lần ghi. Phải kiểm tra trạng thái nghiệp vụ xác nhận, số hiệu ứng, khóa chống trùng và các đường lỗi trước/sau khi commit.

## 19. Ghi nhớ

- **Around advice có thể điều phối việc tiếp tục**, nhưng khả năng gọi `proceed` 0/1/nhiều lần là **phụ thuộc cơ chế AOP**.
- **Mỗi lần tiếp tục có thể chạy lại cả chuỗi advice bên trong và thao tác đích**, nên có thể lặp log, giao dịch và tác dụng phụ.
- **Timeout/ngoại lệ không chứng minh thao tác chưa tạo hiệu ứng.** Lỗi sau commit là lý do retry mù quáng rất nguy hiểm.
- **Idempotency** dùng để giữ một hiệu ứng logic dù có nhiều attempt; chỉ dùng cùng khóa là chưa đủ nếu không có kiểm soát nguyên tử/bền vững tại nơi sở hữu hiệu ứng.
- **Retry phải có giới hạn và điều kiện**: lỗi được phép, ngân sách, deadline, backoff/jitter, an toàn chống trùng và đối soát.
- **Thứ tự aspect quyết định số lần advice chạy và phạm vi tài nguyên/giao dịch**; đo request và attempt là hai nhiệm vụ khác nhau.
- Với async và hệ phân tán, phải xét **khi nào effect thực sự hoàn tất**, không chỉ khi phương thức hoặc future được tạo trả về.
- Với advice chỉ quan sát, mặc định an toàn là **chuyển tiếp một lần**, bảo toàn kết quả, ngoại lệ và số lần thực thi nghiệp vụ.
