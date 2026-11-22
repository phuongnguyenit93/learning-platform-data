# Phân biệt dệt tĩnh với can thiệp động lúc chạy

## 1. Mục tiêu: hiểu hành vi AOP được gắn vào chương trình lúc nào

Trong **Aspect-Oriented Programming (AOP)**, các concern cắt ngang như audit, metrics, tracing và kiểm soát truy cập có thể được tách thành **aspect**. Một aspect thường phối hợp **pointcut** (chọn các join point) với **advice** (hành vi chạy tại những điểm được chọn). Nhưng chỉ viết pointcut/advice là chưa đủ: cần một **cơ chế kết hợp** để lời gọi thực tế đi qua hành vi bổ sung.

**Weaving (dệt aspect)** là quá trình kết hợp định nghĩa aspect với chương trình mục tiêu để tạo ra hệ thống có hành vi mong muốn. Có công nghệ làm việc này khi biên dịch source, có công nghệ biến đổi bytecode đã biên dịch, có công nghệ dệt khi class được nạp; cũng có cách **can thiệp động qua proxy/interceptor trong lúc chương trình chạy** mà không phải dệt trực tiếp vào bytecode target.

Câu hỏi trọng tâm:

> **Hành vi cắt ngang đã được đưa vào mã/chương trình trước khi chạy, được biến đổi khi class được nạp, hay được định tuyến qua một lớp trung gian ở runtime?**

Từ đó suy ra nhiều khác biệt rất thực tế: các join point có thể nhìn thấy, tác động tới private/self-invocation, chi phí mỗi lần gọi, lúc phát hiện lỗi cấu hình, phạm vi cập nhật, khả năng bật/tắt, kiểm thử và vận hành.

Cần đặc biệt lưu ý hai điều:

1. **“Dệt tĩnh” không có nghĩa advice chỉ chạy khi biên dịch.** Chỉ **việc kết hợp** diễn ra trước runtime; advice vẫn chạy khi các join point tương ứng xuất hiện trong chương trình đang chạy.
2. **“Can thiệp động lúc chạy” không tự đồng nghĩa với load-time weaving.** Class transformation khi nạp và lời gọi đi qua proxy runtime là những cơ chế khác nhau, dù đều xảy ra muộn hơn giai đoạn build.

## 2. Những khái niệm nền tảng

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Join point** | Một vị trí/sự kiện thực thi được mô hình AOP công nhận, ví dụ method call hoặc method execution |
| **Pointcut** | Quy tắc chọn tập join point |
| **Advice** | Hành vi thực hiện trước/sau/bao quanh điểm được chọn |
| **Aspect** | Đơn vị tổ chức pointcut, advice và chính sách liên quan |
| **Target** | Chương trình, class hoặc đối tượng có hành vi được can thiệp |
| **Weaver** | Thành phần kết hợp aspect vào chương trình, có thể bằng thay đổi mã nguồn/bytecode |
| **Woven artifact** | Mã hoặc class artifact sau quá trình weaving |
| **Proxy / interceptor** | Lớp trung gian nhận lời gọi và quyết định chuyển tiếp/chạy hành vi bổ sung |
| **Instrumentation** | Cơ chế quan sát hoặc biến đổi mã ở cấp JVM/bytecode, thường có phạm vi và quyền cụ thể |

Điểm thường nhầm là **weaver** với **advice**. Weaver có trách nhiệm *đưa hành vi vào đúng điểm*; advice chỉ là *hành vi muốn chạy*. Một advice `before` có thể được kích hoạt ở runtime cho dù nó đã được dệt từ lúc build.

Một pointcut mô tả nhóm phương thức `public int price(int)` có thể có ý nghĩa về mặt ngữ nghĩa, nhưng một proxy chỉ bắt lời gọi đi qua nó có thể không thấy lời gọi trực tiếp vào target. Ngược lại, một weaver ở mức bytecode có khả năng nhìn các điểm sâu hơn **nếu** mô hình join point và vùng mã được dệt hỗ trợ.

## 3. “Dệt tĩnh” gồm các thời điểm nào?

### 3.1. Compile-time weaving: kết hợp trong quá trình biên dịch

**Compile-time weaving (CTW)**: định nghĩa aspect được kết hợp với chương trình khi build/biên dịch. Trình biên dịch hoặc pipeline dệt tạo artifact có hành vi AOP đã tích hợp.

Sơ đồ:

~~~text
Source nghiệp vụ + định nghĩa aspect
                |
                v
      Build / Compiler / Weaver
                |
                v
  Artifact đã dệt (class / executable)
                |
                v
         Chạy trên runtime
                |
                v
      Join point -> advice chạy
~~~

Ví dụ ý niệm: người dùng gọi `price(2)` qua một class đã được biên dịch và dệt. Khi method chạy, mã advice được chèn/ghép sẽ thực thi theo thứ tự do công cụ xác định. Thực thi advice **vẫn diễn ra ở runtime**, nhưng không cần chờ mỗi lời gọi mới tìm cách gắn aspect vào target.

**Ưu điểm có thể có:**

- Phát hiện một số vấn đề khớp điểm, cú pháp hoặc tương thích khi build thay vì để chạy thực tế mới phát hiện.
- Tạo ra artifact có phạm vi instrumentation rõ ràng, dễ kiểm thử và phát hành như một đơn vị.
- Với weaving thực sự ở class/bytecode, có thể quan sát những join point không phụ thuộc ranh giới proxy, tùy khả năng công cụ.
- Không cần định tuyến **mọi** lời gọi qua một object proxy bổ sung chỉ để có interception.

**Đổi lại:**

- Thay đổi định nghĩa dệt thường đòi hỏi build lại artifact liên quan rồi phát hành lại.
- Phải kiểm soát thứ tự các bước biên dịch, loại bytecode, tương thích thư viện và reproducible build.
- Debugging đôi khi thấy mã đã biến đổi khác source ban đầu; cần symbol/source mapping thích hợp.
- Một artifact được dệt không tự bảo đảm can thiệp mọi class: chỉ những class và join point thực sự được đưa vào phạm vi dệt.

### 3.2. Post-compile / binary weaving: dệt lên output đã biên dịch

Cũng thuộc nhóm chuẩn bị **trước khi chạy**, nhưng không nhất thiết xảy ra trong chính bước biên dịch source:

~~~text
Source -> javac -> các file .class / JAR
                           |
Aspect definitions --------+
                           |
                           v
                Binary / post-compile weaver
                           |
                           v
                  Class / JAR đã dệt
                           |
                           v
                      Run
~~~

Mục đích là áp dụng transformation lên bytecode đã có, có thể hữu ích khi một phần code được tạo bởi công cụ khác hoặc khi build pipeline tách compilation và weaving. Tuy nhiên, việc dệt thư viện bên thứ ba có thành công hay được phép hay không phụ thuộc công nghệ, phạm vi, license, module và tương thích bytecode.

**Compile-time weaving và binary weaving đều là những cách chuẩn bị artifact sớm**, nhưng pipeline, nguồn vào, khả năng debug và phạm vi thao tác có thể khác nhau. Không nên đánh đồng “dệt tĩnh” với “chỉ có một loại compiler đặc biệt”.

## 4. Load-time weaving: dệt khi class được nạp

**Load-time weaving (LTW)** thường chỉ việc áp dụng transformation khi một class đang được JVM nạp/định nghĩa. Nó nằm trên trục **thời điểm dệt** giữa build và các lời gọi về sau.

~~~text
Artifact chưa dệt
        |
        v
Classloader / quá trình định nghĩa class
        |
        +--> ClassFileTransformer / weaver (nếu cấu hình)
        |
        v
Class đã được định nghĩa với bytecode được dệt
        |
        v
Các method của class được thực thi
~~~

LTW **không nhất thiết là proxy**:

- Class bytecode có thể được biến đổi **trước khi JVM định nghĩa class đó**.
- Sau khi class được định nghĩa, các lời gọi vào method có thể thực thi hành vi đã được đưa vào bytecode mà không cần đi qua một wrapper object do ứng dụng tạo.
- Một proxy runtime thường **không sửa bytecode của target**; nó chỉ nhận lời gọi qua một tham chiếu wrapper và gọi tiếp target.
- Những class đã được định nghĩa trước khi transformer được thiết lập có thể không được xử lý bởi LTW thông thường; muốn can thiệp có thể cần khả năng **retransformation/redefinition** riêng của cơ chế instrumentation, với hạn chế cụ thể.

Vì thế không nên gọi mọi AOP engine “dynamic” là LTW, cũng không gọi mọi runtime interceptor là công cụ bytecode weaving.

**Khi kiểm tra LTW**, phải xác minh classloader, thứ tự nạp lớp, điều kiện lọc class, JDK modules, tương thích JVM/bytecode, khả năng mở module, và việc agent/weaver được khởi tạo đủ sớm. Một cấu hình pointcut đúng nhưng transformer đến sau lúc class được nạp có thể không tạo join point như mong muốn.

## 5. Can thiệp động qua proxy/interceptor trong runtime

Mô hình rất phổ biến là **định tuyến lời gọi qua proxy**. Caller giữ một tham chiếu tới đối tượng trung gian. Proxy quyết định thực hiện before/after/around rồi chuyển lời gọi tới target.

~~~text
Caller
  |
  v
Proxy / Interceptor
  |
  +--> pointcut/condition match?
  |      |
  |      +-- yes: advice trước/bao quanh
  |      +-- no:  chuyển tiếp trực tiếp
  |
  v
Target method
  |
  v
Proxy nhận kết quả hoặc lỗi
  |
  +--> advice sau / xử lý theo hợp đồng
  |
  v
Caller
~~~

**Điểm mấu chốt:** interception là **thuộc tính của đường gọi**. Nếu caller giữ target thật và gọi thẳng `target.price()` thay vì `proxy.price()`, proxy không thấy sự kiện đó. Tương tự, trong một mô hình proxy đơn giản, `this.otherMethod()` từ bên trong target cũng không đi qua tham chiếu proxy.

Khả năng cụ thể tùy kỹ thuật proxy:

- **Interface-based proxy:** có thể intercept những phương thức được truy cập qua interface proxy; cần target/contract tương thích.
- **Subclass-based proxy:** có thể override các phương thức đủ điều kiện, nhưng bị ràng buộc bởi `final`, `private` và quy tắc truy cập/override Java.
- **Interceptor chain:** có thể bao nhiều advice quanh một lời gọi và điều khiển thứ tự, nhưng không tự tạo được join point ở mọi constructor, field access hoặc catch handler.

### 5.1. “Động” có thể chỉ là thay đổi chính sách, không phải weaving lại

Một proxy có thể được tạo một lần khi ứng dụng khởi động, nhưng điều kiện bên trong được bật/tắt bằng cấu hình runtime. Ví dụ biến `enabled` quyết định lời gọi `price()` có đi qua code audit hay không.

Điều đó chứng minh **interception behavior linh hoạt theo runtime**, không chứng minh chương trình đã **viết lại bytecode** trong lúc chạy. Cơ chế điều khiển chính sách và cơ chế đưa join point vào đường gọi là hai vấn đề khác nhau.

Không được hứa rằng mọi loại proxy có thể bật/tắt không cần khởi động lại: nếu cấu hình được đọc một lần lúc khởi tạo, thay đổi file cấu hình ngoài cũng có thể chưa được áp dụng. Khả năng hot update phụ thuộc architecture/configuration thật.

### 5.2. JDK proxy và Reflection

Với Java, `java.lang.reflect.Proxy` tạo một implementation proxy cho interface; `InvocationHandler` nhận lời gọi, thông tin `Method` và các đối số. Handler có thể gọi target bằng Reflection, nhưng nếu target ném lỗi thì `Method.invoke()` bọc nguyên nhân trong `InvocationTargetException`. Adapter cần bóc `getCause()` phù hợp để giữ loại ngoại lệ mà caller nên nhận.

Bản thân `Proxy` không định nghĩa một pointcut language tổng quát. Phần điều kiện khớp (tên method, annotation, signature, v.v.) là logic của interceptor hoặc thư viện áp dụng lên proxy.

## 6. Bảng so sánh kiến trúc

| Tiêu chí | Static CTW / binary weaving | Load-time weaving | Runtime proxy / interceptor |
| --- | --- | --- | --- |
| **Khi kết hợp vào chương trình** | Trước lúc chạy, trong hoặc sau build | Khi class được nạp/định nghĩa | Khi caller đi qua wrapper trong runtime |
| **Artifact phát hành** | Thường chứa class đã dệt | Có thể là class gốc + weaver/agent/config | Có thể giữ target class gốc, tạo proxy trong app |
| **Chỉnh sửa bytecode target** | Có thể có, theo cơ chế weaving | Thường có transformation lúc nạp | Không cần sửa bytecode target |
| **Phạm vi** | Các class/join point đã dệt | Các class/join point thực sự qua weaver khi load | Các lời gọi đi qua proxy và method proxy hỗ trợ |
| **Self-invocation trực tiếp** | Có thể quan sát nếu join point được dệt phù hợp | Có thể quan sát nếu class đã được dệt | Thường bypass proxy khi dùng `this.method()` |
| **Private/final method** | Tùy loại join point/weaver, không bị đồng nhất với quy tắc override của proxy | Tùy bytecode/engine/module | Bị giới hạn mạnh với cơ chế cần interface hoặc override |
| **Chi phí runtime** | Có mã advice và overhead do weaving tạo | Có thể phát sinh transform khi class load; advice vẫn có runtime overhead | Dispatch proxy/handler, pointcut runtime, advice và Reflection tùy triển khai |
| **Đổi aspect** | Thường phải build/deploy lại phần liên quan | Cần cấu hình lại và nạp/biến đổi class phù hợp | Có thể đổi handler/cấu hình nếu kiến trúc thiết kế cho phép |
| **Phát hiện lỗi sớm** | Có thể tại build | Nhiều lỗi xuất hiện khi load/deploy | Nhiều lỗi đường gọi/khớp có thể xuất hiện trong runtime |
| **Debugging** | Cần hiểu artifact đã dệt và symbol | Cần quan sát quá trình class loading + transformation | Cần hiểu chuỗi wrapper, thứ tự advice và các đường bypass |
| **Khả năng hot change** | Không mặc định có | Không mặc định có; reload/retransform có giới hạn | Chính sách có thể đổi runtime, nhưng không tự mở rộng đường gọi |
| **Đánh đổi vận hành** | Kiểm soát build artifact | Cần kiểm soát lifecycle classloader/agent | Cần quản lý proxy ownership, object identity và registration |

**Không có kết luận “cách A luôn nhanh hơn cách B”.** Số lượng join point, mức độ tối ưu của engine, Reflection, số tầng advice, class load behavior, memory và tần suất gọi có thể làm kết quả rất khác. So sánh công bằng cần benchmark trên workload đại diện.

## 7. Ví dụ Java 17 chạy độc lập: code chuẩn bị sẵn và proxy có thể bật/tắt

Ví dụ dưới đây cho thấy **hai cách tổ chức luồng gọi dễ quan sát**:

1. `PreparedDecorator` là wrapper có hành vi đo/ghi được xác định từ source và có thể biên dịch thành class trước khi chạy. **Đây là phép so sánh sư phạm cho một artifact đã chuẩn bị, KHÔNG PHẢI một bộ compiler/bytecode weaver.**
2. `runtimeProxy(...)` sử dụng JDK dynamic proxy, chọn việc chạy advice theo `AtomicBoolean enabled` và thông tin `Method` của lời gọi. Nó minh họa **runtime interception thật**, nhưng chỉ trên những lời gọi đi qua proxy.

Cả hai triển khai cùng interface `Pricing`. Trong code, ta quan sát `price` thành công, `price` ném lỗi, `status` bỏ qua pointcut, `batch` gọi nội bộ qua `this.price()`, và việc bật/tắt advice của proxy sau khi proxy đã tạo.

Tạo file `WeavingModesDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicBoolean;

public final class WeavingModesDemo {
    interface Pricing {
        int price(int units);
        int batch(int units);
        String status();
    }

    static final class Core implements Pricing {
        @Override
        public int price(int units) {
            if (units <= 0) {
                throw new IllegalArgumentException("units must be positive");
            }
            System.out.println("BUSINESS price " + units);
            return units * 100;
        }

        @Override
        public int batch(int units) {
            System.out.println("BUSINESS batch");
            return this.price(units); // direct internal call; does not use proxy
        }

        @Override
        public String status() {
            return "READY";
        }
    }

    // A build-fixed wrapper, only an analogy for a prepared code artifact;
    // this is not a bytecode weaver.
    static final class PreparedDecorator implements Pricing {
        private final Pricing target;

        PreparedDecorator(Pricing target) {
            this.target = target;
        }

        @Override
        public int price(int units) {
            System.out.println("PREPARED before price");
            try {
                int result = target.price(units);
                System.out.println("PREPARED after price");
                return result;
            } catch (RuntimeException error) {
                System.out.println("PREPARED throwing "
                        + error.getClass().getSimpleName());
                throw error;
            }
        }

        @Override
        public int batch(int units) {
            return target.batch(units);
        }

        @Override
        public String status() {
            return target.status();
        }
    }

    static Object invokeTarget(Pricing target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Pricing runtimeProxy(Pricing target, AtomicBoolean enabled) {
        return (Pricing) Proxy.newProxyInstance(
                Pricing.class.getClassLoader(),
                new Class<?>[]{Pricing.class},
                (proxy, method, args) -> {
                    if (!enabled.get() || !method.getName().equals("price")) {
                        return invokeTarget(target, method, args);
                    }
                    System.out.println("RUNTIME before price");
                    try {
                        Object result = invokeTarget(target, method, args);
                        System.out.println("RUNTIME after price");
                        return result;
                    } catch (Throwable error) {
                        System.out.println("RUNTIME throwing "
                                + error.getClass().getSimpleName());
                        throw error;
                    }
                });
    }

    public static void main(String[] args) {
        Pricing prepared = new PreparedDecorator(new Core());
        System.out.println("PREPARED result=" + prepared.price(2));

        AtomicBoolean enabled = new AtomicBoolean(false);
        Pricing dynamic = runtimeProxy(new Core(), enabled);
        System.out.println("DYNAMIC OFF result=" + dynamic.price(3));

        enabled.set(true);
        System.out.println("DYNAMIC ON result=" + dynamic.price(3));
        try {
            dynamic.price(0);
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }

        System.out.println("DYNAMIC batch=" + dynamic.batch(1));
        System.out.println("DYNAMIC status=" + dynamic.status());
        enabled.set(false);
        System.out.println("DYNAMIC OFF AGAIN result=" + dynamic.price(1));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 WeavingModesDemo.java
java WeavingModesDemo
~~~

Kết quả đã xác minh bằng biên dịch và chạy thực:

~~~text
PREPARED before price
BUSINESS price 2
PREPARED after price
PREPARED result=200
BUSINESS price 3
DYNAMIC OFF result=300
RUNTIME before price
BUSINESS price 3
RUNTIME after price
DYNAMIC ON result=300
RUNTIME before price
RUNTIME throwing IllegalArgumentException
CALLER units must be positive
BUSINESS batch
BUSINESS price 1
DYNAMIC batch=100
DYNAMIC status=READY
BUSINESS price 1
DYNAMIC OFF AGAIN result=100
~~~

### 7.1. Đọc kết quả của wrapper chuẩn bị từ trước

Lời gọi `prepared.price(2)` qua `PreparedDecorator` luôn in `PREPARED before`, gọi target rồi in `PREPARED after`. Wrapper được viết rõ trong source và biên dịch trước khi chạy; không có một switch runtime trong ví dụ để thay đổi bộ chọn của wrapper này.

**Đây là một ví dụ về *prepared composition*, không phải CTW thực sự**: class `Core` không bị sửa và nếu caller giữ `Core` rồi gọi trực tiếp thì decorator không can thiệp. Một công cụ weaving đúng nghĩa có thể thay đổi bytecode hoặc artifact để can thiệp sâu hơn. Việc nêu khác biệt này giúp tránh kết luận sai rằng mọi lớp decorator đều tương đương với static weaving.

### 7.2. Runtime proxy bật/tắt hành vi

Lần `dynamic.price(3)` đầu tiên có `enabled=false`: proxy chuyển tiếp thẳng và chỉ thấy `BUSINESS price 3`.

Khi `enabled.set(true)`, **cùng đối tượng proxy ấy** bắt đầu ghi `RUNTIME before/after` cho `price`. `AtomicBoolean` cho phép các thread quan sát trạng thái bật/tắt với ngữ nghĩa đồng thời phù hợp, nhưng **không dệt thêm bytecode vào `Core`**. Nó chỉ thay đổi chính sách khi lời gọi đã đi qua proxy.

Sau khi `enabled=false` lần nữa, hành vi bổ sung dừng ở đường này. Tính linh hoạt do code proxy đã thiết kế sẵn, không phải một khả năng hot-reload mọi aspect trên mọi công nghệ.

### 7.3. Lời gọi nội bộ minh họa ranh giới của proxy

`dynamic.batch(1)` vào proxy, nhưng handler chỉ chọn tên `price`. `Core.batch()` thực hiện `this.price(units)` **trực tiếp trên target**, nên không đi qua proxy `dynamic`. Ta thấy `BUSINESS batch` và `BUSINESS price 1` nhưng không có `RUNTIME before price`.

Nếu một weaver có thể chèn advice tại **execution join point** của `Core.price`, lời gọi nội bộ có thể vẫn được quan sát khi method chạy — nhưng chỉ nếu class và loại join point ấy thực sự được weaving. Không tự suy ra điều đó từ việc một công cụ gắn nhãn “AOP”.

### 7.4. Giữ nguyên ngoại lệ target

`dynamic.price(0)` ném `IllegalArgumentException`. Handler gọi target qua Reflection, nhận wrapper `InvocationTargetException` rồi bóc nguyên nhân bằng `getCause()`. Do đó caller nhìn thấy đúng `IllegalArgumentException: units must be positive`, thay vì một ngoại lệ wrapper tùy ý.

Việc giữ nguyên lỗi là ví dụ về **hợp đồng advice chỉ quan sát**. Nếu advice có chủ đích dịch ngoại lệ hoặc fallback, đó là một chính sách khác cần tài liệu và test.

## 8. Runtime instrumentation không chỉ có proxy

Bên cạnh proxy, nền tảng JVM còn có **instrumentation** có thể tương tác với class loading và biến đổi lớp. Một số cơ chế dùng Java agent để đăng ký `ClassFileTransformer`; với khả năng và cấu hình thích hợp, agent có thể tham gia vào quá trình định nghĩa class hoặc thực hiện **retransformation/redefinition** của class đã tải.

Cần phân biệt ba câu hỏi:

1. **Có hook nhận bytecode không?** Transformer có thể được gọi khi load hoặc khi yêu cầu retransform, tùy lifecycle và quyền được cấp.
2. **Có thực sự biến đổi bytecode không?** Chỉ log việc nạp lớp bằng transformer chưa đồng nghĩa với weaving advice vào method.
3. **Có được phép đổi cấu trúc/mã theo cách muốn không?** Các API redefinition/retransformation có những ràng buộc về thay đổi class, JVM implementation, capability, module và thời điểm.

Một **hot instrumentation agent** có thể là một hình thức can thiệp động khác proxy, nhưng không thể khẳng định nó luôn thay mọi method hoặc có thể tháo gỡ advice để khôi phục trạng thái hoàn toàn mà không tác động gì. Khi thiết kế cần kiểm chứng phiên bản JDK, tùy chọn agent, lớp đã tải, bytecode version, classloader, quyền và các hạn chế của công cụ.

### 8.1. Vì sao không nên lẫn LTW với retransformation?

- **Load-time weaving:** thường tác động **trước hoặc trong lúc class được định nghĩa**, rồi các method của class đã biến đổi chạy về sau.
- **Retransformation/redefinition:** cố gắng biến đổi **class đã được định nghĩa**, theo khả năng mà runtime và agent cho phép.
- **Proxy:** không buộc phải biến đổi class target; caller phải đi qua wrapper.

Cả ba có thể xảy ra khi JVM đang chạy, nhưng điểm tác động và giới hạn không giống nhau. Với một bài toán cần tracing production, việc lựa chọn giữa chúng liên quan đến khả năng vận hành và an toàn của runtime chứ không đơn thuần là “muốn động thì dùng load-time”.

## 9. Join point nào có thể được can thiệp?

Khả năng intercept phụ thuộc **mô hình join point** và **kỹ thuật dệt/chuyển tiếp**, không chỉ thời điểm.

| Loại điểm | Proxy method-call điển hình | Weaving ở class/bytecode khi được hỗ trợ |
| --- | --- | --- |
| Lời gọi method qua interface proxy | Có thể | Có thể nếu chọn và dệt điểm phù hợp |
| `this.method()` nội bộ target | Thường bypass proxy | Có thể quan sát method execution đã dệt |
| Private method | Không là phương thức interface public để proxy kiểu đó intercept | Có thể nếu engine hỗ trợ, class nằm trong phạm vi |
| Final method | Có thể được gọi qua interface proxy, nhưng subclass proxy gặp giới hạn override | Có thể theo cơ chế bytecode và join point model |
| Static method | Không là method instance trên interface proxy Java thông thường | Có thể nếu engine hỗ trợ loại execution/call ấy |
| Constructor | Không tương đương một method instance call qua proxy đã tạo | Tùy mô hình join point và vùng dệt |
| Field get/set | Không tự thấy qua method proxy trừ khi access được đưa qua API method | Có thể nếu engine định nghĩa field join point |
| Exception handler/throw | Proxy thấy exceptional exit của method, không tự thấy mỗi `catch` bên trong | Tùy engine hỗ trợ các join point tương ứng |
| Method trả Future | Proxy có thể thấy Future được trả ngay | Weaving method cũng chưa tự đo được Future completion |

Một nhận định tuyệt đối kiểu “proxy không bao giờ intercept final method” cũng có thể sai nếu proxy nằm ở **interface bên ngoài** và chuyển tiếp tới implementation final; hạn chế **override** khác với khả năng đứng trước lời gọi qua interface. Luôn xác định proxy là interface hay subclass-based.

## 10. Khi nào nên chọn dệt tĩnh?

Static weaving phù hợp hơn khi cần:

- Kiểm soát rõ artifact được dệt cùng version của code và aspect.
- Phát hiện một số vấn đề khi build, chạy test trên **chính artifact sẽ phát hành**.
- Can thiệp sâu vào các join point mà proxy đường gọi không quan sát được, khi công nghệ hỗ trợ.
- Tránh việc ứng dụng phải giữ và truyền tham chiếu proxy cho mọi đường gọi cần quan sát.
- Có CI/CD ổn định, khả năng rebuild và release nhất quán mỗi khi cấu hình aspect thay đổi.

Nhưng static weaving có thể kém phù hợp nếu:

- Không kiểm soát được pipeline build hoặc class cần can thiệp.
- Phải thay đổi phạm vi theo môi trường sau khi artifact đã phát hành mà không muốn tạo build khác.
- Việc bytecode weaving gây khó khăn với mã generated, module, bộ công cụ debug hoặc quy tắc packaging.
- Không có cách đảm bảo các class được dệt chính xác và không bị dệt nhiều lần.

**Gợi ý:** ghi nhận weaving configuration và version như một phần của build artifact; có integration test kiểm tra behavior thực trên artifact sau dệt, thay vì chỉ test source trước dệt.

## 11. Khi nào nên chọn interception động qua proxy?

Proxy/interceptor thích hợp khi:

- Chính sách áp dụng ở **ranh giới API hoặc hợp đồng interface rõ ràng**, ví dụ service call.
- Có thể bảo đảm caller sử dụng **đối tượng proxy**, không giữ target gốc ở nơi cần advice.
- Muốn thay điều kiện bật/tắt một số hành vi runtime qua cấu hình rõ và có khả năng quan sát.
- Cần thay interceptor chain, sử dụng dependency injection/factory hoặc lắp middleware có kiểm soát.
- Không muốn chạy một bytecode weaver hoặc agent can thiệp class.

Nhưng phải đề phòng:

- **Bypass:** caller gọi trực tiếp target hoặc `this.method()` nội bộ.
- **Identity/lifecycle:** `proxy != target`; `equals`/`hashCode`, serialization, type checks và method reflection có thể cho behavior cần xem xét.
- **Kiểu API:** interface proxy không phải subtype của class implementation; cast sang implementation có thể thất bại.
- **Overload:** pointcut chỉ theo tên method dễ chọn nhầm chữ ký.
- **Hiệu năng:** số tầng interceptor, Reflection, logging và điều kiện runtime tăng overhead; phải đo thực tế.
- **Security:** nếu advice là lớp bảo vệ duy nhất, đường đi không qua proxy có thể là lỗ hổng kiến trúc.

Đừng chọn proxy chỉ vì “nhanh hơn” hoặc weaving vì “mạnh hơn” mà không đối chiếu tập join point bắt buộc và đường gọi trong hệ thống.

## 12. Load-time weaving trong vận hành thực tế

Nếu chọn load-time weaving, hãy lập checklist kỹ thuật:

1. **Class nào được phép dệt?** Xác định tập package/class rõ, loại trừ lớp hạ tầng của chính agent nếu cần.
2. **Transformer được đăng ký trước khi class mục tiêu được định nghĩa chưa?** Kiểm tra trình tự khởi tạo.
3. **Ai nạp class?** Một ứng dụng có thể có nhiều classloader; cùng tên class ở các loader khác nhau không nhất thiết là cùng runtime class.
4. **Bytecode có hợp lệ?** Transformation phải giữ tính hợp lệ của stack map frames, method descriptors và verifier rules của JVM.
5. **Module boundary được xử lý hợp lệ?** Một lớp có thể không được phép reflective access hoặc instrument theo cách kỳ vọng nếu modules đóng.
6. **Khi class load lỗi thì sao?** Xác định fail-open/fail-closed và thông tin chẩn đoán.
7. **Có class nào đã load sẵn không?** Nếu có, LTW thông thường có thể bỏ lỡ, phải đánh giá khả năng retransformation riêng.
8. **Có dùng thư viện bên thứ ba không?** Kiểm tra compatibility, quyền đóng gói và tương thích bytecode.
9. **Debug được không?** Thiết lập logging transformation có kiểm soát, stack trace và nguồn symbol phù hợp.
10. **Kiểm soát cấu hình theo release:** thay đổi agent/weaver phải có test trên môi trường tương đương production.

Không nên coi “agent đã khởi động” là bằng chứng mọi pointcut đã khớp. Phải kiểm chứng bằng một bài test **gọi thật** qua đúng join point và so khớp kết quả với behavior mong muốn.

## 13. Sai lầm thường gặp trong phân loại

### 13.1. “Weaving tĩnh nghĩa là hành vi không thể quyết định động”

Không đúng. Một artifact đã được dệt có thể chứa advice kiểm tra giá trị đối số, trạng thái runtime hoặc chính sách bật/tắt. **Thời điểm cài điểm can thiệp** khác **thời điểm tính điều kiện trong advice**. Điều kiện có thể vẫn là runtime.

### 13.2. “Load-time weaving cũng là dynamic proxy”

Không đúng. LTW thường xử lý bytecode trước khi class được định nghĩa; proxy có thể đứng trước lời gọi mà không chỉnh bytecode target.

### 13.3. “Runtime proxy chắc chắn chặn được tất cả lời gọi”

Không đúng. Đường bypass, self-invocation, private method và lời gọi trực tiếp vào target thường nằm ngoài vùng quan sát của một proxy thông thường.

### 13.4. “Không sửa bytecode thì không phải AOP”

Không đúng. Một hệ thống áp dụng pointcut và advice thông qua proxy/interceptor vẫn có thể hiện thực các mục tiêu AOP, miễn ranh giới áp dụng đã được hiểu đúng. Nhưng gọi nó là **bytecode weaving** là thiếu chính xác.

### 13.5. “Động luôn thay đổi được mà không restart”

Không đúng. Cấu hình có thể được chốt tại startup; agent có thể không hỗ trợ thay đổi class đang hoạt động; proxy có thể không có cơ chế reload. **Hot update** là một năng lực phải được thiết kế và kiểm thử riêng.

### 13.6. “Weaving lúc build chắc chắn không overhead ở runtime”

Không đúng. Advice, logging, tracing và logic bổ sung vẫn tiêu tốn CPU/bộ nhớ/I/O khi chạy. Static weaving chỉ thay đổi **cách đưa hành vi vào chương trình**, không làm hành vi miễn phí.

### 13.7. “Weaving lúc nạp lớp giống instrumentation đã chạy từ trước”

Không đúng. Nếu class đã được load trước khi transformer đăng ký, không thể mặc định nó sẽ được dệt bởi cơ chế chỉ can thiệp load-time.

### 13.8. “Chọn đúng pointcut là lời gọi chắc chắn được can thiệp”

Không đúng. Cần xét riêng **matching**, **phạm vi weaving/proxy**, **đường gọi thực** và **thứ tự advice**. Test pointcut trong môi trường mô phỏng không thay thế test integration.

## 14. Kiểm thử theo từng kiến trúc

Khi triển khai AOP, hãy xây bộ test thể hiện rõ ba nhóm: matching, interception và preservation.

| Ca thử | Dệt tĩnh | Dệt khi load | Proxy runtime |
| --- | --- | --- | --- |
| Gọi method public ở ranh giới cần advice | Test artifact sau build | Test class được định nghĩa qua weaver | Gọi qua proxy |
| Gọi trực tiếp vào target | Test có advice tại method execution đã dệt hay không | Test class có được dệt và điểm hỗ trợ không | Thường bypass |
| Gọi `this.method()` | Test đúng join point đã dệt | Tương tự, phụ thuộc scope | Thường bypass |
| Private/final/static | Xác minh mô hình pointcut | Xác minh engine/module | Xác minh kiểu proxy và giới hạn |
| Normal return | Giữ nguyên return value khi chỉ quan sát | Tương tự | Tương tự |
| Throw exception | Giữ nguyên lỗi gốc khi chỉ quan sát | Tương tự | Nếu Reflection, bóc wrapper phù hợp |
| Hai advice cùng khớp | Kiểm precedence | Kiểm precedence và load order | Kiểm thứ tự interceptor |
| Thay đổi aspect | Rebuild/redeploy theo quy trình | Reconfigure/reload theo capability | Thay handler/policy nếu thiết kế cho phép |
| Class/library từ bên thứ ba | Kiểm được dệt không | Kiểm loader, agent, module | Chỉ các API có đường đi qua proxy |
| Bật/tắt runtime | Kiểm behavior đã dệt có guard không | Kiểm configuration thực | Kiểm trạng thái handler và concurrent calls |

Một integration test tối thiểu nên chứng minh: **đúng điểm được chọn**, **sai điểm không được chọn**, **return/exception giữ nguyên**, **số lần target chạy không đổi ngoài chủ đích**, và **bypass được nhận diện đúng**.

### 14.1. Kiểm tra metadata không đủ

Phát hiện một `Method` thông qua Reflection hoặc quét annotation không chứng minh advice có chạy. Với proxy, caller phải dùng proxy; với weaving, class thực sự phải được xử lý, và pointcut phải chọn được join point xuất hiện.

### 14.2. Kiểm thử với nhiều classloader/module

Một ứng dụng plugin hoặc container có thể load nhiều class cùng tên từ classloader khác nhau. Weaving configuration theo tên class thôi chưa chắc phù hợp mọi loader. Khi có module boundary, test bằng cấu hình runtime giống production để phát hiện vấn đề access hoặc class definition sớm.

### 14.3. Kiểm thử concurrent và thay cấu hình động

Nếu có cờ bật/tắt runtime, test lúc nhiều lời gọi đang hoạt động: một lời gọi đã bắt đầu dưới policy cũ và lời gọi mới dưới policy mới có thể có trình tự khác nhau. **Không giả định bật/tắt sẽ hủy ngay một advice đã chạy một phần**, trừ khi implementation bảo đảm điều đó. `AtomicBoolean` trong ví dụ bảo đảm visibility cho việc đọc cờ nhưng không điều khiển lại quá khứ của một invocation.

## 15. Hiệu năng: đừng suy luận thay cho benchmark

Một phép đo công bằng cần phân biệt:

- **Startup/load cost:** transformer nạp lớp, verify bytecode, tạo proxy và đăng ký interceptor.
- **Steady-state per-call cost:** indirection, handler dispatch, dynamic pointcut check, logic advice và I/O của sink.
- **Memory pressure:** proxy objects, metadata, transformed bytecode, classloader state, allocations mỗi lời gọi.
- **Optimization effects:** JIT inlining, deoptimization, class redefinition và megamorphic call sites có thể ảnh hưởng khác nhau.
- **Operational cost:** thời gian build, debugging, compatibility và downtime do reconfiguration.

Trong cả hai mô hình, **logic advice** như ghi log network có thể là phần chi phí lớn nhất, che lấp khác biệt giữa proxy dispatch và woven call. Benchmark cần thực hiện với cùng workload, cùng advice, warm-up phù hợp và hệ thống thu metric không làm nhiễu kết quả.

Không dùng một vòng lặp đơn giản có `System.nanoTime()` để tuyên bố kiến trúc nào luôn nhanh hơn: kết quả có thể bị JIT tối ưu, khác phần cứng, khác số tầng wrapper hoặc GC.

## 16. Hướng dẫn lựa chọn theo tình huống

| Tình huống | Phương án đáng cân nhắc | Lý do |
| --- | --- | --- |
| Audit mọi lần method execution kể cả self-invocation, công cụ có hỗ trợ | Bytecode weaving trong phạm vi được kiểm soát | Proxy ngoài không chắc nhìn lời gọi nội bộ |
| Tracing các API qua interface rõ ràng | Proxy/interceptor | Ranh giới đơn giản, dễ chọn và kiểm thử |
| Muốn lỗi weaving lộ ra trong CI | Compile-time hoặc binary weaving | Kiểm tra được artifact đã dệt từ build |
| Không muốn thay artifact gốc nhưng có quyền cấu hình agent từ đầu | Load-time weaving | Kết hợp khi class được nạp |
| Cần hot instrumentation trên class đã load | Runtime retransformation nếu nền tảng hỗ trợ | Khác với load-time thông thường, có giới hạn riêng |
| Muốn bật/tắt metrics trên proxy đã tạo | Handler có cờ/policy cập nhật runtime | Không cần thay bytecode nếu mọi lời gọi qua proxy |
| Code gọi target trực tiếp, không có ranh giới wrapper đáng tin | Weaving hoặc refactor đường gọi | Proxy đơn lẻ dễ bị bypass |
| Yêu cầu bảo mật bắt buộc trên mọi đường | Thiết kế enforcement tại ranh giới tin cậy, không chỉ “gắn advice” | Cần chứng minh mọi đường được bao phủ |

**Không nhất thiết chỉ được dùng một mô hình cho toàn ứng dụng.** Có thể dùng instrumentation ở lớp hạ tầng để tracing, proxy tại service boundary cho chính sách kỹ thuật và code nghiệp vụ rõ ràng cho bất biến miền. Nhưng khi kết hợp nhiều mô hình, nguy cơ **double-instrumentation** hoặc precedence khó hiểu tăng lên. Cần bản đồ các điểm đã instrument và test số lần advice chạy.

## 17. Checklist thiết kế trước khi chọn công nghệ

1. **Điểm cần can thiệp là gì?** Method call, execution, field access, constructor, exception handler hay task completion?
2. **Ai sở hữu code?** Source mình biên dịch hay thư viện đã đóng gói?
3. **Có đường bypass proxy không?** Gọi trực tiếp target, `this.method()`, callback, reflection?
4. **Cần thay ở thời điểm nào?** Build time, lúc class load, hay trong runtime đã nạp lớp?
5. **Có cần hot update thật không?** Nếu có, engine hỗ trợ đổi chính sách hay retransform ở mức nào?
6. **Có hạn chế môi trường không?** Java version, module, classloader, packaging, agent permissions?
7. **Phạm vi pointcut có ổn định?** Dựa trên API contract/annotation hay tên package dễ thay đổi?
8. **Mức bảo đảm là gì?** Quan sát “best effort” hay enforcement/audit bắt buộc?
9. **Ai được xử lý lỗi advice?** Fail-open/fail-closed và bảo toàn ngoại lệ gốc?
10. **Hiệu năng cần tối ưu gì?** Startup, throughput, latency, memory hay khả năng chẩn đoán?
11. **Kiểm thử artifact nào?** Source trước dệt chưa đủ; phải test thành phẩm hoặc đường proxy thật.
12. **Quan sát đủ các nhánh chưa?** Normal, throwing, recursion, async, self-invocation và concurrent reconfiguration.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Compile-time weaving hoàn tất trước khi ứng dụng chạy. Advice có chạy ở runtime không?  
**Đáp án:** Có. Việc **gắn/kết hợp** xảy ra khi build, còn hành vi advice vẫn thực thi khi join point xuất hiện ở runtime.

**Câu 2.** Proxy runtime với `AtomicBoolean` bật/tắt log có đang thay bytecode của target không?  
**Đáp án:** Không. Nó chỉ thay đổi điều kiện thực thi trong handler trên các lời gọi **đi qua proxy**.

**Câu 3.** Load-time weaving khác proxy ở đâu?  
**Đáp án:** LTW thường biến đổi class bytecode khi class được định nghĩa; proxy thường đứng trước lời gọi mà không sửa class target.

**Câu 4.** Nếu target gọi `this.price()` bên trong `batch()`, proxy ngoài có chặn `price()` không?  
**Đáp án:** Trong mô hình JDK proxy của ví dụ: không, vì đó là lời gọi trực tiếp bên trong target. Weaving tại execution có thể quan sát nếu công cụ hỗ trợ và class đã được dệt.

**Câu 5.** Static weaving có luôn nhanh hơn dynamic proxy không?  
**Đáp án:** Không có kết luận chung. Phải đo chi phí advice, mức tối ưu JIT, dispatch, pointcut, I/O, load và workload cụ thể.

**Câu 6.** Transformer được khởi tạo sau khi class đã load thì class ấy chắc chắn được dệt theo LTW không?  
**Đáp án:** Không. Có thể cần capability retransformation/redefinition riêng và vẫn bị các giới hạn JVM/công cụ.

**Câu 7.** Có thể sử dụng một static decorator viết tay để chứng minh thật sự đã bytecode weaving không?  
**Đáp án:** Không. Decorator chỉ minh họa hành vi wrapper đã chuẩn bị; bytecode weaving phải được kiểm tra ở artifact hoặc cơ chế transform thực.

**Câu 8.** Vì sao chỉ nhìn một pointcut match đúng không đủ xác nhận AOP hoạt động?  
**Đáp án:** Phải có join point thật xuất hiện ở đường gọi được weaver/proxy quan sát, advice được gắn theo phạm vi, và thứ tự/hợp đồng kết quả đúng.

## 19. Tổng kết

**Dệt tĩnh** kết hợp aspect vào artifact trước khi chương trình chạy — trong khi biên dịch hoặc hậu biên dịch — còn **load-time weaving** biến đổi class khi chúng được nạp/định nghĩa. **Can thiệp động qua proxy/interceptor** định tuyến các lời gọi qua lớp trung gian ở runtime và có thể đánh giá điều kiện áp dụng ở mỗi lần gọi mà **không cần biến đổi bytecode target**. Runtime instrumentation/retransformation trên class đã nạp lại là một nhánh khác, có capability và hạn chế riêng.

Lựa chọn đúng không chỉ là so “tĩnh hay động”: hãy xác định **loại join point cần quan sát, phạm vi class/đường gọi thực sự được kiểm soát, khả năng thay đổi, chi phí, tương thích runtime và mức độ bảo đảm**. Dùng integration test để chứng minh cả điểm được chọn lẫn điểm bị loại, bảo toàn return/exception và phát hiện đường bypass. Khi hiểu đúng **thời điểm kết hợp** tách biệt với **thời điểm advice chạy**, ta có thể thiết kế AOP rõ ràng, dự đoán được và dễ vận hành hơn.