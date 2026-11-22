# Phân biệt hai đối tượng bằng toán tử `==` và `!=` trong Java

Khi làm việc với class và object, câu hỏi “hai biến có bằng nhau không?” có **hai ý nghĩa rất khác nhau**: chúng có cùng trỏ tới **một đối tượng** hay hai đối tượng chứa **dữ liệu giống nhau**? Trong Java, toán tử `==` và `!=` áp dụng cho **tham chiếu (reference)** để kiểm tra ý nghĩa thứ nhất: **đồng nhất đối tượng (reference identity)**. Muốn so sánh nội dung hoặc giá trị nghiệp vụ, thường phải dùng `equals()` hoặc một phép so sánh được thiết kế phù hợp với kiểu dữ liệu.

Bài này thuộc Java Core — *class-object*, nhóm **Tham chiếu**. Các ví dụ chạy trên **Java 17 trở lên**, phân biệt rõ lỗi logic, lỗi biên dịch, trường hợp `null`, `String`, mảng, wrapper và lớp tự định nghĩa `equals()`.

## 1. Tham chiếu và đối tượng không phải cùng một thứ

Xét đoạn mã:

~~~java
Account first = new Account("A-01");
Account second = first;
~~~

Đây là **đoạn minh họa**; giả định lớp `Account` có constructor nhận `String`. Trong đó:

- `new Account("A-01")` tạo một **đối tượng** kiểu `Account`.
- `first` là **biến tham chiếu** đang giữ tham chiếu tới đối tượng đó.
- `second = first` **sao chép giá trị tham chiếu** từ biến `first` sang biến `second`.
- **Không có `new` thứ hai**, nên hai biến cùng trỏ tới **một đối tượng**.

Sơ đồ:

~~~text
first  -----+
            +----> đối tượng Account #1
second -----+        number = "A-01"
~~~

Một biến tham chiếu cũng có thể giữ `null`, tức **không trỏ tới đối tượng nào**. Ngược lại, hai biến có thể trỏ tới hai đối tượng **khác nhau** nhưng các trường của chúng lại có giá trị giống nhau.

**Điểm cần ghi nhớ:** đếm **số biến** không đồng nghĩa đếm **số object**. Muốn hiểu `==`, phải xác định tham chiếu đang chỉ tới **object nào**, thay vì chỉ nhìn dữ liệu bên trong object.

## 2. `==` và `!=` so sánh tham chiếu như thế nào?

Với hai toán hạng **kiểu tham chiếu** tương thích để so sánh, Java sử dụng:

| Biểu thức | Kết quả `true` khi nào? | Ý nghĩa |
| --- | --- | --- |
| `a == b` | `a` và `b` trỏ đến **cùng object**, hoặc **cả hai đều null** | Đồng nhất tham chiếu |
| `a != b` | `a` và `b` không mang cùng giá trị tham chiếu | Phủ định của `==` |
| `a == null` | `a` không trỏ tới object nào | Kiểm tra tham chiếu null |
| `a != null` | `a` đang trỏ tới một object | Kiểm tra khác null |

Hai biểu thức `a == b` và `a != b` **không thực thi** phương thức `equals()`. Chúng cũng **không tự duyệt các field** của đối tượng. Đây là toán tử có sẵn của ngôn ngữ, không phải phương thức có thể override trên class.

Với cùng cặp tham chiếu hợp lệ, `a != b` có giá trị logic ngược với `a == b`. Ví dụ nếu `a == b` là `true`, thì `a != b` là `false`.

### Khi nào hai tham chiếu được xem là cùng object?

Một cách nghĩ thực dụng:

~~~text
Nếu a --------> Object #1
   b --------> Object #1
=> a == b là true

Nếu a --------> Object #1
   b --------> Object #2
=> a == b là false
   kể cả khi Object #1 và Object #2 có cùng dữ liệu
~~~

Phép so sánh tham chiếu không phụ thuộc hai object cùng thuộc một class hay cùng giá trị trường. Nó chỉ xét **đồng nhất của đối tượng được tham chiếu**.

## 3. Chương trình chạy được: cùng object và hai object khác nhau

Tạo tệp **`ReferenceIdentityDemo.java`**:

~~~java
class Box {
    private final String label;
    private int count;

    Box(String label, int count) {
        if (label == null || label.isBlank() || count < 0) {
            throw new IllegalArgumentException("Box không hợp lệ");
        }
        this.label = label;
        this.count = count;
    }

    int count() {
        return count;
    }

    void add(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số cộng phải dương");
        }
        count = Math.addExact(count, amount);
    }

    String label() {
        return label;
    }
}

public class ReferenceIdentityDemo {
    public static void main(String[] args) {
        Box first = new Box("X", 10);
        Box alias = first;
        Box second = new Box("X", 10);

        System.out.println("first == alias: " + (first == alias));
        System.out.println("first != alias: " + (first != alias));
        System.out.println("first == second: " + (first == second));
        System.out.println("first != second: " + (first != second));
        System.out.println("same count: " + (first.count() == second.count()));
        System.out.println("equals second: " + first.equals(second));

        alias.add(3);
        System.out.println("first count: " + first.count());
        System.out.println("second count: " + second.count());

        Box maybe = null;
        System.out.println("maybe == null: " + (maybe == null));
        System.out.println("first != null: " + (first != null));

        maybe = first;
        System.out.println("maybe == alias: " + (maybe == alias));
    }
}
~~~

Tại thư mục chứa tệp, chạy:

~~~bash
javac -encoding UTF-8 ReferenceIdentityDemo.java
java ReferenceIdentityDemo
~~~

**Stdout:**

~~~text
first == alias: true
first != alias: false
first == second: false
first != second: true
same count: true
equals second: false
first count: 13
second count: 10
maybe == null: true
first != null: true
maybe == alias: true
~~~

### Phân tích từng nhóm kết quả

1. `Box first = new Box("X", 10)` tạo đối tượng #1.
2. `Box alias = first` chỉ sao chép tham chiếu nên `first == alias` là `true`, `first != alias` là `false`.
3. `Box second = new Box("X", 10)` tạo đối tượng #2, vì thế `first == second` là `false`, **dù nhãn và số lượng ban đầu giống nhau**.
4. `first.count() == second.count()` so sánh hai giá trị **`int`**, đều bằng 10, nên là `true`. Đây là **so sánh primitive value**, khác với `first == second`.
5. `Box` chưa override `equals()`, nên `first.equals(second)` dùng phiên bản kế thừa từ `Object`, cũng trả `false` cho hai object riêng biệt.
6. `alias.add(3)` làm thay đổi **chính đối tượng #1** mà `first` cũng trỏ tới. Vì thế `first.count()` thành 13, trong khi `second.count()` vẫn bằng 10.
7. `maybe == null` là `true` trước khi gán `maybe = first`; sau phép gán, `maybe == alias` thành `true` vì chúng trỏ cùng object.

Ví dụ cho thấy một lần gán **tham chiếu** không tạo ra đối tượng mới. Ngược lại, một lệnh `new` thông thường tạo đối tượng riêng, nên không thể suy ra đồng nhất chỉ vì cùng class và dữ liệu.

## 4. Gán lại biến không thay đổi object cũ

Xét một đoạn độc lập về mặt ý tưởng, giả định có constructor `Box(String,int)` như ở mục trước:

~~~java
Box a = new Box("A", 1);
Box b = a;

b = new Box("B", 2);
~~~

Trước phép gán cuối:

~~~text
a ----+
      +----> Box #1 ("A", 1)
b ----+
~~~

Sau phép gán cuối:

~~~text
a --------> Box #1 ("A", 1)
b --------> Box #2 ("B", 2)
~~~

`b = new Box(...)` khiến **biến `b` trỏ tới object mới**; không biến `Box #1` thành `Box #2` và không tự thay đổi giá trị tham chiếu trong `a`.

Nếu sau đó viết `a = null;`, biến `a` thôi giữ tham chiếu tới `Box #1`; object ấy có thể trở thành ứng viên thu hồi nếu không còn đường tham chiếu nào khác. **Gán `null` không đồng nghĩa object bị xóa ngay**.

Trường hợp truyền một tham chiếu vào phương thức cũng tương tự: Java **truyền đối số theo giá trị**. Phương thức nhận bản sao giá trị tham chiếu; nó có thể sửa object đang được chia sẻ nếu được phép, nhưng phép gán lại biến tham số không làm biến của caller tự chuyển sang object khác.

## 5. So sánh với `null` an toàn và phổ biến

`null` là giá trị tham chiếu đặc biệt, không phải một instance của class. So sánh với null là trường hợp nên sử dụng `==` và `!=`:

~~~java
String name = null;

System.out.println(name == null); // true
System.out.println(name != null); // false
~~~

Đây là đoạn minh họa trong phương thức. Hai phép so sánh **không gọi phương thức trên `name`**, nên không ném `NullPointerException` chỉ vì `name` bằng `null`.

Ngược lại:

~~~java
String name = null;
System.out.println(name.equals("An")); // NullPointerException.
~~~

Đoạn trên **biên dịch được nhưng lỗi khi chạy**, vì gọi instance method `equals` thông qua tham chiếu `null`.

Phân biệt các tình huống:

| Biểu thức | Kết quả khi `name == null` |
| --- | --- |
| `name == null` | `true` |
| `name != null` | `false` |
| `name == "An"` | `false` |
| `name.equals("An")` | Ném `NullPointerException` |
| `"An".equals(name)` | `false` |
| `java.util.Objects.equals(name, "An")` | `false` |

Kiểm tra `if (obj != null)` trước khi gọi phương thức trên `obj` là một kỹ thuật phổ biến. Với so sánh nội dung có thể null, `Objects.equals(a,b)` tiện lợi vì xử lý được cả trường hợp hai tham chiếu đều null.

## 6. `==` khác `equals()` ở đâu?

Trong Java:

- `a == b` với hai **tham chiếu** hỏi: “Đây có phải **cùng một object** không?”
- `a.equals(b)` là **lời gọi một phương thức**; ý nghĩa của “bằng nhau” phụ thuộc vào **triển khai `equals()`** của lớp mà `a` tham chiếu.
- Nếu lớp không override `equals()`, triển khai mặc định của `java.lang.Object` dựa trên **reference identity**.
- Nhiều lớp thư viện như `String`, các wrapper và nhiều collection định nghĩa `equals()` để so sánh **giá trị/nội dung** theo hợp đồng riêng.
- `java.util.Objects.equals(a,b)` xử lý null an toàn: nếu cả hai null thì `true`; nếu một null thì `false`; nếu cả hai khác null thì gọi `a.equals(b)`.

Bảng so sánh:

| Câu hỏi thực tế | Thường dùng | Lý do |
| --- | --- | --- |
| Có đúng **cùng instance** không? | `a == b` | So sánh đồng nhất tham chiếu |
| Có phải **hai instance khác nhau** không? | `a != b` | Phủ định reference equality |
| Một tham chiếu có null không? | `a == null` | Kiểm tra giá trị null |
| Hai chuỗi có cùng nội dung không? | `a.equals(b)` hoặc `Objects.equals(a,b)` | `String.equals` có ngữ nghĩa so sánh ký tự |
| Hai object nghiệp vụ có giá trị tương đương không? | `a.equals(b)` nếu lớp định nghĩa đúng | Đo hợp đồng equality của domain |
| Hai mảng có cùng phần tử không? | `Arrays.equals` / `Arrays.deepEquals` thích hợp | `==` chỉ so cùng object mảng |
| Hai giá trị `int` có bằng nhau không? | `x == y` | Toán tử so sánh **giá trị nguyên thủy** |

**Không đúng** khi nói `equals()` “luôn so sánh tất cả field”. Tác giả lớp quyết định những thành phần nào tham gia so sánh, và phải tuân thủ hợp đồng của `equals`. Với class chưa override, `equals` có thể cho kết quả giống `==`; với class override, kết quả có thể khác.

## 7. `String`: vì sao `==` đôi khi in `true` dù khác biến?

`String` là tình huống kinh điển dễ gây hiểu nhầm. Java có **string pool** và cơ chế intern cho string literal / constant expression. Vì vậy hai biến nhận cùng một literal có thể trỏ đến cùng một instance, nhưng điều đó không làm `==` trở thành phép so sánh nội dung.

Ví dụ:

~~~java
String a = "java";
String b = "java";
String c = new String("java");

System.out.println(a == b);      // true: cùng literal được intern
System.out.println(a == c);      // false: c tham chiếu tới object mới
System.out.println(a.equals(c)); // true: cùng nội dung
~~~

Đây là đoạn minh họa trong phương thức. `new String("java")` tạo một object `String` riêng theo ngữ nghĩa `new`, trong khi literal `"java"` sử dụng biểu diễn đã được intern.

**Sai lầm cần tránh:** quan sát `"a" == "a"` là `true` rồi kết luận `==` so sánh chuỗi theo ký tự. Kết quả ấy là hệ quả **đồng nhất tham chiếu của các literal được intern**, không phải ngữ nghĩa tổng quát của toán tử.

### Chương trình String và mảng có output xác định

Tạo tệp **`ContentEqualityDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

record Pixel(int x, int y) {
}

public class ContentEqualityDemo {
    public static void main(String[] args) {
        String literal = "java";
        String folded = "ja" + "va";
        String created = new String("java");

        System.out.println("literal == folded: " + (literal == folded));
        System.out.println("literal == created: " + (literal == created));
        System.out.println("literal.equals(created): "
                + literal.equals(created));
        System.out.println("literal == created.intern(): "
                + (literal == created.intern()));

        int[] first = {1, 2};
        int[] second = {1, 2};
        int[] alias = first;

        System.out.println("arrays same reference: " + (first == alias));
        System.out.println("arrays different reference: " + (first == second));
        System.out.println("Arrays.equals: " + Arrays.equals(first, second));
        System.out.println("Objects.equals(arrays): "
                + Objects.equals(first, second));

        int[][] left = {{1, 2}, {3}};
        int[][] right = {{1, 2}, {3}};
        System.out.println("Arrays.deepEquals: "
                + Arrays.deepEquals(left, right));

        Pixel p1 = new Pixel(2, 3);
        Pixel p2 = new Pixel(2, 3);
        System.out.println("record reference: " + (p1 == p2));
        System.out.println("record equals: " + p1.equals(p2));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ContentEqualityDemo.java
java ContentEqualityDemo
~~~

**Stdout chính xác:**

~~~text
literal == folded: true
literal == created: false
literal.equals(created): true
literal == created.intern(): true
arrays same reference: true
arrays different reference: false
Arrays.equals: true
Objects.equals(arrays): false
Arrays.deepEquals: true
record reference: false
record equals: true
~~~

Giải thích:

1. `folded = "ja" + "va"` là **biểu thức hằng** được nối tại compile time và intern, nên có cùng tham chiếu với literal `"java"`.
2. `created = new String("java")` tạo instance khác, vì vậy `literal == created` là `false`, còn `literal.equals(created)` là `true`.
3. `String.intern()` trả tham chiếu đến biểu diễn intern của nội dung, nên `literal == created.intern()` là `true`.
4. `first == alias` là `true` vì hai biến trỏ cùng mảng; `first == second` là `false` vì tạo hai mảng riêng.
5. `Arrays.equals(first, second)` duyệt các phần tử `int`, so sánh theo giá trị và trả `true`.
6. `Objects.equals(first, second)` **không so sánh nội dung mảng**: nó gọi `first.equals(second)` khi cả hai khác null, mà mảng không override `Object.equals`; kết quả `false`.
7. `Arrays.deepEquals(left,right)` so sánh lồng nhau các mảng và phần tử phù hợp; trong ví dụ hai ma trận có cùng dữ liệu nên là `true`.
8. Hai record `Pixel` được tạo từ hai lệnh `new` khác nhau, nên `p1 == p2` là `false`. Record tự sinh `equals` theo các thành phần của record; ở đây cả `x` và `y` bằng nhau nên `p1.equals(p2)` là `true`.

**Lưu ý:** không sử dụng `new String(...)` trong mã ứng dụng chỉ để so sánh; đây là thủ thuật minh họa sự khác nhau giữa identity và content equality. Với chuỗi người dùng nhập, ghép chuỗi khi chạy hoặc chuỗi đọc từ tệp/API, hãy dùng `equals` để xét nội dung, không dựa vào intern.

## 8. Mảng: `==` so object mảng, không duyệt phần tử

Mảng là **object** trong Java. Hai mảng có cùng số phần tử và cùng giá trị **vẫn có thể khác tham chiếu**:

~~~java
int[] a = {1, 2};
int[] b = {1, 2};

System.out.println(a == b);                 // false
System.out.println(java.util.Arrays.equals(a, b)); // true
~~~

Đây là đoạn minh họa. `a` và `b` được tạo bằng hai lần tạo mảng, nên `a == b` là `false`. `Arrays.equals(int[],int[])` mới thực hiện so sánh **theo từng phần tử**.

Phân biệt các cách:

| Tình huống | Cách so sánh thường dùng |
| --- | --- |
| Hai biến có trỏ cùng mảng không? | `a == b` |
| Hai mảng `int[]` cùng phần tử không? | `Arrays.equals(a,b)` |
| Hai mảng `String[]` cùng phần tử theo `String.equals`? | `Arrays.equals(a,b)` |
| Hai cấu trúc mảng lồng nhau có dữ liệu tương ứng? | `Arrays.deepEquals(a,b)` khi dạng API phù hợp |
| Một mảng có null không? | `a == null` |

Không dùng `a.equals(b)` hay `Objects.equals(a,b)` để kỳ vọng so sánh sâu các phần tử mảng. Nếu bạn có mảng của **đối tượng mutable**, `Arrays.equals(Object[],Object[])` sử dụng `equals` của từng phần tử (với xử lý null), chứ không tự so sánh mọi field theo kiểu phản chiếu.

Với mảng nhiều chiều, `Arrays.deepEquals` hữu ích nhưng cần xem xét **mảng răng cưa**, phần tử null và mảng chứa tham chiếu tới object có `equals` đặc biệt. Cách dùng phù hợp phụ thuộc kiểu và ngữ nghĩa dữ liệu.

## 9. Lớp tự định nghĩa: vì sao `equals()` mặc định giống identity?

Mọi class Java thông thường kế thừa `equals(Object)` từ `java.lang.Object`, trừ khi override. Phiên bản mặc định của `Object.equals` chỉ coi hai tham chiếu bằng nhau khi chúng biểu thị **cùng object**.

Ví dụ `Box` ở chương trình đầu không override `equals`. Vì vậy:

~~~java
Box a = new Box("X", 10);
Box b = new Box("X", 10);

System.out.println(a == b);      // false
System.out.println(a.equals(b));  // false
~~~

Hai object có **cùng trạng thái**, nhưng class chưa định nghĩa “hai Box có cùng nội dung là bằng nhau”.

Có hai lựa chọn thiết kế khác nhau:

1. **Object có danh tính riêng**, ví dụ kết nối mạng, cửa sổ giao diện, một phiên làm việc đang chạy: đôi khi chỉ cần identity là hợp lý.
2. **Value object**, ví dụ mã định danh, tọa độ hay khoảng giá trị: thường muốn các instance khác nhau với cùng giá trị thành phần được xem là bằng nhau.

**Không nên tự động override `equals` trong mọi class.** Hãy xác định **nghĩa của equality theo miền nghiệp vụ** trước khi cài đặt. Với entity có ID, so sánh hai object cùng ID có thể là ý nghĩa nghiệp vụ, nhưng vẫn phải xét vòng đời ID, persistence, proxy, thay đổi trạng thái và hợp đồng `equals/hashCode`.

## 10. Cài đặt `equals()` và `hashCode()` cho value object

Khi một class muốn định nghĩa **bằng nhau theo dữ liệu**, override `equals(Object)` và `hashCode()` nhất quán. Ví dụ một khóa người dùng được xác định bởi cặp `(system, number)`.

Tạo tệp độc lập **`EqualsContractDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class MemberId {
    private final String system;
    private final long number;

    MemberId(String system, long number) {
        if (system == null || system.isBlank() || number < 0) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }
        this.system = system;
        this.number = number;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof MemberId other)) {
            return false;
        }
        return number == other.number && system.equals(other.system);
    }

    @Override
    public int hashCode() {
        return Objects.hash(system, number);
    }
}

public class EqualsContractDemo {
    public static void main(String[] args) {
        MemberId first = new MemberId("app", 42);
        MemberId second = new MemberId("app", 42);
        MemberId third = new MemberId("app", 43);

        System.out.println("first == second: " + (first == second));
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("first.equals(third): " + first.equals(third));
        System.out.println("hashes match: "
                + (first.hashCode() == second.hashCode()));

        Set<MemberId> ids = new HashSet<>();
        ids.add(first);
        System.out.println("contains second: " + ids.contains(second));
        System.out.println("contains third: " + ids.contains(third));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EqualsContractDemo.java
java EqualsContractDemo
~~~

**Stdout:**

~~~text
first == second: false
first.equals(second): true
first.equals(third): false
hashes match: true
contains second: true
contains third: false
~~~

### Vì sao code này đúng về mặt hợp đồng cơ bản?

- `if (this == obj) return true;`: tối ưu khi hai tham chiếu cùng một object. Việc dùng `==` **bên trong `equals()` hoàn toàn hợp lý** để nhận diện cùng instance.
- `instanceof MemberId other` (pattern matching Java 17) loại trường hợp null hoặc khác kiểu; đồng thời khai báo biến `other`.
- `number == other.number` so hai giá trị **`long` nguyên thủy**.
- `system.equals(other.system)` so hai nội dung `String`, không so danh tính chuỗi.
- `hashCode()` dựa trên đúng hai thành phần dùng trong `equals`, nên nếu hai `MemberId` bằng nhau thì hash code của chúng bằng nhau.
- `HashSet.contains(second)` hoạt động dựa trên hợp đồng `equals/hashCode`, do đó tìm thấy object bằng giá trị dù tham chiếu khác object đã thêm.

Hai object **không bằng nhau** vẫn **có thể** có cùng hash code: collision là điều hợp lệ. Vì thế **không dùng `a.hashCode() == b.hashCode()` làm phép kiểm tra equality**.

Dùng các field bất biến như `final String system` và `final long number` giúp tránh vấn đề đối tượng bị thay đổi những thành phần tham gia `hashCode` sau khi đã đưa vào `HashSet` hoặc làm khóa `HashMap`.

## 11. Hợp đồng `equals()` không chỉ là “so tất cả trường”

Theo `Object.equals`, một implementation tốt cần những tính chất cơ bản:

1. **Reflexive:** `x.equals(x)` là `true` với tham chiếu `x` khác null.
2. **Symmetric:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
3. **Transitive:** nếu `x.equals(y)` và `y.equals(z)`, thì `x.equals(z)`.
4. **Consistent:** khi không thay đổi dữ liệu dùng cho equality, các lời gọi lặp lại cho kết quả nhất quán.
5. **Non-null:** `x.equals(null)` là `false` với `x` khác null.

Đi kèm là hợp đồng `hashCode`: **hai object được `equals` coi là bằng nhau phải có cùng hash code**. Chiều ngược lại không bắt buộc.

Thực tế có những class có trạng thái nhưng vẫn dùng identity equality, và có những class chỉ dùng một số trường ổn định để xác định equality. Vì thế đừng áp dụng máy móc “so tất cả field” mà không xác định vai trò các trường.

### Hợp đồng equality và `record`

Một `record` trong Java tự tạo `equals`/`hashCode` theo các component của nó. Với `record Pixel(int x, int y)` ở ví dụ trước, `new Pixel(2,3).equals(new Pixel(2,3))` là `true` dù hai object khác nhau.

**Không nên suy ra record tự so sánh sâu mọi dữ liệu con.** Nếu component là **mảng**, phép equality được tạo cho component mảng về bản chất dựa trên phép bằng nhau phù hợp với kiểu tham chiếu của mảng, không tự gọi `Arrays.deepEquals` cho mọi cấp. Với dữ liệu lồng nhau mutable, cần cân nhắc định nghĩa kiểu giá trị và ownership thích hợp.

## 12. Với primitive, `==` so giá trị chứ không so object

Toán tử `==` không chỉ tồn tại cho tham chiếu. Khi hai toán hạng là **giá trị nguyên thủy** thích hợp, Java so sánh giá trị theo quy tắc kiểu tương ứng:

~~~java
int a = 5;
long b = 5L;
System.out.println(a == b); // true: so giá trị số sau chuyển đổi phù hợp

boolean ready = true;
System.out.println(ready == true); // true
~~~

Đây là đoạn minh họa. `a` và `b` không phải tham chiếu tới hai object; nói “cùng object” ở đây là sai.

Một số chi tiết khi so số thực:

- `Double.NaN == Double.NaN` là `false`, vì phép so sánh giá trị dấu phẩy động với NaN không bằng ngay cả chính nó.
- `0.0 == -0.0` là `true` theo phép so sánh số thực nguyên thủy.
- So sánh số thực bằng `==` có thể không phù hợp để kiểm tra kết quả phép tính gần đúng; khi cần, xác định quy tắc sai số theo yêu cầu.

Những ví dụ số thực trên nói về **primitive equality**, không phải tham chiếu `Double`. Hai wrapper `Double` là các object; `==` khi so trực tiếp hai biến kiểu `Double` vẫn là tham chiếu identity.

## 13. Wrapper và autoboxing: cùng giá trị chưa chắc cùng tham chiếu

Các wrapper như `Integer`, `Long`, `Boolean` là **kiểu tham chiếu**. Với hai biến có kiểu `Integer`, `==` kiểm tra **identity**, không tự thực hiện `Integer.equals`.

~~~java
Integer a = Integer.valueOf(7);
Integer b = Integer.valueOf(7);

System.out.println(a.equals(b)); // true: cùng giá trị Integer
~~~

Java cho phép implementation cache một số object wrapper; với `Integer.valueOf`, dải -128 đến 127 được cache theo hợp đồng API. Vì thế một số phép so sánh `a == b` có thể ra `true` cho các giá trị được cache. **Không suy ra rằng `==` là đúng để so nội dung mọi wrapper.**

Ở các giá trị khác dải bắt buộc, việc dùng lại object có thể phụ thuộc implementation hoặc đường tạo object. Ví dụ `Integer x = 1000; Integer y = 1000;` không nên được dùng để khẳng định một stdout cố định về `x == y` cho mọi runtime. Dùng `x.equals(y)` để so giá trị `Integer`.

### Primitive và wrapper đứng chung trong phép `==`

Nếu một toán hạng là số nguyên thủy và toán hạng còn lại là wrapper số tương ứng, Java có thể **unbox** wrapper để so sánh số:

~~~java
Integer boxed = Integer.valueOf(5);
int primitive = 5;
System.out.println(boxed == primitive); // true: so hai giá trị số
~~~

Khác với `Integer boxedA == Integer boxedB`, biểu thức trên dùng chuyển đổi theo quy tắc số nguyên thủy. **Cẩn trọng với null**:

~~~java
Integer missing = null;
int expected = 0;
// System.out.println(missing == expected); // Chạy sẽ ném NullPointerException.
~~~

Khi cần unbox `missing`, Java không có giá trị nguyên thủy để lấy từ `null`. Nhưng biểu thức `missing == null` an toàn vì đó là phép so sánh tham chiếu.

**Kết luận:** muốn giải thích đúng `==` phải biết **kiểu tĩnh của hai toán hạng tại vị trí so sánh**, không chỉ nhìn cách chúng được in ra màn hình.

## 14. Không phải hai kiểu tham chiếu bất kỳ đều dùng `==` được

Compiler Java áp dụng **quy tắc tương thích kiểu** khi so sánh hai tham chiếu. Ví dụ minh họa lỗi biên dịch:

~~~java
String text = "7";
Integer number = 7;

// boolean same = (text == number); // LỖI: incomparable types.
~~~

`String` và `Integer` là các kiểu không thể tương thích trực tiếp với nhau cho phép so sánh tham chiếu này. Mặc dù ở runtime hai object tất nhiên không là cùng object, Java **không nhất thiết cho phép viết mọi phép `==` giữa hai kiểu tham chiếu không liên quan**.

Một trường hợp hợp lệ hơn:

~~~java
Object text = "7";
Object number = Integer.valueOf(7);
System.out.println(text == number); // false
~~~

Vì hai biểu thức đều có kiểu `Object`, so sánh tham chiếu là hợp lệ và trả `false`: chúng trỏ tới hai object khác nhau.

Dùng phép ép kiểu chỉ để ép hai biểu thức qua compiler thường **không phải thiết kế tốt**. Nếu mục đích là xét dữ liệu tương đương giữa các loại khác nhau, hãy chuyển chúng về **kiểu giá trị chung có ý nghĩa** theo nghiệp vụ, không đánh tráo reference identity.

## 15. `Objects.equals` an toàn với null nhưng không so sánh sâu

`java.util.Objects.equals(a,b)` rất tiện khi hai tham chiếu **có thể null**:

~~~java
String left = null;
String right = null;

System.out.println(java.util.Objects.equals(left, right)); // true

right = "An";
System.out.println(java.util.Objects.equals(left, right)); // false
~~~

Phương thức này về mặt kết quả tương đương ý tưởng:

~~~java
return a == b || (a != null && a.equals(b));
~~~

Đây là **một biểu thức minh họa thân phương thức**, không phải chương trình độc lập. Việc gọi `a.equals(b)` vẫn phụ thuộc implementation của class bên trái.

Vì thế:

- `Objects.equals("A", new String("A"))` là `true` theo nội dung String.
- `Objects.equals(null, null)` là `true`.
- `Objects.equals(array1, array2)` với hai mảng riêng thường **`false`**, dù phần tử giống nhau.
- Nếu class không override `equals`, `Objects.equals` **không tự so mọi trường** của object.

Khi xử lý mảng, hãy chọn `Arrays.equals` hoặc `Arrays.deepEquals`. Khi xử lý đối tượng nghiệp vụ, hãy dựa trên **hợp đồng `equals` của class**, không kỳ vọng `Objects.equals` giải quyết mọi khác biệt semantics.

## 16. Reference identity không nói gì về quan hệ nghiệp vụ

Hai tham chiếu có thể khác nhau nhưng biểu diễn **cùng một thực thể nghiệp vụ**, chẳng hạn hai bản snapshot của một bản ghi database cùng ID. Ngược lại, hai tham chiếu có thể cùng trỏ một object nhưng object đó **đã thay đổi trạng thái** theo thời gian.

Ví dụ tư duy:

~~~text
Trong lần đọc thứ nhất:
  snapshotA  ---> User{id=42, displayName="An"}

Trong lần đọc thứ hai:
  snapshotB  ---> User{id=42, displayName="Anh"}

snapshotA == snapshotB có thể false vì là hai object khác nhau,
dù cả hai cùng nói về user có id=42.
~~~

Đây là **sơ đồ nghiệp vụ**, không xác định cách ORM/cache nào cụ thể vận hành. Để kết luận hai object biểu diễn cùng user, phải định nghĩa tiêu chí nghiệp vụ — ví dụ ID hợp lệ trong một hệ thống nhất định — chứ không dùng `==` như một thay thế.

**Quan trọng:** nhiều ORM có quy tắc identity map, proxy, entity equality, và vòng đời ID phức tạp. Không có quy tắc chung rằng mọi entity nên so `equals` chỉ bằng ID ở mọi thời điểm; cần cân nhắc trường hợp chưa được cấp ID, lazy loading và session. Trong Java Core, hãy tách ba khái niệm:

1. **Reference identity:** đúng cùng object trong bộ nhớ logic JVM.
2. **Value equality:** dữ liệu được class định nghĩa là bằng nhau.
3. **Business identity:** cùng thực thể nghiệp vụ theo quy tắc hệ thống.

Ba câu hỏi có thể cho ba câu trả lời khác nhau.

## 17. `==`, `equals()` và tính an toàn khi dữ liệu thay đổi

So sánh identity **không tạo bản sao** và **không làm object bất biến**. Nếu:

~~~java
Box first = new Box("X", 10);
Box alias = first;

alias.add(1);
~~~

thì `first == alias` vẫn là `true` trước và sau lần gọi; object nhận thao tác đã thay đổi trạng thái, nhưng tham chiếu vẫn chỉ cùng object.

Đối với `equals()` dựa trên nội dung, giá trị so sánh có thể **thay đổi theo thời gian** nếu những field tham gia equality là mutable. Điều đó đặc biệt quan trọng khi object được dùng làm khóa `HashMap` hoặc phần tử `HashSet`. Nếu hash code phụ thuộc giá trị mutable và giá trị đổi trong lúc object đang nằm trong cấu trúc hash, hành vi tìm kiếm có thể sai mong đợi.

Các value object đơn giản thường nên có trường ổn định, được gán qua constructor, ví dụ `MemberId` ở mục trước. Nếu một API chủ ý dùng identity equality, hãy nói rõ, nhất là khi người dùng dễ nhầm với equality theo nội dung.

## 18. Khi nào nên dùng `==` và khi nào không?

Một bảng quyết định thực dụng:

| Bạn muốn biết... | Cách diễn đạt Java thường phù hợp |
| --- | --- |
| Hai biến có chỉ đúng **cùng object**? | `a == b` |
| Hai biến có chỉ **hai object khác nhau**? | `a != b` |
| Một tham chiếu có rỗng (null)? | `a == null` hoặc `a != null` |
| Hai giá trị nguyên thủy bằng nhau? | `x == y` theo quy tắc primitive |
| Hai `String` có cùng ký tự? | `a.equals(b)`, hoặc `Objects.equals(a,b)` khi có null |
| Hai `Integer` có cùng số? | `a.equals(b)` hoặc `Objects.equals(a,b)` |
| Hai mảng có cùng phần tử? | `Arrays.equals(a,b)` |
| Hai mảng lồng nhau có cấu trúc bằng nhau? | `Arrays.deepEquals(a,b)` thích hợp |
| Hai domain value object tương đương? | Override `equals/hashCode` theo invariant |
| Hai entity đại diện cùng ID nghiệp vụ? | Quy tắc identity riêng của domain, không mặc định dùng `==` |

Thói quen tốt là **đặt câu hỏi đúng trước khi chọn toán tử**. Hãy xác định bạn đang cần so sánh **reference** hay **value**. Nếu mục tiêu là nội dung chuỗi, đừng dựa vào vài thử nghiệm `==` tình cờ cho `true` vì intern/caching.

## 19. Lỗi thường gặp và cách sửa

| Hiểu nhầm hoặc lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `new Person("An") == new Person("An")` phải true | Hai lần `new` tạo hai object | Dùng `equals` nếu class định nghĩa so theo nội dung |
| Hai biến là hai tên khác nhau nên `!=` true | `b = a` sao chép tham chiếu | Theo dõi alias và số lần tạo object |
| `String` so nội dung bằng `==` | `==` chỉ so tham chiếu | Dùng `String.equals` hoặc `Objects.equals` |
| `"abc" == "abc"` true chứng minh `==` so ký tự | Literal được intern | Không suy luận từ string pool |
| `array1 == array2` so các phần tử | Mảng là object, `==` so identity | Dùng `Arrays.equals` |
| `Objects.equals` tự so sâu các mảng | Nó gọi `equals` theo class | Dùng `Arrays.deepEquals` khi cần |
| `obj.equals(null)` luôn an toàn | Nếu `obj == null`, gọi phương thức sẽ lỗi | `Objects.equals` hoặc kiểm tra null trước |
| Mọi `equals` đều so tất cả field | Class quyết định ngữ nghĩa equality | Đọc/cài đặt hợp đồng đúng |
| `Integer` luôn có `==` false khi tạo hai biến | Wrapper có cơ chế cache | Dùng `equals` để so giá trị |
| `hashCode` bằng nhau nghĩa là object bằng nhau | Hash collision hợp lệ | Chỉ dựa trên `equals` theo hợp đồng |
| `==` chỉ so giá trị trên mọi kiểu | Với reference, nó so identity; với primitive, nó so value | Xem kiểu tĩnh của hai toán hạng |
| Bất kỳ hai reference đều dùng `==` được | Java có quy tắc tương thích kiểu | Dùng các toán hạng có kiểu phù hợp |
| `!=` và `!equals()` luôn đồng nghĩa | Một cái phủ định identity, cái kia phủ định equality theo class | Chọn đúng câu hỏi đang kiểm tra |

## 20. Bài tập tự kiểm tra

**Bài 1 — Alias.** Cho:

~~~java
Box x = new Box("A", 2);
Box y = x;
Box z = new Box("A", 2);
~~~

Hãy xác định `x == y`, `x != z`, `x.count() == z.count()` và giải thích từng kết quả.

**Bài 2 — Gán lại biến.** Tiếp tục bài 1 với `y = z;`. Lúc này `x == y` và `y == z` là gì? Có object nào bị xóa hoặc sửa chỉ vì phép gán không?

**Bài 3 — Null.** Với `String s = null;`, biểu thức nào an toàn: `s == null`, `s.equals("a")`, `Objects.equals(s,"a")`? Nêu kết quả hoặc ngoại lệ.

**Bài 4 — String.** Giải thích vì sao `String a = "hi"; String b = new String("hi");` thường cho `a == b` là `false` nhưng `a.equals(b)` là `true`.

**Bài 5 — Mảng.** Hai mảng `int[]` chứa `{1,2,3}` nhưng được tạo ở hai câu lệnh khác nhau. `==`, `Arrays.equals` và `Objects.equals` sẽ cho kết quả nào?

**Bài 6 — Wrapper.** Vì sao không nên dùng `Integer x = 1000, y = 1000; System.out.println(x == y);` làm phép kiểm tra hai số có bằng nhau không? Trường hợp so `Integer x` với primitive `int n` khác gì?

**Bài 7 — Equals contract.** Nếu hai object `MemberId` có cùng `system` và `number`, cần kết quả `equals` và quan hệ `hashCode` nào? Hash code bằng nhau có đủ khẳng định equality không?

**Bài 8 — Kiểu tĩnh.** Tại sao `String s = "a"; Integer i = 1; s == i` bị lỗi compile, nhưng `Object a = s; Object b = i; a == b` hợp lệ?

**Bài 9 — Record.** Với `record Point(int x,int y) {}`, `new Point(1,2) == new Point(1,2)` và `new Point(1,2).equals(new Point(1,2))` khác nhau thế nào?

**Bài 10 — Mục đích so sánh.** Bạn đang triển khai hệ thống quản lý tài khoản: hai object Java được tải ở hai thời điểm khác nhau, cùng mang mã tài khoản `"A-01"`. `==` có trả lời câu hỏi “cùng tài khoản nghiệp vụ” một cách đáng tin không? Cần định nghĩa gì thêm?

### Đáp án ngắn

1. `x == y` true; `x != z` true; so `count()` nguyên thủy trả true vì cả hai bằng 2.
2. `x == y` false và `y == z` true; phép gán đổi tham chiếu trong `y`, không tự sửa object.
3. `s == null` true; `s.equals("a")` ném `NullPointerException`; `Objects.equals(s,"a")` false.
4. `new String` tạo object mới, literal có biểu diễn intern; `equals` so nội dung.
5. `==` false, `Arrays.equals` true, `Objects.equals` false.
6. Hai `Integer` so identity khi dùng `==`; cache không phải quy tắc so giá trị. So với primitive có thể unbox, và nếu wrapper null có thể ném lỗi.
7. `equals` true; hash code phải bằng nhau. Hash trùng **không** chứng minh hai object bằng nhau.
8. Cặp kiểu `String` và `Integer` không tương thích trực tiếp cho phép so sánh tham chiếu ấy; hai biểu thức `Object` có thể so identity.
9. `==` false do hai object; `equals` true vì record so các component `int` tương ứng.
10. Không; cần quy tắc so theo **business identity**, ví dụ mã tài khoản thuộc đúng phạm vi duy nhất của hệ thống.

## 21. Tài liệu đối chiếu

- [Java Language Specification 17, §15.21 — Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21): `==`, `!=` đối với số, boolean và tham chiếu.
- [Java SE 17 API — Object.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): hợp đồng equals và quan hệ với hashCode.
- [Java SE 17 API — Objects.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)): so sánh null-safe dựa trên equals.
- [Java SE 17 API — Arrays.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): so nội dung mảng theo overload thích hợp.
- [Java SE 17 API — String.intern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#intern()): biểu diễn chuỗi intern.
- [Java Language Specification 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): các phương thức được suy ra cho record, gồm equals.

**Ghi nhớ:** với hai **tham chiếu**, `==` nghĩa là **cùng đối tượng**, `!=` nghĩa là **không cùng đối tượng**; không có chuyện toán tử này tự so các trường. So **nội dung** hãy dùng `equals()` hoặc API phù hợp như `Arrays.equals`; so **mã nghiệp vụ** cần tiêu chí domain cụ thể. Trường hợp kiểm tra `null` là một lý do rất đúng để dùng `==` và `!=`.
