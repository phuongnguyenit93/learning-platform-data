# Trả về đối tượng mới thay cho cập nhật đối tượng cũ trong Java

Một đối tượng **bất biến (immutable)** không cho phép trạng thái logic của chính nó thay đổi sau khi xây dựng hoàn chỉnh. Vì vậy, khi nghiệp vụ yêu cầu “tăng số lượng”, “đổi địa chỉ”, “chuyển trạng thái”, “thêm sản phẩm” hoặc “cập nhật cấu hình”, cách tiếp cận tự nhiên là **trả về một đối tượng mới chứa kết quả**, thay vì sửa object đang tồn tại.

Ví dụ, thay vì viết `account.setBalance(newBalance)` hay `point.translateInPlace(dx, dy)`, một API có thể công bố `Account deposit(amount)` và `Point movedBy(dx, dy)`: caller nhận kết quả mới; bản gốc giữ nguyên. Hai phiên bản có thể tồn tại đồng thời để so sánh, lưu lịch sử hoặc chia sẻ an toàn hơn.

Đây không chỉ là thay setter bằng tên khác. Để có ý nghĩa thật, phương thức trả object mới cần **giữ invariant**, **không rò rỉ tham chiếu mutable**, định nghĩa rõ trường hợp không thay đổi, xử lý phép tính lỗi mà không cập nhật dở dang, và khiến caller nhận thức rằng cần **sử dụng giá trị trả về**.

Bài thuộc **Java core – class-object**, phần **Lớp bất biến**. Những ví dụ là chương trình Java **17+** có thể biên dịch độc lập; mã minh họa không hoàn chỉnh được ghi rõ.

## 1. Mục tiêu học tập

Sau bài này, bạn cần giải thích và tự thực hành được:

- Vì sao sửa một object dùng chung có thể tạo side effect khó phát hiện.
- Cách thiết kế method kiểu `withX`, `plus`, `minus`, `movedBy`, `withAddedItem` trả đối tượng mới.
- Điểm khác nhau giữa **object identity**, **value equality** và **trạng thái logic bất biến**.
- Cách đặt validation trong constructor/factory để mọi phiên bản mới hợp lệ.
- Lý do collection hoặc object con mutable có thể phá immutable design dù lớp ngoài trả object mới.
- Cách cập nhật list/map theo kiểu **copy-on-write ở mức API**, và phân biệt nó với concurrency collection `CopyOnWriteArrayList`.
- Cách kết hợp nhiều phép biến đổi, xây dựng lịch sử/undo và kiểm thử non-mutation.
- Giới hạn về cấp phát, hiệu năng, lifecycle entity, atomicity và đa luồng.

## 2. Mutation và immutable update là hai hợp đồng khác nhau

**Mutable API** sửa object nhận lời gọi:

~~~java
class MutablePoint {
    int x;
    int y;

    void moveBy(int dx, int dy) {
        x += dx;
        y += dy;
    }
}
~~~

Đây là class minh họa: caller gọi `point.moveBy(2,3)` thì **chính point cũ đổi tọa độ**. Nếu hai biến cùng trỏ point, cả hai cùng quan sát thay đổi.

**Immutable-update API** tạo kết quả khác:

~~~java
record Point(int x, int y) {
    Point movedBy(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}
~~~

Đây là record hợp lệ Java 17. `Point newPoint = oldPoint.movedBy(2,3)` cho một giá trị mới; `oldPoint` không bị sửa. Các component primitive của record này bất biến, và method không có lối sửa state.

Điểm phân biệt phải nêu trong tài liệu API:

| Thuộc tính | Mutable update | Trả object mới |
| --- | --- | --- |
| Receiver sau lời gọi | Đã đổi state | Giữ state cũ |
| Dữ liệu trả về | Thường `void` hoặc kết quả phụ | Object chứa state mới |
| Alias cùng object | Quan sát mutation | Tiếp tục quan sát bản cũ |
| Lịch sử trạng thái | Phải tự chụp snapshot | Có thể giữ nhiều phiên bản |
| Validation thất bại | Có nguy cơ sửa dở nếu đặt sai thứ tự | Có thể không công bố phiên bản mới |
| Bộ nhớ | Thường tái dùng một object | Có thể tạo object/collection mới |
| Đồng thời | Phải bảo vệ state mutable | Value object dễ chia sẻ; cập nhật reference vẫn cần phối hợp |

**Immutable không đồng nghĩa method không được tính toán.** Method vẫn có thể tính giá trị, cấp phát object, trả collection hoặc báo lỗi. Điều quan trọng là **không làm thay đổi trạng thái logic của receiver**.

## 3. Thực nghiệm 1 — alias của biến mutable và phiên bản immutable

Tạo tệp **`MutationVersusNewValueDemo.java`**:

~~~java
class MutableScore {
    private int points;

    MutableScore(int initial) {
        points = initial;
    }

    void award(int amount) {
        points += amount;
    }

    int points() {
        return points;
    }
}

record ImmutableScore(int points) {
    ImmutableScore award(int amount) {
        return new ImmutableScore(points + amount);
    }
}

public class MutationVersusNewValueDemo {
    public static void main(String[] args) {
        MutableScore mutable = new MutableScore(10);
        MutableScore alias = mutable;
        mutable.award(5);

        System.out.println("mutable=" + mutable.points());
        System.out.println("alias=" + alias.points());
        System.out.println("same reference=" + (mutable == alias));

        ImmutableScore before = new ImmutableScore(10);
        ImmutableScore after = before.award(5);

        System.out.println("before=" + before.points());
        System.out.println("after=" + after.points());
        System.out.println("same immutable reference="
                + (before == after));
        System.out.println("same value=" + before.equals(after));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 MutationVersusNewValueDemo.java
java MutationVersusNewValueDemo
~~~

**Stdout chính xác:**

~~~text
mutable=15
alias=15
same reference=true
before=10
after=15
same immutable reference=false
same value=false
~~~

`alias` và `mutable` cùng một object nên cùng nhìn thấy 15. Với `ImmutableScore`, `award(5)` trả record mới: `before` vẫn 10, `after` là 15. Trong ví dụ, equality theo component cũng khác vì 10 không bằng 15.

**Điều cần nhìn thấy:** `final` trên **biến tham chiếu** không làm receiver thành immutable. Nếu viết `final MutableScore score = new MutableScore(10);`, lệnh `score.award(5)` vẫn sửa được object. Thiết kế của class mới quyết định khả năng mutation.

## 4. Đừng bỏ qua giá trị trả về

Với API bất biến:

~~~java
ImmutableScore score = new ImmutableScore(10);
score.award(5);
~~~

Đây là đoạn minh họa dựa trên record `ImmutableScore` ở phần trước. **Kết quả 15 bị bỏ đi**; `score.points()` vẫn là 10.

Muốn tiến trạng thái logic cho biến local:

~~~java
score = score.award(5);
~~~

Giờ biến `score` trỏ tới object kết quả 15; object 10 trước đó **không bị thay đổi**. Phép gán lại **biến** không phải phép mutate object.

Nếu biến local được khai báo `final`, bạn không thể viết `score = ...`; khi ấy hãy sử dụng một tên biến khác:

~~~java
final ImmutableScore before = new ImmutableScore(10);
final ImmutableScore after = before.award(5);
~~~

Một immutable value object vẫn có thể được giữ bởi **biến mutable**; hai loại “thay đổi” nằm ở hai tầng khác nhau.

## 5. Các tên method nên truyền đạt kiểu cập nhật

Các tên thông dụng:

| Tên API | Ý nghĩa hợp lý |
| --- | --- |
| `withName(newName)` | Giá trị mới với tên khác |
| `withStatus(status)` | Giá trị mới với trạng thái được chỉ định |
| `movedBy(dx,dy)` | Giá trị mới có tọa độ dịch chuyển |
| `plus(amount)` | Giá trị mới sau phép cộng |
| `minus(amount)` | Giá trị mới sau phép trừ |
| `withAdded(item)` | Collection/aggregate mới chứa phần tử |
| `without(id)` | Aggregate mới đã bỏ liên kết theo ID |
| `normalized()` | Giá trị mới theo quy tắc chuẩn hóa |
| `copyWith(...)` | Bản sao tùy biến theo hợp đồng |

Không có keyword `with` trong Java tạo ra cơ chế này. Đây là **quy ước đặt tên**, và developer phải tự triển khai việc tạo bản kết quả đúng.

Một method có tên `withName` nhưng lại gọi `this.name = name;` trên chính receiver là **trái kỳ vọng** khi API đã hứa immutable update. Tên nên đi cùng hợp đồng rõ: có copy mới hay có thể trả `this` trong trường hợp không đổi, xử lý null ra sao, trường hợp lỗi có ném exception không.

## 6. Thiết kế value object với validation ở constructor

Một immutable class điển hình:

~~~java
final class Username {
    private final String text;

    Username(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("username rỗng");
        }
        this.text = text;
    }

    Username withText(String next) {
        return new Username(next);
    }

    String text() {
        return text;
    }
}
~~~

Đây là một class hợp lệ, không có `main`. Mọi đường tạo object, bao gồm `withText`, đều đi qua constructor validation. Không có setter; `text` là `String` bất biến, field là `private final`, class `final`.

Nếu muốn loại tên chứa khoảng trắng biên hoặc chuẩn hóa chữ hoa/chữ thường, hãy **định nghĩa quy tắc** tại constructor/factory và dùng nhất quán. Không nên để `withText` bỏ qua validation mà constructor đang áp dụng.

Cần phân biệt: **bất biến** không tự bảo đảm dữ liệu **hợp lệ**. Một object có thể bất biến nhưng mang giá trị sai nếu constructor không kiểm tra quy tắc miền.

## 7. Thực nghiệm 2 — tạo phiên bản mới và từ chối trạng thái sai

Tạo tệp **`ImmutableProfileDemo.java`**:

~~~java
import java.util.Objects;

final class Profile {
    private final String username;
    private final int level;

    Profile(String username, int level) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username rỗng");
        }
        if (level < 1 || level > 10) {
            throw new IllegalArgumentException("level ngoài 1..10");
        }
        this.username = username;
        this.level = level;
    }

    Profile withUsername(String next) {
        return new Profile(next, level);
    }

    Profile withLevel(int next) {
        return new Profile(username, next);
    }

    String description() {
        return username + "@" + level;
    }
}

public class ImmutableProfileDemo {
    public static void main(String[] args) {
        Profile initial = new Profile("An", 2);
        Profile renamed = initial.withUsername("Bình");
        Profile promoted = renamed.withLevel(3);

        System.out.println("initial=" + initial.description());
        System.out.println("renamed=" + renamed.description());
        System.out.println("promoted=" + promoted.description());

        try {
            promoted.withLevel(99);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
        System.out.println("still=" + promoted.description());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 ImmutableProfileDemo.java
java ImmutableProfileDemo
~~~

**Stdout:**

~~~text
initial=An@2
renamed=Bình@2
promoted=Bình@3
reject=level ngoài 1..10
still=Bình@3
~~~

`withUsername` và `withLevel` gọi cùng constructor, không tự gán lại field. Nếu level sai, constructor mới ném `IllegalArgumentException` và không có object kết quả được trả về; những object đã có vẫn hợp lệ.

**Chú ý:** trường hợp `withLevel(3)` gọi trên object đang level 3 có thể được thiết kế **luôn tạo bản mới** hoặc **trả lại `this`**. Cả hai có thể hợp lệ nếu hợp đồng mô tả rõ; tính bất biến yêu cầu state cũ không bị mutate, **không nhất thiết mọi lời gọi trả một identity mới**.

## 8. Kiểu dữ liệu tiền: tránh phép cộng tràn và state dở dang

Với tiền tệ hoặc số dư, immutable update không chỉ giúp dễ kiểm soát mà còn khiến **validation trước khi công bố kết quả** rõ ràng hơn.

Những câu hỏi nghiệp vụ:

- Có cho phép số tiền âm không?
- Mỗi tài khoản có một currency hay nhiều currency?
- Phép cộng/trừ có tràn `long` không?
- Số tiền yêu cầu có lớn hơn số dư hay vượt hạn mức không?
- Đơn vị là đồng, xu hay một fixed-point scale?

Nếu dùng `long cents`, có thể kiểm soát overflow bằng `Math.addExact`/`Math.subtractExact`. Đừng viết `balance + amount` rồi chỉ kiểm tra kết quả âm vì overflow có thể biến số lớn thành số âm hoặc ngược lại theo two's-complement arithmetic.

Trong ví dụ tiếp theo, quy tắc đơn giản là số dư **không âm**, đơn vị **đồng**, mọi phép cộng/trừ phải chính xác trong miền `long`.

## 9. Thực nghiệm 3 — tài khoản bất biến với `Math.addExact`

Tạo tệp **`ImmutableBalanceDemo.java`**:

~~~java
final class Balance {
    private final long dong;

    Balance(long dong) {
        if (dong < 0) {
            throw new IllegalArgumentException("balance âm");
        }
        this.dong = dong;
    }

    Balance deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount phải dương");
        }
        return new Balance(Math.addExact(dong, amount));
    }

    Balance withdraw(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount phải dương");
        }
        if (amount > dong) {
            throw new IllegalArgumentException("không đủ tiền");
        }
        return new Balance(dong - amount);
    }

    long dong() {
        return dong;
    }
}

public class ImmutableBalanceDemo {
    public static void main(String[] args) {
        Balance opening = new Balance(100);
        Balance funded = opening.deposit(50);
        Balance spent = funded.withdraw(30);

        System.out.println("opening=" + opening.dong());
        System.out.println("funded=" + funded.dong());
        System.out.println("spent=" + spent.dong());

        try {
            spent.withdraw(500);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
        System.out.println("spent after reject=" + spent.dong());

        try {
            new Balance(Long.MAX_VALUE).deposit(1);
        } catch (ArithmeticException ex) {
            System.out.println("overflow="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ImmutableBalanceDemo.java
java ImmutableBalanceDemo
~~~

**Stdout chính xác:**

~~~text
opening=100
funded=150
spent=120
reject=không đủ tiền
spent after reject=120
overflow=ArithmeticException
~~~

Mỗi thao tác thành công tạo một `Balance` mới, không thay đổi opening hay funded. Khi rút quá số dư, chương trình ném exception **trước khi tạo kết quả mới**; spent vẫn bằng 120. `Math.addExact` ném `ArithmeticException` khi phép cộng tràn, thay vì để một số dư sai bị lưu âm thầm.

**Giới hạn quan trọng:** đây là **value object số dư**, không phải giải pháp giao dịch ngân hàng đa người dùng. Nếu nhiều threads cùng đọc số dư cũ và độc lập tạo hai Balance mới, việc lưu/công bố trạng thái mới vẫn cần synchronization, compare-and-set, transaction và quản lý quyền sở hữu đúng.

## 10. Trả mới không bắt buộc thay thế mọi dữ liệu gốc

Một object mới có thể tái sử dụng an toàn **các thành phần bất biến** của object cũ. Ví dụ Profile có `String username`: bản mới cùng username không cần tạo một String khác chỉ để tránh mutation, vì String là immutable.

Tuy nhiên, nếu object chứa:

~~~text
Invoice
  - number: String (immutable)
  - lines: ArrayList<MutableLine> (mutable)
~~~

thì `new Invoice(old.number, old.lines)` chỉ tạo root object mới mà **không tách trạng thái mutable**. Phép update kiểu `withNumber` có thể trả một Invoice mới nhưng vẫn chia sẻ danh sách lines, khiến việc mutate một line ảnh hưởng cả hai versions.

Cần quyết định **phạm vi bất biến**: nếu lines là immutable values được giữ trong immutable list, chia sẻ chúng là an toàn; nếu lines là mutable elements, phải copy hoặc thiết kế wrapper/cơ chế sở hữu thích hợp.

## 11. Record không tự làm tất cả components bất biến sâu

Java 17 `record` là công cụ thuận tiện cho value carriers:

~~~java
record Location(int x, int y) {
    Location movedBy(int dx, int dy) {
        return new Location(x + dx, y + dy);
    }
}
~~~

Các components primitive của record này không thể bị mutate qua API bình thường, nên mỗi phép di chuyển có thể trả record mới.

Nhưng:

~~~java
record MutableTagList(java.util.List<String> tags) {
}
~~~

tự động có field final giữ **reference** tới list. Nếu caller truyền `ArrayList` rồi tiếp tục sửa nó, kết quả `MutableTagList.tags()` vẫn có thể thay đổi. Vì thế, một record không tự bảo đảm deep immutability của mutable components.

Giải pháp cho `List<String>` là compact canonical constructor:

~~~java
record SafeTagList(java.util.List<String> tags) {
    SafeTagList {
        tags = java.util.List.copyOf(tags);
    }

    SafeTagList withAdded(String tag) {
        var updated = new java.util.ArrayList<>(tags);
        updated.add(java.util.Objects.requireNonNull(tag));
        return new SafeTagList(updated);
    }
}
~~~

Các đoạn trong mục này là **record definitions minh họa hợp lệ**, không có `main`. Compact constructor làm snapshot; `withAdded` tạo list ứng viên, sau đó tạo object mới có validation/copy nhất quán.

## 12. Thực nghiệm 4 — record và danh sách không đổi

Tạo tệp **`ImmutableTagsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Tags(List<String> values) {
    Tags {
        values = List.copyOf(values);
    }

    Tags withAdded(String tag) {
        Objects.requireNonNull(tag, "tag");
        List<String> next = new ArrayList<>(values);
        next.add(tag);
        return new Tags(next);
    }

    Tags without(String tag) {
        List<String> next = new ArrayList<>(values);
        next.remove(tag);
        return new Tags(next);
    }
}

public class ImmutableTagsDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("java");

        Tags base = new Tags(input);
        Tags extended = base.withAdded("oop");
        Tags reduced = extended.without("java");

        input.add("external");

        System.out.println("base=" + base.values());
        System.out.println("extended=" + extended.values());
        System.out.println("reduced=" + reduced.values());
        System.out.println("same object=" + (base == extended));

        try {
            base.values().add("illegal");
        } catch (UnsupportedOperationException ex) {
            System.out.println("read-only result");
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ImmutableTagsDemo.java
java ImmutableTagsDemo
~~~

**Stdout:**

~~~text
base=[java]
extended=[java, oop]
reduced=[oop]
same object=false
read-only result
~~~

Thêm `external` vào `input` **không làm base đổi** vì constructor đã dùng `List.copyOf`. `withAdded` và `without` tạo versions khác nhau, còn `base.values()` vẫn trả danh sách chứa một phần tử java.

Trong đoạn này, `without` dùng `List.remove(Object)` và loại **một lần xuất hiện đầu tiên**. Nếu domain coi Tags như **tập không trùng**, nên chọn `Set` hoặc validation uniqueness; không thể tự giả định `List` loại hết mọi duplicate.

## 13. `List.copyOf` và `Collections.unmodifiableList` khác nhau

Một thiết kế immutable cần tránh giữ lại một **unmodifiable view** của một collection mutable do bên ngoài còn nắm giữ.

- `Collections.unmodifiableList(backing)` trả **view không cho sửa qua view**, nhưng nếu `backing` đổi thì kết quả view cũng phản ánh thay đổi.
- `List.copyOf(backing)` tạo unmodifiable list biểu diễn các phần tử tại thời điểm gọi; nó có thể trả lại cùng instance nếu đầu vào vốn là unmodifiable list thích hợp. Với mutable list đầu vào, nó không giữ kết nối live với input theo hợp đồng copy.
- Cả hai **không deep-copy elements**. Nếu elements mutable, các thao tác thay đổi element vẫn có thể quan sát được.

Ví dụ nếu record chứa `List<StringBuilder>`, `List.copyOf` không khiến mỗi StringBuilder trở thành immutable. Thay vì đưa mutable elements vào value object, có thể lưu những dạng dữ liệu bất biến như `String`, `record Line(...)` chỉ chứa immutable components, hoặc tạo snapshot riêng của từng element.

## 14. Thực nghiệm 5 — snapshot collection và cập nhật phiên bản

Tạo tệp **`PlaylistVersionsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Playlist {
    private final String title;
    private final List<String> songs;

    Playlist(String title, List<String> songs) {
        this.title = Objects.requireNonNull(title, "title");
        this.songs = List.copyOf(songs);
    }

    Playlist withTitle(String nextTitle) {
        return new Playlist(nextTitle, songs);
    }

    Playlist withSong(String song) {
        Objects.requireNonNull(song, "song");
        List<String> next = new ArrayList<>(songs);
        next.add(song);
        return new Playlist(title, next);
    }

    Playlist withoutSong(String song) {
        List<String> next = new ArrayList<>(songs);
        next.remove(song);
        return new Playlist(title, next);
    }

    String description() {
        return title + "=" + songs;
    }

    List<String> songs() {
        return songs;
    }
}

public class PlaylistVersionsDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Song A");

        Playlist original = new Playlist("Morning", input);
        Playlist expanded = original.withSong("Song B");
        Playlist renamed = expanded.withTitle("Evening");
        Playlist shortened = renamed.withoutSong("Song A");

        input.add("Outside");

        System.out.println("original=" + original.description());
        System.out.println("expanded=" + expanded.description());
        System.out.println("renamed=" + renamed.description());
        System.out.println("shortened=" + shortened.description());
        System.out.println("same original/expanded="
                + (original == expanded));
        System.out.println("songs original=" + original.songs());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 PlaylistVersionsDemo.java
java PlaylistVersionsDemo
~~~

**Stdout chính xác:**

~~~text
original=Morning=[Song A]
expanded=Morning=[Song A, Song B]
renamed=Evening=[Song A, Song B]
shortened=Evening=[Song B]
same original/expanded=false
songs original=[Song A]
~~~

Mỗi `Playlist` giữ unmodifiable snapshot các `String` bất biến; caller sửa input sau đó không ảnh hưởng các phiên bản đã tạo. `withSong` và `withoutSong` thao tác trên **list ứng viên mới** trước khi đưa vào constructor.

**Chi phí:** mỗi lần thêm/bớt bài hát trong ví dụ phải sao chép một list có độ dài tương ứng, có thể tốn **O(n)** thời gian/bộ nhớ. Với danh sách rất lớn hoặc cập nhật cực kỳ thường xuyên, cần cân nhắc persistent data structures, batching hoặc mô hình mutable builder trước khi công bố snapshot.

## 15. Lựa chọn: luôn tạo object mới hay trả `this` khi không đổi?

Với immutable object, khi giá trị đích **bằng** giá trị hiện tại, có hai hợp đồng khả dĩ:

1. **Always-new:** `withName(sameName)` vẫn tạo object mới. Caller có thể dựa vào identity mới nếu API hứa như vậy.
2. **Reuse-if-unchanged:** `withName(sameName)` trả lại `this`. Điều này không phá bất biến vì receiver không bị mutate.

Chẳng hạn:

~~~java
Profile withUsername(String next) {
    if (username.equals(next)) {
        return this;
    }
    return new Profile(next, level);
}
~~~

Đây là **đoạn method minh họa**, giả định class có fields `username`, `level` và constructor tương ứng. Nếu nhận null, phép `equals` trả false, sau đó constructor tiếp tục từ chối null.

Nên quyết định theo hợp đồng API: tên `withX` thường nói về **giá trị kết quả**, không hứa một identity mới ở mọi lần gọi. Tránh để caller kiểm tra `old != next` như tiêu chí “thay đổi dữ liệu” trừ khi hợp đồng identity được tài liệu hóa.

## 16. Thực nghiệm 6 — no-op update và `equals()`

Tạo tệp **`NoOpUpdateDemo.java`**:

~~~java
import java.util.Objects;

record Settings(String theme, int fontSize) {
    Settings {
        Objects.requireNonNull(theme, "theme");
        if (fontSize < 8 || fontSize > 40) {
            throw new IllegalArgumentException("fontSize sai");
        }
    }

    Settings withTheme(String nextTheme) {
        Objects.requireNonNull(nextTheme, "nextTheme");
        return theme.equals(nextTheme)
                ? this : new Settings(nextTheme, fontSize);
    }

    Settings withFontSize(int nextSize) {
        return nextSize == fontSize
                ? this : new Settings(theme, nextSize);
    }
}

public class NoOpUpdateDemo {
    public static void main(String[] args) {
        Settings first = new Settings("light", 14);
        Settings same = first.withTheme("light");
        Settings changed = first.withFontSize(16);
        Settings equalValue = new Settings("light", 14);

        System.out.println("reused=" + (first == same));
        System.out.println("changed identity="
                + (first != changed));
        System.out.println("first=" + first);
        System.out.println("changed=" + changed);
        System.out.println("equal value="
                + first.equals(equalValue));
        System.out.println("same identity="
                + (first == equalValue));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NoOpUpdateDemo.java
java NoOpUpdateDemo
~~~

**Stdout:**

~~~text
reused=true
changed identity=true
first=Settings[theme=light, fontSize=14]
changed=Settings[theme=light, fontSize=16]
equal value=true
same identity=false
~~~

Record `Settings` có `equals/hashCode/toString` được sinh theo components. Hai objects có cùng dữ liệu được xem là **bằng giá trị** dù `==` false. Ngược lại, `withTheme("light")` trả chính receiver vì không có thay đổi dữ liệu.

**Một API immutable cần mô tả kết quả giá trị, không bắt caller đoán theo địa chỉ object.**

## 17. Chuỗi biến đổi: tạo các versions trung gian

Các operations immutable có thể kết hợp:

~~~java
Settings next = start
        .withTheme("dark")
        .withFontSize(18);
~~~

Đây là **đoạn minh họa** sử dụng record `Settings` đã định nghĩa ở mục 16. Mỗi method nhận một immutable receiver rồi trả giá trị mới, nên lập trình theo chuỗi là tự nhiên.

Hãy chú ý:

- `start` **không đổi**.
- Một giá trị trung gian có thể được cấp phát và sớm trở nên unreachable.
- Nếu bước sau ném exception, biến `next` trong câu khai báo trên **không nhận được kết quả hoàn chỉnh**. Các versions đã tồn tại vẫn không bị mutate.
- Nếu cập nhật nhiều fields phải tuân invariant **liên quan lẫn nhau**, chuỗi method có thể bị chặn bởi validation của một trạng thái trung gian. Khi đó cần một **factory hoặc update method tổng hợp** thay vì ép đi qua các trạng thái tạm thời không hợp lệ.

Đây là điểm quan trọng: immutable update an toàn theo từng bước nhưng không tự biến **một chuỗi giao dịch** thành operation nguyên tử ở mức nghiệp vụ.

## 18. Khi nhiều fields ràng buộc nhau, dùng update tổng hợp

Giả sử một khoảng `Range(start,end)` yêu cầu `start <= end`. Với range `[1,5]`, muốn chuyển thành `[10,20]`:

~~~text
withStart(10) trên [1,5] -> [10,5] (không hợp lệ)
withEnd(20) trên [1,5] -> [1,20] (hợp lệ)
withStart(10) tiếp -> [10,20]
~~~

Nếu phải ghi nhiều chỗ, thứ tự updates dễ làm người dùng bất ngờ. Cách rõ là cung cấp `withBounds(newStart,newEnd)` tạo trực tiếp kết quả hợp lệ trong **một constructor call**.

## 19. Thực nghiệm 7 — bất biến quan hệ giữa hai fields

Tạo tệp **`RangeUpdateDemo.java`**:

~~~java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }

    Range withStart(int newStart) {
        return new Range(newStart, end);
    }

    Range withEnd(int newEnd) {
        return new Range(start, newEnd);
    }

    Range withBounds(int newStart, int newEnd) {
        return new Range(newStart, newEnd);
    }
}

public class RangeUpdateDemo {
    public static void main(String[] args) {
        Range source = new Range(1, 5);

        try {
            source.withStart(10);
        } catch (IllegalArgumentException ex) {
            System.out.println("first failed=" + ex.getMessage());
        }

        Range expanded = source.withEnd(20);
        Range moved = expanded.withStart(10);
        Range direct = source.withBounds(10, 20);

        System.out.println("source=" + source);
        System.out.println("expanded=" + expanded);
        System.out.println("moved=" + moved);
        System.out.println("direct=" + direct);
        System.out.println("same value=" + moved.equals(direct));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 RangeUpdateDemo.java
java RangeUpdateDemo
~~~

**Stdout:**

~~~text
first failed=start > end
source=Range[start=1, end=5]
expanded=Range[start=1, end=20]
moved=Range[start=10, end=20]
direct=Range[start=10, end=20]
same value=true
~~~

Một method `withBounds` hữu ích khi nhiều giá trị phải đổi đồng thời để đạt trạng thái hợp lệ. Nó không có nghĩa Java tự cung cấp transaction hoặc tự kiểm soát khi nhiều threads cập nhật biến chứa Range; chỉ là **việc xây dựng một value object mới** không công bố phiên bản trung gian sai.

## 20. Cập nhật collection kiểu “copy rồi thay”

Trong mutable model, có thể viết:

~~~java
items.add(newItem);
items.remove(oldItem);
~~~

Nếu `items` là field nội bộ được chia sẻ với caller, những lệnh này làm đổi trạng thái có thể quan sát trên object cũ.

Với immutable aggregate, pattern phổ biến:

~~~text
1. Đọc collection bất biến của phiên bản gốc.
2. Tạo collection ứng viên có thể sửa trong phạm vi method.
3. Áp dụng các thay đổi cho ứng viên.
4. Validate kết quả theo domain rules.
5. Tạo value object mới chứa snapshot không sửa được.
6. Trả kết quả; phiên bản cũ giữ nguyên.
~~~

Đây là **copy-on-update theo hợp đồng ứng dụng**, không đồng nghĩa việc dùng lớp `java.util.concurrent.CopyOnWriteArrayList`. `CopyOnWriteArrayList` là một collection cụ thể có đặc tính concurrency, vẫn cung cấp thao tác sửa collection; nó không tự biến toàn bộ object đang chứa collection thành immutable value.

Một mutable builder/private temporary collection hoàn toàn chấp nhận được khi xây immutable object, miễn nó **không thoát ra thành một mutable alias** vào kết quả đã công bố.

## 21. Thực nghiệm 8 — giỏ hàng bất biến, cộng dồn và xóa theo mã

Tạo tệp **`ImmutableCartDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Item(String sku, int quantity) {
    Item {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku rỗng");
        }
        if (quantity < 1) {
            throw new IllegalArgumentException("quantity < 1");
        }
    }

    Item withQuantity(int next) {
        return new Item(sku, next);
    }
}

final class Cart {
    private final List<Item> items;

    Cart(List<Item> source) {
        Objects.requireNonNull(source, "source");
        List<Item> checked = new ArrayList<>();
        for (Item item : source) {
            checked.add(Objects.requireNonNull(item, "item"));
        }
        items = List.copyOf(checked);
    }

    static Cart empty() {
        return new Cart(List.of());
    }

    Cart withAdded(String sku, int quantity) {
        Item added = new Item(sku, quantity);
        List<Item> next = new ArrayList<>(items);
        for (int i = 0; i < next.size(); i++) {
            Item current = next.get(i);
            if (current.sku().equals(sku)) {
                int merged = Math.addExact(
                        current.quantity(), quantity);
                next.set(i, current.withQuantity(merged));
                return new Cart(next);
            }
        }
        next.add(added);
        return new Cart(next);
    }

    Cart without(String sku) {
        Objects.requireNonNull(sku, "sku");
        List<Item> next = new ArrayList<>(items);
        boolean changed = next.removeIf(
                item -> item.sku().equals(sku));
        return changed ? new Cart(next) : this;
    }

    List<Item> items() {
        return items;
    }
}

public class ImmutableCartDemo {
    public static void main(String[] args) {
        Cart empty = Cart.empty();
        Cart one = empty.withAdded("P1", 2);
        Cart two = one.withAdded("P2", 1);
        Cart merged = two.withAdded("P1", 3);
        Cart removed = merged.without("P2");
        Cart unchanged = removed.without("missing");

        System.out.println("empty=" + empty.items());
        System.out.println("one=" + one.items());
        System.out.println("two=" + two.items());
        System.out.println("merged=" + merged.items());
        System.out.println("removed=" + removed.items());
        System.out.println("reused=" + (removed == unchanged));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 ImmutableCartDemo.java
java ImmutableCartDemo
~~~

**Stdout chính xác:**

~~~text
empty=[]
one=[Item[sku=P1, quantity=2]]
two=[Item[sku=P1, quantity=2], Item[sku=P2, quantity=1]]
merged=[Item[sku=P1, quantity=5], Item[sku=P2, quantity=1]]
removed=[Item[sku=P1, quantity=5]]
reused=true
~~~

`Item` là record với hai components bất biến (`String` và `int`). `Cart` lưu `List.copyOf` và không lộ mutable list. Khi thêm số lượng cho sản phẩm đã có, nó tạo **Item mới** rồi thay phần tử trong **list ứng viên mới**; các versions trước giữ số lượng ban đầu.

**Hợp đồng ví dụ:** bỏ SKU không có trong giỏ sẽ trả `this` (không đổi). Nó cũng giả định danh sách đầu vào không có các SKU trùng; **constructor hiện chỉ từ chối null và không tự kiểm tra trùng SKU**. Trong API production, nên đưa ràng buộc uniqueness vào constructor/factory hoặc chuyển representation thành `Map<SKU,Item>` để invariant được bảo vệ ở mọi đường tạo object. Ví dụ minh họa nguyên lý bất biến; nó không tuyên bố constructor hiện đã đảm bảo uniqueness cho input tùy ý.

## 22. Copy nông không đủ nếu item bên trong mutable

Đổi `record Item` sang `MutableItem` có setter:

~~~java
final class MutableItem {
    private int quantity;

    MutableItem(int quantity) {
        this.quantity = quantity;
    }

    void setQuantity(int next) {
        quantity = next;
    }

    int quantity() {
        return quantity;
    }
}
~~~

Đây là class minh họa hợp lệ. Nếu Cart chỉ làm `items = List.copyOf(input)` cho một `List<MutableItem>`, caller vẫn có thể:

~~~java
MutableItem item = new MutableItem(1);
List<MutableItem> input = List.of(item);
item.setQuantity(99);
~~~

và thay đổi quantity của chính object item đang được Cart tham chiếu. Không có immutable aggregate thật sự nếu giá trị logic của nó thay đổi theo một mutable reference mà caller còn nắm giữ.

Giải pháp ưu tiên: **dùng immutable elements** như record `Item`. Nếu bắt buộc dùng `MutableItem` vì yêu cầu tích hợp, phải defensive-copy phần tử khi nhận và khi trả, hoặc chỉ công bố immutable projections thay vì trả element references.

## 23. Cập nhật object lồng nhau mà không sửa phiên bản cũ

Một object giá trị có thể chứa một object giá trị khác. Ví dụ `User` chứa `Address`; địa chỉ của user cần đổi thành một `Address` mới, rồi tạo `User` mới chứa Address ấy.

~~~java
record Address(String city, String street) {
    Address {
        java.util.Objects.requireNonNull(city);
        java.util.Objects.requireNonNull(street);
    }

    Address withCity(String nextCity) {
        return new Address(nextCity, street);
    }
}

record User(String id, Address address) {
    User {
        java.util.Objects.requireNonNull(id);
        java.util.Objects.requireNonNull(address);
    }

    User withAddress(Address next) {
        return new User(id,
                java.util.Objects.requireNonNull(next));
    }
}
~~~

Hai records này là code Java hợp lệ, không có `main`. Cả Address và User không chứa mutable components nên an toàn để chia sẻ các object con không thay đổi.

**Nguyên tắc:** ở mỗi cấp trên đường tới dữ liệu đổi, tạo **một node mới**; các nhánh con immutable **không thay đổi** có thể tái sử dụng mà không cần copy sâu toàn bộ graph.

## 24. Thực nghiệm 9 — immutable nested update

Tạo tệp **`NestedUpdateDemo.java`**:

~~~java
import java.util.Objects;

record Address(String city, String street) {
    Address {
        Objects.requireNonNull(city, "city");
        Objects.requireNonNull(street, "street");
    }

    Address withCity(String next) {
        return new Address(next, street);
    }
}

record User(String id, Address address) {
    User {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(address, "address");
    }

    User withAddress(Address next) {
        return new User(id, next);
    }
}

public class NestedUpdateDemo {
    public static void main(String[] args) {
        Address firstAddress = new Address("Huế", "A");
        User initial = new User("U1", firstAddress);

        Address secondAddress = initial.address().withCity("Đà Nẵng");
        User updated = initial.withAddress(secondAddress);

        System.out.println("initial=" + initial);
        System.out.println("updated=" + updated);
        System.out.println("same user=" + (initial == updated));
        System.out.println("same address="
                + (initial.address() == updated.address()));
        System.out.println("initial city=" + initial.address().city());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 NestedUpdateDemo.java
java NestedUpdateDemo
~~~

**Stdout:**

~~~text
initial=User[id=U1, address=Address[city=Huế, street=A]]
updated=User[id=U1, address=Address[city=Đà Nẵng, street=A]]
same user=false
same address=false
initial city=Huế
~~~

Tạo `Address` mới, rồi `User` mới, tránh thay đổi phiên bản `User` ban đầu. Nếu cả hai addresses đều tham chiếu tới một immutable `String street`, việc chia sẻ `String` không gây alias mutable.

**Không phải mọi nested update phải deep-copy toàn bộ cây**. Chỉ những node cần đổi mới tạo object mới; những immutable nodes khác có thể dùng lại. Đây là cơ sở của nhiều thiết kế dữ liệu bất biến hiệu quả.

## 25. Hàm nhận giá trị cũ và trả giá trị mới

Có thể biểu diễn một biến đổi như:

~~~java
java.util.function.UnaryOperator<Settings> change =
        old -> old.withFontSize(18);
~~~

Đây là đoạn minh họa sử dụng kiểu `Settings` ở mục 16, không phải chương trình độc lập. `UnaryOperator<T>` là một `Function<T,T>` cho đầu vào/đầu ra cùng kiểu, hợp với hình dạng update bất biến.

Một hàm biến đổi tốt:

- Không sửa object đầu vào.
- Có thể kiểm thử độc lập theo input/output.
- Trả giá trị mới có invariant hợp lệ.
- Không dựa vào mutable global state để quyết định kết quả nếu cần tính dự đoán.
- Tránh side effects trong lần thực thi nếu muốn dùng an toàn với các cơ chế **có thể thử lại**.

“Method trả object mới” **không tự làm nó pure**: method vẫn có thể ghi log, gửi email, tăng biến static hoặc mutate một dependency khác. Nếu gọi “pure transformation”, phải xét **toàn bộ side effects**, không chỉ receiver.

## 26. Thực nghiệm 10 — biến đổi danh sách bằng `stream().map`

Tạo tệp **`ImmutableStreamUpdateDemo.java`**:

~~~java
import java.util.List;

record Product(String sku, int price) {
    Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku rỗng");
        }
        if (price < 0) {
            throw new IllegalArgumentException("price âm");
        }
    }

    Product withPrice(int nextPrice) {
        return new Product(sku, nextPrice);
    }
}

public class ImmutableStreamUpdateDemo {
    public static void main(String[] args) {
        List<Product> original = List.of(
                new Product("A", 10),
                new Product("B", 20));

        List<Product> updated = original.stream()
                .map(p -> p.sku().equals("B")
                        ? p.withPrice(25) : p)
                .toList();

        System.out.println("original=" + original);
        System.out.println("updated=" + updated);
        System.out.println("same first="
                + (original.get(0) == updated.get(0)));
        System.out.println("same second="
                + (original.get(1) == updated.get(1)));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ImmutableStreamUpdateDemo.java
java ImmutableStreamUpdateDemo
~~~

**Stdout:**

~~~text
original=[Product[sku=A, price=10], Product[sku=B, price=20]]
updated=[Product[sku=A, price=10], Product[sku=B, price=25]]
same first=true
same second=false
~~~

`stream().map` tạo danh sách kết quả mới qua `toList()`. Phần tử A không thay đổi nên lambda trả lại chính immutable object A cũ; phần tử B được thay bằng Product mới. Đây là **structural sharing đơn giản** ở cấp phần tử.

**Lưu ý:** `Stream.toList()` trong Java 17 trả list không hỗ trợ sửa qua các methods như `add`. Nhưng nếu Product là mutable, việc giữ lại cùng phần tử A sẽ không an toàn theo nghĩa immutable deep structure. Chúng ta dùng record với primitive/String components để việc chia sẻ là hợp lý.

## 27. Giữ lịch sử để so sánh, undo và audit

Một ưu điểm của immutable values là có thể giữ các versions:

~~~text
state0 --update A--> state1 --update B--> state2

state0 vẫn tồn tại
state1 vẫn tồn tại
state2 là phiên bản mới nhất
~~~

Với mutable object, nếu chỉ lưu cùng reference vào danh sách history, mọi mục có thể cùng nhìn thấy **state mới nhất**, không phải ảnh chụp thời điểm lưu. Với immutable objects, mỗi reference vẫn mô tả giá trị ở thời điểm được tạo.

Tuy nhiên, lịch sử nhiều phiên bản tiêu thụ bộ nhớ. Nếu mỗi version sao chép cả list lớn, overhead có thể đáng kể; muốn hệ thống lưu lịch sử dài hạn, cần một chính sách retention, snapshot/diff hoặc persistent data structure.

**Lịch sử trong bộ nhớ không phải audit log bền vững**. Nếu cần lưu sự kiện bền vững, khôi phục sau restart hoặc tuân thủ, phải có cơ chế lưu trữ và giao dịch riêng.

## 28. Thực nghiệm 11 — undo qua các phiên bản bất biến

Tạo tệp **`ImmutableHistoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

record Draft(String text) {
    Draft {
        if (text == null) {
            throw new IllegalArgumentException("text null");
        }
    }

    Draft append(String extra) {
        if (extra == null) {
            throw new IllegalArgumentException("extra null");
        }
        return new Draft(text + extra);
    }
}

public class ImmutableHistoryDemo {
    public static void main(String[] args) {
        List<Draft> history = new ArrayList<>();
        Draft current = new Draft("A");
        history.add(current);

        current = current.append("B");
        history.add(current);

        current = current.append("C");
        history.add(current);

        System.out.println("history="
                + history.stream().map(Draft::text).toList());
        System.out.println("current=" + current.text());

        current = history.get(1);
        System.out.println("undo=" + current.text());
        System.out.println("first=" + history.get(0).text());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ImmutableHistoryDemo.java
java ImmutableHistoryDemo
~~~

**Stdout:**

~~~text
history=[A, AB, ABC]
current=ABC
undo=AB
first=A
~~~

Các objects `Draft` trong history không đổi sau mỗi `append`; Undo ở đây chỉ việc đặt biến `current` trở lại một reference cũ.

**Giới hạn:** ví dụ dùng mutable `ArrayList` để quản lý **lịch sử các immutable values**. Danh sách history bản thân không immutable, nhưng các Draft đã lưu là immutable. Đây là hai tầng trách nhiệm khác nhau.

## 29. Điều kiện quan trọng: không để caller sửa nội dung con của phiên bản

Một object root mới không đồng nghĩa một immutable graph.

Ví dụ sai về mặt hợp đồng:

~~~java
final class WrongDocument {
    private final java.util.List<StringBuilder> lines;

    WrongDocument(java.util.List<StringBuilder> input) {
        lines = java.util.List.copyOf(input);
    }

    WrongDocument withMore(StringBuilder line) {
        var next = new java.util.ArrayList<>(lines);
        next.add(line);
        return new WrongDocument(next);
    }

    java.util.List<StringBuilder> lines() {
        return lines;
    }
}
~~~

Đây là một **class hợp lệ nhưng cố ý minh họa thiết kế chưa bất biến sâu**. Constructor copy list container; accessor trả unmodifiable list, nhưng mọi `StringBuilder` bên trong vẫn mutable và caller có thể giữ tham chiếu tới chúng.

Khi gọi `old.lines().get(0).append("!")`, **state logic của old vẫn thay đổi**. Nếu new version chia sẻ builder ấy, cả hai versions còn cùng đổi.

Để sửa, lưu `List<String>` đã chuyển các builders thành `toString()`, hoặc lưu các immutable line value objects. Nếu mutable elements là bắt buộc, defensive-copy các elements đúng lúc nhận, và không công bố mutable elements nội bộ.

## 30. Thực nghiệm 12 — tách dữ liệu mutable khi tạo value mới

Tạo tệp **`ImmutableNotesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Notes {
    private final List<String> lines;

    Notes(List<StringBuilder> input) {
        Objects.requireNonNull(input, "input");
        List<String> copied = new ArrayList<>();
        for (StringBuilder item : input) {
            copied.add(Objects.requireNonNull(item).toString());
        }
        lines = List.copyOf(copied);
    }

    private Notes(List<String> safeLines, boolean marker) {
        lines = List.copyOf(safeLines);
    }

    Notes withLine(String text) {
        Objects.requireNonNull(text, "text");
        List<String> next = new ArrayList<>(lines);
        next.add(text);
        return new Notes(next, true);
    }

    List<String> lines() {
        return lines;
    }
}

public class ImmutableNotesDemo {
    public static void main(String[] args) {
        StringBuilder external = new StringBuilder("A");
        List<StringBuilder> input = List.of(external);

        Notes original = new Notes(input);
        Notes updated = original.withLine("B");

        external.append("!");
        System.out.println("original=" + original.lines());
        System.out.println("updated=" + updated.lines());
        System.out.println("same root=" + (original == updated));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 ImmutableNotesDemo.java
java ImmutableNotesDemo
~~~

**Stdout:**

~~~text
original=[A]
updated=[A, B]
same root=false
~~~

Ở đây, constructor public **chụp giá trị chuỗi** từ từng StringBuilder, nên sửa `external` sau đó không chạm Notes. Các phần tử lưu trong Notes là String bất biến. `withLine` dựng list ứng viên và tạo Notes mới chứa snapshot.

Constructor private thêm tham số `boolean marker` nhằm phân biệt chữ ký có `List<String>` khỏi `List<StringBuilder>` sau **type erasure**; marker không mang nghiệp vụ. Trong mã production, nên đặt **static factory có tên** hoặc thay cấu trúc constructors cho dễ đọc hơn, tránh một “flag parameter” chỉ dùng để phân biệt overload generic. Bài này cố ý cho thấy hai constructor chỉ khác type argument List không thể overload trực tiếp trong Java do erasure.

## 31. Copy constructor và `withX`: khác `clone()` như thế nào?

Một API bất biến có thể dùng:

~~~java
final class Label {
    private final String text;

    Label(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("label rỗng");
        }
        this.text = text;
    }

    Label(Label source) {
        this(source.text);
    }

    Label withText(String next) {
        return new Label(next);
    }

    String text() {
        return text;
    }
}
~~~

Đây là class hợp lệ. **Copy constructor** nhận object hiện có và chạy constructor thường với validation; `withText` tạo giá trị mới chỉ khác một field.

`Object.clone()` lại có cơ chế riêng, thường copy nông và không chạy constructor thông thường của đối tượng bản sao. Với value objects có invariants, `withX`/copy factory/constructor được đặt tên rõ thường **dễ kiểm soát** hơn việc trông chờ một shallow clone được triển khai đúng cho mọi nested references.

Không cần bắt buộc implement `Cloneable` chỉ để xây immutable updates. Nếu class đã có copy contract dùng clone từ một API đặc thù, hãy tuân theo hợp đồng API ấy.

## 32. Immutability và Java `final` khác nhau thế nào trong update?

Đoạn:

~~~java
final class MutableInside {
    private final java.util.ArrayList<String> values =
            new java.util.ArrayList<>();

    void add(String value) {
        values.add(value);
    }
}
~~~

là class **mutable**, mặc dù class final và field final. `final` trên field ngăn việc `values = new ArrayList<>()` trong method bình thường, **không ngăn `values.add`**.

Trong một immutable value object, những fields tham gia state nên:

- Không được gán lại khi object đã tạo xong.
- Không giữ mutable references mà caller có thể sửa theo đường rò rỉ.
- Không bị thay đổi gián tiếp bởi methods công khai.
- Không bị mutate bởi background tasks làm đổi giá trị logic.
- Được tạo thông qua validation/normalization cần thiết.

`final class` giúp ngăn subclass phá hợp đồng; `private final` giúp ngăn tái gán fields. **Hai keyword là công cụ hỗ trợ**, không phải bằng chứng duy nhất cho immutability.

## 33. Tính toán nhiều bước và chính sách exception

Một update immutable thường có cấu trúc:

~~~text
old value (không sửa)
      |
      v
validate yêu cầu
      |
      v
tính toán các trường mới
      |
      v
validate các trường mới trong constructor/factory
      |
      v
trả new value
~~~

Nếu một bước lỗi, không công bố object kết quả cho caller. Bản cũ không bị mutate.

Tuy nhiên:

- Nếu update method **gọi external service**, lưu database hoặc sửa object dependency, exception có thể để lại **side effects khác**, dù receiver vẫn bất biến.
- Nếu nhiều updates phải thành một nghiệp vụ nguyên tử, cần thiết kế **update tổng hợp** hoặc transaction ở tầng phù hợp.
- Nếu phép biến đổi có dữ liệu đầu vào mutable được thay đổi đồng thời, tính toán có thể đọc trạng thái không nhất quán trừ khi snapshot/đồng bộ.

Do đó, **immutable receiver** không tự tạo ACID transaction. Hãy tách bảo đảm “không mutate object cũ” khỏi bảo đảm “không có bất kỳ side effect nào trong toàn hệ thống”.

## 34. Đa luồng: value immutable giúp đọc an toàn, biến hiện hành vẫn phải cập nhật an toàn

Giả sử nhiều threads cùng dùng một `Settings` record bất biến. Việc đọc `settings.theme()` trên một object hoàn chỉnh có thể đơn giản hơn đọc nhiều fields mutable đang bị update.

Nhưng nếu một biến giữ **giá trị Settings hiện tại** cần đổi từ S0 sang S1, nhiều threads cùng ghi biến vẫn cần phối hợp.

Một ví dụ phổ biến:

~~~java
java.util.concurrent.atomic.AtomicReference<Settings> state =
        new java.util.concurrent.atomic.AtomicReference<>(
                new Settings("light", 14));
state.updateAndGet(old -> old.withFontSize(16));
~~~

Đây là đoạn minh họa dựa trên `Settings` ở mục 16. `AtomicReference` quản lý **reference đang được công bố**. `updateAndGet` có thể gọi lại update function khi có tranh chấp, nên update function nên **không có side effects**; chỉ tính value mới từ value cũ.

Một điểm quan trọng: việc dùng `AtomicReference` bảo vệ **việc thay reference** theo API atomic, không biến mọi object con mutable bên trong Settings thành bất biến. Thiết kế value object vẫn phải tự bảo vệ state.

## 35. Thực nghiệm 13 — công bố phiên bản mới bằng `AtomicReference`

Tạo tệp **`AtomicImmutableStateDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

record AppConfig(String mode, int threshold) {
    AppConfig {
        if (mode == null || mode.isBlank()) {
            throw new IllegalArgumentException("mode rỗng");
        }
        if (threshold < 0) {
            throw new IllegalArgumentException("threshold âm");
        }
    }

    AppConfig withThreshold(int next) {
        return new AppConfig(mode, next);
    }
}

public class AtomicImmutableStateDemo {
    public static void main(String[] args) {
        AtomicReference<AppConfig> ref =
                new AtomicReference<>(new AppConfig("normal", 10));

        AppConfig first = ref.get();
        AppConfig second = ref.updateAndGet(
                old -> old.withThreshold(
                        Math.addExact(old.threshold(), 5)));

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("current=" + ref.get());
        System.out.println("first unchanged="
                + (first.threshold() == 10));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AtomicImmutableStateDemo.java
java AtomicImmutableStateDemo
~~~

**Stdout (chương trình chạy tuần tự để có kết quả xác định):**

~~~text
first=AppConfig[mode=normal, threshold=10]
second=AppConfig[mode=normal, threshold=15]
current=AppConfig[mode=normal, threshold=15]
first unchanged=true
~~~

`AtomicReference` giữ reference đang hoạt động. `first` vẫn trỏ phiên bản threshold 10 sau update; `second` và `ref.get()` trỏ phiên bản threshold 15.

Trong hệ thống thật, nếu update function vừa gửi email vừa tính new config, một CAS retry có thể gửi **nhiều email**. Vì thế update function nên là phép biến đổi không side effect, còn hành động ngoài cần được điều phối ở tầng thích hợp.

## 36. Mutable builder để xây một immutable object

Không nhất thiết tránh mọi mutable object trong toàn chương trình. Một pattern thực dụng:

1. Dùng **builder mutable** cục bộ để lắp ráp dữ liệu.
2. Validate các ràng buộc sau cùng.
3. Tạo một **immutable snapshot** khi hoàn thành.
4. Không để builder còn giữ đường sửa trạng thái bên trong snapshot.

Tạo tệp **`BuilderToImmutableDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record ReadingPlan(List<String> chapters) {
    ReadingPlan {
        chapters = List.copyOf(chapters);
    }

    ReadingPlan withChapter(String chapter) {
        List<String> next = new ArrayList<>(chapters);
        next.add(Objects.requireNonNull(chapter));
        return new ReadingPlan(next);
    }
}

final class PlanBuilder {
    private final List<String> chapters = new ArrayList<>();

    PlanBuilder add(String chapter) {
        chapters.add(Objects.requireNonNull(chapter));
        return this;
    }

    ReadingPlan build() {
        return new ReadingPlan(chapters);
    }
}

public class BuilderToImmutableDemo {
    public static void main(String[] args) {
        PlanBuilder builder = new PlanBuilder();
        builder.add("Class");

        ReadingPlan first = builder.build();
        builder.add("Object");
        ReadingPlan second = builder.build();
        ReadingPlan third = first.withChapter("Immutable");

        System.out.println("first=" + first.chapters());
        System.out.println("second=" + second.chapters());
        System.out.println("third=" + third.chapters());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BuilderToImmutableDemo.java
java BuilderToImmutableDemo
~~~

**Stdout:**

~~~text
first=[Class]
second=[Class, Object]
third=[Class, Immutable]
~~~

Builder được phép sửa list của chính nó, nhưng `ReadingPlan` snapshot bằng `List.copyOf`; vì vậy builder tiếp tục thêm Object không làm first đổi. `withChapter` cũng tạo phiên bản mới không ảnh hưởng builder hay first.

Đây là **immutable at boundary**: việc lắp ráp mutable nội bộ vẫn có thể đơn giản/hiệu quả, còn trạng thái được công bố ra ngoài là immutable.

## 37. Hiệu năng: cấp phát, copy chi phí O(n) và chia sẻ cấu trúc

Trả object mới có thể tốn:

- **Cấp phát** root object, dù chỉ một field đổi.
- **Copy collection** mỗi lần cập nhật, nhất là `ArrayList` lớn.
- **GC pressure** nếu tạo nhiều versions rất nhanh.
- **Memory retention** nếu history giữ tất cả versions.

Nhưng cũng có những lợi thế:

- Immutable objects thường dễ **cache, memoize, share** hơn khi hợp đồng được thiết kế đúng.
- Không cần defensive copy mọi **immutable component**.
- Chỉ tạo những nodes thay đổi và **chia sẻ cấu trúc bất biến** ở những nodes không đổi.
- JIT/JVM có các tối ưu riêng; không nên kết luận update immutable luôn chậm hơn chỉ từ số lượng `new` ở source.
- Với operations nhỏ và dữ liệu không quá lớn, chi phí có thể không quan trọng bằng tính rõ ràng và giảm bug alias.

Nếu cần cập nhật list một triệu phần tử liên tục, phương án “copy toàn bộ ArrayList cho mỗi phần tử thêm” thường không hiệu quả. Có thể dùng builder mutable trong phạm vi đóng, batch update hoặc **persistent data structure** chuyên dụng.

**Persistent structure** ở đây nghĩa là một cấu trúc dữ liệu giữ được các phiên bản cũ nhờ sharing các nút bất biến; không đồng nghĩa tự động lưu dữ liệu xuống ổ đĩa hay database.

## 38. Trả object mới có phải lúc nào cũng đúng với entity?

Không. Một object có thể là:

- **Value object:** giá trị được xác định bởi nội dung, ví dụ tọa độ, khoảng số, Money. Immutable updates là lựa chọn rất tự nhiên.
- **Entity:** thực thể có identity, lifecycle, transaction boundaries, ví dụ một tài khoản hoặc đơn hàng được lưu lâu dài. Có thể dùng immutable snapshots cho entity, nhưng **định danh và lưu trữ** cần chính sách riêng.
- **Mutable aggregate/service:** có những nhiệm vụ như quản lý bộ nhớ đệm, luồng dữ liệu, kết nối, bộ đếm đồng thời; không nhất thiết nên clone toàn object ở mỗi thao tác.

Ví dụ một số dư bất biến không tự thực hiện lệnh chuyển tiền thành công trong database. Phải có một tầng khác xác minh cùng lúc hai tài khoản, chống ghi đè phiên bản, commit hoặc rollback theo giao dịch.

**Tư duy đúng:** ưu tiên immutable values khi phù hợp với ngữ nghĩa miền và API; không ép tất cả service, session, file stream hoặc persistence entities trở thành “mỗi lệnh trả object khác”.

## 39. Kiểm thử immutable update: quan sát cả trước lẫn sau

Một bộ kiểm thử tốt cần xác nhận:

| Điều cần kiểm tra | Ví dụ |
| --- | --- |
| Bản cũ không đổi | `source.level() == 2` sau `withLevel(3)` |
| Kết quả mới đúng | `result.level() == 3` |
| Các trường khác được bảo toàn | Đổi theme không đổi fontSize |
| Validation vẫn áp dụng | Level ngoài phạm vi ném lỗi |
| Không có mutation sau lỗi | Bản cũ giữ nguyên sau exception |
| Tham chiếu mutable đầu vào được tách | Caller sửa input không đổi bản cũ |
| Getter không làm lộ mutable state | Caller không thể sửa list nội bộ |
| Immutable elements thực sự độc lập | Không giữ alias tới MutableLine có setter |
| Nested update giữ bản cha cũ | User cũ vẫn có Address cũ |
| Bài toán no-op có hợp đồng rõ | Có thể trả `this` nếu dữ liệu không đổi |
| Equality và identity không bị nhầm | `equals` khác `==` |
| Cập nhật tập hợp không làm lệch invariant | Không trùng SKU nếu hợp đồng cấm |
| Concurrency publication có cơ chế | State reference cập nhật atomically nếu cần |
| Không lặp side effect khi retry | Update function của CAS không gửi email |

Nếu một test chỉ xác nhận **giá trị trả về** mà không xác nhận receiver cũ còn nguyên, một implementation vô tình sửa object rồi trả `this` có thể lọt qua.

Với mutable input, hãy thử **cả hai hướng**: mutate input sau khi xây object, và thử mutate dữ liệu trả từ getter. Chỉ một trong hai đường bảo vệ sẽ không đủ.

## 40. Những lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `withX` nhưng bỏ kết quả | Biến tiếp tục trỏ bản cũ | Lưu hoặc truyền tiếp giá trị trả về |
| `withX` sửa `this` | Phá hợp đồng immutable | Tạo giá trị mới, không gán receiver |
| `new Root(old.list)` nhưng giữ list mutable | Các versions vẫn chia sẻ mutation | Snapshot và immutable elements |
| Dùng `Collections.unmodifiableList` trên input vẫn bị sửa bên ngoài | View sống, không bảo vệ snapshot | `List.copyOf`/defensive copy |
| `List.copyOf` của mutable elements | Chỉ copy container nông | Copy elements hoặc dùng immutable DTO |
| Method mới bỏ qua constructor validation | Có thể tạo giá trị invalid | Route mọi update qua factory/constructor |
| Update hai fields lần lượt qua trạng thái invalid | Exception ở bước trung gian | Dùng method update tổng hợp |
| Dùng `==` để xác định thay đổi giá trị | Nhầm identity với equality | Xác định value equality hợp đồng |
| Bắt buộc `withX` luôn new mà không cần | Cấp phát thừa | Cho phép return `this` khi hợp đồng phù hợp |
| Copy toàn bộ list quá lớn trong vòng lặp | Chi phí O(n) trên mỗi update | Batch/builder/persistent data structure |
| Dùng immutable Balance thay cho transaction | Lost update/ghi đè trạng thái | Đồng bộ/transaction tầng lưu trữ |
| Update function CAS có side effect | Side effect có thể lặp khi retry | Pure update, side effects tách riêng |
| Cho caller sửa object con qua getter | Snapshot root vẫn thay đổi logic | Defensive copy hoặc immutable elements |
| Record được coi tự deep immutable | Mutable components vẫn có thể đổi | Compact constructor + an toàn accessor |
| Mọi object đều phải immutable dù là socket/service | Không đúng lifecycle của tài nguyên | Dùng immutable dữ liệu, quản lý resource riêng |
| Lưu nhiều versions mà không giới hạn | Tốn bộ nhớ | Chính sách retention/snapshot/diff |

## 41. Bài tập tự luyện

**Câu 1.** Vì sao `final MutablePoint p = ...` không ngăn `p.moveBy(1,2)` nếu `moveBy` sửa fields?

**Câu 2.** `Point next = point.movedBy(3,4)` trả object mới. Giá trị của `point` sau đó có đổi không? Nếu biến `point` được gán `point = next` thì object cũ có bị mutate không?

**Câu 3.** Một record `Score(int points)` có `Score add(int n)`. Vì sao gọi `score.add(5)` rồi bỏ kết quả không thay đổi score?

**Câu 4.** `withLevel(99)` trên object hợp lệ bị từ chối ở constructor. Điều gì xảy ra với object cũ?

**Câu 5.** Tại sao nên dùng `Math.addExact` trong một immutable Balance được lưu bằng long khi phép cộng có thể tràn?

**Câu 6.** Một object mới giữ cùng `ArrayList<MutableItem>` của object cũ. Đã bảo đảm hai versions độc lập chưa?

**Câu 7.** Constructor dùng `List.copyOf(input)` khi `input` chứa `StringBuilder`. Caller còn giữ từng builder. Tính bất biến sâu được bảo đảm chưa?

**Câu 8.** `Settings withTheme("light")` trên Settings theme=light trả `this`. Điều này có phá immutability không?

**Câu 9.** Hai records được tạo riêng nhưng có components bằng nhau. `==` và `equals` nhất thiết cho cùng một kết quả không?

**Câu 10.** Range[1,5] cần thành Range[10,20]. Vì sao `withStart(10)` có thể lỗi trong khi `withBounds(10,20)` thành công?

**Câu 11.** `List.copyOf(backing)` và `Collections.unmodifiableList(backing)` khác nhau thế nào khi backing thay đổi?

**Câu 12.** Giỏ hàng bất biến nhận `List<Item>`, nhưng constructor không kiểm tra duplicate SKU. API có chắc invariant “mỗi SKU xuất hiện một lần” chưa?

**Câu 13.** Nếu Person chứa Address bất biến, thay đổi city có cần clone sâu mọi object trong ứng dụng không?

**Câu 14.** `Stream.map` trả lại cùng phần tử A cũ và phần tử B mới. Điều kiện nào khiến việc chia sẻ A an toàn?

**Câu 15.** Tại sao lưu các immutable Draft phiên bản khác nhau hỗ trợ undo đơn giản hơn việc lưu cùng một MutableDraft vào List nhiều lần?

**Câu 16.** Nếu một `withUpdated` method ghi một record vào database trước khi ném exception, việc receiver immutable có khiến operation toàn cục không side effect không?

**Câu 17.** Hai threads cùng đọc config cũ và tạo config mới. Chỉ dùng immutable Config đã tránh lost update chưa?

**Câu 18.** `AtomicReference.updateAndGet` có thể gọi update function nhiều lần. Vì sao lambda cập nhật nên tránh gửi email hoặc mutate list ngoài?

**Câu 19.** Vì sao builder mutable vẫn phù hợp trong workflow trả immutable objects?

**Câu 20.** Khi nào “mỗi lần thêm một phần tử copy toàn bộ ArrayList” gây vấn đề hiệu năng? Có những hướng thiết kế thay thế nào?

### Đáp án và giải thích

1. `final` ở biến chỉ ngăn gán lại reference; nó không cấm mutation của object đích.
2. `point` cũ không đổi; gán biến sang next chỉ đổi reference được giữ, không sửa object cũ.
3. Method chỉ tạo và trả giá trị mới, không có setter; phải sử dụng kết quả trả về.
4. Không đổi. Constructor không trả value mới, object cũ vẫn tồn tại hợp lệ.
5. Để phát hiện overflow bằng exception thay vì lưu kết quả long sai.
6. Chưa; mutable list hoặc các phần tử mutable bị alias có thể làm hai versions cùng đổi.
7. Chưa; List.copyOf chỉ ngăn chỉnh list, không deep-copy StringBuilder elements.
8. Không; trạng thái không đổi và trả lại cùng immutable object là một hợp đồng hợp lệ.
9. Không; hai references khác nhau có `== false` nhưng records có component values bằng nhau thường `equals true`.
10. `[10,5]` vi phạm start<=end; `withBounds` tạo trực tiếp `[10,20]` hợp lệ.
11. Snapshot không tiếp tục phản ánh mutable backing; unmodifiable view thì có.
12. Chưa; constructor phải validate uniqueness hoặc có representation ngăn duplicate ở mọi đường vào.
13. Không. Tạo Address mới và Person mới dọc đường cập nhật; chia sẻ các immutable objects khác là an toàn.
14. Khi A thực sự immutable, không bị mutate gián tiếp qua các tham chiếu khác.
15. Mỗi Draft giữ đúng giá trị thời điểm ấy; cùng MutableDraft trong List sẽ cùng quan sát state mới nhất.
16. Không. Bất biến chỉ nói receiver không bị sửa; side effects khác vẫn có thể tồn tại.
17. Chưa. Việc công bố/reference update cần CAS, synchronization hoặc transaction phù hợp.
18. Vì CAS retry có thể lặp side effects; lambda nên chỉ tính new value từ old value.
19. Builder có thể mutate dữ liệu riêng trong lúc dựng; snapshot phải tách alias khi công bố.
20. Với list lớn hoặc cập nhật nhiều lần, copy mỗi bước có thể O(n) chi phí. Có thể batch, mutable builder trong phạm vi đóng hoặc persistent structure.

## 42. Checklist áp dụng vào dự án Java

- Đã nêu rõ **giá trị logic** và invariant của class?
- API cập nhật có trả **giá trị mới** thay vì tự sửa `this`?
- Caller có hiểu cần lưu/truyền tiếp giá trị trả về?
- Các trường còn lại có được giữ đúng khi cập nhật một field?
- Constructor/factory có được tái dùng để validate mọi kết quả mới?
- Có xử lý null, số âm, overflow và giới hạn miền hợp lý?
- Có case nhiều fields cần cập nhật cùng nhau thay vì tuần tự qua trạng thái invalid?
- Có bảo vệ mutable inputs khỏi alias không?
- Getter và elements trả ra có khiến caller sửa state nội bộ không?
- Record/collection chứa toàn immutable elements hoặc có deep-copy đúng phạm vi?
- Trường hợp no-op trả `this` hay new đã được xác định rõ?
- Tests có khẳng định **receiver gốc không đổi** sau success lẫn failure?
- Có phân biệt `equals` (value) và `==` (identity)?
- Nested update có sao chép đúng các node thay đổi và chia sẻ những immutable nodes còn lại?
- Nếu giữ history, có chính sách quản lý bộ nhớ?
- Nếu có nhiều threads, cập nhật reference hiện hành có đồng bộ đúng không?
- Update lambda có side effect nguy hiểm nếu chạy lại do retry không?
- Nếu liên quan database, có transaction/concurrency control riêng?
- Hiệu năng có được đo đạc trước khi chuyển sang chiến lược mutable hoặc persistent structure?
- Có đang ép immutable object vào một loại resource/service cần lifecycle mutable không?

## 43. Tài liệu chính thức Java 17

- [JLS 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): records, components và compact constructors.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): ý nghĩa `final` với reference/variable.
- [JLS 17 §17.5 — final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): final fields và initialization safety theo Java Memory Model.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot và hạn chế shallow copy.
- [Java SE 17 — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): kết quả list không hỗ trợ sửa trực tiếp.
- [Java SE 17 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view phản ánh backing list.
- [Java SE 17 — Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)): kiểm tra overflow.
- [Java SE 17 — UnaryOperator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/UnaryOperator.html): biểu diễn một phép biến đổi `T -> T`.
- [Java SE 17 — AtomicReference.updateAndGet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html#updateAndGet(java.util.function.UnaryOperator)): công bố giá trị mới và lưu ý hàm cập nhật có thể được tính lại.
- [Java SE 17 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): kiểm tra null.
- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): một ví dụ API bất biến theo thời gian; các phép cộng ngày trả đối tượng kết quả.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): kiểu số immutable với các operations trả giá trị mới.

**Ghi nhớ:** muốn “thay đổi” một **immutable value**, hãy **tạo giá trị mới mô tả trạng thái mong muốn** và giữ nguyên bản gốc. Thiết kế này giúp giảm alias-driven side effects, rõ ràng về validation, dễ xây dựng lịch sử và phối hợp với xử lý theo hàm. Nhưng phải bảo vệ **toàn bộ mutable state có thể quan sát**, không chỉ root object hoặc final references; và khi có lưu trữ/đa luồng, **việc công bố hoặc commit giá trị mới** vẫn cần cơ chế concurrency/transaction đúng phạm vi.
