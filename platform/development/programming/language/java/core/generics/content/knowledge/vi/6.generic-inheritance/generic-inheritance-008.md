# Generic với lớp abstract, lớp final và hệ phân cấp sealed trong Java

Trong Java, **generic** mô tả các quan hệ kiểu bằng tham số như `T`, `E`, `K` hoặc `V`. Còn **`abstract`**, **`final`** và **`sealed`** điều khiển cách một lớp được khởi tạo hoặc được kế thừa. Chúng giải quyết những vấn đề khác nhau nên có thể phối hợp trong một hệ phân cấp.

Ví dụ `abstract class Repository<T>` cho phép định nghĩa hợp đồng dùng chung nhưng không cho tạo trực tiếp repository trừu tượng; `final class MemoryRepository<T> extends Repository<T>` hoàn thiện hợp đồng và không cho kế thừa tiếp; `sealed abstract class Result<T> permits Success, Failure` hạn chế tập các **lớp con trực tiếp** được phép kế thừa.

**Ý chính:** `abstract`, `final`, `sealed` không làm mất tính generic. Thông tin kiểu vẫn được kiểm tra lúc biên dịch, còn quy tắc kế thừa vẫn tuân theo Java.

## 1. Ba cơ chế: abstract, final, sealed giải quyết việc gì?

| Cơ chế | Có thể khai báo generic? | Có thể `new` trực tiếp? | Kế thừa tiếp có được không? |
|---|---|---|---|
| `abstract class Base<T>` | Có | Không | Có, nếu không bị quy tắc khác hạn chế |
| `final class Value<T>` | Có | Có, nếu constructor truy cập được | Không; mọi kiểu con trực tiếp bị cấm |
| `sealed class Base<T> permits A, B` | Có | Có, nếu không đồng thời `abstract` và constructor hợp lệ | Chỉ những lớp con trực tiếp được cho phép |
| `abstract sealed class Base<T> permits A, B` | Có | Không | Chỉ những lớp con trực tiếp được cho phép |
| `non-sealed class A<T> extends Base<T>` | Có | Có nếu không `abstract` | Mở lại kế thừa cho các lớp con tiếp theo |

`non-sealed` chỉ có ý nghĩa khi một lớp hoặc interface đang **kế thừa trực tiếp một lớp/interface sealed** (ở vị trí được phép trong hệ phân cấp). Nó không phải modifier dùng tùy ý cho một class không có supertype sealed trực tiếp.

Một **direct permitted subclass** của sealed class phải nêu rõ một trong ba hướng tiếp tục hệ phân cấp: `final`, `sealed` hoặc `non-sealed`. `abstract` có thể kết hợp với `sealed` hoặc `non-sealed`; `abstract` không thể kết hợp với `final`. Lớp `final` đóng hẳn nhánh đó. Lớp `sealed` giới hạn tiếp nhánh sau. Lớp `non-sealed` mở nhánh đó cho các lớp con không được liệt kê trong danh sách `permits` của ông bà.

Từ **Java 17**, sealed classes và sealed interfaces là tính năng chính thức, không cần bật preview. Riêng một số dạng *pattern matching for switch* trong Java 17 vẫn thuộc preview; không nhầm hai tính năng này.

## 2. Generic abstract class: hợp đồng kiểu nhưng không có đối tượng trừu tượng

Lớp `abstract` thường dùng khi ta muốn chia sẻ trạng thái và hành vi chung, đồng thời yêu cầu lớp con cài đặt những thao tác còn thiếu:

```java
abstract class AbstractStore<T> {
    private final T initial;

    protected AbstractStore(T initial) {
        this.initial = initial;
    }

    public T initial() {
        return initial;
    }

    public abstract String describe(T value);
}
```

Đây là **định nghĩa lớp minh họa**, chưa có `main`. Các điểm quan trọng:

- `<T>` thuộc **lớp**. Trường `initial`, constructor, phương thức `initial()` và `describe(T)` cùng nói về kiểu `T` của mỗi cách tham số hóa.
- Không thể viết `new AbstractStore<String>("x")` để tạo trực tiếp đối tượng của một abstract class.
- Constructor của abstract class **vẫn được chạy** khi lớp con gọi `super(...)`. `abstract` không đồng nghĩa với “không có constructor”.
- Phương thức `abstract String describe(T value)` chỉ có chữ ký, không có thân; lớp con cụ thể phải cài đặt phương thức này hoặc được kế thừa một cài đặt hợp lệ.
- Một abstract class generic có thể chứa cả phương thức abstract lẫn concrete và trạng thái chung.

Một lớp con cố định `T`:

```java
final class StringStore extends AbstractStore<String> {
    StringStore(String initial) {
        super(initial);
    }

    @Override
    public String describe(String value) {
        return "text=" + value;
    }
}
```

Lúc này compiler biết `T = String`, nên chữ ký abstract `describe(T)` trở thành `describe(String)` theo quan hệ kiểu nguồn. `StringStore` không generic nhưng kế thừa một **generic superclass được tham số hóa**.

Một lớp con khác vẫn giữ type parameter:

```java
final class SimpleStore<E> extends AbstractStore<E> {
    SimpleStore(E initial) {
        super(initial);
    }

    @Override
    public String describe(E value) {
        return "item=" + value;
    }
}
```

`SimpleStore<Integer>` là subtype của `AbstractStore<Integer>`. Chữ `E` không bắt buộc trùng `T`: quan hệ nằm ở `extends AbstractStore<E>`. Cả `StringStore` và `SimpleStore<E>` là **hai thiết kế minh họa có thể đặt cùng nhau trong package phù hợp**; chúng không phải hai nhánh của một sealed hierarchy.

## 3. Generic final class: khóa kế thừa, không khóa tham số kiểu

Một `final class` không thể là superclass của một class khác, nhưng **vẫn có thể generic**:

```java
final class ResultBox<T> {
    private final T value;

    ResultBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Có thể dùng `ResultBox<String>`, `ResultBox<Integer>` hoặc `ResultBox<List<String>>`. Modifier `final` **không giới hạn loại type arguments**. Nó chỉ cấm người khác khai báo `class SpecialBox extends ResultBox<String>`.

Cần phân biệt ba ý nghĩa khác nhau của chữ `final`:

1. **`final class`**: cấm kế thừa lớp.
2. **`final` trên method**: không cho override method đó trong subclass hợp lệ.
3. **`final` trên field**: ngăn gán lại field sau khi nó được khởi tạo phù hợp; **không bảo đảm đối tượng mà field trỏ tới bất biến sâu**.

Ví dụ, `final class Data<T>` có trường `private final List<T> items` vẫn có thể lộ một `ArrayList<T>` mutable ra ngoài; người gọi có thể sửa các phần tử thông qua tham chiếu list. Nếu mục tiêu là value object bất biến, phải thiết kế dữ liệu và API phù hợp bên cạnh modifier `final`.

Trong thiết kế generic, `final class` đặc biệt thích hợp với lớp giá trị, helper cụ thể, hoặc một nhánh **kết thúc** của hệ phân cấp sealed. Nó không đồng nghĩa với “lớp chưa được phép đa hình”: đối tượng của một lớp final vẫn có thể được nhìn qua **superclass** hoặc **interface** mà nó triển khai.

## 4. Generic sealed class/interface: giới hạn tập lớp con trực tiếp

Một sealed generic class có thể nêu những lớp được quyền kế thừa trực tiếp:

```java
abstract sealed class Result<T> permits Success, Failure {
    public abstract T orElse(T fallback);
}

final class Success<T> extends Result<T> {
    private final T value;

    Success(T value) {
        this.value = value;
    }

    @Override
    public T orElse(T fallback) {
        return value;
    }
}

final class Failure<T> extends Result<T> {
    @Override
    public T orElse(T fallback) {
        return fallback;
    }
}
```

Đây là **ba khai báo lớp minh họa**, không phải chương trình chạy độc lập. `Success<T>` và `Failure<T>` là hai subclass **trực tiếp** của `Result<T>` và đều `final`, vì vậy nhánh này không cho kế thừa thêm qua hai loại đó.

**Quy tắc cốt lõi của `sealed`:**

- Lớp cha dùng `sealed` và thường ghi `permits` để liệt kê direct subclasses.
- Mỗi direct subclass được phép phải có quan hệ **`extends`** đúng với superclass sealed (hoặc **`implements`** đối với sealed interface).
- Direct subclass phải được khai báo rõ là `final`, `sealed`, hoặc `non-sealed`.
- Với **named module**, những subclass được phép nằm trong **cùng module** với sealed parent. Trong **unnamed module**, chúng phải nằm trong **cùng package**. Điều kiện này không nói rằng toàn bộ codebase phải chỉ có một package.
- Danh sách `permits` chứa **tên các lớp/interface được cho phép**, không chứa cách tham số hóa như `Success<String>`. Chẳng hạn `permits Success, Failure`, không phải `permits Success<T>, Failure<T>`.
- Trong trường hợp tất cả các direct subclasses cùng nằm trong **cùng compilation unit**, compiler có thể suy ra tập permitted subclasses khi bỏ `permits`; ghi rõ `permits` thường dễ đọc hơn trong tài liệu.
- `sealed` hạn chế **cấu trúc kế thừa trực tiếp**, không tự hạn chế tập **type arguments** mà một generic class có thể nhận.

Giữa `Result<String>` và `Result<Integer>`, Java vẫn áp dụng kiểm tra kiểu generic như bình thường. `sealed` không làm hai cách tham số hóa trở thành subtype của nhau.

### `sealed interface` cũng có thể generic

```java
sealed interface Response<T> permits Ok, Error {
    T orElse(T fallback);
}

record Ok<T>(T value) implements Response<T> {
    @Override
    public T orElse(T fallback) {
        return value;
    }
}

record Error<T>(String message) implements Response<T> {
    @Override
    public T orElse(T fallback) {
        return fallback;
    }
}
```

Đây là **một hệ phân cấp minh họa riêng** cho Java 17. Các `record` là `final` ngầm định, nên có thể là direct implementors của sealed interface. `Ok<String>` và `Error<String>` đều là `Response<String>`, nhưng `Error<Integer>` là `Response<Integer>`. Record không thể `extends` class khác vì nó đã kế thừa `java.lang.Record`, nhưng có thể `implements` generic sealed interface.

Hai nhánh `Ok<T>` và `Error<T>` nên tồn tại cùng package/module với `Response<T>` theo quy tắc sealed; ví dụ được viết cùng compilation unit để dễ đọc. Đây là ví dụ thiết kế **tổng kiểu (sum type) theo các trường hợp thành công/thất bại**, không phải ngoại lệ runtime bắt buộc.

## 5. Ba đường đi của một nhánh sealed: `final`, `sealed`, `non-sealed`

Một direct subclass của sealed class phải chọn một trong ba hướng:

```java
sealed abstract class Node<T> permits Leaf, Branch, OpenNode {
    protected final T value;

    Node(T value) {
        this.value = value;
    }
}

final class Leaf extends Node<String> {
    Leaf(String value) {
        super(value);
    }
}

sealed class Branch<T> extends Node<T> permits FinalBranch {
    Branch(T value) {
        super(value);
    }
}

final class FinalBranch extends Branch<Integer> {
    FinalBranch(Integer value) {
        super(value);
    }
}

non-sealed class OpenNode<T> extends Node<T> {
    OpenNode(T value) {
        super(value);
    }
}

final class CustomOpenNode extends OpenNode<Long> {
    CustomOpenNode(Long value) {
        super(value);
    }
}
```

Đây là **một sơ đồ lớp minh họa bằng Java 17**. Quan hệ của các nhánh:

- `Leaf` là `final`: kết thúc nhánh `Node<String>`.
- `Branch<T>` là `sealed`: nó mở một tầng phân loại nhưng chỉ cho phép `FinalBranch` trực tiếp kế thừa; `FinalBranch` dùng `T = Integer`.
- `OpenNode<T>` là `non-sealed`: từ đây các subtype không nhất thiết phải được `Node<T>` liệt kê trong `permits`. `CustomOpenNode` hợp lệ khi `extends OpenNode<Long>`.
- `final class CustomOpenNode` **không phải** direct subclass của `Node`, nên không cần nằm trong `permits Leaf, Branch, OpenNode` của `Node`.
- `sealed` và `non-sealed` không thay đổi quan hệ generic: `OpenNode<Long>` là subtype của `Node<Long>`, không mặc nhiên là subtype của `Node<Object>`.

Tính đóng của hệ phân cấp cần được hiểu chính xác: nếu có một nhánh `non-sealed`, **tập toàn bộ subclass gián tiếp không còn đóng**. `permits` chỉ đóng tập subclass **trực tiếp** của đúng sealed parent. Do đó khi thiết kế một API cần biết đầy đủ mọi subtype để xử lý theo từng nhánh, phải cân nhắc tác động của `non-sealed`.

## 6. Ví dụ Java 17 hoàn chỉnh: generic, abstract, final và sealed phối hợp

Chương trình dưới đây minh họa một hệ phân cấp generic duy nhất. Root `Item<T>` vừa `abstract` vừa `sealed`. Nó có ba direct permitted subclasses: `TextItem` kết thúc nhánh, `NumberItem<N>` mở lại nhánh, và `FlagItem` tiếp tục là sealed cho hai loại cờ.

Lưu toàn bộ mã thành **`SealedGenericHierarchyDemo.java`**:

```java
import java.util.List;

public class SealedGenericHierarchyDemo {

    static abstract sealed class Item<T>
            permits TextItem, NumberItem, FlagItem {

        private final T value;

        protected Item(T value) {
            this.value = value;
        }

        public final T value() {
            return value;
        }

        public abstract String kind();

        public String describe() {
            return kind() + ":" + value;
        }
    }

    static final class TextItem extends Item<String> {
        TextItem(String text) {
            super(text);
        }

        @Override
        public String kind() {
            return "text";
        }

        int length() {
            return value().length();
        }
    }

    static non-sealed class NumberItem<N extends Number>
            extends Item<N> {
        NumberItem(N number) {
            super(number);
        }

        @Override
        public String kind() {
            return "number";
        }

        double doubled() {
            return value().doubleValue() * 2;
        }
    }

    static final class IntegerItem extends NumberItem<Integer> {
        IntegerItem(Integer number) {
            super(number);
        }

        @Override
        public String kind() {
            return "integer";
        }
    }

    static abstract sealed class FlagItem
            extends Item<Boolean> permits OnFlag, OffFlag {

        protected FlagItem(Boolean value) {
            super(value);
        }

        @Override
        public String kind() {
            return "flag";
        }
    }

    static final class OnFlag extends FlagItem {
        OnFlag() {
            super(true);
        }
    }

    static final class OffFlag extends FlagItem {
        OffFlag() {
            super(false);
        }
    }

    static <T> T unwrap(Item<T> item) {
        return item.value();
    }

    static void printAll(List<? extends Item<?>> items) {
        for (Item<?> item : items) {
            System.out.println("item: " + item.describe());
        }
    }

    public static void main(String[] args) {
        TextItem text = new TextItem("Java");
        IntegerItem concreteNumber = new IntegerItem(21);
        Item<String> textView = text;
        Item<Integer> numberView = concreteNumber;
        Item<Boolean> flagView = new OnFlag();

        System.out.println("text value: " + unwrap(textView));
        System.out.println("text length: " + text.length());
        System.out.println("twice: " + concreteNumber.doubled());
        System.out.println("flag value: " + unwrap(flagView));
        System.out.println("dispatch: " + numberView.describe());

        NumberItem<Double> fractional = new NumberItem<>(2.5);
        System.out.println("open branch: " + fractional.describe());
        System.out.println("off branch: " + new OffFlag().describe());

        List<Item<?>> items = List.of(
                textView, numberView, flagView);
        printAll(items);
    }
}
```

Chạy với **JDK 17 hoặc mới hơn** trong thư mục chứa tệp:

```bash
javac SealedGenericHierarchyDemo.java
java SealedGenericHierarchyDemo
```

**Stdout mong đợi:**

```text
text value: Java
text length: 4
twice: 42.0
flag value: true
dispatch: integer:21
open branch: number:2.5
off branch: flag:false
item: text:Java
item: integer:21
item: flag:true
```

### Giải thích từng mối quan hệ

**Root generic abstract sealed:** `Item<T>` khai báo `T` cho toàn bộ lớp. Nó có constructor `protected Item(T value)`, method trả `T`, abstract method `kind()` và concrete method `describe()`. Không thể `new Item<String>("x")` vì lớp là abstract. Một class bên ngoài danh sách `permits` không thể trực tiếp `extends Item<...>`.

**Nhánh final cố định kiểu:** `TextItem extends Item<String>`. Method `value()` kế thừa trả `String`, nên `text.length()` có thể gọi `value().length()` mà không cast. Modifier `final` cấm bất kỳ class nào tiếp tục `extends TextItem`.

**Nhánh non-sealed vẫn generic:** `NumberItem<N extends Number> extends Item<N>` giữ tham số kiểu `N` và đặt bound `Number`. Vì `non-sealed`, `IntegerItem extends NumberItem<Integer>` được phép mà không xuất hiện trong `permits` của `Item<T>`. Đây là **subclass gián tiếp** của root, đi qua direct subclass `NumberItem`.

**Nhánh sealed cấp hai:** `FlagItem extends Item<Boolean> permits OnFlag, OffFlag` cố định `T = Boolean` và giới hạn trực tiếp các lớp con thành `OnFlag`, `OffFlag`. `FlagItem` vẫn abstract; cả hai lớp con là final và kế thừa `kind()` đã được `FlagItem` cài đặt.

**Generic method đọc kiểu cha:** `<T> T unwrap(Item<T> item)` có tham số kiểu riêng của method. Nó nhận `Item<String>` hoặc `Item<Boolean>` mà không mất kiểu trả về. Khi gọi `unwrap(textView)`, kết quả có kiểu `String`; khi gọi `unwrap(flagView)`, có kiểu `Boolean`. Type parameter method này không được khai báo bởi `Item`.

**Đa hình và dispatch:** biến `numberView` có kiểu tĩnh `Item<Integer>`, nhưng trỏ tới `IntegerItem`. Lời gọi `numberView.describe()` thực thi phương thức `describe()` kế thừa của `Item`; bên trong, lời gọi `kind()` là một virtual call đến bản override `IntegerItem.kind()`, nên kết quả `integer:21`. Generic type và dynamic dispatch bổ sung cho nhau, không phải là cùng một cơ chế.

**Danh sách kiểu hỗn hợp:** `List<Item<?>>` có thể chứa nhiều `Item<T>` có các `T` khác nhau. `printAll(List<? extends Item<?>>)` chỉ đọc và in mỗi item, không giả định tất cả có chung kiểu giá trị cụ thể. Ngược lại, `List<Item<String>>` không được gán trực tiếp từ `List<TextItem>` vì tính bất biến (*invariance*) của generic collection.

## 7. Quan hệ giữa sealed hierarchy và tham số kiểu

Tập subtype được quản lý bằng **tên lớp**, còn đối số kiểu được quản lý bằng **hợp đồng generics**. Ví dụ:

```java
// Root:
abstract sealed class Event<T> permits TextEvent, GenericEvent { }

// Nhánh cố định:
final class TextEvent extends Event<String> { }

// Nhánh giữ tham số:
final class GenericEvent<U> extends Event<U> { }
```

Ba khai báo này là **ví dụ độc lập** với chương trình `Item<T>` ở trên. `TextEvent` là subtype của `Event<String>`; `GenericEvent<Integer>` là subtype của `Event<Integer>`. Tên `U` khác tên `T` của cha nhưng việc ánh xạ `extends Event<U>` mới quyết định quan hệ kiểu.

Không được viết:

```java
// sealed class Event<T> permits TextEvent<String> { }
// Sai: permits cần tên class, không phải một parameterized type.
```

Tương tự, sealed parent không thể “cho phép `Event<String>` nhưng cấm `Event<Integer>`” chỉ bằng việc liệt kê type arguments trong `permits`. Nếu miền dữ liệu cần các nhánh cố định kiểu, thiết kế subclass cụ thể như `TextEvent extends Event<String>`; nếu cần hạn chế kiểu theo bound, dùng generic bounds; nếu cần điều kiện dữ liệu runtime, kiểm tra trong constructor/factory.

Java vẫn giữ tính **invariant**: dù `String` là subtype của `Object`, `Event<String>` không tự là subtype của `Event<Object>`. Có thể dùng `Event<?>` khi chỉ cần quan sát một event bất kỳ hoặc `Event<? extends CharSequence>` khi cần đọc giá trị đáp ứng một hợp đồng rộng hơn.

## 8. Sealed và pattern matching: khả năng xử lý theo tập nhánh

Khi hệ phân cấp được đóng, compiler có nhiều thông tin hơn về các subclass khả dĩ. Điều này có ích cho pattern matching, phân tích nhánh và công cụ bảo trì API.

Ví dụ một nhánh `Result<T>` chỉ có `Success` và `Failure`: người đọc có thể thiết kế xử lý cho hai trường hợp đó. Tuy nhiên phải phân biệt:

- **Java 17:** sealed classes/interfaces là tính năng chính thức. Pattern matching cho `instanceof` đã có thể dùng theo Java 17. Nhưng **pattern matching for `switch`** trong Java 17 thuộc preview, vì vậy đừng mặc nhiên sao chép một mẫu `switch` dựa trên sealed patterns rồi kỳ vọng `javac File.java` chạy không cần cờ preview.
- **Java 21 trở lên:** pattern matching for `switch` được chuẩn hóa; một số dạng xử lý sealed hierarchy có thể kiểm tra tính bao phủ các trường hợp ngay khi biên dịch, tùy kiểu selector và pattern. Cú pháp/điều kiện cụ thể phải theo phiên bản JDK đang dùng.
- **Có `non-sealed`:** dù root liệt kê một direct subclass `non-sealed`, phía dưới nhánh đó có thể còn các subtype không xác định trước; không suy diễn tập toàn bộ concrete class là hữu hạn chỉ từ `permits`.

Trong Java 17, một cách đọc nhánh không cần tính năng preview là `instanceof` pattern với các kiểu **reifiable**:

```java
static String category(Object obj) {
    if (obj instanceof SealedGenericHierarchyDemo.TextItem) {
        return "text";
    }
    if (obj instanceof SealedGenericHierarchyDemo.NumberItem<?>) {
        return "numeric";
    }
    if (obj instanceof SealedGenericHierarchyDemo.FlagItem) {
        return "flag";
    }
    return "other";
}
```

Đây là **method minh họa** có thể đặt trong một class truy cập được các nested types của `SealedGenericHierarchyDemo` (ví dụ chính bên trong lớp đó). `NumberItem<?>` có wildcard không hạn chế, nên kiểm tra `instanceof` kiểu đó hợp lệ. Không dùng `obj instanceof NumberItem<Integer>` để kiểm tra type argument cụ thể; dạng đó không reifiable theo Java erasure.

## 9. Abstract + sealed, final + generic và non-sealed có thể phối hợp

Đừng coi ba modifier này là những lựa chọn bắt buộc loại trừ nhau trong toàn bộ hệ phân cấp:

- **Root `abstract sealed`**: không thể khởi tạo trực tiếp và giới hạn các subclass trực tiếp.
- **Nhánh `final`**: là kiểu cụ thể hoàn thiện hợp đồng rồi dừng kế thừa.
- **Nhánh `sealed`**: tiếp tục khống chế các nhánh con của chính nó; có thể đồng thời `abstract`.
- **Nhánh `non-sealed`**: mở tiếp khả năng tạo subtype. Có thể là concrete hoặc abstract; việc mở lại có ý nghĩa theo quy tắc direct sealed supertype.
- **Generic ở từng cấp**: root `Base<T>`, nhánh `Branch<U> extends Base<U>`, nhánh `Fixed extends Base<String>`, hay nhánh thêm kiểu `Tagged<T, M> extends Base<T>` đều được compiler kiểm tra độc lập với sealed modifier.

Một lớp **không thể vừa `final` vừa `abstract`** vì abstract yêu cầu class có thể được subclass để triển khai, còn final cấm subclass. Một lớp cũng không được kết hợp `final` với `sealed` hoặc `non-sealed` như thể chúng mô tả ba cách kế thừa đồng thời; direct permitted subclass phải chọn một chế độ hợp lệ.

Constructor `protected` của sealed abstract class cho phép subclass được quyền khởi tạo phần cha bằng `super(...)`, nhưng không mở quyền `extends` cho một class bị loại khỏi `permits`. Access modifier và sealed restriction là hai tầng kiểm tra khác nhau.

## 10. Lỗi thường gặp và cách khắc phục

**Lỗi 1 — Nghĩ `final` cấm generics.** `final class Box<T>` hợp lệ. `final` cấm kế thừa lớp, không cấm truyền `Box<String>`, `Box<Integer>`.

**Lỗi 2 — `new` trực tiếp abstract generic class.** `new AbstractStore<String>(...)` không hợp lệ; tạo một subclass concrete đáp ứng constructor và triển khai các abstract method, hoặc cung cấp factory trả về subclass phù hợp.

**Lỗi 3 — Quên cài đặt abstract generic method.** Nếu cha có `abstract T read()`, lớp con concrete cần triển khai method với return type đáp ứng quan hệ kiểu sau thay thế type arguments; chỉ khai báo `class Child extends Parent<String>` không tự cài đặt method.

**Lỗi 4 — Dùng `permits` với đối số kiểu.** `permits Good<String>` sai. Danh sách `permits` liệt kê các **kiểu con được khai báo**, chẳng hạn `permits Good, Bad`.

**Lỗi 5 — Direct permitted subclass không chọn `final`, `sealed`, `non-sealed`.** Với một class kế thừa trực tiếp sealed parent, chỉ `class Good extends Parent` là chưa đủ; phải chỉ rõ modifier phù hợp như `final class Good...`, `sealed class Good...` hoặc `non-sealed class Good...`.

**Lỗi 6 — Cho rằng một lớp ở nơi bất kỳ cũng được dùng `non-sealed`.** `non-sealed` có quy tắc ngữ cảnh riêng và cần direct sealed supertype. Không thêm nó vào một class bình thường chỉ để nói rằng class ấy “mở rộng được”.

**Lỗi 7 — Đặt direct permitted subclass sai module/package.** Với named module, chúng cần cùng module; với unnamed module, cần cùng package. Chỉ khai báo `permits` không vô hiệu hóa điều kiện vị trí hoặc kiểm tra truy cập.

**Lỗi 8 — Nghĩ mọi lớp con gián tiếp phải nằm trong `permits` của root.** Nếu root cho phép `non-sealed NumberItem`, lớp `IntegerItem extends NumberItem<Integer>` không phải direct subclass của root và không cần có tên ở root permits.

**Lỗi 9 — Tưởng `sealed` đóng mọi lớp con sau nhánh `non-sealed`.** Một khi một nhánh hợp lệ được đánh dấu `non-sealed`, nó có thể mở rộng về sau; thiết kế phân loại phải cân nhắc khả năng này.

**Lỗi 10 — Nhầm quan hệ kế thừa class với covariance của generic type.** `TextItem extends Item<String>` không kéo theo `Item<String> extends Item<Object>`. Dùng wildcard như `Item<?>` hoặc `Item<? extends CharSequence>` khi muốn nhận nhiều tham số hóa.

**Lỗi 11 — Gọi method của subclass thông qua biến kiểu superclass.** `Item<String> item = new TextItem("x");` không cho gọi trực tiếp `item.length()` nếu `Item<T>` không khai báo `length()`. Static type quyết định method có thể gọi; runtime dispatch chỉ quyết định triển khai override của method đã có.

**Lỗi 12 — Tưởng type arguments được giữ nguyên ở runtime vì sealed.** Sealed kiểm soát quan hệ kế thừa; Java generics thông thường vẫn bị erasure. Không kiểm tra `instanceof Item<String>`, mà dùng `Item<?>` ở vị trí thích hợp hoặc truyền runtime type token nếu bài toán cần.

**Lỗi 13 — Phụ thuộc vào preview switch của Java 17.** Nếu bạn dùng pattern switch từ tài liệu phiên bản mới, xác nhận JDK và cờ preview trước khi chạy; ví dụ đầy đủ trong bài tránh yêu cầu preview.

**Lỗi 14 — Dùng `final` như cam kết bất biến sâu.** Generic class final với field final có thể vẫn giữ một object mutable. Muốn value object an toàn, cân nhắc defensive copy, API đọc và xác định rõ trạng thái có được thay đổi hay không.

**Lỗi 15 — Mở quá nhiều nhánh `non-sealed` dù muốn dữ liệu dạng tổng kiểu hữu hạn.** Nếu yêu cầu xử lý đầy đủ một tập trạng thái đóng, nên dùng các nhánh final/sealed thật sự; chỉ dùng non-sealed khi có lý do cần extension point cho người khác.

## 11. Khi nào nên chọn kiểu thiết kế nào?

| Tình huống | Thiết kế gợi ý | Lý do |
|---|---|---|
| Chia sẻ trạng thái và yêu cầu subclass triển khai thao tác | `abstract class Base<T>` | Có constructor, trường, method chung và abstract method |
| Đối tượng generic dùng làm giá trị, không có chủ đích mở rộng qua inheritance | `final class Value<T>` hoặc `record Value<T>(T x)` | Giảm bề mặt mở rộng; record tự cung cấp các thành phần theo ngữ nghĩa record |
| Chỉ có tập direct variants được phép | `sealed interface Result<T> permits ...` | Định hình rõ hệ phân cấp các trường hợp |
| Cần root abstract và một số nhánh concrete, một số nhánh cần phân loại tiếp | `abstract sealed class Node<T> permits ...` | Kết hợp hợp đồng, trạng thái và giới hạn nhánh |
| Muốn một nhánh được bên thứ ba mở rộng | Direct subclass `non-sealed` | Mở lại kế thừa tại nhánh đó |
| Cần bổ sung dữ liệu nhưng không có quan hệ “is-a” thực sự | Composition như `record Tagged<T, M>(T data, M metadata)` | Tránh ràng buộc kế thừa không cần thiết |

Chọn `sealed` khi sự đóng/mở của hệ phân cấp là **hợp đồng có chủ đích**, không chỉ vì muốn hạn chế số lượng class. Nếu code bên ngoài module/package cần tự bổ sung variant, một hệ phân cấp sealed đóng hoàn toàn có thể không phù hợp. Còn nếu cần mô hình hóa những trạng thái xác định như thành công/thất bại hoặc loại node cố định, sealed giúp hợp đồng dễ đọc và dễ kiểm soát hơn.

Không dùng `sealed` để thay cho kiểm tra dữ liệu runtime: `sealed` không đảm bảo một `Result<String>` có chuỗi hợp lệ, không chống `null`, cũng không tự làm đối tượng thread-safe.

## 12. Bài tập tự kiểm tra có đáp án

**1.** `abstract class Store<T>` có thể có constructor và method concrete không?  
**Đáp án:** Có. `abstract` ngăn tạo trực tiếp class và cho phép abstract method, nhưng constructor và concrete method hoàn toàn hợp lệ.

**2.** `final class Box<T>` có nhận `String` và `Integer` làm type arguments không?  
**Đáp án:** Có, `final` không cấm tham số hóa `T`.

**3.** `sealed abstract class Result<T> permits Ok, Error` có cho `class Other extends Result<String>` ở cùng package không?  
**Đáp án:** Không, nếu `Other` không được đưa vào tập direct permitted subclasses. Ở cùng package chỉ thỏa một điều kiện vị trí, không thay cho `permits`.

**4.** Một direct permitted subclass phải dùng modifier nào?  
**Đáp án:** Một trong `final`, `sealed` hoặc `non-sealed` phù hợp với cách tiếp tục hệ phân cấp.

**5.** `non-sealed class NumberItem<N extends Number> extends Item<N>` có thể có `final class IntegerItem extends NumberItem<Integer>` không?  
**Đáp án:** Có. `IntegerItem` là subclass của nhánh non-sealed, không cần xuất hiện trong root `Item` permits.

**6.** Từ `TextItem extends Item<String>`, biến `Item<Object> o = new TextItem("x");` có hợp lệ không?  
**Đáp án:** Không. `TextItem` là subtype của `Item<String>`, không phải `Item<Object>` do generics invariant.

**7.** Có thể viết `permits Ok<String>, Error<Integer>` để đóng generic hierarchy theo type arguments không?  
**Đáp án:** Không. `permits` liệt kê direct subclasses theo tên khai báo, không nhận parameterized types.

**8.** Tại sao `Item<Boolean> b = new OnFlag()` hợp lệ?  
**Đáp án:** `OnFlag extends FlagItem` và `FlagItem extends Item<Boolean>`; quan hệ transitive inheritance giữ đúng type argument `Boolean`.

**9.** `final` trên class có đồng nghĩa field kiểu `List<T>` bên trong không thể sửa được không?  
**Đáp án:** Không. `final class` cấm subclass, không tự làm phần tử và object bên trong immutable.

**10.** Với Java 17, sealed class có cần `--enable-preview` không?  
**Đáp án:** Không. Sealed classes/interfaces đã chính thức; một số syntax pattern switch ở Java 17 mới là preview.

**11.** Generic method `<T> T unwrap(Item<T> x)` có dùng được với nhiều nhánh của sealed hierarchy không?  
**Đáp án:** Có, miễn mỗi nhánh có supertype `Item<T>` thích hợp; `T` được suy luận hoặc chỉ định theo lời gọi.

**12.** Khi nào nhánh `non-sealed` làm giảm khả năng liệt kê hữu hạn toàn bộ subtype?  
**Đáp án:** Khi nhánh đó cho phép tiếp tục có các subtype gián tiếp không nằm trong root `permits`, vì vậy toàn bộ cây không còn đóng.

**13.** Một `record R<T>(T value)` có thể triển khai sealed interface không?  
**Đáp án:** Có, nếu là direct permitted implementor phù hợp. Record là final ngầm định và không thể kế thừa class tùy ý.

**14.** Có nên dùng `abstract` + `final` để “không tạo được và không kế thừa được” không?  
**Đáp án:** Không. Hai modifier này mâu thuẫn trên class; với utility class, dùng class thường/final và constructor private khi cần, còn abstract class có chủ đích làm superclass.

**15.** `sealed` có làm mất type erasure không?  
**Đáp án:** Không. Hai cơ chế độc lập: sealed giới hạn direct subtypes, generic erasure ảnh hưởng thông tin type arguments tại runtime.

**16.** Để một subclass được phép từ sealed parent tiếp tục giới hạn một tầng nữa, chọn modifier gì?  
**Đáp án:** `sealed` với tập subclasses được phép của chính nhánh đó; các nhánh ở tầng tiếp theo tiếp tục chọn `final`, `sealed` hoặc `non-sealed`.

**17.** Trong ví dụ, vì sao `numberView.describe()` in `integer:21` dù `describe()` được định nghĩa ở root?  
**Đáp án:** `describe()` gọi `kind()`, còn `kind()` được override ở `IntegerItem`. Runtime dynamic dispatch chọn bản `kind()` đó.

**18.** Nếu muốn cho một cặp dữ liệu có generic type mà không cần is-a hierarchy, nên cân nhắc gì?  
**Đáp án:** Composition, ví dụ `record Pair<A,B>(A first, B second)`, thay vì tạo subclass chỉ để chứa thêm trường.

Tóm lại, **generics quyết định quan hệ kiểu**, còn **`abstract`/`final`/`sealed` quyết định hợp đồng khởi tạo và mở rộng lớp**. Với Java 17, bạn có thể dùng root generic abstract sealed, phân nhánh bằng final/sealed/non-sealed, giữ type arguments an toàn khi kế thừa và bổ sung hành vi theo từng subtype. Thiết kế đúng khi tập subtype được kiểm soát theo nhu cầu thực tế, không đánh đổi tính rõ ràng chỉ để sử dụng nhiều modifier.
