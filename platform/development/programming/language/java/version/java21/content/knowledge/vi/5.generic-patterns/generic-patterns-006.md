# Quan hệ giữa kiểu tĩnh, kiểu runtime và tính hợp lệ của pattern

Khi viết pattern trong Java 21, cần phân biệt kiểu mà trình biên dịch biết tại thời điểm biên dịch với lớp thực tế của đối tượng khi chương trình chạy. Kiểu tĩnh quyết định pattern có hợp lệ về mặt ngôn ngữ hay không. Nếu pattern hợp lệ, giá trị và lớp thực tế của đối tượng quyết định phép khớp có thành công hay không.

Quy tắc này đặc biệt quan trọng với generics. Java kiểm tra phần lớn quan hệ kiểu generic khi biên dịch, nhưng type erasure khiến JVM không lưu đầy đủ type argument của từng đối tượng. Vì vậy, pattern chỉ được phép yêu cầu những phép chuyển đổi mà Java có thể bảo đảm an toàn theo quy tắc kiểu.

## 1. Kiểu tĩnh và kiểu runtime

**Kiểu tĩnh (static type)** là kiểu mà trình biên dịch suy ra từ khai báo biến, tham số, biểu thức hoặc kiểu trả về của phương thức. Kiểu này được dùng để kiểm tra lời gọi phương thức, phép gán, ép kiểu và tính hợp lệ của pattern.

**Lớp runtime (runtime class)** là lớp thực tế của đối tượng được tham chiếu tại thời điểm chạy. Một biến có kiểu tĩnh là interface hoặc lớp cha vẫn có thể tham chiếu đến đối tượng thuộc một lớp triển khai hoặc lớp con.

Ví dụ:

```java
interface Payment {}

record CardPayment(String cardNumber) implements Payment {}
record CashPayment(int amount) implements Payment {}

static void process(Payment payment) {
    if (payment instanceof CardPayment card) {
        System.out.println("Card: " + card.cardNumber());
    } else if (payment instanceof CashPayment cash) {
        System.out.println("Cash: " + cash.amount());
    }
}

static void runExample() {
    Payment payment = new CardPayment("1234");
    process(payment);
}
```

Trong ví dụ này, kiểu tĩnh của `payment` là `Payment`, còn lớp runtime của đối tượng được tạo là `CardPayment`. Kiểu tĩnh `Payment` cho phép trình biên dịch xem xét các lớp có thể triển khai interface đó. Khi chạy, `instanceof` kiểm tra đối tượng thực tế và chỉ khởi tạo biến `card` nếu đối tượng khớp `CardPayment`.

Kiểu tĩnh không nhất thiết cho biết chính xác lớp runtime. Ngược lại, lớp runtime không thể làm cho một biểu thức pattern vốn không hợp lệ theo kiểu tĩnh trở thành hợp lệ. Trình biên dịch phải kiểm tra được quan hệ kiểu trước khi chương trình được chạy.

## 2. Điều kiện kiểu tĩnh để một pattern hợp lệ

Theo Java Language Specification 21, một type pattern có biến kiểu tham chiếu `U` áp dụng được tại kiểu tĩnh `T` khi `T` *checked cast convertible* sang `U`. Record pattern có thêm điều kiện: kiểu tĩnh phải checked cast convertible sang kiểu record của pattern, đồng thời từng component pattern phải áp dụng được với kiểu component tương ứng.

Có thể hiểu quy tắc này qua hai câu hỏi:

1. Dựa trên quan hệ kiểu được biết lúc biên dịch, phép chuyển đổi từ kiểu tĩnh sang kiểu pattern có khả thi và không cần unchecked narrowing conversion hay không?
2. Nếu phép chuyển đổi đó khả thi, giá trị thực tế có khớp với pattern khi chạy hay không?

Ví dụ, `Number` có thể tham chiếu đến một `Integer`, do đó pattern sau hợp lệ:

```java
static void printNumber(Number value) {
    if (value instanceof Integer integer) {
        System.out.println(integer.intValue());
    }
}
```

Trình biên dịch biết `Integer` là một lớp con của `Number`, nên phép kiểm tra từ `Number` sang `Integer` có thể thực hiện bằng kiểm tra runtime. Khi chạy, nhánh `if` chỉ được thực hiện nếu đối tượng thực tế là `Integer`.

Tương tự, một biểu thức có kiểu tĩnh `Object` có thể được kiểm tra với `String`:

```java
static int lengthOf(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
}
```

Ngược lại, nếu kiểu tĩnh không thể là kiểu pattern do quan hệ kế thừa và khai báo lớp, trình biên dịch báo lỗi. Ví dụ `String` và `Integer` là hai lớp không có quan hệ kế thừa có thể giao nhau:

```java
String value = "Java";

// Compile-time error: không thể chuyển String sang Integer.
if (value instanceof Integer number) {
    System.out.println(number);
}
```

Không cần chờ đến runtime để phát hiện trường hợp này. Mọi giá trị hợp lệ của biểu thức `value` đều không thể là một `Integer`, nên pattern không có phép chuyển đổi kiểu hợp lệ để kiểm tra.

## 3. Checked cast và unchecked conversion

*Checked cast convertible* là khả năng chuyển đổi kiểu bằng casting conversion mà không cần một narrowing reference conversion thuộc loại unchecked. Với chuyển đổi checked, JVM có thể kiểm tra lớp thực tế ở runtime khi cần. Với chuyển đổi unchecked, thông tin kiểu bị thiếu khiến JVM không thể xác nhận đầy đủ tính đúng đắn của type argument.

Pattern matching yêu cầu phép chuyển đổi kiểu phải được kiểm tra an toàn. Đây là lý do một số phép ép kiểu có thể viết được nhưng pattern tương ứng lại bị từ chối khi biên dịch.

Ví dụ với kiểu không generic:

```java
Object value = "Java 21";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Phép chuyển đổi từ `Object` sang `String` cần kiểm tra lớp runtime, nhưng không cần đoán type argument nào đã bị xóa. Nếu đối tượng không phải `String`, pattern đơn giản trả về `false`.

Với generic type, cần xét thêm type argument:

```java
import java.util.ArrayList;
import java.util.List;

static void inspect(List<Integer> values) {
    if (values instanceof ArrayList<Integer> arrayList) {
        System.out.println(arrayList.size());
    }
}
```

Pattern trên hợp lệ. Kiểu tĩnh `List<Integer>` và kiểu pattern `ArrayList<Integer>` có cùng type argument `Integer`; quan hệ giữa hai kiểu cho phép một checked narrowing conversion. Khi chạy, JVM kiểm tra lớp thực tế có phải `ArrayList` hoặc lớp con phù hợp hay không.

Hai trường hợp sau không hợp lệ:

```java
static void invalidPatterns(List<Integer> values, Object object) {
    // Compile-time error: List<Integer> không thể chuyển thành ArrayList<String>.
    if (values instanceof ArrayList<String> strings) {
        System.out.println(strings);
    }

    // Compile-time error: Object -> List<String> cần unchecked conversion.
    if (object instanceof List<String> strings) {
        System.out.println(strings);
    }
}
```

Trường hợp đầu bị từ chối vì `Integer` và `String` là các type argument không tương thích của cùng hệ phân cấp generic. Trường hợp thứ hai bị từ chối vì từ `Object`, JVM chỉ có thể kiểm tra đối tượng có phải `List` hay không; JVM không thể xác minh đối tượng đó là `List<String>`.

## 4. Type erasure và reifiable types

Java thực hiện type erasure đối với generics. Type argument như `String` hoặc `Integer` chủ yếu phục vụ kiểm tra kiểu khi biên dịch và không được lưu như một phần của lớp runtime của từng đối tượng.

Ví dụ, hai biến sau có thể tham chiếu đến các đối tượng cùng lớp runtime:

```java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

System.out.println(names.getClass() == numbers.getClass()); // true
```

Trong cả hai trường hợp, lớp runtime là `ArrayList`. JVM không thể dùng `getClass()` hoặc một type pattern để phân biệt `ArrayList<String>` với `ArrayList<Integer>` chỉ dựa trên type argument.

Một kiểu *reifiable* là kiểu có đủ thông tin để JVM biết đầy đủ tại runtime. Một số dạng thường gặp:

- Kiểu lớp hoặc interface không generic, ví dụ `String`, `Number`.
- Kiểu tham số hóa mà tất cả type argument là unbounded wildcard, ví dụ `List<?>`.
- Raw type, ví dụ `List`.
- Mảng có component type reifiable, ví dụ `String[]` hoặc `List<?>[]`.

`List<String>` và `List<Integer>` không phải reifiable types. Ngược lại, `List<?>` là reifiable vì wildcard không yêu cầu JVM xác định một type argument cụ thể.

Do đó, khi kiểu tĩnh chỉ là `Object`, pattern sau hợp lệ:

```java
static void inspectList(Object value) {
    if (value instanceof List<?> list) {
        for (Object element : list) {
            System.out.println(element);
        }
    }
}
```

Pattern chỉ xác nhận đối tượng là một `List`. Kiểu phần tử được xem là `Object` vì chương trình chưa có thông tin an toàn hơn về type argument. Nếu cần xử lý phần tử kiểu `String`, hãy kiểm tra từng phần tử:

```java
static void printStrings(Object value) {
    if (value instanceof List<?> list) {
        for (Object element : list) {
            if (element instanceof String text) {
                System.out.println(text.toUpperCase());
            }
        }
    }
}
```

Đây là cách kiểm tra đúng với dữ liệu chỉ biết ở runtime: kiểm tra container trước, sau đó kiểm tra kiểu thực tế của từng phần tử. Không nên suy luận rằng `List<?>` đã được xác nhận là `List<String>`.

## 5. Generic record patterns và suy luận type argument

Record pattern cũng chịu ràng buộc của kiểu tĩnh và checked cast conversion. Java 21 có thêm quy tắc suy luận type argument cho generic record pattern: khi pattern không ghi type argument, trình biên dịch có thể suy ra chúng từ kiểu của giá trị được kiểm tra và các ràng buộc kiểu của record.

```java
record Box<T>(T value) {}

static void printBox(Box<String> box) {
    if (box instanceof Box(var value)) {
        // value được suy luận là String.
        System.out.println(value.toUpperCase());
    }
}
```

Kiểu tĩnh của `box` là `Box<String>`. Từ kiểu đó, trình biên dịch suy luận pattern `Box(var value)` tương ứng với `Box<String>` và kiểu của `value` là `String`. Việc suy luận diễn ra lúc biên dịch, không phải do JVM đọc được type argument `String` từ đối tượng.

Có thể viết tường minh type argument khi kiểu nguồn cung cấp đủ thông tin:

```java
static void printBoxExplicit(Box<String> box) {
    if (box instanceof Box<String>(String value)) {
        System.out.println(value.toUpperCase());
    }
}
```

Nếu nguồn chỉ có raw type, việc yêu cầu một type argument cụ thể không an toàn:

```java
static void invalidRawBox(Box box) {
    // Compile-time error: raw Box không chứng minh được Box<String>.
    if (box instanceof Box<String>(var value)) {
        System.out.println(value);
    }
}
```

Trong trường hợp này, compiler không thể suy ra hoặc xác minh `String` từ raw type. Không nên dùng cast hay `@SuppressWarnings` để che khuất vấn đề rồi coi pattern là đã xác nhận nội dung generic; hãy giữ kiểu generic cụ thể trong API và tại nơi tạo dữ liệu.

Record pattern lồng nhau cũng áp dụng quy tắc tương tự. Kiểu của component được xác định từ kiểu record pattern sau khi suy luận generic; component pattern phải có khả năng chuyển đổi checked từ kiểu component đó.

```java
record Payload<T>(T data) {}
record Message<T>(String id, Payload<T> payload) {}

static void inspectMessage(Message<String> message) {
    if (message instanceof Message(var id, Payload(var data))) {
        // id và data đều có kiểu String.
        System.out.println(id + ": " + data.toUpperCase());
    }
}
```

## 6. Phân biệt lỗi biên dịch và kết quả không khớp lúc chạy

Không phải mọi pattern không khớp đều là lỗi. Cần xác định vấn đề xuất hiện ở giai đoạn nào:

| Tình huống | Giai đoạn phát hiện | Kết quả |
| --- | --- | --- |
| Kiểu tĩnh không thể chuyển đổi checked sang kiểu pattern, ví dụ `String` sang `Integer` | Compile time | Compiler báo lỗi; chương trình không được biên dịch thành công. |
| Kiểu tĩnh là `Object`, pattern là `String`, nhưng đối tượng thực tế là `Integer` | Runtime | Pattern không khớp; `instanceof` trả về `false`. |
| Giá trị kiểm tra là `null` trong một biểu thức `instanceof` | Runtime | Kết quả là `false`; pattern variable không được khởi tạo. |
| Kiểu generic yêu cầu unchecked narrowing conversion, ví dụ raw `List` sang `List<String>` | Compile time | Pattern bị từ chối vì JVM không thể xác minh type argument. |
| Kiểu tĩnh generic tương thích, nhưng lớp runtime không phải kiểu pattern, ví dụ `List<Integer>` đang tham chiếu `LinkedList<Integer>` và pattern là `ArrayList<Integer>` | Runtime | Pattern không khớp; `instanceof` trả về `false`. |
| Generic record pattern có thể suy luận type argument từ kiểu nguồn | Compile time và runtime | Compiler suy luận kiểu component; khi chạy, record và các component vẫn phải khớp pattern. |

Ví dụ cho trường hợp kiểu tĩnh hợp lệ nhưng giá trị runtime không khớp:

```java
static void checkList(List<Integer> values) {
    if (values instanceof ArrayList<Integer> arrayList) {
        System.out.println("ArrayList: " + arrayList.size());
    } else {
        System.out.println("Một kiểu List khác");
    }
}

static void runCheckList() {
    checkList(new java.util.LinkedList<>(List.of(1, 2, 3)));
}
```

Kiểu tĩnh `List<Integer>` có thể chuyển đổi checked sang `ArrayList<Integer>`, vì vậy mã nguồn hợp lệ. Nhưng đối tượng được truyền vào là `LinkedList`, nên pattern trả về `false` và chương trình chạy nhánh `else`.

## 7. Quan hệ kiểu trong `switch` pattern

Các nhãn `case` dùng type pattern hoặc record pattern cũng phải phù hợp với kiểu tĩnh của selector. Chẳng hạn, selector có kiểu `Object` có thể được kiểm tra bằng các pattern `String` và `Integer`:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        case null -> "null";
        default -> "Other type";
    };
}
```

Ngoài tính hợp lệ của quan hệ kiểu, `switch` còn có quy tắc riêng về tính đầy đủ (exhaustiveness) và nhánh bị chi phối (dominance). Một nhãn tổng quát có thể bao phủ nhãn cụ thể phía sau và khiến switch không hợp lệ. Vì vậy, khi kiểm tra lỗi switch, hãy kiểm tra cả kiểu selector, khả năng chuyển đổi của từng pattern, thứ tự nhánh và độ bao phủ các giá trị.

## 8. Quy trình xác định một pattern có hợp lệ hay không

Khi gặp một pattern phức tạp, có thể lần lượt kiểm tra:

1. Xác định kiểu tĩnh của biểu thức hoặc selector. Đừng dùng giá trị mẫu đang quan sát trong debugger để thay thế thông tin kiểu mà compiler nhìn thấy.
2. Xác định kiểu pattern và quan hệ kế thừa/triển khai giữa kiểu nguồn với kiểu đích.
3. Kiểm tra phép chuyển đổi có phải checked cast conversion hay có cần unchecked narrowing conversion.
4. Với generic type, so sánh type argument và lưu ý type erasure. `List<?>` không chứng minh được `List<String>`.
5. Với generic record pattern, xác định type argument tường minh hoặc kiểu mà compiler có thể suy luận từ kiểu nguồn.
6. Nếu mã biên dịch thành công, xét lớp runtime và giá trị component để xác định pattern có khớp hay không.
7. Với `switch`, kiểm tra thêm dominance và exhaustiveness.

Nguyên tắc thực hành là giữ kiểu generic cụ thể xuyên suốt API, tránh raw type và unchecked cast. Khi chỉ có dữ liệu không rõ type argument, dùng wildcard như `List<?>`, rồi kiểm tra từng phần tử bằng pattern riêng nếu nghiệp vụ cần một kiểu cụ thể.

## 9. Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): tính áp dụng của type pattern và record pattern; cách khớp giá trị ở runtime.
- [Java Language Specification, Java SE 21 — §15.20.2 The `instanceof` Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): điều kiện kiểu tĩnh và kết quả kiểm tra lúc chạy.
- [Java Language Specification, Java SE 21 — §5.5 Casting Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.5): checked cast compatibility và checked cast convertibility.
- [Java Language Specification, Java SE 21 — §4.7 Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7): các kiểu có thể được xác định đầy đủ tại runtime.
- [Java Language Specification, Java SE 21 — §18.5.5 Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5): quy tắc suy luận type argument cho generic record patterns.
- [Oracle Java 21 — Pattern Matching for the `instanceof` Operator](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html): ví dụ type pattern, quan hệ kiểu và phạm vi biến pattern.
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): generic record patterns, suy luận kiểu và trường hợp unchecked conversion bị từ chối.
- [Oracle Java 21 — Pattern Matching for `switch`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): tính đầy đủ và dominance của các nhãn switch pattern.
