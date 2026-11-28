# Autoboxing, valueOf và bẫy suy luận equality từ cache wrapper

Java cho phép chuyển đổi tự động giữa kiểu nguyên thủy và lớp wrapper. Nhờ *autoboxing* và *unboxing*, lập trình viên có thể viết **Integer count = 10** hoặc **int total = count** mà không cần gọi phương thức chuyển đổi một cách tường minh. Các API như **Integer.valueOf()** cũng giúp tạo wrapper thuận tiện và có thể tái sử dụng một số instance.

Sự tiện lợi này dễ dẫn đến một nhầm lẫn: hai wrapper chứa cùng một số có nhất thiết là cùng một object hay không? Câu trả lời phụ thuộc vào loại phép chuyển đổi và phạm vi bảo đảm của Java. Bài học này giải thích quy tắc boxing trong Java Language Specification, cache wrapper, cách dùng **valueOf()** và cách tránh phụ thuộc vào identity trong Java hiện đại.

## 1. Wrapper và autoboxing là gì?

Mỗi kiểu nguyên thủy trong Java có một lớp wrapper tương ứng:

| Kiểu nguyên thủy | Lớp wrapper |
| --- | --- |
| **boolean** | **Boolean** |
| **byte** | **Byte** |
| **short** | **Short** |
| **char** | **Character** |
| **int** | **Integer** |
| **long** | **Long** |
| **float** | **Float** |
| **double** | **Double** |

Wrapper cho phép biểu diễn giá trị nguyên thủy dưới dạng object. Điều này cần thiết khi làm việc với generic, collection và các API nhận object. Ví dụ, **List<int>** không hợp lệ, nhưng **List<Integer>** hợp lệ.

### Autoboxing

Autoboxing là chuyển đổi tự động từ kiểu nguyên thủy sang wrapper tương ứng:

~~~java
int primitive = 42;
Integer wrapped = primitive; // Autoboxing
~~~

Về mặt ngôn ngữ, compiler thực hiện một boxing conversion theo quy tắc của Java Language Specification. Có thể viết tường minh bằng **Integer.valueOf()**:

~~~java
int primitive = 42;
Integer wrapped = Integer.valueOf(primitive);
~~~

Cách viết autoboxing ngắn gọn hơn, còn **valueOf()** giúp thể hiện rõ rằng chương trình đang tạo hoặc lấy một wrapper từ giá trị nguyên thủy.

### Unboxing

Unboxing là chuyển đổi ngược từ wrapper sang kiểu nguyên thủy:

~~~java
Integer wrapped = Integer.valueOf(42);
int primitive = wrapped; // Unboxing
~~~

Compiler thực hiện thao tác tương đương gọi phương thức lấy giá trị nguyên thủy, chẳng hạn **wrapped.intValue()**.

Unboxing chỉ an toàn khi wrapper khác **null**. Nếu reference đang là **null**, thao tác unboxing sẽ ném **NullPointerException**:

~~~java
Integer count = null;

// Phát sinh NullPointerException do unboxing
// int value = count;
~~~

Vì vậy, cần kiểm tra null trước khi sử dụng wrapper trong phép tính hoặc phép so sánh với primitive.

## 2. valueOf() và cache wrapper

Các phương thức **valueOf()** tạo wrapper từ giá trị nguyên thủy hoặc chuỗi. Một số lớp wrapper tái sử dụng instance trong một phạm vi giá trị nhất định. Cơ chế này thường được gọi là *wrapper cache*.

Ví dụ với **Integer**:

~~~java
Integer first = Integer.valueOf(100);
Integer second = Integer.valueOf(100);

System.out.println(first == second); // true
~~~

Với **Integer.valueOf(int)**, Java API bảo đảm cache các giá trị từ **-128** đến **127**, đồng thời cho phép implementation cache thêm giá trị ngoài phạm vi này. Vì vậy, hai lời gọi với cùng giá trị **100** trả về cùng instance, nhưng không có bảo đảm tương tự cho **1000**.

Các factory wrapper phổ biến có những bảo đảm cache được ghi rõ trong Java API:

| Factory | Phạm vi cache được API mô tả |
| --- | --- |
| **Boolean.valueOf(boolean)** | Trả về **Boolean.TRUE** hoặc **Boolean.FALSE** tương ứng |
| **Byte.valueOf(byte)** | Cache toàn bộ giá trị có thể biểu diễn bằng **byte** |
| **Short.valueOf(short)**, **Integer.valueOf(int)**, **Long.valueOf(long)** | Luôn cache từ **-128** đến **127**; có thể cache thêm giá trị khác |
| **Character.valueOf(char)** | Luôn cache từ **U+0000** đến **U+007F**; có thể cache thêm ký tự khác |
| **Float.valueOf(float)**, **Double.valueOf(double)** | API không cam kết tái sử dụng instance theo identity |

Các mô tả này thuộc hợp đồng của từng factory. Chúng không có nghĩa ứng dụng nên dùng **==** để so sánh wrapper; cache là chi tiết nhằm tiết kiệm tài nguyên, còn equality theo giá trị vẫn cần dựa trên **equals()**.

Ví dụ ngoài phạm vi được bảo đảm:

~~~java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

System.out.println(first == second); // Không có cam kết về kết quả
System.out.println(first.equals(second)); // true
~~~

Hai wrapper có cùng giá trị số, nhưng chương trình không được dựa vào việc chúng có cùng identity hay không. Runtime có thể tái sử dụng instance hoặc tạo instance khác theo những gì API cho phép.

### Phạm vi cache và bảo đảm của Java

Cần phân biệt hai khái niệm:

- **Bảo đảm của ngôn ngữ và API:** những trường hợp mà Java Language Specification hoặc Java API yêu cầu các phép chuyển đổi phải cho kết quả identity nhất định.
- **Chi tiết triển khai:** runtime có thể cache thêm các giá trị ngoài phạm vi tối thiểu được bảo đảm.

Theo quy tắc boxing conversion trong Java Language Specification, khi boxing kết quả của một biểu thức hằng thuộc các kiểu **boolean**, **byte**, **char**, **short**, **int** hoặc **long** trong những phạm vi được chỉ định, Java bảo đảm các phép boxing tương ứng có cùng identity. Với các kiểu số nguyên, phạm vi hằng số được bảo đảm chung là từ **-128** đến **127**; với **char**, phạm vi là từ **U+0000** đến **U+007F**; với **boolean**, hai giá trị **true** và **false** có identity ổn định.

Quy tắc này áp dụng cho *boxing conversion* của biểu thức hằng phù hợp. Không suy rộng thành cam kết rằng mọi biến wrapper có giá trị nằm trong khoảng đó luôn cùng tham chiếu trong mọi tình huống.

Ví dụ:

~~~java
Integer a = 127;
Integer b = 127;

System.out.println(a == b); // true theo bảo đảm boxing conversion
~~~

Với giá trị ngoài phạm vi:

~~~java
Integer a = 128;
Integer b = 128;

System.out.println(a == b); // Không được đặc tả kết quả
~~~

Một implementation có thể cache thêm giá trị **128**, nên trên một runtime cụ thể kết quả có thể là **true**. Runtime khác hoặc cấu hình khác có thể cho **false**. Cả hai đều không làm thay đổi hợp đồng so sánh giá trị của **Integer**.

Cũng cần chú ý rằng biểu thức hằng và biến thông thường là hai trường hợp khác nhau:

~~~java
int source = 127;

Integer first = source;
Integer second = source;

System.out.println(first == second); // Không có bảo đảm identity từ quy tắc hằng số
System.out.println(first.equals(second)); // true
~~~

**source** là biến, không phải biểu thức hằng tại vị trí boxing. Việc runtime có cache hay không không nên trở thành một phần logic của ứng dụng.

## 3. Không dùng == để kiểm tra giá trị của wrapper

Với hai wrapper reference, **==** kiểm tra identity. Nó không kiểm tra hai wrapper có chứa cùng giá trị hay không.

~~~java
Integer first = Integer.valueOf(10);
Integer second = Integer.valueOf(10);

boolean sameObject = first == second;
boolean sameValue = first.equals(second);
~~~

Trong ví dụ này, **sameObject** có thể là **true** do cache, nhưng **sameValue** mới là kết quả mà logic nghiệp vụ cần dựa vào.

Hãy so sánh theo giá trị:

~~~java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

if (first.equals(second)) {
    System.out.println("Hai giá trị bằng nhau");
}
~~~

Nếu cả hai wrapper có thể null, dùng **Objects.equals()**:

~~~java
import java.util.Objects;

Integer first = null;
Integer second = null;

System.out.println(Objects.equals(first, second)); // true
~~~

**Objects.equals()** trả về **true** khi cả hai cùng null, **false** khi chỉ một bên null và gọi **equals()** khi cả hai khác null.

### Khi so sánh wrapper với primitive

Nếu một toán hạng là primitive, wrapper sẽ được unbox và phép so sánh thực hiện trên giá trị nguyên thủy:

~~~java
Integer wrapped = Integer.valueOf(1000);
int primitive = 1000;

System.out.println(wrapped == primitive); // true: wrapper được unbox
~~~

Điều này khác với so sánh hai wrapper:

~~~java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

System.out.println(first == second);      // So sánh identity
System.out.println(first.intValue() == second.intValue()); // So sánh số nguyên
System.out.println(first.equals(second)); // So sánh theo hợp đồng wrapper
~~~

Không nên cố ý dựa vào unboxing để thay thế **equals()**. Khi viết code với wrapper, dùng **equals()** hoặc **Objects.equals()** thể hiện rõ ý định so sánh object theo giá trị và tránh lỗi khi giá trị có thể null.

## 4. Dùng autoboxing và valueOf đúng cách

### Khi nào nên dùng wrapper?

Wrapper hữu ích trong những trường hợp cần object:

- Phần tử của collection và kiểu tham số generic, ví dụ **List<Integer>**.
- Giá trị có thể vắng mặt, khi cần kết hợp wrapper nullable với mô hình dữ liệu phù hợp.
- API nhận hoặc trả về wrapper.
- Một số API yêu cầu object để làm việc với reflection, annotation hoặc framework.

Nếu chỉ thực hiện tính toán số học, kiểu nguyên thủy thường rõ ràng và tránh chi phí boxing/unboxing không cần thiết.

~~~java
int total = 0;

for (int i = 0; i < 1000; i++) {
    total += i;
}
~~~

Nếu dùng wrapper trong vòng lặp:

~~~java
Integer total = 0;

for (int i = 0; i < 1000; i++) {
    total += i; // Unbox total, cộng số nguyên, rồi box kết quả
}
~~~

Đoạn thứ hai vẫn hợp lệ, nhưng có thể tạo thêm thao tác boxing và unboxing. Compiler và runtime có thể tối ưu một số trường hợp, song không nên chọn wrapper cho phép tính thuần túy khi primitive đã đáp ứng nhu cầu.

### Chọn valueOf() hoặc parseXxx()

Khi có dữ liệu dạng chuỗi, chọn API theo kiểu kết quả mong muốn:

~~~java
String raw = "256";

Integer boxed = Integer.valueOf(raw);
int primitive = Integer.parseInt(raw);
~~~

- **Integer.valueOf(String)** trả về wrapper **Integer**.
- **Integer.parseInt(String)** trả về primitive **int**.

Nếu cần truyền vào collection hoặc API generic, dùng wrapper. Nếu chỉ cần tính toán, dùng primitive. Các phương thức **valueOf()** cũng là cách tạo wrapper thông dụng vì chúng có thể tận dụng cache theo hợp đồng API.

### Tránh constructor wrapper đã deprecated

Không dùng cách tạo wrapper bằng constructor như:

~~~java
// Các constructor wrapper này đã deprecated
// Integer count = new Integer(10);
// Boolean enabled = new Boolean(true);
~~~

Hãy dùng autoboxing hoặc **valueOf()**:

~~~java
Integer count = 10;
Boolean enabled = Boolean.TRUE;

Integer parsedCount = Integer.valueOf("10");
~~~

Cách viết hiện hành giúp tránh tạo object trực tiếp không cần thiết và tránh nhầm lẫn về identity.

## 5. Cache wrapper không phải cơ chế đồng bộ hoặc định danh

Vì cache có thể khiến hai biến cùng trỏ tới một object, không sử dụng wrapper làm khóa cho **synchronized**:

~~~java
Integer lock = Integer.valueOf(1);

// Không dùng value-based instance làm monitor
// synchronized (lock) {
//     updateSharedState();
// }
~~~

Các lớp wrapper là value-based class. Hợp đồng của chúng không bảo đảm identity riêng cho từng giá trị và không cho phép chương trình dựa vào monitor của instance để đồng bộ. Một đoạn code khác có thể nhận cùng instance từ cache, dẫn tới các luồng hoặc thành phần không liên quan vô tình dùng chung monitor.

Hãy tạo một object khóa riêng do lớp sở hữu:

~~~java
public class Inventory {
    private final Object lock = new Object();
    private int quantity;

    public void add(int amount) {
        synchronized (lock) {
            quantity += amount;
        }
    }
}
~~~

Tương tự, không dùng **System.identityHashCode(wrapper)** hoặc **IdentityHashMap** để nhận diện các giá trị wrapper. Khi cần lưu trữ và tìm kiếm theo giá trị, dùng collection dựa trên **equals()** và **hashCode()** như **HashMap** hoặc **HashSet**.

## 6. Ví dụ tổng hợp

Ví dụ sau cho thấy sự khác nhau giữa boxing, cache, unboxing và so sánh theo giá trị:

~~~java
import java.util.Objects;

public class WrapperEqualityDemo {
    public static void main(String[] args) {
        Integer smallA = 127;
        Integer smallB = 127;

        Integer largeA = 1000;
        Integer largeB = 1000;

        System.out.println(smallA == smallB);       // true theo boxing guarantee
        System.out.println(largeA == largeB);       // Không được bảo đảm
        System.out.println(largeA.equals(largeB));  // true

        int primitive = 1000;
        System.out.println(largeA == primitive);    // true sau unboxing

        Integer absent = null;
        System.out.println(Objects.equals(absent, largeA)); // false
    }
}
~~~

Các kết quả có ý nghĩa như sau:

| Biểu thức | Ý nghĩa |
| --- | --- |
| **smallA == smallB** | Hai phép boxing của hằng **127** có identity được bảo đảm theo JLS |
| **largeA == largeB** | So sánh identity; kết quả không được bảo đảm |
| **largeA.equals(largeB)** | So sánh giá trị wrapper |
| **largeA == primitive** | Unbox **largeA**, rồi so sánh hai giá trị **int** |
| **Objects.equals(absent, largeA)** | So sánh an toàn khi một tham chiếu có thể null |

Ví dụ này cũng cho thấy vì sao không nên viết logic ứng dụng dựa trên kết quả **==** của wrapper. Một đoạn code có thể chạy đúng trên môi trường phát triển vì cache được mở rộng, rồi thể hiện kết quả khác khi chạy trên môi trường khác.

## 7. Kết luận

Autoboxing và unboxing giúp Java kết hợp kiểu nguyên thủy với wrapper một cách thuận tiện. Các API **valueOf()** có thể tận dụng cache để tái sử dụng instance, còn Java Language Specification quy định một số bảo đảm identity hẹp cho boxing conversion của các giá trị hằng.

Những bảo đảm đó không biến wrapper thành đối tượng có identity phù hợp cho logic nghiệp vụ. Khi so sánh hai wrapper theo giá trị, hãy dùng **equals()** hoặc **Objects.equals()**; khi cần tính toán, cân nhắc unbox sang primitive và kiểm tra null trước. Dùng wrapper cache như một chi tiết tối ưu của nền tảng, không dùng nó để suy luận equality, khóa đồng bộ hoặc định danh object.

## Tài liệu tham khảo

- [JLS 27 — Boxing Conversion (Section 5.1.7)](https://docs.oracle.com/javase/specs/jls/se27/html/jls-5.html#jls-5.1.7)
- [Integer — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Integer.html)
- [Long — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Long.html)
- [Short — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Short.html)
- [Byte — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Byte.html)
- [Character — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html)
- [Boolean — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Boolean.html)
- [Float — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Float.html)
- [Double — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Double.html)
- [Value-based Classes — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/doc-files/ValueBased.html)
- [JEP 390: Warnings for Value-Based Classes](https://openjdk.org/jeps/390)

