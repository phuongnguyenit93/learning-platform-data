# Type checking trong Java

## Mục tiêu

Sau bài này, bạn có thể giải thích compiler kiểm tra kiểu dữ liệu ở thời điểm biên dịch như thế nào; phân biệt kiểu tĩnh của biến với class thực tế của object; hiểu phép gán, chuyển đổi kiểu, overload, generic và type inference; nhận biết lỗi được phát hiện ở compile time hay runtime; và đọc các cảnh báo của javac để sửa lỗi an toàn.

## 1. Type checking là gì?

**Type checking (kiểm tra kiểu)** là quá trình xác minh rằng các giá trị, biểu thức, biến, tham số và lời gọi phương thức được sử dụng theo những quy tắc kiểu của Java.

Java là ngôn ngữ **statically typed**: phần lớn thông tin kiểu được xác định và kiểm tra khi biên dịch. Compiler cần biết kiểu của biểu thức để quyết định:

- Giá trị có thể gán cho biến hay không.
- Đối số có phù hợp với kiểu tham số của method/constructor hay không.
- Method hoặc constructor overload nào có thể được gọi.
- Một phép toán có hợp lệ với các toán hạng hay không.
- Kiểu generic nào được suy luận và có tương thích với nhau không.
- Một phép cast có thể được chấp nhận ở compile time hay cần kiểm tra thêm khi chạy.

Ví dụ:

~~~java
int age = 20;
String name = "An";

age = name;
~~~

Dòng cuối gây compile-time error vì String không thể được gán trực tiếp cho biến int. Compiler phát hiện vấn đề trước khi chương trình chạy.

Ngược lại:

~~~java
String name = null;
System.out.println(name.length());
~~~

Code này hợp lệ về kiểu nên compiler cho phép biên dịch. Nhưng khi chạy, lời gọi length() trên null gây NullPointerException. Type checking không chứng minh mọi giá trị runtime đều hợp lệ; nó xác minh các quy tắc kiểu mà ngôn ngữ có thể kiểm tra tĩnh.

## 2. Type checking nằm ở đâu trong compilation pipeline?

Một cách nhìn khái quát về quá trình biên dịch Java:

~~~text
Java source (.java)
       |
       v
Lexical analysis / parsing
       |
       v
Enter symbols and resolve declarations
       |
       v
Annotation processing (nếu có)
       |
       v
Attribution / type checking
       |
       v
Flow analysis
       |
       v
Desugaring and code generation
       |
       v
Bytecode (.class)
~~~

Các bước có thể được javac thực hiện xen kẽ hoặc lặp lại theo nhu cầu của annotation processing và dependency. Sơ đồ mô tả vai trò khái niệm, không phải hợp đồng về thứ tự nội bộ cho mọi compiler.

- **Parsing:** kiểm tra token và cấu trúc cú pháp. Ví dụ thiếu dấu chấm phẩy hoặc ngoặc đóng là lỗi cú pháp.
- **Enter symbols:** ghi nhận class, interface, method, field, type parameter và các khai báo để compiler có thể tra cứu.
- **Attribution/type checking:** xác định kiểu của biểu thức, tra cứu member, chọn overload, suy luận generic và kiểm tra các phép chuyển đổi.
- **Flow analysis:** kiểm tra các điều kiện như definite assignment, khả năng biến được khởi tạo trước khi đọc và một số quy tắc luồng điều khiển.
- **Code generation:** tạo bytecode khi các kiểm tra cần thiết thành công.

Một lỗi type checking thường được javac báo với vị trí dòng/cột và thông tin kiểu mong đợi/thực tế. Khi compiler báo incompatible types, no suitable method found hoặc reference to ... is ambiguous, hãy xem đó là vấn đề ở quy tắc kiểu hoặc lựa chọn method, không phải lỗi cú pháp đơn thuần.

## 3. Kiểu tĩnh và kiểu runtime

Mỗi biến và biểu thức Java có một **static type (kiểu tĩnh)** mà compiler dùng để kiểm tra code. Một object có **runtime class (class thực tế)** tương ứng với class đã tạo ra object đó.

Ví dụ:

~~~java
class Animal {
    void speak() {
        System.out.println("Animal sound");
    }
}

class Dog extends Animal {
    @Override
    void speak() {
        System.out.println("Woof");
    }

    void fetch() {
        System.out.println("Fetching");
    }
}

public class TypeExample {
    public static void main(String[] args) {
        Animal pet = new Dog();

        pet.speak();
        // pet.fetch(); // Compile-time error
    }
}
~~~

Biến pet có static type là Animal, nhưng object mà nó tham chiếu có runtime class là Dog.

- Compiler chỉ cho phép gọi những member có thể truy cập qua kiểu Animal. Vì vậy pet.fetch() không hợp lệ: Animal không khai báo fetch().
- Với method instance được override, JVM chọn implementation theo runtime class của object. Do đó pet.speak() chạy Dog.speak() và in Woof.

Đây là khác biệt giữa **overload resolution** và **dynamic dispatch**: overload được chọn lúc biên dịch dựa trên kiểu tĩnh; implementation của method đã chọn có thể được dispatch lúc chạy dựa trên object thực tế.

Muốn gọi hành vi riêng của Dog, cần kiểm tra hoặc cast:

~~~java
if (pet instanceof Dog dog) {
    dog.fetch();
}
~~~

Pattern variable dog chỉ được dùng trong phạm vi mà compiler xác định điều kiện instanceof đã thành công. Pattern matching cho instanceof đã là tính năng chính thức từ Java 16.

## 4. Kiểm tra phép gán và khả năng tương thích kiểu

Với phép gán, kiểu biểu thức bên phải phải có một phép chuyển đổi hợp lệ sang kiểu biến bên trái. Java gọi đây là **assignment conversion**.

### Gán cùng kiểu

~~~java
int count = 10;
int anotherCount = count;
~~~

Hai phía có cùng kiểu nên phép gán hợp lệ.

### Widening primitive conversion

Một số kiểu primitive nhỏ hơn có thể được chuyển sang kiểu rộng hơn mà không cần cast:

~~~java
int count = 10;
long total = count;
double average = total;
~~~

Các phép chuyển đổi như int sang long, long sang double và float sang double được gọi là widening primitive conversion. Tuy nhiên, widening không đảm bảo mọi giá trị đều được biểu diễn chính xác: long sang float có thể mất độ chính xác vì float có ít bit significand hơn.

### Narrowing primitive conversion

Chuyển từ kiểu rộng sang kiểu hẹp thường cần cast tường minh:

~~~java
double price = 19.95;
int wholePrice = (int) price;

System.out.println(wholePrice);
~~~

Output:

~~~text
19
~~~

Phần thập phân bị bỏ. Cast chỉ yêu cầu compiler cho phép phép chuyển đổi; nó không bảo đảm dữ liệu được giữ nguyên.

### Hằng số số nguyên có thể được thu hẹp trong một số phép gán

Java cho phép một constant expression kiểu int được gán vào byte, short hoặc char nếu giá trị nằm trong miền biểu diễn của kiểu đích:

~~~java
byte first = 10;
byte second = 1 + 2;
~~~

Nhưng ví dụ sau không hợp lệ:

~~~java
byte first = 10;
byte second = first + 1; // Compile-time error
~~~

Biểu thức first + 1 có kiểu int do binary numeric promotion. Biến first không phải constant variable nên compiler không thể áp dụng ngoại lệ thu hẹp cho constant expression. Có thể viết:

~~~java
byte second = (byte) (first + 1);
~~~

Hoặc dùng compound assignment:

~~~java
first += 1;
~~~

Phép gán kết hợp có quy tắc chuyển đổi ngầm về kiểu bên trái. Điều này tiện lợi nhưng vẫn có thể làm mất dữ liệu nếu phép toán vượt miền biểu diễn của byte.

### Widening và narrowing reference conversion

Nếu Dog extends Animal, có thể gán Dog cho Animal:

~~~java
Dog dog = new Dog();
Animal animal = dog;
~~~

Đây là widening reference conversion, thường an toàn vì mọi Dog đều là Animal.

Chiều ngược lại cần kiểm tra:

~~~java
Animal animal = new Dog();
Dog dog = (Dog) animal;
~~~

Phép cast có thể thành công khi object thực tế là Dog. Nếu object thực tế là một loại Animal khác, JVM ném ClassCastException.

## 5. Boxing, unboxing và null

Java có thể chuyển đổi giữa primitive type và wrapper type:

| Primitive | Wrapper |
|---|---|
| boolean | Boolean |
| byte | Byte |
| short | Short |
| char | Character |
| int | Integer |
| long | Long |
| float | Float |
| double | Double |

**Boxing** chuyển primitive thành wrapper:

~~~java
int count = 5;
Integer boxed = count;
~~~

**Unboxing** chuyển wrapper thành primitive:

~~~java
Integer boxed = 5;
int count = boxed;
~~~

Compiler tự chèn các phép chuyển đổi này trong những context được Java cho phép. Chúng có thể tiện lợi, nhưng không phải lúc nào cũng miễn phí về hiệu năng hoặc không có rủi ro.

Ví dụ:

~~~java
Integer value = null;
int count = value;
~~~

Code trên biên dịch được nhưng gây NullPointerException khi unboxing vì null không thể trở thành giá trị int. Khi dùng wrapper có thể null, hãy kiểm tra null trước khi chuyển sang primitive.

## 6. Kiểm tra kiểu khi gọi method và constructor

Compiler phải xác định đối số có phù hợp với kiểu tham số hay không. Việc này được gọi là **invocation conversion**.

Ví dụ:

~~~java
static void printLength(String text) {
    System.out.println(text.length());
}

printLength("Java"); // Hợp lệ
printLength(123);    // Compile-time error
~~~

Một đối số có thể được chuyển đổi trong các context được cho phép, ví dụ widening primitive, widening reference, boxing hoặc unboxing. Không phải mọi phép chuyển đổi đều tự động được chấp nhận trong mọi vị trí.

### Overload resolution

Nếu có nhiều method cùng tên, compiler chọn overload phù hợp nhất dựa trên kiểu tĩnh của đối số và các quy tắc overload resolution.

~~~java
public class OverloadDemo {
    static void show(Object value) {
        System.out.println("Object overload");
    }

    static void show(String value) {
        System.out.println("String overload");
    }

    public static void main(String[] args) {
        show("Java");
    }
}
~~~

Output:

~~~text
String overload
~~~

String là kiểu cụ thể hơn Object trong trường hợp này, nên overload nhận String được chọn.

### Overload có thể bị ambiguous

~~~java
static void show(String value) { }
static void show(Integer value) { }

show(null); // Compile-time error: ambiguous
~~~

null có thể gán cho cả String và Integer. Hai kiểu này không phải subtype của nhau nên compiler không có một overload cụ thể hơn để chọn.

Nếu khai báo thêm overload nhận Object, lời gọi show(null) vẫn chọn overload String hoặc Integer? Không có overload nào cụ thể hơn overload còn lại; Object kém cụ thể hơn cả hai nên không giải quyết được sự mơ hồ.

Có thể làm rõ ý định bằng cast:

~~~java
show((String) null);
~~~

### Overload khác override

- **Overload:** cùng tên method nhưng khác danh sách tham số. Compiler quyết định method signature nào được gọi dựa trên static type.
- **Override:** subclass thay implementation của method kế thừa. Với method instance, JVM dispatch đến implementation phù hợp theo runtime class.

Ví dụ:

~~~java
class Parent {
    void display(Object value) {
        System.out.println("Parent Object");
    }
}

class Child extends Parent {
    @Override
    void display(Object value) {
        System.out.println("Child Object");
    }

    void display(String value) {
        System.out.println("Child String");
    }
}

Parent ref = new Child();
ref.display("Java");
~~~

Output:

~~~text
Child Object
~~~

Compiler nhìn static type Parent, nên chỉ có overload display(Object) phù hợp để chọn. Sau đó JVM gọi implementation đã override trong Child. Overload display(String) của Child không tham gia vì nó không có trong kiểu tĩnh Parent.

## 7. Generic type checking

Generics giúp compiler kiểm tra kiểu phần tử của collection và các class/method tổng quát ngay khi biên dịch.

~~~java
List<String> names = new ArrayList<>();
names.add("An");
names.add("Binh");

String first = names.get(0);
~~~

Compiler biết names chỉ nhận String và get(0) trả về String. Lệnh sau bị từ chối:

~~~java
names.add(100); // Compile-time error
~~~

Nếu dùng raw type:

~~~java
List raw = new ArrayList();
raw.add("Java");
raw.add(100);

List<String> names = raw; // Unchecked conversion warning
String value = names.get(1); // Có thể ném ClassCastException
~~~

Raw type làm suy yếu kiểm tra generic. Compiler phát cảnh báo unchecked vì không thể chứng minh dữ liệu trong collection đúng kiểu String. Khi đọc phần tử Integer rồi ép về String, lỗi có thể xảy ra lúc chạy.

### Generic invariant

List<String> không phải subtype của List<Object>, dù String là subtype của Object:

~~~java
List<String> strings = new ArrayList<>();
List<Object> objects = strings; // Compile-time error
~~~

Nếu phép gán trên được cho phép, code có thể thêm một Integer vào danh sách vốn được khai báo là List<String>. Sau đó code khác đọc phần tử và kỳ vọng String sẽ gặp lỗi.

Để biểu diễn một collection có thể chứa các subtype của Number, dùng wildcard:

~~~java
List<? extends Number> values;
~~~

Đây là kiểu producer: có thể đọc phần tử dưới dạng Number, nhưng không thể thêm một Number tùy ý vì compiler không biết chính xác subtype nào đang được giữ.

Với:

~~~java
List<? super Integer> values;
~~~

Đây là kiểu consumer: có thể thêm Integer, nhưng khi đọc một phần tử, kiểu an toàn chung chỉ là Object.

Quy tắc ghi nhớ thường dùng là PECS: Producer Extends, Consumer Super. Đây là mẹo thiết kế API generic, không thay thế các quy tắc kiểu đầy đủ.

### Type erasure

Java thực hiện generics bằng type erasure: phần lớn thông tin tham số kiểu không tồn tại như một kiểu runtime riêng biệt sau khi biên dịch. Compiler kiểm tra generic tại compile time và chèn cast cần thiết vào bytecode.

Vì vậy, không thể viết:

~~~java
if (value instanceof List<String>) {
    // Compile-time error
}
~~~

JVM không thể kiểm tra trực tiếp tham số String của List ở runtime. Có thể kiểm tra:

~~~java
if (value instanceof List<?>) {
    // Kiểm tra object có phải một List hay không
}
~~~

Nếu cần bảo vệ kiểu phần tử, phải kiểm tra từng phần tử hoặc dùng một cơ chế dữ liệu có schema phù hợp.

## 8. Type inference và target typing

Compiler có thể tự suy luận kiểu trong một số context thay vì yêu cầu người lập trình viết đầy đủ type argument.

### Suy luận kiểu generic method

~~~java
static <T> T identity(T value) {
    return value;
}

String name = identity("An");
Integer count = identity(10);
~~~

Từ đối số và context sử dụng, compiler suy luận T lần lượt là String và Integer.

Có thể chỉ rõ type argument:

~~~java
String name = TypeInferenceDemo.<String>identity("An");
~~~

Thông thường không cần viết tường minh nếu compiler có đủ thông tin.

### Diamond operator

~~~java
List<String> names = new ArrayList<>();
~~~

Compiler suy luận type argument của ArrayList từ kiểu đích List<String>. Đây là một ví dụ target typing.

### Lambda expression cần target type

~~~java
Runnable task = () -> System.out.println("Running");
~~~

Lambda không tự đứng độc lập như một object có kiểu tùy ý. Compiler cần target type là một functional interface, ở đây là Runnable, để kiểm tra tham số và kiểu trả về của lambda.

Ví dụ sau không có đủ target type:

~~~java
var task = () -> System.out.println("Running"); // Compile-time error
~~~

Không thể dùng var để suy luận kiểu của lambda nếu không có target functional interface. Hãy viết:

~~~java
Runnable task = () -> System.out.println("Running");
~~~

Type inference làm code gọn hơn, nhưng compiler vẫn xác định một kiểu tĩnh cụ thể; Java không biến thành ngôn ngữ dynamic typing.

## 9. Cast, instanceof và kiểm tra ở runtime

Cast tường minh yêu cầu compiler xem xét một phép chuyển đổi mà phép gán thông thường không cho phép. Với reference type, một số cast cần kiểm tra object thực tế ở runtime.

~~~java
Object value = "Java";
String text = (String) value;
~~~

Phép cast hợp lệ và thành công vì object thực tế là String.

~~~java
Object value = 123;
String text = (String) value;
~~~

Ví dụ này biên dịch được vì compiler không thể loại trừ khả năng value chứa String, nhưng khi chạy sẽ ném ClassCastException vì object thực tế là Integer.

Dùng instanceof để kiểm tra trước khi cast:

~~~java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
} else {
    System.out.println("Not a String");
}
~~~

Với reference type, instanceof trả về false khi value là null. Pattern variable text chỉ được đưa vào scope ở nhánh mà kiểm tra thành công.

Không nên dùng cast để che lỗi thiết kế kiểu. Nếu một API thường xuyên cần nhiều cast, hãy cân nhắc dùng interface, generic type hoặc mô hình dữ liệu rõ ràng hơn.

## 10. Kiểu của biểu thức và target typing

Kiểu của một biểu thức không phải lúc nào cũng được quyết định chỉ từ các toán hạng của nó. Trong một số trường hợp, **target type** từ context xung quanh góp phần xác định kiểu biểu thức. Các biểu thức chịu ảnh hưởng như vậy được gọi là poly expressions.

Ví dụ:

~~~java
List<String> names = new ArrayList<>();
~~~

Kiểu đích List<String> giúp compiler suy luận type argument của biểu thức new ArrayList<>().

Với conditional expression:

~~~java
String result = condition ? "yes" : "no";
~~~

Hai nhánh đều là String nên biểu thức có kiểu String.

Với lambda hoặc method reference, target functional interface quyết định kiểu tham số và kiểu kết quả được kiểm tra. Đây là lý do một lambda có thể phù hợp với một context nhưng không hợp lệ khi đứng độc lập.

Khi gặp lỗi type inference hoặc incompatible types trong biểu thức phức hợp, hãy tách biểu thức thành biến có kiểu tường minh để làm rõ target type và thu hẹp vị trí lỗi.

## 11. Compile-time error, warning và runtime exception

| Loại | Ví dụ | Khi phát hiện |
|---|---|---|
| Syntax error | Thiếu dấu ngoặc hoặc dấu chấm phẩy | Parsing |
| Type error | Gán String cho int, gọi method không tồn tại | Compile time |
| Unchecked warning | Raw type, unchecked cast/conversion | Compile time |
| ClassCastException | Cast object thực tế không tương thích | Runtime |
| NullPointerException | Dereference hoặc unbox null | Runtime |
| ArrayStoreException | Gán object sai runtime component type vào covariant array | Runtime |

Cần xử lý warning unchecked một cách nghiêm túc. Warning cho biết compiler không thể xác minh đầy đủ an toàn kiểu. Thêm @SuppressWarnings("unchecked") chỉ ẩn thông báo; nó không tự làm phép cast hoặc collection trở nên an toàn.

## 12. Đọc và cải thiện diagnostic của javac

Giả sử file TypeError.java:

~~~java
public class TypeError {
    public static void main(String[] args) {
        int count = "five";
    }
}
~~~

Biên dịch:

~~~bash
javac TypeError.java
~~~

Compiler báo lỗi vì không thể chuyển String sang int. Nội dung diagnostic có thể khác nhau theo phiên bản JDK, nhưng bản chất lỗi không đổi.

Một số tùy chọn hữu ích:

| Tùy chọn | Tác dụng |
|---|---|
| -Xlint:all | Bật nhiều nhóm cảnh báo của compiler |
| -Xlint:unchecked | Hiển thị cảnh báo liên quan đến generic/unchecked conversion |
| -Xdiags:verbose | Yêu cầu diagnostic chi tiết hơn |
| -Werror | Chuyển warning thành lỗi biên dịch |
| --release 17 | Biên dịch theo ngôn ngữ, API và bytecode của Java 17 |

Ví dụ kiểm tra một chương trình theo Java 17:

~~~bash
javac --release 17 -Xlint:all -Xdiags:verbose -d out TypeCheckingDemo.java
~~~

Nếu dự án muốn build thất bại khi xuất hiện warning:

~~~bash
javac --release 17 -Xlint:all -Werror -d out TypeCheckingDemo.java
~~~

Không nên bật -Werror cho một codebase cũ mà chưa rà soát warning trước, vì có thể làm build hiện tại thất bại do cảnh báo tồn tại từ trước. Trong dự án mới, kiểm soát warning từ đầu giúp giữ chất lượng type safety tốt hơn.

## 13. Ví dụ tổng hợp có thể chạy

Tạo file TypeCheckingDemo.java:

~~~java
public class TypeCheckingDemo {
    static <T> T identity(T value) {
        return value;
    }

    static void select(Object value) {
        System.out.println("Object overload");
    }

    static void select(String value) {
        System.out.println("String overload: " + value);
    }

    private static final class User {
        private final String name;

        User(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        int count = 7;
        long total = count;

        Integer boxed = count;
        int unboxed = boxed;

        System.out.println("widened=" + total);
        System.out.println("boxed=" + boxed + ", unboxed=" + unboxed);

        select("Java");

        Object candidate = new User("Mina");
        if (candidate instanceof User user) {
            System.out.println("user=" + user.name());
        }

        String text = identity("Java");
        System.out.println("inferred=" + text);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all -d out TypeCheckingDemo.java
java -cp out TypeCheckingDemo
~~~

Output chính xác:

~~~text
widened=7
boxed=7, unboxed=7
String overload: Java
user=Mina
inferred=Java
~~~

Trong ví dụ này:

- int được widening sang long.
- int được boxing thành Integer rồi unboxing về int.
- Compiler chọn overload nhận String.
- Biến candidate có static type Object, còn object thực tế là User; instanceof kiểm tra runtime class và tạo pattern variable user.
- Generic method identity suy luận T là String từ đối số và target type.

## 14. Quy trình xử lý một lỗi type checking

Khi javac báo lỗi kiểu dữ liệu:

1. Đọc dòng và cột được báo, nhưng kiểm tra cả biểu thức xung quanh vì lỗi có thể bắt nguồn từ một lời gọi method trước đó.
2. Ghi ra static type của từng biến và biểu thức liên quan.
3. Xác định context: assignment, method invocation, return, cast, numeric operation hay lambda target typing.
4. Kiểm tra phép chuyển đổi có được Java cho phép trong context đó không.
5. Với overload, liệt kê các candidate method và kiểu tham số của chúng; xác định vì sao candidate không applicable hoặc vì sao có nhiều candidate cùng phù hợp.
6. Với generic, kiểm tra type argument, wildcard, raw type và constraint mà compiler phải suy luận.
7. Với lỗi runtime như ClassCastException hoặc NullPointerException, kiểm tra runtime class/value và không nhầm chúng với compile-time type error.
8. Sửa nguyên nhân ở kiểu khai báo, API hoặc dữ liệu; chỉ dùng cast khi đã có lý do bảo đảm kiểu thực tế.

Một kỹ thuật hữu ích là tạo biến trung gian có kiểu rõ ràng:

~~~java
var result = complicatedExpression();
~~~

Có thể tạm thay bằng:

~~~java
String result = complicatedExpression();
~~~

Nếu compiler báo lỗi ở phép gán, bạn đã xác định được kiểu đích mong muốn và có thể lần ngược về biểu thức tạo ra kiểu không phù hợp.

## 15. Checklist type safety

- [ ] Biến và biểu thức có kiểu tĩnh phù hợp với mục đích sử dụng.
- [ ] Phép gán chỉ dùng conversion hợp lệ.
- [ ] Không cast primitive hoặc reference một cách tùy tiện.
- [ ] Đã kiểm tra null trước khi dereference hoặc unboxing khi cần.
- [ ] Overload được chọn theo static type như dự kiến.
- [ ] Phân biệt overload resolution với runtime method dispatch.
- [ ] Dùng generic thay vì raw type khi có thể.
- [ ] Xử lý unchecked warning thay vì chỉ suppress.
- [ ] Lambda và method reference có target functional interface rõ ràng.
- [ ] Cast runtime được bảo vệ bằng instanceof khi phù hợp.
- [ ] Compiler được chạy với đúng --release hoặc toolchain của dự án.
- [ ] Đã đọc diagnostic đầy đủ và sửa nguyên nhân gốc.

## 16. Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 26 — Chapter 4: Types, Values, and Variables](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html) — kiểu primitive/reference, subtype, generic, erasure và type usage.
- [Java Language Specification, Java SE 26 — Chapter 5: Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html) — widening/narrowing, assignment, invocation, casting, boxing/unboxing và target typing.
- [Java Language Specification, Java SE 26 — §15.12: Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.12) — overload resolution và method invocation.
- [Java Language Specification, Java SE 26 — Chapter 18: Type Inference](https://docs.oracle.com/javase/specs/jls/se26/html/jls-18.html) — suy luận kiểu generic và các constraint.
- [javac — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — tùy chọn compiler, lint và release target.

Type checking là một lớp bảo vệ quan trọng của Java: nó phát hiện nhiều lỗi trước khi chương trình chạy, đồng thời giúp API và code thể hiện rõ kiểu dữ liệu mong đợi. Khi hiểu static type, conversion context và overload resolution, bạn có thể đọc diagnostic nhanh hơn và thiết kế code an toàn hơn.
