# Type erasure ảnh hưởng đến pattern ra sao trong Java

## 1. Vấn đề: tại sao kiểm tra được List<?> nhưng không kiểm tra trực tiếp List<String> từ Object?

Java hỗ trợ generic như `List<String>`, `List<Integer>` và `Box<T>` để kiểm tra an toàn kiểu ở **thời điểm biên dịch**. Tuy nhiên, do cơ chế **type erasure**, phần lớn đối số kiểu generic (như `String` trong `List<String>`) không tồn tại dưới dạng thông tin riêng để JVM phân biệt các thể hiện khác nhau của cùng một generic class khi chạy.

Vì vậy, với một giá trị có kiểu tĩnh `Object`:

~~~java
if (value instanceof List<?> items) {
    System.out.println(items.size());
}
~~~

là một cách kiểm tra hợp lệ; nhưng:

~~~java
if (value instanceof List<String> strings) { // COMPILE ERROR
    System.out.println(strings.size());
}
~~~

bị từ chối. Lý do không đơn giản là “mọi generic pattern đều bị cấm”: Java kiểm tra **tính tương thích của phép cast tại compile time** và mức độ có thể xác minh ở runtime. Trong một ngữ cảnh kiểu tĩnh đã đủ cụ thể, `instanceof ArrayList<String>` vẫn có thể hợp lệ.

Bài này giải thích:

- Type erasure xóa thông tin nào và giữ lại thông tin nào.
- **Reifiable type** là gì, tại sao `List<?>` dùng được trong pattern matching.
- Tại sao `List<String>` không tự động được kiểm chứng bằng `instanceof`, và khi nào một pattern có đối số kiểu cụ thể vẫn biên dịch.
- Vì sao pattern matching không thay thế việc kiểm tra từng phần tử của collection.
- Cách suy luận generic record pattern trong Java 21 hoạt động mà không khôi phục thông tin kiểu đã bị xóa.
- Cách dùng `Class<T>` khi thật sự cần kiểm tra kiểu runtime.

Các ví dụ chính dùng **Java 17** cho `instanceof` pattern; ví dụ `switch` và generic record pattern cần **Java 21**.

## 2. Type erasure hoạt động như thế nào?

Theo Java Language Specification (JLS) `4.6, type erasure ánh xạ một kiểu có thông tin generic sang kiểu không chứa tham số generic hoặc type variable:

- `List<String>` và `List<Integer>` đều có erasure là `List`.
- `ArrayList<String>` và `ArrayList<Integer>` đều có erasure là `ArrayList`.
- Với `class Box<T>`, kiểu biến `T` bị xóa về erasure của **cận trái nhất**; nếu không khai báo cận tường minh thì cận mặc định là `Object`.
- Chẳng hạn `<T extends Number>` có erasure của `T` là `Number`.

Compiler vẫn dùng đầy đủ `List<String>` và `List<Integer>` để bắt nhiều lỗi **trước khi chạy**. Tại runtime, JVM thường nhìn thấy các đối tượng thuộc cùng lớp thực thi `ArrayList`, không biết một thể hiện được khai báo là `ArrayList<String>` và thể hiện kia là `ArrayList<Integer>`.

Vì thế:

~~~java
ArrayList<String> words = new ArrayList<>(List.of("a"));
ArrayList<Integer> numbers = new ArrayList<>(List.of(1));
System.out.println(words.getClass().equals(numbers.getClass()));
~~~

in `true`. Đoạn trích này cần `import java.util.ArrayList;` và `import java.util.List;` và được chạy đầy đủ ở phần tiếp theo.

**Type erasure không xóa lớp runtime của đối tượng.** Máy ảo vẫn phân biệt một `ArrayList` với `LinkedList`, một `String` với `Integer`, và vẫn kiểm tra được `instanceof List<?>`. Thứ bị thiếu là bằng chứng runtime cho đối số kiểu chính xác như `String` của một `List`.

Compiler có thể tạo các phép ép kiểu bổ sung tại một số vị trí đọc giá trị generic; lỗi `ClassCastException` có thể phát sinh khi đọc phần tử sai kiểu. Điều đó **không biến** một phép kiểm tra `instanceof List<?>` thành bước duyệt và xác thực mọi phần tử.

## 3. Reifiable type: kiểu nào kiểm tra được ở runtime?

JLS `4.7 gọi những kiểu có đủ thông tin cần thiết tại runtime là **reifiable types**.

Một số loại quan trọng:

| Kiểu | Reifiable? | Ý nghĩa với pattern |
| --- | --- | --- |
| `String`, `Integer`, `Number` | Có | JVM kiểm tra được lớp hoặc quan hệ kế thừa/interface |
| `List<?>` | Có | Có thể kiểm tra đối tượng có triển khai `List`; không xác nhận kiểu phần tử |
| `Map<?, ?>` | Có | Có thể nhận diện `Map`; không xác nhận kiểu khóa hay giá trị |
| `List` (raw type) | Có | Kiểm tra được, nhưng sử dụng raw type làm mất nhiều bảo đảm compile-time |
| `List<String>` | Không | Không thể kiểm chứng phần đối số kiểu `String` từ giá trị `Object` bất kỳ |
| `List<? extends Number>` | Không | Wildcard bị ràng buộc không giống wildcard không giới hạn `?` |
| `String[]` | Có | Kiểu thành phần `String` của mảng còn khả năng kiểm tra runtime |
| `List<?>[]` | Có | Phần tử mảng có kiểu reifiable `List<?>`; kiểu phần tử bên trong mỗi list vẫn chưa được xác nhận |

Với *parameterized type*, trường hợp reifiable điển hình là **mọi đối số kiểu đều là unbounded wildcard** `?`. `List<?>` nói “một danh sách có phần tử kiểu nào đó”, chứ không nói “một danh sách gồm các String”.

Lưu ý về `null`:

~~~java
Object value = null;
boolean ok = value instanceof List<?> items; // false
~~~

Type pattern `List<?>` không khớp `null`. Trái lại, bản thân một `List<?>` có thể chứa phần tử `null` nếu cách tạo danh sách cho phép; khi duyệt phần tử, cần xử lý trường hợp đó theo nghiệp vụ.

## 4. Ví dụ chạy được trên Java 17: List<?> và kiểm tra từng phần tử

Chương trình đầy đủ dưới đây kiểm tra **collection** bằng `List<?>`, rồi kiểm tra từng **element** bằng một type pattern `String text`.

Lưu thành `ReifiablePatternDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ReifiablePatternDemo {
    static void inspect(Object value) {
        if (value instanceof List<?> items) {
            System.out.println("LIST size=" + items.size());
            for (Object element : items) {
                if (element instanceof String text) {
                    System.out.println("STRING=" + text.toUpperCase());
                } else {
                    System.out.println("OTHER=" + element);
                }
            }
        } else {
            System.out.println("NOT_LIST");
        }
    }

    public static void main(String[] args) {
        inspect(List.of("java", 12, "patterns"));
        inspect("hello");
        ArrayList<String> words = new ArrayList<>(List.of("a"));
        ArrayList<Integer> numbers = new ArrayList<>(List.of(1));
        System.out.println("SAME_CLASS=" +
            words.getClass().equals(numbers.getClass()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ReifiablePatternDemo.java
java ReifiablePatternDemo
~~~

Kết quả:

~~~text
LIST size=3
STRING=JAVA
OTHER=12
STRING=PATTERNS
NOT_LIST
SAME_CLASS=true
~~~

Điểm cần hiểu:

1. `value instanceof List<?> items` kiểm tra đối tượng có phải một `List` hay không và gắn biến `items`. Nó **không** đảm bảo mọi phần tử đều là `String`.
2. Khi duyệt `List<?>`, giá trị phần tử được đọc ở dạng `Object`. Ta dùng `element instanceof String text` mới biết chắc phần tử đó là `String` để gọi `toUpperCase()`.
3. Giá trị `12` là `Integer` nên đi vào nhánh `OTHER`.
4. `"hello"` là `String`, không phải `List`, nên in `NOT_LIST`.
5. Hai `ArrayList` có generic type argument khác nhau cho ra cùng lớp runtime. Điều này minh họa type erasure.

Nếu mục tiêu là “danh sách chỉ chứa String”, chương trình cần thêm quy tắc xác thực các phần tử, chẳng hạn **tất cả phần tử đều là String**, thay vì chỉ kiểm tra `List<?>`.

## 5. Vì sao Object instanceof List<String> bị từ chối?

Đây là phương thức **cố ý không biên dịch** khi dùng Java 17/21:

~~~java
import java.util.List;

class BadObjectListString {
    static boolean test(Object value) {
        return value instanceof List<String> strings;
    }
}
~~~

Chạy `javac --release 17 BadObjectListString.java` sẽ nhận lỗi tiêu biểu:

~~~text
error: Object cannot be safely cast to List<String>
~~~

`Object` không cung cấp thông tin generic cần thiết để compiler cho phép phép kiểm tra có đích `List<String>` mà không phải thực hiện *unchecked conversion*. Do type erasure, runtime không có một “kiểu `List<String>`” riêng để kiểm tra bằng `instanceof`.

Cách viết thông dụng:

~~~java
if (value instanceof List<?> items) {
    // items là List<?>; kiểm tra phần tử khi cần
}
~~~

Đây là **đoạn minh họa** đặt trong phương thức có biến `value` kiểu `Object`. Bạn có thể duyệt `items` và dùng `instanceof String text` trên từng phần tử; hoặc truyền `items` cho một hàm validate nghiệp vụ.

Không nên “sửa” bằng raw type chỉ để dễ ép kiểu:

~~~java
if (value instanceof List items) {
    // Bỏ qua thông tin generic; dễ dẫn đến unchecked operations
}
~~~

Raw type được phép về mặt ngôn ngữ, nhưng `List<?>` thường diễn đạt đúng ý định hơn và giữ lại rào chắn compile-time đối với nhiều thao tác thêm phần tử.

## 6. Ngoại lệ quan trọng: một số generic type pattern có đối số cụ thể vẫn hợp lệ

Không nên kết luận “`instanceof` chỉ được dùng với các kiểu reifiable”. Từ Java 16, pattern matching for `instanceof` cho phép **một số** kiểu tham số hóa không reifiable, nếu kiểu tĩnh của expression bảo đảm phép kiểm tra hợp lệ theo quy tắc *checked cast conversion*.

Ví dụ chương trình Java 17 sau:

Lưu thành `StaticGenericPatternDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StaticGenericPatternDemo {
    static String inspect(List<String> input) {
        if (input instanceof ArrayList<String> items) {
            return "ARRAY_LIST=" + items.get(0).toUpperCase();
        }
        return "OTHER_LIST=" + input.size();
    }

    public static void main(String[] args) {
        System.out.println(inspect(
            new ArrayList<>(List.of("java"))
        ));
        System.out.println(inspect(List.of("java")));
    }
}
~~~

~~~bash
javac --release 17 StaticGenericPatternDemo.java
java StaticGenericPatternDemo
~~~

Kết quả:

~~~text
ARRAY_LIST=JAVA
OTHER_LIST=1
~~~

Vì sao biên dịch được?

- Kiểu **tĩnh** của `input` là `List<String>`, không phải `Object`.
- Pattern `ArrayList<String> items` kiểm tra xem đối tượng có là `ArrayList` hay không. Ở compile time, Java đã biết đối số kiểu tương thích từ `List<String>`.
- Lúc chạy, phép kiểm tra vẫn chỉ xác minh lớp phù hợp `ArrayList`; **không duyệt phần tử để chứng minh mọi phần tử là String**.
- Trong nhánh khớp, `items` có kiểu tĩnh `ArrayList<String>`, nên compiler cho phép gọi `items.get(0).toUpperCase()`.

Ngược lại, nếu tham số chỉ là `Object input`, pattern `ArrayList<String> items` thường không đáp ứng yêu cầu checked cast vì mất thông tin generic cần thiết. Do đó phải phân biệt **kiểu tĩnh của expression**, **kiểu đích của pattern**, và **điều kiện runtime**.

Cách ghi nhớ:

| Expression có kiểu tĩnh | Mẫu muốn thử | Hợp lệ? |
| --- | --- | --- |
| `Object` | `List<?> items` | Có |
| `Object` | `List<String> items` | Không |
| `List<String>` | `ArrayList<String> items` | Có |
| `Object` | `String text` | Có |
| `Object` | `List raw` | Có về cú pháp, nhưng raw type nên được hạn chế |

Một type pattern có thể hợp lệ dù kiểu đích không reifiable, miễn compiler chứng minh được tính an toàn phù hợp dựa trên ngữ cảnh kiểu tĩnh. **Điều này không đồng nghĩa runtime có generic type token.**

## 7. Heap pollution cho thấy pattern không xác thực phần tử

*Heap pollution* là tình huống một biến có kiểu tham số hóa có thể tham chiếu đến dữ liệu vi phạm kỳ vọng kiểu, thường do raw type hoặc unchecked operation. Đây là ví dụ **cố ý tạo dữ liệu sai** để hiểu giới hạn runtime.

Lưu thành `ErasurePollutionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ErasurePollutionDemo {
    @SuppressWarnings({"rawtypes", "unchecked"})
    static List<String> pollutedList() {
        List raw = new ArrayList<String>();
        raw.add(42);
        return raw;
    }

    public static void main(String[] args) {
        List<String> input = pollutedList();
        if (input instanceof ArrayList<String> items) {
            System.out.println("PATTERN_MATCH=" + items.size());
            try {
                String first = items.get(0);
                System.out.println(first);
            } catch (ClassCastException ex) {
                System.out.println("ELEMENT_CAST_FAILED");
            }
        }
    }
}
~~~

~~~bash
javac --release 17 ErasurePollutionDemo.java
java ErasurePollutionDemo
~~~

Kết quả:

~~~text
PATTERN_MATCH=1
ELEMENT_CAST_FAILED
~~~

Giải thích:

- Raw type trong `pollutedList` đã cho phép chèn `Integer 42` vào `ArrayList` mà phần còn lại của code nhìn là `List<String>`. Chú thích `@SuppressWarnings` chỉ ẩn cảnh báo ở đoạn cố ý tạo dữ liệu lỗi; không làm dữ liệu đúng kiểu.
- `input instanceof ArrayList<String> items` hợp lệ theo kiểu tĩnh `List<String>` và khớp với lớp runtime `ArrayList`.
- Khi đọc phần tử đầu tiên vào biến `String first`, JVM phải bảo vệ giả định `String` nên phép ép kiểu ngầm thất bại với `ClassCastException`.
- Kết quả chứng minh rằng **pattern matching không thực hiện kiểm tra sâu generic contents**.

Trong ứng dụng thật, tránh raw type và unchecked cast khi có thể. Nếu nhận dữ liệu từ API không tin cậy, collection không kiểu hoặc đối tượng do thư viện bên ngoài đưa vào, hãy xác thực dữ liệu trước khi sử dụng như một collection có kiểu cụ thể.

## 8. Type variable T không phải runtime pattern

Xét generic method:

~~~java
static <T> boolean test(Object value) {
    return value instanceof T; // COMPILE ERROR
}
~~~

Đây là đoạn **cố ý không biên dịch**: `T` là type variable, và runtime không có phép kiểm tra trực tiếp “giá trị có phải T hay không” từ đối tượng `Object` bất kỳ. Với `javac --release 17`, lỗi có nội dung tiêu biểu:

~~~text
error: Object cannot be safely cast to T
~~~

Điều tương tự thường thấy khi cố dùng `T.class` trong generic method: không có class literal đại diện cho một type variable không được reify.

Với `<T extends Number>`, erasure của `T` là `Number`; nhưng kiểm tra được “đây là Number” chưa chứng minh được “đây là đúng T” (có thể là `Integer` hoặc `Double`). Không được coi cận kiểu như một runtime generic type argument đã được giữ lại.

Nếu cần kiểm tra kiểu động có định danh cụ thể, hãy truyền đối tượng `Class<T>` cho phương thức như phần tiếp theo.

## 9. Class<T> dùng khi cần kiểm tra phần tử theo kiểu runtime cụ thể

`Class<T>` mang một **class token** do phía gọi cung cấp, ví dụ `String.class` hoặc `Integer.class`. Nhờ đó chương trình có thể kiểm tra từng giá trị bằng `isInstance` và chuyển đổi bằng `cast` với kiểu tĩnh được kiểm soát.

Lưu thành `ClassTokenDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ClassTokenDemo {
    static <T> List<T> matchingElements(
        List<?> source, Class<T> elementType
    ) {
        List<T> result = new ArrayList<>();
        for (Object element : source) {
            if (elementType.isInstance(element)) {
                result.add(elementType.cast(element));
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<?> values = List.of("a", 42, "b");
        System.out.println(matchingElements(values, String.class));
        System.out.println(matchingElements(values, Integer.class));
    }
}
~~~

~~~bash
javac --release 17 ClassTokenDemo.java
java ClassTokenDemo
~~~

Kết quả:

~~~text
[a, b]
[42]
~~~

Ở đây `String.class` thực sự tồn tại tại runtime và nhận diện `String`; `Integer.class` nhận diện `Integer`. Hàm trả về danh sách chứa **chỉ các phần tử khớp** kiểu được yêu cầu. Nếu cần *reject* cả danh sách khi có phần tử không khớp, thay vì lọc, hãy ném ngoại lệ khi gặp giá trị không phù hợp.

Giới hạn cần nhớ: `Class<T>` biểu diễn runtime class phù hợp, nhưng bạn không thể viết `List<String>.class` để mang đầy đủ generic type argument. Nếu phải diễn đạt cấu trúc nested generic, cần xây dựng một cơ chế xác thực cụ thể (hoặc type token của một thư viện thích hợp), chứ `Class<List<String>>` không tự xuất hiện từ `List.class`.

## 10. Pattern matching for switch cũng chịu giới hạn erasure (Java 21+)

Pattern matching trong `switch` được chuẩn hóa từ Java 21. Các case pattern cũng phải **applicable** với kiểu tĩnh của selector.

Chương trình đầy đủ dưới đây nhận diện list mà không giả vờ biết kiểu phần tử. Lưu thành `SwitchErasureDemo.java`:

~~~java
import java.util.List;

public class SwitchErasureDemo {
    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";
            case List<?> items -> "LIST=" + items.size();
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(List.of("a", 1, "b")));
        System.out.println(describe("hello"));
        System.out.println(describe(null));
    }
}
~~~

~~~bash
javac --release 21 SwitchErasureDemo.java
java SwitchErasureDemo
~~~

Kết quả:

~~~text
LIST=3
OTHER
NULL
~~~

`case List<?> items` hợp lệ với selector `Object` vì pattern có kiểu reifiable và JVM kiểm tra được collection. Trong nhánh này, `items` vẫn là `List<?>`; Java **không** suy ra phần tử nào là `String`.

Mã sau **cố ý không biên dịch** nếu selector có kiểu `Object`:

~~~java
static int invalid(Object value) {
    return switch (value) {
        case List<String> words -> words.size(); // COMPILE ERROR
        default -> 0;
    };
}
~~~

Lỗi tương tự `instanceof`: compiler không thể thực hiện phép kiểm tra an toàn đến `List<String>` từ `Object`. Khi muốn phân loại nội dung list, dùng `case List<?> items` rồi kiểm tra các phần tử hoặc gọi hàm xác thực.

Tính năng `switch` pattern và record pattern được dùng ở đây cần **Java 21+**; riêng `instanceof String text` và `instanceof List<?> items` dùng ổn định từ Java 16.

## 11. Generic record pattern: type inference dựa vào kiểu tĩnh, không khôi phục type argument đã bị xóa

Java 21 bổ sung record pattern ổn định, cho phép phân rã dữ liệu một record trong lúc khớp mẫu. Với generic record:

~~~java
record Box<T>(T payload) {}
~~~

pattern `Box(var item)` sẽ lấy component `payload`. Kiểu của `item` được compiler **suy luận từ thông tin kiểu tĩnh** có sẵn ở vị trí kiểm tra, không phải bằng cách đọc generic argument từ runtime object.

Chương trình đầy đủ `GenericRecordPatternDemo.java`:

~~~java
record Box<T>(T payload) {}

public class GenericRecordPatternDemo {
    static String known(Box<String> box) {
        if (box instanceof Box(var item)) {
            return "KNOWN=" + item.toUpperCase();
        }
        return "OTHER";
    }

    static String unknown(Object value) {
        if (value instanceof Box(var item)) {
            if (item instanceof String text) {
                return "STRING=" + text.toUpperCase();
            }
            return "PAYLOAD=" + item;
        }
        return "NOT_BOX";
    }

    public static void main(String[] args) {
        System.out.println(known(new Box<>("java")));
        System.out.println(unknown(new Box<>(42)));
        System.out.println(unknown(new Box<>("java")));
        System.out.println(unknown("hello"));
    }
}
~~~

~~~bash
javac --release 21 GenericRecordPatternDemo.java
java GenericRecordPatternDemo
~~~

Kết quả:

~~~text
KNOWN=JAVA
PAYLOAD=42
STRING=JAVA
NOT_BOX
~~~

Phân tích:

- Với `known(Box<String> box)`, compiler nhìn thấy kiểu tham số hóa `Box<String>`, nên `Box(var item)` suy luận `item` là `String`. Gọi `toUpperCase()` hợp lệ.
- Với `unknown(Object value)`, type pattern bên ngoài nhận ra một thể hiện của `Box`, nhưng `value` không mang thông tin generic tĩnh đủ cụ thể. `item` được suy luận là `Object`; vì vậy muốn dùng thao tác riêng của `String`, cần tiếp tục `item instanceof String text`.
- Không có bước “tự động tìm lại T tại runtime”. Với giá trị `new Box<>(42)`, component runtime là `Integer` nhưng compiler vẫn nhìn `item` như `Object` ở nhánh `unknown`.

Record pattern cũng không cho phép unchecked generic test. Đoạn sau **cố ý không biên dịch** với Java 21:

~~~java
record Container<T>(T value) {}

static boolean invalid(Container raw) {
    return raw instanceof Container<String>(var item);
}
~~~

Đây là đoạn minh họa gồm khai báo record và phương thức cần đặt trong class. `raw` chỉ có kiểu raw `Container`; compiler không thể chứng minh phép checked cast đến `Container<String>`. Lỗi tiêu biểu:

~~~text
error: Container cannot be safely cast to Container<String>
~~~

Muốn dùng generic record pattern an toàn, giữ thông tin generic trong khai báo tham số và dữ liệu từ đầu, hoặc dùng mẫu không đòi một đối số kiểu cụ thể rồi xác thực component.

## 12. Tóm tắt các tình huống điển hình

| Điều bạn muốn kiểm tra | Giải pháp | Có xác nhận nội dung generic ở runtime không? |
| --- | --- | --- |
| Đối tượng có phải list? | `value instanceof List<?> items` | Không |
| Đối tượng có phải String? | `value instanceof String text` | Có, đối với chính đối tượng này |
| Một List<?> có toàn String? | Duyệt phần tử và kiểm tra từng phần tử bằng `instanceof String` | Có, nếu kiểm tra tất cả theo tiêu chí xác định |
| Một List<String> có implementation ArrayList? | `input instanceof ArrayList<String> items` với `input` kiểu tĩnh `List<String>` | Chỉ nhận diện lớp implementation; không kiểm tra sâu generic |
| Muốn lấy phần tử thuộc Class<T> được truyền vào | `elementType.isInstance(...)` và `elementType.cast(...)` | Có, đối với lớp runtime đại diện bởi token |
| Generic record pattern trên Box<String> | `box instanceof Box(var item)` | Compiler suy luận `String` từ kiểu tĩnh; không kiểm tra generic argument runtime |
| Generic record pattern trên Object | `value instanceof Box(var item)` | Khớp Box; component có thể có kiểu tĩnh `Object` |

Các quy tắc *checked cast* và khả năng khớp áp dụng theo Java Language Specification của phiên bản đang biên dịch. Khi chuyển mã giữa các phiên bản, dùng `javac --release 17` hoặc `--release 21` để kiểm tra đúng cú pháp và API được phép.

## 13. Những lỗi phổ biến

1. **Cho rằng mọi `List<String>` đều có dấu vết kiểu String ở runtime.** Type erasure khiến một đối tượng `ArrayList` không mang một định danh riêng cho từng type argument.
2. **Cho rằng `List<?>` là `List<String>`.** `?` nghĩa là không biết kiểu phần tử; chỉ được dùng những thao tác hợp lệ cho kiểu chưa biết.
3. **Cho rằng type pattern luôn bắt buộc là reifiable.** Một pattern như `ArrayList<String>` có thể được dùng khi expression có kiểu tĩnh `List<String>` và phép checked cast hợp lệ.
4. **Dùng raw type rồi tin vào generic cast.** Raw operations có thể gây heap pollution; pattern khớp với lớp runtime vẫn không đảm bảo kiểu phần tử.
5. **Dùng type variable `T` trong `instanceof` như một runtime class.** Type variable không tự mang class token; truyền `Class<T>` khi thật sự cần nhận diện lớp cụ thể.
6. **Tin rằng generic record pattern suy ra T từ nội dung runtime.** Type inference dựa vào kiểu của expression và các ràng buộc compile-time.
7. **Dùng `case List<String>` trong switch(Object).** Selector `Object` không cung cấp phép checked cast an toàn đến kiểu tham số hóa đó.
8. **Quên `null`.** `null instanceof List<?>` là `false`. Với switch pattern, dùng `case null` khi muốn xử lý rõ trường hợp này.
9. **Đồng nhất việc pattern khớp với dữ liệu nghiệp vụ đã hợp lệ.** Ví dụ, một `List<?>` có thể chứa kiểu không mong muốn, `null` hoặc dữ liệu không thỏa điều kiện của ứng dụng. Cần validation riêng.

## 14. Bài tập và đáp án

### Bài tập 1 — Nhận biết reifiable

Trong các kiểu `List<?>`, `List<String>`, `String[]`, `Map<?, ?>` và `List<? extends Number>`, kiểu nào là reifiable?

**Đáp án:** `List<?>`, `String[]` và `Map<?, ?>`. `List<String>` và `List<? extends Number>` không reifiable vì type argument không phải toàn bộ unbounded wildcard.

### Bài tập 2 — Dự đoán biên dịch

~~~java
Object a = new ArrayList<String>();
List<String> b = new ArrayList<>();

boolean ok1 = a instanceof List<?> items;
boolean ok2 = a instanceof List<String> words;
boolean ok3 = b instanceof ArrayList<String> array;
~~~

Giả sử đã import `java.util.List` và `java.util.ArrayList`. Câu lệnh nào bị từ chối ở Java 17?

**Đáp án:** `ok2` bị từ chối vì `a` chỉ có kiểu tĩnh `Object`, không có checked cast phù hợp đến `List<String>`. `ok1` hợp lệ nhờ `List<?>` reifiable; `ok3` hợp lệ nhờ kiểu tĩnh `List<String>` của `b`. Đây là trích đoạn Java cần đặt trong một phương thức hoặc khối lệnh.

### Bài tập 3 — Chứng minh runtime chưa kiểm tra phần tử

Nếu một danh sách qua raw type bị thêm `42` nhưng được gán lại vào biến `List<String>`, tại sao `instanceof ArrayList<String>` có thể trả về `true` mà `String s = list.get(0)` lại ném `ClassCastException`?

**Đáp án:** Pattern kiểm tra lớp runtime `ArrayList` trên một phép chuyển đổi được compiler cho phép theo kiểu tĩnh. Khi đọc phần tử vào `String`, phép cast runtime mới thấy giá trị thực tế là `Integer`.

### Bài tập 4 — Generic record

Với `record Box<T>(T payload) {}`, hãy xác định kiểu của `item` trong hai trường hợp:

~~~java
// Java 21+, đặt bên trong các phương thức phù hợp:
Box<String> known = new Box<>("hi");
Object unknown = new Box<>("hi");

if (known instanceof Box(var item)) {
    System.out.println(item.toUpperCase());
}

if (unknown instanceof Box(var item)) {
    System.out.println(item);
}
~~~

**Đáp án:** Ở nhánh thứ nhất, `item` có kiểu tĩnh `String`. Ở nhánh thứ hai, `item` có kiểu tĩnh `Object`. Cả hai có thể chứa cùng giá trị runtime là `"hi"` nhưng phạm vi phương thức được phép gọi khác nhau do thông tin compile-time.

### Bài tập 5 — Thiết kế API an toàn

Bạn nhận `Object rawInput` có thể chứa một `List` gồm các `String`, số nguyên, hoặc đối tượng khác. Cần lấy các chuỗi và biến chúng thành chữ hoa. Bạn sẽ dùng `instanceof List<String>` hay `List<?>`?

**Đáp án:** Dùng `rawInput instanceof List<?> items`, rồi duyệt từng `Object element`, áp dụng `element instanceof String text` và gọi `text.toUpperCase()` với những phần tử khớp. Cách này không yêu cầu phép kiểm tra generic không thể thực hiện, và rõ ràng về việc bỏ qua hay xử lý các phần tử khác kiểu.

## 15. Nguyên tắc ghi nhớ

**Type erasure giữ lại đủ thông tin để nhận diện lớp/interface runtime, nhưng thường không giữ type argument của generic instance.** Vì thế:

- Pattern matching **không tự giải quyết** giới hạn của erasure.
- `List<?>` trả lời câu hỏi “đây có phải List không?”.
- `List<String>` là ràng buộc mạnh ở compile-time; từ `Object` bất kỳ không thể kiểm chứng đầy đủ bằng một pattern.
- Một số pattern tham số hóa như `ArrayList<String>` vẫn hợp lệ nhờ thông tin **kiểu tĩnh** ở phía expression; chúng không chạy kiểm tra từng phần tử.
- Khi cần bảo đảm kiểu dữ liệu bên trong, phải xác thực các thành phần hoặc nhận thông tin kiểu runtime thích hợp (như `Class<T>` cho lớp phần tử).

### Nguồn đặc tả

- JLS Java SE 21 `4.6 — Type Erasure: https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6
- JLS Java SE 21 `4.7 — Reifiable Types: https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7
- JLS Java SE 21 `15.20.2 — The instanceof Operator: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2
- Oracle Java 21 — Record Patterns, Generic Records: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
