# Thành phần mảng trong Java record không tự động được so sánh sâu

## 1. Điều gì xảy ra với mảng trong một record?

Java `record` là một kiểu class giúp khai báo gọn dữ liệu, ví dụ:

```java
record Packet(byte[] payload) {}
```

Nếu không tự khai báo, Java sinh constructor, accessor `payload()` và các phương thức `equals(Object)`, `hashCode()`, `toString()`. Nhưng **record không có cơ chế tự động so sánh sâu các phần tử của mảng**.

Giả sử hai object `Packet` đều chứa dãy byte `{1, 2, 3}`. Nếu mỗi object nhận một mảng được tạo riêng, generated `equals` coi chúng là **khác nhau**. Nguyên nhân là mảng Java dùng `Object.equals` theo **identity tham chiếu**, không so sánh giá trị từng phần tử.

Phân biệt ba điều kiện:

- **Cùng tham chiếu:** `arrayA == arrayB` — hai biến trỏ tới chính một đối tượng mảng.
- **Cùng nội dung mảng một chiều:** `Arrays.equals(arrayA, arrayB)` — cùng độ dài và phần tử tương ứng bằng nhau.
- **Cùng nội dung nhiều tầng mảng:** `Arrays.deepEquals(arrayA, arrayB)` với các kiểu mảng tham chiếu/lồng phù hợp — xét sâu các mảng con.

Không có quy tắc chung nói rằng vì một record “mang giá trị” nên mọi thành phần mutable hoặc dạng mảng tự động có value equality. Ta phải chọn ngữ nghĩa equality phù hợp bài toán.

## 2. Hợp đồng Java SE 17 quy định thế nào?

Tài liệu `java.lang.Record` và Java Language Specification §8.10 xác định generated `equals` kiểm tra cùng class record và equality của **từng component field**:

1. Component kiểu nguyên thủy được so sánh theo quy tắc tương ứng với wrapper `compare`; chẳng hạn hai component `int` có cùng số thì bằng nhau.
2. Component kiểu tham chiếu dùng ngữ nghĩa tương đương `Objects.equals(a, b)`.
3. Quy tắc `Objects.equals` coi hai tham chiếu bằng nhau khi cùng object hoặc khi `a.equals(b)` trả `true` (có xử lý `null`).

Class mảng trong Java không override `Object.equals` để duyệt phần tử; hai mảng khác tham chiếu dù chứa giá trị giống nhau vẫn khác nhau.

| Component | Generated equality của record | Ví dụ |
| --- | --- | --- |
| `int number` | Theo giá trị nguyên thủy | `4` bằng `4` |
| `String title` | Theo `String.equals` | Hai String có cùng nội dung bằng nhau |
| `List<String> items` | Theo `List.equals` | List so sánh các phần tử theo thứ tự |
| `byte[] data` | Theo tham chiếu của mảng | Hai mảng mới chứa `{1, 2}` không bằng |
| `int[][] matrix` | Theo tham chiếu của mảng ngoài | Không tự duyệt các hàng |

Generated `hashCode` được tạo từ các component và tương thích với generated `equals`. **Đừng nhầm với `Arrays.hashCode` hoặc `Arrays.deepHashCode`**: record không tự áp đặt cách tính hash theo nội dung mảng. Thuật toán kết hợp hash chính xác cũng không được Java cam kết chung, vì vậy không nên phụ thuộc vào số hash cụ thể hoặc tin rằng mã băm có thể dùng làm ID bền vững.

Generated `toString` cũng dựa trên component, nhưng nó không cam kết một cách in mảng theo toàn bộ phần tử như `Arrays.toString`. Khi muốn hiển thị nội dung byte, hãy chủ động định dạng.

## 3. Ví dụ Java 17 có thể chạy: cùng phần tử vẫn không bằng

```java
import java.util.Arrays;

public class RecordArrayDemo {
    record RawPacket(byte[] payload) {}

    public static void main(String[] args) {
        byte[] firstArray = {1, 2, 3};
        byte[] secondArray = {1, 2, 3};

        RawPacket a = new RawPacket(firstArray);
        RawPacket b = new RawPacket(secondArray);
        RawPacket c = new RawPacket(firstArray);

        System.out.println(firstArray == secondArray);
        System.out.println(Arrays.equals(firstArray, secondArray));
        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.payload() == firstArray);

        firstArray[0] = 9;
        System.out.println(a.payload()[0]);
        System.out.println(b.payload()[0]);
    }
}
```

Lưu chương trình thành `RecordArrayDemo.java` và chạy:

```bash
javac RecordArrayDemo.java
java RecordArrayDemo
```

Đầu ra xác định:

```text
false
true
false
true
true
9
1
```

**Phân tích:**

- `firstArray == secondArray` là `false` vì hai lần tạo mảng cấp phát hai đối tượng.
- `Arrays.equals(firstArray, secondArray)` là `true` vì tại thời điểm so sánh, nội dung của chúng giống nhau.
- `a.equals(b)` là `false` do hai component `payload` không cùng tham chiếu mảng.
- `a.equals(c)` là `true` vì cùng dùng `firstArray` và cùng kiểu record.
- Accessor `payload()` mặc định trả tham chiếu field, nên `a.payload() == firstArray` là `true`.
- Sửa `firstArray[0] = 9` làm dữ liệu thấy qua `a.payload()` đổi thành `9`, nhưng mảng của `b` vẫn chứa `1` ở phần tử đầu.

Kết quả trên làm rõ hai vấn đề khác nhau: **generated equality không so sánh nội dung mảng**, và **record không bảo đảm bất biến sâu**.

## 4. Vì sao record chỉ bất biến nông?

Đối với một record, mỗi component có field tương ứng `private final`. Với mảng, điều này ngăn field được gán sang tham chiếu mới sau khi khởi tạo, **không ngăn sửa các phần tử trong mảng đang được tham chiếu**.

Ví dụ minh họa (đặt trong phương thức có thể truy cập kiểu `Numbers`):

```java
record Numbers(int[] values) {}

Numbers numbers = new Numbers(new int[] {1, 2});
numbers.values()[0] = 99;
```

Đây là đoạn khái niệm gồm khai báo record và câu lệnh sử dụng; nếu đưa vào tệp hoàn chỉnh thì khai báo `record Numbers...` ở vị trí khai báo kiểu, hai câu lệnh còn lại trong phương thức. Giá trị mảng được nhìn qua accessor có thể đổi dù field record mang tính final.

Tương tự, với `record Item(List<String> tags) {}`, nếu truyền vào một `ArrayList` rồi giữ tham chiếu bên ngoài, việc sửa `ArrayList` có thể làm thay đổi dữ liệu record nhìn thấy, trừ khi constructor đã sao chép/phòng vệ. `List.equals` so sánh theo nội dung, nên các thay đổi ấy còn có thể tác động đến kết quả `equals` và `hashCode`. Với mảng, generated equality vẫn xét identity tham chiếu, nhưng dữ liệu người dùng đọc được qua record có thể thay đổi.

**Bất biến nông** mô tả tính cố định của các field; **bất biến sâu** cần xem xét khả năng biến đổi của toàn bộ cấu trúc dữ liệu được field tham chiếu.

## 5. Mảng một chiều và mảng đa chiều cần phương thức khác nhau

Với mảng một chiều nguyên thủy như `byte[]`, `int[]`, `long[]`, dùng cặp:

- `Arrays.equals(a, b)` nếu muốn so sánh theo từng phần tử.
- `Arrays.hashCode(a)` nếu muốn tạo hash phù hợp với equality đó.

Với mảng tham chiếu một chiều như `String[]`, `Arrays.equals` cũng so sánh các phần tử tương ứng theo equality của từng phần tử. Nhưng nếu mỗi phần tử lại là **một mảng**, equality mảng lồng vẫn theo identity. Để đi sâu vào mảng con, cần `Arrays.deepEquals` và `Arrays.deepHashCode` với kiểu phù hợp.

Ví dụ chương trình độc lập:

```java
import java.util.Arrays;

public class NestedArrayDemo {
    record Matrix(int[][] cells) {}

    public static void main(String[] args) {
        int[][] a = {{1, 2}, {3, 4}};
        int[][] b = {{1, 2}, {3, 4}};

        System.out.println(a == b);
        System.out.println(Arrays.equals(a, b));
        System.out.println(Arrays.deepEquals(a, b));
        System.out.println(new Matrix(a).equals(new Matrix(b)));
    }
}
```

Lưu vào `NestedArrayDemo.java`:

```bash
javac NestedArrayDemo.java
java NestedArrayDemo
```

Đầu ra:

```text
false
false
true
false
```

Dòng thứ hai là `false` vì `Arrays.equals` ở mảng ngoài sẽ so sánh các `int[]` hàng với nhau bằng equality tham chiếu. `Arrays.deepEquals` đệ quy qua các hàng nên trả `true`. Record `Matrix` lại chỉ so sánh hai component `cells` ở mức tham chiếu mảng ngoài, nên generated equality là `false`.

Với `int[][]`, `clone()` của mảng ngoài chỉ tạo bản sao **các tham chiếu hàng**, không tự sao chép từng `int[]` bên trong. Muốn bất biến sâu phải tạo các hàng mới (và tiếp tục xuống sâu khi dữ liệu còn nhiều cấp).

## 6. Record đại diện chuỗi byte: chọn content equality rõ ràng

Nếu miền nghiệp vụ định nghĩa hai `Packet` bằng nhau khi chứa cùng dãy byte, hãy override **cả `equals` và `hashCode`** theo nội dung. Để kiểu đó còn an toàn khi dùng làm khóa `HashMap`/`HashSet`, cần tránh việc mảng nội bộ bị sửa sau khi khởi tạo.

Ví dụ sau bảo vệ cả constructor lẫn accessor:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class SafePacketDemo {
    record ContentPacket(byte[] payload) {
        public ContentPacket {
            Objects.requireNonNull(payload, "payload");
            payload = payload.clone();
        }

        @Override
        public byte[] payload() {
            return payload.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || other instanceof ContentPacket that
                    && Arrays.equals(payload, that.payload);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(payload);
        }

        @Override
        public String toString() {
            return "ContentPacket[payload=" + Arrays.toString(payload) + "]";
        }
    }

    public static void main(String[] args) {
        byte[] left = {1, 2, 3};
        byte[] right = {1, 2, 3};

        ContentPacket a = new ContentPacket(left);
        ContentPacket b = new ContentPacket(right);
        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());

        Set<ContentPacket> packets = new HashSet<>();
        packets.add(a);
        System.out.println(packets.contains(b));

        left[0] = 9;
        System.out.println(a.payload()[0]);

        byte[] exposed = a.payload();
        exposed[1] = 8;
        System.out.println(a.payload()[1]);

        System.out.println(a.equals(b));
        System.out.println(a);
    }
}
```

Lưu tệp `SafePacketDemo.java` rồi chạy:

```bash
javac -encoding UTF-8 SafePacketDemo.java
java SafePacketDemo
```

Kết quả:

```text
true
true
true
1
2
true
ContentPacket[payload=[1, 2, 3]]
```

Đọc đoạn code theo contract:

1. Constructor compact của record sao chép tham số mảng qua `payload.clone()`; compiler lưu tham số đã xử lý vào field component. `ContentPacket` không giữ tham chiếu đến mảng input bên ngoài.
2. Accessor được override để trả **bản sao**, nên code gọi getter không thể sửa trực tiếp mảng nội bộ.
3. `equals` dùng `Arrays.equals` để so nội dung; hai input khác object nhưng cùng byte trở thành hai record bằng nhau.
4. `hashCode` dùng `Arrays.hashCode`, bảo đảm cặp giá trị bằng nhau nhận cùng hash.
5. `HashSet.contains(b)` thành công sau khi thêm `a` do cả equality và hash nhất quán.
6. Sửa mảng `left` hoặc bản sao accessor trả về không ảnh hưởng dữ liệu của `a`, nên record giữ equality/hash ổn định.
7. `toString` tự định dạng nội dung một chiều bằng `Arrays.toString` để tiện quan sát.

**Cần cả hai phía của defensive copy:** Chỉ copy constructor vẫn để lộ mảng qua accessor mặc định; chỉ copy accessor vẫn giữ mảng input gốc có thể sửa. Khi mục tiêu là value object bất biến về nội dung, phải kiểm soát mọi đường giữ và trả tham chiếu mutable.

Ví dụ dùng `byte[]` nên `clone()` sao chép toàn bộ dữ liệu nguyên thủy. Mảng nhiều chiều và array chứa object mutable phải được xem xét sâu hơn; copy mảng ngoài không đảm bảo copy nội dung các object phần tử.

## 7. Một hướng khác: dùng List có equality theo phần tử

Với dữ liệu thực sự là danh sách có thứ tự, có thể dùng `List` trong record thay vì mảng. `List.equals` đã định nghĩa so sánh các phần tử tương ứng.

```java
import java.util.List;

public class ListValueDemo {
    record Codes(List<String> values) {
        public Codes {
            values = List.copyOf(values);
        }
    }

    public static void main(String[] args) {
        Codes a = new Codes(List.of("A", "B"));
        Codes b = new Codes(List.of("A", "B"));

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
    }
}
```

Lưu tệp `ListValueDemo.java`, chạy `javac ListValueDemo.java` và `java ListValueDemo`:

```text
true
true
```

Vì component là `List<String>`, generated record equality dùng `List.equals`; `String` bất biến nên dễ giữ ổn định. `List.copyOf` tạo danh sách không cho sửa cấu trúc, đồng thời không cho chứa phần tử `null`.

Điều này **không có nghĩa `List.copyOf` sao chép sâu**. Nếu danh sách gồm object mutable, việc thay đổi nội dung object phần tử vẫn có thể tác động đến equality/hash. Chọn kiểu dữ liệu và chính sách bất biến theo hợp đồng thực tế, không chỉ theo mức độ thuận tiện khi viết code.

## 8. Có khi nào generated equality theo mảng là điều ta muốn?

Có. Nếu mục tiêu của record là **đánh dấu một vùng đệm cụ thể** hoặc giữ identity của một tài nguyên thay vì giá trị byte, hai mảng riêng dù chứa cùng dữ liệu có thể được xem là hai đối tượng khác nhau. Khi ấy generated equality có thể đúng ý định.

Nhưng nếu record biểu diễn:

- Dữ liệu nhị phân của một thông điệp;
- Vector giá trị số;
- Ma trận, bảng số liệu dạng mảng;
- Bản chụp dữ liệu cần so sánh theo từng phần tử;

thì thường cần xem xét so sánh theo nội dung. Không có một quy tắc thiết kế áp dụng cho mọi class, nhưng **cần xác định contract trước khi tin vào generated equality**.

## 9. Hợp đồng hashCode và collection

Ràng buộc bắt buộc:

`a.equals(b) ⇒ a.hashCode() == b.hashCode()`

Nếu override `equals` để gọi `Arrays.equals` nhưng để nguyên generated `hashCode`, kết quả hash vẫn dựa trên các component theo hợp đồng được sinh, tức chưa được ràng buộc theo nội dung mảng. Hai mảng cùng phần tử nhưng khác identity có thể cho hash khác, trong khi `equals` mới trả `true`: **vi phạm contract**.

Chọn cặp phương thức phù hợp:

| Ngữ nghĩa cần có | Equality | Hash tương thích |
| --- | --- | --- |
| Mảng nguyên thủy một chiều | `Arrays.equals` | `Arrays.hashCode` |
| Mảng tham chiếu một chiều | `Arrays.equals` | `Arrays.hashCode` |
| Mảng lồng với yêu cầu so sánh đệ quy | `Arrays.deepEquals` | `Arrays.deepHashCode` |
| Identity của mảng | Generated record equality | Generated record hashCode |
| List có thứ tự với equality theo phần tử | `List.equals` | `List.hashCode` |

Nếu nội dung mảng tham gia equality/hash, việc sửa mảng khi record nằm trong `HashSet` hoặc làm khóa `HashMap` có thể khiến tra cứu không còn đáng tin cậy. Đây là lý do defensive copy đi cùng chiến lược value equality.

Đừng kiểm thử rằng hai giá trị khác nhau luôn phải cho hash khác nhau. Va chạm hash được phép. Cũng đừng phụ thuộc vào một số hash cụ thể hoặc định dạng generated `toString` như dữ liệu giao thức.

## 10. Những cách sửa chưa đủ

**Chỉ thêm `Arrays.equals` ở một điểm gọi:** Điều đó không đổi `record.equals`, nên khi record đi vào thư viện khác hay dùng làm khóa `Map`, generated equality vẫn theo identity mảng.

**Chỉ override `equals` mà giữ `hashCode` cũ:** Không còn bảo đảm cặp bằng nhau có cùng hash. Phải override hash tương ứng.

**Chỉ clone mảng ở constructor:** Bảo vệ khỏi sửa tham số bên ngoài nhưng hai record sở hữu hai bản copy khác nhau vẫn không bằng nhau theo generated equality. Ngoài ra, accessor có thể trả mảng nội bộ và bị sửa.

**Chỉ clone trong accessor:** Không giải quyết việc constructor giữ tham chiếu tới mảng input đã bị caller sửa; cũng không biến generated equality thành content equality. Generated equality/hash dùng component fields chứ không nhất thiết gọi accessor của record.

**Dùng `Arrays.equals` cho `int[][]` rồi nghĩ đã so mọi số:** Mảng ngoài có các phần tử là mảng con; so nông chỉ thấy identity của các mảng con. Nếu cần so sâu, chọn `Arrays.deepEquals` và `Arrays.deepHashCode`, đồng thời cân nhắc defensive deep copy.

## 11. Câu hỏi tự luyện

**Câu 1.** Hai `record R(int[] data) {}` được tạo bằng hai mảng độc lập cùng chứa `{1, 2}`. Generated `equals` trả gì?

**Đáp án:** `false` vì component `int[]` dùng equality tham chiếu.

**Câu 2.** Hai record cùng kiểu nhận chính **một** mảng làm component. Generated equality có thể trả `true` không?

**Đáp án:** Có, khi mọi component còn lại cũng bằng nhau. Với component mảng, hai bên cùng tham chiếu nên bằng nhau.

**Câu 3.** Một record dùng `Arrays.equals` cho `equals` nhưng không override `hashCode`. Vấn đề ở đâu?

**Đáp án:** Hai mảng khác tham chiếu nhưng cùng nội dung có thể bằng nhau theo `equals` trong khi hash sinh theo component không bảo đảm bằng nhau, vi phạm `Object` contract. Dùng `Arrays.hashCode` cho cùng nội dung mảng.

**Câu 4.** Với `int[][]`, tại sao `Arrays.equals(a, b)` có thể `false` khi `Arrays.deepEquals(a, b)` là `true`?

**Đáp án:** So nông ở mảng ngoài gặp từng phần tử `int[]` và so identity của mảng con. So sâu đi vào từng hàng để so các số nguyên.

**Câu 5.** Một record copy `byte[]` trong constructor, nhưng accessor trả trực tiếp field. Nó đã bất biến theo nội dung chưa?

**Đáp án:** Chưa. Người dùng có thể sửa mảng qua accessor. Cần copy khi trả ra hoặc dùng biểu diễn thực sự immutable.

**Câu 6.** Khi nào generated equality với component `byte[]` có thể phù hợp?

**Đáp án:** Khi hợp đồng kiểu dữ liệu thực sự muốn identity của **đối tượng mảng** thay vì nội dung của dãy byte.

## 12. Ghi nhớ

1. Generated `equals` của record dùng ngữ nghĩa equality của từng **component**, không tự so sánh sâu mọi cấu trúc.
2. Mảng Java dùng equality theo **tham chiếu**; hai mảng cùng nội dung không tự làm hai record bằng nhau.
3. `Arrays.equals` phù hợp khi so mảng một chiều; `Arrays.deepEquals` phù hợp với mảng lồng cần so đệ quy.
4. Khi định nghĩa equality theo nội dung mảng, phải định nghĩa hash tương ứng bằng `Arrays.hashCode` hoặc `Arrays.deepHashCode`.
5. Record chỉ **bất biến nông**; final field không bảo vệ nội dung của mảng hoặc object mutable.
6. Để xây dựng value object ổn định dựa trên mảng, cần defensive copy **khi nhận** và **khi trả** dữ liệu, đồng thời xem xét deep copy khi có cấu trúc lồng.
7. Nếu bài toán cần identity mảng thay vì content equality, generated equality có thể được giữ nguyên; hãy viết rõ ý nghĩa đó trong thiết kế.

Tài liệu chính thức: [`java.lang.Record` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html), [JLS §8.10 – Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10), [`java.util.Arrays`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html) và [`Objects.equals`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).
