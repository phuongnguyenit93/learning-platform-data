# Khi nào switch pattern tốt hơn chuỗi instanceof trong Java?

## 1. Bài toán: phân loại một đối tượng theo nhiều trường hợp

Một tham chiếu kiểu **Object**, một interface hoặc một lớp cha có thể giữ đối tượng thuộc nhiều kiểu cụ thể. Khi cần thực hiện hành vi khác nhau theo kiểu thực tế, cách quen thuộc là viết một chuỗi **if / else if** với **instanceof**:

~~~java
static String describe(Object value) {
    if (value == null) {
        return "null";
    }
    if (value instanceof String text) {
        return "text:" + text.strip();
    }
    if (value instanceof Integer number) {
        return "integer:" + number;
    }
    return "other";
}
~~~

Đoạn trên hợp lệ trên Java 17. Mỗi điều kiện tự kiểm tra kiểu và tạo **pattern variable** theo đúng nhánh. Với hai hoặc ba trường hợp, cách viết này thường đơn giản và dễ hiểu. Khi số kiểu tăng lên, có các điều kiện phụ và cần đảm bảo mỗi kiểu được xử lý, chuỗi **if / else if** có thể dài và khó nhìn thấy toàn bộ bảng phân loại.

Từ **Java 21**, **pattern matching for switch** trở thành tính năng chính thức. Ta có thể viết:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "text:" + text.strip();
        case Integer number -> "integer:" + number;
        default -> "other";
    };
}
~~~

Ở cách thứ hai, toàn bộ các nhánh đều nói về **cùng một giá trị value**. Cú pháp **case Type variable -> result** gộp kiểm tra kiểu, đặt tên biến và chọn kết quả vào một chỗ. Đây là lợi ích về cấu trúc và khả năng đọc; **switch không tự động nhanh hơn hoặc đúng hơn mọi chuỗi instanceof**.

**Phân biệt phiên bản:** type pattern trong **instanceof** là tính năng chính thức từ **Java 16**, dùng được trên **Java 17+**; type pattern và **when** trong **switch** được chuẩn hóa từ **Java 21**. Các ví dụ **switch pattern** trong bài yêu cầu **JDK 21+**.

## 2. Tiêu chí chọn nhanh: một đối tượng, nhiều nhánh loại trừ nhau

**Switch pattern thường tốt hơn** khi cùng một giá trị được phân loại thành một trong nhiều trường hợp và mỗi trường hợp tạo ra một kết quả hoặc một hành động rõ ràng:

- Có nhiều kiểu cần kiểm tra, chẳng hạn **String**, **Integer**, **List<?>**, **Message**, **Error**.
- Các nhánh là những lựa chọn thay thế cho nhau; sau khi chọn một nhánh, không cần kiểm tra nhánh còn lại.
- Muốn đọc danh sách trường hợp như một bảng ánh xạ **kiểu/điều kiện → kết quả**.
- Có **sealed hierarchy** và muốn compiler kiểm tra các nhánh đã bao phủ toàn bộ subtype được cho phép.
- Cần một **switch expression** tính ra giá trị, giúp tránh biến tạm và các lệnh **return** lặp đi lặp lại.

**Chuỗi instanceof vẫn phù hợp** khi chỉ có một hoặc hai phép thử, mỗi phép thử là một guard clause, cần xử lý nhiều tác dụng phụ, hoặc các điều kiện là những kiểm tra **độc lập** có thể cùng đúng. Switch chọn một nhánh phù hợp theo thứ tự case; nó không tự chạy tất cả phép kiểm tra đúng.

Bảng dưới đây tóm lược:

| Tình huống | Lựa chọn thường dễ đọc hơn | Vì sao |
| --- | --- | --- |
| Chỉ kiểm tra một kiểu và thoát sớm | **if (obj instanceof T t)** | Ngắn, điều kiện gần hành động |
| Một giá trị, nhiều loại kết quả loại trừ nhau | **switch pattern** | Các case nằm cạnh nhau, dễ so sánh |
| Cần trả về giá trị từ mỗi nhánh | **switch expression** | Cấu trúc nhất quán, kiểm tra đầy đủ nhánh |
| Nhiều subtype của sealed interface | **switch pattern** | Compiler kiểm tra tính bao phủ |
| Nhiều phép kiểm tra cùng phải thực hiện | Nhiều **if** độc lập | Switch chỉ chọn một nhánh |
| Điều kiện vừa kiểm tra dữ liệu vừa thoát sớm | **if** với guard clause | Diễn đạt luồng thoát sớm trực tiếp |
| Dự án dùng JDK 17 | **instanceof** pattern | Switch pattern chuẩn Java 21 chưa có |
| Chỉ phân loại vài hằng số/enum | **switch** thông thường | Không cần pattern type |

Lựa chọn cuối cùng còn phụ thuộc độ lớn phương thức, yêu cầu dự án và cách xử lý lỗi. Không nên đổi sang **switch** chỉ để có cú pháp mới.

## 3. Cùng một bài toán: if/instanceof và switch pattern

Ví dụ sau phân loại đầu vào thành các nhóm: **null**, chuỗi trắng, chuỗi có nội dung, số nguyên không âm, số nguyên âm, danh sách và kiểu khác. Hai cách viết có cùng hành vi.

Lưu toàn bộ mã thành **SwitchVsInstanceofDemo.java** và dùng **JDK 21+**:

~~~java
import java.util.List;

public class SwitchVsInstanceofDemo {
    static String withIf(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String blankText && blankText.isBlank()) {
            return "blank";
        }
        if (value instanceof String text) {
            return "text:" + text.strip();
        }
        if (value instanceof Integer positive && positive >= 0) {
            return "nonnegative:" + positive;
        }
        if (value instanceof Integer negative) {
            return "negative:" + negative;
        }
        if (value instanceof List<?> items) {
            return "list:" + items.size();
        }
        return "other:" + value.getClass().getSimpleName();
    }

    static String withSwitch(Object value) {
        return switch (value) {
            case null -> "null";
            case String text when text.isBlank() -> "blank";
            case String text -> "text:" + text.strip();
            case Integer number when number >= 0 ->
                    "nonnegative:" + number;
            case Integer number -> "negative:" + number;
            case List<?> items -> "list:" + items.size();
            default -> "other:" + value.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
                null,
                "   ",
                "  Java  ",
                7,
                -2,
                List.of("a", "b"),
                new StringBuilder("x")
        };

        for (Object input : inputs) {
            System.out.println(withIf(input) + " == " + withSwitch(input));
        }
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SwitchVsInstanceofDemo.java
java SwitchVsInstanceofDemo
~~~

Đầu ra kỳ vọng:

~~~text
null == null
blank == blank
text:Java == text:Java
nonnegative:7 == nonnegative:7
negative:-2 == negative:-2
list:2 == list:2
other:StringBuilder == other:StringBuilder
~~~

Cách kiểm tra:

1. **null** được xử lý trực tiếp bằng **value == null** trong **if** và **case null** trong **switch**.
2. Chuỗi chỉ chứa khoảng trắng khớp **String** và điều kiện **isBlank()**; case có **when** đứng trước case **String** tổng quát.
3. Chuỗi **"  Java  "** không blank, nên chuyển tới case **String** kế tiếp và được **strip()** thành **Java**.
4. Số nguyên **7** khớp điều kiện **number >= 0**, còn **-2** khớp case **Integer** không guard.
5. **List.of("a", "b")** khớp **List<?>** với **size() == 2**; pattern không suy đoán kiểu phần tử.
6. **StringBuilder** không khớp các type pattern kể trên, nên đi vào **default**.

Ở dạng **switch**, toàn bộ kết quả của việc phân loại hiện ra ngay trong một biểu thức **return switch (...)**. Khi cần thêm một nhóm, người đọc biết nơi nào chứa danh sách tất cả trường hợp. Trong dạng **if**, từng guard vẫn rất dễ hiểu nhưng phải đọc nhiều lần **value instanceof ...** và nhiều lệnh **return**.

## 4. when: điều kiện phụ giúp switch không chỉ phân loại theo lớp

Một type pattern như **case String text** chỉ xác nhận kiểu và gắn biến. Nhiều nghiệp vụ còn cần điều kiện về **nội dung** hoặc **trạng thái**, ví dụ chuỗi trắng, số dương, độ dài tối thiểu. Java 21 dùng **when** để thêm guard:

~~~java
// Đoạn nhãn case minh họa bên trong switch pattern Java 21:
case String text when text.isBlank() -> "blank";
case String text when text.length() >= 10 -> "long text";
case String text -> "short text";
~~~

Cách đánh giá:

- Chỉ khi giá trị khớp **String text**, biểu thức **when** mới được đánh giá. Biến **text** được dùng an toàn vì đã khớp kiểu.
- Nếu guard trả về **false**, switch tiếp tục xét nhãn case tiếp theo.
- Một type pattern cùng kiểu không kèm guard sẽ xử lý các giá trị còn lại thuộc kiểu đó.
- Điều kiện guard phải có kiểu **boolean**; cần tránh phép kiểm tra có tác dụng phụ bất ngờ hoặc tốn kém trong các case được xét lần lượt.

Thứ tự rất quan trọng. Nếu viết **case String text -> ...** trước các case **String ... when ...**, case tổng quát sẽ che khuất các case cụ thể. Compiler có thể báo **dominated case** thay vì cho code khó hiểu chạy.

Với chuỗi **if / else if**, thứ tự điều kiện cũng quyết định kết quả khi có nhiều điều kiện cùng đúng. Switch làm quy tắc lựa chọn và hiện tượng che khuất nhánh rõ ràng hơn qua nhãn **case** và kiểm tra của compiler.

## 5. Dominance: case tổng quát không được che case cụ thể

Pattern matching cho switch kiểm tra **dominance**: một nhãn case không được đứng sau một nhãn đã bao phủ toàn bộ các giá trị mà nó có thể khớp.

Ví dụ sau **cố ý sai**, chỉ để minh họa; không đặt vào chương trình chạy:

~~~java
// Không biên dịch trên Java 21:
return switch (value) {
    case CharSequence chars -> "length:" + chars.length();
    case String text -> "text:" + text;
    default -> "other";
};
~~~

Mọi **String** đều là **CharSequence**, nên case **String text** phía sau không bao giờ được chọn. Cách sửa là đặt nhánh cụ thể trước:

~~~java
// Hợp lệ trong một phương thức nhận Object value, trả về String (Java 21+):
return switch (value) {
    case String text -> "text:" + text;
    case CharSequence chars -> "length:" + chars.length();
    case null -> "null";
    default -> "other";
};
~~~

Nhánh **String** xử lý chuỗi, sau đó **CharSequence** xử lý các implementation còn lại như **StringBuilder**. Nhánh **null** riêng biệt vì type pattern không khớp null. Khi sắp xếp case, nên nghĩ từ **kiểu chuyên biệt → kiểu tổng quát**, đồng thời xem xét các guard nào có thể chồng lấn.

Compiler có thể phát hiện nhiều trường hợp case không thể tới được, nhưng không thể hiểu mọi quy tắc nghiệp vụ trong **when**. Chẳng hạn hai guard đều đúng với cùng một giá trị thì case đứng trước được chọn. Vì vậy việc kiểm thử các ranh giới vẫn cần thiết.

## 6. Exhaustiveness: lợi ích rõ rệt với sealed hierarchy

Nếu bài toán có một tập kiểu con được định nghĩa bằng **sealed interface**, switch expression Java 21 có thể yêu cầu các case bao phủ hết các subtype hợp lệ. Khi danh sách subtype thay đổi và chương trình được biên dịch lại, compiler có thể yêu cầu cập nhật switch.

Ví dụ hoàn chỉnh, lưu tệp **ExhaustiveSwitchDemo.java** (JDK 21+):

~~~java
public class ExhaustiveSwitchDemo {
    sealed interface Result permits Success, Failure {}

    record Success(String value) implements Result {}
    record Failure(int code) implements Result {}

    static String render(Result result) {
        return switch (result) {
            case Success success -> "success:" + success.value();
            case Failure failure -> "failure:" + failure.code();
        };
    }

    public static void main(String[] args) {
        System.out.println(render(new Success("done")));
        System.out.println(render(new Failure(403)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExhaustiveSwitchDemo.java
java ExhaustiveSwitchDemo
~~~

Kết quả:

~~~text
success:done
failure:403
~~~

Không cần **default** vì compiler biết **Result** chỉ cho phép hai implementation trực tiếp **Success** và **Failure**, cả hai đều được bao phủ. Nếu sau này cho phép thêm subtype, mã switch có thể cần thêm case để biên dịch thành công với định nghĩa mới.

Lưu ý quan trọng: **exhaustive đối với các subtype khác null không đồng nghĩa xử lý null**. Với phương thức **render(null)** trong ví dụ này, switch sẽ ném **NullPointerException** vì không có **case null**. Nếu contract cho phép null, thêm **case null -> ...** một cách tường minh. Không nên thêm **default** một cách máy móc vào mọi switch sealed: một nhánh default quá rộng có thể che mất lợi ích được compiler nhắc nhở khi hierarchy mở rộng.

Một chuỗi **if / else if** cũng có thể xử lý đúng hai subtype, nhưng compiler không tự bắt buộc các nhánh mới khi sealed hierarchy thay đổi. Đây là khác biệt thiết thực về khả năng bảo trì, không chỉ về số dòng mã.

## 7. Switch expression và switch statement: chọn hình thức nào?

**Switch expression** tạo ra một giá trị; nó phù hợp khi mục tiêu là **phân loại → tính kết quả**:

~~~java
static String label(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> text.strip();
        case Integer number -> "number:" + number;
        default -> "other";
    };
}
~~~

Đây là đoạn **phương thức minh họa** Java 21+, chưa phải chương trình có **main**. Vì là expression, các trường hợp phải đủ để compiler chứng minh luôn có kết quả phù hợp. Các nhánh dùng mũi tên (**->**) tránh lỗi rơi xuyên (**fall-through**) thường gặp với các **case** dạng dấu hai chấm cũ.

Nếu một nhánh cần nhiều bước để tính kết quả, dùng block và **yield**:

~~~java
static String labelWithBlock(Object value) {
    return switch (value) {
        case String text -> {
            String normalized = text.strip();
            yield normalized.isEmpty() ? "blank" : normalized;
        }
        case null -> "missing";
        default -> "other";
    };
}
~~~

**yield** đưa giá trị của nhánh block về cho **switch expression**; nó không đồng nghĩa với **return** ra khỏi toàn bộ phương thức. Trong phần thân nhánh **->**, cũng có thể viết switch statement để thực hiện tác vụ thay vì trả về một giá trị. Một switch statement có nhiều case được viết để làm tác dụng phụ vẫn có chỗ dùng, nhưng khi các nhánh chủ yếu tính một kết quả, expression thường ngắn và dễ kiểm tra hơn.

Switch pattern không tự động tốt khi mỗi case chứa một đoạn logic lớn. Khi đó, nên tách logic sang phương thức chuyên trách để switch giữ vai trò phân loại và điều phối.

## 8. Khi chuỗi instanceof hoặc đa hình vẫn tốt hơn

### 8.1. Chỉ có một kiểm tra kiểu

~~~java
static String readText(Object value) {
    if (value instanceof String text) {
        return text.strip();
    }
    return "(none)";
}
~~~

Một **if** ngắn thường dễ đọc hơn switch có một case và một default. Không cần tăng cấu trúc chỉ để thể hiện một điều kiện.

### 8.2. Guard clause để thoát sớm

~~~java
static int requireLength(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }
    return text.length();
}
~~~

Nhánh sai kết thúc bằng **throw**, nên compiler biết **text** đã khớp khi đi tới lệnh **return**. Đây là pattern variable với **flow scoping**, hợp lệ trên Java 17. Một switch expression có thể diễn đạt tương đương, nhưng guard clause thể hiện điều kiện tiên quyết rất trực tiếp.

### 8.3. Các kiểm tra độc lập, có thể cùng đúng

~~~java
static void inspect(Object value) {
    if (value instanceof CharSequence text) {
        System.out.println("length=" + text.length());
    }
    if (value instanceof java.io.Serializable) {
        System.out.println("serializable");
    }
}
~~~

Đoạn trên là **phương thức minh họa**, không phải chương trình đầy đủ. Với một **String**, cả hai điều kiện đều đúng và cả hai dòng được in. Dùng switch để thay trực tiếp sẽ thay đổi hành vi vì switch thông thường chọn **một** nhánh, không chạy tất cả case có thể khớp. Các phép kiểm tra độc lập nên giữ nhiều **if** hoặc được thiết kế thành những bước riêng.

### 8.4. Hành vi thuộc về chính đối tượng

Nếu interface do dự án quản lý đã có phương thức như **handle()**, thường nên gọi **message.handle()** qua đa hình thay vì phân loại kiểu của nó khắp nơi:

~~~java
interface Message {
    String handle();
}

// Trong phương thức nhận Message message:
String result = message.handle();
~~~

Đoạn này minh họa hợp đồng interface và một câu lệnh sử dụng, chưa phải chương trình độc lập. Đa hình phù hợp khi hành vi là trách nhiệm tự nhiên của từng implementation và có thể sửa chúng. Switch pattern hữu ích hơn khi thao tác là một góc nhìn bên ngoài (ví dụ serialization, mapping, reporting) hoặc khi làm việc với sealed data model.

### 8.5. Dự án phải hỗ trợ Java 17

Cú pháp **instanceof T variable** dùng được trên Java 17, nhưng **case T variable** và **when** trong switch chưa phải tính năng chuẩn ở phiên bản đó. Nếu build target là **--release 17**, dùng **if / else if** hoặc thiết kế đa hình; không sao chép code Java 21 vào dự án rồi mong compiler 17 chấp nhận.

## 9. Các vấn đề khi chuyển từ if sang switch

**Thứ tự và mức độ chuyên biệt.** Khi nhiều pattern có thể khớp, case được xét theo thứ tự; các case tổng quát có thể che case cụ thể, gây lỗi dominance. Kiểm tra subtype và guard trước khi chèn case mới.

**Khác biệt về null.** Với **value instanceof String text**, giá trị null chỉ làm điều kiện sai. Với switch tham chiếu, **switch (null)** có thể ném **NullPointerException** nếu không có nhánh phù hợp xử lý null; **default** không thay cho **case null**. Khi refactor từ if-chain có một nhánh dự phòng chấp nhận null, phải giữ rõ hành vi đó trong switch.

**Một nhánh được chọn so với nhiều nhánh độc lập.** Chuỗi **if** độc lập có thể thực thi nhiều khối; switch pattern chọn một case. Chỉ đổi trực tiếp khi hành vi ban đầu thực sự là các lựa chọn loại trừ nhau hoặc các nhánh đã **return**/**else if**.

**Kiểu generic.** **case List<?> items** cho phép nhận biết danh sách và gọi **size()**, nhưng không chứng minh phần tử là **String**. **List<String>** không trở thành reifiable chỉ vì đặt trong switch pattern. Vẫn cần kiểm tra phần tử hoặc dùng API có hợp đồng kiểu rõ ràng.

**Guard có tác dụng phụ.** Nếu **when** gọi phương thức thay đổi trạng thái, thứ tự case có thể làm thay đổi thứ tự side effect. Ưu tiên guard thuần kiểm tra và đặt xử lý có side effect vào phần thân nhánh.

**Không phải mọi trường hợp cần default.** Với **Object**, nhiều kiểu chưa liệt kê thì **default** thường cần thiết. Với sealed hierarchy được liệt kê đầy đủ, bỏ **default** có thể giúp compiler chỉ ra subtype mới cần xử lý khi biên dịch lại.

**Không giả định tối ưu hiệu năng.** JVM/JIT có thể biên dịch các cấu trúc điều khiển thành các kế hoạch thực thi khác nhau; không có quy tắc chung rằng switch pattern luôn nhanh hơn nhiều instanceof. Chọn theo độ rõ ràng và hợp đồng kiểu trước, đo bằng benchmark đại diện nếu hiệu năng thực sự là yêu cầu.

**Giữ chính xác logic cũ.** Khi chuyển code có điều kiện kết hợp, phải bảo toàn thứ tự kiểm tra, xử lý null, thông báo lỗi, khả năng ném ngoại lệ và chính sách cho giá trị không khớp. Một bản refactor trông gọn hơn nhưng đổi hành vi không được xem là tương đương.

## 10. Quy trình refactor có kiểm chứng

1. **Khoanh vùng một biểu thức phân loại.** Xác định tất cả điều kiện có đang kiểm tra cùng một đối tượng không; nếu kiểm tra nhiều đối tượng hoặc các điều kiện độc lập thì cân nhắc giữ if.
2. **Ghi lại các trường hợp đầu vào.** Bao gồm null, từng subtype, nhiều subtype giao nhau qua interface, điều kiện guard true/false và nhóm dự phòng.
3. **Chọn phiên bản JDK.** Chỉ dùng type pattern trong switch và **when** khi target Java 21+. Nếu target Java 17, dùng instanceof pattern.
4. **Chuyển nhánh riêng biệt thành case.** Giữ case cụ thể/guard trước case tổng quát, thêm **case null** nếu hợp đồng cần xử lý null.
5. **Chọn biểu thức hay statement.** Nếu mỗi nhánh tính ra giá trị, ưu tiên **return switch (...)**; nếu thực hiện tác vụ, dùng switch statement hoặc một phương thức điều phối rõ ràng.
6. **Đảm bảo bao phủ.** Với kiểu nguồn tổng quát, sử dụng default hợp lý; với sealed hierarchy, tận dụng kiểm tra exhaustiveness khi có thể.
7. **So sánh hành vi trước/sau.** Chạy cùng bộ input bằng cả hai phiên bản như **SwitchVsInstanceofDemo.java**. Kiểm tra thứ tự ưu tiên, trường hợp biên và ngoại lệ.
8. **Review độ dài và trách nhiệm nhánh.** Nếu case dài, trích xuất logic xử lý sang các phương thức riêng và giữ switch tập trung vào phân loại.

### Bài tập tự kiểm tra

**Câu 1:** Một phương thức chỉ nhận **Object**, nếu là **String** thì **strip()**, còn lại trả về giá trị mặc định. Dùng gì? **if (obj instanceof String s)** thường rõ nhất; switch pattern không mang lại lợi ích lớn.

**Câu 2:** Một **sealed interface** có các record **Created**, **Updated**, **Deleted**, mỗi subtype cần một bản mô tả. Dùng gì? **switch pattern Java 21** phù hợp để liệt kê và được compiler kiểm tra tính đầy đủ khi hierarchy thay đổi.

**Câu 3:** Cần vừa kiểm tra **CharSequence** vừa kiểm tra **Serializable** cho cùng một đối tượng và thực hiện hai tác vụ nếu cả hai đúng. Dùng gì? **Hai if độc lập**. Chuyển trực tiếp sang switch sẽ thay đổi số nhánh được thực thi.

**Câu 4:** Có case **String s** và **CharSequence cs**. Thứ tự nào? **String** trước **CharSequence** để tránh nhánh rộng che nhánh cụ thể. Nếu có case **String s when ...**, đặt case có guard trước case **String** tổng quát.

**Câu 5:** Code cũ trả về **"missing"** khi input null. Chuyển sang switch có **default -> "missing"** đã đủ chưa? **Chưa**: phải xét null riêng, thường bằng **case null -> "missing"**.

## 11. Tài liệu tham khảo

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): thiết kế và tính năng chính thức từ Java 21, guard, case null, dominance và exhaustiveness.
- [JLS 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): các quy tắc nhãn case, tính bao phủ và tính hợp lệ.
- [JLS 21 §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): cách switch expression tạo giá trị.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): type pattern, pattern variable và flow scoping đã chính thức trước Java 17.

**Kết luận:** Switch pattern đáng chọn khi đang phân loại **một giá trị** thành **nhiều nhánh loại trừ nhau**, đặc biệt khi cần **when** và tính bao phủ của **sealed hierarchy**. Với ít trường hợp, guard clause hoặc các kiểm tra độc lập, **instanceof** thường trực tiếp hơn. Quan trọng nhất là giữ đúng hành vi, xử lý null rõ ràng và dùng cú pháp tương thích phiên bản Java của dự án.