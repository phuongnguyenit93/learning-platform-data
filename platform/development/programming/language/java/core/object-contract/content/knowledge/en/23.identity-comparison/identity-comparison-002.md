# IdentityHashMap: so sánh cả khóa và giá trị bằng == thay vì equals()

## 1. Ý tưởng cốt lõi

**java.util.IdentityHashMap<K, V>** là một triển khai Map đặc biệt: nó dùng **danh tính tham chiếu (reference identity)** thay cho **bằng nhau theo giá trị (logical equality)** khi so sánh **khóa lẫn giá trị**.

Hai toán tử/quan hệ dễ nhầm:

- **a == b**, khi a và b là tham chiếu đối tượng, nghĩa là cả hai đang trỏ đến **chính cùng một đối tượng** (hoặc cả hai đều null).
- **a.equals(b)** là phép so sánh logic do lớp của a định nghĩa. Ví dụ String.equals xét nội dung ký tự; hai String có nội dung giống nhau vẫn có thể là hai đối tượng riêng.

IdentityHashMap chọn quan hệ thứ nhất. Vì vậy:

- Hai khóa khác tham chiếu **được coi là hai khóa riêng**, dù key1.equals(key2) trả true.
- Tra cứu bằng một đối tượng mới có nội dung giống khóa đã lưu **không tìm thấy** khóa đó nếu tham chiếu khác.
- Các thao tác liên quan đến kiểm tra **giá trị** cũng dùng danh tính; ví dụ containsValue tìm giá trị cùng tham chiếu, không chấp nhận một đối tượng chỉ bằng nhau theo equals.
- Đây là **lựa chọn thiết kế có chủ đích**, không phải HashMap bị cấu hình nhầm.

Điều kiện quan trọng: toán tử == giữa **hai kiểu nguyên thủy** sẽ so sánh giá trị nguyên thủy; trong IdentityHashMap, khóa và giá trị thuộc tham số kiểu K, V nên các phần tử được xử lý ở dạng **tham chiếu đối tượng**. Với Integer hoặc kiểu bao khác, đừng để autoboxing che khuất ranh giới giữa danh tính tham chiếu và giá trị số.

## 2. So sánh với HashMap thông thường

| Hành vi | HashMap<K, V> | IdentityHashMap<K, V> |
| --- | --- | --- |
| Xác định khóa có trùng | Dựa trên equals, phối hợp hashCode | Dựa trên == (cùng tham chiếu) |
| Tìm khóa bằng đối tượng khác nhưng equals true | Có thể tìm thấy, nếu hashCode nhất quán | Không tìm thấy |
| Kiểm tra giá trị với containsValue | Dùng equals (null được xử lý) | Dùng == (cùng tham chiếu) |
| Hai khóa khác tham chiếu nhưng equals true | Được coi là một khóa | Có thể cùng tồn tại thành hai khóa |
| Mục tiêu thường gặp | Bản đồ theo giá trị hoặc định danh logic | Bản đồ theo **đối tượng cụ thể trong bộ nhớ** |
| Hàm băm phục vụ tìm khóa | Dựa trên key.hashCode | Dựa trên cơ chế băm danh tính |
| Có chấp nhận null | Có một khóa null, có thể có giá trị null | Có một khóa null, có thể có giá trị null |

Một ví dụ:

~~~java
String k1 = new String("ID");
String k2 = new String("ID");

System.out.println(k1.equals(k2)); // true
System.out.println(k1 == k2);      // false
~~~

Dùng new String tạo hai đối tượng riêng; vì vậy String.equals trả true còn toán tử == trả false. Với HashMap, k1 và k2 đại diện một khóa logic theo chuỗi "ID"; với IdentityHashMap, chúng là hai khóa danh tính khác nhau.

**Đừng thay ví dụ bằng hai string literal** như "ID" và "ID" rồi kết luận Java luôn coi chuỗi cùng nội dung là cùng đối tượng. String literal có thể tham chiếu cùng đối tượng thông qua string pool, còn những đối tượng được tạo riêng bằng new vẫn khác tham chiếu. Việc so sánh danh tính không thay thế String.equals khi muốn xác định nội dung.

## 3. IdentityHashMap dùng danh tính cho cả khóa và giá trị

### 3.1. Khóa: get, put, containsKey và remove

Giả sử:

~~~java
String first = new String("account");
String second = new String("account");
IdentityHashMap<String, Integer> identities = new IdentityHashMap<>();
identities.put(first, 10);
identities.put(second, 20);
~~~

Các dòng trên là trích đoạn trong ngữ cảnh đã import java.util.IdentityHashMap.

Vì first != second theo toán tử ==, map có **hai entry** dù first.equals(second) là true.

- identities.get(first) trả 10.
- identities.get(second) trả 20.
- identities.get(new String("account")) trả null nếu chưa lưu chính đối tượng vừa tạo, vì đối tượng mới không cùng tham chiếu với first hoặc second.
- identities.containsKey(new String("account")) trả false.
- identities.remove(new String("account")) không xóa hai entry nói trên.

Lưu ý giá trị null trả về từ get có thể nghĩa là **không có khóa** hoặc **khóa tồn tại nhưng chứa giá trị null**. Nếu cần phân biệt, kiểm tra containsKey bằng đúng tham chiếu khóa.

### 3.2. Giá trị: containsValue và những thao tác kiểm tra cặp khóa–giá trị

Trong IdentityHashMap, phép tìm **giá trị** cũng theo ==:

~~~java
String stored = new String("ACTIVE");
IdentityHashMap<String, String> map = new IdentityHashMap<>();
String key = new String("user-1");
map.put(key, stored);

System.out.println(map.containsValue(stored));               // true
System.out.println(map.containsValue(new String("ACTIVE"))); // false
~~~

Đối tượng String mới có cùng nội dung "ACTIVE" nhưng khác tham chiếu, nên containsValue trả false. Đây là điểm dễ bị bỏ quên: **IdentityHashMap không chỉ dùng == với khóa**.

Một số phép kiểm tra trên tập entry hoặc thao tác Map liên quan đồng thời đến khóa và giá trị cũng chịu ảnh hưởng của quy tắc danh tính. Khi cần hành vi cụ thể của một API như remove(key, value), contains, replace hoặc equals giữa hai map, hãy dựa vào tài liệu của IdentityHashMap thay vì áp dụng trực giác về HashMap.

Quan hệ này không có nghĩa **mỗi giá trị chỉ được dùng một lần**: nhiều khóa có thể cùng trỏ tới một đối tượng value; bản đồ vẫn cho phép các entry như vậy.

### 3.3. null

IdentityHashMap hỗ trợ **một khóa null** và các giá trị null. Vì null == null là true, hai lần put(null, value) cập nhật cùng một khóa null thay vì tạo thêm khóa mới.

~~~java
IdentityHashMap<Object, Object> map = new IdentityHashMap<>();
map.put(null, null);
System.out.println(map.containsKey(null));   // true
System.out.println(map.containsValue(null)); // true
~~~

Không được gọi phương thức instance equals trên một tham chiếu null. Quan hệ danh tính == tự xử lý null mà không cần gọi phương thức trên đối tượng đó.

## 4. Chương trình Java 17+ hoàn chỉnh

Lưu thành **IdentityHashMapDemo.java**:

~~~java
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Set;

public class IdentityHashMapDemo {
    static final class Node {
        final String label;

        Node(String label) {
            this.label = label;
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Node other
                    && label.equals(other.label);
        }

        @Override
        public int hashCode() {
            return label.hashCode();
        }
    }

    public static void main(String[] args) {
        String k1 = new String("code");
        String k2 = new String("code");
        String v1 = new String("ready");
        String v2 = new String("ready");

        IdentityHashMap<String, String> identity =
                new IdentityHashMap<>();
        identity.put(k1, v1);
        identity.put(k2, v2);

        Map<String, String> ordinary = new HashMap<>();
        ordinary.put(k1, v1);
        ordinary.put(k2, v2);

        System.out.println("keys equals: " + k1.equals(k2));
        System.out.println("keys ==: " + (k1 == k2));
        System.out.println("values equals: " + v1.equals(v2));
        System.out.println("values ==: " + (v1 == v2));
        System.out.println("IdentityHashMap size: " + identity.size());
        System.out.println("HashMap size: " + ordinary.size());

        System.out.println("identity get same key: "
                + (identity.get(k1) == v1));
        System.out.println("identity get equal new key: "
                + identity.get(new String("code")));
        System.out.println("identity contains equal new key: "
                + identity.containsKey(new String("code")));
        System.out.println("identity contains exact value: "
                + identity.containsValue(v1));
        System.out.println("identity contains equal new value: "
                + identity.containsValue(new String("ready")));
        System.out.println("HashMap contains equal new value: "
                + ordinary.containsValue(new String("ready")));
        System.out.println("HashMap get equal new key: "
                + (ordinary.get(new String("code")) == v2));

        IdentityHashMap<Object, Object> withNull =
                new IdentityHashMap<>();
        withNull.put(null, null);
        System.out.println("null key present: "
                + withNull.containsKey(null));
        System.out.println("null value present: "
                + withNull.containsValue(null));

        Node n1 = new Node("same");
        Node n2 = new Node("same");
        IdentityHashMap<Node, Boolean> visited =
                new IdentityHashMap<>();
        visited.put(n1, Boolean.TRUE);
        visited.put(n2, Boolean.TRUE);

        Set<Node> ordinaryNodes = new HashSet<>();
        ordinaryNodes.add(n1);
        ordinaryNodes.add(n2);

        Set<Node> identitySet =
                Collections.newSetFromMap(
                        new IdentityHashMap<Node, Boolean>());
        identitySet.add(n1);
        identitySet.add(n2);

        System.out.println("nodes equals: " + n1.equals(n2));
        System.out.println("visited identities: " + visited.size());
        System.out.println("ordinary HashSet nodes: "
                + ordinaryNodes.size());
        System.out.println("identity Set nodes: "
                + identitySet.size());
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 IdentityHashMapDemo.java
java IdentityHashMapDemo
~~~

Kết quả stdout:

~~~text
keys equals: true
keys ==: false
values equals: true
values ==: false
IdentityHashMap size: 2
HashMap size: 1
identity get same key: true
identity get equal new key: null
identity contains equal new key: false
identity contains exact value: true
identity contains equal new value: false
HashMap contains equal new value: true
HashMap get equal new key: true
null key present: true
null value present: true
nodes equals: true
visited identities: 2
ordinary HashSet nodes: 1
identity Set nodes: 2
~~~

### Vì sao output như vậy?

1. **Hai khóa k1/k2:** equals theo String là true, nhưng == false. IdentityHashMap có hai entry, HashMap chỉ có một entry và lần put thứ hai ghi đè value của khóa logic "code".
2. **Tra cứu bằng khóa mới:** IdentityHashMap không thấy String mới cùng nội dung. HashMap tìm được vì String.equals và String.hashCode xét nội dung.
3. **Giá trị v1/v2:** hai String bằng nhau theo nội dung nhưng khác tham chiếu. containsValue(v1) true, còn containsValue(new String("ready")) false trên IdentityHashMap; HashMap chấp nhận đối tượng giá trị tương đương theo equals.
4. **null:** cùng một khóa null và một giá trị null được hỗ trợ. containsKey/containsValue phân biệt được null có mặt khi đã put.
5. **Hai Node có cùng label:** equals true và hashCode giống nhau theo định nghĩa của Node, nhưng n1 và n2 là hai đối tượng riêng. HashSet gộp thành một phần tử; IdentityHashMap và một Set tạo từ IdentityHashMap giữ cả hai.

Chương trình tạo một lớp Node cố tình có equals/hashCode theo label, qua đó chứng minh phép so sánh danh tính **độc lập** với tiêu chí bằng nhau do lớp Node cài đặt. Không sử dụng thứ tự duyệt của map trong output nên không phụ thuộc thứ tự duyệt entry.

## 5. Cơ chế băm danh tính và System.identityHashCode

IdentityHashMap vẫn là một cấu trúc băm, nhưng không dùng phương thức **key.hashCode()** làm tiêu chí hash logic để tìm khóa. Nó băm dựa trên **danh tính** của đối tượng; System.identityHashCode(object) là API cung cấp mã băm kiểu danh tính ngay cả khi lớp đã ghi đè hashCode.

~~~java
Object value = new String("same");
int identityHash = System.identityHashCode(value);
int logicalHash = value.hashCode();
~~~

Đây là hai khái niệm khác nhau:

- **value.hashCode()** có thể được lớp tùy biến. String.hashCode được tính dựa trên nội dung nên hai String khác tham chiếu cùng nội dung có cùng logical hash.
- **System.identityHashCode(value)** trả mã băm theo cách triển khai mặc định dựa trên danh tính đối tượng, kể cả khi lớp ghi đè hashCode. Đừng diễn giải nó thành địa chỉ vùng nhớ hay một số định danh toàn cục duy nhất.
- **Hai đối tượng khác nhau vẫn có thể trùng identity hash**: int chỉ có số lượng giá trị hữu hạn. Map xử lý đụng độ băm bằng kiểm tra danh tính == của khóa, chứ không kết luận cùng khóa vì mã băm trùng.
- **Mã identity hash không phải khóa lâu dài để lưu vào cơ sở dữ liệu**: không có bảo đảm tính duy nhất hoặc ổn định giữa các lần chạy JVM.

Không cần tự gọi System.identityHashCode khi sử dụng IdentityHashMap; cấu trúc tự triển khai cơ chế danh tính. Việc tính lại hashCode đã ghi đè trong một class cũng không thể biến HashMap thành IdentityHashMap nếu logic equality vẫn dựa trên equals.

## 6. Vì sao IdentityHashMap khác hợp đồng Map thông thường?

Giao diện Map nói chung định nghĩa các thao tác dựa trên khái niệm khóa **bằng nhau theo equals** và hashCode tương thích. IdentityHashMap được tài liệu Java nêu rõ là triển khai có chủ đích **không tuân theo quy ước đối tượng-bằng-nhau thông thường của Map**: thay thế bằng quan hệ ==.

Điều này gây bất ngờ nếu đổi kiểu cài đặt nhưng giữ cùng API:

~~~java
Map<String, Integer> map = new IdentityHashMap<>();
String saved = new String("item");
map.put(saved, 42);

// Đối tượng khóa mới có cùng nội dung không tra cứu được:
Integer result = map.get(new String("item")); // null
~~~

Code vẫn biên dịch vì IdentityHashMap implements Map, nhưng **ý nghĩa equality đã đổi**. Việc gán cho biến kiểu Map không “chuyển” phép so sánh về equals.

Những hệ quả thực tế:

- Khi so sánh bản đồ, tập entry hoặc thực hiện những thao tác liên quan equals/hashCode với các Map khác loại, có thể gặp kết quả khác kỳ vọng do quy tắc equality không đồng nhất.
- Dữ liệu hai bản đồ có vẻ giống nhau khi in ra không bảo đảm bản đồ có cùng quan hệ khóa/giá trị; không dựa vào toString để xác định bằng nhau.
- Sử dụng IdentityHashMap trong API công khai cần mô tả rõ **danh tính đối tượng** là một phần hợp đồng. Nếu hệ thống mong đợi khóa có thể được tái tạo từ ID/string, hãy dùng HashMap hoặc một cấu trúc Map theo giá trị.
- Không “nâng cấp hiệu năng” HashMap thành IdentityHashMap chỉ vì ít gọi equals; thay đổi cấu trúc có thể làm thay đổi hành vi đúng đắn của chương trình.

## 7. Tình huống nên sử dụng

### 7.1. Ghi nhận các đối tượng đã thăm trong đồ thị

Khi duyệt một object graph có vòng (cycle), hai nút Node khác tham chiếu dù equals true có thể vẫn là **hai nút vật lý cần xử lý riêng**. Một IdentityHashMap<Node, Boolean> là lựa chọn hữu ích để đánh dấu từng thể hiện đã thăm, nhất là nếu equals của Node so sánh theo nội dung hoặc có tính toán đắt đỏ.

~~~java
// Khai báo trong phương thức xử lý đồ thị:
IdentityHashMap<Node, Boolean> visited = new IdentityHashMap<>();

if (visited.put(node, Boolean.TRUE) == null) {
    // Lần đầu gặp chính node tham chiếu này.
    // Duyệt các liên kết của node ở đây.
}
~~~

Điều kiện ở đây chỉ đúng khi ứng dụng thống nhất luôn lưu Boolean.TRUE làm giá trị đánh dấu, **không dùng null làm giá trị**. Nếu một node từng được lưu với giá trị null, put trả null cũng không chứng minh đó là lần đầu; dùng containsKey nếu muốn xử lý chắc chắn cả trường hợp có null value.

### 7.2. Ánh xạ metadata theo từng đối tượng cụ thể

Một trình kiểm tra cấu trúc, bộ theo dõi aliasing, công cụ serialization, hoặc bộ ánh xạ đối tượng nguồn sang đối tượng bản sao đôi khi cần gắn metadata với **từng instance cụ thể**, không phải với mọi instance bằng nhau theo equals.

Nếu hai đối tượng khác nhau cùng biểu diễn nội dung nhưng là hai node riêng trong bộ nhớ, IdentityHashMap lưu được hai bản ghi riêng. Điều đó quan trọng khi cần giữ thông tin về object sharing hoặc phát hiện vòng lặp trong cấu trúc tham chiếu.

### 7.3. Tạo Set theo danh tính

Nếu muốn một tập hợp giữ các phần tử khác tham chiếu kể cả khi equals true, có thể tạo:

~~~java
Set<Node> seen = java.util.Collections.newSetFromMap(
        new java.util.IdentityHashMap<Node, Boolean>());
~~~

Map truyền vào newSetFromMap phải **đang trống**. Set sinh ra dùng quy tắc khóa của IdentityHashMap, tức là danh tính ==. Với một yêu cầu chỉ cần Set theo danh tính, cách này biểu đạt chủ ý rõ hơn dùng IdentityHashMap<Node, Boolean> và thao tác trực tiếp trên value.

## 8. Khi nào không nên dùng?

**Không nên dùng IdentityHashMap** khi khóa đại diện cho giá trị, nội dung hoặc ID logic:

- String là username, mã sản phẩm, URL hoặc khóa cấu hình;
- Integer/Long là số hiệu, ID database hoặc mã trạng thái;
- record hoặc value object được thiết kế với equals/hashCode theo các component;
- khóa có thể tạo lại từ request, JSON, database row hay một bản sao tương đương.

Trong các trường hợp này, HashMap thường hợp lý hơn, vì các đối tượng có cùng giá trị được tìm thấy dù khác tham chiếu.

**Ví dụ dễ sai với boxing:**

~~~java
IdentityHashMap<Integer, String> values = new IdentityHashMap<>();
values.put(Integer.valueOf(1000), "found");

// Không được giả định một Integer mới có cùng trị số
// sẽ cùng tham chiếu với khóa lưu ở trên.
String answer = values.get(Integer.valueOf(1000));
~~~

Các đối tượng wrapper có thể được cache hoặc được tạo mới tùy API và khoảng giá trị, vì vậy không dùng phép == của wrapper hay IdentityHashMap để thể hiện bình đẳng số học. Ví dụ trên chỉ minh họa **rủi ro thiết kế**, không tuyên bố mọi JVM luôn cho answer bằng null.

Khi cần kiểm tra giá trị, dùng equals và Map theo giá trị. Khi cần danh tính, hãy tạo hoặc truyền **đúng đối tượng khóa ban đầu**, không tái tạo một đối tượng mới có dữ liệu tương đương.

## 9. Những đặc điểm triển khai và lưu ý vận hành

- **Không duy trì thứ tự:** IdentityHashMap không đảm bảo thứ tự phần tử theo thời điểm chèn hoặc theo giá trị. Đừng dựa vào thứ tự của keySet, entrySet, values hoặc toString.
- **Không đồng bộ sẵn:** giống HashMap, nó không tự cung cấp đồng bộ cho truy cập/ghi đồng thời. Dùng biện pháp đồng bộ hoặc thiết kế an toàn luồng nếu nhiều thread cập nhật map.
- **initial expectedMaxSize:** constructor nhận số phần tử kỳ vọng để điều chỉnh kích thước nội bộ; không phải giới hạn cứng số entry được phép thêm. Giá trị âm không hợp lệ.
- **Bộ nhớ và vòng đời:** map giữ tham chiếu mạnh tới khóa và giá trị đã lưu. Vì vậy, việc dùng nó như bảng metadata có thể giữ đối tượng sống lâu hơn mong muốn nếu không xóa entry; cần quản lý vòng đời hoặc cân nhắc cấu trúc khác khi cần khóa yếu (weak keys).
- **Thay đổi trường của khóa:** khác HashMap dùng hashCode theo giá trị, IdentityHashMap vẫn xác định cùng khóa theo chính tham chiếu khi trạng thái nội bộ của object thay đổi. Tuy nhiên việc thay đổi object vẫn có thể ảnh hưởng logic chương trình, nên không đồng nghĩa có thể thao tác mutable object tùy ý trong mọi ứng dụng.
- **Không đánh đồng identity hash với tính duy nhất:** collision vẫn có thể xảy ra và danh tính đối tượng được quyết định bằng ==, không bằng việc so sánh hai số identityHashCode.

## 10. Các nhầm lẫn và cách kiểm tra

| Nhầm lẫn | Sự thật |
| --- | --- |
| IdentityHashMap chỉ dùng == cho khóa | Dùng danh tính cho cả khóa **và giá trị** |
| Hai khóa equals true thì put lần sau luôn ghi đè | Chỉ ghi đè khi là **chính cùng tham chiếu khóa** |
| Tên class IdentityHashMap nghĩa là map mã hash duy nhất | identity hash có thể va chạm, == mới xác nhận danh tính |
| Có thể lookup bằng String mới cùng nội dung | Chỉ được nếu tham chiếu trùng; dùng HashMap nếu muốn so nội dung |
| containsValue dùng equals như mọi Map | IdentityHashMap kiểm tra == giữa các giá trị |
| Dùng cùng tham số generic Map thì hai triển khai có cùng equality | Generic xác định kiểu, không thay đổi chính sách bằng nhau |
| null không dùng được với map danh tính | null key và null value vẫn được hỗ trợ |
| Bản đồ danh tính luôn nhanh hơn HashMap | Hiệu năng phụ thuộc kích thước, phân bố hash, cách dùng; chọn theo ngữ nghĩa trước |

**Checklist khi review code:**

1. Bài toán quan tâm cùng đối tượng hay cùng giá trị? Nếu là cùng giá trị, thường không chọn IdentityHashMap.
2. Có phải caller tái tạo khóa từ String/ID không? Nếu có, việc get bằng đối tượng mới sẽ không phù hợp.
3. Các thao tác tìm giá trị có cần equals không? Nếu cần, containsValue của IdentityHashMap sẽ khác dự kiến.
4. Có null key/value không? Phân biệt không có entry với entry chứa null.
5. Map có được trao qua interface Map cho code giả định hợp đồng equals phổ thông không? Nếu có, phải làm rõ hoặc đổi cấu trúc.
6. Nếu dùng làm visited set, có cần phân biệt từng node instance dù Node.equals true không?
7. Có vấn đề vòng đời bộ nhớ hoặc thao tác đa luồng không? Quản lý tham chiếu mạnh, xóa entry và đồng bộ thích hợp.

## 11. Ghi nhớ

**IdentityHashMap đặt câu hỏi “có phải đúng đối tượng này không?”**, không phải “hai đối tượng có giá trị giống nhau không?”. Vì thế:

- Khóa được xác định bằng **==**, không phải equals.
- Giá trị cũng được kiểm tra bằng **==**, điển hình trong containsValue.
- Hai đối tượng khác tham chiếu nhưng equals true được giữ riêng dưới dạng khóa.
- Map phù hợp với object graph, metadata theo instance và phát hiện chia sẻ tham chiếu; không phù hợp làm bản đồ theo ID hoặc nội dung.

Chỉ sử dụng khi **danh tính tham chiếu là chính xác điều nghiệp vụ cần**. Nếu muốn lookup theo giá trị logic, hãy ưu tiên HashMap cùng equals/hashCode đúng hợp đồng.