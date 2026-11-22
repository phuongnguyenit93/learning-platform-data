# Kết hợp bảng băm với thứ tự duyệt có xác định

## 1. Vì sao cần LinkedHashMap?

Một màn hình cấu hình có các trường được thêm theo thứ tự: tên hiển thị, email, ngôn ngữ. Chương trình cần hai khả năng:

- Tìm nhanh giá trị theo tên trường.
- Khi xuất danh sách, giữ đúng thứ tự đã đưa các trường vào.

HashMap giải quyết tốt việc ánh xạ khóa tới giá trị, nhưng không bảo đảm thứ tự duyệt. Một List giữ được thứ tự, nhưng nếu chỉ dùng danh sách các cặp thì tìm một khóa thường phải kiểm tra nhiều cặp.

LinkedHashMap kết hợp hai ý tưởng: **dùng bảng băm để định vị ánh xạ theo khóa và dùng một chuỗi liên kết để xác định thứ tự duyệt các ánh xạ**.

Vì vậy, tên LinkedHashMap không có nghĩa mỗi lần get đều phải đi hết một LinkedList. Hai cấu trúc phục vụ hai công việc khác nhau.

Bài học tập trung vào cơ chế kết hợp ấy, thứ tự chèn mặc định và những hệ quả khi đọc, cập nhật, sao chép hoặc kiểm thử map. Chế độ thứ tự truy cập được giới thiệu để tránh hiểu rằng mọi LinkedHashMap luôn giữ nguyên vị trí sau get.

## 2. Hai câu hỏi độc lập: tìm ở đâu và duyệt theo đường nào?

### 2.1. Bảng băm trả lời câu hỏi tìm kiếm

Khi gọi get(key), cơ chế băm dùng hash của khóa để định hướng tới bucket có thể chứa ánh xạ, sau đó kiểm tra khóa phù hợp bằng quy tắc bằng của map.

Điều kiện cần giữ vẫn là hợp đồng equals/hashCode. Hai khóa bằng nhau phải có cùng hash; nhiều khóa khác nhau có thể va chạm mà vẫn là những ánh xạ riêng.

Việc có thêm thứ tự không làm LinkedHashMap bỏ mô hình khóa duy nhất của Map.

### 2.2. Chuỗi liên kết trả lời câu hỏi duyệt

Ngoài thông tin phục vụ bảng băm, các entry còn được nối với nhau theo một thứ tự của toàn map.

Hình khái niệm với ba entry:

```text
Bảng băm: hash(key) → bucket phù hợp → entry cần tìm

Thứ tự duyệt:
đầu → [zeta=3] ⇄ [alpha=1] ⇄ [beta=2] → cuối
```

Một entry được tham gia cả cơ chế định vị theo hash lẫn cơ chế thứ tự. Không cần duy trì thủ công một HashMap và một List chứa dữ liệu trùng nhau trong mã ứng dụng.

Trong mã nguồn OpenJDK 17u, entry thông thường có hai liên kết before/after; map có đầu và cuối của chuỗi. Iterator đi theo liên kết thứ tự, thay vì lấy thứ tự bucket làm thứ tự kết quả. Có thể đối chiếu [LinkedHashMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/LinkedHashMap.java).

Tên trường và cách tổ chức lớp nội bộ là chi tiết cài đặt. Điều người dùng được dựa vào là hợp đồng thứ tự duyệt của LinkedHashMap.

### 2.3. Không nhầm hai loại liên kết

Một bucket có nhiều khóa va chạm cũng có thể cần liên kết hoặc cấu trúc nội bộ để giữ các ứng viên trong bucket đó.

Chuỗi before/after của LinkedHashMap có vai trò khác: nó nối **tất cả entry của map theo thứ tự duyệt**, kể cả những entry nằm ở các bucket khác nhau.

Vì thế không suy ra “các khóa gần nhau khi duyệt thì có cùng bucket” hoặc “các khóa cùng hash sẽ đứng liền nhau trong kết quả”.

## 3. Mặc định là thứ tự chèn, không phải thứ tự khóa

Các constructor thông thường như new LinkedHashMap<>() tạo map theo **thứ tự chèn (insertion order)**.

Nếu lần lượt thêm zeta, alpha, beta thì thứ tự duyệt là:

```text
zeta → alpha → beta
```

Nó không tự đổi thành alpha, beta, zeta chỉ vì tên khóa có thứ tự chữ cái như vậy.

### 3.1. Khóa mới được thêm vào cuối

Một khóa chưa có trong map tạo thêm một ánh xạ. Trong chế độ chèn mặc định, ánh xạ ấy đứng sau những ánh xạ còn tồn tại trước đó.

Thứ tự ở đây được tạo bởi lịch sử thao tác lên map, không phải một thuộc tính sắp xếp sẵn của dữ liệu.

### 3.2. Ghi lại khóa đang có giữ vị trí

Với thứ tự zeta, alpha, beta, gọi put("alpha", 10) thay giá trị của alpha nhưng không đẩy alpha xuống cuối trong chế độ chèn.

Điều này có ích khi muốn giữ lần xuất hiện đầu tiên của một khóa, đồng thời cập nhật nội dung mới nhất cho khóa ấy.

Không cần cùng một đối tượng khóa theo phép ==. Một đối tượng khóa khác nhưng bằng khóa đã có vẫn là cập nhật ánh xạ của khóa logic ấy, nếu các khóa tuân hợp đồng.

### 3.3. Xóa rồi thêm lại là một lần chèn mới

Nếu remove("zeta") rồi put("zeta", 30), giữa hai thao tác ấy map không còn zeta. Lần put sau thêm một ánh xạ mới vào cuối.

Thứ tự chuyển từ:

```text
zeta → alpha → beta
       xóa zeta
alpha → beta
       thêm zeta
alpha → beta → zeta
```

Đây là khác biệt giữa “cập nhật giá trị của một khóa còn tồn tại” và “xóa ánh xạ rồi tạo lại”.

### 3.4. Đọc trong chế độ chèn không đổi thứ tự

Get, containsKey và việc duyệt các view không được hiểu là một lần chèn lại. Với cấu hình mặc định, đọc alpha không làm alpha rời vị trí cũ.

Phải biết chế độ thứ tự trước khi kết luận về tác dụng của một thao tác đọc; phần sau sẽ đối chiếu chế độ truy cập.

## 4. Ví dụ Java 17: quan sát thứ tự qua các thao tác

Lưu thành **LinkedOrderDemo.java**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.StringJoiner;

public class LinkedOrderDemo {
    static String entries(Map<String, Integer> map) {
        StringJoiner result = new StringJoiner("; ");
        for (Map.Entry<String, Integer> entry : map.entrySet()) {
            result.add(entry.getKey() + "=" + entry.getValue());
        }
        return result.toString();
    }

    public static void main(String[] args) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("zeta", 3);
        scores.put("alpha", 1);
        scores.put("beta", 2);
        System.out.println("initial keys: " + new ArrayList<>(scores.keySet()));
        System.out.println("get alpha: " + scores.get("alpha"));
        System.out.println("after get: " + new ArrayList<>(scores.keySet()));

        System.out.println("old alpha value: " + scores.put("alpha", 10));
        System.out.println("after update: " + new ArrayList<>(scores.keySet()));
        System.out.println("size after update: " + scores.size());

        scores.remove("zeta");
        scores.put("zeta", 30);
        scores.put("beta", 10);
        System.out.println("after remove and insert: " + new ArrayList<>(scores.keySet()));
        System.out.println("values: " + new ArrayList<>(scores.values()));
        System.out.println("entries: " + entries(scores));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LinkedOrderDemo.java
java LinkedOrderDemo
```

Stdout:

```text
initial keys: [zeta, alpha, beta]
get alpha: 1
after get: [zeta, alpha, beta]
old alpha value: 1
after update: [zeta, alpha, beta]
size after update: 3
after remove and insert: [alpha, beta, zeta]
values: [10, 10, 30]
entries: alpha=10; beta=10; zeta=30
```

Các chương trình trong bài đã được biên dịch với --release 17 và chạy trên OpenJDK 24.0.2. Cờ này chọn mức ngôn ngữ/API đích và bytecode; JVM chạy chương trình vẫn là phiên bản 24.0.2.

### 4.1. Giải thích kết quả

Ba khóa ban đầu là zeta, alpha, beta nên keySet đi theo thứ tự ấy.

Get alpha trả 1 nhưng không đổi thứ tự. Put alpha bằng 10 trả về giá trị cũ 1; số khóa vẫn là ba và alpha vẫn ở vị trí thứ hai.

Sau khi xóa zeta rồi thêm lại, zeta đứng cuối. Tiếp theo cập nhật beta thành 10 không đổi vị trí beta.

Dòng values là [10, 10, 30]. Nó có hai giá trị 10 vì Map chỉ đòi khóa duy nhất; giá trị có thể trùng. Dòng entries thể hiện chính xác cặp khóa–giá trị ở từng vị trí duyệt.

### 4.2. Vì sao vẫn khai báo biến bằng Map?

Biến scores có kiểu Map<String, Integer>, còn đối tượng thực tế được tạo là LinkedHashMap. Việc dùng giao diện Map không làm mất hành vi của đối tượng thực tế.

Tuy nhiên một phương thức nhận Map bất kỳ không được tự giả định mọi đối số đều có thứ tự chèn. Nếu thứ tự là yêu cầu của giao tiếp, phải mô tả yêu cầu ấy rõ ràng và dùng cấu trúc hoặc bản sao phù hợp tại ranh giới.

Các new ArrayList<>(...) trong ví dụ tạo danh sách để in và so sánh thứ tự ở thời điểm đó. Chúng không thay đổi thứ tự bên trong map.

## 5. Một thứ tự được chia sẻ qua keySet, values và entrySet

LinkedHashMap có ba góc nhìn quen thuộc:

| View | Dữ liệu khi duyệt | Quan hệ với cùng một thứ tự entry |
| --- | --- | --- |
| keySet() | Khóa | Khóa của entry thứ nhất, thứ hai, ... |
| values() | Giá trị | Giá trị của entry thứ nhất, thứ hai, ... |
| entrySet() | Cặp khóa–giá trị | Chính các entry theo thứ tự đó |

Nếu map không bị thay đổi giữa các lượt duyệt, ba góc nhìn tương ứng cùng một chuỗi entry. Không có việc keySet giữ thứ tự chèn còn values tự sắp xếp theo giá trị.

### 5.1. View không phải bản sao

Giữ một biến trỏ tới keySet rồi thêm khóa vào map sẽ làm view phản ánh map đã đổi. Ngược lại, thao tác xóa được hỗ trợ qua view có tác dụng lên map.

Nếu cần giữ danh sách khóa tại một thời điểm, có thể tạo new ArrayList<>(map.keySet()). Đây là bản chụp của dãy tham chiếu khóa ở thời điểm sao chép, không phải bản sao sâu của các đối tượng khóa.

### 5.2. Muốn dùng cả khóa và giá trị, duyệt entrySet

Trong ví dụ, entries duyệt Map.Entry để lấy cả hai thành phần của cùng ánh xạ. Cách này thể hiện trực tiếp công việc đang làm.

Đặc biệt, không cần lấy từng khóa rồi gọi get lần nữa chỉ để tìm giá trị đã nằm trong entry. Trong chế độ thứ tự truy cập, một lệnh get còn có thể tác động tới thứ tự, nên lựa chọn vòng lặp cần có chủ đích.

### 5.3. Xóa khi đang duyệt

Nếu cần xóa ngay trong một lượt iterator, dùng remove của chính iterator sau next khi thao tác đó được phép. Iterator của LinkedHashMap duy trì tính nhất quán của việc duyệt và xóa ánh xạ.

Không vừa duyệt bằng enhanced for vừa gọi map.remove tùy ý rồi dựa vào việc một lần chạy chưa báo lỗi. Thay đổi cấu trúc ngoài đường được phép có thể khiến iterator không còn hợp lệ.

Cơ chế fail-fast hỗ trợ phát hiện lỗi theo khả năng; không phải giao thức đồng bộ hay bằng chứng mọi truy cập sai chắc chắn sẽ bị phát hiện.

## 6. Thứ tự chèn, thứ tự truy cập và thứ tự sắp xếp

“Có thứ tự” là một mô tả chưa đủ. Cần biết **thứ tự được tạo theo quy tắc nào**.

| Cấu trúc hoặc cấu hình | Quy tắc thứ tự chủ yếu |
| --- | --- |
| HashMap | Không có cam kết thứ tự duyệt |
| LinkedHashMap mặc định | Thứ tự chèn của các khóa còn tồn tại |
| LinkedHashMap với accessOrder = true | Thứ tự truy cập, từ ít được truy cập gần đây nhất tới gần đây nhất |
| TreeMap | Thứ tự khóa theo thứ tự tự nhiên hoặc Comparator phù hợp |

### 6.1. LinkedHashMap không cần so sánh các khóa để giữ thứ tự chèn

Khóa không phải triển khai Comparable chỉ để dùng LinkedHashMap. Ta cũng không truyền Comparator vào constructor của lớp này để yêu cầu sắp xếp.

Nếu cần dãy khóa đã sắp xếp hoặc truy vấn theo khoảng, phải chọn một hợp đồng đáp ứng yêu cầu đó. Thứ tự chèn không tự cung cấp các phép truy vấn như floorKey.

Đối chiếu [TreeMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) khi yêu cầu là thứ tự so sánh khóa.

### 6.2. Chế độ truy cập thay đổi ý nghĩa của lịch sử

Constructor ba tham số có thể bật accessOrder:

```java
Map<String, Integer> byAccess = new LinkedHashMap<>(16, 0.75f, true);
```

Đây là đoạn khai báo minh họa trong ngữ cảnh đã import Map và LinkedHashMap. Số 16 là tham số dung lượng, 0,75 là load factor và true chọn chế độ truy cập.

Nếu đang có a, b, c, truy cập thành công a bằng get có thể đưa a về cuối, tạo b, c, a. Cuối chuỗi khi ấy là entry được truy cập gần đây nhất, không còn đơn giản là khóa được chèn gần đây nhất.

Tài liệu lớp định nghĩa những thao tác nào được tính là truy cập. Ví dụ get và put có vai trò này đối với entry liên quan trong điều kiện tương ứng; containsKey không được tính là truy cập làm đổi thứ tự.

Không suy ra mọi lời gọi phương thức lên map đều làm một entry thành mới nhất. Duyệt view cũng không được tính là truy cập entry theo quy tắc này.

### 6.3. Chế độ truy cập không tự tạo một cache đầy đủ

Cấu hình accessOrder chỉ chọn cách duy trì thứ tự. Nó không tự đặt giới hạn số entry, thời gian hết hạn hoặc chính sách loại bỏ dữ liệu.

Đây là nền tảng hữu ích cho một số cách tổ chức dữ liệu theo mức dùng gần đây. Muốn có hành vi cache hoàn chỉnh còn cần chính sách riêng.

Trong bài này, cần nhận biết chế độ để hiểu đúng hợp đồng duyệt; không phải tự triển khai một hệ thống cache.

## 7. Có cùng ánh xạ chưa chắc có cùng thứ tự

Hai LinkedHashMap có thể chứa cùng những cặp khóa–giá trị nhưng đã được chèn theo trình tự khác nhau.

Map.equals kiểm tra **cùng các ánh xạ**, không kiểm tra dãy thứ tự chèn. Đó là hợp đồng chung được nêu trong [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#equals(java.lang.Object)).

Ví dụ:

```text
Map trái:  b=2, a=1, c=3
Map phải:  c=3, a=1, b=2

Các ánh xạ giống nhau.
Dãy khóa khi duyệt khác nhau.
```

### 7.1. Kiểm thử thứ tự bằng dãy có thứ tự

Nếu mục tiêu là kiểm tra thứ tự khóa, hãy so sánh hai List khóa được tạo từ lượt duyệt, hoặc kiểm tra chuỗi khóa thu được theo iterator.

Chỉ dùng map.equals hoặc keySet.equals là chưa đủ. Set cũng đánh giá thành phần theo phép bằng của tập hợp, không xác nhận thứ tự duyệt của nó.

Nếu cần kiểm tra cả nội dung và thứ tự, có thể kiểm tra ánh xạ rồi kiểm tra dãy khóa. Nếu cần giữ các cặp để so sánh sau khi map còn có thể đổi, nên chụp các cặp thích hợp thay vì giữ entry sống rồi coi đó là dữ liệu bất biến.

### 7.2. Không dùng hashCode của map để xác nhận thứ tự

Hợp đồng hashCode của Map đi cùng equals của ánh xạ. Hai map bằng nhau phải có cùng hashCode dù thứ tự chèn khác.

Một hashCode trùng nhau càng không chứng minh thứ tự giống nhau. Đừng dùng nó thay cho một kiểm tra thứ tự có mục đích rõ ràng.

## 8. Sao chép giữ thứ tự đang quan sát, không khôi phục một lịch sử bị mất

new LinkedHashMap<>(source) tạo một map theo thứ tự chèn với các ánh xạ từ source. Thứ tự được đưa vào bản sao theo lượt duyệt nguồn.

### 8.1. Nếu nguồn có hợp đồng thứ tự

Sao chép từ một LinkedHashMap theo thứ tự chèn giúp giữ thứ tự duyệt của nguồn tại lúc sao chép.

Nếu nguồn là TreeMap, bản sao có thể bắt đầu với thứ tự khóa đang được duyệt theo sắp xếp. Nhưng bản sao mới vẫn là LinkedHashMap theo thứ tự chèn: thêm một khóa mới sau đó đưa nó xuống cuối, không tự chen vào vị trí đã sắp xếp.

Sao chép từ một map theo thứ tự truy cập cũng ghi nhận thứ tự được quan sát lúc đó; constructor sao chép không tự mang chế độ accessOrder sang bản mới.

### 8.2. Nếu nguồn không bảo đảm thứ tự

Sao chép một HashMap thành LinkedHashMap ghi nhận thứ tự mà HashMap đưa ra trong lượt sao chép. Nó không biết các khóa đã được thêm vào HashMap theo trình tự nào.

Kết quả mới có thể được giữ ổn định theo lịch sử thao tác sau đó, nhưng không trở thành một thứ tự chuẩn như chữ cái, thời gian tạo bản ghi hay thứ tự đầu vào ban đầu.

Nếu đầu ra cần thứ tự nhất quán độc lập với thứ tự nguồn, hãy định nghĩa quy tắc đó rồi chủ động sắp xếp hoặc đưa dữ liệu vào theo quy tắc ấy.

### 8.3. Bản sao cấu trúc chưa phải bản sao sâu

Thêm hoặc xóa ánh xạ ở bản gốc không tự thêm hoặc xóa ánh xạ ở bản sao. Tuy nhiên khóa và giá trị là các đối tượng được tham chiếu lại.

Nếu một giá trị là đối tượng có thể sửa, hai map có thể cùng trỏ tới đối tượng giá trị đó. LinkedHashMap không tự sao chép sâu mọi đối tượng chỉ vì constructor nhận một Map.

## 9. Ví dụ Java 17: equals, sao chép và chế độ truy cập

Lưu thành **OrderSemanticsDemo.java**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class OrderSemanticsDemo {
    static List<String> keys(Map<String, Integer> map) {
        return new ArrayList<>(map.keySet());
    }

    public static void main(String[] args) {
        Map<String, Integer> left = new LinkedHashMap<>();
        left.put("b", 2);
        left.put("a", 1);
        left.put("c", 3);

        Map<String, Integer> right = new LinkedHashMap<>();
        right.put("c", 3);
        right.put("a", 1);
        right.put("b", 2);
        System.out.println("left order: " + keys(left));
        System.out.println("right order: " + keys(right));
        System.out.println("maps equal: " + left.equals(right));
        System.out.println("key sequences equal: " + keys(left).equals(keys(right)));

        Map<String, Integer> copy = new LinkedHashMap<>(left);
        left.remove("a");
        left.put("d", 4);
        System.out.println("left later: " + keys(left));
        System.out.println("copy order: " + keys(copy));

        Map<String, Integer> byAccess = new LinkedHashMap<>(16, 0.75f, true);
        byAccess.put("a", 1);
        byAccess.put("b", 2);
        byAccess.put("c", 3);
        System.out.println("access initial: " + keys(byAccess));
        System.out.println("access get a: " + byAccess.get("a"));
        System.out.println("access after get: " + keys(byAccess));
        System.out.println("access contains b: " + byAccess.containsKey("b"));
        System.out.println("access after contains: " + keys(byAccess));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 OrderSemanticsDemo.java
java OrderSemanticsDemo
```

Stdout trên môi trường đã nêu:

```text
left order: [b, a, c]
right order: [c, a, b]
maps equal: true
key sequences equal: false
left later: [b, c, d]
copy order: [b, a, c]
access initial: [a, b, c]
access get a: 1
access after get: [b, c, a]
access contains b: true
access after contains: [b, c, a]
```

### 9.1. Hai kết quả bằng khác nhau

Left và right có cùng ánh xạ nên maps equal là true. Hai List khóa khác thứ tự nên key sequences equal là false.

Đây là lý do một bài kiểm thử về thứ tự phải kiểm tra dãy có thứ tự, không chỉ gọi equals trên Map.

### 9.2. Bản sao giữ dãy trước khi nguồn đổi

Copy được tạo khi left có b, a, c. Sau đó left bỏ a và thêm d nên thành b, c, d. Copy vẫn có b, a, c.

Các giá trị Integer trong ví dụ không cần xử lý việc sửa đối tượng dùng chung, nhờ vậy ta tập trung quan sát sự độc lập của các ánh xạ.

### 9.3. Get và containsKey khác nhau trong chế độ truy cập

ByAccess bắt đầu với a, b, c. Get a trả 1 và đưa a về cuối, thành b, c, a.

ContainsKey b trả true nhưng không làm b rời đầu chuỗi. Hàm keys chỉ duyệt keySet để tạo List, nên việc in thứ tự cũng không tự phát sinh truy cập làm đổi thứ tự.

Không áp dụng hành vi của byAccess ngược lại cho map mặc định trong chương trình đầu; hai đối tượng có cấu hình thứ tự khác nhau.

## 10. Chi phí của sự kết hợp này

### 10.1. Tra cứu vẫn dựa vào băm

Với hàm băm phân bố phù hợp, các thao tác cơ bản theo khóa có hiệu năng kỳ vọng hằng số. Liên kết thứ tự không biến get thành việc quét toàn chuỗi từ đầu.

Điều kiện phân bố hash vẫn quan trọng. Có thứ tự duyệt không giải quyết một equals/hashCode sai, khóa thay đổi phần định danh hoặc dữ liệu bị dồn quá mức vào một bucket.

### 10.2. Duyệt toàn map đi theo số entry

Iterator theo chuỗi liên kết nên lượt duyệt toàn bộ collection view có chi phí tỉ lệ với size của map, không phải quét mọi bucket theo cách của HashMap.

Ví dụ, một bảng được dành nhiều bucket nhưng chỉ có 100 ánh xạ thì chuỗi thứ tự có 100 entry để thăm. Phần cấu trúc duyệt không cần lần qua từng bucket rỗng.

Tuy nhiên công việc trong thân vòng lặp vẫn có chi phí riêng. “Tỉ lệ với size” không có nghĩa mọi lượt duyệt đều nhanh hơn một cấu trúc khác trong mọi môi trường.

### 10.3. Bộ nhớ và cập nhật có chi phí thêm

Các liên kết trước/sau cần được lưu và cập nhật. Khi thêm, xóa hoặc đổi thứ tự trong chế độ truy cập, cấu trúc phải duy trì chuỗi nhất quán.

Vì vậy không xem LinkedHashMap như một HashMap có thêm thứ tự miễn phí. Kích thước byte cụ thể phụ thuộc bố trí đối tượng và JVM, không nên tự gán một con số cố định cho mọi máy.

Capacity và load factor vẫn ảnh hưởng tới bảng băm, bộ nhớ và việc tăng bảng. Việc iterator không quét bucket rỗng không khiến dành dung lượng cực lớn trở thành vô hại.

### 10.4. Thay đổi bucket không được phá thứ tự đã cam kết

Cài đặt có thể tăng bảng hoặc đổi cách tổ chức một nhóm va chạm. Những việc đó phục vụ cơ chế băm; chúng không cho phép tùy ý đổi thứ tự chèn đã cam kết với người dùng.

Đây là lợi ích của việc tách hai vai trò: cách tìm entry có thể thay đổi bên trong, còn hợp đồng thứ tự vẫn được duy trì.

Kiểm thử theo public API có thể nạp nhiều khóa, dùng cả những khóa va chạm hợp lệ, rồi xác nhận dãy khóa và kết quả tra cứu đều đúng. Không cần kiểm tra tên lớp node nội bộ để chứng minh hợp đồng ấy.

## 11. “Có xác định” cần có đầu vào và lịch sử tương ứng

LinkedHashMap cho biết thứ tự sẽ được duy trì theo quy tắc đã chọn. Nó không tạo ra một thứ tự chuẩn độc lập với mọi lịch sử.

### 11.1. Cùng thao tác cho cùng mô hình thứ tự

Nếu cùng tạo map mặc định rồi lần lượt thêm a, b, c và cập nhật b, ta có cơ sở dự đoán dãy a, b, c.

Nếu đọc dữ liệu từ một nguồn không có hợp đồng thứ tự và đưa vào theo lượt duyệt của nguồn đó, đầu vào cho lịch sử chèn có thể khác nhau. LinkedHashMap vẫn làm đúng quy tắc, nhưng thứ tự giữa những lần xây dựng không nhất thiết giống nhau.

### 11.2. Ổn định trong bộ nhớ chưa bảo đảm thứ tự tới nơi nhận

Chuyển sang một cấu trúc không giữ thứ tự có thể làm mất yêu cầu này. Một thư viện xuất dữ liệu cũng có hợp đồng riêng về thứ tự đầu ra và cách bên nhận diễn giải nó.

Nếu thứ tự là dữ liệu nghiệp vụ, cần mô hình hóa và kiểm tra nó qua toàn bộ đường truyền. Ví dụ, một danh sách có thứ tự có thể phù hợp hơn nếu bên nhận phải đọc các mục theo vị trí.

Không chỉ nhìn một println đúng trong Java rồi kết luận mọi bước xử lý phía sau đều giữ cùng ý nghĩa thứ tự.

### 11.3. Thứ tự không tạo an toàn nhiều luồng

LinkedHashMap không tự đồng bộ hóa truy cập. Khi nhiều luồng cùng thao tác, phải có cách phối hợp thích hợp với yêu cầu của chương trình.

Ở chế độ truy cập, get có thể thay đổi thứ tự nội bộ. Vì vậy không chia thao tác thành “đọc luôn vô hại” và “ghi mới thay cấu trúc” chỉ dựa vào tên phương thức.

Một thứ tự được cam kết trong điều kiện sử dụng đúng không có nghĩa các thao tác đồng thời không được phối hợp sẽ tự tạo lịch sử hợp lệ.

## 12. Null, khóa có thể sửa và giới hạn của “giữ thứ tự”

LinkedHashMap cho phép khóa null và giá trị null. Null như một khóa vẫn chỉ có một ánh xạ; giá trị null có thể xuất hiện ở nhiều khóa.

Trong chế độ chèn, cập nhật giá trị của khóa null đang tồn tại giữ vị trí của khóa đó như các khóa khác.

Get trả null chưa tự chứng minh không có khóa; có thể khóa tồn tại với giá trị null. Nếu cần phân biệt, kiểm tra bằng phương thức phù hợp.

Với khóa có thể sửa, vẫn cần giữ các thuộc tính tham gia equals/hashCode ổn định khi khóa đang được dùng trong map. Chuỗi liên kết có thể còn chứa tham chiếu tới entry không có nghĩa mọi lượt get bằng khóa ấy đều còn đúng nếu quy tắc băm đã bị phá.

Không dùng việc “tôi vẫn nhìn thấy entry khi duyệt” làm bằng chứng khóa đang được thiết kế đúng. Tra cứu và duyệt là hai đường khác nhau; lỗi khóa có thể biểu hiện khác nhau trên hai đường đó.

## 13. Lỗi thường gặp và cách sửa

| Hiểu nhầm | Điều cần sửa |
| --- | --- |
| LinkedHashMap luôn sắp xếp khóa | Xác định thứ tự chèn hay truy cập; nếu cần so sánh khóa thì chọn quy tắc phù hợp |
| Có danh sách liên kết nên get phải O(n) | Phân biệt đường tìm bằng hash với đường iterator |
| Put khóa cũ mặc định đưa nó xuống cuối | Cập nhật ánh xạ còn tồn tại giữ vị trí trong chế độ chèn |
| Xóa rồi thêm lại giống cập nhật tại chỗ | Sau khi xóa, lần thêm lại tạo vị trí chèn mới |
| Values là tập không trùng | Chỉ khóa duy nhất; các giá trị vẫn có thể lặp |
| Map.equals xác nhận thứ tự | So sánh thêm dãy khóa hoặc dãy entry được chụp phù hợp |
| Copy từ HashMap khôi phục thứ tự đã thêm | Bản sao chỉ nhận thứ tự đang được nguồn duyệt |
| Copy giữ nguyên chế độ truy cập của nguồn | Constructor sao chép tạo map theo thứ tự chèn |
| Mọi phương thức đều là một lần truy cập | Đọc hợp đồng access-order; containsKey và duyệt view không có tác dụng ấy |
| Biến có kiểu Map nên đối tượng mất thứ tự | Hành vi của LinkedHashMap vẫn còn; giao diện Map bất kỳ không tự hứa cùng thứ tự |
| Có thứ tự nên an toàn nhiều luồng | Tính đồng bộ là yêu cầu riêng |
| Chuỗi liên kết sửa được khóa sai hash | Hợp đồng khóa vẫn phải được tuân thủ |

## 14. Bài tập tự kiểm tra có lời giải

### Bài 1: Dự đoán thứ tự mặc định

Tạo map mặc định, lần lượt put c, a, b rồi put a lần nữa với giá trị khác. Dãy khóa cuối là gì?

**Lời giải:** c, a, b. Khóa a đang tồn tại nên cập nhật giá trị giữ vị trí.

### Bài 2: Xóa rồi thêm

Từ dãy c, a, b, xóa a rồi thêm a lại. Dãy mới là gì?

**Lời giải:** c, b, a. Ánh xạ a cũ đã bị xóa; lần thêm mới nằm ở cuối.

### Bài 3: Hai giá trị giống nhau

Map theo thứ tự x, y, z có các giá trị 7, 7, 9. Values khi duyệt là gì? Size là bao nhiêu?

**Lời giải:** 7, 7, 9 và size bằng 3. Giá trị trùng không nhập các khóa khác nhau.

### Bài 4: Bảng băm có va chạm

Hai khóa khác nhau có cùng hash hợp lệ. Có bắt buộc chúng phải đứng cạnh nhau khi duyệt LinkedHashMap không?

**Lời giải:** không. Thứ tự của toàn map đi theo quy tắc chèn hoặc truy cập. Nhiều khóa được chèn xen giữa có thể nằm giữa chúng trong chuỗi thứ tự dù không cùng bucket.

### Bài 5: Kiểm tra equals

Hai map có cùng a=1, b=2 nhưng dãy khóa là a,b và b,a. Map.equals có thể true không?

**Lời giải:** có. Nó kiểm tra ánh xạ. Nếu bài kiểm thử đòi thứ tự a,b, cần kiểm tra một dãy có thứ tự tương ứng.

### Bài 6: Sao chép từ nguồn đã sắp xếp

Sao chép một TreeMap có khóa a,c sang LinkedHashMap rồi thêm b. Có chắc bản sao duyệt a,b,c không?

**Lời giải:** không. Bản sao bắt đầu với a,c rồi chèn b vào cuối, nên a,c,b trong chế độ chèn thông thường.

### Bài 7: Hai kiểu đọc

Map access-order đang có a,b,c. Get a thành công, rồi containsKey b. Dãy cuối là gì?

**Lời giải:** b,c,a. Get a đưa a thành mới được truy cập; containsKey b không đưa b xuống cuối.

### Bài 8: Chọn cấu trúc

Cần tra cứu cấu hình theo tên và xuất theo lần xuất hiện đầu tiên của tên; giá trị sau có thể ghi đè giá trị trước. Cấu trúc mặc định nào phù hợp với hai yêu cầu ấy?

**Lời giải:** LinkedHashMap theo thứ tự chèn phù hợp. Put khóa cũ cập nhật giá trị nhưng giữ vị trí lần chèn còn tồn tại, miễn không xóa khóa rồi tạo lại.

## 15. Tài liệu đối chiếu

- [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): hợp đồng thứ tự, hai chế độ, view, hiệu năng và đồng bộ.
- [LinkedHashMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/LinkedHashMap.java): liên kết trước/sau, đầu/cuối, cập nhật liên kết và đường iterator.
- [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): hợp đồng ánh xạ, equals, hashCode và các view.
- [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): đối chiếu việc không bảo đảm thứ tự duyệt.
- [TreeMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): đối chiếu thứ tự theo phép so sánh khóa.

Điểm cần giữ là hai vai trò cùng tồn tại: bảng băm giúp tìm ánh xạ, chuỗi liên kết giúp duyệt theo quy tắc đã chọn. Khi dùng LinkedHashMap, hãy xác định rõ quy tắc thứ tự và kiểm tra nó như một yêu cầu độc lập với nội dung ánh xạ.
