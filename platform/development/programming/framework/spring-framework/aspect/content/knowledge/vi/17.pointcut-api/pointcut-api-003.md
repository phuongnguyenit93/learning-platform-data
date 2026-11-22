# MethodMatcher tĩnh và kiểm tra động theo đối số trong Spring AOP

## 1. Mục tiêu: cùng một chữ ký, nhiều quyết định theo đối số

Giả sử `TransferService.transfer(String, int)` luôn hợp lệ để ghi log tối thiểu, nhưng chỉ những lần gọi có `amount >= 1000` cần audit bổ sung. Spring AOP cho phép tách **điều kiện tĩnh** (class, tên method, kiểu/số tham số) khỏi **điều kiện động** (giá trị thật của `amount` trong từng invocation).

`Pointcut` chứa `ClassFilter` và `MethodMatcher`; `DefaultPointcutAdvisor` ghép Pointcut với advice trong Spring proxy. Với `MethodMatcher`, cần phân biệt ba phương thức:

- `matches(Method, Class<?>)`: kiểm tra tĩnh xem method có thể nhận advice.
- `isRuntime()`: cho biết có cần kiểm tra giá trị thực tế mỗi lời gọi.
- `matches(Method, Class<?>, Object... args)`: chỉ được gọi khi bước tĩnh true và `isRuntime()` true; có thể trả true cho lần gọi này và false cho lần khác.

## 2. Dự đoán khi method và argument thay đổi

| Lời gọi qua proxy | Static match transfer(String,int) | Dynamic match amount >= 1000 | Audit động |
| --- | --- | --- | --- |
| `transfer("A", 50)` | Có | Không | Bỏ qua |
| `transfer("B", 1500)` | Có | Có | Chạy |
| `balance("A")` | Không | Không cần gọi | Bỏ qua |

`ClassFilter` vẫn là cửa đầu tiên để loại toàn bộ target class không liên quan. Spring có thể cache quyết định tĩnh khi tạo hoặc phân giải proxy; đừng gắn side effect vào matcher hay assert nó chỉ chạy đúng một lần. Với một method đã qua bước tĩnh, runtime matcher được đánh giá trên từng invocation theo trạng thái argument lúc đó, rồi Spring mới quyết định chạy advice tương ứng.

Hai lớp Spring có sẵn là `StaticMethodMatcherPointcut` (`isRuntime() == false`) và `DynamicMethodMatcherPointcut` (`isRuntime() == true`). Matcher tĩnh phù hợp khi cùng chữ ký luôn có cùng quyết định; matcher động cần điều kiện tĩnh đủ hẹp và phép kiểm tra `args` nhẹ, thuần, không thay đổi nghiệp vụ. Ví dụ tiếp theo hiện thực đúng tình huống `transfer` trên bằng `ProxyFactory`.

## 3. Ví dụ hoàn chỉnh với Spring ProxyFactory

Yêu cầu: phương thức `transfer` của `TransferService` được audit. Cách **tĩnh** audit mọi lệnh transfer. Cách **động** chỉ audit khi đối số `amount >= 1000`. Ví dụ dùng Java 17+ và Spring AOP trực tiếp, không cần Spring Boot container hay annotation `@Aspect`.

**`build.gradle`** (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-aop:6.1.21'
}

application {
    mainClass = 'example.MatchersDemo'
}
```

**`src/main/java/example/MatchersDemo.java`**:

```java
package example;

import java.lang.reflect.Method;
import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.Pointcut;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.DefaultPointcutAdvisor;
import org.springframework.aop.support.DynamicMethodMatcherPointcut;
import org.springframework.aop.support.StaticMethodMatcherPointcut;

public class MatchersDemo {

    public interface TransferService {
        void transfer(String account, int amount);
        void balance(String account);
    }

    static final class TransferServiceImpl implements TransferService {
        @Override
        public void transfer(String account, int amount) {
            System.out.println("TARGET transfer " + account + " " + amount);
        }

        @Override
        public void balance(String account) {
            System.out.println("TARGET balance " + account);
        }
    }

    private static boolean isTransfer(Method method, Class<?> targetClass) {
        return TransferService.class.isAssignableFrom(targetClass)
                && method.getName().equals("transfer")
                && method.getParameterCount() == 2
                && method.getParameterTypes()[0] == String.class
                && method.getParameterTypes()[1] == int.class;
    }

    static final class StaticTransferPointcut
            extends StaticMethodMatcherPointcut {
        @Override
        public boolean matches(Method method, Class<?> targetClass) {
            return isTransfer(method, targetClass);
        }
    }

    static final class LargeTransferPointcut
            extends DynamicMethodMatcherPointcut {
        @Override
        public boolean matches(Method method, Class<?> targetClass) {
            // Loại các method không liên quan trước khi xét args.
            return isTransfer(method, targetClass);
        }

        @Override
        public boolean matches(Method method, Class<?> targetClass,
                               Object... args) {
            // int trong tham số được boxing thành Integer trong args.
            return args.length == 2
                    && args[1] instanceof Integer amount
                    && amount >= 1000;
        }
    }

    private static TransferService createProxy(Pointcut pointcut) {
        ProxyFactory factory = new ProxyFactory(new TransferServiceImpl());
        factory.setInterfaces(TransferService.class);
        factory.setProxyTargetClass(false);

        MethodInterceptor audit = invocation -> {
            System.out.println("ADVICE audit");
            return invocation.proceed();
        };
        factory.addAdvisor(new DefaultPointcutAdvisor(pointcut, audit));
        return (TransferService) factory.getProxy();
    }

    public static void main(String[] args) {
        System.out.println("=== STATIC ===");
        TransferService a = createProxy(new StaticTransferPointcut());
        a.transfer("ACC", 100);
        a.transfer("ACC", 1500);
        a.balance("ACC");

        System.out.println("=== DYNAMIC ===");
        TransferService b = createProxy(new LargeTransferPointcut());
        b.transfer("ACC", 100);
        b.transfer("ACC", 1500);
        b.balance("ACC");
    }
}
```

Chạy tại thư mục có `build.gradle` bằng `gradle run` (nếu dự án có Gradle wrapper: `./gradlew run`; PowerShell: `.\gradlew.bat run`). Stdout của chương trình, không tính log Gradle:

```text
=== STATIC ===
ADVICE audit
TARGET transfer ACC 100
ADVICE audit
TARGET transfer ACC 1500
TARGET balance ACC
=== DYNAMIC ===
TARGET transfer ACC 100
ADVICE audit
TARGET transfer ACC 1500
TARGET balance ACC
```

Đọc kết quả:

1. Với pointcut **tĩnh**, cả hai lời gọi `transfer` đều nhận advice, vì `Method` và `targetClass` không đổi dù số tiền khác nhau.
2. Với pointcut **động**, bước tĩnh chọn `transfer`; bước runtime lấy `args[1]`. Khi amount là `100`, advice không chạy nhưng target vẫn chạy. Khi amount là `1500`, advice chạy trước target.
3. `balance` bị loại ngay trong `matches(Method, Class<?>)` của cả hai pointcut, nên không in dòng audit.
4. `setInterfaces` và `setProxyTargetClass(false)` khiến ví dụ dùng JDK interface proxy; gọi các phương thức thông qua interface proxy mới đi qua Spring AOP.

Lưu ý: `instanceof Integer amount` dùng pattern matching Java 17, và primitive `int` được boxing khi đặt vào `Object[] args`. Việc kiểm tra `args.length` cùng `instanceof` tránh lỗi khi chữ ký không như dự tính. Kiểm tra tên **và kiểu tham số** tại bước tĩnh cũng giúp tránh match nhầm overload.

## 4. Cách thiết kế matcher hiệu quả

Đặt điều kiện **không phụ thuộc giá trị đầu vào** vào overload hai tham số:

```java
@Override
public boolean matches(Method method, Class<?> targetClass) {
    return method.getName().equals("transfer")
            && method.getParameterCount() == 2;
}
```

Chỉ đặt điều kiện **cần giá trị lúc gọi** vào overload ba tham số:

```java
@Override
public boolean matches(Method method, Class<?> targetClass, Object... args) {
    return args.length == 2
            && args[1] instanceof Integer amount
            && amount >= 1000;
}
```

Hai đoạn trên nhằm minh họa sự phân chia trách nhiệm; ví dụ chạy đầy đủ ở mục 3 có kiểm tra chữ ký chặt chẽ hơn.

Với dịch vụ có nhiều phương thức nhưng chỉ `transfer` cần xét ngưỡng, bộ lọc tĩnh giúp tránh chi phí đọc `args` trên các phương thức khác. Không nên để overload tĩnh luôn trả `true` trừ khi thật sự muốn kiểm tra động cho toàn bộ chúng.

Matcher nên **nhanh, không có side effect, không I/O**, không sửa `args` và không phụ thuộc trạng thái có thể thay đổi một cách khó đoán. Với điều kiện rất tốn kém (DB, HTTP), cân nhắc thực hiện ở service/advice với chính sách cache và xử lý lỗi rõ ràng; dynamic matcher được gọi thường xuyên trong đường đi của phương thức.

## 5. Những bẫy thường gặp

**Nhầm `isRuntime()` với việc tạo proxy runtime.** Nó chỉ cho biết có cần thực hiện thêm overload có `args` hay không. `StaticMethodMatcherPointcut` có `isRuntime() == false`; `DynamicMethodMatcherPointcut` có `isRuntime() == true`. Khi tự cài `MethodMatcher` trực tiếp, ba phương thức phải nhất quán.

**Nhầm chữ ký method với đối số thực tế.** `method.getParameterTypes()` cho kiểu khai báo (`int.class`), còn `args` chứa giá trị của lần gọi (ví dụ `Integer(100)`, `Integer(1500)`). Kiểm tra tĩnh không thể phân biệt hai giá trị này.

**Tưởng matcher trả `false` sẽ dừng transaction/target.** `false` chỉ không áp dụng advice tương ứng. Muốn từ chối dữ liệu không hợp lệ phải thực hiện validation/authorization hoặc ném exception ở lớp nghiệp vụ thích hợp; không dùng matcher đơn thuần để đảm bảo chặn thao tác.

**Không lọc ở bước tĩnh.** Nếu chỉ cần `transfer`, kiểm tra tên/chữ ký trong overload hai tham số. Để overload tĩnh trả `true` với mọi method sẽ khiến Spring chạy dynamic check nhiều hơn mức cần thiết.

**Dựa vào số lần gọi overload tĩnh.** Spring có thể xét tĩnh khi tạo proxy hoặc phân giải phương thức và có caching; các chi tiết triển khai và số lần gọi có thể khác nhau. Chỉ nên dựa vào hợp đồng là runtime check cần static match và `isRuntime == true`.

**Quên thứ tự advice.** Runtime matching được thực hiện trước advice tương ứng; các advice đứng trước trong interceptor chain có thể đã chạy. Nếu một interceptor trước đó đổi đối số, thứ tự chuỗi có thể ảnh hưởng giá trị quan sát được. Vì vậy không nên viết matcher có side effect hoặc phụ thuộc trình tự gọi không được bảo đảm.

**Quên giới hạn proxy.** Lời gọi từ bên ngoài qua proxy được Spring AOP xử lý. Một self-invocation kiểu `this.transfer(...)` bên trong cùng target thường bỏ qua proxy; matcher sẽ không được dùng cho lời gọi nội bộ đó.

## 6. Chọn static, dynamic hay biểu thức AspectJ của Spring?

- Chọn **`StaticMethodMatcherPointcut`** cho điều kiện theo tên, chữ ký, lớp hoặc metadata ổn định. Đây là hướng ưu tiên khi không cần giá trị đầu vào.
- Chọn **`DynamicMethodMatcherPointcut`** khi cần *quyết định có chạy advice* dựa trên đối số mỗi lần gọi, chẳng hạn amount vượt ngưỡng.
- Với điều kiện pointcut thông dụng, biểu thức AspectJ được Spring AOP hỗ trợ (ví dụ `execution(...)`, `within(...)`, `args(...)`) thường gọn hơn. `args(...)` có thể ràng buộc/kiểm tra kiểu đối số ở runtime nhưng không phải cú pháp trực tiếp cho phép viết phép so sánh số `amount >= 1000`; trường hợp này có thể kiểm tra trong advice hoặc dùng custom dynamic MethodMatcher.

Không nên tạo dynamic matcher chỉ để thay một điều kiện có thể giải quyết hoàn toàn bằng matching tĩnh.

## 7. Câu hỏi tự kiểm tra

1. `matches(Method, Class) == false`, `isRuntime() == true`: overload có `args` có chạy không? **Không**; bước tĩnh đã loại method.
2. `isRuntime() == false`: có thể phân biệt hai lần gọi cùng chữ ký nhưng amount khác nhau không? **Không** bằng MethodMatcher đó.
3. Matcher động trả `false` khi amount=100: target còn chạy không? **Có**, khi các thành phần khác trong chain không chặn.
4. Chỉ cần audit mọi `transfer`: dùng lớp nào? **`StaticMethodMatcherPointcut`**, vì tiêu chí không phụ thuộc args.
5. Với `transfer(String, int)`, `getParameterTypes()[1]` và `args[1]` khác gì? **Kiểu khai báo `int.class`** so với **giá trị boxed `Integer` tại lần gọi**.

## Tài liệu Spring chính thức

- [Spring Reference — Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html)
- [Spring 6.1 — MethodMatcher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/aop/MethodMatcher.html)
- [Spring 6.1 — StaticMethodMatcherPointcut](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/aop/support/StaticMethodMatcherPointcut.html)
- [Spring 6.1 — DynamicMethodMatcherPointcut](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/aop/support/DynamicMethodMatcherPointcut.html)
