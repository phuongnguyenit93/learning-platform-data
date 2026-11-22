# Thành phần tham chiếu trong Java record dùng quan hệ bằng nhau của chính kiểu thành phần

## 1. Ý nghĩa của “bằng nhau” trong record

Một `record` khai báo một tập **record component** mô tả dữ liệu của một giá trị. Khi không tự ghi đè, Java sinh các thành phần cần thiết, gồm constructor chuẩn, accessor tương ứng, `equals(Object)`, `hashCode()` và `toString()`.

Ví dụ:

~~~java
record Customer(String name, int age) {}
~~~

Hai `Customer` khác đối tượng có thể bằng nhau về giá trị nếu các component tương ứng bằng nhau. Tuy nhiên **mỗi kiểu component quyết định thế nào là bằng nhau**:

- Component nguyên thủy như `int` được so theo giá trị nguyên thủy phù hợp.
- **Component tham chiếu** như `String`, `List<String>`, `BigDecimal`, đối tượng lớp tự viết hay mảng được so dựa trên **ngữ nghĩa `equals()` của chính đối tượng component**.
- Hai component tham chiếu đều `null` được coi bằng nhau; chỉ một bên `null` thì không bằng nhau.
- Cần so tất cả component tương ứng; thứ tự khai báo và kiểu của component là một phần của cấu trúc record.

Nói cách khác, record không tự biết thế nào là “cùng nội dung” đối với mọi loại đối tượng mà nó chứa. Nếu component có kiểu mà `equals()` được định nghĩa theo giá trị, record kế thừa ý nghĩa đó. Nếu component dùng `Object.equals()` theo danh tính, record cũng chịu quy tắc danh tính cho component ấy.

## 2. Cách hình dung `equals()` và `hashCode()` được sinh ra

Với một record như:

~~~java
record Product(String code, int quantity) {}
~~~

Về **ngữ nghĩa**, phép kiểm tra bằng nhau của record được hiểu qua các bước:

1. Nếu hai tham chiếu chỉ cùng một đối tượng, chúng bằng nhau.
2. Đối tượng được so phải là record thuộc **cùng lớp record lúc chạy**.
3. Những component nguyên thủy tương ứng phải có giá trị bằng nhau theo quy tắc dành cho kiểu đó.
4. Những component tham chiếu tương ứng phải bằng nhau theo quan hệ `equals` của đối tượng component, bao gồm xử lý `null`.

Để diễn giải, có thể hình dung logic tương tự:

~~~java
// Chỉ để giải thích hành vi của Product; không phải Java source do trình biên dịch tạo.
if (this == other) return true;
if (!(other instanceof Product p)) return false;
return quantity == p.quantity
        && java.util.Objects.equals(code, p.code);
~~~

Đoạn này là **mã minh họa**, không phải cách triển khai bytecode bắt buộc của JVM, cũng không phải một phương thức độc lập có thể dán chạy ngay. Với record, trình biên dịch/JVM có thể hiện thực các phương thức sinh ra qua cơ chế động; ta cần dựa vào **hợp đồng hành vi**, không dựa vào một chuỗi lệnh bytecode cụ thể. Record là `final` nên không có lớp con của chính record đó.

`hashCode()` được sinh ra dựa trên các component tương ứng, nhất quán với quan hệ bằng nhau do `equals()` sinh ra. Với component tham chiếu, mã hash phụ thuộc vào `hashCode()` của đối tượng component; với `null` có quy tắc phù hợp. **Không dựa vào một giá trị số hash cụ thể** hay giả định thuật toán của record giống hệt `Objects.hash(...)`: điều cần giữ là **hai record bằng nhau phải có hash bằng nhau**.

`toString()` được sinh cũng hiển thị các component; đây là biểu diễn để đọc/debug, không phải căn cứ định nghĩa equality. Đặc biệt, mảng không tự được in thành danh sách phần tử khi xuất hiện như một object trong chuỗi.

## 3. `String`, `List` và `BigDecimal`: ba kiểu tham chiếu có ngữ nghĩa khác nhau

Một số kiểu thường dùng có `equals()` dựa trên giá trị, nhưng **giá trị** được định nghĩa khác nhau:

- `String.equals` so dãy ký tự (phân biệt chữ hoa/thường); hai đối tượng String khác nhau chứa cùng ký tự vẫn bằng nhau.
- `List.equals` so **số lượng và thứ tự**, rồi so từng cặp phần tử qua quan hệ bằng nhau của các phần tử. Hai danh sách thuộc các triển khai khác nhau vẫn có thể bằng nhau nếu cùng chuỗi phần tử theo quy tắc của `List`.
- `BigDecimal.equals` so **giá trị và scale**; `new BigDecimal("1.0")` không `equals` với `new BigDecimal("1.00")` dù phép `compareTo` trả về `0`. Record chứa BigDecimal dùng chính quy tắc `equals` này.
- Các kiểu giá trị khác như `LocalDate`, `UUID`, các wrapper nguyên thủy và enum có ngữ nghĩa equals riêng. Record dùng ngữ nghĩa thích hợp của đối tượng component.
- Nếu component được khai báo là một interface, **kiểu đối tượng thực tế** cung cấp cách triển khai `equals()` khi phương thức được gọi; tên interface không tự tạo ra một định nghĩa equals chung cho mọi hiện thực.

### Ví dụ chạy được: record với nhiều component tham chiếu

Tạo tệp `ReferenceComponentsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public class ReferenceComponentsDemo {
    record Invoice(String customer, List<String> tags, BigDecimal amount) {}

    public static void main(String[] args) {
        Invoice first = new Invoice(
                new String("An"),
                new ArrayList<>(List.of("java", "core")),
                new BigDecimal("1.0")
        );
        Invoice equal = new Invoice(
                "An",
                List.of("java", "core"),
                new BigDecimal("1.0")
        );
        Invoice differentScale = new Invoice(
                "An",
                List.of("java", "core"),
                new BigDecimal("1.00")
        );
        Invoice differentOrder = new Invoice(
                "An",
                List.of("core", "java"),
                new BigDecimal("1.0")
        );

        System.out.println("same identity: " + (first == equal));
        System.out.println("same components: " + first.equals(equal));
        System.out.println("same hash: "
                + (first.hashCode() == equal.hashCode()));
        System.out.println("different BigDecimal scale: "
                + first.equals(differentScale));
        System.out.println("different List order: "
                + first.equals(differentOrder));
        System.out.println("BigDecimal numeric compare: "
                + first.amount().compareTo(differentScale.amount()));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 ReferenceComponentsDemo.java
java ReferenceComponentsDemo
~~~

Stdout:

~~~text
same identity: false
same components: true
same hash: true
different BigDecimal scale: false
different List order: false
BigDecimal numeric compare: 0
~~~

Giải thích: `first` và `equal` là hai đối tượng `Invoice` riêng biệt, nhưng `String.equals`, `List.equals` và `BigDecimal.equals` của ba component đều trả về `true`, nên hai record bằng nhau. Chênh lệch scale của BigDecimal hoặc thay đổi thứ tự phần tử danh sách làm record khác nhau, vì record không tự chuẩn hóa các component theo mong muốn nghiệp vụ.

Nếu yêu cầu nghiệp vụ muốn coi `1.0` và `1.00` là cùng giá trị, có thể **chuẩn hóa BigDecimal trước khi lưu trong component** với quy tắc đã xác định, hoặc tự thiết kế `equals/hashCode` tương ứng; không nên tự thay riêng phần so sánh equals mà quên cập nhật hash.

## 4. Lớp component không ghi đè `equals()`: record so theo danh tính của component

Một lớp tùy biến mặc định kế thừa `Object.equals`, về cơ bản chỉ coi hai tham chiếu là bằng nhau nếu chúng trỏ đến **cùng đối tượng**. Record chứa lớp đó không tự động suy luận ra “hai field giống nhau thì component bằng nhau”.

Tạo tệp `IdentityComponentDemo.java`:

~~~java
public class IdentityComponentDemo {
    static final class Token {
        private final String code;

        Token(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    record Session(Token token) {}
    record ValueToken(String code) {}
    record ValueSession(ValueToken token) {}

    public static void main(String[] args) {
        Token leftToken = new Token("X");
        Token rightToken = new Token("X");

        Session first = new Session(leftToken);
        Session second = new Session(rightToken);
        Session aliasValue = new Session(leftToken);

        System.out.println("Token content: "
                + leftToken.code().equals(rightToken.code()));
        System.out.println("distinct Token objects: " + first.equals(second));
        System.out.println("same Token object: " + first.equals(aliasValue));

        ValueSession valueA = new ValueSession(new ValueToken("X"));
        ValueSession valueB = new ValueSession(new ValueToken("X"));
        System.out.println("nested record value: "
                + valueA.equals(valueB));
        System.out.println("nested record hash: "
                + (valueA.hashCode() == valueB.hashCode()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 IdentityComponentDemo.java
java IdentityComponentDemo
~~~

Stdout:

~~~text
Token content: true
distinct Token objects: false
same Token object: true
nested record value: true
nested record hash: true
~~~

Hai `Token("X")` có chuỗi `code` bằng nhau, nhưng `Token` không override `equals` nên các đối tượng Token khác nhau không bằng nhau; do đó hai `Session` tương ứng cũng không bằng nhau. Ngược lại, `ValueToken` là một record có component `String` và được sinh equality theo giá trị; hai `ValueSession` chứa hai `ValueToken("X")` riêng biệt vẫn bằng nhau.

Nếu một lớp component có **quan hệ bằng nhau theo giá trị**, hãy cài `equals` và `hashCode` nhất quán tại chính lớp đó. Thiết kế value object như record cũng là lựa chọn tốt khi muốn equality do các component quyết định.

### Bẫy với `StringBuilder`

`StringBuilder` là đối tượng mutable và không ghi đè `equals(Object)` để so nội dung ký tự. Vì vậy:

~~~java
record Text(StringBuilder builder) {}

Text a = new Text(new StringBuilder("hello"));
Text b = new Text(new StringBuilder("hello"));
System.out.println(a.equals(b)); // false
~~~

Đây là đoạn minh họa đặt trong ngữ cảnh Java hợp lệ, không phải tệp độc lập. Nếu ý định là bình đẳng theo nội dung chữ, hãy dùng component `String` bất biến hoặc chuyển `builder.toString()` thành chuỗi khi xây dựng record.

## 5. Trường hợp đặc biệt: component là mảng

Một component `byte[]`, `int[]` hay `String[]` kế thừa `Object.equals` theo identity, nên hai record nhận hai mảng khác tham chiếu vẫn không bằng nhau dù nội dung trùng khớp. Đây là ngoại lệ cần nhớ khi khảo sát equality của **kiểu tham chiếu**. Nếu nghiệp vụ yêu cầu so nội dung, phải dùng đúng cặp `Arrays.equals`/`Arrays.hashCode` (hoặc `deepEquals`/`deepHashCode` cho mảng lồng) và bảo vệ mọi đường sửa mảng qua constructor/accessor. Bài kế tiếp về mảng trình bày ví dụ chạy và từng giới hạn; ở đây điều cốt lõi là record tuân hợp đồng `equals` của component.

## 6. Component là collection: bình đẳng theo tập hợp nhưng không tự thành bất biến

Các collection phổ biến có quan hệ bằng nhau riêng:

| Kiểu component | Ngữ nghĩa `equals` điển hình | Tác động lên record |
| --- | --- | --- |
| `List<T>` | Cùng kích thước, cùng thứ tự và các phần tử tương ứng bằng nhau | Đảo thứ tự thường làm record không bằng nhau |
| `Set<T>` | Cùng tập phần tử (không xét thứ tự lặp) | Hai Set khác triển khai vẫn có thể bằng nhau |
| `Map<K,V>` | Cùng ánh xạ khóa → giá trị theo hợp đồng `Map` | Hai Map chứa cùng mappings có thể bằng nhau |
| `Optional<T>` | Hai Optional rỗng bằng nhau, hoặc cùng có các giá trị bằng nhau | Record theo ngữ nghĩa `Optional.equals` |
| `StringBuilder` | Mặc định so danh tính đối tượng | Hai builder có cùng ký tự nhưng khác đối tượng thường không bằng nhau |
| `byte[]` hoặc `Object[]` | Mặc định so danh tính mảng | Cần override nếu muốn so nội dung |
| Lớp tự viết chưa override `equals` | Mặc định so danh tính đối tượng | Record không so các trường nội bộ của lớp đó |
| Record lồng nhau | Theo `equals` của record lồng | Có thể so giá trị nhiều cấp, trừ khi một component sâu hơn dùng danh tính |

**Lưu ý về collection chứa mảng:** một `List<int[]>` dùng `List.equals` để so từng phần tử, nhưng các phần tử `int[]` vẫn dùng equality theo danh tính. Vì vậy, dù một List có `equals` theo vị trí, điều đó **không đồng nghĩa so sâu nội dung mảng nằm trong List**.

### Mutability ảnh hưởng equality và hash

Record bảo đảm các trường component là `private final`, nghĩa là tham chiếu component **không được gán lại** sau khi khởi tạo. Điều này **không** ngăn trạng thái của đối tượng được tham chiếu thay đổi.

Tạo tệp `MutableComponentDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MutableComponentDemo {
    record Roles(List<String> names) {}

    public static void main(String[] args) {
        List<String> external = new ArrayList<>(List.of("reader"));
        Roles first = new Roles(external);
        Roles baseline = new Roles(List.of("reader"));

        System.out.println("before mutation: " + first.equals(baseline));
        external.add("writer");
        System.out.println("after mutation: " + first.equals(baseline));
        System.out.println("record sees mutation: " + first.names());

        Roles safe = new Roles(List.copyOf(external));
        external.add("admin");
        System.out.println("defensive snapshot: " + safe.names());
    }
}
~~~

~~~bash
javac -encoding UTF-8 MutableComponentDemo.java
java MutableComponentDemo
~~~

Stdout:

~~~text
before mutation: true
after mutation: false
record sees mutation: [reader, writer]
defensive snapshot: [reader, writer]
~~~

Ở đây `first.names()` và `external` cùng trỏ vào một danh sách mutable. Sửa `external` làm kết quả equality của `first` thay đổi. Nếu record được dùng làm **khóa `HashMap` hoặc phần tử `HashSet`**, thay đổi component quyết định hash có thể khiến lookup không còn vận hành như kỳ vọng.

`List.copyOf(external)` tạo một danh sách không thể sửa qua API danh sách và giữ snapshot phần tử hiện có trong ví dụ. Nó **không tự sao chép sâu** các phần tử mutable: nếu danh sách chứa các đối tượng còn sửa được thì trạng thái chúng vẫn có thể thay đổi.

### Compact constructor để phòng vệ khi tạo record

Nếu component là `List<String>` và muốn luôn giữ snapshot bất biến, có thể viết:

~~~java
import java.util.List;
import java.util.Objects;

record SafeRoles(List<String> names) {
    SafeRoles {
        names = List.copyOf(Objects.requireNonNull(names));
    }
}
~~~

Đây là ví dụ lớp record độc lập có thể biên dịch; `List.copyOf` không nhận phần tử `null`. Sau compact constructor, trường component nhận danh sách đã được sao chép/chuẩn hóa; accessor sinh mặc định trả danh sách không thể sửa qua API của nó. Đối với phần tử `String` bất biến, cách này phù hợp để bảo vệ equality. Còn với component mảng, cần clone cả khi nhận vào và khi trả ra nếu muốn ngăn sửa trực tiếp.

## 7. `null`, kiểu tham chiếu và toán tử `==`

Cho record:

~~~java
record Person(String firstName, String lastName) {}
~~~

Hai `Person(null, "A")` bằng nhau vì các component thứ nhất đều là `null` và component thứ hai là hai String có nội dung bằng nhau. Một `Person(null, "A")` và một `Person("", "A")` không bằng nhau: `null` và chuỗi rỗng là hai giá trị khác nhau.

Với component tham chiếu, việc record dùng quan hệ `equals` của đối tượng component không đồng nghĩa với việc sử dụng `==` trên component ấy. Với `String`, `==` có thể trả về `false` cho hai chuỗi khác đối tượng nhưng cùng nội dung, trong khi record chứa chúng có thể bằng nhau.

Hai **record instance** được so bằng `==` chỉ khi chúng là cùng đối tượng; sử dụng `recordA.equals(recordB)` khi muốn so giá trị theo hợp đồng record. Đây là sự khác biệt giữa **danh tính của record** và **bằng nhau của các component**.

## 8. Một vài ranh giới cần biết khi thiết kế

### Lớp record khác nhau không tự bằng nhau

Hai loại record dù khai báo cùng tên component và giá trị giống nhau vẫn là hai lớp khác nhau. Phương thức `equals` được sinh yêu cầu record có **cùng kiểu record thực tế**, không tự ghép cấu trúc giữa các lớp.

~~~java
record A(String code) {}
record B(String code) {}
// new A("x").equals(new B("x")) == false
~~~

Đoạn này minh họa hành vi, có thể khai báo trong cùng một lớp bao hoặc cùng gói với tên khác nhau.

### Component `float` và `double`

Chúng là **primitive**, vì vậy không áp dụng quy tắc gọi `equals` của đối tượng tham chiếu. Tuy nhiên so sánh được sinh của record dùng chính sách phù hợp để giữ hợp đồng hash, trong đó **các giá trị `NaN` được coi bằng nhau với nhau** và **`+0.0` khác `-0.0`**. Không suy rộng máy móc từ toán tử `==` của primitive sang mọi hành vi so sánh record. Điều này giúp phân biệt rõ ranh giới của bài: **component tham chiếu** chịu quy tắc equality của kiểu component; **component primitive** theo quy tắc riêng của primitive trong record.

### Tự ghi đè `equals/hashCode` thay đổi hợp đồng

Record cho phép tự cài `equals` và `hashCode`, nhưng lúc đó người lập trình chịu trách nhiệm về phản xạ, đối xứng, bắc cầu, tính nhất quán, hành vi với `null` và quy tắc **bằng nhau thì hash bằng nhau**. Nếu ghi đè để so nội dung mảng, chuẩn hóa BigDecimal hoặc bỏ qua component nào đó, hãy cập nhật cả hai phương thức đồng bộ và kiểm tra tác động tới đối tượng dùng làm key.

### Đừng suy ra bất biến sâu chỉ từ từ khóa `record`

Record có các trường component cuối cùng, nhưng đối tượng nằm sau tham chiếu có thể mutable. Nếu `equals` hoặc `hashCode` của component dựa vào trạng thái mutable, thì kết quả equality/hash của record cũng có thể biến động. Nếu cần value object ổn định, ưu tiên component bất biến, copy phòng vệ và hạn chế trả về dữ liệu mutable nội bộ.

## 9. Những nhầm lẫn phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| Record tự so tất cả trường bên trong đối tượng component tham chiếu. | Record sinh mặc định dùng quan hệ `equals` do kiểu component cung cấp; nó không phản chiếu sâu mọi trường. |
| Hai `String` khác đối tượng thì hai record chứa chúng cũng khác nhau. | `String.equals` so nội dung; hai record có thể bằng nhau. |
| Hai component `BigDecimal("1.0")` và `BigDecimal("1.00")` tương đương trong record vì có cùng giá trị số. | `BigDecimal.equals` còn xét scale; record theo chính quy tắc đó. |
| Component mảng luôn được record so bằng `Arrays.equals`. | Sai. Equality record mặc định nhìn thấy mảng như đối tượng và so danh tính mảng. |
| Component `List<int[]>` khiến mọi mảng con được so theo phần tử. | `List.equals` gọi equality của từng phần tử, còn `int[]` dùng danh tính. |
| Các field của record là `final` nên toàn bộ trạng thái bất biến. | `final` chỉ giữ ổn định tham chiếu; đối tượng component có thể mutable. |
| Có thể override riêng `equals` để so nội dung mảng mà giữ nguyên hash record mặc định. | Không an toàn, vì hai record bằng nhau có thể nhận hash khác nhau. |
| Hai record khác loại nhưng cùng cấu trúc dữ liệu sẽ bằng nhau. | Equality mặc định yêu cầu cùng loại record. |
| Thấy `hashCode` giống nhau là biết hai record bằng nhau. | Hash có thể va chạm; phải kiểm tra `equals`. |

## 10. Quy trình áp dụng và tự kiểm tra

Khi thiết kế record có các component tham chiếu:

1. **Liệt kê từng component** và kiểu của nó: `String`, `List`, `BigDecimal`, mảng, kiểu tùy biến hay record lồng.
2. **Xác định ngữ nghĩa equals của mỗi kiểu**: theo nội dung, theo thứ tự, theo scale, theo danh tính hay theo một quy tắc riêng.
3. **Kiểm tra phù hợp với nghiệp vụ**: hai record có cùng nội dung “nhìn bằng mắt” có thật sự cần bằng nhau không? Với mảng, builder hoặc lớp tùy biến chưa override `equals`, thường cần điều chỉnh mô hình dữ liệu.
4. **Đánh giá mutability**: liệu đối tượng component có thể bị thay đổi từ ngoài sau khi record được tạo? Có thể dùng `List.copyOf`, bản sao mảng hoặc kiểu bất biến không?
5. **Giữ đồng bộ `equals` và `hashCode`** nếu tự override: dùng cùng tập thuộc tính, cùng chính sách nông/sâu/chuẩn hóa.
6. **Kiểm thử các tình huống phân biệt**: hai đối tượng component khác nhau nhưng nội dung giống nhau; cùng tham chiếu component; `null`; danh sách đổi thứ tự; BigDecimal đổi scale; hai mảng cùng phần tử; biến đổi dữ liệu sau khi làm khóa `HashMap`.
7. **Ưu tiên khai báo record ngắn gọn** khi equality được sinh đã đúng ý nghĩa; chỉ viết thủ công khi có lý do thiết kế cụ thể và kiểm thử đầy đủ hợp đồng.

**Ghi nhớ:** record cung cấp equality theo các component, nhưng với **component tham chiếu**, “bằng nhau” phụ thuộc trực tiếp vào cách **kiểu đối tượng component định nghĩa `equals()`**. `String`, `List`, `BigDecimal`, mảng và lớp tùy biến có thể cho các kết quả rất khác nhau. Chọn đúng kiểu component, bảo vệ dữ liệu mutable và giữ `equals/hashCode` nhất quán quan trọng hơn việc chỉ nhìn hình dạng khai báo record.