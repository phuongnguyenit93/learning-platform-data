# Phân biệt bản sao nông và bản sao sâu khi làm việc với Collection chỉ đọc (Java 10+)

## 1. Mục tiêu bài học

Trong Java, một `Collection` **không cho sửa qua API của nó** (*unmodifiable collection*) chưa chắc đã là một **bản sao sâu** (*deep copy*), và cũng chưa chắc đại diện cho **dữ liệu bất biến hoàn toàn** (*deeply immutable data*).

Đặc biệt, Java 10 bổ sung `List.copyOf(...)`, `Set.copyOf(...)` và `Map.copyOf(...)` để tạo collection không cho chỉnh sửa cấu trúc qua API tương ứng. Các factory này chỉ giữ **các phần tử hoặc cặp khóa–giá trị theo tham chiếu**, không tự nhân bản các đối tượng lồng bên trong. Khi phần tử có trạng thái thay đổi được, dữ liệu quan sát qua collection vẫn có thể thay đổi.

Sau bài này, bạn sẽ giải thích và áp dụng được:
- **Bản sao nông** (*shallow copy*): sao chép cấu trúc collection nhưng chia sẻ các đối tượng phần tử.
- **Bản sao sâu** (*deep copy*): tạo các đối tượng độc lập cho những phần trạng thái có thể thay đổi mà chương trình cần tách biệt.
- **Unmodifiable view**: cấm sửa thông qua view nhưng vẫn theo dõi thay đổi cấu trúc của collection nguồn.
- **Unmodifiable snapshot**: tạo danh sách tham chiếu không cho sửa cấu trúc, thường không thay đổi khi collection nguồn được thêm/xóa phần tử.
- Sự khác nhau giữa **không sửa được cấu trúc** và **không sửa được trạng thái của từng phần tử**.
- Lựa chọn phù hợp khi trả dữ liệu từ API, tránh rò rỉ trạng thái có thể thay đổi.

**Phiên bản:** `Collections.unmodifiableList(...)` đã tồn tại từ trước, `List.of(...)` được bổ sung ở Java 9, và `List.copyOf(...)` có từ **Java 10**. Ví dụ chạy độc lập dùng JDK 17+, kết hợp `record` và `Stream.toList()` (các tính năng này xuất hiện ở Java mới hơn Java 10). Quy tắc cốt lõi về bản sao nông/sâu và `List.copyOf` vẫn áp dụng cho Java hiện đại.

## 2. Hai câu hỏi phải tách riêng

Khi xem một collection, hãy luôn hỏi hai câu khác nhau:

**Câu hỏi A — Collection có cho sửa cấu trúc không?**

Ví dụ: `add`, `remove`, `clear`, `set`, thay đổi ánh xạ trong `Map`. `List.copyOf(source)` trả về danh sách *unmodifiable*: các thao tác sửa cấu trúc qua danh sách ấy không được hỗ trợ.

**Câu hỏi B — Những đối tượng ở bên trong có thay đổi được không?**

Giả sử `List<Student>` chứa những `Student` có field `name` hoặc `address` có thể sửa. Khi đã có đối tượng `Student`, lời gọi `student.rename(...)` hay `student.address.city = ...` có thể làm nội dung được quan sát thay đổi, **dù bản thân danh sách không cho gọi `add`**.

Hai khía cạnh độc lập:

| Cấu trúc danh sách | Phần tử | Có thể xảy ra không? | Ví dụ |
| --- | --- | --- | --- |
| Có thể sửa | Có thể sửa | Có | `ArrayList<MutableStudent>` |
| Không cho sửa qua danh sách | Có thể sửa | Có | `List.copyOf(listOfMutableStudents)` |
| Có thể sửa | Bất biến | Có | `ArrayList<String>` |
| Không cho sửa qua danh sách | Bất biến | Có | `List.of("A", "B")` |

Một danh sách chỉ đọc về cấu trúc chứa các object có thể sửa được **không tự động trở thành deep immutable**. Đừng dùng từ “immutable” một cách mơ hồ; cần nêu rõ **đối tượng nào** và **mức độ bất biến nào**.

## 3. Bản sao nông (shallow copy)

Ví dụ:

~~~java
List<Student> source = new ArrayList<>();
source.add(new Student("An"));

List<Student> shallow = new ArrayList<>(source);
~~~

Đây là các dòng minh họa bên trong một phương thức; cần có lớp `Student` do chương trình định nghĩa và import `java.util`. Đoạn chạy hoàn chỉnh ở mục 8.

`new ArrayList<>(source)` tạo một **đối tượng `ArrayList` mới**, mang tập tham chiếu phần tử ban đầu của `source`. Nhưng nó **không** gọi constructor sao chép của `Student`; các phần tử ở hai danh sách vẫn có thể trỏ đến **cùng một `Student`**.

Nếu viết:

~~~java
System.out.println(source == shallow);         // false
System.out.println(source.get(0) == shallow.get(0)); // true
~~~

Với dữ liệu đã khởi tạo ở trên, kết quả tương ứng là `false` và `true`.

Điều đó dẫn tới hai hành vi quan trọng:
1. **Thêm/xóa phần tử của danh sách nguồn** không tự thêm/xóa phần tử trong `shallow`, bởi đây là hai cấu trúc danh sách khác nhau.
2. **Sửa trạng thái của một đối tượng phần tử đang được chia sẻ** sẽ quan sát được từ cả hai danh sách.

Ví dụ, nếu `Student` có phương thức `rename`:

~~~java
source.get(0).rename("Binh");
System.out.println(shallow.get(0).getName()); // Binh
~~~

Bản sao nông có thể hoàn toàn hợp lý nếu các phần tử **bất biến**, hoặc nếu việc chia sẻ phần tử là một quyết định thiết kế có chủ đích. Vấn đề chỉ xuất hiện khi người viết tưởng rằng sao chép danh sách đã tách luôn dữ liệu bên trong.

## 4. `List.copyOf(source)` (Java 10) là bản sao nông và không cho sửa cấu trúc

~~~java
List<Student> snapshot = List.copyOf(source);
~~~

Với `source` là một `ArrayList<Student>` có thể sửa, `snapshot` là danh sách **unmodifiable** chứa các tham chiếu đến những phần tử hiện có tại lúc gọi.

~~~java
// snapshot.add(new Student("Chi")); // Biên dịch được nhưng ném
// UnsupportedOperationException khi thực thi.

Student first = snapshot.get(0);
first.rename("Minh"); // Nếu Student mutable, lệnh này vẫn có thể hợp lệ.
~~~

Từ đây phải phân biệt:
- `List.copyOf` **không cho phép thay đổi phần tử ở các vị trí của danh sách** qua `snapshot.add`, `snapshot.remove`, `snapshot.set`, ...
- Nó **không sao chép sâu** đối tượng `Student` và các đối tượng mà `Student` tham chiếu.
- Nếu thay đổi `Student` đang dùng chung, cả `source` và `snapshot` có thể quan sát trạng thái mới.
- Nếu thêm một `Student` mới vào `source` sau khi gọi `List.copyOf(source)`, danh sách `snapshot` tạo từ nguồn mutable này **không tự nhận thêm phần tử**.

**Chi tiết API quan trọng:**
- `List.copyOf` từ chối phần tử `null` bằng `NullPointerException`; collection nguồn cũng không được là `null`.
- Không nên dựa vào việc kết quả `List.copyOf` luôn là **đối tượng danh sách mới**. Với đầu vào đã là một collection unmodifiable phù hợp, implementation có thể tái sử dụng instance. Điều cần dựa vào là **hợp đồng nội dung và tính unmodifiable**, không phải `==` giữa hai đối tượng danh sách.
- `List.copyOf` không cung cấp cơ chế nhân bản riêng cho kiểu phần tử. Khi cần deep copy, lập trình viên phải định nghĩa rõ phần trạng thái nào cần sao chép.

Các nguyên tắc tương ứng áp dụng cho `Set.copyOf` và `Map.copyOf`: unmodifiable **không đồng nghĩa** phần tử, khóa hoặc giá trị trở nên bất biến sâu.

## 5. `Collections.unmodifiableList(source)` là view, không phải snapshot

Ví dụ:

~~~java
List<String> source = new ArrayList<>();
source.add("A");

List<String> view = Collections.unmodifiableList(source);
source.add("B");

System.out.println(view); // [A, B]
~~~

*Đoạn minh họa cần import `java.util.List`, `ArrayList` và `Collections`.*

`view` là một **unmodifiable view** của chính `source`, không phải một bản sao cấu trúc tách rời.

- `view.add("C")` là lời gọi hợp lệ về mặt cú pháp và kiểu nhưng **ném `UnsupportedOperationException`** khi chạy.
- `source.add("B")` vẫn hoạt động, và `view` nhìn thấy phần tử mới, vì view tham chiếu đến collection nền.
- Nếu phần tử vốn là đối tượng có trạng thái mutable, thao tác sửa phần tử vẫn có thể được nhìn thấy qua view.

So sánh trực tiếp trên một nguồn mutable:

~~~java
List<String> source = new ArrayList<>();
source.add("A");

List<String> snapshot = List.copyOf(source);
List<String> view = Collections.unmodifiableList(source);

source.add("B");

System.out.println(snapshot); // [A]
System.out.println(view);     // [A, B]
~~~

Điểm khác biệt này **không liên quan** đến việc `String` là bất biến; nó nằm ở chỗ `snapshot` có cấu trúc lưu các tham chiếu ban đầu, còn `view` theo dõi collection gốc.

**Lưu ý khi kết hợp API:** `Collections.unmodifiableList(new ArrayList<>(source))` tạo view bọc quanh một **bản sao nông của cấu trúc nguồn**, do đó thay đổi `source.add(...)` sau đó không tự xuất hiện trong view. Tuy nhiên, **các đối tượng phần tử vẫn được chia sẻ**, nên đây vẫn chưa phải deep copy.

## 6. Bản sao sâu (deep copy) là gì?

Bản sao sâu nhằm tạo dữ liệu **độc lập với những đối tượng mutable được sao chép**.

Giả sử:

~~~text
source List ─────► Student("An") ─────► Address("Hue")
shallow List ────► cùng Student ───────► cùng Address
deep List ───────► Student mới ────────► Address mới
~~~

Ở bản sao nông, đối tượng `Student` và `Address` có thể được chia sẻ. Với bản sao sâu của mô hình này:
- Tạo một `Student` mới.
- Tạo một `Address` mới chứa giá trị tương ứng.
- Các thuộc tính immutable như `String` có thể được dùng chung an toàn vì không sửa được nội dung chuỗi.

Nếu chỉ viết:

~~~java
Student copiedStudent = new Student(original.name, original.address);
~~~

thì mới tạo `Student` mới nhưng **vẫn dùng chung `Address`**. Đây chưa phải deep copy đối với mô hình mà `Address` mutable và cần tách biệt.

Cách đúng nếu `Student` chỉ có `name` (chuỗi bất biến) và `address` (đối tượng mutable):

~~~java
Student copiedStudent = new Student(
        original.name,
        new Address(original.address.city)
);
~~~

Hai đoạn này minh họa các kiểu `Student`, `Address` được định nghĩa trong chương trình ở mục 8. Không phải Java có sẵn hàm `deepCopy` chung cho mọi object graph: **phải thiết kế cách sao chép riêng cho cấu trúc dữ liệu của bạn**.

### Deep copy không phải lúc nào cũng là “sao chép tất cả mọi object”

Một deep copy đúng phụ thuộc vào *hợp đồng độc lập* mà bạn cần:
- Những object immutable như `String` thường có thể chia sẻ.
- Các nested mutable list, map, field chứa mutable object có thể cần sao chép tiếp.
- Với đồ thị có tham chiếu vòng hoặc nhiều nhánh cùng trỏ tới một object, cần cân nhắc bảo toàn quan hệ chia sẻ và tránh lặp vô hạn khi copy; có thể dùng bảng ánh xạ object gốc → object mới.
- Với tài nguyên như socket, file handle, thread hoặc database connection, **không** giả định rằng clone chung sẽ tạo ra tài nguyên độc lập hợp lệ.

Do đó, nhãn *deep copy* phải gắn với mô hình dữ liệu cụ thể, thay vì một thao tác API cố định.

## 7. Một bất biến quan trọng: deep copy ≠ deep immutability

Tạo bản sao sâu của `List<Student>` và `Address` giúp **độc lập trạng thái với nguồn**, nhưng nếu `Student` và `Address` vẫn có setter, người sở hữu bản sao vẫn có thể sửa chúng.

Ví dụ:

~~~java
List<Student> deepCopy = source.stream()
        .map(Student::deepCopy)
        .toList();

deepCopy.get(0).address.city = "Da Nang"; // Có thể hợp lệ nếu address mutable
// deepCopy.add(new Student(...));        // Stream.toList() trả list unmodifiable.
~~~

`Stream.toList()` chỉ có từ Java 16 và ví dụ này chạy trên JDK 17+. Nó trả một danh sách không cho sửa cấu trúc; **những đối tượng `Student` và `Address` trong danh sách vẫn mutable** nếu bạn thiết kế chúng như vậy.

Nếu API yêu cầu trạng thái **không thay đổi được qua các object được công bố**, hãy cân nhắc:
1. Chuyển sang value object immutable, chẳng hạn `record StudentSnapshot(String name, String city)` khi các thành phần đều immutable.
2. Chụp lại giá trị từ object mutable vào các object immutable mới.
3. Trả về `List.copyOf(snapshotValues)` hoặc một unmodifiable list của các value object đó.

**Record cũng không mặc định là deep immutable.** Một record chứa field `List<MutableStudent>` hoặc `Address` mutable vẫn có thể để lộ trạng thái thay đổi được. Với `record StudentSnapshot(String name, String city)`, hai thành phần `String` bất biến giúp ví dụ trở thành một snapshot giá trị thực sự độc lập.

## 8. Ví dụ Java 17+ hoàn chỉnh: quan sát cả bốn trường hợp

Tạo tệp **ShallowDeepCopyDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ShallowDeepCopyDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }

        Address deepCopy() {
            return new Address(city);
        }
    }

    static final class Student {
        String name;
        Address address;

        Student(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Student deepCopy() {
            return new Student(name, address.deepCopy());
        }
    }

    record StudentSnapshot(String name, String city) {}

    public static void main(String[] args) {
        var source = new ArrayList<Student>();
        source.add(new Student("An", new Address("Hue")));

        // (1) Bản sao nông, có thể sửa cấu trúc.
        var shallow = new ArrayList<>(source);

        // (2) Java 10: cấu trúc unmodifiable, phần tử vẫn chia sẻ.
        List<Student> readOnlySnapshot = List.copyOf(source);

        // (3) View unmodifiable, quan sát thay đổi của source.
        List<Student> view = Collections.unmodifiableList(source);

        // (4) Copy Student và Address, list do toList() trả về unmodifiable.
        List<Student> deep = source.stream()
                .map(Student::deepCopy)
                .toList();

        // Snapshot immutable gồm các giá trị String.
        List<StudentSnapshot> immutableValues = source.stream()
                .map(s -> new StudentSnapshot(s.name, s.address.city))
                .toList();

        // Sửa nested mutable object của phần tử nguồn.
        source.get(0).address.city = "Da Nang";

        System.out.println("source city = " + source.get(0).address.city);
        System.out.println("shallow city = " + shallow.get(0).address.city);
        System.out.println("copyOf city = " + readOnlySnapshot.get(0).address.city);
        System.out.println("view city = " + view.get(0).address.city);
        System.out.println("deep city = " + deep.get(0).address.city);
        System.out.println("immutable city = " + immutableValues.get(0).city());

        // Thay đổi cấu trúc danh sách nguồn.
        source.add(new Student("Binh", new Address("Ha Noi")));

        System.out.println("source size = " + source.size());
        System.out.println("shallow size = " + shallow.size());
        System.out.println("copyOf size = " + readOnlySnapshot.size());
        System.out.println("view size = " + view.size());
        System.out.println("deep size = " + deep.size());

        // So sánh identity các object, không chỉ so sánh giá trị.
        System.out.println("same shallow student = "
                + (source.get(0) == shallow.get(0)));
        System.out.println("same copyOf student = "
                + (source.get(0) == readOnlySnapshot.get(0)));
        System.out.println("same deep student = "
                + (source.get(0) == deep.get(0)));
        System.out.println("same deep address = "
                + (source.get(0).address == deep.get(0).address));

        try {
            readOnlySnapshot.add(new Student("Chi", new Address("Hue")));
        } catch (UnsupportedOperationException ex) {
            System.out.println("copyOf add = blocked");
        }

        // Tuy không thêm được, vẫn có thể sửa phần tử mutable qua copyOf.
        readOnlySnapshot.get(0).address.city = "Nha Trang";
        System.out.println("source after element edit = "
                + source.get(0).address.city);
        System.out.println("deep after element edit = "
                + deep.get(0).address.city);
        System.out.println("immutable after element edit = "
                + immutableValues.get(0).city());

        // Deep copy không tự làm các phần tử immutable.
        deep.get(0).address.city = "Sai Gon";
        System.out.println("deep changed separately = "
                + deep.get(0).address.city);
        System.out.println("source still = " + source.get(0).address.city);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

~~~bash
javac ShallowDeepCopyDemo.java
java ShallowDeepCopyDemo
~~~

**Đầu ra chính xác:**

~~~text
source city = Da Nang
shallow city = Da Nang
copyOf city = Da Nang
view city = Da Nang
deep city = Hue
immutable city = Hue
source size = 2
shallow size = 1
copyOf size = 1
view size = 2
deep size = 1
same shallow student = true
same copyOf student = true
same deep student = false
same deep address = false
copyOf add = blocked
source after element edit = Nha Trang
deep after element edit = Hue
immutable after element edit = Hue
deep changed separately = Sai Gon
source still = Nha Trang
~~~

### Phân tích các kết quả

1. **Sửa `source.get(0).address.city`:** `shallow`, `readOnlySnapshot`, `view` thấy `Da Nang` vì đều giữ tham chiếu tới cùng `Student` và `Address` gốc. `deep` và `immutableValues` giữ giá trị `Hue` từ thời điểm tạo bản sao.
2. **Thêm `Binh` vào `source`:** chỉ `source` và `view` có kích thước 2; `shallow`, `readOnlySnapshot`, `deep` tiếp tục có kích thước 1. View theo dõi cấu trúc nguồn, các bản sao không theo dõi.
3. **So sánh `==`:** bản sao nông và `copyOf` giữ cùng object `Student`; deep copy tạo `Student` và `Address` mới.
4. **`readOnlySnapshot.add`:** ném `UnsupportedOperationException` vì danh sách không hỗ trợ thêm phần tử.
5. **Sửa `readOnlySnapshot.get(0).address.city`:** được phép vì đối tượng phần tử có thể sửa, và thay đổi ấy xuất hiện lại qua `source`. Danh sách chỉ đọc **không bảo vệ trạng thái bên trong phần tử**.
6. **Sửa phần tử trong `deep`:** có thể đổi thành `Sai Gon`, nhưng `source` vẫn giữ `Nha Trang`. Bản sao sâu tách trạng thái khỏi nguồn mà không nhất thiết làm dữ liệu bất biến.
7. **`immutableValues`:** giữ bản ghi chỉ gồm `String` từ thời điểm chụp, nên không bị ảnh hưởng bởi sửa `Address` nguồn.

Ví dụ không yêu cầu thư viện ngoài. `Stream.toList()` và `record` được sử dụng đúng với JDK 17+, không tuyên bố các tính năng này đã tồn tại ở Java 10.

## 9. Chỉ dùng tính năng có từ Java 10 thì deep copy thế nào?

Nếu mục tiêu là code có thể biên dịch bằng **JDK 10** (không dùng `record`, không dùng `Stream.toList()`), bạn vẫn có thể tạo bản sao sâu bằng vòng lặp:

~~~java
List<Student> deepMutable = new ArrayList<>();
for (Student student : source) {
    deepMutable.add(student.deepCopy());
}
List<Student> deepReadOnly = List.copyOf(deepMutable);
~~~

Đoạn mã trên giả sử `Student` có phương thức `deepCopy()` đúng như mục 8, với các import `java.util.List` và `ArrayList`. Đây là **đoạn minh họa**, không phải tệp độc lập.

Phân tích:
- `new ArrayList<>()` tạo cấu trúc collection mới.
- Mỗi `student.deepCopy()` tạo một đối tượng `Student` mới và các mutable nested object cần tách biệt.
- `List.copyOf(deepMutable)` trả về cấu trúc unmodifiable giữ **các object mới đã được deep copy**.
- Vì `Student` trong ví dụ vẫn mutable, biến `deepReadOnly` vẫn cho phép người dùng sửa trạng thái đối tượng phần tử sau khi lấy bằng `get`. Nó độc lập với `source` nhưng chưa là *deep immutable*.

Nếu cần một snapshot bất biến, xây dựng các phần tử immutable ngay từ đầu, thay vì chỉ bọc danh sách bằng API unmodifiable.

## 10. Bảng tổng hợp: cùng là “không cho sửa”, nhưng khác bản chất

Giả sử `source` là một `ArrayList<MutableStudent>` đang có phần tử:

| Cách tạo | Thêm/xóa qua kết quả | `source.add(...)` tác động đến kết quả? | Sửa `Student` gốc tác động đến kết quả? |
| --- | --- | --- | --- |
| `new ArrayList<>(source)` | Được | Không | Có |
| `List.copyOf(source)` | Không | Không, với nguồn mutable thông thường | Có |
| `Collections.unmodifiableList(source)` | Không | Có | Có |
| `Collections.unmodifiableList(new ArrayList<>(source))` | Không | Không | Có |
| `source.stream().map(Student::deepCopy).toList()` (JDK 16+) | Không | Không | Không, nếu deep copy bao phủ đúng các trạng thái mutable cần tách |
| Snapshot sang object immutable mới rồi `List.copyOf(...)` | Không | Không | Không, nếu mọi trạng thái cần công bố đã được chụp thành giá trị immutable |

**Chú ý về identity:** Nếu `source` đã là một danh sách unmodifiable, `List.copyOf(source)` có thể tái sử dụng đối tượng danh sách đầu vào. Không nên viết test `assertNotSame(source, copied)` như một điều kiện đúng chung cho `copyOf`. Bảng trên xét nguồn là `ArrayList` mutable để so sánh chính xác snapshot và view.

**Chú ý về `Map.copyOf` và `Set.copyOf`:** Chúng cũng không deep-copy từng phần tử/khóa/giá trị. Ngoài ra, thay đổi trạng thái ảnh hưởng đến `equals` hoặc `hashCode` của **khóa map hoặc phần tử set** có thể phá vỡ cách collection tra cứu nhất quán; tránh dùng khóa hoặc phần tử có trạng thái liên quan đến hashing bị sửa sau khi đưa vào collection.

## 11. Những sai lầm phổ biến

### Sai lầm 1: “`List.copyOf()` chính là deep copy”

Không. Nó tạo danh sách unmodifiable chứa **các phần tử hiện có**, không nhân bản tùy ý từng mutable object. Muốn tách trạng thái, phải tự copy phần tử và phần tham chiếu lồng bên trong.

### Sai lầm 2: “`Collections.unmodifiableList()` là snapshot”

Không. Khi bọc trực tiếp một danh sách có thể sửa, view vẫn quan sát thay đổi cấu trúc ở danh sách nền. Nếu cần snapshot không đổi số phần tử, tạo bản sao cấu trúc trước hoặc dùng `List.copyOf` với nguồn mutable thông thường.

### Sai lầm 3: “Danh sách unmodifiable không bao giờ có dữ liệu thay đổi”

Không. Danh sách unmodifiable không cho sửa cấu trúc qua API của nó; **mutable element** vẫn có thể đổi trạng thái. Với view, cấu trúc nguồn cũng có thể đổi.

### Sai lầm 4: “`new ArrayList<>(source)` tạo các phần tử hoàn toàn mới”

Không. Nó tạo cấu trúc danh sách mới nhưng giữ tham chiếu tới phần tử cũ.

### Sai lầm 5: “Gọi `clone()` là cách deep copy mặc định”

Không. Mặc định `Object.clone()` sao chép field của một object; field tham chiếu vẫn chỉ là tham chiếu, nên kết quả thường là shallow copy nếu không có logic bổ sung. Việc sử dụng `Cloneable`/`clone()` không phải lựa chọn mặc định cho thiết kế copy rõ ràng trong code Java hiện đại. Có thể dùng constructor sao chép, factory hoặc mapper được thiết kế cụ thể.

### Sai lầm 6: “Dùng `record` là dữ liệu trở nên bất biến sâu”

Không luôn đúng. Record cung cấp thành phần final theo mô hình dữ liệu của nó, nhưng nếu một thành phần trỏ đến object mutable, object ấy vẫn có thể sửa được. Chọn các thành phần immutable hoặc copy phòng vệ khi xây dựng và công bố.

### Sai lầm 7: “Collection chỉ đọc là collection thread-safe”

Không. Unmodifiable và snapshot/deep copy là những đặc tính khác với thread safety. Nếu nhiều thread vẫn có đường sửa phần tử hoặc nguồn của một view, cần cơ chế đồng bộ/thiết kế concurrent phù hợp. Không dùng `List.copyOf` làm lời hứa thread-safe cho mọi object graph.

### Sai lầm 8: “`List.copyOf` giữ `null` như `new ArrayList<>(source)`”

Không. `List.copyOf` từ chối `null` trong đầu vào. Hãy kiểm tra dữ liệu và quyết định cách biểu diễn trạng thái thiếu trước khi xây dựng snapshot.

## 12. Gợi ý lựa chọn theo tình huống thực tế

| Nhu cầu | Phương án thường phù hợp | Cần lưu ý |
| --- | --- | --- |
| Chỉ muốn tách cấu trúc, cho phép sửa danh sách kết quả | `new ArrayList<>(source)` | Vẫn chia sẻ mutable elements |
| Muốn snapshot cấu trúc không cho sửa bằng API List (Java 10+) | `List.copyOf(source)` | Bản sao nông, không deep immutable |
| Muốn một view chỉ đọc *theo dõi nguồn* | `Collections.unmodifiableList(source)` | Source thay đổi thì view thay đổi |
| Muốn snapshot cấu trúc, nhưng cần tiếp tục dùng API trước Java 10 | `Collections.unmodifiableList(new ArrayList<>(source))` | Vẫn là shallow copy |
| Muốn bản sao tách trạng thái object mutable khỏi nguồn | Copy từng phần tử và nested mutable state | Xử lý đủ các nhánh tham chiếu được hợp đồng yêu cầu |
| Muốn trả dữ liệu bất biến lâu dài từ API | Snapshot thành immutable value objects, collection unmodifiable | Không để lộ mutable object qua getter, constructor hoặc nested references |
| Muốn tránh sao chép tốn kém khi phần tử thật sự immutable | Có thể giữ và chia sẻ phần tử immutable | Phải hiểu rõ immutable sâu hay chỉ bất biến nông |

### Nguyên tắc defensive copying tại ranh giới API

Giả sử một service lưu trạng thái nội bộ và trả danh sách cho người gọi:
- Trả trực tiếp `internalList` cho phép người gọi thay đổi danh sách nếu nó mutable.
- Trả `Collections.unmodifiableList(internalList)` ngăn thay đổi **qua wrapper**, nhưng người gọi vẫn có thể quan sát thay đổi nội bộ về sau.
- Trả `List.copyOf(internalList)` chụp cấu trúc ở thời điểm gọi (với nguồn mutable), nhưng nếu các phần tử mutable, người gọi có thể sửa **các object được chia sẻ** và ảnh hưởng đến state nội bộ.
- Nếu state phải được bảo vệ đầy đủ, **copy phần tử và trạng thái mutable bên trong**, rồi chỉ trả ra các giá trị immutable hoặc bản sao an toàn theo hợp đồng đã xác định.

Không cần sao chép sâu mọi lúc: với dữ liệu lớn, deep copy có chi phí CPU và bộ nhớ. Chọn đúng mức bảo vệ theo yêu cầu **ownership**, tính bất biến, tần suất cập nhật và vòng đời của dữ liệu.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `List.copyOf(source)` có tạo ra `Student` mới cho từng phần tử `Student` trong `source` không?

**Đáp án:** Không. Nó tạo danh sách unmodifiable chứa tham chiếu phần tử; đây là shallow copy về nội dung.

**Câu 2.** Sau khi tạo `view = Collections.unmodifiableList(source)`, nếu gọi `source.add("B")` thì `view` có thấy `"B"` không?

**Đáp án:** Có, nếu `view` bọc trực tiếp chính `source`: view phản ánh cấu trúc của collection nền.

**Câu 3.** Vì sao `snapshot.add(x)` thất bại nhưng `snapshot.get(0).rename("New")` vẫn có thể thành công?

**Đáp án:** `List.copyOf` cấm sửa cấu trúc danh sách qua API nhưng không làm object phần tử `Student` bất biến. Phương thức `rename` sửa chính `Student`.

**Câu 4.** `new ArrayList<>(source)` có tách trạng thái một `Address` mutable lồng trong `Student` không?

**Đáp án:** Không. Nó chỉ sao chép cấu trúc và tham chiếu phần tử, nên `Address` có thể được chia sẻ.

**Câu 5.** `deep = source.stream().map(Student::deepCopy).toList()` có đảm bảo `Student` trong `deep` không sửa được không?

**Đáp án:** Không. `Stream.toList()` trả danh sách unmodifiable nhưng các `Student` mới vẫn có thể mutable. Deep copy là độc lập với nguồn, không phải bất biến tuyệt đối.

**Câu 6.** Có nên deep-copy `String` bằng cách tạo chuỗi mới riêng cho mỗi phần tử không?

**Đáp án:** Thông thường không cần. `String` là immutable, nên có thể chia sẻ an toàn nếu hợp đồng cần bảo vệ nội dung chuỗi.

**Câu 7.** Vì sao `record StudentSnapshot(String name, String city)` trong ví dụ có thể là một snapshot immutable hiệu quả?

**Đáp án:** Nó lưu trực tiếp hai giá trị `String` bất biến được chụp lại từ nguồn, không công bố tham chiếu `Address` mutable. Không suy ra rằng **mọi** record đều bất biến sâu.

**Câu 8.** `List.copyOf` có bảo đảm luôn trả một list có identity mới khác input không?

**Đáp án:** Không. Với đầu vào unmodifiable phù hợp, implementation có thể tái sử dụng instance; nên kiểm tra giá trị và hợp đồng, không dựa vào `==` giữa hai list.

## 14. Ghi nhớ cuối bài

1. **Shallow copy:** cấu trúc collection mới nhưng **tham chiếu phần tử cũ**; thay đổi object phần tử có thể được thấy ở nhiều nơi.
2. **Deep copy:** sao chép các đối tượng và nested mutable state cần tách biệt; không có một thuật toán mặc định chung cho mọi object graph.
3. **`List.copyOf` (Java 10):** danh sách không cho sửa cấu trúc, nhưng **không tự deep-copy phần tử**; không nhận `null`.
4. **`Collections.unmodifiableList`:** một view không cho sửa qua wrapper, nhưng có thể quan sát thay đổi cấu trúc của collection gốc.
5. **Unmodifiable khác với immutable sâu**; **deep copy khác với immutable sâu**; cả hai cũng không tự bảo đảm thread safety.
6. Khi công bố dữ liệu qua API, hãy nói rõ **snapshot hay view**, **shallow hay deep**, và **phần trạng thái nào được cam kết không bị thay đổi**.

**Tài liệu tham khảo còn áp dụng:**
- [Java SE 17 — List.copyOf(Collection)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Java SE 17 — Collections.unmodifiableList(List)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))
- [Java SE 17 — Stream.toList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Java SE 17 — List.of(...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#of(E...))
