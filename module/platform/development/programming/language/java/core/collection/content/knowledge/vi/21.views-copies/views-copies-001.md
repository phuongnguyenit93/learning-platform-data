# Phân biệt collection sở hữu dữ liệu với view dùng chung nguồn

## 1. Một danh sách trả về có thể là dữ liệu riêng hoặc một cửa sổ nhìn vào nguồn

Giả sử một đối tượng quản lý danh sách công việc và trả một List cho bên gọi. Bên gọi thêm hoặc xóa phần tử trên kết quả rồi thấy dữ liệu của đối tượng quản lý cũng đổi.

Một nguyên nhân có thể là kết quả đang dùng chung cấu trúc nền: đó có thể là chính đối tượng ban đầu hoặc một view gắn với nó.

Ngược lại, hai danh sách có cấu trúc riêng vẫn có thể cùng giữ một đối tượng công việc. Khi sửa trường của đối tượng ấy, cả hai cùng nhìn thấy thay đổi.

Vì vậy không thể chỉ hỏi “đây có phải bản sao không?”. Cần tách ba câu hỏi:

1. Tập phần tử, vị trí hoặc ánh xạ có được quản lý độc lập với nguồn không?
2. Những phép sửa nào được phép qua bề mặt đang cầm?
3. Các đối tượng phần tử có được dùng chung không?

Bài dùng cụm **sở hữu cấu trúc lưu trữ** để nói về collection tự quản lý các liên kết phần tử của nó, chẳng hạn một ArrayList mới được tạo từ dữ liệu nguồn.

Đây không phải quyền sở hữu độc quyền được hệ thống kiểu Java kiểm tra. Một collection vẫn có thể có nhiều biến cùng trỏ tới nó; một cấu trúc có các liên kết riêng vẫn có thể dùng chung các object phần tử.

**View (khung nhìn)** cung cấp một bề mặt truy cập dựa trên dữ liệu nền. Nó có thể giới hạn miền, đổi cách biểu diễn hoặc hạn chế phép sửa, trong khi vẫn gắn với nguồn.

## 2. Hai tầng dữ liệu: cấu trúc chứa và đối tượng phần tử

### 2.1. Collection quản lý cấu trúc riêng

Một biểu thức như new ArrayList<>(source) tạo một ArrayList quản lý cấu trúc danh sách của nó.

Sau khi sao chép xong trong điều kiện nguồn hợp lệ, thêm hoặc xóa một liên kết trong danh sách nguồn không tự thêm/xóa liên kết tương ứng ở ArrayList mới.

Có thể hình dung:

```text
nguồn ──> cấu trúc danh sách 1 ──> Item A, Item B
bản chép ─> cấu trúc danh sách 2 ──> Item A, Item B
                                     các Item vẫn có thể dùng chung
```

Sự độc lập nằm ở cấu trúc danh sách. Không suy ra Item A và Item B đã được nhân bản.

### 2.2. View dùng nguồn để thực hiện thao tác

Một view thường giữ quan hệ tới dữ liệu nền và chuyển các thao tác thích hợp về nguồn thay vì giữ một tập phần tử độc lập.

Ví dụ Collections.unmodifiableList(source) cho một bề mặt đọc danh sách nguồn. Source còn thay đổi hợp lệ thì người đọc view có thể nhìn thấy thay đổi ấy; phép sửa qua view bị chặn theo hợp đồng.

```text
biến source ────────> danh sách nguồn ──> Item A, Item B
biến view ──> lớp view ────────┘
```

Các view có điều kiện sử dụng riêng. Không hiểu sơ đồ thành mọi thay đổi nguồn đều hợp lệ cho mọi view, đặc biệt với List.subList.

Phân biệt collection quản lý lưu trữ và view được giới thiệu trong [Collection Java 17, phần View Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

### 2.3. Phép gán tham chiếu còn đơn giản hơn một view

Nếu viết alias = source thì hai biến cùng trỏ tới một đối tượng. Không có collection mới và không có lớp view mới được tạo chỉ bởi phép gán.

Một view có thể là object khác với nguồn mà vẫn chia sẻ dữ liệu nền. Vì vậy kết quả so == khác nhau không chứng minh hai cấu trúc độc lập.

Equals cũng không chứng minh độc lập. Hai collection có thể có cùng dữ liệu ở một thời điểm nhưng khác hoàn toàn chính sách chia sẻ.

### 2.4. Kiểu List/Set/Collection không ghi hết chính sách sở hữu

Một biến List có thể giữ ArrayList, subList, lớp bao chỉ đọc, danh sách gắn với mảng hoặc kết quả List.copyOf.

Chữ List không nói kết quả là bản sao, có cho thêm hay không, hoặc có gắn với một nguồn khác không.

Cần đọc hợp đồng của phương thức tạo/trả kết quả. Những từ như backed by, view, copy và unmodifiable trong tài liệu có ý nghĩa khác nhau.

## 3. Ví dụ 1: alias, view, bản sao cấu trúc và phần tử dùng chung

Lưu thành **StructureOwnerAndView.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class StructureOwnerAndView {
    static final class Line {
        final String code;
        int quantity;

        Line(String code, int quantity) {
            this.code = code;
            this.quantity = quantity;
        }

        @Override
        public String toString() {
            return code + ":" + quantity;
        }
    }

    public static void main(String[] args) {
        Line first = new Line("A", 1);
        List<Line> owner = new ArrayList<>(List.of(first, new Line("B", 2)));
        List<Line> alias = owner;
        List<Line> view = Collections.unmodifiableList(owner);
        List<Line> copy = new ArrayList<>(owner);
        List<Line> snapshot = List.copyOf(owner);

        System.out.println("alias is owner: " + (alias == owner));
        System.out.println("view is owner: " + (view == owner));
        owner.add(new Line("C", 3));
        System.out.println("view after owner add: " + view);
        System.out.println("copy after owner add: " + copy);
        System.out.println("snapshot after owner add: " + snapshot);

        first.quantity = 9;
        System.out.println("owner after element edit: " + owner);
        System.out.println("copy after element edit: " + copy);
        System.out.println("snapshot after element edit: " + snapshot);

        copy.remove(0);
        System.out.println("copy after its remove: " + copy);
        System.out.println("owner after copy remove: " + owner);
        try {
            view.add(new Line("D", 4));
        } catch (UnsupportedOperationException expected) {
            System.out.println("view add: rejected");
        }
        try {
            snapshot.clear();
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot clear: rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 StructureOwnerAndView.java
java StructureOwnerAndView
```

Stdout:

```text
alias is owner: true
view is owner: false
view after owner add: [A:1, B:2, C:3]
copy after owner add: [A:1, B:2]
snapshot after owner add: [A:1, B:2]
owner after element edit: [A:9, B:2, C:3]
copy after element edit: [A:9, B:2]
snapshot after element edit: [A:9, B:2]
copy after its remove: [B:2]
owner after copy remove: [A:9, B:2, C:3]
view add: rejected
snapshot clear: rejected
```

Các ví dụ trong bài được biên dịch với --release 17 và chạy trên OpenJDK 24.0.2. Cờ --release chọn mức ngôn ngữ/API và bytecode đích, không thay phiên bản JVM thực thi.

### 3.1. Alias là cùng đối tượng, còn view khác đối tượng vẫn gắn nguồn

`alias == owner` cho true vì chỉ có thêm một biến trỏ tới danh sách owner.

`view != owner` trong ví dụ này, nhưng khi owner thêm C, view vẫn đọc được C. Việc có object view khác không tạo dữ liệu độc lập.

Đừng dùng một phép kiểm tra nhận dạng object để thay cho hợp đồng chia sẻ dữ liệu.

### 3.2. Copy và snapshot giữ riêng tập liên kết đã lấy

Biến copy được tạo bằng constructor ArrayList; snapshot được tạo bằng List.copyOf. Cả hai được tạo trước khi C được thêm vào owner.

Owner thêm C không làm copy hoặc snapshot tự có C. Xóa A khỏi copy cũng không xóa A khỏi owner.

Tên snapshot ở đây nói về tập liên kết đã lấy trong điều kiện ví dụ không có cập nhật đồng thời. Nó không hứa đã sao chép sâu mọi dữ liệu hoặc thực hiện một giao dịch đọc nguyên tử trong mọi chương trình.

### 3.3. Sửa Line A tác động tầng phần tử

Đối tượng first được cả owner, copy và snapshot cùng tham chiếu. Đổi quantity của nó thành 9 làm cả ba cùng in A:9.

Đó không phải việc các danh sách liên tục sao chép trạng thái cho nhau. Chúng đang đọc cùng một object Line.

Nếu muốn không chia sẻ dữ liệu khả biến của phần tử, cần một mô hình bất biến hoặc một chính sách sao chép phần tử riêng.

### 3.4. Không cho sửa qua kết quả chưa đủ để phân loại view hay bản sao

Lời gọi `view.add` bị từ chối vì lớp bao chỉ đọc.

Lời gọi `snapshot.clear` cũng bị từ chối, nhưng snapshot không phản ánh phần tử C được thêm vào owner sau lần tạo.

Hai kết quả cùng chặn thao tác sửa vẫn khác quan hệ với cấu trúc nguồn. Tài liệu [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) và [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) công bố những hợp đồng khác nhau ấy.

## 4. View theo miền và view gắn với mảng

### 4.1. SubList là một miền của List nguồn

List.subList(from, to) trả view từ chỉ số from, có tính phần tử ấy, tới to, không tính phần tử ở to.

Nó không mặc định chép các phần tử trong miền sang một ArrayList riêng. Nếu nguồn hỗ trợ, các phép sửa qua subList có thể tác động chính danh sách nguồn.

Một thao tác như subList(...).clear có thể xóa cả miền trong danh sách gốc. Đây là công dụng của view khi người gọi chủ động muốn tác động nguồn.

### 4.2. Giới hạn quan trọng của subList

Theo hợp đồng [List.subList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)), thay đổi không cấu trúc được phản ánh giữa hai cách nhìn.

Nhưng nếu danh sách nền bị sửa cấu trúc theo đường khác với subList trả về, ngữ nghĩa của subList có thể trở thành không được xác định. Sửa cấu trúc gồm thay đổi kích thước hoặc những thay đổi làm hoạt động duyệt không còn đúng.

Ví dụ dùng full.set để thay một phần tử và dùng window.remove/add/clear qua chính view. Nó không thêm trực tiếp vào full rồi tiếp tục mặc định window còn hợp lệ.

Không viết một quy tắc “thêm vào nguồn thì subList luôn cập nhật như danh sách độc lập”. Cũng không đóng đinh ConcurrentModificationException như kết quả API bắt buộc của mọi trường hợp dùng sai view.

Nếu cần giữ một miền độc lập với những thay đổi cấu trúc về sau của nguồn, hãy chép miền ấy trong lúc dữ liệu còn hợp lệ.

### 4.3. Arrays.asList là view có kích thước cố định gắn với mảng

Arrays.asList(array) tạo một List gắn với mảng được truyền vào. Set phần tử qua List có thể đổi ô mảng; gán ô mảng có thể được nhìn thấy qua List.

Nó không cho tăng/giảm số phần tử như một ArrayList thông thường. Cố định kích thước không đồng nghĩa cấm thay thế phần tử.

Các quyền này được mô tả trong [Arrays.asList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### 4.4. Ví dụ 2: sửa một miền và một mảng qua view

Lưu thành **RangeAndArrayViews.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class RangeAndArrayViews {
    public static void main(String[] args) {
        List<String> full = new ArrayList<>(
                List.of("zero", "one", "two", "three", "four"));
        List<String> window = full.subList(1, 4);
        List<String> copy = new ArrayList<>(window);

        window.set(1, "TWO");
        System.out.println("full after window set: " + full);
        full.set(1, "ONE");
        System.out.println("window after full set: " + window);

        window.remove(0);
        window.add("extra");
        System.out.println("window after its edits: " + window);
        System.out.println("full after window edits: " + full);
        window.clear();
        System.out.println("full after window clear: " + full);
        System.out.println("window size: " + window.size());
        System.out.println("copy remains: " + copy);

        String[] names = {"Lan", "Mai"};
        List<String> arrayView = Arrays.asList(names);
        names[0] = "Linh";
        System.out.println("view after array edit: " + arrayView);
        arrayView.set(1, "MAI");
        System.out.println("array after view set: " + Arrays.toString(names));
        try {
            arrayView.add("An");
        } catch (UnsupportedOperationException expected) {
            System.out.println("array view add: rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 RangeAndArrayViews.java
java RangeAndArrayViews
```

Stdout:

```text
full after window set: [zero, one, TWO, three, four]
window after full set: [ONE, TWO, three]
window after its edits: [TWO, three, extra]
full after window edits: [zero, TWO, three, extra, four]
full after window clear: [zero, four]
window size: 0
copy remains: [one, two, three]
view after array edit: [Linh, Mai]
array after view set: [Linh, MAI]
array view add: rejected
```

### 4.5. Đọc kết quả theo nguồn thật sự bị tác động

Biến window ban đầu gồm one,two,three. `window.set(1,"TWO")` đổi phần tử two trong full; full.set(1,"ONE") lại được nhìn qua window.

Các thao tác remove/add qua window làm thay đổi đúng miền trong full. `window.clear` xóa miền hiện tại, nên full chỉ còn zero,four.

Copy vẫn giữ one,two,three vì đã lấy các liên kết trước các thao tác ấy. Ví dụ dùng String để tập trung vào cấu trúc, không có thay đổi trường khả biến của phần tử.

Ở phần mảng, names[0] đổi thành Linh và được nhìn qua arrayView. `arrayView.set` đổi ô thứ hai thành MAI. Add bị từ chối vì view không quản lý một mảng mới có thể tự tăng kích thước.

## 5. Các collection view của Map dựa trên ánh xạ nguồn

### 5.1. KeySet, values và entrySet không phải ba bản dữ liệu độc lập

Map.keySet trả Set view của khóa; values trả Collection view của giá trị; entrySet trả Set view của các ánh xạ.

Thêm một ánh xạ vào map có thể được nhìn thấy qua các view đã lấy. Khi view cho phép xóa, xóa qua view tác động ánh xạ trong map.

Chỉ có một khóa chưa đủ thông tin tạo value mới. Vì vậy không suy keySet.add được hỗ trợ chỉ vì kiểu trả về là Set.

Các hợp đồng backed view và quyền thêm/xóa được quy định trong [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

### 5.2. Entry còn là một bề mặt sửa khác

Một Map.Entry nhận trong lúc duyệt một map cho phép cập nhật có thể hỗ trợ setValue để sửa value của ánh xạ.

Cần đọc hợp đồng về thời gian kết nối của entry tới map và quyền sửa của triển khai. Không giữ một entry tùy ý qua mọi lần sửa map rồi mặc định kết nối luôn còn hợp lệ.

Trong ví dụ dưới, setValue được thực hiện ngay trong lần duyệt entrySet của LinkedHashMap, không dùng entry sau một thao tác sửa cấu trúc bên ngoài lần duyệt.

### 5.3. Ví dụ 3: view xóa ánh xạ và giới hạn của lớp bao tập entry

Lưu thành **MapViewsAndEntryPermissions.java**:

```java
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class MapViewsAndEntryPermissions {
    public static void main(String[] args) {
        Map<String, Integer> source = new LinkedHashMap<>();
        source.put("alpha", 1);
        source.put("beta", 2);
        source.put("gamma", 3);
        Set<String> keys = source.keySet();
        Collection<Integer> values = source.values();
        Set<Map.Entry<String, Integer>> entries = source.entrySet();
        Map<String, Integer> copy = new LinkedHashMap<>(source);

        source.put("delta", 4);
        System.out.println("keys after map put: " + keys);
        keys.remove("beta");
        values.remove(3);
        System.out.println("map after view removals: " + source);

        for (Map.Entry<String, Integer> entry : entries) {
            if (entry.getKey().equals("alpha")) {
                entry.setValue(10);
                break;
            }
        }
        System.out.println("map after entry setValue: " + source);
        try {
            keys.add("new-key");
        } catch (UnsupportedOperationException expected) {
            System.out.println("key view add: rejected");
        }

        Set<Map.Entry<String, Integer>> setOnlyWrapper =
                Collections.unmodifiableSet(entries);
        for (Map.Entry<String, Integer> entry : setOnlyWrapper) {
            if (entry.getKey().equals("alpha")) {
                entry.setValue(11);
                break;
            }
        }
        System.out.println("map after set-only entry edit: " + source);

        Map<String, Integer> readOnlyMap = Collections.unmodifiableMap(source);
        try {
            for (Map.Entry<String, Integer> entry : readOnlyMap.entrySet()) {
                entry.setValue(99);
                break;
            }
        } catch (UnsupportedOperationException expected) {
            System.out.println("unmodifiable map entry edit: rejected");
        }
        source.put("epsilon", 5);
        System.out.println("read-only map after source put: " + readOnlyMap);
        System.out.println("copy remains: " + copy);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 MapViewsAndEntryPermissions.java
java MapViewsAndEntryPermissions
```

Stdout:

```text
keys after map put: [alpha, beta, gamma, delta]
map after view removals: {alpha=1, delta=4}
map after entry setValue: {alpha=10, delta=4}
key view add: rejected
map after set-only entry edit: {alpha=11, delta=4}
unmodifiable map entry edit: rejected
read-only map after source put: {alpha=11, delta=4, epsilon=5}
copy remains: {alpha=1, beta=2, gamma=3}
```

### 5.4. Xóa qua key/value view xóa trên map

Sau khi map thêm delta, view keys đã lấy trước đó cũng có delta.

`keys.remove("beta")` bỏ ánh xạ beta=2. `values.remove(3)` bỏ ánh xạ gamma=3 trong dữ liệu mẫu này.

`entry.setValue` thay alpha thành 10. Bản copy được tạo trước đó vẫn giữ alpha=1,beta=2,gamma=3 vì nó có tập liên kết ánh xạ riêng.

LinkedHashMap được dùng để thứ tự in trong ví dụ ổn định theo thứ tự chèn. Không suy mọi Map đều có thứ tự duyệt ấy.

### 5.5. Bọc Set chỉ đọc không tự làm các entry bên trong chỉ đọc

Biến setOnlyWrapper là Collections.unmodifiableSet(entries). Nó chặn những thao tác sửa tập qua bề mặt Set, nhưng không tự biến mỗi phần tử Map.Entry thành một object không sửa được.

Trong lần duyệt này, entry.setValue(11) vẫn thay alpha ở map nguồn.

Đây là biểu hiện cụ thể của quy tắc “không sửa collection” khác “không sửa object phần tử”. Với entry, sửa object ấy còn có thể là đường cập nhật map.

Nếu mục tiêu là cung cấp một map không cho sửa qua chính map và các collection view của nó, Collections.unmodifiableMap cung cấp hợp đồng phù hợp hơn. Ví dụ cho thấy setValue từ entrySet của lớp bao map này bị từ chối.

Tài liệu [Collections.unmodifiableMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)) mô tả việc chặn sửa trực tiếp và qua các view.

### 5.6. Map chỉ đọc vẫn có thể đọc dữ liệu nguồn mới

Source còn được giữ và tiếp tục put epsilon. Biến readOnlyMap nhìn thấy ánh xạ mới vì nó là view, không phải bản sao độc lập.

Nếu cần một ảnh chụp không đổi về tập ánh xạ khi nguồn thay đổi, phải tạo một cấu trúc ánh xạ riêng theo chính sách mong muốn rồi áp quyền sửa phù hợp.

Các object key/value vẫn cần được xét ở tầng dữ liệu phần tử. Một lớp bao map không tự sao chép sâu chúng.

## 6. Ba trục phân loại phải được đọc độc lập

| Kết quả được tạo | Quan hệ cấu trúc với nguồn | Phép sửa qua kết quả | Phần tử có thể dùng chung? |
| --- | --- | --- | --- |
| alias = source | Cùng một đối tượng | Theo chính đối tượng ấy | Có |
| new ArrayList<>(source) | Danh sách riêng sau khi chép | Theo ArrayList | Có |
| Collections.unmodifiableList(source) | View gắn nguồn | Không cho sửa List qua view | Có |
| source.subList(from, to) | View miền, có điều kiện hợp lệ riêng | Các phép tùy chọn mà nguồn hỗ trợ | Có |
| Arrays.asList(array) | View gắn mảng | Thay phần tử được; tăng/giảm kích thước không được | Có |
| List.copyOf(source) | Không phản ánh sửa cấu trúc nguồn sau lần lấy | Không cho sửa List kết quả | Có |
| map.keySet() | View của ánh xạ map | Xóa nếu được hỗ trợ; không thêm khóa bằng add | Dùng các khóa của map |

Bảng không thay hợp đồng chi tiết của từng view, đặc biệt giới hạn sửa cấu trúc ở subList hoặc sửa map trong lúc duyệt.

### 6.1. Sửa được không đồng nghĩa sở hữu riêng

SubList sửa được vẫn là view. Arrays.asList thay phần tử được vẫn dựa vào mảng. KeySet xóa được vẫn tác động map nguồn.

Việc gọi một phép sửa thành công chỉ chứng minh phép đó được hỗ trợ trong điều kiện hiện tại.

### 6.2. Không sửa được chưa có nghĩa là snapshot hoặc bất biến sâu

Một view chỉ đọc có thể phản ánh sửa từ nguồn. Một List.copyOf có tập liên kết ổn định với sửa cấu trúc nguồn nhưng vẫn giữ phần tử khả biến dùng chung.

Không có một từ duy nhất thay cho cả quyền sửa, quan hệ chia sẻ và độ sâu sao chép.

### 6.3. Không dựa vào việc factory cấp phát object mới

List.copyOf công bố hành vi kết quả; API có thể tái sử dụng kết quả không sửa được thích hợp thay vì bắt buộc tạo object mới cho mọi lời gọi.

Điều cần dựa vào là kết quả không phản ánh những thay đổi cấu trúc về sau của Collection nguồn theo hợp đồng. Không kiểm tra object phải khác bằng != để chứng minh một factory đã thực hiện đúng.

“Sở hữu cấu trúc” trong thiết kế không phải một lời hứa về cách JVM cấp phát bộ nhớ bên trong mọi phương thức tạo collection.

### 6.4. Chính sách dữ liệu đích cũng có thể khác

List.copyOf từ chối phần tử null. Constructor ArrayList có thể chép một danh sách chứa null.

Một Set đích còn có tính duy nhất; một cấu trúc sorted có quy tắc thứ tự riêng. Sao chép sang một kiểu khác không tự bảo toàn mọi đặc tính của nguồn.

Hãy chọn kiểu đích theo dữ liệu và yêu cầu sử dụng, không chỉ theo mong muốn “tạo bản sao”.

## 7. Quyền sở hữu ở ranh giới API

### 7.1. Nhận dữ liệu đầu vào

Nếu một đối tượng giữ trực tiếp List mà bên gọi truyền vào, bên gọi có thể còn một biến tham chiếu và tiếp tục sửa List ấy.

Khai báo trường giữ List là final chỉ ngăn gán trường sang đối tượng khác. Nó không tự ngăn bên ngoài thêm/xóa phần tử ở collection đang được chia sẻ.

Nếu đối tượng cần giữ tập dữ liệu ổn định của riêng nó, hãy sao chép đầu vào theo chính sách rõ ràng trước khi lưu. Nếu dữ liệu cần bất biến sâu, còn phải chọn kiểu phần tử hoặc cách chép phần tử phù hợp.

Nếu đối tượng chủ động chia sẻ một nguồn thay đổi theo thời gian, cũng có thể giữ view/tham chiếu, nhưng đó phải là một hợp đồng được công bố.

### 7.2. Trả dữ liệu đầu ra

| Ý nghĩa muốn công bố | Cách trả cần đánh giá |
| --- | --- |
| Bên gọi được sửa chính trạng thái nội bộ | Trả tham chiếu hoặc view sửa được có chủ đích |
| Bên gọi chỉ đọc nhưng cần theo dữ liệu nội bộ mới | View chỉ đọc của nguồn |
| Bên gọi được sửa kết quả riêng mà không đổi cấu trúc nội bộ | Bản sao cấu trúc sửa được |
| Bên gọi giữ tập liên kết riêng không sửa được qua kết quả | Kết quả sao chép không sửa được phù hợp |
| Bên gọi không được tác động cả dữ liệu phần tử nội bộ | Phần tử bất biến hoặc chính sách sao chép sâu |

Không gọi một getter là “an toàn” chỉ vì kiểu trả về là List hoặc vì nó đã bọc unmodifiableList. Cần nói an toàn đối với thao tác và quan hệ chia sẻ nào.

### 7.3. Bọc một bản sao riêng có thể kết hợp hai mục tiêu

Collections.unmodifiableList(new ArrayList<>(source)) kết hợp việc lấy các liên kết vào một danh sách riêng với việc chặn sửa List qua kết quả.

Nếu không để lộ thêm tham chiếu tới danh sách riêng ấy, các lần thêm/xóa source về sau không tự đổi tập liên kết trong kết quả.

Đó vẫn là sao chép nông đối với các object phần tử. Và quá trình đọc nguồn để chép vẫn cần diễn ra trong điều kiện nguồn hợp lệ.

List.copyOf là một lựa chọn khác với hợp đồng riêng, trong đó có việc không nhận null. Hai lựa chọn không thay thế nhau vô điều kiện cho mọi dữ liệu.

### 7.4. Sao chép sâu phải được định nghĩa theo miền dữ liệu

Một Line có thể chứa tham chiếu tới sản phẩm, lịch sử hoặc các phần tử con khác. Tạo một Line mới chưa chắc đã tách mọi dữ liệu phía dưới.

Cần quyết định thành phần nào dùng chung được, thành phần nào phải sao chép và có cần giữ quan hệ giữa các đối tượng hay không.

Với một mô hình dữ liệu bất biến phù hợp, chia sẻ phần tử có thể là lựa chọn đúng và đơn giản hơn việc nhân bản đồ thị đối tượng.

Không dùng serialization hay clone một cách máy móc rồi coi đã giải quyết mọi vấn đề quyền sở hữu.

## 8. Vòng đời, chi phí và các điều kiện sử dụng

### 8.1. View có thể giữ quan hệ tới nguồn lâu hơn dự tính

Một view nhỏ có thể còn giữ liên hệ tới một cấu trúc nguồn lớn trong triển khai cụ thể. Giữ view không mặc định tách vòng đời lưu trữ của phần đang nhìn khỏi toàn bộ nguồn.

Khi cần giữ riêng một miền lâu dài mà không phụ thuộc cấu trúc gốc, sao chép miền đó có thể là lựa chọn phù hợp.

Không gọi mọi view là rò rỉ bộ nhớ; cần xem đồ thị tham chiếu và thời gian sử dụng thực tế.

### 8.2. Chép có chi phí nhưng cũng cung cấp tính độc lập có giá trị

Một cấu trúc riêng cần lưu các liên kết của chính nó và đọc dữ liệu để khởi tạo. Với nguồn lớn, điều này có thể có chi phí đáng kể.

View giúp tránh chủ động chép toàn bộ dữ liệu khi mục tiêu là chia sẻ có kiểm soát. Nhưng dùng view để “tiết kiệm” mà phá vỡ yêu cầu kết quả phải ổn định là thay đổi ý nghĩa API.

Không khẳng định mọi view tạo trong O(1), mọi thao tác view có cùng độ phức tạp, hoặc mọi bản sao có cùng chi phí. Đọc hợp đồng và triển khai thích hợp khi hiệu năng là yêu cầu.

### 8.3. View và bản sao không tự tạo an toàn luồng

Một view của ArrayList không làm nguồn trở thành một cấu trúc cập nhật đồng thời an toàn.

Một bản sao được tạo trong lúc nguồn đang bị sửa cũng không tự là một ảnh chụp nguyên tử. Việc duyệt để chép cần tuân hợp đồng của nguồn và cơ chế nhất quán đang dùng.

Nếu cần một phiên bản ổn định để xử lý, hãy phối hợp các bên sửa/đọc hoặc công bố các phiên bản dữ liệu ổn định theo một mô hình phù hợp.

### 8.4. Không sửa nguồn theo đường làm view mất điều kiện hợp lệ

Với subList, cần đặc biệt tránh sửa cấu trúc trực tiếp trên danh sách nền rồi tiếp tục sử dụng view như không có gì thay đổi.

Với map view, sửa cấu trúc map trong một lần duyệt phải tuân những đường được phép như iterator.remove; không dựa vào việc chưa thấy ngoại lệ trong một lần chạy.

Một collection chứa dữ liệu riêng cũng vẫn có hợp đồng iterator và đồng thời của nó. Sở hữu cấu trúc riêng không tự miễn trừ các quy tắc duyệt.

## 9. Cách đọc tài liệu và kiểm tra quan hệ chia sẻ

### 9.1. Tìm những cam kết quan sát được

Khi gặp một API trả Collection/List/Set/Map, hãy tìm:

1. Kết quả là view hay bản chép?
2. Nguồn nền là gì?
3. Thay đổi nào được phản ánh theo chiều nào?
4. Các phép sửa nào được hỗ trợ?
5. Có điều kiện làm view mất hiệu lực không?
6. Phần tử được dùng chung hay được sao chép theo mức nào?
7. Thứ tự, null và quy tắc dữ liệu của kết quả là gì?

Đây là cách đọc hợp đồng sử dụng, không phải suy tên lớp nội bộ hoặc dùng reflection để đoán.

### 9.2. Viết phép kiểm tra đủ phân biệt

Chỉ so dữ liệu ngay sau khi tạo chưa phân biệt được một view với một bản sao có cùng nội dung.

Các kiểm tra có ý nghĩa gồm:

- Sửa hợp lệ nguồn rồi quan sát kết quả có phản ánh không.
- Sửa qua kết quả nếu được hỗ trợ rồi quan sát nguồn.
- Xóa một liên kết ở bản sao rồi xác nhận nguồn vẫn giữ liên kết riêng.
- Sửa một object phần tử để nhận diện chia sẻ ở tầng phần tử.
- Kiểm tra các quyền khác nhau: set, thêm, xóa, cập nhật entry.
- Kiểm tra những điều kiện dữ liệu như null nếu lựa chọn copy thay đổi chúng.

Không cố tạo các kết quả đã vượt điều kiện hợp đồng rồi coi một stdout hoặc ngoại lệ tình cờ là đặc tả của API.

### 9.3. Dùng phần tử đơn giản trước, phần tử khả biến sau

String hoặc số giúp nhìn rõ việc thêm/xóa/thay vị trí vì không có một trường nghiệp vụ khả biến cần theo dõi.

Sau đó thêm một kiểu như Line để kiểm tra tầng phần tử dùng chung. Nếu trộn cả hai vấn đề ngay từ đầu, rất dễ kết luận sai rằng bản sao cấu trúc “không hoạt động”.

Các ví dụ trong bài cố ý tách những giai đoạn đó để từng kết luận có bằng chứng rõ.

## 10. Những nhầm lẫn phổ biến

| Nhận định | Cách hiểu đúng |
| --- | --- |
| Khác object nghĩa là không dùng chung dữ liệu | Một view khác object vẫn có thể gắn nguồn |
| Cùng dữ liệu ban đầu nghĩa là cùng chính sách sở hữu | View và copy có thể có cùng nội dung tại lúc tạo |
| Mutable nghĩa tự có dữ liệu riêng | Nhiều view sửa được và sửa xuyên về nguồn |
| Unmodifiable nghĩa không bao giờ thay đổi | Nguồn hoặc phần tử bên trong vẫn có thể thay đổi |
| List.copyOf là sao chép sâu | Các object phần tử vẫn có thể được dùng chung |
| Final List là List bất biến | Final chỉ giữ tham chiếu trường không bị gán lại |
| SubList là ArrayList mới của một đoạn | Nó là view miền có điều kiện hợp lệ riêng |
| SubList luôn tiếp tục đúng sau mọi lần thêm vào full | Sửa cấu trúc ngoài view có thể làm ngữ nghĩa view không còn xác định |
| Arrays.asList là ArrayList tăng kích thước được | Nó là List cố định kích thước gắn với mảng |
| Map.keySet là một Set độc lập | Nó là view của khóa trong các ánh xạ map |
| Bọc entrySet bằng unmodifiableSet bảo vệ toàn bộ map | Các entry bên trong vẫn cần xét quyền setValue |
| Một bản sao đọc từ nguồn đang sửa là ảnh chụp nguyên tử | Cần một cơ chế nhất quán phù hợp |
| Có chữ copy nghĩa luôn phải tạo object khác | Factory có thể tái sử dụng kết quả hợp lệ theo hợp đồng |
| Có cấu trúc riêng nghĩa sở hữu độc quyền mọi phần tử | Java không tự áp mô hình sở hữu độc quyền ấy |

## 11. Bài tập tự kiểm tra

### Bài 1. Hai tên khác nhau có tạo hai collection không?

Sau alias = source, xóa phần tử qua alias có tác động source không?

**Gợi ý trả lời:** Có nếu thao tác được đối tượng ấy hỗ trợ. Hai biến cùng trỏ một đối tượng, không có bản sao do phép gán.

### Bài 2. View khác object có dữ liệu riêng không?

Một unmodifiableList khác object với ArrayList nguồn. Nguồn thêm một phần tử hợp lệ, view đọc được phần tử ấy. Điều gì được chứng minh?

**Gợi ý trả lời:** Khác nhận dạng object không tạo độc lập cấu trúc. Kết quả là view gắn với nguồn.

### Bài 3. Không add được đã đủ biết là snapshot chưa?

Hai kết quả cùng ném UnsupportedOperationException khi add. Có thể kết luận chúng đều không phản ánh sửa ở nguồn không?

**Gợi ý trả lời:** Không. Quyền sửa qua kết quả và quan hệ với nguồn là hai trục khác nhau.

### Bài 4. Vì sao copy vẫn thấy quantity mới?

Danh sách được chép bằng new ArrayList<>(source). Một Line chung bị sửa quantity. Việc bản sao cũng thấy số mới có chứng minh cấu trúc vẫn gắn nguồn không?

**Gợi ý trả lời:** Không. Nó cho thấy cùng tham chiếu phần tử được chia sẻ; cấu trúc danh sách vẫn có thể độc lập.

### Bài 5. SubList.clear xóa ở đâu?

Một subList hợp lệ của ArrayList nguồn gọi clear. Có nên mong danh sách gốc giữ nguyên cả miền không?

**Gợi ý trả lời:** Không. Phép xóa qua view tác động miền tương ứng ở danh sách nguồn khi được hỗ trợ.

### Bài 6. Sửa full ngoài window có luôn hợp lệ không?

Đã tạo window = full.subList(...), sau đó full.add thêm một phần tử rồi tiếp tục dùng window. Có thể coi mọi kết quả về sau đều được hợp đồng bảo đảm không?

**Gợi ý trả lời:** Không. Sửa cấu trúc danh sách nền ngoài đường subList có thể làm ngữ nghĩa của view không còn được xác định.

### Bài 7. List gắn với mảng có sửa được không?

Arrays.asList(array) không cho add. Có suy ra set cũng phải bị từ chối không?

**Gợi ý trả lời:** Không. Nó có kích thước cố định nhưng hỗ trợ thay phần tử và phản ánh thay đổi với mảng theo hợp đồng.

### Bài 8. Xóa một khóa qua keySet làm gì?

Map sửa được có một keySet view. Keys.remove("x") thành công. Ánh xạ x trong map có còn không?

**Gợi ý trả lời:** Không. Xóa qua view khóa bỏ ánh xạ tương ứng trong map.

### Bài 9. Vì sao unmodifiableSet(entrySet) chưa đủ?

Trong một LinkedHashMap, tập entry bị bọc unmodifiableSet nhưng entry trong lần duyệt vẫn hỗ trợ setValue. Có thể sửa value của map qua đường ấy không?

**Gợi ý trả lời:** Có trong trường hợp ấy. Cần dùng hợp đồng bảo vệ map và các view của nó, như unmodifiableMap, nếu đó là mục tiêu.

### Bài 10. Chọn gì cho kết quả riêng nhưng không cho sửa List?

Muốn kết quả không phản ánh thêm/xóa về sau ở nguồn, và bên nhận không được sửa cấu trúc qua kết quả. Chỉ unmodifiableList(source) đã đủ chưa?

**Gợi ý trả lời:** Chưa. Cần kết hợp chính sách lấy dữ liệu riêng với quyền sửa phù hợp, chẳng hạn List.copyOf nếu các điều kiện dữ liệu của nó phù hợp. Vẫn phải xét các object phần tử.

## 12. Tài liệu đối chiếu

- [Collection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html): view, collection không sửa được và chính sách đồng bộ.
- [ArrayList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): danh sách quản lý cấu trúc riêng và constructor chép Collection.
- [List.subList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)): view miền và điều kiện sửa cấu trúc của nguồn.
- [List.copyOf — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): kết quả không phản ánh sửa cấu trúc nguồn, null và khả năng tái sử dụng.
- [Collections.unmodifiableList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): view chỉ đọc của List.
- [Collections.unmodifiableMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): chặn sửa map trực tiếp và qua các collection view.
- [Map — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): keySet, values, entrySet và hợp đồng của các view ánh xạ.
- [Arrays.asList — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): List cố định kích thước gắn với mảng.
