# Sao chép nông, sao chép sâu và đối tượng phần tử dùng chung

## 1. Cần độc lập ở lớp nào?

Một chương trình nhận List rồi tạo List khác để chỉnh sửa. Nó có thể muốn tránh sửa danh sách đầu vào, nhưng vẫn vô tình thay trạng thái của một phần tử mà cả hai danh sách đang trỏ đến.

Để hiểu kết quả, cần nhìn dữ liệu theo nhiều lớp: biến tham chiếu, đối tượng collection, rồi các đối tượng phần tử và dữ liệu lồng bên trong chúng.

Ba hành động khác nhau:

| Hành động | Có collection mới? | Các phần tử có được nhân bản? |
|---|---|---|
| Gán alias = source | Không | Không; hai biến trỏ cùng collection |
| new ArrayList<>(source) | Có cấu trúc chứa riêng | Không; các tham chiếu phần tử được sao chép |
| Tạo collection mới và sao chép các đối tượng theo chính sách đã chọn | Có | Những đối tượng thuộc phạm vi sao chép được tạo lại |

Sao chép nông, gọi là shallow copy, tạo một lớp đối tượng mới nhưng giữ lại các tham chiếu bên trong theo chính sách của thao tác. Sao chép sâu, gọi là deep copy, tạo lại những đối tượng có thể thay đổi trong phạm vi cần độc lập.

Không có một độ sâu đúng cho mọi bài toán. Có lúc chỉ cần sửa danh sách chứa mà không sửa phần tử; có lúc cần một bản dữ liệu chỉnh sửa độc lập; có lúc phải sao chép cả đồ thị có nhiều đường tham chiếu và vòng.

Các chương trình đầy đủ trong bài dùng Java 17 trở lên. Các lớp dữ liệu nhỏ cố ý cho sửa trực tiếp để có thể quan sát rõ từng quan hệ tham chiếu.

### 1.1. Một sơ đồ để đọc các thay đổi

Sau new ArrayList<>(source), có thể hình dung:

```text
source ──→ List thứ nhất ──┬──→ Person A
                          └──→ Person B

copy   ──→ List thứ hai  ──┬──→ Person A
                          └──→ Person B
```

Hai List khác nhau, nhưng cả hai mũi tên ở vị trí đầu đều đến cùng Person A. Thêm một vị trí vào List thứ hai không tự thêm vào List thứ nhất; sửa tên của Person A thì những nơi trỏ đến Person A cùng thấy.

Sau một bản sao sâu phù hợp, các đối tượng Person có trạng thái cần độc lập cũng được tạo lại. Những giá trị bất biến như String có thể tiếp tục được dùng chung mà không tạo đường sửa trạng thái qua chúng.

## 2. Tham chiếu, danh tính và loại thay đổi

### 2.1. Gán một tham chiếu không tạo lại đối tượng

Một biến kiểu tham chiếu giữ giá trị tham chiếu đến đối tượng hoặc null. Gán giá trị đó cho biến khác không tự chạy constructor để nhân bản đối tượng.

Do đó alias = source tạo thêm một đường đến cùng collection. Đây chưa phải thao tác tạo shallow copy của collection; thậm chí collection mới còn chưa tồn tại.

Cơ sở về tham chiếu và đối tượng được mô tả tại [JLS 17, mục 4.3.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3.1).

### 2.2. == và equals trả lời hai câu hỏi khác nhau

Với tham chiếu đối tượng, == kiểm tra cùng đối tượng hay không. equals kiểm tra sự bằng nhau theo hợp đồng của kiểu đó.

Hai List khác nhau có thể equals vì chứa các phần tử bằng nhau theo thứ tự. Hai đối tượng phần tử khác nhau cũng có thể equals nếu lớp định nghĩa bằng nhau theo dữ liệu.

Vì vậy, equals của kết quả không chứng minh sao chép sâu hay nông. Cần kiểm tra các tham chiếu ở đúng lớp dữ liệu và thử những thay đổi mà bản sao được yêu cầu phải cô lập.

Không dùng hashCode hoặc chuỗi toString mặc định như bằng chứng chắc chắn về danh tính. Các ví dụ dùng so sánh ==/!= cho điều đó.

### 2.3. Thay một tham chiếu khác với sửa đối tượng được tham chiếu

Với một bản sao nông List<Person>:

- copy.set(i, new Person(...)) thay tham chiếu trong một vị trí của copy.
- copy.add(...) thêm một vị trí trong copy.
- copy.get(i).name = ... sửa đối tượng Person lấy từ vị trí đó.

Hai hành động đầu thay collection đích. Hành động thứ ba có thể sửa chính Person đang được nguồn dùng chung.

Sự khác biệt này giải thích vì sao “tôi chỉ thay dữ liệu ở bản sao” đôi khi vẫn làm dữ liệu nguồn đổi: cần xác định đang sửa lớp đối tượng nào.

### 2.4. final không làm mọi đối tượng phía sau bất biến

Một tham chiếu final không được gán lại sau khi đã khởi tạo theo quy tắc ngôn ngữ. Nó không tự ngăn việc sửa nội dung List hay trạng thái của phần tử phía sau.

Tương tự, một List không cho add/remove/set chưa chứng minh các phần tử bên trong không có phương thức hay trường cho sửa. Quyền sửa collection và tính bất biến của phần tử là hai điều kiện riêng.

## 3. Chương trình 1: collection mới, phần tử vẫn dùng chung

Lưu vào `ShallowCollectionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ShallowCollectionDemo {
    static final class Person {
        String name;

        Person(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        List<Person> source = new ArrayList<>(
                List.of(new Person("Ada"), new Person("Bob")));
        List<Person> alias = source;
        List<Person> copy = new ArrayList<>(source);
        System.out.println("aliasSameList=" + (alias == source));
        System.out.println("copySameList=" + (copy == source));
        System.out.println("sameFirstElement=" + (copy.get(0) == source.get(0)));
        copy.get(0).name = "Ada2";
        System.out.println("sourceAfterElementEdit=" + source);
        copy.set(1, new Person("Cid"));
        System.out.println("sourceAfterCopySet=" + source);
        System.out.println("copyAfterSet=" + copy);
        copy.add(new Person("Dan"));
        System.out.println("sourceSize=" + source.size());
        System.out.println("copySize=" + copy.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ShallowCollectionDemo.java
java ShallowCollectionDemo
```

Stdout:

```text
aliasSameList=true
copySameList=false
sameFirstElement=true
sourceAfterElementEdit=[Ada2, Bob]
sourceAfterCopySet=[Ada2, Bob]
copyAfterSet=[Ada2, Cid]
sourceSize=2
copySize=3
```

### 3.1. Ba phép so sánh chỉ rõ ba lớp quan hệ

aliasSameList là true: alias và source trỏ cùng List. copySameList là false: constructor ArrayList tạo cấu trúc chứa khác.

sameFirstElement là true: phần tử đầu trong hai List vẫn là cùng Person. Không có thao tác sao chép từng Person trong new ArrayList<>(source).

### 3.2. Sửa Person khác với thay vị trí của List

Đổi tên qua copy.get(0) làm source in Ada2,Bob vì Person đầu được dùng chung.

copy.set(1,new Person(Cid)) chỉ thay vị trí thứ hai của copy. Source vẫn có Bob, còn copy có Cid. Thêm Dan làm copySize thành 3 nhưng sourceSize vẫn là 2.

Từ các kết quả đó có thể nói bản sao độc lập về cấu trúc chứa, nhưng chưa độc lập về trạng thái của mọi phần tử.

Hợp đồng constructor nhận Collection và khả năng chứa phần tử của ArrayList được mô tả tại [ArrayList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

## 4. View không cho sửa và bản sao không cho sửa

### 4.1. Hai cách chặn quyền sửa có quan hệ nguồn khác nhau

Collections.unmodifiableList(source) là một view chặn sửa qua đường wrapper. Khi source thay đổi qua một tham chiếu khác, việc đọc view vẫn đọc dữ liệu nguồn.

List.copyOf(source) trả List không cho thêm, xóa hoặc thay phần tử. Những thay đổi tiếp theo của collection nguồn không được phản ánh như một view sống lên kết quả này. Tuy nhiên, các đối tượng phần tử có thể vẫn được dùng chung.

Không gọi cả hai trường hợp là “deep copy bất biến”. Chúng giải quyết quyền sửa collection theo hai hợp đồng khác nhau.

### 4.2. Chương trình 2: không add được nhưng vẫn sửa được Task

Lưu vào `UnmodifiableElementDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class UnmodifiableElementDemo {
    static final class Task {
        String title;

        Task(String title) {
            this.title = title;
        }
    }

    public static void main(String[] args) {
        Task task = new Task("draft");
        List<Task> source = new ArrayList<>(List.of(task));
        List<Task> view = Collections.unmodifiableList(source);
        List<Task> snapshot = List.copyOf(source);
        source.add(new Task("extra"));
        System.out.println("sourceSize=" + source.size());
        System.out.println("viewSize=" + view.size());
        System.out.println("snapshotSize=" + snapshot.size());
        snapshot.get(0).title = "done";
        System.out.println("sourceTitle=" + source.get(0).title);
        System.out.println("viewTitle=" + view.get(0).title);
        System.out.println("sameTask=" + (snapshot.get(0) == source.get(0)));
        try {
            snapshot.add(new Task("blocked"));
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshotAdd=UnsupportedOperationException");
        }

        List<String> names = new ArrayList<>(List.of("A", "B"));
        List<String> savedNames = List.copyOf(names);
        names.set(0, "A2");
        System.out.println("savedNames=" + savedNames);
        System.out.println("currentNames=" + names);
        try {
            List.copyOf(Arrays.asList("A", null));
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println("nullCopyOf=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 UnmodifiableElementDemo.java
java UnmodifiableElementDemo
```

Stdout:

```text
sourceSize=2
viewSize=2
snapshotSize=1
sourceTitle=done
viewTitle=done
sameTask=true
snapshotAdd=UnsupportedOperationException
savedNames=[A, B]
currentNames=[A2, B]
nullCopyOf=NullPointerException
```

### 4.3. Cấu trúc nguồn và snapshot khác nhau

Sau source.add(extra), source và view đều có size bằng 2; snapshot vẫn có size bằng 1.

snapshot.add bị từ chối. Nhưng snapshot.get(0).title = done không gọi một phương thức sửa cấu trúc của List: nó sửa Task được trả về. Source và view cùng đọc title done, còn sameTask là true.

Không có ngoại lệ là điều dễ hiểu: quyền cấm add/remove/set của List không phải một lớp bảo vệ tự động cho từng đối tượng được get.

### 4.4. Phần tử bất biến có thể được dùng chung an toàn

savedNames giữ A,B khi names thay vị trí đầu sang A2. String là bất biến; thao tác names.set không sửa đối tượng String A, mà thay tham chiếu trong names.

Trong một mô hình chỉ cần List không cho sửa và các phần tử String bất biến, không cần tạo một String mới chỉ để bảo đảm không ai sửa nội dung String cũ.

List.copyOf không cho phép phần tử null, nên phép thử có null ném NullPointerException. Ngoài ra, API có thể tận dụng một List không cho sửa phù hợp; không dựa vào == để hứa mỗi lần copyOf luôn có một đối tượng List mới.

Nguồn đối chiếu: [List.copyOf — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Collections.unmodifiableList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).


## 5. Sao chép sâu cần biết cấu trúc và phạm vi dữ liệu

### 5.1. Tạo đối tượng phần tử mới vẫn có thể chưa đủ

Giả sử Task có title kiểu String và tags kiểu List<String>. Tạo một Task khác rồi gán tags = other.tags vẫn làm hai Task dùng chung danh sách tags.

Có thể vẽ các lớp như sau:

```text
Task gốc   ──→ tags List ──→ các String
Task mới   ──→ tags List ──→ các String
               ↑ cùng List nếu chỉ gán trường tags
```

Muốn hai Task sửa danh sách tags độc lập, cần tạo một List tags mới. Vì phần tử trong tags là String bất biến, có thể tiếp tục dùng chung các String theo chính sách của ví dụ.

Nếu đổi thành List<MutableTag>, tạo riêng List vẫn chưa cô lập MutableTag. Phạm vi sao chép phải được xem tiếp theo kiểu dữ liệu thực tế.

### 5.2. Copy constructor chỉ sâu đến mức người viết cài đặt

Java không tự quy định một constructor nhận đối tượng cùng kiểu phải là deep copy. Tên “copy constructor” là cách thiết kế API; phần thân constructor mới quyết định những tham chiếu nào tiếp tục được chia sẻ.

Một phương thức tên copy, duplicate hay clone cũng cần một hợp đồng rõ: sao chép lớp nào, giữ phần tử nào, có cho null không và kết quả có sửa được không.

Trong ví dụ tiếp theo, constructor nhận Task cố ý sao chép nông các trường. independentCopy tạo riêng List tags để đáp ứng yêu cầu độc lập của mô hình nhỏ này. Hai đường được đặt cạnh nhau để quan sát, không phải khuyến nghị để một API nghiệp vụ có hành vi sao chép mơ hồ.

## 6. Chương trình 3: Task mới nhưng danh sách bên trong có thể còn chung

Lưu vào `NestedObjectCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class NestedObjectCopyDemo {
    static final class Task {
        String title;
        List<String> tags;

        Task(String title, List<String> tags) {
            this.title = title;
            this.tags = tags;
        }

        Task(Task other) {
            this.title = other.title;
            this.tags = other.tags;
        }

        static Task independentCopy(Task source) {
            return new Task(source.title, new ArrayList<>(source.tags));
        }
    }

    public static void main(String[] args) {
        Task original = new Task("report", new ArrayList<>(List.of("urgent")));
        Task fieldCopy = new Task(original);
        Task independent = Task.independentCopy(original);
        System.out.println("differentTask=" + (fieldCopy != original));
        System.out.println("fieldCopySharesTags=" + (fieldCopy.tags == original.tags));
        System.out.println("independentSharesTags="
                + (independent.tags == original.tags));
        fieldCopy.tags.add("shared");
        System.out.println("originalTagsAfterFieldCopyEdit=" + original.tags);
        System.out.println("independentTagsBeforeEdit=" + independent.tags);
        independent.tags.add("local");
        independent.title = "copy-report";
        System.out.println("originalTagsAfterIndependentEdit=" + original.tags);
        System.out.println("independentTags=" + independent.tags);
        System.out.println("originalTitle=" + original.title);
        System.out.println("independentTitle=" + independent.title);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NestedObjectCopyDemo.java
java NestedObjectCopyDemo
```

Stdout:

```text
differentTask=true
fieldCopySharesTags=true
independentSharesTags=false
originalTagsAfterFieldCopyEdit=[urgent, shared]
independentTagsBeforeEdit=[urgent]
originalTagsAfterIndependentEdit=[urgent, shared]
independentTags=[urgent, local]
originalTitle=report
independentTitle=copy-report
```

### 6.1. Danh tính Task và danh tính tags được kiểm tra riêng

differentTask là true, nên fieldCopy và original là hai Task khác nhau. Nhưng fieldCopySharesTags cũng true: hai trường tags trỏ cùng List.

independentSharesTags là false vì independentCopy tạo một ArrayList tags khác.

Chỉ kiểm tra Task mới khác Task cũ là chưa đủ. Phải đi xuống lớp trạng thái mà yêu cầu độc lập thực sự cần bảo vệ.

### 6.2. Sửa tags qua fieldCopy làm nguồn đổi

fieldCopy.tags.add(shared) sửa List tags đang dùng chung. originalTagsAfterFieldCopyEdit là urgent,shared.

independent đã được tạo trước thao tác đó, nên independentTagsBeforeEdit chỉ có urgent. Sau independent.tags.add(local), tags của bản độc lập là urgent,local; original vẫn urgent,shared.

### 6.3. Dùng chung String không đồng nghĩa dùng chung biến trường

title được gán cùng tham chiếu String lúc tạo bản sao. Nhưng independent.title = copy-report chỉ thay trường title của independent, không gán lại trường của original. originalTitle vẫn report.

String không bị sửa nội dung bởi phép gán đó. Đây là trường hợp có thể dùng chung đối tượng bất biến mà hai bản dữ liệu vẫn độc lập với những thay đổi được phép của mô hình.

independentCopy giả định source và source.tags khác null. Nếu API nghiệp vụ muốn nhận null hoặc có các kiểu phần tử khác, phải thêm chính sách đó một cách tường minh.

## 7. Khi dữ liệu là đồ thị chứ không phải một cây đơn giản

### 7.1. Một đối tượng có thể được tham chiếu nhiều lần

Một List có thể chứa cùng một đối tượng tại hai vị trí. Hai phần tử khác nhau cũng có thể cùng trỏ đến một Address, một danh sách con hoặc một nút chung.

Nếu mỗi lần gặp tham chiếu đều tạo một bản mới độc lập, quan hệ dùng chung trong kết quả sẽ bị phá. Ví dụ, hai người cùng tham chiếu một địa chỉ ban đầu có thể trở thành hai Address riêng sau sao chép, làm thay đổi ý nghĩa mô hình.

Điều đó không phải luôn bị cấm trong mọi nghiệp vụ, nhưng phải là chính sách có chủ đích. Khi yêu cầu là bảo toàn hình dạng tham chiếu của đồ thị, một đối tượng nguồn phải tương ứng một đối tượng đích trong cùng lượt sao chép.

### 7.2. Đồ thị có thể có vòng

root có thể trỏ đến child, còn child trỏ ngược root. Một thuật toán đệ quy chỉ “tạo mới rồi sao chép mọi con” mà không ghi nhớ đối tượng đã gặp sẽ tiếp tục đi vòng.

Cần một bảng ánh xạ đối tượng nguồn sang đối tượng đích đã tạo:

1. Nếu nguồn là null, xử lý theo chính sách null.
2. Nếu nguồn đã có trong bảng, dùng lại bản đích.
3. Nếu chưa có, tạo đối tượng đích và ghi vào bảng ngay.
4. Sau đó mới sao chép các đường tham chiếu con.

Ghi nhận trước bước đệ quy là điểm giúp vòng tham chiếu tìm lại đối tượng đích đang được xây dựng.

### 7.3. Bảng ghi nhớ phải phân biệt danh tính với equals

Hai nút khác nhau có thể equals vì cùng dữ liệu. Khi sao chép bảo toàn cấu trúc tham chiếu, không được vì equals mà tự gộp hai đối tượng nguồn khác nhau thành một nút đích.

IdentityHashMap so sánh khóa theo danh tính tham chiếu thay vì equals. Nó phù hợp cho bảng ghi nhớ của ví dụ này. Đây là một mục đích chuyên biệt, không phải lý do thay mọi HashMap nghiệp vụ bằng IdentityHashMap.

Nguồn đối chiếu: [IdentityHashMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html).

### 7.4. Chính sách của ví dụ đồ thị

Mô hình tiếp theo sao chép các Node và các List links mới, giữ thứ tự các cạnh, giữ các cạnh lặp và giữ vòng trong đồ thị kết quả. String name được dùng chung theo tính bất biến.

Các Node có equals đơn giản theo name để cố ý tạo hai nút bằng nhau về dữ liệu nhưng khác danh tính. Bảng sao chép vẫn phải phân biệt chúng. Đây là mô hình minh họa cho sự khác nhau giữa equals và danh tính, không phải một quy tắc chung chọn định danh nghiệp vụ cho mọi Node.

## 8. Chương trình 4: bảo toàn phần dùng chung và vòng trong đồ thị mới

Lưu vào `GraphCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;

public class GraphCopyDemo {
    static final class Node {
        String name;
        final List<Node> links = new ArrayList<>();

        Node(String name) {
            this.name = name;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Node
                    && Objects.equals(name, ((Node) other).name);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(name);
        }
    }

    static Node copy(Node source) {
        return copy(source, new IdentityHashMap<>());
    }

    static Node copy(Node source, IdentityHashMap<Node, Node> seen) {
        if (source == null) {
            return null;
        }
        Node existing = seen.get(source);
        if (existing != null) {
            return existing;
        }
        Node result = new Node(source.name);
        seen.put(source, result);
        for (Node link : source.links) {
            result.links.add(copy(link, seen));
        }
        return result;
    }

    public static void main(String[] args) {
        Node root = new Node("root");
        Node shared = new Node("leaf");
        Node equalButDistinct = new Node("leaf");
        root.links.add(shared);
        root.links.add(shared);
        root.links.add(equalButDistinct);
        shared.links.add(root);

        Node copied = copy(root);
        System.out.println("sourceLeavesEqual=" + shared.equals(equalButDistinct));
        System.out.println("newRoot=" + (copied != root));
        System.out.println("newLeaf=" + (copied.links.get(0) != shared));
        System.out.println("sharedLinkPreserved="
                + (copied.links.get(0) == copied.links.get(1)));
        System.out.println("distinctEqualNodesPreserved="
                + (copied.links.get(0) != copied.links.get(2)));
        System.out.println("cyclePreserved="
                + (copied.links.get(0).links.get(0) == copied));
        copied.links.get(0).name = "copy-leaf";
        System.out.println("originalLeafName=" + shared.name);
        System.out.println("copiedLeafName=" + copied.links.get(0).name);
        System.out.println("copiedOtherLeafName=" + copied.links.get(2).name);
        System.out.println("nullCopy=" + copy(null));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 GraphCopyDemo.java
java GraphCopyDemo
```

Stdout:

```text
sourceLeavesEqual=true
newRoot=true
newLeaf=true
sharedLinkPreserved=true
distinctEqualNodesPreserved=true
cyclePreserved=true
originalLeafName=leaf
copiedLeafName=copy-leaf
copiedOtherLeafName=leaf
nullCopy=null
```

### 8.1. Có ba cạnh nhưng chỉ hai nút lá nguồn khác nhau

root.links chứa shared hai lần rồi equalButDistinct. Hai nút lá có cùng name nên sourceLeavesEqual là true, nhưng chúng là hai đối tượng khác nhau.

shared còn trỏ ngược root. Không in toàn đồ thị bằng một toString đệ quy; ví dụ kiểm tra các quan hệ cần thiết bằng ==/!= để tránh phụ thuộc cách hiển thị vòng.

### 8.2. Nút đích mới, phần dùng chung được giữ trong đồ thị đích

newRoot và newLeaf đều true. Đồ thị đích không dùng lại các Node mutable đó của nguồn.

sharedLinkPreserved là true: hai cạnh đầu trong bản sao vẫn cùng đến một Node đích. distinctEqualNodesPreserved cũng true: cạnh thứ ba đến một Node đích khác, dù hai nút nguồn equals.

Nếu dùng bảng ghi nhớ gộp theo equals, hai nút lá có nguy cơ bị gộp sai. IdentityHashMap giúp thể hiện đúng chính sách một danh tính nguồn tương ứng một danh tính đích.

### 8.3. Vòng được giữ mà không trỏ ngược về nguồn

cyclePreserved là true vì nút lá đích trỏ về copied, không phải root nguồn. Ghi seen.put trước khi đi vào các links giúp thuật toán đạt được điều này.

Sau khi đổi tên nút lá đích đầu thành copy-leaf, originalLeafName vẫn leaf. Nút lá đích thứ ba cũng vẫn leaf, chứng minh hai nút đích riêng không bị gộp theo tên.

nullCopy là null theo chính sách của phương thức copy trong ví dụ.

### 8.4. Phạm vi của thuật toán không phải Object bất kỳ

Thuật toán biết rõ trường name và links của Node. Nếu Node có thêm một payload mutable, phải đưa payload đó vào chính sách sao chép; mã hiện tại không tự phát hiện và sao chép mọi trường mới.

Mỗi lời gọi copy(root) tạo bảng ghi nhớ mới. Nếu sao chép nhiều gốc và cần giữ quan hệ dùng chung giữa các gốc ấy, phải thiết kế một ngữ cảnh sao chép chung cho cả lượt, thay vì mặc nhiên tạo một bảng riêng cho từng gốc.

Đệ quy có bảng ghi nhớ xử lý được vòng, nhưng một chuỗi nút rất sâu vẫn có thể vượt khả năng ngăn xếp. Khi dữ liệu yêu cầu điều đó, có thể thiết kế cách duyệt với danh sách công việc tường minh; đó là quyết định triển khai riêng của mô hình.


## 9. clone không tự có nghĩa sao chép sâu

### 9.1. Object.clone sao chép các trường theo giá trị đang giữ

Object.clone tạo bản sao các trường như khi gán. Trường primitive được sao chép giá trị primitive; trường tham chiếu được sao chép giá trị tham chiếu. Các đối tượng mà trường tham chiếu trỏ đến không tự được clone theo.

Vì vậy super.clone thường chỉ là bước sao chép nông. Nếu lớp cần độc lập những trường mutable, phần cài đặt còn phải xử lý các trường đó theo hợp đồng đã chọn.

Cloneable là một giao diện đánh dấu liên quan đến quyền dùng cơ chế Object.clone. Nó không khai báo phương thức clone và không tự sinh một phương thức public sao chép sâu cho lớp.

Nguồn đối chiếu: [Object.clone — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html), [Cloneable — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html).

### 9.2. Mảng cũng có nhiều lớp tham chiếu

Clone một int[] tạo mảng mới chứa các giá trị số, nên thay một ô của mảng đích không thay ô nguồn.

Clone một StringBuilder[] tạo mảng ngoài mới nhưng các phần tử StringBuilder vẫn có thể là cùng đối tượng. Append lên phần tử qua mảng đích vẫn sửa đối tượng mà nguồn dùng.

Ngay cả int[][] cũng là mảng chứa các tham chiếu đến int[] con. Clone mảng ngoài không tự tạo lại từng mảng con. Cần nhìn từng lớp, không chỉ thấy từ int rồi kết luận không có tham chiếu bên trong.

### 9.3. ArrayList.clone cũng không nhân bản phần tử

ArrayList công bố clone là shallow copy: List mới không có nghĩa mọi phần tử bên trong mới. Khi cần viết mã dễ đọc qua giao diện List, constructor nhận Collection thường diễn tả rõ việc sao chép cấu trúc chứa mà không cần suy đoán về clone.

Điều quan trọng vẫn là hợp đồng, không phải chỉ chọn giữa từ khóa new và tên phương thức clone. Một constructor tùy chỉnh cũng có thể gán lại tham chiếu cũ; một phương thức sao chép tùy chỉnh cũng có thể tạo nhiều lớp đối tượng mới.

Hợp đồng cụ thể của ArrayList.clone được nêu tại [ArrayList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

## 10. Chương trình 5: clone của trường và mảng

Lưu vào `CloneFieldsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class CloneFieldsDemo {
    static final class Box implements Cloneable {
        int quantity;
        List<String> tags;

        Box(int quantity, List<String> tags) {
            this.quantity = quantity;
            this.tags = tags;
        }

        @Override
        public Box clone() {
            try {
                return (Box) super.clone();
            } catch (CloneNotSupportedException impossible) {
                throw new AssertionError(impossible);
            }
        }

        Box independentCopy() {
            return new Box(quantity, new ArrayList<>(tags));
        }
    }

    public static void main(String[] args) {
        Box original = new Box(3, new ArrayList<>(List.of("base")));
        Box shallow = original.clone();
        Box independent = original.independentCopy();
        System.out.println("newBox=" + (shallow != original));
        System.out.println("cloneSharesTags=" + (shallow.tags == original.tags));
        shallow.quantity = 7;
        shallow.tags.add("via-clone");
        System.out.println("originalQuantity=" + original.quantity);
        System.out.println("cloneQuantity=" + shallow.quantity);
        System.out.println("originalTags=" + original.tags);
        System.out.println("independentTagsBeforeEdit=" + independent.tags);
        independent.tags.add("local");
        System.out.println("originalTagsAfterIndependentEdit=" + original.tags);

        int[] numbers = {1, 2};
        int[] numberCopy = numbers.clone();
        numberCopy[0] = 9;
        System.out.println("originalNumbers=" + Arrays.toString(numbers));
        StringBuilder[] builders = {new StringBuilder("x")};
        StringBuilder[] builderCopy = builders.clone();
        builderCopy[0].append("!");
        System.out.println("sharedArrayElement=" + builders[0]);
        int[][] grid = {{1, 2}};
        int[][] gridCopy = grid.clone();
        gridCopy[0][0] = 9;
        System.out.println("sharedInnerArray=" + grid[0][0]);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CloneFieldsDemo.java
java CloneFieldsDemo
```

Stdout:

```text
newBox=true
cloneSharesTags=true
originalQuantity=3
cloneQuantity=7
originalTags=[base, via-clone]
independentTagsBeforeEdit=[base]
originalTagsAfterIndependentEdit=[base, via-clone]
originalNumbers=[1, 2]
sharedArrayElement=x!
sharedInnerArray=9
```

### 10.1. Box mới nhưng tags vẫn chung

Box cài clone bằng cách gọi super.clone. newBox là true, nhưng cloneSharesTags cũng true.

shallow.quantity = 7 thay trường int của Box đích; originalQuantity vẫn 3. shallow.tags.add(via-clone) lại sửa List tags chung, nên originalTags trở thành base,via-clone.

independentCopy tạo Box và ArrayList tags riêng trước thay đổi này. independentTagsBeforeEdit chỉ có base. Thêm local vào bản đó không thêm vào original.tags.

Trong mô hình này, tags chứa String bất biến nên tạo riêng List đủ cho phạm vi độc lập cần minh họa. Nếu tags chứa đối tượng mutable, cần xem tiếp những phần tử đó.

### 10.2. CloneNotSupportedException không được dùng để che lỗi khác

Box đã implements Cloneable nên ví dụ xem việc super.clone từ chối là một lỗi bất thường và chuyển thành AssertionError. Không dùng catch này như cách xử lý mọi lỗi dữ liệu nghiệp vụ.

Lớp tự công bố clone public và trả Box. Chỉ viết implements Cloneable mà không thiết kế API gọi thích hợp không tự giải quyết toàn bộ việc sao chép.

### 10.3. Ba kết quả mảng phản ánh ba loại lớp chứa

numberCopy[0] được đổi thành 9 nhưng originalNumbers vẫn là `[1, 2]`.

builderCopy[0] vẫn trỏ cùng StringBuilder đầu, nên sharedArrayElement là x! sau append.

gridCopy[0] vẫn là cùng mảng int[] con với grid[0], nên đổi ô trong mảng con làm sharedInnerArray thành 9. Nếu muốn độc lập toàn bộ các hàng của một ma trận, phải tạo lại các mảng hàng theo chính sách phù hợp; clone lớp ngoài chưa đủ.

## 11. Thiết kế một hợp đồng sao chép có thể kiểm chứng

### 11.1. Chọn phạm vi độc lập trước khi viết mã

Một API sao chép nên trả lời được:

- Đối tượng ngoài có được tạo mới không?
- Collection lồng bên trong có vùng chứa riêng không?
- Đối tượng phần tử mutable nào phải được tạo lại?
- Đối tượng bất biến nào được tiếp tục dùng chung?
- Quan hệ dùng chung và vòng trong nguồn có cần được giữ trong đồ thị đích không?
- Nguồn null, phần tử null và trường null được xử lý thế nào?
- Kết quả có cho sửa collection và phần tử không?

Không gọi một kết quả là deep copy chỉ vì đã có nhiều lệnh new. Phải đánh giá nó theo những đường trạng thái có thể bị thay đổi trong phạm vi nghiệp vụ.

### 11.2. Sao chép phòng vệ ở ranh giới sở hữu dữ liệu

Nếu một lớp không muốn người gọi sửa dữ liệu nội bộ qua List đầu vào, có thể giữ một bản sao phù hợp ngay khi nhận dữ liệu. Nếu không muốn người gọi sửa dữ liệu qua getter, kết quả trả về cũng cần một chính sách thích hợp.

Chỉ sao chép lớp List bảo vệ quan hệ chứa trước add/remove/set từ ngoài. Nếu phần tử mutable vẫn được chia sẻ, người gọi còn có thể sửa chúng. Muốn cô lập cả trạng thái đó cần sao chép phần tử, chuyển sang mô hình giá trị bất biến hoặc công bố rõ quan hệ chia sẻ.

Một List không cho sửa chứa các phần tử bất biến thường cho phép chia sẻ dữ liệu an toàn với những thao tác được phép của mô hình. Không cần tạo lại mọi đối tượng chỉ để tăng số lớp sao chép.

### 11.3. List, Set và Map có thêm hợp đồng của cấu trúc chứa

Khi đổi cấu trúc trong lúc sao chép, cần giữ các đặc tính mà người gọi dựa vào:

| Loại dữ liệu | Điều cần quyết định ngoài việc tạo đối tượng mới |
|---|---|
| List | Thứ tự, phần tử lặp, null, quyền sửa |
| List của List | List ngoài mới đã đủ chưa, các List con có cần mới không |
| Mảng tham chiếu | Có sao chép từng đối tượng phần tử không |
| Set | Quan hệ bằng nhau, tính duy nhất, thứ tự nếu có |
| Map | Khóa và giá trị nào mutable, thứ tự, Comparator nếu có |
| Đồ thị đối tượng | Cạnh dùng chung, vòng, đối tượng ngoài phạm vi sao chép |

Ví dụ, chỉ deep-copy các giá trị của Map trong khi vẫn dùng chung khóa mutable chưa chắc đáp ứng yêu cầu cô lập dữ liệu. Nếu tạo một TreeMap mới mà bỏ chính sách Comparator, kết quả có thể đổi thứ tự hoặc điều kiện chấp nhận khóa.

Không sửa các thuộc tính dùng trong equals/hashCode của một đối tượng khi nó còn đang làm khóa của map băm hay phần tử tập băm rồi kỳ vọng cấu trúc chứa tự tổ chức lại. Chính sách sao chép không thay thế các hợp đồng sử dụng collection đó.

### 11.4. Không có một hàm deepCopy(Object) đơn giản biết mọi ý nghĩa

Một đối tượng có thể giữ file đang mở, kết nối, luồng thực thi, bộ nhớ đệm hoặc một dịch vụ dùng chung. “Nhân bản tất cả” không cho biết tài nguyên bên ngoài phải được chia sẻ, mở mới hay loại khỏi bản sao.

Với dữ liệu nghiệp vụ đã biết kiểu, constructor/factory sao chép hoặc một bộ chuyển đổi có hợp đồng cụ thể thường giúp đọc và kiểm chứng phạm vi rõ hơn. Nếu chọn một cơ chế dựa trên serialization, JSON hay thư viện, vẫn phải đọc hợp đồng của cơ chế đó và kiểm tra kiểu, quan hệ tham chiếu, vòng cùng các phần dữ liệu được giữ lại.

Không xem một lần chuyển đổi thành công là bằng chứng mặc định rằng mọi đặc tính của đồ thị đã được sao chép đúng.

### 11.5. Sao chép không tự tạo một ảnh chụp nguyên tử khi có nhiều luồng

Trong các ví dụ, nguồn không bị nơi khác sửa trong lúc sao chép. Đó là điều kiện giúp kết quả cố định và dễ kiểm chứng.

Một vòng lặp tạo lại các phần tử từ nguồn đang thay đổi không mặc nhiên thấy toàn bộ trạng thái tại cùng một thời điểm. Cần hợp đồng truy cập thích hợp của nguồn hoặc cách phối hợp riêng nếu nghiệp vụ yêu cầu một ảnh chụp nhất quán.

Tương tự, bản sao đã tạo xong chưa tự trở thành đối tượng an toàn cho nhiều luồng nếu sau đó nhiều nơi cùng sửa nó. Độ sâu sao chép và cách phối hợp truy cập là hai quyết định khác nhau.

## 12. Chi phí và cách kiểm tra độ độc lập

### 12.1. Chi phí phụ thuộc số đối tượng phải tạo lại

Sao chép nông một List có n phần tử cần thu n tham chiếu vào cấu trúc chứa mới. Công việc còn phụ thuộc cách nguồn cho duyệt, nhưng nó không tự bao gồm chi phí sao chép toàn bộ trạng thái của từng phần tử.

Với đồ thị Node trong ví dụ và bảng ghi nhớ có chi phí tra cứu kỳ vọng hằng số, việc sao chép đi qua các nút và cạnh cần xử lý, tương ứng công việc kỳ vọng theo O(V+E). Nó cũng cần bộ nhớ cho bảng ghi nhớ và đồ thị đích; đệ quy còn dùng ngăn xếp theo độ sâu duyệt.

Nếu một phần tử có dữ liệu lớn, chi phí tạo lại phần tử đó phải được tính riêng. Không chọn sao chép sâu theo thói quen khi yêu cầu chỉ là thay cấu trúc List ngoài.

### 12.2. Kiểm tra theo từng đường sửa

Một phép kiểm tra tốt không chỉ dùng equals giữa nguồn và đích. Nên kiểm tra:

1. Danh tính đối tượng ngoài và những phần tử yêu cầu phải khác.
2. Danh tính của phần bất biến được phép dùng chung nếu điều đó có ý nghĩa.
3. Thêm/xóa/thay vị trí của collection đích có ảnh hưởng nguồn không.
4. Sửa trạng thái phần tử đích có ảnh hưởng nguồn không.
5. Các List hoặc đối tượng lồng bên trong còn chung ở đâu.
6. Cạnh dùng chung và vòng có được giữ theo chính sách không.
7. Hai đối tượng nguồn bằng nhau nhưng khác danh tính có bị gộp nhầm không.
8. Null và collection rỗng có được xử lý đúng hợp đồng không.

Nên thử cả chiều sửa nguồn rồi đọc đích nếu yêu cầu là độc lập hai chiều. Một kết quả đúng ngay sau sao chép chưa đủ chứng minh những thay đổi sau đó được cô lập đúng.

## 13. Những lỗi thường gặp

| Kết luận hoặc cách làm | Vì sao sai | Cách kiểm tra hoặc điều chỉnh |
|---|---|---|
| alias = source là đã sao chép List | Chỉ thêm tham chiếu đến cùng List | Kiểm tra alias == source |
| new ArrayList<>(source) tạo lại mọi phần tử | Nó sao chép cấu trúc chứa và tham chiếu | Kiểm tra danh tính phần tử và thử sửa trạng thái |
| Đối tượng ngoài khác thì mọi dữ liệu đã khác | Trường lồng có thể còn cùng tham chiếu | Kiểm tra từng lớp mutable cần độc lập |
| List.copyOf làm phần tử bất biến | Chỉ chặn thao tác sửa List và không theo cấu trúc nguồn về sau | Xem quyền sửa của từng phần tử |
| Wrapper unmodifiable là một bản sao dữ liệu | Wrapper còn dựa trên nguồn | Phân biệt view với kết quả sao chép |
| final List nghĩa List không đổi nội dung | final chặn gán lại tham chiếu, không chặn sửa đối tượng | Thiết kế quyền sửa và mô hình bất biến riêng |
| equals giữa nguồn và đích chứng minh deep copy | equals kiểm tra bằng nhau theo kiểu, không đo toàn bộ chia sẻ tham chiếu | Dùng ==/!= ở lớp cần xét và thử các thay đổi |
| clone luôn deep copy | Object.clone sao chép trường theo giá trị đang giữ | Đọc hợp đồng lớp, xử lý trường mutable khi cần |
| Clone mảng hai chiều là mọi hàng đều mới | Mảng ngoài chứa các tham chiếu đến mảng con | Kiểm tra danh tính các mảng hàng |
| Đệ quy sao chép mà không ghi nhớ nút | Có thể lặp vòng hoặc phá quan hệ dùng chung | Dùng ngữ cảnh ghi nhớ theo chính sách đồ thị |
| Dùng equals để gộp nút trong bản sao bảo toàn danh tính | Hai nguồn khác nhau nhưng equals có thể bị gộp | Ghi nhớ bằng danh tính khi đó là yêu cầu |
| Tạo List con mới nhưng quên phần tử mutable bên trong | Chỉ thêm một lớp độc lập | Xác định ranh giới sao chép theo loại dữ liệu |
| List.copyOf với phần tử null | API từ chối null | Chọn chính sách null và cách tạo kết quả phù hợp |
| Sao chép xong là an toàn đồng thời | Bản sao vẫn có thể được nhiều nơi cùng sửa | Thiết kế cách phối hợp truy cập riêng |

## 14. Tự kiểm tra và thực hành

### 14.1. Câu hỏi với đáp án

1. **Vì sao thêm phần tử vào shallow copy không đổi size nguồn nhưng sửa tên phần tử có thể đổi nguồn?** Cấu trúc List mới độc lập, còn đối tượng phần tử có thể vẫn dùng chung.
2. **copy.set thay một Person mới có giống copy.get(i).name = ... không?** Không. set thay tham chiếu trong List đích; sửa name tác động lên Person được tham chiếu.
3. **Một constructor Task(Task other) có mặc định deep copy không?** Không. Phần thân constructor quyết định cách sao chép từng trường.
4. **Có cần nhân bản String mới để tránh việc ai đó sửa nội dung String không?** Không. String bất biến; có thể chia sẻ theo yêu cầu của mô hình.
5. **Vì sao List.copyOf chứa Task vẫn thấy Task đổi?** Collection đích không cho sửa cấu trúc nhưng vẫn có thể giữ cùng tham chiếu Task mutable.
6. **Sao chép sâu có nhất thiết phá mọi chia sẻ trong bản sao không?** Không. Nếu yêu cầu bảo toàn đồ thị, các cạnh đến cùng một nút nguồn cần đến cùng một nút đích, trong khi nút mutable đích tách khỏi nguồn.
7. **Tại sao phải ghi nút vào bảng trước khi sao chép con?** Để một đường tham chiếu quay lại tìm được đối tượng đích đang xây, tránh đệ quy vô hạn.
8. **Vì sao IdentityHashMap phù hợp với bảng ghi nhớ trong ví dụ?** Nó phân biệt danh tính đối tượng, không gộp hai nguồn chỉ vì equals.
9. **Object.clone có tự clone mọi trường tham chiếu không?** Không. Các nội dung trường được sao chép như phép gán.
10. **int[][] clone có thể còn dùng chung mảng con không?** Có. Mảng ngoài mới vẫn chứa các tham chiếu mảng hàng cũ.
11. **Một List không cho sửa chứa phần tử bất biến có luôn cần deep copy mọi phần tử không?** Không cần tạo lại phần bất biến chỉ để ngăn sửa trạng thái qua nó; vẫn phải xét các yêu cầu khác của hợp đồng.
12. **Deep copy có đủ để có ảnh chụp nhất quán của nguồn đang bị sửa bởi luồng khác không?** Không. Còn cần hợp đồng hoặc cơ chế phối hợp việc đọc nguồn.

### 14.2. Bài tập: ba lớp dữ liệu

Tạo List<List<StringBuilder>> có hai hàng. Viết ba cách tạo kết quả: chỉ gán tham chiếu, tạo List ngoài mới, rồi tạo cả các List hàng và StringBuilder mới.

Với từng cách, kiểm tra ba thao tác: thêm một hàng vào kết quả; thêm một StringBuilder vào một hàng; append vào một StringBuilder. Dự đoán những thao tác nào còn ảnh hưởng nguồn.

Cách thứ ba cần thể hiện rõ chính sách nếu cùng StringBuilder xuất hiện nhiều lần: có giữ cùng một bản đích tương ứng hay chủ động tách thành các bản độc lập không?

### 14.3. Bài tập: kiểm tra hợp đồng sao chép một Order

Thiết kế Order có id kiểu String và List<Line> mutable, mỗi Line có số lượng và mô tả. Viết rõ hợp đồng bản sao trước khi cài đặt.

Nếu yêu cầu chỉnh số lượng trong bản sao mà không ảnh hưởng nguồn, cần tạo List mới và các Line mới. Nếu mô tả là String, có thể dùng chung String. Nếu một Line lại tham chiếu một đối tượng mutable khác, phải quyết định nó có nằm trong phạm vi cần độc lập không.

Kiểm tra thay List, thay Line và sửa trường trong Line như những hành động riêng.

### 14.4. Bài tập: hai nút bằng nhau và một vòng

Dựa vào GraphCopyDemo, tạo hai Node khác danh tính có cùng name và cho cả hai liên kết đến một Node chung. Thêm đường liên kết quay về gốc.

Xác minh kết quả có hai nút riêng cho hai nguồn riêng, một nút đích chung cho nguồn chung, và vòng trong kết quả trỏ về nút đích. Sau đó sửa một Node đích và chứng minh nguồn không đổi.

Không dùng equals làm phép kiểm tra duy nhất; các quan hệ danh tính chính là phần cần được kiểm chứng.

## 15. Nguồn đối chiếu và phạm vi kiểm chứng

- [JLS 17, Objects và Reference Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3.1): cơ sở tham chiếu và đối tượng; cùng chương mô tả biến final.
- [ArrayList — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): constructor nhận Collection và clone nông không sao chép phần tử.
- [List — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): copyOf, quyền sửa kết quả, phần tử mutable và điều kiện null.
- [Collections — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): wrapper unmodifiableList.
- [Object — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): cơ chế sao chép trường của clone.
- [Cloneable — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html): giao diện đánh dấu không tự cung cấp một phương thức clone public.
- [IdentityHashMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): so sánh danh tính và ứng dụng trong biến đổi đồ thị đối tượng.

Năm chương trình đầy đủ đã được biên dịch với `javac --release 17 -encoding UTF-8` và chạy trên Corretto JDK 17.0.15, cho đúng stdout được ghi. Các kết quả danh tính được in bằng ==/!=; ví dụ đồ thị kiểm tra trực tiếp cạnh dùng chung và vòng. Các phương thức sao chép tùy chỉnh trong bài chỉ áp dụng cho mô hình được khai báo, không được trình bày như bộ sao chép tổng quát cho mọi Object.
