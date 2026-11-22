# String.equals với null và đối tượng không phải String

Trong Java, **String.equals(Object)** kiểm tra xem đối số có phải một **String có cùng nội dung** với String ở phía gọi hay không. Hai tình huống dễ nhầm nhất là truyền **null** và truyền **một đối tượng thuộc kiểu khác String**:

- Một String không-null gọi **equals(null)** luôn trả về **false**, không ném ngoại lệ.
- Một String không-null gọi **equals(đối tượng không phải String)** luôn trả về **false**, ngay cả khi đối tượng đó có thể in ra văn bản giống hệt String.
- Nếu **biến ở phía trước dấu chấm là null**, lời gọi **biến.equals(...)** ném **NullPointerException** trước khi String.equals() có cơ hội thực thi.

Phân biệt **đối số null** với **đối tượng gọi phương thức null** là chìa khóa để đọc đúng kết quả và viết điều kiện so sánh an toàn.

## 1. Chữ ký và nguyên tắc so sánh

String cung cấp phương thức:

~~~java
public boolean equals(Object anObject)
~~~

Đây là **chữ ký API để minh họa**, không phải khai báo một phương thức mới mà người học cần thêm vào lớp. Phương thức nhận tham số kiểu Object, nhưng **String.equals() chỉ xét nội dung bằng nhau khi đối số thực sự là một đối tượng String**. Nó không tự đổi Integer, StringBuilder, char[] hoặc bất kỳ kiểu nào khác thành String để so sánh.

Với đối tượng String đang gọi phương thức:

1. Nếu hai tham chiếu cùng trỏ tới một String, kết quả là true.
2. Nếu đối số là một String khác đối tượng nhưng có cùng dãy đơn vị mã UTF-16, kết quả vẫn là true.
3. Nếu đối số là null, kết quả là false.
4. Nếu đối số không phải String, kết quả là false.
5. Nếu cả hai đều là String nhưng nội dung khác nhau, kết quả là false.

**equals() so sánh giá trị nội dung; toán tử == so sánh danh tính tham chiếu** khi cả hai toán hạng là kiểu tham chiếu. Đây là hai phép kiểm tra khác nhau.

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

Hai lệnh new tạo hai đối tượng String khác nhau, nên == là false. Nội dung "Java" bằng nhau nên equals() là true.

## 2. Truyền null cho String.equals(): kết quả false

Ví dụ:

~~~java
String language = "Java";
String missing = null;

System.out.println(language.equals(null));    // false
System.out.println(language.equals(missing)); // false
System.out.println("Java".equals(null));      // false
~~~

**Vì sao không ném NullPointerException?** Đối tượng ở phía gọi (language hoặc literal "Java") tồn tại. Java thực thi String.equals(), và phương thức xác định null không phải đối tượng String có nội dung bằng nó.

So sánh với cách gọi ngược lại:

~~~java
String missing = null;
System.out.println(missing.equals("Java")); // Ném NullPointerException
~~~

Đoạn trên là **minh họa lỗi**, không phải đoạn cần chạy chung với những ví dụ đang in kết quả phía trước. Phép truy cập phương thức qua biến missing không có đối tượng nhận vì missing bằng null. Đây là lỗi ở **receiver** (đối tượng nhận lời gọi), không phải do equals() “không nhận null”.

Có thể ghi nhớ:

| Biểu thức | Kết quả | Nguyên nhân |
|---|---|---|
| "Java".equals(null) | false | Receiver là String hợp lệ; đối số null |
| "Java".equals("Java") | true | Nội dung bằng nhau |
| "Java".equals("java") | false | Phân biệt chữ hoa/chữ thường |
| ((String) null).equals("Java") | NullPointerException | Receiver là null |
| null == null | true | == cho phép so sánh hai tham chiếu null |
| "Java" == null | false | Tham chiếu String không-null |

**Không dùng trực tiếp null.equals(...):** từ khóa null không phải biểu thức nhận lời gọi phương thức hợp lệ; trường hợp chạy thực tế là một biến tham chiếu có giá trị null, như missing.equals(...).

## 3. Truyền đối tượng khác String: luôn false

Vì chữ ký nhận Object, trình biên dịch cho phép truyền nhiều loại tham số. Nhưng String.equals() **không ép kiểu ngầm thành String**, không gọi toString() rồi so sánh, và không so sánh “hai đối tượng hiển thị giống nhau” nếu đối tượng kia không phải String.

Ví dụ:

~~~java
String text = "42";
Integer number = 42;

System.out.println(text.equals(number)); // false
~~~

Mặc dù number.toString() tạo ra "42", number là Integer nên text.equals(number) là false.

Tương tự:

~~~java
String text = "Java";
StringBuilder builder = new StringBuilder("Java");

System.out.println(text.equals(builder));            // false
System.out.println(text.equals(builder.toString())); // true
~~~

StringBuilder có nội dung hiển thị "Java" nhưng **không phải String**. toString() tạo String mới, lúc đó String.equals() mới so sánh được nội dung.

### Bảng những kiểu đối số khác nhau

Giả sử receiver luôn là **"Java"**:

| Đối số | Loại đối số ở runtime | Kết quả equals() |
|---|---|---|
| "Java" | String | true |
| new String("Java") | String | true |
| "java" | String | false |
| null | null | false |
| new StringBuilder("Java") | StringBuilder | false |
| new StringBuffer("Java") | StringBuffer | false |
| new char[] {'J', 'a', 'v', 'a'} | char[] | false |
| Integer.valueOf(123) | Integer | false |
| new Object() | Object | false |

Nếu cần **cố ý** so sánh nội dung String với một CharSequence khác, có thể cân nhắc **String.contentEquals(CharSequence)**. Chẳng hạn:

~~~java
String text = "Java";
StringBuilder builder = new StringBuilder("Java");

System.out.println(text.equals(builder));        // false
System.out.println(text.contentEquals(builder)); // true
~~~

Hai phương thức trả về khác nhau vì **hợp đồng so sánh khác nhau**: equals() chỉ chấp nhận String có cùng nội dung, còn contentEquals() được thiết kế để so sánh nội dung với CharSequence. Không nên tự thay equals() bằng contentEquals() ở mọi nơi, vì ý nghĩa yêu cầu so sánh kiểu dữ liệu có thể khác.

## 4. Kiểu khai báo Object không quyết định kết quả: kiểu thực tế mới quan trọng

Một biến khai báo kiểu **Object** vẫn có thể trỏ tới String. Trong trường hợp đó, khi truyền nó cho String.equals(), phương thức xét **đối tượng thực tại runtime**, không chỉ nhìn kiểu khai báo.

~~~java
String expected = "Java";

Object stringValue = new String("Java");
Object builderValue = new StringBuilder("Java");
Object nullValue = null;

System.out.println(expected.equals(stringValue));  // true
System.out.println(expected.equals(builderValue)); // false
System.out.println(expected.equals(nullValue));    // false
~~~

Ở dòng thứ nhất, stringValue có kiểu biến Object nhưng giá trị thực là String chứa "Java", nên kết quả true. Dòng thứ hai tham chiếu StringBuilder, nên false. Dòng cuối là null, cũng false.

**Không được suy diễn rằng tham số Object đồng nghĩa các kiểu đều được đổi sang String.** Object là kiểu tham số rộng; logic cụ thể của String.equals() mới quyết định thế nào là bằng nhau.

## 5. Khi receiver có thể `null`: chọn cách gọi phù hợp

Nếu cần kiểm tra một trạng thái cố định, hãy gọi `equals()` trên literal. Nếu muốn gọi trên biến, dùng `&&` để bảo đảm biến khác `null` trước khi gọi:

~~~java
String status = null;
System.out.println("ACTIVE".equals(status)); // false
System.out.println(status != null && status.equals("ACTIVE")); // false
~~~

Với **hai** tham chiếu đều có thể `null`, `Objects.equals(left, right)` trả `true` nếu cùng `null`, trả `false` nếu chỉ một bên `null`, còn khi `left` khác `null` thì dùng `left.equals(right)`. Nếu hai giá trị chưa được cung cấp không được coi là bằng nhau trong nghiệp vụ, phải kiểm tra tính hiện diện riêng.

Bài kế tiếp giải thích đầy đủ `Objects.equals` qua String, mảng và các lớp tự định nghĩa. Ở đây, khác biệt cần nhớ là **đối số `null`** so với **receiver `null`** của chính `String.equals(Object)`.

## 6. Chương trình Java 17+ chạy độc lập

Chương trình dưới đây tổng hợp cả null, đối số không phải String, biến khai báo Object, Objects.equals() và các mẫu so sánh an toàn.

Lưu thành file **StringEqualsNullAndTypeDemo.java**:

~~~java
import java.util.Objects;

public class StringEqualsNullAndTypeDemo {
    public static void main(String[] args) {
        String value = "Java";
        String missing = null;

        Object stringAsObject = new String("Java");
        Object builder = new StringBuilder("Java");
        Object number = Integer.valueOf(42);

        System.out.println("literal-null=" + "Java".equals(null));
        System.out.println("value-null=" + value.equals(missing));
        System.out.println("safe-constant=" + "Java".equals(missing));

        System.out.println("object-string=" + value.equals(stringAsObject));
        System.out.println("object-builder=" + value.equals(builder));
        System.out.println("object-number=" + "42".equals(number));

        System.out.println("builder-content="
                + value.contentEquals((StringBuilder) builder));
        System.out.println("builder-string="
                + value.equals(builder.toString()));

        System.out.println("objects-null-null="
                + Objects.equals(missing, null));
        System.out.println("objects-null-value="
                + Objects.equals(missing, value));
        System.out.println("objects-value-value="
                + Objects.equals(value, stringAsObject));

        System.out.println("different-case=" + value.equals("java"));
        System.out.println("equal-new-instance="
                + value.equals(new String("Java")));

        try {
            System.out.println(missing.equals(value));
        } catch (NullPointerException exception) {
            System.out.println("null-receiver=NullPointerException");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac StringEqualsNullAndTypeDemo.java
java StringEqualsNullAndTypeDemo
~~~

Đầu ra:

~~~text
literal-null=false
value-null=false
safe-constant=false
object-string=true
object-builder=false
object-number=false
builder-content=true
builder-string=true
objects-null-null=true
objects-null-value=false
objects-value-value=true
different-case=false
equal-new-instance=true
null-receiver=NullPointerException
~~~

Những chi tiết cần quan sát:

1. **Ba dòng đầu** đều false vì receiver là String thực, còn đối số null.
2. **object-string=true** chứng minh Object có thể đang tham chiếu một String thật.
3. **object-builder=false** và **object-number=false** chứng minh String.equals() không chuyển kiểu đối số.
4. **builder-content=true** và **builder-string=true** dùng các phương thức có ngữ nghĩa so sánh khác, nên có thể kiểm tra cùng nội dung theo chủ đích.
5. **objects-null-null=true** thể hiện khác biệt giữa Objects.equals() và String.equals(null).
6. **different-case=false** cho thấy equals() phân biệt chữ hoa/thường.
7. **null-receiver=NullPointerException** là kết quả của khối catch: lời gọi trên missing thật sự gây ngoại lệ và được bắt để chương trình tiếp tục.

## 7. Ứng dụng thực tế: kiểm tra dữ liệu đầu vào, trạng thái và giá trị nullable

### Kiểm tra một trạng thái có thể bị thiếu

Ví dụ một phương thức nhận trạng thái từ một API:

~~~java
static boolean isReady(String status) {
    return "READY".equals(status);
}
~~~

Đây là **phương thức minh họa**, cần đặt bên trong một lớp Java khi sử dụng. Nó trả về true chỉ khi status là String bằng chính xác "READY"; với null, "ready", hoặc "" đều trả về false.

Cách viết này tự nhiên khi ứng dụng muốn kiểm tra **một hằng giá trị duy nhất** và thiếu dữ liệu được coi là không khớp.

### Khi hai giá trị vắng mặt cũng được coi là bằng nhau

Giả sử trước và sau của một trường nullable đều không có dữ liệu. Để phát hiện thay đổi giữa hai String nullable:

~~~java
static boolean hasChanged(String oldValue, String newValue) {
    return !java.util.Objects.equals(oldValue, newValue);
}
~~~

Khi oldValue và newValue đều null, kết quả false (không có thay đổi). Khi một bên null và bên kia có giá trị, kết quả true. Khi hai String cùng nội dung, kết quả false.

**Cần lựa chọn chủ ý:** trong một số nghiệp vụ, “không có dữ liệu” không đồng nghĩa “bằng nhau”; khi đó đừng máy móc dùng Objects.equals() mà không làm rõ quy tắc so sánh.

### Khi giá trị đến dưới dạng Object

Trong xử lý Object hoặc dữ liệu nhiều loại, đừng nhầm toString() với kiểm tra kiểu:

~~~java
static boolean isJavaString(Object candidate) {
    return "Java".equals(candidate);
}
~~~

Hàm trả về true nếu candidate thực sự là String có nội dung "Java", không chấp nhận StringBuilder hiển thị "Java" hoặc đối tượng khác chỉ vì toString() cho cùng văn bản.

Nếu nghiệp vụ **thật sự cho phép nhiều kiểu** và muốn chuẩn hóa thành String, phải thiết kế quy tắc chuyển đổi riêng và cân nhắc null, định dạng số, locale cùng các trường hợp không hợp lệ. String.equals(Object) tự nó không có trách nhiệm thực hiện chuẩn hóa đó.

## 8. Những ngộ nhận và lỗi phổ biến

### Nhầm 1: equals(null) chắc chắn ném NullPointerException

Sai. **"Java".equals(null)** trả về false. **nullable.equals("Java")** chỉ ném NullPointerException khi nullable thực sự null. Vị trí của null trong lời gọi rất quan trọng.

### Nhầm 2: Vì tham số khai báo Object, equals() sẽ so sánh với mọi kiểu

Sai. Chữ ký **Object** cho phép truyền tham số vào phương thức; nó không có nghĩa phương thức sẽ chuyển tham số thành String. "42".equals(42) trả về false (đối số int được boxing thành Integer); "42".equals(Integer.valueOf(42)) cũng false.

### Nhầm 3: Hai đối tượng có toString() giống nhau thì equals() phải true

Sai. toString() chủ yếu cung cấp biểu diễn văn bản; hợp đồng equals() của từng lớp mới quyết định tính bằng nhau. String.equals() không gọi toString() của đối số để so sánh.

### Nhầm 4: Dùng == thay equals() cho String

Sai nếu mục tiêu là so sánh **nội dung**. == chỉ so sánh tham chiếu. String literal có thể được intern nên đôi lúc == có vẻ đúng, nhưng không thể dùng kết quả tình cờ đó làm quy tắc nghiệp vụ.

### Nhầm 5: Objects.equals(null, null) phải false vì String.equals(null) false

Sai. Hai API có hợp đồng khác nhau. Objects.equals(null, null) là true; trong trường hợp này **không có đối tượng String nào nhận lời gọi equals()**.

### Nhầm 6: null, chuỗi rỗng và chuỗi toàn khoảng trắng đều như nhau

Sai. null nghĩa là không có tham chiếu; "" là một String hợp lệ độ dài 0; " " là String chứa một dấu cách. Ví dụ "".equals(null) là false, "".equals("") là true, và "".equals(" ") là false. Nếu nghiệp vụ muốn coi các giá trị đó tương đương, cần quy tắc xử lý dữ liệu khác trước khi so sánh.

### Nhầm 7: equals() tự bỏ qua chữ hoa/thường hoặc chuẩn hóa Unicode

Sai. String.equals() so sánh đúng dãy đơn vị mã UTF-16, phân biệt "Java" với "java". Nếu cần bỏ qua một phần khác biệt chữ hoa/thường, có String.equalsIgnoreCase(String), nhưng phương thức này **không phải** phép đối chiếu chuỗi theo tất cả quy tắc locale hay chuẩn hóa Unicode. Chuẩn hóa theo nghiệp vụ phải được quyết định rõ ràng.

### Nhầm 8: Dùng ép kiểu String cho đối tượng bất kỳ sẽ giải quyết vấn đề

Sai. Nếu candidate trỏ tới StringBuilder, lệnh (String) candidate gây ClassCastException. Kiểm tra kiểu bằng instanceof trước khi cast, hoặc chuyển đổi chỉ khi ứng dụng thực sự muốn chấp nhận loại dữ liệu đó.

~~~java
Object candidate = new StringBuilder("Java");

if (candidate instanceof String text) {
    System.out.println("Java".equals(text));
} else {
    System.out.println("Not a String");
}
~~~

Đây là **đoạn minh họa** với pattern matching instanceof được Java 17 hỗ trợ. Kết quả là **Not a String**; không có cast sai kiểu.

## 9. Tóm tắt theo trường hợp và tự kiểm tra

| Cần xác định | Câu trả lời |
|---|---|
| String không-null gọi equals(null)? | false |
| String không-null gọi equals(StringBuilder cùng nội dung)? | false |
| String không-null gọi equals(Object trỏ tới String cùng nội dung)? | true |
| Biến String null gọi equals("abc")? | NullPointerException |
| Cả hai String nullable đều null, dùng Objects.equals()? | true |
| StringBuilder muốn so sánh nội dung với String? | Chủ động chuyển bằng toString() hoặc dùng contentEquals() theo yêu cầu |
| Muốn kiểm tra với hằng "OK" và biến nullable? | "OK".equals(value) |
| Muốn so sánh hai String nullable theo quy tắc null/null là bằng nhau? | Objects.equals(a, b) |

**Tự trả lời:**

1. Vì sao "123".equals(123) là false dù hai phía có biểu diễn văn bản giống nhau?
2. Vì sao Object x = "Java"; thì "Java".equals(x) là true, nhưng Object y = new StringBuilder("Java"); lại false?
3. Sự khác nhau giữa "Java".equals(nullable) và nullable.equals("Java") là gì khi nullable null?
4. Tại sao Objects.equals(null, null) trả về true trong khi "Java".equals(null) trả về false?
5. Nếu một trường trạng thái có thể null, bạn sẽ chọn "READY".equals(status) hay status.equals("READY"), và vì sao?

**Đáp án cốt lõi:** (1) String.equals() yêu cầu đối số thực tế là String, số nguyên không phải String. (2) Kiểu đối tượng runtime quyết định, không phải kiểu biến Object hay chữ hiển thị. (3) Receiver non-null trả false, receiver null gây ngoại lệ. (4) Objects.equals() xử lý hai tham chiếu null theo hợp đồng riêng. (5) Đặt literal bên trái để kiểm tra an toàn.

**Ghi nhớ:** **Đối số null → false; đối số không phải String → false; receiver null → NullPointerException.** Dùng String literal ở bên trái khi so sánh với hằng, hoặc dùng Objects.equals() cho hai String có thể null nếu quy tắc **null bằng null** là phù hợp.
