# Mục đích kiểm soát tập lớp con trực tiếp với `sealed` trong Java 17+

Khi thiết kế hệ thống hướng đối tượng, một class hoặc interface công khai thường có thể được kế thừa hoặc triển khai bởi nhiều kiểu mới. Tính mở này hữu ích cho extension, nhưng cũng có lúc **tập những biến thể hợp lệ là một phần của mô hình nghiệp vụ**: chẳng hạn chỉ có hai nhóm kết quả được cho phép, một số loại lệnh đã xác định, hay một cây cú pháp có những node categories rõ ràng.

Từ Java 17, `sealed` là tính năng chính thức giúp **kiểm soát chính xác những class hoặc interface nào được phép trực tiếp mở rộng một class, hoặc trực tiếp triển khai/mở rộng một interface**. Cụm từ quan trọng là **trực tiếp**: `sealed` giới hạn *direct subclasses* hoặc *direct subtypes*, chứ không tự động biến mọi hậu duệ nhiều cấp thành một danh sách đóng nếu một nhánh được khai báo `non-sealed`.

~~~java
sealed interface PaymentResult permits Paid, Rejected {
}

record Paid(String receipt) implements PaymentResult {
}

record Rejected(String reason) implements PaymentResult {
}
~~~

Đây là những **khai báo Java 17 hợp lệ**, không có `main`. Interface `PaymentResult` cho phép chính xác `Paid` và `Rejected` **trực tiếp triển khai** nó trong hierarchy này. Hai record đều implicitly final nên không cho subclass nào kế thừa chúng. Nếu một class khác viết `implements PaymentResult` nhưng không được cho phép, compiler sẽ từ chối.

Bài thuộc **Java core – class-object**, nhóm **Lớp sealed**, chủ đề **Mục đích kiểm soát tập lớp con trực tiếp**. Trọng tâm gồm từ khóa `sealed`, danh sách `permits`, ranh giới direct/indirect subtypes, lựa chọn `final`/`sealed`/`non-sealed`, quy tắc package/module, vai trò trong thiết kế mô hình dữ liệu và những điều `sealed` **không bảo đảm**. Các chương trình độc lập chạy bằng **Java 17+**, không bật preview features. Đoạn cố ý lỗi biên dịch được đánh dấu rõ.

## 1. Mục tiêu học tập

Sau bài, bạn cần có thể:

1. Giải thích `sealed` kiểm soát **kiểu con trực tiếp**, không phải chặn mọi polymorphism.
2. Viết đúng `sealed class X permits A, B` với `A extends X`, `B extends X`.
3. Viết `sealed interface I permits A, B` cùng class `implements I` và interface `extends I`.
4. Phân biệt `final`, `sealed`, `non-sealed` tại mỗi direct permitted subtype.
5. Phân tích nhiều cấp kế thừa, nơi nhánh bị đóng hoặc mở lại.
6. Biết khi nào `permits` có thể được suy ra trong cùng compilation unit.
7. Biết các giới hạn vị trí của permitted subtypes trong **named module** và **unnamed module**.
8. Giải thích một sealed class **không nhất thiết abstract** và có thể khởi tạo nếu constructor cho phép.
9. Phân biệt sealed class với enum, record, abstract class và interface mở.
10. Hiểu tác động tới `instanceof`, pattern matching, switch và API evolution trong Java 17.
11. Không đánh đồng một closed hierarchy với ranh giới bảo mật hoặc kiểm soát quyền truy cập.
12. Thiết kế sealed hierarchy tối thiểu, dễ đọc, phù hợp với domain invariants.

## 2. Trước `sealed`: lớp cha mở cho nhiều lớp con

Java hỗ trợ kế thừa class:

~~~java
class Message {
}

class EmailMessage extends Message {
}

class SmsMessage extends Message {
}
~~~

Ba khai báo là Java hợp lệ. Nếu `Message` không phải `final` và constructor thích hợp có thể truy cập, một class thứ tư cũng có thể viết `extends Message` ở phạm vi cho phép.

Trong một framework hoặc thư viện hướng extension, sự linh hoạt này thường là **chủ đích tốt**. Nhưng trong một domain khép kín, việc phát sinh subtype không được mô hình hóa có thể khiến nhiều đoạn code phải dựa vào `else` hoặc dynamic casts, và không thể chắc chắn đã xét hết biến thể.

Đổi sang:

~~~java
sealed class Message permits EmailMessage, SmsMessage {
}

final class EmailMessage extends Message {
}

final class SmsMessage extends Message {
}
~~~

Giờ chỉ **EmailMessage** và **SmsMessage** là hai direct permitted subclasses. Các kiểu khác **không được** trực tiếp extends Message trừ khi thay đổi định nghĩa `permits` theo đúng quy tắc của Java.

**Đừng hiểu** rằng mọi hệ thống nên đóng extension: sealed là một quyết định thiết kế domain. Nếu thư viện của bạn cố ý cho người dùng tạo plugin classes, việc seal superclass có thể phá mục tiêu extensibility.

## 3. Từ khóa `sealed`, `permits`, `final`, `non-sealed`

| Từ khóa | Vai trò |
| --- | --- |
| `sealed` | Giới hạn tập direct permitted subtypes |
| `permits` | Liệt kê những direct subtypes được phép |
| `final` | Không cho class nào kế thừa class này |
| `non-sealed` | Một direct child được cho phép chọn mở lại kế thừa/triển khai như kiểu bình thường |
| `abstract` | Không cho trực tiếp khởi tạo class; không tự hạn chế subtypes |
| `extends` | Khai báo direct superclass của một class, hoặc superinterface của một interface |
| `implements` | Khai báo interfaces mà một class trực tiếp implements |

Ví dụ:

~~~java
sealed abstract class Event permits LoginEvent, OtherEvent {
}

final class LoginEvent extends Event {
}

non-sealed class OtherEvent extends Event {
}
~~~

Đây là ba khai báo hợp lệ. `LoginEvent` là **nhánh đóng hẳn** do final; `OtherEvent` là **nhánh mở lại** do non-sealed.

Một class bất kỳ không thể cứ khai `non-sealed` theo ý mình: modifier này dành cho class/interface có **direct sealed supertype** mà nó được phép kế thừa/triển khai. Nếu không có sealed supertype trực tiếp, `non-sealed` không có cơ sở ngữ nghĩa và bị từ chối.

## 4. Chương trình độc lập 1 — hai lớp con trực tiếp được phép

Tệp **`SealedPaymentDemo.java`**:

~~~java
sealed abstract class Payment permits CashPayment, CardPayment {
    abstract String description();
}

final class CashPayment extends Payment {
    @Override
    String description() {
        return "Cash";
    }
}

final class CardPayment extends Payment {
    @Override
    String description() {
        return "Card";
    }
}

public class SealedPaymentDemo {
    public static void main(String[] args) {
        Payment first = new CashPayment();
        Payment second = new CardPayment();

        System.out.println("first=" + first.description());
        System.out.println("second=" + second.description());
        System.out.println("same type="
                + (first.getClass() == second.getClass()));
        System.out.println("cash is Payment="
                + (first instanceof Payment));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SealedPaymentDemo.java
java SealedPaymentDemo
~~~

**Stdout:**

~~~text
first=Cash
second=Card
same type=false
cash is Payment=true
~~~

`Payment` là sealed abstract class; compiler cho phép hai direct subclasses CashPayment và CardPayment vì chúng có trong permits. Hai subclass đều final nên không mở tiếp cây kế thừa.

**Mục đích sealed không phải làm mất polymorphism:** biến kiểu Payment vẫn có thể trỏ hai runtime types và gọi `description()` theo dynamic dispatch.

## 5. Chính xác: direct subclass là gì?

Xem cây:

~~~text
                 Payment               sealed
                /       \
      CashPayment     CardPayment       direct subclasses
           |               |
       (final)           (final)

Chỉ hai kiểu ở tầng ngay dưới Payment cần được cho phép trực tiếp.
~~~

Với class, **direct subclass** là class có `extends Payment` trực tiếp. Với interface, **direct subtype** trong ngữ cảnh sealed có thể là một class `implements I` trực tiếp hoặc một interface `extends I` trực tiếp.

Giả sử `Payment` cho phép `OnlinePayment` làm direct child, còn OnlinePayment khai `non-sealed`. Khi đó `NewProviderPayment extends OnlinePayment` là **hậu duệ gián tiếp** của Payment. NewProviderPayment **không cần** được kê trong `Payment permits ...` vì nó không trực tiếp extends Payment.

Đây là phân biệt then chốt của bài: **permits chỉ kiểm soát một cạnh kế thừa từ cha sealed tới con trực tiếp**, không phải một whitelist toàn bộ mọi class nằm ở mọi độ sâu của hierarchy.

## 6. Chương trình độc lập 2 — `non-sealed` mở lại nhánh

Tệp **`NonSealedBranchDemo.java`**:

~~~java
sealed abstract class Delivery permits Pickup, Courier {
    abstract String mode();
}

final class Pickup extends Delivery {
    @Override
    String mode() {
        return "pickup";
    }
}

non-sealed class Courier extends Delivery {
    @Override
    String mode() {
        return "courier";
    }
}

final class ExpressCourier extends Courier {
    @Override
    String mode() {
        return "express";
    }
}

public class NonSealedBranchDemo {
    public static void main(String[] args) {
        Delivery a = new Pickup();
        Delivery b = new Courier();
        Delivery c = new ExpressCourier();

        System.out.println(a.mode());
        System.out.println(b.mode());
        System.out.println(c.mode());
        System.out.println("express is Delivery="
                + (c instanceof Delivery));
        System.out.println("express direct parent="
                + c.getClass().getSuperclass().getSimpleName());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NonSealedBranchDemo.java
java NonSealedBranchDemo
~~~

**Stdout:**

~~~text
pickup
courier
express
express is Delivery=true
express direct parent=Courier
~~~

`Delivery permits Pickup, Courier`, **không** có `ExpressCourier`. Vẫn biên dịch đúng vì ExpressCourier trực tiếp extends **Courier**, một permitted child được khai `non-sealed`. Courier có thể có nhiều subclass khác theo các quy tắc kế thừa Java thông thường.

**Kết luận:** sealed hierarchy với nhánh non-sealed **không phải tập hợp đóng toàn bộ concrete classes**. Nó chỉ đóng danh sách **direct children** tại nút sealed.

## 7. Vì sao permitted child phải chọn một trong ba đường?

Một class hoặc interface trực tiếp kế thừa/triển khai sealed supertype phải thể hiện rõ liệu extension **dừng lại, tiếp tục bị kiểm soát hay được mở lại**.

Các lựa chọn:

1. **`final class`**: không còn subclass hợp lệ.
2. **`sealed class` / `sealed interface`**: tiếp tục cho phép chỉ những direct subtypes được chỉ định.
3. **`non-sealed class` / `non-sealed interface`**: trở lại trạng thái mở ở nhánh đó.

Không có `final interface` trong Java. Vì vậy một **permitted subinterface** phải chọn `sealed` hoặc `non-sealed`; còn một **permitted record/enum** vốn có những quy tắc implicitly final hoặc implicitly sealed riêng tùy hình thức (xem phần sau).

Một lỗi thường gặp:

~~~java
sealed class Base permits Child {
}

class Child extends Base {
}
~~~

Đây là **đoạn cố ý không biên dịch**. Child được nêu trong permits, nhưng lại không mang modifier thích hợp (`final`, `sealed`, `non-sealed`) để nói cho compiler biết subclassing từ Child còn có được phép hay không.

Sửa đơn giản nếu Child không cần con: `final class Child extends Base {}`.

## 8. `sealed` cũng có thể lặp qua nhiều tầng

Không nhất thiết mọi permitted direct child phải final. Một child có thể sealed và đặt tiếp danh sách `permits` của riêng mình:

~~~text
          sealed Expression
           /            \
   final Literal      sealed Binary
                        /       \
                    final Add  final Multiply
~~~

Ở cây này:
- Expression chỉ cho Literal và Binary làm **direct children**.
- Binary chỉ cho Add và Multiply làm **direct children** của Binary.
- Literal/Add/Multiply final nên không cho inheritance tiếp.

Cây có thể sâu tùy thiết kế. Mỗi nút sealed **đóng riêng tập direct children** của chính nó. Nếu bất kỳ đường nào chọn non-sealed, các lớp con sâu hơn theo nhánh đó không còn chịu whitelist của nút gốc.

Việc chọn cấu trúc nhiều tầng hữu ích khi domain có **các cấp khái niệm thật**, ví dụ Expression → Binary → Add/Multiply. Không cần tạo tầng sealed mới chỉ để code “trông hiện đại”.

## 9. Chương trình độc lập 3 — hierarchy sealed nhiều cấp

Tệp **`SealedExpressionDemo.java`**:

~~~java
sealed interface Expr permits Literal, Binary {
    int evaluate();
}

record Literal(int value) implements Expr {
    @Override
    public int evaluate() {
        return value;
    }
}

sealed interface Binary extends Expr permits Sum, Product {
}

record Sum(Expr left, Expr right) implements Binary {
    @Override
    public int evaluate() {
        return left.evaluate() + right.evaluate();
    }
}

record Product(Expr left, Expr right) implements Binary {
    @Override
    public int evaluate() {
        return left.evaluate() * right.evaluate();
    }
}

public class SealedExpressionDemo {
    public static void main(String[] args) {
        Expr two = new Literal(2);
        Expr three = new Literal(3);
        Expr sum = new Sum(two, three);
        Expr product = new Product(sum, new Literal(4));

        System.out.println("sum=" + sum.evaluate());
        System.out.println("product=" + product.evaluate());
        System.out.println("sum implements Binary="
                + (sum instanceof Binary));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SealedExpressionDemo.java
java SealedExpressionDemo
~~~

**Stdout:**

~~~text
sum=5
product=20
sum implements Binary=true
~~~

`Expr` permits đúng Literal và Binary. `Binary` là **subinterface trực tiếp** của Expr và được phép bởi Expr, nhưng nó tự sealed để giới hạn direct children thành Sum và Product.

Hai records Sum/Product implicitly final: chúng không cần viết `final` tường minh. Đây là cách kết hợp **sealed interface + record** thường có ích cho biểu diễn cấu trúc dữ liệu có tập biến thể rõ.

## 10. Class sealed và interface sealed có gì khác?

**Sealed class:**
- Direct subclass phải `extends` class đó và có trong permits.
- Một class Java có **một** direct superclass.
- Parent class có thể có state, constructors và shared implementations.
- Một class sealed có thể abstract hoặc concrete.

**Sealed interface:**
- Direct implementing class hoặc direct extending interface phải hợp lệ theo permits.
- Một class Java có thể implements **nhiều interfaces** (chịu quy tắc sealed của từng interface).
- Interface không có instance constructor/instance fields như class.
- Sealed interface rất phù hợp với **sum type-like models**: một giá trị có thể thuộc một trong vài variants được công nhận.

Với cả hai, permits không có tác dụng cấp quyền truy cập vào private members. Nó là **ràng buộc khai báo quan hệ subtype**, không thay `public`, `protected`, package-private hay `private`.

## 11. Chương trình độc lập 4 — một sealed interface với hai record variants

Tệp **`ResultVariantsDemo.java`**:

~~~java
sealed interface ApiResult permits Success, Failure {
}

record Success(String value) implements ApiResult {
}

record Failure(int code, String message) implements ApiResult {
}

public class ResultVariantsDemo {
    static String describe(ApiResult result) {
        if (result instanceof Success success) {
            return "OK:" + success.value();
        }
        if (result instanceof Failure failure) {
            return "ERROR:" + failure.code()
                    + ":" + failure.message();
        }
        throw new IllegalStateException("Unknown variant");
    }

    public static void main(String[] args) {
        ApiResult a = new Success("saved");
        ApiResult b = new Failure(404, "missing");

        System.out.println(describe(a));
        System.out.println(describe(b));
        System.out.println("same variant="
                + (a.getClass() == b.getClass()));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 ResultVariantsDemo.java
java ResultVariantsDemo
~~~

**Stdout:**

~~~text
OK:saved
ERROR:404:missing
same variant=false
~~~

Trong **Java 17**, pattern variable `success` hoặc `failure` trong `instanceof` đã là tính năng chuẩn, không cần preview. Method describe xử lý hai biến thể đã biết và có đường `throw` nếu giả thiết về hierarchy không còn đúng.

Nhưng **Java 17 không có exhaustiveness checking tổng quát cho chuỗi if/instanceof**. Nếu sau này thêm một permitted variant, chính bạn vẫn phải kiểm tra logic của method describe. Ngoài ra, sealed không cấm biến `ApiResult result` mang `null`, nên `null` sẽ đi tới `throw` trong ví dụ này.

## 12. Mục đích thiết kế: làm tập biến thể có ý nghĩa

Tại sao một domain muốn giới hạn direct subtypes?

**1. Diễn đạt hợp đồng rõ ràng.** Khi API nói một kết quả là Success hoặc Failure, mọi người cùng hiểu tập **direct variants** đã được mô tả, thay vì cho một plugin bất kỳ trực tiếp implement ApiResult.

**2. Bảo vệ các giả định trong model.** Nếu nghiệp vụ có ba lệnh được công nhận, một subtype lạ được sinh ra ngoài thư viện có thể khiến code xử lý sai hoặc cần fallback không mong muốn.

**3. Hỗ trợ phân tích ở compile time.** Java biết danh sách permitted subtypes từ declaration và kiểm tra quan hệ inheritance/implementation, kể cả khi các classes nằm ở các file khác nhau trong phạm vi module/package hợp lệ.

**4. Hỗ trợ người đọc và công cụ.** Trình biên dịch, IDE và các công cụ đọc type hierarchy có thể nhận ra những direct variants đã cho phép.

**5. Cho phép “đóng có chọn lọc”.** Bạn vẫn có thể dành một nhánh `non-sealed` cho extension, thay vì chỉ có hai cực “mở hoàn toàn” hoặc “final tất cả”.

**6. Tổ chức domain API theo ý định.** Một API công bố ít variants chính và giữ details ở các subtype tương ứng, thay vì phân tán “magic string type” qua nhiều nơi.

Không nên diễn giải sealed như công nghệ sandbox/security chống mã độc; nó **không kiểm soát quyền gọi methods hoặc đọc dữ liệu**.

## 13. `non-sealed interface` cũng mở lại nhánh

Với một sealed interface:

~~~java
sealed interface Message permits TextMessage, ExtensionMessage {
}

record TextMessage(String value) implements Message {
}

non-sealed interface ExtensionMessage extends Message {
}
~~~

Các khai báo trên hợp lệ. `TextMessage` là record final; `ExtensionMessage` là một subinterface trực tiếp đã được phép nhưng cho phép các classes/interfaces hợp lệ ở những vị trí khác tiếp tục `implements/extends ExtensionMessage`.

Một class `PluginMessage implements ExtensionMessage` sẽ **gián tiếp** implement Message. Nó không được liệt kê trong `Message permits ...` bởi vì direct superinterface mà nó implements là ExtensionMessage.

Nếu bạn chọn `non-sealed`, hãy bảo đảm đây là một **extension point có chủ đích**; nếu không, nhánh mở có thể làm mất lợi ích kiểm soát toàn bộ những concrete implementations phía dưới.

## 14. Chương trình độc lập 5 — interface mở lại với plugin subtype

Tệp **`OpenInterfaceBranchDemo.java`**:

~~~java
sealed interface Operation permits ReadOperation, CustomOperation {
    String name();
}

record ReadOperation(String path) implements Operation {
    @Override
    public String name() {
        return "read:" + path;
    }
}

non-sealed interface CustomOperation extends Operation {
}

final class BackupOperation implements CustomOperation {
    @Override
    public String name() {
        return "backup";
    }
}

public class OpenInterfaceBranchDemo {
    public static void main(String[] args) {
        Operation first = new ReadOperation("/data");
        Operation second = new BackupOperation();

        System.out.println(first.name());
        System.out.println(second.name());
        System.out.println("backup is CustomOperation="
                + (second instanceof CustomOperation));
        System.out.println("backup is Operation="
                + (second instanceof Operation));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 OpenInterfaceBranchDemo.java
java OpenInterfaceBranchDemo
~~~

**Stdout:**

~~~text
read:/data
backup
backup is CustomOperation=true
backup is Operation=true
~~~

`Operation` chỉ permits `ReadOperation` và `CustomOperation` trực tiếp. `BackupOperation` không trực tiếp implements Operation; nó implements một `non-sealed` subinterface.

**Đây không phải cách “lách lỗi của Java”.** Đây chính là tác dụng được thiết kế của non-sealed: cho phép nhà thiết kế API chọn điểm mở rộng cụ thể.

## 15. Quy tắc `permits` và direct inheritance phải khớp nhau

Ví dụ hợp lệ:

~~~java
sealed class Vehicle permits Car, Bicycle {
}

final class Car extends Vehicle {
}

final class Bicycle extends Vehicle {
}
~~~

Nếu liệt kê `Car` nhưng Car thực tế không `extends Vehicle` trực tiếp, khai báo permits đó không hợp lệ. Tương tự, nếu một class `Bus extends Vehicle` trực tiếp mà không được nêu (hoặc không thuộc danh sách permits suy ra hợp lệ), compiler sẽ từ chối.

Các điều kiện quan trọng:

- Permitted direct subtype phải có quan hệ `extends` hoặc `implements` **trực tiếp** đúng với sealed supertype.
- Modifier của permitted child phải chọn trạng thái extension đúng: final/sealed/non-sealed, hoặc các trường hợp implicitly final/sealed của enum/record.
- Tên trong permits phải trỏ tới những kiểu hợp lệ, được resolve phù hợp.
- Không được khai các subtype trực tiếp ở một module/package không được phép theo các quy tắc của Java 17.
- Không thể dùng `permits` để cho phép một subclass vốn bị **final class** cấm; phải định nghĩa base sealed đúng cách.
- Các luật accessibility/constructor vẫn áp dụng: có tên trong permits không tự mở quyền vào constructor private không truy cập được.

## 16. Khi nào có thể bỏ `permits`?

Có thể bỏ `permits` khi sealed type và các direct permitted subtypes được khai báo phù hợp **trong cùng compilation unit** (thường là cùng file `.java`), và đủ điều kiện khác của JLS:

~~~java
sealed interface Token {}
record NumberToken(int value) implements Token {}
record WordToken(String text) implements Token {}
~~~

Compiler suy ra hai permitted direct implementations. Điều này **không tìm tự động mọi Java file cùng package/module** và không mở cửa cho một third-party subtype ngoài danh sách. Nếu định chuyển permitted types sang các file khác, hãy viết `permits` tường minh. Bài **Điều kiện suy ra danh sách lớp con khi bỏ permits** phân tích cả canonical name, local/anonymous types, nested declarations và compilation units.

## 17. Chương trình độc lập 6 — `permits` được suy ra trong một file

Tệp **`InferredPermitsDemo.java`**:

~~~java
sealed interface Token {
}

record NumberToken(int value) implements Token {
}

record WordToken(String text) implements Token {
}

public class InferredPermitsDemo {
    static String describe(Token token) {
        if (token instanceof NumberToken number) {
            return "number=" + number.value();
        }
        if (token instanceof WordToken word) {
            return "word=" + word.text();
        }
        throw new IllegalArgumentException("not supported");
    }

    public static void main(String[] args) {
        Token first = new NumberToken(7);
        Token second = new WordToken("java");

        System.out.println(describe(first));
        System.out.println(describe(second));
        System.out.println("first Token="
                + (first instanceof Token));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 InferredPermitsDemo.java
java InferredPermitsDemo
~~~

**Stdout:**

~~~text
number=7
word=java
first Token=true
~~~

Không có `permits` được viết trong Token, nhưng compiler có thể suy ra hai direct implementations cùng compilation unit. Cả hai là records final, nên hierarchy trong ví dụ không mở thêm classes thông qua chúng.

Nếu tách hai records ra file khác mà không cập nhật sealed declaration, cần xem lại `permits` và phạm vi module/package cho phù hợp.

## 18. `permits` và Java modules: giới hạn nơi đặt subtype

Vị trí các permitted direct subtypes chịu thêm một ranh giới:

| Sealed parent ở đâu? | Những direct types được phép phải ở đâu? |
| --- | --- |
| **Named module** | **Cùng named module**, có thể khác package nếu visibility cho phép |
| **Unnamed module** (classpath) | **Cùng package** |

`permits` không tự cấp quyền truy cập type/constructor hoặc bypass Java module visibility. Quy tắc này bảo vệ ownership của sealed API chứ không phải cơ chế runtime plugin registration. Bài **Ràng buộc cùng module hoặc cùng package** có ví dụ biên dịch nhiều file, `module-info.java`, exported package và classpath/module-path.

## 19. Minh họa nhiều file cùng package trong unnamed module

Ví dụ giả định các file đặt chung trong package `example.model` và không dùng named module.

**`Outcome.java`**:

~~~java
package example.model;

public sealed interface Outcome permits Good, Bad {
}
~~~

**`Good.java`**:

~~~java
package example.model;

public record Good(String value) implements Outcome {
}
~~~

**`Bad.java`**:

~~~java
package example.model;

public record Bad(String reason) implements Outcome {
}
~~~

Đây là ba file **hợp lệ trong cùng package**, không phải một chương trình có main. Các records được khai `public` nên mỗi record nằm trong file tương ứng đúng tên.

Nếu chuyển `Good` sang package khác trong **unnamed module**, việc trực tiếp implements Outcome không còn thỏa yêu cầu cùng package của sealed hierarchy. Nếu dùng **named module**, các permitted subtypes có thể thuộc nhiều packages trong cùng module theo luật của Java; vẫn cần xử lý visibility và dependencies hợp lệ.

Lợi ích của ví dụ nhiều file là làm rõ **`permits` công khai danh sách**, trong khi type declarations có thể được tổ chức thành các file độc lập.

## 20. Named module không có nghĩa permitted class được ở mọi nơi

Ngay cả khi sealed interface được `public` và export từ named module, một module bên ngoài **không được tự bổ sung direct permitted implementation**. Mở API cho plugins phải là quyết định thiết kế rõ ràng:

- Root có thể permits một `non-sealed` extension interface/class trong cùng named module; bên thứ ba triển khai **nhánh mở** ấy.
- Hoặc dùng ordinary open interface/strategy, nếu extensibility là yêu cầu chính.
- Các access/`exports`/`requires` và constructor restrictions vẫn cần hợp lệ.

Đừng cố “vượt” sealed bằng custom class loader hoặc reflection. Đây chỉ là bản đồ khái niệm; bài **Ràng buộc cùng module hoặc cùng package** có source layout cụ thể, còn bài **So sánh hệ phân cấp đóng với lớp tự do mở rộng** phân tích API trade-offs.

## 21. Sealed class có thể không `abstract`

Một hiểu lầm phổ biến: “sealed nghĩa là abstract, nên không tạo trực tiếp được object”. Đây là **sai**.

`sealed` chỉ giới hạn việc **tạo subtype trực tiếp**, không mặc nhiên cấm `new` trên chính sealed class. Nếu sealed class không abstract và constructor có thể truy cập, bạn vẫn có thể tạo instance của nó.

~~~java
sealed class Animal permits Dog {
    String voice() {
        return "animal";
    }
}

final class Dog extends Animal {
    @Override
    String voice() {
        return "woof";
    }
}
~~~

Đây là hai class declarations hợp lệ. Trong cùng package, có thể viết `new Animal()` lẫn `new Dog()`.

Nếu domain muốn base type chỉ là một abstraction và mọi object phải thuộc một variant cụ thể, hãy thêm **`abstract`** cho sealed class. `abstract` và `sealed` phục vụ hai mục tiêu khác nhau, có thể kết hợp.

## 22. Chương trình độc lập 7 — concrete sealed superclass vẫn khởi tạo được

Tệp **`ConcreteSealedClassDemo.java`**:

~~~java
sealed class Animal permits Dog {
    String voice() {
        return "animal";
    }
}

final class Dog extends Animal {
    @Override
    String voice() {
        return "woof";
    }
}

public class ConcreteSealedClassDemo {
    public static void main(String[] args) {
        Animal base = new Animal();
        Animal dog = new Dog();

        System.out.println("base=" + base.voice());
        System.out.println("dog=" + dog.voice());
        System.out.println("base is Dog="
                + (base instanceof Dog));
        System.out.println("dog is Animal="
                + (dog instanceof Animal));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ConcreteSealedClassDemo.java
java ConcreteSealedClassDemo
~~~

**Stdout:**

~~~text
base=animal
dog=woof
base is Dog=false
dog is Animal=true
~~~

Animal không abstract nên tạo trực tiếp được. Điều được kiểm soát bằng sealed là **không có một direct subclass mới ngoài Dog** trong hierarchy hợp lệ, chứ không phải việc tạo instances của Animal.

## 23. `abstract sealed` để đóng tập concrete variants

Khi base type chỉ đại diện cho một khái niệm mà không phải một biến thể dữ liệu cụ thể, lựa chọn này thường phù hợp:

~~~java
abstract sealed class Document
        permits Invoice, Receipt {
    abstract String kind();
}

final class Invoice extends Document {
    @Override
    String kind() {
        return "invoice";
    }
}

final class Receipt extends Document {
    @Override
    String kind() {
        return "receipt";
    }
}
~~~

Đây là các declarations hợp lệ. `new Document()` không hợp lệ vì Document **abstract**; `new Invoice()` và `new Receipt()` hợp lệ.

**Nếu cả Invoice và Receipt final**, và không có non-sealed branch, mọi concrete subclass thuộc đúng một trong hai direct variants ấy. Đây là mô hình đóng tương tự một danh sách variant types nhưng mỗi variant vẫn có thể có logic, state và hành vi của class.

Nên dùng sealed abstract class nếu variants cần chia sẻ **constructor, protected state hoặc implementations**. Nếu chủ yếu cần value variants và multiple interface implementation, sealed interface + records thường đơn giản hơn.

## 24. Chương trình độc lập 8 — abstract sealed class giữ contract

Tệp **`AbstractSealedDocumentDemo.java`**:

~~~java
abstract sealed class Document
        permits Invoice, Receipt {
    abstract String kind();
}

final class Invoice extends Document {
    @Override
    String kind() {
        return "invoice";
    }
}

final class Receipt extends Document {
    @Override
    String kind() {
        return "receipt";
    }
}

public class AbstractSealedDocumentDemo {
    static String label(Document doc) {
        return "type=" + doc.kind();
    }

    public static void main(String[] args) {
        Document first = new Invoice();
        Document second = new Receipt();

        System.out.println(label(first));
        System.out.println(label(second));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AbstractSealedDocumentDemo.java
java AbstractSealedDocumentDemo
~~~

**Stdout:**

~~~text
type=invoice
type=receipt
~~~

Cả hai concrete types thực hiện abstract method `kind()`. Sealed đưa ra whitelist direct subclasses, abstract yêu cầu implementations và cấm instantiate Document trực tiếp; dynamic dispatch vẫn hoạt động như class inheritance thông thường.

## 25. `record` thường là direct variant của sealed interface

Record là một class implicitly final. Vì vậy, dùng record để biểu diễn mỗi variant của sealed interface rất hợp lý:

~~~java
sealed interface Command permits Create, Delete {
}

record Create(String id) implements Command {
}

record Delete(String id) implements Command {
}
~~~

Các declarations hợp lệ. Nếu muốn thêm `Update` là một direct variant, phải điều chỉnh `Command permits ...` và khai báo `record Update(...)` trong boundary được phép.

**Không thể** để record `extends` một sealed class tùy ý: record luôn extends `java.lang.Record` và không thể extends class khác. Muốn dùng records làm variants, chọn **sealed interface** để chúng trực tiếp implements.

Đây cũng là lý do sealed interface phù hợp với các loại request/result/command kiểu dữ liệu: mỗi variant có một cấu trúc component riêng, và parent type biểu diễn “một trong những variants này”.

## 26. Chương trình độc lập 9 — closed command model bằng sealed + record

Tệp **`SealedCommandDemo.java`**:

~~~java
sealed interface Command permits Create, Delete, Rename {
}

record Create(String id) implements Command {
}

record Delete(String id) implements Command {
}

record Rename(String id, String newName) implements Command {
}

public class SealedCommandDemo {
    static String describe(Command command) {
        if (command instanceof Create c) {
            return "create:" + c.id();
        }
        if (command instanceof Delete d) {
            return "delete:" + d.id();
        }
        if (command instanceof Rename r) {
            return "rename:" + r.id() + "->" + r.newName();
        }
        throw new IllegalArgumentException("invalid command");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Create("A")));
        System.out.println(describe(new Rename("A", "B")));
        System.out.println(describe(new Delete("B")));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SealedCommandDemo.java
java SealedCommandDemo
~~~

**Stdout:**

~~~text
create:A
rename:A->B
delete:B
~~~

Các record variants là implicitly final và mang dữ liệu bằng record components. Trong Java 17, `instanceof` type patterns đã đủ để nhận biết biến thể mà không cần cast thủ công.

**Lưu ý:** method describe viết if/else với `throw` cuối; compiler Java 17 **không tự chứng minh chuỗi if xử lý exhaustive sealed hierarchy**. Đừng xóa nhánh cuối chỉ vì tin rằng sealed sẽ biến method thành một switch expression hoàn chỉnh.

## 27. Java 17 và `switch`: tránh nhầm release

Một số ví dụ trên Internet viết:

~~~java
// Minh họa CÚ PHÁP KHÔNG phải switch sealed-type
// ổn định trong Java 17 không bật preview:
// return switch (command) {
//     case Create c -> ...;
//     case Delete d -> ...;
// };
~~~

Với **Java 17 không bật preview**, bạn không thể dùng switch pattern matching tổng quát trên sealed interface theo cách ổn định như trong những Java releases mới hơn. `switch` truyền thống của Java 17 hỗ trợ selectors như **enum**, strings và những integral types được quy định; không tự cho arbitrary sealed interface làm selector.

**Bạn có thể làm trong Java 17 chuẩn:**

~~~java
if (command instanceof Create create) {
    return "create:" + create.id();
}
~~~

Đây là snippet hợp lệ bên trong method trả String và có biến Command tương ứng.

**Pattern matching for switch** có lịch sử preview và được chuẩn hóa ở Java 21 (JEP 441). Khi đọc tài liệu Java mới, luôn đối chiếu version và có hay không `--enable-preview` trước khi copy ví dụ. Bài này chủ động không sử dụng preview.

Việc sealed giúp compiler/tooling hiểu tập permitted direct subtypes **không có nghĩa mọi cú pháp phân tích hierarchy đều khả dụng trong mọi Java release**.

## 28. So sánh `sealed`, `final`, `enum`, `record`

Các keyword này giải quyết **những trục khác nhau**:

| Cơ chế | Ràng buộc |
| --- | --- |
| `final class` | Cấm lớp con khác kế thừa trực tiếp |
| `sealed class/interface` | Cho phép một danh sách **direct subtypes** được kiểm soát |
| `non-sealed` direct child | Mở lại một nhánh hợp lệ |
| `abstract class` | Không instantiate base class trực tiếp |
| `record` | Data carrier là class implicitly final |
| `enum` | Một tập enum constants theo khai báo, không phải tập tùy ý những class con |

`sealed interface + record` thường hợp với variants có payload khác kiểu; `enum` tốt cho tập giá trị tên cố định; `sealed abstract class` có thể chia sẻ state/constructors. Records không thể extends một superclass ứng dụng vì đã extends `java.lang.Record`. Bài **Kết hợp sealed với lớp abstract, record và enum** phân tích sâu các tổ hợp, giá trị bất biến và trường hợp enum có constant-specific bodies.

## 29. Chương trình độc lập 10 — enum và record cùng nằm trong sealed interface

Tệp **`MixedVariantsDemo.java`**:

~~~java
sealed interface AccessEvent
        permits AccessLevel, TemporaryAccess {
}

enum AccessLevel implements AccessEvent {
    GUEST, MEMBER, ADMIN
}

record TemporaryAccess(int minutes) implements AccessEvent {
}

public class MixedVariantsDemo {
    static String label(AccessEvent event) {
        if (event instanceof AccessLevel level) {
            return "level:" + level.name();
        }
        if (event instanceof TemporaryAccess temporary) {
            return "minutes:" + temporary.minutes();
        }
        throw new IllegalArgumentException("unknown event");
    }

    public static void main(String[] args) {
        AccessEvent permanent = AccessLevel.ADMIN;
        AccessEvent temporary = new TemporaryAccess(15);

        System.out.println(label(permanent));
        System.out.println(label(temporary));
        System.out.println("admin enum="
                + (permanent instanceof AccessLevel));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 MixedVariantsDemo.java
java MixedVariantsDemo
~~~

**Stdout:**

~~~text
level:ADMIN
minutes:15
admin enum=true
~~~

`AccessLevel` enum (không có constant-specific class bodies) implicitly final và là một permitted direct implementor. `TemporaryAccess` record cũng final. `AccessEvent` chỉ có **hai direct permitted implementing types**, dù AccessLevel có **ba enum instances**.

Điều này nhấn mạnh khác biệt giữa **tập subtype** và **tập object instances/constants**. Sealed điều khiển subtype relation, enum điều khiển các named constants.

## 30. Những trường hợp lỗi thường gặp khi khai `sealed`

Các snippets trong mục này **cố ý không biên dịch**; mỗi trường hợp được xem độc lập, không ghép các khai báo trùng tên vào cùng file.

**A. Một direct subclass không được cho phép:**

~~~java
sealed class Base permits Good {
}

final class Good extends Base {
}

// CỐ Ý KHÔNG BIÊN DỊCH nếu bỏ comment:
// final class Surprise extends Base {}
~~~

**B. Permitted direct subclass quên chỉ rõ trạng thái tiếp tục:**

~~~java
sealed class Base permits Good {
}

// CỐ Ý KHÔNG BIÊN DỊCH:
class Good extends Base {
}
~~~

**C. Permits một kiểu không direct extends superclass:**

~~~java
sealed class Base permits Good {
}

// CỐ Ý KHÔNG BIÊN DỊCH:
final class Good {
}
~~~

**D. Dùng `non-sealed` khi không có sealed direct supertype:**

~~~java
class Ordinary {
}

// CỐ Ý KHÔNG BIÊN DỊCH:
non-sealed class Child extends Ordinary {
}
~~~

**E. Dùng `sealed final` đồng thời:**

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
sealed final class Impossible {
}
~~~

`sealed` đòi cho phép các direct children hợp lệ; `final` lại cấm mọi subclass. Java không cho áp cả hai modifiers trên cùng class.

**F. Cố implements trực tiếp sealed interface không được nêu:**

~~~java
sealed interface Event permits Known {
}

final class Known implements Event {
}

// CỐ Ý KHÔNG BIÊN DỊCH nếu bỏ comment:
// record Unknown(String data) implements Event {}
~~~

**G. Sealed interface dùng làm lambda target:**

~~~java
sealed interface Task permits NamedTask {
    void run();
}

final class NamedTask implements Task {
    @Override
    public void run() {
    }
}

// CỐ Ý KHÔNG BIÊN DỊCH trong method:
// Task task = () -> System.out.println("run");
~~~

Ngay cả khi interface chỉ khai một abstract method, **sealed interface không phải functional interface** theo JLS vì functional interface phải không được khai `sealed`. Hãy dùng một `@FunctionalInterface` riêng không sealed để nhận lambda nếu API cần callbacks dạng function.

## 31. Một số giới hạn thiết kế tinh tế

**Permits không tự cấp constructor access.** Một child được phép vẫn phải gọi superclass constructor có thể truy cập; constructor private không thành public nhờ permits.

**Permits không làm bất biến instance state.** Sealed class vẫn có thể có mutable fields và setters. Một record variant mang mutable List cũng chỉ có shallow immutability trừ khi chủ động copy.

**Permits không tạo factory tự động.** Caller vẫn dùng constructors/factories phù hợp. Không có cơ chế runtime bắt buộc phải duyệt tất cả permitted types để khởi tạo.

**Sealed không cấm dùng interface khác.** Một class permitted subtype có thể implements thêm interfaces, nếu không trái các luật Java khác.

**Sealed không bảo đảm exhaustive `if` trong Java 17.** Bạn có thể thiết kế một danh sách variants đóng mà method if/instanceof vẫn quên xử lý một nhánh khi code được thay đổi.

**Không lạm dụng `non-sealed`.** Chỉ cần một nhánh mở, mô hình toàn bộ descendants sẽ không còn đóng như người đọc có thể tưởng tượng.

## 32. Quy tắc reflection: quan sát permitted direct subclasses

Java 17 cung cấp reflection APIs liên quan sealed types:

- `Class.isSealed()`: class/interface runtime type có được khai sealed không.
- `Class.getPermittedSubclasses()`: trả array mô tả **các direct permitted subclasses/subinterfaces** được khai báo cho sealed type; với loại không sealed, kết quả có thể là null theo API.

Quan trọng: API reflection chỉ nên được dùng khi thật sự cần metadata (tooling, framework, diagnostics). Business logic không nên phải duyệt reflection trên mỗi request chỉ để phân loại một vài variants đã biết.

**Không suy** rằng `getPermittedSubclasses()` là “tất cả concrete objects/descendants”. Nếu có non-sealed branch, hàng loạt kiểu mới bên dưới branch không nhất thiết nằm trong array của sealed ancestor.

**Thứ tự array** không nên được dùng làm business ranking. Nếu cần thứ tự định nghĩa từ domain, biểu diễn nó riêng bằng một field hoặc explicit list có chính sách rõ.

## 33. Chương trình độc lập 11 — reflection quan sát đúng direct permits

Tệp **`SealedReflectionDemo.java`**:

~~~java
import java.util.Arrays;

sealed interface Root permits DirectLeaf, OpenBranch {
}

final class DirectLeaf implements Root {
}

non-sealed class OpenBranch implements Root {
}

final class IndirectLeaf extends OpenBranch {
}

public class SealedReflectionDemo {
    public static void main(String[] args) {
        Class<Root> root = Root.class;

        System.out.println("root sealed=" + root.isSealed());
        System.out.println("open sealed="
                + OpenBranch.class.isSealed());

        String[] names = Arrays.stream(
                root.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);

        System.out.println("direct="
                + Arrays.toString(names));
        System.out.println("indirect Root="
                + (new IndirectLeaf() instanceof Root));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SealedReflectionDemo.java
java SealedReflectionDemo
~~~

**Stdout:**

~~~text
root sealed=true
open sealed=false
direct=[DirectLeaf, OpenBranch]
indirect Root=true
~~~

`Root.getPermittedSubclasses()` cho danh sách **direct subtypes được phép**: DirectLeaf và OpenBranch. IndirectLeaf **không** xuất hiện vì nó extends OpenBranch, chứ không trực tiếp implements Root.

Ví dụ chủ động sort theo tên trước khi in, nên không dựa vào thứ tự entries từ reflection. `OpenBranch.class.isSealed()` false vì nhánh này được khai non-sealed.

## 34. Những thay đổi API khi thêm một permitted child

Thêm một permitted direct subtype, chẳng hạn `Pending` vào `Outcome permits Success, Failure`, là **thay đổi hợp đồng API**, không chỉ thêm file. Phải kiểm consumers, serialization/schema, business dispatch và các tests đang giả định chỉ có hai variants.

Trong Java 17 tiêu chuẩn không bật preview, chuỗi `if/else instanceof` không được compiler chứng minh exhaustive chỉ nhờ sealed; Java 21+ có những khả năng kiểm tra pattern switch khác. Duy trì fallback có chủ đích, kiểm thử các nhánh và versioning hợp lý. Nếu ecosystem cần tạo variants độc lập, cân nhắc một `non-sealed` extension point thay vì hứa hierarchy luôn đóng. Bài **So sánh hệ phân cấp đóng với lớp tự do mở rộng** đi sâu vào OCP, binary/source compatibility và cost of evolution.

## 35. Sealed hierarchy không phải biện pháp phân quyền

Một sealed interface có thể nói “chỉ những class trong permits trực tiếp implements tôi”. Nó **không** nói rằng:

- Người dùng đã được xác thực.
- Request đáng tin và không cần validate.
- Một subtype mặc nhiên có quyền truy cập database.
- Một object không thể bị mutate.
- Dữ liệu đã được escape chống injection.
- Reflection/deserialization luôn an toàn.
- API endpoint được bảo vệ khỏi access trái phép.

Ví dụ, `record AdminCommand(String userId) implements Command` không tự chứng minh caller được quyền thực hiện lệnh admin. **Authorization** phải được kiểm tra dựa trên principal, resource và policy thực tế.

Sealed cung cấp **type-hierarchy constraint**, không thay authentication, authorization, validation hoặc serialization hardening.

## 36. Khi nào sealed làm thiết kế tốt hơn?

Sealed phù hợp khi **một owner kiểm soát tập biến thể trực tiếp**, domain biết rõ những loại chính, và việc thêm loại mới cần được xem như thay đổi API. Ví dụ: kết quả Success/Failure với payload khác nhau, các node của AST, những trạng thái workflow có dữ liệu riêng.

Không nên seal chỉ để “hiện đại hóa”: ordinary interface có thể tốt hơn nếu mục tiêu chính là plugin extension; `enum` đơn giản hơn nếu chỉ cần các nhãn hằng, và composition/strategy hữu ích khi hành vi biến đổi nhưng data shape không cần một cây variants. Các nhánh `non-sealed` làm root không còn đóng hoàn toàn về hậu duệ. Bài **Khi nào sealed phù hợp để mô hình hóa các loại giá trị** và bài **So sánh hệ phân cấp đóng với lớp tự do mở rộng** cung cấp decision matrix và mẫu domain cụ thể.

## 37. Dynamic dispatch vẫn đúng như cũ

Khi caller giữ một reference kiểu sealed base class/interface, Java vẫn dispatch virtual methods theo runtime type như bình thường.

~~~java
sealed interface Formatter permits Plain, Upper {
    String format(String value);
}

final class Plain implements Formatter {
    public String format(String value) {
        return value;
    }
}

final class Upper implements Formatter {
    public String format(String value) {
        return value.toUpperCase(
                java.util.Locale.ROOT);
    }
}
~~~

Các declarations hợp lệ. Sealed chỉ quyết định kiểu nào **được** implements Formatter trực tiếp, không đổi luật gọi `formatter.format(...)`.

Vì vậy nhiều khi **không cần** if/instanceof: caller có thể gọi method trên base interface và để polymorphism chọn implementation. Chỉ dùng type tests khi thật sự cần xử lý theo variant cụ thể thay vì hành vi chung.

## 38. Chương trình độc lập 12 — polymorphism trong sealed interface

Tệp **`SealedPolymorphismDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;

sealed interface Formatter permits Plain, Upper {
    String format(String input);
}

final class Plain implements Formatter {
    @Override
    public String format(String input) {
        return input;
    }
}

final class Upper implements Formatter {
    @Override
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}

public class SealedPolymorphismDemo {
    public static void main(String[] args) {
        List<Formatter> formatters =
                List.of(new Plain(), new Upper());

        for (Formatter formatter : formatters) {
            System.out.println(formatter.format("Java"));
        }

        System.out.println("formatter count="
                + formatters.size());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SealedPolymorphismDemo.java
java SealedPolymorphismDemo
~~~

**Stdout:**

~~~text
Java
JAVA
formatter count=2
~~~

Sealed không buộc caller phải viết `instanceof` trong mọi method. Khi polymorphic API đã đủ, người dùng chỉ gọi `format` và implementation thực hiện công việc tương ứng.

## 39. Quy trình thiết kế một sealed hierarchy đúng

Trước khi viết code, đi theo trình tự:

1. **Xác định miền khái niệm:** PaymentResult, Expr, Command, không phải một Base chung chung.
2. **Liệt kê direct variants thực sự:** mỗi class/interface có vai trò domain riêng.
3. **Chọn sealed class hay interface:** có cần shared superclass state/constructors không?
4. **Định nghĩa boundary package/module:** direct subtypes có ở đúng nơi JLS cho phép không?
5. **Viết `permits` tường minh** nếu hierarchy trải nhiều files hoặc cần public contract dễ nhìn.
6. **Chọn modifier cho mỗi direct subtype:** final, sealed hoặc non-sealed; không bỏ qua.
7. **Thiết kế cấp thứ hai nếu cần:** mỗi sealed child có permits riêng.
8. **Quyết định có nhánh mở không:** nếu dùng non-sealed, tài liệu hóa extension point.
9. **Định nghĩa shared behavior rõ:** virtual methods hoặc value components.
10. **Thiết kế invariant/validation:** sealed không thay constructor checks.
11. **Xử lý `null`:** một biến kiểu sealed interface vẫn có thể null.
12. **Chọn xử lý variant trong Java 17:** polymorphism/instanceof patterns, không phụ thuộc pattern switch chưa ổn định.
13. **Xem xét equality, serialization và API evolution:** các records/classes variants có hợp đồng gì?
14. **Viết negative compile tests hoặc kiểm tra với compiler:** subclass không được phép phải fail compile.
15. **Đọc lại hierarchy:** direct subclasses có đủ ý nghĩa, hay đang lạm dụng nhiều tầng trung gian?

## 40. Những hiểu lầm cần tránh

| Hiểu lầm | Điều đúng |
| --- | --- |
| `sealed` cấm mọi subclass ở mọi tầng | Nó hạn chế **direct** subtypes; non-sealed có thể mở lại nhánh |
| Có permits thì không cần `extends`/`implements` | Phải khai báo direct inheritance đúng |
| Permitted child không cần modifier nào | Child cần final/sealed/non-sealed theo rules |
| `final` và `sealed` giống nhau | Final không cho subclass; sealed cho phép danh sách chọn |
| `non-sealed` nghĩa là class không có cha sealed | Ngược lại, nó dành cho direct subtype của sealed |
| Sealed interface dùng được làm lambda target | Sealed interface không được xem là functional interface |
| Sealed class mặc định abstract | Không; có thể khởi tạo nếu concrete và accessible |
| Permits liệt kê cả cháu/chắt | Permits liệt kê direct children |
| Một class ở module bất kỳ có thể được permits | Named module yêu cầu cùng named module |
| Trong unnamed module có thể permits class khác package | Phải cùng package |
| Java 17 switch thường hỗ trợ sealed pattern cases | Java 17 cần phân biệt preview; không phải tính năng chuẩn không-preview |
| Java 17 tự chứng minh mọi `instanceof` chain exhaustive | Không |
| Record tự extends mọi sealed class được permits | Record chỉ extends Record; thường implements sealed interface |
| Sealed là công cụ security/authorization | Không; chỉ là hạn chế subtype declarations |
| Sealed tự bảo đảm bất biến dữ liệu | Không; mutable state vẫn mutable |
| Sealed loại bỏ polymorphism | Không; dispatch hoạt động bình thường |
| `getPermittedSubclasses()` trả mọi descendant | Chỉ direct permitted subtypes |
| Non-sealed branch vẫn bảo đảm toàn bộ leaves đóng | Không; nhánh được mở để phát triển thêm |
| Có thể thêm variant mới mà không ảnh hưởng clients | Có thể thay đổi assumptions/handling/API contract |

## 41. Bài tập tự luyện

**Câu 1.** `sealed` kiểm soát direct children hay toàn bộ descendants của một class?

**Câu 2.** Với `sealed class A permits B`, nếu `B` khai `non-sealed`, `C extends B` có phải nằm trong `A permits` không?

**Câu 3.** Một direct permitted subclass phải chọn những modifier nào?

**Câu 4.** Một direct permitted subinterface có được khai `final` không?

**Câu 5.** `sealed abstract class` khác `sealed class` concrete ở điểm nào?

**Câu 6.** Vì sao `new Base()` có thể hợp lệ nếu Base sealed?

**Câu 7.** Nếu Base sealed chỉ permits Child, một `Unknown extends Base` không được nêu có biên dịch không?

**Câu 8.** Một permitted class quên `final`/`sealed`/`non-sealed` có hợp lệ không?

**Câu 9.** Nếu muốn Child có những subclasses được kiểm soát riêng, dùng modifier gì?

**Câu 10.** Nếu muốn Child thành một extension point mở, dùng modifier gì?

**Câu 11.** Sealed interface có thể permits direct subinterface không?

**Câu 12.** Sealed interface có thể permits record implements nó không?

**Câu 13.** Record có thể `extends` sealed class tùy ý không?

**Câu 14.** Nếu một enum được permits bởi sealed interface và implements nó, có cần khai `final enum` không?

**Câu 15.** Trong named module, permitted direct subtypes phải cùng package hay cùng module?

**Câu 16.** Trong unnamed module, permitted direct subtypes phải cùng package không?

**Câu 17.** Khi nào có thể bỏ `permits` và vẫn giữ sealed?

**Câu 18.** Hai direct subtypes ở file khác cùng package có cần ghi permits rõ không?

**Câu 19.** `sealed` có làm variable reference không được mang null không?

**Câu 20.** Một sealed interface chỉ có một abstract method có phải functional interface dùng cho lambda không?

**Câu 21.** Trong Java 17 không-preview, nên dùng kỹ thuật nào để phân nhánh theo record variants?

**Câu 22.** `instanceof` chain trên sealed hierarchy ở Java 17 có được compiler tự chứng minh exhaustive không?

**Câu 23.** `getPermittedSubclasses()` có liệt kê một grandchild extends non-sealed direct child không?

**Câu 24.** Một framework cho phép plugin implement interface trực tiếp từ module khác có nên seal interface đó vô điều kiện không?

**Câu 25.** Vì sao sealed không thay authorization?

**Câu 26.** Với sealed interface Formatter, caller có cần `instanceof` để gọi `format()` đa hình không?

**Câu 27.** Khi thêm một direct permitted variant mới, những nơi nào cần kiểm tra?

**Câu 28.** Cây Expression → Binary → Add, cần liệt kê Add ở Expression permits không nếu Add trực tiếp implements Binary?

### Đáp án tham khảo

1. Chỉ direct subtypes của nút sealed.
2. Không. C trực tiếp extends B; C là descendant gián tiếp của A.
3. `final`, `sealed`, `non-sealed` cho class, với các trường hợp implicitly final/sealed của record/enum.
4. Không; interface không có final, dùng sealed hoặc non-sealed.
5. Abstract cấm instantiate base và có thể có abstract methods; sealed tự nó chỉ giới hạn direct subtypes.
6. Sealed không đồng nghĩa abstract; nếu Base concrete và constructor accessible có thể instantiate.
7. Không. Unknown không phải direct permitted subclass.
8. Không theo quy tắc direct subtype thông thường.
9. `sealed` với permits của chính Child.
10. `non-sealed`.
11. Có. Subinterface khai `extends` trực tiếp sealed interface và được permits.
12. Có. Record implicitly final và có thể implements sealed interface.
13. Không. Record extends `java.lang.Record` và không extends class khác.
14. Không. Enum có quy tắc implicitly final hoặc implicitly sealed tùy constant-specific bodies.
15. Cùng **named module**, có thể nhiều packages nếu access hợp lệ.
16. Có, cùng package.
17. Khi direct permitted subtypes được suy ra hợp lệ trong cùng compilation unit.
18. Có: nếu ở compilation units khác nhau, cần danh sách permits tường minh.
19. Có thể mang null; sealed không cấm null.
20. Không. Sealed interface không phải functional interface.
21. `instanceof` type patterns, polymorphic methods hoặc visitor phù hợp.
22. Không.
23. Không. Reflection trả permitted **direct** subtypes.
24. Không nếu API thực sự cần open direct extension; có thể dùng non-sealed extension branch hoặc interface mở.
25. Type-hierarchy constraints không kiểm tra principal/permissions.
26. Không. Gọi interface method trực tiếp và dùng dynamic dispatch.
27. Các variant handling paths, tests, APIs, serialization, downstream consumers và versioning.
28. Không nếu Add là direct subtype của Binary chứ không trực tiếp của Expression.

## 42. Checklist kiểm tra kiến thức và code review

- [ ] Mình hiểu sealed giới hạn **lớp con hoặc subtype trực tiếp**, không phải mọi hậu duệ?
- [ ] Đã xác định đúng direct superclass/superinterface ở từng `extends`/`implements`?
- [ ] Danh sách `permits` có đúng những direct subtypes?
- [ ] Mỗi permitted direct subtype có final/sealed/non-sealed hoặc trạng thái implicit đúng?
- [ ] Nếu dùng non-sealed, mình có chủ ý mở branch?
- [ ] Nếu muốn toàn hierarchy đóng, các leaves có final và không có non-sealed branch?
- [ ] Nếu base cần không được instantiate, mình đã khai abstract?
- [ ] Nếu dùng records, parent có phải sealed interface thích hợp?
- [ ] Nếu dùng enum, mình phân biệt named constants với direct implementation types?
- [ ] Có kiểm tra cùng named module hoặc cùng package trong unnamed module?
- [ ] Nếu không ghi permits, các direct subtypes có cùng compilation unit hợp lệ?
- [ ] Constructors/access vẫn thỏa Java rules, permits không tự cấp access?
- [ ] Có phân biệt polymorphism với pattern/type checks?
- [ ] Không dùng Java 21 pattern switch như syntax ổn định của Java 17?
- [ ] Có kiểm tra null handling và fallback trong Java 17?
- [ ] Có coi tập variants là API contract khi versioning?
- [ ] Có kiểm tra `non-sealed` branch sẽ cho descendants mới?
- [ ] Nếu dùng reflection, mình không nhầm permitted direct subclasses với mọi descendants?
- [ ] Có xác định sealed không tự bảo đảm immutable state/security?
- [ ] Việc seal API có thật sự phù hợp mục tiêu extension và plugin integrations?
- [ ] Ví dụ runnable đã kiểm tra imports, class names và stdout Java 17?

## 43. Tài liệu Java 17 chính thức

- [JLS 17 §8.1.1.2 — `sealed`, `non-sealed` and `final` Class Modifiers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): modifiers của class trong sealed hierarchy.
- [JLS 17 §8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6): `permits` với class và quy tắc direct subclass.
- [JLS 17 §9.1.1.4 — `sealed` and `non-sealed` Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): modifiers của interface.
- [JLS 17 §9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4): sealed interface và permitted direct subtypes.
- [JLS 17 §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8): sealed interfaces không là functional interface.
- [JLS 17 §14.30.1 — Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1): type patterns dùng trong Java 17.
- [JLS 17 §15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type tests và pattern variables.
- [Java SE 17 API — `Class.isSealed()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isSealed()): nhận biết sealed class/interface tại runtime.
- [Java SE 17 API — `Class.getPermittedSubclasses()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()): đọc những direct permitted types.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): mục đích, hình thức và giới hạn của sealed hierarchy chuẩn hóa ở Java 17.
- [JEP 395 — Records](https://openjdk.org/jeps/395): record variants được kết hợp với sealed interfaces.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): tính năng pattern switch được chuẩn hóa ở Java 21, **không phải cú pháp chuẩn không-preview của Java 17**.

## 44. Tổng kết

**`sealed` dùng để kiểm soát *những kiểu nào được phép trực tiếp kế thừa hoặc triển khai một kiểu cha***. Với `sealed class A permits B, C`, B/C là direct permitted subclasses. Với `sealed interface I permits X, Y`, X/Y có thể là direct implementing classes hoặc direct extending interfaces. `permits` không liệt kê tự động mọi hậu duệ nhiều cấp.

Mỗi direct permitted child phải cho biết nhánh đó **đóng (`final`)**, **tiếp tục được kiểm soát (`sealed`)** hay **mở lại (`non-sealed`)**. Chính sự lựa chọn theo từng cấp này giúp thiết kế API cân bằng giữa một **closed domain hierarchy** và các **extension points có chủ ý**.

Trong Java 17, sealed giúp compiler kiểm tra quan hệ subtype, tăng tính minh bạch của domain model và làm các variants dễ nhận diện. Nó **không** tự tạo immutability, bảo mật, hay exhaustive pattern switch không-preview. Muốn sử dụng hiệu quả, hãy thiết kế rõ **direct children, module/package boundary, constructor access, fallback behavior và quy trình thay đổi API**.
