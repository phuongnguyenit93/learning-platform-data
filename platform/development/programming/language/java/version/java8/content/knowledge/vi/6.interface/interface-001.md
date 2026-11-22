# Default method và tiến hóa hợp đồng thư viện trong Java 8

## 1. Vì sao Java có default method?

Khi một thư viện xuất bản `interface`, các ứng dụng khác có thể tự viết class `implements` interface đó. Qua các phiên bản, tác giả thư viện muốn bổ sung một hành vi mới mà không bắt mọi class triển khai cũ phải bổ sung mã nguồn ngay.

Từ Java 8, **default method** cho phép interface khai báo phương thức instance có sẵn phần thân. Class triển khai có thể **kế thừa hành vi mặc định** hoặc **override** nó. Đây là một công cụ quan trọng để **tiến hóa hợp đồng (API/library evolution)**, nhưng không đồng nghĩa với việc mọi thay đổi thêm default method đều an toàn tuyệt đối.

Ví dụ một interface ban đầu có:

```java
interface Formatter {
    String format(String input);
}
```

Một phiên bản mới có thể thêm thao tác dựa trên khả năng cũ:

```java
interface Formatter {
    String format(String input);

    default String formatOrMissing(String input) {
        return format(input == null ? "missing" : input);
    }
}
```

Lớp chỉ triển khai `format` vẫn có thể dùng `formatOrMissing`, miễn không gặp xung đột hay điều kiện đặc biệt. Phần thân mặc định sẽ gọi chính implementation `format` mà instance cung cấp. Đây là **hai phiên bản minh họa của cùng interface**, không được đặt cả hai khai báo trùng tên trong một tệp nguồn.

Mục tiêu bài học:

- Hiểu `default`, `abstract`, `static` method trong interface và cơ chế dispatch.
- Biết cách override default method, gọi `InterfaceName.super.method()`, xử lý nhiều interface trùng chữ ký.
- Giải thích ưu tiên **class wins**, default từ **subinterface cụ thể hơn** và trường hợp bắt buộc override.
- Phân biệt **source compatibility**, **binary compatibility** và **behavioral compatibility** khi nâng cấp thư viện.
- Nhận biết những giới hạn: method của `Object`, functional interface, state, concurrency, exception, hiệu năng và xung đột runtime.
- Xây dựng default implementation đúng contract, kiểm thử và phát hành thư viện có trách nhiệm.

**Phạm vi:** kiến thức của Java 8 vẫn còn áp dụng trong Java hiện đại; không dùng API đã bị loại bỏ hoặc hướng dẫn legacy. Chương trình chính dùng cú pháp/API tương thích Java 8 và chạy được trên JDK 17+.

## 2. Cú pháp và bản chất của default method

Một default method là phương thức instance của interface, có từ khóa `default` và có phần thân:

```java
interface Notifier {
    void send(String message);

    default void sendImportant(String message) {
        send("[IMPORTANT] " + message);
    }
}
```

Đây là **interface hợp lệ**, nhưng chưa có `main`. Bất kỳ class concrete nào `implements Notifier` và cài `send` có thể kế thừa `sendImportant`. Khi `sendImportant` chạy, lời gọi `send(...)` được dispatch theo object triển khai, không phải một implementation cố định trong interface.

Những điểm cần nhớ:

1. Default method là **instance method**, gọi trên instance hoặc qua tham chiếu instance; nó không tự động thành static.
2. Class triển khai **không buộc cài lại** một default method đã có body nếu không gặp xung đột.
3. Class có thể **override** default method; cách chọn method tuân theo thứ bậc class/interface và các luật override.
4. Default method có thể gọi các abstract method khác của interface; đây là mẫu thiết kế hữu ích để thêm behavior mới dựa trên primitive operation cũ.
5. Interface không có field instance riêng. Field khai báo trong interface là các hằng `public static final` theo luật Java; default method dùng state của implementation thông qua các method hay object khác, không có state instance "ẩn" do interface tạo.
6. Default method không tự chạy khi tạo object; nó chạy khi được gọi.
7. Một default implementation **không mặc nhiên** đáp ứng semantics của mọi implementation cũ; điều này phải được đánh giá theo contract nghiệp vụ.

### Phân biệt abstract, default và static

| Loại method | Có body? | Ai implement? | Ví dụ |
| --- | --- | --- | --- |
| Abstract interface method | Không | Class concrete hoặc interface kế thừa phù hợp phải cung cấp implementation | `formatter.format(x)` |
| Default method | Có | Interface cung cấp mặc định, class có thể override | `formatter.formatOrMissing(x)` |
| Static interface method | Có | Chính interface định nghĩa | `Formatter.identity()` |
| Instance method của class | Có hoặc abstract | Class/superclass | `object.method()` |

Static method của interface **không được kế thừa như instance method của class implements**. Viết `Formatter.identity()`, không gọi qua `new SomeFormatter().identity()`.

Trong Java 9+ có **private interface method** hỗ trợ dùng chung logic nội bộ giữa default/static methods, nhưng đây không phải cú pháp Java 8. Bài này tập trung vào default method vẫn có giá trị đến hiện nay; các ví dụ runnable không cần cú pháp mới hơn Java 8.

## 3. Ví dụ hoàn chỉnh: mở rộng interface, override và xung đột

Tạo tệp **`DefaultMethodEvolutionDemo.java`**:

```java
public class DefaultMethodEvolutionDemo {
    @FunctionalInterface
    interface Formatter {
        String format(String raw);

        default String formatOrMissing(String raw) {
            return format(raw == null ? "missing" : raw);
        }

        static Formatter identity() {
            return value -> value;
        }
    }

    static class OldFormatter implements Formatter {
        @Override
        public String format(String raw) {
            return "[" + raw + "]";
        }
    }

    static class CustomFormatter implements Formatter {
        @Override
        public String format(String raw) {
            return raw.toUpperCase();
        }

        @Override
        public String formatOrMissing(String raw) {
            return "custom:" + format(raw == null ? "none" : raw);
        }
    }

    interface Left {
        default String name() { return "left"; }
    }

    interface Right {
        default String name() { return "right"; }
    }

    static class Combined implements Left, Right {
        @Override
        public String name() {
            return Left.super.name() + "+" + Right.super.name();
        }
    }

    static class Base {
        public String name() { return "base"; }
    }

    interface Tagged {
        default String name() { return "tagged"; }
    }

    static class Inherited extends Base implements Tagged { }

    interface Advanced extends Left {
        @Override
        default String name() { return "advanced"; }
    }

    static class MoreSpecific implements Left, Advanced { }

    public static void main(String[] args) {
        Formatter old = new OldFormatter();
        System.out.println("old=" + old.formatOrMissing("abc"));
        System.out.println("override="
                + new CustomFormatter().formatOrMissing("abc"));

        Formatter lambda = s -> s.trim();
        System.out.println("lambda=" + lambda.formatOrMissing(" x "));
        System.out.println("factory=" + Formatter.identity().formatOrMissing(null));

        System.out.println("diamond=" + new Combined().name());
        System.out.println("classWins=" + new Inherited().name());
        System.out.println("specific=" + new MoreSpecific().name());
    }
}
```

Biên dịch với JDK hiện đại nhưng target cú pháp/API Java 8:

```bash
javac --release 8 DefaultMethodEvolutionDemo.java
java DefaultMethodEvolutionDemo
```

Nếu môi trường có JDK 17+ nhưng công cụ `javac` của bạn không chấp nhận phiên bản target do cấu hình riêng, có thể biên dịch đơn giản bằng `javac DefaultMethodEvolutionDemo.java`. Mã chương trình không phụ thuộc API sau Java 8.

**Stdout chính xác:**

```text
old=[abc]
override=custom:ABC
lambda=x
factory=missing
diamond=left+right
classWins=base
specific=advanced
```

### Cách đọc từng kết quả

**`old=[abc]`**: `OldFormatter` chỉ viết `format`, nhưng nhận được `formatOrMissing` từ interface. Default method gọi `format` của chính object `OldFormatter`, nên xuất hiện dấu ngoặc vuông.

**`override=custom:ABC`**: `CustomFormatter` override `formatOrMissing`. Khi gọi, method của class thắng default implementation; `format("abc")` được cài trong class nên trả `ABC`.

**`lambda=x`**: `Formatter` vẫn là **functional interface** dù có default và static method. Nó chỉ có một abstract method là `format`, vì vậy lambda `s -> s.trim()` dùng hợp lệ. Default method tiếp tục hoạt động trên instance functional interface được tạo bởi lambda.

**`factory=missing`**: `Formatter.identity()` là một static interface method trả lambda giữ nguyên input. Default method chuyển null thành `"missing"` trước khi gọi SAM.

**`diamond=left+right`**: `Combined` implements hai interface độc lập đều có default `name()`. Class giải quyết conflict bằng override và gọi rõ `Left.super.name()`, `Right.super.name()`.

**`classWins=base`**: `Inherited` có method `name()` thừa hưởng từ class `Base`; method của class được ưu tiên so với default `name()` trong `Tagged`.

**`specific=advanced`**: `Advanced extends Left` và override default `name()`. Implementation từ interface con cụ thể hơn được chọn.

**Lưu ý về compilation:** trên JDK rất mới, `javac --release 8` có thể in một số *compiler warning* liên quan support cho target cũ; các warning đó không phải stdout của chương trình. Các dòng trong khối `text` là kết quả khi gọi `java DefaultMethodEvolutionDemo`.

## 4. Quy tắc chọn method và diamond problem

Default method đưa triển khai vào interface, trong khi class Java có thể implements nhiều interface. Java cần giải quyết trường hợp tên/chữ ký method trùng nhau một cách tường minh.

### 4.1. Class wins

Khi superclass đã có **concrete instance method** phù hợp, method của class thường được ưu tiên hơn default method:

```java
class Parent {
    public String label() { return "from class"; }
}
interface Labeled {
    default String label() { return "from interface"; }
}
class Child extends Parent implements Labeled { }
```

Trong ngữ cảnh phù hợp, `new Child().label()` trả `"from class"`. Đây là ví dụ minh họa, chưa có class chứa `main`. Không mở rộng quy tắc "class wins" một cách máy móc cho mọi tình huống với **abstract class method**: một khai báo abstract trong hierarchy có thể khiến concrete subclass vẫn phải implement. Xét toàn bộ method modifiers, accessibility và override rules.

### 4.2. Interface cụ thể hơn thắng

Nếu `ChildInterface extends ParentInterface` và override method mặc định, một class implements cả hai có thể dùng implementation của **ChildInterface** theo luật chọn method cụ thể hơn. Ví dụ `Advanced extends Left` trong chương trình chính minh họa.

### 4.3. Hai default độc lập cùng chữ ký gây xung đột

Giả sử hai interface:

```java
interface Left {
    default String label() { return "left"; }
}
interface Right {
    default String label() { return "right"; }
}
```

Dòng sau **cố ý không biên dịch** khi bỏ comment:

```java
// class Broken implements Left, Right { }
```

Java **không chọn `Left` vì được viết trước** trong `implements Left, Right`. Một class cần giải quyết xung đột bằng override:

```java
class Resolved implements Left, Right {
    @Override
    public String label() {
        return Left.super.label() + " & " + Right.super.label();
    }
}
```

Các đoạn code này minh họa trong cùng một phạm vi, không phải chương trình độc lập hoàn chỉnh. Phương thức override có thể chọn một implementation, kết hợp cả hai hoặc tự triển khai mới, miễn đáp ứng hợp đồng của các interface mà class tuyên bố thực hiện.

### 4.4. Qualified super là lời gọi có ràng buộc

`Left.super.label()` là lời gọi default method của **superinterface hợp lệ**. Nó không phải lối tắt để gọi tùy tiện bất cứ interface gián tiếp nào trong hệ thừa kế; tên superinterface và quyền truy cập phải thỏa quy tắc ngôn ngữ.

Nếu interface con override default của interface cha, lời gọi nên tôn trọng thiết kế hierarchy. Khi cần behavior chuyên biệt, một override ở class là nơi rõ ràng để diễn đạt policy thay vì cố "né" override của interface con.

## 5. Default method và functional interface

Một **functional interface** được xác định từ số abstract method theo các quy tắc của JLS, không phải số dòng khai báo method tổng cộng. Default method, static method không tính như SAM cần cài.

```java
@FunctionalInterface
interface Sanitizer {
    String sanitize(String raw);

    default String sanitizeOrEmpty(String raw) {
        return sanitize(raw == null ? "" : raw);
    }

    static Sanitizer trim() {
        return String::trim;
    }
}
```

Đây là interface hoàn chỉnh nhưng chưa có `main`. Cả `Sanitizer s = text -> text.trim();` và `Sanitizer.trim()` đều hợp lệ. Thêm `sanitizeOrEmpty` **không làm mất tính functional** vì `sanitize` vẫn là abstract method duy nhất.

Ngược lại, nếu thêm một abstract method thứ hai không tương đương theo JLS, interface có thể không còn là functional interface, phá các lambda/method reference client. Không dùng default method như cách né tất cả thay đổi contract: class triển khai có thể vẫn gặp xung đột tên và behavior.

**Khuyến nghị:** khi interface được thiết kế như functional interface, giữ `@FunctionalInterface` để compiler cảnh báo nếu một lần sửa sau làm hợp đồng SAM không còn hợp lệ.

## 6. Giới hạn với các method của `Object`

Một interface **không được khai báo default method override-equivalent với non-private method của `java.lang.Object`**, chẳng hạn `toString()`, `equals(Object)` và `hashCode()`.

Ví dụ **cố ý không biên dịch** nếu mở dòng comment:

```java
interface BadDefault {
    // default String toString() { return "bad"; }
}
```

Lý do: các class Java đã kế thừa những method nền từ `Object` theo các quy tắc class riêng; default method trong interface không được dùng để âm thầm thay thế semantics của chúng. Interface có thể chứa **abstract declaration** phù hợp với một số method public của `Object` theo luật JLS, nhưng không được cấp default body override những method đó.

Nếu muốn một giá trị có semantics equality phù hợp, thiết kế `equals`/`hashCode` trong class/value type thích hợp; không cố triển khai một `default boolean equals(Object)` ở interface. Nếu muốn định dạng chung, có thể cung cấp một default method tên khác (`displayText()`) rồi để class quyết định có dùng nó trong `toString()` hay không.

## 7. Tiến hóa hợp đồng thư viện: ba lớp tương thích

Không nên tuyên bố rằng thêm default method là "**100% backward-compatible**" nếu chưa xác định tiêu chí tương thích.

| Loại | Câu hỏi cần trả lời | Rủi ro |
| --- | --- | --- |
| **Source compatibility** | Mã nguồn implementer/client cũ **biên dịch lại** với API mới không? | Clash chữ ký, access modifier, return type hoặc ambiguity khi kế thừa nhiều interface. |
| **Binary compatibility** | Class/JAR **đã biên dịch trước** có thể tiếp tục liên kết với phiên bản thư viện mới theo quy tắc JLS không? | Thêm default method thường binary-compatible, nhưng lời gọi có thể phát sinh `IncompatibleClassChangeError` khi gặp xung đột cụ thể. |
| **Behavioral compatibility** | Kết quả, exception, side effect, performance và concurrency có tiếp tục đáp ứng contract mong đợi không? | Default implementation mới hoặc override ở class cũ có thể tạo behavior khác. |

### 7.1. Vì sao binary-compatible chưa chắc chạy an toàn?

**JLS §13.5.7** nêu rõ việc **thêm default method** (hoặc đổi abstract method thành default) về nguyên tắc không phá binary compatibility với binary tồn tại, nhưng một binary cũ vẫn có thể gặp `IncompatibleClassChangeError` **khi gọi method**, ví dụ khi kiểu mà lời gọi sử dụng thừa kế hai default method cùng chữ ký/kết quả từ hai interface độc lập.

Do đó, việc thư viện và client cũ **link được** không chứng minh mọi lời gọi sẽ chạy an toàn. Đừng giải thích lỗi này như thể default method không được hỗ trợ trong JVM; đây là hệ quả hợp đồng được mở rộng mà không có một implementation duy nhất có thể chọn.

### 7.2. Source compatibility có thể bị phá

Một class client trước đây đã có method cùng tên và parameter với default method mới, nhưng method đó không tương thích về return type hoặc visibility; việc biên dịch lại có thể báo lỗi. Một class implements nhiều interface cũng có thể xuất hiện conflict mới khi một interface được thêm default method.

Compiler giúp phát hiện source conflict, nhưng **chỉ khi bạn thực sự recompile** các module/client liên quan. Ứng dụng dùng nhiều thư viện được biên dịch độc lập có thể bỏ sót lỗi nếu chỉ test một module.

### 7.3. Behavioral compatibility luôn cần đánh giá riêng

Giả sử default method `exists(id)` được triển khai bằng `find(id) != null`, nhưng một implementation có quy tắc `find` **ném lỗi** khi không tìm thấy. Việc thêm default method có thể hợp lệ về cú pháp mà không đúng semantics chung.

Ngược lại, nếu một class cũ đã có method cùng chữ ký với default method mới, method của class có thể thắng và behavior thực tế **không giống** phần thân mặc định mà tác giả thư viện mong đợi. Đó là vấn đề hợp đồng, không phải lỗi syntax.

Vì vậy, nên đánh giá source, binary và behavior **như ba lớp kiểm chứng tách biệt**.

## 8. Chọn default implementation nào để giữ hợp đồng?

Một default method an toàn thường:

- Chỉ sử dụng **abstract operations đã có trong interface** hoặc dữ liệu đã được contract công bố.
- Có behavior hợp lý cho **tất cả các implementation phù hợp**, không phụ thuộc chi tiết của một class cụ thể.
- Tuyên bố rõ **input, output, null, exception, side effect và complexity**, không làm client bất ngờ.
- Cho phép implementer override để tối ưu nếu vẫn **đúng contract**.
- Không giả định interface có mutable instance state riêng.
- Không lén thực hiện I/O, retry, transaction hoặc locking không được contract cho phép.

Ví dụ minh họa:

```java
interface Repository<T> {
    T find(String id);

    default boolean contains(String id) {
        return find(id) != null;
    }
}
```

**Điều kiện rất quan trọng:** ví dụ này chỉ đúng nếu hợp đồng `find` nói rõ rằng **không tìm thấy → trả `null`**. Nếu `find` trả `Optional<T>` hoặc ném exception, phải thiết kế `contains` khác. Default method không nên được viết dựa trên một giả định trái contract.

Một mẫu khác: default method diễn giải một số primitive operation có sẵn thành convenience method, nhưng cần tính đến cost. Nếu method nền thực hiện network request, default method lặp lại lời gọi nhiều lần có thể gây tăng latency hoặc side effect. **Hành vi đơn giản trong code không đồng nghĩa chi phí vận hành thấp.**

### Khi nào không nên dùng default method?

Không nên dùng nếu hành vi mới cần state chưa được contract định nghĩa, đòi hỏi implementation bắt buộc phải khác nhau, hoặc chỉ có một số nhỏ implementation hỗ trợ capability đó. Có thể cân nhắc **interface con mới**, một **static factory/utility** hoặc một **API version mới** rõ ràng.

Cẩn thận với default method chỉ làm `throw new UnsupportedOperationException()`: đôi khi một optional operation được tài liệu hóa đầy đủ có thể phù hợp, nhưng nếu đây là capability bắt buộc, bạn chỉ đang chuyển lỗi từ **compile time** sang **runtime**, không thật sự tạo khả năng tương thích nghiệp vụ.

## 9. Thay đổi default body cũng có thể đổi hành vi client

Một thư viện có thể không đổi chữ ký nhưng sửa phần thân default method giữa hai bản phát hành. Khi đó:

- Những class **không override** nhận behavior mới.
- Những class **đã override** tiếp tục dùng override của chúng.
- Method mặc định có thể gọi override khác trên instance cũ; thay đổi thứ tự/số lần gọi có thể gây side effect.
- Performance có thể đổi, ví dụ từ một phép duyệt thành hai phép duyệt collection.
- Exception mới hoặc việc xử lý `null` mới có thể khiến client cũ có kết quả khác.

Ví dụ:

```java
default String normalizeThenFormat(String raw) {
    return format(raw == null ? "" : raw.trim());
}
```

Đoạn này **minh họa** trong interface đã có abstract method `format(String)`. Việc tự động đổi `null` thành `""` và `trim()` là **lựa chọn behavior**, không phải ngữ nghĩa bắt buộc của default method. Nếu `format(null)` từng được phép với ý nghĩa riêng, default mới không nên tự tiện thay hợp đồng.

Vì thế, khi bảo trì thư viện, đừng chỉ so sánh method signature. Hãy đánh giá cả **semantic versioning**, release notes, contract test và quy trình nâng cấp của các client quan trọng.

## 10. Ví dụ từ Java Collections còn áp dụng hiện nay

Các interface chuẩn đã dùng default method để cung cấp tiện ích có giá trị lâu dài:

- `Iterable.forEach` diễn đạt việc xử lý từng phần tử bằng `Consumer`.
- `Collection.removeIf` mô tả việc xóa phần tử theo điều kiện.
- `List.replaceAll`, `List.sort` đưa các thao tác có hành vi mặc định vào giao diện danh sách.
- `Map.getOrDefault`, `Map.computeIfAbsent` là những default method hỗ trợ cách dùng map tiện lợi.

Các API này **vẫn có hiệu lực** trong Java hiện đại. Nhưng phải đọc contract của từng phương thức: `removeIf` trên collection không hỗ trợ loại bỏ có thể ném `UnsupportedOperationException` khi cần xóa; một default method của `Map` không mặc nhiên có bảo đảm **atomicity** như implementation concurrent chuyên biệt.

Đừng suy luận "có default method thì mọi implementation hỗ trợ đầy đủ thao tác" hay "default method luôn thread-safe". Hành vi của implementation và khả năng hỗ trợ mutation vẫn quyết định kết quả.

## 11. Giải quyết xung đột trong hệ thống nhiều thư viện

Trong hệ thống modular, class có thể implements interface từ nhiều thư viện. Việc một thư viện thêm default method mới vô tình làm trùng tên/chữ ký với thư viện khác là một rủi ro có thật.

Giảm rủi ro bằng cách:

1. Dùng tên method **rõ nghĩa**, tránh những tên quá chung nếu chúng mang policy nghiệp vụ riêng.
2. Giữ interface **nhỏ, tập trung vào capability**; không dồn mọi tiện ích vào một public interface lớn.
3. Rà soát nhóm class thường implements nhiều interface cùng lúc.
4. Khi có conflict, đặt **override tường minh** ở lớp ghép, chọn hoặc phối hợp hành vi phù hợp hợp đồng.
5. Không dựa vào thứ tự `implements A, B` để lựa chọn default method.
6. Test cả source recompile và runtime liên kết nhiều version thư viện; đừng chỉ chạy unit test mỗi package.
7. Cân nhắc bổ sung interface mới hoặc điều chỉnh version release nếu một default method làm thay đổi nhiều client hiện hữu.

Một implementation class có method `m()` riêng có thể che default `m()` từ thư viện mới mà vẫn biên dịch. Đây là **accidental override** có thể tạo behavior conflict âm thầm, không nên đánh giá hoàn toàn dựa trên việc compiler không báo lỗi.

## 12. Kiểm thử tiến hóa interface: không chỉ unit test

Hãy kiểm chứng ít nhất các tầng sau:

| Tầng kiểm thử | Đối tượng cần thử | Kết quả mong muốn |
| --- | --- | --- |
| Source compile | Các client/implementation cũ biên dịch lại với thư viện mới | Không có conflict/ambiguity hoặc thay đổi được xử lý rõ. |
| Binary integration | Client đã build với bản thư viện cũ chạy với bản mới | Không có lỗi linkage/invocation như `IncompatibleClassChangeError`. |
| Default contract | Một implementation **không override** | Default behavior đúng input, output, null, exception. |
| Override contract | Implementation **có override** | Chọn đúng method và vẫn giữ semantics đã hứa. |
| Multiple interfaces | Class ghép hai hoặc nhiều capability | Xung đột được giải quyết tường minh. |
| Functional interface | Lambda/method reference client hiện hữu | SAM và target typing vẫn hợp lệ. |
| Nonfunctional | Hiệu năng, concurrency, mutation, exception | Không làm thay đổi kỳ vọng quan trọng. |

Ví dụ bài test hành vi từ chương trình chính:

- `new OldFormatter().formatOrMissing("abc")` phải trả `"[abc]"`.
- `new CustomFormatter().formatOrMissing("abc")` phải trả `"custom:ABC"`.
- `Formatter f = text -> text.trim(); f.formatOrMissing(" x ")` phải trả `"x"`.
- `new Combined().name()` phải trả `"left+right"`.
- `new Inherited().name()` phải trả `"base"`.
- `new MoreSpecific().name()` phải trả `"advanced"`.

**Binary compatibility test đúng nghĩa** phải dùng **hai giai đoạn build**: compile client với JAR/API cũ, giữ class/JAR kết quả, sau đó thay **runtime dependency** bằng bản thư viện mới mà không biên dịch lại client, rồi chạy integration test. Chỉ biên dịch một lần với interface mới **không chứng minh** binary compatibility.

Công cụ phát hiện khác biệt ABI có thể hỗ trợ phân tích thay đổi, nhưng **không thay thế** behavioral tests, nhất là side effect và concurrency.

## 13. Quy trình phát hành default method cho thư viện

Một quy trình nên dùng khi công bố API:

1. **Viết vấn đề cần giải quyết:** vì sao client cần method mới, có thể cài nó bằng operation cũ không?
2. **Đặc tả contract trước code:** return value, exception, null, mutation, thứ tự gọi, complexity, thread safety.
3. **Kiểm tra giới hạn của interface:** tránh default override method của `Object`, tránh tạo xung đột với interface khác, giữ functional-interface contract nếu cần.
4. **Chọn implementation mặc định thận trọng:** dùng primitive operations đáng tin; đừng cho rằng mọi implementation cũ có cùng storage/caching/locking.
5. **Cho phép override rõ ràng** khi implementation có giải pháp phù hợp hơn, nhưng yêu cầu giữ observable behavior.
6. **Chạy source-compatibility test** trên các class/client đại diện.
7. **Chạy binary-compatibility test** qua phiên bản cũ/mới và kiểm tra invocation thực tế, không chỉ class loading.
8. **Thử behavior, performance và concurrency** với nhiều implementation khác nhau.
9. **Viết release notes và kế hoạch versioning** phù hợp mức rủi ro; nếu khả năng breaking cao, cân nhắc API mới thay vì ép thêm default.
10. **Giám sát lỗi sau triển khai**, đặc biệt các class implementations nằm ở module thứ ba mà bạn không kiểm soát.

Đây là phương pháp duy trì hợp đồng thư viện Java vẫn còn phù hợp hiện nay. Không nên chỉ dựa vào khả năng viết một default method ngắn để khẳng định độ tương thích.

## 14. Những lỗi hiểu nhầm phổ biến

| Hiểu nhầm | Điều đúng |
| --- | --- |
| "Default method là static method." | Default là instance method; static method của interface gọi qua tên interface. |
| "Lớp triển khai luôn dùng body mặc định." | Lớp có thể override hoặc kế thừa class method phù hợp được ưu tiên. |
| "Thêm default method chắc chắn không breaking." | Phải xét source, binary/invocation và behavioral compatibility riêng. |
| "Hai interface có cùng default method sẽ chọn bên viết trước." | Không; conflict giữa các default độc lập cần giải quyết bằng override tường minh. |
| "Thêm default method phá functional interface." | Không, nếu abstract-method set theo JLS vẫn chỉ có một SAM. |
| "Interface có thể default-override `toString()`." | Bị cấm nếu override-equivalent với non-private method của `Object`. |
| "Default implementation tự có state của interface." | Interface không cung cấp instance fields; behavior phụ thuộc instance/method được gọi. |
| "Mọi default method đều thread-safe." | Không; shared state và concurrency semantics phải được thiết kế riêng. |
| "Binary-compatible nghĩa là mọi invocation runtime an toàn." | JLS nêu xung đột default method có thể gây `IncompatibleClassChangeError` khi gọi. |
| "Unit test interface mới chứng minh client cũ không bị ảnh hưởng." | Cần source recompile, test binary cũ và kiểm tra behavior. |

## 15. Câu hỏi tự kiểm tra

**1.** Một interface đã có `size()`. Thêm `default boolean isEmpty() { return size() == 0; }` có ưu điểm gì? **Đáp án:** cung cấp tiện ích dựa trên operation cũ, thường không buộc mọi implementer viết `isEmpty`. Vẫn phải kiểm tra cách `size()` hoạt động, hiệu năng/concurrency và conflict.

**2.** Class implements `A` và `B`, cả hai là interface độc lập có `default void run()`. Java chọn A vì `implements A,B`? **Không**; class cần override giải quyết conflict nếu không có method class phù hợp.

**3.** `Base` có concrete public `run()`, `interface A` có default `run()`, `Child extends Base implements A` gọi gì? **Method của class hierarchy** theo luật ưu tiên khi override hợp lệ.

**4.** Interface đang là SAM và được dùng bằng lambda. Thêm một default method có làm lambda cũ mất target type? **Không chỉ vì thêm default**, nếu SAM cũ còn một abstract method hợp lệ và không tạo xung đột chữ ký khác.

**5.** Có thể thêm `default boolean equals(Object other)` vào interface? **Không**, vì tương đương một public instance method của `Object`.

**6.** Đã recompile toàn bộ source client thành công. Có cần chạy binary compatibility test nữa không? **Có**, nếu hỗ trợ client cũ đã biên dịch và phân phối độc lập; recompile chưa kiểm tra invocation của binary cũ.

**7.** Một default method gọi `find(id)`, nhưng implementation A trả null khi không thấy còn B ném exception. Viết `contains = find != null` có chắc đúng cho cả hai không? **Không**; phải định nghĩa hành vi chung trước.

**8.** Thay body default method từ gọi `find` một lần thành gọi hai lần có thể breaking không? **Có** về behavior/side effect/performance, ngay cả khi chữ ký không thay đổi.

## 16. Tổng kết và tham khảo

**Default method** cho phép thư viện mở rộng interface bằng hành vi có sẵn và là một cách tiến hóa hợp đồng hiệu quả khi implementation có thể dựa trên các operation đã được đảm bảo. Tuy nhiên, thứ bậc class/interface vẫn quyết định method nào chạy; hai default method độc lập cùng chữ ký có thể xung đột; default method không được override các method nền của `Object`.

Quan trọng nhất, hãy phân biệt **tương thích mã nguồn**, **tương thích nhị phân** và **tương thích hành vi**. Một thay đổi Java coi là binary-compatible vẫn có thể làm client khó biên dịch lại hoặc gây lỗi khi gọi trong trường hợp xung đột. Hãy đặc tả contract, kiểm tra đa implementation và dùng source/binary/integration tests khi phát hành. Những nguyên tắc này vẫn áp dụng trong Java hiện đại.

**Nguồn đặc tả chính thức:**

- [JLS §9.4 — Interface Method Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4).
- [JLS §13.5.7 — Interface Method Declarations and Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se25/html/jls-13.html#jls-13.5.7).
- [JLS §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12).
- [Oracle Java tutorial — Default Methods](https://docs.oracle.com/javase/tutorial/java/IandI/defaultmethods.html). Đây là tài liệu giải thích tính năng Java 8; các quy tắc hiện còn áp dụng được đối chiếu với JLS mới.
