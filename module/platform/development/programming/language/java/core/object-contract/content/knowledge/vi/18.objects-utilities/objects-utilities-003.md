# Objects.hashCode() cho một đối tượng

## 1. Mục tiêu: tính hashCode null-safe cho đúng một đối tượng

Trong Java, phương thức **hashCode()** thuộc **java.lang.Object**. Nó trả về một số nguyên **int**, thường được dùng cùng **equals(Object)** trong **HashMap**, **HashSet**, **LinkedHashMap** và các cấu trúc dữ liệu băm khác. Cú pháp **value.hashCode()** có một vấn đề thường gặp: nếu **value == null**, chương trình sẽ ném **NullPointerException**.

Lớp tiện ích **java.util.Objects** có phương thức tĩnh:

~~~java
public static int hashCode(Object o)
~~~

Ý nghĩa của nó tương đương:

~~~java
return o == null ? 0 : o.hashCode();
~~~

Hai đoạn này mô tả chữ ký và logic của API, không phải một chương trình Java độc lập. Nếu truyền **null**, kết quả là **0**; nếu truyền một object khác **null**, Java gọi phương thức **hashCode()** của chính object đó, theo cơ chế dispatch động. Nó **không tạo thuật toán hash mới**, không tự gom nhiều trường, không xác minh hợp đồng equals và không biến một kiểu mutable thành immutable.

Ví dụ nhanh:

~~~java
Objects.hashCode(null)   // 0
Objects.hashCode("A")    // 65
"A".hashCode()           // 65
~~~

Đây là các biểu thức minh họa, cần import **java.util.Objects** khi đặt vào code thật. Hash của String **"A"** là 65 theo thuật toán String.hashCode; nhưng **không phải object nào cũng có hash ổn định và dễ đoán** theo cách này.

**Ghi nhớ ngay:** **Objects.hashCode(x)** nghĩa là “nếu x có giá trị thì dùng x.hashCode(), còn null thì dùng 0”.

## 2. Ví dụ Java 17 chạy được: null, String và đối tượng tương đương

Tạo file **SingleObjectHashDemo.java**:

~~~java
import java.util.Objects;

public class SingleObjectHashDemo {
    public static void main(String[] args) {
        Object missing = null;
        String first = new String("A");
        String second = new String("A");

        System.out.println("null hash: " + Objects.hashCode(missing));
        System.out.println("first hash: " + Objects.hashCode(first));
        System.out.println("direct hash: " + first.hashCode());
        System.out.println("same value: " + first.equals(second));
        System.out.println("same hash: " +
            (Objects.hashCode(first) == Objects.hashCode(second)));

        System.out.println("one-field Objects.hash: " +
            Objects.hash(first));
        System.out.println("single-null Objects.hash: " +
            Objects.hash((Object) null));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac SingleObjectHashDemo.java
java SingleObjectHashDemo
~~~

Kết quả:

~~~text
null hash: 0
first hash: 65
direct hash: 65
same value: true
same hash: true
one-field Objects.hash: 96
single-null Objects.hash: 31
~~~

**Giải thích từng dòng quan trọng:**

1. **Objects.hashCode(missing)** không ném exception mà trả **0**.
2. **Objects.hashCode(first)** trực tiếp dùng **String.hashCode()**, nên bằng **first.hashCode()**.
3. Hai instance String được tạo riêng nhưng **equals** true vì có cùng chuỗi ký tự. Vì String tuân thủ hợp đồng equals/hashCode, hai hash bằng nhau.
4. **Objects.hash(first)** lại trả **96**, không phải **65**, vì đây là API **khác**: nó băm một **mảng tham số varargs**, kể cả khi chỉ có một tham số.
5. **Objects.hash((Object) null)** trả **31** vì đây là **một phần tử null** trong mảng tham số dài một. Ép kiểu **(Object)** cho biết rõ ý định truyền **một đối tượng null**, tránh nhập nhằng với việc truyền một mảng **Object[]** null.

Đừng dùng các kết quả ví dụ này để kết luận hashCode là ID duy nhất hoặc một chữ ký an toàn: nhiều object khác nhau có thể cùng hash 32-bit.

## 3. Phân biệt Objects.hashCode(Object) với Objects.hash(Object...)

Tên hai phương thức chỉ khác một chút nhưng cơ chế rất khác:

| Tiêu chí | **Objects.hashCode(Object)** | **Objects.hash(Object...)** |
| --- | --- | --- |
| Số đối tượng về mặt ý nghĩa | **Một** object, có thể null | **Nhiều** giá trị truyền dưới dạng varargs |
| Cơ chế | **o == null ? 0 : o.hashCode()** | Dựa trên **Arrays.hashCode(Object[])** của các tham số |
| Một String **"A"** | **65** | **96** vì 31 × 1 + 65 |
| Một tham số null ép kiểu Object | **0** | **31** |
| Không truyền tham số | Không có overload không tham số | **Objects.hash()** trả **1** |
| Dùng ở đâu | Null-safe delegate đến hashCode của một giá trị | Tiện để phối hợp hash của nhiều field |

Để hiểu kết quả 96:

~~~text
Objects.hash("A")
    = Arrays.hashCode(new Object[]{"A"})
    = 31 * 1 + "A".hashCode()
    = 31 + 65
    = 96
~~~

Điều này **không** có nghĩa **Objects.hash** tính sai. Nó được thiết kế để kết hợp các tham số của **một bộ giá trị**, ví dụ một lớp có **name**, **age**, **department**. Còn **Objects.hashCode** dùng để xử lý hashCode **của một object** theo cách null-safe.

### Hai trường hợp null dễ nhầm

~~~java
Objects.hashCode((Object) null)    // 0
Objects.hash((Object) null)        // 31
Objects.hash((Object[]) null)      // 0
~~~

Đây là các biểu thức minh họa. Với **Objects.hash((Object[]) null)**, tham số varargs là **mảng null**, và **Arrays.hashCode((Object[]) null)** trả 0. Với **Objects.hash((Object) null)**, tham số varargs là **mảng có một phần tử null**, nên kết quả 31.

Khi gọi **Objects.hash(null)** trực tiếp, Java có thể chọn cách diễn giải varargs gây cảnh báo biên dịch hoặc hành vi khiến người đọc hiểu nhầm; nên ghi rõ ép kiểu **(Object)** hoặc **(Object[])** tùy ý định.

### Cách chọn đúng

- Muốn thay **obj.hashCode()** mà tránh NullPointerException: dùng **Objects.hashCode(obj)**.
- Muốn kết hợp hash của **nhiều thành phần giá trị**: dùng **Objects.hash(field1, field2, ...)** hoặc công thức 31 tự viết cẩn thận.
- Muốn băm nội dung mảng: dùng **Arrays.hashCode** hoặc **Arrays.deepHashCode** phù hợp với phép so sánh mảng; không mặc định thay bằng một trong hai API trên.

## 4. Vai trò của equals: hashCode không quyết định hai object bằng nhau

Hợp đồng chung của **Object** yêu cầu:

1. Nếu **a.equals(b)** là **true**, thì **a.hashCode() == b.hashCode()** bắt buộc đúng, miễn là dữ liệu dùng để so sánh không thay đổi.
2. Nếu **a.equals(b)** là **false**, hai hash **được phép** bằng nhau: va chạm băm là bình thường.
3. Khi thông tin được dùng trong equals chưa thay đổi, gọi hashCode nhiều lần trên cùng object phải cho kết quả nhất quán trong một lần chạy ứng dụng theo hợp đồng Java.
4. Không có yêu cầu hashCode của một object phải giống nhau giữa **các lần khởi chạy JVM** khác nhau.

Vì **Objects.hashCode(x)** chỉ gọi **x.hashCode()** với x khác null, quy tắc trên áp dụng nguyên vẹn. Nếu lớp tự cài **equals** mà quên override **hashCode** tương ứng, việc bọc bằng **Objects.hashCode** **không sửa được lỗi**.

### Không dùng hashCode làm phép kiểm tra bằng nhau

Sai:

~~~java
// Chỉ minh họa biểu thức, không phải file độc lập:
boolean same = Objects.hashCode(a) == Objects.hashCode(b);
~~~

Hai object khác nhau có thể trùng mã băm. Muốn so sánh null-safe giữa **hai object**, dùng **Objects.equals(a, b)**; muốn tạo map/set khóa giá trị, cài equals/hashCode đúng cho lớp khóa.

~~~java
boolean same = Objects.equals(a, b);
~~~

Trong chương trình thật, **a** và **b** phải là các biến đã khai báo. Nếu cả hai null, **Objects.equals(a, b)** trả true. Nếu chỉ một bên null, trả false. Nếu cả hai khác null, nó gọi equals của đối tượng thứ nhất. Đây là tác vụ **khác** với Objects.hashCode.

**Một lưu ý:** **Objects.hashCode(null) == 0** không có nghĩa hash 0 chỉ dành riêng cho null. Nhiều object hợp lệ có thể trả hash 0; muốn kiểm tra null phải dùng **obj == null**.

## 5. Ví dụ: tự cài equals/hashCode cho các trường nullable

Giả sử khóa **CustomerKey** gồm **tenantId** và **customerCode**; cả hai là String, và ở ví dụ minh họa ta cho phép null. Hai khóa bằng nhau khi từng trường tương ứng bằng nhau, kể cả trường cùng null.

Tạo file **NullableCustomerKeyDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class NullableCustomerKeyDemo {
    static final class CustomerKey {
        private final String tenantId;
        private final String customerCode;

        CustomerKey(String tenantId, String customerCode) {
            this.tenantId = tenantId;
            this.customerCode = customerCode;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof CustomerKey other)) {
                return false;
            }
            return Objects.equals(tenantId, other.tenantId)
                && Objects.equals(customerCode, other.customerCode);
        }

        @Override
        public int hashCode() {
            int result = Objects.hashCode(tenantId);
            result = 31 * result + Objects.hashCode(customerCode);
            return result;
        }
    }

    public static void main(String[] args) {
        CustomerKey first = new CustomerKey(null, "A");
        CustomerKey second = new CustomerKey(null, new String("A"));
        CustomerKey different = new CustomerKey("X", "A");

        System.out.println("first equals second: " +
            first.equals(second));
        System.out.println("hash equal: " +
            (first.hashCode() == second.hashCode()));
        System.out.println("first hash: " + first.hashCode());
        System.out.println("first equals different: " +
            first.equals(different));

        Set<CustomerKey> keys = new HashSet<>();
        keys.add(first);
        keys.add(second);
        keys.add(different);
        System.out.println("unique keys: " + keys.size());
    }
}
~~~

Chạy:

~~~bash
javac NullableCustomerKeyDemo.java
java NullableCustomerKeyDemo
~~~

Kết quả:

~~~text
first equals second: true
hash equal: true
first hash: 65
first equals different: false
unique keys: 2
~~~

**Phân tích:**

- **Objects.equals** xử lý null cho hai trường trong equals.
- **Objects.hashCode(tenantId)** của khóa đầu tiên là **0**, vì tenantId null.
- **Objects.hashCode(customerCode)** là **65** với String **"A"**, nên hàm hash tự viết cho khóa đó cho **31 × 0 + 65 = 65**.
- Hai instance String "A" khác tham chiếu vẫn cho hash như nhau vì equals của String dựa trên nội dung.
- Khóa khác tenantId không equals khóa đầu tiên; HashSet giữ hai khóa logic.

Đây chỉ là **một công thức kết hợp hash hợp lệ**. Hợp đồng Java không bắt mọi lớp phải dùng số nhân 31. Công thức có thể khác và vẫn đúng nếu tất cả cặp object bằng nhau cho hash giống nhau. **Objects.hash(tenantId, customerCode)** cũng là một lựa chọn gọn, vì nó băm nhiều component nhất quán khi các component có hashCode tương thích với equals.

**Quyết định miền nghiệp vụ:** Một hệ thống thật thường không muốn null trong mã định danh; khi ấy nên dùng **Objects.requireNonNull** trong constructor để từ chối đầu vào. Ví dụ cho phép null ở đây nhằm minh họa rõ cơ chế của **Objects.hashCode(Object)**, không phải khuyến nghị dùng null làm khóa khách hàng.

## 6. Khi field đã có hashCode hoặc đối tượng được bao trong record

### Một field nullable trong một phép tính lớn

Đối với một lớp có một trường object nullable và một trường primitive:

~~~java
// Đoạn mã trong hashCode() của một lớp có các field name, version:
int result = Objects.hashCode(name);
result = 31 * result + Integer.hashCode(version);
return result;
~~~

**Integer.hashCode(int)** phù hợp với primitive int, không cần boxing. Không viết **Objects.hashCode(version)** khi chỉ cần tính hash cho int: lời gọi đó yêu cầu boxing sang Integer; kết quả có thể tương đương nhưng không cần chi phí/độ phức tạp đó.

Với **long**, **boolean**, **double** và các primitive khác, dùng **Long.hashCode**, **Boolean.hashCode**, **Double.hashCode**, v.v. khi muốn hash trực tiếp một giá trị primitive. Với một object như String, enum, LocalDate, record khác hoặc đối tượng nullable, Objects.hashCode rất hữu ích.

### Record thường không cần override hashCode

~~~java
record TicketKey(String eventId, int seatNumber) {}
~~~

Record tự sinh equals/hashCode từ các component. Nếu ngữ nghĩa giá trị là **cùng eventId và seatNumber**, giữ phương thức sinh sẵn là hợp lý. **Objects.hashCode(ticket)** sẽ delegate đến hashCode do record sinh ra.

Không ghi đè equals theo một tập component rồi quên thay hashCode; nếu muốn nhóm theo eventId mà bỏ qua seatNumber, một **record khóa riêng** với chỉ eventId thường rõ nghĩa hơn.

### Trường hợp giá trị nullable tham chiếu đến object khác

Khi field là một record hoặc lớp custom có equals/hashCode đúng, **Objects.hashCode(field)** truyền việc băm cho lớp đó. Nếu field null thì là 0. Nó không tự kiểm tra các field lồng trong object; số băm phụ thuộc hoàn toàn vào **hashCode** thực tế của lớp field.

## 7. Cạm bẫy: `Objects.hashCode(array)` không băm nội dung mảng

Mảng Java là object nhưng không ghi đè `equals()`/`hashCode()` để dùng nội dung phần tử. Vì vậy `Objects.hashCode(array)` ủy quyền đến hash theo danh tính của **chính mảng**. Nếu một lớp so sánh các trường mảng bằng `Arrays.equals` hoặc `Arrays.deepEquals`, phương thức `hashCode()` của lớp cũng phải dựa trên nội dung bằng `Arrays.hashCode` hoặc `Arrays.deepHashCode` tương ứng.

```java
int[] a = {1, 2};
int[] b = {1, 2};
System.out.println(java.util.Arrays.equals(a, b)); // true
System.out.println(java.util.Arrays.hashCode(a)
        == java.util.Arrays.hashCode(b));            // true
```

Những lời gọi trên minh họa trong một phương thức. Hai mảng khác tham chiếu có thể có identity hash khác nhau, nên không thay `Arrays.hashCode(a)` bằng `Objects.hashCode(a)` khi equality xét nội dung. Nếu một lớp bọc mảng được dùng làm khóa `HashMap`, hãy sao chép phòng vệ khi dữ liệu có thể thay đổi. Bài **Objects.deepEquals() khác Objects.equals() ở đối số mảng** trình bày cặp equality/hash cho mảng lồng, còn bài **Objects.hash() cho nhiều giá trị và tình huống truyền mảng** giải thích riêng varargs `Object[]` và `int[]`.

## 8. Lỗi với hashCode của đối tượng mutable làm khóa Map hoặc Set

**Objects.hashCode(obj)** gọi phương thức hiện tại của obj, nên nếu hashCode phụ thuộc vào trường mutable thì số băm có thể thay đổi. HashMap thường chọn bucket theo hash khi chèn; sau khi key bị sửa, tìm lại key có thể không tìm đúng entry đã lưu.

Ví dụ tình huống:

~~~java
// Minh họa: class MutableKey có equals/hashCode dựa trên id có thể sửa.
MutableKey key = new MutableKey("A");
map.put(key, "value");

key.setId("B");

// map.get(key) có thể không tìm được entry đã chèn.
// Objects.hashCode(key) không sửa vấn đề này.
~~~

Đây là đoạn **minh họa không độc lập**, không phải chương trình chạy được; cần có lớp MutableKey và biến map. Điều cần tránh không chỉ là NullPointerException: **giá trị dùng trong equals và hashCode phải ổn định trong thời gian object làm khóa**.

Các lựa chọn an toàn:

- Dùng **String**, **Integer**, **UUID**, **Instant** hoặc record chỉ chứa các component bất biến làm khóa khi phù hợp nghiệp vụ.
- Dùng lớp khóa với trường final và component thực sự bất biến; nếu chứa mảng/collection mutable, áp dụng defensive copy phù hợp.
- Nếu thay đổi định danh là nghiệp vụ bắt buộc, **xóa entry cũ và chèn lại bằng khóa mới**, hoặc dựng lại map theo quy tắc mới.
- Đừng lưu hashCode tính trước rồi tin rằng nó thay cho giá trị khóa hay được phép dùng như ID.

**Phân biệt tính ổn định và tính duy nhất:** Một hàm hash ổn định vẫn có thể va chạm. Cấu trúc hash cần dùng **equals** sau khi xét hash để phân biệt khóa có cùng hash.

## 9. So sánh Object.hashCode, Objects.hashCode, Objects.hash và System.identityHashCode

| API | Giá trị nhận vào | Ý nghĩa |
| --- | --- | --- |
| **obj.hashCode()** | Một obj khác null | Gọi hashCode động của chính object; null gây NullPointerException |
| **Objects.hashCode(obj)** | Một object hoặc null | Null-safe delegate: null → 0, còn lại → obj.hashCode() |
| **Objects.hash(a, b, ...)** | Nhiều giá trị varargs | Kết hợp hash các tham số, thông qua Arrays.hashCode(Object[]) |
| **System.identityHashCode(obj)** | Object, có thể null | Hash theo cơ chế danh tính, không dùng override hashCode; null → 0 |

**System.identityHashCode** đôi khi hữu ích cho cơ chế cần ngữ nghĩa danh tính object, ví dụ chẩn đoán tham chiếu hoặc triển khai dựa trên identity. Tuy nhiên, đây **không** là cách thay thế Objects.hashCode khi equals của lớp đã so theo giá trị. Dùng identity hash trong một lớp có equals theo giá trị có thể làm các instance bằng nhau nhưng có hash khác nhau.

**Lưu ý:** Giá trị số của **System.identityHashCode** không phải địa chỉ bộ nhớ được bảo đảm, và cũng không bảo đảm duy nhất giữa mọi object.

## 10. Kiểm thử nhỏ nhưng đủ phân biệt các API

Một số tình huống nên có trong bài test cho phương thức hashCode của lớp tự viết:

1. **Trường null:** Objects.hashCode(null) là 0; phương thức hashCode của key không ném NullPointerException khi null là đầu vào được cho phép.
2. **Hai object bằng giá trị nhưng khác instance:** nếu equals true thì hashCode phải bằng nhau; thử hai String tạo riêng, hai record cùng component hoặc hai wrapper mảng cùng nội dung.
3. **Va chạm:** không kết luận equals chỉ bằng hash; HashSet/HashMap phải phân biệt các khóa khác nhau ngay cả khi cùng hash.
4. **Trường mutable:** thử thay đổi dữ liệu sau khi làm khóa; nếu lớp cam kết bất biến, hashCode và equals phải không đổi.
5. **Đúng API theo cấu trúc:** object đơn → Objects.hashCode; nhiều field → Objects.hash hoặc công thức tương thích; mảng nội dung → Arrays.hashCode/deepHashCode.
6. **Không dùng độ lớn hash làm độ mạnh:** mã băm âm, dương hoặc 0 đều là kết quả hợp lệ; không tự áp dụng trị tuyệt đối vì **Math.abs(Integer.MIN_VALUE)** vẫn âm.
7. **Không yêu cầu hash khác nhau cho mọi object khác nhau:** đây không phải điều kiện của hợp đồng Object.
8. **Đối chiếu equals và hashCode:** nếu sửa equals để thay đổi bộ trường quyết định giá trị, phải rà lại hashCode cùng lúc.

### Kiểm tra bằng một chương trình đơn giản

Tạo file **HashContractCheckDemo.java**:

~~~java
import java.util.Objects;

public class HashContractCheckDemo {
    record Code(String value) {}

    public static void main(String[] args) {
        Code a = new Code("A");
        Code b = new Code(new String("A"));
        Code c = new Code("B");

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("equal keys hash equal: " +
            (Objects.hashCode(a) == Objects.hashCode(b)));
        System.out.println("a equals c: " + a.equals(c));

        Object missing = null;
        System.out.println("missing hash: " + Objects.hashCode(missing));
    }
}
~~~

Chạy:

~~~bash
javac HashContractCheckDemo.java
java HashContractCheckDemo
~~~

Kết quả:

~~~text
a equals b: true
equal keys hash equal: true
a equals c: false
missing hash: 0
~~~

Hai instance **Code** bằng nhau vì record so component String theo equals. **Objects.hashCode(a)** dùng hashCode của Code; do đó tuân theo hợp đồng giá trị của record. Trường hợp c khác a minh họa equals false, nhưng ta **không yêu cầu** hash của a và c phải khác nhau.

## 11. Câu hỏi thường gặp

**Có thể thay mọi lời gọi obj.hashCode() bằng Objects.hashCode(obj) không?**

Trong ngữ cảnh muốn nhận giá trị 0 khi obj null, điều đó thường đúng. Nhưng nếu **null là lỗi lập trình hoặc đầu vào không hợp lệ**, việc cho phép null âm thầm có thể che đi vi phạm hợp đồng của ứng dụng. Khi ấy **Objects.requireNonNull(obj)** trước khi dùng có thể phù hợp hơn.

**Objects.hashCode(x) có tự gọi equals(x) không?**

Không. Nó chỉ kiểm tra null và gọi **x.hashCode()**. Hợp đồng giữa equals và hashCode phải được bảo đảm bởi kiểu x.

**Tại sao Objects.hash(x) lại khác Objects.hashCode(x)?**

Vì Objects.hash tạo hash **cho một bộ tham số** bằng quy tắc Arrays.hashCode(Object[]). Với đúng một tham số khác null, kết quả thường là **31 + x.hashCode()**, nên khác hash trực tiếp của x.

**HashCode có thể là 0 đối với object không null không?**

Có. Ví dụ một object có override hashCode trả 0 là hoàn toàn có thể; điều này không tự làm equals đúng hay sai. Do đó **Objects.hashCode(x) == 0** không chứng minh x null.

**Có nên lưu hashCode vào database hoặc gửi như định danh duy nhất không?**

Không nên xem hashCode của Java là khóa định danh toàn cục, chữ ký bảo mật hay mã băm mật mã. Nó là số nguyên phục vụ cấu trúc băm, có khả năng va chạm và không được hợp đồng Object bảo đảm ổn định xuyên JVM. Với định danh nên dùng khóa nghiệp vụ, UUID hoặc ID rõ ràng; với toàn vẹn/bảo mật cần thuật toán chuyên dụng theo yêu cầu.

**Khi nào không cần Objects.hashCode?**

Nếu đã có primitive int/long và API tương ứng, dùng **Integer.hashCode**, **Long.hashCode** hoặc cách phối hợp trực tiếp. Nếu record đã sinh hashCode hợp lệ, gọi **record.hashCode()** khi chắc chắn khác null. Nếu đang cần hash một mảng theo nội dung, dùng **Arrays.hashCode** thay vì Objects.hashCode.

## 12. Quy trình áp dụng

Khi thấy một lời gọi **hashCode()** có nguy cơ NullPointerException, hãy xác định trước:

1. Giá trị cần tính hash là **một object** hay **một bộ nhiều trường**?
2. Object có thể null hợp lệ không? Nếu có, **Objects.hashCode(Object)** trả 0. Nếu không, có thể dùng **requireNonNull** để báo lỗi sớm.
3. equals của kiểu object đang kiểm tra **những thuộc tính nào**? HashCode của kiểu đó phải tương thích với equals.
4. Nếu object là **array**, có cần so nội dung bằng Arrays.equals/deepEquals không? Nếu cần, dùng hash nội dung tương ứng.
5. Nếu object là khóa cho HashMap/HashSet, các thành phần ảnh hưởng equals/hashCode có bất biến trong quá trình lưu hay không?
6. Cuối cùng, xác nhận bằng các trường hợp null, giá trị bằng nhau ở hai instance độc lập, collision và thay đổi trạng thái.

**Kết luận cần nhớ:** **Objects.hashCode(x)** chỉ là cách **null-safe** để lấy **hashCode của một đối tượng**. Nó không giống **Objects.hash(x)**, không tự tính hash nội dung mảng, không bảo đảm hash là duy nhất và không sửa được một lớp có equals/hashCode sai. Giá trị thực của API nằm ở khả năng sử dụng nhất quán **hashCode của kiểu x** trong các đoạn code xử lý object có thể null.

Tham khảo: [Java SE 17 – java.util.Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html).
