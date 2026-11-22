# Đặt tên pointcut để tái sử dụng và diễn đạt ý định

## 1. Vì sao nên đặt tên pointcut?

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), **pointcut** là một quy tắc chọn những *join point* (điểm trong luồng thực thi có thể được can thiệp) mà advice sẽ áp dụng. Với quy tắc nhỏ, người đọc có thể hiểu ngay một biểu thức kiểm tra chữ ký hoặc phạm vi. Nhưng khi cùng một quy tắc xuất hiện ở nhiều aspect, sao chép biểu thức thường tạo ra **sự trùng lặp và lệch phạm vi**.

**Đặt tên pointcut (named pointcut)** là đặt một **tên có ý nghĩa** cho một quy tắc lựa chọn, sau đó **tham chiếu và kết hợp** quy tắc ấy ở những nơi cần dùng. Thay vì yêu cầu người đọc giải mã nhiều điều kiện dài ở từng advice, tên sẽ nói rõ **vì sao nhóm join point được chọn**.

Ví dụ, các hành vi audit, ghi chỉ số và tracing cùng cần chọn “những thao tác làm thay đổi đơn hàng đã được đánh dấu cần theo dõi”. Thay vì viết lại ba lần điều kiện khớp chữ ký và annotation, ta đặt một quy tắc `auditableOrderCommands` rồi dùng lại trong cả ba chính sách. Khi ranh giới “thao tác đơn hàng cần audit” thay đổi, một định nghĩa nhất quán có thể cập nhật phạm vi của các nơi tham chiếu.

Cần phân biệt bốn thành phần:

| Thành phần | Vai trò | Câu hỏi nó trả lời |
| --- | --- | --- |
| **Join point** | Một điểm thực thi trong chương trình | “Có điểm nào để can thiệp?” |
| **Pointcut** | Quy tắc chọn tập join point | “Điểm nào được chọn?” |
| **Named pointcut** | Định danh một quy tắc chọn có thể tái sử dụng | “Nhóm điểm này có ý nghĩa gì?” |
| **Advice** | Hành vi chạy tại các điểm được chọn | “Khi được chọn, làm gì?” |

Một tên pointcut **không tự làm advice chạy**, không tự mở rộng tập join point mà engine AOP hỗ trợ, và không thay thế cơ chế weaving hoặc proxy. Nó là cách tổ chức **ý định lựa chọn**, còn hiệu lực thực thi phụ thuộc việc pointcut thực sự khớp và nằm trong vùng được can thiệp.

## 2. Từ biểu thức rời rạc đến một khái niệm có tên

Giả sử chính sách audit cần áp dụng cho phương thức thuộc hợp đồng dịch vụ đơn hàng, có mức truy cập `public` và được đánh dấu cần ghi nhận. Một biểu thức chọn bằng nhiều điều kiện có thể hình dung như sau:

~~~text
declaringType == OrderApi
AND visibility == public
AND hasMarker(Audited)
~~~

Đây là **ký pháp mô tả ý định**, không phải cú pháp thực thi của bất kỳ ngôn ngữ pointcut cụ thể nào. Nếu cùng ý định được lặp ở nhiều nơi, chỉ cần một người sửa thiếu điều kiện là audit, metrics và tracing có thể bắt đầu quan sát những tập lời gọi khác nhau.

Đặt tên cho ý định:

~~~text
pointcut publicOrderApi =
    declaringType == OrderApi AND visibility == public

pointcut markedForAudit =
    hasMarker(Audited)

pointcut auditableOrderCommands =
    publicOrderApi AND markedForAudit

advice audit    applies-to auditableOrderCommands
advice tracing  applies-to auditableOrderCommands
~~~

Các dòng trên là **pseudocode AOP**, không phải cú pháp Java hay một engine cụ thể. Điểm được nhấn mạnh là mối quan hệ: **hai pointcut nhỏ** → **một named pointcut thể hiện ý định** → **nhiều advice tái sử dụng**. Tên gắn với *chính sách áp dụng*, không gắn với việc advice đang làm gì; ví dụ `auditableOrderCommands` có thể dùng cho cả audit và tracing dù tên vốn bắt nguồn từ yêu cầu kiểm toán.

Nếu chỉ muốn ghi dấu một nhóm con nhạy cảm, ta tạo thêm:

~~~text
pointcut importantOrderCommands =
    auditableOrderCommands AND name == "place"
~~~

Ta **không sửa** `auditableOrderCommands` khi cần một nhóm hẹp cho một nhu cầu riêng; thay vào đó, tạo tên mới biểu thị rõ quan hệ “là tập con của”. Điều này tránh vô ý làm thay đổi các advice đang dùng pointcut chung.

## 3. Đặt tên theo ý định, không chỉ diễn đạt cú pháp

Hai tên sau cùng chỉ một điều kiện có thể rất khác nhau về khả năng bảo trì:

| Tên | Người đọc hiểu gì? | Đánh giá |
| --- | --- | --- |
| `publicMethodsWithMarker` | Các yếu tố kỹ thuật được kiểm tra | Hợp lý ở pointcut nền tảng, nhưng chưa nói vì sao chọn |
| `auditableOrderCommands` | Các thao tác đơn hàng thuộc chính sách audit | Phù hợp làm tên nghiệp vụ/kỹ thuật có chủ đích |
| `allMethods` | Một tập rất rộng, chưa có ý nghĩa áp dụng | Chỉ hữu ích nếu thật sự muốn mọi phương thức |
| `everythingForLogging` | Vừa mô tả quá rộng, vừa gắn chặt với một advice | Khó tái dùng cho chính sách khác |
| `pointcut1` hoặc `tempRule` | Không truyền đạt ranh giới hay ý định | Nên tránh |
| `sensitiveOperations` | Ý định rõ nếu thuật ngữ “sensitive” đã có định nghĩa | Cần tài liệu hoặc marker xác định thế nào là nhạy cảm |

Một tên tốt thường là **cụm danh từ mô tả tập join point**: `publicApiOperations`, `mutatingCommands`, `auditableTransactions`, `readOnlyQueries`, `externalBoundaryCalls`. Tên không nên gợi ý rằng **advice đã chạy**, vì việc matching và weaving vẫn là các bước khác nhau.

Hãy chọn độ trừu tượng phù hợp:

- **Pointcut nền tảng:** mô tả tiêu chí kỹ thuật nhỏ, chẳng hạn `publicServiceMethods`, `annotatedOperations` hoặc `inDomainPackage`.
- **Pointcut theo chính sách:** ghép các tiêu chí nền tảng thành `auditableCommands`, `measuredRequests`, `securedEntryPoints`.
- **Pointcut chuyên biệt:** thu hẹp một chính sách đã có cho phạm vi cần thiết, chẳng hạn `criticalAuditableCommands`.

Từ ngữ phải ổn định về mặt nghĩa. Nếu tên là `mutatingCommands` nhưng biểu thức chỉ khớp mọi phương thức có tiền tố `set`, nó có thể bỏ sót `delete` hoặc chọn nhầm phương thức không làm thay đổi dữ liệu. Khi đó tên là lời hứa vượt quá điều kiện thực tế.

## 4. Named pointcut không đồng nghĩa với một cú pháp chung

Các hệ thống AOP có thể cung cấp cách khai báo khác nhau: tên cho biểu thức pointcut, hàm hoặc macro tham chiếu, pointcut trừu tượng được hiện thực ở lớp con, quy tắc chọn bằng object/function, hoặc cấu hình do công cụ tải vào. Có công nghệ hỗ trợ tham số hóa và ghép biểu thức; có công nghệ chỉ cung cấp subset.

Cần xác minh từng khả năng:

1. **Định nghĩa tên:** pointcut được khai báo bằng phương thức, biểu thức, đối tượng hay cấu hình? Tên có nhất thiết trùng tên method không?
2. **Tham chiếu:** tên được dùng trực tiếp, có prefix theo type/namespace hay phải import?
3. **Phạm vi hiển thị:** `private`, package-local hoặc `public` trên pointcut mang ý nghĩa tái sử dụng nào? Nó khác với mức truy cập của phương thức target.
4. **Composition:** có hỗ trợ AND, OR, NOT, phép nhóm ngoặc hoặc đặt một named pointcut trong named pointcut khác không?
5. **Binding tham số:** tham chiếu named pointcut có truyền biến ngữ cảnh hoặc tham số không? Cách kiểm tra kiểu và tên biến ra sao?
6. **Độ phủ join point:** pointcut có khớp method call, method execution, constructor hoặc điểm khác không?
7. **Thời điểm xác định:** quy tắc chỉ theo metadata tĩnh hay có điều kiện runtime? Cách áp dụng khi value `null` hoặc target thay đổi?

**Không sao chép cú pháp pointcut từ hệ thống này sang hệ thống khác** và mặc định nó có cùng ngữ nghĩa. Một ký hiệu wildcard hoặc định dạng signature giống nhau vẫn có thể biểu diễn tập join point khác nhau.

## 5. Ghép và tái sử dụng: AND, OR, NOT và phép nhóm

Nhìn về mặt tập hợp, mỗi pointcut xác định một tập join point trong vũ trụ các điểm mà engine có thể quan sát. Tên giúp ta diễn đạt các phép biến đổi của tập:

| Phép logic | Ý nghĩa trên tập điểm | Trường hợp sử dụng |
| --- | --- | --- |
| `A AND B` | Chỉ điểm thuộc cả A và B | Public API **và** được đánh dấu audit |
| `A OR B` | Điểm thuộc A hoặc B | Lời gọi tới hai nhóm thao tác có cùng chính sách |
| `NOT A` | Điểm không thuộc A trong phạm vi nền | Loại nhóm tiện ích hoặc điểm bị loại trừ |
| `(A OR B) AND C` | Chọn A/B rồi giới hạn bởi C | Nhiều nhóm thao tác nhưng cùng giới hạn quyền |
| Tham chiếu `namedA` trong `namedB` | Tái sử dụng điều kiện đã định nghĩa | Pointcut chuyên biệt kế thừa phạm vi điểm gốc |

Ví dụ:

~~~text
pointcut writeCommands = hasMarker(ChangesState)
pointcut explicitAuditing = hasMarker(Audited)
pointcut entryPoints = publicApi AND notInternalHelpers

pointcut observableMutations =
    entryPoints AND (writeCommands OR explicitAuditing)
~~~

Đây là **pseudocode**, không phải một định dạng khai báo chạy được. Hai điều kiện `ChangesState` và `Audited` chỉ là nhãn khái niệm; ứng dụng có thể định nghĩa marker, metadata hoặc chính sách lựa chọn tương ứng.

Cần nhớ độ ưu tiên toán tử: `A OR B AND C` có thể bị đọc nhầm thành `(A OR B) AND C`, trong khi quy tắc ưu tiên thường cho nghĩa `A OR (B AND C)`. Khi nội dung quan trọng, **dùng ngoặc rõ ràng**, đặt named pointcut trung gian và kèm bảng kiểm thử.

**NOT cần được giới hạn theo phạm vi.** Một pointcut `NOT internalHelpers` nếu không giao với `publicApi` có thể chọn cực nhiều điểm ngoài mong đợi. Thường nên viết `publicApi AND NOT internalHelpers` để người đọc hiểu tập nền ngay từ đầu.

Đặt tên theo **hành vi ổn định** sẽ tránh hiện tượng quy tắc dài dần thành một chuỗi OR của nhiều ngoại lệ. Nếu logic quá phức tạp, cân nhắc chia thành các pointcut nhỏ và cung cấp tài liệu/kiểm thử cho từng tập.

## 6. Pointcut có tham số: tái sử dụng logic mà vẫn truyền ngữ cảnh

Trong một số mô hình AOP, named pointcut có thể nhận tham số hoặc binding ngữ cảnh. Ví dụ, một nhóm join point “mọi thao tác trên thực thể với đối số là tài khoản” có thể vừa được dùng cho audit vừa được dùng cho kiểm quyền. Ý định ở đây không chỉ là **chọn phương thức** mà còn là **đưa dữ liệu của lần gọi** vào advice.

Pseudocode:

~~~text
pointcut operationsOnAccount(account):
    selectedOperationWithAccountArg(account)

advice before operationsOnAccount(account):
    auditAccountId(account.id)
~~~

`account` chỉ là tên biến ngữ cảnh minh họa. Engine thật có thể yêu cầu khai báo kiểu, kiểm tra vị trí đối số, binding annotation hay một cấu trúc khác.

Khi tham số hóa, cần xác định:

- Tên và kiểu của tham số thuộc **khai báo pointcut**, còn giá trị thực tế thuộc **một lần thực thi**.
- Nếu nhiều overload có cấu trúc đối số khác nhau, pointcut phải diễn đạt rõ overload nào được phép khớp.
- `null` có thể làm các phép so kiểu động hoặc truy cập thuộc tính không thực hiện được như kỳ vọng; phải có quy tắc bảo vệ.
- Không sử dụng thông tin nhạy cảm làm khóa log mặc định; chỉ đưa những trường cần thiết vào advice.
- Một named pointcut có tham số không nên lén thay đổi input target nếu mục đích của advice chỉ là quan sát.

Khi công cụ không hỗ trợ binding tham số trong pointcut, có thể chọn join point ở mức tĩnh rồi để advice đọc đối số qua API được cung cấp. **Tái sử dụng pointcut** và **tái sử dụng chức năng xử lý ngữ cảnh** là hai vấn đề liên quan nhưng không đồng nhất.

## 7. Ví dụ Java 17+: đặt tên và ghép pointcut, dùng lại ở hai advice

Ví dụ sau dùng **Java Reflection, `Predicate<Method>` và JDK dynamic proxy** để hiện thực một *mô hình nhỏ* của named pointcut. Đây là ví dụ chạy độc lập trên Java 17+, nhằm chứng minh cách đặt tên, tham chiếu và ghép các bộ lọc; nó **không phải ngôn ngữ pointcut tổng quát** và proxy không hỗ trợ toàn bộ loại join point.

Ý định:

- `publicOrderApi()` chọn phương thức public khai báo trên interface `Orders`.
- `markedForAudit()` chọn các phương thức có annotation `@Audited`.
- `auditableCommands()` **tái sử dụng** hai named predicate và ghép bằng AND.
- `importantCommands()` thu hẹp `auditableCommands()` chỉ còn `place`.
- Hai wrapper `AUDIT` và `TRACE` cùng tham chiếu `auditableCommands()`; lời gọi `status()` không được chọn.

Tạo tệp `NamedPointcutDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;
import java.util.function.Predicate;

public class NamedPointcutDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Audited { }

    interface Orders {
        @Audited String place(String product, int quantity);
        @Audited String cancel(String id);
        String status();
    }

    static class OrderCore implements Orders {
        public String place(String product, int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            System.out.println("BUSINESS place");
            return product + " x" + quantity;
        }

        public String cancel(String id) {
            System.out.println("BUSINESS cancel");
            return "cancelled " + id;
        }

        public String status() {
            return "READY";
        }
    }

    static final class Pointcuts {
        static Predicate<Method> publicOrderApi() {
            return m -> m.getDeclaringClass() == Orders.class
                    && Modifier.isPublic(m.getModifiers());
        }

        static Predicate<Method> markedForAudit() {
            return m -> m.isAnnotationPresent(Audited.class);
        }

        static Predicate<Method> auditableCommands() {
            return publicOrderApi().and(markedForAudit());
        }

        static Predicate<Method> importantCommands() {
            return auditableCommands().and(m -> m.getName().equals("place"));
        }
    }

    static Object invokeTarget(Orders target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    static Orders wrap(Orders target, Predicate<Method> pointcut, String label) {
        return (Orders) Proxy.newProxyInstance(
                Orders.class.getClassLoader(),
                new Class<?>[] { Orders.class },
                (proxy, method, args) -> {
                    if (!pointcut.test(method)) {
                        return invokeTarget(target, method, args);
                    }
                    System.out.println(label + " begin " + method.getName());
                    try {
                        Object result = invokeTarget(target, method, args);
                        System.out.println(label + " success " + method.getName());
                        return result;
                    } catch (Throwable error) {
                        System.out.println(label + " failure " + method.getName());
                        throw error;
                    }
                });
    }

    public static void main(String[] args) throws Exception {
        Method place = Orders.class.getMethod("place", String.class, int.class);
        Method cancel = Orders.class.getMethod("cancel", String.class);
        System.out.println("IMPORTANT place: " + Pointcuts.importantCommands().test(place));
        System.out.println("IMPORTANT cancel: " + Pointcuts.importantCommands().test(cancel));

        Orders audited = wrap(new OrderCore(), Pointcuts.auditableCommands(), "AUDIT");
        Orders observed = wrap(audited, Pointcuts.auditableCommands(), "TRACE");

        System.out.println("STATUS " + observed.status());
        System.out.println("RESULT " + observed.place("Book", 2));
        System.out.println("RESULT " + observed.cancel("O-7"));
        try {
            observed.place("Book", 0);
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 NamedPointcutDemo.java
java NamedPointcutDemo
~~~

Kết quả đầu ra đã được kiểm chứng:

~~~text
IMPORTANT place: true
IMPORTANT cancel: false
STATUS READY
TRACE begin place
AUDIT begin place
BUSINESS place
AUDIT success place
TRACE success place
RESULT Book x2
TRACE begin cancel
AUDIT begin cancel
BUSINESS cancel
AUDIT success cancel
TRACE success cancel
RESULT cancelled O-7
TRACE begin place
AUDIT begin place
AUDIT failure place
TRACE failure place
CALLER quantity must be positive
~~~

**Giải thích từng điểm chính:**

1. `importantCommands()` tham chiếu `auditableCommands()` rồi ghép thêm điều kiện tên `place`. Vì thế `place` trả `true` nhưng `cancel` trả `false`. Cả hai vẫn nằm trong tập `auditableCommands()`.
2. `status()` không có `@Audited`, do đó cả hai wrapper đều bỏ qua logic bổ sung và chuyển tiếp về target. Ta chỉ thấy `STATUS READY`.
3. `place("Book", 2)` khớp named pointcut của cả hai wrapper: `TRACE` ở ngoài → `AUDIT` ở trong → nghiệp vụ → `AUDIT` hoàn tất → `TRACE` hoàn tất. Chính vì có hai wrapper, điểm khớp được quan sát bởi **hai hành vi khác nhau** mà không cần lặp định nghĩa bộ chọn.
4. `cancel("O-7")` cũng được đánh dấu `@Audited` nên được cả `TRACE` và `AUDIT` quan sát, dù không khớp `importantCommands()`.
5. Với `place("Book", 0)`, target ném `IllegalArgumentException`. `invokeTarget()` bóc `InvocationTargetException` do reflection tạo ra, hai wrapper ghi nhánh thất bại rồi ném tiếp nguyên nhân gốc cho caller. Việc tái sử dụng pointcut không làm mất tính đúng của hợp đồng ngoại lệ.

Đây là **mô hình proxy đơn giản**. `Method` mà JDK proxy đưa vào là method của interface, vì vậy `@Audited` được gắn trực tiếp trên interface `Orders`. Một engine AOP thực có thể chọn phương thức trên interface, implementation hoặc join point khác và có quy tắc tra annotation khác. Không nên tự suy ra rằng annotation trên interface luôn được kế thừa và phát hiện như nhau trong mọi cơ chế.

## 8. Tái sử dụng tên không có nghĩa là tái sử dụng trạng thái runtime

Một pointcut có tên về bản chất là một **định nghĩa chọn điểm**. Nó không cần lưu bộ đếm sự kiện, kết quả lời gọi hoặc dữ liệu mutable của từng lần chạy. Ví dụ `auditableCommands()` có thể được gọi nhiều lần để tạo ra các predicate tương đương; hai wrapper đang sử dụng các predicate độc lập nhưng cùng có logic và ý định.

Nếu ứng dụng cần chia sẻ metrics hay cache, chúng là những **dịch vụ/trạng thái khác**, nên được thiết kế có quy tắc đồng thời và vòng đời riêng. Đừng nhét bộ đếm trạng thái vào phần định nghĩa pointcut rồi mặc định gọi ở bất kỳ thời điểm nào cũng có cùng kết quả: hàm chọn điểm bị phụ thuộc vào trạng thái ngẫu nhiên sẽ khó kiểm thử và có thể thay đổi phạm vi advice giữa các lời gọi.

**Named pointcut cũng không mặc nhiên giảm số lần advice chạy.** Nếu hai advice cùng tham chiếu một pointcut, chúng có thể đều chạy trên cùng join point. Tái sử dụng ở đây là tái sử dụng **định nghĩa tập điểm**, không phải tự động loại bỏ một trong các advice.

## 9. Phạm vi truy cập và tổ chức tên giữa nhiều mô-đun

Trong một hệ thống AOP có hỗ trợ named pointcut ở cấp module hoặc class, tác giả thường cần quyết định điểm nào là **API lựa chọn chung** và điểm nào là **chi tiết triển khai riêng**:

| Phạm vi ý niệm | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| Pointcut private/internal | Dùng để ghép các quy tắc trong một aspect | Có thể thay đổi mà không ảnh hưởng tên được công khai |
| Pointcut chia sẻ trong package/module | Nhiều aspect cùng dùng cùng ranh giới | Cần một chủ sở hữu định nghĩa, quy ước thay đổi |
| Pointcut public/shared contract | Nhiều thành phần hoặc module khác nhau phụ thuộc | Tên và ý nghĩa chọn điểm trở thành hợp đồng đáng kiểm thử |

**Quyền truy cập của chính named pointcut** là câu chuyện khác với **modifier truy cập của phương thức target**. Ví dụ, một named pointcut có thể được công bố rộng rãi để mọi aspect dùng, nhưng điều kiện bên trong nó chỉ chọn phương thức target `public`. Ngược lại, một pointcut nội bộ có thể định nghĩa các join point khác nếu engine hỗ trợ.

Không phải công nghệ nào cũng có khái niệm `public/private` cho named pointcut. Khi công cụ chỉ có hàm, biến hoặc file cấu hình, hãy áp dụng cơ chế xuất/ẩn và quản lý dependency tương ứng. Điều quan trọng là **một nơi sở hữu tập điểm** và các nơi dùng hiểu rõ hợp đồng của tên đó.

Ví dụ, nếu `auditableCommands` là pointcut chia sẻ cho auditing và tracing, việc thêm `cancel` vào tập này sẽ tác động đến cả hai. Đó là một thay đổi về **phạm vi quan sát** đáng được code review và kiểm thử như sửa một API.

## 10. Thiết kế pointcut có tên để tránh coupling ẩn

Một biểu thức pointcut rất dài có thể gom nhiều điều kiện thuộc các tầng khác nhau: tên package, modifier, chữ ký, marker và điều kiện runtime. Khi mỗi nhóm điều kiện có tên, người đọc có thể nhận ra **phần nào là ranh giới kỹ thuật, phần nào là chính sách**.

Ví dụ:

~~~text
applicationEntryPoints
    = publicOperations AND inApplicationBoundary

trackedMutations
    = applicationEntryPoints AND changesState

auditableTrackedMutations
    = trackedMutations AND requiresAudit
~~~

Các tên trên là pseudocode thể hiện quan hệ tập hợp. Sự thay đổi ở `inApplicationBoundary` có thể lan tới cả hai tập dẫn xuất. Vì vậy, một chuỗi tham chiếu có tên tốt giúp thấy **phụ thuộc có chủ đích**; ngược lại, nhiều named pointcut lồng nhau nhưng không rõ người sở hữu cũng dễ khiến người sửa một chỗ làm ảnh hưởng phạm vi rộng.

Một điểm cân bằng:

- Đặt tên khi điều kiện **được tham chiếu ở nhiều nơi**, khi nó **diễn đạt một khái niệm ổn định**, hoặc khi biểu thức thô **khó đọc đủ để xác minh đúng**.
- Không cần tạo tên riêng cho mọi toán tử nhỏ nếu tên không giúp giải thích thêm ý nghĩa hoặc chỉ dùng đúng một nơi đơn giản.
- Tránh tạo **vòng tham chiếu** giữa các named pointcut. Hãy giữ các quy tắc như một đồ thị phụ thuộc rõ, dễ kiểm tra.
- Hạn chế đặt tên theo người dùng hiện tại của pointcut (`forLoggerOnly`) khi các chính sách khác có thể cần cùng ranh giới.
- Tài liệu nên nêu điều kiện **phải chọn** và **phải loại trừ**, kể cả ngoại lệ có chủ đích.

## 11. Kiểm thử ngữ nghĩa của named pointcut

Một named pointcut là một hợp đồng về **tập join point**, do đó kiểm thử cần tách **matching** với **advice thực sự chạy**.

| Tình huống | `auditableCommands` | `importantCommands` | Điều cần kiểm tra |
| --- | --- | --- | --- |
| `Orders.place(String,int)` có `@Audited` | Khớp | Khớp | Audit/trace có thể được áp dụng qua proxy |
| `Orders.cancel(String)` có `@Audited` | Khớp | Không | Chỉ thu hẹp ở tên chuyên biệt |
| `Orders.status()` không có `@Audited` | Không | Không | Không sinh sự kiện bổ sung |
| Method public nhưng không thuộc `Orders` | Không trong ví dụ | Không | Điều kiện declaring type phát huy tác dụng |
| Method cùng tên nhưng khác overload | Tùy marker và hợp đồng | Tùy tên/điều kiện khác | Kiểm tra trường hợp overmatching |
| Gọi trực tiếp `OrderCore` bỏ qua proxy | Bộ chọn vẫn có thể mô tả chữ ký | Tương tự | Advice trên proxy không chạy |
| Gọi thất bại qua proxy | Khớp nếu marker/kiểu hợp lệ | Theo tên | Bảo toàn ngoại lệ và kiểm đủ lời gọi |

Đối với công cụ AOP thực, cần kiểm thử cả các giới hạn mà chương trình Reflection mô phỏng không đủ: **join point call/execution, self-invocation, inheritance, bridge/synthetic methods, annotation trên interface hay implementation, thứ tự advice và vùng weaving**.

Có thể thiết lập hai nhóm test:

1. **Contract test cho named pointcut:** lập danh sách một số chữ ký/join point phải khớp, một số phải bị loại. Khi sửa định nghĩa dùng chung, những test này cho biết tập chọn bị mở rộng hay thu hẹp.
2. **Integration test cho aspect:** gọi thật qua cơ chế đã weaving/proxy; kiểm tra cả số lần advice chạy, kết quả, ngoại lệ, dữ liệu quan sát và đường không được chọn.

Khi cả audit và tracing dùng chung một pointcut, không nên chỉ kiểm tra một trong hai. Tập điểm có thể giống nhau về mặt định nghĩa, nhưng mỗi advice vẫn có thể khác nhau về thứ tự, điều kiện bổ sung hoặc đường lỗi.

## 12. Một số góc cạnh nâng cao

### 12.1. Tham chiếu quá rộng và độ ổn định của tên

Nếu `applicationOperations` được định nghĩa bằng “mọi method trong một package”, việc chuyển code sang package đó có thể làm phát sinh advice mà người viết method không dự đoán. Một marker có ngữ nghĩa và quy ước rõ có thể ổn định hơn quy tắc tên package, nhưng cũng đòi hỏi kiểm soát cách đánh dấu. Chọn điều kiện theo chính sách của dự án, rồi bảo vệ bằng contract test.

### 12.2. Compile-time và runtime matching

Một số điều kiện có thể quyết định từ signature khai báo, còn điều kiện khác phụ thuộc giá trị đối số/đối tượng thực trong lúc chạy. Nếu pointcut có tên chứa cả hai loại điều kiện, hãy nêu rõ phạm vi runtime, hiệu năng và dữ liệu nó được phép truy cập. Đừng hiểu việc chỉ ra được tên một method bằng Reflection là bằng chứng rằng mọi lần gọi sẽ có cùng kết quả matching trong một engine có điều kiện động.

### 12.3. Kiểu trả về và đường bất đồng bộ

Một named pointcut chọn “mọi phương thức trả `CompletableFuture`” có thể khớp **lần phương thức trả đối tượng Future**, không tự động quan sát khi tác vụ bên trong Future hoàn tất. Nếu chính sách mang tên `completedOperations` mà chỉ đo thời điểm return, tên và ngữ nghĩa đã lệch. Có thể cần một cơ chế quan sát completion riêng.

### 12.4. Tác dụng phụ và quyền thực thi

Một pointcut dùng lại cho audit và kiểm quyền không có nghĩa các advice đồng nhất. Advice kiểm quyền có thể chặn target; advice audit có thể cần ghi cả trường hợp từ chối. Nếu thứ tự không rõ, named pointcut đúng vẫn có thể dẫn đến log thiếu. Tên pointcut quyết định **tập điểm**, còn precedence/advice quyết định **trình tự và kết quả**.

### 12.5. Điều kiện phụ thuộc công nghệ

Tên pointcut có thể được kiểm tra tại thời điểm biên dịch/weaving hoặc được đánh giá khi chạy. Phạm vi tham chiếu, kiểu binding, wildcard, package/module visibility và xử lý generic/bridge khác nhau theo engine. Khi chuyển nền tảng, giữ **hợp đồng ý nghĩa** và tập trường hợp kiểm thử, sau đó viết lại cú pháp phù hợp thay vì sao chép nguyên biểu thức.

## 13. Sai lầm thường gặp

- **Dùng tên mơ hồ** như `commonMethods` mà không có hợp đồng tập điểm; không biết mở rộng đến đâu thì hợp lệ.
- **Đặt tên theo cú pháp nhưng hứa hẹn sai ý nghĩa:** `allWrites` chỉ chọn method `set*` và bỏ `save/delete`.
- **Sao chép biểu thức thay vì dùng chung tên:** ba advice có ba bộ chọn hơi khác nhau, khiến phạm vi bị lệch.
- **Sửa pointcut chia sẻ mà không đánh giá tác động:** thêm một điều kiện OR có thể khiến audit/tracing chạy ở những nơi ngoài dự kiến.
- **Lạm dụng phủ định rộng:** `NOT internal` có thể chọn gần toàn bộ ứng dụng nếu không giới hạn tập nền.
- **Dựa vào tên để suy ra engine có thể chặn mọi điểm:** proxy và weaving có phạm vi thực thi riêng.
- **Đánh đồng named pointcut với advice:** định nghĩa lựa chọn điểm không tự sinh hành vi.
- **Nhầm public/private của pointcut với access modifier của target:** hai phạm vi tiếp cận hoàn toàn khác.
- **Bỏ qua thứ tự khi nhiều advice dùng chung pointcut:** tập điểm đúng không bảo đảm kết quả quan sát đúng.
- **Không kiểm thử các trường hợp không được khớp:** các false positive đôi khi gây tác dụng phụ lớn hơn false negative.
- **Trông chờ generic, marker và overload được suy diễn giống nhau trong mọi công cụ:** cần kiểm tra mô hình join point và kiểu metadata.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `auditableCommands` thường là tên có ý nghĩa hơn `publicMarkedMethods` cho một chính sách chia sẻ?  
**Trả lời:** Nó thể hiện *mục đích* của tập điểm, còn tên thứ hai chủ yếu mô tả kỹ thuật khớp. Tên có ý nghĩa vẫn phải được bảo đảm bằng định nghĩa và kiểm thử.

**Câu 2.** Hai advice cùng tham chiếu một named pointcut. Một lời gọi khớp sẽ chỉ kích hoạt một advice phải không?  
**Trả lời:** Không. Tên được tái sử dụng cho **cùng tập điểm**; từng advice vẫn có thể chạy theo quy tắc áp dụng và thứ tự của cơ chế AOP.

**Câu 3.** Muốn chỉ lấy nhóm “thao tác quan trọng” từ một pointcut chung nên làm gì?  
**Trả lời:** Định nghĩa pointcut chuyên biệt bằng cách tham chiếu pointcut chung rồi ghép thêm điều kiện, thay vì tự ý thu hẹp pointcut chung làm ảnh hưởng các chính sách khác.

**Câu 4.** Nếu `auditableCommands` chọn đúng `privateMethod()` theo metadata, có chắc proxy sẽ chặn được không?  
**Trả lời:** Không. Matching và interception là hai bước khác nhau; kiểu proxy và weaving quyết định khả năng can thiệp.

**Câu 5.** Đâu là kiểm thử quan trọng nhất khi thay đổi một named pointcut chia sẻ?  
**Trả lời:** Kiểm tra tập **phải khớp/không được khớp** và chạy lại tích hợp các advice đang tham chiếu, bao gồm nhánh thành công, thất bại và đường bypass.

## 15. Tổng kết

**Đặt tên pointcut để tái sử dụng và diễn đạt ý định** giúp tập trung một quy tắc chọn join point thành một hợp đồng có nghĩa, dễ tham chiếu, dễ ghép và dễ kiểm thử. Nên phân biệt pointcut nền tảng với pointcut theo chính sách, đặt tên phản ánh **tập điểm cần áp dụng**, sử dụng composition để tạo tập con/tập hợp mới, và kiểm soát những nơi cùng phụ thuộc vào định nghĩa chia sẻ. Một named pointcut tốt chỉ là khởi đầu: muốn advice vận hành chính xác, vẫn phải xác minh quy tắc matching, phạm vi can thiệp, thứ tự advice, hành vi lỗi và sự khác biệt giữa các công nghệ AOP.