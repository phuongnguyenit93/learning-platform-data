# permits định nghĩa tập subtype trong sealed hierarchy (Java 21)

Trong Java, từ khóa **`sealed`** dùng để kiểm soát **những class hoặc interface nào được phép trực tiếp kế thừa/triển khai một kiểu**. Danh sách sau **`permits`** là phần trung tâm của hợp đồng đó. Nó không liệt kê mọi đối tượng có thể xuất hiện lúc chạy, mà chỉ liệt kê **các direct subclasses hoặc direct subinterfaces được phép**.

Ví dụ:

```java
sealed interface Message permits TextMessage, ErrorMessage {}

record TextMessage(String text) implements Message {}

record ErrorMessage(int code) implements Message {}
```

Hai record `TextMessage` và `ErrorMessage` được phép **trực tiếp implement** `Message`; class thứ ba tùy ý không thể viết `implements Message` nếu chưa được thêm vào `permits`. Vì record ngầm định là `final`, chúng cũng không thể có subclass.

Sự kiểm soát này giúp thiết kế mô hình dữ liệu đóng, cho phép compiler chứng minh **pattern `switch` exhaustive** theo các subtype đã biết. Tuy vậy, cần hiểu đúng ba khái niệm:

- **Tập được phép trực tiếp (permitted direct subtypes):** do `permits` hoặc quy tắc suy ra mặc định xác định.
- **Tập subtype gián tiếp:** phụ thuộc vào việc từng nhánh bên dưới là `final`, `sealed` hay `non-sealed`.
- **Tập instance runtime:** có thể khác với giả định của chương trình đã biên dịch từ trước khi các module/JAR được nâng cấp không đồng bộ.

Bài này sử dụng cú pháp Java 21; tính năng sealed classes/interfaces được chuẩn hóa từ Java 17 (JEP 409) và có thể kết hợp với pattern matching for `switch` của Java 21 (JEP 441).

## 1. `permits` trả lời câu hỏi chính xác nào?

Với một **sealed class**:

```java
sealed class Document permits PdfDocument, TextDocument {}

final class PdfDocument extends Document {}

final class TextDocument extends Document {}
```

Compiler cho phép `PdfDocument` và `TextDocument` trực tiếp `extends Document`. Class khác không được phép trực tiếp mở rộng `Document` chỉ vì nó nằm cùng package hoặc có tên tương tự.

Với **sealed interface**:

```java
sealed interface Command permits Create, Delete {}

record Create(String id) implements Command {}

record Delete(String id) implements Command {}
```

`permits` lần này kiểm soát các **kiểu trực tiếp implement/extend interface** `Command`, không phải các giá trị `id` bên trong record.

Quy tắc cốt lõi:

1. Kiểu được niêm phong khai báo `sealed`.
2. Mỗi tên trong `permits` phải biểu thị một **direct subtype** thực sự của kiểu sealed tương ứng.
3. Một direct subtype muốn được khai báo hợp lệ phải nằm trong tập được cấp phép, có khai báo phù hợp và ở vị trí module/package được phép.
4. Mỗi direct subtype tiếp tục quyết định cho phép các subtype dưới nó đến đâu, thông qua `final`, `sealed`, hoặc `non-sealed` (ngoại lệ đối với kiểu ngầm định `final` như record).
5. Chỉ các nhánh mà compiler có thể chứng minh đã được bao phủ mới làm pattern switch exhaustive mà không cần `default`.

**Điểm dễ nhầm:** `permits` không phải danh sách những class “có thể tạo instance” của sealed class. Ví dụ một permitted subtype có thể là `abstract sealed class` hay `sealed interface`, bản thân nó không được khởi tạo trực tiếp nhưng vẫn là một nhánh hợp lệ trong hierarchy.

## 2. Phân biệt direct subtype và indirect subtype

Xét hệ phân cấp:

```text
Shape (sealed interface)
├── Circle (record; ngầm final)
└── Polygon (non-sealed class)
    ├── Triangle (class)
    └── Rectangle (class)
```

Khai báo `Shape` chỉ cần `permits Circle, Polygon`:

```java
sealed interface Shape permits Circle, Polygon {}

record Circle(double radius) implements Shape {}

non-sealed class Polygon implements Shape {}

final class Triangle extends Polygon {}

final class Rectangle extends Polygon {}
```

`Triangle` và `Rectangle` **không cần có tên trong `Shape permits ...`**, vì chúng **không trực tiếp** implement `Shape`: chúng kế thừa `Polygon`, rồi gián tiếp là `Shape`.

Điều này **không phá vỡ luật sealed**. `Shape` vẫn kiểm soát tất cả các **cửa vào trực tiếp**: muốn trở thành `Shape`, một kiểu mới phải đi vào một nhánh được cấp phép. Nếu nhánh đó là `non-sealed`, tác giả hierarchy đã **có chủ đích mở rộng** khả năng kế thừa ở bên dưới nhánh ấy.

Vì vậy câu nói “`Shape` chỉ có hai subtype” là không chính xác trong ví dụ này. Đúng hơn là: **`Shape` có hai direct permitted subtypes**, nhưng có thể có thêm các subtype gián tiếp của `Polygon`.

Khi làm pattern matching:

```java
static String kind(Shape shape) {
    return switch (shape) {
        case Circle circle -> "circle";
        case Polygon polygon -> "polygon family";
    };
}
```

`case Polygon polygon` bắt cả `Polygon`, `Triangle` và `Rectangle`. Hai case đủ bao phủ mọi `Shape` **khác null** và switch expression là exhaustive theo hierarchy được khai báo. Nếu chỉ có `case Circle` và `case Triangle`, compiler không thể coi như đã bao phủ mọi `Polygon`.

Các mảnh code trong mục này là ví dụ minh họa; chương trình chạy độc lập được trình bày ở phần 10.

## 3. Ba lựa chọn cho permitted subtype: `final`, `sealed`, `non-sealed`

Một permitted direct subclass/subinterface cần biểu thị cách nó tiếp tục kiểm soát kế thừa.

### `final`: chặn kế thừa tiếp

```java
sealed interface Status permits Success, Failure {}

record Success(String value) implements Status {}

final class Failure implements Status {}
```

`Success` là record nên **ngầm định final**; `Failure` khai báo `final` tường minh. Không class nào có thể kế thừa chúng. Đây là cách tạo tập biến thể đóng ở mức lá.

### `sealed`: tiếp tục giới hạn từng nhánh con

```java
sealed interface Action permits ReadAction, WriteAction {}

final class ReadAction implements Action {}

sealed interface WriteAction extends Action
        permits InsertAction, RemoveAction {}

final class InsertAction implements WriteAction {}

final class RemoveAction implements WriteAction {}
```

`Action` chỉ trực tiếp cấp phép `ReadAction` và `WriteAction`. `WriteAction` lại cấp phép riêng cho `InsertAction` và `RemoveAction`. Một **hierarchy nhiều tầng vẫn được kiểm soát**, nếu các nhánh tiếp tục sealed/final.

Không đưa `InsertAction` vào `Action permits` vì `InsertAction` **trực tiếp extends/implements `WriteAction`**, không trực tiếp implements `Action`.

### `non-sealed`: mở nhánh cho mở rộng thông thường

```java
sealed interface PaymentMethod permits CardPayment, AlternativePayment {}

record CardPayment(String token) implements PaymentMethod {}

non-sealed class AlternativePayment implements PaymentMethod {}

final class BankTransfer extends AlternativePayment {}
```

`AlternativePayment` là một direct permitted subtype, nhưng nó cho phép các class con mở rộng như một class thông thường. `BankTransfer` không cần được thêm vào `PaymentMethod permits`.

**Lưu ý cú pháp:** `non-sealed` không phải một modifier có thể gắn tùy tiện vào class bất kỳ; trong ngữ cảnh này, nó phải là subtype trực tiếp của một kiểu sealed. Interface không thể là `final`, nhưng có thể tiếp tục `sealed` hoặc chọn `non-sealed` khi hợp lệ.

| Lựa chọn | Có thể có subtype bên dưới không? | Hệ quả với mô hình |
| --- | --- | --- |
| `final` | Không | Nhánh kết thúc tại đó |
| `sealed ... permits ...` | Chỉ những direct subtype được phép của nhánh | Tiếp tục kiểm soát hierarchy |
| `non-sealed` | Có, theo luật kế thừa thông thường | Cho phép mở rộng về sau mà không sửa `permits` ở tổ tiên |
| `record` | Không vì ngầm `final` | Phù hợp cho biến thể dữ liệu đóng |

Các nhánh trong cùng một sealed hierarchy **không bắt buộc** chọn cùng modifier. Đây là công cụ thiết kế: phần lõi đóng có thể cùng tồn tại với một “extension point” được mở có kiểm soát.

## 4. Khi nào có thể bỏ `permits`?

Java có quy tắc **suy ra danh sách permitted subtype** nếu một sealed class/interface **không viết `permits`**, với điều kiện các direct subtype được khai báo trong **cùng compilation unit**.

Ví dụ toàn bộ ba kiểu nằm trong **một file** `Signal.java`:

```java
sealed interface Signal {}

record Ping() implements Signal {}

record Pong() implements Signal {}
```

Compiler có thể suy ra hai permitted direct subtype là `Ping` và `Pong`; không phải vì chúng nằm trong cùng package một cách chung chung, mà vì các khai báo direct subtype xuất hiện **trong cùng compilation unit** với `Signal`.

Nếu tách `Signal`, `Ping`, `Pong` thành **các file riêng**, hãy khai báo rõ:

```java
sealed interface Signal permits Ping, Pong {}
```

Sau đó đặt các kiểu vào package/module hợp lệ. Việc compiler suy ra `permits` không làm Java “tự tìm mọi implementation ở runtime”: danh sách vẫn được xác định **khi biên dịch**.

Có thể chọn viết `permits` tường minh ngay cả khi ở cùng file nếu muốn hợp đồng public dễ đọc hơn. Với module lớn và subtype phân tán trong nhiều source file, cách tường minh thường thích hợp.

## 5. Giới hạn module và package của `permits`

Không phải mọi class có tên trong danh sách đều được phép trở thành direct subtype; **vị trí của các khai báo cũng quan trọng**:

- Nếu sealed type nằm trong một **named module**, các permitted direct subtype phải nằm trong **cùng named module**. Chúng có thể thuộc các package khác nhau trong module đó.
- Nếu sealed type nằm trong **unnamed module** (ví dụ ứng dụng đơn giản chạy classpath), các permitted direct subtype phải nằm trong **cùng package** với sealed type.
- Nếu một class/interface được nêu trong `permits` nhưng **không trực tiếp extends/implements** kiểu sealed, compiler từ chối.
- Nếu có class mới trực tiếp mở rộng kiểu sealed mà **không được phép**, compiler từ chối.

`permits` vì vậy không phải một “danh sách tên mang tính tài liệu”: compiler và JVM thực thi các ràng buộc của sealed hierarchy. Không thể “mở rộng từ bất kỳ thư viện nào” bằng cách khai báo `implements` nếu tác giả kiểu sealed không cấp quyền tương ứng.

Ví dụ một kiểu trong module `core` không thể tự ý `permits` một implementation direct ở module khác chỉ để tạo plugin xuyên module. Nếu cần điểm cắm cho plugin, cân nhắc **một permitted `non-sealed` extension type** hoặc một interface SPI riêng không sealed, với ranh giới hợp đồng rõ ràng.

Các ví dụ chạy ở mục 10 sử dụng nested types trong một class và không khai báo module, nên không cần cấu hình `module-info.java`.

## 6. Các lỗi thường gặp khi viết `permits`

### Lỗi 1: Quên tên subtype trực tiếp

```java
// CỐ Ý SAI:
sealed interface Result permits Ok {}

record Ok() implements Result {}

record Error() implements Result {} // Không nằm trong Result permits.
```

`Error` trực tiếp implements `Result` nhưng không được cấp phép. Trình biên dịch từ chối. Cách sửa: thêm `Error` vào `Result permits`, hoặc thiết kế lại quan hệ kế thừa nếu `Error` không nên là direct subtype.

### Lỗi 2: Liệt kê một subtype gián tiếp như direct subtype

```java
// CỐ Ý SAI:
sealed interface Base permits Middle, Leaf {}

non-sealed class Middle implements Base {}

final class Leaf extends Middle {} // Leaf không trực tiếp implements Base.
```

Ở đây `Leaf` là subtype **gián tiếp** thông qua `Middle`, nên không được liệt kê như một direct permitted subtype của `Base`. Cách sửa là chỉ `permits Middle` và để nhánh `Middle` điều phối mở rộng phía dưới.

### Lỗi 3: Direct subtype quên modifier hợp lệ

```java
// CỐ Ý SAI:
sealed interface Outcome permits Accepted {}

class Accepted implements Outcome {} // Cần final, sealed hoặc non-sealed.
```

Với class thường `Accepted`, hãy chọn `final class Accepted`, `sealed class Accepted ...`, hoặc `non-sealed class Accepted` theo mong muốn mở rộng. Một **record implement sealed interface** là trường hợp thuận tiện vì đã ngầm final, không cần lặp lại `final`.

### Lỗi 4: Tự ý triển khai kiểu sealed ở module/package khác

Thêm một class trực tiếp implements sealed type trong thư viện khác mà không được liệt kê trong `permits`, hoặc đặt permitted direct subtype sai module/package, sẽ bị từ chối. Đừng xử lý bằng unchecked cast: đây là ràng buộc của **cấu trúc class**, không phải vấn đề cast dữ liệu.

### Lỗi 5: Nhầm `permits` với các giá trị record component

```java
sealed interface Report permits SuccessReport, FailureReport {}

record SuccessReport(String id) implements Report {}

record FailureReport(String message) implements Report {}
```

Danh sách `permits` không giới hạn giá trị `id`, `message`. Nó chỉ giới hạn các **biến thể kiểu**. Các component vẫn có thể mang dữ liệu khác nhau theo kiểu khai báo; muốn kiểm tra dữ liệu hợp lệ, phải sử dụng validation, constructor hoặc các quy tắc nghiệp vụ khác.

Đừng đưa các đoạn **cố ý sai** vào chung file demo chạy ở mục 10.

## 7. `permits` giúp pattern `switch` exhaustive như thế nào?

Một lợi ích rõ rệt trong Java 21 là compiler có thể chứng minh một `switch` trên sealed type đã bao phủ **từng nhánh được phép**.

```java
sealed interface Event permits Started, Finished {}

record Started(String name) implements Event {}

record Finished(String name) implements Event {}

static String describe(Event event) {
    return switch (event) {
        case Started started -> "started:" + started.name();
        case Finished finished -> "finished:" + finished.name();
    };
}
```

Đây là các khai báo minh họa cần đặt trong cùng class hoặc sắp xếp vào các compilation unit hợp lệ. Với selector `Event`, hai case đã bao phủ mọi đối tượng **khác null** có thể là `Event` trong hierarchy đóng này, nên `switch expression` **không cần `default`**.

Ngược lại, nếu chỉ còn:

```java
// KHÔNG BIÊN DỊCH: switch expression không exhaustive.
return switch (event) {
    case Started started -> "started:" + started.name();
};
```

Thì `Finished` chưa được xử lý, compiler từ chối.

Trong Java 21, **enhanced switch statement** có pattern cũng bắt buộc exhaustive. Vì vậy, không chỉ biểu thức mà cả statement sau cần bao phủ đủ các nhánh:

```java
static void printEvent(Event event) {
    switch (event) {
        case Started started ->
                System.out.println(started.name());
        case Finished finished ->
                System.out.println(finished.name());
    }
}
```

Các ví dụ này là **code minh họa**, không phải chương trình riêng.

Điều này tạo một kiểu bảo đảm quan trọng: khi thiết kế hierarchy đóng, compiler có thể phát hiện ngay các nhánh nghiệp vụ còn thiếu, thay vì cho phép `switch` silently bỏ qua biến thể mới.

## 8. `non-sealed` không phá tính exhaustive nếu case bao phủ nhánh mở

Xét:

```java
sealed interface Notification permits Email, External {}

record Email(String subject) implements Notification {}

non-sealed class External implements Notification {}
```

Ta có thể viết:

```java
static String category(Notification item) {
    return switch (item) {
        case Email email -> "email";
        case External external -> "external";
    };
}
```

`case External external` bao phủ **mọi instance của `External` và subclass của nó**, kể cả class con sẽ được tạo sau này. Do đó, compiler vẫn có thể nhận ra switch exhaustive khi bao phủ các direct permitted branches.

Tuy nhiên, chỉ có `case Email` và một số subclass cụ thể của `External` **không nhất thiết đủ**: vì `External` là non-sealed, có thể còn những subclass khác hoặc chính một instance `External` nếu class đó không abstract.

**Quy tắc khi review:** với nhánh `non-sealed`, nếu nghiệp vụ muốn xử lý mọi biến thể hiện tại/tương lai bằng một cách, hãy bắt ở **type của nhánh mở**. Nếu muốn phân loại sâu từng subclass, cần bổ sung chiến lược fallback rõ ràng thay vì giả định tập con là đóng.

## 9. Nested sealed hierarchy: bao phủ bằng nhánh trung gian hoặc bằng các lá

Với sơ đồ:

```text
Operation (sealed)
├── Query (final)
└── Change (sealed)
    ├── Insert (final)
    └── Remove (final)
```

Ta có hai chiến lược hợp lệ.

**Bắt theo nhánh trực tiếp**:

```java
return switch (operation) {
    case Query query -> "query";
    case Change change -> "change";
};
```

`case Change change` bao phủ tất cả subtype của `Change`, bao gồm `Insert` và `Remove`.

**Bắt theo các lá cụ thể**:

```java
return switch (operation) {
    case Query query -> "query";
    case Insert insert -> "insert";
    case Remove remove -> "remove";
};
```

Compiler có thể chứng minh exhaustive dựa trên việc `Change` cũng sealed và chỉ có hai subtype lá. Cách thứ hai phù hợp khi mỗi biến thể cần logic nghiệp vụ riêng.

Lưu ý: thứ tự case có liên quan đến **dominance**. Nếu đặt `case Change change` trước `case Insert insert` trong cùng switch, nhánh `Insert` sẽ bị che vì mọi `Insert` cũng là `Change`, và compiler sẽ báo lỗi case dominated.

Một `case Operation op` không guard, hoặc `default`, cũng có thể làm switch exhaustive nhưng làm mất nhiều giá trị kiểm tra theo subtype của hierarchy.

## 10. Chương trình hoàn chỉnh chạy với JDK 21

Tạo file **`PermitsHierarchyDemo.java`**:

```java
public class PermitsHierarchyDemo {
    sealed interface Message permits Joined, Left, Extension {}

    record Joined(String user) implements Message {}

    record Left(String user, int code) implements Message {}

    static non-sealed class Extension implements Message {
        private final String label;

        Extension(String label) {
            this.label = label;
        }

        String label() {
            return label;
        }
    }

    static final class PriorityExtension extends Extension {
        PriorityExtension(String label) {
            super(label);
        }
    }

    static String describe(Message message) {
        return switch (message) {
            case null -> "missing";
            case Joined joined -> "joined:" + joined.user();
            case Left left -> "left:" + left.user() + ":" + left.code();
            case Extension extension ->
                    "extension:" + extension.label();
        };
    }

    static void printKind(Message message) {
        switch (message) {
            case null -> System.out.println("kind:missing");
            case Joined joined -> System.out.println("kind:joined");
            case Left left -> System.out.println("kind:left");
            case Extension extension -> System.out.println("kind:extension");
        }
    }

    public static void main(String[] args) {
        System.out.println(describe(new Joined("Mai")));
        System.out.println(describe(new Left("Mai", 2)));
        System.out.println(describe(new Extension("basic")));
        System.out.println(describe(new PriorityExtension("priority")));
        System.out.println(describe(null));
        printKind(new PriorityExtension("priority"));
    }
}
```

Biên dịch và chạy với **JDK 21**:

```bash
javac --release 21 PermitsHierarchyDemo.java
java PermitsHierarchyDemo
```

**Stdout chính xác:**

```text
joined:Mai
left:Mai:2
extension:basic
extension:priority
missing
kind:extension
```

Phân tích:

1. `Message` là một sealed interface chỉ trực tiếp cấp phép `Joined`, `Left` và `Extension`.
2. `Joined`, `Left` là record, mặc định `final`, nên đóng hai nhánh này.
3. `Extension` được khai báo `non-sealed` và cho phép `PriorityExtension extends Extension`. `PriorityExtension` **không** cần tên trong `Message permits`.
4. Trong cả `describe` (switch expression) và `printKind` (enhanced switch statement), `case Extension extension` khớp cả `Extension` và `PriorityExtension`.
5. `case null` xử lý selector `null` tường minh; nếu không có case null, một pattern switch trên tham chiếu null thường ném `NullPointerException`. **Exhaustive với subtype không null không tự xử lý null.**
6. Hai switch không có `default` nhưng vẫn exhaustive vì mỗi direct permitted branch được bao phủ và có nhánh riêng cho null.

Không cần `--enable-preview`: sealed hierarchy và pattern matching switch dùng ở đây đều đã được chuẩn hóa trong Java 21.

## 11. `permits` khác gì một interface không sealed?

Với một interface thường:

```java
interface OpenMessage {}

final class Alpha implements OpenMessage {}

final class Beta implements OpenMessage {}
```

Một module khác vẫn có thể viết `class Gamma implements OpenMessage` (nếu các quy tắc truy cập bình thường cho phép). Compiler không có một danh sách hữu hạn được công bố để khẳng định các case `Alpha` và `Beta` đủ cho mọi `OpenMessage`.

Ngược lại, khi dùng:

```java
sealed interface ClosedMessage permits Alpha, Beta {}
```

Với các class `Alpha`, `Beta` được khai báo lại để implements `ClosedMessage` và thỏa `final`/modifier phù hợp, direct subtype mới không thể tự nhiên xuất hiện trong module khác hoặc khi compiler chưa được cập nhật hierarchy.

Đó là giá trị của sealed type trong **mô hình sum type / algebraic data type**: một kiểu tổng bao gồm các biến thể được cấp phép, compiler biết mối quan hệ giữa chúng để hỗ trợ kiểm tra đầy đủ trong pattern matching.

Tuy nhiên, sealed type không phải hệ thống validation cho mọi dữ liệu: ví dụ `Joined(String user)` vẫn có thể nhận `null` cho component nếu bạn không bổ sung validation. Permits kiểm soát **ai được là subtype**, chứ không kiểm soát **giá trị thuộc tính**.

## 12. Khi hierarchy thay đổi: lợi ích và rủi ro của exhaustive switch

Giả sử ban đầu:

```java
sealed interface Event permits Start, Stop {}

record Start() implements Event {}

record Stop() implements Event {}
```

Một `switch` trên `Event` có hai case `Start`, `Stop` có thể exhaustive và không cần `default`.

Sau đó nhà phát triển thêm `Pause`:

```java
sealed interface Event permits Start, Stop, Pause {}

record Start() implements Event {}

record Stop() implements Event {}

record Pause() implements Event {}
```

Nếu **biên dịch lại** đoạn switch với hierarchy mới nhưng vẫn chỉ có case `Start`/`Stop`, compiler có thể báo không exhaustive. Đây là **tác dụng mong muốn**: bắt người bảo trì cân nhắc xử lý `Pause`.

Nếu **chỉ thay library mới ở runtime** còn client chứa switch vẫn là bytecode cũ biên dịch theo hierarchy v1, khi gặp `Pause`, Java 21 có thể ném **`MatchException`** vì giả định exhaustive cũ không còn đúng. Đây là vấn đề *separate compilation* và triển khai không đồng bộ, không phải lỗi của `permits` trong source mới.

Một nhánh `default` có thể cho fallback đối với subtype mới, nhưng cũng làm compiler **không còn bắt buộc** bổ sung case riêng khi hierarchy mở rộng. Cân nhắc:

- **Mọi biến thể có nghiệp vụ riêng:** ưu tiên không có `default` trên hierarchy đóng để compiler kiểm tra đủ case khi rebuild.
- **Biến thể mới được phép xử lý chung:** có thể dùng `default` hoặc type pattern chung tường minh, kèm logging/metrics khi phù hợp.
- **Triển khai đa module:** khóa phiên bản phụ thuộc nhất quán; rebuild và kiểm thử các module chứa pattern switch khi thay đổi danh sách subtype.

Không nhầm tình huống này với `NullPointerException` do selector `null`: đó là đường xử lý null riêng, không phải thiếu permitted subtype.

## 13. Những hiểu nhầm phổ biến

**“`permits A, B` nghĩa là chỉ có hai subtype trong toàn bộ chương trình.”** Không nhất thiết. `A` hoặc `B` có thể `non-sealed` và có subclass/implementation gián tiếp. Danh sách chỉ giới hạn **direct subtypes**.

**“Mọi class muốn tạo instance của interface sealed đều phải xuất hiện trong `permits`.”** Sai. Một class kế thừa một nhánh `non-sealed` đã được cấp phép có thể là subtype gián tiếp hợp lệ mà không có tên trong `permits` của tổ tiên.

**“`permits` có thể nêu class không trực tiếp kế thừa kiểu sealed để cho phép gián tiếp.”** Sai. Một tên trong `permits` phải thể hiện quan hệ direct subtype với sealed type tương ứng.

**“Đã là direct subtype được phép thì không cần modifier nào.”** Sai đối với class bình thường: nó cần `final`, `sealed`, hoặc `non-sealed`. Record là một ngoại lệ thuận tiện vì ngầm final.

**“Không viết `permits` thì kiểu sealed tự tìm tất cả subtype trên classpath lúc chạy.”** Sai. Compiler chỉ suy ra danh sách trực tiếp từ **cùng compilation unit** trong trường hợp được phép bỏ clause; không dò classpath/runtime.

**“Một switch có đủ các nhánh của `permits` sẽ xử lý luôn null.”** Sai. Pattern type không khớp null; có thể thêm `case null` nếu selector nullable.

**“Thêm `default` luôn an toàn hơn.”** Không nhất thiết. Nó giúp fallback nhưng cũng có thể che giấu việc cần xử lý subtype mới khi hệ thống phát triển.

## 14. Checklist thiết kế và review

1. **Định nghĩa phạm vi đóng:** kiểu nào là gốc `sealed`; kiểu nào thực sự được phép **trực tiếp** implement/extend?
2. **Duyệt từng direct subtype:** đã có khai báo `final`, `sealed`, `non-sealed` hoặc là record ngầm final chưa?
3. **Xác minh quan hệ trực tiếp:** subtype nêu trong `permits` có trực tiếp extends/implements kiểu gốc, hay chỉ là hậu duệ gián tiếp?
4. **Xác minh vị trí:** named module cùng module; unnamed module cùng package; chỉ bỏ `permits` nếu quy tắc cùng compilation unit thỏa.
5. **Đánh giá nhánh mở:** có `non-sealed` không, và code sử dụng có dựa nhầm vào việc tập hậu duệ đóng?
6. **Viết pattern switch:** đã bao phủ đủ từng nhánh được phép hoặc tất cả nhánh lá trong hierarchy sealed nhiều tầng chưa?
7. **Kiểm tra dominance:** nhánh supertype có đứng trước nhánh subtype khiến case sau không thể chạy không?
8. **Kiểm tra null:** cần `case null` hay validation đầu vào không? `default` không mặc nhiên bắt null trong pattern switch.
9. **Đánh giá API evolution:** thêm direct permitted subtype có cần rebuild những module chứa switch cũ? Có test cho biến thể mới không?
10. **Quyết định default theo nghiệp vụ:** muốn compiler buộc xử lý kiểu mới hay muốn fallback rõ ràng cho tương thích tương lai?

**Kết luận:** `permits` là **hợp đồng xác định các direct subtype được phép** của một sealed class/interface, chứ không phải danh sách mọi hậu duệ hoặc mọi đối tượng runtime. Kết hợp `final`, `sealed`, `non-sealed` giúp thiết kế nơi nào đóng, nơi nào mở. Trong Java 21, hiểu đúng cây phân cấp này là chìa khóa để viết pattern `switch` **exhaustive, dễ bảo trì và an toàn hơn khi hệ thống phát triển**.

### Tài liệu chính thức

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — §8.1.6, Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.6)
- [Java Language Specification 21 — §9.1.4, Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.4)
- [Oracle Java 21 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html)
