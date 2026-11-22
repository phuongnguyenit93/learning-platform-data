# Thiết kế trường `private final` và khởi tạo đầy đủ trong lớp bất biến Java

## 1. Mục tiêu: một đối tượng có trạng thái hợp lệ và không đổi sau khi tạo

**Lớp bất biến (*immutable class*)** là lớp mà **trạng thái quan sát được của mỗi đối tượng không thay đổi sau khi đối tượng được xây dựng hoàn tất**. Người dùng đối tượng có thể đọc dữ liệu hoặc yêu cầu tính toán, nhưng không thể làm giá trị logic của cùng đối tượng đổi từ trạng thái A sang trạng thái B.

Trong Java, một cách thiết kế phổ biến cho value object bất biến là:

1. Khai báo class `final` khi không cần hỗ trợ subclass, để ngăn class con làm thay đổi hợp đồng bất biến.
2. Đặt các instance fields ở mức `private` để code bên ngoài không được phép truy cập/gán trực tiếp.
3. Khai báo fields `final` để mỗi field chỉ được gán theo quy tắc khởi tạo, không bị gán lại sau đó.
4. **Khởi tạo đầy đủ** mọi field từ dữ liệu hợp lệ trước khi constructor hoàn tất bình thường.
5. Không cung cấp setter hoặc method nào mutate observable state.
6. Với **mutable inputs** (mảng, list, `Date`, object mutable khác), dùng **defensive copy** hoặc immutable snapshot thích hợp.
7. Khi trả dữ liệu ra ngoài, không làm lộ tham chiếu tới mutable state nội bộ.
8. Không làm `this` thoát ra ngoài trước khi constructor và các invariants hoàn thành.

Ví dụ chuẩn:

```java
public final class Product {
    private final String code;
    private final int price;

    public Product(String code, int price) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code required");
        }
        if (price < 0) {
            throw new IllegalArgumentException("negative price");
        }

        this.code = code;
        this.price = price;
    }

    public String code() {
        return code;
    }

    public int price() {
        return price;
    }
}
```

Đây là **class hợp lệ để lưu trong `Product.java`**, nhưng chưa có `main`. `String` là immutable, `int` là primitive, còn các fields private final được gán đúng một lần ở constructor. Với các methods hiện có, caller không thể khiến `code` hoặc `price` của một Product đã tạo đổi.

**Điểm đặc biệt:** `private final` là **nền tảng**, nhưng **chưa đủ** nếu field trỏ tới object mutable. Ví dụ `private final List<String> items` vẫn có thể trỏ tới một `ArrayList` đang bị mutate.

## 2. Phân biệt `private`, `final` và tính bất biến

Ba khái niệm rất dễ bị nhầm:

| Khái niệm | Bảo đảm chính | Điều không tự bảo đảm |
| --- | --- | --- |
| `private` | Giới hạn truy cập trực tiếp tới member ngoài phạm vi cho phép | Không ngăn các methods trong class thay đổi field |
| `final` trên instance field | Field phải được gán theo definite-assignment rules và không được gán lại sau khi được khởi tạo | Không làm object được tham chiếu immutable |
| `final` trên class | Class không thể bị subclass | Không ngăn bản thân class sửa mutable fields |
| Immutable object design | Trạng thái quan sát được không thay đổi sau construction | Không phát sinh chỉ nhờ một modifier |

Ví dụ class **chưa bất biến** dù có field private:

```java
class Counter {
    private int count;

    void increment() {
        count++;
    }
}
```

`private` chỉ khiến caller không trực tiếp viết `counter.count = ...`; chính method `increment()` vẫn mutate.

Ví dụ khác **chưa bất biến** dù field là private final:

```java
class Box {
    private final java.util.List<String> names =
            new java.util.ArrayList<>();

    void add(String name) {
        names.add(name);
    }
}
```

Field reference `names` không thể trỏ sang một list khác sau initialization, nhưng **nội dung list thay đổi** sau `add`.

**Suy luận đúng:** Cần xem **observable state**, các objects được giữ bên trong và toàn bộ public/protected/package-private API, chứ không chỉ đếm bao nhiêu lần có từ khóa `final`.

## 3. Ví dụ runnable đầu tiên: value object bất biến

Tạo tệp **`ImmutableProductDemo.java`**:

```java
final class Product {
    private final String code;
    private final int price;

    Product(String code, int price) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code required");
        }
        if (price < 0) {
            throw new IllegalArgumentException("negative price");
        }

        this.code = code;
        this.price = price;
    }

    String code() {
        return code;
    }

    int price() {
        return price;
    }

    Product withPrice(int newPrice) {
        return new Product(code, newPrice);
    }

    @Override
    public String toString() {
        return code + ":" + price;
    }
}

public class ImmutableProductDemo {
    public static void main(String[] args) {
        Product original = new Product("P1", 100);
        Product updated = original.withPrice(120);

        System.out.println("original=" + original);
        System.out.println("updated=" + updated);
        System.out.println("same reference=" + (original == updated));
    }
}
```

Chạy với JDK 17+:

```bash
javac ImmutableProductDemo.java
java ImmutableProductDemo
```

**Standard output:**

```text
original=P1:100
updated=P1:120
same reference=false
```

**Giải thích:**

1. `Product` là `final class`, không thể có subclass thay đổi hợp đồng của Product.
2. `code` và `price` là `private final`, được kiểm tra và gán trong constructor.
3. Không có `setCode` hoặc `setPrice` để thay đổi Product sau khi tạo.
4. `withPrice(120)` **không sửa original**. Nó tạo **Product mới** với trạng thái khác.
5. Hai references `original` và `updated` khác nhau, nhưng original giữ nguyên `P1:100`.

Cách dùng `with...` trả object mới thường phù hợp với immutable value classes. Nó có chi phí cấp phát object, nhưng đổi lại đơn giản hơn khi suy luận về trạng thái và sharing; hãy đánh giá trade-off bằng yêu cầu thực tế, không mặc định mọi object trong hệ thống đều phải immutable.

## 4. “Khởi tạo đầy đủ” nghĩa là gì?

Đối tượng được **khởi tạo đầy đủ** khi mọi thuộc tính bắt buộc đã có giá trị **hợp lệ và nhất quán** trước khi được công bố để sử dụng.

Điều đó gồm hai lớp yêu cầu khác nhau:

**A. Definite assignment theo Java compiler:** mọi **blank final instance field** phải được gán chắc chắn theo quy tắc trước khi constructor hoàn tất bình thường.

**B. Domain invariant:** dữ liệu phải thỏa **điều kiện nghiệp vụ** như mã không trống, số tiền không âm, `start <= end`, không null, các danh sách không chứa entry bất hợp lệ.

Compiler kiểm được A nhưng **không tự kiểm toàn bộ B**. Ví dụ `private final String code` được gán `null` vẫn có thể **biên dịch**, nhưng nếu domain không chấp nhận null, constructor phải kiểm.

Một constructor nên **kiểm tra đầu vào trước khi công bố thành công instance**, rồi gán fields nhất quán. Nếu validation thất bại và exception được ném, caller không nhận một object hoàn thành bình thường.

### Mã minh họa bị từ chối khi chưa gán blank final field

```java
// Ví dụ lỗi compile-time khi bỏ comment:
//
// class Broken {
//     private final int id;
//
//     Broken() {
//         // Không gán id.
//     }
// }
```

`id` là blank final field. Dù Java cấp giá trị mặc định cho instance storage, compiler **không xem default 0 là assignment đủ cho `final` field**. Constructor được yêu cầu definite-assign field theo rules.

## 5. `final` field có thể khởi tạo tại khai báo hoặc trong constructor

Hai cách đều hợp lệ:

**Khởi tạo tại field declaration:**

```java
class FixedVersion {
    private final int version = 1;
}
```

**Khởi tạo trong constructor:**

```java
class VersionedItem {
    private final int version;

    VersionedItem(int version) {
        this.version = version;
    }
}
```

Khác biệt:

- Field có initializer tại khai báo sẽ được gán trong quy trình instance initialization cho mỗi instance.
- Blank final field không có initializer và phải được gán theo constructor flow hợp lệ.
- Nếu đã khai báo `private final int version = 1;`, **không thể gán lại `version` trong constructor**.
- Nếu giá trị dựa vào arguments, gán trong constructor thường thể hiện ý định rõ hơn.
- Nếu có giá trị dùng chung không phụ thuộc từng instance, cân nhắc `static final` constant phù hợp thay vì mỗi object giữ field riêng, nhưng semantics khác với instance final.

### Ví dụ sai do gán final hai lần

```java
// class Broken {
//     private final int version = 1;
//
//     Broken() {
//         version = 2; // Lỗi compile-time.
//     }
// }
```

Không phải chỉ “gán lại sau khi constructor xong” mới bị cấm. Với final field đã khởi tạo ở declaration, việc cố ghi thêm trong constructor cũng sai.

## 6. Constructor chaining: `this(...)` và một nơi gán chính

Với nhiều constructor overloads, nên gom validation/assignment về **một constructor chuẩn** để giảm khả năng quên field hoặc tạo bất biến không nhất quán.

Tệp **`ImmutableConstructorChainDemo.java`**:

```java
final class Customer {
    private final String name;
    private final String country;

    Customer(String name) {
        this(name, "VN");
    }

    Customer(String name, String country) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        if (country == null || country.isBlank()) {
            throw new IllegalArgumentException("country required");
        }
        this.name = name;
        this.country = country;
    }

    String label() {
        return name + "@" + country;
    }
}

public class ImmutableConstructorChainDemo {
    public static void main(String[] args) {
        Customer first = new Customer("An");
        Customer second = new Customer("Binh", "SG");

        System.out.println(first.label());
        System.out.println(second.label());
    }
}
```

```bash
javac ImmutableConstructorChainDemo.java
java ImmutableConstructorChainDemo
```

```text
An@VN
Binh@SG
```

- Constructor một tham số bắt đầu bằng `this(name, "VN")`.
- Constructor hai tham số là **điểm gán** hai fields sau khi kiểm input.
- Các fields không bị gán lại lần nữa khi quay về constructor một tham số.
- Trong Java 17, explicit constructor invocation `this(...)` hoặc `super(...)` phải đứng ở đầu constructor body theo quy tắc phiên bản này.
- Chọn một constructor có trách nhiệm khởi tạo đầy đủ giúp tránh duplication của validations và assignment logic.

**Không viết** một constructor dùng `this(...)` mà sau đó lại gán `final` fields đã được constructor đích gán.

## 7. Validate toàn bộ quan hệ giữa fields, không chỉ từng field riêng

Ví dụ lưu thời gian bắt đầu/kết thúc:

```java
final class TimeRange {
    private final int start;
    private final int end;

    TimeRange(int start, int end) {
        if (start < 0 || end < start) {
            throw new IllegalArgumentException("invalid range");
        }
        this.start = start;
        this.end = end;
    }

    int duration() {
        return end - start;
    }
}
```

Đây là **khai báo class hợp lệ**, chưa có `main`.

`start` và `end` đều là `final`, nhưng bất biến thực sự còn đòi `start >= 0` và `end >= start`. Compiler không biết đây là invariant của domain.

Nếu constructor nhận thông tin từ nhiều nguồn, hãy xét **tính nhất quán của toàn bộ trạng thái**. Tránh mô hình “gán tạm rồi nhờ setter hoàn thiện sau” cho một object mà API công khai yêu cầu luôn valid.

**Với thuật toán có overflow**, cần thêm range check/kiểu dữ liệu đủ lớn theo nghiệp vụ. Ví dụ trên minh họa quan hệ giữa hai fields, không tuyên bố phù hợp cho mọi loại số hoặc thời gian thực tế.

## 8. `private` ngăn caller sửa field trực tiếp, không ngăn class tự sửa

Tệp **`PrivateNotImmutableDemo.java`**:

```java
class Meter {
    private int value;

    Meter(int value) {
        this.value = value;
    }

    void change(int next) {
        value = next;
    }

    int value() {
        return value;
    }
}

public class PrivateNotImmutableDemo {
    public static void main(String[] args) {
        Meter meter = new Meter(10);

        System.out.println(meter.value());
        meter.change(20);
        System.out.println(meter.value());
    }
}
```

```bash
javac PrivateNotImmutableDemo.java
java PrivateNotImmutableDemo
```

```text
10
20
```

`private` bảo vệ quyền truy cập trực tiếp từ caller. Nhưng `change` là instance method hợp lệ và mutate field. Vì vậy đây **không phải immutable object**.

Nếu muốn bất biến, field thường nên `final` và không có mutator; hoặc tổ chức API để trả **object mới** khi dữ liệu thay đổi. Một class có trạng thái mutable đôi khi vẫn là thiết kế đúng (ví dụ mutable buffer), nhưng không nên gắn nhãn immutable khi API có thay đổi observable state.

## 9. `final` trên reference: cố định tham chiếu chứ không đóng băng đối tượng

Xét:

```java
final java.util.List<String> names =
        new java.util.ArrayList<>();

names.add("An"); // Hợp lệ: mutate list object.
// names = new java.util.ArrayList<>(); // Không hợp lệ: gán lại final variable.
```

Điều tương tự đúng với **`private final List<String> names`** bên trong một class.

### Ví dụ runnable phản chứng

Tệp **`FinalReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Group {
    private final List<String> members = new ArrayList<>();

    void add(String name) {
        members.add(name);
    }

    List<String> members() {
        return members;
    }
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        Group group = new Group();

        group.add("An");
        group.members().add("Binh");

        System.out.println(group.members());
    }
}
```

```bash
javac FinalReferenceDemo.java
java FinalReferenceDemo
```

```text
[An, Binh]
```

Mặc dù field `members` là `private final`:

1. Method `add` mutate list nội bộ.
2. Getter `members()` trả **chính list reference**; caller có thể mutate nội bộ qua nó.
3. Vì thế Group là **mutable**, không phải immutable value object.

Cần xử lý cả **đầu vào constructor** và **đầu ra getter** nếu state tham chiếu có thể mutate. Đây là lý do defensive copying quan trọng.

## 10. Defensive copy với mảng khi nhận vào và khi trả ra

Mảng Java là mutable: có thể sửa phần tử bằng `array[i]=...`. Field `private final int[] scores` chỉ cố định **array reference**, không ngăn việc sửa slots.

Tệp **`ImmutableScoresDemo.java`**:

```java
import java.util.Arrays;

final class Scores {
    private final int[] values;

    Scores(int[] input) {
        if (input == null) {
            throw new IllegalArgumentException("scores required");
        }
        for (int value : input) {
            if (value < 0) {
                throw new IllegalArgumentException("negative score");
            }
        }

        values = input.clone(); // Copy at ingress.
    }

    int size() {
        return values.length;
    }

    int at(int index) {
        return values[index];
    }

    int[] snapshot() {
        return values.clone(); // Copy at egress.
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class ImmutableScoresDemo {
    public static void main(String[] args) {
        int[] source = {10, 20};
        Scores scores = new Scores(source);

        source[0] = 99;
        System.out.println("after source change=" + scores);

        int[] fromGetter = scores.snapshot();
        fromGetter[1] = 77;

        System.out.println("after getter change=" + scores);
        System.out.println("size=" + scores.size());
        System.out.println("first=" + scores.at(0));
    }
}
```

```bash
javac ImmutableScoresDemo.java
java ImmutableScoresDemo
```

```text
after source change=[10, 20]
after getter change=[10, 20]
size=2
first=10
```

**Hai hướng copy đều cần thiết:**

- `input.clone()` trong constructor chặn caller sửa object thông qua mảng gốc sau khi truyền vào.
- `values.clone()` trong getter chặn caller nhận reference nội bộ và sửa slots.
- `size` và `at` trả primitives, không làm lộ mutable array.

`clone()` trên `int[]` tạo mảng primitive một chiều mới với cùng values; đủ cho ví dụ này. Nếu là `MutableElement[]`, clone chỉ copy **array structure**, không deep-copy từng mutable element.

**Chi tiết về concurrency:** Nếu input array bị một thread khác mutate đồng thời trong lúc constructor validate/copy, có nguy cơ validation và snapshot không nhất quán. Trong ví dụ một luồng, giả định caller không sửa input đồng thời; code sản phẩm cần ownership hoặc synchronization thích hợp nếu dữ liệu có thể thay đổi đồng thời.

## 11. Vì sao chỉ copy khi getter chưa đủ?

Giả sử constructor viết:

```java
class BadSnapshot {
    private final int[] values;

    BadSnapshot(int[] values) {
        this.values = values; // Chỉ giữ alias, không copy.
    }

    int[] values() {
        return values.clone();
    }
}
```

Getter có defensive copy, nhưng **caller giữ mảng đầu vào gốc**. Sau `new BadSnapshot(source)`, nếu caller viết `source[0] = 999`, state nội bộ `BadSnapshot.values` cũng đổi.

Ngược lại, nếu constructor copy nhưng getter trả thẳng mảng nội bộ, caller lại có đường mutate khác. Vì vậy phải khảo sát **mọi đường alias ra/vào mutable state**, không chỉ một phía.

Nguyên tắc:

```text
Caller mutable input
       |
       v
Validate / snapshot (copy)
       |
       v
Private final internal state
       |
       v
Query primitives / immutable values
       hoặc copy khi trả mutable data
       |
       v
Caller output
```

Không phải lúc nào copy cả hai lần cũng là lựa chọn duy nhất: có thể dùng immutable value components, read-only API mà implementation thật sự không thể bị mutate, hoặc quy định ownership transfer nghiêm ngặt. Nhưng nếu class được quảng bá immutable cho callers tổng quát, defensive copy là hướng dễ chứng minh hơn.

## 12. `List.copyOf` tạo immutable structural snapshot

Từ Java 10, `List.copyOf(collection)` tạo **unmodifiable list** chứa các elements từ input theo contract. Với mutable input như `ArrayList`, đây là cách rất hữu ích để cắt alias cấu trúc list.

Tệp **`ImmutablePlaylistDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Playlist {
    private final List<String> songs;

    Playlist(List<String> input) {
        Objects.requireNonNull(input, "songs");
        songs = List.copyOf(input);
    }

    List<String> songs() {
        return songs;
    }

    int size() {
        return songs.size();
    }
}

public class ImmutablePlaylistDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        Playlist playlist = new Playlist(source);
        source.add("B");

        System.out.println("source=" + source);
        System.out.println("playlist=" + playlist.songs());

        try {
            playlist.songs().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot modify playlist");
        }

        System.out.println("size=" + playlist.size());
    }
}
```

```bash
javac ImmutablePlaylistDemo.java
java ImmutablePlaylistDemo
```

```text
source=[A, B]
playlist=[A]
cannot modify playlist
size=1
```

Vì sao getter có thể trả `songs` trực tiếp ở đây?

- `List.copyOf` cho một unmodifiable list mà callers không thể dùng `add`/`remove` để mutate cấu trúc.
- Trong ví dụ elements là `String` immutable, nên không có nested mutable element để làm đổi nghĩa logical state.
- `source` ban đầu mutable nhưng biến đổi cấu trúc source sau constructor không làm list snapshot của Playlist thêm phần tử.

**Lưu ý thực tế:** `List.copyOf` từ chối null elements (`NullPointerException` theo API). Hãy xác định rõ null policy của domain, đừng ngầm mong null được giữ.

`List.copyOf` có thể tận dụng đầu vào vốn đã unmodifiable theo API; điều quan trọng là **semantics unmodifiable/snapshot phù hợp**, không phải bảo đảm luôn tạo object mới có identity khác.

## 13. `Collections.unmodifiableList` là view, không nhất thiết là snapshot

Hai API này dễ bị đánh đồng:

```java
List<String> view =
        java.util.Collections.unmodifiableList(source);
```

`view` **không cho mutate qua chính view**, nhưng nó vẫn phản ánh thay đổi cấu trúc được thực hiện trực tiếp trên `source` list bên dưới. Vì vậy, bản thân `unmodifiableList(source)` **không tạo snapshot**.

### Ví dụ runnable so sánh

Tệp **`ViewVersusCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVersusCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view =
                Collections.unmodifiableList(source);
        List<String> copy = List.copyOf(source);

        source.add("B");

        System.out.println("view=" + view);
        System.out.println("copy=" + copy);
    }
}
```

```bash
javac ViewVersusCopyDemo.java
java ViewVersusCopyDemo
```

```text
view=[A, B]
copy=[A]
```

Khi cần một snapshot và muốn dùng `Collections.unmodifiableList`, có thể bọc **một bản sao riêng**:

```java
List<String> snapshot =
        Collections.unmodifiableList(new ArrayList<>(source));
```

Đây là **mảnh code trong method** đã có `source`; imports có thể dùng `java.util.*` đầy đủ khi cần. Caller không được mutate list snapshot qua API của nó và cũng không giữ alias tới internal copied list nếu chỉ nhận wrapper.

Tuy nhiên, kể cả snapshot cấu trúc cũng vẫn là **shallow copy** đối với mutable elements.

## 14. Shallow immutability: `List.copyOf` không đóng băng elements

Một list có thể không cho `add` nhưng những **objects nằm trong list vẫn có thể mutable**.

Tệp **`ShallowListDemo.java`**:

```java
import java.util.List;

public class ShallowListDemo {
    public static void main(String[] args) {
        StringBuilder text = new StringBuilder("A");
        List<StringBuilder> list = List.copyOf(List.of(text));

        text.append("B");

        System.out.println(list.get(0).toString());

        try {
            list.add(new StringBuilder("C"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("structure is unmodifiable");
        }
    }
}
```

```bash
javac ShallowListDemo.java
java ShallowListDemo
```

```text
AB
structure is unmodifiable
```

- `List.copyOf` giữ reference tới `StringBuilder` element.
- Caller có thể mutate `text` thành AB; `list.get(0)` quan sát AB.
- List structure không cho add, nhưng element state vẫn đổi.

**Thiết kế sâu hơn:** dùng immutable element type như `String`, record có immutable components, hoặc tạo **deep copy**/snapshot cho từng mutable element nếu domain yêu cầu. Đừng gọi một class “fully immutable” khi nested mutable object vẫn có thể bị thay qua alias.

### Shallow và deep copy khác nhau

- **Shallow copy**: copy container, giữ references tới elements.
- **Deep copy**: copy cả những mutable parts cần thiết của object graph theo contract.
- Deep copy không phải một lệnh có sẵn đúng cho mọi graph, nhất là khi có cycles, shared identity hoặc external resources.
- Immutability thường dễ đạt nhất bằng việc **lưu immutable value components**, hạn chế số objects mutable phải sao chép.

## 15. Khởi tạo `private final int[][]` cần sao chép đến đúng tầng

Một field có thể được gán một lần nhưng vẫn trỏ vào **đồ thị mutable**. Với mảng hai chiều `int[][]`, gọi `source.clone()` chỉ tạo **outer array** mới; từng hàng `int[]` vẫn có thể là cùng object với source:

~~~java
int[][] source = {{1, 2}, {3}};
int[][] shallow = source.clone();
source[0][0] = 99;
// shallow[0][0] == 99, vì hàng 0 vẫn trỏ cùng mảng con.
~~~

Đây là fragment dùng trong một method. Nếu muốn một immutable value snapshot, constructor phải khởi tạo đầy đủ field bằng cách copy từng hàng:

~~~java
private final int[][] rows;

Matrix(int[][] source) {
    java.util.Objects.requireNonNull(source, "source");
    int[][] copy = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        copy[i] = java.util.Objects.requireNonNull(
                source[i], "row").clone();
    }
    rows = copy;
}
~~~

Đoạn constructor/field ở trên thuộc **một class `Matrix`**, không phải file runnable độc lập. Nếu class cung cấp accessor trả `int[][]`, accessor cũng cần copy outer + từng inner array trước khi trả. Với **mảng chứa mutable objects**, copy từng reference chưa đủ; phải quyết định immutable representation hoặc copy từng phần tử đúng contract.

**Ranh giới:** bài này tập trung việc `private final rows` được **khởi tạo hoàn chỉnh với representation an toàn**. Chương trình deep-copy ma trận và so sánh shallow/deep nhiều tầng nằm ở bài **“Bất biến nông và bất biến sâu”**; các bài test đầu vào/đầu ra và nested aliases nằm ở bài **“Kiểm tra tính bất biến khi lớp chứa mảng hoặc tập hợp”**.

## 16. Mutable `Date`: copy ở constructor và getter

`java.util.Date` là class mutable; nó có method `setTime`. Chỉ giữ `private final Date createdAt` không ngăn người khác sửa object Date ấy.

Tệp **`ImmutableTimestampDemo.java`**:

```java
import java.util.Date;
import java.util.Objects;

final class Timestamp {
    private final Date moment;

    Timestamp(Date input) {
        Objects.requireNonNull(input);
        moment = new Date(input.getTime());
    }

    Date moment() {
        return new Date(moment.getTime());
    }

    long epochMillis() {
        return moment.getTime();
    }
}

public class ImmutableTimestampDemo {
    public static void main(String[] args) {
        Date input = new Date(1000L);
        Timestamp stamp = new Timestamp(input);

        input.setTime(2000L);
        System.out.println(stamp.epochMillis());

        Date extracted = stamp.moment();
        extracted.setTime(3000L);
        System.out.println(stamp.epochMillis());
    }
}
```

```bash
javac ImmutableTimestampDemo.java
java ImmutableTimestampDemo
```

```text
1000
1000
```

- Constructor copy value từ mutable `Date` bằng `new Date(input.getTime())`.
- Getter trả Date mới, không trả nội bộ `moment`.
- Getter trả `long` epoch cũng không làm lộ mutable reference.

**Lựa chọn hiện đại:** nếu phù hợp domain, dùng `java.time.Instant`/`LocalDate`/`LocalDateTime` — đây là những immutable date-time value types trong Java 17, thường dễ thiết kế hơn `Date`.

**Điều kiện:** Ví dụ giả định caller không mutate `Date input` đồng thời với thao tác constructor đọc `getTime()`; thread-safe handoff cần được xử lý riêng nếu input đang dùng chung.

## 17. Một class `final` giúp chặn subclass phá hợp đồng quan sát được

Giả sử một base class định nghĩa API trả giá trị nhưng cho phép subclass override method đó:

```java
class BasePrice {
    private final int amount;

    BasePrice(int amount) {
        this.amount = amount;
    }

    int amount() {
        return amount;
    }
}
```

Nếu `BasePrice` không final, subclass có thể giữ mutable field riêng và override `amount()` để trả giá trị thay đổi, khiến người dùng nhìn qua reference `BasePrice` quan sát state khác theo thời gian.

Vì vậy, một immutable value class đơn giản thường nên là `final class`.

Tuy nhiên, **`final` class một mình không đủ**: class có thể chứa mutable fields, list hoặc callbacks. Và một abstract base class được thiết kế cẩn thận vẫn có thể có immutable concrete subclasses — không phải mọi mô hình bất biến đều bắt buộc final ở gốc hierarchy.

### Tránh gọi overridable methods trong constructor

Một superclass constructor gọi method có thể bị override sẽ dispatch tới subclass **khi subclass fields chưa khởi tạo xong**, vi phạm suy luận về invariant. Thiết kế immutable classes thường tránh những overridable hooks trong construction và không làm `this` escape sớm.

## 18. `this` escape trước khi constructor hoàn tất là rủi ro

Ví dụ thiết kế nguy hiểm:

```java
class Registry {
    static final java.util.List<Object> ALL =
            new java.util.ArrayList<>();
}

class Leaky {
    private final String name;

    Leaky(String name) {
        Registry.ALL.add(this); // Công bố object khi chưa gán name.
        this.name = name;
    }
}
```

Đây là **khai báo minh họa anti-pattern**, không có `main` và không nên áp dụng thực tế.

Dù compiler chấp nhận final field được definite assigned trước khi constructor trả về, `this` được ghi vào registry **trước khi `name` được gán**. Code bên ngoài có thể quan sát object chưa xây dựng đầy đủ, và trong chương trình đa luồng sẽ có thêm nguy cơ publication/visibility.

Các đường escape thường gặp:

- Đăng ký `this` vào static collection.
- Đăng ký callback/listener từ constructor.
- Truyền `this` cho một component có thể lưu lại hoặc gọi overridable methods.
- Khởi động thread trong constructor với code đóng trên `this`.
- Publish reference vào shared field khi chưa có synchronization/handoff thích hợp.

**Nguyên tắc:** Hoàn tất validation và assignment trước khi cho các thành phần khác sử dụng object; tốt hơn, để factory hoặc caller publish/register object **sau khi constructor trả về**.

## 19. Tính bất biến và tính an toàn đa luồng liên hệ nhưng không đồng nhất

Một object được thiết kế immutable và chia sẻ an toàn có lợi thế lớn: nhiều threads chỉ đọc cùng state mà không cần lock cho mỗi getter.

Tuy nhiên cần nói chính xác:

- Java có **final field semantics** đặc biệt trong Java Memory Model giúp visibility của final fields sau construction đúng quy tắc, khi object **được xây dựng đúng cách**.
- Nếu `this` escape trước khi constructor hoàn tất, bảo đảm liên quan final fields có thể không còn áp dụng như mong đợi.
- `final` field không làm **mutable referenced objects** thread-safe.
- Nếu class giữ mutable cache hoặc tự cập nhật collection bên trong, nó có thể **không còn immutable**.
- Khi publish immutable object qua concurrent infrastructure (queues, volatile references, synchronized handoff), phải tuân thủ contract của phương tiện publication; không đánh đồng immutable với tùy ý chia sẻ một object đang xây dựng dở.

### Ví dụ đọc immutable value object qua nhiều threads

Tệp **`ImmutableConcurrentReadDemo.java`**:

```java
final class Pair {
    private final int left;
    private final int right;

    Pair(int left, int right) {
        this.left = left;
        this.right = right;
    }

    int sum() {
        return left + right;
    }
}

public class ImmutableConcurrentReadDemo {
    public static void main(String[] args) throws InterruptedException {
        Pair pair = new Pair(10, 20);

        Runnable reader = () -> {
            if (pair.sum() != 30) {
                throw new AssertionError("unexpected sum");
            }
        };

        Thread a = new Thread(reader);
        Thread b = new Thread(reader);

        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("shared value=" + pair.sum());
    }
}
```

```bash
javac ImmutableConcurrentReadDemo.java
java ImmutableConcurrentReadDemo
```

```text
shared value=30
```

Pair object được tạo hoàn tất trước khi threads bắt đầu. Hai readers chỉ gọi method thuần trả sum từ primitive final fields, không sửa object. Việc gọi `start`/`join` tham gia các happens-before relationships theo Thread API. Không có thứ tự in từ worker threads nên stdout ổn định.

**Đây không phải chứng minh mọi `final` reference graph đều an toàn đa luồng.** Nếu Pair chứa một shared mutable `ArrayList` và trả nó ra ngoài, tình hình khác hẳn.

## 20. Derived values: tính khi cần hay cache?

Một immutable class có thể tính giá trị suy ra từ các fields:

```java
final class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("negative size");
        }
        this.width = width;
        this.height = height;
    }

    long area() {
        return (long) width * height;
    }
}
```

Ở đây `area()` **không thay đổi observable state** và có thể tính lại theo nhu cầu. Dùng phép nhân `long` sau cast để tránh overflow của `int*int` trong trường hợp kích thước lớn.

Nếu tính toán rất đắt, bạn có thể **precompute** kết quả trong constructor và lưu một final field khác:

```java
private final long area;
```

Nhưng không nhất thiết phải tạo lazy cache mutable trong một immutable object. Một `private long cachedArea` cập nhật lười (lazy) không làm giá trị nghiệp vụ đổi nếu được che giấu kỹ, nhưng có thêm yêu cầu về thread safety, visibility và publication.

**Mặc định cho bài học:** Tính từ final fields hoặc tính trước khi constructor hoàn tất; chỉ tối ưu caching sau khi đã đo và có contract concurrency rõ.

## 21. `equals` và `hashCode` trên immutable value class

Immutable objects thường là key phù hợp cho `HashMap`/`HashSet` vì các fields dùng cho equality/hashCode không đổi sau creation.

Tệp **`ImmutableKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

final class Key {
    private final String region;
    private final String code;

    Key(String region, String code) {
        this.region = Objects.requireNonNull(region);
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Key key)) {
            return false;
        }
        return region.equals(key.region)
                && code.equals(key.code);
    }

    @Override
    public int hashCode() {
        return Objects.hash(region, code);
    }
}

public class ImmutableKeyDemo {
    public static void main(String[] args) {
        Map<Key, String> items = new HashMap<>();

        items.put(new Key("VN", "P1"), "product");
        System.out.println(items.get(new Key("VN", "P1")));
        System.out.println(items.containsKey(new Key("US", "P1")));
    }
}
```

```bash
javac ImmutableKeyDemo.java
java ImmutableKeyDemo
```

```text
product
false
```

- Hai `new Key("VN","P1")` là references khác identity nhưng value equal.
- `equals`/`hashCode` dựa cùng two final immutable String fields.
- HashMap lookup bằng một instance mới có value tương đương vẫn đúng contract.
- Key không có setters và không chứa mutable components nên equality/hash ổn định.

**Đừng suy rằng mọi immutable class bắt buộc override equals.** Nếu domain semantics cần phân biệt danh tính từng instance, identity equality có thể vẫn là lựa chọn đúng. Immutability và value equality hỗ trợ nhau nhưng không phải cùng khái niệm.

## 22. Java `record` giúp giảm boilerplate nhưng bất biến chỉ nông

Trong Java 17, một record tự có final component fields, canonical constructor, component accessors, equals/hashCode/toString theo rules. Đây là công cụ tốt cho immutable-ish data carriers.

Ví dụ:

```java
record Point(int x, int y) {
}
```

Hai primitive fields bất biến theo thiết kế record, không có setters và không có mutable state bên ngoài.

Nhưng:

```java
record Numbers(int[] values) {
}
```

sẽ **không tự clone mảng** ở constructor hoặc accessor. Vì vậy object record có thể bị ảnh hưởng bởi caller mutate input array và có thể làm lộ mutable internal reference. Record cũng không tự so deep array contents trong generated equals.

### Record với copy phòng vệ

Tệp **`SafeRecordArrayDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record SafeNumbers(int[] values) {
    SafeNumbers {
        Objects.requireNonNull(values);
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    public int at(int index) {
        return values[index];
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class SafeRecordArrayDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        SafeNumbers numbers = new SafeNumbers(input);

        input[0] = 99;
        System.out.println(numbers);

        int[] copy = numbers.values();
        copy[1] = 77;
        System.out.println(numbers);
        System.out.println(numbers.at(0));
    }
}
```

```bash
javac SafeRecordArrayDemo.java
java SafeRecordArrayDemo
```

```text
[1, 2]
[1, 2]
1
```

Trong **compact constructor**, gán `values=values.clone()` thay constructor parameter variable; record sẽ lưu snapshot ấy vào component field theo rules của compact constructor. Accessor `values()` trả bản sao.

**Lưu ý quan trọng:** Auto-generated `equals`/`hashCode` của record có array component vẫn có identity semantics cho array component. Nếu cần **logical content equality** của SafeNumbers, phải override equals/hashCode tương ứng với `Arrays.equals`/`Arrays.hashCode` và kiểm kỹ contract. Defensive copying **không tự sửa** equality của array fields.

## 23. Java `Map.copyOf`, `Set.copyOf` cũng là shallow immutable snapshots

Tương tự `List.copyOf`, các APIs như `Map.copyOf` và `Set.copyOf` tạo unmodifiable structures theo contracts nhưng **không deep-copy mutable elements/values**.

Ví dụ:

```java
Map<String, String> source = new java.util.HashMap<>();
source.put("A", "one");

Map<String, String> snapshot = Map.copyOf(source);
source.put("B", "two");
```

Đây là **mảnh code** có `import java.util.Map;` phù hợp nếu đặt vào method. `snapshot` không tự thêm mapping B từ source sau khi snapshot tạo. Vì keys/values trong ví dụ là String immutable, nó là snapshot thuận tiện.

Trái lại nếu value là mutable `StringBuilder`, caller vẫn có thể mutate nội dung builder được cả source và snapshot giữ reference.

**Quy tắc thiết kế:** “Unmodifiable container” không có nghĩa “deeply immutable data graph”. Cần kiểm **mutable keys/values, aliasing và element types**.

## 24. Builder: gom cấu hình mutable rồi xây immutable object

Khi có nhiều fields, constructor dài dễ đọc sai thứ tự arguments. Một **builder** mutable có thể giữ cấu hình tạm thời, nhưng object cuối cùng vẫn immutable.

Ví dụ tệp **`ImmutableBuilderDemo.java`**:

```java
final class ServerConfig {
    private final String host;
    private final int port;
    private final boolean tls;

    private ServerConfig(String host, int port, boolean tls) {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host required");
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("invalid port");
        }

        this.host = host;
        this.port = port;
        this.tls = tls;
    }

    static Builder builder() {
        return new Builder();
    }

    String summary() {
        return host + ":" + port + ",tls=" + tls;
    }

    static final class Builder {
        private String host;
        private int port = 8080;
        private boolean tls;

        Builder host(String host) {
            this.host = host;
            return this;
        }

        Builder port(int port) {
            this.port = port;
            return this;
        }

        Builder tls(boolean tls) {
            this.tls = tls;
            return this;
        }

        ServerConfig build() {
            return new ServerConfig(host, port, tls);
        }
    }
}

public class ImmutableBuilderDemo {
    public static void main(String[] args) {
        ServerConfig config = ServerConfig.builder()
                .host("localhost")
                .port(8443)
                .tls(true)
                .build();

        System.out.println(config.summary());
    }
}
```

```bash
javac ImmutableBuilderDemo.java
java ImmutableBuilderDemo
```

```text
localhost:8443,tls=true
```

**Phân biệt vòng đời:**

- `Builder` là mutable object để cấu hình từng bước.
- `ServerConfig` được tạo qua private constructor và validate trước khi hoàn tất.
- `ServerConfig` có ba fields private final và không cung cấp setters.
- Thay Builder sau khi `build` không đổi config đã tạo, vì ở ví dụ này config lưu String/primitive values độc lập với mutable Builder.

Nếu Builder giữ mutable collections rồi truyền thẳng references vào immutable object, vẫn phải **snapshot/copy trong `build`/constructor**. Builder **không thay thế defensive copy**.

## 25. Static factory và các phép thay đổi bằng object mới

Immutable class có thể dùng **static factory** thay public constructor để đặt tên business intent:

```java
final class Money {
    private final long cents;

    private Money(long cents) {
        this.cents = cents;
    }

    static Money ofCents(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("negative");
        }
        return new Money(cents);
    }

    Money plus(Money other) {
        return new Money(Math.addExact(cents, other.cents));
    }

    long cents() {
        return cents;
    }
}
```

Đây là **class declaration hợp lệ** không có `main`. Điểm cần cân nhắc:

- `ofCents` validate nonnegative input.
- `plus` trả Money mới, không mutate receiver.
- Nhưng `plus` hiện gọi private constructor trực tiếp và **không kiểm tổng nonnegative**. Do operands trong contract hiện tại nonnegative, tổng cũng nonnegative trừ overflow (được `Math.addExact` bắt), nên invariant vẫn phù hợp.
- Nếu có phép trừ hoặc các operations khác, chúng phải đảm bảo không tạo Money với state bất hợp lệ.

**Tổng kết:** Khi chọn immutable design, mọi factory và arithmetic method tạo instance mới phải duy trì **cùng invariant**, không chỉ public constructor đầu tiên.

## 26. Phân biệt immutable class với unmodifiable view và read-only interface

Ba từ này không đồng nghĩa:

- **Immutable object:** observable state không đổi sau construction.
- **Unmodifiable view:** caller không được mutate **qua view**, nhưng source ở phía sau có thể thay đổi và view thấy thay đổi.
- **Read-only interface:** interface chỉ khai báo query methods, nhưng implementation có thể mutate state do các callers khác hoặc background jobs.

Ví dụ một `List` trả từ `Collections.unmodifiableList(source)` vẫn có thể phản ánh thêm/xóa qua `source`. Tương tự, `private final Repository repository` với method `read()` không chứng minh state repository giữ là immutable.

Hãy hỏi:

1. Ai giữ reference tới backing mutable object?
2. Có bao nhiêu đường dẫn có thể thay state?
3. Getter có trả alias nội bộ không?
4. Có background updater, callback, cache, hoặc lazy evaluation ảnh hưởng observable result không?
5. Có nested mutable elements không?

Một class thật sự immutable có thể chứa *implementation details* phức tạp, nhưng phải đảm bảo contract observable state ổn định trước mọi thao tác hợp lệ của caller.

## 27. Phòng tránh constructor thực hiện công việc chưa hoàn thành

Một số lỗi thường thấy:

- Gán một field rồi gọi callback trước khi gán fields còn lại.
- Đưa `this` vào collection trong constructor.
- Dùng setter để “hoàn thành” state sau khi constructor trả về.
- Cho phép instance with nullable mandatory fields như một giai đoạn tạm.
- Đọc mutable input nhiều lần trong các phép validation và copy khi input có thể bị thay từ thread khác.
- Gọi overridable method trong superclass constructor khiến subclass state chưa sẵn sàng được quan sát.
- Thực hiện I/O hoặc side effects không rollback khi constructor fail giữa chừng.

**Thiết kế tốt hơn:** validate và snapshot inputs, xây state trong constructor, sau đó **chỉ publish object đã hoàn thành**. Nếu cần quy trình cấu hình nhiều bước, dùng Builder/Factory tách giai đoạn mutable build ra ngoài instance bất biến cuối cùng.

## 28. Null policy và normalization phải rõ ràng

Một immutable class không nhất thiết cấm null ở mọi field, nhưng **phải định nghĩa hợp đồng**:

- Field bắt buộc non-null → `Objects.requireNonNull` hoặc exception domain rõ.
- Optional field → có thể null theo contract, hoặc dùng kiểu biểu đạt absence phù hợp.
- String code → có trim/uppercase trước khi lưu hay giữ nguyên?
- Collections → có cho null elements không? `List.copyOf` không cho.
- Date/time → có normalize timezone hoặc resolution không?

Ví dụ:

```java
final class UserId {
    private final String value;

    UserId(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        value = raw.trim().toUpperCase(java.util.Locale.ROOT);
    }

    String value() {
        return value;
    }
}
```

Đây là class hợp lệ không có `main`. Normalize **trước khi lưu final field** giúp mọi instance lưu một representation hợp lệ nhất quán.

**Cảnh báo:** Không giả định `trim`/uppercase là business-normalization đúng cho mọi identifier, đặc biệt với Unicode/case-sensitive IDs. Đó là policy riêng của domain; ví dụ chỉ minh họa nơi đặt normalization.

## 29. Testing: xác nhận bất biến qua aliasing, không chỉ getter

Một class có getters đúng vẫn có thể bị mutate qua input array hoặc returned list. Test bất biến cần kiểm **đường alias**.

Tệp **`ImmutableContractTestDemo.java`**:

```java
import java.util.Arrays;

final class Snapshot {
    private final int[] values;

    Snapshot(int[] input) {
        if (input == null) {
            throw new IllegalArgumentException("null input");
        }
        values = input.clone();
    }

    int[] values() {
        return values.clone();
    }
}

public class ImmutableContractTestDemo {
    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("immutability failure");
        }
    }

    public static void main(String[] args) {
        int[] original = {1, 2};
        Snapshot snapshot = new Snapshot(original);

        original[0] = 99;
        check(Arrays.equals(snapshot.values(), new int[]{1, 2}));

        int[] leaked = snapshot.values();
        leaked[1] = 77;
        check(Arrays.equals(snapshot.values(), new int[]{1, 2}));

        int[] firstRead = snapshot.values();
        int[] secondRead = snapshot.values();
        check(firstRead != secondRead);

        System.out.println("immutable snapshot checks passed");
    }
}
```

```bash
javac ImmutableContractTestDemo.java
java ImmutableContractTestDemo
```

```text
immutable snapshot checks passed
```

Đây là self-test chạy bằng `main`, không phải JUnit. Nó chứng minh snapshot tránh những alias mutations đã thử. Với nested graph hoặc concurrency, cần thêm tests phù hợp.

**Kiểm tra cả đường lỗi:** Nếu constructor nhận dữ liệu sai, phải ném lỗi đúng và không công bố object hoàn tất sai invariant. Với List copy, thử input có null element để xác nhận null policy.

## 30. Tổng hợp các lỗi phổ biến

| Ngộ nhận / lỗi | Vì sao không đúng? | Giải pháp |
| --- | --- | --- |
| “`private` nghĩa là immutable” | Methods nội bộ vẫn mutate được | Xét toàn bộ API và fields |
| “`final` reference làm list immutable” | List object vẫn thay được | Snapshot/unmodifiable container |
| “`final class` đủ để bất biến” | Class vẫn có mutable state | Private final fields + no mutation + copies |
| “Blank final field có default value nên khỏi gán” | Definite assignment bắt buộc | Gán trong mọi constructor path hợp lệ |
| “Có constructor argument là hợp lệ bất kể dữ liệu” | Compiler không biết domain invariant | Validate/normalize trước hoàn thành |
| “Gán final hai lần trong constructor cũng được” | Final field không được gán lại | Một điểm gán chuẩn |
| “Gọi `this(...)` làm field gán hai lần” | Constructor delegation chỉ thực thi initialization đúng một lần cho instance | Không gán lặp ở outer constructor |
| “Copy array lúc trả ra là đủ” | Caller vẫn sửa input alias | Copy cả constructor input |
| “Copy constructor input là đủ” | Getter có thể lộ mảng nội bộ | Getter copy hoặc expose value queries |
| “`array.clone()` luôn deep copy” | Nested refs vẫn alias | Copy mutable nested parts |
| “`Collections.unmodifiableList` là snapshot” | View phản ánh source mutation | `List.copyOf` hoặc wrap copy riêng |
| “`List.copyOf` deep-freezes elements” | Mutable elements vẫn mutate | Immutable elements/deep copy |
| “List unmodifiable và Date immutable như nhau” | Date vẫn mutable | Copy Date hoặc `Instant` |
| “Record tự deep immutable” | Record component có thể là mutable reference | Compact constructor + defensive accessor |
| “Record chứa mảng tự so contents trong equals” | Array equality mặc định theo identity | Custom equals/hashCode nếu cần |
| “Builder mutable khiến built object mutable” | Không nếu built object snapshot độc lập | Không chia sẻ mutable refs |
| “`final` fields tự an toàn mọi luồng” | Constructor escape và mutable graphs nguy hiểm | Proper construction/publication |
| “Lấy final field bằng getter là không thể mutate” | Getter có thể trả mutable object | Copy/unmodifiable value components |
| “Có thể khởi tạo thiếu rồi dùng setters” | Object xuất hiện ở state chưa hợp lệ | Builder riêng, constructor hoàn chỉnh |
| “Constructor gọi override của subclass là an toàn” | Subclass fields có thể chưa initialize | Tránh overridable calls trong constructor |
| “Mọi immutable class phải override equals” | Equality tùy domain | Chọn identity/value semantics rõ |
| “Mọi class nên immutable” | Mutable types có use cases phù hợp | Chọn theo API, performance, lifecycle |

## 31. Bài thực hành tổng hợp: thiết kế một `Course` bất biến

Yêu cầu:

- `Course` có `code` bắt buộc không blank và danh sách `topics` không chứa null/blank.
- Caller có thể mutate list input sau khi tạo, nhưng Course không đổi.
- Getter trả list không thể thêm/xóa.
- Đổi danh sách topics tạo **Course mới** thay vì mutate object ban đầu.
- Code dễ hiểu, dùng Java 17+.

Tệp **`ImmutableCourseDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Course {
    private final String code;
    private final List<String> topics;

    Course(String code, List<String> topics) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code required");
        }
        Objects.requireNonNull(topics, "topics");

        List<String> copy = new ArrayList<>();
        for (String topic : topics) {
            if (topic == null || topic.isBlank()) {
                throw new IllegalArgumentException("invalid topic");
            }
            copy.add(topic);
        }

        this.code = code;
        this.topics = List.copyOf(copy);
    }

    String code() {
        return code;
    }

    List<String> topics() {
        return topics;
    }

    Course withTopic(String topic) {
        List<String> copy = new ArrayList<>(topics);
        copy.add(topic);
        return new Course(code, copy);
    }

    @Override
    public String toString() {
        return code + ":" + topics;
    }
}

public class ImmutableCourseDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Class");

        Course original = new Course("J17", input);
        input.add("Object");

        Course extended = original.withTopic("Constructor");

        System.out.println("input=" + input);
        System.out.println("original=" + original);
        System.out.println("extended=" + extended);

        try {
            original.topics().add("Invalid");
        } catch (UnsupportedOperationException ex) {
            System.out.println("topics are unmodifiable");
        }

        System.out.println("original remains=" + original);
    }
}
```

```bash
javac ImmutableCourseDemo.java
java ImmutableCourseDemo
```

```text
input=[Class, Object]
original=J17:[Class]
extended=J17:[Class, Constructor]
topics are unmodifiable
original remains=J17:[Class]
```

### Giải thích bước một: copy và validate trong constructor

- `code` bắt buộc non-null/nonblank.
- `topics` reference bắt buộc non-null.
- Vòng lặp kiểm từng topic và tạo list tạm mới. Không giữ alias trực tiếp tới `input`.
- `List.copyOf(copy)` tạo unmodifiable snapshot. Vì elements là `String` immutable nên state list thực tế không đổi từ phía caller.
- Fields `code` và `topics` là `private final`, không được gán lại sau construction.

### Giải thích bước hai: input bị mutate sau construction

Caller thêm `"Object"` vào `input`. `original` vẫn chứa list `[Class]`, vì constructor đã snapshot.

### Giải thích bước ba: thay đổi trả object mới

`withTopic("Constructor")` tạo mutable list tạm từ topics cũ, thêm topic mới, rồi xây Course khác qua constructor. Dữ liệu cũ vẫn được giữ nguyên, trong khi đối tượng mới có thêm topic.

### Giải thích bước bốn: chặn mutate qua getter

`topics()` trả unmodifiable list. Caller `add("Invalid")` bị `UnsupportedOperationException`. Original vẫn không đổi.

**Lưu ý:** Ví dụ chỉ chạy một luồng và không có thread khác mutate `topics` input trong constructor. Với shared concurrently mutable collection, muốn snapshot nhất quán phải có synchronization/ownership contract; đây là vấn đề ngoài các modifier field.

## 32. Bài tập tự luyện

**Bài 1.** Vì sao `private final List<String> list = new ArrayList<>()` chưa đủ để lớp bất biến?

**Gợi ý:** `final` chỉ cố định reference; list mutable có thể bị thay nội dung. Kiểm public methods và getters.

**Bài 2.** Nếu constructor gán `this.values = input` cho `int[]` và getter trả clone, caller có làm đổi object không?

**Đáp án:** Có. Caller còn giữ `input` và có thể mutate nó sau constructor; phải copy ingress.

**Bài 3.** Nếu constructor copy `input.clone()` nhưng getter trả `values` trực tiếp thì sao?

**Đáp án:** Getter tạo đường alias cho caller sửa internal array; phải copy egress hoặc chỉ expose value queries.

**Bài 4.** `Collections.unmodifiableList(source)` và `List.copyOf(source)` khác gì với mutable source?

**Đáp án:** View đầu phản ánh source mutation, copyOf snapshot structure theo contract.

**Bài 5.** `List.copyOf(List.of(new StringBuilder("A")))` có bảo đảm text trong element không đổi không?

**Đáp án:** Không. Container unmodifiable nhưng StringBuilder element vẫn mutable nếu còn alias.

**Bài 6.** Một blank final field không được gán trước constructor trả về có compile không?

**Đáp án:** Không, nếu constructor path bình thường vi phạm definite assignment rules.

**Bài 7.** Hai overloaded constructors dùng `this(...)` có nên mỗi constructor gán cùng final field không?

**Đáp án:** Không. Thường gom vào một constructor chính; delegation phải tránh gán final field nhiều lần.

**Bài 8.** `private final Date date` với getter trả chính Date có immutable không?

**Đáp án:** Không. Date mutable; copy ở ingress/egress hoặc dùng `Instant` phù hợp.

**Bài 9.** `record Data(int[] values)` có tự deep immutable không?

**Đáp án:** Không. Cần clone/snapshot và custom accessor; record generated equals cũng không deep-compare array contents.

**Bài 10.** `final class` có bắt buộc để tất cả objects immutable không?

**Đáp án:** Không bắt buộc trong mọi kiến trúc, nhưng là một cách đơn giản để ngăn subclass phá observable contract khi không cần inheritance.

**Bài 11.** Vì sao không nên register `this` vào global registry trong constructor trước khi gán final fields?

**Đáp án:** Object có thể được quan sát trước khi hoàn tất construction, phá invariant và có nguy cơ sai memory visibility.

**Bài 12.** Có cần `synchronized` ở mọi getter của object có primitive final fields và constructed/published đúng không?

**Đáp án:** Thường không cần để bảo vệ khỏi mutation, vì object không đổi. Nhưng phải xét publication, các referenced mutable objects và operations khác.

**Bài 13.** Có thể dùng `withPrice` để đổi giá immutable product không?

**Đáp án:** Có, nếu `withPrice` tạo object mới với state hợp lệ và không sửa original.

**Bài 14.** Copy một `int[][]` bằng `outer.clone()` có đủ để bảo vệ nội dung không?

**Đáp án:** Không, còn alias tới inner arrays; cần copy từng inner row hoặc thiết kế representation khác.

**Bài 15.** Với value object có hai String private final fields, equals/hashCode nên dựa trên gì?

**Đáp án:** Những fields quyết định logical equality theo domain, và cùng tập dữ liệu dùng tính hash.

**Bài 16.** Nếu constructor kiểm riêng từng field đúng nhưng hai fields mâu thuẫn nhau thì immutable contract đã đủ chưa?

**Đáp án:** Chưa. Phải kiểm **invariants giữa fields** trước khi object được xây dựng hoàn tất.

## 33. Checklist code review cho lớp bất biến

- [ ] Class `final` nếu không cần thiết kế inheritance?
- [ ] Tất cả state instance fields có phạm vi `private` thích hợp?
- [ ] Các fields không phải thay đổi sau construction được khai báo `final`?
- [ ] Mọi blank final fields được definite-assign ở tất cả constructor paths hoàn thành bình thường?
- [ ] Constructor validate null, ranges, normalization và invariants liên-fields?
- [ ] Có constructor overload chain mà gán final field sai hoặc duplicate không?
- [ ] Không có public/protected/package methods mutate observable state?
- [ ] Không để `this` escape trước khi construction hoàn tất?
- [ ] Không gọi overridable methods từ superclass constructor gây observation sớm?
- [ ] Mutable inputs có được snapshot/copy trước khi giữ lâu dài?
- [ ] Mutable internal state có bị getter làm lộ alias không?
- [ ] Containers unmodifiable là snapshot thực hay chỉ là view?
- [ ] Nested mutable elements/arrays có cần deep copy/immutable representation không?
- [ ] `List.copyOf`/`Map.copyOf` null-element/value restrictions đã được xác định?
- [ ] Fields giữ `Date`/array/StringBuilder/list có cách xử lý mutability rõ?
- [ ] Record chứa mutable component đã custom constructor/accessor nếu cần?
- [ ] Các phép `with...`/factory luôn tạo state hợp lệ và giữ original không đổi?
- [ ] Nếu có lazy cache, có bảo đảm thread-safety/visibility và observable immutability không?
- [ ] Equals/hashCode nếu có dựa trên dữ liệu không đổi đúng contract?
- [ ] Các object bất biến được publish qua concurrency boundary đúng ngữ nghĩa?
- [ ] Tests thử mutate cả constructor inputs và getter outputs?
- [ ] Tests thử lỗi validation, copy, identity và kết quả query?
- [ ] Ví dụ Java 17+ có đúng tên file/public class, lệnh `javac`/`java` và stdout?

---

**Ghi nhớ cuối bài:** Thiết kế một lớp bất biến trong Java thường bắt đầu bằng **`private final` instance fields và một constructor khởi tạo đầy đủ, kiểm tra mọi invariant**. Nhưng `final` chỉ ngăn gán lại **field**, không làm mutable referenced object bất biến. Muốn object thực sự không đổi, hãy **chặn mọi đường mutation và aliasing**, sao chép mảng/`Date`/collections ở ranh giới thích hợp, dùng immutable components, không để `this` escape khi constructor chưa hoàn tất và hiểu rằng unmodifiable view khác immutable snapshot. Khi cần “thay đổi”, tạo **một object mới** với state hợp lệ. Đây là nền tảng để objects dễ suy luận, dễ kiểm thử, thích hợp làm value keys và thuận tiện khi chia sẻ an toàn.