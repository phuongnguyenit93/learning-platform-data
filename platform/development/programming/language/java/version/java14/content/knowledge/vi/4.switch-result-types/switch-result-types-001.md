# Biểu thức `switch` độc lập và biểu thức nhận kiểu từ ngữ cảnh (Java 14+)

Từ **Java 14**, `switch expression` trở thành tính năng chính thức của Java (JEP 361). Khác với `switch statement` dùng để điều khiển luồng, `switch expression` **trả về một giá trị** và vì thế phải có **kiểu dữ liệu tĩnh** xác định tại lúc biên dịch. Kiểu đó không phải lúc nào cũng chỉ dựa vào những giá trị sau `case`: đôi khi kiểu mong đợi của chỗ sử dụng được truyền xuống các nhánh.

Bài học này giải thích hai cơ chế hiện vẫn được Java Language Specification sử dụng:

- **Standalone switch expression** (*biểu thức độc lập*): kiểu kết quả được tính từ các biểu thức trả về trong những nhánh `case`/`yield`. Không có kiểu đích cụ thể truyền xuống để định kiểu từng nhánh.
- **Poly switch expression** (*biểu thức nhận kiểu từ ngữ cảnh*): một **target type** (kiểu đích) từ ngữ cảnh gán, trả về hoặc truyền tham số được sử dụng để kiểm tra và định kiểu các biểu thức kết quả trong mọi nhánh.

Đây là hai **cách compiler xử lý cùng một cú pháp**, không phải hai keyword hay hai loại đối tượng runtime. Chọn nhánh nào khi thực thi không thay đổi việc compiler đã kiểm tra **tất cả nhánh** từ trước. Các ví dụ dùng **JDK 17+**, biên dịch trực tiếp với `javac`, không cần tùy chọn preview hoặc cú pháp đã lỗi thời.

## 1. Kiến thức nền: switch expression có kết quả gì?

Ví dụ minh họa trong một phương thức có `int status`:

```java
// Statement: điều khiển luồng, không có kiểu kết quả cho cả switch.
String oldStyle;
switch (status) {
    case 0:
        oldStyle = "NEW";
        break;
    default:
        oldStyle = "OTHER";
}

// Expression: toàn switch tạo một giá trị để gán.
String newStyle = switch (status) {
    case 0 -> "NEW";
    default -> "OTHER";
};
```

Trong `switch expression`, cần phân biệt ba thành phần:

1. **Selector** nằm trong `switch (selector)`, quyết định nhánh nào sẽ chạy. Kiểu của selector không phải là kiểu giá trị kết quả; selector `int` vẫn có thể tạo kết quả `String`, `long`, `List<String>`, v.v.
2. **Result expressions** là các biểu thức ở dạng `case ... -> expression` hoặc `yield expression` trong khối nhánh. Chính chúng được kiểm tra tính tương thích và quyết định kiểu kết quả.
3. **Exhaustiveness**: phải xử lý đủ giá trị selector. Ví dụ với `int` thường cần `default`; với enum có thể liệt kê tất cả hằng enum mà không cần `default`.

Nếu một nhánh cần nhiều câu lệnh, dùng khối `{ ... }` và `yield`:

```java
String message = switch (status) {
    case 0 -> "ready";
    case 1 -> {
        String temporary = "pending";
        yield temporary;
    }
    default -> throw new IllegalArgumentException("Bad status");
};
```

Trong đoạn trên, hai result expressions là `"ready"` và `temporary`. Nhánh `throw` không trả giá trị; nó kết thúc bất thường. `yield` gửi kết quả trở lại **switch expression hiện tại**, khác với `return` thoát khỏi phương thức. Một `switch expression` phải có ít nhất một result expression; một khối nhánh không được chạy đến cuối mà không sinh giá trị hoặc kết thúc bất thường hợp lệ.

**Lưu ý:** ví dụ trong mục này là **đoạn mã tích hợp**, cần đặt trong một phương thức có khai báo `status`. Các chương trình đầy đủ, có tên tệp và stdout, xuất hiện bên dưới.

## 2. Phân biệt hai cách xác định kiểu theo ngữ cảnh

Quy tắc ở **Java Language Specification (JLS) 15.28.1**:

> `switch` expression là **poly** khi xuất hiện trong *assignment context* hoặc *invocation context*; trong các trường hợp còn lại, nó là **standalone**.

**Assignment context**: giá trị được gán cho biến có kiểu đã biết hoặc trả về từ phương thức có kiểu trả về được khai báo. **Invocation context**: giá trị được truyền làm tham số cho lời gọi phương thức/constructor có kiểu tham số tương ứng. Đối với lời gọi overload hoặc generic, compiler còn phải phân giải phương thức phù hợp trước khi hoàn tất kiểm tra kiểu.

| Vị trí của `switch` expression | Kiểu xử lý | Nguồn thông tin về kiểu |
| --- | --- | --- |
| `String text = switch (n) { ... };` | **Poly** | Kiểu đích `String` |
| `text = switch (n) { ... };` với `text` đã khai báo `String` | **Poly** | Kiểu của biến ở vế trái |
| `return switch (n) { ... };` trong phương thức trả `String` | **Poly** | Kiểu trả về của phương thức |
| `consume(switch (n) { ... });` | **Poly** | Kiểu tham số của lời gọi `consume` |
| `var text = switch (n) { ... };` | **Standalone** | `var` yêu cầu suy kiểu từ initializer, chưa có target type |
| `int x = 1 + switch (n) { ... };` | **Standalone** cho `switch` | Ngữ cảnh trực tiếp là toán hạng phép `+` |
| `String x = "value=" + switch (n) { ... };` | **Standalone** cho `switch` | Ngữ cảnh trực tiếp là nối chuỗi |
| `String x = (String) (switch (n) { ... });` | **Standalone** cho `switch` | Ngữ cảnh trực tiếp là phép cast, không phải assignment context của `switch` |

**Với poly switch:** gọi target type là `T`. Mọi result expression được xét như đang nằm trong ngữ cảnh gán/lời gọi với target `T`; nếu một result expression không tương thích thì toàn biểu thức lỗi biên dịch. **Kiểu tĩnh của toàn poly switch chính là `T`.** Các nhánh có thể mang kiểu nguồn khác nhau nếu mỗi nhánh chuyển đổi hợp lệ về `T`.

**Với standalone switch:** không có target type truyền tới từng nhánh. Compiler tự tính kiểu từ **tập hợp** các result expressions bằng các quy tắc cụ thể ở mục 3.

Ngoặc đơn thông thường **không làm mất target type**: `String s = (switch (n) { ... });` vẫn là poly. Nhưng phép cast, nối chuỗi, cộng số hay thao tác khác có thể tạo ngữ cảnh trực tiếp khác. Khi phân tích, xét nơi **chính biểu thức `switch`** xuất hiện, không chỉ nhìn biến cuối cùng được gán.

## 3. Thuật toán xác định kiểu của standalone switch

Theo JLS, khi `switch` là standalone, compiler lần lượt xem xét các result expressions:

1. **Cùng một kiểu**: nếu tất cả có cùng kiểu thì đó là kiểu của switch (bao gồm trường hợp kiểu `null` trong định nghĩa ngôn ngữ).
2. **Boolean**: nếu mọi result expression có kiểu `boolean` hoặc `Boolean`, các giá trị `Boolean` được unbox khi cần; kiểu kết quả là **`boolean`**.
3. **Số**: nếu mọi result expression chuyển đổi được về kiểu số, Java áp dụng **general numeric promotion**. Ví dụ `int` và `long` thành `long`, `int` và `double` thành `double`.
4. **Các kiểu còn lại**: Java boxing kết quả primitive, sau đó tính **least upper bound** (LUB) của các kiểu tham chiếu và áp dụng **capture conversion**. Kết quả có thể là interface chung hoặc kiểu generic với wildcard, không mặc định luôn là `Object`.

Ví dụ:

| Các biểu thức trong các nhánh | Standalone được định kiểu ra sao |
| --- | --- |
| `"A"` và `"B"` | `String` |
| `1` và `2` | `int` |
| `1` và `2L` | `long` |
| `1` và `2.5` | `double` |
| `true` và một biểu thức `Boolean` | `boolean`, có thể unboxing |
| `"abc"` và `new StringBuilder("def")` | Kiểu chung theo LUB, có ít nhất quan hệ với `CharSequence` |
| `List.of()` và `List.of("Java")` | Generic LUB/capture; có thể rộng hơn `List<String>` |
| Hai lambda chưa có functional interface đích | **Lỗi biên dịch**: không suy được kiểu lambda |

**Quan trọng:** kiểu tĩnh được compiler xác định cho **tất cả nhánh**, khác với kiểu runtime của object thực sự được nhánh được chọn trả về. Việc một nhánh không chạy trong lần thử không có nghĩa compiler bỏ qua nó.

## 4. Ví dụ chạy được: cùng nhánh, kiểu và runtime khác nhau

**Tệp `SwitchTypesDemo.java` (JDK 17+):**

```java
import java.util.List;
import java.util.function.IntSupplier;
import java.util.function.Supplier;

public class SwitchTypesDemo {
    static void printValue(Supplier<String> supplier) {
        System.out.println("invocation=" + supplier.get());
    }

    static Supplier<String> chooseMessage(int code) {
        return switch (code) {
            case 0 -> () -> "return-context";
            default -> () -> "other";
        };
    }

    static String status(int code) {
        return switch (code) {
            case 0 -> "ready";
            case 1 -> {
                String result = "pending";
                yield result;
            }
            default -> throw new IllegalArgumentException("invalid");
        };
    }

    public static void main(String[] args) {
        int mode = 0;

        var standaloneNumber = switch (mode) {
            case 0 -> 1;
            default -> 2.5;
        };
        Number polyNumber = switch (mode) {
            case 0 -> 1;
            default -> 2.5;
        };
        System.out.println("standaloneNumber=" + standaloneNumber);
        System.out.println("polyNumber=" + polyNumber.getClass().getSimpleName()
                + ":" + polyNumber);

        short small = switch (mode) {
            case 0 -> 12;
            default -> 30;
        };
        var inferred = switch (mode) {
            case 0 -> 12;
            default -> 30;
        };
        System.out.println("small=" + small + ", inferred=" + inferred);

        List<String> words = switch (mode) {
            case 0 -> List.of();
            default -> List.of("Java");
        };
        System.out.println("words=" + words);

        IntSupplier action = switch (mode) {
            case 0 -> () -> 10;
            default -> () -> 20;
        };
        System.out.println("action=" + action.getAsInt());

        printValue(switch (mode) {
            case 0 -> () -> "method";
            default -> () -> "other";
        });
        System.out.println("return=" + chooseMessage(mode).get());
        System.out.println("status=" + status(1));

        CharSequence text = switch (mode) {
            case 0 -> "abc";
            default -> new StringBuilder("def");
        };
        System.out.println("text=" + text);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SwitchTypesDemo.java
java SwitchTypesDemo
```

**Stdout chính xác:**

```text
standaloneNumber=1.0
polyNumber=Integer:1
small=12, inferred=12
words=[]
action=10
invocation=method
return=return-context
status=pending
text=abc
```

### 4.1. Tại sao standalone in `1.0` còn poly in `Integer:1`?

Cả hai switch có đúng hai result expressions `1` (literal `int`) và `2.5` (literal `double`); `mode = 0` khiến cùng nhánh đầu được chọn.

- `var standaloneNumber` khiến `switch` **standalone**. Do mixed `int`/`double`, numeric promotion xác định toàn switch là `double`; giá trị `1` được chuyển thành `1.0`.
- `Number polyNumber` khiến `switch` **poly** với target type `Number`. `1` tương thích với `Number` qua boxing thành `Integer`; `2.5` tương thích qua boxing thành `Double`. Khi nhánh đầu chạy, object runtime là `Integer`, còn biến `polyNumber` có **kiểu tĩnh `Number`**.

Điểm quan trọng: đây là ảnh hưởng thực tế đến chuyển đổi, không chỉ chuyện “đọc tên kiểu đẹp hơn”. Vì thế đừng mặc định hai câu lệnh khác nhau mỗi `var` và `Number` sẽ có hiệu ứng runtime giống hệt dù dùng cùng nhánh.

### 4.2. Tại sao `short small` hợp lệ?

Các kết quả `12` và `30` là các **constant expression** kiểu `int` có giá trị nằm trong khoảng của `short`. Poly switch trong **assignment context** cho phép từng hằng `int` được thu hẹp (narrowing) về `short` theo quy tắc gán hằng. Toàn switch có kiểu `short`.

Với `var inferred`, không có target `short`; hai nhánh `int` giữ kiểu `int`. Cả hai cùng in `12` nhưng có kiểu tĩnh khác nhau. Thay một hằng bằng `40000` ở `short small` sẽ khiến compiler báo lỗi vì vượt phạm vi `short`.

### 4.3. Kiểu trả về, kiểu tham số và interface

- `List<String> words`: target `List<String>` được truyền xuống cả nhánh `List.of()` rỗng và nhánh `List.of("Java")`, hữu ích cho suy luận generic.
- `IntSupplier action`: các lambda trong hai nhánh được nhận target functional interface `IntSupplier`, có phương thức `getAsInt()`.
- `printValue(switch (...))`: vì `printValue` nhận `Supplier<String>`, lời gọi tạo invocation context cho toàn switch và mỗi lambda.
- `return switch (...)` trong `chooseMessage`: kiểu trả về `Supplier<String>` được truyền xuống result expressions, dù không hề có biến cục bộ đích.
- `CharSequence text`: `String` và `StringBuilder` đều thực thi `CharSequence` nên hai nhánh hợp lệ với target interface này; không cần ép về `Object`.
- `status` cho thấy `yield` tạo giá trị cùng kiểu mong đợi `String`, còn `throw` chỉ là đường thoát bất thường.

## 5. Một ví dụ khác: generics và `var` không tương đương

**Tệp `GenericSwitchDemo.java`, chương trình độc lập (Java 17+):**

```java
import java.util.List;

public class GenericSwitchDemo {
    public static void main(String[] args) {
        int selection = 0;

        List<String> typed = switch (selection) {
            case 0 -> List.of();
            default -> List.of("Java");
        };

        var inferred = switch (selection) {
            case 0 -> List.of();
            default -> List.of("Java");
        };

        System.out.println("typed=" + typed);
        System.out.println("inferred=" + inferred);
    }
}
```

```bash
javac GenericSwitchDemo.java
java GenericSwitchDemo
```

Kết quả:

```text
typed=[]
inferred=[]
```

Hai giá trị runtime cùng là danh sách rỗng, nhưng:

- Ở `typed`, target `List<String>` được truyền đến mỗi `List.of(...)`, kể cả factory rỗng, nên kết quả có kiểu tĩnh `List<String>`.
- Ở `inferred`, `var` không cung cấp target `List<String>`. Các nhánh suy kiểu trước; compiler tính LUB/capture của những kiểu generic đã suy ra. Vì thế, trong ví dụ này, **không thể** thêm dòng dưới vào chương trình:

```java
// Ví dụ LỖI BIÊN DỊCH, không thêm vào chương trình chạy được ở trên:
List<String> copy = inferred;
```

`javac` báo `List<CAP#1> cannot be converted to List<String>` hoặc thông báo tương đương về wildcard capture. Dùng unchecked cast sẽ che giấu việc mất thông tin kiểu; giải pháp rõ nhất là khai báo biến kết quả với target `List<String>` ngay từ đầu.

Điều này quan trọng khi các nhánh gọi factory generic (`List.of`, `Set.of`, `Optional.empty`, v.v.). Đừng dùng `var` máy móc nếu API phía sau cần một kiểu tham số hóa chính xác.

## 6. Lambda/method reference cần target type

Lambda `() -> 10` không tự chứa thông tin “nó là `IntSupplier` hay `Supplier<Integer>`”. Functional interface được xác định bởi **target type**.

Ví dụ **poly**, đã xuất hiện trong chương trình đầy đủ:

```java
IntSupplier action = switch (mode) {
    case 0 -> () -> 10;
    default -> () -> 20;
};
```

Compiler truyền `IntSupplier` tới hai lambda rồi xác nhận chúng đều trả `int` theo phương thức trừu tượng `getAsInt()`. Khi dùng lời gọi phương thức, target functional interface nằm ở kiểu tham số; khi `return switch`, nó có thể nằm ở kiểu trả về khai báo.

Ngược lại, **không biên dịch**:

```java
// Ví dụ sai: var => standalone, lambda không có target.
var action = switch (mode) {
    case 0 -> () -> 10;
    default -> () -> 20;
};
```

Compiler không thể suy ra kiểu từ các lambda chưa có functional interface. Sửa bằng `IntSupplier action = switch (...) { ... };`, hoặc tạo giá trị nhánh vốn đã có kiểu functional interface rõ ràng.

**Phép cast bên ngoài không thay thế assignment context:**

```java
// Vẫn KHÔNG biên dịch: cast được áp dụng bên ngoài switch.
IntSupplier action = (IntSupplier) (switch (mode) {
    case 0 -> () -> 1;
    default -> () -> 2;
});
```

Tại vị trí này, `switch` nằm trong **casting context**, là standalone; vì vậy các lambda bên trong chưa có target type và không hợp lệ. Hãy dùng `IntSupplier action = switch (...) { ... };` để trình biên dịch cấp target đúng mức.

Method reference như `String::trim` cũng cần target functional interface; có thể dùng trong nhánh của poly switch khi các nhánh cùng tương thích kiểu giao diện đích.

## 7. Ngữ cảnh gán và ngữ cảnh lời gọi có quy tắc chuyển kiểu khác nhau

Đều là poly không có nghĩa hai ngữ cảnh cho phép **mọi** chuyển kiểu giống nhau.

- **Assignment context**: cho phép identity, widening, boxing/unboxing phù hợp và, trong giới hạn đặc biệt, **narrowing một constant expression số nguyên** vào `byte`, `short` hoặc `char` khi giá trị nằm trong khoảng.
- **Invocation context**: chuyển kiểu dựa trên strict/loose invocation; có thể widening và tùy giai đoạn boxing/unboxing. **Không** tự narrow một hằng `int` thành `short` chỉ vì phương thức nhận `short`.

Mã sau chỉ là **minh họa trong một lớp**:

```java
static void accept(short value) {
    System.out.println(value);
}

// Trong một phương thức có biến int mode:
short direct = switch (mode) {
    case 0 -> 12;
    default -> 30;
}; // Hợp lệ: assignment context narrow các hằng int thành short.

// accept(switch (mode) {
//     case 0 -> 12;
//     default -> 30;
// }); // Lỗi: invocation context không narrow int constant.

// Cách gọi hợp lệ: mỗi nhánh có kiểu short.
accept(switch (mode) {
    case 0 -> (short) 12;
    default -> (short) 30;
});
```

Đừng suy từ việc `short x = ...` hợp lệ rằng `accept(...)` cũng phải hợp lệ. Với API thực tế, nếu phương thức nhận `int` hợp lý hơn thì thiết kế tham số `int` có thể rõ ràng hơn nhiều cast.

## 8. `Boolean`, `null` và những trường hợp dễ gây nhầm

### 8.1. Boolean unboxing có thể tạo NullPointerException

Standalone switch có cả `boolean` và `Boolean` sẽ có kiểu `boolean` nếu mọi nhánh thuộc một trong hai kiểu đó. Nếu chọn nhánh `Boolean` chứa `null` thì việc unboxing sẽ ném `NullPointerException`.

```java
// Đoạn minh họa CỐ Ý gây lỗi runtime khi code = 1.
Boolean boxed = null;
int code = 1;
var value = switch (code) {
    case 0 -> true;
    default -> boxed;
};
```

Nếu chủ đích giữ giá trị tùy chọn, có thể dùng poly `Boolean value = switch (...) { ... };`; khi đó phải xử lý khả năng `null` trước khi gọi code cần primitive. Target typing không làm dữ liệu `null` tự an toàn.

### 8.2. Null literal và kiểu đích

```java
String message = switch (code) {
    case 0 -> null;
    default -> "ready";
}; // Poly: cả hai đều tương thích String.

// Không biên dịch: var không thể suy một kiểu local từ toàn null.
// var unknown = switch (code) {
//     case 0 -> null;
//     default -> null;
// };
```

Đoạn trên là minh họa tại một phương thức có `code`; nhánh trả `null` của biến `message` vẫn cần được kiểm tra trước khi dereference. Nếu mọi nhánh trả `null` thì standalone không cung cấp kiểu tham chiếu cụ thể để `var` suy ra.

### 8.3. Không phải giá trị nào cũng tự chuyển thành String

```java
// KHÔNG biên dịch: nhánh default có kiểu int, không phù hợp String.
String status = switch (code) {
    case 0 -> "OK";
    default -> 404;
};
```

Sửa thành `default -> "404";` hoặc, nếu thực sự cần nhiều loại giá trị, chọn một target type chung có ý nghĩa. Không nên ép đại `Object` chỉ để tránh xem xét ý nghĩa của từng kết quả.

### 8.4. `yield` trong khối phải tuân thủ target type như `case -> expression`

```java
String label = switch (code) {
    case 0 -> "OK";
    case 1 -> {
        String tmp = "PENDING";
        yield tmp;
    }
    default -> throw new IllegalArgumentException("Unknown code");
};
```

Ở ví dụ poly này, compiler kiểm tra `"OK"` và `tmp` theo target type `String`. Nếu đổi `yield tmp;` thành `yield 123;`, chương trình không biên dịch, dù lần chạy cụ thể không đi vào `case 1`.

### 8.5. Kiểu tĩnh không phải kiểu lớp runtime

`Number n` có thể trỏ đến `Integer` hoặc `Double`; `getClass()` cho biết **lớp runtime của object**, không cho biết kiểu tĩnh của biểu thức. `double` primitive không gọi `getClass()` trực tiếp được. Khi đọc output, phân biệt bước chọn nhánh, chuyển đổi khi đánh giá kết quả và kiểu đã được compiler gán.

### 8.6. Overload và generic có thể làm target type phức tạp hơn

Khi truyền poly switch vào phương thức có nhiều overload, compiler phải xét overload applicability và kiểu tham số có thể phù hợp; không luôn có một target type duy nhất dễ đoán chỉ bằng mắt. Trong API quan trọng, có thể tách kết quả vào biến với **kiểu khai báo rõ ràng**, sau đó mới gọi phương thức. Cách này giảm lỗi suy luận generic và làm code dễ đọc khi review.

## 9. Quy trình chọn kiểu kết quả trong ứng dụng

Trước khi viết `switch` trả giá trị, tự kiểm tra:

1. **Đầu ra có kiểu rõ ràng chưa?** Nếu là `String`, `List<Order>` hoặc `Supplier<Result>`, đặt kiểu đó ở biến, tham số hoặc kiểu trả về để nhận lợi ích của poly typing.
2. **Mỗi nhánh có thực sự tương thích với target không?** Xem cả nhánh ít được chạy, khối `yield`, generic factory, boxing/unboxing và khả năng `null`.
3. **Nếu dùng `var`, compiler sẽ hợp nhất các kiểu nào?** Với các nhánh số, cân nhắc numeric promotion; với các nhánh tham chiếu, cân nhắc LUB và wildcard capture; với lambda thì cần target functional interface.
4. **Kiểu chung có phản ánh đúng nghiệp vụ không?** Một interface/domain type cụ thể thường tốt hơn `Object`, và xử lý dữ liệu đúng cách tốt hơn ép kiểu để bịt lỗi compiler.
5. **Đã thử biên dịch với JDK dự án dùng chưa?** Java 14 đã chuẩn hóa `switch expression`, nên dùng cú pháp chính thức trên JDK 17+; không dùng cách viết preview cũ.

| Nhu cầu | Gợi ý |
| --- | --- |
| Nhánh đều tạo `String` | `String result = switch (...)` hoặc `var` nếu suy kiểu rõ |
| Nhánh số `int` và `double`; muốn kết quả số thực | `double result = switch (...)`, hoặc `var` nếu chấp nhận promotion |
| Muốn giữ các wrapper `Integer`/`Double` của từng nhánh | `Number result = switch (...)` |
| Nhánh tạo collection generic rỗng và có dữ liệu | `List<String> result = switch (...)` |
| Nhánh tạo lambda hay method reference | Khai báo functional interface đích |
| Nhánh tạo nhiều lớp cùng interface | Chọn interface đích phù hợp, ví dụ `CharSequence` |
| Nhánh có xử lý nhiều câu lệnh | `case x -> { ... yield value; }` |
| Nhánh invalid cần báo lỗi | `default -> throw new IllegalArgumentException(...)` |

## 10. Bài tập và hướng dẫn kiểm chứng

1. **Numeric promotion:** với `var n = switch(flag) { case 0 -> 2; default -> 4L; };`, xác định kiểu tĩnh và output khi `flag=0`. Sau đó đổi `var` thành `Number`, quan sát object runtime.
2. **Generic target:** tạo `List<String> list = switch(flag) { case 0 -> List.of(); default -> List.of("A"); };`; đổi thành `var` rồi thử gán kết quả sang `List<String>`.
3. **Functional target:** tạo `IntSupplier f = switch(flag)` với hai lambda; thay kiểu đích bằng `var` và giải thích lỗi compiler.
4. **Phương thức trả về:** viết phương thức `static CharSequence display(int x)` dùng `return switch`, một nhánh trả `String`, nhánh khác trả `StringBuilder`.
5. **Assignment so với invocation:** kiểm tra `short a = switch(flag) {case 0 -> 1; default -> 2;};` rồi thử truyền cùng biểu thức trực tiếp vào `accept(short)`. Sửa theo JLS 5.2/5.3.
6. **Kiểu và runtime:** chạy chương trình `SwitchTypesDemo` với `mode=0` và `mode=1`, so sánh `standaloneNumber`/`polyNumber` và giải thích bằng numeric promotion so với boxing.
7. **Yield:** viết một case dùng `yield String` và một case dùng `yield int`; xác định khi nào target `String` từ assignment context khiến compiler báo lỗi.

**Gợi ý đáp án:** (1) với `var` kết quả `long`, còn target `Number` có thể boxing `Integer`/`Long`; (2) `var` có thể suy wildcard generic rộng hơn; (3) lambda không có target functional interface thì không suy kiểu; (4) `CharSequence` tương thích cả hai nhánh; (5) chỉ assignment context cho phép narrowing constant trong giới hạn, invocation context không; (6) standalone `int/double` ra `double`, poly `Number` boxing theo từng nhánh; (7) toàn bộ result expressions phải tương thích với target, kể cả nhánh không được chọn tại runtime.

## 11. Nguồn đối chiếu chính thức

- **JLS Java 25, mục 15.28 và 15.28.1:** result expressions; poly/standalone; kiểu kết quả; `yield`; tính exhaustive. https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.28
- **JLS Java 25, mục 5.2 và 5.3:** assignment/invocation contexts; widening, boxing/unboxing và quy tắc narrowing constant. https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html
- **JLS Java 17, mục 15.28:** quy tắc ngôn ngữ vẫn áp dụng ở bản Java LTS phổ biến. https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28
- **OpenJDK JEP 361 — Switch Expressions:** tính năng ổn định kể từ Java 14. https://openjdk.org/jeps/361

**Ghi nhớ:** trước khi hỏi “`switch` trả kiểu gì?”, hãy hỏi **“`switch` này là standalone hay poly?”**. Sau đó mới áp dụng thuật toán suy kiểu của standalone hoặc kiểm tra từng result expression theo target type của poly.