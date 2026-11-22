# Trường `final` và giới hạn của cách bổ sung sao chép sau `super.clone()`

## 1. Vấn đề cần giải quyết

Khi sao chép một đối tượng Java, ta thường muốn tạo **một instance mới** nhưng bảo đảm những dữ liệu có thể thay đổi bên trong không bị chia sẻ ngoài ý muốn với đối tượng gốc. Với mảng, `List`, `Map` hoặc những object mutable, chỉ sao chép tham chiếu là chưa đủ.

Một cách được nhắc đến trong mã Java kế thừa là:

1. Gọi `super.clone()` để tạo một instance có các trường ban đầu được sao chép từ đối tượng hiện tại.
2. Sau đó, trên object bản sao, **gán lại các trường tham chiếu mutable** thành bản sao riêng (ví dụ `result.items = new ArrayList<>(items)`).

Kỹ thuật này **có giới hạn quan trọng khi field được khai báo `final`**. Với:

```java
private final int[] values;
```

câu lệnh `result.values = values.clone();` bên trong `clone()` **không biên dịch được**, vì Java không cho phép gán lại trường `final` trong một phương thức thông thường, dù trường đó thuộc instance mới do `super.clone()` tạo ra.

Trong khi đó, `super.clone()` vẫn sao chép được **giá trị tham chiếu** của trường `final`. Hệ quả là object gốc và object clone có thể giữ **cùng một mảng mutable**:

```text
Trước clone:
original.values ─────> int[] {1, 2}

Sau super.clone() (bản sao nông):
original.values ──┐
                  ├────> cùng một int[] {1, 2}
copy.values ──────┘

Mong muốn nếu độc lập:
original.values ─────> int[] {1, 2}
copy.values ─────────> int[] {1, 2} (mảng khác)
```

Đây là trọng tâm của bài: **`final` làm tham chiếu không thể bị gán lại sau khởi tạo thông thường, nhưng không làm đối tượng được tham chiếu trở nên bất biến; `super.clone()` lại thực hiện sao chép nông, còn cách sửa bằng gán lại field sau clone bị chặn bởi `final`.**

## 2. Hiểu chính xác `final` trên trường dữ liệu

So sánh ba trường hợp:

| Khai báo | Điều `final` bảo vệ | Điều nó **không** bảo vệ |
| --- | --- | --- |
| `private final int count;` | Sau khi khởi tạo, không thể gán lại `count` từ phương thức thông thường | Không có object con mutable trong trường primitive này |
| `private final String name;` | Không thể gán lại tham chiếu `name` | `String` tự nó bất biến; đó là thuộc tính của lớp `String`, không phải phép màu của `final` |
| `private final int[] scores;` | Không thể gán lại tham chiếu `scores` trong method | Vẫn có thể gọi `scores[0] = 99`; phần tử mảng mutable |
| `private final List<Item> items;` | Không thể gán lại tham chiếu `items` | Có thể sửa collection nếu loại list cho phép; cũng có thể sửa từng `Item` mutable |

Ví dụ:

```java
// Mảnh code trong một class; không phải chương trình độc lập.
private final int[] scores = {5, 10};

void update() {
    scores[0] = 20;            // Hợp lệ: sửa phần tử mảng
    // scores = new int[] {5}; // LỖI BIÊN DỊCH: gán lại final field
}
```

Một field `final` có thể được khởi tạo trong khai báo hoặc trong constructor theo quy tắc Java về gán một lần; không được gán lại tùy tiện trong các method khác. Với tham chiếu mutable, điều đó là **cố định địa chỉ tham chiếu ở cấp ngôn ngữ**, không phải *deep immutability*.

Cần phân biệt `final class` với `final field`: lớp `final` không thể bị kế thừa, nhưng các object được lưu trong field của nó vẫn có thể mutable. Ngược lại, một trường `final` có thể xuất hiện trong lớp không `final`.

## 3. `Cloneable`, `Object.clone()` và bản sao nông

### 3.1. `Cloneable` không tự cung cấp một phương thức `clone()` public

`java.lang.Cloneable` là một **marker interface**. Nó không khai báo phương thức `clone()` để bên gọi tùy ý sử dụng. `Object.clone()` là phương thức `protected`, có thể được lớp con override để công bố API clone phù hợp.

Khi `Object.clone()` được gọi trên instance không hỗ trợ `Cloneable`, nó có thể ném `CloneNotSupportedException`. Các mảng Java là trường hợp đặc biệt: mảng hỗ trợ clone và `array.clone()` tạo mảng mới với phần tử được sao chép nông theo cấp mảng.

Một mẫu truyền thống:

```java
@Override
public Example clone() {
    try {
        return (Example) super.clone();
    } catch (CloneNotSupportedException e) {
        throw new AssertionError(e);
    }
}
```

Đây là mảnh code minh họa bên trong lớp `Example implements Cloneable`. Bắt exception thành `AssertionError` chỉ hợp lý nếu bạn **biết chắc** class thực hiện `Cloneable` và `super.clone()` có thể hoạt động theo hợp đồng; không sao chép cơ học sang mọi cây kế thừa.

### 3.2. `super.clone()` không chạy constructor của lớp đang được clone

`Object.clone()` tạo một đối tượng có các field ban đầu nhận các giá trị như đối tượng nguồn theo cơ chế shallow copy. Nó **không gọi constructor thông thường** của lớp đó để khởi tạo lại các trường hoặc kiểm tra lại toàn bộ bất biến.

Do vậy:

- Trường primitive nhận cùng giá trị primitive.
- Trường `String` hay object bất biến có thể giữ cùng tham chiếu; thường an toàn vì nội dung không thể sửa.
- Trường tham chiếu tới mảng, collection hoặc object mutable được sao chép dưới dạng **cùng một tham chiếu**.
- Trường `final` cũng được chép giá trị ban đầu, nhưng code Java trong `clone()` không được gán lại nó sau đó.

Điều này không đồng nghĩa Java nói “không thể clone class có `final`”: **vẫn có thể clone**, nhưng nếu field `final` trỏ tới dữ liệu mutable cần độc lập, kỹ thuật “`super.clone()` rồi gán lại field” không đáp ứng được.

## 4. Vì sao đoạn sửa shallow clone thông thường không áp dụng cho `final`?

Với field không `final`, lớp cũ thường viết:

```java
// Mảnh code trong một lớp implements Cloneable, có List<String> items.
@Override
public Example clone() {
    try {
        Example result = (Example) super.clone();
        result.items = new ArrayList<>(this.items);
        return result;
    } catch (CloneNotSupportedException e) {
        throw new AssertionError(e);
    }
}
```

Mảnh này giả định `items` là trường **không final** và các phần tử `String` bất biến. `new ArrayList<>(items)` tạo list mới, nhưng chỉ shallow copy các phần tử. Nếu `items` chứa `MutableItem`, hai list khác nhau vẫn chia sẻ chính các phần tử mutable.

Đổi khai báo thành:

```java
private final List<String> items;
```

thì dòng:

```java
result.items = new ArrayList<>(this.items);
```

trở thành **compile-time error**: không thể gán lại trường `final`. Không thể lách giới hạn chỉ bằng cách cast, gọi setter hay bỏ `private`; setter vẫn không có quyền gán lại field final đã khởi tạo.

**Không sửa bằng cách thao tác trực tiếp vào collection đã chia sẻ**:

```java
// KHÔNG đúng nếu original.items và result.items trỏ cùng một list!
result.items.clear();
result.items.addAll(this.items);
```

Thao tác như thế thay đổi **chính collection mà bản gốc cũng sở hữu**. Với `this.items` trỏ cùng đối tượng, `clear()` còn làm mất dữ liệu nguồn trước khi `addAll` chạy. Đây không phải cách tạo bản sao độc lập.

Tương tự, gọi `result.values[0] = ...` trên mảng `final` sau clone chỉ sửa phần tử của cùng mảng, không tách thành mảng mới.

## 5. Ví dụ Java 17 hoàn chỉnh: chia sẻ nguy hiểm và hai phương án an toàn

Ví dụ sau kiểm tra ba thiết kế:

1. `ShallowFinalClone` có `private final int[]` và override `clone()` bằng `super.clone()`. Mảng nguồn được copy vào constructor nhưng bản gốc và clone **vẫn chung mảng** sau clone.
2. `SafeCopy` giữ `private final int[]` và có **copy constructor**, tạo mảng mới khi xây object. Bản gốc và bản copy có thể thay đổi độc lập.
3. `DeepCloneMutableField` cố ý để field mảng **không final**, cho phép clone bằng `super.clone()` rồi gán lại một bản sao mảng. Nó minh họa điểm giới hạn cú pháp: kỹ thuật này hoạt động khi field không final nhưng phải đánh đổi sự cố định tham chiếu ở cấp field.

Lưu tệp **`FinalCloneDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

public class FinalCloneDemo {
    static final class ShallowFinalClone implements Cloneable {
        private final int[] values;

        ShallowFinalClone(int[] input) {
            values = Objects.requireNonNull(input, "input").clone();
        }

        void update(int index, int value) {
            values[index] = value;
        }

        int[] snapshot() {
            return values.clone();
        }

        boolean sharesArrayWith(ShallowFinalClone other) {
            return values == other.values;
        }

        @Override
        public ShallowFinalClone clone() {
            try {
                return (ShallowFinalClone) super.clone();
                // Không thể viết:
                // result.values = this.values.clone();
                // vì values là final.
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }
    }

    static final class SafeCopy {
        private final int[] values;

        SafeCopy(int[] input) {
            values = Objects.requireNonNull(input, "input").clone();
        }

        SafeCopy(SafeCopy other) {
            Objects.requireNonNull(other, "other");
            values = other.values.clone();
        }

        void update(int index, int value) {
            values[index] = value;
        }

        int[] snapshot() {
            return values.clone();
        }

        boolean sharesArrayWith(SafeCopy other) {
            return values == other.values;
        }
    }

    static final class DeepCloneMutableField implements Cloneable {
        private int[] values; // Không final để có thể gán lại trong clone()

        DeepCloneMutableField(int[] input) {
            values = Objects.requireNonNull(input, "input").clone();
        }

        void update(int index, int value) {
            values[index] = value;
        }

        int[] snapshot() {
            return values.clone();
        }

        boolean sharesArrayWith(DeepCloneMutableField other) {
            return values == other.values;
        }

        @Override
        public DeepCloneMutableField clone() {
            try {
                DeepCloneMutableField copy =
                    (DeepCloneMutableField) super.clone();
                copy.values = values.clone();
                return copy;
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }
    }

    public static void main(String[] args) {
        int[] external = {1, 2};
        ShallowFinalClone original = new ShallowFinalClone(external);
        ShallowFinalClone clone = original.clone();

        external[0] = 99;
        System.out.println("Constructor detached input: "
            + Arrays.toString(original.snapshot()));
        System.out.println("Final clone shares array: "
            + original.sharesArrayWith(clone));

        clone.update(0, 7);
        System.out.println("Original after clone update: "
            + Arrays.toString(original.snapshot()));
        System.out.println("Clone after update: "
            + Arrays.toString(clone.snapshot()));

        SafeCopy safeOriginal = new SafeCopy(new int[] {1, 2});
        SafeCopy safeCopy = new SafeCopy(safeOriginal);
        safeCopy.update(0, 7);
        System.out.println("Copy constructor shares array: "
            + safeOriginal.sharesArrayWith(safeCopy));
        System.out.println("Safe original: "
            + Arrays.toString(safeOriginal.snapshot()));
        System.out.println("Safe copy: "
            + Arrays.toString(safeCopy.snapshot()));

        DeepCloneMutableField deepOriginal =
            new DeepCloneMutableField(new int[] {1, 2});
        DeepCloneMutableField deepCopy = deepOriginal.clone();
        deepCopy.update(0, 7);
        System.out.println("Repaired clone shares array: "
            + deepOriginal.sharesArrayWith(deepCopy));
        System.out.println("Repaired original: "
            + Arrays.toString(deepOriginal.snapshot()));
        System.out.println("Repaired copy: "
            + Arrays.toString(deepCopy.snapshot()));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**, trong thư mục chứa tệp:

```bash
javac FinalCloneDemo.java
java FinalCloneDemo
```

Kết quả xác định:

```text
Constructor detached input: [1, 2]
Final clone shares array: true
Original after clone update: [7, 2]
Clone after update: [7, 2]
Copy constructor shares array: false
Safe original: [1, 2]
Safe copy: [7, 2]
Repaired clone shares array: false
Repaired original: [1, 2]
Repaired copy: [7, 2]
```

**Diễn giải:**

- Constructor của `ShallowFinalClone` đã `clone()` mảng input nên sửa `external[0]` không ảnh hưởng nội bộ. Nhưng đó chỉ là ranh giới **caller → original**. Khi gọi `original.clone()`, `super.clone()` lại tạo **hai object giữ chung một field tham chiếu**, và `final` không tách được object được tham chiếu.
- `clone.update(0, 7)` thay đổi mảng chung; kết quả snapshot của cả gốc và clone đều `[7, 2]`. Đây là lỗi độc lập của bản sao, không phải do getter làm lộ tham chiếu.
- `SafeCopy(SafeCopy other)` **tạo object bằng constructor**, nên có quyền gán giá trị mới cho field `final` ngay trong giai đoạn khởi tạo. Mảng được clone riêng, các lần sửa sau đó độc lập.
- `DeepCloneMutableField.clone()` dùng được `copy.values = values.clone()` vì `values` không final. Nó vẫn cần copy đúng mọi thành phần mutable khác của lớp nếu có; đây chỉ là ví dụ với một mảng primitive.
- Các bản sao đều là instance khác nhau. Mục tiêu “độc lập” đề cập **không chia sẻ nội dung mutable cần sở hữu riêng**, không phải chỉ kiểm tra `clone != original`.

## 6. Giải pháp ưu tiên: copy constructor hoặc factory tạo object mới

Khi class cần trường `final` và cả trạng thái được sao chép độc lập, **copy constructor** là cách trực tiếp:

```java
public final class Snapshot {
    private final int[] values;

    public Snapshot(int[] values) {
        this.values = values.clone();
    }

    public Snapshot(Snapshot source) {
        this.values = source.values.clone();
    }

    public int[] values() {
        return values.clone();
    }
}
```

Lưu ý: đoạn này là một class độc lập không có `main`; nếu biên dịch riêng, lưu `Snapshot.java`. Việc kiểm tra `null` phải được bổ sung nếu input được phép không hợp lệ và cần thông báo lỗi rõ ràng.

Cách làm này đáp ứng ba yêu cầu:

1. **Khởi tạo field final hợp lệ:** constructor gán tham chiếu một lần trong vòng đời tạo instance.
2. **Copy-in:** tránh bên gọi sửa mảng đầu vào rồi làm thay đổi snapshot.
3. **Copy-out:** getter không trả trực tiếp mảng nội bộ.

Có thể tạo factory đặt tên thể hiện rõ chính sách:

```java
public static Snapshot copyOf(Snapshot source) {
    return new Snapshot(source);
}
```

Đây là mảnh code thêm **bên trong** lớp `Snapshot` ở trên, không phải phương thức độc lập nằm ngoài class.

### 6.1. “Copy constructor” không mặc định là deep copy

Nếu field là `List<MutableItem>`, viết `new ArrayList<>(other.items)` chỉ sao chép **collection vỏ ngoài**; các `MutableItem` vẫn có thể được chia sẻ. Nếu mỗi phần tử cần sở hữu riêng, constructor phải copy đúng cấp dữ liệu mutable:

```java
// Mảnh code: giả sử MutableItem có copy constructor.
List<MutableItem> copiedItems = other.items.stream()
    .map(MutableItem::new)
    .toList();
```

`Stream.toList()` trong Java 17 tạo list không cho sửa cấu trúc, nhưng nếu `MutableItem` vẫn là mutable thì bản sao cho phép sửa từng phần tử; đó có thể đúng với một lớp sở hữu riêng phần tử, miễn các tham chiếu ấy không bị lộ trái phép. Nếu muốn trạng thái bất biến sâu, hãy dùng immutable value object hoặc snapshot record cho từng phần tử.

### 6.2. Khi nào không cần copy từng thành phần?

Không phải tham chiếu nào cũng phải clone:

- `String`, `LocalDate`, `Instant`, `BigInteger`, các value object bất biến được thiết kế đúng: chia sẻ tham chiếu thường an toàn.
- `List<String>` đã tạo bằng `List.copyOf`, với phần tử `String` bất biến và không có alias mutable ảnh hưởng, có thể chia sẻ như một immutable value.
- Immutable record với **mọi component bất biến sâu** có thể được tái sử dụng trong bản sao mà không phá sự độc lập quan sát được.

Ngược lại, chỉ gắn `final` vào `List<MutableItem>` hoặc dùng `List.copyOf` chưa tự biến `MutableItem` thành bất biến. Tập hợp có cấu trúc không sửa được nhưng chứa object mutable **không phải** immutable graph.

## 7. Có thể giữ `clone()` public mà không dùng `super.clone()` không?

Với một lớp `final` tự thiết kế, nếu API đã yêu cầu tên `clone()`, bạn có thể **tạo instance mới bằng constructor** trong override thay vì dùng `super.clone()`:

```java
public final class CloneByConstructor implements Cloneable {
    private final int[] values;

    public CloneByConstructor(int[] input) {
        this.values = input.clone();
    }

    @Override
    public CloneByConstructor clone() {
        return new CloneByConstructor(this.values);
    }
}
```

Đây là một class có thể biên dịch nếu lưu `CloneByConstructor.java`; không chứa `main`. Trong ví dụ này, constructor sẽ clone mảng đầu vào lần nữa, bảo đảm bản sao có mảng riêng. Implement `Cloneable` là lựa chọn để giữ một API quen thuộc, nhưng **không phải điều kiện cần** để phương thức tự viết ở đây dùng `new` tạo object mới; nó chỉ quan trọng khi sử dụng cơ chế `Object.clone()`.

Tuy vậy, **đừng áp dụng ngây thơ cho cây kế thừa mở**: constructor của class cha/con có thể có bất biến, loại runtime của object có thể là subclass, và một bản sao được tạo bằng constructor của lớp cha có thể làm mất trạng thái/lớp con. Thường nên thiết kế copy constructor hoặc factory rõ ràng cho từng kiểu, hoặc ưu tiên value object bất biến.

Nếu class là `final` như `CloneByConstructor`, không có subclass nên việc tạo đúng kiểu bản sao dễ kiểm soát hơn.

## 8. Vì sao bỏ `final` chỉ để phục vụ `super.clone()` chưa chắc tốt?

Một lựa chọn về mặt cú pháp là bỏ `final`:

```java
private int[] values; // Có thể gán lại trong clone(), nhưng không còn final.
```

Điều đó cho phép:

```java
Example copy = (Example) super.clone();
copy.values = values.clone();
```

Đây là mảnh code giả định lớp `Example implements Cloneable`, có field `values` không final và đang trong method `clone()` có xử lý checked exception phù hợp.

Tuy nhiên việc bỏ `final` đánh đổi:

- **Bất biến tham chiếu**: các method khác trong class có thể gán lại field, tăng không gian trạng thái cần kiểm soát.
- **Tín hiệu thiết kế**: người đọc không còn được bảo đảm rằng field tham chiếu không bị thay sau khi object được khởi tạo.
- **An toàn công bố và concurrency**: `final` có ngữ nghĩa bộ nhớ riêng theo Java Memory Model khi object được xây đúng và không làm lộ `this` trong constructor. Loại bỏ `final` có thể khiến lý luận về khởi tạo/công bố khó hơn; nó không tự động khiến code sai, nhưng không nên bỏ qua lợi ích này chỉ vì clone.
- **Bảo trì**: phải luôn nhớ cập nhật `clone()` khi thêm field mutable mới; quên copy một field là thêm một đường chia sẻ không mong muốn.

Không cần khẳng định mọi class nên bất biến. Nếu yêu cầu thật sự cần một class mutable được clone theo giao thức riêng, field không final và deep-copy có kiểm soát là thiết kế có thể chấp nhận. Nhưng nếu yêu cầu lõi là một snapshot không đổi hoặc một value object, constructor/factory và các field final thường dễ chứng minh đúng hơn.

## 9. Tác động tới `equals()`, `hashCode()` và collection băm

Khi sao chép một object, cần tách **độc lập trạng thái** khỏi **bình đẳng theo giá trị**:

- `original == copy` phải là `false` nếu tạo instance mới thật sự.
- `original.equals(copy)` có thể là `true` hoặc `false` tùy ngữ nghĩa equality của class. Với value object cùng thành phần, thường là `true`; với entity so theo danh tính riêng, tùy chiến lược ID.
- `original.hashCode() == copy.hashCode()` **bắt buộc** khi `equals` nói bằng nhau; hai object khác nhau vẫn có thể trùng hash hợp lệ.
- `toString()` có thể hiển thị cùng nội dung dù clone chia sẻ mutable object; chuỗi dễ đọc **không chứng minh** sự độc lập.

Nếu `equals/hashCode` dựa trên mảng mutable được chia sẻ bởi clone, thao tác thay đổi thông qua clone có thể làm hash của object gốc **thay đổi ngầm**. Nếu gốc đang là khóa `HashMap` hoặc phần tử `HashSet`, lookup có thể thất bại.

Ví dụ:

```java
// Mảnh code: giả sử key.hashCode() dựa trên nội dung một mảng mutable.
set.add(original);
CloneType copy = original.clone(); // super.clone() chia sẻ mảng final
copy.updateValue(0, 99);          // có thể khiến original.hashCode() đổi
boolean found = set.contains(original); // không được bảo đảm như kỳ vọng
```

Mã trên minh họa hệ quả thiết kế; không phải một chương trình Java độc lập. Nếu object được dùng làm khóa băm, những trường tham gia `equals/hashCode` cần ổn định trong thời gian nó nằm trong cấu trúc băm, hoặc phải chọn biểu diễn identity phù hợp. Defensive copying chỉ giải quyết alias từ bên ngoài; bản thân class vẫn có method sửa trạng thái thì đối tượng vẫn mutable.

## 10. Các cách xử lý khi có tập hợp hoặc đối tượng lồng nhau

### 10.1. `final List<String>`

Nếu class nhận list chứa `String` và muốn chụp snapshot cấu trúc:

```java
// Mảnh code bên trong constructor; input: List<String>.
this.tags = List.copyOf(input);
```

Với field `private final List<String> tags;`, lời gọi `List.copyOf` tạo/gắn một list không sửa được với các String bất biến. Khi tạo một bản sao nghiệp vụ sau này, có thể dùng lại `tags` nếu bảo đảm tính immutable của nội dung. **Không cần** `super.clone()` rồi gán lại `tags` để đạt độc lập giá trị.

### 10.2. `final List<MutableItem>`

Nếu `MutableItem` thay đổi được, `List.copyOf(items)` chỉ tạo/giữ list không cho sửa **cấu trúc**; các phần tử mutable vẫn chia sẻ. Cần copy hoặc chuyển thành immutable item trong constructor:

```java
// Mảnh code: ItemSnapshot là record chỉ chứa immutable fields.
this.items = input.stream()
    .map(x -> new ItemSnapshot(x.id(), x.name()))
    .toList();
```

Đoạn này giả định field có kiểu `List<ItemSnapshot>`, input có `id()` và `name()`, còn các component của `ItemSnapshot` bất biến. `Stream.toList()` trả list không cho sửa cấu trúc trong Java 17. Đây là snapshot các trường được chọn, không phải “clone tất cả” tự động.

### 10.3. `final int[][]`

`matrix.clone()` chỉ sao chép mảng ngoài; các hàng `int[]` vẫn chia sẻ. Nếu cần độc lập toàn bộ ma trận:

```java
static int[][] copyMatrix(int[][] source) {
    int[][] result = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        result[i] = source[i].clone();
    }
    return result;
}
```

Đây là hàm minh họa giả định `source` và mọi hàng khác `null`; chính sách `null` phải được thiết kế thêm nếu dữ liệu cho phép. Hãy gọi `copyMatrix` trong constructor để gán field final, và khi trả ma trận ra ngoài để không làm lộ alias.

### 10.4. Object graph có vòng tham chiếu

Với nhiều node tham chiếu qua lại, “deep copy” có thể cần bảng ánh xạ từ node cũ sang node mới để giữ cấu trúc và xử lý vòng; copy constructor đơn giản trên từng node có thể lặp vô hạn hoặc vô tình tạo nhiều bản sao của cùng node. Nếu yêu cầu nghiệp vụ chỉ cần vài giá trị, thiết kế immutable DTO/snapshot thường ít lỗi hơn việc clone toàn bộ graph.

## 11. Đặt câu hỏi đúng trước khi chọn giải pháp

Một bảng lựa chọn thực tế:

| Nhu cầu | Giải pháp phù hợp | Ghi chú |
| --- | --- | --- |
| Snapshot/value object có `final` và dữ liệu cần độc lập | Copy constructor hoặc factory + defensive copy | Dễ bảo toàn final field và bất biến |
| Chỉ có field primitive và immutable references | Chia sẻ các giá trị immutable có thể chấp nhận | Không cần deep-copy vô ích |
| Bắt buộc tương thích clone cũ, field mutable không final | `super.clone()` rồi thay từng reference mutable bằng bản sao | Cập nhật mỗi khi thêm trường cần copy |
| Bắt buộc API tên `clone()` nhưng class `final` có mutable final field | Override `clone()` để gọi constructor/factory mới | Không bắt buộc dùng `super.clone()` |
| Đang có `final List<MutableItem>` cần bất biến sâu | Chuyển từng item thành immutable value snapshot | `List.copyOf` đơn lẻ chưa đủ |
| Class/graph có kế thừa hoặc quan hệ phức tạp | Thiết kế giao thức copy chuyên biệt hoặc snapshot theo miền | Cẩn thận mất subtype và vòng tham chiếu |

**Không có một “deep clone” tự động đúng cho mọi object Java**: tài nguyên file/socket, lock, entity ID, kết nối database và object graph có thể có quy tắc sở hữu riêng. Clone một connection hoặc copy cùng business ID có thể không mang ý nghĩa hợp lệ. Cần quyết định rõ đối tượng mới được phép chia sẻ gì và phải độc lập với cái gì.

## 12. Các lỗi thường gặp

| Sai lầm | Vì sao sai? | Hướng khắc phục |
| --- | --- | --- |
| Nghĩ `final int[]` làm mảng bất biến | Chỉ cố định tham chiếu, phần tử vẫn sửa được | Defensive copy và API không lộ alias |
| Nghĩ `super.clone()` tự deep copy | Chỉ sao chép nông các field | Thiết kế copy từng thành phần mutable |
| Viết `copy.finalField = ...` sau `super.clone()` | Không biên dịch: không được gán lại final field | Copy constructor/factory tạo instance mới |
| Gọi `copy.items.clear()/addAll` để “sửa” alias | Hai object có thể chung list, sửa clone cũng sửa gốc | Tạo collection mới trong constructor hoặc cho field không final nếu đúng thiết kế |
| Dùng `new ArrayList<>(source)` và cho rằng phần tử mutable đã độc lập | Chỉ copy vỏ collection | Copy phần tử mutable hoặc snapshot immutable |
| Chỉ copy input ở constructor rồi `super.clone()` | Caller đã tách nhưng clone mới vẫn chia sẻ nội bộ với gốc | Áp dụng riêng chiến lược copy khi tạo clone |
| Bỏ `final` mà không xét thiết kế | Mất cam kết cố định tham chiếu và thay đổi cách lý luận concurrency | Ưu tiên constructor khi muốn field final |
| Để clone kế thừa từ class cha bỏ sót field mới của subclass | Bản sao có thể chia sẻ trạng thái mutable hoặc mất bất biến | Thiết kế copy cho cả lớp cha/con và kiểm thử |
| Dùng `clone()` mà không có chiến lược xử lý lỗi/`Cloneable` | `Object.clone()` có thể ném `CloneNotSupportedException` | Dùng API copy rõ ràng hoặc triển khai Cloneable đúng |
| Gọi clone rồi chỉ kiểm tra `original != copy` | Hai object khác tham chiếu vẫn có thể chung mảng | Thử sửa bản sao và xác nhận gốc không đổi |

## 13. Checklist kiểm thử

Đối với lớp có mutable final field và yêu cầu copy độc lập:

1. **Kiểm tra tạo instance khác:** `original != copy`.
2. **Kiểm tra nội dung khởi đầu:** các giá trị cần tương đương sau khi copy.
3. **Kiểm tra alias:** sửa qua phương thức của bản copy, quan sát xem bản gốc có đổi không.
4. **Kiểm tra input alias:** sửa mảng/list đầu vào sau constructor; object đã tạo có đổi không?
5. **Kiểm tra output alias:** nếu getter trả array/list, sửa giá trị nhận về có ảnh hưởng nội bộ không?
6. **Kiểm tra nested mutable:** mảng nhiều chiều hoặc phần tử mutable có được copy đến đúng độ sâu không?
7. **Kiểm tra equals/hashCode:** bản sao độc lập không được làm hash của object gốc thay đổi ngoài ý muốn; quan hệ equality phù hợp domain.
8. **Kiểm tra null, collection order và invariant:** chiến lược copy không vô ý đổi điều kiện hợp lệ, thứ tự hay tính duy nhất.
9. **Kiểm tra khai báo `final` và compile:** những giải pháp dùng constructor gán được field trong thời điểm hợp lệ; các giải pháp gán lại trong `clone()` sẽ bị Java từ chối.
10. **Kiểm tra các subtype:** nếu có inheritance, clone có giữ đúng runtime type và các invariant của từng lớp không?

Một kiểm thử chỉ so mảng ban đầu bằng nhau không đủ để chứng minh độc lập. Cần chủ động **thay đổi bản sao sau khi tạo** rồi đối chiếu bản gốc; đây là cách nhanh nhất để phát hiện shared mutable state.

## 14. Tự kiểm tra

**Câu 1.** Một lớp có `private final int[] numbers`. `super.clone()` có sao chép các phần tử sang mảng mới không?

**Đáp án:** Không. Bản sao shallow giữ cùng tham chiếu mảng. Field `final` vẫn được sao chép giá trị tham chiếu ban đầu, chứ không tự tạo mảng mới.

**Câu 2.** Vì sao `copy.numbers = numbers.clone()` sau `super.clone()` không biên dịch nếu `numbers` là `final`?

**Đáp án:** Vì đó là phép gán lại final field trong phương thức `clone()`, không phải thao tác khởi tạo field hợp lệ ở constructor hay initializer. Object được sinh bởi `super.clone()` không làm mất quy tắc `final` của ngôn ngữ.

**Câu 3.** Có thể viết `numbers[0] = 3` dù `numbers` là final không? Điều đó giải quyết deep copy không?

**Đáp án:** Có thể sửa phần tử nếu mảng mutable; nhưng không tạo mảng mới, nên không giải quyết vấn đề chia sẻ alias. Nếu clone đang chung mảng với gốc, cả hai cùng quan sát thay đổi.

**Câu 4.** Cách nào giữ được `private final int[] numbers` nhưng tạo hai instance sở hữu mảng riêng?

**Đáp án:** Copy constructor hoặc factory gọi constructor, và clone mảng khi gán field lúc tạo instance. Nếu cần API `clone()`, có thể tự tạo một instance bằng constructor trong phương thức đó đối với lớp có thiết kế phù hợp.

**Câu 5.** `List.copyOf(List<MutableItem>)` có tạo immutable graph không?

**Đáp án:** Không. Nó không cho sửa cấu trúc list nhưng vẫn tham chiếu các `MutableItem`; để có bất biến sâu cần immutable item hoặc copy từng item đúng mức.

**Câu 6.** Sau khi `super.clone()`, hai object có `original != copy` và `original.toString().equals(copy.toString())`. Đã chứng minh độc lập chưa?

**Đáp án:** Chưa. Cả hai chỉ xác nhận instance khác và biểu diễn chuỗi tương tự. Cần thử thay đổi dữ liệu mutable thông qua một bên và quan sát bên kia.

**Câu 7.** Có nhất thiết phải bỏ `final` để có bản sao độc lập không?

**Đáp án:** Không. Chỉ việc **gán lại sau `super.clone()`** bị chặn. Tạo object mới qua constructor/factory cho phép khởi tạo field final bằng tham chiếu đã được sao chép, mà vẫn giữ thiết kế cố định tham chiếu.

---

**Ghi nhớ:** `final` cố định **tham chiếu của field**, không làm bất biến dữ liệu được tham chiếu. `super.clone()` tạo **bản sao nông**, không tự sao chép mảng/collection; cách “`super.clone()` rồi gán lại field” không áp dụng cho trường `final`. Khi cần độc lập thực sự mà vẫn giữ field final, ưu tiên **copy constructor/factory với defensive copying**, và kiểm thử bằng cách sửa bản sao rồi xác nhận bản gốc không thay đổi.