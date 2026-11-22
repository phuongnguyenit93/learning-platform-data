# Kiểm thử kế thừa, thay đổi trạng thái và độc lập sau sao chép

## 1. Vì sao ba nhóm kiểm thử này thuộc hợp đồng đối tượng?

Khi triển khai các phương thức của `Object` hoặc xây dựng một lớp có ngữ nghĩa giá trị, cần kiểm chứng hành vi của đối tượng **trong nhiều tình huống**, không chỉ trường hợp hai đối tượng có dữ liệu giống nhau. Ba nhóm trường hợp dễ làm lộ lỗi là:

1. **Kế thừa:** lớp con bổ sung thuộc tính hay thay đổi `equals()`/`hashCode()` có thể phá tính đối xứng, bắc cầu hoặc quan hệ giữa hai phương thức.
2. **Thay đổi trạng thái:** một đối tượng đổi thuộc tính sau khi tạo có thể thay đổi kết quả so sánh và mã băm; điều này đặc biệt nguy hiểm nếu đối tượng đang là khóa của `HashMap` hoặc phần tử của `HashSet`.
3. **Sao chép:** đối tượng mới có thể chỉ là một bản sao nông, vẫn dùng chung danh sách hoặc đối tượng con với bản gốc. Kiểm thử phải xác định rõ mức độ độc lập mà API cam kết.

Không có một hợp đồng duy nhất buộc **mọi** lớp phải so sánh theo giá trị hoặc phải sao chép sâu toàn bộ đồ thị đối tượng. Trước khi viết test, phải xác định lớp mang **identity** hay **value semantics**, các thuộc tính nào tham gia `equals()`/`hashCode()`, trường nào được phép thay đổi, và tài liệu API hứa chia sẻ hay sao chép trạng thái nào.

## 2. Những bất biến cần kiểm chứng

Với các tham chiếu không null `x`, `y`, `z`, hợp đồng của `Object.equals()` yêu cầu:

| Thuộc tính | Phép kiểm | Ý nghĩa |
| --- | --- | --- |
| Phản xạ | `x.equals(x)` là `true` | Một đối tượng bằng chính nó |
| Đối xứng | `x.equals(y) == y.equals(x)` | Đổi chiều so sánh không đổi kết quả |
| Bắc cầu | Nếu `x.equals(y)` và `y.equals(z)`, thì `x.equals(z)` | Ba đối tượng tương đương nhất quán |
| Nhất quán | Nhiều lần so sánh cho cùng kết quả khi trạng thái liên quan không đổi | Không phát sinh kết quả bất ngờ |
| Khác null | `x.equals(null)` là `false` | Không coi null là một đối tượng bình thường |

Quan hệ giữa `equals()` và `hashCode()`:

- Nếu `x.equals(y)` là `true`, **bắt buộc** `x.hashCode() == y.hashCode()`.
- Hai đối tượng không bằng nhau **vẫn có thể** có cùng hash code; không viết test yêu cầu mã băm của mọi giá trị khác nhau đều khác nhau.
- Nếu trạng thái liên quan tới `equals()` không đổi, các lần gọi `hashCode()` trong cùng một lần chạy phải nhất quán. Giá trị hash code không nhất thiết giữ nguyên giữa các lần chạy JVM khác nhau.

Cần kiểm thử cả **trường hợp phủ định** (khác kiểu, khác thuộc tính có ý nghĩa, giá trị null phù hợp). Trường hợp thành công riêng lẻ không chứng minh hợp đồng đúng với toàn bộ không gian đầu vào, nên chọn tập dữ liệu đại diện, các trường hợp biên và trường hợp kế thừa.

Với sao chép, hãy kiểm riêng các tính chất:

- **Không cùng tham chiếu:** `copy != original`.
- **Dữ liệu ban đầu đúng:** nội dung copy giống dữ liệu được hứa sao chép; nếu lớp dùng value equality thì có thể kiểm `copy.equals(original)` ban đầu.
- **Độc lập sau sửa đổi:** thay đổi thành phần mutable ở một bên không làm thay đổi bên kia **nếu** API cam kết copy độc lập. Kiểm tra cả chiều sửa original lẫn chiều sửa copy.
- **Tính toàn vẹn của quan hệ chia sẻ có chủ ý:** nếu tài liệu quy định một thành phần dùng chung, cần kiểm tra sự chia sẻ đó thay vì mặc nhiên coi là lỗi.

## 3. Kiểm thử kế thừa: bẫy đối xứng và bắc cầu

### 3.1. Lớp cha dùng `instanceof`, lớp con thêm trường có nghĩa

Giả sử `BaseKey` chỉ lưu `id` và coi mọi đối tượng thuộc `BaseKey` hoặc lớp con có cùng `id` là bằng nhau:

```java
@Override
public boolean equals(Object other) {
    return other instanceof BaseKey key && id == key.id;
}
```

Sau đó `TaggedKey extends BaseKey` thêm trường `tag`, và `equals()` của lớp con yêu cầu cả `id` và `tag` bằng nhau.

Khi đó, với `base = new BaseKey(7)` và `child = new TaggedKey(7, "red")`:

```text
base.equals(child)  → true
child.equals(base)  → false
```

Tính đối xứng đã hỏng. Nếu lớp con tính hash cả `tag`, cặp đối tượng mà lớp cha coi là bằng nhau còn có thể có mã băm khác nhau, vi phạm quy tắc hash. Chỉ kiểm `child.equals(base)` mà quên kiểm chiều ngược sẽ bỏ sót lỗi.

### 3.2. Cố sửa đối xứng nhưng làm hỏng bắc cầu

Một giải pháp thiếu an toàn là: lớp con bỏ qua `tag` khi so sánh với lớp cha, nhưng so sánh `tag` khi hai phía đều là lớp con. Xét:

- `red = TaggedKey(7, "red")`
- `base = BaseKey(7)`
- `blue = TaggedKey(7, "blue")`

Nếu hai lớp được viết để `red.equals(base)` và `base.equals(blue)` đều đúng, nhưng `red.equals(blue)` sai, hợp đồng **bắc cầu** bị phá vỡ. Một test với bộ ba này sẽ phát hiện lỗi mà kiểm thử từng cặp giống kiểu không nhận ra.

Không thể tùy tiện bổ sung thành phần giá trị ở lớp con trong khi lớp cha vẫn cho phép so sánh ngang kiểu mà luôn giữ được các quy tắc `equals()`. Cách thiết kế phù hợp tùy miền dữ liệu:

- Dùng lớp giá trị `final` để không cho lớp con thay đổi ý nghĩa equality.
- Dùng **composition** để thêm metadata, thay vì kế thừa một lớp giá trị đã có equality.
- Dùng `getClass()` để equality chỉ hoạt động giữa hai đối tượng có cùng runtime class, nếu ngữ nghĩa miền chấp nhận sự phân biệt này; khi lớp con override thì vẫn phải duy trì hợp đồng.
- Một số hierarchy dùng giao thức `canEqual` được thiết kế cẩn thận; không mặc định đổi `instanceof` sang `getClass()` là phù hợp với mọi ứng dụng.

Test cần mô tả **quyết định thiết kế về cross-type equality**: một lớp cha và lớp con cùng dữ liệu có *được phép* bằng nhau không? Nếu không, kiểm `!parent.equals(child)` và `!child.equals(parent)`. Nếu có, kiểm đủ các quy tắc và các cặp/bộ ba lớp con khác nhau, thay vì kiểm từng override độc lập.

## 4. Kiểm thử thay đổi trạng thái

### 4.1. Trạng thái tham gia equality và hash

Một lớp mutable có thể tính `equals()`/`hashCode()` từ trường thay đổi được. Việc kết quả hai hàm thay đổi theo trạng thái tự nó không nhất thiết vi phạm hợp đồng: hợp đồng nhất quán áp dụng **khi thông tin dùng trong phép so sánh không bị sửa đổi**.

Tuy nhiên, đưa một đối tượng vào `HashSet` hoặc làm khóa `HashMap` rồi sửa trường tham gia mã băm có thể khiến tìm kiếm thất bại: đối tượng được đặt theo hash cũ, trong khi lần tìm sau dùng hash mới. Với những cấu trúc này, tốt nhất dùng **khóa bất biến**.

Một kiểm thử giá trị nên diễn ra qua các mốc:

1. Tạo `a` và `b` cùng giá trị; xác nhận `a.equals(b)` và hash bằng nhau.
2. Sửa trường tham gia equality trên `a`; xác nhận phép so sánh phản ánh giá trị mới.
3. Sửa `b` sang cùng giá trị mới; xác nhận hai đối tượng lại bằng nhau và hash bằng nhau.
4. Nếu trường có thể trở lại giá trị cũ, kiểm kết quả cũng trở lại như thiết kế.
5. Nếu lớp được dùng trong hash collection, kiểm hoặc quy định **không sửa khóa sau khi chèn**, hoặc dùng một thiết kế khóa bất biến; không biến lỗi tra cứu thành kỳ vọng chức năng của ứng dụng.

Phân biệt **mutable field dùng để hiển thị** với **field tham gia logical identity**. Chỉ kiểm rằng hash thay đổi với mọi setter có thể sai: nếu một thuộc tính không thuộc equality, nó thường **không nên** làm thay đổi hash.

### 4.2. Trạng thái kế thừa

Nếu lớp con có thêm trường mutable tham gia equality, kiểm các chuyển trạng thái ở **cả trường lớp cha lẫn lớp con**, với nhiều đối tượng cùng lớp con. Đảm bảo override `hashCode()` theo đúng những thành phần `equals()` sử dụng. Không cần giả định mọi lớp con đều được phép mở rộng equality; có trường metadata không tham gia equality.

## 5. Kiểm thử tính độc lập sau sao chép

### 5.1. Sao chép nông và sao chép sâu

Với đối tượng `Profile` chứa `Address` và `List<String>` mutable:

```text
Original Profile ── address ──> Address("Hue")
                 └─ skills  ──> ["java"]

Shallow copy     ── address ──> cùng Address
                 └─ skills  ──> cùng List

Deep copy        ── address ──> Address mới ("Hue")
                 └─ skills  ──> List mới ["java"]
```

Một bản sao nông có thể tạo ra **đối tượng ngoài mới** nhưng vẫn chia sẻ tham chiếu đến các đối tượng con. Vì thế chỉ kiểm `assertNotSame(original, copy)` là chưa đủ.

Bản sao sâu không bắt buộc nhân bản mọi đối tượng bất biến như `String`, và thường không nên sao chép các resource như socket, lock hoặc thread. Mức độ sâu phụ thuộc **hợp đồng của lớp** và ranh giới ownership, đặc biệt khi đồ thị có vòng tham chiếu hoặc các phần tử được chia sẻ chủ ý.

### 5.2. Ma trận kiểm thử độc lập

| Thao tác | Bản sao nông chia sẻ tham chiếu | Bản sao sâu đúng hợp đồng |
| --- | --- | --- |
| Sửa `original.address.city` | `shallow.address.city` thay đổi theo | `deep.address.city` không đổi |
| Thêm phần tử vào `original.skills` | `shallow.skills` nhìn thấy phần tử mới | `deep.skills` không thay đổi |
| Sửa `deep.address.city` | Không liên quan | `original.address.city` không đổi |
| Thêm vào `deep.skills` | Không liên quan | `original.skills` không đổi |
| So sánh object ngoài | Bản sao khác tham chiếu với original | Bản sao khác tham chiếu với original |
| So sánh object con mutable | Có thể **cùng** tham chiếu | Phải **khác** tham chiếu nếu cam kết copy độc lập |

Nếu API dùng `clone()` theo `Object.clone()`, nhớ rằng hành vi mặc định sao chép các field và **không tự deep-copy đối tượng được tham chiếu**. Một lớp có thể cần override `clone()`, copy constructor hoặc factory để sao chép sâu có kiểm soát. Không đánh đồng việc implement `Cloneable` với bảo đảm toàn bộ trạng thái độc lập.

## 6. Ví dụ Java 17+ chạy độc lập: phát hiện lỗi và kiểm chứng hành vi

Ví dụ cố ý đặt một lớp equality bị lỗi để **test phát hiện lỗi**; các kiểm thử còn lại minh họa cách xác minh thiết kế đúng. Lưu mã thành tệp `ObjectContractVerification.java`.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class ObjectContractVerification {
    // Thiết kế lỗi: lớp cha xem lớp con cùng id là bằng nhau.
    static class BaseKey {
        final int id;

        BaseKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BaseKey key && id == key.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    static final class TaggedKey extends BaseKey {
        final String tag;

        TaggedKey(int id, String tag) {
            super(id);
            this.tag = tag;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof TaggedKey key
                    && super.equals(key)
                    && tag.equals(key.tag);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + tag.hashCode();
        }
    }

    // Thiết kế nhất quán: chỉ so sánh value object cùng runtime class.
    static class StrictKey {
        final int id;

        StrictKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other != null
                    && getClass() == other.getClass()
                    && id == ((StrictKey) other).id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    static final class StrictTaggedKey extends StrictKey {
        final String tag;

        StrictTaggedKey(int id, String tag) {
            super(id);
            this.tag = tag;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof StrictTaggedKey key
                    && super.equals(key)
                    && tag.equals(key.tag);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + tag.hashCode();
        }
    }

    static final class MutableKey {
        String code;

        MutableKey(String code) {
            this.code = code;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key
                    && Objects.equals(code, key.code);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(code);
        }
    }

    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Profile {
        final String name;
        final Address address;
        final List<String> skills;

        Profile(String name, Address address, List<String> skills) {
            this.name = name;
            this.address = address;
            this.skills = skills;
        }

        Profile shallowCopy() {
            return new Profile(name, address, skills);
        }

        Profile deepCopy() {
            return new Profile(
                    name,
                    new Address(address.city),
                    new ArrayList<>(skills)
            );
        }
    }

    public static void main(String[] args) {
        BaseKey parent = new BaseKey(7);
        TaggedKey child = new TaggedKey(7, "red");
        boolean badSymmetry = parent.equals(child) == child.equals(parent);
        System.out.println("Broken inheritance symmetry valid: " + badSymmetry);

        StrictKey strictParent = new StrictKey(7);
        StrictTaggedKey s1 = new StrictTaggedKey(7, "red");
        StrictTaggedKey s2 = new StrictTaggedKey(7, "red");
        StrictTaggedKey s3 = new StrictTaggedKey(7, "red");

        boolean strictSymmetry =
                strictParent.equals(s1) == s1.equals(strictParent);
        boolean transitive =
                s1.equals(s2) && s2.equals(s3) && s1.equals(s3);
        boolean equalHash =
                s1.equals(s2) && s1.hashCode() == s2.hashCode();

        System.out.println("Strict inheritance symmetry valid: " + strictSymmetry);
        System.out.println("Strict value transitivity valid: " + transitive);
        System.out.println("Equal strict values share hash: " + equalHash);

        MutableKey first = new MutableKey("A");
        MutableKey second = new MutableKey("A");
        boolean equalBefore = first.equals(second);
        int initialHash = first.hashCode();

        Set<MutableKey> set = new HashSet<>();
        set.add(first);
        first.code = "B";

        System.out.println("Mutable values equal before: " + equalBefore);
        System.out.println("Mutable values equal after: " + first.equals(second));
        System.out.println("Mutable hash changed: "
                + (first.hashCode() != initialHash));
        System.out.println("Mutated key found in HashSet: " + set.contains(first));

        Profile original = new Profile(
                "Mai", new Address("Hue"), new ArrayList<>(List.of("java")));
        Profile shallow = original.shallowCopy();
        Profile deep = original.deepCopy();

        original.address.city = "Da Nang";
        original.skills.add("spring");

        System.out.println("Shallow shares nested state: "
                + (shallow.address.city.equals("Da Nang")
                && shallow.skills.contains("spring")));
        System.out.println("Deep preserves initial state: "
                + (deep.address.city.equals("Hue")
                && deep.skills.equals(List.of("java"))));
        System.out.println("Deep owns separate mutable references: "
                + (deep.address != original.address
                && deep.skills != original.skills));

        deep.address.city = "Ha Noi";
        deep.skills.add("testing");

        System.out.println("Reverse mutation independent: "
                + (original.address.city.equals("Da Nang")
                && original.skills.equals(List.of("java", "spring"))));
    }
}
```

Biên dịch và chạy:

```bash
javac ObjectContractVerification.java
java ObjectContractVerification
```

Đầu ra trên OpenJDK/Java 17 với mã ví dụ trên:

```text
Broken inheritance symmetry valid: false
Strict inheritance symmetry valid: true
Strict value transitivity valid: true
Equal strict values share hash: true
Mutable values equal before: true
Mutable values equal after: false
Mutable hash changed: true
Mutated key found in HashSet: false
Shallow shares nested state: true
Deep preserves initial state: true
Deep owns separate mutable references: true
Reverse mutation independent: true
```

**Diễn giải kết quả:**

- Dòng đầu là `false` **có chủ đích** để chứng minh test bắt được một lớp thiết kế sai. Không được coi đó là kết quả mong muốn của một triển khai sản xuất.
- Với `StrictKey`, lớp cha và con không bao giờ bằng nhau khác runtime class; hai đối tượng `StrictTaggedKey` có `id`/`tag` giống nhau vẫn bằng nhau và có cùng hash. Đây là **một lựa chọn thiết kế**, không phải cách duy nhất giải quyết equality trong kế thừa.
- Sau khi đổi `"A"` thành `"B"`, `MutableKey` đổi hash; trên `HashSet` của Java 17, lookup trong ví dụ này trả về `false`. Đây là minh họa nguy cơ do phá giả định về hash key ổn định, **không phải** một lời hứa rằng mọi hash collection hay mọi cặp giá trị sẽ luôn trả `false` sau mọi lần sửa.
- Bản sao nông nhìn thấy thay đổi ở `Address` và `List`, trong khi bản sao sâu giữ giá trị ban đầu và cũng không ảnh hưởng original khi được thay đổi ở chiều ngược lại.

Lưu ý ví dụ kiểm thử một số trường hợp đại diện và in kết quả để quan sát. Trong test suite thật, hãy dùng assertion để **fail ngay khi hợp đồng mong đợi bị phá**, đồng thời lưu các ca lỗi có chủ đích thành test xác minh bug thay vì test thành công của sản phẩm.

## 7. Chuyển thành kiểm thử tự động có assertion

Một helper không phụ thuộc thư viện ngoài có thể khẳng định các đặc tính quan trọng (đặt trong lớp test):

```java
static void checkEqualityContract(Object a, Object b, Object c) {
    if (!a.equals(a) || !b.equals(b) || !c.equals(c)) {
        throw new AssertionError("Reflexivity failed");
    }
    if (a.equals(null) || b.equals(null) || c.equals(null)) {
        throw new AssertionError("Null equality failed");
    }
    if (a.equals(b) != b.equals(a)
            || b.equals(c) != c.equals(b)
            || a.equals(c) != c.equals(a)) {
        throw new AssertionError("Symmetry failed");
    }
    if (a.equals(b) && b.equals(c) && !a.equals(c)) {
        throw new AssertionError("Transitivity failed");
    }
    if (a.equals(b) && a.hashCode() != b.hashCode()) {
        throw new AssertionError("Equal objects have different hashes");
    }
}
```

Đây là **đoạn helper minh họa**, không phải một chương trình Java độc lập. Nó chỉ kiểm đúng các đối tượng được truyền vào, nên vẫn cần chọn dữ liệu phản ánh cấu trúc kế thừa và các trạng thái quan trọng. Trong JUnit 5 có thể thay bằng `assertEquals`, `assertFalse`, `assertNotSame` và `assertAll`; kiểm thử equality đặc biệt nên bao gồm ba đối tượng và cả hai chiều so sánh.

Với code có `clone()` hoặc copy constructor, một test tốt thường theo dạng:

1. Tạo object chứa **ít nhất hai tầng tham chiếu mutable**, không chỉ chuỗi/primitive.
2. Sao chép và so sánh dữ liệu lúc ban đầu; phân biệt `same object` với `same value`.
3. Sửa nested state bản gốc, khẳng định bản sao vẫn đúng theo hợp đồng.
4. Sửa nested state bản sao, khẳng định bản gốc vẫn đúng.
5. Nếu có collection, sửa cả **cấu trúc** (thêm/xóa) và **phần tử mutable bên trong**, vì sao chép một `ArrayList` mới vẫn có thể dùng chung các phần tử trong danh sách.
6. Với kiểu có equality theo giá trị, thử `equals()`/`hashCode()` trước và sau các thay đổi; không so sánh hash giữa hai trạng thái khác nhau như một bất biến.

## 8. Các lỗi kiểm thử hay bỏ sót

| Thiếu sót | Hậu quả | Bổ sung |
| --- | --- | --- |
| Chỉ gọi `parent.equals(child)` | Bỏ sót đối xứng bị phá ở chiều ngược | Kiểm cả hai chiều |
| Chỉ kiểm hai đối tượng | Bỏ sót vi phạm bắc cầu qua đối tượng thứ ba | Tạo bộ ba đại diện |
| Cho rằng hai hash khác nhau khi hai object không bằng nhau | Đặt yêu cầu sai với `hashCode()` | Chỉ bắt buộc hash bằng khi `equals()` là `true` |
| Chỉ thử trạng thái ban đầu | Không bắt được lỗi khi field mutable đổi | Test chuyển trạng thái |
| Sửa hash key ngay trong `HashMap` rồi đổ lỗi collection | Bỏ qua điều kiện sử dụng khóa có hash ổn định | Đóng băng khóa hoặc không sửa sau khi chèn |
| Chỉ kiểm `copy != original` | Không phát hiện alias của nested mutable fields | Kiểm tham chiếu con và thay đổi hai chiều |
| Chỉ copy lại container danh sách | Các phần tử mutable có thể còn dùng chung | Kiểm sâu tới tầng cần độc lập |
| Bắt buộc mọi bản copy phải `equals(original)` | Sai nếu lớp định nghĩa equality theo identity | Xác nhận ngữ nghĩa equality trước |
| Coi `clone()` mặc định là deep copy | Sao chép shallow làm lộ shared state | Đọc hợp đồng và viết test tương ứng |
| Chỉ test một subclass | Khó phát hiện cross-type equality sai khi hierarchy mở rộng | Test nhiều kiểu runtime và cặp/triple tương ứng |

## 9. Tiêu chí hoàn thành

Một bộ kiểm chứng đáng tin cho hợp đồng đối tượng cần trả lời được:

- **Kế thừa:** Đối tượng lớp cha/lớp con có được bằng nhau không, và hai chiều so sánh có thống nhất không? Bộ ba đối tượng có bảo đảm tính bắc cầu? Hash có đồng nhất khi equals đúng?
- **Trạng thái:** Field nào tạo nên logical identity? Setter nào được phép làm thay đổi equality/hash? Có đang dùng một key mutable trong hash collection không?
- **Sao chép:** Bản sao nông hay sâu theo hợp đồng? Mức nào của đồ thị mutable cần độc lập? Thay đổi ở **cả hai chiều** có tác động ngoài ý muốn không?

Từ các câu trả lời đó, hãy xây test dùng assertion và dữ liệu đại diện cho từng quyết định thiết kế. **Không suy ra tính đúng từ một phép so sánh thành công hay một bản sao có tham chiếu ngoài khác nhau**: chính các tình huống kế thừa, đổi trạng thái và chia sẻ tham chiếu mới thường phơi bày lỗ hổng trong hợp đồng.
