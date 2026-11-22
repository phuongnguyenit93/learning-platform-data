# Record trong Java: Kiểu mô tả một tập dữ liệu có tên

> **Bối cảnh module Java 14 — Nền tảng record:** `record` được giới thiệu dưới dạng *preview* tại Java 14, nhưng **chỉ trở thành tính năng chính thức từ Java 16 (JEP 395)**. Vì bài học chỉ giữ kiến thức còn áp dụng hiện nay, toàn bộ ví dụ dưới đây sử dụng **cú pháp record đã chính thức** trên JDK được hỗ trợ (ví dụ JDK 21 hoặc 25). Không cài JDK 14 cũ và không bật `--enable-preview`.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích vì sao một `record` diễn tả **một kiểu dữ liệu có tên và tập thành phần được đặt tên, có kiểu rõ ràng**, thay vì chỉ là một danh sách giá trị.
2. Khai báo `record`, khởi tạo bằng constructor và truy cập dữ liệu qua các **component accessor**.
3. Hiểu các thành viên Java tự tạo: trường `private final`, canonical constructor, `equals`, `hashCode` và `toString`.
4. Phân biệt **dữ liệu thành phần không thể gán lại** và **bất biến sâu**; biết dùng bản sao phòng vệ khi có collection hoặc mảng.
5. Bảo vệ tính hợp lệ của dữ liệu bằng **compact canonical constructor**.
6. Biết khi nào nên dùng `record`, khi nào nên giữ `class` thông thường; tránh xem `record` là sự thay thế mặc định cho mọi lớp.

## 2. Ý tưởng trung tâm: “Một tập dữ liệu có tên” nghĩa là gì?

Giả sử muốn biểu diễn thông tin về một khóa học. Dữ liệu của khóa học gồm:

- `title`: tên khóa học, kiểu `String`;
- `lessons`: số bài học, kiểu `int`;
- `published`: trạng thái công bố, kiểu `boolean`.

Nếu chỉ dùng `List<Object>` hoặc `Object[]`, người đọc phải tự nhớ phần tử thứ 0, thứ 1, thứ 2 nghĩa là gì; kiểu dữ liệu cũng không được kiểm tra rõ ràng ở từng vị trí. Nếu chỉ dùng một `Map<String, Object>`, tên khóa tuy có nghĩa nhưng lỗi viết sai tên và ép kiểu thường chỉ lộ ra khi chạy.

`record` cung cấp một **kiểu danh nghĩa (*nominal type*)** có tên riêng:

~~~java
record Course(String title, int lessons, boolean published) {}
~~~

Đọc dòng khai báo này như một hợp đồng dữ liệu:

- **`Course`** là **tên kiểu**; có thể dùng làm kiểu biến, tham số, kết quả phương thức và phần tử collection.
- **`title`, `lessons`, `published`** là ba *record components*. Mỗi component có **tên, kiểu và thứ tự** trong **record header** (`(...)`).
- Tập component là **hình dạng dữ liệu cố định** được công khai qua API. Java tạo constructor và phương thức đọc tương ứng.
- Mỗi giá trị `new Course(...)` là một **đối tượng** thuộc lớp `Course`; `record` vẫn là một loại lớp, không phải tuple không tên và không phải bản ghi trong cơ sở dữ liệu.
- Thứ tự header có ý nghĩa khi gọi constructor: `new Course("Java", 12, true)` đúng thứ tự `String, int, boolean`.

Nhìn vào kiểu `Course`, người lập trình biết một giá trị `Course` **gồm những thành phần nào** mà không cần đọc một khối mã khai báo getter/setter thủ công.

**Hai kiểu cùng “hình dạng” vẫn khác nhau:** `record CourseId(long value) {}` và `record StudentId(long value) {}` là **hai kiểu khác biệt**. Chúng không thể dùng thay nhau chỉ vì cùng có một thành phần kiểu `long`. Đây là khác biệt quan trọng so với dữ liệu không có kiểu chuyên biệt.

## 3. Cú pháp `record` chính thức

Cấu trúc phổ biến:

~~~java
[accessModifier] record RecordName(Type1 component1, Type2 component2) {
    // Constructor, methods, static members (tùy chọn)
}
~~~

Dấu `[]` trong dòng trên chỉ phần tùy chọn để giải thích cú pháp, **không phải Java code có thể biên dịch nguyên văn**.

Các trường hợp hợp lệ:

~~~java
record Point(int x, int y) {}

record Tag(String value) {}

record EmptyMarker() {}

record Pair<L, R>(L left, R right) {}
~~~

- `Point` lưu hai tọa độ có tên `x` và `y`.
- `Tag` tạo một kiểu riêng mang một giá trị `String`; hữu ích khi muốn tránh dùng nhầm những chuỗi có ý nghĩa khác nhau.
- `EmptyMarker` cho thấy header có thể rỗng, dù thường không cần thiết cho ứng dụng mô tả dữ liệu.
- `Pair<L, R>` là một **generic record**; Java không cấm tham số kiểu ở record.

Khai báo `record` có thể ở cấp tệp, là kiểu lồng trong một lớp hoặc được khai báo cục bộ ở phạm vi cho phép. Một record lồng là **implicit static**, vì vậy không tự giữ tham chiếu đến thể hiện lớp bao ngoài.

### Các thành viên được sinh tự động

Với `record Point(int x, int y) {}`, Java cung cấp:

| Thành viên | Ý nghĩa |
| --- | --- |
| Trường `private final int x` và `private final int y` | Lưu trạng thái tương ứng component, không gán lại được sau khởi tạo. |
| Canonical constructor `Point(int x, int y)` | Nhận đủ component đúng thứ tự và khởi tạo chúng. |
| `public int x()` và `public int y()` | Phương thức đọc **cùng tên component**, không dùng mẫu `getX()` mặc định. |
| `equals(Object)` | So sánh record **cùng kiểu** theo giá trị component, theo quy tắc Java quy định. |
| `hashCode()` | Tạo hash phù hợp với `equals` từ các component. |
| `toString()` | Cung cấp chuỗi mô tả record, gồm tên record và tên/giá trị component. |

Đây là **hành vi ngôn ngữ**, không cần plugin, annotation hoặc thư viện tạo getter. Bạn có thể khai báo thêm phương thức nếu chúng hỗ trợ ý nghĩa của dữ liệu, nhưng API chính được quyết định bởi header.

Lưu ý: `toString()` thuận tiện để quan sát dữ liệu, **không nên dùng định dạng của nó như một giao thức trao đổi dữ liệu** và không nên mặc định log toàn bộ record nếu component chứa thông tin nhạy cảm.

## 4. Ví dụ độc lập: record giữ một bộ dữ liệu có tên

Tạo tệp **`RecordBasicsDemo.java`**:

~~~java
record Learner(String name, int age) {}

public class RecordBasicsDemo {
    public static void main(String[] args) {
        Learner first = new Learner("Lan", 22);
        Learner same = new Learner("Lan", 22);
        Learner other = new Learner("Minh", 22);

        System.out.println(first.name() + " / " + first.age());
        System.out.println(first.equals(same));
        System.out.println(first.equals(other));
        System.out.println(first.hashCode() == same.hashCode());
    }
}
~~~

Biên dịch và chạy trên một JDK hiện hành, chẳng hạn JDK 21 hoặc JDK 25:

~~~bash
javac --release 17 RecordBasicsDemo.java
java RecordBasicsDemo
~~~

**Kết quả chính xác:**

~~~text
Lan / 22
true
false
true
~~~

Phân tích từng dòng:

1. `Learner first = new Learner("Lan", 22);` gọi canonical constructor có tham số `String name` và `int age`. Không cần viết constructor khi không có logic kiểm tra đặc biệt.
2. `first.name()` và `first.age()` là các **component accessor**. `first.getName()` **không tự được tạo**. IDE có thể hiển thị gợi ý phương thức, nhưng tên thực là `name()` và `age()`.
3. `first.equals(same)` trả `true` vì cả hai là `Learner` và các component tương ứng bằng nhau. Hai tham chiếu vẫn trỏ tới **hai đối tượng khác nhau**.
4. `first.equals(other)` trả `false` vì `name` khác nhau.
5. Hai đối tượng bằng nhau theo `equals` phải có cùng `hashCode`. Giá trị hash cụ thể không phải kết quả cần học thuộc.

Ở thời điểm khai báo, `Learner` chỉ có một dòng, nhưng mang đủ ý nghĩa của **lớp chuyên chở dữ liệu**. Không tạo setter vì record biểu thị các giá trị thành phần đã được chốt tại lúc khởi tạo.

## 5. Tại sao tên component quan trọng?

So sánh ba cách mô tả cùng dữ liệu:

~~~java
// Cách 1: dữ liệu không có kiểu riêng
String title = "Java";
int lessonCount = 12;

// Cách 2: kiểu record có ý nghĩa nghiệp vụ
record Course(String title, int lessons) {}
Course course = new Course("Java", 12);

// Cách 3: kiểu chuyên biệt cho một định danh
record CourseId(long value) {}
CourseId id = new CourseId(101L);
~~~

Các đoạn trên là **mảnh cú pháp minh họa**; khai báo record và biến cần đặt ở vị trí hợp lệ trong một chương trình Java.

Ở **cách 1**, một phương thức nhận hai tham số có thể bị gọi sai thứ tự, đặc biệt khi nhiều tham số cùng kiểu. **Cách 2** gói các thuộc tính thành một giá trị thống nhất `Course`, giúp truyền/nhận và so sánh trong chương trình. **Cách 3** tạo tên kiểu cho một định danh: thay vì truyền mọi nơi một `long` có ý nghĩa mơ hồ, ta có thể chỉ định rõ `CourseId`.

Đặt tên rõ ràng cho record và component giúp API **tự mô tả**. Ví dụ `course.lessons()` có nghĩa hơn truy cập `values[1]` hoặc ép kiểu từ `map.get("lessons")`. Khi thay đổi record header, người dùng record và các lời gọi constructor có thể phải cập nhật; đó chính là tác dụng của **hợp đồng dữ liệu được kiểm tra lúc biên dịch**.

**Record không phải “struct chỉ có dữ liệu thô”:** record vẫn có phương thức, constructor tùy chỉnh, interface và logic xác thực. Thiết kế phù hợp khi **toàn bộ trạng thái thiết yếu** của một đối tượng được mô tả bởi các component công khai qua API.

## 6. Record có những ràng buộc nào?

Theo đặc tả Java hiện hành:

- Record là một **class ngầm định `final`**: không thể dùng `extends` để tạo lớp con từ một record. Record cũng không được khai báo `abstract`.
- Record kế thừa trực tiếp `java.lang.Record` do ngôn ngữ quy định; bạn **không viết** `extends Record` hoặc `extends SomeClass` trong khai báo record.
- Record **có thể `implements` interface**.
- Không thể tự khai báo thêm **instance field** ngoài các component; có thể khai báo **static field/constant**, phương thức và các thành viên hợp lệ khác.
- Không thể có **instance initializer block** để thiết lập thêm trạng thái như lớp thông thường.
- Các component được lưu bởi trường `private final`, còn accessor là `public`. Không có setter mặc định.
- Record không được dùng một số tên component trùng tên các phương thức `Object` không có tham số như `toString`, `hashCode` hoặc `getClass`.
- Constructor không tham số **không được tự sinh** nếu header có component. Muốn hỗ trợ thêm cách tạo giá trị, bạn có thể dùng static factory hoặc constructor phụ ủy quyền đúng cách cho canonical constructor.

Một ví dụ record triển khai interface:

~~~java
interface Named {
    String name();
}

record Project(String name, int tasks) implements Named {
    boolean hasTasks() {
        return tasks > 0;
    }

    static Project empty(String name) {
        return new Project(name, 0);
    }
}
~~~

Đây là **mảnh định nghĩa kiểu**, chưa có `main`. Java tự cung cấp `Project.name()` tương thích với `Named.name()`; `hasTasks()` là phương thức tính từ component; `empty()` là static factory. Không có trạng thái instance ẩn bên ngoài `name` và `tasks`.

Tạo record khi cần mô hình **giá trị dữ liệu đã được đặt tên rõ ràng**. Không cố dùng record để mô phỏng đối tượng có nhiều trường nội bộ mutable, vòng đời trạng thái phức tạp hoặc hệ phân cấp lớp phải kế thừa.

## 7. Bảo vệ dữ liệu hợp lệ với compact canonical constructor

Record tạo constructor mặc định, nhưng bạn có thể kiểm tra và chuẩn hóa dữ liệu khi tạo đối tượng. Một **compact constructor** viết theo dạng `RecordName { ... }`, không lặp lại danh sách tham số. Mỗi tham số trùng tên component được cung cấp ngầm; sau khi khối lệnh hoàn tất bình thường, Java tự gán giá trị các tham số cho component field.

Tạo tệp **`RecordValidationDemo.java`**:

~~~java
import java.util.Objects;

record Course(String title, int lessons) {
    Course {
        Objects.requireNonNull(title, "title");
        title = title.strip();

        if (title.isEmpty()) {
            throw new IllegalArgumentException("title must not be blank");
        }
        if (lessons <= 0) {
            throw new IllegalArgumentException("lessons must be positive");
        }
    }
}

public class RecordValidationDemo {
    public static void main(String[] args) {
        Course course = new Course("  Java records  ", 8);
        System.out.println(course.title() + " / " + course.lessons());

        try {
            new Course("  ", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RecordValidationDemo.java
java RecordValidationDemo
~~~

Kết quả chính xác:

~~~text
Java records / 8
invalid
~~~

**Tại sao đoạn mã trên đúng?**

- `Objects.requireNonNull(title, "title")` bác bỏ `null` ngay lúc khởi tạo. Nếu `title == null`, nó ném `NullPointerException`, không vào nhánh `IllegalArgumentException` bên dưới.
- `title = title.strip()` **chuẩn hóa tham số ngầm**, rồi Java tự dùng giá trị tham số sau khi khối compact constructor chạy xong để khởi tạo trường `title`. Không cần viết `this.title = title;`.
- `lessons <= 0` là ràng buộc nghiệp vụ được nêu tường minh; khi không hợp lệ, constructor ném ngoại lệ, không tạo ra đối tượng `Course` thành công.
- Với `new Course("  ", 0)`, tên trống bị phát hiện trước; `catch (IllegalArgumentException)` in `invalid`.

**Không gán trực tiếp cho component field** trong compact constructor: `this.title = ...` là không hợp lệ trong thân loại constructor này. Cũng không viết `return` để thoát sớm khỏi compact constructor. Nếu có nhiều constructor, hãy bảo đảm chúng dẫn đến việc khởi tạo đầy đủ trạng thái theo hợp đồng canonical constructor.

Constructor là nơi phù hợp để bảo đảm các giá trị record tuân thủ **invariant** (điều kiện luôn đúng sau khi tạo). Tuy vậy, việc bất biến nông còn đòi hỏi phòng vệ đối với component tham chiếu đến đối tượng mutable; xem mục tiếp theo.

## 8. Bất biến nông: `final` không có nghĩa là dữ liệu bên trong không đổi

Một record có trường component `private final`, vì vậy bạn không thể đổi tham chiếu của trường đó sau khi tạo đối tượng. Nhưng nếu component trỏ đến một `List`, mảng hoặc đối tượng mutable, **nội dung bên trong vẫn có thể bị sửa**.

Ví dụ nhầm lẫn thường gặp:

~~~java
record ScoreArray(int[] values) {}
~~~

Sau khi tạo `ScoreArray scores = new ScoreArray(array);`, Java không cho bạn viết `scores.values = otherArray`. Tuy nhiên, `scores.values()[0] = 99` vẫn có thể thay đổi phần tử mảng nếu đó là mảng có phần tử.

Ngoài ra, `equals` được sinh ra **không so sánh nội dung sâu của mảng**: bản thân mảng sử dụng so sánh tham chiếu. Hai record có hai mảng khác nhau cùng phần tử có thể **không bằng nhau**.

### Ví dụ độc lập về mảng

Tạo tệp **`RecordArrayDemo.java`**:

~~~java
import java.util.Arrays;

record ScoreArray(int[] values) {}

public class RecordArrayDemo {
    public static void main(String[] args) {
        ScoreArray first = new ScoreArray(new int[] {1, 2});
        ScoreArray second = new ScoreArray(new int[] {1, 2});

        System.out.println(first.equals(second));
        System.out.println(Arrays.equals(first.values(), second.values()));

        first.values()[0] = 99;
        System.out.println(first.values()[0]);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RecordArrayDemo.java
java RecordArrayDemo
~~~

Kết quả chính xác:

~~~text
false
true
99
~~~

Ba dòng cho thấy: **các mảng có nội dung bằng nhau** không khiến hai record mặc nhiên bằng nhau; và accessor mặc định trả về **chính tham chiếu mảng**, cho phép sửa nội dung.

**Lựa chọn thiết kế:** nếu dữ liệu có ý nghĩa giống một tập giá trị không thay đổi, hãy ưu tiên component có kiểu bất biến phù hợp hoặc tạo bản sao phòng vệ. Riêng mảng, việc clone ở constructor và accessor có thể ngăn chỉnh sửa qua tham chiếu, nhưng **không tự chuyển `equals` sang so sánh nội dung**; cần cân nhắc dùng `List` bất biến hoặc thiết kế `equals/hashCode` tùy chỉnh đúng hợp đồng.

### Ví dụ độc lập: danh sách được sao chép khi tạo record

Tạo tệp **`RecordSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record CourseTags(String owner, List<String> tags) {
    CourseTags {
        Objects.requireNonNull(owner, "owner");
        tags = List.copyOf(tags);
    }
}

public class RecordSnapshotDemo {
    public static void main(String[] args) {
        List<String> original = new ArrayList<>(List.of("core", "api"));
        CourseTags snapshot = new CourseTags("Lan", original);

        original.add("extra");
        System.out.println(snapshot.tags());

        try {
            snapshot.tags().add("other");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RecordSnapshotDemo.java
java RecordSnapshotDemo
~~~

Kết quả chính xác:

~~~text
[core, api]
unmodifiable
~~~

Vì `List.copyOf(tags)` tạo/thu nhận một danh sách **không sửa đổi được**, snapshot không bị ảnh hưởng bởi lệnh `original.add("extra")`. Các phần tử `String` cũng bất biến, nên đây là một ví dụ tốt cho record mang giá trị.

**Giới hạn cần hiểu đúng:** `List.copyOf` không sao chép sâu từng phần tử. Nếu danh sách chứa đối tượng mutable, các đối tượng đó vẫn có thể thay đổi qua tham chiếu khác. `List.copyOf` cũng không cho phép component danh sách hoặc phần tử trong đó là `null`. Hãy chọn kiểu thành phần và chiến lược sao chép theo nhu cầu bất biến thực sự.

## 9. So sánh theo giá trị, danh tính và hợp đồng của record

Một record là **đối tượng** trong Java, nên vẫn có danh tính tham chiếu (`==`) như các đối tượng bình thường. Điểm khác biệt khi mô hình dữ liệu là Java tự tạo phép `equals` có ý nghĩa theo **các component**.

Ví dụ:

~~~java
record Location(int x, int y) {}
record Offset(int x, int y) {}
~~~

Hai dòng là **mảnh định nghĩa kiểu**. Với:

~~~java
Location a = new Location(2, 3);
Location b = new Location(2, 3);
Offset c = new Offset(2, 3);
~~~

- `a == b` là `false` vì được tạo bằng hai lệnh `new` khác nhau;
- `a.equals(b)` là `true` vì cùng **kiểu record** và các giá trị component tương ứng bằng nhau;
- `a.equals(c)` là `false` vì `Location` và `Offset` là **hai kiểu khác nhau**, dù dữ liệu có cùng hình dạng.

Đây là lợi thế của **kiểu có tên**: hệ thống kiểu bảo vệ ý nghĩa của dữ liệu, còn `equals` hỗ trợ ngữ nghĩa giá trị bên trong một kiểu.

Với các component chứa tham chiếu, `equals` mặc định tuân theo phép so sánh của chính kiểu component: `String.equals` so sánh văn bản; `List.equals` so sánh phần tử theo thứ tự; mảng dùng so sánh tham chiếu. **Đừng mặc định “mọi record đều so sánh sâu”**.

Tùy biến accessor hoặc `equals/hashCode` cần cẩn trọng: record được thiết kế để biểu lộ trạng thái đúng như header. Nếu logic tùy biến che giấu hoặc biến đổi bất ngờ các component, những người dùng API sẽ khó tái tạo một record từ các giá trị mà accessor trả về. Cố gắng giữ **tính minh bạch của thành phần dữ liệu**.

## 10. Record generic và giá trị mang cấu trúc nhỏ

Tạo tệp **`RecordGenericDemo.java`**:

~~~java
record Pair<L, R>(L left, R right) {}

public class RecordGenericDemo {
    public static void main(String[] args) {
        Pair<String, Integer> pair = new Pair<>("alpha", 42);
        System.out.println(pair.left() + " / " + pair.right());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 RecordGenericDemo.java
java RecordGenericDemo
~~~

Kết quả chính xác:

~~~text
alpha / 42
~~~

Đối với mô hình nghiệp vụ quan trọng, nên dùng tên ý nghĩa như `PriceRange`, `DateInterval` hoặc `CourseSummary` thay vì dùng `Pair` ở mọi nơi. `Pair` cho thấy khả năng generic, nhưng tên `left`/`right` thường ít truyền đạt mục đích hơn tên của component trong một record chuyên biệt.

Ví dụ:

~~~java
record DateInterval(java.time.LocalDate start,
                    java.time.LocalDate end) {}
~~~

Có thể bổ sung compact constructor kiểm tra `start` không nằm sau `end`. Khi đó kiểu mang một **bất biến nghiệp vụ**: mỗi `DateInterval` được tạo thành công đều có khoảng thời gian hợp lệ. Đây là ví dụ record vừa mô tả các giá trị có tên vừa thực thi các ràng buộc dữ liệu.

## 11. Khác biệt với `class` thông thường

| Tiêu chí | `record` | `class` thông thường |
| --- | --- | --- |
| Mục đích tiêu biểu | Biểu diễn tập component có tên và kiểu, đóng vai trò giá trị dữ liệu | Tùy ý: thực thể có danh tính, đối tượng mutable, dịch vụ, mô hình có hành vi/phân cấp |
| Trường instance | Tự sinh từ header, `private final`; không khai báo thêm instance field | Tự thiết kế, có thể mutable hoặc `final` |
| Constructor | Có canonical constructor theo header; tùy chỉnh để chuẩn hóa/kiểm tra | Tự định nghĩa hoặc nhận constructor mặc định nếu đủ điều kiện |
| Accessor | `componentName()` được sinh tự động | Tên getter tùy tác giả/thư viện |
| `equals/hashCode/toString` | Có triển khai được sinh theo các component | Kế thừa từ `Object` nếu không tự cài đặt |
| Kế thừa lớp | Ngầm `final`, không thể extends lớp khác | Có thể hỗ trợ kế thừa nếu thiết kế cho phép |
| Interface | Có thể implements | Có thể implements |
| Thay đổi trạng thái | Không thể gán lại component field; vẫn có thể chứa tham chiếu đến đối tượng mutable | Tùy thiết kế |
| Phù hợp mô hình ORM cần proxy/setter/constructor riêng | Phải kiểm tra yêu cầu framework; thường dùng làm DTO/projection hơn là entity mutable | Thường linh hoạt hơn cho entity có vòng đời trạng thái |

### Khi nên chọn record

- Giá trị truyền qua ranh giới phương thức: `CourseSummary`, `ApiResult`, `ValidationError`.
- Đầu ra của một phép tính: `PriceQuote`, `Statistics`, `Coordinates`.
- Kết quả truy vấn, projection/DTO (khi phiên bản thư viện hỗ trợ).
- Giá trị cấu hình bất biến hoặc snapshot không cần trạng thái ẩn.
- Giá trị định danh có kiểu riêng: `CustomerId`, `OrderId`.

### Khi nên cân nhắc class

- Đối tượng có **vòng đời thay đổi** và nhiều thao tác biến đổi trạng thái.
- Mô hình cần kế thừa từ superclass hiện có hoặc cần proxy/subclass theo hợp đồng thư viện.
- Có trạng thái instance không thuộc hợp đồng dữ liệu công khai; record không cho phép thêm instance field.
- Phải tuân thủ framework yêu cầu constructor không tham số, setter hoặc mutability; kiểm tra phiên bản framework trước khi quyết định.

**Đừng đồng nhất “record” với “database record”.** Một entity JPA có yêu cầu về constructor, nhận dạng và quản lý trạng thái riêng; record có thể rất hữu ích cho DTO/projection trả về từ tầng dữ liệu, nhưng không phải thay thế tự động cho mọi entity.

## 12. Những hiểu nhầm phổ biến

| Hiểu nhầm | Sự thật |
| --- | --- |
| “Học module Java 14 thì phải cài JDK 14 để học record.” | Không. Record ở Java 14 chỉ là preview; cú pháp **chính thức** từ Java 16, nên dùng JDK hiện hành. |
| “Record chính thức trong Java 14.” | Không. **JEP 395 chính thức từ Java 16**; Java 14/15 là các giai đoạn preview lịch sử. |
| “Record chỉ là cách viết tắt cho class có getter và setter.” | Record có **API thành phần cố định** và không có setter mặc định; cung cấp ngữ nghĩa giá trị qua `equals/hashCode`. |
| “Record là bất biến sâu.” | Chỉ đảm bảo trường component `private final`; đối tượng mutable bên trong vẫn có thể bị sửa. |
| “Accessor tên là `getName()`.” | Mặc định là `name()`, trùng tên component. |
| “`equals` so sánh sâu toàn bộ dữ liệu.” | So sánh phụ thuộc quy tắc bằng nhau của từng component; mảng là trường hợp dễ nhầm. |
| “Record và class là hai hệ kiểu không liên quan.” | Record **là một lớp** đặc biệt, ngầm extends `java.lang.Record`. |
| “Record không thể có phương thức.” | Có thể thêm phương thức, static factory, static field và triển khai interface. |
| “Tất cả record có cùng thành phần đều là một kiểu.” | Record là **nominal type**: `CourseId` không tự động trở thành `StudentId`. |
| “Dùng `toString()` để tạo JSON ổn định.” | `toString` dành cho mô tả, không phải định dạng giao tiếp dữ liệu ổn định. |

## 13. Cách lựa chọn và kiểm chứng trong dự án hiện đại

**Bước 1 — Viết hợp đồng dữ liệu bằng lời.** Trả lời: đối tượng này chứa những thành phần gì, tên và kiểu của từng phần, có cần đổi trạng thái sau khi tạo không? Nếu toàn bộ trạng thái cần hiển thị nằm trong các component ổn định, record là ứng viên tốt.

**Bước 2 — Chọn phiên bản Java phù hợp.** Record chính thức từ **Java 16**. Với JDK LTS đang được hỗ trợ, bạn có thể dùng `--release 17` hoặc phiên bản dự án chuẩn hóa. Dùng `javac --help` để xác nhận phiên bản đích mà JDK đang cài còn hỗ trợ. **Không dùng `--release 14` để biên dịch record**, vì record chưa phải tính năng chính thức ở mốc đó.

**Bước 3 — Chọn kiểu component thể hiện đúng bất biến.** Với kiểu nguyên thủy và `String`, rủi ro mutability thường đơn giản. Với `List`, `Map`, mảng hoặc đối tượng mutable, quyết định có cần sao chép, bọc bất biến hoặc mô hình hóa bằng giá trị khác.

**Bước 4 — Xác thực tại constructor.** Kiểm tra `null`, khoảng giá trị và quan hệ giữa các component. Dữ liệu chuẩn hóa phải được áp dụng nhất quán ngay tại lúc tạo.

**Bước 5 — Kiểm thử hành vi bên ngoài.** Với record có hai component, hãy kiểm tra: tạo đúng, tạo sai bị chặn, accessor trả giá trị mong đợi, `equals/hashCode` đúng với ý nghĩa nghiệp vụ, dữ liệu mutable không phá bất biến mà bạn công bố.

**Bước 6 — Kiểm tra tương thích thư viện.** Công cụ JSON/ORM/serialization có thể yêu cầu version hoặc cấu hình riêng để hỗ trợ record; hãy kiểm tra tài liệu thư viện đang dùng. API record accessor là `componentName()`, nên đừng mặc định mọi công cụ dựa trên quy ước `getX()` sẽ hiểu record giống JavaBean truyền thống.

**Bước 7 — Đánh giá thay đổi header.** Thêm, đổi tên, đổi kiểu hoặc đổi thứ tự component có thể ảnh hưởng constructor, accessor, `equals` và khách hàng của API. Thay đổi này cần được xem như thay đổi **hợp đồng kiểu dữ liệu**.

## 14. Bài tập có định hướng

### Bài 1 — Record mô tả tập dữ liệu

Tạo một `record Product(String sku, String name, long price)`. Trong `main`, khởi tạo với `"SKU-01"`, `"Keyboard"` và `500_000L`; in ra `name()` và `price()`. Giải thích vì sao cả ba component đều có **tên và kiểu**, và vì sao `Product` có ý nghĩa hơn một mảng `Object[]`.

**Tiêu chí:** mã dùng cú pháp record đã chính thức, compile thành công trên target từ Java 16 trở lên, không dùng setter.

### Bài 2 — Tính bằng nhau

Tạo hai đối tượng `Product` cùng giá trị và một đối tượng khác giá `price`. Kiểm tra `equals` của từng cặp, rồi giải thích quan hệ giữa `equals` và `hashCode`. Không so sánh hash bằng một con số cố định vì thuật toán hash cụ thể không phải hợp đồng cần dựa vào.

### Bài 3 — Xác thực dữ liệu

Thêm compact constructor để bác bỏ `sku` trống, `name` trống và `price < 0`. Chuẩn hóa khoảng trắng ở `sku` và `name` bằng `strip()` trước khi kiểm tra. Với input sai, bảo đảm constructor ném ngoại lệ và không tạo thành công đối tượng lỗi.

### Bài 4 — Bất biến nông

Thay `Product` bằng `record Cart(String id, List<String> skuList)`. Tạo record từ một `ArrayList`, sửa danh sách gốc sau đó và quan sát nếu không sao chép. Bổ sung `skuList = List.copyOf(skuList);` vào compact constructor rồi kiểm chứng record giữ nguyên snapshot.

### Bài 5 — Chọn record hay class

Một `OrderDraft` được chỉnh số lượng, thêm/xóa sản phẩm liên tục, có vòng đời thay đổi trạng thái. Một `OrderSummary` chỉ chứa mã đơn, tổng số tiền, thời điểm xuất báo cáo. Trình bày lựa chọn `class` hoặc `record` cho mỗi trường hợp dựa trên **hợp đồng trạng thái và hành vi**, không chỉ dựa trên số dòng mã.

Bạn đạt mục tiêu khi có thể **đọc một record header và mô tả chính xác kiểu, danh sách component, cách khởi tạo, cách truy cập, tính bằng nhau và các giới hạn bất biến** của nó.

## 15. Tài liệu chính thức còn áp dụng

1. [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): thiết kế record và mốc chính thức Java 16.
2. [Java Language Specification 25, `8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10): quy tắc record header, component, constructor, thành viên và giới hạn của record.
3. [Oracle Java 16 Language Guide — Record Classes](https://docs.oracle.com/en/java/javase/16/language/records.html): giải thích trực quan các thành viên được Java tạo. Dù trang thuộc bản Java 16, nội dung về **record chính thức** vẫn là cơ sở của Java hiện đại.
4. [JDK API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html): giao ước kiểu record và trạng thái bất biến nông.
5. [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html): kiểm tra dòng JDK LTS và chính sách cập nhật khi thiết lập môi trường.

**Ghi nhớ:** `record` mô tả **một kiểu dữ liệu có tên** với các **component có tên, kiểu và thứ tự rõ ràng**. Nó giảm mã lặp nhưng quan trọng hơn là làm **hợp đồng dữ liệu** trở nên minh bạch. Dùng cú pháp đã chính thức từ Java 16, xác thực dữ liệu tại constructor và thiết kế cẩn thận khi component chứa đối tượng có thể thay đổi.