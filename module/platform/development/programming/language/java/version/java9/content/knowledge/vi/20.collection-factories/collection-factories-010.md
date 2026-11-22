# Kiểm tra tính bất biến của cả đồ thị dữ liệu

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt một collection không cho sửa với một đồ thị đối tượng thực sự bất biến.
- Giải thích vì sao \`List.of\`, \`Set.of\`, \`Map.of\` và wrapper không sửa được không tự động làm bất biến các phần tử bên trong.
- Phân biệt unmodifiable view với defensive snapshot.
- Thiết kế các object lồng nhau sao cho mọi trạng thái có thể truy cập đều không bị thay đổi từ bên ngoài.
- Kiểm tra tính bất biến bằng các phép thử ở cả container, collection lồng nhau và object được tham chiếu.

## 1. Bất biến của collection và bất biến của đồ thị dữ liệu

Một **collection không sửa được** ngăn caller thay đổi cấu trúc collection thông qua các thao tác như \`add\`, \`remove\`, \`put\` hoặc \`clear\`. Tuy nhiên, collection có thể đang chứa những object vẫn thay đổi được.

Ví dụ:

~~~java
List<StringBuilder> names = List.of(new StringBuilder("An"));
names.get(0).append(" Binh");
System.out.println(names.get(0));
~~~

Output:

~~~text
An Binh
~~~

Không thể thêm hoặc xóa phần tử của list, nhưng vẫn sửa được nội dung của \`StringBuilder\`. Vì vậy, list không sửa được chưa đồng nghĩa với toàn bộ dữ liệu mà nó tham chiếu đều bất biến.

**Đồ thị dữ liệu (object graph)** là object gốc cùng toàn bộ object có thể đi tới thông qua các tham chiếu từ nó. Nếu một object gốc chứa collection, collection chứa object con, và object con lại chứa collection khác, tất cả những object đó nằm trong cùng đồ thị.

Một đồ thị chỉ thực sự bất biến khi caller không thể thay đổi trạng thái quan sát được của bất kỳ object nào có thể truy cập từ gốc. Điều này đòi hỏi kiểm soát cả:

- Cấu trúc collection ở mọi cấp.
- Trạng thái của từng object phần tử.
- Các tham chiếu mutable được giữ từ bên ngoài.
- Các giá trị mutable bị trả ra qua accessor.
- Các mảng hoặc cấu trúc mutable được lồng bên trong object.

Không có thao tác chung của JDK có thể tự động biến mọi object graph bất kỳ thành immutable. Ứng dụng phải thiết kế các kiểu dữ liệu và ranh giới sở hữu sao cho bất biến được duy trì từ lúc tạo object.

## 2. Java 9 collection factory tạo collection không sửa được

Java 9 bổ sung các factory method cho collection:

~~~java
List<String> names = List.of("An", "Binh");
Set<String> codes = Set.of("A1", "B2");
Map<String, Integer> scores = Map.of(
    "An", 9,
    "Binh", 10
);
~~~

Các factory này trả về collection không sửa được. Những điểm cần nhớ:

- \`List.of(...)\` giữ thứ tự và cho phép phần tử trùng nhau.
- \`Set.of(...)\` không cho phép phần tử trùng nhau; nếu có phần tử trùng, lời gọi ném \`IllegalArgumentException\`.
- \`Map.of(...)\` không cho phép key trùng; key hoặc value là \`null\` sẽ làm lời gọi thất bại.
- Các factory trên không chấp nhận phần tử \`null\`.
- Các collection tạo ra không hỗ trợ thao tác thay đổi; gọi mutator như \`add\`, \`remove\`, \`put\` hoặc \`clear\` sẽ ném \`UnsupportedOperationException\`.

Có thể tạo map với nhiều entry bằng \`Map.ofEntries(...)\` và \`Map.entry(key, value)\`, cũng được bổ sung trong Java 9.

Các factory method này bảo vệ cấu trúc collection. Chúng không deep-copy hoặc đóng băng trạng thái mutable của từng phần tử. Ví dụ \`List.of(new StringBuilder("An"))\` vẫn chứa một \`StringBuilder\` có thể bị sửa.

## 3. Phân biệt view không sửa được và defensive snapshot

### 3.1. Unmodifiable view

\`Collections.unmodifiableList(source)\` tạo một wrapper không cho caller sửa list thông qua wrapper. Wrapper vẫn nhìn thấy thay đổi được thực hiện trực tiếp trên list gốc:

~~~java
List<String> source = new ArrayList<>(List.of("An"));
List<String> view = Collections.unmodifiableList(source);

source.add("Binh");
System.out.println(view);
~~~

Output:

~~~text
[An, Binh]
~~~

Caller không thể gọi \`view.add(...)\`, nhưng code còn giữ \`source\` vẫn có thể thay đổi dữ liệu mà view quan sát được. Vì thế, unmodifiable view không phải một snapshot độc lập.

### 3.2. Defensive snapshot

Nếu cần ngăn thay đổi từ collection đầu vào ảnh hưởng đến object mới, hãy copy trước rồi mới bọc:

~~~java
List<String> snapshot = Collections.unmodifiableList(
    new ArrayList<>(source)
);
~~~

Wrapper ở đây bao quanh một bản copy riêng. Thay đổi cấu trúc của \`source\` sau đó không làm thay đổi \`snapshot\`.

Java 10+ cung cấp \`List.copyOf\`, \`Set.copyOf\` và \`Map.copyOf\` để tạo collection không sửa được từ collection đầu vào. Các method này không thuộc Java 9. Chúng cũng chỉ tạo snapshot ở cấp container: các object mutable bên trong vẫn được dùng chung tham chiếu.

**Snapshot nông (shallow snapshot)** copy các phần tử hoặc tham chiếu ở cấp container. **Copy sâu (deep copy)** phải tạo bản sao phù hợp cho các object con có thể thay đổi. Với thiết kế immutable, thường nên làm cho object con vốn đã bất biến để không cần sao chép tùy tiện toàn bộ graph.

## 4. Điều kiện để cả đồ thị bất biến

Một object gốc có thể được xem là deeply immutable khi mọi đường đi từ object đó đều dẫn tới trạng thái không thể bị caller thay đổi. Một thiết kế thường dùng các nguyên tắc sau:

1. **Dùng kiểu value bất biến khi có thể.** Ví dụ \`String\`, primitive và các value object được thiết kế không có mutator.
2. **Giữ trạng thái trong field private final.** Không cung cấp setter hoặc phương thức thay đổi trạng thái sau khi constructor hoàn tất.
3. **Copy collection đầu vào.** Không giữ trực tiếp một list, set hoặc map mutable mà caller vẫn sở hữu.
4. **Bảo vệ collection khi trả ra.** Accessor không trả về tham chiếu tới collection mutable nội bộ.
5. **Kiểm tra các phần tử.** Nếu phần tử mutable, wrapper collection không đủ; cần chuyển sang immutable representation hoặc tạo bản sao phù hợp.
6. **Bảo vệ mảng và cấu trúc mutable.** Copy khi nhận dữ liệu và không trả trực tiếp mảng nội bộ.
7. **Áp dụng đệ quy cho object con.** Nếu object con chứa collection hoặc object mutable khác, chính object con cũng phải duy trì các điều kiện tương tự.

Tính bất biến có tính bắc cầu: object cha không thể bảo đảm toàn bộ graph bất biến nếu nó chứa một object con vẫn cho phép thay đổi trạng thái có thể quan sát.

## 5. Ví dụ Java 9: xây dựng một cây dữ liệu bất biến

Ví dụ sau tạo một object \`Node\` chứa danh sách các node con. Mỗi node là \`final\`, giữ field \`private final\`, không có setter và copy danh sách con trước khi bọc bằng \`Collections.unmodifiableList\`.

Tạo file **ImmutableGraphDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

final class Node {
    private final String name;
    private final List<Node> children;

    Node(String name, List<Node> children) {
        this.name = Objects.requireNonNull(name, "name");
        Objects.requireNonNull(children, "children");

        List<Node> copy = new ArrayList<>(children.size());
        for (Node child : children) {
            copy.add(Objects.requireNonNull(child, "child"));
        }

        this.children = Collections.unmodifiableList(copy);
    }

    public String getName() {
        return name;
    }

    public List<Node> getChildren() {
        return children;
    }
}

public class ImmutableGraphDemo {
    public static void main(String[] args) {
        Node leaf = new Node("leaf", List.of());

        List<Node> input = new ArrayList<>();
        input.add(leaf);

        Node root = new Node("root", input);

        // Sửa collection đầu vào sau khi tạo root.
        input.clear();

        // Root vẫn giữ snapshot đã nhận ở constructor.
        System.out.println(root.getChildren().size());
        System.out.println(root.getChildren().get(0).getName());

        // Không thể thay đổi cấu trúc collection con.
        try {
            root.getChildren().add(new Node("other", List.of()));
        } catch (UnsupportedOperationException ex) {
            System.out.println("children: blocked");
        }

        // Ví dụ collection snapshot nhưng phần tử vẫn mutable.
        List<StringBuilder> mutableItems = new ArrayList<>();
        StringBuilder item = new StringBuilder("before");
        mutableItems.add(item);

        List<StringBuilder> shallowSnapshot =
                Collections.unmodifiableList(new ArrayList<>(mutableItems));

        item.append("-after");
        System.out.println(shallowSnapshot.get(0));

        try {
            shallowSnapshot.add(new StringBuilder("new"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("container: blocked");
        }
    }
}
~~~

Biên dịch và chạy bằng Java 9:

~~~bash
javac --release 9 -Xlint:all -d out ImmutableGraphDemo.java
java -cp out ImmutableGraphDemo
~~~

Output chính xác:

~~~text
1
leaf
children: blocked
before-after
container: blocked
~~~

### 5.1. Vì sao cây Node này bất biến?

- \`Node\` là class \`final\`, nên không thể tạo subclass ghi đè hành vi để thêm trạng thái mutable.
- \`name\` là \`String\`, một kiểu bất biến.
- \`name\` và \`children\` là field \`private final\`; không có setter.
- Constructor kiểm tra null và copy toàn bộ danh sách con sang list mới.
- List mới được bọc bằng \`Collections.unmodifiableList\`; caller không thể thay đổi cấu trúc qua getter.
- Các phần tử của danh sách là \`Node\` cũng tuân theo cùng invariant, nên tính bất biến được duy trì đệ quy qua cây.

Ví dụ mô hình một cây có cấu trúc không đổi sau khi khởi tạo. Nếu ứng dụng cần graph có chu trình hoặc chia sẻ node theo định danh, cần thiết kế cách xây dựng và quản lý identity riêng; không nên thêm các tham chiếu mutable sau khi object đã được công bố.

### 5.2. Vì sao shallow snapshot vẫn thấy thay đổi?

Phần \`StringBuilder\` cho thấy \`shallowSnapshot\` đã copy container và chặn thao tác thêm phần tử, nhưng nó vẫn giữ tham chiếu đến chính object \`item\`. Khi \`item.append(...)\` chạy, giá trị quan sát qua snapshot cũng thay đổi.

Đây là bằng chứng rằng kiểm tra \`add\` bị chặn mới chỉ xác nhận container không sửa được. Muốn kết luận cả graph bất biến, phải kiểm tra cả object được tham chiếu.

## 6. Kiểm tra tính bất biến của toàn bộ graph

Không nên chỉ viết một assertion rằng \`list.add\` ném \`UnsupportedOperationException\` rồi kết luận cả graph bất biến. Hãy xác định invariant của mô hình và kiểm tra từng ranh giới sở hữu.

Một bộ kiểm tra nên bao gồm:

| Vị trí cần kiểm tra | Phép thử | Kết quả mong đợi |
|---|---|---|
| Collection gốc | Thử thêm, xóa, clear | Bị chặn |
| Collection lồng nhau | Thử thay đổi từng collection con | Bị chặn |
| Đầu vào constructor | Sửa collection nguồn sau khi tạo object | Object không đổi |
| Accessor | Thử sửa collection nhận từ getter | Bị chặn |
| Object phần tử | Thử gọi mutator hoặc thay đổi field có thể truy cập | Không có đường thay đổi trạng thái |
| Mảng nội bộ | Sửa mảng đầu vào hoặc mảng được trả ra | Object không đổi |
| Map value | Thử sửa object nằm trong value | Không thay đổi trạng thái graph |

Khi kiểm thử một graph phức tạp, cần duyệt các node có thể truy cập và áp dụng kiểm tra phù hợp với từng kiểu. Có thể dùng identity set để tránh duyệt lặp khi nhiều node cùng tham chiếu một object hoặc khi graph có chu trình. Tuy nhiên, reflection không thể tự chứng minh mọi hành vi bất biến: method có thể thay đổi trạng thái bên ngoài object, gọi native code hoặc tác động đến tài nguyên khác. Thiết kế kiểu dữ liệu và kiểm thử hành vi vẫn là bằng chứng chính.

## 7. Lỗi thường gặp

### Chỉ bọc collection bằng unmodifiable wrapper

Wrapper chặn thao tác qua wrapper, nhưng nếu code khác giữ collection gốc thì vẫn có thể sửa nội dung. Hãy copy trước khi bọc nếu cần snapshot.

### Nghĩ rằng \`List.of\` làm phần tử bất biến

\`List.of\` bảo vệ cấu trúc list. Một phần tử như \`StringBuilder\`, object domain mutable hoặc collection lồng nhau vẫn có thể thay đổi.

### Copy collection nhưng không copy hoặc kiểm soát phần tử

\`new ArrayList<>(source)\` chỉ copy các tham chiếu phần tử. Nếu phần tử mutable và vẫn được chia sẻ, trạng thái bên trong vẫn thay đổi được.

### Trả trực tiếp mảng hoặc collection nội bộ

Field \`private\` không đủ nếu getter trả ra tham chiếu mutable. Hãy trả view không sửa được cho collection hoặc defensive copy phù hợp; với mảng, copy cả khi nhận và khi trả.

### Chỉ kiểm tra node gốc

Một node gốc không có setter vẫn có thể tham chiếu đến child mutable. Kiểm tra phải đi theo các tham chiếu và xác nhận invariant ở mọi cấp.

### Nhầm snapshot với deep copy

Snapshot bảo vệ trạng thái cấu trúc ở thời điểm copy. Nó không tự tạo bản sao độc lập cho mọi object con.

## 8. Khi nào nên dùng?

- Dùng \`List.of\`, \`Set.of\`, \`Map.of\` khi cần collection hằng, không sửa được và các phần tử đã đáp ứng yêu cầu sở hữu.
- Dùng defensive copy kết hợp unmodifiable wrapper khi cần snapshot độc lập trên Java 9.
- Dùng \`List.copyOf\`, \`Set.copyOf\`, \`Map.copyOf\` từ Java 10+ khi cần snapshot không sửa được ở cấp container.
- Thiết kế value object bất biến cho phần tử và node con để bảo đảm tính bất biến xuyên suốt graph.
- Dùng copy sâu khi phải tiếp nhận các phần tử mutable mà ứng dụng không thể kiểm soát hoặc chuyển đổi sang immutable representation.

## 9. Checklist

- [ ] Collection gốc không cho caller thay đổi cấu trúc.
- [ ] Collection lồng nhau cũng được bảo vệ.
- [ ] Constructor không giữ trực tiếp tham chiếu tới collection mutable do caller sở hữu.
- [ ] Accessor không làm lộ collection hoặc mảng mutable nội bộ.
- [ ] Các object phần tử đều bất biến hoặc được copy/chuyển đổi phù hợp.
- [ ] Không có setter hoặc đường gọi nào làm thay đổi trạng thái reachable.
- [ ] Đã kiểm thử sửa đầu vào, sửa đầu ra và sửa các object con.
- [ ] Đã phân biệt rõ unmodifiable view, snapshot nông và deep immutability.

