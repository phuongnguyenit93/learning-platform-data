# Thêm default method và nguy cơ xung đột kế thừa

Từ Java 8, interface có thể khai báo **default method**: một phương thức instance có phần thân triển khai mặc định. Tính năng này giúp mở rộng hợp đồng interface bằng hành vi dùng chung mà không bắt buộc mọi lớp triển khai phải tự viết phương thức mới ngay lập tức.

Tuy nhiên, một lớp có thể triển khai nhiều interface và một interface có thể kế thừa từ nhiều interface khác. Khi các nguồn đó cung cấp những default method có chữ ký tương đương, Java cần xác định triển khai nào được sử dụng. Nếu không có quy tắc ưu tiên rõ ràng, chương trình có thể gặp xung đột ở thời điểm biên dịch; việc thêm default method vào một API đã được sử dụng cũng có thể làm lộ ra xung đột trước đó chưa tồn tại.

## 1. Default method là gì?

Một default method là phương thức instance được khai báo bằng từ khóa `default` trong interface. Phương thức này có thân và mặc định là `public`. Nó khác với phương thức `static` của interface: static method được gọi qua tên interface và không được lớp triển khai kế thừa như một phương thức instance.

```java
interface Identifiable {
    String id();

    default boolean hasId() {
        return id() != null && !id().isBlank();
    }
}
```

Lớp triển khai `Identifiable` chỉ cần cung cấp `id()`; nó có thể dùng ngay `hasId()` hoặc ghi đè phương thức này nếu hợp đồng cho phép và có lý do hợp lý.

Default method hữu ích khi:

- Một hành vi nhỏ có ý nghĩa chung với hầu hết hoặc tất cả triển khai của interface.
- API cần được mở rộng mà không buộc mọi lớp triển khai cũ phải bổ sung một phương thức abstract mới.
- Hành vi mặc định có thể được mô tả chính xác từ các thao tác đã có trong hợp đồng.

Không nên thêm default method chỉ vì muốn tránh viết mã. Hành vi mặc định phải đúng về mặt ngữ nghĩa đối với các triển khai mà interface đại diện.

## 2. Java chọn default method nào?

Khi nhiều kiểu cung cấp phương thức cùng chữ ký, hãy xét các quy tắc chính sau theo thứ tự.

### 2.1. Phương thức instance từ lớp thắng default method của interface

Nếu lớp hoặc lớp cha cung cấp phương thức instance phù hợp, phương thức đó được ưu tiên hơn default method. Điều này bảo toàn mô hình kế thừa lớp của Java.

```java
interface Greeting {
    default String greet() {
        return "Greeting";
    }
}

class BaseGreeter {
    public String greet() {
        return "BaseGreeter";
    }
}

class ClassWinsGreeter extends BaseGreeter implements Greeting {
}
```

Gọi `new ClassWinsGreeter().greet()` trả về `"BaseGreeter"`. Lớp không cần ghi đè phương thức chỉ để giải quyết default method của `Greeting`.

Quy tắc này không có nghĩa là mọi phương thức cùng tên đều thay thế được nhau: chữ ký, kiểu trả về và khả năng truy cập vẫn phải tương thích theo quy tắc Java. Phương thức static cũng không tham gia cơ chế ghi đè instance này.

### 2.2. Interface cụ thể hơn thắng interface cha

Nếu một subinterface ghi đè default method của superinterface, triển khai từ subinterface cụ thể hơn được ưu tiên.

```java
interface GeneralGreeting {
    default String greet() {
        return "General";
    }
}

interface FormalGreeting extends GeneralGreeting {
    @Override
    default String greet() {
        return "Formal";
    }
}

class FormalGreeter implements FormalGreeting {
}
```

`FormalGreeter` dùng `FormalGreeting.greet()` và nhận `"Formal"`. Đây không phải xung đột giữa hai default độc lập: quan hệ kế thừa cho biết rõ phương thức nào cụ thể hơn.

### 2.3. Hai interface không liên quan cùng khai báo default sẽ gây xung đột

Nếu hai interface không có quan hệ kế thừa cung cấp default method cùng chữ ký, Java không tự chọn interface được viết trước, được liệt kê trước hay có tên nào đó. Lớp cụ thể cần ghi đè phương thức và xác định hành vi mong muốn.

```java
interface LeftGreeting {
    default String greet() {
        return "Left";
    }
}

interface RightGreeting {
    default String greet() {
        return "Right";
    }
}

// Không biên dịch nếu bỏ phần ghi đè greet():
// class BrokenGreeter implements LeftGreeting, RightGreeting { }

class ResolvedGreeter implements LeftGreeting, RightGreeting {
    @Override
    public String greet() {
        return LeftGreeting.super.greet()
                + " + "
                + RightGreeting.super.greet();
    }
}
```

Cú pháp `LeftGreeting.super.greet()` gọi trực tiếp triển khai default của một superinterface trực tiếp. Nó hữu ích khi hai cách triển khai đều có ý nghĩa và lớp muốn kết hợp chúng. Nếu hai hành vi không thể kết hợp hợp lý, hãy viết một triển khai riêng thay vì gọi cả hai chỉ để làm trình biên dịch hết báo lỗi.

Lớp hoặc interface kết hợp các interface xung đột phải xử lý xung đột một cách tường minh. Đừng dựa vào thứ tự liệt kê tên interface để dự đoán kết quả.

## 3. Ví dụ hoàn chỉnh chạy được

Lưu đoạn mã sau trong tệp `DefaultMethodConflictDemo.java`. Ví dụ minh họa cả ba quy tắc: subinterface cụ thể hơn, phương thức lớp thắng default và lớp chủ động giải quyết hai default không liên quan.

```java
interface Greeting {
    default String greet() { return "Greeting"; }
}

interface FormalGreeting extends Greeting {
    @Override
    default String greet() { return "FormalGreeting"; }
}

class SpecificGreeting implements FormalGreeting { }

class BaseGreeter {
    public String greet() { return "BaseGreeter"; }
}

class ClassWinsGreeter extends BaseGreeter implements Greeting { }

interface LeftGreeting {
    default String greet() { return "Left"; }
}

interface RightGreeting {
    default String greet() { return "Right"; }
}

class ResolvedGreeter implements LeftGreeting, RightGreeting {
    @Override
    public String greet() {
        return LeftGreeting.super.greet() + " + " + RightGreeting.super.greet();
    }
}

public class DefaultMethodConflictDemo {
    public static void main(String[] args) {
        System.out.println(new SpecificGreeting().greet());
        System.out.println(new ClassWinsGreeter().greet());
        System.out.println(new ResolvedGreeter().greet());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```text
javac -encoding UTF-8 DefaultMethodConflictDemo.java
java DefaultMethodConflictDemo
```

Kết quả chuẩn:

```text
FormalGreeting
BaseGreeter
Left + Right
```

Kết quả cho thấy Java không chọn ngẫu nhiên một default method: nó ưu tiên khai báo cụ thể hơn trong cây interface, ưu tiên phương thức instance của lớp, và yêu cầu giải quyết tường minh khi hai default không liên quan xung đột.

## 4. Vì sao thêm default method vẫn có thể phá vỡ API?

Giả sử phiên bản đầu của thư viện có interface `Auditable` và `Displayable`, trong đó chưa interface nào khai báo `label()`. Một lớp khách hàng có thể triển khai cả hai mà không gặp vấn đề.

Ở phiên bản sau, thư viện thêm default `label()` vào `Auditable`. Nếu một phiên bản khác của thư viện hoặc interface mà lớp khách hàng sử dụng cũng cung cấp default `label()` trong `Displayable`, lớp có thể rơi vào xung đột giữa hai default không liên quan. Khi biên dịch lại, mã có thể không biên dịch cho đến khi lớp ghi đè phương thức để chọn hành vi.

Điều này có nghĩa là:

- Thêm default method thường ít gây gánh nặng cho lớp triển khai hơn so với thêm phương thức abstract mới.
- “Có phần thân mặc định” không đồng nghĩa với “luôn tương thích trong mọi hệ thống phân cấp”.
- Một phương thức mới có thể va chạm với default method từ interface khác hoặc với phương thức đã tồn tại trong các lớp khách hàng.
- Thay đổi thư viện cần được kiểm tra với những tổ hợp interface thực tế, không chỉ với một lớp triển khai đơn giản.

Khi phát hành thư viện dùng chung, cần xem xét cả tương thích mã nguồn lẫn tương thích nhị phân. Những tổ hợp đã biên dịch trước đó không nên được mặc nhiên coi là an toàn trong mọi trường hợp sau khi interface thay đổi; hãy kiểm thử các cấu hình triển khai được hỗ trợ và xác minh hành vi ở runtime khi có nhiều phiên bản thư viện liên quan.

## 5. Quy trình xử lý xung đột

Khi compiler báo một lớp kế thừa các default không liên quan cùng chữ ký, hãy thực hiện theo trình tự:

1. **Xác định chính xác chữ ký xung đột.** Kiểm tra tên phương thức, tham số, kiểu trả về và các interface mà lớp triển khai trực tiếp hoặc kế thừa.
2. **Tìm quan hệ kế thừa giữa các interface.** Nếu một khai báo đến từ subinterface cụ thể hơn, đó có thể là trường hợp đã có quy tắc ưu tiên.
3. **Kiểm tra lớp cha.** Xem có phương thức instance tương thích nào trong lớp hoặc lớp cha hay không; phương thức lớp thường được ưu tiên hơn default.
4. **Quyết định hợp đồng mong muốn.** Chọn một default, kết hợp các triển khai nếu có ý nghĩa, hoặc viết hành vi riêng.
5. **Ghi đè rõ ràng tại nơi phù hợp.** Với lớp cụ thể, dùng phương thức public có chữ ký tương thích. Nếu thiết kế một subinterface hợp nhất, hãy định nghĩa lại default ở interface đó để mọi lớp con nhận được một quyết định thống nhất.
6. **Biên dịch và kiểm thử.** Kiểm tra các lớp triển khai trực tiếp, các lớp dùng lớp cơ sở và những tổ hợp interface khác nhau.

Ví dụ khi chỉ muốn chọn một phía:

```java
class LeftOnlyGreeter implements LeftGreeting, RightGreeting {
    @Override
    public String greet() {
        return LeftGreeting.super.greet();
    }
}
```

Không bắt buộc phải gọi `InterfaceName.super`. Một triển khai mới có thể trả về giá trị khác, miễn là vẫn đáp ứng hợp đồng công khai của phương thức.

## 6. Thiết kế default method an toàn hơn

### Giữ phương thức nhỏ và dựa trên hợp đồng đã có

Một default method thường nên phối hợp các phương thức công khai hiện hữu, cung cấp truy vấn tiện ích hoặc thực hiện một hành vi đơn giản. Tránh tạo mặc định mà ý nghĩa chỉ đúng với một vài lớp triển khai.

### Cẩn thận với tên và chữ ký phổ biến

Những tên chung như `close()`, `name()`, `id()` hoặc `toString()` có thể xuất hiện trong nhiều hệ thống phân cấp. Tên phương thức rõ nghĩa và hợp đồng nhất quán giúp giảm nguy cơ va chạm, dù không thể loại bỏ hoàn toàn xung đột chữ ký.

### Không dùng default method thay cho trạng thái đối tượng

Interface không có trường instance cho từng đối tượng. Nếu hành vi cần trạng thái riêng, constructor, invariant hoặc một thuật toán nền phức tạp, hãy cân nhắc abstract class hoặc một đối tượng cộng tác. Default method nên được giữ ở mức phù hợp với hợp đồng interface.

### Chú ý đến phương thức có sẵn của Object

Default method không thể cung cấp triển khai thay thế cho các phương thức instance công khai của `java.lang.Object` như `toString()`, `equals(Object)` hay `hashCode()` theo cách ghi đè chúng từ interface. Nếu API cần hợp đồng cho các hành vi đó, hãy thiết kế và kiểm thử ở cấp lớp triển khai.

### Không biến ghi đè thành thao tác hình thức

Khi giải quyết xung đột, không nên chỉ gọi một default tùy ý vì nó giúp biên dịch thành công. Hãy xác định hành vi mà người gọi có thể dựa vào và kiểm tra rằng kết quả mới vẫn đúng với hợp đồng của interface.

## 7. Default method và tương thích API

Trước khi thêm một default method vào interface đã công bố, hãy xem xét các câu hỏi sau:

- Phương thức có ý nghĩa đối với mọi triển khai hay chỉ một nhóm triển khai?
- Có phương thức cùng chữ ký ở interface cha, interface độc lập hoặc lớp khách hàng không?
- Nếu hai default xung đột, nơi nào nên chịu trách nhiệm hợp nhất hành vi: interface chuyên biệt hơn hay lớp cụ thể?
- Có thể triển khai hành vi mặc định bằng các phương thức hiện hữu mà không làm thay đổi ngữ nghĩa của chúng không?
- Bộ kiểm thử có bao phủ nhiều interface cùng được triển khai, lớp cha có phương thức trùng chữ ký và các cấu hình thư viện được hỗ trợ không?

Nếu mọi triển khai không có một hành vi mặc định hợp lý, một phương thức abstract mới hoặc một interface mở rộng riêng có thể thể hiện hợp đồng tốt hơn. Nếu default method thực sự là hành vi chung, hãy tài liệu hóa điều kiện, kết quả và xung đột có thể xảy ra.

## 8. Những nhầm lẫn thường gặp

- **Cho rằng interface được liệt kê trước sẽ thắng:** thứ tự khai báo trong mệnh đề `implements` không giải quyết xung đột.
- **Cho rằng mọi default đều thắng phương thức lớp:** phương thức instance tương thích trong lớp hoặc lớp cha được ưu tiên.
- **Nhầm default method với static method:** static method được gọi qua tên interface và không được kế thừa như default instance method.
- **Cho rằng thêm default method luôn an toàn:** có thể phát sinh xung đột với interface khác hoặc với cấu trúc lớp của khách hàng.
- **Gọi `InterfaceName.super` từ bất kỳ interface nào:** cú pháp này chỉ dùng với superinterface trực tiếp phù hợp; không phải cơ chế tra cứu tùy ý mọi interface trong cây kế thừa.
- **Chỉ kiểm tra một lớp triển khai:** xung đột thường chỉ xuất hiện khi nhiều interface được kết hợp trong cùng một kiểu.

## 9. Tóm tắt

Default method giúp tiến hóa interface bằng cách bổ sung hành vi có sẵn, nhưng việc chọn triển khai vẫn tuân theo quy tắc kế thừa của Java. Phương thức instance của lớp được ưu tiên hơn default; khai báo ở subinterface cụ thể hơn được ưu tiên hơn khai báo ở interface cha; hai default không liên quan có cùng chữ ký cần được giải quyết tường minh.

Khi phát triển API, hãy xem default method là một thay đổi hợp đồng cần được đánh giá, không phải một cách tự động bảo đảm tương thích. Xác định rõ hành vi mặc định, kiểm tra các hệ thống phân cấp interface có thể kết hợp, viết ghi đè có chủ đích và chạy kiểm thử trên những cấu hình triển khai quan trọng trước khi phát hành.