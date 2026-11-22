# Ngăn lộ mảng, tập hợp và đối tượng có thể thay đổi trong Java

**Đóng gói (encapsulation)** không chỉ là đặt trường dữ liệu thành `private`. Nếu một lớp **trả ra tham chiếu** đến mảng, danh sách, map hoặc đối tượng mutable đang lưu bên trong, mã bên ngoài vẫn có thể thay đổi trạng thái nội bộ **mà không gọi phương thức cập nhật được thiết kế**. Chiều ngược lại cũng quan trọng: nếu constructor hoặc setter **giữ nguyên tham chiếu** đến một đối tượng mutable do caller cung cấp, caller có thể tiếp tục sửa đối tượng đó từ bên ngoài.

Hiện tượng này thường gọi là **representation exposure** (*làm lộ biểu diễn nội bộ*) hay **leaking mutable state**. Nó làm suy yếu tính đóng gói dù field đã là `private final`.

Ví dụ có vấn đề:

```java
class Course {
    private final int[] scores;

    Course(int[] scores) {
        this.scores = scores;  // Giữ tham chiếu mảng của caller
    }

    int[] scores() {
        return scores;        // Trả tham chiếu mảng nội bộ
    }
}
```

Caller có thể làm:

```java
int[] input = {8, 9};
Course course = new Course(input);

input[0] = -100;             // Thay đổi từ đầu vào
course.scores()[1] = -200;   // Thay đổi qua getter
```

Cả hai thao tác đều sửa **cùng mảng** mà `Course` lưu. Modifier `private final` chỉ ngăn mã ngoài truy cập trực tiếp field và ngăn field bị gán lại sau khi khởi tạo hợp lệ; nó **không làm mảng bất biến**.

**Mục tiêu:** thiết kế một lớp sao cho mã bên ngoài chỉ thay được trạng thái nội bộ qua **API có chủ đích**, không qua các tham chiếu mutable bị lộ.

## 1. Cơ chế: biến tham chiếu và aliasing

Trong Java, mảng, collection và phần lớn các kiểu object đều được sử dụng qua **tham chiếu**. Phép gán một biến tham chiếu sang biến khác không tự tạo bản sao object.

```java
int[] a = {1, 2};
int[] b = a;
b[0] = 99;

System.out.println(a[0]); // 99
```

`a` và `b` là hai biến nhưng cùng trỏ đến một đối tượng mảng.

```text
a ─────┐
       ├──> int[] #1 { 99, 2 }
b ─────┘
```

Một field private vẫn có thể tham chiếu chính object mà caller đang giữ:

```text
caller.input ──────────┐
                       ├──> int[] #1
Course.scores (private)┘
```

Vì thế **đóng gói field** và **đóng gói trạng thái của object được tham chiếu** là hai việc liên quan nhưng khác nhau.

**Java truyền đối số theo giá trị:** khi constructor nhận `int[] scores`, nó nhận một **bản sao giá trị tham chiếu**. Bản sao tham chiếu ấy vẫn trỏ đến cùng mảng của caller. Đây không phải cơ chế pass-by-reference của biến caller.

### Hai đường lộ trạng thái

| Đường đi | Code có nguy cơ | Tại sao nguy hiểm? |
| --- | --- | --- |
| **Đầu vào** (*inbound alias*) | `this.scores = scores;` | Caller còn `scores` và có thể sửa mảng sau khi constructor kết thúc |
| **Đầu ra** (*outbound alias*) | `return scores;` | Caller nhận mảng nội bộ và có thể sửa phần tử |
| Trả collection mutable | `return items;` | Caller có thể gọi `add`/`remove`/`clear` |
| Trả view của collection mutable | `return Collections.unmodifiableList(items);` | Cấm sửa qua view, nhưng alias khác có thể sửa backing list; view thay đổi theo |
| Trả collection mới chứa mutable elements | `return new ArrayList<>(items);` | Tách cấu trúc list nhưng vẫn chia sẻ các element objects |
| Trả field là object mutable | `return address;` | Caller có thể gọi setter/mutator trên chính object nội bộ |

Một API an toàn phải xác định **ai sở hữu trạng thái**, **ai được phép sửa**, **cần trả bản sao ở mức nào**, và **bất biến nghiệp vụ nào phải giữ**.

## 2. Phân biệt các khái niệm hay nhầm

**Mutable object:** có trạng thái có thể thay đổi sau khi tạo; ví dụ mảng, `ArrayList`, `HashMap`, `StringBuilder`, `java.util.Date`.

**Immutable object:** hợp đồng kiểu không cho thay đổi trạng thái quan sát được sau khi tạo; ví dụ `String`, `LocalDate`, `Integer`. Một record không tự trở thành *deeply immutable* khi component giữ mảng hoặc list mutable.

**Unmodifiable collection:** một collection mà các thao tác sửa cấu trúc qua giao diện trả về bị từ chối. Điều này **chưa bảo đảm** dữ liệu bên dưới hoặc object phần tử bất biến.

**Defensive copy:** tạo đối tượng hoặc cấu trúc riêng để tránh chia sẻ trạng thái mutable ngoài ý muốn. Sao chép có thể **nông** (*shallow*) hoặc **sâu theo miền dữ liệu** (*deep copy*).

**Snapshot:** kết quả phản ánh trạng thái tại một thời điểm; về sau các cập nhật của nguồn không tự thay nội dung snapshot. Tuy nhiên, nếu snapshot chứa tham chiếu đến mutable elements, bản thân **trạng thái phần tử** vẫn có thể đổi từ ngoài.

**Read-only view:** nơi nhận không có quyền sửa qua view, nhưng view có thể **phản ánh cập nhật** của nguồn bên dưới.

Không nên dùng các từ `final`, `private`, `unmodifiable`, `immutable` và `copy` như thể chúng đồng nghĩa.

## 3. Vì sao `private final` vẫn không đủ?

Xét:

```java
class Scores {
    private final int[] values;

    Scores(int[] values) {
        this.values = values;
    }
}
```

- `private`: một lớp độc lập khác không thể viết `scores.values` trực tiếp.
- `final`: field `values` không được gán sang mảng khác sau khi đã khởi tạo hợp lệ.
- **Không có** điều kiện nào ở trên cấm `values[0] = ...`, kể cả khi được thực hiện từ một alias ngoài lớp.

```java
int[] input = {5};
Scores scores = new Scores(input);
input[0] = -10;
```

Sau đó field `values` vẫn trỏ đúng mảng ban đầu — chính điều này khiến cập nhật từ `input` thấy được qua object.

Đây là ví dụ về **bất biến tham chiếu** nhưng **không phải bất biến nội dung**.

Một lớp thực hiện validation trong constructor cũng có thể bị phá invariant nếu nó tiếp tục giữ đầu vào mutable:

```java
// Ý tưởng dễ lỗi:
if (scores[0] < 0) {
    throw new IllegalArgumentException();
}
this.scores = scores;
```

Caller vẫn có thể sửa `scores[0]` thành số âm sau khi constructor trả về, bỏ qua bước validation.

## 4. Bảo vệ mảng: sao chép khi nhận và khi trả

Với mảng nguyên thủy một chiều như `int[]`, có thể dùng:

- `array.clone()`;
- `Arrays.copyOf(array, array.length)`;
- `System.arraycopy(...)` vào mảng mới có độ dài thích hợp.

**Chỉ sao chép ở một phía là chưa đủ** nếu cả caller đầu vào và caller đầu ra cần bị ngăn sửa nội bộ.

Mẫu thông dụng:

```java
class GradeBook {
    private final int[] grades;

    GradeBook(int[] grades) {
        this.grades = grades.clone(); // Copy đầu vào
    }

    int[] grades() {
        return grades.clone();       // Copy đầu ra
    }
}
```

Mỗi lần gọi `grades()` trả về **mảng mới**. Nếu phần tử là kiểu nguyên thủy thì sao chép một chiều này đủ để tách trạng thái từng phần tử trong mảng.

### 4.1. Chương trình Java 17 hoàn chỉnh

Lưu toàn bộ thành **`SafeArrayDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class GradeBook {
    private final int[] grades;

    GradeBook(int[] source) {
        Objects.requireNonNull(source, "source");
        int[] copy = source.clone();

        for (int grade : copy) {
            if (grade < 0 || grade > 10) {
                throw new IllegalArgumentException("Grade must be 0..10");
            }
        }
        this.grades = copy;
    }

    int[] grades() {
        return grades.clone();
    }

    int at(int index) {
        return grades[index];
    }

    int size() {
        return grades.length;
    }
}

public class SafeArrayDemo {
    public static void main(String[] args) {
        int[] input = {8, 9};
        GradeBook book = new GradeBook(input);

        input[0] = -100;       // Chỉ sửa mảng của caller
        int[] received = book.grades();
        received[1] = -200;    // Chỉ sửa bản sao trả về

        System.out.println(Arrays.toString(input));
        System.out.println(Arrays.toString(received));
        System.out.println(Arrays.toString(book.grades()));
        System.out.println(book.at(0));
        System.out.println(book.size());
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 SafeArrayDemo.java
java SafeArrayDemo
```

**Stdout chính xác:**

```text
[-100, 9]
[8, -200]
[8, 9]
8
2
```

Kết quả chứng minh **hai đường tham chiếu đã được tách**:

1. Caller sửa `input` mà không làm mảng riêng của `GradeBook` đổi.
2. Caller sửa bản `received` mà không làm mảng riêng của `GradeBook` đổi.
3. `book.grades()` vẫn trả dữ liệu ban đầu đã vượt validation.

### 4.2. Sao chép rồi mới kiểm tra dữ liệu

Ví dụ thực hiện `source.clone()` trước rồi duyệt **bản sao**. Trong thiết kế cần chống thay đổi đồng thời ngoài ý muốn, mục đích là kiểm tra **đúng dữ liệu sẽ được lưu**, thay vì kiểm tra mảng nguồn rồi lưu mảng khác. Tuy nhiên, sao chép mảng từ đầu vào đang bị nhiều thread thay đổi **không tự bảo đảm một snapshot nguyên tử của cả mảng**; cần thêm giao thức đồng bộ hoặc chỉ nhận dữ liệu có ownership rõ ràng.

`Objects.requireNonNull` cung cấp lỗi rõ khi đầu vào `null` thay vì để `clone()` ném lỗi ngầm không giải thích. Với API khác, bạn có thể chọn chấp nhận `null` theo hợp đồng, nhưng phải nhất quán.

## 5. Khi API không cần trả cả mảng

Một cách hạn chế bề mặt API là **không cung cấp getter trả toàn bộ object mutable** nếu caller chỉ cần vài thao tác đọc:

```java
int gradeAt(int index) {
    return grades[index];
}

int count() {
    return grades.length;
}
```

Ưu điểm:
- Không cần tạo mảng mới mỗi lần đọc một phần tử.
- Không làm lộ tham chiếu mảng.
- Có thể thêm kiểm tra quyền truy cập, bounds, invariant hoặc logging khi cần.

Nếu caller thực sự cần toàn bộ dữ liệu, getter trả **defensive copy** có thể hợp lý:

```java
int[] allGrades() {
    return grades.clone();
}
```

**Trade-off:** defensive copy cấp phát và sao chép `O(n)` với mảng độ dài `n`; API đọc từng phần tử có thể tiết kiệm hơn nhưng đòi nhiều lời gọi. Chọn theo nhu cầu thật, không phơi cả collection chỉ vì thuận tiện.

## 6. Mảng hai chiều và mảng chứa object: `clone()` chỉ sao chép nông

Một mảng Java nhiều chiều là **mảng có phần tử là tham chiếu tới các mảng khác**. Vì vậy:

```java
int[][] original = {{1, 2}, {3, 4}};
int[][] shallow = original.clone();

shallow[0][0] = 99;
System.out.println(original[0][0]); // 99
```

`original` và `shallow` là hai mảng ngoài **khác nhau**, nhưng `original[0] == shallow[0]` là `true` do chúng vẫn trỏ tới **cùng mảng hàng đầu tiên**.

### Sao chép từng hàng

Một cách sao chép cấu trúc cho `int[][]` là:

```java
static int[][] copyMatrix(int[][] source) {
    int[][] result = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        result[i] = source[i].clone();
    }
    return result;
}
```

Đây là đoạn phương thức minh họa giả sử `source` và từng hàng đều khác `null`. Nó tạo:
- Mảng ngoài mới;
- Một mảng hàng mới cho mỗi hàng;
- Các `int` được sao chép theo giá trị.

Vì `int` là primitive, kết quả tách được trạng thái các phần tử. Nếu một hàng có thể `null`, cần quy tắc riêng cho `null`; không gọi `clone()` trực tiếp lên hàng null.

### Chương trình hoàn chỉnh: shallow và sao chép từng hàng

Lưu **`MatrixCopyDemo.java`**:

```java
import java.util.Arrays;

public class MatrixCopyDemo {
    static int[][] copyMatrix(int[][] source) {
        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = source[i].clone();
        }
        return result;
    }

    public static void main(String[] args) {
        int[][] original = {{1, 2}, {3, 4}};
        int[][] shallow = original.clone();
        int[][] independent = copyMatrix(original);

        shallow[0][0] = 90;
        independent[1][1] = 80;

        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(shallow));
        System.out.println(Arrays.deepToString(independent));
        System.out.println(original[0] == shallow[0]);
        System.out.println(original[0] == independent[0]);
    }
}
```

```bash
javac -encoding UTF-8 MatrixCopyDemo.java
java MatrixCopyDemo
```

**Stdout:**

```text
[[90, 2], [3, 4]]
[[90, 2], [3, 4]]
[[1, 2], [3, 80]]
true
false
```

**Cẩn thận:** với `Person[]`, `clone()` tạo mảng mới nhưng giữ nguyên **tham chiếu Person** trong từng ô. Nếu `Person` mutable, một caller có thể sửa `copy[0].setName(...)` và làm object `Person` của mảng gốc đổi theo. Khi đó cần **sao chép phần tử theo hợp đồng**, không chỉ clone mảng.

## 7. Collection mutable: getter trả thẳng danh sách có vấn đề gì?

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

class Team {
    private final List<String> members = new ArrayList<>();

    List<String> members() {
        return members;   // Trả object nội bộ trực tiếp
    }
}
```

Caller có thể:

```java
Team team = new Team();
team.members().add("Bình");
team.members().clear();
```

Mọi thao tác này thay đổi **list nội bộ**, mặc dù `members` là `private final`. Nếu lớp `Team` định kiểm soát việc thêm thành viên qua `addMember` (chẳng hạn kiểm tra tên trùng hoặc giới hạn số lượng), caller đã **bỏ qua invariant**.

Đây là trường hợp lộ biểu diễn nội bộ qua **getter**.

### Giải pháp tùy nhu cầu

- **Unmodifiable view:** `Collections.unmodifiableList(members)` ngăn caller sửa qua view nhưng vẫn phản ánh các thay đổi sau đó của backing list.
- **Unmodifiable snapshot:** `List.copyOf(members)` cho caller danh sách không sửa được và không cần phản ánh thay đổi cấu trúc về sau của `members`, nếu đầu vào là mutable list thông thường.
- **Mutable copy:** `new ArrayList<>(members)` trả cấu trúc danh sách khác; caller có thể tự sửa danh sách nhận được, nhưng không sửa cấu trúc list nội bộ.
- **API đọc có chủ đích:** `size()`, `memberAt(index)`, `contains(...)`, hoặc method trả dữ liệu immutable.

Không có giải pháp duy nhất cho mọi API. Quan trọng là **hợp đồng có tuyên bố snapshot hay live view, mutable copy hay immutable result**.

## 8. `Collections.unmodifiableList` và `List.copyOf` khác nhau

Đây là một trong những khác biệt quan trọng nhất của bài.

### 8.1. Unmodifiable view

```java
List<String> view = Collections.unmodifiableList(source);
```

Các phương thức sửa trực tiếp qua `view` như `add`, `remove`, `set` thường ném `UnsupportedOperationException`.

Nhưng **view được hỗ trợ bởi collection nguồn**. Nếu object `source` được sửa qua **một alias còn quyền**, dữ liệu `view` hiển thị có thể thay đổi.

### 8.2. Unmodifiable snapshot

```java
List<String> snapshot = List.copyOf(source);
```

Với `source` là một `ArrayList<String>` mutable bình thường:

- `snapshot` không cho caller dùng mutator của `List` để sửa cấu trúc.
- Những thay đổi cấu trúc của `source` sau thời điểm sao chép không tự thay `snapshot`.
- Việc sao chép là **nông**: các tham chiếu phần tử được chia sẻ nếu phần tử là object.
- `List.copyOf` từ chối phần tử `null` bằng `NullPointerException`.
- Nếu đầu vào đã là một loại unmodifiable list phù hợp, implementation **có thể trả cùng object** thay vì luôn cấp phát bản sao. Vì thế đừng xây thiết kế dựa vào `snapshot != source` trong mọi trường hợp.

Cả hai kiểu kết quả đều **không tự bảo đảm deep immutability** của các phần tử bên trong.

### 8.3. Ví dụ Java 17 có stdout chính xác

Lưu **`ViewVsSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);
        List<String> mutableCopy = new ArrayList<>(source);

        source.add("Bình");
        mutableCopy.add("Chi");

        System.out.println("Source: " + source);
        System.out.println("View: " + view);
        System.out.println("Snapshot: " + snapshot);
        System.out.println("Mutable copy: " + mutableCopy);

        try {
            view.add("Dũng");
        } catch (UnsupportedOperationException error) {
            System.out.println("View không cho add");
        }

        try {
            snapshot.add("Dũng");
        } catch (UnsupportedOperationException error) {
            System.out.println("Snapshot không cho add");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
```

**Stdout:**

```text
Source: [An, Bình]
View: [An, Bình]
Snapshot: [An]
Mutable copy: [An, Chi]
View không cho add
Snapshot không cho add
```

**Quan sát chính:** gọi `add` qua view bị chặn, nhưng chính view vẫn phản ánh `source.add("Bình")`. Snapshot không thay khi thêm phần tử vào nguồn. Mutable copy cho phép caller sửa độc lập **cấu trúc list**.

## 9. `List.copyOf` chưa bảo vệ trạng thái của phần tử mutable

Nếu `List` chứa object mutable, sao chép cấu trúc chưa đủ.

Ví dụ `Card` có setter:

```java
class Card {
    private String title;

    Card(String title) {
        this.title = title;
    }

    void rename(String newTitle) {
        this.title = newTitle;
    }

    String title() {
        return title;
    }
}
```

Với:

```java
Card card = new Card("A");
List<Card> input = new ArrayList<>();
input.add(card);

List<Card> result = List.copyOf(input);
card.rename("B");
```

Sau đó `result.get(0).title()` là `"B"`, bởi `result.get(0)` vẫn là **chính object `card`**.

**Unmodifiable list không có nghĩa phần tử immutable.** Caller không thể `result.add(...)`, nhưng nếu có tham chiếu đến `Card` thì vẫn có thể `rename`.

### Chương trình runnable cho alias phần tử

Lưu **`MutableElementDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Card {
    private String title;

    Card(String title) {
        this.title = title;
    }

    void rename(String title) {
        this.title = title;
    }

    String title() {
        return title;
    }
}

public class MutableElementDemo {
    public static void main(String[] args) {
        Card card = new Card("Java");
        List<Card> source = new ArrayList<>();
        source.add(card);

        List<Card> snapshot = List.copyOf(source);
        source.clear();

        System.out.println(snapshot.size());
        System.out.println(snapshot.get(0).title());

        card.rename("Java 17");
        System.out.println(snapshot.get(0).title());
        System.out.println(snapshot.get(0) == card);
    }
}
```

```bash
javac -encoding UTF-8 MutableElementDemo.java
java MutableElementDemo
```

**Stdout:**

```text
1
Java
Java 17
true
```

`source.clear()` không xóa phần tử khỏi `snapshot`. Nhưng `snapshot` giữ tham chiếu đến `Card` cũ, nên khi `card.rename(...)` chạy, trạng thái hiển thị trong snapshot thay đổi.

Để tách **cả phần tử mutable**, cần một chính sách copy/immutable representation cho `Card`; ví dụ chuyển thành một record chỉ chứa `String` bất biến, hoặc tạo bản sao của từng `Card`.

## 10. Sao chép sâu theo miền dữ liệu: object chứa object mutable

Không có một lệnh `deepClone(object)` chung trong Java core tự động sao chép đúng mọi đồ thị đối tượng.

Hãy xem một object `Person` chứa `Address` mutable:

```java
class Address {
    private String city;

    Address(String city) {
        this.city = city;
    }

    void setCity(String city) {
        this.city = city;
    }

    String city() {
        return city;
    }
}
```

Nếu constructor `Person` làm `this.address = address;`, caller còn tham chiếu `address` và có thể gọi `address.setCity(...)` để thay trạng thái bên trong `Person`.

Nếu getter làm `return address;`, caller có thể làm `person.address().setCity(...)`. **Cả đầu vào lẫn đầu ra đều có nguy cơ lộ.**

Một giải pháp là **copy ngay tại các ranh giới**:

```java
Person(Address address) {
    this.address = new Address(address.city());
}

Address address() {
    return new Address(address.city());
}
```

Điều này yêu cầu `Address` được thiết kế sao cho lấy `city()` là đủ đại diện cho trạng thái mong muốn và không còn tham chiếu mutable nào khác cần sao chép.

### 10.1. Chương trình hoàn chỉnh

Lưu **`DefensiveObjectDemo.java`**:

```java
import java.util.Objects;

final class Address {
    private String city;

    Address(String city) {
        this.city = Objects.requireNonNull(city, "city");
    }

    Address(Address other) {
        this(other.city);
    }

    String city() {
        return city;
    }

    void setCity(String city) {
        this.city = Objects.requireNonNull(city, "city");
    }
}

final class Person {
    private final String name;
    private final Address address;

    Person(String name, Address address) {
        this.name = Objects.requireNonNull(name, "name");
        this.address = new Address(
                Objects.requireNonNull(address, "address"));
    }

    String name() {
        return name;
    }

    Address address() {
        return new Address(address);
    }

    String city() {
        return address.city();
    }
}

public class DefensiveObjectDemo {
    public static void main(String[] args) {
        Address fromCaller = new Address("Hà Nội");
        Person person = new Person("An", fromCaller);

        fromCaller.setCity("Huế");
        Address returned = person.address();
        returned.setCity("Đà Nẵng");

        System.out.println(fromCaller.city());
        System.out.println(returned.city());
        System.out.println(person.city());
    }
}
```

```bash
javac -encoding UTF-8 DefensiveObjectDemo.java
java DefensiveObjectDemo
```

Stdout:

```text
Huế
Đà Nẵng
Hà Nội
```

Phân tích:
- `Person` không lưu object `Address` của caller; constructor tạo **bản sao**.
- `Person.address()` không trả field `address` trực tiếp; getter tạo **bản sao khác**.
- Việc `fromCaller.setCity(...)` và `returned.setCity(...)` không thay `person.city()`.

**Chính sách sao chép phù hợp với domain:** nếu `Address` còn các field mutable khác, copy constructor phải xử lý chúng. Nếu `Address` chứa một collection mutable, cũng cần xem copy collection và phần tử bên trong.

## 11. Chuyển sang kiểu immutable thay vì copy liên tục

Một chiến lược thường đơn giản hơn là **dùng value object bất biến** cho dữ liệu bên trong.

Ví dụ Java 17:

```java
record Address(String city) {
    Address {
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("city required");
        }
    }
}
```

Ở đây component `city` có kiểu `String`, là kiểu bất biến. `Address` record không cung cấp setter làm đổi thành phố sau khi tạo, nên có thể chia sẻ tham chiếu `Address` an toàn hơn theo hợp đồng giá trị.

Với các field kiểu immutable, việc return reference thường không làm lộ **mutable state của field đó**. Cần phân biệt với record chứa mutable components.

### Record không mặc định deep immutable

```java
record Scores(int[] points) {
}
```

Constructor mặc định của record trên vẫn nhận và lưu **tham chiếu mảng**; accessor `points()` trả mảng đó. Caller có thể sửa phần tử:

```java
int[] source = {7, 8};
Scores scores = new Scores(source);
source[0] = 0;
scores.points()[1] = -1;
```

Không có bất biến sâu dù record component là final.

### 11.1. Bảo vệ record có component mảng

Lưu **`SafeRecordDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record Scores(int[] points) {
    public Scores {
        points = Objects.requireNonNull(points, "points").clone();
    }

    @Override
    public int[] points() {
        return points.clone();
    }
}

public class SafeRecordDemo {
    public static void main(String[] args) {
        int[] input = {7, 8};
        Scores scores = new Scores(input);

        input[0] = 0;
        int[] returned = scores.points();
        returned[1] = -1;

        System.out.println(Arrays.toString(input));
        System.out.println(Arrays.toString(returned));
        System.out.println(Arrays.toString(scores.points()));
    }
}
```

```bash
javac -encoding UTF-8 SafeRecordDemo.java
java SafeRecordDemo
```

**Stdout:**

```text
[0, 8]
[7, -1]
[7, 8]
```

Giải thích:
- **Compact constructor** `public Scores { ... }` kiểm tra và sao chép tham số `points`, sau đó quá trình khởi tạo component field dùng giá trị tham số đã được gán lại.
- Accessor `points()` được override để trả mảng mới.
- Record vẫn có những vấn đề cần cân nhắc liên quan `equals`, `hashCode` và cách so sánh mảng; chúng sử dụng semantics của các component theo quy tắc record, nên mảng có `equals`/`hashCode` dựa trên identity, không tự deep-compare các phần tử. Nếu cần value semantics theo nội dung, phải thiết kế/override phù hợp hoặc ưu tiên component là immutable collection/value object.

Bài học là **record làm các component field final**, nhưng **không tự sao chép hoặc đóng băng object mà component trỏ tới**.

## 12. Bảo vệ danh sách khi nhận từ constructor

Một constructor dễ lộ trạng thái:

```java
class Playlist {
    private final List<String> tracks;

    Playlist(List<String> tracks) {
        this.tracks = tracks; // Lộ qua input
    }
}
```

Nếu caller còn tham chiếu `tracks`, họ có thể `clear()` mà đối tượng `Playlist` quan sát được.

Nếu nội dung là `String` (immutable), một cách tốt là:

```java
Playlist(List<String> tracks) {
    this.tracks = List.copyOf(tracks);
}
```

`List.copyOf`:

- Tạo dữ liệu danh sách không sửa được qua `List` API;
- Duy trì thứ tự phần tử của nguồn;
- Bác bỏ list `null` hoặc phần tử `null`;
- Tách danh sách lưu nội bộ khỏi **cập nhật cấu trúc** của đầu vào mutable thông thường;
- Chỉ sao chép nông những tham chiếu phần tử.

Vì các phần tử là `String` bất biến, không có sự chia sẻ mutable element trong ví dụ này.

### 12.1. Chương trình ví dụ playlist

Lưu thành **`ImmutableListFieldDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Playlist {
    private final List<String> tracks;

    Playlist(List<String> tracks) {
        this.tracks = List.copyOf(tracks);
    }

    List<String> tracks() {
        return tracks;
    }

    int size() {
        return tracks.size();
    }
}

public class ImmutableListFieldDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("Intro");

        Playlist playlist = new Playlist(source);
        source.add("Outro");

        System.out.println(source);
        System.out.println(playlist.tracks());
        System.out.println(playlist.size());

        try {
            playlist.tracks().add("Extra");
        } catch (UnsupportedOperationException error) {
            System.out.println("Không sửa được danh sách trả về");
        }
    }
}
```

```bash
javac -encoding UTF-8 ImmutableListFieldDemo.java
java ImmutableListFieldDemo
```

Stdout:

```text
[Intro, Outro]
[Intro]
1
Không sửa được danh sách trả về
```

Ở đây `Playlist` lưu một `List<String>` không sửa được và mỗi `String` cũng immutable. Vì vậy getter có thể **trả trực tiếp** field `tracks` mà không phải copy mỗi lần.

**Hợp đồng rõ:** `tracks()` trả về dữ liệu không sửa được. Caller muốn chỉnh sửa cho mục đích riêng có thể viết `new ArrayList<>(playlist.tracks())`, nhưng không làm ảnh hưởng object `Playlist`.

## 13. Khi cần danh sách nội bộ vẫn mutable

Một lớp có thể cần thêm/xóa phần tử qua các phương thức riêng, ví dụ quản lý nhóm:

```java
final class Group {
    private final List<String> members = new ArrayList<>();

    void add(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        members.add(name);
    }

    List<String> members() {
        return List.copyOf(members);
    }
}
```

Đây là các khai báo minh họa giả định đã import `java.util.List` và `java.util.ArrayList`.

- `Group.add` là đường cập nhật có validation.
- `Group.members` cho một **snapshot không sửa được** của danh sách ở thời điểm gọi.
- Caller không thể bỏ qua validation bằng cách sửa thẳng backing list thông qua getter.
- Nếu object `Group` thay đổi về sau, snapshot đã trả vẫn giữ **cấu trúc và các `String` cũ**.

### Chi phí và tính nhất quán

Mỗi `List.copyOf(members)` có thể phải sao chép `n` phần tử, chi phí theo kích thước danh sách. Nếu API truy vấn thường xuyên, cân nhắc:
- Trả API `size()`, `memberAt(index)`;
- Cache snapshot bất biến khi trạng thái đổi (phải quản lý invalidation);
- Dùng cấu trúc dữ liệu immutable/persistent phù hợp;
- Trả live unmodifiable view **chỉ khi hợp đồng chấp nhận sự thay đổi của nguồn**.

**Không tối ưu bằng cách tự động trả mutable backing list**: điều đó phá ranh giới đóng gói và có thể gây lỗi khó phát hiện.

## 14. `Collections.unmodifiableList`: khi nào view là đúng?

Live unmodifiable view không luôn sai. Nó thích hợp khi caller **được phép quan sát cập nhật của một đối tượng** nhưng không được sửa qua tham chiếu trả về.

Ví dụ:
- Một UI muốn hiển thị danh sách hiện tại của mô hình và UI chỉ đọc;
- API tài liệu nêu rõ kết quả là **live view**;
- Chủ sở hữu collection giữ độc quyền cập nhật qua method riêng.

Tuy nhiên phải lưu ý:
- Nếu caller còn alias mutable đến backing list, họ vẫn có thể sửa qua alias đó.
- Thay đổi của backing collection có thể làm iterator trên view ném `ConcurrentModificationException` theo cơ chế fail-fast của một số collection; không nên dựa vào exception này để đồng bộ.
- Unmodifiable view **không đảm bảo snapshot độc lập** và **không làm phần tử bất biến**.
- Đối với việc trao dữ liệu qua thread boundary, cần thêm quy tắc an toàn đồng thời.

### Ví dụ phương thức thiết kế live view

```java
class Inventory {
    private final List<String> items = new ArrayList<>();
    private final List<String> readOnly =
            Collections.unmodifiableList(items);

    void add(String item) {
        items.add(item);
    }

    List<String> view() {
        return readOnly;
    }
}
```

Đây là ví dụ minh họa cần các import từ `java.util`. `view()` trả một view không sửa trực tiếp được, nhưng `inventory.add("A")` làm nội dung view đã nhận trước đó thay đổi theo.

Một API nên **đặt tên/tài liệu rõ** `view()` hoặc `snapshot()` để caller không dựa vào giả định sai.

## 15. Các factory collection không sửa được trong Java 17

Các API phổ biến:

| API | Kết quả chính | Chú ý |
| --- | --- | --- |
| `List.of("A", "B")` | Danh sách unmodifiable | Không chấp nhận `null` |
| `List.copyOf(collection)` | Danh sách unmodifiable từ collection nguồn | Shallow; không nhất thiết cấp phát object mới nếu nguồn đã phù hợp |
| `Set.of("A", "B")` | Tập hợp unmodifiable | Không chấp nhận `null`, phần tử trùng có thể gây `IllegalArgumentException` khi truyền trực tiếp vào factory |
| `Set.copyOf(collection)` | Tập hợp unmodifiable | Từ collection có phần tử trùng, kết quả là tập phần tử duy nhất; không xác định trình tự duyệt |
| `Map.of("A", 1)` | Map unmodifiable | Không chấp nhận key/value `null` |
| `Map.copyOf(map)` | Map unmodifiable từ nguồn | Shallow; key/value object có thể mutable |
| `Collections.unmodifiableList(list)` | Unmodifiable view | Phản ánh cập nhật backing list |
| `Collections.unmodifiableMap(map)` | Unmodifiable view của map | Phản ánh cập nhật backing map |

**“Không sửa được collection” chỉ bảo vệ giao diện thay đổi cấu trúc.** Nếu key/value hoặc element là object mutable, việc thay đổi **trạng thái của object phần tử** có thể vẫn diễn ra qua alias.

### Chú ý với `List.copyOf`

`List.copyOf` bác bỏ `null` cả khi chính đầu vào null và khi có phần tử null. Vì thế đừng thay `new ArrayList<>(source)` bằng `List.copyOf(source)` mà không xem hợp đồng về null.

Nếu dữ liệu phải chấp nhận null, cần quy ước khác (chẳng hạn lọc/biểu diễn Optional hợp lý, dùng bản sao riêng và view), không cố buộc factory có hợp đồng từ chối null nhận null.

## 16. `Arrays.asList` không phải một bản sao an toàn

`Arrays.asList(array)` trả danh sách kích thước cố định **được hỗ trợ bởi mảng đã truyền** đối với overload thông thường dùng mảng reference.

```java
String[] array = {"A", "B"};
List<String> list = Arrays.asList(array);

array[0] = "X";
list.set(1, "Y");
```

Sau đó:
- `list` hiển thị `[X, Y]`;
- `array` chứa `["X", "Y"]`.

`list.add("Z")` không được hỗ trợ vì kích thước cố định, nhưng `set` có thể sửa phần tử và **mảng gốc thay đổi theo**.

### Chương trình minh họa

Lưu **`ArraysAsListDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;

public class ArraysAsListDemo {
    public static void main(String[] args) {
        String[] data = {"A", "B"};
        List<String> view = Arrays.asList(data);

        data[0] = "X";
        view.set(1, "Y");

        System.out.println(Arrays.toString(data));
        System.out.println(view);

        try {
            view.add("Z");
        } catch (UnsupportedOperationException error) {
            System.out.println("Không thể thêm phần tử");
        }
    }
}
```

```bash
javac -encoding UTF-8 ArraysAsListDemo.java
java ArraysAsListDemo
```

Stdout:

```text
[X, Y]
[X, Y]
Không thể thêm phần tử
```

**Nếu mục tiêu là defensive copy**, `Arrays.asList(input)` **một mình không đủ**. Có thể dùng `List.copyOf(Arrays.asList(input))` nếu đầu vào phù hợp và không chứa null, nhưng với element mutable vẫn phải xét shallow copy.

**Với mảng primitive**, `Arrays.asList(intArray)` có hành vi generic khác: nó thường cho một list có một phần tử là **toàn bộ mảng `int[]`**, không phải list các `Integer` như nhiều người tưởng. Nếu muốn collection số nguyên, cần chuyển từng giá trị theo thiết kế, ví dụ `IntStream.of(data).boxed().toList()` trong Java 17, và nhớ rằng `Stream.toList()` trả unmodifiable list.

## 17. Map: không lộ cấu trúc, cũng không lộ mutable values

Một `Map` có thể chứa giá trị kiểu mutable:

```java
Map<String, List<String>> roles = new HashMap<>();
roles.put("admin", new ArrayList<>(List.of("read")));
```

Nếu trả:

```java
return Map.copyOf(roles);
```

thì kết quả là map unmodifiable (không cho `put` hoặc `remove` qua map ấy). Nhưng giá trị của key `"admin"` vẫn có thể là **cùng object `ArrayList<String>`** mà `roles` giữ.

Caller có thể:

```java
Map<String, List<String>> exposed = Map.copyOf(roles);
exposed.get("admin").add("write");
```

Điều này **sửa list nằm bên trong**, dù không thay cấu trúc map. `Map.copyOf` không tự deep-copy các value.

### 17.1. Bản sao theo từng tầng

Nếu muốn tạo kết quả có **String keys** và **list of Strings immutable**, có thể sao chép list value trước rồi đóng gói map:

```java
static Map<String, List<String>> snapshot(
        Map<String, List<String>> source) {

    Map<String, List<String>> copy = new HashMap<>();
    for (Map.Entry<String, List<String>> entry : source.entrySet()) {
        copy.put(entry.getKey(), List.copyOf(entry.getValue()));
    }
    return Map.copyOf(copy);
}
```

Đoạn này là minh họa cần import `java.util.Map`, `java.util.HashMap` và `java.util.List`. Nó giả định không có key/value/list element null. Vì key và phần tử đều `String` bất biến, đây là một snapshot an toàn về **cấu trúc map và các list value** trong phạm vi ví dụ.

Nếu value chứa object mutable (như `List<Card>`), vẫn cần tách hoặc chuyển chúng sang immutable value representation.

### 17.2. Chương trình Java 17 hoàn chỉnh

Lưu **`NestedMapCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class NestedMapCopyDemo {
    static Map<String, List<String>> snapshot(
            Map<String, List<String>> source) {

        Map<String, List<String>> copy = new HashMap<>();
        for (Map.Entry<String, List<String>> entry : source.entrySet()) {
            copy.put(entry.getKey(), List.copyOf(entry.getValue()));
        }
        return Map.copyOf(copy);
    }

    public static void main(String[] args) {
        List<String> permissions = new ArrayList<>(List.of("read"));
        Map<String, List<String>> source = new HashMap<>();
        source.put("admin", permissions);

        Map<String, List<String>> result = snapshot(source);
        permissions.add("write");
        source.put("guest", List.of("view"));

        System.out.println(source.get("admin"));
        System.out.println(result.get("admin"));
        System.out.println(result.containsKey("guest"));

        try {
            result.get("admin").add("delete");
        } catch (UnsupportedOperationException error) {
            System.out.println("Không thể sửa nested list");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 NestedMapCopyDemo.java
java NestedMapCopyDemo
```

**Stdout:**

```text
[read, write]
[read]
false
Không thể sửa nested list
```

Ví dụ cố tình **không in trực tiếp toàn bộ HashMap/Map.copyOf** vì thứ tự duyệt map có thể khác nhau. Việc truy cập qua key cụ thể cho stdout ổn định.

## 18. Set và đối tượng làm phần tử: một bẫy khác

`Set.copyOf(source)` ngăn caller thay đổi cấu trúc set qua interface, nhưng **không copy sâu object phần tử**.

Thêm nữa, khi phần tử là object mutable dùng làm khóa hash, một thay đổi tới các field tham gia `equals`/`hashCode` có thể làm collection hoạt động khó dự đoán.

Ví dụ thiết kế nên tránh:

```java
class MutableKey {
    String code;

    // equals/hashCode dựa trên code và code có thể thay đổi.
}
```

Nếu một `HashSet<MutableKey>` đã thêm key rồi `key.code` bị sửa, thao tác `contains` có thể không tìm thấy key như kỳ vọng vì hash thay đổi.

Defensive copy **cấu trúc Set** không giải quyết triệt để vấn đề **mutable element equality/hash**. Thường nên dùng immutable value objects làm phần tử của set và key của map.

### `Set.copyOf` và giá trị trùng

Nếu đầu vào là collection có phần tử trùng nhau, `Set.copyOf` tạo set những phần tử duy nhất theo quy tắc. Kết quả không bảo đảm giữ thứ tự duyệt của list nguồn.

Đừng dùng Set khi hợp đồng cần giữ số lần lặp hoặc thứ tự. Khi snapshot hóa dữ liệu, **chọn kiểu collection đúng ngữ nghĩa** còn quan trọng hơn chọn API copy.

## 19. Ngăn lộ `java.util.Date`, `Calendar` và một số kiểu mutable chuẩn

Không chỉ collection tự viết mới có nguy cơ. `java.util.Date` và `Calendar` là những kiểu mutable.

Ví dụ lộ field `Date`:

```java
class Event {
    private final java.util.Date startsAt;

    Event(java.util.Date startsAt) {
        this.startsAt = startsAt;
    }

    java.util.Date startsAt() {
        return startsAt;
    }
}
```

Caller có thể dùng `Date.setTime(...)` trên tham số ban đầu hoặc getter trả ra để thay thời gian nội bộ.

Một cách bảo vệ:

```java
Event(Date startsAt) {
    this.startsAt = new Date(startsAt.getTime());
}

Date startsAt() {
    return new Date(startsAt.getTime());
}
```

Trong ví dụ trên, `Date` lưu **giá trị mili-giây thời điểm**. Copy constructor logic dựa trên `getTime`/`new Date(long)` tạo object khác để tách mutation; null cần được xử lý theo contract. Với một domain phức tạp hơn, cần xét cách so sánh và tính hợp lệ của thời gian.

### Chương trình hoàn chỉnh

Lưu **`DateDefensiveDemo.java`**:

```java
import java.util.Date;

final class Event {
    private final Date timestamp;

    Event(Date source) {
        this.timestamp = new Date(source.getTime());
    }

    Date timestamp() {
        return new Date(timestamp.getTime());
    }

    long epochMillis() {
        return timestamp.getTime();
    }
}

public class DateDefensiveDemo {
    public static void main(String[] args) {
        Date input = new Date(1000L);
        Event event = new Event(input);

        input.setTime(2000L);
        Date returned = event.timestamp();
        returned.setTime(3000L);

        System.out.println(input.getTime());
        System.out.println(returned.getTime());
        System.out.println(event.epochMillis());
    }
}
```

```bash
javac -encoding UTF-8 DateDefensiveDemo.java
java DateDefensiveDemo
```

Stdout:

```text
2000
3000
1000
```

Để giảm nhu cầu defensive copy, khi phù hợp nên ưu tiên những value types bất biến của `java.time` như `Instant`, `LocalDate`, `LocalDateTime` hoặc `ZonedDateTime`. Cần chọn đúng loại thời gian theo yêu cầu nghiệp vụ, không thay `Date` bằng `LocalDate` nếu dự án cần một **thời điểm chính xác trên timeline**.

## 20. Getter trả stream, iterator hoặc sublist có làm lộ dữ liệu?

Không chỉ getter trả `List` mới có nguy cơ.

### Trả `Iterator` trên collection nội bộ

```java
Iterator<String> iterator() {
    return items.iterator();
}
```

Một iterator của mutable collection có thể cho phép `remove()` nếu implementation hỗ trợ, qua đó sửa cấu trúc collection. Ngay cả iterator không hỗ trợ remove cũng có thể quan sát trạng thái đang thay đổi.

**Giải pháp có thể:** trả iterator của snapshot không sửa được:

```java
Iterator<String> iterator() {
    return List.copyOf(items).iterator();
}
```

Vẫn là shallow copy các element objects và có chi phí sao chép. Hoặc thiết kế API chỉ truy cập từng giá trị.

### Trả `subList`

```java
List<String> firstTwo() {
    return items.subList(0, 2);
}
```

Với các `List` thông dụng, `subList` trả **view được hỗ trợ bởi danh sách gốc**. Thao tác `set`/`clear` qua view có thể tác động backing list; những thay đổi cấu trúc từ nơi khác còn có thể làm semantics của view không xác định theo contract.

Nếu muốn snapshot độc lập:

```java
List<String> firstTwo() {
    return List.copyOf(items.subList(0, Math.min(2, items.size())));
}
```

### Trả `Stream`

```java
Stream<String> stream() {
    return items.stream();
}
```

Một stream **không phải snapshot tự động**. Với nguồn mutable, việc sử dụng stream về sau có thể phụ thuộc trạng thái nguồn và quy tắc xử lý stream/spliterator. Không nên mô tả rằng vì không có `add()` trên `Stream` nên đã hoàn toàn bảo vệ trạng thái nội bộ.

Nếu API yêu cầu dữ liệu chụp tại một thời điểm, có thể tạo **snapshot trước khi cung cấp stream**, ví dụ `List.copyOf(items).stream()`, và phải xem element mutable.

## 21. Constructor, setter và builder đều có đường lộ ở đầu vào

Nguy cơ không chỉ xuất hiện ở getter. Một lớp có thể giữ trực tiếp mutable input ở:

- Constructor;
- Setter;
- Builder;
- Factory method;
- Method đăng ký callback/observer;
- Method nhận collection rồi giữ lại tham chiếu để xử lý sau.

Ví dụ setter:

```java
void replaceTags(List<String> tags) {
    this.tags = tags;
}
```

Ngay sau lời gọi `model.replaceTags(input)`, caller vẫn có `input` và có thể gọi `input.clear()` để đổi trạng thái model.

Với field được thiết kế immutable:

```java
void replaceTags(List<String> tags) {
    this.tags = List.copyOf(tags);
}
```

Nếu yêu cầu chấp nhận null hoặc element mutable, phải xử lý các trường hợp ấy theo hợp đồng.

### Builder có thể vô tình chuyển alias sang sản phẩm

Một builder giữ mutable list:

```java
class RequestBuilder {
    List<String> headers = new ArrayList<>();

    Request build() {
        return new Request(headers); // Nguy cơ nếu Request lưu trực tiếp
    }
}
```

Nếu `Request` lưu cùng list và builder tiếp tục được dùng để thêm header sau `build()`, sản phẩm `Request` đã tạo có thể bị đổi theo.

**Giải pháp:** `Request` constructor (hoặc `build()`) phải snapshot/copy theo ownership contract. Đối với kiểu dữ liệu immutable elements, một `List.copyOf(headers)` có thể đủ.

Về thiết kế, **nơi tạo lớp bất biến nên tự bảo vệ invariant của nó**, không dựa hoàn toàn vào việc mỗi caller/builder luôn nhớ copy.

## 22. Đặt defensive copy trước hay sau validation?

Có hai vấn đề cần phân biệt:

1. **Validation tính hợp lệ**: dữ liệu thỏa domain constraints không?
2. **Ownership isolation**: object lưu lại có còn bị alias bên ngoài sửa được không?

Một mẫu tương đối vững khi nhận mảng mutable:

```java
int[] localCopy = Objects.requireNonNull(input).clone();
for (int value : localCopy) {
    if (value < 0) {
        throw new IllegalArgumentException("negative value");
    }
}
this.values = localCopy;
```

Lợi ích: kiểm tra **chính dữ liệu được lưu**, tránh tình huống kiểm tra một object rồi lưu tham chiếu object khác hoặc lưu original mutable input.

Tuy nhiên, nếu input có thể bị sửa đồng thời giữa những lần đọc trong quá trình `clone`, phép clone không tự biến cả quá trình thành một transaction. **Copy + validate** không thay thế quy tắc thread-safety của data source; việc nhận dữ liệu cần ranh giới ownership hoặc đồng bộ rõ.

Khi input là một loại immutable và đã bảo đảm hợp đồng, việc copy có thể không cần thiết.

### Có nên validate xong mới copy?

Nếu data source không bị thay đổi đồng thời, validate trên input rồi copy có thể cho kết quả đúng trong nhiều chương trình. Nhưng mẫu **copy trước, validate chính bản copy** thường dễ chứng minh invariant hơn, đặc biệt khi contract của constructor hứa object lưu trữ chính dữ liệu đã được kiểm tra.

Quan trọng nhất: **không giữ alias mutable của caller nếu không có quyền sở hữu/thỏa thuận chia sẻ rõ ràng**.

## 23. Defensive copy và yêu cầu hiệu năng

Sao chép không miễn phí:

| Thao tác | Chi phí thường gặp |
| --- | --- |
| `array.clone()` với `n` phần tử | Thời gian và bộ nhớ `O(n)` |
| `new ArrayList<>(source)` | Sao chép cấu trúc khoảng `O(n)` |
| `List.copyOf(source)` | Thường khoảng `O(n)` để sao chép nguồn mutable; có thể tái sử dụng input đã unmodifiable phù hợp |
| Deep copy graph đối tượng | Phụ thuộc số object, liên kết và chính sách sao chép |
| Getter trả scalar `int`/`long` | Thường không cần cấp phát bản sao object |
| Getter trả immutable value | Thường có thể chia sẻ tham chiếu an toàn hơn |

**Tối ưu theo hợp đồng trước:**

1. Nếu caller chỉ cần tổng/số lượng, trả scalar thay vì collection.
2. Nếu data immutable, có thể chia sẻ theo hợp đồng.
3. Nếu cần snapshot nhiều lần, cân nhắc cache snapshot khi state thay đổi.
4. Nếu data lớn, tránh tạo bản sao sâu không cần thiết khi caller chỉ đọc một phần.
5. Nếu API phải trả live view, nêu rõ và bảo vệ mọi đường mutation của backing collection.

**Không** nên chuyển sang lộ mutable reference chỉ vì thấy copy có chi phí. Trước tiên xác định tần suất, kích thước, mô hình ownership và tính đúng đắn.

## 24. Ownership: khi nào có thể chia sẻ một object mutable?

Không phải mọi trường hợp cùng giữ tham chiếu mutable đều sai. Có những API **cố ý chia sẻ trạng thái**, chẳng hạn:
- Một đối tượng session dùng chung có hợp đồng cập nhật rõ;
- Một editor thao tác trên model hiện tại;
- Một collection do caller sở hữu mà API chỉ xử lý tức thời, không giữ sau khi method kết thúc;
- Những abstraction concurrency cho phép cập nhật chung một object.

Điều đáng ngại là **chia sẻ không được công bố**, nhất là khi:
- Class hứa trạng thái bất biến nhưng giữ input mutable;
- Getter trông như đọc dữ liệu nhưng trả object có thể sửa nội bộ;
- Setter/constructor validation bị caller phá sau đó;
- Nhiều thread cùng giữ mutable reference mà không có synchronization contract.

Một mô hình tốt xác định ai **được quyền sửa**, object có còn bị giữ lại sau lời gọi không và thời điểm dữ liệu được quan sát.

### Đừng gọi mọi object được trả về là “bản sao sâu”

Ví dụ `new ArrayList<>(source)` là một **new list** nhưng thường chỉ là **shallow copy**. Tên method nên làm rõ `snapshotTags()` hoặc `copyTags()` theo đúng dữ liệu đã tách, thay vì `deepCopy` khi còn mutable element alias.

## 25. Thread-safety: defensive copy không tự cung cấp snapshot nguyên tử

Một ví dụ:

```java
List<String> snapshot = List.copyOf(sharedMutableList);
```

Nếu **thread khác đang sửa sharedMutableList không đồng bộ**, quá trình copy có thể gặp lỗi hoặc quan sát dữ liệu thiếu nhất quán tùy collection và thời điểm. Câu lệnh trên **không tự tạo một khóa toàn cục**.

Một lớp thread-safe phải xét:
- Tất cả những đường có thể cập nhật trạng thái;
- Visibility giữa thread, `happens-before` và synchronization;
- Tính nguyên tử của thao tác đọc-sửa-ghi;
- Thời điểm snapshot được tạo;
- Việc công bố an toàn (*safe publication*) những object đã xây dựng.

Với một list được bảo vệ bằng lock, snapshot có thể được tạo **trong cùng lock** mà mọi writer tuân thủ. Sau đó caller đọc snapshot không sửa được và chứa immutable elements có thể giảm nhu cầu đồng bộ đọc.

`Collections.unmodifiableList` chỉ chặn mutator qua view, **không** biến backing list thành thread-safe. `List.copyOf` cũng không tự sửa mọi vấn đề concurrency ở thời điểm đọc nguồn.

## 26. Chống lộ state khi dùng map key và equals/hashCode

Khi dùng mutable object làm `Map` key hoặc `Set` element, thay đổi những field liên quan `equals`/`hashCode` sau khi đưa object vào hash-based collection có thể phá tính nhất quán của tra cứu.

Một cách giảm rủi ro:
- Dùng immutable value objects làm key, ví dụ `String`, `UUID` hoặc record chỉ chứa các component thực sự immutable;
- Nếu phải nhận mutable key object, tạo canonical immutable representation hoặc defensive copy phù hợp;
- Đừng trả ra object key nội bộ mutable cho caller tùy ý chỉnh.

**Map.copyOf** ngăn thêm/xóa entry qua map được trả về, nhưng nó **không làm key mutable trở thành immutable**, cũng không tự deep-copy key/value. Đóng gói cần được kiểm tra ở **mọi nút mutable trong cấu trúc dữ liệu**.

## 27. Phân biệt *defensive copy* với *unmodifiable wrapper*

Tóm tắt theo câu hỏi:

| Cách trả dữ liệu | Caller sửa cấu trúc kết quả? | Nguồn sửa cấu trúc về sau có ảnh hưởng kết quả? | Mutable element alias còn? |
| --- | --- | --- | --- |
| `return internalList;` | Có nếu list mutable | Có, vì cùng object | Có |
| `return Collections.unmodifiableList(internalList);` | Không qua view | **Có**, vì backing list dùng chung | Có |
| `return new ArrayList<>(internalList);` | **Có**, nhưng trên list khác | **Không** với cấu trúc list | Có |
| `return List.copyOf(internalList);` | **Không** qua snapshot | Không với cấu trúc từ nguồn mutable thông thường | Có |
| Trả list immutable của immutable values | Không | Không theo hợp đồng snapshot | Không có mutable element state tương ứng |
| Sao chép từng mutable element rồi đóng gói | Không nếu output cũng unmodifiable | Không khi tất cả mutable paths được tách đúng | Tùy mức độ deep copy đã thực hiện |

**Kết luận thực tế:** mục tiêu không nhất thiết phải “deep copy mọi thứ”. Hãy xác định **cấp dữ liệu cần bất biến**. Ví dụ danh sách `String` chỉ cần `List.copyOf`; danh sách `Address` mutable cần thiết kế thêm về phần tử.

## 28. Ngăn lộ mảng byte trong đối tượng chứa dữ liệu nhạy cảm

Một ứng dụng có thể giữ khóa, mã bí mật hoặc payload dưới dạng `byte[]`. Ngoài tính đúng đắn, việc trả mảng trực tiếp còn cho phép caller **sửa dữ liệu ngoài tầm kiểm soát**.

Ví dụ:

```java
final class Packet {
    private final byte[] payload;

    Packet(byte[] payload) {
        this.payload = payload.clone();
    }

    byte[] payload() {
        return payload.clone();
    }
}
```

Ở đây mỗi bên nhận một bản sao mảng. Nhưng **copy không tự giải quyết vấn đề bảo mật của dữ liệu bí mật**, vì bộ nhớ có thể có các bản sao còn tồn tại, GC không cam kết xóa ngay và hệ thống có thể có những yêu cầu quản lý vòng đời đặc biệt.

Nếu quản lý secret bytes thực sự, cần chính sách rõ về thời điểm xóa bản sao, các lớp được phép xử lý, tránh logging, concurrency và các giới hạn của bộ nhớ JVM. Bài này tập trung vào **ngăn sửa trạng thái từ alias**, không tuyên bố rằng `clone()` bảo đảm xóa dữ liệu nhạy cảm khỏi bộ nhớ.

## 29. Test đóng gói: thử “tấn công” cả đầu vào lẫn đầu ra

Một cách kiểm tra thiết kế là viết test cố gắng thay object từ phía caller.

### Quy trình test với mảng

1. Tạo mảng nguồn `input`.
2. Gọi constructor `new Holder(input)`.
3. Sửa `input[0]`.
4. Kiểm tra trạng thái Holder **không thay**.
5. Lấy `int[] output = holder.values()`.
6. Sửa `output[0]`.
7. Kiểm tra Holder **vẫn không thay**.

### Quy trình test với list

1. Tạo `ArrayList` mutable đầu vào.
2. Tạo object chứa list từ input.
3. Gọi `input.add(...)` hoặc `input.clear()`.
4. Kiểm tra snapshot/list nội bộ không thay ngoài contract.
5. Nhận list từ getter.
6. Thử `getterResult.add(...)` và xác định nên bị chặn hay chỉ sửa bản sao.
7. Nếu list chứa mutable object, thử **sửa trạng thái của phần tử**.
8. Nếu object có nhiều collection lồng nhau, thử sửa từng cấp.

### Quan sát identity khi cần

`result == internal` có thể hữu ích trong test riêng nằm **bên trong phạm vi được phép**, nhưng không nên coi việc identity khác nhau là bằng chứng đủ cho **deep copy**. Hai outer lists khác nhau vẫn có thể giữ cùng mutable element.

**Hợp đồng kiểm tra cần tập trung vào state/invariant**, không bắt mọi getter phải trả object mới trong mọi trường hợp. Nếu field thực sự immutable, trả cùng object thường là hợp lệ.

## 30. Lỗi thường gặp và cách khắc phục

| Tình huống | Sai ở đâu? | Cách cải thiện |
| --- | --- | --- |
| `private final int[] data` nhưng getter trả `data` | Lộ mảng qua output | `return data.clone();` |
| Constructor `this.data = input;` | Caller giữ alias đầu vào | Copy input trước khi lưu |
| `return new ArrayList<>(items)` rồi tưởng deep copy | Elements vẫn dùng chung | Copy mutable elements hoặc dùng immutable values |
| `return Collections.unmodifiableList(items)` rồi nghĩ là snapshot | View có thể phản ánh mutation backing list | Dùng `List.copyOf(items)` nếu cần snapshot |
| `List.copyOf(cards)` rồi caller sửa `Card` được | Copy shallow element references | Copy từng `Card` hoặc chuyển sang immutable records/DTOs |
| `return Arrays.asList(data);` | View gắn với mảng, `set` có thể đổi mảng | Snapshot như `List.copyOf(Arrays.asList(data))` khi phù hợp |
| Getter trả `Date` trực tiếp | `Date.setTime` làm đổi object nội bộ | Copy `Date` hai phía hoặc dùng `Instant` |
| Record giữ `int[]` rồi tưởng immutable | Record chỉ shallow immutable components | Compact constructor copy và accessor copy |
| `final List<String> items` rồi nghĩ không thêm được | Final cấm gán lại field, không cấm mutate list | Unmodifiable data hoặc API mutation được kiểm soát |
| `Map.copyOf` nhưng nested list vẫn sửa được | Map chỉ unmodifiable ở cấp map | Copy nested collection/values |
| `List.copyOf` gặp null | API từ chối null | Định nghĩa contract null, lọc hoặc chọn representation khác |
| `List.of(...)` mà cố `add`/`remove` | Factory tạo list unmodifiable | Dùng mutable copy nếu thật sự cần sửa |
| `List.copyOf` luôn tạo object mới | Implementation có thể reuse unmodifiable input | Test semantics, không dựa vào identity |
| Getter chỉ trả `Stream` nhưng nguồn mutable | Stream không tự là snapshot | Tạo snapshot trước nếu cần |
| Setter lưu list mà builder còn thay | Builder và sản phẩm dùng chung backing list | Copy khi build/construct |
| `clone()` mảng hai chiều rồi mutate hàng | Clone outer array là shallow | Copy từng inner array |
| `HashSet` chứa mutable key thay `hashCode` | Hash lookup có thể không ổn định | Dùng immutable key |
| Copy list khi thread khác đang ghi | Copy không tự atomic/thread-safe | Ownership hoặc đồng bộ |
| Public getter trả mutable object nội bộ | Bỏ qua validation của owner | Trả copy/immutable view hoặc API đọc |
| Getter dùng defensive copy nhưng constructor không copy | Input alias vẫn lộ state | Kiểm tra **cả hai chiều** |
| Constructor copy nhưng getter trả field trực tiếp | Output alias vẫn lộ | Kiểm tra **cả hai chiều** |
| Deep copy bằng serialization tự động | Giả định mọi loại đều serializable/copy đúng | Thiết kế copy theo domain, object graph, tài nguyên và contract |

## 31. Bài tập tự luyện có đáp án

### Bài 1 — `private final` đã an toàn chưa?

```java
class Scores {
    private final int[] data;

    Scores(int[] data) {
        this.data = data;
    }

    int[] getData() {
        return data;
    }
}
```

**Câu hỏi:** có hai cách nào để caller sửa nội bộ mà không gọi mutator?

**Đáp án:** (1) sửa mảng `data` gốc sau khi đưa vào constructor, (2) sửa mảng nhận từ `getData()`. `private final` không chặn mutation của object mảng. Cần copy ở đầu vào và đầu ra, hoặc thiết kế API không trả mảng.

### Bài 2 — Unmodifiable view có đứng yên không?

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
source.add("B");
System.out.println(view);
```

**Đáp án:** `[A, B]`. View không cho sửa trực tiếp qua chính nó, nhưng phản ánh cấu trúc backing list bị thay bởi alias `source`.

### Bài 3 — Snapshot list có cho thấy update nguồn?

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(source);
source.add("B");
System.out.println(snapshot);
```

**Đáp án:** `[A]`. Cấu trúc snapshot không đổi theo update `source`. Vì `String` immutable, cũng không có mutable state phần tử cần lo trong ví dụ này.

### Bài 4 — Sao chép nông có bảo vệ `Card`?

```java
Card card = new Card("A");
List<Card> source = new ArrayList<>(List.of(card));
List<Card> snapshot = List.copyOf(source);
card.rename("B");
System.out.println(snapshot.get(0).title());
```

**Đáp án:** `B`. Snapshot giữ cùng tham chiếu `Card`. Muốn đóng gói trạng thái Card, cần copy element hoặc chuyển thành immutable representation.

### Bài 5 — Mảng hai chiều

```java
int[][] a = {{1}, {2}};
int[][] b = a.clone();
b[0][0] = 7;
System.out.println(a[0][0]);
```

**Đáp án:** `7`. `clone()` chỉ copy mảng ngoài; `a[0]` và `b[0]` cùng trỏ đến hàng đầu. Để tách primitive matrix, cần clone từng hàng.

### Bài 6 — `Arrays.asList` có độc lập không?

```java
String[] array = {"A"};
List<String> view = Arrays.asList(array);
view.set(0, "B");
System.out.println(array[0]);
```

**Đáp án:** `B`. `Arrays.asList` trả view gắn với mảng, không phải defensive copy.

### Bài 7 — Record có tự bất biến sâu?

```java
record ScoreRecord(int[] values) {
}
```

**Đáp án:** **Không.** Truyền mảng vào canonical constructor và nhận mảng qua accessor mặc định có thể làm lộ cùng object mutable. Cần copy trong constructor/accessor hoặc chọn kiểu dữ liệu immutable.

### Bài 8 — Map không sửa được, value vẫn sửa được?

```java
List<String> values = new ArrayList<>(List.of("read"));
Map<String, List<String>> source = Map.of("admin", values);
Map<String, List<String>> copied = Map.copyOf(source);
values.add("write");
System.out.println(copied.get("admin"));
```

**Đáp án:** `[read, write]`. Map không sửa được cấu trúc nhưng list làm value vẫn là object mutable được chia sẻ.

### Bài 9 — `List.copyOf` nhận null không?

```java
List<String> input = new ArrayList<>();
input.add(null);
List<String> result = List.copyOf(input);
```

**Đáp án:** `List.copyOf` ném `NullPointerException` vì collection nguồn chứa phần tử null. Đây là một phần hợp đồng API, không phải lỗi ngẫu nhiên của implementation.

### Bài 10 — Khi nào getter có thể trả thẳng field?

Giả sử lớp lưu:

```java
private final List<String> names;

MyType(List<String> source) {
    this.names = List.copyOf(source);
}
```

**Đáp án:** Nếu hợp đồng chỉ cần snapshot of immutable `String` values, `return names;` là phù hợp vì chính list không sửa được và elements immutable. Không cần clone trên mọi getter chỉ để có identity khác. Nếu `names` chứa mutable element, phải xét sâu hơn.

### Bài 11 — Validation phải bảo vệ được sau constructor?

Constructor kiểm tra tất cả số điểm từ `0` đến `10` nhưng giữ luôn mảng input. Caller thay input thành `-5` sau đó. Invariant có được bảo đảm không?

**Đáp án:** **Không.** Bước validation chỉ kiểm tra trạng thái tại thời điểm gọi; alias ngoài vẫn có thể làm object chứa dữ liệu invalid. Copy dữ liệu lưu trữ và tránh lộ bản copy qua getter.

### Bài 12 — Lộ mutable object dù không có setter?

Một lớp không khai báo bất kỳ setter nào nhưng getter trả `java.util.Date` nội bộ. Có bất biến không?

**Đáp án:** **Chưa chắc.** Caller có thể `date.setTime(...)` trên object trả về. Việc không có setter trên lớp chủ không ngăn mutator của **object con**; cần defensive copy hoặc kiểu bất biến phù hợp.

## 32. Checklist kiểm tra một lớp đóng gói an toàn

1. **Liệt kê field kiểu tham chiếu mutable:** mảng, list, set, map, builder, mutable DTO, Date/Calendar, nested object graph.
2. **Kiểm tra constructor:** có giữ lại cùng object đầu vào không? Có copy rồi validate đúng bản sẽ lưu không?
3. **Kiểm tra setter:** có gán thẳng mutable input cho field không? Có quy tắc ownership cụ thể không?
4. **Kiểm tra getter:** trả trực tiếp backing array/list/map/object hay chỉ giá trị đọc/copy/snapshot?
5. **Kiểm tra cả hai phía:** copy mỗi input mà lộ output vẫn sai; copy mỗi output mà giữ input alias cũng sai.
6. **Kiểm tra tính mutable của phần tử:** `List.copyOf`/`Map.copyOf` là shallow; có nested mutable elements hoặc mutable keys không?
7. **Kiểm tra `clone()` trên mảng đa chiều:** chỉ mảng ngoài được clone nếu không duyệt từng hàng.
8. **Kiểm tra API view:** `Collections.unmodifiableList` là live view, `Arrays.asList` gắn mảng, `subList` thường là view.
9. **Kiểm tra null:** `List.copyOf`/`Map.copyOf`/`Set.copyOf` có hợp đồng từ chối null; API của lớp có tương thích không?
10. **Kiểm tra kiểu trả về record:** component final không chứng minh object con immutable.
11. **Ưu tiên immutable value objects:** `String`/`Instant`/record chứa thực sự immutable fields khi phù hợp.
12. **Nếu API cần cho caller sửa dữ liệu riêng:** trả mutable copy thay vì backing collection.
13. **Nếu API cần caller luôn thấy thay đổi mới:** có thể trả live unmodifiable view **nếu được ghi rõ**, và đảm bảo backing list chỉ được owner thay.
14. **Nếu có builder:** sau `build()`, builder có còn alias vào sản phẩm không? Sản phẩm có cần snapshot?
15. **Nếu có map/set hash keys:** key có immutable `equals`/`hashCode` không?
16. **Nếu có concurrency:** việc tạo snapshot có được đồng bộ đúng khi source bị thay đổi không? Safe publication đã được xem xét chưa?
17. **Đánh giá hiệu năng thực tế:** copy `O(n)` có cần trên mọi getter không, hay có thể dùng API scalar/immutable snapshot được cache?
18. **Viết test hai chiều:** sửa input sau constructor và sửa output sau getter, kiểm tra object không bị thay ngoài hợp đồng.
19. **Kiểm tra cả cấp lồng nhau:** list of lists, map of lists, object chứa Date và mảng.
20. **Viết rõ hợp đồng API:** kết quả là snapshot, live view, mutable copy hay shared mutable reference?

## Ghi nhớ

- **`private` bảo vệ quyền truy cập field, không tự bảo vệ object mutable mà field trỏ tới.** `final` chỉ hạn chế gán lại tham chiếu field, không tự làm object bất biến.
- **Defensive copy ở đầu vào** ngăn caller tiếp tục sửa nội bộ qua dữ liệu đã truyền; **copy hoặc immutable return ở đầu ra** ngăn sửa nội bộ qua getter.
- **Mảng một chiều primitive:** `clone()`/`Arrays.copyOf` thường đủ; **mảng nhiều chiều hoặc mảng object mutable:** phải xét **các phần tử lồng nhau**.
- **`Collections.unmodifiableList` là read-only view**, có thể phản ánh update backing list; **`List.copyOf` là cấu trúc unmodifiable snapshot** của mutable source nhưng **shallow** đối với mutable elements.
- **`Arrays.asList` không phải defensive copy** đối với mảng reference; `set` có thể thay mảng.
- **`Map.copyOf` và `Set.copyOf` không deep-copy keys/values/elements**. Nếu những object ấy mutable, alias có thể còn.
- **Record không tự deeply immutable** nếu component là mảng, collection hoặc mutable object.
- **Dùng immutable value types khi có thể**, và thiết kế API theo hợp đồng ownership/snapshot rõ ràng.
- **Kiểm tra cả hai hướng lộ dữ liệu và mọi tầng mutable** để việc đóng gói thực sự bảo vệ invariant của object.
