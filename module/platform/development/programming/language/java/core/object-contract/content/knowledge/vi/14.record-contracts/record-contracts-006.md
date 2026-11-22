# Record chỉ bất biến nông và vẫn có thể chứa dữ liệu thay đổi được

## 1. Điều quan trọng cần hiểu

Trong Java 17+, `record` cho phép khai báo một lớp chuyên biểu diễn dữ liệu bằng danh sách **record components**. Với ví dụ:

```java
record Profile(String name, java.util.List<String> roles) {}
```

Java sinh các trường `private final` tương ứng với `name` và `roles`, constructor, accessor `name()`/`roles()` và các phương thức `equals()`, `hashCode()`, `toString()`. Bản thân lớp record cũng là `final`, nghĩa là không thể kế thừa để mở rộng nó.

Tuy nhiên, `final` trên **trường tham chiếu** chỉ ngăn gán lại tham chiếu đó sau khi khởi tạo. Nó **không đóng băng đối tượng mà tham chiếu đang trỏ tới**. Do đó, một record có thể giữ `List`, `Map`, mảng, `Date`, `StringBuilder` hoặc đối tượng do bạn tạo có trạng thái thay đổi được. Nếu record giữ trực tiếp một đối tượng mutable, dữ liệu quan sát được qua record vẫn có thể đổi.

**Phân biệt ba khái niệm:**

- **Không gán lại được trường (final reference):** trường `roles` luôn giữ cùng tham chiếu đã được khởi tạo; không thể viết `profile.roles = other` từ bên ngoài.
- **Bất biến nông (shallow immutability):** cấu trúc bên ngoài không cho thay tham chiếu thành phần, nhưng dữ liệu nằm trong đối tượng được tham chiếu có thể đổi.
- **Bất biến sâu (deep immutability):** mọi trạng thái có thể quan sát và ảnh hưởng đến giá trị đều không thể thay đổi thông qua các tham chiếu có sẵn; điều này đòi hỏi cả các thành phần lồng bên trong cũng bất biến hoặc được sao chép/phong tỏa phù hợp.

**Record không mặc nhiên đảm bảo bất biến sâu.** Record là công cụ mô hình hóa dữ liệu với hợp đồng về các components, chứ không phải cơ chế tự động đóng băng toàn bộ đồ thị đối tượng.

## 2. Cơ chế: `final` cố định tham chiếu, không cố định trạng thái

Xem đoạn mã minh họa:

```java
record Team(String name, java.util.List<String> members) {}

java.util.List<String> people =
        new java.util.ArrayList<>(java.util.List.of("An"));
Team team = new Team("Backend", people);

people.add("Binh");

// team.members() nay có ["An", "Binh"].
```

`team.members()` trả lại danh sách mà record đang giữ; do constructor mặc định không sao chép nó, biến `people` và component `members` trỏ tới cùng `ArrayList`.

Người sử dụng có thể thay đổi danh sách theo ít nhất hai đường:

1. Giữ tham chiếu đầu vào `people` rồi gọi `people.add(...)`; record sẽ quan sát được thay đổi ấy.
2. Gọi `team.members().add(...)`; accessor được sinh mặc định trả chính tham chiếu `List` đang lưu.

`private final` chỉ áp dụng cho **trường `members` của record**. Nó không làm các phương thức `add`, `remove`, `clear` của một `ArrayList` trở nên bất hợp pháp.

Nếu component là `String` hoặc một giá trị bất biến phù hợp, ta không gặp vấn đề biến đổi nội dung qua chính đối tượng đó. Nhưng chỉ cần có một component mutable, không thể tuyên bố mọi trạng thái của record đều bất biến.

## 3. Những gì Java bảo đảm và không bảo đảm cho record

| Thuộc tính | Record bảo đảm | Record không tự bảo đảm |
| --- | --- | --- |
| Kiểu record | Là kiểu `final`, không có lớp con | Toàn bộ các đối tượng được component trỏ tới là bất biến |
| Trường component | Trường tương ứng là `private final` | Đối tượng tham chiếu không bị sửa từ nơi khác |
| Accessor mặc định | Cung cấp `componentName()` | Tự sao chép phòng vệ (defensive copy) khi trả component |
| Constructor mặc định | Nhận các giá trị component và lưu vào trường | Tự sao chép/kiểm tra cấu trúc mutable |
| `equals()`/`hashCode()` mặc định | Dựa trên các components theo quy tắc Java | Kết quả luôn ổn định khi component mutable bị sửa |
| `toString()` mặc định | Biểu diễn tên record và các component | Bản chụp bất biến hoặc dữ liệu an toàn để công khai |
| Mảng hoặc collection làm component | Có thể lưu tham chiếu tới chúng | So sánh sâu mọi phần tử hoặc khóa trạng thái bên trong |

Một record có thể định nghĩa phương thức, constructor để xác thực/sao chép đầu vào, hoặc accessor riêng. Nó vẫn không được khai báo thêm **instance field** độc lập ngoài các component fields mà cấu trúc record cho phép; các trường `static` vẫn có thể tồn tại theo quy tắc Java. Hạn chế này không đồng nghĩa với việc đối tượng được giữ trong component là immutable.

## 4. Vì sao dữ liệu mutable còn liên quan đến hợp đồng `equals()` và `hashCode()`?

Một điểm rất quan trọng của **hợp đồng record** là các phương thức `equals()` và `hashCode()` được sinh dựa trên những components.

Với record:

```java
record Task(String title, java.util.List<String> labels) {}
```

thành phần `labels` được so theo quan hệ bằng nhau của `List`. Các `List` tiêu chuẩn so bằng **dãy phần tử** và tính hash theo nội dung của dãy. Vì vậy, sau khi thêm phần tử vào danh sách được lưu, kết quả `task.hashCode()` có thể đổi. Đối với một record khác, `task.equals(otherTask)` cũng có thể chuyển từ `true` sang `false` hoặc ngược lại nếu dữ liệu tham gia so sánh bị sửa.

Điều này không tự động vi phạm hợp đồng của `equals`: hợp đồng nhất quán chỉ áp dụng khi dữ liệu dùng để so sánh không thay đổi. Nhưng record mutable sẽ tạo rủi ro lớn khi trở thành khóa trong `HashMap` hoặc phần tử của `HashSet`.

Ví dụ:

```java
java.util.List<String> labels =
        new java.util.ArrayList<>(java.util.List.of("java"));
Task key = new Task("study", labels);

java.util.Set<Task> items = new java.util.HashSet<>();
items.add(key);
labels.add("spring"); // Thay dữ liệu dùng để tạo hash.
```

Sau phép `add` cuối, giá trị hash của `key` có thể khác hash tại thời điểm `items.add(key)`. `HashSet` lưu phần tử theo vị trí tính từ hash cũ, nên tra cứu `items.contains(key)` có thể thất bại dù **đang giữ chính tham chiếu key đó**. Không nên viết bài test mặc định rằng mọi cấu hình hash đều chắc chắn thất bại vì hash/bucket collision và kích thước bảng có thể ảnh hưởng; điều cần tránh là **biến đổi khóa sau khi đưa vào collection**.

### Khác biệt giữa `List` và mảng trong component

Với `List`, phép `equals` tiêu chuẩn xét phần tử. Nhưng Java array **không override `Object.equals()` theo nội dung**. Do đó:

```java
record Bytes(byte[] content) {}

Bytes a = new Bytes(new byte[] {1, 2});
Bytes b = new Bytes(new byte[] {1, 2});

// java.util.Arrays.equals(a.content(), b.content()) là true.
// a.equals(b) là false: hai mảng khác tham chiếu.
```

Các bình luận ở trên là kết quả của đoạn minh họa; không cần thay code `equals` của record để có được chúng. Record sinh ra `equals` cho component mảng theo quan hệ bằng nhau của tham chiếu mảng, **không tự gọi `Arrays.equals`**. Nếu muốn mảng được so theo nội dung, phải tự thiết kế `equals`/`hashCode` phù hợp (và sao chép phòng vệ), hoặc đổi mô hình sang dạng giá trị bất biến có quan hệ bằng nhau đúng yêu cầu.

**Ghi nhớ:** Bất biến và bằng nhau là hai vấn đề liên quan nhưng **khác nhau**. Chặn sửa mảng bằng clone vẫn không làm record mặc định tự so các byte theo nội dung.

## 5. Hai ranh giới phải bảo vệ khi muốn bất biến sâu

Với dữ liệu mutable, cần xem xét **cả đầu vào constructor và đầu ra accessor**. Chẳng hạn, record chứa `byte[]` phải clone khi nhận để bên gọi không sửa mảng gốc, đồng thời clone khi trả để accessor không làm lộ mảng nội bộ. Với `List<String>`, `List.copyOf` trong compact constructor thường đủ vì danh sách không sửa được và `String` bất biến; `Collections.unmodifiableList(source)` chỉ là view nên chưa chụp snapshot.

Các biện pháp này phụ thuộc vào kiểu phần tử và hợp đồng sở hữu. `List.copyOf(List<MutableItem>)` vẫn cho phép sửa từng item qua alias; mảng đa chiều cần xem xét từng tầng. Nếu yêu cầu so nội dung mảng, cần đồng bộ `equals` và `hashCode`, vì generated equality chỉ so identity mảng. Bài về canonical constructor và accessor tiếp theo hướng dẫn cách hiện thực từng bước.

## 6. Ví dụ Java 17+ hoàn chỉnh

Ví dụ sau minh họa ba tình huống: record giữ `List` gốc; record chụp snapshot `List<String>`; record chụp snapshot `List` nhưng giữ phần tử mutable; và mảng đã clone nhưng `equals` mặc định vẫn so tham chiếu mảng.

Tạo tệp **`RecordShallowDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class RecordShallowDemo {

    record LooseProfile(String user, List<String> roles) {}

    record SafeProfile(String user, List<String> roles) {
        public SafeProfile {
            Objects.requireNonNull(user, "user");
            roles = List.copyOf(roles);
        }
    }

    static final class Tag {
        private String label;

        Tag(String label) {
            this.label = label;
        }

        void rename(String newLabel) {
            label = newLabel;
        }

        String label() {
            return label;
        }
    }

    record Holder(List<Tag> tags) {
        public Holder {
            tags = List.copyOf(tags);
        }
    }

    record ByteData(byte[] bytes) {
        public ByteData {
            bytes = bytes.clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("reader"));

        LooseProfile loose = new LooseProfile("An", source);
        SafeProfile safe = new SafeProfile("An", source);

        System.out.println("loose aliases source: "
                + (loose.roles() == source));
        System.out.println("safe aliases source: "
                + (safe.roles() == source));

        Set<LooseProfile> indexed = new HashSet<>();
        indexed.add(loose);
        int before = loose.hashCode();
        int safeBefore = safe.hashCode();

        source.add("admin");

        System.out.println("loose roles: " + loose.roles());
        System.out.println("safe roles: " + safe.roles());
        System.out.println("loose hash changed: "
                + (before != loose.hashCode()));
        System.out.println("safe hash unchanged: "
                + (safeBefore == safe.hashCode()));

        try {
            safe.roles().add("editor");
        } catch (UnsupportedOperationException ex) {
            System.out.println("safe roles are unmodifiable");
        }

        Tag tag = new Tag("draft");
        List<Tag> originals = new ArrayList<>(List.of(tag));
        Holder holder = new Holder(originals);

        originals.clear();
        System.out.println("holder count: "
                + holder.tags().size());

        tag.rename("published");
        System.out.println("tag inside holder: "
                + holder.tags().get(0).label());

        byte[] input = {1, 2};
        ByteData left = new ByteData(input);
        ByteData right = new ByteData(new byte[] {1, 2});

        input[0] = 9;
        System.out.println("array copy protected: "
                + (left.bytes()[0] == 1));
        System.out.println("same byte contents: "
                + Arrays.equals(left.bytes(), right.bytes()));
        System.out.println("record equality for arrays: "
                + left.equals(right));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac RecordShallowDemo.java
java RecordShallowDemo
```

**Kết quả:**

```text
loose aliases source: true
safe aliases source: false
loose roles: [reader, admin]
safe roles: [reader]
loose hash changed: true
safe hash unchanged: true
safe roles are unmodifiable
holder count: 1
tag inside holder: published
array copy protected: true
same byte contents: true
record equality for arrays: false
```

### Giải thích từng bước

1. `loose.roles() == source` là `true` vì record giữ nguyên tham chiếu danh sách. `safe.roles() == source` là `false` vì `List.copyOf` tạo snapshot từ `ArrayList` gốc.
2. Sau `source.add("admin")`, danh sách của `loose` có thêm `"admin"`. `safe` vẫn chỉ có `"reader"`.
3. `loose.hashCode()` đổi vì `List.hashCode()` phụ thuộc nội dung. Với `safe`, snapshot `List<String>` không đổi nên hash cũng ổn định.
4. `safe.roles().add("editor")` ném `UnsupportedOperationException`; chương trình bắt ngoại lệ và in thông báo.
5. `Holder` đã sao chép danh sách `Tag` nên `originals.clear()` không làm mất phần tử trong holder. Nhưng cả hai vẫn giữ **cùng đối tượng `Tag`**; vì thế `tag.rename("published")` làm tên tag trong holder thay đổi.
6. `ByteData` clone mảng ở cả constructor và accessor, nên chỉnh `input[0]` bên ngoài không làm đổi dữ liệu nội bộ.
7. `Arrays.equals(left.bytes(), right.bytes())` là `true` vì cùng byte. Nhưng `left.equals(right)` là `false` vì record mặc định so hai component kiểu `byte[]` theo danh tính của hai mảng khác nhau.

Ví dụ sử dụng `HashSet` để minh họa trường hợp khóa biến đổi hash; nó **không phụ thuộc** vào việc `contains` luôn trả `false` trên mọi JVM hay cấu hình bảng băm. Rủi ro là hash động có thể phá việc tra cứu chính xác khi đối tượng đã nằm trong hash collection.

## 7. Nếu cần record thật sự bất biến sâu

Một chiến lược có thể áp dụng:

1. **Chọn các component bất biến ngay từ thiết kế:** ưu tiên `String`, primitive, enum, `BigInteger`, `BigDecimal` và các value object đã được kiểm chứng bất biến.
2. **Dùng snapshot cho collection:** `List.copyOf`, `Set.copyOf`, `Map.copyOf` nếu các lựa chọn này phù hợp với chính sách null, thứ tự và ý nghĩa dữ liệu.
3. **Kiểm tra cả phần tử lồng bên trong:** nếu các phần tử mutable, biến đổi chúng thành record/value object bất biến trước khi đưa vào collection, hoặc thực hiện sao chép phòng vệ đúng kiểu.
4. **Đóng các đường rò rỉ qua accessor:** không trả trực tiếp mảng hoặc đối tượng mutable nội bộ nếu người gọi không được phép sửa.
5. **Giữ hợp đồng equality ổn định:** những thành phần dùng trong `equals`/`hashCode` không nên thay đổi khi record làm key hoặc phần tử set.
6. **Rõ ràng về chính sách null và validation:** `List.copyOf` từ chối null; cần quy định rõ có cho phép thiếu dữ liệu hay không.
7. **Viết test cho các alias đầu vào và đầu ra:** sửa dữ liệu gốc sau khi tạo, thử sửa giá trị accessor trả về, và sửa phần tử lồng bên trong để kiểm tra phạm vi bất biến thực tế.

Ví dụ với các phần tử có thể thay đổi:

```java
record MutableAddress(StringBuilder street) {}

record AddressValue(String street) {}

record Person(String name, List<AddressValue> addresses) {
    public Person {
        addresses = List.copyOf(addresses);
    }
}
```

Đây là đoạn khai báo minh họa cần `import java.util.List;`. `MutableAddress` không sâu bất biến vì `StringBuilder` có thể sửa. Ngược lại, `AddressValue` chỉ giữ `String`, còn `Person` chụp snapshot danh sách các `AddressValue`, nên **trong phạm vi các component vừa định nghĩa và không có trạng thái mutable khác**, chúng tạo nên đồ thị giá trị bất biến.

Không nên gọi bất biến sâu chỉ vì một lớp có từ khóa `record` hoặc chỉ vì accessor trả về collection “unmodifiable”; phải xem xét **đối tượng được chứa**.

## 8. Nguyên tắc thực hành và những lỗi phổ biến

| Cách làm sai hoặc thiếu | Vấn đề | Hướng giải quyết |
| --- | --- | --- |
| Dùng `record User(List<String> roles) {}` rồi mặc định cho là bất biến | Lộ tham chiếu `ArrayList` từ constructor và accessor | Dùng snapshot trong canonical constructor nếu cần giá trị bất biến. |
| Chỉ đặt `private final` cho biến tham chiếu | Không khóa nội dung `List`, `Map`, mảng hoặc object mutable | Sao chép phòng vệ và xem xét tính bất biến của từng component. |
| Dùng `Collections.unmodifiableList(source)` trực tiếp | Chỉ chặn sửa qua view; chỉnh `source` vẫn tác động | Dùng `List.copyOf` nếu muốn snapshot cấu trúc. |
| Dùng `new ArrayList<>(source)` rồi trả qua accessor | Bản sao có thể vẫn bị sửa qua accessor | Trả collection không sửa được hoặc bản sao phòng vệ. |
| Dùng `List.copyOf(List<MutableItem>)` rồi coi là sâu bất biến | Các phần tử vẫn giữ tham chiếu mutable | Chuyển đổi từng phần tử sang immutable value hoặc sao chép sâu theo yêu cầu. |
| Clone mảng khi nhận nhưng trả mảng trực tiếp | Bên ngoài có thể sửa mảng nội bộ qua accessor | Clone cả khi nhận và khi trả. |
| Clone mảng rồi mong `record.equals` so nội dung | Mảng không override `equals` theo nội dung | Tự định nghĩa equality/hash theo mảng hoặc dùng component kiểu giá trị thích hợp. |
| Đưa record chứa `ArrayList` mutable làm key `HashMap` | Hash thay đổi sau khi thêm có thể phá tra cứu | Thiết kế snapshot bất biến trước khi dùng làm key. |
| Cho rằng `final` của record ngăn mọi side effect | Phương thức vẫn có thể gọi mutator của đối tượng tham chiếu, ghi log, tác động hệ thống khác | Phân biệt trạng thái nội bộ record, tham chiếu và side effect ngoài đối tượng. |

### Trường hợp nào cho phép record có mutable component?

Không phải mọi record đều bắt buộc sâu bất biến. Có những API cố ý bọc một tài nguyên hoặc một đối tượng trạng thái để truyền nhiều giá trị gọn hơn. Điều này có thể hợp lệ nếu quy ước sở hữu và vòng đời dữ liệu được xác định rõ.

Tuy vậy, record mặc định được thiết kế xoay quanh **giá trị của components**. Nếu các component thay đổi theo thời gian, cần đánh giá nghiêm túc những hệ quả đối với `equals()`, `hashCode()`, `toString()`, tính an toàn luồng, việc serialize dữ liệu và việc dùng object làm cache key.

**Đặc biệt:** `final` không tự tạo thread-safety. Một component `List` mutable có thể đang được nhiều luồng cùng đọc/ghi; record không thay thế cho các quy tắc đồng bộ, ownership hay bất biến sâu.

## 9. Tự kiểm tra

**Câu 1.** Record có trường component `private final List<String> roles`. Điều gì được bảo đảm?

**Đáp án:** Tham chiếu trường được khởi tạo và không thể gán lại sau đó. Nội dung danh sách vẫn có thể đổi nếu đối tượng danh sách mutable và còn đường tham chiếu để sửa.

**Câu 2.** Vì sao `List.copyOf(source)` khác `Collections.unmodifiableList(source)`?

**Đáp án:** `List.copyOf` cung cấp snapshot không sửa được của cấu trúc danh sách từ đầu vào mutable; `Collections.unmodifiableList` là view không sửa được nhưng có thể phản ánh các thay đổi được thực hiện trên danh sách nền.

**Câu 3.** `List.copyOf` có giúp record chứa `List<StringBuilder>` bất biến sâu không?

**Đáp án:** Không. Danh sách không cho thêm/xóa phần tử qua API nhưng các `StringBuilder` bên trong vẫn có thể `append` hoặc sửa khác.

**Câu 4.** Vì sao record chứa `List` mutable có thể gây rắc rối khi được dùng làm key của `HashMap`?

**Đáp án:** Record sinh `hashCode()` từ các components. Với `List`, hash thay đổi theo nội dung; thay đổi danh sách sau khi đưa key vào map có thể làm tra cứu theo bucket cũ thất bại.

**Câu 5.** Hai record chứa hai `byte[]` khác nhau nhưng có byte giống hệt sẽ mặc định bằng nhau qua `equals()` không?

**Đáp án:** Không. Mảng mặc định so tham chiếu, không so toàn bộ phần tử. Nếu yêu cầu so nội dung, cần quy tắc equality/hash khác.

**Câu 6.** Muốn record lưu mảng mà bên ngoài không sửa được dữ liệu nội bộ, cần làm gì?

**Đáp án:** Clone mảng trong constructor để tách đầu vào và clone tiếp ở accessor để không lộ mảng nội bộ. Nếu cần equality theo nội dung, thiết kế riêng `equals`/`hashCode` phù hợp.

**Ghi nhớ:** Record của Java cố định **tham chiếu các component** và cung cấp hợp đồng giá trị tiện lợi, nhưng **không tự biến các đối tượng được tham chiếu thành bất biến sâu**. Khi cần bất biến thực sự, phải kiểm soát đầu vào, đối tượng lồng nhau, accessor và quan hệ `equals()`/`hashCode()`.