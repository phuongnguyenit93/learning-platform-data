# Thứ tự trường `static` và khối `static` theo văn bản nguồn trong Java

Trong Java, một class có thể khai báo nhiều **trường static (static fields)** xen kẽ với **khối khởi tạo static (`static { ... }`)**. Khi class được khởi tạo, Java thực hiện các field initializers và static blocks theo **thứ tự xuất hiện trong văn bản nguồn**, nhưng còn một số quy tắc nền tảng cần hiểu trước: giá trị mặc định, constant variables, giới hạn forward reference, class initialization trigger và thứ tự giữa superclass–subclass.

Ví dụ:

~~~java
class Settings {
    static int first = 2;

    static {
        System.out.println("block 1: " + first);
    }

    static int second = first + 3;

    static {
        System.out.println("block 2: " + second);
    }
}
~~~

Khi `Settings` được **khởi tạo thực sự**, trường `first` được gán 2; block thứ nhất thấy 2; trường `second` nhận 5; block thứ hai thấy 5. Tuy nhiên, chỉ **khai báo** class không đồng nghĩa static blocks sẽ chạy ngay; mã phải kích hoạt quá trình khởi tạo class.

Mục tiêu bài: phân tích đúng **“field initializer nào chạy trước, block nào chạy sau, tại thời điểm đọc một field đã nhận giá trị mới chưa?”** thay vì nhớ máy móc “static chạy đầu tiên”.

Nội dung thuộc Java Core — **Class & Object / Thứ tự khởi tạo**, sử dụng Java 17+. Các chương trình đầy đủ có file name, `javac`, `java` và stdout. Các đoạn cố ý không biên dịch được đánh dấu riêng.

## 1. Kết quả cần đạt

Sau bài này, bạn cần có khả năng:

1. Phân biệt **class loading, linking/preparation và initialization** ở mức đủ dùng để đọc static code.
2. Hiểu static field thông thường có **giá trị mặc định** trước khi initializer gán giá trị tường minh.
3. Mô tả **thứ tự từ trên xuống dưới** của static field initializers và `static { ... }` trong cùng class.
4. Biết mỗi class runtime được khởi tạo theo quy tắc Java, không chạy lại static initializer khi tạo thêm mỗi instance.
5. Dự đoán stdout của những chương trình in log ở nhiều static fields/blocks.
6. Giải thích lúc nào compiler báo **illegal forward reference**.
7. Phân biệt field được truy cập qua **simple name**, qua **qualified name** và qua **method**.
8. Hiểu tại sao method có thể đọc field khai báo sau nó và nhìn thấy **giá trị mặc định**.
9. Phân biệt **constant variable** (`static final` primitive/String có constant expression) với các static final fields khác.
10. Hiểu vì sao đọc compile-time constant không nhất thiết kích hoạt class initialization.
11. Theo dõi thứ tự giữa **superclass và subclass**, cũng như giữa static và instance initializers.
12. Đọc lỗi khởi tạo static, tránh circular initialization và side effects không mong muốn.
13. Biết static blocks/fields phù hợp lúc nào, nên tách sang factory hoặc lazy initialization khi nào.
14. Kiểm thử các tình huống khởi tạo dựa trên semantics thay vì phụ thuộc môi trường IDE.

## 2. Phân biệt bốn khái niệm dễ bị gộp

| Khái niệm | Ý nghĩa chính | Có chạy static initializer không? |
| --- | --- | --- |
| **Loading** | JVM tìm và tạo representation của class/interface | Không phải mặc định đồng nghĩa đã chạy |
| **Linking / preparation** | Kiểm tra, chuẩn bị class variables; đặt giá trị chuẩn bị theo quy tắc VM | Không phải giai đoạn chạy lần lượt các static blocks |
| **Initialization** | Thực thi class initialization procedure; các field initializers/static blocks theo ngữ nghĩa Java | **Có**, đây là giai đoạn trọng tâm |
| **Instance initialization** | Chuẩn bị và khởi tạo từng object cụ thể khi tạo instance | Không phải static initializer chạy lại |

Cách nói “JVM vừa gặp tên class là static block chạy ngay” **không chính xác**. JVM có thể load/link class trước mà chưa initialize. Ngược lại, có những hành vi chủ động sử dụng class khiến initialization bắt buộc xảy ra trước khi tiếp tục.

### Quy tắc quan trọng

> Trong một class, sau các xử lý đặc biệt dành cho **constant variables**, Java thực thi các static field initializers và static initializer blocks theo **textual order** của khai báo trong source code.

Sự khác nhau giữa giai đoạn chuẩn bị field và lúc chạy initializer giải thích vì sao một static field được đọc quá sớm có thể còn giữ **default value**. Nhưng không được khẳng định mọi static final compile-time constant cũng chỉ có 0/null cho tới đúng dòng khai báo của nó: **constant variables có quy tắc khởi tạo riêng**.

## 3. Cú pháp static field initializer và static initializer block

Một static field có thể được khởi tạo ngay trong khai báo:

~~~java
class AppConfig {
    static int maxUsers = 100;
    static String mode = "development";
}
~~~

Một static initializer block:

~~~java
class AppConfig {
    static int maxUsers;

    static {
        maxUsers = 100;
        System.out.println("AppConfig initialized");
    }
}
~~~

Đây là **hai class minh họa ở hai phương án độc lập**, không ghép hai đoạn thành cùng một khai báo `AppConfig`.

Block `static { ... }` là code được thực thi trong **quá trình khởi tạo class**, không phải một method có tên. Nó không nhận parameters, không có return value, và không thể dùng `this` của một instance.

Một class có thể có **nhiều static blocks**, xen giữa nhiều static field declarations. Trong cùng class, **vị trí theo source** quyết định thứ tự chạy của các initializer thuộc quá trình khởi tạo thường.

## 4. Quy tắc quan trọng nhất: xen kẽ theo văn bản nguồn

Xem class minh họa:

~~~java
class Demo {
    static int a = 1;

    static {
        System.out.println("A=" + a);
    }

    static int b = a + 2;

    static {
        System.out.println("B=" + b);
        b += 5;
    }

    static int c = b * 2;
}
~~~

Thứ tự:

1. Initializer `a = 1`.
2. Static block thứ nhất đọc `a` và in `A=1`.
3. Initializer `b = a + 2`, cho `b = 3`.
4. Static block thứ hai in `B=3`, rồi cập nhật `b = 8`.
5. Initializer `c = b * 2`, cho `c = 16`.

Không phải JVM chạy **toàn bộ các field initializers trước**, rồi mới chạy **toàn bộ static blocks**. Nếu làm thế, kết quả sẽ khác; Java dùng thứ tự nguồn khi thực hiện những khai báo static thông thường ấy.

**Hỏi đúng:** “Dòng này có nằm trước hay sau static block nào trong source?” và “Class đã thực sự được initialize ở mốc nào?”

## 5. Ví dụ chạy đầy đủ: log từng static initializer

Tạo file **`StaticTextualOrderDemo.java`**:

~~~java
public class StaticTextualOrderDemo {
    static class Sample {
        static int alpha = mark("field alpha", 3);

        static {
            System.out.println("block 1: alpha=" + alpha);
            alpha += 2;
        }

        static int beta = mark("field beta", alpha * 2);

        static {
            System.out.println("block 2: beta=" + beta);
            beta++;
        }

        static int gamma = mark("field gamma", beta + alpha);

        static int mark(String label, int value) {
            System.out.println(label + "=" + value);
            return value;
        }
    }

    public static void main(String[] args) {
        System.out.println("main begins");
        System.out.println("gamma=" + Sample.gamma);
        System.out.println("alpha=" + Sample.alpha);
        System.out.println("beta=" + Sample.beta);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StaticTextualOrderDemo.java
java StaticTextualOrderDemo
~~~

Stdout:

~~~text
main begins
field alpha=3
block 1: alpha=3
field beta=10
block 2: beta=10
field gamma=16
gamma=16
alpha=5
beta=11
~~~

### Lập bảng sau từng mốc

| Mốc trong `Sample` | `alpha` | `beta` | `gamma` | Hành động |
| --- | ---: | ---: | ---: | --- |
| Default của static ints | 0 | 0 | 0 | Giá trị ban đầu trước các initializer thường |
| `alpha = mark(...,3)` | 3 | 0 | 0 | In `field alpha=3` |
| Block 1 | 5 | 0 | 0 | In alpha=3, cộng 2 |
| `beta = mark(...,alpha*2)` | 5 | 10 | 0 | In `field beta=10` |
| Block 2 | 5 | 11 | 0 | In beta=10, rồi ++ |
| `gamma = mark(...,beta+alpha)` | 5 | 11 | 16 | In `field gamma=16` |
| Sau khởi tạo | 5 | 11 | 16 | Main in ba giá trị |

Tại đầu `main`, nested class `Sample` chưa cần phải được initialize; lệnh in `main begins` chạy trước. Khi biểu thức `Sample.gamma` được sử dụng, Java khởi tạo `Sample` và chạy toàn bộ chuỗi log theo thứ tự. Đọc `Sample.alpha`/`beta` **sau đó** không khiến static code chạy lại.

Method `mark` **có thể được khai báo ở cuối class** và vẫn được gọi trong initializer ở đầu; khác biệt giữa forward reference của **field** và việc gọi **method** sẽ được giải thích kỹ bên dưới.

## 6. Giá trị mặc định trước khi gán giá trị tường minh

Class variables là fields, nên có các **default values** theo kiểu dữ liệu khi được chuẩn bị theo quy tắc Java/JVM:

| Field type | Giá trị mặc định thông thường |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` tương ứng kiểu |
| `float`, `double` | số không dấu dương theo kiểu |
| `char` | ký tự NUL `'\\u0000'` |
| `boolean` | `false` |
| Các reference types như `String`, `List`, mảng | `null` |

Ví dụ:

~~~java
class Settings {
    static int count;
    static boolean enabled;
    static String title;
}
~~~

Nếu không có initializer hay phép gán khác, sau class initialization thông thường: `count == 0`, `enabled == false`, `title == null`.

**Phân biệt:** Local variable trong method **không** được tự động đọc giá trị mặc định tương tự nếu chưa definite-assigned. Ví dụ local `int n; System.out.println(n);` là lỗi biên dịch.

### Ngoại lệ đặc biệt dành cho constant variables

Một `static final int LIMIT = 10;` được khởi tạo bằng constant expression thuộc nhóm **constant variables**. Java xử lý nhóm này trước các static initializers thông thường; việc đọc chúng không nên được diễn giải như “chắc chắn thấy 0 cho tới dòng LIMIT trong source”. Vì vậy bảng default values hữu ích nhất khi phân tích **non-constant static fields**.

## 7. Class initialization chạy một lần trong điều kiện bình thường

Xét:

~~~java
class Gateway {
    static int requests = 0;

    static {
        System.out.println("Gateway initialized");
    }

    Gateway() {
        requests++;
    }
}
~~~

Sau:

~~~java
Gateway a = new Gateway();
Gateway b = new Gateway();
~~~

Hai lần `new` gọi constructor của hai instances, nên field static `requests` tăng hai lần. Nhưng static block **không** chạy lại cho mỗi object. Trong một class runtime đã khởi tạo thành công, initialization procedure không được thực hiện lại bởi những lần tạo object tiếp theo.

### Đừng suy luận “static có đời sống vĩnh viễn”

Một class runtime có thể có lifecycle liên quan class loader và môi trường ứng dụng; hai class có cùng tên được định nghĩa bởi class loaders khác nhau có thể có static states riêng. Với chương trình một JVM nhỏ dùng class loader thông thường, mô hình “static initializer chạy một lần cho class này” là đủ.

## 8. Ví dụ chạy: static block và constructor khác nhau

Lưu file **`StaticVersusInstanceDemo.java`**:

~~~java
public class StaticVersusInstanceDemo {
    static class Gadget {
        static int nextId = 1;

        static {
            System.out.println("Gadget static block");
        }

        final int id;

        {
            System.out.println("Gadget instance block");
        }

        Gadget() {
            id = nextId++;
            System.out.println("constructor id=" + id);
        }
    }

    public static void main(String[] args) {
        System.out.println("start");
        new Gadget();
        new Gadget();
        System.out.println("nextId=" + Gadget.nextId);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticVersusInstanceDemo.java
java StaticVersusInstanceDemo
~~~

Stdout:

~~~text
start
Gadget static block
Gadget instance block
constructor id=1
Gadget instance block
constructor id=2
nextId=3
~~~

- `nextId` static field initializer chạy khi Gadget được initialize lần đầu.
- Static block in đúng **một lần**.
- Instance initializer block chạy **mỗi lần tạo Gadget**.
- Constructor body cũng chạy cho **mỗi Gadget instance**.
- Đọc static `Gadget.nextId` cuối cùng không chạy lại static block.

Cả field static và khối static đều thuộc quá trình **class initialization**; field instance và non-static initializer block thuộc quá trình **instance initialization**. Hai khái niệm này không hoán đổi cho nhau.

## 9. Illegal forward reference: vì sao không đọc field phía sau bằng tên đơn?

Thử khai báo:

~~~java
class Invalid {
    // static int earlier = later; // Lỗi: illegal forward reference.
    static int later = 10;
}
~~~

Nếu bỏ comment, compiler từ chối vì trong **static field initializer của cùng class**, một **simple name** `later` tham chiếu tới field được khai báo **sau** vị trí đọc và không thuộc ngoại lệ cho phép.

Tương tự:

~~~java
class Invalid {
    static {
        // System.out.println(later); // Lỗi: illegal forward reference.
    }

    static int later = 10;
}
~~~

Dòng cố ý sai nằm trong comment để các snippets còn lại hợp lệ.

### Tại sao Java giới hạn điều này?

Nếu cho đọc trực tiếp mọi field khai báo phía sau, người viết dễ tưởng initializer của field ấy đã chạy. Thực tế, việc đọc có thể thấy giá trị mặc định. Quy tắc hạn chế **simple-name forward reference trong một số static initialization contexts** nhằm tránh lỗi vô tình, dù không chặn mọi cách đọc gián tiếp.

**Đừng học mẹo “Java cấm nhắc tới bất cứ member nào khai báo ở dưới”.** Java cho phép gọi method khai báo dưới, và một số cách tham chiếu field bằng qualified name vẫn hợp lệ.

## 10. Phân biệt simple name và qualified name

Một điểm nâng cao nhưng rất hữu ích:

~~~java
class QualifiedExample {
    static int observed = QualifiedExample.later;
    static int later = 10;
}
~~~

Ở initializer của `observed`, biểu thức `QualifiedExample.later` là **qualified name**. Nó khác `later` là simple name trong quy tắc illegal forward reference đang xét.

Ví dụ này có thể biên dịch. Khi `observed` được khởi tạo, `later` **chưa chạy initializer `= 10`**, nên việc đọc non-constant `later` ở đây cho `0`. Sau đó initializer `later = 10` chạy.

### Ví dụ chạy

Tạo file **`QualifiedForwardReadDemo.java`**:

~~~java
public class QualifiedForwardReadDemo {
    static class Example {
        static int observed = Example.later;
        static int later = 10;

        static {
            System.out.println("observed=" + observed);
            System.out.println("later=" + later);
        }
    }

    public static void main(String[] args) {
        System.out.println("main=" + Example.later);
    }
}
~~~

~~~bash
javac -encoding UTF-8 QualifiedForwardReadDemo.java
java QualifiedForwardReadDemo
~~~

Stdout:

~~~text
observed=0
later=10
main=10
~~~

**Quan trọng:** Mã này biên dịch được không có nghĩa nên viết như vậy trong ứng dụng thật. Nó tạo một phụ thuộc nhạy cảm với thứ tự khai báo và có thể khiến người đọc bất ngờ. Nên **đặt initializer của dependency phía trên nơi sử dụng**, hoặc thiết kế explicit initialization khi logic phức tạp.

## 11. Method được gọi từ initializer có thể đọc field khai báo sau

Quy tắc simple-name forward reference xét vị trí của **biểu thức field access** trong initializer. Nếu initializer **gọi một method**, còn method đọc field, việc đó có thể hợp lệ về cú pháp vì việc đọc nằm trong **method body**, không phải trực tiếp trong initializer theo điều kiện bị cấm.

Ví dụ:

~~~java
class Indirect {
    static int observed = readLater();
    static int later = 10;

    static int readLater() {
        return later;
    }
}
~~~

Method `readLater()` đã được khai báo và có thể gọi khi `observed` được khởi tạo. Nhưng tại thời điểm đó, `later` vẫn chưa được gán 10 theo textual order, nên method nhận **giá trị mặc định 0**.

Điều này tạo một “bẫy hợp lệ nhưng nguy hiểm”: code **không lỗi compile**, nhưng giá trị có thể khác kỳ vọng.

### Ví dụ chạy

Lưu file **`MethodForwardReadDemo.java`**:

~~~java
public class MethodForwardReadDemo {
    static class Example {
        static int observed = readLater();

        static int later = 10;

        static int readLater() {
            System.out.println("inside method later=" + later);
            return later;
        }

        static {
            System.out.println("observed=" + observed);
            System.out.println("later=" + later);
        }
    }

    public static void main(String[] args) {
        System.out.println("final observed=" + Example.observed);
    }
}
~~~

~~~bash
javac -encoding UTF-8 MethodForwardReadDemo.java
java MethodForwardReadDemo
~~~

Stdout:

~~~text
inside method later=0
observed=0
later=10
final observed=0
~~~

Phân tích:

1. Class `Example` bắt đầu initialization; các static ints thông thường có giá trị mặc định 0.
2. `observed = readLater()` gọi method.
3. Method đọc `later` khi initializer `later = 10` chưa chạy, nên in 0 và trả 0.
4. Sau đó `later = 10`.
5. Static block in `observed=0` và `later=10`.
6. Đọc `Example.observed` sau khởi tạo vẫn là 0; nó **không tự tính lại**.

Không nên dùng cách này để “né” compiler kiểm tra illegal forward reference trong code sản phẩm. Nếu code có nghĩa là observed phải bằng later=10, hãy sắp xếp dependency đúng thứ tự hoặc viết phép khởi tạo trực tiếp, rõ ràng.

## 12. Giá trị mặc định khi static field chưa đến lượt khởi tạo

Trong một chương trình nhiều fields, lập bảng theo ba trạng thái:

1. **Default:** field đã có giá trị chuẩn bị theo quy tắc VM nhưng initializer thông thường chưa chạy.
2. **Initialized:** initializer của field đã chạy và hoàn tất.
3. **Mutated:** static block/method khác có thể thay đổi field sau đó.

Ví dụ:

~~~java
class State {
    static int first = 3;
    static int second = first * 2;

    static {
        first = 10;
    }

    static int third = first + second;
}
~~~

Kết quả:

| Mốc | first | second | third |
| --- | ---: | ---: | ---: |
| Trước initializer thường | 0 | 0 | 0 |
| `first = 3` | 3 | 0 | 0 |
| `second = first * 2` | 3 | 6 | 0 |
| Static block | 10 | 6 | 0 |
| `third = first + second` | 10 | 6 | 16 |

Điều dễ bỏ sót là `second` **không tự tính lại** khi `first` đổi thành 10. Field initializer là **một hành động gán tại một thời điểm**, không phải một công thức spreadsheet liên tục phụ thuộc `first`.

## 13. Static block có thể gán lại static field phía trên

Một static field không final có thể được sửa nhiều lần trong các static blocks:

~~~java
class Flags {
    static String mode = "default";

    static {
        mode = "ready";
    }

    static {
        mode = mode.toUpperCase();
    }
}
~~~

Sau class initialization thành công, `Flags.mode` là `"READY"`. Không có “bản riêng” cho mỗi block: cả hai blocks và initializer cùng thao tác trên **cùng static field**.

Tuy nhiên `final` field có quy tắc assignment nghiêm ngặt. Bạn không thể khởi tạo field final rồi tùy ý gán lại trong block tiếp theo:

~~~java
class InvalidFinal {
    static final int LIMIT = 10;

    static {
        // LIMIT = 20; // Không hợp lệ: final field đã được gán.
    }
}
~~~

## 14. Blank `static final` có thể được gán trong static block

Một **blank static final field** là static final field không có initializer trực tiếp tại khai báo:

~~~java
class Tokens {
    static final String PREFIX;

    static {
        PREFIX = "ID-";
    }
}
~~~

Trong ngữ cảnh constructor không có ý nghĩa cho static final field, vì field thuộc class chứ không thuộc instance. Hãy thiết lập blank static final theo **quy tắc definite assignment** trong quá trình static initialization, thường ngay tại một static block.

### Ví dụ chạy với nhiều static blocks

Tạo file **`BlankStaticFinalDemo.java`**:

~~~java
public class BlankStaticFinalDemo {
    static class TokenConfig {
        static final String PREFIX;

        static {
            PREFIX = "ID-";
            System.out.println("prefix assigned");
        }

        static int number = 5;

        static {
            System.out.println("second block: " + PREFIX + number);
        }
    }

    public static void main(String[] args) {
        System.out.println("result=" + TokenConfig.PREFIX + "42");
    }
}
~~~

~~~bash
javac -encoding UTF-8 BlankStaticFinalDemo.java
java BlankStaticFinalDemo
~~~

Stdout:

~~~text
prefix assigned
second block: ID-5
result=ID-42
~~~

`PREFIX` được gán một lần trong static block đầu tiên. `number = 5` chạy sau block đó và trước static block thứ hai. `PREFIX` không phải compile-time constant variable trong ví dụ này vì không có constant-expression initializer ngay tại field declaration; do đó truy cập nó từ main kích hoạt initialization.

**Điểm cần nhớ:** Blank static final field có thể gán trong initializer block hợp lệ, nhưng không thể để một đường khởi tạo đọc nó trước definite assignment hoặc gán lần hai. Đừng dùng blank final như mutable state.

## 15. `static final` constant variable có quy tắc riêng

Ví dụ:

~~~java
class Limits {
    static final int MAX = 10;
    static final String PREFIX = "X-";
}
~~~

Hai fields này là những ứng viên **constant variables**: final field của kiểu primitive hoặc String, được khởi tạo bằng **constant expressions**.

Chúng có một số khác biệt:

- Các constant variables được khởi tạo trước các static initializers thông thường trong quá trình class initialization theo quy tắc Java.
- Đọc constant variable từ class khác **không nhất thiết kích hoạt** initialization của class khai báo.
- Compiler có thể **inline** giá trị khi biên dịch client.
- Có thể xuất hiện rủi ro phiên bản cũ của constant trong bytecode client không được recompile.

Ngược lại:

~~~java
static final Integer BOXED = Integer.valueOf(10);
static final int COMPUTED = compute();
static final java.time.Duration TIMEOUT =
        java.time.Duration.ofSeconds(5);
~~~

không phải constant variables theo cùng quy tắc chỉ vì có `static final`: Integer/Duration là reference objects (không phải String constant variable), và method call `compute()` không phải constant expression.

## 16. Ví dụ chạy: constant có thể không kích hoạt static block

Tạo file **`ConstantInitializationDemo.java`**:

~~~java
public class ConstantInitializationDemo {
    static class Config {
        static final int LIMIT = 10;
        static final String LABEL = "Java";
        static final Integer BOXED = Integer.valueOf(20);

        static {
            System.out.println("Config static block");
        }
    }

    public static void main(String[] args) {
        System.out.println("limit=" + Config.LIMIT);
        System.out.println("label=" + Config.LABEL);
        System.out.println("boxed=" + Config.BOXED);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstantInitializationDemo.java
java ConstantInitializationDemo
~~~

Stdout:

~~~text
limit=10
label=Java
Config static block
boxed=20
~~~

Hai dòng đầu dùng compile-time constant variables `LIMIT` và `LABEL`. Trong chương trình này, chỉ đọc chúng không khiến `Config` chạy static block. Khi đọc `BOXED` — không phải constant variable — class `Config` được initialize và in `Config static block` trước dòng `boxed=20`.

**Sai lầm thường gặp:** “Bất cứ khi nào gặp `ClassName.FIELD`, Java chạy static block”. Điều đó không đúng với những trường hợp constant variable được sử dụng như trên.

## 17. Constant variable có thể được đọc sớm mà vẫn mang giá trị hằng

Trong phần về forward reads, non-constant static int thường cho giá trị mặc định khi initializer phía sau chưa chạy. Nhưng **constant variables là trường hợp khác**.

Ví dụ:

~~~java
class Example {
    static int observed = readConstant();
    static final int LIMIT = 7;

    static int readConstant() {
        return LIMIT;
    }
}
~~~

`LIMIT` là compile-time constant variable. Việc đọc `LIMIT` trong method có thể được biên dịch như dùng giá trị 7; không giống việc đọc một static field thường chưa chạy initializer.

Tại thời điểm class initialization, Java xử lý constant variables trước những static field initializers thông thường, nên không được áp dụng máy móc suy luận “field nằm phía dưới chắc chắn vẫn bằng 0” cho `LIMIT`.

### Ví dụ chạy

Lưu **`ConstantForwardReadDemo.java`**:

~~~java
public class ConstantForwardReadDemo {
    static class Example {
        static int observed = readConstant();
        static final int LIMIT = 7;

        static int readConstant() {
            return LIMIT;
        }

        static {
            System.out.println("observed=" + observed);
            System.out.println("LIMIT=" + LIMIT);
        }
    }

    public static void main(String[] args) {
        System.out.println("main=" + Example.observed);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstantForwardReadDemo.java
java ConstantForwardReadDemo
~~~

Stdout:

~~~text
observed=7
LIMIT=7
main=7
~~~

Trong đoạn này, `readConstant()` được gọi trước dòng khai báo LIMIT theo thứ tự initializer thông thường, nhưng constant variable có giá trị 7. Kết quả khác với ví dụ `readLater()` đọc **non-constant static field** chưa đến lượt initializer và thấy 0.

**Phân biệt kỹ:** Việc đọc constant value này không đồng nghĩa method `readConstant()` không bao giờ có thể liên quan class initialization trong mọi ngữ cảnh; ở ví dụ, initialization đã được kích hoạt do `Example.observed` trong main.

## 18. Chỉ khai báo static field không có initializer thì sao?

Nếu viết:

~~~java
class Counters {
    static int hits;
    static String latest;
}
~~~

thì không có field initializer tường minh để chạy riêng cho `hits` hay `latest`. Các fields được đặt giá trị mặc định theo quy tắc VM và giữ như vậy cho đến khi code có phép gán sau đó.

`Counters.hits` có thể được đọc là 0 và `Counters.latest` là null khi class được sử dụng thông thường.

Thêm một static block:

~~~java
class Counters {
    static int hits;

    static {
        hits = 1;
    }
}
~~~

thì sau khởi tạo thành công, `hits == 1`. Nếu có code khác cập nhật `hits` sau đó, giá trị thay đổi — textual initialization order chỉ giải thích **giai đoạn khởi tạo**, không đóng băng static field suốt đời.

## 19. Thứ tự khai báo và thứ tự method: không đánh đồng

So sánh:

~~~java
class Example {
    static int x = calculate();

    static int calculate() {
        return 5;
    }
}
~~~

Hợp lệ. Việc gọi method `calculate()` trước vị trí method declaration trong source **không gây** illegal forward reference như đọc simple-name field quá sớm.

Trong Java, method declarations không vận hành như “script phải định nghĩa function trước khi gọi” theo thứ tự dòng; compiler biết chữ ký method của class. Nhưng **thời điểm method được gọi** vẫn rất quan trọng: nếu method đọc một static field chưa được gán initializer tường minh, nó có thể thấy default value.

### Method body chạy khi nào?

~~~java
static int a = method();

static int method() {
    System.out.println("method executed");
    return 3;
}
~~~

Method `method` chạy **ngay tại lúc initializer `a = method()` được thực thi**, không phải lúc compiler đọc method declaration. Thứ tự **thực thi** xuất phát từ lời gọi ở initializer.

## 20. Khi static initializer tác động tới field phía sau

Không chỉ đọc sớm; static block có thể **ghi** một field được khai báo phía dưới, tùy quy tắc forward-reference/assignment áp dụng.

Ví dụ:

~~~java
class Example {
    static {
        future = 4;
    }

    static int future = 9;
}
~~~

Việc gán simple-name `future` ở vế trái assignment có một ngoại lệ trong forward-reference rule; đoạn minh họa này có thể biên dịch. Nhưng sau block, initializer `future = 9` chạy và **ghi đè** giá trị 4. Do đó giá trị cuối là 9, không phải 4.

### Chương trình chạy

Tạo file **`ForwardWriteDemo.java`**:

~~~java
public class ForwardWriteDemo {
    static class Example {
        static {
            future = 4;
            System.out.println("assigned future in block");
        }

        static int future = 9;

        static {
            System.out.println("later future=" + future);
        }
    }

    public static void main(String[] args) {
        System.out.println("final=" + Example.future);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForwardWriteDemo.java
java ForwardWriteDemo
~~~

Stdout:

~~~text
assigned future in block
later future=9
final=9
~~~

**Lưu ý:** Không nên dùng “ghi trước, initializer phía dưới ghi đè” như một thiết kế có chủ đích. Đây là ví dụ cơ chế forward assignment. Nếu logic yêu cầu thứ tự rõ, viết initializer theo một chiều phụ thuộc dễ hiểu.

## 21. Khi nào class được initialize?

Một class hoặc interface không phải lúc nào cũng được initialize chỉ vì JVM đã load nó. Các hành vi chủ động sử dụng class thường có thể kích hoạt initialization, ví dụ:

- Tạo instance bằng `new ClassName()`.
- Gọi một static method do class khai báo.
- Đọc/ghi một static field do class khai báo, trừ trường hợp constant variable đặc biệt.
- Những tình huống reflective invocation hay sử dụng class theo cơ chế VM quy định.

Để đo lường thứ tự trong ví dụ, nên đặt class có static blocks thành **nested static class** hoặc class riêng, rồi kích hoạt ở một dòng được kiểm soát từ `main`.

### Ví dụ nào dễ gây hiểu lầm?

Nếu file có:

~~~java
public class Main {
    static {
        System.out.println("Main initialized");
    }

    public static void main(String[] args) {
        System.out.println("main called");
    }
}
~~~

Static block của **chính Main** chạy trước body `main`, vì class Main phải được initialize để gọi main trong điều kiện thực thi bình thường. Nhưng điều đó **không có nghĩa mọi class được nhắc tới trong source Main đều đã chạy static blocks**.

## 22. Ví dụ chạy: không nhầm khởi tạo main class với nested class

Lưu **`MainAndNestedInitDemo.java`**:

~~~java
public class MainAndNestedInitDemo {
    static {
        System.out.println("outer init");
    }

    static class Nested {
        static {
            System.out.println("nested init");
        }

        static int value = 42;
    }

    public static void main(String[] args) {
        System.out.println("main body");
        System.out.println("nested value=" + Nested.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 MainAndNestedInitDemo.java
java MainAndNestedInitDemo
~~~

Stdout:

~~~text
outer init
main body
nested init
nested value=42
~~~

Giải thích:

1. Main class phải được initialize để thực thi `main`, nên in `outer init`.
2. Body `main` bắt đầu, in `main body`.
3. Đọc `Nested.value` (non-constant static int) yêu cầu initialize `Nested`, làm in `nested init`.
4. Sau đó expression đọc giá trị 42 và in `nested value=42`.

Không có quan hệ “mọi static nested class tự initialize cùng lúc với outer”. Mỗi nested class là class runtime có initialization lifecycle của riêng nó.

## 23. Kế thừa: superclass khởi tạo trước subclass

Khi một class `Child extends Parent` phải được initialize, Java đảm bảo superclass phù hợp được initialize trước subclass theo các quy tắc class initialization.

Ví dụ:

~~~java
class Parent {
    static int p = 1;

    static {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    static int c = 2;

    static {
        System.out.println("Child");
    }
}
~~~

Nếu chương trình truy cập `Child.c` theo cách kích hoạt khởi tạo Child, static initialization của Parent phải hoàn tất thích hợp trước khi chạy static initialization của Child.

### Bảng thứ tự

| Phạm vi | Thứ tự cơ bản |
| --- | --- |
| Parent | Các static field initializers và static blocks của Parent theo source |
| Child | Các static field initializers và static blocks của Child theo source |
| Tạo Child instance | Sau các class initializations cần thiết, instance initialization đi theo quy tắc constructor/superclass |

Không gộp tất cả static fields của hai class vào một danh sách trộn theo tên file, thời điểm viết file hoặc chữ cái. Phải xét **thứ tự phụ thuộc superclass → subclass**, rồi **thứ tự văn bản nguồn bên trong từng class**.

## 24. Ví dụ chạy: thứ tự Parent và Child

Tạo **`InheritanceStaticInitDemo.java`**:

~~~java
public class InheritanceStaticInitDemo {
    static int mark(String text, int number) {
        System.out.println(text + "=" + number);
        return number;
    }

    static class Parent {
        static int parentValue = mark("Parent.field", 1);

        static {
            System.out.println("Parent.block");
        }
    }

    static class Child extends Parent {
        static int childValue = mark("Child.field", 2);

        static {
            System.out.println("Child.block");
        }
    }

    public static void main(String[] args) {
        System.out.println("before");
        System.out.println("child=" + Child.childValue);
        System.out.println("parent=" + Parent.parentValue);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InheritanceStaticInitDemo.java
java InheritanceStaticInitDemo
~~~

Stdout:

~~~text
before
Parent.field=1
Parent.block
Child.field=2
Child.block
child=2
parent=1
~~~

`Child.childValue` kích hoạt khởi tạo Child. JVM đảm bảo Parent được initialize trước; sau đó Child chạy các static declarations của riêng mình theo textual order. Khi main đọc `Parent.parentValue` sau cùng, Parent đã được khởi tạo nên static block không in lần nữa.

### Một ngoại lệ đáng lưu ý

Đọc **inherited static field** qua tên subclass có thể chỉ khởi tạo **class khai báo field**, không nhất thiết khởi tạo subclass. Ví dụ nếu `Child` không khai báo `shared` mà kế thừa `Parent.shared`, thì `Child.shared` thực chất đề cập field được khai báo trong Parent. Khi cần suy ra class nào initialize, xác định **class thực sự khai báo static member** chứ không chỉ class qualifier viết trong source.

## 25. Static initialization khác instance initialization ở lớp kế thừa

Với `new Child()`, có hai lớp thứ tự cần phân tích:

1. Class initialization: các superclasses cần thiết, rồi subclass.
2. Instance construction: bộ phận instance của superclass và constructor, rồi bộ phận instance của subclass và constructor, theo quy tắc Java.

Đối với mỗi class trong quá trình tạo instance, **instance field initializers và instance initializer blocks** được xử lý theo textual order của chúng ở giai đoạn thích hợp, không phải xen ngang tùy tiện vào class initialization.

### Ví dụ chạy minh họa cả hai loại

Tạo file **`ClassAndObjectInitDemo.java`**:

~~~java
public class ClassAndObjectInitDemo {
    static class Parent {
        static {
            System.out.println("Parent static");
        }

        {
            System.out.println("Parent instance");
        }

        Parent() {
            System.out.println("Parent constructor");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child static");
        }

        {
            System.out.println("Child instance");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("begin");
        new Child();
        System.out.println("again");
        new Child();
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassAndObjectInitDemo.java
java ClassAndObjectInitDemo
~~~

Stdout:

~~~text
begin
Parent static
Child static
Parent instance
Parent constructor
Child instance
Child constructor
again
Parent instance
Parent constructor
Child instance
Child constructor
~~~

Lần đầu tạo Child kích hoạt khởi tạo class Parent rồi Child; sau đó tạo object theo chuỗi constructor. Lần hai class initialization đã hoàn tất, nên chỉ có instance blocks và constructors chạy lại. Điều này khác hoàn toàn với việc hai static blocks nằm xen kẽ trong **cùng một class**, là trọng tâm textual order ban đầu.

## 26. Khi static initializer gọi method của class khác

Một field initializer có thể gọi method của class B:

~~~java
class A {
    static int data = B.load();
}

class B {
    static int load() {
        return 5;
    }
}
~~~

Trong ví dụ, initialize A đến `data = B.load()` có thể kích hoạt initialization của B nếu B chưa được initialize. Sau khi B sẵn sàng, method `load` chạy rồi trả 5; A tiếp tục hoàn tất.

**Điểm quan trọng:** Textual order là quy tắc **bên trong từng class**, nhưng quá trình có thể **đi sang khởi tạo class khác** ngay tại một bước gọi method/đọc field. Vì vậy log từ nhiều class có thể xen kẽ theo đường phụ thuộc, không chỉ thành các block lớn tách biệt.

### Điều nên tránh

Tạo các static initializers phụ thuộc chéo nhiều class làm code khó đoán. Một class A đọc B, B đọc C, C lại đọc A có thể đưa tới **partially initialized state** hoặc lỗi liveness nếu nhiều threads và locks liên quan. Sắp xếp lại dependencies để initialization đơn giản, một chiều và dễ kiểm thử.

## 27. Circular initialization: static fields có thể nhìn thấy state chưa hoàn tất

Nếu A cần B khi đang initialize và B lại đọc A, quy tắc VM có thể cho thấy các static fields của class đang khởi tạo nhưng **chưa chạy xong** initializer.

Ví dụ:

~~~java
class A {
    static int value = B.value + 1;
}

class B {
    static int value = A.value + 1;
}
~~~

Khi **cùng một thread** bắt đầu initialization từ A, có thể xảy ra:

1. A.value ở default 0; initializer A cần `B.value`.
2. B bắt đầu initialize; initializer B cần `A.value`.
3. Vì A đã đang được initialize bởi **cùng thread**, recursive request không chạy lại toàn bộ initializer A mà có thể quan sát `A.value` hiện tại là 0.
4. B.value trở thành 1.
5. A tiếp tục và gán `A.value = 2`.

### Ví dụ chạy

Tạo file **`CircularStaticInitDemo.java`**:

~~~java
public class CircularStaticInitDemo {
    static class A {
        static int value = B.value + 1;
    }

    static class B {
        static int value = A.value + 1;
    }

    public static void main(String[] args) {
        System.out.println("A=" + A.value);
        System.out.println("B=" + B.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 CircularStaticInitDemo.java
java CircularStaticInitDemo
~~~

Stdout:

~~~text
A=2
B=1
~~~

**Không lấy ví dụ này làm mẫu thiết kế.** Kết quả phụ thuộc vào điểm bắt đầu initialization: nếu B được chủ động initialize trước trong một chương trình khác, thứ tự và giá trị có thể khác. Textual order vẫn đúng trong từng class, nhưng circular dependency khiến việc dự đoán phải xét cả class-init graph.

Trong môi trường nhiều threads, circular class initialization còn có thể tạo rủi ro chờ lẫn nhau. Hãy ưu tiên tách dependencies và giảm side effects trong static initialization.

## 28. Static initialization và lỗi ngoại lệ

Một static field initializer hoặc static block có thể **thất bại**:

~~~java
class Broken {
    static int value = fail();

    static int fail() {
        throw new IllegalStateException("configuration unavailable");
    }
}
~~~

Khi khởi tạo Broken, exception có thể khiến JVM báo `ExceptionInInitializerError` với nguyên nhân gốc là `IllegalStateException`. Class có thể bị đánh dấu trạng thái **erroneous** trong class runtime. Những lần sử dụng sau đó có thể báo `NoClassDefFoundError` thay vì thử khởi tạo lại.

Điều này quan trọng khi đọc log: `NoClassDefFoundError` sau một lần init thất bại có thể là **hệ quả thứ hai**, không phải “class file tự nhiên biến mất”.

### Không dùng static block để làm giao dịch nặng

Các tác vụ dễ lỗi như gọi mạng, mở kết nối database, đọc nhiều file hoặc khởi tạo tài nguyên có lifecycle phức tạp thường nên có **explicit setup và error handling** thay vì thực thi tùy tiện trong static initializer.

Một lỗi static init có thể ảnh hưởng toàn bộ class runtime, gây khó khăn cho retry và test isolation.

## 29. Ví dụ chạy: thất bại lúc class initialization

Lưu file **`StaticInitializationFailureDemo.java`**:

~~~java
public class StaticInitializationFailureDemo {
    static class Broken {
        static int value = load();

        static int load() {
            throw new IllegalStateException("invalid config");
        }
    }

    static void attempt(String label) {
        try {
            System.out.println(Broken.value);
        } catch (Throwable ex) {
            System.out.println(label + "=" +
                    ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        attempt("first");
        attempt("second");
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticInitializationFailureDemo.java
java StaticInitializationFailureDemo
~~~

Stdout điển hình theo Java 17:

~~~text
first=ExceptionInInitializerError
second=NoClassDefFoundError
~~~

Khi lần đầu truy cập `Broken.value`, JVM khởi tạo Broken và `load()` ném `IllegalStateException`. Lỗi khởi tạo được biểu diễn bằng `ExceptionInInitializerError`. Lần sau class runtime đã ở trạng thái khởi tạo thất bại, nên JVM báo `NoClassDefFoundError`.

**Chỉ trong ví dụ học tập** ta catch `Throwable` để thấy hai loại lỗi; **không nên catch Throwable rộng khắp trong ứng dụng** để che các lỗi nghiêm trọng. Trong hệ thống thật, cần truy vết nguyên nhân ban đầu, sửa configuration và thiết kế retry/lifecycle ở tầng phù hợp.

## 30. Static block không phải nơi thích hợp cho mọi logic

Một static block ngắn có thể hợp lý để xây dựng immutable lookup data phức tạp:

~~~java
class ColorCodes {
    static final java.util.Map<String, Integer> CODES;

    static {
        java.util.Map<String, Integer> data =
                new java.util.HashMap<>();
        data.put("RED", 1);
        data.put("GREEN", 2);
        CODES = java.util.Map.copyOf(data);
    }
}
~~~

Đây là class minh họa. `CODES` là final reference tới một unmodifiable map snapshot với keys String và values Integer immutable trong ví dụ.

Nhưng nếu block đọc dữ liệu từ mạng hoặc đăng ký callbacks nhiều nơi, initialization order dễ trở thành một hệ thống lifecycle **ẩn** và khó test. Lựa chọn tốt hơn có thể là static factory method đơn giản, explicit constructor, service setup hoặc lazy holder pattern.

### Một điều không đúng

`static final Map<String, String> map = new HashMap<>();` **không tự immutable**, dù reference final. Nếu có public getter trả mutable Map hoặc methods mutate nó, state có thể thay đổi sau khởi tạo và ảnh hưởng mọi callers.

## 31. Lazy holder: khởi tạo tài nguyên khi thật sự cần

Một cách trì hoãn khởi tạo dữ liệu là giữ resource trong **static nested class** riêng:

~~~java
class Repository {
    private static class Holder {
        static final java.util.List<String> NAMES =
                java.util.List.of("Mai", "An");
    }

    static java.util.List<String> names() {
        return Holder.NAMES;
    }
}
~~~

Việc gọi `Repository.names()` có thể initialize Repository và sau đó initialize Holder khi static field Holder.NAMES được sử dụng; không nhất thiết initialize Holder từ lúc chương trình mới biết tới tên Repository.

### Ví dụ chạy

Tạo file **`LazyHolderDemo.java`**:

~~~java
public class LazyHolderDemo {
    static class Repository {
        static {
            System.out.println("Repository initialized");
        }

        static class Holder {
            static {
                System.out.println("Holder initialized");
            }

            static final java.util.List<String> NAMES =
                    java.util.List.of("Mai", "An");
        }

        static void ping() {
            System.out.println("ping");
        }

        static java.util.List<String> names() {
            return Holder.NAMES;
        }
    }

    public static void main(String[] args) {
        Repository.ping();
        System.out.println("names=" + Repository.names());
        System.out.println("names again=" + Repository.names());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LazyHolderDemo.java
java LazyHolderDemo
~~~

Stdout:

~~~text
Repository initialized
ping
Holder initialized
names=[Mai, An]
names again=[Mai, An]
~~~

`Repository.ping()` kích hoạt initialize Repository, nhưng không dùng Holder. Khi `names()` đầu tiên truy cập `Holder.NAMES`, Holder được initialize riêng. Lời gọi `names()` thứ hai không chạy lại blocks.

**Đừng lạm dụng lazy holder:** Nó hữu ích khi có tài nguyên đáng trì hoãn, nhưng có thể gây lỗi khởi tạo tại thời điểm sử dụng đầu tiên. Hãy xác định failure strategy/lifecycle nếu initializer phức tạp.

## 32. Tương tác với `static final` và constant inlining

Một ví dụ:

~~~java
public class PublicLimits {
    public static final int MAX_USERS = 100;
}
~~~

Một client biên dịch tham chiếu `PublicLimits.MAX_USERS` có thể được compiler thay bằng giá trị 100 trong bytecode của client. Nếu thư viện sửa thành 200 nhưng chỉ build lại thư viện, client cũ có thể vẫn dùng 100. Đây là hệ quả của **compile-time constants**, không phải static initializer chưa kịp chạy.

Nếu muốn config thay đổi theo triển khai, cân nhắc accessor method:

~~~java
public static int maxUsers() {
    return 100;
}
~~~

Method có thể được call tại runtime và không phải cùng cơ chế constant inlining của một field `public static final int` có constant expression.

**Không suy luận** rằng mọi `static final` đều được inline. Một `static final Integer`, `Duration` hoặc `String` tính qua method call không phải constant variable theo quy tắc nêu trên.

## 33. Static blocks và trường kế thừa bị hiding

Giả sử:

~~~java
class Parent {
    static int value = 1;
}

class Child extends Parent {
    static int value = 2;
}
~~~

Đây là **hai static fields khác nhau** vì Child khai báo field riêng trùng tên (field hiding). Không phải Child override field Parent.

Nếu bên trong Child có:

~~~java
static {
    System.out.println(value);
    System.out.println(Parent.value);
}
~~~

thì tên `value` trong Child thường tham chiếu **Child.value** đã khai báo ở Child, còn `Parent.value` là field của superclass. Khi xác định initialization order, phải phân biệt **field owner** thay vì chỉ tên field giống nhau.

Không dùng field hiding như cách tổ chức config dễ hiểu; nó gây nhầm về thứ tự và field thực sự được đọc. Với static data, truy cập qua **class khai báo** giúp rõ ràng hơn.

## 34. Static initializer không được có `this`

Trong static block:

~~~java
class Example {
    int instanceValue = 1;
    static int sharedValue = 2;

    static {
        System.out.println(sharedValue); // Hợp lệ.
        // System.out.println(this.instanceValue); // Lỗi.
        // System.out.println(instanceValue);      // Lỗi.
    }
}
~~~

Static context không có instance receiver `this`. Muốn đọc instance field, cần một object cụ thể:

~~~java
Example example = new Example();
System.out.println(example.instanceValue);
~~~

Nhưng tạo object ngay trong static initializer thường làm initialization graph phức tạp. Đừng tạo object chỉ để bypass việc không có `this` nếu bạn có thể dùng value/config phù hợp hơn.

### Không thể return value từ static block

~~~java
static {
    // return; // Không hợp lệ trong static initializer.
}
~~~

Static initializer không phải method. Nó không có parameter list, return type hay lời gọi bằng tên từ caller.

## 35. Static initialization và checked exception

Không thể tùy ý để một static initializer block ném một checked exception chưa xử lý:

~~~java
class Config {
    static {
        // throw new java.io.IOException("missing"); // Không hợp lệ:
        // checked exception không được thoát như vậy từ initializer.
    }
}
~~~

Nếu cần I/O trong quá trình khởi tạo, phải xử lý checked exceptions hợp lệ. Nhưng **bắt rồi ném unchecked trong static block** chưa chắc là thiết kế tốt, vì failure có thể khiến cả class runtime không sử dụng được sau đó.

Cân nhắc explicit load method:

~~~java
static ConfigData load(java.nio.file.Path path)
        throws java.io.IOException {
    // Đọc file và trả kết quả, caller quản lý lỗi.
    return null; // Minh họa chữ ký, không phải triển khai thực tế.
}
~~~

Mã trên là **chữ ký minh họa về quản lý lỗi**, chưa phải chương trình runnable; trong ứng dụng thực tế phải có `ConfigData` và implementation cụ thể, không trả null tùy tiện.

## 36. Tránh side effects trong static initializers

Static initialization chạy vào lúc class được **sử dụng chủ động**. Nếu static block:

- Ghi file.
- Mở cổng mạng.
- Thay system properties.
- Đăng ký listener.
- Khởi chạy thread.
- Chạm nhiều services bên ngoài.

thì một caller chỉ muốn đọc field của class cũng có thể vô tình kích hoạt side effect. Điều này khiến test và runtime startup phụ thuộc vào **ai dùng class trước**.

### Ví dụ mùi thiết kế

~~~java
class AppGlobals {
    static {
        System.setProperty("app.mode", "production");
    }
}
~~~

Đây là **đoạn phản ví dụ**. Nó thay process-wide property khi AppGlobals được initialize; những tests hoặc module khác có thể chịu tác động mà không biết nguyên nhân.

Thay vì side effects ẩn, dùng **explicit bootstrap/configuration**, với ownership và cleanup rõ ràng. Đặc biệt, đừng để static initializer vô tình tạo “người chạy đầu tiên quyết định toàn bộ config”.

## 37. Kết quả thử nghiệm có thể phụ thuộc việc class đã khởi tạo chưa

Một test in log và mong static block xuất hiện mỗi lần test method chạy sẽ không đáng tin nếu test runner giữ class runtime giữa các tests. Một test khác có thể initialize class trước, khiến static block đã chạy khi test cần quan sát nó.

Không nên dùng test đơn thuần phụ thuộc “class này chắc chắn chưa từng được initialize” trong một shared test process trừ khi bạn thật sự kiểm soát class loading/lifecycle.

### Cách test hợp lý

- Test trạng thái cuối hoặc hành vi công khai sau initialization.
- Với thứ tự initialization, dùng một class ví dụ nhỏ độc lập và chạy trong process/class-loader được kiểm soát khi cần.
- Không dựa vào thứ tự các test methods ngẫu nhiên.
- Tránh mutable static global state giữa tests.
- Nếu khởi tạo tài nguyên bên ngoài, test qua explicit initialization API với fake dependencies.
- Khi cần kiểm tra lỗi init, cân nhắc JVM process riêng vì class có thể bị đánh dấu erroneous sau lần đầu thất bại.

Đây là rủi ro thực tế của việc dùng static blocks cho setup lớn: test isolation phức tạp hơn so với explicit instance/setup.

## 38. Bài toán tổng hợp: trace từng dòng trong cùng class

Cho:

~~~java
class Calculation {
    static int x = 2;

    static {
        x += 3;
    }

    static int y = x * 2;

    static {
        y = y - x;
        x++;
    }

    static int z = x + y;
}
~~~

Hãy tính:

- Sau `x = 2`: x = 2.
- Sau block đầu: x = 5.
- Sau `y = x * 2`: y = 10.
- Block tiếp theo: y = 10 - 5 = 5; x = 6.
- Sau `z = x + y`: z = 11.

Giá trị cuối: `x=6`, `y=5`, `z=11`.

Một sai lầm thường gặp là xem `y = x * 2` như một công thức tự cập nhật khi x tăng trong block sau. Trong Java, initializer chỉ chạy ở **mốc khởi tạo**. `y` giữ 10 cho tới khi bị code block sau gán lại thành 5.

## 39. Ví dụ chạy tổng hợp ba static fields và hai blocks

Tạo file **`StaticTraceExerciseDemo.java`**:

~~~java
public class StaticTraceExerciseDemo {
    static class Calculation {
        static int x = 2;

        static {
            x += 3;
        }

        static int y = x * 2;

        static {
            y = y - x;
            x++;
        }

        static int z = x + y;
    }

    public static void main(String[] args) {
        System.out.println("x=" + Calculation.x);
        System.out.println("y=" + Calculation.y);
        System.out.println("z=" + Calculation.z);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticTraceExerciseDemo.java
java StaticTraceExerciseDemo
~~~

Stdout:

~~~text
x=6
y=5
z=11
~~~

Để giải dạng bài này, đừng chỉ đếm các field hoặc blocks. Hãy ghi **một dòng bảng cho từng initializer/block đúng thứ tự source**; mỗi dòng cập nhật các fields thực sự bị tác động.

## 40. So sánh static field initializer với instance field initializer

Ví dụ:

~~~java
class Sample {
    static int a = logStatic();

    int b = logInstance();

    static int logStatic() {
        System.out.println("static");
        return 1;
    }

    int logInstance() {
        System.out.println("instance");
        return 2;
    }
}
~~~

Đây là class minh họa. `logStatic` được gọi trong class initialization nếu class được initialize; `logInstance` được gọi **mỗi khi tạo một Sample instance** sau khi class initialization phù hợp. Việc hai initializers cùng xuất hiện trong source không có nghĩa chúng chạy xen nhau từng dòng cho từng object.

Nếu có static block nằm sau instance field declaration, static block vẫn thuộc **class initialization**, không chờ mỗi instance chạy đến vị trí đó. Do đó “theo văn bản nguồn” phải được hiểu **trong cùng loại initialization phase và class**, không đơn thuần đọc từng dòng class rồi chạy tất cả theo một luồng từ trên xuống cho mỗi `new`.

## 41. Không được dùng thứ tự file làm thứ tự class initialization

Hai file:

~~~text
src/
├── A.java
└── B.java
~~~

Việc `A.java` xuất hiện trước `B.java` trong explorer, tên theo thứ tự alphabet hay compiler đọc file nào trước **không tự xác định runtime initialization order**.

Nếu A sử dụng static method của B, B có thể được initialize trong lúc A đang initialize. Nếu B được dùng trước, ngược lại. Class hierarchy, class initialization triggers và dependency graph mới là cơ sở để dự đoán.

Một static initializer có side effects cần phân biệt “source order **trong một class**” với “thứ tự những class độc lập được initialize **trên toàn chương trình**”. Không có một bảng sắp xếp file toàn cục thay cho thứ tự thực thi.

## 42. Một số vấn đề cần lưu ý khi có nhiều threads

Java class initialization được JVM phối hợp để không có hai threads độc lập tùy tiện chạy cùng một static initializer như hai bản initialization bình thường.

Tuy nhiên:

- Static fields **có thể bị sửa sau initialization**, và những cập nhật ấy cần đúng quy tắc Java Memory Model.
- `static int count; count++` không tự atomic.
- `static final List` có thể chứa mutable object; object ấy không tự thread-safe.
- Nếu thread A và thread B cần initialize các class phụ thuộc chéo theo những đường phức tạp, có thể xuất hiện tình huống chờ class initialization không mong muốn.
- Không dùng static blocks làm nơi triển khai một mạng lưới thread startup/phối hợp phức tạp.

**Đừng nhầm “JVM bảo vệ class initialization” với “mọi static field đều thread-safe”.** Cần thiết kế visibility, synchronization, atomicity và ownership cho những hoạt động cập nhật state về sau.

## 43. Bài tập 1 — Xác định textual order

Cho:

~~~java
class Steps {
    static int a = 1;

    static {
        a *= 3;
    }

    static int b = a + 2;

    static {
        b += a;
    }
}
~~~

Hỏi sau khi class initialization thành công, `a` và `b` là bao nhiêu?

**Đáp án:** `a=3`. Initializer `b = a + 2` cho `b=5`. Block cuối làm `b=5+3=8`. Kết quả `a=3`, `b=8`.

## 44. Bài tập 2 — Direct forward reference

Cho:

~~~java
class Sample {
    // static int first = second; // Vì sao lỗi?
    static int second = 9;
}
~~~

**Đáp án:** `second` được dùng bằng simple name ở static field initializer **trước khai báo field** trong cùng class, vi phạm giới hạn forward reference. Không phải bởi Java không bao giờ biết field `second` tồn tại — compiler biết khai báo — mà bởi quy tắc sử dụng field sớm trong static initialization context.

Hãy thử thay bằng qualified name và dự đoán giá trị `first` trước khi second initializer chạy.

## 45. Bài tập 3 — Đọc gián tiếp qua method

~~~java
class Example {
    static int early = read();

    static int late = 12;

    static int read() {
        return late;
    }
}
~~~

**Đáp án:** Sau initialization, `early=0`, `late=12`. Method `read()` được gọi khi `late` vẫn là default 0; initializer `late = 12` chạy sau đó.

## 46. Bài tập 4 — Constant variable

~~~java
class Config {
    static int observed = readLimit();
    static final int LIMIT = 15;

    static int readLimit() {
        return LIMIT;
    }
}
~~~

**Đáp án:** `observed=15`. `LIMIT` là static final int với constant-expression initializer, không giống non-constant static field `late` ở bài trước. Đọc LIMIT trong method trả 15.

## 47. Bài tập 5 — Superclass và subclass

~~~java
class Base {
    static int a = 2;
    static {
        a++;
    }
}

class Derived extends Base {
    static int b = a * 2;
    static {
        b++;
    }
}
~~~

Nếu `Derived.b` làm initialize Derived, Base đã được initialize trước: `Base.a` từ 2 thành 3; Derived dùng `a=3` để tính `b=6` rồi tăng lên 7.

**Đáp án:** `Base.a=3` và `Derived.b=7`.

## 48. Bài tập 6 — Lỗi init và phương án cải thiện

Một class có:

~~~java
class ServiceConfig {
    static final String ENDPOINT = readRemoteConfig();

    static String readRemoteConfig() {
        throw new IllegalStateException("service offline");
    }
}
~~~

Nếu class initialization thất bại, vì sao gọi lại method có liên quan class này không đơn giản “thử khởi tạo lại từ đầu”?

**Đáp án:** JVM có thể đánh dấu class runtime erroneous sau init failure; những lần dùng sau đó có thể nhận `NoClassDefFoundError`. Nếu config có thể tạm thời thất bại và cần retry, hãy dùng explicit config loader/service với lifecycle và retry policy rõ, không gắn toàn bộ retry semantics vào một static final field initializer.

## 49. Checklist tự đánh giá

- [ ] Tôi phân biệt class loading/preparation với class initialization.
- [ ] Tôi biết non-constant static fields có default values trước các initializers thường.
- [ ] Tôi không áp dụng máy móc default 0/null cho compile-time constant variables.
- [ ] Tôi biết field initializers và static blocks xen kẽ theo **thứ tự nguồn** trong cùng class.
- [ ] Tôi biết static blocks không chạy lại với mỗi instance mới.
- [ ] Tôi biết static methods có thể được khai báo sau và được gọi trước trong initializer.
- [ ] Tôi biết khi nào simple-name forward read gây `illegal forward reference`.
- [ ] Tôi biết qualified forward read có thể biên dịch và quan sát default value.
- [ ] Tôi biết method-mediated forward read có thể quan sát default value.
- [ ] Tôi phân biệt forward assignment hợp lệ trong một số trường hợp với forward read bị cấm.
- [ ] Tôi biết `static final int` với constant expression khác `static final Integer`.
- [ ] Tôi biết đọc compile-time constant có thể không kích hoạt class initialization.
- [ ] Tôi biết blank static final field có thể được gán trong static block.
- [ ] Tôi biết static field initializer không tự chạy lại khi field khác thay đổi.
- [ ] Tôi tính được thứ tự Parent static trước Child static khi initialize Child.
- [ ] Tôi biết access inherited static field có thể chỉ initialize class khai báo member.
- [ ] Tôi phân biệt static initializer với instance initializer và constructor.
- [ ] Tôi không coi thứ tự source file là thứ tự class initialization toàn hệ thống.
- [ ] Tôi nhận diện circular static initialization và trạng thái partially initialized.
- [ ] Tôi hiểu class initialization failure có thể tạo `ExceptionInInitializerError`/`NoClassDefFoundError`.
- [ ] Tôi tránh side effects và phụ thuộc chéo phức tạp trong static blocks.
- [ ] Tôi hiểu lazy nested holder được initialize theo nhu cầu riêng.
- [ ] Tôi biết static initialization an toàn theo cơ chế JVM không làm mọi static mutation thread-safe.
- [ ] Tôi biết cách thiết kế test tránh phụ thuộc class đã được initialize ở test khác.
- [ ] Tôi biên dịch và chạy được những ví dụ Java 17+ kèm kết quả như bài.

**Kết luận:** Với một class Java, hãy theo dõi **những static field initializers và static initializer blocks theo đúng vị trí từ trên xuống trong văn bản nguồn**, nhưng đặt chúng trong bối cảnh **class initialization thực sự được kích hoạt khi nào, static fields đã có giá trị mặc định ra sao, constant variables được xử lý đặc biệt như thế nào**. Khi gặp field phía sau, phân biệt **simple-name forward read bị cấm**, **qualified/indirect read có thể thấy default**, và **compile-time constant có giá trị hằng**. Với nhiều class, thêm thứ tự superclass–subclass và các class-init dependencies. Bảng từng mốc khởi tạo sẽ giúp bạn dự đoán chính xác chương trình thay vì trông chờ vào cảm giác “static lúc nào cũng chạy trước”.
