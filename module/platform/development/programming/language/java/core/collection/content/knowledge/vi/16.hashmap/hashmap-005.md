# Va chạm, cây hóa bucket và giới hạn của chi tiết cài đặt

## 1. Vì sao một HashMap cần xử lý nhiều khóa cùng bucket?

Một HashMap có số bucket hữu hạn, trong khi ứng dụng có thể đưa vào rất nhiều khóa. Nhiều khóa có thể cùng được định hướng vào một bucket. Đó là **va chạm (collision)**, một tình huống bình thường mà cấu trúc phải xử lý.

Nếu một bucket chỉ có vài ánh xạ, một chuỗi node đơn giản có thể đáp ứng tốt. Nếu rất nhiều khóa dồn vào cùng bucket, việc phải kiểm tra nhiều ứng viên liên tiếp có thể làm tra cứu chậm.

Trong các cài đặt OpenJDK hiện đại, một bucket đông có thể được chuyển sang cấu trúc cây cân bằng, gọi là **cây hóa bucket (treeification)**. Cơ chế này giúp đối phó với một số trường hợp va chạm nhiều.

Cần giữ hai tầng kiến thức riêng:

| Tầng | Điều cần dựa vào |
| --- | --- |
| Hợp đồng công khai | Khóa duy nhất theo phép bằng, put/get/remove đúng ánh xạ, chính sách null và thứ tự |
| Chi tiết cài đặt | Bucket dạng danh sách hay cây, các ngưỡng chuyển đổi, bố trí node và thuật toán bên trong |

Bài này giải thích cơ chế cây hóa và cách quan sát nó, đồng thời chỉ ra những điều không được biến thành giả định của mã ứng dụng.

## 2. Va chạm không có nghĩa hai khóa bằng nhau

### 2.1. Cùng hash và cùng bucket là hai mức khác nhau

Trong mô hình OpenJDK 17u, một hash sau bước trộn được dùng với độ dài bảng n để chọn chỉ số:

```java
int index = (n - 1) & hash;
```

Đây là biểu thức giải thích cơ chế nội bộ, không phải API người gọi HashMap phải tự tính.

Với n bằng 64:

```text
63 & 1  = 1
63 & 65 = 1
```

Hai hash khác nhau vẫn cùng bucket. Nếu bảng tăng lên 128:

```text
127 & 1  = 1
127 & 65 = 65
```

chúng có thể tách sang hai bucket.

Ngược lại, nếu nhiều khóa trả cùng hashCode và có cùng hash sau trộn, tăng số bucket không tự làm các hash ấy khác nhau. Chúng vẫn cùng đường chọn chỉ số.

### 2.2. Equals vẫn quyết định cùng khóa logic

Hai khóa cùng hash nhưng equals false vẫn phải giữ các ánh xạ riêng. Put một khóa bằng khóa đã có cập nhật ánh xạ; put một khóa khác trong cùng bucket thêm ánh xạ khác.

Cây hóa không đổi quy tắc này. Nó đổi cách tổ chức ứng viên trong bucket, không đổi một HashMap thành cấu trúc loại trùng theo một tiêu chí mới.

Các đặc tính công khai của lớp có thể đối chiếu ở [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

## 3. Từ chuỗi node tới cây cân bằng

### 3.1. Bucket dạng danh sách

Một hình dung đơn giản:

```text
table[index]
     ↓
   node A → node B → node C → ... → node M
```

Nếu phải tìm một khóa ở gần cuối hoặc chứng minh khóa không có, cấu trúc có thể phải xét nhiều node trong nhóm. Với m ứng viên trong một bucket, một lượt tìm tuyến tính có thể tốn O(m).

Độ dài của một bucket khác với số ánh xạ toàn map. Map có thể có nhiều bucket gần rỗng nhưng một bucket rất đông do hàm băm phân bố kém.

### 3.2. Bucket dạng cây

OpenJDK dùng cây đỏ–đen cho các tree bin. Đây là một dạng cây tìm kiếm tự cân bằng, giữ chiều cao theo cấp logarit thay vì để chuỗi nhánh kéo dài tùy ý.

Hình khái niệm:

```text
table[index]
     ↓
   một node gốc
      /    \
   nhánh  nhánh
    / \    / \
   ...    ...
```

Hình này không mô tả một bố trí bắt buộc của các khóa cụ thể. Cài đặt còn giữ các liên kết phục vụ những thao tác khác như duyệt bucket; không phải bỏ toàn bộ liên kết node cũ rồi lộ ra một API cây mới cho người gọi.

Tree node có nhiều liên kết và thông tin cân bằng hơn node thông thường. Vì thế cây hóa có chi phí bộ nhớ và duy trì cấu trúc; không có lý do phải dùng cây cho mọi bucket chỉ có một, hai phần tử.

### 3.3. Đây là cải tiến cài đặt, không phải một kiểu Map mới

Các cải tiến trong Java 8 giới thiệu việc dùng cây cân bằng khi nhiều khóa va chạm. Tài liệu lịch sử cũng nhấn mạnh thứ tự duyệt HashMap vốn không được cam kết; xem [Collections Framework Enhancements in Java SE 8 của OpenJDK](https://cr.openjdk.org/~naoto/idna2008/docs_www/technotes/guides/collections/changes8.html).

Người gọi vẫn dùng HashMap với cùng thao tác put/get/remove. Không có yêu cầu đổi mã nghiệp vụ sang một lớp TreeBucket hoặc tự duy trì màu của node.

## 4. Ba hằng số 8, 6, 64 phải được đọc đúng ngữ cảnh

Trong mã nguồn OpenJDK 17u:

| Hằng số | Giá trị | Vai trò |
| --- | --- | --- |
| TREEIFY_THRESHOLD | 8 | Tham gia quyết định chuyển bucket đông sang cây khi thêm |
| UNTREEIFY_THRESHOLD | 6 | Ngưỡng chuyển nhóm đã tách về node thường trong đường resize |
| MIN_TREEIFY_CAPACITY | 64 | Độ dài bảng tối thiểu để cây hóa theo đường treeifyBin |

Đối chiếu [HashMap.java của OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java).

Những số này không phải các hằng public trong giao diện Map hoặc một cam kết số học của Java SE cho mọi phiên bản. Chúng là điểm bắt đầu để đọc một cài đặt cụ thể.

### 4.1. 64 là số bucket của bảng, không phải size bắt buộc

Một map có thể chỉ có chín ánh xạ nhưng bảng đã có 64 bucket do lựa chọn dung lượng ban đầu. Khi các ánh xạ cùng dồn vào một bucket, điều kiện độ dài bảng có thể đã đủ.

Ngược lại, không hiểu “phải có ít nhất 64 entry trong map thì mới được cây hóa”. Đây là nhầm capacity với size.

Khởi tạo HashMap với một dung lượng cũng không có nghĩa constructor lập tức công khai một mảng có thể truy cập. Việc cấp phát và làm tròn dung lượng là chi tiết cài đặt; ví dụ chỉ dùng tham số để tạo điều kiện cho thí nghiệm.

### 4.2. Bảng nhỏ có thể được tăng thay vì cây hóa

Trong đường treeifyBin của OpenJDK 17u, nếu độ dài bảng nhỏ hơn 64 thì cài đặt gọi resize thay vì lập cây cho bucket đó.

Lý do hợp lý về cơ chế là: nhiều hash khác nhau đang va chạm vì bảng còn nhỏ có thể tách được khi bảng có thêm bit chỉ số. Tăng bảng là một cách xử lý trước khi trả chi phí tree node.

Với những khóa có hash hoàn toàn giống nhau, resize không giải tán được nhóm ấy. Sau khi bảng đủ lớn và nhóm tiếp tục đông, cây hóa vẫn có thể diễn ra.

### 4.3. Không học “put phần tử thứ 8 luôn cây hóa”

TREEIFY_THRESHOLD bằng 8 không thay thế cho việc đọc nơi sử dụng nó.

Trong đường putVal thông thường của OpenJDK 17u, kiểm tra chuyển đổi nằm khi thêm một node mới vào một chuỗi đã có. Với bucket đang có tám node, lần put thêm khóa khác tiếp theo có thể kích hoạt đường treeify. Các đường cập nhật khác còn có cách đếm và thời điểm kiểm tra riêng.

Vì vậy cần nêu đủ: cài đặt nào, đường thao tác nào, số node trước hay sau thêm, độ dài bảng là bao nhiêu. Không dùng một câu thuộc lòng bỏ qua các điều kiện ấy.

## 5. Thí nghiệm quan sát Node và TreeNode

### 5.1. Cách quan sát và giới hạn

Chương trình sau dùng khóa có hashCode hằng để ép va chạm. Khóa triển khai Comparable theo id, nhất quán với phép bằng của record.

Nó lấy một Map.Entry qua API duyệt rồi in tên lớp chạy thực tế bằng getClass().getSimpleName(). Các tên Node/TreeNode là chi tiết cài đặt được quan sát, không phải kiểu public mà mã nghiệp vụ nên kiểm tra để quyết định xử lý.

Chương trình không truy cập trường private của HashMap, không cần reflection mở module hoặc cờ mở gói. Dù vậy, việc in được tên lớp không biến tên lớp ấy thành một hợp đồng ổn định.

Lưu thành **BucketTreeObservation.java**:

```java
import java.util.HashMap;
import java.util.Map;

public class BucketTreeObservation {
    record Key(int id) implements Comparable<Key> {
        @Override
        public int hashCode() {
            return 7;
        }

        @Override
        public int compareTo(Key other) {
            return Integer.compare(id, other.id);
        }
    }

    private static String observedEntryClass(Map<Key, Integer> map) {
        return map.entrySet().iterator().next().getClass().getSimpleName();
    }

    public static void main(String[] args) {
        Map<Key, Integer> largeStart = new HashMap<>(64);
        for (int id = 1; id <= 7; id++) {
            largeStart.put(new Key(id), id * 10);
        }
        System.out.println("observed start-64 after 7: " + observedEntryClass(largeStart));
        largeStart.put(new Key(8), 80);
        System.out.println("observed start-64 after 8: " + observedEntryClass(largeStart));
        largeStart.put(new Key(9), 90);
        System.out.println("observed start-64 after 9: " + observedEntryClass(largeStart));
        System.out.println("get equal key 5: " + largeStart.get(new Key(5)));
        System.out.println("replace equal key 5 old: " + largeStart.put(new Key(5), 500));
        System.out.println("size after replacement: " + largeStart.size());
        System.out.println("remove equal key 5: " + largeStart.remove(new Key(5)));
        System.out.println("key 6 preserved: " + largeStart.get(new Key(6)));

        Map<Key, Integer> smallStart = new HashMap<>(16);
        for (int id = 1; id <= 9; id++) {
            smallStart.put(new Key(id), id);
        }
        System.out.println("observed start-16 after 9: " + observedEntryClass(smallStart));
        smallStart.put(new Key(10), 10);
        System.out.println("observed start-16 after 10: " + observedEntryClass(smallStart));
        smallStart.put(new Key(11), 11);
        System.out.println("observed start-16 after 11: " + observedEntryClass(smallStart));
        System.out.println("small-start size: " + smallStart.size());
        System.out.println("small-start get 11: " + smallStart.get(new Key(11)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BucketTreeObservation.java
java BucketTreeObservation
```

Các chương trình trong bài được biên dịch với --release 17 và chạy trên OpenJDK 24.0.2. Stdout quan sát được:

```text
observed start-64 after 7: Node
observed start-64 after 8: Node
observed start-64 after 9: TreeNode
get equal key 5: 50
replace equal key 5 old: 50
size after replacement: 9
remove equal key 5: 500
key 6 preserved: 60
observed start-16 after 9: Node
observed start-16 after 10: Node
observed start-16 after 11: TreeNode
small-start size: 11
small-start get 11: 11
```

**Các dòng observed ghi nhận cài đặt của môi trường đã nêu, không phải thứ tự chuyển lớp mà mọi Java 17+ phải bảo đảm.** Cờ --release 17 kiểm tra ngôn ngữ/API mục tiêu và sinh bytecode tương ứng; JVM chạy chương trình vẫn là bản 24.0.2.

### 5.2. Đọc kết quả theo đường thao tác

Với điểm bắt đầu dung lượng 64, trong thí nghiệm put:

- Sau bảy và tám khóa va chạm, entry quan sát vẫn là Node.
- Sau khóa thứ chín, entry quan sát là TreeNode.
- Get, cập nhật bằng khóa tương đương và remove vẫn giữ đúng ý nghĩa Map.

Với điểm bắt đầu nhỏ hơn, sau chín và mười khóa vẫn quan sát Node; sau mười một mới quan sát TreeNode. Kết quả phù hợp với việc đường xử lý bảng nhỏ ưu tiên tăng bảng trước khi tạo cây.

Chỉ từ một tên lớp được in không thể kết luận mọi thông số capacity bên trong. Phần giải thích đường resize cần đối chiếu mã nguồn của cài đặt; chương trình không cung cấp API kiểm tra capacity.

Không dùng những dòng observed làm kiểm thử khả năng tương thích cho sản phẩm. Các kết quả nghiệp vụ như size, get và remove mới thuộc phần hợp đồng cần giữ khi cấu trúc bên trong thay đổi.

## 6. Cây hóa không làm HashMap thành TreeMap

Một tree bin là một nhóm trong một bảng băm. Nó không tạo thứ tự tăng dần cho toàn bộ map.

| Câu hỏi | HashMap có tree bin |
| --- | --- |
| Iterator có phải đi theo thứ tự khóa tăng dần không? | Không có bảo đảm đó |
| Có public API floorKey/ceilingKey vì đã có cây không? | Không |
| Có thể truyền Comparator qua constructor HashMap để điều khiển cây không? | Không |
| CompareTo bằng 0 có tự loại khóa khác equals không? | Không đổi hợp đồng nhận diện của HashMap |
| Put/get/remove theo khóa tương đương có còn đúng không? | Vẫn phải đúng khi khóa tuân hợp đồng |

Trong tìm kiếm tree bin, hash vẫn là thông tin quan trọng để chọn hướng. Khi hash bằng nhau, cài đặt có thể dùng một dạng Comparable phù hợp của khóa để hỗ trợ phân biệt nhánh.

Không cần người gọi tự chọn một comparator nội bộ cho HashMap. Cũng không biến compareTo thành phép thay thế equals cho việc cùng khóa logic.

Nếu cần truy vấn thứ tự khóa hoặc khoảng khóa như một tính năng ứng dụng, hãy chọn một Map có hợp đồng công khai đáp ứng yêu cầu đó. Việc một bucket vô tình chuyển thành cây không bổ sung những tính năng ấy.

## 7. Giới hạn của phát biểu “cây thì tìm luôn O(log n)”

### 7.1. Chiều cao cây và tổng công việc tìm không phải cùng một thứ

Cây cân bằng giới hạn chiều cao. Nếu mỗi bước tìm xác định được nhánh phù hợp, tìm trong m node có thể theo một đường dài O(log m).

Nhưng trong tree bin, nhiều khóa có thể cùng hash và không có quan hệ Comparable hữu ích để phân biệt. Mã nguồn tìm cây của OpenJDK có đường phải tìm thêm ở nhánh khác khi không chọn được hướng đủ thông tin.

Vì thế không phát biểu vô điều kiện: “từ Java 8 mọi get của HashMap trong trường hợp xấu đều O(log n), bất kể kiểu khóa và hàm hash”.

Đặc biệt, cùng hash và không so sánh được có thể khiến việc tìm một khóa không có phải khảo sát nhiều node. Cây đỏ–đen vẫn cân bằng nhưng tổng số node được xem không nhất thiết chỉ là một đường từ gốc xuống lá.

### 7.2. Comparable hỗ trợ cấu trúc, không sửa khóa sai

Nếu khóa có một thứ tự tự nhiên phù hợp, cài đặt có thể dùng nó để xử lý các trường hợp hash trùng. Chương trình thí nghiệm dùng Comparable<Key> theo id để có một mô hình nhất quán và dễ đọc.

Một equals/hashCode vi phạm hợp đồng, hoặc một khóa bị sửa thông tin định danh sau khi put, vẫn có thể làm tra cứu không còn như mong đợi. Treeification không tự sửa vấn đề đó.

### 7.3. Hàm băm tốt vẫn quan trọng

Mã băm phân bố phù hợp giúp tránh việc rất nhiều khóa dồn vào một bucket. Cây hóa là một cơ chế giảm tác động trong những điều kiện nhất định, không phải lý do chủ đích trả cùng hashCode cho mọi khóa của ứng dụng.

Một lần hashCode/equals/compareTo tốn công cũng làm chi phí thực tăng lên. Khi phân tích O(1) trung bình hoặc O(log m), phải hiểu giả định về chi phí các phép so sánh.

Tài liệu HashMap chỉ mô tả hiệu năng hằng số cho các thao tác cơ bản dưới điều kiện hàm băm phân bố thích hợp. Không bỏ điều kiện ấy khi diễn giải.

## 8. Khi nào một bucket trở về dạng thường?

### 8.1. Resize có thể chia một nhóm thành hai nhóm nhỏ

Với bảng tăng từ 64 lên 128, các hash khác nhau đang cùng chỉ số cũ có thể rẽ sang hai chỉ số mới. Trong mô hình hash 1 và 65:

```text
Trước: bucket 1 của bảng 64
       ├─ bốn khóa có hash 1
       └─ năm khóa có hash 65

Sau:   bucket 1  của bảng 128: bốn khóa hash 1
       bucket 65 của bảng 128: năm khóa hash 65
```

Trong đường split tree bin của OpenJDK 17u, các nhóm nhỏ có số node không vượt UNTREEIFY_THRESHOLD có thể được đổi về node thường.

Đây là một lý do hợp lý để dùng ngưỡng vào và ra khác nhau: không phải mọi biến động nhỏ đều cần trả chi phí đổi cấu trúc qua lại.

### 8.2. Không áp “xóa còn 6 thì luôn thành danh sách” cho mọi đường xóa

Hằng UNTREEIFY_THRESHOLD bằng 6 được dùng trong đường tách khi resize. Đường removeTreeNode còn có kiểm tra dựa trên hình dạng cây và cách thao tác.

Không biến ba con số 8/6/64 thành một máy trạng thái đơn giản chỉ nhìn size. Phải xem chúng được dùng ở hàm nào.

Một cài đặt có thể chuyển dạng vì resize, vì nhóm trở nên nhỏ sau xóa, hoặc giữ dạng trong những trường hợp khác. Đây không phải chính sách ứng dụng nên điều khiển bằng số entry cố định.

### 8.3. Chuyển dạng không được làm mất ánh xạ hợp lệ

Dù node được đổi biểu diễn, những khóa và giá trị còn tồn tại phải giữ được ý nghĩa tra cứu. Kiểm thử tính đúng nên kiểm tra ánh xạ được bảo toàn, thay vì bắt một dạng node cụ thể.

## 9. Thí nghiệm tách tree bin khi bảng tăng

Lưu thành **BucketSplitObservation.java**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class BucketSplitObservation {
    record Key(int id, int rawHash) implements Comparable<Key> {
        @Override
        public int hashCode() {
            return rawHash;
        }

        @Override
        public int compareTo(Key other) {
            int byHash = Integer.compare(rawHash, other.rawHash);
            return byHash != 0 ? byHash : Integer.compare(id, other.id);
        }
    }

    private static String observedEntryClass(Map<Key, Integer> map, Key key) {
        for (Map.Entry<Key, Integer> entry : map.entrySet()) {
            if (entry.getKey().equals(key)) {
                return entry.getClass().getSimpleName();
            }
        }
        return "missing";
    }

    public static void main(String[] args) {
        Map<Key, Integer> map = new HashMap<>(64);
        List<Key> original = new ArrayList<>();
        for (int id = 0; id < 9; id++) {
            Key key = new Key(id, id < 4 ? 1 : 65);
            original.add(key);
            map.put(key, id);
        }

        Key low = new Key(2, 1);
        Key high = new Key(7, 65);
        System.out.println("before growth size: " + map.size());
        System.out.println("observed low entry before: " + observedEntryClass(map, low));
        System.out.println("observed high entry before: " + observedEntryClass(map, high));

        for (int rawHash = 2; rawHash <= 41; rawHash++) {
            map.put(new Key(100 + rawHash, rawHash), 100 + rawHash);
        }

        System.out.println("after growth size: " + map.size());
        System.out.println("observed low entry after: " + observedEntryClass(map, low));
        System.out.println("observed high entry after: " + observedEntryClass(map, high));

        boolean preserved = true;
        for (Key key : original) {
            preserved &= Integer.valueOf(key.id()).equals(map.get(new Key(key.id(), key.rawHash())));
        }
        System.out.println("original mappings preserved: " + preserved);
        System.out.println("get low key: " + map.get(low));
        System.out.println("get high key: " + map.get(high));
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 BucketSplitObservation.java
java BucketSplitObservation
```

Stdout quan sát trên cùng môi trường:

```text
before growth size: 9
observed low entry before: TreeNode
observed high entry before: TreeNode
after growth size: 49
observed low entry after: Node
observed high entry after: Node
original mappings preserved: true
get low key: 2
get high key: 7
```

Chín khóa đầu gồm bốn khóa trả hash 1 và năm khóa trả hash 65. Với các giá trị nhỏ này, bước trộn của cài đặt được đối chiếu không đổi hai hash đó; khi bảng có 64 bucket, cả hai nhóm cùng vào chỉ số 1.

Các khóa thêm sau dùng hash từ 2 đến 41, không dồn vào bucket ban đầu ấy trong mô hình đang xét. Chúng làm tổng số entry tăng từ 9 lên 49. Với cài đặt và cấu hình thí nghiệm này, đường tăng bảng dẫn tới việc tách nhóm; các entry gốc được quan sát chuyển từ TreeNode thành Node.

Lần nữa, tên lớp và thời điểm chuyển là kết quả quan sát, không phải API kiểm tra cấu trúc. Phần original mappings preserved cùng các lệnh get chứng minh điều quan trọng đối với mã gọi: dữ liệu gốc vẫn được tìm thấy bằng khóa tương đương.

Chương trình duyệt entrySet để tìm entry cần quan sát. Nó không dựa vào thứ tự duyệt HashMap, vì thứ tự ấy không được cam kết.

## 10. Những thứ không nên đưa vào hợp đồng của ứng dụng

### 10.1. Không rẽ nhánh nghiệp vụ theo tên lớp node

Các tên `HashMap$Node` hoặc `HashMap$TreeNode`, việc một entry có thêm trường màu hay liên kết nào, và cấu trúc gốc của cây là nội bộ.

Mã như “nếu entry là TreeNode thì chọn cách xác thực khác” biến một tối ưu bộ nhớ thành điều kiện nghiệp vụ. Nó có thể hỏng khi nâng JDK dù các thao tác Map công khai vẫn hoạt động đúng.

Không cần đọc trường private của HashMap hoặc mở các gói nội bộ để sử dụng Map đúng.

### 10.2. Không dựa vào thứ tự iterator

HashMap không bảo đảm thứ tự duyệt. Resize hoặc đổi cấu trúc có thể làm thứ tự quan sát khác đi; một thứ tự có vẻ ổn trên dữ liệu nhỏ không trở thành cam kết.

Nếu đầu ra cần một thứ tự, phải biểu đạt yêu cầu đó bằng cấu trúc hoặc bước xử lý có hợp đồng thứ tự rõ ràng.

### 10.3. Không dùng threshold để đoán hiệu năng mà không xét dữ liệu

Biết ngưỡng 8 không cho biết một chương trình sẽ nhanh hay chậm ở entry thứ chín. Còn có phân bố hash, số bucket, equals/compareTo, kiểu đường thao tác, cấp phát và nhiều yếu tố khác.

Không suy ra thời gian chạy từ một lần đo rất ngắn hoặc từ việc lớp entry đã đổi tên. Khi hiệu năng là yêu cầu thật, dùng phép đo phù hợp với dữ liệu và môi trường đại diện.

### 10.4. Không xem cây hóa là cơ chế đồng bộ

HashMap không tự an toàn cho việc nhiều luồng cùng sửa chỉ vì một bucket đã thành cây. Cấu trúc đồng thời và cơ chế đồng bộ là một yêu cầu độc lập.

Cũng không dùng ConcurrentModificationException như một bằng chứng rằng mọi truy cập sai đều được phát hiện. Đây là cơ chế hỗ trợ phát hiện lỗi theo khả năng, không phải bảo đảm đồng bộ.

## 11. Cách đọc nguồn cài đặt mà vẫn giữ mô hình đúng

Một trình tự đọc hữu ích:

1. Đọc hợp đồng công khai của HashMap và Map.
2. Xem hash/index để biết nhiều khóa có thể cùng vùng như thế nào.
3. Xem putVal và treeifyBin để biết lúc nào có đề nghị chuyển dạng.
4. Xem TreeNode.find để hiểu điều kiện chọn nhánh.
5. Xem split và removeTreeNode để hiểu đường quay về dạng thường.
6. Kiểm tra dữ liệu bằng public API; dùng chẩn đoán nội bộ chỉ để học cơ chế.

Hãy ghi rõ phiên bản nguồn khi giải thích. “Nguồn OpenJDK 17u có hằng này” chính xác hơn “Java luôn làm như vậy”.

Bản nguồn trên nhánh cập nhật cũng có thể thay đổi theo thời gian. Khi cần tái hiện một điều tra hiệu năng, ghi lại bản JDK, bản nguồn hoặc commit liên quan thay vì chỉ tên một ngôn ngữ.

Đừng chép nguyên một đoạn điều kiện ra rồi bỏ ngữ cảnh: một threshold có thể là đếm node trước thêm; một đường khác có thể dùng biến đếm khác; một điều kiện capacity có thể chuyển thao tác sang resize.

## 12. Kiểm thử nên bảo vệ kết quả nào?

Các thuộc tính bền vững để kiểm tra:

- Nhiều khóa khác nhau cùng hash vẫn giữ đủ entry.
- Put bằng khóa tương đương thay đúng giá trị, không tăng số khóa logic.
- Get và remove bằng bản khóa tương đương vẫn đúng trước và sau nhiều lần thêm.
- Khóa ở các bucket khác không bị ảnh hưởng bởi xóa trong một nhóm va chạm.
- Null và giá trị trả về được xử lý theo đúng lớp map.
- Mã gọi không giả định thứ tự iterator của HashMap.

Các kiểm thử khóa đúng này vẫn có giá trị nếu cài đặt thay ngưỡng hoặc thay cách tổ chức bucket.

Ngược lại, kiểm thử đòi “entry thứ chín phải mang class tên TreeNode” thuộc về một thí nghiệm cài đặt có môi trường được cố định. Không dùng nó làm yêu cầu của một thư viện chỉ cam kết sử dụng Map API.

Có thể giữ cả hai loại kiểm tra trong một hoạt động học, nhưng phải đặt mục tiêu rõ: một loại xác nhận hợp đồng dữ liệu; một loại ghi nhận cơ chế của môi trường cụ thể.

## 13. Lỗi phổ biến và cách sửa

| Lỗi suy luận | Điều bị bỏ qua | Cách hiểu phù hợp |
| --- | --- | --- |
| Cùng hash nên khóa sau ghi đè khóa trước | Equals vẫn nhận diện khóa | Va chạm hợp lệ không nhập khóa khác nhau |
| Cứ tám entry là thành cây | Đường đếm, capacity và thao tác | Đọc điều kiện tại nơi dùng threshold |
| Phải có 64 entry mới cây hóa | 64 là độ dài bảng | Phân biệt size với capacity |
| Bảng nhỏ gặp nhiều va chạm luôn lập cây | Có đường resize trước | Xem MIN_TREEIFY_CAPACITY |
| Có tree bin nên HashMap đã sắp xếp | Cây chỉ là cấu trúc một bucket | Không có hợp đồng thứ tự toàn map |
| Cây cân bằng nên mọi lookup chắc O(log n) | Có nhánh tìm không phân biệt được bằng thứ tự | Xét hash và Comparable phù hợp |
| Xóa còn sáu luôn đổi về danh sách | Đường remove khác split | Không dùng một ngưỡng thay toàn cơ chế |
| Treeification sửa được khóa bị mutate | Hợp đồng khóa vẫn bị phá | Giữ định danh khóa ổn định |
| Tên Node là API công khai | Đó là tên lớp chạy thực tế | Chỉ dùng cho quan sát, không cho nghiệp vụ |
| Cây hóa làm HashMap an toàn nhiều luồng | Không có bảo đảm đồng bộ mới | Chọn cấu trúc/đồng bộ phù hợp riêng |

## 14. Bài tập tự kiểm tra có lời giải

### Bài 1: Hai mức va chạm

Hash đã trộn 1 và 65 có cùng bucket khi bảng dài 64 không? Khi bảng dài 128 thì sao?

**Lời giải:** ở 64, cả hai vào bucket 1. Ở 128, chúng vào 1 và 65. Va chạm do mask của bảng nhỏ có thể được tách khi tăng bảng.

### Bài 2: Hash hoàn toàn giống nhau

Hai mươi khóa khác nhau đều có cùng hashCode hợp lệ. Tăng bảng có bảo đảm chia chúng vào nhiều bucket không?

**Lời giải:** không. Hash sau trộn giống nhau vẫn cho cùng chỉ số với cùng mask. Resize không tự tạo sự khác nhau giữa các hash bằng nhau.

### Bài 3: Ý nghĩa 64

Map có chín entry nhưng đã có bảng đủ lớn. Có mâu thuẫn nếu bucket của nó được cây hóa không?

**Lời giải:** không. Điều kiện 64 nói về độ dài bảng của đường cài đặt được đối chiếu, không phải map phải có 64 entry.

### Bài 4: Ngưỡng 8

Một quan sát put thấy sau tám khóa còn Node, sau chín khóa là TreeNode. Điều đó có tự mâu thuẫn với TREEIFY_THRESHOLD bằng 8 không?

**Lời giải:** không. Phải xem ngưỡng được kiểm tra khi thêm vào chuỗi đã có bao nhiêu node và biến đếm được dùng thế nào. Một con số riêng chưa mô tả đủ thời điểm chuyển.

### Bài 5: Thứ tự

Một bucket là cây đỏ–đen. Có được dùng vòng for trên HashMap để lấy các khóa tăng dần không?

**Lời giải:** không. Tree bin không tạo hợp đồng duyệt khóa có thứ tự cho toàn map.

### Bài 6: Tìm khóa thiếu

Một nhóm có nhiều khóa cùng hash và không có thứ tự Comparable hữu ích. Cây cân bằng có bảo đảm việc tìm khóa thiếu chỉ xem một đường O(log m) không?

**Lời giải:** không thể khẳng định như vậy. Đường tìm của cài đặt có thể cần tìm thêm nhánh khi không phân biệt được hướng. Chiều cao cân bằng không đồng nghĩa mọi lượt tìm đều chỉ đi một nhánh.

### Bài 7: Tách nhóm

Một tree bin tách thành nhóm bốn node và nhóm năm node trong resize của OpenJDK 17u. Chúng có thể trở về node thường không?

**Lời giải:** có, theo đường split với UNTREEIFY_THRESHOLD. Điều này không tạo quy tắc rằng mọi phép xóa đến sáu node trong mọi hoàn cảnh đều phải đổi dạng.

### Bài 8: Kiểm thử nâng JDK

Một bản JDK khác không in tên entry như thí nghiệm nhưng put/get/remove với khóa đúng vẫn giữ dữ liệu. Có đủ để kết luận JDK vi phạm Map không?

**Lời giải:** không. Tên lớp entry và thời điểm cây hóa không thuộc cam kết của Map. Phải đánh giá các thuộc tính công khai mà ứng dụng được phép dựa vào.

## 15. Tài liệu đối chiếu

- [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): hợp đồng lớp, hiệu năng có điều kiện và thứ tự không được bảo đảm.
- [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): ý nghĩa ánh xạ và giới hạn với khóa thay đổi được.
- [HashMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java): treeifyBin, TreeNode.find, split, removeTreeNode và các hằng số.
- [Collections Framework Enhancements in Java SE 8 của OpenJDK](https://cr.openjdk.org/~naoto/idna2008/docs_www/technotes/guides/collections/changes8.html): bối cảnh cải tiến bucket va chạm.

Cây hóa là một cách tổ chức lại bucket để cải thiện xử lý va chạm trong cài đặt cụ thể. Hiểu nó giúp giải thích và chẩn đoán, còn mã sử dụng HashMap nên tiếp tục dựa vào hợp đồng ánh xạ, quy tắc khóa đúng và yêu cầu thứ tự/đồng thời được biểu đạt rõ ràng.
