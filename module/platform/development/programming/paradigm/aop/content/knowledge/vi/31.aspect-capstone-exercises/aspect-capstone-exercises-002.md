# Bài tập tổng hợp: Thiết kế aspect ghi nhật ký với phạm vi chọn và loại trừ rõ ràng

## 1. Mục tiêu bài tập

Bài tập này yêu cầu xây dựng một **logging aspect** trong lập trình hướng khía cạnh (*Aspect-Oriented Programming – AOP*) với chính sách chọn join point có chủ đích. Kết quả không chỉ phải ghi log cho những phương thức được phép, mà còn phải **chứng minh những phương thức bị loại trừ không sinh log**.

Sau khi hoàn thành, người học cần:

1. Phân biệt **join point**, **pointcut**, **advice**, **weaving** và lời gọi bình thường của chương trình.
2. Thiết kế pointcut có **phạm vi dương (inclusion)** và **phạm vi âm (exclusion)**, với lý do cho từng điều kiện.
3. Tránh cách viết wildcard quá rộng như `execution(* *(..))` và tránh lệ thuộc hoàn toàn vào tên phương thức thay đổi theo refactor.
4. Dùng metadata có chủ đích để biểu thị phương thức được phép ghi log; vẫn có cơ chế **từ chối ghi log rõ ràng** ngay cả khi đã được đánh dấu.
5. Giữ đúng giá trị trả về, ngoại lệ và luồng nghiệp vụ; không để advice tự kích hoạt vô hạn.
6. Viết kiểm thử có cả **must-match** và **must-not-match**, xem weave report và chạy đúng artifact đã dệt.
7. Giải thích được chi phí hiệu năng, quy tắc không ghi dữ liệu nhạy cảm và giới hạn của cơ chế AOP đã chọn.

Ví dụ thực hành dùng **Java 17+ với AspectJ compiler/weaver độc lập** làm một hiện thực của AOP ở mức bytecode. Điều kiện pointcut và tập join point hỗ trợ có thể khác ở các cơ chế AOP khác; bài không giả định mọi bộ proxy/interceptor đều có khả năng chọn method execution như bytecode weaving.

## 2. Đề bài thực tế

Giả sử một ứng dụng quản lý đơn hàng có ba loại thao tác:

- **Thao tác nghiệp vụ được kiểm toán:** xác nhận đơn, tác vụ có thể thất bại. Cần log lúc bắt đầu, khi thành công và khi có ngoại lệ.
- **Thao tác bình thường hoặc được miễn trừ:** xem trước đơn, xử lý bảo trì không muốn ghi log. Chúng không được tạo dòng audit dù nằm cùng lớp nghiệp vụ.
- **Thao tác kỹ thuật nội bộ:** phương thức ở package nội bộ có thể mang marker ghi log, nhưng toàn bộ package đó thuộc vùng loại trừ.

Thiết kế aspect mang tên `AuditAspect`. Thay vì ghi log toàn bộ package, bài tập dùng **hai marker annotation** và một điều kiện package exclusion.

**Quy tắc chọn:** một method execution chỉ được ghi log nếu **đồng thời**:

1. Là phương thức `public` của kiểu thuộc `demo.shop.service` hoặc package con.
2. Mang annotation `@Logged`.
3. **Không** mang annotation `@NoLog`.
4. **Không** thuộc package `demo.shop.service.internal` hoặc các package con.

Những điểm này là một phép giao: nếu một điều kiện không thỏa, advice không được chạy. Để tránh quan niệm sai, marker `@Logged` là ý định ghi log do lập trình viên công bố, **không phải** cơ chế weaving tự động; chỉ pointcut + trình weave mới nối marker với advice.

**Quy tắc ghi log:** tại mỗi execution join point được chọn, ghi một dòng `AUDIT START: <method>` trước khi chạy. Nếu method hoàn tất bình thường, ghi `AUDIT OK: <method>`; nếu thoát bằng ngoại lệ, ghi `AUDIT ERROR: <method> - <exception-class>`. Không ghi giá trị tham số, kết quả, stack trace hoặc dữ liệu nhạy cảm trong ví dụ.

**Quy tắc nghiệp vụ:** mã nghiệp vụ vẫn thực thi đúng một lần. Result không bị thay đổi; ngoại lệ không bị nuốt hoặc chuyển thành trạng thái thành công. Advice chỉ thực hiện ghi log minh họa vào stdout.

### 2.1. Ma trận chấp nhận

| Join point | @Logged | @NoLog | Vị trí | Mong đợi |
|---|---:|---:|---|---|
| `OrderService.submit(String)` | Có | Không | `service` | **Có log START + OK** |
| `OrderService.preview(String)` | Không | Không | `service` | **Không log** |
| `OrderService.maintenance(String)` | Có | Có | `service` | **Không log** vì marker loại trừ |
| `InternalJobs.ping()` | Có | Không | `service.internal` | **Không log** vì package loại trừ |
| `OrderService.fail()` | Có | Không | `service` | **Có log START + ERROR**, giữ ngoại lệ |
| Mọi method khác không thỏa đủ điều kiện | Bất kỳ | Bất kỳ | Bất kỳ | **Không log** |

Đây là tiêu chí nghiệm thu. Một lời giải chỉ in được log ở `submit` nhưng vẫn in thêm ở `preview` thì **chưa đạt**.

## 3. Phân tích trước khi viết mã

### 3.1. Vì sao phải tách positive scope và exclusions?

Một biểu thức kiểu `execution(public * demo.shop.service..*.*(..))` có thể chọn quá nhiều phương thức chỉ vì chúng được đặt trong cùng package. Một biểu thức kiểu `execution(* *.submit(..))` có thể ngừng hoạt động sau khi đổi tên `submit` thành `confirm`. Kết hợp **phạm vi loại/type** với **annotation mang ý nghĩa audit** làm điều kiện chính sẽ rõ ràng hơn.

Ngược lại, chỉ dùng `@Logged` cũng chưa đủ: một marker có thể bị copy vào helper hoặc một lớp nội bộ mới. Điều kiện `!within(demo.shop.service.internal..*)` bảo vệ rõ ràng ranh giới kỹ thuật. `@NoLog` cung cấp một ngoại lệ có thể review tại chính nơi khai báo phương thức.

Với bài này, precedence về ý nghĩa là **quy tắc kết hợp bằng AND và phủ định**: `@NoLog` luôn khiến method không match, kể cả khi có `@Logged`.

### 3.2. Vì sao dùng method execution?

Mục tiêu là ghi log mỗi lần **thân phương thức nghiệp vụ thực sự được thực thi**. Pointcut `execution(...)` trong AspectJ phù hợp với mục tiêu đó: weave advice tại method execution join point. `call(...)` chọn điểm gọi và có đặc tính khác khi mã gọi nằm ngoài phạm vi weaving. Một interception qua proxy còn phụ thuộc việc lời gọi có đi qua proxy hay không. Khi chuyển cơ chế AOP, phải xác minh lại semantics thay vì sao chép pointcut theo tên.

### 3.3. Logging aspect phải làm việc gì?

- Lấy thông tin tên phương thức qua join point metadata, **không** serialize toàn bộ `args`.
- Ghi rõ START/OK/ERROR và giữ đúng thứ tự bao quanh nghiệp vụ.
- Đảm bảo code logging tự nó không nằm trong tập method được chọn. Trong bài này, aspect ở package `demo.shop.aspect`, nằm ngoài positive scope `demo.shop.service..*`.
- Không gọi lại phương thức target từ advice. Nếu cần `around advice`, phải hiểu rõ số lần `proceed()`; với yêu cầu hiện tại, advice before/after là đủ.

## 4. Bộ mã nguồn Java 17+ có thể chạy

Làm bài độc lập trong thư mục `aop-logging-lab`. Sử dụng cấu trúc:

```text
aop-logging-lab/
├── src/
│   └── demo/
│       └── shop/
│           ├── Main.java
│           ├── audit/
│           │   ├── Logged.java
│           │   └── NoLog.java
│           ├── aspect/
│           │   └── AuditAspect.aj
│           └── service/
│               ├── OrderService.java
│               └── internal/
│                   └── InternalJobs.java
└── tools/
    ├── aspectjtools-1.9.24.jar
    └── aspectjrt-1.9.24.jar
```

Các đoạn `.java` là mã Java hợp lệ; `AuditAspect.aj` là cú pháp aspect của AspectJ và phải được biên dịch bằng **`ajc`**, không bằng `javac` thuần. Các bản JAR ví dụ dùng cùng phiên bản **AspectJ 1.9.24**; xác nhận toolchain phù hợp với môi trường Java trước khi dùng vào một dự án thật.

### 4.1. Marker cho phương thức phải được ghi log

Tạo `src/demo/shop/audit/Logged.java`:

```java
package demo.shop.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Logged {
}
```

Marker này nói rằng một method *có thể* được audit, tùy thêm các giới hạn pointcut. `RetentionPolicy.RUNTIME` giữ annotation trong metadata runtime; một số hình thức weaving có thể xử lý annotation ở thời điểm compile và có yêu cầu riêng, nhưng dùng retention rõ ràng tránh nhầm rằng mọi annotation đều tồn tại lúc chạy.

### 4.2. Marker loại trừ có chủ đích

Tạo `src/demo/shop/audit/NoLog.java`:

```java
package demo.shop.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface NoLog {
}
```

Method có đồng thời `@Logged` và `@NoLog` phải **bị loại** khỏi logging. Không suy ra mọi annotation trên method tự động được kế thừa khi override; code production phải kiểm tra vị trí annotation và ngữ nghĩa matcher trên implementation cụ thể.

### 4.3. Lớp nghiệp vụ và bốn hành vi đối chứng

Tạo `src/demo/shop/service/OrderService.java`:

```java
package demo.shop.service;

import demo.shop.audit.Logged;
import demo.shop.audit.NoLog;

public final class OrderService {
    @Logged
    public String submit(String id) {
        return "SUBMITTED:" + id;
    }

    public String preview(String id) {
        return "PREVIEW:" + id;
    }

    @Logged
    @NoLog
    public String maintenance(String id) {
        return "MAINTENANCE:" + id;
    }

    @Logged
    public void fail() {
        throw new IllegalStateException("rejected");
    }
}
```

Quan sát:

- `submit` và `fail` thỏa điều kiện chọn.
- `preview` không có marker nên không chọn.
- `maintenance` cố tình mang **cả hai marker** để buộc kiểm tra exclusion thực tế. Trong sản phẩm thật, hãy cân nhắc vì sao exception được phép thay vì vô tình sao chép annotation.

### 4.4. Package nội bộ có marker nhưng không được log

Tạo `src/demo/shop/service/internal/InternalJobs.java`:

```java
package demo.shop.service.internal;

import demo.shop.audit.Logged;

public final class InternalJobs {
    @Logged
    public String ping() {
        return "PONG";
    }
}
```

`ping` mang `@Logged` và nằm bên dưới `demo.shop.service`. Nếu chỉ dựa vào positive scope và annotation, method sẽ match. Điều kiện `!within(demo.shop.service.internal..*)` phải loại chính method này.

### 4.5. Aspect chứa điều kiện chọn và loại trừ

Tạo `src/demo/shop/aspect/AuditAspect.aj`:

```java
package demo.shop.aspect;

public aspect AuditAspect {
    pointcut selectedServiceMethod():
        execution(public * demo.shop.service..*.*(..))
        && @annotation(demo.shop.audit.Logged)
        && !@annotation(demo.shop.audit.NoLog)
        && !within(demo.shop.service.internal..*);

    before(): selectedServiceMethod() {
        System.out.println(
            "AUDIT START: " + thisJoinPointStaticPart.getSignature().getName());
    }

    after() returning: selectedServiceMethod() {
        System.out.println(
            "AUDIT OK: " + thisJoinPointStaticPart.getSignature().getName());
    }

    after() throwing(Throwable error): selectedServiceMethod() {
        System.out.println(
            "AUDIT ERROR: " + thisJoinPointStaticPart.getSignature().getName()
            + " - " + error.getClass().getSimpleName());
    }
}
```

**Giải nghĩa từng nhánh:**

| Điều kiện | Ý nghĩa | Nếu bỏ điều kiện |
|---|---|---|
| `execution(public * demo.shop.service..*.*(..))` | Chỉ public method execution của các kiểu trong namespace nghiệp vụ | Có nguy cơ chặn method ngoài ranh giới này |
| `@annotation(demo.shop.audit.Logged)` | Method phải được đánh dấu có chủ đích | `preview` và các method public khác trong namespace cũng có thể bị ghi log |
| `!@annotation(demo.shop.audit.NoLog)` | Marker từ chối có ưu tiên loại trừ | `maintenance` có thể bị ghi log |
| `!within(demo.shop.service.internal..*)` | Loại toàn bộ mã nằm trong package nội bộ và cấp con | `InternalJobs.ping` sẽ bị ghi log |

`&&` là phép giao và `!` là phủ định pointcut. Trong cú pháp AspectJ này, `..` ở type pattern cho phép xét các package con; cần kiểm tra điểm khớp thực bằng weave report. Cách dùng `within` ở đây chỉ có ý nghĩa với method execution thuộc lexical type phù hợp, không có nghĩa nó tự động áp dụng chính sách cho mọi class loader hoặc công cụ AOP khác.

**Vì sao ba advice?** `before` chạy trước thân method; `after() returning` chỉ chạy khi thoát bình thường; `after() throwing` chạy khi method thoát bởi ngoại lệ phù hợp. Như vậy không cần `around` chỉ để ghi log, đồng thời giữ nguyên luồng trả về/ngoại lệ mà không phải tự gọi `proceed`.

Với ví dụ đơn luồng và in stdout trực tiếp, thứ tự log là xác định. Trong ứng dụng nhiều luồng, log giữa các request có thể xen nhau; test không nên suy luận tính đúng chỉ dựa vào thứ tự dòng log toàn hệ thống.

### 4.6. Entry point để quan sát kết quả

Tạo `src/demo/shop/Main.java`:

```java
package demo.shop;

import demo.shop.service.OrderService;
import demo.shop.service.internal.InternalJobs;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        OrderService orders = new OrderService();
        InternalJobs internal = new InternalJobs();

        System.out.println(orders.submit("A-17"));
        System.out.println(orders.preview("A-17"));
        System.out.println(orders.maintenance("M-1"));
        System.out.println(internal.ping());

        try {
            orders.fail();
        } catch (IllegalStateException exception) {
            System.out.println("CAUGHT:" + exception.getMessage());
        }
    }
}
```

Code này không gọi `AuditAspect` bằng tay. Khi class đã được weave đúng, các method `submit` và `fail` tự kích hoạt advice tại execution join point.

## 5. Biên dịch và weave từ mã nguồn

Cần có JDK 17+ và hai JAR AspectJ cùng phiên bản. Ví dụ lệnh bên dưới dùng **POSIX shell** (Linux/macOS/Git Bash phù hợp). Lấy compiler và runtime từ Maven Central:

```bash
mkdir -p tools build/woven

curl -fLsS \
  https://repo.maven.apache.org/maven2/org/aspectj/aspectjtools/1.9.24/aspectjtools-1.9.24.jar \
  -o tools/aspectjtools-1.9.24.jar

curl -fLsS \
  https://repo.maven.apache.org/maven2/org/aspectj/aspectjrt/1.9.24/aspectjrt-1.9.24.jar \
  -o tools/aspectjrt-1.9.24.jar
```

Tiếp theo chạy AspectJ compiler với target Java 17. Bắt đầu từ output **sạch**, ví dụ xóa riêng `build/woven` của lab trước lần chạy mới khi chắc chắn không có dữ liệu cần giữ. Lệnh sau giả định `build/woven` chưa chứa class từ lần build cũ:

```bash
java -cp tools/aspectjtools-1.9.24.jar \
  org.aspectj.tools.ajc.Main \
  -17 -encoding UTF-8 \
  -classpath tools/aspectjrt-1.9.24.jar \
  -showWeaveInfo \
  -d build/woven \
  src/demo/shop/audit/Logged.java \
  src/demo/shop/audit/NoLog.java \
  src/demo/shop/service/OrderService.java \
  src/demo/shop/service/internal/InternalJobs.java \
  src/demo/shop/Main.java \
  src/demo/shop/aspect/AuditAspect.aj
```

Các điểm phải kiểm chứng:

1. Exit code của compiler bằng `0`; không có lỗi syntax/classpath.
2. `-showWeaveInfo` báo advice được dệt vào join point của `submit` và `fail`.
3. Không có advice khớp `preview`, `maintenance`, `InternalJobs.ping`.
4. Các classfile đầu ra thực sự nằm trong `build/woven`; quá trình chạy phải lấy từ đây.
5. Compiler version và target JDK thống nhất trên CI.

Không nên phụ thuộc chính xác từng câu chữ trong weave report bởi format log có thể khác giữa các bản AspectJ; hãy xác minh **tập join point** và kiểm thử hành vi.

Chạy:

```bash
java -cp "build/woven:tools/aspectjrt-1.9.24.jar" demo.shop.Main
```

**Stdout mong đợi của ứng dụng**:

```text
AUDIT START: submit
AUDIT OK: submit
SUBMITTED:A-17
PREVIEW:A-17
MAINTENANCE:M-1
PONG
AUDIT START: fail
AUDIT ERROR: fail - IllegalStateException
CAUGHT:rejected
```

Compiler có thể in thông báo weaving riêng **trong bước build**, nhưng không thuộc stdout trên khi chạy chương trình.

### 5.1. Giải thích stdout

- Hai dòng `AUDIT START: submit` và `AUDIT OK: submit` xuất hiện **trước** khi `Main` in result từ lời gọi `submit`.
- `preview` vẫn trả về đúng giá trị nghiệp vụ, nhưng **không có** dòng `AUDIT` dành cho `preview`.
- `maintenance` nằm trong namespace được chọn và có marker ghi log, nhưng **bị loại trừ tường minh** bằng `@NoLog`.
- `ping` cũng mang marker nhưng bị loại vì namespace `internal`. Vì thế chỉ thấy `PONG`.
- `fail` ném ngoại lệ: có `START` và `ERROR`, **không** có `OK`; code gọi vẫn bắt được đúng `IllegalStateException` với message `rejected`.
- Có đúng **hai method được audit** trong ví dụ, mỗi lần gọi tạo hai dòng log, tổng cộng bốn dòng `AUDIT`.

Chỉ cần một dòng audit xuất hiện cho method bị loại hoặc một dòng audit bắt buộc bị thiếu thì testcase nghiệm thu phải fail.

## 6. Biến kiểm thử tự động: match và no-match

### 6.1. So sánh toàn bộ kết quả

Sau khi compile/weave thành công, trên POSIX shell có thể dùng:

```bash
actual=$(java -cp \
  "build/woven:tools/aspectjrt-1.9.24.jar" \
  demo.shop.Main)

expected=$(printf '%s\n' \
  'AUDIT START: submit' \
  'AUDIT OK: submit' \
  'SUBMITTED:A-17' \
  'PREVIEW:A-17' \
  'MAINTENANCE:M-1' \
  'PONG' \
  'AUDIT START: fail' \
  'AUDIT ERROR: fail - IllegalStateException' \
  'CAUGHT:rejected')

test "$actual" = "$expected"
```

Mã thoát của `test` bằng `0` khi output khớp. So sánh toàn bộ chuỗi có ích cho **ví dụ đơn luồng, output xác định**: nó bắt được cả trường hợp thiếu log và trường hợp ghi log thừa. Với ứng dụng thật, nên đưa log vào sink có thể quan sát/assert từng event bằng metadata được chuẩn hóa, tránh phụ thuộc thứ tự xen kẽ của nhiều thread hay format log bên ngoài.

Để kiểm thử riêng các tiêu chí:

- **Must match:** `submit` và `fail` tạo đúng cặp event yêu cầu.
- **Must not match theo thiếu annotation:** `preview` không tạo event.
- **Must not match theo marker phủ định:** `maintenance` không tạo event.
- **Must not match theo package phủ định:** `InternalJobs.ping` không tạo event.
- **Không thay đổi semantics:** giá trị trả về và ngoại lệ vẫn như khi không áp dụng advice.

### 6.2. Test sau khi đóng gói artifact

Gói class đã dệt:

```bash
jar --create \
  --file build/aop-logging-lab.jar \
  -C build/woven .

jar --list --file build/aop-logging-lab.jar
```

Phải thấy các entry quan trọng như:

```text
demo/shop/Main.class
demo/shop/service/OrderService.class
demo/shop/service/internal/InternalJobs.class
demo/shop/aspect/AuditAspect.class
demo/shop/audit/Logged.class
demo/shop/audit/NoLog.class
```

JAR có thể có manifest và metadata khác; danh sách không bắt buộc phải có đúng thứ tự trên. Chạy **chính JAR đã đóng gói**:

```bash
java -cp "build/aop-logging-lab.jar:tools/aspectjrt-1.9.24.jar" \
  demo.shop.Main
```

Expected stdout giống mục 5.1. Trên Windows, classpath separator là `;` thay vì `:`. Việc đóng gói JAR **không tự ghép** runtime `aspectjrt` vào trong, vì vậy phải phân phối nó hoặc chuẩn bị launcher/package mang đủ phụ thuộc.

Kiểm tra bytecode có thể dùng:

```bash
javap -classpath build/aop-logging-lab.jar \
  -c -p demo.shop.service.OrderService
```

Ở các method được weave, compiler có thể chèn call tới aspect/helper. Tên method phụ trợ và layout instruction có thể thay đổi theo phiên bản; **đừng chỉ grep một tên helper cố định**. Kết hợp weave report, kiểm tra JAR cuối và chạy ứng dụng là bằng chứng mạnh hơn kiểm tra bytecode đơn lẻ.

## 7. Thử nghiệm thay đổi từng điều kiện pointcut

Đây là phần quan trọng của bài tập tổng hợp: quan sát việc mở rộng/thu hẹp tập join point khi thay đổi **một điều kiện mỗi lần**. Mỗi biến thể cần biên dịch lại output sạch và chạy lại bảng nghiệm thu.

### 7.1. Bỏ `@annotation(Logged)`

Nếu pointcut chỉ còn chọn public method trong `service`, ngoại trừ `@NoLog` và `internal`, `preview` sẽ bị log dù không thuộc hợp đồng. Đây là lỗi **overmatching**. Với logic audit, nguy cơ còn là leak tham số nếu advice thực tế ghi cả args.

### 7.2. Bỏ `!@annotation(NoLog)`

`maintenance` sẽ được log vì nó mang `@Logged` và thuộc package positive. Thử nghiệm chứng minh một exclusion có tác dụng thật, không chỉ là điều kiện trang trí.

### 7.3. Bỏ `!within(demo.shop.service.internal..*)`

`InternalJobs.ping` sẽ được log vì package con vẫn thuộc `service..*` và method có `@Logged`. Đây là chứng cứ cần thiết để giữ ranh giới nội bộ độc lập với marker.

### 7.4. Giới hạn bằng tên phương thức thay annotation

Thử thay `@annotation(Logged)` bằng một mẫu tên như `execution(* *..*.submit*(..))` (điều chỉnh cú pháp cho weaver). Tên có thể đổi thành `confirm` trong một lần refactor nhưng ý nghĩa audit vẫn còn. Nếu không có test bảo vệ, advice sẽ biến mất âm thầm. Marker diễn đạt ngữ nghĩa tốt hơn trong trường hợp này, dù vẫn phải được kiểm soát khi đổi code.

### 7.5. Đổi `execution` thành `call`

Đây không phải một phép thay thế tương đương. `execution` bắt ở thân method được weave; `call` bắt tại call site phù hợp được weave. Một lời gọi phát sinh từ thư viện/class không được weave có thể không bị advice `call` chặn, dù target execution vẫn chạy. Chỉ thử khi hiểu phạm vi weaving và pointcut designator được công cụ hỗ trợ.

### 7.6. Thêm phương thức mới

Thêm một public method không có marker vào `OrderService`; xác nhận không log. Sau đó thêm `@Logged` cho method mới; xác nhận log. Cuối cùng thêm `@NoLog`; xác nhận lại không log. Chuỗi thử nghiệm cho thấy chính **hợp đồng annotation và exclusion**, không phải tên method ngẫu nhiên, quyết định chính sách.

**Lưu ý:** với các biến thể cố tình làm sai, bộ test chuẩn phải **fail**. Đó là tín hiệu mong muốn chứng minh test phát hiện lỗi, không phải lý do sửa “expected output” để mọi biến thể đều pass.

## 8. Bài nâng cao: tăng độ tin cậy của logging aspect

### 8.1. Không để dữ liệu nhạy cảm lọt vào log

Ví dụ in **chỉ tên method**. Một hệ thống thực tế có thể thêm correlation ID, thời gian, trạng thái hoặc mã lỗi, nhưng không nên tự động in tất cả `args`, result, token hay exception message. Khi thêm field, cần có chính sách:

- Field nào được phép ghi?
- Dữ liệu có phải che/mask không?
- Log có bị đọc bởi nhiều người hoặc chuyển sang dịch vụ bên ngoài không?
- Giá trị có tạo cardinality không giới hạn hay chứa payload quá lớn không?

Với failure, ví dụ chỉ in **tên lớp exception** để tránh lộ message. Với ứng dụng thật, chọn log level và sink phù hợp, lưu nguyên nhân lỗi ở nơi được kiểm soát khi cần chẩn đoán.

### 8.2. Advice có thể ném ngoại lệ

Ví dụ `System.out.println` đơn giản, nhưng logger thực tế có thể fail do I/O, định dạng, serialize hoặc backpressure. Nếu yêu cầu là “logging hỏng không được phá nghiệp vụ”, cần thiết kế rõ fail-open và cách cô lập lỗi của sink. Nếu audit là bắt buộc về mặt pháp lý hoặc transaction, đôi khi fail-closed lại được lựa chọn. **Đây là chính sách ứng dụng**, không có một quy tắc chung cho mọi aspect.

Tránh viết `catch (Exception ignored)` bao quanh toàn bộ advice mà không hiểu hậu quả: nó có thể che mất sự cố giám sát quan trọng. Test trường hợp logger hỏng để xác nhận chính sách mong muốn.

### 8.3. Logger không nên trở thành một join point của chính nó

Một broad pointcut như `execution(* *(..))` có thể bắt cả method helper bên trong aspect, tạo recursion hoặc log storm, tùy phạm vi dệt. Trong ví dụ, positive scope `demo.shop.service..*` đã loại package `demo.shop.aspect`. Với hệ thống lớn, quy tắc an toàn thường bao gồm giới hạn scope và exclusion cho logging/metrics/tracing infrastructure nếu các lớp đó có nguy cơ nằm trong phạm vi weaving.

Không giải quyết mọi vấn đề chỉ bằng cách thêm dần hàng chục exclusion. Nếu danh sách phủ định quá dài, xem lại positive scope và ranh giới kiến trúc.

### 8.4. Aspect state, concurrency và thứ tự event

Ví dụ không lưu trạng thái dùng chung. Nếu thêm bộ đếm event hoặc context, tránh biến mutable không thread-safe trong singleton aspect. Một chương trình nhiều luồng có thể tạo event xen kẽ, nên cần correlation ID hoặc per-request context phù hợp để ghép START với OK/ERROR. Không lấy thứ tự các dòng log global làm bằng chứng chắc chắn cho một request.

`ThreadLocal` có thể hữu ích trong mô hình thread-per-request, nhưng cần xử lý cleanup và các trường hợp chuyển ngữ cảnh; mô hình task bất đồng bộ hoặc virtual thread có chính sách riêng. Không chuyển tiếp context bằng cách giữ tham chiếu lâu dài vô ý.

### 8.5. Around advice và `proceed`

Yêu cầu hiện tại không cần quanh toàn bộ lời gọi. Nếu chuyển sang `around` để đo duration, code phải gọi `proceed()` theo semantics đã chọn, trả về đúng kết quả, giữ ngoại lệ và dọn context trong `finally`. Dùng `around` nhưng quên `proceed` sẽ làm business method không chạy; gọi `proceed` hai lần có thể tạo giao dịch/side effect lặp. Đây là lỗi lớn hơn việc thiếu một dòng log.

### 8.6. Chi phí ghi log và pointcut động

Weaving có thể chèn mã vào join point, nhưng advice vẫn tiêu thụ CPU/bộ nhớ/I/O. Nếu instrument một getter được gọi hàng triệu lần, tác động có thể lớn dù chỉ in một dòng mỗi lần. Thu hẹp pointcut là tối ưu căn bản.

Các điều kiện động như `args` hoặc `if()` (nếu được hỗ trợ) có thể thêm công việc kiểm tra runtime. Khi có thể, hãy dùng thông tin kiểu/annotation/phạm vi để lọc tĩnh; dùng điều kiện runtime cho các quy tắc thực sự phụ thuộc dữ liệu và kiểm tra chi phí dưới tải đại diện.

## 9. Kiểm tra rủi ro khi thay đổi mã và build

### 9.1. Refactor và marker

Đổi tên `submit` thành `confirm` nhưng giữ marker `@Logged` trên method mới, chạy lại weaving và test. Lúc này tên in trong log thay đổi thành `confirm` vì metadata phản ánh tên mới, nhưng **quyết định có audit** vẫn do marker và phạm vi quyết định. Bộ test cần cập nhật expected name theo thay đổi có chủ đích, đồng thời xác nhận method vẫn được chọn.

Chuyển `submit` ra ngoài `demo.shop.service..*` sẽ làm nó không còn match mặc dù vẫn mang `@Logged`. Nếu thao tác vẫn thuộc nghiệp vụ phải audit, cần xem xét lại **ranh giới scope**, không âm thầm nới toàn bộ pointcut thành `execution(* *(..))`.

Nếu chuyển vào `demo.shop.service.internal`, exclusion có quyền ưu tiên và advice không chạy. Đó là hành vi phù hợp với quy tắc đã phát biểu, nhưng nếu không còn phù hợp nghiệp vụ thì phải cập nhật hợp đồng và test công khai.

### 9.2. Override và annotation

Method annotation trên interface hoặc class cha **không tự động** xuất hiện ở method override như một quy luật Java tổng quát. Cách bộ weaving xác định annotation tại execution join point có thể khác cách một proxy dùng reflection trên interface. Khi đưa marker vào nhiều cấp kế thừa, phải test trên method **thực sự chạy**, tránh chỉ nhìn metadata ở interface.

### 9.3. Build artifact

Một dự án có thể chứa nhiều thư mục lớp: plain classes, woven classes, classes từ test và JAR phát hành. Nếu compiler báo đã weave nhưng đóng gói nhầm plain classes, log sẽ biến mất khi triển khai. Luôn chạy smoke test từ **artifact cuối**. Nếu có load-time weaving, phải kiểm tra cấu hình agent và thời điểm class loader định nghĩa class; không dùng kết quả CTW để suy luận tự động về LTW.

### 9.4. Theo dõi tập match

Giữ một “join point inventory” ở mức đủ cần thiết, ví dụ:

```text
MUST MATCH:
  demo.shop.service.OrderService.submit(String)
  demo.shop.service.OrderService.fail()

MUST NOT MATCH:
  demo.shop.service.OrderService.preview(String)
  demo.shop.service.OrderService.maintenance(String)
  demo.shop.service.internal.InternalJobs.ping()
```

Khi PR làm thay đổi tập match, reviewer cần thấy lý do: nghiệp vụ mới, marker mới hay thay đổi phạm vi? Nếu chỉ đếm số join point, một điểm mất và một điểm thừa có thể triệt tiêu về tổng số nhưng vẫn là lỗi.

## 10. Đề kiểm thử đánh giá cuối bài

Học viên cần tự nộp:

1. Các file mã nguồn, trong đó aspect có named pointcut và đủ các điều kiện chọn/loại trừ.
2. Lệnh biên dịch/weave, phiên bản JDK và weaver, cùng weave report chứng minh điểm được chọn.
3. Artifact đã weave hoặc quy trình build tái tạo được artifact, kèm lệnh chạy runtime.
4. Kết quả kiểm thử must-match và must-not-match trên bảng mục 2.1.
5. Một thử nghiệm cố ý bỏ `@NoLog` hoặc package exclusion, cho thấy test fail vì match thừa.
6. Giải thích ảnh hưởng khi đổi tên method, chuyển package hoặc dùng cơ chế proxy thay vì method-execution weaving.
7. Đề xuất logging production không làm lộ dữ liệu nhạy cảm và không thay đổi semantics của nghiệp vụ.

### 10.1. Tiêu chí chấm

| Tiêu chí | Điểm | Điều kiện đạt |
|---|---:|---|
| Phân tích phạm vi | 20 | Giải thích rõ inclusion/exclusion và đủ trường hợp |
| Pointcut đúng | 20 | Match đúng tập method, không phụ thuộc wildcard toàn cục |
| Advice đúng luồng | 20 | START/OK/ERROR chính xác, exception và return giữ nguyên |
| Kiểm thử dương/âm | 20 | Có test phát hiện cả thiếu log lẫn thừa log |
| Build và đóng gói | 10 | Weave thành công; chạy từ artifact đã weave với runtime đầy đủ |
| Giải thích rủi ro | 10 | Đề cập refactor, bảo mật log, hiệu năng, recursion và giới hạn AOP |

**Đạt yêu cầu** khi test chạy trên artifact đã weave đúng output ở mục 5 và giải thích được từng điều kiện loại trừ. Các điểm chấm giúp tự đánh giá, không thay thế xác minh kỹ thuật.

## 11. Các lỗi thường gặp trong lời giải

**Lỗi: chỉ viết `execution(* demo.shop..*.*(..))`.** Pointcut sẽ chọn cả thao tác chỉ đọc và mã kỹ thuật. Cách sửa là đặt thêm ranh giới service, marker được audit và exclusion có chủ đích.

**Lỗi: dùng `@Logged` nhưng bỏ `@NoLog`.** Một method được đánh dấu song song vẫn bị log; điều kiện loại trừ phải có mặt thực sự trong pointcut và được test.

**Lỗi: viết `!within(demo.shop.service.internal.*)` rồi nghĩ đã loại mọi package con.** Mẫu type/package trong AspectJ cần hiểu chính xác; dùng `..*` cho namespace phân cấp phù hợp và xác nhận qua test class nằm sâu hơn.

**Lỗi: dùng method name làm hợp đồng nghiệp vụ duy nhất.** `submit*(..)` có thể match nhầm các method mới hoặc bỏ sót sau refactor. Marker/ranh giới ổn định cùng test làm ý định rõ hơn.

**Lỗi: chỉ quan sát dòng START.** Nếu logic after-return/after-throw sai, hoặc exception bị nuốt, test vẫn có thể báo pass. Cần assert cả OK/ERROR và nghiệp vụ.

**Lỗi: tự gọi lại target trong advice.** Logging before/after không đòi hỏi gọi method target lần nữa; lặp lời gọi có thể tạo side effect và event kép.

**Lỗi: coi `javac` biên dịch được `.aj`.** `.aj` là cú pháp AspectJ; dùng compiler tương ứng hoặc công cụ hỗ trợ rõ ràng, và giữ runtime dependency khi chạy.

**Lỗi: chỉ test class directory rồi giao JAR khác.** Cần đóng gói từ woven output và smoke test chính artifact phát hành.

**Lỗi: so sánh dòng log từ nhiều thread bằng thứ tự global tuyệt đối.** Sự xen kẽ giữa thread là bình thường; chọn correlation/context và kiểm tra tập event trên từng đơn vị nghiệp vụ.

**Lỗi: ghi tất cả args/result để tiện debug.** Thông tin có thể nhạy cảm, khổng lồ hoặc khó serialize. Chỉ ghi dữ liệu thực sự được cho phép và có cấu trúc.

## 12. Checklist trước khi hoàn tất

- [ ] Đã phát biểu được bằng lời nghiệp vụ nào cần ghi log và nghiệp vụ nào không.
- [ ] Pointcut có tên; positive scope dễ đọc; `@Logged` được dùng nhất quán.
- [ ] `@NoLog` và `service.internal..*` thực sự bị loại, không chỉ mô tả bằng comment.
- [ ] Advice không chặn code logging của chính nó và không gọi lại target.
- [ ] Kết quả của `submit`, `preview`, `maintenance`, `ping` đúng.
- [ ] `fail` tạo ERROR và ngoại lệ vẫn đến caller; không có OK giả.
- [ ] Có kiểm thử chứng minh **4 trường hợp rõ ràng: chọn, thiếu marker, marker phủ định, package phủ định**; đồng thời có đường ngoại lệ.
- [ ] Weave report đúng; code chạy từ class/JAR đã weave.
- [ ] Kịch bản cố tình nới pointcut khiến test phát hiện match thừa.
- [ ] Có kế hoạch xử lý thay đổi tên/package, annotation và môi trường build.
- [ ] Không đưa dữ liệu nhạy cảm vào log; đã cân nhắc runtime overhead và concurrency.

**Thông điệp cuối bài:** một logging aspect đúng không được đánh giá bằng việc “có tạo log”, mà bằng **tập join point được chọn chính xác, tập bị loại trừ chính xác và nghiệp vụ không đổi**. Hãy phát biểu chính sách chọn trước, biểu diễn nó bằng pointcut dễ review, rồi kiểm chứng bằng cả test dương lẫn test âm trên artifact thực sự chạy.