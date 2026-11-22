# Lập trình hướng khía cạnh (AOP) là gì?

**Aspect-Oriented Programming (AOP)**, hay *lập trình hướng khía cạnh*, là cách tổ chức phần mềm để gom và áp dụng những hành vi xuất hiện ở nhiều nơi — chẳng hạn ghi log, đo thời gian, kiểm tra quyền truy cập, theo dõi lỗi — quanh các điểm thực thi được chọn. Những hành vi ấy thường được gọi là **mối quan tâm xuyên suốt** (*cross-cutting concerns*). AOP bổ sung cho cách tổ chức chương trình theo lớp, đối tượng và hàm; mục tiêu là giữ logic nghiệp vụ dễ đọc, đồng thời làm cho quy tắc chung nhất quán và có nơi quản lý rõ ràng.

Một cách hình dung: phương thức `transferMoney()` chịu trách nhiệm chuyển tiền. Việc ghi nhận thời gian chạy hoặc lưu vết một yêu cầu có thể cần thiết nhưng không tạo nên nghiệp vụ “chuyển tiền”. Thay vì sao chép mã ghi log vào mọi phương thức, ta định nghĩa quy tắc “bao quanh các lần thực thi đã chọn” để hệ thống tự áp dụng hành vi chung.

> **Phân biệt ngay từ đầu:** AOP là một mô hình lập trình; không đồng nghĩa với một thư viện, một cơ chế chặn lời gọi, hay một cú pháp cụ thể. Khả năng chặn những điểm thực thi nào, và thời điểm kết hợp mã AOP vào chương trình, phụ thuộc công cụ triển khai.

## 1. Vì sao AOP xuất hiện?

Giả sử ứng dụng có các nghiệp vụ tạo đơn hàng, thanh toán và tìm kiếm. Cả ba đều cần ghi log thời gian xử lý:

```java
// Mã minh họa: phần ghi thời gian bị lặp trong nhiều phương thức.
long start = System.nanoTime();
try {
    return executeBusinessOperation();
} finally {
    long elapsedNanos = System.nanoTime() - start;
    recordDuration(elapsedNanos);
}
```

Nếu viết đoạn này trong hàng chục phương thức, một thay đổi về định dạng log, chính sách loại trừ dữ liệu nhạy cảm hoặc cách tính số liệu buộc ta sửa nhiều chỗ. Cấu trúc code sẽ có hai lớp trách nhiệm đan vào nhau: **làm việc nghiệp vụ** và **thực hiện chính sách kỹ thuật dùng chung**.

Hai triệu chứng điển hình:

- **Scattering (phân tán):** cùng một quan tâm xuất hiện ở nhiều lớp hoặc phương thức.
- **Tangling (đan xen):** một phương thức chứa cả nghiệp vụ và nhiều xử lý phụ trợ, làm khó hiểu luồng chính.

AOP giải quyết chúng bằng cách mô tả “làm gì” và “làm ở đâu” tương đối độc lập. Ví dụ: “trước và sau khi chạy các phương thức xử lý đơn hàng, ghi mốc thời gian và kết quả”. Việc kết hợp hai phần này được gọi là *weaving*.

Tuy vậy, **không phải mọi đoạn mã dùng lại nhiều lần đều nên thành aspect**. Phép tính giá, thuật toán xác thực chữ ký hoặc quy tắc nghiệp vụ có đầu vào/đầu ra rõ ràng thường phù hợp với hàm, lớp, đối tượng dịch vụ hay thành phần được gọi tường minh. AOP có ích nhất khi hành vi cần bám theo *ranh giới thực thi* của nhiều vị trí.

## 2. Mối quan hệ giữa OOP và AOP

**Lập trình hướng đối tượng (OOP)** tổ chức dữ liệu và hành vi theo các đối tượng, trách nhiệm và mối quan hệ. Ví dụ, `OrderService` chứa quy trình đặt hàng và `OrderRepository` lưu dữ liệu đơn hàng. Điều này vẫn là nền tảng thiết kế.

**AOP** cung cấp thêm một cách mô-đun hóa theo *quy tắc áp dụng xuyên qua nhiều đối tượng*. Một aspect về đo thời gian có thể tác động lên các phương thức được chọn từ nhiều lớp. AOP không làm biến mất các lớp nghiệp vụ và cũng không thay thế interface, composition hay dependency injection.

| Câu hỏi | Tổ chức thông thường | Tổ chức theo AOP |
| --- | --- | --- |
| “Phần mềm thực hiện nghiệp vụ gì?” | Phương thức/lớp thực hiện nghiệp vụ | Vẫn do phương thức/lớp thực hiện |
| “Tất cả thao tác này cần ghi log như thế nào?” | Từng nơi gọi hàm ghi log hoặc wrapper | Aspect chọn điểm áp dụng và gắn lời khuyên |
| “Luồng chạy có nhìn thấy toàn bộ trong mã nghiệp vụ?” | Thường tường minh hơn | Có thể bị bổ sung hành vi bên ngoài |
| “Tác động ở vị trí nào?” | Vị trí gọi hàm trực tiếp | Do tập điểm thực thi được chọn quyết định |

Đổi lại khả năng tách biệt, AOP có chi phí về **khả năng quan sát luồng điều khiển**: đọc riêng một phương thức có thể chưa thấy tất cả công việc diễn ra trước, sau hoặc quanh phương thức đó. Bởi vậy aspect cần có phạm vi rõ, tên dễ hiểu và cách kiểm chứng được.

## 3. Sáu thuật ngữ cốt lõi

### 3.1. Join point — điểm có thể tham gia

**Join point** là một sự kiện/vị trí được mô hình AOP cho phép tác động: thường gặp nhất là *thực thi phương thức*. Tùy công cụ, nó còn có thể là *lời gọi phương thức*, khởi tạo đối tượng, truy cập trường dữ liệu, bắt ngoại lệ hoặc các điểm khác.

Ví dụ, việc đi vào thân `PaymentService.pay()` có thể là một join point kiểu **method execution**. Trong một số mô hình, vị trí mã thực hiện lệnh `paymentService.pay()` cũng có thể là một join point kiểu **method call**. Hai khái niệm này khác nhau: execution thuộc lần chạy của phương thức; call thuộc chỗ phát sinh lời gọi. Không phải công cụ AOP nào cũng hỗ trợ cả hai.

### 3.2. Pointcut — quy tắc chọn join point

**Pointcut** mô tả tập join point mà aspect cần xử lý. Một pointcut có thể dựa vào tên, kiểu, chữ ký, annotation, phạm vi package hoặc điều kiện thực thi; mức hỗ trợ phụ thuộc kỹ thuật weaving.

Ví dụ ở mức ý tưởng:

- Chọn các lần thực thi phương thức công khai thuộc nhóm thao tác thanh toán.
- Chọn những phương thức được đánh dấu bằng annotation `@Audited`.
- Chọn các thao tác có ngữ cảnh yêu cầu hợp lệ để thu thập trace.

**Pointcut là bộ lọc; join point là một điểm thực thi cụ thể.** Cú pháp `execution(...)` hoặc các biểu thức tương tự là cú pháp của từng công cụ, không phải cú pháp bắt buộc của toàn bộ AOP.

### 3.3. Advice — hành vi bổ sung

**Advice** là đoạn xử lý chạy liên quan đến join point đã chọn. Các loại phổ biến:

| Loại advice | Thời điểm/ý nghĩa |
| --- | --- |
| **Before** | Chạy trước thao tác được chọn. |
| **After returning** | Chạy khi thao tác hoàn thành bình thường; có thể xem kết quả nếu công cụ hỗ trợ. |
| **After throwing** | Chạy khi thao tác kết thúc bằng ngoại lệ; phạm vi loại ngoại lệ bắt được tùy công cụ. |
| **After/finally** | Chạy khi rời thao tác, dù bình thường hay có ngoại lệ. |
| **Around** | Bao quanh thao tác, có thể chủ động quyết định khi nào tiếp tục, có gọi tiếp hay không, và kết quả/ngoại lệ trả ra. |

Cần phân biệt **after returning** với **finally**: một lời gọi ném lỗi sẽ không đi qua nhánh “trả về bình thường”, nhưng vẫn có thể đi qua phần dọn dẹp “finally”.

### 3.4. Aspect — đơn vị đóng gói quy tắc

Một **aspect** thường kết hợp pointcut với một hoặc nhiều advice để thể hiện một quan tâm xuyên suốt, ví dụ `ExecutionTiming` hoặc `AuditTrail`. Nó là đơn vị tổ chức mã/khai báo, không nhất thiết là kiểu class đặc biệt trong mọi triển khai.

### 3.5. Target — đối tượng/thao tác đích

**Target** là phần chương trình gốc mà advice được áp dụng lên. Nếu một proxy đứng trước `InventoryService`, service thật thường là target; proxy đóng vai trò trung gian chuyển tiếp lời gọi. Khi weaving ở mức bytecode, có thể không tồn tại một đối tượng proxy độc lập.

### 3.6. Weaving — kết hợp hành vi

**Weaving** là quá trình gắn advice vào các join point được chọn. Có thể hình dung:

```text
Người gọi
   |
   v
Điểm thực thi được chọn
   |
   +--> Advice trước
   |
   +--> Logic nghiệp vụ gốc
   |
   +--> Advice sau / xử lý lỗi / dọn dẹp
   |
   v
Kết quả hoặc ngoại lệ quay về người gọi
```

Sơ đồ chỉ là trường hợp đơn giản. Với **around advice**, logic nghiệp vụ có thể không chạy, chạy một lần, hoặc (nếu thiết kế cho phép) được gọi nhiều lần; các thành phần có thể được lồng nhau và thay đổi thứ tự thực tế.

## 4. AOP vận hành như thế nào?

Một đường đi phổ biến khi có nhiều advice:

1. Chương trình đi đến một join point, chẳng hạn gọi một thao tác của đối tượng.
2. Cơ chế AOP xác định join point này có khớp pointcut hay không.
3. Các advice áp dụng được xếp thành chuỗi theo quy tắc thứ tự của hệ thống.
4. Advice ở phía ngoài thực thi phần **before**, sau đó chuyển tiếp vào thành phần kế tiếp hoặc nghiệp vụ gốc.
5. Khi thành phần bên trong hoàn tất, phần **after returning**, **after throwing** hoặc **finally** được thực thi tương ứng.
6. Người gọi nhận kết quả cuối cùng hoặc ngoại lệ đã được chuyển tiếp/biến đổi.

Ví dụ một chuỗi lồng nhau:

```text
Caller
  -> Audit around: bắt đầu
      -> Timing around: bắt đầu
          -> Business operation
      <- Timing around: kết thúc
  <- Audit around: kết thúc
Caller nhận kết quả
```

Ở đây `Audit` và `Timing` cùng áp dụng lên một thao tác. Vì advice có thể lồng nhau, **thứ tự quyết định** việc đo thời gian bao gồm hay không bao gồm chi phí ghi audit. Không có một thứ tự advice phổ quát áp dụng cho mọi thư viện; phải xem quy tắc precedence/order của cơ chế đang dùng.

### Ví dụ nghiệp vụ: đo thời gian một thao tác

Tưởng tượng `calculateQuote()` chỉ quan tâm công thức tính báo giá. Một aspect đo thời gian có thể:

- Ghi mốc `System.nanoTime()` ngay trước khi chuyển tiếp thao tác.
- Cho phép thao tác chạy và giữ nguyên giá trị trả về.
- Trong nhánh `finally`, tính độ dài khoảng thời gian bằng nanosecond.
- Gửi metric với tên thao tác đã được chuẩn hóa và thông tin ngữ cảnh cho phép.

**Vì sao dùng `System.nanoTime()`?** Đây là đồng hồ phù hợp để đo khoảng thời gian đã trôi qua trong cùng tiến trình; không sử dụng để suy ra giờ lịch hoặc dấu thời gian UTC. Đo “toàn bộ lời gọi” cũng không đồng nghĩa “chỉ thời gian CPU”, và metric tổng thể có thể bao gồm thời gian chờ I/O hoặc xử lý của advice khác.

## 5. Những cách triển khai AOP

AOP là ý tưởng; mỗi kỹ thuật triển khai đánh đổi phạm vi join point, thời điểm can thiệp và chi phí vận hành.

| Kỹ thuật | Diễn ra lúc nào? | Đặc trưng |
| --- | --- | --- |
| **Compile-time weaving** | Khi biên dịch | Kết hợp advice vào mã đầu ra; có thể tác động ở nhiều vị trí theo công cụ biên dịch. |
| **Post-compile/binary weaving** | Sau khi đã có bytecode, trước khi chạy | Biến đổi artifact đã biên dịch; cần quản lý tương thích bản build. |
| **Load-time weaving** | Khi JVM nạp class | Có thể dùng bộ biến đổi bytecode/class loader/agent; cần bảo đảm quy tắc nạp lớp và cấu hình nhất quán. |
| **Runtime proxy/interception** | Khi lời gọi đi qua lớp trung gian lúc chạy | Dễ hình dung; chỉ bắt được các lời gọi thực sự đi qua điểm trung gian đó. |

### 5.1. Proxy và giới hạn của nó

Một **proxy** là đối tượng nhận lời gọi thay cho target, thực hiện hành vi bổ sung rồi chuyển tiếp. Trong Java, `java.lang.reflect.Proxy` tạo proxy động dựa trên **interface**. Nếu đối tượng gọi trực tiếp target hoặc một phương thức khác gọi nội bộ qua `this` mà không quay qua proxy, interceptor bên ngoài có thể không được kích hoạt.

Ví dụ:

```text
caller -> proxy -> target.publicOperation()    [được trung gian quan sát]

caller -> target.publicOperation()             [bỏ qua proxy]

target.publicOperation() -> this.helper()      [lời gọi nội bộ không quay qua proxy]
```

Với dynamic proxy dựa trên interface, chỉ những phương thức của giao diện proxy được gọi qua proxy mới đi vào handler. Cách tạo lớp con trung gian có giới hạn khác, chẳng hạn không thể override một phương thức `final`. Weaving ở mức bytecode có thể bao phủ nhiều tình huống hơn, nhưng không mặc nhiên hỗ trợ mọi join point hay miễn phí về hiệu năng.

**Bài học thiết kế:** không kết luận “đã khai báo aspect” là “mọi lời gọi liên quan đều bị chặn”. Phải hiểu cơ chế kết hợp và đường gọi thực tế.

### 5.2. Interception và instrumentation khác nhau thế nào?

- **Interception** tập trung vào việc chặn/chuyển tiếp lời gọi tại một ranh giới; proxy là một cách làm.
- **Instrumentation** là bổ sung mã/quan sát vào chương trình, có thể bằng bytecode transformation hoặc các cơ chế khác.
- **AOP** là mô hình biểu diễn các mối quan tâm và điểm áp dụng. Một công cụ AOP có thể dùng interception hoặc instrumentation để hiện thực.

Ba khái niệm có liên hệ nhưng không đồng nghĩa.

## 6. Ví dụ Java 17+ chạy được: AOP tối giản bằng dynamic proxy

Ví dụ dưới đây tự xây một lớp advice quanh lời gọi phương thức bằng API chuẩn Java. Nó **minh họa Before, After returning, After throwing và Finally**. Đây là một cách thực hiện interception nhỏ gọn; chưa phải một ngôn ngữ pointcut hay công cụ weaving hoàn chỉnh.

Lưu thành tệp `AopBasicsDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AopBasicsDemo {
    public interface GreetingService {
        String greet(String name);
        void reject();
    }

    public static class GreetingServiceImpl implements GreetingService {
        @Override
        public String greet(String name) {
            return "Xin chào, " + name;
        }

        @Override
        public void reject() {
            throw new IllegalArgumentException("Từ chối thao tác");
        }
    }

    public static void main(String[] args) {
        GreetingService target = new GreetingServiceImpl();

        GreetingService service = (GreetingService) Proxy.newProxyInstance(
                GreetingService.class.getClassLoader(),
                new Class<?>[]{GreetingService.class},
                (proxy, method, arguments) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return callTarget(method, target, arguments);
                    }

                    System.out.println("[before] " + method.getName());
                    try {
                        Object result = callTarget(method, target, arguments);
                        System.out.println("[after-returning] " + method.getName());
                        return result;
                    } catch (Throwable error) {
                        System.out.println("[after-throwing] " + method.getName());
                        throw error;
                    } finally {
                        System.out.println("[finally] " + method.getName());
                    }
                });

        System.out.println(service.greet("Lan"));

        try {
            service.reject();
        } catch (IllegalArgumentException error) {
            System.out.println("[caller] " + error.getMessage());
        }
    }

    private static Object callTarget(
            Method method, Object target, Object[] arguments) throws Throwable {
        try {
            return method.invoke(target, arguments);
        } catch (InvocationTargetException error) {
            throw error.getCause();
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp (terminal lưu tệp bằng UTF-8):

```bash
javac -encoding UTF-8 AopBasicsDemo.java
java AopBasicsDemo
```

Kết quả chuẩn:

```text
[before] greet
[after-returning] greet
[finally] greet
Xin chào, Lan
[before] reject
[after-throwing] reject
[finally] reject
[caller] Từ chối thao tác
```

Giải thích từng điểm:

1. `GreetingServiceImpl` là **target** chứa nghiệp vụ thật.
2. Đối tượng do `Proxy.newProxyInstance(...)` trả về là **proxy** triển khai interface `GreetingService`; người gọi làm việc với proxy.
3. `InvocationHandler` đóng vai trò **around interceptor**: in dòng before, gọi phương thức gốc, xử lý hai kết thúc thành công/thất bại rồi chạy finally.
4. `Method.invoke(...)` bọc ngoại lệ ném từ phương thức đích trong `InvocationTargetException`. `callTarget` mở lớp bọc để người gọi nhận lại `IllegalArgumentException` ban đầu.
5. `method.getDeclaringClass() == Object.class` tránh gắn log demo vào các lời gọi `Object` như `toString()`. Trong hệ thống thực, cách xử lý `equals`/`hashCode`/`toString` phải được thiết kế nhất quán.

Ví dụ cố ý áp dụng handler cho mọi phương thức interface, tức **pointcut rất rộng**. Một ứng dụng thực tế có thể kiểm tra metadata của `method` để chỉ xử lý tập phương thức cần thiết. **Không suy ra** rằng mọi công cụ AOP dùng reflection, và ví dụ không minh họa weaving vào lời gọi nội bộ hoặc truy cập trường.

## 7. Thiết kế pointcut sao cho đúng phạm vi

Pointcut tốt phải đủ ổn định khi mã được tái cấu trúc. Một số chiến lược:

- **Theo chữ ký hoặc kiểu:** phù hợp khi các thao tác được chọn có một giao diện/contract rõ ràng. Cần chú ý overload và phương thức được kế thừa.
- **Theo annotation:** dễ diễn đạt ý định như “thao tác này cần audit”; nhưng phải quy định annotation có hiệu lực ở đâu, có được kế thừa không và công cụ đọc annotation trên interface hay implementation.
- **Theo package/module:** thuận tiện cho chính sách phủ rộng, nhưng dễ kéo cả phương thức không mong muốn vào phạm vi khi tổ chức package thay đổi.
- **Theo điều kiện tại thời điểm chạy:** có thể cần để xét đối số, trạng thái hoặc ngữ cảnh; tốn chi phí đánh giá và phải kiểm soát tính nhất quán khi chạy song song.

Điểm cần kiểm tra là **khớp thừa** (*false positive*, advice chạy ở nơi không cần) và **khớp thiếu** (*false negative*, nơi cần nhưng không có advice). Tên phương thức chỉ là một tín hiệu; việc đặt tên lại có thể vô tình phá quy tắc nếu pointcut phụ thuộc vào tên.

Một cách kiểm thử hữu ích: lập bảng các phương thức *phải* được áp dụng và *không được* áp dụng, gọi qua đúng đường đi thực tế, rồi xác minh advice có/không chạy tương ứng.

## 8. Mức nâng cao: around advice và chuỗi advice

**Around advice** có sức mạnh lớn vì nó kiểm soát việc tiếp tục thao tác. Pseudocode sau mô tả mô hình chung, **không phải mã Java độc lập**:

```text
around(joinPoint):
    begin = monotonicClock()
    try:
        result = proceed(joinPoint)
        return result
    finally:
        recordDuration(monotonicClock() - begin)
```

Lệnh `proceed` là khái niệm “đi tiếp tới advice bên trong hoặc thao tác gốc”. Tên hàm/cú pháp thay đổi theo công cụ. Nếu không gọi `proceed`, nghiệp vụ có thể không chạy; nếu gọi hai lần, nghiệp vụ có thể thực thi hai lần. Điều đó đặc biệt nguy hiểm với thanh toán, ghi dữ liệu, gửi thông báo và những thao tác có tác dụng phụ.

**Thứ tự và nesting.** Cho hai advice `A` và `B` đều bao quanh `operation`:

```text
A.before
  B.before
    operation
  B.after
A.after
```

Đây là cấu trúc ngăn xếp: phần vào đi từ ngoài vào trong; phần ra đi ngược lại. Nếu `B` ném ngoại lệ, `A` chỉ chạy phần xử lý phù hợp với ngoại lệ/`finally`, không tự động chạy “after returning”.

**Biến đổi kết quả và lỗi.** Một around advice có thể thay thế kết quả, ánh xạ ngoại lệ, chặn thao tác hoặc thử lại. Nhưng quyền kỹ thuật không đồng nghĩa hành vi ấy luôn đúng. Chẳng hạn, retry một thao tác không idempotent có thể tạo tác dụng phụ trùng lặp. Khi một aspect thay đổi semantics của nghiệp vụ, contract phải mô tả rõ để người dùng API và người viết test biết điều gì có thể xảy ra.

**Tái nhập và đệ quy.** Nếu advice ghi log thông qua một phương thức cũng khớp chính pointcut của nó, hệ thống có thể ghi log lặp vô hạn. Thiết kế có thể giới hạn phạm vi pointcut, loại trừ thành phần hạ tầng của advice, hoặc kiểm soát guard theo ngữ cảnh. Tránh dùng biến static chung để đánh dấu “đang chạy” trong môi trường đa luồng.

## 9. Những mối quan tâm phù hợp với AOP

### 9.1. Logging, tracing và metrics

Aspect có thể tạo một luồng quan sát nhất quán: tên thao tác, trạng thái thành công/thất bại, thời gian chạy và mã tương quan. Tuy nhiên:

- Không tự động ghi toàn bộ đối số hoặc giá trị trả về: chúng có thể chứa mật khẩu, token hoặc dữ liệu cá nhân.
- Không đưa giá trị có số lượng khác biệt không giới hạn (như ID từng đơn hàng) vào nhãn metric, vì có thể tạo **cardinality** rất lớn.
- Thời gian đo tại ranh giới aspect là thời gian quan sát được từ ranh giới đó; chưa hẳn phản ánh riêng thời gian xử lý lõi.
- Khi chuyển luồng hoặc chạy bất đồng bộ, ngữ cảnh trace có thể cần được truyền rõ ràng; dữ liệu gắn với thread không luôn đi theo công việc.

### 9.2. Kiểm soát quyền truy cập

Advice có thể kiểm tra chính sách trước khi cho phép một thao tác tiếp tục. Tuy nhiên, **ranh giới bảo mật phải thật sự bao phủ mọi đường truy cập**. Nếu có đường gọi bỏ qua proxy hoặc một endpoint không khớp pointcut, kiểm tra quyền chỉ đặt ở aspect có thể bị né tránh. Những điều kiện bảo mật cốt lõi cần được áp dụng tại điểm tin cậy phù hợp và được kiểm thử theo các đường gọi thực tế.

### 9.3. Quản lý tài nguyên, giao dịch và retry

Các bước mở/đóng ngữ cảnh, đo thời gian, thực hiện chính sách giao dịch hoặc retry có thể được bao quanh thao tác. Cần xác định chính xác **phạm vi commit/rollback**, điều kiện lỗi, idempotency, thời hạn chờ và hành vi khi hủy tác vụ. Không mặc định rằng “đặt advice trước/sau” tự bảo đảm tính nguyên tử giao dịch hay thu hồi tài nguyên đúng trong mọi trường hợp.

### 9.4. Audit và tuân thủ

Audit ghi nhận *ai thực hiện thao tác nào, khi nào, kết quả gì* ở ranh giới được chọn. Audit khác log chẩn đoán: có thể cần tính toàn vẹn, truy vết và quy tắc lưu giữ riêng. Nếu audit là yêu cầu bắt buộc, phải cân nhắc điều gì xảy ra khi ghi audit thất bại và liệu nghiệp vụ có được phép hoàn tất hay không.

## 10. Các giới hạn và lỗi thường gặp

1. **Cho rằng mọi phương thức đều là join point.** Tập join point phụ thuộc cơ chế triển khai; proxy dựa trên interface khác weaving bytecode.
2. **Gọi thẳng target nên bỏ qua advice.** Khi dùng proxy, lời gọi phải đi qua proxy. Lời gọi nội bộ qua `this` cũng có thể bỏ qua interceptor.
3. **Dùng pointcut quá rộng.** Phương thức không liên quan bị ghi log, bị đo hoặc bị thay đổi hành vi, gây nhiễu và hao tài nguyên.
4. **Giấu quy tắc nghiệp vụ cốt lõi vào aspect.** Người bảo trì không nhìn thấy điều kiện thiết yếu ngay ở nơi sử dụng; behavior trở nên khó dự đoán.
5. **Bắt và nuốt ngoại lệ.** Advice khiến API báo thành công giả hoặc làm mất stack trace. Chỉ biến đổi ngoại lệ khi đó là contract có chủ đích.
6. **Dùng around advice nhưng quên tiếp tục.** Nghiệp vụ không chạy hoặc chạy nhiều lần; đặc biệt nguy hiểm với thao tác có tác dụng phụ.
7. **Bỏ qua precedence.** Hai advice thay đổi cách đo thời gian, ngữ cảnh bảo mật hoặc transaction boundary, tạo kết quả khác nhau dù cùng pointcut.
8. **Ghi dữ liệu nhạy cảm vào log.** AOP làm logging phủ rộng nên tác hại của một chính sách ghi dữ liệu sai cũng lan rộng.
9. **Lạm dụng reflection/đánh giá điều kiện động.** Advice chạy trên đường nóng có thể làm tăng độ trễ đáng kể; cần đo trên tải thực.
10. **Không kiểm thử hành vi khi lỗi và chạy đồng thời.** Một aspect “đúng lúc thành công” có thể rò ngữ cảnh, bỏ dọn dẹp hoặc làm sai số liệu khi có ngoại lệ và nhiều luồng.

## 11. Khi nào nên và không nên dùng AOP?

**Nên cân nhắc AOP** khi một chính sách thật sự xuyên qua nhiều thành phần, có ranh giới áp dụng rõ, có thể biểu diễn bằng pointcut ổn định, và lợi ích từ việc quản lý tập trung lớn hơn chi phí hiểu luồng chạy. Ví dụ điển hình: đo thời gian cho một nhóm API, thống nhất audit ở ranh giới dịch vụ, hay thu thập trace ở điểm ra/vào.

**Ưu tiên lời gọi tường minh hoặc composition** khi hành vi là bước nghiệp vụ quan trọng, thứ tự thực hiện phải hiển thị ngay trong mã, hoặc quyết định cần được kiểm soát riêng theo từng trường hợp. Một wrapper/decorator bình thường đôi khi đủ để tái sử dụng code mà không cần một cơ chế chọn join point.

Có thể áp dụng cả hai: giữ quy trình nghiệp vụ tường minh, gom thao tác kỹ thuật lặp lại vào thành phần riêng, rồi dùng AOP có phạm vi hẹp để áp dụng chúng ở những ranh giới phù hợp.

### Checklist trước khi đưa một aspect vào dự án

- **Concern:** Quy tắc đang tách ra là hành vi xuyên suốt hay là bước nghiệp vụ thiết yếu?
- **Join points:** Chính xác những đường gọi nào được bao phủ? Có đường nào bỏ qua cơ chế AOP?
- **Pointcut:** Khi refactor, thêm overload hoặc di chuyển package, tập khớp có còn đúng?
- **Advice:** Có cần thay đổi kết quả/ngoại lệ hay chỉ quan sát? Có dùng `finally` để dọn dẹp?
- **Order:** Những advice khác kết hợp theo thứ tự nào, thứ tự ấy có ảnh hưởng semantics không?
- **Vận hành:** Chi phí, recursion, reentrancy, concurrency và dữ liệu nhạy cảm được xử lý ra sao?
- **Kiểm thử:** Đã có ca thành công, lỗi, không khớp pointcut, lời gọi nội bộ và chạy đồng thời chưa?

## 12. Tự luyện tập để hiểu bản chất

Dựa trên `AopBasicsDemo.java` ở trên:

1. Sửa handler để chỉ ghi log cho phương thức `greet` bằng cách kiểm tra `method.getName()`; khi gọi `reject`, xác minh không còn các dòng advice. Đây là **mô phỏng pointcut**, chưa phải bộ diễn giải biểu thức pointcut.
2. Thêm phép đo `System.nanoTime()` trong khối `finally`. Không in một con số thời gian “dự đoán” cố định: thời gian chạy biến thiên từng lần.
3. Gọi trực tiếp `target.greet("Lan")` và so sánh với `service.greet("Lan")` để thấy đường gọi có hoặc không đi qua proxy.
4. Tạo một phương thức trong implementation gọi nội bộ đến phương thức khác; quan sát rằng lần gọi qua `this` không tạo thêm lượt callback của dynamic proxy.
5. Viết test cho hai nhánh thành công và ném lỗi, rồi kiểm tra số lần mỗi advice được gọi và ngoại lệ ban đầu có giữ nguyên không.

**Câu hỏi tự kiểm tra:** “Một pointcut là join point hay điều kiện chọn join point?”, “After returning có chạy khi target ném ngoại lệ không?”, “Tại sao quanh một lời gọi có thể có nhiều advice lồng nhau?”, “Tại sao đi thẳng vào target lại bỏ qua proxy?”, “Khi nào ghi log trong aspect có thể trở thành rủi ro bảo mật?”

## Kết luận

AOP tách các **mối quan tâm xuyên suốt** thành những **aspect** và áp dụng chúng lên **join point** được chọn bằng **pointcut**, thông qua các **advice** được kết hợp bằng cơ chế **weaving** hoặc trung gian tương đương. Sức mạnh của AOP là tăng tính nhất quán cho những chính sách chung; điểm cần kiểm soát là phạm vi khớp, đường gọi thực tế, thứ tự advice và sự thay đổi hành vi khi có lỗi. Hiểu rõ các ranh giới đó quan trọng hơn việc thuộc cú pháp của bất kỳ thư viện AOP cụ thể nào.