# Kiểm thử tra cứu bằng đối tượng bằng nhau trong HashMap và HashSet

## 1. Mục tiêu học tập

Giả sử một hệ thống lưu trạng thái tài khoản trong HashMap theo khóa gồm mã tổ chức và mã người dùng. Khi đã lưu với đối tượng **new UserKey("team-a", 42)**, hệ thống phải tra cứu được bằng **một đối tượng UserKey khác có đúng các giá trị đó**. Tương tự, HashSet phải nhận ra hai đối tượng khác tham chiếu nhưng bằng nhau về mặt khóa logic là cùng một phần tử.

Bài kiểm thử không dừng ở **map.get()** hoặc **set.contains()** đơn lẻ; cần chứng minh mối quan hệ giữa **identity**, **equals()**, **hashCode()**, hành vi tra cứu/cập nhật và tính duy nhất, đồng thời xác nhận các khóa khác nhau thực sự không bị nhận nhầm.

Các khái niệm cần phân biệt:

- **a == b:** hai biến tham chiếu cùng một object.
- **a.equals(b):** hai object được xem là bằng nhau theo hợp đồng equality do lớp định nghĩa.
- **a.hashCode():** số nguyên dùng phục vụ phân vùng hash khi tổ chức dữ liệu. Hai đối tượng bằng nhau theo equals() bắt buộc trả cùng hashCode().
- **Khóa logic:** danh tính nghiệp vụ do các field tham gia equals/hashCode xác định. Hai object riêng biệt có thể biểu diễn cùng khóa logic.

Một chương trình chỉ thêm một đối tượng a rồi tra cứu lại cũng bằng **chính a** là kiểm thử yếu: lớp kế thừa equals/hashCode mặc định của Object cũng có thể vượt qua. Hãy luôn tạo **b** độc lập với a nhưng bằng nhau theo giá trị.

## 2. HashMap và HashSet nhận diện đối tượng bằng nhau thế nào?

**HashMap<K, V>** dùng hash của key để xác định vùng tìm kiếm phù hợp và so sánh key bằng quan hệ equals để tìm entry. Khi **put(a, "ACTIVE")**, lệnh **get(b)** và **containsKey(b)** có thể tìm đúng entry nếu b bằng a và đáp ứng hợp đồng hash. Khi tiếp tục **put(b, "UPDATED")**, Map phải cập nhật cùng khóa logic, không sinh một entry mới.

**HashSet<E>** lưu các phần tử duy nhất theo equality/hash. Sau **add(a)**, lệnh **contains(b)** phải trả true và **add(b)** phải trả false nếu b bằng a; kích thước Set không tăng.

| Phép kiểm | Kết quả mong đợi với a và b bằng nhau nhưng khác tham chiếu |
| --- | --- |
| **a != b** | true |
| **a.equals(b)** và **b.equals(a)** | true |
| **a.hashCode() == b.hashCode()** | true |
| **map.put(a, v); map.get(b)** | v |
| **map.containsKey(b)** | true |
| **map.put(b, v2)** | cập nhật value cho cùng khóa logic; Map vẫn có 1 entry nếu ban đầu rỗng |
| **set.add(a); set.contains(b)** | true khi contains |
| **set.add(a); set.add(b)** | lần thêm đầu true, lần sau false; Set vẫn có 1 phần tử |

Không được kết luận hai object bằng nhau chỉ vì hash trùng: **collision được phép**. HashMap/HashSet phải phân biệt hai đối tượng có equals() false dù hashCode bằng nhau.

## 3. Hợp đồng equals() và hashCode()

**equals()** phải thỏa các điều kiện, giả sử trạng thái có liên quan không thay đổi:

1. **Reflexive:** a.equals(a) là true.
2. **Symmetric:** a.equals(b) và b.equals(a) cho cùng kết quả.
3. **Transitive:** nếu a bằng b, b bằng c, thì a bằng c.
4. **Consistent:** so sánh lặp lại trên những object có trạng thái không đổi cho cùng kết quả.
5. **Non-null:** a.equals(null) là false với a khác null.

**hashCode()** yêu cầu:

- Lặp lại trên cùng đối tượng với thông tin equality không đổi trong một lần thực thi phải trả cùng kết quả.
- **Nếu a.equals(b) == true thì a.hashCode() == b.hashCode().**
- Nếu a không bằng b, hash có thể trùng hoặc khác; không bắt buộc khác nhau.

Nếu override equals() để so sánh theo field nhưng không override hashCode() tương thích, hai instance có thể equals true nhưng có hash khác nhau, dẫn tới tra cứu lỗi trong HashMap/HashSet. Hãy dùng cùng các thành phần xác định khóa logic cho cả hai phương thức. Với khóa cần ổn định lâu dài trong collection, nên chọn dữ liệu immutable; nếu field tham gia hash bị sửa sau khi thêm, collection không tự tổ chức lại theo hash mới.

## 4. Chương trình Java 17+ chạy độc lập

Lớp UserKey được khai báo **final**, trường **tenantId** và **userId** cũng final. Phương thức equals() so sánh hai trường; hashCode() tính từ cùng hai trường. Mã dưới đây kiểm tra bằng một object mới cùng giá trị, chèn Map/Set, cập nhật bằng object tương đương, và từ chối khóa khác.

Tạo tệp **EqualKeyLookupDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class EqualKeyLookupDemo {
    static final class UserKey {
        private final String tenantId;
        private final int userId;

        UserKey(String tenantId, int userId) {
            this.tenantId = Objects.requireNonNull(tenantId);
            this.userId = userId;
        }

        @Override
        public boolean equals(Object object) {
            if (this == object) {
                return true;
            }
            if (!(object instanceof UserKey other)) {
                return false;
            }
            return userId == other.userId
                    && tenantId.equals(other.tenantId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, userId);
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        UserKey first = new UserKey("team-a", 42);
        UserKey equivalent = new UserKey("team-a", 42);
        UserKey different = new UserKey("team-a", 43);

        System.out.println("Khác tham chiếu: "
                + (first != equivalent));
        System.out.println("Bằng nhau theo equals: "
                + first.equals(equivalent));
        System.out.println("Hash bằng nhau: "
                + (first.hashCode() == equivalent.hashCode()));

        require(first != equivalent, "Phải tạo hai instance khác nhau");
        require(first.equals(equivalent)
                        && equivalent.equals(first),
                "equals phải nhất quán hai chiều");
        require(first.hashCode() == equivalent.hashCode(),
                "Đối tượng bằng nhau phải cùng hash");

        Map<UserKey, String> map = new HashMap<>();
        map.put(first, "ACTIVE");

        System.out.println("Map tra bằng đối tượng khác: "
                + map.get(equivalent));
        System.out.println("Map containsKey: "
                + map.containsKey(equivalent));

        require("ACTIVE".equals(map.get(equivalent)),
                "Map không tìm được khóa bằng nhau");
        require(map.containsKey(equivalent),
                "Map không nhận ra khóa bằng nhau");

        String oldValue = map.put(equivalent, "UPDATED");
        System.out.println("Giá trị cũ khi put: " + oldValue);
        System.out.println("Số entry của Map: " + map.size());
        System.out.println("Giá trị bằng khóa ban đầu: "
                + map.get(first));

        require("ACTIVE".equals(oldValue), "Put không cập nhật đúng");
        require(map.size() == 1, "Map sinh khóa logic trùng");
        require("UPDATED".equals(map.get(first)),
                "Map không trả value đã cập nhật");

        Set<UserKey> set = new HashSet<>();
        boolean addedFirst = set.add(first);
        boolean addedAgain = set.add(equivalent);

        System.out.println("Set thêm ban đầu: " + addedFirst);
        System.out.println("Set thêm đối tượng bằng nhau: "
                + addedAgain);
        System.out.println("Set contains: "
                + set.contains(equivalent));
        System.out.println("Số phần tử của Set: " + set.size());

        require(addedFirst && !addedAgain,
                "Set phải ngăn phần tử bằng nhau");
        require(set.contains(equivalent) && set.size() == 1,
                "Set không tìm thấy phần tử tương đương");

        System.out.println("Map chứa khóa khác: "
                + map.containsKey(different));
        System.out.println("Set chứa khóa khác: "
                + set.contains(different));

        require(!map.containsKey(different), "Map nhầm khóa khác");
        require(!set.contains(different), "Set nhầm khóa khác");

        System.out.println("Tất cả kiểm thử thành công.");
    }
}
~~~

Lệnh biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 EqualKeyLookupDemo.java
java EqualKeyLookupDemo
~~~

**Stdout mong đợi chính xác:**

~~~text
Khác tham chiếu: true
Bằng nhau theo equals: true
Hash bằng nhau: true
Map tra bằng đối tượng khác: ACTIVE
Map containsKey: true
Giá trị cũ khi put: ACTIVE
Số entry của Map: 1
Giá trị bằng khóa ban đầu: UPDATED
Set thêm ban đầu: true
Set thêm đối tượng bằng nhau: false
Set contains: true
Số phần tử của Set: 1
Map chứa khóa khác: false
Set chứa khóa khác: false
Tất cả kiểm thử thành công.
~~~

Giải thích: **first** và **equivalent** có identity khác, nhưng bằng nhau theo đúng hai field làm khóa. HashMap tra cứu được bằng equivalent, cập nhật bằng equivalent giữ đúng một entry; HashSet nhận ra giá trị tương đương và không thêm trùng. **different** không bằng first vì userId khác. Hàm **require(...)** ném AssertionError ngay khi điều kiện không đạt, khác với câu lệnh **assert** của Java có thể bị vô hiệu hóa khi thiếu cờ **-ea**.

Bài kiểm thử không in toàn bộ HashMap/HashSet để so thứ tự phần tử vì **không có bảo đảm về thứ tự lặp** của hai collection này.

## 5. Viết kiểm thử JUnit Jupiter (JUnit 5)

Trong ứng dụng thực tế, hãy dùng assertion có thông báo rõ ràng. Đoạn dưới là **mã test bổ sung**, yêu cầu dependency JUnit 5 và lớp EqualKeyLookupDemo ở cùng package, không phải chương trình độc lập chạy chỉ bằng lệnh java.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class EqualKeyLookupDemoTest {

    @Test
    void equalDistinctKeysFindOneMapEntry() {
        var a = new EqualKeyLookupDemo.UserKey("team-a", 42);
        var b = new EqualKeyLookupDemo.UserKey("team-a", 42);

        assertNotSame(a, b);
        assertEquals(a, b);
        assertEquals(b, a);
        assertEquals(a.hashCode(), b.hashCode());

        Map<EqualKeyLookupDemo.UserKey, String> map = new HashMap<>();
        map.put(a, "ACTIVE");

        assertTrue(map.containsKey(b));
        assertEquals("ACTIVE", map.get(b));
        assertEquals("ACTIVE", map.put(b, "UPDATED"));
        assertEquals(1, map.size());
        assertEquals("UPDATED", map.get(a));
    }

    @Test
    void equalDistinctElementsCountOnceInSet() {
        var a = new EqualKeyLookupDemo.UserKey("team-a", 42);
        var b = new EqualKeyLookupDemo.UserKey("team-a", 42);

        Set<EqualKeyLookupDemo.UserKey> set = new HashSet<>();
        assertTrue(set.add(a));
        assertTrue(set.contains(b));
        assertFalse(set.add(b));
        assertEquals(1, set.size());
    }

    @Test
    void differentKeysDoNotMatch() {
        var a = new EqualKeyLookupDemo.UserKey("team-a", 42);
        var otherId = new EqualKeyLookupDemo.UserKey("team-a", 43);
        var otherTenant = new EqualKeyLookupDemo.UserKey("team-b", 42);

        assertNotEquals(a, otherId);
        assertNotEquals(a, otherTenant);
        assertNotEquals(a, null);

        Map<EqualKeyLookupDemo.UserKey, String> map = new HashMap<>();
        map.put(a, "ACTIVE");
        assertFalse(map.containsKey(otherId));
        assertFalse(map.containsKey(otherTenant));

        Set<EqualKeyLookupDemo.UserKey> set = new HashSet<>();
        set.add(a);
        assertFalse(set.contains(otherId));
        assertFalse(set.contains(otherTenant));
    }

    @Test
    void equalityContract() {
        var a = new EqualKeyLookupDemo.UserKey("team-a", 42);
        var b = new EqualKeyLookupDemo.UserKey("team-a", 42);
        var c = new EqualKeyLookupDemo.UserKey("team-a", 42);

        assertEquals(a, a);
        assertEquals(a, b);
        assertEquals(b, a);
        assertEquals(b, c);
        assertEquals(a, c);
        assertEquals(a.hashCode(), b.hashCode());
        assertEquals(b.hashCode(), c.hashCode());
    }
}
~~~

Khi xây dựng test riêng cho class của dự án, thay UserKey bằng khóa thực tế. Nếu khóa gồm nhiều field, phải kiểm thử ít nhất một trường hợp **khác ở từng field tham gia equality**; nếu không, equals() quá rộng có thể xem nhầm hai khóa khác nhau là cùng khóa.

## 6. Phân biệt collision với equality

Hai đối tượng **không bằng nhau nhưng có cùng hashCode** vẫn phải được HashMap/HashSet lưu và tra cứu độc lập. Có thể dựng collision cố ý bằng một lớp mà hashCode() luôn trả 1. Điều này **vẫn thỏa hợp đồng** (các khóa bằng nhau chắc chắn có hash như nhau) nhưng kém hiệu năng nghiêm trọng với tập lớn.

Ví dụ bổ sung minh họa, giả định có import **java.util.Map** và **java.util.HashMap**:

~~~java
record CollisionKey(int id) {
    @Override
    public int hashCode() {
        return 1;
    }
}

Map<CollisionKey, String> map = new HashMap<>();
map.put(new CollisionKey(1), "ONE");
map.put(new CollisionKey(2), "TWO");

// Hai khóa có hash trùng nhưng equals khác.
if (!"ONE".equals(map.get(new CollisionKey(1)))
        || !"TWO".equals(map.get(new CollisionKey(2)))
        || map.size() != 2) {
    throw new AssertionError("Hash collision bị xử lý sai");
}
~~~

Đoạn minh họa này không phải tệp Java độc lập: đặt record và các statement vào ngữ cảnh khai báo phù hợp, chẳng hạn record ở mức lớp và các statement trong test method. Một collision không chứng minh lỗi equals/hashCode. **Không dùng hash hằng trong ứng dụng sản xuất** chỉ để đơn giản hóa việc tính hash.

## 7. Các tình huống lỗi thường gặp

### 7.1. Override equals() mà quên hashCode()

Giả sử lớp chỉ ghi đè equals() để so sánh tenantId và userId nhưng để hashCode() kế thừa Object. Hai instance khác nhau có thể equals true nhưng hashCode khác, khiến HashMap/HashSet tìm sai vùng và trả kết quả không mong muốn.

**Không nên cố tình viết test luôn mong đợi lỗi tra cứu** cho kiểu lớp hỏng này, vì identity hash có thể trùng tình cờ; sự thất bại không được bảo đảm trên mọi lần chạy. Test phải khẳng định trực tiếp **a.equals(b) ⇒ a.hashCode()==b.hashCode()** cùng với hành vi tìm kiếm.

### 7.2. Dùng == để so sánh String trong equals()

**tenantId == other.tenantId** so sánh tham chiếu, trong khi hai String khác object có thể chứa cùng nội dung. Dùng **tenantId.equals(other.tenantId)** khi chắc chắn non-null; dùng **Objects.equals(...)** khi cần hỗ trợ null.

### 7.3. Không thống nhất tiêu chí equality và hash

Nếu equals() xem hai khóa cùng userId là bằng nhau bất kể tenantId, nhưng hashCode() đưa cả tenantId vào tính toán, hai khóa được equals xem là bằng nhau có thể có hash khác: sai hợp đồng. Ngược lại, nếu hashCode() chỉ dùng userId còn equals() dùng cả tenantId và userId thì hợp đồng có thể vẫn đúng, nhưng dễ tạo nhiều collision hơn.

### 7.4. Sửa khóa mutable sau khi chèn

Nếu equals/hashCode dựa trên trường **code** mutable, lệnh **map.put(key, value)** lưu entry theo hash ban đầu. Sau **key.code = "new-code"**, gọi **map.containsKey(key)** bằng chính tham chiếu cũ vẫn **có thể thất bại** vì collection không tự di chuyển entry đến vùng hash mới. HashSet gặp rủi ro tương tự.

Ưu tiên dùng **final field với thành phần immutable**, hoặc một record chỉ chứa các component an toàn. Nếu thực sự phải thay khóa, quản lý thao tác xóa khóa ở trạng thái cũ và thêm khóa mới có kiểm soát; tránh để đối tượng bên ngoài sửa trực tiếp dữ liệu làm khóa.

### 7.5. equals() bất đối xứng giữa lớp cha và lớp con

Lớp cha có thể cho rằng nó bằng một instance lớp con, nhưng lớp con yêu cầu thêm field và không coi là bằng lớp cha. Khi **a.equals(b) != b.equals(a)**, hợp đồng bị phá vỡ và tra cứu trong collection có thể phụ thuộc hướng so sánh. Với kiểu khóa giá trị, **final class** hoặc **record** thường giúp diễn đạt equality minh bạch. Nếu cần kế thừa, phải kiểm thử đối xứng và bắc cầu giữa mọi kiểu liên quan.

### 7.6. Dùng map.get() == null để kết luận khóa không tồn tại

**HashMap cho phép value null**: một khóa b có thể tồn tại, **map.containsKey(b)==true**, nhưng **map.get(b)==null**. Nếu bài toán cần phân biệt khóa chưa chèn và khóa ánh xạ tới null, hãy kiểm tra **containsKey**. HashSet.contains trực tiếp trả boolean.

### 7.7. Kiểm thử chỉ bằng một instance

Chèn a rồi gọi get(a) không chứng minh được lookup bằng khóa tương đương. Test phải tạo b khác identity, assert chúng bằng nhau và tra bằng b. Kiểm tra chỉ có cùng hash cũng không đủ để chứng minh equality.

### 7.8. Nhầm record với bất biến sâu

Một **record** tự sinh equals/hashCode dựa vào các component, nhưng component có thể là List, array hoặc một object mutable. Nếu component có trạng thái thay đổi và tham gia hashCode, khóa record vẫn có thể mất tính ổn định. Record đơn giản với String và primitive an toàn hơn; với component mutable cần hợp đồng defensive copy và equality phù hợp.

## 8. Ma trận ca kiểm thử quan trọng

| Trường hợp | Dữ liệu | Kết quả cần chứng minh |
| --- | --- | --- |
| Positive equality | Hai instance khác nhau, cùng mọi trường khóa | Map get/containsKey và Set contains tìm thấy |
| Put/update trùng khóa logic | put(a), sau đó put(b) | Map chỉ có một entry và giữ giá trị mới |
| Add trùng phần tử | add(a), sau đó add(b) | add(b) false và size không tăng |
| Negative theo mã người dùng | Cùng tenant, userId khác | Không khớp |
| Negative theo tổ chức | Cùng userId, tenant khác | Không khớp |
| Phản xạ/đối xứng/bắc cầu | Tạo a, b, c bằng nhau | Tất cả tính chất equals đều đúng |
| Hash contract | a.equals(b) true | hashCode(a)==hashCode(b) |
| Collision | Hai khóa khác nhau, cố ý cùng hash | Collection vẫn phân biệt |
| Null value trong Map | put(a, null) | containsKey(b) true dù get(b) null |
| Mutable key | Field hash thay đổi sau khi chèn | Nhận diện nguy cơ và sửa thiết kế khóa |
| Kế thừa / proxy | Các kiểu khóa liên quan theo thiết kế | Không phá symmetry/transitivity |
| Nhiều phần tử | Thêm nhiều khóa có trùng và không trùng | Số lượng và giá trị đúng; không dựa vào thứ tự |

**Không nên khẳng định các hashCode của object khác nhau bắt buộc khác nhau** hoặc Map/Set luôn có một thứ tự duyệt cụ thể. Những kỳ vọng đó nằm ngoài hợp đồng Java.

## 9. Dùng record để biểu diễn khóa theo giá trị

Với Java 17+, record gọn khi các component đúng là thông tin nhận diện khóa logic. Ví dụ sau là **mảnh mã minh họa**, cần các import Map, HashMap tương ứng và đặt các statement trong method:

~~~java
record UserKey(String tenantId, int userId) {}

UserKey first = new UserKey("team-a", 42);
UserKey equivalent = new UserKey("team-a", 42);
Map<UserKey, String> map = new HashMap<>();
map.put(first, "ACTIVE");

// map.get(equivalent) trả "ACTIVE".
// map.containsKey(equivalent) trả true.
~~~

Record tự cung cấp equals/hashCode theo các component; vẫn phải kiểm tra rằng **toàn bộ component** thực sự thuộc khóa logic. Nếu một trường chỉ là dữ liệu mô tả không nên tham gia equality, hãy định nghĩa kiểu khóa tách biệt chứa đúng các field cần thiết, thay vì dùng record bao gồm cả trường mô tả. Việc khai báo record không bảo đảm các object do component trỏ tới là bất biến sâu.

## 10. Checklist đánh giá PASS

Một bộ kiểm thử nên kết luận PASS cho hợp đồng lookup khi:

- Hai **đối tượng riêng biệt** có cùng nội dung khóa được chứng minh khác identity nhưng bằng nhau cả hai chiều equals().
- equals() phản xạ, đối xứng, bắc cầu, nhất quán và trả false với null; các đối tượng bằng nhau có cùng hashCode().
- Map đã lưu a vẫn tìm bằng b, cập nhật bằng b không tăng số khóa logic và đọc bằng a thấy value mới.
- Set đã chứa a vẫn tìm bằng b; thêm b không tăng số phần tử.
- Các khóa không bằng nhau không bị nhầm, kể cả khi trùng hash.
- Không dùng field mutable làm thay đổi nghĩa/hash của khóa sau khi chèn; nếu có chia sẻ trạng thái thì thiết kế xử lý theo hợp đồng.
- Assertions thực sự được thực thi; kết quả không phụ thuộc thứ tự HashMap/HashSet hay identity hash may rủi.

**Kết luận:** phép thử quyết định là **thêm một instance vào HashMap/HashSet rồi tra cứu bằng instance khác nhưng bằng nhau theo equals() và có hashCode tương thích**. Kết hợp phép thử đó với cập nhật/chống trùng, negative case, collision và sự ổn định của khóa để kiểm chứng đúng hợp đồng đối tượng trong ứng dụng Java.