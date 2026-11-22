# IdentityHashMap: so sánh khóa theo tham chiếu

Hai đối tượng có thể mang cùng dữ liệu nhưng vẫn là hai đối tượng khác nhau. Một bảng tra cứu theo mã khách hàng thường muốn gộp chúng theo giá trị mã. Một công cụ theo dõi các đối tượng trong bộ nhớ lại có thể cần giữ chúng riêng.

`IdentityHashMap` phục vụ yêu cầu thứ hai: đối với khóa, điều kiện khớp là hai tham chiếu cùng trỏ một đối tượng, tức `k1 == k2`. Nó không thay phép so sánh đó bằng `k1.equals(k2)`.

Bài này giải thích khi nào định danh đối tượng là điều cần giữ, cách phân biệt nó với bằng nhau theo giá trị và những hệ quả khi đưa IdentityHashMap qua các API Map thông thường. Ví dụ dùng mã nguồn tương thích Java 17+, không dựa vào thứ tự duyệt hoặc giá trị số của mã băm định danh.

## 1. Ba câu hỏi khác nhau

Giả sử tạo hai khóa có cùng mã:

~~~java
record Key(String code) {}

Key a = new Key("same");
Key b = new Key("same");
Key alias = a;
~~~

Đây là đoạn minh họa một phần. Với bản ghi này:

~~~text
a.equals(b) -> true
a == b      -> false
alias == a  -> true
~~~

Ba kết quả không mâu thuẫn:

- Equals hỏi hai khóa có bằng nhau theo quy tắc giá trị của lớp không.
- Phép == trên tham chiếu hỏi có cùng đối tượng không.
- Alias là tên biến khác giữ cùng tham chiếu, không phải một đối tượng khóa mới.

Có thể hình dung:

~~~text
a --------> đối tượng K1, code = "same"
alias ----> đối tượng K1

b --------> đối tượng K2, code = "same"
~~~

Một HashMap dùng quy tắc bằng nhau theo giá trị có thể coi K1 và K2 là cùng khóa logic. IdentityHashMap coi chúng là hai khóa vì K1 và K2 là hai đối tượng.

### 1.1. Chọn map là chọn ý nghĩa của khóa

Câu hỏi quyết định không phải “map nào lạ hơn hoặc nhanh hơn?”, mà là “hai đối tượng bằng dữ liệu có cần được xem như cùng một khóa không?”.

| Yêu cầu | Ngữ nghĩa phù hợp để xem xét |
|---|---|
| Hai yêu cầu có cùng mã nghiệp vụ tìm cùng dữ liệu | Khóa theo giá trị, thường là map thông thường |
| Theo dõi riêng từng đối tượng đang được xử lý | Khóa theo tham chiếu |
| Sao chép đồ thị, giữ hai nút khác đối tượng dù cùng nhãn | Khóa theo tham chiếu |
| Tra tên người dùng được tạo từ nhiều chuỗi bằng nội dung | Khóa theo giá trị |

IdentityHashMap được thiết kế cho các tình huống chuyên biệt như biến đổi đồ thị đối tượng và bảng liên hệ đối tượng với bản đại diện. Nó không phải cách thay thế mặc định cho HashMap. [Java 17: IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)

### 1.2. Không dùng nó để che lỗi equals hoặc hashCode

Nếu nghiệp vụ muốn các mã bằng nhau là cùng khóa, lỗi triển khai equals/hashCode cần được sửa theo ý nghĩa đó. Chuyển sang IdentityHashMap chỉ để một lỗi băm tạm biến mất sẽ đổi ngữ nghĩa tra cứu.

Sau khi đổi, một đối tượng khóa mới có cùng mã có thể không tìm được dữ liệu. Đó không phải tối ưu miễn phí; ứng dụng đã chọn một quan hệ khóa khác.

## 2. Get, put và remove theo đúng tham chiếu

### 2.1. Hai đối tượng bằng nhau vẫn có hai ánh xạ

Với a và b ở trên:

~~~java
IdentityHashMap<Key, String> byObject = new IdentityHashMap<>();
byObject.put(a, "first");
byObject.put(b, "second");
~~~

ByObject có hai ánh xạ. Get a nhận first, get b nhận second. Get một Key mới có code same không nhận hai giá trị ấy, vì tham chiếu mới không trùng a hoặc b.

Ngược lại, đưa alias vào put là dùng lại đúng khóa a:

~~~java
byObject.put(alias, "updated");
~~~

Số ánh xạ vẫn là hai; giá trị gắn với đối tượng K1 được thay. Biến khác tên không làm xuất hiện khóa thứ ba.

### 2.2. ContainsKey và remove một đối số

ContainsKey cũng hỏi đối tượng tham chiếu đó có đang là khóa không. Remove(key) loại ánh xạ của đúng khóa tham chiếu được truyền.

Tạo một đối tượng mới bằng nội dung rồi gọi remove không có nghĩa “xóa mọi đối tượng cùng mã”. Nếu cần quy tắc ấy, phải dùng cấu trúc hoặc thuật toán biểu diễn rõ quan hệ theo mã.

Chương trình đầy đủ kiểm chứng hai lượt remove: một khóa mới bằng nội dung không xóa được a; alias của a xóa đúng ánh xạ a.

### 2.3. Giá trị null và khóa null

IdentityHashMap cho phép một khóa null và các giá trị null. Put null lần nữa cập nhật ánh xạ của khóa null, không tạo nhiều khóa null riêng.

Get trả null vẫn có hai khả năng: không tìm thấy đúng khóa tham chiếu hoặc khóa ấy đang ánh xạ tới null. Dùng containsKey khi cần phân biệt, trong bối cảnh truy cập được tổ chức phù hợp.

Khả năng có khóa null không làm những tham chiếu không null bằng nhau. Quy tắc == vẫn phân biệt các đối tượng bình thường.

## 3. Mã băm định danh không phải định danh duy nhất

### 3.1. Khác với phương thức hashCode bị ghi đè

`System.identityHashCode(object)` trả mã băm theo cách mặc định của Object ngay cả khi lớp đã ghi đè hashCode. Điều đó phục vụ việc tổ chức tra cứu theo định danh đối tượng. [Java 17: System.identityHashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object))

Không nên suy từ đó rằng:

- Mã băm chính là địa chỉ bộ nhớ.
- Hai đối tượng khác nhau luôn có hai số khác nhau.
- Số ấy là khóa bền vững để lưu và dùng lại ở một lần chạy khác.

Một bảng băm vẫn phải xử lý va chạm; bước kiểm tra đúng khóa là so sánh tham chiếu. Mã băm là công cụ phân bố, không phải phép thay thế cho ==.

Hợp đồng hashCode không yêu cầu mọi đối tượng khác nhau có mã băm khác nhau. [Java 17: Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode())

### 3.2. Không thay IdentityHashMap bằng Map<Integer, V> của identityHashCode

Nếu chỉ dùng số identityHashCode làm khóa trong một HashMap, hai đối tượng va chạm có thể bị coi là cùng khóa số nguyên. Cách đó đã bỏ mất bước phân biệt tham chiếu mà IdentityHashMap cung cấp.

Tương tự, không cần in mã băm cụ thể để kiểm chứng bài học. Các số phụ thuộc lần chạy và không diễn đạt quan hệ nghiệp vụ. Chương trình dùng các phép ==, equals, size và tra cứu có kết quả ổn định.

### 3.3. Đừng dùng đối tượng được chia sẻ tình cờ làm phép thử duy nhất

Chuỗi có thể được dùng chung, và các lớp bao số có thể có cơ chế dùng chung đối tượng trong những trường hợp nhất định. Một ví dụ chỉ dùng các giá trị hằng có thể vô tình đang truyền lại cùng tham chiếu.

Muốn kiểm chứng khác biệt, hãy tạo rõ hai đối tượng mới rồi kiểm tra a != b. Bản ghi Key trong bài làm điều đó trực tiếp.

Các lệnh new String trong phần so giá trị cũng chỉ để tạo hai đối tượng chắc chắn khác tham chiếu cho thí nghiệm. Không phải khuyến nghị tạo chuỗi dư thừa trong mã ứng dụng thông thường.

## 4. Nội bộ bảng băm và ý nghĩa hiệu năng

Tài liệu Java 17 mô tả cách triển khai dạng dò tuyến tính: bảng chứa xen kẽ khóa và giá trị, việc va chạm được xử lý bằng tìm vị trí phù hợp trong bảng.

Mô hình khái niệm:

~~~text
tính vị trí bắt đầu từ mã băm định danh
    ↓
xem vị trí đang xét
    ↓
so khóa bằng ==; nếu chưa khớp thì tiếp tục theo cách dò của bảng
~~~

Sơ đồ này giải thích vì sao vẫn cần kiểm tra tham chiếu dù đã có mã băm. Nó không phải mã nguồn hoặc cam kết bố cục cho mọi phiên bản JVM.

Get và put có hiệu năng thời gian hằng số khi hàm băm định danh phân bố phù hợp. Không được biến điều kiện ấy thành lời hứa thời gian như nhau cho mọi dữ liệu hoặc cho mọi thao tác.

Constructor nhận `expectedMaxSize` là số ánh xạ tối đa dự kiến. Nó không phải số ô mảng được API hứa cấp đúng bằng tham số, cũng không phải giới hạn cứng khiến map ngừng nhận phần tử khi vượt số đó. Chọn quá lớn còn ảnh hưởng duyệt và bộ nhớ. [Java 17: mô hình và tham số của IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)

Không chọn IdentityHashMap chỉ vì nghe nói bảng dò tuyến tính có thể nhanh. Quan hệ khóa phải đúng trước, rồi mới xem xét số liệu của tải công việc.

## 5. Khi đối tượng khóa thay đổi nội dung

Một lớp có thể định nghĩa equals/hashCode theo trường có thể thay đổi. IdentityHashMap vẫn tra theo cùng đối tượng khi trường đó đổi, vì định danh tham chiếu chưa đổi.

Ví dụ trong chương trình:

~~~text
đối tượng mutable có code "old"
put(mutable, "tracked")

đổi mutable.code thành "new"
get(mutable) -> "tracked"
get(new MutableKey("new")) -> không tìm thấy
~~~

Điều này có ích khi đang theo dõi chính đối tượng qua các bước biến đổi. Nhưng không chứng minh IdentityHashMap là cách sửa đúng cho mọi khóa có thể thay đổi.

Nếu mục đích là tra cứu theo mã mới, cần thiết kế khóa theo giá trị ổn định hoặc quản lý thay đổi ánh xạ thích hợp. Theo dõi đối tượng và lập chỉ mục theo trường là hai yêu cầu khác nhau.

IdentityHashMap cũng giữ tham chiếu tới khóa và giá trị như dữ liệu của map; nó không tự trở thành một map khóa yếu chỉ vì tên có chữ Identity. Bảng theo dõi lâu dài cần có vòng đời và cách giải phóng phù hợp với tác vụ.

## 6. Giá trị, góc nhìn và hợp đồng Map thông thường

### 6.1. ContainsValue cũng có ý nghĩa tham chiếu

Với một String value và một String equalValue khác đối tượng nhưng cùng nội dung:

~~~text
value.equals(equalValue) -> true
value == equalValue     -> false
~~~

Nếu map giữ value, containsValue(value) trả true, còn containsValue(equalValue) trả false. Điều này khác kỳ vọng phổ biến từ map theo bằng nhau giá trị.

Không nên suy từ việc get trả một chuỗi có nội dung label rằng mọi đối tượng chuỗi label đều được xem là cùng giá trị tham chiếu trong các thao tác này.

### 6.2. Các view mang theo ngữ nghĩa đặc biệt

KeySet là view theo định danh khóa. Values và các entry của entrySet cũng có các quy tắc so sánh theo tham chiếu được lớp mô tả.

Ví dụ, một entry biểu diễn cùng tham chiếu key và value có thể được tìm thấy trong entrySet. Nếu chỉ thay value bằng một đối tượng bằng nội dung nhưng khác tham chiếu, kết quả kiểm tra có thể khác.

Không coi keySet của IdentityHashMap như một Set giá trị thông thường rồi trộn các thao tác so sánh, removeAll hoặc chuyển đổi mà không đọc hợp đồng của bên nhận. View còn dựa trên map gốc; sửa được hỗ trợ qua view có thể sửa dữ liệu gốc.

### 6.3. Map.equals với map thông thường có thể mất tính đối xứng

IdentityHashMap cố ý khác hợp đồng Map tổng quát vốn dựa vào equals. Vì vậy, so sánh nó với một map thông thường có thể cho hai kết quả khác nhau theo chiều gọi.

Chương trình dùng cùng key tham chiếu nhưng hai value khác đối tượng, bằng nội dung:

~~~text
normal.equals(identity) -> true
identity.equals(normal) -> false
~~~

Normal so giá trị theo equals; identity đòi cặp tham chiếu theo ngữ nghĩa của nó. Đây là hệ quả đã được tài liệu lớp nêu, không phải một cơ chế nên dùng để xây dựng quan hệ bằng nhau chung cho mọi map. [Java 17: IdentityHashMap.equals và các view](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)

Do đó, nên giữ bảng định danh ở ranh giới nội bộ rõ ràng khi tác vụ cần nó. Một tham số kiểu Map không tự bảo đảm mọi map truyền vào có cùng quan hệ khóa.

### 6.4. Điểm khác biệt phiên bản ở các overload có điều kiện

Có một chi tiết thực tế cần tách khỏi quy tắc khóa: Oracle công bố trong JDK 20 rằng remove(key, value) và replace(key, oldValue, newValue) của IdentityHashMap đã được sửa. Các bản trước đó dùng equals khi so giá trị đối số, trái với ngữ nghĩa tham chiếu mà lớp quy định; sau sửa, các phép so ấy dùng định danh đối tượng. [Oracle: ghi chú sửa đổi IdentityHashMap trong JDK 20](https://www.oracle.com/java/technologies/javase/20-relnote-issues.html)

Vì ví dụ hướng tới mã tương thích 17+, bài không dùng hai overload đó để đưa ra stdout chung cho mọi runtime. Khi kiểm tra một môi trường cũ hoặc chuyển phiên bản, cần đọc hành vi phương thức trên bản JDK thực tế.

Điều này không thay đổi điểm đang học: get, containsKey, put và remove(key) phải được hiểu theo đúng tham chiếu khóa. Đồng thời, không nên mở rộng một nhận xét đúng về khóa thành một lời hứa thiếu điều kiện cho mọi overload về giá trị.

## 7. Chuyển đổi map có thể đổi ý nghĩa dữ liệu

### 7.1. Sao chép sang HashMap có thể gộp khóa

IdentityHashMap có thể chứa hai khóa a và b khác tham chiếu nhưng a.equals(b) là true. Sao chép sang HashMap đưa các khóa đó vào quy tắc bằng nhau giá trị của đích, nên có thể chỉ còn một ánh xạ.

Không hứa giá trị của a hoặc b chắc chắn thắng. IdentityHashMap không cam kết thứ tự duyệt, nên không dùng thứ tự tình cờ khi sao chép làm chính sách giải quyết xung đột.

Chương trình chỉ kiểm tra số ánh xạ sau chuyển đổi. Nó cố ý không khẳng định giá trị nào được giữ.

### 7.2. Chuyển ngược không phục hồi thông tin đã mất

Nếu HashMap đã gộp hai đối tượng bằng giá trị thành một ánh xạ, tạo IdentityHashMap từ nó không tự tìm lại đối tượng hoặc ánh xạ bị loại trước đó.

Cần quyết định ngữ nghĩa từ lúc xây dựng bảng, không đợi chuyển kiểu ở cuối rồi mong lấy lại định danh đã không được lưu.

### 7.3. Sao chép identity map không sao chép sâu đối tượng

Tạo một IdentityHashMap mới từ bảng định danh có thể giữ các cặp tham chiếu với cấu trúc ánh xạ riêng. Xóa ở bản sao không tự xóa ở nguồn.

Tuy vậy, các key và value vẫn là những đối tượng được tham chiếu, không phải bản clone sâu. Cần phân biệt “sao chép bảng liên hệ” với “sao chép đồ thị đối tượng mà bảng đang mô tả”.

## 8. Tình huống đúng: sao chép đồ thị giữ quan hệ tham chiếu

### 8.1. Vì sao nhãn bằng nhau không được gộp nút?

Xét đồ thị:

~~~text
root
 ├─ left  (label = "same") ─┐
 └─ right (label = "same") ─┴─> shared ("leaf") ─> root
~~~

Left và right là hai đối tượng khác nhau nhưng được định nghĩa equals theo label nên bằng nhau. Chúng cần có hai bản sao riêng.

Shared là một đối tượng được cả hai nhánh trỏ tới, nên trong đồ thị sao chép cũng phải chỉ có một bản sao shared được dùng chung. Cạnh từ shared quay lại root tạo chu trình; thuật toán phải kết thúc thay vì gọi đệ quy vô hạn.

Như vậy có hai điều đồng thời cần giữ:

- Khác đối tượng ở nguồn không bị gộp chỉ vì bằng nhãn.
- Cùng đối tượng được nhiều nơi tham chiếu phải đi tới cùng một đối tượng bản sao.

Đây là quan hệ hình dạng tham chiếu của đồ thị, không chỉ danh sách nhãn.

### 8.2. Bảng đã xử lý ánh xạ nguồn sang bản sao

Dùng bảng:

~~~text
đúng đối tượng nguồn -> đúng đối tượng bản sao đã tạo
~~~

Mỗi lần sao chép một Node:

1. Nếu nguồn null, trả null.
2. Nếu bảng đã có bản sao cho đúng nguồn đó, dùng lại bản sao.
3. Nếu chưa có, tạo Node đích.
4. Đặt cặp nguồn–đích vào bảng trước khi đi sâu vào các con.
5. Sao chép các cạnh con bằng cùng bảng.

Bước đặt vào bảng trước đệ quy là điều giúp xử lý chu trình. Lúc quay về root, bảng đã có root đích để trả lại.

Trong chương trình, mọi value của bảng seen là Node bản sao khác null, nên get trả null được dùng làm dấu chưa xử lý. Đó là điều kiện riêng của thuật toán này; không áp nó cho một map tùy ý có thể lưu value null.

### 8.3. Phạm vi của ví dụ

Hàm copy chỉ sao chép lớp Node được định nghĩa trong bài và danh sách cạnh của nó. Nó không phải thư viện sao chép sâu mọi đối tượng Java, không tự xử lý mọi tài nguyên hoặc mọi chính sách chia sẻ.

Nguồn được xem là ổn định trong lúc sao chép. Với đồ thị rất sâu hoặc nguồn đang được sửa cạnh tranh, thiết kế duyệt và chính sách truy cập cần được tổ chức theo yêu cầu thực tế.

## 9. Chương trình Java đầy đủ

Lưu toàn bộ mã sau vào `IdentityKeysDemo.java`. Chương trình không in bản đồ theo thứ tự duyệt và không in các số identity hash, nên stdout không phụ thuộc những chi tiết không được cam kết.

Nó dùng các kiểu lồng trong một lớp để có thể biên dịch từ một tệp. Ví dụ bao gồm cả HashMap để đối chiếu, nhưng không chọn IdentityHashMap dựa vào kết quả thời gian chạy.

~~~java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;

public class IdentityKeysDemo {
    record Key(String code) {}

    static final class MutableKey {
        String code;

        MutableKey(String code) {
            this.code = code;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    static final class Node {
        final String label;
        final List<Node> children = new ArrayList<>();

        Node(String label) {
            this.label = label;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Node node && label.equals(node.label);
        }

        @Override
        public int hashCode() {
            return label.hashCode();
        }
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected identity result");
        }
    }

    private static Node copy(Node source, IdentityHashMap<Node, Node> seen) {
        if (source == null) {
            return null;
        }
        Node existing = seen.get(source);
        if (existing != null) {
            return existing;
        }
        Node target = new Node(source.label);
        seen.put(source, target);
        for (Node child : source.children) {
            target.children.add(copy(child, seen));
        }
        return target;
    }

    public static void main(String[] args) {
        Key a = new Key("same");
        Key b = new Key("same");
        Key alias = a;
        require(a.equals(b) && a != b && alias == a);
        System.out.println("keys/equals=" + a.equals(b)
                + ", sameReference=" + (a == b)
                + ", aliasSame=" + (alias == a));

        Map<Key, String> ordinary = new HashMap<>();
        ordinary.put(a, "first");
        ordinary.put(b, "second");
        require(ordinary.size() == 1);
        System.out.println("hash/size=" + ordinary.size()
                + ", getA=" + ordinary.get(a));

        IdentityHashMap<Key, String> identity = new IdentityHashMap<>();
        identity.put(a, "first");
        identity.put(b, "second");
        require(identity.size() == 2);
        System.out.println("identity/size=" + identity.size()
                + ", getA=" + identity.get(a) + ", getB=" + identity.get(b));
        Key equalNew = new Key("same");
        System.out.println("identity/equalNewContains="
                + identity.containsKey(equalNew)
                + ", get=" + identity.get(equalNew));
        String previous = identity.put(alias, "updated");
        require(identity.size() == 2 && previous.equals("first"));
        System.out.println("identity/aliasPrevious=" + previous
                + ", size=" + identity.size());
        System.out.println("identity/removeEqualNew=" + identity.remove(equalNew)
                + ", size=" + identity.size());
        System.out.println("identity/removeAlias=" + identity.remove(alias)
                + ", size=" + identity.size());

        IdentityHashMap<Key, Integer> distinct = new IdentityHashMap<>();
        distinct.put(a, 1);
        distinct.put(b, 2);
        Map<Key, Integer> hashCopy = new HashMap<>(distinct);
        IdentityHashMap<Key, Integer> identityFromHash =
                new IdentityHashMap<>(hashCopy);
        require(distinct.size() == 2 && hashCopy.size() == 1
                && identityFromHash.size() == 1);
        System.out.println("conversion/identity=" + distinct.size()
                + ", hashCopy=" + hashCopy.size()
                + ", identityFromHash=" + identityFromHash.size());
        IdentityHashMap<Key, Integer> shallowCopy =
                new IdentityHashMap<>(distinct);
        shallowCopy.remove(a);
        require(distinct.size() == 2 && shallowCopy.size() == 1);
        System.out.println("copy/sourceSize=" + distinct.size()
                + ", copySize=" + shallowCopy.size());

        Object handle = new Object();
        String value = new String("label");
        String equalValue = new String("label");
        IdentityHashMap<Object, String> values = new IdentityHashMap<>();
        values.put(handle, value);
        System.out.println("values/equals=" + value.equals(equalValue)
                + ", sameContains=" + values.containsValue(value)
                + ", equalContains=" + values.containsValue(equalValue));
        System.out.println("entries/sameReferences="
                + values.entrySet().contains(
                        new AbstractMap.SimpleEntry<>(handle, value))
                + ", equalValue=" + values.entrySet().contains(
                        new AbstractMap.SimpleEntry<>(handle, equalValue)));
        Map<Object, String> normal = new HashMap<>();
        normal.put(handle, equalValue);
        require(normal.equals(values) && !values.equals(normal));
        System.out.println("equals/normalToIdentity=" + normal.equals(values)
                + ", identityToNormal=" + values.equals(normal));

        IdentityHashMap<Object, String> nullable = new IdentityHashMap<>();
        Object presentWithNull = new Object();
        nullable.put(null, "null-key");
        nullable.put(presentWithNull, null);
        System.out.println("null/keyValue=" + nullable.get(null)
                + ", present=" + nullable.containsKey(presentWithNull)
                + ", mappedValue=" + nullable.get(presentWithNull));

        MutableKey mutable = new MutableKey("old");
        IdentityHashMap<MutableKey, String> tracking = new IdentityHashMap<>();
        tracking.put(mutable, "tracked");
        mutable.code = "new";
        require(tracking.get(mutable).equals("tracked"));
        System.out.println("mutable/sameReference=" + tracking.get(mutable)
                + ", equalNew=" + tracking.get(new MutableKey("new")));

        Node root = new Node("root");
        Node left = new Node("same");
        Node right = new Node("same");
        Node shared = new Node("leaf");
        root.children.add(left);
        root.children.add(right);
        left.children.add(shared);
        right.children.add(shared);
        shared.children.add(root);

        IdentityHashMap<Node, Node> seen = new IdentityHashMap<>();
        Node copiedRoot = copy(root, seen);
        Node copiedLeft = copiedRoot.children.get(0);
        Node copiedRight = copiedRoot.children.get(1);
        Node copiedShared = copiedLeft.children.get(0);
        require(left.equals(right) && copiedLeft != copiedRight);
        require(copiedShared == copiedRight.children.get(0));
        require(copiedShared.children.get(0) == copiedRoot);
        require(copiedRoot != root && seen.size() == 4);
        System.out.println("graph/equalSources=" + left.equals(right)
                + ", distinctCopies=" + (copiedLeft != copiedRight));
        System.out.println("graph/sharedChild="
                + (copiedShared == copiedRight.children.get(0)));
        System.out.println("graph/cycleReturnsCopiedRoot="
                + (copiedShared.children.get(0) == copiedRoot));
        System.out.println("graph/sourceSeparate=" + (copiedRoot != root)
                + ", memoSize=" + seen.size());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 IdentityKeysDemo.java
java IdentityKeysDemo
~~~

Stdout của lần chạy kiểm chứng:

~~~text
keys/equals=true, sameReference=false, aliasSame=true
hash/size=1, getA=second
identity/size=2, getA=first, getB=second
identity/equalNewContains=false, get=null
identity/aliasPrevious=first, size=2
identity/removeEqualNew=null, size=2
identity/removeAlias=updated, size=1
conversion/identity=2, hashCopy=1, identityFromHash=1
copy/sourceSize=2, copySize=1
values/equals=true, sameContains=true, equalContains=false
entries/sameReferences=true, equalValue=false
equals/normalToIdentity=true, identityToNormal=false
null/keyValue=null-key, present=true, mappedValue=null
mutable/sameReference=tracked, equalNew=null
graph/equalSources=true, distinctCopies=true
graph/sharedChild=true
graph/cycleReturnsCopiedRoot=true
graph/sourceSeparate=true, memoSize=4
~~~

Mã đã biên dịch với `--release 17` và chạy thành công. Tùy chọn release xác định mức API và mã đích tương thích; nó không khẳng định JVM thực thi là đúng bản JDK 17.

## 10. Đọc các nhóm kết quả

### 10.1. Khóa bằng giá trị và alias

HashMap giữ một ánh xạ sau hai lần put với a và b bằng nội dung. IdentityHashMap giữ hai. Khóa mới bằng nội dung không tìm thấy ánh xạ identity.

Alias cập nhật ánh xạ a, không tăng size. Remove khóa mới không xóa gì; remove alias xóa đúng ánh xạ a. Các bước này tách được khái niệm một biến mới khỏi một đối tượng mới.

### 10.2. Chuyển đổi và sao chép

Chuyển hai khóa định danh bằng giá trị sang HashMap chỉ còn một ánh xạ. Tạo identity map từ kết quả ấy vẫn chỉ có một. Bài không in hoặc khẳng định người thắng của xung đột.

Bản sao identity có cấu trúc riêng nên xóa a khỏi copy không làm nguồn mất a. Nó vẫn dùng các tham chiếu khóa tương ứng, không tự tạo a và b mới.

### 10.3. Giá trị và phép so sánh map

Hai String value bằng nội dung nhưng khác đối tượng cho kết quả containsValue khác nhau. EntrySet cũng phân biệt hai cặp có cùng key nhưng value khác tham chiếu.

Dòng equals thể hiện sự bất đối xứng khi trộn ngữ nghĩa identity với map thông thường. Nó nhắc rằng tính phù hợp với một API không thể chỉ suy từ việc đối tượng triển khai Map.

### 10.4. Null và trường có thể đổi

Map có thể giữ khóa null và một ánh xạ khác có value null. ContainsKey giúp phân biệt ánh xạ tồn tại với vắng.

Đổi code của mutable không làm nó thành một đối tượng khác. Bảng vẫn tìm được bằng đúng tham chiếu; một đối tượng mới cùng code không khớp.

### 10.5. Đồ thị

Hai nguồn cùng label được sao chép thành hai Node riêng. Hai nhánh dùng cùng bản sao shared, và cạnh vòng quay về copiedRoot.

Seen có bốn cặp, tương ứng bốn đối tượng nguồn root, left, right, shared. Nếu dùng quan hệ equals theo label cho bảng ghi nhớ, left và right có thể bị gộp sai dù chúng cần giữ hai định danh.

## 11. Giới hạn khi sử dụng trong ứng dụng

IdentityHashMap không cam kết thứ tự duyệt và không tự đồng bộ hóa. Nếu cần hiển thị có thứ tự, phải tạo kết quả theo một quy tắc rõ ràng; không đoán thứ tự từ mã băm hoặc thứ tự thêm.

Iterator fail-fast là cơ chế phát hiện một số sửa đổi không phù hợp theo nỗ lực tốt nhất. Nó không thay cho cơ chế phối hợp nhiều luồng và không được dùng làm điều kiện tính đúng.

Với bảng ghi nhớ phục vụ một lần biến đổi đồ thị, giữ nó cục bộ theo vòng đời tác vụ thường giúp ranh giới ý nghĩa rõ ràng: nó nói về định danh các đối tượng của tác vụ ấy. Không tự đưa bảng đó thành một chỉ mục nghiệp vụ lâu dài nếu hệ thống cần tra theo mã giá trị.

## 12. Các lỗi dễ gặp

| Lỗi | Cách hiểu đúng |
|---|---|
| Hai đối tượng equals thì luôn là cùng khóa | IdentityHashMap xét == cho khóa |
| Hai tên biến khác nhau là hai khóa | Hai biến có thể cùng tham chiếu |
| Tạo lại một chuỗi cùng nội dung để get là đủ | Phải có đúng tham chiếu nếu dùng làm khóa identity |
| IdentityHashMap sửa được mọi lỗi khóa mutable | Nó đổi quan hệ khóa; chỉ đúng khi định danh đối tượng là yêu cầu |
| IdentityHashCode luôn là số duy nhất | Mã băm có thể va chạm; vẫn cần so tham chiếu |
| Identity hash là địa chỉ hoặc mã bền vững | API không hứa như vậy |
| Map<Integer,V> của identity hash thay được identity map | Nó mất bước phân biệt tham chiếu khi mã va chạm |
| Map.equals luôn đối xứng khi trộn mọi map | Ngữ nghĩa identity có thể phá kỳ vọng với map thông thường |
| Chuyển sang HashMap giữ nguyên mọi ánh xạ | Các khóa equals có thể bị gộp |
| Chuyển ngược phục hồi các khóa đã gộp | Thông tin đã mất không tự được tái tạo |
| Sao chép bảng là sao chép sâu các đối tượng | Cấu trúc mới vẫn có thể giữ cùng tham chiếu |
| Đặt memo sau khi sao chép con vẫn xử lý được mọi chu trình | Cần ghi nhận bản sao trước khi đi sâu để dùng lại khi gặp vòng |
| Mọi overload đã giống nhau trên mọi JDK cũ | Phải xét các sửa đổi phiên bản đã công bố |
| Không có CME nghĩa là an toàn đồng thời | Fail-fast không phải cơ chế đồng bộ hóa |

## 13. Thực hành và lời giải

### Bài 1. Hai đối tượng, ba biến

A và B là hai Key mới có cùng code; C được gán bằng A. Put cả A, B, C vào IdentityHashMap. Có tối đa bao nhiêu ánh xạ của ba lần put này?

**Lời giải:** Hai, nếu A và B khác tham chiếu. C dùng lại khóa A nên cập nhật cùng ánh xạ. Số biến không quyết định số định danh khóa.

### Bài 2. Tra cứu theo mã nghiệp vụ

Một dịch vụ tạo đối tượng Key mới cho mỗi yêu cầu, nhưng cùng code phải tra cùng thông tin. IdentityHashMap có phù hợp chỉ vì các đối tượng Key là bất biến không?

**Lời giải:** Không. Tính bất biến không thay đổi việc hai đối tượng mới khác tham chiếu. Yêu cầu đang là tra theo giá trị code, cần cấu trúc và quy tắc equals/hashCode phù hợp.

### Bài 3. Mã băm định danh

Hai đối tượng có cùng identityHashCode. Có được kết luận chúng là cùng đối tượng không? Có nên dùng số ấy làm khóa duy nhất của bảng thay cho hai tham chiếu không?

**Lời giải:** Không. Va chạm mã băm không chứng minh cùng định danh. Cần giữ bước so tham chiếu; một HashMap chỉ có khóa số đã không còn phân biệt được hai nguồn chỉ từ số ấy.

### Bài 4. Chuyển sang map thông thường

IdentityMap chứa hai khóa khác đối tượng nhưng equals và có giá trị khác nhau. Sao chép sang HashMap rồi sao chép ngược có bảo toàn hai ánh xạ không? Có thể hứa giá trị nào thắng không?

**Lời giải:** Không bảo toàn: HashMap có thể gộp thành một khóa logic, chuyển ngược không phục hồi thông tin. Không hứa người thắng dựa trên thứ tự duyệt không được cam kết của nguồn; nếu cần giải quyết xung đột phải có chính sách rõ ràng.

### Bài 5. Memo trong đồ thị

Hai Node cùng label nhưng khác đối tượng đều trỏ tới cùng một leaf. Khi sao chép, cần bao nhiêu bản sao cho hai Node và leaf? Vì sao bảng theo equals của label không đáp ứng đúng?

**Lời giải:** Cần hai bản sao riêng cho hai Node và một bản sao leaf dùng chung. Equals theo label có thể gộp hai Node khác định danh, làm sai quan hệ đồ thị.

### Bài 6. Ghi memo trước hay sau?

Đồ thị có A trỏ B, B trỏ A. Vì sao phải đặt cặp nguồn–đích vào memo trước khi sao chép các con?

**Lời giải:** Khi duyệt từ B quay về A, thuật toán phải tìm thấy A đích đã được tạo. Nếu chưa ghi nhận, nó có thể tiếp tục tạo và đi sâu lặp lại thay vì đóng cạnh vòng về bản sao đã có.

### Bài 7. Null và ánh xạ tồn tại

Get trả null với một khóa tham chiếu. Điều đó có đủ chứng minh khóa chưa có không?

**Lời giải:** Không. Khóa có thể đang ánh xạ tới null. ContainsKey phân biệt trong bối cảnh truy cập hợp lệ. Với thuật toán memo chỉ lưu bản sao khác null, điều kiện riêng ấy mới cho phép dùng null làm dấu chưa xử lý.

### Bài 8. Sự cố khi so map

Một map thông thường bằng nội dung với identity map theo một chiều gọi equals nhưng không theo chiều ngược. Có nên “sửa” bằng cách so chuỗi toString của hai map không?

**Lời giải:** Không. ToString không thiết lập quan hệ bằng nhau đúng, thứ tự identity map không được cam kết và nội dung in có thể giống dù tham chiếu khác. Cần chọn quan hệ so sánh mà bài toán thực sự yêu cầu và kiểm tra dữ liệu theo quan hệ ấy.

## 14. Tự xác định ranh giới định danh

Trước khi dùng IdentityHashMap, hãy mô tả được hai đối tượng bằng nội dung nhưng khác tham chiếu có phải giữ hai ánh xạ hay không. Sau đó xác định cách tạo khóa, vòng đời bảng và các API sẽ nhận bảng hoặc view của nó.

Khi định danh đối tượng là yêu cầu, phép == là ý nghĩa cốt lõi của khóa. Khi giá trị nghiệp vụ là yêu cầu, giữ nguyên ngữ nghĩa theo giá trị sẽ giúp tránh biến một cấu trúc chuyên biệt thành nguồn lỗi tra cứu.
