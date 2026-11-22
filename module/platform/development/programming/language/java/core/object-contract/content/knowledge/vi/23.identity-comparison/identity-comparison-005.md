# Không thay HashMap bằng IdentityHashMap nếu nghiệp vụ cần bằng nhau theo giá trị

## 1. Quyết định quan trọng: “cùng khóa” nghĩa là gì?

Khi chọn một cấu trúc Map trong Java, trước hết phải trả lời **hai khóa nào được coi là cùng một khóa**. Với các đối tượng Java, có hai khái niệm khác nhau:

- **Bằng nhau theo giá trị (logical equality)**: hai object có thể là hai instance khác nhau nhưng đại diện cùng giá trị nghiệp vụ. Quy tắc này được diễn đạt bằng **equals(Object)** và hợp đồng đi kèm **hashCode()**.
- **Cùng một đối tượng (reference identity)**: hai tham chiếu trỏ tới **chính cùng một instance**. Java kiểm tra bằng toán tử **==** trên các tham chiếu.

**HashMap** chọn ngữ nghĩa **giá trị**: các khóa khác instance nhưng **equals true** (với hashCode tương thích) phải được nhận diện là cùng khóa. **IdentityHashMap** chọn ngữ nghĩa **danh tính tham chiếu**: chỉ những tham chiếu **==** mới được coi là cùng khóa. Vì vậy, đổi **HashMap** thành **IdentityHashMap** là **thay đổi logic nghiệp vụ**, không đơn thuần là đổi cách tối ưu bộ nhớ, tốc độ hoặc thuật toán băm.

Ví dụ: hai đối tượng **CustomerId("C-17")** được tạo từ hai request khác nhau. Nếu nghiệp vụ quy định cùng mã khách hàng là cùng một khách hàng, HashMap phải cho phép dùng instance thứ hai để tìm bản ghi được chèn bằng instance thứ nhất. IdentityHashMap không bảo đảm và thường trả về không tìm thấy, dù **equals** giữa chúng trả true.

**Quy tắc chọn mặc định:** Khi khóa là mã khách hàng, mã đơn hàng, UUID, String, record, value object, hoặc tổ hợp thuộc tính định danh nghiệp vụ, thông thường hãy dùng **HashMap<K,V>** (hoặc LinkedHashMap nếu cần thứ tự). Chỉ dùng **IdentityHashMap** khi yêu cầu thực sự là phân biệt từng object **theo tham chiếu**.

## 2. Hợp đồng equals/hashCode của HashMap

**HashMap<K,V>** sử dụng **hashCode()** để hỗ trợ xác định vị trí tìm kiếm và **equals(Object)** để kiểm tra sự tương đương của khóa. Điều kiện nền tảng của hợp đồng Java:

1. **Phản xạ:** a.equals(a) phải true.
2. **Đối xứng:** a.equals(b) có cùng kết quả với b.equals(a).
3. **Bắc cầu:** a bằng b, b bằng c thì a bằng c.
4. **Nhất quán:** khi dữ liệu tham gia so sánh không đổi, kết quả equals ổn định.
5. **Với null:** a.equals(null) là false đối với a khác null.
6. **Hash tương thích:** nếu a.equals(b) true thì a.hashCode() **bắt buộc bằng** b.hashCode().

Điều ngược lại của quy tắc hash **không** đúng: hai khóa có cùng hashCode có thể không bằng nhau. HashMap xử lý va chạm băm bằng cách tiếp tục kiểm tra khóa.

Khi một khóa mới được đưa vào **put** và nó tương đương một khóa đã tồn tại, giá trị gắn với khóa đó được **thay thế**; size không tăng. Trong triển khai HashMap thông thường, khóa đại diện đã lưu được giữ lại khi chỉ thay giá trị của cùng logical key. Không nên dựa vào tham chiếu của “khóa đại diện” trừ khi API hoặc yêu cầu thực sự cần.

**HashMap** cho phép một khóa null và các giá trị null. Vì **get(key)** có thể trả null khi không có ánh xạ hoặc khi ánh xạ tới giá trị null, dùng **containsKey(key)** để phân biệt nếu cần. Đây là thuộc tính Map độc lập với việc chọn equals hay reference identity.

## 3. IdentityHashMap thay thế equals bằng ==

**java.util.IdentityHashMap<K,V>** là Map đặc biệt:

- So sánh **khóa** bằng **==**, thay vì gọi equals theo giá trị.
- Băm khóa theo **System.identityHashCode(key)**, thay vì hashCode được override trong lớp khóa.
- Hai object có cùng nội dung và equals true nhưng **khác tham chiếu** vẫn là **hai khóa**.
- Hai biến tham chiếu cùng instance là **một khóa**, kể cả khi object đó override equals một cách đặc biệt.
- Cho phép khóa null và giá trị null; hành vi kiểm tra danh tính với null vẫn được xử lý như khóa riêng của Map.
- Không bảo đảm thứ tự duyệt. Không dùng kết quả lặp qua entrySet để suy ra thứ tự chèn.

IdentityHashMap **cố ý không tuân quy ước equals theo giá trị** thường dùng cho Map và các view liên quan. Đặc biệt, trong các chương trình trộn Map thường với IdentityHashMap, đừng giả định kiểm tra **mapA.equals(mapB)** luôn có cùng ý nghĩa hoặc đối xứng như giữa hai Map thông thường; tài liệu Java cảnh báo về việc này.

**System.identityHashCode(obj)** không phải địa chỉ bộ nhớ được Java bảo đảm và không đảm bảo duy nhất giữa các object. Có thể xảy ra va chạm identity hash; IdentityHashMap vẫn dựa trên **tham chiếu ==** để phân biệt khóa. Không dùng số identity hash như một ID vĩnh viễn hay khóa nghiệp vụ.

## 4. Ví dụ Java 17: cùng giá trị, hai kết quả Map khác nhau

Tạo file **HashVsIdentityMapDemo.java**:

~~~java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class HashVsIdentityMapDemo {
    record CustomerId(String value) {}

    public static void main(String[] args) {
        CustomerId first = new CustomerId("C-17");
        CustomerId second = new CustomerId("C-17");
        CustomerId lookup = new CustomerId("C-17");

        System.out.println("same reference: " + (first == second));
        System.out.println("same value: " + first.equals(second));
        System.out.println("hash equal: " +
            (first.hashCode() == second.hashCode()));

        Map<CustomerId, String> byValue = new HashMap<>();
        byValue.put(first, "created");
        byValue.put(second, "updated");

        System.out.println("HashMap size: " + byValue.size());
        System.out.println("HashMap lookup: " + byValue.get(lookup));

        Map<CustomerId, String> byIdentity =
            new IdentityHashMap<>();
        byIdentity.put(first, "created");
        byIdentity.put(second, "updated");

        System.out.println("IdentityHashMap size: " +
            byIdentity.size());
        System.out.println("IdentityHashMap first: " +
            byIdentity.get(first));
        System.out.println("IdentityHashMap second: " +
            byIdentity.get(second));
        System.out.println("IdentityHashMap fresh: " +
            byIdentity.get(lookup));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac HashVsIdentityMapDemo.java
java HashVsIdentityMapDemo
~~~

Kết quả:

~~~text
same reference: false
same value: true
hash equal: true
HashMap size: 1
HashMap lookup: updated
IdentityHashMap size: 2
IdentityHashMap first: created
IdentityHashMap second: updated
IdentityHashMap fresh: null
~~~

**Vì sao HashMap chỉ có một entry?** Record **CustomerId** tự sinh equals/hashCode theo component String. Cả first và second đều chứa "C-17", nên hai khóa bằng nhau. Lần put thứ hai cập nhật giá trị của logical key. Một instance CustomerId thứ ba với cùng mã vẫn tìm thấy **"updated"**.

**Vì sao IdentityHashMap có hai entry?** first và second được tạo bằng hai biểu thức **new CustomerId(...)**, nên khác tham chiếu. IdentityHashMap không sử dụng equals/hashCode do record sinh để quyết định cùng khóa. Một instance mới **lookup** không phải first hay second, nên **get(lookup)** trả null.

Nếu chương trình cần đại diện cho “khách hàng C-17”, kết quả IdentityHashMap là **sai về nghĩa nghiệp vụ**: cùng khách hàng bị chia ra nhiều entry. Không có ngoại lệ hay cảnh báo biên dịch nào nhắc về vấn đề này.

## 5. String và wrapper: các trường hợp đánh lừa khi thử bằng ==

Một sai lầm là kiểm tra IdentityHashMap bằng **string literal** rồi tưởng rằng khóa tương đương theo nội dung:

~~~java
String a = "paid";
String b = "paid";
System.out.println(a == b); // thường true vì string literal được intern
~~~

Đoạn này chỉ minh họa. Java intern các string literal tương ứng; điều này khiến hai biến trong ví dụ trỏ cùng object. Nhưng chuỗi nhận từ file, JSON, database hoặc tạo bằng **new String(...)** có thể là instance khác dù giá trị giống nhau.

Tạo file **StringIdentityDemo.java**:

~~~java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class StringIdentityDemo {
    public static void main(String[] args) {
        String first = new String("paid");
        String second = new String("paid");

        Map<String, Integer> byValue = new HashMap<>();
        Map<String, Integer> byIdentity = new IdentityHashMap<>();

        byValue.put(first, 1);
        byValue.put(second, 2);
        byIdentity.put(first, 1);
        byIdentity.put(second, 2);

        System.out.println("same object: " + (first == second));
        System.out.println("same text: " + first.equals(second));
        System.out.println("value map size: " + byValue.size());
        System.out.println("identity map size: " + byIdentity.size());
        System.out.println("value lookup: " +
            byValue.get(new String("paid")));
        System.out.println("identity lookup: " +
            byIdentity.get(new String("paid")));
    }
}
~~~

Lệnh chạy:

~~~bash
javac StringIdentityDemo.java
java StringIdentityDemo
~~~

Kết quả:

~~~text
same object: false
same text: true
value map size: 1
identity map size: 2
value lookup: 2
identity lookup: null
~~~

Các kiểu wrapper như **Integer** cũng có thể được cache ở một số giá trị; không suy ra ý nghĩa nghiệp vụ của **==** từ vài kết quả thử nghiệm có cache. Nếu giá trị là số, chuỗi hoặc khóa dữ liệu, phải dựa trên **equals** hoặc các phép so primitive phù hợp, không dựa trên tình cờ cùng tham chiếu.

Không “sửa” cách dùng IdentityHashMap bằng việc gọi **String.intern()** một cách tùy tiện. Interning thay đổi chính sách chia sẻ tham chiếu, không thay thế hợp đồng giá trị; việc ép mọi dữ liệu đi qua interning có thể có chi phí hoặc hậu quả quản lý bộ nhớ và vẫn dễ bị bỏ sót ở nguồn khác.

## 6. Hậu quả trong xử lý dữ liệu thật

Một map nghiệp vụ thường dùng để:

- **Gom dữ liệu theo customerId:** khách hàng có thể xuất hiện nhiều lần trong log hoặc payload khác nhau.
- **Khử trùng theo orderId:** hai bản ghi cùng định danh chỉ được tính là một đơn.
- **Tra trạng thái theo correlationId:** một request đi qua nhiều tầng có thể tạo nhiều String mới nhưng cùng nội dung.
- **Đếm số thực thể logic:** hai bản sao value object đại diện cùng ID phải gộp thành một nhóm.
- **Lưu cache theo khóa tham số:** hai khóa có bộ tham số bằng nhau phải truy cập chung một entry.

Trong các bài toán này, IdentityHashMap có thể **nhân đôi entry**, tính sai số lượng, bỏ lỡ cache, mất khả năng tra cứu bằng khóa tương đương tạo mới, hoặc khiến kết quả phụ thuộc vào **việc hệ thống có tái sử dụng cùng instance hay không**.

Ví dụ: xử lý dữ liệu phân tán thường deserialize hai bản JSON độc lập thành hai object Java độc lập. Chúng có thể **equals true**, nhưng không cùng object. IdentityHashMap sẽ đối xử như hai khách hàng khác nhau nếu dùng object đó làm khóa, mặc dù miền nghiệp vụ coi cùng ID là một khách hàng.

Đây là lý do không nên chọn IdentityHashMap chỉ vì thấy tên có chữ **HashMap** và suy đoán nó “tối ưu hơn”. Nó là **cấu trúc có semantics riêng**, dành cho bài toán cần tham chiếu vật lý.

## 7. Ví dụ: khóa tổ hợp nghiệp vụ từ record

Một lỗi khác là gom theo mã ID nhưng quên namespace. Trong hệ thống đa tenant, cùng mã khách hàng ở hai tenant có thể đại diện hai khách hàng khác nhau. **HashMap** vẫn cần khóa logic được thiết kế đúng.

Tạo file **BusinessKeyDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class BusinessKeyDemo {
    record CustomerKey(String tenant, String customerCode) {}

    public static void main(String[] args) {
        CustomerKey first = new CustomerKey("A", "C-17");
        CustomerKey duplicate = new CustomerKey("A", "C-17");
        CustomerKey otherTenant = new CustomerKey("B", "C-17");

        Map<CustomerKey, Integer> counts = new HashMap<>();
        counts.merge(first, 1, Integer::sum);
        counts.merge(duplicate, 1, Integer::sum);
        counts.merge(otherTenant, 1, Integer::sum);

        System.out.println("entries: " + counts.size());
        System.out.println("tenant A: " +
            counts.get(new CustomerKey("A", "C-17")));
        System.out.println("tenant B: " +
            counts.get(new CustomerKey("B", "C-17")));
    }
}
~~~

Chạy:

~~~bash
javac BusinessKeyDemo.java
java BusinessKeyDemo
~~~

Kết quả:

~~~text
entries: 2
tenant A: 2
tenant B: 1
~~~

Record **CustomerKey** tự sinh equals/hashCode theo **cả hai component**. Hai bản ghi cùng tenant và cùng customerCode là một khóa, còn cùng customerCode ở tenant khác thì không. HashMap thể hiện chính xác hợp đồng khóa này.

Nếu dùng IdentityHashMap, hai bản ghi của tenant A lại thành hai khóa vì được tạo riêng. Nếu chỉ dùng String customerCode làm khóa HashMap mà bỏ tenant, các khách hàng khác tenant sẽ bị gộp sai. Do đó **chọn HashMap và thiết kế khóa đúng** là hai việc đều quan trọng.

## 8. Khi nào IdentityHashMap thực sự phù hợp?

IdentityHashMap được thiết kế cho các tình huống **danh tính đối tượng có ý nghĩa riêng biệt so với giá trị equals**.

Ví dụ:

1. **Theo dõi object trong thuật toán xử lý đồ thị object:** hai node có cùng dữ liệu nhưng là hai node vật lý khác nhau; thuật toán cần ghi nhớ từng node đã thăm.
2. **Sao chép sâu hoặc serialize đồ thị với tham chiếu chia sẻ:** cần ánh xạ **object gốc → object sao chép**, trong đó hai object gốc có nội dung bằng nhau vẫn phải tạo hai bản sao riêng khi chúng là hai node khác nhau.
3. **Theo dõi trạng thái phụ cho từng instance:** công cụ chẩn đoán, phân tích heap hoặc trình duyệt cấu trúc object cần phân biệt tham chiếu.
4. **Kiểm tra tính đồng nhất tham chiếu:** lưu một thuộc tính gắn với **chính object cụ thể**, không gắn với bất kỳ object nào có cùng giá trị.

Trong những tình huống đó, nếu dùng HashMap và lớp node override equals theo dữ liệu, **hai node riêng** có thể vô tình bị gộp. IdentityHashMap làm đúng yêu cầu phân biệt instance.

Nếu theo dõi các node bằng `Collections.newSetFromMap(new IdentityHashMap<>())`, một lần thêm mỗi instance giữ hai node riêng dù nhãn bằng nhau. Thuật toán DFS/BFS và nhận biết chu kỳ được triển khai đầy đủ ở bài **Dùng danh tính khi duyệt và theo dõi đồ thị đối tượng**.

**Cẩn trọng:** IdentityHashMap giữ tham chiếu mạnh tới khóa và giá trị như một map thông thường trong khi entry còn tồn tại; không dùng nó như cơ chế weak reference. Nếu cần liên kết metadata với object nhưng muốn cho phép garbage collection, phải xem xét cấu trúc như **WeakHashMap** và hợp đồng riêng của nó. Không đánh đồng hai cấu trúc chỉ vì chúng đều chứa chữ Map.

## 9. Trường hợp đặc biệt: hai object equals sai hợp đồng

Có thể có người đổi HashMap thành IdentityHashMap vì **HashMap “không tìm thấy” khóa**. Nhưng nguyên nhân thường là:

- Lớp override **equals** nhưng quên override **hashCode** tương thích.
- Những field tham gia equals/hashCode thay đổi sau khi dùng object làm khóa.
- Các trường mảng dùng equals/hashCode theo danh tính dù nghiệp vụ yêu cầu so nội dung.
- Khóa chỉ chứa một phần định danh nên gộp nhầm các bản ghi khác nhau.
- Sử dụng **LocalDateTime**, **OffsetDateTime**, **BigDecimal** hoặc loại giá trị khác với hợp đồng equals không khớp yêu cầu nghiệp vụ.

**IdentityHashMap có thể che một số triệu chứng** vì nó bỏ qua equals/hashCode tùy biến, nhưng hậu quả là đổi từ “một khóa cho mỗi giá trị” sang “một khóa cho mỗi instance”. Nếu hệ thống cần equals theo giá trị, cách sửa đúng là **khắc phục hợp đồng của kiểu khóa và làm khóa ổn định**, hoặc rút ra một value key bất biến chuyên dụng.

### Ví dụ khóa mutable: đây không phải lý do đổi IdentityHashMap

Tạo file **MutableKeyDemo.java**:

~~~java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Objects;

public class MutableKeyDemo {
    static final class MutableKey {
        String code;

        MutableKey(String code) {
            this.code = code;
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof MutableKey other
                && Objects.equals(code, other.code);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(code);
        }
    }

    public static void main(String[] args) {
        MutableKey key = new MutableKey("A");
        Map<MutableKey, String> byValue = new HashMap<>();
        Map<MutableKey, String> byIdentity = new IdentityHashMap<>();

        byValue.put(key, "found");
        byIdentity.put(key, "found");

        key.code = "B";

        System.out.println("HashMap after edit: " + byValue.get(key));
        System.out.println("IdentityHashMap after edit: " +
            byIdentity.get(key));

        System.out.println("IdentityHashMap equivalent new key: " +
            byIdentity.get(new MutableKey("B")));
    }
}
~~~

Chạy:

~~~bash
javac MutableKeyDemo.java
java MutableKeyDemo
~~~

Kết quả:

~~~text
HashMap after edit: null
IdentityHashMap after edit: found
IdentityHashMap equivalent new key: null
~~~

**Giải thích:** HashMap lưu khóa ở vị trí tổ chức theo hash của String **"A"**. Sau khi sửa code thành **"B"**, hashCode đổi, nên một lần get mới theo hash của B không tìm đúng entry cũ trong ví dụ này. IdentityHashMap vẫn tìm được khi dùng **cùng tham chiếu key**, vì identity không đổi; nhưng với object khác có cùng code B, nó vẫn không tìm thấy.

**Cách sửa nghiệp vụ:** dùng **record MutableKeySnapshot(String code)** hoặc một lớp khóa bất biến; khi cần thay đổi code, tạo **khóa mới** và cập nhật Map có chủ đích. Không thay loại Map chỉ để tránh biểu hiện của mutable key.

## 10. Không dùng identityHashCode làm giá trị ID

Hai khái niệm quan trọng:

- **obj == other** chứng minh hai tham chiếu là cùng object trong ngữ cảnh chạy.
- **System.identityHashCode(obj) == System.identityHashCode(other)** **không chứng minh** hai tham chiếu là cùng object, vì identity hash có thể va chạm.

Không ghi identityHashCode vào database như khóa duy nhất hoặc dùng để liên kết đối tượng giữa các tiến trình/lần khởi động JVM. Số đó không mang ý nghĩa định danh nghiệp vụ hay địa chỉ bộ nhớ bền vững.

Nếu ứng dụng cần ID thực thể, dùng ID được quản lý rõ ràng trong model (ví dụ UUID hoặc khóa database). Nếu cần phân biệt tham chiếu trong thuật toán tạm thời, dùng **==** hoặc IdentityHashMap/identity set để duy trì quan hệ tham chiếu trực tiếp.

## 11. HashMap và IdentityHashMap trong API công khai

Chữ ký **Map<K,V>** che đi sự khác biệt về cách so khóa. Hai implementation đều có thể được truyền vào một hàm nhận Map, nhưng hành vi lookup/put phụ thuộc instance map thực tế.

Ví dụ một hàm dùng **containsKey(new CustomerId("C-17"))** có thể đúng với HashMap và sai với IdentityHashMap đã nhận một CustomerId tương đương nhưng khác tham chiếu. Nếu API yêu cầu “logical key equality”, việc chấp nhận IdentityHashMap là **sai tiền điều kiện**. Tài liệu và test cần diễn đạt điều kiện này, hoặc module chủ động tạo HashMap với khóa value object rõ ràng.

Một số nơi cố dùng IdentityHashMap để “tăng tốc” vì nó không gọi equals phức tạp. Điều đó thay đổi kết quả nghiệp vụ, không phải tối ưu an toàn. Chỉ tối ưu sau khi chứng minh dữ liệu thật và có một phép chuyển đổi **bảo toàn semantics**. Với Map theo giá trị, có thể cải thiện hashCode, tính bất biến của khóa, phân bổ dung lượng hoặc thiết kế khóa chuyên biệt trong khi vẫn giữ HashMap.

Không dùng **IdentityHashMap** để suy luận rằng **equals** của khóa không quan trọng với hệ thống: các API khác vẫn dùng equals, ví dụ HashSet, HashMap khác, List.contains và nhiều nghiệp vụ so sánh giá trị.

## 12. Kiểm tra đúng ngữ nghĩa bằng bộ test tối thiểu

Đối với bài toán cần gộp theo giá trị, hãy kiểm tra ít nhất:

1. **Hai instance được tạo độc lập, cùng giá trị:** equals true, hashCode bằng nhau; khi put vào HashMap, size chỉ tăng một lần.
2. **Lookup bằng instance thứ ba:** HashMap trả đúng giá trị dù tham chiếu khác khóa đã put.
3. **Khác giá trị nghiệp vụ:** equals false và được giữ thành hai khóa; hashCode có thể tình cờ trùng nhưng vẫn không bị gộp.
4. **Khóa tổ hợp:** những thành phần như tenantId, loại thực thể, mã và phiên bản được xét theo đúng định nghĩa miền.
5. **Khóa ổn định:** không sửa field ảnh hưởng equals/hashCode khi khóa còn ở trong Map.
6. **Null:** nếu null được phép, kiểm tra containsKey để phân biệt “không có entry” với “entry có value null”.
7. **Mảng:** nếu nghiệp vụ coi nội dung là giá trị, dùng Arrays.equals/hashCode hoặc wrapper đúng hợp đồng.
8. **Các phiên bản dữ liệu:** deserialize cùng bản ghi hai lần, tạo hai object độc lập rồi thử lookup/gom nhóm.
9. **Nếu thực sự dùng identity:** khẳng định bằng test rằng hai object equals nhưng khác tham chiếu **phải** là hai khóa riêng.

Test theo dữ liệu độc lập quan trọng vì String literal, boxing hoặc các cơ chế tái sử dụng instance có thể làm ví dụ quá đơn giản vô tình trùng identity và che lỗi.

## 13. Bảng quyết định cho ứng dụng

| Nhu cầu thực sự | Cấu trúc thường phù hợp | Tiêu chí bằng nhau |
| --- | --- | --- |
| Trạng thái theo **customerId**, **orderId**, UUID, record key | **HashMap** | **equals/hashCode** của khóa |
| Tra cứu theo **String** tạo từ nhiều nguồn | **HashMap<String,V>** | Nội dung String |
| Gom nhóm theo **tenant + id** | **HashMap<BusinessKey,V>** | equals/hashCode của value key tổ hợp |
| Cần thứ tự các nhóm theo lần xuất hiện | **LinkedHashMap** | Vẫn là **equals/hashCode** |
| Cần thứ tự sắp xếp theo Comparator | **TreeMap** | **compare == 0** theo comparator; phải kiểm tra nhất quán với equals |
| Theo dõi **từng node object** kể cả khi equals nhau | **IdentityHashMap** | **==** và identity hash |
| Tập hợp các object **theo danh tính** | **Collections.newSetFromMap(new IdentityHashMap<>())** | **==** |
| Metadata gắn với object, cần quản lý theo tham chiếu yếu | Xem xét **WeakHashMap** hoặc cơ chế reference phù hợp | **WeakHashMap vẫn có semantics riêng và dùng equals**, không phải thay thế IdentityHashMap |

**Ghi nhớ cốt lõi:** **HashMap** và **IdentityHashMap** trả lời hai câu hỏi khác nhau. Nếu hệ thống cần “hai bản ghi có cùng giá trị nghiệp vụ là một khóa”, hãy giữ **HashMap** với khóa có equals/hashCode đúng và ổn định. **IdentityHashMap** chỉ phù hợp khi yêu cầu chính là **cùng tham chiếu object**; thay nó vào Map theo giá trị sẽ làm mất tính đúng đắn của dữ liệu mà không gây lỗi biên dịch.

Tham khảo chính thức: [HashMap (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [IdentityHashMap (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html), [Object.equals/hashCode (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).
