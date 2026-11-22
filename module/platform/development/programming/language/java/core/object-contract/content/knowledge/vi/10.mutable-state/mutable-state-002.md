# Vì sao một khóa có thể không tìm lại được sau khi thay đổi

## 1. Hiện tượng: phần tử còn trong Map nhưng get trả về null

Xét một đối tượng được dùng làm **khóa** trong `HashMap` hoặc làm **phần tử** trong `HashSet`. Nếu các trường dùng để tính `equals(Object)` và `hashCode()` bị sửa **sau khi đã thêm vào cấu trúc băm**, lời gọi `get(key)`, `containsKey(key)`, `remove(key)` hoặc `contains(element)` có thể không tìm được mục vừa lưu, ngay cả khi ta truyền vào **chính tham chiếu đối tượng cũ**.

Điều này dễ gây ngạc nhiên: `map.size()` vẫn có thể là `1`, vòng lặp qua `entrySet()` vẫn thấy mục, nhưng `map.get(key)` lại trả về `null`. Không có gì tự động xóa dữ liệu; vấn đề nằm ở **vị trí lưu đã được xác định từ hash code cũ**, trong khi phép tra cứu sau đó dùng **hash code mới**.

Đây là hệ quả của mối liên hệ giữa trạng thái thay đổi, hợp đồng `equals`/`hashCode` và cách bảng băm tìm vị trí phần tử. `HashMap` không theo dõi để tự chuyển một mục sang bucket khác mỗi khi trường trong đối tượng khóa bị sửa.

> Ghi nhớ: thay đổi một trường không liên quan đến `equals` và `hashCode` chưa chắc ảnh hưởng tới tra cứu. Rủi ro đặc biệt xuất hiện khi thay đổi **trạng thái tham gia quyết định bình đẳng hoặc mã băm**.

## 2. Cơ chế từng bước

Giả sử lớp `Key` có trường `id`; hai khóa có cùng `id` thì bằng nhau, và `hashCode()` trả về hash của `id`.

1. Khi thực hiện `map.put(key, value)` lúc `id == 1`, `HashMap` tính hash của khóa hiện tại, dùng hash đó để xác định bucket và lưu mục vào cấu trúc nội bộ. Triển khai `HashMap` của JDK còn lưu giá trị hash được tính tại thời điểm chèn trong mục nội bộ.
2. Sau đó, mã ứng dụng sửa `key.id = 2`. **Đối tượng khóa đã đổi**, nhưng mục trong bảng băm không tự chuyển chỗ theo trạng thái mới.
3. Khi gọi `map.get(key)`, `HashMap` tính lại hash từ `id == 2`. Hash này có thể hướng tra cứu tới bucket khác nơi mục được chèn, hoặc không khớp với hash lưu ở mục cũ.
4. Vì không tìm thấy mục phù hợp qua thuật toán tra cứu, `get` trả về `null` và `containsKey` trả về `false`, mặc dù dữ liệu vẫn có thể được duyệt qua `entrySet`.

Minh họa khái niệm:

~~~text
Trước khi sửa:
key.id = 1  -> hash = 1 -> bucket của hash 1 -> [key -> "data"]

Sau khi sửa key.id = 2:
key.id = 2  -> hash = 2 -> tra theo hash 2 -> không thấy mục đã lưu
                                                (mục cũ vẫn ở bucket trước)
~~~

Đây là **sơ đồ logic**, không phải mô tả địa chỉ bucket cố định trên mọi dung lượng bảng. Vị trí bucket thực tế phụ thuộc thuật toán trộn hash, kích thước bảng và thời điểm thay đổi cấu trúc. Điểm cốt lõi vẫn là: **sửa chính đối tượng khóa không tương đương với xóa mục cũ rồi chèn lại**.

Hash code cũng không phải vị trí lưu duy nhất. Có thể có nhiều đối tượng hash trùng nhau; khi xử lý va chạm, `HashMap` dùng thêm kiểm tra khóa, trong đó có `equals`. Do vậy:

- Nếu hai đối tượng **bằng nhau**, chúng bắt buộc phải có cùng hash code.
- Nếu hash code giống nhau, hai đối tượng **chưa chắc bằng nhau**.
- Nếu một khóa đã lưu đổi các trường tham gia bình đẳng, trạng thái khóa trong cấu trúc băm không còn ổn định; việc tìm kiếm theo khóa mới hoặc khóa cũ đều có thể không mang lại kết quả mong đợi.
- Việc `get` trả về `null` riêng lẻ cũng có thể là do giá trị gắn với khóa thật sự là `null`. Dùng `containsKey` và kiểm tra mục trong `entrySet` để phân biệt khi phân tích lỗi.

## 3. Chương trình Java 17 chạy được

Ví dụ sau có `MutableKey` với trường `id` thay đổi được và một lớp `StableKey` dùng `record` với thành phần `int` không thay đổi sau khi tạo. Các phương thức `equals` và `hashCode` của `MutableKey` **đúng khi giá trị id cố định**; lỗi đến từ việc đổi `id` khi đối tượng đang nằm trong collection.

Lưu mã sau vào tệp **MutableHashKeyDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class MutableHashKeyDemo {
    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void changeId(int newId) {
            id = newId;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof MutableKey that && id == that.id);
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    record StableKey(int id) { }

    public static void main(String[] args) {
        Map<MutableKey, String> broken = new HashMap<>();
        MutableKey key = new MutableKey(1);
        broken.put(key, "data");

        System.out.println("before: " + broken.get(key));

        key.changeId(2);
        System.out.println("after: " + broken.get(key));
        System.out.println("contains mutated: " + broken.containsKey(key));
        System.out.println("entries: " + broken.size());
        System.out.println("entry still value: "
                + broken.entrySet().iterator().next().getValue());
        System.out.println("same object reference: "
                + (broken.entrySet().iterator().next().getKey() == key));
        System.out.println("search old id: "
                + broken.get(new MutableKey(1)));
        System.out.println("search new id: "
                + broken.get(new MutableKey(2)));

        Set<MutableKey> set = new HashSet<>();
        MutableKey member = new MutableKey(5);
        set.add(member);
        member.changeId(6);
        System.out.println("set contains after: " + set.contains(member));
        System.out.println("set size: " + set.size());

        Map<MutableKey, String> safe = new HashMap<>();
        MutableKey editable = new MutableKey(100);
        safe.put(editable, "safe");
        String savedValue = safe.remove(editable); // Khi hash còn là 100
        editable.changeId(101);
        safe.put(editable, savedValue);
        System.out.println("safe lookup: " + safe.get(editable));

        Map<StableKey, String> stable = new HashMap<>();
        StableKey original = new StableKey(8);
        stable.put(original, "stable");
        StableKey replacement = new StableKey(9);
        System.out.println("stable original: "
                + stable.get(new StableKey(8)));
        System.out.println("stable replacement: "
                + stable.get(replacement));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac MutableHashKeyDemo.java
java MutableHashKeyDemo
~~~

Kết quả:

~~~text
before: data
after: null
contains mutated: false
entries: 1
entry still value: data
same object reference: true
search old id: null
search new id: null
set contains after: false
set size: 1
safe lookup: safe
stable original: stable
stable replacement: null
~~~

### Đọc kết quả đúng cách

- **`before: data`:** ngay sau khi chèn, `key.id == 1`; hash tại lúc tra cứu vẫn khớp hash khi chèn.
- **`after: null` và `contains mutated: false`:** `id` đã đổi thành `2`, nên hash mới không còn dẫn tới mục với hash cũ trong ví dụ. Hai lệnh tra cứu không tìm được mục.
- **`entries: 1` và `entry still value: data`:** phần tử không tự bị xóa, nên vẫn tồn tại trong `HashMap`.
- **`same object reference: true`:** khóa trong mục còn lưu chính là đối tượng `key` đã bị sửa. Vì vậy, việc không tìm được không có nghĩa Java đã thay khóa bằng một bản sao.
- **`search old id: null`:** tra cứu với một khóa mới có `id == 1` sẽ tới nơi chứa mục cũ, nhưng khóa đang lưu đã có `id == 2` nên `equals` không còn khớp.
- **`search new id: null`:** tra cứu bằng một khóa mới có `id == 2` dùng hash mới, không khớp vị trí/hash được lưu khi chèn khóa cũ. Trong ví dụ với kích thước bảng mặc định và các giá trị nguyên nhỏ này, hai hash dẫn tới hai bucket khác nhau.
- **`set contains after: false` và `set size: 1`:** `HashSet` chịu cùng vấn đề bởi nó sử dụng cấu trúc băm bên dưới.
- **`safe lookup: safe`:** thao tác xóa khi khóa vẫn còn `id == 100`, sau đó đổi sang `101` và chèn lại đã tạo ra mục đúng vị trí theo hash mới.
- **`stable original: stable`:** khóa record chứa một `int` cố định nên phép tra cứu với một giá trị khóa tương đương vẫn hoạt động. `replacement` là một khóa mới có giá trị khác, không tự thay thế khóa cũ.

Không được kết luận rằng **mọi** đột biến đều luôn làm `get` thất bại. Kết quả phụ thuộc trường bị sửa, cách cài `equals`/`hashCode`, hash và thao tác cụ thể. Nhưng việc thay đổi dữ liệu quyết định hash/bình đẳng khi khóa đã nằm trong cấu trúc băm là thiết kế không an toàn.

## 4. Vì sao vẫn nhìn thấy mục qua entrySet?

`HashMap.entrySet()` cho phép duyệt những mục hiện đang được lưu trong bảng. Việc duyệt bảng không đòi hỏi phải tìm một mục dựa trên **hash vừa tính lại từ một khóa đầu vào** như `get(key)`.

Trong chương trình, vòng duyệt nội bộ qua tập entry vẫn nhìn thấy khóa và giá trị. Nhưng `get(key)` phải thực hiện lại quy trình xác định vị trí từ hash mới. Hai đường đi này khác nhau nên quan sát “vòng lặp thấy mục nhưng tra cứu không thấy” không mâu thuẫn.

Cũng vì thế, không thể mặc nhiên sửa lỗi bằng cách gọi `map.remove(key)` **sau khi khóa đã đổi**: thao tác `remove` cũng cần tìm khóa theo hash hiện tại và có thể thất bại. Việc liên tục gọi `put(key, value)` sau khi khóa đã thay đổi còn có thể khiến cùng tham chiếu khóa xuất hiện ở những mục khác nhau nếu mục cũ không được tìm thấy. Không nên coi đó là phương thức “sửa chữa” collection đang sai trạng thái.

## 5. Chẩn đoán và phòng tránh mà không làm mất entry

Khi gặp tình huống `size() > 0` nhưng `get(key) == null`, trước tiên cần phân biệt **không tìm thấy khóa** với **khóa có value null** bằng `containsKey`. Sau đó, trong điều kiện không có bên ghi đồng thời, kiểm tra các entry đang tồn tại để xác nhận đối tượng khóa có bị thay đổi so với thời điểm chèn hay không. Duyệt được entry không chứng minh cấu trúc hash vẫn tìm được nó bằng khóa hiện tại.

**Quy tắc ngăn lỗi ngay từ đầu:** dùng khóa có thông tin tham gia `equals/hashCode` ổn định; `record` chứa kiểu bất biến như `String` hoặc primitive phù hợp. Record có component mảng hoặc collection mutable chỉ bất biến nông: phải bảo vệ cả các tham chiếu thành phần và dữ liệu lồng nhau.

Nếu **thật sự cần đổi định danh**, hãy kiểm tra khóa mới và xung đột, **xóa khóa cũ khi nó còn nguyên**, rồi mới đổi thuộc tính hoặc tạo khóa mới và chèn lại. Với `Map` cho phép value null, phải kiểm tra tồn tại trước khi dựa vào kết quả `remove`. Một chuỗi `remove → mutate → put` chưa phải giao dịch nguyên tử khi có luồng ghi khác.

Nếu **đã lỡ đổi khóa khi còn lưu**, không gọi `remove(mutatedKey)` hoặc `put(mutatedKey, value)` liên tục để chữa: chính đường tra cứu đó có thể sai hoặc tạo thêm entry. Cần kiểm soát độc quyền collection, duyệt để xác định entry, tháo qua iterator hợp lệ khi thích hợp hoặc xây dựng lại từ dữ liệu đáng tin, rồi kiểm tra chính sách trùng. Các bước chuyển khóa với xử lý va chạm, rollback và đồng thời được dạy chính tại bài *Loại bỏ rồi thêm lại dữ liệu khi nghiệp vụ thật sự cần đổi khóa*.

Với object mutable dùng như **value** trong `Map`, chỉ sửa trường hiển thị của value không gây lỗi hash của **key**. Với object dùng làm key, tách định danh bất biến khỏi trạng thái hiển thị thay đổi giúp tránh phụ thuộc vào bucket cũ. Bài *Ưu tiên khóa bất biến* đi sâu vào lựa chọn kiểu và phòng vệ đối tượng thành phần.

## 6. Các nhầm lẫn thường gặp

| Nhầm lẫn | Điều thực tế |
| --- | --- |
| “Map giữ bản sao của khóa nên sửa khóa bên ngoài không ảnh hưởng” | `HashMap` thường giữ tham chiếu tới đối tượng khóa; không tự sao chép khóa tùy biến |
| “Đối tượng vẫn trong map, vì vậy get chắc chắn phải tìm thấy” | Mục vẫn tồn tại nhưng quy trình tra theo hash hiện tại có thể không dẫn tới mục cũ |
| “Chỉ cần equals đúng là đủ” | Với collection băm, `hashCode` phải nhất quán với `equals` và các trường quyết định bình đẳng cần ổn định khi là khóa |
| “Nếu hashCode không đổi thì mọi đột biến đều an toàn” | Thay đổi dữ liệu tham gia `equals` vẫn làm đổi ý nghĩa so sánh với khóa khác; cần thiết kế khóa ổn định |
| “Gọi remove sau khi đổi id sẽ sửa ngay” | `remove` cũng tra cứu theo hash hiện tại và có thể không tìm thấy mục đã lưu |
| “Dùng record thì bất kỳ trường nào cũng bất biến sâu” | Thành phần kiểu tham chiếu có thể chứa đối tượng thay đổi được |
| “Đổi khóa cũ bằng cách sửa chính nó là tương đương với reinsert” | Bảng không theo dõi setter; cần xóa trước và thêm lại, hoặc tạo khóa mới |

## 7. Kiểm tra thiết kế và kiểm thử

Khi thiết kế lớp làm khóa, hãy trả lời:

- Những trường nào dùng trong `equals` và `hashCode`? Hai phương thức có dùng dữ liệu tương ứng để bảo đảm các khóa bằng nhau có cùng hash không?
- Có bất kỳ đường cập nhật nào làm đổi các trường này **sau khi khóa được đưa vào** `HashMap`/`HashSet` không?
- Có mã khác đang giữ tham chiếu và có thể sửa khóa không?
- Nếu cần thay đổi định danh, ứng dụng có xóa mục cũ và thêm khóa mới theo trình tự rõ ràng không?
- Có những giá trị thành phần mutable nằm bên trong đối tượng có vẻ bất biến không?
- Trong môi trường nhiều luồng, việc đọc/ghi khóa và cập nhật collection có được phối hợp nhất quán không?

Một kiểm thử hành vi hữu ích là thêm khóa, tra cứu thành công, thử thay đổi các trường được phép, rồi kiểm tra lại `get`/`containsKey` hoặc `contains`. Nếu thay đổi trường định danh là nghiệp vụ có chủ đích, kiểm thử cần xác nhận quy trình **xóa khóa cũ rồi thêm khóa mới** và tính toàn vẹn số lượng mục. Đồng thời, kiểm tra kết quả `equals`/ `hashCode` khi trường dữ liệu liên quan không thay đổi.

**Ghi nhớ:** Khóa băm phải có **trạng thái bình đẳng và mã băm ổn định trong thời gian được lưu**. Khi bạn sửa một trường tham gia `hashCode`, `HashMap` không tự di chuyển mục sang vị trí mới; vì thế mục có thể còn tồn tại nhưng không còn tìm được bằng `get`. Ưu tiên khóa bất biến; nếu bắt buộc đổi khóa, hãy cập nhật collection bằng thao tác xóa và thêm lại có kiểm soát.