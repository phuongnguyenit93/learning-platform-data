# Truyền tham số theo giá trị và thay đổi trạng thái đối tượng

Khi gọi một phương thức Java, các đối số được đánh giá rồi giá trị của chúng được truyền vào những tham số tương ứng. Java luôn **truyền tham số theo giá trị** (*pass-by-value*). Với kiểu nguyên thủy, giá trị được sao chép là số, ký tự hoặc giá trị boolean. Với kiểu tham chiếu, giá trị được sao chép là tham chiếu đến đối tượng.

Sự khác biệt này giải thích một tình huống dễ gây nhầm lẫn: phương thức có thể thay đổi trạng thái của một đối tượng mà mã gọi đang giữ, nhưng không thể gán lại biến tham chiếu của mã gọi bằng cách gán cho tham số bên trong phương thức. Bài học này trình bày cơ chế đó, cách tránh tác dụng phụ ngoài ý muốn và cách thiết kế API có hợp đồng rõ ràng trong Java 27.

## 1. Java truyền đối số theo giá trị

Khi một phương thức được gọi, Java tạo các tham số cục bộ cho lần gọi đó. Mỗi tham số nhận bản sao giá trị của đối số tương ứng. Tham số là biến cục bộ của phương thức; nó không phải bí danh cho biến ở phía gọi.

### 1.1. Với kiểu nguyên thủy

Ví dụ sau truyền một giá trị `int` vào phương thức:

```java
public class PrimitiveArgumentDemo {
    static void increase(int value) {
        value++;
        System.out.println("Trong phương thức: " + value);
    }

    public static void main(String[] args) {
        int score = 10;

        increase(score);

        System.out.println("Sau lời gọi: " + score);
    }
}
```

Kết quả:

```text
Trong phương thức: 11
Sau lời gọi: 10
```

Khi gọi `increase(score)`, giá trị `10` được sao chép vào tham số `value`. Phép `value++` chỉ cập nhật biến cục bộ đó. Biến `score` ở `main` vẫn giữ giá trị `10`.

Điều tương tự áp dụng cho các kiểu nguyên thủy còn lại: `byte`, `short`, `char`, `long`, `float`, `double` và `boolean`. Việc truyền một mảng không thuộc trường hợp này vì mảng trong Java là đối tượng và biến mảng là biến tham chiếu.

### 1.2. Với kiểu tham chiếu

Biến tham chiếu không chứa trực tiếp trạng thái của đối tượng. Nó chứa một giá trị tham chiếu dùng để truy cập đối tượng. Khi truyền biến tham chiếu vào phương thức, **giá trị tham chiếu được sao chép** vào tham số.

Do cả biến ở phía gọi và tham số đều có thể tham chiếu đến cùng một đối tượng, phương thức có thể gọi phương thức thay đổi trạng thái của đối tượng đó. Tuy nhiên, hai biến tham chiếu vẫn là hai biến độc lập.

```java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    String getName() {
        return name;
    }

    void setName(String name) {
        this.name = name;
    }
}

public class ReferenceArgumentDemo {

    static void rename(Person person) {
        person.setName("Bình");
    }

    static void replaceParameter(Person person) {
        person = new Person("Chi");
    }

    public static void main(String[] args) {
        Person original = new Person("An");

        rename(original);
        System.out.println(original.getName());

        replaceParameter(original);
        System.out.println(original.getName());
    }
}
```

Kết quả:

```text
Bình
Bình
```

Trong `rename`, tham số `person` và biến `original` cùng tham chiếu đến một đối tượng `Person`. Gọi `setName` thay đổi trạng thái của đối tượng đó nên `original.getName()` nhìn thấy tên mới.

Trong `replaceParameter`, phép `new Person("Chi")` tạo một đối tượng khác và chỉ gán tham chiếu mới cho biến cục bộ `person`. Biến `original` ở `main` vẫn tham chiếu đến đối tượng ban đầu. Khi phương thức kết thúc, tham số cục bộ không còn được sử dụng.

Đây là lý do không chính xác khi nói Java truyền đối tượng theo tham chiếu. Java truyền theo giá trị; giá trị được sao chép trong trường hợp này chính là tham chiếu.

## 2. Phân biệt thay đổi đối tượng và gán lại tham số

Hai thao tác sau có ý nghĩa khác nhau:

| Thao tác bên trong phương thức | Ảnh hưởng đến mã gọi |
| --- | --- |
| `person.setName("Bình")` | Thay đổi đối tượng mà cả hai tham chiếu đang trỏ tới; mã gọi quan sát được thay đổi |
| `person = new Person("Chi")` | Chỉ thay đổi tham chiếu cục bộ; biến tham chiếu ở mã gọi không đổi |
| `person = null` | Chỉ gán null cho tham số cục bộ; biến ở mã gọi không đổi |
| `person.name = "Bình"` (nếu được phép truy cập) | Thay đổi field của đối tượng; mã gọi quan sát được thay đổi |

Ví dụ với việc gán null:

```java
static void clearLocalReference(Person person) {
    person = null;
}

Person person = new Person("An");
clearLocalReference(person);
System.out.println(person.getName()); // Vẫn là An
```

Việc gán `null` cho tham số không xóa đối tượng, cũng không xóa tham chiếu ở phía gọi. Đối tượng chỉ đủ điều kiện để garbage collector thu hồi khi không còn đường tham chiếu có thể truy cập từ chương trình (cùng các điều kiện liên quan đến reachability).

### Một hình dung về hai biến tham chiếu

Giả sử mã gọi có biến `customer` tham chiếu đến đối tượng `Person A`. Khi gọi `rename(customer)`, Java sao chép giá trị tham chiếu đó vào tham số `person`:

```text
Trước lời gọi:
customer ───────┐
               v
             Person A

Trong phương thức:
customer ───────┐
               v
             Person A
               ^
person ─────────┘
```

Nếu `person.setName(...)`, đối tượng `Person A` thay đổi. Nếu `person = new Person(...)`, chỉ mũi tên từ `person` chuyển sang đối tượng mới; `customer` vẫn trỏ đến `Person A`.

## 3. Thay đổi trạng thái đối tượng có thể quan sát được

Một đối tượng có trạng thái thay đổi được (*mutable*) cho phép các phương thức cập nhật dữ liệu bên trong. Khi nhiều biến tham chiếu cùng trỏ đến đối tượng đó, tất cả đều quan sát được trạng thái mới.

```java
public class AccountDemo {
    static class Account {
        private int balance;

        Account(int balance) {
            this.balance = balance;
        }

        void deposit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            balance = Math.addExact(balance, amount);
        }

        int getBalance() {
            return balance;
        }
    }

    static void depositBonus(Account account, int bonus) {
        account.deposit(bonus);
    }

    public static void main(String[] args) {
        Account account = new Account(1_000);

        depositBonus(account, 250);

        System.out.println(account.getBalance()); // 1250
    }
}
```

Phương thức `depositBonus` không thay biến `account` ở phía gọi. Nó nhận một bản sao tham chiếu rồi gọi `deposit` trên cùng đối tượng. Trạng thái số dư thay đổi nên mã gọi đọc được số dư mới.

Điều này cũng có nghĩa một phương thức có thể tạo tác dụng phụ (*side effect*) ngoài giá trị trả về: thay đổi một đối tượng mà mã gọi đang dùng. Khi thiết kế API, cần nói rõ phương thức có sửa đối tượng được truyền vào hay không.

### 3.1. Nhiều tham số có thể cùng tham chiếu một đối tượng

Hai tham số không nhất thiết đại diện cho hai đối tượng khác nhau. Người gọi có thể truyền cùng một biến vào cả hai vị trí:

```java
static void copyName(Person source, Person target) {
    target.setName(source.getName());
}

Person person = new Person("An");
copyName(person, person);
```

Trong ví dụ này, `source` và `target` cùng tham chiếu đến một đối tượng. Việc đọc tên rồi ghi lại chính tên đó không tạo ra một bản sao đối tượng. Nếu thuật toán giả định hai tham số luôn khác nhau, kết quả có thể sai khi người gọi truyền cùng một đối tượng.

Khi một phương thức nhận nhiều tham chiếu có thể alias (cùng trỏ tới một đối tượng), hãy cân nhắc trường hợp này trong thiết kế và kiểm thử. Nếu không cho phép alias, cần xác định và kiểm tra điều kiện đó trong hợp đồng API.

## 4. Đối tượng bất biến và tham số

Đối tượng bất biến (*immutable*) không cho phép thay đổi trạng thái quan sát được sau khi được tạo. Ví dụ phổ biến trong Java là `String`, các lớp wrapper như `Integer`, `Long`, `Boolean`, và `BigDecimal`.

Với đối tượng bất biến, phương thức thường tạo một đối tượng mới rồi gán lại tham số cục bộ. Việc này không thay đổi biến tham chiếu ở phía gọi:

```java
static void appendSuffix(String text) {
    text = text + " Java";
    System.out.println(text);
}

String language = "Learn";
appendSuffix(language);
System.out.println(language);
```

Kết quả:

```text
Learn Java
Learn
```

Phép nối chuỗi tạo ra một giá trị `String` mới. Tham số `text` được gán tham chiếu mới, còn `language` vẫn tham chiếu đến chuỗi ban đầu.

Tương tự, phép toán với wrapper thường unbox giá trị rồi tạo kết quả primitive, sau đó autobox nếu cần:

```java
static void increase(Integer count) {
    count = count + 1;
}

Integer count = 10;
increase(count);
System.out.println(count); // 10
```

`Integer` không thay đổi giá trị bên trong. Phép `count + 1` tạo giá trị `int` mới, rồi autobox thành `Integer` cho tham số cục bộ. Biến `count` ở mã gọi vẫn giữ giá trị ban đầu.

### Record không tự động làm mọi dữ liệu bên trong bất biến

Record là kiểu dữ liệu mô tả các thành phần dữ liệu; các component field được tạo là `private final`. Tuy nhiên, nếu một component là tham chiếu đến đối tượng mutable, trạng thái của đối tượng đó vẫn có thể thay đổi:

```java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) { }

List<String> names = new ArrayList<>(List.of("An", "Bình"));
Team team = new Team(names);

names.add("Chi");
System.out.println(team.members()); // [An, Bình, Chi]
```

Component `members` không thể bị gán lại trực tiếp sau khi tạo record, nhưng nó tham chiếu đến một `List` có thể thay đổi. Vì vậy, record chỉ bất biến nông (*shallowly immutable*) nếu các component tham chiếu đến đối tượng mutable.

## 5. Mảng và collection: tham chiếu được truyền theo giá trị

Mảng là đối tượng. Khi truyền mảng vào phương thức, tham số nhận bản sao tham chiếu đến cùng mảng. Phương thức có thể sửa phần tử của mảng, nhưng gán một mảng mới cho tham số không thay mảng của mã gọi.

```java
import java.util.Arrays;

static void updateFirst(int[] values) {
    values[0] = 99; // Sửa mảng mà mã gọi đang tham chiếu
}

static void replaceArray(int[] values) {
    values = new int[] {7, 8, 9}; // Chỉ thay tham chiếu cục bộ
}

int[] numbers = {1, 2, 3};
updateFirst(numbers);
replaceArray(numbers);

System.out.println(Arrays.toString(numbers)); // [99, 2, 3]
```

Collection cũng là đối tượng. Nếu phương thức thêm hoặc xóa phần tử trên chính collection được truyền vào, người gọi quan sát được thay đổi:

```java
import java.util.ArrayList;
import java.util.List;

static void addMember(List<String> members) {
    members.add("Chi");
}

List<String> members = new ArrayList<>(List.of("An", "Bình"));
addMember(members);
System.out.println(members); // [An, Bình, Chi]
```

Nếu phương thức chỉ gán một collection mới cho tham số, biến ở phía gọi không đổi:

```java
static void replaceMembers(List<String> members) {
    members = new ArrayList<>(List.of("Dung"));
}
```

### 5.1. Varargs cũng được biểu diễn bằng mảng

Tham số varargs như `String... names` được xử lý như một mảng ở bên trong phương thức. Nếu người gọi truyền một mảng có sẵn, phương thức nhận tham chiếu đến mảng đó và có thể sửa phần tử:

```java
import java.util.Arrays;

static void renameFirst(String... names) {
    if (names.length > 0) {
        names[0] = "Người mới";
    }
}

String[] names = {"An", "Bình"};
renameFirst(names);
System.out.println(Arrays.toString(names)); // [Người mới, Bình]
```

Khi gọi `renameFirst("An", "Bình")`, trình biên dịch tạo mảng đối số cho lời gọi đó. Dù trường hợp nào, quy tắc truyền tham số vẫn là truyền giá trị tham chiếu của mảng. Nếu phần tử varargs là đối tượng mutable, việc thay đổi trạng thái của chính các đối tượng phần tử cũng có thể được mã gọi quan sát.

## 6. Vì sao không thể hoán đổi hai biến ở phía gọi bằng tham số?

Một ví dụ thường dùng để nhận biết cơ chế truyền theo giá trị là phương thức hoán đổi hai tham số:

```java
static void swap(Person first, Person second) {
    Person temporary = first;
    first = second;
    second = temporary;
}

Person a = new Person("An");
Person b = new Person("Bình");

swap(a, b);
System.out.println(a.getName()); // An
System.out.println(b.getName()); // Bình
```

`first` và `second` là hai biến tham chiếu cục bộ nhận các bản sao giá trị từ `a` và `b`. Hoán đổi chúng chỉ hoán đổi tham chiếu cục bộ. Hai biến `a` và `b` ở phía gọi không bị thay đổi.

Nếu muốn trả về hai giá trị đã hoán đổi, hãy biểu diễn kết quả bằng một kiểu dữ liệu và trả về:

```java
record PersonPair(Person first, Person second) { }

static PersonPair swapped(Person first, Person second) {
    return new PersonPair(second, first);
}

PersonPair result = swapped(a, b);
a = result.first();
b = result.second();
```

Mã gọi chủ động gán các kết quả mới vào `a` và `b`. Đây là cách rõ ràng để một phương thức cung cấp nhiều kết quả mà không cần giả định có tham số truyền theo tham chiếu.

## 7. Thiết kế API khi cần thay đổi dữ liệu

Khi viết phương thức, cần xác định mục đích của tham số: chỉ đọc, thay đổi trạng thái đối tượng, hay tạo ra một kết quả mới. Các lựa chọn sau giúp API dễ hiểu và ít gây tác dụng phụ bất ngờ.

### 7.1. Trả về giá trị mới khi muốn người gọi nhận thay đổi

Nếu muốn biến ở phía gọi nhận một tham chiếu mới, hãy trả kết quả và yêu cầu người gọi gán lại:

```java
static String normalizeName(String name) {
    return name == null ? "" : name.strip();
}

String name = "  An  ";
name = normalizeName(name);
```

Đối với mảng hoặc collection, cũng có thể trả về bản sao đã cập nhật:

```java
import java.util.Arrays;

static int[] withUpdatedFirst(int[] source, int value) {
    int[] copy = Arrays.copyOf(source, source.length);
    if (copy.length > 0) {
        copy[0] = value;
    }
    return copy;
}

int[] values = {1, 2, 3};
values = withUpdatedFirst(values, 99);
```

Cách này làm rõ rằng phương thức tạo kết quả mới; mảng đầu vào không bị sửa.

### 7.2. Dùng kiểu kết quả có tên cho nhiều giá trị

Nếu cần trả nhiều kết quả, dùng record hoặc một lớp kết quả thay vì truyền các tham số rồi mong phương thức gán lại chúng:

```java
import java.util.List;

record ValidationResult(boolean valid, List<String> errors) { }

static ValidationResult validate(String email) {
    if (email == null || email.isBlank()) {
        return new ValidationResult(false, List.of("Email is required"));
    }

    return new ValidationResult(true, List.of());
}
```

Người gọi nhận một giá trị kết quả có cấu trúc, với tên trường diễn đạt ý nghĩa. Nếu component chứa collection hoặc đối tượng mutable, hãy cân nhắc tạo bản sao phòng vệ trong constructor và khi trả dữ liệu ra ngoài.

### 7.3. Thể hiện rõ khi phương thức sửa đối tượng đầu vào

Nếu việc sửa trạng thái là chủ đích, đặt tên phương thức và tài liệu API cho thấy hành vi đó. Ví dụ `deposit`, `addMember`, `clear` và `sortInPlace` gợi ý rằng đối tượng đầu vào có thể bị thay đổi. Ngược lại, tên như `withName`, `normalized` hoặc `copyOf` thường gợi ý phương thức trả về kết quả mới.

Không nên sửa collection đầu vào nếu người gọi có thể đang chia sẻ nó với phần khác của chương trình mà hợp đồng API không nói rõ. Tác dụng phụ bất ngờ dễ gây lỗi khó tái hiện, nhất là khi nhiều thành phần cùng tham chiếu một đối tượng.

## 8. Defensive copy và quyền sở hữu dữ liệu

Nếu một lớp lưu giữ tham chiếu đến mảng hoặc collection do người gọi cung cấp, người gọi vẫn có thể sửa đối tượng đó sau khi constructor kết thúc. Khi lớp cần kiểm soát trạng thái nội bộ, hãy tạo bản sao phòng vệ (*defensive copy*).

### 8.1. Sao chép mảng

```java
import java.util.Arrays;

public final class CodeSet {
    private final int[] codes;

    public CodeSet(int[] codes) {
        this.codes = Arrays.copyOf(codes, codes.length);
    }

    public int[] codes() {
        return Arrays.copyOf(codes, codes.length);
    }
}
```

Constructor sao chép dữ liệu đầu vào để người gọi không thể thay đổi mảng nội bộ thông qua tham chiếu cũ. Phương thức `codes()` cũng trả về bản sao để người gọi không thể sửa mảng nội bộ qua kết quả trả về.

Ví dụ:

```java
int[] source = {1, 2, 3};
CodeSet codeSet = new CodeSet(source);

source[0] = 99;
int[] exported = codeSet.codes();
exported[1] = 88;

System.out.println(Arrays.toString(codeSet.codes())); // [1, 2, 3]
```

### 8.2. Collection không thể sửa

Với collection, `List.copyOf` tạo một list không thể sửa, không phản ánh các thay đổi cấu trúc sau đó trên collection nguồn:

```java
import java.util.ArrayList;
import java.util.List;

public final class TeamDirectory {
    private final List<String> names;

    public TeamDirectory(List<String> names) {
        this.names = List.copyOf(names);
    }

    public List<String> names() {
        return names;
    }
}
```

`List.copyOf` từ chối collection null và phần tử null. Kết quả là một list không thể thêm, xóa hoặc thay thế phần tử. Trong ví dụ này, phần tử là `String` bất biến nên việc chia sẻ phần tử an toàn.

Một lựa chọn khác là `Collections.unmodifiableList`. Phương thức này tạo một view không cho phép sửa thông qua view đó, nhưng view vẫn phản ánh thay đổi trên collection nền nếu collection nền còn bị sửa ở nơi khác. Nếu cần snapshot độc lập, hãy sao chép trước rồi mới bọc bằng view không thể sửa, hoặc dùng `List.copyOf` khi các quy tắc null phù hợp.

### 8.3. Sao chép nông và sao chép sâu

Sao chép mảng hoặc collection thường chỉ sao chép cấu trúc bên ngoài. Các phần tử tham chiếu đến đối tượng mutable vẫn có thể được chia sẻ:

```java
import java.util.ArrayList;
import java.util.List;

List<StringBuilder> source = new ArrayList<>();
source.add(new StringBuilder("Java"));

List<StringBuilder> copy = List.copyOf(source);
copy.get(0).append(" 27");

System.out.println(source.get(0)); // Java 27
```

`List.copyOf` không sao chép từng `StringBuilder`. Hai list vẫn cùng tham chiếu đến một phần tử. Nếu cần độc lập hoàn toàn, hãy tạo bản sao của từng đối tượng mutable theo quy tắc miền nghiệp vụ. Java không cung cấp một thao tác deep-copy tổng quát đúng cho mọi loại đối tượng.

## 9. Tham số null và xác thực đầu vào

Tham số kiểu tham chiếu có thể nhận `null`, trừ khi hợp đồng API hoặc cơ chế kiểm tra đảm bảo giá trị khác null. Nếu phương thức không chấp nhận null, hãy xác thực ngay ở đầu phương thức:

```java
import java.util.Objects;

static String normalize(String input) {
    Objects.requireNonNull(input, "input must not be null");
    return input.strip();
}
```

Nếu null có ý nghĩa hợp lệ, hãy xử lý nó theo nhánh rõ ràng:

```java
static String displayName(String input) {
    if (input == null || input.isBlank()) {
        return "Chưa cung cấp tên";
    }
    return input.strip();
}
```

Việc kiểm tra null giúp tránh NPE khi gọi phương thức hoặc truy cập field. Nó không thay đổi quy tắc truyền tham số: tham chiếu null cũng là một giá trị được sao chép vào tham số.

Với tham số có thể thay đổi, hãy xác định rõ quyền sở hữu: phương thức chỉ đọc, được phép sửa, hay cần giữ một bản sao. Với API công khai, ghi rõ các điều kiện này trong Javadoc để người gọi biết có thể tái sử dụng đối tượng sau lời gọi hay không.

## 10. Tham số final không làm đối tượng bất biến

Có thể khai báo tham số `final` để không cho phép gán lại biến tham số trong thân phương thức:

```java
static void update(final Person person) {
    person.setName("Bình"); // Hợp lệ: thay đổi trạng thái đối tượng
    // person = new Person("Chi"); // Không biên dịch: tham số final
}
```

`final` khóa việc gán lại biến tham chiếu `person`; nó không khóa trạng thái của đối tượng mà biến đang tham chiếu. Nếu đối tượng mutable, các phương thức của đối tượng vẫn có thể thay đổi trạng thái của nó.

Tương tự, khai báo một biến tham chiếu `final` ở phía gọi cũng chỉ ngăn gán lại biến đó:

```java
import java.util.ArrayList;
import java.util.List;

final List<String> names = new ArrayList<>();
names.add("An"); // Hợp lệ
// names = new ArrayList<>(); // Không biên dịch
```

Muốn bảo vệ dữ liệu, cần dùng thiết kế immutable, bản sao phòng vệ hoặc API không cung cấp quyền sửa phù hợp. Chỉ thêm `final` vào tham số không đủ để bảo đảm điều đó.

## 11. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Java truyền object theo tham chiếu | Java truyền bản sao giá trị tham chiếu đến object |
| Gán `parameter = new Object()` sẽ thay object ở phía gọi | Chỉ tham số cục bộ nhận tham chiếu mới |
| Phương thức không thể làm thay đổi object ở phía gọi | Phương thức có thể sửa trạng thái object mutable được tham chiếu chung |
| Truyền mảng sẽ sao chép toàn bộ phần tử | Tham số nhận bản sao tham chiếu đến cùng mảng |
| Tham số `final` làm object bất biến | `final` chỉ ngăn gán lại biến tham số |
| Record luôn immutable sâu | Component tham chiếu có thể trỏ đến object mutable |
| `List.copyOf` sao chép sâu từng phần tử | Nó tạo list không thể sửa; các phần tử tham chiếu vẫn có thể được chia sẻ |
| Có thể viết hàm `swap(a, b)` để đổi hai biến của caller | Gán lại hai tham số chỉ đổi các tham chiếu cục bộ; hãy trả về kết quả |

## 12. Ví dụ tổng hợp: sửa đối tượng và trả về đối tượng mới

Ví dụ sau cho thấy hai hợp đồng API khác nhau: `renameInPlace` thay đổi trạng thái đối tượng được truyền vào; `renamedCopy` tạo và trả về một đối tượng mới.

```java
public class PersonUpdateDemo {
    static final class Person {
        private final String id;
        private String name;

        Person(String id, String name) {
            this.id = id;
            this.name = name;
        }

        String id() {
            return id;
        }

        String name() {
            return name;
        }

        void rename(String name) {
            this.name = name;
        }
    }

    static void renameInPlace(Person person, String newName) {
        person.rename(newName);
    }

    static Person renamedCopy(Person person, String newName) {
        return new Person(person.id(), newName);
    }

    static void replaceOnlyParameter(Person person) {
        person = new Person("temporary", "Không thay caller");
    }

    public static void main(String[] args) {
        Person original = new Person("P-01", "An");

        renameInPlace(original, "Bình");
        System.out.println(original.name()); // Bình

        Person copy = renamedCopy(original, "Chi");
        System.out.println(original.name()); // Bình
        System.out.println(copy.name());     // Chi

        replaceOnlyParameter(original);
        System.out.println(original.name()); // Bình
    }
}
```

`renameInPlace` thay đổi đối tượng gốc; `renamedCopy` trả về đối tượng độc lập; `replaceOnlyParameter` chỉ gán lại tham số cục bộ. Tên phương thức và cách trả kết quả giúp người gọi nhận biết tác động của từng API.

## 13. Nguyên tắc thực hành

- Ghi nhớ rằng Java luôn truyền tham số theo giá trị, với cả kiểu nguyên thủy lẫn kiểu tham chiếu.
- Phân biệt giá trị tham chiếu được sao chép với đối tượng mà tham chiếu đó trỏ tới.
- Xác định phương thức có sửa trạng thái đối tượng đầu vào hay chỉ tạo kết quả mới.
- Không kỳ vọng gán lại tham số sẽ thay đổi biến tham chiếu ở phía gọi.
- Xem xét trường hợp hai tham số cùng tham chiếu một đối tượng.
- Dùng kiểu kết quả, record hoặc lớp kết quả khi cần trả nhiều giá trị.
- Tạo defensive copy khi lớp cần kiểm soát mảng hoặc collection đầu vào và đầu ra.
- Nhớ rằng copy collection thường là shallow copy; đối tượng mutable bên trong vẫn có thể được chia sẻ.
- Dùng `final` để ngăn gán lại biến khi phù hợp, nhưng không coi nó là cơ chế làm object immutable.
- Xác thực null và ghi rõ quyền sở hữu, tác dụng phụ trong hợp đồng API.

## Tài liệu tham khảo

- [Java Language Specification 27 — Chapter 15: Expressions, including method invocation and argument evaluation](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html)
- [Java Language Specification 27 — §4.3.1 Objects](https://docs.oracle.com/javase/specs/jls/se27/html/jls-4.html#jls-4.3.1)
- [Java SE 27 API — List.copyOf](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Java SE 27 API — Arrays.copyOf](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Arrays.html#copyOf(int[],int))
- [Java SE 27 API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String))
- [Java SE 27 API — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))
