# clone, serialization và giới hạn của từng cách sao chép

## 1. Muốn “một bản khác” thì khác ở những chỗ nào?

Một danh sách chứa các giỏ hàng. Mỗi giỏ hàng lại giữ danh sách sản phẩm và thông tin giao nhận. Khi tạo bản sao danh sách để thử chỉnh sửa, việc có một đối tượng List mới chưa đủ để bảo đảm giỏ hàng gốc không đổi.

Điểm xuất phát của bài này là **đồ thị đối tượng**:

- Mỗi đối tượng là một nút.
- Trường tham chiếu, phần tử trong collection và khóa/giá trị của map tạo ra các liên kết.
- Biến đang có chỉ giữ một tham chiếu đến nút đầu vào, thường gọi là gốc của đồ thị.
- Hai liên kết có thể trỏ đến cùng một nút; một chuỗi liên kết cũng có thể quay về nút đã đi qua.

Vì vậy, “sao chép” cần có một phạm vi rõ ràng:

| Mức độ | Có gì mới? | Còn dùng chung gì? |
|---|---|---|
| Gán một tham chiếu sang biến khác | Chỉ có biến khác | Cùng đối tượng gốc |
| Sao chép nông (shallow copy) | Đối tượng hoặc cấu trúc chứa bên ngoài | Các đối tượng được tham chiếu bên trong |
| Sao chép sâu theo hợp đồng | Những nút được quy định phải tách trong đồ thị | Có thể vẫn dùng chung dữ liệu bất biến, dịch vụ hoặc đối tượng được quy định dùng chung |
| Chuyển đổi sang mô hình dữ liệu khác | Các đối tượng của mô hình đích | Chỉ giữ phần thông tin mà phép chuyển đổi định nghĩa |

**clone() không mặc định sao chép sâu. Serialization cũng không phải cam kết nhân bản độc lập mọi trạng thái đang có.** Mỗi cách có quy tắc và điều kiện riêng.

Trước khi chọn, hãy trả lời ba câu hỏi: thao tác nào ở bản sao được phép ảnh hưởng nguồn, liên kết dùng chung nào phải được giữ trong bản sao, và trạng thái nào không thể hoặc không nên mang sang?

Bài học tập trung vào sao chép collection cùng đồ thị được chứa bên trong, không thiết kế một giao thức lưu trữ tổng quát. Bốn chương trình đầy đủ dùng Java 17 trở lên, chỉ dùng thư viện chuẩn. Các kết quả được in bằng giá trị và so sánh tham chiếu, tránh phụ thuộc địa chỉ đối tượng hay thứ tự duyệt của HashMap.

## 2. Object.clone() và Cloneable: cơ chế cơ bản

### 2.1. Cloneable là dấu hiệu cho Object.clone(), không phải API sao chép chung

Object khai báo phương thức clone() với quyền protected và kiểu trả về Object. Cloneable là một interface đánh dấu, không khai báo phương thức clone().

Điều này dẫn đến hai khác biệt:

- Lớp triển khai Cloneable nhưng không công khai một phương thức phù hợp thì nơi gọi bên ngoài vẫn chưa có API clone() công khai.
- Một biến có kiểu Cloneable không thể chỉ dựa vào interface đó để gọi clone() như gọi một phương thức trong hợp đồng interface.

Theo cách dùng thông thường, lớp hỗ trợ clone sẽ ghi đè clone(), tăng quyền truy cập thành public khi muốn công khai, và có thể dùng kiểu trả về cụ thể của lớp.

Nếu thực thi Object.clone() trên đối tượng không triển khai Cloneable, nó ném CloneNotSupportedException. Đây là điều kiện của cơ chế Object.clone(); một phương thức tự viết có tên clone nhưng không dùng cơ chế đó còn có thể định nghĩa chính sách khác. Tài liệu [Cloneable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html) giải thích rõ vai trò đánh dấu và việc interface không khai báo clone().

### 2.2. Object.clone() sao chép từng trường như phép gán

Đối với cách triển khai của Object:

- Giá trị kiểu nguyên thủy được chép sang trường tương ứng.
- Giá trị của trường tham chiếu cũng được chép, nghĩa là bản sao giữ tham chiếu tới cùng đối tượng bên trong.
- Các đối tượng được tham chiếu không tự được clone tiếp.
- Không chạy constructor và bộ khởi tạo trường của lớp để tạo lại trạng thái như khi dùng new theo cách thông thường.
- Một trường instance được đánh dấu transient vẫn được chép bởi cơ chế clone; transient có ý nghĩa khác trong serialization.

Hãy hình dung một đối tượng có int count và List<Item> items. Sau super.clone(), count là một giá trị riêng trên đối tượng mới, còn items ở hai phía vẫn chỉ cùng một danh sách.

Để tạo bản sao sâu bằng clone, lớp phải chủ động thay các tham chiếu cần tách sau super.clone(), đồng thời xử lý quan hệ dùng chung và vòng tham chiếu đúng chính sách. [Object.clone](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()) mô tả phép sao chép từng trường; nó không làm bước đệ quy ấy thay lớp.

### 2.3. Đối tượng mới không đồng nghĩa equals hoặc tài nguyên mới

Thông lệ clone thường tạo đối tượng khác tham chiếu và cùng lớp chạy với nguồn. Tuy vậy, không dùng một tên phương thức đơn lẻ để suy ra mọi thuộc tính của kết quả. Cần đọc hợp đồng của chính lớp.

Cũng không có yêu cầu chung rằng bản clone luôn equals nguồn. Nếu lớp chưa ghi đè equals(), hai đối tượng khác tham chiếu thường không bằng nhau theo equals() của Object.

Một tham chiếu tới kết nối cơ sở dữ liệu, luồng nhập/xuất hoặc dịch vụ không trở thành tài nguyên độc lập chỉ vì đối tượng chứa nó được clone. Sao chép tài nguyên bên ngoài phải có chính sách riêng.

## 3. Clone của collection và mảng: tách lớp chứa, còn chung phần tử

ArrayList.clone() tạo một ArrayList mới với các phần tử vẫn là những tham chiếu cũ. HashMap.clone() tạo map mới nhưng không clone khóa hoặc giá trị. Đây là sao chép nông ở cấp cấu trúc chứa.

Chương trình dưới đây dùng các Box có trường value thay đổi được. Key là record chỉ chứa String để việc kiểm tra map không bị nhiễu bởi vấn đề khóa thay đổi mã băm.

Tệp **CollectionCloneDemo.java**:

```java
import java.util.ArrayList;
import java.util.HashMap;

public class CollectionCloneDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    record Key(String id) {}

    @SuppressWarnings("unchecked")
    private static ArrayList<Box> cloneList(ArrayList<Box> source) {
        return (ArrayList<Box>) source.clone();
    }

    @SuppressWarnings("unchecked")
    private static HashMap<Key, Box> cloneMap(HashMap<Key, Box> source) {
        return (HashMap<Key, Box>) source.clone();
    }

    public static void main(String[] args) {
        ArrayList<Box> source = new ArrayList<>();
        source.add(new Box(10));
        ArrayList<Box> copy = cloneList(source);
        System.out.println("newList=" + (copy != source));
        System.out.println("sharedElement=" + (copy.get(0) == source.get(0)));

        copy.add(new Box(20));
        System.out.println("listSizes=" + source.size() + "," + copy.size());
        copy.get(0).value = 99;
        System.out.println("originalAfterElementEdit=" + source.get(0).value);
        copy.set(0, new Box(7));
        System.out.println("afterReplace=" +
                source.get(0).value + "," + copy.get(0).value);

        Key key = new Key("K");
        HashMap<Key, Box> map = new HashMap<>();
        map.put(key, new Box(50));
        HashMap<Key, Box> mapCopy = cloneMap(map);
        System.out.println("sharedKey=" +
                (mapCopy.keySet().iterator().next() == key));
        System.out.println("sharedValue=" + (mapCopy.get(key) == map.get(key)));
        mapCopy.get(key).value = 66;
        mapCopy.remove(key);
        System.out.println("mapSizes=" + map.size() + "," + mapCopy.size());
        System.out.println("originalMapValue=" + map.get(key).value);

        int[] numbers = {10, 20};
        int[] numbersCopy = numbers.clone();
        numbersCopy[0] = 90;
        System.out.println("primitiveArray=" + numbers[0] + "," + numbersCopy[0]);

        Box[] objects = {new Box(3)};
        Box[] objectsCopy = objects.clone();
        objectsCopy[0].value = 4;
        System.out.println("objectArrayShared=" + (objects[0] == objectsCopy[0]));
        System.out.println("objectArrayOriginal=" + objects[0].value);

        int[][] matrix = {{1, 2}, {3, 4}};
        int[][] matrixCopy = matrix.clone();
        matrixCopy[0][0] = 8;
        System.out.println("newOuterArray=" + (matrix != matrixCopy));
        System.out.println("sharedRow=" + (matrix[0] == matrixCopy[0]));
        System.out.println("matrixOriginal=" + matrix[0][0]);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CollectionCloneDemo.java
java CollectionCloneDemo
```

Stdout chính xác:

```text
newList=true
sharedElement=true
listSizes=1,2
originalAfterElementEdit=99
afterReplace=99,7
sharedKey=true
sharedValue=true
mapSizes=1,0
originalMapValue=66
primitiveArray=10,90
objectArrayShared=true
objectArrayOriginal=4
newOuterArray=true
sharedRow=true
matrixOriginal=8
```

### 3.1. Thêm, thay phần tử và sửa phần tử là ba việc khác nhau

Hai list có cấu trúc riêng nên copy.add(...) làm kích thước bản sao tăng mà không thêm vào nguồn. Tuy nhiên, copy.get(0) ban đầu vẫn là Box của nguồn.

Bởi vậy copy.get(0).value = 99 thay chính đối tượng Box đang được cả hai list giữ. Sau đó copy.set(0,new Box(7)) chỉ thay tham chiếu ở một vị trí của list copy; nó không thay tham chiếu ở list source. Kết quả hai bên lúc này là 99 và 7.

Ở map, mapCopy.get(key).value = 66 sửa giá trị dùng chung. mapCopy.remove(key) chỉ xóa ánh xạ của bản sao. Ánh xạ của nguồn vẫn tồn tại với Box đã có value bằng 66.

Các kết quả này minh họa đúng hợp đồng sao chép nông của [ArrayList.clone](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#clone()) và [HashMap.clone](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html#clone()).

### 3.2. Mảng nguyên thủy và mảng tham chiếu

Mảng có hỗ trợ clone; kiểu trả về của clone trên một kiểu mảng cụ thể là chính kiểu mảng đó. Không cần ép Object về int[] hoặc Box[] khi gọi trực tiếp như ví dụ.

int[] chứa giá trị int, nên clone tạo mảng khác và sửa số trong mảng mới không sửa số trong mảng cũ.

Box[] chứa tham chiếu, nên mảng mới vẫn trỏ tới các Box cũ. int[][] cũng là mảng chứa tham chiếu đến các hàng int[]. Vì vậy clone() trên int[][] chỉ tách mảng ngoài; các hàng vẫn dùng chung.

Nếu một ma trận thật sự là các hàng độc lập và muốn tách mọi hàng, có thể sao chép từng hàng theo chính sách của ứng dụng. Nhưng nếu nhiều vị trí cố ý trỏ cùng một hàng, clone từng hàng một cách độc lập sẽ làm mất quan hệ dùng chung đó. Ngay cả “mảng hai chiều” cũng cần hiểu hình dạng đồ thị.

### 3.3. Không nâng hỗ trợ clone của một lớp thành bảo đảm của Collection

Các interface Collection, List, Set và Map không cung cấp một phương thức clone() công khai chung. Một biến khai báo List không tự có clone chỉ vì đối tượng lúc chạy có thể là ArrayList.

Một lớp cụ thể hỗ trợ clone cũng không có nghĩa mọi view, lớp bọc hoặc kết quả trả về từ một factory có cùng khả năng. Không ép kiểu một đối tượng không biết rõ sang ArrayList chỉ để dùng clone.

Với yêu cầu sao chép cấu trúc thông thường, constructor nhận collection/map hoặc factory sao chép tường minh thường dễ biểu đạt hơn. Chúng cũng cần được đọc đúng hợp đồng: tạo cấu trúc mới không tự sao chép sâu từng đối tượng.

## 4. Sao chép sâu phải giữ đúng quan hệ giữa các đối tượng

Giả sử root có hai liên kết cùng trỏ đến child, còn child trỏ lại root. Có hai yêu cầu đồng thời:

1. Bản sao phải có root và child riêng để có thể sửa độc lập.
2. Hai liên kết ở root mới vẫn phải cùng chỉ đến một child mới; đường quay lại phải đến root mới.

Nếu chỉ viết một hàm đệ quy “gặp đối tượng nào thì new đối tượng đó”, nó có thể lặp vô hạn ở chu trình hoặc tạo nhiều bản sao cho cùng một nút, làm mất quan hệ ban đầu.

Bảng ánh xạ **tham chiếu nguồn → tham chiếu đích đã tạo** giải quyết cả hai vấn đề. Dùng IdentityHashMap để nhận diện cùng đối tượng bằng ==, thay vì gộp các đối tượng khác nhau chỉ vì equals() trả true.

### 4.1. Chương trình giữ tham chiếu trùng và vòng tham chiếu

Node bên dưới có một clone công khai, dùng super.clone() để minh họa sao chép nông. Hàm deepCopy() là phép sao chép được viết riêng cho mô hình Node; nó không dùng serialization và không gọi clone cho từng nút.

Tệp **GraphCopyDemo.java**:

```java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;

public class GraphCopyDemo {
    static final class Node implements Cloneable {
        String name;
        final List<Node> links = new ArrayList<>();

        Node(String name) {
            this.name = name;
        }

        @Override
        public Node clone() {
            try {
                return (Node) super.clone();
            } catch (CloneNotSupportedException impossible) {
                throw new AssertionError(impossible);
            }
        }
    }

    private static Node deepCopy(Node source) {
        return copy(source, new IdentityHashMap<>());
    }

    private static Node copy(Node source, IdentityHashMap<Node, Node> seen) {
        if (source == null) {
            return null;
        }
        Node existing = seen.get(source);
        if (existing != null) {
            return existing;
        }

        Node target = new Node(source.name);
        seen.put(source, target);
        for (Node link : source.links) {
            target.links.add(copy(link, seen));
        }
        return target;
    }

    public static void main(String[] args) {
        Node root = new Node("root");
        Node child = new Node("child");
        root.links.add(child);
        root.links.add(child);
        child.links.add(root);

        Node shallow = root.clone();
        System.out.println("shallowNewRoot=" + (shallow != root));
        System.out.println("shallowSharedList=" + (shallow.links == root.links));
        System.out.println("shallowCycleUsesOriginal=" +
                (shallow.links.get(0).links.get(0) == root));

        Node deep = deepCopy(root);
        Node copiedChild = deep.links.get(0);
        System.out.println("deepNewRoot=" + (deep != root));
        System.out.println("deepNewList=" + (deep.links != root.links));
        System.out.println("deepNewChild=" + (copiedChild != child));
        System.out.println("aliasPreserved=" +
                (deep.links.get(0) == deep.links.get(1)));
        System.out.println("cyclePreserved=" + (copiedChild.links.get(0) == deep));

        copiedChild.name = "child-copy";
        deep.links.add(null);
        System.out.println("names=" + child.name + "," + copiedChild.name);
        System.out.println("linkCounts=" + root.links.size() + "," + deep.links.size());
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 GraphCopyDemo.java
java GraphCopyDemo
```

Stdout chính xác:

```text
shallowNewRoot=true
shallowSharedList=true
shallowCycleUsesOriginal=true
deepNewRoot=true
deepNewList=true
deepNewChild=true
aliasPreserved=true
cyclePreserved=true
names=child,child-copy
linkCounts=2,3
```

### 4.2. Đăng ký nút mới trước khi đi theo liên kết

Hàm copy() làm bốn việc theo đúng thứ tự:

1. Trả null nếu liên kết nguồn là null.
2. Nếu nút nguồn đã có trong bảng seen, trả đúng nút đích tương ứng.
3. Tạo nút đích rồi đưa vào seen ngay lập tức.
4. Sau đó mới sao chép các liên kết của nút nguồn.

Bước thứ ba phải đi trước đệ quy. Khi child trỏ lại root, bảng đã biết root mới là đối tượng nào; hàm không tạo root lần nữa và không đệ quy vô hạn.

Hai liên kết cùng đến child cũng gặp cùng một mục trong seen, nên aliasPreserved bằng true. Đây là giữ quan hệ cùng trỏ một đối tượng trong đồ thị mới, không phải giữ liên kết trở về đối tượng mutable ở nguồn.

[IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html) nêu việc biến đổi đồ thị và sao chép sâu bảo toàn quan hệ tham chiếu là một trường hợp sử dụng điển hình.

### 4.3. final không làm danh sách trở nên bất biến

Node.links là final, nghĩa là không thể gán một danh sách khác vào trường đó sau khi được khởi tạo theo quy tắc thông thường. Nội dung danh sách vẫn có thể thêm, xóa hoặc sửa.

super.clone() chép tham chiếu của trường final này. shallow.links và root.links vì thế là cùng một danh sách. Nếu trong một bản clone nông mà gọi links.clear() với ý định “làm sạch trước khi chép lại”, sẽ xóa luôn danh sách của nguồn.

Hàm deepCopy() dùng new Node(...) nên constructor tạo danh sách riêng ngay từ đầu. Nó không phải dùng thủ thuật phản chiếu để đổi một trường final của bản clone.

Đây là một lý do chọn constructor/factory sao chép tường minh khi thiết kế lớp mới: khởi tạo đối tượng đích và các bất biến có thể đọc được ngay trong code.

### 4.4. Phạm vi của thuật toán phải được công khai

GraphCopyDemo chỉ biết mô hình Node gồm tên String và các liên kết Node. Nó chủ động dùng chung String vì String bất biến. Nó không phải hàm sao chép mọi đối tượng Java, không xử lý tự động tài nguyên hệ điều hành, mọi kiểu con hoặc bất kỳ trường mới nào được thêm về sau.

Nếu Node có thêm thuộc tính mutable, người thiết kế phải quyết định sao chép, dùng chung, bỏ qua hay tính lại thuộc tính đó. Nếu cần giữ quan hệ giữa nhiều gốc, phải dùng chung một bảng seen cho toàn bộ nhóm gốc cần sao chép; mỗi lần tạo bảng mới là một đồ thị sao chép riêng.

Với đồ thị rất sâu, cách đệ quy có thể vượt ngăn xếp. Một thuật toán dùng hàng đợi/ngăn xếp tường minh có thể cần thiết khi quy mô dữ liệu yêu cầu. “Có bảng đã gặp” giải quyết chu trình, không tự bảo đảm độ sâu đệ quy vô hạn.

## 5. Serialization: mã hóa đồ thị rồi dựng lại

Java Object Serialization dùng ObjectOutputStream để ghi trạng thái thành byte và ObjectInputStream để đọc lại. Khi dùng nó để sao chép, thường có quy trình:

1. Ghi một gốc đối tượng vào bộ đệm byte.
2. Tạo luồng đọc mới từ các byte đó.
3. Đọc gốc được dựng lại và kiểm tra kiểu mong đợi.

Đây là sao chép thông qua **hợp đồng biểu diễn tuần tự hóa**, không phải chụp nguyên trạng bộ nhớ của JVM.

### 5.1. Cơ chế giữ tham chiếu trong một luồng

Với các đối tượng serializable thông thường, luồng ghi theo dõi những đối tượng đã gặp và cấp định danh nội bộ cho chúng. Gặp lại cùng một đối tượng, nó có thể ghi liên kết tới định danh đã có thay vì ghi một bản độc lập khác.

Khi đọc lại, cơ chế này giữ được nhiều liên kết cùng trỏ một đối tượng và các chu trình trong đồ thị thông thường. Nó không tự nhân đôi một nút chỉ vì có hai đường dẫn tới nút đó.

Đặc tả [kiến trúc Java Object Serialization](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html) mô tả cách dùng định danh để tái tạo quan hệ dùng chung và vòng tham chiếu. Các ngoại lệ do kiểu đặc biệt hoặc cơ chế thay thế đối tượng sẽ được xét ở phần giới hạn.

### 5.2. Serializable của đối tượng gốc chưa đủ

Serializable cũng là interface đánh dấu. Theo cơ chế mặc định, các trường instance không static và không transient của lớp serializable tham gia trạng thái được ghi. Phần được ghi có thể được tùy biến bằng các cơ chế serialization riêng của lớp.

Một ArrayList triển khai Serializable không làm mọi phần tử bất kỳ trong nó trở nên serializable. Khi cơ chế đi tới một đối tượng không hỗ trợ cần được ghi, có thể nhận NotSerializableException. Điều tương tự xảy ra với khóa, giá trị, Comparator hoặc cấu hình được đồ thị tham chiếu tới.

Ngay cả một hàm generic dạng T extends Serializable cũng chỉ kiểm tra được kiểu gốc qua hệ kiểu; nó không chứng minh mọi nút thực tế được duyệt đều hợp lệ. Cần hiểu mô hình cụ thể và xử lý lỗi lúc chạy.

Đánh dấu một trường transient có thể loại nó khỏi cơ chế mặc định, nhưng đó là quyết định bỏ hoặc dựng lại trạng thái, không phải đã sao chép thành công trạng thái ấy.

## 6. Chương trình: sao chép đồ thị và thấy phần trạng thái bị thay đổi

Ví dụ sau có hai Node với một vòng tham chiếu và hai liên kết trùng tới child. Nó còn có:

- cache là trường transient có giá trị khởi tạo.
- global là trường static.
- inherited thuộc Base không triển khai Serializable.
- policy là enum.
- token có readResolve() trả lại một đối tượng dùng chung.

Chương trình chỉ đọc byte vừa tự tạo trong bộ nhớ. Bộ lọc luồng đọc giới hạn những lớp và quy mô cần cho chính ví dụ này; đây không phải hàm tiếp nhận byte tùy ý từ bên ngoài.

Tệp **SerializationCopyDemo.java**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class SerializationCopyDemo {
    static class Base {
        static int constructions;
        int inherited = 7;

        Base() {
            constructions++;
        }
    }

    enum Policy { STANDARD }

    static final class Token implements Serializable {
        private static final long serialVersionUID = 1L;
        static final Token INSTANCE = new Token();

        private Token() {}

        private Object readResolve() {
            return INSTANCE;
        }
    }

    static final class Node extends Base implements Serializable {
        private static final long serialVersionUID = 1L;
        static int constructions;
        static String global = "before";

        String name;
        List<Node> links = new ArrayList<>();
        transient String cache = "warm";
        Policy policy = Policy.STANDARD;
        Token token = Token.INSTANCE;

        Node(String name) {
            constructions++;
            this.name = name;
        }
    }

    private static byte[] serialize(Serializable source) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(source);
        }
        return buffer.toByteArray();
    }

    private static ObjectInputFilter.Status filter(ObjectInputFilter.FilterInfo info) {
        if (info.depth() > 20 || info.references() > 1000 ||
                info.arrayLength() > 1000 || info.streamBytes() > 1_000_000) {
            return ObjectInputFilter.Status.REJECTED;
        }
        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }
        if (type == Node.class || type == Token.class ||
                type == Policy.class || type == Enum.class ||
                type == ArrayList.class || type == Object[].class ||
                type == String.class) {
            return ObjectInputFilter.Status.ALLOWED;
        }
        return ObjectInputFilter.Status.REJECTED;
    }

    private static Node readLocalBytes(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in =
                new ObjectInputStream(new ByteArrayInputStream(bytes))) {
            in.setObjectInputFilter(SerializationCopyDemo::filter);
            return Node.class.cast(in.readObject());
        }
    }

    public static void main(String[] args) throws Exception {
        Node root = new Node("root");
        Node child = new Node("child");
        root.links.add(child);
        root.links.add(child);
        child.links.add(root);
        root.inherited = 99;

        byte[] bytes = serialize(root);
        Base.constructions = 0;
        Node.constructions = 0;
        Node.global = "changed-after-write";
        Node copy = readLocalBytes(bytes);

        System.out.println("newRoot=" + (copy != root));
        System.out.println("newChild=" + (copy.links.get(0) != child));
        System.out.println("aliasPreserved=" +
                (copy.links.get(0) == copy.links.get(1)));
        System.out.println("cyclePreserved=" +
                (copy.links.get(0).links.get(0) == copy));
        System.out.println("cache=" + copy.cache);
        System.out.println("global=" + Node.global);
        System.out.println("inherited=" + copy.inherited);
        System.out.println("baseConstructors=" + Base.constructions);
        System.out.println("nodeConstructors=" + Node.constructions);
        System.out.println("sameEnum=" + (copy.policy == root.policy));
        System.out.println("sameResolvedToken=" + (copy.token == root.token));

        copy.links.get(0).name = "child-copy";
        System.out.println("names=" + child.name + "," + copy.links.get(0).name);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SerializationCopyDemo.java
java SerializationCopyDemo
```

Stdout chính xác:

```text
newRoot=true
newChild=true
aliasPreserved=true
cyclePreserved=true
cache=null
global=changed-after-write
inherited=7
baseConstructors=2
nodeConstructors=0
sameEnum=true
sameResolvedToken=true
names=child,child-copy
```

### 6.1. Các nút thường được tách, quan hệ trong đồ thị được giữ

copy khác root; child trong copy cũng khác child gốc. Tuy vậy, hai vị trí trong copy.links cùng trỏ tới một child mới. Liên kết từ child mới quay về chính copy.

Sửa tên child ở bản sao không sửa tên ở nguồn. Đây là phần hành vi thường khiến serialization được dùng như một cách sao chép sâu cho các mô hình đã hỗ trợ nó.

Nhưng chính chương trình cũng cho thấy không thể kết luận “mọi trạng thái đều độc lập” chỉ từ việc gốc và child đã được tạo mới.

### 6.2. transient và static không đi theo cơ chế mặc định

cache được khai báo transient và không có code khôi phục riêng. Giá trị warm được khởi tạo khi gọi constructor Node ở chương trình gốc, nhưng phần khởi tạo của lớp Node không chạy lại theo cách new Node(...) trong lần đọc này. cache của bản đọc lại là null.

Nếu cần cache sau khi đọc, phải tính lại khi dùng hoặc khôi phục bằng cơ chế phù hợp. Không hiểu transient là “tự đặt lại về giá trị viết ở khai báo trường”.

global là static, thuộc lớp trong JVM, không phải trạng thái riêng của mỗi Node. Sau khi đổi thành changed-after-write rồi đọc byte, nó vẫn là changed-after-write. Dữ liệu đã ghi không phục hồi giá trị before cho biến static này.

Tương phản đáng nhớ: clone nông chép cả giá trị của trường instance transient; serialization mặc định bỏ trường đó. Từ khóa transient không phải một chỉ dẫn chung cho mọi kiểu sao chép.

### 6.3. Phần lớp cha không serializable được khởi tạo lại

Base không triển khai Serializable. Trạng thái inherited = 99 của root không được ghi tự động như trạng thái của Node. Khi dựng lại hai Node, constructor không đối số của Base được gọi cho mỗi đối tượng, làm inherited trở lại 7 và bộ đếm Base tăng lên 2.

Constructor Node không chạy, nên bộ đếm Node vẫn là 0. Cần đọc cả hai dòng, không nói chung rằng “deserialization không gọi constructor nào”.

Với lớp Serializable thông thường, constructor không đối số của lớp cha không serializable đầu tiên phải truy cập được theo quy tắc dành cho lớp con. Nếu không có điều kiện này, quá trình dựng lại có thể thất bại. Hợp đồng này được mô tả ở [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html).

### 6.4. readResolve và enum giữ đối tượng được quy định dùng chung

Token.readResolve() trả Token.INSTANCE. Kết quả đọc cho trường token vì thế trỏ lại singleton đã có; sameResolvedToken bằng true.

policy là enum. Trong cùng định nghĩa kiểu enum đã được nạp, đọc lại hằng enum nhận chính hằng tương ứng, không tạo một bản enum độc lập như một Node thông thường; sameEnum cũng bằng true.

Việc dùng chung enum bất biến thường đúng mong muốn. Nhưng nếu một lớp có readResolve() trả một singleton mutable, bản đọc lại có thể tiếp tục dùng chung trạng thái thay đổi được qua singleton ấy.

Do đó kết luận phù hợp là: serialization tái tạo đồ thị **theo giao thức của các lớp tham gia**, bao gồm quy tắc thay thế và dùng chung của chúng. Nó không bảo đảm “mọi đối tượng reachable đều khác tham chiếu so với nguồn”.

## 7. Constructor, bất biến và các cơ chế tùy biến

### 7.1. Không dùng constructor thông thường làm bằng chứng đã kiểm tra dữ liệu

Một lớp có constructor kiểm tra giá trị hợp lệ không tự có nghĩa đọc Serializable thông thường sẽ chạy lại chính constructor ấy. Nếu một bất biến cần được duy trì sau khi đọc, thiết kế serialization của lớp phải có bước kiểm tra/khôi phục thích hợp.

Lớp có thể định nghĩa readObject() để đọc trạng thái, kiểm tra điều kiện và từ chối dữ liệu không hợp lệ, chẳng hạn bằng InvalidObjectException. Một số thiết kế dùng mẫu đại diện tuần tự hóa để dựng lại qua một đường khởi tạo được kiểm soát.

Không thêm readObject một cách máy móc: thứ tự đọc, trạng thái đang được khôi phục, quan hệ với lớp cha và vòng tham chiếu đều cần được xem xét. Với nhu cầu sao chép dữ liệu ứng dụng mới, một factory/constructor sao chép rõ ràng có thể đơn giản hơn việc mở thêm một đường dựng đối tượng bằng serialization.

### 7.2. writeObject, writeReplace và readResolve làm thay đổi ý nghĩa sao chép

Các lớp có thể ghi/đọc trạng thái tùy biến qua writeObject()/readObject(), thay đối tượng được ghi bằng writeReplace(), hoặc thay kết quả đọc bằng readResolve().

Điều này có nghĩa:

- Không phải mọi trường transient đều nhất định bị mất; lớp có thể ghi hoặc dựng lại thông tin liên quan bằng code riêng.
- Không phải mọi trường không transient đều được sao chép đúng theo cách nhìn trực tiếp vào trường; biểu diễn tuần tự hóa có thể được tùy biến.
- Không phải mọi đối tượng đọc ra đều có quan hệ tham chiếu như một bản nhân đôi thuần túy của nguồn.
- Code của các lớp tham gia có thể chạy trong khi ghi và đọc.

Hãy đánh giá hợp đồng của **toàn bộ mô hình tham gia**, không chỉ việc đối tượng gốc có implements Serializable.

Đặc tả [luồng ghi](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/output.html) và [luồng đọc](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html) phân định các điểm tùy biến này.

### 7.3. Externalizable, enum và record có quy tắc riêng

Externalizable mở rộng Serializable nhưng giao trách nhiệm ghi/đọc cho writeExternal()/readExternal(). Khi dựng lại, nó dùng constructor public không đối số rồi gọi readExternal(). Không áp nguyên quy tắc “constructor lớp serializable không chạy” của lớp thông thường sang trường hợp này. Xem [Externalizable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Externalizable.html).

Record có thể triển khai Serializable; khi đọc, constructor chuẩn tắc của record được dùng để tạo đối tượng từ các thành phần. Một vòng tham chiếu đi qua thành phần của record cũng không được bảo toàn như chu trình của lớp thông thường trong GraphCopyDemo hoặc SerializationCopyDemo.

Enum có cách xử lý riêng theo tên hằng. Các phương thức tùy biến serialization không có cùng tác dụng như với lớp thông thường. Vì vậy không tổng quát kết quả constructor hoặc chu trình của một ví dụ cho mọi kiểu dữ liệu Java.

Các khác biệt của [record và vòng tham chiếu](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html#serialization-of-records) là một giới hạn thực tế khi cân nhắc dùng serialization làm công cụ sao chép tổng quát.

## 8. Chương trình kiểm chứng lỗi và việc dùng lại một luồng

SerializationLimitsDemo giải quyết bốn hiểu nhầm:

1. Collection serializable thì mọi phần tử cũng ghi được.
2. Comparator dùng được cho cây thì đương nhiên ghi được.
3. Ghi cùng một đối tượng lần nữa luôn tạo ảnh chụp mới.
4. Bộ lọc không cho phép kiểu vẫn có thể bị bỏ qua chỉ vì sau đó ép kiểu đúng.

Tệp **SerializationLimitsDemo.java**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.NotSerializableException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.TreeMap;

public class SerializationLimitsDemo {
    static final class Box implements Serializable {
        private static final long serialVersionUID = 1L;
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    private static byte[] serialize(Object source) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(source);
        }
        return buffer.toByteArray();
    }

    private static void expectNotSerializable(String label, Object source)
            throws IOException {
        try {
            serialize(source);
            throw new AssertionError(label + ": no exception");
        } catch (NotSerializableException expected) {
            System.out.println(label + "=NotSerializableException");
        }
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        expectNotSerializable("badElement",
                new ArrayList<>(List.of(new Object())));

        Comparator<Integer> order = (a, b) -> Integer.compare(b, a);
        TreeMap<Integer, String> tree = new TreeMap<>(order);
        tree.put(1, "one");
        tree.put(2, "two");
        TreeMap<Integer, String> treeClone =
                (TreeMap<Integer, String>) tree.clone();
        System.out.println("cloneOrder=" + treeClone.navigableKeySet());
        System.out.println("sharedComparator=" +
                (treeClone.comparator() == tree.comparator()));
        expectNotSerializable("badComparator", tree);

        Box original = new Box(10);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(original);
            original.value = 20;
            out.writeObject(original);
            out.reset();
            out.writeObject(original);
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(buffer.toByteArray()))) {
            in.setObjectInputFilter(ObjectInputFilter.Config.createFilter(
                    "maxdepth=10;maxrefs=100;maxbytes=100000;" +
                    "SerializationLimitsDemo$Box;!*"));
            Box first = (Box) in.readObject();
            Box second = (Box) in.readObject();
            Box third = (Box) in.readObject();
            System.out.println("sameWithoutReset=" + (first == second));
            System.out.println("valuesWithoutReset=" +
                    first.value + "," + second.value);
            System.out.println("newAfterReset=" + (third != first));
            System.out.println("valueAfterReset=" + third.value);
        }

        byte[] local = serialize(new Box(1));
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(local))) {
            in.setObjectInputFilter(info -> ObjectInputFilter.Status.REJECTED);
            in.readObject();
            throw new AssertionError("filter did not reject");
        } catch (InvalidClassException expected) {
            System.out.println("filter=InvalidClassException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SerializationLimitsDemo.java
java SerializationLimitsDemo
```

Stdout chính xác:

```text
badElement=NotSerializableException
cloneOrder=[2, 1]
sharedComparator=true
badComparator=NotSerializableException
sameWithoutReset=true
valuesWithoutReset=10,10
newAfterReset=true
valueAfterReset=20
filter=InvalidClassException
```

### 8.1. Cấu trúc chứa hợp lệ, phần được duyệt không hợp lệ

ArrayList trong chương trình chứa new Object(). ArrayList hỗ trợ Serializable nhưng Object này không hỗ trợ, nên ghi cả đồ thị bị NotSerializableException.

Comparator của tree là lambda chỉ được gán vào Comparator<Integer>, không phải một kiểu đích yêu cầu Serializable. Nó hoạt động khi so sánh và vẫn được dùng chung bởi treeClone, nhưng không ghi được theo ví dụ này. Serialization tree vì thế cũng thất bại.

Đổi lambda sang một Comparator được thiết kế có hỗ trợ Serializable có thể giải quyết riêng lỗi khả năng ghi của đối tượng đó; vẫn phải kiểm tra trạng thái mà Comparator giữ và hợp đồng tương thích. Không đánh dấu Serializable như một cách làm dữ liệu tùy ý tự trở nên sao chép được.

Một bản clone cây có thể giữ Comparator cũ mà không cần ghi thành byte. Vì vậy điều kiện thành công của clone và serialization khác nhau. Với Comparator thay đổi được, việc clone dùng chung Comparator cũng là một liên kết phải đưa vào đánh giá mức độ độc lập.

### 8.2. Luồng ghi có bảng đối tượng đã gặp

Lần đầu ghi original có value = 10. Sau khi sửa original.value thành 20, lần ghi thứ hai trên cùng ObjectOutputStream vẫn có thể chỉ ghi tham chiếu ngược tới đối tượng đã biết.

Khi đọc, first và second là cùng một đối tượng, cùng value bằng 10. Lần ghi thứ hai không tạo ra một bản chụp mới của trạng thái value = 20.

out.reset() xóa trạng thái theo dõi của luồng tại thời điểm hợp lệ và làm lần ghi sau coi original là đối tượng cần ghi lại. Vì thế third khác first và có value = 20. [ObjectOutputStream.reset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html#reset()) mô tả tác dụng làm mới trạng thái này.

Nếu muốn mỗi lần sao chép là một đồ thị độc lập, cách dễ đọc thường là dùng cặp luồng mới cho mỗi lần sao chép, thay vì vô tình giữ một ObjectOutputStream lâu dài. Nếu cần giữ quan hệ giữa nhiều gốc trong cùng một bản sao, lại phải xác định rõ chúng thuộc cùng lần ghi/đọc nào.

writeUnshared()/readUnshared() có những quy tắc riêng, không phải lối tắt nhân bản độc lập mọi đối tượng con. Không thay một phép gọi rồi bỏ qua quan hệ toàn đồ thị.

### 8.3. Lỗi lọc là một lỗi đọc, không phải lỗi generic

Đoạn cuối tạo byte hợp lệ từ Box, sau đó bộ lọc chủ động từ chối tất cả. readObject() thất bại bằng InvalidClassException; việc luồng có thể chứa đúng kiểu Box không làm nó vượt bộ lọc.

Tên ngoại lệ ở đây được in có chủ đích, không phụ thuộc thông báo hoặc stack trace của từng JDK. Trong thực tế, InvalidClassException cũng có thể liên quan đến bất tương thích lớp; cần xem nguyên nhân/ngữ cảnh để phân loại.

Các lần ghi lỗi được bỏ đi cùng bộ đệm và luồng của chúng. Không coi dữ liệu của một lần serialize đã thất bại là một bản sao một phần có thể dùng tiếp bình thường.

## 9. Giới hạn an toàn khi dùng serialization để sao chép

Serialization có thể gọi code của lớp trong quá trình đọc. Không nhận một mảng byte tùy ý từ nguồn không tin cậy rồi đưa thẳng vào ObjectInputStream chỉ vì mục tiêu được đặt tên là “sao chép”.

Trong các ví dụ, byte được tạo tại chỗ từ mô hình đã biết. Bộ lọc được đặt trước readObject() và giới hạn kiểu/quy mô theo từng ví dụ. Không biến các hàm minh họa thành tiện ích nhận mọi đối tượng hoặc mọi byte.

### 9.1. Bộ lọc cần đúng ngữ cảnh

ObjectInputFilter có thể xem lớp đang được đọc và các chỉ số như độ sâu, số tham chiếu, độ dài mảng và số byte đã đọc. Một danh sách lớp cho phép cùng giới hạn tài nguyên giúp thu hẹp dữ liệu được chấp nhận.

Bộ lọc của SerializationCopyDemo cho phép cả Object[] vì cách đọc ArrayList của JDK có kiểm tra mảng chứa phần tử. Việc cho phép mảng ấy không cho phép mọi lớp phần tử tùy ý; những đối tượng bên trong vẫn chịu các lượt kiểm tra phù hợp của luồng.

Danh sách này chỉ dành cho đồ thị minh họa gồm Node, Token, enum và ArrayList. Thay đổi mô hình hoặc cách triển khai cấu trúc có thể đòi hỏi xem lại bộ lọc; không mở rộng thành cho phép toàn bộ thư viện chỉ để “hết lỗi”.

Bộ lọc cũng không thay kiểm tra nghiệp vụ, không bảo đảm mọi nội dung String đã được kiểm tra, và các chỉ số được kiểm tra tại các điểm gọi lọc chứ không biến mọi thao tác thành một hạn mức tuyệt đối tổng quát. Khi thiết kế một biên tiếp nhận dữ liệu, còn phải giới hạn dữ liệu đầu vào, quyền của code chạy và các bất biến cần giữ.

Tài liệu [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html) và [Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html) trình bày cơ chế và các giới hạn sử dụng. Bộ lọc bổ sung lớp bảo vệ; nó không làm deserialization dữ liệu không tin cậy trở thành lựa chọn mặc định.

### 9.2. Kiểm tra kiểu sau readObject không đủ

Node.class.cast(in.readObject()) xác nhận đối tượng gốc sau khi đọc là Node. Nó không chứng minh mọi bước chạy trước đó an toàn và không kiểm tra toàn bộ ý nghĩa nghiệp vụ của các nút con.

Một chữ ký T extends Serializable hay một phép ép kiểu chỉ là một phần hợp đồng. Hợp đồng sao chép còn phải nêu nguồn được tin cậy, lớp được chấp nhận, giới hạn dữ liệu, bất biến và chính sách đối với tài nguyên.

### 9.3. Byte không phải dữ liệu đã mã hóa bảo mật

Serialization chuyển trạng thái thành biểu diễn byte; nó không tự mã hóa để giữ bí mật. Những trường được ghi có thể chứa thông tin nhạy cảm ngay cả khi code không in chúng.

transient loại một trường khỏi cơ chế mặc định, nhưng cùng thông tin có thể tồn tại ở trường/đối tượng khác hoặc được phương thức tùy biến ghi ra. Không dùng transient như chứng minh rằng mọi bản byte chắc chắn không có dữ liệu nhạy cảm.

Nếu chỉ cần sao chép cục bộ, không cần ghi byte ra tệp để rồi đọc lại; bộ đệm trong bộ nhớ đã minh họa được cơ chế. Việc tạo thêm tệp không giải quyết vấn đề mức độ sâu của bản sao.

## 10. Tương thích lớp và serialVersionUID

Một bản serialize thường chứa thông tin về lớp và trạng thái cần đọc lại. Nó không đóng gói toàn bộ mã thực thi của chương trình thành một bản chạy độc lập.

Nơi đọc vẫn cần các lớp phù hợp và khả năng nạp chúng. Thiếu lớp có thể gây ClassNotFoundException. Thay đổi tên, cấu trúc lớp hoặc hợp đồng đọc có thể khiến dữ liệu cũ không dùng được.

Đối với lớp Serializable thông thường, serialVersionUID tham gia kiểm tra tương thích. Các lớp trong ví dụ khai báo rõ:

```java
// Doan khai bao nam ben trong lop Serializable thong thuong.
private static final long serialVersionUID = 1L;
```

UID khác giữa biểu diễn ghi và lớp đọc có thể gây InvalidClassException. Nếu không khai báo rõ, UID được tính từ các chi tiết của lớp và có thể thay đổi khi lớp được sửa theo cách người viết không chủ ý coi là thay đổi dữ liệu.

Nhưng giữ cùng UID **không tự biến mọi thay đổi thành tương thích**. Nó không chuyển kiểu trường tùy ý, không khôi phục logic cũ và không bảo đảm dữ liệu mới đọc lên thỏa bất biến. Tương thích là hợp đồng thiết kế và kiểm thử, không chỉ là một hằng long.

Enum và record có quy tắc riêng, nên không áp toàn bộ kết luận UID của lớp thông thường sang chúng. Bài này không dùng native serialization làm định dạng trao đổi lâu dài; nếu mục tiêu thật là lưu trữ hoặc liên hệ giữa nhiều hệ thống, cần thiết kế định dạng và phiên bản dữ liệu theo mục tiêu đó.

[Đặc tả versioning](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/version.html) mô tả những thay đổi tương thích và không tương thích. Dùng serialization chỉ để sao chép trong cùng lần chạy có thể tránh một số vấn đề phiên bản, nhưng vẫn không tránh được transient, hook tùy biến, chi phí và các giới hạn đồ thị.

## 11. Chi phí và tài nguyên: “ghi rồi đọc” không phải phép gán rẻ

Clone nông của một collection phải tạo cấu trúc chứa mới và chép các tham chiếu cần thiết. Nó không đi sao chép mọi thuộc tính sâu của từng phần tử.

Sao chép thủ công một đồ thị cần tạo những nút được quy định, đi theo các liên kết và có thể giữ bảng đã gặp. Thuật toán của GraphCopyDemo còn cần bộ nhớ cho bảng IdentityHashMap và ngăn xếp đệ quy.

Serialization thêm bước dựng biểu diễn byte, lưu thông tin giao thức, theo dõi tham chiếu, đọc và dựng lại đối tượng. Trong cách dùng bộ đệm, có thể tồn tại đồng thời nguồn, byte trung gian và đồ thị mới; không giả định bộ nhớ đỉnh chỉ bằng kích thước bản sao.

Không có một con số thời gian chung đúng cho mọi collection hoặc mọi đồ thị. Nếu sao chép nằm trên đường xử lý thường xuyên, đo với dữ liệu đại diện, bao gồm kích thước, phần dùng chung, độ sâu và các phương thức tùy biến. Đừng lấy một ví dụ vài nút rồi kết luận serialization có chi phí tương đương clone.

Các tài nguyên bên ngoài cần xét riêng:

| Loại trạng thái | Câu hỏi phải trả lời |
|---|---|
| Kết nối, socket, file đang mở | Bản sao cần mở mới, dùng chung có kiểm soát hay không được mang theo? |
| Cache | Cần chép, bỏ rồi tính lại hay giữ một cache dùng chung? |
| Khóa đồng bộ, luồng, bộ thực thi | Ý nghĩa một “bản sao” là gì và ai sở hữu vòng đời? |
| ID thực thể nghiệp vụ | Bản sao là ảnh chụp cùng thực thể hay một thực thể mới cần ID khác? |
| Callback, listener, dịch vụ | Có nên nhân bản liên kết đó hay chuyển thành dữ liệu thuần? |
| Comparator hoặc chiến lược xử lý | Dùng chung có an toàn không, trạng thái có ghi/đọc được không? |

Không có clone() hay serialization mặc định nào thay người thiết kế trả lời tất cả câu hỏi trên.

## 12. Chọn cách sao chép theo hợp đồng cần đạt

| Nhu cầu | Hướng phù hợp | Điều còn phải kiểm tra |
|---|---|---|
| Chỉ cần một tên biến khác cho cùng đối tượng | Gán tham chiếu | Hai nơi cùng sửa một đối tượng |
| Tách cấu trúc collection, phần tử có thể dùng chung | Constructor/factory sao chép hoặc clone đã được lớp hỗ trợ | Phần tử/khóa/giá trị vẫn có thể dùng chung |
| Tách dữ liệu mutable của một mô hình mình quản lý | Constructor/factory hoặc hàm sao chép theo mô hình | Quan hệ trùng, chu trình, kiểu con, trường mới |
| Giữ quan hệ đồ thị bằng cơ chế serialization sẵn có | Cặp luồng ghi/đọc mới trong ngữ cảnh tin cậy và kiểm soát | Toàn đồ thị, hook, transient, UID, lọc, chi phí |
| Chỉ cần dữ liệu để hiển thị/truyền đi | Ánh xạ sang DTO/mô hình dữ liệu phù hợp | Những thông tin nào được giữ, bỏ hoặc đổi kiểu |
| Chặn sửa cấu trúc qua tham chiếu trả về | Lớp bọc/factory không cho sửa theo hợp đồng | Nguồn có còn liên kết không; phần tử có bất biến không |

Không buộc lớp nghiệp vụ phải triển khai Serializable chỉ để tránh viết vài dòng sao chép có ý nghĩa. Nếu mô hình đã có giao thức Serializable được kiểm soát và đồ thị không lớn, cách ghi/đọc có thể đáp ứng một mục đích cục bộ; cần chấp nhận những giới hạn đã nêu.

Ngược lại, không tự viết đệ quy tùy tiện rồi gọi là sao chép sâu tổng quát. Hàm thủ công chỉ đúng trong phạm vi những kiểu và chính sách mà nó xử lý.

### 12.1. Constructor sao chép và bất biến

Constructor/factory cho phép quyết định tường minh: tạo danh sách mới, tái sử dụng phần tử bất biến, sao chép giá trị mutable, giữ hoặc cấp ID, và bỏ cache. Với lớp có trường final, cách khởi tạo có chủ đích thường thể hiện hợp đồng rõ hơn việc sửa lại kết quả super.clone().

Một constructor nhận List rồi lưu nguyên List ấy chưa phải bản sao cấu trúc. Tên “copy constructor” cũng cần được code thực tế thực hiện đúng. Nếu phần tử thay đổi được, tạo List mới chỉ giải quyết lớp chứa.

### 12.2. JSON hoặc chuyển đổi dữ liệu không tự thay thế serialization

Ghi JSON rồi đọc lại cũng là đi qua một biểu diễn dữ liệu. Nó có thể là lựa chọn đúng cho một mô hình truyền dữ liệu, nhưng không tự giữ kiểu chạy, Comparator, quan hệ cùng tham chiếu hoặc chu trình như Java Object Serialization của lớp thông thường.

Khả năng giữ những thông tin đó phụ thuộc thư viện và cấu hình cụ thể. Không đưa một bước chuyển JSON vào giữa rồi mặc định đã có sao chép sâu đúng với mọi đồ thị.

### 12.3. Collection không cho sửa không đồng nghĩa sao chép sâu

Một collection không cho sửa cấu trúc vẫn có thể chứa đối tượng mutable. Nếu một phần tử được dùng chung, sửa thuộc tính của nó vẫn ảnh hưởng mọi nơi giữ nó.

“Không sửa được qua API này”, “cấu trúc độc lập với nguồn” và “mọi trạng thái bên trong độc lập” là ba thuộc tính cần kiểm tra riêng. Clone nông chỉ đáp ứng một phần; serialization cũng chỉ đáp ứng theo giao thức lớp, không phải cả ba một cách tự động.

## 13. Kiểm thử một bản sao bằng hành vi và tham chiếu

Chỉ in toString() giống nhau hoặc kiểm tra equals() là chưa đủ. Hai collection có thể hiển thị cùng giá trị nhưng vẫn dùng chung phần tử; hai đối tượng sao chép đúng cũng có thể không equals nếu lớp dùng so sánh danh tính.

Một bộ kiểm tra phù hợp với hợp đồng thường xét:

1. **Gốc:** khi yêu cầu đối tượng mới, copy != source.
2. **Cấu trúc chứa:** thêm/xóa/thay vị trí ở copy có ảnh hưởng cấu trúc nguồn không?
3. **Phần tử mutable:** sửa thuộc tính ở copy có làm nguồn đổi không, và điều đó có đúng chính sách không?
4. **Liên kết trùng:** hai đường cùng đến một nút nguồn còn cùng đến một nút đích không?
5. **Vòng tham chiếu:** đường quay lại trỏ tới nút đích đúng hay lẫn nút nguồn?
6. **Dữ liệu bị bỏ/tính lại:** cache, transient và trạng thái lớp cha có kết quả đã định nghĩa không?
7. **Đối tượng cố ý dùng chung:** enum, singleton hoặc dịch vụ có đúng chính sách không?
8. **Lỗi:** phần tử không được hỗ trợ, giới hạn lọc và dữ liệu không tương thích có thất bại rõ ràng không?

Các chương trình trong bài cố tình kiểm tra cả thay đổi cấu trúc và sửa thuộc tính. Đây là hai loại thay đổi khác nhau, thường là nơi bản sao “có vẻ độc lập” bộc lộ liên kết còn sót.

Với nguồn bị nhiều luồng cập nhật, cả clone, thuật toán tự viết và serialization đều không mặc định tạo một ảnh chụp nguyên tử của toàn bộ đồ thị. Cần cơ chế quyền sở hữu, bất biến hoặc đồng bộ phù hợp trong lúc đọc. Bản sao có thể độc lập sau khi tạo nhưng vẫn đã chụp một trạng thái không nhất quán nếu bước tạo thiếu phối hợp.

## 14. Các lỗi thường gặp

| Nhầm lẫn | Biểu hiện | Cách sửa suy luận |
|---|---|---|
| Cloneable khai báo clone() | Không gọi được qua biến kiểu Cloneable | Đọc API công khai của lớp cụ thể |
| List nào cũng clone được | Lỗi biên dịch hoặc ép kiểu sai | Dùng hợp đồng của interface và constructor/factory phù hợp |
| Clone list là clone từng phần tử | Sửa Box ở bản sao làm nguồn đổi | Kiểm tra lớp chứa và phần tử riêng |
| final làm collection bất biến | Vẫn thêm/xóa được nội dung | final giữ tham chiếu, không khóa nội dung đối tượng |
| transient làm mọi kiểu sao chép bỏ trường | Clone vẫn giữ tham chiếu của trường | Phân biệt quy tắc clone và serialization |
| Đệ quy new cho mọi liên kết | Lặp ở chu trình hoặc phá liên kết trùng | Có bảng nguồn→đích theo danh tính và ghi trước đệ quy |
| Serializable ở gốc đủ cho toàn bộ đồ thị | NotSerializableException khi ghi | Kiểm tra các nút thực tế cần serialize |
| Đọc lại luôn chạy constructor lớp | Mất bước kiểm tra hoặc cache không khởi tạo | Hiểu cơ chế của lớp thông thường và kiểu đặc biệt |
| Serialization luôn tách mọi đối tượng | Singleton hoặc enum vẫn dùng chung | Xét readResolve và giao thức của từng kiểu |
| Ghi lại cùng đối tượng là ảnh chụp mới | Đọc lại cùng đối tượng với trạng thái cũ | Hiểu bảng tham chiếu và vòng đời luồng |
| Giữ UID thì mọi phiên bản đều đọc đúng | Đọc lỗi hoặc trạng thái không hợp lệ | Thiết kế, kiểm thử tương thích dữ liệu |
| Ép kiểu sau đọc là đủ an toàn | Code khác có thể đã chạy trong lúc đọc | Kiểm soát nguồn, lớp, bộ lọc và bất biến |
| Serialization là mã hóa bí mật | Byte vẫn chứa dữ liệu cần bảo vệ | Phân biệt biểu diễn byte với bảo mật dữ liệu |

## 15. Bài tập và lời giải

### Bài 1 — Hai kiểu sửa trên một clone list

List gốc là ArrayList chứa một Box có value = 5. Clone list thành c, gọi c.get(0).value = 8 rồi c.set(0,new Box(9)). Box ở nguồn có value bằng bao nhiêu?

**Lời giải:** bằng 8. Lệnh đầu sửa Box dùng chung; lệnh sau chỉ thay tham chiếu trong c. Nguồn không tự chuyển sang Box(9).

### Bài 2 — transient trong clone và serialization

Một lớp hỗ trợ super.clone() có transient List<String> cache đang trỏ tới một ArrayList. Nếu không có xử lý tùy biến, so sánh cache của bản clone nông với cache của bản deserialization thông thường.

**Lời giải:** clone nông giữ cùng tham chiếu cache với nguồn. Serialization mặc định bỏ trường transient, nên trường cache của lớp Serializable thông thường sau khi đọc không được khôi phục từ nguồn; nếu không có code dựng lại, nó là null. Một biểu thức khởi tạo trường ở lớp serializable không tự được chạy như constructor new trong quá trình đọc đó.

### Bài 3 — Ma trận có hàng dùng chung

int[] row = {1,2}; int[][] matrix = {row,row}; Nếu clone mảng ngoài, hai hàng của bản sao có khác nguồn không? Nếu clone riêng từng hàng, có giữ quan hệ hai vị trí cùng một hàng không?

**Lời giải:** clone mảng ngoài giữ cùng tham chiếu row ở cả hai vị trí, cũng là row của nguồn. Clone mỗi hàng riêng tách dữ liệu khỏi nguồn nhưng tạo hai hàng khác nhau, làm mất quan hệ dùng chung giữa hai vị trí. Nếu cần vừa tách nguồn vừa giữ quan hệ đó, tạo đúng một bản row mới rồi dùng nó cho cả hai vị trí, hoặc dùng thuật toán có bảng theo dõi danh tính.

### Bài 4 — Khi nào đưa nút vào bảng đã gặp?

Trong GraphCopyDemo, có thể chuyển seen.put(source,target) xuống sau vòng lặp sao chép links không?

**Lời giải:** không giữ đúng khả năng xử lý chu trình. Khi child trỏ lại root mà root chưa được đăng ký, hàm tiếp tục tạo/sao chép root thay vì quay về root đích đã có. Cần đưa vào bảng trước khi đi theo liên kết con.

### Bài 5 — equals không thay được danh tính của nút

Hai nút nguồn khác tham chiếu nhưng cùng tên và equals() trả true. Nếu dùng HashMap theo equals để ghi nhớ bản sao thay vì IdentityHashMap, rủi ro là gì?

**Lời giải:** thuật toán có thể coi hai nút nguồn khác nhau là một nút và gộp chúng vào cùng bản đích. Khi mục tiêu là bảo toàn hình dạng đồ thị theo danh tính, phải phân biệt hai tham chiếu ấy ngay cả khi giá trị nghiệp vụ bằng nhau.

### Bài 6 — Collection serializable có phần tử không serializable

Một ArrayList<Object> chứa một new Object(). Gốc ArrayList triển khai Serializable. Có bảo đảm serialize thành công không? Đổi trường chứa list ở một lớp khác thành transient giải quyết điều gì?

**Lời giải:** không, cơ chế có thể gặp phần tử không hỗ trợ và ném NotSerializableException. Đánh dấu trường list transient chỉ bỏ đường ghi đó khỏi trạng thái mặc định của lớp chứa, không sao chép nội dung list; phải định nghĩa trạng thái mong muốn sau khi đọc. Nếu còn một đường tham chiếu khác cần ghi tới cùng đối tượng không hỗ trợ, lỗi vẫn có thể xảy ra.

### Bài 7 — Ghi hai lần trên cùng luồng

Ghi một Box(1), đổi value thành 2 rồi writeObject cùng Box lần nữa trên cùng ObjectOutputStream, không reset. Hai lần readObject tương ứng có bắt buộc trả hai Box khác nhau với giá trị 1 và 2 không?

**Lời giải:** không. Với đối tượng thông thường như ví dụ, lần ghi sau dùng tham chiếu ngược; hai lần đọc trả cùng đối tượng và giữ trạng thái được ghi ở lần đầu, là 1. Muốn ghi trạng thái mới phải thiết kế vòng đời luồng/định danh phù hợp, chẳng hạn lần sao chép dùng cặp luồng mới.

### Bài 8 — Bản sao có singleton

Một trường của đối tượng serializable trỏ đến Config.INSTANCE. Config có readResolve() trả INSTANCE. Sau serialization rồi đọc lại, có thể mặc định sửa Config ở bản đọc không ảnh hưởng Config gốc không?

**Lời giải:** không. Trường có thể lại trỏ tới chính singleton dùng chung. Nếu Config mutable, việc sửa nó ảnh hưởng các nơi giữ cùng INSTANCE. Muốn độc lập phải đổi hợp đồng mô hình, không chỉ đổi tên hàm thành deepCopy.

### Bài 9 — Constructor lớp cha

Child triển khai Serializable, extends Parent không serializable. Parent có constructor không đối số truy cập được, khởi tạo x = 10. Trước khi ghi, child.x = 80. Không có code tùy biến lưu x. Sau đọc, x là gì?

**Lời giải:** là 10 theo khởi tạo của Parent, không phải 80. Trạng thái phần lớp cha không serializable không được tự ghi; constructor lớp cha phù hợp được gọi khi dựng lại. Không suy kết quả này sang Externalizable hoặc record mà bỏ qua quy tắc riêng.

### Bài 10 — Chọn bản sao cho màn hình chỉnh sửa

Một màn hình cần chỉnh sửa danh sách đơn hàng thử nghiệm mà không sửa đơn gốc. Các đơn chứa List<LineItem> mutable và một mã String bất biến. Clone ArrayList ngoài đã đủ chưa? Nêu hợp đồng sao chép tối thiểu.

**Lời giải:** chưa đủ. Cần cấu trúc danh sách riêng, đơn hàng riêng cho phần trạng thái được phép chỉnh, danh sách LineItem riêng và các LineItem mutable riêng theo yêu cầu. Mã String có thể dùng chung. Nếu nhiều đơn cố ý dùng chung một đối tượng bên trong, cần quyết định giữ quan hệ dùng chung trong bản sao hay tách theo nghiệp vụ, rồi kiểm thử điều đó. ID và dịch vụ không được tự sao chép theo cảm giác “cứ sâu hết là đúng”.

## 16. Nguồn đối chiếu chính thức

- [Object.clone và hợp đồng sao chép từng trường](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone()).
- [Cloneable và giới hạn của interface đánh dấu](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html).
- [Serializable và các phương thức tùy biến](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html).
- [Java Object Serialization Specification — kiến trúc, record và chu trình](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html).
- [ObjectOutputStream — định danh tham chiếu và reset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html).
- [Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html).
