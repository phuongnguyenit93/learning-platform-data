# Kiểu nguồn và kiểu đích phải tương thích thế nào trong Java pattern matching?

## 1. Phân biệt kiểu khai báo và kiểu của đối tượng thực tế

Khi dùng **pattern matching for instanceof**, Java cần trả lời hai câu hỏi khác nhau:

1. **Lúc biên dịch:** kiểu tĩnh của biểu thức bên trái (**kiểu nguồn**, source type) có cho phép phép thử với kiểu được viết trong type pattern bên phải (**kiểu đích**, target/pattern type) hay không?
2. **Lúc chạy:** giá trị thực tế có phải một đối tượng khác **null** tương thích với kiểu đích hay không?

Ví dụ Java 17:

~~~java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Kiểu nguồn **S = Object**, kiểu đích **T = String**. Compiler cho phép biểu thức vì một tham chiếu **Object** có thể trỏ đến một **String**. Khi chạy, giá trị ở đây thật sự là **String**, nên phép khớp thành công, biến **text** có kiểu tĩnh **String** và **length()** trả về **4**.

Đổi dữ liệu mà không đổi kiểu nguồn:

~~~java
Object value = 42;
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Chương trình **vẫn biên dịch**: điều kiện tương thích được quyết định theo kiểu tĩnh **Object**. Khi chạy, đối tượng thực tế là **Integer**, không phải **String**, nên **instanceof** trả về **false**, khối **if** không chạy. Phép thử thất bại theo cách thông thường; nó không tự ném **ClassCastException**.

Cần ghi nhớ: **có thể biên dịch** không có nghĩa là **chắc chắn khớp lúc chạy**. Mặt khác, một phép thử Java có thể chứng minh là không hợp lệ hoặc không cần thiết cũng có thể bị compiler bác bỏ trước khi chạy.

## 2. Ba quy tắc quan trọng đối với type pattern của instanceof trong Java 17

Với biểu thức **expression instanceof T variable**, đặt **S** là kiểu tĩnh của **expression** và **T** là kiểu của pattern.

**Quy tắc 1 — vế trái phải có kiểu tham chiếu hoặc kiểu null.** Trên Java 17, type pattern trong **instanceof** dùng kiểu tham chiếu, ví dụ **String**, **Number**, **Runnable**, **String[]**; không dùng trực tiếp primitive type pattern như **int x**.

~~~java
Object value = 10;
if (value instanceof Integer number) {
    System.out.println(number + 1);
}
~~~

**Integer** là kiểu wrapper tham chiếu. **10** được boxing thành **Integer** khi gán cho **Object**. Ngược lại, **int value = 10; if (value instanceof Integer n) ...** không hợp lệ trong Java 17 vì vế trái có kiểu nguyên thủy **int**.

**Quy tắc 2 — S phải có khả năng chuyển đổi kiểm tra kiểu đến T.** Đặc tả Java 17 gọi đây là khả năng **downcast compatible**. Nói theo cách thực hành: tại thời điểm biên dịch, phải còn khả năng tồn tại một đối tượng hợp lệ có thể được xem là **T** khi biểu thức có kiểu **S**. Không bắt buộc S và T là quan hệ cha–con trực tiếp; hai interface cũng có thể phù hợp nếu có một lớp triển khai đồng thời cả hai.

**Quy tắc 3 — với type pattern trong instanceof Java 17, S không được là subtype của T.** Nếu biểu thức đã có kiểu tĩnh **T** hoặc kiểu con của **T**, compiler báo lỗi cho mẫu kiểu quá tổng quát. Kiểm tra ấy không bổ sung thông tin phân loại kiểu cần thiết.

~~~java
String text = "hello";

// Sai trên Java 17: String đã là subtype của CharSequence.
// if (text instanceof CharSequence sequence) { ... }

// Sai trên Java 17: kiểu nguồn và kiểu pattern trùng nhau.
// if (text instanceof String same) { ... }

// Đúng: gọi phương thức trực tiếp trên biến có kiểu đã đủ cụ thể.
System.out.println(text.length());
~~~

Đừng nhầm quy tắc 3 với **instanceof** kiểu cũ không khai báo biến pattern. Biểu thức **text instanceof CharSequence** (không có **sequence**) là cú pháp type comparison hợp lệ trong Java 17; còn **text instanceof CharSequence sequence** là type pattern bị compiler từ chối khi kiểu tĩnh nguồn đã là subtype của đích.

Ba quy tắc trên dành cho **instanceof type pattern trong Java 17**. Các phiên bản Java mới hơn có thể bổ sung dạng pattern và kiểm tra khác; khi học Java 17, hãy dùng chính quy tắc và compiler của Java 17.

## 3. Các quan hệ kiểu thường gặp

| Kiểu nguồn S (khai báo) | Kiểu pattern T | Hợp lệ với instanceof type pattern Java 17? | Lý do |
| --- | --- | --- | --- |
| **Object** | **String** | Có | Object có thể giữ một String |
| **CharSequence** | **String** | Có | String triển khai CharSequence; cần kiểm tra kiểu cụ thể lúc chạy |
| **Number** | **Integer** | Có | Integer là một subtype của Number |
| **Object** | **String[]** | Có | Mảng là kiểu tham chiếu; Object có thể giữ một mảng String |
| **Object** | **List<?>** | Có | Có thể kiểm tra kiểu danh sách không yêu cầu biết kiểu phần tử |
| **InterfaceA** | **InterfaceB** | Có thể | Có thể tồn tại class triển khai đồng thời hai interface |
| **String** | **Integer** | Không | Hai lớp cuối cùng không có một đối tượng chung vừa là String vừa là Integer |
| **String** | **CharSequence** | Không | S đã là subtype của T; type pattern này quá tổng quát trên Java 17 |
| **String** | **String** | Không | S và T trùng nhau; type pattern bị từ chối trên Java 17 |
| **int** | **Integer** | Không | int không phải kiểu tham chiếu ở vế trái instanceof Java 17 |
| **Object** | **List<String>** | Không | Không thể kiểm tra phần tử generic String bằng type pattern này do type erasure |

Bảng chỉ xét câu lệnh kiểu **source instanceof Target variable** trên Java 17, không phải mọi hình thức ép kiểu hay mọi dạng **switch** pattern. Với interface, chữ **“có thể”** phụ thuộc quan hệ và ràng buộc cụ thể, đặc biệt nếu kiểu nguồn là một lớp **final** không triển khai interface đích.

## 4. Quan hệ cha–con: hướng kiểm tra rất quan trọng

Có một interface **CharSequence**, với implementation như **String** và **StringBuilder**:

~~~java
CharSequence source = new StringBuilder("abc");

if (source instanceof String text) {
    System.out.println("String: " + text);
} else {
    System.out.println("Không phải String");
}
~~~

Compiler chấp nhận vì kiểu nguồn **CharSequence** có thể trỏ đến **String**. Khi chạy, đối tượng là **StringBuilder**, nên nhánh **else** được chọn. Nếu gán **source = "abc"**, type pattern sẽ khớp và **text** được gắn.

Đi theo chiều ngược lại trong Java 17:

~~~java
String source = "abc";

// Không hợp lệ với type pattern:
// if (source instanceof CharSequence sequence) { ... }

// Dùng trực tiếp phương thức có sẵn:
System.out.println(source.length());
~~~

Với **String source**, việc tạo pattern **CharSequence sequence** bị từ chối bởi quy tắc kiểu nguồn là subtype của kiểu pattern. Nếu thực sự cần thể hiện một giá trị qua kiểu interface, có thể gán tường minh:

~~~java
CharSequence sequence = source;
System.out.println(sequence.length());
~~~

Không nên ép kiểu vòng qua **Object** chỉ để làm cho một type pattern vốn không cần thiết được biên dịch. Điều đó làm khó đọc mà không đem lại kiểm tra kiểu có ích.

Tương tự, từ **Number** về **Integer** là phép phân loại hợp lý:

~~~java
Number n = Integer.valueOf(7);
if (n instanceof Integer integer) {
    System.out.println(integer + 1);
}
~~~

Đầu ra là **8**. Nếu **n** giữ một **Double** thì pattern **Integer** không khớp và nhánh không chạy.

## 5. Hai interface không cần có quan hệ kế thừa trực tiếp

Một lỗi nhận thức phổ biến là cho rằng S và T phải nằm cùng một chuỗi cha–con. Trên thực tế, một class có thể triển khai **nhiều interface**, nên một tham chiếu kiểu interface A có thể chứa đối tượng đồng thời triển khai interface B.

~~~java
interface Named {
    String name();
}

interface Tagged {
    String tag();
}

final class Item implements Named, Tagged {
    public String name() { return "item"; }
    public String tag() { return "v1"; }
}

static String label(Named source) {
    if (source instanceof Tagged tagged) {
        return source.name() + ":" + tagged.tag();
    }
    return source.name();
}
~~~

Đoạn trên minh họa khai báo trong một class hoặc tệp hợp lệ; nó chưa phải toàn bộ chương trình có **main**. Kiểu nguồn **Named**, kiểu đích **Tagged**. Vì có thể tồn tại **Item** triển khai cả hai, phép thử hợp lệ. Compiler không đòi **Named extends Tagged** hoặc ngược lại.

Nhưng nếu kiểu nguồn là một class **final** không triển khai target interface và không thể có subclass, kiểu giao nhau đó có thể bất khả thi. Ví dụ **String** là class final, không triển khai **Runnable**, nên **String value; value instanceof Runnable task** không hợp lệ trong Java 17.

## 6. Ví dụ Java 17 chạy được: nhiều kiểu nguồn và kiểu đích

Tạo tệp **TypeCompatibilityDemo.java** với toàn bộ nội dung sau:

~~~java
public class TypeCompatibilityDemo {
    interface Named {
        String name();
    }

    interface Tagged {
        String tag();
    }

    static final class Both implements Named, Tagged {
        @Override
        public String name() { return "note"; }

        @Override
        public String tag() { return "v1"; }
    }

    static final class OnlyNamed implements Named {
        @Override
        public String name() { return "plain"; }
    }

    static String describe(Object source) {
        if (source instanceof String text) {
            return "String:" + text.length();
        }
        if (source instanceof Number number) {
            return "Number:" + number.intValue();
        }
        if (source instanceof CharSequence sequence) {
            return "CharSequence:" + sequence.length();
        }
        return source == null ? "null" : "other";
    }

    static String inspectNumber(Number source) {
        if (source instanceof Integer integer) {
            return "Integer:" + (integer + 1);
        }
        return "not Integer";
    }

    static String inspectInterfaces(Named source) {
        if (source instanceof Tagged tagged) {
            return source.name() + ":" + tagged.tag();
        }
        return source.name() + ":untagged";
    }

    static String inspectArray(Object source) {
        if (source instanceof String[] values) {
            return "String[]:" + values.length;
        }
        return "not String[]";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(12));
        System.out.println(describe(new StringBuilder("abc")));
        System.out.println(describe(null));

        System.out.println(inspectNumber(7));
        System.out.println(inspectNumber(2.5));

        System.out.println(inspectInterfaces(new Both()));
        System.out.println(inspectInterfaces(new OnlyNamed()));

        System.out.println(inspectArray(new String[] {"A", "B"}));
        System.out.println(inspectArray(new int[] {1, 2}));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 TypeCompatibilityDemo.java
java TypeCompatibilityDemo
~~~

Đầu ra:

~~~text
String:4
Number:12
CharSequence:3
null
Integer:8
not Integer
note:v1
plain:untagged
String[]:2
not String[]
~~~

**Giải thích lần lượt:**

1. **describe** nhận tham số khai báo kiểu **Object**, nên có thể kiểm tra các pattern **String**, **Number**, **CharSequence**. Đối tượng **"Java"** khớp **String** và có độ dài 4.
2. Số **12** được autobox thành **Integer**, khớp pattern **Number**, nên **intValue()** trả về 12.
3. **StringBuilder("abc")** không khớp nhánh **String**, nhưng khớp **CharSequence**, độ dài 3.
4. **null** không khớp bất kỳ type pattern nào của **instanceof**, nên đi tới nhánh trả về **null** như một chuỗi mô tả.
5. Tham số **Number** trong **inspectNumber** có thể được thử với subtype **Integer**. Integer 7 khớp và cho 8; Double 2.5 không khớp và trả về **not Integer**.
6. **Both** triển khai hai interface nên **Named → Tagged** khớp; **OnlyNamed** không triển khai **Tagged** nên chọn nhánh dự phòng.
7. **String[]** là kiểu mảng tham chiếu mà type pattern có thể kiểm tra trực tiếp; đối tượng **int[]** không phải **String[]**. Bản thân **int[]** vẫn là một kiểu tham chiếu của mảng, dù phần tử là primitive.

Ví dụ không sử dụng tính năng preview và không cần Java 21. Mỗi pattern biến chỉ được dùng sau khi đã khớp, phù hợp **flow scoping** của compiler Java 17.

## 7. Phân biệt lỗi lúc biên dịch với phép khớp thất bại lúc chạy

**Trường hợp A — hợp lệ nhưng chạy không khớp:**

~~~java
Object source = Integer.valueOf(7);
System.out.println(source instanceof String); // false
~~~

Compiler thấy kiểu nguồn **Object** đủ tổng quát để có thể là **String**, nên cho phép phép thử. Đối tượng thực tế là **Integer**, kết quả là **false**. Bản type pattern **source instanceof String text** cũng hợp lệ và không gắn **text** khi không khớp.

**Trường hợp B — từ chối khi biên dịch vì hai kiểu không thể gặp nhau:**

~~~java
String source = "Java";
// if (source instanceof Integer number) { ... } // Lỗi biên dịch
~~~

**String** và **Integer** đều là các class final không có quan hệ subtype tương thích. Compiler không cần chờ runtime để kết luận phép thử không có giá trị.

**Trường hợp C — từ chối vì type pattern quá tổng quát:**

~~~java
String source = "Java";
// if (source instanceof Object object) { ... } // Lỗi biên dịch
// if (source instanceof String text) { ... }  // Lỗi biên dịch
~~~

Đây là điểm khác biệt đáng chú ý của **type pattern** trong Java 17. Nếu chỉ muốn kiểm tra null, dùng **source != null**. Nếu cần biến kiểu rộng hơn, khai báo **Object object = source** hoặc **CharSequence text = source** thay vì một type pattern vô điều kiện.

**Trường hợp D — ép kiểu trực tiếp có thể ném ngoại lệ:**

~~~java
Object source = Integer.valueOf(7);
// String text = (String) source; // Biên dịch, nhưng ném ClassCastException khi chạy.
~~~

Một phép cast có thể hợp lệ về quan hệ kiểu tại compile time nhưng thất bại với đối tượng thực tế. Type pattern cho phép rẽ nhánh trước khi sử dụng biến đã đúng kiểu:

~~~java
Object source = Integer.valueOf(7);
if (source instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không phải String");
}
~~~

**Trường hợp E — null:** với **Object source = null**, cả **source instanceof String** và **source instanceof String text** đều cho ra **false**. Điều này không biến biểu thức thành không hợp lệ ở compile time; kiểu tĩnh vẫn có thể được thử với String.

## 8. Kiểu generic, type erasure và mảng

Trong Java 17, type pattern **instanceof** thường kiểm tra được một **raw/runtime-reifiable type**; không thể dựa vào kiểm tra này để xác nhận các đối số kiểu generic đã bị xóa.

~~~java
Object source = java.util.List.of("A", "B");

if (source instanceof java.util.List<?> values) {
    System.out.println(values.size());
}
~~~

Ví dụ hợp lệ: compiler biết **values** là một **List<?>** và gọi được **size()**. Nhưng các phần tử trong **values** được nhìn theo kiểu chưa xác định (khi đọc thường là **Object**); pattern không chứng minh tất cả đều là **String**.

Ví dụ không hợp lệ trên Java 17:

~~~java
Object source = java.util.List.of("A", "B");

// Không thể kiểm tra đối số kiểu String của List theo cách này:
// if (source instanceof java.util.List<String> values) { ... }
~~~

**List<String>** không phải kiểu runtime-reifiable thích hợp cho phép thử này; generic type arguments chịu **type erasure**. Nếu cần bảo đảm danh sách chứa các chuỗi, kiểm tra từng phần tử hoặc thiết kế API với kiểu tham số mạnh ngay từ đầu.

Với mảng, component type được giữ nhiều thông tin hơn tại runtime, nên **source instanceof String[] strings** là phép thử hợp lệ từ nguồn kiểu **Object**; còn **int[]** là một loại mảng khác. Đừng dùng sự hỗ trợ mảng để suy ra rằng Java 17 cũng có pattern trực tiếp cho primitive **int** hay kiểm tra được mọi generic type argument.

## 9. Các lỗi thường gặp khi chọn kiểu nguồn và kiểu đích

- **Nhìn giá trị mà quên kiểu khai báo:** **Object source = "abc"** và **String source = "abc"** có cùng đối tượng thực tế nhưng khác quy tắc hợp lệ đối với **source instanceof String text**. Trường hợp thứ nhất hợp lệ, trường hợp thứ hai bị từ chối trên Java 17.
- **Nghĩ instanceof giống phép chuyển đổi:** pattern **String text** không chuyển **Integer** thành chuỗi và không parse **"42"** thành số. Nó chỉ kiểm tra và gắn biến nếu đối tượng đã tương thích.
- **Dùng pattern khi biến đã có kiểu cần thiết:** từ **String** sang **CharSequence** có thể gán trực tiếp; không cần giới thiệu pattern chỉ để đổi kiểu tham chiếu.
- **Tưởng hai interface phải kế thừa nhau:** một class có thể triển khai hai interface độc lập. Tuy nhiên, nếu nguồn là một class final không triển khai target interface, phép thử có thể bị bác bỏ ngay lúc biên dịch.
- **Nhầm null với lỗi kiểu:** phép **instanceof** với null trả về **false**, không phải **ClassCastException**. Nếu nghiệp vụ cần phân biệt null với dữ liệu sai kiểu, hãy xử lý riêng.
- **Kiểm tra generic type arguments bằng instanceof:** **List<?>** thường hợp lệ; **List<String>** không thể được xác nhận trực tiếp từ **Object** bằng type pattern Java 17.
- **Dùng kiểu nguyên thủy ở vế trái:** Java 17 yêu cầu vế trái của **instanceof** có kiểu tham chiếu hoặc kiểu null. Nếu đầu vào là **int** và cần dùng như **Integer**, hãy cân nhắc boxing hoặc API có kiểu rõ ràng thay vì ép kiểm tra pattern.
- **Không phân biệt loại instanceof:** **value instanceof SomeType** là phép so sánh kiểu cổ điển; **value instanceof SomeType name** là phép khớp pattern và có thêm quy tắc về subtype vô điều kiện.
- **Sử dụng pattern variable ở nhánh sai:** biến pattern chỉ được sử dụng tại những nơi compiler chứng minh đã khớp. Kiểu nguồn/đích có thể hợp lệ nhưng chương trình vẫn không biên dịch nếu tham chiếu biến ở đường đi chưa khớp.

## 10. Cách lựa chọn và kiểm tra nhanh trong công việc

Trước khi viết một biểu thức **instanceof T variable**, hãy làm theo thứ tự:

1. Xác định **kiểu tĩnh S** của biểu thức bên trái từ khai báo và quy tắc kiểu của Java, đừng chỉ nhìn đối tượng đang được gán trong một ví dụ.
2. Xác định **kiểu pattern T** mong muốn. Với Java 17, đó phải là kiểu tham chiếu phù hợp để có thể kiểm tra tại runtime.
3. Hỏi **S có thể được kiểm tra/cast hợp lệ sang T không?** Nếu hai kiểu tách biệt chắc chắn (ví dụ hai class final không liên quan), biểu thức không hợp lệ.
4. Hỏi **S đã là subtype của T chưa?** Nếu có, Java 17 không cho dùng type pattern này trong **instanceof**. Gọi trực tiếp phương thức hoặc gán tham chiếu theo kiểu cần thiết.
5. Nếu biên dịch hợp lệ, nhớ rằng **runtime match** còn phụ thuộc đối tượng thực tế và **null** luôn không khớp.
6. Dùng biến pattern chỉ ở phạm vi được bảo đảm đã khớp; với dữ liệu generic và nội dung nghiệp vụ, bổ sung kiểm tra riêng.
7. Kiểm thử ít nhất một đối tượng khớp, một đối tượng không khớp và null; chạy **javac** với đúng phiên bản Java của dự án.

### Bài tập nhỏ tự kiểm tra

Xét đoạn mã dưới đây (Java 17):

~~~java
Object a = "text";
Number b = Integer.valueOf(3);
CharSequence c = new StringBuilder("x");
String d = "text";
~~~

Dự đoán:

- **a instanceof String s**: hợp lệ; runtime khớp.
- **b instanceof Integer i**: hợp lệ; runtime khớp.
- **c instanceof String t**: hợp lệ; runtime không khớp với **StringBuilder**.
- **d instanceof Object o**: lỗi biên dịch với type pattern trong Java 17 vì kiểu nguồn **String** đã là subtype của **Object**.
- **d instanceof Integer i**: lỗi biên dịch vì **String** và **Integer** không thể cùng là kiểu của một đối tượng.
- **d instanceof CharSequence**: hợp lệ vì đây là type comparison không khai báo pattern variable; với **d** khác null kết quả true.

Những dự đoán này giúp tách bạch ba vấn đề: **tương thích ở compile time**, **đúng kiểu ở runtime**, và **phạm vi/sự cần thiết của pattern variable**.

## Tài liệu đặc tả tham khảo

- [Java Language Specification 17, §14.30.1 — Kinds of Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1): định nghĩa type pattern và yêu cầu tương thích.
- [Java Language Specification 17, §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): phân biệt type comparison với pattern match, kiểm tra tương thích và null.
- [Java Language Specification 17, §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): quan hệ conversion có thể dùng trong kiểm tra tương thích.

**Kết luận:** với **instanceof type pattern** trong Java 17, kiểu nguồn và kiểu đích phải cho phép một phép kiểm tra kiểu có ý nghĩa: nguồn phải tương thích để có thể kiểm tra sang đích, đồng thời chưa là subtype của chính kiểu pattern. Sau khi compiler cho phép, kết quả khớp vẫn phụ thuộc đối tượng thực tế và điều kiện **khác null**. Hiểu rõ ba tầng này giúp chọn pattern đúng, dự đoán lỗi biên dịch và tránh nhầm lẫn giữa kiểm tra kiểu với ép kiểu.