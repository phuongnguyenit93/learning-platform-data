# removeEldestEntry và mô hình bộ nhớ đệm LRU đơn giản

## 1. Bắt đầu từ một cache có chỗ chứa hữu hạn

Một bộ nhớ đệm (cache) giữ tạm kết quả đã tính hoặc đã tải để lần yêu cầu sau có thể dùng lại. Ví dụ, chương trình đã tải mô tả của mã sản phẩm `A`; nếu người dùng hỏi `A` lần nữa, chương trình có thể trả bản đang giữ thay vì tải lại ngay. Việc tra cứu tìm thấy kết quả gọi là **cache hit**; không tìm thấy gọi là **cache miss**. Cache chỉ hữu ích khi chương trình chấp nhận dùng lại dữ liệu theo chính sách đã chọn.

Nếu cứ thêm kết quả vào một `Map` mà không loại bỏ, số entry có thể tăng theo số khóa đã gặp. Một cache đơn giản cần trả lời hai câu hỏi khác nhau:

1. Được giữ tối đa bao nhiêu entry?
2. Khi đã đủ chỗ mà có khóa mới, entry nào phải rời cache?

**LRU — Least Recently Used** chọn entry ít được sử dụng gần đây nhất. LRU không hỏi entry nào được tạo sớm nhất, giá trị nào nhỏ nhất hay khóa nào được dùng nhiều nhất trong toàn bộ lịch sử. Nó chỉ dựa vào thứ tự các lần truy cập mà cấu trúc đang theo dõi. Entry được truy cập thành công gần đây được đưa về phía mới nhất; entry nằm lâu nhất ở phía cũ nhất là ứng viên bị loại.

Trong bài này, thứ tự được viết từ trái sang phải:

```text
[ít được dùng gần đây nhất, ..., vừa được dùng gần đây nhất]
[LRU, ..., MRU]
```

`MRU` là Most Recently Used. Với giới hạn ba entry, chuỗi thao tác sau diễn tả điều cần xây:

| Thao tác | Thứ tự LRU → MRU sau thao tác | Giải thích |
|---|---|---|
| Thêm A | `[A]` | A là entry duy nhất |
| Thêm B | `[A, B]` | B mới được đưa vào |
| Thêm C | `[A, B, C]` | Đã đủ ba entry |
| Đọc A thành công | `[B, C, A]` | A vừa được dùng, B trở thành cũ nhất |
| Thêm D | `[C, A, D]` | D vào cache, B bị loại vì vượt giới hạn |

Việc B rời cache gọi là **loại bỏ entry (eviction)**. Loại một entry khỏi cache không có nghĩa là xóa sản phẩm trong cơ sở dữ liệu hay xóa dữ liệu gốc. Cache nên giữ dữ liệu có thể tải hoặc tạo lại. Nếu bỏ entry đồng nghĩa mất bản dữ liệu duy nhất, cần một thiết kế lưu trữ khác trước khi áp dụng chính sách loại bỏ.

Mục tiêu ở đây là hiểu và tự viết một cache LRU nhỏ, dùng một luồng, giới hạn theo số entry, dựa trên `LinkedHashMap`. Hai thành phần chính là **thứ tự truy cập** và **quy tắc loại bỏ sau khi thêm entry**. Hiểu từng thành phần riêng giúp tránh tạo ra một map có giới hạn nhưng lại loại sai entry.

## 2. LinkedHashMap cung cấp phần nào của cơ chế LRU?

### 2.1. Tra cứu theo khóa và giữ một thứ tự duyệt

`LinkedHashMap` kết hợp cơ chế tra cứu theo khóa của bảng băm với danh sách liên kết giữ thứ tự các entry. Khi dùng chế độ thứ tự truy cập, thứ tự duyệt của `keySet()`, `values()` và `entrySet()` phản ánh thứ tự từ ít được truy cập gần đây nhất đến mới được truy cập gần đây nhất.

Vì cấu trúc đã giữ thứ tự này, cache không cần tự tìm entry có thời gian truy cập nhỏ nhất bằng cách quét toàn bộ map sau mỗi lần thêm. Chương trình cũng không cần ghi một timestamp cho từng `get`. Thứ tự truy cập ở đây là thứ tự thao tác trên map, không phải lịch sử thời gian thực có ngày giờ.

Đoạn mã sau chỉ minh họa cấu hình, chưa phải một chương trình chạy độc lập:

```java
LinkedHashMap<String, String> entries =
        new LinkedHashMap<>(16, 0.75f, true);
```

Ba đối số có nhiệm vụ khác nhau:

| Đối số | Ý nghĩa trong ví dụ | Có phải giới hạn số entry của cache không? |
|---|---|---|
| `16` | Dung lượng ban đầu yêu cầu cho bảng băm | Không |
| `0.75f` | Hệ số tải của bảng băm | Không |
| `true` | Bật thứ tự truy cập (`accessOrder`) | Không; chỉ chọn cách duy trì thứ tự |

`new LinkedHashMap<>(3)` không tạo ra cache chỉ giữ ba entry. Dung lượng ban đầu có thể liên quan đến việc cấp phát và mở rộng bảng băm; nó không cấm map chứa nhiều hơn số đó. Giới hạn cache phải được thể hiện bằng một chính sách riêng.

### 2.2. Thứ tự chèn và thứ tự truy cập trả lời hai câu hỏi khác nhau

Constructor mặc định của `LinkedHashMap` dùng **thứ tự chèn**. Trong chế độ đó, đọc A sau khi đã chèn A, B, C không chuyển A xuống cuối. Nếu luôn loại entry đứng đầu, chính sách gần với FIFO — First In, First Out: entry vào trước rời trước.

Constructor ba đối số với `accessOrder=true` dùng **thứ tự truy cập**. Khi `get(A)` tìm thấy A, entry A trở thành mới được dùng gần đây nhất. Sau đó loại entry đứng đầu mới phù hợp với LRU.

Vì vậy, một cache LRU có giới hạn cần cả hai phần:

```text
accessOrder=true
    → giữ đúng thứ tự sử dụng

removeEldestEntry trả về size() > maximumEntries
    → loại entry đầu khi vừa thêm vượt giới hạn
```

Chỉ bật `accessOrder=true` thì map vẫn có thể tăng không giới hạn. Chỉ ghi đè `removeEldestEntry` nhưng giữ thứ tự chèn thì có giới hạn số entry, song chưa phải LRU.

### 2.3. Truy cập nào làm thay đổi độ mới?

Đối với các thao tác dùng trong bài, cần nhớ:

| Thao tác trên map theo thứ tự truy cập | Thay đổi số entry? | Ảnh hưởng thứ tự |
|---|---|---|
| `get(key)` tìm thấy khóa | Không | Entry trở thành mới nhất |
| `get(key)` không tìm thấy | Không | Không có entry để chuyển |
| `put(key, value)` với khóa mới | Có trước khi xét loại bỏ | Entry mới đứng cuối; có thể loại entry đầu |
| `put(key, value)` với khóa đã tồn tại | Không | Cập nhật giá trị và đưa entry đó về phía mới nhất |
| `containsKey(key)` | Không | Không tính là truy cập để đổi thứ tự |
| Duyệt `entrySet()` hoặc sao chép `keySet()` | Không | Bản thân việc duyệt không làm mới entry |

Không nên suy ra rằng mọi phương thức có vẻ như “đọc” đều giữ nguyên cấu trúc. `get` có thể đổi liên kết thứ tự dù không đổi `size()`. Ngược lại, `containsKey` xác nhận sự tồn tại nhưng không thay thế ý nghĩa sử dụng của `get` trong chính sách LRU.

Tài liệu còn quy định các thao tác tạo truy cập như `getOrDefault`, `putIfAbsent`, các phương thức `compute` và `merge` khi entry tương ứng tồn tại sau thao tác. Các phương thức `replace` chỉ tạo truy cập khi giá trị thực sự được thay thế. Với `putAll`, từng mapping tạo một truy cập theo thứ tự duyệt của `entrySet()` ở map đầu vào. Khi mở rộng API cache, cần kiểm tra đúng hợp đồng của phương thức dùng thêm; không mặc định rằng chỉ `get` mới tác động đến LRU.

## 3. removeEldestEntry là điểm quyết định loại bỏ

### 3.1. Chữ ký và ý nghĩa kết quả boolean

`LinkedHashMap` khai báo phương thức `protected boolean removeEldestEntry(Map.Entry<K,V> eldest)`. Đây là một phương thức được lớp cung cấp để lớp con ghi đè. Tên phương thức không có nghĩa rằng chính đoạn ghi đè luôn phải tự gọi `remove`.

Đoạn cốt lõi sau minh họa phần ghi đè bên trong một lớp con; nó không phải tệp Java độc lập:

```java
@Override
protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
    return size() > maximumEntries;
}
```

Đọc đoạn mã theo ba bước:

1. `LinkedHashMap` vừa thêm một entry mới và hỏi chính sách xem có nên bỏ entry cũ nhất không.
2. `eldest` là entry đang đứng đầu thứ tự của map: cũ nhất theo thứ tự chèn hoặc ít được truy cập gần đây nhất theo thứ tự truy cập.
3. Kết quả `true` yêu cầu map loại entry đó; kết quả `false` giữ nó.

Giá trị trả về là quyết định `boolean`, không phải entry bị loại. Cài đặt mặc định trả về `false`, nên một `LinkedHashMap` thông thường không tự trở thành cache có giới hạn.

### 3.2. Thời điểm gọi: sau khi thêm entry mới

Điểm quan trọng nhất là phương thức được gọi sau khi `put` hoặc `putAll` chèn một entry mới vào map. Khi đang kiểm tra điều kiện, `size()` đã tính cả entry vừa được chèn.

Với giới hạn ba:

```text
Trước put(D):              [B, C, A]       size=3
Sau khi D được chèn:       [B, C, A, D]    size=4
removeEldestEntry(B):      4 > 3 → true
Sau khi loại B:           [C, A, D]       size=3
```

Điều kiện đúng là `size() > maximumEntries`. Nếu viết `size() >= maximumEntries`, entry thứ ba đã kích hoạt loại bỏ ngay khi map vừa đạt giới hạn ba; cache chỉ giữ được tối đa hai entry sau các lần thêm thông thường.

`get` không gọi cơ chế loại bỏ này chỉ vì một lần đọc vừa diễn ra. Cập nhật một khóa đã có bằng `put` có thể thay đổi thứ tự truy cập nhưng không thêm entry mới để kích hoạt điểm kiểm tra này. Cần phân biệt **làm mới thứ tự** với **kích hoạt kiểm tra sau khi thêm**.

Với `putAll`, đừng hình dung rằng Java nhận toàn bộ dữ liệu rồi chỉ gọi chính sách một lần sau cùng. Các entry mới được chèn lần lượt; chính sách được xét sau các lần chèn đó. Kết quả giữ lại phụ thuộc cả vào thứ tự truy cập được tạo ra trong quá trình nạp.

### 3.3. Một lần quyết định chỉ yêu cầu loại entry đầu

Một lần `true` yêu cầu loại một entry `eldest`. Đây không phải câu lệnh “lặp cho đến khi mọi giới hạn tùy ý đều được thỏa mãn”. Trong thiết kế đơn giản, giới hạn được cố định từ constructor, map bắt đầu rỗng và mỗi `put` khóa mới chỉ làm số entry tăng một. Vì thế kiểm tra rồi bỏ một entry là đủ để quay về giới hạn.

Nếu đổi một giới hạn đang là 100 xuống 2 trong lúc cache đã chứa 100 entry, không thể chỉ sửa biến rồi mong một lần hook dọn tất cả. Cần một thao tác thu gọn có chủ đích. Các lớp trong bài giữ giới hạn cố định để không đưa thêm trách nhiệm đó vào API.

### 3.4. Không tự xóa rồi đồng thời trả về true

Cách rõ ràng trong bài là để phần ghi đè chỉ tính quyết định. Không gọi `remove(eldest.getKey())` ở đây rồi lại trả về `true`. Tài liệu cho phép phần ghi đè trực tiếp sửa map, nhưng khi làm như vậy phải trả về `false`; nếu vừa sửa map vừa trả về `true`, ảnh hưởng của lần gọi không được quy định. Một cache theo số entry không cần dùng cách phức tạp đó.

Không nên dùng phương thức này để tải dữ liệu, phát sinh nghiệp vụ hoặc thực hiện tác vụ chậm. Nó đang chạy trong đường xử lý thêm entry của map. Giữ quyết định ngắn, dễ kiểm tra sẽ giúp hiểu được khi nào dữ liệu bị loại.

## 4. Chương trình 1: quan sát chính xác thời điểm hook chạy

Lưu chương trình đầy đủ dưới đây vào tệp `LinkedHashMapLruHookDemo.java`. Ví dụ dùng Java 17 trở lên. Biến đếm và các dòng `hook:` chỉ giúp quan sát cơ chế trong bài.

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class LinkedHashMapLruHookDemo {
    static final class LruMap<K, V> extends LinkedHashMap<K, V> {
        private final int maximumEntries;
        private int hookCalls;

        LruMap(int maximumEntries) {
            super(16, 0.75f, true);
            if (maximumEntries < 0) {
                throw new IllegalArgumentException("negative limit");
            }
            this.maximumEntries = maximumEntries;
        }

        @Override
        protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
            hookCalls++;
            boolean evict = size() > maximumEntries;
            System.out.println("hook: size=" + size()
                    + ", eldest=" + eldest.getKey()
                    + ", evict=" + evict);
            return evict;
        }
    }

    public static void main(String[] args) {
        LruMap<String, Integer> cache = new LruMap<>(3);
        cache.put("A", 1);
        cache.put("B", 2);
        cache.put("C", 3);
        System.out.println("initialLruToMru=" + cache.keySet());

        System.out.println("getA=" + cache.get("A"));
        System.out.println("afterGetA=" + cache.keySet());

        cache.put("D", 4);
        System.out.println("afterPutD=" + cache.keySet());
        System.out.println("hasB=" + cache.containsKey("B"));
        System.out.println("size=" + cache.size());

        int beforeUpdate = cache.hookCalls;
        cache.put("C", 30);
        System.out.println("afterExistingPut=" + cache);
        System.out.println("hookCountUnchanged="
                + (beforeUpdate == cache.hookCalls));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapLruHookDemo.java
java LinkedHashMapLruHookDemo
```

Stdout:

```text
hook: size=1, eldest=A, evict=false
hook: size=2, eldest=A, evict=false
hook: size=3, eldest=A, evict=false
initialLruToMru=[A, B, C]
getA=1
afterGetA=[B, C, A]
hook: size=4, eldest=B, evict=true
afterPutD=[C, A, D]
hasB=false
size=3
afterExistingPut={A=1, D=4, C=30}
hookCountUnchanged=true
```

### 4.1. Đọc kết quả theo từng giai đoạn

Ba lần `put` đầu đều thêm khóa mới nên xuất hiện ba dòng `hook:`. Ở lần đầu, entry A vừa được thêm cũng chính là `eldest`, vì map chỉ có một entry. `size=1`, `2`, `3` đều không vượt ba nên không entry nào bị loại.

`get("A")` trả về `1` và chuyển A về cuối: `[A, B, C]` thành `[B, C, A]`. Không xuất hiện dòng `hook:` giữa `getA` và `afterGetA`. Đó là bằng chứng rằng cập nhật thứ tự bởi một lần đọc không đồng nghĩa với gọi `removeEldestEntry`.

Khi thêm D, dòng `hook: size=4, eldest=B, evict=true` cho thấy đủ ba điều: kích thước đã tính D, B đang đứng đầu thứ tự truy cập, và điều kiện vượt giới hạn đã đúng. Sau khi `put` kết thúc, map còn `[C, A, D]`, B không tồn tại, `size()` trở về ba.

Cuối cùng, `put("C", 30)` thay giá trị của khóa C đã có. Số entry không tăng. C trở thành mới nhất nên map được in là `{A=1, D=4, C=30}`; `hookCountUnchanged=true` xác nhận không có lần gọi hook mới trong thao tác cập nhật đó.

### 4.2. Vai trò của từng chi tiết triển khai

`super(16, 0.75f, true)` bật thứ tự truy cập ngay khi tạo map. `maximumEntries` là trường `final`, tách riêng giới hạn nghiệp vụ khỏi dung lượng bảng băm. Kiểm tra số âm giúp lỗi cấu hình được báo tại nơi tạo đối tượng. `@Override` giúp trình biên dịch phát hiện nếu gõ sai tên hoặc chữ ký của phương thức.

`eldest.getKey()` được dùng để in entry sắp được xét. Quyết định theo số entry không cần đọc khóa hay giá trị, vì câu hỏi chỉ là `size()` có vượt giới hạn hay không. Không nên thêm điều kiện theo tên khóa khi đang muốn học một chính sách LRU thuần túy.

Các thao tác in `keySet()` và in toàn bộ map phản ánh thứ tự đang có. Chúng không âm thầm gọi `get` cho từng khóa để làm mới lại toàn bộ thứ tự. Chính vì vậy ví dụ có thể dùng các dòng in đó để quan sát LRU.

## 5. Chương trình 2: cùng giới hạn, FIFO và LRU loại khác nhau

Một lỗi dễ mắc là ghi đè đúng `removeEldestEntry` nhưng quên đối số `true`. Chương trình sau tạo hai map với cùng giới hạn ba; chỉ khác chế độ duy trì thứ tự. Lưu vào `LinkedHashMapLruFifoDemo.java`.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class LinkedHashMapLruFifoDemo {
    static final class BoundedMap<K, V> extends LinkedHashMap<K, V> {
        private final int maximumEntries;

        BoundedMap(int maximumEntries, boolean accessOrder) {
            super(16, 0.75f, accessOrder);
            if (maximumEntries < 0) {
                throw new IllegalArgumentException("negative limit");
            }
            this.maximumEntries = maximumEntries;
        }

        @Override
        protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
            return size() > maximumEntries;
        }
    }

    public static void main(String[] args) {
        BoundedMap<String, String> fifo = new BoundedMap<>(3, false);
        BoundedMap<String, String> lru = new BoundedMap<>(3, true);

        for (String key : List.of("A", "B", "C")) {
            fifo.put(key, key);
            lru.put(key, key);
        }

        fifo.get("A");
        lru.get("A");
        System.out.println("fifoBeforeD=" + fifo.keySet());
        System.out.println("lruBeforeD=" + lru.keySet());

        fifo.put("D", "D");
        lru.put("D", "D");
        System.out.println("fifoAfterD=" + fifo.keySet());
        System.out.println("lruAfterD=" + lru.keySet());
        System.out.println("fifoHasA=" + fifo.containsKey("A"));
        System.out.println("lruHasA=" + lru.containsKey("A"));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LinkedHashMapLruFifoDemo.java
java LinkedHashMapLruFifoDemo
```

Stdout:

```text
fifoBeforeD=[A, B, C]
lruBeforeD=[B, C, A]
fifoAfterD=[B, C, D]
lruAfterD=[C, A, D]
fifoHasA=false
lruHasA=true
```

Sau khi thêm A, B, C rồi đọc A, map `fifo` vẫn là `[A, B, C]`; map `lru` đã thành `[B, C, A]`. Khi D được thêm, cả hai đều thấy kích thước bốn và đều trả về `true`, nhưng `eldest` khác nhau:

| Map | Entry đứng đầu trước khi thêm D | Entry bị loại | Thứ tự còn lại |
|---|---|---|---|
| Thứ tự chèn (`false`) | A | A | `[B, C, D]` |
| Thứ tự truy cập (`true`) | B | B | `[C, A, D]` |

`fifoHasA=false` trong khi `lruHasA=true` là khác biệt thực tế của chính sách. A vừa được dùng nhưng vẫn rời cache FIFO vì tuổi chèn của nó không đổi. Trong cache LRU, lần dùng A đã bảo vệ A khỏi lần loại bỏ kế tiếp; B là entry không được dùng lâu nhất.

Cả hai cấu trúc đều có giới hạn số entry. Do đó, chỉ kiểm tra `size() <= maximumEntries` chưa đủ để xác nhận một cache thực hiện đúng LRU. Cần kiểm tra cả **entry nào bị loại** và **thứ tự sau các lần truy cập**.
## 6. Chương trình 3: bọc map thành một cache nhỏ có hợp đồng rõ ràng

### 6.1. Vì sao không chỉ trả thẳng LinkedHashMap ra ngoài?

Kế thừa `LinkedHashMap` như hai ví dụ trước giúp nhìn rõ cơ chế. Tuy nhiên, nếu đưa toàn bộ đối tượng map cho nơi sử dụng, người gọi nhận cả API `Map`, các view liên kết với map và nhiều đường thay đổi dữ liệu. Lúc đó hợp đồng “cache này hỗ trợ những thao tác nào” khó kiểm soát hơn.

Cách thứ hai là **chứa một map ở bên trong**. Lớp cache chỉ công bố các thao tác cần dùng: `get`, `put`, `containsKey`, `size` và một bản sao thứ tự khóa để quan sát. Map nội bộ là `private`; người gọi không nhận trực tiếp `keySet()` hay `entrySet()` đang liên kết với nó.

Cache trong ví dụ chọn các quy tắc cụ thể:

- Giới hạn không âm, được cố định khi tạo cache.
- Giới hạn bằng 0 hợp lệ: dữ liệu có thể được đưa vào rồi bị loại ngay, nên không giữ lại entry.
- Không nhận khóa hoặc giá trị `null`.
- `get` trả về `null` chỉ khi không có entry tương ứng.
- `containsKey` kiểm tra sự tồn tại nhưng không làm mới vị trí LRU.
- `keysLruToMru()` trả về một danh sách sao chép, từ cũ nhất đến mới nhất.

Đây là chính sách của lớp bọc, không phải giới hạn vốn có của `LinkedHashMap`. Bản thân `LinkedHashMap` cho phép khóa `null` và giá trị `null`. Việc cấm chúng ở đây giúp phân biệt cache miss bằng kết quả `get == null` mà không cần thêm trạng thái chứa giá trị rỗng.

Lưu chương trình đầy đủ vào `SimpleLruCacheDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class SimpleLruCacheDemo {
    static final class SimpleLruCache<K, V> {
        private final LinkedHashMap<K, V> entries;

        SimpleLruCache(int maximumEntries) {
            if (maximumEntries < 0) {
                throw new IllegalArgumentException("negative limit");
            }
            entries = new LinkedHashMap<K, V>(16, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
                    return size() > maximumEntries;
                }
            };
        }

        V get(K key) {
            Objects.requireNonNull(key, "key");
            return entries.get(key);
        }

        void put(K key, V value) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");
            entries.put(key, value);
        }

        boolean containsKey(K key) {
            Objects.requireNonNull(key, "key");
            return entries.containsKey(key);
        }

        int size() {
            return entries.size();
        }

        List<K> keysLruToMru() {
            return new ArrayList<>(entries.keySet());
        }
    }

    private static void expectNullPointer(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println(label + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        SimpleLruCache<String, String> cache = new SimpleLruCache<>(2);
        cache.put("A", "a");
        cache.put("B", "b");
        System.out.println("getA=" + cache.get("A"));
        System.out.println("afterHit=" + cache.keysLruToMru());
        System.out.println("getMissing=" + cache.get("missing"));
        System.out.println("afterMiss=" + cache.keysLruToMru());
        System.out.println("hasB=" + cache.containsKey("B"));
        System.out.println("afterContains=" + cache.keysLruToMru());

        cache.put("C", "c");
        System.out.println("afterPutC=" + cache.keysLruToMru());
        System.out.println("getEvictedB=" + cache.get("B"));
        cache.put("A", "a2");
        System.out.println("afterUpdateA=" + cache.keysLruToMru());
        System.out.println("size=" + cache.size());

        List<String> snapshot = cache.keysLruToMru();
        snapshot.clear();
        System.out.println("afterSnapshotClear=" + cache.keysLruToMru());

        SimpleLruCache<String, String> disabled = new SimpleLruCache<>(0);
        disabled.put("A", "a");
        System.out.println("zeroLimitSize=" + disabled.size());
        System.out.println("zeroLimitGetA=" + disabled.get("A"));

        try {
            new SimpleLruCache<String, String>(-1);
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("negativeLimit=IllegalArgumentException");
        }

        expectNullPointer("nullKey", () -> cache.put(null, "value"));
        expectNullPointer("nullValue", () -> cache.put("X", null));
        System.out.println("afterRejectedNulls=" + cache.keysLruToMru());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SimpleLruCacheDemo.java
java SimpleLruCacheDemo
```

Stdout:

```text
getA=a
afterHit=[B, A]
getMissing=null
afterMiss=[B, A]
hasB=true
afterContains=[B, A]
afterPutC=[A, C]
getEvictedB=null
afterUpdateA=[C, A]
size=2
afterSnapshotClear=[C, A]
zeroLimitSize=0
zeroLimitGetA=null
negativeLimit=IllegalArgumentException
nullKey=NullPointerException
nullValue=NullPointerException
afterRejectedNulls=[C, A]
```

### 6.2. Hit, miss và kiểm tra sự tồn tại

Sau khi thêm A và B, thứ tự là `[A, B]`. `get("A")` tìm thấy `a`, vì thế thứ tự thành `[B, A]`. `get("missing")` trả về `null` và không tạo entry mới; thứ tự vẫn `[B, A]`.

`containsKey("B")` trả về `true` nhưng `afterContains` vẫn là `[B, A]`. Nếu việc kiểm tra tồn tại được coi như một lần dùng dữ liệu trong ứng dụng, cần chọn thao tác phù hợp với ý nghĩa đó. Không thể gọi `containsKey` rồi suy ra B đã được làm mới trong LRU.

Khi C được thêm vào cache giới hạn hai entry, B rời cache. `get("B")` sau đó trả về `null`, hoàn toàn bình thường dù B từng tồn tại trước đó. Một cache miss không chứng minh dữ liệu gốc đã biến mất; nó chỉ chứng minh cache hiện tại không có entry mà yêu cầu đang cần.

`put("A", "a2")` cập nhật khóa đã có, nên kích thước vẫn hai. Sau thao tác này A là mới nhất và thứ tự là `[C, A]`. Nếu ghi lại cùng một giá trị cho khóa đã có, `put` vẫn là một thao tác truy cập theo hợp đồng của map theo thứ tự truy cập; không nên dùng so sánh giá trị cũ/mới để tự suy ra độ mới không đổi.

### 6.3. Bản sao danh sách khóa bảo vệ điều gì?

`new ArrayList<>(entries.keySet())` duyệt thứ tự hiện tại rồi chứa các tham chiếu khóa trong một danh sách mới. Gọi `snapshot.clear()` chỉ xóa phần tử khỏi danh sách mới; dòng `afterSnapshotClear=[C, A]` cho thấy cache không bị xóa theo.

Điều này khác với trả trực tiếp `entries.keySet()`: view đó liên kết với map, và các thao tác loại bỏ được hỗ trợ trên view sẽ tác động đến map. Không lộ view giúp lớp cache giữ các đường thay đổi trạng thái ở một nơi dễ kiểm tra.

Tuy nhiên, đây chỉ là bản sao của **cấu trúc danh sách**. Nó không sao chép sâu từng đối tượng khóa. Cache cũng đang giữ tham chiếu giá trị, không tự tạo bản sao sâu dữ liệu. Nếu khóa là một đối tượng có thể thay đổi, không được sửa các trường tham gia `equals`/`hashCode` khi khóa đang nằm trong map. Nếu giá trị có thể thay đổi, cần quyết định nơi sử dụng có được phép sửa nó hay không. Chính sách LRU không giải quyết thay các hợp đồng đó.

### 6.4. Giới hạn bằng 0, bằng 1 và số âm

Với giới hạn bằng 0, lần `put("A", "a")` chèn entry đầu tiên, `size()` tạm thời bằng một, rồi hook trả về `1 > 0`. Entry duy nhất đó cũng chính là `eldest` và bị loại. Sau khi `put` trả về, `size()` bằng 0 và `get("A")` là `null`.

Cách xử lý này có thể dùng để cấu hình tắt lưu đệm mà vẫn giữ cùng đường gọi API. Nó là quyết định được nêu rõ trong ví dụ; một API khác có thể chọn từ chối giới hạn 0, nhưng phải mô tả và kiểm tra chính sách của mình nhất quán.

Với giới hạn bằng 1, entry đầu tiên được giữ vì `1 > 1` là `false`. Thêm khóa khác làm kích thước tạm thời bằng hai và entry cũ bị loại. Đây cũng là cách dễ phát hiện lỗi dùng `>=`: với điều kiện sai đó, ngay entry đầu tiên đã bị loại.

Giới hạn âm được từ chối bằng `IllegalArgumentException` ngay tại constructor. Không dùng một số âm làm tín hiệu mơ hồ cho “không giới hạn” trong lớp này, vì như vậy điều kiện loại bỏ sẽ không còn khớp hợp đồng đang học.

### 6.5. Từ chối null trước khi thay đổi map

`put` kiểm tra cả khóa và giá trị bằng `Objects.requireNonNull` trước khi gọi `entries.put`. Vì vậy, khi hai lần thử `put(null, "value")` và `put("X", null)` thất bại, không có entry mới nào được chèn, không entry cũ nào bị loại và thứ tự vẫn `[C, A]`.

Không nên kiểm tra giá trị sau khi đã chèn rồi mới ném lỗi. Trong cache có giới hạn, việc chèn một entry không hợp lệ có thể đã loại một entry hợp lệ khác. Kiểm tra trước thao tác thay đổi giữ cho hành vi báo lỗi dễ hiểu.

Nếu ứng dụng cần lưu kết quả “không tìm thấy” để tránh tải lại liên tục, có thể cần một kiểu kết quả hoặc một giá trị đại diện được thiết kế riêng. Chỉ bỏ kiểm tra `null` trong ví dụ sẽ làm điều kiện `get(key) == null` trở nên nhập nhằng: đó có thể là miss hoặc là hit với giá trị `null`. Bài này giữ chính sách không có giá trị `null` để đường hit/miss rõ ràng.

## 7. Chương trình 4: lấy từ cache, thiếu thì tải

### 7.1. Đường xử lý một yêu cầu

Một lớp cache thường được dùng theo mẫu:

```text
Nhận khóa
    ↓
Tra cache bằng get
    ├─ Có giá trị → trả ngay; entry trở thành mới nhất
    └─ Không có → tải/tính kết quả
                      ↓
                put vào cache
                      ↓
           có thể loại entry LRU nếu đầy
                      ↓
                 trả kết quả
```

Hàm tải dữ liệu, gọi là `loader` trong chương trình, nhận khóa và tạo giá trị. Ở đây hàm chỉ đổi chuỗi thành chữ hoa để kết quả và số lần gọi hoàn toàn xác định. Trong một ứng dụng thật, chi phí tải có thể lớn hơn nhiều; nguyên tắc kiểm tra cache trước vẫn giống nhau.

Lưu chương trình sau vào `ReadThroughLruDemo.java`. Đây là chương trình độc lập với ba ví dụ trước; không cần chép thêm lớp từ tệp khác.

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;

public class ReadThroughLruDemo {
    static final class Cache<K, V> {
        private final LinkedHashMap<K, V> entries;

        Cache(int maximumEntries) {
            if (maximumEntries < 0) {
                throw new IllegalArgumentException("negative limit");
            }
            entries = new LinkedHashMap<K, V>(16, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
                    return size() > maximumEntries;
                }
            };
        }

        V getOrLoad(K key, Function<? super K, ? extends V> loader) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(loader, "loader");
            V cached = entries.get(key);
            if (cached != null) {
                return cached;
            }
            V loaded = Objects.requireNonNull(loader.apply(key), "loaded value");
            entries.put(key, loaded);
            return loaded;
        }

        List<K> keysLruToMru() {
            return new ArrayList<>(entries.keySet());
        }
    }

    private static int loadCount;

    private static String load(String key) {
        loadCount++;
        System.out.println("load=" + key);
        return key.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        Cache<String, String> cache = new Cache<>(2);
        for (String key : List.of("a", "b", "a", "c", "b")) {
            String value = cache.getOrLoad(key, ReadThroughLruDemo::load);
            System.out.println("result=" + key + ":" + value
                    + ", order=" + cache.keysLruToMru());
        }
        System.out.println("loadCount=" + loadCount);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ReadThroughLruDemo.java
java ReadThroughLruDemo
```

Stdout:

```text
load=a
result=a:A, order=[a]
load=b
result=b:B, order=[a, b]
result=a:A, order=[b, a]
load=c
result=c:C, order=[a, c]
load=b
result=b:B, order=[c, b]
loadCount=4
```

### 7.2. Năm yêu cầu nhưng chỉ bốn lần tải

Cache giữ tối đa hai entry. Từng yêu cầu được xử lý như sau:

| Yêu cầu | Hit hay miss? | Có gọi hàm tải không? | Thứ tự sau yêu cầu | Entry bị loại |
|---|---|---|---|---|
| `a` | Miss | Có, lần 1 | `[a]` | Không |
| `b` | Miss | Có, lần 2 | `[a, b]` | Không |
| `a` | Hit | Không | `[b, a]` | Không |
| `c` | Miss | Có, lần 3 | `[a, c]` | `b` |
| `b` | Miss | Có, lần 4 | `[c, b]` | `a` |

Yêu cầu thứ ba là bằng chứng cache đang dùng lại kết quả: trước dòng `result=a:A, order=[b, a]` không có dòng `load=a` mới. Yêu cầu này đồng thời làm a thành mới nhất, nên khi c được thêm, b phải rời cache.

Yêu cầu b cuối cùng lại phải tải vì b đã bị loại. LRU giúp ưu tiên dữ liệu được dùng gần đây; nó không bảo đảm một khóa chỉ được tải một lần trong suốt đời chương trình. Số lần tải phụ thuộc chuỗi yêu cầu và giới hạn cache.

`Locale.ROOT` giúp thao tác đổi chữ hoa không phụ thuộc locale mặc định của máy. Phần này chỉ giữ ví dụ có kết quả ổn định; nó không tham gia cơ chế LRU.

### 7.3. Vì sao kiểm tra cached != null là đủ ở đây?

Map nội bộ chỉ được thêm dữ liệu qua `getOrLoad`, và kết quả của `loader.apply(key)` được kiểm tra khác `null` trước `put`. Vì vậy không có entry với giá trị `null`; `entries.get(key)` trả `null` có thể được hiểu là miss.

Khóa và chính đối tượng `loader` cũng được kiểm tra trước. Với hợp đồng này, truyền `loader=null` là lỗi kể cả khi khóa đã có trong cache. Đó là lựa chọn kiểm tra đầu vào của API đang viết, không phải hành vi bắt buộc của mọi cache.

Nếu loader ném ngoại lệ, luồng chạy không đến `entries.put`; kết quả lỗi không tự trở thành một entry. Nếu loader trả về `null`, `requireNonNull` ném `NullPointerException`, và cache cũng không chèn một giá trị `null`. Loader trong ví dụ chỉ tính giá trị, không trực tiếp sửa chính cache.

Giá trị rỗng như chuỗi `""` vẫn là một đối tượng khác `null` và vẫn có thể được lưu. Đừng trộn lẫn “không có entry”, “có một giá trị rỗng theo nghiệp vụ” và “hàm tải bị lỗi” thành cùng một nhánh mà không xác định hợp đồng.

Với giới hạn bằng 0, `getOrLoad` vẫn có thể tải và trả giá trị cho yêu cầu hiện tại. Entry vừa đưa vào sẽ bị loại ngay, nên yêu cầu sau lại miss. “Không giữ kết quả” không có nghĩa rằng phương thức không được phép trả kết quả vừa tính.

## 8. Đọc đúng các giới hạn của mô hình

### 8.1. Giới hạn số entry không phải giới hạn byte

`size() > maximumEntries` đếm số mapping. Một entry giữ một chuỗi nhỏ và một entry giữ một cấu trúc dữ liệu rất lớn đều đóng góp một đơn vị vào `size()`. Do đó cache tối đa 100 entry không tự bảo đảm chỉ chiếm một số MB cố định.

Map, khóa, giá trị và các liên kết thứ tự đều có chi phí bộ nhớ. Giới hạn entry giúp chặn sự tăng số mapping theo số khóa từng gặp; nó không thay thế việc đánh giá kích thước và vòng đời của dữ liệu. Không gọi đây là một cơ chế đo hoặc quản lý chính xác dung lượng heap.

Việc loại entry chỉ bỏ tham chiếu từ cache đến dữ liệu đó. Nếu nơi khác còn giữ tham chiếu, đối tượng vẫn có thể được sử dụng. Ngay cả khi không còn tham chiếu mạnh nào, thời điểm thu gom rác do JVM quyết định; `removeEldestEntry` không phải lệnh yêu cầu JVM lập tức giải phóng một lượng byte xác định.

### 8.2. LRU không phải thời hạn sử dụng

LRU dựa vào độ gần đây của truy cập, còn thời hạn sử dụng thường được gọi là TTL — Time To Live. Một entry không được dùng trong một giờ vẫn có thể nằm trong cache LRU nếu chưa có lần thêm nào gây vượt giới hạn. Ngược lại, entry vừa mới được tải vẫn có thể bị loại nếu nhiều khóa khác tiếp tục được dùng.

`removeEldestEntry` không được bộ định thời gọi theo chu kỳ. Đồng hồ chạy qua một mốc không tự làm phương thức này chạy. Một lần `get` cũng không tự gọi hook để dọn dữ liệu hết hạn. Vì vậy không thể có TTL đúng nghĩa chỉ bằng cách đổi biểu thức điều kiện rồi giả định cache sẽ dọn liên tục.

Bài này chỉ thực hiện chính sách LRU theo số entry. Khi cần thời hạn, trọng số dung lượng hoặc chính sách làm mới dữ liệu, phải thiết kế riêng cách kiểm tra và loại bỏ tương ứng. Không nên gắn thêm tên các tính năng đó vào lớp chỉ vì nó đã có một phương thức loại entry.

### 8.3. Giữ kết quả không tự bảo đảm dữ liệu mới nhất

Nếu dữ liệu gốc thay đổi trong khi bản cũ vẫn còn trong cache, một hit có thể trả bản cũ. LRU chỉ quyết định ưu tiên giữ entry nào; nó không biết nguồn dữ liệu vừa được cập nhật. Việc xóa theo thay đổi nguồn, ghi lại giá trị mới hoặc lựa chọn khoảng thời gian chấp nhận dữ liệu cũ là một quyết định khác.

Cache này cũng không lưu dữ liệu qua lần khởi động chương trình. Tạo đối tượng cache mới bắt đầu với map rỗng. Không nên dùng ví dụ này thay cho cơ chế lưu trữ bền vững hoặc coi nó là nơi giữ bản duy nhất của dữ liệu cần bảo toàn.

### 8.4. get có thể thay đổi cấu trúc thứ tự

`LinkedHashMap` không tự đồng bộ cho truy cập đồng thời. Đặc biệt ở chế độ thứ tự truy cập, `get` có thể đổi liên kết thứ tự. Không thể chia thao tác thành “đọc thì không cần bảo vệ, chỉ put mới cần” rồi cho rằng map đã an toàn khi nhiều luồng cùng dùng.

Nếu cần nhiều luồng, mọi đường truy cập trạng thái liên quan phải được phối hợp theo một thiết kế nhất quán. Chỉ thêm một wrapper đồng bộ cho từng lệnh `get` và `put` riêng lẻ chưa làm cả chuỗi **kiểm tra thiếu → tải → đưa vào** trở thành nguyên tử. Hai luồng có thể cùng thấy miss và cùng tải một khóa.

Các chương trình ở đây chạy trong một luồng, không cung cấp cơ chế gộp các lần tải đồng thời, hủy tác vụ hay xử lý tác vụ đang chờ. Không suy ra các bảo đảm đó chỉ từ việc cache có thứ tự LRU. Khi chuyển sang yêu cầu đồng thời, cần xem xét lại hợp đồng trước khi chọn cách khóa và cách thực hiện công việc tải dữ liệu.

### 8.5. Duyệt map và gọi get trên chính map là một bẫy

Trong một map theo thứ tự truy cập, duyệt `keySet()` bằng iterator rồi gọi `get(key)` trên chính map có thể thay đổi thứ tự khi iterator đang chạy. Điều đó có thể dẫn đến `ConcurrentModificationException`, dù chương trình chỉ có một luồng.

Cơ chế fail-fast của iterator chỉ cố gắng phát hiện việc sửa cấu trúc; không nên dùng việc có hay không có ngoại lệ làm phép thử an toàn đồng thời. Nếu entry đã ở vị trí mới nhất, một số lần gọi cũng có thể không làm thứ tự thay đổi; không được từ một trường hợp chạy được suy ra cả mẫu duyệt là an toàn.

Khi chỉ cần quan sát cặp khóa–giá trị trong một luồng, có thể duyệt `entrySet()` và đọc `entry.getKey()`/`entry.getValue()` để tránh tự tạo truy cập `get` trên map. Khi API cache trả bản sao thứ tự khóa như ví dụ, thao tác `clear` trên bản sao không sửa cache. Tuy nhiên, nếu sau đó dùng từng khóa trong bản sao để gọi `cache.get`, các lời gọi đó vẫn sẽ làm mới entry trong cache thật. Có bản sao giúp tránh view liên kết; nó không biến `get` thành thao tác không ảnh hưởng LRU.

## 9. Kiểm tra một cache LRU như thế nào?

### 9.1. Kiểm tra cả dữ liệu lẫn thứ tự

Một kiểm tra tốt phải quan sát đúng chính sách, không chỉ kiểm tra số lượng. Với giới hạn ba, chuỗi `put(A)`, `put(B)`, `put(C)`, `get(A)`, `put(D)` phải thỏa:

- A vẫn có và D có trong cache.
- B không còn trong cache.
- Thứ tự cuối là `[C, A, D]`.
- Số entry cuối là ba.

Nếu chỉ kiểm tra số entry, một cache FIFO sai chính sách cũng có thể vượt qua. Nếu chỉ so sánh hai map bằng `Map.equals`, phép so sánh kiểm tra các mapping, không xác nhận thứ tự LRU. Tương tự, so sánh hai tập khóa không xác nhận thứ tự. Khi cần kiểm tra thứ tự, hãy chuyển nó thành một `List` rồi so sánh danh sách theo đúng thứ tự mong đợi.

Đừng vô tình làm thay đổi chính trạng thái đang kiểm tra: gọi `get` để kiểm tra sự tồn tại của hàng loạt khóa sẽ làm mới từng entry theo thứ tự gọi. Có thể dùng `containsKey` để kiểm tra có/không mà không làm mới, và dùng bản sao thứ tự để xác nhận LRU. Nếu chủ đích đang kiểm tra hiệu ứng của `get`, cần tính cả hiệu ứng đó vào kết quả mong đợi.

### 9.2. Những trường hợp biên đáng kiểm tra

| Trường hợp | Kết quả mong đợi theo các lớp cache trong bài | Lỗi có thể phát hiện |
|---|---|---|
| Thêm đúng bằng giới hạn | Giữ đủ số entry cho phép | Dùng `>=` thay vì `>` |
| Thêm vượt giới hạn một khóa mới | Loại entry đầu hiện tại | Không ghi đè hook hoặc sai điều kiện |
| Đọc thành công một khóa cũ | Đưa entry đó thành mới nhất | Quên `accessOrder=true` |
| Đọc khóa không có | Trả `null`, không tạo entry | Trộn đọc và tự thêm giá trị mặc định ngoài hợp đồng |
| `containsKey` trên entry cũ | Không đổi thứ tự | Hiểu nhầm mọi kiểm tra đều làm mới |
| `put` khóa đã tồn tại | Cập nhật và làm mới, không tăng số entry | Coi mọi `put` là một lần thêm khóa |
| Giới hạn 0 | Sau `put`, cache rỗng | Không định nghĩa rõ cấu hình tắt lưu đệm |
| Giới hạn âm | Constructor ném `IllegalArgumentException` | Để lỗi cấu hình trôi vào thời gian chạy sau đó |
| Khóa/giá trị `null` trong lớp bọc | Báo lỗi trước khi sửa map | Cho `null` lọt vào làm hit/miss nhập nhằng |
| Xóa danh sách khóa sao chép | Cache không đổi | Trả lộ view liên kết |

Trong phần tải theo yêu cầu, đếm số lần loader thực sự chạy là bằng chứng hữu ích: chuỗi `a, b, a, c, b` ở giới hạn hai phải tải bốn lần, không phải ba lần theo số khóa phân biệt và cũng không phải năm lần theo số yêu cầu.

Điều kiện `size() <= maximumEntries` của thiết kế này được hiểu sau khi các thao tác thêm công khai hoàn tất bình thường. Ngay trong hook, map có thể tạm thời có `maximumEntries + 1` entry. Một kiểm tra ném lỗi chỉ vì thấy kích thước tạm thời đó sẽ phủ nhận chính cơ chế thêm rồi loại đang dùng.

### 9.3. Chi phí của các thao tác

Với phân bố băm phù hợp, các thao tác cơ bản như `get` và `put` có thời gian trung bình hằng số theo mô hình của bảng băm. Việc duy trì thứ tự và loại entry đầu không đòi hỏi quét toàn bộ cache trong chính sách này. Đây là một lý do `LinkedHashMap` phù hợp để minh họa LRU nhỏ.

Tuy nhiên, không phải mọi phương thức của lớp bọc đều có cùng chi phí. `keysLruToMru()` sao chép n khóa vào danh sách mới nên tốn thời gian và bộ nhớ theo n. Các dòng in toàn bộ thứ tự trong ví dụ phục vụ quan sát; chúng cũng duyệt dữ liệu. Loader có chi phí riêng, có thể lớn hơn nhiều so với một lần tra cứu map.

Không nên biến nhận xét “get/put trung bình nhanh” thành cam kết mọi thao tác đều có độ trễ cố định. Chất lượng băm, kích thước dữ liệu, cấp phát, việc mở rộng bảng và công việc tải dữ liệu đều có thể ảnh hưởng chi phí thực tế.

## 10. Lỗi phổ biến và cách sửa đúng trọng tâm

| Cách viết hoặc suy luận sai | Vì sao sai | Cách xử lý |
|---|---|---|
| `new LinkedHashMap<>(3)` là cache ba entry | Số 3 là dung lượng ban đầu yêu cầu | Có giới hạn riêng và quy tắc loại bỏ |
| Bật `accessOrder=true` là đã có cache hữu hạn | Nó chỉ giữ thứ tự truy cập | Ghi đè hook theo giới hạn |
| Hook đúng nhưng dùng constructor mặc định | Entry đầu là cũ nhất theo thứ tự chèn | Bật chế độ truy cập nếu muốn LRU |
| `size() >= maximumEntries` | Entry mới đã nằm trong map khi hook chạy | Dùng `size() > maximumEntries` |
| Mỗi `get` đều gọi hook | Đọc có thể đổi thứ tự nhưng không phải thêm entry mới | Phân biệt cập nhật độ mới và kiểm tra loại bỏ |
| `put` khóa cũ luôn tạo một entry mới | Mapping của khóa đã có được cập nhật | Xem riêng đường thêm và đường cập nhật |
| Tự `remove` rồi trả `true` | Vừa sửa map vừa yêu cầu map loại tiếp có hành vi không được quy định | Trong mẫu này chỉ trả quyết định |
| Bỏ entry LRU là xóa dữ liệu gốc | Cache chỉ giữ bản hoặc kết quả có thể tạo lại | Tách lưu đệm khỏi lưu trữ nguồn |
| Entry không được đọc lâu sẽ tự hết hạn | Không có bộ định thời trong cơ chế LRU này | Đừng gán bảo đảm TTL cho cache |
| Chỉ khóa `put`, để `get` chạy tự do ở nhiều luồng | `get` có thể sửa thứ tự truy cập | Thiết kế phối hợp toàn bộ trạng thái |
| Dùng `null` vừa làm dữ liệu vừa làm dấu hiệu miss | `get == null` không còn phân biệt được hai trường hợp | Chọn rõ chính sách giá trị hoặc kiểu kết quả |
| So sánh tập khóa để xác nhận LRU | Tập không mô tả thứ tự trong phép bằng nhau | So sánh một danh sách theo thứ tự |

## 11. Tự kiểm tra

1. Vì sao `removeEldestEntry` đi cùng thứ tự chèn chưa đủ để tạo LRU?
2. Với giới hạn ba, khi hook được gọi sau lần thêm khóa thứ tư, `size()` là mấy?
3. Vì sao điều kiện `>=` làm cache giới hạn một entry không giữ được entry nào sau `put`?
4. `get` tìm thấy entry và `containsKey` tìm thấy entry có cùng hiệu ứng lên LRU không?
5. Cập nhật giá trị của khóa đã có bằng `put` có làm tăng số entry không? Có thể đổi thứ tự không?
6. Một lần trả `true` có ý nghĩa tự dọn mọi entry thừa đến khi đạt một giới hạn vừa giảm mạnh không?
7. Vì sao lớp bọc kiểm tra khác `null` trước khi gọi `entries.put`?
8. Cache có giới hạn 0 trả kết quả vừa tải cho yêu cầu hiện tại được không?
9. Vì sao chỉ đồng bộ từng `get` và `put` chưa bảo đảm một khóa chỉ có một lần tải đang thực hiện?
10. Với cache giới hạn hai, yêu cầu `x, y, x, z, y` cần bao nhiêu lần tải và kết thúc theo thứ tự nào?

### Đáp án và lập luận

1. Thứ tự chèn không đổi khi A được đọc lại. Loại entry đầu sẽ loại entry vào sớm nhất, kể cả entry vừa được dùng. LRU cần thứ tự truy cập để entry đầu phản ánh entry ít được dùng gần đây nhất.
2. Bốn. Entry mới đã được thêm; hook quyết định có loại entry đầu để quay về ba hay không.
3. Entry đầu tiên tạo `size=1`; `1 >= 1` đúng nên nó bị loại ngay. Điều kiện đúng `1 > 1` là sai nên giữ được entry đó.
4. Không. `get` thành công làm entry thành mới nhất; `containsKey` không làm mới thứ tự truy cập.
5. Không tăng số entry. Trong map theo thứ tự truy cập, `put` khóa đã có vẫn làm entry đó thành mới nhất; không có lần thêm mới để kích hoạt hook theo đường chèn.
6. Không. Một quyết định `true` yêu cầu bỏ entry `eldest`. Thiết kế giới hạn cố định đủ dùng một lần loại sau mỗi lần thêm; thay giới hạn động cần cơ chế thu gọn riêng.
7. Để đầu vào sai bị từ chối trước mọi thay đổi và trước nguy cơ loại một entry hợp lệ. Đồng thời giữ hợp đồng `null` từ `get` nghĩa là miss.
8. Có. Phương thức có thể tải, thử lưu rồi trả kết quả đã tính. Cache không giữ entry sau thao tác, nên yêu cầu sau lại phải tải.
9. Hai luồng có thể lần lượt kiểm tra và cùng thấy miss trước khi một luồng ghi kết quả. Chuỗi nhiều bước cần một hợp đồng phối hợp riêng; khóa từng lệnh không gộp chúng thành một bước nguyên tử.
10. Bốn lần tải: x, y, z, rồi y một lần nữa. Các thứ tự sau mỗi yêu cầu là `[x]`, `[x, y]`, `[y, x]`, `[x, z]`, `[z, y]`. Lần dùng x thứ hai là hit; y đã bị loại khi thêm z.

## 12. Thực hành có kết quả đối chiếu

### Bài 1: xác nhận lỗi ranh giới

Trong một bản sao của chương trình quan sát hook, đổi điều kiện thành `size() >= maximumEntries` rồi chạy với giới hạn ba. Trước khi chạy, dự đoán sau ba lần thêm A, B, C còn những khóa nào. Kết quả phải chỉ còn B, C: A đã bị loại khi kích thước vừa bằng ba. Sau đó khôi phục điều kiện đúng và xác nhận map giữ A, B, C.

Mục đích là hiểu thời điểm đánh giá điều kiện, không phải thêm một nhánh đặc biệt cho lần chèn thứ ba. Cùng một điều kiện `>` phải xử lý được giới hạn 0, 1 và lớn hơn.

### Bài 2: tách quan sát và sử dụng

Với giới hạn hai, thêm A, B rồi gọi `containsKey("A")`, sau đó thêm C. Dự đoán A bị loại và thứ tự còn `[B, C]`. Làm lại từ map rỗng nhưng thay `containsKey("A")` bằng `get("A")`; lần này B bị loại và thứ tự còn `[A, C]`.

Hai lần thử phải khởi tạo cache riêng để có cùng điểm xuất phát. Nếu tiếp tục trên cache đã bị thay đổi từ lần thử trước, kết quả sẽ không còn phản ánh đúng một khác biệt duy nhất giữa hai phương thức.

### Bài 3: theo dõi đường cập nhật khóa cũ

Với giới hạn hai, thêm A=a, B=b rồi `put("A", "a2")`. Xác nhận kích thước vẫn hai, thứ tự `[B, A]`, giá trị của A là `a2`. Sau đó thêm C và xác nhận B bị loại. Nếu dùng `get("A")` để kiểm tra giá trị, ghi nhận rằng lời gọi đó cũng là một lần truy cập; ở thời điểm này A đã mới nhất nên thứ tự quan sát vẫn như cũ.

### Bài 4: chứng minh việc loại không làm mất nguồn

Trong chương trình tải theo yêu cầu, giữ loader có thể tạo lại cùng kết quả cho cùng khóa. Chạy chuỗi `a, b, a, c, b`, đối chiếu b được tải hai lần nhưng đều trả `B`. Dữ liệu rời cache rồi được tạo lại; số lần tải tăng, còn ý nghĩa của kết quả không thay đổi.

Tiêu chí hoàn thành là giải thích được vì sao một yêu cầu hit, một yêu cầu miss và entry nào phải rời cache ở từng bước. Chỉ nhìn thấy chương trình chạy không lỗi chưa chứng minh chính sách LRU đã đúng.

## 13. Tài liệu đối chiếu và môi trường chạy

Các chương trình trong bài dùng cú pháp và API tương thích Java 17. Chúng đã được biên dịch với `javac --release 17 -encoding UTF-8` và chạy trên JDK 24.0.2; stdout phía trên là kết quả đã đối chiếu từ các lần chạy đó. Mỗi tệp chỉ chứa một lớp `public` cùng tên tệp, không phụ thuộc thư viện ngoài.

- [LinkedHashMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): thứ tự chèn/truy cập, các thao tác tạo truy cập, thời điểm và hợp đồng của `removeEldestEntry`, giới hạn đồng bộ và iterator.
- [Map — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): hợp đồng mapping, ý nghĩa của `get`, giá trị `null`, phép bằng nhau và các view.
- [Objects.requireNonNull — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): kiểm tra tham chiếu đầu vào khác `null`.
