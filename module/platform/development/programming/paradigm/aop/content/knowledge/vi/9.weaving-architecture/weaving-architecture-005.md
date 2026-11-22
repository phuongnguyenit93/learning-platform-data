# Phạm vi dệt trong một mô-đun và giữa các mô-đun trong AOP

**Weaving (dệt aspect)** là quá trình kết hợp mã của các **aspect/advice** vào những **join point** được **pointcut** chọn. Trong ứng dụng nhỏ, ta dễ nghĩ “khai báo aspect là nó áp dụng cho mọi nơi”. Nhưng khi ứng dụng được chia thành nhiều **mô-đun (module)**, câu hỏi quan trọng là:

**Mã nào được đưa vào phạm vi dệt, ở phía gọi hay phía thực thi, và những ranh giới mô-đun nào có thể hoặc không thể được cơ chế AOP vượt qua?**

Một aspect định nghĩa trong mô-đun A không tự động can thiệp mọi lời gọi ở mô-đun B. Ngay cả khi A gọi được API của B, cơ chế weaving vẫn phải **nhìn thấy đúng join point**, được phép instrument phần mã cần thiết, kết hợp advice vào artifact/bytecode hoặc đi qua interceptor thích hợp, rồi đưa kết quả đã dệt vào runtime thật.

Có hai phạm vi cần phân biệt:

- **Dệt trong một mô-đun (intra-module weaving):** điểm can thiệp và mã thực thi liên quan nằm trong phạm vi cùng một đơn vị mã/build/deployment do ta kiểm soát. Có thể bao gồm cả các lời gọi nội bộ nếu công cụ hỗ trợ kiểu join point và phương thức dệt đó.
- **Dệt giữa các mô-đun (inter-module weaving):** pointcut/advice cần áp dụng tại ranh giới gọi từ module này tới module khác, hoặc tại execution của target ở module phụ thuộc. Thành công phụ thuộc cấu trúc module, cách phân phối artifact, visibility, class loading và nơi weaving thực sự diễn ra.

> **Phạm vi kiến thức:** Bài này nói về AOP nói chung, từ nền tảng tới tổ chức weaving nâng cao. Java 17+ được dùng để minh họa module graph và giới hạn interceptor. Không có một mô hình module hoặc một engine AOP chung bắt buộc; các biểu thức chọn điểm dạng `module=A` hay `execution(B.Service.method)` dưới đây là **ký pháp mô tả ý tưởng**, không phải cú pháp pointcut có thể dùng nguyên xi trong mọi công cụ.

## 1. Ôn lại: aspect, pointcut, join point và weaving

Trong mô hình AOP:

1. **Aspect** đóng gói một mối quan tâm cắt ngang, ví dụ audit, tracing hoặc đo thời gian.
2. **Pointcut** là tiêu chí chọn join point.
3. **Join point** là vị trí/sự kiện có thể can thiệp, ví dụ một lời gọi hoặc một lần thực thi phương thức, tùy engine.
4. **Advice** là hành vi được áp dụng tại điểm khớp.
5. **Weaving** là hoạt động kết hợp advice với mã/chương trình để hành vi đó thực sự xuất hiện khi chạy.

```text
Pointcut + Advice + Chương trình cần can thiệp
                    |
               Weaving process
                    |
                    v
           Chương trình sau weaving
                    |
                    v
        Join point khớp -> advice thực thi
```

**Pointcut được viết đúng không có nghĩa advice đã được weave.** Một class có thể tồn tại, annotation có thể hiện diện, hoặc interceptor có thể được tạo, nhưng nếu đường thực thi không đi qua nó thì hành vi cắt ngang không xảy ra.

Weaving có thể diễn ra khi biên dịch, sau biên dịch, khi class được nạp, hoặc được mô phỏng ở ranh giới runtime bằng proxy/interceptor. Các cơ chế này có **phạm vi mã và join point khác nhau**; chúng không phải những tên gọi tương đương của cùng một thao tác.

## 2. “Mô-đun” có thể chỉ những ranh giới khác nhau

Từ *module* không có một nghĩa duy nhất. Trước khi phân tích intra-/inter-module weaving, cần xác định đang nói về **đơn vị nào**.

| Loại ranh giới | Ví dụ | Hệ quả đối với AOP |
| --- | --- | --- |
| **Package** | `com.example.billing` | Là nhóm tên và ranh giới truy cập Java, không nhất thiết là đơn vị build |
| **Module build** | Một project con sinh ra JAR | Có artifact và quy trình compile riêng; thường là đơn vị được đưa vào hoặc bỏ ra khỏi weaving |
| **JAR/library** | `billing-api.jar`, `billing-impl.jar` | Mã có thể đóng gói tách biệt; weaving cần xử lý JAR chứa join point tương ứng |
| **Java Platform Module System (JPMS)** | `module com.example.billing { ... }` | Có module descriptor, readability, exports, opens, module path |
| **Class loader domain** | Module/plugin được nạp bởi class loader riêng | Quyền truy cập và class identity có thể ảnh hưởng khả năng dệt |
| **Runtime process/service** | Hai dịch vụ chạy trên JVM khác nhau | Không có call stack và object graph chung; AOP local không tự dệt xuyên tiến trình |

**Một package không tự là một module JPMS.** Một JAR cũng không nhất thiết là **named JPMS module**; nó có thể chạy trên classpath (unnamed module), là automatic module, hoặc chứa `module-info.class`. Một module build có thể chứa nhiều package và có thể tạo một hoặc nhiều artifact.

Vì thế, câu “weave trong module Billing” cần giải thích thêm: **weave class nào, artifact nào, ở build step nào, class loader nào, và loại join point nào**?

### Ranh giới tiến trình không phải ranh giới weaving bytecode thông thường

Nếu module A gọi module B **trong cùng JVM**, một cơ chế instrument bytecode có thể có khả năng can thiệp ở các phía phù hợp. Nhưng nếu “B” là một dịch vụ ở **process khác**, trong JVM A chỉ có lời gọi client/protocol. Dệt `B.Service.process()` đòi can thiệp vào artifact/runtime của B, chứ không tự xuất hiện chỉ vì A đã được weave.

Có thể dùng tracing trên hai dịch vụ rồi nối bằng trace context, nhưng **đó là correlation qua giao thức**, không phải một method-call join point Java kéo dài xuyên mạng.

## 3. Phạm vi dệt là một tập mã cụ thể, không phải khẩu hiệu toàn cục

Hãy ký hiệu:

- `M`: tập module của ứng dụng.
- `C(m)`: các class/bytecode thuộc module `m`.
- `W`: tập class hoặc call site thực sự được công cụ đưa vào phạm vi weaving.
- `J(W)`: các join point mà công cụ có thể nhận diện trong tập đó.
- `P`: điều kiện pointcut.

Những điểm được áp dụng advice về nguyên tắc nằm trong **giao**:

```text
EligibleJoinPoints = J(W) ∩ Matches(P) ∩ SupportedByEngine
```

Đây là **mô hình tập hợp khái niệm**, không phải công thức runtime bắt buộc. Ngoài ba điều kiện này, còn có thể có ràng buộc thời điểm load class, visibility, dynamic dispatch, deployment và cơ chế interception.

### Hai loại “phạm vi” hay bị nhập nhằng

**Phạm vi khớp (matching scope):** pointcut mô tả bao nhiêu join point. Ví dụ chọn mọi execution `save(String)` trong nhóm type nhất định.

**Phạm vi dệt/bao phủ (weaving coverage):** những class, call site và đường thực thi mà engine thực sự có thể áp dụng advice.

Một pointcut rất rộng vẫn có thể cho coverage thấp nếu chỉ một JAR được weave. Một công cụ có thể instrument cả ứng dụng nhưng pointcut rất hẹp nên chỉ chọn một method. **Không thể suy luận coverage chỉ từ độ rộng của biểu thức pointcut.**

## 4. Dệt trong cùng mô-đun: các trường hợp cơ bản

Giả sử module `catalog` chứa:

```java
// Mã minh họa, không phải tệp Java độc lập.
class CatalogService {
    void publish(String id) {
        validate(id);
        save(id);
    }

    private void validate(String id) { }

    void save(String id) { }
}
```

Trong cùng một module, có ít nhất ba sự kiện cần phân biệt:

- **Execution** của `publish`.
- **Call site** bên trong `publish` phát lời gọi `validate`, `save`.
- **Execution** của `validate` và `save`.

Nếu một engine hỗ trợ instrument **bytecode của class này** và hỗ trợ đúng loại join point, nó có thể nhận diện nhiều sự kiện kể trên. Nhưng nếu cơ chế chỉ là **proxy đứng ngoài service**, một lời gọi `serviceProxy.publish(...)` có thể được intercept, còn `this.validate(...)` và `this.save(...)` bên trong target có thể đi thẳng tới thân method mà không quay ra proxy.

**Cùng module không bảo đảm self-invocation được advice.** Đây là khác biệt giữa **vị trí mã** và **đường interception**.

### Intra-module: thuận lợi, nhưng không tự động toàn diện

- Có thể kiểm soát cùng build pipeline và xử lý nhiều class trong một lần weave.
- Có thể truy cập metadata, bytecode hoặc type hierarchy dễ hơn khi chúng cùng nằm trong đầu vào build.
- Có thể quản lý cấu hình pointcut chung trong phạm vi module.
- Nhưng vẫn có giới hạn ở private/static/final, method synthetic, reflection, native method và các join point mà engine không hỗ trợ.
- Những class **không được đưa vào `W`** vẫn không được weave dù chúng thuộc cùng project build.

## 5. Dệt giữa các mô-đun: caller và callee ở hai phía

Giả sử module `checkout` gọi module `billing`:

```text
+----------------------------+       +----------------------------+
| Module checkout            |       | Module billing             |
| CheckoutFlow.submit()      |       | InvoiceService.create()    |
|       |                    |       |      ^                     |
|       +--- CALL ---------- +------>+------ EXECUTION ----------|
|                            |       |                            |
+----------------------------+       +----------------------------+
```

Mối quan tâm cắt ngang có thể đặt ở:

1. **Phía caller:** “Mọi lời gọi phát từ `checkout` sang API billing phải được thống kê.” Nếu chọn **method call join point**, vị trí cần instrument có thể nằm **trong bytecode của checkout**.
2. **Phía callee:** “Mọi lần `InvoiceService.create` thực thi đều phải được audit, bất kể caller nào.” Nếu chọn **method execution join point**, vị trí cần instrument có thể nằm **trong bytecode của billing**.
3. **Một lớp trung gian:** một proxy/API gateway nội bộ trong JVM nhận lời gọi trước khi tới target. Coverage phụ thuộc **mọi lời gọi cần bảo vệ có thực sự đi qua lớp này không**.

Đây là ba chiến lược khác nhau. Việc khai báo aspect trong module `observability` không tự khiến cả caller và callee được instrument.

### Bảng nơi cần dệt theo mục tiêu

| Yêu cầu | Vị trí quan sát tự nhiên | Mã thường cần được weave/intercept |
| --- | --- | --- |
| Ghi tất cả lời gọi **từ Checkout** tới Billing | Method call ở checkout | Caller `checkout` |
| Audit mọi lần `Billing.create` thật sự chạy | Method execution ở billing | Callee `billing` |
| Chỉ theo dõi API đi qua một cổng chung | Interceptor tại cổng | Đường gọi qua cổng |
| Theo dõi cả direct call và self-invocation | Execution instrumentation phù hợp | Các method target được instrument |
| Đo tổng thời gian end-to-end qua mạng | Client/server instrumentation + context | Hai phía riêng, nối bằng metadata giao thức |

Bảng là định hướng kiến trúc, **không khẳng định engine nào cũng hỗ trợ call/execution và mọi kiểu method**.

## 6. Một module định nghĩa aspect, module khác chứa target

Giả sử:

```text
observability-module
    └── TraceAspect

business-module
    ├── OrderService
    └── InvoiceService
```

Có ít nhất ba vấn đề độc lập:

**(1) Advice có sẵn ở thời điểm weaving không?** Engine cần tìm được định nghĩa aspect/advice và type cần thiết. Nếu aspect nằm trong một artifact không được đưa vào build/load path thích hợp, việc dệt có thể không thực hiện được hoặc artifact được tạo không chạy được.

**(2) Business bytecode có được weave không?** Nếu engine chỉ xử lý `observability-module` mà không xử lý `business-module`, có thể **không có execution join point nào của business được biến đổi**. Aspect ở module riêng không tự biến đổi class ở module còn lại.

**(3) Runtime có nạp đúng kết quả đã weave không?** Một build có thể tạo artifact woven, nhưng runtime lại load JAR gốc, cache cũ hoặc class từ đường khác. Điều này tạo lỗi “build báo weave thành công nhưng advice không bao giờ chạy”.

Tách module chứa aspect là lựa chọn tổ chức mã tốt, nhưng **weaving boundary** phải được cấu hình cho các module có join point cần bao phủ.

### Module chứa interface khác module chứa implementation

Một API có thể nằm trong `billing-api` còn implementation trong `billing-impl`. Nếu pointcut chọn **call tới interface**, mã phát lời gọi có thể nằm ở module client. Nếu chọn **execution của implementation**, class được instrument nằm ở module implementation.

Dệt riêng `billing-api` thường **không đủ** để dệt thân phương thức implementation nằm trong artifact khác. Interface có thể chỉ định hợp đồng, còn thân logic nằm nơi khác. Đây là vấn đề đặc biệt quan trọng khi dùng layered architecture.

## 7. Những cơ chế weaving và phạm vi module tương ứng

| Cơ chế | Thời điểm | Phạm vi cần kiểm soát | Giới hạn cần xác minh |
| --- | --- | --- | --- |
| **Compile-time weaving** | Khi biên dịch mã | Source/module được đưa vào compiler/weaver | Source/binary của dependency có thể không nằm trong đầu vào |
| **Post-compile weaving** | Sau biên dịch, trước chạy | Class/JAR cụ thể bị biến đổi | Phải deploy **artifact đã dệt**, không phải bản gốc |
| **Load-time weaving** | Khi JVM nạp class | Class loader, agent, cấu hình chọn class | Class đã nạp trước khi agent áp dụng có thể cần cơ chế khác; ranh giới loader quan trọng |
| **Runtime proxy/interceptor** | Khi caller đi qua đối tượng trung gian/hook | Lời gọi thật đi qua interceptor | Direct call/self-invocation dễ bỏ qua |
| **Build-time generated wrapper** | Khi build hoặc generate source | API và call site sử dụng wrapper | Wrapper không tự thay những lời gọi không sử dụng nó |

**Proxy không nhất thiết là bytecode weaving.** Proxy giúp minh họa interception và phạm vi đường gọi, nhưng không được dùng làm bằng chứng rằng method body của target đã được biến đổi.

### Compile-time: cần đưa đúng module vào pipeline

Nếu có modules `A` và `B`, và pointcut chọn call site trong A, compiler/weaver cần xử lý mã call site của A. Chỉ compile B với aspect mà không instrument caller không bảo đảm call advice trong A sẽ tồn tại.

Nếu pointcut chọn execution ở B, cần instrument method execution trong B. Một số toolchain có thể đọc aspect từ artifact khác, một số có thêm điều kiện về compiler, plugin hoặc classpath/module path. Nguyên lý ổn định là: **đưa đúng mã cần thay đổi vào quá trình weaving**.

### Post-compile: kiểm soát artifact đầu ra

Pipeline thường có dạng:

```text
Compile module A -> A.jar
Compile module B -> B.jar
                 |
          Post-compile weave
                 |
          A-woven.jar / B-woven.jar
                 |
          Runtime loads chosen artifacts
```

Không nhất thiết cần dệt cả A và B. Phải chọn theo **loại join point cần có**. Việc dệt nhầm artifact hoặc đưa bản gốc vào runtime có thể khiến test nhận kết quả bất ngờ. Các bước đóng gói, shading, ký JAR hoặc biến đổi bytecode khác phải được sắp xếp nhất quán trong pipeline.

### Load-time: phạm vi phụ thuộc class loading

Load-time weaving có thể can thiệp khi class được JVM định nghĩa, nếu agent/transformer được cài đặt đúng thời điểm và class nằm trong phạm vi xử lý. Nhưng các điểm cần kiểm chứng gồm:

- Transformer có được gọi cho class ở module mục tiêu không?
- Class đã được định nghĩa trước khi transformer sẵn sàng chưa?
- Có class loader khác/child loader không?
- Bytecode có bị một transformer khác biến đổi hay không?
- Có cần quyền truy cập module hoặc cấu hình mở package phù hợp?
- Một số loại class/JDK internals có nằm ngoài phạm vi được phép không?

Không hứa rằng một “công tắc LTW” sẽ dệt mọi class trong cả JVM.

## 8. Java JPMS không đồng nghĩa với cơ chế weaving

**Java Platform Module System (JPMS)**, có từ Java 9 và phù hợp với Java 17+, cho phép tổ chức **named modules** bằng `module-info.java`. JPMS quản lý **module readability** và **khả năng truy cập package**; nó **không tự triển khai pointcut hoặc advice**.

Ví dụ:

```java
module com.example.core {
    exports com.example.core.api;
}
```

Một module khác:

```java
module com.example.app {
    requires com.example.core;
}
```

Từ góc nhìn JPMS:

- `requires com.example.core` tạo sự phụ thuộc/khả năng đọc module khi điều kiện resolution phù hợp.
- `exports com.example.core.api` cho phép truy cập các public type/member phù hợp từ module đọc được.
- Package implementation **không export** vẫn có thể dùng **nội bộ** trong core; app không tự import các public class trong package không export đó như API public.
- `opens` dùng cho trường hợp reflective access sâu theo quy tắc module. Nó **khác** với `exports`.
- `open module` hoặc `opens package` không tự động có nghĩa một engine AOP sẽ nhận diện và weave tất cả class trong package.
- Việc điều chỉnh module graph bằng runtime flags có thể thay khả năng truy cập, nhưng không thay thế cấu hình điểm weave và chính sách bảo mật.

**JPMS là ranh giới của ngôn ngữ/runtime; weaving là cơ chế kết hợp advice.** Hai vấn đề tương tác, nhưng không nên đánh đồng.

### `exports` và `opens` khác nhau thế nào?

| Khai báo | Ý nghĩa chính | Không có nghĩa |
| --- | --- | --- |
| `exports p;` | Công bố public API của package `p` cho module đọc được | Cho phép Reflection truy cập private members tùy ý |
| `exports p to q;` | Công bố public API có điều kiện cho module `q` | Cho mọi module khác truy cập public API |
| `opens p;` | Cho phép deep reflection trên package `p` ở runtime theo quy tắc JPMS | Biến package thành API compile-time được export |
| `opens p to q;` | Deep reflection giới hạn tới module `q` | Tự động instrument code trong `p` |
| `requires q;` | Module cần đọc module `q` | Mọi package của `q` đều được export |

Một engine thao tác bytecode có thể cần quyền riêng khác so với một proxy chỉ gọi public interface method. **Không nên tự thêm `opens` cho toàn bộ module** chỉ để “cho AOP chạy” nếu chưa có lỗi quyền truy cập cụ thể và phương án đúng phạm vi.

## 9. Ví dụ Java 17+: hai module thật, proxy cho thấy ranh giới interception

Ví dụ sau tạo **hai JPMS named modules**:

- `com.example.core`: có API và implementation. Package `com.example.core.api` được export; package `com.example.core.internal` không được export.
- `com.example.app`: phụ thuộc module core, tạo một proxy trước `PriceService` và quan sát lời gọi đi qua proxy.

Ta kiểm chứng ba đường:

1. `app → proxy → core.quote`: advice được quan sát ở ranh giới module.
2. `core.quote → core.basePrice`: lời gọi nội bộ không đi qua proxy app.
3. `app → raw core.quote`: caller gọi target trực tiếp nên không đi qua proxy.

**Phân biệt rõ:** Đây là **minh họa runtime interception**, không phải ví dụ đã thực hiện compile-time weaving vào bytecode của core. Nó chỉ ra vì sao một ranh giới module/proxy **không bao phủ tự động mọi method execution nội bộ**. Một engine bytecode weaving có thể hỗ trợ phạm vi khác.

### 9.1. Cấu trúc thư mục

```text
project/
  src/
    com.example.core/
      module-info.java
      com/example/core/api/PriceService.java
      com/example/core/api/Services.java
      com/example/core/internal/DefaultPriceService.java
    com.example.app/
      module-info.java
      com/example/app/Tracing.java
      com/example/app/Main.java
```

Tạo đúng các file bên dưới. Những tên file chứa `module-info.java` là **module descriptors**, không phải class thông thường.

### 9.2. `src/com.example.core/module-info.java`

```java
module com.example.core {
    exports com.example.core.api;
}
```

Package API được export. Package implementation `com.example.core.internal` không export, nhưng code trong core vẫn có quyền sử dụng các class nội bộ của chính module.

### 9.3. `src/com.example.core/com/example/core/api/PriceService.java`

```java
package com.example.core.api;

public interface PriceService {
    int quote(String sku);
    int basePrice(String sku);
}
```

Đây là contract public. Việc cả `quote` và `basePrice` đều nằm trên interface không có nghĩa một lời gọi từ bên trong implementation bắt buộc đi qua proxy; **proxy chỉ được dùng nếu receiver thật là proxy**.

### 9.4. `src/com.example.core/com/example/core/api/Services.java`

```java
package com.example.core.api;

import com.example.core.internal.DefaultPriceService;

public final class Services {
    private Services() { }

    public static PriceService create() {
        return new DefaultPriceService();
    }
}
```

Factory tạo implementation ở package nội bộ và trả nó qua interface public, cho phép app sử dụng API mà không import class implementation không export.

### 9.5. `src/com.example.core/com/example/core/internal/DefaultPriceService.java`

```java
package com.example.core.internal;

import com.example.core.api.PriceService;

public final class DefaultPriceService implements PriceService {
    @Override
    public int quote(String sku) {
        System.out.println("core.quote " + sku);
        return basePrice(sku) + 5;
    }

    @Override
    public int basePrice(String sku) {
        System.out.println("core.basePrice " + sku);
        return 10;
    }
}
```

`quote` **tự gọi `basePrice`** trong cùng object. Ở ví dụ này, việc gọi không đi vòng qua proxy app.

### 9.6. `src/com.example.app/module-info.java`

```java
module com.example.app {
    requires com.example.core;
}
```

App đọc module core và truy cập API được export. Không cần mở package nội bộ chỉ để tạo proxy trên interface public.

### 9.7. `src/com.example.app/com/example/app/Tracing.java`

```java
package com.example.app;

import com.example.core.api.PriceService;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class Tracing {
    private Tracing() { }

    public static PriceService wrap(PriceService target) {
        return (PriceService) Proxy.newProxyInstance(
                PriceService.class.getClassLoader(),
                new Class<?>[] { PriceService.class },
                (proxy, method, args) -> around(method, args, target));
    }

    private static Object around(
            Method method, Object[] args, PriceService target)
            throws Throwable {
        String name = method.getName();
        System.out.println("app.before " + name);

        try {
            Object result = method.invoke(target, args);
            System.out.println("app.after " + name);
            return result;
        } catch (InvocationTargetException e) {
            throw e.getCause();
        }
    }
}
```

Đây là một interceptor bao quanh lời gọi **đi qua proxy**. Hàm `around` dùng Reflection để chuyển tiếp tới target, giữ kết quả trả về và mở lỗi target từ `InvocationTargetException` nếu có.

Không gọi nó là “weaving toàn bộ core”: `Tracing` không biến đổi bytecode `DefaultPriceService` và không tự nhận diện các lời gọi nội bộ.

### 9.8. `src/com.example.app/com/example/app/Main.java`

```java
package com.example.app;

import com.example.core.api.PriceService;
import com.example.core.api.Services;

public class Main {
    public static void main(String[] args) {
        PriceService raw = Services.create();
        PriceService wrapped = Tracing.wrap(raw);

        System.out.println("result " + wrapped.quote("A"));
        System.out.println("result " + wrapped.basePrice("A"));
        System.out.println("result " + raw.quote("A"));
    }
}
```

### 9.9. Biên dịch và chạy

Đứng tại thư mục `project` chứa thư mục `src`. Lệnh sau dùng tính năng **module source path** của `javac`, không cần thư viện ngoài:

```bash
javac --module-source-path src -d out -m com.example.core,com.example.app
java --module-path out -m com.example.app/com.example.app.Main
```

**Standard output chính xác:**

```text
app.before quote
core.quote A
core.basePrice A
app.after quote
result 15
app.before basePrice
core.basePrice A
app.after basePrice
result 10
core.quote A
core.basePrice A
result 15
```

Các tệp cùng lệnh đã được kiểm chứng với một JDK hiện đại; mã sử dụng những tính năng có trong **Java 17**. Nếu chạy từ một thư mục khác, đường dẫn tương đối `src`/`out` cần được điều chỉnh tương ứng.

### 9.10. Phân tích ba đường gọi

**Đường 1 — `wrapped.quote("A")`:** caller ở module app gọi proxy, nên handler in `app.before quote`. Sau đó core thực thi `quote`, bên trong nó gọi `basePrice` và in hai dòng `core.*`. Handler nhận kết quả rồi in `app.after quote`. **Không có `app.before basePrice` bên trong `quote`** vì đó là lời gọi nội bộ trực tiếp trên target.

**Đường 2 — `wrapped.basePrice("A")`:** caller app phát lời gọi riêng qua proxy, nên handler in `before basePrice`/`after basePrice`. Đó là một lượt interception khác với lời gọi `basePrice` phát sinh từ bên trong `quote`.

**Đường 3 — `raw.quote("A")`:** app vẫn có thể gọi interface trực tiếp trên target lấy từ factory. Lời gọi vượt ranh giới module nhưng **bỏ qua proxy**, nên không có dòng `app.before`/`app.after`. Ranh giới module không buộc caller phải dùng interceptor.

### 9.11. Điều gì thay đổi nếu thực sự dệt bytecode?

Nếu một engine AOP có khả năng weave **execution entry** của `DefaultPriceService.basePrice`, advice có thể quan sát cả lời gọi nội bộ từ `quote` và lời gọi trực tiếp khác, **với điều kiện đúng class đã được weave và execution join point được hỗ trợ**.

Nếu engine chỉ weave **call site trong app**, nó có thể thấy các biểu thức `wrapped.quote` hoặc `raw.quote` theo tiêu chí, nhưng **không tự thấy call site `basePrice` trong core** nếu core không được weave. Nếu engine weave **call site trong core**, nó có thể quan sát lời gọi nội bộ `quote → basePrice` nếu loại join point phù hợp.

Sự khác biệt nằm ở **mã sở hữu join point**, không phải nơi file aspect được viết.

## 10. Sơ đồ phạm vi module và khả năng bao phủ

```text
                     MODULE APP
             +-------------------------+
             | Main / external callers |
             |     |             |     |
             |     v             |     |
             |  Proxy            |     |
             |     |             |     |
             +-----|-------------|-----+
                   |             |
         inter-module call       | direct call
                   |             |
             +-----v-------------v-----+
             | MODULE CORE             |
             | DefaultPriceService     |
             |     quote()             |
             |        |                |
             |        +--> basePrice() |
             |          intra-module   |
             +-------------------------+
```

Nếu chỉ proxy ở app, hai đường qua proxy được bao phủ, còn direct/internal call có thể không. Nếu dệt execution của target trong core, đường vào execution có thể được bao phủ bất kể caller, miễn instrument đầy đủ. Nếu dệt call join point của app, tác động chủ yếu lên vị trí gọi do app sở hữu.

**Đừng đánh đồng vị trí triển khai concern với phạm vi các điểm được instrument.** Có thể lưu aspect ở một module độc lập nhưng dệt điểm trong nhiều module khác, hoặc aspect nằm cùng module target nhưng chỉ một số class được dệt.

## 11. Chọn call hay execution khi target ở module khác?

Giả sử ba client `A`, `B`, `C` cùng gọi `SharedService.handle` trong module `Shared`.

Một pointcut **call join point** gắn với những vị trí gọi do client sở hữu:

- Dệt caller A: có thể chỉ quan sát lời gọi phát từ A.
- Dệt caller B: quan sát tương ứng từ B.
- Không dệt caller C: có thể không quan sát call site của C dù nó gọi cùng target.
- Nếu target tự gọi method khác, call site ấy nằm trong Shared chứ không thuộc A/B.

Một pointcut **execution join point** gắn với method được định nghĩa ở Shared:

- Dệt method execution của `SharedService.handle`: có thể quan sát mỗi lần method thực thi do A/B/C gọi, cả những đường trực tiếp được hỗ trợ.
- Nhưng nếu còn nhiều implementation hoặc subclass khác không được weave, vẫn có thể thiếu coverage.
- Advice execution không tự biết một caller tĩnh duy nhất; ràng buộc “chỉ caller A” thường cần cơ chế/context bổ sung.

### Bảng lựa chọn

| Câu hỏi cần trả lời | Hướng điểm can thiệp | Lý do |
| --- | --- | --- |
| “Module A gọi API B bao nhiêu lần?” | Call ở A, hoặc boundary client được bảo đảm | Quan tâm nguồn phát lời gọi |
| “B xử lý thao tác bao nhiêu lần?” | Execution ở B | Quan tâm thao tác đích thực sự chạy |
| “Mọi lời gọi nội bộ trong B đã được log chưa?” | Call sites/executions thuộc B | Caller A không chứa các call site nội bộ của B |
| “Tất cả client đều tuân thủ giới hạn chung chưa?” | Ranh giới thực thi đáng tin cậy hoặc adapter không thể bypass | Chỉ weave một client là không đủ |
| “Một lời gọi ở A có thành công end-to-end không?” | Client-side outcome cộng quan sát ở B khi cần | Return/throw ở ranh giới client khác outcome bên trong B |

**Một call event không nhất thiết tương đương một execution event:** target có thể không được vào do lỗi ở caller, around advice có thể không proceed, hoặc retry có thể gây nhiều lần execution. Vì vậy số liệu phía caller và phía callee có thể khác nhau một cách hợp lệ.

## 12. Module phụ thuộc có nằm trong quyền dệt của ứng dụng không?

Một ứng dụng có thể dùng thư viện ngoài hoặc module chỉ có binary artifact. Khả năng weave nó phụ thuộc giấy phép, quyền sửa artifact, công cụ build/runtime và cơ chế class loading.

Các trường hợp phổ biến:

**Ứng dụng sở hữu source và build của B:** dễ đưa B vào pipeline compile/post-compile weaving, nhưng vẫn cần xác định module path, artifact kết quả và bài test.

**Ứng dụng chỉ dùng binary JAR B:** một số weaver có thể dệt bytecode JAR; số khác không. Phải kiểm chứng tương thích class file, chữ ký JAR, licensing và khả năng kiểm thử bản đã biến đổi. Không tự kết luận “không có source thì không thể weave”, cũng không hứa rằng mọi JAR đều biến đổi an toàn.

**Ứng dụng chỉ gọi public API B qua proxy:** có thể instrument ở phía client mà không đổi B, nhưng coverage giới hạn ở các lời gọi đi qua proxy/adapter. Điều này không tương đương dệt execution nội bộ của B.

**B là runtime module của JDK:** can thiệp vào JDK internals có giới hạn nghiêm ngặt hơn về module, security, instrumentation, tương thích phiên bản và hỗ trợ. Không dùng wildcard weave toàn bộ JDK làm mặc định.

### Độc lập compile và nguy cơ version mismatch

Module A có thể được biên dịch với API B phiên bản cũ, còn runtime nạp B mới. Một rule dựa trên tên/chữ ký/hierarchy có thể bỏ lọt hoặc khớp nhầm khi API thay đổi. Với weaving nhúng bytecode, còn có rủi ro liên quan descriptor, method bridge và thứ tự các bước biến đổi.

Hãy coi **phiên bản artifact + phiên bản aspect/weaver + cấu hình weaving + classloader/module graph** là một cấu hình cần được test chung.

## 13. Module path, classpath và class loader

Trong Java, cùng một ứng dụng có thể phối hợp named modules trên **module path** và classpath trong **unnamed module**. Việc hỗ trợ kết hợp này phụ thuộc cấu trúc thực tế và ràng buộc JPMS.

Các điểm cần kiểm tra khi advice không chạy:

- Module đích có được resolve và load đúng từ đường dự kiến không?
- Code có chạy với `--module-path` hay vô tình đặt JAR lên `-classpath`?
- Class cần weave được nạp bởi **class loader nào**?
- Có **hai bản cùng tên class** ở những loader khác nhau không?
- Runtime có load bản đã weave hay bản chưa weave?
- Module descriptor có `requires`/`exports` đúng cho mã của ứng dụng không?
- Có lỗi truy cập Reflective API vì package chưa được mở hợp lệ không?

**Class identity trong JVM phụ thuộc tên class và class loader định nghĩa nó**, không chỉ tên đầy đủ. Một aspect được cấu hình cho class mà loader A nạp không nên mặc định tương đương class cùng tên do loader B nạp. Điều này có thể xảy ra trong kiến trúc plugin, container hoặc hot reload.

### Một module có nhiều package

Khi một JPMS module chứa cả `api` và `internal`, export `api` không làm mọi method trong `internal` tự được instrument. Ranh giới export điều khiển API access, còn weaver chọn những class/bytecode của nó theo cấu hình và khả năng runtime.

### Split package và tổ chức aspect

JPMS đặt ra các quy tắc tránh xung đột package giữa named modules trong một module graph/layer thích hợp. Không nên đặt class aspect và class target trong **cùng package name nhưng khác named module** rồi mặc định Java sẽ xem chúng như một package có thể chia sẻ quyền package-private. Một cách phổ biến là đặt aspect trong package riêng và sử dụng API/weaving phù hợp, thay vì dựa vào package-private cross-module access.

## 14. Visibility không chỉ là `public` hay `private`

Có ba nhóm quyền khác nhau:

1. **Quyền truy cập Java:** private, package-private, protected, public; trong JPMS còn có readability/exports.
2. **Quyền reflective access:** phụ thuộc API Reflection, module opens và điều kiện runtime.
3. **Khả năng instrument:** phụ thuộc compiler/weaver, class loader, transformer và join point hỗ trợ.

Một `private` method trong B không thể được app A gọi trực tiếp như public API, nhưng **nó vẫn có thể thực thi nội bộ**. Một engine bytecode weaving nhất định có thể có khả năng đặt advice lên execution của nó nếu mã được instrument và công cụ hỗ trợ. Proxy interface bên ngoài thường không bắt được private method như một lời gọi public qua proxy.

Vì vậy:

> “Không gọi trực tiếp được từ module A” không đồng nghĩa “không có join point”; còn “gọi public API được” không đồng nghĩa “đã weave mọi execution liên quan”.

### Khi nào mới cần `opens`?

Nếu một resolver/advice cần deep reflection vào một package trong named module, Java có thể áp đặt hạn chế truy cập. Một module descriptor có thể mở **đúng package cho đúng module đọc reflection**, nếu phù hợp với thiết kế và công cụ.

Nhưng không nên mở toàn bộ internals để chữa một lỗi do **weaver không instrument đúng class**. Trước tiên xác định: thất bại là **không có advice được chèn**, **lời gọi bypass interceptor**, hay **lỗi truy cập Reflection**? Ba vấn đề có cách giải quyết khác nhau.

## 15. Method visibility, overriding và dynamic dispatch xuyên module

Client module có thể gọi qua interface hoặc class cha:

```java
// Khai báo minh họa, không phải chương trình độc lập.
interface Processor {
    void process(String data);
}

class FileProcessor implements Processor {
    @Override
    public void process(String data) { }
}
```

Nếu A tham chiếu `Processor` còn B chứa `FileProcessor`, call site trong A biết chữ ký trên interface; runtime execution đi vào method implementation. Điều này ảnh hưởng matching:

- Pointcut theo **call** có thể khớp chữ ký interface ở caller.
- Pointcut theo **execution** có thể khớp class triển khai ở callee.
- Một implementation khác, hoặc một override mới, có thể thay tập execution được khớp.
- Generic type erasure/bridge methods có thể tạo method descriptor bổ sung mà weaver cần xử lý.
- Một class base được instrument nhưng subclass override không được instrument có thể tạo lỗ coverage, tùy loại join point và cách dệt.

Khi cần độ chính xác cao, hãy viết **ma trận type tĩnh của caller × runtime implementation × module chứa method × loại join point**, thay vì chỉ dựa vào tên method.

## 16. Aspects của nhiều mô-đun và thứ tự kết hợp

Ứng dụng có thể có:

```text
module observability -> TraceAspect
module security      -> AccessAspect
module business      -> OrderService
```

Nếu cả hai aspect cùng khớp `OrderService.place`, phải xác định **precedence**:

```text
Trace.before
  Access.before
    OrderService.place()
  Access.after
Trace.after
```

Đó là một thứ tự giả định. Một thứ tự khác có thể khiến Trace chỉ nhìn thấy lời gọi sau Access, hoặc Access ném lỗi trước khi Trace được vào. Nếu quanh một method có around advice, nó có thể không proceed khiến advice nằm bên trong và target không chạy.

**Mô-đun nào chứa aspect không tự quyết định thứ tự advice.** Ordering thường là một chính sách AOP riêng, không thể suy ra từ tên module, thứ tự JAR hay thứ tự khai báo source nếu công cụ không cam kết điều đó.

### Weaving nhiều lượt và advice bị dệt trùng

Trong pipeline nhiều module, có thể vô tình **dệt một artifact hai lần**, hoặc dệt thêm aspect đã được tích hợp từ bước trước. Hệ quả có thể là log trùng, metric nhân đôi hoặc behavior biến đổi nhiều lần. Một số engine có cơ chế tránh trùng, nhưng không phải bảo đảm phổ quát.

Hãy kiểm tra đầu vào/đầu ra từng bước, số advice thực tế mỗi join point và khả năng lặp lại của build. **Idempotent build pipeline** là mục tiêu khác với **idempotent business operation**; cả hai đều cần chú ý.

## 17. Module giao tiếp qua HTTP hoặc message queue

Hai “module” chạy ở hai process riêng không chia sẻ một JVM stack. Ví dụ:

```text
JVM A                           Network                 JVM B
OrderClient.send()
    |
    +-- HTTP request ----------> server.handle()
                                      |
                                      +--> BusinessService.execute()
```

AOP ở phía A có thể quan sát lời gọi client, encode trace context và đo round-trip. AOP phía B có thể quan sát server handler hoặc business execution. Nhưng **method execution ở B không phải join point trong bytecode A**.

Muốn liên kết hai hoạt động:

- Tạo hoặc chuyển **correlation/trace ID** qua header/message metadata.
- Ở phía nhận, xác thực/trích xuất dữ liệu đúng ranh giới tin cậy.
- Thiết lập context trong scope của request/task B, rồi cleanup.
- Có instrumentation phù hợp ở **cả hai tiến trình**.
- Phân biệt sự kiện client đã gửi, server đã nhận, server đã xử lý và phản hồi đã tới client.

Điều này đặc biệt quan trọng với async queue: một message có thể retry và được xử lý nhiều lần. Một advice ở phía gửi không tự bảo đảm advice ở phía nhận được thực thi chính xác một lần.

## 18. Async trong cùng JVM cũng thay đổi phạm vi quan sát

Ngay cả khi cả hai module chạy trong cùng JVM, module A có thể gọi:

```java
// Minh họa, giả sử executor và task đã được định nghĩa.
executor.submit(() -> businessService.process());
```

Có hai thời điểm khác nhau:

- **Call `submit`** xảy ra ở thread caller trong A.
- **Execution `process`** xảy ra trong worker thread, có thể ở module B.

Method call join point quanh `submit` không đồng nghĩa với execution của `process`. Nếu advice chọn dựa trên **control flow của caller** hoặc `ThreadLocal`, worker không tự nhận context ấy. Muốn quan sát đủ và nối quan hệ nhân quả, cần xác định propagation qua task boundary.

### Đo hiệu năng đúng ranh giới

- Thời gian quanh `submit` thường phản ánh **thời gian lên lịch/gửi tác vụ**, không nhất thiết bao gồm thực thi.
- Advice execution ở `process` có thể đo thời gian chạy target nếu điểm đó được weave.
- End-to-end latency cần kết hợp mốc gửi, thời gian chờ và completion.
- Result `CompletableFuture<T>` là một object trả về trước khi computation có thể hoàn tất; after-returning của method trả future không tự quan sát outcome sau này.

Không dùng một tên pointcut “business operations” để khẳng định mọi hoạt động async đều được đo đúng.

## 19. Annotation giữa module: metadata nằm ở đâu?

Một module API có thể chứa interface được đánh dấu annotation:

```java
// Minh họa, annotation và import chưa được khai báo trong snippet.
interface PaymentApi {
    @Audited
    void charge(String orderId);
}
```

Module implementation có thể override method mà không đặt lại `@Audited`. Annotation trên **interface method** không tự biến thành annotation trên override implementation theo quy tắc kế thừa method annotation của Java.

Nếu pointcut hoặc advice resolver đọc **method implementation** nhưng annotation chỉ có ở **API interface**, nó có thể không tìm thấy metadata. Có thể cần một quy tắc tìm **interface method → implementation method → class-level default**, hoặc thứ tự khác được thiết kế rõ.

Khi chạy với JPMS, khả năng truy cập các annotation type/reflective methods còn phụ thuộc module dependencies/visibility. Nhưng mở package không tự làm annotation bị thiếu xuất hiện trên một phần tử khác.

### Type retention và giai đoạn weave

Annotation có retention `SOURCE`, `CLASS` hoặc `RUNTIME`. Reflection runtime thông thường cần retention `RUNTIME`, còn công cụ phân tích source/bytecode có thể đọc metadata ở giai đoạn khác nếu được hỗ trợ.

Nếu pointcut dựa vào annotation mà một module được compile với retention không phù hợp cơ chế, advice có thể không chọn được join point dự kiến. Đây là vấn đề **metadata availability**, không phải “module B ở quá xa”.

## 20. Rủi ro kiến trúc: chính sách toàn cục chỉ được dệt một phần

Một mối quan tâm cắt ngang như audit có thể được yêu cầu áp dụng **trong toàn hệ thống**. Nhưng nếu chỉ dệt module web/client, các đường sau có thể bỏ lọt:

- Worker batch gọi trực tiếp business module.
- Một module khác dùng API business không qua proxy chung.
- Self-invocation trong business implementation.
- Reflection hoặc callback gọi method trong target.
- Một module/plugin được load muộn không nằm trong tập weaving.
- Một process khác có cùng business API nhưng chạy artifact chưa weave.

**Không sử dụng partial weaving làm lớp bảo vệ duy nhất cho bất biến nghiệp vụ hoặc authorization bắt buộc.** Nếu chính sách là ràng buộc không thể bỏ qua, phải xác định một boundary mà **mọi đường thực thi liên quan đi qua**, hoặc dệt/instrument đầy đủ và có test chứng minh coverage trong phạm vi được hỗ trợ.

### Quan sát và bảo vệ là hai mức kỳ vọng khác nhau

Mất một log có thể là lỗi observability. Mất một kiểm tra quyền là lỗi bảo mật. Với concern quan trọng, cần trả lời rõ:

1. Có chấp nhận partial coverage không?
2. Có test nào phát hiện đường bypass mới khi thêm module không?
3. Mục tiêu là **đảm bảo** hay **ghi nhận theo khả năng tốt nhất**?
4. Khi weaver/agent không hoạt động, ứng dụng có được tiếp tục khởi chạy không?
5. Nếu thiếu aspect trong một module deployment, điều gì sẽ cảnh báo người vận hành?

Phạm vi và chính sách khi lỗi phải là lựa chọn thiết kế được ghi nhận, không bị mặc định.

## 21. Hiệu năng, kích thước build và chi phí mở rộng phạm vi

Càng nhiều class được dệt, càng cần quan tâm:

- Thời gian build, kích thước artifact và chi phí transformation ở runtime.
- Các method tần suất cao bị instrument ngoài ý muốn.
- Việc thu thập context/argument/result có tạo object hoặc log quá nhiều không?
- Chi phí nhận diện join point động và đọc annotation/config.
- Tác động của advice lên inlining/JIT, stack trace, debugging và profiling.
- Số lượng aspect cùng khớp làm độ sâu chuỗi advice tăng.
- Độ phức tạp khi nâng cấp compiler, JDK, class file version và dependency.

Tối ưu không có nghĩa luôn thu hẹp weaving xuống một JAR. Nếu mục tiêu yêu cầu execution coverage trên nhiều module, thu hẹp không đúng sẽ làm mất dữ liệu. Cách hợp lý là **xác định rõ phạm vi cần thiết, kiểm tra điểm khớp thực, sau đó đo overhead**.

### Wildcard xuyên module có thể nguy hiểm

Một pattern “chọn mọi method của mọi module” dễ tạo side effect bất ngờ:

- Log sâu vào thư viện hoặc hạ tầng nội bộ.
- Advice tự gọi method cũng bị pointcut chọn, gây reentrancy.
- Serialization/logging lộ dữ liệu nhạy cảm.
- Giới hạn vòng đời trên thread hoặc asynchronous task không được xử lý.
- Mỗi lần upgrade dependency xuất hiện thêm method bị can thiệp.

Nên có **điều kiện type/package/module/artifact rõ ràng** và danh sách loại trừ cho infrastructure của chính aspect nếu phù hợp công cụ.

## 22. Lập sơ đồ weaving scope trước khi triển khai

Một tài liệu thiết kế ngắn có thể có bốn phần:

**(1) Module graph:**

```text
app (caller)
  -> api (contracts)
      -> implementation (targets)
observability (aspects)
```

**(2) Join point cần chọn:**

```text
call: app.CheckoutFlow -> api.PaymentApi.pay(String)
execution: implementation.PaymentService.pay(String)
```

**(3) Mã/artifact cần instrument:**

```text
call join point       -> weave app call sites
execution join point  -> weave implementation method bodies
```

**(4) Những đường cần kiểm thử:**

```text
app -> proxy -> target
app -> direct target
implementation -> this.otherMethod()
batch -> target
reflection -> target
worker task -> target
```

Khi bốn phần rõ ràng, mới chọn compile-time, post-compile, load-time weaving hay proxy phù hợp. Tránh quyết định theo lời quảng cáo “cross-cutting = toàn cục”; **khả năng kết hợp concern không tự tạo coverage toàn cục**.

## 23. Quy trình dệt qua nhiều module theo từng bước

1. **Định danh module thật:** package, build module, JAR, named JPMS module, class loader hoặc process?
2. **Chọn concern và join point:** audit execution ở target, hay đo lời gọi từ caller?
3. **Vẽ graph phụ thuộc:** module nào chứa interface, implementation, aspect và entry points?
4. **Xác định quyền sở hữu bytecode:** ai build/có thể biến đổi module target hoặc caller?
5. **Chọn cơ chế:** compile-time, post-compile, load-time hoặc proxy/interceptor. Không coi chúng tương đương.
6. **Chọn phạm vi class/artifact:** module nào được weave, tập package/type nào được đưa vào?
7. **Kiểm tra JPMS/access:** `requires`, `exports`, `opens` chỉ khi thực sự cần; tránh mở rộng quyền quá mức.
8. **Xử lý artifact build:** bảo đảm bản đã weave được đóng gói và nạp thực.
9. **Xác định precedence:** nếu aspect từ nhiều module cùng khớp, thứ tự có rõ ràng không?
10. **Kiểm thử đường gọi:** external/internal/direct/override/async/reflection.
11. **Đánh giá policy khi lỗi:** thiếu weaving, thiếu annotation, class không load hoặc agent lỗi có được tiếp tục không?
12. **Giám sát và nâng cấp:** thêm module hoặc dependency mới phải kích hoạt regression coverage.

Đây là quy trình **thiết kế và xác minh**; cú pháp build flags và plugin của từng AOP engine phải lấy từ công cụ được chọn, không thể suy ra từ JPMS.

## 24. Ma trận kiểm thử intra-/inter-module

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Caller và target ở cùng module | Join point tương ứng có được engine hỗ trợ và weave không? |
| Caller ở A, target ở B | Advice nằm ở call site A hay execution B? |
| Module C dùng cùng target B | Coverage có tự bao gồm C hay cần weave C? |
| B tự gọi method của chính nó | Proxy có bị bypass; bytecode execution có bao phủ? |
| Client đi qua proxy | Advice chạy đúng một lượt theo contract? |
| Client gọi raw target | Có đường bypass ngoài ý muốn không? |
| Implementation trong package không export | App có dùng API public factory/interface hợp lệ? |
| Reflection vào package không open | Có lỗi quyền truy cập; đó có thật là lỗi weaving? |
| Một method bị override ở subtype | Pointcut có áp dụng trên execution implementation mới? |
| Interface chứa annotation, implementation không | Resolver tìm đúng metadata? |
| Generic bridge method | Có advice bị trùng hoặc bỏ lọt không? |
| Một JAR được weave nhưng runtime dùng JAR gốc | Test có phát hiện artifact sai? |
| Module plugin dùng class loader riêng | Transformer/resolver có bao phủ loader đó? |
| Task chạy trên worker thread | Context, advice và outcome có đúng đường execution? |
| Gọi sang process khác | Mỗi phía có instrumentation riêng và trace propagation? |
| Hai aspect nằm ở hai module | Precedence và số lần advice chạy có ổn định không? |
| Điểm can thiệp có lỗi | Caller nhận đúng result/exception theo contract? |
| Module/phiên bản mới được thêm | Coverage regression có chạy trước phát hành? |

### Đừng chỉ assert số dòng log

Một test xác nhận “có log audit” chưa cho biết log có đúng **mỗi lần execution** và không bỏ sót đường bypass. Với các concern quan trọng, nên có:

- Counter/log riêng ở target để biết số lần execution thật.
- Counter/log riêng ở call/interception boundary.
- Test cho cả ca **phải có advice** và **không được có advice**.
- Test thay đổi một chiều **chỉ weave A**, **chỉ weave B**, **weave cả hai** nếu công cụ hỗ trợ để xác minh hiểu đúng địa điểm join point.
- Đối chiếu artifact hashes/bytecode metadata trong pipeline khi cần xác minh bản woven được deploy.

## 25. Chẩn đoán “module này không thấy advice”

Khi một method ở module B không có advice dù pointcut có vẻ đúng, hãy kiểm tra theo thứ tự:

**Bước 1 — Xác định đường gọi thật.** Caller có đang gọi object proxy, hay trực tiếp target? Có self-invocation không? Nếu target không được vào do exception ở caller, execution advice có điểm để chạy không?

**Bước 2 — Xác định loại join point.** Bạn muốn call ở caller A hay execution ở target B? Engine có hỗ trợ loại đó không?

**Bước 3 — Kiểm tra phạm vi weave.** Class/JAR chứa điểm can thiệp có nằm trong đầu vào build/transform không? Có bị exclude? Class có được load trước transformer không?

**Bước 4 — Xác định module path và loader.** Runtime có load đúng class từ đúng artifact/module/loader không? Có bản gốc lẫn bản woven không?

**Bước 5 — Kiểm tra pointcut matching.** Signature, package, type hierarchy, visibility, annotation/interface/implementation có đúng không?

**Bước 6 — Kiểm tra access.** Có lỗi JPMS exports/opens hoặc lỗi Reflection quyền truy cập cụ thể không?

**Bước 7 — Kiểm tra precedence và around.** Aspect bên ngoài có bỏ qua `proceed`, nuốt exception hoặc thay kết quả khiến advice bên trong không được gọi không?

**Bước 8 — Kiểm tra runtime task.** Lời gọi có xảy ra ở worker/process khác? Có nhầm ngữ cảnh/ThreadLocal không?

**Bước 9 — Kiểm tra output và test.** Có thể advice đã chạy nhưng logging/metric bị tắt, bị sampling hoặc sink lỗi. Tách test “advice entered” khỏi test “đã xuất log”.

Quy trình này giúp phân biệt **không dệt**, **không khớp**, **bypass**, **không đủ quyền** và **advice chạy nhưng không quan sát được kết quả**.

## 26. Các lỗi tư duy thường gặp

1. **“Aspect nằm trong module A nên chỉ tác động tới A.”** Không nhất thiết; phạm vi được quyết định bởi điểm weave và cấu hình, không chỉ nơi đặt code advice.
2. **“Aspect nằm trong module A thì tự tác động mọi module.”** Cũng không; target/caller cần được đưa vào cơ chế can thiệp.
3. **“Hai method cùng module chắc chắn có self-invocation interception.”** Không đúng với nhiều mô hình proxy.
4. **“Module A có `requires B` nghĩa là AOP sẽ weave B.”** JPMS readability không tự tạo weaving.
5. **“Package được `exports` thì Reflection đọc được mọi private member.”** Không; deep reflection có quy tắc khác.
6. **“Thêm `opens` là đủ để advice chạy.”** Không, nếu bytecode chưa được weave hoặc đường gọi không qua interceptor.
7. **“Dệt interface API là đã dệt toàn bộ implementation.”** Không tự động, vì thân implementation có thể nằm ở module khác.
8. **“Call join point từ A tương đương execution join point ở B.”** Khác phía và tập đường đi được quan sát.
9. **“Một JAR đã weave là mọi runtime dùng bản woven.”** Phải xác minh deployment/module path/class loader.
10. **“Không có source của dependency thì mọi kiểu interception đều bất khả thi.”** Có thể có binary weaving hoặc proxy, tùy công cụ/quyền.
11. **“Một interceptor ở app nhận mọi lời gọi nội bộ core.”** Internal call có thể bypass proxy ở app.
12. **“Lời gọi qua HTTP cũng là method execution join point trong JVM caller.”** Không; process bên kia có stack/runtime riêng.
13. **“Annotation trên interface luôn được reflection ở implementation tìm thấy.”** Java không tự kế thừa method annotation như vậy.
14. **“Weave tất cả package giúp đảm bảo an toàn.”** Wildcard rộng có thể gây recursion, log nhạy cảm và chi phí lớn; coverage cũng còn phụ thuộc đường runtime.
15. **“Pointcut đúng cú pháp thì không cần test thực.”** Matching, weaving và runtime deployment là ba lớp khác nhau.
16. **“Thứ tự module/JAR quyết định precedence.”** Chỉ đúng khi engine cam kết semantics tương ứng; không suy đoán.
17. **“Đo submit là đo task execution.”** Không, nếu tác vụ chạy bất đồng bộ.
18. **“Một aspect audit chỉ cần tồn tại là chính sách audit được bảo đảm.”** Cần boundary đáng tin cậy và test coverage toàn bộ đường đi liên quan.

## 27. Bài tập thực hành

1. **Chạy hai JPMS module:** tạo đúng bảy file của `com.example.core` và `com.example.app`; biên dịch/chạy theo lệnh đã nêu, đối chiếu toàn bộ stdout.
2. **So sánh proxy và raw target:** bỏ lời gọi `wrapped.basePrice("A")`, giữ `wrapped.quote("A")`. Có bao nhiêu dòng `app.before basePrice` và tại sao?
3. **Đổi gọi nội bộ:** sửa `quote` để gọi `basePrice` hai lần. Dự đoán số dòng `core.basePrice` và số dòng advice.
4. **Đổi ranh giới API:** thử import trực tiếp `com.example.core.internal.DefaultPriceService` trong app. Quan sát lỗi compile do package không export, rồi giải thích vì sao factory public tránh vấn đề.
5. **Lọc theo type:** trong `Tracing.around` chỉ in advice nếu tên method là `quote`. Method `basePrice` của proxy còn chạy nghiệp vụ không?
6. **Thêm module client C:** một named module mới `com.example.batch` yêu cầu core và gọi `Services.create().quote(...)` không qua app proxy. Đường gọi đó có log `app.before` không?
7. **Thiết kế call pointcut:** một chính sách chỉ đo lời gọi từ module app tới core. Nêu nơi cần weave và vì sao dệt execution core sẽ quan sát cả batch client.
8. **Thiết kế execution pointcut:** một chính sách phải audit mọi lần `DefaultPriceService.basePrice` thực sự chạy. Nêu phạm vi target cần instrument và đường test phải bao gồm.
9. **Phân tích build:** tạo sơ đồ compile A/B → post-compile weave B → runtime. Nếu deploy B.jar gốc thì kết quả test nào phải thất bại?
10. **Module permissions:** phân biệt khi nào `exports` cần thiết và khi nào một reflection tool có thể cần `opens`. Vì sao không nên `open module` tùy tiện?
11. **Overriding:** thêm `PriceService` implementation thứ hai ở module core. Một pointcut execution chỉ chọn implementation thứ nhất có thể bỏ lọt những lượt gọi nào?
12. **Async:** đưa `wrapped.quote("A")` vào một task trên executor. Advice proxy còn chạy không, và trace ID từ ThreadLocal caller có tự đi theo worker không?
13. **Multiple aspects:** thêm một proxy audit bao ngoài proxy tracing, rồi so sánh thứ tự log khi đảo cách lồng hai proxy.
14. **Boundary mạng:** vẽ hai process A/B trao đổi HTTP. Liệt kê join point local ở mỗi phía, nơi truyền trace headers và khác biệt giữa send/receive/execute.
15. **Coverage test:** tạo ma trận có ít nhất năm đường phải có advice và năm đường không thuộc chính sách; nêu một kiểm chứng tại runtime cho từng đường.

**Tự kiểm tra:** Khi chọn execution trong B, module nào chứa bytecode cần weave? Khi chọn call phát từ A, đâu là nơi chứa call site? `requires`/`exports` có tự chạy advice không? Proxy ở app có tự intercept self-invocation trong core không? Một pointcut rộng có bảo đảm module ngoài tập instrument được bao phủ không? Cùng một target nằm trong module khác có thể được quan sát từ cả call và execution theo những điều kiện nào?

## Kết luận

**Phạm vi dệt trong một mô-đun và giữa các mô-đun không được quyết định chỉ bằng cách tổ chức package hoặc vị trí đặt aspect.** Nó phụ thuộc **loại join point**, **mã sở hữu call site hay execution entry**, **tập class/artifact được weave**, **cơ chế compile-time/post-compile/load-time/proxy**, và **module graph/class loader/deployment thực tế**. Với Java JPMS, `requires`, `exports` và `opens` xác định ranh giới truy cập, chứ không tự đưa advice vào chương trình. Một kiến trúc AOP nhiều module đáng tin cậy phải thiết kế coverage tường minh, test cả lời gọi từ ngoài lẫn lời gọi nội bộ/bypass, xác định precedence và kiểm chứng artifact đã dệt được chạy thật. Khi đó aspect mới thực hiện được mối quan tâm cắt ngang **đúng phạm vi, đủ đường đi và có thể kiểm chứng**.