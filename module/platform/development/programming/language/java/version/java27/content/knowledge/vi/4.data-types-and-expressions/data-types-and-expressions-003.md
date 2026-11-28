# Kiểu tham chiếu, null và sự khác biệt giữa giá trị với đối tượng

Trong Java 27, một biến có kiểu tham chiếu lưu một **giá trị tham chiếu** có thể dùng để truy cập một đối tượng. Bản thân biến và đối tượng là hai khái niệm khác nhau. Nhiều biến có thể cùng tham chiếu đến một đối tượng; một biến cũng có thể không tham chiếu đến đối tượng nào, khi giá trị của nó là **null**.

Hiểu đúng sự khác biệt này giúp bạn đọc và thiết kế chương trình Java chính xác hơn, đặc biệt khi làm việc với phép so sánh, phép gán, tham số phương thức, dữ liệu có thể vắng mặt và lỗi **NullPointerException**.

## 1. Giá trị và đối tượng là hai khái niệm khác nhau

Java có hai nhóm kiểu dữ liệu lớn: kiểu nguyên thủy (primitive types) và kiểu tham chiếu (reference types).

| Đặc điểm | Kiểu nguyên thủy | Kiểu tham chiếu |
|---|---|---|
| Ví dụ kiểu | **int**, **long**, **double**, **boolean** | **String**, **Person**, **int[]**, **List<String>** |
| Giá trị mà biến lưu | Một giá trị nguyên thủy thuộc kiểu đó | Một giá trị tham chiếu đến đối tượng hoặc **null** |
| Có thể nhận null | Không | Có |
| Phép **==** | So sánh giá trị nguyên thủy | So sánh hai giá trị tham chiếu theo danh tính đối tượng |
| Có thể gọi phương thức | Không gọi phương thức trên chính giá trị nguyên thủy | Có thể gọi phương thức qua tham chiếu khác null |

Ví dụ:

~~~java
int age = 27;
String name = "An";
~~~

**age** là biến kiểu nguyên thủy. Giá trị **27** được lưu theo mô hình ngôn ngữ của kiểu **int**.

**name** là biến kiểu tham chiếu. Giá trị của **name** là một tham chiếu đến đối tượng **String** biểu diễn nội dung "An".

Có thể hình dung như sau:

~~~text
age
 |
 +----> giá trị int: 27


name
 |
 +----> tham chiếu đến đối tượng String "An"
~~~

Sơ đồ chỉ diễn tả quan hệ ở mức khái niệm. Java không quy định rằng một giá trị tham chiếu phải là địa chỉ bộ nhớ có thể đọc được từ mã Java. Lập trình viên không được thực hiện phép toán con trỏ trên tham chiếu như trong một số ngôn ngữ khác.

### 1.1. Những kiểu nào là kiểu tham chiếu?

Các kiểu tham chiếu gồm:

- **Kiểu lớp (class types):** String, Object, Integer và các lớp do bạn định nghĩa.
- **Kiểu giao diện (interface types):** Runnable, List<E> và các giao diện do bạn định nghĩa. Biến có kiểu giao diện có thể tham chiếu đến một đối tượng thuộc lớp triển khai giao diện đó.
- **Kiểu mảng (array types):** chẳng hạn int[], String[] và Person[][]. Mảng cũng là đối tượng trong Java.
- **Kiểu enum:** các kiểu liệt kê do bạn khai báo bằng từ khóa enum.
- **Kiểu record:** các lớp record được khai báo bằng từ khóa record.

Ví dụ:

~~~java
class ReferenceTypeExamples {
    enum Status {
        NEW, IN_PROGRESS, DONE
    }

    void show() {
        String title = "Java";
        int[] scores = {8, 9, 10};
        Runnable task = () -> System.out.println("Running");
        Status status = Status.NEW;
    }
}
~~~

Các biến **title**, **scores**, **task** và **status** đều là biến kiểu tham chiếu. Chúng có thể mang giá trị null nếu được khai báo theo kiểu tham chiếu và chưa được gán một tham chiếu hợp lệ khác.

### 1.2. Đối tượng có trạng thái và danh tính

Một đối tượng thường có:

- **Trạng thái (state):** dữ liệu hiện tại của các trường và những dữ liệu mà đối tượng quản lý.
- **Hành vi (behavior):** các phương thức mà đối tượng cung cấp.
- **Danh tính (identity):** khả năng phân biệt một đối tượng cụ thể với một đối tượng khác, ngay cả khi chúng có cùng trạng thái.

Ví dụ, hai đối tượng Person có cùng tên vẫn có thể là hai đối tượng khác nhau:

~~~java
class Person {
    String name;

    Person(String name) {
        this.name = name;
    }
}

Person first = new Person("An");
Person second = new Person("An");
~~~

Hai đối tượng có cùng trạng thái ban đầu (name đều là "An"), nhưng được tạo bởi hai lần gọi new riêng biệt. Vì vậy, **first** và **second** tham chiếu đến hai đối tượng khác nhau.

Điều này tạo ra sự khác biệt quan trọng giữa **bằng nhau về nội dung** và **cùng một đối tượng**. Phần sau sẽ phân tích cách kiểm tra hai trường hợp này.

## 2. Biến tham chiếu và phép gán

Khi gán một biến tham chiếu cho biến tham chiếu khác, Java sao chép **giá trị tham chiếu**. Phép gán không tự động tạo bản sao của đối tượng.

~~~java
Person first = new Person("An");
Person second = first;
~~~

Sau phép gán, hai biến cùng tham chiếu đến một đối tượng:

~~~text
first  ----+
           |
           +------> Person object { name = "An" }
           |
second ----+
~~~

Có thể quan sát việc dùng chung đối tượng:

~~~java
second.name = "Binh";

System.out.println(first.name);  // Binh
System.out.println(second.name); // Binh
~~~

Thay đổi thông qua **second** được nhìn thấy khi truy cập qua **first**, vì cả hai cùng tham chiếu đến một đối tượng.

### 2.1. Gán lại biến không đồng nghĩa thay đổi đối tượng cũ

Xét tiếp:

~~~java
Person first = new Person("An");
Person second = first;

first = new Person("Binh");

System.out.println(first.name);  // Binh
System.out.println(second.name); // An
~~~

Sau lệnh gán lại, **first** tham chiếu đến đối tượng mới. **second** vẫn tham chiếu đến đối tượng cũ.

~~~text
first  --------> Person object mới { name = "Binh" }

second --------> Person object cũ { name = "An" }
~~~

Phép gán lại biến chỉ thay đổi giá trị tham chiếu đang được biến lưu. Nó không tự thay đổi những biến khác và không sửa trạng thái của đối tượng cũ.

### 2.2. final với biến tham chiếu

Từ khóa **final** có thể ngăn một biến tham chiếu được gán lại sau khi đã khởi tạo:

~~~java
final Person person = new Person("An");

person.name = "Binh"; // Hợp lệ: thay đổi trạng thái đối tượng
// person = new Person("Lan"); // Lỗi biên dịch: không thể gán lại biến final
~~~

**final** ở đây bảo vệ giá trị tham chiếu của biến khỏi việc gán lại. Nó không tự làm cho đối tượng trở thành bất biến (immutable).

Nếu muốn đối tượng bất biến, thiết kế lớp phải kiểm soát trạng thái của chính đối tượng, ví dụ dùng trường **private final**, không cung cấp phương thức sửa đổi và không để lộ dữ liệu mutable có thể bị thay đổi từ bên ngoài.

## 3. Giá trị null là gì?

**null** là một literal đặc biệt biểu thị **không có tham chiếu đến đối tượng**. Nó có thể được gán cho biến có kiểu tham chiếu.

~~~java
String name = null;
Person person = null;
int[] numbers = null;
~~~

Ba biến trên có kiểu tham chiếu, nhưng hiện không tham chiếu đến đối tượng nào.

**null** không phải là:

- Số **0**.
- Chuỗi rỗng **""**.
- Giá trị **false**.
- Một đối tượng đặc biệt mà bạn có thể gọi phương thức.
- Một giá trị có thể gán trực tiếp cho biến kiểu nguyên thủy.

Ví dụ:

~~~java
String empty = "";
String missing = null;

System.out.println(empty.isEmpty()); // true
System.out.println(missing == null); // true
~~~

Chuỗi rỗng là một đối tượng String có độ dài bằng 0. **null** biểu thị không có tham chiếu đến một đối tượng String.

### 3.1. null chỉ dùng với kiểu tham chiếu

Ví dụ hợp lệ:

~~~java
String text = null;
Object value = null;
Integer count = null;
~~~

Ví dụ không hợp lệ:

~~~java
// int count = null;       // Lỗi biên dịch
// boolean active = null;  // Lỗi biên dịch
~~~

Bạn cũng không thể dùng **null** làm kiểu khai báo tường minh:

~~~java
// null value; // Không có kiểu khai báo tên là null
~~~

Với biến cục bộ dùng **var**, trình biên dịch cần suy ra kiểu từ biểu thức khởi tạo. **null** đứng một mình không cung cấp đủ kiểu để suy luận:

~~~java
// var value = null; // Lỗi biên dịch
String value = null;  // Hợp lệ vì kiểu được khai báo rõ
~~~

### 3.2. Giá trị mặc định của biến tham chiếu

Nếu một trường (field) có kiểu tham chiếu không được khởi tạo tường minh, Java gán giá trị mặc định là **null**.

~~~java
class Account {
    String owner;       // Mặc định null
    Integer balance;    // Mặc định null
    int retryCount;     // Mặc định 0
    boolean enabled;    // Mặc định false
}
~~~

Ngược lại, biến cục bộ phải được gán giá trị trước khi được đọc:

~~~java
void printName() {
    String name;
    // System.out.println(name); // Lỗi biên dịch: biến cục bộ chưa được khởi tạo
}
~~~

Không nên dựa vào giá trị mặc định null như một cách thiết kế trạng thái thiếu dữ liệu nếu chương trình có thể biểu diễn trạng thái đó rõ ràng hơn. Hãy xác định hợp đồng của trường và phương thức: dữ liệu có bắt buộc hay không, khi vắng mặt cần xử lý như thế nào.

## 4. So sánh hai giá trị tham chiếu: == và equals

Một trong những lỗi phổ biến khi làm việc với đối tượng là dùng **==** để kiểm tra hai đối tượng có nội dung giống nhau.

Trong Java, cần phân biệt:

- **Đồng nhất (identity):** hai tham chiếu cùng trỏ đến một đối tượng.
- **Bằng nhau theo logic (logical equality):** hai đối tượng được xem là bằng nhau theo quy tắc do kiểu của chúng định nghĩa.

### 4.1. Toán tử ==

Với kiểu nguyên thủy, **==** so sánh giá trị:

~~~java
int a = 10;
int b = 10;

System.out.println(a == b); // true
~~~

Với kiểu tham chiếu, **==** kiểm tra hai giá trị tham chiếu có cùng chỉ đến một đối tượng hay không. Nếu cả hai đều là null, kết quả cũng là true.

~~~java
Person first = new Person("An");
Person second = first;
Person third = new Person("An");

System.out.println(first == second); // true
System.out.println(first == third);  // false
System.out.println(first == null);   // false
System.out.println((Person) null == null); // true
~~~

**first** và **second** cùng tham chiếu đến một đối tượng. **third** tham chiếu đến một đối tượng khác, dù hai đối tượng có thể có cùng nội dung.

### 4.2. Phương thức equals

**equals** là phương thức được kế thừa từ lớp **Object**. Triển khai mặc định trong Object có hành vi tương đương so sánh danh tính. Các lớp có thể ghi đè phương thức này để định nghĩa thế nào là hai đối tượng bằng nhau về mặt logic.

Ví dụ với String:

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

Hai đối tượng String khác nhau nhưng có cùng chuỗi ký tự. String định nghĩa equals để so sánh nội dung chuỗi.

Khi muốn so sánh nội dung, hãy dùng phương thức equality mà kiểu dữ liệu cung cấp, thay vì mặc định dùng **==**.

### 4.3. Vì sao không nên so sánh chuỗi bằng ==?

Chuỗi literal có thể được lưu trong string pool. Vì vậy, hai biến khởi tạo từ cùng một literal có thể cùng tham chiếu đến một đối tượng:

~~~java
String a = "Java";
String b = "Java";

System.out.println(a == b);      // Có thể là true do string interning
System.out.println(a.equals(b)); // true
~~~

Tuy nhiên, điều đó không biến **==** thành cách kiểm tra nội dung chuỗi. Kết quả của **==** phụ thuộc vào việc hai biến có cùng tham chiếu hay không.

Hãy luôn dùng **equals** để so sánh nội dung chuỗi:

~~~java
if ("Java".equals(language)) {
    System.out.println("Đang học Java");
}
~~~

Cách viết trên còn tránh lỗi NullPointerException nếu **language** đang là null, vì đối tượng nhận lời gọi phương thức là chuỗi literal không null.

### 4.4. Hợp đồng của equals và hashCode

Khi ghi đè **equals**, lớp cần tuân thủ hợp đồng của phương thức. Những tính chất quan trọng gồm:

- **Phản xạ:** x.equals(x) phải là true.
- **Đối xứng:** nếu x.equals(y) là true thì y.equals(x) cũng phải là true.
- **Bắc cầu:** nếu x.equals(y) và y.equals(z) là true thì x.equals(z) cũng phải là true.
- **Nhất quán:** nếu trạng thái liên quan đến so sánh không thay đổi, kết quả gọi lặp lại phải nhất quán.
- Với mọi đối tượng khác null, x.equals(null) phải là false.

Nếu hai đối tượng bằng nhau theo equals, chúng phải có cùng giá trị hashCode. Chiều ngược lại không bắt buộc: hai đối tượng có cùng hashCode chưa chắc bằng nhau.

Quy tắc này đặc biệt quan trọng khi đối tượng được dùng làm khóa trong **HashMap** hoặc phần tử trong **HashSet**.

Ví dụ, nếu một lớp định nghĩa equals dựa trên mã tài khoản, hashCode cũng phải được tính dựa trên mã tài khoản đó. Không nên để hai phương thức sử dụng các tiêu chí khác nhau.

### 4.5. So sánh an toàn khi một giá trị có thể là null

Gọi phương thức trên một biến đang là null sẽ gây NullPointerException:

~~~java
String input = null;

// input.equals("Java"); // NullPointerException
~~~

Nếu cả hai giá trị đều có thể là null, dùng **Objects.equals**:

~~~java
import java.util.Objects;

String first = null;
String second = null;

System.out.println(Objects.equals(first, second)); // true
System.out.println(Objects.equals(first, "Java"));  // false
~~~

**Objects.equals(a, b)** xử lý các trường hợp:

| a | b | Kết quả |
|---|---|---|
| null | null | true |
| null | "Java" | false |
| "Java" | null | false |
| "Java" | "Java" | true nếu hai chuỗi có nội dung bằng nhau |

Với mảng, equals kế thừa từ Object không so sánh nội dung từng phần tử. Dùng **Arrays.equals** cho mảng một chiều hoặc **Arrays.deepEquals** khi cần so sánh sâu các mảng lồng nhau:

~~~java
import java.util.Arrays;

int[] first = {1, 2, 3};
int[] second = {1, 2, 3};

System.out.println(first == second);              // false
System.out.println(first.equals(second));         // false
System.out.println(Arrays.equals(first, second)); // true
~~~

## 5. Truyền biến tham chiếu vào phương thức

Java luôn truyền tham số theo giá trị (pass-by-value). Khi đối số là biến tham chiếu, **giá trị tham chiếu được sao chép** vào tham số hình thức của phương thức.

Ví dụ:

~~~java
class Box {
    String label;

    Box(String label) {
        this.label = label;
    }
}

public class Main {
    static void changeLabel(Box box) {
        box.label = "Đã thay đổi";
    }

    public static void main(String[] args) {
        Box original = new Box("Ban đầu");

        changeLabel(original);

        System.out.println(original.label); // Đã thay đổi
    }
}
~~~

Tham số **box** và biến **original** là hai biến tham chiếu riêng biệt, nhưng ban đầu cùng chứa giá trị tham chiếu đến một đối tượng. Vì vậy, thay đổi trạng thái của đối tượng thông qua **box** được quan sát qua **original**.

Điều này không có nghĩa Java truyền tham chiếu theo kiểu pass-by-reference. Có thể chứng minh bằng cách gán lại tham số:

~~~java
static void replace(Box box) {
    box = new Box("Đối tượng mới");
}

public static void main(String[] args) {
    Box original = new Box("Đối tượng ban đầu");

    replace(original);

    System.out.println(original.label); // Đối tượng ban đầu
}
~~~

Phép gán **box = new Box(...)** chỉ thay đổi biến tham số cục bộ **box**. Nó không thay đổi biến **original** ở nơi gọi.

Cần ghi nhớ:

- Có thể thay đổi trạng thái đối tượng nếu tham số và biến bên ngoài cùng tham chiếu đến đối tượng mutable.
- Có thể thay đổi biến tham chiếu cục bộ bằng cách gán lại tham số.
- Không thể thay đổi trực tiếp giá trị tham chiếu mà biến của bên gọi đang lưu bằng cách gán lại tham số.
- Nếu đối tượng bất biến, phương thức không thể sửa trạng thái của đối tượng đó thông qua các API thông thường; phương thức có thể trả về một đối tượng mới.

## 6. Alias và hệ quả của việc nhiều biến cùng tham chiếu

Khi nhiều biến tham chiếu đến cùng một đối tượng, chúng được gọi là các alias của đối tượng đó.

~~~java
List<String> first = new ArrayList<>();
List<String> second = first;

second.add("Java");

System.out.println(first); // [Java]
~~~

Hai biến có tên khác nhau nhưng cùng truy cập một danh sách. Đây là hành vi hợp lệ và thường được dùng khi truyền đối tượng giữa các phương thức. Tuy nhiên, alias có thể khiến việc thay đổi trạng thái trở nên khó theo dõi nếu nhiều phần của chương trình cùng giữ tham chiếu đến một đối tượng mutable.

### 6.1. Phân biệt sao chép tham chiếu và sao chép đối tượng

~~~java
List<String> source = new ArrayList<>();
source.add("Java");

List<String> alias = source; // Chỉ sao chép giá trị tham chiếu

List<String> copy = new ArrayList<>(source); // Tạo danh sách mới
~~~

Sau đó:

~~~java
alias.add("Kotlin");
copy.add("Go");

System.out.println(source); // [Java, Kotlin]
System.out.println(alias);  // [Java, Kotlin]
System.out.println(copy);   // [Java, Go]
~~~

**alias** dùng chung danh sách với **source**. **copy** là một danh sách khác.

Tuy nhiên, **new ArrayList<>(source)** chỉ tạo **bản sao nông (shallow copy)**. Các phần tử bên trong danh sách vẫn là những tham chiếu được sao chép. Nếu phần tử là đối tượng mutable, danh sách mới và danh sách cũ vẫn có thể cùng tham chiếu đến các đối tượng phần tử đó.

Ví dụ:

~~~java
List<Person> people = new ArrayList<>();
people.add(new Person("An"));

List<Person> copiedPeople = new ArrayList<>(people);

copiedPeople.get(0).name = "Binh";

System.out.println(people.get(0).name); // Binh
~~~

Danh sách đã được sao chép, nhưng đối tượng Person bên trong chưa được sao chép. Nếu cần bản sao sâu, phải xác định rõ đối tượng nào cần sao chép và cách sao chép trạng thái của từng đối tượng. Java không tự động tạo bản sao sâu khi thực hiện phép gán tham chiếu hoặc tạo collection mới từ collection cũ.

### 6.2. Đối tượng bất biến giúp giảm rủi ro alias

Đối tượng bất biến không cho phép thay đổi trạng thái quan sát được sau khi khởi tạo. Ví dụ phổ biến gồm **String**, các lớp wrapper như **Integer** và nhiều lớp ngày giờ trong **java.time**.

Nếu nhiều phần của chương trình cùng tham chiếu đến một đối tượng bất biến, chúng có thể đọc dữ liệu mà không lo phần khác sửa trạng thái của đối tượng đó.

Record cũng hỗ trợ tạo kiểu dữ liệu bất biến theo cách thuận tiện, nhưng cần hiểu rằng record chỉ làm các component thành trường final; nó không tự bảo đảm mọi đối tượng được tham chiếu từ component đều bất biến.

~~~java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) {
}
~~~

Trường **members** của record không thể được gán lại sau khi khởi tạo, nhưng danh sách được truyền vào vẫn có thể mutable:

~~~java
List<String> names = new ArrayList<>();
names.add("An");

Team team = new Team(names);

names.add("Binh");
System.out.println(team.members()); // [An, Binh]
~~~

Nếu cần bảo vệ dữ liệu, hãy tạo bản sao phù hợp và cung cấp giao diện đọc không cho sửa đổi. Việc đó phải được thực hiện có chủ đích trong constructor hoặc phương thức truy cập; record không tự thực hiện deep copy.

## 7. null và lỗi NullPointerException

**NullPointerException (NPE)** xuất hiện khi chương trình thực hiện một thao tác cần truy cập đối tượng thông qua giá trị tham chiếu null.

Ví dụ:

~~~java
String name = null;
System.out.println(name.length()); // NullPointerException
~~~

Một số trường hợp phổ biến:

| Thao tác | Ví dụ có thể gây NPE |
|---|---|
| Gọi phương thức instance | name.length() khi name là null |
| Truy cập trường instance | person.name khi person là null |
| Truy cập phần tử mảng | items[0] khi items là null |
| Lấy độ dài mảng | items.length khi items là null |
| Unboxing wrapper null | int count = boxedCount; khi boxedCount là null |
| Đồng bộ trên monitor null | synchronized (lock) khi lock là null |

NPE thường xuất hiện tại nơi chương trình sử dụng giá trị null. Vì vậy, khi đọc stack trace, hãy xác định dòng đầu tiên thuộc mã ứng dụng và kiểm tra các biểu thức tham chiếu được dùng ở dòng đó.

### 7.1. null khi unboxing kiểu wrapper

Các lớp như **Integer**, **Long**, **Double** và **Boolean** là kiểu tham chiếu bao bọc giá trị nguyên thủy. Khi chuyển wrapper sang primitive, Java thực hiện unboxing.

~~~java
Integer quantity = null;
int count = quantity; // NullPointerException
~~~

Không có giá trị nguyên thủy nào tương ứng với null, vì vậy thao tác unboxing không thể hoàn thành.

Nếu giá trị có thể vắng mặt, hãy kiểm tra trước khi unbox:

~~~java
Integer quantity = null;

if (quantity != null) {
    int count = quantity;
    System.out.println(count);
}
~~~

### 7.2. Kiểm tra null bằng điều kiện

Cách đơn giản nhất là kiểm tra trước khi sử dụng:

~~~java
String name = null;

if (name != null) {
    System.out.println(name.length());
} else {
    System.out.println("Chưa có tên");
}
~~~

Toán tử **&&** và **||** có cơ chế short-circuit. Vì vậy, có thể viết điều kiện kiểm tra null rồi mới gọi phương thức:

~~~java
String name = null;

if (name != null && name.startsWith("A")) {
    System.out.println("Tên bắt đầu bằng A");
}
~~~

Vế phải của **&&** chỉ được đánh giá khi vế trái là true, nên **name.startsWith** không được gọi nếu **name** là null.

### 7.3. Dùng Objects.requireNonNull để bảo vệ hợp đồng

Nếu một phương thức yêu cầu đối số bắt buộc không được null, hãy kiểm tra ngay tại ranh giới phương thức:

~~~java
import java.util.Objects;

class UserService {
    void register(String username) {
        Objects.requireNonNull(username, "username không được null");

        System.out.println("Đăng ký: " + username);
    }
}
~~~

**Objects.requireNonNull** trả về tham chiếu nếu giá trị không null; nếu giá trị null, phương thức ném NullPointerException. Cách này làm rõ điều kiện đầu vào và giúp lỗi xuất hiện gần nơi dữ liệu đi vào hệ thống.

### 7.4. Dùng giá trị mặc định khi phù hợp

Nếu null có nghĩa là chưa cung cấp một giá trị tùy chọn và nghiệp vụ cho phép dùng mặc định, có thể sử dụng toán tử ba ngôi hoặc các tiện ích của **Objects**.

~~~java
import java.util.Objects;

String name = null;
String displayName = Objects.requireNonNullElse(name, "Khách");
~~~

**Objects.requireNonNullElse** trả về giá trị đầu tiên nếu không null, nếu không sẽ trả về giá trị thay thế. Khi giá trị đầu tiên là null, giá trị thay thế cũng phải khác null; nếu cả hai đều null, phương thức ném NullPointerException.

Nếu việc tạo giá trị mặc định tốn tài nguyên hoặc cần thực hiện có điều kiện, dùng **Objects.requireNonNullElseGet** với một Supplier:

~~~java
String name = null;
String displayName =
        Objects.requireNonNullElseGet(name, () -> "Khách");
~~~

Không nên thay thế mọi null bằng một chuỗi rỗng hoặc số 0 một cách máy móc. Hãy chọn mặc định dựa trên ý nghĩa nghiệp vụ; ví dụ, không có số dư tài khoản khác với số dư bằng 0.

## 8. Dùng Optional để biểu diễn kết quả có thể vắng mặt

**Optional<T>** là một kiểu tham chiếu dùng để biểu diễn một kết quả có thể có hoặc không có giá trị. Nó hữu ích khi một phương thức cần thông báo rõ rằng kết quả có thể vắng mặt.

~~~java
import java.util.Optional;

class UserRepository {
    Optional<String> findUsernameById(long id) {
        if (id == 1L) {
            return Optional.of("An");
        }

        return Optional.empty();
    }
}
~~~

Người gọi có thể xử lý kết quả:

~~~java
UserRepository repository = new UserRepository();
Optional<String> result = repository.findUsernameById(1L);

String username = result.orElse("Người dùng ẩn danh");
System.out.println(username);
~~~

Một số phương thức thường dùng:

| Phương thức | Công dụng |
|---|---|
| **Optional.empty()** | Tạo Optional không chứa giá trị |
| **Optional.of(value)** | Tạo Optional chứa giá trị khác null; nếu null thì ném NPE |
| **Optional.ofNullable(value)** | Tạo Optional rỗng nếu giá trị là null |
| **isPresent()** | Kiểm tra có giá trị hay không |
| **ifPresent(action)** | Thực hiện hành động nếu có giá trị |
| **map(function)** | Chuyển đổi giá trị bên trong nếu có |
| **orElse(other)** | Lấy giá trị bên trong hoặc giá trị thay thế |
| **orElseGet(supplier)** | Lấy giá trị bên trong hoặc gọi supplier để tạo giá trị thay thế |
| **orElseThrow()** | Lấy giá trị hoặc ném NoSuchElementException nếu rỗng |

Ví dụ với **map**:

~~~java
Optional<String> username = Optional.of("An");

String upperName = username
        .map(String::toUpperCase)
        .orElse("UNKNOWN");

System.out.println(upperName); // AN
~~~

Không nên gọi **get()** mà không kiểm tra trạng thái của Optional. Nếu Optional rỗng, get() ném NoSuchElementException. Thông thường, hãy dùng **map**, **orElse**, **orElseGet**, **orElseThrow** hoặc **ifPresent** để thể hiện rõ cách xử lý.

**Optional** thường phù hợp nhất làm kiểu trả về cho phương thức có kết quả có thể không tồn tại. Không nên tự động bọc mọi trường, tham số hoặc phần tử collection bằng Optional; hãy tuân theo hợp đồng API và quy ước của dự án.

Cũng cần nhớ rằng bản thân biến Optional vẫn là biến tham chiếu. Một phương thức được thiết kế trả về Optional nên trả **Optional.empty()** thay vì trả null để biểu diễn kết quả vắng mặt.

## 9. Một số trường hợp đặc biệt cần nhớ

### 9.1. Wrapper class và so sánh

Các lớp wrapper như **Integer** là kiểu tham chiếu. Khi dùng **==** giữa hai wrapper, bạn đang so sánh tham chiếu, không phải giá trị số được bao bọc.

~~~java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

System.out.println(first.equals(second)); // true
~~~

Không nên dựa vào **==** để so sánh wrapper. Một số giá trị boxing có thể được dùng lại từ bộ nhớ đệm theo quy tắc của Java, khiến phép **==** đôi khi trả về true dù bạn không chủ ý so sánh danh tính. Hãy dùng **equals** để so sánh giá trị wrapper hoặc chuyển sang primitive khi chắc chắn không null.

~~~java
Integer first = 1000;
Integer second = 1000;

boolean sameValue = first.equals(second);
~~~

Nếu wrapper có thể là null, hãy kiểm tra null hoặc dùng **Objects.equals** trước khi unbox.

### 9.2. Record: bằng nhau theo component, nhưng vẫn là đối tượng

Record tự sinh các phương thức như **equals**, **hashCode** và **toString** dựa trên các component được khai báo.

~~~java
record Point(int x, int y) {
}

Point first = new Point(3, 4);
Point second = new Point(3, 4);

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false
~~~

Hai record có component bằng nhau theo quy tắc của record có thể được xem là bằng nhau theo equals, nhưng mỗi lần gọi new vẫn tạo một đối tượng riêng. Vì vậy, **==** và **equals** vẫn có ý nghĩa khác nhau.

Nếu component là mảng, cần lưu ý rằng so sánh component theo equals của mảng không tự động so sánh nội dung các phần tử. Hãy cân nhắc kiểu dữ liệu component và định nghĩa equality phù hợp với yêu cầu.

### 9.3. Mảng là đối tượng

Mảng trong Java có kiểu tham chiếu và có thể nhận null:

~~~java
String[] names = {"An", "Binh"};
String[] missingNames = null;

System.out.println(names.length); // 2
// System.out.println(missingNames.length); // NPE
~~~

Khi gán mảng:

~~~java
int[] first = {1, 2};
int[] second = first;

second[0] = 99;

System.out.println(first[0]); // 99
~~~

Hai biến tham chiếu cùng một mảng. Nếu cần sao chép mảng một chiều, có thể dùng **Arrays.copyOf** hoặc **clone**:

~~~java
import java.util.Arrays;

int[] original = {1, 2, 3};
int[] copy = Arrays.copyOf(original, original.length);

copy[0] = 99;

System.out.println(original[0]); // 1
System.out.println(copy[0]);     // 99
~~~

Với mảng nhiều chiều, sao chép mảng ngoài không tự động sao chép sâu các mảng con.

### 9.4. instanceof với null

Phép kiểm tra kiểu **instanceof** trả về false nếu biểu thức bên trái là null:

~~~java
Object value = null;

System.out.println(value instanceof String); // false
~~~

Với pattern matching cho instanceof, biến pattern chỉ khả dụng khi đối tượng không null và phù hợp với kiểu được kiểm tra:

~~~java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

Cách viết này vừa kiểm tra kiểu vừa tạo biến **text** có kiểu String trong nhánh đúng.

## 10. Chọn cách biểu diễn dữ liệu vắng mặt

Không phải mọi trường hợp thiếu dữ liệu đều nên dùng null. Hãy xác định ý nghĩa của trạng thái đó trước khi chọn cách biểu diễn.

| Trường hợp | Cách biểu diễn thường phù hợp | Ý nghĩa |
|---|---|---|
| Một đối tượng bắt buộc phải tồn tại | Yêu cầu non-null và kiểm tra ở ranh giới API | Thiếu đối tượng là lỗi đầu vào hoặc lỗi trạng thái |
| Kết quả tìm kiếm có thể không tồn tại | **Optional<T>** làm kiểu trả về | Không tìm thấy là một kết quả hợp lệ |
| Một trường văn bản bắt buộc nhưng chưa hợp lệ | Kiểm tra và báo lỗi xác thực | Chuỗi rỗng và null cần được phân biệt |
| Danh sách không có phần tử | Collection rỗng | Có danh sách, nhưng hiện không chứa phần tử |
| Một tham số tùy chọn có giá trị mặc định hợp lệ | Giá trị mặc định hoặc **Objects.requireNonNullElse** | Thiếu đầu vào được thay bằng quy tắc mặc định |
| Trạng thái chưa được khởi tạo trong mô hình đối tượng | null chỉ khi hợp đồng cho phép và có kiểm tra | Chưa có tham chiếu đến đối tượng |

Một số collection factory như **List.of(...)**, **Set.of(...)** và **Map.of(...)** không chấp nhận phần tử hoặc khóa/giá trị null. Các triển khai collection khác có thể cho phép null. Hãy đọc hợp đồng API cụ thể thay vì giả định mọi collection đều xử lý null giống nhau.

## 11. Ví dụ tổng hợp

Ví dụ sau kết hợp kiểu tham chiếu, null, so sánh và Optional trong một trường hợp tìm kiếm người dùng.

~~~java
import java.util.Objects;
import java.util.Optional;

record User(long id, String name) {
    User {
        Objects.requireNonNull(name, "name không được null");
    }
}

class UserService {
    private final User user = new User(1L, "An");

    Optional<User> findById(long id) {
        if (user.id() == id) {
            return Optional.of(user);
        }

        return Optional.empty();
    }

    String displayName(long id) {
        return findById(id)
                .map(User::name)
                .orElse("Không tìm thấy người dùng");
    }
}

public class Main {
    public static void main(String[] args) {
        UserService service = new UserService();

        System.out.println(service.displayName(1L));
        System.out.println(service.displayName(2L));

        User first = new User(10L, "Binh");
        User second = new User(10L, "Binh");

        System.out.println(first == second);
        System.out.println(first.equals(second));
    }
}
~~~

Kết quả:

~~~text
An
Không tìm thấy người dùng
false
true
~~~

Trong ví dụ:

1. **User** là record, một kiểu tham chiếu.
2. Constructor của record kiểm tra **name** không null.
3. **findById** trả về **Optional<User>** để biểu diễn trường hợp tìm thấy hoặc không tìm thấy.
4. **displayName** dùng **map** và **orElse** để chuyển kết quả thành nội dung hiển thị.
5. Hai đối tượng User được tạo riêng nên **first == second** là false.
6. Record sinh **equals** dựa trên component, nên hai đối tượng có component bằng nhau trả về true khi gọi **equals**.

## 12. Checklist khi làm việc với kiểu tham chiếu

Khi thiết kế hoặc đọc mã Java, hãy tự kiểm tra:

- Biến đang dùng là kiểu nguyên thủy hay kiểu tham chiếu?
- Giá trị tham chiếu có thể là null theo hợp đồng của chương trình không?
- Phép gán đang sao chép giá trị tham chiếu hay tạo một đối tượng mới?
- Hai biến có thể cùng tham chiếu đến một đối tượng mutable không?
- Khi so sánh, bạn muốn kiểm tra cùng đối tượng (**==**) hay bằng nhau theo nội dung (**equals**)?
- Nếu dùng **equals**, lớp đó có định nghĩa equality phù hợp và triển khai **hashCode** nhất quán không?
- Có thể phát sinh NPE khi gọi phương thức, truy cập trường, truy cập mảng hoặc unboxing không?
- Trạng thái vắng mặt nên được biểu diễn bằng null, Optional, collection rỗng hay một kiểu trạng thái cụ thể?
- Nếu tạo bản sao collection hoặc mảng, đó là shallow copy hay deep copy?
- Đối tượng có cần bất biến để giảm rủi ro khi nhiều phần của chương trình cùng tham chiếu không?

## Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 27 — Types, Values, and Variables (Chapter 4)](https://docs.oracle.com/javase/specs/jls/se27/html/jls-4.html)
- [Java Language Specification, Java SE 27 — Expressions (Chapter 15), Equality Operators](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html)
- [Object API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Object.html)
- [Objects API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Objects.html)
- [Optional API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Optional.html)
- [Arrays API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Arrays.html)
- [Record API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Record.html)
