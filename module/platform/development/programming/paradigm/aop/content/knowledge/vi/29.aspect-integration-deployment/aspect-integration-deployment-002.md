# Tách mã aspect, cấu hình và thư viện dùng chung

## 1. Bài toán: aspect tái sử dụng được nhưng phải có ranh giới rõ

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), **aspect** gom một mối quan tâm xuyên suốt nhiều thành phần, chẳng hạn đo thời gian, ghi dấu vết, kiểm tra truy cập, giới hạn số lần thử hoặc kiểm toán. Khi một dự án lớn dần, việc đặt toàn bộ advice, biểu thức pointcut, tham số cấu hình, mã kích hoạt weaving/proxy và tiện ích chung vào cùng một gói khiến sửa một chính sách có thể ảnh hưởng đến nhiều dịch vụ.

Mục tiêu của việc tách là thiết lập ranh giới **ai định nghĩa hợp đồng, ai hiện thực chính sách, ai cấu hình chính sách và ai gắn chính sách vào nghiệp vụ**. Không phải cứ chia ra nhiều thư mục là đã tách đúng: cần nhìn vào **chiều phụ thuộc**, **quyền sở hữu cấu hình**, **thời điểm áp dụng AOP** và **kiểm thử tích hợp**.

Sau bài học, bạn có thể:

- Phân biệt **mã aspect/advice**, **cấu hình** và **thư viện dùng chung** về trách nhiệm và vòng đời.
- Xác định nơi đặt pointcut, precedence, cơ chế proxy/weaving và composition root.
- Thiết kế phụ thuộc một chiều để nghiệp vụ không phải biết advice đang tồn tại.
- Đóng gói, lập phiên bản và kiểm thử riêng từng phần mà vẫn xác minh được đường gọi đã được can thiệp.
- Áp dụng mô hình cụ thể với Java 17+, thư viện hợp đồng nhỏ và một ứng dụng tự lắp ráp chuỗi around advice.

Phạm vi là **AOP tổng quát**. Không có một chuẩn duy nhất áp đặt cấu trúc dự án hay thuật toán precedence cho mọi công cụ AOP. Ví dụ dùng **JDK dynamic proxy** để minh họa việc tách thành phần có thể chạy độc lập; phần tích hợp weaving khi biên dịch hoặc khi tải lớp được phân tích riêng ở các mục sau.

## 2. Bốn ranh giới trách nhiệm

| Ranh giới | Chứa gì? | Không nên chứa gì? | Ai thay đổi? |
| --- | --- | --- | --- |
| **Hợp đồng AOP dùng chung** | Giao diện continuation/invocation, advice API, kiểu dữ liệu context, ngoại lệ hợp đồng nếu cần. | Pointcut gắn với domain cụ thể; biến cấu hình của từng ứng dụng; secret. | Nhóm sở hữu thư viện công cụ. |
| **Mã aspect/chính sách** | Logic của tracing, authorization, audit, retry; xử lý trước/sau/quanh join point. | Đọc trực tiếp file cấu hình của ứng dụng; tự khởi động engine; biết cách triển khai từng môi trường. | Nhóm sở hữu chính sách xuyên suốt. |
| **Cấu hình và quy tắc áp dụng** | Bật/tắt tính năng được phép, giá trị timeout, selector/pointcut, thứ tự precedence, ánh xạ chính sách với join point. | Mã nghiệp vụ, thuật toán advice, phụ thuộc ngầm vào global mutable state. | Ứng dụng hoặc lớp triển khai, trong phạm vi quyền được cấp. |
| **Composition root / lớp tích hợp** | Tạo aspect, inject dependency, chọn proxy/weaver, kết nối target với advice, kiểm tra cấu hình. | Logic xử lý nghiệp vụ và logic chuyên sâu của từng aspect. | Ứng dụng sử dụng các thư viện. |

Một **thư viện dùng chung** không đồng nghĩa với “nơi bỏ mọi mã không biết đặt ở đâu”. Chỉ nên chia sẻ những khái niệm có hợp đồng ổn định và thực sự được nhiều module dùng. Ví dụ, giao diện AroundAdvice có thể thuộc lõi chung, còn quy tắc “chỉ ghi audit cho đơn hàng đã thanh toán” thuộc chính sách hoặc ứng dụng sở hữu nghiệp vụ đó.

**Nguyên tắc chủ đạo:** target nghiệp vụ không phụ thuộc vào lớp aspect cụ thể. Ứng dụng biết những aspect nào cần dùng khi lắp ghép; aspect phụ thuộc vào API tối thiểu và các dịch vụ được inject, không đi ngược vào entry point của ứng dụng.

## 3. Kiến trúc phụ thuộc một chiều

Một cách tổ chức ở cấp module có thể là:

~~~text
                    host-app
                     /  |  \
                    v   v   v
          aop-aspects  aop-engine   app-config
                 \       /          (ứng dụng sở hữu)
                  v     v
                aop-contract

    domain-business  <--- được host-app lắp với advice
          |
          +--- không tham chiếu aop-aspects hay aop-engine
~~~

Sơ đồ diễn tả **quan hệ sử dụng**, không yêu cầu mọi dự án phải xuất bản bốn artifact riêng. Với một chương trình nhỏ, các ranh giới này có thể là những package trong một artifact; khi cần tái sử dụng nhiều nơi, mới cân nhắc tách thành các module/JAR độc lập.

### 3.1. aop-contract: API tối thiểu

Lõi định nghĩa thao tác continuation như proceed và hợp đồng quanh join point. Nếu cần metadata về phương thức, tham số, đích, context, danh tính yêu cầu, thiết kế các kiểu dữ liệu đó **bất biến hoặc có quy tắc mutability rõ**, tránh làm API trở thành “túi” chứa mọi dữ liệu. Không ràng buộc hợp đồng vào một engine/proxy cụ thể nếu mục tiêu là tái sử dụng.

**Lưu ý:** mỗi lần gọi proceed có thể thực thi phần còn lại của chuỗi. Một số advice quanh join point cho phép gọi nhiều lần hoặc bỏ qua; việc đó phải được thể hiện trong hợp đồng, tài liệu và phép thử.

### 3.2. aop-aspects: chính sách độc lập với bootstrap

Aspect hiện thực một mối quan tâm rõ ràng. Ví dụ tracing chỉ quyết định **sự kiện nào được ghi**, định dạng nào và xử lý lỗi của việc ghi; nó không nên tự đọc biến môi trường hoặc quyết định lớp nghiệp vụ nào cần được bọc. Kiểm tra quyền chỉ nhận nguồn kiểm tra quyền/phán quyết thông qua giao diện; không nên phụ thuộc vào implementation của ứng dụng khác.

Chia một aspect quá lớn thành những advice có trách nhiệm dễ kiểm thử, nhưng tránh tách tùy tiện đến mức một quy tắc phải chạm hàng chục artifact. Dùng các lớp phụ trợ có thể tái sử dụng trong chính thư viện aspect nếu chúng chỉ phục vụ nội bộ chính sách.

### 3.3. app-config: đầu vào được kiểm tra và có kiểu rõ

Cấu hình quyết định chính sách nào hoạt động, với ngưỡng nào, thứ tự ưu tiên nào, và join point nào được chọn. Lớp chuyển đổi cấu hình chịu trách nhiệm đọc nguồn (tham số chạy, tệp, biến môi trường hoặc nguồn cấu hình được hỗ trợ), kiểm tra schema và tạo **đối tượng cấu hình có kiểu**. Advice nhận đối tượng hoặc những giá trị đã kiểm tra.

Một tùy chọn cấu hình không hợp lệ nên được báo rõ khi khởi động (*fail fast*) nếu nó có thể khiến chính sách bảo vệ không hoạt động. Không tự động chuyển mọi lỗi parse thành giá trị mặc định thuận tiện.

### 3.4. host-app: composition root và entry point

Composition root là chỗ duy nhất lắp các mảnh: tạo target, chọn aspect instance, sắp xếp thứ tự, kết nối với cơ chế interception rồi cấp đối tượng hoàn chỉnh cho caller. Nó có quyền biết cả domain lẫn thư viện AOP. Nhờ vậy mã nghiệp vụ không phải gọi thủ công “tracing.before” và “tracing.after” ở mỗi phương thức.

## 4. Ranh giới aspect, pointcut và cấu hình precedence

Ba khái niệm dễ bị trộn là:

1. **Advice:** phải làm gì trước/quanh/sau join point, kể cả khi target lỗi?
2. **Pointcut/selector:** join point nào được áp dụng advice?
3. **Precedence/order:** nếu nhiều advice cùng áp dụng, ai bao ngoài, ai bao trong?

Một aspect có thể mang pointcut tĩnh ở cấp mã, nhưng các quy tắc lựa chọn **phụ thuộc ứng dụng** thường nên ở lớp tích hợp/cấu hình (nếu engine cho phép). Ví dụ thư viện tracing biết cách ghi sự kiện; ứng dụng chọn chỉ tracing các lời gọi dịch vụ công khai, bỏ qua các phương thức nội bộ và chính code ghi log để tránh vòng lặp.

Trong một chuỗi around:

~~~text
caller
  TraceAdvice.enter
    AccessAdvice.check
      target.execute()
    AccessAdvice.return
  TraceAdvice.exit
caller nhận kết quả
~~~

Trace ở **ngoài** Access nhìn thấy cả lỗi bị Access chặn; Trace ở **trong** Access có thể không chạy nếu truy cập bị từ chối. Cả hai cách có thể đúng tùy mục tiêu; không nên dựa vào “tên lớp theo alphabet” hay “thứ tự đăng ký tình cờ” để suy luận precedence.

**Hợp đồng thứ tự** phải được mô tả và kiểm chứng bằng event trace: ghi advice enter, proceed, advice exit/catch, target enter. Khi hệ AOP áp dụng thứ tự theo annotation, precedence declaration, cấu hình DSL hoặc thứ tự đăng ký, phải xác minh theo **tài liệu và phiên bản engine thực tế**. Không áp đặt quy tắc của bộ chặn tự viết dưới đây cho engine khác.

## 5. Ví dụ đa tệp Java 17+: tách hợp đồng, mã aspect và cấu hình

Ví dụ nhỏ này không cần thư viện bên thứ ba. Nó sử dụng JDK dynamic proxy cho một interface nghiệp vụ và dùng các package khác nhau để mô phỏng ranh giới module.

**Cấu trúc tệp:**

~~~text
demo/
├── api/
│   ├── Invocation.java
│   └── AroundAdvice.java
├── core/
│   └── AdviceChain.java
├── aspect/
│   ├── TraceAdvice.java
│   └── AccessAdvice.java
├── config/
│   └── AspectSettings.java
└── app/
    ├── OrderService.java
    └── Main.java
~~~

Tám tệp dưới đây là **mã đầy đủ**. Trong ví dụ chúng biên dịch cùng classpath để dễ học; khi tách thành artifact khác nhau, cần giữ đúng hướng phụ thuộc đã nêu. Thứ tự danh sách advice được chọn rõ: phần tử đầu tiên là vòng **ngoài cùng**.

### 5.1. API chung: demo/api/Invocation.java

~~~java
package demo.api;

@FunctionalInterface
public interface Invocation {
    Object proceed() throws Throwable;
}
~~~

**Invocation** đóng vai trò continuation. Nó không biết domain OrderService, cách lấy cấu hình hoặc cơ chế proxy.

### 5.2. API chung: demo/api/AroundAdvice.java

~~~java
package demo.api;

@FunctionalInterface
public interface AroundAdvice {
    Object apply(Invocation next) throws Throwable;
}
~~~

Hợp đồng đơn giản nhận một continuation và có thể trả kết quả hoặc ném lỗi. Ví dụ cố ý giữ API nhỏ; các thư viện AOP thực tế có thể cần InvocationContext chứa join point, Method, tham số và metadata, đồng thời cần hợp đồng rõ về xử lý nhiều lần proceed.

### 5.3. Lõi chặn lời gọi: demo/core/AdviceChain.java

~~~java
package demo.core;

import demo.api.AroundAdvice;
import demo.api.Invocation;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.List;

public final class AdviceChain {
    private AdviceChain() {}

    public static <T> T wrap(Class<T> contract, T target,
                             List<AroundAdvice> advices) {
        if (!contract.isInterface() || !contract.isInstance(target)) {
            throw new IllegalArgumentException("target must implement interface");
        }
        return contract.cast(Proxy.newProxyInstance(
                contract.getClassLoader(), new Class<?>[]{contract},
                (proxy, method, args) -> {
                    Invocation current = () -> {
                        try {
                            return method.invoke(target, args);
                        } catch (InvocationTargetException wrapper) {
                            throw wrapper.getCause();
                        }
                    };
                    for (int i = advices.size() - 1; i >= 0; i--) {
                        AroundAdvice layer = advices.get(i);
                        Invocation next = current;
                        current = () -> layer.apply(next);
                    }
                    return current.proceed();
                }));
    }
}
~~~

Phần lõi dựng chain bằng cách đi ngược danh sách, nên advice thứ nhất được thực thi trước khi vào những advice còn lại và nhận kết quả sau cùng. Target được gọi qua reflection; InvocationTargetException được mở để advice nhìn thấy exception gốc.

Đây là ví dụ **chặn qua interface proxy**, chưa phải một engine AOP hoàn chỉnh. Một implementation sản xuất phải xác định cách xử lý các phương thức đặc biệt như equals/hashCode/toString, kiểm soát kiểu trả về, checked exception, tham số, phương thức mặc định và giới hạn của proxy. Đặc biệt, JDK proxy chỉ can thiệp lời gọi **thực sự đi qua proxy**; nó không tự weave mọi method execution trong chương trình.

### 5.4. Aspect tracing: demo/aspect/TraceAdvice.java

~~~java
package demo.aspect;

import demo.api.AroundAdvice;
import demo.api.Invocation;

public final class TraceAdvice implements AroundAdvice {
    @Override
    public Object apply(Invocation next) throws Throwable {
        System.out.println("TRACE enter");
        try {
            Object result = next.proceed();
            System.out.println("TRACE exit");
            return result;
        } catch (Throwable failure) {
            System.out.println("TRACE error=" + failure.getClass().getSimpleName());
            throw failure;
        }
    }
}
~~~

TraceAdvice chỉ biết hợp đồng invocation, không biết OrderService hay tham số dòng lệnh. Trong ứng dụng thật, thay System.out bằng một abstraction xuất sự kiện/log và quy định cách xử lý khi hệ ghi log thất bại; không được làm mất exception nghiệp vụ một cách ngẫu nhiên.

### 5.5. Aspect kiểm tra điều kiện: demo/aspect/AccessAdvice.java

~~~java
package demo.aspect;

import demo.api.AroundAdvice;
import demo.api.Invocation;
import java.util.Objects;
import java.util.function.BooleanSupplier;

public final class AccessAdvice implements AroundAdvice {
    private final BooleanSupplier allowed;

    public AccessAdvice(BooleanSupplier allowed) {
        this.allowed = Objects.requireNonNull(allowed);
    }

    @Override
    public Object apply(Invocation next) throws Throwable {
        if (!allowed.getAsBoolean()) {
            throw new SecurityException("Denied");
        }
        System.out.println("CHECK allowed");
        return next.proceed();
    }
}
~~~

AccessAdvice nhận một dependency cung cấp quyết định qua BooleanSupplier. Đây chỉ là **điều kiện giả lập để chứng minh wiring**, không phải hệ phân quyền thực tế; với authorization thật, cần danh tính tin cậy, ngữ cảnh yêu cầu, chính sách mặc định từ chối, xử lý lỗi nguồn quyền và kiểm thử đường đi không được bảo vệ.

### 5.6. Cấu hình có kiểu: demo/config/AspectSettings.java

~~~java
package demo.config;

public record AspectSettings(boolean tracing, boolean allowRequest) {
    public static AspectSettings parse(String[] args) {
        boolean tracing = true;
        boolean allowRequest = true;
        for (String arg : args) {
            switch (arg) {
                case "--no-trace" -> tracing = false;
                case "--deny" -> allowRequest = false;
                default -> throw new IllegalArgumentException("Unknown option: " + arg);
            }
        }
        return new AspectSettings(tracing, allowRequest);
    }
}
~~~

Record chứa giá trị bất biến sau khi parse. Hai tham số của ví dụ giúp tạo các kịch bản kiểm tra có đầu ra xác định. Giá trị allowRequest là **dữ liệu giả lập trong demo**, không phải cấu hình được khuyến nghị để tắt một cơ chế bảo vệ khi triển khai thực tế.

Cấu hình được tạo một lần ở composition root và truyền vào constructor/lambda của aspect. Advice không tự gọi System.getenv hay đọc tệp mỗi lần chạy. Nếu ứng dụng hỗ trợ đổi cấu hình lúc chạy, cần chính sách áp dụng snapshot nhất quán và một thiết kế reload an toàn riêng.

### 5.7. Hợp đồng nghiệp vụ: demo/app/OrderService.java

~~~java
package demo.app;

public interface OrderService {
    String create(String sku);
}
~~~

Hợp đồng nghiệp vụ không import bất kỳ mã aspect nào.

### 5.8. Ứng dụng lắp ráp: demo/app/Main.java

~~~java
package demo.app;

import demo.api.AroundAdvice;
import demo.aspect.AccessAdvice;
import demo.aspect.TraceAdvice;
import demo.config.AspectSettings;
import demo.core.AdviceChain;
import java.util.ArrayList;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        AspectSettings settings = AspectSettings.parse(args);
        OrderService target = sku -> {
            System.out.println("BUSINESS order=" + sku);
            return "ok:" + sku;
        };

        List<AroundAdvice> advices = new ArrayList<>();
        if (settings.tracing()) {
            advices.add(new TraceAdvice());
        }
        advices.add(new AccessAdvice(settings::allowRequest));
        OrderService service = AdviceChain.wrap(OrderService.class, target, advices);

        try {
            System.out.println("RESULT " + service.create("BOOK-1"));
        } catch (SecurityException denied) {
            System.out.println("RESULT blocked");
        }
    }
}
~~~

Main là **composition root**: chỉ Main biết mình dùng cả TraceAdvice, AccessAdvice, AspectSettings, AdviceChain và OrderService. Target nghiệp vụ vẫn chỉ xử lý SKU. Đăng ký theo thứ tự **TRACE ngoài ACCESS**, vì thế khi ACCESS từ chối, TRACE nhìn thấy và ghi exception.

### 5.9. Biên dịch và chạy

Chạy trong thư mục **chứa thư mục demo/**. Lệnh có danh sách tệp tường minh nên dùng được trong shell Bash lẫn PowerShell, với JDK 17+:

~~~bash
javac -d out demo/api/Invocation.java demo/api/AroundAdvice.java demo/core/AdviceChain.java demo/aspect/TraceAdvice.java demo/aspect/AccessAdvice.java demo/config/AspectSettings.java demo/app/OrderService.java demo/app/Main.java
java -cp out demo.app.Main
~~~

**Stdout chế độ mặc định, đã kiểm chứng với JDK 21:**

~~~text
TRACE enter
CHECK allowed
BUSINESS order=BOOK-1
TRACE exit
RESULT ok:BOOK-1
~~~

Tắt riêng tracing để thấy việc điều khiển thành phần nằm ở cấu hình và composition root:

~~~bash
java -cp out demo.app.Main --no-trace
~~~

~~~text
CHECK allowed
BUSINESS order=BOOK-1
RESULT ok:BOOK-1
~~~

Thử nhánh từ chối giả lập để thấy TRACE nằm ngoài ACCESS:

~~~bash
java -cp out demo.app.Main --deny
~~~

~~~text
TRACE enter
TRACE error=SecurityException
RESULT blocked
~~~

Ba kết quả cho thấy **cùng một business target**, thay đổi chính sách và cấu hình ở bên ngoài target, không cần chèn lời gọi tracing/authorization trong mã create(). Đây là lợi ích thiết kế cốt lõi của tách mã AOP.

**Giới hạn của ví dụ:** không có pointcut matcher tổng quát, bộ giải quyết precedence của engine, interception của field access, constructor, hoặc weaving bytecode. Wrapper trong ví dụ áp dụng chain cho mọi phương thức được gọi qua interface proxy; trong một hệ triển khai thực, phải ràng buộc đúng tập join point và ngăn interceptor tác động vào những lời gọi không phù hợp.

## 6. Phân ranh giới khi chuyển từ package sang JAR/module độc lập

Ví dụ được biên dịch một lần cho dễ thực hành. Khi nhiều ứng dụng cùng sử dụng một bộ aspect, tổ chức thành artifact có thể là:

~~~text
aop-contract/     -> around advice API, invocation/context model
aop-engine/       -> proxy adapter hoặc tích hợp weaving, phụ thuộc contract
aop-aspects/      -> trace/audit/retry implementations, phụ thuộc contract
host-app/         -> config, domain, entry point; phụ thuộc các phần cần dùng
~~~

**Không nhất thiết xuất bản thư viện riêng cho mỗi aspect**. Chỉ tách artifact khi có nhu cầu vòng đời độc lập, khách hàng sử dụng chung hoặc ranh giới trách nhiệm rõ. Nếu aop-aspects cùng thay đổi và xuất bản với host-app, tách JAR có thể chỉ tăng chi phí quản lý.

Ma trận phụ thuộc mong muốn:

| Thành phần | Được tham chiếu | Tránh tham chiếu |
| --- | --- | --- |
| aop-contract | API Java ổn định, kiểu dữ liệu nền tảng | host-app, mã domain, cấu hình triển khai |
| aop-engine | aop-contract, cơ chế proxy/weaving cụ thể | chính sách nghiệp vụ riêng |
| aop-aspects | aop-contract, abstraction logging/clock/policy thích hợp | Main, domain implementation của host-app |
| host-app | API, engine, các aspect đã chọn, domain | Không có hạn chế chiều ngược vì đây là điểm lắp ráp |

Ví dụ phụ thuộc mô tả bằng Gradle Groovy DSL **chỉ để thấy chiều tham chiếu**, không phải build script hoàn chỉnh:

~~~groovy
// aop-engine/build.gradle
dependencies {
    implementation project(':aop-contract')
}

// aop-aspects/build.gradle
dependencies {
    implementation project(':aop-contract')
}

// host-app/build.gradle
dependencies {
    implementation project(':aop-contract')
    implementation project(':aop-engine')
    implementation project(':aop-aspects')
}
~~~

Mã demo trực tiếp import AroundAdvice ở host-app; khi xuất bản, hợp đồng phải được phơi bày phù hợp (chẳng hạn API dependency hoặc phụ thuộc explicit ở consumer). Không để thư viện tùy tiện kéo theo dependency transitive khiến ứng dụng vô tình có thêm một cơ chế weaving/proxy khác.

### 6.1. Ổn định hợp đồng giữa các bản phát hành

Với thư viện dùng chung, cần công bố:

- Namespace/package ổn định cho API công khai.
- Ngữ nghĩa của proceed, quy tắc số lần gọi, cách truyền ngoại lệ và giá trị trả về.
- Tính thread-safe và vòng đời được hỗ trợ của advice/context.
- Phiên bản Java tối thiểu và những artifact runtime cần thiết.
- Quy tắc deprecation, thay đổi breaking, kiểm tra compatibility.
- Phiên bản engine AOP, đặc biệt nếu API cấu hình pointcut phụ thuộc engine.

Thay chữ ký AroundAdvice hoặc đổi ý nghĩa “thứ tự đầu danh sách” có thể phá nhiều consumer dù mã vẫn biên dịch. Hãy kiểm tra source/binary compatibility của public API và hành vi bằng contract tests trước khi phát hành.

### 6.2. Quy tắc đóng gói để tránh trùng thư viện

Một ứng dụng vô tình kéo vào hai phiên bản API AOP có thể gặp lỗi liên kết class, phương thức không tồn tại hoặc khác biệt classloader. Dùng dependency graph/lockfile hay cơ chế quản lý phiên bản phù hợp để kiểm soát. Không “shade” API công khai vào nhiều JAR khác nhau nếu các bên cần cùng một kiểu AroundAdvice; có thể khiến hai lớp có tên gần giống nhưng không tương thích về identity.

## 7. Cấu hình nên nằm ở đâu?

### 7.1. Tách giá trị cấu hình khỏi logic advice

Những ví dụ cấu hình phổ biến:

| Giá trị | Người sở hữu phù hợp | Rủi ro nếu trộn vào advice |
| --- | --- | --- |
| tracingEnabled | host-app / deployment | Khó bật/tắt có kiểm soát, khó test. |
| traceSampleRate | host-app; aspect dùng số đã kiểm tra | Parse lặp lại, không nhất quán giữa các instance. |
| retryMaxAttempts | từng ứng dụng/chính sách | Một thư viện ép retry cho mọi nghiệp vụ, tăng tác dụng phụ. |
| auditSink | lớp tích hợp chọn implementation | Thư viện khó chạy trong test, phụ thuộc hạ tầng bên ngoài. |
| pointcut expression | tầng tích hợp hoặc artifact engine-specific | Thư viện chứa tên class/domain cứng, khó tái sử dụng. |
| precedence | lớp tích hợp của engine | Thay đổi thứ tự ngầm gây lệch hành vi và xử lý lỗi. |

Nên khai báo **schema**, kiểu, mặc định có chủ đích, giá trị hợp lệ, đơn vị đo, cách ưu tiên nguồn và trạng thái thiếu bắt buộc. Ví dụ: số lần retry tối đa không âm, timeout có đơn vị, biểu thức pointcut phải biên dịch hợp lệ, hoặc cấu hình kiểm soát truy cập không được rơi về “cho phép tất cả” khi parse lỗi.

### 7.2. Thứ tự ưu tiên nguồn cấu hình

Một hệ có thể lấy giá trị từ build defaults, tệp cấu hình, biến môi trường và đối số dòng lệnh. Phải **định nghĩa precedence rõ**, chẳng hạn đối số dòng lệnh ghi đè môi trường, môi trường ghi đè tệp, còn tệp ghi đè mặc định. Đây là **một ví dụ chính sách**, không phải quy tắc chung của AOP.

Tránh việc mỗi aspect tự có thuật toán chọn nguồn khác nhau. Cung cấp một bước resolve tập trung rồi tạo **cấu hình bất biến** để ghi lại snapshot khởi động. Với secret, sử dụng cơ chế cấp phát bí mật riêng, hạn chế in giá trị nhạy cảm ra log và không đóng gói secret vào JAR.

### 7.3. Cấu hình runtime thay đổi động

Một bản cấu hình bất biến được inject lúc tạo aspect sẽ không tự thay đổi chỉ vì tệp bên ngoài vừa đổi. Nếu thật sự cần reload, thiết kế cơ chế cập nhật atomically (thay toàn bộ snapshot), quy tắc cho lời gọi đang chạy, đồng bộ các instance, audit thay đổi và rollback. Không cho advice đọc file vào mỗi lần proceed vì vừa tăng overhead, vừa gây trạng thái không nhất quán trong cùng một yêu cầu.

### 7.4. Chỉ bật tính năng có thể tùy chọn an toàn

Tracing có thể là chức năng có thể tắt trong môi trường thử nghiệm; authorization/audit bắt buộc không nên bị vô hiệu hóa bằng một flag chung dễ bị dùng nhầm. Demo có tham số --deny để minh họa nhánh policy, **không đại diện một hệ thống bảo mật thực tế**. Mỗi policy cần được phân loại: bắt buộc, có thể tùy chọn, hoặc có thể thay cấu hình; cách kiểm tra khi thiếu policy tương ứng phải rõ.

## 8. Tích hợp ba cơ chế áp dụng AOP

Ranh giới mã aspect/config/shared library vẫn hữu ích, nhưng **điểm kết nối engine** khác nhau theo cơ chế.

### 8.1. Proxy interception

Composition root tạo target, xây proxy và cấp **proxy** cho caller. Một lời gọi đi trực tiếp vào target gốc có thể bỏ qua advice; một lời gọi nội bộ trên cùng instance cũng có thể không qua interception. Các cơ chế proxy khác nhau có giới hạn khác nhau về interface, method visibility, finality và đối tượng đích.

Bài kiểm tra tích hợp quan trọng là gọi qua **cùng loại reference** mà ứng dụng thật sử dụng, không chỉ gọi advice trực tiếp. Nếu test advice chạy nhưng ứng dụng không có log, kiểm tra nơi proxy được tạo, nơi reference được truyền và điểm caller thực sự dùng.

### 8.2. Compile-time weaving

Engine có thể weave các advice vào bytecode khi build. Lớp tích hợp phải sở hữu tùy chọn compiler/weaver, nguồn aspect được nạp, pointcut, precedence và thứ tự bước build. Một thư viện aspect chỉ tồn tại trên classpath **chưa đủ** để bảo đảm target đã được weave, nếu cấu hình cần một bước riêng.

Cần lưu bằng chứng build: phiên bản weaver, cấu hình, class đầu vào/đầu ra, log các join point được áp dụng và artifact được phát hành. Nếu build có nhiệm vụ weave riêng, chạy kiểm thử trên **artifact sau weaving**, không chỉ trên class trước biến đổi.

### 8.3. Load-time weaving

Weaver có thể biến đổi lớp khi tải vào runtime, thường cần bootstrap/agent hoặc integration hook do công cụ cung cấp. Chủ sở hữu cấu hình phải xác định agent và các tùy chọn khi khởi động, các classloader cần quan sát, class/path được include/exclude và trình tự load.

Một MRE chỉ dùng proxy không chứng minh rằng load-time weaving đã chạy. Kiểm tra class đã tải qua loader nào, weave xảy ra trước hay sau khi class được định nghĩa, có module access phù hợp hay không, và phương thức thực tế có được can thiệp không. Cú pháp agent, file cấu hình và quy tắc chọn join point là **đặc thù của engine**; cần theo tài liệu phiên bản được dùng.

### 8.4. Không để engine rò vào business API

Một ứng dụng có thể phải chọn engine AOP cụ thể. Tuy nhiên, nếu muốn tái sử dụng cùng logic tracing/policy giữa nhiều engine, đặt phần adapter engine-specific ở **aop-engine** hoặc các gói adapter riêng; phần chính sách thuần phụ thuộc contract trung lập. Khi hai engine có tập join point khác nhau, đừng che giấu khác biệt đó dưới một abstraction quá hứa hẹn: tài liệu hóa các khả năng thực sự hỗ trợ.

## 9. Quản lý thứ tự, trạng thái và tác dụng phụ giữa nhiều aspect

### 9.1. Thứ tự phải kiểm thử được

Giả sử có TRACE, CHECK và RETRY. Nếu RETRY nằm ngoài CHECK, phép kiểm tra có thể lặp lại mỗi attempt; nếu CHECK nằm ngoài RETRY, nó chỉ kiểm tra trước toàn bộ hoạt động retry. Nếu TRACE nằm ngoài RETRY, trace có thể đại diện cho một yêu cầu logic; nếu TRACE nằm trong RETRY, mỗi attempt có thể có trace riêng.

Không có thứ tự đúng tuyệt đối cho mọi ứng dụng. Thứ tự phù hợp phụ thuộc **hợp đồng nghiệp vụ**, tính idempotent, các ranh giới lỗi và ngữ nghĩa đo lường. Document order và dùng test có event sequence chính xác để bảo vệ.

### 9.2. Vòng đời đối tượng advice

Một instance advice có thể phục vụ nhiều lời gọi và nhiều thread. Không lưu “request hiện tại” trong trường instance dùng chung nếu chưa thiết kế cơ chế cô lập. Dùng metadata truyền theo invocation hoặc một context có vòng đời rõ; nếu dùng ThreadLocal, cần quy tắc cleanup và xử lý khi chuyển thread.

**Bất biến thường cần kiểm tra:** một yêu cầu không bị lẫn correlation id sang yêu cầu khác; một phép gọi proceed được thực hiện đúng số lần theo hợp đồng; side effect chỉ xuất hiện khi chính sách cho phép.

### 9.3. Hiệu năng và failure policy

Advice trên hot path có thể làm tăng latency ngay cả khi business method đơn giản. Tránh parse cấu hình, phản chiếu lặp lại không cần thiết, cấp phát quá nhiều, truy cập mạng đồng bộ hoặc ghi log vô hạn ở mỗi join point. Nếu dùng cache metadata, bảo đảm tính đúng với nhiều classloader và khi thay class.

Phải quy định rõ khi subsystem của aspect thất bại: ví dụ ghi metric thất bại có thể được xử lý khác kiểm soát truy cập thất bại. Không gộp mọi Throwable vào “bỏ qua lỗi để chạy tiếp”; quyết định fail-open/fail-closed cần xuất phát từ hợp đồng từng chính sách và được kiểm thử.

## 10. Chiến lược kiểm thử theo ranh giới

| Lớp kiểm thử | Cách thực hiện | Điều được chứng minh |
| --- | --- | --- |
| **Contract test** | Gọi AroundAdvice bằng Invocation giả có counter và Throwable định trước. | Advice gọi proceed/return/throw đúng hợp đồng. |
| **Unit test cấu hình** | Parse đối số hợp lệ, sai định dạng, thiếu bắt buộc; kiểm tra immutable settings. | Chính sách mặc định, xác thực đầu vào, fail-fast. |
| **Unit test aspect** | Inject BooleanSupplier, clock/sink giả; quan sát output/events. | Quy tắc tracing/check độc lập với engine. |
| **Integration test proxy** | Gọi qua proxy thật, so sánh call count/exception với target. | Wiring, thứ tự và interception qua interface hoạt động. |
| **Integration test weaving** | Build/run bằng engine và cấu hình weaving thực, kiểm tra join point. | Aspect thật sự được áp dụng vào bytecode/runtime. |
| **Compatibility test** | Consumer biên dịch/chạy với phiên bản thư viện mới và cũ được hỗ trợ. | API và ngữ nghĩa công khai vẫn tương thích. |

Với ví dụ, kiểm tra ba stdout là smoke test hữu ích, nhưng ứng dụng thực nên dùng assertions thay vì chỉ so sánh log bằng mắt. Chẳng hạn:
- Mặc định: target chạy một lần; TRACE enter/exit xuất hiện một lần; CHECK cho phép; kết quả ok:BOOK-1.
- Không tracing: target vẫn chạy một lần; không có sự kiện TRACE; kết quả không đổi.
- Từ chối: target không chạy; TRACE ghi nhận SecurityException; caller nhận kết quả blocked.
- Thay đổi thứ tự advice (trong một test riêng): trace sự kiện phản ánh vòng ngoài/vòng trong đúng như cấu hình.

Với retry, thêm test target fail một lần rồi thành công và một test target fail hết lượt; xác nhận số lần thực thi, exception cuối, side effect và những advice nào chạy mỗi attempt. Những thuộc tính đó quan trọng hơn việc cố định tên proxy được sinh ra.

### 10.1. Kiểm thử điểm cắt

Không chỉ hỏi “advice có chạy không?”. Cần kiểm tra **nơi không được chạy**. Dựng một phương thức match và một phương thức không match, thêm các trường hợp gọi lồng nhau, phương thức helper dùng cho logging và caller sử dụng target gốc. Nếu pointcut thay đổi khiến aspect tự bắt lại lời gọi của nó, có thể tạo reentrancy hoặc recursion.

### 10.2. Kiểm thử thread và trạng thái

Khởi tạo nhiều lời gọi đồng thời với input/identity khác nhau; xác nhận context không bị rò sang nhau. Dùng CountDownLatch hoặc điều kiện đồng bộ có kiểm soát để tái hiện race. Một test dùng Thread.sleep với timing ngẫu nhiên không đủ chứng minh thread-safety.

## 11. Quy trình phát hành và triển khai thư viện AOP dùng chung

Có thể áp dụng trình tự:

1. **Khóa contract:** xác định public API, ngữ nghĩa proceed, thông tin join point, hợp đồng exception và phiên bản Java tối thiểu.
2. **Biên dịch và kiểm thử độc lập:** build contract, engine adapter và aspect library; chạy test ở từng ranh giới.
3. **Kiểm tra phụ thuộc:** xác minh không có đường vòng từ thư viện về host-app; không kéo nhiều engine/weaver ngoài chủ đích.
4. **Xuất bản artifact có phiên bản:** artifact immutable, metadata và changelog chỉ rõ API mới, thay đổi precedence hoặc cấu hình mặc định.
5. **Lắp vào ứng dụng:** khai báo phụ thuộc và cấu hình có kiểu; tạo proxy hoặc cấu hình weaving; xác nhận pointcut áp dụng đúng.
6. **Kiểm tra artifact cuối:** chạy trên cùng dạng artifact triển khai, đặc biệt với weaving; kiểm tra startup diagnostics, performance và security.
7. **Rollout có quan sát:** giám sát lỗi phát sinh từ aspect, độ trễ, số lời gọi bị chặn, tỷ lệ retry, tác dụng phụ và khả năng rollback.

Nếu dùng Java Platform Module System (JPMS), tính visibility của package, module reads/exports/opens và khả năng truy cập reflection có thể quyết định proxy/weaver chạy được hay không. Không tự mở toàn bộ package chỉ để “hết lỗi”; dùng những quyền truy cập tối thiểu được engine yêu cầu và kiểm tra trên runtime thực tế.

### 11.1. Tránh trôi cấu hình giữa môi trường

Cùng một mã aspect nhưng khác pointcut, precedence hay cờ khởi động có thể cho hành vi khác nhau. Ghi lại **cấu hình hiệu lực** (đã loại secret) cùng fingerprint/phiên bản artifact. So sánh staging và production theo những giá trị ảnh hưởng đến join point. Bản triển khai phải có cách kiểm tra “aspect mong đợi có được kích hoạt không?”, không chỉ “ứng dụng có khởi động không?”.

### 11.2. Rollback thực chất

Hạ phiên bản thư viện có thể không khôi phục trạng thái cũ nếu cấu hình hoặc bytecode đã weave đã thay đổi. Kế hoạch rollback cần lưu phiên bản artifact, cấu hình và quy trình build/weaving tương ứng. Khi thay precedence hoặc semantics của retry/audit, coi đó là thay đổi hành vi có thể ảnh hưởng dữ liệu, không chỉ refactor package.

## 12. Những kiểu tách sai thường gặp

1. **Một thư viện chung biết mọi domain.** Aspect cố import OrderService, PaymentService, InventoryService từ các app khác; mỗi thay đổi nghiệp vụ kéo theo phiên bản thư viện mới. Hãy chuyển quyết định gắn pointcut/domain mapping về từng ứng dụng hoặc adapter domain riêng.
2. **Advice tự đọc cấu hình toàn cục trong mỗi lần gọi.** Lỗi khó tái hiện, test phụ thuộc môi trường và cấu hình giữa các request có thể không đồng nhất. Parse tập trung, inject dependency và quy định snapshot.
3. **Tập trung tất cả vào một “AspectUtils” lớn.** Khó sở hữu và dễ sinh chu kỳ phụ thuộc. Giữ contract thật nhỏ; tách policy theo trách nhiệm.
4. **Ứng dụng gọi advice thủ công.** Business service import tracer, tự gọi enter/exit cho từng phương thức; mã nghiệp vụ bị dính chặt với cross-cutting concern. Chuyển wiring đến composition root nếu yêu cầu là interception xuyên suốt.
5. **Cài đặt precedence nhờ thứ tự vô tình.** Thêm một aspect mới có thể thay lỗi/return hoặc số lần retry. Công khai thứ tự và test event sequence.
6. **Đặt cơ chế weaving trong thư viện policy nhưng không nói cho consumer.** Consumer thêm dependency mà tưởng advice tự chạy. Tài liệu hóa rõ cấu hình build/runtime, agent, classloader và khả năng pointcut.
7. **Trùng public API trong nhiều artifact.** Hai class có cùng tên nhưng tải bởi classloader/phiên bản khác làm wiring lỗi. Kiểm soát version và dependency graph.
8. **Hợp đồng quá mơ hồ về proceed.** Advice gọi nhiều lần hoặc trả sớm gây tác dụng phụ ngoài ý muốn. Ghi rõ điều kiện gọi tiếp và kiểm thử.
9. **Dùng trạng thái mutable dùng chung cho từng request.** Rò dữ liệu giữa thread hoặc bị ghi đè do song song. Chuyển state vào invocation context có vòng đời rõ.
10. **Tắt mọi kiểm soát khi config lỗi.** Đặc biệt nguy hiểm với audit/authorization. Quy định fail-fast hoặc fail-closed thích hợp cho chính sách bảo vệ.
11. **Chỉ test implementation advice, bỏ integration.** Unit test pass nhưng caller dùng target gốc nên advice không chạy. Kiểm tra đường gọi thật qua proxy/weaver và pointcut.
12. **Tách module quá sớm.** Mỗi class thành một JAR làm tăng vòng đời phát hành và dependency. Chia package trước nếu chưa có nhu cầu tái sử dụng độc lập.

## 13. Bài tập áp dụng

### Bài tập A — Thêm một aspect mà không sửa nghiệp vụ

Tạo một class TimingAdvice triển khai AroundAdvice, nhận một nguồn thời gian qua constructor (ví dụ LongSupplier), đo thời gian bao quanh next.proceed() bằng khối try/finally. Trong Main, đăng ký TimingAdvice vào danh sách. Không thay đổi OrderService.java hoặc lambda xử lý đơn hàng. Viết test dùng đồng hồ giả để tính khoảng thời gian xác định, không dựa vào thời gian chạy thật.

### Bài tập B — Đổi thứ tự để quan sát phạm vi lỗi

Đưa AccessAdvice lên trước TraceAdvice. Chạy chế độ --deny. Dự đoán xem TRACE còn in “TRACE enter” hay không, giải thích bằng thứ tự vòng ngoài/vòng trong. Ghi chuỗi sự kiện trước khi chạy để kiểm tra sự hiểu đúng ngữ nghĩa proceed.

### Bài tập C — Tách thành module thật

Đưa demo/api sang module aop-contract, demo/core sang aop-engine, demo/aspect sang aop-aspects, giữ demo/config và demo/app ở host-app. Khai báo dependency một chiều như mục 6. Chạy lại ba tình huống và so sánh stdout với bản một classpath. Nếu xuất bản JAR, kiểm tra API cùng kiểu được chia sẻ giữa engine và aspect, không chứa bản sao tách biệt.

### Bài tập D — Điểm cắt của công cụ AOP thực tế

Dùng một engine AOP bạn chọn và tạo hai phương thức: một phương thức được pointcut chọn và một phương thức nằm ngoài phạm vi. Chuyển logic TRACE sang aspect của engine và cấu hình pointcut ở tầng tích hợp. Chạy test xác nhận cả **có can thiệp** và **không can thiệp**. Mô tả chính xác cơ chế (proxy, compile-time weaving hoặc load-time weaving) và những điểm khác với ví dụ JDK proxy.

## 14. Checklist thiết kế trước khi chia sẻ thư viện

- [ ] Business target không import mã aspect hoặc engine-specific adapter.
- [ ] Hợp đồng AroundAdvice/Invocation có mô tả rõ proceed, return, exception và thread-safety.
- [ ] Aspect tập trung vào chính sách; cấu hình được parse/validate bên ngoài và inject vào.
- [ ] Pointcut, precedence và cơ chế interception có người sở hữu và cách kiểm chứng cụ thể.
- [ ] Composition root tạo các đối tượng và truyền proxy/đối tượng đã weave theo đúng đường gọi sử dụng thực.
- [ ] Package/artifact phụ thuộc một chiều, không có vòng và không nhân bản API dùng chung.
- [ ] Test gồm unit contract, cấu hình, riêng aspect, integration với cơ chế AOP thật và trường hợp không được can thiệp.
- [ ] Có quản lý phiên bản, compatibility, cấu hình hiệu lực, artifact cuối và đường rollback.
- [ ] Những cơ chế bảo vệ bắt buộc không bị vô hiệu hóa bởi cờ cấu hình thiếu kiểm soát.
- [ ] Chi phí runtime, state per-invocation, behavior khi lỗi và retry/side effect đã được đánh giá.

**Kết luận kỹ thuật:** Tách đúng không dừng ở vị trí tệp. **Hợp đồng** cho các phần nói cùng một ngôn ngữ; **aspect** hiện thực chính sách; **cấu hình** chọn cách áp dụng; **composition root/engine** nối advice với join point thật. Khi ranh giới và chiều phụ thuộc rõ, có thể thay chính sách, môi trường cấu hình hoặc cơ chế proxy/weaving với phạm vi tác động có thể đo được, đồng thời giữ nghiệp vụ độc lập và đủ bằng chứng để kiểm thử tích hợp.
