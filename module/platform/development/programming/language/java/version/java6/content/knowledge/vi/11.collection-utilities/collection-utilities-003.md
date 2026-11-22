# Tạo tập hợp dùng so sánh danh tính khi nghiệp vụ yêu cầu

## 1. “Trùng” có thể mang hai ý nghĩa khác nhau

Trước khi chọn một tập hợp, cần xác định thế nào là hai phần tử trùng nhau.

- **Trùng theo giá trị:** hai đối tượng được xem là bằng nhau theo `equals`. Ví dụ, hai mã khách hàng có cùng nội dung biểu diễn cùng một mã nghiệp vụ.
- **Trùng theo danh tính đối tượng (object identity):** hai tham chiếu cùng trỏ đến đúng một đối tượng, tức `a == b`.

Hai đối tượng khác nhau có thể có cùng dữ liệu và `a.equals(b)` là `true`, trong khi `a == b` là `false`.

`HashSet` phù hợp với ngữ nghĩa bằng nhau thông thường dựa trên `equals` và `hashCode`. Nhưng nếu nhiệm vụ là “đối tượng cụ thể này đã được xử lý chưa?”, gộp hai đối tượng chỉ vì chúng có giá trị bằng nhau có thể làm thuật toán sai.

Ví dụ, khi duyệt một đồ thị các đối tượng trong bộ nhớ, hai nút khác nhau có thể cùng nhãn. Nếu yêu cầu là ghé thăm từng đối tượng, hai nút đó vẫn cần được xử lý riêng.

## 2. Tạo tập hợp danh tính bằng map nền

Java cung cấp cách tạo tập hợp dựa trên một map:

```java
Set<Node> visited =
        Collections.newSetFromMap(new IdentityHashMap<>());
```

Đây là mẫu khai báo, giả sử kiểu `Node` tồn tại và đã import các lớp trong `java.util`.

Hai thành phần có vai trò khác nhau:

- `IdentityHashMap` quyết định cách nhận diện khóa: dùng danh tính tham chiếu thay cho `equals`.
- `Collections.newSetFromMap` cung cấp giao diện `Set` dựa trên các khóa của map đó.

Kiểu map nền là `Map<E, Boolean>`. Phần tử của tập hợp tương ứng với khóa; giá trị `Boolean` do lớp bọc quản lý. Khi chỉ cần tập hợp, không cần tự ghi hoặc đọc các giá trị này.

`newSetFromMap` có từ Java 6 và vẫn áp dụng trong Java hiện đại. Hợp đồng tạo tập hợp được mô tả trong [Collections.newSetFromMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#newSetFromMap(java.util.Map)).

### Điều kiện của map nền

Map truyền vào phải **rỗng**. Nếu map đã có phần tử, `newSetFromMap` ném `IllegalArgumentException`.

Sau khi tạo tập hợp, không tiếp tục truy cập map trực tiếp. Thay đổi phần tử thông qua tập hợp được trả về. Việc truyền một map mới ngay trong lời gọi như ví dụ giúp tránh giữ thêm một đường truy cập ngoài ý muốn.

Không dùng `newSetFromMap(new HashMap<>())` để có ngữ nghĩa danh tính. `HashMap` vẫn dùng `equals`/`hashCode`; lớp bọc không tự đổi quy tắc so sánh. Với ngữ nghĩa đó, dùng `HashSet` trực tiếp thường rõ ràng hơn.

## 3. Ví dụ chạy đầy đủ: cùng dữ liệu nhưng khác đối tượng

Dùng một `record` để có `equals` dựa trên dữ liệu. Hai lần `new` tạo hai đối tượng khác nhau, dù thành phần của chúng giống nhau.

Lưu thành `IdentitySetDemo.java`:

```java
import java.util.Collections;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Set;

public class IdentitySetDemo {
    record Sample(String value) {}

    public static void main(String[] args) {
        Sample first = new Sample("blue");
        Sample second = new Sample("blue");
        Sample alias = first;

        System.out.println("equal values: " + first.equals(second));
        System.out.println("same object: " + (first == second));
        System.out.println("alias is first: " + (alias == first));

        Set<Sample> byValue = new HashSet<>();
        System.out.println("value add first: " + byValue.add(first));
        System.out.println("value add second: " + byValue.add(second));
        System.out.println("value size: " + byValue.size());

        Set<Sample> byIdentity =
                Collections.newSetFromMap(new IdentityHashMap<>());

        System.out.println("identity add first: " + byIdentity.add(first));
        System.out.println("identity add second: " + byIdentity.add(second));
        System.out.println("identity add alias: " + byIdentity.add(alias));
        System.out.println("identity size: " + byIdentity.size());

        System.out.println("contains new equal object: "
                + byIdentity.contains(new Sample("blue")));
        System.out.println("remove alias: " + byIdentity.remove(alias));
        System.out.println("still contains second: "
                + byIdentity.contains(second));
        System.out.println("remaining size: " + byIdentity.size());
    }
}
```

Biên dịch và chạy bằng Java 17+:

```shell
javac IdentitySetDemo.java
java IdentitySetDemo
```

Stdout:

```text
equal values: true
same object: false
alias is first: true
value add first: true
value add second: false
value size: 1
identity add first: true
identity add second: true
identity add alias: false
identity size: 2
contains new equal object: false
remove alias: true
still contains second: true
remaining size: 1
```

Điểm cần hiểu:

1. `HashSet` giữ một phần tử vì `first` và `second` bằng nhau theo giá trị.
2. Tập hợp danh tính giữ cả hai vì chúng là hai đối tượng.
3. `alias` không tạo thêm phần tử: nó trỏ tới chính `first`.
4. Một đối tượng mới có dữ liệu `"blue"` không được xem là đã có trong tập hợp danh tính.
5. Xóa qua `alias` xóa phần tử của `first`, không xóa đối tượng `second` dù dữ liệu bằng nhau.

Đây là thay đổi về ý nghĩa của việc trùng lặp, không chỉ là một lựa chọn tối ưu hiệu năng.

## 4. Tình huống phù hợp: duyệt đồ thị đối tượng có chu trình

Giả sử ta đang phân tích các đối tượng thực sự tồn tại trong bộ nhớ:

```text
          root
         /    \
    leaf #1  leaf #2
       |
       +------> root
```

Hai đối tượng lá có cùng nhãn `"leaf"`. Lớp nút định nghĩa `equals` dựa trên nhãn, nhưng nhiệm vụ hiện tại yêu cầu đếm từng đối tượng có thể đi tới từ gốc.

Cần giải quyết đồng thời:

- Không lặp vô hạn khi gặp cạnh quay về `root`.
- Không bỏ qua một đối tượng lá chỉ vì nó có cùng nhãn với đối tượng lá khác.

Lưu thành `IdentityGraphVisitDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class IdentityGraphVisitDemo {
    static final class Vertex {
        final String label;
        final List<Vertex> next = new ArrayList<>();

        Vertex(String label) {
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Vertex vertex
                    && label.equals(vertex.label);
        }

        @Override
        public int hashCode() {
            return label.hashCode();
        }
    }

    // Moi lan goi truyen vao mot tap hop seen rong.
    // Do thi trong vi du khong chua canh null va khong bi sua khi duyet.
    static int countReachable(Vertex root, Set<Vertex> seen) {
        Deque<Vertex> pending = new ArrayDeque<>();
        pending.push(root);

        while (!pending.isEmpty()) {
            Vertex current = pending.pop();

            if (!seen.add(current)) {
                continue;
            }

            for (Vertex target : current.next) {
                pending.push(target);
            }
        }

        return seen.size();
    }

    public static void main(String[] args) {
        Vertex root = new Vertex("root");
        Vertex firstLeaf = new Vertex("leaf");
        Vertex secondLeaf = new Vertex("leaf");

        root.next.add(firstLeaf);
        root.next.add(secondLeaf);
        firstLeaf.next.add(root);

        System.out.println("leaves equal: "
                + firstLeaf.equals(secondLeaf));
        System.out.println("leaves same object: "
                + (firstLeaf == secondLeaf));

        int valueCount = countReachable(root, new HashSet<>());

        Set<Vertex> seenByIdentity =
                Collections.newSetFromMap(new IdentityHashMap<>());
        int identityCount = countReachable(root, seenByIdentity);

        System.out.println("visited by value: " + valueCount);
        System.out.println("visited by identity: " + identityCount);
    }
}
```

Biên dịch và chạy:

```shell
javac IdentityGraphVisitDemo.java
java IdentityGraphVisitDemo
```

Stdout:

```text
leaves equal: true
leaves same object: false
visited by value: 2
visited by identity: 3
```

Lời gọi `seen.add(current)` vừa kiểm tra vừa ghi nhận việc ghé thăm:

- `true`: đây là lần đầu đối tượng được thấy theo quy tắc của tập hợp; tiếp tục khám phá các cạnh.
- `false`: phần tử đã được ghi nhận; bỏ qua để tránh xử lý lặp.

Với tập hợp danh tính, cạnh quay về gốc bị chặn vì đó đúng là đối tượng `root` đã thấy. Hai lá vẫn được giữ riêng.

Nếu mô hình đồ thị của bạn định nghĩa các đỉnh theo mã nghiệp vụ thay vì theo đối tượng, tập hợp theo giá trị có thể mới là lựa chọn đúng. Ví dụ này chọn danh tính vì nhiệm vụ là khảo sát từng đối tượng trong bộ nhớ.

Các phép biến đổi cần giữ cấu trúc tham chiếu, chẳng hạn sao chép sâu đồ thị, cũng có nhu cầu tương tự. Với bài toán sao chép, thường cần thêm map từ đối tượng gốc sang đối tượng đích; riêng tập hợp đã thăm chỉ ghi nhận việc tồn tại. Đây là nhóm ứng dụng được nêu trong [IdentityHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/IdentityHashMap.html).

## 5. Khi nào dùng và khi nào không dùng?

| Yêu cầu thật sự | Cách lựa chọn phù hợp |
| --- | --- |
| Ghé thăm mỗi đối tượng đúng một lần trong một lượt duyệt | Tập hợp danh tính |
| Theo dõi từng đối tượng đã được cấp phát hoặc đang được xử lý trong một phạm vi | Có thể dùng danh tính nếu cần phân biệt từng đối tượng cụ thể |
| Nhận diện việc hai tham chiếu cùng dùng một tài nguyên đối tượng | So sánh danh tính hoặc cấu trúc lưu theo danh tính |
| Loại trùng email, mã sản phẩm, mã khách hàng | Tập hợp theo giá trị hoặc tập hợp các mã ổn định |
| Gộp hai đối tượng cùng biểu diễn một bản ghi được tải ở hai thời điểm | So sánh theo định danh nghiệp vụ |
| Loại trùng chuỗi chỉ dựa trên nội dung | `HashSet<String>` hoặc cấu trúc phù hợp khác theo giá trị |

Một khách hàng được tải hai lần có thể tạo hai đối tượng khác nhau. Nếu mục tiêu là “mỗi khách hàng chỉ nhận một thông báo”, tập hợp danh tính có thể cho phép cả hai đi qua. Khi đó, nên lưu mã khách hàng hoặc dùng quy tắc bằng nhau đã được thiết kế cho nghiệp vụ.

Ngược lại, trong công cụ phân tích bộ nhớ, hai đối tượng khách hàng đó có thể chính là hai phần tử cần quan sát riêng.

Câu hỏi quyết định là: **nếu hai đối tượng có cùng dữ liệu nhưng khác lần tạo, yêu cầu có muốn gộp chúng không?**

## 6. Danh tính không phải identityHashCode

`System.identityHashCode(object)` trả về mã băm gắn với danh tính thay vì gọi phiên bản `hashCode` đã được đối tượng ghi đè. Nhưng mã băm là một số nguyên, không phải một định danh duy nhất được bảo đảm cho mọi đối tượng. Xem [System.identityHashCode](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)).

Không tự thay tập hợp danh tính bằng:

```java
Set<Integer> visitedHashes = new HashSet<>();
// Khong dung ma bam nhu bang chung duy nhat ve danh tinh.
```

Đoạn này chỉ minh họa một cách thiết kế cần tránh. Hai đối tượng khác nhau có thể có cùng mã băm. Nếu chỉ giữ mã băm, bạn có thể bỏ qua nhầm một đối tượng.

`IdentityHashMap` dùng cơ chế băm để tổ chức tra cứu nhưng vẫn phân biệt khóa theo tham chiếu. Va chạm mã băm không làm hai đối tượng khác nhau trở thành một khóa.

Cũng không nên mô tả mã băm danh tính như một địa chỉ bộ nhớ ổn định. Nếu cần mã nhận diện để lưu vào cơ sở dữ liệu, truyền qua mạng hoặc dùng ở lần chạy sau, hãy thiết kế định danh nghiệp vụ riêng.

## 7. Giới hạn cần giữ trong thiết kế

### Khác ngữ nghĩa bằng nhau của tập hợp thông thường

`IdentityHashMap` cố ý dùng quan hệ bằng nhau khác với hợp đồng thông thường dựa trên `equals`. Tập hợp tạo từ nó cũng có ngữ nghĩa nhận diện phần tử theo danh tính.

Đừng thay một `HashSet` bằng tập hợp này trong một API tổng quát rồi giả định mọi mã gọi vẫn hiểu “trùng” theo cách cũ. Cần đặt tên thể hiện ý định, chẳng hạn `visitedByIdentity` hoặc `activeInstances`, và tài liệu hóa phạm vi sử dụng.

Khi so sánh `equals`/`hashCode` giữa tập hợp này và các tập hợp theo giá trị, hoặc dùng các phép tập hợp phối hợp nhiều cách so sánh, không được mặc định các quy tắc tương đương nhau. Ưu tiên giữ tập hợp danh tính bên trong thuật toán có yêu cầu rõ ràng.

Nếu cần kiểm thử thành viên của tập hợp danh tính, hãy kiểm tra trực tiếp từng tham chiếu quan trọng bằng `contains`, kiểm tra kích thước và các lần thêm trùng tham chiếu. Một tập hợp kỳ vọng theo giá trị có thể không diễn đạt đúng điều cần kiểm tra.

### Không có thứ tự duyệt được bảo đảm

`IdentityHashMap` không bảo đảm thứ tự khóa; tập hợp dựa trên nó cũng không phải tập hợp giữ thứ tự thêm. Ví dụ trong bài không in trực tiếp thứ tự phần tử của tập hợp, mà kiểm tra kết quả không phụ thuộc thứ tự đó.

Nếu cần vừa nhận diện theo danh tính vừa phát kết quả theo thứ tự khám phá, có thể giữ một danh sách kết quả riêng. Khi `visited.add(node)` trả `true`, mới thêm `node` vào danh sách. Đừng suy ra thứ tự từ bảng băm.

### Không tự an toàn giữa nhiều luồng

Tập hợp dựa trên một `IdentityHashMap` thông thường không tự an toàn khi nhiều luồng đồng thời thay đổi. Nếu cần chia sẻ, phải có chính sách đồng bộ phù hợp, chẳng hạn một lớp bọc đồng bộ và việc dùng đúng lớp bọc đó ở mọi nơi.

Ngay cả khi các thao tác trên tập hợp đã được đồng bộ, các trường và cạnh của đồ thị không vì thế tự được bảo vệ. Ví dụ duyệt đồ thị trong bài giả sử cấu trúc không thay đổi trong khi duyệt.

### Giữ tham chiếu có thể kéo dài vòng đời đối tượng

Tập hợp này giữ các tham chiếu đến phần tử. Một tập hợp theo dõi tồn tại quá lâu có thể giữ lại các đối tượng không còn cần thiết cho công việc khác.

Với tập hợp đã thăm của một lượt duyệt, nên giới hạn nó trong phạm vi lượt duyệt đó. Nếu dùng làm sổ đăng ký đối tượng đang hoạt động, phải có thời điểm `remove` hoặc `clear` phù hợp.

`IdentityHashMap` cho phép một khóa `null`, nên tập hợp tạo từ nó có thể giữ một phần tử `null`. Tuy nhiên, điều này không buộc thuật toán phải chấp nhận nút `null`; ví dụ đồ thị đã loại trường hợp đó khỏi đầu vào.

## 8. Những lỗi lựa chọn thường gặp

| Lỗi | Hệ quả | Điều chỉnh |
| --- | --- | --- |
| Dùng danh tính để loại trùng dữ liệu nghiệp vụ | Hai đối tượng cùng dữ liệu vẫn được giữ riêng | Dùng giá trị hoặc mã nghiệp vụ |
| Dùng `newSetFromMap(new HashMap<>())` nhưng mong so sánh `==` | Vẫn nhận diện theo `equals` | Chọn đúng `IdentityHashMap` làm nền |
| Truyền map đã có phần tử | Gặp `IllegalArgumentException` | Tạo map rỗng rồi thêm qua tập hợp |
| Tiếp tục sửa map nền trực tiếp | Phá vỡ quy tắc sử dụng lớp bọc | Chỉ thao tác qua tập hợp được trả về |
| Lưu `identityHashCode` thay đối tượng | Có nguy cơ gộp nhầm do va chạm mã băm | Dùng cấu trúc có so sánh tham chiếu |
| Dựa vào thứ tự duyệt | Kết quả trình bày có thể thay đổi | Giữ thứ tự bằng cấu trúc riêng |
| Đổi sang danh tính để né lỗi `equals`/`hashCode` | Thay đổi nghĩa nghiệp vụ thay vì sửa lỗi gốc | Sửa hợp đồng bằng nhau hoặc quy tắc dữ liệu |

Không dùng sự khác biệt giữa các đối tượng được tái sử dụng, lưu đệm hoặc chia sẻ như một quy tắc nghiệp vụ ngầm. Ví dụ, chuỗi có thể được dùng chung; đối tượng bao số có thể được lưu đệm. Nếu điều cần so sánh là nội dung hay giá trị số, hãy dùng ngữ nghĩa giá trị.

## 9. Tự kiểm tra

1. Hai đối tượng bằng nhau theo `equals` nhưng `a != b` có cùng tồn tại trong tập hợp danh tính không? **Có.**
2. Hai biến khác tên cùng trỏ đến một đối tượng có tạo hai phần tử không? **Không.**
3. Vì sao tập hợp danh tính phù hợp với đồ thị trong ví dụ? **Cần ghé thăm từng đối tượng và không gộp hai nút chỉ vì cùng nhãn.**
4. Vì sao không dùng nó để loại trùng hai lần tải cùng mã khách hàng? **Danh tính trong bộ nhớ không tự biểu diễn cùng thực thể nghiệp vụ.**
5. Map nền của `newSetFromMap` có được chứa dữ liệu sẵn không? **Không; phải rỗng khi tạo.**
6. Hai đối tượng có cùng `identityHashCode` có chắc là cùng đối tượng không? **Không; mã băm có thể va chạm.**
