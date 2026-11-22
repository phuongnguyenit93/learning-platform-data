# Tái hiện lỗi thay đổi khóa sau khi đưa vào HashMap

## 1. Mục tiêu thực hành

Khi một đối tượng được dùng làm **khóa** của `HashMap`, các giá trị tham gia vào `equals()` và `hashCode()` phải giữ ổn định trong suốt thời gian đối tượng nằm trong map. Nếu thay đổi một trường dùng để tính khóa sau khi đã gọi `put()`, map có thể **không tìm được entry**, dù entry vẫn còn đó và ngay cả khi ta sử dụng đúng biến tham chiếu ban đầu.

Trong bài thực hành này, ta sẽ:

1. Tạo một lớp khóa có trường `id` có thể thay đổi.
2. Ghi đè `equals()` và `hashCode()` dựa trên `id`, tuân thủ hợp đồng của hai phương thức tại mỗi trạng thái.
3. Đưa khóa vào `HashMap`, thay đổi `id` rồi quan sát `get()`, `containsKey()`, `remove()` và `size()`.
4. Giải thích tại sao map mất khả năng tra cứu một entry còn tồn tại.
5. Thử thao tác `put()` lần nữa để thấy trạng thái bất thường hơn.
6. Sửa thiết kế bằng khóa bất biến và kiểm chứng kết quả.

**Kết luận cần chứng minh:** việc tham chiếu tới khóa vẫn còn và `map.size()` vẫn lớn hơn 0 **không có nghĩa** `map.get(key)` còn tìm được giá trị. `HashMap` dùng mã băm để xác định vị trí tra cứu; nó không duyệt toàn bộ các entry để tìm chính tham chiếu đó.

## 2. Ôn lại hợp đồng khóa của HashMap

`HashMap<K,V>` triển khai `Map<K,V>` bằng bảng băm. Hai phương thức trên khóa có vai trò chính:

- `hashCode()`: tạo số nguyên dùng để chọn vùng lưu/tra cứu, sau khi `HashMap` xử lý bit và tính chỉ số bucket.
- `equals(Object)`: quyết định hai khóa có được coi là cùng một khóa về mặt logic hay không, khi HashMap đã xét các điều kiện mã băm phù hợp.

Hợp đồng cơ bản giữa hai phương thức:

- Nếu `a.equals(b)` trả `true`, `a.hashCode()` và `b.hashCode()` phải bằng nhau.
- Nếu `a.hashCode() == b.hashCode()`, chưa thể suy ra `a.equals(b)`.
- Với một đối tượng mà thông tin dùng trong `equals()` không thay đổi, `hashCode()` phải ổn định trong quá trình thực thi tương ứng.
- Khi `equals()` trả về `false`, hai khóa có thể cùng hash; HashMap vẫn có khả năng lưu chúng thành hai entry khác nhau.

**Hợp đồng dùng khóa trong map còn cần một điều kiện thực tế:** đừng thay đổi trạng thái của khóa theo cách ảnh hưởng tới so sánh bằng nhau trong khi khóa nằm trong map. Tài liệu `Map` của Java nêu rằng hành vi không được xác định rõ nếu một đối tượng làm khóa bị thay đổi theo cách ảnh hưởng đến so sánh `equals` khi nó đang nằm trong map.

Điều này không có nghĩa lớp khóa mutable luôn vi phạm ngay hợp đồng `equals/hashCode`. Lớp vẫn có thể tính hai phương thức nhất quán tại từng thời điểm, nhưng **map đã lập chỉ mục theo trạng thái cũ** và không được thông báo để tái lập chỉ mục khi trường khóa thay đổi.

## 3. Ví dụ chạy được: khóa đổi hash sau khi put

Tạo tệp `MutableHashMapKeyDemo.java` (Java 17+):

~~~java
import java.util.HashMap;
import java.util.Map;

public class MutableHashMapKeyDemo {
    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void setId(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            return obj instanceof MutableKey other && id == other.id;
        }

        @Override
        public int hashCode() {
            return id;
        }
    }

    public static void main(String[] args) {
        Map<MutableKey, String> map = new HashMap<>();
        MutableKey key = new MutableKey(1);

        map.put(key, "An");
        System.out.println("hash trước: " + key.hashCode());
        System.out.println("get trước: " + map.get(key));
        System.out.println("size trước: " + map.size());

        key.setId(2); // Lỗi thiết kế: sửa trường tham gia equals/hashCode

        System.out.println("hash sau: " + key.hashCode());
        System.out.println("get sau: " + map.get(key));
        System.out.println("containsKey sau: " + map.containsKey(key));
        System.out.println("remove sau: " + map.remove(key));
        System.out.println("size sau remove: " + map.size());
        System.out.println("containsValue An: " + map.containsValue("An"));

        for (Map.Entry<MutableKey, String> entry : map.entrySet()) {
            System.out.println("entry còn lại: id="
                    + entry.getKey().id + ", value=" + entry.getValue());
            System.out.println("cùng tham chiếu key: "
                    + (entry.getKey() == key));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MutableHashMapKeyDemo.java
java MutableHashMapKeyDemo
~~~

Kết quả với triển khai `HashMap` của JDK 17:

~~~text
hash trước: 1
get trước: An
size trước: 1
hash sau: 2
get sau: null
containsKey sau: false
remove sau: null
size sau remove: 1
containsValue An: true
entry còn lại: id=2, value=An
cùng tham chiếu key: true
~~~

### Giải thích từng kết quả

1. Khi `put(key, "An")`, `hashCode()` trả `1` và `HashMap` lưu entry tương ứng với hash tại thời điểm chèn.
2. `map.get(key)` trước khi sửa trả `"An"` vì đối tượng có trạng thái khớp với thông tin lập chỉ mục.
3. Sau `key.setId(2)`, chính đối tượng `key` thay đổi `hashCode()` từ `1` sang `2`. Entry đã được lưu trước đó **không tự di chuyển**.
4. `map.get(key)` tra cứu theo hash mới. Nó không tìm entry nằm ở vị trí/hash cũ nên trả `null`.
5. `containsKey(key)` là `false` và `remove(key)` trả `null` vì chúng cũng phụ thuộc vào tra cứu khóa theo mã băm mới.
6. `size()` vẫn trả `1` vì lệnh `remove` không xóa được entry; `containsValue("An")` vẫn là `true` vì thao tác này kiểm tra giá trị trên những entry hiện tồn tại.
7. Vòng lặp `entrySet()` chứng minh map còn giữ **đúng đối tượng khóa ban đầu** (so sánh bằng `==` là `true`), giờ có `id == 2`.

Kết quả `null` của `get` chưa tự nó chứng minh không có entry nếu map cho phép lưu giá trị `null`. Trong ví dụ, ta đã biết giá trị được chèn là `"An"` và xác minh bổ sung bằng `containsKey`, `size`, `entrySet`.

## 4. Nhìn sâu vào nguyên nhân: hash được ghi nhận lúc chèn

Để hình dung lỗi, xét mô hình đơn giản tương ứng với ví dụ trên (JDK `HashMap` thường khởi tạo bảng có 16 bucket khi chèn lần đầu). Với các hash nhỏ như `1` và `2`, phép trộn hash của cách triển khai phổ biến giữ nguyên giá trị, dẫn tới bucket khác nhau.

~~~text
Thời điểm put:
key.id = 1  ---> hashCode() = 1
                    |
                    v
           bucket 1: [hash đã lưu = 1, key -> "An"]

Sau khi key.setId(2):
key.id = 2  ---> hashCode() = 2
                    |
                    v
           tìm ở bucket 2: không có entry

Nhưng bucket 1 vẫn giữ:
           [hash đã lưu = 1, key (hiện id=2) -> "An"]
~~~

Đây là mô hình giải thích hiện tượng với JDK 17, **không phải cam kết API** về số bucket, công thức phân bucket hoặc cấu trúc nội bộ cho mọi phiên bản Java.

Trong triển khai `HashMap` của OpenJDK, mỗi entry/nút lưu hash được tính khi chèn. Khi tra cứu, map tính hash từ đối tượng khóa tại thời điểm gọi và dùng hash đó trong việc xác định entry phù hợp. Thay đổi khóa không kích hoạt `put`/rehash cho entry đã có.

Một hiểu nhầm phổ biến là: “`key.equals(key)` chắc chắn trả `true` nên `get(key)` phải thành công.” Thực tế, **so sánh `equals` không cứu được entry nếu bước tìm theo hash đã dẫn đến vị trí khác**. Việc dùng lại cùng tham chiếu (`==`) cũng không giúp.

Một hiểu nhầm khác là “nếu hash mới vô tình rơi vào cùng bucket thì tra cứu sẽ an toàn”. Trong triển khai HashMap phổ biến, điều kiện so khớp còn xét **hash đã lưu** của entry, nên cùng bucket không tạo bảo đảm khi mã băm thay đổi. Ngoài ra, sửa trường chỉ tham gia `equals()` mà không thay đổi `hashCode()` cũng có thể phá vỡ ngữ nghĩa tra cứu bằng những đối tượng khóa tương đương khác. Quy tắc thiết kế vẫn là **giữ ổn định cả các trường ảnh hưởng `equals()` lẫn `hashCode()`**.

## 5. Thí nghiệm mở rộng: put lại cùng một biến khóa

**Chỉ thực hiện để quan sát lỗi, tuyệt đối không dùng để “chữa” map trong ứng dụng.**

Chèn các dòng sau sau phần `for` trong `main` của ví dụ ở mục 3:

~~~java
map.put(key, "Bình");
System.out.println("size sau put lại: " + map.size());
System.out.println("get sau put lại: " + map.get(key));

for (Map.Entry<MutableKey, String> entry : map.entrySet()) {
    System.out.println("entry value: " + entry.getValue()
            + ", cùng tham chiếu: " + (entry.getKey() == key));
}
~~~

Với trạng thái map sau ví dụ chính, kết quả của đoạn bổ sung trong JDK 17:

~~~text
size sau put lại: 2
get sau put lại: Bình
entry value: An, cùng tham chiếu: true
entry value: Bình, cùng tham chiếu: true
~~~

Ở đây, bảng băm có thể chứa **hai entry cùng giữ một tham chiếu khóa**: entry cũ vẫn nằm theo hash `1`, entry mới được chèn theo hash `2`. `size()` thành `2` mặc dù hai khóa là cùng đối tượng.

Điều này diễn ra vì `HashMap` không thể tìm entry cũ bằng hash hiện tại của khóa và coi `put` như chèn entry mới. Nó minh họa trạng thái bất thường khi vi phạm giả định ổn định khóa. Bài thực hành chọn mã băm nhỏ `1`/`2` để kết quả bucket trong JDK 17 rõ ràng; **không được dựa vào hành vi lỗi cụ thể này như một đặc tính được API `Map` bảo đảm**.

Không nên gọi thêm `put`, `remove` hoặc `compute` rồi giả định trạng thái đã phục hồi; một map đã bị biến đổi khóa trong lúc lưu có thể khó kiểm soát, nhất là khi có nhiều key và quan hệ bằng nhau thay đổi.

## 6. Khắc phục bằng khóa bất biến

Cách khắc phục đáng tin cậy nhất là **dùng khóa có trạng thái nhận diện bất biến**. Với Java 17, `record` chỉ chứa thành phần bất biến như `int`, `long`, `String` là lựa chọn ngắn gọn.

Tạo tệp `StableHashMapKeyDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class StableHashMapKeyDemo {
    record UserKey(int id) {}

    public static void main(String[] args) {
        Map<UserKey, String> map = new HashMap<>();

        UserKey oldKey = new UserKey(1);
        map.put(oldKey, "An");

        System.out.println("get bằng key tương đương: "
                + map.get(new UserKey(1)));

        UserKey newKey = new UserKey(2);
        System.out.println("get với id mới: " + map.get(newKey));
        System.out.println("get với id cũ: " + map.get(oldKey));

        String oldValue = map.remove(oldKey);
        map.put(newKey, oldValue);

        System.out.println("get sau chuyển key: " + map.get(newKey));
        System.out.println("size: " + map.size());
        System.out.println("chứa key cũ: " + map.containsKey(oldKey));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StableHashMapKeyDemo.java
java StableHashMapKeyDemo
~~~

Kết quả:

~~~text
get bằng key tương đương: An
get với id mới: null
get với id cũ: An
get sau chuyển key: An
size: 1
chứa key cũ: false
~~~

**Điểm khác biệt:** `UserKey(1)` không bị sửa thành `UserKey(2)`. Khi nghiệp vụ muốn thay đổi định danh, ứng dụng **xóa entry bằng khóa cũ trước**, rồi chèn bằng **đối tượng khóa mới**. Trạng thái bảng băm và quy tắc tra cứu được duy trì.

Trong tình huống tổng quát, `remove(oldKey)` có thể trả `null` vì không tồn tại key *hoặc* vì key có giá trị `null`. Nếu map cho phép giá trị `null`, kiểm tra `containsKey(oldKey)` trước khi chuyển khóa để phân biệt hai tình huống. Đồng thời xác định rõ chính sách khi `newKey` đã tồn tại, vì `put(newKey, value)` có thể ghi đè dữ liệu cũ. Ví dụ trên có dữ liệu đơn giản nên không gặp hai vấn đề này.

### 6.1. Record không tự tạo bất biến sâu

Không nên suy luận rằng mọi `record` đều là khóa an toàn. Ví dụ:

~~~java
record ArrayKey(int[] values) {}
~~~

Mảng vẫn thay đổi được. Hơn nữa, `equals/hashCode` được sinh tự động cho thành phần kiểu mảng sử dụng cách so sánh/hash của chính tham chiếu mảng, **không phải nội dung mảng**. Nếu nghiệp vụ muốn so sánh theo từng phần tử, cần tự xác định quan hệ bình đẳng và bảo vệ trạng thái theo quan hệ đó. Trường reference dạng collection hoặc bean mutable trong `record` cũng cần xem xét alias và cách tính `equals/hashCode`.

Với định danh đơn giản, `record UserKey(int id)` là ví dụ tốt vì `int` không có đối tượng mutable lồng bên trong.

### 6.2. Giá trị (value) có thể thay đổi; khóa nên ổn định

Một cách thiết kế khác là lưu đối tượng nghiệp vụ mutable làm **value**, và dùng ID bất biến làm **key**:

~~~java
// Đoạn minh họa bên trong một phương thức; account là đối tượng nghiệp vụ.
Map<Long, Account> byId = new HashMap<>();
byId.put(account.getId(), account);
account.setDisplayName("Tên mới"); // Không đổi Long key
~~~

`Account` ở đây chỉ là tên lớp nghiệp vụ minh họa, không phải lớp của JDK hay chương trình chạy độc lập. Nếu ID chính nó cần thay đổi, phải xác định cách di chuyển entry trong map theo khóa cũ và khóa mới. Không được đổi đối tượng khóa đang lưu theo cách ảnh hưởng đến `equals/hashCode`.

## 7. Nếu bắt buộc dùng lớp khóa có trường mutable?

Có những lớp có setter nhưng vẫn có thể được dùng làm khóa nếu **chỉ những trường không ảnh hưởng đến `equals/hashCode` được phép đổi trong lúc làm key**. Ví dụ một `User` có `final long id` dùng cho `equals/hashCode` và `displayName` mutable *không tham gia* hai phương thức: đổi tên không tự phá vỡ tra cứu theo ID.

Tuy nhiên, cần thỏa mãn đồng thời:

- Quy tắc `equals` và `hashCode` dùng chính xác cùng tiêu chí nhận diện và giữ ổn định trong suốt vòng đời làm khóa.
- Không tồn tại setter, alias ngoài lớp hoặc reference lồng bên trong có thể âm thầm làm thay đổi những thông tin nhận diện đó.
- Các trường dùng trong so sánh không phụ thuộc vào trạng thái ngoài đối tượng có thể thay đổi, chẳng hạn cấu hình, thời gian hoặc collection mutable.
- Các đối tượng được coi là bằng nhau luôn cho cùng hash. Tránh sử dụng dữ liệu thay đổi hoặc các quy tắc không ổn định trong tính hash.

**Chú ý:** dùng `final` cho biến giữ khóa, ví dụ `final MutableKey key = ...`, chỉ ngăn gán biến sang đối tượng khác; `key.setId(2)` vẫn hợp lệ. Dùng `final` trên một trường tham chiếu cũng không biến đối tượng được tham chiếu thành bất biến. Với mảng hoặc collection tham gia nhận diện, cần copy phòng vệ và/hoặc dùng cấu trúc thực sự bất biến.

### Khi đã lỡ làm hỏng HashMap

Không có phương thức “làm mới hash cho tất cả khóa đang bị thay đổi” mà `Map` cam kết xử lý mọi trạng thái hỏng. Có thể:

1. Nếu biết chính xác trạng thái nhận diện cũ và chưa phát sinh entry trùng bất thường, phục hồi khóa về trạng thái cũ **chỉ như biện pháp xử lý tình huống được kiểm soát**, xóa entry bằng trạng thái cũ rồi chuyển sang khóa bất biến mới.
2. Nếu còn dữ liệu nguồn đáng tin cậy (database, danh sách đối tượng có ID ổn định, bản snapshot), **tạo map mới** bằng các khóa bất biến được dựng từ nguồn đó. Xác định chính sách khi nhiều entry quy về cùng khóa logic.
3. Nếu phải duyệt `entrySet()` của map lỗi để cứu dữ liệu, phải kiểm tra trùng khóa, giá trị xung đột và alias; đây không phải cách phục hồi tự động bảo đảm không mất dữ liệu.

Ngay cả `new HashMap<>(damagedMap)` cũng **không phải** một bản vá thiết kế: nó không làm khóa thành bất biến và có thể hợp nhất các khóa được xem là bằng nhau ở trạng thái hiện tại hoặc duy trì nguy cơ thay đổi về sau.

## 8. Quy trình gỡ lỗi trong dự án thật

Khi thấy `get(key)` trả `null` bất ngờ, nên kiểm tra theo trình tự:

1. **Kiểm tra đúng instance của map:** biến đang đọc có trỏ tới map mà trước đó đã `put` không? Có ai `clear` hoặc `remove` không?
2. **Phân biệt không tìm được khóa với giá trị null:** dùng `containsKey(key)` và xác định map có cho lưu null value không.
3. **Ghi log các thuộc tính nhận diện trước và sau:** nếu có thể, log ID, các trường tham gia `equals/hashCode` và hash tại hai thời điểm; không chỉ log `toString()`.
4. **Kiểm tra setter và alias:** đối tượng khóa có bị thay đổi từ một chỗ khác sau `put` không? Có collection/mảng lồng bên trong tham gia so sánh không?
5. **Duyệt `entrySet()` phục vụ chẩn đoán:** xem entry còn tồn tại không, nhận diện khóa hiện tại ra sao. Việc tìm thấy đối tượng trong vòng lặp không chứng minh `get(key)` phải tìm được.
6. **Kiểm tra hiện thực `equals/hashCode`:** hai đối tượng được xem là bằng nhau phải có cùng hash; kiểm tra tính đối xứng, bắc cầu, ổn định và xử lý `null` đúng hợp đồng.
7. **Thay đổi thiết kế rồi tái kiểm thử:** dùng key immutable hoặc tách key/value. Đừng vá bằng cách chèn lại cùng khóa mutable để che triệu chứng.

Lỗi này không được giải quyết chỉ bằng cách chuyển sang `ConcurrentHashMap` hay khóa đồng bộ: collection concurrent xử lý truy cập đa luồng, nhưng **không biến trạng thái nhận diện của một đối tượng khóa mutable thành bất biến**. Nếu khóa có thể đổi trong khi đang được dùng, vấn đề thiết kế vẫn còn.

## 9. Bài tập tự kiểm tra

### Câu 1: Cùng object reference có bảo đảm `get` thành công?

**Không.** Ví dụ ở mục 3 dùng cùng biến `key` cả khi `put` và `get`. HashMap không dựa vào việc duyệt tất cả phần tử và so sánh identity để tìm entry.

### Câu 2: Nếu sửa trường không tham gia `equals/hashCode` thì sao?

Nếu trường đó thực sự không ảnh hưởng trực tiếp hoặc gián tiếp tới hash và quan hệ bằng nhau, riêng sự thay đổi đó không làm hỏng lập chỉ mục khóa. Tuy nhiên, bản thân chương trình vẫn cần xử lý đúng các yêu cầu khác như thread safety.

### Câu 3: Có nên dùng `System.identityHashCode(key)` cho khóa?

Không nên xem đây là cách sửa lỗi chung. Identity hash chỉ gắn với nhận diện đối tượng và không phản ánh bình đẳng theo giá trị. Chọn `equals/hashCode` theo hợp đồng nhận diện khóa. Nếu bài toán cần so sánh theo identity thật sự, cân nhắc `IdentityHashMap` với hiểu biết rõ về ngữ nghĩa `==` và các khác biệt so với `HashMap`; nó không phù hợp để thay thế một cách máy móc.

### Câu 4: Vì sao `HashSet` cũng có thể gặp lỗi tương tự?

Trong triển khai Java thông dụng, `HashSet` dựa trên cấu trúc băm. Nếu thêm một đối tượng rồi thay đổi trạng thái ảnh hưởng tới `hashCode/equals`, `contains` hoặc `remove` có thể thất bại ngay cả khi phần tử vẫn còn trong lần duyệt. Đây là cùng lớp lỗi **thay đổi trạng thái nhận diện khi đang lưu trong collection dựa trên hash**.

### Câu 5: Có cần bắt buộc mọi đối tượng làm key phải immutable?

Hợp đồng `Map` không bắt buộc kiểu khóa được khai báo `final` hay hoàn toàn immutable. Điều kiện quan trọng là **thông tin ảnh hưởng đến bình đẳng và mã băm phải giữ ổn định** khi khóa đang trong map. Trong thực hành, thiết kế immutable là cách bảo đảm điều này rõ ràng và dễ review nhất.

## 10. Checklist nhớ nhanh

- Trước `put`: biết những trường nào tham gia `equals/hashCode`.
- Trong thời gian khóa nằm trong map: **không thay đổi** các trường đó hoặc dữ liệu mutable mà chúng phụ thuộc.
- Khi muốn thay “ID khóa”: dùng **khóa mới**, xóa bằng **khóa cũ còn nguyên trạng** rồi chèn lại theo chính sách xử lý xung đột.
- Khi `get` trả `null`: đối chiếu `containsKey`, `size`, `entrySet` và trạng thái khóa; đừng kết luận ngay dữ liệu đã biến mất.
- Trong thiết kế mới: ưu tiên ID primitive/`String`/kiểu immutable hoặc `record` chỉ chứa thành phần nhận diện bất biến.

**Ghi nhớ:** `HashMap` không theo dõi setter để tự lập chỉ mục lại. Khóa có thể vẫn nằm trong map nhưng bị “thất lạc” khi tra cứu vì **trạng thái dùng để xác định hash/equals đã thay đổi sau lúc chèn**.
