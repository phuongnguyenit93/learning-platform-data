# Kiểm thử proxy có default method và phương thức abstract

Khi kiểm thử Java dynamic proxy, cần xác nhận cả hai nhánh xử lý trong `InvocationHandler`: default method được chạy bằng `InvocationHandler.invokeDefault`, còn phương thức abstract được handler xử lý hoặc ủy quyền đến implementation thật. Một bài kiểm thử tốt nên quan sát kết quả công khai, thứ tự lời gọi và ngoại lệ; không phụ thuộc tên lớp proxy do JDK sinh ra hay chi tiết bytecode nội bộ.

`Proxy`, `InvocationHandler` và `InvocationHandler.invokeDefault` là các API Java hiện hành. `invokeDefault` có từ Java 16. Ví dụ trong bài dùng JUnit Jupiter (JUnit 5) để minh họa cách viết kiểm thử tự động trên JDK 16 trở lên.

## 1. Xác định hành vi cần kiểm thử

Giả sử interface có một phương thức abstract cung cấp giá trị gốc, cùng một số default method dùng giá trị đó để tính kết quả:

```java
public interface PricingService {
    int basePrice();

    default int tax() {
        return 10;
    }

    default int totalPrice() {
        return basePrice() + tax();
    }

    default int discountedTotal(int percent) {
        return totalPrice() * (100 - percent) / 100;
    }

    default int divide(int divisor) {
        return 10 / divisor;
    }
}
```

Trong factory ở phần tiếp theo, interface này được đặt lồng trong `PricingProxyFactory` để ví dụ có thể dùng một file riêng cho factory; vì vậy test tham chiếu kiểu `PricingProxyFactory.PricingService`.

Các trường hợp nên có trong bộ kiểm thử:

- Gọi trực tiếp phương thức abstract để xác nhận handler trả về dữ liệu.
- Gọi default method độc lập để xác nhận handler chạy phần thân mặc định.
- Gọi default method gọi một phương thức abstract để xác nhận lời gọi lồng nhau quay lại handler.
- Truyền đối số vào default method để xác nhận đối số được chuyển tiếp nguyên vẹn.
- Kiểm tra ngoại lệ phát sinh trong default method được truyền về client.
- Kiểm tra `equals`, `hashCode`, `toString` nếu handler có chính sách xử lý riêng cho các phương thức của `Object`.

## 2. Tạo proxy dùng trong kiểm thử

Factory dưới đây tạo proxy cho `PricingService`. Handler ghi nhận tên các phương thức nghiệp vụ được gọi, chạy default method qua `invokeDefault` và tự xử lý phương thức abstract `basePrice()`.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.util.List;

public class PricingProxyFactory {
    public interface PricingService {
        int basePrice();

        default int tax() {
            return 10;
        }

        default int totalPrice() {
            return basePrice() + tax();
        }

        default int discountedTotal(int percent) {
            return totalPrice() * (100 - percent) / 100;
        }

        default int divide(int divisor) {
            return 10 / divisor;
        }
    }

    public static PricingService create(
            int basePrice, List<String> calls) {
        InvocationHandler handler = (proxy, method, args) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "PricingService proxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == args[0];
                    default -> throw new UnsupportedOperationException(
                            method.toString());
                };
            }

            calls.add(method.getName());

            if (method.isDefault()) {
                Object[] actualArgs = args == null
                        ? new Object[0]
                        : args;
                return InvocationHandler.invokeDefault(
                        proxy, method, actualArgs);
            }

            if (method.getName().equals("basePrice")
                    && method.getParameterCount() == 0) {
                return basePrice;
            }

            throw new UnsupportedOperationException(method.toString());
        };

        return (PricingService) Proxy.newProxyInstance(
                PricingService.class.getClassLoader(),
                new Class<?>[]{PricingService.class},
                handler);
    }
}
```

Factory này dùng danh sách `calls` được truyền từ test để quan sát luồng xử lý. Trong ứng dụng thật, handler có thể ghi log hoặc áp dụng chính sách khác; danh sách ghi nhận ở đây chỉ phục vụ kiểm thử.

## 3. Kiểm thử phương thức abstract

Phương thức abstract không có phần thân để `invokeDefault` thực thi. Handler phải tự cung cấp kết quả hoặc gọi implementation đích. Với factory trên, `basePrice()` trả về giá trị đã truyền vào khi tạo proxy.

Đặt phương thức kiểm thử trong lớp `PricingProxyTest`. Các phương thức ở những phần sau cũng được thêm vào cùng lớp này.

```java
class PricingProxyTest {
    @Test
    void abstractMethodIsHandledByInvocationHandler() {
        List<String> calls = new ArrayList<>();
        PricingProxyFactory.PricingService service =
                PricingProxyFactory.create(100, calls);

        assertEquals(100, service.basePrice());
        assertEquals(List.of("basePrice"), calls);
    }
}
```

Test xác nhận hai điều: kết quả trả về đúng là `100`, và handler đã nhận lời gọi `basePrice`. Kiểm tra danh sách lời gọi giúp phát hiện trường hợp handler vô tình bỏ qua hoặc định tuyến sai phương thức.

## 4. Kiểm thử default method gọi phương thức abstract

`totalPrice()` là default method. Phần thân của nó gọi `basePrice()` và `tax()` trên `this`. Khi default method chạy trên proxy qua `InvocationHandler.invokeDefault`, hai lời gọi bên trong tiếp tục đi qua proxy và quay lại handler.

```java
@Test
void defaultMethodCanCallAbstractMethodThroughProxy() {
    List<String> calls = new ArrayList<>();
    PricingProxyFactory.PricingService service =
            PricingProxyFactory.create(100, calls);

    assertEquals(110, service.totalPrice());
    assertEquals(
            List.of("totalPrice", "basePrice", "tax"),
            calls);
}
```

Thứ tự mong đợi là `totalPrice`, `basePrice`, `tax`. Test này xác nhận default method được chạy, phương thức abstract được handler xử lý, và default method `tax()` tiếp tục được chuyển đến handler rồi chạy đúng phần thân mặc định.

## 5. Kiểm thử default method có đối số

Đối số của phương thức proxy được chuyển đến handler dưới dạng `Object[]`. Với tham số primitive như `int`, giá trị được boxing thành `Integer`. Khi handler chuyển tiếp nguyên mảng cho `invokeDefault`, JDK thực hiện việc chuyển đổi phù hợp để chạy phương thức.

```java
@Test
void defaultMethodReceivesItsArguments() {
    List<String> calls = new ArrayList<>();
    PricingProxyFactory.PricingService service =
            PricingProxyFactory.create(100, calls);

    assertEquals(88, service.discountedTotal(20));
    assertEquals(
            List.of("discountedTotal", "totalPrice", "basePrice", "tax"),
            calls);
}
```

Với giá gốc `100`, thuế `10` và mức giảm `20%`, kết quả là `88`. Danh sách lời gọi xác nhận `discountedTotal(20)` nhận đúng đường đi qua `totalPrice`, `basePrice` và `tax`.

## 6. Kiểm thử ngoại lệ từ default method

`invokeDefault` gọi phần thân default method trực tiếp. Nếu phần thân ném unchecked exception, handler có thể để ngoại lệ truyền ra client. Ví dụ `divide(0)` gây `ArithmeticException`:

```java
@Test
void exceptionFromDefaultMethodReachesCaller() {
    List<String> calls = new ArrayList<>();
    PricingProxyFactory.PricingService service =
            PricingProxyFactory.create(100, calls);

    assertThrows(ArithmeticException.class, () -> service.divide(0));
    assertEquals(List.of("divide"), calls);
}
```

Không có `InvocationTargetException` ở đây vì handler gọi default method bằng `InvocationHandler.invokeDefault`, không phải `Method.invoke`. Nếu handler ủy quyền đến target bằng `Method.invoke(target, args)`, ngoại lệ do target ném ra sẽ được bọc trong `InvocationTargetException`; khi đó handler thường lấy `getCause()` để chuyển tiếp lỗi gốc.

## 7. Kiểm thử các phương thức của Object và nhận diện proxy

Các phương thức `equals`, `hashCode` và `toString` cũng có thể được chuyển đến handler. Nếu handler định nghĩa chính sách riêng cho chúng, nên kiểm thử chính sách đó để tránh lỗi khi framework hoặc thư viện gọi các phương thức này.

```java
@Test
void proxyAndObjectMethodsFollowTheConfiguredPolicy() {
    PricingProxyFactory.PricingService service =
            PricingProxyFactory.create(100, new ArrayList<>());

    assertTrue(Proxy.isProxyClass(service.getClass()));
    assertNotNull(Proxy.getInvocationHandler(service));
    assertEquals("PricingService proxy", service.toString());
    assertEquals(System.identityHashCode(service), service.hashCode());
    assertTrue(service.equals(service));
}
```

Trong test này, `Proxy.isProxyClass` xác nhận lớp thực tế là lớp proxy do JDK tạo, còn `Proxy.getInvocationHandler` xác nhận proxy có handler. Không nên assert tên lớp được sinh tự động, vì tên và chi tiết triển khai nội bộ không phải hợp đồng API ổn định.

Nếu cần kiểm tra chính handler đã gắn vào proxy, có thể lấy kết quả `Proxy.getInvocationHandler(service)` và so sánh với handler mà factory đã tạo. Trong thiết kế test thực tế, có thể trả về một cấu trúc chứa cả proxy lẫn handler để kiểm tra rõ ràng hơn.

## 8. Tổ chức bộ test JUnit Jupiter

Các phương thức test ở trên có thể đặt trong cùng một lớp test `PricingProxyTest`. Phần import tĩnh thường dùng gồm:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
```

Đưa các import này lên đầu file `PricingProxyTest.java`. Các đoạn test ở mục 4 đến mục 7 là những phương thức thành viên bổ sung trong lớp đã tạo ở mục 3; khi ghép lại, giữ một dấu `}` đóng lớp ở cuối file.

Mỗi test tạo proxy và danh sách ghi nhận riêng để không chia sẻ trạng thái giữa các test. JUnit Jupiter tự quản lý việc thực thi các phương thức có `@Test`; khi chạy song song, không nên dùng chung một danh sách mutable hoặc proxy có handler chứa trạng thái không an toàn giữa các test.

Khi dự án đã dùng JUnit Jupiter, giữ dependency test trong cấu hình test scope của build tool. Không cần thêm thư viện mocking chỉ để kiểm tra hành vi cơ bản của JDK dynamic proxy; một handler nhỏ có thể thể hiện rõ luồng gọi và kết quả mong đợi.

## 9. Những điều nên và không nên kiểm thử

| Nên kiểm thử | Tránh phụ thuộc |
|---|---|
| Kết quả trả về từ default method và abstract method | Tên lớp proxy do JDK sinh ra |
| Thứ tự lời gọi qua handler khi đây là hợp đồng cần giữ | Bytecode hoặc tên method nội bộ của lớp proxy |
| Đối số được chuyển đúng và ngoại lệ đúng loại được truyền về | Cách JDK tạo hoặc lưu lớp proxy trong bộ nhớ |
| Chính sách `equals`, `hashCode`, `toString` do ứng dụng định nghĩa | Thứ tự gọi nội bộ không được API cam kết |
| Hành vi với phương thức không tham số và primitive | Giả định `args` luôn là mảng khác `null` |

Không nên viết test cố ý gọi `Method.invoke(proxy, args)` đến khi tràn stack để chứng minh lỗi đệ quy. Test như vậy không ổn định, tiêu tốn tài nguyên và có thể làm hỏng tiến trình test. Hãy kiểm tra trực tiếp handler đang dùng `InvocationHandler.invokeDefault` cho default method và không phản chiếu lại cùng lời gọi trên proxy.

## 10. Chạy kiểm thử và đánh giá kết quả

Khi chạy bộ test, cần bảo đảm JUnit Jupiter có trên test classpath và ứng dụng được biên dịch bằng JDK 16 trở lên vì ví dụ dùng `InvocationHandler.invokeDefault`. Với dự án dùng Maven hoặc Gradle, chạy task test tiêu chuẩn của dự án để nhận báo cáo pass/fail.

Khi test thất bại, kiểm tra theo thứ tự:

1. `method.isDefault()` có nhận diện đúng phương thức được gọi không?
2. Handler có truyền đúng `proxy`, `method` và `args` vào `invokeDefault` không?
3. Nhánh xử lý phương thức abstract có trả kiểu dữ liệu phù hợp với chữ ký không?
4. Default method có gọi thêm phương thức qua `this` và tạo ra lời gọi handler lồng nhau như dự kiến không?
5. Ngoại lệ được ném trực tiếp từ default method hay được bọc khi ủy quyền bằng `Method.invoke`?

Một bộ kiểm thử proxy có chất lượng xác nhận hành vi quan sát được từ interface, đường đi qua handler và hợp đồng ngoại lệ. Khi tập trung vào những điểm đó, test vẫn có giá trị khi JDK thay đổi chi tiết triển khai lớp proxy ở các phiên bản sau.
