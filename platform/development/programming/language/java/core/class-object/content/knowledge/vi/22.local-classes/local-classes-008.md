# Khi nào lớp cục bộ giúp giữ chi tiết triển khai gần nơi dùng trong Java

## 1. Ý tưởng cốt lõi

**Lớp cục bộ (*local class*)** là một lớp được khai báo trong một block, thường ngay bên trong một method, constructor hoặc một block khởi tạo. Nó giúp gom **một phần triển khai chỉ phục vụ một thao tác** vào một kiểu có tên, có fields, constructor và methods riêng, nhưng không phải đưa kiểu đó lên phạm vi rộng hơn.

Ví dụ định hướng:

```java
void process() {
    class Helper {
        void firstStep() {
            // ...
        }

        void secondStep() {
            // ...
        }
    }

    Helper helper = new Helper();
    helper.firstStep();
    helper.secondStep();
}
```

Đây là **mảnh minh họa**, không phải một chương trình chạy độc lập. Điểm đáng chú ý là người đọc thấy khai báo `Helper` **ngay trước nơi dùng**, không phải tìm một file/class khác để hiểu một chi tiết chỉ có giá trị trong `process()`.

Khi nào đây là lựa chọn tốt?

- Helper thực sự là **chi tiết triển khai của đúng một method hoặc một block**.
- Logic có đủ **trạng thái hay nhiều phương thức liên quan** để đáng được đặt trong một class có tên.
- Helper cần dùng một số **parameters hoặc local variables effectively final** ngay tại nơi khai báo.
- Có một interface/superclass ổn định mà helper implement, nhưng **concrete type không cần lộ ra API**.
- Đưa helper thành member/top-level class sẽ làm tăng số khái niệm phải tìm đọc mà **không đem lại tái sử dụng thực chất**.

Khi nào không nên?

- Chỉ cần một biểu thức/hành vi rất ngắn phù hợp với **lambda**.
- Một helper thực sự được dùng bởi **nhiều methods** hoặc nhiều modules.
- Implementation đủ lớn/phức tạp đến mức để giữa method khiến việc đọc luồng chính khó hơn.
- Helper cần một public, independently testable API với tên kiểu truy cập từ nhiều nơi.
- Một static nested class nhận dependencies rõ ràng sẽ đơn giản hơn một local class capture quá nhiều biến.

> **Mục tiêu của lớp cục bộ không phải viết ít dòng bằng mọi giá, mà là giữ một ý tưởng phụ ở đúng nơi nó phục vụ, trong khi vẫn có cấu trúc đặt tên đủ rõ.**

Bài này trình bày tiêu chí lựa chọn, ví dụ Java 17+ biên dịch/chạy độc lập, những ranh giới của capture, scope, quản lý state và cách tổ chức code để tránh biến lớp cục bộ thành một “class lớn bị giấu trong method”.

## 2. Ba mức nơi đặt helper

Khi một đoạn logic bắt đầu có danh tính riêng, ta thường cân nhắc ba vùng chứa:

| Vị trí | Phù hợp khi | Chi phí/cảnh báo |
| --- | --- | --- |
| **Local class** trong method | Chỉ một workflow dùng; cần methods/state riêng | Tên kiểu không dùng được ngoài block; method có thể quá dài |
| **Member class** hoặc **static nested class** | Vài methods trong enclosing class dùng lại; trách nhiệm gắn với class | Tăng số members, có thể mở rộng surface không cần thiết |
| **Top-level class** | Nhiều modules dùng lại; có API và tests độc lập | Thêm file và cấp abstraction rộng hơn |

Không phải class càng “ẩn” càng tốt. Nguyên tắc là **đặt abstraction ở phạm vi hẹp nhất vẫn phù hợp trách nhiệm và khả năng tái sử dụng**. Khi chỉ một method cần helper, lớp cục bộ có thể là mức hẹp tự nhiên.

### So với một đoạn code không đặt class

Nếu helper chỉ gói một phép cộng hoặc một điều kiện, thêm class có thể làm code dài hơn và tăng cognitive load. Nếu logic có hai hay ba bước, một ít mutable state và một hợp đồng riêng, class có tên giúp đặt **danh tính cho cụm trách nhiệm**.

## 3. Ví dụ runnable: helper phục vụ riêng một method

Tạo tệp **`LocalHelperWorkflowDemo.java`**:

```java
import java.util.List;

public class LocalHelperWorkflowDemo {
    static void printAccepted(List<String> inputs) {
        String prefix = "OK:";

        class Checker {
            boolean valid(String item) {
                return item != null && !item.isBlank();
            }

            String present(String item) {
                return prefix + item.trim();
            }
        }

        Checker checker = new Checker();
        for (String item : inputs) {
            if (checker.valid(item)) {
                System.out.println(checker.present(item));
            }
        }
    }

    public static void main(String[] args) {
        printAccepted(List.of(" Java ", "", " OOP "));
    }
}
```

```bash
javac LocalHelperWorkflowDemo.java
java LocalHelperWorkflowDemo
```

**Standard output:**

```text
OK:Java
OK:OOP
```

Ở đây:

1. `Checker` có hai trách nhiệm liên quan: **kiểm tra** và **trình bày**.
2. Nó chỉ có ý nghĩa trong `printAccepted`.
3. Biến `prefix` có giá trị cố định trong mỗi lần gọi và được local class dùng vì effectively final.
4. Không cần thêm member `Checker` trong `LocalHelperWorkflowDemo`, bởi các methods khác hiện không dùng tới helper ấy.
5. Method chính đọc được như một workflow: tạo Checker, duyệt đầu vào, kiểm hợp lệ, in kết quả.

**Một chi tiết về dữ liệu:** `List.of(...)` không nhận null elements; ví dụ này thử chuỗi rỗng, không thử null. Method `valid` vẫn xử lý null nếu một caller truyền một List implementation có null.

### Giá trị thiết kế

Tên `Checker` nói rõ “đây là một đối tượng nhỏ chuyên xử lý hai thao tác của workflow”. Nó có thể thay các đoạn điều kiện/lắp chuỗi lặp lại ngay trong một method. Nhưng nếu helper chỉ có một dòng `item.trim()` và không có nhiều logic, tạo class như vậy chưa chắc đáng giá.

## 4. Khi nào một local class tốt hơn lambda?

Lambda rất phù hợp với một hàm ngắn theo functional interface:

```java
java.util.function.Predicate<String> nonBlank =
        text -> text != null && !text.isBlank();
```

Đây là mảnh code trong một method. Nếu toàn bộ nhu cầu chỉ là predicate đó, **lambda dễ đọc hơn** local class implement Predicate bằng một method vài dòng.

Local class đáng cân nhắc khi cần **một hoặc nhiều dấu hiệu**:

- Có **nhiều methods** phối hợp, như `validate`, `explainFailure`, `normalize`.
- Có **trạng thái riêng trên mỗi instance** và một constructor xác định state.
- Cần một **tên kiểu thể hiện một trách nhiệm nhỏ**, giúp đọc/trace behavior.
- Cần implement một interface có **nhiều abstract methods** (không phải functional interface).
- Cần các phương thức phụ private để cấu trúc logic, thay vì một lambda có body dài.
- Cần tạo **nhiều instances độc lập** với cấu hình/trạng thái khác nhau trong block.

Không phải cứ có mutable state là bắt buộc local class: lambda có thể capture object mutable hoặc một object state holder khác, nhưng local class có fields riêng thường làm **ownership của state** rõ hơn.

## 5. Ví dụ: local class với state độc lập mỗi lần tạo

Một ví dụ mà lambda ngắn không mô tả tự nhiên là bộ đếm có trạng thái của từng generator.

Tạo **`LocalSequenceGeneratorDemo.java`**:

```java
import java.util.function.IntSupplier;

public class LocalSequenceGeneratorDemo {
    static IntSupplier sequence(int start, int step) {
        class Generator implements IntSupplier {
            private int next = start;

            @Override
            public int getAsInt() {
                int result = next;
                next += step;
                return result;
            }
        }

        return new Generator();
    }

    public static void main(String[] args) {
        IntSupplier odd = sequence(1, 2);
        IntSupplier hundreds = sequence(100, 10);

        System.out.println(odd.getAsInt());
        System.out.println(odd.getAsInt());
        System.out.println(hundreds.getAsInt());
        System.out.println(odd.getAsInt());
        System.out.println(hundreds.getAsInt());
    }
}
```

```bash
javac LocalSequenceGeneratorDemo.java
java LocalSequenceGeneratorDemo
```

```text
1
3
100
5
110
```

`Generator` là local class được khai báo tại nơi factory `sequence` tạo object. Mỗi lần gọi `new Generator()` tạo **một instance với field `next` riêng**.

`start` và `step` là method parameters **effectively final**; Generator capture chúng. Field `next` thuộc từng Generator object nên có thể thay đổi sau mỗi `getAsInt()`.

**Lưu ý concurrency:** Generator ở ví dụ có mutable `int next` và không tự thread-safe. Nếu share một IntSupplier này giữa nhiều threads, phải có chính sách đồng bộ/atomic phù hợp. Mục đích là mô tả local-class state per instance, không hứa concurrent sequence.

### Tại sao không đưa Generator lên cấp class?

Vì logic tạo Generator chỉ cần biết `start`/`step` và được dùng qua `IntSupplier`. Nếu không có nơi nào khác dùng concrete Generator type, để tên `Generator` nằm trong `sequence` giảm surface và giúp người đọc tập trung vào factory contract.

## 6. Khi cần nhiều behavior trong cùng một helper

Một local class có thể chứa vài methods có cùng mục tiêu nhưng không cần xuất hiện ở interface mà caller dùng.

Tạo **`LocalValidationDemo.java`**:

```java
public class LocalValidationDemo {
    static String describeRegistration(String username, int age) {
        class Validator {
            boolean nameValid() {
                return username != null
                        && !username.isBlank();
            }

            boolean ageValid() {
                return age >= 18 && age <= 120;
            }

            String issue() {
                if (!nameValid()) {
                    return "invalid username";
                }
                if (!ageValid()) {
                    return "invalid age";
                }
                return "accepted";
            }
        }

        Validator validator = new Validator();
        return validator.issue();
    }

    public static void main(String[] args) {
        System.out.println(describeRegistration("An", 20));
        System.out.println(describeRegistration("", 20));
        System.out.println(describeRegistration("Binh", 16));
    }
}
```

```bash
javac LocalValidationDemo.java
java LocalValidationDemo
```

```text
accepted
invalid username
invalid age
```

Các methods `nameValid`, `ageValid` và `issue` gần nhau giúp đọc invariant của thao tác registration. Không nhất thiết tạo một class riêng dùng toàn ứng dụng tên `RegistrationValidator` nếu **chỉ đúng một method** cần chúng và logic còn gọn.

**Điểm cần cân nhắc:** Nếu quy tắc username/age trở thành business rule dùng ở nhiều nơi (API, UI, batch import), giữ nhiều bản local Validator sẽ tạo nguy cơ sai khác. Khi ấy nên **trích ra service/value validator tái sử dụng**, hoặc ít nhất một named nested class và các tests chung.

## 7. Khi helper cần cấu hình riêng và constructor

Local class vẫn là class: có fields, constructor, method, initializer như các class thông thường theo những quy tắc áp dụng cho local class.

Tạo **`LocalComparatorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

record WorkItem(String code, int urgency) {
}

public class LocalComparatorDemo {
    static List<WorkItem> order(List<WorkItem> input,
                                boolean highestFirst) {
        class WorkOrder implements Comparator<WorkItem> {
            private final int direction;

            WorkOrder(boolean highestFirst) {
                direction = highestFirst ? -1 : 1;
            }

            @Override
            public int compare(WorkItem a, WorkItem b) {
                int priority =
                        Integer.compare(a.urgency(), b.urgency());
                if (priority != 0) {
                    return direction * priority;
                }
                return a.code().compareTo(b.code());
            }
        }

        List<WorkItem> result = new ArrayList<>(input);
        result.sort(new WorkOrder(highestFirst));
        return result;
    }

    public static void main(String[] args) {
        List<WorkItem> items = List.of(
                new WorkItem("B", 2),
                new WorkItem("A", 2),
                new WorkItem("C", 1));

        for (WorkItem item : order(items, true)) {
            System.out.println(item.code() + ":" + item.urgency());
        }
    }
}
```

```bash
javac LocalComparatorDemo.java
java LocalComparatorDemo
```

```text
A:2
B:2
C:1
```

### Vì sao ví dụ này dùng local class?

- `WorkOrder` là chính sách **chỉ dành cho method order**.
- Có một field `direction` được khởi tạo qua constructor; state là của **comparator instance**.
- Có rule so sánh chính (urgency), rule phụ (code), nên tên class và method `compare` có ý nghĩa.
- Tên của WorkOrder không cần lộ ra các phương thức khác.

### Khi nào nên viết ngắn hơn?

Nếu chỉ cần một phép sort đơn giản, ví dụ sort `String` tăng dần, `Comparator.naturalOrder()` hoặc lambda/method reference là lựa chọn tốt hơn. Class cục bộ không phải bắt buộc chỉ vì ta đang gọi `sort`.

**Lưu ý thiết kế:** `direction` chỉ nhận -1 hoặc +1, và `Integer.compare` trả -1/0/1 nên phép nhân ở đây không gây overflow. Không đổi sang phép trừ `a.urgency()-b.urgency()` nếu có nguy cơ overflow.

## 8. Khi helper implement một interface được dùng ở bên ngoài method

Điểm mạnh của local class: **ẩn concrete implementation** nhưng trả về một contract có phạm vi rộng.

Tạo **`LocalStrategyFactoryDemo.java`**:

```java
interface TextRule {
    String apply(String input);
}

public class LocalStrategyFactoryDemo {
    static TextRule prefixRule(String prefix) {
        class PrefixRule implements TextRule {
            @Override
            public String apply(String input) {
                return prefix + input;
            }
        }

        return new PrefixRule();
    }

    public static void main(String[] args) {
        TextRule rule = prefixRule("ID-");
        System.out.println(rule.apply("7"));
        System.out.println(rule.apply("8"));
    }
}
```

```bash
javac LocalStrategyFactoryDemo.java
java LocalStrategyFactoryDemo
```

```text
ID-7
ID-8
```

`PrefixRule` chỉ có tên trong `prefixRule`. Người dùng phương thức factory chỉ biết interface `TextRule`.

**Quan trọng:** Việc `prefixRule` return không phá object hay làm nó mất hành vi. Reference kiểu TextRule vẫn giữ instance của PrefixRule; method `apply` vẫn dùng giá trị `prefix` được capture.

**Đây là một chiến lược đóng gói cụ thể:** Implementation được giữ gần factory, public-facing contract có thể ổn định. Nếu triển khai chỉ một method cực ngắn, lambda `input -> prefix + input` sẽ gọn hơn. Local class có giá trị rõ hơn khi implementation cần nhiều methods/phần xử lý.

## 9. Khi helper dùng local variables: quy tắc effectively final

Local class có thể dùng parameters và local variables của enclosing method, nhưng các biến local/parameters được capture phải là **final hoặc effectively final**.

`Effectively final` nghĩa là biến không bị gán lại theo cách phá điều kiện final sau khi đã được khởi tạo.

Tạo **`CapturedThresholdDemo.java`**:

```java
import java.util.function.IntPredicate;

public class CapturedThresholdDemo {
    static IntPredicate atLeast(int threshold) {
        class Minimum implements IntPredicate {
            @Override
            public boolean test(int value) {
                return value >= threshold;
            }
        }

        return new Minimum();
    }

    public static void main(String[] args) {
        IntPredicate rule = atLeast(10);
        System.out.println(rule.test(9));
        System.out.println(rule.test(10));
        System.out.println(rule.test(11));
    }
}
```

```bash
javac CapturedThresholdDemo.java
java CapturedThresholdDemo
```

```text
false
true
true
```

`threshold` là tham số nhận một giá trị và không bị gán lại. Local class `Minimum` được phép đọc nó trong method `test`; instance vẫn hoạt động sau khi factory return.

### Sai lầm: gán lại biến đang được capture

Đoạn dưới đây **không biên dịch** nếu bỏ comment:

```java
void invalid() {
    int threshold = 10;

    class Rule {
        boolean test(int value) {
            return value >= threshold;
        }
    }

    // threshold = 20; // Làm threshold không còn effectively final.
}
```

Đây là **mảnh method minh họa lỗi**. Không khắc phục bằng cách đổi local class thành một lambda; lambda cũng tuân thủ effectively-final rules đối với captured local variables.

### Cần một giá trị có thể thay đổi?

Hãy đặt mutable state vào **field của helper object** hoặc object state holder có ownership rõ, thay vì cố cập nhật captured local variable. Nếu state là shared, còn phải xem xét thread safety và mutation aliasing.

## 10. Capture reference không phải sao chép sâu object

Một reference variable có thể effectively final trong khi object mà nó trỏ tới vẫn mutable.

Tạo **`CapturedMutableDependencyDemo.java`**:

```java
public class CapturedMutableDependencyDemo {
    public static void main(String[] args) {
        StringBuilder buffer = new StringBuilder("A");

        class Appender {
            void add(String text) {
                buffer.append(text);
            }

            String content() {
                return buffer.toString();
            }
        }

        Appender helper = new Appender();
        helper.add("1");
        System.out.println(helper.content());

        buffer.append("2");
        System.out.println(helper.content());
    }
}
```

```bash
javac CapturedMutableDependencyDemo.java
java CapturedMutableDependencyDemo
```

```text
A1
A12
```

`buffer` variable không đổi reference nhưng `StringBuilder` bên trong thay nội dung. Local helper và enclosing method cùng nhìn thấy **một object**.

**Tiêu chí chọn:** Nếu một helper local capture mutable dependency, quyết định xem sharing là cố ý hay nguy hiểm. Với tác vụ snapshot/immutable processing, copy dữ liệu tại thời điểm phù hợp. **Local class không tự tạo isolation** cho captured objects.

## 11. Một local class có tên giúp gì cho logging và debug?

Giả sử method xử lý qua ba giai đoạn:

- Kiểm dữ liệu.
- Tính kết quả.
- Tạo thông điệp chẩn đoán.

Một local class tên `Attempt`, `Parser` hoặc `Rule` có thể gom state và methods hỗ trợ. Khi review, người đọc hiểu “đây là một ý tưởng phụ” và thấy các bất biến cùng nhau.

Tuy nhiên, **không được phụ thuộc vào tên nhị phân do compiler sinh** như `Outer$1Attempt` làm API ổn định. Khi log muốn nhận diện thao tác, hãy tự đặt một label/logical operation name có ý nghĩa.

Ví dụ:

```java
class Attempt {
    private final String operation = "parseOrder";

    String label() {
        return operation;
    }
}
```

Đây là local-class **mảnh khai báo** dự kiến nằm trong một block; tên `operation` là dữ liệu ứng dụng, khác runtime compiler-generated class name.

### Scope giúp tránh public surface

Tên `Attempt` không tự trở thành member type `Outer.Attempt`. Nó được giới hạn trong block, do đó code ngoài block không thể vô tình phụ thuộc vào concrete type này. Một interface/superclass có thể là hợp đồng công khai duy nhất.

## 12. Khi chỉ cần một callback một lần: anonymous class có thể tự nhiên hơn

Nếu cần một object implement interface trong đúng một expression, không dùng lại tên concrete type, **anonymous class** đôi khi hợp hơn local named class.

Tạo **`AnonymousAlternativeDemo.java`**:

```java
public class AnonymousAlternativeDemo {
    public static void main(String[] args) {
        Runnable action = new Runnable() {
            @Override
            public void run() {
                System.out.println("ANONYMOUS");
            }
        };

        action.run();
    }
}
```

```bash
javac AnonymousAlternativeDemo.java
java AnonymousAlternativeDemo
```

```text
ANONYMOUS
```

Với `Runnable`, còn đơn giản hơn:

```java
Runnable action = () -> System.out.println("LAMBDA");
```

Nếu behavior chỉ một dòng, dùng lambda thường gọn nhất.

**Local named class nổi bật hơn** khi cần dùng lại tên kiểu nhiều lần trong block, tạo nhiều instances, viết constructor, giữ nhiều fields hoặc nhóm một số helper methods rõ ràng. Anonymous class có khả năng khai báo state/methods riêng, nhưng không cung cấp tên concrete type để dùng lại theo cách một local class làm được.

## 13. Ba lựa chọn cùng giải bài toán và sự khác biệt

Tạo **`ThreeApproachesDemo.java`**:

```java
import java.util.function.IntUnaryOperator;

public class ThreeApproachesDemo {
    static void demonstrate(int offset) {
        IntUnaryOperator lambda = value -> value + offset;

        IntUnaryOperator anonymous = new IntUnaryOperator() {
            @Override
            public int applyAsInt(int value) {
                return value + offset;
            }
        };

        class LocalAdder implements IntUnaryOperator {
            @Override
            public int applyAsInt(int value) {
                return value + offset;
            }
        }

        IntUnaryOperator named = new LocalAdder();

        System.out.println(lambda.applyAsInt(2));
        System.out.println(anonymous.applyAsInt(2));
        System.out.println(named.applyAsInt(2));
    }

    public static void main(String[] args) {
        demonstrate(5);
    }
}
```

```bash
javac ThreeApproachesDemo.java
java ThreeApproachesDemo
```

```text
7
7
7
```

**Cả ba cùng có kết quả** vì phép tính đơn giản. Trong tình huống này, lambda là lựa chọn ngắn gọn nhất.

Chọn local class không làm phép cộng “đúng hơn”; nó thêm giá trị khi cấu trúc thực sự phức tạp và **một kiểu có tên giúp hiểu hơn**.

| Đặc điểm | Lambda | Anonymous class | Local named class |
| --- | --- | --- | --- |
| Cần target functional interface | Có | Không nhất thiết; có thể tạo subclass/interface implementer | Không; khai báo class theo rules |
| Có tên source-level cho implementation | Không | Không | Có, trong block |
| Có thể khai báo constructor riêng | Không | Không thể khai báo constructor của anonymous class | Có |
| Có thể khai báo fields/helper methods | State phải đặt qua capture hoặc collaborator | Có | Có |
| `this` trong body | Theo lexical enclosing context | Anonymous object | Local-class object |
| Tạo lại bằng tên trong cùng block | Không theo tên kiểu | Không theo tên kiểu | Có |
| Phù hợp nhất | Hành vi ngắn | Một implementation tại chỗ, không cần tên | Helper có state/phân đoạn logic rõ |

Không cần cố chọn một hình thức thống nhất cho mọi callbacks. **Hãy ưu tiên cách mà mục tiêu và phạm vi được nhìn rõ nhất.**

## 14. Local class có thể tạo nhiều instances ngay trong một method

Không phải chỉ dùng local class để tạo một object. Khi muốn nhiều helper instances thuộc cùng một quy tắc local, tên class có ích.

Tạo **`MultipleLocalInstancesDemo.java`**:

```java
public class MultipleLocalInstancesDemo {
    public static void main(String[] args) {
        class Accumulator {
            private int total;

            void add(int value) {
                total += value;
            }

            int total() {
                return total;
            }
        }

        Accumulator first = new Accumulator();
        Accumulator second = new Accumulator();

        first.add(10);
        first.add(5);
        second.add(2);

        System.out.println("first=" + first.total());
        System.out.println("second=" + second.total());
    }
}
```

```bash
javac MultipleLocalInstancesDemo.java
java MultipleLocalInstancesDemo
```

```text
first=15
second=2
```

Mỗi Accumulator có field `total` riêng. Tên `Accumulator` dùng lại trong block giúp rõ rằng hai instances thuộc cùng một loại helper với state độc lập.

**Đây là mutable class**, không phải immutable object. Việc nó local chỉ giới hạn **phạm vi tên**, không làm fields an toàn để share đa luồng hay tự áp dụng defensive copying.

## 15. Khi cần giải thích một thuật toán, đặt class sát thuật toán

Ví dụ một method duyệt chuỗi các ký tự và gom một cấu trúc token. Có thể tách một **scanner helper** ngay trong method nếu chỉ một workflow dùng, thay vì đưa nó thành API công khai.

Tạo **`LocalScannerDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LocalScannerDemo {
    static List<String> words(String input) {
        class Scanner {
            private int position;

            boolean hasMore() {
                skipSpaces();
                return position < input.length();
            }

            String nextWord() {
                skipSpaces();
                int start = position;

                while (position < input.length()
                        && input.charAt(position) != ' ') {
                    position++;
                }
                return input.substring(start, position);
            }

            private void skipSpaces() {
                while (position < input.length()
                        && input.charAt(position) == ' ') {
                    position++;
                }
            }
        }

        Scanner scanner = new Scanner();
        List<String> result = new ArrayList<>();

        while (scanner.hasMore()) {
            result.add(scanner.nextWord());
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(words("Java  local   class"));
    }
}
```

```bash
javac LocalScannerDemo.java
java LocalScannerDemo
```

```text
[Java, local, class]
```

### Vì sao một Scanner local class có ích?

- Các methods `hasMore`, `nextWord`, `skipSpaces` cùng quản lý một field `position`.
- `position` là state riêng của mỗi Scanner instance.
- `input` là parameter effectively final của method `words`.
- Luồng chính nằm gọn ở vài dòng: tạo Scanner, gọi hasMore/nextWord, lưu kết quả.
- Nếu Scanner không được dùng ngoài `words`, đặt ngay tại đây tránh tạo abstraction rộng thừa.

### Khi nào không nên để local?

Nếu yêu cầu tách từ tăng lên (tabs/newlines, Unicode whitespace, escapes, quotes, token types, error recovery, streaming), local Scanner có thể dài và chiếm ưu thế toàn method. Khi ấy nên chuyển thành **named reusable scanner class** với API/tests riêng. Ví dụ này chỉ tách token theo ký tự space `' '`, không tuyên bố là general-purpose tokenizer.

## 16. Mức độ phức tạp hợp lý: không để helper nuốt luồng chính

Một local class lớn có thể làm method:

1. Bắt đầu bằng hơn trăm dòng khai báo helper.
2. Sau đó mới có vài dòng chính cần người đọc hiểu.
3. Buộc người đọc cuộn qua nhiều details trước khi biết method làm gì.

Đó là dấu hiệu **đang đặt chi tiết ở vị trí quá chật**.

### Heuristic review

- Nếu helper ngắn và chỉ thuộc một workflow, local class là lựa chọn tốt.
- Nếu helper dài nhưng vẫn chỉ thuộc một workflow, cân nhắc một **private method** cho các bước thuần, hoặc một **private static nested class** để giữ flow chính dễ đọc.
- Nếu helper có lifecycle riêng, constructor nhiều đối số, complex invariants hoặc cần test trực tiếp, tách thành class có tên ngoài method.
- Nếu helper được gọi ở hai hay nhiều methods, kiểm xem đây có phải logic chung thực sự; tránh sao chép local class sang nhiều nơi.
- Nếu helper cần đọc rất nhiều local variables, cân nhắc đóng gói chúng vào immutable configuration/parameters thay vì capture hàng loạt.

**Không có ngưỡng số dòng bắt buộc.** Đánh giá bằng mục tiêu đọc hiểu, khả năng test, mức coupling và tần suất thay đổi.

## 17. Capture nhiều biến có thể làm dependency trở nên ẩn

Ví dụ local class tham chiếu `currency`, `taxRate`, `discount`, `locale`, `clock` đều từ enclosing method. Mặc dù code biên dịch nếu variables đáp ứng effectively-final, người đọc helper phải nhìn cả phần trước của method để hiểu dependencies.

Cách rõ hơn đôi khi là:

```java
record Options(String currency, int taxPercent) {
}

class Formatter {
    private final Options options;

    Formatter(Options options) {
        this.options = options;
    }

    String format(int amount) {
        return options.currency() + ":" +
                (amount + amount * options.taxPercent() / 100);
    }
}
```

Đây là **hai khai báo kiểu minh họa** nếu đặt trong một block phù hợp của Java 17. Với local record `Options`, record implicitly static và không capture enclosing local variables; nó nhận dữ liệu qua components. `Formatter` thì nhận `Options` qua constructor.

Với nhiều dependencies, **explicit parameters** có thể rõ hơn capture. Local class vẫn có ích, nhưng đừng dùng nó như một cơ chế “giấu đầu vào” làm code khó test.

## 18. Local class trong instance method có thể truy cập enclosing object

Khi local class được khai báo trong một **instance method** của outer class, code của nó có thể dùng enclosing instance nếu hợp lệ.

Tạo **`LocalClassOuterStateDemo.java`**:

```java
class Account {
    private int balance;

    Account(int balance) {
        this.balance = balance;
    }

    void applyBonus(int amount) {
        class BonusOperation {
            void apply() {
                Account.this.balance += amount;
            }
        }

        new BonusOperation().apply();
    }

    int balance() {
        return balance;
    }
}

public class LocalClassOuterStateDemo {
    public static void main(String[] args) {
        Account account = new Account(100);
        account.applyBonus(15);
        System.out.println(account.balance());
    }
}
```

```bash
javac LocalClassOuterStateDemo.java
java LocalClassOuterStateDemo
```

```text
115
```

- `Account.this` là enclosing Account instance khi `applyBonus` chạy.
- `amount` là method parameter effectively final được capture.
- Local class BonusOperation chỉ có tên trong `applyBonus`.
- `this` bên trong `BonusOperation.apply` là **BonusOperation object**, không phải Account. Dùng `Account.this.balance` làm rõ target mutation.

**Cảnh báo thiết kế:** Đây cũng là coupling với outer state. Nếu helper không cần tự động nhìn thấy Account, một static nested helper với explicit dependency có thể dễ đọc/test hơn.

## 19. Trong static method vẫn khai báo local class được

Local class **không đòi một Outer instance** nếu được khai báo trong static context, nhưng khi đó không có implicit `Outer.this` để truy cập instance fields.

Tạo **`StaticLocalClassDemo.java`**:

```java
public class StaticLocalClassDemo {
    static String format(String code) {
        class Formatter {
            String apply() {
                return "[" + code + "]";
            }
        }

        return new Formatter().apply();
    }

    public static void main(String[] args) {
        System.out.println(format("J17"));
    }
}
```

```bash
javac StaticLocalClassDemo.java
java StaticLocalClassDemo
```

```text
[J17]
```

Ở đây `Formatter` capture parameter `code` mà không cần enclosing instance. Khi static helper cần instance data, **truyền object qua parameter/constructor** thay vì viết `Outer.this` không hợp lệ.

**Không nhầm:** Tên local class bị giới hạn ở method block là một quy tắc về **lexical scope**; việc method static hay instance chỉ ảnh hưởng một số khả năng tham chiếu/capture context.

## 20. Lớp cục bộ và constructor: thiết lập state trước khi dùng

Local class có thể định nghĩa constructor để kiểm invariants và thiết lập state.

Tạo **`LocalConstructorDemo.java`**:

```java
import java.util.function.IntUnaryOperator;

public class LocalConstructorDemo {
    static IntUnaryOperator multiplier(int factor) {
        class Multiply implements IntUnaryOperator {
            private final int value;

            Multiply(int value) {
                if (value <= 0) {
                    throw new IllegalArgumentException(
                            "positive factor required");
                }
                this.value = value;
            }

            @Override
            public int applyAsInt(int operand) {
                return Math.multiplyExact(operand, value);
            }
        }

        return new Multiply(factor);
    }

    public static void main(String[] args) {
        IntUnaryOperator twice = multiplier(2);
        System.out.println(twice.applyAsInt(7));

        try {
            multiplier(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid factor rejected");
        }
    }
}
```

```bash
javac LocalConstructorDemo.java
java LocalConstructorDemo
```

```text
14
invalid factor rejected
```

Dù `Multiply` chỉ có tên trong `multiplier`, nó vẫn có một proper constructor, final field và validation. Return type `IntUnaryOperator` là hợp đồng bên ngoài.

`Math.multiplyExact` ném `ArithmeticException` khi overflow. Đây là một quyết định rõ ràng hơn silently overflow nếu miền yêu cầu arithmetic đúng.

**Chọn local class** khi validation/state chỉ có nghĩa trong factory này. Nếu các call sites khác cũng cần tạo/kiểm Multiply theo một shared contract, cân nhắc nâng abstraction lên phạm vi rộng hơn.

## 21. Lớp cục bộ không bị giới hạn ở một instance

Một method có thể khai báo một local class rồi khởi tạo nhiều objects. Nhưng tên class chỉ có thể được sử dụng **trong block có scope**.

Tạo **`LocalInstanceCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LocalInstanceCollectionDemo {
    static List<Runnable> tasks() {
        List<Runnable> result = new ArrayList<>();

        class Task implements Runnable {
            private final String name;

            Task(String name) {
                this.name = name;
            }

            @Override
            public void run() {
                System.out.println(name);
            }
        }

        result.add(new Task("ONE"));
        result.add(new Task("TWO"));
        return result;
    }

    public static void main(String[] args) {
        for (Runnable task : tasks()) {
            task.run();
        }

        // Task t; // Tên Task không nằm trong scope main.
    }
}
```

```bash
javac LocalInstanceCollectionDemo.java
java LocalInstanceCollectionDemo
```

```text
ONE
TWO
```

`Task` chỉ có tên trong `tasks`, nhưng các objects vẫn tồn tại khi một List<Runnable> giữ chúng sau method return. Scope của **tên kiểu** không đồng nghĩa với lifetime của **instance**.

Nếu helper được dự kiến truyền qua hệ thống rộng, xem lại xem concrete type cần một API/test/lifecycle riêng hay không. Một object từ local class vẫn có thể giữ captured values hoặc enclosing instance reference.

## 22. Phạm vi tên: chỉ từ chỗ khai báo đến cuối block

Tạo **`LocalScopeBoundaryDemo.java`**:

```java
public class LocalScopeBoundaryDemo {
    public static void main(String[] args) {
        System.out.println("before local type");

        {
            class Local {
                String value() {
                    return "VISIBLE";
                }
            }

            Local item = new Local();
            System.out.println(item.value());
        }

        System.out.println("after block");
        // Local outside = new Local(); // Không hợp lệ.
    }
}
```

```bash
javac LocalScopeBoundaryDemo.java
java LocalScopeBoundaryDemo
```

```text
before local type
VISIBLE
after block
```

Tên `Local` có scope **từ khai báo đến hết block trực tiếp bao quanh**. Sau khi block đóng, không dùng được tên đó trong source code của enclosing block, dù có thể trả object qua interface/superclass.

Hai blocks hoặc methods độc lập có thể dùng local classes trùng tên vì đó là hai declarations khác nhau.

**Đánh giá thiết kế:** Scope hẹp là ưu điểm khi implementation thật sự local. Nó trở thành bất tiện nếu ngay sau đó bạn phải tìm cách “gọi tên class” ở một method khác — dấu hiệu nên dùng abstraction rộng hơn.

## 23. Lớp cục bộ có thể giúp giới hạn một thuật toán đặc biệt

Một thuật toán chỉ dùng trong một method đôi khi cần một node/entry type nhỏ.

Tạo **`LocalTraversalNodeDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class LocalTraversalNodeDemo {
    static int sumChain(int[] numbers) {
        class Entry {
            final int value;
            final Entry previous;

            Entry(int value, Entry previous) {
                this.value = value;
                this.previous = previous;
            }
        }

        Entry head = null;
        for (int number : numbers) {
            head = new Entry(number, head);
        }

        int total = 0;
        for (Entry current = head;
             current != null;
             current = current.previous) {
            total += current.value;
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(sumChain(new int[] {2, 3, 4}));
    }
}
```

```bash
javac LocalTraversalNodeDemo.java
java LocalTraversalNodeDemo
```

```text
9
```

`Entry` tồn tại như một kiểu riêng trong `sumChain`; nó không phải một domain entity toàn hệ thống. Code có thể dùng `Entry` trong chính body của class cho field `previous`, và sau khai báo để tạo/traverse entries.

**Quyết định:** Nếu cấu trúc danh sách/node này chỉ phục vụ một thuật toán, local class giữ nó gần nơi dùng. Nếu trở thành cấu trúc dữ liệu phổ biến, đừng copy/paste nhiều local Entry; trích thành reusable type.

**Lưu ý hiệu năng:** Ví dụ cấp phát một Entry object cho mỗi phần tử; với bài toán chỉ cộng một mảng, vòng lặp cộng trực tiếp đơn giản và ít allocation hơn. Ví dụ nhằm minh họa cách tổ chức một thuật toán *có yêu cầu giữ các node/metadata lồng nhau*, không khuyên tạo linked nodes chỉ để tính tổng.

## 24. Khi local record tốt hơn local class có state?

Java 17 cho phép local **record** cho dữ liệu nhỏ có giá trị bất biến theo cấu trúc components, nếu components cũng immutable.

Tạo **`LocalRecordChoiceDemo.java`**:

```java
public class LocalRecordChoiceDemo {
    static String label(String code, int count) {
        record Entry(String code, int count) {
        }

        Entry entry = new Entry(code, count);
        return entry.code() + ":" + entry.count();
    }

    public static void main(String[] args) {
        System.out.println(label("A", 3));
    }
}
```

```bash
javac LocalRecordChoiceDemo.java
java LocalRecordChoiceDemo
```

```text
A:3
```

Local record phù hợp cho data carrier có components/auto-generated accessors/equals/hashCode. Local class thường phù hợp hơn khi có mutable per-instance state hoặc logic/constructor phi tầm thường.

**Khác biệt quan trọng:** Local record là **implicitly static**, không capture local variables/enclosing instance như non-static local class. Dữ liệu cần thiết phải được truyền qua components/method arguments. Và record không tự deep-immutable nếu component là mutable array/list.

Không chọn local record chỉ vì cú pháp ngắn khi abstraction thực sự cần behavior/state phức tạp.

## 25. Vì sao không nên tạo một local class cho mọi lambda?

Các tình huống sau thường **không đáng thêm local class**:

- Map một danh sách số sang bình phương: `n -> n * n`.
- Lọc phần tử theo một điều kiện ngắn.
- In mỗi phần tử bằng method reference.
- Gọi callback một lần không cần name/state.
- Chỉ chuyển một method đã tồn tại thành functional object: `String::trim` hoặc `System.out::println` khi type phù hợp.

Ví dụ:

```java
List<Integer> doubled = numbers.stream()
        .map(n -> n * 2)
        .toList();
```

Đây là mảnh code, giả định `numbers` là `List<Integer>` có sẵn và `java.util.List` được import. Thêm một local class implements Function chỉ để thực hiện `n * 2` sẽ tăng ceremony không cần thiết.

**Quy tắc:** Lambda tốt khi logic ngắn và functional intent rõ. Local class tốt khi behavior **có cấu trúc đáng đặt tên** và có nhiều chi tiết cần gom một chỗ.

## 26. Vì sao không nên tạo local class chỉ để “tránh thêm file”?

Mục tiêu không phải giảm số lượng file bằng mọi giá. Một local class phức tạp 200 dòng có thể:

- Che mất luồng điều khiển của enclosing method.
- Khó kiểm thử trực tiếp.
- Capture quá nhiều dependencies ngầm.
- Lặp lại logic ở nhiều methods.
- Có lifecycle/resource management riêng nhưng không có nơi quản lý rõ.
- Buộc sửa một method lớn khi thay đổi một rule nhỏ.

Nếu class có **business responsibility ổn định**, nhiều public-facing consumers hoặc cần định nghĩa versioning/API, hãy cân nhắc static nested/top-level class. Việc nó “chỉ được gọi từ một method hôm nay” chưa đủ chứng minh nó phải local mãi mãi nếu complexity không phù hợp.

### Review bằng câu hỏi thay vì số dòng

1. Concrete helper type cần được **đặt tên ở nơi khác** không?
2. Người đọc method có hiểu luồng chính mà không phải đọc mọi dòng helper không?
3. Những state fields và helper methods có phục vụ **chỉ một workflow** không?
4. Các dependencies được capture có rõ ràng không?
5. Có test đủ qua enclosing method/interface không, hay cần test một class độc lập?
6. Nếu thêm yêu cầu tương lai, helper có khả năng tái sử dụng ở nhiều nơi không?

Đáp án quan trọng hơn quy tắc “local class dưới N dòng”.

## 27. Refactor từ local class sang static nested class khi bắt đầu tái sử dụng

Giả sử vài methods cần cùng rule, ta có thể đưa helper thành static nested class có dependencies explicit.

Tạo **`ReusableNestedHelperDemo.java`**:

```java
public class ReusableNestedHelperDemo {
    private static final class Prefixer {
        private final String prefix;

        Prefixer(String prefix) {
            this.prefix = prefix;
        }

        String apply(String value) {
            return prefix + value;
        }
    }

    static String labelA(String value) {
        return new Prefixer("A-").apply(value);
    }

    static String labelB(String value) {
        return new Prefixer("B-").apply(value);
    }

    public static void main(String[] args) {
        System.out.println(labelA("1"));
        System.out.println(labelB("2"));
    }
}
```

```bash
javac ReusableNestedHelperDemo.java
java ReusableNestedHelperDemo
```

```text
A-1
B-2
```

**Lợi ích refactor:**

- `Prefixer` không thuộc riêng một method nữa.
- Hai methods dùng lại một implementation.
- Dependency `prefix` được truyền rõ qua constructor.
- Vì nested class là `static`, nó không tự giữ implicit instance của outer `ReusableNestedHelperDemo`.
- Nó vẫn `private` và không thành top-level public API.

Khi nào tiếp tục tách ra file riêng? Khi responsibility và khả năng dùng lại vượt khỏi enclosing class, hoặc tests/docs/dependencies cần một module type riêng.

## 28. Test local class qua observable behavior

Vì tên local class không có scope ngoài block, unit tests thường kiểm qua **enclosing method**, **interface** hoặc **public behavior**, không gọi trực tiếp constructor tên local type từ class test.

Tạo **`LocalClassBehaviorTestDemo.java`**:

```java
import java.util.function.IntUnaryOperator;

public class LocalClassBehaviorTestDemo {
    static IntUnaryOperator scaledAdder(int scale, int offset) {
        class Rule implements IntUnaryOperator {
            @Override
            public int applyAsInt(int input) {
                return input * scale + offset;
            }
        }

        return new Rule();
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        IntUnaryOperator rule = scaledAdder(2, 3);

        check(rule.applyAsInt(4) == 11, "positive input");
        check(rule.applyAsInt(0) == 3, "zero input");
        check(rule.applyAsInt(-2) == -1, "negative input");

        System.out.println("local helper behavior PASS");
    }
}
```

```bash
javac LocalClassBehaviorTestDemo.java
java LocalClassBehaviorTestDemo
```

```text
local helper behavior PASS
```

Helper `Rule` không cần bị expose để test phép toán có ý nghĩa. Một method public hoặc package-private khác có thể test qua cùng interface.

Nếu logic có nhiều branches phức tạp khiến tests phải thiết lập những trạng thái khó tạo qua enclosing API, đó có thể là tín hiệu đưa helper thành **testable named type** có phạm vi phù hợp.

**Không nhầm:** Tên local class bị giới hạn là một tính chất compile-time; nó không làm code “không thể test”. Chỉ là ta nên test qua contract mà code bên ngoài thật sự dùng.

## 29. Local class có thể chứa trạng thái mutable và side effects: cần xét lifecycle

Một helper tên `Task` hoặc `Processor` bên trong một method đôi khi được **return** dưới dạng interface và sống lâu. Khi ấy:

- Captured references có thể giữ objects khác sống lâu hơn dự kiến.
- Instance state có thể bị mutate từ threads khác.
- Helper có thể giữ file/socket hoặc callback cần cleanup.
- State có thể không còn đúng khi external environment thay đổi.

**Ví dụ logic:** `Runnable` trả từ factory có thể được chạy nhiều lần, trên threads khác nhau. Nếu nó mutate một `ArrayList` capture từ caller, có thể cần synchronization.

Đừng xem local class như “chỉ tồn tại trong method”: **chỉ tên class giới hạn về source scope**, còn instances có lifecycle theo references/GC bình thường.

Nếu lifecycle phức tạp, đưa concrete class ra phạm vi rộng hơn để owner/cleanup contract dễ quan sát có thể tốt hơn.

## 30. Một bẫy về `this` trong local class và lambda

Local class có receiver `this` riêng. Nếu được khai báo trong instance method của Outer, `Outer.this` trỏ tới Outer instance tương ứng.

Trong lambda, `this` có ý nghĩa **lexical** của nơi khai báo lambda, không phải một lambda object receiver.

Tạo **`LocalClassThisVsLambdaDemo.java`**:

```java
class Outer {
    private final String name = "OUTER";

    void show() {
        class Local {
            private final String name = "LOCAL";

            void print() {
                System.out.println("local this=" + this.name);
                System.out.println("outer=" + Outer.this.name);
            }
        }

        Runnable lambda = () ->
                System.out.println("lambda this=" + this.name);

        new Local().print();
        lambda.run();
    }
}

public class LocalClassThisVsLambdaDemo {
    public static void main(String[] args) {
        new Outer().show();
    }
}
```

```bash
javac LocalClassThisVsLambdaDemo.java
java LocalClassThisVsLambdaDemo
```

```text
local this=LOCAL
outer=OUTER
lambda this=OUTER
```

Trong `Local.print`, `this` là Local. Trong lambda viết trực tiếp ở `Outer.show`, `this` là lexical Outer.

**Lý do cần biết khi lựa chọn:** Nếu logic dùng outer state, chuyển giữa local class và lambda có thể làm `this` mang ý nghĩa khác. Đừng refactor chỉ dựa trên độ ngắn mà không rà receiver identity.

## 31. Local class không tự trở thành member class có thể dùng ở nơi khác

Ví dụ:

```java
class Outer {
    void method() {
        class Helper {
        }
        Helper h = new Helper();
    }

    void other() {
        // Helper h; // Không hợp lệ.
        // Outer.Helper h; // Không hợp lệ.
    }
}
```

Đây là **khai báo minh họa** không có `main`.

Tên `Helper` có scope từ dòng class declaration đến hết block method chứa nó. Nó **không thể được truy cập bằng `Outer.Helper`** như một member nested type.

Nếu caller ở method khác cần concrete type, scope hiện tại không đáp ứng; dùng interface/supertype hoặc refactor helper thành member/static nested/top-level class.

### Hai local classes trùng tên ở hai methods là hai types riêng

Đây là hợp lệ khi scopes tách biệt:

```java
void first() {
    class Helper {
    }
    new Helper();
}

void second() {
    class Helper {
    }
    new Helper();
}
```

Hai methods dùng cùng simple name nhưng không dùng chung một Helper type; không coi đó là cơ chế chia sẻ implementation.

## 32. Khi nào một private method tốt hơn local class?

Một **private method** thường tốt hơn nếu:

- Logic hoàn toàn thuần, không cần state riêng.
- Đã có inputs/outputs rõ ràng, có thể truyền parameters trực tiếp.
- Chỉ muốn đặt tên cho một phép biến đổi ngắn.
- Thêm một class chỉ làm tăng mức nesting mà không tạo semantic entity rõ.

Ví dụ thay local helper:

```java
private static boolean isValidCode(String code) {
    return code != null && !code.isBlank();
}
```

Đây là mảnh method thuộc class. Nếu nhiều call sites dùng `isValidCode`, private method vừa ngắn vừa reuse thuận tiện.

Ngược lại, nếu phải truyền lặp lại 5-6 parameters cho một nhóm 4 methods phụ, một helper object có fields/constructor rõ ràng có thể gom dependencies tốt hơn.

**Đặt câu hỏi:** Đang đặt tên cho **một thao tác** hay cho **một nhóm hành vi/trạng thái**? Thao tác → private method/lambda. Nhóm có identity và invariants → class, trong đó local class là ứng viên nếu phạm vi chỉ một block.

## 33. Những dấu hiệu lựa chọn sai

| Dấu hiệu | Vấn đề có thể có | Hướng cân nhắc |
| --- | --- | --- |
| Local class chỉ có một method trả biểu thức một dòng | Ceremony nhiều hơn ý nghĩa | Lambda/private method |
| Local class copy giống nhau ở vài methods | Duplicate logic | Static nested/top-level helper |
| Local class quá dài khiến method chính khó nhìn | Chi tiết át mục tiêu | Extract class/private helper |
| Helper capture rất nhiều local variables | Hidden dependencies | Immutable config/constructor parameters |
| Caller ngoài method muốn dùng tên implementation | Scope không đáp ứng | Public interface hoặc named type phù hợp |
| Helper chỉ nhận primitive/immutable input và không có state | Class có thể dư | Pure function |
| Helper dùng mutable shared collection từ caller | Aliasing, race conditions | Ownership/defensive copy/synchronization |
| Helper giữ resources có lifecycle riêng | Cleanup khó phát hiện | Scoped resource manager/named class |
| Helper cần test trực tiếp quá nhiều edge cases | Contract lớn hơn mức “chi tiết nhỏ” | Extract testable type |
| Helper là phần domain model dùng rộng | Đặt tên quá hẹp | Domain class/value type |
| Local class trong static method gọi `Outer.this` | Không có enclosing Outer instance | Explicit owner reference |
| Logic đơn giản nhưng dùng anonymous/local vì quen tay | Khó đọc | Lambda/method reference |
| “Tất cả mọi thứ” đều local để giảm files | Tăng coupling/độ dài method | Refactor theo trách nhiệm |

**Ghi nhớ:** Một helper đúng đắn vẫn có thể được đặt sai phạm vi. Đánh giá cả cách **người khác đọc, test và thay đổi** code.

## 34. Bài tập tổng hợp: lựa chọn thiết kế cho từng tình huống

**Tình huống A.** Một method sắp xếp ba phần tử theo comparator đơn giản và không có state.

*Lựa chọn đề xuất:* Lambda hoặc built-in Comparator, vì không cần local class.

**Tình huống B.** Một method parse chuỗi dài, cần scanner giữ cursor, methods `peek`, `read`, `skip`, và scanner không dùng nơi khác.

*Lựa chọn đề xuất:* Local class có thể phù hợp nếu tổng độ dài còn dễ đọc. Nếu parser tăng trưởng, cân nhắc class riêng.

**Tình huống C.** Ba methods khác nhau đều dùng cùng validation rules.

*Lựa chọn đề xuất:* Shared private method hoặc static nested/top-level validator. Không copy cùng local class ba lần.

**Tình huống D.** Factory tạo một strategy implement interface và chỉ factory quan tâm implementation.

*Lựa chọn đề xuất:* Local class nếu implementation nhiều steps/state; lambda nếu chỉ một function ngắn.

**Tình huống E.** Callback được return ra ngoài và giữ mutable state, chạy trên nhiều threads.

*Lựa chọn đề xuất:* Đầu tiên xác định lifecycle, concurrency và ownership. Local class không tự đồng bộ; có thể cần named component có tests/contract rõ.

**Tình huống F.** Một helper có thể được gọi bởi vài enclosing methods, không cần Outer instance.

*Lựa chọn đề xuất:* `private static nested class` và truyền dependencies tường minh.

**Tình huống G.** Một phép biến đổi rất ngắn được dùng lặp lại, không có fields.

*Lựa chọn đề xuất:* Private method hoặc method reference thay vì local class.

**Tình huống H.** Một thuật toán riêng cần cấu trúc Node/Frame nhỏ với hai fields và một số thao tác phụ; không có người dùng ngoài thuật toán.

*Lựa chọn đề xuất:* Local class hoặc local record khi chỉ lưu immutable data (theo restrictions), tùy mô hình state.

## 35. Checklist review cho một lớp cục bộ

- [ ] Local class phục vụ **chính một method/block** hay nhiều nơi?
- [ ] Nó có **tên thể hiện trách nhiệm thực sự**?
- [ ] Có đủ **state/methods/constructor** để việc đặt class có lợi?
- [ ] Luồng chính của enclosing method vẫn dễ đọc khi khai báo class nằm bên trong?
- [ ] Một lambda/private method có đơn giản hơn mà vẫn rõ không?
- [ ] Một anonymous class có hợp hơn nếu chỉ tạo đúng một object tại một expression?
- [ ] Một static nested/top-level class có hợp hơn vì tái sử dụng hoặc complexity không?
- [ ] Những local variables/parameters được capture có final/effectively final?
- [ ] Các references captured có mutable state bị chia sẻ ngoài ý muốn?
- [ ] Nếu helper chạy sau khi enclosing method return, lifecycle/ownership có rõ?
- [ ] Nếu object helper được return, API có visible interface/supertype thích hợp?
- [ ] Không dùng tên local class từ code ngoài lexical scope?
- [ ] Không dựa vào compiler-generated binary class names để làm API?
- [ ] Nếu helper ở static method, không nhầm `Outer.this` là luôn có?
- [ ] Nếu có `this` trong local class/lambda, đã xét lexical receiver đúng?
- [ ] Nếu helper có mutable fields, concurrency contract có hợp lý?
- [ ] Các phương thức phụ cùng chia sẻ một invariant hay đang nhồi nhiều trách nhiệm?
- [ ] Helper có bị sao chép y nguyên ở methods khác không?
- [ ] Nếu helper dài, có lý do gì không refactor ra thành named class?
- [ ] Unit tests bao phủ observable behavior qua enclosing method/interface?
- [ ] Public-facing API không rò tên local class hay implementation detail?
- [ ] Các ví dụ Java 17+ có file/public class đúng và stdout xác định?

## 36. Câu hỏi ôn tập có đáp án

**1.** Khi nào lớp cục bộ là lựa chọn tự nhiên?

**Đáp án:** Khi một cụm chi tiết triển khai có state/methods riêng, chỉ cần trong một block/method, và đặt gần nơi dùng giúp hiểu code hơn.

**2.** Local class có thể có constructor, fields và nhiều instance methods không?

**Đáp án:** Có. Nó là một class theo các rules của local class, không chỉ là lambda có tên.

**3.** Nếu chỉ cần `n -> n * 2`, có nên tạo local class?

**Đáp án:** Thường không. Lambda hoặc method phù hợp dễ đọc hơn.

**4.** Nếu nhiều methods cần cùng helper thì sao?

**Đáp án:** Cân nhắc private method, static nested class hoặc top-level class để tái sử dụng.

**5.** Class cục bộ được khai báo trong static method có hợp lệ không?

**Đáp án:** Có. Nhưng không có implicit enclosing Outer instance để dùng `Outer.this` trong static context.

**6.** Local class có dùng parameter của enclosing method không?

**Đáp án:** Có nếu parameter final/effectively final và đáp ứng các rules liên quan.

**7.** Captured `StringBuilder` có biến thành immutable không?

**Đáp án:** Không. Biến tham chiếu có thể effectively final nhưng object vẫn mutable.

**8.** Sau khi method return, instance local class có còn hoạt động không?

**Đáp án:** Có nếu còn reference giữ object, ví dụ qua interface.

**9.** Tên local class có dùng được trong method khác không?

**Đáp án:** Không. Nó có phạm vi từ khai báo đến hết block trực tiếp chứa khai báo.

**10.** Tại sao interface return type hữu ích?

**Đáp án:** Nó cho caller sử dụng behavior mà không cần biết concrete local class name.

**11.** Local named class khác anonymous class ở điểm nào quan trọng?

**Đáp án:** Local class có tên để khởi tạo nhiều lần và tự định nghĩa constructor; anonymous class không có tên source-level hay constructor được khai báo bằng tên class.

**12.** Local record có thay local class mutable-state helper được trong mọi trường hợp không?

**Đáp án:** Không. Local record implicitly static và là data carrier có component semantics; mutable state/capture behavior khác.

**13.** Khi helper capture nhiều dependencies, làm thế nào để rõ hơn?

**Đáp án:** Gom thành config/value objects hoặc truyền constructor parameters; cân nhắc named helper có scope rộng hơn.

**14.** Local class có mặc nhiên thread-safe vì chỉ tên nó ở một block không?

**Đáp án:** Không. Instances có thể sống lâu và được share giữa threads, cần concurrency contract.

**15.** Vì sao class cục bộ 200 dòng có thể không hợp dù chỉ dùng trong một method?

**Đáp án:** Nó có thể che luồng chính, khó test/reuse và tạo coupling; nên cân nhắc refactor.

**16.** Có nên dùng tên kiểu do compiler sinh để gọi local class từ code khác?

**Đáp án:** Không. Đó không phải source API ổn định; dùng interface/supertype hoặc đổi thiết kế scope.

**17.** Một local class có thể tự khai báo type của field liên kết tới nó không?

**Đáp án:** Có, tên class được dùng trong body của chính khai báo để xây cấu trúc như Node.

**18.** Khi nào static nested helper tốt hơn?

**Đáp án:** Khi nhiều methods của outer class sử dụng và helper không cần implicit owner instance.

**19.** Khi nào private method tốt hơn?

**Đáp án:** Khi cần tên cho một thao tác thuần, không cần per-instance state/constructor.

**20.** Tiêu chí cuối cùng để chọn local class là gì?

**Đáp án:** Nó có giữ **chi tiết triển khai gần đúng nơi dùng**, giảm phạm vi không cần thiết và **cải thiện khả năng đọc/kiểm thử/bảo trì** hơn các lựa chọn thay thế hay không.

---

**Ghi nhớ cuối bài:** **Lớp cục bộ** đáng dùng khi một method có **một helper có tên, có trạng thái hoặc nhiều phương thức liên quan**, nhưng concrete type ấy không cần tái sử dụng bằng tên ở nơi khác. Nó giúp **giấu chi tiết triển khai và giữ mạch giải thích gần nơi dùng**, có thể capture effectively-final parameters/local variables và có thể return instances qua interface/supertype. Tuy nhiên, lớp cục bộ không tự làm code tốt hơn: **lambda/private method** thường phù hợp với logic ngắn; **static nested/top-level class** phù hợp hơn khi helper được dùng lại, có lifecycle/API riêng hoặc quá phức tạp. Hãy lựa chọn dựa trên **trách nhiệm, phạm vi dùng thực tế, tính rõ ràng của dependencies và khả năng duy trì**, không dựa vào mục tiêu giảm số file hay tăng số class.