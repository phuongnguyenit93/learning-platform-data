# HashMap xử lý va chạm khóa trong triển khai JDK hiện đại

## 1. Mục tiêu và phạm vi

`HashMap<K,V>` thuộc `java.util` là bản triển khai bảng băm của giao diện `Map<K,V>`: từ một **khóa** (key), chương trình tìm được **giá trị** (value). Khi các khóa phân bố tương đối đều trên các bucket, những thao tác cơ bản như `put` và `get` thường có thời gian trung bình gần **O(1)**. Nhưng bảng băm không thể tránh hoàn toàn **va chạm** (collision), và xử lý va chạm là phần quan trọng trong thiết kế `HashMap`.

Trong OpenJDK hiện đại, một bucket có thể dùng **chuỗi nút (linked list)** hoặc **nút cây đỏ–đen (red-black tree bin)** khi số lượng phần tử va chạm đủ lớn và bảng đủ rộng. Khi bảng tăng kích thước, các nút lại được **phân phối vào bucket mới**. Đây là những chi tiết triển khai giúp cải thiện hiệu năng trong nhiều tình huống; ứng dụng vẫn phải dựa vào **hợp đồng công khai** của `Map`/`HashMap` thay vì phụ thuộc cấu trúc nội bộ.

Bài học giúp bạn trả lời:

1. Va chạm `hashCode()` và va chạm **bucket** khác nhau như thế nào?
2. HashMap chọn bucket và kiểm tra `equals()` ra sao khi thêm, tìm, cập nhật hoặc xóa khóa?
3. Tại sao triển khai OpenJDK có **list bin**, **tree bin**, các mốc `8`, `6`, `64` và bước `resize`?
4. Vì sao cây đỏ–đen cải thiện nhiều trường hợp nhưng **không** biến mọi khóa băm tệ thành bảo đảm O(log n) tuyệt đối?
5. Thiết kế `equals`/`hashCode`, khóa bất biến, capacity/load factor và xử lý đồng thời thế nào?
6. Kiểm thử đúng tính chính xác khi có nhiều khóa cố tình trùng hash, không dựa vào reflection của nội bộ JDK.

**Phiên bản và mức cam kết:** Các ví dụ được thiết kế cho **Java 17+**. Phần về ngưỡng treeification và biểu thức tính bucket được đối chiếu với mã nguồn **OpenJDK JDK 25u**; đây là **chi tiết của một triển khai**, có thể thay đổi ở JDK, vendor hoặc bản sửa tương lai. Các quy tắc `Map`/`HashMap` như khóa duy nhất theo `equals`, `null`, thứ tự duyệt không được bảo đảm và tính không đồng bộ là hợp đồng công khai vẫn áp dụng hiện nay.

## 2. Từ `hashCode()` đến bucket: hiểu đúng hai loại va chạm

Hai đối tượng có thể liên quan đến va chạm theo hai cách:

- **Va chạm hash:** `a.hashCode() == b.hashCode()` dù `!a.equals(b)`. Phương thức `hashCode()` trả `int`, còn tập khóa có thể lớn hơn rất nhiều, nên không thể bảo đảm hash riêng cho mọi khóa.
- **Va chạm bucket:** sau khi trộn bit và tính chỉ số bảng, **hai mã hash khác nhau** vẫn có thể chọn cùng một bucket vì số bucket hữu hạn.

Va chạm hash chắc chắn khiến hai khóa cùng đi đến bucket trong một triển khai tính bucket theo hash; nhưng va chạm bucket không nhất thiết có cùng `hashCode()`.

### 2.1. Biểu thức tính bucket trong OpenJDK JDK 25u

Mã nguồn dùng kỹ thuật trộn bit đơn giản (diễn giải tương đương, không phải API công khai):

```java
int h = key.hashCode();
int spread = h ^ (h >>> 16);
int index = (capacity - 1) & spread;
```

Với khóa `null`, triển khai này dùng hash nội bộ bằng `0`. Khi đã cấp phát, `capacity` là độ dài mảng bucket và là lũy thừa của hai. Phép `& (capacity - 1)` chọn các bit thấp tương ứng để tính chỉ số trong bảng.

**Vì sao có `h ^ (h >>> 16)`?** Một số kiểu khóa có biến thiên chủ yếu ở các bit cao của `hashCode`. Nếu chỉ lấy bit thấp với một mảng ngắn, các khóa dễ rơi vào cùng bucket. Trộn một phần bit cao xuống thấp giúp phân tán chúng tốt hơn với chi phí nhỏ, nhưng **không sửa được** một `hashCode()` luôn trả cùng một hằng số.

Ví dụ có hai hash khác nhau: `1` và `17`.

```text
capacity = 16:
    (16-1) & spread(1)  = 1
    (16-1) & spread(17) = 1
    => Hai hash khác nhau nhưng cùng bucket số 1.

capacity = 32:
    (32-1) & spread(1)  = 1
    (32-1) & spread(17) = 17
    => Khi bảng rộng hơn, chúng vào hai bucket khác nhau.
```

Những kết quả trên đúng với **biểu thức nội bộ được trình bày**, không phải một phương thức `HashMap.bucketIndex()` mà ứng dụng có thể gọi. Không dùng công thức này để viết logic nghiệp vụ phụ thuộc chỉ số bucket, vì API công khai không bảo đảm công thức sẽ giữ nguyên mãi.

### 2.2. Va chạm không đồng nghĩa hai khóa bằng nhau

Ví dụ `Alice` và `Bob` tình cờ có cùng `hashCode()` vẫn là **hai key khác nhau** nếu `equals` trả `false`. HashMap phải giữ được **hai mapping**.

Ngược lại, nếu tạo một đối tượng khác nhưng `equals` cho rằng nó bằng khóa đã tồn tại, `put` sẽ **thay giá trị cũ** thay vì thêm mapping mới. Chỉ `hashCode` bằng nhau **không đủ** để coi hai key là trùng.

## 3. Các nút trong bucket và xử lý va chạm cơ bản

Một cách hình dung:

```text
Bảng có nhiều bucket:
index 0    -> null
index 1    -> Node(key=A, value=...) -> Node(key=B, value=...) -> null
index 2    -> null
index 3    -> Node(key=C, value=...) -> null
...        -> ...

Trong ví dụ, A và B rơi cùng bucket nhưng A không equals B.
```

Trong OpenJDK JDK 25u, nút thông thường chứa thông tin tương đương: **hash đã trộn**, **key**, **value**, **next**. Những trường cụ thể này là nội bộ triển khai; code ứng dụng chỉ thấy `Map.Entry<K,V>` qua API.

### 3.1. `put(key, value)` khi bucket đã có phần tử

Quy trình khái quát:

1. Tính hash nội bộ cho key, xác định chỉ số bucket.
2. Nếu bucket trống, tạo mapping mới.
3. Nếu bucket có nút, kiểm tra khóa hiện tại có cùng hash phù hợp và **bằng nhau theo `equals`** không.
4. Nếu tìm được khóa tương đương, cập nhật value và trả **giá trị cũ**; `size()` không tăng.
5. Nếu không có khóa bằng nhau, thêm nút mới vào cấu trúc của bucket (list hoặc tree).
6. Sau khi thêm mapping mới, cập nhật `size` và nếu cần thì `resize` theo ngưỡng bảng.

**Không có quy tắc “hai khóa cùng hash thì một khóa bị ghi đè”.** Việc ghi đè dựa vào **tính bằng nhau của khóa**, không chỉ vào hash.

### 3.2. `get(key)` khi bucket có nhiều mapping

Quy trình khái quát:

1. Dùng hash để định vị bucket.
2. Tìm mapping có khóa tương đương theo `equals` trong bucket.
3. Với list bin, duyệt các nút cần thiết; với tree bin, triển khai có thể dùng quy tắc tìm trên cây.
4. Trả `value` nếu có mapping hoặc `null` nếu không có (và nếu value thực sự được lưu là null, `get` cũng trả null).

`HashMap` **cho phép value null**, vì vậy `map.get(k) == null` không đủ kết luận `k` không tồn tại. Khi cần phân biệt, dùng `map.containsKey(k)`.

### 3.3. `remove(key)` khi có va chạm

`remove` xác định bucket theo hash, tìm **khóa tương đương**, rồi xóa đúng một mapping. Những khóa khác chỉ tình cờ nằm cùng bucket vẫn còn nguyên. Vì vậy việc kiểm thử collision cần bao gồm **thêm, tra cứu, cập nhật, xóa**, không chỉ đếm size ngay sau thêm.

## 4. Hợp đồng `equals` / `hashCode` quyết định tính đúng đắn

Java quy định một số quan hệ quan trọng:

- Nếu `a.equals(b) == true` thì **`a.hashCode() == b.hashCode()`**.
- Chiều ngược lại **không đúng**: hai hash bằng nhau không buộc hai khóa `equals` bằng nhau.
- `equals` cần tuân thủ phản xạ, đối xứng, bắc cầu, nhất quán và xử lý null đúng hợp đồng.
- `hashCode` phải nhất quán khi thông tin dùng để so bằng nhau không thay đổi.
- Khi override `equals` để định nghĩa đồng nhất nghiệp vụ, **override `hashCode` tương ứng**.

Ví dụ khóa tốt là một record bất biến chứa ID:

```java
record UserKey(long id) {}
```

Trong Java 17+, record tự tạo `equals` và `hashCode` dựa trên các thành phần. Nếu hai `UserKey(42)` được tạo ở hai vị trí khác nhau, chúng có thể được xem là cùng khóa vì bằng nhau theo giá trị.

**Lưu ý về record:** “record là bất biến” chỉ đúng ở mức **tham chiếu tới thành phần** (shallow); nếu thành phần là mảng hoặc đối tượng mutable, bạn vẫn phải thiết kế sự bất biến và ngữ nghĩa `equals`/`hashCode` cho đúng. Mảng mặc định so bằng tham chiếu, không so nội dung; đừng đưa mảng mutable làm khóa rồi cho rằng record tự xử lý deep equality.

### 4.1. Khóa mutable là một lỗi rất nguy hiểm

Giả sử key có `id` thay đổi và `hashCode` phụ thuộc `id`:

```java
final class MutableKey {
    int id;
    MutableKey(int id) { this.id = id; }
    @Override public int hashCode() { return Integer.hashCode(id); }
    @Override public boolean equals(Object obj) {
        return obj instanceof MutableKey other && id == other.id;
    }
}
```

Đây là lớp **anti-pattern minh họa**; không phải thiết kế key được khuyến nghị.

Nếu bạn `map.put(key, value)` rồi đổi `key.id`, key có thể không tìm lại được ở bucket cũ, vì hash lúc tra cứu đã khác hash lưu khi thêm. Ngay cả việc dùng chính đối tượng key ban đầu cũng không cứu được sự bất nhất này. Theo hợp đồng `Map`, hành vi không được bảo đảm nếu thay đổi key theo cách ảnh hưởng `equals` khi key đang nằm trong map.

**Cách sửa:** chọn key bất biến và ổn định trong toàn bộ thời gian tồn tại mapping; tránh dùng các field bị thay đổi làm thành phần nhận dạng khóa.

### 4.2. `Comparable` có vai trò gì?

Trong tree bin của OpenJDK, khi cần phân biệt nút có hash trùng nhau, triển khai **có thể** tận dụng thứ tự tự nhiên của các khóa `Comparable` có kiểu phù hợp. Cách này giúp định hướng tìm kiếm trong nhiều tình huống.

Nếu tự định nghĩa `Comparable<K>` cho key, nên làm cho `compareTo(a,b) == 0` nhất quán với `equals(a,b)` khi có thể. Không cài `compareTo` chỉ để tác động đến nội bộ HashMap; thiết kế thứ tự tự nhiên đúng nghiệp vụ trước.

**Quan trọng:** Một key không cần triển khai `Comparable` mới dùng được trong `HashMap`. Việc có Comparable giúp tối ưu đường tìm ở một số trường hợp va chạm, nhưng `HashMap` vẫn cần dựa vào `equals` để xác nhận khóa thực sự bằng nhau.

## 5. List bin và tree bin trong OpenJDK hiện đại

### 5.1. Vì sao list bin không đủ khi va chạm dày đặc?

Khi nhiều khóa vào cùng một bucket, danh sách liên kết phải xét nhiều nút để tìm phần tử. Nếu bucket có `k` phần tử, tìm ở cuối list có thể cần **O(k)** bước, đặc biệt khi hash và equals không phân tán tốt.

Một đối tượng `HashMap` có thể vẫn có tổng số mapping vừa phải nhưng **một bucket quá đông**. Chỉ nhìn `map.size()` không biết được tình trạng phân bố giữa các bucket.

Để giảm chi phí với các bucket có nhiều nút, OpenJDK JDK 25u có **TreeNode** và chuyển bucket từ list sang cấu trúc **cây đỏ–đen** khi điều kiện phù hợp. Cây tự cân bằng, hỗ trợ định hướng tìm kiếm tốt hơn cho trường hợp khóa có thể so sánh hữu ích.

### 5.2. Các hằng số đáng biết — nhưng là chi tiết triển khai

Trong mã nguồn `HashMap.java` của **OpenJDK JDK 25u** có:

| Hằng số nội bộ | Giá trị ở nguồn tham chiếu | Vai trò |
| --- | --- | --- |
| `TREEIFY_THRESHOLD` | `8` | Mốc nội bộ liên quan đến chuyển một list bin quá dài sang tree bin |
| `UNTREEIFY_THRESHOLD` | `6` | Mốc được dùng khi chuyển tree bin thành list trong một số trường hợp, nhất là lúc phân chia khi resize |
| `MIN_TREEIFY_CAPACITY` | `64` | Bảng phải có ít nhất 64 bucket mới treeify; nếu nhỏ hơn, quá trình có thể ưu tiên resize |

**Đừng diễn giải sai “đủ 8 phần tử thì chắc chắn ngay lập tức thành cây”.** Với đường thêm thông thường `putVal` trong mã nguồn được tham chiếu, lời gọi `treeifyBin` xảy ra khi việc thêm nút mới làm một list bin đã có 8 nút tăng lên **9 nút**, và còn phụ thuộc capacity/đường xử lý. Với capacity dưới `64`, `treeifyBin` ưu tiên **resize bảng** thay vì lập tức chuyển sang tree bin. Vì vậy không dùng `map.size() == 8` hay `== 9` để khẳng định chắc chắn bên trong đang là cây.

**`UNTREEIFY_THRESHOLD = 6` cũng không có nghĩa cứ `remove` còn đúng 6 phần tử là một tree bin bắt buộc đổi thành list ngay.** Việc chuyển ngược phụ thuộc đường đi triển khai, bao gồm tách tree bin khi resize hoặc cấu trúc sau xóa; không coi con số là bảo đảm của API.

Các con số này **không xuất hiện như hằng số public của `HashMap`** để người dùng dựa vào. Chúng có thể khác trong các phiên bản/vender JDK. Kiến thức bền vững là: **va chạm được giữ đúng ngữ nghĩa; bucket có thể đổi cấu trúc để cải thiện hiệu năng, nhưng không làm thay đổi kết quả `Map`**.

### 5.3. Tại sao cây đỏ–đen không phải lời hứa O(log n) tuyệt đối?

Cây đỏ–đen giữ chiều cao được cân bằng theo số nút. Nhưng ở trường hợp **tất cả khóa đều có hash giống hệt nhau và không thể định hướng tìm kiếm một cách phù hợp theo thứ tự khóa**, việc xác nhận `equals` của một key tìm kiếm có thể phải kiểm tra nhiều nút/subtree.

Do đó:

- Với khóa có hash phân tán tốt, `get`/`put` có hiệu năng trung bình kỳ vọng gần **O(1)**.
- Với một list bin có `k` nút, tìm kiếm có thể là **O(k)**.
- Với tree bin, có thể đạt hành vi gần **O(log k)** theo cấu trúc cây khi có đủ thông tin thứ tự/phân biệt khóa, nhưng **không hứa O(log k) trong mọi trường hợp đối tượng khóa phi Comparable cùng hash**.
- Hash cực tệ vẫn làm tăng chi phí `equals`, xây cây, bộ nhớ và resize; treeification không thay thế thiết kế hash đúng.

Kết luận thực dụng: **hãy ưu tiên một `hashCode` phân bố đủ tốt**. Tree bin là cơ chế bảo vệ/giảm thiểu, không phải giấy phép dùng `hashCode() { return 1; }` trong ứng dụng thật.

## 6. Resize, load factor và sự thay đổi bucket

`HashMap` có hai tham số ảnh hưởng phân bố và chi phí:

- **Capacity:** số bucket hiện tại, không phải `size()`. `size()` là số mapping.
- **Load factor:** mức tải mục tiêu dùng để quyết định khi nào tăng capacity.

Trong các cấu hình mặc định của OpenJDK JDK 25u:

- Initial capacity mặc định khi cấp phát là **16 bucket**.
- Load factor mặc định là **0.75**.
- Khi ngưỡng tương ứng bị vượt, bảng thường được **tăng gấp đôi** (trong giới hạn hỗ trợ).

Với capacity = 16 và load factor = 0.75, ngưỡng thông dụng là 12; thêm mapping thứ 13 thường dẫn đến resize. Đừng đồng nhất ngưỡng tổng số mapping với ngưỡng treeify **tại một bucket**. Đó là **hai cơ chế khác nhau**.

### 6.1. Khi resize, các khóa trong cùng bucket có thể tách ra

OpenJDK dùng bảng có kích thước lũy thừa của 2. Khi capacity từ `oldCap` lên `2 * oldCap`, các nút từ bucket cũ ở vị trí `j` có thể:

- **Giữ nguyên** chỉ số `j` nếu bit tương ứng `oldCap` trong hash không bật.
- **Chuyển** sang `j + oldCap` nếu bit đó bật.

Hình minh họa:

```text
capacity = 16:
    hash 1  -> bucket 1
    hash 17 -> bucket 1  (va chạm bucket)

capacity = 32:
    hash 1  -> bucket 1
    hash 17 -> bucket 17 (không còn va chạm bucket)
```

Do đó **resize đôi khi làm giảm va chạm bucket**, kể cả khi không đổi `hashCode()` của khóa. Nhưng nếu tất cả khóa đều trả **cùng một hash**, resize đơn thuần không thể tách chúng theo các bit hash.

**Chi tiết kỹ thuật:** Mã nguồn OpenJDK 25u có thể phân phối lại các node đã lưu hash nội bộ bằng phép kiểm bit mà **không nhất thiết gọi lại `key.hashCode()` cho từng khóa** ở mọi lần resize. Tài liệu API thường mô tả tổng quát quá trình này là “rehash”. Đừng suy diễn thuật ngữ đó thành cam kết số lần gọi phương thức `hashCode` trên key.

### 6.2. Chọn initial capacity như thế nào?

Nếu dự đoán cần lưu nhiều mapping, chọn capacity hợp lý để giảm số lần resize. Ví dụ:

```java
Map<String, Integer> counts = new HashMap<>(128, 0.75f);
```

Đây là đoạn minh họa, cần import `java.util.*`. Constructor nhận initial capacity (số bucket mục tiêu), **không phải số mapping được bảo đảm không resize**. Một số JDK hiện đại có factory `HashMap.newHashMap(expectedNumberOfMappings)` để diễn đạt số mapping dự kiến; không dùng nó trong ví dụ cần biên dịch tương thích Java 17 vì phương thức này được giới thiệu ở phiên bản mới hơn.

Capacity cao quá có thể tốn bộ nhớ và khiến việc duyệt `HashMap` chậm hơn do phải quét các bucket trống. Theo tài liệu Oracle, thời gian duyệt collection views phụ thuộc cả **capacity + size**. Không chọn capacity khổng lồ chỉ để hy vọng tránh va chạm; cần cân bằng với số mapping và phân phối hash.

**Đừng tự chỉnh load factor** như một cách “sửa” hàm hash kém. Với các key liên tục có cùng hash, load factor thấp và resize nhiều vẫn không giải quyết gốc rễ. Load factor mặc định `0.75` thường là lựa chọn hợp lý, trừ khi có dữ liệu benchmark và yêu cầu bộ nhớ rõ ràng.

## 7. Ví dụ Java 17+ hoàn chỉnh: cố ý tạo va chạm nhưng kết quả vẫn đúng

Mục tiêu ví dụ là kiểm tra **hợp đồng public** của HashMap, không dùng reflection can thiệp vào `table`, `TreeNode` hay số bucket nội bộ. Để cố ý tạo va chạm, record `CollisionKey` sẽ trả một `hashCode` cố định. **Đây là key giả dùng cho kiểm thử, tuyệt đối không phải gợi ý thiết kế key thực tế.**

Tạo tệp **`HashCollisionDemo.java`**:

```java
import java.util.*;
import java.util.stream.*;

public class HashCollisionDemo {
    // Chỉ dùng trong test: mọi key cố tình có hashCode() giống nhau.
    record CollisionKey(int id) implements Comparable<CollisionKey> {
        @Override
        public int hashCode() {
            return 7;
        }

        @Override
        public int compareTo(CollisionKey other) {
            return Integer.compare(this.id, other.id);
        }
        // equals() được record sinh từ trường id.
    }

    static void require(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    // Mô hình hóa đúng công thức spread/index của OpenJDK 25u;
    // đây KHÔNG phải API public của HashMap.
    static int bucketFor(int hashCode, int capacity) {
        int spread = hashCode ^ (hashCode >>> 16);
        return (capacity - 1) & spread;
    }

    public static void main(String[] args) {
        System.out.println("bucketAt16=" +
                bucketFor(1, 16) + "/" + bucketFor(17, 16));
        System.out.println("bucketAt32=" +
                bucketFor(1, 32) + "/" + bucketFor(17, 32));

        Map<CollisionKey, String> map = new HashMap<>(64, 0.75f);
        for (int i = 0; i < 20; i++) {
            map.put(new CollisionKey(i), "v" + i);
        }

        require(map.size() == 20, "collision keys preserved");
        System.out.println("collidingKeys=" + map.size());
        System.out.println("getFreshEquivalentKey=" +
                map.get(new CollisionKey(19)));

        // Đối tượng key mới nhưng equals theo id là true -> ghi đè.
        System.out.println("replacePrevious=" +
                map.put(new CollisionKey(3), "updated"));
        System.out.println("sizeAfterReplace=" + map.size());
        System.out.println("updatedValue=" +
                map.get(new CollisionKey(3)));

        // Xóa đúng một key; các key khác trong bucket vẫn tra được.
        System.out.println("removedValue=" +
                map.remove(new CollisionKey(10)));
        System.out.println("sizeAfterRemove=" + map.size());

        boolean complete = IntStream.range(0, 20)
                .filter(i -> i != 10)
                .allMatch(i -> map.get(new CollisionKey(i)) != null);
        require(complete && !map.containsKey(new CollisionKey(10)),
                "remaining keys");
        System.out.println("allRemainingFound=" + complete);

        // HashMap cho phép một null key và cả null value.
        Map<String, Integer> nullable = new HashMap<>();
        nullable.put(null, 5);
        nullable.put("known", null);
        System.out.println("nullKeyValue=" + nullable.get(null));
        System.out.println("containsNullValueKey=" +
                nullable.containsKey("known"));
        System.out.println("missingLookup=" + nullable.get("absent"));

        // Kiểm tra nhiều va chạm, không dựa vào chi tiết TreeNode.
        Map<CollisionKey, Integer> many = new HashMap<>(64);
        for (int i = 0; i < 1000; i++) {
            many.put(new CollisionKey(i), i);
        }
        for (int i = 0; i < 1000; i++) {
            require(Objects.equals(
                    many.get(new CollisionKey(i)), i),
                    "stress " + i);
        }
        System.out.println("manyCollisionLookups=PASS");
        System.out.println("ALL TESTS PASSED");
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac HashCollisionDemo.java
java HashCollisionDemo
```

**Stdout chính xác:**

```text
bucketAt16=1/1
bucketAt32=1/17
collidingKeys=20
getFreshEquivalentKey=v19
replacePrevious=v3
sizeAfterReplace=20
updatedValue=updated
removedValue=v10
sizeAfterRemove=19
allRemainingFound=true
nullKeyValue=5
containsNullValueKey=true
missingLookup=null
manyCollisionLookups=PASS
ALL TESTS PASSED
```

### 7.1. Giải thích cơ chế qua output

- `bucketAt16=1/1` và `bucketAt32=1/17` được tính bằng **mô hình công thức OpenJDK 25u**, minh họa rằng hai hash khác nhau có thể cùng bucket ở capacity nhỏ rồi tách khi resize.
- `CollisionKey` là record có `equals` theo `id` và `hashCode` cố định `7`. Với 20 `id` khác nhau, tất cả có cùng hash nhưng là **20 khóa không bằng nhau**, nên `size()==20`.
- `getFreshEquivalentKey=v19` chứng minh tra cứu bằng đối tượng `new CollisionKey(19)` vẫn tìm được mapping, dù đó không phải object cũ theo `==`.
- `replacePrevious=v3` chứng minh `put` tìm đúng khóa tương đương và trả giá trị trước đó; `sizeAfterReplace=20` vì cập nhật không tăng số mapping.
- `removedValue=v10` và `sizeAfterRemove=19` chứng minh `remove` chỉ loại một key; những key còn lại vẫn được tra cứu.
- `nullKeyValue=5` xác nhận HashMap cho phép một khóa null. `containsNullValueKey=true` xác nhận key `"known"` tồn tại dù value bằng null.
- `missingLookup=null` cho thấy cần `containsKey` khi phân biệt key vắng mặt với key có value null.
- `manyCollisionLookups=PASS` xác nhận một nghìn khóa được giữ và tìm lại bằng khóa tương đương. Đây là test **tính đúng** dưới va chạm, không phải benchmark và **không xác nhận trực tiếp** nội bộ hiện là list hay tree.

### 7.2. Vì sao `Comparable` được thêm vào khóa test?

`CollisionKey implements Comparable<CollisionKey>` với `compareTo` dựa trên `id`. Điều này tạo một thứ tự phù hợp với `equals` do record sinh, giúp OpenJDK dùng đường tìm kiếm hữu ích khi có tree bin. Nhưng:

- Code ứng dụng vẫn phải đúng trên bất kỳ `Map` nào đáp ứng hợp đồng, dù có hoặc không có tree bin.
- Không được thiết kế `compareTo` trái ngược `equals` để “ép” nội bộ HashMap hoạt động theo ý mình.
- Một key không Comparable vẫn hoàn toàn hợp lệ; key không cần Comparable để được dùng trong HashMap.

### 7.3. Tại sao không in trực tiếp kiểu `TreeNode`?

Trường `table` và các class node bên trong là **chi tiết private/package-private**, không phải API ứng dụng. Kỹ thuật reflection vào `java.base/java.util` có thể bị chặn bởi module encapsulation, đòi hỏi cờ mở module và khiến test phụ thuộc phiên bản JDK.

Trong ví dụ giáo dục, ta **đọc mã nguồn JDK để hiểu triển khai** và **kiểm thử API public để xác nhận ngữ nghĩa**. Nếu cần phân tích chi tiết nội bộ cho JVM cụ thể, hãy dùng công cụ chẩn đoán/JDK source phù hợp riêng; đừng biến reflection vào `HashMap.table` thành điều kiện để ứng dụng chạy đúng.

## 8. Điều gì xảy ra với `null` và khóa có hash bằng 0?

`HashMap` cho phép **một mapping với key null** và nhiều key non-null. Trong OpenJDK 25u, `hash(null)` trả 0, vì vậy key null được phân tuyến đến bucket 0; nhưng **bucket 0 không dành riêng chỉ cho null** — các khóa khác có hash sau trộn cho index 0 cũng có thể ở đó.

Khi tìm trong bucket, logic so khóa thích hợp phân biệt key null với key không null. Vì vậy:

```java
Map<String, Integer> m = new HashMap<>();
m.put(null, 5);
m.put("known", null);

boolean hasNullKey = m.containsKey(null);     // true
boolean hasKnownKey = m.containsKey("known"); // true
Integer absent = m.get("missing");           // null
Integer existingNull = m.get("known");       // null
```

Hai biến `absent` và `existingNull` có cùng giá trị `null`, nhưng chúng biểu thị tình trạng mapping **khác nhau**. Dùng `containsKey` khi cần kiểm tra sự tồn tại. Cần chú ý các phương thức như `computeIfAbsent` hoặc `putIfAbsent` có ngữ nghĩa xử lý key đã ánh xạ tới null riêng theo API; không đánh đồng null với “chưa từng tồn tại” trong toàn bộ thiết kế dữ liệu.

**Đối chiếu với `ConcurrentHashMap`:** `ConcurrentHashMap` **không** cho phép khóa hoặc giá trị null. Nó cũng có cơ chế phân phối hash, quản lý va chạm và đồng thời riêng; không áp các chi tiết nội bộ của `HashMap` sang `ConcurrentHashMap` một cách máy móc.

## 9. HashMap không bảo đảm thứ tự và không an toàn khi cập nhật đồng thời

### 9.1. Thứ tự duyệt không được cam kết

Ngay cả khi implementation đang dùng list hoặc tree và ở vài trường hợp có vẻ duyệt giống thứ tự chèn, **`HashMap` không bảo đảm insertion order**. Sau thêm/xóa/resize, thứ tự `keySet()`, `values()`, `entrySet()` có thể khác.

- Cần thứ tự chèn: cân nhắc `LinkedHashMap`.
- Cần thứ tự theo comparator: cân nhắc `TreeMap`.
- Cần chỉ một key tra value, không quan trọng thứ tự: `HashMap` thường phù hợp.

Không viết unit test kiểu `map.keySet().toString().equals("[a, b, c]")` nếu đối tượng thực là `HashMap` và yêu cầu không có thứ tự. Trong ví dụ hoàn chỉnh, kết quả in ra là các số, boolean và value tra theo key, **không in thứ tự duyệt Map**.

### 9.2. Không cập nhật HashMap từ nhiều thread mà không phối hợp

`HashMap` **không phải map đồng thời**. Khi nhiều thread truy cập và ít nhất một thread có thay đổi cấu trúc mà không có đồng bộ phù hợp, kết quả có thể sai hoặc không xác định theo cách ứng dụng mong đợi. Tree bin và resize **không biến HashMap thành thread-safe**.

Tùy yêu cầu:

- Chia sẻ map chỉ đọc sau khi khởi tạo an toàn: bảo đảm **safe publication** và không sửa cấu trúc/giá trị thiếu đồng bộ.
- Nhiều thread cùng cập nhật: cân nhắc `ConcurrentHashMap` hoặc cơ chế đồng bộ thích hợp.
- Bọc bằng `Collections.synchronizedMap` khi cần map đồng bộ, nhưng phải tuân thủ cách dùng và đồng bộ khi duyệt theo tài liệu.

Iterator của HashMap có tính chất **fail-fast best effort**. `ConcurrentModificationException` giúp phát hiện một số thay đổi cấu trúc ngoài ý muốn, **không phải bảo đảm phát hiện mọi data race** và không được dùng làm kỹ thuật điều phối luồng.

## 10. Những ngộ nhận phổ biến khi giải thích collision

| Ngộ nhận | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Hai key cùng hash thì key sau ghi đè key trước” | `hashCode` chỉ dùng định vị ứng viên | Cần `equals` để quyết định key tương đương |
| “HashMap không có collision vì đã trộn hash” | Không thể ánh xạ vô hạn khóa vào hữu hạn bucket mà tránh hết va chạm | Trộn hash chỉ giúp phân bố tốt hơn |
| “Trùng bucket nghĩa là `hashCode()` trùng” | Chỉ số bucket sử dụng mask theo capacity | Hai hash khác nhau vẫn có thể cùng bucket |
| “Cứ có 8 key trong Map là đã dùng tree” | Mốc áp dụng tại **một bin**, còn phụ thuộc capacity/đường thêm | Xem `TREEIFY_THRESHOLD`/`MIN_TREEIFY_CAPACITY` trong nguồn cụ thể |
| “Xóa còn 6 nút thì luôn quay về list ngay” | Đường untreeify phụ thuộc cách xóa/resize | `UNTREEIFY_THRESHOLD` không là cam kết chuyển tức thời |
| “Tree bin bảo đảm mọi truy vấn O(log n)” | Khóa đồng hash, không phân biệt thứ tự hữu ích có thể phải dò nhiều nhánh | Tối ưu hiệu năng không thay thế hash tốt |
| “Resize giải quyết được hash luôn hằng số” | Mọi key vẫn có cùng bit hash | Phải sửa thiết kế hash/key |
| “Capacity == size()” | Một bên là số bucket, một bên là số mapping | Phân biệt khi phân tích load factor |
| “Record luôn tạo key bất biến sâu” | Thành phần có thể là đối tượng mutable hoặc mảng | Chọn thành phần ổn định và ngữ nghĩa value phù hợp |
| “`get(k)==null` nghĩa không có key” | HashMap cho value null | Dùng `containsKey(k)` nếu cần biết tồn tại |
| “HashMap có thứ tự vì list nối đuôi” | Cấu trúc nội bộ không thành API order | Dùng LinkedHashMap/TreeMap cho yêu cầu thứ tự |
| “HashMap an toàn song song vì có tree” | Tree giải quyết tìm trong bucket, không giải quyết data race | Chọn cấu trúc thread-safe khi cần |

## 11. Quy trình kiểm thử collision nên có

Đừng chỉ thử vài key tình cờ trùng hash. Kiểm thử một cách có chủ đích để phân biệt các hợp đồng:

| Tình huống | Kỳ vọng đúng | Lỗi thường lộ ra |
| --- | --- | --- |
| Nhiều key khác nhau nhưng `hashCode` bằng nhau | Mỗi key có một mapping độc lập | Đánh đồng hash với equals |
| Hai instance bằng nhau theo `equals` | `put` cập nhật, không tăng size | Dựa vào tham chiếu `==` |
| Sau update một key | Chỉ value của key ấy đổi | Cập nhật nhầm nút khác trong bin |
| Sau xóa một key | Key ấy biến mất, các key còn lại vẫn tra được | Xóa sai liên kết |
| Key null, value null | Hành vi đúng theo hợp đồng HashMap | Nhầm get-null và key vắng |
| Hai hash 1 và 17 | Cùng bucket ở bảng 16, khác bucket ở bảng 32 theo công thức đang xét | Không hiểu mask/capacity |
| Nhiều lần thêm tới ngưỡng resize/treeification | Tất cả mapping vẫn đúng | Mất/trùng entry khi tái phân phối |
| Key mutable bị sửa | Đánh dấu là thiết kế sai, không coi kết quả `get` sau sửa là hợp đồng | Bỏ qua điều kiện ổn định hash/equals |
| Hash phân bố thông thường | Kết quả bằng oracle độc lập | Lỗi logic nghiệp vụ bị đổ cho collision |
| Map bị cập nhật đồng thời | Chỉ chạy với đồng bộ hoặc concurrent map hợp lệ | Data race bị nhầm thành lỗi hash |

**Oracle độc lập:** Với các key được đánh số `0..999`, sau khi `put(new CollisionKey(i), i)` phải tra `get(new CollisionKey(i)) == i` cho mọi `i`. Đó là điều chương trình mẫu kiểm tra. So sánh với một map khác cùng kiểu `HashMap` có thể vẫn che khuất lỗi test; kiểm tra trực tiếp giá trị dự kiến theo key rõ ràng hơn.

**Không đoán nội bộ từ thời gian chạy đơn lẻ:** Một test 20 key cực nhanh không chứng minh đang dùng tree bin. Một test 1000 key chậm cũng không chứng minh treeification thất bại. JVM warmup, JIT, phân phối key, loại phép toán và thời điểm GC đều có thể ảnh hưởng thời gian. Nếu muốn benchmark, dùng công cụ benchmark Java thích hợp như JMH với warmup, nhiều lần đo và workload thực tế; chỉ dùng số liệu đo làm căn cứ tối ưu.

### Kiểm tra với `equals`/`hashCode` bị viết sai

Một ví dụ sai điển hình là ghi đè `equals` nhưng giữ `hashCode` mặc định dựa trên tham chiếu object. Khi hai object `equals` bằng nhau mà trả hash khác nhau, chúng có thể rơi vào bucket khác và vi phạm kỳ vọng của Map.

Không nên thiết kế test với mục tiêu “HashMap phải tự cứu mọi key vi phạm hợp đồng”. HashMap có quyền dựa vào `hashCode` và `equals` đúng luật. Hãy kiểm thử **chính lớp key**: nếu `a.equals(b)` thì assert `a.hashCode()==b.hashCode()`; nếu object được dùng làm key lâu dài thì phần đồng nhất phải ổn định trong suốt vòng đời lưu trong map.

## 12. Hướng dẫn áp dụng vào ứng dụng hiện nay

### 12.1. Thiết kế khóa trước khi chỉnh capacity

Một `hashCode` tốt nên:

- Dựa vào các trường được `equals` dùng để nhận dạng đối tượng.
- Phân phối đủ đều với dữ liệu có thật, không luôn trả một hằng số.
- Giữ ổn định khi object đang được dùng làm key.
- Tính toán đủ nhanh so với chi phí dùng map.

Java `Objects.hash(...)` hoặc `record` có thể giúp triển khai ngắn gọn trong nhiều trường hợp, nhưng không có lời hứa hash hoàn hảo. Với key ghép lớn, cân nhắc chi phí cấp phát và hash, rồi đo trên dữ liệu thực. Không phụ thuộc việc các lần chạy JVM luôn có cùng thứ tự duyệt map.

### 12.2. Có rất nhiều key và biết trước số lượng

Nếu dự kiến `n` mapping, constructor với initial capacity đủ lớn giúp tránh một số lần resize, nhưng không được quá cao làm lãng phí bộ nhớ. Load factor mặc định thường phù hợp. Các factory dành cho expected size trong JDK mới hơn giúp diễn đạt ý định rõ hơn, nhưng phải kiểm tra mức Java tối thiểu của dự án.

### 12.3. Key đến từ nguồn bên ngoài hoặc không kiểm soát được

Nếu input do người dùng cung cấp có thể tạo nhiều collision cố ý, đừng xem treeification là phòng vệ an toàn tuyệt đối trước mọi trường hợp tấn công làm cạn tài nguyên. Cần kết hợp giới hạn kích thước, validation, rate limiting và biện pháp an toàn phù hợp ứng dụng; luôn chú ý thời gian xử lý `hashCode`/`equals` của key.

### 12.4. Chọn cấu trúc phù hợp với các yêu cầu khác

| Yêu cầu | Cấu trúc thường phù hợp | Chú ý |
| --- | --- | --- |
| Tra cứu key → value, không cần thứ tự, một luồng hoặc có đồng bộ bên ngoài | `HashMap` | Hash/equals phải ổn định |
| Cần giữ thứ tự chèn | `LinkedHashMap` | Không thay bằng HashMap rồi mong thứ tự |
| Cần key theo thứ tự sắp xếp | `TreeMap` | Comparator/Comparable quyết định key equality trong tree map |
| Cập nhật từ nhiều thread | `ConcurrentHashMap` | Không chấp nhận null key/value, hợp đồng khác |
| Chỉ cần map nhỏ không sửa | `Map.of(...)` / `Map.copyOf(...)` | Không cho null; không cam kết insertion order |

Đây là lựa chọn kiến trúc, **không** có nghĩa các lớp này giống nhau về cách xử lý collision. Cụ thể `TreeMap` là cây sắp xếp theo key trong toàn bộ map, còn **tree bin của HashMap chỉ là cấu trúc nội bộ của một bucket**.

## 13. Tự luyện tập và đáp án

**Câu 1.** Hai key trả `hashCode()==7` nhưng `equals` trả `false`. Gọi `put` cho cả hai có được hai mapping không?

**Đáp án:** Có. Trùng hash **không** đồng nghĩa cùng key.

**Câu 2.** Hai key là hai object khác nhau theo `==` nhưng `equals` bằng nhau và `hashCode` bằng nhau. Gọi `put` cho key thứ hai có tăng `size` không?

**Đáp án:** Không. Giá trị của mapping hiện tại được cập nhật.

**Câu 3.** Trong biểu thức bucket của OpenJDK 25u, hash `1` và `17` nằm đâu với capacity `16` và `32`?

**Đáp án:** Capacity 16: cả hai index 1. Capacity 32: index 1 và 17.

**Câu 4.** `TREEIFY_THRESHOLD=8` có nghĩa `HashMap.size()==8` chắc chắn có cây không?

**Đáp án:** Không. Ngưỡng xét bucket, không phải tổng size; còn phụ thuộc capacity, đường thêm và chi tiết triển khai.

**Câu 5.** Tăng capacity có giúp tách các khóa mà **tất cả `hashCode` đều là 7** không?

**Đáp án:** Không, vì tất cả vẫn có hash giống nhau. Tăng capacity có thể tách các hash **khác nhau** trước đó chỉ tình cờ cùng bucket.

**Câu 6.** Nếu map có `put("A", null)`, gọi `get("A")` và `get("B")` đều trả null, làm sao biết chỉ `"A"` tồn tại?

**Đáp án:** Dùng `containsKey("A")` và `containsKey("B")`.

**Câu 7.** Khi key có thể đổi trường ảnh hưởng `equals`/`hashCode` sau khi đã insert, có thể coi việc lookup là hợp đồng được bảo đảm không?

**Đáp án:** Không. Khóa cần có thông tin nhận dạng ổn định.

**Câu 8.** Khi một bucket trở thành cây đỏ–đen, liệu thứ tự duyệt cả HashMap có trở thành thứ tự sắp xếp không?

**Đáp án:** Không. Tree bin là chi tiết của một bucket; HashMap vẫn không bảo đảm thứ tự duyệt.

**Câu 9.** Có thể dùng HashMap để nhiều thread cùng `put` mà không đồng bộ vì đã có tree bins không?

**Đáp án:** Không. Tree bin không tạo ra an toàn luồng.

**Câu 10.** Với khóa non-Comparable có cùng hash, có được hứa `get` luôn O(log n) trong mọi hoàn cảnh không?

**Đáp án:** Không. Cơ chế cây có thể giảm chi phí nhiều trường hợp, nhưng tìm đúng key có thể cần kiểm tra nhiều nhánh, và hợp đồng công khai không bảo đảm độ phức tạp worst-case cố định cho từng truy vấn.

## 14. Checklist trước khi đưa vào production

- [ ] Khóa tuân thủ đầy đủ hợp đồng `equals`/`hashCode`.
- [ ] Trường nhận dạng của key không thay đổi khi key ở trong map.
- [ ] Đã xác định `null` key/value có được phép hay không; không dùng `get()==null` để suy luận không có mapping.
- [ ] Không phụ thuộc insertion order của `HashMap`.
- [ ] Chỉ cấu hình capacity/load factor khi hiểu số mapping dự kiến và chi phí bộ nhớ.
- [ ] Không dựa vào `TREEIFY_THRESHOLD`/`MIN_TREEIFY_CAPACITY` như API công khai cố định.
- [ ] Hiểu collision hash khác collision bucket, và resize không sửa hàm hash luôn hằng số.
- [ ] Test thêm/đọc/sửa/xóa nhiều key va chạm, gồm tra cứu bằng instance khóa mới nhưng `equals` bằng nhau.
- [ ] Nếu nhiều thread truy cập và sửa, chọn đồng bộ/`ConcurrentHashMap` phù hợp.
- [ ] Tránh reflection phụ thuộc `HashMap.table`, `TreeNode` trong logic sản phẩm.
- [ ] Khi cần chứng minh hiệu năng, đo với benchmark và dữ liệu thực; không suy đoán O(log n) tuyệt đối chỉ từ việc có tree bin.

## Tài liệu tham khảo chính thức và mã nguồn hiện hành

1. [Oracle Java SE 25 — HashMap<K,V>: hành vi công khai, capacity, load factor, đồng thời và thứ tự](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashMap.html)
2. [Oracle Java SE 25 — Map<K,V>: hợp đồng key và tác động khi sửa khóa](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html)
3. [OpenJDK JDK 25u — java.util.HashMap.java: hash(), putVal(), treeifyBin(), resize() và hằng số treeification](https://github.com/openjdk/jdk25u/blob/master/src/java.base/share/classes/java/util/HashMap.java)
4. [Oracle Java SE 25 — Object.hashCode() / equals()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html)
5. [Oracle Java SE 25 — ConcurrentHashMap (để phân biệt yêu cầu đồng thời)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

**Ghi nhớ:** Hợp đồng đúng của HashMap nằm ở khả năng lưu, tìm và cập nhật mapping theo khóa tương đương. List bin, tree bin, các mốc kích thước và cách resize là cơ chế cải thiện hiệu năng của triển khai được tham chiếu, không phải những chi tiết nên mã hóa cứng vào ứng dụng.
