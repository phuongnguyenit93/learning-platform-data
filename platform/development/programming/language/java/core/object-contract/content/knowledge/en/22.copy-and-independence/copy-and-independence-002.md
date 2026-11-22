# Trường trỏ tới đối tượng bất biến có thể chia sẻ an toàn

## 1. Ý nghĩa trong sao chép đối tượng

Khi tạo bản sao của một đối tượng Java, “độc lập” thường có nghĩa là **thay đổi trạng thái của bản gốc không làm thay đổi trạng thái quan sát được của bản sao, và ngược lại**. Điều này không bắt buộc mọi trường tham chiếu phải trỏ đến một đối tượng mới.

Nếu trường trỏ tới một đối tượng **bất biến (immutable)**, bản gốc và bản sao có thể giữ **cùng tham chiếu**: không bên nào có thể sửa trạng thái của đối tượng được chia sẻ. Sao chép tham chiếu trong trường hợp này vừa đúng về ngữ nghĩa vừa tránh tạo đối tượng không cần thiết.

Ví dụ: hai hồ sơ cùng trỏ đến một `String` biểu diễn tên hoặc cùng trỏ đến một `LocalDate` biểu diễn ngày tham gia. Nếu sửa riêng các phần dữ liệu có thể thay đổi của một hồ sơ, hồ sơ kia vẫn độc lập.

Cần phân biệt:

- **Sao chép tham chiếu:** `copy.name = original.name`; cả hai trường cùng trỏ đến một đối tượng.
- **Sao chép trạng thái:** tạo đối tượng mới chứa dữ liệu tương đương; thường cần khi dữ liệu có thể thay đổi.
- **Độc lập về trạng thái:** hai đối tượng chứa không vô tình chia sẻ trạng thái *có thể bị sửa*. Hai bản sao không nhất thiết phải khác nhau về định danh ở mọi đối tượng con.

## 2. Khi nào chia sẻ tham chiếu là an toàn?

Một đối tượng phù hợp để chia sẻ phải có trạng thái quan sát được không thay đổi sau khi được tạo, kể cả qua các đối tượng con mà nó tham chiếu. Không được có đường truy cập công khai nào làm thay đổi trạng thái đó.

Trong Java, ví dụ điển hình gồm:

- `String`: nội dung chuỗi không đổi; nối chuỗi tạo kết quả mới.
- `LocalDate`, `LocalDateTime`, `Instant`: các phương thức như `plusDays` trả về giá trị mới thay vì sửa đối tượng hiện có.
- `BigInteger` và `BigDecimal`: phép toán trả về đối tượng kết quả mới.
- `UUID`: giá trị định danh không đổi sau khi tạo.

**Quy tắc:** nếu một trường có kiểu và *giá trị thực tế* thực sự bất biến, copy constructor, factory sao chép hoặc phương thức `copy` có thể gán lại nguyên tham chiếu đó.

~~~java
this.name = source.name;                 // String bất biến: chia sẻ an toàn
this.joinedDate = source.joinedDate;     // LocalDate bất biến: chia sẻ an toàn
~~~

Hai dòng trên là **đoạn minh họa bên trong copy constructor**, không phải chương trình Java độc lập.

Sơ đồ tham chiếu:

~~~text
bản gốc.name ---------+
                      +----> String "An" (bất biến)
bản sao.name ---------+

bản gốc.skills ------------> List A (có thể thay đổi)
bản sao.skills ------------> List B (có thể thay đổi)
~~~

Trong sơ đồ, chia sẻ đối tượng `String` an toàn; hai danh sách `List` được tách riêng để thay đổi danh sách A không tác động danh sách B.

## 3. Ví dụ Java 17: chia sẻ immutable, sao chép mutable

Ví dụ sau dùng copy constructor. Hai trường bất biến (`String` và `LocalDate`) được dùng chung. Danh sách kỹ năng có thể thay đổi nên mỗi `Profile` sở hữu một `ArrayList` riêng. Constructor cũng tạo bản sao phòng vệ của danh sách đầu vào để người gọi không giữ quyền sửa ngầm trạng thái nội bộ.

Tạo tệp `SafeImmutableSharingDemo.java`:

~~~java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SafeImmutableSharingDemo {
    static final class Profile {
        private final String name;
        private final LocalDate joinedDate;
        private final List<String> skills;

        Profile(String name, LocalDate joinedDate, List<String> skills) {
            this.name = Objects.requireNonNull(name);
            this.joinedDate = Objects.requireNonNull(joinedDate);
            this.skills = new ArrayList<>(Objects.requireNonNull(skills));
        }

        Profile(Profile source) {
            Objects.requireNonNull(source);
            this.name = source.name;             // Chia sẻ String bất biến
            this.joinedDate = source.joinedDate; // Chia sẻ LocalDate bất biến
            this.skills = new ArrayList<>(source.skills); // Tách List mutable
        }

        void addSkill(String skill) {
            skills.add(Objects.requireNonNull(skill));
        }

        List<String> getSkills() {
            return List.copyOf(skills); // Trả snapshot không sửa được
        }
    }

    public static void main(String[] args) {
        Profile original = new Profile(
                "An",
                LocalDate.of(2026, 10, 23),
                List.of("Java", "SQL")
        );
        Profile copy = new Profile(original);

        System.out.println("Cùng name: " + (original.name == copy.name));
        System.out.println("Cùng joinedDate: "
                + (original.joinedDate == copy.joinedDate));
        System.out.println("skills độc lập: "
                + (original.skills != copy.skills));

        original.addSkill("Spring");

        System.out.println("Original skills: " + original.getSkills());
        System.out.println("Copy skills: " + copy.getSkills());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac SafeImmutableSharingDemo.java
java SafeImmutableSharingDemo
~~~

Kết quả chuẩn:

~~~text
Cùng name: true
Cùng joinedDate: true
skills độc lập: true
Original skills: [Java, SQL, Spring]
Copy skills: [Java, SQL]
~~~

**Giải thích kết quả:**

1. `original.name == copy.name` là `true` vì copy constructor gán cùng tham chiếu `String`. Bất biến giúp việc dùng chung không gây rò rỉ thay đổi.
2. `original.joinedDate == copy.joinedDate` cũng là `true` vì cả hai cùng giữ tham chiếu `LocalDate`; gọi `plusDays` trên ngày này sẽ nhận một đối tượng ngày khác.
3. `original.skills != copy.skills` là `true` vì `new ArrayList<>(source.skills)` tạo **danh sách mới**.
4. Thêm `"Spring"` vào danh sách của bản gốc không làm đổi bản sao.
5. `getSkills()` trả về snapshot không cho sửa trực tiếp danh sách nội bộ. Vì các phần tử ở đây là `String` bất biến, không có trạng thái mutable bị chia sẻ qua các phần tử.

**Điểm quan trọng:** `private final List<String> skills` chỉ ngăn gán lại trường `skills` sau khi khởi tạo; bản thân `ArrayList` vẫn thay đổi được qua `addSkill`. Chính việc tạo danh sách riêng mới bảo đảm hai `Profile` không cùng sửa một danh sách.

## 4. Phản ví dụ: chia sẻ nhầm trạng thái mutable

Nếu copy constructor viết:

~~~java
this.skills = source.skills; // SAI nếu List này có thể thay đổi
~~~

thì hai `Profile` cùng trỏ đến **một danh sách**. Thêm/xóa phần tử qua một bản sẽ xuất hiện ở bản kia. Đây là *shallow copy* gây lỗi aliasing khi yêu cầu là hai hồ sơ độc lập.

Cách sửa phụ thuộc hợp đồng dữ liệu:

- Danh sách được phép thay đổi trong từng `Profile`: dùng `new ArrayList<>(source.skills)` như ví dụ chính.
- Danh sách phải bất biến từ lúc khởi tạo và các phần tử cũng bất biến: có thể dùng `List.copyOf(source.skills)` để lấy snapshot không thể sửa rồi chia sẻ snapshot đó giữa các bản sao.
- Danh sách chứa đối tượng mutable: sao chép mỗi phần tử mutable theo cách phù hợp; chỉ tạo `ArrayList` mới vẫn để hai danh sách trỏ đến **cùng các phần tử**.

Ví dụ về điểm cuối cùng: với `List<Address>` và `Address` có setter, biểu thức `new ArrayList<>(originalAddresses)` tạo danh sách mới nhưng *không* tạo `Address` mới. Nếu cần độc lập cả thông tin địa chỉ, hãy copy từng `Address`. Đây là mô tả cơ chế, không phải đoạn chương trình độc lập.

## 5. Không nhầm “không sửa được qua biến này” với “bất biến”

| Trường/giá trị | Có thể dùng chung khi copy? | Lý do/cách xử lý |
| --- | --- | --- |
| `String`, `LocalDate`, `Instant` | Có | Đối tượng bất biến. |
| `BigDecimal`, `BigInteger` | Có | Phép toán tạo giá trị mới. |
| `int[]`, `byte[]` | Không, nếu cần bản sao độc lập | Mảng mutable; dùng `clone()` hoặc `Arrays.copyOf(...)`. |
| `ArrayList<String>` mutable | Không | Tạo danh sách mới; phần tử `String` có thể dùng chung. |
| `List.copyOf(values)` với các phần tử immutable | Có, nếu không có đường sửa trạng thái ẩn | Danh sách snapshot không sửa được; giá trị lồng bên trong cũng bất biến. |
| `Collections.unmodifiableList(backing)` | Chưa chắc | Đây là view chỉ đọc; người giữ `backing` vẫn sửa được dữ liệu và view phản ánh thay đổi đó. |
| `List<MutableAddress>` | Không, nếu cần độc lập cả phần tử | Tạo danh sách và bản sao các phần tử mutable. |
| `Date`, `StringBuilder` | Không | Đây là các lớp mutable; cân nhắc copy hoặc đổi sang kiểu bất biến. |

Một số bẫy thường gặp:

### 5.1. `final` không biến đối tượng thành bất biến

~~~java
final int[] scores = {10, 20};
scores[0] = 99; // Hợp lệ: chỉ nội dung mảng thay đổi
~~~

`final` chỉ ngăn `scores` trỏ sang mảng khác. Ngay cả khi lớp chứa cũng khai báo `final`, mảng vẫn mutable.

### 5.2. `record` chỉ bảo đảm trường thành phần không gán lại được

~~~java
record Report(int[] totals) {}

int[] data = {1, 2};
Report report = new Report(data);
data[0] = 99; // report.totals()[0] bây giờ bằng 99
~~~

`record` tự sinh constructor/accessor nhưng không tự sao chép sâu mảng hoặc collection. Muốn một record bất biến về trạng thái, cần phòng vệ trong constructor và accessor đối với thành phần mutable.

### 5.3. “Unmodifiable” không đủ nếu phần tử mutable

`List.copyOf` tạo collection không thể thêm, xóa hay thay phần tử qua giao diện đó. Tuy nhiên nó **không tự sao chép sâu** các đối tượng phần tử. Nếu danh sách chứa một đối tượng `Address` có thể thay đổi và bên ngoài còn tham chiếu tới `Address`, thay đổi địa chỉ vẫn hiện ra khi đọc từ danh sách.

### 5.4. Giá trị bất biến được chia sẻ; thay trường là chuyện khác

Với trường có thể gán lại (`non-final`), phép `copy.name = "Tên mới"` chỉ thay **tham chiếu trong bản sao**, không sửa đối tượng `String` cũ và không đổi `original.name`. Cần phân biệt *gán lại tham chiếu* với *sửa trạng thái của đối tượng được tham chiếu*.

### 5.5. Chia sẻ giữa các luồng cần xét việc công bố đối tượng

Bất biến giúp loại bỏ tranh chấp về *thay đổi trạng thái của chính đối tượng immutable*. Nhưng khi truyền cả đối tượng chứa giữa các luồng, vẫn phải bảo đảm quá trình khởi tạo và công bố đối tượng đúng quy tắc Java Memory Model; các trường mutable khác vẫn cần chiến lược đồng bộ phù hợp. Không suy ra rằng toàn bộ object graph tự động thread-safe chỉ từ một trường `String` hay `LocalDate`.

## 6. Cách quyết định khi viết copy constructor

Với từng trường tham chiếu, kiểm tra theo trình tự:

1. **Có thể thay đổi được không?** Xét cả đối tượng cụ thể, các phần tử lồng bên trong và các alias còn tồn tại, không chỉ kiểu khai báo hay modifier `final`.
2. **Hợp đồng bản sao yêu cầu độc lập đến đâu?** Nếu cần độc lập về trạng thái, có thể chia sẻ bất biến. Nếu API yêu cầu mỗi thành phần phải có identity riêng, phải tuân thủ điều kiện identity đó.
3. **Nếu chắc chắn bất biến:** gán cùng tham chiếu; không cần tạo đối tượng tương đương một cách vô ích.
4. **Nếu mutable:** tạo bản sao thích hợp (mảng, collection hoặc từng đối tượng con). Với object graph có vòng tham chiếu hoặc nhiều alias, thiết kế copy sâu cẩn thận để giữ cấu trúc mong muốn.
5. **Chặn đường sửa ngầm:** copy phòng vệ ở constructor/getter khi cần; không để một alias bên ngoài tiếp tục sửa dữ liệu được coi là bất biến.

Ví dụ nhanh: một `Person` chứa `String fullName`, `LocalDate birthDate`, `int[] scores` và `List<Address> addresses`, trong đó `Address` mutable. Để sao chép độc lập trạng thái:

- Dùng lại tham chiếu `fullName` và `birthDate`.
- Dùng `scores.clone()` để tạo mảng mới.
- Tạo danh sách `addresses` mới **và** copy các `Address`; chỉ copy danh sách chưa đủ.

**Ghi nhớ:** *Độc lập trạng thái không đồng nghĩa phải tạo mới mọi đối tượng.* Hãy chia sẻ những đối tượng **thực sự bất biến**, và sao chép mọi phần trạng thái **có thể thay đổi** mà hợp đồng bản sao yêu cầu phải độc lập.
