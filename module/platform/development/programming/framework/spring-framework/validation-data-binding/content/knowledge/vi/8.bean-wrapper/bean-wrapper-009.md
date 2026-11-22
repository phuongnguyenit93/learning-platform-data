# Ảnh hưởng của setter tới bất biến và tác dụng phụ khi dùng BeanWrapper

## 1. Vấn đề: binding là thao tác thay đổi trạng thái thật

Trong Spring Framework, `BeanWrapper` và `BeanWrapperImpl` cho phép truy cập thuộc tính JavaBean qua tên, chẳng hạn `customerName` hoặc `address.city`. Khi dùng **bean property access**, thao tác ghi thuộc tính sẽ đi qua setter JavaBean tương ứng, ví dụ `setCustomerName(...)`. `DataBinder` dùng cơ chế này cho **property binding** mặc định; Spring cũng hỗ trợ constructor binding và direct-field access, có cơ chế khác.

Điều dễ bỏ sót: setter là một **phương thức Java có thể chạy logic bất kỳ**, chứ không phải một thao tác gán dữ liệu được framework bảo đảm an toàn. Nếu setter:

- kiểm tra hoặc thay đổi các thuộc tính khác;
- cập nhật bộ đếm, cache hay audit;
- ghi database, phát event, gửi email, gọi dịch vụ ngoài;
- ném exception khi phát hiện giá trị không hợp lệ;
- sử dụng trạng thái hiện tại của các thuộc tính khác;

thì các hành vi ấy có thể xảy ra **ngay khi BeanWrapper/DataBinder gọi setter**. Chúng có thể xảy ra **trước** khi toàn bộ các field được bind, trước `Validator.validate(...)` và trước khi caller quyết định chấp nhận hay từ chối yêu cầu.

### Kết quả học tập

Sau bài này, bạn có thể giải thích cơ chế gọi setter qua `BeanWrapper`; phân biệt bất biến của từng thuộc tính với bất biến liên quan nhiều thuộc tính; nhận diện lỗi cập nhật một phần, tác dụng phụ lặp lại và vấn đề thứ tự gán; chọn ranh giới DTO, validation và domain phù hợp; kiểm soát thuộc tính được phép bind; cũng như kiểm thử cả trạng thái và các tác dụng phụ.

**Nguyên tắc nền tảng:** binding là thao tác biến đổi object; validation là thao tác kiểm tra dữ liệu hoặc object ở một thời điểm. Hai hoạt động này có trách nhiệm khác nhau. Một kết quả `BindingResult` có lỗi không có nghĩa mọi thay đổi trước đó đều được hoàn tác.

## 2. BeanWrapper đi vào setter như thế nào?

Ví dụ một JavaBean:

~~~java
public class ProductDraft {
    private String title;

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

Đây là một class JavaBean độc lập; Spring nhận biết property `title` qua các phương thức truy cập theo quy ước JavaBeans. Với `BeanWrapperImpl`:

~~~java
ProductDraft draft = new ProductDraft();
BeanWrapper wrapper = new BeanWrapperImpl(draft);
wrapper.setPropertyValue("title", "Spring");
String current = (String) wrapper.getPropertyValue("title");
~~~

Đoạn thứ hai là **mảnh code** trong một phương thức đã import `org.springframework.beans.BeanWrapper` và `BeanWrapperImpl`. `setPropertyValue("title", ...)` tìm writable property tương ứng và gọi `setTitle(...)` (kèm chuyển kiểu nếu cần). `getPropertyValue(...)` đọc thông qua getter; vì getter cũng là phương thức Java, không nên cài tác dụng phụ bên trong getter được dùng rộng rãi để quan sát/trình bày.

Cơ chế tương tự có thể xuất hiện khi:

~~~java
DataBinder binder = new DataBinder(draft, "draft");
binder.bind(new MutablePropertyValues(
    java.util.Map.of("title", "Spring")
));
~~~

Đây cũng là mảnh code, cần import `org.springframework.validation.DataBinder` và `org.springframework.beans.MutablePropertyValues`. `DataBinder` tạo một lớp điều phối quanh property access: giới hạn field được bind, xử lý chuyển kiểu và ghi nhận lỗi vào `BindingResult`. Nó không biến setter của object đích thành một thao tác không có tác dụng phụ.

### So sánh các cơ chế

| Cơ chế | Thay đổi object bằng cách nào? | Liên quan tới setter |
| --- | --- | --- |
| `BeanWrapperImpl.setPropertyValue(...)` | Ghi property theo JavaBeans conventions | Gọi setter tương ứng cho writable property |
| `DataBinder.bind(...)` với bean property access | Dùng property accessor để gán các `PropertyValues` | Có thể gọi nhiều setter |
| `DataBinder.initDirectFieldAccess()` rồi `bind(...)` | Truy cập field trực tiếp qua cơ chế phản chiếu | Bỏ qua setter; có thể bỏ qua luôn guard nằm trong setter |
| `DataBinder.construct(...)` | Khởi tạo object qua constructor binding | Kiểm soát qua constructor, không phụ thuộc các setter để tạo đối tượng |
| Jackson deserialize `@RequestBody` | Tuỳ cấu hình: constructor, setter, field, creator, v.v. | Không nên khẳng định mọi JSON request luôn dùng `BeanWrapper` |

`BeanWrapper.isWritableProperty("title")` chỉ cho biết một property có thể ghi theo cơ chế đó; **không chứng minh việc ghi property an toàn về nghiệp vụ, không có tác dụng phụ, hoặc được client phép sửa**.

## 3. Bất biến là gì và setter có thể bảo vệ hoặc phá vỡ chúng ra sao?

**Bất biến (invariant)** là điều kiện cần tiếp tục đúng trong các trạng thái hợp lệ của object. Ví dụ:

- Số lượng `quantity` của một dòng hàng phải dương.
- Khoảng thời gian phải thỏa `start <= end`.
- `reserved <= available` đối với tồn kho.
- Trạng thái `PAID` chỉ được chuyển sang `REFUNDED` theo quy tắc cho phép.
- Một đơn hàng đã chốt không được thay đổi giá tổng bằng một setter công khai.

Có hai nhóm quan trọng:

1. **Bất biến cục bộ (single-field):** có thể kiểm một giá trị độc lập, ví dụ `quantity >= 1`. Một setter có thể từ chối giá trị không hợp lệ trước khi gán.
2. **Bất biến liên thuộc (cross-field/aggregate):** cần xem đồng thời nhiều giá trị hoặc trạng thái nghiệp vụ, ví dụ `start <= end`. Hai setter riêng có thể không biết trạng thái cuối cùng mà caller dự định thiết lập.

Setter có guard không phải lúc nào cũng sai. Vấn đề xuất hiện khi object bị đưa vào một cơ chế **gán nhiều field tuần tự**, trong khi contract của object lại yêu cầu thay đổi một nhóm field **cùng nhau**. Nếu getter hoặc setter của một field quan sát trạng thái trung gian, nó có thể thấy một snapshot chưa hợp lệ theo ý định của caller.

### Một ví dụ về thứ tự gán

Giả sử khoảng thời gian ban đầu là `[1, 5]`, cần đổi thành `[7, 9]`. Cách triển khai sau cố bảo vệ invariant trong từng setter:

~~~java
public final class Range {
    private int start = 1;
    private int end = 5;

    public int getStart() {
        return start;
    }

    public int getEnd() {
        return end;
    }

    public void setStart(int value) {
        if (value > end) {
            throw new IllegalArgumentException("start > end");
        }
        start = value;
    }

    public void setEnd(int value) {
        if (value < start) {
            throw new IllegalArgumentException("end < start");
        }
        end = value;
    }
}
~~~

Đây là một class Java đầy đủ; các lời gọi sau là mảnh minh họa:

~~~java
Range range = new Range();
BeanWrapper wrapper = new BeanWrapperImpl(range);

// Đặt start trước: thất bại vì 7 > end hiện tại (5).
wrapper.setPropertyValue("start", 7);

// Nếu caller bắt lỗi rồi tiếp tục:
wrapper.setPropertyValue("end", 9);
wrapper.setPropertyValue("start", 7);
~~~

Lệnh đầu tiên có thể ném `BeansException` (Spring bọc lỗi từ setter) và không thể tự chuyển atomically sang trạng thái mong muốn. Sau khi xử lý lỗi và gán `end=9`, việc gán `start=7` mới hợp lệ. **Cùng bộ giá trị mong muốn nhưng khác thứ tự setter có thể cho kết quả khác nhau.** Không xây dựng tính đúng đắn nghiệp vụ dựa trên thứ tự field trong form, query string, JSON hay thứ tự property của binder.

Thiết kế phù hợp hơn là một phương thức biểu diễn **một ý định nghiệp vụ trọn vẹn**:

~~~java
public void changeRange(int newStart, int newEnd) {
    if (newStart > newEnd) {
        throw new IllegalArgumentException("start > end");
    }
    this.start = newStart;
    this.end = newEnd;
}
~~~

Đây là mảnh method nên nằm trong class `Range`. Nó kiểm tra cả hai giá trị trước khi gán; kết quả không phụ thuộc vào thứ tự gọi hai setter. Nếu việc thay đổi cần truy cập các đối tượng khác hoặc tạo tác dụng phụ bên ngoài, kiểm invariant vẫn phải đi cùng ranh giới transaction và quy tắc domain thích hợp.

## 4. Tác dụng phụ của setter có thể gồm những gì?

Một setter chỉ gán field:

~~~java
public void setName(String name) {
    this.name = name;
}
~~~

thường dễ dự đoán hơn setter vừa gán vừa thực hiện hành động khác:

~~~java
public void setName(String name) {
    this.name = name;
    auditLog.add("name changed");
    notificationGateway.sendNameChanged(name);
}
~~~

Các đoạn trên là **mảnh code minh họa**; `auditLog` và `notificationGateway` là các dependency giả định. Hành vi quan trọng là: mỗi lần binder gọi `setName` có thể ghi audit và gửi thông báo, ngay cả khi một field khác sau đó thất bại.

Các dạng tác dụng phụ cần xem xét:

| Tác dụng phụ | Biểu hiện | Rủi ro khi binding |
| --- | --- | --- |
| Tăng bộ đếm, ghi log, thay đổi cache | Setter gọi thêm mã nội bộ | Lặp lại setter tạo nhiều side effect; số lần gọi trở thành đặc tính ngoài ý muốn |
| Tính lại field phụ thuộc | Setter gán `total = price * quantity` | Giá trị trung gian có thể dùng `price` mới và `quantity` cũ |
| Phát domain event hoặc message | Setter gửi Kafka/event bus | Dữ liệu không hợp lệ vẫn có thể phát event; rollback DB không tự xóa message đã gửi |
| Gửi email/HTTP request | Setter gọi dịch vụ ngoài | Lỗi binding ở field khác không thể “thu hồi” hành động bên ngoài |
| Ghi persistence | Setter gọi repository hoặc entity đang managed trở nên dirty | Có thể lưu trạng thái không như dự định nếu transaction vẫn commit |
| Ném exception sau khi đã gán | Setter sửa trạng thái rồi kiểm tra | Trạng thái có thể đã đổi dù caller nhận lỗi |
| Tự sửa nhiều field | Setter tự điều chỉnh field khác | Kết quả phụ thuộc thứ tự gán và khó dự đoán |

Một setter **không được Spring cam kết gọi đúng một lần trong mọi tình huống**. Việc có gọi setter hay không còn phụ thuộc source field, chuyển kiểu, cách access, binding lồng nhau, cấu hình framework và logic caller. Khi ứng dụng cần idempotency, không nên coi số lần setter được gọi là tín hiệu để phát side effect.

**Tác dụng phụ ở mức local memory** cũng đáng quan tâm. Một setter cập nhật cache hoặc danh sách audit trong object có thể để lại trạng thái thay đổi ngay cả khi database transaction được rollback. DB transaction chỉ bảo đảm các thao tác nằm trong phạm vi transaction tương ứng; email, network request, cache ngoài và message đã publish cần cơ chế riêng như after-commit dispatch hoặc transactional outbox khi yêu cầu nhất quán.

## 5. Ví dụ hoàn chỉnh Java 17: setter lặp lại và batch cập nhật một phần

Chương trình sau trực tiếp sử dụng `BeanWrapperImpl` để minh họa hai hiện tượng:

1. Gọi setter nhiều lần với **cùng giá trị** vẫn có thể tạo side effect nhiều lần.
2. Một batch set property có thể thành công ở field trước và thất bại ở field sau. Lỗi không tự đảo ngược field đã được thay đổi.

Ví dụ chạy với **Java 17+, Maven và Spring Framework 6.2.0**. Không cần Spring Boot, servlet, web controller hay database.

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>bean-wrapper-setters</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-beans</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `src/main/java/SetterEffectsDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.BeansException;
import org.springframework.beans.MutablePropertyValues;

public class SetterEffectsDemo {

    public static class OrderDraft {
        private String customer = "Initial";
        private int quantity = 1;
        private int setterCalls;
        private final List<String> customerNotifications = new ArrayList<>();

        public String getCustomer() {
            return customer;
        }

        public int getQuantity() {
            return quantity;
        }

        public int getSetterCalls() {
            return setterCalls;
        }

        public int getNotificationCount() {
            return customerNotifications.size();
        }

        public void setCustomer(String value) {
            setterCalls++;
            customer = value;
            customerNotifications.add(value);
        }

        public void setQuantity(int value) {
            setterCalls++;
            if (value < 1) {
                throw new IllegalArgumentException(
                    "quantity must be positive");
            }
            quantity = value;
        }
    }

    public static void main(String[] args) {
        OrderDraft draft = new OrderDraft();
        BeanWrapper wrapper = new BeanWrapperImpl(draft);

        wrapper.setPropertyValue("customer", "Lan");
        wrapper.setPropertyValue("customer", "Lan");

        System.out.println("afterRepeat=" + draft.getCustomer());
        System.out.println("notifications=" + draft.getNotificationCount());

        MutablePropertyValues changes = new MutablePropertyValues();
        changes.add("customer", "Mai");
        changes.add("quantity", -5);

        try {
            wrapper.setPropertyValues(changes);
            System.out.println("batchFailed=false");
        } catch (BeansException ex) {
            System.out.println("batchFailed=true");
        }

        System.out.println("customer=" + draft.getCustomer());
        System.out.println("quantity=" + draft.getQuantity());
        System.out.println("setterCalls=" + draft.getSetterCalls());
        System.out.println("notifications=" + draft.getNotificationCount());
    }
}
~~~

Chạy trong thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=SetterEffectsDemo
~~~

Stdout dự kiến từ chương trình:

~~~text
afterRepeat=Lan
notifications=2
batchFailed=true
customer=Mai
quantity=1
setterCalls=4
notifications=3
~~~

Giải thích từng bước:

- Hai lời gọi `setPropertyValue("customer", "Lan")` cùng kích hoạt `setCustomer(...)`, nên `customerNotifications` tăng từ 0 lên 2 **dù giá trị không thay đổi giữa hai lần gọi**. Setter không tự có tính idempotent.
- `MutablePropertyValues` được thêm `customer` trước `quantity`. Với thứ tự trong ví dụ này, Spring thực hiện setter `customer="Mai"` thành công; sau đó `setQuantity(-5)` ném `IllegalArgumentException` do guard, được bộ truy cập property của Spring phản ánh qua `BeansException`.
- `customer` vẫn là `"Mai"` sau lỗi. `quantity` vẫn bằng 1 vì method `setQuantity` kiểm tra trước khi gán; đây là tính chất của method **trong ví dụ**, không phải một cơ chế rollback tự động của Spring.
- `setterCalls=4` tính cả **lần setter số lượng thất bại** vì biến đếm được tăng trước lệnh kiểm tra. `notifications=3` tính ba lần gọi setter customer thành công.
- Ví dụ ghi side effect vào một `List` trong bộ nhớ để nhìn thấy rõ hậu quả; nếu thay danh sách bằng publish event hoặc email thì side effect đó có thể khó hoặc không thể hoàn tác.

**Độ tin cậy của stdout:** ví dụ dùng các giá trị cố định và in các thuộc tính tường minh, không dựa trên thứ tự iterating của `Map` hoặc toàn bộ chuỗi thông báo exception. `BeansException` được bắt như một supertype, nên không khóa test vào text/thứ tự của exception message. Đây là bài chạy Maven với dependency Spring; lệnh `javac SetterEffectsDemo.java` đơn lẻ sẽ không đủ classpath cho Spring.

### Điều gì xảy ra nếu setter ném sau khi gán?

So sánh setter trong demo:

~~~java
public void setQuantity(int value) {
    if (value < 1) {
        throw new IllegalArgumentException("invalid quantity");
    }
    quantity = value;
}
~~~

với biến thể nguy hiểm:

~~~java
public void setQuantity(int value) {
    quantity = value; // Đã thay đổi object.
    if (value < 1) {
        throw new IllegalArgumentException("invalid quantity");
    }
}
~~~

Đây là hai **mảnh code thay thế cho nhau**, không đặt cả hai vào cùng class. Ở biến thể thứ hai, exception xảy ra **sau khi object chứa giá trị không hợp lệ**. Một caller bắt ngoại lệ mà tiếp tục dùng hoặc lưu object đó có thể duy trì bất biến sai. Spring không thể tự biết phải phục hồi trạng thái nào, nhất là nếu setter còn sửa các field hoặc hệ thống bên ngoài.

## 6. Gán nhiều property không phải transaction

`BeanWrapper.setPropertyValues(...)` có thể tiếp tục xử lý các property khác đối với lỗi có thể phục hồi và báo nhiều lỗi; các property đã được ghi thành công vẫn ở trạng thái mới. Với `DataBinder.bind(...)`, các lỗi truy cập property phù hợp có thể được ghi vào `BindingResult`; điều đó **không** bảo đảm object chưa bị biến đổi.

Các kết luận cần tránh:

- “`setPropertyValues(...)` nhận một collection nên tất cả field được gán nguyên tử.”
- “`BindingResult.hasErrors() == true` nghĩa là target vẫn còn trạng thái cũ.”
- “`DataBinder.close()` ném `BindException` thì mọi setter trước đó đã được rollback.”
- “`@Valid` sau binding sẽ ngăn mọi setter gây tác dụng phụ.”
- “Một database transaction bao phủ luôn HTTP call/email/event được gửi từ setter.”

Diễn biến có thể là:

~~~text
request:  { customer: "Mai", quantity: -5 }
         |
         v
Setter customer("Mai") --> target.customer thay đổi; audit có thể phát sinh
         |
         v
Setter quantity(-5) --> từ chối, phát sinh lỗi
         |
         v
BindingResult/caller có lỗi
         |
         +--> target.customer vẫn có thể là "Mai"
         +--> side effect đã diễn ra vẫn tồn tại
         +--> quyết định rollback/không lưu cần ở tầng nghiệp vụ
~~~

Không có cam kết rằng mọi loại exception setter đều được Spring gói thành cùng một lỗi; một số lỗi có thể dừng thao tác ngay, và một số lỗi truy cập property có thể được tổng hợp. Điểm chung quan trọng là **không được dựa vào exception để giả định object tự hoàn tác**.

### Lỗi chuyển kiểu có thể xảy ra trước setter

Nếu `setQuantity(int)` yêu cầu một số nguyên nhưng binder nhận `quantity="abc"`, bước convert sang `int` có thể thất bại **trước khi setter của property đó được gọi**. Khi đó setter quantity không tạo side effect từ lần thử này; tuy nhiên, setter của các field đã gán trước vẫn có thể chạy.

Bởi vậy khi phân tích lỗi cần phân biệt:

| Giai đoạn | Có thể gây gì? | Setter được gọi? |
| --- | --- | --- |
| Chọn field hợp lệ | Field bị bỏ qua/suppressed do không được bind | Không cho field bị loại |
| Chuyển kiểu | `typeMismatch` và lỗi conversion | Không nhất thiết; lỗi conversion có thể chặn setter field đó |
| Gọi setter | Guard từ chối, side effect, thay đổi field khác | Có |
| Validation sau bind | Lỗi constraint/domain validation | Setter có thể đã chạy trước validation |
| Lưu dữ liệu/dispatch event | Transaction, persistence, outbox, messaging | Phụ thuộc code service, không tự do BeanWrapper thực hiện |

Với `DataBinder`, kiểm `FieldError.isBindingFailure()` để biết lỗi field có nguồn gốc từ binding; nhưng nó không nói liệu **các setter khác** đã thay đổi object hay không. Muốn biết các side effect, phải xem thiết kế của target và đo bằng test/observation phù hợp.

## 7. Bất biến nhiều field: kiểm tra giá trị mới cùng nhau

Một object chứa `price` và `quantity` có quy tắc `total == price.multiply(quantity)`. Nếu setter giá tự tính lại tổng dựa trên quantity hiện tại rồi setter quantity cũng tính lại tổng, kết quả cuối có thể đúng trong một số thứ tự, nhưng bên ngoài có thể quan sát hoặc nhận event về **một tổng trung gian** không thuộc bản cập nhật mong muốn. Nếu chỉ một setter cập nhật `total`, kết quả còn có thể sai hẳn.

Thiết kế domain tốt hơn:

~~~java
public final class OrderLine {
    private java.math.BigDecimal unitPrice;
    private int quantity;

    public OrderLine(java.math.BigDecimal unitPrice, int quantity) {
        change(unitPrice, quantity);
    }

    public void change(java.math.BigDecimal newUnitPrice,
                       int newQuantity) {
        if (newUnitPrice == null
                || newUnitPrice.signum() < 0
                || newQuantity < 1) {
            throw new IllegalArgumentException("invalid order line");
        }

        this.unitPrice = newUnitPrice;
        this.quantity = newQuantity;
    }

    public java.math.BigDecimal getTotal() {
        return unitPrice.multiply(
            java.math.BigDecimal.valueOf(quantity));
    }
}
~~~

Đây là class Java đầy đủ dùng JDK, thể hiện invariant: kiểm cả giá mới và số lượng mới trước khi đổi trạng thái; `getTotal()` tính từ hai field luôn hợp lệ. Lỗi validation không cần tạo side effect để “sửa sai” sau đó. Ở sản phẩm thực, tính thuế, tiền tệ, làm tròn và trạng thái đơn hàng cần quy tắc domain tương ứng.

**Bất biến ở một thời điểm và bất biến xuyên transaction khác nhau:** nếu cần kiểm tồn kho, quyền của người dùng hoặc một trạng thái trong database, việc validate tất cả field của DTO vẫn chưa đủ. Service/domain phải kiểm tra điều kiện liên quan dữ liệu hiện tại, lock/optimistic version khi cần và cập nhật theo transaction. Đừng đặt điều đó vào setter bị framework tự động gọi khi nhận request.

### Phương án bất biến qua constructor

Một record hoặc class immutable nhận toàn bộ giá trị trong constructor:

~~~java
public record ProductCommand(String sku, int quantity) {
    public ProductCommand {
        if (sku == null || sku.isBlank() || quantity < 1) {
            throw new IllegalArgumentException("invalid product");
        }
    }
}
~~~

Đây là Java 17 hoàn chỉnh, dùng compact canonical constructor. Khi tạo `new ProductCommand("BOOK", 2)`, object chỉ xuất hiện sau khi constructor kết thúc thành công; không có setter cho framework gọi dần trên bản thân record. Spring hỗ trợ constructor binding khi được cấu hình theo kiểu dữ liệu/điểm vào phù hợp; tuy nhiên **đừng suy luận mọi converter hoặc Jackson configuration tự có cùng hành vi**. Constructor vẫn có thể chứa side effect nếu tác giả thêm vào, vì vậy immutable không tự bảo đảm “không có side effect” mà cần kỷ luật thiết kế.

## 8. Kiến trúc khuyến nghị: input DTO, validation và phương thức domain

Khi nhận dữ liệu ngoài hệ thống, phân biệt rõ ba lớp trách nhiệm:

1. **Adapter/boundary:** biến chuỗi/JSON/form thành một DTO/command với các thuộc tính **được phép từ nguồn bên ngoài**.
2. **Validation:** kiểm trường bắt buộc, giới hạn độ dài, kiểu, định dạng và các constraint của dữ liệu đầu vào. Các lỗi được phản hồi theo contract.
3. **Service/domain:** kiểm invariant nghiệp vụ theo trạng thái hiện tại; chỉ sau khi các điều kiện cần thiết thành công mới đổi domain qua phương thức có chủ đích. Phát side effect sau thời điểm ghi nhận thành công phù hợp.

~~~text
HTTP form / JSON / CSV
          |
          v
Input DTO (dữ liệu chưa tin cậy)
          |
          v
Binding / conversion / validation
          |
          v
Service: quyền, tồn kho, trạng thái, giao dịch
          |
          v
Aggregate.changeX(allRequiredValues)
          |
          +--> lưu trạng thái hợp lệ
          |
          +--> dispatch event theo chính sách nhất quán
~~~

Ví dụ contract Java (mảnh code service/DTO, không phải một project Spring Boot hoàn chỉnh):

~~~java
public record ChangeOrderCommand(
    String customer, int quantity) {}

public void changeOrder(ChangeOrderCommand input) {
    // Validate input, quyền sửa đơn và trạng thái hiện tại trước.
    order.changeCustomerAndQuantity(
        input.customer(), input.quantity());

    // Lưu và lên lịch side effects sau khi các điều kiện đạt.
}
~~~

Điểm chính là domain cung cấp phương thức có ý nghĩa, ví dụ `changeCustomerAndQuantity(...)`, thay vì cho bộ binder ghi trực tiếp vào mọi field của entity. Một API dùng constructor binding/record cho request có thể giúp giới hạn bề mặt đầu vào; service vẫn giữ quyền quyết định thay đổi nghiệp vụ.

### Vì sao setter của entity có thể đặc biệt nguy hiểm?

Nếu bind trực tiếp vào một **JPA managed entity**, setter có thể sửa trạng thái đang được persistence context theo dõi. Khi transaction commit và flush, các field đã đổi có thể được lưu. Nếu request có một field sai nhưng code xử lý lỗi không đúng và transaction vẫn commit, trạng thái bất ngờ có thể được ghi. Ngay cả khi DB rollback, tác dụng phụ ngoài DB trước đó vẫn có thể xảy ra.

Do đó không bind dữ liệu chưa tin cậy trực tiếp vào entity có `role`, `status`, `price`, `balance`, `isAdmin` hoặc quan hệ lồng phức tạp. DTO chuyên biệt và mapping có chủ đích giúp kiểm soát quyền ghi, tách validation từ nghiệp vụ và làm test dễ dự đoán hơn.

## 9. Hạn chế property mà BeanWrapper/DataBinder được phép ghi

`BeanWrapperImpl` trực tiếp là API truy cập property; không mặc định biết một HTTP client chỉ được phép sửa những field nào. `DataBinder` hỗ trợ `setAllowedFields(...)` cho **property binding**.

Ví dụ một controller Spring MVC đã có một request DTO `OrderInput` với property `customer` và `quantity`:

~~~java
@InitBinder("orderInput")
void configureBinding(WebDataBinder binder) {
    binder.setAllowedFields("customer", "quantity");
}
~~~

Đây là mảnh code nằm trong controller, cần các import `org.springframework.web.bind.annotation.InitBinder` và `org.springframework.web.bind.WebDataBinder`; tên `orderInput` phải khớp tên model attribute thực tế. Hạn chế field giúp tránh các thuộc tính không được phép như `role` hay `internalStatus` nếu chúng có mặt trên target. **Không nên giải quyết bằng việc mặc nhiên bỏ qua mọi field không quen thuộc** khi API cần báo lỗi field không được phép; cân nhắc kiểm `BindingResult.getSuppressedFields()` theo contract.

Có thể cấu hình:

~~~java
binder.setDeclarativeBinding(true);
binder.setAllowedFields("customer", "quantity");
~~~

Đây là mảnh code cho Spring Framework 6.1+; với declarative binding, constructor binding được hỗ trợ theo contract, còn property binding chỉ được thực hiện khi khai báo trường cho phép. Cần kiểm version và cách framework tạo target cho use case; `setAllowedFields` chỉ là whitelist property path, **không phải cơ chế đảm bảo setter an toàn**, không ngăn getter/setter có side effect trên field hợp lệ.

### Nested property và collection

Spring cho phép path như:

| Path | Ý nghĩa |
| --- | --- |
| `name` | Ghi property đơn |
| `address.city` | Đi qua object lồng và ghi property `city` |
| `lines[0].quantity` | Ghi quantity của phần tử đầu tiên trong list/array |
| `attributes[theme]` | Ghi một entry trong map |

Điều này mở rộng bề mặt thay đổi: một field input có thể chạm tới object lồng, làm phát sinh getter/setter ở nhiều cấp hoặc kích hoạt **auto-grow** tùy cấu hình. `DataBinder.setAutoGrowNestedPaths(true)` có thể khởi tạo object trung gian khi path null và mở rộng collection trong giới hạn. Cơ chế đó giúp form phức tạp tiện dùng, nhưng có thể khiến nhiều object trong graph bị tạo/thay đổi chỉ vì một tên field.

Đối với input không tin cậy, hãy:

- Sử dụng DTO chỉ phơi bày cấu trúc cần thiết.
- Whitelist cụ thể property path hợp lệ; xem xét cấu hình auto-grow và giới hạn collection.
- Tránh cho client điều khiển các quan hệ domain hoặc index/map key không giới hạn.
- Giới hạn kích thước dữ liệu và kiểm tài nguyên ở boundary.
- Kiểm permission riêng trong service; biết một field “writable” không tương đương người dùng được sửa nó.

## 10. Direct field access có giải quyết được vấn đề không?

`DataBinder.initDirectFieldAccess()` chuyển sang cơ chế ghi field trực tiếp thay vì gọi JavaBean setter. Trong một mô hình dữ liệu thụ động, việc này có thể tránh logic đặt trong setter. Nhưng nó **không tự bảo đảm invariant**:

- Guard trong `setQuantity(...)` có thể hoàn toàn bị bỏ qua.
- Giá trị âm hoặc các field không nhất quán có thể được ghi thẳng vào object.
- Một trường domain thiết kế chỉ có private field không có nghĩa field ấy an toàn để bind trực tiếp từ input.
- Những kiểm tra sau binding vẫn không có tính rollback tự động nếu caller giữ object đã bị thay đổi.
- Các hành vi ngoài setter (ví dụ persistence dirty checking) vẫn cần được xem xét.

Vì vậy “bỏ qua setter cho khỏi tác dụng phụ” chỉ là đổi cơ chế truy cập. Với dữ liệu cần invariant, hãy dùng boundary DTO, constructor/validation phù hợp, rồi gọi domain method rõ ràng. Direct-field binding hữu ích trong một số mô hình dữ liệu được kiểm soát, nhưng không phải cách chung để bảo vệ domain.

## 11. Validation không xóa tác dụng phụ của binding

Với một `DataBinder` dùng tường minh:

~~~java
DataBinder binder = new DataBinder(form, "form");
binder.setValidator(validator);
binder.bind(values);
binder.validate();

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Có thể form đã bị setter làm thay đổi một phần.
}
~~~

Đây là mảnh code với `form`, `validator` và `values` đã được tạo trước. `bind(...)` chạy các gán property trước; `validate()` chạy Spring `Validator` sau khi giá trị đã được bind. Việc ghi `FieldError` hoặc `ObjectError` chỉ mô tả lỗi, không bảo đảm hoàn tác mọi setter đã gọi.

Bean Validation annotation như `@NotBlank`, `@Min` và `@Valid` cũng không tự khóa mọi setter khi framework tạo object. Với Spring MVC, việc kích hoạt validation phụ thuộc loại tham số và cấu hình; ví dụ `@Valid @ModelAttribute` trên DTO có thể validate sau binding. Với JSON `@RequestBody`, Jackson thường deserialize trước validation, theo cơ chế khác; Jackson có thể sử dụng setter nếu DTO được thiết kế như JavaBean, nhưng đường đi không nhất thiết qua `BeanWrapperImpl`.

**Kiểm tra giá trị chưa đủ:** nếu setter phát email hoặc domain event trong `bind()`, validation thất bại ở bước sau không xóa được email/event ấy. Hãy tránh cho các tác vụ này nằm trong setter của đối tượng nhận dữ liệu thô.

### Binder ghi nhận lỗi khác với gọi BeanWrapper trực tiếp

| Công cụ | Phản ứng thường gặp khi có lỗi |
| --- | --- |
| `BeanWrapperImpl.setPropertyValue(...)` | Có thể ném `BeansException` hoặc subclass tương ứng ngay tại lời gọi |
| `BeanWrapperImpl.setPropertyValues(...)` | Có thể thu thập lỗi truy cập property có thể phục hồi; các giá trị được gán thành công vẫn thay đổi |
| `DataBinder.bind(...)` | Ghi những lỗi binding phù hợp vào `BindingResult`, có cấu hình allowed/required field |
| `DataBinder.validate()` | Gọi validator đã đăng ký để bổ sung lỗi, không undo các setter |
| `DataBinder.close()` | Trả model nếu không lỗi hoặc ném `BindException` nếu kết quả có lỗi; không rollback |

Có trường hợp lỗi nghiêm trọng hoặc exception bên ngoài cơ chế ghi `BindingResult` được ném ngay; không khẳng định mọi exception được deferred. Cũng không dùng `close()` như `AutoCloseable.close()` hay thao tác commit transaction.

## 12. Setter thuần dữ liệu và phương thức nghiệp vụ

Một setter phù hợp cho **DTO đơn giản** thường chỉ cập nhật property, không gọi external IO và không tự phát domain event. Domain object có invariant nên thể hiện các thao tác có chủ đích:

| Thiết kế | Ưu điểm/hạn chế |
| --- | --- |
| Setter nhận mọi field và tự gửi sự kiện | Dễ viết ban đầu nhưng bất ngờ khi reflection/binding gọi, khó kiểm soát số lần và thời điểm |
| Setter chỉ gán field của DTO | Dễ bind; validation tập trung, có thể bỏ hoặc sửa các field không hợp lệ trước khi map |
| Setter có guard cục bộ của domain | Có thể bảo vệ field đơn nhưng cần cân nhắc thay đổi nhiều field và thứ tự setter |
| Domain method `reschedule(start, end)` | Có toàn bộ dữ liệu cho invariant liên thuộc, rõ ý định và test dễ hơn |
| Immutable value object/record | Hạn chế trạng thái trung gian có thể quan sát; constructor/factory kiểm invariant |
| Service transaction + outbox/event sau commit | Tổ chức mutation và side effect theo ranh giới nhất quán đã chọn |

Khi setter là API công khai của domain, một lớp ngoài có thể gọi nó ngoài bối cảnh controller. **Đừng phụ thuộc vào annotation của request để bảo vệ invariant cốt lõi**; domain/service vẫn phải kiểm điều kiện của nó trước khi đổi trạng thái.

### Trường hợp side effect thật sự là yêu cầu nghiệp vụ

Một lệnh “đổi địa chỉ giao hàng” có thể phải phát event. Thay vì `setAddress(...)` âm thầm phát message, domain/service có thể:

1. Nhận `ChangeShippingAddressCommand` đã được kiểm tra định dạng.
2. Kiểm trạng thái đơn, quyền người gọi và địa chỉ mới.
3. Gọi `order.changeShippingAddress(newAddress)`.
4. Ghi thay đổi và một outbox record trong cùng transaction nếu hệ thống dùng outbox.
5. Worker khác gửi message từ outbox với xử lý retry/deduplication.

Cách này tách **ý định thay đổi nghiệp vụ** khỏi số lần một binder hoặc serializer gọi setter. Nó cũng giúp test rõ lúc nào event được phát, và cách xử lý khi commit/retry thất bại.

## 13. Những lỗi phổ biến

1. **Cho rằng setter luôn là phép gán đơn giản.** Setter là method Java; phải kiểm code và side effect trước khi cho binder tự gọi.
2. **Cho rằng mọi field được áp dụng atomically.** `setPropertyValues(...)` có thể để lại những field đã gán thành công trước khi phát hiện lỗi khác.
3. **Đưa logic email, network, publish message vào setter DTO.** Validation thất bại sau binding vẫn có thể để lại hành động không thể undo.
4. **Kiểm invariant liên thuộc trong nhiều setter độc lập.** Thứ tự set property có thể quyết định success/failure hoặc tạo trạng thái trung gian. Dùng domain method nhận đủ giá trị.
5. **Ném exception sau khi đã mutate object.** Lỗi không phục hồi object tự động; luôn kiểm điều kiện cần thiết trước khi thay đổi state khi có thể.
6. **Cho rằng cùng giá trị sẽ không gọi setter lần nữa.** Framework/consumer có thể gọi lại; nếu cần idempotency phải thiết kế rõ và kiểm soát ở tầng đúng.
7. **Tin rằng `@Valid` bảo vệ các side effect trong quá trình binding.** Validation có thể chạy sau setter; không phải cơ chế transaction hoặc rollback.
8. **Bind HTTP request trực tiếp vào JPA entity.** Dễ mass assignment hoặc sửa field đang được theo dõi persistence; tách DTO và domain change.
9. **Dùng `initDirectFieldAccess()` để lách invariant.** Bỏ qua setter cũng bỏ qua guard trong setter; không tự làm domain an toàn.
10. **Cho phép nested path quá rộng.** `address.city`, indexed collection và auto-grow có thể thay đổi nhiều object; hạn chế allowed paths và kích thước input.
11. **Giả định `BeanWrapper.isWritableProperty()` là kiểm tra authorization.** API đó chỉ xét khả năng truy cập property.
12. **Chỉ kiểm tra return value, không kiểm tra side effect.** Test phải quan sát trạng thái target, số lần gọi setter, event/outbox và lỗi khi từng field thất bại.
13. **Mặc định DB rollback sẽ thu hồi email hoặc HTTP request.** Cần thiết kế phát side effect theo transaction boundary và cơ chế retry/deduplication thích hợp.
14. **Gán domain transaction vào mọi setter.** Một loạt setter lẻ không thể hiện đúng ý định aggregate và làm khó kiểm soát invariant.

## 14. Bài tập và kiểm thử đề xuất

### Bài tập 1: Thay đổi trạng thái một phần

Dùng ví dụ `SetterEffectsDemo` rồi thay dòng `changes.add("quantity", -5)` bằng `changes.add("quantity", 3)`. Dự đoán `batchFailed`, `quantity`, `setterCalls` và `notifications`; chạy kiểm. Sau đó thay setter `setQuantity` bằng biến thể gán trước, kiểm tra sau; phân tích vì sao exception có thể xuất hiện khi state đã bị thay đổi.

### Bài tập 2: Thứ tự setter và invariant

Dùng class `Range`, thử hai thứ tự để chuyển trạng thái từ `[1, 5]` sang `[7, 9]`:

- Thứ tự A: `setStart(7)` rồi `setEnd(9)`.
- Thứ tự B: `setEnd(9)` rồi `setStart(7)`.

Bắt exception riêng cho từng lời gọi và in `start/end` cuối cùng. Sau đó triển khai `changeRange(7, 9)` rồi so sánh tính nhất quán khi hai giá trị được kiểm đồng thời.

### Bài tập 3: Whitelist field đầu vào

Tạo DTO có `customer`, `quantity` và `internalStatus`. Bind bằng `DataBinder` với `setAllowedFields("customer", "quantity")`, gửi input có thêm `internalStatus` và kiểm `getBindingResult().getSuppressedFields()`. Xác nhận trạng thái nội bộ không đổi và thử phân biệt tình huống bị suppression với `FieldError` do type mismatch.

### Checklist kiểm thử cho mã production

| Kiểm thử | Cần khẳng định |
| --- | --- |
| Một property hợp lệ | Setter nhận đúng giá trị, side effect theo contract |
| Gán cùng giá trị hai lần | Side effect có hoặc không lặp đúng chủ đích |
| Field A hợp lệ, field B lỗi | Xác định A có bị đổi không; không giả định rollback |
| Setter tự ném trước/sau khi gán | Object không bị để lại trạng thái không hợp lệ ngoài ý muốn |
| Cross-field update theo hai thứ tự | Bất biến không phụ thuộc thứ tự input |
| Lỗi chuyển kiểu | Phân biệt setter chưa được gọi với các setter trước đã chạy |
| Validation lỗi sau bind | Không phát event/email hoặc lưu state không hợp lệ |
| Nested/indexed property | Không vượt allowed paths và giới hạn collection |
| Request có field đặc quyền | Bị từ chối/suppressed; không thay đổi quyền hoặc status |
| Transaction thất bại hoặc retry | Side effect được phát/khử trùng đúng chính sách, không tạo sự kiện sai |

**Kết quả mong muốn:** hệ thống chỉ biến đổi domain sau khi đã biết dữ liệu đầu vào nào được phép, kiểm được toàn bộ invariant cần thiết và quyết định rõ thời điểm phát side effect. `BeanWrapper` là công cụ truy cập property hữu ích, nhưng an toàn của setter và nghiệp vụ vẫn là trách nhiệm của thiết kế đối tượng.

## Tài liệu tham khảo chính thức

- [Spring Framework — Data Binding (BeanWrapper, property binding, constructor binding)](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Spring MVC Data Binding / Model Design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework 6.2 — BeanWrapperImpl Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework 6.2 — BeanWrapper Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/beans/BeanWrapper.html)
- [Spring Framework 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
