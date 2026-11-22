# Giới hạn tham chiếu chính nó và F-bounded polymorphism trong Java Generics

## 1. Vấn đề: ràng buộc một kiểu bằng chính kiểu đó

Khi khai báo generic thông thường như `Box<T>`, Java không biết `T` có hành vi gì ngoài các hành vi của `Object`. Giới hạn kiểu (`bounded type parameter`) cho phép diễn đạt yêu cầu: kiểu được truyền vào phải thỏa mãn một quan hệ kế thừa hoặc triển khai interface nhất định.

Có những quan hệ mà chính tham số kiểu xuất hiện **bên trong giới hạn của nó**:

```java
interface Self<S extends Self<S>> {
    S copy();
}
```

Đây là **giới hạn tự tham chiếu** (*self-referential type bound*) hay một dạng **F-bounded polymorphism**. Đọc là: "`S` phải là kiểu triển khai `Self<S>`". Ở đây, `Self` đóng vai trò cấu trúc kiểu được áp dụng trở lại lên `S`.

Ví dụ một cách triển khai:

```java
final class Document implements Self<Document> {
    @Override
    public Document copy() {
        return new Document();
    }
}
```

Nhờ ràng buộc đó, thao tác `copy()` được biết là trả về `Document` khi làm việc với `Self<Document>`, thay vì chỉ trả về `Object` hoặc một interface quá chung.

**Điểm cốt lõi:** F-bound diễn đạt một *quan hệ kiểu tại thời điểm biên dịch*. Nó không tạo vòng lặp đệ quy ở runtime, cũng không tự bảo đảm tham số `S` chính là lớp đang viết.

## 2. Đọc đúng cú pháp và cơ chế kiểm tra kiểu

Một dạng điển hình:

```java
abstract class Base<S extends Base<S>> {
    abstract S next();
}

final class Concrete extends Base<Concrete> {
    @Override
    Concrete next() {
        return this;
    }
}
```

Phân tích:

- `S` là tham số kiểu của `Base`.
- `extends Base<S>` là **giới hạn trên** của `S`. Từ khóa `extends` trong generic dùng được cho cả class và interface.
- `Base<S>` bên phải là một *kiểu tham số hóa*; `S` được dùng làm đối số kiểu ngay trong khai báo giới hạn của `S`.
- `Concrete extends Base<Concrete>` hợp lệ vì `Concrete` thực sự là kiểu con của `Base<Concrete>`.
- Phương thức `next()` trong `Base<Concrete>` có kiểu trả về được trình biên dịch nhìn thấy là `Concrete`, nên mã gọi có thể tiếp tục dùng API riêng của `Concrete` mà không cần ép kiểu thủ công.

Có thể hình dung quan hệ:

```text
S thỏa điều kiện: S <: Base<S>
                       │
Concrete <: Base<Concrete>
                       │
Base<Concrete>.next() trả về Concrete
```

Ký hiệu `<:` nghĩa là "là kiểu con của". Trình biên dịch kiểm tra quan hệ này bằng hệ thống kiểu generic; không cần tạo ra vô hạn các lớp `Base<Base<Base<...>>>`.

### Hai kiểu khai báo cần phân biệt

```java
interface Comparable<T> {
    int compareTo(T other);
}
```

Riêng `Comparable<T>` **không** khai báo giới hạn đệ quy: `T` chưa bị ràng buộc. F-bound xuất hiện khi một khai báo khác quy định:

```java
static <T extends Comparable<T>> T choose(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Khi ấy, `T` phải có khả năng so sánh với đối tượng kiểu `T`. Ngược lại, cách viết `<T extends Comparable<?>>` chỉ nói rằng `T` so sánh được với *một kiểu nào đó*, chưa đủ để chứng minh `first.compareTo(second)` hợp lệ.

## 3. Ứng dụng 1: thuật toán generic cần so sánh

Một phương thức tìm phần tử lớn nhất cần biết chắc `compareTo` chấp nhận phần tử cùng nhóm đang xử lý. Trong thư viện Java, phiên bản giới hạn có tính ứng dụng rộng hơn là `Comparable<? super T>`:

```java
import java.util.List;

public class BoundMaxDemo {
    static <T extends Comparable<? super T>> T max(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("Danh sách không được rỗng");
        }

        T best = values.get(0);
        for (int i = 1; i < values.size(); i++) {
            T current = values.get(i);
            if (current.compareTo(best) > 0) {
                best = current;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        System.out.println(max(List.of(3, 8, 5)));
        System.out.println(max(List.of("An", "Binh", "Chi")));
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac BoundMaxDemo.java
java BoundMaxDemo
```

Kết quả:

```text
8
Chi
```

Lý do phương thức an toàn về kiểu:

1. `values` chứa các phần tử có kiểu `T`; `best` và `current` cùng kiểu `T`.
2. Giới hạn xác nhận rằng `T` triển khai `Comparable<X>` với một kiểu `X` là `T` hoặc **kiểu cha của `T`**.
3. Do đó `current.compareTo(best)` hợp lệ: đối số `best` có kiểu `T`, có thể được truyền vào vị trí nhận `X`.
4. Giá trị trả về vẫn giữ kiểu `T`, không bị hạ xuống `Object`.

`? super T` là **lower-bounded wildcard**; nó làm giới hạn linh hoạt hơn so với `Comparable<T>`. Chẳng hạn, `Student` kế thừa `Person`, còn `Person` triển khai `Comparable<Person>`. `Student` có thể tham gia thuật toán giới hạn bởi `Comparable<? super Student>` nhờ cơ chế so sánh kế thừa từ `Person`; giới hạn `Comparable<Student>` sẽ quá chặt trong trường hợp đó.

Chương trình trên giả định các phần tử không phải `null`, điều được bảo đảm bởi các ví dụ `List.of(...)`. Với đầu vào từ nguồn khác, cần xác định rõ chính sách xử lý `null`. Trường hợp danh sách rỗng được chặn tường minh để không truy cập `get(0)` sai.

**Lưu ý:** Ví dụ thuật toán này là một ứng dụng của giới hạn đệ quy thông qua `Comparable<? super T>`; nó không đòi mọi lớp được chọn phải viết `implements Comparable<ChínhNó>` trực tiếp. Đây là lý do wildcard `super` hữu ích trong thiết kế API.

## 4. Ứng dụng 2: giữ kiểu cụ thể trong fluent API

Trong một builder có kế thừa, setter được định nghĩa ở lớp cha nhưng khai báo trả về chính lớp cha có thể làm mất các phương thức riêng của lớp con khi gọi nối chuỗi. Giới hạn tự tham chiếu cho phép khai báo **kiểu builder cần trả về** như một tham số có tên:

```java
abstract class Builder<B extends Builder<B>> {
    private String name;

    B name(String value) {
        name = value;
        return self();
    }

    protected abstract B self();
}

final class UserBuilder extends Builder<UserBuilder> {
    UserBuilder age(int years) { return this; }

    @Override
    protected UserBuilder self() { return this; }
}
```

Khi gọi `new UserBuilder().name("Mai").age(20)`, compiler biết `name(...)` trả `UserBuilder`, nên tìm được phương thức `age(...)`. Lớp generic không thể viết `return this` với kiểu `B` một cách trực tiếp: `this` chỉ được biết là `Builder<B>`. `self()` trừu tượng chuyển trách nhiệm trả về đúng kiểu sang lớp lá, tránh unchecked cast `(B)this` ở base.

Đây là **đoạn minh họa đầy đủ các khai báo lớp**, không phải ví dụ có `main`. Với builder nhiều tầng, lớp trung gian còn phải truyền nguyên tham số `B` xuống lớp cha và builder lá override `build()` đúng kiểu sản phẩm. Bài riêng về builder có kế thừa thực hành chuỗi nhiều tầng, kiểu trả về theo từng call, validation và trạng thái mutable. Ở đây điều cần giữ là: **F-bound liên kết kiểu trả về fluent, không tự bảo đảm mọi lớp con chọn đúng self-type**.

## 5. Ứng dụng 3: `Enum<E extends Enum<E>>` trong Java chuẩn

Một ví dụ quan trọng về F-bound là `java.lang.Enum<E extends Enum<E>>`: với `enum Priority { LOW, MEDIUM, HIGH }`, Java thiết lập quan hệ kiểu tương ứng `Priority extends Enum<Priority>`. Bởi vậy `Priority.LOW.compareTo(Priority.HIGH)` hợp lệ, còn so sánh trực tiếp với hằng của enum khác bị từ chối bởi generic type checking.

Một phương thức dùng lại cho mọi enum nhưng vẫn giữ đúng `E`:

```java
static <E extends Enum<E>> E lastDeclared(Class<E> enumType) {
    E[] values = enumType.getEnumConstants();
    if (values == null || values.length == 0) {
        throw new IllegalArgumentException("Không có enum constants");
    }
    return values[values.length - 1];
}
```

Khi gọi `lastDeclared(Priority.class)`, kết quả có kiểu `Priority`; với các hằng được khai báo như trên, kết quả là `HIGH`. `Class<E>` mang thông tin kiểu enum cần thiết để lấy constants; `E.values()` không hợp lệ vì `values()` là phương thức được trình biên dịch tạo riêng cho *từng* enum cụ thể. Không thể tự viết một class thường `extends Enum`.

`EnumSet<E>` và `EnumMap<E,V>` cũng dựa trên giới hạn đệ quy, nhưng còn nhiều trường hợp cần phân biệt: `Enum.valueOf`, thứ tự khai báo, constant-specific class body, `getClass()` khác `getDeclaringClass()`, và chính sách null. Những hành vi đặc thù của enum được triển khai chi tiết ở bài chuyên biệt; mục này minh họa **cách F-bound xuất hiện trong một API JDK thực tế**.

## 6. Bảo đảm tĩnh và giới hạn của “self type”

Xét `abstract class Base<S extends Base<S>>`. Compiler chứng minh **`S` là subtype của `Base<S>`**, chứ không chứng minh `S` luôn bằng lớp đang khai báo `extends Base<S>`.

```java
abstract class Base<S extends Base<S>> {
    abstract S next();
}

final class Right extends Base<Right> {
    @Override Right next() { return this; }
}

final class Wrong extends Base<Right> {
    @Override Right next() { return new Right(); }
}
```

Cả `Right` và `Wrong` đều hợp lệ: khi khai báo `Wrong extends Base<Right>`, kiểu `Right` vẫn thỏa điều kiện `Right extends Base<Right>`. Kết quả `new Wrong().next()` có kiểu `Right` và là một đối tượng `Right`, **không phải** `Wrong`; F-bound không hứa `next()` trả về `this`.

Nếu base cố `return (S)this`, cast bị **unchecked** và có thể dẫn tới `ClassCastException` khi caller chờ kiểu cụ thể sau erasure. Cách thực tế là tách `self()` trừu tượng, giới hạn hierarchy bằng `final`/`sealed` khi thích hợp và review tham số generic của lớp con — nhưng từng biện pháp vẫn có giới hạn. Chủ đề **giới hạn của kiểu tự tham chiếu** trình bày riêng các phản ví dụ lớp con lệch kiểu, lớp cháu, việc chèn cast trong bytecode, và phạm vi bảo vệ thực của sealed hierarchy.

## 7. F-bound và xóa kiểu (type erasure)

Generics của Java chủ yếu được kiểm tra lúc biên dịch. Trong bytecode, tham số kiểu bị **xóa kiểu** theo giới hạn của nó:

- Nếu `T` không có giới hạn, erasure thường là `Object`.
- Với `<S extends Base<S>>`, erasure của `S` là `Base`.
- Với `<T extends Comparable<? super T>>`, erasure của `T` là `Comparable`.

Bởi vậy, F-bound không tạo ra một bản bytecode mới cho từng `Concrete`. Trình biên dịch có thể chèn cast tại chỗ dùng và sinh *bridge method* để giữ tương thích đa hình khi phương thức override có kiểu trả về chuyên biệt. Điều đó lý giải vì sao kiểm tra generic rất hữu ích ở compile time nhưng không thể chứng minh cast unchecked từ `this` sang một tham số kiểu sau erasure.

Hệ quả thực tế:

- Không thể viết `new S()` chỉ vì `S extends Base<S>`; giới hạn không cung cấp constructor có thể khởi tạo qua type parameter.
- Không thể dùng trực tiếp `S.class`; thông tin kiểu cụ thể không có sẵn dưới dạng class literal của tham số kiểu.
- Không nên dùng raw type `Base` vì nó bỏ qua phần lớn kiểm tra generic và có thể dẫn đến unchecked warning.
- Không suy luận rằng F-bound biến Java thành hệ thống có *dependent type* hay phép kiểm tra chính xác kiểu runtime của receiver.

Nếu cần tạo đối tượng `S`, hãy nhận một `Supplier<S>`, `Class<S>` hoặc factory thích hợp từ bên ngoài; mỗi cách có hợp đồng và giới hạn riêng.

## 8. So sánh với các cơ chế gần giống

| Khai báo | Ý nghĩa | Khi nào dùng |
|---|---|---|
| `<T>` | Bất kỳ kiểu tham chiếu hợp lệ nào | Không cần gọi hành vi chuyên biệt của `T` |
| `<T extends Number>` | `T` là subtype của `Number` | Xử lý chung các kiểu số |
| `<T extends Comparable<T>>` | `T` so sánh được với `T` | Quan hệ đối xứng theo chính kiểu đang xét |
| `<T extends Comparable<? super T>>` | `T` so sánh được với `T` hoặc kiểu cha của `T` | Thuật toán so sánh linh hoạt hơn, thường phù hợp API tổng quát |
| `<S extends Base<S>>` | `S` là subtype của `Base<S>` | Giữ kiểu cụ thể khi kế thừa API fluent hoặc thao tác đệ quy trên kiểu |
| `<? extends Base<?>>` | Một kiểu chưa biết là subtype của `Base<?>` | Đọc các đối tượng không cần giữ danh tính tham số kiểu cụ thể |

**Chú ý sự khác biệt giữa type parameter và wildcard.** `S` là một biến kiểu có tên: cùng một `S` có thể dùng nhất quán ở đầu vào, đầu ra và giới hạn. `?` là một kiểu chưa biết ở vị trí đối số generic; nó không tự tạo ra một tên chung để dùng xuyên suốt nhiều vị trí trong cùng chữ ký. Khi API cần diễn đạt "nhận hai đối số cùng `S` và trả về `S`", type parameter thường rõ ý hơn.

F-bound cũng không làm generic Java trở nên đồng biến: `List<Cat>` vẫn không phải subtype của `List<Animal>` chỉ vì `Cat extends Animal`. Quy tắc bất biến của generic và wildcard `extends`/`super` là một vấn đề khác với ràng buộc đệ quy.

### Giới hạn giao nhau

Java có thể kết hợp F-bound với interface bổ sung:

```java
static <T extends Comparable<T> & java.io.Serializable>
T preferred(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Đây là **đoạn minh họa phương thức**, cần đặt trong một class để chạy. Một type parameter có thể có nhiều giới hạn giao nhau, nhưng tối đa một class bound và class bound (nếu có) phải đứng đầu. Các giới hạn khác thường là interface.

## 9. Quy tắc thiết kế API và lỗi thường gặp

**1. Bắt đầu từ hành vi cần bảo toàn.** F-bound hợp lý khi có lợi ích thực sự, như `copy()` trả về kiểu cụ thể, builder kế thừa API fluent mà không mất phương thức con, hoặc thuật toán cần `compareTo` có quan hệ kiểu rõ ràng. Đừng thêm tự tham chiếu chỉ để làm chữ ký "mạnh hơn" khi không có hợp đồng cần thiết.

**2. Chọn bound phù hợp cho so sánh.** Với tiện ích nhận những kiểu kế thừa triển khai `Comparable` của lớp cha, thường nên cân nhắc `Comparable<? super T>` thay cho `Comparable<T>`. Phần wildcard không làm lỏng yêu cầu về loại đối số mà `compareTo` được nhận; nó cho phép loại đối số đó là một supertype của `T`.

**3. Tránh liên kết sai tham số kiểu.** `class Wrong extends Base<Right>` có thể hợp lệ về Java dù phá quy ước "kiểu tự thân". Với cây kế thừa do bạn kiểm soát, đánh dấu lớp cuối là `final` khi không cần mở rộng và review phần `extends Base<...>` của từng lớp con.

**4. Phân biệt kiểu tĩnh và đối tượng runtime.** Kiểu trả về `S` nói rằng kết quả phù hợp hợp đồng kiểu `S`; không tự nói rằng kết quả là `this`, không nói kết quả được tạo mới và không chứng minh mọi subclass liên kết đúng.

**5. Hạn chế raw types và cast unchecked.** Raw `Base` bỏ qua tham số kiểu; cast `(S) this` chỉ dựa vào lời hứa của người viết nếu compiler không thể kiểm chứng. Một cảnh báo unchecked là tín hiệu cần chứng minh bất biến, không phải bằng chứng tự động rằng mã sai hoặc đúng.

**6. Giữ độ phức tạp tương xứng.** Trong hệ thống có nhiều tầng kế thừa, các chữ ký dạng `Child<C extends Child<C, ...>>` dễ khó đọc và làm thông báo lỗi kiểu phức tạp. Có thể ưu tiên composition, builder riêng cho từng loại, interface tách chức năng hoặc covariant return type khi chúng đáp ứng yêu cầu đơn giản hơn.

**7. Không nhầm giới hạn generic với đệ quy thuật toán.** F-bound là ràng buộc định nghĩa kiểu, không phải lời gọi hàm đệ quy. Không có quy tắc nào bắt buộc phải có phương thức tự gọi hoặc dữ liệu dạng cây để sử dụng nó.

## 10. Cách tự kiểm tra một thiết kế F-bound

Khi gặp một khai báo mới, hãy tự trả lời theo thứ tự:

1. **Biến kiểu là gì?** Trong `<S extends Base<S>>`, đó là `S`.
2. **Điều kiện hợp lệ là gì?** Ứng viên `X` phải là subtype của `Base<X>`.
3. **Ai truyền kiểu vào?** Lớp con, ví dụ `Concrete extends Base<Concrete>`, hoặc lời gọi phương thức generic.
4. **Lợi ích compile time là gì?** Phương thức nhận/trả về `S` vẫn giữ chính kiểu tĩnh cụ thể ấy.
5. **Có lỗ hổng tự đồng nhất không?** Kiểm tra tình huống một lớp khác dùng `Base<Concrete>`; cần bảo vệ quy ước nếu tính đồng nhất là thiết yếu.
6. **Có thể làm đơn giản hơn không?** Nếu không cần kế thừa fluent hoặc self typing, một interface thường hoặc overload rõ ràng có thể đủ.

### Bài tập thực hành

**Bài 1 — Dự đoán kiểu:** Với `class CarBuilder extends BaseBuilder<CarBuilder>`, phương thức `name(...)` khai báo trả `B` thì khi gọi trên `CarBuilder`, kiểu tĩnh của kết quả là gì? Vì sao phương thức riêng của `CarBuilder` có thể được gọi tiếp? **Gợi ý đối chiếu:** `B` được thay bằng `CarBuilder`.

**Bài 2 — Đánh giá giới hạn:** Giải thích vì sao `Student extends Person` và `Person implements Comparable<Person>` có thể thỏa mãn giới hạn `Comparable<? super Student>` nhưng không tự động thỏa `Comparable<Student>`. **Gợi ý đối chiếu:** generic là invariant; `Person` là supertype của `Student`.

**Bài 3 — Tìm sai lầm:** Một lập trình viên viết `class A extends Base<B>` với `B extends Base<B>` và khẳng định trình biên dịch Java sẽ luôn từ chối vì `A` khác `B`. Khẳng định này đúng hay sai? **Đáp án:** sai. F-bound kiểm tra điều kiện trên tham số `B`, không kiểm tra tên lớp đang kế thừa có trùng `B` hay không.

**Bài 4 — Chọn phương án:** Tạo API `withName` cho một builder chỉ có một lớp, không bao giờ kế thừa. Bạn có cần `<B extends Builder<B>>`? **Gợi ý:** thường không; trả về chính `Builder` là đủ.

## 11. Ghi nhớ

F-bounded polymorphism dùng tham số kiểu ngay trong giới hạn của nó, tiêu biểu là `<S extends Base<S>>`. Kỹ thuật này giúp Java biểu diễn quan hệ giữa một kiểu cụ thể và các thao tác dùng/trả lại chính kiểu cụ thể ấy. Nó đặc biệt có ích trong thuật toán dựa trên `Comparable`, hệ thống enum của JDK và các fluent API có phân cấp kế thừa.

Sức mạnh của F-bound nằm ở **an toàn kiểu tại thời điểm biên dịch**; giới hạn quan trọng là nó không thể ép `S` phải đúng bằng lớp con hiện tại, không thay thế việc thiết kế hợp đồng `self()` và không loại bỏ cơ chế type erasure. Dùng nó khi quan hệ kiểu này tạo ra một lợi ích API rõ ràng, đồng thời kiểm tra các lớp con có tuân thủ quy ước đã chọn hay không.