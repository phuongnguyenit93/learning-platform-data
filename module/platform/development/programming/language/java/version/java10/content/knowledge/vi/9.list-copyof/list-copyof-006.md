# Chia sẻ tham chiếu của từng phần tử sau khi sao chép với `List.copyOf` (Java 10+)

## 1. Mục tiêu và nguyên tắc cốt lõi

`List.copyOf(Collection<? extends E>)` được bổ sung trong **Java 10**. Phương thức tạo ra một `List` **không hỗ trợ sửa cấu trúc qua API của danh sách** (*unmodifiable list*) chứa các phần tử có trong collection nguồn tại thời điểm gọi. Nhưng **`List.copyOf` không nhân bản từng đối tượng phần tử**.

Nếu `source` chứa tham chiếu đến một đối tượng `Student`, thì danh sách do `List.copyOf(source)` tạo ra có thể giữ **chính tham chiếu đến `Student` ấy**. Kết quả là:
- Sửa **trạng thái bên trong `Student`** có thể được nhìn thấy qua cả `source` và bản sao.
- Thêm, xóa hoặc thay thế **vị trí phần tử của `source`** sau khi sao chép thường **không** làm thay đổi cấu trúc bản sao.
- Không thể `add`, `remove`, `set` qua list trả về bởi `List.copyOf`; thao tác sửa đổi sẽ ném `UnsupportedOperationException`.
- Khi phần tử là đối tượng bất biến như `String`, việc chia sẻ tham chiếu thường không gây vấn đề về thay đổi trạng thái phần tử.

Đây là điểm phân biệt giữa **bản sao nông về phần tử** (*shallow copy*) và **bản sao sâu** (*deep copy*). `List.copyOf` làm cho danh sách không thể sửa qua API của nó, nhưng không bảo đảm tất cả đối tượng mà danh sách trỏ tới đều bất biến.

Bài này tập trung đúng vào việc **chia sẻ tham chiếu của các phần tử** trong chủ đề `List.copyOf`, đi từ mô hình tham chiếu đến ví dụ Java 17+ chạy được, tác động đến nested object và cách bảo vệ trạng thái ở ranh giới API. Quy tắc vẫn áp dụng trong Java hiện đại.

## 2. Mô hình bộ nhớ: bản sao danh sách khác với bản sao đối tượng phần tử

Giả sử có hai danh sách:

~~~java
var source = new ArrayList<Student>();
source.add(new Student("An"));

List<Student> copy = List.copyOf(source);
~~~

Đây là đoạn minh họa trong phương thức đã import `java.util.List`, `java.util.ArrayList` và định nghĩa lớp `Student`. Chương trình đầy đủ ở mục 8.

Hình dung trạng thái:

~~~text
source  ──► [ phần tử 0 ] ──► Student("An")
                              ▲
copy    ──► [ phần tử 0 ] ─────┘

source: có thể thay đổi cấu trúc
copy:   không cho sửa cấu trúc qua List
Student: cùng một đối tượng được cả hai tham chiếu
~~~

**Hai điều không được nhầm:**
1. **Đối tượng danh sách:** `source` và `copy` là các biến tham chiếu tới danh sách. Với đầu vào `source` là một `ArrayList` mutable thông thường, `List.copyOf(source)` tạo kết quả unmodifiable riêng về cấu trúc.
2. **Đối tượng phần tử:** Các tham chiếu phần tử được đưa vào danh sách kết quả; `List.copyOf` **không gọi `new Student(...)`** hay một hàm `deepCopy()` cho từng phần tử.

Khi nói `copy` là một *snapshot*, ta đang nói tới **chuỗi các tham chiếu phần tử tại thời điểm sao chép**, không phải trạng thái sâu của từng đối tượng mãi mãi được chụp lại.

### Dùng `==` để quan sát identity của phần tử

~~~java
Student student = new Student("An");
var source = new ArrayList<Student>();
source.add(student);

var copy = List.copyOf(source);
System.out.println(source.get(0) == copy.get(0)); // true
~~~

`==` với hai biến tham chiếu kiểm tra **cùng đối tượng** (*reference identity*). Kết quả `true` cho thấy hai ô ở hai danh sách trỏ tới **chính `Student` đó**.

Ngược lại, `equals()` có thể kiểm tra bằng giá trị tùy cách lớp triển khai. Hai object khác nhau vẫn có thể `equals() == true`. Vì thế, để kiểm tra việc chia sẻ tham chiếu trong bài học này, `==` trực tiếp và dễ hiểu hơn `equals()`.

## 3. Thay đổi trạng thái phần tử: cả hai danh sách cùng nhìn thấy

Giả sử `Student` là mutable:

~~~java
static final class Student {
    String name;

    Student(String name) {
        this.name = name;
    }
}
~~~

Dưới đây là đoạn minh họa đặt trong phương thức có thể sử dụng kiểu `Student`:

~~~java
var source = new ArrayList<Student>();
source.add(new Student("An"));

var copy = List.copyOf(source);
source.get(0).name = "Binh";

System.out.println(source.get(0).name); // Binh
System.out.println(copy.get(0).name);   // Binh
~~~

Vì `source.get(0)` và `copy.get(0)` trả về cùng một đối tượng `Student`, việc đổi field `name` tác động đến **object đó**, không phải đến cấu trúc list. Do vậy cả hai vị trí đều quan sát được tên mới.

Đảo chiều thao tác cũng được:

~~~java
copy.get(0).name = "Chi";
System.out.println(source.get(0).name); // Chi
~~~

Ở đây `copy.get(0).name = "Chi"` **không phải phép sửa list**. Nó chỉ đọc phần tử rồi sửa trạng thái của object mutable mà phần tử ấy trỏ tới. Không có `UnsupportedOperationException` từ `List.copyOf` cho phép gán field đó; mức độ cho phép sửa nằm ở thiết kế lớp `Student` và quyền truy cập field hoặc setter.

**Kết luận:** *unmodifiable list* không có nghĩa là *immutable elements*. Nếu API công bố danh sách chứa mutable object, người dùng có thể sửa đối tượng được chia sẻ và ảnh hưởng đến trạng thái của thành phần khác.

## 4. Thay đổi cấu trúc nguồn: bản sao giữ tham chiếu cũ

Hãy phân biệt **sửa bản thân đối tượng phần tử** với **thay đối tượng ở một vị trí trong list**.

~~~java
var first = new Student("An");
var source = new ArrayList<Student>();
source.add(first);

var copy = List.copyOf(source);

// Thay tham chiếu tại vị trí 0 trong danh sách nguồn:
source.set(0, new Student("Binh"));

System.out.println(source.get(0).name); // Binh
System.out.println(copy.get(0).name);   // An
System.out.println(copy.get(0) == first); // true
~~~

Khi `source.set(0, ...)` chạy:
- Danh sách nguồn đổi **tham chiếu ở vị trí 0** sang một đối tượng `Student` mới.
- Danh sách `copy` vẫn giữ **tham chiếu ban đầu** tới `first`.
- Vì vậy `copy.get(0).name` tiếp tục là `An`, trừ khi bản thân đối tượng `first` được sửa ở nơi khác.

Tương tự, khi thêm hoặc xóa phần tử trong danh sách nguồn mutable:

~~~java
var source = new ArrayList<String>();
source.add("A");

var copy = List.copyOf(source);
source.add("B");

System.out.println(source); // [A, B]
System.out.println(copy);   // [A]
~~~

`copy` không tự nhận phần tử mới. Dạng thay đổi cấu trúc nguồn **không được phản chiếu** trong snapshot do `List.copyOf` tạo từ một danh sách mutable thông thường.

Đây là sự khác biệt bản chất: **sửa object mà cả hai cùng tham chiếu thì cả hai thấy; thay tham chiếu trong collection nguồn thì chỉ nguồn đổi**.

## 5. Cấm sửa danh sách không có nghĩa cấm sửa các phần tử

Mọi collection trả về bởi `List.copyOf` không hỗ trợ những phép thay đổi cấu trúc qua API `List`:

~~~java
var source = new ArrayList<Student>();
source.add(new Student("An"));
var copy = List.copyOf(source);

// copy.add(new Student("Binh")); // Hợp lệ về cú pháp/kiểu,
// nhưng ném UnsupportedOperationException khi thực thi.

// copy.set(0, new Student("Chi")); // Cũng ném UnsupportedOperationException.

// copy.remove(0); // Cũng ném UnsupportedOperationException.
~~~

Tuy nhiên:

~~~java
copy.get(0).name = "Minh"; // Có thể hợp lệ nếu Student.name được phép sửa
~~~

Không có mâu thuẫn:
- `copy.set(0, replacement)` cố **đổi phần tử được lưu ở vị trí 0**, bị cấm.
- `copy.get(0).name = "Minh"` chỉ **đổi trạng thái của object mà vị trí 0 đang trỏ đến**, không đổi cấu trúc list.

Nếu `Student` được thiết kế bất biến (không có field hoặc API cho sửa trạng thái sau khi tạo), phép sửa `name` sẽ không hợp lệ. Nhưng khi đó **tính bất biến đến từ lớp `Student`**, không phải từ `List.copyOf`.

Lưu ý thêm: `List.copyOf` không nhận collection nguồn `null` hoặc phần tử `null` trong nguồn; những trường hợp này phát sinh `NullPointerException`. Đây là điều kiện của API, không liên quan đến shallow hay deep copy.

## 6. Tham chiếu lồng nhau: shallow copy lan tới các object con

Một object phần tử có thể giữ tham chiếu tới các object mutable khác, ví dụ `Student` giữ `Address`:

~~~java
static final class Address {
    String city;
    Address(String city) { this.city = city; }
}

static final class Student {
    String name;
    Address address;

    Student(String name, Address address) {
        this.name = name;
        this.address = address;
    }
}
~~~

Đây là mô hình kiểu minh họa; mã hoàn chỉnh ở mục 8.

Nếu cả `source` và `copy` cùng tham chiếu tới `Student`, thì chúng cũng có thể quan sát cùng `Student.address`:

~~~java
var source = new ArrayList<Student>();
source.add(new Student("An", new Address("Hue")));

var copy = List.copyOf(source);
source.get(0).address.city = "Da Nang";

System.out.println(copy.get(0).address.city); // Da Nang
~~~

`List.copyOf` không duyệt đồ thị đối tượng để tạo `Student` mới hay `Address` mới. Nó chỉ ghi nhận tham chiếu phần tử ở cấp `List`.

**Một lưu ý dễ bỏ sót:** kể cả khi class `Student` dùng `final Address address`, field `address` không thể trỏ sang `Address` khác sau khi khởi tạo, nhưng **bản thân `Address` vẫn có thể mutable**. Tương tự, một `record` chứa `Address` mutable không tự trở thành immutable sâu.

Hãy hỏi liệu **trạng thái mà API muốn bảo vệ** chỉ nằm ở danh sách, ở object phần tử, hay sâu hơn trong các field của object phần tử.

## 7. So sánh `List.copyOf`, copy constructor và unmodifiable view

Cùng một collection nguồn mutable, ba cách phổ biến sẽ có hệ quả khác nhau:

| Cách tạo | Sửa cấu trúc qua kết quả? | Sửa cấu trúc nguồn ảnh hưởng kết quả? | Sửa object phần tử gốc ảnh hưởng kết quả? |
| --- | --- | --- | --- |
| `new ArrayList<>(source)` | Có | Không | Có |
| `List.copyOf(source)` | Không | Không | Có |
| `Collections.unmodifiableList(source)` | Không | **Có** | Có |
| `Collections.unmodifiableList(new ArrayList<>(source))` | Không | Không | Có |

Giải thích:
- **`new ArrayList<>(source)`** tạo cấu trúc list mới **có thể sửa**, nhưng sao chép nông các tham chiếu phần tử.
- **`List.copyOf(source)`** chụp các tham chiếu phần tử vào một list **unmodifiable**; với nguồn là `ArrayList` mutable, thay đổi cấu trúc sau đó không làm snapshot đổi theo.
- **`Collections.unmodifiableList(source)`** chỉ tạo **view** bọc quanh chính `source`. Nếu code khác thêm/xóa/thay thế phần tử trong `source`, view phản ánh cấu trúc mới.
- **`Collections.unmodifiableList(new ArrayList<>(source))`** bọc một bản sao cấu trúc, không theo dõi cấu trúc nguồn nhưng vẫn **chia sẻ phần tử**.

Hai phương thức `List.copyOf` và `Collections.unmodifiableList` thường được gọi chung là “read-only list” trong giao tiếp hằng ngày, nhưng **snapshot và view là hai hợp đồng khác nhau**.

Ví dụ nhỏ:

~~~java
var source = new ArrayList<String>();
source.add("A");

var snapshot = List.copyOf(source);
var view = Collections.unmodifiableList(source);

source.set(0, "B");
source.add("C");

System.out.println(snapshot); // [A]
System.out.println(view);     // [B, C]
~~~

Hai lệnh `set` và `add` thay đổi cấu trúc hoặc phần tử tại vị trí của `source`. View theo dõi `source`; snapshot giữ các tham chiếu đã chụp tại thời điểm gọi.

## 8. Chương trình Java 17+ độc lập: kiểm tra tham chiếu, sửa object và thay phần tử

Tạo tệp **ListCopyOfReferencesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class ListCopyOfReferencesDemo {
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
        final String id;
        String name;
        final Address address;

        Student(String id, String name, Address address) {
            this.id = id;
            this.name = name;
            this.address = address;
        }

        Student deepCopy() {
            return new Student(id, name, address.deepCopy());
        }
    }

    record StudentSnapshot(String id, String name, String city) {}

    public static void main(String[] args) {
        var source = new ArrayList<Student>();
        var original = new Student("01", "An", new Address("Hue"));
        source.add(original);

        List<Student> snapshot = List.copyOf(source);
        List<Student> shallow = new ArrayList<>(source);
        List<Student> view = Collections.unmodifiableList(source);

        System.out.println("same list = " + (source == snapshot));
        System.out.println("same student = "
                + (source.get(0) == snapshot.get(0)));
        System.out.println("same address = "
                + (source.get(0).address == snapshot.get(0).address));

        // Thay đổi trạng thái của Student và Address đang được chia sẻ.
        original.name = "Binh";
        original.address.city = "Da Nang";
        System.out.println("source name = " + source.get(0).name);
        System.out.println("snapshot name = " + snapshot.get(0).name);
        System.out.println("snapshot city = " + snapshot.get(0).address.city);

        // Thay đổi các tham chiếu trong cấu trúc nguồn.
        source.set(0, new Student("02", "Chi", new Address("Ha Noi")));
        source.add(new Student("03", "Dung", new Address("Hue")));

        System.out.println("source size = " + source.size());
        System.out.println("snapshot size = " + snapshot.size());
        System.out.println("view size = " + view.size());
        System.out.println("source first = " + source.get(0).name);
        System.out.println("snapshot first = " + snapshot.get(0).name);
        System.out.println("view first = " + view.get(0).name);

        // Bản sao nông khác cũng giữ cùng Student cũ.
        snapshot.get(0).name = "Minh";
        System.out.println("shallow first = " + shallow.get(0).name);
        System.out.println("source first after edit = " + source.get(0).name);

        // Sao chép sâu theo model Student/Address.
        var deepMutable = new ArrayList<Student>();
        for (var student : snapshot) {
            deepMutable.add(student.deepCopy());
        }
        List<Student> deepReadOnly = List.copyOf(deepMutable);

        // Chụp dữ liệu sang value object gồm các String bất biến.
        List<StudentSnapshot> immutableValues = snapshot.stream()
                .map(s -> new StudentSnapshot(s.id, s.name, s.address.city))
                .toList();

        snapshot.get(0).address.city = "Nha Trang";
        System.out.println("snapshot city now = "
                + snapshot.get(0).address.city);
        System.out.println("deep city = "
                + deepReadOnly.get(0).address.city);
        System.out.println("immutable city = "
                + immutableValues.get(0).city());
        System.out.println("same deep student = "
                + (snapshot.get(0) == deepReadOnly.get(0)));

        try {
            snapshot.set(0, new Student("04", "Hoa", new Address("Hue")));
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot set = blocked");
        }

        try {
            List.copyOf(Arrays.asList("A", null));
        } catch (NullPointerException ex) {
            System.out.println("copyOf null element = rejected");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac ListCopyOfReferencesDemo.java
java ListCopyOfReferencesDemo
~~~

**Kết quả chuẩn:**

~~~text
same list = false
same student = true
same address = true
source name = Binh
snapshot name = Binh
snapshot city = Da Nang
source size = 2
snapshot size = 1
view size = 2
source first = Chi
snapshot first = Binh
view first = Chi
shallow first = Minh
source first after edit = Chi
snapshot city now = Nha Trang
deep city = Da Nang
immutable city = Da Nang
same deep student = false
snapshot set = blocked
copyOf null element = rejected
~~~

### Giải thích các nhóm kết quả

1. **`same list = false`:** vì `source` trong ví dụ là `ArrayList` mutable, còn `snapshot` là kết quả unmodifiable riêng về cấu trúc. Không suy ra rằng mọi `List.copyOf(input)` đều phải trả instance mới với mọi loại input.
2. **`same student = true`:** bản sao giữ cùng `Student` ban đầu, không tạo phần tử mới.
3. **`same address = true`:** vì danh sách giữ cùng `Student`, nested object `Address` cũng vẫn là object được chia sẻ.
4. **Sửa `original`:** các giá trị `name` và `city` quan sát được qua `snapshot` cùng thay đổi.
5. **`source.set` và `source.add`:** `source` và view thấy cấu trúc mới, còn `snapshot` vẫn giữ một phần tử ban đầu là `original`.
6. **Sửa qua `snapshot.get(0)`:** tên mới `Minh` xuất hiện ở bản sao nông `shallow` vì chúng chia sẻ `original`, nhưng không làm thay đối tượng ở `source.get(0)` sau khi nguồn đã được `set` sang object mới.
7. **`deepReadOnly`:** sao chép cả `Student` và `Address`, nên việc đổi `Address` ở bản sao nông không đổi `deepReadOnly`.
8. **`immutableValues`:** lưu giá trị `String` vào các record `StudentSnapshot` thay vì để lộ `Student` hoặc `Address` mutable, nên thể hiện snapshot giá trị độc lập.
9. **`snapshot.set`:** `UnsupportedOperationException` chứng minh không thể thay đổi phần tử ở vị trí list qua API `snapshot`.
10. **`List.copyOf` với `null`:** ném `NullPointerException` theo hợp đồng API.

Đây là ví dụ **Java 17+**, vì `record` và `Stream.toList()` được hỗ trợ từ những phiên bản sau Java 10. Các thao tác `List.copyOf`, so sánh reference và sao chép object vẫn phù hợp với Java 10.

## 9. Cách tạo bản sao độc lập khi cần bảo vệ trạng thái

`List.copyOf(source)` phù hợp khi bạn muốn **chụp cấu trúc** nhưng chấp nhận việc phần tử được chia sẻ, đặc biệt nếu phần tử vốn đã immutable. Khi muốn một API không bị sửa dữ liệu từ bên ngoài, cần xác định **những object mutable nào phải được tách ra**.

### Cách A — Copy từng phần tử, bao gồm trạng thái mutable lồng bên trong

Giả sử lớp `Student` có `deepCopy()` như chương trình ở mục 8:

~~~java
var independent = new ArrayList<Student>();
for (var student : source) {
    independent.add(student.deepCopy());
}
List<Student> result = List.copyOf(independent);
~~~

Đây là đoạn minh họa trong một phương thức, không phải chương trình chạy độc lập.

Thứ tự các bước:
1. Duyệt collection nguồn.
2. Tạo một `Student` mới cho mỗi phần tử.
3. Trong `Student.deepCopy()`, tạo thêm `Address` mới hoặc các object mutable cần tách biệt khác.
4. Dùng `List.copyOf` để ngăn sửa **cấu trúc** danh sách kết quả.

**Kết quả:** `result` không chia sẻ `Student` và `Address` với nguồn trong mô hình này, nhưng những `Student` mới vẫn mutable. Người giữ `result` vẫn có thể viết `result.get(0).name = ...` nếu có quyền truy cập. **Bản sao sâu không đồng nghĩa bất biến sâu.**

### Cách B — Chụp dữ liệu sang value object thực sự bất biến

Trong JDK 17+, có thể định nghĩa:

~~~java
record StudentSnapshot(String id, String name, String city) {}
~~~

Sau đó:

~~~java
List<StudentSnapshot> safe = source.stream()
        .map(s -> new StudentSnapshot(s.id, s.name, s.address.city))
        .toList();
~~~

`safe` chỉ chứa các giá trị `String`, không giữ tham chiếu tới `Student` hay `Address` mutable. `Stream.toList()` trả danh sách unmodifiable, và mỗi `StudentSnapshot` trong mô hình này có các thành phần `String` immutable.

**Không suy rộng** rằng mọi `record` đều immutable sâu: một record có thành phần `Address` mutable hay `List<MutableStudent>` vẫn có thể để lộ trạng thái thay đổi được.

### Cách C — Giữ tham chiếu chung nếu phần tử thật sự immutable

Ví dụ:

~~~java
var source = new ArrayList<String>();
source.add("A");

var copy = List.copyOf(source);
source.set(0, "B");

System.out.println(source); // [B]
System.out.println(copy);   // [A]
~~~

Vì `String` là immutable, một tham chiếu `String` được chia sẻ không dẫn đến việc “sửa nội dung chuỗi” sau khi tạo. Thay `source[0]` bằng chuỗi khác là **đổi tham chiếu trong list nguồn**, nên không thay đổi `copy`.

Không cần deep-copy `String` bằng cách tạo thêm object `String` mới cho mục đích tách trạng thái; bản thân đối tượng chuỗi đã không cho thay đổi nội dung.

## 10. Điều kiện đặc biệt: `List.copyOf` không bảo đảm luôn tạo list instance mới

Với `source` là `ArrayList` mutable như các ví dụ chính, bạn có thể dựa vào việc kết quả không bị tác động bởi các lệnh `add`, `set`, `remove` trên nguồn sau đó. Nhưng với đầu vào đã là một danh sách unmodifiable thích hợp, **`List.copyOf` có thể không tạo thêm đối tượng danh sách mới**.

~~~java
List<String> original = List.of("A", "B");
List<String> copy = List.copyOf(original);

// Không dựa vào biểu thức original == copy để kiểm tra hợp đồng.
System.out.println(copy); // [A, B]
~~~

Không nên viết test yêu cầu `copy != original` trong mọi trường hợp. Java chỉ cam kết hành vi của một list unmodifiable chứa các phần tử phù hợp; identity của instance kết quả không phải mục tiêu API.

**Phân biệt hai cấp identity:**
- **Identity của chính list kết quả:** không được `List.copyOf` cam kết lúc nào cũng mới.
- **Identity của từng object phần tử:** không được `List.copyOf` sao chép; cùng một object phần tử có thể xuất hiện ở nhiều danh sách.

Các phép thử `source.get(0) == copy.get(0)` trong bài quan sát **object phần tử**, không dùng identity của list để kết luận phần tử có được nhân bản hay không.

## 11. Các lỗi phổ biến khi hiểu `List.copyOf`

| Nhận định hoặc code | Sai ở đâu? | Cách hiểu đúng |
| --- | --- | --- |
| “`List.copyOf` deep-copy tất cả phần tử.” | API không nhân bản các object phần tử. | Kết quả giữ tham chiếu phần tử; dùng copy theo model nếu cần độc lập. |
| “Không `add` được thì `Student` cũng bất biến.” | Lệnh sửa object không phải thao tác sửa cấu trúc list. | Thiết kế `Student` immutable, hoặc sao chép phòng vệ. |
| “Sửa `source.get(0).name` không ảnh hưởng `copy`.” | Hai danh sách có thể dùng chung `Student` tại vị trí đó. | Thay đổi object được chia sẻ có thể quan sát ở cả hai. |
| “`source.set(0, replacement)` sẽ đổi `copy.get(0)`.” | Nó chỉ thay tham chiếu trong danh sách nguồn. | Snapshot vẫn trỏ tới object cũ. |
| “`Collections.unmodifiableList(source)` là bản sao.” | Đây là view bọc trực tiếp nguồn. | Source thay cấu trúc thì view phản ánh thay đổi. |
| “`copy == source` luôn là false.” | `List.copyOf` có thể tái sử dụng list unmodifiable đầu vào. | Không dựa vào identity list để xác định copy đã tạo instance mới. |
| “`final` field giữ một `Address` nghĩa là địa chỉ bất biến.” | `final` chặn gán lại tham chiếu field, không chặn sửa trạng thái `Address`. | Cần immutable `Address` hoặc defensive copy. |
| “`List.copyOf` xử lý `null` như `new ArrayList<>(source)`.” | `List.copyOf` không nhận phần tử `null`. | Kiểm tra/loại `null` theo hợp đồng trước khi gọi. |
| “Kết quả unmodifiable chắc chắn thread-safe.” | Thread safety độc lập với việc cho phép sửa list và object phần tử. | Bảo vệ dữ liệu mutable được chia sẻ và có chiến lược đồng bộ phù hợp. |

**Ghi chú về `Set.copyOf`/`Map.copyOf`:** Hai API Java 10 này cũng không deep-copy phần tử, khóa hay giá trị. Đặc biệt, với khóa `Map` hoặc phần tử `Set`, không nên sửa các field ảnh hưởng tới `equals()`/`hashCode()` khi đã đưa chúng vào collection dạng hash vì có thể phá vỡ tính đúng đắn của việc tra cứu.

## 12. Chọn cách triển khai khi công bố dữ liệu từ API

Giả sử một service đang quản lý `List<Student>` nội bộ. Mỗi cách trả dữ liệu ngụ ý một mức chia sẻ khác nhau:

**Trả nguồn trực tiếp:**

~~~java
return internalStudents;
~~~

Người gọi có thể sửa cấu trúc `internalStudents` nếu tham chiếu này có kiểu collection mutable; cũng có thể sửa từng phần tử nếu chúng mutable.

**Trả unmodifiable view của nguồn:**

~~~java
return Collections.unmodifiableList(internalStudents);
~~~

Chặn thao tác sửa cấu trúc *qua view*, nhưng người gọi có thể quan sát thay đổi cấu trúc của `internalStudents` về sau; các phần tử mutable vẫn được chia sẻ.

**Trả `List.copyOf` của nguồn:**

~~~java
return List.copyOf(internalStudents);
~~~

Tạo snapshot cấu trúc các tham chiếu phần tử ở thời điểm gọi, không cho sửa cấu trúc qua kết quả; các object `Student` mutable vẫn có thể được chia sẻ với trạng thái nội bộ.

**Trả dữ liệu tách biệt và không để lộ mutable object:**

~~~java
return internalStudents.stream()
        .map(s -> new StudentSnapshot(s.id, s.name, s.address.city))
        .toList();
~~~

Đây là ví dụ áp dụng kiểu `StudentSnapshot` ở mục 9 trong JDK 17+. Kết quả chứa những giá trị `String` được chụp lại, nên sửa `Student` hoặc `Address` nội bộ sau đó không đổi các giá trị đã công bố.

Lựa chọn tối ưu phụ thuộc vào **hợp đồng ownership**, nhu cầu cập nhật, kích thước object graph, chi phí sao chép, tính nhất quán dữ liệu và yêu cầu thread safety. Không nên deep-copy vô điều kiện dữ liệu lớn khi phần tử đã thực sự immutable; ngược lại, cũng không nên công bố tham chiếu mutable nếu người gọi không được phép thay đổi dữ liệu nội bộ.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Sau `var copy = List.copyOf(source);`, nếu `source.get(0)` là đối tượng `Student` mutable thì `copy.get(0) == source.get(0)` có thể là `true` không?

**Đáp án:** Có, và với danh sách nguồn chứa phần tử ấy mà chưa thay tham chiếu ở vị trí 0, hai lệnh thường lấy chính cùng một object. `List.copyOf` không deep-copy phần tử.

**Câu 2.** Vì sao `copy.get(0).name = "Binh"` có thể chạy được, còn `copy.set(0, new Student(...))` lại ném ngoại lệ?

**Đáp án:** Lệnh đầu sửa trạng thái object mutable đã lấy ra, không sửa cấu trúc danh sách. Lệnh sau cố thay phần tử tại một vị trí trong list unmodifiable.

**Câu 3.** Sau `source.set(0, anotherStudent)`, `copy.get(0)` có tự trỏ tới `anotherStudent` không?

**Đáp án:** Không, nếu `copy` là snapshot tạo từ `ArrayList` mutable trước phép `set`. Nó vẫn giữ tham chiếu tới object đã chụp tại thời điểm sao chép.

**Câu 4.** Khác nhau giữa `List.copyOf(source)` và `Collections.unmodifiableList(source)` khi `source.add(x)` là gì?

**Đáp án:** Với nguồn mutable, `List.copyOf` giữ cấu trúc tại thời điểm gọi; view trực tiếp `Collections.unmodifiableList(source)` quan sát thay đổi cấu trúc nguồn.

**Câu 5.** `List.copyOf(source)` có tạo thêm `Address` mới trong mỗi `Student` không?

**Đáp án:** Không. Nó chỉ nhận tham chiếu `Student`; nếu `Student` giữ một `Address` mutable thì object đó có thể tiếp tục được dùng chung.

**Câu 6.** Deep copy có tự động biến các phần tử thành immutable không?

**Đáp án:** Không. Nó có thể tạo những object mutable mới độc lập với nguồn. Muốn bất biến sâu, cần thiết kế value object và các thành phần được công bố là immutable hoặc thực hiện defensive copy phù hợp.

**Câu 7.** Với `List<String>`, chia sẻ tham chiếu phần tử thường an toàn hơn vì sao?

**Đáp án:** `String` là bất biến; không có thao tác sửa nội dung của object chuỗi đã được chia sẻ. Việc thay một phần tử trong nguồn là thay tham chiếu trong list nguồn, không đổi object cũ trong snapshot.

**Câu 8.** Có thể dựa vào `List.copyOf(source) != source` với mọi nguồn để kiểm tra một bản sao mới đã được tạo không?

**Đáp án:** Không. API có thể tái sử dụng một list đầu vào đã unmodifiable phù hợp. Cần kiểm tra hợp đồng và nội dung, không dùng identity list làm tiêu chí chung.

## 14. Ghi nhớ cuối bài

1. **`List.copyOf` tạo list unmodifiable chứa tham chiếu phần tử, không deep-copy object phần tử.**
2. **Sửa object phần tử được chia sẻ** có thể phản ánh ở cả nguồn và snapshot.
3. **Thêm/xóa/thay thế vị trí của danh sách nguồn mutable** không tự thay đổi snapshot đã tạo.
4. **`Collections.unmodifiableList(source)` là view**, khác với snapshot của `List.copyOf(source)`; cả hai vẫn có thể chia sẻ mutable elements.
5. Muốn tách biệt state, phải **copy từng phần tử và nested mutable object**, hoặc công bố **immutable value objects** được chụp từ nguồn.
6. Đừng đồng nhất *unmodifiable list*, *deep copy*, *deep immutability* và *thread safety*. Đây là các thuộc tính riêng cần bảo đảm theo hợp đồng cụ thể.

**Tài liệu tham khảo còn áp dụng:**
- [Java SE 17 — `List.copyOf(Collection)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
- [Java SE 17 — `Collections.unmodifiableList(List)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).
- [Java SE 17 — `ArrayList(Collection)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection)).
- [Java SE 17 — `Stream.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()).
