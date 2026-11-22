# Hàm khởi tạo sao chép và phương thức tạo bản sao có tên trong Java

## 1. Bài toán: một đối tượng mới có độc lập với đối tượng gốc không?

Trong Java, biến có kiểu tham chiếu chứa **tham chiếu đến đối tượng**, không chứa toàn bộ đối tượng. Vì vậy, gán `Profile b = a;` chỉ tạo thêm một tên cùng trỏ tới đối tượng `a`. Thay đổi trạng thái qua `b` cũng chính là thay đổi trạng thái thấy được qua `a`.

Khi cần hai đối tượng có dữ liệu ban đầu tương đương nhưng có thể phát triển độc lập, ta **tạo một đối tượng mới** và chủ động xác định cách sao chép từng thành phần. Hai cách phổ biến trong Java là:

- **Copy constructor (hàm khởi tạo sao chép)**: `new Profile(existing)`. Constructor nhận một đối tượng cùng loại và khởi tạo trạng thái của đối tượng mới từ nó.
- **Named copy method / named copy factory (phương thức tạo bản sao có tên)**: `Profile.copyOf(existing)`, `Profile.from(existing)` hoặc `existing.copy()`. Tên phương thức biểu đạt ý định, còn phần triển khai quyết định có tạo đối tượng mới và sao chép sâu đến đâu.

Java **không tự tạo copy constructor** cho class. Khác một số ngôn ngữ, truyền đối tượng vào constructor cùng loại không tự động có nghĩa “copy”: tác giả class phải định nghĩa hành vi đó.

Ví dụ ngắn về khác biệt giữa **gán tham chiếu** và **tạo bản sao**:

```java
Profile alias = original;                   // Cùng một đối tượng.
Profile copy = new Profile(original);       // Đối tượng mới theo hợp đồng copy.
boolean sameObject = alias == original;     // true
boolean copiedObject = copy == original;    // false nếu constructor tạo object mới.
```

Đoạn trên dùng class `Profile` được định nghĩa trong chương trình đầy đủ ở phần 4.

## 2. Copy constructor hoạt động như thế nào?

Mẫu cơ bản:

```java
public final class Point {
    private final int x;
    private final int y;

    public Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public Point(Point source) {
        this(source.x, source.y);
    }
}
```

- `Point(Point source)` là **constructor**, không có kiểu trả về.
- `new Point(source)` luôn cấp phát một `Point` mới nếu khởi tạo thành công.
- Dòng `this(source.x, source.y)` dùng lại constructor chính, giảm nguy cơ bỏ sót trường hoặc áp dụng quy tắc kiểm tra khác nhau.
- `int` được sao chép theo giá trị. Với trường là tham chiếu, điều cần quyết định là **sao chép tham chiếu, sao chép container, hay sao chép luôn đối tượng bên trong**.

Một copy constructor tốt nên công khai hợp đồng: sau khi sao chép, những thay đổi nào ở bản gốc hoặc bản sao có thể ảnh hưởng lẫn nhau? Hợp đồng ấy quan trọng hơn việc “có constructor nhận cùng kiểu”.

## 3. Sao chép nông, sâu và chia sẻ có chủ ý

Giả sử `Person` chứa một `Address` có thể đổi `city` và một `List<String>` có thể thêm phần tử.

| Cách làm | Thành phần được tạo mới | Hệ quả |
| --- | --- | --- |
| `this.address = source.address;` | Không tạo `Address` mới | Hai `Person` cùng thấy thay đổi địa chỉ: **shallow copy** đối với trường này |
| `this.address = new Address(source.address);` | Tạo `Address` mới | Thay đổi `city` ở một bên không tác động bên kia |
| `this.tags = source.tags;` | Không tạo list mới | Thêm/xóa phần tử ở một bên ảnh hưởng list bên kia |
| `this.tags = new ArrayList<>(source.tags);` | Tạo list mới, giữ tham chiếu đến phần tử | Hai list độc lập về thêm/xóa; **các phần tử** không tự được deep-copy |

**Shallow copy** tạo đối tượng bao ngoài mới nhưng vẫn chia sẻ một hay nhiều tham chiếu bên trong. **Deep copy** sao chép tiếp những đối tượng mutable mà hợp đồng yêu cầu phải độc lập. “Deep” có phạm vi theo đồ thị đối tượng: không có quy tắc rằng mọi reference phải luôn tạo mới. `String`, enum và kiểu giá trị bất biến thường an toàn khi dùng chung.

Ví dụ, `new ArrayList<>(source.tags)` đủ để tách hai danh sách `String` vì các chuỗi là bất biến. Nếu đổi sang `List<MutableTask>`, hai list vẫn có thể chứa **cùng các `MutableTask`**. Khi đó cần tạo từng `MutableTask` mới nếu đòi hỏi thay đổi task độc lập.

**Tính độc lập cần xét cả hai chiều**: thay đổi bản gốc không làm hỏng bản sao, và thay đổi bản sao cũng không làm hỏng bản gốc. Ngoài ra, constructor nhận dữ liệu từ bên ngoài có thể cần **defensive copy** ngay lúc đầu để tránh caller giữ và sửa tham chiếu vào nội bộ.

## 4. Ví dụ hoàn chỉnh Java 17+: ba cách sao chép, một hợp đồng độc lập

Lưu thành tệp **`CopyPatternsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class CopyPatternsDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = Objects.requireNonNull(city, "city");
        }

        Address(Address source) {
            this(Objects.requireNonNull(source, "source").city);
        }

        String city() {
            return city;
        }

        void setCity(String city) {
            this.city = Objects.requireNonNull(city, "city");
        }
    }

    static final class Profile {
        private final String name;
        private final Address address;       // Reference final, Address vẫn mutable.
        private final List<String> tags;     // Reference final, List vẫn mutable.

        Profile(String name, Address address, List<String> tags) {
            this.name = Objects.requireNonNull(name, "name");
            this.address = new Address(
                    Objects.requireNonNull(address, "address"));
            this.tags = new ArrayList<>(
                    Objects.requireNonNull(tags, "tags"));
        }

        // (1) Copy constructor: tái sử dụng constructor chính.
        Profile(Profile source) {
            this(Objects.requireNonNull(source, "source").name,
                    source.address,
                    source.tags);
        }

        // (2) Named static factory: diễn đạt rõ ý định ở phía caller.
        static Profile copyOf(Profile source) {
            return new Profile(source);
        }

        // (3) Named instance method: thuận tiện khi đã có đối tượng.
        Profile copy() {
            return new Profile(this);
        }

        void moveTo(String city) {
            address.setCity(city);
        }

        void addTag(String tag) {
            tags.add(Objects.requireNonNull(tag, "tag"));
        }

        String describe() {
            return name + " / " + address.city() + " / " + tags;
        }
    }

    public static void main(String[] args) {
        Address inputAddress = new Address("Ha Noi");
        List<String> inputTags = new ArrayList<>(List.of("java"));

        Profile original = new Profile("An", inputAddress, inputTags);
        Profile byConstructor = new Profile(original);
        Profile byFactory = Profile.copyOf(original);
        Profile byMethod = original.copy();

        // Chỉ thay đổi bản gốc và các đầu vào vẫn do caller giữ.
        original.moveTo("Da Nang");
        original.addTag("oop");
        inputAddress.setCity("Hue");
        inputTags.add("external");

        System.out.println("original: " + original.describe());
        System.out.println("constructor: " + byConstructor.describe());
        System.out.println("factory: " + byFactory.describe());
        System.out.println("method: " + byMethod.describe());
        System.out.println("distinct objects: "
                + (original != byConstructor
                && original != byFactory
                && original != byMethod));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac CopyPatternsDemo.java
java CopyPatternsDemo
```

Kết quả chính xác:

```text
original: An / Da Nang / [java, oop]
constructor: An / Ha Noi / [java]
factory: An / Ha Noi / [java]
method: An / Ha Noi / [java]
distinct objects: true
```

Giải thích theo luồng:

1. Constructor chính **chép phòng vệ** `Address` và list từ đầu vào. Vì thế sửa `inputAddress` hay `inputTags` sau đó không đổi `original`.
2. Copy constructor gọi constructor chính; địa chỉ được sao chép bằng `new Address(...)`, còn list tạo bằng `new ArrayList<>(...)`. Do phần tử trong list là `String` bất biến, mức sao chép này đủ cho ví dụ.
3. `copyOf` và `copy()` **ủy quyền cùng một điểm thực thi**, tránh ba bản logic copy lệch nhau.
4. Khi `original` chuyển thành “Da Nang” và được thêm tag “oop”, ba bản sao vẫn giữ ảnh chụp dữ liệu trước sửa đổi.
5. `!=` chỉ chứng minh các đối tượng ngoài khác tham chiếu. Tính độc lập của **trường bên trong** được thể hiện bằng kết quả địa chỉ và list.

Dấu `final` ở `address` và `tags` chỉ ngăn **gán lại reference của trường**; bản thân `Address` và `List` vẫn mutable. Vì vậy không thể dựa vào `final` để bỏ bước sao chép phòng vệ.

## 5. Phương thức tạo bản sao có tên: khi nào dùng và đặt tên gì?

Hai hình thức thường gặp:

```java
Profile a = new Profile(original);  // Constructor nhận Profile.
Profile b = Profile.copyOf(original); // Static factory có tên.
Profile c = original.copy();         // Instance method có tên.
```

| API | Ưu điểm chính | Điểm phải nói rõ trong tài liệu |
| --- | --- | --- |
| `new T(source)` | Dễ tìm, gần với cú pháp tạo object, bắt buộc tạo đối tượng `T` mới nếu thành công | Có sao chép sâu hay chỉ chép trường? Điều kiện input hợp lệ? |
| `T.copyOf(source)` | Ý định dễ đọc, có thể giấu chi tiết khởi tạo, tập trung kiểm tra/chuẩn hóa | **Tên không bảo đảm** luôn trả object mới: vài API bất biến có thể tái sử dụng instance |
| `source.copy()` | Tự nhiên khi thao tác trên instance; có thể hỗ trợ hành vi riêng theo loại đối tượng | Trả về cùng kiểu hay kiểu cơ sở? Mức độ độc lập? |
| `T.from(source)` | Hữu ích khi chuyển từ kiểu nguồn khác hoặc biểu diễn khác | `from` thường thiên về **chuyển đổi**, không mặc nhiên có nghĩa deep copy |
| `withX(newValue)` | Diễn đạt bản sao có chỉnh một thuộc tính, hợp với immutable value object | Các trường không đổi có được chia sẻ hay không? |

Trong ví dụ, `Profile.copyOf` **luôn** gọi `new Profile(source)`, nên trả object mới. Đừng suy rộng quy tắc này cho mọi thư viện: chẳng hạn factory cho kiểu bất biến có thể trả lại chính input theo hợp đồng riêng. Nếu caller bắt buộc cần **định danh đối tượng mới** (`result != source`), cần ghi rõ trong API và kiểm chứng bằng test.

Một biến thể hữu ích khi muốn “sao chép và đổi một trường” là phương thức `withName`:

```java
// Phương thức thêm vào class Profile ở phần 4 (không phải chương trình độc lập).
Profile withName(String newName) {
    return new Profile(newName, address, tags);
}
```

Vì constructor chính đã sao chép `Address` và list, `withName` vẫn duy trì hợp đồng độc lập trong ví dụ. Với class bất biến thực sự, các giá trị bất biến thường có thể chia sẻ an toàn để giảm cấp phát.

## 6. Thiết kế hợp đồng sao chép chính xác

Trước khi viết một copy constructor hay copy method, hãy xác định các điểm sau:

**(a) Những trường nào là giá trị, những trường nào có thể thay đổi?** Primitive, `String`, enum và các value object bất biến có thể sao chép giá trị/tham chiếu. Các object mutable phải được xem xét theo quyền sở hữu dữ liệu và mức độc lập mong muốn.

**(b) Có giữ được bất biến của class không?** Tái sử dụng constructor hoặc một hàm kiểm tra nội bộ duy nhất để các bản sao thỏa cùng điều kiện: trường bắt buộc không null, collection có phần tử hợp lệ, dữ liệu ở trạng thái nhất quán. Copy constructor không nên bỏ qua các quy tắc mà constructor bình thường tuân thủ.

**(c) Chia sẻ đối tượng con có chủ ý hay vô tình?** Nếu hai bản sao **được phép** cùng nhìn một cache bất biến, một service, hay nguồn dữ liệu dùng chung, ghi rõ đó là quan hệ chia sẻ. Không cố copy file handle, thread, lock, socket, connection hoặc tài nguyên ngoài chỉ để “deep copy mọi thứ”. Với tài nguyên, cần hợp đồng vòng đời và ownership riêng.

**(d) Có trạng thái dẫn xuất hoặc bí mật nội bộ không?** Trường cache suy ra từ dữ liệu chính thường nên tính lại hoặc làm rỗng có chủ ý; identity, version, thời điểm tạo, id nghiệp vụ và trạng thái đăng ký event cần quyết định rõ là **giữ** hay **cấp mới**. Sao chép toàn bộ field máy móc có thể phá bất biến.

**(e) Có null hoặc phần tử mutable lồng nhau không?** `Objects.requireNonNull(source, "source")` giúp lỗi đầu vào rõ ràng. Với trường nullable, tự định nghĩa trường hợp null thay vì gọi constructor copy trên null. Với `List<MutableItem>`, phải copy từng item nếu mỗi item cần độc lập. Đồ thị có **tham chiếu vòng** hoặc nhiều nhánh cùng trỏ một object cần cơ chế theo dõi identity khi deep copy để tránh đệ quy vô hạn và không làm mất quan hệ chia sẻ nội bộ.

**(f) Có nhiều luồng sửa dữ liệu đồng thời không?** Copy nhiều mutable field theo từng bước **không tự tạo snapshot nguyên tử**. Nếu thread khác có thể sửa nguồn giữa chừng, dùng lock, immutable snapshot hoặc chiến lược đồng bộ phù hợp. Copy constructor không tự giải quyết thread safety.

### Gợi ý JavaDoc cho hợp đồng

```java
/**
 * Creates a new Profile with the same name, a separate Address,
 * and a separate mutable list of immutable String tags.
 * Later mutations of either Profile do not affect the other.
 *
 * @throws NullPointerException if source is null
 */
Profile(Profile source) {
    this(Objects.requireNonNull(source, "source").name,
            source.address, source.tags);
}
```

Đoạn JavaDoc này minh họa cách mô tả **phạm vi độc lập** cụ thể; constructor đầy đủ đã có ở phần 4.

## 7. Về kế thừa, record và clone()

**Class có kế thừa:** Copy constructor trong lớp cha chỉ biết phần state của lớp cha; nếu gọi `new Base(subclassInstance)`, đối tượng nhận được là `Base`, phần riêng của subclass không được giữ. Với phân cấp phức tạp, hãy cân nhắc copy method có contract đa hình, protected copy hook hoặc một thiết kế bất biến/không kế thừa. Tránh gọi phương thức có thể override từ constructor vì trạng thái subclass có thể chưa được khởi tạo hoàn chỉnh.

**Record Java:** Record thường là lựa chọn tốt cho dữ liệu dạng giá trị ít thay đổi; record không tự deep-copy reference mutable. Một record chứa `List` vẫn cần snapshot/defensive copy nếu muốn trạng thái ổn định. Non-canonical constructor trong record phải ủy quyền cho canonical constructor:

```java
record Coordinate(int x, int y) {
    Coordinate(Coordinate source) {
        this(source.x(), source.y());
    }
}
```

Với một `Coordinate` bất biến, việc tạo bản sao mới thường **không cần thiết** về mặt hành vi; chia sẻ cùng instance là an toàn nếu API không yêu cầu identity khác nhau.

**`Object.clone()`:** Cơ chế `Cloneable`/`clone()` mang các quy ước và góc cạnh riêng, và phép sao chép mặc định của `Object.clone()` là shallow. Copy constructor hoặc named factory thường dễ diễn đạt kiểm tra đầu vào, bất biến và ownership hơn. Không cần dùng `clone()` chỉ vì bài toán có chữ “copy”.

## 8. Lỗi phổ biến và cách tránh

1. **Nhầm gán tham chiếu với sao chép:** `b = a` không tạo object mới. Dùng constructor hoặc factory được định nghĩa rõ hợp đồng.
2. **Sao chép bao ngoài nhưng giữ chung object mutable:** `this.address = source.address` làm hai bản ghi liên đới. Sao chép `Address` khi cần tách độc lập.
3. **Tưởng constructor `new ArrayList<>(list)` sao chép sâu mọi phần tử:** thao tác này chỉ tạo list mới; từng element mutable có thể vẫn chung tham chiếu.
4. **Tạo hai logic copy riêng:** constructor một kiểu, `copyOf` một kiểu khiến mỗi đường cho kết quả khác nhau. Chọn một chỗ cài đặt và ủy quyền từ API còn lại.
5. **Quên cập nhật copy khi class thêm trường:** bản sao mất thông tin hoặc sai invariant. Rà soát toàn bộ state và test khi thêm trường mới.
6. **Sao chép nguồn chưa nhất quán trong môi trường đa luồng:** snapshot có thể chứa dữ liệu từ nhiều thời điểm. Tổ chức đồng bộ trước khi chép.
7. **Dùng `==` để kết luận hai bản sao có cùng giá trị:** `==` so sánh identity với object; kiểm tra giá trị theo contract (accessor, `equals()` phù hợp) và kiểm tra độc lập bằng thay đổi state.
8. **Đặt tên `copyOf` nhưng không mô tả hành vi:** người đọc có thể kỳ vọng object mới hoặc deep copy. Viết rõ có tái sử dụng instance, chép nông/sâu, và xử lý null thế nào.

## 9. Cách kiểm tra bản sao

Một bộ kiểm tra có ý nghĩa cần chứng minh cả **giá trị ban đầu** lẫn **độc lập sau khi sửa**, thay vì chỉ kiểm tra object khác reference:

- Tạo nguồn có ít nhất một trường mutable lồng nhau và một collection; copy bằng từng API được công khai.
- So sánh dữ liệu quan sát được ngay sau copy.
- Thay đổi trường mutable ở nguồn; kiểm tra bản sao vẫn giữ giá trị cũ.
- Thay đổi trường mutable ở bản sao; kiểm tra nguồn không thay đổi.
- Thử null, dữ liệu không hợp lệ và phần tử mutable trong collection theo hợp đồng đã công bố.
- Với đối tượng giữ quan hệ tham chiếu vòng hoặc alias giữa các nhánh, kiểm tra cấu trúc quan hệ sau deep copy, nếu hợp đồng yêu cầu.

**Quy tắc chọn cách dùng:** `new T(existing)` ngắn gọn khi cần tạo bản sao kiểu `T` một cách trực tiếp. `T.copyOf(existing)` dễ đọc khi muốn API có tên, kiểm soát cách khởi tạo và thống nhất chính sách sao chép. `existing.copy()` thuận tiện cho thao tác theo instance. Dù chọn cách nào, điều quyết định là **hợp đồng về dữ liệu được sao chép và dữ liệu được chia sẻ**, được bảo đảm bằng triển khai và kiểm thử.
