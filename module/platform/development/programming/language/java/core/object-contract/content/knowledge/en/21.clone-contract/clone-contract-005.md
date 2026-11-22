# `super.clone()` sao chép nông các trường trong Java

## 1. `super.clone()` làm gì?

Trong Java, `java.lang.Object` định nghĩa phương thức `protected Object clone() throws CloneNotSupportedException`. Một lớp có thể override `clone()` rồi gọi `super.clone()` để tạo một đối tượng mới có trạng thái ban đầu được sao chép từ đối tượng đang gọi. Nếu chuỗi gọi đi tới triển khai của `Object.clone()`, thao tác này thực hiện **sao chép nông** (*shallow copy*) các trường.

Hãy tưởng tượng đối tượng `Document` có các trường:

```text
Document original
├── title = "Java"           (tham chiếu String)
├── version = 1              (int)
└── tags ──────────────┐
                       ▼
                ArrayList ["core"]

Document clone (sau super.clone)
├── title = "Java"           (cùng tham chiếu String ban đầu)
├── version = 1              (bản sao giá trị int)
└── tags ──────────────┘     (cùng đối tượng ArrayList)
```

`original` và `clone` là **hai đối tượng `Document` khác nhau** (`original != clone`), nhưng trường `tags` của cả hai lại trỏ tới **cùng một** `ArrayList`.

- **Trường nguyên thủy** (`int`, `long`, `boolean`, ...): giá trị được chép sang trường của đối tượng mới; gán lại trường ở một bản không đổi trường của bản còn lại.
- **Trường tham chiếu** (`String`, `List`, array, object nghiệp vụ, ...): chép **giá trị tham chiếu**, không tự tạo đối tượng con mới. Hai bản có thể cùng trỏ tới một đối tượng con.
- **Trường `static`** thuộc về lớp, không phải trạng thái của từng instance; `clone` không tạo bản sao độc lập của những trường này.
- **Trường `final`** cũng có giá trị được sao chép. Nếu đó là tham chiếu tới một đối tượng mutable, `final` không giúp tách đối tượng con.
- **Constructor của lớp được clone không được chạy lại** bởi cơ chế `Object.clone()`; trạng thái được tạo bằng sao chép trường, không phải khởi tạo một instance qua constructor thông thường.

Như vậy, `super.clone()` không có nghĩa là "sao chép toàn bộ đồ thị đối tượng". Nó chỉ tạo lớp vỏ đối tượng mới với các giá trị trường tương ứng, khi lời gọi đi tới cơ chế clone mặc định của `Object`.

## 2. Điều kiện để gọi được `super.clone()`

`Object.clone()` là phương thức `protected`, vì vậy lớp con có thể gọi `super.clone()` bên trong chính triển khai của mình. Tuy nhiên, nếu đối tượng thực tế **không thực hiện interface `Cloneable`**, triển khai `Object.clone()` sẽ ném `CloneNotSupportedException` (mảng Java có cơ chế clone riêng).

```java
class Example implements Cloneable {
    @Override
    public Example clone() {
        try {
            return (Example) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
```

Đây là một khai báo lớp hoàn chỉnh nhưng chưa có `main`. Những điểm cần hiểu:

1. `Cloneable` là **marker interface** trong `java.lang`, không khai báo phương thức `clone()`. Việc `implements Cloneable` không tự sinh một API `clone()` public để caller sử dụng.
2. Lớp chủ động override `clone()` thành `public` nếu muốn người dùng gọi được. Tăng phạm vi truy cập từ `protected` thành `public` là hợp lệ.
3. Kiểu trả về `Example` thay vì `Object` là **covariant return type** hợp lệ, giúp caller không phải ép kiểu kết quả. Ép kiểu `(Example)` bên trong cần thiết vì `super.clone()` có kiểu khai báo `Object`.
4. `super.clone()` được gọi bên trong `try` vì chữ ký của `Object.clone()` khai báo ngoại lệ checked `CloneNotSupportedException`.
5. Với lớp `Example` thực hiện `Cloneable` và dùng cơ chế mặc định, lỗi trên là bất thường; mã chuyển thành `AssertionError` để biểu thị giả định thiết kế đã bị phá. Một lớp khác cũng có thể công khai `throws CloneNotSupportedException` tùy API của mình.

Đừng nhầm **đã khai báo `Cloneable`** với việc **đã có API sao chép hoàn chỉnh, đúng nghĩa nghiệp vụ**. `Cloneable` chỉ cho phép cơ chế clone của `Object`; việc tách dữ liệu mutable, xác minh bất biến và xử lý các quan hệ giữa các trường vẫn là trách nhiệm của lớp.

## 3. Hợp đồng thông thường: khác danh tính nhưng trạng thái bắt đầu tương ứng

Nếu `x.clone()` được thiết kế theo quy ước phổ biến:

- Bản sao thường có **runtime class tương ứng với bản gốc**.
- Bản sao thường là đối tượng riêng biệt: `x.clone() != x`.
- Trong nhiều lớp giá trị, ngay sau khi clone, `x.clone().equals(x)` thường là `true`, nhưng **không phải bảo đảm tuyệt đối** cho mọi kiểu dữ liệu hay mọi override tùy biến.

Lý do là một lớp có thể định nghĩa `equals()` theo **danh tính** (mặc định `Object.equals`), lúc đó hai đối tượng khác tham chiếu không bằng nhau. Cũng có thể có lớp override `clone()` với quy tắc đặc biệt. Vì thế, **clone và equals là hai hợp đồng khác nhau**; không được suy luận rằng clone chắc chắn khiến `equals` bằng `true`.

Nếu gọi tới `Object.clone()`, đối tượng mới có cùng **runtime class** với bản gốc và các trường được chép theo cơ chế mặc định. `super.clone()` không cắt phần trạng thái ở lớp con: một lời gọi hợp lệ trên đối tượng lớp con sẽ sao chép những trường instance thuộc cả lớp cha lẫn lớp con. Tuy nhiên, nếu có lớp cha **override `clone()`** thì lời gọi `super.clone()` của lớp con đi vào override lớp cha đó, có thể có logic bổ sung; không được giả định mọi `super.clone()` đều trực tiếp gọi ngay `Object.clone()`.

## 4. Ví dụ Java 17: bản sao nông cùng giữ một danh sách

Tạo tệp độc lập `CloneShallowDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CloneShallowDemo {
    static final class Document implements Cloneable {
        private String title;
        private List<String> tags;

        Document(String title, List<String> tags) {
            this.title = title;
            this.tags = new ArrayList<>(tags);
        }

        @Override
        public Document clone() {
            try {
                return (Document) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        Document detachedCopy() {
            Document copy = clone();
            copy.tags = new ArrayList<>(tags);
            return copy;
        }

        void addTag(String value) {
            tags.add(value);
        }

        void rename(String value) {
            title = value;
        }
    }

    public static void main(String[] args) {
        Document original = new Document("Java", List.of("core"));
        Document shallow = original.clone();

        System.out.println("different objects: " + (original != shallow));
        System.out.println("shared tags: "
                + (original.tags == shallow.tags));

        shallow.rename("Spring");
        System.out.println("original title: " + original.title);

        shallow.addTag("concurrency");
        System.out.println("original tags after shallow: "
                + original.tags);

        Document detached = original.detachedCopy();
        System.out.println("detached tags: "
                + (original.tags != detached.tags));

        detached.addTag("collections");
        System.out.println("original tags after detached: "
                + original.tags);
        System.out.println("detached tags after edit: "
                + detached.tags);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac CloneShallowDemo.java
java CloneShallowDemo
```

Stdout:

```text
different objects: true
shared tags: true
original title: Java
original tags after shallow: [core, concurrency]
detached tags: true
original tags after detached: [core, concurrency]
detached tags after edit: [core, concurrency, collections]
```

### Vì sao kết quả như vậy?

1. `original.clone()` tạo một `Document` mới nên `original != shallow` là `true`.
2. `original.tags == shallow.tags` là `true`: hai trường chứa cùng tham chiếu tới `ArrayList` do clone nông.
3. Gọi `shallow.rename("Spring")` chỉ gán lại trường `title` của **bản shallow**; trường `title` trong `original` vẫn là `"Java"`. `String` cũng là immutable, nên không có chuyện sửa nội dung chuỗi dùng chung.
4. Gọi `shallow.addTag("concurrency")` thay đổi chính đối tượng `ArrayList` được hai bản dùng chung, vì vậy bản gốc cũng nhìn thấy phần tử mới.
5. `detachedCopy()` bắt đầu bằng bản sao nông, sau đó thay trường `copy.tags` bằng `new ArrayList<>(tags)`. Lúc này bản sao có **danh sách độc lập**. Thêm `"collections"` chỉ ảnh hưởng danh sách của `detached`.

**Giới hạn của `new ArrayList<>(tags)`:** đây chỉ là sao chép nông ở **cấp danh sách**. Trong ví dụ các phần tử là `String` bất biến nên đủ để tách trạng thái có thể thay đổi. Nếu danh sách chứa đối tượng mutable như `Address` có setter, hai danh sách vẫn có thể giữ **cùng từng instance `Address`**; muốn tách toàn bộ trạng thái thì phải sao chép từng phần tử theo chính sách rõ ràng.

## 5. Sao chép nông, sao chép sâu và số cấp cần tách

### Sao chép nông (*shallow copy*)

`super.clone()` sao chép các trường instance một lần:

```text
A ── address ──> Address { city = "Hue" }
B ── address ──┘
```

`A` và `B` là hai instance riêng, nhưng việc sửa `address.city` qua một phía được nhìn thấy qua phía kia.

### Sao chép sâu (*deep copy*)

Nếu nghiệp vụ đòi hỏi **không chia sẻ trạng thái mutable**, phải tạo các đối tượng con mới cần thiết:

```text
A ── address ──> Address { city = "Hue" }
B ── address ──> Address { city = "Hue" }  (instance riêng)
```

Không có một mức "deep copy" phổ quát duy nhất: cần xác định những thành phần nào được phép dùng chung. Những đối tượng immutable như `String` thường có thể chia sẻ an toàn; các entity có danh tính dùng chung, cache hoặc liên kết đối tượng có thể có quy tắc khác. Với đồ thị đối tượng có chu trình, quá trình sao chép sâu cần quản lý các đối tượng đã gặp để tránh đệ quy vô hạn và giữ đúng các quan hệ chia sẻ.

### Sao chép nông rồi tách từng trường

Với các trường có thể gán lại, mã thường có dạng:

```java
@Override
public MyType clone() {
    try {
        MyType copy = (MyType) super.clone();
        copy.mutableList = new ArrayList<>(mutableList);
        copy.numbers = numbers.clone();
        return copy;
    } catch (CloneNotSupportedException ex) {
        throw new AssertionError(ex);
    }
}
```

Đoạn trên là **khung minh họa** cho lớp `MyType implements Cloneable` có trường `mutableList` và `numbers` phù hợp. Nó không phải chương trình độc lập và vẫn có thể cần sao chép tiếp những đối tượng mutable bên trong `mutableList`.

Nếu các trường tham chiếu cần tách được khai báo `final`, ta không thể đơn giản gán lại `copy.mutableList` bên trong `clone`. Lúc đó thiết kế với **copy constructor** hoặc factory tạo đối tượng mới thường rõ ràng hơn và cho phép khởi tạo trường `final` theo bất biến mong muốn.

## 6. Clone mảng: tạo mảng mới nhưng không tự clone từng phần tử

Mảng Java hỗ trợ `clone()` dù người viết không khai báo `implements Cloneable`; mỗi mảng có phương thức clone riêng, trả kiểu mảng tương ứng. Nó cũng thực hiện **sao chép nông**.

- Với `int[]`, `clone()` tạo mảng mới chứa các số được sao chép. Sửa một phần tử của bản sao không sửa mảng gốc.
- Với `String[]`, `clone()` tạo mảng mới nhưng các phần tử là tham chiếu `String` được chép; `String` immutable nên chia sẻ các chuỗi thường an toàn.
- Với `Person[]`, `clone()` tạo mảng mới nhưng từng phần tử ban đầu vẫn có thể trỏ tới đúng các đối tượng `Person` cũ. Sửa một đối tượng `Person` thông qua bản sao sẽ được nhìn thấy qua bản gốc.
- Với `int[][]`, `clone()` của mảng ngoài chỉ tạo **mảng ngoài mới**; từng hàng `int[]` vẫn là các tham chiếu dùng chung. Muốn độc lập ở hai cấp cần clone từng hàng.

Một chương trình độc lập thứ hai làm rõ cả điều kiện `Cloneable`, constructor và mảng.

Tạo tệp `CloneMechanicsDemo.java`:

```java
public class CloneMechanicsDemo {
    static final class Unmarked {
        Object attempt() throws CloneNotSupportedException {
            return super.clone();
        }
    }

    static final class Counted implements Cloneable {
        static int created;

        Counted() {
            created++;
        }

        @Override
        public Counted clone() {
            try {
                return (Counted) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }
    }

    public static void main(String[] args) {
        try {
            new Unmarked().attempt();
            System.out.println("unmarked allowed: true");
        } catch (CloneNotSupportedException ex) {
            System.out.println("unmarked rejected: true");
        }

        Counted original = new Counted();
        Counted copied = original.clone();
        System.out.println("constructor count: " + Counted.created);
        System.out.println("different Counted: " + (original != copied));
        System.out.println("same runtime class: "
                + (original.getClass() == copied.getClass()));

        int[][] source = {{1, 2}, {3}};
        int[][] outer = source.clone();
        System.out.println("new outer array: " + (source != outer));
        System.out.println("shared first row: "
                + (source[0] == outer[0]));

        outer[0][0] = 99;
        System.out.println("source first number: " + source[0][0]);

        int[][] detached = source.clone();
        for (int i = 0; i < detached.length; i++) {
            detached[i] = source[i].clone();
        }
        detached[0][0] = 7;
        System.out.println("source after row copies: "
                + source[0][0]);
        System.out.println("detached after row copies: "
                + detached[0][0]);
    }
}
```

Biên dịch và chạy:

```bash
javac CloneMechanicsDemo.java
java CloneMechanicsDemo
```

Stdout:

```text
unmarked rejected: true
constructor count: 1
different Counted: true
same runtime class: true
new outer array: true
shared first row: true
source first number: 99
source after row copies: 99
detached after row copies: 7
```

Giải thích:

- `Unmarked` không implements `Cloneable`, nên `Object.clone()` từ `attempt()` ném `CloneNotSupportedException`.
- Một đối tượng `Counted` được tạo bởi constructor thông thường. Gọi `clone()` không gọi lại constructor, nên `created` vẫn bằng `1`.
- `source.clone()` trả về mảng ngoài mới, nhưng `source[0] == outer[0]` vẫn đúng. Gán `outer[0][0] = 99` thực chất sửa hàng chung với mảng nguồn.
- Ở bước `detached`, từng hàng `int[]` cũng được clone. Vì thế gán `detached[0][0] = 7` không đổi `source[0][0]`.

Ví dụ giả định không có hàng `null` khi clone từng hàng. Nếu cấu trúc là mảng răng cưa cho phép hàng `null`, phải bảo vệ `source[i] == null` trước khi gọi `clone()`. Nếu các phần tử là đối tượng mutable thay vì `int`, clone hai tầng mảng vẫn chưa đồng nghĩa với sao chép sâu từng đối tượng phần tử.

## 7. Quan hệ với kế thừa và việc override `clone()`

Nếu một lớp cha `Base` có cơ chế clone được kế thừa, còn lớp con `Derived` bổ sung trường mới, việc gọi `Object.clone()` trên instance `Derived` sẽ sao chép trường instance của **toàn đối tượng `Derived`**, bao gồm trường lớp cha và lớp con. Tuy nhiên, việc sao chép các tham chiếu bổ sung của lớp con vẫn chỉ là sao chép nông.

Ví dụ khung:

```java
class Base implements Cloneable {
    int id;

    @Override
    public Base clone() {
        try {
            return (Base) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

class Derived extends Base {
    java.util.ArrayList<String> notes = new java.util.ArrayList<>();

    @Override
    public Derived clone() {
        Derived copy = (Derived) super.clone();
        copy.notes = new java.util.ArrayList<>(notes);
        return copy;
    }
}
```

Đây là **các khai báo lớp có thể đặt trong cùng tệp Java** (không có `main`), minh họa tầng cha sao chép nông trước và tầng con tách trường `notes` riêng của nó.

Điểm quan trọng:

1. `super.clone()` ở `Derived` gọi phiên bản `clone` của `Base`; phiên bản đó tiếp tục gọi `Object.clone()`.
2. `Base.clone()` trả về `Base` ở kiểu khai báo nhưng đối tượng clone thực tế là `Derived` khi receiver ban đầu là `Derived`. Ép kiểu `(Derived)` lúc này hợp lệ với cơ chế đã thiết kế.
3. Sau đó `Derived.clone()` sao chép thêm `notes` vì trường này tham chiếu dữ liệu có thể thay đổi. Nếu không làm bước này, bản gốc và bản clone sẽ dùng chung một danh sách.
4. Nếu có nhiều lớp con ở nhiều tầng, mỗi tầng có thể phải chịu trách nhiệm những tài nguyên mutable được thêm tại tầng đó. Cần giữ quy ước rõ ràng; việc clone trong hệ phân cấp mở rộng tùy ý có thể khó duy trì.

Không nên mặc định gọi `super.clone()` ở mọi cấp là đủ để bất biến hoặc tài nguyên nội bộ được xử lý đúng. Nếu lớp cha có trạng thái quan hệ phức tạp, các lớp con chưa biết rõ hợp đồng clone của lớp cha có thể tạo bản sao không hợp lệ.

## 8. Những bẫy với `final`, tài nguyên và liên kết đối tượng

### Trường `final` không đảm bảo deep copy

```java
private final java.util.List<String> tags;
```

Một lớp có trường trên không thể gán lại `copy.tags = new ArrayList<>(tags)` trong một phương thức `clone` thông thường. Cả hai bản được tạo bằng clone nông vẫn trỏ cùng danh sách; chỉ việc khai báo `final` **không biến danh sách thành immutable**. Nếu thiết kế cần danh sách riêng, copy constructor có thể khởi tạo trường `final` mới đúng cách.

### Tài nguyên hệ điều hành không nên sao chép vô thức

Các đối tượng chứa `FileInputStream`, socket, lock, transaction, thread hoặc handle native không thể mặc định có ý nghĩa khi chỉ copy các trường. Clone nông có thể khiến hai bản cùng giữ một tài nguyên, từ đó xảy ra đóng trùng, ghi đồng thời, sai ownership hoặc vi phạm bất biến.

Hãy định nghĩa rõ hành vi cần thiết: không hỗ trợ clone, tạo tài nguyên độc lập mới qua factory, hoặc chỉ sao chép dữ liệu cấu hình có thể chuyển giao. Đối với tài nguyên `AutoCloseable`, cơ chế quản lý vòng đời như `try-with-resources` vẫn cần được thiết kế riêng.

### Liên kết giữa các trường và giữa các object

Giả sử `left` và `right` của bản gốc cùng tham chiếu một đối tượng con, hoặc đối tượng con trỏ ngược về bản cha. Sao chép sâu không đơn thuần là gọi `clone` độc lập cho từng trường: có thể phải giữ **quan hệ dùng chung** (`left == right`) và sửa các con trỏ ngược đúng bản mới.

Với đồ thị có chu trình, nếu clone đệ quy mà không theo dõi đối tượng đã tạo thì có thể lặp vô hạn. Đây là lý do copy constructor/factory với quy tắc về danh tính, liên kết và bất biến rõ ràng thường phù hợp hơn cho mô hình có nhiều quan hệ.

## 9. Khi nào nên dùng `clone()`, khi nào nên chọn cách sao chép khác?

| Cách làm | Ưu điểm | Hạn chế/điều kiện |
| --- | --- | --- |
| `super.clone()` + điều chỉnh trường mutable | Có thể tái sử dụng sao chép trường mặc định, không cần truyền lại từng trường đơn giản. | Dễ bỏ sót tham chiếu mutable, khó xử lý `final`, kế thừa, constructor bất biến và tài nguyên. |
| Copy constructor `new Type(source)` | Có quyền tạo trạng thái mới, gán trường `final`, sao chép có chọn lọc và kiểm tra bất biến. | Cần chủ động liệt kê các dữ liệu cần sao chép, phải xác định xử lý lớp con. |
| Factory `Type.copyOf(source)` | API có thể nêu rõ chính sách copy, đôi khi tái sử dụng đối tượng immutable hợp lệ. | Phải có hợp đồng rõ về chia sẻ/sao chép và kiểu trả về. |
| Kiểu immutable/record | Ít cần copy phòng vệ khi mọi thành phần và dữ liệu con thật sự bất biến. | Record có thể chứa component mutable; immutable không tự động là bất biến sâu. |
| Sao chép thủ công từng thành phần/đồ thị | Kiểm soát rõ mức độ tách, ownership và xử lý chu trình. | Có thể tốn công và cần bộ nhớ trung gian để giữ quan hệ danh tính. |

Đối với các kiểu dữ liệu mới, Java không bắt buộc sử dụng `Cloneable` để có tính năng sao chép. Một copy constructor hoặc factory là lựa chọn thường dễ giải thích và kiểm thử. Nếu dùng `clone` vì tương thích API cũ hoặc vì lớp đã có hợp đồng clone rõ, cần kiểm tra kỹ tất cả trường tham chiếu.

Lưu ý rằng `clone` không phải là cơ chế serialization, không gọi lại constructor để đảm bảo các ràng buộc khởi tạo, và không tự động là giải pháp thread-safe. Nếu đối tượng đang được sửa đồng thời trong lúc clone, cần đồng bộ hoặc tạo snapshot nhất quán.

## 10. Những lỗi phổ biến và checklist kiểm tra

| Lỗi thường gặp | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng `super.clone()` là deep copy. | Hai đối tượng vẫn dùng chung list, mảng hoặc object mutable. | Xác định rõ trường nào cần tạo instance con mới. |
| Chỉ `implements Cloneable` rồi gọi `obj.clone()` ở ngoài lớp. | Interface không khai báo clone public; code có thể không biên dịch. | Cung cấp phương thức `clone` public hoặc API sao chép khác. |
| Quên `Cloneable` nhưng gọi `Object.clone()`. | `CloneNotSupportedException`. | Tuân thủ cơ chế Cloneable hoặc bỏ clone, dùng factory/copy constructor. |
| Nghĩ bản clone được khởi tạo qua constructor. | Có thể bỏ qua logic thiết lập bất biến trong constructor. | Rà soát bất biến, cân nhắc khởi tạo bằng constructor tường minh. |
| Dùng `new ArrayList<>(oldList)` rồi tin rằng phần tử mutable đã được clone. | Danh sách mới nhưng các phần tử vẫn dùng chung. | Sao chép từng phần tử khi cần. |
| Clone `int[][]` một lần để tách mọi hàng. | Mảng ngoài mới nhưng các hàng `int[]` vẫn chia sẻ. | Clone mỗi hàng ngoài việc clone mảng ngoài. |
| Cố gán trường `final` của bản clone sau `super.clone()`. | Lỗi biên dịch; không thể tái gán final trong clone thông thường. | Dùng constructor/factory tạo đối tượng mới. |
| Clone object có socket/stream/lock mà không định nghĩa ownership. | Hai bản có thể chia sẻ tài nguyên ngoài ý muốn. | Thiết kế vòng đời tài nguyên; có thể cấm clone. |
| Giả định `clone.equals(original)` luôn đúng. | Không đúng khi `equals` so theo danh tính hoặc lớp có quy tắc riêng. | Xác minh hợp đồng `equals` của kiểu dữ liệu cụ thể. |

Checklist trước khi triển khai clone:

1. Instance cần clone có implements `Cloneable` theo đúng cơ chế `Object.clone` không?
2. API clone có phạm vi truy cập và kiểu trả về phù hợp cho caller không?
3. Đối tượng mới có đúng runtime type và các giá trị trường thiết yếu không?
4. Có những trường tham chiếu mutable, mảng đa chiều, collection hoặc object con nào đang được chia sẻ?
5. Trường `final` hoặc bất biến constructor nào khiến việc sửa bản clone sau đó không phù hợp?
6. Việc sao chép có bảo toàn liên kết nội bộ, alias và con trỏ ngược nếu mô hình cần không?
7. Có tài nguyên không nên copy như stream, socket, lock, native handle hay state bên ngoài không?
8. Nếu bản sao được dùng trong collection dựa trên hash, các trường tham gia `equals/hashCode` có ổn định và đúng hợp đồng không?
9. Thao tác sao chép có thể chạy đồng thời với việc sửa đối tượng gốc không? Nếu có, đã thiết kế snapshot nhất quán chưa?
10. Một copy constructor hoặc factory có truyền đạt ý nghĩa sao chép rõ ràng và dễ duy trì hơn không?

### Bài tập tự kiểm tra

1. Sau `B b = (B) a.clone()`, vì sao `a != b` nhưng `a.list == b.list` vẫn có thể là `true`?
2. Nếu clone chứa `int age` và `List<String> tags`, việc sửa `age` và thêm phần tử vào `tags` có gì khác nhau?
3. Tại sao `Cloneable` không có phương thức `clone` để gọi trực tiếp bằng biến kiểu `Cloneable`?
4. Vì sao `new ArrayList<>(tags)` chưa phải deep copy nếu `tags` chứa các đối tượng mutable?
5. Nếu clone một `int[][]` chỉ bằng `source.clone()`, những gì đã độc lập và những gì vẫn dùng chung?
6. Vì sao `final List<String>` khó xử lý khi muốn tách list bằng cách gán lại sau `super.clone()`?
7. Vì sao cloning một object có socket hoặc input stream cần chính sách ownership đặc biệt?
8. Một lớp có thể không hỗ trợ clone nhưng vẫn cung cấp phương thức `copy()` hợp lệ không? Hãy nêu ví dụ cách làm.

**Ghi nhớ:** Khi đi tới `Object.clone()`, `super.clone()` tạo **instance mới** và **sao chép nông các trường**: dữ liệu nguyên thủy được chép, còn tham chiếu vẫn trỏ tới cùng object con. Muốn bản sao có trạng thái mutable độc lập, phải tách các thành phần cần thiết hoặc tạo bản mới bằng copy constructor/factory với hợp đồng rõ ràng.