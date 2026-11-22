# Sao chép cấu trúc chứa tham chiếu dùng chung hoặc vòng trong Java

## 1. Mục tiêu: sao chép object graph chứ không chỉ copy từng field

Trong Java, object có thể chứa references tới objects khác qua fields, arrays, Lists, Maps, v.v. Một tập hợp những objects và references này tạo thành **object graph (đồ thị đối tượng)**. Không phải graph nào cũng là cây: hai objects có thể cùng tham chiếu một child, một object có thể trỏ lại tổ tiên, hoặc tự trỏ đến chính nó.

Ví dụ:

~~~text
        A
       / \
      B   C
       \ /
        D
        |
        +------> A
 A còn có cạnh tự trỏ A --> A
~~~

B và C cùng trỏ tới **một instance D**, không phải hai objects cùng nội dung. D trỏ ngược về A, tạo chu trình A→B→D→A; A còn có self-loop.

Khi sao chép cấu trúc này thành một graph độc lập, ta muốn:

- A, B, C, D ở bản sao là những object mới A', B', C', D'.
- Nếu B.child và C.child cùng trỏ D ở nguồn, B'.child và C'.child cùng trỏ **D'**.
- D'.next phải trỏ **A'**, không được trỏ lại A nguồn.
- A'.self phải trỏ A' để giữ self-loop.
- Nếu mutable payload của D' thay đổi, D nguồn không đổi.
- Những references được phép chia sẻ có chủ đích, như immutable String hoặc service bên ngoài, phải được ghi rõ trong copy policy.

Một thuật toán đơn giản cứ gặp child là gọi `new Child(...)` có thể **nhân đôi shared references**, **đệ quy vô hạn với cycles**, hoặc **giữ nhầm references về graph gốc**. Do đó sao chép đúng phải bảo vệ cả *giá trị dữ liệu* lẫn *quan hệ identity giữa các nodes*.

Bài Knowledge README dành cho **Java 17+**, thuộc Java Core → Class/Object → **Sao chép đối tượng**, tập trung đúng chủ đề **sao chép cấu trúc chứa tham chiếu dùng chung hoặc vòng**: copy policy, identity vs equals, IdentityHashMap, memoization, trình tự allocate→register→populate, DFS/BFS, null/duplicate links, mutable nested state, heterogeneous types, final fields, snapshots bằng IDs, concurrency, lỗi thường gặp và các ví dụ runnable với stdout chính xác.

## 2. Khái niệm cốt lõi: graph identity và sharing

Mỗi reference tới một Java object có thể được so bằng toán tử `==` trong ngữ cảnh type hợp lệ. Nếu:

~~~java
Node a = new Node("A");
Node b = new Node("B");
Node c = new Node("C");
Node d = new Node("D");

b.next = d;
c.next = d;
~~~

thì `b.next == c.next` là true: B và C cùng có reference tới **D instance**. Đây là **aliasing**.

Trong ví dụ fragment trên, class Node có field `next` và constructor tương ứng; đây là phần minh họa chứ chưa là chương trình chạy độc lập.

### 2.1. Identity khác equality

- `x == y`: cùng reference hay không.
- `x.equals(y)`: có thể so logical value nếu class override.
- `x != y` nhưng `x.equals(y)` true là hoàn toàn có thể.
- Đối với thuật toán giữ topology graph, **hai source objects khác references không được tự gộp làm một chỉ vì equals true**.

Nếu graph có hai nodes X1 và X2 cùng label `"X"` nhưng là hai instances, bản sao phải có **hai clones** cho X1 và X2 khi policy là preserve reference topology.

### 2.2. Giữ sharing trong cloned graph khác với share nodes cùng nguồn

Có hai kiểu “chia sẻ” cần phân biệt:

1. **B' và C' cùng trỏ tới D'**: sharing **bên trong cloned graph**, là điều cần giữ.
2. **B' hoặc C' vẫn trỏ tới D gốc**: sharing mutable state **giữa graph nguồn và graph sao chép**, thường vi phạm deep copy independence.

Không thể dùng một phép so sánh `equals` duy nhất để chứng minh cả hai yêu cầu.

### 2.3. Cycle và self-loop

Cycle có thể là A→B→A hoặc dài hơn, hay self-loop A→A. Khi deep-copy theo policy giữ graph:

~~~text
 A --> B --> A

 A' --> B' --> A'
~~~

Cạnh quay lại phải trỏ tới **clone tương ứng**. Nếu một node child trong cloned graph trỏ về A nguồn, graph mới không còn độc lập và topology đã sai.

## 3. Shallow copy, deep copy và unfold thành cây

**Shallow copy** tạo object wrapper/root mới nhưng giữ references tới children cũ. Ví dụ copy một Node nhưng `newNode.next = oldNode.next` thì cả hai cùng giữ neighbor gốc. Nếu đó là immutable object hay collaborator được chủ đích share, có thể phù hợp; nếu mutable child thuộc graph cần copy, chưa đủ.

**Deep copy preserving graph topology** tạo clones cho mutable nodes trong scope và nối tất cả references qua mapping source→clone. Một source node được gặp nhiều lần vẫn chỉ có **một clone**.

**Unfold graph thành tree** cố ý nhân bản shared nodes theo mỗi đường đi. Điều này có thể hữu ích khi xuất từng path của một DAG, nhưng khác graph deep-copy; với cycles cần policy cắt/giới hạn depth, không thể unfold vô hạn.

**Immutable snapshot bằng IDs** có thể biểu diễn nodes và edges bằng các IDs thay vì Java reference cycles. Đây là lựa chọn tốt khi mục tiêu là bản chụp dữ liệu không đổi, không cần một mutable graph mới.

Không có một định nghĩa deep copy “sao chép mọi object reachable trong JVM” thích hợp cho mọi domain. Phải nói rõ loại fields/references nào thuộc copy scope và những dependencies nào tiếp tục được chia sẻ.

## 4. Vì sao thuật toán copy cây đơn giản không đủ?

Một method hay được viết:

~~~java
Node copy(Node original) {
    if (original == null) {
        return null;
    }
    Node result = new Node(original.name);
    for (Node child : original.children) {
        result.children.add(copy(child));
    }
    return result;
}
~~~

Đây là **method fragment**, giả định Node có `name`, `children` và constructor thích hợp.

Nó đúng trong điều kiện graph thực sự là cây không có shared mutable nodes hoặc cycles, và những fields cần copy đã được xử lý.

### 4.1. Khi cùng D có hai parents

~~~text
Nguồn:      B ──┐
                ├──> D
            C ──┘

Naive copy: B'──> D1'
            C'──> D2'
~~~

`D1' != D2'`, dù source chỉ có một D. Nếu clone D1' được sửa, clone D2' không thấy sự thay đổi; behavior khác graph gốc.

### 4.2. Khi có cycle

~~~text
A -> B -> D -> A -> B -> D -> ...
~~~

Nếu chưa lưu những nodes đã thấy, recursive copy không có điểm dừng; có thể gây `StackOverflowError`. **Bắt StackOverflowError không phải cách copy graph đúng.**

## 5. Bảng memo identity: lời giải cốt lõi

Ta cần một mapping duy nhất cho toàn bộ một lượt copy:

~~~text
Source reference     Cloned reference
A                    A'
B                    B'
C                    C'
D                    D'
~~~

Trong Java, lựa chọn thông thường:

~~~java
IdentityHashMap<Node, Node> memo = new IdentityHashMap<>();
~~~

`IdentityHashMap` so keys bằng reference identity, không theo `equals`/`hashCode` được class tự định nghĩa.

### 5.1. Vì sao không luôn dùng `HashMap<Node,Node>`?

Nếu class Node override `equals` theo label, hai source instances có cùng label có thể bị coi là cùng key trong HashMap. Thuật toán sẽ gộp references vốn khác nhau. Với graph topology, đó là sai.

`IdentityHashMap` thích hợp cho visited-by-reference, graph copy, cycle analysis; không thay HashMap trong các bài toán business cần logical key equality.

### 5.2. Không dùng name/id thay identity một cách mặc định

Hai source nodes có thể cùng name hoặc cùng một business ID tạm thời. Nếu dùng `Map<String,Node>` để cache copy, bạn có nguy cơ gộp hai nodes khác references. Khi cần **sao chép references**, hãy memo bằng **source object identity**. Khi domain muốn gộp theo stable business ID, đó là **normalization/deduplication operation riêng**, không phải implicit graph copy.

### 5.3. Memo dùng trong toàn bộ copy session

Không tạo memo mới cho mỗi child; nếu làm vậy, mọi sharing sẽ mất. Nếu copy nhiều roots cùng một graph và muốn giữ shared nodes giữa các roots, dùng **chung một memo** cho tất cả roots trong cùng lượt.

Không xóa memo khi quay lui từ recursion. Một node có thể xuất hiện lại qua nhánh khác; clone của nó phải được tái sử dụng.

## 6. Quy tắc vàng: allocate → register → populate

Thuật toán đúng với cycles thường đi theo trình tự:

1. Nếu input null, trả null hoặc xử lý theo policy.
2. Kiểm tra `memo`: nếu source đã có clone, **trả clone ấy ngay**.
3. Nếu chưa có, **cấp phát một clone shell** với fields có thể khởi tạo sớm.
4. **Ghi `memo.put(source, clone)` ngay**, trước khi đi theo child references.
5. Copy mutable scalar/value payloads theo ownership policy.
6. Duyệt edges, nối mỗi cloned edge tới `copy(child, memo)`.
7. Trả clone sau khi đã populate.

**Thứ tự đăng ký là mấu chốt:**

~~~text
ĐÚNG
allocate A' -> memo[A]=A' -> copy B -> B copy lại A -> reuse A'

SAI
allocate A' -> copy B -> B copy lại A -> allocate A'' -> ...
~~~

Một clone đã được đưa vào memo có thể **chưa hoàn thiện các fields/edges**; đó là cơ chế có chủ đích để xử lý backreferences. Vì vậy đừng publish clone cho observers/callbacks trước khi toàn bộ graph copy hoàn tất.

## 7. Chương trình hoàn chỉnh 1: DFS với `IdentityHashMap` bảo toàn cycles và sharing

Tạo tệp **`GraphDeepCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;

public class GraphDeepCopyDemo {
    static final class Node {
        private String name;
        private final List<Node> links = new ArrayList<>();

        Node(String name) {
            this.name = Objects.requireNonNull(name);
        }

        Node add(Node next) {
            links.add(next);
            return this;
        }

        String name() {
            return name;
        }

        void rename(String next) {
            name = Objects.requireNonNull(next);
        }
    }

    static Node deepCopy(Node source) {
        return copy(source, new IdentityHashMap<>());
    }

    private static Node copy(
            Node source,
            IdentityHashMap<Node, Node> memo) {
        if (source == null) {
            return null;
        }
        Node existing = memo.get(source);
        if (existing != null) {
            return existing;
        }

        Node target = new Node(source.name);
        memo.put(source, target); // Trước khi đi theo links.

        for (Node neighbor : source.links) {
            target.links.add(copy(neighbor, memo));
        }
        return target;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");
        Node d = new Node("D");

        a.add(b).add(c).add(a);
        b.add(d);
        c.add(d);
        d.add(a);

        Node copiedA = deepCopy(a);
        Node copiedB = copiedA.links.get(0);
        Node copiedC = copiedA.links.get(1);
        Node copiedDfromB = copiedB.links.get(0);
        Node copiedDfromC = copiedC.links.get(0);

        System.out.println("Root independent = " + (copiedA != a));
        System.out.println("Shared D = "
                + (copiedDfromB == copiedDfromC));
        System.out.println("Cycle to cloned root = "
                + (copiedDfromB.links.get(0) == copiedA));
        System.out.println("Self-loop = "
                + (copiedA.links.get(2) == copiedA));
        System.out.println("D independent = "
                + (copiedDfromB != d));

        copiedDfromB.rename("D-copy");
        System.out.println("Original D = " + d.name());
        System.out.println("Copied D = " + copiedDfromC.name());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 GraphDeepCopyDemo.java
java GraphDeepCopyDemo
~~~

**Stdout chính xác:**

~~~text
Root independent = true
Shared D = true
Cycle to cloned root = true
Self-loop = true
D independent = true
Original D = D
Copied D = D-copy
~~~

### 7.1. Bước sao chép A

Khi `copy(A)` bắt đầu, thuật toán tạo A' và **lưu memo[A] = A'**. Sau đó duyệt A→B. B' được tạo, memoized, rồi B→D; D' được tạo. D→A gặp A đã có trong memo nên D' trỏ A'. Vòng recursion về A kết thúc bình thường.

### 7.2. Bước sao chép C

Khi thuật toán trở lại A và đi A→C, C' được tạo. C→D gặp D đã có clone D'; C' được nối về **cùng D'** mà B' trỏ. Cuối cùng A→A được remap thành A'→A'.

### 7.3. Vì sao mutation cho kết quả đúng?

`copiedDfromB == copiedDfromC` true nên đổi D' qua đường B' có thể được quan sát qua đường C'. `copiedDfromB != d` true nên D nguồn vẫn tên `"D"`, còn D' tên `"D-copy"`. Bản sao vừa bảo vệ independence vừa giữ aliasing topology.

### 7.4. Giới hạn recursion

Với V nodes và E edges reachable, thuật toán duyệt mỗi node một lần và mỗi edge một lần: thời gian kỳ vọng **O(V+E)** với lookups trung bình hằng số, memo O(V), cloned structure O(V+E). Tuy nhiên call stack có thể sâu O(depth); một graph rất dài dù không có cycles vẫn có thể gây `StackOverflowError`. Khi depth lớn/không tin cậy, dùng iterative BFS/DFS.

## 8. Chương trình hoàn chỉnh 2: copy ngây thơ giữ giá trị nhưng mất sharing

Để cô lập lỗi shared reference, dùng một **DAG không có cycle**. Cả thuật toán naïve và memoized đều chạy hết, nhưng chỉ memoized giữ đúng topology.

Tạo tệp **`SharingPreservationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;

public class SharingPreservationDemo {
    static final class Node {
        final String label;
        final List<Node> children = new ArrayList<>();

        Node(String label) {
            this.label = label;
        }

        Node add(Node next) {
            children.add(next);
            return this;
        }
    }

    static Node naiveCopy(Node source) {
        if (source == null) {
            return null;
        }
        Node result = new Node(source.label);
        for (Node child : source.children) {
            result.children.add(naiveCopy(child));
        }
        return result;
    }

    static Node smartCopy(Node source) {
        return smartCopy(source, new IdentityHashMap<>());
    }

    private static Node smartCopy(
            Node source,
            IdentityHashMap<Node, Node> memo) {
        if (source == null) {
            return null;
        }
        Node existing = memo.get(source);
        if (existing != null) {
            return existing;
        }
        Node result = new Node(source.label);
        memo.put(source, result);
        for (Node child : source.children) {
            result.children.add(smartCopy(child, memo));
        }
        return result;
    }

    public static void main(String[] args) {
        Node root = new Node("root");
        Node left = new Node("left");
        Node right = new Node("right");
        Node shared = new Node("shared");

        root.add(left).add(right);
        left.add(shared);
        right.add(shared);

        Node naive = naiveCopy(root);
        Node proper = smartCopy(root);

        Node naiveLeft = naive.children.get(0).children.get(0);
        Node naiveRight = naive.children.get(1).children.get(0);
        Node goodLeft = proper.children.get(0).children.get(0);
        Node goodRight = proper.children.get(1).children.get(0);

        System.out.println("Source shared = "
                + (left.children.get(0) == right.children.get(0)));
        System.out.println("Naive preserves sharing = "
                + (naiveLeft == naiveRight));
        System.out.println("Memo preserves sharing = "
                + (goodLeft == goodRight));
        System.out.println("Clone independent = "
                + (goodLeft != shared));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 SharingPreservationDemo.java
java SharingPreservationDemo
~~~

**Stdout chính xác:**

~~~text
Source shared = true
Naive preserves sharing = false
Memo preserves sharing = true
Clone independent = true
~~~

**Điều quan trọng:** naïve version vẫn tạo các clones tách source; nhưng vì copy shared node hai lần, nó **không còn là graph preserving topology**. Nếu API chủ đích “unfold mỗi nhánh thành một tree độc lập” thì behavior này có thể đúng, nhưng phải nêu rõ contract và tránh cycles vô hạn.

## 9. Chương trình hoàn chỉnh 3: hai nodes `equals` nhau không phải một source reference

Memo `HashMap` thông thường có thể gộp hai nodes nếu class override `equals` theo dữ liệu. Chương trình sau cố ý tạo hai instances label X và kiểm tra `IdentityHashMap` không gộp chúng.

Tạo tệp **`IdentityMemoDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;

public class IdentityMemoDemo {
    static final class Node {
        final String label;
        final List<Node> edges = new ArrayList<>();

        Node(String label) {
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Node n && label.equals(n.label);
        }

        @Override
        public int hashCode() {
            return label.hashCode();
        }
    }

    static Node copy(
            Node source,
            IdentityHashMap<Node, Node> memo) {
        if (source == null) {
            return null;
        }
        Node existing = memo.get(source);
        if (existing != null) {
            return existing;
        }

        Node cloned = new Node(source.label);
        memo.put(source, cloned);
        for (Node edge : source.edges) {
            cloned.edges.add(copy(edge, memo));
        }
        return cloned;
    }

    public static void main(String[] args) {
        Node root = new Node("R");
        Node firstX = new Node("X");
        Node secondX = new Node("X");
        root.edges.add(firstX);
        root.edges.add(secondX);

        IdentityHashMap<Node, Node> memo = new IdentityHashMap<>();
        Node clonedRoot = copy(root, memo);

        System.out.println("Values equal = "
                + firstX.equals(secondX));
        System.out.println("References distinct = "
                + (firstX != secondX));
        System.out.println("Copied nodes distinct = "
                + (clonedRoot.edges.get(0)
                        != clonedRoot.edges.get(1)));
        System.out.println("Not original X = "
                + (clonedRoot.edges.get(0) != firstX));
        System.out.println("Memo count = " + memo.size());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 IdentityMemoDemo.java
java IdentityMemoDemo
~~~

**Stdout chính xác:**

~~~text
Values equal = true
References distinct = true
Copied nodes distinct = true
Not original X = true
Memo count = 3
~~~

Cả firstX và secondX có logical equality true (do label cùng X) nhưng identity khác. Memo chứa Root, firstX và secondX, cho ra ba clones. Việc copy object graph theo references không được trộn với hoạt động nghiệp vụ **deduplicate theo value**.

## 10. DFS đệ quy hay BFS/DFS lặp?

Một algorithm đệ quy với memo xử lý cycles nhưng vẫn có thể stack overflow với chain dài. Một **work queue** cho phép thực hiện BFS lặp:

1. Clone root, đưa root→clone vào memo và root vào queue.
2. Lấy một source node từ queue.
3. Lấy clone tương ứng trong memo.
4. Duyệt từng neighbor:
   - Nếu null, xử lý null theo policy.
   - Nếu neighbor chưa có trong memo, tạo clone và thêm vào queue.
   - Thêm edge trỏ tới **clone của neighbor**.
5. Lặp đến khi queue trống, trả clone root.

Tất cả clone allocations và registrations xảy ra **trước khi node được dùng như neighbor của cloned graph**, nên backreferences không làm lặp vô hạn.

### 10.1. Chương trình hoàn chỉnh 4: BFS với cycles, shared nodes và null/duplicate edges

Tạo tệp **`IterativeGraphCopyDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;

public class IterativeGraphCopyDemo {
    static final class Node {
        String id;
        final List<Node> edges = new ArrayList<>();

        Node(String id) {
            this.id = id;
        }

        Node add(Node next) {
            edges.add(next);
            return this;
        }
    }

    static Node copyGraph(Node root) {
        if (root == null) {
            return null;
        }

        IdentityHashMap<Node, Node> memo = new IdentityHashMap<>();
        ArrayDeque<Node> pending = new ArrayDeque<>();

        memo.put(root, new Node(root.id));
        pending.add(root);

        while (!pending.isEmpty()) {
            Node original = pending.removeFirst();
            Node cloned = memo.get(original);

            for (Node neighbor : original.edges) {
                if (neighbor == null) {
                    cloned.edges.add(null);
                    continue;
                }

                if (!memo.containsKey(neighbor)) {
                    memo.put(neighbor, new Node(neighbor.id));
                    pending.addLast(neighbor);
                }
                cloned.edges.add(memo.get(neighbor));
            }
        }

        return memo.get(root);
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node c = new Node("C");
        Node d = new Node("D");

        a.add(b).add(c).add(b).add(null);
        b.add(d);
        c.add(d);
        d.add(a);

        Node clonedA = copyGraph(a);
        Node clonedB = clonedA.edges.get(0);
        Node clonedC = clonedA.edges.get(1);
        Node clonedD = clonedB.edges.get(0);

        System.out.println("Duplicate edge preserved = "
                + (clonedA.edges.get(0) == clonedA.edges.get(2)));
        System.out.println("Shared D = "
                + (clonedD == clonedC.edges.get(0)));
        System.out.println("Cycle to cloned A = "
                + (clonedD.edges.get(0) == clonedA));
        System.out.println("Null preserved = "
                + (clonedA.edges.get(3) == null));
        System.out.println("Independent root = " + (clonedA != a));

        clonedB.id = "B-copy";
        System.out.println("Original B = " + b.id);
        System.out.println("Cloned B = " + clonedB.id);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 IterativeGraphCopyDemo.java
java IterativeGraphCopyDemo
~~~

**Stdout chính xác:**

~~~text
Duplicate edge preserved = true
Shared D = true
Cycle to cloned A = true
Null preserved = true
Independent root = true
Original B = B
Cloned B = B-copy
~~~

### 10.2. Vì sao null không enqueue?

`ArrayDeque` không chấp nhận null values. Nếu graph policy cho phép null edge slots, copy giữ nguyên null trong cloned List thay vì đưa null vào queue. Nếu domain cấm null edges, nên validate và ném exception chứ không âm thầm bỏ qua.

### 10.3. Complexity và giới hạn thực tế

Với V nodes reachable và E edges, DFS/BFS memoized có thời gian kỳ vọng **O(V+E)**, O(V) memo, copy structure O(V+E). Iterative BFS tránh Java call-stack sâu, nhưng queue có thể chiếm O(V) và heap memory vẫn phải đủ. Nếu object graph cực lớn, cần memory/size limits hoặc chuyển thành streaming immutable snapshots.

## 11. Copy mutable payloads, không chỉ remap edges

Một graph clone đã giữ đúng A'→B' nhưng còn trỏ chung một mutable `byte[]`, `Date` hoặc `List<MutableItem>` với source có thể vẫn không độc lập.

Ví dụ:

~~~java
class Node {
    byte[] data;
    List<Node> edges;
}
~~~

Nếu `clone.data = original.data` thì caller mutate bytes ở clone sẽ đổi source. Phải có một policy theo field:

- `String`, `Instant`, immutable value classes: có thể reuse.
- Primitive fields: copy values.
- `byte[]`, `int[]`: clone/copy arrays.
- `List<Node>`: tạo List mới và remap từng Node qua memo.
- `Map<String,Node>`: tạo Map mới, remap values.
- `List<MutableItem>`: copy List và Item khi Item nằm trong mutable ownership scope.
- Services/resources: thường không tự deep-clone.
- Final references: vẫn có thể trỏ mutable content; final không tự deep immutable.

### 11.1. Chương trình hoàn chỉnh 5: copy cả payload và self-cycle

Tạo tệp **`GraphPayloadCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;

public class GraphPayloadCopyDemo {
    static final class Node {
        final String name;
        private final byte[] payload;
        private final List<Node> edges = new ArrayList<>();

        Node(String name, byte[] input) {
            this.name = Objects.requireNonNull(name);
            payload = Objects.requireNonNull(input).clone();
        }

        byte[] payload() {
            return payload.clone();
        }
    }

    static Node deepCopy(Node source) {
        return copy(source, new IdentityHashMap<>());
    }

    private static Node copy(
            Node source,
            IdentityHashMap<Node, Node> memo) {
        if (source == null) {
            return null;
        }
        Node existing = memo.get(source);
        if (existing != null) {
            return existing;
        }

        Node target = new Node(source.name, source.payload);
        memo.put(source, target);
        for (Node edge : source.edges) {
            target.edges.add(copy(edge, memo));
        }
        return target;
    }

    public static void main(String[] args) {
        byte[] external = {1, 2};
        Node source = new Node("A", external);
        source.edges.add(source);

        external[0] = 9;
        Node cloned = deepCopy(source);

        // Chỉ enclosing demo được truy cập private payload để test.
        cloned.payload[0] = 7;

        System.out.println("Source payload = "
                + Arrays.toString(source.payload()));
        System.out.println("Cloned payload = "
                + Arrays.toString(cloned.payload()));
        System.out.println("Arrays independent = "
                + (source.payload != cloned.payload));
        System.out.println("Cloned self-cycle = "
                + (cloned.edges.get(0) == cloned));
        System.out.println("Nodes independent = "
                + (source != cloned));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 GraphPayloadCopyDemo.java
java GraphPayloadCopyDemo
~~~

**Stdout chính xác:**

~~~text
Source payload = [1, 2]
Cloned payload = [7, 2]
Arrays independent = true
Cloned self-cycle = true
Nodes independent = true
~~~

Constructor Node sao chép byte array đầu vào, nên sửa `external` không tác động source Node. Graph copier tạo Node mới qua constructor, nên cloned payload cũng là byte array riêng. Getter `payload()` trả copy, không lộ nội bộ. Enclosing demo cố ý sửa private payload của cloned Node để chứng minh source vẫn không đổi; đây không phải lời khuyên cung cấp public mutable accessor.

## 12. Snapshot bất biến bằng IDs: biểu diễn shared references và cycles không cần object cycles

Không phải lúc nào người dùng cũng cần một **graph mutable mới**. Khi cần lưu trữ, xuất dữ liệu hoặc lưu lại trạng thái ở một thời điểm, có thể dùng **immutable graph snapshot**:

~~~text
Node 1: A, outgoing=[2,3,2]
Node 2: B, outgoing=[1]
Node 3: C, outgoing=[2]
~~~

- Node 1 có hai edges trỏ node 2: duplicate links vẫn được giữ.
- Node 2 trỏ node 1: một cycle.
- Không cần Java records trực tiếp giữ reference vòng.
- Có thể validate mọi outgoing ID đều tồn tại.
- Có thể mô hình hóa graph thành immutable records/collections.

### 12.1. Chương trình hoàn chỉnh 6: Graph snapshot với records

Tạo tệp **`GraphIdSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class GraphIdSnapshotDemo {
    record NodeView(int id, String name, List<Integer> outgoing) {
        NodeView {
            if (id < 1) {
                throw new IllegalArgumentException("ID không hợp lệ");
            }
            Objects.requireNonNull(name);
            outgoing = List.copyOf(outgoing);
        }
    }

    record Snapshot(Map<Integer, NodeView> nodes, int rootId) {
        Snapshot {
            nodes = Map.copyOf(nodes);
            if (!nodes.containsKey(rootId)) {
                throw new IllegalArgumentException("Thiếu root");
            }
            for (Map.Entry<Integer, NodeView> e
                    : nodes.entrySet()) {
                if (e.getKey() != e.getValue().id()) {
                    throw new IllegalArgumentException("ID mismatch");
                }
                for (int next : e.getValue().outgoing()) {
                    if (!nodes.containsKey(next)) {
                        throw new IllegalArgumentException("Dangling edge");
                    }
                }
            }
        }

        NodeView root() {
            return nodes.get(rootId);
        }
    }

    public static void main(String[] args) {
        List<Integer> edges = new ArrayList<>(List.of(2, 3, 2));
        Map<Integer, NodeView> input = new HashMap<>();

        input.put(1, new NodeView(1, "A", edges));
        input.put(2, new NodeView(2, "B", List.of(1)));
        input.put(3, new NodeView(3, "C", List.of(2)));

        Snapshot snapshot = new Snapshot(input, 1);

        edges.add(1);
        input.clear();

        System.out.println("Root = " + snapshot.root().name());
        System.out.println("Outgoing = " + snapshot.root().outgoing());
        System.out.println("Unique nodes = "
                + snapshot.nodes().size());
        System.out.println("Cycle to root = "
                + (snapshot.nodes().get(2).outgoing().get(0)
                        == snapshot.rootId()));
        System.out.println("Duplicate link = "
                + snapshot.root().outgoing().get(0).equals(
                        snapshot.root().outgoing().get(2)));

        try {
            snapshot.root().outgoing().add(4);
        } catch (UnsupportedOperationException ex) {
            System.out.println("Edges unmodifiable");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 GraphIdSnapshotDemo.java
java GraphIdSnapshotDemo
~~~

**Stdout chính xác:**

~~~text
Root = A
Outgoing = [2, 3, 2]
Unique nodes = 3
Cycle to root = true
Duplicate link = true
Edges unmodifiable
~~~

### 12.2. Vì sao snapshot ở đây bất biến theo contract?

`NodeView` chứa primitives, immutable String và một unmodifiable List snapshot của Integer IDs. `Snapshot` chụp outer Map qua `Map.copyOf`. Caller thay `edges` hoặc `input` sau construction không thay internal snapshot. Generated record accessors trả immutable references phù hợp.

Không giả định `Map.copyOf` giữ insertion order của nguồn, nên chương trình chỉ tra theo ID và in List có order rõ. Nếu Map values là mutable objects, `Map.copyOf` sẽ **không deep-copy** chúng; phải kiểm soát representation ở từng tầng.

### 12.3. Copy graph bằng IDs và identity mapping

Nếu đầu vào là graph object reference, quá trình tạo snapshot cần map **source reference → generated integer ID** theo identity. Khi gặp lại cùng reference, reuse ID để giữ sharing/cycle; với two distinct source instances dù equals true, IDs phải khác nếu preserve topology là mục tiêu.

Lưu IDs trong snapshot không đồng nghĩa dùng `System.identityHashCode` làm ID lâu dài. `identityHashCode` không bảo đảm unique. Nên cấp IDs theo traversal/session có kiểm soát hoặc dùng stable domain IDs nếu contract cho phép.

## 13. Graph gồm nhiều concrete classes

Một graph thật thường có nhiều loại object:

~~~text
Order --> Customer
  |
  +----> Line --> Product
                  |
                  +--> Price
~~~

Có thể có `Order`, `Customer`, `Product` với constructors và fields khác nhau. Một copier luôn `new BaseNode(...)` sẽ làm mất subtype-specific state/behavior.

Cách tiếp cận:

1. Xác định tập types được hỗ trợ.
2. Cấp phát clone shell **đúng concrete type** hoặc một immutable DTO phù hợp.
3. Ghi source→clone vào **memo chung** trước khi populate references.
4. Copy scalar fields và mutable components theo policy.
5. Remap outgoing links tới các clones bằng cùng memo.
6. Sau khi graph hoàn tất, validate invariants và publish root.

### 13.1. `final` fields làm two-phase construction khó hơn

Một class có `private final Node parent` không cho phép tạo empty shell rồi gán field parent ở bất kỳ instance method nào. Với cycles ở final references, có thể cần:

- Builders/wiring stage sau đó tạo representation khác.
- ID-based snapshot, tránh trực tiếp tạo reference cycle.
- Indirection qua holder được thiết kế cẩn thận.
- Một copy factory có hỗ trợ construction order và invariants riêng.

Không dùng reflection/Unsafe để sửa final fields ngoài language rules như một giải pháp mặc định; điều đó phá encapsulation, module access và có thể gây các vấn đề memory visibility.

### 13.2. Constructors có side effects

Copy một domain entity bằng constructor bình thường có thể phát event, sinh ID, mở resource hoặc đăng ký vào registry. Nếu chỉ cần một snapshot, những side effects ấy thường sai. Thiết kế **copy constructor/factory riêng** có contract rõ hoặc convert sang immutable DTOs.

### 13.3. Business identity có giữ hay đổi?

`source != cloned` chỉ chứng minh reference identity khác. Nó không tự trả lời **CustomerId, OrderId hoặc database ID** phải khác. Nếu clone là bản chụp cùng thực thể, giữ ID có thể đúng. Nếu clone là tạo một entity nghiệp vụ mới, có thể cần ID mới và cập nhật mọi relationships. Hãy quyết định theo domain, không theo thuật toán đồ thị.

## 14. Collections trong graph: List, Set, Map, arrays

### 14.1. List

Clone outer List mới, đi lần lượt từng element:

~~~java
for (Node n : source.links) {
    target.links.add(copy(n, memo));
}
~~~

Giữ **order**, **null slots** nếu cho phép, và **duplicate edges**. Chuyển List sang Set sẽ thay semantics khi nguồn có repeated edge.

### 14.2. Arrays

Với `Node[]`, tạo array mới cùng length rồi remap mỗi slot qua memo; chỉ gọi `sourceArray.clone()` sẽ shallow-copy Node references, chưa clone graph.

Với primitive arrays như `byte[]`, clone từng array có thể đủ vì elements không chứa references.

### 14.3. Map

`Map<String,Node>`: tạo Map mới, String keys immutable, values Node remap qua memo. Nếu iteration order là contract, cần chọn Map implementation/order contract phù hợp; không giả định mọi HashMap có stable iteration order.

`Map<Node,Node>`: cần xem remap **cả keys lẫn values**. Chọn map type theo logical/identity equality của graph mới.

### 14.4. Set và mutable keys

Nếu Node.equals/hashCode phụ thuộc fields chưa được populate, chèn clone Node vào `HashSet`/`HashMap` **trước khi fields ổn định** có thể tạo lỗi mutable hash keys. Giải pháp:

- Populate equality-relevant fields trước khi chèn vào hash collection.
- Dùng identity-based Set/Map nếu relation được định nghĩa bằng identity.
- Dùng immutable IDs/keys cho collection output.

Memo `IdentityHashMap` chỉ là bảng theo dõi nội bộ, **không bắt buộc cloned business Map cũng dùng IdentityHashMap**.

## 15. Graph có nhiều roots hoặc disconnected components

Một `deepCopy(root)` chỉ sao chép **reachable nodes** theo các edges mà thuật toán duyệt. Nếu một component không reachable từ root, nó không tự được copy.

Nếu cần sao chép nhiều roots và giữ sharing giữa chúng, phải dùng cùng memo:

~~~java
IdentityHashMap<Node, Node> memo = new IdentityHashMap<>();
Node copiedFirst = copy(firstRoot, memo);
Node copiedSecond = copy(secondRoot, memo);
~~~

Đây là fragment, giả định method `copy` và class Node có sẵn. Nếu dùng memo riêng cho từng root, shared descendant có thể bị clone hai lần, làm mất sharing giữa các components có giao nhau.

### 15.1. Null roots và dangling references

API có thể định nghĩa `deepCopy(null) == null` hoặc ném exception; tùy contract. Với ID snapshots, một outgoing ID không tồn tại trong nodes table là **dangling edge** và cần validate hoặc được phép biểu diễn external link theo schema rõ.

### 15.2. Recursive processing không cần clear memo khi return

Memo phục vụ **toàn bộ copy session**, không phải local recursion path. Nếu xóa mapping sau khi một node xử lý xong, node khác đến nó qua đường khác sẽ clone lại nó; sharing mất.

## 16. Tốc độ, stack và memory

Với graph có V nodes và E edges:

- Memoized DFS/BFS thông thường duyệt mỗi node một lần, mỗi edge một lần: kỳ vọng **O(V+E)** time khi identity lookup trung bình O(1).
- Memo cần O(V) references; cloned edges cần O(E) memory.
- Recursive DFS có call stack O(depth), có thể gặp StackOverflowError với graph rất sâu.
- Iterative BFS tránh recursion-stack growth nhưng queue có thể chiếm O(V).
- Clone mutable payload arrays/collections thêm thời gian và memory tương ứng size của payloads.
- Graph quá lớn vẫn có thể gây `OutOfMemoryError`; iterative không miễn nhiễm memory limits.

**Đừng sao chép một graph rất lớn chỉ để trả một vài fields** nếu immutable projection/snapshot của phần cần thiết đủ. Xem performance dựa trên workload thực tế và giới hạn input.

## 17. Concurrency: memo đúng vẫn chưa bảo đảm snapshot nhất quán

Nếu threads khác sửa graph trong khi copier duyệt:

- A được copy trước khi edge thay đổi, B được copy sau thay đổi.
- List có thể thay đổi giữa iteration.
- Mutable payload có thể bị sửa lúc đang copy.
- Graph mới có thể kết hợp dữ liệu của nhiều thời điểm, không tương ứng snapshot nguyên tử nào.

`IdentityHashMap` chỉ giải quyết **identity/topology của những references mà copier quan sát**, không giải quyết data races hay atomic snapshot.

Có thể cần:

1. Toàn bộ graph được owner bảo vệ bằng read/write lock cùng protocol.
2. Immutable/versioned graph state, snapshot theo một version.
3. Transactional read từ persistence nếu graph bắt nguồn từ database.
4. Optimistic version validation có khả năng phát hiện tất cả thay đổi liên quan.
5. Copy-on-write nếu phần lớn dữ liệu immutable.

`volatile` ở một edge field không tự làm traversal nhiều nodes atomic. Một builder/copier cũng không nên publish root clone trước khi các edges của nó đã được populate và invariant được kiểm tra.

## 18. External resources và ownership

Một object graph có thể chứa references đến:

- Database Connection, transaction/session.
- Socket, file channel, InputStream/OutputStream.
- Thread, ExecutorService, locks.
- Logger, cache, dependency injection service.
- Native handle hoặc tài nguyên ngoài JVM.

Những thứ này thường **không nên deep-clone vô điều kiện**. Copy một reference String đường dẫn file không tự copy nội dung file. Copy một object chứa Connection không tự tạo một database transaction tương đương.

Chọn policy rõ:

- **Share service reference** vì đó là dependency ngoài copy scope.
- **Omit resource** khỏi immutable snapshot.
- **Rebind/reinject** resource từ owner.
- **Copy immutable resource descriptor/ID** chứ không copy live handle.
- **Transfer ownership** nếu API cho phép, thay vì copy.

Đối với locks, copy một monitor object có thể làm thay đổi coordination semantics; giữ nguyên lock lại làm clone phụ thuộc nguồn. Vì vậy concurrency resources phải được xem như trường hợp riêng, không như mutable data bình thường.

## 19. Errors và partial copies

Nếu constructor của một clone ném exception giữa quá trình sao chép:

- Memo có thể chứa các partially initialized clones.
- Graph vẫn chưa hoàn thiện.
- Callers không được nhận clone như kết quả thành công.
- External side effects đã xảy ra không tự rollback vì Java exception.

Thiết kế thực tế:

- Dùng local memo chỉ tồn tại trong một copy operation.
- Validate đầu vào/schema trước khi publish.
- Dùng copy constructors/factories ít side effects.
- Nếu copy tạo resources, có cleanup/close policy phù hợp.
- Không mutate graph nguồn trong khi dựng bản sao.
- Trả cloned root **chỉ sau khi toàn bộ copy kết thúc bình thường**.

Một cloned graph object **không nên thoát ra ngoài** qua event/callback/global registry trước khi wiring complete; nếu không, thread khác có thể quan sát edges chưa đầy đủ.

## 20. `clone()` và serialization có giải quyết bài toán tự động không?

### 20.1. `Object.clone()` thường là shallow

Nếu class implements Cloneable và dùng `super.clone()`, nó thường tạo shallow copy của fields. Một `Node next` vẫn có thể trỏ tới source child. Với cycles và sharing, cần memo và remap; gọi `child.clone()` đệ quy mà không dùng memo vẫn có thể lặp vô hạn hoặc nhân đôi shared node.

### 20.2. Copy constructors không tự xử lý cycles

Một `new Node(oldNode)` nhận fields có thể hữu ích để copy scalar/mutable payloads, nhưng nếu constructor đệ quy tạo các children trước khi đăng ký clone trong memo, vấn đề cycles vẫn còn. Copy constructor chỉ giải quyết đúng những fields và constructor graph protocol mà nó được thiết kế hỗ trợ.

### 20.3. Java serialization round-trip không phải deep copy phổ dụng

Serialization có thể bảo toàn sharing/cycles của serializable object graphs trong những điều kiện và hooks phù hợp, nhưng:

- Không phải mọi class/resource đều serializable.
- `transient`/`static` fields và custom hooks có behaviors riêng.
- Deserialization của dữ liệu không tin cậy có security risks.
- Constructors/invariants/compatibility cần xem xét.
- External resources/business identity không tự được sao chép đúng.

Không nên coi native serialization như một copy strategy mặc định. Explicit mapping hoặc ID snapshots thường minh bạch hơn.

## 21. Kiểm thử graph copy: phải dùng `==` ở đúng chỗ

Một test `source.equals(clone)` có thể pass dù sharing/cycles sai, vì equals thường chỉ so một vài scalar fields. Cần kiểm tra:

1. **Independence:** copied root != original root; cloned mutable nodes khác mọi original mutable nodes trong copy scope.
2. **Preserved sharing:** hai source edges cùng target thì hai cloned edges cùng target bằng `==`.
3. **Preserved cycles:** back edge của clone trỏ cloned ancestor, không trỏ source.
4. **Self-loop:** clonedSelf == clonedRoot.
5. **Repeated edges:** List giữ đúng positions và references.
6. **Null edges:** null slots còn đúng theo policy.
7. **Scalar values:** các labels/data values tương ứng.
8. **Mutable payload isolation:** sửa clone không đổi nguồn, và ngược lại nếu source còn có thể mutate.
9. **Equals-equal but reference-distinct nodes:** không bị gộp.
10. **Multiple roots:** shared descendants được reuse khi dùng memo chung.
11. **Very deep chain:** chọn iterative để tránh stack overflow.
12. **Concurrency:** nếu snapshot phải atomic, có tests/validation cho locking/versioning protocol.

### 21.1. Mutation test cho sharing

Trong graph nguồn, nếu B và C cùng trỏ D, copy phải cho B' và C' cùng D'. Sau đó đổi D' qua đường B', đọc D' qua đường C' thấy giá trị mới; D nguồn giữ giá trị cũ.

Đây là test mạnh hơn chỉ so tên của B'/C' vì nó kiểm tra **aliasing behavior**.

### 21.2. Một source node ↔ một clone node

Một graph-copy mapping preserving topology phải không tạo hai clones cho cùng source reference; cũng không gộp hai source references khác nhau. Đó là quan hệ bijection trong phạm vi các mutable nodes được copy.

## 22. Bảng so sánh chiến lược

| Chiến lược | Giữ shared references | Xử lý cycles | Chi phí/giới hạn |
| --- | --- | --- | --- |
| Shallow copy | Share với **source** | Có thể giữ links về source | Không độc lập với mutable children |
| Naive copy tree | Không bảo đảm | Có thể vô hạn | Chỉ phù hợp cây thật sự |
| Memoized DFS | Có | Có | Recursion stack có thể sâu |
| Memoized iterative BFS/DFS | Có | Có | Queue/memo chiếm memory |
| Immutable ID snapshot | Bằng repeated IDs | Bằng ID links | Cần schema/ID mapping/validation |
| Domain-specific mapper | Theo policy | Khi được thiết kế | Phải xác định type/field semantics |
| Serialization round-trip | Tùy mechanism | Có thể | Security/compatibility/resource constraints |
| Persistent immutable graph | Có structural sharing có chủ đích | Tùy data model | Thiết kế riêng, cập nhật theo versions |

## 23. Những lỗi thường gặp

1. Dùng naïve recursion cho graph có cycles.
2. Đăng ký memo sau khi clone children.
3. Dùng `HashMap` memo trong khi Node.equals có thể gộp distinct references.
4. Dùng label hoặc mutable business ID làm identity của source.
5. Tạo memo riêng cho mỗi child/root mặc dù graphs có shared descendants.
6. Dùng visited Set mà không lưu source→clone references.
7. Xóa memo khi quay lui recursion.
8. Không remap self-loop/back edge về cloned node.
9. Copy outer List nhưng vẫn giữ Node references nguồn.
10. Không copy mutable payload arrays/Date/nested List.
11. Copy immutable Strings vô ích.
12. Dùng Set để thay List edges, mất duplicates/order.
13. Không xử lý null edges mà enqueue null vào ArrayDeque.
14. Dùng recursive DFS cho graph có chuỗi rất dài, gặp stack overflow.
15. Dùng BFS nhưng quên memo, vẫn duplicate nodes/cycles.
16. Map copy sai semantics keys/values, nhất là mutable hash keys.
17. Dùng domain constructor gây event/registry side effects khi chỉ muốn snapshot.
18. Chọn clone type theo compile-time superclass làm mất subtype fields.
19. Cố điền final cyclic references bằng reflection/Unsafe.
20. Deep-clone external resources không có copy contract.
21. Đổi business IDs tùy tiện khi copy.
22. Publish clone trước khi hoàn tất graph.
23. Coi memo identity là cơ chế atomic snapshot khi graph bị concurrent mutation.
24. So `equals` thay `==` trong topology tests.
25. Cho rằng Object.clone tự deep-copy.
26. Dùng native serialization với untrusted data.
27. Không validate dangling IDs khi dùng ID-based snapshot.
28. Dựa vào iteration order của Map.copyOf.
29. Không xử lý partially created nodes nếu copy thất bại.
30. Không nêu rõ copy scope và tài nguyên được share.

## 24. Bài tập tự kiểm tra có đáp án

**Câu 1.** B và C cùng trỏ D trong graph nguồn. Trong clone preserving topology, cần quan hệ gì?

**Đáp án:** B'.link == C'.link và đều trỏ tới một D' khác D nguồn.

**Câu 2.** Vì sao phải gọi `memo.put(source, clone)` trước khi duyệt children?

**Đáp án:** Để backreferences/cycles tìm thấy clone đã cấp phát, không tạo clone khác và không đệ quy vô hạn.

**Câu 3.** Tại sao `IdentityHashMap` phù hợp hơn `HashMap` cho graph-copy memo?

**Đáp án:** Nó dùng reference identity làm key, không gộp hai source instances chỉ vì equals true.

**Câu 4.** `a.equals(b)` true có chứng minh a==b không?

**Đáp án:** Không. Equality theo values khác identity.

**Câu 5.** Copy graph có thể trả original immutable String label mà vẫn là deep copy đúng không?

**Đáp án:** Có, nếu copy policy cho phép reuse immutable values. Không cần nhân bản immutable strings.

**Câu 6.** Copy List of Nodes bằng `new ArrayList<>(source.links)` có đủ không?

**Đáp án:** Không nếu Nodes cần clone; List mới vẫn giữ references tới source nodes.

**Câu 7.** A tự trỏ A, clone thế nào?

**Đáp án:** A' phải tự trỏ A': `A'.self == A'`.

**Câu 8.** Với A→B→A, naïve recursion có thể xảy ra gì?

**Đáp án:** Không dừng/stack overflow nếu không memo hoặc cycle policy.

**Câu 9.** Memo có cần dùng chung giữa nhiều roots có shared descendants không?

**Đáp án:** Có nếu muốn bảo toàn sharing xuyên những cloned roots.

**Câu 10.** DFS memoized có thể stack overflow không?

**Đáp án:** Có khi graph depth rất lớn; memo ngăn cycles nhưng không làm call stack biến mất.

**Câu 11.** BFS iterative có cần memo không?

**Đáp án:** Có, để reuse clones và tránh lặp vô hạn.

**Câu 12.** ArrayDeque có chấp nhận null entries không?

**Đáp án:** Không. Xử lý null edges riêng.

**Câu 13.** Nếu source List chứa [B,C,B], clone cần gì?

**Đáp án:** [B',C',B'] với hai references tới B' cùng identity.

**Câu 14.** Nếu Clone D' có byte[] payload chung với D nguồn thì đã độc lập chưa?

**Đáp án:** Chưa đối với payload mutable; phải copy array phù hợp.

**Câu 15.** Vì sao clone graph không nhất thiết clone database Connection?

**Đáp án:** Connection là resource có lifecycle/ownership; deep copy đối tượng trong heap không có nghĩa copy transaction/service.

**Câu 16.** Source graph có hai distinct nodes nhưng cùng label. Memo nên làm gì?

**Đáp án:** Tạo hai clones riêng nếu muốn bảo toàn reference identity.

**Câu 17.** Một `final Node parent` cyclic relationship có thể làm shell-then-populate khó không?

**Đáp án:** Có; final assignment constraints có thể đòi builder/indirection/ID representation.

**Câu 18.** Copy Graph bằng immutable ID snapshot có biểu diễn được cycles không?

**Đáp án:** Có, thông qua edges chứa IDs quay lại node đã tồn tại.

**Câu 19.** Map.copyOf có tự deep-copy mutable NodeView values không?

**Đáp án:** Không. Values phải là immutable hoặc được copy theo policy.

**Câu 20.** Một graph bị thread khác sửa khi copy có được atomic snapshot nhờ IdentityHashMap không?

**Đáp án:** Không. Cần locking/versioning/immutable graph state phù hợp.

**Câu 21.** Độ phức tạp time thường gặp cho memoized traversal là gì?

**Đáp án:** O(V+E) kỳ vọng khi mỗi node/edge được xử lý một lần và identity lookup trung bình O(1).

**Câu 22.** `source != clone` đã đủ chứng minh deep copy chưa?

**Đáp án:** Không; cloned neighbors/payloads có thể vẫn trỏ tới source.

**Câu 23.** Cần kiểm tra gì ngoài labels?

**Đáp án:** Sharing bằng ==, cycles, independence bằng !=, repeated/null edges, mutable payload isolation.

**Câu 24.** Nếu copy constructor tạo database event, có rủi ro gì?

**Đáp án:** Copy graph nhân đôi side effects dù chỉ muốn snapshot; nên dùng copy factory không có những tác động đó.

**Câu 25.** Một node source nằm ngoài phần reachable từ root có được copy bởi `copy(root)` không?

**Đáp án:** Không, trừ khi API chọn thêm roots hoặc duyệt những references khác.

**Câu 26.** Vì sao không clear memo khi đi qua nhánh mới?

**Đáp án:** Node source có thể được gặp lại ở nhánh khác; clear sẽ làm duplicate cloned node.

**Câu 27.** HashMap cloned graph có key là mutable clone còn đang populate thì sao?

**Đáp án:** Không nên insert khi equality/hash-relevant fields chưa ổn định; có thể gây stale hash lookup.

**Câu 28.** Khi nào nên dùng snapshot dạng IDs thay mutable graph?

**Đáp án:** Khi mục tiêu là lưu/report/so sánh một trạng thái bất biến, validate references và biểu diễn cycles/sharing dễ hơn.

**Câu 29.** Copying graph có bắt buộc cấp business ID mới không?

**Đáp án:** Không; copy reference identity khác domain identity. Phải theo mục đích snapshot hay tạo entity mới.

**Câu 30.** Nguyên tắc cốt lõi nào ngăn cả nhân đôi shared node và đệ quy cycle?

**Đáp án:** Dùng source identity→clone mapping chung, **đăng ký clone trước khi đi theo references**.

## 25. Checklist thiết kế trước khi sao chép object graph

1. Graph có references dùng chung không?
2. Có cycles/self-loops/backreferences không?
3. Có null edges hay duplicate links không?
4. Muốn copy graph topology hay unfold paths thành tree?
5. Đã xác định scope nodes/edges phải copy chưa?
6. Memo có dùng source reference identity không?
7. Đã allocate→register→populate đúng thứ tự chưa?
8. Memo có dùng chung cho toàn bộ session/multiple roots chưa?
9. Có remap tất cả graph links về clones không?
10. Có copy arrays, Lists, Maps và nested mutable payloads phù hợp không?
11. Có bewusst share immutable values không? 
12. Có external resources/services không nên clone không?
13. Có heterogeneous subclasses cần preserve runtime type không?
14. Có final fields/cyclic construction constraints không?
15. Constructors có side effects cần tránh không?
16. Cloned HashMap/HashSet keys đã stable trước khi insert chưa?
17. Có dùng queue iterative khi depth có thể rất lớn không?
18. Có giới hạn V/E/memory cho input không tin cậy không?
19. Có concurrency snapshot/locking policy không?
20. Có cấm partially built clones escape ra ngoài không?
21. Có error/rollback/cleanup policy không?
22. Copy giữ hay cấp business IDs mới theo domain?
23. Tests có dùng == và != để đo graph identity không?
24. Tests có kiểm tra shared targets và cycles đúng không?
25. Tests có mutation isolation cho mutable payloads không?
26. Có validate null/dangling IDs cho immutable snapshots không?
27. Có tránh phụ thuộc iteration order của unordered Maps không?
28. Có phân biệt clone method, serialization và true graph copy không?
29. Có tài liệu hóa trường nào được copy và trường nào được share không?
30. Có tránh phụ thuộc reflection/Unsafe để phá final fields không?

## Kết luận

**Sao chép cấu trúc chứa tham chiếu dùng chung hoặc vòng** đòi hỏi giữ **identity topology**, không chỉ copy giá trị. Một source node chỉ được cấp phát một cloned node trong phạm vi copy; những references lặp lại phải cùng trỏ cloned node đó, và cycles phải quay về clones thay vì objects gốc.

Trong Java 17+, cách làm phổ biến là **`IdentityHashMap<Source,Clone>`** kết hợp thứ tự **allocate → memoize → populate**, rồi duyệt graph bằng DFS hoặc BFS. Memoization tránh đệ quy vô hạn do cycles và bảo toàn shared references. DFS đệ quy đơn giản hơn nhưng có thể tràn call stack ở graph sâu; BFS/DFS iterative giúp xử lý depth lớn mà vẫn cần O(V) memo và memory cho graph mới.

Quan trọng không kém là **copy policy**: arrays/collections/nested mutable state cần được sao chép khi thuộc ownership của graph; immutable values có thể share; services/resources và business IDs cần quyết định riêng. Nếu mục tiêu là snapshot bất biến, biểu diễn nodes-by-ID có thể giữ sharing/cycles mà không cần mutable reference cycles. Cuối cùng, hãy kiểm thử **reference identity, cycles, duplicate edges và mutation isolation** — đây là những phép kiểm tra mà `equals()` trên root không thể thay thế.
