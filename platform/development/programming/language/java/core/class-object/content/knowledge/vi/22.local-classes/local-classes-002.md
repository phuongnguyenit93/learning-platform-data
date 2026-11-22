# Phạm vi sử dụng tên của lớp cục bộ trong Java

## 1. Mục tiêu: phân biệt nơi tên kiểu hợp lệ với nơi đối tượng còn tồn tại

**Lớp cục bộ (*local class*)** là một khai báo lớp nằm trong một block, chẳng hạn thân method, constructor hoặc block lồng trong một method. Tên lớp cục bộ không có phạm vi trên toàn bộ file hay toàn bộ outer class; nó có **phạm vi từ khai báo của lớp đến hết block trực tiếp bao chứa khai báo đó**, kể cả các block nằm sâu hơn trong phần còn lại của block.

Ví dụ khái niệm:

```java
void example() {
    // Chưa thể dùng tên Local ở đây.

    class Local {
        String message() {
            return "hello";
        }
    }

    Local value = new Local(); // Hợp lệ.
    System.out.println(value.message());
}
// Ở ngoài method không thể gọi kiểu Local bằng tên đó.
```

Đoạn trên là **một instance method minh họa**, không phải chương trình độc lập. Những điểm cần ghi nhớ:

1. Trước chỗ khai báo `class Local`, tên **lớp cục bộ ấy** chưa nằm trong phạm vi sử dụng.
2. Trong phần thân khai báo của chính Local và trong phần còn lại của block bao chứa, có thể sử dụng tên `Local` theo quy tắc Java.
3. Sau dấu `}` đóng **block trực tiếp chứa khai báo**, tên Local không còn là tên kiểu nhìn thấy được từ phía ngoài.
4. Một **instance của Local vẫn có thể tồn tại** sau khi ra khỏi block nếu được giữ qua kiểu giao diện/superclass công khai thích hợp.
5. Phạm vi **tên kiểu** không giống phạm vi của **biến local**, và cũng không tự quyết định **vòng đời object trong heap**.

> **Câu chốt:** Khi đọc code Java, hãy tìm **block nào chứa dòng `class Local`**, rồi xác định vị trí trước/sau dòng khai báo. Không suy rằng lớp cục bộ có thể gọi tên ở mọi nơi chỉ vì class của nó được JVM tạo ra.

Bài học tập trung chính xác vào **phạm vi sử dụng tên của lớp cục bộ**, và mở rộng những tình huống gắn trực tiếp với phạm vi: block lồng, nhánh điều kiện, vòng lặp, khai báo trùng tên ở các vùng tách biệt, kiểu trả về giao diện, capture biến, `this`, ngữ cảnh static và các lỗi compile-time dễ gặp. Các chương trình bên dưới dùng Java 17+.

## 2. Ví dụ runnable cơ bản: dùng tên sau khai báo trong cùng block

Tạo tệp **`LocalNameScopeDemo.java`**:

```java
public class LocalNameScopeDemo {
    public static void main(String[] args) {
        String prefix = "Hello";

        class Greeting {
            String text() {
                return prefix + ", Java";
            }
        }

        Greeting greeting = new Greeting();
        System.out.println(greeting.text());

        Greeting second = new Greeting();
        System.out.println(second.text());
    }
}
```

Biên dịch và chạy:

```bash
javac LocalNameScopeDemo.java
java LocalNameScopeDemo
```

**Standard output:**

```text
Hello, Java
Hello, Java
```

Phân tích:

- `Greeting` được khai báo **bên trong block của main**.
- Hai lệnh `new Greeting()` đều **nằm sau** khai báo và **vẫn trong cùng block**, nên compiler nhận ra tên kiểu.
- `prefix` là local variable được lớp Greeting sử dụng; giá trị `prefix` được capture theo quy tắc final/effectively final. Chúng ta sẽ phân biệt capture và scope của tên class ở phần sau.
- Kết thúc `main`, mã ở method khác không thể tham chiếu `Greeting` bằng tên không được khai báo tại phạm vi của method kia.

**Không viết `LocalNameScopeDemo.Greeting`:** Greeting là local class chứ không phải member class được khai báo trực tiếp trong body của `LocalNameScopeDemo`. Tên kiểu qualified theo outer class không thể biến một local class thành member class.

## 3. Phạm vi bắt đầu tại khai báo, không áp dụng cho các dòng phía trước

Xét đoạn **cố ý không biên dịch**:

```java
public class BeforeDeclarationError {
    public static void main(String[] args) {
        // Local value = new Local(); // Lỗi nếu bỏ comment:
        // chưa có local type tên Local trong phạm vi này.

        class Local {
            int value() {
                return 42;
            }
        }

        Local okay = new Local(); // Hợp lệ.
        System.out.println(okay.value());
    }
}
```

Nếu giữ phần không hợp lệ dưới dạng comment, file trên biên dịch và chạy được:

```bash
javac BeforeDeclarationError.java
java BeforeDeclarationError
```

```text
42
```

**Mốc quan trọng** là vị trí `class Local`, không phải chỉ vị trí mở method. Trước khi khai báo, tên của local class này không thể được giải quyết.

### Vì sao lớp vẫn tự nhắc đến tên của chính nó?

Ngay trong khai báo local class, tên lớp được phép dùng cho các thành viên, constructor và kiểu của nó:

```java
class Node {
    Node next;

    Node(Node next) {
        this.next = next;
    }
}
```

Đó là **mảnh khai báo lớp cục bộ** đặt trong một block hợp lệ. Tên `Node` được dùng trong chính khai báo Node, không phải “tham chiếu tới một tên chưa khai báo” như ở dòng trước khai báo.

**Không kết luận sai rằng** chỉ các dòng *sau dấu ngoặc đóng của class* mới được dùng tên. Thân khai báo là phần hợp lệ của phạm vi tên class, còn các dòng **trước dòng khai báo** thì không.

## 4. Block trực tiếp chứa khai báo quyết định ranh giới

Lớp cục bộ có phạm vi trong **phần còn lại của block trực tiếp chứa nó**, bao gồm các block lồng tiếp theo trong phần ấy.

Tạo **`NestedBlockScopeDemo.java`**:

```java
public class NestedBlockScopeDemo {
    public static void main(String[] args) {
        class Ticket {
            String label() {
                return "TICKET";
            }
        }

        Ticket first = new Ticket();
        System.out.println(first.label());

        {
            Ticket second = new Ticket();
            System.out.println(second.label());

            {
                Ticket third = new Ticket();
                System.out.println(third.label());
            }
        }

        Ticket afterNestedBlocks = new Ticket();
        System.out.println(afterNestedBlocks.label());
    }
}
```

```bash
javac NestedBlockScopeDemo.java
java NestedBlockScopeDemo
```

```text
TICKET
TICKET
TICKET
TICKET
```

**Giải thích:**

- `Ticket` nằm trong block main, và mọi code phía sau ở cùng block có thể gọi tên nó.
- Các block lồng bên dưới vẫn nằm trong phạm vi của local class đã khai báo ở cấp cao hơn.
- Khi thoát block lồng, tên Ticket vẫn nhìn thấy được vì **block chứa trực tiếp khai báo Ticket vẫn chưa kết thúc**.

Quy tắc này không ngược lại: nếu Ticket được khai báo *bên trong* một block con, code ở block cha sau khi block con đóng **không dùng được tên Ticket ấy**.

## 5. Khai báo trong block con: tên không “rò” ra block cha

Tạo **`InnerBlockOnlyDemo.java`**:

```java
public class InnerBlockOnlyDemo {
    public static void main(String[] args) {
        {
            class Local {
                String id() {
                    return "INSIDE";
                }
            }

            Local instance = new Local();
            System.out.println(instance.id());
        }

        System.out.println("outer block continues");

        // Local outside = new Local(); // Không hợp lệ:
        // tên Local chỉ thuộc block con đã đóng.
    }
}
```

```bash
javac InnerBlockOnlyDemo.java
java InnerBlockOnlyDemo
```

```text
INSIDE
outer block continues
```

Dòng `Local outside` được comment để ví dụ chạy được. Nếu bỏ comment, compiler sẽ không nhận tên kiểu Local từ block đã đóng.

Đừng nhầm với việc **giữ một biến đối tượng**: ở ví dụ này `instance` cũng là local variable chỉ tồn tại về mặt tên trong block con. Nhưng ngay cả nếu instance được truyền ra ngoài qua interface, tên class Local vẫn không mở rộng phạm vi. Hai chuyện phải phân biệt.

## 6. Lớp cục bộ trong hai block khác nhau có thể trùng tên

Hai khai báo `class Result` trong **hai block tách biệt, không chồng lấp phạm vi** có thể cùng dùng tên Result. Mỗi khai báo tạo một local class khác về kiểu.

Tạo **`DisjointLocalNamesDemo.java`**:

```java
public class DisjointLocalNamesDemo {
    public static void main(String[] args) {
        {
            class Result {
                String text() {
                    return "FIRST";
                }
            }

            Result a = new Result();
            System.out.println(a.text());
        }

        {
            class Result {
                String text() {
                    return "SECOND";
                }
            }

            Result b = new Result();
            System.out.println(b.text());
        }
    }
}
```

```bash
javac DisjointLocalNamesDemo.java
java DisjointLocalNamesDemo
```

```text
FIRST
SECOND
```

Tại block thứ nhất, `Result` là kiểu được khai báo ở block thứ nhất. Sau khi đóng block, tên ấy ra khỏi scope. Ở block thứ hai, một **khai báo mới** tạo kiểu Result khác.

**Không có nghĩa** hai classes này là cùng một type chỉ vì cách viết tên `Result` giống nhau. Cũng không thể lấy một biến declared ở block đầu rồi dùng ở block sau khi nó đã hết scope.

### Nếu phạm vi chồng lấp thì sao?

Đừng tự khai báo hai local classes cùng tên ở một vùng phạm vi chồng lấp rồi nghĩ rằng Java sẽ coi chúng là overloads. Hãy chọn tên khác hoặc tổ chức thành những block tách biệt với ranh giới rõ.

## 7. Khai báo cùng tên ở hai method khác nhau

Method scopes độc lập: mỗi method có thể khai báo một local class cùng tên mà không phải cùng type.

Tạo **`SameNameDifferentMethodsDemo.java`**:

```java
public class SameNameDifferentMethodsDemo {
    static void alpha() {
        class Helper {
            String message() {
                return "ALPHA";
            }
        }
        System.out.println(new Helper().message());
    }

    static void beta() {
        class Helper {
            String message() {
                return "BETA";
            }
        }
        System.out.println(new Helper().message());
    }

    public static void main(String[] args) {
        alpha();
        beta();
    }
}
```

```bash
javac SameNameDifferentMethodsDemo.java
java SameNameDifferentMethodsDemo
```

```text
ALPHA
BETA
```

`alpha.Helper` và `beta.Helper` **không phải cú pháp Java để gọi tên local class**. Cả hai chỉ có simple name `Helper` trong phạm vi riêng của từng method body.

Nếu bạn cần một kiểu dùng chung giữa nhiều methods, hãy đặt nó thành **member class**, static nested class, top-level class hoặc dùng một interface/superclass chung; không chuyển local class thành API dùng chung bằng cách ghép tên method và tên class.

## 8. Lớp cục bộ trong nhánh `if` có scope theo braces

Một local class declaration là block statement, vì vậy thường được đặt trong **`{ ... }`** của một nhánh điều kiện.

Tạo **`ConditionalLocalClassDemo.java`**:

```java
public class ConditionalLocalClassDemo {
    public static void main(String[] args) {
        boolean enabled = true;

        if (enabled) {
            class Choice {
                String value() {
                    return "YES";
                }
            }

            Choice chosen = new Choice();
            System.out.println(chosen.value());
        } else {
            class Choice {
                String value() {
                    return "NO";
                }
            }

            Choice chosen = new Choice();
            System.out.println(chosen.value());
        }

        System.out.println("after if");
        // Choice invalid = new Choice(); // Ngoài cả hai blocks.
    }
}
```

```bash
javac ConditionalLocalClassDemo.java
java ConditionalLocalClassDemo
```

```text
YES
after if
```

**Vì sao hai tên `Choice` không xung đột?** Mỗi khai báo nằm trong block nhánh riêng; các phạm vi tên không chồng lấp.

**Vì sao sau `if` không dùng được `Choice`?** Cả hai block nhánh đều đã kết thúc. Dù chương trình đã tạo một Choice instance từ nhánh true, **không có local type name Choice nào trong block bao ngoài sau câu if**.

Nếu kết quả cần dùng sau if, hãy chọn một **kiểu được công khai ở phạm vi rộng hơn** như interface/supertype.

## 9. Trả object của local class qua interface

Một local class có thể implement một interface **được khai báo ở phạm vi đủ rộng**, để code bên ngoài block giữ và gọi object mà **không cần gọi tên local class**.

Tạo **`LocalClassFactoryDemo.java`**:

```java
interface Message {
    String text();
}

public class LocalClassFactoryDemo {
    static Message makeMessage(String prefix) {
        class LocalMessage implements Message {
            @Override
            public String text() {
                return prefix + " Java";
            }
        }

        return new LocalMessage();
    }

    public static void main(String[] args) {
        Message message = makeMessage("Hello");
        System.out.println(message.text());

        // LocalMessage x; // Không hợp lệ tại main:
        // tên LocalMessage chỉ có trong makeMessage.
    }
}
```

```bash
javac LocalClassFactoryDemo.java
java LocalClassFactoryDemo
```

```text
Hello Java
```

Phân tích:

- `LocalMessage` chỉ được đặt tên trong block method `makeMessage`.
- `Message` là top-level interface package-private trong cùng file, nên main biết tên interface.
- Factory trả object thông qua `Message`, type caller có thể nhìn thấy.
- Khi `makeMessage` kết thúc, **object LocalMessage không biến mất** nếu `message` đang giữ reference. JVM vẫn có instance với runtime class tương ứng, nhưng code tại main chỉ dùng **tên interface Message** để tương tác.

**Một tên kiểu nằm ngoài scope không đồng nghĩa runtime object không còn tồn tại.** Đây là điểm kiểm tra quan trọng nhất ở các câu hỏi phân biệt scope và lifetime.

## 10. Không thể đặt tên local class ở chữ ký method bên ngoài block

Nếu một class chỉ được khai báo bên trong method A, tên nó không nằm trong phạm vi của:

- Return type declaration của một method khác.
- Field declaration của enclosing class.
- Parameter declaration của một method khác.
- Method body khác.
- Một top-level class đặt ngoài block.

Các đoạn dưới đây là **mã sai được giữ trong comment**:

```java
class Enclosing {
    // LocalType saved;              // Không thể gọi tên class cục bộ.
    // LocalType create() { ... }    // Không thể dùng làm return type.

    Object create() {
        class LocalType {
        }
        return new LocalType();
    }

    void inspect() {
        Object x = create();         // Hợp lệ.
        // LocalType y = ...;        // Không nhìn thấy local class name.
    }
}
```

Đây là **class minh họa** không có main; dấu `...` chỉ xuất hiện trong comment, không phải placeholder cần thực hiện.

**Sửa có ý nghĩa:** Đặt một interface hoặc base type có thể dùng ở những nơi ấy, rồi cho local class implement/extend nó. Khi đó API không rò rỉ tên kiểu cục bộ.

## 11. Dùng `Object` được, nhưng chỉ thấy API của `Object`

Nếu factory trả `Object` thay vì interface cụ thể, caller có thể giữ reference nhưng **không gọi được các method chỉ có trên local class** theo static type Object.

Tạo **`LocalObjectReturnDemo.java`**:

```java
public class LocalObjectReturnDemo {
    static Object create() {
        class Local {
            String special() {
                return "SECRET";
            }

            @Override
            public String toString() {
                return special();
            }
        }

        return new Local();
    }

    public static void main(String[] args) {
        Object object = create();

        System.out.println(object);
        System.out.println(object != null);

        // object.special(); // Không biên dịch:
        // static type Object không khai báo special().
    }
}
```

```bash
javac LocalObjectReturnDemo.java
java LocalObjectReturnDemo
```

```text
SECRET
true
```

`Object.toString()` là method có sẵn trên Object và được local class override, nên gọi `System.out.println(object)` có thể hiển thị SECRET.

**Không kết luận:** vì instance có runtime type Local thì biến Object ở mọi vị trí khác biết tên Local để cast. Nếu caller cần API `special()`, dùng interface công khai thích hợp, không dùng reflection hoặc tên compiler-generated làm đường chính.

## 12. Dùng tên qua superclass trong cùng package

Không nhất thiết interface mới giữ được object. Local class cũng có thể **extends một superclass có phạm vi rộng hơn**.

Tạo **`LocalSubclassDemo.java`**:

```java
abstract class Operation {
    abstract int run();
}

public class LocalSubclassDemo {
    static Operation create(int amount) {
        class Addition extends Operation {
            @Override
            int run() {
                return amount + 1;
            }
        }

        return new Addition();
    }

    public static void main(String[] args) {
        Operation operation = create(9);
        System.out.println(operation.run());
    }
}
```

```bash
javac LocalSubclassDemo.java
java LocalSubclassDemo
```

```text
10
```

- `Addition` chỉ có tên trong method `create`.
- `Operation` là supertype visible cho main.
- Runtime polymorphism gọi override `run()` trên instance Addition sau khi factory method kết thúc.

**Đây không phải “lớp cục bộ có scope mở rộng qua class cha”**: chỉ có tên `Operation` rộng hơn; tên `Addition` vẫn giới hạn trong method create.

## 13. Phạm vi trong vòng lặp: khai báo có thể được chạy nhiều lần, tên vẫn theo block

Khai báo local class trong body block của một vòng lặp hợp lệ. Mỗi vòng có thể tạo một **instance mới**, nhưng tên local class chỉ tồn tại ở **vùng source code đã định nghĩa**.

Tạo **`LocalClassInLoopDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LocalClassInLoopDemo {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            int index = i;

            class Printer implements Runnable {
                @Override
                public void run() {
                    System.out.println("index=" + index);
                }
            }

            tasks.add(new Printer());
        }

        for (Runnable task : tasks) {
            task.run();
        }

        // Printer p; // Không nằm trong scope của block vòng for.
    }
}
```

```bash
javac LocalClassInLoopDemo.java
java LocalClassInLoopDemo
```

```text
index=0
index=1
index=2
```

Điểm cần hiểu:

1. Dòng `class Printer` nằm bên trong **block body của for**.
2. Trong phần còn lại của block body ấy, có thể tạo `new Printer()`.
3. Khi ra khỏi block for, `Printer` không còn là tên kiểu visible ở block main.
4. Các `Runnable` objects đã được thêm vào `tasks` **vẫn tồn tại**; khi gọi `run()` sau vòng lặp, mỗi instance trả giá trị `index` đã capture.
5. `index` được khai báo mới ở mỗi lần đi vào block vòng lặp và không được gán lại sau đó, nên effectively final cho instance tương ứng.

**Lưu ý:** Trong ví dụ trên, không nói mỗi vòng lặp tạo một *loại class mới* khác nhau. Đó là **một khai báo lớp ở một vị trí source**, được sử dụng nhiều lần để tạo objects.

## 14. `switch`, `try` và những block khác: tìm dấu `{ }` thật sự

Phạm vi tên local class phụ thuộc vào **vị trí khai báo và block trực tiếp bao quanh**, không chỉ vào tên cấu trúc điều khiển.

Tạo **`TryBlockLocalClassDemo.java`**:

```java
public class TryBlockLocalClassDemo {
    public static void main(String[] args) {
        try {
            class ResourceNote {
                String text() {
                    return "TRY";
                }
            }

            System.out.println(new ResourceNote().text());
        } catch (RuntimeException ex) {
            System.out.println("ERROR");
            // ResourceNote note; // Không nhìn thấy từ catch.
        }

        System.out.println("END");
        // ResourceNote note; // Cũng không nhìn thấy sau try.
    }
}
```

```bash
javac TryBlockLocalClassDemo.java
java TryBlockLocalClassDemo
```

```text
TRY
END
```

`ResourceNote` được khai báo **bên trong try block**; catch block không thuộc phạm vi ấy. Khai báo này không “vươn” qua catch hoặc sau try.

**Cẩn thận với switch:** Những dạng switch khác nhau có quy tắc block, switch statement groups và switch expressions riêng. Đừng suy đơn giản rằng “mỗi case luôn tự có scope mới”. Khi dùng local class trong một nhánh switch, cách rõ ràng, ít nhầm là đặt phần logic của nhánh trong một block có braces riêng, rồi kiểm theo ranh giới block ấy.

### Hai nhánh switch có block rõ ràng

Đoạn code sau là **một method minh họa**, không có main riêng:

```java
void show(int kind) {
    switch (kind) {
        case 1: {
            class Marker {
                String text() {
                    return "ONE";
                }
            }
            System.out.println(new Marker().text());
            break;
        }
        default: {
            class Marker {
                String text() {
                    return "OTHER";
                }
            }
            System.out.println(new Marker().text());
        }
    }
}
```

Hai `Marker` ở hai block tách biệt được đặt tên giống nhau có chủ đích; chúng không tạo một Marker type có scope bao phủ mọi case.

## 15. Phạm vi của tên class khác với phạm vi của tên biến

Xét:

```java
void example() {
    class Box {
    }

    Box first = new Box();

    {
        Box second = new Box();
    }

    Box third = new Box();
    // second không nhìn thấy ở đây,
    // còn Box vẫn nhìn thấy vì class khai báo ở block ngoài.
}
```

Đây là **instance method minh họa**.

- Tên **`Box`** được khai báo ở outer block và vẫn trong scope đến cuối outer block.
- Tên biến local **`second`** được khai báo trong inner block và hết scope khi inner block đóng.
- `Box` vẫn được dùng để khai báo `third`.
- Việc biến second hết scope không tự hủy object lập tức, và cũng không hủy định nghĩa class Box.

**Phân biệt thêm:** Java có những không gian tên/lookup rules dành cho types và variables. Đừng dùng chuyện một biến cùng tên để suy chắc chắn một local class name bị che theo cách giống nhau; phải kiểm lookup theo đúng ngữ cảnh cú pháp đang yêu cầu một **type name** hay một **expression name**.

## 16. “Phạm vi” không có nghĩa “quyền truy cập”

Đây là hai khái niệm khác nhau:

- **Scope / lexical visibility:** Ở dòng code nào tên `Local` có thể được dùng để đặt kiểu, tạo instance hoặc gọi constructor?
- **Access control:** Nếu tên/type đã có thể được sử dụng, quy tắc `public`/package-private/`protected`/`private` cho phép truy cập thành viên nào?

Local class không khai báo trực tiếp như public API ở cấp class:

```java
void make() {
    // public class Local { } // Không hợp lệ như local class.
    class Local {
    }
}
```

Đây là mảnh code trong class hợp lệ. Local class declaration không nhận modifier `public` như một top-level public class. Dù member methods của local class có thể public nếu contract yêu cầu, tên **Local** vẫn không thoát ra khỏi block.

**Tương tự:** Một local class có thể implements public interface và instance được trả ra ngoài; điều đó **không làm tên local class trở thành public**.

## 17. Có thể truy cập biến local của enclosing method, nhưng phải effectively final

Local class có thể tham chiếu tới local variables và parameters của enclosing method khi những biến đó **final hoặc effectively final**.

Tạo **`CapturedValueLocalClassDemo.java`**:

```java
public class CapturedValueLocalClassDemo {
    static Runnable create(String prefix) {
        int count = 3;

        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println(prefix + "=" + count);
            }
        }

        return new LocalTask();
    }

    public static void main(String[] args) {
        Runnable task = create("ITEM");
        task.run();
    }
}
```

```bash
javac CapturedValueLocalClassDemo.java
java CapturedValueLocalClassDemo
```

```text
ITEM=3
```

`prefix` là parameter; `count` là local variable. Không có assignment nào thay đổi chúng sau khi nhận/khởi tạo, nên cả hai effectively final.

Khi `create` trả về, biến `count` không còn được dùng qua tên ở main, nhưng local task vẫn có dữ liệu capture theo contract. Tương tự, **tên `LocalTask` chỉ có trong create**, còn object Runnable tiếp tục tồn tại.

### Một ví dụ lỗi compile-time do capture

```java
void wrong() {
    int count = 1;

    class Local {
        int read() {
            return count;
        }
    }

    count++; // Khi cùng biến count đã được local class capture,
             // nó không còn effectively final.
}
```

Đây là **mã minh họa lỗi**, không phải chương trình runnable. Vấn đề ở đây là **capture biến local**, không phải tên `Local` hết scope.

**Phân biệt:**
- Phạm vi tên lớp `Local`: xác định nơi có thể viết `new Local()`.
- Effectively-final của `count`: xác định liệu local class có thể capture biến ấy.
- Vòng đời object Local: phụ thuộc vào references còn giữ, không đồng nhất với hai điều trên.

## 18. Thay đổi state của object được capture khác gán lại biến capture

Điều kiện effectively final áp dụng cho **biến tham chiếu**, không có nghĩa mọi object mà reference trỏ tới đều immutable.

Tạo **`MutableCapturedObjectDemo.java`**:

```java
public class MutableCapturedObjectDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");

        class Printer {
            void addAndPrint(String suffix) {
                builder.append(suffix);
                System.out.println(builder);
            }
        }

        Printer printer = new Printer();

        printer.addAndPrint("1");
        builder.append("2");
        printer.addAndPrint("3");
    }
}
```

```bash
javac MutableCapturedObjectDemo.java
java MutableCapturedObjectDemo
```

```text
A1
A12
A123
```

`builder` vẫn effectively final vì không bị **gán reference mới**. Nhưng `StringBuilder` là mutable, nên các lần `append` đổi object nội dung.

**Điểm liên quan scope:** Local class Printer có tên trong phần còn lại của main block. Biến builder có thể được sử dụng khi capture thỏa rule; mutable state được quan sát qua alias.

Đừng nhầm Java local class capture với một “bản sao sâu” của object được capture; thường đó vẫn là reference tới cùng object.

## 19. `this` trong lớp cục bộ là đối tượng của chính lớp ấy

Lớp cục bộ là một class, không phải lambda expression. Trong instance method của local class, `this` trỏ **local-class object**.

Tạo **`LocalThisDemo.java`**:

```java
class Outer {
    private final String label = "OUTER";

    void run() {
        class Local {
            private final String label = "LOCAL";

            void show() {
                System.out.println(this.label);
                System.out.println(Outer.this.label);
            }
        }

        new Local().show();
    }
}

public class LocalThisDemo {
    public static void main(String[] args) {
        new Outer().run();
    }
}
```

```bash
javac LocalThisDemo.java
java LocalThisDemo
```

```text
LOCAL
OUTER
```

- `this.label`: field thuộc Local object.
- `Outer.this.label`: field thuộc enclosing Outer instance trong instance method Outer.run.
- `Local` chỉ có scope trong phần còn lại của block `run()`.

**Không suy rằng** Local class có implicit Outer instance ở mọi trường hợp. Nếu local class khai báo trong **static method**, không có implicit `Outer.this`; code cần một Outer reference tường minh nếu muốn dùng instance state.

## 20. Local class trong static method: vẫn khai báo được, không có `Outer.this`

Một local class có thể xuất hiện trong **static method**. Quy tắc scope của **tên local class** không đổi, nhưng việc truy cập enclosing Outer instance có khác biệt.

Tạo **`StaticMethodLocalClassDemo.java`**:

```java
class Outer {
    private final String label;

    Outer(String label) {
        this.label = label;
    }

    static String run(Outer owner) {
        class Local {
            String text() {
                // Không có Outer.this trong static context.
                return owner.label;
            }
        }

        Local result = new Local();
        return result.text();
    }
}

public class StaticMethodLocalClassDemo {
    public static void main(String[] args) {
        Outer owner = new Outer("EXPLICIT");
        System.out.println(Outer.run(owner));
    }
}
```

```bash
javac StaticMethodLocalClassDemo.java
java StaticMethodLocalClassDemo
```

```text
EXPLICIT
```

`owner` là method parameter effectively final, được capture. `Local` là tên kiểu local nằm trong scope từ khai báo tới cuối static method block.

**Không nhầm** hai câu sau:

- “Có thể khai báo local class trong static method?” → Có.
- “Có thể viết `Outer.this` trong local class được khai báo từ static method mà không có enclosing Outer instance?” → Không.

## 21. Local class và member nested class có những phạm vi tên khác nhau

So sánh nhanh:

| Đặc điểm | Local class | Member nested class |
| --- | --- | --- |
| Vị trí khai báo | Trong block method/constructor/initializer hợp lệ | Trong body class/interface theo rules |
| Tên có scope bao toàn enclosing class? | Không; theo phần còn lại của block khai báo | Được khai báo là member type và được resolve theo các quy tắc member-type lookup |
| Có thể viết `Outer.Local` từ bên ngoài? | Không | Có thể với member type nếu access cho phép |
| Các method khác trong Outer dùng tên trực tiếp? | Không nếu nằm ngoài scope block | Có thể khi member type visible |
| Có thể tạo instance sau khi ra khỏi block? | Có, qua interface/supertype/reference đã giữ | Có |
| Có phải mọi nested class đều inner? | Không; có static nested class | Member nested có thể static hoặc non-static |
| Có cần implicit outer instance? | Tùy context khai báo local class | Non-static member inner thì có enclosing instance, static nested thì không |

**Câu phải nhớ:** Local class có tên nằm trong **block**, member nested class có tên là **member type của enclosing class**. Không dùng cùng một cách qualified name cho hai loại.

### Ví dụ member class có thể dùng từ method khác

Tệp **`MemberVersusLocalDemo.java`**:

```java
public class MemberVersusLocalDemo {
    static class Member {
        String name() {
            return "MEMBER";
        }
    }

    static void first() {
        class Local {
            String name() {
                return "LOCAL";
            }
        }

        System.out.println(new Local().name());
    }

    static void second() {
        System.out.println(new Member().name());
        // new Local(); // Local của first không visible ở đây.
    }

    public static void main(String[] args) {
        first();
        second();
    }
}
```

```bash
javac MemberVersusLocalDemo.java
java MemberVersusLocalDemo
```

```text
LOCAL
MEMBER
```

Member là static nested member class của outer class; Local chỉ tồn tại bằng tên trong block của `first`.

## 22. Local class không tự có qualified name dành cho source client

Compiler/JVM có thể tạo tên nhị phân (*binary name*) nội bộ cho local classes, thường chứa dấu `$` và số thứ tự. Nhưng đó **không phải cú pháp truy cập kiểu trong source** được đảm bảo ổn định cho API.

Không viết:

```java
// Outer$1Local x;       // Không phải cách gọi tên local class ổn định.
// Outer.Local x;        // Local không phải member type Outer.
// someMethod.Local x;   // Java không dùng method name để qualify type.
```

**Không dựa vào** tên file class sinh ra bởi compiler để thay thế scope. Một thay đổi vị trí/structure source code có thể làm compiler-generated artifacts khác đi.

Reflection có thể quan sát runtime class của một object local:

```java
Object instance = ...; // Minh họa: instance từ local class.
Class<?> runtimeType = instance.getClass();
```

Đó là runtime reflection, không làm Java compiler chấp nhận tên kiểu `Local` ở vị trí nằm ngoài lexical scope.

### Ví dụ reflection an toàn, không đoán tên binary

Tạo **`LocalClassReflectionDemo.java`**:

```java
public class LocalClassReflectionDemo {
    static Object create() {
        class LocalValue {
            @Override
            public String toString() {
                return "VALUE";
            }
        }

        return new LocalValue();
    }

    public static void main(String[] args) {
        Object value = create();
        Class<?> type = value.getClass();

        System.out.println(type.isLocalClass());
        System.out.println(value.toString());
    }
}
```

```bash
javac LocalClassReflectionDemo.java
java LocalClassReflectionDemo
```

```text
true
VALUE
```

`Class.isLocalClass()` cho biết runtime class là local class theo API. Chương trình không in `getName()` hay `getCanonicalName()` vì không nên dùng compiler-generated name như hợp đồng output.

## 23. Local class khác anonymous class và lambda expression

Ba hình thức đều có thể tạo một hành vi cục bộ nhưng khác về tên và kiểu:

- **Local named class**: có tên kiểu trong phạm vi block kể từ khai báo; có thể tạo nhiều instances bằng `new Local()` trong phạm vi ấy.
- **Anonymous class**: không có một tên lớp source-level mới để gọi lại bằng `new AnonymousName()`; expression trực tiếp tạo object.
- **Lambda expression**: không phải khai báo một local class có tên và có quy tắc lexical `this` khác anonymous class.

### Ví dụ so sánh không phụ thuộc runtime class name

Tạo **`LocalAnonymousLambdaDemo.java`**:

```java
public class LocalAnonymousLambdaDemo {
    public static void main(String[] args) {
        class LocalAction implements Runnable {
            @Override
            public void run() {
                System.out.println("LOCAL");
            }
        }

        Runnable named = new LocalAction();
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("ANONYMOUS");
            }
        };
        Runnable lambda = () -> System.out.println("LAMBDA");

        named.run();
        anonymous.run();
        lambda.run();
    }
}
```

```bash
javac LocalAnonymousLambdaDemo.java
java LocalAnonymousLambdaDemo
```

```text
LOCAL
ANONYMOUS
LAMBDA
```

`LocalAction` là tên kiểu có scope trong phần còn lại của main. Anonymous class không có tên để khai báo `new Anonymous()`, còn lambda dùng target type `Runnable` theo functional-interface rules.

Tất cả vẫn có thể được giữ và gọi thông qua biến `Runnable` nếu API phù hợp.

## 24. Local record không hoàn toàn giống local class thường về capture

Java 17 hỗ trợ **local record declarations** trong block. Record mang tính chất khác: local record là **implicitly static**, không capture các local variables từ enclosing method như một local inner class thường.

Tệp **`LocalRecordContrastDemo.java`**:

```java
public class LocalRecordContrastDemo {
    public static void main(String[] args) {
        int offset = 10;

        class LocalAdder {
            int add(int value) {
                return value + offset;
            }
        }

        record Pair(int left, int right) {
            int sum() {
                return left + right;
            }
        }

        System.out.println(new LocalAdder().add(5));
        System.out.println(new Pair(2, 3).sum());
    }
}
```

```bash
javac LocalRecordContrastDemo.java
java LocalRecordContrastDemo
```

```text
15
5
```

**Phân biệt hai mặt:**

- Tên `LocalAdder` và `Pair` đều có phạm vi trong block theo cách khai báo tương ứng.
- Nhưng `LocalAdder` có thể capture effectively-final `offset`.
- `Pair` là local record, không được tự capture `offset` trong instance methods của record; muốn dùng giá trị offset thì đưa nó vào component/parameter hay cấu trúc dữ liệu theo contract.

Không suy rằng **mọi loại local type declaration** cho phép capture giống member/local inner classes.

## 25. Một local class tự tạo node liên kết: tên dùng trong chính body

Ví dụ thực tiễn cho self-reference:

Tạo **`LocalLinkedNodesDemo.java`**:

```java
public class LocalLinkedNodesDemo {
    public static void main(String[] args) {
        class Node {
            final int value;
            Node next;

            Node(int value) {
                this.value = value;
            }
        }

        Node first = new Node(1);
        Node second = new Node(2);
        first.next = second;

        int sum = 0;
        for (Node node = first; node != null; node = node.next) {
            sum += node.value;
        }

        System.out.println(sum);
    }
}
```

```bash
javac LocalLinkedNodesDemo.java
java LocalLinkedNodesDemo
```

```text
3
```

Tại thân `class Node`, khai báo field `Node next` là hợp lệ. Sau khai báo, main dùng Node cho biến, constructor và biến lặp for.

**Chú ý:** Ví dụ chỉ cho hai nodes, không có cycle; vòng for dừng ở null. Khi dùng local class kiểu Node cho thuật toán graph lớn hơn, scope không cản tạo linked objects trong lúc tên còn visible, nhưng lớp chỉ dùng nội bộ cho thuật toán ấy.

## 26. Một factory trong block con: đối tượng thoát ra, tên không thoát

Phạm vi có thể hẹp hơn cả method nếu khai báo trong block con. Để sử dụng object sau block, cần **một biến có kiểu thích hợp được khai báo bên ngoài block**.

Tạo **`EscapingLocalInstanceDemo.java`**:

```java
public class EscapingLocalInstanceDemo {
    public static void main(String[] args) {
        Runnable action;

        {
            String label = "BLOCK";

            class LocalAction implements Runnable {
                @Override
                public void run() {
                    System.out.println(label);
                }
            }

            action = new LocalAction();
        }

        action.run();

        // LocalAction x; // Không visible sau block con.
    }
}
```

```bash
javac EscapingLocalInstanceDemo.java
java EscapingLocalInstanceDemo
```

```text
BLOCK
```

**Hai phạm vi cần chú ý:**

- Biến `action` được khai báo tại block main, nên vẫn trong scope sau block con và được definite assigned trước khi gọi.
- Tên `LocalAction` chỉ có trong block con, nên không thể dùng để khai báo type sau block ấy.

Lúc gọi `action.run()`, đối tượng LocalAction vẫn còn. Điều này cũng chứng minh local variable `label` có thể được capture; việc lexical scope của biến kết thúc không đồng nghĩa dữ liệu mà object đã capture phải bị mất.

## 27. Tại sao không khai báo local class làm một API công khai?

Local class phù hợp khi implementation chỉ cần trong một method/block, ví dụ:

- Một helper ngắn cho thuật toán.
- Một object implement strategy/interface chỉ dành cho một factory.
- Một comparator/callback cần trạng thái local (khi không dùng lambda).
- Một cấu trúc dữ liệu tạm trong một phép tính.
- Một xử lý cục bộ, không cần tái sử dụng bằng tên ở methods khác.

Nếu nhiều methods hoặc callers cần **đặt tên kiểu đó**, local class thường không phù hợp làm API, vì:

1. Tên local class không visible ở các methods khác.
2. Không thể khai báo return type chính là local class trên method signature ở ngoài scope.
3. Code bên ngoài khó sử dụng các members không có ở public interface/superclass.
4. Nếu một implementation được dùng ở nhiều nơi, copy/paste local declarations có thể tạo nhiều types khác nhau với cùng tên và tăng duplication.

**Hướng thay thế:** member class, static nested class, top-level class, hoặc public interface cộng một implementation local tùy nhu cầu.

Không có ý nghĩa rằng local class “chậm hơn” hoặc “ít hướng đối tượng hơn”. Đây chủ yếu là quyết định **phạm vi tên và mức độ ẩn implementation**.

## 28. Những lỗi biên dịch phổ biến

| Sai lầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Dùng `new Local()` trước dòng `class Local` | Tên local class chưa vào scope | Đặt khai báo trước vị trí dùng |
| Dùng `Local x` sau `}` đóng block khai báo | Đã hết scope | Dùng interface/supertype bên ngoài |
| Dùng `Local` ở method khác | Scope chỉ là block của method khai báo | Member type hoặc interface |
| Dùng `Outer.Local` | Local không phải member class | Chọn type có scope phù hợp |
| Khai báo `public class Local` trong block | Không phải modifier hợp lệ cho local class declaration | Chỉ dùng cú pháp local class hợp lệ |
| Cho hai local classes trùng tên vào cùng một vùng chồng lấp | Name conflict theo rules | Tách blocks hoặc đổi tên |
| Mong `if (x) class Local { }` như một statement không có block | Local class declaration là block declaration | Đặt trong `{...}` |
| Xem `Object result = create()` là có thể gọi `result.special()` | Static type Object không khai báo special | Dùng interface có special method |
| Đòi object local class biến mất khi method return | Scope tên khác lifetime instance | Hiểu references/GC |
| Dùng biến local bị gán lại từ local class | Capture yêu cầu final/effectively final | Không reassign, hoặc thiết kế state riêng |
| Xem captured mutable object là deep copy | Chỉ reference capture, object còn mutable | Dùng immutable snapshot nếu cần |
| Nhầm `this` của local class với `Outer.this` | Hai receivers khác nhau | Qualified receiver đúng |
| Dùng `Outer.this` trong local class của static method | Không có implicit enclosing Outer instance | Truyền owner reference |
| Dự đoán tên runtime dạng `Outer$1Local` | Compiler details không ổn định cho API | Dùng `Class.isLocalClass()` khi cần reflection |
| Cho rằng trùng tên ở hai methods tạo cùng type | Hai khai báo riêng | Dùng common interface/supertype |
| Nhầm local record với capturing local class | Local record implicitly static | Truyền giá trị qua record components |
| Chỉ kiểm code chạy trong block mà không kiểm API bên ngoài | Bỏ sót type-name scope boundary | Test phần trước/sau khai báo và sau block |

## 29. Câu hỏi tự luyện có đáp án

**Câu 1.** Một local class được khai báo trong block của method. Phạm vi tên class là gì?

**Đáp án:** Bắt đầu từ khai báo (bao gồm khai báo) đến hết block trực tiếp bao quanh, bao gồm các block lồng trong phần còn lại của block.

**Câu 2.** Có dùng `new Local()` trước `class Local` được không?

**Đáp án:** Không dùng được *khai báo local class ấy* trước khi nó vào scope.

**Câu 3.** Có thể viết `Local next;` ngay bên trong body của `class Local` không?

**Đáp án:** Có; local class có thể tự dùng tên trong chính body như self-referential linked node.

**Câu 4.** Local class được khai báo trong một block con; code ở block cha sau khi block con đóng có nhìn thấy tên không?

**Đáp án:** Không.

**Câu 5.** Local class khai báo trong outer block có dùng được trong block con phía sau không?

**Đáp án:** Có, nếu block con nằm trong phần còn lại của phạm vi bao ngoài.

**Câu 6.** Hai blocks tách biệt đều khai báo `class Result` có luôn xung đột không?

**Đáp án:** Không nếu scopes không chồng lấp và từng declaration tuân thủ rules; chúng là hai types khác nhau.

**Câu 7.** Hai methods khác nhau có thể khai báo local class cùng tên `Worker` không?

**Đáp án:** Có. Tên chỉ visible trong block method tương ứng.

**Câu 8.** Sau khi factory trả object của local class dưới type interface, object còn dùng được không?

**Đáp án:** Có, qua methods của interface/supertype visible.

**Câu 9.** Nếu trả object dưới static type `Object`, có gọi được method chỉ có trong local class không?

**Đáp án:** Không theo static type Object; dùng interface khai báo method mong muốn.

**Câu 10.** `SomeMethod.Local` có phải cú pháp gọi tên kiểu local class không?

**Đáp án:** Không. Local class không phải member type có thể qualified bằng method name.

**Câu 11.** Scope của biến local tham chiếu một object có đồng nghĩa với vòng đời của object không?

**Đáp án:** Không. Object có thể sống tiếp nếu một reference khác vẫn giữ.

**Câu 12.** Local class có được dùng parameter của enclosing method không?

**Đáp án:** Có nếu parameter final/effectively final và việc dùng đáp ứng các quy tắc Java khác.

**Câu 13.** Capture `StringBuilder` nghĩa là builder không thể mutate nữa?

**Đáp án:** Không. Reference variable effectively final nhưng object được trỏ tới có thể mutable.

**Câu 14.** Local class khai báo trong static method có hợp lệ không?

**Đáp án:** Có. Nhưng không có `Outer.this` implicit trong static context.

**Câu 15.** Trong instance method của local class, `this` là object nào?

**Đáp án:** Object của local class đó.

**Câu 16.** Có thể khai báo local record và dùng tên record trong phần còn lại của block không?

**Đáp án:** Có. Nhưng local record implicitly static, khác local inner class thường về capture.

**Câu 17.** Local class và anonymous class khác gì về tên?

**Đáp án:** Local class có tên trong block; anonymous class không có tên source-level mới để tái sử dụng.

**Câu 18.** Dùng `Class.isLocalClass()` có giúp gọi tên class ngoài scope trong source không?

**Đáp án:** Không. Reflection quan sát runtime type, không thay compile-time name scope.

**Câu 19.** Khi viết switch có các local classes cùng tên, cần chú ý gì?

**Đáp án:** Ranh giới lexical block thật sự của mỗi declaration; dùng braces từng nhánh khi muốn scopes độc lập.

**Câu 20.** Nhiều modules cần tạo cùng helper class, nên chọn local hay member class?

**Đáp án:** Nếu cần tên reusable và contract chung, chọn member/static nested/top-level type; local class phù hợp khi implementation chỉ cần trong block.

## 30. Checklist khi review code có lớp cục bộ

- [ ] Đã xác định đúng **dòng `class Local`**?
- [ ] Đã tìm **block trực tiếp bao quanh** khai báo?
- [ ] Có dòng sử dụng tên Local **trước** khi khai báo không?
- [ ] Có dòng dùng Local **sau** khi block chứa khai báo đóng không?
- [ ] Code trong các block con có thực sự nằm trong phần còn lại của scope không?
- [ ] Có hai local types trùng tên với scopes chồng lấp không?
- [ ] Nếu hai blocks tách biệt trùng tên, đã hiểu chúng là **hai classes khác nhau**?
- [ ] Có nhánh `if`, `try`, `switch`, vòng lặp khiến ranh giới block dễ nhầm?
- [ ] Có đang nhầm local class với member nested class (`Outer.Local`)?
- [ ] Nếu caller ngoài block cần object, có **interface/supertype visible** phù hợp?
- [ ] Không sử dụng method đặc thù local class qua biến chỉ có static type Object?
- [ ] Không nhầm name scope với variable scope hoặc runtime object lifetime?
- [ ] Nếu local class capture parameter/variable, nó có final/effectively final?
- [ ] Nếu captured value là mutable reference, đã xét aliasing và state changes?
- [ ] Nếu local class ở static method, đã tránh implicit `Outer.this`?
- [ ] Nếu local class ở instance method, đã hiểu `this` và `Outer.this`?
- [ ] Có vô tình dựa trên compiler-generated binary names?
- [ ] Có cần member/static nested/top-level class thay cho một local type khó tái sử dụng?
- [ ] Đã kiểm khi local class nằm trong loop: type declaration và instance/captured values khác nhau?
- [ ] Không nhầm local record với local inner class ở việc capture?
- [ ] Ví dụ runnable Java 17+ có đúng public class/file name và lệnh `javac`/`java`?
- [ ] Output mô tả value và order do code xác định, không dựa trên hash/runtime binary name?

---

**Ghi nhớ cuối bài:** Tên của một **lớp cục bộ** trong Java có phạm vi **từ chỗ khai báo (bao gồm khai báo) đến hết block trực tiếp chứa nó**. Có thể dùng tên ấy trong các block con phía sau, nhưng **không được dùng trước khai báo hoặc sau khi block khai báo đã đóng**. Các block/method tách biệt có thể khai báo local classes trùng tên mà tạo ra **các kiểu khác nhau**. Khi cần sử dụng đối tượng sau khi rời scope tên class, hãy giữ nó qua **interface hoặc superclass có phạm vi đủ rộng**; object có thể tiếp tục tồn tại dù tên local class không còn khả dụng. Cuối cùng, đừng nhầm phạm vi **tên kiểu** với capture biến final/effectively-final, receiver `this`/`Outer.this` hoặc vòng đời runtime instance.