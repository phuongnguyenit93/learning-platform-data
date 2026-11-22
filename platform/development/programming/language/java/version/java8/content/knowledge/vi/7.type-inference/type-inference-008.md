# Phân biệt kiểu được suy luận với kiểu động trong Java

**Suy luận kiểu (*type inference*) không phải là kiểu động (*dynamic typing*).** Trong Java, trình biên dịch có thể xác định kiểu của một biểu thức, đối số generic, tham số lambda hoặc biến cục bộ từ ngữ cảnh mà lập trình viên không cần viết đầy đủ tên kiểu. **Sau khi suy luận, kiểu được xác định ở thời điểm biên dịch và vẫn được kiểm tra theo hệ thống kiểu tĩnh của Java.**

Một đối tượng Java cũng có **lớp thực tế ở runtime**. Khi một biến kiểu `Animal` đang tham chiếu đối tượng `Dog`, Java có thể thực thi phương thức override của `Dog` nhờ **dynamic method dispatch**. Điều này **không có nghĩa** biến `Animal` chuyển thành biến có kiểu động, hay Java bỏ kiểm tra kiểu khi biên dịch.

Để không nhầm, hãy tách ba khái niệm:

1. **Kiểu tĩnh (*compile-time/static type*)**: trình biên dịch dùng để kiểm tra phép gán, phương thức có thể gọi, overload, generic, biểu thức lambda và method reference.
2. **Kiểu được suy luận (*inferred type*)**: một kiểu tĩnh được compiler **suy ra** từ dữ liệu/ngữ cảnh thay vì được viết trực tiếp tại chỗ.
3. **Lớp runtime và dispatch động**: JVM biết đối tượng thật là instance của class nào, và có thể chọn implementation của phương thức instance override phù hợp khi chương trình chạy.

Bài này thuộc chủ đề **Suy luận kiểu** trong Java 8, nhưng cũng giải thích `var` (Java 10+) và pattern matching `instanceof` (Java 16+) vì hai cú pháp mới dễ bị hiểu nhầm thành “Java đã có biến kiểu động”. Nội dung đều là quy tắc còn được sử dụng trong Java hiện đại; ví dụ đầy đủ biên dịch bằng **JDK 17+**.

## 1. Bảng phân biệt nhanh

| Câu hỏi | Suy luận kiểu | Kiểu động thực sự | Kiểu/lớp runtime của object trong Java |
| --- | --- | --- | --- |
| Khi nào biết kiểu của biến? | **Compiler** suy ra kiểu tĩnh trong quá trình biên dịch | Tùy ngôn ngữ: phép gán/gọi có thể dựa nhiều vào kiểu giá trị lúc chạy | JVM biết class của object được tạo |
| Có thể gán biến đang là `String` sang `int` tùy ý? | Không, nếu biến đã có kiểu `String` | Có thể ở một số ngôn ngữ kiểu động, tùy quy tắc của chúng | Biến Java vẫn phải tuân thủ kiểu khai báo/tĩnh |
| Lời gọi method được kiểm tra trước khi chạy? | Có, dựa trên kiểu tĩnh và các quy tắc Java | Có thể để lại nhiều kiểm tra cho runtime | JVM chọn implementation override của method đã hợp lệ về mặt tĩnh |
| `var` trong Java có phải kiểu động? | **Không**. `var` cho compiler suy ra kiểu tĩnh | Không áp dụng | Object được tham chiếu vẫn có runtime class |
| Có thể đổi object `Dog` sang `Cat` trong biến `Animal`? | Có, vì cả hai phù hợp kiểu tĩnh `Animal` | Không chứng minh biến có kiểu động | Runtime class của object tham chiếu thay đổi, **kiểu biến không đổi** |
| Generic `List<String>` còn thông tin `String` trong `getClass()`? | Compiler kiểm tra type argument | Không áp dụng | Vì **type erasure**, `getClass()` của `ArrayList<String>` và `ArrayList<Integer>` cùng là `ArrayList` |
| Gọi overload hay override dựa vào đâu? | Overload resolution chủ yếu dựa trên thông tin biên dịch | Tùy ngôn ngữ | Java dispatch method instance override ở runtime trong phạm vi method signature đã chọn |

Ví dụ ngắn nhất:

~~~java
var title = "Java";  // Java 10+: compiler suy ra String
title = "Modern";    // Hợp lệ
// title = 123;      // SAI: int không gán được cho String
~~~

`title` **không “mang kiểu gì cũng được”**. Nó là biến kiểu `String`, chỉ có cú pháp khai báo ngắn hơn `String title = "Java";`.

## 2. Java là ngôn ngữ kiểm tra kiểu tĩnh

Java gán kiểu cho các biểu thức và biến theo quy tắc ngôn ngữ trước khi chương trình chạy. Compiler quyết định các thao tác nào có thể viết tại một vị trí dựa trên **kiểu tĩnh có thể biết được**.

~~~java
String name = "Lan";
int length = name.length(); // Compiler biết String có length()
~~~

Nếu thay bằng:

~~~java
Object value = "Lan";
// int length = value.length(); // SAI khi biên dịch
~~~

thì phương thức `length()` không xuất hiện trong API của `Object`, mặc dù object thật ở runtime là một `String`. Có thể truy cập sau khi chứng minh/chuyển kiểu hợp lệ:

~~~java
Object value = "Lan";
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

**Pattern matching cho `instanceof`** theo dạng `instanceof String text` trở thành tính năng chính thức ở Java 16. Trong Java 8, dùng `if (value instanceof String) { String text = (String) value; ... }`.

Việc phải kiểm tra và narrowing type này là bằng chứng ngược với ý tưởng “Java tự chuyển biến sang kiểu động khi thấy object”. Compiler vẫn không cho gọi những phương thức bên ngoài **kiểu tĩnh hiện tại**, trừ khi có cơ chế chuyển/kiểm tra kiểu được phép.

### `Object` không đồng nghĩa kiểu động

`Object` là kiểu tham chiếu gốc của các lớp Java, không phải “kiểu tắt kiểm tra”. Một biến `Object` có thể chứa tham chiếu đến nhiều loại object phù hợp, nhưng compiler chỉ cho sử dụng các method thuộc API có thể truy cập của `Object`:

~~~java
Object item = "hello";
System.out.println(item.toString());      // Hợp lệ
// System.out.println(item.substring(1)); // SAI khi biên dịch
~~~

Nếu biết chắc object là `String`, có thể kiểm tra `instanceof` hoặc cast; cast không tạo object mới và không đổi class runtime. Một cast sai có thể gây `ClassCastException` **khi chạy**.

## 3. Suy luận kiểu đã có trong Java 8, dù chưa có `var`

Suy luận kiểu không bắt đầu từ Java 10. Java 8 đã nâng cao cơ chế suy luận cho **generic methods**, **diamond operator**, **lambda expressions**, **method references** và **target typing**.

### 3.1. Diamond operator `<>`

~~~java
List<String> names = new ArrayList<>();
names.add("Lan");
String first = names.get(0);
~~~

Phía trái cung cấp target `List<String>`, nên compiler có thể suy ra type argument `String` cho `new ArrayList<>()`. Đây là một ví dụ suy luận generic tại thời điểm biên dịch. Java **không cần xem object sau khi tạo rồi mới quyết định list chứa kiểu gì**.

Đoạn sai:

~~~java
List<String> names = new ArrayList<>();
// names.add(42); // SAI: Integer không tương thích String
~~~

Lỗi được phát hiện tại biên dịch. Runtime implementation của list là `ArrayList`, nhưng hợp đồng `List<String>` của biến vẫn buộc các phép thêm/đọc phải phù hợp.

**Đừng nhầm:** Java có diamond từ Java 7; Java 8 mở rộng khả năng suy luận trong nhiều ngữ cảnh khác. Điều quan trọng là các khả năng suy luận generic này vẫn đang được dùng.

### 3.2. Generic method tự suy ra type parameter

~~~java
static <T> T echo(T value) {
    return value;
}
~~~

Đây là **khai báo method** đặt trong lớp, không phải chương trình độc lập. Với:

~~~java
String result = echo("hello");
Integer number = echo(42);
~~~

compiler suy ra type argument tương ứng từ thông tin lời gọi/ngữ cảnh. Trong ví dụ thứ hai, `42` được boxing thành `Integer` để phù hợp tham số kiểu generic `T`, vốn yêu cầu kiểu tham chiếu.

Khi triển khai JDK 17:

~~~java
String upper = echo("hello").toUpperCase(Locale.ROOT);
~~~

`upper` là `"HELLO"`. Compiler biết kết quả lời gọi phù hợp kiểu `String` trong ngữ cảnh đó nên cho gọi `toUpperCase`. Đây là **kiểu tĩnh được suy luận**; không có việc mỗi lần chạy hệ thống lại quyết định `upper` được phép gọi những method nào.

Ở những biểu thức generic phức tạp, Java giải các ràng buộc kiểu và target type chứ không phải luôn “nhìn vào vế phải một lần”. Nếu suy luận không đủ hoặc cần điều khiển kết quả, có thể ghi type witness: `ClassName.<String>echo("hello")`.

### 3.3. Suy luận cho lambda và method reference

~~~java
Function<String, Integer> length = String::length;
Predicate<String> longerThan3 = s -> s.length() > 3;
~~~

Đây là các khai báo trong một phương thức; cần import `java.util.function.*`. Kiểu tĩnh của `length` là `Function<String,Integer>`; kiểu đối số của `s` được suy ra là `String` từ hợp đồng `Predicate<String>.test(String)`.

`String::length` trả `int`, nhưng `Function<String,Integer>` cần wrapper `Integer`; compiler áp dụng boxing khi phù hợp. Dạng `ToIntFunction<String> length = String::length;` có thể giữ kết quả primitive.

Không thể tự tạo một lambda “không kiểu đích” rồi mong Java coi nó là giá trị kiểu động:

~~~java
// SAI: thiếu target functional interface
// var fn = s -> s.length();
// var ref = String::length;
~~~

Cả lambda và method reference là **poly expressions**: cần target type đủ thông tin. Chúng không tự suy ra một “function object” với các tham số có kiểu tùy biến ở runtime.

### 3.4. Target typing và generic result

~~~java
List<String> empty = Collections.emptyList();
~~~

`Collections.emptyList()` là generic method; ngữ cảnh `List<String>` góp phần xác định type argument. Cùng một phương thức có thể được dùng tại chỗ khác với target `List<Integer>`. Không có chuyện các phần tử đang được chứa trong một list rỗng quyết định kiểu lúc runtime.

Lưu ý không phải mọi biểu thức đều là poly expression. Với một số lời gọi/điều kiện hoặc overload, cách suy luận khác nhau theo quy tắc chi tiết của JLS. Hãy hiểu nguyên tắc: **target type có thể giúp compiler suy luận**, nhưng điều này vẫn hoàn toàn là cơ chế biên dịch.

## 4. `var` (Java 10+) là suy luận kiểu cục bộ, không phải dynamic typing

Từ **Java 10**, có thể viết:

~~~java
var message = "Java";
var total = 42;
var people = new ArrayList<String>();
~~~

Compiler suy ra kiểu tĩnh:

~~~java
String message = "Java";
int total = 42;
ArrayList<String> people = new ArrayList<String>();
~~~

Hai đoạn minh họa các kiểu **tương ứng**, không được dùng cùng lúc trong một block vì trùng tên biến. Cả hai cách đều được kiểm tra kiểu như nhau. Cụ thể:

- `message` vẫn là `String` trong toàn bộ phạm vi biến.
- `total` vẫn là primitive `int`.
- `people` có kiểu tĩnh **`ArrayList<String>`**, không mặc nhiên là interface `List<String>`.

### 4.1. Không được đổi kiểu qua lần gán kế tiếp

~~~java
var count = 10;
count = 20;      // ĐÚNG
// count = "20";  // SAI: String không gán được int
~~~

**Kiểu được suy luận một lần tại lúc khai báo**, chứ không thay đổi khi biến nhận giá trị mới.

Ngược lại:

~~~java
Object value = "Lan";
value = Integer.valueOf(7); // ĐÚNG vì cả hai phù hợp Object
~~~

Kiểu tĩnh của `value` luôn là `Object`, không phải lần đầu `String` rồi về sau `Integer`. Việc nhận nhiều loại object là do **quan hệ subtyping**, không phải cơ chế kiểu động.

### 4.2. `var` không dùng ở mọi vị trí

`var` là **reserved type name**, không phải một kiểu dữ liệu hay từ khóa `dynamic`. Trong Java hiện đại, nó hỗ trợ các trường hợp như **local variables có initializer**, biến lặp `for`, biến phần tử trong enhanced `for`, và tài nguyên cục bộ được khai báo trong try-with-resources. Từ Java 11, còn có thể dùng `var` cho **tham số lambda viết tường minh**, đặc biệt để gắn annotation khi cần.

Không thể khai báo field hoặc method return type bằng `var`:

~~~java
// SAI: var không dùng làm kiểu field/method return
class Invalid {
    // var field = 1;
    // var getValue() { return 1; }
}
~~~

Không thể khai báo biến cục bộ có `var` mà thiếu initializer hoặc chỉ có `null`:

~~~java
// SAI: không có đủ thông tin để suy luận
// var x;
// var y = null;
~~~

Không thể suy ra kiểu lambda thuần từ `var` nếu không có target functional interface:

~~~java
// SAI
// var handler = x -> x.toString();

// ĐÚNG
Function<Object, String> handler = x -> x.toString();
~~~

Một `var` có thể dùng khi initializer **đã có kiểu functional interface rõ ràng**, ví dụ `var handler = (Function<Object,String>) (x -> x.toString());`. Đây vẫn là suy luận một kiểu tĩnh từ biểu thức có kiểu xác định.

### 4.3. Suy luận cụ thể quá mức có thể làm API khó bảo trì

~~~java
var list = new ArrayList<String>();
~~~

Ở đây `list` là `ArrayList<String>`. Nếu mục đích chỉ là “danh sách chuỗi”, bản viết:

~~~java
List<String> list = new ArrayList<>();
~~~

có thể rõ hơn vì công khai phụ thuộc vào **interface `List`** chứ không vào implementation cụ thể. Dùng `var` không luôn tốt hơn việc viết type tường minh; chọn dựa trên khả năng đọc và mức trừu tượng mong muốn.

Đặc biệt chú ý:

~~~java
var list = new ArrayList<>();
// Kiểu suy ra là ArrayList<Object> ở ngữ cảnh này.
~~~

Không nên giả định Java tự “chờ đến lúc add(String)” để suy ra `ArrayList<String>`. Nếu muốn danh sách chuỗi, viết `new ArrayList<String>()` hoặc ghi target type bên trái là `List<String>`. Java không dùng các lệnh `add` tương lai để sửa lại kết quả suy luận đã hoàn tất.

## 5. Kiểu tĩnh của biến khác với class thực tế ở runtime

Xét:

~~~java
abstract class Animal {
    abstract String sound();
}

final class Dog extends Animal {
    @Override String sound() { return "woof"; }
}

final class Cat extends Animal {
    @Override String sound() { return "meow"; }
}
~~~

Đây là các **khai báo kiểu minh họa**. Trong một phương thức:

~~~java
Animal pet = new Dog();
System.out.println(pet.sound()); // "woof"
pet = new Cat();
System.out.println(pet.sound()); // "meow"
~~~

**Điều không thay đổi:** kiểu tĩnh của biến `pet` vẫn là `Animal`. Compiler cho gọi `sound()` vì `Animal` đã khai báo method đó.

**Điều thay đổi:** object được `pet` tham chiếu: lần đầu `Dog`, lần sau `Cat`. JVM dùng cơ chế **dynamic method dispatch** để chọn implementation override tương ứng khi lời gọi `pet.sound()` thực hiện.

Nếu `Dog` có method riêng `fetch()`, không thể viết `pet.fetch()` chỉ vì dòng trước đó `pet = new Dog()`:

~~~java
Animal pet = new Dog();
// pet.fetch(); // SAI tại biên dịch: Animal không khai báo fetch()
~~~

Sau khi kiểm tra kiểu phù hợp hoặc dùng interface API rộng hơn, mới gọi được method chuyên biệt. Đây là **đa hình và kiểm tra kiểu tĩnh phối hợp**, không phải Java trở thành ngôn ngữ kiểu động.

### Một biến được `var` suy luận từ `new Dog()` có giống `Animal pet` không?

~~~java
var dog = new Dog(); // kiểu tĩnh Dog
Animal pet = new Dog(); // kiểu tĩnh Animal
~~~

Cả hai ban đầu tham chiếu object `Dog`, nhưng **kiểu tĩnh khác nhau**. Với `dog`, compiler biết các method public/package-accessible tương ứng của `Dog`; với `pet`, compiler chỉ dựa trên `Animal` và các kiểu liên quan. `var` không có nhiệm vụ tự chọn interface hay superclass “nên dùng” về mặt thiết kế; nó suy ra kiểu theo initializer và luật ngôn ngữ.

### `getClass()` phản ánh class thực tế, không phản ánh kiểu tĩnh của biến

~~~java
Animal pet = new Dog();
System.out.println(pet.getClass().getSimpleName()); // Dog
~~~

`getClass()` trả thông tin class của **object hiện tại**. Nó không “trả về” tên kiểu khai báo `Animal`. Đổi object thành `Cat` thì kết quả thành `Cat`, nhưng compiler vẫn biết `pet` là `Animal`.

Giới hạn quan trọng:

- Nếu biến là `null`, không có object để hỏi class; `pet.getClass()` gây `NullPointerException`.
- Primitive `int`, `boolean`... không phải object và không gọi `getClass()` trực tiếp.
- Object runtime class có thể là subclass, anonymous class, proxy... tùy cách tạo; kết quả `getClass()` không dùng để suy ra mọi ràng buộc generic đã được compiler kiểm tra.

## 6. Cùng runtime object, overload khác nhau vì kiểu tĩnh

Java có hai cơ chế rất khác:

**Overloading (nhiều method cùng tên nhưng khác tham số)**: compiler chọn method signature phù hợp dựa trên thông tin kiểu tại vị trí gọi, khả năng áp dụng và các quy tắc chọn method cụ thể nhất. Không tự dùng runtime class của đối số để chọn overload khác.

**Overriding (lớp con cài lại instance method)**: sau khi compiler xác định method hợp lệ, JVM có thể chọn implementation override theo runtime class của receiver.

Ví dụ:

~~~java
static void describe(Object value) {
    System.out.println("overload=Object");
}

static void describe(String value) {
    System.out.println("overload=String");
}
~~~

Đây là **hai static methods** đặt trong một lớp. Khi gọi:

~~~java
Object value = "hello";
describe(value);           // overload=Object
describe((String) value);  // overload=String
~~~

Trong cả hai lời gọi, object thật là cùng một `String`. Nhưng ở lời gọi thứ nhất **kiểu tĩnh của biểu thức đối số là `Object`**, nên compiler chọn `describe(Object)`. Ở lời gọi thứ hai, cast làm kiểu tĩnh của biểu thức là `String`, nên chọn `describe(String)`. Đây không phải runtime dynamic overload selection.

Trong trường hợp có các instance methods được override, sau khi chữ ký được chọn, JVM mới áp dụng **virtual dispatch** để chọn implementation tương ứng theo receiver runtime. Đừng gộp hai quy tắc này thành “Java lúc nào cũng chọn hàm bằng runtime type”.

### Điều gì không phải virtual dispatch?

- `static` methods được **hiding** thay vì override theo cơ chế instance virtual dispatch.
- Constructors không phải instance methods được override.
- Fields không tham gia polymorphic method dispatch theo cách của instance methods.
- `private` methods không được override như các instance methods kế thừa.
- Với `final` instance method, subclass không được override nên không có override implementation khác để chọn.

Vì thế, nói “Java có dispatch động” **không đồng nghĩa** mọi truy cập và mọi lời gọi đều được quyết định động.

## 7. Generic type inference không xóa bỏ kiểm tra kiểu

Java generics giúp biểu đạt quan hệ kiểu lúc biên dịch:

~~~java
List<String> names = new ArrayList<>();
names.add("Lan");
String first = names.get(0);
~~~

Compiler yêu cầu `names.add(...)` nhận `String` và biết `names.get(...)` trả `String` theo generic API. Khi chương trình được biên dịch, nhiều type arguments được xử lý theo cơ chế **type erasure**.

Ví dụ:

~~~java
List<String> strings = new ArrayList<>();
List<Integer> integers = new ArrayList<>();
boolean sameClass = strings.getClass() == integers.getClass(); // true
~~~

Ở runtime, hai object đều là `java.util.ArrayList`. `getClass()` không phân biệt `ArrayList<String>` và `ArrayList<Integer>`. Điều này **không có nghĩa** hai generic variables là “kiểu động”, cũng không làm `List<String>` được phép add `Integer` trong code type-safe.

### Tại sao `instanceof List<String>` không hợp lệ?

~~~java
Object unknown = new ArrayList<String>();
// if (unknown instanceof List<String>) { } // SAI: kiểm tra type argument không reifiable
if (unknown instanceof List<?>) {
    // Chỉ kiểm tra được nó là một List; không xác nhận element type String.
}
~~~

`List<?>` là một **reifiable type** trong ngữ cảnh `instanceof`; còn `List<String>` thông thường không thể kiểm tra trực tiếp type argument ở runtime do erasure. Không nên làm cast không kiểm tra rồi khẳng định rằng runtime đã xác thực mọi phần tử. Nếu dữ liệu bên ngoài không tin cậy, kiểm tra từng element hoặc parse/copy vào cấu trúc có hợp đồng rõ.

### Invariance của generic cũng là kiểm tra tĩnh

Ngay cả khi `Dog extends Animal`:

~~~java
List<Dog> dogs = new ArrayList<>();
// List<Animal> animals = dogs; // SAI: generics invariant
List<? extends Animal> animals = dogs; // ĐÚNG với tham chiếu đọc dữ liệu Animal
~~~

Đây là đoạn minh họa trong ngữ cảnh khai báo `Dog` và `Animal`. Với wildcard `? extends Animal`, ta có thể đọc element theo `Animal`; **không được tùy ý thêm một `Cat`** vào list có thể thực chất là `List<Dog>`. Đây là sự an toàn kiểu dựa trên thông tin lúc biên dịch, không dựa trên runtime guess.

## 8. Kiểu suy luận có thể phụ thuộc ngữ cảnh, không phải “đọc dữ liệu ở runtime”

Các biểu thức Java nhất định là *poly expressions*: ý nghĩa kiểu của chúng chịu ảnh hưởng bởi target type. Điều này đặc biệt quan trọng với lambda/method reference và generic methods.

~~~java
Function<String, Integer> toLength = String::length;
ToIntFunction<String> toPrimitiveLength = String::length;
~~~

Cùng một method reference `String::length` nhưng được đặt vào hai target functional interfaces:
- `Function<String,Integer>` nhận wrapper `Integer` sau boxing.
- `ToIntFunction<String>` nhận primitive `int`.

Với target `Consumer<String>`, compiler có thể cho bỏ giá trị trả về của method invocation tương thích `void`; vì thế:

~~~java
List<String> log = new ArrayList<>();
Consumer<String> append = log::add;       // List.add trả boolean, Consumer trả void
Function<String, Boolean> appendAndReport = log::add;
~~~

Cả hai có thể thêm phần tử, nhưng `append` không đưa boolean cho caller. **Target type khác nhau không làm `log` hay method `add` trở nên “động”**; chúng tạo hai hợp đồng callback được kiểm tra tại biên dịch.

Khi method overload nhận các functional interface khác nhau, các ràng buộc suy luận có thể phức tạp. Nếu compiler báo ambiguous hoặc kết quả suy luận không phù hợp ý định, khai báo biến trung gian có type tường minh thường rõ ràng hơn là chèn cast bừa bãi.

### Phép suy luận chưa chắc luôn chọn kiểu “cụ thể nhất bạn muốn”

~~~java
var items = new ArrayList<>(); // suy ra ArrayList<Object> trong trường hợp này
List<String> strings = new ArrayList<>(); // target làm rõ String
~~~

Code chạy có thể trông giống nhau trước khi add phần tử, nhưng **hợp đồng generic khác nhau**. Khi API cần kiểu rõ hoặc public boundary ổn định, viết kiểu tường minh giúp giảm khả năng refactor vô ý đổi signature.

## 9. Chương trình Java 17 chạy được: đối chiếu từng cơ chế

Chương trình sau chứng minh bằng stdout: diamond, `var`, kiểu runtime của object, dynamic dispatch, overload, suy luận generic/lambda và type erasure. Đồng thời dùng pattern matching cho `instanceof` theo Java 16+.

Lưu đúng tên **InferredVsRuntimeTypeDemo.java**:

~~~java
import java.util.*;
import java.util.function.*;

public class InferredVsRuntimeTypeDemo {
    abstract static class Animal {
        abstract String sound();
    }
    static final class Dog extends Animal {
        @Override String sound() { return "woof"; }
        String fetch() { return "ball"; }
    }
    static final class Cat extends Animal {
        @Override String sound() { return "meow"; }
    }

    static <T> T echo(T value) { return value; }
    static void describe(Object value) {
        System.out.println("overload=Object");
    }
    static void describe(String value) {
        System.out.println("overload=String");
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        String first = names.get(0);
        System.out.println("diamond=" + first);

        var text = "Java";
        text = "Modern";
        System.out.println("var=" + text);

        var precise = new ArrayList<String>();
        precise.add("An");
        System.out.println("precise=" + precise.get(0));

        Animal pet = new Dog();
        System.out.println("runtime=" + pet.getClass().getSimpleName()
                + ",sound=" + pet.sound());
        pet = new Cat();
        System.out.println("runtime=" + pet.getClass().getSimpleName()
                + ",sound=" + pet.sound());

        Object value = "hello";
        describe(value);
        describe((String) value);
        System.out.println("objectClass=" + value.getClass().getSimpleName());

        String upper = echo("hello").toUpperCase(Locale.ROOT);
        System.out.println("generic=" + upper);

        Function<String, Integer> length = String::length;
        Predicate<String> longerThan3 = s -> s.length() > 3;
        System.out.println("targetTyping=" + length.apply("Java")
                + "," + longerThan3.test("Java"));

        List<String> strings = new ArrayList<>();
        List<Integer> integers = new ArrayList<>();
        System.out.println("erasure=" + (strings.getClass() == integers.getClass()));

        Object unknown = new Dog();
        if (unknown instanceof Dog dog) {
            System.out.println("pattern=" + dog.fetch());
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 InferredVsRuntimeTypeDemo.java
java InferredVsRuntimeTypeDemo
~~~

Stdout chính xác đã được **biên dịch và kiểm chứng bằng thực thi**:

~~~text
diamond=Lan
var=Modern
precise=An
runtime=Dog,sound=woof
runtime=Cat,sound=meow
overload=Object
overload=String
objectClass=String
generic=HELLO
targetTyping=4,true
erasure=true
pattern=ball
~~~

### Đọc kết quả từng phần

1. **`diamond=Lan`**: `List<String> names = new ArrayList<>();` để compiler suy ra type argument `String`; phương thức `get(0)` có kiểu tĩnh trả `String`.
2. **`var=Modern`**: `var text = "Java"` suy ra `String`, nên gán tiếp một `String` khác được; gán số nguyên trực tiếp sẽ báo lỗi biên dịch.
3. **`precise=An`**: `var precise = new ArrayList<String>();` suy ra **`ArrayList<String>`**, không phải một biến dynamic generic.
4. **`runtime=Dog` và `runtime=Cat`**: kiểu tĩnh của `pet` luôn là `Animal`, trong khi class của object đang tham chiếu thay đổi. `sound()` chạy implementation override tương ứng.
5. **`overload=Object` rồi `overload=String`**: `describe(value)` chọn overload `Object` từ static type của biến. Cast sang `String` làm thay đổi static type của **biểu thức gọi** nên chọn overload `String`.
6. **`objectClass=String`**: object runtime thật là `String`, không phải type khai báo `Object` của biến.
7. **`generic=HELLO`**: generic method `echo` được compiler suy luận phù hợp kiểu `String`, nên kết quả dùng được `toUpperCase(Locale.ROOT)`.
8. **`targetTyping=4,true`**: method reference `String::length` được gõ theo `Function<String,Integer>` (boxing `int` thành `Integer`); lambda predicate nhận tham số `String` và trả boolean.
9. **`erasure=true`**: hai đối tượng `ArrayList` có type arguments khác nhau ở compile time nhưng có cùng `Class` runtime sau type erasure.
10. **`pattern=ball`**: pattern matching `instanceof Dog dog` kiểm tra và tạo biến pattern kiểu tĩnh `Dog` trong phạm vi kiểm tra đúng. Đây là **kiểm tra và narrowing type được compiler/JVM quy định**, không có biến động kiểu.

Các đoạn mã cố ý không biên dịch trong phần lý thuyết chỉ để phân tích lỗi, không đưa vào tệp runnable.

## 10. Những lỗi xảy ra ở compile time và runtime

Tĩnh/động đôi khi bị nhầm vì Java cũng có **runtime exceptions** liên quan kiểu. Điều này không làm Java thành ngôn ngữ có biến kiểu động.

| Tình huống | Khi nào phát hiện? | Vì sao |
| --- | --- | --- |
| `var x = "A"; x = 1;` | Compile time | Biến đã được suy ra là String |
| `Object x = "A"; x.length();` | Compile time | API của Object không có `length()` |
| `List<String> xs = new ArrayList<>(); xs.add(1);` | Compile time | Generic contract yêu cầu String |
| `var x = null;` | Compile time | Thiếu kiểu có thể suy luận từ initializer |
| `Function<String,Integer> fn = s -> s.trim();` | Compile time | Kết quả String không phù hợp Integer |
| `Object x = "A"; Integer n = (Integer) x;` | Runtime (`ClassCastException`) | Cast hợp lệ về mặt cú pháp/quan hệ kiểu rộng, nhưng object không phải Integer |
| `Object x = null; x.getClass();` | Runtime (`NullPointerException`) | Không có object để lấy class |
| `Animal a = new Dog(); a.sound();` | Cả hai giai đoạn | Compiler chấp nhận method trong Animal; runtime chọn Dog override |
| `Object x = "A"; describe(x);` với overload Object/String | Compile-time chọn signature | Runtime class String không tự thay đổi overload được gọi |

Ngoại lệ khi cast hoặc dereference không phải bằng chứng type checking bị “dời hết” về runtime. Java kết hợp nhiều bảo đảm tĩnh với những kiểm tra cần dữ liệu object thực tế, đúng như hợp đồng ngôn ngữ.

### Mất an toàn kiểu do raw types hoặc unchecked cast không phải suy luận kiểu

~~~java
List<String> strings = new ArrayList<>();
// Không nên dùng raw List để chèn Integer, hoặc cast unchecked để bỏ qua kiểm tra.
~~~

Java cho phép một số tương tác với legacy/raw APIs để duy trì tương thích, nhưng dùng raw types hoặc unchecked casts có thể làm xuất hiện lỗi runtime muộn. Trong code mới, ưu tiên generic types chính xác và kiểm tra dữ liệu ở ranh giới. **Không coi hiện tượng phát sinh lỗi khi chạy là “dynamic typing có chủ ý”**.

## 11. `instanceof`, reflection và runtime type information khác type inference

Khi chương trình chạy, có thể quan sát **class thực tế** của object và điều khiển luồng dựa trên nó:

~~~java
Object value = "hello";
if (value instanceof String text) {
    System.out.println(text.toUpperCase(Locale.ROOT));
}
~~~

Ở đây:
- `instanceof` thực hiện kiểm tra runtime phù hợp.
- Biến pattern `text` có **kiểu tĩnh `String`** trong phạm vi thích hợp sau khi kiểm tra đúng.
- `toUpperCase` vẫn được compiler xác nhận là method hợp lệ cho String.

**Reflection** (`Class<?>`, `java.lang.reflect.Method`, ...) có thể truy vấn metadata lớp và gọi method theo tên khi chạy, với những quy tắc truy cập và exception riêng. Điều đó là một API runtime đặc thù, **không biến các biến Java bình thường thành biến động kiểu** và không thay thế mọi kiểm tra của compiler.

Ví dụ `value.getClass()` chỉ trả class object; muốn biết generic type arguments, không thể tùy tiện suy ra từ `getClass()` sau erasure. Một số metadata kiểu khai báo có thể được reflection nhìn thấy trong signature/field/method, nhưng điều đó khác với việc biết nội dung generic của mọi instance collection.

### Khi thực sự cần hành vi theo subtype

Nếu có hierarchy ổn định và các kiểu con cùng triển khai một hợp đồng, dùng **polymorphic override** thường rõ hơn chuỗi dài `if (obj instanceof ...)`. Với mô hình dữ liệu cần phân nhánh theo nhiều biến thể, có thể xem xét sealed types hoặc pattern matching hiện đại khi phù hợp JDK mục tiêu, nhưng đó là **công cụ mô hình hóa kiểu và kiểm tra**, không phải suy luận kiểu động.

Tránh lạm dụng reflection chỉ để gọi những method vốn được định nghĩa trong interface chung: một hợp đồng kiểu tĩnh rõ ràng giúp code dễ bảo trì, dễ kiểm thử hơn.

## 12. Những nhầm lẫn thường gặp

| Nhận định sai | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “Có `var` thì Java là ngôn ngữ dynamic” | `var` chỉ bỏ phần viết type ở vị trí khai báo hỗ trợ | Compiler suy ra **kiểu tĩnh** |
| “`var` xuất hiện từ Java 8” | `var` local-variable inference là Java 10+ | Java 8 đã có generic/lambda inference nhưng chưa có `var` |
| “`var x = 1` rồi gán String cũng được” | Kiểu `x` được cố định `int` | Gán tiếp phải tương thích int |
| “`Object` là type động” | API được phép gọi vẫn theo Object | Chỉ object runtime có thể thuộc nhiều subclass |
| “`Animal pet = new Dog()` làm pet có type Dog” | Type biến vẫn Animal | Object runtime là Dog |
| “`getClass()` cho biết inferred type của biến” | Nó cho biết class object thật | Static type của biến không nằm trong kết quả đó |
| “Overload luôn chọn theo runtime class” | Overload resolution xảy ra ở biên dịch | Runtime override dispatch là khái niệm khác |
| “Một tên method có nhiều overload thì compiler tùy chọn khi chạy” | Java dùng quy tắc applicability/most-specific | Đọc kiểu tĩnh và chữ ký lời gọi |
| “`List<String>` và `List<Integer>` có runtime class khác nhau” | Type erasure với cùng implementation | `getClass()` đều là `ArrayList` ở ví dụ |
| “`instanceof List<String>` xác thực kiểu phần tử” | Non-reifiable type argument không thể kiểm tra trực tiếp | Dùng `List<?>` và kiểm tra dữ liệu khi cần |
| “`var list = new ArrayList<>()` chắc chắn tạo ArrayList<String> nếu sau đó add String” | Compiler không nhìn phép add tương lai để sửa type | Suy ra `ArrayList<Object>`, khai báo type mong muốn |
| “Lambda không cần target type” | Lambda là poly expression | Cần functional interface đủ thông tin |
| “Generic type inference phụ thuộc object runtime class” | Suy luận bằng ràng buộc lúc biên dịch | Runtime class không phải lời giải của suy luận |
| “Runtime ClassCastException nghĩa là Java không type-safe” | Những thao tác như downcast cần runtime check | Kiểm tra động bổ trợ cho hệ thống kiểu tĩnh |
| “Pattern variable `dog` là dynamic” | `instanceof Dog dog` gắn với kiểm tra và static type Dog | Không phải biến có kiểu tùy ý |
| “Kiểu tĩnh của field/method return có thể viết `var`” | `var` không phải kiểu dùng mọi nơi | Dùng khai báo type rõ theo API |
| “Method dispatch động có nghĩa fields/static methods cũng động” | Dynamic dispatch nói về instance method overriding | Static method hiding và field access theo quy tắc riêng |

## 13. Cách chọn cách viết trong dự án thực tế

**Đối với API công khai:** Ưu tiên khai báo kiểu tham số và return value rõ ràng. Nó cho thấy hợp đồng cho người gọi và giúp tránh phụ thuộc vô tình vào implementation cụ thể.

**Đối với local variables có initializer rõ:** `var` (Java 10+) có thể giảm lặp type mà vẫn giữ an toàn kiểu. Nhưng nếu initializer khó đọc hoặc kiểu suy ra quá cụ thể, dùng type tường minh:

~~~java
List<String> recipients = new ArrayList<>();
// thay vì chỉ thấy "var recipients = buildComplexExpression();"
~~~

**Đối với generic collections:** Dùng type arguments cụ thể và diamond khi có target. Tránh raw types và unchecked casts không cần thiết.

**Đối với callbacks:** Hãy chọn `Function`, `Predicate`, `Consumer`, `Supplier`... trước; compiler dùng target type để suy luận lambda/method reference. Nếu overload phức tạp, khai báo biến trung gian có type rõ ràng.

**Đối với hierarchy nhiều subtype:** Đưa hành vi chung vào interface/base class có method được override thay vì đoán class bằng chuỗi `getClass()==...`, trừ khi bài toán thật sự cần phân biệt chính xác runtime class.

**Đối với dữ liệu bên ngoài:** Không dựa vào type inference để xác thực JSON/HTTP/database payload. Đọc dữ liệu từ môi trường bên ngoài vẫn cần parsing, validation, kiểm soát null và error handling. Type inference chỉ hỗ trợ **compiler hiểu code Java của bạn**, không tự bảo đảm dữ liệu môi trường là hợp lệ.

### Checklist trước khi kết luận “đây là kiểu động”

1. Biến có **kiểu khai báo hoặc kiểu suy luận ở compile time** nào?
2. Đối tượng runtime hiện tại có class nào? Có thể đổi sang subclass khác **hợp lệ với kiểu biến** không?
3. Lời gọi đang xét là **overload** hay **override**?
4. Nếu viết `var`, initializer cung cấp kiểu gì? Có dùng JDK 10+ chưa?
5. Generic type arguments có được kiểm tra ở compile time, hay code đang dựa vào unchecked cast?
6. Phần nào của chương trình cần runtime check thật sự: cast, `instanceof`, reflection hay deserialization?
7. Dùng type tường minh có làm mục đích và ranh giới API rõ hơn không?

## 14. Bài tập kiểm tra hiểu biết

1. `var name = "Lan"; name = 123;` bị lỗi ở giai đoạn nào? Biến có kiểu gì sau khi suy luận?
2. `Object x = "Java";` và `String y = "Java";` có thể tham chiếu object cùng runtime class; vì sao chỉ `y.length()` được compiler chấp nhận?
3. `Animal pet = new Dog();`: nêu kiểu tĩnh của `pet` và runtime class của object. Sau `pet = new Cat();`, phần nào thay đổi?
4. Vì sao `describe(Object)` và `describe(String)` có thể cho kết quả khác khi đối số là `Object ref = "text"` và `(String) ref`?
5. So sánh `List<String> xs = new ArrayList<>();` với `var xs = new ArrayList<String>();` theo kiểu tĩnh của biến.
6. Với `var xs = new ArrayList<>();`, compiler suy ra type argument nào? Làm thế nào để yêu cầu `String`?
7. Vì sao `Function<String,Integer> length = String::length;` và `ToIntFunction<String> length = String::length;` có kiểu kết quả khác nhưng đều không phải kiểu động?
8. Viết generic method `<T> T identity(T value)`, rồi gọi bằng chuỗi và số. Kiểu nào được compiler suy ra ở mỗi lời gọi?
9. Hai object `new ArrayList<String>()` và `new ArrayList<Integer>()` có `getClass()` khác nhau không? Vì sao?
10. Vì sao `obj instanceof List<String>` không hợp lệ? Nếu cần xác thực toàn bộ phần tử đến từ API không tin cậy, phải làm gì?
11. Với object `Dog` được gán vào `Animal`, tại sao lời gọi `sound()` chạy implementation Dog nhưng lời gọi `fetch()` có thể báo lỗi biên dịch?
12. Java 8 có hỗ trợ lambda type inference không? Có hỗ trợ khai báo biến local bằng `var` không?
13. Khi `Object value = null;`, lời gọi `value.getClass()` thất bại do kiểu suy luận hay do thiếu object ở runtime?
14. Nếu sử dụng `instanceof Dog dog`, biến `dog` có static type hay dynamic type? JDK tối thiểu để dùng cú pháp này là bao nhiêu?
15. Khi nào type tường minh `List<String>` có lợi hơn `var` trong code hướng giao diện?

## Tài liệu chuẩn còn áp dụng

- [Java Language Specification SE 26 — Chapter 18: Type Inference](https://docs.oracle.com/javase/specs/jls/se26/html/jls-18.html)
- [Java Language Specification SE 26 — `15.12 Method Invocation (Overload and Runtime Dispatch)](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.12)
- [Java Language Specification SE 26 — `15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.27)
- [Java Language Specification SE 26 — `14.4 Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.4)
- [Oracle Java 18 Language Guide — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/18/language/local-variable-type-inference.html)
- [Java SE 17 — java.util.function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
- [Java SE 17 — java.util.List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)

**Kết luận:** Trong Java, **kiểu được suy luận vẫn là kiểu tĩnh** mà compiler kiểm tra trước khi chạy. `var` chỉ làm cách khai báo ngắn hơn; generics, diamond và lambda target typing cũng đều là cơ chế biên dịch. **Runtime class và polymorphic override dispatch** giải thích vì sao cùng một biến kiểu `Animal` có thể gọi implementation của `Dog` rồi `Cat`, nhưng không hề cho phép biến tự do đổi sang một kiểu không tương thích. Phân biệt ba tầng này giúp hiểu đúng lỗi biên dịch, cast, generic erasure, overload và hành vi đa hình trong Java hiện đại.
