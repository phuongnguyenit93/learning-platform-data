# Thành phần mảng và giới hạn so sánh nội dung mặc định trong Java record

## 1. Vấn đề cốt lõi: record mang giá trị nhưng mảng vẫn là đối tượng tham chiếu

`record` là một cách khai báo kiểu mang dữ liệu với các thành phần (components) được mô tả trong header. Java tự sinh constructor chính tắc, các accessor và ba phương thức `equals`, `hashCode`, `toString` khi bạn không khai báo tường minh. Record là tính năng chính thức từ **Java 16** và hoạt động bình thường trên **Java 17+**, không cần preview.

Xét:

~~~java
record Packet(byte[] data) {}
~~~

Java tự tạo trường thành phần `private final byte[] data`, accessor `data()` và các phương thức so sánh/in mô tả. Nhưng `final` chỉ ngăn **gán lại tham chiếu** trong record; nó không ngăn sửa các phần tử của mảng. Mặc định, accessor trả **chính tham chiếu tới mảng đang lưu**, không tự sao chép.

Một khác biệt quan trọng khác: hai mảng có cùng phần tử **không nhất thiết được xem là bằng nhau** khi dùng `Object.equals`. Mảng Java không ghi đè `Object.equals` để so sánh từng phần tử. Khi một component record là mảng, `equals` được sinh của record so sánh component tham chiếu theo ngữ nghĩa `Objects.equals`, vì vậy với mảng thì về cơ bản là **cùng đối tượng mảng hay không**.

~~~java
record Packet(byte[] data) {}

Packet first = new Packet(new byte[] {1, 2, 3});
Packet second = new Packet(new byte[] {1, 2, 3});

System.out.println(first.equals(second));                // false
System.out.println(java.util.Arrays.equals(
        first.data(), second.data()));                     // true
~~~

Đây là đoạn minh họa cần đặt trong class hoặc phương thức thích hợp. Hai lần `new byte[]` tạo hai mảng khác nhau dù nội dung giống hệt. `first.equals(second)` là `false`; `Arrays.equals` trên hai mảng byte trả `true`.

**Hệ quả học tập:** đừng suy từ tên “record” rằng Java tự so sánh sâu tất cả dữ liệu bên trong nó. Record có ngữ nghĩa giá trị dựa trên **ngữ nghĩa so sánh của từng component**; nếu component là mảng, phép so sánh mặc định của mảng là theo tham chiếu.

## 2. Ba phương thức được sinh có ý nghĩa gì với array component?

Giả sử:

~~~java
record FileChunk(int part, byte[] bytes) {}
~~~

| Thành phần | Hành vi mặc định | Điều cần lưu ý |
| --- | --- | --- |
| `equals(Object)` | So sánh từng component; `part` theo giá trị số, `bytes` theo `Objects.equals` | Hai mảng byte nội dung giống nhau nhưng là hai mảng khác nhau khiến hai record **không bằng nhau** |
| `hashCode()` | Kết hợp mã băm từ các component theo hợp đồng record | Hash của component mảng tuân theo `hashCode` của chính đối tượng mảng, **không phải** `Arrays.hashCode(bytes)` |
| `toString()` | Mô tả tên record, tên và giá trị các component | Mảng thường hiện dạng đại diện tham chiếu như `[B@...`, **không** liệt kê `[1, 2, 3]` |
| Accessor `bytes()` | Trả tham chiếu component đã lưu | Người gọi có thể sửa `record.bytes()[0]`, khiến dữ liệu bên trong record thay đổi |

Vì thuật toán chi tiết tạo hash code và chuỗi của record không được chuẩn hóa thành một định dạng cố định, **không** viết kiểm thử dựa trên số hash cụ thể, hậu tố `[B@...` cụ thể hoặc toàn bộ format `toString()`. Điều cần kiểm tra là **ý nghĩa**, không phải định dạng không được bảo đảm.

Hai record cùng giữ **chính một tham chiếu mảng** có thể được xem là bằng nhau, dù bất kỳ ai đang giữ tham chiếu đó đều có thể sửa nội dung mảng:

~~~java
byte[] shared = {10, 20};
var x = new FileChunk(1, shared);
var y = new FileChunk(1, shared);

System.out.println(x.equals(y));  // true: cùng part, cùng mảng
shared[0] = 99;
System.out.println(x.bytes()[0]); // 99
~~~

Việc đổi phần tử **không biến** `x` và `y` thành hai đối tượng khác nhau. Nhưng điều đó cũng có nghĩa `record` mặc định **không đảm bảo** dữ liệu ảnh chụp (snapshot) được cố định từ lúc khởi tạo.

## 3. Tại sao bất biến nông gây lỗi thực tế?

Record không có setter được tạo tự động, nhưng mảng component vẫn có hai đường thay đổi:

**Đường 1 — Sửa mảng đầu vào sau khi tạo record.**

~~~java
byte[] input = {1, 2};
var packet = new Packet(input);
input[0] = 9;

System.out.println(packet.data()[0]); // 9
~~~

**Đường 2 — Sửa mảng được trả từ accessor.**

~~~java
var packet = new Packet(new byte[] {1, 2});
packet.data()[1] = 7;

System.out.println(packet.data()[1]); // 7
~~~

Điều này có thể gây:

- Dữ liệu đi qua một API “trông như immutable” nhưng thực tế bị sửa bởi nơi khác.
- Một phép tính đọc record ở thời điểm khác cho kết quả khác; các phần tử mảng không được bảo vệ bởi `final`.
- Một bản ghi dùng làm key của cấu trúc dữ liệu băm bị sai ngữ nghĩa nếu bạn tự tạo `hashCode` phụ thuộc **nội dung có thể thay đổi** của mảng.
- Snapshot/caching hoặc kiểm thử so sánh dữ liệu có hành vi khó hiểu.
- Nội dung nhạy cảm từ mảng bị công bố qua accessor hoặc logging không kiểm soát.

Lưu ý về key: với record mặc định, array component thường đóng góp **identity hash**, nên việc sửa một phần tử mảng không nhất thiết làm hash mặc định của record thay đổi. Rủi ro “hashCode đổi sau khi insert vào `HashSet`/`HashMap`” đặc biệt xảy ra nếu bạn **đã ghi đè hashCode để băm nội dung** nhưng vẫn để mảng bị sửa. Không được nhầm hai vấn đề này.

Khi record được dùng để biểu diễn **giá trị nhị phân, tọa độ, danh sách điểm số, ảnh thu nhỏ, khóa dữ liệu hoặc trạng thái tính toán**, cần quyết định rõ: component có so sánh theo nội dung không, và dữ liệu có phải bất biến từ sau construction không?

## 4. So sánh theo nội dung bằng `java.util.Arrays`

API `Arrays` cung cấp các phép toán theo nội dung cho nhiều kiểu mảng:

| Mục đích | Mảng một chiều | Mảng lồng nhau |
| --- | --- | --- |
| So sánh nội dung | `Arrays.equals(a, b)` | `Arrays.deepEquals(a, b)` đối với mảng tham chiếu chứa mảng con |
| Tạo hash theo nội dung | `Arrays.hashCode(a)` | `Arrays.deepHashCode(a)` |
| In các phần tử | `Arrays.toString(a)` | `Arrays.deepToString(a)` |

**Chọn đúng overload:**

- `int[]`, `byte[]`, `long[]`, `char[]` và các mảng primitive một chiều: dùng overload tương ứng của `Arrays.equals`, `hashCode`, `toString`.
- `String[]`: `Arrays.equals(Object[], Object[])` so sánh các phần tử bằng `Objects.equals`; với `String`, phép so sánh theo nội dung chuỗi.
- `int[][]` hoặc `String[][]`: mảng ngoài thực chất chứa các **mảng con**; dùng `deepEquals/deepHashCode/deepToString` nếu muốn so sánh sâu theo phần tử.
- `List<int[]>`: tự động so sánh `List.equals` **không** làm các mảng trong list được so sánh sâu. Cần thiết kế representation hoặc comparator chuyên biệt.

Ví dụ:

~~~java
import java.util.Arrays;

int[] a = {2, 4, 6};
int[] b = {2, 4, 6};

System.out.println(a.equals(b));              // false
System.out.println(Arrays.equals(a, b));       // true
System.out.println(Arrays.hashCode(a)
        == Arrays.hashCode(b));                 // true
System.out.println(Arrays.toString(a));        // [2, 4, 6]

int[][] left = {{1, 2}, {3}};
int[][] right = {{1, 2}, {3}};

System.out.println(Arrays.equals(left, right));      // false
System.out.println(Arrays.deepEquals(left, right));  // true
~~~

Đây là đoạn minh họa trong thân phương thức. `Arrays.equals(left, right)` nhận overload cho `Object[]` vì `int[][]` là mảng của `int[]`; nó so sánh từng mảng con bằng `equals` mặc định theo tham chiếu, nên kết quả `false`.

**Quy tắc đi đôi:** nếu dùng `Arrays.equals` để ghi đè `equals` của record, phải dùng `Arrays.hashCode` tương thích; nếu dùng `deepEquals` cho mảng nhiều chiều, dùng `deepHashCode` tương ứng. Nếu chỉ ghi đè một phương thức, đối tượng có thể vi phạm hợp đồng `equals/hashCode` và hoạt động sai trong các tập/map băm.

## 5. Ví dụ chương trình Java 17+ chạy độc lập

Ví dụ dưới đây so sánh record mặc định với record được thiết kế có **snapshot an toàn và equality theo nội dung**, rồi dùng record chứa immutable list làm phương án thay thế khi dữ liệu phù hợp.

Lưu chính xác thành **`RecordArrayDemo.java`** (UTF-8):

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class RecordArrayDemo {

    record RawPacket(byte[] payload) {}

    record SafePacket(byte[] payload) {
        // Bảo vệ khỏi sửa mảng đầu vào sau khi khởi tạo.
        SafePacket {
            payload = Objects.requireNonNull(payload, "payload").clone();
        }

        // Bảo vệ khỏi sửa mảng bên trong qua accessor.
        @Override
        public byte[] payload() {
            return payload.clone();
        }

        // So sánh nội dung, không so sánh identity của mảng.
        @Override
        public boolean equals(Object obj) {
            return obj instanceof SafePacket other
                    && Arrays.equals(payload, other.payload);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(payload);
        }

        @Override
        public String toString() {
            return "SafePacket[payload="
                    + Arrays.toString(payload) + "]";
        }
    }

    record Labels(List<String> values) {
        Labels {
            values = List.copyOf(values);
        }
    }

    public static void main(String[] args) {
        RawPacket r1 = new RawPacket(new byte[] {1, 2, 3});
        RawPacket r2 = new RawPacket(new byte[] {1, 2, 3});

        System.out.println("raw equals: " + r1.equals(r2));
        System.out.println("array contents: "
                + Arrays.equals(r1.payload(), r2.payload()));

        byte[] shared = {4, 5};
        System.out.println("same array: "
                + new RawPacket(shared).equals(new RawPacket(shared)));

        byte[] rawInput = {1, 2, 3};
        RawPacket exposed = new RawPacket(rawInput);
        rawInput[0] = 9;
        exposed.payload()[1] = 8;
        System.out.println("raw after changes: "
                + Arrays.toString(exposed.payload()));

        byte[] safeInput = {1, 2, 3};
        SafePacket s1 = new SafePacket(safeInput);
        SafePacket s2 = new SafePacket(new byte[] {1, 2, 3});

        System.out.println("safe equals: " + s1.equals(s2));
        System.out.println("safe hash match: "
                + (s1.hashCode() == s2.hashCode()));

        safeInput[0] = 9;
        byte[] returned = s1.payload();
        returned[1] = 8;
        System.out.println("safe after changes: "
                + Arrays.toString(s1.payload()));
        System.out.println("safe display: " + s1);

        Set<SafePacket> unique = new HashSet<>();
        unique.add(s1);
        unique.add(s2);
        System.out.println("safe set size: " + unique.size());

        Labels l1 = new Labels(List.of("a", "b"));
        Labels l2 = new Labels(List.of("a", "b"));
        System.out.println("list record equals: " + l1.equals(l2));
    }
}
~~~

Chạy trên JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 RecordArrayDemo.java
java RecordArrayDemo
~~~

**Đầu ra chính xác:**

~~~text
raw equals: false
array contents: true
same array: true
raw after changes: [9, 8, 3]
safe equals: true
safe hash match: true
safe after changes: [1, 2, 3]
safe display: SafePacket[payload=[1, 2, 3]]
safe set size: 1
list record equals: true
~~~

**Giải thích theo từng phần:**

1. `r1` và `r2` có hai mảng khác nhau, nên `RawPacket.equals` mặc định trả `false`; `Arrays.equals` so sánh từng byte, nên trả `true`.
2. Hai `RawPacket` cùng giữ `shared` thì bằng nhau theo mặc định, cho dù chúng là hai đối tượng record khác nhau.
3. `RawPacket` không clone khi nhận mảng hoặc khi trả mảng; cả sửa từ biến gốc và sửa qua accessor đều đổi dữ liệu bên trong.
4. Compact canonical constructor của `SafePacket` clone mảng lúc tạo. Accessor `payload()` clone trước khi trả. Vì vậy hai đường sửa từ ngoài không làm đổi nội dung bên trong.
5. `SafePacket.equals/hashCode` được cài đặt thống nhất dựa trên nội dung; hai record có byte giống nhau được xem là bằng nhau, nên `HashSet` chỉ giữ một phần tử.
6. `SafePacket.toString()` chủ động dùng `Arrays.toString`, giúp người đọc thấy phần tử. Với dữ liệu bí mật, **không** in payload như ví dụ; cần redaction hoặc thông tin mô tả an toàn.
7. `Labels` dùng `List.copyOf` để lưu một danh sách không thể sửa qua API của nó. Vì `List.equals/hashCode` dùng ngữ nghĩa nội dung phần tử và `String` là immutable, record với list này có thể giữ `equals/hashCode` mặc định mà vẫn phù hợp với so sánh theo giá trị.

## 6. Vì sao cần cả clone đầu vào lẫn clone ở accessor?

Chỉ clone trong constructor:

~~~java
record InputOnly(byte[] bytes) {
    InputOnly {
        bytes = bytes.clone();
    }
}
~~~

sẽ ngăn người gọi sửa `byte[]` đã truyền vào, **nhưng accessor mặc định `bytes()` vẫn trả mảng nội bộ**. Người gọi có thể làm:

~~~java
InputOnly packet = new InputOnly(new byte[] {1, 2});
packet.bytes()[0] = 9; // Vẫn sửa được mảng bên trong.
~~~

Chỉ clone trong accessor:

~~~java
record OutputOnly(byte[] bytes) {
    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

sẽ bảo vệ một đường đọc, nhưng caller vẫn có thể giữ và sửa mảng `bytes` đã đưa vào constructor. Nếu mục tiêu là snapshot an toàn, cần bảo vệ **cả hai chiều**.

Cũng phải quyết định chính sách đối với `null`. Ví dụ `SafePacket` ở mục 5 dùng `Objects.requireNonNull` để từ chối `null`. Nếu muốn cho phép `null`, constructor và accessor phải xử lý `null` tường minh; cả `Arrays.equals`, `Arrays.hashCode` đều có overload chấp nhận mảng `null`, nhưng lệnh `clone()` sẽ ném `NullPointerException` nếu mảng là `null`.

Sao chép không phải “đóng băng” bản thân Java array: mỗi bản sao vẫn là mảng mutable. Thiết kế chỉ đảm bảo người ngoài không lấy được **tham chiếu tới mảng bên trong** qua những API được cung cấp, với giả định code của record không cố ý rò rỉ tham chiếu từ đường khác.

## 7. Lưu ý đặc biệt: bất biến sao chép của record (copy invariant)

Javadoc của `java.lang.Record` mô tả kỳ vọng: nếu một record `r` được dựng lại bằng cách gọi canonical constructor với kết quả từ các accessor của chính nó, bản sao phải bằng `r`:

~~~java
R copy = new R(r.c1(), r.c2(), /* ... */ r.cn());
// Kỳ vọng hợp đồng record: r.equals(copy) == true
~~~

Đây là **cú pháp minh họa khái niệm**, không phải Java chạy độc lập; `R` và `c1`, `c2` chỉ đại diện cho record và components bất kỳ.

Với một record chứa mảng, nếu **chỉ** clone đầu vào và clone accessor nhưng **giữ nguyên equals mặc định**, kỳ vọng này bị phá vỡ:

~~~java
record CopiedButIdentity(byte[] bytes) {
    CopiedButIdentity {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}

var first = new CopiedButIdentity(new byte[] {1, 2});
var reconstructed = new CopiedButIdentity(first.bytes());
System.out.println(first.equals(reconstructed)); // false
~~~

Mỗi lần copy tạo **tham chiếu mảng mới**, trong khi generated `equals` so sánh identity của mảng. Cả hai có dữ liệu giống nhau nhưng không được xem là bằng nhau; record trên gây bất ngờ về ngữ nghĩa giá trị và không giữ được copy invariant.

Vì vậy, khi quyết định dùng mảng như **giá trị** của record, cần thiết kế đồng bộ:

1. Clone mảng ở constructor (snapshot đầu vào).
2. Clone mảng ở accessor (không rò rỉ tham chiếu nội bộ).
3. Ghi đè `equals` bằng `Arrays.equals` hoặc `Arrays.deepEquals` theo cấu trúc.
4. Ghi đè `hashCode` bằng hàm băm nội dung tương ứng.
5. Cân nhắc `toString` rõ ràng nếu cần mô tả phần tử; xử lý dữ liệu nhạy cảm.
6. Kiểm tra copy invariant và tính ổn định sau khi caller sửa các mảng từng nhận/trả.

Nếu các bước này quá phức tạp so với yêu cầu, cân nhắc thay mảng bằng một representation có ngữ nghĩa giá trị phù hợp hoặc dùng class có quyền kiểm soát đóng gói rõ ràng hơn. Không phải hệ thống nào cũng cần so sánh binary payload theo nội dung; hợp đồng sử dụng thực tế quyết định.

## 8. Nhiều component: không được quên trường còn lại

Record thực tế có thể có ID, loại dữ liệu và một mảng:

~~~java
record Segment(long id, String type, byte[] data) {}
~~~

Nếu cần equality theo cả ba component, một override đúng phải xét **mọi trường thuộc identity/value contract**:

~~~java
@Override
public boolean equals(Object obj) {
    return obj instanceof Segment other
            && id == other.id
            && java.util.Objects.equals(type, other.type)
            && java.util.Arrays.equals(data, other.data);
}

@Override
public int hashCode() {
    int result = Long.hashCode(id);
    result = 31 * result + java.util.Objects.hashCode(type);
    result = 31 * result + java.util.Arrays.hashCode(data);
    return result;
}
~~~

Mã trên là **mảnh phương thức để đặt vào thân record `Segment`**; nếu dùng để thay thế trong ứng dụng bất biến, cũng cần constructor/accessor copy mảng như mục 5. Công thức kết hợp hash chỉ là cách cài đặt nhất quán, **không phải** thuật toán hash bắt buộc của record. Không nên so sánh giá trị hash số giữa các phiên bản JDK.

Nếu chỉ ghi đè `equals` theo nội dung mảng nhưng quên `id` hoặc `type`, có thể vô tình xem hai segment khác nhau là một. Ngược lại, nếu `equals` xét mọi trường mà `hashCode` chỉ xét một phần, nó vẫn có thể đúng về mặt bắt buộc “bằng nhau thì hash bằng nhau”, nhưng tăng collision không cần thiết; thiết kế rõ các thành phần liên quan để tránh nhầm lẫn.

**Phân biệt identity của domain và content equality của record.** Nếu hai bản ghi có ID giống nhau nhưng nội dung khác nhau vẫn được coi là cùng một thực thể theo nghiệp vụ, đó là lựa chọn thiết kế domain riêng; record mặc định thường mang **tất cả** components vào equality. Đừng tự bỏ trường khỏi `equals` mà không xác định trước hợp đồng.

## 9. Mảng nhiều chiều cần deep equality **và deep copy**

Với `int[][]`, chỉ gọi `clone()` trên mảng ngoài tạo ra một mảng ngoài mới nhưng **các mảng hàng bên trong vẫn được chia sẻ**:

~~~java
int[][] original = {{1, 2}, {3, 4}};
int[][] outerCopy = original.clone();

original[0][0] = 9;
System.out.println(outerCopy[0][0]); // 9
~~~

Nếu yêu cầu dữ liệu không bị sửa từ ngoài, hãy sao chép **từng hàng**. Ví dụ sau là **mảnh mã class đầy đủ về mặt nội bộ**, có thể đặt trong một class và gọi từ `main`:

~~~java
import java.util.Arrays;
import java.util.Objects;

final class MatrixExample {
    static int[][] copyRows(int[][] source) {
        Objects.requireNonNull(source, "source");
        int[][] result = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            result[i] = Objects.requireNonNull(
                source[i], "row " + i
            ).clone();
        }
        return result;
    }

    record Matrix(int[][] cells) {
        Matrix {
            cells = copyRows(cells);
        }

        @Override
        public int[][] cells() {
            return copyRows(cells);
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Matrix other
                    && Arrays.deepEquals(cells, other.cells);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(cells);
        }

        @Override
        public String toString() {
            return "Matrix[cells="
                    + Arrays.deepToString(cells) + "]";
        }
    }
}
~~~

`int[][]` cũng là một `Object[]` của các mảng `int[]`, nên `Arrays.deepEquals` và `deepHashCode` xử lý được cấu trúc này. Hai bước độc lập:

- **Deep comparison** quyết định khi nào các giá trị được coi là bằng nhau.
- **Deep copy** quyết định dữ liệu bên trong có được bảo vệ khỏi thay đổi từ bên ngoài không.

Chỉ làm một trong hai chưa đảm bảo **cả tính bất biến mong muốn lẫn value equality**. Với mảng nhiều cấp chứa object mutable, sao chép các tầng mảng vẫn không sao chép sâu các object phần tử; cần thiết kế copy theo loại dữ liệu thực. Mảng có cấu trúc vòng tham chiếu cũng không thích hợp để mặc định dùng các hàm deep của `Arrays`, vì API có giới hạn khi các mảng chứa lẫn nhau theo chu kỳ.

## 10. Cách thay thế array component bằng immutable list

Nếu dữ liệu là tập phần tử có thứ tự thông thường, dùng `List` với bản sao không thể sửa thường đơn giản hơn:

~~~java
import java.util.List;
import java.util.Objects;

record Tags(List<String> values) {
    Tags {
        values = List.copyOf(
            Objects.requireNonNull(values, "values")
        );
    }
}
~~~

Lợi ích:

- `List.equals` so sánh số lượng, thứ tự và sự bằng nhau của **từng phần tử**; hai list độc lập nhưng cùng các `String` tương ứng sẽ bằng nhau.
- `List.hashCode` nhất quán với `List.equals`. Generated `equals/hashCode` của `Tags` sẽ hoạt động hợp lý cho danh sách chuỗi.
- `List.copyOf` tạo hoặc tái sử dụng một danh sách **không thể chỉnh sửa** qua API `List`, không chia sẻ một `ArrayList` mutable với caller.
- `String` immutable, nên không cần clone từng phần tử trong ví dụ này.

Tuy vậy, `List.copyOf` chỉ đảm bảo danh sách không sửa được qua API, **không deep copy đối tượng phần tử**. Nếu dùng `List<byte[]>`, mỗi `byte[]` vẫn mutable và so sánh theo tham chiếu; cần cách biểu diễn khác hoặc copy từng mảng kèm cơ chế equality theo nội dung.

Không chuyển mọi `byte[]` sang `List<Byte>` theo thói quen. `List<Byte>` đòi hỏi boxing từng byte và có chi phí bộ nhớ/hiệu năng; dữ liệu nhị phân lớn có thể phù hợp với mảng được quản lý an toàn hơn. Chọn thiết kế dựa trên kích thước dữ liệu, tần suất copy, yêu cầu equality và mức độ bảo vệ.

## 11. Tình huống sử dụng trong ứng dụng

### 11.1. DTO chứa hash/digest

Ví dụ:

~~~java
record DigestResult(String algorithm, byte[] digest) {}
~~~

Nếu hai digest bằng nhau khi **thuật toán và bytes** bằng nhau, generated `equals` không đủ. Một response DTO có thể được so sánh trong test, lưu vào cache hoặc truyền qua lớp service. Với dữ liệu mang ý nghĩa giá trị, nên có defensive copy và content-based equality hoặc đổi thành một kiểu bất biến chuyên dụng.

Lưu ý: so sánh mã băm mật mã có thể yêu cầu **so sánh constant-time** trong ngữ cảnh nhạy cảm với timing; `Arrays.equals` là API equality thông thường và không nên mặc nhiên coi nó đáp ứng yêu cầu bảo mật đó. Quy tắc an toàn thuộc về bài toán bảo mật, nằm ngoài mục đích so sánh giá trị thông thường của record.

### 11.2. Record làm key của `HashMap` hoặc phần tử `HashSet`

Nếu đưa `record Key(byte[] bytes) {}` vào `HashMap` rồi truy xuất bằng một `Key` mới bọc một mảng khác có cùng bytes, `Map.get` sẽ **không tìm được** theo ngữ nghĩa mặc định vì key không bằng nhau. Nếu muốn tra cứu theo bytes, dùng kiểu key có `Arrays.equals/hashCode` nhất quán và bảo vệ khỏi mutation.

Nếu tự tạo content-based hash nhưng để bytes mutable, việc sửa mảng sau khi thêm key có thể làm hash thay đổi, khiến ngay cả `containsKey` cho chính đối tượng đó không hoạt động như kỳ vọng. Vì vậy copy dữ liệu tại biên là một phần quan trọng trong thiết kế key giá trị.

### 11.3. Kết quả truy vấn chứa mảng

Một projection query trả `byte[] fileBytes` hoặc `int[] scores` có thể là một snapshot của dữ liệu khi đọc. Nhưng nếu record để lộ mảng, code caller có thể vô tình đổi snapshot. Khi cần chuyển record qua nhiều tầng, cân nhắc clone lúc tạo/đọc và content equality theo yêu cầu; hoặc giữ mảng trong một lớp đóng gói có API đọc chuyên biệt.

### 11.4. Không cần nội dung equality

Có những mô hình **chủ động** xem array identity là quan trọng, chẳng hạn handle dùng chung đến một bộ đệm mutable. Khi đó, hành vi `equals` mặc định có thể phù hợp với mục đích rất cụ thể. Tuy nhiên, kiểu dữ liệu đó mang tính **handle/reference**, không hẳn là value record theo trực giác. Viết rõ hợp đồng và cân nhắc class thường nếu cần vòng đời, đồng bộ, quản lý tài nguyên hoặc phương thức thao tác.

## 12. Lỗi phổ biến và cách khắc phục

| Lỗi/hiểu nhầm | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| “Record có `equals` nên so sánh mảng theo nội dung.” | `Object.equals` của array theo tham chiếu | Ghi đè `equals` bằng `Arrays.equals` hoặc dùng kiểu component có value equality |
| “`final byte[]` là mảng bất biến.” | `final` khóa tham chiếu, không khóa phần tử | Defensive copy hoặc đổi representation |
| “Chỉ clone trong constructor là đủ.” | Accessor mặc định vẫn làm lộ mảng | Clone ở **cả constructor và accessor** |
| “Chỉ clone trong accessor là đủ.” | Caller vẫn giữ mảng đầu vào | Clone cả đầu vào |
| “Clone hai chiều rồi để mặc định `equals`.” | Hai bản sao với mảng khác tham chiếu không bằng nhau; phá copy invariant | Cài content-based `equals/hashCode` nhất quán |
| “Ghi đè `equals` nhưng không ghi đè `hashCode`.” | Vi phạm hợp đồng equals/hashCode | Thiết kế hai phương thức cùng tiêu chí |
| “`Arrays.equals` đủ cho `int[][]`.” | So sánh các mảng con theo identity | Dùng `Arrays.deepEquals` / `deepHashCode` |
| “`int[][].clone()` sao chép sâu.” | Mảng con vẫn chia sẻ | Clone từng hàng nếu cần snapshot |
| “`List.copyOf` copy sâu mọi phần tử.” | Object/array phần tử vẫn được chia sẻ | Chỉ dùng với phần tử immutable hoặc tự snapshot chúng |
| “Hash code giống nhau nghĩa là hai records bằng nhau.” | Collision vẫn có thể xảy ra | Kiểm tra `equals`, không suy diễn từ hash |
| “`toString` mặc định in rõ phần tử mảng.” | Array thường hiện dạng tham chiếu; format record không cố định | Dùng `Arrays.toString/deepToString` cho hiển thị có chủ đích |
| “In toàn bộ mảng luôn tốt.” | Có thể lộ byte bí mật hoặc log quá lớn | Chỉ in metadata/độ dài hoặc redaction theo hợp đồng |

## 13. Checklist thiết kế record có array component

Trước khi công bố hoặc sử dụng record chứa mảng, kiểm tra:

1. **Nghĩa của dữ liệu**: cần so sánh theo *nội dung*, hay thật sự là một *tham chiếu* tới buffer có thể thay đổi?
2. **Bất biến bên ngoài**: caller có thể sửa array gốc hoặc array trả về từ accessor không? Có cần snapshot lúc construction và copy lúc đọc?
3. **Quy tắc equals/hashCode**: đã dùng cùng tập components và `Arrays.equals/hashCode` hoặc `deepEquals/deepHashCode` tương ứng chưa?
4. **Record copy invariant**: nếu dựng record mới từ accessor của record cũ, kết quả có bằng nhau không?
5. **Mảng nhiều chiều**: đã clone đúng tất cả cấp mutable cần bảo vệ chưa?
6. **Null và dữ liệu lỗi**: constructor có từ chối mảng `null` hoặc mô tả cách xử lý tường minh chưa?
7. **Dữ liệu nhạy cảm**: accessor và `toString` có thể lộ gì? Có rủi ro khi log hoặc serialization?
8. **Collection keys**: record có dùng làm key của map hoặc phần tử set không? Hash có giữ ổn định sau khi thêm đối tượng vào tập?
9. **Kích thước dữ liệu**: copy có tốn bộ nhớ/CPU đáng kể không? Có cần API chuyên dụng hoặc kiểu bất biến khác?
10. **Kiểm thử**: thử hai mảng bằng nội dung nhưng khác tham chiếu, cùng tham chiếu, mutation cả hai chiều, `HashSet` và copy invariant.

## 14. Bài tập thực hành

**Bài 1 — Dự đoán kết quả.** Với `record R(int[] values) {}`, dự đoán `new R(new int[]{1,2}).equals(new R(new int[]{1,2}))`; sau đó dùng `Arrays.equals` để kiểm chứng. Giải thích vì sao kết quả khác nhau.

**Bài 2 — Phát hiện lỗ hổng snapshot.** Cài `record Image(int[] pixels)` chỉ clone mảng trong compact constructor; gọi `pixels()[0] = 99`. Thêm accessor defensive copy và xác định vì sao vẫn phải cân nhắc ghi đè equals/hashCode.

**Bài 3 — Thử copy invariant.** Tạo `SafePacket` như mục 5, rồi:

~~~java
SafePacket original = new SafePacket(new byte[] {5, 6});
SafePacket copy = new SafePacket(original.payload());
System.out.println(original.equals(copy)); // true
~~~

Dùng mô hình `CopiedButIdentity` ở mục 7 để so sánh và giải thích sự khác biệt.

**Bài 4 — Mảng 2 chiều.** Với `int[][]`, cho hai ma trận cùng giá trị nhưng có các hàng là mảng mới. Kiểm tra `Arrays.equals`, `Arrays.deepEquals` và sửa một ô của dữ liệu gốc sau khi tạo record. Viết constructor/accessor copy từng hàng và cặp equals/hashCode theo nội dung sâu.

**Bài 5 — Thiết kế API.** Một API trả `record SearchResult(String id, byte[] preview)`. Hãy chọn giữa: (a) dùng `byte[]` với defensive copy và custom equality, (b) một immutable value type phù hợp, (c) thay bằng URL/ID tham chiếu tới file. Giải thích dựa trên kích thước preview, nhu cầu so sánh và quyền truy cập.

## Tài liệu chính thức

- [Oracle — Record (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html): hợp đồng equality của component, cách tạo copy từ accessor và giới hạn thuật toán `hashCode/toString`.
- [Oracle — Record Classes (Java SE 21)](https://docs.oracle.com/en/java/javase/21/language/records.html): cách khai báo record, compact constructor, accessor tường minh, semantics của thành phần mutable.
- [Oracle — Arrays (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): `equals/hashCode/toString`, `deepEquals/deepHashCode/deepToString` và các overload.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): thiết kế record đã được chuẩn hóa từ Java 16 và ngữ nghĩa data carrier.
- [Java Language Specification §8.10 — Record Classes (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10): quy định chính thức về các thành phần, constructor và phương thức sinh của record.
