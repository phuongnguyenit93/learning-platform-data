# Không gọi tiếp và trách nhiệm bảo toàn hợp đồng trong advice bao quanh

**Around advice (advice bao quanh)** là một dạng can thiệp trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**) có thể chạy trước, sau và bao quanh một join point. Khác với việc chỉ quan sát một thời điểm, around advice trong những cơ chế hỗ trợ còn có quyền **quyết định có tiếp tục phần thực thi được bao quanh hay không**, và có thể định hình kết quả hoặc ngoại lệ mà bên gọi nhìn thấy.

Điểm khó không nằm ở cú pháp `proceed()`. Nếu một advice **không gọi tiếp** mà tự trả kết quả hoặc ném ngoại lệ, nó đã thay đổi đường thực thi. Người viết phải chứng minh rằng cách thay thế ấy **bảo toàn hợp đồng có thể quan sát của thao tác gốc**, hoặc đang thay đổi hợp đồng theo một chính sách được thiết kế và công bố rõ ràng.

Ví dụ: một truy vấn giá chỉ đọc có thể trả kết quả từ cache mà không cần gọi hệ thống lưu trữ. Ngược lại, không thể tùy ý bỏ qua thao tác chuyển tiền rồi trả “thành công” chỉ vì muốn tiết kiệm thời gian; thao tác có tác dụng phụ và ràng buộc nghiệp vụ mà kết quả giả không thỏa mãn.

Bài viết tập trung vào mô hình AOP tổng quát: ý nghĩa của **không gọi tiếp**, các nhánh trả về/từ chối, hợp đồng kiểu và ngoại lệ, tác dụng phụ, thứ tự nhiều advice, tính an toàn và cách kiểm chứng. Tên hàm `proceed` trong các đoạn giả mã là cách gọi khái niệm; tên, khả năng và ngữ nghĩa chính xác phụ thuộc công cụ AOP.

## 1. Ba ngả điều khiển của around advice

Một **pointcut** chọn join point, **weaving/interception** nối advice vào đường thực thi, và **around advice** có thể quyết định có chuyển quyền vào phần bên trong hay không. Phần được tiếp tục có thể chứa thêm advice trước khi tới target; vì thế `proceed()` không mặc nhiên đồng nghĩa với một lời gọi trực tiếp đến phương thức gốc.

Trọng tâm bài này là những lần advice **không tiếp tục**. Có ba nhánh cần tách rõ:

~~~text
Around advice
  |-- proceed()  → tiếp tục chuỗi bên trong; nhận result hoặc error
  |-- return R   → kết thúc bình thường, không gọi phần bên trong
  |-- throw E    → kết thúc bằng lỗi, không gọi phần bên trong
~~~

Hai nhánh cuối đều **short-circuit**; chúng có thể bỏ qua target và mọi advice nằm bên trong. Tuy nhiên, advice bao phía ngoài vẫn có thể nhận giá trị `R` hoặc lỗi `E` và tiếp tục xử lý. Nếu có side effect đã hoàn thành trước khi short-circuit, việc không gọi tiếp **không hoàn tác** những tác động đó.

Quyền gọi 0/1/nhiều lần, thay đối số hoặc trả giá trị thay thế phụ thuộc công cụ và loại join point. Đánh giá short-circuit dựa trên **hợp đồng kết quả, lỗi và tác dụng phụ** của thao tác, thay vì suy rằng trả một giá trị có vẻ đúng là đã bảo toàn nghiệp vụ.

## 2. “Không gọi tiếp” có nghĩa chính xác là gì?

Giả sử nhiều lớp advice lồng nhau:

~~~text
Caller
  |
  v
OuterAdvice
  |
  v
CacheAdvice
  |
  v
AuditAdvice
  |
  v
BusinessMethod
~~~

Nếu `CacheAdvice` trả một kết quả cache mà **không tiếp tục**:

- `BusinessMethod` **không được gọi qua chuỗi này**.
- `AuditAdvice` nằm trong `CacheAdvice` **không được vào**, vì luồng chưa đi tới nó.
- `OuterAdvice` đã được vào vẫn có thể quan sát **kết quả trả về bình thường từ CacheAdvice**, rồi chạy xử lý sau/finally của chính nó.
- Một advice **after returning** ở lớp ngoài có thể thấy “thành công” dù phần thân nghiệp vụ không chạy lần này.
- Một advice bên trong không có cơ hội ghi log, đo thời gian hoặc kiểm tra quyền trong nhánh bị rút ngắn.

**Short-circuit có tính vị trí trong chuỗi lồng nhau.** Nói “nghiệp vụ bị bỏ qua” là chưa đủ; phải xác định những lớp advice **đã vào** và những lớp advice **chưa từng được chạy**.

### 2.1 Không gọi tiếp khác với tiếp tục rồi thay kết quả

Hai tình huống khác nhau về tác dụng phụ:

~~~text
A. Không gọi tiếp:
    return substituteValue

B. Gọi tiếp rồi thay kết quả:
    original = proceed()
    return transform(original)
~~~

Ở A, phần bên trong không chạy. Ở B, phần bên trong đã chạy, có thể ghi dữ liệu, gửi sự kiện hoặc mở giao dịch. Việc giá trị trả về cuối cùng giống nhau **không chứng minh** hai đường xử lý tương đương.

Tương tự, một around advice có thể gọi tiếp, bắt ngoại lệ, rồi trả fallback. Lúc đó nghiệp vụ đã được **thử chạy**; đây không phải trường hợp “không gọi tiếp từ đầu”.

## 3. Hợp đồng của phương thức bao gồm những gì?

**Hợp đồng (contract)** là tập những điều người gọi, người triển khai và các thành phần liên quan được quyền kỳ vọng về hành vi của một thao tác. Trong phạm vi kỹ thuật AOP, nó không chỉ có kiểu trả về.

| Thành phần hợp đồng | Ví dụ | Câu hỏi khi không gọi tiếp |
| --- | --- | --- |
| Tiền điều kiện | ID phải dương; người gọi phải có quyền | Advice có duy trì hoặc từ chối đúng điều kiện không? |
| Kiểu và ý nghĩa kết quả | `int` là giá theo đơn vị cent | Giá trị thay thế có đúng kiểu, đơn vị và ý nghĩa không? |
| Hậu điều kiện | Kết quả tương ứng dữ liệu hiện tại | Kết quả cache có đủ mới và hợp lệ không? |
| Ngoại lệ | Đầu vào sai bị từ chối; lỗi hạ tầng được thông báo | Advice có ném đúng loại lỗi và giữ thông tin cần thiết không? |
| Tác dụng phụ | Ghi bản ghi, trừ tiền, gửi thông báo | Bỏ qua thao tác có vi phạm nghĩa vụ tạo tác dụng phụ không? |
| Bất biến hệ thống | Số dư không âm; trạng thái nhất quán | Short-circuit có phá vỡ bất biến không? |
| Quyền truy cập | Trả dữ liệu chỉ cho người có quyền | Có bỏ qua một hàng rào kiểm soát nằm bên trong không? |
| Thời gian và vòng đời | Tài nguyên phải đóng; thao tác có timeout | Nhánh rút ngắn có dọn dẹp và đáp ứng timeout không? |
| Tính lặp / đồng thời | Không đếm trùng; không trả dữ liệu sai dưới race | Cache, idempotency và trạng thái chia sẻ có được đồng bộ đúng không? |
| Quan sát và truy vết | Mỗi yêu cầu có trạng thái cuối | Log/metrics phản ánh “cache hit” khác “backend executed” không? |

Tùy loại phương thức, có thể có ràng buộc khác như transaction, bảo mật, idempotency, tính nhất quán phân tán hoặc chính sách cache. **Trả về đúng Java type là cần, nhưng chưa đủ**.

### 3.1 Trả về giá trị thay thế khi nào là hợp lý?

Một around advice không gọi tiếp có thể hợp lệ nếu nó có **cách thực hiện tương đương hoặc được phép thay thế theo hợp đồng**. Những tình huống thường gặp:

- **Cache hit của truy vấn chỉ đọc:** dữ liệu cache hợp lệ về khóa, phiên bản, phân quyền và giới hạn độ mới.
- **Memoization:** thao tác thuần túy, cùng đầu vào hợp lệ thì cùng kết quả, không phụ thuộc tác dụng phụ ngoài.
- **Idempotency/deduplication:** cùng yêu cầu đã được xử lý theo một giao thức lưu trạng thái kết quả tin cậy; việc trả kết quả đã ghi nhận tuân thủ hợp đồng.
- **Circuit breaker / fallback:** hợp đồng công bố rõ chế độ từ chối hoặc kết quả suy giảm khi dịch vụ phụ thuộc không khả dụng.
- **Validation/authorization:** phát hiện yêu cầu không hợp lệ và ném ngoại lệ từ chối theo chính sách thay vì thực thi tiếp.
- **Test double:** trong kiểm thử được kiểm soát, thay thế thao tác thật nhằm kiểm tra thành phần khác; không suy rằng hành vi giả phù hợp production.

Không nên đánh đồng “có giá trị để trả” với “được phép trả giá trị đó”. Cache cũ, khác tài khoản, khác tenant hoặc không đúng phiên bản có thể vi phạm hợp đồng ngay cả khi không gây lỗi kiểu.

### 3.2 Khi không được tùy ý bỏ qua

Những thao tác sau cần thận trọng đặc biệt:

- **Ghi giao dịch:** nếu hợp đồng yêu cầu thay đổi trạng thái bền vững, trả “thành công” mà không ghi gì thường là sai.
- **Gửi thông báo/sự kiện:** nếu có cam kết gửi hoặc ghi nhận gửi, bỏ qua có thể phá luồng downstream.
- **Cấp số thứ tự/định danh:** trả lại kết quả cũ có thể gây trùng hoặc vi phạm uniqueness.
- **Kiểm toán bắt buộc:** một lớp cache bên ngoài có thể làm advice audit bên trong không chạy.
- **Bảo mật:** một lớp trả cache bên ngoài kiểm tra quyền có thể lộ dữ liệu cho người không đủ quyền.
- **Tài nguyên:** một kết quả thay thế không tự thực hiện cleanup mà phần thực thi gốc chịu trách nhiệm.

Hành vi bỏ qua chỉ hợp lệ khi **được thiết kế là một nhánh của hợp đồng**, không phải khi thuận tiện cho người viết advice.

## 4. Bảo toàn kiểu trả về

Around advice thường phải trả về một giá trị tương thích với **kiểu và ngữ nghĩa kết quả** của join point.

### 4.1 Kiểu nguyên thủy và boxing

Một phương thức Java trả `int` thường được một wrapper dựa trên Reflection biểu diễn qua `Integer`. Nếu handler trả `null` cho kết quả primitive, quá trình unboxing của lời gọi proxy có thể gây `NullPointerException`. Nếu trả một giá trị có kiểu boxing không phù hợp, quá trình chuyển kiểu có thể gây lỗi runtime.

Ví dụ:

~~~java
int countItems();   // Hợp đồng primitive int
String itemName();  // Có thể cho phép null hoặc cấm null tùy hợp đồng
void refresh();     // Hợp đồng không trả giá trị
~~~

Đây là **mảnh khai báo minh họa**, không phải chương trình độc lập.

Không nên nghĩ “around advice trả `Object` nên trả gì cũng được”. Kiểu ở lớp can thiệp có thể rộng, nhưng bên gọi vẫn được biên dịch dựa trên hợp đồng thật.

### 4.2 `null`, tùy chọn và collections

Với kiểu tham chiếu, `null` chỉ hợp lệ nếu hợp đồng cho phép. Một phương thức hứa trả danh sách không null không được thay bằng `null` dù Java cho phép gán kiểu. Nếu hợp đồng trả `Optional<T>`, giá trị thay thế cần là một `Optional` có ý nghĩa đúng, không tự thay thành `null` hay một `T` trần.

Danh sách trả về từ cache còn phải xét **mutability**: trả cùng một danh sách có thể bị bên gọi chỉnh sửa và làm hỏng cache hoặc làm lộ dữ liệu cho người khác. Bản sao bất biến, snapshot và chính sách sở hữu dữ liệu cần được xem xét.

### 4.3 Generics và kiểu runtime

Với phương thức `List<Order> listOrders()`, runtime Java có thể chỉ kiểm tra `List` do type erasure; một danh sách phần tử sai kiểu có thể không bị phát hiện ngay ở ranh giới can thiệp và chỉ gây lỗi khi bên gọi sử dụng. Bảo toàn hợp đồng generic đòi hỏi dữ liệu bên trong cũng đúng kiểu theo khai báo.

### 4.4 Void và giao thức hoàn thành

Với `void`, “trả thành công không gọi tiếp” có nghĩa bên gọi quan sát một lần hoàn thành bình thường dù thao tác gốc không chạy. Điều đó vẫn có thể **sai nghiêm trọng** nếu phương thức `void` có trách nhiệm gửi sự kiện, lưu dữ liệu hoặc giải phóng tài nguyên. `void` chỉ nói **không có giá trị trả về**, không có nghĩa **không có hợp đồng hậu điều kiện**.

## 5. Hợp đồng ngoại lệ và lỗi

Thay vì trả một giá trị, around advice có thể từ chối bằng cách ném ngoại lệ phù hợp:

~~~text
around(context, proceed):
    if invalidInput(context):
        throw InvalidRequestException()
    return proceed()
~~~

Điều này có thể là một nhánh hợp lệ của hợp đồng nếu hành vi gốc vốn yêu cầu từ chối đầu vào sai.

Cần phân biệt:

- **Lỗi đầu vào/chính sách:** ví dụ `IllegalArgumentException`, ngoại lệ phân quyền hoặc kiểu lỗi miền ứng dụng.
- **Lỗi hạ tầng:** timeout, kết nối lỗi, phụ thuộc không khả dụng.
- **Ngoại lệ từ nghiệp vụ:** phát sinh sau khi đã gọi tiếp.
- **Ngoại lệ do chính advice gây ra:** NullPointerException khi dùng context sai, lỗi định dạng, lỗi trong log/cleanup.

Một around advice không nên che giấu lỗi gốc bằng lỗi phụ không liên quan. Nếu cần đổi loại lỗi, hãy xác định rõ ý nghĩa và nguyên nhân `cause`. Với Java, những API dựa trên Reflection có thể bọc lỗi của phương thức đích bằng `InvocationTargetException`; khi chuyển tiếp nên hiểu cách tháo lớp bọc để bên gọi thấy ngoại lệ theo hợp đồng.

### 5.1 Checked exceptions

Một giao diện Java chỉ khai báo một số checked exceptions nhất định. Một proxy động ném ra checked exception không tương thích với hợp đồng khai báo có thể khiến bên gọi nhận `UndeclaredThrowableException`. Không nên dùng khả năng khai báo `throws Throwable` trong bộ xử lý proxy để suy rằng mọi checked exception đều hợp lệ khi truyền ra ngoài.

Around advice cần giữ **miền ngoại lệ hợp lệ** đối với phương thức đang can thiệp, hoặc chuyển thành kiểu ngoại lệ mà hợp đồng cho phép một cách có chủ đích.

### 5.2 Không gọi tiếp và phương thức bất đồng bộ

Nếu phương thức trả `CompletionStage<T>`, `Future<T>` hoặc một kiểu đại diện tác vụ, có hai sự kiện khác nhau:

1. **Phương thức trả về đối tượng đại diện**.
2. **Công việc bất đồng bộ hoàn tất**, thất bại hoặc bị hủy.

Short-circuit bằng một kết quả **đã hoàn tất** có thể hợp lệ trong một số hợp đồng, nhưng không tương đương với “đã khởi chạy tác vụ”. Cần bảo toàn quy tắc completion, cancellation, timeout, context propagation và chính sách báo lỗi. Trả `null` chỉ để bỏ qua tác vụ thường là sai nếu bên gọi được hứa một completion handle hợp lệ.

## 6. Tác dụng phụ và các nghĩa vụ không thể thay bằng một giá trị

Để chứng minh một nhánh short-circuit hợp lệ, cần trả lời:

1. Phương thức gốc có **thay đổi trạng thái** nào mà lời gọi đó phải thực hiện không?
2. Có **gửi sự kiện** hoặc tương tác bên ngoài bắt buộc không?
3. Có **kiểm tra quyền hoặc audit** ở các lớp bên trong không?
4. Có **mở rồi đóng tài nguyên** ở lớp bên ngoài không?
5. Có **cam kết exactly-once, at-least-once hay idempotency** đối với tác vụ này không?
6. Có yêu cầu **độ mới dữ liệu** hoặc tính nhất quán mà cache/fallback phải giữ không?

Từ góc nhìn bên gọi, hai hành vi `return 200` có vẻ giống nhau. Nhưng với hệ thống, một hành vi đã đặt hàng thành công và một hành vi chỉ trả hằng số có thể khác hoàn toàn.

### 6.1 Idempotency không có nghĩa tùy ý bỏ qua

Một yêu cầu có idempotency key có thể được trả lại kết quả đã lưu khi đến lần lặp. Tuy nhiên, hệ thống phải xác minh key thuộc đúng chủ thể/phạm vi, nội dung yêu cầu phù hợp, trạng thái xử lý đã hoàn tất và kết quả có thể tái sử dụng. Chỉ kiểm tra “key tồn tại” rồi trả thành công có thể bỏ qua một lần xử lý đang dở hoặc cho kết quả của yêu cầu khác.

### 6.2 Cache hit cũng cần hợp đồng

Một kết quả cache hợp lệ thường cần xét:

- **Khóa đầy đủ:** đầu vào, tenant, người dùng hoặc phạm vi quyền khi kết quả phụ thuộc các yếu tố ấy.
- **Độ mới:** thời hạn sống, phiên bản, invalidation, mức consistency cho phép.
- **Kết quả đặc biệt:** cache lỗi, cache null, “không tìm thấy” có được phép không?
- **Thay đổi dữ liệu:** khả năng trả snapshot bất biến hoặc bản sao để tránh chia sẻ đối tượng mutable sai cách.
- **Đồng thời:** nhiều cache miss có thể cùng gọi nghiệp vụ; HashMap thông thường không an toàn khi truy cập/ghi đồng thời không được đồng bộ.

## 7. Ví dụ Java 17 chạy độc lập: cache hit và từ chối trước `proceed`

Chương trình dưới đây dùng **Java dynamic proxy** để tạo một điểm can thiệp qua interface. Hàm `around` có ba nhánh:

1. **Đầu vào sai:** ném `IllegalArgumentException`, không gọi tiếp.
2. **Cache hit:** trả kết quả đã lưu, không gọi tiếp.
3. **Cache miss:** gọi tiếp đúng một lần rồi lưu kết quả khi thành công.

Phương thức gốc `price(id)` được giả định là **truy vấn chỉ đọc, xác định theo ID**, không cần tạo tác dụng phụ ngoài việc truy vấn. Ví dụ có một biến đếm để chứng minh **số lần thân phương thức thật chạy**; biến đếm này chỉ phục vụ quan sát, không phải trách nhiệm nghiệp vụ của truy vấn giá.

Tạo file `AroundShortCircuitDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.Map;

public class AroundShortCircuitDemo {
    public interface Catalog {
        int price(int productId);
    }

    public static final class CatalogImpl implements Catalog {
        private int executions;

        @Override
        public int price(int productId) {
            executions++;
            System.out.println("BUSINESS call=" + executions);
            if (productId == 5) {
                throw new IllegalStateException("backend down");
            }
            return productId * 100;
        }

        int executions() {
            return executions;
        }
    }

    @FunctionalInterface
    interface Proceed {
        Object call() throws Throwable;
    }

    static Object around(
            int productId, Map<Integer, Integer> cache, Proceed proceed)
            throws Throwable {
        if (productId <= 0) {
            System.out.println("REJECT " + productId);
            throw new IllegalArgumentException(
                    "productId must be positive");
        }

        Integer cached = cache.get(productId);
        if (cached != null) {
            System.out.println("CACHE HIT " + productId);
            return cached; // Không gọi tiếp.
        }

        System.out.println("PROCEED " + productId);
        try {
            Object value = proceed.call(); // Gọi tiếp đúng một lần.
            int price = (Integer) value;
            cache.put(productId, price);
            System.out.println("CACHE STORE " + productId);
            return price;
        } catch (Throwable error) {
            System.out.println("AROUND ERROR "
                    + error.getClass().getSimpleName());
            throw error;
        }
    }

    static Object invokeTarget(
            Catalog target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static Catalog wrap(Catalog target) {
        Map<Integer, Integer> cache = new HashMap<>();

        return (Catalog) Proxy.newProxyInstance(
                Catalog.class.getClassLoader(),
                new Class<?>[] { Catalog.class },
                (proxy, method, args) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return invokeTarget(target, method, args);
                    }
                    Object[] callArgs =
                            args == null ? new Object[0] : args.clone();

                    if (!method.getName().equals("price")) {
                        return invokeTarget(target, method, callArgs);
                    }
                    int productId = (Integer) callArgs[0];
                    return around(productId, cache,
                            () -> invokeTarget(target, method, callArgs));
                });
    }

    public static void main(String[] args) {
        CatalogImpl implementation = new CatalogImpl();
        Catalog catalog = wrap(implementation);

        System.out.println("RESULT " + catalog.price(2));
        System.out.println("RESULT " + catalog.price(2));

        try {
            catalog.price(-1);
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }

        try {
            catalog.price(5);
        } catch (IllegalStateException error) {
            System.out.println("CALLER " + error.getMessage());
        }

        System.out.println("RESULT " + catalog.price(3));
        System.out.println("EXECUTIONS " + implementation.executions());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac AroundShortCircuitDemo.java
java AroundShortCircuitDemo
~~~

Stdout:

~~~text
PROCEED 2
BUSINESS call=1
CACHE STORE 2
RESULT 200
CACHE HIT 2
RESULT 200
REJECT -1
CALLER productId must be positive
PROCEED 5
BUSINESS call=2
AROUND ERROR IllegalStateException
CALLER backend down
PROCEED 3
BUSINESS call=3
CACHE STORE 3
RESULT 300
EXECUTIONS 3
~~~

### 7.1 Phân tích từng nhánh

| Lần gọi | Quyết định của around advice | Có gọi tiếp? | Thân `CatalogImpl.price` chạy? | Bên gọi quan sát |
| --- | --- | --- | --- | --- |
| `price(2)` lần đầu | Cache miss | Có, một lần | Có | `200` |
| `price(2)` lần hai | Cache hit | **Không** | **Không** | `200` từ cache |
| `price(-1)` | Từ chối tiền điều kiện | **Không** | **Không** | `IllegalArgumentException` |
| `price(5)` | Cache miss, nghiệp vụ lỗi | Có, một lần | Có | `IllegalStateException` |
| `price(3)` | Cache miss | Có, một lần | Có | `300` |

Biến đếm `executions` cuối cùng bằng **3** vì chỉ các lần truy vấn ID 2 lần đầu, ID 5 và ID 3 chạy thân nghiệp vụ. Cache hit và đầu vào bị từ chối không làm tăng bộ đếm.

Bản thân việc `price(5)` ném lỗi không làm advice cache kết quả, bởi lệnh `cache.put` chỉ chạy sau `proceed.call()` trả về bình thường. Hàm `invokeTarget` tháo lớp bọc `InvocationTargetException` để chuyển tiếp ngoại lệ gốc từ thân phương thức.

### 7.2 Điều gì được bảo toàn trong ví dụ?

- **Kiểu trả về:** interface hứa `int`, advice trả một `Integer` có thể unbox thành `int`.
- **Giá trị:** cùng một ID hợp lệ trả một số giá ổn định trong giả định của ví dụ.
- **Lỗi đầu vào:** ID không dương bị từ chối bằng ngoại lệ đã chọn, không thực thi nghiệp vụ.
- **Lỗi backend:** lỗi từ thân phương thức được truyền tiếp; nó không bị biến thành giá cache tùy tiện.
- **Phạm vi:** advice chỉ bao những lời gọi đi qua proxy `catalog`.

Ví dụ dùng `HashMap` và biến đếm thường, **chỉ nhằm minh họa luồng đơn luồng**. Nếu truy cập đồng thời, cần chiến lược đồng bộ/cache phù hợp, độ mới dữ liệu, ngữ cảnh phân quyền, cơ chế chống cache stampede và yêu cầu hiệu năng. Ví dụ cũng **không** thể hiện một policy xác thực người dùng thật.

### 7.3 Vì sao không được khái quát quá mức?

Đây là một lớp bọc Java mô phỏng around advice. Nó **không phải cú pháp của một ngôn ngữ AOP phổ quát**, không tự weave bytecode và không nhìn thấy lời gọi trực tiếp như `implementation.price(2)`. Trong một hệ thống AOP khác, thời điểm join point và cách cung cấp continuation có thể khác. Chỉ điều có thể rút ra chắc chắn là: **nếu đường thực thi trả về hoặc ném lỗi trước khi gọi continuation, phần nằm sau continuation không được gọi qua đường đó**.

## 8. Nhiều advice lồng nhau: lớp nào bị bỏ qua?

Giả sử thứ tự lồng nhau:

~~~text
Metrics(
    Cache(
        Authorization(
            Audit(
                Business
            )
        )
    )
)
~~~

Nếu `Cache` trả kết quả mà không gọi tiếp, `Authorization`, `Audit` và `Business` **bị bỏ qua**, còn `Metrics` ở ngoài có thể ghi nhánh trả về bình thường. Điều này tạo **rủi ro nghiêm trọng về phân quyền**, ngay cả khi `Authorization` được viết chính xác.

Hai cách diễn đạt an toàn hơn phải được kiểm chứng theo hợp đồng:

1. Đặt **kiểm tra quyền không thể bỏ qua** ở lớp ngoài trước nhánh cache, để mỗi yêu cầu được kiểm tra trước khi truy xuất dữ liệu.
2. Hoặc bảo đảm lớp cache **tự áp dụng chính sách phân quyền đáng tin** khi trả dữ liệu và khóa cache đã phân vùng đúng; không thể chỉ dựa vào tên “cache” để chứng minh bảo mật.

Một cấu trúc gợi ý, không phải thứ tự mặc định của bất kỳ công cụ nào:

~~~text
Authorization(
    Metrics(
        Cache(
            Business
        )
    )
)
~~~

Đối với ví dụ này, mọi yêu cầu đi vào `Authorization` trước. Nhưng cần xác nhận một advice khác nằm ngoài cùng **không trả sớm trước kiểm tra quyền**, và mọi đường vào cần bảo vệ đều được can thiệp. Hợp đồng bảo mật là một **bất biến của toàn luồng**, không phải thuộc tính riêng của tên aspect.

### 8.1 Advice inside và outside không giống nhau

Khi `Cache` nằm ngoài `Metrics`:

~~~text
Cache(Metrics(Business))
~~~

cache hit làm `Metrics` không chạy; phép đo chỉ thấy cache miss. Khi `Metrics` nằm ngoài `Cache`:

~~~text
Metrics(Cache(Business))
~~~

mọi lời gọi qua wrapper đều được đo, kể cả cache hit. Hai hệ thống có thể cùng đúng nếu gọi rõ phép đo: **thời gian xử lý bên trong cache** so với **độ trễ toàn yêu cầu**.

Tương tự, nếu audit bắt buộc đếm **mọi lần người dùng yêu cầu**, nó không thể chỉ nằm trong lớp bị cache bỏ qua. Cần xác định ranh giới đo và ranh giới sự kiện trước khi cấu hình thứ tự advice.

## 9. Hợp đồng của `proceed`: không lần nào, một lần, nhiều lần

### 9.1 Không lần nào — short-circuit

~~~text
if validCacheHit:
    return cachedValue
if forbidden:
    throw policyError
~~~

Phải chứng minh hành vi thay thế đúng hợp đồng; mọi advice và nghiệp vụ bên trong có thể không chạy.

### 9.2 Một lần — bao quanh thông thường

~~~text
before()
try:
    return proceed()
finally:
    after()
~~~

Ở đây, phần bên trong được yêu cầu thực thi một lần. Tuy nhiên, một advice khác bên trong vẫn có thể short-circuit, nên “gọi `proceed`” không tự chứng minh thân nghiệp vụ thật chạy.

### 9.3 Nhiều lần — retry hoặc lặp có chủ đích

~~~text
for attempt in allowedAttempts:
    try:
        return proceed()
    catch retryable:
        continue
throw lastFailure
~~~

Đây là **giả mã**, và chỉ áp dụng khi cơ chế AOP cho phép gọi lại continuation theo cách phù hợp. Gọi lại có thể lặp tác dụng phụ, gửi yêu cầu trùng hoặc gây sai trạng thái giao dịch. Nếu nghiệp vụ không idempotent, một advice retry đặt sai có thể gây hậu quả nghiêm trọng.

**Phân biệt đơn vị đếm:** một request logic có thể thực hiện nhiều attempt, còn một cache hit có thể thực hiện không attempt nào. Metrics và audit cần phản ánh đúng đơn vị.

## 10. Trách nhiệm với transaction, locks và tài nguyên

Nếu around advice mở tài nguyên trước khi chọn short-circuit, nó vẫn phải đóng tài nguyên đã mở. Ví dụ:

~~~text
resource = open()
try:
    if cacheHit:
        return cachedResult
    return proceed()
finally:
    close(resource)
~~~

Ở đây `finally` cần chạy khi rời phạm vi dù nhánh cache có `return`. Nếu người viết return ở ngoài hoặc trước khối quản lý tài nguyên, cần xét xem tài nguyên đã được mở ở đâu.

Tuy nhiên, một short-circuit ở lớp ngoài trước giao dịch có thể làm **transaction advice bên trong chưa bao giờ được gọi**. Điều đó có thể tốt nếu không cần transaction cho cache hit, nhưng cũng có thể sai nếu hợp đồng yêu cầu thao tác ghi nhận giao dịch hoặc tính nhất quán cụ thể.

Với khóa và đồng bộ, một advice không được tùy tiện giữ khóa khi chuyển sang xử lý bất đồng bộ, bỏ qua `unlock` hoặc thay đổi thứ tự khóa. Nếu advice can thiệp trong vùng đang giữ khóa, việc gọi log hoặc truy cập cache có thể tăng contention hoặc tạo deadlock; phải giữ phần xử lý nhanh và có chiến lược đồng thời đúng.

## 11. Fallback, circuit breaker và tính minh bạch

### 11.1 Fallback không mặc nhiên là thành công

Một around advice có thể trả fallback khi dịch vụ không sẵn sàng, nhưng hợp đồng cần trả lời: fallback là **giá trị cuối cùng hợp lệ**, **dữ liệu suy giảm có đánh dấu**, hay **một sự thất bại được chuyển dạng**?

Ví dụ, API đọc giá có thể cho phép trả giá cache với dấu “stale” nếu tài liệu hợp đồng quy định rõ. API tài chính yêu cầu giá hiện thời có thể **không** được phép làm vậy. Nếu trả giá trị sai mà không thông báo, bên gọi nhận một “thành công giả”.

### 11.2 Circuit breaker có thể từ chối trước khi gọi tiếp

Khi circuit đang mở, advice có thể ném một lỗi “dịch vụ tạm thời không khả dụng” trước khi truy cập backend. Đây là một short-circuit hợp lệ nếu là hành vi được cho phép. Phải quy định chính xác loại lỗi, retry hint, timeout, thời gian mở circuit và cách khôi phục.

### 11.3 Không nuốt ngoại lệ chỉ để giữ đường chạy xanh

Bắt mọi ngoại lệ rồi trả `null`, `0`, chuỗi rỗng hoặc kết quả mặc định thường **phá hợp đồng** khi các giá trị đó mang ý nghĩa hợp lệ khác. Cần phân loại lỗi có thể khôi phục, trường hợp từ chối, lỗi lập trình và trạng thái không thể suy ra kết quả an toàn.

## 12. Quan sát và truy vết đúng khi không thực thi nghiệp vụ

Nếu chỉ đo số lần chạy thân phương thức, cache hit không được tính là “backend execution”. Nếu chỉ đo số yêu cầu từ phía người dùng, cache hit **vẫn** là một request.

Bộ đo nên có tên và phạm vi rõ:

| Đại lượng | Có tính cache hit? | Giải thích |
| --- | --- | --- |
| `requests` | Có | Số yêu cầu đi vào phạm vi ngoài cùng |
| `backend_attempts` | Không | Chỉ những lần thực sự gọi tiếp tới backend theo điểm quan sát |
| `cache_hits` | Có | Số yêu cầu được trả từ cache |
| `policy_rejections` | Có | Số lần advice từ chối theo chính sách |
| `backend_errors` | Không với cache hit | Chỉ lỗi của lần backend thực sự được gọi |
| `end_to_end_latency` | Có | Nếu bộ đo bao ngoài nhánh short-circuit |
| `backend_latency` | Không | Nếu chỉ đo vùng gọi backend |

Điều kiện “có/không” ở bảng phụ thuộc các vị trí instrument đã nêu, không phải là mặc định nền tảng.

Trace nên thể hiện rõ **cache hit, policy reject, fallback, attempted backend** để người vận hành không nghĩ nghiệp vụ đã chạy khi chưa chạy. Nếu một quanh advice rút ngắn từ ngoài, các span/audit nằm trong có thể không xuất hiện; đó là lý do instrumentation cho yêu cầu tổng thể thường cần đặt bên ngoài các lớp có thể short-circuit.

## 13. Bẫy khi chọn điểm can thiệp

Một quanh advice chỉ có ý nghĩa ở những **join point thực sự được weave**. Giả sử một cơ chế dùng proxy qua giao diện:

- Lời gọi thông qua proxy có thể được advice can thiệp.
- Lời gọi trực tiếp tới đối tượng đích có thể bỏ qua proxy.
- Lời gọi nội bộ từ phương thức này tới phương thức khác trên đối tượng đích có thể không quay qua proxy.
- Nếu chỉ can thiệp method call mà không hỗ trợ method execution, một số đường vào phần thân có thể nằm ngoài phạm vi quan sát.
- Kế thừa, overload, bridge/synthetic methods hoặc class được sinh có thể tác động vào chữ ký/đường gọi; phải kiểm chứng theo nền tảng.

Với hệ thống an ninh, đừng đặt mọi bảo vệ vào một around advice chỉ thấy một phần đường gọi. Phải có ranh giới đáng tin **bao phủ tất cả điểm truy cập được bảo vệ**, kết hợp các bất biến nghiệp vụ ở nơi phù hợp. Một pointcut được viết “đúng cú pháp” không chứng minh phạm vi được bảo vệ là đầy đủ.

## 14. Những sai lầm phổ biến

1. **“Không gọi `proceed` luôn là lỗi.”** Sai. Cache hit, từ chối hợp lệ hoặc fallback được định nghĩa có thể chủ đích không gọi tiếp.
2. **“Không gọi tiếp thì chỉ cần trả đúng kiểu.”** Sai. Còn hậu điều kiện, ngoại lệ, tác dụng phụ, consistency, security và quan sát.
3. **“Cache hit là nghiệp vụ đã chạy thành công lần này.”** Sai. Có thể không có lần thực thi backend nào trong yêu cầu hiện tại.
4. **“Trả `null` dùng được với mọi phương thức.”** Sai với primitive, `Optional`, non-null contract và completion handle.
5. **“Return từ advice làm mọi advice khác dừng ngay.”** Sai. Lớp ngoài đã vào có thể tiếp tục after/finally; chỉ phần bên trong bị skip.
6. **“Một advice gọi `proceed` nghĩa là thân nghiệp vụ chắc chắn chạy.”** Sai nếu một advice bên trong có quyền short-circuit.
7. **“Mọi lỗi backend đều nên chuyển thành kết quả mặc định.”** Sai nếu fallback không nằm trong hợp đồng.
8. **“`void` không có tác dụng phụ.”** Sai. Nhiều phương thức void chủ yếu tạo tác dụng phụ.
9. **“Cứ lưu theo khóa đầu vào là cache an toàn.”** Sai nếu kết quả còn phụ thuộc quyền, người dùng, tenant, phiên bản hoặc thời gian.
10. **“Advice kiểm tra quyền ở bên trong cache vẫn luôn chạy.”** Sai nếu cache trả sớm trước khi gọi tiếp.
11. **“Bỏ qua backend nghĩa là đã bảo đảm idempotency.”** Sai nếu thiếu giao thức ghi nhận trạng thái yêu cầu và kết quả tương ứng.
12. **“Một mô hình around advice áp dụng giống nhau cho mọi framework.”** Sai; phải xem cơ chế hỗ trợ continuation, thay kết quả và ngoại lệ.

## 15. Checklist thiết kế một nhánh short-circuit

Trước khi triển khai around advice có thể không gọi tiếp, hãy trả lời:

1. **Điểm chọn:** pointcut áp dụng tại method call hay method execution? Có bao phủ mọi đường vào mong muốn không?
2. **Ngữ cảnh:** advice lấy dữ liệu từ đâu? Dữ liệu runtime nào là đáng tin? Có cần phân biệt target, caller và tham số?
3. **Lý do short-circuit:** cache hit, validation reject, authorization deny, circuit open, fallback hay dedup?
4. **Hợp đồng kiểu:** kết quả thay thế có đúng kiểu/đơn vị/nullability/generic và trạng thái hoàn tất không?
5. **Hợp đồng lỗi:** loại ngoại lệ hoặc tín hiệu thất bại có phù hợp bên gọi không? Có giữ cause và không che lỗi quan trọng không?
6. **Hậu điều kiện:** bên gọi có nhận được trạng thái hợp lệ dù phần thân không thực thi không?
7. **Tác dụng phụ:** điều gì bắt buộc xảy ra? Điều gì được phép bỏ qua?
8. **Bảo mật:** kiểm tra quyền có thể bị lớp ngoài skip không? Cache có bị dùng chung qua người dùng/tenant sai cách không?
9. **Thứ tự advice:** outer/inner nào bị bỏ qua, lớp nào vẫn cleanup hoặc ghi audit?
10. **Tài nguyên:** khóa, giao dịch, kết nối và context tạm có được dọn dẹp đúng mọi đường không?
11. **Đồng thời:** có race condition, cache stampede, yêu cầu đang xử lý dở hoặc retry trùng không?
12. **Quan sát:** log/metrics thể hiện đúng `cache-hit`, `rejected`, `fallback`, `attempted`?
13. **Bất đồng bộ:** trả completion handle hợp lệ, báo hoàn tất/thất bại/hủy đúng hợp đồng không?
14. **Khả năng thực thi:** nền tảng AOP có hỗ trợ thật kiểu join point, around advice và continuation mà thiết kế cần không?

Nếu không trả lời được một điều khoản quan trọng, **không nên coi một lệnh `return` là đủ để thay thế thực thi gốc**.

## 16. Bài tập tự đánh giá

### Bài tập 1: Bộ nhớ đệm trước kiểm tra quyền

Cho mô hình:

~~~text
Cache(Authorization(Business))
~~~

Cache tìm thấy kết quả cho một ID và trả thẳng về, không gọi tiếp. Điều gì xảy ra?

**Đáp:** `Authorization` và `Business` ở bên trong không chạy. Nếu kiểm tra quyền là bắt buộc trên mọi lần đọc, thiết kế có nguy cơ vi phạm bảo mật. Cần đặt rào chắn quyền ngoài đường short-circuit hoặc tích hợp kiểm soát quyền đáng tin tại nhánh trả cache và phân vùng cache phù hợp.

### Bài tập 2: Trả sai kiểu

Phương thức gốc trả `int`, nhưng proxy handler trả `null` để “bỏ qua” phần gốc. Đây là một thay thế hợp lệ không?

**Đáp:** không. Quá trình unboxing kết quả `null` sang `int` có thể phát sinh `NullPointerException`. Ngay cả khi trả `0`, cũng phải chứng minh `0` là kết quả hợp lệ theo ngữ nghĩa nghiệp vụ.

### Bài tập 3: Cache của phương thức ghi

Một phương thức `void submitOrder(Order)` có nghĩa vụ tạo đơn hàng. Có thể dùng cache hit để không gọi tiếp, rồi trả bình thường không?

**Đáp:** không thể suy như vậy. Muốn hỗ trợ yêu cầu lặp, cần giao thức idempotency/dedup đáng tin chứng minh yêu cầu tương đương đã hoàn thành và trạng thái được bảo toàn. Bỏ qua thao tác ghi tùy tiện phá hợp đồng.

### Bài tập 4: Ngoại lệ sau khi đã gọi tiếp

Advice gọi `proceed`, nghiệp vụ ném lỗi, advice bắt lỗi rồi trả fallback. Đây là trường hợp “không gọi tiếp” không?

**Đáp:** không. Nó đã gọi phần bên trong rồi **chuyển đổi đường thất bại** thành một kết quả; tác dụng phụ một phần vẫn có thể đã xảy ra. Phải kiểm tra chính sách rollback và ý nghĩa fallback.

### Bài tập 5: Metrics nằm ở trong cache

~~~text
Cache(Metrics(Business))
~~~

Cache hit thì metrics có ghi không?

**Đáp:** nếu cache trả sớm mà không gọi tiếp, `Metrics` bên trong không được thực thi. Nếu cần đo mọi yêu cầu, đặt phép đo ở phạm vi bên ngoài short-circuit.

### Bài tập 6: Nhánh trả sớm trong `try/finally`

Một around advice đã mở tài nguyên rồi trả cached value từ trong khối `try`. Điều gì cần bảo đảm?

**Đáp:** `finally` của phạm vi đó vẫn chạy để dọn tài nguyên. Mã cleanup cũng không được vô tình làm mất kết quả hoặc che ngoại lệ gốc.

### Bài tập 7: Phương thức bất đồng bộ

Một phương thức hứa trả `CompletionStage<Result>`. Trả `null` ngay vì cache hit có tương đương trả kết quả cache không?

**Đáp:** không. Bên gọi kỳ vọng một đối tượng biểu diễn sự hoàn thành. Nếu short-circuit hợp lệ, cần trả completion handle phù hợp theo hợp đồng, cùng quy tắc lỗi, cancellation và context.

## 17. Tổng kết

**Không gọi tiếp trong around advice** có thể là một kỹ thuật thiết kế hợp lệ và hiệu quả: trả kết quả cache, từ chối yêu cầu hoặc cung cấp fallback. Nhưng điều đó chỉ đúng khi chính sách cho phép rút ngắn đường thực thi và kết quả quan sát được **vẫn thỏa hợp đồng**.

Hãy luôn tách ba việc:

- **Quyết định điều khiển:** có gọi continuation hay short-circuit?
- **Bảo toàn hợp đồng:** kiểu trả về, giá trị, lỗi, tác dụng phụ, bảo mật, nhất quán và vòng đời tài nguyên có còn đúng?
- **Phạm vi can thiệp:** join point/pointcut và thứ tự nhiều advice có bảo đảm mọi hành vi bắt buộc vẫn diễn ra không?

Điểm cốt lõi: **around advice có quyền thay thế đường thực thi, nhưng quyền đó đi cùng trách nhiệm chứng minh hành vi thay thế là hợp lệ**. Khi còn nghi ngờ về hậu điều kiện hoặc bảo mật, đừng bỏ qua `proceed` chỉ vì một giá trị có vẻ hợp lý.
