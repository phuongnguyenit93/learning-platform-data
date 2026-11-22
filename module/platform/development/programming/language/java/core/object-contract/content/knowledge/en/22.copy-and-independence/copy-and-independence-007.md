# Chọn phạm vi sao chép theo quyền sở hữu dữ liệu trong Java

**Bối cảnh:** Java core → object-contract → sao chép và độc lập. Khi tạo bản sao của một đối tượng, câu hỏi quyết định không phải “sao chép nông hay sâu?” ngay lập tức, mà là **ai sở hữu dữ liệu nào, ai được phép thay đổi dữ liệu đó, và sau khi sao chép những thay đổi nào phải độc lập?** Quyền sở hữu ở đây là **quy ước thiết kế/API**, không phải cơ chế ownership được trình biên dịch Java thực thi.

## 1. Sao chép để bảo vệ ranh giới sở hữu

Biến tham chiếu Java trỏ tới đối tượng; phép gán chỉ sao chép giá trị tham chiếu. Hai biến có thể cùng trỏ tới một đối tượng và cùng quan sát được thay đổi của nó (*aliasing*). Ví dụ:

~~~java
List<String> input = new ArrayList<>(List.of("A"));
List<String> alias = input;                 // Cùng một danh sách
List<String> separate = new ArrayList<>(input); // Danh sách khác
input.add("B");
// alias thấy ["A", "B"]; separate vẫn ["A"].
~~~

Ví dụ trên độc lập ở **cấu trúc danh sách** vì phần tử `String` bất biến. Nếu danh sách chứa các đối tượng có thể thay đổi, `new ArrayList<>(input)` chỉ sao chép danh sách, **vẫn chia sẻ từng phần tử**.

Có thể mô tả một đối tượng như một đồ thị: nút gốc tham chiếu tới các đối tượng con; đối tượng con có thể tiếp tục tham chiếu tới đối tượng khác. **Phạm vi sao chép** là tập các nút cần tạo mới để bảo đảm đúng hợp đồng độc lập, không nhất thiết là toàn bộ đồ thị có thể đi tới được.

Ba kết quả thường gặp:

- **Chia sẻ có chủ đích:** hai bên cùng dùng một giá trị bất biến hoặc tài nguyên chung; không cần bản sao.
- **Sao chép chọn lọc:** tạo mới các nút mutable thuộc sở hữu riêng, đồng thời chia sẻ các giá trị bất biến hoặc các phụ thuộc dùng chung.
- **Snapshot:** tạo ảnh chụp của trạng thái tại một thời điểm; cần xác định snapshot chỉ cố định cấu trúc hay cố định cả trạng thái các phần tử.

Một bản sao có thể bằng nhau theo `equals()` nhưng khác nhau về identity (`original != copy`). Nếu chính identity là ý nghĩa nghiệp vụ (ví dụ một entity đang được ORM quản lý), tự tạo bản sao như một entity mới có thể sai, dù trường dữ liệu giống nhau.

## 2. Xác định quyền sở hữu trước khi chọn kỹ thuật

Với từng trường, tham số và giá trị trả về, cần trả lời:

1. **Ai tạo, ai quản lý vòng đời?** Đối tượng đang được lưu nội bộ, được caller cung cấp tạm thời, hay do framework/tài nguyên ngoài quản lý?
2. **Ai có quyền ghi?** Caller có thể sửa sau khi truyền vào không? Người nhận kết quả có thể sửa không?
3. **Thay đổi nào phải bị cô lập?** Chỉ thêm/xóa phần tử danh sách, hay cả sửa thuộc tính của mỗi phần tử?
4. **Đối tượng có thật sự bất biến?** Không chỉ trường `final`; mọi trạng thái có thể quan sát qua đối tượng đó cũng phải không thể thay đổi bằng các đường tham chiếu được cấp.
5. **Đồ thị có chia sẻ/cycle/identity quan trọng không?** Hai đường dẫn trỏ chung tới một nút có phải vẫn trỏ chung trong bản sao không?
6. **Chi phí có phù hợp không?** Đối tượng lớn, dữ liệu nhị phân, tải cao và luồng đồng thời có thể cần snapshot, immutable value hoặc copy-on-write thay vì deep copy tất cả.

### Ma trận quyết định theo ownership

| Dữ liệu tại ranh giới | Chính sách thường phù hợp | Vì sao |
| --- | --- | --- |
| `String`, `BigInteger`, `LocalDate`, value object bất biến đúng nghĩa | Chia sẻ tham chiếu | Không có mutation quan sát được để rò rỉ |
| `byte[]`, mảng mutable do caller đưa vào và đối tượng cần sở hữu | `array.clone()` hoặc `Arrays.copyOf()` | Tách vùng lưu trữ mảng; nếu mảng đa chiều thì cần xét phần tử bên trong |
| `List<String>` thuộc trạng thái nội bộ | `List.copyOf(input)` hoặc bản sao cấu trúc tương đương | Tách cấu trúc danh sách; `String` bất biến nên phần tử có thể dùng chung |
| `List<MutableItem>` do đối tượng sở hữu | Tạo danh sách mới **và sao chép từng phần tử** | Chỉ sao chép list vẫn làm lọt mutable item |
| Đồ thị nút mutable thuộc sở hữu riêng | Copy constructor/factory có ánh xạ nút đã sao chép | Bảo đảm độc lập, bảo toàn alias/cycle khi hợp đồng đòi hỏi |
| Repository, logger, service, pool, socket, file handle | Giữ tham chiếu chung theo hợp đồng hoặc quản lý vòng đời riêng | Đây là phụ thuộc/tài nguyên, không phải dữ liệu value có thể deep-copy tùy tiện |
| Thực thể JPA/ORM, aggregate có identity nghiệp vụ | Dùng DTO/value snapshot hoặc thao tác qua API quản lý entity | Tạo bản sao object không tự tạo ra entity nghiệp vụ hợp lệ |
| Cache hay cấu trúc chia sẻ chủ đích | Định nghĩa rõ quyền ghi và tính nhất quán | Copy vô điều kiện có thể làm mất semantics chia sẻ |

**Quy tắc hữu ích:** chỉ cần tạo bản sao của các đối tượng **mutable mà ranh giới mới phải sở hữu độc lập**; còn immutable có thể chia sẻ an toàn. Với mutable được chia sẻ có chủ đích, hợp đồng phải chỉ ra bên nào được sửa và khi nào.

## 3. Ba mức độc lập dễ bị nhầm

Giả sử `Order` chứa một `List<Line>`, mỗi `Line` chứa một `Price`:

- **Sao chép tham chiếu:** `Order second = first`. Cả hai biến chỉ đến cùng một đối tượng.
- **Shallow copy:** có `Order` mới và `List` mới, nhưng vẫn tham chiếu tới các `Line` cũ. Sửa danh sách (thêm/xóa) của bản này không trực tiếp thay đổi cấu trúc danh sách bản kia; sửa một `Line` có thể hiện ở cả hai.
- **Deep/ownership copy:** có `Order`, `List` và các `Line` thuộc sở hữu riêng; `Price` chỉ cần copy nếu mutable. Nếu `Price` là value bất biến thì chia sẻ vẫn cho mức độc lập mong muốn.

Đừng gọi một giải pháp là “deep copy” nếu chưa xác định **deep tới đâu**. Một cây mutable, một đồ thị có vòng lặp và một tập object chứa resource sống là ba trường hợp khác nhau. Kết quả đúng được đo bằng invariant và tình huống sửa dữ liệu, không bởi số lần gọi `clone()`.

Sao chép theo ownership thường cần ở hai hướng:

- **Defensive copy đầu vào:** constructor/setter nhận mutable từ caller, tạo phần thuộc sở hữu riêng để caller không thể lén sửa trạng thái nội bộ sau đó.
- **Defensive copy đầu ra:** getter/API trả dữ liệu mutable phải trả bản copy/snapshot hoặc giao diện chỉ đọc phù hợp để bên ngoài không sửa trạng thái thuộc sở hữu nội bộ.

Chỉ copy đầu vào mà trả trực tiếp mutable ra ngoài vẫn có lỗ hổng. Chỉ copy đầu ra mà giữ tham chiếu đầu vào cũng vậy.

## 4. Quy trình chọn phạm vi sao chép

**Bước 1 — Viết hợp đồng độc lập.** Chẳng hạn: “Sau khi tạo `Team` từ danh sách thành viên, caller được sửa danh sách, sửa thành viên và địa chỉ ban đầu mà không làm đổi `Team`. Caller được sửa snapshot trả về mà không làm đổi `Team`.”

**Bước 2 — Vẽ những cạnh tham chiếu quan trọng.** Ví dụ: `Team → List<Member> → Member → Address`. Đánh dấu `List`, `Member`, `Address` là mutable; `String` là immutable.

**Bước 3 — Đánh dấu chủ sở hữu.** `Team` sở hữu danh sách, các phần tử và địa chỉ riêng. Caller tiếp tục sở hữu các object đã truyền vào. Hai phía không được giữ chung mutable node.

**Bước 4 — Chỉ định hành vi ở từng ranh giới.** Constructor `Team` sao chép list, mỗi member và address. Method xuất snapshot lặp lại chính sách ấy. Các phương thức vận hành nội bộ được quyền sửa object mà `Team` sở hữu.

**Bước 5 — Kiểm chứng hai chiều.** Sửa dữ liệu gốc rồi quan sát bản sao; sửa bản sao rồi quan sát dữ liệu gốc. Kiểm tra cả cấu trúc và các phần tử lồng nhau, vì kiểm tra mỗi `==` hoặc size danh sách là chưa đủ.

## 5. Ví dụ Java 17 chạy độc lập: copy theo quyền sở hữu

Lưu thành tệp **OwnershipCopyDemo.java**. `Team` sở hữu độc lập cây `List<Member> → Member → Address`. Dữ liệu chuỗi được chia sẻ an toàn vì `String` bất biến. Snapshot trả về có cấu trúc danh sách không sửa được và các member tách biệt; **member trong snapshot vẫn mutable**, nên snapshot này là dữ liệu tách rời chứ chưa phải immutable value.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class OwnershipCopyDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = Objects.requireNonNull(city);
        }

        Address(Address source) {
            this(Objects.requireNonNull(source).city);
        }

        String city() {
            return city;
        }

        void setCity(String city) {
            this.city = Objects.requireNonNull(city);
        }
    }

    static final class Member {
        private String name;
        private final Address address;

        Member(String name, Address address) {
            this.name = Objects.requireNonNull(name);
            this.address = new Address(Objects.requireNonNull(address));
        }

        Member(Member source) {
            this(Objects.requireNonNull(source).name, source.address);
        }

        String name() {
            return name;
        }

        String city() {
            return address.city();
        }

        void rename(String name) {
            this.name = Objects.requireNonNull(name);
        }

        void move(String city) {
            address.setCity(city);
        }
    }

    static final class Team {
        private final List<Member> members;

        Team(List<Member> suppliedMembers) {
            Objects.requireNonNull(suppliedMembers);
            List<Member> copies = new ArrayList<>(suppliedMembers.size());
            for (Member member : suppliedMembers) {
                copies.add(new Member(Objects.requireNonNull(member)));
            }
            members = List.copyOf(copies);
        }

        List<Member> membersSnapshot() {
            List<Member> copies = new ArrayList<>(members.size());
            for (Member member : members) {
                copies.add(new Member(member));
            }
            return List.copyOf(copies);
        }

        void renameFirst(String newName) {
            members.get(0).rename(newName);
        }

        String describe() {
            Member first = members.get(0);
            return first.name() + "@" + first.city();
        }
    }

    public static void main(String[] args) {
        Address originalAddress = new Address("Ha Noi");
        Member originalMember = new Member("Lan", originalAddress);
        List<Member> supplied = new ArrayList<>();
        supplied.add(originalMember);

        Team team = new Team(supplied);

        originalAddress.setCity("Da Nang");
        originalMember.move("Hue");
        supplied.clear();
        System.out.println("Team after caller changes: " + team.describe());

        List<Member> snapshot = team.membersSnapshot();
        snapshot.get(0).rename("Minh");
        snapshot.get(0).move("Can Tho");
        System.out.println("Team after snapshot changes: " + team.describe());
        System.out.println("Snapshot: "
                + snapshot.get(0).name() + "@" + snapshot.get(0).city());

        try {
            snapshot.add(new Member("Mai", new Address("Hue")));
        } catch (UnsupportedOperationException ex) {
            System.out.println("List structure is unmodifiable");
        }

        team.renameFirst("Hoa");
        System.out.println("Team now: " + team.describe());
        System.out.println("Old snapshot remains: "
                + snapshot.get(0).name() + "@" + snapshot.get(0).city());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac OwnershipCopyDemo.java
java OwnershipCopyDemo
~~~

Stdout chính xác:

~~~text
Team after caller changes: Lan@Ha Noi
Team after snapshot changes: Lan@Ha Noi
Snapshot: Minh@Can Tho
List structure is unmodifiable
Team now: Hoa@Ha Noi
Old snapshot remains: Minh@Can Tho
~~~

**Vì sao ví dụ hoạt động?**

1. Constructor `Member(String, Address)` copy `Address`, nên sửa `originalAddress` không tác động tới thành viên.
2. Constructor `Team(List<Member>)` copy từng `Member`, và constructor `Member(Member)` lại copy `Address`. Vì vậy sửa `originalMember` hoặc xóa phần tử trong danh sách input không tác động tới `Team`.
3. `List.copyOf(copies)` ngăn thêm/xóa phần tử thông qua list được lưu, nhưng **không khóa trạng thái Member**; `Team.renameFirst()` vẫn đổi member nội bộ được.
4. `membersSnapshot()` tạo bản sao mọi phần tử mutable trước khi trả về. Caller sửa snapshot không ảnh hưởng tới `Team`; `Team` thay đổi sau đó cũng không ảnh hưởng snapshot cũ.
5. Nếu chỉ viết `List.copyOf(suppliedMembers)` ở constructor, cấu trúc list sẽ riêng nhưng phần tử vẫn là object caller sở hữu — vi phạm yêu cầu độc lập.

Đây là ví dụ dùng một luồng thực thi. Các thao tác copy/rename/move không tự mang lại thread safety; mục về concurrency bên dưới chỉ ra cách có snapshot nhất quán.

## 6. Hiểu đúng công cụ trong Java

### Copy constructor hoặc static factory

Với mutable value có quy tắc sở hữu rõ, copy constructor như `new Member(source)` hoặc factory như `Member.copyOf(source)` là nơi dễ mô tả chính sách copy cho từng field. Nên triển khai rõ ở lớp quản lý dữ liệu, kiểm tra tham số và invariant, để caller không phải biết cấu trúc nội bộ. Copy constructor tự viết **không đương nhiên deep**: nếu nó gán tham chiếu của field mutable thì vẫn là shallow copy.

### Arrays

- `byte[] result = input.clone();` sao chép các byte sang mảng mới — đủ để độc lập vì byte là primitive.
- `Address[] result = input.clone();` chỉ sao chép mảng chứa tham chiếu; từng `Address` vẫn dùng chung.
- `int[][] result = input.clone();` chỉ sao chép mảng ngoài; các mảng hàng vẫn dùng chung. Muốn độc lập dữ liệu hai chiều phải sao chép từng hàng và quy định xử lý hàng `null` nếu cho phép.

### Collections

~~~java
List<StringBuilder> source = new ArrayList<>();
source.add(new StringBuilder("A"));

List<StringBuilder> structuralCopy = new ArrayList<>(source);
List<StringBuilder> unmodifiableStructure = List.copyOf(source);

source.get(0).append("B");
// Cả structuralCopy.get(0) và unmodifiableStructure.get(0) đều là "AB".
~~~

- `new ArrayList<>(source)` tách cấu trúc, không sao chép phần tử.
- `List.copyOf(source)` tạo danh sách **không hỗ trợ thao tác thay đổi cấu trúc**, nhưng phần tử mutable vẫn có thể bị sửa; API này từ chối `null` và có thể trả lại cùng instance nếu input đã là danh sách không sửa được phù hợp.
- `Collections.unmodifiableList(source)` tạo **view** không cho sửa qua view, nhưng nếu `source` thay đổi thì view phản ánh thay đổi; không phải snapshot.
- `Stream.toList()` cho danh sách không hỗ trợ thao tác thay đổi cấu trúc, nhưng cũng không sao chép mutable item bên trong.
- `Map.copyOf()`, `Set.copyOf()` cũng không tự deep-copy key/value/element. Nếu key mutable ảnh hưởng `equals()/hashCode()`, sửa key sau khi cho vào map có thể làm hỏng khả năng tra cứu.

Nếu muốn snapshot thực sự bất biến, hãy **chuyển từng phần tử thành immutable DTO/value** (ví dụ record chỉ chứa `String`, `int`, `LocalDate` hay immutable value đúng nghĩa) rồi dùng danh sách bất biến.

### Java records không tự deep-copy

Record làm component reference trở thành `private final` và sinh accessor, nhưng không biến đối tượng được tham chiếu thành bất biến. Ví dụ sau **chỉ bảo vệ cấu trúc danh sách** khi element là `String` (bất biến):

~~~java
import java.util.List;
import java.util.Objects;

record Tags(List<String> values) {
    Tags {
        values = List.copyOf(Objects.requireNonNull(values));
    }
}
~~~

Đây là khai báo record minh họa, không phải chương trình chạy độc lập có `main`. Trong compact canonical constructor, gán lại tham số `values` khiến giá trị sau kiểm tra được dùng để gán field tương ứng khi constructor kết thúc. Nếu component là `List<MutableItem>`, phải copy sâu các item hoặc đổi sang immutable snapshot. Với mảng mutable, accessor mặc định của record còn trả ra chính mảng bên trong; cần override accessor để trả bản sao khi muốn bảo vệ trạng thái.

### `Object.clone()` không phải giải pháp tự động

Cài đặt `Object.clone()` mặc định tạo bản sao **shallow** ở mức field. `Cloneable` là marker interface; nó không định nghĩa public `clone()` cho caller. Kế thừa, field `final`, mutable nested state và invariant làm quy tắc clone khó bảo trì; các lớp không hỗ trợ clone có thể ném `CloneNotSupportedException`. Đối với ownership copy có hợp đồng cụ thể, constructor/factory rõ ràng thường dễ đọc và dễ kiểm chứng hơn. Không gọi `clone()` trên resource/ORM object với kỳ vọng hệ thống ngoài cũng được copy.

## 7. Khi không nên deep-copy

**Dữ liệu bất biến:** `String`, `UUID`, `LocalDate`, `BigDecimal` và immutable domain values có thể được chia sẻ vì sửa một instance là không thể theo API của chúng. Lưu ý một lớp tự khai báo “immutable” vẫn không bất biến nếu nó trả mảng, collection view có backing mutable, hoặc chứa mutable child truy cập được.

**Dịch vụ hoặc tài nguyên chia sẻ:** logger, executor, kết nối mạng, stream mở, transaction và repository có vòng đời/quyền truy cập riêng. Sao chép field reference có thể đúng khi hai bên cố ý cùng dùng một dependency; “deep-copy” tài nguyên thường không được định nghĩa. Đừng biến dependency thành một phần của cây dữ liệu cần clone.

**Entity và identity nghiệp vụ:** bản sao của một entity có ID cũ không tự trở thành bản ghi độc lập trong database. Tách DTO immutable/snapshot khi cần chuyển dữ liệu qua API hoặc event; thay đổi entity nên đi qua lifecycle/transaction theo hợp đồng hệ thống.

**Chia sẻ mutable có chủ đích:** hai component có thể cùng sở hữu một cache hoặc state store. Khi đó sự phụ thuộc là điều được thiết kế; copy tự tiện làm hai bên không còn quan sát cùng trạng thái. Ghi rõ owner của mutation, đồng bộ, thời gian sống và mức nhất quán.

### Đồ thị có alias hoặc chu trình

Ví dụ `left.child == right.child` trước copy. Nếu tạo riêng hai bản copy cho hai đường đi, invariant “hai cạnh cùng trỏ một nút” bị mất. Với đồ thị có cycle, đệ quy naïve còn có thể lặp vô hạn. Khi hợp đồng yêu cầu clone toàn đồ thị và **bảo toàn topology**, sử dụng bảng ánh xạ dựa trên identity, chẳng hạn `IdentityHashMap<OriginalNode, CopiedNode>`: tạo node copy, ghi vào map **trước** khi đệ quy copy các cạnh, và tái dùng copy đã có khi gặp lại node. Không áp dụng cách này như công thức chung nếu business semantics muốn tách các node logic khác nhau hoặc giữ reference tới resource ngoài.

## 8. Snapshot, hiệu năng và concurrency

Sao chép tốn thời gian và bộ nhớ tỷ lệ với lượng dữ liệu được tạo mới. Chọn phạm vi đúng giúp tránh clone toàn bộ đồ thị không cần thiết:

- Với read-only dữ liệu lớn, ưu tiên immutable value/immutable aggregate và chia sẻ chúng.
- Với mutable state ít được sửa nhưng đọc nhiều, cân nhắc **copy-on-write** hoặc thay thế snapshot immutable nguyên khối khi cập nhật. Đánh giá chi phí ghi và phân bổ bộ nhớ.
- Với dữ liệu trao đổi qua API, cân nhắc DTO snapshot chỉ chứa các trường caller thật sự cần; đừng serialize/deserialize toàn bộ object graph chỉ để tạo bản sao nếu có cách rõ ràng hơn.
- Với mảng lớn như `byte[]`, copy tại ranh giới trust/ownership khi cần chống mutation từ caller; nếu cố tình cho phép zero-copy, ghi rõ lifetime và quyền ghi.

**Thread safety là một yêu cầu khác với ownership independence.** Nếu thread A sửa `Member` đúng lúc thread B copy nó, snapshot có thể quan sát dữ liệu tại nhiều thời điểm khác nhau (đặc biệt khi có nhiều field). Hai bản sao độc lập sau khi tạo **không bảo đảm** snapshot được tạo ra một cách nhất quán.

Để snapshot nhất quán, chọn một cơ chế mà toàn bộ các thread liên quan đều tuân thủ: khóa khi ghi và khi đọc/sao chép, immutable snapshots được phát hành qua cơ chế đồng bộ thích hợp, hoặc một protocol versioning/snapshot có chứng minh nhất quán. `final` bảo vệ việc gán lại tham chiếu field, không làm những object lồng bên trong trở nên thread-safe. Copy một danh sách trong lúc một thread khác sửa danh sách đó mà không đồng bộ còn có thể gặp kết quả không nhất quán hoặc lỗi.

## 9. Lỗi phổ biến và cách nhận diện

| Lỗi | Dấu hiệu | Cách sửa |
| --- | --- | --- |
| Gán `this.items = input` khi cần ownership riêng | Caller sửa input, object nội bộ đổi theo | Copy cấu trúc và mọi phần tử mutable cần tách |
| Chỉ dùng `new ArrayList<>(input)` với mutable elements | Sửa thuộc tính item từ caller ảnh hưởng bản sao | Copy từng item hoặc chuyển thành immutable item |
| Trả trực tiếp mảng/list mutable qua getter | Caller sửa kết quả, trạng thái nội bộ đổi | Defensive copy đầu ra hoặc immutable representation |
| Nghĩ `List.copyOf()` làm mọi phần tử immutable | List không thêm được nhưng item vẫn bị sửa | Tách hoặc đóng băng element |
| Nghĩ `Collections.unmodifiableList()` là snapshot | Backing list sửa thì view đổi | Copy dữ liệu trước khi tạo view |
| Deep-copy luôn mọi field | Tốn kém, sai semantics với service/resource/identity | Phân loại theo ownership và mutability |
| Clone đệ quy mà không xử lý alias/cycle | Mất cấu trúc chia sẻ hoặc lặp vô hạn | Identity memoization nếu cần giữ graph topology |
| Chỉ test `original != copy` | Root khác nhưng nested state vẫn chung | Test thay đổi ở cả hai hướng và mọi lớp mutable |
| Copy khi có concurrent writes mà không điều phối | Snapshot chứa trạng thái trộn thời điểm | Đồng bộ writers/readers hoặc immutable snapshot protocol |

## 10. Checklist review hợp đồng sao chép

Khi thiết kế một constructor, factory hoặc API trả snapshot, hãy kiểm tra:

1. **Định nghĩa ownership:** Sau lời gọi, mỗi mutable object trong graph do ai kiểm soát? Có chỗ nào chủ đích chia sẻ mutable state không?
2. **Đầu vào:** Nếu caller sửa list, array, từng phần tử, object nested hoặc alias sau lời gọi, trạng thái bên nhận có còn đúng không?
3. **Đầu ra:** Caller có thể sửa kết quả và vô tình thay đổi object gốc không? Nếu chỉ trả view, có hợp đồng live-view rõ ràng không?
4. **Identity & invariant:** Object copy phải có identity mới, identity nghiệp vụ giữ nguyên trong DTO, hay phải bảo toàn alias/cycle? `equals()/hashCode()` còn đúng không?
5. **Dữ liệu đặc biệt:** Có `null`, collections chứa `null`, generic mutable object, resource bên ngoài, cache, JPA entity hoặc class kế thừa không?
6. **Concurrency:** Có mutation trong lúc copy không? Tại đâu bảo đảm snapshot nhất quán và visibility giữa thread?
7. **Chi phí:** Lượng dữ liệu cần copy bao nhiêu? Có thể chia sẻ immutable value hoặc chỉ copy đúng phần caller sở hữu không?
8. **Kiểm thử:** Sửa sau khi copy theo cả hai hướng; kiểm tra nested state, các đường alias, danh sách/mảng, snapshot cũ sau khi object gốc thay đổi.

### Tình huống áp dụng nhanh

**Tình huống A:** Constructor nhận `List<LocalDate>`, về sau caller được thay đổi list. Copy cấu trúc một lần bằng `List.copyOf(input)` (nếu không có `null`) là đủ; không cần copy từng `LocalDate`.

**Tình huống B:** Constructor nhận `List<MutableAddress>` và cần dữ liệu độc lập. Tạo list mới và copy mỗi address; chỉ dùng `List.copyOf(input)` thì chưa đạt hợp đồng.

**Tình huống C:** Một getter trả `byte[]` dùng để giữ bí mật trong object. Trả `data.clone()`; constructor cũng copy mảng caller cấp. Nếu không, hai phía có thể sửa trực tiếp cùng bộ nhớ.

**Tình huống D:** Có hai object cùng trỏ tới một `ExecutorService` được truyền từ bên ngoài. Chia sẻ theo hợp đồng và quyết định rõ bên nào chịu trách nhiệm `shutdown()`; không clone executor như dữ liệu domain.

## 11. Tự kiểm tra

**Câu 1.** Sau khi chạy `List.copyOf(mutableList)`, sửa một object mutable vốn là phần tử của `mutableList` có thể hiện trong kết quả không?  
**Đáp án:** Có. Chỉ cấu trúc collection bị ngăn sửa; object phần tử vẫn dùng chung nếu không được copy riêng.

**Câu 2.** Copy constructor phải sao chép tất cả field mới là “đúng”?  
**Đáp án:** Không. Copy những mutable value mà bản sao phải sở hữu riêng; immutable value và shared dependency có thể giữ cùng reference theo hợp đồng.

**Câu 3.** Hai object có `equals() == true` và `a != b` là bằng chứng deep copy đã thành công?  
**Đáp án:** Không. Chúng có thể chia sẻ nested mutable state. Phải thử mutation theo từng ranh giới ownership; với đồ thị, còn phải xem alias/cycle.

**Câu 4.** Vì sao một snapshot deep-copy sau khi tạo vẫn có thể sai trong chương trình đa luồng?  
**Đáp án:** Vì quá trình đọc để copy có thể chồng lấn với thread đang ghi, tạo dữ liệu không nhất quán. Cần protocol đồng bộ cho **thời điểm chụp**, ngoài việc tách alias sau khi chụp.

**Nguyên tắc kết thúc:** Hãy chọn phạm vi sao chép dựa trên **quyền sở hữu, tính mutable và hợp đồng độc lập có thể kiểm chứng**. Deep copy mọi thứ thường thừa hoặc sai; shallow copy mặc định thường thiếu. Thiết kế tốt chỉ sao chép đúng phần trạng thái mutable cần tách và làm rõ mọi phần được chia sẻ.