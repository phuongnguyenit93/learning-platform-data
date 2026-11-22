# Thực nghiệm sửa bản gốc, bản sao và thành phần lồng nhau trong Java

## 1. Mục tiêu học tập và câu hỏi cần chứng minh

Khi tạo một bản sao trong Java, câu hỏi quan trọng không chỉ là **“đã tạo đối tượng mới chưa?”**, mà còn là:

- Nếu **sửa bản gốc**, bản sao có thay đổi theo không?
- Nếu **sửa bản sao**, bản gốc có thay đổi theo không?
- Nếu sửa **thành phần lồng nhau** như mảng, danh sách, địa chỉ hoặc một phần tử mutable, điều gì xảy ra ở từng bản?
- Nếu hai bản chứa cùng một object con, đó là chia sẻ an toàn (immutable) hay lỗi aliasing (mutable)?
- Cách kiểm nào cho phép **kết luận có bằng chứng** thay vì chỉ nhìn `==`, `equals()` hoặc nội dung ban đầu giống nhau?

Bài này sử dụng các **thực nghiệm Java 17+ có thể biên dịch/chạy độc lập**. Mỗi ví dụ phân biệt rõ *đầu vào*, *phép sao chép*, *tác động*, *giá trị quan sát* và *kết luận*. Mã không độc lập được ghi rõ là đoạn minh họa.

> **Nguyên tắc kiểm chứng:** `original != copy` chỉ chứng minh **hai đối tượng ngoài cùng khác danh tính**. Nó **không chứng minh** các đối tượng con như `address`, `items`, `scores` hoặc `items.get(0)` cũng độc lập.

## 2. Ba khái niệm cần phân biệt trước khi thử

| Khái niệm | Cách thực hiện | Điều được bảo đảm |
| --- | --- | --- |
| **Gán tham chiếu / alias** | `B b = a;` | `a` và `b` cùng trỏ một object; chưa tạo bản sao |
| **Sao chép nông (*shallow*)** | `super.clone()`, copy một số reference fields, clone outer container | Object hoặc container mới, nhưng có thể giữ references tới mutable objects cũ |
| **Sao chép sâu theo contract (*deep copy*)** | Copy chủ động các mutable components cần tách | Những đường thay đổi mà contract yêu cầu độc lập không còn làm hai bản ảnh hưởng nhau |

“Deep copy” không nhất thiết là tạo lại **mọi** immutable object:

- Chia sẻ một `String` là an toàn cho giá trị nội dung, vì String immutable.
- Chia sẻ `List.copyOf(...)` của các Strings có thể an toàn khi snapshot không bị backing mutable source thay đổi.
- Chia sẻ một `ArrayList` hoặc `StringBuilder` mutable có thể làm bản gốc và bản sao tác động qua lại.
- Hai graphs có cycles hoặc shared children cần **chính sách copy topology** riêng, không chỉ `clone()` liên tiếp.

Đối với mỗi kiểu dữ liệu, **mức độ sâu phải được định nghĩa bằng observable behavior**. Nếu không, thuật ngữ “deep” rất dễ được dùng quá mức.

## 3. Đọc sơ đồ object graph: điểm nào đang chia sẻ?

Giả sử `Customer` giữ một `Address` mutable:

```text
original Customer A
    name = "An"
    address ───────┐
                   ├──> Address X { city = "Hue" }
copy Customer B    │
    name = "An"     │
    address ───────┘
```

Đây là **shallow copy** ở field `address`.

Sau khi:

```java
original.address.setCity("Da Nang");
```

thành phố mà `copy.address` nhìn thấy cũng đổi, vì **cả hai cùng trỏ Address X**.

Deep copy mong muốn sẽ tạo:

```text
original Customer A --address--> Address X { city = "Hue" }
copy Customer B     --address--> Address Y { city = "Hue" }

X != Y
```

Lúc này mutate X không mutate Y. Các sơ đồ là mô hình **ngữ nghĩa tham chiếu**, không phải khẳng định về vị trí stack/heap vật lý hoặc layout JVM.

## 4. Thí nghiệm số 1: phép gán `b = a` không phải sao chép

Tạo tệp **`ReferenceAliasExperiment.java`**:

```java
final class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}

public class ReferenceAliasExperiment {
    public static void main(String[] args) {
        Counter original = new Counter(10);
        Counter alias = original;

        System.out.println(original == alias);

        alias.increment();
        System.out.println("original=" + original.value());

        original.increment();
        System.out.println("alias=" + alias.value());
    }
}
```

```bash
javac ReferenceAliasExperiment.java
java ReferenceAliasExperiment
```

**Standard output:**

```text
true
original=11
alias=12
```

**Kết luận:** Chưa có object mới. `original` và `alias` cùng trỏ một Counter. Mọi mutation đều quan sát trên cùng state.

**Để tránh suy sai:** Java truyền các giá trị tham số theo tham trị (*pass-by-value*), kể cả giá trị tham chiếu. Truyền reference cho method không tự clone object; nếu method mutate object qua reference, caller vẫn có thể thấy thay đổi.

## 5. Thí nghiệm số 2: hai object độc lập khi chỉ có primitive field

Tạo **`PrimitiveFieldCopyExperiment.java`**:

```java
final class Score {
    private int value;

    Score(int value) {
        this.value = value;
    }

    Score(Score source) {
        this.value = source.value;
    }

    void set(int next) {
        value = next;
    }

    int get() {
        return value;
    }
}

public class PrimitiveFieldCopyExperiment {
    public static void main(String[] args) {
        Score original = new Score(10);
        Score copy = new Score(original);

        System.out.println(original == copy);
        System.out.println("start=" + original.get() + "," + copy.get());

        original.set(20);
        System.out.println("change original=" +
                original.get() + "," + copy.get());

        copy.set(30);
        System.out.println("change copy=" +
                original.get() + "," + copy.get());
    }
}
```

```bash
javac PrimitiveFieldCopyExperiment.java
java PrimitiveFieldCopyExperiment
```

```text
false
start=10,10
change original=20,10
change copy=20,30
```

Ở đây copy constructor tạo `new Score(...)` và gán giá trị `int`. Hai objects có vùng instance state riêng, nên thay primitive field ở bản nào chỉ làm bản ấy đổi.

**Đừng khái quát quá mức:** Với reference field, lệnh `this.child = source.child` **không tạo child object mới**. Vì vậy một copy constructor đúng với primitives có thể trở thành shallow copy nếu thêm một mutable reference field mà không cập nhật logic copy.

## 6. Thí nghiệm số 3: thay field ngoài cùng khác với sửa object con

Ta cố ý sao chép `Customer` **nông** ở field `Address`. Để thấy hai tầng độc lập/chia sẻ, Customer có mutable `name` riêng; Address có `city` mutable.

Tạo **`ShallowAddressExperiment.java`**:

```java
final class Address {
    private String city;

    Address(String city) {
        this.city = city;
    }

    void moveTo(String nextCity) {
        city = nextCity;
    }

    String city() {
        return city;
    }
}

final class Customer {
    private String name;
    private final Address address;

    Customer(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    Customer(Customer source) {
        this.name = source.name;
        this.address = source.address; // Shallow copy.
    }

    void rename(String nextName) {
        name = nextName;
    }

    void move(String nextCity) {
        address.moveTo(nextCity);
    }

    String describe() {
        return name + "@" + address.city();
    }
}

public class ShallowAddressExperiment {
    public static void main(String[] args) {
        Customer original =
                new Customer("An", new Address("Hue"));
        Customer copy = new Customer(original);

        System.out.println("same customer=" + (original == copy));
        System.out.println("start=" + original.describe() +
                " | " + copy.describe());

        original.rename("Binh");
        System.out.println("rename original=" + original.describe() +
                " | " + copy.describe());

        copy.move("Da Nang");
        System.out.println("move copy=" + original.describe() +
                " | " + copy.describe());
    }
}
```

```bash
javac ShallowAddressExperiment.java
java ShallowAddressExperiment
```

```text
same customer=false
start=An@Hue | An@Hue
rename original=Binh@Hue | An@Hue
move copy=Binh@Da Nang | An@Da Nang
```

### Phân tích kết quả

- Hai Customer objects có **identity khác**.
- `name` là một reference field tới String. Gán lại `original.name` không sửa String, mà thay reference của Customer gốc, nên `copy.name` vẫn là `"An"`.
- `address` ở cả hai Customers trỏ **cùng Address object**.
- `copy.move(...)` mutate Address chung, khiến **cả original và copy** thấy `"Da Nang"`.

Đây là **bài học trọng tâm**: cùng một bản sao có thể độc lập ở **một tầng** và chia sẻ ở **tầng sâu hơn**. Đừng chỉ thử setter ngoài cùng rồi kết luận “đã deep copy”.

## 7. Thí nghiệm số 4: sửa bản gốc hay bản sao đều không lan nếu copy đúng Address

Ta sửa copy constructor để tạo một Address mới bằng **copy constructor dành cho component**. Đồng thời constructor Customer cắt alias đầu vào để có quyền sở hữu Address riêng.

Tạo **`DeepAddressExperiment.java`**:

```java
final class Address {
    private String city;

    Address(String city) {
        this.city = city;
    }

    Address(Address source) {
        this.city = source.city;
    }

    void moveTo(String nextCity) {
        city = nextCity;
    }

    String city() {
        return city;
    }
}

final class Customer {
    private final String name;
    private final Address address;

    Customer(String name, Address input) {
        this.name = name;
        this.address = new Address(input);
    }

    Customer(Customer source) {
        this.name = source.name;
        this.address = new Address(source.address);
    }

    void move(String city) {
        address.moveTo(city);
    }

    String describe() {
        return name + "@" + address.city();
    }
}

public class DeepAddressExperiment {
    public static void main(String[] args) {
        Address input = new Address("Hue");
        Customer original = new Customer("An", input);
        Customer copy = new Customer(original);

        input.moveTo("Can Tho");
        System.out.println("after input=" + original.describe() +
                " | " + copy.describe());

        original.move("Da Nang");
        System.out.println("after original=" + original.describe() +
                " | " + copy.describe());

        copy.move("Ha Noi");
        System.out.println("after copy=" + original.describe() +
                " | " + copy.describe());
    }
}
```

```bash
javac DeepAddressExperiment.java
java DeepAddressExperiment
```

```text
after input=An@Hue | An@Hue
after original=An@Da Nang | An@Hue
after copy=An@Da Nang | An@Ha Noi
```

**Ba phép thử tách biệt:**

1. Mutate `input` sau khi tạo Customer: không thay internal Address của Customer, vì constructor cắt alias.
2. Mutate Address của original: copy không đổi.
3. Mutate Address của copy: original không đổi.

**Lưu ý:** Customer trong ví dụ vẫn là mutable class vì có `move`. “Deep copy” không đồng nghĩa “immutable”: hai bản có thể cùng **mutable nhưng độc lập**.

## 8. Bảng truy vết để phân loại đúng kết quả

Cho object có root và component mutable:

| Thao tác | Alias hoàn toàn | Shallow root copy | Deep-enough copy |
| --- | --- | --- | --- |
| `original == copy` | true | false | false |
| Sửa primitive field của original | Copy thấy đổi (cùng root) | Copy thường không đổi | Copy không đổi |
| Sửa primitive field của copy | Original thấy đổi | Original không đổi | Original không đổi |
| Sửa mutable child qua original | Copy thấy đổi | Copy thấy đổi nếu shared child | Copy không đổi |
| Sửa mutable child qua copy | Original thấy đổi | Original thấy đổi nếu shared child | Original không đổi |
| Mutate constructor input đã được giữ bên ngoài | Tùy alias đầu vào | Tùy copy ở constructor | Không đổi nếu constructor snapshot đúng |

Bảng mô tả những trường hợp phổ biến của ví dụ. **“Deep-enough” phải gắn với đồ thị state thực tế**: nếu có grandchildren mutable bị chia sẻ, hàng ở tầng đó cần kiểm thêm.

Để viết test, không chỉ xác nhận `original != copy`. Hãy thử **mỗi hướng thay đổi**, ở **mỗi mutable level**, và quan sát **cả hai bản**.

## 9. Thí nghiệm số 5: mảng primitive một chiều

Mảng `int[]` là mutable object; nhưng các phần tử `int` là primitive values. `clone()` trên mảng tạo **một array object mới** và copy các values.

Tạo **`OneDimensionalArrayExperiment.java`**:

```java
import java.util.Arrays;

public class OneDimensionalArrayExperiment {
    public static void main(String[] args) {
        int[] original = {1, 2, 3};
        int[] alias = original;
        int[] copied = original.clone();

        System.out.println("alias=" + (original == alias));
        System.out.println("copy=" + (original == copied));

        original[0] = 9;
        System.out.println("after original=" +
                Arrays.toString(original) + " | " +
                Arrays.toString(copied));

        copied[1] = 8;
        System.out.println("after copy=" +
                Arrays.toString(original) + " | " +
                Arrays.toString(copied));
    }
}
```

```bash
javac OneDimensionalArrayExperiment.java
java OneDimensionalArrayExperiment
```

```text
alias=true
copy=false
after original=[9, 2, 3] | [1, 2, 3]
after copy=[9, 2, 3] | [1, 8, 3]
```

`int[]` không có mutable object elements bên trong, nên structural clone đã tách toàn bộ state của array trong thí nghiệm này. `Arrays.copyOf(original, original.length)` cũng có thể tạo array mới với values tương ứng.

**Không nhầm:** `Object.clone()` trên một class giữ field `int[]` mặc định chỉ copy **reference field**, khác với việc **gọi `clone()` trên chính mảng `int[]`**.

## 10. Thí nghiệm số 6: mảng 2D bị chia sẻ phần tử lồng nhau

`int[][]` là một outer array chứa **references tới inner `int[]` arrays**. Clone outer array chỉ mới là shallow copy.

Tạo **`TwoDimensionalArrayExperiment.java`**:

```java
import java.util.Arrays;

public class TwoDimensionalArrayExperiment {
    public static void main(String[] args) {
        int[][] original = {{1, 2}, {3}};
        int[][] copied = original.clone();

        System.out.println("outer shared=" + (original == copied));
        System.out.println("row shared=" + (original[0] == copied[0]));

        original[0][0] = 9;
        System.out.println("mutate original child=" +
                Arrays.deepToString(copied));

        copied[1][0] = 8;
        System.out.println("mutate copy child=" +
                Arrays.deepToString(original));

        original[0] = new int[] {7, 7};
        System.out.println("replace original row=" +
                Arrays.deepToString(original) + " | " +
                Arrays.deepToString(copied));
    }
}
```

```bash
javac TwoDimensionalArrayExperiment.java
java TwoDimensionalArrayExperiment
```

```text
outer shared=false
row shared=true
mutate original child=[[9, 2], [3]]
mutate copy child=[[9, 2], [8]]
replace original row=[[7, 7], [8]] | [[9, 2], [8]]
```

**Vì sao phép thử cuối quan trọng?**

- Ban đầu `original[0]` và `copied[0]` cùng trỏ một inner array.
- `original[0][0]=9` mutate inner array chung.
- Nhưng `original[0] = new int[]{7,7}` thay **reference slot của outer original**, không mutate inner array cũ.
- Vì hai outer arrays khác identity, việc thay row reference ở original **không thay slot tương ứng ở copied**.

Đây là ví dụ chính xác cho sự khác nhau giữa **thay tham chiếu tới child** và **thay state bên trong child**.

## 11. Thí nghiệm số 7: deep copy 2D array bằng cách clone từng row

Tạo **`DeepMatrixCopyExperiment.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

public class DeepMatrixCopyExperiment {
    static int[][] deepCopy(int[][] input) {
        Objects.requireNonNull(input);
        int[][] result = new int[input.length][];

        for (int i = 0; i < input.length; i++) {
            result[i] =
                    Objects.requireNonNull(input[i]).clone();
        }
        return result;
    }

    public static void main(String[] args) {
        int[][] original = {{1, 2}, {3}};
        int[][] copied = deepCopy(original);

        System.out.println(original == copied);
        System.out.println(original[0] == copied[0]);

        original[0][0] = 99;
        copied[1][0] = 88;

        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(copied));
    }
}
```

```bash
javac DeepMatrixCopyExperiment.java
java DeepMatrixCopyExperiment
```

```text
false
false
[[99, 2], [3]]
[[1, 2], [88]]
```

Hàm `deepCopy` tạo outer array và các inner arrays riêng. Với `int[][]`, đây là deep copy đủ cho các primitive elements.

**Không áp dụng mù quáng cho `MutableThing[][]`:** clone mỗi row vẫn chỉ copy references tới mutable elements. Để tách toàn bộ mutable state theo contract, còn phải copy từng mutable element hoặc dùng immutable representation.

## 12. Thí nghiệm số 8: object array — khác outer array nhưng cùng element

Tạo **`MutableElementArrayExperiment.java`**:

```java
public class MutableElementArrayExperiment {
    public static void main(String[] args) {
        StringBuilder originalText =
                new StringBuilder("A");
        StringBuilder[] original = {originalText};
        StringBuilder[] copied = original.clone();

        System.out.println("outer=" + (original == copied));
        System.out.println("element=" +
                (original[0] == copied[0]));

        copied[0].append("B");
        System.out.println("original element=" + original[0]);

        original[0] = new StringBuilder("C");
        System.out.println("original replaced=" + original[0]);
        System.out.println("copy retained=" + copied[0]);
    }
}
```

```bash
javac MutableElementArrayExperiment.java
java MutableElementArrayExperiment
```

```text
outer=false
element=true
original element=AB
original replaced=C
copy retained=AB
```

- `copied[0].append("B")` mutate **StringBuilder chung**; original nhìn thấy AB.
- `original[0] = new StringBuilder("C")` chỉ thay một **array slot ở original**; copied vẫn trỏ builder cũ AB.

Nếu cần **snapshot nội dung text** thay vì chia sẻ mutable builder, có thể chuyển mỗi StringBuilder sang immutable `String` khi copy. Một lần `StringBuilder.toString()` tạo String representation riêng theo API, giúp những lần `append` sau không đổi text snapshot.

## 13. Thí nghiệm số 9: copy sâu nội dung mảng object bằng value snapshot

Tạo **`TextSnapshotExperiment.java`**:

```java
import java.util.Arrays;

public class TextSnapshotExperiment {
    static String[] snapshot(StringBuilder[] input) {
        String[] output = new String[input.length];
        for (int i = 0; i < input.length; i++) {
            output[i] = input[i].toString();
        }
        return output;
    }

    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("A");
        StringBuilder second = new StringBuilder("B");
        StringBuilder[] original = {first, second};

        String[] copiedText = snapshot(original);
        first.append("1");
        second.append("2");

        System.out.println("original=" +
                Arrays.toString(original));
        System.out.println("snapshot=" +
                Arrays.toString(copiedText));

        copiedText[0] = "X";
        System.out.println("original after slot=" +
                Arrays.toString(original));
    }
}
```

```bash
javac TextSnapshotExperiment.java
java TextSnapshotExperiment
```

```text
original=[A1, B2]
snapshot=[A, B]
original after slot=[A1, B2]
```

Đây là **copy chuyển đổi representation** từ `StringBuilder[]` mutable sang `String[]` chứa immutable values. Nó không giữ nguyên loại phần tử; đây có thể là lựa chọn đúng khi mục tiêu là snapshot dữ liệu, nhưng không phải generic clone của mọi StringBuilder.

**Giới hạn:** Nếu builders đang bị sửa đồng thời trong lúc lấy `toString()`, phải quản lý ownership/synchronization; ví dụ chạy tuần tự và không tự bảo đảm snapshot atomic giữa nhiều mutable components.

## 14. Thí nghiệm số 10: sao chép outer `ArrayList` vẫn chia sẻ elements

Tạo **`ShallowListExperiment.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ShallowListExperiment {
    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("A");
        List<StringBuilder> original =
                new ArrayList<>(List.of(item));
        List<StringBuilder> copied =
                new ArrayList<>(original);

        System.out.println(original == copied);
        System.out.println(original.get(0) == copied.get(0));

        original.add(new StringBuilder("B"));
        System.out.println("sizes=" +
                original.size() + "," + copied.size());

        copied.get(0).append("X");
        System.out.println("original child=" + original.get(0));
        System.out.println("copy child=" + copied.get(0));
    }
}
```

```bash
javac ShallowListExperiment.java
java ShallowListExperiment
```

```text
false
true
sizes=2,1
original child=AX
copy child=AX
```

**Hai mức của thí nghiệm:**

1. `new ArrayList<>(original)` tạo list structure mới; `original.add(...)` không làm copied list dài ra.
2. Hai lists vẫn trỏ **cùng StringBuilder element đầu tiên**; mutate element từ copied thấy ở original.

**Không kết luận chỉ từ `sizes=2,1`** rằng mọi phần tử đã deep copied. Cần thử mutator của element và so `original.get(i)==copied.get(i)` khi identity của element có ý nghĩa.

## 15. Thí nghiệm số 11: `List.copyOf` chỉ khóa structure, không khóa element

Tạo **`CopyOfListExperiment.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CopyOfListExperiment {
    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("A");
        List<StringBuilder> source = new ArrayList<>();
        source.add(item);

        List<StringBuilder> snapshot = List.copyOf(source);
        source.add(new StringBuilder("B"));

        System.out.println("sizes=" +
                source.size() + "," + snapshot.size());

        item.append("X");
        System.out.println("nested=" + snapshot.get(0));

        try {
            snapshot.add(new StringBuilder("C"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("structure locked");
        }
    }
}
```

```bash
javac CopyOfListExperiment.java
java CopyOfListExperiment
```

```text
sizes=2,1
nested=AX
structure locked
```

`List.copyOf` tạo unmodifiable list với snapshot structure khi input là mutable `ArrayList`; nó **không deep-copy `StringBuilder` elements**.

Với `List<String>`, vì String immutable nên `List.copyOf` có thể là giải pháp hiệu quả để giữ một immutable collection value. Với `List<Mutable>`, muốn độc lập sâu hơn phải copy/convert mỗi mutable element.

**Bài học:** “Không gọi được `add`” không chứng minh **nội dung lồng nhau** không đổi.

## 16. Thí nghiệm số 12: unmodifiable view khác snapshot

Tạo **`UnmodifiableViewExperiment.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewExperiment {
    public static void main(String[] args) {
        List<String> original =
                new ArrayList<>(List.of("A"));

        List<String> view =
                Collections.unmodifiableList(original);
        List<String> snapshot =
                List.copyOf(original);

        original.add("B");

        System.out.println("original=" + original);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            view.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("view rejects add");
        }
    }
}
```

```bash
javac UnmodifiableViewExperiment.java
java UnmodifiableViewExperiment
```

```text
original=[A, B]
view=[A, B]
snapshot=[A]
view rejects add
```

- `Collections.unmodifiableList(original)` ngăn mutation **thông qua view**, nhưng vẫn phản ánh thay đổi backing list từ reference original.
- `List.copyOf(original)` tạo snapshot structure tương ứng tại thời điểm gọi (với mutable ArrayList input).
- Cả hai không làm các mutable element objects tự immutable nếu element type khác String.

**Không test `List.of(...) == List.of(...)` hay `List.copyOf(existing) != existing` như một lời hứa identity.** Những value-based collection factory outputs không bảo đảm một chiến lược reuse/allocate nhất định; kiểm semantics bằng contents và mutation behavior.

## 17. Thí nghiệm số 13: danh sách lồng nhau — shallow hai tầng

Tạo **`NestedListExperiment.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class NestedListExperiment {
    public static void main(String[] args) {
        List<String> students =
                new ArrayList<>(List.of("An"));

        List<List<String>> original =
                new ArrayList<>();
        original.add(students);

        List<List<String>> copied =
                new ArrayList<>(original);

        System.out.println("outer=" + (original == copied));
        System.out.println("inner=" +
                (original.get(0) == copied.get(0)));

        students.add("Binh");
        System.out.println("after inner mutation=" + copied);

        original.add(new ArrayList<>(List.of("Chi")));
        System.out.println("outer sizes=" +
                original.size() + "," + copied.size());
    }
}
```

```bash
javac NestedListExperiment.java
java NestedListExperiment
```

```text
outer=false
inner=true
after inner mutation=[[An, Binh]]
outer sizes=2,1
```

Chỉ sao chép outer `List<List<String>>` khiến inner lists vẫn shared. Mutate `students` lan tới copied. Nhưng thêm một **inner-list reference mới vào original outer** không làm copied outer đổi kích thước.

**Đây là mẫu cần phát hiện ở dữ liệu JSON-like**: Map chứa List, List chứa Map, graph nodes có child lists, DTO chứa nested structures. Mỗi tầng mutable phải được xét trong copy policy.

## 18. Thí nghiệm số 14: sao chép đủ sâu cho `List<List<String>>`

Tạo **`DeepNestedListExperiment.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DeepNestedListExperiment {
    static List<List<String>> deepSnapshot(
            List<List<String>> source) {
        List<List<String>> copied =
                new ArrayList<>();

        for (List<String> inner : source) {
            copied.add(List.copyOf(inner));
        }

        return List.copyOf(copied);
    }

    public static void main(String[] args) {
        List<String> students =
                new ArrayList<>(List.of("An"));
        List<List<String>> original =
                new ArrayList<>();
        original.add(students);

        List<List<String>> copy = deepSnapshot(original);

        students.add("Binh");
        original.add(new ArrayList<>(List.of("Chi")));

        System.out.println("original=" + original);
        System.out.println("copy=" + copy);

        try {
            copy.get(0).add("X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("inner snapshot locked");
        }
    }
}
```

```bash
javac DeepNestedListExperiment.java
java DeepNestedListExperiment
```

```text
original=[[An, Binh], [Chi]]
copy=[[An]]
inner snapshot locked
```

Tại sao đủ cho tình huống này?

- Mỗi inner list được `List.copyOf` thành unmodifiable snapshot.
- Outer list được `List.copyOf` khóa structure.
- Các elements là `String` immutable.
- Thay nguồn ngoài lẫn các inner lists không lan sang copy.

**Giới hạn:** Nếu inner list chứa `StringBuilder` thay vì String, cần thêm bước copy/convert từng element. Bài toán “deep” phải gắn với **loại mutable leaves**, không dừng ở generic depth 2.

## 19. Thí nghiệm số 15: Map structure copy nhưng value object vẫn chia sẻ

Tạo **`ShallowMapExperiment.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public class ShallowMapExperiment {
    public static void main(String[] args) {
        StringBuilder value = new StringBuilder("A");
        Map<String, StringBuilder> original =
                new HashMap<>();
        original.put("x", value);

        Map<String, StringBuilder> copied =
                new HashMap<>(original);

        System.out.println(original == copied);
        System.out.println(original.get("x") == copied.get("x"));

        original.put("y", new StringBuilder("B"));
        System.out.println("sizes=" +
                original.size() + "," + copied.size());

        copied.get("x").append("X");
        System.out.println("original value=" + original.get("x"));
        System.out.println("copy value=" + copied.get("x"));
    }
}
```

```bash
javac ShallowMapExperiment.java
java ShallowMapExperiment
```

```text
false
true
sizes=2,1
original value=AX
copy value=AX
```

HashMap constructor copy tạo **map container mới**, nhưng key/value references được chuyển sang mapping tương ứng, không tự copy StringBuilder. Vì vậy:

- Mutate map structure của original: copied structure riêng.
- Mutate shared StringBuilder value: original/copy cùng quan sát.

**Tránh in trực tiếp toàn Map có nhiều entries làm stdout mẫu nếu iteration order không được bảo đảm.** Ở đây in booleans, sizes và một key cụ thể để kết quả xác định.

## 20. Thí nghiệm số 16: deep snapshot cho Map values mutable

Tạo **`DeepMapExperiment.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public class DeepMapExperiment {
    static Map<String, String> snapshot(
            Map<String, StringBuilder> input) {
        Map<String, String> result = new HashMap<>();

        for (Map.Entry<String, StringBuilder> e :
                input.entrySet()) {
            result.put(e.getKey(), e.getValue().toString());
        }

        return Map.copyOf(result);
    }

    public static void main(String[] args) {
        StringBuilder value = new StringBuilder("A");
        Map<String, StringBuilder> original =
                new HashMap<>();
        original.put("x", value);

        Map<String, String> copy = snapshot(original);

        value.append("B");
        original.put("y", new StringBuilder("C"));

        System.out.println("original x=" + original.get("x"));
        System.out.println("copy x=" + copy.get("x"));
        System.out.println("copy has y=" + copy.containsKey("y"));

        try {
            copy.put("z", "D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("copy locked");
        }
    }
}
```

```bash
javac DeepMapExperiment.java
java DeepMapExperiment
```

```text
original x=AB
copy x=A
copy has y=false
copy locked
```

Thay representation từ mutable StringBuilder values sang immutable String values giúp cắt mutable aliases. Snapshot structure Map không có key mới thêm sau đó và không cho mutate mapping qua result.

**Nhớ:** `Map.copyOf` cấm null keys/values; nếu domain cho phép null, cần copy policy khác. Nếu keys là mutable objects thay vì String, cũng cần xem key-copy/equality contract.

## 21. Thí nghiệm số 17: hai copies cùng chia sẻ một component ở các nhánh khác nhau

Đôi khi alias không nằm ở field cùng tên. Hai objects có thể cùng tham chiếu component qua những nhánh graph khác nhau.

Giả sử:

```text
Order A ---> customer ---> Address X
Order B ---> shipping ---> Address X
```

Một phép copy chỉ sao chép Order nhưng giữ customer/shipping addresses theo reference có thể tạo **shared alias xuyên nhánh**. Khi Order B cập nhật shipping Address X, Order A nhìn thấy thay đổi trong customer address.

**Vì vậy kiểm thử graph phải xác định reachable mutable objects**, không chỉ nhìn tên fields. Một bảng ownership có ích:

| Object | Referenced by | Mutable? | Copy policy |
| --- | --- | --- | --- |
| `Order` root | original/copy riêng | Có thể | New root |
| `Address` | customer/shipping | Có | New component hoặc intentional sharing |
| `String` city | Address | Không | Có thể share |
| `List<LineItem>` | Order | Có thể | New list/snapshot |
| `LineItem` | List | Tùy type | Copy nếu mutable |

Nếu sharing là **chủ ý** (ví dụ một service/cache/collaborator shared), không gọi đó là deep copy của state nếu API không hứa độc lập ở component đó.

## 22. Thí nghiệm số 18: `Object.clone()` sao chép root nhưng giữ array field

`Object.clone()` thường được gọi trong một public override, với class implements `Cloneable`. Implementation gốc tạo **shallow field-for-field copy**.

Tạo **`ShallowObjectCloneExperiment.java`**:

```java
import java.util.Arrays;

final class Snapshot implements Cloneable {
    private final int[] data;

    Snapshot(int[] input) {
        data = input.clone();
    }

    void setAt(int index, int value) {
        data[index] = value;
    }

    @Override
    public Snapshot clone() {
        try {
            return (Snapshot) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    @Override
    public String toString() {
        return Arrays.toString(data);
    }
}

public class ShallowObjectCloneExperiment {
    public static void main(String[] args) {
        Snapshot original =
                new Snapshot(new int[] {1, 2});
        Snapshot copy = original.clone();

        System.out.println("root=" + (original == copy));

        original.setAt(0, 9);
        System.out.println("after original=" +
                original + " | " + copy);

        copy.setAt(1, 8);
        System.out.println("after copy=" +
                original + " | " + copy);
    }
}
```

```bash
javac ShallowObjectCloneExperiment.java
java ShallowObjectCloneExperiment
```

```text
root=false
after original=[9, 2] | [9, 2]
after copy=[9, 8] | [9, 8]
```

**Kết luận:** Original và cloned Snapshot là hai objects khác nhau, nhưng cùng giữ `data` array reference được copy từ source. Constructor đã copy array input của Snapshot **không làm `super.clone()` tự copy sâu**.

Lưu ý: `Cloneable` chỉ là marker interface; nó **không khai báo `clone()` public**. `Object.clone()` là protected và có checked exception. Ví dụ cung cấp public override để caller được gọi.

## 23. Thí nghiệm số 19: deep clone thay mutable field sau `super.clone()`

Nếu mutable field **không final**, override có thể:

1. Gọi `super.clone()` tạo shallow root.
2. Gán clone một component copy riêng.
3. Trả cloned root sau khi hoàn thành.

Tạo **`DeepObjectCloneExperiment.java`**:

```java
import java.util.Arrays;

final class Snapshot implements Cloneable {
    private int[] data;

    Snapshot(int[] input) {
        data = input.clone();
    }

    void setAt(int index, int value) {
        data[index] = value;
    }

    @Override
    public Snapshot clone() {
        try {
            Snapshot copy = (Snapshot) super.clone();
            copy.data = data.clone();
            return copy;
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    @Override
    public String toString() {
        return Arrays.toString(data);
    }
}

public class DeepObjectCloneExperiment {
    public static void main(String[] args) {
        Snapshot original =
                new Snapshot(new int[] {1, 2});
        Snapshot copy = original.clone();

        original.setAt(0, 9);
        copy.setAt(1, 8);

        System.out.println("original=" + original);
        System.out.println("copy=" + copy);
    }
}
```

```bash
javac DeepObjectCloneExperiment.java
java DeepObjectCloneExperiment
```

```text
original=[9, 2]
copy=[1, 8]
```

Ở đây, `copy.data = data.clone()` tạo array độc lập nên hai hướng mutation không lan.

**Góc cạnh `final`:** Nếu khai báo `private final int[] data`, phép gán `copy.data = ...` trong clone override không hợp lệ. Có thể chọn **copy constructor** hoặc một implementation copy khác bằng `new`, nơi constructor được phép khởi tạo final field, thay vì clone-and-patch.

**Góc cạnh bảo mật/lifecycle:** Không công bố object clone cho thread hoặc registry khác trước khi sửa xong các references cần thiết.

## 24. Thí nghiệm số 20: constructor copy tường minh với `final` field

Tạo **`FinalFieldCopyExperiment.java`**:

```java
import java.util.Arrays;

final class Data {
    private final int[] values;

    Data(int[] values) {
        this.values = values.clone();
    }

    Data(Data source) {
        this.values = source.values.clone();
    }

    void setAt(int index, int value) {
        values[index] = value;
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class FinalFieldCopyExperiment {
    public static void main(String[] args) {
        Data original = new Data(new int[] {1, 2});
        Data copy = new Data(original);

        original.setAt(0, 9);
        copy.setAt(1, 8);

        System.out.println("original=" + original);
        System.out.println("copy=" + copy);
    }
}
```

```bash
javac FinalFieldCopyExperiment.java
java FinalFieldCopyExperiment
```

```text
original=[9, 2]
copy=[1, 8]
```

`private final int[] values` giữ tham chiếu không được gán lại sau construction, nhưng **Data vẫn là mutable class** do `setAt`. Hai instances chỉ độc lập vì mỗi constructor tạo array riêng.

**Đừng nhầm:** “Copy sâu thành công” không đồng nghĩa “bản sao immutable”. Nếu muốn immutable, ngoài defensive copy còn phải không expose mutators và không lộ array reference bên trong.

## 25. Thí nghiệm số 21: constructor không chạy trong đường `Object.clone()`

Sự khác biệt này rất hữu ích để suy luận về validations/side effects khi copy.

Tạo **`CloneVsConstructorExperiment.java`**:

```java
final class Ticket implements Cloneable {
    private static int constructorCalls;

    private final int number;

    Ticket(int number) {
        constructorCalls++;
        this.number = number;
    }

    Ticket copy() {
        return new Ticket(number);
    }

    @Override
    public Ticket clone() {
        try {
            return (Ticket) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    static int calls() {
        return constructorCalls;
    }
}

public class CloneVsConstructorExperiment {
    public static void main(String[] args) {
        Ticket original = new Ticket(7);
        System.out.println("after original=" + Ticket.calls());

        Ticket cloned = original.clone();
        System.out.println("after clone=" + Ticket.calls());

        Ticket copied = original.copy();
        System.out.println("after copy=" + Ticket.calls());

        System.out.println(original == cloned);
        System.out.println(original == copied);
    }
}
```

```bash
javac CloneVsConstructorExperiment.java
java CloneVsConstructorExperiment
```

```text
after original=1
after clone=1
after copy=2
false
false
```

`Object.clone()` tạo object mới mà không chạy Ticket constructor; `copy()` gọi `new Ticket(...)` nên counter tăng.

**Không khẳng định rằng mọi method tên `clone()` đều bỏ qua constructor**: một override tự viết `return new Ticket(...);` sẽ gọi constructor. Kết luận ở đây đúng với **đường gọi `super.clone()`/Object.clone()`**.

Nếu constructor của class có validation hoặc cấp phát resource, phải xét clone contract kỹ: clone field-for-field không mặc định thực thi lại những quy trình ấy.

## 26. Thí nghiệm số 22: copy một record chứa array không tự là deep

Record trên Java 17 có component fields final, nhưng một array component **vẫn mutable**.

Tạo **`RecordArrayAliasExperiment.java`**:

```java
import java.util.Arrays;

record Measurements(int[] values) {
}

public class RecordArrayAliasExperiment {
    public static void main(String[] args) {
        int[] source = {1, 2};

        Measurements original = new Measurements(source);
        Measurements copied = new Measurements(
                original.values());

        System.out.println(original == copied);
        System.out.println(
                original.values() == copied.values());

        source[0] = 9;
        System.out.println("original=" +
                Arrays.toString(original.values()));
        System.out.println("copy=" +
                Arrays.toString(copied.values()));

        copied.values()[1] = 8;
        System.out.println("source=" +
                Arrays.toString(source));
    }
}
```

```bash
javac RecordArrayAliasExperiment.java
java RecordArrayAliasExperiment
```

```text
false
true
original=[9, 2]
copy=[9, 2]
source=[9, 8]
```

Hai record instances khác identity nhưng cùng giữ `source` array. Không có defensive copying trong record canonical constructor hoặc generated accessor. Field final trong record chỉ cố định reference; không khóa array elements.

**Cách sửa:** Compact constructor clone array, tự viết accessor trả clone và, nếu cần value equality theo array contents, override `equals`/`hashCode` tương ứng. Record-generated equals cho array component không tự deep-compare nội dung.

## 27. Thí nghiệm số 23: record có defensive copying ở hai ranh giới

Tạo **`SafeRecordCopyExperiment.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record SafeMeasurements(int[] values) {
    SafeMeasurements {
        values = Objects.requireNonNull(values).clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    public int at(int index) {
        return values[index];
    }
}

public class SafeRecordCopyExperiment {
    public static void main(String[] args) {
        int[] source = {1, 2};

        SafeMeasurements original =
                new SafeMeasurements(source);
        SafeMeasurements copied =
                new SafeMeasurements(original.values());

        source[0] = 9;
        int[] returned = copied.values();
        returned[1] = 8;

        System.out.println("original=" +
                Arrays.toString(original.values()));
        System.out.println("copy=" +
                Arrays.toString(copied.values()));
        System.out.println(original.at(0));
    }
}
```

```bash
javac SafeRecordCopyExperiment.java
java SafeRecordCopyExperiment
```

```text
original=[1, 2]
copy=[1, 2]
1
```

- Compact constructor thay parameter bằng `values.clone()` trước khi field được khởi tạo theo record rules.
- Accessor trả clone, không lộ mảng nội bộ.
- Hai record instances giữ separate mutable arrays; source bên ngoài không mutate được internal state.

**Cảnh báo:** Generated `equals`/`hashCode` của record vẫn dựa trên array component identity semantics, không tự so giá trị `[1,2]`. **Bất biến** và **logical equality** là hai contract phải kiểm riêng.

## 28. Thí nghiệm số 24: phép copy có thể làm mất subtype nếu gọi constructor của class cha

Khi `source` có runtime class là subclass, một copy constructor trên class cha bằng `new Base(source)` **luôn tạo Base instance**, không tự giữ subclass fields.

Tạo **`SubtypeCopyExperiment.java`**:

```java
class Animal {
    private final String name;

    Animal(String name) {
        this.name = name;
    }

    Animal(Animal source) {
        this.name = source.name;
    }

    String name() {
        return name;
    }
}

final class Dog extends Animal {
    private final String breed;

    Dog(String name, String breed) {
        super(name);
        this.breed = breed;
    }

    String breed() {
        return breed;
    }
}

public class SubtypeCopyExperiment {
    public static void main(String[] args) {
        Animal original = new Dog("Milo", "Collie");
        Animal copied = new Animal(original);

        System.out.println(original.getClass().getSimpleName());
        System.out.println(copied.getClass().getSimpleName());
        System.out.println(original.name().equals(copied.name()));
    }
}
```

```bash
javac SubtypeCopyExperiment.java
java SubtypeCopyExperiment
```

```text
Dog
Animal
true
```

**Kết luận:** Copy constructor đã copy field `name` theo contract Animal, nhưng không giữ runtime subtype Dog/breed. Nếu API hứa polymorphic copy, có thể định nghĩa `abstract Base copy()` và để mỗi concrete subclass tự copy.

Ngược lại, `Object.clone()` theo field-copy contract thường tạo object **cùng runtime class với source**, nhưng vẫn shallow đối với nested mutable fields. **Subtype preservation không chứng minh deep copying.**

## 29. Thí nghiệm số 25: polymorphic copy không cần `Cloneable`

Tạo **`PolymorphicCopyExperiment.java`**:

```java
abstract class Animal {
    private final String name;

    Animal(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    abstract Animal copy();
}

final class Dog extends Animal {
    private final String breed;

    Dog(String name, String breed) {
        super(name);
        this.breed = breed;
    }

    @Override
    Dog copy() {
        return new Dog(name(), breed);
    }

    String breed() {
        return breed;
    }
}

public class PolymorphicCopyExperiment {
    public static void main(String[] args) {
        Animal original = new Dog("Milo", "Collie");
        Animal copy = original.copy();

        System.out.println(original == copy);
        System.out.println(copy.getClass().getSimpleName());

        if (copy instanceof Dog dog) {
            System.out.println(dog.breed());
        }
    }
}
```

```bash
javac PolymorphicCopyExperiment.java
java PolymorphicCopyExperiment
```

```text
false
Dog
Collie
```

Ở đây `copy()` là method override đa hình, có covariant return type Dog. Nó gọi constructor bình thường và giữ subtype vì **class Dog chủ động xây copy Dog**.

Một interface `Copyable<T> { T copy(); }` cũng có thể tạo contract tương tự. Đây là **API ứng dụng tự định nghĩa**, không phải tự động được cung cấp bởi marker `Cloneable`.

Với subclass có mutable fields mới, lớp ấy phải tự bảo đảm copy policy của từng field.

## 30. Thí nghiệm số 26: deep copy một graph có chu trình

Deep copying graphs phức tạp phải xử lý **cycles** và **shared identity topology**. Không thể chỉ đệ quy `new Node(copy(next))` mà không nhớ objects đã thăm: graph có cycle có thể gây đệ quy vô hạn.

Ta dùng `IdentityHashMap<Node,Node>`, vì keys cần phân biệt **chính reference identity**, không phụ thuộc bất kỳ `equals()` nào.

Tạo **`CyclicGraphCopyExperiment.java`**:

```java
import java.util.IdentityHashMap;
import java.util.Map;

final class Node {
    final String name;
    Node next;

    Node(String name) {
        this.name = name;
    }
}

public class CyclicGraphCopyExperiment {
    static Node copyGraph(Node source, Map<Node, Node> seen) {
        if (source == null) {
            return null;
        }

        Node existing = seen.get(source);
        if (existing != null) {
            return existing;
        }

        Node copy = new Node(source.name);
        seen.put(source, copy);
        copy.next = copyGraph(source.next, seen);
        return copy;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        a.next = b;
        b.next = a;

        Node copy = copyGraph(a, new IdentityHashMap<>());

        System.out.println(copy != a);
        System.out.println(copy.next != b);
        System.out.println(copy.next.next == copy);
        System.out.println(a.next.next == a);
        System.out.println(copy.name + copy.next.name);
    }
}
```

```bash
javac CyclicGraphCopyExperiment.java
java CyclicGraphCopyExperiment
```

```text
true
true
true
true
AB
```

**Cách thuật toán bảo toàn cycle:**

1. Tạo Node A copy.
2. Ghi mapping `A_original -> A_copy` **trước khi** copy `next`.
3. Đi tới B, tạo B copy, ghi mapping.
4. B.next trỏ lại A_original; map đã có A_copy nên dùng lại.
5. Kết quả copy graph có A_copy↔B_copy, tách khỏi A_original↔B_original.

Đây là ví dụ có **mutable link field `next`** để kết nối graph theo hai giai đoạn. Với graph có `final` links hoặc constructor invariants nghiêm ngặt, cần một chiến lược xây dựng khác, không thể gán field sau constructor như ví dụ.

## 31. Thí nghiệm số 27: bảo toàn sharing trong graph, không nhân đôi nhánh chung

Graph gốc có thể có **một child shared bởi hai fields**:

```text
root.left ──┐
            ├──> Child X
root.right ─┘
```

Nếu copy child hai lần, result không giữ quan hệ `copy.left == copy.right` nữa. Điều này có thể vi phạm contract khi sharing là một phần ngữ nghĩa.

Tạo **`SharedGraphCopyExperiment.java`**:

```java
import java.util.IdentityHashMap;
import java.util.Map;

final class Node {
    final String id;
    Node left;
    Node right;

    Node(String id) {
        this.id = id;
    }
}

public class SharedGraphCopyExperiment {
    static Node copy(Node source, Map<Node, Node> visited) {
        if (source == null) {
            return null;
        }
        Node existing = visited.get(source);
        if (existing != null) {
            return existing;
        }

        Node result = new Node(source.id);
        visited.put(source, result);
        result.left = copy(source.left, visited);
        result.right = copy(source.right, visited);
        return result;
    }

    public static void main(String[] args) {
        Node shared = new Node("X");
        Node root = new Node("root");
        root.left = shared;
        root.right = shared;

        Node duplicate = copy(root, new IdentityHashMap<>());

        System.out.println(root.left == root.right);
        System.out.println(duplicate.left == duplicate.right);
        System.out.println(duplicate.left != shared);
        System.out.println(duplicate.id);
    }
}
```

```bash
javac SharedGraphCopyExperiment.java
java SharedGraphCopyExperiment
```

```text
true
true
true
root
```

Map giúp clone giữ **cùng topology sharing** và đồng thời tạo distinct mutable Node instances so với source. Đây là bài toán sâu hơn việc copy một `int[][]` đơn giản.

**Không dùng `HashMap<Node,Node>` tùy tiện nếu `Node.equals()` có thể coi hai nodes khác identity là equal.** Trong graph copy cần ghi nhớ theo **instance identity**, `IdentityHashMap` thể hiện ý định rõ.

## 32. Tại sao `equals()` và `hashCode()` không phải bằng chứng đủ của deep copy?

Một value class có thể override equals để so nội dung. Hai objects equal về value vẫn có thể chia sẻ mutable array:

```java
System.out.println(original.equals(copy)); // Có thể true.
System.out.println(original == copy);       // Có thể false.
```

Hai dòng là **mảnh minh họa**; kết quả phụ thuộc class implementation.

Vì vậy cần kiểm **ít nhất ba trục**:

1. **Root identity**: object mới hay alias?
2. **Logical equality/state**: nội dung bắt đầu có tương đương không?
3. **Mutation isolation**: sửa original/copy/nested objects có lan không?

Hash code cũng không chứng minh deep copy: hai unequal objects có thể hash trùng, hai equal objects phải hash giống nếu contract đúng, nhưng hash không nói component references có bị share hay không.

### Bộ kiểm gợi ý

```text
Check A: original != copy (nếu API hứa instance mới)
Check B: same initial logical values
Check C: mutate original root field; copy unaffected
Check D: mutate copy root field; original unaffected
Check E: mutate original mutable child; copy unaffected
Check F: mutate copy mutable child; original unaffected
Check G: mutate original nested grandchild; copy unaffected
Check H: mutate constructor input retained by caller
Check I: mutate getter-returned mutable data
```

C/G/H/I có thể không áp dụng khi class có toàn immutable components hoặc getter chỉ cung cấp value queries. **Test theo contract**, không ép một mẫu kiểm cho mọi loại object.

## 33. Thí nghiệm số 28: tự động báo PASS/FAIL với Java `AssertionError`

Một chương trình thực nghiệm nên kiểm các điều kiện **có ý nghĩa** và báo FAIL ngay nếu sai, thay vì chỉ in vài giá trị để người đọc tự đoán.

Tạo **`CopyIsolationSelfTest.java`**:

```java
import java.util.Arrays;

final class Payload {
    private final int[] values;

    Payload(int[] input) {
        values = input.clone();
    }

    Payload(Payload source) {
        values = source.values.clone();
    }

    void set(int index, int value) {
        values[index] = value;
    }

    int[] snapshot() {
        return values.clone();
    }
}

public class CopyIsolationSelfTest {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        int[] input = {1, 2};
        Payload original = new Payload(input);
        Payload copy = new Payload(original);

        check(original != copy, "root identity");

        input[0] = 99;
        check(Arrays.equals(original.snapshot(),
                new int[] {1, 2}), "input alias");

        original.set(0, 9);
        check(copy.snapshot()[0] == 1,
                "original -> copy isolation");

        copy.set(1, 8);
        check(original.snapshot()[1] == 2,
                "copy -> original isolation");

        int[] external = copy.snapshot();
        external[0] = 77;
        check(copy.snapshot()[0] == 1,
                "getter alias isolation");

        System.out.println("copy isolation PASS");
    }
}
```

```bash
javac CopyIsolationSelfTest.java
java CopyIsolationSelfTest
```

```text
copy isolation PASS
```

Ở đây các assertions không phụ thuộc JVM flag `-ea` vì helper chủ động ném `AssertionError`. Các kiểm tra có mục tiêu:

- Root identity khác.
- Constructor không lộ alias tới input.
- Mutation hai hướng không lan.
- Getter trả snapshot tách mutable reference.

**Giới hạn:** Self-test chỉ bao phủ `Payload` có một `int[]`. Nếu thêm một `List<MutableItem>` trong phiên bản tương lai, phải bổ sung tests cho nested list/elements.

## 34. Thí nghiệm số 29: viết bảng kết quả theo thời điểm

Trong một bài review, thay vì ghi “shallow”/“deep” chỉ bằng trực giác, hãy lập bảng có trạng thái **trước và sau từng phép sửa**.

Ví dụ với `ShallowAddressExperiment`:

| Thời điểm | Phép tác động | Original | Copy | Quan sát |
| --- | --- | --- | --- | --- |
| T0 | Vừa copy | `An@Hue` | `An@Hue` | Nội dung giống |
| T1 | Rename original | `Binh@Hue` | `An@Hue` | Root field riêng |
| T2 | Move copy's address | `Binh@Da Nang` | `An@Da Nang` | Nested mutable child shared |

Với `DeepAddressExperiment`:

| Thời điểm | Phép tác động | Original | Copy | Quan sát |
| --- | --- | --- | --- | --- |
| T0 | Vừa copy | `An@Hue` | `An@Hue` | Nội dung giống |
| T1 | Mutate original address | `An@Da Nang` | `An@Hue` | Child objects riêng |
| T2 | Mutate copy address | `An@Da Nang` | `An@Ha Noi` | Độc lập cả chiều ngược lại |

**Phương pháp thực nghiệm có độ tin cậy cao:** mỗi thí nghiệm bắt đầu từ trạng thái biết trước; ghi rõ từng mutation; kiểm cả root, child và ggf. grandchild; tránh trộn nhiều hành động mà không ghi dấu thời điểm.

## 35. Khi nào nên cố tình chia sẻ reference trong bản sao?

Không phải mọi shared reference đều là lỗi.

**Chia sẻ an toàn thường gặp:**

- `String`, `Integer`, `LocalDate`, `Instant` và các immutable values khác.
- Một immutable collection snapshot có toàn immutable elements.
- Một service stateless/shared collaborator theo contract.
- Cấu trúc persistent immutable data structure có structural sharing.

**Chia sẻ cần phân tích kỹ:**

- Mutable caches hoặc memoization.
- `ArrayList`/`HashMap`/arrays.
- `StringBuilder`, `Date`.
- Resource handles như sockets, streams, database connections.
- Những objects chứa callbacks hoặc threads.
- Một mutable entity có business identity riêng.

Nếu copy chỉ giữ reference tới immutable component, dữ liệu vẫn độc lập về observable state. Nếu copy giữ reference tới live resource, “sửa” hoặc đóng resource ở một wrapper có thể phá wrapper khác — cần quy tắc resource ownership riêng chứ không thể chỉ nói deep/shallow.

## 36. Thử nghiệm sao chép qua constructor vs `Object.clone()`

| Điểm khác biệt | Copy constructor dùng `new` | Override dựa trên `super.clone()` |
| --- | --- | --- |
| Có chạy constructor mới | Có | Không ở cơ chế Object.clone |
| Definite assignment cho fields `final` | Theo constructor flow | Fields final được copy field-for-field |
| Copy reference mutable | Tùy code; có thể chủ động copy | Mặc định shallow |
| Kiểm validation lại | Có nếu constructor gọi logic validation | Không tự chạy constructor validations |
| Public API | Có thể tường minh `new T(source)` | Object.clone protected, cần expose override |
| Checked exception | Theo constructor policy | Cơ sở khai `CloneNotSupportedException` |
| Runtime subtype | `new Base(source)` tạo Base | Object.clone tạo cùng runtime class với source |
| Test mutation isolation | Cần | Cần |
| Dễ audit nested copy | Thường rõ từng field | Cần đọc override/hierarchy |
| Với mutable `final` field | Có thể gán defensive copy trong constructor | Khó clone-and-patch field final |

**Không kết luận clone “tốt/xấu” chỉ từ bảng.** Nếu code cần clone legacy API, hiểu rõ contract và viết tests tương ứng. Nếu thiết kế API Java mới có mutable nested state và invariants, explicit copy thường dễ thể hiện chính sách hơn.

## 37. Cảnh báo riêng về constructor input đang bị sửa đồng thời

Các thí nghiệm trên **chạy tuần tự**: input arrays/lists ổn định trong lúc constructor hoặc copy method đọc/copy.

Nếu thread khác sửa source đồng thời trong khi copy:

- Có thể gặp dữ liệu không nhất quán giữa các fields/elements.
- Với mutable collections không concurrent-safe, iterator/copy có thể thất bại hoặc quan sát race theo API.
- Nếu validation diễn ra trước copy, source có thể đổi giữa hai bước.
- `final` fields của result không tự biến việc lấy snapshot từ source thành một thao tác atomic.

**Cách làm an toàn:** xác định ownership hoặc synchronization protocol; bảo đảm source state ổn định trong khi snapshot; validate **chính snapshot** được lưu. Nếu cần snapshot concurrent, chọn concurrent data structure/API có contract cụ thể.

Đừng dùng stress test chạy vài lần mà không thấy lỗi để “chứng minh” thread safety. Bài này tập trung vào logic alias graph của một snapshot tuần tự.

## 38. Cảnh báo copy object có resource, ID hoặc lifecycle

Một object có thể giữ:

- Session ID / database-generated ID.
- Timestamp creation.
- File/socket/stream handle.
- A thread/lock/callback.
- Registry membership hoặc external lease.

Sao chép toàn bộ fields bằng Object.clone có thể vô tình **giữ cùng ID hoặc resource handle**. Nhưng copy constructor cũng có thể gây lỗi nếu người viết chủ động copy sai.

Trước khi copy, xác định:

1. Field nào phải giữ nguyên?
2. Field nào phải tạo ID mới?
3. Resource nào được chia sẻ, resource nào phải mở mới hoặc không được copy?
4. Ai có quyền `close`?
5. Có cần giữ subtype và invariants của class hierarchy?
6. Có external side effects từ constructor/factory không?
7. Copy có nghĩa snapshot “giá trị” hay tạo một thực thể nghiệp vụ mới?

Nếu không có semantics copy hợp lý cho live object, có thể **cấm copy** và chỉ copy immutable configuration riêng.

## 39. Sai lầm thường gặp trong thí nghiệm

| Sai lầm | Vì sao sai | Cách kiểm/sửa |
| --- | --- | --- |
| “`b=a` là copy” | Hai references cùng root | In `a==b` và mutate |
| “`a!=b` chứng minh deep copy” | Nested child có thể shared | Kiểm `a.child==b.child` và mutate |
| “Các fields ban đầu giống nhau nên độc lập” | Same values không nói alias | Sửa mutable fields hai chiều |
| “Sửa root field không lan nên deep” | Mutable child vẫn có thể share | Mutate child/grandchild |
| “Mảng `clone()` luôn deep” | Object arrays và 2D arrays shallow ở references | Kiểm inner array/element identity |
| “New ArrayList copy clone cả elements” | Chỉ copy structure | Mutate StringBuilder element |
| “List.copyOf làm mutable elements bất biến” | Structure unmodifiable, elements có thể mutable | Mutate element alias |
| “unmodifiableList là snapshot” | View thấy backing changes | Mutate source list |
| “Getter trả copy nên constructor không alias” | Input alias vẫn có thể giữ | Mutate original input |
| “Constructor copy nên getter không alias” | Getter có thể trả internal mutable reference | Mutate getter result |
| “final field làm array immutable” | final chỉ giữ reference | Mutate `array[i]` |
| “Record tự deep copy array” | Record constructor/accessor mặc định giữ alias | Mutate input và accessor |
| “record equals so array contents” | Array component dùng identity equality | Custom Arrays.equals/hash |
| “`Object.clone()` gọi lại constructor” | Object.clone bỏ qua constructor | Counter experiment |
| “Cloneable tự tạo public clone” | Marker không có method | Public override hoặc copy method |
| “copy constructor giữ runtime subtype” | `new Base` tạo Base | Polymorphic copy |
| “Giữ subtype là deep copy” | Mutable descendant fields vẫn có thể share | Audit per-subclass fields |
| “Hai hashCode bằng nhau là một object” | Collisions hợp lệ | Dùng `==` cho identity |
| “Hai objects equals thì không share mutable refs” | Equality và alias isolation khác nhau | Mutate nested state |
| “Copy graph chỉ cần recursion” | Cycles vô hạn/shared topology mất | IdentityHashMap visited |
| “Deep copy luôn tạo mọi immutable object mới” | Sharing immutable state có thể an toàn | Định nghĩa theo observable state |
| “Trật tự HashMap/HashSet toString luôn cố định” | Không có bảo đảm chung | Kiểm size/key/value xác định |
| “Stress test qua một lần là đủ thread-safe” | Race timing-dependent | Protocol đồng bộ/ownership |
| “Clone live resource tự tạo handle mới” | Field copy thường giữ reference | Resource-specific contract |

## 40. Bài tập tự luyện kèm đáp án

**Câu 1.** `Box b=a;` sau `b.set(10)`, a có đổi không?

*Đáp án:* Có nếu setter mutate chính object và hai references cùng trỏ object ấy. Không có bản sao.

**Câu 2.** Copy constructor chỉ copy primitive fields thì `original != copy` và sửa từng phía có lan không?

*Đáp án:* Hai root khác identity; với instance primitive fields riêng, sửa phía này không làm phía kia đổi.

**Câu 3.** Hai Customer objects khác nhau nhưng dùng chung Address mutable. Sửa Customer.name có nhất thiết lan không?

*Đáp án:* Không nếu mỗi Customer giữ name reference field riêng; gán lại name field không đổi Address. Nhưng mutate Address chung thì lan.

**Câu 4.** Vì sao `int[] cloned = original.clone()` độc lập về contents một chiều?

*Đáp án:* Clone tạo array mới và copy primitive values sang slots riêng.

**Câu 5.** Vì sao `int[][] cloned = original.clone()` vẫn shallow?

*Đáp án:* Inner arrays là references được copy, không tạo inner arrays mới.

**Câu 6.** Khi `StringBuilder[]` được clone, gọi `cloned[0].append("X")` có thể đổi original không?

*Đáp án:* Có nếu element 0 vẫn là same StringBuilder instance.

**Câu 7.** `new ArrayList<>(other)` có tạo list object mới không? Có clone element objects không?

*Đáp án:* Có list structure mới; không tự clone element objects.

**Câu 8.** `Collections.unmodifiableList(source)` ngăn `source.add(...)` không?

*Đáp án:* Không. Nó là unmodifiable view; backing source còn mutable.

**Câu 9.** `List.copyOf(mutableArrayList)` có snapshot list structure không?

*Đáp án:* Có theo semantics khi mutable source; nhưng không deep-copy mutable elements.

**Câu 10.** Dùng `Map.copyOf` với map values là mutable lists đã deep copy chưa?

*Đáp án:* Chưa. Phải copy từng nested mutable list/value thích hợp.

**Câu 11.** Nếu original và copy có cùng String reference, deep copy bị sai không?

*Đáp án:* Chưa chắc. String immutable; chia sẻ có thể an toàn nếu copy contract cho phép.

**Câu 12.** `super.clone()` có gọi constructor của class được clone không?

*Đáp án:* Không theo mechanism Object.clone. Một override tự dùng `new` thì lại gọi constructor.

**Câu 13.** Có thể patch `private final int[] data` thành array mới sau `super.clone()` không?

*Đáp án:* Không qua ordinary assignment ở clone method; copy constructor có thể khởi tạo final field phù hợp.

**Câu 14.** Tại sao kiểm `original.equals(copy)` chưa đủ chứng minh deep copy?

*Đáp án:* Equality do class định nghĩa, có thể true dù đang chia sẻ mutable references.

**Câu 15.** Nếu copy cần giữ runtime subtype khi source có kiểu Animal và thực tế là Dog thì sao?

*Đáp án:* Dùng polymorphic copy method hoặc contract clone phù hợp; `new Animal(source)` chỉ tạo Animal.

**Câu 16.** Một graph A→B→A copy recursive thiếu visited map gây nguy cơ gì?

*Đáp án:* Đệ quy vòng lặp vô hạn hoặc stack overflow.

**Câu 17.** Vì sao visited map trong graph copy nên kiểm identity thay vì value equals?

*Đáp án:* Hai nodes có thể equal về value nhưng khác identity; deep copy topology cần phân biệt actual instances.

**Câu 18.** Hai branches cùng trỏ một child ở source có nhất thiết giữ sharing trong copy không?

*Đáp án:* Tùy contract. Nếu cần bảo toàn topology, copy nên dùng chung child clone trong hai branches, không clone thành hai children độc lập.

**Câu 19.** Một clone của object giữ Socket có tự tạo Socket khác không?

*Đáp án:* Không thể mặc định. Shallow field copy giữ cùng Socket reference; cần resource-specific factory/ownership rule.

**Câu 20.** Kiểm đúng một chiều mutate original→copy đã đủ chưa?

*Đáp án:* Không. Cần mutate copy→original và nested components, thêm input/getter aliases tùy API.

## 41. Checklist thực nghiệm trước khi kết luận

- [ ] Đã phân biệt phép gán reference với object copy?
- [ ] Đã kiểm root identity bằng `==` khi contract hứa copy mới?
- [ ] Đã ghi nhận logical data của hai bản **trước khi sửa**?
- [ ] Đã sửa một field root của original và đọc copy?
- [ ] Đã sửa một field root của copy và đọc original?
- [ ] Đã sửa một mutable child qua original?
- [ ] Đã sửa một mutable child qua copy?
- [ ] Đã kiểm grandchild/nested list/array nếu có?
- [ ] Đã kiểm child reference identity khi hữu ích?
- [ ] Đã phân biệt thay reference slot với mutate referenced object?
- [ ] Nếu copy mảng 2D, đã kiểm cả outer và inner arrays?
- [ ] Nếu copy object array, đã xét mutable elements?
- [ ] Nếu copy collection, đã phân biệt structure và element sharing?
- [ ] Nếu dùng `List.copyOf`/`Map.copyOf`, đã xét nested mutable components?
- [ ] Nếu dùng unmodifiable view, đã kiểm backing collection bị mutate?
- [ ] Nếu class nhận mutable input, đã thử sửa input sau constructor?
- [ ] Nếu class trả mutable data, đã thử sửa getter output?
- [ ] Nếu dùng `Object.clone()`, đã xác minh marker/access/method contract?
- [ ] Đã kiểm Object.clone shallow và constructor-bypass khi ảnh hưởng logic?
- [ ] Có mutable `final` field khiến clone-and-patch khó hơn không?
- [ ] Có yêu cầu giữ runtime subtype không?
- [ ] Có yêu cầu giữ graph cycles hoặc shared topology không?
- [ ] Có resource, ID hoặc external lifecycle không phù hợp field copy?
- [ ] Đã tránh dựa vào raw hash values hoặc unordered collection iteration?
- [ ] Có method self-test `check` với exception khi thất bại?
- [ ] Đã định nghĩa rõ những sharing **được phép** của immutable components?
- [ ] Đã xác định quyền sở hữu/synchronization khi copy dữ liệu bị mutate đồng thời?
- [ ] Các ví dụ Java 17+ có đúng tên file và public class, lệnh `javac`/`java` và stdout?

---

**Ghi nhớ cuối bài:** Muốn biết bản sao có độc lập hay không, **phải thực nghiệm thay đổi trạng thái ở cả hai hướng và mọi tầng mutable liên quan**. `original != copy` chỉ chứng minh root objects khác nhau; sao chép nông vẫn có thể chia sẻ array, list, map hoặc một element mutable. Hãy quan sát riêng **thay field ngoài cùng**, **mutate container**, **mutate element/child lồng nhau**, rồi thử **input alias và getter alias**. Với dữ liệu đơn giản, copy constructor, `array.clone()` hoặc `Arrays.copyOf` có thể đủ; với 2D arrays, nested collections và graph có cycles/sharing, phải định nghĩa độ sâu và topology rõ ràng. `Object.clone()` mặc định shallow và không chạy constructor; copy tường minh dễ thể hiện mức độ sao chép hơn khi có mutable state và invariants. **Một copy đúng là copy đáp ứng hợp đồng quan sát được đã được kiểm chứng — không chỉ copy có tên gọi “deep”.**