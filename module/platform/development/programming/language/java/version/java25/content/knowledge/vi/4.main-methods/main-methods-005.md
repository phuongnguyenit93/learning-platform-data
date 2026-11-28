# Phạm vi truy cập và khả năng kế thừa của phương thức main

## 1. Vì sao cần học lại quy tắc main ở Java 25?

Trong nhiều năm, hầu hết tài liệu Java bắt đầu bằng:

~~~java
public class App {
    public static void main(String[] args) {
        System.out.println("Hello!");
    }
}
~~~

Cách viết này **vẫn hợp lệ, được hỗ trợ đầy đủ và phù hợp cho dự án hiện đại**. Tuy nhiên, **không còn là hình thức duy nhất** mà Java launcher có thể dùng để khởi động chương trình.

Từ **Java 25**, JEP 512 (*Compact Source Files and Instance Main Methods*) đã được hoàn thiện thành tính năng chính thức. Nó cho phép chương trình có phương thức `main` là **instance method** hoặc `static method`, có thể không mang tham số và không bắt buộc `public`. Đồng thời, `main` có thể được **kế thừa** từ lớp cha hoặc thậm chí là một `default method` từ interface.

Bài thuộc chương **Hàm main** trong module **JAVA_VERSION_JAVA25**. Mục tiêu là hiểu **phạm vi truy cập và khả năng kế thừa của `main`** như Java 25 quy định, thay vì dùng một lời giải thích cũ chỉ đúng cho Java trước đó. Những đặc tính khác của Java 25 như compact source files, module import, constructor linh hoạt, `ScopedValue`, KDF API, AOT cache hay JFR vẫn hữu ích trong ứng dụng hiện đại nhưng không phải trọng tâm của bài này.

### Mục tiêu học tập

Kết thúc bài, người học có thể:

1. Nhận diện phương thức `main` nào đủ điều kiện để Java 25 khởi chạy.
2. Phân biệt `public`, `protected`, *package-private* và `private` đối với entry point.
3. Giải thích sự khác nhau giữa `static main` và **instance main**, đặc biệt việc tạo đối tượng trước khi gọi instance method.
4. Dự đoán launcher sẽ chọn `main(String[] args)` hay `main()` nếu cả hai tồn tại.
5. Chạy một lớp con khi `main` được **kế thừa**, bị **override** hoặc bị **hide**.
6. Phân biệt instance `main` kế thừa từ **lớp cha** và từ **default method của interface**.
7. Xác định các tình huống compile thành công nhưng launcher thất bại vì thiếu entry point hoặc không tạo được instance.
8. Viết ví dụ và bộ kiểm tra bằng JDK 25 **không cần** `--enable-preview`.

> **Giới hạn:** bài sử dụng cú pháp và quy tắc chính thức của **Java SE 25**, đặc biệt JLS `12.1.4 và JEP 512. Những hướng dẫn từ giai đoạn Java 21–24 về *preview* hoặc thứ tự chọn `main` cũ không được dùng làm quy tắc cho Java 25.

## 2. main là entry point, không phải một loại phương thức đặc biệt về cú pháp

Một phương thức tên `main` vẫn tuân theo quy tắc ngôn ngữ Java về:

- **Chữ ký (signature):** tên và kiểu tham số quyết định overload.
- **Kiểu trả về:** entry point phải trả về `void`.
- **Phạm vi truy cập:** `public`, `protected`, package-private hoặc `private`.
- **Phân loại:** `static` thuộc lớp; phương thức instance thuộc đối tượng.
- **Kế thừa, override và hide:** áp dụng theo quy tắc chung của class/interface.
- **Lỗi biên dịch:** Java không cho hai phương thức cùng chữ ký chỉ khác nhau ở `static` hoặc kiểu trả về.

Điểm đặc biệt nằm ở **launch protocol**: khi chạy `java TenLop`, launcher cần tìm một phương thức đủ điều kiện và quyết định cách gọi nó.

Hai khái niệm nên tách biệt:

| Khái niệm | Nội dung |
| --- | --- |
| Phương thức hợp lệ ở mức Java source | Code có thể biên dịch thành công, dù chưa chắc dùng được làm điểm vào |
| **Candidate/launchable main** | `main` đáp ứng mẫu mà Java 25 launcher tìm và gọi |
| **Initial class** | Class/interface được chỉ định để launcher bắt đầu, ví dụ `java Runner` |
| **Inherited main** | Phương thức `main` mà initial class có được qua kế thừa hợp lệ |
| **Selected main** | Một candidate cụ thể được chọn theo thứ tự ưu tiên Java 25 |

Do đó, một class chỉ có `private void main()` vẫn có thể là **Java source hợp lệ**, nhưng việc chọn class đó làm chương trình khởi động sẽ thất bại nếu không có candidate `main` nào khác.

## 3. Quy tắc đầy đủ của candidate main trong Java 25

Theo JLS Java SE 25 `12.1.4, `main` là **candidate** khi đáp ứng **tất cả** yêu cầu:

1. Tên phương thức là `main`.
2. Kiểu trả về là `void`.
3. Có **không tham số** hoặc đúng **một tham số `String[]`**; cú pháp `String...` cũng biểu diễn cùng kiểu tham số mảng.
4. Phạm vi truy cập là `public`, `protected` hoặc **package-private** (không ghi access modifier).
5. Có thể là **`static` hoặc instance**.
6. Có thể được khai báo trực tiếp hoặc được **kế thừa hợp lệ** bởi initial class/interface.

Không cần `throws` đặc biệt; một candidate có thể khai báo `throws IOException` hay `throws Exception` theo quy tắc Java thông thường.

### Bảng 12 dạng main cơ bản

Lấy ba mức truy cập hợp lệ nhân hai lựa chọn `static/instance` và hai dạng tham số:

| Quyền truy cập | Static/instance | Chữ ký ví dụ | Candidate trong Java 25? |
| --- | --- | --- | --- |
| `public` | static | `public static void main(String[] args)` | Có |
| `public` | static | `public static void main()` | Có |
| `public` | instance | `public void main(String[] args)` | Có |
| `public` | instance | `public void main()` | Có |
| `protected` | static | `protected static void main(String[] args)` | Có |
| `protected` | static | `protected static void main()` | Có |
| `protected` | instance | `protected void main(String[] args)` | Có |
| `protected` | instance | `protected void main()` | Có |
| package-private | static | `static void main(String[] args)` | Có |
| package-private | static | `static void main()` | Có |
| package-private | instance | `void main(String[] args)` | Có |
| package-private | instance | `void main()` | Có |

`String... args` được chấp nhận thay `String[] args` ở những dòng có tham số, nhưng **không tạo thêm một chữ ký overload riêng**.

### Những dạng không đủ điều kiện

| Khai báo | Có thể biên dịch? | Dùng làm entry point? | Lý do |
| --- | --- | --- | --- |
| `private static void main(String[] args)` | Có | **Không** | `private` không phải access candidate |
| `private void main()` | Có trong class tường minh | **Không** | `private` không phải access candidate |
| `static int main(String[] args)` | Có | **Không** | Trả về `int` thay vì `void` |
| `void main(String name)` | Có | **Không** | Không phải `String[]` |
| `void main(String[] args, int code)` | Có | **Không** | Hai tham số |
| `void Main(String[] args)` | Có | **Không** | Java phân biệt hoa/thường |
| `void main(Object[] args)` | Có | **Không** | `Object[]` khác `String[]` |
| `void main(List<String> args)` | Có nếu import đúng | **Không** | Kiểu tham số không đúng |

**Quy tắc ngắn:** `private` bị loại ngay khỏi tập candidate; launcher không tự nâng quyền truy cập của private method thành entry point.

## 4. Thực hành từng mức truy cập

Các ví dụ sau là **các tệp độc lập**. Tạo từng tệp đúng tên bên dưới rồi chạy với **JDK 25**.

### 4.1. public main

Tệp `PublicMain.java`:

~~~java
public class PublicMain {
    public static void main(String[] args) {
        System.out.println("public static main");
    }
}
~~~

Chạy:

~~~bash
java PublicMain.java
~~~

Kết quả:

~~~text
public static main
~~~

Đây là hình thức quen thuộc. Nó hữu ích khi cần entry point có tên class rõ ràng, tương thích với nhiều công cụ build, IDE và framework.

### 4.2. protected instance main

Tệp `ProtectedMain.java`:

~~~java
class ProtectedMain {
    protected void main(String[] args) {
        System.out.println("protected instance: " + args.length);
    }
}
~~~

Chạy:

~~~bash
java ProtectedMain.java a b
~~~

Kết quả:

~~~text
protected instance: 2
~~~

Lớp `ProtectedMain` **không phải `public`** và method `main` **không phải `static`**. Java 25 vẫn có thể khởi chạy theo giao thức mới.

### 4.3. package-private main

Tệp `PackageMain.java`:

~~~java
class PackageMain {
    void main() {
        System.out.println("package-private instance main");
    }
}
~~~

Chạy:

~~~bash
java PackageMain.java
~~~

Kết quả:

~~~text
package-private instance main
~~~

Không ghi access modifier nghĩa là **package-private**, không phải `private`. Java launcher có thể nhận candidate này, dù một class khác ở package khác không được phép gọi method theo quy tắc truy cập Java thông thường.

### 4.4. private main không đủ điều kiện

Tệp `PrivateMain.java`:

~~~java
class PrivateMain {
    private void main() {
        System.out.println("Không phải launchable main");
    }
}
~~~

Với class tường minh, đoạn trên có thể được biên dịch:

~~~bash
javac --release 25 PrivateMain.java
~~~

Nhưng chạy:

~~~bash
java PrivateMain
~~~

sẽ thất bại ở **bước khởi chạy** vì không có candidate `main` hợp lệ. Nội dung lỗi cụ thể tùy bản JDK, không nên viết test dựa vào nguyên văn thông báo.

**Khác biệt cần nhớ:** compiler cho phép một phương thức `private main` như một thành viên bình thường; Java launcher không có nghĩa vụ coi nó là entry point.

## 5. Static main và instance main khác nhau thế nào?

### Static main

~~~java
class StaticProgram {
    static void main(String[] args) {
        System.out.println("Chạy mà không cần new");
    }
}
~~~

`static main` thuộc về class, launcher **không phải tạo instance** để gọi. Điều này có ý nghĩa khi class không có constructor không tham số hoặc không nên được tạo chỉ để chạy ứng dụng.

### Instance main

~~~java
class InstanceProgram {
    private final String label;

    InstanceProgram() {
        label = "đã chạy constructor";
    }

    void main(String[] args) {
        System.out.println(label);
        System.out.println("Số đối số: " + args.length);
    }
}
~~~

Chạy `java InstanceProgram.java mot hai`. Trước khi gọi `main`, launcher phải tạo một instance của **initial class** bằng một constructor không tham số có thể sử dụng; các field initializer và constructor chạy như khi tạo đối tượng bình thường.

Đầu ra:

~~~text
đã chạy constructor
Số đối số: 2
~~~

`InstanceProgram` có thể dùng field và gọi các method instance mà không cần mọi thành viên phải là `static`. Đó là lý do instance main hữu ích cho chương trình nhỏ với trạng thái cục bộ.

### Quy tắc về constructor

Nếu launcher đã chọn **instance main**, nó phải tạo được một instance của initial class:

- Class có constructor không tham số khả dụng: có thể khởi chạy.
- Class không khai báo constructor: thường có **default constructor** nếu là class tường minh thông thường; kiểm tra accessibility phù hợp.
- Class chỉ có constructor nhận tham số: launcher không biết cung cấp tham số, nên khởi chạy sẽ thất bại.
- Class `abstract` không thể được tạo trực tiếp để gọi instance main.
- Nếu constructor ném exception, chương trình có thể thất bại **trước khi main chạy**.
- Một non-static inner class có thể cần enclosing instance, vì vậy không phải lựa chọn phù hợp cho entry point instance thông thường.

Để entry point rõ ràng và dễ di chuyển giữa môi trường, hãy cung cấp constructor không tham số **không private** khi cần instance main. Không dựa vào các chi tiết triển khai hoặc hành vi phản chiếu đặc biệt của một bản JDK đối với private constructor.

Tệp `NoDefaultConstructor.java` minh họa ca khởi chạy lỗi:

~~~java
class NoDefaultConstructor {

    NoDefaultConstructor(String config) {
        System.out.println(config);
    }

    void main() {
        System.out.println("Không chạy được theo giao thức instance");
    }
}
~~~

Lệnh `javac --release 25 NoDefaultConstructor.java` có thể **biên dịch thành công**. Lệnh `java NoDefaultConstructor` không thể khởi tạo đối tượng theo cách launcher yêu cầu.

**Mặt khác:** nếu class chỉ có `static void main()`, việc thiếu zero-argument constructor không cản trở launcher gọi method tĩnh.

## 6. Cách Java 25 chọn main khi có nhiều overload

Một class có thể khai báo **cả hai** dạng `main(String[] args)` và `main()`. Java 25 cho phép điều này vì chữ ký khác nhau.

**Thứ tự ưu tiên trong Java 25:**

1. Tìm candidate `main` có **một tham số `String[]`**.
2. Nếu không có, tìm candidate `main` **không tham số**.
3. Nếu chọn method **static**, gọi trực tiếp.
4. Nếu chọn method **instance**, tạo instance của initial class rồi gọi.
5. Nếu không tìm được candidate hoặc không thể tạo instance cần thiết, launch thất bại.

Điểm rất quan trọng: **ưu tiên theo dạng tham số, không ưu tiên static trước instance**.

~~~mermaid
flowchart TD
    A[Launch initial class] --> B{Có candidate main với String[]?}
    B -- Có --> C[Chọn main String[]]
    B -- Không --> D{Có candidate main không tham số?}
    D -- Có --> E[Chọn main()]
    D -- Không --> F[Launch thất bại]
    C --> G{Method static?}
    E --> G
    G -- Có --> H[Gọi main trực tiếp]
    G -- Không --> I[Tạo instance bằng zero-arg constructor]
    I --> J{Tạo được instance?}
    J -- Có --> K[Gọi instance main]
    J -- Không --> F
~~~

### 6.1. Instance main(String[]) thắng static main()

Tệp `Selection.java`:

~~~java
class Selection {

    static void main() {
        System.out.println("static main không tham số");
    }

    void main(String[] args) {
        System.out.println("instance main(String[]): " + args.length);
    }
}
~~~

Chạy:

~~~bash
java Selection.java A B
~~~

Kết quả:

~~~text
instance main(String[]): 2
~~~

Mặc dù có `static main()`, launcher chọn **instance `main(String[])`** vì có tham số mảng. Constructor mặc định của `Selection` cho phép tạo object.

### 6.2. Static main(String[]) thắng instance main()

Tệp `Selection2.java`:

~~~java
class Selection2 {

    void main() {
        System.out.println("instance main()");
    }

    static void main(String[] args) {
        System.out.println("static main(String[]): " + args.length);
    }
}
~~~

Chạy `java Selection2.java x` và nhận:

~~~text
static main(String[]): 1
~~~

### 6.3. Không được phân biệt overload chỉ bằng static/instance

Đoạn sau **không thể biên dịch**:

~~~java
class InvalidDuplicate {
    static void main(String[] args) {}
    void main(String[] args) {}
}
~~~

Hai khai báo có **cùng signature**; Java không cho chúng cùng tồn tại dù một cái static, một cái instance. Tương tự, `main(String[] args)` và `main(String... args)` **cũng cùng signature**, không thể dùng làm hai overload độc lập.

### 6.4. Hành vi không phải “main có trong source file đầu tiên”

Khi chạy `java SomeClass`, đầu vào là **initial class** do launcher chọn. Khi chạy `java SomeFile.java`, Java source-file mode chọn class theo quy tắc của launcher cho tệp nguồn đó. Đừng dùng một tệp chứa nhiều top-level classes để thử inheritance/selection rồi đoán tên class được khởi chạy; trong ví dụ kế thừa bên dưới, ta **biên dịch trước và gọi chính xác lớp con**.

## 7. main có thể được kế thừa từ lớp cha

Java 25 cho phép launcher tìm candidate `main` được khai báo trong **initial class hoặc được kế thừa bởi class đó**.

Để tránh nhầm việc source-file mode chọn class trong tệp chứa nhiều class, các bài thực hành sẽ dùng `javac` và `java Child` riêng biệt.

### 7.1. Kế thừa instance main(String[])

Tệp `BaseProgram.java`:

~~~java
class BaseProgram {

    protected void main(String[] args) {
        System.out.println("Base instance main: " + args.length);
    }
}
~~~

Tệp `ChildProgram.java`:

~~~java
class ChildProgram extends BaseProgram {
    // Không khai báo main
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 25 BaseProgram.java ChildProgram.java
java ChildProgram a b c
~~~

Kết quả:

~~~text
Base instance main: 3
~~~

Giải thích:

1. Initial class là `ChildProgram`, không phải `BaseProgram`.
2. `ChildProgram` **kế thừa** `protected void main(String[])` từ superclass.
3. Launcher chọn inherited candidate với `String[]`.
4. Launcher tạo **instance của ChildProgram**, không phải tạo BaseProgram thuần túy.
5. Method body được kế thừa chạy trên đối tượng ChildProgram.

Đây là **kế thừa phương thức bình thường**, không phải một quy tắc đặc biệt chỉ dành cho main.

### 7.2. Override instance main

Sửa `ChildProgram.java`:

~~~java
class ChildProgram extends BaseProgram {

    @Override
    public void main(String[] args) {
        System.out.println("Child override main: " + args.length);
    }
}
~~~

Chạy lại:

~~~bash
javac --release 25 BaseProgram.java ChildProgram.java
java ChildProgram X
~~~

Kết quả:

~~~text
Child override main: 1
~~~

`@Override` giúp compiler kiểm tra rằng method của lớp con thật sự override method phù hợp từ superclass. Vì parent method là `protected`, child có thể nâng thành `public`. Child **không được giảm visibility** từ `protected` xuống package-private hay `private`.

### 7.3. Lưu ý khi đặt main cùng tên nhưng khác tham số

Giả sử Base có `main(String[])`, Child chỉ khai báo `main()`:

~~~java
class BaseWithArgs {
    protected void main(String[] args) {
        System.out.println("Inherited args main");
    }
}

class ChildWithNoArgs extends BaseWithArgs {
    static void main() {
        System.out.println("Own no-args main");
    }
}
~~~

Biên dịch file `ChildWithNoArgs.java` chứa hai class trên:

~~~bash
javac --release 25 ChildWithNoArgs.java
java ChildWithNoArgs test
~~~

Kết quả:

~~~text
Inherited args main
~~~

Child có candidate `main()` của chính nó **và** candidate `main(String[])` kế thừa. Java 25 **ưu tiên dạng có `String[]`**, bất kể method đó có được khai báo trực tiếp trong Child hay không.

**Không kết luận:** “method main đặt trong subclass luôn thắng method main của superclass.” Lựa chọn còn phụ thuộc chữ ký và override/hide.

## 8. Kế thừa static main và khái niệm method hiding

`static` method có thể được **kế thừa** từ superclass nếu quy tắc truy cập/kế thừa cho phép, nhưng khi subclass khai báo method tĩnh **cùng signature**, ta gọi đó là **method hiding**, không phải overriding.

### 8.1. Chạy một static main kế thừa

Tệp `StaticParent.java`:

~~~java
class StaticParent {

    public static void main(String[] args) {
        System.out.println("Static parent: " + args.length);
    }
}
~~~

Tệp `StaticChild.java`:

~~~java
class StaticChild extends StaticParent {
    // Kế thừa static main
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 25 StaticParent.java StaticChild.java
java StaticChild a b
~~~

Kết quả:

~~~text
Static parent: 2
~~~

Launcher có thể dùng candidate `static main(String[])` được Child **kế thừa**. Nó gọi static method mà không cần tạo instance của `StaticChild`.

### 8.2. Child hide static main của Parent

Sửa `StaticChild.java`:

~~~java
class StaticChild extends StaticParent {

    public static void main(String[] args) {
        System.out.println("Static child: " + args.length);
    }
}
~~~

Khi chạy `java StaticChild a`:

~~~text
Static child: 1
~~~

Đó là **hiding**: không có virtual dispatch theo kiểu instance override. Cả parent và child có các static methods riêng, và việc giải quyết method tĩnh dựa theo kiểu tham chiếu ở mức Java.

Để thấy khác biệt với override, xem:

~~~java
StaticParent parentReference = new StaticChild();
parentReference.main(new String[]{"x"}); // Cú pháp hợp lệ nhưng không nên dùng
~~~

Lời gọi static thông qua biến instance **không làm static dispatch thành polymorphism**. Compiler resolve theo kiểu tĩnh của biểu thức `parentReference`, nên gọi `StaticParent.main`; trong code thực tế hãy viết `StaticParent.main(...)` để tránh gây hiểu nhầm.

### 8.3. Không thể đổi static thành instance để override cùng signature

Đoạn sau là lỗi biên dịch:

~~~java
class ParentStatic {
    static void main(String[] args) {}
}

class ChildInstance extends ParentStatic {
    void main(String[] args) {}  // Compile error
}
~~~

Ngược lại, dùng `static` để “hide” một instance method cùng signature cũng bị Java cấm. Khi thiết kế class hierarchy, hãy giữ nguyên phân loại static/instance nếu định nghĩa lại một method cùng signature.

### So sánh ngắn

| Đặc tính | Instance main | Static main |
| --- | --- | --- |
| Có thể kế thừa từ superclass? | Có, nếu Java inheritance rules cho phép | Có, nếu Java inheritance rules cho phép |
| Khi subclass định nghĩa lại cùng signature | **Override** | **Hide** |
| Có virtual dispatch? | Có | Không |
| Launcher cần tạo instance khi chọn method? | Có | Không |
| Dùng trạng thái của object qua `this`? | Có | Không |
| Method có thể là `final`? | Có, không cho override | Có, không cho hide theo quy tắc Java |

## 9. Protected và package-private ảnh hưởng đến kế thừa ra sao?

**Candidate main có quyền package-private không đồng nghĩa với việc method ấy được kế thừa qua mọi package.** Phải áp dụng các quy tắc access/inheritance của Java trước khi xét đến giao thức launcher.

### 9.1. Protected main qua hai package

Cấu trúc:

~~~text
src/
├── base/
│   └── Startup.java
└── client/
    └── Client.java
~~~

`src/base/Startup.java`:

~~~java
package base;

public class Startup {
    protected void main(String[] args) {
        System.out.println("Protected từ base: " + args.length);
    }
}
~~~

`src/client/Client.java`:

~~~java
package client;

public class Client extends base.Startup {
    // Không cần khai báo main
}
~~~

Biên dịch và chạy từ thư mục gốc ví dụ:

~~~bash
javac --release 25 -d out src/base/Startup.java src/client/Client.java
java --class-path out client.Client one two
~~~

Kết quả:

~~~text
Protected từ base: 2
~~~

`protected` cho phép một subclass ở package khác **kế thừa** method. Launcher vì thế thấy candidate trong initial class `client.Client`.

### 9.2. Package-private không tự lan sang package khác

Nếu `Startup.main` được đổi thành:

~~~java
void main(String[] args) {
    System.out.println("package-private");
}
~~~

và `Client` vẫn nằm trong `package client` thì `Client` **không kế thừa** method package-private đó theo quy tắc inheritance giữa các package khác nhau. Vì không có candidate `main` nào khác trong Client, launch sẽ thất bại.

Nếu cả Startup và Client ở **cùng package**, package-private method có thể được kế thừa và trở thành candidate khi các quy tắc còn lại thỏa mãn.

### 9.3. Private không được kế thừa

Khi superclass khai báo:

~~~java
class ParentPrivate {
    private void main(String[] args) {
        System.out.println("private parent");
    }
}
~~~

thì một class con không kế thừa `main` này. Nếu class con khai báo một `main` cùng tên/chữ ký, đó không phải override của private parent method: `private` không thuộc API kế thừa.

**Kết luận:** xét thứ tự **inheritance/access rules → candidate main rules → overload selection**. Không áp quy tắc “launcher nhìn thấy mọi method trong superclass” một cách máy móc.

## 10. main kế thừa từ default method của interface

Java 25 cho phép một **instance default method** từ interface trở thành candidate `main` nếu class triển khai interface **kế thừa** method ấy.

Tệp `Runner.java`:

~~~java
interface ProgramEntry {

    default void main(String[] args) {
        System.out.println("Interface default main: " + args.length);
    }
}

class Runner implements ProgramEntry {
    // Kế thừa default main(String[])
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 25 Runner.java
java Runner hello
~~~

Kết quả:

~~~text
Interface default main: 1
~~~

Diễn giải:

1. Interface có method mặc định `void main(String[])`, chính là **instance method**.
2. Class Runner implement interface và không override method, nên kế thừa default method.
3. Java launcher tìm candidate `main(String[])` ở Runner, tạo một Runner và gọi method mặc định.
4. Constructor mặc định không tham số của Runner đủ cho việc khởi tạo.

### 10.1. Override default main

~~~java
class Runner implements ProgramEntry {

    @Override
    public void main(String[] args) {
        System.out.println("Override trong Runner");
    }
}
~~~

Khi đó gọi `java Runner` sẽ thực thi method override của Runner. Vì interface method mặc định là `public`, method override ở class cũng phải là `public`; không được giảm quyền truy cập.

### 10.2. Static method trong interface không được kế thừa

Một interface cũng có thể khai báo static method:

~~~java
interface StaticInterface {
    static void main(String[] args) {
        System.out.println("Interface static");
    }
}

class Implementer implements StaticInterface {
}
~~~

`Implementer` **không kế thừa** `StaticInterface.main`, vì static interface methods không được inherited như instance default methods.

Nếu chạy:

~~~bash
javac --release 25 Implementer.java
java Implementer
~~~

thì launcher không tìm được main trong Implementer. Việc interface tự có static main không biến nó thành inherited main của class implement.

**Đừng nhầm hai kiểu quan hệ:** `implements SomeInterface` có thể mang theo default instance method, nhưng **không mang theo static methods của interface**.

## 11. main trong compact source file có kế thừa được không?

Một cải tiến nổi bật của Java 25 là **compact source file**: có thể viết thành viên cấp cao nhất mà không cần khai báo class tường minh.

`Hello.java`:

~~~java
String greeting(String name) {
    return "Xin chào, " + name;
}

void main(String[] args) {
    String name = args.length == 0 ? "Java 25" : args[0];
    IO.println(greeting(name));
}
~~~

Chạy:

~~~bash
java Hello.java Minh
~~~

Kết quả:

~~~text
Xin chào, Minh
~~~

Điều gì xảy ra?

- Compiler tạo một **implicitly declared class** chứa các field/method của source.
- Class ngầm định đó là **final**, thuộc unnamed package và unnamed module.
- Nó có default zero-argument constructor.
- Nó không có tên mà mã Java nguồn khác có thể tham chiếu tường minh để kế thừa; nó cũng không tự khai báo superclass tùy chọn hoặc implements interface.
- Các method cấp cao nhất vẫn có thể mang modifier thông thường; `void main` mặc định là package-private **instance method**.
- `IO.println` thuộc `java.lang.IO` trong Java 25.
- **Không cần `--enable-preview`**: compact source files/instance main đã chính thức ở JDK 25.

Vì vậy, dù cơ chế `main` của Java 25 hỗ trợ **kế thừa**, một compact source file **không phải** nơi phù hợp để xây dựng hierarchy entry point. Khi cần `extends` hoặc `implements`, hãy khai báo class tường minh.

### 11.1. Chuyển compact source thành class tường minh

Từ `Hello.java` ở trên, chuyển sang:

~~~java
class Hello {

    String greeting(String name) {
        return "Xin chào, " + name;
    }

    void main(String[] args) {
        String name = args.length == 0 ? "Java 25" : args[0];
        System.out.println(greeting(name));
    }
}
~~~

Class tường minh giờ có thể `extends` hoặc `implements` theo quy tắc Java bình thường. Không còn tự động nhận mọi tiện ích của compact source: ví dụ khi dùng kiểu ở ngoài `java.lang`, cần import rõ hoặc dùng `import module java.base;` nếu phù hợp Java 25.

### 11.2. Private main trong compact source file

Nếu chỉ có:

~~~java
private void main() {
    IO.println("Không thể làm entry point");
}
~~~

thì compact source file thiếu **launchable main**. Khác với explicit class có thể chứa private helper method cùng tên, compact source file phải có phương thức `main` đủ điều kiện để chạy; compiler có thể từ chối ngay tệp nguồn không có main phù hợp.

## 12. Các quy tắc override/hide vẫn là quy tắc Java thông thường

### 12.1. Không thể giảm mức truy cập khi override

~~~java
class Parent {
    protected void main(String[] args) {}
}

class Child extends Parent {
    // Lỗi: giảm visibility từ protected xuống package-private.
    @Override
    void main(String[] args) {}
}
~~~

Đổi method override thành `protected` hoặc `public` mới phù hợp.

### 12.2. final chặn override

~~~java
class Parent {
    public final void main(String[] args) {}
}

class Child extends Parent {
    // Không được override main(String[]) vì parent method final.
}
~~~

Child vẫn có thể **kế thừa và chạy** phương thức `final main` nếu class có constructor phù hợp. `final` chặn việc thay đổi body ở subclass, chứ không khiến inherited method hết là candidate.

### 12.3. Không thể dùng static như một cách “override nhanh”

~~~java
class Parent {
    public void main(String[] args) {}
}

class Child extends Parent {
    // Lỗi: static không thể hide instance main cùng signature.
    public static void main(String[] args) {}
}
~~~

Đó là lỗi compile-time; launcher không có cơ hội chọn method.

### 12.4. Một subclass vẫn có thể cung cấp một overload khác

~~~java
class Parent {
    protected void main(String[] args) {
        System.out.println("Parent args");
    }
}

class Child extends Parent {
    public static void main() {
        System.out.println("Child no args");
    }
}
~~~

Hai methods khác signature nên cùng tồn tại. Khi launch `Child`, dạng `String[]` kế thừa vẫn được ưu tiên. Hãy dùng tên function khác nếu cần làm rõ ý nghĩa nghiệp vụ, tránh tổ hợp overload khiến entry point khó đoán.

## 13. Cần test những gì khi dùng main trong kiến trúc có kế thừa?

Với một dự án có hierarchy hoặc nhiều dạng `main`, nên tách ba loại bài kiểm tra:

1. **Compile test:** class có hợp lệ theo Java source rules?
2. **Launch test:** Java 25 launcher có chọn được `main` và tạo instance khi cần?
3. **Behavior test:** method được chọn có xuất ra kết quả/side effect đúng?

Ví dụ một test thủ công:

~~~bash
javac --release 25 BaseProgram.java ChildProgram.java
java ChildProgram first second
~~~

Không chỉ nhìn compilation thành công: class có thể biên dịch nhưng **không có candidate main**, hoặc candidate instance không thể được khởi chạy.

### 13.1. Bảng test matrix

| Case | Class chứa main | Constructor / inheritance | Dự đoán |
| --- | --- | --- | --- |
| `public static void main(String[])` | Declared | Không cần instance | Chạy trực tiếp |
| `protected static void main()` | Declared | Không cần instance | Chạy trực tiếp |
| `void main()` | Declared | Có constructor không tham số | Tạo instance, chạy |
| `protected void main(String[])` | Declared | Có constructor không tham số | Tạo instance, chạy |
| `private void main()` | Declared | Không có main khác | Launch thất bại |
| `int main(String[])` | Declared | Không có main khác | Launch thất bại |
| `main(String[])` + `main()` | Declared | Hai signatures | Chọn `String[]` |
| Instance `main(String[])` ở superclass | Inherited | Child có zero-arg constructor | Tạo Child, gọi inherited method |
| Static `main(String[])` ở superclass | Inherited | Không cần constructor Child | Chạy inherited static method |
| Package-private main khác package | Không inherited | Child không có main khác | Launch thất bại |
| Protected main khác package | Inherited | Constructor Child hợp lệ | Chạy inherited method |
| Interface `default main(String[])` | Inherited | Class có zero-arg constructor | Chạy inherited default method |
| Interface `static main(String[])` | Không inherited vào implementer | Implementer không có main khác | Launch Implementer thất bại |
| Instance main nhưng chỉ có ctor nhận args | Declared | Không có zero-arg constructor | Compile có thể pass, launch thất bại |
| Override instance main hợp lệ | Override | Child khởi tạo được | Chạy implementation Child |
| Hide static main hợp lệ | Hide | Không cần instance | Gọi static theo initial class |

Bảng giả định không có các candidate khác gây thay đổi kết quả lựa chọn; cần kiểm tra đầy đủ class hierarchy trong tình huống thực tế.

### 13.2. Tạo script kiểm chứng đơn giản

Ví dụ Bash chạy những ca thành công đã biên dịch:

~~~bash
javac --release 25 BaseProgram.java ChildProgram.java
java ChildProgram alpha

javac --release 25 StaticParent.java StaticChild.java
java StaticChild beta

javac --release 25 Runner.java
java Runner gamma
~~~

Với Windows PowerShell, các lệnh `javac`/`java` vẫn tương tự, chỉ cần chạy từng lệnh theo thứ tự và kiểm tra `$LASTEXITCODE`. Không chạy script cùng lúc trong thư mục chứa các ví dụ có **class trùng tên** như Parent/Child từ các phần độc lập: hãy tạo thư mục bài tập riêng, hoặc chỉ giữ một cặp ví dụ đang kiểm thử.

### 13.3. Test bằng JUnit có thay thế launch test?

Không hoàn toàn. Một JUnit test gọi trực tiếp `new Child().main(args)` chỉ chứng minh behavior của Java method; nó **không chứng minh launcher chọn đúng overload hoặc chấp nhận access của candidate**.

Khi cần xác minh giao thức thực thi, hãy chạy **một tiến trình `java` riêng** trên artifact đã biên dịch, sau đó kiểm tra exit code và stdout/stderr theo hợp đồng. Điều này càng quan trọng khi nâng cấp build tool/IDE hoặc chuyển giữa nguồn chạy trực tiếp và JAR.

## 14. Sai lầm thường gặp

### 14.1. “main bắt buộc public static”

Đây từng là quy tắc của giao thức khởi chạy truyền thống; **không còn là mô tả đầy đủ cho Java 25**. `public static void main(String[] args)` vẫn là lựa chọn tốt, nhưng Java 25 cũng chấp nhận `protected`/package-private, instance method và dạng không tham số. Không được kết luận mọi `void main()` là sai.

### 14.2. “private main sẽ chạy vì JVM có reflection”

**Sai.** `private main` không phải candidate theo JLS 25. Java launcher không coi private method là điểm vào chỉ vì có thể có cơ chế reflection ở nơi khác.

### 14.3. “static main luôn được ưu tiên”

**Sai.** Java 25 ưu tiên **dạng có `String[]`** trước dạng không tham số; static/instance chỉ quyết định cách gọi method đã được chọn. Ví dụ `instance main(String[])` sẽ thắng `static main()`.

### 14.4. “Lớp con sẽ tự chạy main() của nó”

**Không chắc.** Nếu lớp con có `main()` nhưng vẫn kế thừa candidate `main(String[])`, launcher chọn dạng `String[]`. Dự đoán phải dựa trên tập candidate và thứ tự ưu tiên thực tế.

### 14.5. “protected và package-private đều được kế thừa qua package khác”

**Sai.** `protected` có thể được inherited bởi subclass khác package; package-private không được inherited qua ranh giới package như vậy. Visibility là điều kiện ngôn ngữ trước khi xét main.

### 14.6. “Static method được override theo runtime type”

**Sai.** Static method trong subclass **hide** method cùng signature của superclass; không có virtual dispatch như instance override. Gọi static qua object reference là cách viết dễ gây hiểu nhầm.

### 14.7. “Interface static main được inherited khi implements”

**Sai.** Interface static methods không inherited vào implementing class; interface `default main` có thể inherited và dùng để launch.

### 14.8. “Instance main không cần constructor”

**Sai.** Launcher phải tạo object initial class trước khi gọi. Một class chỉ có constructor nhận tham số có thể compile nhưng không launch qua instance main như mong đợi.

### 14.9. “Compact source file là class thường nên có thể extends và override”

**Sai.** Lớp ngầm định của compact source file là final và không thể được tham chiếu tường minh bằng tên trong source Java. Khi cần hierarchy, hãy chuyển sang explicit class declaration.

### 14.10. “Phải bật preview cho Java 25 instance main”

**Không còn đúng.** JEP 512 đã hoàn thiện trong Java 25. Hãy dùng JDK 25 và chạy/biên dịch theo cú pháp chính thức, không sao chép `--enable-preview` từ các hướng dẫn cho bản JDK cũ.

## 15. Cân nhắc thiết kế entry point trong chương trình hiện đại

Java 25 nới giao thức khởi chạy để đơn giản hóa chương trình nhỏ, nhưng quyền tự do đó không có nghĩa **mọi ứng dụng nên kế thừa main từ superclass**.

### Khi nên dùng instance main

- Chương trình ngắn cần truy cập field/helper method instance trực tiếp.
- Ví dụ giảng dạy Java cơ bản hoặc CLI nhỏ.
- Một explicit class đơn giản có trạng thái khởi tạo bằng zero-arg constructor.
- Một chương trình compact source file có `void main()` hoặc `void main(String[])`.

### Khi nên tiếp tục dùng public static main(String[])

- Ứng dụng có entry point công khai, dễ nhận diện qua IDE/build tooling.
- Launcher framework sử dụng convention quen thuộc, ví dụ ứng dụng Spring Boot.
- Muốn thể hiện rõ việc bootstrap nằm ở class và không phụ thuộc constructor.
- Cần thuận tiện khi bàn giao artifact JAR hoặc Java module có main class.

### Khi nên tránh kế thừa main

- Hierarchy được tạo chỉ nhằm tái sử dụng entry point mà không có ý nghĩa mô hình domain.
- Code có nhiều inherited/overloaded mains khiến launcher chọn khó đoán.
- Các module triển khai độc lập cần điểm vào tường minh, dễ bảo trì và debug.
- Khi muốn có bootstrap logic chung: thường tốt hơn tách thành **một service/helper** rồi gọi từ entry point rõ ràng.

**Nguyên tắc:** coi `main` là **điểm bắt đầu vòng đời ứng dụng**. Khả năng override/inherit là tính năng Java hợp lệ, nhưng không nên biến nó thành một kiến trúc thừa kế phức tạp chỉ để tiết kiệm vài dòng code khởi chạy.

## 16. Bài tập thực hành

### Bài tập 1 — ba mức truy cập hợp lệ

Viết ba class độc lập với `public`, `protected` và package-private `main`. Đối với mỗi class, thử một static và một instance version. Chạy bằng JDK 25, ghi lại stdout và giải thích vì sao `private` không được launcher chấp nhận.

**Tiêu chí đạt:** có thể gọi đủ 6 trường hợp và giải thích đúng quyền truy cập.

### Bài tập 2 — ưu tiên giữa hai overload

Tạo class có `static void main()` và `void main(String[])`. Chạy với 0 và 2 tham số, xem method nào được chọn. Đổi chỗ source code của hai method và chạy lại.

**Tiêu chí đạt:** kết quả không đổi theo vị trí khai báo; dạng `String[]` luôn được ưu tiên nếu đủ điều kiện.

### Bài tập 3 — kế thừa từ superclass

Tạo `Base` với `protected void main(String[])`; `Child` không khai báo main. Chạy `Child` rồi override method ở Child. Quan sát kết quả trước/sau khi thêm `@Override`.

**Tiêu chí đạt:** giải thích được launcher tạo instance **Child** và virtual dispatch theo method override.

### Bài tập 4 — static hiding

Tạo Parent/Child có inherited static `main(String[])`, sau đó khai báo static main cùng signature ở Child. Giải thích sự khác nhau giữa hiding và overriding.

**Tiêu chí đạt:** phân biệt được method theo class, không nhầm với virtual dispatch.

### Bài tập 5 — package boundary

Chuyển `Parent` và `Child` sang hai package khác nhau. Thử `protected main` rồi đổi sang package-private.

**Tiêu chí đạt:** giải thích được vì sao trường hợp protected có thể được inherited còn package-private không qua package khác.

### Bài tập 6 — interface default main

Tạo interface có `default void main(String[])`; class implement không khai báo main. Chạy class rồi override method. Thử thay bằng `static main` trong interface.

**Tiêu chí đạt:** phân biệt được default instance method inherited với static interface method không inherited.

### Bài tập 7 — compact source file

Tạo `Hello.java` chỉ có `void main()` và helper method, chạy `java Hello.java`. Chuyển sang class tường minh, thêm `extends`/`implements` và kiểm chứng main ở class con.

**Tiêu chí đạt:** biết tại sao class ngầm định không phù hợp cho kế thừa, nhưng instance main vẫn dùng được trong explicit class.

### Checklist đánh giá cuối bài

- [ ] Hiểu candidate main cần `void`, 0 tham số hoặc đúng một `String[]`.
- [ ] Biết `public`/`protected`/package-private hợp lệ và `private` không hợp lệ cho entry point.
- [ ] Phân biệt phương thức static với instance và nhu cầu zero-argument constructor.
- [ ] Dự đoán đúng khi có cả `main(String[])` và `main()`.
- [ ] Hiểu static main có thể được kế thừa từ superclass và bị hide.
- [ ] Hiểu instance main có thể được kế thừa và override.
- [ ] Hiểu `protected`/package-private/private ảnh hưởng đến inheritance qua package.
- [ ] Biết default main của interface có thể inherited, còn interface static method không.
- [ ] Biết compact source file của Java 25 không cần preview và không tạo hierarchy riêng.
- [ ] Có test compile, test launcher và test output cho các case quan trọng.
- [ ] Chỉ sử dụng JDK 25/Java SE 25 rules, không dựa vào tài liệu preview lỗi thời.

## 17. Tài liệu tham khảo chính thức

1. [Java Language Specification, Java SE 25 — `12.1.4 Invoke a main Method](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.1.4): định nghĩa candidate, lựa chọn overload và inherited main.
2. [Java 25 Language Guide — Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): instance main, compact source và cách chạy chương trình.
3. [JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512): thay đổi đã chính thức trong JDK 25.
4. [Java Language Specification, Java SE 25 — `8.4.8 Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8): quy tắc kế thừa, override và hide methods.
5. [Java Language Specification, Java SE 25 — `9.4 Interface Methods](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4): default/static interface methods.
6. [Java 25 — java Launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): chạy source file, class và module.

**Kết quả mong đợi:** người học có thể xác định một `main` có thực sự là entry point của Java 25 hay không, dự đoán chính xác cách launcher chọn method khi có overload/kế thừa, phân biệt override và static hiding, cũng như lý giải các lỗi chỉ xuất hiện ở thời điểm launch. Đây là nền tảng còn áp dụng cho ứng dụng Java hiện đại khi dùng chương trình nguồn gọn hoặc class tường minh trong dự án lớn.
