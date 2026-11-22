# Objects.equals cho hai tham chiếu có thể null trong Java

## 1. Vấn đề: so sánh khi một hoặc cả hai tham chiếu có thể là null

Trong Java, **String** là kiểu tham chiếu. Hai biến có thể chứa hai đối tượng String, cùng tham chiếu đến một đối tượng, hoặc chứa **null** (không tham chiếu đến đối tượng nào). Khi dùng **a.equals(b)**, Java phải gọi phương thức trên đối tượng **a**; nếu **a == null**, lệnh này ném **NullPointerException**.

~~~java
String first = null;
String second = "Java";

// Đoạn minh họa lỗi nếu chạy:
boolean equal = first.equals(second); // NullPointerException
~~~

Lớp **java.util.Objects** cung cấp phương thức tĩnh:

~~~java
boolean result = Objects.equals(first, second);
~~~

Phương thức này **so sánh hai tham chiếu an toàn khi có null**. Nó trả về **true** nếu cả hai là null hoặc nếu giá trị thứ nhất khác null và phương thức **equals** của nó đánh giá hai giá trị là bằng nhau. Nếu chỉ một tham chiếu là null, kết quả **false**.

**Objects.equals** hữu ích cho String, các đối tượng giá trị, thuộc tính của đối tượng và các phương thức nhận tham số tùy chọn có thể null. Cần **import java.util.Objects**; đây là API có từ Java 7 và hoàn toàn dùng được trong Java 17+.

## 2. Hợp đồng chính xác của Objects.equals

Chữ ký:

~~~java
public static boolean equals(Object a, Object b)
~~~

Hành vi về cơ bản tương đương:

~~~java
public static boolean nullableEquals(Object a, Object b) {
    return (a == b) || (a != null && a.equals(b));
}
~~~

Đoạn trên là **phương thức minh họa**, đặt trong một lớp nếu muốn biên dịch. Thư viện Java sẽ tự chọn phương thức **equals** phù hợp với kiểu thực tế của đối tượng **a**, nhờ cơ chế gọi phương thức động.

| Tham chiếu a | Tham chiếu b | Kết quả | Giải thích |
| --- | --- | --- | --- |
| **null** | **null** | **true** | Cùng là null; nhánh **a == b** đúng |
| **null** | Đối tượng | **false** | **a != null** sai, không gọi phương thức |
| Đối tượng | **null** | Thường **false** với equals đúng hợp đồng | Gọi **a.equals(null)**; hợp đồng equals yêu cầu trả về false |
| Cùng một đối tượng | Cùng tham chiếu | **true** | **a == b** đúng |
| Hai đối tượng khác tham chiếu | Giá trị tương đương theo **a.equals(b)** | **true** | Chẳng hạn hai String có cùng nội dung |
| Hai đối tượng khác tham chiếu | Giá trị không tương đương | **false** | Kết quả dựa trên **a.equals(b)** |

**Lưu ý về điều kiện:** một triển khai **equals** bị viết sai có thể vi phạm hợp đồng của Java, ném ngoại lệ hoặc trả về kết quả không nhất quán. **Objects.equals** chỉ xử lý trường hợp null ở bên ngoài và chuyển tiếp tới **equals** thông thường; nó không sửa các lỗi nghiệp vụ hay tự kiểm chứng sự đối xứng của một phép so sánh.

### Vì sao hai null lại được xem là bằng nhau?

Đây là quy tắc đã được định nghĩa cho phép so sánh giá trị trong **Objects.equals**: hai tham chiếu đều không có đối tượng được xem là tương đương. Quy tắc này thường phù hợp khi kiểm tra “hai trạng thái có giống nhau không”.

Tuy nhiên, **hai trường dữ liệu đều thiếu** không luôn có nghĩa “hai thực thể giống nhau” trong nghiệp vụ. Khi so mã định danh bắt buộc khác null, hãy kiểm tra tính hợp lệ của mã định danh trước khi gọi **Objects.equals**, hoặc yêu cầu cả hai phải khác null:

~~~java
boolean sameKnownId = idA != null && idB != null
        && idA.equals(idB);
~~~

Đây là **đoạn minh họa** trong một phương thức; nó trả về false nếu mã định danh của một trong hai phía không tồn tại. Không nên dùng **Objects.equals(null, null) == true** như bằng chứng rằng hai thực thể không có ID là cùng một thực thể.

## 3. Ví dụ đầy đủ: hai String có thể null

Lưu mã vào **NullableStringComparisonDemo.java**:

~~~java
import java.util.Objects;

public class NullableStringComparisonDemo {
    public static void main(String[] args) {
        String missingA = null;
        String missingB = null;
        String literal = "Java";
        String newObject = new String("Java");
        String other = "Kotlin";

        System.out.println(Objects.equals(missingA, missingB));
        System.out.println(Objects.equals(missingA, literal));
        System.out.println(Objects.equals(literal, missingA));
        System.out.println(Objects.equals(literal, newObject));
        System.out.println(literal == newObject);
        System.out.println(Objects.equals(literal, other));
        System.out.println("Java".equals(missingA));
        System.out.println(Objects.equals("", missingA));
        System.out.println(Objects.equals("", ""));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 NullableStringComparisonDemo.java
java NullableStringComparisonDemo
~~~

Stdout:

~~~text
true
false
false
true
false
false
false
false
true
~~~

Giải thích theo thứ tự:

1. Cả hai giá trị **missingA** và **missingB** đều là **null**, kết quả **true**.
2. So **null** với **"Java"** hoặc ngược lại đều cho **false**.
3. **literal** và **newObject** chứa nội dung **"Java"** giống nhau nên **Objects.equals** trả về **true**, dù là hai đối tượng khác nhau.
4. **literal == newObject** là **false** vì **==** kiểm tra tham chiếu.
5. Hai nội dung **"Java"** và **"Kotlin"** không giống nhau.
6. **"Java".equals(missingA)** không gây ngoại lệ, vì đối tượng nhận phương thức là literal chắc chắn khác null; kết quả **false**.
7. **""** là String rỗng thực sự, khác **null**, nhưng hai chuỗi rỗng có nội dung bằng nhau.

Đối với hai String, kết quả **Objects.equals(a, b)** vẫn phân biệt chữ hoa/thường. Ví dụ **Objects.equals("java", "Java")** là **false**.

## 4. Phân biệt Objects.equals, equals và ==

| Biểu thức | Mục đích | Khi a null | Kết luận |
| --- | --- | --- | --- |
| **a == b** | So tham chiếu (với kiểu tham chiếu) | An toàn | Cho biết hai biến có trỏ cùng đối tượng hoặc cùng null hay không |
| **a.equals(b)** | Gọi phép so sánh do lớp của a định nghĩa | Ném **NullPointerException** | Dùng khi biết a không null |
| **Objects.equals(a, b)** | So giá trị có xử lý null | An toàn | Phù hợp khi cả hai tham chiếu đều có thể null |
| **"value".equals(a)** | So nội dung với một giá trị cố định | An toàn | Gọn và rõ khi một vế là hằng String khác null |
| **Objects.requireNonNull(a)** | Xác thực a bắt buộc khác null | Ném **NullPointerException** | Không phải phép so sánh; dùng để thực thi điều kiện đầu vào |

Phép **==** đặc biệt dễ gây nhầm với String:

~~~java
String a = "hello";
String b = new String("hello");

System.out.println(a == b);               // false
System.out.println(a.equals(b));           // true
System.out.println(Objects.equals(a, b));  // true
~~~

Đây là các câu lệnh minh họa đặt trong phương thức có **import java.util.Objects**. Việc một số literal String được JVM tái sử dụng trong **string pool** có thể khiến **==** đôi khi trả về true với hai literal, nhưng không nên dựa vào hiện tượng đó để kiểm tra văn bản. Chọn **equals** hoặc **Objects.equals** để diễn đạt rõ ý định so nội dung.

### Khi nào ưu tiên từng cách?

- Nếu **a** đã được bảo đảm khác null theo hợp đồng, dùng **a.equals(b)** là tự nhiên.
- Nếu **cả hai biến có thể null**, dùng **Objects.equals(a, b)**.
- Nếu so với một hằng String chắc chắn khác null, **"ACTIVE".equals(status)** là lựa chọn ngắn gọn.
- Nếu chỉ muốn kiểm tra chính xác **cùng đối tượng**, dùng **==**.
- Nếu nghiệp vụ quy định không được chấp nhận null, kiểm tra và báo lỗi trước; đừng để **Objects.equals(null, null)** vô tình được coi là trường hợp hợp lệ.

## 5. Những chi tiết về null cần làm rõ

**null khác chuỗi rỗng và chuỗi chỉ chứa khoảng trắng.**

~~~java
String absent = null;
String empty = "";
String spaces = "   ";

System.out.println(Objects.equals(absent, empty)); // false
System.out.println(Objects.equals(empty, spaces)); // false
System.out.println(empty.isEmpty());               // true
System.out.println(spaces.isBlank());              // true
~~~

Các câu lệnh minh họa trong phương thức có import **Objects**. Phương thức **isEmpty()** chỉ kiểm tra độ dài bằng 0; **isBlank()** kiểm tra toàn bộ chuỗi là whitespace theo quy tắc của Java. Việc xem **null**, chuỗi rỗng hoặc chuỗi trắng như nhau phải là **quyết định nghiệp vụ được viết tường minh**, ví dụ bước chuẩn hóa đầu vào trước khi so sánh.

**Không có phép “coi null là chuỗi "null"”** trong **Objects.equals**. Ví dụ:

~~~java
System.out.println(Objects.equals(null, "null")); // false
~~~

Phương thức **String.valueOf((Object) null)** lại tạo ra String có nội dung bốn chữ cái **"null"**; không nên dùng cách này để thay thế phép so sánh null-safe.

**Thứ tự tham số trong một phép equals chuẩn:** hợp đồng **Object.equals** yêu cầu tính đối xứng: **a.equals(b)** và **b.equals(a)** phải tương đương về giá trị logic khi cả hai khác null. Nếu một lớp triển khai equals sai, **Objects.equals(a, b)** và **Objects.equals(b, a)** có thể khác nhau. Phương thức tĩnh không tự thử cả hai hướng để sửa lỗi.

## 6. Objects.equals với các loại đối tượng khác

**Objects.equals** có tên tổng quát vì nhận hai tham số kiểu **Object**. Kết quả khi cả hai khác null phụ thuộc vào **equals** của loại đối tượng đứng bên trái.

### String và các lớp giá trị phổ biến

**String**, các lớp wrapper như **Integer**, **Long**, **Boolean**, cùng nhiều lớp giá trị Java khác có định nghĩa **equals** dựa trên dữ liệu có ý nghĩa. Tuy nhiên, một số loại còn yêu cầu **đúng kiểu**:

~~~java
Object number = Integer.valueOf(10);
Object longNumber = Long.valueOf(10L);

System.out.println(Objects.equals(number, longNumber)); // false
~~~

Giá trị số đều biểu diễn “10”, nhưng hai wrapper khác lớp nên **Integer.equals(Long)** trả về false. **Objects.equals** không tự chuyển đổi kiểu số, không bỏ qua khác biệt locale và cũng không tự chuyển chữ hoa/thường.

### Đối tượng không ghi đè equals

Nếu một lớp chỉ kế thừa **Object.equals** mặc định, phép so sánh về cơ bản dựa trên **cùng đối tượng**. Hai đối tượng mới có cùng dữ liệu trường chưa chắc bằng nhau:

~~~java
class Box {
    int value;
    Box(int value) {
        this.value = value;
    }
}

// Các câu lệnh sau ở bên trong một phương thức:
Box first = new Box(7);
Box second = new Box(7);
System.out.println(Objects.equals(first, second)); // false
~~~

Nếu muốn coi hai **Box** có cùng **value** là tương đương, lớp phải định nghĩa **equals** (và **hashCode**) phù hợp. **Objects.equals** không tự dùng reflection để so tất cả thuộc tính.

### Array không được so nội dung sâu bằng Objects.equals

Mảng Java không ghi đè **Object.equals** để so các phần tử. Vì vậy:

~~~java
String[] first = {"a", "b"};
String[] second = {"a", "b"};

System.out.println(Objects.equals(first, second)); // false
System.out.println(java.util.Arrays.equals(first, second)); // true
System.out.println(Objects.deepEquals(first, second)); // true
~~~

Đây là đoạn minh họa; cần import **java.util.Objects** nếu dùng tên ngắn. Dùng **Arrays.equals** cho mảng một chiều và **Arrays.deepEquals** hoặc **Objects.deepEquals** trong trường hợp cần so các mảng lồng nhau phù hợp. **Objects.deepEquals** cũng xử lý null, nhưng cần tránh lạm dụng với đồ thị mảng có tham chiếu vòng.

Để minh họa đầy đủ, lưu thành **ArrayEqualityDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class ArrayEqualityDemo {
    public static void main(String[] args) {
        String[] one = {"a", "b"};
        String[] two = {"a", "b"};

        System.out.println(Objects.equals(one, two));
        System.out.println(Arrays.equals(one, two));
        System.out.println(Objects.deepEquals(one, two));

        int[][] left = {{1, 2}, {3}};
        int[][] right = {{1, 2}, {3}};

        System.out.println(Arrays.equals(left, right));
        System.out.println(Arrays.deepEquals(left, right));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArrayEqualityDemo.java
java ArrayEqualityDemo
~~~

~~~text
false
true
true
false
true
~~~

**Vì sao?** Mảng **one** và **two** là hai đối tượng khác nhau, nhưng phần tử tương ứng có cùng nội dung. Với **int[][]**, phép **Arrays.equals** ở tầng ngoài lại so các mảng con theo tham chiếu; **Arrays.deepEquals** mới đệ quy so nội dung các mảng con.

## 7. Viết equals null-safe trong lớp của chính bạn

Trong lớp giá trị do ứng dụng định nghĩa, có thể dùng **Objects.equals** để so các trường tham chiếu có thể null. Cần ghi đè **hashCode** tương thích nếu ghi đè **equals**.

Ví dụ đầy đủ, lưu thành **CustomerEqualityDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class Customer {
    private final String email;
    private final int level;

    Customer(String email, int level) {
        this.email = email;
        this.level = level;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Customer that)) {
            return false;
        }

        return level == that.level
                && Objects.equals(email, that.email);
    }

    @Override
    public int hashCode() {
        return Objects.hash(email, level);
    }
}

public class CustomerEqualityDemo {
    public static void main(String[] args) {
        Customer first = new Customer(null, 2);
        Customer second = new Customer(null, 2);
        Customer other = new Customer(null, 3);

        System.out.println(first == second);
        System.out.println(Objects.equals(first, second));
        System.out.println(Objects.equals(first, other));
        System.out.println(Objects.equals(first, null));

        Set<Customer> customers = new HashSet<>();
        customers.add(first);
        System.out.println(customers.contains(second));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CustomerEqualityDemo.java
java CustomerEqualityDemo
~~~

~~~text
false
true
false
false
true
~~~

Đây là ví dụ Java 17+ dùng cú pháp **instanceof Customer that**, được Java 16 chuẩn hóa. Hai đối tượng **Customer** có cùng **level** và cùng **email == null** được coi là bằng nhau theo chính sách của lớp. **HashSet.contains(second)** hoạt động đúng vì **equals** và **hashCode** tương thích.

**Cảnh báo về thiết kế:** trong ví dụ, các trường là **final** để dễ bảo đảm bất biến. Nếu các trường tham gia **equals/hashCode** bị thay đổi sau khi đối tượng đã vào **HashSet** hoặc làm key của **HashMap**, việc tìm kiếm có thể thất bại. Với mã định danh bắt buộc có giá trị, hãy kiểm tra tính hợp lệ ở constructor thay vì cho phép null một cách vô điều kiện.

**Objects.hash(email, level)** tính hash tổng hợp của các trường. Không nhầm với **Objects.hashCode(value)**, tiện ích trả về 0 nếu value null hoặc **value.hashCode()** nếu khác null. Cả hai hỗ trợ việc xây dựng hashCode; lựa chọn phải tương thích với những trường được **equals** sử dụng.

### Record trong Java 17

Một **record** tự tạo **equals/hashCode** dựa trên các thành phần của nó:

~~~java
record Profile(String displayName, int age) {}

Profile a = new Profile(null, 20);
Profile b = new Profile(null, 20);
System.out.println(Objects.equals(a, b)); // true
~~~

Đây là đoạn minh họa trong ngữ cảnh phù hợp với Java 17 và có import **Objects**. **Record** có phép so sánh thành phần theo hợp đồng của Java; tuy vậy, với thành phần kiểu array, không mặc nhiên hiểu rằng record sẽ so sâu nội dung của mảng. Vẫn cần thiết kế rõ semantics của lớp.

## 8. Trường hợp ứng dụng thực tế

### 8.1. Kiểm tra giá trị cũ/mới để quyết định có cập nhật

Khi trạng thái cũ và mới đều có thể null, muốn phát hiện thay đổi:

~~~java
if (!Objects.equals(oldValue, newValue)) {
    System.out.println("Value changed");
}
~~~

Dùng **!Objects.equals** giúp xử lý các chuyển trạng thái **null → giá trị**, **giá trị → null**, hoặc **giá trị A → giá trị B** một cách nhất quán. Hai giá trị đều null được xem là không thay đổi.

### 8.2. So khớp tham số bộ lọc có thể null

~~~java
boolean matches = Objects.equals(requestedCategory, itemCategory);
~~~

Biểu thức này có nghĩa **cả hai cùng null cũng là match**. Nếu null trong bộ lọc nghĩa là **“không lọc”**, cần một điều kiện khác:

~~~java
boolean matches = requestedCategory == null
        || Objects.equals(requestedCategory, itemCategory);
~~~

Hai đoạn trên là minh họa trong một phương thức. Chúng thể hiện hai chính sách nghiệp vụ khác nhau; nên chọn dựa trên định nghĩa của API.

### 8.3. So với một trạng thái cố định

~~~java
boolean active = "ACTIVE".equals(status);
~~~

Khi **status** có thể null, gọi **equals** trên literal vẫn an toàn và ngắn. **Objects.equals(status, "ACTIVE")** cũng đúng, nhưng không mang thêm lợi ích đáng kể trong trường hợp một vế đã chắc chắn khác null.

### 8.4. Hai tham chiếu nullable cần so không phân biệt hoa/thường

**Objects.equals** không tự thực hiện so sánh bỏ qua chữ hoa/thường. Nếu ứng dụng xác định rõ chính sách **equalsIgnoreCase** cho hai String có thể null:

~~~java
static boolean equalsIgnoreCaseNullable(String a, String b) {
    return a == b || (a != null && a.equalsIgnoreCase(b));
}
~~~

Đây là phương thức minh họa: hai null trả về true, một null trả về false, còn hai String khác null được so không phân biệt hoa/thường theo **String.equalsIgnoreCase**. Nó không tự chuẩn hóa Unicode, không giải quyết đầy đủ so sánh ngôn ngữ tự nhiên theo locale. Nếu yêu cầu là sắp xếp/tìm kiếm tiếng Việt, cần quy tắc normalization, locale và collation tách biệt.

## 9. Khi nào Objects.equals chưa đủ?

- **Yêu cầu bắt buộc có dữ liệu:** nếu cả hai null vẫn là trạng thái không hợp lệ, dùng điều kiện kiểm tra tính tồn tại hoặc **Objects.requireNonNull** trước khi so.
- **Mảng:** dùng phương thức của **Arrays** phù hợp với kiểu mảng và nhu cầu so từng tầng.
- **So sánh không phân biệt chữ hoa/thường:** dùng **equalsIgnoreCase** hoặc quy tắc so sánh ngôn ngữ phù hợp; **Objects.equals** phân biệt nội dung chính xác theo **equals**.
- **Unicode normalization:** hai String có hình thức hiển thị giống nhau nhưng khác NFC/NFD vẫn có thể không **equals**. Chuẩn hóa có chủ đích trước khi so nếu nghiệp vụ cần.
- **So sánh dữ liệu số khác kiểu:** **Integer(10)** và **Long(10L)** không tự quy về cùng kiểu.
- **Đối tượng nghiệp vụ không ghi đè equals:** **Objects.equals** không tạo ra bình đẳng theo thuộc tính; lớp phải tự định nghĩa và tuân thủ hợp đồng equals/hashCode.
- **Sắp xếp:** **Objects.equals** chỉ trả về boolean, không cho quan hệ thứ tự. Khi cần thứ tự và null, dùng **Comparator.nullsFirst(...)** hoặc **Comparator.nullsLast(...)** với comparator phù hợp.
- **Bảo vệ tính bí mật của giá trị:** **Objects.equals** không bảo đảm so sánh thời gian cố định. Với byte bí mật, cần API và thiết kế chuyên dụng phù hợp ngữ cảnh bảo mật.

## 10. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| **nullable.equals(value)** | **NullPointerException** nếu nullable null | **Objects.equals(nullable, value)** hoặc gọi trên hằng khác null |
| Dùng **==** để so nội dung String | So tham chiếu, kết quả phụ thuộc việc hai biến có cùng đối tượng | Dùng **equals** hoặc **Objects.equals** |
| Mặc định hai null không bao giờ bằng nhau | Hiểu sai kết quả API | Nhớ **Objects.equals(null, null)** là true; bổ sung điều kiện nghiệp vụ khi cần |
| Dùng **Objects.equals** trên hai mảng mới | Có thể false dù các phần tử bằng nhau | Dùng **Arrays.equals/deepEquals** |
| Cho rằng Objects.equals tự so trường của mọi object | Hai object khác nhau thường false nếu dùng **Object.equals** mặc định | Định nghĩa equals/hashCode trong lớp giá trị |
| Ghi đè **equals** nhưng bỏ quên **hashCode** | Vi phạm hợp đồng, gây lỗi trong HashMap/HashSet | Ghi đè đồng thời, dựa trên các trường so sánh |
| Xem **null** giống **""** | Mất khác biệt giữa vắng giá trị và chuỗi rỗng | Xác định quy tắc normalize đầu vào riêng |
| Giả định so sánh bỏ qua chữ hoa/dấu | So sánh có thể false | Dùng logic chuẩn hóa và so sánh riêng theo yêu cầu |
| Đặt đối tượng có trường equals/hashCode biến đổi vào HashSet | Khó tìm lại object sau khi trường thay đổi | Thiết kế key bất biến hoặc duy trì hợp đồng nhất quán |

## 11. Tự kiểm tra kiến thức

1. **Objects.equals(null, null)** trả về gì? — **true**, vì hai tham chiếu cùng null.
2. **Objects.equals(null, "x")** có ném NullPointerException không? — **Không**, nó trả về **false**.
3. Vì sao **new String("x") == "x"** khác với **Objects.equals(new String("x"), "x")**? — Biểu thức đầu kiểm tra hai tham chiếu (false), biểu thức sau dùng String.equals so nội dung (true).
4. **Objects.equals(new int[]{1, 2}, new int[]{1, 2})** có trả về true không? — **Không**, hai mảng khác tham chiếu; dùng **Arrays.equals** khi muốn so phần tử.
5. Khi cả hai ID đều null, **Objects.equals(idA, idB)** trả về true. Có nên coi đó là cùng một tài khoản? — **Không mặc nhiên**; phải áp dụng ràng buộc mã định danh hợp lệ trong nghiệp vụ.
6. Khi ghi đè **equals** trong lớp có trường String nullable, nên so trường đó bằng gì? — **Objects.equals(this.field, other.field)**, đồng thời bảo đảm **hashCode** phù hợp.
7. Dùng cách nào nếu chỉ muốn biết trạng thái từ null sang một giá trị mới đã thay đổi? — **!Objects.equals(oldValue, newValue)**.
8. Hai String cùng nội dung nhưng khác mã hóa dấu tiếng Việt có luôn equals không? — **Không**; nếu cần so canonical equivalence, phải chuẩn hóa Unicode nhất quán trước.

## 12. Ghi nhớ

**java.util.Objects.equals(a, b)** là cách ngắn gọn và an toàn để so sánh **hai tham chiếu có thể null**. Quy tắc cốt lõi là **(a == b) || (a != null && a.equals(b))**.

Với String, nó so **nội dung**, thay vì dựa vào tính đồng nhất của đối tượng. Nó vẫn tuân theo **equals** do lớp triển khai: không tự chuẩn hóa văn bản, không tự bỏ qua chữ hoa/thường, không tự so sâu mọi mảng, và không tự xác thực rằng **null** là hợp lệ về mặt nghiệp vụ.

Khi dùng trong lớp của mình, hãy giữ đúng hợp đồng **equals/hashCode**, xác định ý nghĩa của null, và chọn phương thức so sánh tương ứng với loại dữ liệu thực tế.

**Tài liệu API:** Java SE 17 — **java.util.Objects.equals(Object, Object)**, **java.lang.Object.equals(Object)**, **java.lang.String.equals(Object)**, **java.util.Arrays.equals(...)** và **Arrays.deepEquals(...)**.