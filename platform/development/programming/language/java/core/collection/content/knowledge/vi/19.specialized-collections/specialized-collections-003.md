# WeakHashMap: khóa yếu và tác động của thu gom rác

## 1. Khi một bảng tra cứu không nên quyết định tuổi thọ của đối tượng

Giả sử một công cụ phân tích giao diện lưu thêm thông tin cho từng đối tượng cửa sổ. Cửa sổ được quản lý ở nơi khác; bảng này chỉ gắn dữ liệu phụ trợ với nó.

Nếu dùng một HashMap sống rất lâu, chính bảng có thể tiếp tục giữ đối tượng cửa sổ sau khi mọi nơi khác đã ngừng sử dụng nó. Dữ liệu phụ trợ vô tình trở thành chủ sở hữu tuổi thọ của đối tượng.

WeakHashMap cung cấp một lựa chọn khác: **ánh xạ trong map không tự giữ sống khóa bằng tham chiếu mạnh**. Khi đối tượng khóa không còn được giữ theo cách ngăn thu gom và GC xử lý các tham chiếu yếu của nó, ánh xạ có thể biến mất.

Đây là cấu trúc phù hợp để suy nghĩ về dữ liệu phụ trợ gắn với vòng đời đối tượng. Nó không đưa ra cam kết “giữ mục trong năm phút”, “giữ tối đa một nghìn mục” hay “xóa mục ít dùng nhất”.

Ba khái niệm cần tách rõ ngay từ đầu:

| Khái niệm | Câu hỏi nó trả lời |
| --- | --- |
| Quan hệ bằng của khóa | Một lần get đang tìm ánh xạ của khóa nào? |
| Khả năng truy cập đối tượng | Đối tượng khóa còn được giữ sống qua những đường tham chiếu nào? |
| Dọn ánh xạ hết hiệu lực | Khi nào phần tử có khóa đã bị xử lý được tháo khỏi bảng? |

Hai khóa có equals bằng nhau không nhất thiết là cùng một đối tượng được GC theo dõi. Một khóa không còn tham chiếu mạnh cũng không có nghĩa map phải giảm size ngay tại câu lệnh tiếp theo.

Bài này đi từ đồ thị tham chiếu tới hành vi Map, rồi chạy ba chương trình Java 17 để phân biệt điều được bảo đảm với kết quả phụ thuộc GC.

## 2. “Yếu” là thuộc tính của một đường tham chiếu

### 2.1. Tham chiếu mạnh và tham chiếu yếu

Trong mô hình thông thường, một đường tham chiếu mạnh còn dùng được từ chương trình tới đối tượng giúp giữ đối tượng sống.

WeakReference cho phép giữ một liên hệ tới đối tượng mà liên hệ yếu ấy không tự ngăn đối tượng được thu gom. Đối tượng được tham chiếu gọi là đối tượng đích của tham chiếu, thường gặp tên referent trong tài liệu API.

Với WeakHashMap còn sống, mô hình đơn giản là:

```text
chương trình --mạnh--> map --mạnh--> phần tử lưu trữ
phần tử lưu trữ --yếu--> khóa
phần tử lưu trữ --mạnh--> giá trị
```

Mũi tên yếu chỉ nằm ở quan hệ từ phần tử lưu trữ tới khóa. Không suy ra map, các nút lưu trữ hay value đều được giữ yếu.

### 2.2. Phải xét mọi đường tới khóa

Nếu chương trình còn giữ khóa trong một danh sách đang dùng, khóa vẫn sống dù map chỉ tham chiếu yếu tới nó.

Nếu value chứa một trường trỏ mạnh ngược về khóa, đường map → value → key cũng có thể giữ khóa sống.

Nếu chỉ còn chu kỳ không thể truy cập từ chương trình, việc có chu kỳ không tự làm đối tượng sống mãi. Vấn đề là có đường giữ sống tới chu kỳ ấy hay không, chứ không chỉ đếm số tham chiếu.

Vì vậy, “tôi đã gán biến key bằng null” chỉ nói đã bỏ một đường tham chiếu. Nó chưa chứng minh các đường khác đã mất.

### 2.3. Phạm vi biến không đồng nghĩa phạm vi sống của đối tượng

Một tên biến còn xuất hiện trong khối mã không tự bảo đảm JVM giữ đối tượng tới cuối dấu ngoặc. Ngược lại, một đối tượng không còn tên biến cục bộ vẫn có thể được giữ qua trường, collection hoặc tác vụ đang chạy.

[JLS 17, mục 12.6.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6.1) mô tả khả năng biến đổi tối ưu làm đối tượng hết khả năng truy cập sớm hơn cách đọc mã đơn giản.

Các ví dụ cần giữ khóa chắc chắn sẽ dùng Reference.reachabilityFence ở cuối đoạn quan sát. Mục đích là xác định ranh giới giữ sống cho thí nghiệm, không phải ép GC hay khóa một luồng khác.

### 2.4. Không cần học mọi loại reference để dùng đúng bài này

Java còn có SoftReference và PhantomReference với mục đích, quy tắc khác. WeakHashMap dùng khóa yếu; không tự có chính sách mềm dựa trên áp lực bộ nhớ hoặc cơ chế đóng tài nguyên của các loại khác.

Khái niệm khả năng truy cập và các nhóm tham chiếu được giới thiệu trong [gói java.lang.ref của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html). Trong bài này, trọng tâm là đường giữ khóa, không phải thuật toán của từng bộ thu gom rác.

## 3. Từ khóa hết được giữ sống tới ánh xạ biến mất

### 3.1. Không phải cứ hết dùng là có thao tác remove đồng bộ ngay

Một trình tự khái niệm có thể hình dung như sau:

1. Ứng dụng bỏ những đường giữ sống thông thường tới đối tượng khóa.
2. GC xác định đối tượng ở trạng thái có thể xử lý qua tham chiếu yếu.
3. Các tham chiếu yếu thích hợp được xóa liên hệ tới đối tượng đích.
4. Tham chiếu đã đăng ký có thể được đưa vào `ReferenceQueue`.
5. Map xử lý thông tin nội bộ và dọn phần tử có khóa đã hết hiệu lực.

Không gắn mỗi bước với một câu lệnh Java cụ thể hay một khoảng chờ cố định.

Tài liệu [WeakReference Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html) phân biệt lúc xóa các tham chiếu yếu với lúc đưa chúng vào hàng đợi; việc đưa vào hàng đợi có thể xảy ra cùng lúc hoặc sau đó.

### 3.2. `ReferenceQueue` thông báo về reference, không trả lại khóa đã mất

`ReferenceQueue` cho phép nhận các đối tượng Reference đã được đưa vào hàng đợi. Nó không phải một hàng đợi chứa bản sao đầy đủ của các khóa đã bị thu gom.

Trong ví dụ phía sau, một WeakReference quan sát riêng được đăng ký với hàng đợi riêng. Khi poll trả lại đúng reference ấy, ta biết reference quan sát đã được đưa vào hàng đợi. Không suy ra đã trực tiếp đọc được hàng đợi nội bộ của WeakHashMap.

[`ReferenceQueue` Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html) là API đối chiếu cho poll và cơ chế đăng ký reference.

### 3.3. Phân biệt khả năng tìm ánh xạ với phần lưu trữ chờ dọn

Chi tiết OpenJDK 17: WeakHashMap sử dụng một hàng đợi nội bộ; các đường truy cập bảng và size có thể xử lý những phần tử đã được báo hết hiệu lực. Khi dọn, triển khai tháo phần tử và bỏ liên kết tới value.

Vì có nhiều bước, không nên dùng một số đo size làm bằng chứng rằng mọi bộ nhớ liên quan đã được thu hồi tức thì. Một map ít được truy cập có thể còn phần lưu trữ chờ dọn; một value còn được nơi khác giữ vẫn sống sau khi ánh xạ mất.

Đó là phần giải thích theo [mã nguồn WeakHashMap của OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/WeakHashMap.java). Không coi tên hàm nội bộ hay thời điểm dọn cụ thể là hợp đồng cho mọi triển khai Java.

## 4. Yếu về vòng đời không có nghĩa so khóa bằng identity

WeakHashMap vẫn là một Map dựa trên bảng băm. Tra cứu tuân quan hệ equals/hashCode của khóa, không mặc định thay equals bằng toán tử ==.

Phân biệt hai trục:

| Trục | Ví dụ câu hỏi |
| --- | --- |
| Định danh theo equals | Một Key(7) mới có tìm ánh xạ đang có của Key(7) không? |
| Tuổi thọ đối tượng cụ thể | Đối tượng Key(7) nào thực sự được giữ làm đích của tham chiếu yếu? |

Nếu hai đối tượng khác nhau nhưng equals true, một đối tượng mới có thể tìm hoặc cập nhật ánh xạ đang tồn tại. Nhưng việc giữ đối tượng mới không tự tạo một đường tham chiếu mạnh tới đối tượng khóa cũ.

Các kiểu khóa phải có equals/hashCode đúng và ổn định trong lúc được dùng làm khóa. Đổi trường dùng tính hash hoặc equals có thể làm tra cứu sai theo quy tắc của map băm; dùng khóa yếu không chữa lỗi đó. Xem hợp đồng khóa của [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

WeakHashMap nhận cả một khóa null và các value null. Vì vậy get trả null có thể là khóa vắng mặt hoặc một ánh xạ có value null; containsKey hữu ích khi cần phân biệt.

Khóa null không phải một đối tượng ứng dụng có thể mất tham chiếu mạnh như new Object(). Trong OpenJDK 17 nó được biểu diễn bằng một đối tượng đánh dấu được giữ tĩnh. Không trông đợi ánh xạ null tự hết hạn bằng GC; hãy remove(null) hoặc clear khi cần.

## 5. Ví dụ 1: hành vi Map khi các khóa còn được giữ sống

Lưu thành **WeakKeyBasics.java**:

```java
import java.lang.ref.Reference;
import java.util.Map;
import java.util.WeakHashMap;

public class WeakKeyBasics {
    record Key(int id) {}

    public static void main(String[] args) {
        Map<Key, String> map = new WeakHashMap<>();
        Key original = new Key(7);
        Key equalKey = new Key(7);
        Key nullableValueKey = new Key(8);

        map.put(original, "first");
        System.out.println("same object: " + (original == equalKey));
        System.out.println("equal keys: " + original.equals(equalKey));
        System.out.println("lookup equal key: " + map.get(equalKey));
        System.out.println("previous value: " + map.put(equalKey, "updated"));
        System.out.println("size after update: " + map.size());

        map.put(nullableValueKey, null);
        map.put(null, "null-key value");
        System.out.println("null value lookup: " + map.get(nullableValueKey));
        System.out.println("null value key present: " + map.containsKey(nullableValueKey));
        System.out.println("absent key present: " + map.containsKey(new Key(9)));
        System.out.println("null key lookup: " + map.get(null));
        System.out.println("total size: " + map.size());

        System.out.println("removed value: " + map.remove(equalKey));
        System.out.println("original key present: " + map.containsKey(original));
        System.out.println("size after remove: " + map.size());

        Reference.reachabilityFence(original);
        Reference.reachabilityFence(equalKey);
        Reference.reachabilityFence(nullableValueKey);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 WeakKeyBasics.java
java WeakKeyBasics
```

Stdout:

```text
same object: false
equal keys: true
lookup equal key: first
previous value: first
size after update: 1
null value lookup: null
null value key present: true
absent key present: false
null key lookup: null-key value
total size: 3
removed value: updated
original key present: false
size after remove: 2
```

Các chương trình trong bài được biên dịch với --release 17 và chạy trên OpenJDK 24.0.2. --release 17 chọn mức ngôn ngữ/API và bytecode đích; JVM thực thi vẫn là phiên bản đã nêu.

### 5.1. Equal key không cần là cùng object

Hai biến original và equalKey giữ hai record khác nhau, nên == cho false. Dữ liệu id bằng nhau nên equals cho true.

`get` bằng equalKey tìm được "first"; put bằng equalKey trả về giá trị cũ và cập nhật thành "updated". Số ánh xạ vẫn là 1.

Ví dụ này chứng minh WeakHashMap không mặc định là IdentityHashMap. Nó chưa chứng minh ánh xạ tồn tại sau khi đối tượng khóa được lưu không còn được giữ sống.

### 5.2. Các giá trị null không liên quan việc thu gom ở đây

Khóa nullableValueKey có một ánh xạ với value null, còn Key(9) vắng mặt. `containsKey` phân biệt hai trường hợp.

Ánh xạ khóa null là một mục khác, có value "null-key value". Tổng size là 3 trước remove.

Không có chuyện value null tự khiến khóa bị thu gom. Tuổi thọ khóa phụ thuộc đồ thị tham chiếu, không phụ thuộc việc value tình cờ là null.

### 5.3. Vì sao giữ cả original lẫn equalKey?

Thí nghiệm đang kiểm tra hành vi Map, nên không muốn kết quả bị lẫn với việc khóa hết được giữ sống giữa các lần in.

`reachabilityFence` ở cuối bảo đảm các đối tượng cần thiết vẫn được giữ sống qua phần quan sát. Việc giữ cả hai cũng tránh phải dựa vào giả định constructor hay put sẽ chọn đối tượng nào làm đích lưu trữ cho một khóa bằng nhau.

Không dùng một lệnh put với equal key như một giao thức cam kết “đổi chủ sở hữu tuổi thọ” của ánh xạ.

## 6. Ví dụ 2: quan sát GC mà không giả vờ kiểm soát GC

### 6.1. Điều cần quan sát

Ta tạo ba ánh xạ:

- Một khóa held được giữ sống tới hết đoạn đo.
- Một khóa null.
- Một khóa tạm chỉ được trả ra ngoài qua WeakReference.

Hàm addTemporaryKey tạo khóa tạm rồi kết thúc, giúp đoạn main không giữ thêm biến mạnh tới khóa ấy.

Một WeakReference quan sát được đăng ký với `ReferenceQueue` riêng. Nó là công cụ đo; WeakHashMap có cơ chế nội bộ riêng.

### 6.2. Chương trình đầy đủ

Lưu thành **WeakKeyGcObservation.java**:

```java
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;
import java.util.WeakHashMap;

public class WeakKeyGcObservation {
    private static WeakReference<Object> addTemporaryKey(
            WeakHashMap<Object, String> map, ReferenceQueue<Object> queue) {
        Object temporary = new Object();
        map.put(temporary, "temporary value");
        return new WeakReference<>(temporary, queue);
    }

    public static void main(String[] args) throws InterruptedException {
        WeakHashMap<Object, String> map = new WeakHashMap<>();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        Object held = new Object();
        map.put(held, "held value");
        map.put(null, "null-key value");
        WeakReference<Object> observer = addTemporaryKey(map, queue);

        boolean cleared = false;
        boolean enqueued = false;
        boolean removed = false;
        for (int attempt = 0; attempt < 100; attempt++) {
            System.gc();
            Thread.sleep(10);
            cleared = observer.refersTo(null);

            Reference<?> notification;
            while ((notification = queue.poll()) != null) {
                if (notification == observer) {
                    enqueued = true;
                }
            }

            removed = map.size() == 2;
            if (cleared && enqueued && removed) {
                break;
            }
        }

        System.out.println("observer cleared: " + cleared);
        System.out.println("observer enqueued: " + enqueued);
        System.out.println("temporary mapping removed: " + removed);
        System.out.println("held lookup: " + map.get(held));
        System.out.println("null-key lookup: " + map.get(null));
        System.out.println("remaining size: " + map.size());
        Reference.reachabilityFence(held);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 WeakKeyGcObservation.java
java WeakKeyGcObservation
```

**Stdout dưới đây là kết quả quan sát của một lần chạy trên OpenJDK 24.0.2, không phải kết quả Java bảo đảm xuất hiện trong mọi lần chạy:**

```text
observer cleared: true
observer enqueued: true
temporary mapping removed: true
held lookup: held value
null-key lookup: null-key value
remaining size: 2
```

### 6.3. Ba điều được đo riêng

Observer cleared cho biết reference quan sát đã không còn đối tượng đích. `refersTo`(null) kiểm tra điều đó mà không cần lấy một tham chiếu mạnh mới bằng get.

Observer enqueued cho biết reference quan sát đã được lấy ra từ hàng đợi của thí nghiệm. Không dùng isEnqueued để chờ, vì trạng thái hàng đợi có thể thay đổi và API ấy đã bị đánh dấu deprecated.

Temporary mapping removed được suy ra từ size bằng 2 trong điều kiện chương trình chỉ có ba ánh xạ đã mô tả, không có luồng ứng dụng khác sửa map, held được giữ sống và khóa null không bị xóa. Đó không phải một công thức phát hiện mọi khóa chết trong một map bất kỳ.

Các lần gọi size cũng tạo cơ hội cho triển khai dọn những phần tử nội bộ đã hết hiệu lực.

### 6.4. Nếu ba cờ chưa thành true thì sao?

Vòng lặp có tối đa 100 lượt; mỗi lượt gửi gợi ý GC và ngủ 10 ms. Nó không phải cam kết GC phải hoàn tất trong một giây, cũng không bảo đảm tổng thời gian thực thi đúng một giây.

Nếu quan sát chưa hoàn tất, chương trình vẫn kết thúc và in trạng thái đã thấy. Không có AssertionError ép thời điểm thu gom thành điều kiện đúng của ứng dụng.

Theo [System.gc Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()), lời gọi này chỉ gợi ý JVM nỗ lực thu hồi. Nó không bảo đảm thu hồi một đối tượng cụ thể, xóa/enqueue một số reference cụ thể hay hoàn tất vào thời điểm yêu cầu.

Thread.sleep không tạo bảo đảm ấy. Lặp System.gc thật nhiều cũng không biến yêu cầu thành một đồng hồ hết hạn đáng tin cậy.

### 6.5. Một lần chạy khác trên cùng JVM

OpenJDK/HotSpot hỗ trợ tùy chọn thử nghiệm sau:

```shell
java -XX:+DisableExplicitGC WeakKeyGcObservation
```

Trong môi trường kiểm tra của bài, lần chạy này in:

```text
observer cleared: false
observer enqueued: false
temporary mapping removed: false
held lookup: held value
null-key lookup: null-key value
remaining size: 3
```

Tùy chọn này làm các yêu cầu GC tường minh bị bỏ qua trong JVM đang dùng; nó không có nghĩa mọi hoạt động GC tự động đều bị tắt. JVM khác có thể không nhận tùy chọn này.

Hai stdout khác nhau đều phù hợp với mục đích chương trình. Lần chạy chưa thấy khóa tạm biến mất không đủ kết luận WeakHashMap bị rò rỉ. Cần phân tích đường giữ sống và khả năng GC đã thực sự xử lý reference hay chưa.

## 7. Bẫy quan trọng nhất: value giữ mạnh ngược về key

### 7.1. Bỏ biến bên ngoài chưa chắc bỏ đường giữ khóa

Nếu một value có trường owner trỏ về chính khóa, đồ thị có thêm đường mạnh; tài liệu [WeakHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html) cũng chỉ rõ trường hợp này:

```text
chương trình --mạnh--> map --mạnh--> value --mạnh--> key
                             phần tử --yếu--> key
```

Cạnh yếu không làm cạnh mạnh mất tác dụng. Map còn được giữ sống, value còn ở trong map và value còn giữ key thì khóa vẫn có đường được giữ sống.

Tương tự, value A có thể giữ khóa B, còn value B giữ khóa A. Nếu cả hai value được map giữ mạnh, một vòng liên hệ gián tiếp vẫn có thể khiến các khóa sống theo map.

Đây là lý do cần đọc toàn bộ đồ thị đối tượng, không chỉ nhìn kiểu WeakHashMap ở khai báo.

### 7.2. Chương trình nhìn thấy đường giữ mạnh

Lưu thành **ValueBackReference.java**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;
import java.util.WeakHashMap;

public class ValueBackReference {
    static final class Metadata {
        Object owner;

        Metadata(Object owner) {
            this.owner = owner;
        }
    }

    public static void main(String[] args) {
        WeakHashMap<Object, Metadata> map = new WeakHashMap<>();
        Object key = new Object();
        Metadata metadata = new Metadata(key);
        WeakReference<Object> observer = new WeakReference<>(key);
        map.put(key, metadata);

        key = null;
        metadata = null;
        System.gc();

        Metadata stored = map.values().iterator().next();
        Object owner = stored.owner;
        System.out.println("value holds key: " + (owner != null));
        System.out.println("observer refers to owner: " + observer.refersTo(owner));
        System.out.println("lookup through owner: " + (map.get(owner) == stored));

        stored.owner = null;
        System.out.println("owner field detached: " + (stored.owner == null));
        System.out.println("local owner still finds value: " + (map.get(owner) == stored));

        map.clear();
        System.out.println("size after explicit clear: " + map.size());
        System.out.println("observer still refers to local owner: " + observer.refersTo(owner));
        Reference.reachabilityFence(owner);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ValueBackReference.java
java ValueBackReference
```

Stdout:

```text
value holds key: true
observer refers to owner: true
lookup through owner: true
owner field detached: true
local owner still finds value: true
size after explicit clear: 0
observer still refers to local owner: true
```

Đây là ví dụ kiểm tra một đường tham chiếu mạnh đang tồn tại. Nó không cần GC thực hiện một lần thu gom thành công mới cho kết quả như trên.

### 7.3. Cách đọc từng giai đoạn

Sau khi key và metadata được gán null, map vẫn giữ Metadata, và Metadata vẫn giữ owner. Vì vậy có thể đi từ value trong map tới khóa, rồi dùng khóa ấy tra lại chính value.

Lệnh System.gc không thể biến một khóa còn đường giữ sống hợp lệ thành khóa không được sử dụng chỉ vì map tên là WeakHashMap.

Sau khi stored.owner được gán null, biến owner trong chương trình vẫn còn giữ khóa. `reachabilityFence` ở cuối giữ ranh giới này rõ ràng. Chỉ cắt trường owner chưa đủ làm mọi đường mạnh biến mất.

`clear` tháo các ánh xạ một cách tường minh, nên size bằng 0. Điều đó vẫn không thu gom đối tượng owner ngay, vì chương trình còn giữ nó.

Ba việc khác nhau là: cắt một đường tham chiếu, xóa một ánh xạ và GC thu hồi một đối tượng. Không dùng cùng từ “xóa” để suy ra cả ba đã xảy ra.

### 7.4. Chọn value phù hợp với mục đích phụ trợ

Nếu muốn dữ liệu phụ trợ không giữ đối tượng chính sống, value nên chứa thông tin không dẫn mạnh về đối tượng ấy: chẳng hạn số đo đã tính hoặc dữ liệu mô tả tách rời.

Cần kiểm tra cả liên hệ gián tiếp qua callback, đối tượng bao ngoài, collection và các value khác.

Một lựa chọn khác là chủ động dùng tham chiếu yếu trong phần value phù hợp với nghiệp vụ. Đó là thay đổi chính sách giữ dữ liệu: value có thể biến mất và nơi đọc phải chấp nhận điều đó.

Không thay mọi trường bằng WeakReference một cách máy móc. Nếu ứng dụng cần dữ liệu tồn tại ổn định, chính sách yếu có thể làm sai yêu cầu thay vì giải quyết nó.

## 8. Đối tượng khóa thật khác với “cùng một mã nghiệp vụ”

### 8.1. Vì sao tài liệu nhắc tới khóa theo identity?

Với một đối tượng dùng equals mặc định của Object, chỉ chính đối tượng ấy bằng nó theo identity. Sau khi đối tượng thật sự không còn dùng được nữa, ứng dụng không tạo một object mới rồi đòi nó phải bằng đối tượng đã mất.

Điều này làm chính sách vòng đời dễ hiểu: dữ liệu phụ trợ theo đúng đối tượng đang sống.

Tài liệu [WeakHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html) mô tả nhóm khóa này là mục đích sử dụng chính, đồng thời vẫn cho phép các kiểu dùng equals theo giá trị.

Đó là hướng dẫn chọn khóa, không phải việc WeakHashMap tự thay đổi cách so bằng của mọi kiểu.

### 8.2. Khóa theo giá trị có thể được tạo lại nhưng ánh xạ không được hứa giữ lại

Giả sử một lời gọi tạo một đối tượng mã khách hàng mới rồi put kết quả tra cứu. Khi lời gọi kết thúc, không còn nơi nào giữ đối tượng khóa đã lưu.

Lời gọi sau có thể tạo một đối tượng mã mới equals với mã cũ. Tuy nhiên, đối tượng mới không tự giữ đối tượng cũ sống, và ánh xạ cũ có thể đã biến mất sau GC.

Nếu mục đích là nhớ kết quả theo chuỗi mã qua nhiều yêu cầu, vòng đời của một object mã tạm thường không phải chính sách lưu giữ mong muốn.

Một kiểu khóa bất biến giúp equals/hashCode ổn định. Nó không tự làm object ấy được giữ sống lâu hơn trong một map khóa yếu.

### 8.3. Các nguồn giữ khóa ngoài dự tính

Nếu thí nghiệm không thấy khóa mất, cần xét những nơi có thể còn giữ nó:

- Một HashMap, danh sách, trường static hoặc đối tượng quản lý đang sống.
- Một value trỏ ngược về khóa.
- Một tác vụ hoặc callback còn nắm đối tượng liên quan.
- Một bản sao dữ liệu chứa chính đối tượng khóa.
- Công cụ quan sát hoặc đoạn mã đo đã giữ lại khóa vừa đọc.

Với String, dữ liệu dùng chung và các đối tượng có sẵn trong bộ nhớ đệm của thư viện cũng có thể làm thí nghiệm khó suy luận. Không dùng một literal hoặc một đối tượng dùng chung rồi mặc định chỉ còn map tham chiếu tới nó.

Trong ví dụ GC, new Object() được tạo ở hàm riêng nhằm tạo một khóa tạm không chia sẻ theo chủ đích. Cách đó giúp lập luận về thí nghiệm; vẫn không điều khiển thời điểm thu gom.

### 8.4. Chính việc quan sát có thể kéo dài tuổi thọ

WeakReference.get trả về một tham chiếu thông thường tới đối tượng đích nếu còn. Nếu giữ kết quả trong một biến đang dùng, thí nghiệm đã thêm đường mạnh trong giai đoạn ấy.

`refersTo`(null) phù hợp khi chỉ cần hỏi reference đã được xóa liên hệ hay chưa. `ReferenceQueue` phù hợp khi cần theo dõi thông báo đã enqueue.

Một danh sách chứa các khóa lấy từ map hoặc một HashMap sao chép các ánh xạ sẽ giữ mạnh những khóa được chép khi bản sao còn được sử dụng. Không giữ bản sao như vậy trong lúc đo rồi kết luận WeakHashMap không nhả khóa.

Riêng view keySet không đồng nghĩa một bản sao giữ mạnh toàn bộ khóa. Cần phân biệt view, iterator và dữ liệu đã chép ra.

Các thao tác reference và ranh giới giữ sống được mô tả trong [Reference Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html).

## 9. Những thay đổi có thể xảy ra dù ứng dụng không gọi remove

Một chương trình chỉ có một luồng vẫn có thể thấy ánh xạ giảm đi khi GC xử lý khóa. Đây là hành vi được mô tả trong [WeakHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html). Không có lời gọi remove trong mã nghiệp vụ không có nghĩa nội dung phải giữ nguyên.

Các quan sát hợp lệ có thể gồm size nhỏ hơn, isEmpty thay đổi, một phép tìm sau không còn thấy ánh xạ từng tồn tại.

Điều đó có ý nghĩa trực tiếp với cách viết ứng dụng:

- Không dùng size trước đó để cam kết chính xác số mục sẽ xử lý trong một lần duyệt sau.
- Không dùng dữ liệu phụ trợ yếu làm bằng chứng bắt buộc về việc một giao dịch đã tồn tại.
- Khi việc thiếu ánh xạ là trạng thái bình thường của thiết kế, chuẩn bị cách tính lại hoặc bỏ qua thích hợp.
- Khi cần giữ một đối tượng trong suốt thao tác, giữ đường tham chiếu mạnh có chủ đích tới chính đối tượng cần dùng.

Một ngoại lệ quan trọng trong cách suy luận: nếu chương trình đang giữ mạnh chính khóa đã lưu qua toàn bộ thao tác và không có ai xóa/tác động khác, GC không được tự làm đối tượng khóa ấy mất. Đừng diễn đạt tính không chắc chắn thành “mọi mục đều biến mất tùy tiện ngay cả khi khóa còn được dùng”.

### 9.1. Khả năng truy cập đồng thời là một vấn đề riêng

WeakHashMap không tự đồng bộ. Nếu nhiều luồng cùng truy cập có sửa đổi, phải chọn cơ chế bảo vệ thích hợp.

Collections.synchronizedMap có thể bao map; mọi truy cập cần đi qua lớp bao. Khi duyệt collection view bằng iterator, cần đồng bộ trên map được trả về theo quy tắc API. Xem [Collections.synchronizedMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)).

Đồng bộ bảo vệ truy cập của các luồng ứng dụng. Nó không biến khóa yếu thành khóa mạnh và không cấm GC xử lý một khóa không còn được giữ sống.

Tương tự, một chuỗi kiểm tra rồi hành động vẫn cần được thiết kế như một thao tác nghiệp vụ nhất quán nếu có dữ liệu dùng chung. Một lớp bao không tự suy ra ý nghĩa nghiệp vụ của cả chuỗi.

### 9.2. Fail-fast không phải thông báo khóa đã bị thu gom

Iterator có cơ chế dừng sớm (fail-fast) đối với sửa cấu trúc theo hợp đồng và giới hạn best effort của nó. Không viết chương trình dựa vào ConcurrentModificationException để biết một khóa đã chết hoặc để bảo đảm an toàn luồng.

Trong OpenJDK 17, đường dọn phần tử do GC không vận hành như một lời gọi put/remove thông thường làm tăng bộ đếm sửa đổi. Iterator còn có thể giữ tạm khóa đang xét để dùng nó.

Vì thế không giả định mỗi lần GC bỏ khóa đều phải ném ngoại lệ, cũng không giả định một iterator là ảnh chụp bất biến của toàn map.

## 10. Giới hạn thực tế: đây không phải chính sách bộ nhớ đệm hoàn chỉnh

### 10.1. Không có thời gian hết hạn hoặc giới hạn số mục

WeakHashMap có thể giữ một ánh xạ rất lâu nếu khóa còn được dùng ở nơi khác. Nó cũng có thể mất ánh xạ sớm hơn mong đợi nếu khóa chỉ là object tạm.

Nó không định nghĩa thời hạn tồn tại (TTL), không tự giới hạn số ánh xạ theo một con số nghiệp vụ và không chọn mục ít dùng nhất.

Initial capacity là tham số tổ chức bảng băm, không phải số phần tử tối đa được phép lưu. Đổi load factor cũng không biến vòng đời khóa thành hạn sử dụng.

Nếu yêu cầu là giữ dữ liệu theo thời gian hoặc dung lượng, phải chọn chính sách thể hiện yêu cầu đó. Không thay câu hỏi “khi nào khóa hết sống?” cho câu hỏi “khi nào dữ liệu phải hết hạn?”.

### 10.2. Khóa yếu không đồng nghĩa giá trị yếu

Giả sử một khóa còn được ứng dụng giữ mạnh rất lâu và value chứa một mảng lớn. WeakHashMap vẫn giữ mạnh mảng ấy khi ánh xạ tồn tại.

Nếu chọn Map<K, WeakReference<V>> hoặc kết hợp thêm value yếu, lúc đọc còn phải phân biệt: không có ánh xạ, có wrapper nhưng đích đã bị xóa, hoặc có value đang dùng được.

Nên lấy value từ một WeakReference một lần vào biến cục bộ rồi kiểm tra và sử dụng giá trị đã lấy. Hai lần gọi get liên tiếp không phải một cam kết giá trị còn nguyên giữa hai lần nếu không giữ nó.

Đây là thiết kế giữ dữ liệu khác, không phải tính năng được kích hoạt sẵn bởi tên WeakHashMap.

### 10.3. Không dùng thời điểm GC để đóng tài nguyên bắt buộc

Nếu một thao tác cần đóng tệp, kết nối hoặc giải phóng tài nguyên ở một thời điểm xác định, hãy có cơ chế sở hữu và đóng tường minh phù hợp.

Việc một mục tự biến mất không tương đương lời gọi close đã chạy thành công. WeakHashMap không cung cấp một giao thức hoàn tất tài nguyên hay thông báo nghiệp vụ đáng tin cậy.

Không gắn tính đúng của ứng dụng với việc một vòng GC có diễn ra hay không.

### 10.4. Chi phí gồm cả cơ chế reference và dọn bảng

Cấu trúc vẫn dùng băm, nhưng có thêm đối tượng/cơ chế cho tham chiếu yếu và xử lý các phần tử hết hiệu lực. Một thao tác truy cập có thể kèm công việc dọn.

Không đo một lời gọi rồi kết luận mọi get đều có độ trễ cố định. Phân bố hash, kích thước bảng và công việc dọn đang chờ đều ảnh hưởng chi phí quan sát.

WeakHashMap là một lớp triển khai riêng; không mặc định mọi chi tiết nội bộ tối ưu của HashMap đều được sao chép sang nó.

## 11. Chọn cách dùng và cách kiểm tra

### 11.1. Một tình huống phù hợp

Một công cụ lưu kết quả phân tích phụ trợ cho các đối tượng đang được hệ thống chính giữ sống. Kết quả có thể tính lại, việc thiếu kết quả được xử lý bình thường, và value không dẫn mạnh về khóa.

Đây là một thiết kế có thể cân nhắc khóa yếu vì dữ liệu phụ trợ không nên quyết định tuổi thọ đối tượng chính.

Trước khi triển khai, vẫn cần trả lời ai giữ map, ai giữ key, value có giữ lại key gián tiếp không và các luồng truy cập thế nào.

### 11.2. Những yêu cầu nên được diễn đạt bằng chính sách khác

| Yêu cầu | Điều cần thiết kế rõ |
| --- | --- |
| Lưu bằng chứng nghiệp vụ bắt buộc | Cơ chế lưu giữ có tuổi thọ do nghiệp vụ quyết định |
| Giữ kết quả ít nhất một khoảng thời gian | Chính sách thời gian rõ ràng |
| Không vượt dung lượng cho phép | Chính sách dung lượng và loại bỏ rõ ràng |
| Gắn dữ liệu phụ trợ với một đối tượng đang sống | Quan hệ tham chiếu và khả năng tính lại khi thiếu |
| Đóng tài nguyên khi kết thúc thao tác | Quy trình đóng tường minh và xử lý lỗi |
| Tìm theo mã có thể tạo lại giữa các yêu cầu | Chính sách lưu theo mã, không mặc định theo tuổi thọ object mã tạm |

Không chọn cấu trúc chỉ vì nó có khả năng tự làm size nhỏ đi.

### 11.3. Tách kiểm thử hành vi Map khỏi quan sát GC

Kiểm thử hành vi Map có thể giữ mạnh khóa và xác nhận equals/hashCode, cập nhật giá trị, remove, null và cách ứng dụng xử lý thiếu dữ liệu.

Thí nghiệm GC nên:

1. Tạo khóa tạm không được chia sẻ theo chủ đích.
2. Tránh giữ bản sao khóa trong dữ liệu đo.
3. Dùng reference quan sát và hàng đợi nếu cần.
4. Có số lần quan sát hữu hạn.
5. Ghi rõ đã quan sát được hay chưa, không coi một hạn chờ tùy ý là hợp đồng JVM.
6. Kiểm tra riêng các đường giữ mạnh nếu kết quả khác mong đợi.

Để kiểm tra một cơ chế xử lý “không có dữ liệu phụ trợ”, có thể tạo trực tiếp tình huống ánh xạ vắng mặt bằng remove/clear trong kiểm thử nghiệp vụ. Không cần bắt GC làm đồng hồ để xác nhận nhánh ấy.

Nếu tự gọi clear trên một WeakReference do mình tạo, cần ghi rõ đó là xóa reference tường minh; không coi nó là bằng chứng GC đã thu gom khóa hay WeakHashMap đã dọn reference nội bộ.

## 12. Bài tập tự kiểm tra

### Bài 1. Vì sao put không bảo đảm giữ khóa sống?

Một object chỉ còn được WeakHashMap giữ làm khóa; value là dữ liệu không trỏ về object ấy. Việc có ánh xạ trong map có ngăn khóa được thu gom không?

**Gợi ý trả lời:** Cạnh từ phần tử tới khóa là yếu nên bản thân ánh xạ không giữ sống khóa theo cách tham chiếu mạnh. Thời điểm GC xử lý vẫn không được cam kết.

### Bài 2. Tại sao gán key bằng null chưa đủ?

Sau khi put(key, metadata), metadata.owner vẫn bằng key. Gán biến key bằng null có làm khóa chỉ còn được tham chiếu yếu không?

**Gợi ý trả lời:** Chưa. Nếu map còn sống, đường map → metadata → owner vẫn giữ mạnh khóa.

### Bài 3. Equal key có giữ được object cũ không?

Tạo một Key(12) mới equals với khóa đã lưu. Chỉ giữ object mới có tự giữ object cũ sống không?

**Gợi ý trả lời:** Không. Quan hệ equals là quy tắc bằng, không phải đường tham chiếu từ object mới tới object cũ.

### Bài 4. Một giây chưa thấy size giảm có phải lỗi không?

Sau System.gc và một khoảng ngủ, size vẫn như cũ. Có thể kết luận WeakHashMap không hoạt động không?

**Gợi ý trả lời:** Không. Chưa có bảo đảm GC đã xóa reference/enqueue/dọn ánh xạ đúng trong hạn đó; cũng cần kiểm tra còn đường mạnh nào hay không.

### Bài 5. Vì sao value lớn vẫn tồn tại?

Ứng dụng giữ mạnh key lâu dài. Value là một mảng lớn không còn nơi nào khác dùng. WeakHashMap có tự giữ value yếu không?

**Gợi ý trả lời:** Không. Value vẫn được map giữ mạnh khi ánh xạ còn; yếu là chính sách cho key.

### Bài 6. Key null có tự hết hạn không?

Đưa null → dữ liệu vào WeakHashMap rồi không giữ thêm biến khóa nào. Có nên chờ mục null được thu gom không?

**Gợi ý trả lời:** Không. Null không phải object khóa tạm có thể hết được giữ sống; triển khai OpenJDK dùng đối tượng đánh dấu được giữ tĩnh. Khi cần bỏ mục ấy, xóa tường minh.

### Bài 7. Đồng bộ có đóng băng map không?

Bao WeakHashMap bằng synchronizedMap và đồng bộ đúng khi duyệt. Các khóa đã không còn được giữ sống có bị ngăn GC chỉ nhờ đồng bộ map không?

**Gợi ý trả lời:** Không. Bảo vệ truy cập ứng dụng không thay chính sách tham chiếu tới khóa.

### Bài 8. Bản sao để đo có làm lệch thí nghiệm không?

Chép các khóa đang thấy vào một danh sách rồi giữ danh sách trong suốt thí nghiệm GC. Điều gì đã thay đổi?

**Gợi ý trả lời:** Danh sách giữ mạnh các object khóa đã chép. Chính dụng cụ đo có thể kéo dài tuổi thọ của chúng.

### Bài 9. Poll nhận về thứ gì?

Một WeakReference được đăng ký với `ReferenceQueue` và sau đó xuất hiện khi poll. Poll trả về object khóa cũ hay object reference?

**Gợi ý trả lời:** Object reference đã được enqueue. Không phải một bản sao khóa để tiếp tục dùng như trước.

### Bài 10. Khi nào nên chọn chính sách khác?

Một bảng kết quả cần giữ chính xác tối đa N mục theo thời gian truy cập gần nhất. Chỉ dùng WeakHashMap có đáp ứng yêu cầu không?

**Gợi ý trả lời:** Không. Cần chính sách dung lượng và loại bỏ theo truy cập; tuổi thọ object khóa không diễn đạt quy tắc đó.

## 13. Tài liệu đối chiếu

- [WeakHashMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): hợp đồng khóa yếu, giá trị mạnh, null và những thay đổi do GC.
- [WeakReference — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): xử lý tham chiếu yếu và thời điểm enqueue.
- [Reference — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): get, refersTo, clear và reachabilityFence.
- [ReferenceQueue — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html): hàng đợi thông báo về reference.
- [System.gc — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()): giới hạn của yêu cầu GC tường minh.
- [Map — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): hợp đồng equals, hashCode và khóa khả biến.
- [Collections.synchronizedMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)): quy tắc truy cập qua lớp bao và đồng bộ khi duyệt.
- [JLS 17, mục 12.6.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6.1): khả năng truy cập đối tượng và tối ưu vòng đời.
- [WeakHashMap.java — OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/WeakHashMap.java): đối tượng đánh dấu null, hàng đợi nội bộ, dọn phần tử và iterator. Các chi tiết này được gắn với phiên bản triển khai, không thay thế hợp đồng API.
