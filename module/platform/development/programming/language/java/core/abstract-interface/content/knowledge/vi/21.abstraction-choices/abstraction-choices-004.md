# Kết hợp interface công khai với lớp trừu tượng hỗ trợ tùy chọn

Khi thiết kế API Java, thường nên công bố một **interface mô tả hợp đồng** và cung cấp thêm một **abstract class làm lớp hỗ trợ tùy chọn**. Người dùng API có thể triển khai interface trực tiếp nếu muốn tự kiểm soát toàn bộ hành vi, hoặc kế thừa lớp trừu tượng để tái sử dụng phần triển khai chung.

Cách thiết kế này tách biệt hai quyết định: *một đối tượng phải làm được gì* và *một triển khai có thể tái sử dụng hành vi đó như thế nào*. Mã gọi API chỉ cần phụ thuộc vào interface; abstract class đóng vai trò một lựa chọn tiện lợi, không phải điều kiện bắt buộc.

## 1. Interface công khai định nghĩa hợp đồng

Interface nên mô tả những thao tác mà người dùng API được phép gọi và những điều kiện có ý nghĩa đối với các thao tác đó. Hợp đồng cần tập trung vào hành vi quan sát được: đầu vào, kết quả, lỗi có thể xảy ra và các bảo đảm mà mọi triển khai phải đáp ứng.

Ví dụ, một bộ kết xuất văn bản có thể được mô tả bằng interface:

```java
interface TextRenderer {
    String render(String text);
}
```

Đoạn mã sử dụng bộ kết xuất chỉ cần biết kiểu `TextRenderer` và gọi `render`. Nó không cần biết đối tượng là một lớp viết trực tiếp từ interface hay một lớp kế thừa abstract class.

```java
static void show(TextRenderer renderer, String value) {
    System.out.println(renderer.render(value));
}
```

Đây là điểm quan trọng của hợp đồng công khai: người gọi dựa vào khả năng mà interface cam kết, thay vì phụ thuộc vào một lớp triển khai cụ thể.

## 2. Abstract class cung cấp phần triển khai dùng chung

Interface ở trên chỉ định nghĩa thao tác `render`. Một lớp trừu tượng có thể cung cấp thuật toán chung và để các lớp con tùy chỉnh một bước nhỏ thông qua phương thức móc (hook) được khai báo `protected`.

Mẫu này thường được gọi là **skeletal implementation** khi abstract class giúp giảm lượng mã mà người triển khai phải viết. Khi lớp cơ sở kiểm soát thứ tự thực hiện các bước, đây cũng là một dạng của **Template Method**.

```java
import java.util.Objects;

abstract class AbstractTextRenderer implements TextRenderer {
    @Override
    public final String render(String text) {
        Objects.requireNonNull(text, "text");
        return "[" + renderContent(text.trim()) + "]";
    }

    protected abstract String renderContent(String normalizedText);
}
```

Lớp cơ sở thực hiện các bước chung: từ chối đầu vào `null`, loại bỏ khoảng trắng ở hai đầu, rồi bao kết quả bằng dấu ngoặc vuông. Phương thức `renderContent` là điểm tùy biến dành cho lớp con.

Từ khóa `final` trên `render` bảo đảm lớp con không thay đổi thứ tự của thuật toán chung. Đây là một quyết định thiết kế có chủ đích: nó phù hợp khi quy trình cần được giữ ổn định, nhưng không phù hợp nếu mỗi lớp con cần tự định nghĩa toàn bộ quy trình `render`.

## 3. Cả hai cách triển khai đều hợp lệ

Lớp sử dụng interface có thể tự triển khai hợp đồng mà không cần kế thừa abstract class:

```java
import java.util.Objects;

class DirectRenderer implements TextRenderer {
    @Override
    public String render(String text) {
        Objects.requireNonNull(text, "text");
        return text.trim();
    }
}
```

Hoặc có thể kế thừa lớp hỗ trợ và chỉ cung cấp bước còn thiếu:

```java
import java.util.Locale;

class UppercaseBracketRenderer extends AbstractTextRenderer {
    @Override
    protected String renderContent(String normalizedText) {
        return normalizedText.toUpperCase(Locale.ROOT);
    }
}
```

Cả hai đối tượng đều là `TextRenderer`. Lớp gọi không cần kiểm tra kiểu lớp cụ thể hoặc có hai nhánh xử lý khác nhau.

## 4. Ví dụ hoàn chỉnh có thể chạy

Lưu tất cả mã sau trong tệp `InterfaceAndAbstractSupportDemo.java`. Các interface và lớp hỗ trợ không có từ khóa `public` nên có thể nằm cùng tệp với lớp công khai:

```java
import java.util.Locale;
import java.util.Objects;

interface TextRenderer {
    String render(String text);
}

abstract class AbstractTextRenderer implements TextRenderer {
    @Override
    public final String render(String text) {
        Objects.requireNonNull(text, "text");
        return "[" + renderContent(text.trim()) + "]";
    }

    protected abstract String renderContent(String normalizedText);
}

class DirectRenderer implements TextRenderer {
    @Override
    public String render(String text) {
        Objects.requireNonNull(text, "text");
        return text.trim();
    }
}

class UppercaseBracketRenderer extends AbstractTextRenderer {
    @Override
    protected String renderContent(String normalizedText) {
        return normalizedText.toUpperCase(Locale.ROOT);
    }
}

public class InterfaceAndAbstractSupportDemo {
    private static void show(TextRenderer renderer, String value) {
        System.out.println(renderer.render(value));
    }

    public static void main(String[] args) {
        TextRenderer direct = new DirectRenderer();
        TextRenderer supported = new UppercaseBracketRenderer();

        show(direct, " Java ");
        show(supported, " Java ");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```text
javac -encoding UTF-8 InterfaceAndAbstractSupportDemo.java
java InterfaceAndAbstractSupportDemo
```

Kết quả chuẩn:

```text
Java
[JAVA]
```

Dòng đầu cho thấy triển khai trực tiếp có thể tự chọn cách xử lý. Dòng thứ hai cho thấy lớp kế thừa tái sử dụng quy trình chung của abstract class và chỉ cung cấp phần định dạng nội dung.

Trong thiết kế thực tế, các kiểu và phương thức của API công khai thường được đặt trong những tệp riêng. Ví dụ trên gom chúng vào một tệp để người học có thể biên dịch và chạy ngay mà không cần cấu hình dự án.

## 5. Vì sao abstract class nên là tùy chọn?

Java chỉ cho phép một lớp kế thừa trực tiếp từ một lớp khác. Nếu API bắt buộc mọi triển khai phải kế thừa một abstract class, người dùng có thể không còn khả năng kế thừa lớp khác phù hợp với thiết kế của họ.

Khi interface là hợp đồng chính, người dùng có thể lựa chọn:

- **Triển khai trực tiếp:** phù hợp khi hành vi khác biệt, cần kế thừa một lớp khác, hoặc phần hỗ trợ không phù hợp.
- **Kế thừa abstract class:** phù hợp khi muốn dùng lại thuật toán, trạng thái, constructor hoặc các phương thức hỗ trợ đã được cung cấp.
- **Kết hợp với một lớp cơ sở riêng:** nếu có thể kế thừa một lớp khác, người dùng vẫn có thể triển khai interface công khai và tự tổ chức phần mã dùng chung.

Nhờ giữ abstract class là tùy chọn, API có thể cung cấp tiện ích mà không chiếm mất quyền lựa chọn cấu trúc lớp của người dùng.

## 6. Interface có `default` method thì khác gì?

Interface Java có thể cung cấp phương thức `default` để chia sẻ một hành vi đơn giản ngay trong hợp đồng. Cách này hữu ích khi hành vi không cần trạng thái của đối tượng hoặc không cần một hệ thống hook phức tạp.

Ví dụ:

```java
interface Named {
    String name();

    default boolean hasName() {
        return name() != null && !name().isBlank();
    }
}
```

Mọi triển khai `Named` đều nhận được `hasName` nếu không ghi đè phương thức đó. Tuy nhiên, `default` method không thay thế mọi vai trò của abstract class. Abstract class có thể có constructor, trường instance, các phương thức `protected` và một chuỗi bước triển khai có thể tái sử dụng.

Một quy tắc thực tế:

- Dùng interface để công bố hợp đồng và các phương thức `default` nhỏ khi hành vi chung thực sự phù hợp với mọi triển khai.
- Dùng abstract class khi cần một triển khai nền có trạng thái, constructor, phương thức hỗ trợ hoặc Template Method.
- Giữ lớp trừu tượng là tùy chọn nếu người dùng không cần phải kế thừa nó để đáp ứng hợp đồng.

Không nên thêm một abstract class chỉ để bọc lại interface mà không cung cấp giá trị dùng chung thực tế.

## 7. Giữ hợp đồng công khai ổn định

Interface công khai là điểm phụ thuộc của mã khách hàng. Việc thêm một phương thức abstract mới có thể làm các lớp triển khai hiện tại không còn biên dịch được cho đến khi chúng triển khai phương thức đó.

Một abstract class hỗ trợ có thể giảm công việc cho những lớp kế thừa nó nếu lớp cơ sở cung cấp triển khai phù hợp cho phương thức mới. Tuy nhiên, các lớp triển khai interface trực tiếp vẫn phải tuân theo hợp đồng mới. Vì vậy, không thể xem abstract class là cách tự động bảo đảm tương thích ngược cho mọi khách hàng.

Khi phát triển API đã được sử dụng rộng rãi:

1. Chỉ thêm thao tác công khai khi nó thực sự thuộc hợp đồng của interface.
2. Cân nhắc liệu một phương thức `default` có thể cung cấp hành vi tương thích hay không.
3. Nếu cần hỗ trợ triển khai trực tiếp, hãy xác định rõ cách hành vi mới hoạt động với các triển khai hiện hữu.
4. Nếu có abstract class hỗ trợ, hãy cập nhật nó một cách nhất quán nhưng vẫn xem các triển khai trực tiếp là một phần của API.
5. Kiểm thử cả lớp kế thừa abstract class và lớp triển khai interface trực tiếp.

Phương thức `default` cũng cần được thiết kế cẩn thận: thêm phương thức có chữ ký trùng hoặc xung đột với interface khác có thể gây xung đột khi kết hợp nhiều interface. Không nên thêm mặc định chỉ để tránh suy nghĩ về hợp đồng.

## 8. Những lỗi thiết kế thường gặp

- **Ép mọi người dùng phải kế thừa abstract class:** điều này giới hạn khả năng kế thừa đơn của Java và khiến lớp hỗ trợ trở thành ràng buộc không cần thiết.
- **Cho mã gọi phụ thuộc vào lớp hỗ trợ:** khi có thể, hãy nhận tham số bằng interface công khai để triển khai trực tiếp và triển khai dựa trên abstract class đều sử dụng được.
- **Đưa toàn bộ hành vi vào interface dù cần trạng thái hoặc hook:** hãy xem xét abstract class nếu thuật toán chung cần trường instance, constructor hoặc các bước tùy biến có kiểm soát.
- **Dùng abstract class mà không có phần tái sử dụng đáng kể:** nếu lớp chỉ lặp lại chữ ký interface, nó có thể làm API phức tạp mà không giúp người dùng.
- **Cho rằng abstract class tự bảo đảm tương thích ngược:** thay đổi hợp đồng interface vẫn ảnh hưởng đến các triển khai trực tiếp.
- **Để lớp con ghi đè một bước phải được giữ nguyên:** nếu thuật toán cần bảo toàn thứ tự, cân nhắc phương thức điều phối `final` và các hook `protected` rõ ràng; chỉ dùng cách này khi hạn chế ghi đè là yêu cầu thật sự.

## 9. Quy trình lựa chọn

Trước tiên, xác định những thao tác mà mọi đối tượng cần cung cấp và công bố chúng qua interface. Sau đó, tìm phần thuật toán hoặc trạng thái nào có thể dùng chung. Nếu phần dùng chung đơn giản và không cần trạng thái, phương thức `default` có thể đủ. Nếu cần constructor, trạng thái, hook hoặc một thuật toán khung, hãy cung cấp abstract class triển khai interface đó.

Cuối cùng, bảo đảm mã khách hàng có thể làm việc thông qua interface và không phải biết lớp hỗ trợ có được sử dụng hay không. Kiểm thử cả hai đường triển khai để xác nhận chúng đáp ứng cùng hợp đồng.

Kết hợp interface công khai với abstract class tùy chọn cho phép API vừa giữ được hợp đồng rõ ràng, vừa cung cấp mã dùng chung hữu ích. Interface xác định cách người dùng tương tác; abstract class giảm công sức triển khai khi phù hợp, đồng thời để những người dùng khác tự chọn cách hiện thực hợp đồng.