# Đầu vào, đầu ra và thời điểm áp dụng aspect trong kiến trúc weaving (AOP)

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), **weaving** là quá trình kết hợp chương trình cơ sở với các **aspect** để hành vi bổ sung (*advice*) có hiệu lực tại các **điểm can thiệp** (*join point*) phù hợp với **pointcut**. Hiểu kiến trúc weaving không chỉ là nhớ thuật ngữ: người học cần biết **đầu vào nào được xử lý, kết quả kết hợp tồn tại dưới dạng nào và thời điểm nào việc kết hợp xảy ra**.

Có hai thời điểm rất dễ nhầm:

- **Thời điểm kết hợp aspect (weaving/composition):** một công cụ hoặc cơ chế chuẩn bị đường thực thi có chứa hành vi bổ sung, chẳng hạn trong build, khi nạp lớp hoặc khi tạo proxy.
- **Thời điểm advice thực thi:** chương trình đang chạy thực sự đi đến một join point được chọn, điều kiện động được thỏa và advice được kích hoạt.

Aspect có thể được weave lúc build nhưng advice chạy hàng nghìn lần sau khi triển khai. Một proxy có thể được tạo lúc khởi động nhưng advice không chạy lần nào nếu không ai gọi qua proxy. Vì vậy, **“aspect đã được kết hợp” không đồng nghĩa “advice đã chạy”**.

Bài học giải thích kiến trúc AOP tổng quát. Những công cụ khác nhau có các mô hình join point và cơ chế kết hợp khác nhau; không nên coi khả năng của một mô hình là cam kết cho mọi hệ AOP.

## 1. Mục tiêu

Sau bài, bạn có thể:

1. Xác định chương trình cơ sở, định nghĩa aspect, pointcut, advice, cấu hình, công cụ weaving và môi trường thực thi.
2. Mô tả **đầu vào** của compile-time, binary/post-compile, load-time và runtime composition.
3. Nhận diện **đầu ra** là bytecode/artifact đã kết hợp, định nghĩa lớp lúc nạp hay proxy/interceptor, tùy cơ chế.
4. Phân biệt **đánh giá điểm khớp tĩnh** với **kiểm tra điều kiện động** ở runtime.
5. Giải thích vì sao một lớp có aspect hoặc một pointcut hợp lệ chưa bảo đảm đường gọi thực tế được can thiệp.
6. So sánh các mốc áp dụng aspect theo độ phủ join point, ảnh hưởng build, nạp lớp, triển khai và bảo trì.
7. Kiểm thử các trường hợp trả về bình thường, ném lỗi, nhiều advice lồng nhau, lời gọi bỏ qua proxy và lớp chưa được weave.
8. Đọc và chạy ví dụ Java 17 mô phỏng runtime composition mà không nhầm nó với bytecode weaving.

## 2. Bản đồ kiến trúc weaving

Sơ đồ tư duy tổng quát:

```text
CHƯƠNG TRÌNH CƠ SỞ                   ĐỊNH NGHĨA ASPECT
  Mã nguồn / bytecode                 Pointcut + Advice
           |                                 |
           +-----------+   +-----------------+
                       |   |
                       v   v
                   [WEAVER / COMPOSER] <--- Cấu hình + thông tin kiểu
                           |
                           v
             KẾT QUẢ KẾT HỢP PHÙ HỢP
         Woven bytecode / class definition / proxy
                           |
                           v
                    CHƯƠNG TRÌNH CHẠY
                           |
                           v
              Join point thực sự xuất hiện?
                      /          \
                     Không        Có
                      |           |
                 Không advice    Kiểm tra điều kiện
                                      |
                                  Advice chạy
```

Một số mô hình không có bộ weaver biến đổi class file mà dùng chuỗi interceptor. Sơ đồ chỉ mô tả trách nhiệm logic. Đầu vào/đầu ra vật lý tùy cơ chế.

### 2.1. Thành phần nào làm việc gì?

| Thành phần | Chức năng |
| --- | --- |
| **Base program** | Chứa logic nghiệp vụ đang có, chẳng hạn `OrderService.submit()` |
| **Join point model** | Quy định loại điểm có thể can thiệp: method execution, call, field get/set, constructor… nếu được hỗ trợ |
| **Pointcut** | Chọn tập join point bằng kiểu, tên, chữ ký, ngữ cảnh hoặc điều kiện tương ứng |
| **Advice** | Quy định hành vi trước, sau thành công, sau lỗi hoặc bao quanh |
| **Aspect** | Đóng gói pointcut và chính sách advice |
| **Weaver/composer** | Kết hợp aspect với đường thực thi của chương trình |
| **Configuration** | Chọn lớp/đường được xử lý, loại trừ, thứ tự aspect, môi trường áp dụng |
| **Runtime** | Thực hiện chương trình đã kết hợp và kích hoạt advice tại join point |

Điểm can thiệp do **mô hình AOP** định nghĩa, không chỉ do cú pháp Java. Ví dụ, một JDK dynamic proxy chặn lời gọi qua phương thức giao diện, nhưng không tự nhìn thấy mọi lệnh truy cập field hoặc constructor.

## 3. Đầu vào: cần những gì để weave?

### 3.1. Chương trình nền

Tùy cơ chế, đầu vào có thể là:

- **Mã nguồn** ở giai đoạn biên dịch;
- **Bytecode** sau khi biên dịch, như các tệp `.class`;
- **Artifact** chứa bytecode và metadata, ví dụ JAR;
- **Bytecode ngay trước lúc JVM định nghĩa lớp**;
- **Đối tượng và hợp đồng phương thức/giao diện** dùng để lắp proxy ở runtime.

Mỗi dạng đầu vào dẫn tới phạm vi và cách kiểm chứng khác nhau. Bộ xử lý bytecode cần biết mã chứa join point; proxy runtime cần bảo đảm người gọi sử dụng đối tượng đại diện.

### 3.2. Định nghĩa aspect

Aspect mô tả ít nhất hai ý:

1. **Chọn điểm nào?** Pointcut có thể lọc loại join point, kiểu khai báo, package, chữ ký, annotation hoặc bối cảnh.
2. **Làm gì ở điểm đó?** Advice có thể ghi log, đo thời gian, kiểm toán hoặc thực thi một chính sách có quyền thay đổi hành vi.

Một số hệ AOP còn cần khai báo thứ tự ưu tiên khi nhiều aspect cùng khớp. Around advice có thể bao quanh chuỗi bên trong, nên `Timing(Retry(Operation))` khác `Retry(Timing(Operation))`.

### 3.3. Thông tin kiểu và phụ thuộc

Để tìm đúng phương thức, công cụ có thể cần thông tin:

- Lớp khai báo, kiểu cha và giao diện;
- Danh sách kiểu/thứ tự tham số, kiểu trả về, modifier;
- Annotation hoặc metadata;
- Các lớp được advice tham chiếu;
- Classpath/module path và class loader;
- Phiên bản JDK, compiler, công cụ weaving tương ứng.

Nếu thông tin kiểu hoặc dependency không khớp giữa lúc build và chạy, có thể thiếu điểm can thiệp hoặc xuất hiện lỗi khi nạp lớp. Tên phương thức trùng nhau không đủ; overload và phương thức kế thừa có thể làm tập điểm khớp thay đổi.

### 3.4. Cấu hình phạm vi

Cấu hình có thể gồm:

- Những lớp, package, module hoặc artifact nào được phép xử lý;
- Những lớp bị loại trừ, kể cả mã hạ tầng của chính advice;
- Thứ tự aspect;
- Thời điểm kích hoạt biến đổi;
- Cách tạo và phân phát proxy;
- Chính sách khi pointcut không khớp hoặc công cụ không hỗ trợ join point.

Pointcut quá rộng có thể tạo log trùng, overhead và can thiệp ngoài ý muốn. Pointcut đúng nhưng lớp nằm ngoài phạm vi weaving cũng không tạo advice ở đường mong muốn.

## 4. Đầu ra: chương trình được kết hợp có dạng gì?

Một khái niệm logic là:

```text
wovenProgram = weave(baseProgram, aspects, configuration)
```

Đây là **ký hiệu mô hình**, không phải API Java. Đầu ra vật lý có nhiều hình thức:

| Cơ chế | Đầu ra điển hình | Điều cần kiểm chứng |
| --- | --- | --- |
| Compile-time | Class file/artifact đã tích hợp logic aspect lúc biên dịch | Có dùng đúng output của compiler/weaver khi chạy không? |
| Binary/post-compile | Bytecode/artifact được biến đổi sau biên dịch | Bước đóng gói có dùng bản đã biến đổi không? |
| Load-time | Class definition chứa bytecode đã được biến đổi trước khi JVM định nghĩa lớp | Transformer có xử lý đúng lớp tại đúng lúc không? |
| Runtime proxy/interceptor | Đối tượng đại diện hoặc chuỗi gọi đã được lắp | Người gọi có đi qua đại diện không? |
| Runtime redefinition (nếu hỗ trợ) | Một số định nghĩa lớp đang sống được cập nhật có điều kiện | JVM và công cụ có cho phép thay đổi loại đó không? |

**Đầu ra không nhất thiết là file nguồn đã sửa.** Khi load-time weaving, file JAR trên đĩa có thể giữ nguyên. Với proxy, lớp nghiệp vụ có thể hoàn toàn không bị thay đổi bytecode.

Không đồng nhất bốn con số: **số lớp được xem xét**, **số join point đã weave**, **số proxy được tạo** và **số lần advice thực thi**.

## 5. Compile-time weaving

**Compile-time weaving** kết hợp aspect như một phần bước biên dịch.

```text
Source code + Aspect definition + Config + Dependencies
                         |
                         v
                    Compiler/Weaver
                         |
                         v
                 Woven bytecode
                         |
                         v
                       Runtime
                         |
                  Join point xảy ra
                         |
                    Advice chạy
```

### 5.1. Điểm mạnh

- Đường thực thi đã được chuẩn bị trước khi ứng dụng chạy.
- Một số lỗi kiểu, pointcut hoặc binding có thể được phát hiện ở build.
- Có thể kiểm thử trực tiếp artifact sẽ triển khai.
- Việc tạo proxy cho từng đối tượng không nhất thiết cần thiết nếu bytecode đã được kết hợp.

### 5.2. Điểm cần kiểm tra

- Công cụ build có thật sự chạy bước weaving không?
- Tập lớp nào nằm trong phạm vi được biên dịch và weave?
- Build cache/incremental build có tạo artifact không nhất quán không?
- Artifact deploy có đúng là **bản đã weave** không?
- Mã do công cụ khác sinh hoặc dependency thứ ba có nằm trong phạm vi không?
- Nếu aspect đổi, những phần nào phải được build lại?

**Kết hợp lúc compile** không có nghĩa advice chạy trong compiler. Advice vẫn thường chạy khi join point xảy ra ở chương trình đã triển khai.

## 6. Binary hoặc post-compile weaving

Ở mô hình này, Java compiler hoặc một công cụ khác tạo bytecode gốc **trước**. Bộ weaver nhận bytecode đó cùng aspect, rồi tạo đầu ra mới.

```text
Java source -> javac -> ORIGINAL .class
                              |
                         Aspect/config
                              |
                           Weaver
                              |
                              v
                          WOVEN .class -> Package -> Runtime
```

### 6.1. Vì sao chọn cách này?

Có thể cần tách bước biên dịch chức năng và bước bổ sung chính sách cắt ngang. Nó hữu ích khi phần mã nền đã được biên dịch riêng hoặc build gồm nhiều bước, miễn công cụ được phép xử lý bytecode đó.

### 6.2. Sai lầm quan trọng

Nếu pipeline vô tình đóng gói `ORIGINAL .class` thay vì `WOVEN .class`, chương trình vẫn có thể chạy nhưng **không có advice**. Tương tự, weave hai lần ngoài ý định có thể gây áp trùng nếu công cụ không thiết kế việc lặp đó.

Cần xác nhận bản class cuối, đường đầu vào/đầu ra của weaver, bytecode hợp lệ và tương thích với JVM. Không mặc định công cụ có thể sửa mọi thư viện hoặc lớp nền tảng.

## 7. Load-time weaving

**Load-time weaving** thực hiện biến đổi trước hoặc trong quá trình JVM **định nghĩa lớp**, khi bytecode đi qua class loader/transformer được cấu hình.

```text
Bytecode gốc -> Class loader / Transformer
                             |
                   Aspect + Config
                             |
                             v
                 Transformed class definition
                             |
                             v
                    JVM executes class
                             |
                        Advice chạy
                      ở join point
```

### 7.1. Đầu vào và đầu ra

Đầu vào thường là bytecode lớp, aspect, cấu hình chọn lớp, thông tin môi trường nạp lớp và những dependency cần thiết. Đầu ra là **định nghĩa lớp đã biến đổi trong JVM**; không bắt buộc có file `.class` mới trên đĩa.

### 7.2. Tại sao thời điểm nạp lớp quan trọng?

Nếu một lớp đã được JVM định nghĩa **trước khi** cơ chế LTW được kích hoạt, không thể mặc định nó sẽ tự được weave. Java Instrumentation có các khả năng redefinition/retransformation trong những giới hạn nhất định, nhưng đó không phải tính năng mặc nhiên của mọi hệ LTW.

Các yếu tố cần kiểm tra là class loader, thời điểm định nghĩa lớp, bộ lọc class, giới hạn bytecode/JVM và cấu hình module. Hai lớp cùng tên nhưng do loader khác nhau định nghĩa có thể là hai kiểu runtime khác nhau, với phạm vi can thiệp khác nhau.

### 7.3. Một giới hạn thường bị hiểu nhầm

Cấu hình module của Java có `requires`, `exports`, `opens` với ý nghĩa riêng. Các khai báo ấy **không tự làm cho aspect được weave**. Quyền truy cập, reflection, class loader và khả năng biến đổi bytecode phải được xem theo công cụ và JVM cụ thể.

## 8. Runtime composition bằng proxy/interceptor

Ở một phương án khác, runtime tạo **proxy** hoặc **chuỗi interceptor** để can thiệp khi lời gọi đi qua đường đó.

```text
Target + Interface + Advice/Interceptor
                      |
                      v
                  Create proxy
                      |
                      v
              Caller holds proxy
                      |
                      v
                 Method call
                      |
               Before -> Target
                      |
               After/Throw/Finally
```

Đầu vào là đối tượng đích, hợp đồng giao diện hoặc lớp phù hợp, chính sách chặn và điều kiện chọn lời gọi. Đầu ra là **đại diện**. Lớp đích có thể không bị thay đổi.

### 8.1. Ưu điểm

- Có thể lắp chính sách tại runtime theo đối tượng hoặc cấu hình.
- Đường chặn có thể được biểu diễn rõ bằng chuỗi interceptor.
- Không nhất thiết sửa bytecode của lớp nghiệp vụ.
- Phù hợp để quan sát các lời gọi đi qua API hoặc cổng giao diện, trong phạm vi cơ chế hỗ trợ.

### 8.2. Những giới hạn phải nhớ

Với **JDK dynamic proxy**, handler nhận các lời gọi qua **giao diện được đại diện**. Nó không tự chặn mọi constructor, phương thức private, lời gọi `this.otherMethod()` bên trong đối tượng đích hoặc lệnh truy cập field trực tiếp.

Ngay cả khi proxy đã được dựng, lời gọi vào **đối tượng gốc** có thể bypass advice. Một proxy theo giao diện cũng không tự trở thành một weaver hỗ trợ method-call join point ở mọi vị trí mã nguồn.

## 9. So sánh thời điểm kết hợp và thời điểm advice chạy

| Trường hợp | Khi nào cấu trúc được kết hợp? | Khi nào advice chạy? |
| --- | --- | --- |
| Compile-time | Khi build/biên dịch | Khi join point đã weave được thực thi |
| Binary/post-compile | Khi xử lý bytecode sau compiler | Khi chạy artifact đã biến đổi và chạm join point |
| Load-time | Khi lớp được biến đổi trước lúc JVM định nghĩa | Khi mã của lớp ấy chạm join point |
| Runtime proxy | Khi lắp đại diện/chuỗi interceptor | Khi lời gọi đi qua proxy, khớp điều kiện |
| Runtime retransform (nếu hỗ trợ) | Khi công cụ được phép biến đổi lại lớp | Khi điểm phù hợp của định nghĩa đã biến đổi được thực thi |

Cách nói **“aspect áp dụng ở runtime”** đôi khi mơ hồ: có thể đang nói đến **lắp proxy lúc runtime**, **biến đổi lớp đang chạy** hoặc đơn giản là **advice được kích hoạt trong runtime sau khi đã weave tại build**. Khi trao đổi kỹ thuật nên ghi rõ ý nào.

### 9.1. Điều kiện tĩnh và điều kiện động

Một phần pointcut có thể được đánh giá theo **tên kiểu, package, chữ ký hoặc annotation** ở giai đoạn sớm. Các điều kiện như **giá trị đối số**, đối tượng runtime hoặc trạng thái luồng điều khiển có thể chỉ biết khi lời gọi xảy ra.

Một weaver có thể chèn đoạn kiểm tra điều kiện động trước; về sau điều kiện ấy mới quyết định advice có chạy ở **lần gọi cụ thể** hay không. Vì vậy “join point nằm trong mã đã weave” không bảo đảm advice chạy cho **mọi** lần đi qua vị trí đó.

## 10. Ví dụ Java 17: lắp cấu trúc trước, gọi advice sau

Ví dụ sử dụng **JDK dynamic proxy** để cho thấy đầu vào/đầu ra của runtime composition và thứ tự hai lớp advice. Nó **không** giả vờ là ví dụ compile-time hoặc load-time weaving. Toàn bộ mã chạy độc lập với JDK 17.

Lưu vào tệp `WeavingLifecycleDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class WeavingLifecycleDemo {
    interface WorkPort {
        String execute(String id);
        String lookup(String id);
    }

    static final class WorkService implements WorkPort {
        @Override public String execute(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id blank");
            }
            return "OK:" + id;
        }

        @Override public String lookup(String id) {
            return "FOUND:" + id;
        }
    }

    static Object invokeTarget(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static WorkPort withAdvice(String label, WorkPort target) {
        return (WorkPort) Proxy.newProxyInstance(
                WorkPort.class.getClassLoader(),
                new Class<?>[] { WorkPort.class },
                (proxy, method, args) -> {
                    if (!method.getName().equals("execute")) {
                        return invokeTarget(method, target, args);
                    }

                    String id = (String) args[0];
                    String value = id == null ? "<null>"
                            : id.isBlank() ? "<blank>" : id;

                    System.out.println("[" + label + "] before " + value);
                    try {
                        Object result = invokeTarget(method, target, args);
                        System.out.println("[" + label + "] after " + result);
                        return result;
                    } catch (Throwable error) {
                        System.out.println("[" + label + "] throw "
                                + error.getClass().getSimpleName());
                        throw error;
                    } finally {
                        System.out.println("[" + label + "] finally");
                    }
                });
    }

    public static void main(String[] args) {
        WorkPort original = new WorkService();
        WorkPort inner = withAdvice("INNER", original);
        WorkPort outer = withAdvice("OUTER", inner);

        System.out.println("ASSEMBLED");
        System.out.println("CALLER " + outer.execute("R-1"));

        try {
            outer.execute(" ");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER_ERROR " + error.getMessage());
        }

        System.out.println("LOOKUP " + outer.lookup("R-2"));
        System.out.println("DIRECT " + original.execute("R-3"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 WeavingLifecycleDemo.java
java WeavingLifecycleDemo
```

Kết quả:

```text
ASSEMBLED
[OUTER] before R-1
[INNER] before R-1
[INNER] after OK:R-1
[INNER] finally
[OUTER] after OK:R-1
[OUTER] finally
CALLER OK:R-1
[OUTER] before <blank>
[INNER] before <blank>
[INNER] throw IllegalArgumentException
[INNER] finally
[OUTER] throw IllegalArgumentException
[OUTER] finally
CALLER_ERROR id blank
LOOKUP FOUND:R-2
DIRECT OK:R-3
```

### 10.1. Đâu là đầu vào, đâu là đầu ra?

`withAdvice(label, target)` nhận tên lớp quan sát, một đối tượng triển khai `WorkPort`, thông tin giao diện và logic can thiệp. Nó trả về một **proxy `WorkPort`**. `inner` bao đối tượng gốc; `outer` bao `inner`.

Sau hai lời gọi `withAdvice`, chương trình in `ASSEMBLED`: cấu trúc đã được lắp. Chưa có `execute` nào được gọi, nên **chưa có dòng advice**.

### 10.2. Khi nào advice thực thi?

`outer.execute("R-1")` đi qua proxy ngoài rồi proxy trong. OUTER ghi `before`, INNER ghi `before`, đích chạy, sau đó INNER hoàn tất và OUTER hoàn tất. Thứ tự là kết quả cấu trúc lồng `OUTER(INNER(Target))`.

Lần gọi với `" "` ném `IllegalArgumentException`. Cả hai lớp proxy ghi nhánh lỗi và `finally`; hàm `invokeTarget` bóc `InvocationTargetException` để giữ lỗi đích ban đầu.

### 10.3. Lời gọi nào không được quan sát?

`outer.lookup("R-2")` đi qua proxy nhưng không khớp điều kiện `execute`. `original.execute("R-3")` **khớp về tên** nhưng đi thẳng vào đối tượng gốc, không qua proxy. Cả hai không in dòng advice.

Đây là bằng chứng: **đã lắp cơ chế** khác với **đã thực thi advice trên mọi đường gọi**.

### 10.4. Phạm vi minh họa

Mã dùng proxy JDK chứ không biến đổi bytecode. Điều kiện `method.getName().equals("execute")` là bộ lọc Java đơn giản; khi có overload thực tế phải xác định thêm chữ ký. Nó cũng không mô phỏng field get/set, constructor hay mọi loại join point khác. Dữ liệu ghi log chỉ nhằm học thuật; phải tránh ghi thông tin nhạy cảm trong hệ thống thật.

## 11. Hai đầu vào tưởng giống nhau nhưng tạo phạm vi khác nhau

Giả sử `OrderService` gọi `PaymentGateway.charge()`:

- **Method call join point** có thể gắn với **vị trí viết lời gọi** trong mã `OrderService`.
- **Method execution join point** có thể gắn với **phương thức thực thi** của `PaymentGateway`.
- Một proxy quanh `PaymentGateway` chỉ có thể quan sát đường gọi đi qua đại diện được cấp.

Nếu yêu cầu chọn “mọi lời gọi phát ra từ package order”, đó có thể là tập điểm khác với “mọi phương thức khai báo trong package order”. Một công cụ chỉ hỗ trợ method interception không tự cho phép quan sát mọi method-call join point trong bytecode.

Tương tự, muốn chọn **đọc/ghi field trực tiếp**, một proxy chỉ chặn getter/setter **không đủ**. Cần công nghệ có join point field access và phạm vi weaving phù hợp, hoặc tái thiết kế ranh giới truy cập tường minh.

## 12. Thứ tự aspect là một phần của đầu vào

Hai aspect có thể cùng khớp một join point. Kết quả lắp theo:

```text
Timer(Retry(Target))
```

có thể đo toàn bộ chuỗi thử lại, còn:

```text
Retry(Timer(Target))
```

có thể khiến bộ đo chạy từng attempt. Tương tự, thứ tự giữa kiểm tra quyền, cache, transaction và tracing có thể thay đổi ý nghĩa chính sách.

Không suy ra thứ tự từ tên file hoặc thứ tự khai báo khi công nghệ không cam kết điều đó. Cần có quy tắc precedence hoặc cấu hình chuỗi chặn được kiểm chứng.

## 13. Vấn đề nâng cao

### 13.1. Lớp đã nạp rồi

Thêm một transformer vào JVM **sau khi** lớp đã được định nghĩa không mặc định làm thay đổi lớp ấy. Nếu công nghệ cho phép retransform/redefine thì phải tuân theo điều kiện và giới hạn; không coi nó là đặc tính sẵn có của mọi cơ chế weaving.

### 13.2. Đối tượng đã được cấp ra ngoài

Tạo proxy mới không thay mọi tham chiếu trước đó tới đối tượng gốc. Nếu người gọi còn giữ bản gốc, đường bypass vẫn tồn tại. Phải lựa chọn rõ lúc tạo proxy và nơi quản lý/cấp đối tượng cho chương trình.

### 13.3. Nhiều class loader và module

Hai lớp cùng tên được nạp bởi loader khác nhau có thể là hai kiểu runtime khác nhau. Một transformer hoặc phạm vi weaving của một loader không nhất thiết bao phủ loader kia. JPMS và những quy tắc truy cập của Java cũng cần được xét theo JVM/công nghệ, không suy luận rằng tên package đã đủ.

### 13.4. Asynchronous completion

Phương thức có thể trả về `CompletableFuture` ngay nhưng tác vụ bên trong còn chạy. Advice after-returning quanh lời gọi tạo future quan sát **việc phương thức trả future**, không nhất thiết là **tác vụ hoàn tất thành công**. Cần cơ chế theo dõi completion phù hợp nếu mục tiêu là kết quả bất đồng bộ.

### 13.5. Advice tự gây lỗi

Một advice logging ném lỗi có thể biến lời gọi vốn thành công thành lỗi. Một around advice gọi tiếp hai lần có thể lặp tác dụng phụ. Một cleanup trong `finally` có thể che ngoại lệ gốc nếu ném lỗi mới. Kiến trúc weaving cần kiểm soát cả **thứ tự** và **hợp đồng bảo toàn hành vi**, không chỉ vị trí áp dụng.

## 14. Kiểm tra thành công theo bốn mức

| Mức | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Defined** | Aspect/pointcut đã tồn tại? | Build hoặc cấu hình nhận diện được |
| **Selected** | Pointcut chọn đúng những điểm cần thiết? | Test chữ ký, loại điểm, phạm vi, điều kiện |
| **Woven/Composed** | Đầu ra đã được tạo và sử dụng? | Class đã biến đổi hoặc proxy được cấp đúng |
| **Executed** | Advice thật sự chạy ở đường hợp lệ? | Test tích hợp trên lời gọi và kết quả thực |

Một hệ thống có thể PASS mức 1–3 nhưng FAIL mức 4 nếu không ai gọi qua proxy, điều kiện động sai hoặc chạy nhầm artifact. Ngược lại, thấy một dòng log chạy không chứng minh **mọi** đường nghiệp vụ quan trọng được áp chính sách.

### 14.1. Ma trận kiểm thử gợi ý

| Ca kiểm thử | Điều cần chứng minh |
| --- | --- |
| Join point đúng tên/chữ ký | Advice chạy đúng số lần |
| Overload khác | Không khớp ngoài ý muốn |
| Đường trả về bình thường | Kết quả giữ nguyên nếu chỉ theo dõi |
| Đường ném ngoại lệ | Giữ ngoại lệ gốc và dọn bối cảnh phù hợp |
| Đường gọi trực tiếp vs proxy | Hiểu rõ giới hạn bypass |
| Self-invocation | Biết cơ chế có đi qua advice không |
| Lớp chưa weave / loader khác | Phát hiện điểm bỏ sót |
| Compile-time output | Artifact triển khai là bản đã kết hợp |
| Binary output | Không đóng gói nhầm class gốc |
| Load-time | Transformer hoạt động trước lúc lớp được định nghĩa |
| Hai aspect cùng khớp | Thứ tự và hiệu ứng đúng |
| Tác vụ bất đồng bộ | Phân biệt return với completion |
| Nhiều lần retry | Không gây tác dụng phụ lặp ngoài hợp đồng |

## 15. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Nghĩ “có file aspect là tự chạy” | Không có advice | Xác nhận cơ chế weaving/composition |
| Nghĩ weave lúc build thì advice cũng chạy lúc build | Hiểu sai vòng đời | Tách thời điểm kết hợp và kích hoạt |
| Quên dùng artifact sau binary weave | Thiếu advice dù build báo thành công | Kiểm tra output cuối cùng |
| Bật load-time transformer quá muộn | Lớp mong đợi đã nạp | Kiểm tra timeline class loading |
| Tạo proxy nhưng vẫn cấp đối tượng gốc | Đường gọi bỏ qua advice | Kiểm soát nơi cấp tham chiếu |
| Chọn pointcut quá rộng | Log lặp, ảnh hưởng hiệu năng | Giới hạn chữ ký, loại điểm và phạm vi |
| Cho rằng proxy chặn field access | Bỏ sót truy cập trực tiếp | Dùng cơ chế hỗ trợ loại điểm phù hợp |
| Không kiểm tra thứ tự nhiều aspect | Sai phạm vi retry, logging, transaction | Xác minh precedence |
| Bỏ qua kết quả/lỗi | Advice có thể đổi hành vi nghiệp vụ | Kiểm tra cả return và throw |
| Không theo dõi class loader | Một số lớp không được xử lý | Kiểm tra nguồn lớp và loader |
| Tin số proxy tạo là số advice đã chạy | Số liệu sai | Đếm invocation riêng |
| Không kiểm thử đường bypass | Chính sách quan trọng bị bỏ sót | Test cả đường không có advice |

## 16. Bài tập vận dụng có đáp án

### Bài 1: Thời điểm và đầu ra

Một bộ compile-time weaver tạo class đã kết hợp aspect lúc 10:00. Lần đầu chương trình gọi phương thức khớp lúc 10:30. Weaving và advice diễn ra lúc nào?

**Đáp án:** Weaving diễn ra trong build 10:00. Advice chạy tại join point 10:30, khi chương trình thực thi và điều kiện áp dụng đúng. Hai mốc khác nhau.

### Bài 2: Artifact nhầm

Sau khi chạy binary weaver, pipeline triển khai lại lấy bytecode trước biến đổi. Điều gì có thể xảy ra?

**Đáp án:** Artifact deploy thiếu logic advice mặc dù từng bước build/weaving có thể đã báo thành công. Phải đóng gói và kiểm thử **đúng đầu ra đã weave**.

### Bài 3: Transformer đăng ký muộn

Một lớp `Service` đã được định nghĩa trước khi load-time weaver hoạt động. Có thể mặc định lớp đang chạy được thay đổi ngay không?

**Đáp án:** Không. LTW thường xử lý trong giai đoạn nạp/định nghĩa lớp. Thay lớp đã nạp cần cơ chế riêng, điều kiện và giới hạn tương ứng, không phải mặc nhiên.

### Bài 4: Proxy

Proxy cho `OrderPort` đã tạo, nhưng thành phần A gọi `original.execute()` còn thành phần B gọi `proxy.execute()`. Vì sao A không có advice?

**Đáp án:** A dùng đối tượng gốc và bypass proxy. Tạo đại diện không tự thay tất cả tham chiếu. Đây là vấn đề **đường gọi được kết hợp**, không phải nhất thiết do pointcut sai.

### Bài 5: Một lớp, nhiều lần gọi

Một class được weave một lần ở build và phương thức khớp được gọi 100 lần. Có bắt buộc số lần advice bằng một không?

**Đáp án:** Không. Advice có thể chạy ở từng lần join point xảy ra, tùy điều kiện động và cấu trúc chuỗi aspect. Số lần weave và số invocation khác nhau.

### Bài 6: Loại join point

Yêu cầu can thiệp tại các lần đọc field trực tiếp. JDK dynamic proxy bọc getter có bảo đảm làm được không?

**Đáp án:** Không. Truy cập field trực tiếp không nhất thiết gọi getter qua proxy. Cần mô hình AOP hỗ trợ field-read join point và cơ chế kết hợp phù hợp, hoặc ranh giới API khác.

### Bài 7: Runtime composition

Trong ví dụ Java 17, vì sao `ASSEMBLED` in trước các dòng `[OUTER]` và `[INNER]`?

**Đáp án:** Proxy đã được **tạo và lắp** trước khi `execute` được gọi. Handler/advice chỉ chạy khi có cuộc gọi đi qua proxy và khớp điều kiện.

### Bài 8: Hai aspect

Nếu thứ tự là `Timer(Retry(Target))` thì Timer thường đo gì? Nếu là `Retry(Timer(Target))` thì sao?

**Đáp án:** Timer bên ngoài bao toàn bộ chuỗi retry; Timer bên trong có thể đo từng attempt. Cần xác minh thứ tự thực tế được công nghệ thiết lập.

### Bài 9: Completion bất đồng bộ

Một phương thức trả ngay một future chưa hoàn tất. Advice sau return ghi `SUCCESS`. Có chắc tác vụ async đã thành công không?

**Đáp án:** Không. Return của phương thức tạo future khác với completion của future. Cần theo dõi completion thực và hợp đồng kết quả.

## 17. Ghi nhớ

- **Đầu vào:** base code/bytecode hoặc đối tượng, định nghĩa aspect/pointcut/advice, thông tin kiểu, cấu hình và cơ chế kết hợp.
- **Đầu ra:** artifact/class đã biến đổi, định nghĩa lớp khi nạp hoặc proxy/interceptor, tùy kiến trúc; không phải lúc nào cũng sửa mã nguồn.
- **Các thời điểm áp dụng:** biên dịch, sau biên dịch, nạp lớp hoặc lúc dựng chuỗi runtime; mỗi cách có phạm vi và giới hạn riêng.
- **Weaving xảy ra trước về mặt cấu trúc; advice được thực thi khi join point phù hợp xuất hiện.** Cấu hình một aspect không chứng minh nó đã chạy.
- **Chọn điểm** (pointcut), **kết hợp** (weaving) và **thực thi** (advice invocation) cần được kiểm tra độc lập.
- Với nhiều aspect, **thứ tự lồng nhau** ảnh hưởng kết quả, lỗi, đo thời gian và tác dụng phụ.
- Khi sử dụng AOP cho chính sách quan trọng, hãy xác minh **artifact, class loading, proxy references, đường bypass và tính bảo toàn hợp đồng**, thay vì chỉ nhìn source aspect.
