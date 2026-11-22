# Khả năng can thiệp thư viện ngoài và giới hạn sở hữu mã trong các thời điểm weaving AOP

## 1. Đặt vấn đề: AOP có can thiệp được vào mã không do mình viết không?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, một **aspect** chứa logic xử lý mối quan tâm xuyên suốt (ghi log, đo thời gian, kiểm toán, giám sát lỗi, kiểm tra chính sách...). Một **pointcut** lựa chọn các **join point** thuộc mô hình can thiệp của công cụ; **advice** được kết hợp vào đường thực thi tương ứng thông qua **weaving** hoặc interception.

Một vấn đề thực tế xuất hiện ngay khi ứng dụng gọi thư viện từ bên thứ ba:

> Ta không có mã nguồn và không thể sửa class của thư viện. Vậy có thể thêm logging, tracing hoặc kiểm tra điều kiện vào các lời gọi của thư viện bằng AOP không?

**Câu trả lời là: có thể trong nhiều trường hợp, nhưng không phải luôn luôn.** Khả năng phụ thuộc đồng thời vào:

1. **Loại join point cần quan sát**: vị trí gọi thư viện ở mã của ta, hay phần thân phương thức nằm trong thư viện?
2. **Thời điểm weaving**: lúc biên dịch, lúc nạp lớp, hay trong đường gọi runtime.
3. **Phạm vi mã có thể xử lý**: chỉ mã ứng dụng hay bao gồm thư viện đã biên dịch.
4. **Quyền truy cập và tính tương thích kỹ thuật**: class loader, module, quyền biến đổi, bytecode, native code, cấu hình agent.
5. **Quyền sở hữu và quyền sử dụng**: ta được phép sửa/phân phối lại artifact hay chỉ được phép sử dụng thông qua API?
6. **Tác động đến hợp đồng thư viện**: return value, exception, thread safety, hiệu năng, nâng cấp phiên bản và tính an toàn.

Mục tiêu bài là xây cách đánh giá **có căn cứ** khi một aspect cần chạm tới hành vi thư viện ngoài, không mặc định rằng “có pointcut là can thiệp được mọi class”.

Bài trình bày **AOP tổng quát từ cơ bản đến nâng cao**; những ví dụ Java 17 mô tả một số giới hạn và công cụ ở tầng JVM, không xem một cách triển khai cụ thể là định nghĩa chung của AOP.

## 2. “Sở hữu mã” có nhiều nghĩa khác nhau

Khi nói “không sở hữu mã nguồn thư viện”, cần phân biệt các tầng:

| Tầng | Ta có thể có | Điều chưa chắc có |
| --- | --- | --- |
| **Mã nguồn** | Chỉ JAR/.class đã biên dịch | Quyền sửa source hoặc xem triển khai nội bộ |
| **Artifact** | Quyền tải, chạy, lưu cache | Quyền sửa tệp gốc và phân phối bản sửa |
| **Môi trường chạy** | Quyền cấu hình ứng dụng/JVM của mình | Quyền instrument tiến trình do bên khác quản lý |
| **Đường gọi** | Có thể đổi chỗ ứng dụng tạo đối tượng và gọi API | Không kiểm soát lời gọi nội bộ trong thư viện |
| **Class loader/module** | Có thể cấu hình một số lớp nạp | Không mở được mọi ranh giới module hoặc loader |
| **Hợp đồng API** | Dùng public API/documented extension | Không được phụ thuộc private internals không ổn định |
| **Giấy phép & chính sách** | Có quyền sử dụng theo license | Không mặc nhiên có quyền biến đổi, đóng gói lại hoặc phân phối |

**Không có source không đồng nghĩa không can thiệp được**, vì nhiều kỹ thuật hoạt động trên bytecode hoặc lời gọi. Nhưng **có thể sửa bytecode về mặt kỹ thuật không đồng nghĩa được quyền làm vậy về mặt pháp lý hoặc chính sách**.

Nếu thư viện chứa mã do tổ chức khác quản lý, cần kiểm tra hợp đồng cấp phép, điều khoản phân phối, kiểm soát an ninh và trách nhiệm hỗ trợ. Bài không thay thế tư vấn pháp lý; mục tiêu là xác định những rủi ro phải đánh giá.

## 3. Ba câu hỏi trước khi chọn kỹ thuật

Trước khi quyết định phải “dệt” thư viện ngoài, hãy tách ba mục tiêu:

**A. Muốn quan sát lời gọi từ mã mình tới thư viện?**

```text
Application -> library.execute()
       ^
       |
Điểm gọi thuộc mã ứng dụng
```

Ta có thể quan sát ở **ranh giới của ứng dụng**, ví dụ qua wrapper/proxy hoặc weaving vào call site của ứng dụng, mà **không cần** thay phần thân `library.execute()`.

**B. Muốn can thiệp mọi lần thực thi của phương thức bên trong thư viện?**

```text
Application ---> Library.publicMethod()
                     |
                     +-- Library.privateHelper()
                     +-- Library.internalCall()
```

Nếu muốn advice chạy cả khi thư viện tự gọi method của nó, nhiều cơ chế chỉ chặn qua proxy ở ứng dụng sẽ **không đủ**. Có thể cần weaving/instrumentation ở lớp thư viện, nếu kỹ thuật và quyền sử dụng cho phép.

**C. Muốn quan sát một tác vụ ngoài JVM hoặc ngoài tiến trình?**

```text
Application JVM -> HTTP/IPC -> Remote Vendor Service
```

Weaving class Java trong ứng dụng **không tự can thiệp** vào mã chạy ở máy chủ bên thứ ba. Ta chỉ có thể quan sát request/response tại ranh giới client của mình, trừ khi có quyền triển khai công cụ trên hệ thống đích.

Ba mục tiêu khác nhau về phạm vi kiểm soát, chứng cứ và kỹ thuật.

## 4. Join point nằm ở phía gọi hay phía được gọi?

Đây là nền tảng của bài.

**Method-call join point** mô tả một vị trí gọi phương thức. Nếu vị trí gọi nằm trong mã ứng dụng do ta build, bộ dệt hỗ trợ call join point có thể can thiệp ngay tại đó ngay cả khi **đích là thư viện ngoài**.

**Method-execution join point** mô tả ranh giới phần thân phương thức được chạy. Nếu phần thân thuộc class thư viện, muốn chèn advice vào execution đó có thể cần có bytecode lớp thư viện trong phạm vi weaving.

```text
Ứng dụng của ta                     JAR bên thứ ba
+------------------------+          +------------------------+
| Checkout.placeOrder()  |          | Gateway.send()         |
|                        |          |                        |
|  gateway.send(data) ---+--------->| thực thi send(data)    |
|          ^             |          |       ^                |
|       call site        |          |    execution           |
+------------------------+          +------------------------+
```

Trong công cụ hỗ trợ cả hai loại, pointcut chọn **call** có thể hoạt động ở bên trái còn chọn **execution** cần đánh giá phạm vi biến đổi bên phải.

Đừng suy diễn rằng mọi ngôn ngữ/công cụ AOP có cả call và execution join point. Có công cụ chỉ hỗ trợ những lời gọi đi qua interface/proxy hoặc một tập phương thức cụ thể.

### 4.1. Lời gọi nội bộ là ca dễ bỏ sót

Nếu thư viện gọi `this.internalMethod()` trong cùng đối tượng, một proxy đặt **bên ngoài** thư viện có thể chỉ thấy lời gọi entry từ ứng dụng, không thấy từng lời gọi bên trong.

Ngược lại, weaving trực tiếp tại execution của method nội bộ có thể quan sát được nếu loại điểm đó được hỗ trợ và class tương ứng đã được xử lý.

Vì vậy phải xác định **điều muốn bao phủ là entry boundary hay toàn bộ internal execution** trước khi viết pointcut.

## 5. So sánh theo các thời điểm weaving

| Thời điểm/cách can thiệp | Có cần source thư viện? | Có cần sửa bytecode thư viện? | Khả năng và giới hạn tiêu biểu |
| --- | --- | --- | --- |
| **Compile-time weaving từ source** | Thường cần source hoặc biểu diễn đầu vào thích hợp | Có thể sinh artifact đã dệt | Hạn chế nếu không có quyền build lại thư viện |
| **Binary/post-compile weaving** | Không nhất thiết | Có, nếu dệt trực tiếp artifact thư viện | Phải kiểm tra license, chữ ký số, tương thích bytecode, phân phối |
| **Load-time weaving** | Không nhất thiết | Biến đổi bytes khi nạp, có thể không sửa JAR trên đĩa | Phụ thuộc agent/class loader/module, thời điểm và phạm vi lớp |
| **Runtime proxy/interception** | Không | Thường không | Chỉ chặn lời gọi đi qua proxy/interceptor; không tự thấy mọi lời gọi nội bộ |
| **Runtime class retransformation** | Không nhất thiết | Thay định nghĩa trong VM khi được hỗ trợ | Có giới hạn khả năng, loại lớp và thay đổi cấu trúc |
| **API hook/callback do thư viện cung cấp** | Không | Không | Ổn định hơn nếu API thiết kế cho mở rộng, nhưng chỉ trong phạm vi hook |
| **Quan sát tại network/IPC boundary** | Không | Không | Thấy tương tác client, không thấy internals dịch vụ từ xa |

Đây là bảng **năng lực khái quát**, không phải cam kết một công cụ cụ thể thực hiện được mọi ô. Một giải pháp compile-time có thể hỗ trợ đầu vào bytecode; một công cụ runtime có thể tạo subclass proxy; khả năng thật phải đối chiếu tài liệu và thử nghiệm.

### 5.1. Từ “không được sửa source” đến “không được sửa artifact”

Có source hay không khác với có quyền phân phối bản JAR đã thay đổi. Một tổ chức có thể cho phép chạy agent/instrumentation trong môi trường kiểm thử của mình, nhưng cấm xuất bản lại thư viện dưới dạng đã sửa. Không được đồng nhất “không cần source” với “không có ràng buộc bản quyền”.

## 6. Compile-time weaving khi thư viện không do ta build

Nếu chỉ build **mã ứng dụng**, trình biên dịch có thể nhìn các call site của ứng dụng nhưng không nhất thiết có quyền biến đổi phần thân bên trong JAR của nhà cung cấp.

Có ba tình huống:

1. **Chỉ dệt mã ứng dụng:** có thể chèn logic ở những join point thuộc mã của ta, như lời gọi tới API vendor nếu mô hình hỗ trợ.
2. **Đưa bytecode thư viện vào bước binary weaving:** có thể thay class thư viện mà không có source nếu công cụ và quyền sử dụng cho phép.
3. **Thư viện đã được nhà cung cấp dệt trước:** ta nhận artifact đã dệt sẵn, lúc đó cần xem rõ những advice nào đã có và có xung đột với instrumentation khác không.

Các hệ quả cần kiểm tra:

- Bản thư viện sau biến đổi có thể không khớp checksum/chữ ký số của bản phát hành gốc.
- Cần bảo đảm classpath/modulepath chứa **bản đã dệt** chứ không lẫn bản gốc.
- Phải giữ tài liệu phiên bản và quy trình tái lập build.
- Khi nhà cung cấp cập nhật JAR, có thể phải dệt lại và chạy lại kiểm thử.
- Một transform làm thay đổi ABI hoặc hành vi có thể làm mất khả năng hỗ trợ từ nhà cung cấp.

### 6.1. Rủi ro signed JAR

Một JAR có chữ ký số có thể chứa metadata xác minh nội dung. Sửa các entry đã ký mà không xử lý quy trình ký phù hợp có thể làm xác minh chữ ký thất bại hoặc vi phạm chính sách phân phối. Không nên tự coi “đã zip/JAR lại được” là artifact còn hợp lệ.

Nếu cần biến đổi trực tiếp, hãy quản lý provenance: bản gốc, hash, bước transform, bản sau transform, bản ký/phê duyệt phù hợp và quyền được làm việc đó.

### 6.2. Không chỉ là vấn đề cú pháp pointcut

Một pointcut đúng vẫn vô tác dụng nếu **lớp thư viện không nằm trong tập đầu vào weaving**. Ngược lại, dệt quá rộng có thể chạm vào nhiều class của thư viện mà người phát triển không chủ ý, làm tăng rủi ro về hiệu năng và tương thích.

## 7. Load-time weaving: can thiệp tại lúc nạp lớp

Trên JVM, cơ chế instrumentation có thể đăng ký transformer và nhận bytecode của class trước khi class được định nghĩa. Đây là một con đường để áp dụng hành vi vào bytecode thư viện **mà không sửa JAR trên đĩa**.

Pipeline khái niệm:

```text
Vendor library JAR (bytes gốc)
             |
             v
        Class loader
             |
             v
    Class-file transformer
             |
     +-------+--------+
     |                |
 Không chọn       Chọn class
     |                |
     v                v
 Giữ bytes       Sinh bytes đã biến đổi
     |                |
     +-------+--------+
             |
             v
     JVM define class
             |
             v
   Đường thực thi có hiệu lực
```

Đây là mô hình khái niệm. Một số công cụ thay đổi cấu trúc bytecode ngay tại điểm nạp; công cụ khác dùng phương án dispatch/tracking riêng.

### 7.1. Khả năng của Java instrumentation

Java 17 cung cấp API `java.lang.instrument.Instrumentation` và `ClassFileTransformer`. Agent có thể đăng ký transformer để xử lý class definition; một số môi trường hỗ trợ tái biến đổi hoặc định nghĩa lại class.

**Không phải mọi class đang chạy đều có thể sửa**, và không phải mọi thay đổi class đều hợp lệ. API cung cấp các phép kiểm tra khả năng như `isModifiableClass`, `isRetransformClassesSupported`; khi thao tác không được hỗ trợ có thể phát sinh lỗi phù hợp.

Trong những giới hạn tái biến đổi, thay đổi cấu trúc class như thêm/xóa trường hay phương thức có thể bị cấm dù thay đổi thân method được cho phép theo các ràng buộc cụ thể. Không suy rằng “agent attach thành công” nghĩa là có thể thực hiện mọi transform.

### 7.2. Thời điểm nạp có thể quyết định kết quả

Một class đã được nạp trước khi agent/transformer được kích hoạt có thể không nhận advice giống một class nạp sau. Nếu muốn tác động lên lớp đã nạp, cần xác minh **có hỗ trợ retransformation/redefinition** và cấu hình yêu cầu khả năng đó.

Không nên khẳng định hệ thống luôn có thể retroactively sửa mọi class. Điều kiện thực tế phụ thuộc JVM, agent manifest, loại class, trạng thái và loại thay đổi bytecode.

### 7.3. Tệp JAR gốc không nhất thiết là bytecode runtime

Khi dùng load-time weaving, `javap` trên thư viện gốc có thể không cho thấy lệnh advice vì transform chỉ được áp dụng khi class được nạp. Muốn kiểm tra mã thực, cần log transformer, bytecode dump hoặc công cụ chẩn đoán được môi trường hỗ trợ.

## 8. Runtime proxy: can thiệp khi kiểm soát đường gọi

Proxy phù hợp khi ứng dụng **có quyền thay đổi cách lấy và gọi đối tượng thư viện**, đặc biệt nếu thư viện công bố giao diện rõ ràng.

```text
App -> VendorInterface proxy -> interceptor -> VendorImplementation
```

**Ưu điểm:**

- Không đụng source hay class file của thư viện.
- Có thể bao quanh lời gọi của ứng dụng để đo thời gian, log, audit hoặc chuyển lỗi.
- Dễ tách logic quan sát khỏi đối tượng vendor và kiểm thử với fake.
- Thường ít rủi ro hơn biến đổi bytecode nội bộ.

**Giới hạn:**

- Caller phải thực sự sử dụng **proxy**.
- Lời gọi trực tiếp tới target không đi qua proxy sẽ bị bỏ qua.
- Lời gọi nội bộ từ target tới method khác trên `this` thường không đi qua proxy.
- Một proxy chỉ hiện thực giao diện được chọn không phải subclass của class vendor.
- Không tự chặn mọi constructor, static method, final method hay field access.
- Một số API không thiết kế bằng giao diện hoặc không cho thay thế instance theo cách ứng dụng cần.

Trong Java, **JDK dynamic proxy tạo instance của lớp thực thi các interface đã khai báo**; không thể dùng nó như một giải pháp chung để bao mọi class không có giao diện. Các công cụ khác có thể tạo subclass proxy, nhưng lại có giới hạn riêng khi class/method không thể override, constructor phức tạp hoặc cấu trúc class không cho subclass.

## 9. Ví dụ Java 17 đầy đủ: can thiệp thư viện ngoài mà không sửa mã vendor

Ta mô phỏng một thư viện của nhà cung cấp bằng **hai tệp riêng**, sau đó một ứng dụng dùng JDK dynamic proxy để chặn những lời gọi đi qua giao diện. Đây là ví dụ **chạy được bằng Java 17**, không phải một engine AOP tổng quát.

Mục tiêu quan sát:

- Lời gọi qua proxy có các bước trước/sau.
- Lời gọi trực tiếp tới vendor không có advice.
- Lời gọi nội bộ trên `this` của vendor không được proxy nhìn thấy.
- Ngoại lệ do vendor ném có thể được handler gỡ lớp bọc reflection và truyền về caller.

### 9.1. Mã “thư viện ngoài” — tệp `VendorGateway.java`

```java
public interface VendorGateway {
    String send(String id, int amount);
}
```

### 9.2. Triển khai “thư viện ngoài” — tệp `VendorClient.java`

```java
public final class VendorClient implements VendorGateway {
    @Override
    public String send(String id, int amount) {
        System.out.println("vendor:send:" + id + ":" + amount);
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        return "ACCEPTED:" + id;
    }

    public String internal(String id, int amount) {
        return send(id, amount);
    }
}
```

`VendorClient` ở đây được đánh dấu `final` để minh họa rằng ứng dụng **không cần subclass** khi dùng proxy giao diện. Lời gọi `internal` là lời gọi trực tiếp trên đối tượng vendor và `send` bên trong cũng chạy trên cùng đối tượng đó.

### 9.3. Mã ứng dụng — tệp `ThirdPartyInterceptionDemo.java`

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ThirdPartyInterceptionDemo {
    public static void main(String[] args) {
        VendorClient vendor = new VendorClient();

        VendorGateway intercepted = (VendorGateway) Proxy.newProxyInstance(
                VendorGateway.class.getClassLoader(),
                new Class<?>[] { VendorGateway.class },
                (proxy, method, arguments) -> {
                    String id = (String) arguments[0];
                    System.out.println("advice:before:" + id);
                    try {
                        Object result = method.invoke(vendor, arguments);
                        System.out.println("advice:after:" + id);
                        return result;
                    } catch (InvocationTargetException wrapper) {
                        Throwable original = wrapper.getCause();
                        System.out.println("advice:error:" + id + ":"
                                + original.getClass().getSimpleName());
                        throw original;
                    }
                }
        );

        System.out.println("caller:proxy:" + intercepted.send("A", 20));
        System.out.println("caller:direct:" + vendor.send("B", 30));
        System.out.println("caller:internal:" + vendor.internal("C", 40));

        try {
            intercepted.send("D", -1);
        } catch (IllegalArgumentException original) {
            System.out.println("caller:caught:" + original.getMessage());
        }
    }
}
```

### 9.4. Cách biên dịch và chạy

Đặt cả ba tệp trong một thư mục, dùng JDK 17 hoặc cao hơn:

```bash
javac VendorGateway.java VendorClient.java ThirdPartyInterceptionDemo.java
java ThirdPartyInterceptionDemo
```

Đầu ra xác định:

```text
advice:before:A
vendor:send:A:20
advice:after:A
caller:proxy:ACCEPTED:A
vendor:send:B:30
caller:direct:ACCEPTED:B
vendor:send:C:40
caller:internal:ACCEPTED:C
advice:before:D
vendor:send:D:-1
advice:error:D:IllegalArgumentException
caller:caught:negative amount
```

### 9.5. Giải thích các đường gọi

1. `intercepted.send("A",20)`: caller đi qua proxy, nên có `advice:before` và `advice:after`.
2. `vendor.send("B",30)`: caller gọi **trực tiếp** target, không qua proxy nên không có advice.
3. `vendor.internal("C",40)`: ứng dụng gọi helper trực tiếp; từ bên trong target có `this.send(...)`, vẫn không đi qua proxy, nên không có advice.
4. `intercepted.send("D",-1)`: có before advice; vendor ném `IllegalArgumentException`; `Method.invoke` bọc trong `InvocationTargetException`; handler lấy cause và ném lại lỗi gốc để caller bắt.

**Điểm giới hạn cần hiểu:** ở ca (3), ứng dụng có thể chủ động tạo wrapper cho `internal` nếu cần quan sát lời gọi **entry** của ứng dụng. Nhưng điều đó không tự tạo interception cho mọi lời gọi nội bộ trong thư viện.

### 9.6. Vì sao đây không phải weaving bytecode?

- Không thay đổi `VendorClient.class`.
- Không biên dịch pointcut DSL.
- Không chặn mọi cuộc gọi tới `VendorClient.send` trên VM.
- Không xem được mọi constructor/field/private method của vendor.
- Chỉ những caller dùng `intercepted` mới được chuyển qua handler.

Ví dụ thể hiện **quyền kiểm soát đường gọi**, chứ không thể chứng minh một công cụ AOP có thể can thiệp vào bytecode thư viện ngoài.

## 10. Mô phỏng thư viện được đóng gói thành JAR

Trong dự án thực tế, mã vendor thường được phân phối dưới dạng JAR. Ví dụ trên có thể được chia ranh giới build:

```text
VendorGateway.java + VendorClient.java -> vendor.jar
ThirdPartyInterceptionDemo.java        -> app dùng vendor.jar
```

Các lệnh mang tính minh họa trên JDK 17, chạy từ thư mục có đủ hai tệp vendor:

```bash
javac VendorGateway.java VendorClient.java
jar --create --file vendor.jar VendorGateway.class VendorClient.class
javac -cp vendor.jar ThirdPartyInterceptionDemo.java
```

Chạy trên hệ điều hành dùng dấu hai chấm phân cách classpath:

```bash
java -cp ".:vendor.jar" ThirdPartyInterceptionDemo
```

Trên Windows, dấu phân cách classpath thường là dấu chấm phẩy:

```text
java -cp ".;vendor.jar" ThirdPartyInterceptionDemo
```

Ở ví dụ mô phỏng, có thể còn class file vendor trong thư mục làm việc sau bước build; điều này không thay đổi việc proxy **không sửa** vendor. Để bảo đảm phép thử đóng gói thuần túy, hãy thực hiện với một thư mục ứng dụng sạch chỉ chứa JAR và mã app. **Không dùng ví dụ này làm hướng dẫn repack thư viện thương mại khi chưa kiểm tra quyền sử dụng.**

## 11. Khi thư viện không cung cấp interface

Giả sử chỉ có:

```java
public final class VendorUtility {
    public static String normalize(String value) {
        return value.trim();
    }
}
```

Đây là mảnh code minh họa, không có `main`.

Với JDK dynamic proxy, ta **không thể trực tiếp biến `VendorUtility` thành một proxy cùng kiểu class** theo cách như ví dụ giao diện vì proxy JDK hiện thực interface.

Những lựa chọn thay thế ở mức thiết kế:

1. **Application-owned adapter:** định nghĩa interface của mình và triển khai bằng một adapter gọi `VendorUtility.normalize`. Advice có thể quan sát lời gọi qua adapter.
2. **Wrapper/facade:** chuyển mọi nơi trong ứng dụng gọi thư viện về một đầu mối.
3. **Hook/callback chính thức:** nếu vendor có API extension được hỗ trợ.
4. **Bytecode weaving/instrumentation:** chỉ khi khả năng kỹ thuật và quyền sử dụng phù hợp.
5. **Boundary observation:** quan sát đầu vào/đầu ra ở nơi ứng dụng tiếp xúc với thư viện.

Adapter không can thiệp vào lời gọi mà code khác vẫn gọi trực tiếp `VendorUtility`. Để áp dụng chính sách nhất quán, kiến trúc ứng dụng phải thực sự chuyển những đường gọi quan trọng qua adapter.

### 11.1. Final class và final method

Vì class `final` không thể được subclass thông thường, các proxy dựa trên subclass sẽ gặp giới hạn. Tương tự, phương thức `final` không thể override trong subclass.

Tuy nhiên, **đây không phải hạn chế chung của tất cả bytecode instrumentation**: một bộ biến đổi class có quyền và năng lực phù hợp có thể dùng đường khác không phụ thuộc override. Đừng kết luận “final method thì mọi AOP đều bất lực”.

### 11.2. Constructor và static method

JDK dynamic proxy không biến constructor hoặc static method trên class vendor thành lời gọi giao diện thông thường qua proxy. Nếu cần quan sát các điểm này, phải xét mô hình join point và khả năng weaving khác, hoặc đặt một factory/adapter thuộc quyền ứng dụng.

## 12. Lớp và thành viên không công khai: ranh giới truy cập

Các thành viên `private`, package-private, protected và internal implementation làm việc can thiệp khó hơn so với API public.

Có những vấn đề khác nhau cần tránh trộn lẫn:

- **Java access control:** mã ứng dụng có quyền gọi trực tiếp thành viên hay không?
- **Reflection access:** có được phép truy cập sâu vào thành viên không?
- **JPMS/module encapsulation:** package có được export/open cho module liên quan không?
- **Instrumentation permission/capability:** class có modifiable và transform hợp lệ không?
- **Runtime calling model:** lời gọi thực tế có qua một đường interception được quản lý không?

Một engine biến đổi bytecode không nhất thiết dùng reflection để gọi private method; ngược lại, việc reflection báo `InaccessibleObjectException` không tự chứng minh mọi kỹ thuật can thiệp khác đều bất khả thi.

**Cách đúng là kiểm tra từng ranh giới theo công cụ đang dùng**, không suy kết luận từ một từ khóa `private` duy nhất.

### 12.1. Java module system (JPMS)

Một thư viện có thể nằm trong named module với quy tắc `exports` và `opens` rõ ràng. Package được export cho phép truy cập public API theo quan hệ module tương ứng; mở package phục vụ deep reflection theo phạm vi xác định. Hai khái niệm không giống nhau.

Trên môi trường có module encapsulation, một giải pháp AOP dùng reflection sâu có thể cần cấu hình mở package hợp lệ hoặc cơ chế instrumentation tương ứng. Việc thay đổi chính sách module có tác động bảo mật và bảo trì, không nên tự ý mở toàn bộ module.

Một Java agent có thể sử dụng một số API instrumentation liên quan module, nhưng không phải có agent là “vượt qua mọi rào cản” tự động. Phải kiểm tra quyền, module readability, access và hạn chế của VM.

## 13. Class loader và phạm vi khả kiến của thư viện ngoài

Một lớp Java không chỉ được định danh bởi tên đầy đủ; **class loader định nghĩa** cũng quan trọng đối với identity của class trong JVM.

Hai bản class cùng tên do hai loader khác nhau định nghĩa có thể không tương đương ở runtime. Điều này tác động tới:

- Loader nhìn thấy interface nào để tạo proxy.
- Loader có tải được advice/helper class không.
- Một agent có thấy và biến đổi mọi loader thích hợp không.
- Một plugin được nạp động có mang một bản vendor library riêng không.
- Nguy cơ `ClassCastException`, `LinkageError` hoặc xung đột phiên bản.

### 13.1. Thư viện ở plugin hoặc container

Một ứng dụng plugin có thể dùng loader riêng cho mỗi plugin. Nếu advice helper chỉ có ở class loader ứng dụng chính, bytecode đã biến đổi trong plugin có thể tham chiếu tới loại helper mà plugin không nhìn thấy, gây lỗi liên kết.

Đây là lý do **weaving được một class không đồng nghĩa class đó sẽ chạy thành công**: các tham chiếu do bộ dệt chèn thêm cũng phải thỏa ràng buộc truy cập và nạp lớp.

### 13.2. Lớp nạp bởi bootstrap loader

Một số lớp nền tảng Java được nạp bởi bootstrap loader hoặc cơ chế đặc biệt. Instrumentation có thể có hỗ trợ và đường khai báo phụ trợ riêng, nhưng không thể mặc định tất cả lớp nền tảng đều được phép biến đổi hoặc mọi helper class có thể được tìm thấy từ bootstrap context.

Với các lớp lõi, rủi ro tác động lan rộng tới toàn JVM đặc biệt lớn. Chỉ instrument khi có mục tiêu rõ, công cụ được hỗ trợ và kiểm thử tương thích nghiêm ngặt.

## 14. Thư viện native/JNI và mã ngoài JVM

Nếu thư viện Java gọi native method hoặc chuyển sang mã C/C++ thông qua JNI/FFI, AOP Java có thể can thiệp tại **ranh giới Java** nhưng không tự chèn advice vào từng instruction native.

```text
Java application
    |
    v
Java wrapper (có thể can thiệp)
    |
    v
JNI/native bridge
    |
    v
Native library (không tự động nằm trong join-point model Java)
```

Để quan sát chi tiết bên trong mã native cần công cụ phù hợp với runtime/native layer và quyền triển khai tương ứng. Tương tự, một lời gọi HTTP tới dịch vụ vendor bên ngoài chỉ cung cấp điểm đo ở phía client khi ta không kiểm soát tiến trình server.

Không nên mô tả một Java pointcut là “chặn được mọi hàm của thư viện ngoài” khi một phần quan trọng nằm ngoài mô hình join point hỗ trợ.

## 15. Quản trị rủi ro khi biến đổi artifact do bên thứ ba sở hữu

Đụng trực tiếp bytecode vendor có rủi ro cao hơn việc dùng public API qua wrapper.

### 15.1. Giấy phép, chữ ký số và provenance

Các câu hỏi phải có đáp án:

1. Quyền sử dụng có cho phép **sửa bản cài** trong môi trường của mình không?
2. Có được **phân phối lại** một JAR đã biến đổi không?
3. Nếu artifact có chữ ký số, bước biến đổi ảnh hưởng xác minh như thế nào?
4. Ai chịu trách nhiệm cung cấp bản vá bảo mật/phiên bản mới?
5. Có thể truy được hash của bản gốc và bản đã dệt không?
6. Có quy trình kiểm duyệt các thay đổi ở bytecode hoặc cấu hình agent không?

Không cần biến mọi lựa chọn thành tranh luận pháp lý phức tạp: **nếu wrapper theo public API đã đáp ứng đầy đủ yêu cầu, không nên biến đổi artifact bên thứ ba chỉ vì có thể làm được**.

### 15.2. Hỗ trợ của nhà cung cấp và nâng cấp phiên bản

Một pointcut vào private method `processInternal` có thể hoạt động trên một bản thư viện rồi bị hỏng khi nhà cung cấp refactor. Phần API public có versioning thường ổn định hơn các chi tiết nội bộ.

Với mỗi lần nâng cấp vendor:

- So sánh chữ ký và cấu trúc bytecode nếu đang instrument nội bộ.
- Kiểm tra những shadow đã được weaving còn tồn tại không.
- Kiểm thử tính đúng đắn, hiệu năng và ngoại lệ.
- Xác minh các quyền truy cập module/class loader.
- Lưu báo cáo thay đổi tập join point.
- Cập nhật cấu hình hoặc bỏ instrumentation không cần thiết.

## 16. Chi phí của các phương án: không chỉ runtime overhead

| Phương án | Chi phí chạy | Chi phí build/deploy | Chi phí bảo trì |
| --- | --- | --- | --- |
| Wrapper/adapter | Một tầng gọi/logic phụ trợ | Thường thấp | Phải chuyển mọi caller cần thiết |
| Interface proxy | Dispatcher và advice theo invocation | Cấu hình tạo/thay thế instance | Quản lý việc bypass và hợp đồng interface |
| Compile/binary weaving | Có thể tối ưu tốt hoặc có guard runtime | Build/artifact phức tạp hơn | Reweave khi nâng cấp vendor |
| Load-time weaving | Chi phí transform lúc load + runtime advice | Agent/loader/module/config | Chẩn đoán khi lớp không được dệt |
| Retransformation | Chi phí/giới hạn VM và chuyển đổi | Quản trị agent attach/lifecycle | Khó bảo đảm mọi class/mọi trạng thái |
| Network boundary tracing | Phụ thuộc handler/client | Cấu hình client/transport | Không quan sát được internals |

Chi phí thực tế phải **đo** chứ không suy từ nhãn kỹ thuật. Một proxy cho điểm nóng có thể tạo overhead đáng kể; một transformer chèn quá nhiều advice cũng có thể gây chi phí lớn. Ngược lại, wrapper đơn giản có thể giúp tách điểm can thiệp rõ và dễ kiểm thử.

### 16.1. Static match và dynamic guard

Nếu pointcut chọn thư viện theo tên method nhưng còn điều kiện theo tham số/đối tượng runtime, một phần logic có thể được xác định trước, phần còn lại phải kiểm tra trên mỗi invocation phù hợp.

Đừng dùng `cached=true` theo chữ ký cho mọi lần chạy khi kết quả phụ thuộc giá trị tham số. Ví dụ số tiền 20 và 20.000 trên cùng method phải được phân biệt nếu chính sách yêu cầu ngưỡng.

## 17. Lỗi thường thấy khi áp AOP vào thư viện ngoài

**Lỗi 1 — “Không có source thì AOP không làm được gì.”** Sai. Call-site weaving, binary/load-time instrumentation, proxy hoặc wrapper có thể phù hợp mà không sửa source vendor.

**Lỗi 2 — “Có pointcut thì chạm được mọi method trong JAR.”** Sai. Phải xét mô hình join point, phạm vi weaving, loader, module và quyền truy cập.

**Lỗi 3 — “Proxy bao được mọi lời gọi nội bộ.”** Không. Proxy giao diện chỉ thấy các lời gọi đi qua đối tượng proxy; target tự gọi trên `this` có thể không đi qua nó.

**Lỗi 4 — “Final class nghĩa mọi cơ chế AOP đều không can thiệp.”** Không. Final cản subclass/override nhưng không tự loại bỏ mọi kỹ thuật bytecode instrumentation.

**Lỗi 5 — “Agent đã chạy thì mọi class đã nạp đều có advice.”** Không. Phải xét lúc agent/transformer kích hoạt và khả năng retransformation.

**Lỗi 6 — “Sửa signed JAR rồi đóng gói lại là ổn.”** Chưa chắc. Chữ ký và chính sách phân phối có thể không còn hợp lệ.

**Lỗi 7 — “Dùng reflection là truy cập được mọi private method.”** Không. Access rules, JPMS và cấu hình runtime có thể hạn chế.

**Lỗi 8 — “Chặn wrapper Java nghĩa thấy được mọi hoạt động native.”** Không. Native code nằm ngoài mô hình Java join point thông thường.

**Lỗi 9 — “Biến đổi vendor method không ảnh hưởng hỗ trợ/bảo hành.”** Không thể khẳng định. Cần đọc điều khoản và đánh giá trách nhiệm khi xảy ra sự cố.

**Lỗi 10 — “Nhìn thấy log của một lần gọi chứng minh đầy đủ coverage.”** Không. Cần kiểm tra cả các đường gọi trực tiếp, nội bộ, static, async và các phiên bản thư viện khác.

## 18. Kiểm thử trước khi tuyên bố can thiệp thành công

Một bộ kiểm thử nên bao gồm **những nơi advice phải chạy** và **những nơi không được chạy**.

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| Lời gọi ứng dụng qua proxy | Advice chạy đúng số lần |
| Lời gọi trực tiếp target | Không bị nhầm là đi qua proxy |
| Lời gọi nội bộ `this.method()` | Hành vi đúng giới hạn công cụ |
| Method overload | Không chọn thừa hoặc bỏ sót chữ ký |
| Final/static/constructor | Có/không theo khả năng từng kỹ thuật |
| Phương thức private | Không mặc định có thể truy cập |
| Class nạp trước transformer | Có cần/cho phép retransformation không |
| Class loader khác nhau | Helper/advice có thể được liên kết đúng không |
| Named module | Quyền export/open/readability phù hợp không |
| JAR signed | Artifact có còn hợp lệ theo chính sách không |
| Method ném ngoại lệ | Caller thấy lỗi/cause đúng hợp đồng |
| Advice hậu xử lý ném lỗi | Không nhầm business thất bại khi đã có side effect |
| Nhiều aspect cùng khớp | Thứ tự có hiệu lực đúng |
| Hot path đồng thời | Không trộn context, không chi phí quá mức |
| Nâng cấp vendor JAR | Báo cáo tập điểm khớp thay đổi |
| Thư viện native hoặc remote | Ranh giới Java/client được hiểu đúng |

### 18.1. Chứng cứ ba tầng

Muốn chắc chắn không bỏ sót, hãy thu thập:

1. **Tầng cấu trúc:** pointcut chọn shadow nào, class nào được đưa vào weaving.
2. **Tầng triển khai:** transform/proxy/adapter có được cài đặt và kết nối đúng không.
3. **Tầng runtime:** các invocation thực tế có đi qua advice, guard và continuation đúng như chính sách không.

Một báo cáo pointcut khớp tĩnh không đủ nếu lời gọi bypass proxy. Một log runtime từ một đường gọi cũng không chứng minh tất cả phương thức trong JAR đã được weaving.

## 19. Chẩn đoán khi advice không chạy ở thư viện vendor

Áp dụng quy trình theo thứ tự:

1. **Tái hiện chính xác đường gọi:** client đi qua proxy hay gọi trực tiếp?
2. **Xác định điểm muốn can thiệp:** call site ở app, execution ở vendor, hay native/remote boundary?
3. **Kiểm tra cú pháp pointcut và chữ ký:** declaring type, overload, modifier, subtype và annotation.
4. **Xác minh phạm vi weaving:** app-only, JAR bên ngoài, package/class cụ thể.
5. **Kiểm tra class loader/module:** class đang chạy có đến từ loader khác, module không mở, hay class bị trùng không?
6. **Kiểm tra thời điểm nạp:** class đã nạp trước transformer hoặc không thuộc tập retransformation?
7. **Kiểm tra quyền/kỹ thuật sửa class:** class có modifiable, bytecode hợp lệ, classpath helper đầy đủ không?
8. **Kiểm tra guard động:** tham số, runtime type hoặc ngữ cảnh có làm pointcut trượt không?
9. **Kiểm tra advice khác:** outer around advice có thể ngăn `proceed` đến pointcut trong.
10. **Đọc log và report của weaver:** không nhầm “không có log” với “không weaving”.
11. **Giảm thành ví dụ tối thiểu:** kiểm tra một lần qua proxy và một lần bypass.
12. **Đối chiếu build/version:** đúng JAR vendor và đúng cấu hình agent chưa?

**Không chữa lỗi bằng cách mở rộng wildcard vô hạn.** Nếu vấn đề là class loader hoặc đường gọi không qua trung gian, pointcut rộng hơn thường không giải quyết được và còn gây can thiệp thừa.

## 20. Ma trận lựa chọn theo nhu cầu và quyền kiểm soát

Một bảng quyết định thực tế:

| Mục tiêu | Kiểm soát được gì? | Lựa chọn nên xem trước | Khi cần phương án mạnh hơn |
| --- | --- | --- | --- |
| Đo thời gian mọi lần app gọi vendor API | Chỗ app tạo/gọi client | Wrapper, interface proxy | Call-site weaving nếu nhiều đường khó thay |
| Quan sát private helper của vendor | Chỉ có JAR | Kiểm tra public API/hook trước | Bytecode weaving nếu thật sự cần và được phép |
| Chặn external SDK static utility | Mã gọi trong app | Application-owned facade | Call-site/bytecode weaving có kiểm chứng |
| Theo dõi thư viện được nạp khi chạy | Quyền JVM/agent | Load-time instrumentation phù hợp | Retransform nếu cần và được hỗ trợ |
| Áp policy trên microservice vendor ở máy khác | Chỉ kiểm soát client | Client interceptor/network telemetry | Cần quyền ở server mới quan sát internals |
| Can thiệp class final | Có interface public | JDK interface proxy | Bytecode instrumentation hoặc adapter khi phù hợp |
| Can thiệp trên module đóng | Quyền ứng dụng hạn chế | Public API/adapter | Cấu hình module/agent được phê duyệt |
| Duy trì qua nâng cấp vendor thường xuyên | Chỉ API ổn định | Facade/adapter có kiểm thử | Instrument internals chỉ khi có năng lực bảo trì |

**Lựa chọn ưu tiên thường là ít xâm lấn nhất nhưng vẫn đủ phạm vi chính sách.** Nếu public API/hook đáp ứng yêu cầu, đó thường là phương án dễ nâng cấp hơn việc dệt vào private implementation.

## 21. Một số trường hợp nâng cao cần cân nhắc

### 21.1. Multi-release JAR và biến thể runtime

Một số artifact Java có các phiên bản class khác nhau cho những mức Java khác nhau. Khi kiểm tra bytecode và xây matcher, cần xác định **class thực sự được JVM chọn**. Dệt nhầm biến thể hoặc kiểm thử trên JDK khác production có thể tạo kết luận sai.

### 21.2. Method bridge/synthetic do compiler sinh

Generic types và đa hình có thể làm Java compiler sinh các method bridge/synthetic. Weaver nhìn vào bytecode có thể thấy nhiều method hơn người đọc source dự đoán. Nếu advice áp vào cả bridge và target một cách không phù hợp, có thể quan sát log thừa hoặc thời gian bị đo lặp.

Không có quy tắc chung rằng mọi weaver đều tự loại những method đó; phải xem model/matcher của công cụ và kiểm thử.

### 21.3. Thư viện dùng callback

Một vendor library có thể gọi callback do ứng dụng cung cấp. Khi đó điểm callback nằm trong mã **do ta sở hữu**, nên đôi khi có thể áp advice ngay trên callback để quan sát sự kiện mà không sửa JAR vendor.

Nhưng callback chỉ cho thông tin mà API cung cấp. Nó không biến mọi thao tác nội bộ thành sự kiện có thể nhìn thấy.

### 21.4. Thư viện hoạt động bất đồng bộ

Khi API trả `Future` hoặc `CompletableFuture`, method return không đồng nghĩa công việc bên trong đã hoàn tất. Proxy chỉ đo thời gian gọi `submit()` có thể bỏ qua thời gian task chạy về sau. Nếu cần đo completion, phải gắn logic vào stage phù hợp hoặc dùng hook của API, giữ ngữ cảnh và lỗi đúng vòng đời.

### 21.5. Hot instrumentation và thay đổi đang chạy

Định nghĩa lại hoặc retransformation class lúc JVM đang chạy có những hạn chế ngữ nghĩa và tác động đến frame đang hoạt động. Không mặc định mọi lời gọi đang chạy lập tức đổi sang mã mới; cần hiểu hợp đồng runtime đối với active frames và xác minh khả năng trên JVM đích.

### 21.6. Nhiều bộ biến đổi cùng tác động một lớp

Profiler, coverage agent, security instrumentation và AOP weaver có thể cùng xử lý một class. **Thứ tự transformer** và tính tương thích của bytecode sau từng bước có thể ảnh hưởng kết quả. Cần quan sát thứ tự áp dụng, kiểm tra có nhân đôi instrumentation hay làm hỏng stack map/verification không, và tránh giả định một transformer luôn hoạt động độc lập.

## 22. Bảo mật và trách nhiệm khi can thiệp code không thuộc mình

Instrumenting thư viện không chỉ là vấn đề kỹ thuật. Một advice có thể:

- Truy cập dữ liệu trước khi thư viện bảo vệ/che đi.
- Ghi log tham số nhạy cảm hoặc token.
- Làm thay đổi luồng xác thực/ủy quyền.
- Nuốt ngoại lệ của cơ chế bảo mật.
- Thay đổi kết quả phương thức theo cách caller không mong đợi.
- Thêm dependency dễ xung đột hoặc tạo cơ chế nạp code mới.
- Làm sai thông tin kiểm toán hoặc ảnh hưởng hiệu năng toàn ứng dụng.

Vì vậy cần quy định **ai được sửa cấu hình weaving**, **những module/class nào được phép can thiệp**, **review/test ra sao**, **log được phép lưu gì** và **cách rollback/disable** khi gặp sự cố.

Một pointcut rộng vào thư viện mật mã hoặc bảo mật có thể tác động tới nhiều luồng trọng yếu. Không nên can thiệp các thành phần nhạy cảm chỉ vì engine cho phép; phải có mục đích chính đáng, phạm vi rõ và kiểm chứng an toàn.

## 23. Bài tập tự luyện

**1.** Ứng dụng gọi thư viện ngoài qua một interface public, chỉ cần log các lời gọi do ứng dụng phát ra. Có cần sửa JAR không?

Không nhất thiết. Có thể dùng adapter/proxy hoặc cơ chế can thiệp vào call site do ứng dụng sở hữu, miễn tất cả đường gọi mong muốn thực sự đi qua ranh giới đó.

**2.** Vendor method tự gọi `this.internalMethod()`. Vì sao JDK dynamic proxy không tự thấy lời gọi nội bộ?

Vì lời gọi ấy thực hiện trên đối tượng target, không chuyển qua proxy mà ứng dụng tạo ở bên ngoài.

**3.** Một class `final` có thể được quan sát qua JDK interface proxy không?

Có thể, nếu class triển khai interface phù hợp và ứng dụng sử dụng proxy của interface đó. Final class không thể subclass theo Java thông thường, nhưng proxy giao diện không cần subclass target.

**4.** Một Java agent được kích hoạt sau khi class vendor đã nạp. Có thể khẳng định class đó sẽ được weave không?

Không. Phải kiểm tra khả năng retransformation/redefinition, cấu hình agent và class có modifiable hay không.

**5.** Tệp JAR gốc chưa có lệnh advice khi xem bằng `javap`. Điều đó chứng minh load-time weaving không chạy không?

Không. Class có thể được biến đổi khi nạp. Cần quan sát bytecode/runtime report đúng thời điểm.

**6.** Một thư viện nằm trong named module không mở private package. Có thể mặc định reflection vào mọi private field không?

Không. Module encapsulation và access rules có thể ngăn deep reflection. Cần dùng public API hoặc cấu hình được cho phép; bytecode instrumentation là một vấn đề năng lực khác, không phải “tự động vượt quyền”.

**7.** Ứng dụng Java gọi một dịch vụ vendor qua HTTP. AOP trong ứng dụng có nhìn thấy private method ở server không?

Không, vì mã ấy chạy ở tiến trình bên ngoài. Ta có thể quan sát client request/response; muốn instrument server cần quyền trên hệ thống server và công cụ tương ứng.

**8.** Vì sao cần xem license trước khi phân phối JAR vendor đã dệt?

Vì việc có thể biến đổi về kỹ thuật không xác nhận quyền sửa hoặc phân phối lại. Artifact signed, hỗ trợ nhà cung cấp và trách nhiệm cập nhật cũng có thể bị ảnh hưởng.

**9.** Khi nâng cấp thư viện, pointcut vẫn hợp cú pháp nhưng advice biến mất. Những nguyên nhân nào nên kiểm tra?

Đổi method signature, đổi loader/module, class khác được runtime chọn, thay đổi phạm vi weaving, điều kiện động, việc gọi không đi qua proxy, hoặc private implementation đã refactor.

**10.** Nếu muốn ghi trace một lần cho mỗi thao tác vendor, tại sao không tự động dệt cả mọi private helper?

Có thể tạo log thừa và chi phí không cần thiết; một thao tác public gọi nhiều helper, dẫn tới đếm sai số sự kiện. Cần chọn ranh giới nghiệp vụ phù hợp và kiểm thử số lần advice chạy.

## 24. Checklist áp dụng trước khi can thiệp thư viện ngoài

- [ ] Xác định chính xác **điểm call hay execution** cần can thiệp.
- [ ] Biết thư viện chạy trong cùng JVM hay tiến trình ngoài.
- [ ] Xác định chỉ cần quan sát lời gọi từ app hay cả hoạt động nội bộ.
- [ ] Đánh giá quyền sở hữu source/artifact/runtime và điều khoản cấp phép.
- [ ] Ưu tiên public hook, adapter hoặc proxy khi đủ yêu cầu.
- [ ] Đã kiểm tra công cụ hỗ trợ loại join point cần thiết.
- [ ] Đã kiểm tra phạm vi weaving của các class thư viện.
- [ ] Với load-time weaving, xác minh thời điểm class được nạp và transformer.
- [ ] Với retransformation, kiểm tra capability và giới hạn thay đổi class.
- [ ] Kiểm tra Java module, class loader và khả năng nạp helper.
- [ ] Kiểm tra final/private/static/constructor theo cơ chế thực tế, không suy chung.
- [ ] Xác minh signed JAR, hash, phiên bản và provenance nếu đổi artifact.
- [ ] Có kiểm thử qua proxy và trực tiếp target.
- [ ] Có kiểm thử self-invocation và internal call nếu thuộc phạm vi mong muốn.
- [ ] Có test overload, override, bridge/synthetic và phiên bản vendor mới khi liên quan.
- [ ] Kiểm tra return, exception, cause và side effect vẫn đúng hợp đồng.
- [ ] Không log dữ liệu nhạy cảm từ vendor args/result.
- [ ] Có số đo overhead cho hot path và tải đồng thời.
- [ ] Có rollback hoặc cách tắt instrumentation khi phát sinh lỗi.
- [ ] Có báo cáo những class/join point đã được xử lý và những đường không bao phủ.

## 25. Tài liệu tham khảo cho các khả năng JVM cụ thể

Các nguồn dưới đây mô tả **API Java SE 17**, không phải một đặc tả chung của mọi AOP engine:

- [Java 17 — `Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): dynamic proxy theo interface và các điều kiện module/loader.
- [Java 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): bytecode transform khi định nghĩa/nạp, redefine, retransform.
- [Java 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): agent instrumentation, capability và giới hạn retransformation.
- [Java 17 — Gói `java.lang.instrument`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): cơ chế agent và cấu hình liên quan.

Khi áp dụng với một công cụ AOP thật, cần đối chiếu thêm tài liệu chính thức của **chính công cụ ấy** về pointcut, loại join point, thứ tự advice, phạm vi weaving và tương thích bytecode.

## 26. Kết luận

**Giới hạn sở hữu mã không đồng nhất với giới hạn khả năng can thiệp.** Ta có thể quan sát hành vi của thư viện ngoài bằng wrapper, proxy, call-site weaving, biến đổi bytecode hoặc instrumentation — nhưng mỗi lựa chọn yêu cầu một mức kiểm soát khác nhau đối với đường gọi, lớp được nạp, artifact hoặc runtime.

Để chọn đúng phương án, hãy luôn làm rõ ba ranh giới:

1. **Ranh giới kỹ thuật:** điểm nào thuộc mô hình join point và phạm vi weaving có thật.
2. **Ranh giới kiểm soát:** ứng dụng sở hữu call site, class loader, JVM, artifact hay chỉ có public API.
3. **Ranh giới trách nhiệm:** giấy phép, bảo mật, tương thích, hỗ trợ nhà cung cấp và hành vi nghiệp vụ khi advice hoạt động.

Phương án tốt là phương án **ít xâm lấn nhất nhưng đủ phạm vi yêu cầu**, có thể chứng minh bằng kiểm thử dương/âm, có khả năng truy vết phiên bản và không dựa vào giả định rằng một pointcut có thể tự động kiểm soát toàn bộ mã bên ngoài.
