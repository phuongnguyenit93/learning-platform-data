# Bất biến nông và bất biến sâu trong Java

Trong lập trình hướng đối tượng, **bất biến (immutability)** là thuộc tính của một đối tượng mà **trạng thái quan sát được** của nó không thay đổi sau khi được tạo hoàn chỉnh. Một đối tượng bất biến thường dễ suy luận, có thể chia sẻ an toàn hơn và phù hợp để làm *value object*. Tuy nhiên, trong Java, việc khai báo các field là `private final` **chưa đủ để kết luận** rằng toàn bộ đối tượng bất biến.

Hãy xem ví dụ:

```java
final class Team {
    private final List<StringBuilder> members;

    Team(List<StringBuilder> members) {
        this.members = members;
    }
}
```

`members` là một **tham chiếu final**: constructor gán một lần và code của `Team` không thể gán lại field đó. Nhưng:

- Caller có thể giữ tham chiếu đến chính `List` rồi thêm/xóa phần tử.
- Caller có thể giữ tham chiếu đến `StringBuilder` và sửa nội dung.
- Nếu một getter trả list hoặc phần tử mutable, người dùng có thể thay đổi trạng thái mà `Team` quan sát.
- `final class` chỉ cấm kế thừa, không cấm thay đổi nội dung list.

Đây là trọng tâm của bài: **“không đổi tham chiếu”**, **“không sửa được cấu trúc collection qua API”** và **“không đổi được trạng thái sâu trong object graph”** là ba mức bảo đảm khác nhau.

Bài hướng dẫn trên **Java 17+**, gồm khái niệm, cơ chế tham chiếu, bản sao nông/sâu, các bẫy với array, collection và record, thiết kế defensive copy ở cả hai ranh giới, immutable value objects, các tình huống đồng thời, đánh đổi hiệu năng, chương trình chạy độc lập với lệnh `javac`/`java` và bài tập kèm đáp án.

## 1. Ba tầng dễ nhầm: final, bất biến nông, bất biến sâu

### 1.1. Tham chiếu `final`

```java
final List<String> names = new ArrayList<>();
names.add("An");
// names = new ArrayList<>(); // Không biên dịch: gán lại biến final.
```

`final` cấm **gán lại biến**, nhưng không cấm gọi các method thay đổi **đối tượng được tham chiếu**. Với field, `private final` bảo vệ việc gán lại field sau khởi tạo; nó không khóa toàn bộ những object có thể truy cập từ field.

### 1.2. Bất biến nông (shallow immutability)

Thuật ngữ *shallow immutable* trong tài liệu thực tế có thể có vài cách dùng. Một cách diễn đạt hữu ích trong bài này:

> Các thành phần trực tiếp/quan hệ tham chiếu của đối tượng được cố định theo API, nhưng những object mutable **được tham chiếu sâu hơn** vẫn có thể thay đổi.

Ví dụ record:

```java
record Group(List<StringBuilder> members) {
}
```

`Group` không có setter cho component `members`, nhưng `group.members().get(0).append("!")` có thể thay nội dung đối tượng `StringBuilder`. Vì vậy xét toàn bộ dữ liệu quan sát được, Group **không phải đối tượng bất biến sâu**.

### 1.3. Bất biến sâu (deep immutability)

Một object bất biến sâu khi, theo ranh giới trạng thái mà nó công bố, **không có đường truy cập hợp lệ nào để sửa trạng thái có thể quan sát của cả những thành phần phụ thuộc**, kể cả qua alias bên ngoài.

Ví dụ đơn giản:

```java
record Address(String city, String street) {
}
```

Hai components là `String` bất biến; record không có setter. Sau khi tạo, một `Address` thông thường có thể được xem là một **immutable value object** đối với hai components đó.

**Không có modifier `deep final` trong Java**. Bất biến sâu đến từ **thiết kế cả object graph**, lựa chọn thành phần immutable, ranh giới API và cách copy/ownership được bảo vệ.

## 2. Bản đồ so sánh

| Thuộc tính | Ví dụ | Điều được bảo đảm | Điều chưa được bảo đảm |
| --- | --- | --- | --- |
| Biến reference `final` | `final List<T> a` | Không gán lại `a` | Nội dung list/element không đổi |
| Field `private final` | `private final int[] data` | Field không gán lại sau khởi tạo | Phần tử array không đổi |
| Class `final` | `final class X` | Không subclass `X` | State của `X` không đổi |
| Collection unmodifiable view | `Collections.unmodifiableList(source)` | Không mutate qua view | Nguồn có thể bị mutate |
| Unmodifiable snapshot nông | `List.copyOf(source)` | List result không cho sửa cấu trúc qua API; detached khỏi nguồn mutable | Mutable elements vẫn đổi |
| Immutable elements + snapshot | `List.copyOf(List<String>)` với input đúng | Collection structure và các `String` không sửa được | Những mutable objects khác ngoài model |
| Defensive deep copy | Clone từng row của `int[][]` | Caller không sửa nội bộ qua array alias | Thread-safety của các thành phần mutable khác |
| Immutable value graph | `record Point(int x,int y)` và owner không lộ state mutable | Trạng thái giá trị quan sát được không đổi | Business entity bao ngoài không nhất thiết bất biến |

Một cách kiểm tra nhanh:

1. **Có setter/operation mutate trạng thái trực tiếp không?**
2. **Constructor giữ alias tới input mutable không?**
3. **Getter trả reference mutable nội bộ không?**
4. **Các phần tử/nested objects có mutate được không?**
5. **Object có quan sát dữ liệu mutable bên ngoài mà không copy không?**

Chỉ cần một đường làm thay đổi trạng thái có thể quan sát của đối tượng mà contract hứa bất biến, thiết kế đã không đạt bất biến sâu.

## 3. Phân biệt “state” với “identity” và “tham chiếu”

Một **biến tham chiếu** có thể trỏ tới một object; object ấy có thể chứa các tham chiếu khác.

```text
variable group ─────► Group object
                         │ final members
                         ▼
                      List object
                         │
                         ▼
                    StringBuilder object
                         │ mutable chars
                         ▼
                      "An"
```

Nếu `Group.members` là `final`, mũi tên **Group → List** không được gán lại qua field đó. Nhưng nội dung **List** hoặc **StringBuilder** vẫn có thể thay đổi.

Đây là ý nghĩa của **object graph**: một tập các objects được nối qua các references. Cần nhìn toàn đồ thị trạng thái có liên quan, không chỉ dòng khai báo field ở tầng đầu.

### Chia sẻ cùng một object (aliasing)

```java
StringBuilder builder = new StringBuilder("An");
List<StringBuilder> input = new ArrayList<>();
input.add(builder);

Group group = new Group(input);
```

Nếu Group giữ trực tiếp `input`, ba đường truy cập có thể ảnh hưởng representation của cùng dữ liệu:
- `input.add(...)`.
- `builder.append(...)`.
- `group.members().get(0).append(...)` nếu getter mở đường truy cập.

**Alias** là nhiều references cùng trỏ đến một object. Chỉ tạo thêm biến hoặc list chứa object **không** tạo bản sao của object đó.

## 4. Java `final` bảo vệ điều gì?

`final` có thể dùng với:
- Biến cục bộ;
- Tham số method;
- Instance fields;
- Static fields;
- Methods (cấm override);
- Classes (cấm subclass).

Ở bài này, chúng ta chủ yếu quan tâm **final field/reference**.

```java
final int age = 20;
// age = 21; // Không hợp lệ.

final StringBuilder name = new StringBuilder("An");
name.append(" Bình"); // Hợp lệ.
```

**Với primitive final**, giá trị primitive không thể được gán lại qua biến ấy. **Với reference final**, reference không thể gán lại, nhưng referent có thể mutable.

Khi fields có `final`, Java Memory Model còn cung cấp một số bảo đảm đặc biệt về **initialization safety** nếu object được xây dựng đúng và `this` không thoát ra trước khi constructor kết thúc. Tuy nhiên:

**Final-field semantics không biến `ArrayList` hoặc `int[]` thành thread-safe/immutable** và không làm những thay đổi xảy ra sau construction trở thành tự động synchronized.

## 5. Ví dụ runnable: `final` không đồng nghĩa bất biến sâu

Lưu **`FinalReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Catalog {
    private final List<String> names = new ArrayList<>();

    void add(String name) {
        names.add(name);
    }

    String description() {
        return names.toString();
    }
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        final Catalog catalog = new Catalog();

        catalog.add("Java");
        System.out.println(catalog.description());

        catalog.add("SQL");
        System.out.println(catalog.description());

        // catalog = new Catalog(); // Lỗi biên dịch.
    }
}
```

Chạy Java 17+:

```bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
```

**Stdout:**

```text
[Java]
[Java, SQL]
```

Ngay cả `catalog` ở `main` và field `names` trong Catalog đều cố định tham chiếu, object Catalog vẫn **thay đổi trạng thái qua `add`**. `final` không phải công cụ để tự động biến đối tượng thành immutable.

## 6. Bản sao nông (shallow copy) là gì?

Một **shallow copy** sao chép cấu trúc tầng ngoài nhưng vẫn **chia sẻ tham chiếu đến những phần tử object** bên trong.

Ví dụ:

```java
List<StringBuilder> original = new ArrayList<>();
original.add(new StringBuilder("An"));

List<StringBuilder> shallow = new ArrayList<>(original);
```

`original` và `shallow` là **hai List objects khác nhau**. Nhưng:

```java
original.get(0) == shallow.get(0) // true
```

vì chúng cùng tham chiếu một `StringBuilder`.

Kết quả:
- Thêm/xóa phần tử ở một list không tự thêm/xóa phần tử ở list còn lại.
- Sửa **StringBuilder element** qua một list được list còn lại nhìn thấy.
- Chỉ copy tầng ngoài **không đủ** nếu yêu cầu snapshot phải bất biến sâu.

### Phân biệt immutable với copy

Một object có thể immutable mà **không cần** tạo bản copy mới khi được chia sẻ; ví dụ cùng một `String` được giữ bởi nhiều lists thường an toàn về mutation.

Một object có thể được copy nông nhưng **cả bản gốc và bản sao vẫn mutable**.

**Copying** nói về quan hệ giữa hai trạng thái/đối tượng; **immutability** nói về khả năng trạng thái thay đổi. Chúng liên quan nhưng không đồng nghĩa.

## 7. Chương trình: sao chép nông không tách mutable elements

Lưu **`ShallowCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ShallowCopyDemo {
    public static void main(String[] args) {
        StringBuilder element = new StringBuilder("An");

        List<StringBuilder> original = new ArrayList<>();
        original.add(element);

        List<StringBuilder> copy = new ArrayList<>(original);

        System.out.println(original == copy);
        System.out.println(original.get(0) == copy.get(0));

        copy.add(new StringBuilder("Bình"));
        original.get(0).append("!");

        System.out.println("original = " + original);
        System.out.println("copy = " + copy);
    }
}
```

```bash
javac -encoding UTF-8 ShallowCopyDemo.java
java ShallowCopyDemo
```

**Stdout:**

```text
false
true
original = [An!]
copy = [An!, Bình]
```

- Thêm Bình vào `copy` không làm `original` dài thêm.
- Thay đổi `element` thành `An!` ảnh hưởng hiển thị ở **cả hai lists**.
- Không có race trong ví dụ: mọi thao tác chạy tuần tự trong một thread.

## 8. `Collections.unmodifiableList` là view, không phải snapshot

`Collections.unmodifiableList(source)` tạo một **wrapper view** không cho mutate collection **qua wrapper**, nhưng nếu bên ngoài vẫn giữ reference đến `source`, thay đổi `source` vẫn phản ánh qua view.

```java
List<String> source = new ArrayList<>();
source.add("A");

List<String> view = Collections.unmodifiableList(source);
source.add("B");
System.out.println(view); // [A, B]
```

Vì thế thuật ngữ “unmodifiable” không đồng nghĩa “immutable snapshot”.

Các điểm cần nhớ:

- `view.add(...)` → `UnsupportedOperationException`.
- `source.add(...)` → được phép vì source mutable.
- `view` đọc thấy dữ liệu từ source thay đổi.
- Nếu elements mutable, chúng vẫn có thể đổi qua alias.

### Tại sao một unmodifiable view vẫn hữu ích?

Khi source được sở hữu và mutate có kiểm soát bởi một object, view có thể cung cấp **read-only access qua API của client** để người dùng không tùy ý thêm/xóa.

Nhưng nếu contract yêu cầu **snapshot không thay đổi sau khi lấy**, phải tạo snapshot độc lập thay vì chỉ unmodifiable view trên live backing collection.

## 9. Chương trình: view thay đổi theo backing list

Lưu **`UnmodifiableViewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view =
                Collections.unmodifiableList(source);

        System.out.println("before = " + view);

        source.add("B");
        System.out.println("after = " + view);

        try {
            view.add("C");
        } catch (UnsupportedOperationException error) {
            System.out.println("view rejects mutation");
        }
    }
}
```

```bash
javac -encoding UTF-8 UnmodifiableViewDemo.java
java UnmodifiableViewDemo
```

**Stdout:**

```text
before = [A]
after = [A, B]
view rejects mutation
```

Chú ý: `view` vẫn có cùng các phần tử với backing source sau khi source được thay đổi. Dù wrapper chặn mutators, nó **không phải snapshot**.

## 10. `List.copyOf` tạo unmodifiable snapshot tầng ngoài

Với nguồn mutable thông thường:

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(source);

source.add("B");
System.out.println(snapshot); // [A]
```

`List.copyOf` trả một **unmodifiable List** mang các phần tử theo thứ tự nguồn tại thời điểm copy. Nó không phản ánh các thay đổi cấu trúc tiếp theo của mutable source.

**Tuy nhiên:**
- Copy là **shallow** đối với elements object.
- `List.copyOf` **không cho phần tử null**; có thể ném `NullPointerException` nếu source chứa null.
- Nó **có thể tái sử dụng** một list đầu vào vốn đã là unmodifiable implementation phù hợp; không nên khẳng định method luôn cấp phát object mới.
- Khi elements là `String`/immutable value objects và không có state mutable ẩn, snapshot có thể đủ cho bất biến sâu theo model.

### Khác `Collections.unmodifiableList`

| Cách tạo | Đổi cấu trúc source sau đó? | Mutate qua kết quả? | Các mutable elements có bị copy sâu? |
| --- | --- | --- | --- |
| `Collections.unmodifiableList(source)` | View thường phản ánh thay đổi | Không | Không |
| `List.copyOf(source)` | Snapshot không phản ánh mutation sau của mutable source | Không | Không |
| `new ArrayList<>(source)` | List mới tách cấu trúc nguồn | Có | Không |
| Custom deep copy | Tùy implementation | Tùy API xuất bản | Có, nếu copy đủ các tầng mutable |

## 11. Chương trình so sánh cùng lúc ba kiểu list

Lưu **`ListVariantsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListVariantsDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> view =
                Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);
        List<String> mutableCopy = new ArrayList<>(source);

        source.add("B");
        mutableCopy.add("C");

        System.out.println("source = " + source);
        System.out.println("view = " + view);
        System.out.println("snapshot = " + snapshot);
        System.out.println("mutableCopy = " + mutableCopy);
    }
}
```

```bash
javac -encoding UTF-8 ListVariantsDemo.java
java ListVariantsDemo
```

**Stdout:**

```text
source = [A, B]
view = [A, B]
snapshot = [A]
mutableCopy = [A, C]
```

Một bài học rất thực tế: không thể nhìn tên biến `snapshot` hoặc `view` để suy ra hành vi; phải xét **API tạo collection** và **mutability của các phần tử**.

## 12. Bất biến nông của collection chứa mutable elements

`List.copyOf` không thể ngăn một mutable element bị sửa qua reference khác.

```java
StringBuilder builder = new StringBuilder("A");
List<StringBuilder> source = new ArrayList<>();
source.add(builder);

List<StringBuilder> snapshot = List.copyOf(source);
builder.append("!");

System.out.println(snapshot); // [A!]
```

Snapshot list vẫn có cấu trúc cố định, nhưng representation của element thay đổi.

Tương tự:
- `List<Date>` với `java.util.Date` mutable;
- `List<int[]>` vì arrays mutable;
- `Map<String, List<String>>` nếu values chứa mutable lists;
- `Set<MutableUser>` nếu User có setters;
- `List<AtomicInteger>` vì atomic object mutable.

**Không thể gọi một cấu trúc “bất biến sâu” chỉ vì collection outer unmodifiable.**

### Một câu thử quan trọng

> Nếu caller giữ tham chiếu tới một element và gọi một mutator trên element đó, giá trị mà owner công bố có thay đổi không?

Nếu câu trả lời là “có”, owner không đạt bất biến sâu theo trạng thái bao gồm element đó.

## 13. Ví dụ: `List.copyOf` không copy `StringBuilder`

Lưu **`ShallowSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ShallowSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("Java");

        List<StringBuilder> source = new ArrayList<>();
        source.add(item);

        List<StringBuilder> snapshot = List.copyOf(source);

        source.add(new StringBuilder("SQL"));
        item.append(" 17");

        System.out.println("source = " + source);
        System.out.println("snapshot = " + snapshot);

        try {
            snapshot.clear();
        } catch (UnsupportedOperationException error) {
            System.out.println("structure locked");
        }
    }
}
```

```bash
javac -encoding UTF-8 ShallowSnapshotDemo.java
java ShallowSnapshotDemo
```

**Stdout:**

```text
source = [Java 17, SQL]
snapshot = [Java 17]
structure locked
```

Cấu trúc snapshot độc lập khỏi những lần thêm phần tử mới vào source, nhưng **mutable `StringBuilder` là cùng object** trong cả hai lists.

## 14. Deep copy là gì?

**Deep copy** tạo trạng thái mới và tách biệt những mutable objects có liên quan đến snapshot, thay vì chỉ copy reference outer.

Với list builders:

```java
List<StringBuilder> deep = new ArrayList<>();

for (StringBuilder sourceItem : source) {
    deep.add(new StringBuilder(sourceItem.toString()));
}
```

Đây là deep copy **cho object graph cụ thể gồm list và những StringBuilder elements**, không phải một thuật toán copy sâu tổng quát cho mọi Java object.

Khái niệm phụ thuộc **model và ranh giới**:
- Những immutable objects như `String` thường **không cần copy**.
- Những entities dùng chung theo identity có thể **không nên copy** nếu copy phá nghĩa domain.
- Những mutable objects cần độc lập thì phải copy toàn bộ các thành phần mutable liên quan.
- Các graph có shared aliases/cycles cần thuật toán giữ quan hệ identity khi có yêu cầu.

**Deep copy không có một hàm `Object.deepCopy()` chung trong Java.** Bạn thiết kế copy theo loại dữ liệu và hợp đồng của class.

## 15. Chương trình: copy list và copy từng mutable element

Lưu **`DeepCopyBuildersDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DeepCopyBuildersDemo {
    private static List<StringBuilder> deepCopy(
            List<StringBuilder> original) {

        List<StringBuilder> result = new ArrayList<>();

        for (StringBuilder builder : original) {
            result.add(new StringBuilder(builder.toString()));
        }

        return result;
    }

    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("An");
        List<StringBuilder> source = new ArrayList<>();
        source.add(item);

        List<StringBuilder> shallow = new ArrayList<>(source);
        List<StringBuilder> deep = deepCopy(source);

        item.append("!");
        shallow.add(new StringBuilder("Bình"));

        System.out.println("source = " + source);
        System.out.println("shallow = " + shallow);
        System.out.println("deep = " + deep);
        System.out.println(
                source.get(0) == deep.get(0));
    }
}
```

```bash
javac -encoding UTF-8 DeepCopyBuildersDemo.java
java DeepCopyBuildersDemo
```

**Stdout:**

```text
source = [An!]
shallow = [An!, Bình]
deep = [An]
false
```

Vì bản sao sâu có `StringBuilder` mới, mutation vào builder cũ không làm builder trong `deep` đổi. Nhưng `deep` trong ví dụ vẫn là một **mutable ArrayList** chứa mutable builders; nó **là bản copy sâu**, không phải một immutable object!

Đây là khác biệt then chốt: **copy sâu là thao tác tạo bản sao độc lập, không tự bảo đảm bản sao không thể bị mutate**.

## 16. Thiết kế immutable object: đóng cả hai ranh giới

Một class cố gắng bất biến sâu cần bảo vệ:
- **Input boundary:** constructor/factory không lưu alias mutable mà caller tiếp tục sửa.
- **Output boundary:** getter/accessor không trả direct reference tới mutable internal state.
- **Internal methods:** class không cung cấp operations thay state đã được hứa cố định.
- **Nested state:** các elements/children có khả năng mutate phải immutable hoặc được copy/ẩn an toàn.
- **Subclass boundary:** subclass không được phép làm sai invariant của base contract; `final` hoặc thiết kế inheritance có chủ đích.

Ví dụ class chứa primitive array:

```java
final class IntSeries {
    private final int[] values;

    IntSeries(int[] source) {
        this.values = source.clone();  // Copy đầu vào.
    }

    int[] values() {
        return values.clone();         // Copy đầu ra.
    }
}
```

Hai lần `clone()` **đều có mục đích**. Nếu bỏ một trong hai, caller có đường để thay đổi internal array.

## 17. Lỗi 1: chỉ `final` field, không defensive copy

```java
final class UnsafeScores {
    private final int[] values;

    UnsafeScores(int[] source) {
        values = source; // Sai nếu cần deep immutability.
    }

    int[] values() {
        return values;
    }
}
```

Hai đường sửa:
1. Caller thay `source[0]` sau khi constructor hoàn thành.
2. Caller lấy `values()` rồi sửa phần tử.

Field `values` vẫn trỏ tới cùng array, nhưng **nội dung array đã thay**.

### Lỗi 2: copy đầu vào nhưng lộ đầu ra

```java
UnsafeScores(int[] source) {
    values = source.clone();
}

int[] values() {
    return values; // Vẫn làm lộ internal mutable array.
}
```

Input được tách khỏi caller, nhưng getter trả alias nội bộ. Caller vẫn có thể sửa.

### Lỗi 3: không lộ array nhưng không copy đầu vào

```java
UnsafeScores(int[] source) {
    values = source; // Caller vẫn sở hữu alias.
}

int[] values() {
    return values.clone();
}
```

Getter an toàn hơn nhưng caller vẫn có thể sửa `source` gốc bên ngoài.

**Phải bảo vệ cả hai phía** khi một class cần cam kết snapshot bất biến.

## 18. Chương trình: copy array cả đầu vào và đầu ra

Lưu **`ImmutableScoresDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class ImmutableScores {
    private final int[] scores;

    ImmutableScores(int[] source) {
        scores = Objects.requireNonNull(source).clone();
    }

    int[] scores() {
        return scores.clone();
    }

    int sum() {
        int result = 0;
        for (int score : scores) {
            result += score;
        }
        return result;
    }

    @Override
    public String toString() {
        return "ImmutableScores" + Arrays.toString(scores);
    }
}

public class ImmutableScoresDemo {
    public static void main(String[] args) {
        int[] input = {10, 20};

        ImmutableScores scores = new ImmutableScores(input);
        input[0] = 999;

        int[] leakedCopy = scores.scores();
        leakedCopy[1] = 888;

        System.out.println(scores);
        System.out.println("sum = " + scores.sum());
        System.out.println(
                "input = " + Arrays.toString(input));
        System.out.println(
                "getter result = " + Arrays.toString(leakedCopy));
    }
}
```

```bash
javac -encoding UTF-8 ImmutableScoresDemo.java
java ImmutableScoresDemo
```

**Stdout:**

```text
ImmutableScores[10, 20]
sum = 30
input = [999, 20]
getter result = [10, 888]
```

Dù caller đổi input rồi sửa array từ getter, internal `scores` vẫn giữ dữ liệu snapshot `[10,20]`.

**Lưu ý:** `sum()` dùng `int` và có thể overflow nếu dữ liệu quá lớn. Ví dụ chỉ tập trung vào aliasing và bất biến, không phải mô hình tổng số nguyên không giới hạn.

## 19. Primitive array: `clone()` một tầng có đủ không?

Với `int[]`, mỗi phần tử là primitive, nên `clone()` tạo array mới chứa các **giá trị primitive** được copy. Không còn nested object mutable nào **bên trong mảng một chiều đó**.

Vì vậy đối với trạng thái chỉ gồm một `int[]`:
- Copy array khi nhận.
- Không mutate internal array sau construction.
- Trả copy khi getter được gọi.
- Không publish mutable internals theo đường khác.

là nền tảng hợp lý cho deep immutability.

**Nhưng với `int[][]` thì khác:** nó là một mảng chứa **references tới các mảng `int[]` con**. Chỉ clone outer array vẫn chia sẻ các inner arrays.

## 20. Mảng hai chiều: shallow copy khác deep copy

```java
int[][] source = {
    {1, 2},
    {3, 4}
};

int[][] shallow = source.clone();
```

Sau lệnh:

```java
source != shallow;            // true
source[0] == shallow[0];      // true
```

Nên:

```java
source[0][0] = 99;
```

làm `shallow[0][0]` cũng thành `99`.

Muốn tách các hàng:

```java
int[][] deep = new int[source.length][];

for (int i = 0; i < source.length; i++) {
    deep[i] = source[i].clone();
}
```

Với matrix có các elements primitive ở tầng sâu nhất, copy cả outer array và từng row đủ để tách những mutable arrays đó.

### Mảng răng cưa

Java cho phép mỗi row có độ dài khác nhau. Không nên giả định matrix luôn có số cột cố định khi copy. `source[i].clone()` giữ đúng độ dài của từng row; nếu row có thể null, phải chọn chính sách xử lý null trước.

## 21. Chương trình: shallow và deep với `int[][]`

Lưu **`MatrixCopyDemo.java`**:

```java
import java.util.Arrays;

public class MatrixCopyDemo {
    static int[][] copyDeep(int[][] source) {
        int[][] result = new int[source.length][];

        for (int i = 0; i < source.length; i++) {
            result[i] = source[i].clone();
        }

        return result;
    }

    public static void main(String[] args) {
        int[][] original = {{1, 2}, {3, 4}};

        int[][] shallow = original.clone();
        int[][] deep = copyDeep(original);

        original[0][0] = 99;
        shallow[1][1] = 88;

        System.out.println(
                "original = " + Arrays.deepToString(original));
        System.out.println(
                "shallow = " + Arrays.deepToString(shallow));
        System.out.println(
                "deep = " + Arrays.deepToString(deep));
        System.out.println(original[0] == deep[0]);
    }
}
```

```bash
javac -encoding UTF-8 MatrixCopyDemo.java
java MatrixCopyDemo
```

**Stdout:**

```text
original = [[99, 2], [3, 88]]
shallow = [[99, 2], [3, 88]]
deep = [[1, 2], [3, 4]]
false
```

Đây là bản copy sâu cho **hai tầng mảng** của ví dụ, không phải hàm deep-copy mọi object graph Java tùy ý.

## 22. Bất biến sâu của một object chứa matrix

Nếu muốn đóng gói `int[][]` thành value object:
- Constructor copy tất cả rows.
- Getter trả một deep copy.
- Operations đọc không mutate dữ liệu.
- Class `final` để không xuất hiện subclass phá invariant.
- Không expose các mảng nội bộ qua method khác.

### Chương trình runnable: immutable matrix snapshot

Lưu **`ImmutableMatrixDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class ImmutableMatrix {
    private final int[][] data;

    ImmutableMatrix(int[][] source) {
        data = copyDeep(source);
    }

    private static int[][] copyDeep(int[][] source) {
        Objects.requireNonNull(source, "source");

        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = Objects.requireNonNull(
                    source[i], "row " + i).clone();
        }
        return result;
    }

    int[][] data() {
        return copyDeep(data);
    }

    int at(int row, int col) {
        return data[row][col];
    }

    @Override
    public String toString() {
        return Arrays.deepToString(data);
    }
}

public class ImmutableMatrixDemo {
    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3, 4}};

        ImmutableMatrix matrix = new ImmutableMatrix(input);

        input[0][0] = 10;
        int[][] snapshot = matrix.data();
        snapshot[1][1] = 40;

        System.out.println(matrix);
        System.out.println(matrix.at(0, 0));
        System.out.println(matrix.at(1, 1));
    }
}
```

```bash
javac -encoding UTF-8 ImmutableMatrixDemo.java
java ImmutableMatrixDemo
```

**Stdout:**

```text
[[1, 2], [3, 4]]
1
4
```

**Vấn đề phụ:** nếu class muốn có **value equality**, cần triển khai `equals`/`hashCode` phù hợp, chẳng hạn `Arrays.deepEquals`/`Arrays.deepHashCode` trên matrix (và giữ contract). Chỉ làm data immutable không tự viết equality cho bạn.

## 23. Record: final components, nhưng chưa chắc deep immutable

Record thường được dùng làm value carrier:

```java
record Student(String name, int age) {
}
```

Với `String` và `int` như trên, state công bố không có nested mutable referents. Nhưng:

```java
record Classroom(List<String> students) {
}
```

được tạo với một `ArrayList` mutable sẽ giữ reference đến list đó nếu bạn không xử lý đặc biệt. Accessor `students()` tự sinh cũng trả chính reference list component.

Ví dụ:

```java
List<String> input = new ArrayList<>();
input.add("An");
Classroom classroom = new Classroom(input);

input.add("Bình");
System.out.println(classroom.students()); // [An, Bình]
```

Record không bảo vệ chủ sở hữu khỏi aliasing **một cách tự động**.

### Record cũng không tự deep-copy

Dù record ngầm định final và fields cho components là final, trường `List<StringBuilder>` hay `int[]` vẫn giữ những object mutable. **Syntax của record làm gọn value class, không thay việc thiết kế ownership.**

## 24. Chương trình: record shallow mutable qua constructor/accessor

Lưu **`UnsafeRecordDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Classroom(List<String> students) {
}

public class UnsafeRecordDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Classroom room = new Classroom(input);

        input.add("Bình");
        room.students().remove("An");

        System.out.println("input = " + input);
        System.out.println("room = " + room);
    }
}
```

```bash
javac -encoding UTF-8 UnsafeRecordDemo.java
java UnsafeRecordDemo
```

**Stdout:**

```text
input = [Bình]
room = Classroom[students=[Bình]]
```

Constructor giữ direct alias đến mutable list. Generated accessor cũng trả alias đó; vì vậy hai phía đều có quyền sửa cùng list.

## 25. Record compact constructor: `List.copyOf` phù hợp khi elements immutable

Java record có **compact canonical constructor**:

```java
record Classroom(List<String> students) {
    Classroom {
        students = List.copyOf(students);
    }
}
```

Trong compact constructor, bạn có thể **gán lại parameter `students`**; compiler sẽ dùng giá trị parameter cuối để khởi tạo component field theo quy tắc record.

Vì đây là `List<String>` và `String` immutable, đây là cách gọn để tạo một snapshot bất biến sâu **đối với danh sách các chuỗi**, với giả định không có dữ liệu mutable nào khác cần xét.

### Chương trình an toàn với record

Lưu **`SafeRecordDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Classroom(List<String> students) {
    Classroom {
        students = List.copyOf(students);
    }
}

public class SafeRecordDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Classroom room = new Classroom(input);
        input.add("Bình");

        System.out.println("input = " + input);
        System.out.println("room = " + room);

        try {
            room.students().add("Chi");
        } catch (UnsupportedOperationException error) {
            System.out.println("room list is unmodifiable");
        }
    }
}
```

```bash
javac -encoding UTF-8 SafeRecordDemo.java
java SafeRecordDemo
```

**Stdout:**

```text
input = [An, Bình]
room = Classroom[students=[An]]
room list is unmodifiable
```

**Giới hạn:** nếu thay component thành `List<StringBuilder>`, `List.copyOf` vẫn shallow và record vẫn không đạt deep immutability.

## 26. Record chứa arrays và value equality

Đặc biệt dễ sai:

```java
record Data(int[] values) {
}
```

Có ba vấn đề:
1. Constructor mặc định có thể giữ direct alias đến array.
2. Accessor `values()` trả direct array reference.
3. Generated `equals`/`hashCode` của record khi component là array dựa trên các quy tắc equality/hash của array **không phải so sánh nội dung sâu như `Arrays.equals`**.

Vì vậy **chỉ viết compact constructor clone array vẫn chưa tự có deep value semantics**.

Có thể:
- Dùng một `final class` để viết defensive copy và deep-value equality rõ.
- Dùng immutable `List<Integer>` thay array nếu kích thước/hiệu năng phù hợp.
- Override cả accessor và `equals/hashCode` cần thiết trong record một cách có chủ đích.

**Immutability** và **value equality** là hai hợp đồng khác nhau: object có thể immutable nhưng `equals` mặc định vẫn so identity.

## 27. `Date` mutable so với `java.time`

`java.util.Date` là mutable:

```java
Date date = new Date(0);
date.setTime(1_000L);
```

Nếu một class lưu trực tiếp `Date` đầu vào và getter trả direct Date, object ấy không bất biến sâu.

Ngược lại, nhiều lớp của `java.time` như:
- `LocalDate`;
- `LocalDateTime`;
- `Instant`;
- `ZoneId` implementations thích hợp;
- `Duration`;

được thiết kế với semantics immutable. Các thao tác như `plusDays` trả **đối tượng/giá trị kết quả** thay vì mutate object gốc.

**Lưu ý:** Date vs java.time không có nghĩa mọi object ở mọi thư viện thời gian đều immutable. Luôn kiểm tra contract của type cụ thể.

## 28. Chương trình: Date aliasing làm “immutable” object đổi

Lưu **`MutableDateDemo.java`**:

```java
import java.util.Date;

final class UnsafeEvent {
    private final Date when;

    UnsafeEvent(Date when) {
        this.when = when;
    }

    long epochMillis() {
        return when.getTime();
    }
}

public class MutableDateDemo {
    public static void main(String[] args) {
        Date date = new Date(0L);
        UnsafeEvent event = new UnsafeEvent(date);

        System.out.println(event.epochMillis());

        date.setTime(2_000L);
        System.out.println(event.epochMillis());
    }
}
```

```bash
javac -encoding UTF-8 MutableDateDemo.java
java MutableDateDemo
```

**Stdout:**

```text
0
2000
```

`UnsafeEvent.when` là `final` nhưng object `Date` do caller giữ alias đã bị thay đổi.

## 29. Hai hướng sửa Date: defensive copy hoặc immutable time type

Hướng 1 — Copy `Date` ở cả đầu vào và đầu ra:

```java
final class SafeLegacyEvent {
    private final Date when;

    SafeLegacyEvent(Date input) {
        when = new Date(input.getTime());
    }

    Date when() {
        return new Date(when.getTime());
    }
}
```

Cần import `java.util.Date`. `Date` vẫn mutable, nhưng caller không có direct alias tới internal Date qua những API này.

Hướng 2 — Dùng `Instant`:

```java
record Event(java.time.Instant at) {
}
```

`Instant` là immutable; thường đơn giản hơn nếu domain chỉ cần một timestamp và không có ràng buộc compatibility với API Date cũ.

### Chương trình runnable với `Instant`

Lưu **`InstantImmutabilityDemo.java`**:

```java
import java.time.Instant;

record Event(Instant at) {
}

public class InstantImmutabilityDemo {
    public static void main(String[] args) {
        Instant original = Instant.parse("2026-01-01T00:00:00Z");
        Event event = new Event(original);

        Instant next = original.plusSeconds(60);

        System.out.println(event.at());
        System.out.println(next);
        System.out.println(event.at() == original);
    }
}
```

```bash
javac -encoding UTF-8 InstantImmutabilityDemo.java
java InstantImmutabilityDemo
```

**Stdout:**

```text
2026-01-01T00:00:00Z
2026-01-01T00:01:00Z
true
```

`plusSeconds` tạo giá trị kết quả mà không mutate `original`. Reference `Event.at` vẫn trỏ tới immutable Instant ban đầu.

## 30. Immutable objects có thể chia sẻ references an toàn

Một lầm tưởng: “Bất biến sâu phải copy mọi object ở mọi tầng.”

Thực tế **không phải**. Nếu hai objects cùng giữ một `String`, `LocalDate` hoặc value object immutable, chia sẻ reference **không cho phép sửa trạng thái qua alias**.

```java
String label = "Java";
record Name(String value) { }

Name a = new Name(label);
Name b = new Name(label);
```

Cả a và b có thể dùng cùng `String` mà không lo caller append trực tiếp lên string đó. Gọi `label.concat(" 17")` trả một giá trị String khác, không làm String gốc đổi.

**Một immutable graph có thể chia sẻ các immutable subgraphs.** Đó còn là cơ sở của kỹ thuật **structural sharing** trong persistent immutable data structures.

Không cần clone String để bảo vệ state; clone những loại vốn immutable thường chỉ gây chi phí vô ích.

## 31. Nested collections: snapshot ngoài chưa đủ nếu list bên trong mutable

Ví dụ:

```java
List<List<String>> outer = new ArrayList<>();
List<String> first = new ArrayList<>();
first.add("A");
outer.add(first);

List<List<String>> snapshot = List.copyOf(outer);
first.add("B");
```

`snapshot` là unmodifiable **outer list**, nhưng `snapshot.get(0)` vẫn là **inner ArrayList** mutable và giờ chứa `[A,B]`.

Cần một nested immutable representation:

```java
List<List<String>> rows = outer.stream()
        .map(List::copyOf)
        .toList();
```

Với `String` elements immutable, mỗi inner list snapshot detached khỏi mutable source; outer list từ `Stream.toList()` là unmodifiable theo Java 17 contract.

### Không clone sâu bằng cách chỉ copy outer

Các cách sau **chưa đủ**:
- `List.copyOf(outer)`;
- `new ArrayList<>(outer)`;
- `Collections.unmodifiableList(outer)`;
- `Collections.unmodifiableList(new ArrayList<>(outer))`;

vì chúng vẫn giữ mutable inner list references nếu source chứa chúng.

## 32. Chương trình: immutable snapshot hai tầng List<List<String>>

Lưu **`NestedListSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Schedule {
    private final List<List<String>> rows;

    Schedule(List<List<String>> source) {
        rows = source.stream()
                .map(List::copyOf)
                .toList();
    }

    List<List<String>> rows() {
        return rows;
    }
}

public class NestedListSnapshotDemo {
    public static void main(String[] args) {
        List<String> monday = new ArrayList<>();
        monday.add("Java");

        List<List<String>> input = new ArrayList<>();
        input.add(monday);

        Schedule schedule = new Schedule(input);

        monday.add("SQL");
        input.add(new ArrayList<>(List.of("Python")));

        System.out.println("input = " + input);
        System.out.println("schedule = " + schedule.rows());

        try {
            schedule.rows().get(0).add("Kotlin");
        } catch (UnsupportedOperationException error) {
            System.out.println("inner list unmodifiable");
        }
    }
}
```

```bash
javac -encoding UTF-8 NestedListSnapshotDemo.java
java NestedListSnapshotDemo
```

**Stdout:**

```text
input = [[Java, SQL], [Python]]
schedule = [[Java]]
inner list unmodifiable
```

Vì inner elements là `String` immutable, object Schedule bảo vệ dữ liệu hai tầng ở đây. Nếu thay `String` bằng một class mutable, cần tiếp tục xử lý tầng đó.

## 33. `Map.copyOf` không copy sâu values

`Map.copyOf(input)` tạo một unmodifiable map theo contract, nhưng là shallow đối với key/value objects.

```java
Map<String, List<String>> data = new HashMap<>();
List<String> items = new ArrayList<>();
items.add("A");
data.put("course", items);

Map<String, List<String>> frozenOuter = Map.copyOf(data);
items.add("B");
```

`frozenOuter.get("course")` có thể chứa `[A,B]` vì value list vẫn là cùng mutable object.

### Cách tạo map với immutable nested values

```java
Map<String, List<String>> snapshot = new HashMap<>();

for (var entry : data.entrySet()) {
    snapshot.put(entry.getKey(),
            List.copyOf(entry.getValue()));
}

snapshot = Map.copyOf(snapshot);
```

Với immutable String keys/values, đây là một snapshot sâu theo model hai tầng này.

**Lưu ý:** `Map.copyOf` không cam kết iteration order của map kết quả. Nếu output cần thứ tự, hãy chọn representation/collection có contract order tương ứng và bọc snapshot thích hợp.

Ngoài ra `Map.copyOf` từ chối null keys/values, nên cần xác định null policy trước khi dùng.

## 34. Chương trình: map ngoài cố định nhưng values vẫn đổi

Lưu **`MapShallowDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class MapShallowDemo {
    public static void main(String[] args) {
        List<String> courses = new ArrayList<>();
        courses.add("Java");

        Map<String, List<String>> input = new HashMap<>();
        input.put("dev", courses);

        Map<String, List<String>> copy = Map.copyOf(input);

        courses.add("SQL");

        System.out.println(copy.get("dev"));

        try {
            copy.put("qa", List.of("Tests"));
        } catch (UnsupportedOperationException error) {
            System.out.println("outer map is unmodifiable");
        }
    }
}
```

```bash
javac -encoding UTF-8 MapShallowDemo.java
java MapShallowDemo
```

**Stdout:**

```text
[Java, SQL]
outer map is unmodifiable
```

Không nên suy luận “Map unmodifiable → data toàn bộ bất biến”.

## 35. Set và các collection factories

Java 9+ có:
- `List.of(...)`;
- `Set.of(...)`;
- `Map.of(...)`;
- `List.copyOf(...)`;
- `Set.copyOf(...)`;
- `Map.copyOf(...)`.

Chúng cung cấp **unmodifiable collections** phù hợp để xây value graph với immutable elements, nhưng:
- Không deep-copy mutable element objects.
- Có những quy tắc null/duplicate riêng: `List.of`/`Set.of`/`Map.of` không cho null; `Set.of` không cho duplicate elements; `Map.of` không cho duplicate keys.
- Không phải mọi factory bảo đảm iteration order mong đợi.
- Implementation có thể tối ưu hoặc chia sẻ instances theo contract; không dựa vào identity equality `==` giữa collection results.

Một **unmodifiable collection** là một công cụ, không phải định nghĩa đầy đủ của immutable object graph.

## 36. `Collections.unmodifiableMap` và backing alias

`Collections.unmodifiableMap(backing)` tạo một **view** trên backing map. Nếu một owner còn sửa backing map, view sẽ phản ánh thay đổi.

```java
Map<String, Integer> backing = new HashMap<>();
backing.put("A", 1);

Map<String, Integer> view =
        Collections.unmodifiableMap(backing);

backing.put("B", 2);
```

Không thể gọi `view.put(...)` thành công, nhưng view **không phải snapshot**.

Muốn snapshot với immutable keys/values, có thể dùng `Map.copyOf(backing)` hoặc copy sang một unmodifiable map khác theo ordering needs. **Không đem `unmodifiableMap(backing)` đi công bố như một historical snapshot** nếu backing còn thay đổi.

## 37. `clone()` và `Cloneable` không tự tạo deep copy

`Object.clone()` có cơ chế copy object theo contract, nhưng **không tự sao chép sâu mọi mutable referenced fields**.

Nếu class có:

```java
class Container implements Cloneable {
    int[] values;
}
```

một clone nông có thể có reference `values` trỏ đến cùng array như object gốc, trừ khi tác giả clone thủ công array đó.

Vấn đề thực tế:
- `Cloneable` có API contract gây khó hiểu nếu dùng bừa.
- Constructors/invariants có thể không được xử lý theo cách người đọc mong đợi.
- Kế thừa và fields mới dễ khiến clone thiếu deep copy.
- Cycles/shared aliases trong object graph khiến copy thủ công phức tạp.

**Không nên dùng `clone()` như một “nút deep immutable”**. Copy constructor, factory method `copyOf` hoặc immutable design rõ ràng thường dễ kiểm soát hơn.

## 38. Copy constructor không tự sâu hay nông

Tên method không quyết định semantics.

```java
final class Box {
    final List<StringBuilder> values;

    Box(Box other) {
        values = new ArrayList<>(other.values);
    }
}
```

Dù gọi là **copy constructor**, ví dụ chỉ copy **outer list**, không copy builders. Nó vẫn shallow copy đối với elements.

Một copy constructor đúng với contract **deep copy** phải duyệt và copy đủ mọi mutable state thuộc phạm vi owner.

**Đừng tự tuyên bố copy constructor là deep chỉ vì nhận một object cùng type.**

## 39. Value object với nested mutable input: thiết kế representation immutable

Một hướng thực tế là **chuyển đổi dữ liệu mutable đầu vào thành immutable value types** ngay ở ranh giới:

Ví dụ nhận danh sách `StringBuilder` từ một subsystem cũ, nhưng nội bộ chỉ giữ `String`:

```java
List<String> values = builders.stream()
        .map(StringBuilder::toString)
        .toList();
```

`StringBuilder.toString()` tạo một String representation hiện tại. Vì String immutable, owner không còn chia sẻ mutable builder references.

Đây là **snapshot bằng cách chuyển representation**, không phải giữ builder rồi cố khóa nó.

### Ưu điểm so với giữ mutable element

- Ít đường alias để kiểm soát.
- Getter có thể trả immutable list của immutable strings.
- Equality và hashing đơn giản hơn.
- An toàn hơn khi chia sẻ giữa threads **sau khi publish đúng cách**.
- Các invariants của owner ít phụ thuộc code ngoài.

### Giới hạn

Đôi khi mutable object chứa identity/resources không thể chuyển thành String mà vẫn giữ semantics; khi đó cần snapshot type tương ứng hoặc ownership contract riêng.

## 40. Chương trình: chuyển `StringBuilder` thành immutable snapshots

Lưu **`BuilderToStringSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Names {
    private final List<String> values;

    Names(List<StringBuilder> input) {
        values = input.stream()
                .map(StringBuilder::toString)
                .toList();
    }

    List<String> values() {
        return values;
    }
}

public class BuilderToStringSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("An");
        List<StringBuilder> input = new ArrayList<>();
        input.add(builder);

        Names names = new Names(input);

        builder.append("!");
        input.add(new StringBuilder("Bình"));

        System.out.println("input = " + input);
        System.out.println("names = " + names.values());
    }
}
```

```bash
javac -encoding UTF-8 BuilderToStringSnapshotDemo.java
java BuilderToStringSnapshotDemo
```

**Stdout:**

```text
input = [An!, Bình]
names = [An]
```

Ở Java 17, `Stream.toList()` trả unmodifiable list. Các phần tử kết quả là `String` immutable, nên graph do `Names` công bố không bị thay bởi việc caller sửa builders/list đầu vào.

## 41. Deep immutability và nested custom classes

Giả sử:

```java
class MutableAddress {
    String city;

    void setCity(String city) {
        this.city = city;
    }
}

record Person(String name, MutableAddress address) {
}
```

`Person` được tạo bằng record, nhưng caller vẫn có thể `address.setCity(...)` và làm `person.address().city` đổi.

Cách sửa phù hợp với domain:
- Thay `MutableAddress` bằng một immutable `Address` record với `String city`.
- Hoặc lưu immutable snapshot of address fields trong Person.
- Hoặc copy `MutableAddress` và **không trả mutable internal Address** ra ngoài.
- Hoặc thiết kế owner API không cho nested state thay sau construction.

**Không thể “deep copy” bằng cách copy mỗi `Person` record rồi vẫn giữ nguyên MutableAddress reference.**

### Tránh subclass phá invariant

Nếu class immutable có thể subclass, subclass có thể thêm mutable state hoặc override methods công bố trạng thái thay đổi. `final class`, record (final) hoặc một inheritance design được tài liệu hóa là cách giới hạn extension tùy nhu cầu.

## 42. Chương trình: immutable Address value object trong Person

Lưu **`DeepValueGraphDemo.java`**:

```java
import java.util.List;
import java.util.ArrayList;

record Address(String city, String street) {
}

record Person(String name, Address address) {
}

record Team(List<Person> members) {
    Team {
        members = List.copyOf(members);
    }
}

public class DeepValueGraphDemo {
    public static void main(String[] args) {
        Address address = new Address("Hà Nội", "A");
        Person an = new Person("An", address);

        List<Person> input = new ArrayList<>();
        input.add(an);

        Team team = new Team(input);
        input.add(new Person("Bình",
                new Address("Huế", "B")));

        System.out.println(team.members().size());
        System.out.println(team.members().get(0).address().city());

        Address other = new Address("Đà Nẵng", "C");
        System.out.println(other.city());
        System.out.println(team.members().get(0).address().city());
    }
}
```

```bash
javac -encoding UTF-8 DeepValueGraphDemo.java
java DeepValueGraphDemo
```

**Stdout:**

```text
1
Hà Nội
Đà Nẵng
Hà Nội
```

Graph `Team → List<Person> → Person → Address → Strings` dùng immutable value objects. List được snapshot. Vì vậy các mutations vào mutable input list không làm Team thấy thành viên mới, và tạo Address mới không thay Address gốc của An.

## 43. Deep immutability không đồng nghĩa “không có mutable object bên ngoài”

Một immutable object có thể **sử dụng** mutable service qua method parameter mà không lưu trong state:

```java
record Invoice(long cents) {
    void printTo(java.io.PrintStream output) {
        output.println(cents);
    }
}
```

`PrintStream` mutable và có side effects, nhưng nó **không phải thành phần trạng thái bất biến mà Invoice công bố**.

Tương tự, một class có thể cung cấp method `render(Formatter formatter)` dùng mutable formatter tạm thời, mà không biến giá trị bên trong class trở thành mutable.

Khi phân loại shallow/deep, cần xác định **ranh giới trạng thái (state boundary)** chứ không xem bất cứ object nào từng xuất hiện trong method là part của object graph.

**Nên phân biệt state, dependency và ownership.**

## 44. Ownership: chuyển trách nhiệm vs copy

Nếu một owner nhận mutable object, có hai chiến lược chính:

1. **Sao chép snapshot**, để caller tiếp tục sửa input mà owner không bị ảnh hưởng.
2. **Chuyển giao ownership theo hợp đồng**, caller cam kết không đụng object sau khi giao; owner kiểm soát toàn bộ các đường mutate.

Trong Java phổ thông, compiler **không ép** một reference chỉ có một owner hay đã được “move” như một linear/affine type system. Nếu caller giữ alias và vẫn có quyền mutate qua Java API, chỉ dựa vào lời hứa transfer có rủi ro.

Với immutable value objects công khai rộng rãi, **defensive copy hoặc immutable representation** thường dễ chứng minh hơn.

**Không phải mọi object cần deep copy:** nếu part là resource/socket/entity có identity thật, việc copy có thể sai nghĩa. Khi ấy nên thiết kế lifecycle/permissions thay vì giả vờ có deep immutable snapshot.

## 45. Mutable graph có cycles: copy sâu phức tạp hơn lặp các getter

Một graph:

```text
A ──► B
▲     │
└─────┘
```

có **cycle**. Nếu một hàm copy ngây thơ đệ quy:

```java
Node copy(Node node) {
    return new Node(copy(node.next));
}
```

nó có thể không bao giờ dừng với cycle.

Một graph có **shared alias**:

```text
Parent1 ──► SharedChild ◄── Parent2
```

nếu deep-copy mỗi nhánh độc lập, bạn có thể vô tình tạo **hai** SharedChild khác nhau và phá semantics identity-sharing.

Giải pháp tổng quát khi thật sự cần clone graph:
- Dùng một map từ **original object identity** sang **copy object** đã cấp phát, ví dụ `IdentityHashMap<Object,Object>`.
- Tạo placeholder/copy instance trước khi đệ quy khi cần hỗ trợ cycles.
- Giữ đúng alias relation theo contract.
- Sau khi xây dựng xong, công bố representation immutable phù hợp.

Đây là lý do **deep copy tổng quát** phức tạp hơn nhiều so với copy `int[][]` hoặc list của immutable values.

## 46. Snapshot của graph mutable và tính nhất quán giữa threads

Giả sử thread A đang sửa mutable list trong lúc thread B gọi:

```java
List.copyOf(source)
```

Nếu không có synchronization phù hợp, snapshot có thể quan sát dữ liệu đang đổi, có race hoặc kết quả không như kỳ vọng; `List.copyOf` **không phải transaction snapshot đồng thời** cho một collection mutable được cập nhật ngoài.

Để có snapshot nhất quán:
- Tất cả writers và snapshot reader phối hợp trên cùng lock, hoặc
- Dùng immutable/persistent state và atomic publication, hoặc
- Dùng concurrent structure với snapshot semantics được tài liệu hóa, hoặc
- Thiết kế protocol transaction đúng hơn.

**Deep copy** giải quyết vấn đề **aliasing của kết quả sau khi copy**, nhưng bản thân thao tác copy phải quan sát một nguồn nhất quán nếu yêu cầu snapshot tương ứng một thời điểm hợp lệ.

## 47. Bất biến và thread-safety: liên hệ nhưng không đồng nhất

Một **immutable value graph** sau construction thường có lợi:
- Không có data race do mutation của chính graph.
- Nhiều threads có thể đọc state cùng lúc mà không cần lock cho thao tác đọc state ấy.
- Không cần đồng bộ mỗi lần truy cập một field immutable đơn giản.
- Caching, memoization bên ngoài và sử dụng làm keys có thể dễ hơn.

Tuy nhiên phải xét **safe publication**: việc chuyển reference từ thread xây dựng sang thread dùng cần tuân theo Java Memory Model. Final fields cung cấp initialization-safety guarantees khi được xây đúng, nhưng đừng cho rằng **mọi kiểu reference publication racy đều an toàn cho mọi thành phần**.

Các cách publish rõ ràng:
- Giao object qua `BlockingQueue`;
- Đưa vào `volatile`/atomic reference thích hợp;
- Tạo/đưa qua `synchronized`;
- Truyền qua `Thread.start` theo happens-before;
- Dùng concurrent collection có contract publication.

Đặc biệt với mutable elements hoặc lazy state, `final` ở outer field **không** tự giải quyết race ở những object con.

## 48. Example: immutable snapshot chia sẻ qua threads

Lưu **`ImmutableThreadShareDemo.java`**:

```java
import java.util.List;

record Configuration(List<String> features) {
    Configuration {
        features = List.copyOf(features);
    }
}

public class ImmutableThreadShareDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Configuration configuration =
                new Configuration(List.of("A", "B"));

        Thread first = new Thread(() -> {
            System.out.println(
                    "first size = " + configuration.features().size());
        });

        Thread second = new Thread(() -> {
            System.out.println(
                    "second size = " + configuration.features().size());
        });

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("shared safely");
    }
}
```

```bash
javac -encoding UTF-8 ImmutableThreadShareDemo.java
java ImmutableThreadShareDemo
```

**Các dòng được in**:

```text
first size = 2
second size = 2
shared safely
```

**Chú ý:** hai dòng đầu **có thể đổi thứ tự** giữa các lần chạy, do scheduling không xác định; dòng `shared safely` luôn đến sau cả hai vì `join`. Giá trị và nội dung từng dòng xác định, nhưng nếu muốn **stdout đúng một thứ tự**, hãy lưu kết quả vào các biến thread-safe/ô riêng rồi in tại main sau `join`.

Ví dụ này cố ý làm rõ giới hạn về thứ tự output trong concurrency, không khẳng định tính determinism mà Java không hứa.

## 49. Chương trình có output deterministic khi nhiều threads đọc immutable object

Lưu **`ImmutableThreadDeterministicDemo.java`**:

```java
import java.util.List;

record Configuration(List<String> features) {
    Configuration {
        features = List.copyOf(features);
    }
}

public class ImmutableThreadDeterministicDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Configuration config =
                new Configuration(List.of("A", "B"));

        int[] observed = new int[2];

        Thread first = new Thread(
                () -> observed[0] = config.features().size());
        Thread second = new Thread(
                () -> observed[1] = config.features().size());

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("first = " + observed[0]);
        System.out.println("second = " + observed[1]);
        System.out.println("same object = " + (config == config));
    }
}
```

```bash
javac -encoding UTF-8 ImmutableThreadDeterministicDemo.java
java ImmutableThreadDeterministicDemo
```

**Stdout chính xác:**

```text
first = 2
second = 2
same object = true
```

Hai threads ghi vào **hai phần tử array khác nhau** và main đợi `join` trước khi đọc. Dòng cuối chỉ minh họa một reference tự bằng chính nó; câu chuyện quan trọng là snapshot `Configuration` không thay đổi.

## 50. Bất biến sâu và hash-based collections

Nếu một object được dùng làm key trong `HashMap` hoặc element của `HashSet`, thay đổi các fields dùng cho `equals/hashCode` sau insertion có thể phá kỳ vọng truy xuất.

Ví dụ rủi ro:

```java
class MutableKey {
    String code;

    // equals/hashCode dùng code.
}
```

Nếu `code` đổi sau khi key nằm trong map, lookup bằng key/value tương đương có thể thất bại vì hash bucket/search không còn phù hợp trạng thái mới.

**Immutable value objects** thường là lựa chọn tốt cho keys vì giá trị equality/hash không đổi sau construction.

Tuy nhiên phải xác định:
- `equals` dùng đúng các components theo contract.
- `hashCode` nhất quán với equals.
- Components tham gia equals/hashCode cũng immutable hoặc được snapshot đúng.
- Không lộ nested mutable state ảnh hưởng equality.

Đừng cố “sửa” bằng cách lưu hashCode cached nếu mutable fields vẫn thay; như vậy có thể tạo inconsistency nguy hiểm hơn.

## 51. Runnable: mutable key gây lookup bất ngờ

Lưu **`MutableKeyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

final class MutableKey {
    private String code;

    MutableKey(String code) {
        this.code = code;
    }

    void setCode(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey key
                && Objects.equals(code, key.code);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(code);
    }
}

public class MutableKeyDemo {
    public static void main(String[] args) {
        MutableKey key = new MutableKey("A");
        Map<MutableKey, String> map = new HashMap<>();

        map.put(key, "value");
        System.out.println(map.get(new MutableKey("A")));

        key.setCode("B");

        System.out.println(map.get(new MutableKey("A")));
        System.out.println(map.get(new MutableKey("B")));
    }
}
```

```bash
javac -encoding UTF-8 MutableKeyDemo.java
java MutableKeyDemo
```

**Stdout thường gặp trên JDK 17:**

```text
value
null
null
```

**Quan trọng:** đây là ví dụ minh họa tình huống nguy hiểm, **không nên lấy kết quả lookup cuối làm bảo đảm trong mọi hash collision/implementation**. Khi key mutate, behavior tương ứng không còn hợp đồng sử dụng HashMap đúng cách. Phép `get(new MutableKey("B"))` có thể trả kết quả phụ thuộc hash bucket/collisions và chi tiết table state.

Hướng đúng là dùng immutable key như `record Key(String code) {}`, bảo đảm các components tham gia equality không đổi.

## 52. `equals` của record với mutable elements

Record sinh `equals/hashCode` dựa trên components, nhưng **điều này không tự làm components bất biến**.

Ví dụ:

```java
record Group(List<String> values) {
}
```

Nếu `values` là mutable ArrayList, sau khi mutate:
- `group.toString()` có thể đổi.
- `group.hashCode()` có thể đổi vì hash của list đổi.
- `group.equals(other)` có thể đổi theo content.

Vì vậy record dùng làm key **cần snapshot nested mutable components** hoặc chọn immutable types.

### Cấu trúc phù hợp

```java
record Group(List<String> values) {
    Group {
        values = List.copyOf(values);
    }
}
```

Với List<String>, object graph theo components bất biến, generated equals/hashCode phản ánh immutable values.

## 53. Immutability và builder pattern

Builder thường là **mutable construction helper**:
- Caller thêm data trong nhiều bước.
- `build()` tạo **immutable snapshot**.
- Sau `build()`, caller có thể tiếp tục sửa builder mà không ảnh hưởng object đã tạo.

Sai:

```java
class Config {
    private final List<String> values;

    Config(Builder builder) {
        values = builder.values; // Alias tới builder mutable list.
    }
}
```

Nếu builder sửa list sau khi build, Config “bất biến” bị ảnh hưởng.

Đúng:
- `values = List.copyOf(builder.values)` nếu String immutable.
- Hoặc deep-copy nested mutable parts.
- Builder không expose reference tới private internal immutable snapshot.

## 54. Chương trình: builder không làm thay object đã build

Lưu **`ImmutableBuilderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Config {
    private final List<String> endpoints;

    private Config(List<String> source) {
        endpoints = List.copyOf(source);
    }

    List<String> endpoints() {
        return endpoints;
    }

    static final class Builder {
        private final List<String> values = new ArrayList<>();

        Builder add(String endpoint) {
            values.add(endpoint);
            return this;
        }

        Config build() {
            return new Config(values);
        }
    }
}

public class ImmutableBuilderDemo {
    public static void main(String[] args) {
        Config.Builder builder = new Config.Builder();
        builder.add("/users");

        Config first = builder.build();
        builder.add("/orders");

        Config second = builder.build();

        System.out.println("first = " + first.endpoints());
        System.out.println("second = " + second.endpoints());
    }
}
```

```bash
javac -encoding UTF-8 ImmutableBuilderDemo.java
java ImmutableBuilderDemo
```

**Stdout:**

```text
first = [/users]
second = [/users, /orders]
```

Hai immutable Config snapshots độc lập với mutable builder. Builder là mutable, nhưng object kết quả bất biến theo data model List<String>.

## 55. Functional update: tạo object mới thay vì mutate

Một immutable value object thường cung cấp operations “with” hoặc “plus” trả object mới:

```java
record Counter(int value) {
    Counter increment() {
        return new Counter(value + 1);
    }
}
```

`counter.increment()` **không** sửa `counter`, mà trả một Counter mới có value lớn hơn.

### Chương trình

Lưu **`FunctionalUpdateDemo.java`**:

```java
record Counter(int value) {
    Counter increment() {
        return new Counter(value + 1);
    }
}

public class FunctionalUpdateDemo {
    public static void main(String[] args) {
        Counter before = new Counter(4);
        Counter after = before.increment();

        System.out.println("before = " + before.value());
        System.out.println("after = " + after.value());
        System.out.println("same instance = " + (before == after));
    }
}
```

```bash
javac -encoding UTF-8 FunctionalUpdateDemo.java
java FunctionalUpdateDemo
```

**Stdout:**

```text
before = 4
after = 5
same instance = false
```

Functional update giúp code rõ dữ liệu “trước/sau”, thường thuận lợi trong concurrent programming hoặc event-driven systems. Cần cân đối chi phí allocations với lợi ích reasoning, không mặc định mọi object mutable là lỗi.

## 56. Deep immutability không đòi cấm mọi lazy cache

Một class có thể **bất biến về mặt logic (observational/logical immutability)** trong khi có một cache nội bộ thay đổi nhưng không làm đổi kết quả nghiệp vụ được công bố.

Ví dụ memoize một giá trị tính toán:
- Giá trị kết quả phải ổn định;
- Cache không được lộ ra;
- Các cập nhật cache phải thread-safe khi class được chia sẻ;
- Không gây side effects không phù hợp với contract.

Đây là **khác biệt giữa vật lý tuyệt đối không mutate bit nào** và **không thay đổi trạng thái logic quan sát được**.

Tuy nhiên nếu định nghĩa bài toán yêu cầu **deep structural immutability tuyệt đối**, một hidden mutable cache vẫn là mutation nội bộ. Khi tài liệu hóa, hãy dùng từ chính xác: “immutable về mặt quan sát đối với API” hay “cấu trúc không có mutable state”.

### Tránh cache gây race

Một `private String cached;` không tự thread-safe. Có thể dùng initialization eager, volatile/synchronized, hoặc cơ chế concurrent phù hợp. Việc chỉ thêm `final` cho field chứa mutable cache không giải quyết publication race.

## 57. Deep immutability và bảo mật dữ liệu đầu vào

Giả sử một auth token được biểu diễn bằng `char[]` vì ứng dụng muốn xóa ký tự khỏi memory sau khi dùng. Nếu class lưu direct alias:

```java
final class SecretBox {
    private final char[] secret;

    SecretBox(char[] secret) {
        this.secret = secret;
    }
}
```

caller có thể sửa/xóa array làm thay đổi state. Sao chép array cho snapshot có thể bảo vệ dữ liệu đầu vào, nhưng cũng **tạo thêm bản sao secret trong memory** mà cần có chính sách xóa/cân nhắc rõ.

**Đánh đổi:** deep immutability và secret lifecycle đôi khi mâu thuẫn; một secret holder cần zeroization có thể chủ động **mutable** theo protocol bảo mật. Không nên luôn ép immutable chỉ vì “bất biến tốt hơn”.

Chọn thiết kế dựa trên threat model và contract quản lý resource/lifecycle, không chỉ style.

## 58. Bất biến và serialization/ORM/frameworks

Một immutable value object có thể được serialize, persist hoặc dùng trong ORM, nhưng:
- Một framework có thể yêu cầu constructor, setters, reflection access hoặc proxies.
- Deserialization có thể tạo object thông qua cơ chế đặc thù.
- Entity có identity/vòng đời riêng thường mutable theo nghiệp vụ.
- Có thể tách **mutable persistence entity** khỏi **immutable read model/DTO**.

Đừng làm class mutable chỉ vì framework “thường vậy” khi use case value object có thể thiết kế riêng; cũng đừng bỏ qua ràng buộc framework và khẳng định mọi immutable class đều tích hợp tự nhiên.

**Một snapshot DTO immutable** là lựa chọn hay khi xuất data từ entity đang đổi và cần tránh caller sửa state của persistence context.

## 59. Chi phí của deep copy

Deep copy có thể:
- Tốn CPU tương ứng số phần tử/độ sâu.
- Tăng memory allocations và GC pressure.
- Đòi duyệt object graph lớn.
- Làm mất identity/reference-sharing mong muốn nếu copy thiếu suy nghĩ.
- Gây chậm ở API hot path nếu getter luôn copy mảng lớn.

Không có một quy tắc “phải deep-copy toàn bộ ứng dụng”.

Các lựa chọn thay thế:
- Chọn **immutable component types** từ đầu.
- Chuyển đổi mutable input thành compact immutable representation.
- Dùng **persistent collections**/structural sharing nếu thay phiên bản dữ liệu thường xuyên.
- Không expose mutable internals, cung cấp read-only primitive queries.
- Giới hạn snapshot vào miền dữ liệu thực sự cần độc lập.

### Ví dụ getter thiết kế hẹp

Thay vì:

```java
int[] values() {
    return values.clone();
}
```

nếu caller chỉ cần đọc phần tử/sum, có thể cung cấp:

```java
int size() {
    return values.length;
}

int get(int index) {
    return values[index];
}
```

Không phải cứ getter phải trả toàn bộ internal structure. API hẹp giúp giảm nhu cầu copy lớn và tăng encapsulation.

## 60. Persistent immutable data structures và structural sharing

Một **persistent data structure** giữ được các phiên bản trước sau khi cập nhật; operations tạo phiên bản mới mà có thể chia sẻ **những nhánh đã bất biến** giữa các phiên bản.

```text
Version 1 ──► immutable node A ──► immutable node B
Version 2 ──► immutable node C ──► immutable node B
                                    shared safely
```

Vì node B immutable, chia sẻ nó giữa hai versions không tạo alias mutation.

Đừng nhầm:
- “Persistent” trong khái niệm data structure không nhất thiết có nghĩa lưu đĩa/database.
- “Structural sharing” không có nghĩa copy nông một mutable node rồi để ai cũng mutate.
- Java Collections Framework `ArrayList` không tự là persistent immutable vector chỉ vì bọc bằng unmodifiable view.

Persistent collections có ích với snapshots lớn, nhiều phiên bản và functional updates, nhưng chọn library/implementation phải đánh giá constraints thực tế.

## 61. Quy trình thiết kế class bất biến sâu

**Bước 1 — Xác định state:** những field/value nào tạo ra identity/value của object? Có nested objects nào ảnh hưởng kết quả getter/equals/hashCode?

**Bước 2 — Chọn type:** ưu tiên primitives và immutable components (`String`, `Instant`, nested immutable records) nếu có thể.

**Bước 3 — Giới hạn mutators:** không có setters thay đổi state đã hứa cố định; dùng factories/with-methods trả object mới khi cần.

**Bước 4 — Chống subclass phá contract:** dùng `final class` hoặc record khi phù hợp; nếu inheritance cần thiết, design invariants và extension points nghiêm túc.

**Bước 5 — Defensive copy đầu vào:** arrays, collections và mutable elements phải copy/chuyển representation theo ranh giới sở hữu.

**Bước 6 — Defensive API đầu ra:** getters không trả mutable state trực tiếp; trả immutable value/snapshot/query hẹp.

**Bước 7 — Validate invariants:** không cho invalid/null elements nếu contract không cho phép; chuẩn hóa dữ liệu trước khi giữ.

**Bước 8 — Kiểm tra alias paths:** caller sửa input sau construction, sửa getter result, sửa nested child qua reference khác.

**Bước 9 — Xem concurrency/publication:** object không thoát constructor quá sớm, được publish đúng; source snapshot phải nhất quán khi copied từ mutable concurrent source.

**Bước 10 — Test value semantics:** cùng values có bằng nhau theo yêu cầu không, hash ổn định không, serialized form có đúng contract không.

## 62. Checklist kiểm thử class bất biến

Tạo một object từ input mutable rồi thử:

1. Thay cấu trúc input collection sau constructor.
2. Thay một mutable input element sau constructor.
3. Lấy getter collection rồi gọi `add/remove/clear`.
4. Lấy nested element từ getter rồi gọi mutator.
5. Lấy getter array rồi sửa phần tử.
6. Nếu multi-dimensional array, sửa inner row.
7. Gọi `toString` trước/sau các phép sửa bên ngoài.
8. Kiểm tra `equals/hashCode` trước/sau mutation bên ngoài.
9. Tạo hai object từ cùng input rồi thử sửa một reference.
10. Thử null elements/keys theo contract.
11. Kiểm tra thứ tự collection nếu nghiệp vụ yêu cầu order.
12. Chạy test trong nhiều threads khi source là mutable concurrent state có protocol snapshot.
13. Kiểm tra không có mutable caches/escape qua getters gián tiếp.
14. Nếu builder được dùng lại, build lần hai không đổi lần một.
15. Đo chi phí copy với các input đủ lớn nếu performance quan trọng.

Nếu dữ liệu object quan sát từ getter đổi dù API hứa bất biến, tìm **alias còn mở** ở đầu vào, đầu ra hoặc một tầng nested.

## 63. Bài tập 1 — `final List` có sâu bất biến không?

```java
final List<String> names = new ArrayList<>();
names.add("An");
```

**Đáp án:** Không. Biến reference final không cho gán lại `names`, nhưng list object mutable. Cần xét ranh giới và API nếu muốn immutable snapshot.

## 64. Bài tập 2 — Unmodifiable view có là snapshot không?

```java
List<String> input = new ArrayList<>();
List<String> view = Collections.unmodifiableList(input);
input.add("Java");
```

**Đáp án:** Không. `view` đọc thấy `Java` vì backing list được thay. Đây là unmodifiable view, không phải detached immutable snapshot.

## 65. Bài tập 3 — `List.copyOf` đã đủ với MutableUser?

```java
List<MutableUser> users = ...;
List<MutableUser> copy = List.copyOf(users);
```

**Đáp án:** Chưa đủ nếu `MutableUser` có state observable và mutators qua aliases. Outer list structure unmodifiable, nhưng phần tử là cùng MutableUser references. Cần immutable user value snapshot hoặc deep copy đúng domain.

## 66. Bài tập 4 — Mảng `int[]` cần sao chép mấy lần?

Class nhận `int[]` rồi có accessor trả `int[]`, cam kết snapshot bất biến.

**Đáp án:** Sao chép ở **constructor** để loại alias của input và sao chép ở **getter** để không lộ internal array. Với một chiều int[] như vậy, clone sao chép các primitive elements đầy đủ.

## 67. Bài tập 5 — `int[][]` clone ngoài có đủ?

```java
int[][] copied = source.clone();
```

**Đáp án:** Không. Các rows là int[] objects được chia sẻ, nên caller vẫn có thể sửa nội dung hàng. Cần copy mỗi row hoặc immutable representation khác.

## 68. Bài tập 6 — Record có List mutable

```java
record Group(List<String> names) {}
```

**Đáp án:** Record là final và component reference final, nhưng mặc định vẫn giữ list alias mutable. Dùng compact constructor `names = List.copyOf(names);` với `String` immutable để tạo snapshot phù hợp.

## 69. Bài tập 7 — Record có List<StringBuilder>

```java
record Group(List<StringBuilder> names) {
    Group {
        names = List.copyOf(names);
    }
}
```

**Đáp án:** Vẫn chỉ shallow snapshot của list. `StringBuilder` elements mutable được chia sẻ. Cần chuyển mỗi Builder sang immutable String hoặc copy và không expose mutators.

## 70. Bài tập 8 — `String` cần clone không?

Một immutable Person chỉ giữ `String name` được caller cấp.

**Đáp án:** Thông thường không. `String` immutable; caller không thể mutate String object qua alias. Có thể chia sẻ an toàn về mutation.

## 71. Bài tập 9 — `Date` trong final field

```java
final class Event {
    private final Date when;
    Event(Date when) { this.when = when; }
}
```

**Đáp án:** Chưa sâu bất biến nếu caller giữ mutable Date và sửa `setTime`. Có thể copy Date vào/ra hoặc dùng `Instant` immutable.

## 72. Bài tập 10 — Deep copy có tự immutable?

```java
List<StringBuilder> deep = deepCopyBuilders(source);
deep.get(0).append("!");
```

**Đáp án:** Không. Deep copy làm objects độc lập với source, nhưng bản deep vẫn mutable nếu API cho phép. Cần thêm immutable representation / encapsulation để có immutable object.

## 73. Bài tập 11 — `Map.copyOf` với nested list

```java
Map<String, List<String>> copy = Map.copyOf(input);
```

**Đáp án:** Outer map unmodifiable, nhưng values có thể mutable lists. Phải snapshot từng list (và nested mutable elements nếu có).

## 74. Bài tập 12 — Deep immutability và final class

Một class final nhưng có `void increment()` sửa `int count`.

**Đáp án:** Class final chỉ cấm subclass, không cấm mutation. Đối tượng **không bất biến**.

## 75. Bài tập 13 — Builder sau khi build

Builder giữ `ArrayList`; object Config chỉ giữ direct alias tới list builder.

**Đáp án:** Config có thể thay khi builder thêm phần tử sau `build()`. Constructor/build nên copy snapshot và không expose mutable state.

## 76. Bài tập 14 — Dùng immutable key để làm gì?

Một object có các fields tham gia `hashCode` bị mutate sau khi put vào HashMap.

**Đáp án:** Lookup có thể thất bại hoặc cho hành vi không mong muốn. Immutable keys với equality/hash ổn định giúp tránh lỗi.

## 77. Bài tập 15 — Nested immutable record và List.copyOf

```java
record A(String s) {}
record B(List<A> items) {
    B {
        items = List.copyOf(items);
    }
}
```

**Đáp án:** Với `A` chỉ chứa String và không có mutable state ngoài, `B` có deep immutability đối với graph này. Không cần clone riêng các immutable `A` elements.

## 78. Bài tập 16 — `Collections.unmodifiableList(new ArrayList<>(src))`

**Hỏi:** có snapshot sâu không?

**Đáp án:** Có **shallow snapshot** của outer list và bọc thành unmodifiable view của bản copy; nếu elements mutable thì vẫn chia sẻ element aliases. Với immutable elements, nó có thể đáp ứng yêu cầu sâu của model.

## 79. Bài tập 17 — Mutable array trong record equality

```java
record Data(int[] values) {}
```

**Đáp án:** Generated record equals/hashCode không dùng deep content equality cho array component. Ngoài chuyện defensive copy, muốn value semantics theo nội dung array phải thiết kế equals/hashCode phù hợp hoặc dùng immutable value representation khác.

## 80. Bài tập 18 — Copy graph có chu trình

Graph A→B→A; copy đệ quy không nhớ objects đã đi qua.

**Đáp án:** Có thể lặp vô hạn hoặc stack overflow. Cần quản lý original-to-copy identity mapping và placeholder hợp lệ để giữ cycles và shared aliases nếu việc deep copy thật sự là yêu cầu.

## 81. Bài tập 19 — Snapshot đang có concurrent writers

Thread A mutate một ArrayList; Thread B gọi `List.copyOf(list)` không synchronized.

**Đáp án:** Không có cam kết snapshot nguyên tử/nhất quán; còn có data race vì ArrayList không thread-safe. Cần synchronization/immutable publication/concurrent structure có contract phù hợp.

## 82. Bài tập 20 — Hidden mutable cache

Object trả cùng kết quả business, nhưng dùng cache field mutable để tránh tính lại.

**Đáp án:** Có thể được mô tả là immutable về mặt logic/quan sát nếu cache không ảnh hưởng behavior đã hứa và được xử lý thread-safe; không phải physically deep immutable tuyệt đối. Cần dùng thuật ngữ và contract rõ ràng.

## 83. Các sai lầm thường gặp

| Sai lầm | Lý do sai | Hướng khắc phục |
| --- | --- | --- |
| “`final` field làm child bất biến” | Khóa reference, không khóa referent | Dùng immutable child/copy |
| “`final class` nghĩa immutable” | Vẫn có mutable fields/methods | Thiết kế state đúng |
| “Record luôn bất biến sâu” | Component có thể mutable | Compact constructor, immutable types |
| “Unmodifiable collection là snapshot” | View có thể theo backing | `copyOf`/snapshot |
| “`List.copyOf` copy từng element” | Shallow copy references | Chọn immutable elements/deep copy |
| “`new ArrayList<>(input)` là deep copy” | Chỉ copy outer structure | Copy mutable nested state |
| “Copy trong constructor là đủ” | Getter có thể lộ internal alias | Defensive copy cả output |
| “Getter trả copy nhưng giữ input gốc cũng được” | Caller có alias đầu vào | Defensive copy input |
| “Clone int[][] là deep” | Inner rows vẫn chia sẻ | Copy từng row |
| “Dùng `Collections.unmodifiableMap` đóng băng dữ liệu” | Chỉ view của backing map | Copy snapshot và nested values |
| “Deep copy tự làm object immutable” | Bản copy vẫn có mutators | Dùng immutable representation |
| “Immutable thì phải copy mọi String” | String đã immutable | Share immutable subgraphs |
| “Record array equality so contents” | Arrays dùng reference equality trong generated record methods | Custom value equality hoặc representation khác |
| “Java có `deep final`” | Không có modifier này | Design/API/ownership |
| “Immutable nghĩa concurrency không cần nghĩ nữa” | Safe publication/source snapshot vẫn cần đúng | Theo Java Memory Model |
| “`volatile` outer ref khóa inner List” | Inner mutable vẫn có race | Immutable state hoặc đồng bộ |
| “Clone mọi entity như value object” | Có thể phá identity/lifecycle | Tách aggregate ID/snapshot |
| “HashMap key mutable vẫn tra cứu bình thường” | Hash/equality có thể đổi | Immutable keys |
| “Sao chép graph chỉ cần recursion” | Cycles và shared aliases | Identity mapping |
| “Immutable snapshot miễn phí” | Có chi phí memory/CPU | Immutable types, structural sharing |
| “Không có setter nghĩa deep immutable” | Mutate qua getter/alias | Audit tất cả reference paths |
| “Deep immutable bắt buộc không có cache nào” | Logical vs physical immutability khác nhau | Định nghĩa contract và đồng bộ cache |

## 84. Checklist ra quyết định khi review Java class

1. **Đã định nghĩa rõ bất biến là gì** (physical hay observational; graph nào tính là state)?
2. Có những references tới mutable objects nào trong fields/components?
3. `final` đang cấm gán lại reference hay thực sự loại mutation?
4. Constructor có sao chép những mutable inputs không?
5. Getter có trả mutable internal array/list/map/object không?
6. Có nested elements mutable cần deep-copy không?
7. Nếu dùng `List.copyOf`, elements có immutable thật không?
8. Có đang nhầm `unmodifiable view` với detached snapshot không?
9. Với nested list/map, đã copy đủ các tầng cần thiết chưa?
10. Với `int[][]`, có copy cả outer và từng inner row không?
11. Nếu dùng record, component accessor có làm lộ mutable object không?
12. Nếu dùng array component trong record, equals/hashCode có đúng value semantics không?
13. Những mutable elements có thể được thay qua external aliases không?
14. Nếu input là `Date`/`StringBuilder`, đã thay bằng immutable type hoặc snapshot chưa?
15. Nếu dùng builder, việc sửa builder sau build có ảnh hưởng built object không?
16. Class có setter hoặc method thay internal state sau construction không?
17. Class có thể subclass và phá invariant không?
18. Nếu có hidden cache, contract logical immutability và thread-safety đã rõ chưa?
19. Object graph có cycles/shared aliases khiến deep copy cần identity map không?
20. Có đang deep-copy một entity mà lẽ ra cần giữ identity không?
21. Có cần snapshot nhất quán khi source bị nhiều threads sửa không?
22. Publication/visibility của final immutable graph giữa threads có đúng không?
23. Hash/equality của object có ổn định khi được dùng làm map key không?
24. Có thể giảm chi phí bằng immutable components/structural sharing hay query hẹp không?
25. Các tests đã thử mutate input, getter result và nested child sau construction chưa?

## 85. Ghi nhớ

- **Bất biến nông** nói về ràng buộc ở tầng ngoài (reference/structure/API), trong khi **bất biến sâu** đòi những state có thể quan sát trong graph liên quan không thay đổi sau construction.
- **`final` không làm mutable referent bất biến**; `final class` và record cũng không tự bảo đảm deep immutability.
- **`Collections.unmodifiableList` là view**; **`List.copyOf` là unmodifiable snapshot tầng collection đối với nguồn mutable**, nhưng vẫn chia sẻ mutable elements.
- **Shallow copy** tạo outer structure mới, chia sẻ nested references; **deep copy** phải tách đủ những mutable objects thuộc phạm vi snapshot.
- **Deep copy không tự làm bản sao immutable**: cần đóng mutators và tránh lộ mutable aliases.
- **Array một chiều primitive** có thể clone để tách dữ liệu; **mảng hai chiều** cần clone từng row.
- **Record với String/primitives/immutable components** thuận lợi để tạo value objects; record với List/array/Date/StringBuilder vẫn có thể “bất biến giả”.
- **Defensive copy cả input lẫn output** nếu owner giữ mutable array/object nội bộ.
- **Bất biến sâu không yêu cầu clone immutable values** như String/Instant; có thể chia sẻ safely khi graph được thiết kế đúng.
- **Concurrency, publication, ownership, identity và performance** vẫn cần được xem xét; immutable graph giúp giảm rủi ro mutation nhưng không thay thế mọi hợp đồng đồng thời.
- Cách thiết kế bền vững nhất thường là **chọn immutable components từ đầu**, chỉ copy mutable boundaries cần thiết và công bố API vừa đủ để bảo vệ invariant.
