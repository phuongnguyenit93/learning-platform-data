# Kiểm tra override, kiểu trả về và ngoại lệ khai báo trong Java

Khi một lớp con khai báo phương thức có liên quan đến phương thức đã có ở lớp cha hoặc interface, trình biên dịch Java phải xác định **đó có thật là override hay không**, rồi kiểm tra **chữ ký phương thức, quyền truy cập, kiểu trả về và các checked exception trong `throws`**. Những kiểm tra ngữ nghĩa này bảo đảm một đối tượng lớp con có thể được sử dụng qua kiểu cha mà vẫn tôn trọng hợp đồng phương thức đã công bố.

Ba câu hỏi cốt lõi:

1. **Có quan hệ override không?** Phương thức lớp con có chữ ký thích hợp và có thực sự ghi đè một instance method có thể được override?
2. **Giá trị trả về có thay thế được không?** Kiểu trả về của phương thức mới phải *return-type-substitutable* cho kiểu trả về được ghi đè, thường là **cùng kiểu hoặc kiểu con**.
3. **Ngoại lệ khai báo có phù hợp không?** Phương thức override **không được mở rộng tập checked exception** so với hợp đồng phương thức cha; có thể thu hẹp hoặc loại bỏ.

Bài tập trung vào kiểm tra ở giai đoạn biên dịch `javac`, dùng Java 17 và các tình huống có thể chạy hoặc cố ý gây lỗi để nhận diện quy tắc.

## 1. Override là gì và trình biên dịch nhận ra như thế nào?

**Override** là việc một instance method của lớp con hoặc interface con cung cấp khai báo/phần thực thi thay thế cho instance method tương ứng đã có trong kiểu cha. Khi gọi qua tham chiếu kiểu cha, phương thức được chọn để **thực thi ở runtime** có thể là bản override của lớp đối tượng thực tế (dynamic dispatch). Tuy nhiên, việc **xác định lời gọi có hợp lệ, kiểu kết quả và checked exception phải xử lý** được `javac` kiểm tra trước lúc chạy, dựa trên kiểu ở thời điểm biên dịch.

Ví dụ Java 17:

```java
class Animal {
    String sound() {
        return "unknown";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

class Example {
    public static void main(String[] args) {
        Animal animal = new Dog();
        System.out.println(animal.sound());
    }
}
```

Lưu ba lớp trên vào `Example.java`, rồi chạy:

```sh
javac --release 17 Example.java
java Example
```

**Stdout chính xác:**

```text
woof
```

`javac` công nhận `Dog.sound()` override `Animal.sound()`: tên và danh sách tham số tương ứng, cả hai đều là instance methods và kiểu trả về `String` hợp lệ. JVM gọi bản của `Dog` do đối tượng thực tế là `Dog`.

### Chữ ký không gồm kiểu trả về và `throws`

Trong Java, **method signature** được xác định bởi tên phương thức, type parameters (theo quy tắc tương đương) và danh sách kiểu tham số phù hợp; **không bao gồm** kiểu trả về, `throws` hoặc tên biến tham số.

Điều này có hai hệ quả:

- `print(String)` và `print(Object)` là hai overload do tham số khác nhau, không tự động override nhau.
- Không được khai báo hai phương thức trong cùng lớp chỉ khác kiểu trả về hoặc `throws`. Nếu đã có cùng chữ ký, quy tắc override, name clash hoặc duplicate declaration có thể áp dụng; không thể dùng return type để “phân biệt” hai overload.

Đối với generic methods và kế thừa, chuẩn dùng khái niệm **subsignature/override-equivalent** chứ không chỉ so sánh văn bản của tên/kiểu tham số. Có các trường hợp tương thích với legacy raw types được phép, đôi khi phát cảnh báo unchecked. Vì thế, mẹo “cùng tên và cùng tham số” là cách nhận biết ban đầu, còn JLS `8.4.2` và `8.4.8` mới là quy tắc đầy đủ.

### `@Override` kiểm tra gì?

`@Override` yêu cầu compiler xác nhận phương thức thực sự override hoặc implement một phương thức được phép theo quy tắc Java. Nếu viết sai tên hay tham số, `javac` báo lỗi thay vì âm thầm tạo ra một phương thức khác:

```java
class Parent {
    void save(String value) {
    }
}

class Child extends Parent {
    @Override
    void save(Object value) {
    }
}
```

Đoạn này **cố ý không biên dịch**: `save(Object)` là overload khác chữ ký, không override `save(String)`. Nếu bỏ `@Override`, compiler có thể cho phép cả hai phương thức tồn tại nhưng hành vi polymorphism không như tác giả mong đợi. Hãy giữ `@Override` trên phương thức override: đây là phép kiểm tra ngữ nghĩa rẻ và hữu ích.

`@Override` **không** thay thế các ràng buộc về kiểu trả về, `throws` hay visibility. Một phương thức có annotation đúng chỗ vẫn có thể bị từ chối vì vi phạm những quy tắc đó.

## 2. Điều kiện để một phương thức được override

| Điều kiện | Quy tắc thực tế | Nếu vi phạm |
| --- | --- | --- |
| Quan hệ kiểu | Phương thức nằm trong kiểu con có quan hệ kế thừa/triển khai phù hợp | Khai báo cùng tên ở hai lớp không liên quan không phải override |
| Chữ ký | Có quan hệ subsignature/override-equivalence theo JLS | Có thể thành overload hoặc lỗi name clash |
| Bản chất instance | Instance method ghi đè instance method | `static` và instance không được tráo đổi khi có quan hệ override-equivalent |
| Không `final` | Phương thức `final` cấm override | Compile-time error |
| Không `private` theo nghĩa kế thừa | Phương thức `private` ở lớp cha không được override | Phương thức cùng tên ở con có thể là phương thức mới, không phải override |
| Truy cập đủ rộng | Không được hạ visibility của phương thức override | Compile-time error như “attempting to assign weaker access privileges” |
| Kiểu trả về | Phải return-type-substitutable | Compile-time error hoặc unchecked warning trong một số trường hợp generic legacy |
| Checked exceptions | `throws` không được mở rộng trái hợp đồng cha | Compile-time error |
| Abstract/interface | Lớp concrete phải cung cấp implementation cho các abstract methods chưa được thỏa mãn | Lớp phải `abstract` hoặc có phương thức triển khai phù hợp |

### Quyền truy cập không được thu hẹp

Khi override:

- `public` ở cha → bắt buộc `public` ở con.
- `protected` ở cha → `protected` hoặc `public` ở con.
- Package-private ở cha → với override hợp lệ trong cùng package, không được giảm xuống `private`; có thể giữ package-private hoặc mở rộng.
- Phương thức `private` không được kế thừa theo cách một instance method override được.

Đoạn **cố ý lỗi**:

```java
class Base {
    protected void run() {
    }
}

class Sub extends Base {
    @Override
    private void run() {
    }
}
```

`javac` không cho phép phương thức override giảm truy cập từ `protected` xuống `private`. Trong các package khác nhau còn phải xét khả năng truy cập/khả năng kế thừa; đừng mặc định mọi phương thức không ghi modifier của cha đều có thể được override từ package khác.

### `static`, `private`, `final` và constructor không giống instance override

- **`static` method:** có thể bị *hide* bởi static method trong lớp con; việc chọn method dựa trên kiểu tham chiếu ở compile time, khác dynamic dispatch của instance method.
- **`private` method:** lớp con không override phương thức private của cha. Nếu lớp con khai báo cùng tên/chữ ký, đó là một phương thức riêng khi hợp lệ.
- **`final` instance method:** lớp con không thể override; class `final` còn không thể được kế thừa.
- **Constructor:** không được kế thừa và không override. Quy tắc `throws` của constructor con thuộc constructor chaining/exception checking, không phải giới hạn override của instance methods.

Ví dụ đối chiếu hiding và overriding (file `Dispatch.java`):

```java
class Parent {
    static String kind() {
        return "parent-static";
    }

    String name() {
        return "parent-instance";
    }
}

class Child extends Parent {
    static String kind() {
        return "child-static";
    }

    @Override
    String name() {
        return "child-instance";
    }
}

public class Dispatch {
    public static void main(String[] args) {
        Parent object = new Child();
        System.out.println(object.kind());
        System.out.println(object.name());
    }
}
```

Biên dịch/chạy:

```sh
javac --release 17 Dispatch.java
java Dispatch
```

**Stdout:**

```text
parent-static
child-instance
```

Gọi static method thông qua biến đối tượng là cú pháp được chấp nhận nhưng có thể gây nhầm và phát sinh lint warning khi bật các kiểm tra liên quan. Trong mã sản xuất nên viết rõ `Parent.kind()` hoặc `Child.kind()`; ví dụ dùng `object.kind()` chỉ để minh họa sự khác nhau về lựa chọn lời gọi.

## 3. Kiểu trả về: quy tắc hiệp biến (covariant return)

Nếu phương thức cha trả về một **reference type**, phương thức override thường được trả về **cùng kiểu hoặc một subtype**. Quy tắc này gọi là **covariant return**, được Java hỗ trợ để kiểu con cung cấp giá trị cụ thể hơn mà vẫn đáp ứng kiểu trả về cha.

Ví dụ:

```java
class Producer {
    Number result() {
        return 1;
    }
}

class IntegerProducer extends Producer {
    @Override
    Integer result() {
        return 42;
    }
}
```

Hợp lệ vì `Integer` là subtype của `Number`. Khi dùng `Producer p = new IntegerProducer();`, biểu thức `p.result()` có **kiểu tĩnh `Number`** nhưng đối tượng trả về lúc chạy là `Integer`. Khi dùng biến kiểu `IntegerProducer`, biểu thức `result()` có kiểu tĩnh `Integer`.

### Những kiểu trả về hợp lệ hoặc không

| Phương thức cha | Phương thức override | Kết quả |
| --- | --- | --- |
| `Number get()` | `Integer get()` | Hợp lệ: `Integer` là con của `Number` |
| `Object create()` | `String create()` | Hợp lệ: subtype reference |
| `CharSequence text()` | `String text()` | Hợp lệ |
| `int count()` | `int count()` | Hợp lệ |
| `int count()` | `long count()` | **Lỗi:** primitive không được thay chỉ vì có widening conversion |
| `void reset()` | `void reset()` | Hợp lệ |
| `void reset()` | `boolean reset()` | **Lỗi:** `void` phải giữ `void` |
| `String label()` | `Object label()` | **Lỗi:** cố mở rộng từ `String` ra `Object` |
| `List<String> list()` | `ArrayList<String> list()` | Hợp lệ: kiểu con của `List<String>` |
| `List<String> list()` | `List<Object> list()` | **Lỗi trong trường hợp thông thường:** generic `List` là invariant |

**Không áp dụng autoboxing như một phép thay thế return override.** `int` và `Integer` khác nhau; việc Java tự boxing trong biểu thức không làm `Integer get()` hợp lệ để override `int get()`.

### Khái niệm đầy đủ: return-type-substitutability

JLS `8.4.5` định nghĩa *return-type-substitutable*. Với reference type, quan hệ subtype là trường hợp phổ biến nhưng chuẩn còn cho phép một số tương thích với mã nguồn generic/raw cũ và **yêu cầu cảnh báo unchecked** khi return type không phải subtype theo đúng nghĩa. Vì vậy, phát biểu “kiểu trả về luôn phải đúng subtype, tuyệt đối không ngoại lệ” là chưa đầy đủ đối với những thư viện Java tiền generic.

Đối với mã mới: ưu tiên cùng return type hoặc subtype rõ ràng, không sử dụng raw types để “vượt qua” kiểm tra kiểu. Khi compiler phát warning về return-type substitution, hiểu đó là tín hiệu thiếu an toàn kiểu có thể biểu hiện ở runtime.

### Ví dụ cố ý lỗi do kiểu trả về

```java
class Parent {
    Number value() {
        return 1;
    }
}

class BadChild extends Parent {
    @Override
    String value() {
        return "x";
    }
}
```

Đây là **ví dụ negative test, không được biên dịch thành công**. `String` không phải subtype có thể thay thế `Number`; đổi tên phương thức, thay tham số (nếu thực sự muốn overload) hoặc chọn return type tương thích với hợp đồng cha.

## 4. `throws`: checked và unchecked exception

Trước khi kiểm tra `throws` khi override, phải phân biệt:

- **Checked exception:** subtype của `Throwable` không thuộc nhóm `RuntimeException` và `Error`. Ví dụ `IOException`, `FileNotFoundException`, `SQLException`. Trình biên dịch bắt buộc xử lý hoặc khai báo khi một operation có thể ném checked exception theo quy tắc exception analysis.
- **Unchecked exception:** `RuntimeException` và các subclass của nó, `Error` và các subclass. Ví dụ `IllegalArgumentException`, `NullPointerException`. Không bị yêu cầu bắt/khai báo trong `throws` theo cơ chế checked exception.

Từ **khai báo của một phương thức**, `throws` là phần của hợp đồng kiểm tra ngoại lệ cho code gọi đến nó; `throws` **không** phải thành phần dùng để phân biệt overload. Một phương thức có thể khai báo checked exception mà không ném ngoại lệ đó trong mọi đường chạy; tương tự, phương thức không khai báo unchecked exception vẫn có thể ném loại unchecked lúc thực thi.

## 5. Quy tắc checked exception khi override

**Phương thức override không được khai báo checked exception mới hoặc rộng hơn những gì phương thức bị override cho phép.** Những trường hợp thường gặp:

| Phương thức cha | Phương thức con | Hợp lệ? |
| --- | --- | --- |
| `void load() throws IOException` | `void load() throws IOException` | Có: cùng loại |
| `void load() throws IOException` | `void load() throws FileNotFoundException` | Có: checked exception hẹp hơn |
| `void load() throws IOException` | `void load()` | Có: bỏ hẳn checked exception |
| `void load()` | `void load() throws IOException` | **Không:** thêm checked exception |
| `void load() throws FileNotFoundException` | `void load() throws IOException` | **Không:** mở rộng checked exception |
| `void load() throws IOException` | `void load() throws Exception` | **Không:** mở rộng |
| `void load()` | `void load() throws IllegalStateException` | Có: unchecked exception không bị giới hạn này |
| `void load() throws IOException` | `void load() throws IOException, IllegalArgumentException` | Có: unchecked được phép thêm |

`FileNotFoundException extends IOException`, do đó nếu cha cho phép `IOException` thì con khai báo `FileNotFoundException` là thu hẹp hợp lệ. Ngược lại, nếu cha chỉ cho phép `FileNotFoundException` thì con không được khai báo `IOException` vì nó còn có các subclass khác.

Nếu phương thức cha khai báo **nhiều checked exceptions**, mỗi checked exception của phương thức con phải có quan hệ phù hợp với ít nhất một ngoại lệ được phương thức cha cho phép, theo quy tắc chính xác của JLS `8.4.8.3`, đồng thời phải thỏa mọi phương thức tương ứng được override/hide trong hệ kế thừa. Với các generic `throws T`, type variables và erasure còn có các chi tiết bổ sung; không lấy một sơ đồ subtype đơn giản thay thế toàn bộ tiêu chuẩn.

### Ví dụ lỗi: mở rộng `throws`

```java
import java.io.IOException;

class Parent {
    void read() throws IOException {
    }
}

class BadChild extends Parent {
    @Override
    void read() throws Exception {
    }
}
```

**Đoạn trên cố ý gây compile-time error.** `Exception` rộng hơn `IOException`, nên code gọi qua `Parent` có thể chỉ chuẩn bị xử lý `IOException` mà không biết những checked exception khác từ bản override. Đổi `throws Exception` thành `throws IOException`, subtype như `FileNotFoundException`, hoặc bỏ khai báo nếu body không phát sinh checked exception.

### Không khai báo nhưng thân hàm ném checked exception thì sao?

`throws` của cha có thể cho phép một loại checked exception, nhưng **body phương thức con vẫn phải tuân thủ chính khai báo `throws` của nó**:

```java
import java.io.IOException;

class Parent {
    void load() throws IOException {
    }
}

class BadChild extends Parent {
    @Override
    void load() {
        throw new IOException("failed");
    }
}
```

Cũng **cố ý không biên dịch**: phương thức con không khai báo `throws IOException` và không bắt ngoại lệ đó trong body. Để hợp lệ, thêm `throws IOException` vào bản override (được phép vì cha đã khai báo) hoặc xử lý ngoại lệ bằng `try/catch`.

Đừng suy ra rằng `throws` của cha tự động “được kế thừa vào thân phương thức con”. Kiểu exception mà compiler kiểm tra tại một declaration phụ thuộc vào `throws` của **chính method được khai báo**, cùng quy tắc exception analysis của body.

## 6. Ví dụ end-to-end: covariant return + thu hẹp `throws` + dynamic dispatch

Tạo cấu trúc nguồn:

```text
project/
└── src/
    └── demo/
        └── Main.java
```

Nội dung đầy đủ `src/demo/Main.java`:

```java
package demo;

import java.io.FileNotFoundException;
import java.io.IOException;

public class Main {
    static class Parent {
        public Number read() throws IOException {
            return -1;
        }
    }

    static final class Child extends Parent {
        @Override
        public Integer read() throws FileNotFoundException {
            return 42;
        }
    }

    public static void main(String[] args) throws IOException {
        Parent parentRef = new Child();
        Child childRef = new Child();

        System.out.println(parentRef.read());
        System.out.println(childRef.read().getClass().getSimpleName());
    }
}
```

Từ thư mục `project`, dùng JDK hỗ trợ Java 17:

```sh
javac --release 17 -encoding UTF-8 -d out src/demo/Main.java
java -cp out demo.Main
```

**Stdout chính xác:**

```text
42
Integer
```

Giải thích:

1. `Child.read()` là override hợp lệ của `Parent.read()`. `@Override` xác nhận quan hệ đó.
2. Kiểu trả về từ `Number` thu hẹp thành `Integer`, là **covariant return** hợp lệ.
3. `throws IOException` của cha thu hẹp thành `throws FileNotFoundException` ở con, cũng hợp lệ. Không có exception thực tế nào được ném trong body ví dụ.
4. `Parent parentRef = new Child();` có **kiểu tĩnh** `Parent` nhưng trỏ tới đối tượng `Child`. Gọi `parentRef.read()` sử dụng implementation `Child.read()` ở runtime, nên in `42`.
5. `childRef.read()` có kiểu tĩnh trả về `Integer`; `getClass().getSimpleName()` của giá trị trả về cho chuỗi `Integer`.
6. Vì lời gọi `parentRef.read()` được kiểm tra từ kiểu `Parent`, khai báo `main throws IOException` ở đây xử lý yêu cầu checked exception phía compiler, dù implementation `Child` không ném gì lúc chạy.

**Điểm then chốt:** Quy tắc checked exception phụ thuộc **kiểu tại compile time** của lời gọi, còn thân method được dispatch phụ thuộc **đối tượng thực tế**. Không thể kết luận code gọi qua `Parent` khỏi cần xử lý `IOException` chỉ vì tình cờ đang cầm một `Child`.

### Có thể bỏ `throws` ở con hoàn toàn

Thay thế riêng phương thức `Child.read()` trong ví dụ bằng:

```java
@Override
public Integer read() {
    return 42;
}
```

Bản override vẫn hợp lệ vì vừa return covariant vừa bỏ hẳn checked exception. Nếu truy cập qua biến kiểu `Parent`, lời gọi vẫn được compiler kiểm tra theo `Parent.read() throws IOException`.

## 7. Implement interface cũng phải thỏa cùng hợp đồng

Interface method thông thường là `public`; lớp implement phải khai báo implementation với visibility ít nhất `public`, return type có thể thay thế và `throws` không rộng hơn. Quy tắc tương tự áp dụng cho abstract superclass và default method được override.

Ví dụ hợp lệ với **hai interface**:

```java
import java.io.IOException;
import java.sql.SQLException;

interface Left {
    CharSequence report() throws IOException;
}

interface Right {
    String report() throws SQLException;
}

final class Reporter implements Left, Right {
    @Override
    public String report() {
        return "ready";
    }
}

class InterfaceExample {
    public static void main(String[] args) {
        Reporter reporter = new Reporter();
        System.out.println(reporter.report());
    }
}
```

Đặt đoạn này vào `InterfaceExample.java` (không có public top-level class) rồi chạy:

```sh
javac --release 17 InterfaceExample.java
java InterfaceExample
```

**Stdout:**

```text
ready
```

`String` là subtype của `CharSequence` và cũng chính là return type của `Right.report()`; implementation **không khai báo checked exception** nên không vi phạm `IOException` hoặc `SQLException` của hai interface. Lưu ý nếu implementation lại khai báo `throws IOException` thì sẽ **không thỏa** hợp đồng `Right.report()`, vì `IOException` không phải subtype được `SQLException` cho phép. Khi một method phải đáp ứng nhiều superinterfaces, không được chỉ kiểm tra riêng interface thuận tiện nhất.

Khi gọi thông qua `Left` hoặc `Right`, compiler vẫn kiểm tra `throws` tương ứng của từng **kiểu tĩnh**:

```java
Left left = new Reporter();
// left.report(); // Cần catch/throws IOException, dù Reporter.report() không khai báo.

Right right = new Reporter();
// right.report(); // Cần catch/throws SQLException.
```

Đây chỉ là **mảnh minh họa**; hai dòng lời gọi bị comment để không thay đổi chương trình chạy đầy đủ.

### Default methods và xung đột

Nếu hai interface cung cấp default method trùng chữ ký và một class kế thừa cả hai, class thường phải override rõ ràng để giải quyết xung đột. Khi tự viết bản override, nó vẫn phải tuân thủ return-type substitutability và checked `throws` đối với các hợp đồng bị ghi đè. Ngay cả khi hai abstract methods cùng chữ ký được kế thừa từ nhiều interface, việc kết hợp return types có thể hợp lệ hoặc tạo lỗi biên dịch nếu không có kiểu trả về có thể thay thế phù hợp.

**Không dùng default method để tùy tiện định nghĩa lại các phương thức public của `Object`** như `toString()`; JLS có ràng buộc riêng đối với default method có chữ ký tương đương phương thức `Object`.

## 8. Generic, erasure và bridge methods: những chi tiết liên quan kiểm tra override

Với generic inheritance:

```java
class Box<T> {
    T get() {
        return null;
    }
}

class StringBox extends Box<String> {
    @Override
    String get() {
        return "text";
    }
}
```

`StringBox.get()` override `Box<String>.get()` hợp lệ. Khi type erasure xảy ra, JVM method descriptor không giữ nguyên mọi thông tin generic như source; compiler có thể phát sinh một **synthetic bridge method** để duy trì cơ chế dispatch tương thích. Bridge là chi tiết bytecode; nó **không** cho phép khai báo hai source methods chỉ khác return type.

Có thể dùng `javap -p -c` và, nếu cần, `javap -v` để nghiên cứu bytecode do một bản JDK tạo. Khi làm việc ở mức source, hãy dựa vào quy tắc override của Java thay vì tự viết tên bridge hoặc dựa vào implementation detail.

### Generic không hiệp biến theo tham số kiểu

`List<String>` **không** là subtype của `List<Object>`. Vì vậy, trường hợp sau là **negative test**:

```java
import java.util.List;

class Base {
    List<Object> items() {
        return List.of();
    }
}

class BadChild extends Base {
    @Override
    List<String> items() {
        return List.of("a");
    }
}
```

Hai return types có tham số kiểu không tương thích nên không phải bản override hợp lệ. Nếu hợp đồng cha cần cho phép linh hoạt, hãy thiết kế API cẩn thận với kiểu tổng quát hoặc wildcard phù hợp, thay vì dựa vào raw type và bỏ qua warning.

### Name clash do erasure

Hai method `process(List<String>)` và `process(List<Integer>)` **không thể cùng tồn tại để tạo hai overload phân biệt được ở runtime**, vì sau erasure chữ ký có thể trùng nhau. `javac` phát hiện tình huống name clash. Đây là lỗi ngữ nghĩa liên quan generic signature, nhưng khác với việc return type/`throws` của một override có hợp lệ hay không.

## 9. Biên dịch từng bước và đọc diagnostics

Khi `javac` xác định một method override không hợp lệ, thông báo thường chỉ ra **method con**, **method bị override**, và vấn đề như return type không tương thích, checked exception rộng hơn, giảm visibility hoặc không thực sự override.

Một số dạng chẩn đoán thường thấy (từ ngữ, dấu vị trí và thứ tự có thể khác theo JDK):

| Nội dung lỗi | Kiểm tra cần làm |
| --- | --- |
| `method does not override or implement a method from a supertype` | Có viết sai tên, sai parameter types, dùng `@Override` cho overload hay method không thể override? |
| `return type ... is not compatible with ...` | Có vi phạm covariant return, primitive/void hoặc generic invariance? |
| `overridden method does not throw ...` | Method con đang thêm checked exception mà cha không cho phép? |
| `... is overridden method ... throws ...` | Checked exception ở con có rộng hơn hợp đồng? |
| `attempting to assign weaker access privileges` | Đã giảm `public`/`protected` xuống hẹp hơn? |
| `overridden method is final` | Đang ghi đè phương thức `final`? |
| `name clash: ... have the same erasure` | Có xung đột generic signatures sau erasure? |
| `... is not abstract and does not override abstract method ...` | Concrete class còn thiếu implementation của abstract/interface method? |

Quy trình điều tra:

1. Xác nhận **tên, kiểu tham số, modifier** của method cha và method con; với generic, xem các kiểu sau khi thay type arguments của superclass/interface.
2. Kiểm tra phương thức cha có thể được kế thừa/override không: `static`, `private`, `final`, package accessibility, module visibility.
3. So sánh **return types**: same type, subtype, primitive/void, generic invariant hay trường hợp legacy có unchecked warning?
4. So sánh **checked exceptions** trong `throws`: từng loại ở con phải hợp lệ đối với **mọi** hợp đồng được override.
5. Đảm bảo **body** đã catch hoặc khai báo các checked exception có thể phát sinh; đây là phép kiểm tra khác với tính hợp lệ của bản override.
6. Biên dịch lại với compiler và release dự kiến. Nếu cần thêm diagnostics, có thể dùng `-Xdiags:verbose`; đọc lỗi đầu tiên có nguyên nhân rõ thay vì chỉ đọc dòng lỗi cuối.
7. Chỉ sau khi compile thành công mới chạy kiểm thử hành vi dispatch và exception handling.

Các snippet ghi rõ **cố ý lỗi** ở trên là bài kiểm tra âm; không nên ghép vào cùng file của một ví dụ chạy được. Khi biên dịch ví dụ lỗi, không hứa chính xác toàn bộ stderr vì cách trình bày diagnostics phụ thuộc JDK.

## 10. Các hiểu nhầm thường gặp

**“Nếu method con cùng tên thì là override.”** Không. Phải đối chiếu chữ ký, quan hệ kế thừa và các điều kiện của instance method. Thay parameter types có thể thành overload. Annotation `@Override` giúp bắt nhầm lẫn.

**“Kiểu trả về có thể khác tùy ý miễn có thể ép kiểu.”** Không. Covariant return cho reference types và quy tắc return-type-substitutability mới là tiêu chuẩn. Primitive widening/boxing không làm override hợp lệ.

**“Con được khai báo `throws Exception` vì Exception là cha của IOException.”** Sai: mở rộng checked exceptions phá hợp đồng từ phía caller. `IOException` ở cha không cho phép con khai báo tùy ý `Exception`.

**“Bỏ `throws` ở con thì mọi caller đều khỏi catch.”** Sai: caller qua kiểu tĩnh của cha vẫn phải đáp ứng checked exceptions trong declaration cha.

**“Unchecked exceptions không thể được khai báo ở con.”** Sai. Có thể thêm `RuntimeException` hoặc subclass của nó trong `throws` mà không vi phạm hạn chế checked exceptions, dù API vẫn cần cân nhắc hợp đồng hành vi.

**“Phương thức `static` được override giống instance method.”** Không. Static có thể bị hide; việc lựa chọn dựa trên kiểu tham chiếu ở compile time, không dispatch theo object.

**“`private` ở cha có thể được override nếu `@Override`.”** Không. Annotation không thay đổi tính kế thừa/khả năng override.

**“Tất cả phương thức implement interface có thể để package-private.”** Không. Implementation cần `public` phù hợp với interface method.

**“Một class thực thi hai interface thì chỉ cần thỏa `throws` của một interface.”** Không. Implementation phải thỏa mọi declaration liên quan; nếu các checked exception sets không giao thoa, lựa chọn bỏ checked exceptions thường là cách đơn giản nhất.

**“Đã compile thành công thì method không thể ném exception khác.”** Không. Unchecked exceptions vẫn có thể xuất hiện ở runtime, và lỗi checked/unchecked cần được phân tích theo ngữ nghĩa thực tế; compile-time checking không chứng minh chương trình không lỗi khi chạy.

## 11. Checklist đọc hoặc viết một bản override

- [ ] Có quan hệ kế thừa/implements hợp lệ? Method cha có khả năng override?
- [ ] Tên và parameter list tạo subsignature phù hợp, kể cả generic/erasure?
- [ ] Có `@Override` để compiler kiểm tra việc ghi đè?
- [ ] Method không ghi đè `final`/`private` hoặc nhầm `static` hiding?
- [ ] Visibility của con có ít nhất rộng bằng cha?
- [ ] Kiểu trả về cùng kiểu hoặc return-type-substitutable (reference subtype, primitive/void phù hợp)?
- [ ] Không thêm hay mở rộng checked exception trong `throws` so với mọi method bị override?
- [ ] Thân method xử lý/khai báo checked exceptions do chính nó phát sinh?
- [ ] Concrete class đã triển khai mọi abstract/interface methods bắt buộc?
- [ ] Khi gọi qua kiểu cha, code caller đã xử lý checked exceptions của **kiểu tĩnh**, còn runtime dispatch đã được kiểm tra?

**Cốt lõi:** Compiler bảo vệ hợp đồng kế thừa bằng cách kiểm tra **quan hệ override → quyền truy cập và kiểu trả về → phạm vi checked exceptions**. Covariant return giúp lớp con cụ thể hóa kết quả; thu hẹp `throws` giúp không bắt caller phải xử lý ngoại lệ mới; `@Override` biến ý định ghi đè thành một kiểm tra trực tiếp của `javac`.

### Tài liệu chuẩn để tra cứu

- *Java Language Specification 17*, `8.4.2 — Method Signature; `8.4.5 — Method Result; `8.4.6 — Method Throws; `8.4.8 — Inheritance, Overriding, and Hiding: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html
- *Java Language Specification 17*, `9.4.1 — Interface Methods, Overriding: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html
- *Java Language Specification 17*, `11.1 và `11.2 — Checked/Unchecked Exceptions và Compile-Time Checking: https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html