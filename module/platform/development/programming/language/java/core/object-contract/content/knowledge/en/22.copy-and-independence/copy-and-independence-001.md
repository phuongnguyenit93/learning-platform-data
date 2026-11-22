# Sao chép nông và sao chép sâu trong Java

## 1. Vì sao cần phân biệt?

Trong Java, biến có kiểu tham chiếu lưu **tham chiếu đến đối tượng**, không chứa nguyên đối tượng. Khi gán một biến tham chiếu cho biến khác, Java sao chép **giá trị tham chiếu**: cả hai biến cùng trỏ đến một đối tượng. Gán biến không tạo ra đối tượng mới.

```java
Person a = new Person(...);
Person b = a; // b và a cùng tham chiếu một Person
```

Dòng khai báo trên là đoạn minh họa; `Person` cần được định nghĩa riêng. Muốn có bản sao, chương trình phải chủ động tạo đối tượng khác, chẳng hạn qua constructor, phương thức sao chép, `clone()` hoặc cơ chế ánh xạ phù hợp.

Vấn đề quan trọng xuất hiện khi đối tượng chứa **trường tham chiếu đến các đối tượng khác**. Một đối tượng `Person` có trường `address` tham chiếu đến `Address`; `Address` lại có thể có danh sách dữ liệu khác. Tổng thể các đối tượng và liên kết đó gọi là *đồ thị đối tượng* (*object graph*).

- **Sao chép nông (shallow copy):** tạo đối tượng gốc mới, sao chép các giá trị trường; trường nguyên thủy được sao chép theo giá trị, còn trường tham chiếu vẫn tham chiếu đến đối tượng con cũ.
- **Sao chép sâu (deep copy):** tạo bản sao độc lập cho những đối tượng con **cần độc lập** trong phạm vi sao chép đã xác định; các liên kết trong bản sao trỏ đến bản sao tương ứng. Những giá trị bất biến như `String` thường có thể chia sẻ an toàn.
- **Độc lập** phải được hiểu theo phần trạng thái có thể thay đổi (*mutable state*): sửa trạng thái của bản sao không được vô tình sửa trạng thái của bản gốc và ngược lại, trong phạm vi đã cam kết.

Minh họa với một trường tham chiếu có thể thay đổi:

```text
Bản gốc:          Person P1 ──address──> Address A1
Bản sao nông:     Person P2 ──address──> Address A1  (dùng chung)
Bản sao sâu:      Person P3 ──address──> Address A2  (độc lập với A1)
```

`P1`, `P2` và `P3` là ba đối tượng `Person` khác nhau. Điểm khác biệt nằm ở đối tượng `Address` mà chúng giữ.

## 2. Ví dụ Java 17: quan sát sự khác biệt

Tạo tệp `CopyDemo.java`:

```java
public class CopyDemo {
    static class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static class Person {
        String name;
        Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person shallowCopy() {
            return new Person(name, address);
        }

        Person deepCopy() {
            return new Person(name, new Address(address.city));
        }
    }

    public static void main(String[] args) {
        Person original = new Person("An", new Address("Hà Nội"));
        Person shallow = original.shallowCopy();
        Person deep = original.deepCopy();

        System.out.println("original == shallow: " + (original == shallow));
        System.out.println("same address in shallow: "
                + (original.address == shallow.address));
        System.out.println("same address in deep: "
                + (original.address == deep.address));

        shallow.address.city = "Đà Nẵng";
        System.out.println("original after shallow edit: " + original.address.city);

        deep.address.city = "Huế";
        System.out.println("original after deep edit: " + original.address.city);
        System.out.println("deep after edit: " + deep.address.city);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 CopyDemo.java
java CopyDemo
```

Kết quả:

```text
original == shallow: false
same address in shallow: true
same address in deep: false
original after shallow edit: Đà Nẵng
original after deep edit: Đà Nẵng
deep after edit: Huế
```

Giải thích từng bước:

1. `shallowCopy()` tạo một `Person` mới nhưng truyền thẳng `address` cũ vào constructor; sửa `shallow.address.city` cũng sửa thành phố nhìn thấy từ `original`.
2. `deepCopy()` tạo cả `Person` và `Address` mới; sửa `deep.address.city` không tác động đến `original.address.city`.
3. `name` là `String` bất biến, nên dùng chung tham chiếu `name` không gây rò rỉ thay đổi trạng thái.
4. Ví dụ giả định `address` khác `null` và `Address` chỉ có một trường `String`. Khi cấu trúc dữ liệu phức tạp hơn, hàm sao chép phải xử lý thêm các trường và quan hệ tương ứng.

**Chú ý:** `original == shallow` trả về `false` chỉ xác nhận hai đối tượng `Person` khác nhau. Nó **không** chứng minh tất cả đối tượng con đã được sao chép.

## 3. So sánh theo các tiêu chí quan trọng

| Tiêu chí | Gán tham chiếu | Sao chép nông | Sao chép sâu |
| --- | --- | --- | --- |
| Đối tượng ở mức gốc | Dùng chung | Tạo mới | Tạo mới |
| Trường kiểu nguyên thủy | Cùng đối tượng gốc | Sao chép giá trị | Sao chép giá trị |
| Trường tham chiếu có thể thay đổi | Dùng chung | Thường dùng chung đối tượng con | Sao chép đối tượng con thuộc phạm vi cần độc lập |
| Thay đổi trường của đối tượng gốc | Nhìn thấy qua mọi biến cùng trỏ đến nó | Không làm đổi trường tương ứng của bản sao nếu trường được gán lại trên một đối tượng gốc riêng | Không làm đổi trường tương ứng của bản sao |
| Thay đổi *trạng thái bên trong* đối tượng con | Nhìn thấy ở cả hai | Có thể lan sang bản kia | Không lan sang bản kia trong phạm vi sao chép |
| Chi phí | Thường là thao tác gán rất nhỏ | Thường thấp hơn deep copy | Tùy số đối tượng/quan hệ thực sự phải tạo |
| Phù hợp | Cố ý chia sẻ đúng một đối tượng | Muốn đối tượng bao mới nhưng có thể chia sẻ phần bên trong | Cần cô lập trạng thái mutable |

Không thể nhận biết loại sao chép chỉ từ việc có dùng `new` hay không. `new Person(old.name, old.address)` chỉ sao chép nông đối với `address`; constructor copy cũng có thể là shallow hoặc deep tùy cách hiện thực.

## 4. Bộ sưu tập và mảng: tạo container mới chưa phải deep copy

`new ArrayList<>(source)` tạo danh sách mới và sao chép các **tham chiếu phần tử**, không tự tạo bản sao từng đối tượng. `HashMap` copy constructor tương tự: cấu trúc map mới nhưng khóa và giá trị thường vẫn được dùng chung. `array.clone()` hoặc `Arrays.copyOf(...)` sao chép mảng; nếu phần tử là tham chiếu, các đối tượng phần tử vẫn được chia sẻ.

Ví dụ chạy độc lập trong `CollectionCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CollectionCopyDemo {
    static class Task {
        String title;

        Task(String title) {
            this.title = title;
        }
    }

    public static void main(String[] args) {
        List<Task> original = new ArrayList<>();
        original.add(new Task("Học Java"));

        List<Task> shallow = new ArrayList<>(original);
        List<Task> unmodifiable = List.copyOf(original);

        shallow.get(0).title = "Học Java 17";
        System.out.println(original.get(0).title);
        System.out.println(unmodifiable.get(0).title);

        shallow.add(new Task("Viết test"));
        System.out.println(original.size());
        System.out.println(shallow.size());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CollectionCopyDemo.java
java CollectionCopyDemo
```

Kết quả:

```text
Học Java 17
Học Java 17
1
2
```

`List.copyOf(original)` tạo danh sách **không cho sửa cấu trúc qua danh sách kết quả**, nhưng không làm cho từng `Task` trở nên bất biến và không deep-copy `Task`. Nếu danh sách đầu vào đã là danh sách không thể sửa, Java có thể tái sử dụng đối tượng danh sách đó. `List.copyOf` cũng không chấp nhận phần tử `null`.

Phân biệt thêm:

- `Collections.unmodifiableList(list)` thường là *view*: không cho sửa qua view, nhưng thay đổi cấu trúc trên `list` gốc có thể xuất hiện trong view.
- `List.copyOf(list)` cho danh sách không thể sửa với tập phần tử tại thời điểm gọi; nó không bảo vệ trạng thái mutable của các phần tử.
- Sao chép sâu một `List<Task>` đòi hỏi tạo container phù hợp **và** tạo `Task` mới cho từng phần tử cần độc lập, đồng thời xem xét trường tham chiếu bên trong `Task`.
- Nếu toàn bộ phần tử là giá trị bất biến (ví dụ `String`), sao chép container có thể đủ để cô lập thay đổi cấu trúc; sao chép thêm từng `String` không đem lại lợi ích.

Ví dụ hướng xử lý danh sách đơn giản, khi `Task` chỉ có trường `title` như trên:

```java
List<Task> deepTasks = original.stream()
        .map(task -> new Task(task.title))
        .toList();
```

Đây là **đoạn mã minh họa nằm trong ngữ cảnh** của `CollectionCopyDemo`, không phải một tệp chạy riêng. `Stream.toList()` (Java 16+) trả về danh sách không thể sửa; các `Task` mới vẫn có thể thay đổi. Nếu cần thêm/xóa phần tử, bọc kết quả trong `new ArrayList<>(...)`.


## 5. Từ khái niệm đến hợp đồng sao chép

Shallow copy và deep copy là cách mô tả **mức độ chia sẻ tham chiếu**, không phải tên của một API cụ thể. Copy constructor, factory, `clone()` hay cơ chế ánh xạ chỉ đạt được mức độc lập mà phần triển khai thật sự bảo đảm. Một lớp có thể chia sẻ `String` bất biến nhưng phải sao chép mảng, collection hay phần tử mutable nếu hợp đồng yêu cầu tách trạng thái.

Với đồ thị có hai cạnh cùng trỏ một nút hoặc có chu trình, việc sao chép đệ quy từng nhánh có thể làm mất cấu trúc hoặc lặp vô hạn. Khi cần bảo toàn quan hệ, phải ghi nhớ mỗi nút gốc theo **identity** trong cùng một phiên sao chép. Với trường `final` trỏ tới dữ liệu mutable, `super.clone()` vẫn sao chép nông và không cho phép gán lại trường sau clone; constructor/factory có thể khởi tạo trường final bằng bản sao riêng.

Các bài tiếp theo lần lượt đi sâu vào chia sẻ immutable, defensive copy, đồ thị có chu trình, ràng buộc `final`, copy constructor/factory, ownership, kiểm thử hai chiều và giới hạn của serialization. Ở bài này, chỉ cần nắm nguyên lý và biết cách chọn phạm vi sao chép.

## 6. Chọn chiến lược trong thực tế

1. **Chỉ cần một tên tham chiếu khác cho cùng đối tượng:** dùng phép gán, hiểu rằng trạng thái được chia sẻ.
2. **Cần một đối tượng/container mới nhưng vẫn chủ động dùng chung các phần tử:** dùng shallow copy và ghi rõ hợp đồng chia sẻ.
3. **Cần chỉnh sửa bản sao mà không ảnh hưởng bản gốc:** xây dựng deep copy trong phạm vi mutable phù hợp; ưu tiên copy constructor/factory rõ ràng.
4. **Muốn tránh chi phí và lỗi sao chép:** cân nhắc immutable value object, defensive copy ở ranh giới API, hoặc snapshot chuyên dụng.
5. **Đồ thị có chu trình/alias:** thiết kế thuật toán duyệt có bảng identity, kiểm tra quan hệ liên kết và độ sâu dữ liệu.
6. **Đối tượng chứa resource hoặc tham gia xử lý đồng thời:** xác định vòng đời, quyền sở hữu và snapshot consistency trước khi chọn cách copy.

Khi thiết kế một API copy, hãy mô tả: bản sao có instance gốc mới không; các trường mutable nào được tách; những giá trị nào có chủ đích dùng chung; quan hệ alias/cycle có được giữ không; xử lý `null`, kế thừa và lỗi ra sao; và việc sao chép có nhất quán trước cập nhật đồng thời hay không.

## 7. Tự kiểm tra kiến thức

- Nếu một `List<Employee>` được tạo bằng `new ArrayList<>(oldList)`, thao tác `add()` vào danh sách mới có ảnh hưởng `oldList` không? Nếu sửa `newList.get(0).name`, tác động sẽ ra sao khi `Employee` mutable?
- Nếu `a.left == a.right`, bản sao sâu đúng phải thỏa quan hệ gì giữa `copy.left` và `copy.right`? Tại sao chỉ clone đệ quy từng trường lại có thể sai?
- Vì sao `String` dùng chung thường không phá tính độc lập, còn `ArrayList` dùng chung có thể phá?
- Một phương thức copy tạo đối tượng gốc mới nhưng giữ nguyên `Socket` và `List<MutableItem>`. Hãy giải thích phần nào chỉ được sao chép nông và cách mô tả hợp đồng an toàn.

**Ghi nhớ:** Nông/sâu không phụ thuộc tên phương thức hay sự xuất hiện của `new`. Điều quyết định là **đồ thị tham chiếu và trạng thái mutable nào được chia sẻ sau khi copy**.