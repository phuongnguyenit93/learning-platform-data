# Pointcut quá rộng hoặc phụ thuộc chi tiết dễ thay đổi

## 1. Vấn đề cốt lõi

Trong **Aspect-Oriented Programming (AOP)**, *pointcut* xác định **join point nào** được lựa chọn để áp dụng *advice*. Một pointcut có thể được viết rất ngắn nhưng ảnh hưởng tới hàng trăm phương thức. Khi lựa chọn sai phạm vi, AOP có thể trở thành nguồn lỗi kín đáo: hành vi bổ sung xuất hiện ngoài dự kiến, bỏ sót điểm cần xử lý, chi phí tăng lên hoặc kết quả thay đổi sau một lần đổi tên package tưởng như vô hại.

Có hai dạng sai lầm cần phân biệt:

1. **Quá rộng (overmatching):** pointcut khớp nhiều join point hơn ý định. Ví dụ, chỉ cần audit thao tác đặt hàng nhưng lại áp dụng ghi log cho mọi phương thức trong package nghiệp vụ, kể cả getter, kiểm tra nội bộ và thao tác nhạy cảm.
2. **Phụ thuộc chi tiết dễ thay đổi (brittle matching):** pointcut xác định “đúng” hành vi bằng tên lớp, tên phương thức, vị trí file/package, kiểu tham số hoặc cách tổ chức code vốn không phải một phần của hợp đồng nghiệp vụ. Khi refactor, advice âm thầm biến mất hoặc áp dụng sang phương thức khác.

Cũng có lỗi đối xứng là **khớp quá hẹp (undermatching)**: pointcut chỉ nhận một số join point đáng lẽ phải được bảo vệ hoặc quan sát. Một pointcut tốt cần đồng thời có **độ bao phủ đúng** và **độ chọn lọc đúng**, không chỉ “có chạy” ở ví dụ đầu tiên.

Bài này bàn về **AOP nói chung**, minh họa cú pháp pointcut theo phong cách AspectJ khi cần thiết. Phạm vi join point hỗ trợ phụ thuộc công cụ weaving/interception cụ thể; không được giả định mọi hệ AOP đều cung cấp cùng bộ designator hoặc cùng cách áp dụng lời gọi nội bộ.

## 2. Khái niệm cần giữ tách biệt

- **Join point:** điểm trong quá trình thực thi mà mô hình AOP cho phép can thiệp; một số hệ thống hỗ trợ method execution, method call, field access, constructor, handler... tùy cơ chế.
- **Pointcut:** điều kiện chọn một tập join point. Có thể gồm phần xác định tĩnh (kiểu, chữ ký, annotation) và điều kiện phụ thuộc ngữ cảnh runtime.
- **Advice:** logic bổ sung trước, sau hoặc bao quanh join point đã chọn.
- **Weaving/interception:** cách kết nối advice tới join point, chẳng hạn biến đổi bytecode khi build/nạp lớp hoặc chuyển lời gọi qua đối tượng trung gian.
- **Shadow:** trong một số mô hình weaving, vị trí mã có thể trở thành join point khi chạy; việc một shadow được chọn hay không có thể được quyết định một phần ở build time.

**Pointcut là hợp đồng chọn hành vi.** Hợp đồng ấy cần nói được “vì sao một join point thuộc phạm vi”, có ví dụ phản chứng và được kiểm thử khi codebase thay đổi.

## 3. Vì sao pointcut quá rộng thường nguy hiểm?

### 3.1. Ví dụ đối chiếu

Giả sử chỉ muốn đo thời gian các thao tác nghiệp vụ cập nhật đơn hàng. Một biểu thức minh họa theo cú pháp AspectJ:

```java
// Quá rộng: mọi method execution trong package demo và các package con.
pointcut almostEverything():
    execution(* demo..*.*(..));
```

Đây là **mảnh cú pháp bên trong một aspect**, không phải chương trình Java độc lập. `execution` chọn method execution join point; `*` đại diện mẫu kiểu/tên phù hợp; `(..)` khớp danh sách tham số tùy ý; `demo..*` là mẫu kiểu trong package `demo` và các mức package con phù hợp. Cách khớp cụ thể phải được xác minh bằng công cụ AOP đang sử dụng.

Nếu package chứa `OrderService.place`, `OrderService.status`, `Inventory.read` và cả các helper, advice có thể chạy rất nhiều lần ngoài dự tính. Nếu pointcut được dùng để audit dữ liệu, một getter từng là “vô hại” cũng có thể làm lộ thông tin trong log hoặc tạo chi phí không cần thiết.

Một lựa chọn chọn lọc hơn:

```java
// Hẹp theo chữ ký và ý định hiện tại:
pointcut placeOrder():
    execution(public void demo.order.OrderService.place(java.lang.String));
```

Biểu thức này nhắm một thao tác cụ thể, nhưng đánh đổi bằng **phụ thuộc mạnh vào tên lớp và chữ ký**. Thay đổi tên phương thức, kiểu tham số hay chuyển nơi cài đặt có thể khiến pointcut không còn khớp. Nên coi đây là giải pháp hợp lý khi chữ ký ổn định và có test bảo vệ, không phải lựa chọn mặc định cho mọi concern.

### 3.2. Hệ quả về tính đúng

Một pointcut quá rộng có thể:

- Ghi dữ liệu riêng tư hoặc nhạy cảm ngoài chính sách vì advice thu thập args/result trên các phương thức không định quan sát.
- Thực thi kiểm tra quyền hay logic giao dịch ở những ngữ cảnh không thích hợp, khiến chương trình lỗi bất ngờ.
- Chạy advice nhiều lần trong một chuỗi gọi lồng nhau; cùng request có thể bị đo/ghi nhiều event thay vì một event nghiệp vụ.
- Kéo vào phương thức gọi đệ quy hoặc các thao tác kỹ thuật, gây tăng độ sâu call stack, logging storm hoặc tái nhập (*re-entrancy*).
- Thay đổi thứ tự side effect, exception hoặc kết quả khi dùng around advice xử lý sai `proceed`.
- Khi một developer thêm phương thức mới dưới package đã bị chặn, advice cũng áp dụng cho phương thức đó mà không qua quyết định thiết kế rõ ràng.

Tất cả vấn đề trên **có thể tồn tại dù unit test nghiệp vụ thuần vẫn pass**, vì sai lệch chỉ xuất hiện khi cơ chế weaving/interception được kích hoạt trên artifact thực sự chạy.

### 3.3. Hệ quả về hiệu năng

Dù advice rất nhẹ, số lần thực thi mới là yếu tố quyết định:

```text
Chi phí tương đối ≈ số join point được chặn ×
                    chi phí dispatch/điều kiện/advice mỗi lần
                    + tác động phụ lên allocation, I/O, JIT và GC
```

Đây là mô hình để suy nghĩ, không phải công thức benchmark chính xác. Một lời gọi ghi log trong đường nóng chạy hàng triệu lần có thể tốn nhiều hơn việc intercept một API biên chỉ chạy vài trăm lần. Pointcut mở rộng còn có thể tăng khối lượng tìm khớp/weaving, số class bị biến đổi, bộ nhớ metadata hoặc thời gian nạp lớp; mức độ tùy công cụ.

**Nguyên tắc:** trước khi tối ưu một handler vài nanosecond, hãy kiểm tra có đang intercept quá nhiều join point hay không.

## 4. Vì sao pointcut theo tên và cấu trúc dễ hỏng?

Xem một số kiểu phụ thuộc:

| Dạng ghép pointcut | Thay đổi khiến nó lệch | Triệu chứng |
|---|---|---|
| `execution(* *..*Service.*(..))` | Đổi hậu tố tên lớp, tách interface/implementation | Advice không còn chạy dù ý định nghiệp vụ không đổi |
| `within(com.acme.oldpackage..*)` | Chuyển lớp sang package mới | Toàn bộ nhánh hành vi mất advice |
| `execution(* *.save*(..))` | Đổi tên `save` thành `persist`, thêm `saveDraft` | Vừa có thể bỏ sót vừa có thể khớp nhầm |
| `execution(* *(java.lang.String))` | Đổi DTO, overload, boxing/thay tham số | Hành vi áp dụng theo hình dạng chữ ký thay vì ý nghĩa |
| `call(* SomeType.*(..))` | Chuyển logic gọi, thêm wrapper/adapter | Điểm gọi thay đổi dù method target không đổi |
| Annotation mang ý nghĩa nghiệp vụ | Quên gắn/bỏ nhầm marker; annotation bị dùng sai | Pointcut cũng có thể sai dù không phụ thuộc tên |

Các ví dụ cú pháp trong bảng chỉ để thể hiện **kiểu coupling**; một số mẫu viết ngắn cần được đặt vào biểu thức pointcut đầy đủ và kiểm tra với cú pháp của weaver được chọn.

Mức độ mong manh phụ thuộc **tính ổn định của dấu hiệu**. Tên package thường phản ánh bố cục kỹ thuật, trong khi một marker có chủ đích như `@AuditedOperation` có thể diễn đạt rõ hợp đồng. Nhưng marker cũng cần người sở hữu, quy trình review, chính sách kế thừa và test để tránh bị gắn nhầm.

### 4.1. Một lần refactor gây mất advice âm thầm

Trước refactor:

```text
demo.order.OrderService.place(String)
  └─ pointcut theo đúng tên/chữ ký → có audit
```

Sau refactor:

```text
demo.order.CheckoutWorkflow.submit(OrderCommand)
  └─ giữ nguyên ý nghĩa "xác nhận đặt hàng"
  └─ pointcut cũ theo OrderService.place(String) → không còn khớp
```

Nếu compiler không được cấu hình cảnh báo cho pointcut bắt buộc không khớp, build có thể vẫn thành công. Chỉ một kiểm thử có cả **luồng nghiệp vụ** và **kỳ vọng advice** mới dễ phát hiện vấn đề.

### 4.2. Sai lầm khi dựa vào package name

Package được đổi để sắp xếp thư mục, chia module, hoặc cô lập thành phần dùng chung. Một pointcut tên package có thể:

- Mất hiệu lực khi package đổi tên.
- Vô tình bao phủ class được chuyển vào package phù hợp.
- Tạo phạm vi khác nhau theo phiên bản artifact, class loader hoặc cấu hình weaving.
- Khi dùng thư viện bên ngoài, tên package thay đổi ngoài quyền kiểm soát của đội ứng dụng.

Package vẫn hữu ích làm **vòng giới hạn kỹ thuật bên ngoài** (scope), đặc biệt để tránh weave code của JDK, thư viện hoặc chính infrastructure aspect. Nhưng riêng package thường không đủ diễn đạt một quy tắc nghiệp vụ.

## 5. Các nguyên tắc thiết kế pointcut bền vững

### 5.1. Bắt đầu từ hợp đồng nghiệp vụ

Hãy viết rõ bằng lời:

> “Audit các **thao tác xác nhận đơn hàng được công bố như API nghiệp vụ**; không audit truy vấn trạng thái, helper hay chức năng quản trị.”

Sau đó mới chọn cách biểu đạt: marker annotation, interface/hợp đồng, type hierarchy, chữ ký ổn định hoặc tổ hợp điều kiện. Nếu không thể chỉ rõ tập join point mong đợi bằng lời và test, pointcut có nguy cơ được viết theo cấu trúc code tiện tay.

### 5.2. Dùng ranh giới có chủ đích

Những cách định nghĩa phạm vi thường có ích:

1. **Marker mang ngữ nghĩa:** annotate đúng phương thức/type cần concern, ví dụ `@AuditedOperation`, để việc review dễ xác định ý định. Chính sách gắn marker và nơi marker được đọc cần rõ.
2. **Interface hoặc type ổn định:** áp dụng cho các implementation của một capability có hợp đồng ổn định. Chú ý khác biệt giữa execution method và proxy interface interception.
3. **Named pointcut:** gom biểu thức phức tạp vào pointcut có tên rõ nghĩa; nhiều advice dùng cùng một định nghĩa để tránh lệch logic.
4. **Giới hạn package/type:** dùng thêm điều kiện tránh quét toàn bộ ứng dụng hay dependency; không lấy wildcard rộng làm toàn bộ hợp đồng.
5. **Explicit exclusion:** loại trừ helper/diagnostics hoặc các lớp mà advice tự sử dụng, khi cần để tránh đệ quy hoặc tác động ngoài ý muốn.

Điểm cuối không có nghĩa cứ thêm `!within(...)` là chữa được gốc vấn đề. Exclusion liên tục phình to là tín hiệu pointcut gốc quá rộng hoặc boundary không được định nghĩa rõ.

### 5.3. Ưu tiên tính đọc được

So sánh hai ý tưởng:

```java
// Khó hiểu ý đồ, nhiều wildcard:
execution(* *(..)) && !within(demo.debug..*)
                  && !within(demo.generated..*)
                  && !within(demo.internal..*)
```

```java
// Ví dụ mảnh biểu thức mang ý định rõ hơn:
execution(public * demo.orders.api..*(..))
    && @annotation(demo.audit.AuditedOperation)
```

Đoạn thứ hai vẫn cần kiểm tra chính xác kiểu method được match và semantics của `@annotation` ở framework/weaver đang dùng. Điểm mấu chốt là **phạm vi API + dấu hiệu nghiệp vụ có chủ đích**, chứ không phải mọi tên phương thức trông giống nghiệp vụ.

### 5.4. Điều kiện tĩnh và động

Một số bộ pointcut có thể lọc tại weave time theo signature/type/annotation, còn điều kiện theo argument hoặc control flow phải được xét tại runtime. Ví dụ `args(...)` có thể ràng buộc kiểu/giá trị ngữ cảnh, `if()` có thể đặt điều kiện động, `cflow(...)` chọn ngữ cảnh luồng gọi; cú pháp và chi phí phụ thuộc công cụ.

Không đưa mọi logic lọc vào điều kiện động của advice nếu có thể xác định tĩnh ranh giới đáng tin. Tuy nhiên, một điều kiện phụ thuộc **dữ liệu request** có thể bắt buộc được đánh giá runtime; tránh kết luận rằng mọi điều kiện động đều nên loại bỏ.

## 6. Ví dụ Java 17+ có thể chạy: pointcut chính xác và test phủ định

Đây là ví dụ **weaving bằng AspectJ độc lập**, sử dụng Java 17. Nó thể hiện rằng lời gọi nghiệp vụ được audit còn phương thức truy vấn trạng thái không bị ảnh hưởng. Cần công cụ `ajc` và runtime thư viện AspectJ cùng phiên bản. Cú pháp `.aj` được biên dịch bởi AspectJ compiler, **không phải bởi `javac` thuần**.

### 6.1. Tạo mã nguồn

Cấu trúc:

```text
pointcut-example/
└── src/
    └── demo/
        └── orders/
            ├── OrderService.java
            ├── Main.java
            └── OrderAudit.aj
```

`src/demo/orders/OrderService.java`:

```java
package demo.orders;

public final class OrderService {
    public void place(String id) {
        System.out.println("PLACED: " + id);
    }

    public String status() {
        return "READY";
    }
}
```

`src/demo/orders/Main.java`:

```java
package demo.orders;

public final class Main {
    public static void main(String[] args) {
        OrderService service = new OrderService();
        service.place("A-17");
        System.out.println("STATUS: " + service.status());
    }
}
```

`src/demo/orders/OrderAudit.aj`:

```java
package demo.orders;

public aspect OrderAudit {
    pointcut confirmedOrder():
        execution(public void demo.orders.OrderService.place(java.lang.String));

    before(): confirmedOrder() {
        System.out.println("AUDIT: placing order");
    }
}
```

`confirmedOrder` là named pointcut, tách định nghĩa phạm vi khỏi advice. `execution` nhắm vào việc **thực thi** `place(String)`, vì vậy lời gọi `status()` không thuộc phạm vi. Ví dụ không đòi hỏi thay đổi method Java để gọi aspect một cách thủ công.

### 6.2. Biên dịch, weave và thực thi

Giả sử chạy từ thư mục `pointcut-example`, có JDK 17 và đã lấy hai JAR cùng phiên bản, ví dụ AspectJ 1.9.24:

```text
tools/aspectjtools-1.9.24.jar
tools/aspectjrt-1.9.24.jar
```

Chạy trên POSIX shell (Linux/macOS); dấu `:` trong classpath đổi thành `;` trên Windows:

```bash
mkdir -p build/woven

java -cp tools/aspectjtools-1.9.24.jar \
  org.aspectj.tools.ajc.Main \
  -17 -encoding UTF-8 \
  -classpath tools/aspectjrt-1.9.24.jar \
  -showWeaveInfo \
  -d build/woven \
  src/demo/orders/OrderService.java \
  src/demo/orders/Main.java \
  src/demo/orders/OrderAudit.aj

java -cp "build/woven:tools/aspectjrt-1.9.24.jar" \
  demo.orders.Main
```

Các dòng stdout của chương trình (không tính thông báo compiler/weaver in khi build):

```text
AUDIT: placing order
PLACED: A-17
STATUS: READY
```

Điều có thể quan sát:

- Advice xuất hiện **một lần** trước `place`.
- Business method vẫn tạo kết quả `PLACED: A-17`.
- `status()` trả `READY` và **không có thêm dòng audit**.
- Biểu thức pointcut hẹp đã chọn đúng **một kiểu execution join point** được minh họa.

Việc test output không chứng minh mọi biến thể của chương trình đều đúng; nó là kiểm thử tối thiểu cho một cặp **positive/negative**. Cần kiểm tra trực tiếp weave report và chạy bài test với chính artifact đóng gói sẽ triển khai.

### 6.3. Thay bằng pointcut quá rộng thì điều gì đổi?

Chỉ để minh họa hậu quả, nếu đổi nội dung `confirmedOrder()` thành:

```java
pointcut confirmedOrder():
    execution(* demo.orders..*.*(..));
```

Thì pointcut nhắm gần như toàn bộ method execution của các type trong package này, bao gồm `status` và `main`, tùy weaving scope/cơ chế. Thứ tự/số dòng audit sẽ không còn tương đương output của phiên bản hẹp. Nếu sau này thêm `OrderService.healthCheck`, pointcut rộng cũng có thể áp dụng cho nó mà không cần sửa aspect. **Đây là một thay đổi hợp đồng quan sát đáng kể**, không phải chỉ đổi cách viết regex.

Không nên dựa vào một output cố định cho biến thể quá rộng vì woven join point còn phụ thuộc các method/constructor/compiler-generated artifact và cấu hình; nên quan sát weave report thực tế của phiên bản đang chạy.

### 6.4. Kiểm thử positive và negative một cách cơ học

Với phiên bản pointcut hẹp, có thể tạo một test shell tối giản:

```bash
actual=$(java -cp "build/woven:tools/aspectjrt-1.9.24.jar" \
  demo.orders.Main)
expected=$(printf 'AUDIT: placing order\nPLACED: A-17\nSTATUS: READY')
test "$actual" = "$expected"
```

Nếu advice mất hiệu lực sau refactor, dòng `AUDIT` biến mất và test fail. Nếu advice khớp thừa `status()` hoặc `Main.main`, dòng audit bổ sung cũng làm test fail. Tại CI, nên thực hiện clean output và dùng assertion rõ ràng trên side effect thay vì chỉ kiểm tra stdout nếu chương trình thực có concurrency/async logging.

## 7. Annotation như một hợp đồng ngữ nghĩa

Khi nhiều phương thức mang cùng một ý nghĩa xuyên suốt, dùng một marker nhất quán có thể giảm coupling vào tên lớp, package và phương thức. Ví dụ sau là **minh họa cách thiết kế**; cần đặt nó trong cấu hình AspectJ hoàn chỉnh và kiểm thử lại nếu tích hợp thực.

Khai báo `demo.audit.AuditedOperation`:

```java
package demo.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface AuditedOperation {
}
```

Gắn marker có chủ đích vào phương thức cập nhật nghiệp vụ:

```java
@AuditedOperation
public void place(String id) {
    // Business code.
}
```

Trong aspect kiểu AspectJ:

```java
pointcut auditedOperation():
    execution(public * demo.orders..*.*(..))
    && @annotation(demo.audit.AuditedOperation);
```

Ý nghĩa: giới hạn phạm vi tới public method execution trong khu vực nghiệp vụ đã xác định **và** có annotation audit. Khi đổi `place` thành `submit` hoặc đổi kiểu tham số, marker vẫn thể hiện ý định cần audit nếu được giữ đúng tại phương thức mới.

**Không phải annotation là thuốc chữa mọi tình huống:**

- Nếu developer quên gắn marker cho phương thức mới, advice vẫn bị bỏ sót.
- Nếu marker được copy sang helper hoặc getter khi refactor, advice có thể khớp thừa.
- Nếu marker đặt trên interface method nhưng weaving kiểm tra method implementation, việc match có thể khác với kỳ vọng. Cần test cụ thể; không mặc định method annotation tự động được kế thừa.
- `@Inherited` trong Java áp dụng cho annotation trên class, không khiến method annotation tự động “thừa kế” theo overriding.
- Retention policy, module visibility và công cụ weaving có thể ảnh hưởng cách kiểm tra annotation. Không mặc định annotation có retention `SOURCE` luôn hiện diện cho mọi trường hợp binary/runtime weaving.

Phương án bền vững là **đặt marker ở ranh giới chính sách được review**, test các triển khai quan trọng, và dùng static analysis/conventions để phát hiện quên marker khi cần.

## 8. Các cặp lựa chọn pointcut dễ nhầm

### 8.1. `call` khác `execution`

```java
// Hai loại join point khác nhau, chỉ dùng nếu weaver hỗ trợ:
call(* demo.orders.OrderService.place(..))
execution(* demo.orders.OrderService.place(..))
```

- `call` chọn điểm **gọi** method từ caller (nếu loại join point đó được hỗ trợ và caller nằm trong phạm vi weaving).
- `execution` chọn **thực thi** thân method target (nếu target được weave).
- Một call site mới, wrapper hoặc caller không được weave có thể ảnh hưởng `call` khác với `execution`.
- Nếu AOP dựa trên proxy, tập join point thực tế có thể chỉ gồm lời gọi đi qua proxy. Không chuyển kết luận của bytecode weaving sang proxy một cách máy móc.

Nếu mục tiêu là “mọi lần chạy thao tác đặt hàng”, execution-level thường bám sát ý định hơn; nếu cần “mọi lời gọi đi ra từ tầng X sang tầng Y”, call-level có thể phản ánh boundary khác. Phải chọn theo **sự kiện cần theo dõi**, không chỉ cú pháp dễ viết.

### 8.2. `within` khác `withincode`

- `within(TypePattern)` giới hạn join point thuộc vùng kiểu/class phù hợp.
- `withincode(SignaturePattern)` giới hạn join point theo lexical code nơi chúng xuất hiện, tùy loại join point.
- Một điều kiện lexical có thể thay đổi khi chuyển câu lệnh sang helper, cho dù nghiệp vụ vẫn như cũ.

Dùng điều kiện lexical khi chính **vị trí code** là một phần của hợp đồng, không thay cho marker nghiệp vụ có ngữ nghĩa ổn định.

### 8.3. `this` và `target`

Trong mô hình pointcut hỗ trợ hai designator này, `this` nói về đối tượng thực thi join point theo ngữ cảnh, còn `target` nói về đối tượng đích của join point; giá trị cụ thể và ý nghĩa đối với các loại join point phải đọc theo ngữ nghĩa của công cụ. Với proxy-based interception, proxy object và target có thể khác nhau. Dùng nhầm có thể khiến pointcut chỉ khớp một implementation hoặc sai kiểu runtime.

Không thể khái quát “`this` luôn là caller” hay “`target` luôn là proxy” cho mọi kiểu join point.

### 8.4. `args` khác kiểm tra kiểu trong chữ ký

Một signature pattern có thể chọn theo kiểu tham số được **khai báo**; `args(...)` thường liên quan đến đối tượng/tham số có mặt tại runtime và có thể binding giá trị. Overload, subtype hoặc đối tượng `null` có thể dẫn tới hành vi match khác với trực giác. Khi dùng các điều kiện đó để kiểm soát an toàn hoặc giao dịch, hãy đưa các kiểu cạnh biên vào test.

## 9. Rủi ro cụ thể khi pointcut quá rộng trong advice quan trọng

### 9.1. Logging, audit và observability

Một advice log mọi tham số trên `execution(* *(..))` có thể vô tình đọc password, token, dữ liệu cá nhân hoặc payload lớn. Vấn đề không chỉ là throughput mà còn là **phạm vi dữ liệu được phép quan sát**. Thực hiện allowlist join point và field, loại bỏ hoặc che dữ liệu nhạy cảm, kiểm tra output trên cả success và exception. Khi sửa tên hoặc di chuyển lớp, phải kiểm tra lại allowlist và exclusion.

### 9.2. Authorization

Nếu quyền truy cập phụ thuộc một pointcut theo tên phương thức như `*Admin*`, việc refactor tên có thể làm biến mất việc kiểm tra dù endpoint/hành vi vẫn nhạy cảm. Chính sách an toàn không nên chỉ trông chờ vào một mẫu tên không được test. Cần kiểm thử trường hợp bị từ chối và được cho phép, đồng thời bảo đảm mọi entry point được bảo vệ. Đừng coi một advice chạy ở “ít nhất một test” là chứng cứ mọi đường vào đều an toàn.

### 9.3. Transaction và resource cleanup

Advice quản lý transaction hoặc resource có thể phá vỡ ranh giới vòng đời nếu match helper và method con, tạo transaction lồng nhau hay đóng resource không đúng thời điểm. Với around advice, việc gọi `proceed` sai số lần hoặc nuốt ngoại lệ có thể làm thay đổi ý nghĩa nghiệp vụ. Xác định rõ boundary mà advice phải sở hữu và kiểm tra nested calls, exception path và retry.

### 9.4. Metric/tracing

Một yêu cầu nghiệp vụ gọi nhiều method nhỏ. Nếu pointcut quá rộng, hệ thống tạo vô số span hoặc metric label, làm tăng chi phí, độ trễ và cardinality. Pointcut theo naming convention rộng còn mở rộng theo code mới mà không có kiểm soát. Ưu tiên điểm có ý nghĩa quan sát, tách trace cấp giao dịch khỏi metric chi tiết nếu cần.

## 10. Quản lý pointcut khi refactor

Pointcut phải nằm trong phạm vi review như một **public behavioral contract** của hệ thống, dù không xuất hiện trong method signature thông thường.

### 10.1. Trước refactor

1. Liệt kê concern bị ảnh hưởng: audit, tracing, cache, kiểm tra quyền, transaction...
2. Xác định named pointcut và danh sách join point hiện được weave/intercept.
3. Chốt các **must match** (bắt buộc khớp) và **must not match** (bắt buộc không khớp).
4. Kiểm tra điểm yếu: name pattern, package, overload, visibility, annotation placement, call/execution semantics, target loader.
5. Nếu đổi method signature/di chuyển lớp, lập bảng mapping join point cũ sang join point mới theo **ý nghĩa nghiệp vụ**.

### 10.2. Trong refactor

- Khi đổi tên package hoặc phương thức, tìm pointcut có thể tham chiếu đến cấu trúc cũ; IDE rename không nhất thiết cập nhật mọi chuỗi pattern.
- Nếu aspect chứa wildcard, chạy lại báo cáo weaving: wildcard có thể match thêm code vừa được chuyển vào scope.
- Khi tách method nghiệp vụ thành nhiều helper, quyết định advice thuộc boundary ngoài hay toàn bộ helper; đừng để cơ chế match tự quyết.
- Nếu dùng marker, kiểm tra marker được giữ ở **method thực thi đúng ý định**, không chỉ copy trên interface.
- Nếu thay đổi call path hoặc chuyển từ lời gọi trực tiếp sang proxy/adapter, kiểm tra lại loại join point mà cơ chế AOP hỗ trợ.

### 10.3. Sau refactor

Chạy lại kiểm thử trên **artifact đã weave/đã cấu hình interception**. So sánh tập join point trước/sau và giải thích phần chênh lệch. Không chỉ so sánh số lượng tổng vì một join point mất và một join point thừa có thể làm tổng số không đổi.

Nếu dùng AspectJ, công cụ `ajc` có thể in thông tin weaving qua `-showWeaveInfo`. Log giúp rà soát nhưng định dạng có thể đổi giữa phiên bản; kết hợp với test hành vi. Các công cụ AOP khác có thể có cách báo join point riêng.

## 11. Kiểm thử pointcut: bảng quyết định rõ ràng

Giả sử mục tiêu là audit các thao tác đặt hàng thật sự:

| Trường hợp | Mong đợi | Lý do |
|---|---|---|
| `OrderService.place("A-17")` | **MATCH** | Thao tác cần audit |
| `OrderService.status()` | **NO MATCH** | Truy vấn chỉ đọc |
| `OrderService.place(...)` sau đổi tham số | **MATCH** nếu cùng ngữ nghĩa | Không được mất audit vì thay DTO |
| `CheckoutWorkflow.submit(...)` sau chuyển nghiệp vụ | **MATCH** khi đây là entry point mới | Boundary được thay thế |
| Helper `OrderFormatter.format(...)` | **NO MATCH** | Không phải hành vi audit |
| Method mới `OrderService.preview(...)` | **NO MATCH** nếu chỉ xem trước | Tránh wildcard khớp thêm |
| Method audit tự gọi đến logger/helper | **NO MATCH** đối với chính hạ tầng advice | Tránh recursion và log storm |
| Thao tác cập nhật qua nhiều thread/loader | **MATCH** theo hợp đồng ở môi trường đích | Không bỏ sót vì môi trường chạy |

### 11.1. Kiểm thử ba tầng

**(A) Kiểm tra khai báo:** pointcut thể hiện rõ tập join point dự kiến; tài liệu mô tả scope và exclusion. Có thể lint phát hiện mẫu đặc biệt rộng (ví dụ `execution(* *(..))`) mà không có giới hạn bổ sung.

**(B) Kiểm tra weaving/cấu hình:** xác nhận class/method được chọn đúng qua weave report hoặc introspection của hệ thống AOP. Tập join point thay đổi phải được reviewer nhìn thấy.

**(C) Kiểm tra hành vi runtime:** chạy các case dương/âm và xác minh side effect, giá trị trả về, exception, thứ tự, số lần advice, cùng phần code **không** bị chặn.

Không có tầng nào thay thế hoàn toàn hai tầng còn lại. Một biểu thức “trông đúng” vẫn có thể không được áp dụng lên lớp runtime vì class loader, weaving scope, phiên bản artifact hoặc cơ chế proxy.

### 11.2. Kiểm thử biến đổi có chủ đích (mutation test)

Để kiểm tra sức mạnh của test, thử một số sửa đổi có kiểm soát trong branch phát triển:

- Đổi tên class/method được audit nhưng giữ ý nghĩa nghiệp vụ.
- Thêm method `preview` hoặc `healthCheck` cùng package.
- Tạm bỏ marker annotation khỏi một thao tác cần audit.
- Dời method qua helper, thêm overload hoặc thay kiểu DTO.

Nếu test vẫn pass khi advice mất khỏi điểm bắt buộc, bộ test chưa đủ mạnh. Khi kiểm thử matcher, đừng tạo một “test” chỉ kiểm tra cùng một chuỗi pattern được copy từ implementation; cần kiểm tra **hành vi có ý nghĩa**.

## 12. Hiệu năng, khả năng bảo trì và lựa chọn chiến lược

| Chiến lược | Lợi thế | Đánh đổi |
|---|---|---|
| Chữ ký tường minh | Dễ dự đoán phạm vi hiện tại, ít match thừa | Giòn khi refactor method/class; nhiều khai báo |
| Package/type boundary | Dễ tổ chức theo khu vực code | Package không nhất thiết mang nghĩa nghiệp vụ |
| Annotation marker | Biểu đạt policy rõ, ổn định trước nhiều lần rename | Cần gắn marker đúng, kiểm tra retention/placement |
| Interface/capability | Bám hợp đồng phân lớp/công bố | Có thể khác khi execution nằm ở implementation hay proxy |
| Named pointcut tổ hợp | Tái sử dụng, dễ review và mở rộng có kiểm soát | Biểu thức phức tạp, cần test cả inclusion/exclusion |
| Điều kiện runtime | Cho phép quyết định theo ngữ cảnh dữ liệu | Tăng chi phí và độ khó dự đoán; dễ có logic ẩn trong advice |

Không có lựa chọn tốt nhất cho mọi hệ thống. Độ ổn định cần được đánh giá bằng câu hỏi: **“Nếu code được refactor nhưng ý nghĩa nghiệp vụ không đổi, pointcut có còn chọn đúng tập hành vi không?”**

## 13. Các lỗi phổ biến và cách khắc phục

**Lỗi 1 — Chọn toàn bộ ứng dụng để “không bỏ sót”.** Kết quả là advice chạy ở getter/helper, tạo quá nhiều log/span và có thể chạm dữ liệu nhạy cảm. *Khắc phục:* định nghĩa positive scope và negative scope, thêm case không được khớp.

**Lỗi 2 — Tin wildcard tự diễn đạt nghiệp vụ.** `save*(..)` không có nghĩa “mọi thao tác ghi bền vững”; một method `savePreview` có thể chỉ tạo bản nháp. *Khắc phục:* xác định marker/capability hoặc chữ ký ổn định và có review.

**Lỗi 3 — Gắn pointcut vào package dễ thay đổi.** Refactor thư mục làm biến mất advice mà build vẫn thành công. *Khắc phục:* thêm test bảo vệ semantics và kiểm tra weave report trước/sau đổi package.

**Lỗi 4 — Chỉ test case được khớp.** Pointcut match quá rộng mà test vẫn pass. *Khắc phục:* kiểm thử must-not-match, đặc biệt khi thêm method/package mới.

**Lỗi 5 — Giả định annotation luôn được kế thừa.** Method marker trên interface/base class không nhất thiết được nhìn thấy ở method implementation/override trong mọi cơ chế AOP. *Khắc phục:* định nghĩa chính sách placement và kiểm thử binary/runtime concrete class.

**Lỗi 6 — Nhầm loại join point.** `call` khác `execution`; proxy interception không tương đương weaving tất cả call site. *Khắc phục:* mô tả sự kiện cần bắt và kiểm tra class loader/weaving boundary.

**Lỗi 7 — Advice tự kích hoạt lại.** Broad pointcut bao gồm helper của advice, gây recursion hay logging storm. *Khắc phục:* tách infrastructure scope, loại trừ rõ ràng, test đường gây tái nhập.

**Lỗi 8 — Giữ blacklist exclusion ngày càng dài.** Mỗi class mới sinh thêm `!within(...)` và khó hiểu. *Khắc phục:* thiết kế allowlist dựa trên ranh giới nghiệp vụ.

**Lỗi 9 — Lấy thành công compiler làm tiêu chí duy nhất.** Compiler hợp lệ không đồng nghĩa join point yêu cầu đã được weave. *Khắc phục:* kiểm tra match thực và chạy integration test trên artifact cuối.

**Lỗi 10 — Bỏ qua tải thật.** Advice được đặt lên method nóng mà chỉ test chức năng. *Khắc phục:* đo invocation count, allocation, CPU, tail latency ở đường có AOP bật; sửa scope trước khi micro-optimize.

## 14. Checklist review pointcut trước khi đưa vào production

- [ ] Pointcut có tên và mô tả **hành vi cần chọn**, không chỉ cấu trúc mã.
- [ ] Đã liệt kê ít nhất một **must match** và một **must not match** đại diện.
- [ ] Wildcard được giới hạn bằng package/type/marker khi có thể; không vô tình quét hạ tầng advice hoặc dependency.
- [ ] Có lý do rõ nếu phụ thuộc class name, method name, signature hay package; refactor tương ứng đã được test.
- [ ] Hiểu đúng loại join point (**call, execution, field, constructor...**) và giới hạn của cơ chế AOP đang dùng.
- [ ] Không giả định annotation tự kế thừa hoặc proxy chặn mọi lời gọi nội bộ.
- [ ] Đã kiểm tra trường hợp overload, visibility, exception, đường gọi lồng nhau và concurrency nếu liên quan.
- [ ] Có test bắt được lời gọi bị bỏ sót **và** bị match thừa; không chỉ test rằng “có một advice đã chạy”.
- [ ] Weave/interception thực sự được kích hoạt trên artifact và JVM sẽ triển khai.
- [ ] Đã đánh giá chi phí với invocation count thực tế và rủi ro dữ liệu nhạy cảm trong advice.
- [ ] Khi refactor, diff tập join point trước/sau được xem xét theo nghiệp vụ, kể cả nếu tổng số match không đổi.

## 15. Kết luận thực hành

Một pointcut tốt chọn **đúng hành vi theo một hợp đồng rõ ràng**. Pointcut quá rộng làm advice lan sang mã không thuộc policy; pointcut quá phụ thuộc tên và vị trí làm policy biến mất khi refactor. Cách sửa hiệu quả là xác định ranh giới nghiệp vụ trước, chọn điều kiện tĩnh/marker/capability phù hợp, kiểm thử cả **match và no-match**, và kiểm tra weaving trên artifact thực tế. Khi code được tái cấu trúc nhưng ý nghĩa không đổi, điều cần được giữ ổn định là **tập hành vi chịu advice**, không phải chuỗi ký tự của phương thức cũ.