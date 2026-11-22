# Java Serialization: tham chiếu dùng chung, vòng tham chiếu và object handle

## 1. Bài toán: làm sao khôi phục đúng **đồ thị đối tượng**?

Khi dùng `ObjectOutputStream` và `ObjectInputStream`, điều quan trọng không chỉ là lưu giá trị của từng field. Một đối tượng Java có thể **trỏ đến cùng một đối tượng từ nhiều field khác nhau**, hoặc các đối tượng có thể **tham chiếu vòng về nhau**.

Ví dụ:

~~~text
               +-------------------+
               |    Person (An)    |
               |  home ----+       |
               |  office --|--+    |
               +-----------|--|----+
                           |  |
                           v  v
                      +----------+
                      | Address  |
                      |  Hà Nội  |
                      +----------+

home và office là **cùng một Address**, không phải hai Address
chỉ tình cờ có nội dung giống nhau.
~~~

Và một vòng tham chiếu:

~~~text
       +--------+   next    +--------+
       | Node A | --------> | Node B |
       +--------+           +--------+
            ^                   |
            +-------------------+
                      next
~~~

Nếu chỉ sao chép nội dung field thành các bản độc lập, sau deserialize:

- Có thể làm mất quan hệ `person.home == person.office`.
- Có thể làm vòng `A -> B -> A` thành một chuỗi sao chép vô hạn hoặc một cấu trúc sai.
- Có thể làm thay đổi ngữ nghĩa chương trình, vì **identity** (đồng nhất tham chiếu) khác với equality (bằng nhau về nội dung).

**Java Object Serialization mặc định giữ cấu trúc chia sẻ và các vòng tham chiếu** bằng cách gán **object handle** cho những đối tượng đã xuất hiện trong *cùng một luồng tuần tự hóa*. Những lần gặp lại thường được ghi thành **back-reference** thay vì serialize toàn bộ đối tượng lần nữa.

## 2. Điều kiện cơ bản để serialize một đồ thị

Một lớp được tuần tự hóa mặc định thường triển khai `java.io.Serializable`:

~~~java
import java.io.Serializable;

final class Node implements Serializable {
    private static final long serialVersionUID = 1L;

    String name;
    Node next;

    Node(String name) {
        this.name = name;
    }
}
~~~

`Serializable` là **marker interface**: không bắt buộc định nghĩa method. `ObjectOutputStream.writeObject(root)` duyệt những object reachable qua các field tham chiếu cần tuần tự hóa:

- Field instance bình thường, **không phải `transient` hoặc `static`**, được tham gia vào cơ chế default serialization (tuân theo các quy tắc của lớp/kiểu).
- Field kiểu primitive được lưu theo giá trị.
- Field tham chiếu tới object khác có thể kéo theo cả **đồ thị các object mà nó trỏ tới**.
- `null` được ghi như giá trị null, không tạo object mới.
- Mọi object cần ghi trong đồ thị phải phù hợp với cơ chế serialization; một field tham chiếu đến object không serializable thường gây `NotSerializableException`, trừ khi được loại bỏ hoặc xử lý tùy biến.

Không nên nhầm:

~~~java
Node first = new Node("X");
Node second = new Node("X");
boolean same = first == second;  // false
~~~

Dù `first.name.equals(second.name)` là true, chúng là **hai instance khác nhau** và theo cơ chế mặc định sẽ được lưu dưới hai handle khác nhau.

Ngược lại:

~~~java
Node shared = new Node("X");
Node first = shared;
Node second = shared;
boolean same = first == second;  // true
~~~

Đây chỉ là **một object** có hai tham chiếu. Serialization giữ quan hệ `==` đó khi khôi phục graph trong luồng, miễn không bị cơ chế thay thế object tùy biến thay đổi.

## 3. Object handle là gì?

`ObjectOutputStream` quản lý trạng thái của luồng, trong đó có bảng ghi nhớ những object đã được serialize. Khi gặp một object lần đầu:

1. Luồng ghi thông tin loại object (gồm class descriptor khi cần).
2. Object nhận một **handle** — mã nhận dạng nội bộ trong **stream**, không phải Java reference, địa chỉ RAM hay `hashCode()`.
3. Luồng ghi các field cần lưu; nếu field tham chiếu đến object khác thì tiếp tục xử lý object đó.
4. Nếu gặp lại object đã được ghi, luồng có thể ghi **reference đến handle** thay vì lặp lại toàn bộ object.

Ở phía đọc, `ObjectInputStream` duy trì bảng handle tương ứng để trả lại các tham chiếu tới **cùng instance đã khôi phục**.

Sơ đồ khái niệm:

~~~text
ObjectOutputStream

Lần 1: writeObject(address)
  -> NEW_OBJECT(Address, handle H1, fields ...)

Lần 2: writeObject(address) với CÙNG instance
  -> REFERENCE(H1)

ObjectInputStream

Lần 1: readObject() -> Address#1
Lần 2: readObject() -> chính Address#1

Do đó: firstRead == secondRead  ==> true
~~~

Đây chỉ là **sơ đồ logic**. Trong stream thực còn header, class descriptor, mã loại phần tử và các handle của class descriptor, string/array và object khác. Không coi `H1` là byte handle cố định hay một mã có thể đem lưu độc lập.

### Handle khác `hashCode()`, `equals()` và object ID nghiệp vụ

| Khái niệm | Dùng để làm gì? | Phạm vi/giới hạn |
|---|---|---|
| `==` trên hai reference | Kiểm tra cùng một instance | Trong một JVM |
| `equals()` | Kiểm tra tính bằng nhau do lớp định nghĩa | Không nhất thiết cùng instance |
| `hashCode()` | Hỗ trợ hashing; không phải ID duy nhất | Có thể trùng, có thể thay đổi theo implementation |
| **Serialization handle** | Nhận dạng các object đã xuất hiện trong stream | Nội bộ mỗi stream, chịu tác động bởi `reset()` |
| ID nghiệp vụ (UUID, database ID) | Nhận dạng thực thể ở mức ứng dụng | Do ứng dụng quy định, không do serialization tự tạo |

**Không dùng một handle được đọc từ stream như primary key database.** Nó chỉ là cơ chế biểu diễn tham chiếu trong định dạng tuần tự hóa.

## 4. Vì sao tham chiếu dùng chung được bảo toàn?

Giả sử:

~~~java
// Đoạn minh họa trong ngữ cảnh có lớp Address và Person Serializable.
Address address = new Address("Hà Nội");
Person person = new Person();
person.home = address;
person.office = address;
out.writeObject(person);
~~~

Khi serializer duyệt field `home`, nó lưu `address` và gán handle. Đến field `office`, nó thấy **cùng object address** nên ghi back-reference. Phía đọc tái lập:

~~~java
Person restored = (Person) in.readObject();
System.out.println(restored.home == restored.office); // true
~~~

Nếu hai field trỏ đến **hai Address khác nhau nhưng có giá trị giống nhau**, mặc định serializer không tự “gộp” chúng lại:

~~~text
Trước ghi:   home -> Address#1("HN")
             work -> Address#2("HN")
Sau đọc:     home -> Address#3("HN")
             work -> Address#4("HN")

home != work, dù thuộc tính có thể giống nhau.
~~~

Đây là lý do phải xác định bài toán có cần bảo toàn **identity** hay chỉ cần bảo toàn **giá trị**.

### Chia sẻ trong nhiều cấp lồng nhau

Không chỉ hai field của cùng object được bảo toàn. Nếu một danh sách chứa `sameNode` hai lần, hoặc nhiều đối tượng khác nhau cùng trỏ đến một đối tượng con, back-reference vẫn có thể được dùng trong một đồ thị được ghi vào cùng stream.

~~~java
Node sameNode = new Node("shared");
List<Node> nodes = new ArrayList<>();
nodes.add(sameNode);
nodes.add(sameNode);
// Sau serialize/deserialize nodes, phần tử index 0 và 1
// vẫn là cùng một Node: nodes.get(0) == nodes.get(1).
~~~

Đoạn này là mã minh họa, cần imports `java.util.*` và lớp Node serializable; không phải một chương trình độc lập.

## 5. Vòng tham chiếu: tại sao serializer không đệ quy vô hạn?

Nếu hai object trỏ về nhau:

~~~java
Node a = new Node("A");
Node b = new Node("B");
a.next = b;
b.next = a;
~~~

Quá trình lưu có thể hình dung:

~~~text
writeObject(a)
  1) gặp A lần đầu -> cấp handle HA
  2) ghi A.next = B
     3) gặp B lần đầu -> cấp handle HB
     4) ghi B.next = A
        5) A đã có HA -> ghi REFERENCE(HA), không đệ quy thêm
  6) quay lại hoàn tất B rồi A
~~~

Điểm then chốt: **handle của object được gán trước khi toàn bộ field tham chiếu của nó được viết xong**. Vì vậy khi đọc đến một liên kết quay về object đang trong quá trình serialize, serializer đã có handle để tham chiếu.

Phía đọc cũng tạo/đăng ký đối tượng trước khi hoàn tất toàn bộ field của nó theo cơ chế mặc định, cho phép khôi phục vòng:

~~~java
Node restored = (Node) in.readObject();
boolean cycle = restored.next.next == restored; // true
~~~

Vòng tham chiếu **không** cần được cắt bằng cách đặt field thành `null`. Tuy nhiên, cơ chế tuần tự hóa có hạn mức tài nguyên (độ sâu, kích thước) và có thể thất bại trên đồ thị quá lớn/phức tạp; không tự suy ra mọi đồ thị vô hạn hoặc dữ liệu hỏng đều đọc được.

### Self-reference

Một object có thể trỏ đến chính nó:

~~~java
Node self = new Node("SELF");
self.next = self;
~~~

Sau serialize/deserialize mặc định:

~~~java
Node restored = (Node) in.readObject();
System.out.println(restored.next == restored); // true
~~~

Đây là một trường hợp vòng độ dài 1. Với nhiều thư viện JSON, xử lý vòng có thể cần chiến lược riêng; **đừng lấy hành vi JSON làm mặc định cho Java Object Serialization**.

## 6. Chương trình Java 17+ hoàn chỉnh

Ví dụ này chứng minh **bốn hiện tượng** bằng cách chạy thực tế:

1. Hai lần `writeObject(root)` liên tiếp trong cùng `ObjectOutputStream` tham chiếu đến **cùng object đã được serialize trước**.
2. Sửa field `name` rồi gọi lại `writeObject(root)` **không tự lưu field mới** nếu object vẫn còn handle cũ trong stream.
3. `ObjectOutputStream.reset()` làm lần ghi tiếp theo trở thành **một lần serialize mới**; phía đọc nhận một graph mới, và nội dung field mới được ghi.
4. Các tham chiếu chia sẻ và vòng `A -> B -> A` vẫn được tái lập **bên trong từng graph**.

Lưu tệp **`ObjectHandleDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class ObjectHandleDemo {

    private static final class Node implements Serializable {
        private static final long serialVersionUID = 1L;

        String name;
        Node next;
        Node also;

        Node(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) throws Exception {
        Node a = new Node("A");
        Node b = new Node("B");

        a.next = b;
        a.also = b; // Hai field của A trỏ đến cùng B.
        b.next = a; // A -> B -> A tạo vòng.

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out =
                     new ObjectOutputStream(bytes)) {
            out.writeObject(a); // Graph đầu tiên, có handle của A/B.
            out.writeObject(a); // Back-reference tới A cũ.

            a.name = "A-updated";
            out.writeObject(a); // Vẫn back-reference, không ghi name mới.

            out.reset();        // Hủy bảng handle của stream.
            out.writeObject(a); // Ghi graph mới với name đã thay đổi.
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {

            Node first = (Node) in.readObject();
            Node second = (Node) in.readObject();
            Node third = (Node) in.readObject();
            Node afterReset = (Node) in.readObject();

            System.out.println("same-root="
                    + (first == second && second == third));
            System.out.println("old-name=" + first.name);
            System.out.println("updated-name=" + afterReset.name);
            System.out.println("new-root="
                    + (first != afterReset));

            System.out.println("shared-child="
                    + (first.next == first.also));
            System.out.println("cycle="
                    + (first.next.next == first));
            System.out.println("new-cycle="
                    + (afterReset.next.next == afterReset));

            System.out.println("original-vs-restored="
                    + (a == first));
        }
    }
}
~~~

Biên dịch và chạy trong thư mục có tệp nguồn:

~~~bash
javac ObjectHandleDemo.java
java ObjectHandleDemo
~~~

**Stdout chính xác khi chương trình chạy thành công:**

~~~text
same-root=true
old-name=A
updated-name=A-updated
new-root=true
shared-child=true
cycle=true
new-cycle=true
original-vs-restored=false
~~~

**Giải thích từng dòng:**

- `first == second == third` đều đúng vì ba lần đọc đầu phục hồi **một object handle** từ một object mới rồi hai back-reference.
- `old-name=A` vì giá trị của A đã được ghi khi nó **xuất hiện lần đầu trong stream**; thay đổi A trong bộ nhớ **không tự cập nhật bytes đã serialize**.
- `afterReset.name` là `"A-updated"` vì lần ghi sau `reset()` thực hiện serialize trạng thái hiện tại của A.
- `first != afterReset` vì sau reset, reader tạo một graph mới cho phần dữ liệu tiếp theo.
- `first.next == first.also` cho thấy shared B được giữ.
- `first.next.next == first` và `afterReset.next.next == afterReset` cho thấy cả graph cũ và graph mới có chu trình đúng.
- `a == first` là false vì `a` là object gốc trong bộ nhớ trước khi ghi, còn `first` là một object được khôi phục bởi deserialization trong cùng JVM.

**Lưu ý:** `ByteArrayOutputStream` chỉ giữ bytes trong bộ nhớ, vì vậy demo không phụ thuộc filesystem. Nó kiểm chứng identity và nội dung, **không mô phỏng persistence/durability trên đĩa**.

## 7. Object handle tồn tại trong phạm vi nào?

Bảng handle thuộc **mỗi `ObjectOutputStream`** và được phía `ObjectInputStream` tương ứng theo dõi. Nó **không phải cache toàn cục JVM**.

### Cùng stream, cùng object

~~~java
out.writeObject(shared);
out.writeObject(shared);
~~~

Thao tác thứ hai có thể chỉ ghi back-reference, vì `shared` đã có handle trong luồng đó. Khi đọc hai mục tương ứng, hai biến nhận được tham chiếu cùng object.

### Hai stream độc lập

~~~java
// Minh họa, hai ObjectOutputStream khác nhau:
outA.writeObject(shared);
outB.writeObject(shared);
~~~

Hai stream có trạng thái handle riêng. Đọc các stream độc lập thông thường tạo object mới cho mỗi stream, dù phía ghi truyền vào đúng cùng một object gốc.

### Trong một lần ghi cả graph

~~~java
// Minh họa root chứa cùng subObject qua nhiều field.
root.left = subObject;
root.right = subObject;
out.writeObject(root);
~~~

Field `left/right` cùng trỏ đến subObject trong graph được phục hồi (mặc định). Điều này hoạt động không phụ thuộc vào việc có gọi `writeObject(root)` lần thứ hai hay không.

### Hai object có nội dung bằng nhau

~~~java
out.writeObject(new Node("same"));
out.writeObject(new Node("same"));
~~~

Đây là **hai instance khác nhau**, không phải một shared reference. Kết quả đọc thường tạo hai Node riêng biệt.

**Đừng dựa vào giá trị `equals()` hoặc `System.identityHashCode()` để đoán handle serialization.** Đó là những cơ chế khác.

## 8. Vì sao sửa object rồi `writeObject()` lại có thể nhận trạng thái cũ?

Một lỗi rất phổ biến:

~~~java
// Minh họa: User là lớp Serializable.
User user = new User("first");
out.writeObject(user);

user.name = "second";
out.writeObject(user); // Không tự phát lại toàn bộ trạng thái mới.
~~~

Luồng đã biết handle của `user` nên lần hai có thể là back-reference. Reader trả lại object có dữ liệu được khôi phục từ **lần ghi đầu tiên**.

### Các cách giải quyết tùy mục tiêu

- **Muốn giữ identity và không muốn snapshot mới:** `writeObject` như thường lệ; back-reference là hành vi cần thiết.
- **Muốn ghi trạng thái mới của toàn graph:** gọi `ObjectOutputStream.reset()` tại một ranh giới hợp lệ **trước lần ghi kế tiếp**; stream quên handle cũ, lần sau serialize lại.
- **Muốn chủ động gửi lại trạng thái của cùng object nhưng giữ những đối tượng phụ đã biết:** nghiên cứu `writeUnshared(...)` hoặc `writeObject` trên một bản snapshot riêng, hiểu rõ giới hạn phạm vi chia sẻ.
- **Muốn cập nhật trạng thái lưu bền theo transaction:** object stream không phải database; cần định dạng record/version hoặc cơ chế lưu trữ phù hợp.

Không sửa thủ công bảng handle hay dựa vào việc `flush()` để làm mới object đã được cache trong stream. **`flush()` đẩy bytes đang đệm; không xóa object handles.**

## 9. `ObjectOutputStream.reset()`: xóa trạng thái handle cho các mục ghi tiếp

`reset()` trên `ObjectOutputStream`:

1. Bỏ trạng thái ghi nhớ những object đã xuất hiện trong stream.
2. Ghi dấu reset trong stream để phía `ObjectInputStream` tương ứng **cũng xóa bảng handle tại vị trí đó**.
3. Những object đã ghi trước đó **không bị sửa hoặc mất khỏi bytes hiện có**.
4. Object cùng Java reference nếu được `writeObject` sau reset sẽ được serialize như một lần xuất hiện mới.
5. Có thể làm tăng kích thước stream vì object và class descriptor có thể được ghi lại.

Ví dụ:

~~~java
out.writeObject(root); // Root được gán handle lần đầu.
out.writeObject(root); // Back-reference.
out.reset();            // Quên bảng handle.
out.writeObject(root); // Dữ liệu của root được ghi lại.
~~~

**Không gọi `reset()` trong lúc serializer đang thực hiện ghi một object**, ví dụ gọi tùy tiện bên trong `private writeObject(ObjectOutputStream out)` để ép child mới. Đặc tả không cho phép reset trong quá trình serialize object; có thể ném `IOException`.

Reset là **mốc cho những object về sau**, không phải lệnh xóa bytes trước nó. Đừng nhầm với `ByteArrayOutputStream.reset()`: phương thức của ByteArrayOutputStream xóa **nội dung buffer bytes** trong RAM, còn `ObjectOutputStream.reset()` có nhiệm vụ đặt lại **trạng thái serialization** và ghi marker tương ứng.

### Reset có “deep copy” không?

Nếu sau reset ta serialize lại toàn bộ root graph, phía đọc có graph mới, trong đó các tham chiếu nội bộ vẫn được chia sẻ/có vòng đúng cách. Tuy nhiên:

- Dữ liệu mutable chỉ phản ánh trạng thái tại thời điểm được serialize lại.
- Nếu một field là `transient`/`static` hoặc các custom hooks thay đổi logic, graph kết quả có thể khác.
- Định nghĩa graph mới không tự đảm bảo thread-safety nếu object gốc bị thread khác sửa trong lúc serialize.

## 10. `writeUnshared()`: ghi lại object ở cấp gốc mà không dùng back-reference cũ

Ngoài `writeObject`, Java cung cấp:

~~~java
out.writeUnshared(obj);
~~~

Theo tài liệu `ObjectOutputStream`:

- Đối với **object ở cấp gốc được truyền trực tiếp**, `writeUnshared(obj)` luôn ghi object như một object mới xuất hiện, thay vì viết back-reference đến lần ghi trước.
- Những lần `writeObject(obj)` về sau **không tham chiếu ngược tới lần ghi bằng `writeUnshared`** như thể đó là một lần ghi shared thông thường.
- Quy tắc này **chỉ áp dụng trực tiếp cho root object của lời gọi**. Các object con được tham chiếu transitively vẫn có thể chia sẻ handle với object đã ghi khác.
- Vì vậy **`writeUnshared()` không phải deep copy toàn bộ graph** và không có nghĩa tắt object caching trên mọi cấp.

### Ví dụ trực tiếp với hai lần ghi unshared

Lưu thành **`UnsharedDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class UnsharedDemo {

    private static final class Box implements Serializable {
        private static final long serialVersionUID = 1L;
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) throws Exception {
        Box box = new Box(7);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (ObjectOutputStream out =
                     new ObjectOutputStream(bytes)) {
            out.writeUnshared(box);
            out.writeUnshared(box);
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            Box first = (Box) in.readUnshared();
            Box second = (Box) in.readUnshared();

            System.out.println("first=" + first.value);
            System.out.println("second=" + second.value);
            System.out.println("distinct=" + (first != second));
        }
    }
}
~~~

Chạy:

~~~bash
javac UnsharedDemo.java
java UnsharedDemo
~~~

**Stdout:**

~~~text
first=7
second=7
distinct=true
~~~

Trong ví dụ này Box đơn giản, không có `readResolve()` hoặc object con, nên hai lần đọc nhận **hai instance khác nhau**.

### `readUnshared()` khác `readObject()`

`ObjectInputStream.readUnshared()` nhận một object mới **và ngăn những lần đọc back-reference về handle đó**. Nếu `readUnshared()` gặp chính một back-reference đã có trong stream, Java ném một **`ObjectStreamException`** (thường gặp `InvalidObjectException` theo triển khai; không nên gắn logic vào một subtype cụ thể nếu chỉ dựa trên hợp đồng API).

Ví dụ sai:

~~~java
// Ghi:
out.writeObject(box);
out.writeObject(box); // Back-reference tới box.

// Đọc:
Box first = (Box) in.readObject();
Box second = (Box) in.readUnshared(); // Không hợp lệ trên back-reference.
~~~

Đây là **đoạn minh họa ở hai phía ghi/đọc**, không phải chương trình độc lập. Không dùng `readUnshared` tùy tiện thay cho tất cả `readObject`.

**Ngoại lệ tinh tế:** `readResolve()` có thể thay object bằng một singleton hoặc instance đã có ở nơi khác, và enum/Class có ngữ nghĩa đặc biệt. Vì vậy kết hợp `writeUnshared/readUnshared` không phải cam kết tuyệt đối về một instance mới cho *mọi loại object*. Với `readResolve` trả về array, `readUnshared` dùng bản clone nông theo đặc tả. Bản thân child object trong graph cũng có thể vẫn chia sẻ.

## 11. Dòng byte: `TC_OBJECT`, `TC_REFERENCE` và `TC_RESET`

Trong giao thức Java Object Serialization, các phần tử stream được đánh dấu bằng mã loại:

| Token | Ý nghĩa khái quát |
|---|---|
| `TC_OBJECT` | Dữ liệu một ordinary object mới |
| `TC_ARRAY` | Một array mới |
| `TC_STRING` / `TC_LONGSTRING` | Một String mới |
| `TC_CLASSDESC` | Class descriptor tương ứng |
| `TC_REFERENCE` | Tham chiếu đến object/descriptor/string đã có handle |
| `TC_NULL` | Tham chiếu null |
| `TC_RESET` | Đặt lại trạng thái handle của luồng tại điểm này |

Đây là cách **hình dung giao thức**, không phải danh sách mọi token. Một stream thực còn header như magic/version, các descriptor và phần tử khác. Không phải mỗi lần gọi `writeObject` đều sinh `TC_OBJECT`; lần gặp lại có thể chỉ sinh `TC_REFERENCE`.

~~~text
writeObject(root)  -> NEW root (handle Hroot), các child, field ...
writeObject(root)  -> TC_REFERENCE(Hroot)
reset()            -> TC_RESET
writeObject(root)  -> NEW root/children, handle table mới
~~~

Handle không phải memory pointer. Nó dùng để biểu diễn sự nhận dạng object **bên trong định dạng stream**.

Muốn học binary format, đọc Java Object Serialization Stream Protocol thay vì dựa vào hexdump của một ví dụ duy nhất; handle của class descriptors, strings và các thành phần phụ khiến offsets thay đổi theo đồ thị.

## 12. Khi nào quan hệ chia sẻ hoặc vòng có thể bị thay đổi?

Cơ chế mặc định bảo toàn graph, nhưng các cấu hình/hook đặc biệt có thể thay đổi kết quả:

### `transient` và `static`

~~~java
class Data implements Serializable {
    private static final long serialVersionUID = 1L;

    Node child;                // Mặc định được serialize.
    transient Node cache;      // Không lưu bằng default serialization.
    static Node registry;      // Không thuộc trạng thái instance được lưu.
}
~~~

Nếu một vòng chỉ đi qua field `transient`, cạnh tham chiếu đó **không được lưu** theo cơ chế mặc định. Khi deserialize, field transient của object nhận giá trị mặc định trừ khi có logic tùy biến khôi phục.

### `writeReplace()` và `readResolve()`

Một lớp có thể định nghĩa cơ chế **thay thế object** khi ghi/đọc. Khi `readResolve()` trả singleton (ví dụ một instance canonical), kết quả `==` có thể không còn đúng theo cách suy đoán từ object mới thông thường.

Điều này hữu ích với singleton/canonicalization nhưng phải thiết kế và kiểm thử rõ, vì dễ gây nhầm identity, đặc biệt khi kết hợp `readUnshared`. Không tự gắn các hook này vào ví dụ graph mặc định nếu không cần.

### Custom `writeObject/readObject`

Một lớp có thể tùy biến dữ liệu field lưu trong stream. Nếu custom implementation bỏ qua một field quan trọng, tự ghi object con khác thường hoặc khôi phục theo quy tắc riêng, graph kết quả có thể khác.

**Nguyên tắc:** nếu mục tiêu là bảo toàn graph như mặc định, giữ `defaultWriteObject()` / `defaultReadObject()` đúng contract trong các hook, và chỉ bổ sung logic đã kiểm chứng.

### `Externalizable`

`Externalizable` trao quyền lớn hơn cho lớp tự ghi/đọc trạng thái. Không mặc nhiên kỳ vọng mọi custom format phục hồi graph đúng nếu tác giả tự bỏ qua field hoặc không tái lập quan hệ tham chiếu. Hãy phân biệt khả năng handle của stream với dữ liệu mà lớp chọn ghi.

## 13. Lỗi phổ biến: nhầm identity, snapshot và reset

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Sau đọc, hai field `==` dù tưởng phải là bản sao | Chúng vốn trỏ cùng object; stream bảo toàn chia sẻ | Xác định rõ cần share hay copy, tạo object mới nếu yêu cầu |
| Sau đọc, hai object `equals()` nhưng `!=` | Trước ghi có hai instance khác nhau | Đừng nhầm value equality với identity |
| Gặp vòng tham chiếu mà lo serialize vô hạn | Hiểu nhầm serializer luôn đệ quy không có memoization | Object handles phá vòng với cơ chế mặc định |
| Sửa field rồi `writeObject` lại nhưng reader vẫn thấy giá trị cũ | Stream dùng back-reference đến object đã ghi | Ghi snapshot mới hoặc `out.reset()` ở ranh giới hợp lệ |
| `flush()` xong vẫn thấy giá trị cũ | Flush bytes không xóa bảng handles | Dùng reset/strategy khác, không dựa vào flush |
| `writeUnshared()` rồi tưởng mọi object con đều riêng biệt | Chỉ root object được đảm bảo ghi như mới | Hiểu rõ transitively referenced children vẫn có thể share |
| `readUnshared()` gặp back-reference và lỗi | API cấm đọc back-reference bằng readUnshared | Ghép đúng write/read semantics |
| `reset()` trong custom serialization gây lỗi | Reset không được gọi giữa lúc ghi object | Chỉ reset khi ở ngoài lượt serialize graph |
| Deserialization ném `NotSerializableException` lúc ghi | Một reachable object không serializable | Làm nó serializable, `transient` hoặc dùng custom representation |
| `InvalidClassException` khi đọc | Class metadata/`serialVersionUID` không tương thích | Quản lý version/schema, không chỉ đổi UID tùy tiện |
| Dữ liệu bị sửa đồng thời trong lúc serialize | Object graph không được snapshot nguyên tử | Đồng bộ hoặc tạo immutable snapshot trước khi ghi |
| Stream ngày càng lớn vì reset thường xuyên | Mỗi reset làm object/class descriptors được ghi lại | Cân bằng freshness, identity và kích thước |
| Đọc lại object gốc từ stream rồi so `==` với object nguồn | Deserialization thông thường tạo object mới | So sánh identity trong graph được khôi phục, không qua hai thế giới |

## 14. Liên hệ với `serialVersionUID` và ngoại lệ

Serialization chứa thông tin lớp và trạng thái field. Nếu class được thay đổi không tương thích giữa ghi và đọc, có thể gặp `InvalidClassException`. Nên khai báo `private static final long serialVersionUID` cho lớp serializable cần duy trì định dạng ổn định, nhưng **khai báo UID không đảm bảo mọi thay đổi class đều tương thích**.

Các lỗi cần biết:

- `NotSerializableException`: một object không hỗ trợ serialization trong graph và không được thay thế/loại bỏ hợp lệ.
- `InvalidClassException`: class descriptor/schema không tương thích với phiên bản lớp hiện tại.
- `StreamCorruptedException`: dữ liệu stream không đúng định dạng hoặc đã bị hỏng.
- `EOFException`: đọc quá dữ liệu stream sẵn có.
- `ClassNotFoundException`: không tìm được lớp cần khôi phục.
- `ObjectStreamException` khi `readUnshared` gặp back-reference trái phép.
- `IOException`: lỗi I/O nền hoặc lỗi giao thức.

**Không nên tiếp tục dùng một `ObjectOutputStream` hoặc `ObjectInputStream` với giả định trạng thái vẫn an toàn sau lỗi nghiêm trọng giữa lúc ghi/đọc graph**. Đọc tài liệu về exception protocol của Java serialization và tạo stream mới khi cần phục hồi theo một ranh giới đáng tin cậy.

## 15. Bảo mật: chỉ deserialize dữ liệu đáng tin hoặc có kiểm soát

Java Object Serialization **không phải định dạng giao tiếp an toàn mặc định cho dữ liệu không tin cậy**. `ObjectInputStream.readObject()` có thể tạo một đồ thị lớp phong phú và kích hoạt các cơ chế đặc biệt khi khôi phục; stream bị sửa đổi có thể gây lạm dụng bộ nhớ/tài nguyên hoặc các nguy cơ deserialization khác.

Với đầu vào không tin cậy:

1. Cân nhắc dùng một định dạng dữ liệu đơn giản, có schema rõ thay vì Java native serialization.
2. Nếu bắt buộc dùng `ObjectInputStream`, triển khai **`ObjectInputFilter`** ở Java 17 để giới hạn lớp, graph depth, số reference, kích thước array và tổng bytes theo phạm vi cho phép.
3. Giới hạn kích thước input trước khi deserialize, xác thực nguồn và kiểm tra business invariants sau khi đọc.
4. Đừng coi `serialVersionUID` hay object handle là biện pháp xác thực hoặc mã hóa.
5. Không log trực tiếp toàn bộ object graph trong môi trường nhạy cảm; có thể tạo vòng hoặc lộ dữ liệu.

Ví dụ minh họa bộ lọc đơn giản:

~~~java
// Đoạn minh họa, input là ObjectInputStream đã tạo.
// Hãy điều chỉnh pattern theo class thực tế, không copy
// một allowlist demo sang production mà chưa kiểm tra.
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=10000;maxbytes=1048576;maxarray=100000;!*");
input.setObjectInputFilter(filter);
~~~

Pattern trên **chặn mọi lớp** không được cho phép tường minh, nên không thể đọc ví dụ Node nếu giữ nguyên; nó chỉ minh họa ý nghĩa **giới hạn tài nguyên + deny-by-default**. Trong ứng dụng thật phải thêm danh sách lớp được phép theo ngữ cảnh. Đoạn minh họa cần `import java.io.ObjectInputFilter;`.

## 16. Thiết kế hợp lý cho dữ liệu ứng dụng

### Khi nên giữ chia sẻ như mặc định

Nếu nhiều entity đang sử dụng **cùng một object** có ý nghĩa (ví dụ một address/cache/config được chia sẻ trong graph), serialization mặc định giúp khôi phục đúng topology. Dùng `writeObject` thông thường và bảo đảm mọi object cần lưu trong graph có representation phù hợp.

### Khi cần snapshot phiên bản mới

Nếu viết liên tục nhiều snapshot của cùng object mutable vào **một ObjectOutputStream**, cần chính sách làm mới:

- `reset()` giữa các snapshot nếu chấp nhận việc object mới không chia sẻ identity với snapshot trước.
- Hoặc xây dựng DTO/immutable snapshot mới cho mỗi lần ghi.
- Đừng dùng `flush()` hoặc `close()` như cách yêu cầu serializer viết lại object đã có handle.

### Khi cần tránh lặp lại cả đồ thị

Nếu graph rất lớn với nhiều shared references, việc giữ handle có thể giảm kích thước stream đáng kể. Nhưng bảng handle cũng giữ trạng thái lâu trong luồng; một stream sống rất lâu có thể tiêu thụ bộ nhớ nhiều hơn. Có thể reset tại các boundary rõ ràng, chấp nhận dữ liệu được serialize lại sau reset.

### Khi cần persistence lâu dài

Java native serialization phụ thuộc định dạng lớp, serial UID và những quy tắc tương thích. Nếu lưu bền nhiều năm, truyền qua môi trường công nghệ khác hoặc cần kiểm soát schema, cân nhắc format có version và schema độc lập (ví dụ JSON/CBOR/Protocol Buffers phù hợp ngữ cảnh), đồng thời chủ động biểu diễn object IDs/references nếu cần chia sẻ và vòng.

## 17. Tự kiểm tra

1. Hai field trước khi ghi cùng trỏ tới một object. Sau deserialize mặc định, `field1 == field2`? **True.**
2. Hai object khác nhau nhưng `equals() == true`. Serializer có tự gộp? **Không.**
3. A.next=B và B.next=A. Vì sao không đệ quy vô hạn? **Serializer gán handle trước khi ghi xong các field và dùng back-reference khi gặp lại A.**
4. Object handle có phải Java memory address hay database ID không? **Không; đó là mã trong phạm vi stream.**
5. `writeObject(obj)` hai lần trong cùng stream, không reset. Hai lần đọc thường trả object nào? **Cùng instance đã deserialize qua back-reference.**
6. Sửa field sau lần ghi đầu rồi `writeObject` lại. Có tự gửi field mới không? **Không, nếu lần hai là back-reference.**
7. `ObjectOutputStream.reset()` có xóa bytes đã ghi không? **Không. Nó đặt lại trạng thái handle và ghi reset marker.**
8. `ByteArrayOutputStream.reset()` có giống ObjectOutputStream.reset không? **Không. Một cái xóa bytes trong bộ nhớ, một cái đặt lại trạng thái serialization.**
9. `writeUnshared(root)` có bảo đảm toàn bộ child object cũng không shared với graph trước không? **Không; chỉ root ở cấp gọi.**
10. `readUnshared()` đọc một back-reference có hợp lệ không? **Không, ném ObjectStreamException.**
11. Field `static` hoặc `transient` được default serialization lưu hay không? **Không.**
12. ObjectInputStream có nên đọc stream bất kỳ từ Internet không? **Không; cần kiểm soát nguồn, filter và giới hạn tài nguyên.**
13. `serialVersionUID` có thay thế versioning/scheme migration không? **Không.**
14. Dùng cùng class nhưng tạo hai ObjectOutputStream khác nhau, có dùng chung bảng handle không? **Không.**
15. Tại sao `original == restored` thường false dù graph giữ identity? **Deserialization tạo object trong một graph mới; identity chỉ được tái lập giữa các reference bên trong graph/stream được đọc.**

## 18. Tham khảo chính thức

- [Java SE 17 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html): `writeObject`, `writeUnshared`, `reset` và tham chiếu dùng chung.
- [Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): `readObject`, `readUnshared`, khôi phục đồ thị, serial filtering.
- [Java SE 17 — Java Object Serialization Specification: System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html): handles, shared references và cyclic references.
- [Java SE 17 — Object Output Classes](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/output.html): thuật toán gán handle, reset, writeUnshared.
- [Java SE 17 — Object Input Classes](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html): phục hồi handle, reset token và readUnshared.
- [Java SE 17 — Stream Protocol](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/protocol.html): định dạng phần tử, TC_REFERENCE, TC_RESET và class descriptors.
- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): giới hạn và lọc dữ liệu khi deserialize.
