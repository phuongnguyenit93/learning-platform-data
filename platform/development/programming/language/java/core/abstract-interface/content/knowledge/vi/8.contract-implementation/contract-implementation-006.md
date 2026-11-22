# Nhiều interface có yêu cầu kiểu trả về không tương thích trong Java

## 1. Vấn đề khi triển khai đồng thời nhiều hợp đồng

Một lớp Java có thể `implements` nhiều interface. Tuy nhiên, nếu các interface cùng yêu cầu một phương thức có **cùng chữ ký** nhưng đòi hỏi **kiểu trả về không tương thích**, một lớp triển khai không thể thỏa mãn đồng thời các hợp đồng đó.

Xét hai interface:

~~~java
interface TextId {
    String id();
}

interface NumericId {
    Integer id();
}
~~~

Cả hai đều khai báo phương thức `id()`, không có tham số. Điểm khác biệt là `TextId.id()` yêu cầu trả về `String`, còn `NumericId.id()` yêu cầu trả về `Integer`.

Nếu viết:

~~~java
// Ví dụ CỐ Ý SAI: không biên dịch.
final class BrokenRecord implements TextId, NumericId {
    @Override
    public String id() {
        return "42";
    }
}
~~~

Trình biên dịch từ chối, vì `String id()` không triển khai được yêu cầu `Integer id()`. Đổi thành `Integer id()` thì lại vi phạm `TextId`. `String` và `Integer` là hai kiểu lớp không có quan hệ lớp con để kiểu trả về của phương thức duy nhất thay thế được cho cả hai. Nội dung thông báo lỗi cụ thể có thể khác theo phiên bản `javac` và dạng mã, nhưng đây là **lỗi biên dịch**, không phải lỗi chỉ xảy ra khi chương trình chạy.

Một interface kế thừa đồng thời hai hợp đồng không tương thích cũng gặp lỗi:

~~~java
// Ví dụ CỐ Ý SAI: không biên dịch.
interface CombinedId extends TextId, NumericId {
}
~~~

Vấn đề xuất hiện ngay trong quan hệ kế thừa hợp đồng; không thể trì hoãn việc giải quyết bằng cách chờ một lớp khác triển khai.

## 2. Vì sao khác kiểu trả về vẫn bị xem là trùng phương thức?

Trong Java, chữ ký phương thức dùng để xét việc overload/override dựa vào **tên phương thức** và **danh sách kiểu tham số** (cùng các quy tắc liên quan đến phương thức generic). **Kiểu trả về không được dùng để phân biệt hai overload.**

Do đó:

~~~java
// Ví dụ CỐ Ý SAI: không biên dịch.
class InvalidOverload {
    String read() {
        return "text";
    }

    int read() {
        return 123;
    }
}
~~~

Hai phương thức `read()` không khác tên hoặc tham số; không thể cùng tồn tại chỉ vì một phương thức trả về `String` còn phương thức kia trả về `int`.

Ngược lại, khi tham số khác nhau, ta có overload hợp lệ:

~~~java
// Hai chữ ký khác nhau: convert(String) và convert(int).
class Converter {
    int convert(String value) {
        return Integer.parseInt(value);
    }

    String convert(int value) {
        return Integer.toString(value);
    }
}
~~~

Đây là **đoạn minh họa** không có `main`; nếu dùng, truyền tham số đúng kiểu. Không nên đổi tham số một cách tùy tiện chỉ để tránh xung đột khi nghiệp vụ cần cùng thao tác không tham số.

## 3. Quy tắc tương thích kiểu trả về khi ghi đè

Java áp dụng quy tắc **return-type-substitutability**: kiểu trả về của phương thức triển khai phải thay thế hợp lệ kiểu trả về mà hợp đồng yêu cầu. Ba nhóm quan trọng cho người mới học là:

| Kiểu trả về trong hợp đồng | Phương thức triển khai phù hợp | Không phù hợp |
| --- | --- | --- |
| `void` | `void` | `String`, `int`, ... |
| Kiểu nguyên thủy `int` | `int` | `long`, `Integer` |
| Kiểu tham chiếu `CharSequence` | `CharSequence` hoặc kiểu con như `String` | Kiểu rộng hơn như `Object` |

Với **kiểu nguyên thủy**, cùng chữ ký phải dùng kiểu trả về nguyên thủy giống hệt; khả năng tự động chuyển `int` sang `long` khi dùng biểu thức không biến một phương thức `int get()` thành triển khai của `long get()`. Autoboxing cũng không biến `int get()` thành triển khai hợp lệ của `Integer get()`.

Với **kiểu tham chiếu**, Java hỗ trợ **kiểu trả về hiệp biến** (*covariant return type*): phương thức triển khai có thể trả về kiểu cụ thể hơn, miễn thỏa quy tắc thay thế kiểu trả về. Ví dụ, `String` thực hiện `CharSequence`, nên `String` thay thế được cho yêu cầu `CharSequence`. Một số trường hợp generic/unchecked được quy định riêng trong Java Language Specification; không nên diễn giải quy tắc bằng việc chỉ nhìn tên hai kiểu.

### Ví dụ hợp lệ: kiểu trả về hiệp biến

Lưu toàn bộ chương trình sau vào `CovariantReturnDemo.java`:

~~~java
interface TextView {
    CharSequence render();
}

interface StringView {
    String render();
}

final class MarkdownView implements TextView, StringView {
    @Override
    public String render() {
        return "Học Java";
    }
}

public class CovariantReturnDemo {
    public static void main(String[] args) {
        MarkdownView view = new MarkdownView();

        TextView general = view;
        StringView specific = view;

        System.out.println(general.render());
        System.out.println(specific.render().length());
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac -encoding UTF-8 CovariantReturnDemo.java
java CovariantReturnDemo
~~~

Kết quả chính xác:

~~~text
Học Java
8
~~~

Giải thích: `MarkdownView.render()` chỉ có **một** phương thức triển khai, trả về `String`. Giá trị này đáp ứng cả yêu cầu `CharSequence render()` lẫn `String render()`. Biến `general` chỉ nhìn thấy hợp đồng `CharSequence`; biến `specific` biết kiểu trả về là `String` và có thể gọi `length()`. Chuỗi `Học Java` có tám ký tự.

Đây là điểm quyết định: **khác kiểu trả về chưa chắc đã xung đột**. Xung đột chỉ trở thành vấn đề khi không có kiểu trả về hợp lệ cho phương thức triển khai theo các quy tắc của Java.

### Mở rộng interface với kiểu trả về cụ thể hơn

Một interface con cũng có thể khai báo lại phương thức bằng kiểu trả về hiệp biến:

~~~java
interface GeneralResult {
    Number value();
}

interface IntegerResult extends GeneralResult {
    @Override
    Integer value();
}

final class Counter implements IntegerResult {
    @Override
    public Integer value() {
        return 7;
    }
}
~~~

Đây là đoạn khai báo hợp lệ, nhưng chưa có chương trình `main`. Vì `Integer` là lớp con của `Number`, `IntegerResult.value()` tuân thủ hợp đồng từ `GeneralResult`. Một instance `Counter` có thể được sử dụng qua cả hai interface.

## 4. Những xung đột thật sự không thể giải quyết bằng một phương thức

### Hai kiểu tham chiếu không thể cùng được thỏa mãn

~~~java
interface TextReader {
    String read();
}

interface NumericReader {
    Integer read();
}

// CỐ Ý SAI.
class DualReader implements TextReader, NumericReader {
    @Override
    public Object read() {
        return "data";
    }
}
~~~

`Object` có khả năng giữ giá trị `String` hoặc `Integer` tại runtime, nhưng **kiểu trả về khai báo** là `Object` quá rộng so với cả `String` lẫn `Integer`. Vì thế phương thức trên không triển khai đúng hai hợp đồng. Thay `Object` bằng `String` hay `Integer` cũng chỉ thỏa được một phía.

Không thể khai báo thêm `Integer read()` bên cạnh `String read()`, bởi Java không overload theo kiểu trả về. Ép kiểu trong thân phương thức, thay đổi giá trị trả về lúc runtime, thêm `@Override` hay sử dụng `default` không làm biến mất sự không tương thích của kiểu khai báo.

### Xung đột kiểu nguyên thủy và void

~~~java
interface IntMetric {
    int measure();
}

interface LongMetric {
    long measure();
}

// CỐ Ý SAI.
interface ConflictingMetric extends IntMetric, LongMetric {
}
~~~

`int` và `long` khác nhau; một phương thức `measure()` không thể thỏa cả hai chỉ nhờ widening conversion. Tương tự, `void execute()` và `boolean execute()` có cùng chữ ký nhưng kiểu trả về không tương thích. Trường hợp `int` và `Integer` cũng không được giải quyết bằng autoboxing.

### Chú ý với generic

Các kiểu tham số hóa như `List<String>` và `List<Integer>` không có quan hệ subtype với nhau chỉ vì cùng bắt đầu bằng `List`:

~~~java
interface Names {
    java.util.List<String> items();
}

interface Counts {
    java.util.List<Integer> items();
}

// CỐ Ý SAI.
interface ImpossibleCatalog extends Names, Counts {
}
~~~

Ví dụ này cũng bị lỗi vì các phương thức cùng chữ ký có yêu cầu kiểu trả về generic không tương thích. Generic trong Java không tự biến `List<String>` thành một kiểu con của `List<Integer>`. Cần cân nhắc thiết kế lại hợp đồng, loại dữ liệu hoặc đặt tên hành vi khác nhau; dùng raw type/ép kiểu không an toàn để né lỗi chỉ làm mất kiểm tra kiểu.

**Lưu ý nâng cao:** Hai kiểu trả về là interface *khác nhau* không mặc nhiên có nghĩa là không thể triển khai đồng thời. Một lớp cụ thể có thể thực hiện cả hai interface kiểu trả về đó; nếu phương thức của lớp trả về kiểu cụ thể phù hợp với cả hai, hai hợp đồng có thể cùng được thỏa mãn. Hãy phân tích khả năng thay thế kiểu thực sự, thay vì suy luận từ việc tên kiểu trả về khác nhau. Tuy nhiên, kế thừa đồng thời nhiều khai báo trong một interface con có quy tắc riêng về các phương thức được thừa kế; đừng giả định một cách giải cho class sẽ làm mọi `interface extends A, B` hợp lệ.

## 5. Cách giải quyết khi hợp đồng không tương thích

### Cách A: Điều chỉnh tên hoặc ý nghĩa phương thức nếu kiểm soát được API

Nếu hai hành vi vốn khác nhau về ý nghĩa, tách rõ tên hợp đồng:

~~~java
interface TextIdentifier {
    String textId();
}

interface NumericIdentifier {
    int numericId();
}

final class Product implements TextIdentifier, NumericIdentifier {
    private final int number;

    Product(int number) {
        this.number = number;
    }

    @Override
    public String textId() {
        return "P-" + number;
    }

    @Override
    public int numericId() {
        return number;
    }
}
~~~

Hai phương thức `textId()` và `numericId()` có chữ ký khác nhau. Cách đặt tên này còn làm rõ một giá trị dùng làm mã hiển thị, một giá trị dùng làm mã số nội bộ. Đây là đoạn triển khai minh họa; không có `main`.

### Cách B: Thống nhất hợp đồng về kiểu trả về có quan hệ subtype

Nếu hai interface thực sự mô tả cùng một thao tác, có thể sửa API của mình để sử dụng kiểu phù hợp, chẳng hạn một hợp đồng trả về `Number` và một hợp đồng khác trả về `Integer`. Khi đó phương thức trả về `Integer` có thể đáp ứng cả hai, như ví dụ `GeneralResult` / `IntegerResult` ở trên.

Không nên ép các hợp đồng dùng một kiểu chung quá rộng như `Object` chỉ để biên dịch: điều này chuyển gánh nặng kiểm tra kiểu sang các nơi sử dụng. Việc thay đổi kiểu trả về của public API cũng có thể ảnh hưởng mã nguồn/nhị phân phụ thuộc, nên cần xem xét phạm vi tương thích khi sửa thư viện đã phát hành.

### Cách C: Dùng hai adapter khi không thể sửa interface gốc

Nếu `TextId` và `NumericId` là hợp đồng của thư viện bên ngoài, một đối tượng dữ liệu dùng chung có thể được bao bởi **hai lớp adapter** khác nhau. Mỗi adapter chỉ triển khai hợp đồng của mình, tránh buộc một class phải có hai `id()` với kiểu trả về không tương thích.

Ví dụ sau là chương trình đầy đủ. Lưu thành `IdAdapterDemo.java`:

~~~java
interface TextId {
    String id();
}

interface NumericId {
    Integer id();
}

final class RecordData {
    private final int value;

    RecordData(int value) {
        this.value = value;
    }

    int number() {
        return value;
    }
}

final class TextIdAdapter implements TextId {
    private final RecordData data;

    TextIdAdapter(RecordData data) {
        this.data = data;
    }

    @Override
    public String id() {
        return "ID-" + data.number();
    }
}

final class NumericIdAdapter implements NumericId {
    private final RecordData data;

    NumericIdAdapter(RecordData data) {
        this.data = data;
    }

    @Override
    public Integer id() {
        return data.number();
    }
}

public class IdAdapterDemo {
    public static void main(String[] args) {
        RecordData data = new RecordData(42);
        TextId textApi = new TextIdAdapter(data);
        NumericId numericApi = new NumericIdAdapter(data);

        System.out.println(textApi.id());
        System.out.println(numericApi.id() + 1);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 IdAdapterDemo.java
java IdAdapterDemo
~~~

Đầu ra:

~~~text
ID-42
43
~~~

`TextIdAdapter` và `NumericIdAdapter` cùng sử dụng `RecordData`, nhưng mỗi adapter có một trách nhiệm và hợp đồng riêng. Dữ liệu gốc là `42`; phía văn bản nhận `"ID-42"`, phía số nhận `Integer` có giá trị `42`, cộng 1 được `43`. Khi thay đổi lớp cung cấp dữ liệu, chỉ cần cập nhật adapter tương ứng.

Nếu yêu cầu bắt buộc một lớp duy nhất phải trực tiếp `implements TextId, NumericId` với hai kiểu `String`/`Integer` cho cùng `id()`, thì **không có cách viết một phương thức Java hợp lệ** để giữ nguyên đồng thời cả hai hợp đồng đó. Cần đổi mô hình hoặc dùng lớp trung gian riêng.

## 6. Phân biệt xung đột kiểu trả về với xung đột default method

Cần xác định đúng nguyên nhân:

- **Xung đột return type:** cùng chữ ký nhưng kiểu trả về không thể thay thế nhau. Viết lại phần thân, thêm `@Override` hay chọn một `default` không chữa được mâu thuẫn kiểu.
- **Xung đột default method:** hai interface cung cấp implementation mặc định trùng chữ ký. Khi các kiểu trả về tương thích, lớp triển khai có thể cần ghi đè tường minh để chọn hoặc kết hợp hành vi; đây là bài toán ưu tiên implementation, khác với bài toán hợp đồng kiểu.

Ví dụ, nếu `interface A { default String label() { return "A"; } }` và `interface B { default String label() { return "B"; } }`, lớp triển khai cả hai phải tự định nghĩa `public String label()` (có thể gọi `A.super.label()` hoặc `B.super.label()` khi hợp lệ). Việc cả hai trả về `String` không tự quyết định lớp chọn thân phương thức nào.

## 7. Quy trình chẩn đoán lỗi biên dịch

Khi `class X implements First, Second` hoặc `interface Combined extends First, Second` gặp lỗi quanh một phương thức, thực hiện lần lượt:

1. **So sánh tên và tham số:** chúng có cùng chữ ký hoặc *override-equivalent* không? Nếu khác danh sách tham số, có thể là hai overload thông thường.
2. **So sánh kiểu trả về khai báo:** trùng nhau, hiệp biến, hay không thể thay thế? Nhớ phân biệt primitive, `void`, reference type và generic.
3. **Kiểm tra phương thức triển khai:** có đúng mức truy cập `public` và kiểu trả về thay thế hợp lệ cho **từng** interface cần triển khai không?
4. **Xác định quyền kiểm soát API:** tự sở hữu interface thì có thể đổi tên hoặc chuẩn hóa kiểu; interface bên thứ ba thì thường dùng composition/adapter.
5. **Biên dịch lại tại chỗ:** lỗi xảy ra ở compile time nên không thể dùng `instanceof` hoặc bắt ngoại lệ runtime để thay cho việc chỉnh khai báo.

Thông điệp lỗi có thể có dạng “return type is not compatible” hoặc “inherits abstract and default / unrelated defaults” trong các trường hợp khác nhau. Đọc tên phương thức, kiểu đang được yêu cầu và nơi kế thừa để phân biệt nguyên nhân thật.

## 8. Câu hỏi tự kiểm tra

1. Hai interface cùng khai báo `String fetch()` và `Integer fetch()`: một class triển khai cả hai có thể thêm hai phương thức chỉ khác kiểu trả về hay không?
2. Vì sao `String render()` có thể triển khai `CharSequence render()`?
3. Nếu hợp đồng yêu cầu `long total()`, trả về `int total()` có hợp lệ vì int chuyển thành long được hay không?
4. `List<String> items()` và `List<Integer> items()` có tự động tương thích vì cùng là `List` không?
5. Nếu hai thư viện cung cấp interface có `id()` trả về hai kiểu không thể hòa giải và không thể chỉnh thư viện, cách thiết kế nào giữ được cả hai hợp đồng?

**Gợi ý đáp án:** (1) Không; Java không overload theo return type. (2) Vì `String` là subtype của `CharSequence` (covariant return). (3) Không, primitive return phải cùng kiểu. (4) Không, kiểu generic khác nhau không mặc nhiên có quan hệ subtype. (5) Dùng các adapter riêng cùng khai thác dữ liệu/lõi xử lý chung, hoặc sửa kiến trúc nơi tích hợp.

## 9. Đọc thêm từ đặc tả Java

- [JLS `8.4.2` — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2): quy tắc chữ ký phương thức và overload.
- [JLS `8.4.5` — Method Result](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.5): kiểu trả về và quy tắc return-type-substitutability.
- [JLS `9.4.1.3` — Inheriting Methods with Override-Equivalent Signatures](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1.3): các phương thức cùng chữ ký thừa kế trong interface.

**Ghi nhớ:** nhiều interface chỉ được kết hợp an toàn khi một cách triển khai hợp lệ có thể đáp ứng tất cả phương thức cùng chữ ký của chúng. Khi các yêu cầu return type thực sự mâu thuẫn, hãy sửa hợp đồng hoặc tách lớp thích ứng, thay vì tìm cách overload theo kiểu trả về.
