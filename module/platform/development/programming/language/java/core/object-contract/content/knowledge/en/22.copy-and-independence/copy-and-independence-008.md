# Kiểm tra thay đổi bản sao có ảnh hưởng bản gốc hay không

## 1. Mục tiêu: kiểm tra tính độc lập của bản sao

Khi sao chép một đối tượng Java, câu hỏi quan trọng không chỉ là “hai biến có trỏ tới hai đối tượng khác nhau không?”, mà là: **nếu thay đổi trạng thái có thể thay đổi được (mutable state) ở bản sao, trạng thái quan sát được của bản gốc có bị thay đổi theo hay không, và ngược lại?**

Ví dụ, một đối tượng hồ sơ có tên (String), địa chỉ (Address) và danh sách kỹ năng (List<String>). Hai hồ sơ có thể là hai đối tượng khác nhau nhưng cùng trỏ tới một Address hoặc cùng trỏ tới một List. Khi sửa địa chỉ hay danh sách ở bản sao, bản gốc vẫn bị ảnh hưởng.

Cần phân biệt hai khái niệm:

- **Khác danh tính (identity):** kiểm tra bằng toán tử **==** hoặc **!=** trên tham chiếu. **copy != original** chỉ chứng minh đối tượng ngoài cùng khác nhau.
- **Độc lập về trạng thái mutable:** những thành phần được yêu cầu độc lập không có đường tham chiếu chia sẻ khiến thao tác sửa ở một phía làm thay đổi phía kia. Đây là hành vi phải kiểm thử bằng các thao tác thay đổi và quan sát cụ thể.

Không phải mọi tham chiếu dùng chung đều là lỗi: có thể chia sẻ đối tượng bất biến như String, Integer hoặc một value object thực sự immutable mà không tạo rủi ro sửa chung. Mức độc lập cần đạt phụ thuộc vào **hợp đồng sao chép** của lớp/API; “deep copy” thường có nghĩa sao chép phần đồ thị mutable thuộc quyền sở hữu của đối tượng, chứ không nhất thiết tạo một bản mới cho mọi giá trị bất biến.

## 2. Vì sao bản sao có thể ảnh hưởng bản gốc?

Các biến kiểu tham chiếu chứa tham chiếu tới đối tượng, không chứa toàn bộ cấu trúc đối tượng con. Gán biến hay sao chép trường tham chiếu có thể khiến hai đường truy cập cùng đến một đối tượng mutable.

| Cách tạo | Đối tượng ngoài cùng | Trường tham chiếu mutable bên trong | Kết quả khi sửa |
| --- | --- | --- | --- |
| **alias = original** | Chính cùng một đối tượng | Dùng chung | Mọi thay đổi trạng thái qua alias đều nhìn thấy qua original |
| **Sao chép nông (shallow copy)** | Thường là đối tượng mới | Thường vẫn dùng chung đối tượng con | Sửa đối tượng con dùng chung có thể ảnh hưởng bản gốc |
| **Sao chép sâu (deep copy)** | Đối tượng mới | Sao chép các phần mutable thuộc phạm vi cần độc lập | Thay đổi phần đã sao chép độc lập giữa hai phía |
| **Thiết kế immutable / chia sẻ an toàn** | Có thể mới hoặc chia sẻ | Dữ liệu chia sẻ không thể bị thay đổi qua API hợp lệ | Không có thay đổi mutable để lan truyền qua phần được chia sẻ |

Một biến String được gán sang bản sao có thể dùng chung đối tượng String an toàn, vì String immutable. Ngược lại, nếu cùng một đối tượng Address được giữ trong hai đối tượng hồ sơ, lệnh **copy.address.city = "Huế"** sửa chính Address mà bản gốc đang giữ; đây không phải lệnh gán lại trường address của riêng bản sao.

Tương tự, việc gọi **new ArrayList<>(original.skills)** tạo một List mới nhưng chỉ sao chép các tham chiếu phần tử. Nếu các phần tử là String thì việc chia sẻ phần tử an toàn; nếu các phần tử là Address mutable thì thay đổi nội dung Address vẫn có thể lan qua hai danh sách.

## 3. Quy trình kiểm thử đúng

1. **Xác định hợp đồng:** bản sao cần độc lập ở những trường nào? Liệt kê cả đối tượng lồng nhau, mảng, collection, phần tử mutable và trạng thái có thể sửa thông qua getter hoặc phương thức khác.
2. **Arrange – tạo dữ liệu gốc có thể quan sát:** ví dụ địa chỉ “Hà Nội”, danh sách [Java]. Tạo bản sao bằng đúng phương thức/API cần kiểm thử. Chụp giá trị trước khi sửa bằng bản snapshot độc lập hoặc expected value bất biến; tránh gọi một tham chiếu alias là “snapshot”.
3. **Kiểm tra cấu trúc tham chiếu khi phù hợp:** **assertNotSame(original, copy)** chưa đủ; với những thành phần mutable phải tách, kiểm tra thêm **assertNotSame(original.address, copy.address)** và các collection hay phần tử liên quan. Nếu hợp đồng cố ý chia sẻ tài nguyên, không ép mọi tham chiếu đều khác nhau.
4. **Act – sửa trực tiếp bản sao:** gán trường mutable, sửa trạng thái đối tượng con, thêm/xóa phần tử, thay đổi phần tử mutable. **Assert – xác nhận bản gốc không đổi** theo hợp đồng.
5. **Kiểm tra chiều ngược lại:** sửa chính bản gốc rồi xác nhận phần tương ứng của bản sao không đổi. Hai chiều giúp phát hiện tham chiếu chung ngay cả khi chỉ có một phía phơi bày API sửa.
6. **Lặp với những nhánh mutable quan trọng:** nhiều cấp lồng nhau, mảng, List, Map, phần tử mutable, null/collection rỗng và cấu trúc có vòng tham chiếu nếu mô hình dữ liệu có hỗ trợ.

Cần tách bạch **sửa đối tượng con** với **gán lại tham chiếu**. Ví dụ **copy.address = new Address("Huế")** chỉ đổi trường address của copy, nên bản gốc không đổi ngay cả khi trước đó cả hai dùng chung Address. Để thử phát hiện shallow copy phải dùng **copy.address.city = "Huế"** hoặc một phương thức thực sự sửa đối tượng Address hiện có.

## 4. Ví dụ Java 17+: so sánh alias, shallow copy và deep copy

Đoạn sau là chương trình hoàn chỉnh. **UserProfile.shallowCopy()** tạo đối tượng UserProfile mới nhưng giữ nguyên tham chiếu Address và List. **UserProfile.deepCopy()** tạo Address và List mới. Vì phần tử của List là String immutable, cách sao chép List này đủ để độc lập với các trường mutable trong ví dụ.

Lưu thành tệp **CopyIsolationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CopyIsolationDemo {

    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }

        Address(Address other) {
            this.city = other.city;
        }
    }

    static final class UserProfile {
        String name;
        Address address;
        List<String> skills;

        UserProfile(String name, Address address, List<String> skills) {
            this.name = name;
            this.address = address;
            this.skills = skills;
        }

        UserProfile shallowCopy() {
            return new UserProfile(name, address, skills);
        }

        UserProfile deepCopy() {
            return new UserProfile(
                    name,
                    new Address(address),
                    new ArrayList<>(skills)
            );
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        UserProfile original = new UserProfile(
                "An",
                new Address("Hà Nội"),
                new ArrayList<>(List.of("Java"))
        );

        UserProfile alias = original;
        UserProfile shallow = original.shallowCopy();

        System.out.println("Alias cùng đối tượng: " + (alias == original));
        System.out.println("Shallow khác đối tượng: " + (shallow != original));
        System.out.println("Shallow dùng chung Address: "
                + (shallow.address == original.address));
        System.out.println("Shallow dùng chung List: "
                + (shallow.skills == original.skills));

        shallow.address.city = "Huế";
        shallow.skills.add("SQL");
        System.out.println("Gốc sau sửa shallow: "
                + original.address.city + " | " + original.skills);

        require("Huế".equals(original.address.city),
                "Shallow phải nhìn thấy thay đổi trên Address dùng chung");
        require(original.skills.contains("SQL"),
                "Shallow phải nhìn thấy thay đổi trên List dùng chung");

        UserProfile source = new UserProfile(
                "Bình",
                new Address("Hà Nội"),
                new ArrayList<>(List.of("Java"))
        );
        UserProfile deep = source.deepCopy();

        require(deep != source, "Đối tượng ngoài cùng phải khác");
        require(deep.address != source.address, "Address phải khác");
        require(deep.skills != source.skills, "List phải khác");

        deep.address.city = "Đà Nẵng";
        deep.skills.add("Spring");
        System.out.println("Gốc sau sửa deep: "
                + source.address.city + " | " + source.skills);

        require("Hà Nội".equals(source.address.city),
                "Sửa Address của deep không được sửa bản gốc");
        require(source.skills.equals(List.of("Java")),
                "Sửa List của deep không được sửa bản gốc");

        source.address.city = "Cần Thơ";
        source.skills.add("SQL");
        System.out.println("Deep sau sửa gốc: "
                + deep.address.city + " | " + deep.skills);

        require("Đà Nẵng".equals(deep.address.city),
                "Sửa Address gốc không được sửa deep");
        require(deep.skills.equals(List.of("Java", "Spring")),
                "Sửa List gốc không được sửa deep");

        System.out.println("Các phép kiểm tra đã thành công.");
    }
}
~~~

Biên dịch và chạy (trong terminal có JDK 17+):

~~~bash
javac -encoding UTF-8 CopyIsolationDemo.java
java CopyIsolationDemo
~~~

Kết quả stdout chính xác:

~~~text
Alias cùng đối tượng: true
Shallow khác đối tượng: true
Shallow dùng chung Address: true
Shallow dùng chung List: true
Gốc sau sửa shallow: Huế | [Java, SQL]
Gốc sau sửa deep: Hà Nội | [Java]
Deep sau sửa gốc: Đà Nẵng | [Java, Spring]
Các phép kiểm tra đã thành công.
~~~

**Giải thích kết quả:**

- **alias == original** là true: hai biến cùng trỏ tới một UserProfile.
- **shallow != original** là true nhưng cả Address và List của shallow vẫn trỏ đến các đối tượng con của original; các sửa đổi qua shallow xuất hiện ở original.
- **deep.address != source.address** và **deep.skills != source.skills**. Sau khi sửa deep, source vẫn giữ dữ liệu cũ. Sau khi sửa source, deep vẫn giữ dữ liệu riêng. Điều này chứng minh sự độc lập đối với các trường mutable đã kiểm tra trong mô hình này.
- Phương thức **require(...)** ném AssertionError nếu điều kiện sai, không phụ thuộc cờ chạy **-ea** như câu lệnh assert của Java. Ví dụ cố ý kiểm tra shallow *có* tác động chung để minh họa hành vi, còn deep *không* có tác động chung để chứng minh yêu cầu độc lập.

Lưu ý: deepCopy trên chỉ đúng trong phạm vi ví dụ vì Address không có trường mutable lồng nhau khác và List chứa String. Nếu Address có một đối tượng mutable bên trong hoặc List chứa phần tử mutable thì phải tiếp tục sao chép những nhánh đó theo hợp đồng.

## 5. Chuyển tiêu chí trên thành kiểm thử tự động

Trong dự án có **JUnit Jupiter (JUnit 5)**, có thể viết một test riêng với các phép assert rõ ràng. Đoạn dưới giả định lớp test ở **cùng package** với CopyIsolationDemo và dự án đã khai báo dependency JUnit 5; đây là mã test bổ sung, không phải chương trình chạy độc lập bằng lệnh java trực tiếp.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class CopyIsolationDemoTest {

    @Test
    void deepCopyIsIndependentInBothDirections() {
        var original = new CopyIsolationDemo.UserProfile(
                "An",
                new CopyIsolationDemo.Address("Hà Nội"),
                new ArrayList<>(List.of("Java"))
        );
        var copy = original.deepCopy();

        assertNotSame(original, copy);
        assertNotSame(original.address, copy.address);
        assertNotSame(original.skills, copy.skills);

        copy.address.city = "Huế";
        copy.skills.add("SQL");
        assertEquals("Hà Nội", original.address.city);
        assertEquals(List.of("Java"), original.skills);

        original.address.city = "Đà Nẵng";
        original.skills.add("Docker");
        assertEquals("Huế", copy.address.city);
        assertEquals(List.of("Java", "SQL"), copy.skills);
    }
}
~~~

Khi kiểm thử một phương thức sao chép thật trong dự án, thay **original.deepCopy()** bằng API thực tế, chọn bộ dữ liệu bao phủ các nhánh mutable và khẳng định theo hợp đồng. Một test duy nhất cho đối tượng phẳng có thể bỏ sót việc chia sẻ ở một trường ít dùng.

## 6. Ma trận tình huống cần kiểm tra

| Kiểu dữ liệu / cấu trúc | Tác động cần thử | Dấu hiệu bản sao chưa độc lập |
| --- | --- | --- |
| Trường nguyên thủy **int**, **boolean** | Sửa trường ở copy rồi kiểm tra original | Thông thường không thể lan qua phép copy giá trị nguyên thủy; nếu lan, có thể đang thao tác cùng đối tượng ngoài cùng |
| **String**, kiểu wrapper bất biến | Gán giá trị mới cho trường ở copy | Gán trường riêng không làm sửa đối tượng String/Integer; không cần sao chép sâu chúng |
| Đối tượng mutable lồng nhau, ví dụ **Address** | Sửa **copy.address.city** | **original.address.city** đổi theo |
| Mảng nguyên thủy, ví dụ **int[]** | Sửa **copy.values[0]** | Phần tử của mảng original đổi theo nếu dùng chung mảng |
| **List<String>** | **copy.skills.add(...)**, remove, set | List gốc đổi theo nếu dùng chung chính List |
| **List<Address>** | Sửa **copy.addresses.get(0).city** | List mới nhưng phần tử Address vẫn dùng chung |
| **Map<K, MutableValue>** | Sửa một value, thêm/xóa entry | Value gốc đổi theo nếu phần tử chung; thêm/xóa entry lan nếu Map chung |
| Getter trả tham chiếu mutable | Lấy **copy.getAddress()** rồi sửa | Bản gốc đổi dù trường có thể được khai báo private |
| Đồ thị có nhánh dùng chung/vòng tham chiếu | Sửa phần tử sâu hơn, kiểm tra hai chiều | Một nhánh còn chia sẻ ngoài phạm vi hợp đồng; sao chép đệ quy ngây thơ có thể lặp vô hạn |

Với List, Map và mảng, phải phân biệt **sao chép vỏ chứa** với **sao chép phần tử**. Ví dụ:

~~~java
List<Address> original = new ArrayList<>();
original.add(new Address("Hà Nội"));

List<Address> copy = new ArrayList<>(original); // List mới, Address cũ
copy.get(0).city = "Huế";

// original.get(0).city cũng là "Huế" vì phần tử Address dùng chung.
~~~

Đoạn này minh họa và sử dụng lớp Address đã định nghĩa ở ví dụ trước; không phải một tệp Java độc lập. Nếu muốn độc lập với thay đổi của từng Address, cần tạo Address mới cho từng phần tử, chẳng hạn duyệt source và gọi **new Address(item)**, đồng thời xử lý null và các mối liên hệ tham chiếu theo hợp đồng.

## 7. Chọn chiến lược sao chép và giới hạn của từng API

- **Copy constructor / factory method:** dễ diễn đạt chính xác cách sao chép các trường. Với lớp có trường mutable, cần quyết định sao chép đệ quy, giữ immutable hay chia sẻ một tài nguyên có chủ đích. Một copy constructor chỉ gán lại các tham chiếu có thể vẫn là shallow copy.
- **clone():** **Object.clone()** sao chép trạng thái trường ở mức nông; nó không tự tạo bản sao độc lập cho mọi đối tượng con. Muốn dùng clone theo hợp đồng sâu phải cài đặt xử lý các trường mutable phù hợp. Việc lớp hỗ trợ Cloneable không có nghĩa đồ thị đối tượng đã được deep copy.
- **Mảng:** **array.clone()** hoặc **Arrays.copyOf(...)** tạo mảng mới; đối với mảng chứa tham chiếu, các phần tử vẫn có thể cùng trỏ tới những đối tượng mutable.
- **Collection:** **new ArrayList<>(source)** tạo List mới nhưng phần tử vẫn được chia sẻ theo tham chiếu. **List.copyOf(source)** tạo danh sách không cho sửa bằng các thao tác List của nó, nhưng không sao chép sâu các phần tử mutable; nó cũng từ chối null trong các phần tử đầu vào. **Collections.unmodifiableList(source)** là view không cho sửa qua view nhưng có thể phản ánh thay đổi từ danh sách nguồn bên dưới.
- **record trong Java:** các component tham chiếu vẫn có thể trỏ tới đối tượng mutable. Cú pháp record không tự tạo bản sao sâu hoặc bảo đảm bất biến sâu; constructor và accessor có thể cần defensive copy nếu mục tiêu là bảo vệ trạng thái.
- **Đối tượng immutable:** có thể chia sẻ an toàn khi tính bất biến là thật (bao gồm các phần con được phơi bày). Không nên cố sao chép mọi String hay value object immutable chỉ để mọi identity khác nhau.
- **Đồ thị phức tạp:** với tham chiếu vòng, tham chiếu trỏ chung giữa nhiều trường hoặc đối tượng quản lý tài nguyên (file, socket, thread), khái niệm “deep copy toàn bộ” cần định nghĩa rõ. Một số thành phần phải giữ dùng chung hoặc không thể sao chép hợp lý; nên thiết kế API và test theo hợp đồng sở hữu.

Ví dụ một cách hạn chế rò rỉ qua getter: thay vì trả trực tiếp một List mutable nội bộ, có thể trả **List.copyOf(internalList)** nếu phần tử an toàn để chia sẻ. Với phần tử mutable, cần tạo bản sao từng phần tử hoặc cung cấp giao diện chỉ đọc thực sự theo hợp đồng.

## 8. Các sai lầm phổ biến khi kết luận “bản sao độc lập”

1. **Chỉ kiểm tra copy != original:** kết luận sai vì đối tượng ngoài cùng khác nhau nhưng nhánh mutable có thể cùng tham chiếu.
2. **Chỉ kiểm tra equals():** **equals()** trả lời câu hỏi bằng nhau về giá trị theo cách lớp định nghĩa, không nói hai đồ thị đối tượng có độc lập hay không. Hai bản sao có thể equals() true ngay sau khi sao chép mà vẫn độc lập.
3. **Chỉ gán lại trường ở copy:** thay đổi tham chiếu riêng không thử được sharing của đối tượng con. Cần sửa *bên trong* đối tượng con mutable.
4. **Chỉ kiểm tra chiều copy → original:** có thể bỏ sót những đường cập nhật qua bản gốc hay getter; thử cả hai chiều khi hợp đồng yêu cầu.
5. **Dùng snapshot bị alias:** ví dụ **var before = original.address;** rồi đọc **before.city** sau khi sửa không phải là lưu giá trị ban đầu. Hãy lưu String city hoặc tạo snapshot độc lập.
6. **Nhầm collection không sửa được với phần tử bất biến:** một List không cho add/remove vẫn có thể chứa Address mutable và chia sẻ Address với bản gốc.
7. **Bỏ qua đường truy cập gián tiếp:** setter, getter, phần tử mảng, Map value và một nhánh con sâu vẫn có thể sửa chung trạng thái.
8. **Dựa vào lệnh assert thông thường nhưng không bật -ea:** Java bỏ qua câu lệnh assert nếu assertions disabled. Dùng JUnit assertions hoặc kiểm tra luôn hoạt động như **require(...)** trong ví dụ.
9. **Quên hợp đồng của hashCode/equals với đối tượng mutable:** nếu thay đổi trường tham gia equals/hashCode khi đối tượng là khóa HashMap hoặc phần tử HashSet, có thể làm tra cứu sai kỳ vọng. Đây là lý do bổ sung để thiết kế bản sao và tính bất biến cẩn thận; nó không phải phép thử thay thế cho independence.

## 9. Checklist đánh giá kết quả

Một bài kiểm thử về độc lập bản sao chỉ nên kết luận **PASS cho phạm vi được kiểm tra** khi:

- Xác định được bản sao bằng đúng cơ chế sản phẩm sử dụng và đối tượng ngoài cùng có danh tính phù hợp hợp đồng.
- Những nhánh mutable cần tách có quan hệ identity đúng; nếu có chia sẻ, đó là chia sẻ được phép và không tạo ảnh hưởng trạng thái trái hợp đồng.
- Sửa trực tiếp từng nhóm trạng thái mutable được yêu cầu trên copy không làm thay đổi trạng thái tương ứng của original.
- Sửa original không làm thay đổi phần tương ứng của copy.
- Những trường hợp trọng yếu như collection chứa phần tử mutable, null, dữ liệu rỗng và độ sâu nhiều cấp được bao phủ theo cấu trúc thật; expected value được lưu độc lập.
- Kết quả quan sát bằng assertion có thể thất bại khi code sao chép bị hỏng; kiểm thử thực sự phát hiện shallow sharing ngoài ý muốn.

**Kết luận:** Để trả lời “thay đổi bản sao có ảnh hưởng bản gốc không?”, hãy **thao tác lên trạng thái mutable được sao chép, kiểm tra trạng thái gốc trước/sau và thử cả chiều ngược lại**. Kiểm tra identity giúp định vị nguyên nhân, còn kiểm thử hành vi và hợp đồng sở hữu mới quyết định bản sao có độc lập đúng yêu cầu hay không.