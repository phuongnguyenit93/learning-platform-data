# Quan hệ hai chiều và bảo toàn tính nhất quán giữa các lớp trong Java

Trong lập trình hướng đối tượng, một **quan hệ hai chiều (bidirectional association)** cho phép đi từ object A đến object B, đồng thời từ B truy ngược về A. Ví dụ: `Employee` biết phòng ban mình thuộc về, còn `Department` biết những nhân viên của phòng. Cả hai phía phải mô tả **cùng một quan hệ**.

Điều nguy hiểm là Java không tự đồng bộ hai reference hay collection. Nếu `employee.department` trỏ phòng X nhưng `X.employees` không chứa nhân viên đó, đối tượng đang ở trạng thái mâu thuẫn. Tương tự, nếu chuyển nhân viên từ X sang Y mà quên xóa khỏi danh sách của X, một người có thể xuất hiện ở hai phòng dù mô hình chỉ cho phép thuộc tối đa một phòng.

Bài thuộc **Java core - class-object**, nhóm **Quan hệ giữa lớp**. Mục tiêu là thiết kế bất biến quan hệ (*relationship invariants*), kiểm soát thêm–xóa–chuyển liên kết, tránh cập nhật một phía, xử lý ngoại lệ, chống duplicate và alias mutable, phân biệt một–một, một–nhiều, nhiều–nhiều, rồi nhận biết khi nào cần concurrency control hoặc database transaction. Các chương trình hoàn chỉnh sử dụng **Java 17+**.

## 1. Association một chiều và hai chiều

Một chiều:

~~~java
class Department {
    private final String name = "Engineering";
}

class Employee {
    private Department department;
}
~~~

Đây là hai lớp minh họa, không có `main`. Khi có object Employee, code được cho phép có thể lần theo `department`. Ngược lại, một Department không có field giúp truy cập trực tiếp danh sách Employee. Muốn tìm người thuộc phòng ấy có thể truy vấn từ repository hoặc một collection quản lý bên ngoài.

Hai chiều:

~~~java
class Department {
    private final java.util.List<Employee> employees =
            new java.util.ArrayList<>();
}

class Employee {
    private Department department;
}
~~~

Bây giờ có hai hướng, nhưng **hai field không tự giữ đúng với nhau**. Một collection và một reference đang lưu trùng thông tin liên kết. Nếu tồn tại hai chỗ cập nhật độc lập, chúng dễ lệch nhau.

Chỉ nên chọn quan hệ hai chiều khi việc tra cứu ngược mang lại giá trị thực sự. Nếu chiều ngược có thể truy vấn dễ và hiếm sử dụng, mô hình một chiều có thể ít rủi ro hơn.

## 2. Không nhầm bidirectional với aggregation/composition

Đây là những chiều phân loại khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Association | Các object có liên hệ | Nhân viên và phòng ban |
| Unidirectional/bidirectional | Có thể điều hướng một hay hai chiều | Employee → Department hoặc cả hai |
| Multiplicity | Mỗi đầu có bao nhiêu đối tác | Một phòng nhiều người, mỗi người tối đa một phòng |
| Aggregation | Toàn thể–thành phần lỏng theo mô hình miền | Nhóm gồm các thành viên độc lập |
| Composition | Sở hữu mạnh/vòng đời thành phần gắn với toàn thể | Order sở hữu OrderLine |
| Ownership of update | Phần code nào thực thi thay đổi liên kết | Department.addMember là lối vào |

**Quan hệ hai chiều không tự là composition.** Một liên kết bạn bè có thể hai chiều nhưng không ai sở hữu vòng đời của ai. Một Order có thể sở hữu OrderLine nhưng API chỉ cần chiều từ Order sang các dòng.

Trong Java Core, những quan hệ này thường được biểu diễn bằng field tham chiếu, `List`, `Set`, `Map` và các method. Trách nhiệm duy trì invariant là của code, không phải keyword đặc biệt.

## 3. Viết invariant dưới dạng kiểm tra được

Giả định nghiệp vụ: một `Member` thuộc **0 hoặc 1** `Team`; một `Team` có **0 hoặc nhiều** `Member`; mỗi member chỉ xuất hiện một lần trong cùng team.

~~~text
Member.team == T
    <=> Team T chứa Member đúng một lần.

Member.team == null
    => không Team nào trong phạm vi quản lý giữ Member.

Member chỉ có một team tại một thời điểm.
Nếu chuyển từ A sang B:
    A không còn Member;
    B có Member đúng một lần;
    Member.team == B.
~~~

Ký hiệu `<=>` trong sơ đồ nghĩa là hai chiều tương đương về sự tồn tại quan hệ. Không chỉ kiểm tra `member.team != null`, mà còn phải kiểm tra Team ở chiều ngược thực sự lưu member.

Nếu nghiệp vụ không cho phép member không có team thì phải dùng multiplicity **1 ↔ 0..***, và method `leave()` không được công bố trạng thái `team=null` như một trạng thái cuối hợp lệ. Chính sách miền dữ liệu quyết định `null` được phép hay không.

## 4. Ba thao tác cốt lõi của quan hệ hai chiều

| Thao tác | Các thay đổi bắt buộc |
| --- | --- |
| Thêm | Gắn tham chiếu từ A tới B và thêm A vào collection của B |
| Xóa | Gỡ tham chiếu ở A và loại A khỏi collection B |
| Chuyển A từ B1 sang B2 | Gỡ ở B1, thêm ở B2, cập nhật tham chiếu A |
| Thêm lại cùng liên kết | Không tạo phần tử trùng |
| Xóa lại hoặc yêu cầu xóa từ sai B | Không xóa nhầm liên kết khác |
| Thất bại validation | Giữ trạng thái cũ theo hợp đồng |

Lời gọi nguy hiểm nếu setter chỉ sửa một field:

~~~java
employee.setDepartment(newDepartment);
~~~

Đây là **lời gọi minh họa một API thiếu bảo vệ**, không phải chương trình độc lập. `oldDepartment.employees` và `newDepartment.employees` có thể vẫn chưa đổi.

Một API hành vi hợp lý hơn là `employee.transferTo(newDepartment)` hoặc `newDepartment.addEmployee(employee)`. Bên trong method đó, code thực hiện toàn bộ cập nhật cần thiết.

## 5. Chọn một nguồn thực thi thay đổi

Nên có **một thuật toán trung tâm** cho việc thay liên kết. Nếu cả hai đầu đều có method công khai dễ gọi, đầu còn lại **ủy quyền** về thuật toán đó; không sao chép hai bản implementation.

Ví dụ, `Member.moveTo(next)` có thể gọi `next.add(this)`. `Team.add(member)` là nơi kiểm tra phòng cũ, phòng mới và chỉnh cả hai đầu. Khi rời nhóm, `Member.moveTo(null)` ủy quyền `oldTeam.remove(this)`.

Không bắt buộc thuật toán phải nằm trong Team: một `MembershipService` hoặc `Employee.transferTo` cũng có thể là chủ quản. Điều quan trọng là tránh API bắt caller phải nhớ ba thao tác độc lập theo đúng thứ tự.

**Thiết kế đúng:** caller diễn đạt *ý định*. **Thiết kế dễ sai:** caller phải biết mọi collection/reference bên trong.

## 6. Chương trình hoàn chỉnh: một nhóm và nhiều thành viên

Tạo tệp **`BidirectionalTeamDemo.java`**. Hai kiểu thành viên `Team` và `Member` cùng nằm trong một lớp bao; Java cho phép code các lớp lồng truy cập `private` thích hợp của nhau trong cùng nest.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BidirectionalTeamDemo {
    private static final class Team {
        private final String name;
        private final List<Member> members = new ArrayList<>();

        Team(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("team name rỗng");
            }
            this.name = name;
        }

        String name() {
            return name;
        }

        List<String> memberNames() {
            return members.stream()
                    .map(Member::name)
                    .toList();
        }

        boolean add(Member member) {
            Objects.requireNonNull(member, "member");

            if (member.team == this) {
                return false;
            }
            if (members.contains(member)) {
                throw new IllegalStateException("đích đã chứa member");
            }

            Team old = member.team;
            if (old != null && !old.members.contains(member)) {
                throw new IllegalStateException("nguồn thiếu member");
            }

            // Bước có thể cần cấp phát ở đích diễn ra trước.
            members.add(member);

            if (old != null) {
                old.members.remove(member);
            }
            member.team = this;
            return true;
        }

        boolean remove(Member member) {
            Objects.requireNonNull(member, "member");

            if (member.team != this) {
                return false;
            }
            if (!members.remove(member)) {
                throw new IllegalStateException("team thiếu member");
            }
            member.team = null;
            return true;
        }
    }

    private static final class Member {
        private final String name;
        private Team team;

        Member(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("member name rỗng");
            }
            this.name = name;
        }

        String name() {
            return name;
        }

        String teamName() {
            return team == null ? "-" : team.name();
        }

        boolean moveTo(Team next) {
            if (next == null) {
                return team != null && team.remove(this);
            }
            return next.add(this);
        }
    }

    public static void main(String[] args) {
        Team red = new Team("Đỏ");
        Team blue = new Team("Xanh");
        Member an = new Member("An");
        Member binh = new Member("Bình");

        red.add(an);
        red.add(binh);
        System.out.println("red=" + red.memberNames());
        System.out.println("blue=" + blue.memberNames());

        System.out.println("repeat=" + red.add(an));
        System.out.println("An team=" + an.teamName());

        an.moveTo(blue);
        System.out.println("after red=" + red.memberNames());
        System.out.println("after blue=" + blue.memberNames());
        System.out.println("after An=" + an.teamName());

        System.out.println("wrong remove=" + red.remove(an));
        an.moveTo(null);
        System.out.println("empty blue=" + blue.memberNames());
        System.out.println("unassigned=" + an.teamName());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BidirectionalTeamDemo.java
java BidirectionalTeamDemo
~~~

**Stdout:**

~~~text
red=[An, Bình]
blue=[]
repeat=false
An team=Đỏ
after red=[Bình]
after blue=[An]
after An=Xanh
wrong remove=false
empty blue=[]
unassigned=-
~~~

### Vì sao ví dụ này giữ hai đầu nhất quán?

- `Team.members` và `Member.team` là private, không có setter trực tiếp tùy ý.
- `red.add(an)` thêm vào danh sách và đổi `an.team` cùng một đường xử lý.
- `red.add(an)` lần hai trả `false`, tránh duplicate.
- `an.moveTo(blue)` ủy quyền cho `blue.add(an)`: kiểm tra nguồn hợp lệ, thêm đích, xóa nguồn, đặt tham chiếu mới.
- `red.remove(an)` khi An đã thuộc Blue trả `false`, không gỡ quan hệ hiện tại.
- `an.moveTo(null)` gỡ ở đúng Blue và đưa An về trạng thái chưa phân nhóm.

**Giới hạn:** ví dụ chủ ý là **đơn luồng**, không có callback/database. Các bước riêng biệt không nguyên tử giữa những thread. `ArrayList.add` có thể thất bại do tài nguyên; việc thêm vào đích trước xóa nguồn giúp giảm một tình huống mất quan hệ nhưng **không cam kết rollback trước mọi lỗi nghiêm trọng**.

## 7. Một bất biến cần cả chiều thuận lẫn chiều ngược

Một số code chỉ kiểm tra một đầu:

~~~text
assert member.team == team
~~~

Điều này chưa đủ. Nếu collection của `team` không chứa `member`, hệ thống vẫn sai. Một phép kiểm tra đầy đủ cho quan hệ 0..1 ↔ 0..* cần xác nhận:

- Nếu `member.team == team`, collection của team phải chứa member.
- Nếu collection chứa member, field `member.team` phải trỏ về chính team.
- Mỗi object member xuất hiện đúng một lần trong một team theo mô hình.
- Member thuộc team A không còn trong bất cứ team B khác thuộc phạm vi quan hệ quản lý.

Khi viết test cho một thao tác chuyển, phải kiểm tra **cả phòng cũ, phòng mới và object được chuyển**. Chỉ kiểm tra dòng `member.teamName()` sau lời gọi không phát hiện được “danh sách cũ còn sót”.

## 8. Vì sao không trả trực tiếp collection nội bộ?

Nếu thiết kế:

~~~java
List<Member> getMembers() {
    return members;
}
~~~

và một caller thực hiện:

~~~java
team.getMembers().clear();
~~~

thì caller xóa hết membership trong Team mà không cập nhật `member.team` ở từng Member. Đây là **đoạn minh họa về đường phá invariant**, không phải chương trình đầy đủ.

Các lựa chọn:

- **Snapshot:** `List.copyOf(members)` khi phần tử không null; caller không thể thêm/xóa qua danh sách snapshot.
- **Read-only view:** `Collections.unmodifiableList(members)`; ngăn sửa qua view nhưng phản ánh thay đổi của list gốc.
- **Projection:** chỉ trả các thông tin cần đọc, như danh sách tên hoặc ID.
- **Truy vấn:** `containsMember`, `memberCount`, `findMember` nếu không cần lộ cả danh sách.

`List.copyOf` tạo shallow copy: object Member bên trong **không được deep-copy**. Nếu Member có setter trái invariant, caller vẫn có thể tác động tới object ấy. Vì vậy phải bảo vệ cả các phần tử, không chỉ collection container.

Trong `BidirectionalTeamDemo`, `memberNames()` trả `List<String>` từ `Stream.toList()`; kết quả không hỗ trợ thay đổi qua API danh sách và không cho caller thao tác trực tiếp vào membership.

## 9. Dùng `List` hay `Set` để chống trùng?

| Collection | Thuận lợi | Điểm cần chú ý |
| --- | --- | --- |
| `ArrayList<Member>` | Giữ thứ tự thêm, dễ demo | Tự kiểm tra duplicate |
| `LinkedHashSet<Member>` | Không trùng theo equality và giữ thứ tự | `equals/hashCode` phải ổn định |
| `HashSet<Member>` | Tra cứu membership thuận tiện | Thứ tự duyệt không cố định |
| `Map<MemberId,Member>` | Đảm bảo mỗi ID chỉ xuất hiện một lần | Cần định nghĩa ID duy nhất/ổn định |
| `List<Enrollment>` | Thích hợp khi một liên kết là object có thuộc tính | Cần cách tìm duplicate theo cặp khóa |

`Member` trong chương trình hoàn chỉnh là `final` và không override `equals`: `ArrayList.contains` dựa trên identity object. **Hai nhân viên khác object nhưng cùng tên** vẫn là hai thực thể khác nhau. Hệ thống thực nên dùng mã nhân viên hoặc identity có hợp đồng rõ, không lấy tên hiển thị làm khóa duy nhất.

Đừng dùng trường mutable để tính `hashCode` cho object đang là phần tử trong `HashSet`: đổi field có thể khiến set không tìm thấy phần tử theo bucket cũ.

## 10. Validation, idempotence và chính sách khi thấy lệch

Nếu cùng quan hệ được thêm lại, method có thể trả `false`, không sinh liên kết trùng. Nếu caller xóa từ phía sai, nên trả `false` hoặc một kết quả có nghĩa, **không tự cắt liên kết đang tồn tại ở nơi khác**.

Khi phát hiện field và collection đã lệch, đừng âm thầm đoán phía nào đúng rồi tự sửa một nửa. Ví dụ trên chọn `IllegalStateException` để báo trạng thái nội bộ bất hợp lệ.

Một hợp đồng có thể quy định:

~~~text
add(đã tồn tại đúng) -> không thay đổi
remove(không tồn tại) -> không thay đổi
move(A -> B) -> tất cả các phía cùng phản ánh B
đầu vào sai -> báo lỗi trước khi đổi
trạng thái nội bộ lệch -> fail fast để điều tra
~~~

Các hệ thống cần tự chữa dữ liệu có thể tạo **quy trình reconciliation riêng**. Nhưng reconciliation không nên âm thầm lẫn vào mọi setter vì có thể che nguyên nhân sai hoặc làm mất liên kết đúng.

## 11. Thứ tự thao tác khi chuyển và bảo toàn trạng thái khi lỗi

Xét việc chuyển Member từ Team A tới Team B. Nếu B đã đầy mà code xóa Member khỏi A trước khi kiểm tra sức chứa, khi validation thất bại, Member đã mất liên kết cũ.

Một trình tự tốt hơn:

1. Kiểm tra tham số và quy tắc cho phép chuyển.
2. Kiểm tra điều kiện của B, như capacity và trạng thái active.
3. Xác minh Member thật sự đang có trong A nếu field nói A.
4. Tính các dữ liệu cần cập nhật; làm trước những phép tính có thể ném exception.
5. Cập nhật những cấu trúc liên quan trong một lối vào kiểm soát.
6. Kiểm tra trạng thái mới đúng invariant; công bố kết quả thành công.

Cập nhật hai collection và một field vẫn không phải **transaction nguyên tử** giữa luồng nếu chỉ dùng method thông thường. Nếu có callback hoặc bên ngoài có quyền sửa collection trong quá trình chuyển, rủi ro càng lớn.

**Không dùng exception như rollback tự động.** Java sẽ không tự hoàn tác `old.members.remove(member)` chỉ vì bước `new.members.add(member)` sau đó ném lỗi.

## 12. Quan hệ hai chiều một–một: giữ đối xứng

Một–một hai chiều yêu cầu:

~~~text
A.partner == B <=> B.partner == A

Mỗi A có tối đa một partner.
Tùy nghiệp vụ, null có thể biểu diễn chưa ghép.
~~~

Nếu A↔B và C↔D rồi gọi A ghép với C, kết quả nhất quán phải là **A↔C**, B không còn partner và D cũng không còn partner. Chỉ gán `A.partner=C` và `C.partner=A` sẽ bỏ lại hai reference cũ sai.

Tạo tệp **`SymmetricPartnerDemo.java`**:

~~~java
public class SymmetricPartnerDemo {
    private static final class Partner {
        private final String name;
        private Partner peer;

        Partner(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name rỗng");
            }
            this.name = name;
        }

        String peerName() {
            return peer == null ? "-" : peer.name;
        }

        void unpair() {
            if (peer == null) {
                return;
            }
            Partner old = peer;
            if (old.peer != this) {
                throw new IllegalStateException("quan hệ bị lệch");
            }
            peer = null;
            old.peer = null;
        }

        void pairWith(Partner other) {
            if (other == null) {
                throw new IllegalArgumentException("other null");
            }
            if (other == this) {
                throw new IllegalArgumentException("không tự ghép");
            }
            if (peer == other) {
                if (other.peer != this) {
                    throw new IllegalStateException("quan hệ bị lệch");
                }
                return;
            }

            if (peer != null && peer.peer != this) {
                throw new IllegalStateException("nguồn bị lệch");
            }
            if (other.peer != null && other.peer.peer != other) {
                throw new IllegalStateException("đích bị lệch");
            }

            unpair();
            other.unpair();
            peer = other;
            other.peer = this;
        }
    }

    public static void main(String[] args) {
        Partner an = new Partner("An");
        Partner binh = new Partner("Bình");
        Partner chi = new Partner("Chi");
        Partner dung = new Partner("Dũng");

        an.pairWith(binh);
        chi.pairWith(dung);
        System.out.println("first=" + an.peerName()
                + "/" + binh.peerName());
        System.out.println("second=" + chi.peerName()
                + "/" + dung.peerName());

        an.pairWith(chi);
        System.out.println("An=" + an.peerName());
        System.out.println("Chi=" + chi.peerName());
        System.out.println("Bình=" + binh.peerName());
        System.out.println("Dũng=" + dung.peerName());

        chi.unpair();
        System.out.println("after unpair="
                + an.peerName() + "/" + chi.peerName());

        try {
            an.pairWith(an);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SymmetricPartnerDemo.java
java SymmetricPartnerDemo
~~~

**Stdout:**

~~~text
first=Bình/An
second=Dũng/Chi
An=Chi
Chi=An
Bình=-
Dũng=-
after unpair=-/-
reject=không tự ghép
~~~

### Phân tích

`an.pairWith(chi)` kiểm tra hai liên kết hiện có trước, gỡ A↔B, gỡ C↔D, rồi gán A↔C. Không có callback hay nguồn sửa ngoài trong quá trình này. Gọi `chi.unpair()` tiếp theo gỡ **cả hai reference**.

Ví dụ **cấm tự ghép** `A↔A` vì quy tắc của mô hình minh họa, không phải vì Java cấm object trỏ tới `this`. Trong những miền dữ liệu có self-reference hợp lệ, invariant và cách xử lý phải được xác định riêng.

Với quan hệ bắt buộc 1↔1, trạng thái `peer=null` có thể bị cấm; khi đó không thể dùng cùng API `unpair()` như một thao tác công khai hợp lệ.

## 13. Quan hệ nhiều–nhiều và association object

Với `Student` và `Course`, một sinh viên học nhiều môn, một môn có nhiều sinh viên. Thiết kế hai chiều trực tiếp có thể gồm:

~~~text
Student.courses = Set<Course>
Course.students = Set<Student>
~~~

Nhưng mỗi lần đăng ký hoặc hủy đăng ký phải thêm/xóa **cả hai sets**, tránh duplicate và giữ các phía đúng.

Nếu quan hệ có thông tin như điểm, ngày đăng ký hoặc trạng thái, một lớp `Enrollment` biểu diễn **chính liên kết** thường tự nhiên hơn. Điểm 9 thuộc **An–Java**, không phải điểm chung của An cho mọi môn hay của Java cho mọi sinh viên.

Có hai cách tổ chức:

- Giữ hai collections và một helper cập nhật cả hai.
- Giữ một **registry của Enrollment làm nguồn sự thật**, rồi xây hai hướng truy vấn dựa trên registry, tránh lưu hai bản sao membership.

Cách thứ hai có thể cần chỉ mục bổ sung để tra cứu hiệu quả trên dữ liệu lớn; nhưng chỉ mục cũng phải được cập nhật đúng quy tắc.

## 14. Chương trình hoàn chỉnh: nhiều–nhiều bằng một registry

Tạo tệp **`EnrollmentRegistryDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class EnrollmentRegistryDemo {
    private static final class Student {
        private final String name;

        Student(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("student name rỗng");
            }
            this.name = name;
        }
    }

    private static final class Course {
        private final String code;

        Course(String code) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("course code rỗng");
            }
            this.code = code;
        }
    }

    private static final class Enrollment {
        private final Student student;
        private final Course course;
        private int score;

        Enrollment(Student student, Course course) {
            this.student = student;
            this.course = course;
        }

        int score() {
            return score;
        }

        void setScore(int next) {
            if (next < 0 || next > 10) {
                throw new IllegalArgumentException("score ngoài 0..10");
            }
            score = next;
        }
    }

    private record Key(Student student, Course course) {
    }

    private final Map<Key, Enrollment> entries =
            new LinkedHashMap<>();

    Enrollment enroll(Student student, Course course) {
        Objects.requireNonNull(student, "student");
        Objects.requireNonNull(course, "course");
        Key key = new Key(student, course);
        return entries.computeIfAbsent(
                key, k -> new Enrollment(student, course));
    }

    boolean drop(Student student, Course course) {
        Objects.requireNonNull(student, "student");
        Objects.requireNonNull(course, "course");
        return entries.remove(new Key(student, course)) != null;
    }

    Optional<Enrollment> find(Student student, Course course) {
        Objects.requireNonNull(student, "student");
        Objects.requireNonNull(course, "course");
        return Optional.ofNullable(
                entries.get(new Key(student, course)));
    }

    List<String> coursesOf(Student student) {
        Objects.requireNonNull(student, "student");
        return entries.values().stream()
                .filter(e -> e.student == student)
                .map(e -> e.course.code)
                .toList();
    }

    List<String> studentsOf(Course course) {
        Objects.requireNonNull(course, "course");
        return entries.values().stream()
                .filter(e -> e.course == course)
                .map(e -> e.student.name)
                .toList();
    }

    public static void main(String[] args) {
        EnrollmentRegistryDemo registry =
                new EnrollmentRegistryDemo();
        Student an = new Student("An");
        Student binh = new Student("Bình");
        Course java = new Course("Java");
        Course sql = new Course("SQL");

        registry.enroll(an, java).setScore(9);
        registry.enroll(an, sql).setScore(8);
        registry.enroll(binh, java).setScore(7);
        registry.enroll(an, java);

        System.out.println("An=" + registry.coursesOf(an));
        System.out.println("Java=" + registry.studentsOf(java));
        System.out.println("score="
                + registry.find(an, java).orElseThrow().score());

        System.out.println("drop=" + registry.drop(an, java));
        System.out.println("An after=" + registry.coursesOf(an));
        System.out.println("Java after=" + registry.studentsOf(java));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnrollmentRegistryDemo.java
java EnrollmentRegistryDemo
~~~

**Stdout:**

~~~text
An=[Java, SQL]
Java=[An, Bình]
score=9
drop=true
An after=[SQL]
Java after=[Bình]
~~~

### Một source of truth cho hai hướng truy vấn

- `Key(Student,Course)` xác định cặp; `computeIfAbsent` không tạo Enrollment thứ hai cho cùng cặp khóa đã có.
- Gọi đăng ký lại `an,java` giữ đối tượng Enrollment cũ, bao gồm điểm 9.
- `coursesOf(an)` và `studentsOf(java)` cùng **đọc entries**; không tồn tại hai collection membership độc lập phải đồng bộ.
- `drop` xóa một cặp. Sau đó **cả hai góc nhìn** đều không còn cặp ấy.
- `LinkedHashMap` giữ thứ tự chèn đã có, giúp stdout có thứ tự ổn định.

Trong ví dụ, `Student` và `Course` không override `equals/hashCode`; record `Key` dùng equality của các component, nên ở đây mỗi object Student/Course được phân biệt theo identity tham chiếu. Với ứng dụng thật cần quản lý nhiều object biểu diễn cùng thực thể, nên dùng **studentId/courseId ổn định** hoặc hợp đồng identity khác phù hợp.

## 15. Vấn đề identity và `equals/hashCode`

Hai `Employee` cùng tên `"An"` chưa chắc là cùng một người. Hai đối tượng Java cùng biểu diễn một hàng database cũng chưa chắc là **cùng tham chiếu `==`**. Vì thế phải quyết định rõ thế nào là một liên kết trùng:

- Dùng **object identity** khi tất cả object được quản lý tập trung trong cùng một aggregate và danh tính tham chiếu chính là danh tính nghiệp vụ ở phạm vi đó.
- Dùng **ID bất biến** khi entity có định danh bền vững.
- Cẩn thận với **equality theo mutable fields** của object trong `HashSet` hoặc dùng làm key `HashMap`.

Ví dụ minh họa dễ sai:

~~~java
@Override
public int hashCode() {
    return mutableName.hashCode();
}
~~~

Đây là **đoạn method minh họa** trong class giả định có field `mutableName`, không phải chương trình độc lập. Nếu `mutableName` đổi sau khi object được đưa vào HashSet, mã băm có thể đổi và set không tìm/xóa được object theo cách dự kiến.

Đối với quan hệ hai chiều, lỗi đó có thể khiến `oldTeam.members.remove(member)` thất bại và để lại stale reference. Đừng đưa mọi field quan hệ vào `equals/hashCode` chỉ vì công cụ có thể sinh mã tự động.

## 16. Tránh vòng lặp trong `toString` và serialization

Quan hệ hai chiều tạo chu trình reference:

~~~text
Employee -> Department -> List<Employee> -> Employee -> ...
~~~

Nếu `Employee.toString()` in `department.toString()`, trong khi `Department.toString()` in toàn bộ `employees` bằng `toString()`, hai method có thể đệ quy vô hạn tới `StackOverflowError`.

Tương tự, serializer không biết xử lý cycle có thể báo lỗi hoặc tạo dữ liệu lặp. Các chiến lược:

- In **ID/tên ngắn** của đầu bên kia thay vì toàn object graph.
- Dùng DTO chuyên cho xuất dữ liệu để xác định rõ chiều đi và độ sâu.
- Dùng ID references, annotations hoặc cấu hình cycle-handling khi thư viện serialization hỗ trợ.
- Không tự động đưa toàn bộ association vào `equals/hashCode`.

**Chu trình reference không đồng nghĩa memory leak.** GC Java có thể thu hồi nhóm object trỏ vòng nhau nếu không còn reachable từ GC roots. Leak thường liên quan tới object còn được giữ bởi root, static collection, listener hoặc cache, không phải chỉ vì A trỏ B và B trỏ A.

## 17. Xóa liên kết khác với xóa object

Ví dụ: khi xóa một Team, có thể chọn chuyển toàn bộ Member sang Team khác, gỡ họ về trạng thái `null`, hoặc từ chối xóa Team còn thành viên.

Với `Order`–`OrderLine` theo composition, chính sách lifecycle có thể yêu cầu dòng đơn hàng thuộc về một Order duy nhất và bị xóa cùng Order. Nhưng **đó là quy tắc nghiệp vụ riêng**, không phải Java suy ra từ việc Order chứa `List<OrderLine>`.

Trước khi viết `remove`, hỏi:

1. Quan hệ có bắt buộc hay có thể null?
2. Xóa link có đồng thời xóa entity không?
3. Có cần kiểm tra quyền/trạng thái trước khi xóa không?
4. Nếu đang có child objects, gỡ, chuyển hay cascade?
5. Các đầu còn lại phải phản ánh trạng thái nào khi thành công?
6. Nếu có nhiều đối tượng, thứ tự xóa và lỗi giữa chừng được xử lý thế nào?

Không nên công bố `getChildren().clear()` như API xóa tổng quát nếu mỗi child còn giữ reference ngược.

## 18. Concurrency: một method không đồng nghĩa atomic

Giả sử Member từ A sang B. Ba thao tác:

~~~text
B thêm Member
A gỡ Member
Member.team = B
~~~

vẫn là những bước riêng. Thread khác có thể quan sát Member trong cả hai danh sách hoặc reference chưa cập nhật. Nếu hai thread cùng chuyển một Member sang các Team khác nhau, kết quả có thể race và mất invariant.

Các hướng giải quyết khi thực sự cần đồng thời:

- Một **aggregate/service lock chung** bảo vệ toàn bộ thao tác đọc–kiểm tra–ghi.
- Nếu khóa nhiều Team, tuân thứ tự khóa nhất quán để tránh deadlock.
- Biểu diễn membership như một snapshot bất biến và công bố một tham chiếu mới theo cơ chế thread-safe.
- Đưa consistency liên quan dữ liệu bền vững vào database transaction và constraints.

Chỉ thêm `synchronized` ở `Team.add` không đủ nếu `Team.remove` hay API khác sửa cùng state qua lock khác. Các ví dụ runnable ở bài là **mô hình tuần tự**, không tuyên bố thread-safe.

## 19. ORM/JPA và khái niệm owning side

Với database, quan hệ hai chiều có hai lớp nhất quán:

- **Object graph trong Java:** tham chiếu và collection ở hai bên phải phù hợp.
- **Trạng thái lưu trữ:** foreign key/join table phải được ghi/commit theo giao dịch.

Một số ORM/JPA mappings có **owning side** và **inverse side**. Nếu foreign key thực chất được quản lý từ `Employee.department`, chỉ `Department.employees.add(employee)` có thể **không đủ** để thay đổi foreign key như mong muốn; phụ thuộc mapping và provider.

Helper domain nên đồng bộ **cả hai phía của object graph** theo quy tắc của mô hình, đồng thời đảm bảo phía ORM dùng để ghi persistence được đặt đúng. Database transaction/foreign key không tự sửa những Java object reference đã bị lệch trong memory.

**Không nhầm owning side của ORM với composition/lifecycle ownership.** Chúng là những khái niệm khác nhau: một bên là chính sách mapping dữ liệu, bên kia là quyết định thiết kế miền.

## 20. Kiểm thử quan hệ theo ma trận

| Ca | Khởi đầu | Lệnh | Kết quả phải kiểm tra |
| --- | --- | --- | --- |
| T1 | Member chưa thuộc team | `A.add(m)` | A chứa m và m.team=A |
| T2 | m thuộc A | `A.add(m)` | Không duplicate |
| T3 | m thuộc A | `B.add(m)` | A gỡ, B có, m.team=B |
| T4 | m thuộc B | `A.remove(m)` | B không bị ảnh hưởng |
| T5 | m thuộc B | `B.remove(m)` | B gỡ, m.team=null |
| T6 | m đã rời | Rời lần nữa | Không đổi nếu hợp đồng idempotent |
| T7 | Team đích hết chỗ | Thử chuyển | Phải giữ team cũ |
| T8 | Caller nhận danh sách | Cố xóa phần tử | Không sửa trực tiếp membership |
| T9 | A↔B và C↔D | A ghép C | B và D đều được gỡ |
| T10 | Student đã học Course | Đăng ký lại | Không thêm Enrollment trùng |
| T11 | Enroll Student–Course | Drop | Hai hướng truy vấn cùng mất cặp |
| T12 | Tham số null/invalid | Gọi API | Bị từ chối trước cập nhật |

Nên kiểm tra **cả chiều thuận và chiều ngược** của từng trạng thái. Nếu Team A không chứa m nữa, nhưng `m.team` vẫn trỏ A thì chưa đạt. Nếu trả về `List` chỉ đọc mà object phần tử có thể bị sửa để phá association, cũng chưa bảo vệ đầy đủ.

### Một đoạn kiểm thử JDK thuần

Giả định test có quyền quan sát một API đọc-only cho member/team:

~~~java
if (member.team() != expectedTeam) {
    throw new AssertionError("member trỏ sai team");
}
if (!expectedTeam.members().contains(member)) {
    throw new AssertionError("team thiếu member");
}
~~~

Đây là **đoạn minh họa theo API giả định**, không phải tệp độc lập: `team()` và `members()` phải được định nghĩa nếu dùng lại. Nếu viết test bằng JUnit, có thể dùng `assertSame`, `assertTrue` và `assertEquals`, nhưng cần dependency JUnit.

Điều quan trọng không phải framework test, mà là **kiểm tra tất cả invariant sau mỗi thao tác**, kể cả sau thất bại.

## 21. Những lỗi dễ gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ sửa `employee.department` | Phòng cũ/mới không được cập nhật | Một API chỉnh hai phía |
| Chỉ thêm vào `department.employees` | Employee chưa biết phòng | Đồng bộ tham chiếu ngược |
| Quên gỡ ở phòng cũ | Một Member ở hai phòng | Chuyển liên kết có kiểm tra |
| Xóa từ phòng sai mà xóa field của member | Phá quan hệ đúng với phòng khác | Kiểm tra ownership trước xóa |
| Caller tự `clear()` collection | Xóa chỉ một phía | Không trả collection mutable nội bộ |
| Add lặp nhưng List có duplicate | Duyệt, đếm, remove sai | Chống trùng bằng kiểm tra/Set/ID |
| Xóa nguồn rồi mới validate đích | Thất bại làm mất liên kết cũ | Kiểm tra trước khi đổi |
| Hai method cập nhật ở hai lớp không ủy quyền | Logic trôi khác nhau | Một đầu mối thuật toán |
| `equals/hashCode` phụ thuộc field mutable | HashSet/HashMap không tìm được phần tử | ID ổn định hoặc identity |
| `toString` in toàn bộ quan hệ qua lại | Đệ quy vô hạn | In ID, DTO, giới hạn traversal |
| Gộp xóa link với xóa entity | Xóa dữ liệu trái nghiệp vụ | Quy tắc lifecycle riêng |
| Một method nhiều phép gán được coi là atomic | Thread quan sát trạng thái lệch | Đồng bộ/transaction |
| ORM cập nhật một phía rồi cho rằng đã đồng bộ | Object graph hoặc FK có thể sai | Helper hai chiều, mapping rõ |
| Không test lệnh chuyển, xóa lặp, lỗi | Bug chỉ xuất hiện muộn | Test cả trạng thái trước/sau |

## 22. Bài tập tự luyện

**Bài 1.** `e.department=D` thì collection của D phải có quan hệ gì với e? Nếu e không thuộc phòng, những collection khác phải ra sao?

**Bài 2.** Vì sao gọi `e.setDepartment(B)` đơn lẻ không đủ khi e đang ở A? Nêu ba thay đổi.

**Bài 3.** E thuộc B nhưng A được gọi `remove(E)`. Có được đặt `E.department=null` không?

**Bài 4.** Gọi `add(E)` lần hai lên Team đang chứa E. API nên tránh điều gì?

**Bài 5.** Nếu dùng `HashSet<Employee>`, vì sao đổi trường tham gia tính hash khi object đang trong Set có thể làm `remove` thất bại?

**Bài 6.** `Department.getEmployees()` trả `ArrayList` nội bộ. Caller có thể phá quan hệ bằng những thao tác nào? Đề xuất phương thức an toàn.

**Bài 7.** Hai cặp A↔B, C↔D chuyển thành A↔C. B và D phải trỏ ai?

**Bài 8.** Nếu quan hệ yêu cầu Member thuộc **đúng một Team**, method `leave()` đặt null có phù hợp không?

**Bài 9.** Enrollment lưu `score`. Vì sao không đặt điểm duy nhất vào `Student` hoặc `Course`?

**Bài 10.** Registry theo `Key(Student,Course)` dùng object identity có hạn chế gì khi cùng một student được load thành hai Java objects?

**Bài 11.** Khi Team B đã đầy, vì sao không gỡ Member khỏi A trước khi kiểm tra B?

**Bài 12.** Việc có `synchronized` trên mỗi `Team.add` riêng lẻ có chắc làm thao tác chuyển giữa A, B và Member atomic không?

**Bài 13.** ORM/JPA có owning side. Vì sao thay đổi inverse collection có thể chưa đủ để ghi foreign key?

**Bài 14.** Nếu `toString` của hai phía cùng in toàn bộ đối tượng kia, lỗi có thể xuất hiện là gì?

### Đáp án tham khảo

1. D chứa e đúng một lần và e trỏ đúng D; nếu e.department=null, không phòng nào trong phạm vi quản lý còn giữ e.
2. Xóa e khỏi A, thêm vào B, cập nhật `e.department=B`.
3. Không. A không sở hữu liên kết hiện tại và không được phá quan hệ của B.
4. Tránh tạo duplicate; có thể trả false hoặc không thay đổi.
5. Hash bucket của Set được chọn từ hash ban đầu, giá trị hash đổi làm tra cứu/xóa thiếu ổn định.
6. `clear`, `remove`, `add` có thể sửa một phía; trả snapshot/read-only view/projection và API hành vi.
7. B.peer=null, D.peer=null, A.peer=C, C.peer=A.
8. Không nếu trạng thái null bị cấm; cần chuyển thẳng hoặc thao tác nghiệp vụ khác.
9. Điểm thuộc một **cặp Student–Course**; Enrollment là nơi tự nhiên giữ dữ liệu quan hệ.
10. Hai instance khác nhau có thể sinh hai Key khác nhau dù biểu diễn cùng thực thể; dùng ID ổn định/chiến lược identity phù hợp.
11. B có thể từ chối, và Member sẽ mất quan hệ cũ; validate đích trước thay đổi.
12. Không chắc. Phải bảo vệ **toàn bộ** chuỗi trên các object và tránh thứ tự khóa gây deadlock.
13. Vì ORM dựa trên mapping/owning side khi xác định thay đổi persistence; cần đồng bộ object graph và mapping đúng.
14. `StackOverflowError` do đệ quy qua lại không kết thúc.

## 23. Checklist thiết kế API quan hệ hai chiều

- Có thật sự cần lưu **hai phía**, hay một phía/registry đủ?
- Multiplicity là `0..1`, `1`, `0..*` hay `1..*`?
- Có được phép rời nhóm không? Có quy tắc chuyển?
- Ai sở hữu thuật toán thêm/xóa/chuyển?
- Các method công khai có ủy quyền về **một nguồn thực thi** không?
- Có check duplicate và chống xóa sai phía?
- Có kiểm tra toàn bộ điều kiện trước khi thay đổi state không?
- Nếu thất bại, có giữ nguyên state theo hợp đồng?
- Có lộ mutable list/set qua getter không?
- `equals/hashCode` có dựa vào những field mutable không?
- Có `toString` hoặc serialization đi vào chu trình không?
- Xóa link và xóa object có bị trộn lẫn không?
- Nếu đa luồng, toàn bộ invariant được bảo vệ bởi cơ chế nào?
- Nếu có ORM, object graph và persistence mapping có được đồng bộ không?
- Test có kiểm tra **cả hai phía** của thêm, xóa, chuyển và các trường hợp lỗi không?

## 24. Tài liệu đối chiếu

- [Java SE 17 — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): thao tác trên danh sách, `List.copyOf`, `equals`.
- [Java SE 17 — Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): uniqueness theo `equals/hashCode`.
- [Java SE 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): registry ánh xạ khóa sang Enrollment.
- [Java SE 17 — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `requireNonNull`.
- [Java SE 17 — Object.equals/hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): quy tắc so sánh và hash.
- [Java SE 17 — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): trả danh sách không hỗ trợ phép sửa.
- [Java Language Specification 17, §8](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): khai báo class, field, methods và nested classes.
- [Java Language Specification 17, §17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): các vấn đề thread/lock và visibility của state mutable.

**Kết luận:** Quan hệ hai chiều cho phép điều hướng thuận tiện nhưng đòi **một bất biến mô tả cả hai hướng**. Không để caller tự sửa tham chiếu/collection từng phần; hãy dùng một API hành vi để **thêm, xóa hoặc chuyển liên kết** đồng bộ, xử lý lặp và thất bại rõ ràng, bảo vệ mutable collections và kiểm thử cả hai phía. Với nhiều–nhiều hoặc quan hệ có thuộc tính riêng, association object/registry làm **nguồn sự thật duy nhất** thường giảm sự trùng lặp trạng thái. Khi chuyển từ mô hình tuần tự sang đa luồng hoặc database, cần synchronization/transaction đúng phạm vi, không thể dựa vào riêng `private` hay một method nhiều dòng.
