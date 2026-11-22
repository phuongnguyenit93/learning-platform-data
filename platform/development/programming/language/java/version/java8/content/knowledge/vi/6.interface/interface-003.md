# Quy tắc ưu tiên phương thức của lớp khi triển khai interface trong Java

Kể từ Java 8, interface có thể khai báo **`default method`**: một phương thức instance có sẵn phần thân, nhằm cung cấp hành vi mặc định cho các lớp triển khai. Cơ chế này giúp bổ sung hành vi mới vào interface trong nhiều trường hợp mà không buộc mọi lớp triển khai cũ phải viết lại phương thức. Tuy nhiên, khi một **lớp** và một **interface** cùng cung cấp phương thức có chữ ký tương đương, Java cần quyết định phương thức nào được dùng.

Quy tắc trọng tâm là **“class methods win over interface defaults” — phương thức instance hợp lệ của lớp được ưu tiên hơn phương thức `default` tương ứng của interface**. Nếu lớp triển khai interface đã có một phương thức concrete phù hợp, trực tiếp khai báo hoặc kế thừa từ lớp cha, thì phương thức của lớp xác định hành vi khi gọi. Quy tắc này vẫn thuộc Java Language Specification hiện hành; không phải một mẹo tạm thời của Java 8.

Ví dụ:

```java
interface Greeter {
    default String greet() {
        return "Hello from interface";
    }
}

class Parent {
    public String greet() {
        return "Hello from class";
    }
}

class Child extends Parent implements Greeter {
}
```

`Child` không khai báo lại `greet()`, nhưng **kế thừa phương thức public concrete từ `Parent`**. Do đó:

```java
Child child = new Child();
System.out.println(child.greet()); // Hello from class
```

Bài này giải thích **vì sao lớp được ưu tiên**, phạm vi thực sự của quy tắc, các ngoại lệ quan trọng như **phương thức `abstract` của lớp cha**, cách xử lý **hai interface có default trùng nhau**, và cách tránh lỗi thiết kế khi thay đổi API.

## 1. Kiến thức nền: interface `default` là gì?

Trong Java hiện đại, interface có thể khai báo phương thức trừu tượng, phương thức `default`, phương thức `static` và phương thức `private` (từ Java 9). `default` là phương thức instance có phần thân:

```java
interface Notifier {
    default String channel() {
        return "email";
    }
}
```

Lớp triển khai có thể không ghi đè:

```java
class BasicNotifier implements Notifier {
}

String channel = new BasicNotifier().channel(); // "email"
```

Nếu lớp tự định nghĩa phương thức đáp ứng cùng hợp đồng, phương thức lớp sẽ được gọi:

```java
class SmsNotifier implements Notifier {
    @Override
    public String channel() {
        return "sms";
    }
}

String channel = new SmsNotifier().channel(); // "sms"
```

**Phân biệt:** `default` khác `static`. Phương thức `static` của interface được gọi bằng tên interface, ví dụ `Notifier.someStaticMethod()` nếu phương thức đó tồn tại; nó không phải một default instance method được kế thừa bởi đối tượng theo cùng cơ chế.

Các ví dụ ngắn phía trên là **đoạn minh họa trong ngữ cảnh Java hợp lệ**, không phải tệp độc lập đầy đủ. Chương trình hoàn chỉnh có thể chạy được trình bày ở mục 9.

## 2. Quy tắc chính: phương thức concrete trong lớp được ưu tiên

Hãy nhớ thứ tự tư duy:

1. Kiểm tra lớp cụ thể **có khai báo phương thức instance phù hợp** hay không.
2. Nếu không, kiểm tra **chuỗi lớp cha** có phương thức instance concrete phù hợp được kế thừa hay không.
3. Nếu đã có phương thức lớp hợp lệ, phương thức đó được ưu tiên hơn `default` của interface với chữ ký tương đương.
4. Nếu không có phương thức concrete của lớp, mới xem xét những `default` được kế thừa từ interface, tính đặc hiệu giữa các interface và các xung đột có thể có.
5. Luôn kiểm tra **chữ ký, kiểu trả về, phạm vi truy cập, `throws` và quy tắc override**; không phải cứ trùng tên là hợp lệ.

Ví dụ lớp khai báo trực tiếp:

```java
interface Message {
    default String text() {
        return "interface";
    }
}

class DirectMessage implements Message {
    @Override
    public String text() {
        return "class";
    }
}
```

`new DirectMessage().text()` trả `"class"`.

Đây là trường hợp **lớp tự override** rõ ràng, không có sự nhập nhằng. Trường hợp dễ nhầm hơn là **lớp con không override**, nhưng kế thừa phương thức từ lớp cha.

### 2.1. Phương thức kế thừa từ superclass cũng được ưu tiên

```java
interface Named {
    default String name() {
        return "from interface";
    }
}

class Base {
    public String name() {
        return "from superclass";
    }
}

class Derived extends Base implements Named {
}
```

`Derived` kế thừa `Base.name()`, nên:

```java
Derived value = new Derived();
System.out.println(value.name()); // from superclass
```

Điểm cần nhớ là **`Base` không cần biết interface `Named` tồn tại**. `Derived` cũng không cần khai báo lại `name()` để quy tắc ưu tiên của lớp phát huy tác dụng. Cách vận hành này giúp bảo toàn hành vi của hệ phân cấp lớp khi interface bổ sung một default method trùng chữ ký.

### 2.2. Gọi qua biến kiểu interface vẫn dùng phương thức của lớp

Một hiểu nhầm phổ biến: “Nếu ép kiểu đối tượng sang interface thì Java sẽ gọi default method”. Không đúng. Gọi phương thức instance vẫn sử dụng cơ chế dispatch động để chọn implementation của đối tượng:

```java
Named named = new Derived();
System.out.println(named.name()); // from superclass
```

Ép kiểu `(Named) value` **không thay đổi implementation của đối tượng**; nó chỉ thay đổi kiểu tĩnh mà compiler dùng để kiểm tra lời gọi. Trong trường hợp trên, `Base.name()` là phương thức được chọn để thực thi.

Vì thế, không dùng ép kiểu sang interface như cách “bỏ qua” implementation của lớp để gọi mặc định.

## 3. Vì sao Java đặt lớp trên interface?

Interface dùng để khai báo một **hợp đồng**, còn default method cung cấp một implementation có thể tái sử dụng khi lớp chưa có phương thức phù hợp. Trong khi đó, việc một lớp đã khai báo hoặc kế thừa phương thức concrete thường thể hiện **hành vi hiện có của hệ phân cấp lớp**.

Nếu một thư viện thêm default method mới vào interface và Java bất ngờ thay thế phương thức mà một lớp cha đã cung cấp, chương trình cũ có thể đổi hành vi không mong muốn. Quy tắc ưu tiên lớp giúp hạn chế tình huống đó trong các trường hợp hợp đồng tương thích.

Tuy nhiên, nó **không bảo đảm mọi thay đổi interface đều tương thích ngược**. Thêm default method vẫn có thể gây xung đột với interface khác, lỗi về tính hợp lệ của override, hoặc vấn đề tương thích ở một thiết kế cụ thể. Luôn kiểm thử các lớp triển khai khi mở rộng interface công khai.

## 4. Quy tắc ưu tiên lớp KHÔNG xóa bỏ yêu cầu của hợp đồng

Nói “class wins” không có nghĩa là bất kỳ phương thức trùng tên nào của lớp cũng tự động phù hợp. Để một phương thức lớp thực sự đáp ứng phương thức instance public của interface, nó cần có chữ ký override phù hợp và tuân theo các giới hạn của Java.

### 4.1. Phạm vi truy cập không được hẹp hơn

Phương thức instance trừu tượng và default của interface thông thường là **`public`**. Một phương thức lớp dùng để implement/override chúng phải đủ mức truy cập. Ví dụ sau cố ý sai:

```java
interface Visible {
    default String label() {
        return "interface";
    }
}

class TooNarrow implements Visible {
    // KHÔNG BIÊN DỊCH: phạm vi package-private hẹp hơn public.
    String label() {
        return "class";
    }
}
```

Không phải Java sẽ “bỏ qua phương thức lớp rồi tự dùng default”. Định nghĩa có chữ ký đè lên phương thức public nhưng mức truy cập hẹp hơn là **lỗi biên dịch**. Sửa bằng cách khai báo `public`:

```java
class Correct implements Visible {
    @Override
    public String label() {
        return "class";
    }
}
```

Phương thức `private` hoặc `static` cũng không thể được dùng tùy tiện để thay thế một instance method public cùng chữ ký của interface. Các quy tắc override và static/instance vẫn phải được tuân thủ.

### 4.2. Kiểu trả về và checked exception phải hợp lệ

Nếu interface có `default String label()` thì một class không được override với kiểu kết quả không tương thích như `int label()`. Java cho phép **covariant return** đối với kiểu tham chiếu khi thỏa luật override, nhưng không cho phép tùy ý đổi kiểu.

Tương tự, một phương thức override không được mở rộng tập **checked exception** vượt quá phạm vi hợp đồng overridden. Ví dụ:

```java
interface Readable {
    default String read() {
        return "default";
    }
}

// KHÔNG BIÊN DỊCH nếu dùng khai báo:
// class Reader implements Readable {
//     @Override
//     public String read() throws java.io.IOException {
//         return "file";
//     }
// }
```

Lý do: `Readable.read()` không khai báo `throws IOException`. Kể cả khi “class wins”, chữ ký override vẫn phải thỏa hợp đồng của interface. `RuntimeException` là unchecked exception và tuân theo quy tắc khác về yêu cầu khai báo.

### 4.3. Trùng tên nhưng khác danh sách tham số là overload, không phải override

```java
interface Converter {
    default String convert(String value) {
        return "interface:" + value;
    }
}

class BaseConverter {
    public String convert(int number) {
        return "class:" + number;
    }
}

class ConverterImpl extends BaseConverter implements Converter {
}
```

Ở đây `convert(int)` và `convert(String)` **khác chữ ký**; chúng là overload, không tranh cùng một slot override. Vì vậy:

```java
ConverterImpl c = new ConverterImpl();
System.out.println(c.convert(7));       // class:7
System.out.println(c.convert("Java"));  // interface:Java
```

Không áp dụng khẩu hiệu “class wins” chỉ vì hai phương thức có cùng tên `convert`. Phải so sánh **chữ ký override-equivalent** (cùng tên và tham số tương đương theo quy tắc Java, có cân nhắc generic/erasure khi liên quan).

## 5. Trường hợp quan trọng: phương thức `abstract` từ superclass

Đây là điểm thường bị giải thích thiếu. **Superclass có phương thức `abstract` phù hợp có thể ngăn việc dùng default method làm implementation tự động**. Lúc này, lớp concrete phải cung cấp implementation hợp lệ; không được kết luận “interface có default nên đủ”.

Ví dụ:

```java
abstract class AbstractBase {
    public abstract String getValue();
}

interface HasDefault {
    default String getValue() {
        return "interface default";
    }
}

// KHÔNG BIÊN DỊCH: ConcreteMissing chưa triển khai
// phương thức abstract getValue() của AbstractBase.
// class ConcreteMissing extends AbstractBase implements HasDefault {
// }
```

Cách sửa:

```java
class ConcreteValue extends AbstractBase implements HasDefault {
    @Override
    public String getValue() {
        return "implemented in class";
    }
}
```

`new ConcreteValue().getValue()` trả `"implemented in class"`.

Giải thích cẩn thận: trong Java Language Specification, sự hiện diện của một phương thức abstract được khai báo ở superclass có quy tắc riêng khi lớp kế thừa các phương thức tương đương từ interface. Nó không đơn giản là “abstract method chạy thay cho default method”; **abstract method không có thân để chạy**. Về mặt hợp đồng, yêu cầu abstract từ hệ phân cấp lớp không được xem như đã được đáp ứng chỉ nhờ default trong trường hợp này.

Nếu chính lớp con đã triển khai phương thức concrete phù hợp, phương thức concrete đó hoàn thành nghĩa vụ, và đây lại trở thành một trường hợp thông thường của quy tắc ưu tiên lớp.

### 5.1. Lớp trừu tượng vẫn có thể mang nghĩa vụ chưa hoàn thành

Một lớp abstract trung gian có thể tiếp tục mang nghĩa vụ cung cấp `getValue()`. Không cần ép nó thành concrete nếu chưa có implementation thích hợp:

```java
abstract class Intermediate
        extends AbstractBase implements HasDefault {
    // Vẫn trừu tượng.
}
```

Đoạn này minh họa ngữ cảnh chứa các khai báo `AbstractBase` và `HasDefault` ở trên. Lớp con concrete của `Intermediate` vẫn phải đáp ứng phương thức trừu tượng.

## 6. Nếu không có class method: mặc định của interface nào được chọn?

Quy tắc ưu tiên lớp chỉ giải quyết một phần của bức tranh. Khi không có phương thức concrete của lớp phù hợp, Java xét hệ thống kế thừa các interface.

### 6.1. Interface con cụ thể hơn được ưu tiên

Giả sử interface con override default của interface cha:

```java
interface BasicGreeting {
    default String greet() {
        return "basic";
    }
}

interface FriendlyGreeting extends BasicGreeting {
    @Override
    default String greet() {
        return "friendly";
    }
}

class FriendlyUser implements FriendlyGreeting {
}
```

`new FriendlyUser().greet()` trả `"friendly"`. `FriendlyGreeting.greet()` ghi đè phiên bản ở interface cha và là lựa chọn cụ thể hơn. Không có xung đột giữa **hai default độc lập** ở trường hợp này, vì chúng có quan hệ kế thừa và default ở interface con đã override default ở cha.

Một lớp triển khai cả `BasicGreeting` lẫn `FriendlyGreeting` cũng không tự tạo hai default độc lập: phương thức của interface con vẫn override phương thức từ interface cha trong cấu trúc đó.

### 6.2. Hai interface không liên quan có default giống chữ ký: phải giải quyết xung đột

```java
interface Left {
    default String side() {
        return "left";
    }
}

interface Right {
    default String side() {
        return "right";
    }
}

// KHÔNG BIÊN DỊCH: hai default độc lập xung đột.
// class Ambiguous implements Left, Right {
// }
```

Lớp cần **override phương thức**, quyết định cách kết hợp/chọn hành vi:

```java
class Resolved implements Left, Right {
    @Override
    public String side() {
        return Left.super.side() + "+" + Right.super.side();
    }
}
```

`new Resolved().side()` trả `"left+right"`. Cú pháp `Left.super.side()` và `Right.super.side()` được sử dụng trong ngữ cảnh implement trực tiếp interface tương ứng để gọi default được chọn một cách tường minh.

Không nên coi thứ tự `implements Left, Right` là thứ tự ưu tiên. Java **không** tự chọn interface đứng trước.

### 6.3. Nếu đã có concrete method từ lớp cha, xung đột hai default có thể được giải quyết theo quy tắc lớp

```java
class BaseSide {
    public String side() {
        return "base";
    }
}

class BothWithBase extends BaseSide implements Left, Right {
}
```

`new BothWithBase().side()` trả `"base"`. Ở đây có concrete instance method công khai phù hợp từ `BaseSide`, nên lớp không cần override chỉ để chọn giữa hai default `Left` và `Right`.

Tương phản với `Ambiguous`: `Ambiguous` không có class method phù hợp nên compiler không thể tự chọn một trong hai default độc lập.

### 6.4. Một interface trừu tượng và một interface default độc lập cũng cần chú ý

Không nên khẳng định “cứ có một default cùng chữ ký là compiler sẽ dùng nó”. Nếu hai interface **không có quan hệ override thích hợp** cung cấp một phương thức abstract và một default có chữ ký tương đương, cũng có thể xảy ra lỗi xung đột khi lớp cố kế thừa cả hai.

```java
interface Required {
    String status();
}

interface Provided {
    default String status() {
        return "provided";
    }
}

// KHÔNG BIÊN DỊCH: xung đột phương thức kế thừa.
// class MissingResolution implements Required, Provided {
// }
```

Lớp có thể giải quyết bằng một implementation hợp lệ:

```java
class StatusResolved implements Required, Provided {
    @Override
    public String status() {
        return "resolved";
    }
}
```

Phân biệt rõ tình huống này với trường hợp interface con override/phân giải phương thức của cha, và với phương thức abstract được khai báo ở **superclass** (mục 5).

## 7. Khác biệt giữa `Object` và interface default

Mọi lớp Java (ngoại trừ bản thân `Object`) nằm trong hệ phân cấp có `Object` ở gốc. Các phương thức public như `toString()`, `equals(Object)`, `hashCode()` có vị trí đặc biệt trong Java.

Interface **không được khai báo default method có chữ ký override-equivalent với phương thức không private tương ứng của `Object`**. Ví dụ sau là lỗi biên dịch:

```java
interface BadDescription {
    // KHÔNG BIÊN DỊCH:
    // default String toString() {
    //     return "from interface";
    // }
}
```

Đoạn trên được chú thích để chỉ rõ quy tắc; như đang viết, `BadDescription` là một interface rỗng có thể biên dịch, nhưng nếu bỏ comment quanh phương thức `default toString()` thì sẽ xuất hiện lỗi.

Nếu muốn đối tượng có biểu diễn chuỗi riêng, lớp nên override `toString()`:

```java
interface Described {
    default String description() {
        return "description from interface";
    }
}

class RecordLike implements Described {
    @Override
    public String toString() {
        return description();
    }
}
```

`description()` là một tên khác không xung đột với `Object.toString()`. `RecordLike.toString()` là phương thức lớp tự định nghĩa; nó có thể gọi default `description()` từ interface mà không cần interface cố override `Object`.

Lưu ý: một interface có thể **khai báo trừu tượng** các phương thức tương thích với `Object` trong những trường hợp được Java cho phép; cấm quan trọng ở đây là khai báo **`default`** tương đương với phương thức không private của `Object`. Không trộn hai ý này thành “interface không được nhắc đến `toString`”.

## 8. Cách gọi tường minh superclass và interface

### 8.1. `super.method()` là lời gọi superclass

Nếu lớp con override method và muốn gọi implementation của lớp cha, dùng `super.method()`:

```java
interface Greeting {
    default String greeting() {
        return "interface";
    }
}

class GreeterBase {
    public String greeting() {
        return "base";
    }
}

class SpecialGreeter extends GreeterBase implements Greeting {
    @Override
    public String greeting() {
        return "special>" + super.greeting();
    }
}
```

`new SpecialGreeter().greeting()` là `"special>base"`. `super.greeting()` gọi theo chuỗi lớp cha; nó không mặc nhiên yêu cầu Java gọi default của `Greeting`.

### 8.2. `InterfaceName.super.method()` chọn default cụ thể khi hợp lệ

Cú pháp `Left.super.side()` trong `Resolved implements Left, Right` (mục 6) được dùng để chọn một default method từ một direct superinterface trong trường hợp luật Java cho phép. Nó hữu ích khi chủ động phối hợp hai interface:

```java
class PreferLeft implements Left, Right {
    @Override
    public String side() {
        return Left.super.side();
    }
}
```

`new PreferLeft().side()` trả `"left"`. Đây là quyết định có chủ đích của lớp, không phải ưu tiên mặc định của compiler.

Không nhầm cú pháp này với phép ép kiểu `((Left) object).side()`. Ép kiểu **không** buộc thực thi default `Left.side`; lời gọi thông thường vẫn dispatch theo implementation của đối tượng.

### 8.3. Có nên gọi default khi class method đã thắng?

Đôi khi code muốn sử dụng một phần hành vi mặc định của interface. Lúc đó, có thể override trong lớp và gọi `InterfaceName.super.method()` nếu ngữ cảnh đáp ứng các ràng buộc của JLS (đặc biệt là interface phù hợp ở danh sách superinterface trực tiếp và không bị che bởi override interface cụ thể hơn).

Tuy nhiên, chỉ nên gọi tường minh khi điều đó **thực sự là lựa chọn nghiệp vụ**, thay vì cố ép compiler bỏ qua quy tắc class wins. Nếu quan hệ kế thừa phức tạp, giải pháp thường dễ hiểu hơn là trích hành vi dùng chung thành một phương thức/đối tượng hợp thành riêng.

## 9. Chương trình Java hoàn chỉnh kiểm chứng các quy tắc

Tạo tệp **`ClassMethodPriorityDemo.java`**. Chương trình dùng cú pháp `default` có từ Java 8 và các API còn hỗ trợ; biên dịch/chạy trên JDK 17+ (đồng thời tương thích Java 8).

```java
public class ClassMethodPriorityDemo {

    interface Greeter {
        default String greet() {
            return "interface";
        }
    }

    static class Parent {
        public String greet() {
            return "class";
        }
    }

    static class Child extends Parent implements Greeter {
        // Kế thừa phương thức từ Parent, không cần override.
    }

    static class Direct implements Greeter {
        @Override
        public String greet() {
            return "direct";
        }
    }

    interface Basic {
        default String label() {
            return "basic";
        }
    }

    interface Specific extends Basic {
        @Override
        default String label() {
            return "specific";
        }
    }

    static class SpecificImpl implements Specific {
    }

    interface Left {
        default String side() {
            return "left";
        }
    }

    interface Right {
        default String side() {
            return "right";
        }
    }

    static class Resolved implements Left, Right {
        @Override
        public String side() {
            return Left.super.side() + "+" + Right.super.side();
        }
    }

    static class SideBase {
        public String side() {
            return "base";
        }
    }

    static class BothWithBase extends SideBase
            implements Left, Right {
    }

    static abstract class AbstractBase {
        public abstract String value();
    }

    interface WithValue {
        default String value() {
            return "default value";
        }
    }

    static class ConcreteValue extends AbstractBase
            implements WithValue {
        @Override
        public String value() {
            return "implemented";
        }
    }

    public static void main(String[] args) {
        Child child = new Child();

        System.out.println("Inherited class: " + child.greet());

        Greeter interfaceView = child;
        System.out.println("Interface view: "
                + interfaceView.greet());

        System.out.println("Direct class: "
                + new Direct().greet());

        System.out.println("Specific interface: "
                + new SpecificImpl().label());

        System.out.println("Resolved defaults: "
                + new Resolved().side());

        System.out.println("Two defaults with class: "
                + new BothWithBase().side());

        System.out.println("Abstract obligation: "
                + new ConcreteValue().value());
    }
}
```

Biên dịch và chạy:

```bash
javac ClassMethodPriorityDemo.java
java ClassMethodPriorityDemo
```

**Stdout chính xác:**

```text
Inherited class: class
Interface view: class
Direct class: direct
Specific interface: specific
Resolved defaults: left+right
Two defaults with class: base
Abstract obligation: implemented
```

Giải thích kết quả:

1. `Child` kế thừa `Parent.greet()`; phương thức concrete của lớp được ưu tiên hơn `Greeter.greet()` mặc định. Vì vậy dòng đầu in `class`.
2. Tham chiếu kiểu `Greeter` trỏ đến cùng đối tượng `Child`; dispatch vẫn gọi phương thức lớp, nên dòng thứ hai cũng là `class`.
3. `Direct` khai báo override riêng và trả `direct`.
4. `Specific` là interface con override `Basic.label()`, nên `SpecificImpl` dùng default cụ thể hơn và in `specific`.
5. `Resolved` giải quyết hai default độc lập bằng `Left.super.side()` cộng `Right.super.side()`, cho `left+right`.
6. `BothWithBase` có `SideBase.side()` public concrete nên không cần tự phân giải hai default `Left`/`Right`; in `base`.
7. `ConcreteValue` triển khai nghĩa vụ abstract của `AbstractBase` thay vì được dùng default `WithValue.value()` tự động; in `implemented`.

Vì các phương thức trả về chuỗi hằng và chương trình không có I/O mạng, ngẫu nhiên hoặc thứ tự collection không xác định, stdout ở trên có thể kiểm tra trực tiếp.

## 10. Bảng quyết định tổng hợp

| Tình huống | Điều Java làm | Việc nên làm |
| --- | --- | --- |
| Lớp khai báo phương thức public concrete đúng chữ ký của default interface | Sử dụng phương thức của lớp | Dùng `@Override` để làm rõ ý định |
| Lớp kế thừa phương thức public concrete từ superclass | Phương thức lớp được ưu tiên | Kiểm thử khi thêm interface mới |
| Biến gọi có kiểu interface nhưng đối tượng thuộc lớp trên | Vẫn dispatch theo implementation lớp | Không ép kiểu để tìm default |
| Superclass khai báo abstract method tương đương | Default không tự xóa nghĩa vụ abstract | Lớp concrete phải implement |
| Interface con override default của interface cha | Default ở interface con có hiệu lực | Sắp xếp quan hệ kế thừa rõ |
| Hai interface không liên quan có cùng default | Xung đột nếu thiếu class method phân giải | Override và chọn/kết hợp tường minh |
| Hai interface cùng default nhưng có public concrete superclass method tương ứng | Phương thức lớp được ưu tiên | Không cần override chỉ để chọn interface |
| Hai interface độc lập, một abstract và một default tương đương | Có thể xung đột khi kế thừa | Override trong lớp hoặc thiết kế lại hierarchy |
| Phương thức lớp trùng tên nhưng khác tham số | Overload, không phải override | Kiểm tra chữ ký cụ thể |
| Phương thức lớp access hẹp hơn phương thức interface | Lỗi override/implement | Dùng access phù hợp, thường `public` |
| Kiểu trả về/checked `throws` không phù hợp | Lỗi biên dịch | Giữ hợp đồng override hợp lệ |
| Interface cố khai báo `default toString()` | Không hợp lệ | Override `toString()` ở lớp hoặc dùng tên method khác |

## 11. Những sai lầm phổ biến

### Sai lầm 1 — “Interface đứng trước trong `implements` nên thắng”

Không có quy tắc ưu tiên dựa vào vị trí viết:

```java
class Example implements Left, Right {
    @Override
    public String side() {
        return Right.super.side();
    }
}
```

Ở đây kết quả là `right` do **lớp tự chọn**. Không phải do `Right` viết bên phải hay bên trái. Nếu lớp bỏ override và không có phương thức lớp phù hợp khác, hai default độc lập sẽ xung đột.

### Sai lầm 2 — “Có thể ép kiểu để gọi default”

`((Greeter) child).greet()` vẫn gọi implementation trong `Parent` ở ví dụ mục 9. Kiểu biến không đổi hành vi dispatch của instance method.

### Sai lầm 3 — “Một phương thức `abstract` của lớp cha có thể chạy và thắng default”

`abstract` chỉ khai báo hợp đồng, không có thân. Nó có thể ngăn default tự đáp ứng phương thức, nhưng lớp concrete vẫn phải cung cấp implementation. Không gọi “abstract method chạy”.

### Sai lầm 4 — “Tên giống nhau là một phương thức”

`convert(int)` và `convert(String)` có chữ ký khác nhau; không tạo ra tranh chấp override chỉ vì cùng tên. Đặc biệt với generic, cần kiểm tra cả quy tắc erasure và override-equivalent.

### Sai lầm 5 — “Class wins nên mọi method lớp đều hợp lệ”

Phương thức override phải đáp ứng access, kiểu trả về, checked exception, static/instance và các yêu cầu khác. Java báo lỗi biên dịch khi hợp đồng vi phạm, chứ không tùy tiện chuyển về default.

### Sai lầm 6 — “Default method là cách hiện đại để override `Object.toString` trong interface”

Java không cho khai báo `default` override-equivalent với các phương thức không private tương ứng của `Object`. Đặt hành vi dùng chung dưới tên khác hoặc override `toString` ở lớp.

### Sai lầm 7 — “Cứ thêm default là chắc chắn không phá client”

Bổ sung default giúp tương thích trong nhiều tình huống, nhưng không đảm bảo tất cả hệ phân cấp lớp/interface tiếp tục biên dịch. Đặc biệt chú ý xung đột với một interface độc lập và các trường hợp định nghĩa override không tương thích.

## 12. Cách thiết kế và kiểm thử an toàn

**Khi thiết kế interface có default method mới:**

1. Kiểm tra interface đó có triển khai bởi nhiều hệ phân cấp lớp hay không.
2. Xác định chữ ký phương thức muốn thêm, đặc biệt các tên dễ trùng như `name`, `status`, `execute`.
3. Kiểm tra có phương thức public concrete tương đương từ lớp cha không, và chấp nhận rằng implementation lớp được ưu tiên.
4. Kiểm tra các interface độc lập cùng được implement có khai báo default hoặc abstract trùng chữ ký không.
5. Xác minh return type, access, checked exception và các ràng buộc override.
6. Viết unit test cho class cụ thể và cho lời gọi qua biến kiểu interface; cả hai thường phải cho kết quả nhất quán theo dispatch động.
7. Nếu có xung đột, cân nhắc override tường minh hoặc phân tách hành vi, thay vì đặt thứ tự `implements` như một “giải pháp”.
8. Ghi Javadoc cho default method: ý nghĩa mặc định, điều kiện và kỳ vọng đối với implementation override.

**Khi bảo trì một lớp implements nhiều interface:**

- Ưu tiên override tường minh nếu hành vi nghiệp vụ cần rõ ràng hơn default.
- Dùng `@Override` trên phương thức lớp khi ghi đè một hợp đồng interface.
- Nếu đang kế thừa phương thức từ superclass, đừng làm bản sao override chỉ để “chắc chắn thắng”; chỉ thêm override khi nó làm rõ logic hoặc bảo vệ hợp đồng.
- Phân biệt `super.method()` (hệ phân cấp lớp) với `InterfaceName.super.method()` (default của interface cụ thể trong ngữ cảnh hợp lệ).
- Dùng công cụ build/CI và test khi cập nhật interface trong thư viện dùng chung.

## 13. Câu hỏi tự kiểm tra

1. `class C extends P implements I`, trong đó `P` có `public String id()` concrete và `I` có `default String id()`. Nếu `C` không override, phương thức nào được gọi? Vì sao?
2. Nếu biến được khai báo `I x = new C()`, gọi `x.id()` có dùng default của `I` không?
3. Hai interface độc lập `A` và `B` đều có `default void run()`. Lớp concrete `X implements A, B` có cần override không nếu không có method lớp phù hợp? Khi nào quy tắc lớp giúp giải quyết?
4. Nếu superclass có `public abstract void work()` và interface có `default void work()`, lớp concrete có thể bỏ qua việc triển khai `work()` không?
5. Vì sao `default String toString()` trong interface là không hợp lệ? Thay vào đó có thể thiết kế thế nào?
6. Nếu lớp có `run(int)` và interface có `default run(String)`, hai phương thức có cạnh tranh cùng một override không?
7. Có thể dùng `((A) obj).run()` để ép chạy `A` default khi class đã override method không?

**Kết luận:** với phương thức instance có hợp đồng override hợp lệ, **class trước, interface default sau**. Quy tắc áp dụng cho phương thức concrete được **khai báo trực tiếp** hoặc **kế thừa từ superclass**, không phụ thuộc kiểu biến ở vị trí gọi. Nhưng khi gặp `abstract` của superclass, nhiều default từ interface, chữ ký không tương thích hoặc giới hạn của `Object`, phải áp dụng đầy đủ luật kế thừa và override của Java thay vì ghi nhớ một khẩu hiệu đơn lẻ.

## Tài liệu chuẩn

- Java Language Specification (Java SE 25), **`8.4.8 — Inheritance, Overriding, and Hiding**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8
- Java Language Specification (Java SE 25), **`8.4.8.4 — Inheriting Methods with Override-Equivalent Signatures**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.4
- Java Language Specification (Java SE 25), **`9.4 — Abstract Method Declarations / Default Methods**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4
- Oracle Dev.java, **Overriding and Hiding Methods**: https://dev.java/learn/inheritance/overriding/
